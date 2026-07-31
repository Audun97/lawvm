"""Typed Norsk Lovtidend commencement-instrument surface.

Parses commencement instruments into typed candidates, and owns the
execution-authorization gate that re-dates unresolved amendment acts from a
whole-act, single-date instrument. Parsing itself still authorizes nothing: only
a candidate that passes every conjunct of the gate re-dates the act it cites.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
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
_WHOLE_ACT_RE = compile_classifier_regex(
    r"^(?:denne )?(?:loven|lova) trer i (?:kraft|verk)\b[^§]{0,400}$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.whole_act_commencement",
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
        return cls(
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
class NOCommencementExecutionAuthorization:
    """The gate's total outcome: the instruments, and a receipt per decision."""

    instruments: tuple[NOCommencementInstrumentCandidate, ...] = ()
    authorizations: tuple[NOCommencementAuthorizationReceipt, ...] = ()
    refusals: tuple[NOCommencementRefusalReceipt, ...] = ()
    conflicts: tuple[NOCommencementDateConflictReceipt, ...] = ()

    def authorized_effective_dates(self) -> dict[str, str]:
        return {
            receipt.act_source_id: receipt.effective_date for receipt in self.authorizations
        }


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
    unresolved_act_ids: Collection[str],
) -> NOCommencementExecutionAuthorization:
    """Gate already-parsed instruments into whole-act re-dating authorizations.

    Consumes parse results; it never re-parses instrument XML and never
    reclassifies a parse. An (instrument, act) pair authorizes only when every
    conjunct of ``NOCommencementAuthorizationConjunct`` holds and the cited law
    id aliases to an act in ``unresolved_act_ids``. An instrument citing no
    unresolved act authorizes nothing and records nothing: that is the
    enabling-statute filter — an instrument commencing a *forskrift* cites the
    forskrift's hjemmel statutes, which are principal laws, not unresolved
    amendment acts.
    """
    unresolved = frozenset(unresolved_act_ids)
    proposals: dict[str, dict[str, list[str]]] = {}
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
                    if act_id in unresolved
                }
            )
        )
        if not cited_act_ids:
            continue
        failed_conjuncts = _failed_authorization_conjuncts(parse_status, candidate)
        if failed_conjuncts:
            refusals.extend(
                NOCommencementRefusalReceipt(
                    act_source_id=act_id,
                    instrument_source_id=candidate.source_id,
                    failed_conjuncts=failed_conjuncts,
                    parse_status=parse_status,
                    scope_status=candidate.scope_status,
                    effective_dates=candidate.effective_dates,
                )
                for act_id in cited_act_ids
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

    return NOCommencementExecutionAuthorization(
        instruments=tuple(
            replace(candidate, replay_authorized=True)
            if candidate.source_id in authorized_instrument_ids
            else candidate
            for _parse_status, candidate in parsed_instruments
        ),
        authorizations=tuple(authorizations),
        refusals=tuple(refusals),
        conflicts=tuple(conflicts),
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
    if not _COMMENCEMENT_TITLE_RE.search(title) and not _LAW_COMMENCEMENT_RE.search(body_text):
        return NOCommencementInstrumentParseResult(
            parse_status=NOCommencementParseStatus.BENIGN_NOT_COMMENCEMENT
        )

    affected_law_ids = _law_ids(root)
    effective_text = _class_text(root, "dateInForce")
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
