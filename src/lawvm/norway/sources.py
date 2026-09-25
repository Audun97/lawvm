"""Shared Norway source-store helpers.

Norway is transitioning from raw Lovdata tarballs as a direct runtime
dependency to the same Farchive-backed source boundary used elsewhere in
LawVM. The helpers here make that migration boring:

- resolve the effective Norway source path
- read current/original/amendment bytes by logical id
- iterate logical artifacts independent of whether backing storage is a legacy
  tar directory or a ``.farchive`` DB
- hydrate a Norway Farchive from the four public Lovdata tarballs
"""
from __future__ import annotations

import hashlib
import os
import re
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Optional, cast

from lxml import etree

from lawvm.core.archive_safety import (
    ArchiveMemberTooLarge,
    log_archive_member_too_large,
    safe_tar_read,
)
from lawvm.core.diagnostic_records import diagnostic_detail
from lawvm.core.filter_result import RejectedItem
from lawvm.core.ir_helpers import kind_str
from lawvm.core.source_lane import SourceLaneAttempt, SourceLaneSelectionEvidence
from lawvm.core.xml_parse import parse_corpus_xml
from lawvm.norway.grafter import (
    lovdata_amendment_filename_to_id,
    lovdata_filename_to_id,
    normalize_lovdata_refid,
)
from lawvm.core.quirks_disposition import QuirksDisposition

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NORWAY_DIR = _REPO_ROOT / "data" / "norway"
DEFAULT_NORWAY_DB = _REPO_ROOT / "data" / "norway.farchive"
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ARCHIVE_SPAN_RE = re.compile(r"^lovtidend-avd1-(\d{4})(?:-(\d{4}))?\.tar\.bz2$")
_NO_CURRENT_LOCATOR_RE = re.compile(r"^no://lov/(?P<date>\d{4}-\d{2}-\d{2}-\d+)/current\.xml$")
_NO_ORIGINAL_LOCATOR_RE = re.compile(r"^no://lov/(?P<date>\d{4}-\d{2}-\d{2}-\d+)/original\.lti\.xml$")
_NO_AMENDMENT_LOCATOR_RE = re.compile(r"^no://lovtid/(?P<date>\d{4}-\d{2}-\d{2}-\d+)/amendment\.xml$")
_NO_FORSKRIFT_FILENAME_RE = re.compile(r"(?:^|/)sf-(?P<date>\d{8})-(?P<num>\d+)\.xml$")
_NO_UNNUMBERED_LAW_ID_RE = re.compile(r"^no/lov/\d{4}-\d{2}-\d{2}$")
_NO_CHANGES_TO_DOCUMENTS_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' changesToDocuments ')]"
)
_NO_FORSKRIFT_LOCATOR_RE = re.compile(
    r"^no://forskrift/(?P<date>\d{4}-\d{2}-\d{2}-\d+)/original\.lti\.xml$"
)


# §1.8 typed-receipt reason_code for archive members that declare more bytes
# than ``$LAWVM_MAX_ARCHIVE_MEMBER_BYTES``. The receipt carries the rejected
# member's ``member_name`` as ``item``, the four-field diagnostic on ``reason``,
# and is non-blocking (the cap is operator-tunable; over-retention per §0 —
# the loader treats the oversized member as absent and lets the caller
# adjudicate the missing source). Mirrors the precedent at
# ``us_federal/import_plaw.py:212-234`` and ``finland/he_acquisition.py:858-884``
# where the typed skip is the §1.8 contract surface; the stderr receipt via
# ``log_archive_member_too_large`` was a workaround for generators whose
# ``(id, bytes)`` yield shape could not extend a ``RejectedItem`` list without
# breaking the destructuring consumer protocol — pattern (B) sink-threading
# threads the accumulator as an optional kwarg so destructuring stays intact.
NO_ARCHIVE_MEMBER_TOO_LARGE_REASON_CODE = "no_archive_member_too_large"


def _no_record_archive_skip(
    rejected_items: list[RejectedItem[str]] | None,
    *,
    exc: ArchiveMemberTooLarge,
) -> None:
    """Append a typed ``RejectedItem`` receipt for an oversized archive member.

    When ``rejected_items`` is ``None`` (caller did not thread a sink), the
    prior structured stderr receipt via
    :func:`log_archive_member_too_large` is preserved so the skip stays
    greppable (the §1.8 minimum for out-of-scope destructuring consumers
    whose signature cannot be widened here without breaking ``(id, bytes)``
    unpacking). When ``rejected_items`` is a list, a typed
    ``RejectedItem(item=member_name, reason=..., reason_code=..., blocking=False)``
    is appended instead — the §1.8 contract surface upstream tooling reads,
    not a stderr line that disappears. Mirrors the precedent at
    ``us_federal/import_plaw.py:212`` and ``tools/import_zip.py:322``.

    Per AGENTS.md §1.10 the reason embeds the offending archive_path /
    member_name / declared_size / cap_bytes so triage does not have to
    re-run extraction to identify the rejected member. The companion
    ``ArchiveMemberTooLargeDiagnostic.render_reason`` in
    ``core/archive_safety.py`` omits these (it lives below the
    frontend/core boundary and cannot reference frontend-local accumulators);
    this helper layers them on at the §1.8 receipt surface.
    """
    if rejected_items is None:
        log_archive_member_too_large(exc)
        return
    rejected_items.append(
        RejectedItem(
            item=exc.member_name,
            reason=(
                f"archive member {exc.member_name} from "
                f"{exc.archive_path or '<archive>'} declares "
                f"{exc.declared_size} bytes (cap {exc.cap_bytes}); "
                "refusing to materialise into memory. Raise "
                "LAWVM_MAX_ARCHIVE_MEMBER_BYTES to admit it, or trim "
                "the source archive."
            ),
            reason_code=NO_ARCHIVE_MEMBER_TOO_LARGE_REASON_CODE,
            blocking=False,
        )
    )


@dataclass(frozen=True)
class NOLocatedArtifact:
    locator: str
    logical_id: str
    source_name: str
    member_name: str
    payload: bytes


class NOEffectiveStatus(StrEnum):
    """Closed set of commencement (in-force) resolution outcomes for a NO act.

    A ``StrEnum`` so the value flows through the serialized ``effective_status``
    dict/field and test ``== "..."`` comparisons byte-for-byte while the value
    set is closed.
    """

    DATED = "dated"
    """A concrete in-force date was resolved."""

    IMMEDIATE = "immediate"
    """In force on the source/promulgation date."""

    OVERRIDE = "override"
    """An explicit commencement override supplied the in-force date."""

    INSTRUMENT_AUTHORIZED = "instrument_authorized"
    """An official Norsk Lovtidend whole-act commencement instrument supplied
    the in-force date. Distinct from ``DATED`` (metadata-derived, no instrument
    in evidence) and from ``OVERRIDE`` (manually curated evidence) so a reader
    of a serialized index can tell why the act carries a date."""

    PART_INSTRUMENT_AUTHORIZED = "part_instrument_authorized"
    """An official instrument commenced the ONE part of a staged multi-part act
    that amends this base law (W-39).

    Never an act-level status: it is issued per (act, base law) binding, because
    that is exactly the scope the evidence covers. The act's own
    ``effective_status`` stays whatever it was — usually ``contingent`` — since
    the act's other parts are still uncommenced, and no single date could stand
    for parts that commence years apart."""

    SECTION_INSTRUMENT_AUTHORIZED = "section_instrument_authorized"
    """W-100. Official instrument(s) dated this (act, base law) binding BELOW
    binding level — a binding date with carve-outs, per-section dates, or both —
    and every op of the act on this law resolves to a date through
    ``NOAmendmentIndexEntry.effective_date_for_op``. Per binding, never
    act-level, for W-39's reason. The binding's own ``effective_date`` may be
    ``None`` when only sections were dated; consumers that need one date per op
    must ask per op."""

    SECTION_INSTRUMENT_PARTIAL = "section_instrument_partial"
    """W-100. Instrument(s) dated SOME ops of this binding and not others: a
    carved-out section still undated, or a section list that does not cover
    every section the act's ops target. Unresolved at binding level — the base
    law stays ``blocked_contingent`` — while replay still dates the ops it can
    and skips the rest with a per-op receipt."""

    CONTINGENT = "contingent"
    """In force on a condition / future delegated commencement (unresolved)."""

    MISSING = "missing"
    """No in-force signal present in the source."""

    UNKNOWN = "unknown"
    """An in-force signal was present but not interpretable."""


