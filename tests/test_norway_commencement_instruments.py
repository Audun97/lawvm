from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

import pytest

from lawvm.norway.commencement_instruments import (
    NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
    NO_COMMENCEMENT_EXECUTION_REFUSED,
    NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID,
    NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT,
    NOCommencementActPartEvidence,
    NOCommencementMultiPartAuthorizationConjunct,
    NOCommencementPartAuthorizationConjunct,
    NOCommencementAuthorizationConjunct,
    NOCommencementInstrumentCandidate,
    NOCommencementInstrumentCoverage,
    NOCommencementInstrumentCoverageError,
    NOCommencementParseStatus,
    NOCommencementScopeStatus,
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


def _partial_instrument_xml() -> bytes:
    return b"""<html><body>
<dd class="title">Delt ikraftsetting av lov 2. februar 2025 nr. 5</dd>
<dd class="basedOn"><a href="lov/2025-02-02-5">endringsloven</a></dd>
<dd class="dateInForce">2025-04-01 og 2025-06-01</dd>
<main class="documentBody">Loven \xc2\xa7 2 trer i kraft 1. april 2025. Resten trer i kraft 1. juni 2025.</main>
</body></html>"""


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
            ("lti/2025/sf-20250301-0101.xml", _partial_instrument_xml()),
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
) -> NOCommencementInstrumentCandidate:
    return NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=f"no://forskrift/{source_id.rsplit('/', 1)[1]}/original.lti.xml",
        archive="norway.farchive",
        member_name="",
        title="Delvis ikraftsetting av lov 2. februar 2025 nr. 5",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=effective_dates,
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
        source_excerpt="",
        changed_law_ids=changed_law_ids,
        commenced_section_labels=commenced_section_labels,
        whole_act_operative_text=whole_act_operative_text,
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
    assert len(inert) == 29
    assert sum(1 for d in single if d["law_id"] not in entries[d["source_id"]].base_ids) == 2
    assert sum(1 for d in multi if d["law_id"] not in entries[d["source_id"]].base_ids) == 27
