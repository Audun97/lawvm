"""Inventory helpers for Norway public Lovdata archives."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, cast

from lxml import etree

from lawvm.core.diagnostic_records import diagnostic_detail
from lawvm.core.regex_safety import compile_classifier_regex
from lawvm.norway.commencement import (
    apply_no_commencement_overrides,
    load_no_commencement_overrides,
)
from lawvm.norway.index import NOAmendmentIndex, build_no_amendment_index, load_no_amendment_index
from lawvm.norway.sources import (
    NOReplayStatus,
    iter_no_current_artifacts,
    iter_no_original_lti_artifacts,
    load_available_lti_law_ids,
    load_no_current_law_ids,
    load_no_current_law_titles,
    no_base_replay_status_from_statuses,
    parse_header_value,
    resolve_no_source_path,
)


@dataclass
class NOInventory:
    data_dir: Path
    current_law_ids: set[str] = field(default_factory=set)
    current_law_ids_with_local_base_source: set[str] = field(default_factory=set)
    amendment_status_counts: Counter[str] = field(default_factory=Counter)
    base_to_statuses: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    base_to_sources: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    malformed_base_refs: Counter[str] = field(default_factory=Counter)
    current_law_source_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    # W-45: the converse census — laws with a replayable ORIGINAL and no stored
    # consolidation. Absent from every field above by construction (they are all
    # keyed off ``current_law_ids``), so the family needs its own carrier. See
    # ``build_no_no_consolidation_rows`` for the universe note.
    stored_consolidation_law_ids: set[str] = field(default_factory=set)
    no_consolidation_rows: list[dict[str, Any]] = field(default_factory=list)

    def law_status_map(self) -> dict[str, NOReplayStatus]:
        laws_with_amendments = self.current_law_ids & set(self.base_to_statuses)
        statuses = {base_id: self._base_replay_status(base_id) for base_id in laws_with_amendments}
        for base_id in self.current_law_ids - laws_with_amendments:
            statuses[base_id] = NOReplayStatus.NO_AMENDMENTS
        return statuses

    def amended_executable_law_status_map(self) -> dict[str, NOReplayStatus]:
        amended_current_laws = self.current_law_ids & set(self.base_to_statuses)
        executable_current_laws = amended_current_laws & self.current_law_ids_with_local_base_source
        return {base_id: self._base_replay_status(base_id) for base_id in executable_current_laws}

    def to_dict(self) -> dict[str, Any]:
        status_map = self.law_status_map()
        executable_status_map = self.amended_executable_law_status_map()
        laws_with_amendments = {base_id for base_id, status in status_map.items() if status != NOReplayStatus.NO_AMENDMENTS}
        fully_replayable = {base_id for base_id, status in status_map.items() if status == NOReplayStatus.FULLY_REPLAYABLE}
        blocked_contingent = {base_id for base_id, status in status_map.items() if status == NOReplayStatus.BLOCKED_CONTINGENT}
        blocked_unknown = {base_id for base_id, status in status_map.items() if status == NOReplayStatus.BLOCKED_UNKNOWN}
        no_amendments = {base_id for base_id, status in status_map.items() if status == NOReplayStatus.NO_AMENDMENTS}
        executable_fully_replayable = {
            base_id for base_id, status in executable_status_map.items() if status == NOReplayStatus.FULLY_REPLAYABLE
        }
        executable_blocked_contingent = {
            base_id for base_id, status in executable_status_map.items() if status == NOReplayStatus.BLOCKED_CONTINGENT
        }
        executable_blocked_unknown = {
            base_id for base_id, status in executable_status_map.items() if status == NOReplayStatus.BLOCKED_UNKNOWN
        }
        missing_base_source = laws_with_amendments - self.current_law_ids_with_local_base_source

        top_blocked = sorted(
            (
                (base_id, len(self.base_to_sources[base_id]))
                for base_id in blocked_contingent | blocked_unknown
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]

        top_replayable = sorted(
            (
                (base_id, len(self.base_to_sources[base_id]))
                for base_id in fully_replayable
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]

        top_executable_blocked = sorted(
            (
                (base_id, len(self.base_to_sources[base_id]))
                for base_id in executable_blocked_contingent | executable_blocked_unknown
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]

        top_executable_replayable = sorted(
            (
                (base_id, len(self.base_to_sources[base_id]))
                for base_id in executable_fully_replayable
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]

        top_missing_base = sorted(
            (
                (base_id, len(self.base_to_sources[base_id]))
                for base_id in missing_base_source
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]

        no_consolidation_by_family = Counter(
            str(row.get("family") or "") for row in self.no_consolidation_rows
        )

        return {
            "data_dir": str(self.data_dir),
            "current_laws": len(self.current_law_ids),
            "current_laws_with_local_base_source": len(self.current_law_ids_with_local_base_source),
            "current_laws_without_local_base_source": len(
                self.current_law_ids - self.current_law_ids_with_local_base_source
            ),
            # W-45: the converse of ``current_laws_without_local_base_source``.
            # That counter is "the scan wants this law and has no original";
            # these are "we have a replayable original and there is nothing to
            # compare it against". Neither population overlaps the other, and
            # this one has no denominator anywhere else in this dict — it is
            # outside ``current_law_ids`` by construction.
            "stored_consolidations": len(self.stored_consolidation_law_ids),
            "originals_without_consolidation": len(self.no_consolidation_rows),
            "originals_without_consolidation_amending_act": no_consolidation_by_family[
                "amending_act"
            ],
            "originals_without_consolidation_temporary_or_wage_board": (
                no_consolidation_by_family["temporary_act"]
                + no_consolidation_by_family["wage_board_act"]
            ),
            "originals_without_consolidation_substantive": no_consolidation_by_family[
                "substantive_act"
            ],
            "originals_without_consolidation_substantive_without_repeal_evidence": sum(
                1
                for row in self.no_consolidation_rows
                if row.get("family") == "substantive_act" and not row.get("repealed_by")
            ),
            "amendment_documents": sum(self.amendment_status_counts.values()),
            "amendment_documents_by_status": dict(self.amendment_status_counts),
            "current_laws_with_amendments": len(laws_with_amendments),
            "current_laws_without_amendments": len(no_amendments),
            "current_laws_fully_replayable": len(fully_replayable),
            "current_laws_blocked_contingent": len(blocked_contingent),
            "current_laws_blocked_unknown": len(blocked_unknown),
            "current_laws_with_amendments_missing_base_source": len(missing_base_source),
            "current_laws_with_amendments_fully_replayable_executable": len(executable_fully_replayable),
            "current_laws_with_amendments_blocked_contingent_executable": len(executable_blocked_contingent),
            "current_laws_with_amendments_blocked_unknown_executable": len(executable_blocked_unknown),
            "top_blocked_current_laws": [
                {"base_id": base_id, "amendments": count}
                for base_id, count in top_blocked
            ],
            "top_executable_blocked_current_laws": [
                {"base_id": base_id, "amendments": count}
                for base_id, count in top_executable_blocked
            ],
            "top_fully_replayable_current_laws": [
                {"base_id": base_id, "amendments": count}
                for base_id, count in top_replayable
            ],
            "top_executable_fully_replayable_current_laws": [
                {"base_id": base_id, "amendments": count}
                for base_id, count in top_executable_replayable
            ],
            "top_missing_base_source_current_laws": [
                {"base_id": base_id, "amendments": count}
                for base_id, count in top_missing_base
            ],
            "malformed_base_refs": dict(self.malformed_base_refs),
            "current_law_source_diagnostic_count": len(self.current_law_source_diagnostics),
            "current_law_source_diagnostic_rule_counts": dict(
                Counter(str(row.get("rule_id") or "") for row in self.current_law_source_diagnostics)
            ),
            "current_law_source_diagnostics": list(self.current_law_source_diagnostics),
        }

    def _base_replay_status(self, base_id: str) -> NOReplayStatus:
        return no_base_replay_status_from_statuses(
            self.base_to_statuses.get(base_id, [])
        )


def build_no_inventory(
    data_dir: Optional[Path] = None,
    index: Optional[NOAmendmentIndex] = None,
    index_path: Optional[Path] = None,
    commencement_path: Optional[Path] = None,
) -> NOInventory:
    data_dir = resolve_no_source_path(data_dir)
    if index is None and index_path is not None:
        index = load_no_amendment_index(index_path)
    if index is None:
        index = build_no_amendment_index(data_dir)
    if commencement_path is not None:
        overrides = load_no_commencement_overrides(commencement_path)
        index = apply_no_commencement_overrides(index, overrides)
    inventory = NOInventory(data_dir=data_dir)

    current_law_source_diagnostics: list[dict[str, Any]] = []
    inventory.current_law_ids = load_no_current_law_ids(
        data_dir,
        diagnostics_out=current_law_source_diagnostics,
    )
    if not inventory.current_law_ids:
        fallback_ids = {artifact.logical_id for artifact in iter_no_current_artifacts(data_dir)}
        if fallback_ids:
            current_law_source_diagnostics.append(
                diagnostic_detail(
                    rule_id="no_inventory_current_law_id_artifact_fallback_used",
                    family="source_pathology",
                    phase="acquisition",
                    blocking=True,
                    reason=(
                        "Norway inventory used current artifact locators as a fallback because the current-law ID "
                        "parser returned no retained IDs."
                    ),
                    fallback_current_law_count=len(fallback_ids),
                )
            )
        inventory.current_law_ids = fallback_ids
    inventory.current_law_source_diagnostics = current_law_source_diagnostics
    inventory.current_law_ids_with_local_base_source = (
        inventory.current_law_ids & load_available_lti_law_ids(data_dir)
    )

    for entry in index.entries:
        inventory.amendment_status_counts[entry.effective_status] += 1
        for base_id in entry.base_ids:
            if not base_id.startswith("no/lov/"):
                inventory.malformed_base_refs[base_id] += 1
                continue
            # W-39: the status a binding contributes is the status of THAT
            # binding, not of the act. This loop was already per (entry, base)
            # — a staged act whose part I is commenced and part III is not
            # simply reports different statuses to its two laws, which is what
            # the evidence says. ``amendment_status_counts`` above stays
            # act-level and so stays byte-identical.
            _date, binding_status = entry.effective_date_for_base(base_id)
            inventory.base_to_statuses[base_id].append(binding_status)
            inventory.base_to_sources[base_id].append(entry.source_id)

    # W-45: the converse census, computed from the same archive + the maps just
    # built (no second index pass). Runs last so nothing above can see it and no
    # existing counter can move.
    inventory.stored_consolidation_law_ids = load_no_stored_consolidation_law_ids(data_dir)
    inventory.no_consolidation_rows = build_no_no_consolidation_rows(
        data_dir,
        stored_consolidation_law_ids=inventory.stored_consolidation_law_ids,
        base_to_statuses=inventory.base_to_statuses,
        base_to_sources=inventory.base_to_sources,
    )

    return inventory


def build_no_missing_base_report(
    inventory: NOInventory,
    *,
    current_law_titles: Optional[dict[str, str]] = None,
    base_id: str | None = None,
    min_amendments: int = 1,
) -> dict[str, Any]:
    current_law_title_diagnostics: list[dict[str, Any]] = []
    if current_law_titles is None:
        current_law_titles = load_no_current_law_titles(
            inventory.data_dir,
            diagnostics_out=current_law_title_diagnostics,
        )

    missing_base_source = sorted(
        (
            base_id_candidate,
            len(inventory.base_to_sources[base_id_candidate]),
        )
        for base_id_candidate in (
            (inventory.current_law_ids & set(inventory.base_to_statuses))
            - inventory.current_law_ids_with_local_base_source
        )
        if (base_id is None or base_id_candidate == base_id)
        and len(inventory.base_to_sources[base_id_candidate]) >= min_amendments
    )
    missing_base_source.sort(key=lambda item: (-item[1], item[0]))

    laws = [
        {
            "base_id": law_id,
            "title": current_law_titles.get(law_id, ""),
            "amendments": amendment_count,
            "source_ids": sorted(inventory.base_to_sources[law_id]),
        }
        for law_id, amendment_count in missing_base_source
    ]

    return {
        "data_dir": str(inventory.data_dir),
        "current_laws": len(inventory.current_law_ids),
        "missing_base_source_law_count": len(laws),
        "base_id_filter": base_id or "",
        "min_amendments": min_amendments,
        "laws": laws,
        "current_law_title_diagnostic_count": len(current_law_title_diagnostics),
        "current_law_title_diagnostic_rule_counts": dict(
            Counter(str(row.get("rule_id") or "") for row in current_law_title_diagnostics)
        ),
        "current_law_title_diagnostics": current_law_title_diagnostics,
    }


# ---------------------------------------------------------------------------
# W-45: the "replayable original, no stored consolidation" family
# ---------------------------------------------------------------------------
#
# ``build_no_missing_base_report`` above answers "which laws does the scan want
# to verify but cannot, for want of a local original?". This section answers the
# converse: "which originals could we replay that the scan never reaches at all,
# for want of a consolidation to compare them against?".
#
# The second family is STRUCTURALLY invisible to every counter in this module.
# ``load_no_current_law_ids`` walks stored consolidations only, so a law with no
# consolidation is absent from ``current_law_ids`` — no denominator, no bucket,
# no receipt, and therefore no way to tell "we never acquired this law" apart
# from "this law has no current text because it is repealed". W-44 measured the
# family at 2,642 laws on the 2026-07-10 corpus and found zero demonstrated
# acquisition gaps. Everything below recomputes that measurement at RUNTIME so
# the receipt stays live rather than being a frozen probe output.

NO_NO_CONSOLIDATION_FAMILIES: tuple[str, ...] = (
    "amending_act",
    "temporary_act",
    "wage_board_act",
    "substantive_act",
)
"""Closed set of title-shape families for the no-consolidation census.

