from __future__ import annotations

import io
import os
import tarfile
from dataclasses import replace as dataclass_replace
from pathlib import Path

import pytest

from lawvm.norway.commencement_instruments import (
    _WHOLE_ACT_RE,
    no_commencement_act_id_from_law_id,
    NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
    NO_COMMENCEMENT_EXECUTION_REFUSED,
    NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID,
    NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT,
    NOCommencementActPartEvidence,
    NOCommencementMultiPartAuthorizationConjunct,
    NOCommencementNamedPartListAuthorizationConjunct,
    NOCommencementPartAuthorizationConjunct,
    NOCommencementAuthorizationConjunct,
    NOCommencementInstrumentCandidate,
    NOCommencementInstrumentCoverage,
    NOCommencementInstrumentCoverageError,
    NOCommencementParseStatus,
    NOCommencementScopeStatus,
    _named_part_labels,
    _whole_act_operative_text,
    authorize_no_commencement_instruments,
    parse_no_commencement_instrument,
)
from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.commencement import _recommend_no_backfill_lane
from lawvm.norway.replay import replay_no_to_pit
from lawvm.norway.sources import ingest_no_public_archives, open_no_archive
from lawvm.tools.no_commencement_candidates import build_no_commencement_candidate_report


_BASE_XML = b"""<html><head><title>Testlov</title></head><body>
<main class="documentBody" data-lovdata-URL="LTI/lov/2025-01-01-1">
<section class="section" data-name="kap1"><h2>Kapittel 1</h2>
<article class="legalArticle" data-name="\xc2\xa71"><h3 class="legalArticleHeader">\xc2\xa7 1</h3>
<article class="legalP">Opprinnelig tekst.</article></article></section></main>
</body></html>"""


def _amendment_xml() -> bytes:
    return b"""<html><body>
<dd class="title">Endringslov</dd><dd class="dateInForce">Kongen bestemmer</dd>
<article class="document-change" data-document="lov/2025-01-01-1">
<article class="change" data-change-part="lov/2025-01-01-1/\xc2\xa71">
<article class="defaultP">\xc2\xa7 1 skal lyde:</article>
<article class="futureLegalArticle" data-name="\xc2\xa71">
<article class="legalP">Endret tekst.</article></article></article></article>
</body></html>"""


def _whole_act_instrument_xml() -> bytes:
    return b"""<html><body>
<dd class="title">Ikraftsetting av lov 2. februar 2025 nr. 5</dd>
<dd class="basedOn"><a href="lov/2025-02-02-5">lov 2. februar 2025 nr. 5</a></dd>
<dd class="dateInForce">2025-04-01</dd>
<main class="documentBody"><article class="legalP">Loven trer i kraft 1. april 2025.</article></main>
</body></html>"""


def _partial_instrument_xml(
    date_in_force: str = "2025-04-01 og 2025-06-01",
    body: str = "Loven § 2 trer i kraft 1. april 2025. Resten trer i kraft 1. juni 2025.",
) -> bytes:
    """A partial commencement instrument, refused for want of whole-act scope.

    W-51 parameterizes the dates, because after the repair they are no longer
    inert: this instrument cites the same act as the whole-act one beside it, so
    a date of its LATER than the whole-act grant refutes that grant. The default
    keeps the shape the parse tests assert on; the end-to-end archive below uses
    a variant whose staging is finished before the whole-act date, and
    :func:`test_a_later_partial_instrument_demotes_the_whole_act_grant_end_to_end`
    pins what the default shape now does.
    """
    return (
        "<html><body>\n"
        '<dd class="title">Delt ikraftsetting av lov 2. februar 2025 nr. 5</dd>\n'
        '<dd class="basedOn"><a href="lov/2025-02-02-5">endringsloven</a></dd>\n'
        f'<dd class="dateInForce">{date_in_force}</dd>\n'
        f'<main class="documentBody">{body}</main>\n'
        "</body></html>"
    ).encode("utf-8")


def _ordinary_forskrift_xml() -> bytes:
    return b"""<html><body><dd class="title">Forskrift om rapportering</dd>
<dd class="basedOn"><a href="lov/2025-02-02-5">hjemmel</a></dd>
<main class="documentBody">Departementet kan kreve rapportering.</main></body></html>"""


def _instrument_candidate(
    source_id: str,
    *,
    affected_law_ids: tuple[str, ...],
    effective_dates: tuple[str, ...],
    scope_status: NOCommencementScopeStatus = NOCommencementScopeStatus.WHOLE_ACT,
) -> NOCommencementInstrumentCandidate:
    number = source_id.rsplit("-", 1)[-1]
    return NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=f"no://forskrift/{source_id.removeprefix('no/forskrift/')}/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name=f"lti/2025/sf-20250301-{int(number):04d}.xml",
        title="Ikraftsetting av lov 2. februar 2025 nr. 5",
        affected_law_ids=affected_law_ids,
        effective_dates=effective_dates,
        scope_status=scope_status,
        source_excerpt="Loven trer i kraft 1. april 2025.",
    )


def _write_archive(path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:bz2") as archive:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def test_parse_whole_act_commencement_candidate_is_non_authorizing() -> None:
    result = parse_no_commencement_instrument(
        _whole_act_instrument_xml(),
        source_id="no/forskrift/2025-03-01-100",
        locator="no://forskrift/2025-03-01-100/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0100.xml",
    )

    assert result.parse_status is NOCommencementParseStatus.CANDIDATE
    assert result.residuals == ()
    assert result.candidate is not None
    assert result.candidate.affected_law_ids == ("no/lov/2025-02-02-5",)
    assert result.candidate.effective_dates == ("2025-04-01",)
    assert result.candidate.scope_status is NOCommencementScopeStatus.WHOLE_ACT
    assert result.candidate.replay_authorized is False


def test_parse_partial_commencement_preserves_blocking_scope_residual() -> None:
    result = parse_no_commencement_instrument(
        _partial_instrument_xml(),
        source_id="no/forskrift/2025-03-01-101",
        locator="no://forskrift/2025-03-01-101/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0101.xml",
    )

    assert result.parse_status is NOCommencementParseStatus.BLOCKED_UNRESOLVED
    assert result.candidate is not None
    assert result.candidate.scope_status is NOCommencementScopeStatus.UNRESOLVED
    assert result.candidate.effective_dates == ("2025-04-01", "2025-06-01")
    assert result.candidate.replay_authorized is False
    assert result.residuals[0].rule_id == "no_lovtidend_commencement_scope_unresolved"
    assert result.residuals[0].blocking is True
    assert "\u00a7 2" in result.residuals[0].clause_text


def test_parse_ordinary_forskrift_is_accounted_benign_non_candidate() -> None:
    result = parse_no_commencement_instrument(
        _ordinary_forskrift_xml(),
        source_id="no/forskrift/2025-03-01-102",
        locator="no://forskrift/2025-03-01-102/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0102.xml",
    )

    assert result.parse_status is NOCommencementParseStatus.BENIGN_NOT_COMMENCEMENT
    assert result.candidate is None
    assert result.residuals == ()


def test_parse_malformed_instrument_preserves_blocking_source_residual() -> None:
    payload = b"<html><body><main>truncated"

    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2025-03-01-103",
        locator="no://forskrift/2025-03-01-103/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0103.xml",
    )

    assert result.parse_status is NOCommencementParseStatus.BLOCKED_UNRESOLVED
    assert result.candidate is None
    assert result.residuals[0].rule_id == "no_lovtidend_commencement_instrument_parse_failed"
    assert result.residuals[0].clause_text == payload.decode()


def test_persisted_coverage_rejects_malformed_counter() -> None:
    with pytest.raises(
        NOCommencementInstrumentCoverageError,
        match=NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID,
    ):
        NOCommencementInstrumentCoverage.from_dict({"total_instruments": "3"})


def test_execution_authorization_redates_the_cited_unresolved_act() -> None:
    candidate = _instrument_candidate(
        "no/forskrift/2025-03-01-100",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.CANDIDATE, candidate)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorized_effective_dates() == {"no/lovtid/2025-02-02-5": "2025-04-01"}
    assert authorization.refusals == ()
    assert authorization.conflicts == ()
    assert [item.replay_authorized for item in authorization.instruments] == [True]
    receipt = authorization.authorizations[0].to_diagnostic_detail()
    assert receipt["rule_id"] == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    assert receipt["family"] == "temporal_recovery"
    assert receipt["phase"] == "temporal"
    assert receipt["source_id"] == "no/lovtid/2025-02-02-5"
    assert receipt["instrument_source_ids"] == ["no/forskrift/2025-03-01-100"]
    assert receipt["effective_date"] == "2025-04-01"
    assert receipt["blocking"] is False
    assert receipt["strict_disposition"] == "record"
    assert receipt["quirks_disposition"] == "record"


def test_execution_authorization_refuses_a_partial_commencement_candidate() -> None:
    candidate = _instrument_candidate(
        "no/forskrift/2025-03-01-101",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.BLOCKED_UNRESOLVED, candidate)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert authorization.conflicts == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False]
    assert authorization.refusals[0].failed_conjuncts == (
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    )
    receipt = authorization.refusals[0].to_diagnostic_detail()
    assert receipt["rule_id"] == NO_COMMENCEMENT_EXECUTION_REFUSED
    assert receipt["source_id"] == "no/lovtid/2025-02-02-5"
    assert receipt["instrument_source_id"] == "no/forskrift/2025-03-01-101"
    assert receipt["failed_conjuncts"] == ["parse_status_candidate", "whole_act_scope"]
    assert receipt["blocking"] is False
    assert receipt["strict_disposition"] == "record"


def test_execution_authorization_refuses_a_multi_date_instrument() -> None:
    candidate = _instrument_candidate(
        "no/forskrift/2025-03-01-102",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01", "2025-06-01"),
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.CANDIDATE, candidate)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False]
    receipt = authorization.refusals[0].to_diagnostic_detail()
    assert receipt["failed_conjuncts"] == ["single_effective_date"]
    assert receipt["effective_dates"] == ["2025-04-01", "2025-06-01"]


def test_execution_authorization_refuses_both_instruments_on_a_date_conflict() -> None:
    first = _instrument_candidate(
        "no/forskrift/2025-03-01-103",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    second = _instrument_candidate(
        "no/forskrift/2025-03-01-104",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-07-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, first),
            (NOCommencementParseStatus.CANDIDATE, second),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False, False]
    receipt = authorization.conflicts[0].to_diagnostic_detail()
    assert receipt["rule_id"] == NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT
    assert receipt["source_id"] == "no/lovtid/2025-02-02-5"
    assert receipt["instrument_source_ids"] == [
        "no/forskrift/2025-03-01-103",
        "no/forskrift/2025-03-01-104",
    ]
    assert receipt["effective_dates"] == ["2025-04-01", "2025-07-01"]
    assert receipt["blocking"] is True
    assert receipt["strict_disposition"] == "block"
    assert receipt["quirks_disposition"] == "block"


