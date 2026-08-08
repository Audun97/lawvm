"""Typed Norsk Lovtidend commencement-instrument surface.

Parses commencement instruments into typed candidates, and owns the
execution-authorization gate that re-dates unresolved amendment acts from a
whole-act, single-date instrument. Parsing itself still authorizes nothing: only
a candidate that passes every conjunct of the gate re-dates the act it cites.

W-39 adds the gate's second, narrower route: a PART-SCOPED authorization. A
staged multi-part amending act is commenced one *romertall* at a time
("Delvis/Delt ikraftsetting"), so no single instrument can ever satisfy
``whole_act_scope`` and the act stays contingent even when every part it
contains has in fact been commenced. The part route authorizes the act's ops
for ONE law — the law of the one part the instrument's own ``Endrer`` header
names — and leaves every other part of the act exactly as unresolved as it was.
Its scope proof is structural, not textual: see
:class:`NOCommencementAuthorizationConjunct`.

W-47 adds the gate's third route, for the pairs the W-39 matcher refuses
because the ``Endrer`` header spans SEVERAL parts. The census behind it settled
two facts that between them decide the route's whole shape:

* the header is a faithful PART-to-LAW map — in all 168 refused pairs the
  spanned parts amend exactly the laws the header names, in both directions;
* the header is NOT a faithful statement of the INSTRUMENT's scope — eleven of
  those 168 have operative text commencing strictly less than the header names
  ("Loven del I trer i kraft" against a two-part header; "Romertall II, III og
  IV" against a I/III/IV header; "Del VI punkt 1" against a I-V header).

So a spanning header licenses nothing on its own. What licenses the multi-part
grant is the instrument's own text saying the WHOLE act commences: then dating
the header's parts is dating a SUBSET of what the text commences, and the header
supplies the part-to-law mapping those dates are keyed by. Deliberately NOT
routed through ``whole_act_scope``: that would re-date the act wholesale,
including parts the header never named, and move its act-level status. See
:class:`NOCommencementMultiPartAuthorizationConjunct`.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, cast

from lxml import etree

from lawvm.core.diagnostic_records import diagnostic_detail
from lawvm.core.quirks_disposition import QuirksDisposition
from lawvm.core.regex_safety import compile_classifier_regex
from lawvm.core.xml_parse import parse_corpus_xml

NO_COMMENCEMENT_INSTRUMENT_RULE = "no_lovtidend_commencement_instrument_candidate"
NO_COMMENCEMENT_SCOPE_UNRESOLVED = "no_lovtidend_commencement_scope_unresolved"
NO_COMMENCEMENT_INSTRUMENT_PARSE_FAILED = "no_lovtidend_commencement_instrument_parse_failed"
NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID = "no_lovtidend_commencement_instrument_coverage_invalid"
NO_COMMENCEMENT_EXECUTION_AUTHORIZED = "no_lovtidend_commencement_execution_authorized"
NO_COMMENCEMENT_EXECUTION_REFUSED = "no_lovtidend_commencement_execution_refused"
NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT = "no_lovtidend_commencement_execution_date_conflict"
NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_part_execution_authorized"
)
NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT = (
    "no_lovtidend_commencement_part_execution_date_conflict"
)
NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_multi_part_execution_authorized"
)

_WS_RE = re.compile(r"\s+")
_LAW_REF_RE = re.compile(r"(?:^|[/\s])lov/(?P<date>\d{4}-\d{2}-\d{2})-(?P<num>\d+)(?:$|[/\s#?])")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_COMMENCEMENT_TITLE_RE = compile_classifier_regex(
    r"\b(?:ikraftsetting|ikraftsetjing|ikrafttredelse)\b",
    re.IGNORECASE,
    classifier_id="no.lovtidend.commencement_instrument_title",
)
_LAW_COMMENCEMENT_RE = compile_classifier_regex(
    r"\b(?:loven|lova)\s+trer\s+i\s+(?:kraft|verk)\b",
    re.IGNORECASE,
    classifier_id="no.lovtidend.law_commencement_clause",
)
# The section labels a commencement instrument's operative text names. Shapes
# attested in the 246 exact part matches: ``§ 16``, ``§ 14a``, ``§ 20-14``,
# ``§ 4 a``. The label body is the grafter's own section-label alphabet; the
# comparison downstream is set equality, so a shape this misses shows up as a
# refusal, never as an over-authorization.
# The two label shapes are spelled as an alternation rather than as an optional
# ``-<n>`` suffix group: a quantifier nested inside an optional group is exactly
# what the classifier-safety lint refuses, and the chapter-numbered form is
# listed FIRST so ``§ 20-14`` never matches as ``20``.
_COMMENCED_SECTION_RE = compile_classifier_regex(
    r"§+ ?([0-9]+-[0-9]+ ?[a-zA-Z]?|[0-9]+ ?[a-zA-Z]?)",
    classifier_id="no.lovtidend.commenced_section_label",
)
_WHOLE_ACT_RE = compile_classifier_regex(
    r"^(?:denne )?(?:loven|lova) trer i (?:kraft|verk)\b[^§]{0,400}$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.whole_act_commencement",
)
# W-47. The multi-part route's text guard, in two halves that must BOTH hold.
#
# Half one, ``_SUBDIVISION_SCOPE_RE``, is purely REFUSING: any of these tokens
# in the operative text means the instrument may be scoping to a proper part of
# the act, and the pair refuses. Nothing in it can ever accept. The list is the
# subdivision vocabulary Norwegian commencement instruments actually use
# (romertall part, punkt, avsnitt, kapittel, bokstav, ledd, the section sign)
# plus the negative/exception phrases that carve a hole in an otherwise
# whole-act sentence ("med unntak av", "settes ikke i kraft"). Measured over the
# 168 spanning-header pairs it refuses 96, including all eleven whose text is
# PROVEN to commence less than their header names.
_SUBDIVISION_SCOPE_RE = compile_classifier_regex(
    r"(?:§"
    r"|\bdel(?:en|ene|er|e|s)?\b"
    r"|\bromertall\b|\bromartal\b|\bromartall\b"
    r"|\bpunkt(?:um|et|a)?\b"
    r"|\bavsnitt(?:et|a)?\b"
    r"|\bkapit(?:tel|let|la|lene|el)\b"
    r"|\bbokstav(?:en|ene|er)?\b"
    r"|\bledd(?:et)?\b"
    r"|\bmed\s+unntak\b|\bunntatt\b|\bikke\s+i\s+kraft\b"
    r"|\bfor\s+så\s+vidt\b|\bbortsett\s+fra\b|\bmed\s+mindre\b)",
    re.IGNORECASE,
    classifier_id="no.lovtidend.commencement_subdivision_scope",
)
_COMMENCEMENT_VERB = (
    r"(?:trer\s+i\s+kraft|trer\s+ikraft|trer\s+i\s+verk|tek\s+til\s+å\s+gjelde"
    r"|gjelder\s+fra|gjelder\s+frå|gjeld\s+frå|skal\s+gjelde"
    r"|blir\s+satt\s+i\s+kraft|blir\s+sett\s+i\s+kraft|blir\s+sette\s+i\s+kraft"
    r"|settes\s+i\s+kraft|setjast\s+i\s+kraft|iverksettes)"
)
# Half two is the POSITIVE half, and it exists for the one narrowing half one
# cannot see: an instrument scoping by LAW rather than by subdivision
# ("Endringene i folketrygdloven trer i kraft" under a three-law header). The
# subject of the commencement clause must therefore be the ACT, in one of two
# closed shapes — a generic act-word IMMEDIATELY before the verb (the adjacency
# is the whole point; "Endringene i X-loven trer" has a preposition phrase in
# between and fails), or a sentence-initial citation of the amending act itself.
_WHOLE_ACT_SUBJECT_RE = compile_classifier_regex(
    r"\b(?:loven|lova|lovens|endringsloven|endringslova|endringslovene"
    r"|lovendringene|lovendringane|endringene|endringane)\s+" + _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.whole_act_commencement_subject",
)
_CITED_ACT_SUBJECT_RE = compile_classifier_regex(
    r"(?:^|(?<=[.:])\s)lov\b[^§]{0,400}?\bom\s+endring(?:er|ar|a)?\b[^§]{0,400}?"
    + _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.cited_act_commencement_subject",
)


class NOCommencementParseStatus(StrEnum):
    CANDIDATE = "candidate"
    BENIGN_NOT_COMMENCEMENT = "benign_not_commencement"
    BLOCKED_UNRESOLVED = "blocked_unresolved"


class NOCommencementScopeStatus(StrEnum):
    WHOLE_ACT = "whole_act"
    UNRESOLVED = "unresolved"


class NOCommencementAuthorizationConjunct(StrEnum):
    """The conjuncts an (instrument, act) pair must satisfy to re-date the act."""

    PARSE_STATUS_CANDIDATE = "parse_status_candidate"
    WHOLE_ACT_SCOPE = "whole_act_scope"
    SINGLE_EFFECTIVE_DATE = "single_effective_date"


class NOCommencementPartAuthorizationConjunct(StrEnum):
    """The conjuncts an (instrument, act) pair must satisfy to date ONE part.

    Deliberately a separate closed set from the whole-act conjuncts: the two
    routes prove different things, and a refusal that lists both sets' names in
    one field would say nothing about which route was even attempted.
    """

    SINGLE_EFFECTIVE_DATE = "single_effective_date"
    """The instrument's ``dateInForce`` carries exactly one ISO date."""

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse failed for no reason other than whole-act scope.

    A ``blocked_unresolved`` parse has exactly three causes: no affected law, no
    effective date, or no whole-act scope proof. The first is excluded because
    the pair exists only when the instrument cites an offered act; the second by
    ``SINGLE_EFFECTIVE_DATE``. What is left is an instrument that IS a
    commencement and names its act, and whose only defect is that it commences
    less than the whole act — which is precisely the population this route is
    for. A genuine parse failure (malformed XML) never reaches here at all.
    """

    INSTRUMENT_DECLARES_CHANGED_LAWS = "instrument_declares_changed_laws"
    """The instrument's own ``Endrer`` (``changesToDocuments``) block is present
    and non-empty. This is the scope evidence; without it there is nothing to
    match a part against, and the instrument stays evidence."""

    ACT_PART_LAW_MAP_INJECTIVE = "act_part_law_map_injective"
    """No law is amended by two of the act's parts.

    A law appearing in two parts makes "the part this instrument commences"
    undecidable from the ``Endrer`` header alone — the same ambiguity W-24's
    part resolver refuses when a part's ``document-change`` wrappers disagree.
    """

    ACT_BINDINGS_INSIDE_PART_MAP = "act_bindings_inside_part_map"
    """Every law the act actually binds is the law of some part.

    Without this, an op bound by a carried-over base id from a part that
    resolved no law of its own could be dated by a part authorization that never
    covered it.
    """

    ENDRER_MATCHES_ONE_PART_EXACTLY = "endrer_matches_one_part_exactly"
    """The ``Endrer`` law set equals the law set of exactly one part.

    Equality in BOTH directions: every named law lives in that part, and the
    part amends no law the header omits. A header spanning two parts, or naming
    a law the act's structure cannot place, refuses.
    """

    WHOLE_PART_SCOPE = "whole_part_scope"
    """The instrument commences the whole part, not a slice of it.

    The ``Endrer`` match proves WHICH part; it does not prove HOW MUCH of it. A
    "Delvis ikraftsetting" that names individual sections inside the part
    commences less than the part, and dating the part's whole op stream from it
    would apply ops that are not yet in force. Proof, mirroring ``_WHOLE_ACT_RE``'s
    own ``[^§]{0,400}`` guard one level down: the operative text names no section
    at all, or the sections it names are exactly the sections the part's ops
    target. Measured over the 246 exact ``Endrer``-to-part matches in the corpus,
    122 name no section and 15 name the part's own section set; the other 109 are
    genuinely narrower and are refused here.
    """


class NOCommencementMultiPartAuthorizationConjunct(StrEnum):
    """The conjuncts an (instrument, act) pair must satisfy to date SEVERAL parts.

    A third closed set beside the whole-act and single-part ones, for the same
    reason those two are separate: naming a conjunct only says something if the
    reader knows which route was attempted. Five of these are the single-part
    route's conjuncts unchanged — the part-structure requirements do not weaken
    when more than one part is in play — and three are this route's own.
    """

    SINGLE_EFFECTIVE_DATE = "single_effective_date"
    """The instrument's ``dateInForce`` carries exactly one ISO date."""

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse failed for no reason other than whole-act scope."""

    INSTRUMENT_DECLARES_CHANGED_LAWS = "instrument_declares_changed_laws"
    """The instrument's own ``Endrer`` block is present and non-empty."""

    ACT_PART_LAW_MAP_INJECTIVE = "act_part_law_map_injective"
    """No law is amended by two of the act's parts."""

    ACT_BINDINGS_INSIDE_PART_MAP = "act_bindings_inside_part_map"
    """Every law the act actually binds is the law of some part.

    One-directional, as at W-39: a part may resolve a law the act's lowered ops
    never bind, and a grant for such a part dates nothing at all, because
    ``effective_date_for_base`` is only ever asked about a law in ``base_ids``.
    Measured, 27 of this route's 260 grants are inert that way (2 of W-39's 123
    already were). They are left in rather than filtered, so both routes behave
    alike and the commencement fact stays receipted; the count is pinned.
    """

    ENDRER_MATCHES_A_PART_SET_EXACTLY = "endrer_matches_a_part_set_exactly"
    """The ``Endrer`` law set equals the union of the law sets of the parts it
    spans, and that span is more than one part.

    The generalization of ``ENDRER_MATCHES_ONE_PART_EXACTLY``, and equally
    two-directional: every named law lives in one of the spanned parts, and no
    spanned part amends a law the header omits. Requiring MORE than one part is
    what keeps the two routes disjoint — a single-part header is the W-39
    route's business and is never re-examined here.

    Honest note on its strength today: given ``ACT_PART_LAW_MAP_INJECTIVE`` and
    an evidence model where a part resolves at most ONE law, the reverse
    direction is structurally implied, and the census bears that out — the
    reverse check refuses 0 of the 168 pairs, at either granularity. It is
    asserted rather than dropped because the implication is a property of the
    evidence shape, not of the law: the day ``part_law_ids`` carries several
    laws per part, this is the conjunct that stops a header naming one of them
    from dating all of them.
    """

    WHOLE_ACT_OPERATIVE_TEXT = "whole_act_operative_text"
    """The instrument's operative text commences the act as a WHOLE.

    This is the conjunct that does the licensing work, because the header alone
    is not evidence of the instrument's scope — measured, eleven of the 168
    spanning-header pairs commence strictly less than their header names. Proof
    has two halves: the text names no subdivision of the act anywhere and
    carries no negative/exception phrase (``_SUBDIVISION_SCOPE_RE``, refusing
    only), and the subject of its commencement clause is the act rather than one
    of the laws the act amends (``_WHOLE_ACT_SUBJECT_RE`` /
    ``_CITED_ACT_SUBJECT_RE``). Given both, what the instrument commences is a
    superset of the parts the header names, so dating exactly those parts claims
    strictly less than the instrument says.
    """

    WHOLE_PART_SCOPE_PER_PART = "whole_part_scope_per_part"
    """Every spanned part passes the single-part route's ``whole_part_scope``.

    Vacuous as things stand — ``WHOLE_ACT_OPERATIVE_TEXT`` refuses any text
    containing ``§`` at all, so the named-section set is always empty here and
    the check passes for every part. It is asserted per part rather than assumed
    so that the day the text guard is loosened, a slice named inside a spanned
    part refuses the part it is inside instead of silently dating it.
    """

    ACT_HAS_NO_LATER_INSTRUMENT = "act_has_no_later_instrument"
    """No other instrument commences anything of this act at a LATER date.

    The route's claim is that the act came into force as a whole on this date.
    Another instrument commencing (or re-commencing) part of the same act
    afterwards is direct evidence that it did not, whatever that instrument's
    own scope, so the whole match refuses. Not a hypothetical guard: without it
    the W-39 soundness probe FIRES on ``no/lovtid/2019-12-06-76``, whose
    whole-act instrument ``2019-12-20-1913`` is contradicted first by
    ``2020-01-10-15`` revoking the commencement of verdipapirhandelloven
    § 3-1 første ledd and then by ``2021-01-29-266`` re-commencing del I on
    2021-03-01 — a 15-month early application of that part's ops.
    """