These are DATA VALUES on a census row, not witness rule ids: nothing here is a
hypothesis about amendment semantics that a replay could falsify. They partition
the family by why a law plausibly has no current text — it never had one of its
own (``amending_act``), it expired by its own terms (``temporary_act``), it
self-repealed on a Rikslønnsnemnda ruling (``wage_board_act``), or it is a real
standalone act and therefore needs a repeal explanation (``substantive_act``).
"""

_NO_MONTH_NUMBERS: dict[str, int] = {
    "januar": 1,
    "februar": 2,
    "mars": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}

# "17. juni 2005 nr. 58" -> no/lov/2005-06-17-58. The long-form citation Lovdata
# writes inside a repeal manifest's list items; there is no refid attribute to
# read there, only prose.
_NO_ACT_CITATION_RE = compile_classifier_regex(
    r"(\d{1,2})\.\s*(" + "|".join(_NO_MONTH_NUMBERS) + r")\s+(\d{4})\s+nr\.?\s*(\d+)",
    re.IGNORECASE,
    classifier_id="norway.inventory.long_form_act_citation",
)
# The manifest block's own lead text is the ONLY discriminator between a repeal
# manifest and its structurally identical amend sibling, so both halves matter:
# it must mention repeal AND must not open with "Endring(ar) i ...".
_NO_REPEAL_MANIFEST_HEADER_RE = compile_classifier_regex(
    r"(?:oppheva|oppheves|opphevast|opphevet|opphever|oppheving)\b",
    re.IGNORECASE,
    classifier_id="norway.inventory.repeal_manifest_header",
)
_NO_AMEND_MANIFEST_HEADER_RE = compile_classifier_regex(
    r"^\s*endring",
    re.IGNORECASE,
    classifier_id="norway.inventory.amend_manifest_header",
)
# Title shapes. The optional temporariness prefix is spelled out rather than
# written ``midlertidige?\s+`` because a quantifier nested inside an optional
# group trips ``lawvm_regex_risks``; titles arrive whitespace-normalized from
# ``parse_header_value``, so a literal space is equivalent here.
_NO_AMENDING_TITLE_RE = compile_classifier_regex(
    r"^lov om (?:midlertidig |midlertidige |mellombels |mellombelse )?"
    r"(?:endring\w*|oppheving\w*|opphevelse\w*)\b",
    re.IGNORECASE,
    classifier_id="norway.inventory.amending_act_title",
)
_NO_WAGE_BOARD_TITLE_RE = compile_classifier_regex(
    r"^lov om (?:lønnsnemnd|lønnsnemndbehandling|lønnsnemnda)",
    re.IGNORECASE,
    classifier_id="norway.inventory.wage_board_act_title",
)
_NO_TEMPORARY_TITLE_RE = compile_classifier_regex(
    r"^(?:midlertidig|mellombels)\w*\s+lov\b|^lov om midlertidig",
    re.IGNORECASE,
    classifier_id="norway.inventory.temporary_act_title",
)
# Lovdata writes a built-in expiry into the act's own ``dateInForce`` header
# ("... oppheves 2023-01-01", "... oppheves ved kgl.res."), which is a temporary
# act even when the title says nothing about it.
_NO_SELF_REPEAL_IN_FORCE_RE = compile_classifier_regex(
    r"oppheves \d{4}-\d{2}-\d{2}|oppheves ved",
    re.IGNORECASE,
    classifier_id="norway.inventory.self_repealing_date_in_force",
)

_NO_DOCUMENT_BODY_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' documentBody ')]"
)
_NO_MANIFEST_BLOCK_XPATH = (
    ".//*[contains(concat(' ', normalize-space(@class), ' '), ' defaultP ')]"
)


def load_no_stored_consolidation_law_ids(source_path: Optional[Path] = None) -> set[str]:
    """Ids whose ``no://lov/.../current.xml`` artifact exists locally.

    Deliberately NOT :func:`load_no_current_law_ids`, which is the narrower
    "…and that consolidation has operative content". On the 2026-07-10 corpus
    763 consolidations are stored and 645 are operative: the 118-law difference
    is Lovdata consolidating an amending act down to its bare change
    instructions, which carry no ``legalArticleHeader`` and so read as
    non-operative. 110 of those 118 also have an original.

    The distinction is load-bearing for the census below. Those 110 laws DO have
    a stored consolidation — it just is not a law text — so counting them as
    "no stored consolidation" would be false, and would inflate the amending-act
    family from 2,514 to 2,624 and the would-be-candidate ceiling from 55 to 64.
    Both universes are reported side by side (``stored_consolidations`` and
    ``current_laws``) rather than one being silently substituted for the other.
    """
    return {artifact.logical_id for artifact in iter_no_current_artifacts(source_path)}


def read_no_structural_repeal_manifest(
    payload: bytes,
    *,
    self_id: str = "",
) -> tuple[str, ...]:
    """Law ids this act names in a structural repeal manifest, in document order.

    Lovdata LTI acts carry a machine-readable repeal manifest at the top of
    ``documentBody``::

        <article class="defaultP">Følgjande lover blir oppheva:
          <ul class="defaultList">
            <li><article class="legalP">Lov 17. juni 2005 nr. 58 om ...</article></li>
          </ul>
        </article>

    Sibling blocks use the IDENTICAL markup for "Endringar i følgjande lover:"
    (amend, not repeal), so the block's lead text is the only discriminator —
    hence the two-sided header test.

    This is the structural read, deliberately not a prose pass over the act
    body. W-44 measured both. The prose pass ("Fra samme tid oppheves lov
    3. juni 2005 nr. 33 ...") over-fires on section-level repeals and on acts
    that merely recite someone else's repeal; the structural read carries a
    corpus-wide precision control instead — of the 332 laws named in some
    manifest, only 24 still have a stored consolidation, and each of those 24 is
    a staged or not-yet-commenced repeal. The conjunction "named in a manifest
    AND absent from the consolidation snapshot" is what the census relies on.

    ``self_id`` suppresses an act naming itself (a repeal act that restates its
    own citation), which would otherwise make every such act its own repealer.
    """
    # The grafter's tolerant Lovdata parser: same reader the rest of the NO
    # frontend uses, so a document this census can read is a document replay
    # could read. Imported lazily to keep this module free of the grafter's
    # import cost, matching ``sources.py``'s convention.
    from lawvm.norway.grafter import _parse_document

    try:
        root = _parse_document(payload)
    except Exception:
        return ()
    bodies = cast(list[etree._Element], root.xpath(_NO_DOCUMENT_BODY_XPATH))
    body = bodies[0] if bodies else root

    named: list[str] = []
    seen: set[str] = set()
    for block in cast(list[etree._Element], body.xpath(_NO_MANIFEST_BLOCK_XPATH)):
        lead = " ".join((block.text or "").split())
        if not lead:
            continue
        # Census receipt only: these read a manifest block's OWN lead text to tell
        # repeal from amend. No replay authority — the DOM owns the structure, and
        # nothing downstream of the report consumes the result.
        # lawvm-regex: diagnostic census manifest lead-text discriminator, amend half
        if _NO_AMEND_MANIFEST_HEADER_RE.match(lead):
            continue
        # lawvm-regex: diagnostic census manifest lead-text discriminator, repeal half
        if not _NO_REPEAL_MANIFEST_HEADER_RE.search(lead):
            continue
        for item in cast(list[etree._Element], block.xpath(".//li")):
            text = " ".join("".join(str(part) for part in item.itertext()).split())
            # Lovdata gives no refid attribute inside a manifest list item, only the
            # long-form prose citation, so the id has to be read out of the text.
            # lawvm-regex: diagnostic census long-form citation read inside a manifest item
            for match in _NO_ACT_CITATION_RE.finditer(text):
                law_id = (
                    f"no/lov/{match.group(3)}"
                    f"-{_NO_MONTH_NUMBERS[match.group(2).lower()]:02d}"
                    f"-{int(match.group(1)):02d}-{int(match.group(4))}"
                )
                if law_id == self_id or law_id in seen:
                    continue
                seen.add(law_id)
                named.append(law_id)
    return tuple(named)


def build_no_structural_repeal_manifest(
    source_path: Optional[Path] = None,
) -> dict[str, tuple[str, ...]]:
    """Map repealed law id -> the acts naming it in a structural repeal manifest.

    Both lanes are read. Originals carry the manifest as enacted; stored
    consolidations carry it as amended, which is where a repeal introduced by a
    later amendment to the repealing act shows up. Scanning only one lane loses
    repeals the other records.
    """
    source_path = resolve_no_source_path(source_path)
    named_by: dict[str, set[str]] = defaultdict(set)
    lanes: tuple[Iterable[Any], ...] = (
        iter_no_original_lti_artifacts(source_path),
        iter_no_current_artifacts(source_path),
    )
    for lane in lanes:
        for artifact in lane:
            for law_id in read_no_structural_repeal_manifest(
                artifact.payload, self_id=artifact.logical_id
            ):
                named_by[law_id].add(artifact.logical_id)
    return {law_id: tuple(sorted(sources)) for law_id, sources in named_by.items()}


def no_no_consolidation_family(title: str, date_in_force: str = "") -> str:
    """Classify a no-consolidation law by title shape into a census family.

    Order is significant and is the order of decreasing certainty:

    1. ``amending_act`` — the title opens "Lov om endring(ar/er) i ..." or
       "Lov om oppheving av ...". Such an act has no standing text of its own;
       Lovdata consolidates roughly 4% of them and drops the rest, so absence is
       the norm rather than a gap.
    2. ``wage_board_act`` — "Lov om lønnsnemnd(behandling) ...", which by its own
       terms lapses when Rikslønnsnemnda rules on the dispute.
    3. ``temporary_act`` — a title declaring itself midlertidig/mellombels, or a
       ``dateInForce`` header carrying a built-in expiry. Checked after the two
       above because "Lov om midlertidige endringer i ..." is an amending act
       first and a temporary one second.
    4. ``substantive_act`` — everything else: a real standalone act, which
       therefore OWES a repeal explanation. This is the residue the census is
       actually about; the other three families explain themselves.
    """
    # Census receipt only: these four read the act's OWN title / dateInForce header
    # to label a report row. No replay authority — no parse, lowering, index or
    # verify path reads ``family``, so a misclassified row moves a count on a
    # receipt and nothing else.
    # lawvm-regex: diagnostic census title label, amending act
    if _NO_AMENDING_TITLE_RE.match(title):
        return "amending_act"
    # lawvm-regex: diagnostic census title label, wage-board act
    if _NO_WAGE_BOARD_TITLE_RE.match(title):
        return "wage_board_act"
    lowered = title.lower()
    if (
        # lawvm-regex: diagnostic census title label, temporary act
        _NO_TEMPORARY_TITLE_RE.search(title)
        or "midlertidig lov" in lowered
        or "mellombels lov" in lowered
        # lawvm-regex: diagnostic census header label, built-in expiry in dateInForce
        or _NO_SELF_REPEAL_IN_FORCE_RE.search(date_in_force)
    ):
        return "temporary_act"
    return "substantive_act"


def build_no_no_consolidation_rows(
    data_dir: Optional[Path] = None,
    *,
    index: Optional[NOAmendmentIndex] = None,
    index_path: Optional[Path] = None,
    stored_consolidation_law_ids: Optional[set[str]] = None,
    base_to_statuses: Optional[Mapping[str, list[str]]] = None,
    base_to_sources: Optional[Mapping[str, list[str]]] = None,
) -> list[dict[str, Any]]:
    """One census row per law with a local original and no stored consolidation.

    Rows carry ``base_id``, ``title``, ``family``, ``would_be_status``,
    ``repealed_by`` and ``amendments``, sorted by id.

    ``would_be_status`` is the replay status the inventory WOULD assign this law
    if a consolidation existed — the same
    :func:`no_base_replay_status_from_statuses` over the same per-binding
    statuses ``build_no_inventory`` feeds it. It is ``None``, not
    ``no_amendments``, when nothing in the index binds the law: "the index has
    no opinion" and "the index says zero amendments" are different claims, and
    only the former is true of the 2,552 laws nothing amends. The counterfactual
    this supports is the candidate ceiling — 55 of the 2,642 would enter the
    scan as ``fully_replayable`` if Lovdata published a current text for them.

    The status maps and the stored-consolidation set may be passed in by a
    caller that already has them (``build_no_inventory`` does); otherwise they
    are derived here from ``index`` / ``index_path`` / the archive, so the
    function stands alone for callers with no inventory (``verify.py`` does).
    """
    data_dir = resolve_no_source_path(data_dir)
    if base_to_statuses is None or base_to_sources is None:
        if index is None and index_path is not None:
            index = load_no_amendment_index(index_path)
        if index is None:
            index = build_no_amendment_index(data_dir)
        derived_statuses: dict[str, list[str]] = defaultdict(list)
        derived_sources: dict[str, list[str]] = defaultdict(list)
        for entry in index.entries:
            for entry_base_id in entry.base_ids:
                if not entry_base_id.startswith("no/lov/"):
                    continue
                _date, binding_status = entry.effective_date_for_base(entry_base_id)
                derived_statuses[entry_base_id].append(binding_status)
                derived_sources[entry_base_id].append(entry.source_id)
        base_to_statuses = derived_statuses
        base_to_sources = derived_sources

    if stored_consolidation_law_ids is None:
        stored_consolidation_law_ids = load_no_stored_consolidation_law_ids(data_dir)

    repeal_manifest = build_no_structural_repeal_manifest(data_dir)

    rows: list[dict[str, Any]] = []
    for artifact in iter_no_original_lti_artifacts(data_dir):
        law_id = artifact.logical_id
        if law_id in stored_consolidation_law_ids:
            continue
        try:
            title = parse_header_value(artifact.payload, "title")
            date_in_force = parse_header_value(artifact.payload, "dateInForce")
        except Exception:
            title = ""
            date_in_force = ""
        statuses = list(base_to_statuses.get(law_id, []))
        would_be = no_base_replay_status_from_statuses(statuses) if statuses else None
        rows.append(
            {
                "base_id": law_id,
                "title": title,
                "family": no_no_consolidation_family(title, date_in_force),
                "would_be_status": str(would_be) if would_be is not None else None,
                "repealed_by": list(repeal_manifest.get(law_id, ())),
                "amendments": len(base_to_sources.get(law_id, [])),
            }
        )
    rows.sort(key=lambda row: str(row["base_id"]))
    return rows


def summarize_no_no_consolidation_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """The census reduced to the four numbers a scan receipt needs.

    ``substantive_unexplained`` is the load-bearing one: a substantive act with
    no stored consolidation AND no act naming it in a repeal manifest. On the
    2026-07-10 corpus it is 13, every one adjudicated by hand as spent, absorbed
    or never commenced. It is the number that moves if a future corpus really
    does lose an in-force law.
    """
    by_family = Counter(str(row.get("family") or "") for row in rows)
    return {
        "total": len(rows),
        "by_family": {family: by_family[family] for family in NO_NO_CONSOLIDATION_FAMILIES},
        "would_be_candidates": sum(
            1 for row in rows if row.get("would_be_status") == NOReplayStatus.FULLY_REPLAYABLE
        ),
        "substantive_unexplained": sum(
            1
            for row in rows
            if row.get("family") == "substantive_act" and not row.get("repealed_by")
        ),
    }


def build_no_no_consolidation_report(
    inventory: NOInventory,
    *,
    family: str | None = None,
    base_id: str | None = None,
    min_amendments: int = 0,
) -> dict[str, Any]:
    """The no-consolidation census as a report, mirroring the missing-base one.

    ``min_amendments`` defaults to 0 rather than the missing-base report's 1:
    2,552 of the 2,642 rows have no indexed amendment at all, and they are the
    point of the census rather than noise to be filtered out of it.
    """
    rows = [
        row
        for row in inventory.no_consolidation_rows
        if (base_id is None or row["base_id"] == base_id)
        and (family is None or row["family"] == family)
        and int(row["amendments"]) >= min_amendments
    ]
    rows.sort(key=lambda row: (-int(row["amendments"]), str(row["base_id"])))
    summary = summarize_no_no_consolidation_rows(rows)

    return {
        "data_dir": str(inventory.data_dir),
        "current_laws": len(inventory.current_law_ids),
        "stored_consolidations": len(inventory.stored_consolidation_law_ids),
        "originals_without_consolidation": len(inventory.no_consolidation_rows),
        "without_consolidation_law_count": len(rows),
        "family_filter": family or "",
        "base_id_filter": base_id or "",
        "min_amendments": min_amendments,
        "counts_by_family": summary["by_family"],
        "would_be_status_counts": dict(
            Counter(str(row["would_be_status"]) for row in rows)
        ),
        "would_be_candidates": summary["would_be_candidates"],
        "substantive_unexplained": summary["substantive_unexplained"],
        "substantive_unexplained_law_ids": sorted(
            row["base_id"]
            for row in rows
            if row["family"] == "substantive_act" and not row["repealed_by"]
        ),
        "laws": rows,
    }