def test_execution_authorization_dedupes_two_instruments_agreeing_on_one_date() -> None:
    first = _instrument_candidate(
        "no/forskrift/2025-03-01-105",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    second = _instrument_candidate(
        "no/forskrift/2025-03-01-106",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, first),
            (NOCommencementParseStatus.CANDIDATE, second),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.conflicts == ()
    assert len(authorization.authorizations) == 1
    assert authorization.authorizations[0].instrument_source_ids == (
        "no/forskrift/2025-03-01-105",
        "no/forskrift/2025-03-01-106",
    )
    assert authorization.authorized_effective_dates() == {"no/lovtid/2025-02-02-5": "2025-04-01"}
    assert [item.replay_authorized for item in authorization.instruments] == [True, True]


def test_execution_authorization_ignores_enabling_statute_citations() -> None:
    # "Ikraftsetting av forskrift ..." instruments cite the forskrift's hjemmel
    # statutes; those are principal laws, not unresolved amendment acts, so the
    # alias join finds nothing. Normal case, not a pathology: no receipt.
    candidate = _instrument_candidate(
        "no/forskrift/2025-03-01-107",
        affected_law_ids=("no/lov/1952-11-21-2", "no/lov/1997-02-28-19"),
        effective_dates=("2025-04-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.CANDIDATE, candidate)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert authorization.refusals == ()
    assert authorization.conflicts == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False]


def test_execution_authorization_never_redates_an_already_resolved_act() -> None:
    # The act the instrument cites carries a resolved status, so it is not in the
    # unresolved set the gate is offered and nothing may touch it.
    candidate = _instrument_candidate(
        "no/forskrift/2025-03-01-108",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.CANDIDATE, candidate)],
        offered_act_ids=set(),
    )

    assert authorization.authorizations == ()
    assert authorization.refusals == ()
    assert authorization.conflicts == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False]


def test_commencement_candidate_replay_authorized_round_trips() -> None:
    candidate = _instrument_candidate(
        "no/forskrift/2025-03-01-109",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.CANDIDATE, candidate)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    payload = authorization.instruments[0].to_dict()
    assert payload["replay_authorized"] is True
    assert NOCommencementInstrumentCandidate.from_dict(payload).replay_authorized is True
    assert candidate.to_dict()["replay_authorized"] is False

    without_key = {key: value for key, value in payload.items() if key != "replay_authorized"}
    assert NOCommencementInstrumentCandidate.from_dict(without_key).replay_authorized is False


def test_backfill_prefers_exact_lovtidend_instrument_without_authorizing_it() -> None:
    lane = _recommend_no_backfill_lane(
        {
            "local_corpus": 1,
            "lovtidend_commencement_instrument": 1,
            "statsrad": 1,
        }
    )

    assert lane == "lovtidend_commencement_instrument"


def test_ingest_index_and_replay_execute_the_whole_act_lovtidend_instrument(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
            ("lti/2025/sf-20250301-0100.xml", _whole_act_instrument_xml()),
            # W-51: the partial instrument's staging finishes on the whole-act
            # date, so it is a sibling but not a LATER one and the act's
            # whole-act grant stands. See the test below for the other case.
            (
                "lti/2025/sf-20250301-0101.xml",
                _partial_instrument_xml(
                    date_in_force="2025-01-15 og 2025-04-01",
                    body="Loven § 2 trer i kraft 15. januar 2025. Resten trer i kraft 1. april 2025.",
                ),
            ),
            ("lti/2025/sf-20250301-0102.xml", _ordinary_forskrift_xml()),
        ],
    )
    db_path = tmp_path / "norway.farchive"

    ingest_report = ingest_no_public_archives(tmp_path, db_path)
    index = build_no_amendment_index(db_path)
    report = build_no_commencement_candidate_report(
        source_id="no/lovtid/2025-02-02-5",
        data_dir=db_path,
        direct_only=True,
    )

    assert ingest_report["forskrift_locators_stored"] == 3
    assert ingest_report["skipped_unmapped"] == 0
    archive = open_no_archive(db_path)
    try:
        assert archive.get("no://forskrift/2025-03-01-100/original.lti.xml") == _whole_act_instrument_xml()
    finally:
        archive.close()
    assert len(index.commencement_instruments) == 2
    assert index.commencement_instrument_coverage.to_dict() == {
        "total_instruments": 3,
        "candidates": 1,
        "benign_non_commencement": 1,
        "blocked_unresolved": 1,
    }
    assert index.commencement_instrument_coverage.is_partition()
    assert len(index.entries) == 1
    assert index.entries[0].effective_status == "instrument_authorized"
    assert index.entries[0].effective_date == "2025-04-01"
    assert index.entries[0].raw_date_in_force == "Kongen bestemmer"
    assert [
        (item.source_id, item.replay_authorized) for item in index.commencement_instruments
    ] == [
        ("no/forskrift/2025-03-01-100", True),
        ("no/forskrift/2025-03-01-101", False),
    ]
    # The backfill-candidate advisory lane authorizes nothing itself: it mirrors
    # the index's authorization verdicts and never computes its own.
    assert report["lovtidend_commencement_instrument_count"] == 2
    assert [
        (item["source_id"], item["replay_authorized"])
        for item in report["lovtidend_commencement_instruments"]
    ] == [
        ("no/forskrift/2025-03-01-100", True),
        ("no/forskrift/2025-03-01-101", False),
    ]
    assert report["candidate_source_counts"]["lovtidend_commencement_instrument"] == 2

    replay = replay_no_to_pit(
        "no/lov/2025-01-01-1",
        as_of="2025-12-31",
        data_dir=db_path,
        index=index,
    )
    assert replay.amendments_applied == ["no/lovtid/2025-02-02-5"]
    assert replay.amendments_skipped_contingent == []
    assert replay.n_ops == 1

    before_the_instrument_date = replay_no_to_pit(
        "no/lov/2025-01-01-1",
        as_of="2025-03-31",
        data_dir=db_path,
        index=index,
    )
    assert before_the_instrument_date.amendments_applied == []
    assert before_the_instrument_date.amendments_skipped_future == ["no/lovtid/2025-02-02-5"]


def test_a_later_partial_instrument_demotes_the_whole_act_grant_end_to_end(
    tmp_path,
) -> None:
    """W-51 through ingest, index and replay: the etterretningstjenesteloven shape.

    Same archive as above but with the partial instrument staging the REST of the
    act two months after the whole-act instrument's date. Before W-51 the act
    took 2025-04-01 and replay applied every op of it from that day, including
    the ones the partial instrument says arrive on 2025-06-01 — a two-month early
    application. Now the act stays contingent and replay applies nothing.
    """
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
            ("lti/2025/sf-20250301-0100.xml", _whole_act_instrument_xml()),
            ("lti/2025/sf-20250301-0101.xml", _partial_instrument_xml()),
        ],
    )
    db_path = tmp_path / "norway.farchive"
    ingest_no_public_archives(tmp_path, db_path)
    index = build_no_amendment_index(db_path)

    assert len(index.entries) == 1
    assert index.entries[0].effective_status == "contingent"
    assert index.entries[0].effective_date is None
    assert [
        (item.source_id, item.replay_authorized) for item in index.commencement_instruments
    ] == [
        ("no/forskrift/2025-03-01-100", False),
        ("no/forskrift/2025-03-01-101", False),
    ]
    refusal = next(
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_EXECUTION_REFUSED
        and d.get("instrument_source_id") == "no/forskrift/2025-03-01-100"
    )
    assert refusal["failed_conjuncts"] == ["act_has_no_later_instrument"]

    replay = replay_no_to_pit(
        "no/lov/2025-01-01-1",
        as_of="2025-12-31",
        data_dir=db_path,
        index=index,
    )
    assert replay.amendments_applied == []
    assert replay.amendments_skipped_contingent == ["no/lovtid/2025-02-02-5"]


def test_real_corpus_whole_act_commencement_witness_when_archive_available() -> None:
    archive_path = Path("data/norway/public/lovtidend-avd1-2026.tar.bz2")
    if not archive_path.exists():
        pytest.skip("local Norway public archive is not installed")
    member_name = "lti/2026/sf-20260206-0148.xml"
    with tarfile.open(archive_path, "r:bz2") as archive:
        member = archive.getmember(member_name)
        extracted = archive.extractfile(member)
        assert extracted is not None
        payload = extracted.read()

    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2026-02-06-148",
        locator="no://forskrift/2026-02-06-148/original.lti.xml",
        archive=archive_path.name,
        member_name=member_name,
    )

    assert result.candidate is not None
    assert result.candidate.affected_law_ids == ("no/lov/2026-02-06-4",)
    assert result.candidate.replay_authorized is False


# --------------------------------------------------------------------------
# W-39, half (ii): part-scoped commencement authorization.
# --------------------------------------------------------------------------


def _no_farchive_path() -> Path | None:
    """Resolve ``norway.farchive`` the way the other NO archive tests do."""
    root = os.environ.get("LAWVM_CANONICAL_DATA_ROOT")
    if root:
        candidate = Path(root) / "data" / "norway.farchive"
        if candidate.exists():
            return candidate
    fallback = Path(__file__).resolve().parent.parent / "data" / "norway.farchive"
    return fallback if fallback.exists() else None


_NO_FARCHIVE_PATH = _no_farchive_path()


def _part_evidence(
    *,
    part_law_ids: dict[str, str],
    bound_law_ids: tuple[str, ...],
    law_section_labels: dict[str, frozenset[str]] | None = None,
) -> NOCommencementActPartEvidence:
    return NOCommencementActPartEvidence(
        part_law_ids=part_law_ids,
        bound_law_ids=bound_law_ids,
        law_section_labels=law_section_labels or {},
    )


def _part_instrument(
    source_id: str,
    *,
    changed_law_ids: tuple[str, ...],
    commenced_section_labels: tuple[str, ...] = (),
    effective_dates: tuple[str, ...] = ("2025-04-01",),
    whole_act_operative_text: bool = False,
    named_part_labels: tuple[str, ...] = (),
    affected_law_ids: tuple[str, ...] = ("no/lov/2025-02-02-5",),
) -> NOCommencementInstrumentCandidate:
    return NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=f"no://forskrift/{source_id.rsplit('/', 1)[1]}/original.lti.xml",
        archive="norway.farchive",
        member_name="",
        title="Delvis ikraftsetting av lov 2. februar 2025 nr. 5",
        affected_law_ids=affected_law_ids,
        effective_dates=effective_dates,
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
        source_excerpt="",
        changed_law_ids=changed_law_ids,
        commenced_section_labels=commenced_section_labels,
        whole_act_operative_text=whole_act_operative_text,
        named_part_labels=named_part_labels,
    )