# Statuses that count as a RESOLVED in-force date (replayable). The complement
# (contingent/missing/unknown) blocks deterministic replay.
NO_RESOLVED_EFFECTIVE_STATUSES: frozenset[NOEffectiveStatus] = frozenset(
    {
        NOEffectiveStatus.DATED,
        NOEffectiveStatus.IMMEDIATE,
        NOEffectiveStatus.OVERRIDE,
        NOEffectiveStatus.INSTRUMENT_AUTHORIZED,
        NOEffectiveStatus.PART_INSTRUMENT_AUTHORIZED,
        NOEffectiveStatus.SECTION_INSTRUMENT_AUTHORIZED,
    }
)
NO_UNRESOLVED_EFFECTIVE_STATUSES: frozenset[NOEffectiveStatus] = frozenset(
    {NOEffectiveStatus.CONTINGENT, NOEffectiveStatus.MISSING, NOEffectiveStatus.UNKNOWN}
)
# W-100. Binding-level statuses that classify a base law as blocked on a
# contingent commencement even though some of the binding's ops are dated.
NO_PARTIALLY_RESOLVED_EFFECTIVE_STATUSES: frozenset[NOEffectiveStatus] = frozenset(
    {NOEffectiveStatus.SECTION_INSTRUMENT_PARTIAL}
)


class NOCommencementShape(StrEnum):
    """Closed set of shapes a *resolved* ``dateInForce`` field can have.

    Orthogonal to :class:`NOEffectiveStatus`, which says *how* the in-force date
    was resolved. This says what the Lovdata metadata field the date came from
    actually looked like — the distinction between "a date and nothing else" and
    "a date plus a delegated-commencement tail". A ``StrEnum`` so it flows
    through the serialized ``commencement_shape`` index field byte-for-byte
    while the value set stays closed, which is the point: the shape must be
    readable off a serialized index without re-parsing ``raw_date_in_force``.
    """

    PLAIN = "plain"
    """The field carried ISO dates and no delegated-commencement language."""

    STAGED_DELEGATED = "staged_delegated"
    """The field carried at least one ISO date AND a delegated-commencement
    tail (``Kongen bestemmer`` and its siblings).

    That conjunction — dates plus a tail — is the whole guarantee. It is a
    shape read off the raw field, not a claim about what the dates *do*: the
    common member is Lovdata's way of writing STAGED commencement (part of the
    act enters force at the stated date(s), the rest on a date the executive
    later fixes), but the label does not certify that reading of every member.
    ``no/lovtid/2024-06-21-50`` is the counterexample in the corpus — its
    ``Kongen bestemmer, oppheves 2026-07-01`` puts the delegated tail beside a
    REPEAL date, so its stated date takes force away rather than granting it.
    A reader who needs the dates' direction must go to ``raw_date_in_force``.

    This is emphatically NOT deferred commencement. Measured over the corpus,
    Lovdata's own consolidation shows most such acts ARE in force at their
    leading date, so the act stays resolved at ``min(dates)`` and stays inside
    :data:`NO_RESOLVED_EFFECTIVE_STATUSES`. The shape is a label on a resolved
    date, recording that the collapse to ``min(dates)`` threw away a staged tail
    the engine cannot yet represent at provision level (see
    ``notes/NORWAY_LAWVM_STATUS.md`` 2.3). Its operational use is that such an
    act is offered to the commencement-instrument authorization gate: an
    official whole-act instrument outranks a ``min(dates)`` metadata guess.
    """


def coerce_no_commencement_shape(value: object) -> NOCommencementShape:
    """Coerce a stored/loaded value to a ``NOCommencementShape``, failing loud.

    Used where ``commencement_shape`` re-enters from an untyped mapping
    (mirrors ``lawvm.core.quirks_disposition.coerce_quirks_disposition``): an
    unrecognized string is a registration gap, never a silently-carried label
    outside the closed set.
    """
    if isinstance(value, NOCommencementShape):
        return value
    return NOCommencementShape(str(value))


# Lovdata's delegated-commencement vocabulary in ``dateInForce``: the phrases
# that say "the executive fixes the (rest of the) commencement date". Read on
# the lowercased field, prefix-matched, so bokmål/nynorsk inflections of the
# same phrase (``fastsetter`` / ``fastsetjer`` after ``fastset``) are covered by
# one member.
#
# Which axis a marker lands on depends on whether the field ALSO carries a date:
# with no date it is the whole in-force signal, so the act is CONTINGENT; beside
# a date it is a staged tail, so the act stays DATED and is labelled
# :attr:`NOCommencementShape.STAGED_DELEGATED`.
#
# ``departementet fastset`` and ``kongen avgjer`` are the nynorsk siblings of
# ``departementet bestemmer`` / ``kongen bestemmer``; both were measured absent
# and are the batch-04 widening. Their total corpus effect is three acts and
# nothing else: ``no/lovtid/2016-06-17-56`` and ``no/lovtid/2021-04-23-23``
# (bare ``Kongen avgjer``, previously UNKNOWN — an in-force signal the reader
# could not interpret — now correctly CONTINGENT), and ``no/lovtid/2020-06-23-103``
# (``departementet fastset`` beside three dates, previously an unremarked plain
# DATED, now labelled STAGED_DELEGATED).
NO_DELEGATED_COMMENCEMENT_MARKERS: tuple[str, ...] = (
    "kongen bestemmer",
    "kongen fastset",
    "kongen avgjer",
    "departementet bestemmer",
    "departementet fastset",
    "fastsettes ved lov",
    "fra den tid",
)


class NOReplayStatus(StrEnum):
    """Closed set of per-base-law replayability classifications.

    Derived from the in-force statuses of a base law's amendments (INVENTORY
    axis, used by ``no_base_replay_status_from_statuses``) AND the endpoint
    outcome of a verify run (VERIFY axis — adds ``ERROR``, ``REPLAYED``,
    ``BLOCKED_MISSING_SOURCE``). A ``StrEnum`` so it flows through serialized
    status maps / test comparisons / ``_NO_BENCH_SOURCE_UNAVAILABLE_STATUSES``
    membership checks byte-for-byte.

    Closure invariant (§1.9): every ``NOVerifyResult.replay_status`` produced
    by ``verify_no_against_current`` and every inventory map value MUST be a
    member of this set. The prior shape reserved a typed enum for the
    inventory axis only and the verify endpoint (which emits
    ``replayed`` / ``blocked_missing_source`` / ``error`` as bare inline
    strings) escaped it — forcing the bench comparator's
    ``_NO_BENCH_SOURCE_UNAVAILABLE_STATUSES`` frozenset to read raw strings.
    """

    NO_AMENDMENTS = "no_amendments"
    """The base law has no amendments to replay (INVENTORY axis)."""

    FULLY_REPLAYABLE = "fully_replayable"
    """Every amendment has a resolved in-force date (INVENTORY axis)."""

    BLOCKED_CONTINGENT = "blocked_contingent"
    """At least one amendment is contingent (future/conditional commencement)."""

    BLOCKED_UNKNOWN = "blocked_unknown"
    """At least one amendment has a missing/unknown in-force status."""

    BLOCKED_MISSING_SOURCE = "blocked_missing_source"
    """Replay skipped amendments because their source text was not archived
    (VERIFY axis; produced when ``replay.amendments_skipped_missing_source``
    is non-empty — distinct from the in-force-status axis)."""

    REPLAYED = "replayed"
    """Replay completed with at least one applied amendment that did not
    error (VERIFY axis). Carries the comparison-surface judgment
    (consistent / divergent-bearing) underneath; the bench's SCORED path
    fires only when ``replay_status`` is ``REPLAYED``."""

    ERROR = "error"
    """Replay raised an unhandled exception (VERIFY axis). The bench maps
    this to ``BenchStatus.CRASH`` (an unexpected production failure),
    distinct from the SOURCE_UNAVAILABLE ceiling tier."""


