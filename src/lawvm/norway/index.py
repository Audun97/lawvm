"""Index Norway amendment sources into replayable metadata."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any, Optional, cast

from lawvm.core.diagnostic_records import diagnostic_detail
from lawvm.core.source_lane import SourceLaneAttempt, SourceLaneSelectionEvidence
from lawvm.norway.commencement_instruments import (
    NOCommencementActPartEvidence,
    NOCommencementInstrumentCandidate,
    NOCommencementInstrumentCoverage,
    NOCommencementParseStatus,
    authorize_no_commencement_instruments,
    parse_no_commencement_instrument,
)
from lawvm.norway.grafter import (
    NOBeriktigetReannouncement,
    iter_no_document_change_ops,
    lovdata_amendment_filename_to_id,
    no_beriktiget_reannouncement,
    no_part_law_ids,
    no_superseded_announcement_dates,
)
from lawvm.norway.sources import (
    NO_UNRESOLVED_EFFECTIVE_STATUSES,
    NOCommencementShape,
    NODeclaredChangeTargets,
    NOEffectiveDate,
    NOEffectiveStatus,
    NOLocatedArtifact,
    coerce_no_commencement_shape,
    declared_change_targets_from_amendment,
    effective_date_from_amendment,
    iter_no_amendment_artifacts,
    iter_no_forskrift_artifacts,
    iter_no_unmapped_lovtidend_xml_members,
    no_source_metadata,
    parse_header_value,
    resolve_no_source_path,
)
from lawvm.replay_adjudication import CompileAdjudication
from lawvm.core.quirks_disposition import QuirksDisposition, coerce_quirks_disposition

NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR = "no_acquisition_duplicate_logical_locator"
NO_AMENDMENT_INDEX_STAGED_COMMENCEMENT_COLLAPSED = (
    "no_amendment_index_staged_commencement_collapsed"
)
# W-84, the two receipts of the beriktiget/utgått correction lane. Neither
# supersession is ever silent: a matched pair says so, and an unmatched half says
# so more loudly, because an unmatched half means the machinery is knowingly
# replaying (or knowingly ignoring) text Lovdata has flagged.
NO_BERIKTIGET_ANNOUNCEMENT_PAIRED = "no_beriktiget_announcement_paired"
NO_BERIKTIGET_ANNOUNCEMENT_UNPAIRED = "no_beriktiget_announcement_unpaired"


@dataclass(frozen=True)
class NOAmendmentIndexEntry:
    source_id: str
    archive: str
    member_name: str
    effective_status: str
    effective_date: Optional[str] = None
    raw_date_in_force: str = ""
    title: str = ""
    base_ids: tuple[str, ...] = ()
    n_ops: int = 0
    # Lovdata's own ``changesToDocuments`` list, recorded beside ``base_ids`` so
    # the two can be compared. Storing it here binds nothing — no code reads this
    # tuple back — but the list itself is NOT inert upstream: the grafter's
    # sole-declared-ref ``default_base_id`` (``grafter.py`` ~:1500, outranking
    # every extracted signal at ~:1557) is the only ``base_id`` 393 of the 2466
    # entries have. Measured by counterfactual: strip every ``changesToDocuments``
    # carrier and rebuild, and those 393 lose ``base_ids`` entirely.
    declared_target_ids: tuple[str, ...] = ()
    # The shape of the ``dateInForce`` field this entry's date was read off
    # (:class:`NOCommencementShape`), carried as its ``StrEnum`` value so the
    # staged-commencement population is queryable off a serialized index without
    # re-parsing ``raw_date_in_force``. Orthogonal to ``effective_status``: the
    # 8 staged acts an instrument re-dates keep ``staged_delegated`` here while
    # their status moves to ``instrument_authorized``.
    commencement_shape: str = NOCommencementShape.PLAIN
    # W-84. Empty for every entry but the three superseded/rectified pairs. When
    # set it is the ``no/forskrift/<id>`` of the *beriktiget* re-announcement whose
    # bytes this entry's ops were lowered from — the entry's ``member_name`` points
    # at that document, while ``source_id``, ``title`` and every date stay the ACT's.
    # Both ids on one row is the point: a reader can see that the text replayed for
    # ``no/lovtid/2021-06-18-129`` was read from ``no/forskrift/2021-06-25-2137``.
    beriktiget_announcement_id: str = ""
    # W-39. Per-BINDING commencement dates: ``(base law id, ISO date)`` pairs
    # granted by the part-scoped route, sorted by law id. Orthogonal to
    # ``effective_status``/``effective_date``, which stay the act's WHOLE-act
    # verdict: a staged act whose part I commenced in 2011 and part III in 2023
    # has no single act-level date, and inventing one would be a claim the
    # evidence does not make. Consumers resolve a base law's date as "this map
    # first, the act-level date otherwise".
    part_scoped_effective_dates: tuple[tuple[str, str], ...] = ()

    def effective_date_for_base(self, base_id: str) -> tuple[str | None, str]:
        """``(date, status)`` for this entry AS IT APPLIES TO ``base_id``."""
        for law_id, date in self.part_scoped_effective_dates:
            if law_id == base_id:
                return date, NOEffectiveStatus.PART_INSTRUMENT_AUTHORIZED
        return self.effective_date, self.effective_status


@dataclass
class NOAmendmentIndex:
    data_dir: str
    source_kind: str = "dir"
    generated_at_utc: str = ""
    archive_names: list[str] = field(default_factory=list)
    archive_metadata: dict[str, dict[str, int | str]] = field(default_factory=dict)
    entries: list[NOAmendmentIndexEntry] = field(default_factory=list)
    commencement_instruments: list[NOCommencementInstrumentCandidate] = field(default_factory=list)
    commencement_instrument_coverage: NOCommencementInstrumentCoverage = field(
        default_factory=NOCommencementInstrumentCoverage
    )
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_dir": self.data_dir,
            "source_kind": self.source_kind,
            "generated_at_utc": self.generated_at_utc,
            "archive_names": list(self.archive_names),
            "archive_metadata": self.archive_metadata,
            "entries": [asdict(entry) for entry in self.entries],
            "commencement_instruments": [
                instrument.to_dict() for instrument in self.commencement_instruments
            ],
            "commencement_instrument_coverage": self.commencement_instrument_coverage.to_dict(),
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NOAmendmentIndex":
        raw_entries = data.get("entries", [])
        entries = [
            NOAmendmentIndexEntry(
                source_id=entry["source_id"],
                archive=entry["archive"],
                member_name=entry["member_name"],
                effective_status=entry["effective_status"],
                effective_date=entry.get("effective_date"),
                raw_date_in_force=entry.get("raw_date_in_force", ""),
                title=entry.get("title", ""),
                base_ids=tuple(entry.get("base_ids", [])),
                n_ops=int(entry.get("n_ops", 0)),
                declared_target_ids=tuple(entry.get("declared_target_ids", [])),
                commencement_shape=coerce_no_commencement_shape(
                    entry.get("commencement_shape") or NOCommencementShape.PLAIN
                ),
                beriktiget_announcement_id=str(entry.get("beriktiget_announcement_id", "") or ""),
                part_scoped_effective_dates=tuple(
                    (str(pair[0]), str(pair[1]))
                    for pair in entry.get("part_scoped_effective_dates", []) or []
                    if isinstance(pair, (list, tuple)) and len(pair) == 2
                ),
            )
            for entry in raw_entries
            if isinstance(entry, dict)
        ]
        archive_names = [str(item) for item in data.get("archive_names", [])]
        archive_metadata = data.get("archive_metadata", {})
        raw_diagnostics = data.get("diagnostics", [])
        raw_commencement_instruments = data.get("commencement_instruments", [])
        return cls(
            data_dir=str(data.get("data_dir", "")),
            source_kind=str(data.get("source_kind", "dir")),
            generated_at_utc=str(data.get("generated_at_utc", "")),
            archive_names=archive_names,
            archive_metadata={
                str(key): value for key, value in archive_metadata.items()
                if isinstance(key, str) and isinstance(value, dict)
            },
            entries=entries,
            commencement_instruments=[
                NOCommencementInstrumentCandidate.from_dict(item)
                for item in raw_commencement_instruments
                if isinstance(item, dict)
            ],
            commencement_instrument_coverage=NOCommencementInstrumentCoverage.from_dict(
                data.get("commencement_instrument_coverage", {})
            ),
            diagnostics=[dict(item) for item in raw_diagnostics if isinstance(item, dict)],
        )

    def entries_for_base(self, base_id: str) -> list[NOAmendmentIndexEntry]:
        return [entry for entry in self.entries if base_id in entry.base_ids]

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.effective_status] = counts.get(entry.effective_status, 0) + 1
        return counts

    def staleness_report(self, data_dir: Optional[Path] = None) -> dict[str, object]:
        data_dir = resolve_no_source_path(data_dir or Path(self.data_dir))
        if self.source_kind == "farchive":
            if not data_dir.exists():
                return {
                    "index_stale": True,
                    "missing_archives": [str(data_dir)],
                    "stale_archives": [],
                }
            stat = data_dir.stat()
            current = {
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
            recorded = self.archive_metadata.get("__farchive__", {})
            expected = {
                "size": int(recorded.get("size", -1)),
                "mtime_ns": int(recorded.get("mtime_ns", -1)),
            }
            return {
                "index_stale": current != expected,
                "missing_archives": [],
                "stale_archives": [] if current == expected else [{"archive": str(data_dir), "recorded": expected, "current": current}],
            }
        stale_archives = []
        missing_archives = []
        for archive_name in self.archive_names:
            path = data_dir / archive_name
            meta = self.archive_metadata.get(archive_name, {})
            if not path.exists():
                missing_archives.append(archive_name)
                continue
            stat = path.stat()
            current = {
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
            recorded = {
                "size": int(meta.get("size", -1)),
                "mtime_ns": int(meta.get("mtime_ns", -1)),
            }
            if current != recorded:
                stale_archives.append(
                    {
                        "archive": archive_name,
                        "recorded": recorded,
                        "current": current,
                    }
                )
        return {
            "index_stale": bool(stale_archives or missing_archives),
            "missing_archives": missing_archives,
            "stale_archives": stale_archives,
        }


@dataclass(frozen=True)
class NOBeriktigetPair:
    """One superseded announcement matched to its rectified re-announcement."""

    reannouncement: NOBeriktigetReannouncement
    artifact: NOLocatedArtifact


def _no_beriktiget_reannouncements(data_dir: Path) -> dict[str, NOBeriktigetPair]:
    """Index the forskrift lane's rectified re-announcements by the act they announce.

    A pre-pass rather than a second consumer of the commencement loop below,
    because its answer is needed BEFORE the amendment loop lowers anything: a
    superseded announcement's ops are never minted and then withdrawn, they are
    never minted. Cost is one pass over the forskrift lane (~1.5s of a ~45s
    build); the reader's own byte prefilter is what keeps it that cheap, since
    35,952 of the 35,955 artifacts are rejected without being parsed.

    Keyed by the ANNOUNCED act. A second re-announcement of the same act would
    make the key ambiguous, so it is dropped from the map instead of overwriting —
    the caller then sees no match and refuses the pairing, which is the safe
    direction. Measured: no act is re-announced twice.
    """
    found: dict[str, list[NOBeriktigetPair]] = {}
    for artifact in iter_no_forskrift_artifacts(data_dir):
        reannouncement = no_beriktiget_reannouncement(artifact.payload)
        if reannouncement is None:
            continue
        found.setdefault(reannouncement.announced_act_id, []).append(
            NOBeriktigetPair(reannouncement=reannouncement, artifact=artifact)
        )
    return {
        act_id: pairs[0]
        for act_id, pairs in found.items()
        if len(pairs) == 1
    }


def _no_beriktiget_paired_diagnostic(
    *,
    artifact: NOLocatedArtifact,
    pair: NOBeriktigetPair,
    note_dates: tuple[str, ...],
    withdrawn_ops: int,
    admitted_ops: int,
    base_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Receipt the whole-instrument swap of a superseded announcement.

    Non-blocking and dispositioned APPLY: this is not a refusal, it is the
    correction landing. What it has to preserve is the pair of numbers a reader
    would otherwise have to reconstruct from two archives — how many ops the
    superseded announcement used to mint, and how many the rectified one mints in
    their place. The two are NOT ordered: rectified versions in this corpus both
    add ops and remove them.
    """
    return diagnostic_detail(
        rule_id=NO_BERIKTIGET_ANNOUNCEMENT_PAIRED,
        family="source_pathology",
        phase="acquisition",
        reason=(
            "Norway amendment index replaced a superseded (utgått) gazette announcement's "
            "operations with those of its rectified (beriktiget) re-announcement."
        ),
        blocking=False,
        quirks_disposition=QuirksDisposition.APPLY,
        source_id=artifact.logical_id,
        locator=artifact.locator,
        archive=artifact.source_name,
        member_name=artifact.member_name,
        superseded_note_dates=list(note_dates),
        announcement_id=pair.reannouncement.announcement_id,
        announcement_locator=pair.artifact.locator,
        announcement_date=pair.reannouncement.announcement_date,
        withdrawn_op_count=withdrawn_ops,
        admitted_op_count=admitted_ops,
        base_ids=list(base_ids),
    )