def test_part_scoped_authorization_dates_one_part_of_a_staged_act() -> None:
    """The Endrer header names exactly part I's law, so part I's ops get a date."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-201",
                changed_law_ids=("no/lov/2001-01-05-1",),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"I": "no/lov/2001-01-05-1", "III": "no/lov/1997-06-13-55"},
                bound_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
            )
        },
    )

    assert authorization.authorizations == ()
    assert authorization.refusals == ()
    assert authorization.part_conflicts == ()
    assert len(authorization.part_authorizations) == 1
    receipt = authorization.part_authorizations[0]
    assert receipt.act_source_id == "no/lovtid/2025-02-02-5"
    assert receipt.part_label == "I"
    assert receipt.law_id == "no/lov/2001-01-05-1"
    assert receipt.effective_date == "2025-04-01"
    assert authorization.part_authorized_effective_dates() == {
        "no/lovtid/2025-02-02-5": {"no/lov/2001-01-05-1": "2025-04-01"}
    }
    detail = receipt.to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED
    assert detail["blocking"] is False
    assert detail["strict_disposition"] == "record"
    assert detail["passed_conjuncts"] == [
        str(conjunct) for conjunct in NOCommencementPartAuthorizationConjunct
    ]
    # The instrument is now a replay-authorizing instrument.
    assert [item.replay_authorized for item in authorization.instruments] == [True]


def test_part_scoped_authorization_refuses_an_endrer_spanning_two_parts() -> None:
    """The ambiguous negative control: which part did this instrument commence?

    Naming both parts' laws makes the scope undecidable from the header, so the
    instrument stays evidence and the ordinary whole-act refusal is recorded.

    W-47 keeps this refusal exactly where it was, and this test is now also its
    paired negative: the multi-part route sees the same spanning header and
    still declines, because this instrument's operative text carries no
    whole-act proof. A spanning header is never on its own a reason to grant.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-202",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"I": "no/lov/2001-01-05-1", "III": "no/lov/1997-06-13-55"},
                bound_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
            )
        },
    )

    assert authorization.part_authorizations == ()
    assert authorization.authorizations == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False]
    assert authorization.refusals[0].failed_conjuncts == (
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    )


def test_part_scoped_authorization_refuses_a_slice_of_a_part() -> None:
    """``whole_part_scope``: the Endrer match says WHICH part, not HOW MUCH.

    The instrument commences § 7 of a part whose ops span §§ 7 and 12; dating
    the whole part from it would apply § 12 years before it is in force.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-203",
                changed_law_ids=("no/lov/2001-01-05-1",),
                commenced_section_labels=("7",),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"I": "no/lov/2001-01-05-1"},
                bound_law_ids=("no/lov/2001-01-05-1",),
                law_section_labels={"no/lov/2001-01-05-1": frozenset({"7", "12"})},
            )
        },
    )

    assert authorization.part_authorizations == ()
    assert len(authorization.refusals) == 1


def test_part_scoped_authorization_admits_a_named_section_set_that_is_the_part() -> None:
    """The same conjunct's other branch: named sections == the part's own ops."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-204",
                changed_law_ids=("no/lov/1997-06-13-55",),
                commenced_section_labels=("16",),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"III": "no/lov/1997-06-13-55"},
                bound_law_ids=("no/lov/1997-06-13-55",),
                law_section_labels={"no/lov/1997-06-13-55": frozenset({"16"})},
            )
        },
    )

    assert len(authorization.part_authorizations) == 1
    assert authorization.part_authorizations[0].part_label == "III"


def test_part_scoped_authorization_refuses_a_binding_outside_the_part_map() -> None:
    """An op bound by carry-over from a law-less part must not be dated blind."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-205",
                changed_law_ids=("no/lov/2001-01-05-1",),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"I": "no/lov/2001-01-05-1"},
                bound_law_ids=("no/lov/2001-01-05-1", "no/lov/1814-05-17-0"),
            )
        },
    )

    assert authorization.part_authorizations == ()
    assert len(authorization.refusals) == 1


def test_part_scoped_authorization_conflicting_dates_refuse_both() -> None:
    """Two instruments commencing ONE part at two dates: neither is applied.

    The safety valve for a part commenced in slices by several instruments that
    each name no section: the conflict is visible as a date disagreement.
    """
    evidence = {
        "no/lovtid/2025-02-02-5": _part_evidence(
            part_law_ids={"I": "no/lov/2001-01-05-1"},
            bound_law_ids=("no/lov/2001-01-05-1",),
        )
    }
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-206",
                    changed_law_ids=("no/lov/2001-01-05-1",),
                    effective_dates=("2025-04-01",),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-207",
                    changed_law_ids=("no/lov/2001-01-05-1",),
                    effective_dates=("2026-01-01",),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=evidence,
    )

    assert authorization.part_authorizations == ()
    assert len(authorization.part_conflicts) == 1
    conflict = authorization.part_conflicts[0].to_diagnostic_detail()
    assert conflict["rule_id"] == NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT
    assert conflict["blocking"] is True
    assert conflict["effective_dates"] == ["2025-04-01", "2026-01-01"]


def test_part_route_is_disabled_without_part_evidence() -> None:
    """W-39 is opt-in at the call site: no evidence, no part route, no change."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-208",
                changed_law_ids=("no/lov/2001-01-05-1",),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.part_authorizations == ()
    assert len(authorization.refusals) == 1


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w39_corpus_witness_vaktvirksomhetsloven_both_parts_authorized() -> None:
    """W-39 joint corpus witness — the two halves land together or not at all.

    ``no/lovtid/2009-06-19-85`` is ``Kongen bestemmer.`` and stays contingent as
    an ACT. Its part I (vaktvirksomhetsloven) is commenced by
    ``no/forskrift/2011-04-01-342`` and its part III (serveringsloven) by
    ``no/forskrift/2023-05-11-690``, twelve years apart — which is why the dates
    are per-binding and the act-level status does not move. Half (i) is what
    makes part I resolve a law at all; without it this test cannot pass.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2009-06-19-85")

    assert entry.effective_status == "contingent"
    assert entry.effective_date is None
    assert entry.part_scoped_effective_dates == (
        ("no/lov/1997-06-13-55", "2023-10-01"),
        ("no/lov/2001-01-05-1", "2011-04-01"),
    )
    assert entry.effective_date_for_base("no/lov/2001-01-05-1") == (
        "2011-04-01",
        "part_instrument_authorized",
    )

    receipts = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2009-06-19-85"
    ]
    assert {(r["part_label"], r["law_id"], r["effective_date"]) for r in receipts} == {
        ("I", "no/lov/2001-01-05-1", "2011-04-01"),
        ("III", "no/lov/1997-06-13-55", "2023-10-01"),
    }
    assert {r["instrument_source_ids"][0] for r in receipts} == {
        "no/forskrift/2011-04-01-342",
        "no/forskrift/2023-05-11-690",
    }


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w39_corpus_pin_vaktvirksomhetsloven_replays_consistent() -> None:
    """W-39 joint payoff pin: the witness law goes 81 divergences -> 0.

    The whole point of landing the two halves together. Half (i) alone would
    bind the act's 22 ops to a contingent commencement and DECERTIFY this law
    (it leaves the candidate set); half (ii) alone would authorize a part that
    still produces no ops.
    """
    from lawvm.norway.verify import verify_no_against_current

    result = verify_no_against_current(
        "no/lov/2001-01-05-1", as_of="2026-07-10", data_dir=_NO_FARCHIVE_PATH
    )
    assert result.replay_status == "replayed"
    assert result.divergence_count == 0
    # All four indexed amenders apply — including the 2009 act, whose part I is
    # only reachable at all because half (ii) dated it.
    assert result.indexed_amendment_count == 4
    assert result.applied_amendment_count == 4


# --- W-47: the multi-part route -------------------------------------------
#
# The design pass behind these cases measured all 168 (instrument, act) pairs
# the W-39 matcher refused for a spanning Endrer header. Two findings set the
# shape of every test below: the header names exactly the spanned parts' laws
# in 168 of 168, so the part-to-law map is trustworthy; and eleven of the 168
# have operative text commencing strictly LESS than the header names, so the
# header is NOT evidence of the instrument's own scope. Artifacts:
# ``.tmp/w47/multipart_census.json``, ``.tmp/w47/s1_shapes.json``,
# ``.tmp/w47/guard_final.json``.


def _multi_part_evidence() -> dict[str, NOCommencementActPartEvidence]:
    """A three-part act: I and III named by the header, IV left out of it."""
    return {
        "no/lovtid/2025-02-02-5": _part_evidence(
            part_law_ids={
                "I": "no/lov/2001-01-05-1",
                "III": "no/lov/1997-06-13-55",
                "IV": "no/lov/2006-06-30-50",
            },
            bound_law_ids=(
                "no/lov/1997-06-13-55",
                "no/lov/2001-01-05-1",
                "no/lov/2006-06-30-50",
            ),
        )
    }


def test_multi_part_authorization_dates_every_part_the_header_names() -> None:
    """The positive: a whole-act text plus a spanning header dates both parts.

    Modelled on ``no/forskrift/2023-09-15-1422`` ("Ikraftsetting av lov 23.
    april 2021 nr. 25 ... Loven trer i kraft straks"), whose header spans del I
    and del II of ``no/lovtid/2021-04-23-25`` and which brings two laws into the
    candidate set at once.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-301",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.authorizations == ()
    assert authorization.part_authorizations == ()
    assert authorization.refusals == ()
    assert authorization.part_conflicts == ()
    assert len(authorization.multi_part_authorizations) == 2
    assert {
        (receipt.part_label, receipt.law_id, receipt.effective_date)
        for receipt in authorization.multi_part_authorizations
    } == {
        ("I", "no/lov/2001-01-05-1", "2025-04-01"),
        ("III", "no/lov/1997-06-13-55", "2025-04-01"),
    }
    # Every receipt records the WHOLE span it was granted under, so a reader of
    # one receipt can see it was not a one-part decision.
    assert {
        receipt.spanned_part_labels for receipt in authorization.multi_part_authorizations
    } == {("I", "III")}
    detail = authorization.multi_part_authorizations[0].to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED
    assert detail["blocking"] is False
    assert detail["strict_disposition"] == "record"
    assert detail["passed_conjuncts"] == [
        str(conjunct) for conjunct in NOCommencementMultiPartAuthorizationConjunct
    ]
    assert [item.replay_authorized for item in authorization.instruments] == [True]


def test_multi_part_authorization_leaves_the_unnamed_part_unauthorized() -> None:
    """The property that keeps the grant a SUBSET claim, asserted per part.

    Del IV amends a third law the header never names. It gets no date and no
    receipt — exactly as unresolved as before, which is what makes the route
    safe on acts whose header is narrower than their structure (measured: 17 of
    ``no/lovtid/2008-12-19-106``'s 18 parts).
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-302",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    dated = authorization.part_authorized_effective_dates()["no/lovtid/2025-02-02-5"]
    assert set(dated) == {"no/lov/1997-06-13-55", "no/lov/2001-01-05-1"}
    assert "no/lov/2006-06-30-50" not in dated
    assert not [
        receipt
        for receipt in authorization.multi_part_authorizations
        if receipt.law_id == "no/lov/2006-06-30-50"
    ]


def test_multi_part_authorization_refuses_a_text_scoped_below_the_header() -> None:
    """The paired negative for ``whole_act_operative_text``.

    The corpus case this stands for is ``no/forskrift/2012-12-07-1149``: header
    spans del I and del II, text reads "Loven del I trer i kraft 10. desember
    2012". Forgiving on the header alone would date del II years early.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-303",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=False,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 1
    assert [item.replay_authorized for item in authorization.instruments] == [False]


def test_multi_part_authorization_refuses_a_later_instrument_for_the_act() -> None:
    """The fired stop condition, kept fired: a later sibling refutes the claim.

    Without this conjunct the W-39 zero-early probe FIRES on
    ``no/lovtid/2019-12-06-76``, whose whole-act instrument is contradicted 15
    months later by one re-commencing its del I. The sibling's own scope is
    irrelevant — what it refutes is "the act came into force as a whole then".
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-304",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    whole_act_operative_text=True,
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2026-05-01-305",
                    changed_law_ids=("no/lov/2001-01-05-1",),
                    commenced_section_labels=("7",),
                    effective_dates=("2026-05-01",),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 2


def test_multi_part_authorization_admits_an_earlier_sibling() -> None:
    """The conjunct is about LATER instruments only, not about siblings at all.

    An earlier instrument commencing another part of the same act says nothing
    against "the rest came into force on this date" — which is the ordinary
    staged shape the whole lane exists for — so the span still grants.
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2024-01-01-311",
                    changed_law_ids=("no/lov/2006-06-30-50",),
                    effective_dates=("2024-01-01",),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-312",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    whole_act_operative_text=True,
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert len(authorization.multi_part_authorizations) == 2
    assert len(authorization.part_authorizations) == 1


def test_multi_part_authorization_refuses_a_non_injective_part_law_map() -> None:
    """The ambiguity conjuncts do not weaken with more parts in play.

    Two parts amend the same law, so "the part this header names" is no more
    decidable than it was at one part, and the whole span refuses.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-306",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={
                    "I": "no/lov/2001-01-05-1",
                    "II": "no/lov/2001-01-05-1",
                    "III": "no/lov/1997-06-13-55",
                },
                bound_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
            )
        },
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 1


def test_multi_part_authorization_refuses_a_binding_outside_the_part_map() -> None:
    """A carried-over binding no part owns must not be dated by a span either."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-307",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={
                    "I": "no/lov/2001-01-05-1",
                    "III": "no/lov/1997-06-13-55",
                },
                bound_law_ids=(
                    "no/lov/1997-06-13-55",
                    "no/lov/2001-01-05-1",
                    "no/lov/1814-05-17-0",
                ),
            )
        },
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 1