class NOCommencementInstrumentCoverageError(ValueError):
    """Persisted commencement-instrument coverage has an invalid shape."""


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentCandidate:
    source_id: str
    locator: str
    archive: str
    member_name: str
    title: str
    affected_law_ids: tuple[str, ...]
    effective_dates: tuple[str, ...]
    scope_status: NOCommencementScopeStatus
    source_excerpt: str
    rule_id: str = NO_COMMENCEMENT_INSTRUMENT_RULE
    replay_authorized: bool = False
    # W-39. The instrument's own ``Endrer`` (``changesToDocuments``) law ids —
    # the laws Lovdata records this instrument as changing. For a commencement
    # instrument those are not the instrument's own targets: they are the laws
    # the commenced PART of the cited act amends, which is what makes them a
    # scope proof. Read through ``declared_change_targets_from_root``, the
    # corpus's single reader of that block.
    changed_law_ids: tuple[str, ...] = ()
    # The section labels the operative text names, normalized to the grafter's
    # own section-label spelling so the two sets are comparable. Empty means the
    # operative text names no section at all.
    commenced_section_labels: tuple[str, ...] = ()
    # W-47. The operative text commences the act as a WHOLE — it names no
    # subdivision of the act and its commencement clause's subject is the act
    # itself. Read at parse time, where the operative blocks are already in
    # hand, so the gate stays a pure function of typed evidence and parses no
    # XML. Strictly weaker than ``scope_status is WHOLE_ACT``, which additionally
    # demands a single operative block matching ``_WHOLE_ACT_RE`` end to end;
    # this flag deliberately feeds ONLY the multi-part route, never the whole-act
    # one, so a looser reading can never re-date an act wholesale.
    whole_act_operative_text: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "archive": self.archive,
            "member_name": self.member_name,
            "title": self.title,
            "affected_law_ids": list(self.affected_law_ids),
            "effective_dates": list(self.effective_dates),
            "scope_status": self.scope_status,
            "source_excerpt": self.source_excerpt,
            "rule_id": self.rule_id,
            "replay_authorized": self.replay_authorized,
            "changed_law_ids": list(self.changed_law_ids),
            "commenced_section_labels": list(self.commenced_section_labels),
            "whole_act_operative_text": self.whole_act_operative_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "NOCommencementInstrumentCandidate":
        raw_affected_law_ids = data.get("affected_law_ids", [])
        raw_effective_dates = data.get("effective_dates", [])
        affected_law_ids = (
            tuple(item for item in raw_affected_law_ids if isinstance(item, str))
            if isinstance(raw_affected_law_ids, list)
            else ()
        )
        effective_dates = (
            tuple(item for item in raw_effective_dates if isinstance(item, str))
            if isinstance(raw_effective_dates, list)
            else ()
        )

        def _str_tuple(key: str) -> tuple[str, ...]:
            raw = data.get(key, [])
            if not isinstance(raw, list):
                return ()
            return tuple(item for item in raw if isinstance(item, str))

        return cls(
            changed_law_ids=_str_tuple("changed_law_ids"),
            commenced_section_labels=_str_tuple("commenced_section_labels"),
            source_id=str(data["source_id"]),
            locator=str(data["locator"]),
            archive=str(data.get("archive", "")),
            member_name=str(data.get("member_name", "")),
            title=str(data.get("title", "")),
            affected_law_ids=affected_law_ids,
            effective_dates=effective_dates,
            scope_status=NOCommencementScopeStatus(str(data.get("scope_status", "unresolved"))),
            source_excerpt=str(data.get("source_excerpt", "")),
            replay_authorized=bool(data.get("replay_authorized", False)),
            whole_act_operative_text=bool(data.get("whole_act_operative_text", False)),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentResidual:
    rule_id: str
    reason: str
    clause_text: str
    blocking: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "family": "temporal_recovery",
            "phase": "parse",
            "reason": self.reason,
            "clause_text": self.clause_text[:400],
            "blocking": self.blocking,
            "strict_disposition": "block" if self.blocking else "record",
        }


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentParseResult:
    parse_status: NOCommencementParseStatus
    candidate: NOCommencementInstrumentCandidate | None = None
    residuals: tuple[NOCommencementInstrumentResidual, ...] = ()


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentCoverage:
    total_instruments: int = 0
    candidates: int = 0
    benign_non_commencement: int = 0
    blocked_unresolved: int = 0

    def is_partition(self) -> bool:
        return self.total_instruments == (
            self.candidates + self.benign_non_commencement + self.blocked_unresolved
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "total_instruments": self.total_instruments,
            "candidates": self.candidates,
            "benign_non_commencement": self.benign_non_commencement,
            "blocked_unresolved": self.blocked_unresolved,
        }

    @classmethod
    def from_dict(cls, data: object) -> "NOCommencementInstrumentCoverage":
        if not isinstance(data, dict):
            raise NOCommencementInstrumentCoverageError(
                f"{NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID}: expected an object"
            )
        typed_data = cast(dict[str, object], data)

        def count(key: str) -> int:
            value = typed_data.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise NOCommencementInstrumentCoverageError(
                    f"{NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID}: "
                    f"{key} must be a non-negative integer"
                )
            return value

        return cls(
            total_instruments=count("total_instruments"),
            candidates=count("candidates"),
            benign_non_commencement=count("benign_non_commencement"),
            blocked_unresolved=count("blocked_unresolved"),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementAuthorizationReceipt:
    """One unresolved amendment act re-dated by a whole-act instrument."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    effective_date: str

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument authorized an unresolved amendment act: "
                "the act takes the instrument's whole-act commencement date."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_date=self.effective_date,
        )


@dataclass(frozen=True, slots=True)
class NOCommencementRefusalReceipt:
    """One (instrument, unresolved act) pair the authorization gate refused."""

    act_source_id: str
    instrument_source_id: str
    failed_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...]
    parse_status: NOCommencementParseStatus
    scope_status: NOCommencementScopeStatus
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_EXECUTION_REFUSED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument cites an unresolved amendment act but fails the "
                "execution-authorization gate; it stays evidence and re-dates nothing."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_id=self.instrument_source_id,
            failed_conjuncts=[str(conjunct) for conjunct in self.failed_conjuncts],
            parse_status=str(self.parse_status),
            scope_status=str(self.scope_status),
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementDateConflictReceipt:
    """Two instruments commencing one act at different dates; both refused."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instruments give one amendment act contradictory whole-act "
                "commencement dates; neither date is applied."
            ),
            blocking=True,
            strict_disposition="block",
            quirks_disposition=QuirksDisposition.BLOCK,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementPartAuthorizationReceipt:
    """One PART of one multi-part amending act, dated by one instrument.

    ``law_id`` is not decoration beside ``part_label``: it is how the
    authorization is applied. A part resolves to exactly one law (the gate
    refuses otherwise), and the act's ops are keyed by law, so "this part's ops"
    and "this act's ops for this law" are the same set of ops.
    """

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_date: str
    passed_conjuncts: tuple[NOCommencementPartAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument authorized ONE part of a staged "
                "multi-part amendment act: the act's operations on that part's law take "
                "the instrument's date; every other part stays as unresolved as before."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_date=self.effective_date,
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementMultiPartAuthorizationReceipt:
    """One part of a multi-part act dated by a WHOLE-ACT-text instrument.

    Carries the same fields as the single-part receipt and lands in the same
    ``part_scoped_effective_dates`` map, but keeps its own rule id so the two
    routes' grants stay separately countable: they prove different things, and
    a corpus pin that could not tell them apart would move for either.
    """

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_date: str
    spanned_part_labels: tuple[str, ...]
    passed_conjuncts: tuple[NOCommencementMultiPartAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument commences a multi-part amendment act as a "
                "WHOLE, so each part its Endrer header names takes the instrument's date; "
                "parts the header does not name stay as unresolved as before."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_date=self.effective_date,
            spanned_part_labels=list(self.spanned_part_labels),
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementPartDateConflictReceipt:
    """Two instruments commencing one part at different dates; both refused."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instruments give one part of an amendment act "
                "contradictory commencement dates; neither date is applied."
            ),
            blocking=True,
            strict_disposition="block",
            quirks_disposition=QuirksDisposition.BLOCK,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementActPartEvidence:
    """What the gate needs to know about ONE amendment act's part structure.

    Supplied by the caller that owns the artifacts (``index.py``); the gate
    computes none of it and parses no act XML.
    """

    part_law_ids: Mapping[str, str]
    """``romertall`` label -> the law that part amends. Parts that resolve no
    law of their own are simply absent."""

    bound_law_ids: tuple[str, ...]
    """The laws the act's lowered ops actually bind."""

    law_section_labels: Mapping[str, frozenset[str]]
    """law -> the section labels this act's ops on that law target."""


@dataclass(frozen=True, slots=True)
class NOCommencementExecutionAuthorization:
    """The gate's total outcome: the instruments, and a receipt per decision."""

    instruments: tuple[NOCommencementInstrumentCandidate, ...] = ()
    authorizations: tuple[NOCommencementAuthorizationReceipt, ...] = ()
    refusals: tuple[NOCommencementRefusalReceipt, ...] = ()
    conflicts: tuple[NOCommencementDateConflictReceipt, ...] = ()
    part_authorizations: tuple[NOCommencementPartAuthorizationReceipt, ...] = ()
    part_conflicts: tuple[NOCommencementPartDateConflictReceipt, ...] = ()
    multi_part_authorizations: tuple[NOCommencementMultiPartAuthorizationReceipt, ...] = ()

    def authorized_effective_dates(self) -> dict[str, str]:
        return {
            receipt.act_source_id: receipt.effective_date for receipt in self.authorizations
        }

    def part_authorized_effective_dates(self) -> dict[str, dict[str, str]]:
        """act -> {law -> date}, the per-binding dates the part routes granted.

        Both part routes land here: they grant the same KIND of thing (one
        binding's date) and every consumer wants one map. The single-part route
        is written second so that if the two ever proposed the same binding the
        older, narrower proof would win; measured over the corpus they never
        overlap, and the multi-part route refuses any key the single-part route
        already holds before it gets this far.
        """
        out: dict[str, dict[str, str]] = {}
        for multi_receipt in self.multi_part_authorizations:
            out.setdefault(multi_receipt.act_source_id, {})[
                multi_receipt.law_id
            ] = multi_receipt.effective_date
        for receipt in self.part_authorizations:
            out.setdefault(receipt.act_source_id, {})[receipt.law_id] = receipt.effective_date
        return out


def no_commencement_act_id_from_law_id(law_id: str) -> str:
    """Alias an instrument's ``basedOn`` law id onto the amendment-act id.

    Instruments cite the amending act by its law id (``no/lov/<date>-<num>``)
    while the index keys the same act by its Lovtidend id
    (``no/lovtid/<date>-<num>``); the date-and-number segment is shared.
    Returns ``""`` for an id that is not in law form.
    """
    if not law_id.startswith("no/lov/"):
        return ""
    return "no/lovtid/" + law_id.removeprefix("no/lov/")


def authorize_no_commencement_instruments(
    parsed_instruments: Sequence[
        tuple[NOCommencementParseStatus, NOCommencementInstrumentCandidate]
    ],
    *,
    offered_act_ids: Collection[str],
    act_part_evidence: Mapping[str, NOCommencementActPartEvidence] | None = None,
) -> NOCommencementExecutionAuthorization:
    """Gate already-parsed instruments into whole-act re-dating authorizations.

    Consumes parse results; it never re-parses instrument XML and never
    reclassifies a parse. An (instrument, act) pair authorizes only when every
    conjunct of ``NOCommencementAuthorizationConjunct`` holds and the cited law
    id aliases to an act in ``offered_act_ids``.

    ``offered_act_ids`` is whatever set the caller judges re-datable by an
    official instrument — this gate does not define it and does not inspect the
    acts' statuses. The production offering policy lives with the comprehension
    that defines it, in ``index.py``'s
    ``_authorize_no_commencement_instruments_into_index``.

    An instrument citing no offered act authorizes nothing and records nothing:
    that is the enabling-statute filter — an instrument commencing a *forskrift*
    cites the forskrift's hjemmel statutes, which are principal laws, not
    offered amendment acts.

    W-39: when the whole-act conjuncts fail, the pair is offered to the
    PART-SCOPED route (``NOCommencementPartAuthorizationConjunct``) before it is
    refused. The two routes are ordered, not alternative — an act the whole-act
    route dates is never re-examined per part, so the coarser, older
    authorization always wins where it exists. ``act_part_evidence`` left at
    ``None`` disables the part route entirely and this function behaves exactly
    as it did before W-39.

    W-47 adds a THIRD route in the same ordering, tried only where the
    single-part route declined: a header spanning several parts under an
    operative text that commences the whole act. It reads one thing the other
    two do not — the dates every OTHER instrument gives the same act, gathered
    below into ``instrument_dates_by_act`` — because its claim is about the act
    as a whole, and a later instrument is exactly what refutes such a claim.
    """
    offered = frozenset(offered_act_ids)
    part_evidence = dict(act_part_evidence or {})
    # act -> [(instrument id, date)] over EVERY parsed candidate citing it,
    # authorized or not: what refutes "the whole act commenced then" is that
    # another instrument commenced part of it later, whatever that instrument's
    # own scope was and whether or not it went on to authorize anything itself.
    instrument_dates_by_act: dict[str, list[tuple[str, str]]] = {}
    for _parse_status, sibling in parsed_instruments:
        for sibling_law_id in sibling.affected_law_ids:
            sibling_act_id = no_commencement_act_id_from_law_id(sibling_law_id)
            if not sibling_act_id:
                continue
            for sibling_date in sibling.effective_dates:
                instrument_dates_by_act.setdefault(sibling_act_id, []).append(
                    (sibling.source_id, sibling_date)
                )
    proposals: dict[str, dict[str, list[str]]] = {}
    part_proposals: dict[
        tuple[str, str, str], dict[str, list[str]]
    ] = {}
    part_conjuncts: dict[
        tuple[str, str, str], tuple[NOCommencementPartAuthorizationConjunct, ...]
    ] = {}
    multi_part_proposals: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    multi_part_spans: dict[tuple[str, str, str], tuple[str, ...]] = {}
    refusals: list[NOCommencementRefusalReceipt] = []
    for parse_status, candidate in parsed_instruments:
        cited_act_ids = tuple(
            sorted(
                {
                    act_id
                    for act_id in (
                        no_commencement_act_id_from_law_id(law_id)
                        for law_id in candidate.affected_law_ids
                    )
                    if act_id in offered
                }
            )
        )
        if not cited_act_ids:
            continue
        failed_conjuncts = _failed_authorization_conjuncts(parse_status, candidate)
        if failed_conjuncts:
            for act_id in cited_act_ids:
                part_match = _part_scoped_authorization_scope(
                    parse_status,
                    candidate,
                    failed_conjuncts,
                    part_evidence.get(act_id),
                )
                if part_match is not None:
                    part_label, law_id, passed = part_match
                    key = (act_id, part_label, law_id)
                    part_proposals.setdefault(key, {}).setdefault(
                        candidate.effective_dates[0], []
                    ).append(candidate.source_id)
                    part_conjuncts[key] = passed
                    continue
                multi_part_match = _multi_part_scoped_authorization_scope(
                    parse_status,
                    candidate,
                    failed_conjuncts,
                    part_evidence.get(act_id),
                    instrument_dates_by_act.get(act_id, ()),
                )
                if multi_part_match is not None:
                    for part_label, law_id in multi_part_match:
                        key = (act_id, part_label, law_id)
                        multi_part_proposals.setdefault(key, {}).setdefault(
                            candidate.effective_dates[0], []
                        ).append(candidate.source_id)
                        multi_part_spans[key] = tuple(
                            sorted(label for label, _law in multi_part_match)
                        )
                    continue
                refusals.append(
                    NOCommencementRefusalReceipt(
                        act_source_id=act_id,
                        instrument_source_id=candidate.source_id,
                        failed_conjuncts=failed_conjuncts,
                        parse_status=parse_status,
                        scope_status=candidate.scope_status,
                        effective_dates=candidate.effective_dates,
                    )
                )
            continue
        for act_id in cited_act_ids:
            proposals.setdefault(act_id, {}).setdefault(
                candidate.effective_dates[0], []
            ).append(candidate.source_id)

    authorizations: list[NOCommencementAuthorizationReceipt] = []
    conflicts: list[NOCommencementDateConflictReceipt] = []
    authorized_instrument_ids: set[str] = set()
    for act_id, instrument_ids_by_date in sorted(proposals.items()):
        if len(instrument_ids_by_date) > 1:
            conflicts.append(
                NOCommencementDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        authorizations.append(
            NOCommencementAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                effective_date=effective_date,
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # An act the whole-act route already dated is not re-examined per part: the
    # older, coarser authorization stands, and a part proposal for it is dropped
    # without a receipt because the act already carries the date it would grant.
    whole_act_authorized = {receipt.act_source_id for receipt in authorizations}
    part_authorizations: list[NOCommencementPartAuthorizationReceipt] = []
    part_conflicts: list[NOCommencementPartDateConflictReceipt] = []
    for (act_id, part_label, law_id), instrument_ids_by_date in sorted(part_proposals.items()):
        if act_id in whole_act_authorized:
            continue
        if len(instrument_ids_by_date) > 1:
            part_conflicts.append(
                NOCommencementPartDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    part_label=part_label,
                    law_id=law_id,
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        part_authorizations.append(
            NOCommencementPartAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                part_label=part_label,
                law_id=law_id,
                effective_date=effective_date,
                passed_conjuncts=part_conjuncts[(act_id, part_label, law_id)],
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # The multi-part route resolves last, and yields to both routes above it:
    # to the whole-act one per act, and to the single-part one per BINDING. A
    # key either already holds the date this route would grant or holds a
    # narrower proof of it, so the proposal is dropped without a receipt for the
    # same reason W-39's is. Measured over the corpus neither collision occurs.
    single_part_authorized_keys = {
        (receipt.act_source_id, receipt.part_label, receipt.law_id)
        for receipt in part_authorizations
    }
    multi_part_authorizations: list[NOCommencementMultiPartAuthorizationReceipt] = []
    for (act_id, part_label, law_id), instrument_ids_by_date in sorted(
        multi_part_proposals.items()
    ):
        if act_id in whole_act_authorized:
            continue
        if (act_id, part_label, law_id) in single_part_authorized_keys:
            continue
        if len(instrument_ids_by_date) > 1:
            part_conflicts.append(
                NOCommencementPartDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    part_label=part_label,
                    law_id=law_id,
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        multi_part_authorizations.append(
            NOCommencementMultiPartAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                part_label=part_label,
                law_id=law_id,
                effective_date=effective_date,
                spanned_part_labels=multi_part_spans[(act_id, part_label, law_id)],
                passed_conjuncts=tuple(NOCommencementMultiPartAuthorizationConjunct),
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    return NOCommencementExecutionAuthorization(
        instruments=tuple(
            replace(
                candidate,
                replay_authorized=candidate.source_id in authorized_instrument_ids,
            )
            for _parse_status, candidate in parsed_instruments
        ),
        authorizations=tuple(authorizations),
        refusals=tuple(refusals),
        conflicts=tuple(conflicts),
        part_authorizations=tuple(part_authorizations),
        part_conflicts=tuple(part_conflicts),
        multi_part_authorizations=tuple(multi_part_authorizations),
    )


def _part_scoped_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
    evidence: "NOCommencementActPartEvidence | None",
) -> tuple[str, str, tuple[NOCommencementPartAuthorizationConjunct, ...]] | None:
    """Prove which single part this instrument commences, or return ``None``.

    Every conjunct of :class:`NOCommencementPartAuthorizationConjunct` must
    hold; there is no partial credit and no ranking among them. Returns
    ``(part label, law id, the conjuncts it passed)``.
    """
    if evidence is None:
        return None
    if len(candidate.effective_dates) != 1:
        return None
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return None
    if set(failed_whole_act_conjuncts) != {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    }:
        return None
    changed = set(candidate.changed_law_ids)
    if not changed:
        return None

    parts_by_law: dict[str, list[str]] = {}
    for part_label, law_id in evidence.part_law_ids.items():
        parts_by_law.setdefault(law_id, []).append(part_label)
    if any(len(labels) > 1 for labels in parts_by_law.values()):
        return None
    if any(law_id not in parts_by_law for law_id in evidence.bound_law_ids):
        return None
    if any(law_id not in parts_by_law for law_id in changed):
        return None
    part_labels = {parts_by_law[law_id][0] for law_id in changed}
    if len(part_labels) != 1:
        return None
    part_label = part_labels.pop()
    part_laws = {
        law_id for law_id, labels in parts_by_law.items() if labels[0] == part_label
    }
    if part_laws != changed:
        return None
    law_id = next(iter(changed))
    named_sections = set(candidate.commenced_section_labels)
    if named_sections and named_sections != set(
        evidence.law_section_labels.get(law_id, frozenset())
    ):
        return None
    return (
        part_label,
        law_id,
        tuple(NOCommencementPartAuthorizationConjunct),
    )


def _multi_part_scoped_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
    evidence: "NOCommencementActPartEvidence | None",
    instrument_dates_for_act: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...] | None:
    """Prove which SEVERAL parts this instrument commences, or return ``None``.

    Every conjunct of :class:`NOCommencementMultiPartAuthorizationConjunct` must
    hold; there is no partial credit, and in particular no per-part credit — the
    span authorizes whole or not at all, because what proves it is a single
    statement about the whole act. Returns the ``(part label, law id)`` pairs in
    part-label order.
    """
    if evidence is None:
        return None
    if len(candidate.effective_dates) != 1:
        return None
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return None
    if set(failed_whole_act_conjuncts) != {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    }:
        return None
    changed = set(candidate.changed_law_ids)
    if not changed:
        return None

    parts_by_law: dict[str, list[str]] = {}
    for part_label, law_id in evidence.part_law_ids.items():
        parts_by_law.setdefault(law_id, []).append(part_label)
    if any(len(labels) > 1 for labels in parts_by_law.values()):
        return None
    if any(law_id not in parts_by_law for law_id in evidence.bound_law_ids):
        return None
    if any(law_id not in parts_by_law for law_id in changed):
        return None
    spanned_labels = {parts_by_law[law_id][0] for law_id in changed}
    # One part is the W-39 route's business; it has already declined this pair
    # for some other reason, and re-deciding it here on weaker evidence would
    # overrule it.
    if len(spanned_labels) < 2:
        return None
    spanned_laws = {
        law_id for law_id, labels in parts_by_law.items() if labels[0] in spanned_labels
    }
    if spanned_laws != changed:
        return None
    if not candidate.whole_act_operative_text:
        return None
    named_sections = set(candidate.commenced_section_labels)
    if named_sections and any(
        named_sections != set(evidence.law_section_labels.get(law_id, frozenset()))
        for law_id in changed
    ):
        return None
    effective_date = candidate.effective_dates[0]
    if any(
        source_id != candidate.source_id and date > effective_date
        for source_id, date in instrument_dates_for_act
    ):
        return None
    return tuple(
        sorted(
            (parts_by_law[law_id][0], law_id) for law_id in changed
        )
    )


def _failed_authorization_conjuncts(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
) -> tuple[NOCommencementAuthorizationConjunct, ...]:
    failed: list[NOCommencementAuthorizationConjunct] = []
    if parse_status is not NOCommencementParseStatus.CANDIDATE:
        failed.append(NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE)
    if candidate.scope_status is not NOCommencementScopeStatus.WHOLE_ACT:
        failed.append(NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE)
    if len(candidate.effective_dates) != 1:
        failed.append(NOCommencementAuthorizationConjunct.SINGLE_EFFECTIVE_DATE)
    return tuple(failed)


def _normalized_text(root: etree._Element) -> str:
    return _WS_RE.sub(
        " ",
        " ".join(str(item) for item in root.itertext()).replace("\xa0", " "),
    ).strip()


def _class_text(root: etree._Element, class_name: str) -> str:
    value = root.xpath(
        "string(//dd[contains(concat(' ', normalize-space(@class), ' '), "
        f"' {class_name} ')][1])"
    )
    return _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()


def _body_text(root: etree._Element) -> str:
    value = root.xpath(
        "string(//*[contains(concat(' ', normalize-space(@class), ' '), ' documentBody ')][1])"
    )
    return _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()


def _operative_blocks(root: etree._Element) -> tuple[str, ...]:
    blocks: list[str] = []
    for node in cast(
        list[etree._Element],
        root.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' documentBody ')]"
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' legalP ')]"
        ),
    ):
        text = _WS_RE.sub(" ", " ".join(str(item) for item in node.itertext())).strip()
        if text:
            blocks.append(text)
    return tuple(blocks)


def _commenced_section_labels(operative_blocks: Sequence[str]) -> tuple[str, ...]:
    """The section labels the operative text names, in the grafter's spelling.

    Normalized to match ``_normalize_no_section_label`` output (``§`` dropped,
    inner spaces removed, lower-cased) so the set can be compared directly with
    the section labels of the part's own ops. An empty result means the text
    names no section, which is the strongest whole-part evidence there is.
    """
    labels: set[str] = set()
    for block in operative_blocks:
        # lawvm-regex: owning_parser this IS the commenced-section-label reader
        for match in _COMMENCED_SECTION_RE.finditer(block):
            labels.add(_WS_RE.sub("", match.group(1)).lower())
    return tuple(sorted(labels))


def _whole_act_operative_text(operative_blocks: Sequence[str]) -> bool:
    """Does the operative text commence the act as a WHOLE?

    Both halves of the W-47 guard, over the blocks joined: no subdivision of the
    act named anywhere and no negative/exception phrase, AND a commencement
    clause whose subject is the act rather than one of the laws it amends. The
    first half alone would miss a law-scoped narrowing, the second alone would
    miss "Loven trer i kraft ... med unntak av del V"; measured over the
    spanning-header surface, each half catches pairs the other lets through.
    """
    text = " ".join(operative_blocks)
    # lawvm-regex: owning_parser this IS the reader of the instrument's own operative scope; refusing half, cannot accept
    if _SUBDIVISION_SCOPE_RE.search(text):
        return False
    # lawvm-regex: owning_parser same reader, subject half; a closed act-word vocabulary, and absence refuses
    if _WHOLE_ACT_SUBJECT_RE.search(text):
        return True
    # lawvm-regex: owning_parser same reader, the act's own citation as the clause subject
    return bool(_CITED_ACT_SUBJECT_RE.search(text))


def _document_title(root: etree._Element) -> str:
    for value in (
        _class_text(root, "title"),
        _class_text(root, "titleShort"),
        root.xpath("string(//head/title[1])"),
        root.xpath("string(//h1[1])"),
    ):
        normalized = _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()
        if normalized:
            return normalized
    return ""


def _law_ids(root: etree._Element) -> tuple[str, ...]:
    candidates: list[str] = []
    for node in cast(
        list[etree._Element],
        root.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' basedOn ')]"),
    ):
        candidates.append(" ".join(str(item) for item in node.itertext()))
        candidates.extend(str(value) for value in cast(list[str], node.xpath(".//@*")))
    law_ids: set[str] = set()
    for value in candidates:
        # lawvm-regex: owning_parser harvests lov/<date>-<num> ids from basedOn locators, not prose
        for match in _LAW_REF_RE.finditer(value.replace("https://lovdata.no/dokument/NL/", "")):
            law_ids.add(f"no/lov/{match.group('date')}-{int(match.group('num'))}")
    return tuple(sorted(law_ids))


