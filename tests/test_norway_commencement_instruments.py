from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from lawvm.norway.commencement_instruments import (
    NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID,
    NOCommencementInstrumentCoverage,
    NOCommencementInstrumentCoverageError,
    NOCommencementParseStatus,
    NOCommencementScopeStatus,
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


def test_backfill_prefers_exact_lovtidend_instrument_without_authorizing_it() -> None:
    lane = _recommend_no_backfill_lane(
        {
            "local_corpus": 1,
            "lovtidend_commencement_instrument": 1,
            "statsrad": 1,
        }
    )

    assert lane == "lovtidend_commencement_instrument"


def test_ingest_index_and_candidate_report_keep_lovtidend_lane_non_authorizing(tmp_path) -> None:
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
    assert index.entries[0].effective_status == "contingent"
    assert index.entries[0].effective_date is None
    assert report["lovtidend_commencement_instrument_count"] == 2
    assert all(item["replay_authorized"] is False for item in report["lovtidend_commencement_instruments"])
    assert report["candidate_source_counts"]["lovtidend_commencement_instrument"] == 2

    replay = replay_no_to_pit(
        "no/lov/2025-01-01-1",
        as_of="2025-12-31",
        data_dir=db_path,
        index=index,
    )
    assert replay.amendments_applied == []
    assert replay.amendments_skipped_contingent == ["no/lovtid/2025-02-02-5"]
    assert replay.n_ops == 0


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