def test_multi_part_authorization_refuses_a_header_law_no_part_places() -> None:
    """A header naming a law the act's structure cannot place refuses the span."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-308",
                changed_law_ids=(
                    "no/lov/1814-05-17-0",
                    "no/lov/1997-06-13-55",
                    "no/lov/2001-01-05-1",
                ),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 1


def test_multi_part_authorization_refuses_a_slice_named_inside_a_spanned_part() -> None:
    """``whole_part_scope_per_part``, asserted rather than assumed.

    Unreachable through ``parse_no_commencement_instrument`` today — the text
    guard refuses any operative text containing "§" — so this drives it from a
    constructed candidate. It is the check that keeps the route safe if that
    guard is ever loosened.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-313",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                commenced_section_labels=("7",),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={
                    "I": "no/lov/2001-01-05-1",
                    "III": "no/lov/1997-06-13-55",
                },
                bound_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                law_section_labels={
                    "no/lov/2001-01-05-1": frozenset({"7", "12"}),
                    "no/lov/1997-06-13-55": frozenset({"16"}),
                },
            )
        },
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 1


def test_multi_part_route_yields_to_the_single_part_route() -> None:
    """One part is the W-39 route's business and is never re-decided here."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-309",
                changed_law_ids=("no/lov/2001-01-05-1",),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.part_authorizations) == 1
    assert authorization.part_authorizations[0].part_label == "I"


def test_multi_part_route_is_disabled_without_part_evidence() -> None:
    """Opt-in at the call site, exactly as the single-part route is."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-310",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=True,
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.multi_part_authorizations == ()
    assert len(authorization.refusals) == 1


@pytest.mark.parametrize(
    "blocks",
    [
        # The dominant corpus shape: a title sentence, then a whole-act clause.
        (
            "Ikraftsetting av lov 19. desember 2008 nr. 106 om endringer i "
            "folketrygdloven og i enkelte andre lover. Loven trer i kraft 1. mars 2010.",
        ),
        ("Loven gjelder fra 1. januar 2012.",),
        ("Lovendringene trer i kraft 1. februar 2011.",),
        ("Endringsloven trer i kraft straks.",),
        ("Lova tek til å gjelde frå 1. juli 2013.",),
        ("Lov om endringer i kirkeloven m.m. trer i kraft 1. juli 2012.",),
        ("Denne loven trer i kraft 1. januar 2020.",),
        # Multi-block: the whole-act clause need not be the only block, which is
        # one of the two reasons `_WHOLE_ACT_RE` misses this population.
        ("Loven trer i kraft fra 1. oktober 2017.", "Fremmet av Samferdselsdepartementet ."),
    ],
)
def test_whole_act_operative_text_accepts_the_measured_whole_act_shapes(
    blocks: tuple[str, ...],
) -> None:
    assert _whole_act_operative_text(blocks) is True