def _no_beriktiget_unpaired_diagnostic(
    *,
    source_id: str,
    locator: str,
    reason: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Receipt a supersession half that found no counterpart.

    THE RULE THIS RECORDS, stated because the corpus does not yet exercise it: a
    superseded announcement with no matched re-announcement is NOT suppressed. Its
    ops stand. ``utgått`` says the announcement was superseded; it does not say by
    what, and it does not say the act was unmade. Dropping the ops on the strength
    of the mark alone would delete enacted law on no evidence of what replaced it —
    the same over-application in the opposite direction from the one W-84 fixes.
    Symmetrically, a rectified re-announcement whose act carries no ``utgått`` mark
    is NOT admitted: one signal is not the pair, and the forskrift lane stays shut.
    Either way the machinery is knowingly leaving a flagged document unread, which
    is exactly the class of silence W-83 spent an audit discovering, so it is
    blocking: it should surface in the blockers report, not sit in a census.
    """
    return diagnostic_detail(
        rule_id=NO_BERIKTIGET_ANNOUNCEMENT_UNPAIRED,
        family="source_pathology",
        phase="acquisition",
        reason=(
            "Norway amendment index found one half of a superseded/rectified announcement "
            "pair without its counterpart; neither suppression nor admission applied."
        ),
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.RECORD,
        source_id=source_id,
        locator=locator,
        unpaired_reason=reason,
        **detail,
    )


def build_no_amendment_index(data_dir: Optional[Path] = None) -> NOAmendmentIndex:
    data_dir = resolve_no_source_path(data_dir)
    source_meta = no_source_metadata(data_dir)
    archive_names = [str(item) for item in source_meta.get("archive_names", [])]
    archive_metadata: dict[str, dict[str, int | str]] = {}
    raw_archive_metadata = source_meta.get("archive_metadata", {})
    if isinstance(raw_archive_metadata, dict):
        archive_metadata = cast(dict[str, dict[str, int | str]], raw_archive_metadata)
    if source_meta.get("source_kind") == "farchive" and source_meta.get("exists"):
        archive_metadata = {
            "__farchive__": {
                "size": int(source_meta.get("size", 0)),
                "mtime_ns": int(source_meta.get("mtime_ns", 0)),
            }
        }
    index = NOAmendmentIndex(
        data_dir=str(data_dir),
        source_kind=str(source_meta.get("source_kind", "dir")),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        archive_names=archive_names,
        archive_metadata=archive_metadata,
    )

    act_part_evidence: dict[str, NOCommencementActPartEvidence] = {}
    # W-84. Read before a single amendment is lowered: a superseded announcement's
    # ops must never enter the stream, not enter it and be taken back out.
    beriktiget_by_act = _no_beriktiget_reannouncements(data_dir)
    beriktiget_paired: set[str] = set()

    if index.source_kind == "dir":
        for artifact in iter_no_unmapped_lovtidend_xml_members(data_dir):
            index.diagnostics.append(
                _no_index_unmapped_member_diagnostic(
                    artifact=artifact,
                )
            )

    for artifact in _deduplicated_no_amendment_artifacts(
        tuple(iter_no_amendment_artifacts(data_dir)),
        diagnostics=index.diagnostics,
    ):
        source_id = artifact.logical_id
        if lovdata_amendment_filename_to_id(artifact.member_name) is None and not artifact.locator.startswith("no://lovtid/"):
            index.diagnostics.append(
                _no_index_skipped_artifact_diagnostic(
                    rule_id="no_amendment_index_unrecognized_amendment_locator",
                    artifact=artifact,
                    reason="Norway amendment index skipped artifact whose member name and locator did not identify an amendment source lane",
                    phase="acquisition",
                )
            )
            continue
        declared = declared_change_targets_from_amendment(artifact.payload)
        parser_adjudications: list[CompileAdjudication] = []
        # ── W-84: the superseded/rectified swap ──────────────────────────────
        #
        # Two of Lovdata's own marks have to agree before anything moves: the act
        # carries an ``utgått`` gazettenote, and a forskrift-lane document titled
        # "Kunngjøring av beriktiget versjon av lov …" names THIS act. The note's
        # date is then required to equal the re-announcement's own publication
        # date — a free cross-check (the date is already in the forskrift id), and
        # the one that makes a coincidental title match unable to bind an act.
        #
        # The swap is WHOLE-INSTRUMENT: the rectified document re-announces the act
        # in full, so its ops replace the superseded announcement's wholesale rather
        # than merging with them. Identity and dates stay the ACT's throughout —
        # ``source_id``, ``title``, ``declared``, ``effective`` are all still read
        # off the act — because a *kunngjøring av beriktiget versjon* is a
        # republication, not a new law. Only the operative TEXT comes from the
        # rectified bytes. See the dates discussion in the paired receipt.
        superseded_note_dates = no_superseded_announcement_dates(artifact.payload)
        pair = beriktiget_by_act.get(source_id) if superseded_note_dates else None
        if pair is not None and pair.reannouncement.announcement_date not in superseded_note_dates:
            index.diagnostics.append(
                _no_beriktiget_unpaired_diagnostic(
                    source_id=source_id,
                    locator=artifact.locator,
                    reason="announcement_date_disagrees_with_note",
                    detail={
                        "superseded_note_dates": list(superseded_note_dates),
                        "announcement_id": pair.reannouncement.announcement_id,
                        "announcement_date": pair.reannouncement.announcement_date,
                    },
                )
            )
            pair = None
        elif superseded_note_dates and pair is None:
            index.diagnostics.append(
                _no_beriktiget_unpaired_diagnostic(
                    source_id=source_id,
                    locator=artifact.locator,
                    reason="rectified_reannouncement_absent",
                    detail={"superseded_note_dates": list(superseded_note_dates)},
                )
            )
        lowered_payload = artifact.payload if pair is None else pair.artifact.payload
        grouped = iter_no_document_change_ops(
            lowered_payload,
            source_id,
            adjudications_out=parser_adjudications,
        )
        if pair is not None:
            # Conservation, checked against Lovdata's own declaration on the ACT: a
            # rectified re-announcement of act X may only bind laws X itself
            # declares it changes. Nothing in the corpus violates this (all three
            # pairs bind exactly the act's declared set), and a violation would
            # mean the title match had reached the wrong act — so it refuses the
            # whole swap rather than landing a partly-trusted op stream.
            swapped_base_ids = tuple(sorted({base_id for base_id, _ops in grouped}))
            undeclared = [
                base_id for base_id in swapped_base_ids if base_id not in declared.law_ids
            ]
            if undeclared or not swapped_base_ids:
                index.diagnostics.append(
                    _no_beriktiget_unpaired_diagnostic(
                        source_id=source_id,
                        locator=artifact.locator,
                        reason="rectified_bases_not_declared_by_act",
                        detail={
                            "superseded_note_dates": list(superseded_note_dates),
                            "announcement_id": pair.reannouncement.announcement_id,
                            "rectified_base_ids": list(swapped_base_ids),
                            "declared_target_ids": list(declared.law_ids),
                        },
                    )
                )
                pair = None
                parser_adjudications = []
                grouped = iter_no_document_change_ops(
                    artifact.payload,
                    source_id,
                    adjudications_out=parser_adjudications,
                )
        for adjudication in parser_adjudications:
            index.diagnostics.append(
                _no_index_parser_adjudication_diagnostic(
                    adjudication=adjudication,
                    # The DOCUMENT the refused prose actually lives in. For a
                    # swapped entry that is the rectified re-announcement, not the
                    # act: a reader chasing the receipt back to bytes must land on
                    # the bytes the parser read.
                    artifact=artifact if pair is None else pair.artifact,
                )
            )
        base_ids = tuple(sorted({base_id for base_id, _ops in grouped}))
        declared_target_gap = _no_index_declared_target_unbound_diagnostic(
            artifact=artifact,
            declared=declared,
            base_ids=base_ids,
        )
        if declared_target_gap is not None:
            index.diagnostics.append(declared_target_gap)
        if not grouped:
            index.diagnostics.append(
                _no_index_skipped_artifact_diagnostic(
                    rule_id="no_amendment_index_no_change_ops",
                    artifact=artifact,
                    reason="Norway amendment artifact did not yield document-change operations",
                    phase="extraction",
                )
            )
            continue
        effective = effective_date_from_amendment(
            artifact.payload,
            source_date=source_id.removeprefix("no/lovtid/"),
        )
        if effective.commencement_shape is NOCommencementShape.STAGED_DELEGATED:
            index.diagnostics.append(
                _no_index_staged_commencement_diagnostic(
                    artifact=artifact,
                    source_id=source_id,
                    effective=effective,
                )
            )
        # W-39. The part-scoped commencement gate's scope proof, read here
        # because this is where the artifact's bytes and its lowered op stream
        # are both in hand; the gate parses no XML of its own. Only acts with
        # roman-numbered parts contribute — for everything else the map is empty
        # and the part route can never fire.
        part_law_ids = no_part_law_ids(artifact.payload)
        if part_law_ids:
            act_part_evidence[source_id] = NOCommencementActPartEvidence(
                part_law_ids=part_law_ids,
                bound_law_ids=base_ids,
                law_section_labels={
                    base_id: frozenset(
                        label
                        for op in ops
                        for kind, label in op.target.path[:1]
                        if kind == "section"
                    )
                    for base_id, ops in grouped
                },
            )
        # W-84. A swapped entry points ``archive``/``member_name`` at the rectified
        # document, which is what makes replay load the corrected bytes: replay
        # resolves an entry's source through those two fields, not through
        # ``source_id``. Everything else on the row stays the act's.
        if pair is not None:
            beriktiget_paired.add(pair.reannouncement.announcement_id)
            withdrawn = iter_no_document_change_ops(artifact.payload, source_id)
            index.diagnostics.append(
                _no_beriktiget_paired_diagnostic(
                    artifact=artifact,
                    pair=pair,
                    note_dates=superseded_note_dates,
                    withdrawn_ops=sum(len(ops) for _base_id, ops in withdrawn),
                    admitted_ops=sum(len(ops) for _base_id, ops in grouped),
                    base_ids=base_ids,
                )
            )
        index.entries.append(
            NOAmendmentIndexEntry(
                source_id=source_id,
                archive=artifact.source_name if pair is None else pair.artifact.source_name,
                member_name=artifact.member_name if pair is None else pair.artifact.member_name,
                effective_status=effective.effective_status,
                effective_date=effective.effective_date,
                raw_date_in_force=effective.raw_text,
                title=parse_header_value(artifact.payload, "title") or parse_header_value(artifact.payload, "titleShort"),
                base_ids=base_ids,
                n_ops=sum(len(ops) for _base_id, ops in grouped),
                declared_target_ids=declared.law_ids,
                commencement_shape=effective.commencement_shape,
                beriktiget_announcement_id=(
                    "" if pair is None else pair.reannouncement.announcement_id
                ),
            )
        )

    # The gate's other half, receipted: a rectified re-announcement whose act
    # carries no ``utgått`` mark (or which the pairing refused) is NOT admitted,
    # and the forskrift lane stays shut behind it.
    for act_id, unpaired in sorted(beriktiget_by_act.items()):
        if unpaired.reannouncement.announcement_id in beriktiget_paired:
            continue
        index.diagnostics.append(
            _no_beriktiget_unpaired_diagnostic(
                source_id=unpaired.reannouncement.announcement_id,
                locator=unpaired.artifact.locator,
                reason="superseded_announcement_absent",
                detail={
                    "announced_act_id": act_id,
                    "announcement_date": unpaired.reannouncement.announcement_date,
                },
            )
        )

    commencement_total = 0
    commencement_candidates = 0
    commencement_benign = 0
    commencement_blocked = 0
    parsed_instruments: list[
        tuple[NOCommencementParseStatus, NOCommencementInstrumentCandidate]
    ] = []
    for artifact in _deduplicated_no_amendment_artifacts(
        tuple(iter_no_forskrift_artifacts(data_dir)),
        diagnostics=index.diagnostics,
    ):
        commencement_total += 1
        result = parse_no_commencement_instrument(
            artifact.payload,
            source_id=artifact.logical_id,
            locator=artifact.locator,
            archive=artifact.source_name,
            member_name=artifact.member_name,
        )
        if result.parse_status is NOCommencementParseStatus.BENIGN_NOT_COMMENCEMENT:
            commencement_benign += 1
            continue
        if result.parse_status is NOCommencementParseStatus.BLOCKED_UNRESOLVED:
            commencement_blocked += 1
        else:
            commencement_candidates += 1
        if result.candidate is not None:
            parsed_instruments.append((result.parse_status, result.candidate))
        for residual in result.residuals:
            index.diagnostics.append(
                {
                    **residual.to_dict(),
                    "source_id": artifact.logical_id,
                    "locator": artifact.locator,
                    "archive": artifact.source_name,
                    "member_name": artifact.member_name,
                    "quirks_disposition": QuirksDisposition.RECORD,
                }
            )

    index.commencement_instrument_coverage = NOCommencementInstrumentCoverage(
        total_instruments=commencement_total,
        candidates=commencement_candidates,
        benign_non_commencement=commencement_benign,
        blocked_unresolved=commencement_blocked,
    )
    if not index.commencement_instrument_coverage.is_partition():
        raise AssertionError("Norway commencement-instrument coverage is not a total partition")

    index.entries.sort(key=lambda entry: (entry.source_id, entry.archive, entry.member_name))
    parsed_instruments.sort(
        key=lambda item: (item[1].source_id, item[1].archive, item[1].member_name)
    )
    _authorize_no_commencement_instruments_into_index(
        index, parsed_instruments, act_part_evidence
    )
    return index


def _authorize_no_commencement_instruments_into_index(
    index: NOAmendmentIndex,
    parsed_instruments: list[
        tuple[NOCommencementParseStatus, NOCommencementInstrumentCandidate]
    ],
    act_part_evidence: dict[str, NOCommencementActPartEvidence] | None = None,
) -> None:
    """Re-date acts whose own date is weak from their whole-act commencement instruments.

    Runs inside the index build so inventory, scan, replay, and the commencement
    reports all read one authorized view; no consumer authorizes for itself. The
    manual override sidecar — applied after the build — still outranks an
    instrument authorization.

    Two populations are offered, and offering is all that changed here: the
    gate's own conjuncts (candidate parse, whole-act scope, exactly one
    effective date, cited act present in the offered set) are untouched.

    1. Acts with an unresolved ``effective_status``. They have no date at all,
       so any authorized date is strictly more than they had.
    2. Acts labelled :attr:`NOCommencementShape.STAGED_DELEGATED`. These DO
       carry a date, but it is the weakest kind the index issues: ``min(dates)``
       over a metadata field that also says the executive fixes the real
       commencement. An official Norsk Lovtidend whole-act instrument outranks
       that guess, so the instrument's date wins where one exists. Measured
       corpus-wide this re-dates 8 of the 167 staged acts, every one of them
       EARLIER than the metadata guess (the metadata named a planned date the
       instrument then superseded); the other 159 keep ``min(dates)`` and replay
       exactly as before.

    A ``plain`` dated / ``immediate`` / ``override`` entry is still never
    offered and so can never be re-dated here.

    W-39 changes what a refused pair may still yield, not what is offered: the
    same offered set now also feeds the part-scoped route, whose grant lands in
    ``part_scoped_effective_dates`` rather than in ``effective_status`` /
    ``effective_date``. That asymmetry is the point — the act's whole-act
    verdict is untouched (the corpus's status histogram does not move), while
    the ONE binding the instrument proves gets a date.

    W-47 changes neither the offering nor the landing place: its multi-part
    route grants the same kind of per-binding date into the same field, for acts
    whose Endrer header spans several parts under a whole-act operative text. So
    the act-level histogram does not move for it either — an act with parts
    commencing on one date still has no single act-level date to claim.

    W-49's named-part-list route changes neither either, for the third time and
    the same reason: one more per-binding date into the same field, from an
    instrument that names the parts it commences instead of commencing the act
    whole. No act-level status moves, and no ``base_ids`` are ever written.

    W-53's widened whole-act route is the first since W-39 to move the act-level
    histogram: its grant lands in ``authorized_effective_dates`` beside the
    shipped route's, so the acts it dates become ``instrument_authorized`` exactly
    as they would have under a matched ``_WHOLE_ACT_RE``. What it still does not
    touch is the OFFERING (unchanged, above) and ``base_ids`` — this lane writes
    dates and never bindings, which is why widening it cannot decertify a law: a
    law's coverage partition is a function of its bindings, and resolution is
    monotone in the dates.
    """
    authorization = authorize_no_commencement_instruments(
        parsed_instruments,
        offered_act_ids={
            entry.source_id
            for entry in index.entries
            if entry.effective_status in NO_UNRESOLVED_EFFECTIVE_STATUSES
            or entry.commencement_shape == NOCommencementShape.STAGED_DELEGATED
        },
        act_part_evidence=act_part_evidence,
    )
    index.commencement_instruments = list(authorization.instruments)
    effective_dates = authorization.authorized_effective_dates()
    part_dates = authorization.part_authorized_effective_dates()
    index.entries = [
        dc_replace(
            entry,
            effective_status=NOEffectiveStatus.INSTRUMENT_AUTHORIZED,
            effective_date=effective_dates[entry.source_id],
        )
        if entry.source_id in effective_dates
        else dc_replace(
            entry,
            part_scoped_effective_dates=tuple(
                sorted(part_dates[entry.source_id].items())
            ),
        )
        if entry.source_id in part_dates
        else entry
        for entry in index.entries
    ]
    for receipt in authorization.authorizations:
        index.diagnostics.append(receipt.to_diagnostic_detail())
    for receipt in authorization.part_authorizations:
        index.diagnostics.append(receipt.to_diagnostic_detail())
    for multi_part_receipt in authorization.multi_part_authorizations:
        index.diagnostics.append(multi_part_receipt.to_diagnostic_detail())
    for named_part_receipt in authorization.named_part_list_authorizations:
        index.diagnostics.append(named_part_receipt.to_diagnostic_detail())
    for widened_receipt in authorization.widened_whole_act_authorizations:
        index.diagnostics.append(widened_receipt.to_diagnostic_detail())
    for widened_conflict in authorization.widened_whole_act_conflicts:
        index.diagnostics.append(widened_conflict.to_diagnostic_detail())
    for refusal in authorization.refusals:
        index.diagnostics.append(refusal.to_diagnostic_detail())
    for conflict in authorization.conflicts:
        index.diagnostics.append(conflict.to_diagnostic_detail())
    for part_conflict in authorization.part_conflicts:
        index.diagnostics.append(part_conflict.to_diagnostic_detail())


def _payload_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _deduplicated_no_amendment_artifacts(
    artifacts: tuple[NOLocatedArtifact, ...],
    *,
    diagnostics: list[dict[str, Any]],
) -> tuple[NOLocatedArtifact, ...]:
    grouped: dict[tuple[str, str], list[NOLocatedArtifact]] = {}
    for artifact in artifacts:
        if artifact.logical_id and artifact.locator:
            grouped.setdefault((artifact.logical_id, artifact.locator), []).append(artifact)

    duplicate_keys = {key for key, items in grouped.items() if len(items) > 1}
    selected: dict[tuple[str, str], NOLocatedArtifact] = {}
    blocked: set[tuple[str, str]] = set()
    for key in sorted(duplicate_keys):
        items = sorted(grouped[key], key=lambda item: (item.source_name, item.member_name))
        digests = {_payload_digest(item.payload) for item in items}
        identical_payloads = len(digests) == 1
        diagnostics.append(
            _no_index_duplicate_logical_locator_diagnostic(
                logical_id=key[0],
                locator=key[1],
                artifacts=items,
                identical_payloads=identical_payloads,
            )
        )
        if identical_payloads:
            selected[key] = items[0]
        else:
            blocked.add(key)

    deduplicated: list[NOLocatedArtifact] = []
    emitted_selected: set[tuple[str, str]] = set()
    for artifact in artifacts:
        key = (artifact.logical_id, artifact.locator)
        if key in blocked:
            continue
        if key in selected:
            if key in emitted_selected:
                continue
            deduplicated.append(selected[key])
            emitted_selected.add(key)
            continue
        deduplicated.append(artifact)
    return tuple(deduplicated)


def _no_index_duplicate_logical_locator_diagnostic(
    *,
    logical_id: str,
    locator: str,
    artifacts: list[NOLocatedArtifact],
    identical_payloads: bool,
) -> dict[str, Any]:
    selected = min(artifacts, key=lambda item: (item.source_name, item.member_name)) if identical_payloads else None
    selected_locator = _no_artifact_source_lane_locator(selected)
    return diagnostic_detail(
        rule_id=NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR,
        family="source_pathology",
        phase="acquisition",
        reason=(
            "Norway acquisition found duplicate byte-identical artifacts for the same logical source locator; "
            "quirks mode selected a deterministic witness."
            if identical_payloads
            else "Norway acquisition found conflicting artifacts for the same logical source locator; source is ambiguous."
        ),
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.SELECT_FIRST_IDENTICAL if identical_payloads else QuirksDisposition.BLOCK,
        source_id=logical_id,
        locator=locator,
        duplicate_count=len(artifacts),
        identical_payloads=identical_payloads,
        payload_digests=sorted({_payload_digest(artifact.payload) for artifact in artifacts}),
        source_lane_selection=_no_duplicate_logical_locator_source_lane_evidence(
            logical_id=logical_id,
            locator=locator,
            artifacts=artifacts,
            identical_payloads=identical_payloads,
            selected=selected,
        ),
        candidates=[
            {
                "archive": artifact.source_name,
                "member_name": artifact.member_name,
                "payload_digest": _payload_digest(artifact.payload),
            }
            for artifact in artifacts
        ],
        selected_archive=selected.source_name if selected is not None else "",
        selected_member_name=selected.member_name if selected is not None else "",
        selected_source_locator=selected_locator,
    )


def _no_artifact_source_lane_locator(artifact: NOLocatedArtifact | None) -> str:
    if artifact is None:
        return ""
    return f"{artifact.source_name}:{artifact.member_name}"


def _no_duplicate_logical_locator_source_lane_evidence(
    *,
    logical_id: str,
    locator: str,
    artifacts: list[NOLocatedArtifact],
    identical_payloads: bool,
    selected: NOLocatedArtifact | None,
) -> dict[str, Any]:
    return SourceLaneSelectionEvidence(
        rule_id=NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR,
        phase="acquisition",
        reason=(
            "Norway amendment indexing selected one byte-identical duplicate "
            "source witness deterministically."
            if identical_payloads
            else "Norway amendment indexing found conflicting duplicate source witnesses and selected no lane."
        ),
        selected_lane=(
            "norway_lovtidend_archive_member"
            if selected is not None
            else "no_source_lane_selected_conflicting_duplicates"
        ),
        selected_locator=_no_artifact_source_lane_locator(selected),
        attempts=tuple(
            SourceLaneAttempt(
                lane="norway_lovtidend_archive_member",
                locator=_no_artifact_source_lane_locator(artifact),
                lane_attempt_status=(
                    "selected_identical_duplicate"
                    if selected is artifact
                    else (
                        "duplicate_identical_not_selected"
                        if identical_payloads
                        else "blocked_conflicting_duplicate"
                    )
                ),
                detail={
                    "logical_id": logical_id,
                    "logical_locator": locator,
                    "payload_digest": _payload_digest(artifact.payload),
                },
            )
            for artifact in artifacts
        ),
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.SELECT_FIRST_IDENTICAL if identical_payloads else QuirksDisposition.BLOCK,
        detail={
            "logical_id": logical_id,
            "logical_locator": locator,
            "identical_payloads": identical_payloads,
        },
    ).to_diagnostic_detail()


def _no_index_unmapped_member_diagnostic(
    *,
    artifact: NOLocatedArtifact,
) -> dict[str, Any]:
    return diagnostic_detail(
        rule_id="no_amendment_index_unmapped_lovtidend_xml_member",
        family="source_pathology",
        phase="acquisition",
        reason="Norway Lovtidend XML member filename could not be mapped to a law or amendment source id",
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.RECORD,
        source_id="",
        locator="",
        archive=artifact.source_name,
        member_name=artifact.member_name,
    )


def _no_index_skipped_artifact_diagnostic(
    *,
    rule_id: str,
    artifact: NOLocatedArtifact,
    reason: str,
    phase: str,
) -> dict[str, Any]:
    return diagnostic_detail(
        rule_id=rule_id,
        family="source_pathology",
        phase=phase,
        reason=reason,
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.RECORD,
        source_id=artifact.logical_id,
        locator=artifact.locator,
        archive=artifact.source_name,
        member_name=artifact.member_name,
    )


def _no_index_staged_commencement_diagnostic(
    *,
    artifact: NOLocatedArtifact,
    source_id: str,
    effective: NOEffectiveDate,
) -> dict[str, Any]:
    """Receipt one act whose ``dateInForce`` staged its commencement.

    Emitted once per act whose field carries both ISO dates and a
    delegated-commencement tail, so the population is total and queryable rather
    than an unremarked DATED. Non-blocking on purpose: the act IS in force at
    ``min(dates)`` — Lovdata's own consolidation says so — and the recorded fact
    is the narrower one that ``date_count`` dates collapsed to one and a
    delegated tail was dropped, because the engine represents commencement at
    act rather than provision granularity (``NORWAY_LAWVM_STATUS.md`` 2.3).
    Naming the raw field and the collapsed date is what lets a reader recover
    what the collapse discarded without re-reading the source.
    """
    return diagnostic_detail(
        rule_id=NO_AMENDMENT_INDEX_STAGED_COMMENCEMENT_COLLAPSED,
        family="temporal_recovery",
        phase="temporal",
        reason=(
            "Norway amendment act states a commencement date AND delegates the rest of its "
            "commencement to the executive; the act is dated at the earliest stated date and "
            "the staged tail is recorded, not represented."
        ),
        blocking=False,
        strict_disposition="record",
        quirks_disposition=QuirksDisposition.RECORD,
        source_id=source_id,
        locator=artifact.locator,
        archive=artifact.source_name,
        member_name=artifact.member_name,
        commencement_shape=str(effective.commencement_shape),
        raw_date_in_force=effective.raw_text,
        effective_date=effective.effective_date,
        date_count=effective.date_count,
    )


def _no_index_declared_target_unbound_diagnostic(
    *,
    artifact: NOLocatedArtifact,
    declared: NODeclaredChangeTargets,
    base_ids: tuple[str, ...],
) -> Optional[dict[str, Any]]:
    """Adjudicate the targets Lovdata declared that the extracted ops never bound.

    Measurement only: ``base_ids`` stays whatever extraction produced, and a
    declared id that is absent from it is recorded here rather than bound.
    ``unnumbered_unbound_target_ids`` labels the ``no/lov/<date>`` declarations
    that carry no trailing act number. They are labelled inside the gap, not
    held apart from it: they stay in ``unbound_target_ids`` and in
    ``declared_target_count``, which is what makes the emitted totals reconcile
    with ``scripts/probes/no_declared_target_coverage.py`` (4,088 unbound across
    1,245 acts). The label is not an unreachability verdict — 65 of the 92
    unnumbered ids emitted corpus-wide do name a corpus law, filed under a
    ``<date>-0`` id — so these are real gaps, reported as such and merely
    distinguished by the form in which Lovdata declared them.
    """
    unbound = tuple(sorted(set(declared.law_ids) - set(base_ids)))
    if not unbound:
        return None
    return diagnostic_detail(
        rule_id="no_amendment_index_declared_target_unbound",
        family="source_pathology",
        phase="acquisition",
        reason="Norway amendment act declared amendment targets that no extracted operation bound",
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.RECORD,
        source_id=artifact.logical_id,
        locator=artifact.locator,
        archive=artifact.source_name,
        member_name=artifact.member_name,
        declared_target_count=len(declared.law_ids),
        bound_base_id_count=len(base_ids),
        unbound_target_ids=list(unbound),
        unnumbered_unbound_target_ids=sorted(set(declared.unnumbered_law_ids) & set(unbound)),
    )


def _no_index_parser_adjudication_diagnostic(
    *,
    adjudication: CompileAdjudication,
    artifact: NOLocatedArtifact,
) -> dict[str, Any]:
    detail = dict(adjudication.detail)
    rule_id = str(detail.get("rule_id") or adjudication.kind)
    phase = str(detail.get("phase") or "parse")
    family = str(detail.get("family") or "source_pathology")
    diagnostic = diagnostic_detail(
        rule_id=rule_id,
        family=family,
        phase=phase,
        reason=adjudication.message,
        blocking=bool(detail.get("blocking", True)),
        strict_disposition=str(detail.get("strict_disposition") or "block"),
        quirks_disposition=coerce_quirks_disposition(detail.get("quirks_disposition") or QuirksDisposition.RECORD),
        kind=adjudication.kind,
        source_id=adjudication.source_statute,
        op_id=adjudication.op_id,
        locator=artifact.locator,
        archive=artifact.source_name,
        member_name=artifact.member_name,
    )
    diagnostic["detail"] = detail
    return diagnostic


def load_no_amendment_index(path: Path) -> NOAmendmentIndex:
    return NOAmendmentIndex.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_no_amendment_index(index: NOAmendmentIndex, path: Path) -> None:
    path.write_text(json.dumps(index.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