# Reaching the bench comparator's ``SOURCE_UNAVAILABLE`` tier via the enum
# (single source of truth after migration — previously the bench held a
# parallel raw-string frozenset). ``REPLAYED``, ``ERROR``, and
# ``NO_AMENDMENTS`` stay out of this set: REPLAYED carries the SCORED path,
# ERROR maps to CRASH, and NO_AMENDMENTS maps to NO_TRUTH.
NO_BENCH_SOURCE_UNAVAILABLE_STATUSES: frozenset[NOReplayStatus] = frozenset(
    {
        NOReplayStatus.BLOCKED_CONTINGENT,
        NOReplayStatus.BLOCKED_MISSING_SOURCE,
        NOReplayStatus.BLOCKED_UNKNOWN,
    }
)


def no_base_replay_status_from_statuses(
    statuses: list[NOEffectiveStatus] | list[str],
) -> NOReplayStatus:
    """Classify a base law's replayability from its amendments' in-force statuses.

    Single source of truth for the rule shared by the inventory and the
    commencement report (was duplicated in both).
    """
    if not statuses:
        return NOReplayStatus.NO_AMENDMENTS
    if any(
        status == NOEffectiveStatus.CONTINGENT
        or status in NO_PARTIALLY_RESOLVED_EFFECTIVE_STATUSES
        for status in statuses
    ):
        return NOReplayStatus.BLOCKED_CONTINGENT
    if any(status not in NO_RESOLVED_EFFECTIVE_STATUSES for status in statuses):
        return NOReplayStatus.BLOCKED_UNKNOWN
    return NOReplayStatus.FULLY_REPLAYABLE


class NOBackfillLane(StrEnum):
    """Closed set of recommended source-acquisition lanes for a NO backfill.

    Derived from which candidate-source families surfaced. A ``StrEnum`` so it
    flows through serialized ``recommended_lane`` dict keys / advisory output and
    test comparisons byte-for-byte.
    """

    MIXED = "mixed"
    """Both local_corpus and statsrad produced candidates."""

    STATSRAD = "statsrad"
    """Only statsrad candidates surfaced."""

    LOCAL_CORPUS = "local_corpus"
    """Only local_corpus candidates surfaced."""

    LOVTIDEND_COMMENCEMENT_INSTRUMENT = "lovtidend_commencement_instrument"
    """An official Lovtidend instrument cites the contingent amending law."""

    UNRESOLVED = "unresolved"
    """No candidate surfaced in any lane."""


class NOBackfillHintStatus(StrEnum):
    """Closed set of next-source recommendation states for a NO backfill hint.

    Derived from the recommended backfill lane (``NOBackfillLane``). A
    ``StrEnum`` so it flows through the serialized ``hint_status`` dict key /
    advisory output and test comparisons byte-for-byte while the value set is
    closed.
    """

    NEEDS_EXTERNAL_OFFICIAL_SOURCE = "needs_external_official_source"
    """No local_corpus/statsrad candidate surfaced — search external channels."""

    COMPARE_EXISTING_LANES = "compare_existing_lanes"
    """Both local_corpus and statsrad produced candidates — compare them."""

    STATSRAD_FIRST = "statsrad_first"
    """Only statsrad candidates surfaced — start there."""

    LOCAL_CORPUS_FIRST = "local_corpus_first"
    """Only local_corpus candidates surfaced — start there."""

    LOVTIDEND_FIRST = "lovtidend_first"
    """An official Lovtidend commencement candidate should be validated first."""


class NOBackfillPlanStatus(StrEnum):
    """Closed set of per-source-plan-item states for a NO backfill plan.

    A ``StrEnum`` so it flows through the serialized ``plan_status`` dict key /
    advisory output and test comparisons byte-for-byte while the value set is
    closed.
    """

    CANDIDATE = "candidate"
    """A surfaced candidate source family to search/compare."""

    NEXT_OFFICIAL_SOURCE = "next_official_source"
    """An external official publication channel to search next."""

    FALLBACK_HISTORY = "fallback_history"
    """A deeper historical layer to fall back to."""


@dataclass(frozen=True)
class NOEffectiveDate:
    effective_status: NOEffectiveStatus
    effective_date: Optional[str] = None
    raw_text: str = ""
    # The shape of the ``dateInForce`` field the status was read off, and how
    # many ISO dates it held. ``date_count`` is carried here rather than
    # recomputed downstream so the staged-commencement receipt can name the
    # count of collapsed dates without re-parsing ``raw_text``.
    commencement_shape: NOCommencementShape = NOCommencementShape.PLAIN
    date_count: int = 0


@dataclass(frozen=True)
class NODeclaredChangeTargets:
    """The amendment targets Lovdata declares on one act's ``changesToDocuments`` block.

    Block presence is measured on the ``<dd class="changesToDocuments">`` element:
    2,942 of the 3,089 amendment artifacts carry one and 147 carry none. Every
    block present is non-empty, and 2,941 of them hold at least one ``lov``-form
    target — ``no/lovtid/2021-06-18-115`` declares only ``forskrift/1952-04-21-4287``.

    ``law_ids`` holds every declared ``lov`` reference normalized through
    :func:`normalize_lovdata_refid`, deduplicated in document order; forskrift
    references and the literal ``null`` normalize to nothing and never appear.
    ``unnumbered_law_ids`` is the ``lov/<date>`` subset declared without a
    trailing act number (109 declarations corpus-wide, e.g. ``lov/1967-02-10``).
    That is the whole claim the field makes: the declaration carried no act
    number. It is a label, not an unreachability verdict — 65 of the 92 such ids
    the index reports unbound do name a corpus law, filed there under a
    ``<date>-0`` id (``no/lov/1967-02-10`` is forvaltningsloven, present as
    ``no/lov/1967-02-10-0``). They stay inside the measured gap; see
    :func:`lawvm.norway.index._no_index_declared_target_unbound_diagnostic`.
    """

    block_present: bool = False
    law_ids: tuple[str, ...] = ()
    unnumbered_law_ids: tuple[str, ...] = ()