@pytest.mark.parametrize(
    "blocks",
    [
        # Corpus instruments whose header spans several parts and whose text
        # commences less, or cannot be shown to commence the whole act. Sources:
        # `.tmp/w47/s1_shapes.json` buckets C and D.
        ("Loven del I trer i kraft 10. desember 2012.",),
        ("Romertall II, III og IV trer i kraft 1. mars 2015.",),
        (
            "Delt ikraftsetjing av Stortinget sitt vedtak 15. desember 2017. "
            "Del VI punkt 1, endringar i lov om pensjonstrygd for sjømenn, "
            "setjast i kraft 1. januar 2018.",
        ),
        (
            "Delt ikraftsetting av loven. Loven trer i kraft 1. desember 2024, "
            "med unntak av endringene under del V.",
        ),
        (
            "Delt ikraftsetting av loven. Loven trer i kraft 21. juli 2019 med "
            "unntak av endringene i verdipapirhandelloven kapittel 3, 4, 5, 12, "
            "19 og 21.",
        ),
        (
            "Endringsloven romertall I siste setning og romertall II-VII trer i "
            "kraft 1. januar 2020.",
        ),
        # Law-scoped rather than act-scoped: the narrowing no subdivision token
        # can see, and the reason the subject half of the guard exists at all.
        ("Endringane i kommunelova m.m. skal gjelde frå 1. juli 2012.",),
        # A commencement of named sections, not of the act.
        ("§ 4 og § 7 trer i kraft 1. januar 2020.",),
        # No operative commencement statement at all.
        ("Ikraftsetting av endringsloven.",),
        (),
    ],
)
def test_whole_act_operative_text_refuses_anything_narrower(
    blocks: tuple[str, ...],
) -> None:
    assert _whole_act_operative_text(blocks) is False


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w47_corpus_witness_dates_every_part_of_a_two_part_act() -> None:
    """W-47 corpus witness: one instrument, two parts, two laws certified.

    ``no/forskrift/2023-09-15-1422`` commences ``no/lovtid/2021-04-23-25``
    ("Loven trer i kraft straks") whose Endrer header spans del I and del II.
    The act itself stays contingent — the grant is per binding — and both
    ``2013-04-12-13`` and ``2004-12-17-101`` enter the candidate set on it.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2021-04-23-25")

    assert entry.effective_status == "contingent"
    assert entry.effective_date is None
    assert entry.part_scoped_effective_dates == (
        ("no/lov/2004-12-17-101", "2023-09-15"),
        ("no/lov/2013-04-12-13", "2023-09-15"),
    )

    receipts = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2021-04-23-25"
    ]
    assert {(r["part_label"], r["law_id"]) for r in receipts} == {
        ("I", "no/lov/2013-04-12-13"),
        ("II", "no/lov/2004-12-17-101"),
    }
    assert {r["instrument_source_ids"][0] for r in receipts} == {
        "no/forskrift/2023-09-15-1422"
    }
    assert {tuple(r["spanned_part_labels"]) for r in receipts} == {("I", "II")}


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w47_corpus_negative_the_probe_witness_stays_refused() -> None:
    """The one act the later-instrument conjunct costs, pinned as a negative.

    ``no/lovtid/2019-12-06-76`` has a spanning header AND a whole-act text, and
    is refused anyway: ``no/forskrift/2020-01-10-15`` revokes part of that
    commencement and ``no/forskrift/2021-01-29-266`` re-commences del I on
    2021-03-01. Granting it would apply verdipapirhandelloven's ops 15 months
    early — the W-39 zero-early assertion firing.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2019-12-06-76")

    assert entry.part_scoped_effective_dates == ()
    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2019-12-06-76"
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w47_corpus_totals_and_the_untouched_single_part_route() -> None:
    """The route's whole corpus footprint, and W-39's pin held beside it.

    260 multi-part grants over 70 acts; the single-part route's 123 do not move,
    which is the check that the two routes are disjoint rather than competing.
    No part-date conflict appears in either route.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    multi = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED
    ]
    single = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED
    ]
    assert len(multi) == 260
    assert len({d["source_id"] for d in multi}) == 70
    assert len(single) == 123
    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT
    ]
    # F-10: every grant is a DATE, never a base_id, so neither route can bind an
    # unresolved amender and neither carries decertification risk. Asserted at
    # the receipt (no base_ids field) and at the entry (the date lands in
    # ``part_scoped_effective_dates``, and the act's ``base_ids`` are untouched).
    assert all("base_ids" not in d for d in multi)
    entries = {e.source_id: e for e in index.entries}
    for d in multi:
        entry = entries[d["source_id"]]
        assert (d["law_id"], d["effective_date"]) in entry.part_scoped_effective_dates

    # A part may resolve a law the act's lowered ops never bind — the
    # ``act_bindings_inside_part_map`` conjunct constrains bindings-to-parts, not
    # parts-to-bindings — and such a grant dates nothing: ``effective_date_for_base``
    # is only ever asked about a law in ``base_ids``. Pinned so the inert
    # population cannot grow unnoticed: 2 at W-39, 27 more at W-47, 29 total,
    # and 0 of them reachable. Cleaning them up would mean either dropping the
    # receipt (losing the commencement fact) or filtering one route and not the
    # other; recorded as a follow-up instead of decided here.
    inert = [
        (entry.source_id, law_id)
        for entry in index.entries
        for law_id, _date in entry.part_scoped_effective_dates
        if law_id not in entry.base_ids
    ]
    # W-49 adds 2 more, both unreachable for the same reason; the per-route
    # split is asserted with the W-49 totals.
    assert len(inert) == 31
    assert sum(1 for d in single if d["law_id"] not in entries[d["source_id"]].base_ids) == 2
    assert sum(1 for d in multi if d["law_id"] not in entries[d["source_id"]].base_ids) == 27


# --- W-49: the named-part-list route ---------------------------------------
#
# The design pass measured the 97 (instrument, act) pairs W-47's route refuses.
# 12 of them have an operative text naming a part LIST that covers the Endrer
# header; 20 name a list that does not, 9 of those being proven header/text
# disagreements; the reader refuses the other 65 outright. Artifacts:
# ``.tmp/w49/surface.json``, ``.tmp/w49/w49_gate.json``, ``.tmp/w49/payoff.json``.


@pytest.mark.parametrize(
    ("blocks", "expected"),
    [
        # "romertall" as the part word, plain conjunction — 2009-10-23-1295.
        (
            (
                "Lov 19. juni 2009 nr. 106 om endringer i industrikonsesjonsloven, "
                "vassdragsreguleringsloven og vannressursloven (utleie av "
                "vannkraftproduksjon mv.) romertall II og III trer i kraft 1. januar 2010.",
            ),
            ("II", "III"),
        ),
        # "del" with a comma list and a nynorsk verb — 2010-09-03-1239.
        (
            (
                "Lov 19. juni 2009 nr. 107 om endringer i jernbaneloven, "
                "jernbaneansvarsloven og COTIF-loven, lovens del II, III og IV blir "
                "sette i kraft straks.",
            ),
            ("II", "III", "IV"),
        ),
        # A bare "gjelder fra" clause — 2011-06-24-646.
        (("Lovens del I og II gjelder fra 30. juni 2011.",), ("I", "II")),
        # A five-element comma list — 2012-12-14-1208.
        (
            (
                "Lov 22. juni 2012 nr. 52 om endringer i utleveringsloven m.m. del I, "
                "II, III, IV og V trer i kraft 1. januar 2013.",
            ),
            ("I", "II", "III", "IV", "V"),
        ),
        # The reader must NOT read "UCITS V-direktivet" as part V of the act: a
        # romertall only counts when a part word opens it — 2016-12-16-1592, whose
        # list happens to name a real del V as well, so the case is about the
        # SOURCE of the label rather than its presence.
        (
            (
                "Delt ikraftsetting av Stortingets vedtak 12. desember 2016 til lov om "
                "endringer i verdipapirfondloven mv. (UCITS V-direktivet mv.). Lovens "
                "del I, II, IV og V trer i kraft 1. januar 2017.",
            ),
            ("I", "II", "IV", "V"),
        ),
        # An en-dash range plus singles — 2024-05-31-875.
        (
            (
                "Delt ikraftsetting av lov 24. november 2023 nr. 84 om endringer i "
                "forsvarsloven mv. (militær disiplinærmyndighet) del I–V og del VII og "
                "VIII. Loven trer i kraft 1. juli 2024.",
            ),
            ("I", "II", "III", "IV", "V", "VII", "VIII"),
        ),
        # A "til" range — 2026-06-12-1058.
        (
            (
                "Delt ikraftsetting av lov 12. juni 2026 om endringer i grenseloven, "
                "utlendingsloven og SIS-loven (screening av tredjelandsborgere). "
                "Følgende endringer trer i kraft 12. juni 2026: "
                "Endringsloven del I til III.",
            ),
            ("I", "II", "III"),
        ),
        # Blocks as a list, an ORPHAN part word ("deler") that opens nothing, and
        # parenthetical law names between the items — 2023-02-17-229.
        (
            (
                "Følgende deler av loven trer i kraft 1. mars 2023: del I "
                "(varemerkeloven) del II (patentloven) del III (panteloven) del IV "
                "(foretaksnavneloven) del V (designloven).",
                "del I (varemerkeloven)",
                "del V (designloven).",
            ),
            ("I", "II", "III", "IV", "V"),
        ),
        # The list repeated across blocks, as Lovdata's list markup yields it —
        # 2025-11-21-2305.
        (
            ("Følgende trer i kraft 1. januar 2026: Romertall IV og V", "Romertall IV og V"),
            ("IV", "V"),
        ),
    ],
)
def test_named_part_labels_reads_the_measured_list_shapes(
    blocks: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert _named_part_labels(blocks) == expected


@pytest.mark.parametrize(
    "blocks",
    [
        # --- the proven header/text disagreements the READER itself refuses ---
        # A sub-part qualifier the W-47 guard never needed: part I is commenced
        # only in its LAST SENTENCE (no/forskrift/2019-11-22-1552). Reading the
        # list naively would date the whole of del I.
        (
            "Endringsloven romertall I siste setning og romertall II–VII trer i "
            "kraft 1. januar 2020.",
        ),
        # A punkt qualifier (no/forskrift/2017-12-19-2156).
        (
            "Delt ikraftsetjing av Stortinget sitt vedtak 15. desember 2017. Del VI "
            "punkt 1, endringar i lov om pensjonstrygd for sjømenn, setjast i kraft "
            "1. januar 2018.",
        ),
        # An exception carving a hole in the list (no/forskrift/2024-11-29-2890).
        (
            "Delt ikraftsetting av loven. Loven trer i kraft 1. desember 2024, med "
            "unntak av endringene under del V.",
        ),
        # An exception scoped by chapter (no/forskrift/2019-06-21-802).
        (
            "Delt ikraftsetting av loven. Loven trer i kraft 21. juli 2019 med unntak "
            "av endringene i verdipapirhandelloven kapittel 3, 4, 5, 12, 19 og 21.",
        ),
        # "avsnitt" as a part word is not in this reader's vocabulary, and the
        # chapter this one adds is why (no/forskrift/2013-02-01-130).
        (
            "Lov 19. juni 2009 nr. 75 om endringer i straffeloven og "
            "straffeprosessloven avsnitt I og nytt kapittel 16 c i "
            "straffeprosessloven, trer i kraft straks.",
        ),
        # --- the hazard classes, as such ---
        # A section sign anywhere: the slice surface, W-41's business.
        ("Del I § 3 og del II trer i kraft 1. januar 2020.",),
        # A ledd qualifier.
        ("Del I første ledd og del II trer i kraft 1. januar 2020.",),
        # A bokstav qualifier.
        ("Del I bokstav a og del II trer i kraft 1. januar 2020.",),
        # A part deferred to a delegated date: one ISO date, two scopes.
        (
            "Del I og del II trer i kraft 1. januar 2020. Del III trer i kraft fra "
            "det tidspunkt departementet bestemmer.",
        ),
        # Two commencement clauses, hence two scopes, hence no single list.
        ("Del I trer i kraft straks. Del II trer i kraft 1. januar 2027.",),
        # No commencement clause at all.
        ("Ikraftsetting av endringsloven del I og del II.",),
        # A whole-act text: W-47's business, and this reader must not claim it.
        ("Loven trer i kraft 1. januar 2020.",),
        # A range that never gets its second end.
        ("Del I– trer i kraft 1. januar 2020.",),
        # A descending range is not a range.
        ("Del V–I trer i kraft 1. januar 2020.",),
        # An orphan part word alone names nothing.
        ("Følgende deler av loven trer i kraft 1. januar 2020.",),
        (),
    ],
)
def test_named_part_labels_refuses_everything_it_cannot_account_for(
    blocks: tuple[str, ...],
) -> None:
    assert _named_part_labels(blocks) == ()


def test_named_part_list_and_whole_act_readers_are_mutually_exclusive() -> None:
    """The two routes cannot both fire, and the reason is structural.

    ``_whole_act_operative_text``'s refusing half lists ``del`` and ``romertall``
    among the subdivision tokens, and ``_named_part_labels`` needs one of those
    words to open a list at all. So no text can satisfy both, and the ordering
    between the W-47 and W-49 routes is a formality rather than a tie-break.
    """
    part_list = ("Lovens del I og II gjelder fra 30. juni 2011.",)
    whole_act = ("Loven trer i kraft 1. januar 2020.",)

    assert _named_part_labels(part_list) == ("I", "II")
    assert _whole_act_operative_text(part_list) is False
    assert _named_part_labels(whole_act) == ()
    assert _whole_act_operative_text(whole_act) is True


def test_named_part_list_authorization_dates_every_part_the_list_covers() -> None:
    """The positive: a list covering the header dates each part the header names.

    Modelled on ``no/forskrift/2011-06-24-646`` ("Lovens del I og II gjelder fra
    30. juni 2011") against ``no/lovtid/2011-06-24-31``, whose Endrer header
    spans two of the act's five parts.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-401",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                named_part_labels=("I", "III"),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.authorizations == ()
    assert authorization.part_authorizations == ()
    assert authorization.multi_part_authorizations == ()
    assert authorization.refusals == ()
    assert len(authorization.named_part_list_authorizations) == 2
    assert {
        (receipt.part_label, receipt.law_id, receipt.effective_date)
        for receipt in authorization.named_part_list_authorizations
    } == {
        ("I", "no/lov/2001-01-05-1", "2025-04-01"),
        ("III", "no/lov/1997-06-13-55", "2025-04-01"),
    }
    detail = authorization.named_part_list_authorizations[0].to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED
    assert detail["blocking"] is False
    assert detail["strict_disposition"] == "record"
    assert detail["named_part_labels"] == ["I", "III"]
    assert detail["spanned_part_labels"] == ["I", "III"]
    assert detail["passed_conjuncts"] == [
        str(conjunct) for conjunct in NOCommencementNamedPartListAuthorizationConjunct
    ]
    assert [item.replay_authorized for item in authorization.instruments] == [True]


def test_named_part_list_authorization_dates_only_the_parts_the_header_names() -> None:
    """A list wider than the header still dates only the header's parts.

    ``no/forskrift/2010-09-03-1239`` names del II, III and IV under a II/III
    header; ``no/forskrift/2016-12-16-1592`` names I, II, IV and V under an
    I/II/IV one. The extra part is simply not dated — the grant stays a SUBSET
    of what the text commences, which is the whole licensing argument.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-402",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                named_part_labels=("I", "III", "IV"),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    dated = authorization.part_authorized_effective_dates()["no/lovtid/2025-02-02-5"]
    assert set(dated) == {"no/lov/1997-06-13-55", "no/lov/2001-01-05-1"}
    assert "no/lov/2006-06-30-50" not in dated
    assert {
        receipt.named_part_labels
        for receipt in authorization.named_part_list_authorizations
    } == {("I", "III", "IV")}


def test_named_part_list_authorization_refuses_a_list_narrower_than_the_header() -> None:
    """The negative suite's own shape: the list misses a part the header spans.

    Six of the eleven proven W-47 header/text disagreements are refused right
    here — ``no/forskrift/2012-12-07-1149`` ("Loven del I", header I+II),
    ``2014-12-19-1735`` (text II/III/IV, header I/III/IV), ``2016-06-17-706``,
    ``2017-06-16-758``, ``2012-12-14-1324``, ``2024-11-11-2739``. Forgiving any
    of them would date a part years early.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-403",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                named_part_labels=("I",),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.named_part_list_authorizations == ()
    assert len(authorization.refusals) == 1
    assert [item.replay_authorized for item in authorization.instruments] == [False]


def test_named_part_list_authorization_refuses_an_unreadable_text() -> None:
    """No list, no route: an empty label tuple is the reader's REFUSAL."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-404",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                named_part_labels=(),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.named_part_list_authorizations == ()
    assert len(authorization.refusals) == 1


def test_named_part_list_admits_a_later_instrument_on_other_parts() -> None:
    """Half one of the per-part refutation: the staged pattern must NOT refute.

    A later instrument commencing del IV — another part of the same act, by both
    its declared laws and its own named list — says nothing against "del I and
    del III commenced then". W-47's act-global conjunct would refuse this, and
    measured over the corpus that is what it costs: two of this route's twelve
    pairs (``no/forskrift/2009-10-23-1295`` and ``2016-12-16-1592``) exist only
    because the refutation is per part.
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-405",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    named_part_labels=("I", "III"),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2026-05-01-406",
                    changed_law_ids=("no/lov/2006-06-30-50",),
                    named_part_labels=("IV",),
                    effective_dates=("2026-05-01",),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert len(authorization.named_part_list_authorizations) == 2
    # The later instrument is a single-part match in its own right, and takes
    # the single-part route: the two coexist on one act at two dates.
    assert len(authorization.part_authorizations) == 1


def test_named_part_list_refuses_a_later_instrument_naming_a_claimed_part() -> None:
    """Half two: a later instrument re-commencing a NAMED part DOES refute.

    This is the W-47 revocation witness in list form. On the real corpus the
    witness is ``no/lovtid/2019-12-06-76``, whose whole-act instrument is
    followed by ``no/forskrift/2021-01-29-266`` re-commencing del I on
    2021-03-01; had the first instrument named "del I og del II" instead of
    commencing the act whole, this is the conjunct that would still catch it.
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-407",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    named_part_labels=("I", "III"),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2026-05-01-408",
                    changed_law_ids=("no/lov/2001-01-05-1",),
                    named_part_labels=("I",),
                    effective_dates=("2026-05-01",),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.named_part_list_authorizations == ()


def test_named_part_list_refuses_a_later_instrument_it_cannot_read() -> None:
    """A later text the reader cannot account for bounds nothing, so it refutes.

    The corpus case is ``no/forskrift/2015-09-18-1059``, whose declared laws put
    it in del I of ``no/lovtid/2012-01-20-7`` — disjoint from the II/III/IV claim
    of ``no/forskrift/2012-01-20-36`` — but whose own text the reader refuses.
    One clear witness is not two, so the pair does not grant.
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-409",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    named_part_labels=("I", "III"),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2026-05-01-410",
                    changed_law_ids=("no/lov/2006-06-30-50",),
                    commenced_section_labels=("7",),
                    effective_dates=("2026-05-01",),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.named_part_list_authorizations == ()


def test_named_part_list_refuses_when_the_two_witnesses_disagree() -> None:
    """A later instrument whose header is coarser than its text still refutes.

    ``no/forskrift/2017-06-16-758``'s text commences only del III while its
    Endrer header spans del I, II and III, and it is the later sibling of
    ``no/forskrift/2017-09-01-1328``'s del I / del II claim. The textual witness
    clears; the structural one does not. Refusing on disagreement costs exactly
    this one pair, and it is the price of not adjudicating a header/text
    disagreement inside a route whose whole premise is that they exist.
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-411",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    named_part_labels=("I", "III"),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2026-05-01-412",
                    changed_law_ids=("no/lov/2001-01-05-1", "no/lov/2006-06-30-50"),
                    named_part_labels=("IV",),
                    effective_dates=("2026-05-01",),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.named_part_list_authorizations == ()


def test_named_part_list_admits_an_earlier_sibling() -> None:
    """The conjunct is about LATER instruments only, exactly as at W-47.

    The earlier sibling here commences del IV, a part outside the claim; had it
    commenced del I the claim would still hold, but the I grant would be the
    single-part route's rather than this one's — the yield, not a refusal.
    """
    authorization = authorize_no_commencement_instruments(
        [
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2024-01-01-413",
                    changed_law_ids=("no/lov/2006-06-30-50",),
                    named_part_labels=("IV",),
                    effective_dates=("2024-01-01",),
                ),
            ),
            (
                NOCommencementParseStatus.BLOCKED_UNRESOLVED,
                _part_instrument(
                    "no/forskrift/2025-03-01-414",
                    changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                    named_part_labels=("I", "III"),
                ),
            ),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert len(authorization.named_part_list_authorizations) == 2


def test_named_part_list_refuses_a_two_act_instrument() -> None:
    """One document commencing parts of two acts merges two lists into one.

    ``no/forskrift/2020-04-29-885`` commences del I and del II of
    ``2018-04-20-12`` and del II of ``2019-03-08-5`` in one text; read joined,
    nothing in the merged list says which act each label belongs to.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-415",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                named_part_labels=("I", "III"),
                affected_law_ids=("no/lov/2025-02-02-5", "no/lov/2024-01-01-9"),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert authorization.named_part_list_authorizations == ()
    assert len(authorization.refusals) == 1


def test_named_part_list_route_yields_to_the_multi_part_route() -> None:
    """Ordering, asserted rather than assumed.

    The two readers are mutually exclusive on real text, so this can only be
    reached by a hand-built candidate — which is exactly why it is worth
    pinning: if the guards ever overlap, the older proof must win.
    """
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-416",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                whole_act_operative_text=True,
                named_part_labels=("I", "III"),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence=_multi_part_evidence(),
    )

    assert len(authorization.multi_part_authorizations) == 2
    assert authorization.named_part_list_authorizations == ()