def parse_no_commencement_instrument(
    payload: bytes,
    *,
    source_id: str,
    locator: str,
    archive: str,
    member_name: str,
) -> NOCommencementInstrumentParseResult:
    """Parse one ``sf`` source into a candidate or an accounted non-candidate."""
    try:
        root = parse_corpus_xml(payload)
    except etree.XMLSyntaxError as exc:
        clause_text = payload.decode("utf-8", errors="replace")[:400]
        return NOCommencementInstrumentParseResult(
            parse_status=NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            residuals=(
                NOCommencementInstrumentResidual(
                    rule_id=NO_COMMENCEMENT_INSTRUMENT_PARSE_FAILED,
                    reason=f"Norway Lovtidend instrument XML parse failed: {exc}",
                    clause_text=clause_text,
                ),
            ),
        )
    text = _normalized_text(root)
    title = _document_title(root)
    body_text = _body_text(root) or text
    # lawvm-regex: prefilter compile_classifier_regex-built title/clause guards; route non-commencement out
    if not _COMMENCEMENT_TITLE_RE.search(title) and not _LAW_COMMENCEMENT_RE.search(body_text):
        return NOCommencementInstrumentParseResult(
            parse_status=NOCommencementParseStatus.BENIGN_NOT_COMMENCEMENT
        )

    affected_law_ids = _law_ids(root)
    effective_text = _class_text(root, "dateInForce")
    # lawvm-regex: owning_parser reads ISO dates from the instrument's own dateInForce field
    effective_dates = tuple(sorted(set(_ISO_DATE_RE.findall(effective_text))))
    operative_blocks = _operative_blocks(root)
    whole_act = (
        len(operative_blocks) == 1
        and bool(_WHOLE_ACT_RE.fullmatch(operative_blocks[0]))
        and len(effective_dates) == 1
    )
    scope_status = (
        NOCommencementScopeStatus.WHOLE_ACT
        if whole_act
        else NOCommencementScopeStatus.UNRESOLVED
    )
    # Function-local like the grafter's own use of it: ``sources`` imports from
    # this module at load time, so the corpus's single ``changesToDocuments``
    # reader is only reachable from inside the function.
    from lawvm.norway.sources import declared_change_targets_from_root

    candidate = NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=locator,
        archive=archive,
        member_name=member_name,
        title=title,
        affected_law_ids=affected_law_ids,
        effective_dates=effective_dates,
        scope_status=scope_status,
        source_excerpt=text[:400],
        changed_law_ids=declared_change_targets_from_root(root).law_ids,
        commenced_section_labels=_commenced_section_labels(operative_blocks),
        whole_act_operative_text=_whole_act_operative_text(operative_blocks),
    )
    residuals: tuple[NOCommencementInstrumentResidual, ...] = ()
    parse_status = NOCommencementParseStatus.CANDIDATE
    if not affected_law_ids or not effective_dates or scope_status is NOCommencementScopeStatus.UNRESOLVED:
        missing = []
        if not affected_law_ids:
            missing.append("affected law binding")
        if not effective_dates:
            missing.append("effective date")
        if scope_status is NOCommencementScopeStatus.UNRESOLVED:
            missing.append("whole-act scope proof")
        residuals = (
            NOCommencementInstrumentResidual(
                rule_id=NO_COMMENCEMENT_SCOPE_UNRESOLVED,
                reason="Norway commencement instrument remains non-executable: missing " + ", ".join(missing),
                clause_text=text,
            ),
        )
        parse_status = NOCommencementParseStatus.BLOCKED_UNRESOLVED
    return NOCommencementInstrumentParseResult(
        parse_status=parse_status,
        candidate=candidate,
        residuals=residuals,
    )