def resolve_no_source_path(path: Path | None = None) -> Path:
    """Return the effective Norway source path.

    Priority:
    1. explicit path argument
    2. ``LAWVM_NORWAY_DB``
    3. ``LAWVM_NORWAY_DATA_DIR``
    4. ``data/norway.farchive`` if present
    5. legacy ``data/norway`` directory
    """
    if path is not None:
        return path
    env_db = os.environ.get("LAWVM_NORWAY_DB")
    if env_db:
        return Path(env_db)
    env_dir = os.environ.get("LAWVM_NORWAY_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if DEFAULT_NORWAY_DB.exists():
        return DEFAULT_NORWAY_DB
    return DEFAULT_NORWAY_DIR


def is_no_farchive_path(path: Path | str) -> bool:
    path = Path(path)
    return path.suffix == ".farchive" or (path.exists() and path.is_file() and path.name.endswith(".farchive"))


def open_no_archive(db_path: Path | None = None, *, readonly: bool = True):  # returns Farchive
    from farchive import Farchive

    path = resolve_no_source_path(db_path)
    if not is_no_farchive_path(path):
        raise ValueError(f"Norway source path is not an farchive DB: {path}")
    return Farchive(path, readonly=readonly)


# Fallback consolidation horizon, used only when the source path carries no
# observation metadata (legacy tar directory). Source: the `gjeldende-lover`
# consolidation snapshot this corpus was captured from, recorded in
# ``notes/NORWAY_VERIFY_FINDINGS_LEDGER.md`` section 1 and used there as the
# commensurable comparison date behind every scan reading in the scoreboard.
# The farchive derivation below independently reproduces this date, and
# ``test_corpus_consolidation_snapshot_date_reproduces_the_fallback_constant``
# asserts that reproduction against the installed corpus — that executable
# check is what licenses this constant as the fallback rather than a second
# guess, and it is what makes it rot loudly on a corpus re-capture.
#
# 2026-07-10 -> 2026-08-17 at W-86, the first re-capture this constant has
# lived through, and the rot alarm fired exactly as designed. The derivation's
# contract is the latest OBSERVATION instant over the ``current.xml`` family,
# and on the restored corpus every one of the 758 spans was confirmed
# 2026-08-17 (the restoration ingest, item 91) — three days after the
# capture's own Lovdata generation date (`gjeldende-lover` lastModified
# 2026-08-14T01:31Z). The charter posed moving to 2026-08-14; measurement
# corrected it: the constant follows the derivation, not the tarball label.
# The three-day gap is observationally inert on this corpus — no act or
# instrument carries an effective date in (2026-08-14, 2026-08-17] (measured
# zero at W-86), and the full scan at --as-of 2026-08-17 is row-for-row
# byte-identical to the pinned --as-of 2026-08-14 scoreboard reading
# (``.tmp/w86/scan_0814.json`` vs ``scan_0817.json``). Scoreboard rows keep
# reading --as-of 2026-08-14, the snapshot-commensurable horizon.
NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE: str = "2026-08-17"


class NOConsolidationSnapshotError(ValueError):
    """An farchive Norway source carries no consolidated ``current.xml`` observation."""


def no_consolidation_snapshot_date(source_path: Path | None = None) -> str:
    """Return the ISO date of the consolidated snapshot the corpus carries.

    Replay is compared against the ``current.xml`` consolidated artifacts, and
    an farchive records when each artifact was observed. The latest observation
    over that family therefore *is* the consolidation horizon: a comparison at
    or after this date is commensurable with the snapshot, one before it is not
    — laws then read as defective purely because an amendment took effect in
    the gap (finding F-01 in ``notes/NORWAY_VERIFY_FINDINGS_LEDGER.md``).

    The instant read is :attr:`~farchive.StateSpan.last_confirmed_at`, not
    ``observed_from``. farchive's ``store`` branches on digest identity: content
    identical to the locator's head EXTENDS the open span — bumping
    ``last_confirmed_at`` and ``observation_count`` while leaving
    ``observed_from`` at the instant that content first appeared. Only
    ``last_confirmed_at`` therefore answers "when did the crawl last see this
    consolidation", which is the horizon; ``observed_from`` would freeze the
    answer at the last content *change* and re-open F-01 after any change-free
    re-crawl. The two coincide on today's corpus (every ``current.xml`` span has
    ``observation_count == 1``), so the distinction is latent, not academic.

    Only the newest span per locator is read, via :meth:`~farchive.Farchive.resolve`.
    A locator keeps exactly one open span, and a digest change closes the old
    span at the same instant the new one opens with that instant as its
    ``last_confirmed_at`` — so the open span's ``last_confirmed_at`` is
    monotonically the locator's maximum, and the closed spans behind it cannot
    beat it. This is one indexed single-row query per locator instead of
    materializing every locator's whole history.

    Observation instants are stored UTC and read as UTC, so the answer does not
    move with the reader's timezone. Falls back to
    :data:`NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE` only for a legacy tar
    directory, which records no observation instant at all. An farchive holding
    no consolidated artifact is a corrupt or mis-populated corpus, not a legacy
    one, and raises :class:`NOConsolidationSnapshotError` rather than borrowing
    the legacy constant — a silent share would make the two indistinguishable.
    """
    source_path = resolve_no_source_path(source_path)
    if not is_no_farchive_path(source_path) or not source_path.exists():
        return NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE
    latest: datetime | None = None
    archive = open_no_archive(source_path)
    try:
        for locator in archive.locators("no://lov/%/current.xml"):
            span = archive.resolve(locator)
            # ``locators()`` lists only locators that own a span, and a locator
            # always retains exactly one open span, so this is never None on a
            # well-formed archive; the guard is for the type checker.
            if span is not None and (latest is None or span.last_confirmed_at > latest):
                latest = span.last_confirmed_at
    finally:
        archive.close()
    if latest is None:
        raise NOConsolidationSnapshotError(
            f"Norway farchive {source_path} records no consolidated snapshot "
            "observation, so the scan's comparison horizon cannot be derived. "
            "Expected: at least one `no://lov/%/current.xml` artifact carrying "
            "an observation instant. Found: none. Fix: re-ingest the "
            "`gjeldende-lover` consolidation into this archive with "
            "`uv run lawvm no-ingest`, or point LAWVM_NORWAY_DB at a populated "
            "corpus. Do not substitute NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE "
            "here — that constant documents a legacy tar directory, and reusing "
            "it would make a mis-populated archive read as a legitimate one."
        )
    return latest.astimezone(timezone.utc).date().isoformat()


def no_current_locator(base_id: str) -> str:
    return f"no://lov/{base_id.removeprefix('no/lov/')}/current.xml"


def no_original_locator(base_id: str) -> str:
    return f"no://lov/{base_id.removeprefix('no/lov/')}/original.lti.xml"


def no_amendment_locator(source_id: str) -> str:
    return f"no://lovtid/{source_id.removeprefix('no/lovtid/')}/amendment.xml"


def no_forskrift_id_from_filename(member_name: str) -> str | None:
    # lawvm-regex: owning_parser derives the forskrift id from its archive member filename
    match = _NO_FORSKRIFT_FILENAME_RE.search(member_name)
    if not match:
        return None
    raw_date = match.group("date")
    return (
        f"no/forskrift/{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}-"
        f"{int(match.group('num'))}"
    )


def no_forskrift_locator(source_id: str) -> str:
    return f"no://forskrift/{source_id.removeprefix('no/forskrift/')}/original.lti.xml"


def no_forskrift_id_from_locator(locator: str) -> str | None:
    match = _NO_FORSKRIFT_LOCATOR_RE.fullmatch(locator.strip())
    if not match:
        return None
    return f"no/forskrift/{match.group('date')}"


def no_base_id_from_current_locator(locator: str) -> str | None:
    match = _NO_CURRENT_LOCATOR_RE.fullmatch(locator.strip())
    if not match:
        return None
    return f"no/lov/{match.group('date')}"


def no_base_id_from_original_locator(locator: str) -> str | None:
    match = _NO_ORIGINAL_LOCATOR_RE.fullmatch(locator.strip())
    if not match:
        return None
    return f"no/lov/{match.group('date')}"


def no_source_id_from_amendment_locator(locator: str) -> str | None:
    match = _NO_AMENDMENT_LOCATOR_RE.fullmatch(locator.strip())
    if not match:
        return None
    return f"no/lovtid/{match.group('date')}"


def repair_mojibake(text: str) -> str:
    """Best-effort repair for common UTF-8-as-Latin-1 mojibake in Lovdata metadata."""
    if not text or not any(marker in text for marker in ("Ã", "Â", "â")):
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if repaired == text:
        return text
    original_markers = sum(text.count(marker) for marker in ("Ã", "Â", "â"))
    repaired_markers = sum(repaired.count(marker) for marker in ("Ã", "Â", "â"))
    if repaired_markers > original_markers:
        return text
    return repaired


def _parse_no_header_root(html_bytes: bytes) -> etree._Element:
    root = None
    try:
        root = parse_corpus_xml(html_bytes, recover=True)
    except etree.XMLSyntaxError:
        root = None
    if root is None:
        parser = etree.HTMLParser(recover=True)
        root = etree.fromstring(html_bytes, parser=parser)
    return root


def parse_header_value(html_bytes: bytes, dd_class: str) -> str:
    root = _parse_no_header_root(html_bytes)
    values = root.xpath(
        f"string(//dd[contains(concat(' ', normalize-space(@class), ' '), ' {dd_class} ')][1])"
    )
    normalized = " ".join(str(values).replace("\xa0", " ").split()).strip()
    return repair_mojibake(normalized)


def declared_change_targets_from_root(root: etree._Element) -> NODeclaredChangeTargets:
    """Read the amendment targets Lovdata declares on a parsed act.

    The single reader of the ``changesToDocuments`` block: the grafter takes its
    sole-declared-ref ``default_base_id`` from it, the index its declared-target
    denominator. It reads the ``<li>`` elements, never
    :func:`parse_header_value` — that helper's XPath ``string()`` flattening
    concatenates the declared ids into one separator-free token.
    """
    block_present = False
    law_ids: list[str] = []
    for element in cast(list[etree._Element], root.xpath(_NO_CHANGES_TO_DOCUMENTS_XPATH)):
        if etree.QName(element).localname == "dd":
            block_present = True
        law_ids.extend(
            ref
            for ref in (
                normalize_lovdata_refid(
                    " ".join("".join(str(part) for part in li.itertext()).split())
                )
                for li in cast(list[etree._Element], element.xpath(".//li"))
            )
            if ref is not None
        )
    ordered = tuple(dict.fromkeys(law_ids))
    return NODeclaredChangeTargets(
        block_present=block_present,
        law_ids=ordered,
        unnumbered_law_ids=tuple(
            # lawvm-regex: owning_parser shape-tests an id for the unnumbered no/lov/<date> form
            law_id for law_id in ordered if _NO_UNNUMBERED_LAW_ID_RE.match(law_id)
        ),
    )


def declared_change_targets_from_amendment(html_bytes: bytes) -> NODeclaredChangeTargets:
    """Read the declared amendment targets from raw Lovdata amendment bytes."""
    return declared_change_targets_from_root(_parse_no_header_root(html_bytes))


def effective_date_from_amendment(html_bytes: bytes, source_date: str = "") -> NOEffectiveDate:
    """Classify one act's ``dateInForce`` metadata field.

    The field is read on two axes, not one. :class:`NOEffectiveStatus` answers
    "is there a resolved date, and where did it come from"; ``date_count`` and
    :class:`NOCommencementShape` answer "what did the field say". A field with
    no ISO date and delegated-commencement language is CONTINGENT — nothing is
    resolved. A field carrying BOTH is not: Lovdata writes staged commencement
    that way, and the corpus shows the leading date is real. Such an act stays
    DATED at ``min(dates)`` and is merely labelled ``STAGED_DELEGATED``, so the
    collapse is queryable instead of silent.
    """
    raw = parse_header_value(html_bytes, "dateInForce")
    dates = ISO_DATE_RE.findall(raw)
    lowered = raw.lower()
    delegated = any(marker in lowered for marker in NO_DELEGATED_COMMENCEMENT_MARKERS)
    if not dates:
        if not raw:
            return NOEffectiveDate(effective_status=NOEffectiveStatus.MISSING, raw_text="")
        if "straks" in lowered and source_date:
            return NOEffectiveDate(
                effective_status=NOEffectiveStatus.IMMEDIATE, effective_date=source_date, raw_text=raw
            )
        if delegated:
            return NOEffectiveDate(effective_status=NOEffectiveStatus.CONTINGENT, raw_text=raw)
        return NOEffectiveDate(effective_status=NOEffectiveStatus.UNKNOWN, raw_text=raw)
    return NOEffectiveDate(
        effective_status=NOEffectiveStatus.DATED,
        effective_date=min(dates),
        raw_text=raw,
        commencement_shape=(
            NOCommencementShape.STAGED_DELEGATED if delegated else NOCommencementShape.PLAIN
        ),
        date_count=len(dates),
    )


def archive_year_span(archive_path: Path) -> Optional[tuple[int, int]]:
    match = ARCHIVE_SPAN_RE.match(archive_path.name)
    if not match:
        return None
    start_year = int(match.group(1))
    end_year = int(match.group(2) or match.group(1))
    return start_year, end_year


def iter_lovtidend_archives(data_dir: Path) -> list[Path]:
    archives = []
    for path in data_dir.glob("lovtidend-avd1-*.tar.bz2"):
        span = archive_year_span(path)
        if span is None:
            continue
        archives.append((span, path))
    archives.sort(key=lambda item: (item[0][0], item[0][1], item[1].name))
    return [path for _span, path in archives]


def _iter_current_artifacts_from_dir(
    data_dir: Path,
    *,
    rejected_items: list[RejectedItem[str]] | None = None,
) -> Iterator[NOLocatedArtifact]:
    current_archive = data_dir / "gjeldende-lover.tar.bz2"
    if not current_archive.exists():
        return
    with tarfile.open(current_archive, "r:bz2") as tf:
        for member in tf.getmembers():
            if not member.name.endswith(".xml"):
                continue
            base_id = lovdata_filename_to_id(member.name)
            if base_id is None:
                continue
            try:
                payload = safe_tar_read(
                    tf, member, archive_path=current_archive.name
                )
            except ArchiveMemberTooLarge as exc:
                # §1.8 typed receipt (AGENTS.md §1.8): the helper appends a
                # ``RejectedItem`` to ``rejected_items`` when a sink is
                # threaded; otherwise it falls back to the structured stderr
                # receipt so the skip stays greppable. Never silently dropped.
                _no_record_archive_skip(rejected_items, exc=exc)
                continue
            if payload is None:
                continue
            yield NOLocatedArtifact(
                locator=no_current_locator(base_id),
                logical_id=base_id,
                source_name=current_archive.name,
                member_name=member.name,
                payload=payload,
            )


def _iter_lovtidend_members_from_dir(
    data_dir: Path,
    *,
    rejected_items: list[RejectedItem[str]] | None = None,
) -> Iterator[tuple[str | None, str | None, str, str, bytes]]:
    for archive_path in iter_lovtidend_archives(data_dir):
        with tarfile.open(archive_path, "r:bz2") as tf:
            for member in tf.getmembers():
                if not member.name.endswith(".xml"):
                    continue
                try:
                    payload = safe_tar_read(
                        tf, member, archive_path=archive_path.name
                    )
                except ArchiveMemberTooLarge as exc:
                    # §1.8 typed receipt (AGENTS.md §1.8) — see
                    # :func:`_no_record_archive_skip`. Falls back to the
                    # structured stderr receipt when the caller did not
                    # thread a sink.
                    _no_record_archive_skip(rejected_items, exc=exc)
                    continue
                if payload is None:
                    continue
                yield (
                    lovdata_filename_to_id(member.name),
                    lovdata_amendment_filename_to_id(member.name),
                    archive_path.name,
                    member.name,
                    payload,
                )


def _iter_original_lti_artifacts_from_dir(data_dir: Path) -> Iterator[NOLocatedArtifact]:
    for base_id, _source_id, archive_name, member_name, payload in _iter_lovtidend_members_from_dir(data_dir):
        if base_id is None:
            continue
        yield NOLocatedArtifact(
            locator=no_original_locator(base_id),
            logical_id=base_id,
            source_name=archive_name,
            member_name=member_name,
            payload=payload,
        )


def _iter_amendment_artifacts_from_dir(data_dir: Path) -> Iterator[NOLocatedArtifact]:
    for _base_id, source_id, archive_name, member_name, payload in _iter_lovtidend_members_from_dir(data_dir):
        if source_id is None:
            continue
        yield NOLocatedArtifact(
            locator=no_amendment_locator(source_id),
            logical_id=source_id,
            source_name=archive_name,
            member_name=member_name,
            payload=payload,
        )


def _iter_forskrift_artifacts_from_dir(data_dir: Path) -> Iterator[NOLocatedArtifact]:
    for _base_id, _source_id, archive_name, member_name, payload in _iter_lovtidend_members_from_dir(data_dir):
        source_id = no_forskrift_id_from_filename(member_name)
        if source_id is None:
            continue
        yield NOLocatedArtifact(
            locator=no_forskrift_locator(source_id),
            logical_id=source_id,
            source_name=archive_name,
            member_name=member_name,
            payload=payload,
        )


def iter_no_unmapped_lovtidend_xml_members(source_path: Path | None = None) -> Iterator[NOLocatedArtifact]:
    """Yield Lovtidend XML members whose filename cannot be mapped to a legal source id."""
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        return
    for base_id, source_id, archive_name, member_name, payload in _iter_lovtidend_members_from_dir(source_path):
        if base_id is not None or source_id is not None or no_forskrift_id_from_filename(member_name) is not None:
            continue
        yield NOLocatedArtifact(
            locator="",
            logical_id="",
            source_name=archive_name,
            member_name=member_name,
            payload=payload,
        )


def iter_no_unmapped_current_xml_members(
    source_path: Path | None = None,
    *,
    rejected_items: list[RejectedItem[str]] | None = None,
) -> Iterator[NOLocatedArtifact]:
    """Yield current-law XML members whose filename cannot be mapped to a law id."""
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        return
    current_archive = source_path / "gjeldende-lover.tar.bz2"
    if not current_archive.exists():
        return
    with tarfile.open(current_archive, "r:bz2") as tf:
        for member in tf.getmembers():
            if not member.name.endswith(".xml"):
                continue
            if lovdata_filename_to_id(member.name) is not None:
                continue
            try:
                payload = safe_tar_read(
                    tf, member, archive_path=current_archive.name
                )
            except ArchiveMemberTooLarge as exc:
                # §1.8 typed receipt (AGENTS.md §1.8) — see
                # :func:`_no_record_archive_skip`.
                _no_record_archive_skip(rejected_items, exc=exc)
                continue
            if payload is None:
                continue
            yield NOLocatedArtifact(
                locator="",
                logical_id="",
                source_name=current_archive.name,
                member_name=member.name,
                payload=payload,
            )


def _iter_artifacts_from_farchive(
    db_path: Path,
    *,
    pattern: str,
    id_from_locator: Any,
) -> Iterator[NOLocatedArtifact]:
    archive = open_no_archive(db_path, readonly=True)
    try:
        for locator in archive.locators(pattern):
            logical_id = id_from_locator(locator)
            if logical_id is None:
                continue
            payload = archive.get(locator)
            if payload is None:
                continue
            yield NOLocatedArtifact(
                locator=locator,
                logical_id=logical_id,
                source_name=db_path.name,
                member_name=locator,
                payload=payload,
            )
    finally:
        archive.close()


def iter_no_current_artifacts(source_path: Path | None = None) -> Iterator[NOLocatedArtifact]:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        yield from _iter_artifacts_from_farchive(
            source_path,
            pattern="no://lov/%/current.xml",
            id_from_locator=no_base_id_from_current_locator,
        )
        return
    yield from _iter_current_artifacts_from_dir(source_path)


def iter_no_original_lti_artifacts(source_path: Path | None = None) -> Iterator[NOLocatedArtifact]:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        yield from _iter_artifacts_from_farchive(
            source_path,
            pattern="no://lov/%/original.lti.xml",
            id_from_locator=no_base_id_from_original_locator,
        )
        return
    yield from _iter_original_lti_artifacts_from_dir(source_path)


def iter_no_amendment_artifacts(source_path: Path | None = None) -> Iterator[NOLocatedArtifact]:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        yield from _iter_artifacts_from_farchive(
            source_path,
            pattern="no://lovtid/%/amendment.xml",
            id_from_locator=no_source_id_from_amendment_locator,
        )
        return
    yield from _iter_amendment_artifacts_from_dir(source_path)


def iter_no_forskrift_artifacts(source_path: Path | None = None) -> Iterator[NOLocatedArtifact]:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        yield from _iter_artifacts_from_farchive(
            source_path,
            pattern="no://forskrift/%/original.lti.xml",
            id_from_locator=no_forskrift_id_from_locator,
        )
        return
    yield from _iter_forskrift_artifacts_from_dir(source_path)


def load_no_current_bytes(base_id: str, source_path: Path | None = None) -> bytes | None:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        archive = open_no_archive(source_path, readonly=True)
        try:
            return archive.get(no_current_locator(base_id))
        finally:
            archive.close()
    for artifact in _iter_current_artifacts_from_dir(source_path):
        if artifact.logical_id == base_id:
            return artifact.payload
    return None


def load_no_original_lti_bytes(base_id: str, source_path: Path | None = None) -> bytes | None:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        archive = open_no_archive(source_path, readonly=True)
        try:
            return archive.get(no_original_locator(base_id))
        finally:
            archive.close()
    for artifact in _iter_original_lti_artifacts_from_dir(source_path):
        if artifact.logical_id == base_id:
            return artifact.payload
    return None


def load_no_amendment_bytes(source_id: str, source_path: Path | None = None) -> bytes | None:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        archive = open_no_archive(source_path, readonly=True)
        try:
            return archive.get(no_amendment_locator(source_id))
        finally:
            archive.close()
    for artifact in _iter_amendment_artifacts_from_dir(source_path):
        if artifact.logical_id == source_id:
            return artifact.payload
    return None


def load_no_amendment_artifact_bytes(
    source_id: str,
    archive_name: str,
    member_name: str,
    source_path: Path | None = None,
    *,
    rejected_items: list[RejectedItem[str]] | None = None,
) -> bytes | None:
    source_path = resolve_no_source_path(source_path)
    if not archive_name or not member_name:
        return load_no_amendment_bytes(source_id, source_path)
    if is_no_farchive_path(source_path):
        archive = open_no_archive(source_path, readonly=True)
        try:
            locator = member_name if member_name.startswith("no://") else no_amendment_locator(source_id)
            return archive.get(locator)
        finally:
            archive.close()
    archive_path = source_path / archive_name
    if not archive_path.exists():
        return None
    with tarfile.open(archive_path, "r:bz2") as tf:
        for member in tf.getmembers():
            if member.name != member_name:
                continue
            try:
                payload = safe_tar_read(
                    tf, member, archive_path=archive_path.name
                )
            except ArchiveMemberTooLarge as exc:
                # Visible §1.8 receipt (AGENTS.md §1.8) — the helper appends
                # a ``RejectedItem`` to ``rejected_items`` when a sink is
                # threaded, else falls back to the structured stderr receipt.
                # Returns None so the loader treats an oversized member like
                # an absent one (the over-retention principle — §0 never
                # fabricate) while the receipt stays audible.
                _no_record_archive_skip(rejected_items, exc=exc)
                return None
            if payload is None:
                return None
            return payload
    return None


# §§ 1.9 / 1.10 — module-scope IR-operative-content predicate.
#
# The previous shape was a nested closure inside ``load_no_current_law_ids``
# with this membership test:
#
#     if getattr(node, "kind", "") in {"section", "subsection", "item", "sentence"}:
#
# which silently returned False on every IRNode whose ``kind`` is an
# ``IRNodeKind`` enum member (enum members don't equal their string values).
# The OR-clause's right side (``_payload_has_operative_content``) was the
# sole authority — the IR walk was dead code, an invisible §1.10 heuristic
# that lied about whether the IR carried operative content.
#
# The fix uses ``kind_str`` coercion (the same pattern as
# ``_no_kind_value`` in verify.py:269); both enum and plain-str kinds now
# participate. Hoisted to module scope so the predicate is unit-testable
# directly against synthetic IRNodes.
_NO_OPERATIVE_KINDS: frozenset[str] = frozenset(
    {"section", "subsection", "item", "sentence"}
)


def _has_operative_content(node: Any) -> bool:
    """Return True if *node* (or any descendant) carries operative section content.

    A node is operative when its ``kind`` is one of the leaf-bearing legal-unit
    kinds (section / subsection / item / sentence) AND it has either populated
    text or non-empty children. The IR-walk recurses into any non-leaf node
    (the body, chapter, …) so the recursive case remains the authority when
    the inspected level is a container, not a leaf.

    Honors both IRNode with ``IRNodeKind`` enum kind and any legacy str-typed
    kind — coercion goes through :func:`lawvm.core.ir_helpers.kind_str`, the
    shared canonical-string projection (mirroring ``_no_kind_value`` in
    verify.py).
    """
    kind_value = kind_str(getattr(node, "kind", ""))
    if kind_value in _NO_OPERATIVE_KINDS:
        if getattr(node, "text", "") or getattr(node, "children", []):
            return True
    return any(_has_operative_content(child) for child in getattr(node, "children", []))


def load_no_current_law_ids(
    source_path: Path | None = None,
    *,
    diagnostics_out: list[dict[str, Any]] | None = None,
) -> set[str]:
    from lawvm.norway.grafter import parse_no_statute

    def _payload_has_operative_content(payload: bytes) -> bool:
        text = payload.decode("utf-8", errors="ignore")
        if "legalArticleHeader" not in text:
            return False
        return any(marker in text for marker in ("legalP", "legalArticleText", "<p>", "<P>"))

    current_ids: set[str] = set()
    for artifact in iter_no_current_artifacts(source_path):
        try:
            statute = parse_no_statute(artifact.payload, artifact.logical_id)
        except Exception as exc:
            has_marker_fallback = _payload_has_operative_content(artifact.payload)
            if diagnostics_out is not None:
                rule_id = (
                    "no_current_law_id_parse_marker_fallback_used"
                    if has_marker_fallback
                    else "no_current_law_id_parse_skipped"
                )
                diagnostics_out.append(
                    diagnostic_detail(
                        rule_id=rule_id,
                        phase="parse",
                        family="source_pathology",
                        reason=(
                            "Norway current-law ID loader retained an artifact via operative marker fallback "
                            "after statute parsing failed."
                            if has_marker_fallback
                            else "Norway current-law ID loader skipped an artifact because statute parsing failed."
                        ),
                        blocking=True,
                        strict_disposition="block",
                        quirks_disposition=QuirksDisposition.RECORD,
                        statute_id=artifact.logical_id,
                        locator=artifact.locator,
                        source_name=artifact.source_name,
                        member_name=artifact.member_name,
                        exception_type=type(exc).__name__,
                        error=str(exc),
                        retained_by_marker_fallback=has_marker_fallback,
                    )
                )
            if has_marker_fallback:
                current_ids.add(artifact.logical_id)
            continue
        if _has_operative_content(statute.body) or _payload_has_operative_content(artifact.payload):
            current_ids.add(artifact.logical_id)
    return current_ids


def load_available_lti_law_ids(source_path: Path | None = None) -> set[str]:
    """Return canonical ``no/lov/...`` ids whose original LTI artifact exists locally."""
    return {artifact.logical_id for artifact in iter_no_original_lti_artifacts(source_path)}


def load_no_current_law_titles(
    source_path: Path | None = None,
    *,
    diagnostics_out: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    from lawvm.norway.grafter import parse_no_statute

    titles: dict[str, str] = {}
    for artifact in iter_no_current_artifacts(source_path):
        try:
            titles[artifact.logical_id] = parse_no_statute(artifact.payload, artifact.logical_id).title
        except Exception as exc:
            if diagnostics_out is not None:
                diagnostics_out.append(
                    diagnostic_detail(
                        rule_id="no_current_law_title_parse_skipped",
                        phase="parse",
                        family="source_pathology",
                        reason="Norway current-law title extraction skipped an artifact because statute parsing failed.",
                        blocking=True,
                        strict_disposition="block",
                        quirks_disposition=QuirksDisposition.RECORD,
                        statute_id=artifact.logical_id,
                        locator=artifact.locator,
                        source_name=artifact.source_name,
                        member_name=artifact.member_name,
                        exception_type=type(exc).__name__,
                        error=str(exc),
                    )
                )
            continue
    return titles


def no_source_metadata(source_path: Path | None = None) -> dict[str, Any]:
    source_path = resolve_no_source_path(source_path)
    if is_no_farchive_path(source_path):
        if not source_path.exists():
            return {"source_kind": "farchive", "path": str(source_path), "exists": False}
        stat = source_path.stat()
        return {
            "source_kind": "farchive",
            "path": str(source_path),
            "exists": True,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }
    current_archive = source_path / "gjeldende-lover.tar.bz2"
    archive_paths = ([current_archive] if current_archive.exists() else []) + iter_lovtidend_archives(source_path)
    archive_metadata = {
        path.name: {"size": int(path.stat().st_size), "mtime_ns": int(path.stat().st_mtime_ns)}
        for path in archive_paths
    }
    return {
        "source_kind": "dir",
        "path": str(source_path),
        "exists": source_path.exists(),
        "archive_names": [path.name for path in archive_paths],
        "archive_metadata": archive_metadata,
    }


def _no_archive_member_locator(artifact: NOLocatedArtifact) -> str:
    return f"{artifact.source_name}:{artifact.member_name}"


def _no_ingest_duplicate_locator_source_lane_evidence(
    *,
    artifact: NOLocatedArtifact,
    identical_payloads: bool,
    existing_payload: bytes,
) -> dict[str, Any]:
    return SourceLaneSelectionEvidence(
        rule_id="no_acquisition_duplicate_logical_locator",
        phase="acquisition",
        reason=(
            "Norway Farchive ingest retained the existing byte-identical source witness."
            if identical_payloads
            else "Norway Farchive ingest found a conflicting duplicate source witness and retained the existing lane."
        ),
        selected_lane="existing_farchive_locator",
        selected_locator=artifact.locator,
        attempts=(
            SourceLaneAttempt(
                lane="existing_farchive_locator",
                locator=artifact.locator,
                lane_attempt_status="selected_existing_identical" if identical_payloads else "selected_existing_conflict",
                detail={
                    "logical_id": artifact.logical_id,
                    "payload_digest": hashlib.sha256(existing_payload).hexdigest(),
                },
            ),
            SourceLaneAttempt(
                lane="incoming_archive_member",
                locator=_no_archive_member_locator(artifact),
                lane_attempt_status="duplicate_identical_not_stored" if identical_payloads else "blocked_conflicting_duplicate",
                detail={
                    "logical_id": artifact.logical_id,
                    "logical_locator": artifact.locator,
                    "payload_digest": hashlib.sha256(artifact.payload).hexdigest(),
                },
            ),
        ),
        blocking=True,
        strict_disposition="block",
        quirks_disposition=QuirksDisposition.SELECT_EXISTING_IDENTICAL if identical_payloads else QuirksDisposition.BLOCK,
        detail={
            "logical_id": artifact.logical_id,
            "logical_locator": artifact.locator,
            "identical_payloads": identical_payloads,
        },
    ).to_diagnostic_detail()


def ingest_no_public_archives(
    source_dir: Path,
    db_path: Path | None = None,
    *,
    skip_existing: bool = False,
) -> dict[str, object]:
    """Hydrate a Norway Farchive from local public Lovdata tarballs."""
    db_path = db_path or DEFAULT_NORWAY_DB
    archive = open_no_archive(db_path, readonly=False)
    skipped_existing_entries: list[dict[str, str]] = []
    skipped_unmapped_entries: list[dict[str, Any]] = []
    duplicate_locator_entries: list[dict[str, Any]] = []
    report: dict[str, object] = {
        "source_dir": str(source_dir),
        "db_path": str(db_path),
        "current_locators_stored": 0,
        "original_locators_stored": 0,
        "amendment_locators_stored": 0,
        "forskrift_locators_stored": 0,
        "skipped_existing": 0,
        "skipped_existing_entries": skipped_existing_entries,
        "skipped_unmapped": 0,
        "skipped_unmapped_entries": skipped_unmapped_entries,
        "duplicate_locator_count": 0,
        "duplicate_locator_entries": duplicate_locator_entries,
    }

    def _record_skipped_existing(artifact: NOLocatedArtifact, *, kind: str) -> None:
        report["skipped_existing"] = cast(int, report["skipped_existing"]) + 1
        skipped_existing_entries.append(
            {
                "rule_id": "no_ingest_existing_locator_skipped",
                "phase": "acquisition",
                "family": "transport_cleanup",
                "reason": "archive already contains locator and skip_existing was enabled",
                "kind": kind,
                "locator": artifact.locator,
                "logical_id": artifact.logical_id,
                "source_name": artifact.source_name,
                "member_name": artifact.member_name,
            }
        )

    def _record_skipped_unmapped(artifact: NOLocatedArtifact, *, kind: str) -> None:
        report["skipped_unmapped"] = cast(int, report["skipped_unmapped"]) + 1
        skipped_unmapped_entries.append(
            diagnostic_detail(
                rule_id="no_ingest_unmapped_xml_member",
                phase="acquisition",
                family="source_pathology",
                reason="Norway Lovdata XML member filename could not be mapped to a legal source id",
                blocking=True,
                strict_disposition="block",
                quirks_disposition=QuirksDisposition.RECORD,
                kind=kind,
                locator=artifact.locator,
                logical_id=artifact.logical_id,
                source_name=artifact.source_name,
                member_name=artifact.member_name,
            )
        )

    def _record_duplicate_locator(
        artifact: NOLocatedArtifact,
        *,
        kind: str,
        existing_payload: bytes,
    ) -> None:
        identical_payloads = existing_payload == artifact.payload
        report["duplicate_locator_count"] = cast(int, report["duplicate_locator_count"]) + 1
        duplicate_locator_entries.append(
            diagnostic_detail(
                rule_id="no_acquisition_duplicate_logical_locator",
                phase="acquisition",
                family="source_pathology",
                reason=(
                    "Norway Farchive ingest found a byte-identical duplicate logical source locator; "
                    "the existing witness was retained."
                    if identical_payloads
                    else "Norway Farchive ingest found a conflicting duplicate logical source locator; "
                    "the existing witness was retained and the new payload was not stored."
                ),
                blocking=True,
                strict_disposition="block",
                quirks_disposition=QuirksDisposition.SELECT_EXISTING_IDENTICAL if identical_payloads else QuirksDisposition.BLOCK,
                kind=kind,
                locator=artifact.locator,
                logical_id=artifact.logical_id,
                source_name=artifact.source_name,
                member_name=artifact.member_name,
                existing_payload_digest=hashlib.sha256(existing_payload).hexdigest(),
                new_payload_digest=hashlib.sha256(artifact.payload).hexdigest(),
                identical_payloads=identical_payloads,
                source_lane_selection=_no_ingest_duplicate_locator_source_lane_evidence(
                    artifact=artifact,
                    identical_payloads=identical_payloads,
                    existing_payload=existing_payload,
                ),
            )
        )

    try:
        for artifact in iter_no_unmapped_current_xml_members(source_dir):
            _record_skipped_unmapped(artifact, kind="current")
        for artifact in iter_no_unmapped_lovtidend_xml_members(source_dir):
            _record_skipped_unmapped(artifact, kind="lovtidend")
        for artifact in _iter_current_artifacts_from_dir(source_dir):
            if skip_existing and archive.has(artifact.locator):
                _record_skipped_existing(artifact, kind="current")
                continue
            if archive.has(artifact.locator):
                _record_duplicate_locator(
                    artifact,
                    kind="current",
                    existing_payload=archive.get(artifact.locator) or b"",
                )
                continue
            archive.store(
                artifact.locator,
                artifact.payload,
                storage_class="xml",
                metadata={"source_name": artifact.source_name, "member_name": artifact.member_name, "kind": "current"},
            )
            report["current_locators_stored"] += 1
        for artifact in _iter_original_lti_artifacts_from_dir(source_dir):
            if skip_existing and archive.has(artifact.locator):
                _record_skipped_existing(artifact, kind="original")
                continue
            if archive.has(artifact.locator):
                _record_duplicate_locator(
                    artifact,
                    kind="original",
                    existing_payload=archive.get(artifact.locator) or b"",
                )
                continue
            archive.store(
                artifact.locator,
                artifact.payload,
                storage_class="xml",
                metadata={"source_name": artifact.source_name, "member_name": artifact.member_name, "kind": "original"},
            )
            report["original_locators_stored"] += 1
        for artifact in _iter_amendment_artifacts_from_dir(source_dir):
            if skip_existing and archive.has(artifact.locator):
                _record_skipped_existing(artifact, kind="amendment")
                continue
            if archive.has(artifact.locator):
                _record_duplicate_locator(
                    artifact,
                    kind="amendment",
                    existing_payload=archive.get(artifact.locator) or b"",
                )
                continue
            archive.store(
                artifact.locator,
                artifact.payload,
                storage_class="xml",
                metadata={"source_name": artifact.source_name, "member_name": artifact.member_name, "kind": "amendment"},
            )
            report["amendment_locators_stored"] += 1
        for artifact in _iter_forskrift_artifacts_from_dir(source_dir):
            if skip_existing and archive.has(artifact.locator):
                _record_skipped_existing(artifact, kind="forskrift")
                continue
            if archive.has(artifact.locator):
                _record_duplicate_locator(
                    artifact,
                    kind="forskrift",
                    existing_payload=archive.get(artifact.locator) or b"",
                )
                continue
            archive.store(
                artifact.locator,
                artifact.payload,
                storage_class="xml",
                metadata={
                    "source_name": artifact.source_name,
                    "member_name": artifact.member_name,
                    "kind": "forskrift",
                    "replay_authorized": False,
                },
            )
            report["forskrift_locators_stored"] += 1
    finally:
        archive.close()
    return report