def test_named_part_list_route_is_disabled_without_part_evidence() -> None:
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _part_instrument(
                "no/forskrift/2025-03-01-417",
                changed_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
                named_part_labels=("I", "III"),
            ),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.named_part_list_authorizations == ()
    assert len(authorization.refusals) == 1


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w49_corpus_witness_dates_the_two_parts_a_list_names() -> None:
    """W-49 corpus witness: the staged act the per-part refutation unlocks.

    ``no/forskrift/2009-10-23-1295`` commences "romertall II og III" of
    ``no/lovtid/2009-06-19-106``; ``no/forskrift/2010-06-25-938`` commences its
    del I nine months later. Under W-47's act-global conjunct that later sibling
    would refuse the whole span — here it clears both witnesses and the two
    parts take their date.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2009-06-19-106")

    assert entry.effective_status == "contingent"
    assert entry.effective_date is None
    assert ("no/lov/1917-12-14-17", "2010-01-01") in entry.part_scoped_effective_dates
    assert ("no/lov/2000-11-24-82", "2010-01-01") in entry.part_scoped_effective_dates

    receipts = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2009-06-19-106"
    ]
    assert {(r["part_label"], r["law_id"]) for r in receipts} == {
        ("II", "no/lov/1917-12-14-17"),
        ("III", "no/lov/2000-11-24-82"),
    }
    assert {r["instrument_source_ids"][0] for r in receipts} == {
        "no/forskrift/2009-10-23-1295"
    }
    assert {tuple(r["named_part_labels"]) for r in receipts} == {("II", "III")}


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w49_corpus_negatives_the_proven_disagreements_stay_refused() -> None:
    """The eleven proven header/text disagreements, pinned as negatives.

    Each of these acts has an instrument whose text commences strictly less than
    its Endrer header names. None of them may pick up a named-part-list grant
    from that instrument.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    granted = {
        (d["source_id"], d["instrument_source_ids"][0])
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED
    }
    disagreements = {
        ("no/lovtid/2012-12-07-71", "no/forskrift/2012-12-07-1149"),
        ("no/lovtid/2012-12-14-82", "no/forskrift/2012-12-14-1324"),
        ("no/lovtid/2017-06-16-66", "no/forskrift/2017-06-16-758"),
        ("no/lovtid/2017-12-19-113", "no/forskrift/2017-12-19-2156"),
        ("no/lovtid/2024-11-29-73", "no/forskrift/2024-11-29-2890"),
        ("no/lovtid/2019-06-21-41", "no/forskrift/2019-06-21-802"),
        ("no/lovtid/2013-06-21-79", "no/forskrift/2014-12-19-1735"),
        ("no/lovtid/2016-06-17-48", "no/forskrift/2016-06-17-706"),
        ("no/lovtid/2016-04-22-4", "no/forskrift/2019-11-22-1552"),
        ("no/lovtid/2009-06-19-75", "no/forskrift/2013-02-01-130"),
        ("no/lovtid/2018-12-20-115", "no/forskrift/2024-11-11-2739"),
    }
    assert granted & disagreements == set()
    # ``2016-04-22-4`` is the one whose list READS as a superset of its header
    # (romertall I plus II-VII against an I-VI header) and is refused only
    # because "siste setning" qualifies part I. It gets no part date at all.
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2016-04-22-4")
    assert entry.part_scoped_effective_dates == ()


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w49_corpus_totals_and_the_untouched_older_routes() -> None:
    """The route's whole corpus footprint, with the two older pins beside it.

    33 named-part-list grants over 10 acts; W-39's 123 and W-47's 260 do not
    move, which is the check that the three routes are disjoint rather than
    competing. No part-date conflict appears in any of them.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    named = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED
    ]
    multi = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED
    ]
    single = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED
    ]
    assert len(named) == 33
    assert len({d["source_id"] for d in named}) == 10
    assert len(multi) == 260
    assert len(single) == 123
    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT
    ]
    # No binding is claimed by two routes.
    keys = [
        (d["source_id"], d["part_label"], d["law_id"]) for d in named + multi + single
    ]
    assert len(set(keys)) == len(keys)

    # F-10: dates only, never base_ids — the property that keeps every part
    # route free of decertification risk.
    assert all("base_ids" not in d for d in named)
    entries = {e.source_id: e for e in index.entries}
    for d in named:
        entry = entries[d["source_id"]]
        assert (d["law_id"], d["effective_date"]) in entry.part_scoped_effective_dates

    # P2 / corruption immunity, asserted at the corpus: the reader refuses any
    # text containing "§" and ``_COMMENCED_SECTION_RE`` can only emit a label
    # from a "§", so no W-49 grant has a section label at all — the W-48
    # ordinal-swallowing defect has nothing here to corrupt.
    instruments = {c.source_id: c for c in index.commencement_instruments}
    for d in named:
        for instrument_id in d["instrument_source_ids"]:
            assert instruments[instrument_id].commenced_section_labels == ()
            assert instruments[instrument_id].named_part_labels != ()

    # The inert population grows by 2 and stays unreachable (W-39 2, W-47 27).
    assert sum(1 for d in named if d["law_id"] not in entries[d["source_id"]].base_ids) == 2


# --------------------------------------------------------------------------
# W-51: the shipped whole-act route's soundness repair.
#
# The W-50 sizing pass ran the act-level zero-early probe over the corpus's 542
# whole-act authorizations for the first time and found the OLDEST route in
# breach: 8 EARLY rows over 5 acts. Three repairs, measured in ``.tmp/w51/``:
# a sharpened sibling predicate (5 of the 8 rows were forskrift instruments
# citing the act as hjemmel), a fence on ``_WHOLE_ACT_RE``'s carve-out tail, and
# the act-level refutation W-47's route already asserted.
# --------------------------------------------------------------------------


def _sibling_xml(
    *,
    title: str,
    based_on: str,
    date_in_force: str,
    body: str,
    endrer: str | None = None,
) -> bytes:
    endrer_block = (
        f'<dd class="changesToDocuments"><ul>{endrer}</ul></dd>' if endrer else ""
    )
    return (
        f'<html><body><dd class="title">{title}</dd>'
        f'<dd class="basedOn"><ul><li>{based_on}</li></ul></dd>'
        f"{endrer_block}"
        f'<dd class="dateInForce">{date_in_force}</dd>'
        f'<main class="documentBody"><article class="legalP">{body}</article></main>'
        "</body></html>"
    ).encode("utf-8")


def _hjemmel_only(payload: bytes) -> bool:
    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2025-03-01-900",
        locator="no://forskrift/2025-03-01-900/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0900.xml",
    )
    assert result.candidate is not None
    return result.candidate.cites_acts_as_hjemmel_only


def test_hjemmel_only_reader_excludes_a_forskrift_commencement() -> None:
    """The measured artefact shape, both witnesses holding.

    ``no/forskrift/2016-06-29-845`` commences forskrift 2006-04-21-433, declares
    exactly that forskrift in its ``Endrer`` block, and cites fiskesalslagslova
    only as the hjemmel it was made under. The act-level probe read it as
    fiskesalslagslova still commencing something in 2023.
    """
    assert _hjemmel_only(
        _sibling_xml(
            title="Ikrafttredelse av forskrift 21. april 2006 nr. 433 om transitt av fisk",
            based_on="lov/2013-06-21-75/§8",
            date_in_force="2016-09-01",
            endrer="<li>forskrift/2006-04-21-433</li>",
            body=(
                "Forskrift 21. april 2006 nr. 433 om transitt av fisk trer i kraft "
                "1. september 2016."
            ),
        )
    )


def test_hjemmel_only_reader_keeps_a_sibling_with_no_endrer_block() -> None:
    """The structural witness must be POSITIVE, not merely absent.

    ``no/forskrift/2021-08-26-2589`` — the genuine sibling that refutes
    bredbåndsutbyggingsloven's whole-act grant — declares no ``Endrer`` block at
    all. An absent block proves nothing about what the instrument commences, so
    the sibling stays in.
    """
    assert not _hjemmel_only(
        _sibling_xml(
            title="Delt ikraftsetting av lov 7. mai 2020 nr. 40",
            based_on="lov/2020-05-07-40/§26",
            date_in_force="2021-10-01",
            body=(
                "Delt ikraftsetting av lov 7. mai 2020 nr. 40 om tilrettelegging for "
                "utbygging av høyhastighetsnett for elektronisk kommunikasjon "
                "(bredbåndsutbyggingsloven). Lovens kapittel 6 trer i kraft "
                "1. oktober 2021."
            ),
        )
    )


def test_hjemmel_only_reader_keeps_a_sibling_declaring_a_law() -> None:
    """``no/forskrift/2021-08-26-2581``: the Endrer block names the act itself."""
    assert not _hjemmel_only(
        _sibling_xml(
            title="Delt ikrafttredelse av lov om Etterretningstjenesten kapittel 7 og 8",
            based_on="lov/2020-06-19-77/§12-1",
            date_in_force="2022-01-01",
            endrer="<li>lov/2020-06-19-77</li>",
            body=(
                "Delt ikraftsetting av lov 19. juni 2020 nr. 77 om Etterretningstjenesten "
                "(etterretningstjenesteloven). Loven kapittel 7 og 8 trer i kraft "
                "1. januar 2022, med unntak av § 7-3."
            ),
        )
    )


def test_hjemmel_only_reader_keeps_an_act_commencement_rewriting_a_resolution() -> None:
    """The textual witness earning its keep, on a measured shape.

    ``no/forskrift/2013-12-13-1449`` POSTPONES an act's commencement, and its
    ``Endrer`` block names only the kongelig resolusjon it rewrites — so the
    structural witness alone would drop the most refuting sibling there is.
    The definite act-word in its text keeps it. Eight instruments in the corpus
    are held back by this second witness; 242 clear the structural one and 234
    clear both.
    """
    assert not _hjemmel_only(
        _sibling_xml(
            title="Utsatt ikrafttredelse av lov 28. mai 2010 nr. 16",
            based_on="lov/2010-05-28-16/§74",
            date_in_force="2014-07-01",
            endrer="<li>forskrift/2013-09-27-1132</li>",
            body=(
                "I kongelig resolusjon 27. september 2013 nr. 1132 gjøres følgende "
                "endringer: Loven trer i kraft 1. juli 2014, unntatt § 57 som trer i "
                "kraft senere."
            ),
        )
    )


def test_hjemmel_only_reader_is_not_fooled_by_a_short_title_compound() -> None:
    """``folkehelseloven`` is not the definite act-word ``loven``.

    ``no/forskrift/2018-10-23-1603`` names the act in full — "med hjemmel i lov
    24. juni 2011 nr. 29 om folkehelsearbeid (folkehelseloven) § 21" — while
    commencing a forskrift amendment. The word boundary is what makes the
    textual witness hold here, and it is the reason the reader looks for the
    bare definite form rather than for the act's name.
    """
    assert _hjemmel_only(
        _sibling_xml(
            title="Vedtak om ikrafttredelse av forskrift 11. mai 2018 nr. 724",
            based_on="lov/2011-06-24-29/§21",
            date_in_force="2018-10-23",
            endrer="<li>forskrift/2018-05-11-724</li>",
            body=(
                "Forskriftsendringen (forskrift 11. mai 2018 nr. 724) er fastsatt av "
                "Helse- og omsorgsdepartementet 11. mai 2018 med hjemmel i lov 24. juni "
                "2011 nr. 29 om folkehelsearbeid (folkehelseloven) § 21 fjerde ledd. "
                "Forskriftsendringen trer i kraft straks."
            ),
        )
    )


@pytest.mark.parametrize(
    "tail",
    [
        # The live breach: bredbåndsutbyggingsloven's chapter 6, commenced 15
        # months later by ``no/forskrift/2021-08-26-2589``.
        ", med unntak av kapittel 6 om sentral informasjonstjeneste, som trer i "
        "kraft når departementet bestemmer",
        ", unntatt bestemmelsene om klage",
        ", med unntak for del V",
        ", bortsett fra kapittel 3",
        " for så vidt gjelder del I",
        ". Kapittel 4 settes foreløpig ikke i kraft",
        ", likevel slik at tredje ledd trer i kraft senere",
        ". Romertall II trer i kraft senere",
        ", med unntak av punkt 3",
        ", men bokstav c gjelder først fra 2027",
    ],
)
def test_whole_act_scope_refuses_a_carve_out_in_the_regex_tail(tail: str) -> None:
    """W-51 repair two: ``[^§]{0,400}$`` may not swallow an exception.

    The head of every one of these is a clean "Loven trer i kraft <date>" that
    ``_WHOLE_ACT_RE`` matches end to end; what the fence reads is the tail. The
    first assertion is what makes this a test OF THE FENCE rather than of some
    other refusal: the shipped pattern still accepts every one of these texts.
    """
    body = f"Loven trer i kraft 1. april 2025{tail}."
    assert _WHOLE_ACT_RE.fullmatch(body) is not None
    payload = _sibling_xml(
        title="Ikraftsetting av lov 2. februar 2025 nr. 5",
        based_on="lov/2025-02-02-5/§26",
        date_in_force="2025-04-01",
        body=body,
    )
    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2025-03-01-901",
        locator="no://forskrift/2025-03-01-901/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0901.xml",
    )
    assert result.parse_status is NOCommencementParseStatus.BLOCKED_UNRESOLVED
    assert result.candidate is not None
    assert result.candidate.scope_status is NOCommencementScopeStatus.UNRESOLVED


@pytest.mark.parametrize(
    "body",
    [
        # The bare shape, and the overwhelming majority of the 607.
        "Loven trer i kraft 1. april 2025.",
        "Lova trer i verk 1. april 2025.",
        "Denne loven trer i kraft 1. april 2025.",
        # An innocuous tail: it narrows nothing about WHICH provisions commence.
        "Loven trer i kraft 1. april 2025 med virkning for regnskapsår påbegynt "
        "etter 31. desember 2024.",
        "Loven trer i kraft 1. april 2025. Fremmet av Finansdepartementet.",
    ],
)
def test_whole_act_scope_still_accepts_an_unqualified_commencement(body: str) -> None:
    """The fence is refusing only: it may not cost the shape the route exists for."""
    payload = _sibling_xml(
        title="Ikraftsetting av lov 2. februar 2025 nr. 5",
        based_on="lov/2025-02-02-5/§26",
        date_in_force="2025-04-01",
        body=body,
    )
    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2025-03-01-902",
        locator="no://forskrift/2025-03-01-902/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0902.xml",
    )
    assert result.parse_status is NOCommencementParseStatus.CANDIDATE
    assert result.candidate is not None
    assert result.candidate.scope_status is NOCommencementScopeStatus.WHOLE_ACT


def test_whole_act_authorization_refuses_a_later_instrument_for_the_act() -> None:
    """W-51 repair three, the refuting direction.

    The etterretningstjenesteloven shape: a clean whole-act instrument dates the
    act at 2021-01-01 while a later one commences its chapters 7 and 8 on
    2022-01-01. The act-level claim is that EVERY op was in force on the granted
    day, so any later commencement of any part of the act refutes it — there is
    no disjointness to prove, unlike W-49's per-part claim, because a whole-act
    claim leaves no part of the act unclaimed.
    """
    whole = _instrument_candidate(
        "no/forskrift/2025-03-01-910",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    later = _instrument_candidate(
        "no/forskrift/2026-01-05-911",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2026-01-05",),
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, whole),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, later),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert [item.replay_authorized for item in authorization.instruments] == [False, False]
    refusal = next(
        r for r in authorization.refusals if r.instrument_source_id.endswith("910")
    )
    assert refusal.failed_conjuncts == (
        NOCommencementAuthorizationConjunct.ACT_HAS_NO_LATER_INSTRUMENT,
    )
    detail = refusal.to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_EXECUTION_REFUSED
    assert detail["failed_conjuncts"] == ["act_has_no_later_instrument"]
    assert detail["source_id"] == "no/lovtid/2025-02-02-5"


def test_whole_act_authorization_admits_an_earlier_sibling() -> None:
    """An earlier instrument says nothing against "the rest commenced later"."""
    earlier = _instrument_candidate(
        "no/forskrift/2024-01-01-912",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2024-01-01",),
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
    )
    whole = _instrument_candidate(
        "no/forskrift/2025-03-01-913",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, earlier),
            (NOCommencementParseStatus.CANDIDATE, whole),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorized_effective_dates() == {
        "no/lovtid/2025-02-02-5": "2025-04-01"
    }


def test_whole_act_authorization_admits_a_later_hjemmel_only_sibling() -> None:
    """The sharpening, at the gate: a hjemmel citation is not a sibling.

    Without it this is one of the five artefact rows the W-50 probe reported —
    a forskrift commencement whose enabling statute is the act.
    """
    whole = _instrument_candidate(
        "no/forskrift/2025-03-01-914",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    hjemmel = dataclass_replace(
        _instrument_candidate(
            "no/forskrift/2026-01-05-915",
            affected_law_ids=("no/lov/2025-02-02-5",),
            effective_dates=("2026-01-05",),
            scope_status=NOCommencementScopeStatus.UNRESOLVED,
        ),
        cites_acts_as_hjemmel_only=True,
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, whole),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, hjemmel),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorized_effective_dates() == {
        "no/lovtid/2025-02-02-5": "2025-04-01"
    }


def test_whole_act_refutation_is_per_act_not_per_instrument() -> None:
    """One instrument commencing two acts is refuted on only the refuted one."""
    whole = _instrument_candidate(
        "no/forskrift/2025-03-01-916",
        affected_law_ids=("no/lov/2025-02-02-5", "no/lov/2025-02-02-6"),
        effective_dates=("2025-04-01",),
    )
    later = _instrument_candidate(
        "no/forskrift/2026-01-05-917",
        affected_law_ids=("no/lov/2025-02-02-6",),
        effective_dates=("2026-01-05",),
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, whole),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, later),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5", "no/lovtid/2025-02-02-6"},
    )

    assert authorization.authorized_effective_dates() == {
        "no/lovtid/2025-02-02-5": "2025-04-01"
    }
    assert [
        r.act_source_id
        for r in authorization.refusals
        if r.failed_conjuncts
        == (NOCommencementAuthorizationConjunct.ACT_HAS_NO_LATER_INSTRUMENT,)
    ] == ["no/lovtid/2025-02-02-6"]


def test_whole_act_date_conflict_still_blocks_under_the_refutation() -> None:
    """The refutation is asserted AFTER the conflict branch, deliberately.

    Two instruments giving one act two whole-act dates is a contradiction the
    lane blocks on. Applied while proposals are gathered, the refutation would
    resolve every such disagreement in favour of the later date and the blocking
    receipt would never be written. Measured, the corpus carries no whole-act
    date conflict, so the ordering costs nothing and keeps the louder verdict.
    """
    first = _instrument_candidate(
        "no/forskrift/2025-03-01-918",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    second = _instrument_candidate(
        "no/forskrift/2025-03-01-919",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-07-01",),
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, first),
            (NOCommencementParseStatus.CANDIDATE, second),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert len(authorization.conflicts) == 1
    assert authorization.conflicts[0].effective_dates == ("2025-04-01", "2025-07-01")


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w51_corpus_the_two_demoted_acts_and_their_repairs() -> None:
    """The whole measured cost of the repair: two acts, one per mechanism.

    ``no/lovtid/2020-05-07-40`` (bredbåndsutbyggingsloven) falls to the CARVE-OUT
    FENCE — its instrument's text excepts kapittel 6 — so its instrument is no
    longer a candidate at all. ``no/lovtid/2020-06-19-77``
    (etterretningstjenesteloven) falls to the REFUTATION — its instrument is
    still a clean whole-act candidate, and the receipt says which conjunct
    failed. Both were live P1 breaches: chapter 6 commenced 2021-10-01 against a
    2020-07-01 grant, chapters 7 and 8 on 2022-01-01 against 2021-01-01.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entries = {e.source_id: e for e in index.entries}
    instruments = {c.source_id: c for c in index.commencement_instruments}

    for act_id in ("no/lovtid/2020-05-07-40", "no/lovtid/2020-06-19-77"):
        assert entries[act_id].effective_status == "contingent"
        assert entries[act_id].effective_date is None
        assert entries[act_id].part_scoped_effective_dates == ()

    # The fenced one is no longer a whole-act candidate at all, and W-47's
    # reader had always refused its text for the same reason (the exception
    # phrase is in ``_SUBDIVISION_SCOPE_RE`` too) — which is exactly the
    # inconsistency W-51 removes: two readers of the same sentence disagreeing.
    fenced = instruments["no/forskrift/2020-05-07-944"]
    assert fenced.scope_status is NOCommencementScopeStatus.UNRESOLVED
    assert fenced.whole_act_operative_text is False
    assert fenced.effective_dates == ("2020-07-01",)
    # The sibling that made the old grant a live breach.
    chapter_six = instruments["no/forskrift/2021-08-26-2589"]
    assert chapter_six.effective_dates == ("2021-10-01",)
    assert chapter_six.affected_law_ids == ("no/lov/2020-05-07-40",)
    assert chapter_six.cites_acts_as_hjemmel_only is False

    refuted = instruments["no/forskrift/2020-06-19-1231"]
    assert refuted.scope_status is NOCommencementScopeStatus.WHOLE_ACT
    refusals = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_EXECUTION_REFUSED
        and "act_has_no_later_instrument" in (d.get("failed_conjuncts") or [])
    ]
    assert [(d["source_id"], d["instrument_source_id"]) for d in refusals] == [
        ("no/lovtid/2020-06-19-77", "no/forskrift/2020-06-19-1231")
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w51_corpus_zero_early_over_every_whole_act_grant() -> None:
    """P1, promoted from a measurement of the gate to a property of it.

    The probe W-50 ran from the outside, run here over the sharpened sibling
    set: no whole-act grant has a later commencement-relevant sibling. Given the
    conjunct that is now close to a tautology — which is the point of moving it
    inside — so the assertion that carries information is the second one: the
    234 sibling exclusions did not hide a breach, because every one of them is
    an instrument whose ``Endrer`` block declares no law at all.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    instruments = {c.source_id: c for c in index.commencement_instruments}
    dates_by_act: dict[str, list[tuple[str, str]]] = {}
    for candidate in index.commencement_instruments:
        if candidate.cites_acts_as_hjemmel_only:
            continue
        for law_id in candidate.affected_law_ids:
            act_id = no_commencement_act_id_from_law_id(law_id)
            if not act_id:
                continue
            for date in candidate.effective_dates:
                dates_by_act.setdefault(act_id, []).append((candidate.source_id, date))

    grants = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    ]
    assert len(grants) == 540
    early = [
        (d["source_id"], d["effective_date"], sibling_id, sibling_date)
        for d in grants
        for sibling_id, sibling_date in dates_by_act.get(d["source_id"], ())
        if sibling_id not in set(d["instrument_source_ids"])
        and sibling_date > d["effective_date"]
    ]
    assert early == []

    excluded = [c for c in instruments.values() if c.cites_acts_as_hjemmel_only]
    assert len(excluded) == 234
    assert all(c.changed_law_ids == () for c in excluded)


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w51_corpus_totals_and_the_untouched_part_routes() -> None:
    """The repair's whole corpus footprint, with the three part pins beside it.

    540 whole-act grants (542 - 2), and W-39's 123, W-47's 260 and W-49's 33 do
    NOT move. That is the check the sharpening owes: it only ever removes
    siblings, so it can only ever remove refutations, so no part grant can be
    lost to it — and measured, none is gained either, because every sibling it
    drops was already failing to refute for some other reason.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    counts = {
        rule: len([d for d in index.diagnostics if d.get("rule_id") == rule])
        for rule in (
            NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED,
        )
    }
    assert counts == {
        NO_COMMENCEMENT_EXECUTION_AUTHORIZED: 540,
        NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED: 123,
        NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED: 260,
        NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED: 33,
    }
    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
            NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT,
        }
    ]
    # The inert part-grant population is untouched too (W-39 2, W-47 27, W-49 2).
    inert = [
        (entry.source_id, law_id)
        for entry in index.entries
        for law_id, _date in entry.part_scoped_effective_dates
        if law_id not in entry.base_ids
    ]
    assert len(inert) == 31


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w51_corpus_the_carve_out_fence_flips_exactly_one_instrument() -> None:
    """The fence's whole corpus effect, recorded — not tuned.

    Of the 608 instruments the shipped ``_WHOLE_ACT_RE`` accepted, the fence
    refuses exactly one: 608 - 1 = 607 whole-act scopes, and the one missing is
    named. The two other carve-out texts the W-50 sizing found
    (``2010-06-04-771``, ``2011-12-09-1221``) never reach the fence: each
    carries two ``dateInForce`` dates, so ``SINGLE_EFFECTIVE_DATE`` had already
    left them inert — asserted here so a later widening of the date reader
    cannot quietly promote a carve-out.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    assert index.commencement_instrument_coverage.to_dict()["candidates"] == 607
    whole_act_scoped = {
        candidate.source_id
        for candidate in index.commencement_instruments
        if candidate.scope_status is NOCommencementScopeStatus.WHOLE_ACT
    }
    assert len(whole_act_scoped) == 607
    assert "no/forskrift/2020-05-07-944" not in whole_act_scoped
    instruments = {c.source_id: c for c in index.commencement_instruments}
    for inert_carve_out in ("no/forskrift/2010-06-04-771", "no/forskrift/2011-12-09-1221"):
        candidate = instruments[inert_carve_out]
        assert candidate.scope_status is NOCommencementScopeStatus.UNRESOLVED
        assert len(candidate.effective_dates) == 2
