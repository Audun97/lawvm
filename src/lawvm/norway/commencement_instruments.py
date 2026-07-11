"""Typed, non-authorizing Norsk Lovtidend commencement-instrument surface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from lxml import etree

from lawvm.core.regex_safety import compile_classifier_regex
from lawvm.core.xml_parse import parse_corpus_xml

NO_COMMENCEMENT_INSTRUMENT_RULE = "no_lovtidend_commencement_instrument_candidate"
NO_COMMENCEMENT_SCOPE_UNRESOLVED = "no_lovtidend_commencement_scope_unresolved"
NO_COMMENCEMENT_INSTRUMENT_PARSE_FAILED = "no_lovtidend_commencement_instrument_parse_failed"
NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID = "no_lovtidend_commencement_instrument_coverage_invalid"

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
            "replay_authorized": False,
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
