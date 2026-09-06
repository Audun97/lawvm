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
    NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_DATE_CONFLICT,
    NOCommencementActPartEvidence,
    NOCommencementWidenedWholeActAuthorizationConjunct,
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

# W-73. The title-cited subject reader's corpus population, over CANDIDATES
# rather than grants. 30 of the 2,365 parsed instruments name their act by title
# in a single operative block that agrees with their own declared title; 8 of
# those are blocked only on scope and so gain ``widened_whole_act_scope``, and 5
# of THOSE cite an offered amendment act and become grants. The three counts are
# pinned separately because they answer different questions — how many
# instruments the reader reads, how many that changes the scope proof for, and
# how many acts actually move.
# 30 -> 204 at W-100: the title-cited subject now also reads the act cited by
# date and number before its title (``Lov 11. januar 2013 nr. 3 om … trer i
# kraft …``), which most principal-act commencement instruments use; 174 more
# candidates carry the proof, 29 of them dating an offered act (the rest are
# already dated by the shipped route or cite an act no caller offers).
_W73_TITLE_CITED_CANDIDATE_COUNT = 204


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
def test_w47_corpus_witness_is_absorbed_by_the_widened_route_at_the_same_date() -> None:
    """W-47's corpus witness, and what W-53's absorption does and does not change.

    ``no/forskrift/2023-09-15-1422`` commences ``no/lovtid/2021-04-23-25``
    ("Loven trer i kraft straks") whose Endrer header spans del I and del II.
    Until W-53 that was two PART grants and the act stayed contingent. The
    widened whole-act route reads the same sentence as an act-level claim, and
    the act-level claim SUBSUMES the two part claims: same instrument, same
    date, same two laws dated — so the two laws
    (``2013-04-12-13``, ``2004-12-17-101``) keep the certification W-47 bought
    them, and what changes is that the act now says so at act level.

    This is the deliberate part-grant retirement, asserted on the witness the
    retired route was pinned by: the part receipts are GONE, and the property
    they were there to guarantee is asserted here in its stronger form.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2021-04-23-25")

    assert entry.effective_status == "instrument_authorized"
    assert entry.effective_date == "2023-09-15"
    # The part-scoped map is emptied, not contradicted: the act-level date now
    # answers for every binding, which is what ``effective_date_for_base`` reads
    # when the map is empty.
    assert entry.part_scoped_effective_dates == ()
    for law_id in ("no/lov/2004-12-17-101", "no/lov/2013-04-12-13"):
        assert law_id in entry.base_ids
        assert entry.effective_date_for_base(law_id)[0] == "2023-09-15"

    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2021-04-23-25"
    ]
    widened = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2021-04-23-25"
    ]
    assert len(widened) == 1
    assert widened[0]["instrument_source_ids"] == ["no/forskrift/2023-09-15-1422"]
    assert widened[0]["effective_date"] == "2023-09-15"


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
    # W-53: the widened route reads the same instrument's text as an ACT-level
    # claim and is refused by the same fact, through the same helper over the
    # same sharpened sibling set. Widening the reader must not widen the
    # soundness hole, and this is where that is asserted: the act stays
    # contingent with no date and no grant of either kind.
    assert entry.effective_status == "contingent"
    assert entry.effective_date is None
    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
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

    W-53 RETIRES most of both, deliberately and by design: the widened whole-act
    route grants at ACT level, so an act it dates carries the date its part
    grants would have given each binding and the part proposals are dropped
    without a receipt — exactly as they always were for an act the shipped
    whole-act route dated. 260 -> 4 over 2 acts, and 123 -> 33 over 31 acts.
    346 of the 416 part grants are absorbed; measured per grant, 344 are
    DATE-IDENTICAL and 2 are LATER (conservative), and 0 are earlier — which is
    the property that makes the retirement safe rather than merely intended
    (``.tmp/w53/absorption.json``). The disjointness this test was written for
    still holds among the survivors, and now holds against the act-level routes
    too.
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
    assert len(multi) == 4
    assert len({d["source_id"] for d in multi}) == 2
    assert len(single) == 33
    assert len({d["source_id"] for d in single}) == 31
    # No surviving part grant sits on an act either act-level route dated: the
    # yield is per act, so the two populations are disjoint by construction.
    act_level = {
        d["source_id"]
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
        }
    }
    assert not (act_level & {d["source_id"] for d in multi + single})
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
    # 31 -> 4 at W-53, and the follow-up question this pin recorded is mostly
    # answered by the absorption rather than by a cleanup: 27 of the 31 sat on
    # acts the widened route now dates at act level, so their receipts are gone
    # with the rest of their route's. The 4 that remain (1 single, 1 multi, 2
    # named) are still unreachable for the reason above.
    assert len(inert) == 4
    assert sum(1 for d in single if d["law_id"] not in entries[d["source_id"]].base_ids) == 1
    assert sum(1 for d in multi if d["law_id"] not in entries[d["source_id"]].base_ids) == 1


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

    W-53 absorbs the two older routes into the widened act-level one (123 -> 33,
    260 -> 4) and takes NOTHING from this one: all 33 grants over all 10 acts
    survive, byte for byte. That is not a coincidence and is worth stating,
    because it is the sharpest evidence the two claim shapes really are
    different. This route only ever fires on an act whose parts commence in
    STAGES — its ``LATER_INSTRUMENTS_NAME_OTHER_PARTS`` conjunct requires a later
    sibling to exist and to be provably about other parts — and a later sibling
    on the act is exactly what the widened route's act-global
    ``ACT_HAS_NO_LATER_INSTRUMENT`` refuses. The two routes are mutually
    exclusive on the corpus for a structural reason, not a numerical one.
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
    assert len(multi) == 4
    assert len(single) == 33
    # Every act this route serves has a later sibling, which is what makes it
    # unreachable by the widened act-level route — the structural argument in
    # the docstring, asserted rather than asserted-about.
    widened_acts = {
        d["source_id"]
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
    }
    assert not (widened_acts & {d["source_id"] for d in named})
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

    # W-53: and neither returns by the widened route, which is the check a
    # widening owes a soundness repair. Both are still contingent with no date
    # and no grant of ANY of the five kinds; the mechanisms that demoted them
    # are the same two the widened route inherits (the carve-out fence on the
    # scope proof, the act-level refutation on the gate).
    granted_acts = {
        d["source_id"]
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED,
        }
    }
    for act_id in ("no/lovtid/2020-05-07-40", "no/lovtid/2020-06-19-77"):
        assert entries[act_id].effective_status == "contingent"
        assert entries[act_id].effective_date is None
        assert entries[act_id].part_scoped_effective_dates == ()
        assert act_id not in granted_acts

    # The fenced one is no longer a whole-act candidate at all, and W-47's
    # reader had always refused its text for the same reason (the exception
    # phrase is in ``_SUBDIVISION_SCOPE_RE`` too) — which is exactly the
    # inconsistency W-51 removes: two readers of the same sentence disagreeing.
    fenced = instruments["no/forskrift/2020-05-07-944"]
    assert fenced.scope_status is NOCommencementScopeStatus.UNRESOLVED
    assert fenced.whole_act_operative_text is False
    # W-53: and therefore no widened scope either — the widened proof is the
    # conjunction of that flag with a single block and the fence, so the reader
    # refusing is already enough. This is the assertion that stops a future
    # loosening of ``_whole_act_operative_text`` from silently re-authorizing the
    # act W-51 demoted.
    assert fenced.widened_whole_act_scope is False
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
    # 540 -> 541 at W-61: the ONE act gaining its first index entry when the
    # unstructured repeal-then-shift lead widens (`no/lovtid/2014-06-20-26`).
    # Nothing about the gate moved — the OFFERING grew by one act — and the
    # assertion that carries the information is the P1 one below, which still
    # reads EMPTY over the larger grant set.
    # 541 -> 542 at W-77, the same mechanism again: ``no/lovtid/2008-06-27-50``
    # gains its first index entry off the item-depth newness payload production
    # ("§ 10-8 tredje ledd ny bokstav h skal lyde:", amending folketrygdloven)
    # and is dated 2008-07-01 by its own ``no/forskrift/2008-06-27-722``. Nothing
    # is withdrawn, no act is re-dated, and the P1 assertion below still reads
    # EMPTY.
    # 542 -> 541 at W-79, the same mechanism running BACKWARDS for the first
    # time: ``no/lovtid/2025-03-28-4``'s only op was the own-text fallback
    # writing its own lead ("I lov 4. juni 1993 nr. 58 om allmenngjøring av
    # tariffavtaler m.v. skal § 2 nr. 4 lyde:") over allmenngjøringsloven § 2 —
    # the node declares a payload but keeps it in a ``numberedLegalP`` the
    # fallback cannot read. W-79 refuses it typed, the instrument drops to zero
    # ops, and with no index entry it no longer reaches this lane. The OFFERING
    # shrank by one instrument; the gate did not move, and the P1 assertion
    # below still reads EMPTY over the smaller grant set.
    # 541 -> 545 at W-98 and 545 -> 546 at W-99 — recorded together because this
    # shard was not run at W-98 and the pin sat stale for it: W-98's pre-2001
    # lead grammar gave four acts their first index entry, each dated by its own
    # kongelig resolusjon through this route (``no/lovtid/2010-06-25-50``,
    # ``2016-01-22-1``, ``2016-12-16-99``, ``2022-12-16-93``; the index shard's
    # own notes carry the same four), and W-99's address-after-citation lead
    # gives ``no/lovtid/2017-06-16-51`` its first entry, dated 2018-01-01 by its
    # own ``no/forskrift/2017-06-16-751``. Every one is ``plain``.
    assert len(grants) == 546
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

    W-53 keeps the 540 exactly (the widened route is entered only by pairs the
    shipped one refused) and retires the part routes into its own 430 act-level
    grants; the five-route census below is the whole lane in one assertion.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    counts = {
        rule: len([d for d in index.diagnostics if d.get("rule_id") == rule])
        for rule in (
            NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED,
        )
    }
    # 540 -> 541 at W-61 (one act gains its first index entry); the other four
    # routes are unmoved, which is the check that a LOWERING widening reaches the
    # commencement lane only by growing what is offered to it.
    # 435 -> 436 at W-67, the same mechanism with the same check passing:
    # ``no/lovtid/2004-09-24-72`` gains its first index entry off the two-token
    # section-renumber widening and enters the WIDENED whole-act route, so this
    # time 541 is the count that holds and the other three part routes are again
    # untouched.
    # 436 -> 437 at W-66, the same mechanism a THIRD time:
    # ``no/lovtid/2001-06-15-33`` gains its first index entry off the sibling-set
    # ledd relabel ("Nåværende annet ledd blir nytt tredje ledd.", inheriting § 73 E
    # from the preceding lead) and enters the WIDENED whole-act route. 541 holds and
    # all four other routes are unmoved. A LOWERING widening reaches this lane only
    # by growing what is offered to it, and this assertion is what proves it each
    # time.
    # 437 -> 438 at W-66b, a FOURTH time and by the same mechanism:
    # ``no/lovtid/2005-06-17-92`` gains its first index entry off the sibling-set
    # relabel one depth word down ("Nåværende annet og tredje punktum blir nye
    # fjerde og femte punktum.", § 54 første ledd of ``no/lov/1902-05-22-10``,
    # section AND ledd both inherited from the preceding lead) and enters the
    # WIDENED whole-act route at 2006-01-01 via ``no/forskrift/2005-12-16-1517``.
    # 541 holds and all four other routes are unmoved.
    # 541 -> 542 at W-77, a FIFTH time and by the same mechanism, but on the
    # SHIPPED whole-act route rather than the widened one: ``no/lovtid/2008-06-27-50``
    # gains its first index entry off the item-depth newness payload production
    # ("§ 10-8 tredje ledd ny bokstav h skal lyde:") and is dated 2008-07-01 by its
    # own ``no/forskrift/2008-06-27-722``. 438/33/4/33 all hold, which is again the
    # check that a LOWERING widening reaches this lane only by growing what is
    # offered to it.
    # 542 -> 541 at W-79, the mechanism running backwards: ``no/lovtid/2025-03-28-4``
    # loses its only op to the structured payload lane's own-text invariant and
    # with it its index entry. 438/33/4/33 all hold — the shrinkage reaches this
    # lane only by shrinking what is offered to it, exactly as the growths did.
    # 541 -> 545 at W-98 and 545 -> 546 at W-99 — recorded together because this
    # shard was not run at W-98 and the pin sat stale for it: W-98's pre-2001
    # lead grammar gave four acts their first index entry, each dated by its own
    # kongelig resolusjon through this route (``no/lovtid/2010-06-25-50``,
    # ``2016-01-22-1``, ``2016-12-16-99``, ``2022-12-16-93``; the index shard's
    # own notes carry the same four), and W-99's address-after-citation lead
    # gives ``no/lovtid/2017-06-16-51`` its first entry, dated 2018-01-01 by its
    # own ``no/forskrift/2017-06-16-751``. Every one is ``plain``.
    # 438 -> 440 at W-98, recorded at W-99 for the same reason as the whole-act
    # pin above: two of W-98's entrants (``no/lovtid/2002-08-30-68``,
    # ``2016-09-16-81``) are dated through the widened route. W-99 itself
    # moves nothing here.
    # 440 -> 469 at W-100 on the WIDENED route (the title-cited citation form);
    # the shipped route and the three part routes are unmoved, and the two
    # section-scoped receipts this item adds are censused in the W-100 block.
    assert counts == {
        NO_COMMENCEMENT_EXECUTION_AUTHORIZED: 546,
        NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED: 469,
        NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED: 33,
        NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED: 4,
        NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED: 33,
    }
    assert not [
        d
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
            NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_DATE_CONFLICT,
            NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT,
        }
    ]
    # W-53: no act carries both a grant and a refusal for the SAME instrument.
    # The whole-act route writes its refusal before any route resolves, so the
    # widened route withdraws it where it grants — otherwise 274 receipts whose
    # own reason is "stays evidence and re-dates nothing" would sit on acts that
    # had just been re-dated. (1,156 -> 882 refusals; the difference is smaller
    # than the 430 grants because 156 of those pairs had been consumed by a part
    # route at base and never carried a refusal in the first place.)
    # 882 -> 877 at W-73, exactly conserving against its five new grants: each of
    # the five title-cited pairs had carried a whole-act refusal at base and the
    # widened route withdraws it where it grants, so the refusal set falls by
    # exactly the number of grants added and no pair is ever both.
    # 877 -> 879 at W-66, and it GROWS for the honest reason: no refusal is
    # created for an act that already had one, and none is withdrawn. The two new
    # pairs are ``no/lovtid/2005-06-17-98`` x
    # {``no/forskrift/2005-06-17-631``, ``no/forskrift/2008-05-30-524``} — an act
    # that had no index entry at all until the sibling-set ledd relabel gave it its
    # first lowered op, so its commencement instruments had nothing to be refused
    # AGAINST. The disjointness assertion above is what carries the real property,
    # and it still holds.
    granted_pairs = {
        (d["source_id"], instrument_id)
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
        }
        for instrument_id in d["instrument_source_ids"]
    }
    refused_pairs = {
        (d["source_id"], d["instrument_source_id"])
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_EXECUTION_REFUSED
    }
    assert not (granted_pairs & refused_pairs)
    # 879 -> 880 at W-77, the SAME mechanism a third time: ``no/lovtid/2012-12-07-75``
    # had no index entry at all until the item-depth newness payload production gave
    # it its first lowered op ("§ 3-15 annet ledd ny bokstav f skal lyde:"), so its
    # commencement instrument ``no/forskrift/2014-09-26-1221`` had nothing to be
    # refused AGAINST. One pair gained, none withdrawn, and the disjointness
    # assertion above — the one that carries the real property — still holds.
    # 880 -> 879 at W-85, the mechanism in reverse: ``no/lovtid/2012-12-07-71``
    # lost its index entry when the re-sanctioning gate withdrew the defective
    # act wholesale, so ``no/forskrift/2012-12-07-1149`` — the resolution that
    # would have commenced it — again has nothing to be refused against (its
    # ``scope_unresolved`` receipt remains). One pair withdrawn, none gained.
    # 879 -> 882 at W-99, the SAME mechanism forward: three acts had no index
    # entry at all until the address-after-citation lead gave each its first
    # lowered op (``no/lovtid/2002-05-03-13``, ``2004-03-26-17``,
    # ``2005-12-21-123`` — all contingent), so their own resolutions
    # (``no/forskrift/2002-05-03-420``, ``2004-03-26-575``, ``2005-12-21-1610``)
    # now have something to be refused AGAINST. Three pairs gained, none
    # withdrawn; the disjointness assertion above still holds.
    # 882 -> 728 at W-100, the mechanism BACKWARDS by design: the section-scoped
    # route and the title-cited citation form withdraw the generic refusal for
    # every pair they GRANT (154 of them), exactly as W-53 withdrew it for the
    # widened route's; a pair the reader read but the gate refused keeps the
    # generic receipt and gains a reasoned one beside it.
    # 728 -> 710 at W-102, the same withdrawal one step further down: a pair
    # whose every dated label was ledd-qualified is now GRANTED by path where
    # the act's ops admit it (28 all-qualified keys -> 8; 3 one-instrument
    # staged keys land), and each granted pair sheds its generic refusal.
    assert len(refused_pairs) == 710

    # The inert part-grant population, 31 -> 4 at W-53 with the absorption.
    inert = [
        (entry.source_id, law_id)
        for entry in index.entries
        for law_id, _date in entry.part_scoped_effective_dates
        if law_id not in entry.base_ids
    ]
    assert len(inert) == 4


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


# --------------------------------------------------------------------------
# W-53: the widened whole-act route, the gate's fifth and its second act-level
# one.
#
# ``_WHOLE_ACT_RE`` is a SHAPE — a single block BEGINNING ``(denne )?loven trer i
# kraft`` — and the W-50 census measured what that misses at 518 mechanical
# misses over 449 offered acts. The three miss classes the ledger had guessed did
# not survive measurement (0 title-prefix hits); what actually breaks is the
# SUBJECT (317 cited-act subjects like "Lov 17. juni 2005 nr. 62 om … trer i
# kraft", 181 adjacent subjects whose verb is outside the anchored set) and the
# verb vocabulary (``gjelder fra``, ``skal gjelde``, the nynorsk forms).
#
# The widened route reads those with W-47's reader rather than a new pattern, and
# bounds it three ways: one operative block, W-51's carve-out fence over that
# block, and W-51's act-level refutation over W-51's sharpened sibling set. Sized
# at W-50 (research only), unblocked by W-51 (the shipped route was itself in
# act-level breach) and W-52 (its first entrant exposed a replay-receipt defect),
# landed here.
# --------------------------------------------------------------------------


def _widened_instrument(
    source_id: str,
    *,
    affected_law_ids: tuple[str, ...] = ("no/lov/2025-02-02-5",),
    effective_dates: tuple[str, ...] = ("2025-04-01",),
    whole_act_operative_text: bool = True,
    widened_whole_act_scope: bool = True,
    changed_law_ids: tuple[str, ...] = (),
    cites_acts_as_hjemmel_only: bool = False,
) -> NOCommencementInstrumentCandidate:
    """A candidate the SHIPPED whole-act route refuses and the widened one reads.

    ``scope_status`` is always UNRESOLVED — that is what makes the pair this
    route's business rather than the shipped route's — and callers always pass
    ``BLOCKED_UNRESOLVED`` beside it, for the same reason.
    """
    return NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=f"no://forskrift/{source_id.removeprefix('no/forskrift/')}/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="",
        title="Ikraftsetting av lov 2. februar 2025 nr. 5",
        affected_law_ids=affected_law_ids,
        effective_dates=effective_dates,
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
        source_excerpt="Lov 2. februar 2025 nr. 5 om … gjelder fra 1. april 2025.",
        changed_law_ids=changed_law_ids,
        whole_act_operative_text=whole_act_operative_text,
        cites_acts_as_hjemmel_only=cites_acts_as_hjemmel_only,
        widened_whole_act_scope=widened_whole_act_scope,
    )


def test_widened_route_dates_an_act_the_shipped_shape_refuses() -> None:
    """The route's positive case, and its receipt."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _widened_instrument("no/forskrift/2025-03-01-500"),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert authorization.widened_whole_act_conflicts == ()
    # And no refusal: the whole-act route's receipt for this pair is WITHDRAWN
    # once the widened route grants it, because that receipt's own reason says
    # the instrument "re-dates nothing".
    assert authorization.refusals == ()
    assert len(authorization.widened_whole_act_authorizations) == 1
    receipt = authorization.widened_whole_act_authorizations[0]
    assert receipt.act_source_id == "no/lovtid/2025-02-02-5"
    assert receipt.instrument_source_ids == ("no/forskrift/2025-03-01-500",)
    assert receipt.effective_date == "2025-04-01"
    assert receipt.passed_conjuncts == tuple(
        NOCommencementWidenedWholeActAuthorizationConjunct
    )
    # It lands in the ACT-level date map, beside the shipped route's grants.
    assert authorization.authorized_effective_dates() == {
        "no/lovtid/2025-02-02-5": "2025-04-01"
    }
    assert [item.replay_authorized for item in authorization.instruments] == [True]

    detail = receipt.to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
    assert detail["source_id"] == "no/lovtid/2025-02-02-5"
    assert detail["effective_date"] == "2025-04-01"
    assert detail["blocking"] is False
    assert detail["passed_conjuncts"] == [
        "single_effective_date",
        "blocked_only_on_scope",
        "single_operative_block",
        "whole_act_operative_text",
        "act_has_no_later_instrument",
    ]
    # F-10, at the receipt: a DATE and no base_ids, so like the three part
    # routes this one cannot bind an unresolved amender and carries no
    # decertification risk.
    assert "base_ids" not in detail


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"widened_whole_act_scope": False}, "several operative blocks, or the fence"),
        (
            {"whole_act_operative_text": False, "widened_whole_act_scope": False},
            "the reader refuses the text",
        ),
        (
            {"effective_dates": ("2025-04-01", "2025-07-01")},
            "two dateInForce dates: the instrument stages itself",
        ),
    ],
)
def test_widened_route_refuses_without_every_conjunct(kwargs, why: str) -> None:
    """All-or-nothing: each conjunct alone is enough to refuse."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _widened_instrument("no/forskrift/2025-03-01-501", **kwargs),
        )],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )
    assert authorization.widened_whole_act_authorizations == (), why
    assert authorization.authorized_effective_dates() == {}


def test_widened_route_never_sees_a_pair_the_shipped_route_accepted() -> None:
    """``BLOCKED_ONLY_ON_SCOPE`` is what keeps the two act-level routes disjoint.

    Not a hypothetical guard: measured over the corpus, ALL 607 shipped whole-act
    candidates also satisfy the widened scope proof, because a text matching
    ``_WHOLE_ACT_RE`` is exactly the kind W-47's reader accepts. Without this
    conjunct the shipped 540 would drain into the new rule id wholesale.
    """
    shipped = dataclass_replace(
        _instrument_candidate(
            "no/forskrift/2025-03-01-502",
            affected_law_ids=("no/lov/2025-02-02-5",),
            effective_dates=("2025-04-01",),
        ),
        whole_act_operative_text=True,
        widened_whole_act_scope=True,
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.CANDIDATE, shipped)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert len(authorization.authorizations) == 1
    assert authorization.widened_whole_act_authorizations == ()


def test_widened_route_refuses_a_later_instrument_for_the_act() -> None:
    """``ACT_HAS_NO_LATER_INSTRUMENT``, the same conjunct through the same helper.

    The claim is act-global, so a later instrument commencing anything of the act
    refutes it whatever that instrument's own scope — W-49's per-part
    disjointness reading does not apply, for the reason W-51 gave: a whole-act
    claim leaves no part of the act unclaimed.
    """
    widened = _widened_instrument("no/forskrift/2025-03-01-503")
    later = _widened_instrument(
        "no/forskrift/2026-01-05-504",
        effective_dates=("2026-01-05",),
        whole_act_operative_text=False,
        widened_whole_act_scope=False,
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, widened),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, later),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.widened_whole_act_authorizations == ()
    assert authorization.authorized_effective_dates() == {}
    assert [item.replay_authorized for item in authorization.instruments] == [False, False]


def test_widened_route_admits_an_earlier_sibling() -> None:
    """An earlier instrument says nothing against "the rest commenced later"."""
    earlier = _widened_instrument(
        "no/forskrift/2024-01-01-505",
        effective_dates=("2024-01-01",),
        whole_act_operative_text=False,
        widened_whole_act_scope=False,
    )
    widened = _widened_instrument("no/forskrift/2025-03-01-506")

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, earlier),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, widened),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert len(authorization.widened_whole_act_authorizations) == 1
    assert authorization.widened_whole_act_authorizations[0].effective_date == "2025-04-01"


def test_widened_route_admits_a_later_hjemmel_only_sibling() -> None:
    """The route consumes W-51's SHARPENED sibling set, not a re-derivation.

    A later instrument citing the act only as its hjemmel — its own commencement
    action is about a forskrift — is not in the sibling list at all and cannot
    refute. Worth its own pin: measured, this is the whole difference between the
    route's 430 grants and the 428 W-50 sized before the sharpening existed
    (``no/lovtid/2003-12-12-113`` and ``no/lovtid/2011-06-24-39``).
    """
    hjemmel_only = _widened_instrument(
        "no/forskrift/2026-01-05-507",
        effective_dates=("2026-01-05",),
        whole_act_operative_text=False,
        widened_whole_act_scope=False,
        cites_acts_as_hjemmel_only=True,
    )
    widened = _widened_instrument("no/forskrift/2025-03-01-508")

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, hjemmel_only),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, widened),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert len(authorization.widened_whole_act_authorizations) == 1


def test_widened_date_conflict_blocks_instead_of_taking_the_later_date() -> None:
    """W-51's ordering lesson, inherited: the conflict branch gets FIRST refusal.

    Two instruments each reading the act as commencing whole, on different dates.
    The refutation alone would resolve that silently in favour of the later one —
    the earlier claim has a later sibling, the later claim has none — and the
    contradiction would never be receipted. Asserting the refutation AFTER the
    conflict branch keeps the louder, blocking verdict.
    """
    earlier = _widened_instrument(
        "no/forskrift/2025-03-01-509", effective_dates=("2025-04-01",)
    )
    later = _widened_instrument(
        "no/forskrift/2025-06-01-510", effective_dates=("2025-09-01",)
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, earlier),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, later),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.widened_whole_act_authorizations == ()
    assert authorization.authorized_effective_dates() == {}
    assert len(authorization.widened_whole_act_conflicts) == 1
    conflict = authorization.widened_whole_act_conflicts[0]
    assert conflict.act_source_id == "no/lovtid/2025-02-02-5"
    assert conflict.effective_dates == ("2025-04-01", "2025-09-01")
    assert conflict.instrument_source_ids == (
        "no/forskrift/2025-03-01-509",
        "no/forskrift/2025-06-01-510",
    )
    detail = conflict.to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_DATE_CONFLICT
    assert detail["blocking"] is True
    assert detail["strict_disposition"] == "block"


def test_widened_route_yields_to_a_shipped_proposal_it_disagrees_with() -> None:
    """The yield is on a shipped PROPOSAL, not merely on a shipped grant.

    A shape-proved instrument dates the act 2025-04-01 and a read one dates it
    2025-09-01. The shipped route refuses (its own refutation sees the later
    sibling) and writes its receipt. Without this yield the widened route would
    then grant 2025-09-01 — it has no later sibling of its own — and a
    disagreement between two act-level claims would be resolved silently toward
    the later date ACROSS routes, which is the same mistake the conflict branch
    above prevents within one.
    """
    shipped = _instrument_candidate(
        "no/forskrift/2025-03-01-511",
        affected_law_ids=("no/lov/2025-02-02-5",),
        effective_dates=("2025-04-01",),
    )
    widened = _widened_instrument(
        "no/forskrift/2025-06-01-512", effective_dates=("2025-09-01",)
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.CANDIDATE, shipped),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, widened),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
    )

    assert authorization.authorizations == ()
    assert authorization.widened_whole_act_authorizations == ()
    assert authorization.authorized_effective_dates() == {}
    # Both instruments keep the whole-act route's refusal, and correctly: the
    # act is re-dated by nothing, so neither receipt's "stays evidence and
    # re-dates nothing" is false. The widened route adds no receipt of its own,
    # because the older act-level route already adjudicated this same claim.
    assert {
        r.instrument_source_id: r.failed_conjuncts for r in authorization.refusals
    } == {
        "no/forskrift/2025-03-01-511": (
            NOCommencementAuthorizationConjunct.ACT_HAS_NO_LATER_INSTRUMENT,
        ),
        "no/forskrift/2025-06-01-512": (
            NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
            NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
        ),
    }


def test_part_routes_yield_to_a_widened_act_level_grant() -> None:
    """The absorption at unit scale: one instrument, one act, one date.

    The same instrument would give the single-part route a grant for del I. The
    widened route dates the WHOLE act at the same date, so the part proposal is
    dropped without a receipt — exactly as it always was for an act the shipped
    whole-act route dated, and the reason 346 of the corpus's 416 part grants
    retire.
    """
    instrument = _widened_instrument(
        "no/forskrift/2025-03-01-513", changed_law_ids=("no/lov/2001-01-05-1",)
    )

    authorization = authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.BLOCKED_UNRESOLVED, instrument)],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"I": "no/lov/2001-01-05-1", "III": "no/lov/1997-06-13-55"},
                bound_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
            )
        },
    )

    assert len(authorization.widened_whole_act_authorizations) == 1
    assert authorization.part_authorizations == ()
    assert authorization.part_authorized_effective_dates() == {}
    assert authorization.authorized_effective_dates() == {
        "no/lovtid/2025-02-02-5": "2025-04-01"
    }


def test_a_refuted_widened_claim_leaves_the_part_grant_standing() -> None:
    """The widened proposal consumes nothing, which is what makes the yield safe.

    Same instrument, plus a later sibling that refutes the ACT-level claim. The
    act-level claim falls; the part claim — about del I only, proved structurally
    — does not, and must not: the widened route asked for more and got nothing,
    rather than taking the part grant down with it.
    """
    instrument = _widened_instrument(
        "no/forskrift/2025-03-01-514", changed_law_ids=("no/lov/2001-01-05-1",)
    )
    later = _widened_instrument(
        "no/forskrift/2026-01-05-515",
        effective_dates=("2026-01-05",),
        whole_act_operative_text=False,
        widened_whole_act_scope=False,
    )

    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, instrument),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, later),
        ],
        offered_act_ids={"no/lovtid/2025-02-02-5"},
        act_part_evidence={
            "no/lovtid/2025-02-02-5": _part_evidence(
                part_law_ids={"I": "no/lov/2001-01-05-1", "III": "no/lov/1997-06-13-55"},
                bound_law_ids=("no/lov/1997-06-13-55", "no/lov/2001-01-05-1"),
            )
        },
    )

    assert authorization.widened_whole_act_authorizations == ()
    assert len(authorization.part_authorizations) == 1
    assert authorization.part_authorizations[0].part_label == "I"


def test_widened_route_is_off_for_an_act_no_caller_offers() -> None:
    """No offered act, no pair, no receipt — the enabling-statute filter."""
    authorization = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _widened_instrument("no/forskrift/2025-03-01-516"),
        )],
        offered_act_ids=set(),
    )
    assert authorization.widened_whole_act_authorizations == ()
    assert authorization.refusals == ()


# --- W-53's parse-time scope proof -----------------------------------------


def _widened_scope_of(blocks: list[str], *, date_in_force: str = "2025-04-01") -> bool:
    body = "".join(f'<article class="legalP">{text}</article>' for text in blocks)
    payload = (
        '<html><body><dd class="title">Ikraftsetting av lov 2. februar 2025 nr. 5</dd>'
        '<dd class="basedOn"><ul><li>lov/2025-02-02-5</li></ul></dd>'
        f'<dd class="dateInForce">{date_in_force}</dd>'
        f'<main class="documentBody">{body}</main>'
        "</body></html>"
    ).encode("utf-8")
    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2025-03-01-517",
        locator="no://forskrift/2025-03-01-517/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0517.xml",
    )
    assert result.candidate is not None
    return result.candidate.widened_whole_act_scope


@pytest.mark.parametrize(
    "text",
    [
        # The W-50 census's two measured miss classes: a cited-act subject, and
        # an adjacent subject whose verb is outside the anchored set.
        "Lov 17. juni 2005 nr. 62 om endringer i arbeidsmiljøloven trer i kraft 1. januar 2006.",
        "Loven gjelder fra 1. april 2025.",
        "Lova skal gjelde frå 1. april 2025.",
    ],
)
def test_widened_scope_accepts_the_shapes_the_shipped_pattern_misses(text: str) -> None:
    """The route's whole reason to exist, in the shapes W-50 measured.

    The second assertion is the one that makes these this route's population
    rather than a duplicate of the old one: ``_WHOLE_ACT_RE`` really does refuse
    every one of them.
    """
    assert _widened_scope_of([text]) is True
    # lawvm-regex: owning_parser the shipped whole-act shape, asserted negatively
    assert _WHOLE_ACT_RE.fullmatch(text) is None


def test_widened_scope_refuses_a_second_operative_block() -> None:
    """``SINGLE_OPERATIVE_BLOCK``: the reader joins blocks, so one block only.

    Block one commences the act; block two says something else. The block COUNT
    has to carry this, because a second block need not mention a subdivision at
    all in order to say something the first does not — which is exactly how the
    ``reader`` variant W-50 priced ended up admitting delegation and
    forskrift-amendment texts.
    """
    assert _widened_scope_of(["Loven gjelder fra 1. april 2025."]) is True
    assert (
        _widened_scope_of(
            [
                "Loven gjelder fra 1. april 2025.",
                "Departementet kan gi overgangsregler.",
            ]
        )
        is False
    )


@pytest.mark.parametrize(
    "tail",
    [
        ", med unntak av kapittel 6",
        ", med unntak for § 13a",
        ". Kapittel 7 settes foreløpig ikke i kraft",
    ],
)
def test_widened_scope_refuses_a_carve_out(tail: str) -> None:
    """W-51's fence over the widened proof, from the same computed value.

    The item asked specifically whether ``unntak for`` and ``foreløpig ikke``
    reach this route's reader. They are the only two phrases
    ``_WHOLE_ACT_TAIL_HAZARD_RE`` carries that ``_SUBDIVISION_SCOPE_RE`` does
    not, and measured over all 2,365 parsed instruments the fence's flip set on
    this route is EMPTY: each of the 13 corpus texts carrying either phrase is
    already refused by the reader on another token, because the grammatical
    object of ``unntak for`` is itself always a subdivision noun
    (``.tmp/w53/fence_witnesses.json``). The fence is kept and pinned anyway —
    it is refusing-only, it costs nothing, and it makes "the module's two
    whole-act readers agree on carve-outs" true by construction rather than by
    measurement.
    """
    assert _widened_scope_of([f"Loven gjelder fra 1. april 2025{tail}."]) is False


def test_widened_scope_round_trips_through_serialization() -> None:
    """The flag is persisted, so a reloaded index gates identically."""
    candidate = _widened_instrument("no/forskrift/2025-03-01-518")
    assert candidate.to_dict()["widened_whole_act_scope"] is True
    restored = NOCommencementInstrumentCandidate.from_dict(candidate.to_dict())
    assert restored.widened_whole_act_scope is True
    # Absent in a pre-W-53 serialized index: the safe default is False, so an
    # old artifact can never authorize through the new route.
    assert (
        NOCommencementInstrumentCandidate.from_dict(
            {"source_id": "no/forskrift/2025-03-01-519", "locator": "x"}
        ).widened_whole_act_scope
        is False
    )


# --- W-53 corpus ------------------------------------------------------------


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w53_corpus_witness_dates_the_act_that_needed_w52_first() -> None:
    """W-53's corpus witness, chosen because it is the one W-52 had to make safe.

    ``no/lovtid/2007-06-29-93`` is the contingent amending act that kept
    ``no/lov/2004-12-17-99`` (klimakvoteloven) out of the candidate set. Under the
    W-50 counterfactual its admission produced the programme's first and only
    ``error`` verdict — a renumber whose displaced occupant the receipt did not
    declare. W-52 fixed the receipt; here the widened route dates the act and the
    law enters the scan CONSISTENT at 0 divergences, so the error column never
    opens.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entry = next(e for e in index.entries if e.source_id == "no/lovtid/2007-06-29-93")

    assert entry.effective_status == "instrument_authorized"
    assert entry.effective_date == "2007-07-01"
    assert entry.part_scoped_effective_dates == ()
    assert "no/lov/2004-12-17-99" in entry.base_ids

    receipts = [
        d
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
        and d.get("source_id") == "no/lovtid/2007-06-29-93"
    ]
    assert len(receipts) == 1
    assert receipts[0]["instrument_source_ids"] == ["no/forskrift/2007-06-29-823"]
    assert receipts[0]["effective_date"] == "2007-07-01"

    instrument = next(
        c
        for c in index.commencement_instruments
        if c.source_id == "no/forskrift/2007-06-29-823"
    )
    # The proof in one place: the shipped SHAPE refuses it, the reader accepts
    # it, and the widened scope proof holds.
    assert instrument.scope_status is NOCommencementScopeStatus.UNRESOLVED
    assert instrument.whole_act_operative_text is True
    assert instrument.widened_whole_act_scope is True
    assert instrument.replay_authorized is True


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w53_corpus_zero_early_over_every_widened_grant() -> None:
    """P1 at act level over the widened set — the item's hard gate.

    The probe W-51 promoted from a measurement of the gate to a property of it,
    run over this route's 430 grants. Given the conjunct this is close to a
    tautology, which is the point of the conjunct; what carries information is
    the SCOPE — 0 EARLY over all 1,040 grants across all five routes, where the
    older probe covered 540.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
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
        if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
    ]
    # 435 -> 436 at W-67: one more act reaches the widened route
    # (``no/lovtid/2004-09-24-72``, see the census note on the totals test above).
    # 436 -> 437 at W-66 (``no/lovtid/2001-06-15-33``, same mechanism again).
    # 437 -> 438 at W-66b (``no/lovtid/2005-06-17-92`` @2006-01-01 via
    # ``no/forskrift/2005-12-16-1517``), and the mechanism is the same a THIRD
    # time: an instrument with no lowered op has no amendment for a commencement
    # route to authorize. That instrument's only lowerable instruction is
    # "Nåværende annet og tredje punktum blir nye fjerde og femte punktum."
    # against ``no/lov/1902-05-22-10`` § 54 første ledd, which this item lowers.
    # Gained by CONTENT, 0 lost.
    # The zero-early property below is what actually matters here, and it holds
    # over the grown set.
    # 438 -> 440 at W-98, recorded at W-99 for the same reason as the whole-act
    # pin above: two of W-98's entrants (``no/lovtid/2002-08-30-68``,
    # ``2016-09-16-81``) are dated through the widened route. W-99 itself
    # moves nothing here.
    # 440 -> 469 at W-100: the title-cited subject's citation form dates 29
    # principal acts (``no/lovtid/2013-01-11-3`` @2013-06-01 the witness); the
    # zero-early property below holds over the grown set, and the Bouvetøya
    # instrument (``no/forskrift/2005-02-25-173``) is refused by the form's
    # bare-date-tail conjunct rather than dating ``no/lovtid/2003-06-27-57``.
    assert len(grants) == 469
    early = [
        (d["source_id"], d["effective_date"], sibling_id, sibling_date)
        for d in grants
        for sibling_id, sibling_date in dates_by_act.get(d["source_id"], ())
        if sibling_id not in set(d["instrument_source_ids"])
        and sibling_date > d["effective_date"]
    ]
    assert early == []


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w53_corpus_the_absorbed_part_grants_are_never_dated_earlier() -> None:
    """The retirement's safety property, asserted where it can still be checked.

    346 of the base's 416 part grants are absorbed by an act-level grant, 70
    survive. For each absorbed one the act-level date must be the part date or
    LATER — an earlier date would apply that part's ops on a day the part route's
    own evidence says it was not yet in force, which is a soundness regression
    dressed as a coverage win. Measured across the change: 344 identical, 2
    later, 0 earlier (``.tmp/w53/absorption.json``).
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entries = {e.source_id: e for e in index.entries}
    act_dates = {
        d["source_id"]: d["effective_date"]
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
        }
    }
    surviving = [
        d
        for d in index.diagnostics
        if d.get("rule_id")
        in {
            NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
            NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED,
        }
    ]
    assert len(surviving) == 70
    # Absorption is total per act, never partial: no act carries both an
    # act-level date and a part-scoped one. That is what makes "the act-level
    # date answers for every binding" safe to rely on.
    for act_id, entry in entries.items():
        if act_id in act_dates:
            assert entry.part_scoped_effective_dates == (), act_id

    # The two LATER-conservative absorptions, by id and with both dates. Their
    # part receipts are gone, so the part dates are the measured base values and
    # what is asserted here is that the act now says something strictly later.
    for act_id, part_date, act_date in (
        ("no/lovtid/2008-12-19-106", "2010-02-01", "2010-03-01"),
        ("no/lovtid/2009-04-24-22", "2009-12-18", "2010-01-01"),
    ):
        assert act_dates[act_id] == act_date
        assert act_date > part_date

    # SCOPE INFLATION, the other side of the retirement: two acts / four
    # bindings that no part grant covered and the act-level grant now dates.
    # Sound per binding — the instrument's text commences the WHOLE act, so the
    # bindings the Endrer header omitted are commenced by the same sentence —
    # and pinned so the population cannot grow unnoticed.
    for act_id, newly_dated in (
        ("no/lovtid/2005-01-07-2", ("no/lov/1903-06-09-7", "no/lov/1915-08-13-5")),
        ("no/lovtid/2006-06-30-52", ("no/lov/1975-06-06-31", "no/lov/2006-05-19-16")),
    ):
        entry = entries[act_id]
        assert entry.effective_status == "instrument_authorized"
        for law_id in newly_dated:
            assert law_id in entry.base_ids
            assert entry.effective_date_for_base(law_id)[0] == act_dates[act_id]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w53_corpus_the_two_scope_proofs_are_nested_not_overlapping() -> None:
    """Why ``BLOCKED_ONLY_ON_SCOPE`` is load-bearing rather than decorative.

    The widened proof is strictly WEAKER than the shipped one: every one of the
    607 shipped whole-act candidates also satisfies it, so route membership is
    decided entirely by which route got there first. 1,107 candidates carry the
    widened proof against 1,127 whose text the reader accepts; the 20-candidate
    gap is the block count, and none of it is the carve-out fence (its flip set
    here is 0 — see the unit test above).

    W-73 BREAKS the plain ``widened <= reader`` nesting, deliberately and in one
    direction only. ``widened_whole_act_scope`` is now the disjunction of two
    text readers, so 8 candidates carry it without carrying
    ``whole_act_operative_text`` — every one of them a title-cited subject W-47's
    reader cannot take. The containment that still has to hold is the one the
    route's disjointness rests on (``shipped <= widened``), and the reader's own
    population is unmoved at 1,127, which is the check that W-47's multi-part
    route saw nothing change.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    candidates = index.commencement_instruments
    assert len(candidates) == 2365
    reader = {c.source_id for c in candidates if c.whole_act_operative_text}
    widened = {c.source_id for c in candidates if c.widened_whole_act_scope}
    title_cited = {c.source_id for c in candidates if c.title_cited_whole_act_scope}
    shipped = {
        c.source_id
        for c in candidates
        if c.scope_status is NOCommencementScopeStatus.WHOLE_ACT
    }
    # 1,127 at W-53 and unmoved at W-73: the item added a second reader beside
    # this one, never inside it.
    assert len(reader) == 1127
    # 1,107 -> 1,115 at W-73.
    # 1,115 -> 1,189 at W-100: the title-cited citation form (74 more), read
    # beside W-47's reader as W-73's was — ``reader`` is unmoved at 1,127.
    assert len(widened) == 1189
    assert len(shipped) == 607
    assert len(title_cited) == _W73_TITLE_CITED_CANDIDATE_COUNT
    # Nesting, in the directions that still hold.
    assert shipped <= widened
    assert len(reader - widened) == 20
    # Every one of the 8 that break the old containment carries the title-cited
    # proof: no OTHER reader can put a candidate into ``widened`` without putting
    # it into ``reader`` too, which is the property that keeps this item's blast
    # attributable to one named reader.
    #
    # The inclusion is one-way on purpose, and the gap is the point:
    # ``widened_whole_act_scope`` is the title-cited proof AND the single-block
    # count AND W-51's carve-out fence, so a candidate can read as title-cited
    # and still not widen. Measured, exactly one does — ``2010-06-25-942`` — and
    # it is the witness that those two extra conjuncts are still load-bearing
    # over this reader rather than only over W-47's.
    title_cited_only = {
        c.source_id
        for c in candidates
        if c.title_cited_whole_act_scope and not c.whole_act_operative_text
    }
    assert widened - reader <= title_cited_only
    # 8 -> 82 at W-100 (the citation form), and the one-way gap closes:
    # ``2010-06-25-942`` now widens too, because W-100's single-block reader sets
    # its forskrift-only second block aside, so the title-cited proof and the
    # block count agree on it. The two extra conjuncts stay load-bearing — the
    # Bouvetøya instrument carries the title-cited proof's shape and is refused
    # by the citation form's own bare-date-tail conjunct.
    assert len(widened - reader) == 82
    assert title_cited_only - (widened - reader) == set()


def _title_cited_instrument_xml(
    *,
    title: str,
    operative: str,
    law_ids: tuple[str, ...] = ("lov/2012-08-24-64",),
    date_in_force: str = "2013-01-01",
) -> bytes:
    """A minimal Lovtidend commencement instrument with ONE operative block."""
    based_on = "".join(f"<li>{law_id}/§14</li>" for law_id in law_ids)
    return (
        "<html><head><title>"
        + title
        + '</title></head><body><header class="documentHeader"><dl>'
        + f'<dt class="title">Tittel</dt><dd class="title">{title}</dd>'
        + f'<dt class="dateInForce">I kraft fra</dt><dd class="dateInForce">{date_in_force}</dd>'
        + f'<dt class="basedOn">Hjemmel</dt><dd class="basedOn"><ul>{based_on}</ul></dd>'
        + '</dl></header><main class="documentBody">'
        + f'<article class="legalP" id="ledd-1">{operative}</article>'
        + "</main></body></html>"
    ).encode("utf-8")


def _parse_title_cited(
    *,
    title: str,
    operative: str,
    law_ids: tuple[str, ...] = ("lov/2012-08-24-64",),
) -> NOCommencementInstrumentCandidate:
    result = parse_no_commencement_instrument(
        _title_cited_instrument_xml(title=title, operative=operative, law_ids=law_ids),
        source_id="no/forskrift/test-1",
        locator="no://forskrift/test-1/instrument.xml",
        archive="test",
        member_name="instrument.xml",
    )
    assert result.candidate is not None
    return result.candidate


def test_w73_title_cited_whole_act_subject_accepts_the_bustottelova_witness() -> None:
    """W-73's witness, at the shape that carries it.

    ``no/forskrift/2012-08-24-826`` commenced bustøttelova on 2013-01-01 and its
    whole operative text is "Lov om bustøtte skal gjelde frå 1. januar 2013." —
    a NEW act named by its title, which is the one way neither W-47 reader can
    read. The candidate must carry the new proof and NOT the old one: the two
    readers stay separately visible so W-47's multi-part route, which reads
    ``whole_act_operative_text`` alone, cannot be moved by this item.
    """
    candidate = _parse_title_cited(
        title="Ikraftsetjing av lov 24. august 2012 nr. 64 om bustøtte (bustøttelova)",
        operative="Lov om bustøtte skal gjelde frå 1. januar 2013.",
    )

    assert candidate.title_cited_whole_act_scope is True
    assert candidate.whole_act_operative_text is False
    assert candidate.widened_whole_act_scope is True
    # The SHIPPED route is untouched: its shape reader still refuses, so the pair
    # can only ever reach the widened route.
    assert candidate.scope_status is NOCommencementScopeStatus.UNRESOLVED


def test_w73_title_cited_whole_act_subject_refuses_each_missing_conjunct() -> None:
    """Each of the four conjuncts, refused on its own.

    The reader is the loosest subject shape in the module, so what makes it safe
    is that every conjunct can only REFUSE. Each case below flips exactly one and
    the answer must go to False; none of them is carried by the others.
    """
    # TWO CITED ACTS — the corpus case, ``no/forskrift/2009-03-06-266``. A single
    # act-level grant cannot be attributed to whichever of two the loop reaches.
    assert (
        _parse_title_cited(
            title=(
                "Ikraftsetting av lov 6. mars 2009 nr. 12 om Statens finansfond "
                "og lov 6. mars 2009 nr. 13 om Statens obligasjonsfond"
            ),
            operative=(
                "Lov om Statens finansfond og lov om Statens obligasjonsfond "
                "trer i kraft straks."
            ),
            law_ids=("lov/2009-03-06-12", "lov/2009-03-06-13"),
        ).title_cited_whole_act_scope
        is False
    )
    # TITLE DISAGREEMENT — the subject names an act the instrument's own title
    # does not. This is the conjunct that ties a loose textual shape to the
    # document's identity.
    assert (
        _parse_title_cited(
            title="Ikraftsetjing av lov 24. august 2012 nr. 64 om bustøtte (bustøttelova)",
            operative="Lov om dyrevelferd skal gjelde frå 1. januar 2013.",
        ).title_cited_whole_act_scope
        is False
    )
    # SUBJECT NOT SENTENCE-INITIAL — a law-scoped narrowing, not an act-level
    # claim. The same adjacency argument ``_WHOLE_ACT_SUBJECT_RE`` records.
    assert (
        _parse_title_cited(
            title="Ikraftsetjing av lov 24. august 2012 nr. 64 om bustøtte (bustøttelova)",
            operative="Endringane i lov om bustøtte skal gjelde frå 1. januar 2013.",
        ).title_cited_whole_act_scope
        is False
    )
    # SUBDIVISION NAMED — the shared refusing fence, reused verbatim. A
    # title-cited subject may not carry a text that scopes to part of the act.
    assert (
        _parse_title_cited(
            title="Ikraftsetjing av lov 24. august 2012 nr. 64 om bustøtte (bustøttelova)",
            operative="Lov om bustøtte kapittel 2 skal gjelde frå 1. januar 2013.",
        ).title_cited_whole_act_scope
        is False
    )


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_w73_corpus_title_cited_route_dates_exactly_five_acts() -> None:
    """The whole measured effect of W-73's widening on the index, pinned.

    Five acts move ``contingent`` -> ``instrument_authorized``, each on the date
    its OWN kongelig resolusjon sets, and every one of the five is a NEW act
    whose consequential-amendment part binds a base law. Nothing else moves: the
    shipped whole-act route's grants are untouched (the widened route can
    only be entered by a pair the shipped route already refused), no act is
    re-dated, and no grant is withdrawn.
    """
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entries = {entry.source_id: entry for entry in index.entries}

    # The five, with the instrument that dates each and the date it sets.
    for act_id, instrument_id, date in (
        ("no/lovtid/2009-01-09-2", "no/forskrift/2009-01-09-7", "2009-06-01"),
        ("no/lovtid/2010-06-04-21", "no/forskrift/2010-06-04-760", "2010-07-01"),
        ("no/lovtid/2012-08-24-64", "no/forskrift/2012-08-24-826", "2013-01-01"),
        ("no/lovtid/2017-06-16-67", "no/forskrift/2017-06-16-763", "2017-07-01"),
        ("no/lovtid/2024-12-13-76", "no/forskrift/2024-12-13-3095", "2025-01-01"),
    ):
        entry = entries[act_id]
        assert entry.effective_status == "instrument_authorized"
        assert entry.effective_date == date
        grant = next(
            d
            for d in index.diagnostics
            if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED
            and d["source_id"] == act_id
        )
        assert instrument_id in grant["instrument_source_ids"]

    # The shipped route is unmoved, which is what ``BLOCKED_ONLY_ON_SCOPE``
    # guarantees structurally rather than by measurement.
    shipped = {
        d["source_id"]
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    }
    # 541 -> 542 at W-77: ``no/lovtid/2008-06-27-50`` gains its FIRST index entry
    # off the item-depth newness payload production and enters this shipped route
    # on its own instrument's date. The offering grew; the route did not move.
    # 542 -> 541 at W-79: ``no/lovtid/2025-03-28-4`` loses its only op (and with
    # it its index entry) to the structured payload lane's own-text invariant.
    # The offering shrank; the route still did not move.
    # 541 -> 545 at W-98 and 545 -> 546 at W-99 — recorded together because this
    # shard was not run at W-98 and the pin sat stale for it: W-98's pre-2001
    # lead grammar gave four acts their first index entry, each dated by its own
    # kongelig resolusjon through this route (``no/lovtid/2010-06-25-50``,
    # ``2016-01-22-1``, ``2016-12-16-99``, ``2022-12-16-93``; the index shard's
    # own notes carry the same four), and W-99's address-after-citation lead
    # gives ``no/lovtid/2017-06-16-51`` its first entry, dated 2018-01-01 by its
    # own ``no/forskrift/2017-06-16-751``. Every one is ``plain``.
    assert len(shipped) == 546

    # The reader's own corpus population, over the candidates rather than the
    # grants: 15 instruments carry the title-cited proof, and the five above are
    # the ones whose cited act is an offered amendment act blocked only on scope.
    title_cited = {
        c.source_id for c in index.commencement_instruments if c.title_cited_whole_act_scope
    }
    assert len(title_cited) == _W73_TITLE_CITED_CANDIDATE_COUNT


# --------------------------------------------------------------------------
# W-100: the section-scoped commencement route, and the two whole-act reader
# widenings that shipped with it.
# --------------------------------------------------------------------------

from lawvm.norway.commencement_instruments import (  # noqa: E402
    NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_DATE_CONFLICT,
    NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_REFUSED,
    NOCommencementSectionScopeAuthorizationConjunct,
    NOCommencementOpAddress,
    _title_cited_whole_act_subject,
    no_commencement_op_address,
    no_commencement_section_and_subpath,
)
from lawvm.norway.commencement_scope import (  # noqa: E402
    NOCommencementScopeItem,
    NOCommencementScopeReading,
    NOCommencementScopeStatement,
)
from lawvm.norway.sources import NOEffectiveStatus  # noqa: E402

_W100_ACT = "no/lovtid/2025-02-02-5"
_W100_LAW_A = "no/lov/2001-01-05-1"
_W100_LAW_B = "no/lov/2002-02-06-2"


def _w100_item(
    kind: str,
    *labels: str,
    part: str = "",
    law_ref: str = "",
    qualified: tuple[str, ...] = (),
    subpaths: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> NOCommencementScopeItem:
    return NOCommencementScopeItem(
        kind=kind,
        part_label=part,
        law_ref=law_ref,
        section_labels=labels,
        qualified_section_labels=qualified,
        qualified_section_subpaths=subpaths,
    )


def _w100_instrument(
    source_id: str,
    statements: tuple[NOCommencementScopeStatement, ...],
    *,
    effective_dates: tuple[str, ...] = ("2025-04-01",),
    affected_law_ids: tuple[str, ...] = ("no/lov/2025-02-02-5",),
    total: bool = True,
) -> NOCommencementInstrumentCandidate:
    """A candidate the whole-act routes refuse and the section-scoped route reads.

    ``scope_status`` is UNRESOLVED and callers pass ``BLOCKED_UNRESOLVED``, as for
    every route below the shipped one.
    """
    return NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=f"no://forskrift/{source_id.rsplit('/', 1)[1]}/original.lti.xml",
        archive="norway.farchive",
        member_name="",
        title="Delt ikraftsetting av lov 2. februar 2025 nr. 5",
        affected_law_ids=affected_law_ids,
        effective_dates=effective_dates,
        scope_status=NOCommencementScopeStatus.UNRESOLVED,
        source_excerpt="",
        scope_reading=NOCommencementScopeReading(
            statements=statements, total=total, dates=tuple(sorted(effective_dates))
        ),
    )


def _w100_evidence(
    *,
    part_law_ids: dict[str, str] | None = None,
    bound_law_ids: tuple[str, ...] = (_W100_LAW_A,),
    law_section_labels: dict[str, frozenset[str]] | None = None,
    unsectioned_op_laws: tuple[str, ...] = (),
    law_op_addresses: dict[str, tuple[NOCommencementOpAddress, ...]] | None = None,
) -> NOCommencementActPartEvidence:
    return NOCommencementActPartEvidence(
        part_law_ids=part_law_ids or {},
        bound_law_ids=bound_law_ids,
        law_section_labels=law_section_labels or {},
        unsectioned_op_laws=unsectioned_op_laws,
        law_op_addresses=law_op_addresses or {},
    )


def _w102_evidence(*addresses: tuple[str, str] | tuple[str, str, tuple[str, str]]) -> NOCommencementActPartEvidence:
    """W-102. Evidence with op addresses on law A: ``(section, subpath[, destination])``.

    ``law_section_labels`` is derived from the same addresses, as ``index.py``
    derives it, so the two granularities agree.
    """
    ops = tuple(
        NOCommencementOpAddress(
            section_label=address[0],
            subpath=address[1],
            destination=address[2] if len(address) == 3 else None,
        )
        for address in addresses
    )
    return _w100_evidence(
        law_section_labels={_W100_LAW_A: frozenset(op.section_label for op in ops if op.section_label)},
        law_op_addresses={_W100_LAW_A: ops},
    )


def _w100_authorize(instruments, evidence, offered=(_W100_ACT,)):
    return authorize_no_commencement_instruments(
        [(NOCommencementParseStatus.BLOCKED_UNRESOLVED, instrument) for instrument in instruments],
        offered_act_ids=set(offered),
        act_part_evidence={_W100_ACT: evidence},
    )


def test_section_scope_dates_sections_only_and_refuses_the_qualified_ones() -> None:
    """The 2009-06-19-702 shape: section lists, two dates, no binding date."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-700",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "2-3", "2-13", "4-2", qualified=("2-3",)),
                        date="2025-04-01",
                    ),
                    NOCommencementScopeStatement(subject=_w100_item("sections", "6-4"), date="2025-07-01"),
                ),
                effective_dates=("2025-04-01", "2025-07-01"),
            )
        ],
        _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"2-3", "2-13", "4-2", "6-4", "9"})}),
    )
    assert authorization.refusals == ()
    assert authorization.section_scoped_conflicts == ()
    assert authorization.section_scoped_refusals == ()
    assert len(authorization.section_scoped_authorizations) == 1
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.act_source_id == _W100_ACT
    assert receipt.law_id == _W100_LAW_A
    assert receipt.binding_date is None
    assert receipt.section_dates == (("2-13", "2025-04-01"), ("4-2", "2025-04-01"), ("6-4", "2025-07-01"))
    assert receipt.qualified_refused_labels == ("2-3",)
    assert receipt.excluded_section_labels == ()
    # § 9 is targeted and undated, § 2-3 was refused: the binding is not complete.
    assert receipt.complete is False
    assert receipt.passed_conjuncts == tuple(NOCommencementSectionScopeAuthorizationConjunct)
    assert [item.replay_authorized for item in authorization.instruments] == [True]
    # Nothing act-level, nothing per-binding: the landing is its own.
    assert authorization.authorized_effective_dates() == {}
    assert authorization.part_authorized_effective_dates() == {}
    assert list(authorization.section_scoped_landings()) == [_W100_ACT]
    detail = receipt.to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_AUTHORIZED
    assert detail["section_dates"] == [["2-13", "2025-04-01"], ["4-2", "2025-04-01"], ["6-4", "2025-07-01"]]
    assert detail["blocking"] is False
    assert "base_ids" not in detail


def test_section_scope_binding_date_with_carve_outs_restricted_to_targeted_sections() -> None:
    """The 2005-06-17-631 shape: the act commences, three sections are carved out."""
    statement = NOCommencementScopeStatement(
        subject=_w100_item("act"),
        date="2025-04-01",
        excluded=(
            _w100_item("sections", "4-4", qualified=("4-4",)),
            _w100_item("sections", "10-3", qualified=("10-3",)),
            _w100_item("sections", "4-6"),
        ),
    )
    authorization = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-701", (statement,))],
        _w100_evidence(
            law_section_labels={_W100_LAW_A: frozenset({"4-4", "2-1"})},
            unsectioned_op_laws=(_W100_LAW_A,),
        ),
    )
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.binding_date == "2025-04-01"
    assert receipt.section_dates == ()
    # A ledd-qualified carve-out excludes the WHOLE section; carve-outs the act's
    # ops never target are recorded as unbound, not landed.
    assert receipt.excluded_section_labels == ("4-4",)
    assert receipt.unbound_section_labels == ("10-3", "4-6")
    assert receipt.complete is False
    # With nothing targeted carved out, the binding is complete — the
    # unsectioned op takes the binding date.
    complete = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-701", (statement,))],
        _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"2-1"})}, unsectioned_op_laws=(_W100_LAW_A,)),
    ).section_scoped_authorizations[0]
    assert complete.excluded_section_labels == ()
    assert complete.complete is True


def test_section_scope_part_statements_resolve_through_the_part_map() -> None:
    """The 2025-04-04-601 shape: named parts, one with a carve-out, on a multi-law act."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-702",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("part", part="I"),
                        date="2025-04-01",
                        excluded=(_w100_item("sections", "2-22", "2-23"),),
                    ),
                    NOCommencementScopeStatement(subject=_w100_item("part", part="II"), date="2025-04-01"),
                ),
            )
        ],
        _w100_evidence(
            part_law_ids={"I": _W100_LAW_A, "II": _W100_LAW_B},
            bound_law_ids=(_W100_LAW_A, _W100_LAW_B),
            law_section_labels={
                _W100_LAW_A: frozenset({"1-1", "2-22", "2-23"}),
                _W100_LAW_B: frozenset({"35"}),
            },
        ),
    )
    receipts = {r.law_id: r for r in authorization.section_scoped_authorizations}
    assert receipts[_W100_LAW_A].binding_date == "2025-04-01"
    assert receipts[_W100_LAW_A].excluded_section_labels == ("2-22", "2-23")
    assert receipts[_W100_LAW_A].complete is False
    assert receipts[_W100_LAW_B].binding_date == "2025-04-01"
    assert receipts[_W100_LAW_B].complete is True
    assert authorization.refusals == ()


def test_section_scope_act_statement_with_part_carve_outs() -> None:
    """The 2020-05-20-1032 shape: the act commences less parts I (two sections) and V (whole)."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-703",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("act"),
                        date="2025-04-01",
                        excluded=(
                            _w100_item("part", "44", "47", part="I", law_ref=_W100_LAW_A, qualified=("44",)),
                            _w100_item("part", part="II", law_ref=_W100_LAW_B),
                        ),
                    ),
                ),
            )
        ],
        _w100_evidence(
            part_law_ids={"I": _W100_LAW_A, "II": _W100_LAW_B, "III": "no/lov/2003-03-07-3"},
            bound_law_ids=(_W100_LAW_A, _W100_LAW_B, "no/lov/2003-03-07-3"),
            law_section_labels={_W100_LAW_A: frozenset({"44", "47", "50"}), "no/lov/2003-03-07-3": frozenset({"1"})},
        ),
    )
    receipts = {r.law_id: r for r in authorization.section_scoped_authorizations}
    assert set(receipts) == {_W100_LAW_A, "no/lov/2003-03-07-3"}
    assert receipts[_W100_LAW_A].excluded_section_labels == ("44", "47")
    assert receipts[_W100_LAW_A].complete is False
    assert receipts["no/lov/2003-03-07-3"].complete is True


@pytest.mark.parametrize(
    ("statements", "evidence", "reason"),
    [
        (
            (NOCommencementScopeStatement(subject=_w100_item("sections", "5"), date="2025-04-01"),),
            _w100_evidence(bound_law_ids=(_W100_LAW_A, _W100_LAW_B)),
            "section list without a resolvable law on a multi-law act",
        ),
        (
            (NOCommencementScopeStatement(subject=_w100_item("part", part="IV"), date="2025-04-01"),),
            _w100_evidence(part_law_ids={"I": _W100_LAW_A}),
            "part IV resolves no law",
        ),
        (
            (NOCommencementScopeStatement(subject=_w100_item("sections", "5", law_ref="no/lov/1999-09-09-9"), date="2025-04-01"),),
            _w100_evidence(),
            "cited law no/lov/1999-09-09-9 is not bound by the act",
        ),
        (
            (
                NOCommencementScopeStatement(
                    subject=_w100_item("part", part="I"),
                    date="2025-04-01",
                    excluded=(_w100_item("part", part="II"),),
                ),
            ),
            _w100_evidence(part_law_ids={"I": _W100_LAW_A, "II": _W100_LAW_B}, bound_law_ids=(_W100_LAW_A, _W100_LAW_B)),
            "whole part carved out of a part",
        ),
        (
            (
                NOCommencementScopeStatement(subject=_w100_item("act"), date="2025-04-01"),
                NOCommencementScopeStatement(subject=_w100_item("act"), date="2025-07-01"),
            ),
            _w100_evidence(),
            f"two binding dates for {_W100_LAW_A}",
        ),
        (
            (NOCommencementScopeStatement(subject=_w100_item("sections", "5", qualified=("5",)), date="2025-04-01"),),
            _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"5"})}),
            f"every dated label of {_W100_LAW_A} is ledd-qualified",
        ),
    ],
)
def test_section_scope_refuses_with_the_reason_on_the_receipt(statements, evidence, reason: str) -> None:
    authorization = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-704", statements, effective_dates=("2025-04-01", "2025-07-01"))],
        evidence,
    )
    assert authorization.section_scoped_authorizations == ()
    assert [r.reason for r in authorization.section_scoped_refusals] == [reason]
    # The generic refusal stands beside it: the pair re-dates nothing.
    assert [r.instrument_source_id for r in authorization.refusals] == ["no/forskrift/2025-03-01-704"]
    detail = authorization.section_scoped_refusals[0].to_diagnostic_detail()
    assert detail["rule_id"] == NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_REFUSED
    assert detail["refusal"] == reason


def test_section_scope_ignores_a_pair_the_reader_refused() -> None:
    authorization = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-705", (), total=False)],
        _w100_evidence(),
    )
    assert authorization.section_scoped_authorizations == ()
    assert authorization.section_scoped_refusals == ()
    assert len(authorization.refusals) == 1


def test_section_scope_counts_only_amendment_acts_among_the_cited_ids() -> None:
    """no/forskrift/2015-06-12-633 cites kringkastingsloven as the forskrift part's hjemmel."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-706",
                (NOCommencementScopeStatement(subject=_w100_item("act"), date="2025-04-01"),),
                affected_law_ids=("no/lov/2025-02-02-5", "no/lov/1992-12-04-127"),
            )
        ],
        _w100_evidence(),
    )
    assert len(authorization.section_scoped_authorizations) == 1
    # But two AMENDMENT acts in one text refuse.
    two_acts = authorize_no_commencement_instruments(
        [(
            NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            _w100_instrument(
                "no/forskrift/2025-03-01-706",
                (NOCommencementScopeStatement(subject=_w100_item("act"), date="2025-04-01"),),
                affected_law_ids=("no/lov/2025-02-02-5", "no/lov/2025-03-03-6"),
            ),
        )],
        offered_act_ids={_W100_ACT, "no/lovtid/2025-03-03-6"},
        act_part_evidence={_W100_ACT: _w100_evidence(), "no/lovtid/2025-03-03-6": _w100_evidence()},
    )
    assert two_acts.section_scoped_authorizations == ()
    assert {r.reason for r in two_acts.section_scoped_refusals} == {"instrument cites several acts"}


def test_section_scope_conflicts_drop_the_whole_binding() -> None:
    """Two binding dates, or a section dated against a binding it was not carved out of."""
    first = _w100_instrument(
        "no/forskrift/2025-03-01-707",
        (NOCommencementScopeStatement(subject=_w100_item("act"), date="2025-04-01"),),
    )
    second = _w100_instrument(
        "no/forskrift/2025-03-01-708",
        (NOCommencementScopeStatement(subject=_w100_item("act"), date="2025-07-01"),),
        effective_dates=("2025-07-01",),
    )
    authorization = _w100_authorize([first, second], _w100_evidence())
    assert authorization.section_scoped_authorizations == ()
    assert len(authorization.section_scoped_conflicts) == 1
    conflict = authorization.section_scoped_conflicts[0]
    assert conflict.section_label == ""
    assert conflict.effective_dates == ("2025-04-01", "2025-07-01")
    assert conflict.to_diagnostic_detail()["rule_id"] == NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_DATE_CONFLICT
    assert conflict.to_diagnostic_detail()["blocking"] is True
    # Both generic refusals stand: neither pair re-dated anything.
    assert len(authorization.refusals) == 2

    third = _w100_instrument(
        "no/forskrift/2025-03-01-709",
        (NOCommencementScopeStatement(subject=_w100_item("sections", "6"), date="2025-07-01"),),
        effective_dates=("2025-07-01",),
    )
    contradiction = _w100_authorize([first, third], _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"6"})}))
    assert contradiction.section_scoped_authorizations == ()
    assert contradiction.section_scoped_conflicts[0].section_label == "6"


def test_section_scope_two_ledd_level_dates_for_one_section_do_not_conflict() -> None:
    """no/lovtid/2021-06-11-84: § 4-5 andre ledd (2025) beside § 4-5 første, tredje … ledd (2022)."""
    first = _w100_instrument(
        "no/forskrift/2025-03-01-710",
        (NOCommencementScopeStatement(subject=_w100_item("sections", "4-5", "1-7", qualified=("4-5",)), date="2025-04-01"),),
    )
    second = _w100_instrument(
        "no/forskrift/2025-03-01-711",
        (NOCommencementScopeStatement(subject=_w100_item("sections", "4-5", qualified=("4-5",)), date="2025-07-01"),),
        effective_dates=("2025-07-01",),
    )
    authorization = _w100_authorize([first, second], _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"4-5", "1-7"})}))
    assert authorization.section_scoped_conflicts == ()
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.section_dates == (("1-7", "2025-04-01"),)
    assert receipt.qualified_refused_labels == ("4-5",)
    assert receipt.instrument_source_ids == ("no/forskrift/2025-03-01-710", "no/forskrift/2025-03-01-711")


def test_section_scope_carved_out_section_may_be_dated_by_a_later_instrument() -> None:
    """The staged pattern itself: carve out now, date later, no conflict."""
    first = _w100_instrument(
        "no/forskrift/2025-03-01-712",
        (
            NOCommencementScopeStatement(
                subject=_w100_item("act"), date="2025-04-01", excluded=(_w100_item("sections", "10-3"),)
            ),
        ),
    )
    second = _w100_instrument(
        "no/forskrift/2025-03-01-713",
        (NOCommencementScopeStatement(subject=_w100_item("sections", "10-3"), date="2025-07-01"),),
        effective_dates=("2025-07-01",),
    )
    authorization = _w100_authorize([first, second], _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"10-3", "2"})}))
    assert authorization.section_scoped_conflicts == ()
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.binding_date == "2025-04-01"
    assert receipt.section_dates == (("10-3", "2025-07-01"),)
    # Once dated, the section is no longer an exclusion, and the binding is complete.
    assert receipt.excluded_section_labels == ()
    assert receipt.complete is True


def test_section_scope_yields_to_an_act_level_grant_and_to_a_part_grant() -> None:
    """Older routes win per act and per binding; the section proposal is dropped without a receipt."""
    widened = _widened_instrument("no/forskrift/2025-03-01-714")
    sectioned = _w100_instrument(
        "no/forskrift/2025-03-01-715",
        (NOCommencementScopeStatement(subject=_w100_item("sections", "5"), date="2025-07-01"),),
        effective_dates=("2025-07-01",),
    )
    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, widened),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, sectioned),
        ],
        offered_act_ids={_W100_ACT},
        act_part_evidence={_W100_ACT: _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"5"})})},
    )
    # The widened claim is refuted by the LATER sectioned sibling, so nothing
    # act-level lands either — the ordering W-51 fixed — and the section grant
    # stands on its own.
    assert authorization.widened_whole_act_authorizations == ()
    assert len(authorization.section_scoped_authorizations) == 1

    part_dated = _part_instrument(
        "no/forskrift/2025-03-01-716",
        changed_law_ids=(_W100_LAW_A,),
    )
    authorization = authorize_no_commencement_instruments(
        [
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, part_dated),
            (NOCommencementParseStatus.BLOCKED_UNRESOLVED, sectioned),
        ],
        offered_act_ids={_W100_ACT},
        act_part_evidence={
            _W100_ACT: _w100_evidence(
                part_law_ids={"I": _W100_LAW_A, "II": _W100_LAW_B},
                bound_law_ids=(_W100_LAW_A, _W100_LAW_B),
                law_section_labels={_W100_LAW_A: frozenset({"5"})},
            )
        },
    )
    assert len(authorization.part_authorizations) == 1
    assert authorization.section_scoped_authorizations == ()
    assert authorization.section_scoped_conflicts == ()


# --------------------------------------------------------------------------
# W-102: ledd-precise grants and carve-outs, admitted against the op addresses.
# --------------------------------------------------------------------------


def test_w102_op_address_reads_the_section_step_wherever_it_stands() -> None:
    """The subpath is everything below the section step, in the grafter's spelling."""
    assert no_commencement_section_and_subpath((("section", "2-3"), ("subsection", "2"))) == ("2-3", "subsection:2")
    assert no_commencement_section_and_subpath(
        (("chapter", "5A"), ("section", "5A-1"), ("subsection", "1"), ("sentence", "2"))
    ) == ("5A-1", "subsection:1/sentence:2")
    assert no_commencement_section_and_subpath((("section", "4-4"),)) == ("4-4", "")
    assert no_commencement_section_and_subpath((("chapter", "5A"),)) == (None, "")
    assert no_commencement_section_and_subpath(()) == (None, "")

    class _Address:
        def __init__(self, path):
            self.path = path

    class _Op:
        def __init__(self, target, destination=None):
            self.target = target
            self.destination = destination

    renumber = no_commencement_op_address(
        _Op(_Address((("section", "4-4"), ("subsection", "3"))), _Address((("section", "4-4"), ("subsection", "4"))))
    )
    assert renumber == NOCommencementOpAddress(section_label="4-4", subpath="subsection:3", destination=("4-4", "subsection:4"))
    assert no_commencement_op_address(_Op(None)) == NOCommencementOpAddress(section_label=None)
    assert renumber.to_dict() == {"section_label": "4-4", "subpath": "subsection:3", "destination": ["4-4", "subsection:4"]}


def test_w102_ledd_grant_lands_by_path_when_every_op_sits_inside_it() -> None:
    """The 2009-06-19-702 shape against the 2009 act's real op shapes: § 2-3
    andre ledd (one REPLACE on subsection 2) and § 10-4 første ledd (one on
    subsection 1) are dated by path; the binding becomes complete."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-720",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item(
                            "sections", "2-3", "2-13", "10-4",
                            qualified=("2-3", "10-4"),
                            subpaths=(("10-4", ("subsection:1",)), ("2-3", ("subsection:2",))),
                        ),
                        date="2025-04-01",
                    ),
                ),
            )
        ],
        _w102_evidence(("2-3", "subsection:2"), ("2-13", ""), ("10-4", "subsection:1")),
    )
    assert authorization.section_scoped_refusals == ()
    assert authorization.section_scoped_conflicts == ()
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.binding_date is None
    assert receipt.section_dates == (("2-13", "2025-04-01"),)
    assert receipt.subpath_dates == (("10-4", "subsection:1", "2025-04-01"), ("2-3", "subsection:2", "2025-04-01"))
    assert receipt.qualified_refused_labels == ()
    assert receipt.qualified_fallback_reasons == ()
    assert receipt.excluded_subpaths == ()
    assert receipt.complete is True
    detail = receipt.to_diagnostic_detail()
    assert detail["subpath_dates"] == [["10-4", "subsection:1", "2025-04-01"], ["2-3", "subsection:2", "2025-04-01"]]
    assert detail["excluded_subpaths"] == []
    assert detail["qualified_fallback_reasons"] == []


def test_w102_ledd_grant_leaves_the_ops_outside_the_path_undated() -> None:
    """An op on § 2-3 ledd 3 under a grant of ledd 2 alone is not dated (no
    binding date to fall back on): the path lands, the binding is partial."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-721",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "2-3", qualified=("2-3",), subpaths=(("2-3", ("subsection:2",)),)),
                        date="2025-04-01",
                    ),
                ),
            )
        ],
        _w102_evidence(("2-3", "subsection:2"), ("2-3", "subsection:3/sentence:1")),
    )
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.subpath_dates == (("2-3", "subsection:2", "2025-04-01"),)
    assert receipt.qualified_refused_labels == ()
    assert receipt.complete is False


def test_w102_whole_section_op_keeps_the_qualified_label_refused() -> None:
    """``§ 3 skal lyde:`` cannot be split at ``annet ledd``: W-100's refusal stands, with the reason."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-722",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "3", "4", qualified=("3",), subpaths=(("3", ("subsection:2",)),)),
                        date="2025-04-01",
                    ),
                ),
            )
        ],
        _w102_evidence(("3", ""), ("4", "")),
    )
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.section_dates == (("4", "2025-04-01"),)
    assert receipt.subpath_dates == ()
    assert receipt.qualified_refused_labels == ("3",)
    assert receipt.qualified_fallback_reasons == (("3", "op on § 3 stands above the named subsection:2"),)
    assert receipt.complete is False


def test_w102_ledd_op_above_a_named_punktum_keeps_the_label_refused() -> None:
    """A REPLACE of the whole ledd 1 cannot be split at ``første ledd fjerde punktum``."""
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-723",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "6", qualified=("6",), subpaths=(("6", ("subsection:1/sentence:4",)),)),
                        date="2025-04-01",
                    ),
                ),
            )
        ],
        _w102_evidence(("6", "subsection:1"), ("6", "subsection:1/sentence:4")),
    )
    assert authorization.section_scoped_authorizations == ()
    assert [r.reason for r in authorization.section_scoped_refusals] == [f"every dated label of {_W100_LAW_A} is ledd-qualified"]


def test_w102_qualifier_without_a_path_and_evidence_without_addresses_fall_back() -> None:
    """``siste ledd`` spells no path; a caller supplying only section labels admits nothing below them."""
    pathless = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-724",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "3", "4", qualified=("3",)), date="2025-04-01"
                    ),
                ),
            )
        ],
        _w102_evidence(("3", "subsection:2"), ("4", "")),
    )
    receipt = pathless.section_scoped_authorizations[0]
    assert receipt.qualified_refused_labels == ("3",)
    assert receipt.qualified_fallback_reasons == (("3", "the qualifier spells no path"),)

    no_addresses = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-725",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "3", "4", qualified=("3",), subpaths=(("3", ("subsection:2",)),)),
                        date="2025-04-01",
                    ),
                ),
            )
        ],
        _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"3", "4"})}),
    )
    receipt = no_addresses.section_scoped_authorizations[0]
    assert receipt.qualified_refused_labels == ("3",)
    assert receipt.qualified_fallback_reasons == (("3", "the act evidence carries no op addresses"),)
    assert receipt.subpath_dates == ()


def test_w102_ledd_carve_out_excludes_the_path_and_dates_the_rest_of_the_section() -> None:
    """The 2005-06-17-631 shape against the 2005 act's op: ``med unntak av nytt
    § 4-4 tredje ledd`` with the act's RENUMBER of old ledd 3 to 4 (target
    inside the named path, destination outside — the shift belongs with the
    insert). Only ``subsection:3`` is excluded; an op on ledd 1 takes the
    binding date."""
    statement = NOCommencementScopeStatement(
        subject=_w100_item("act"),
        date="2025-04-01",
        excluded=(
            _w100_item("sections", "4-4", qualified=("4-4",), subpaths=(("4-4", ("subsection:3",)),)),
            _w100_item("sections", "4-6"),
        ),
    )
    authorization = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-726", (statement,))],
        _w102_evidence(("4-4", "subsection:3", ("4-4", "subsection:4")), ("4-4", "subsection:1"), ("4-6", "")),
    )
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.binding_date == "2025-04-01"
    assert receipt.excluded_section_labels == ("4-6",)
    assert receipt.excluded_subpaths == (("4-4", "subsection:3"),)
    assert receipt.qualified_fallback_reasons == ()
    assert receipt.complete is False
    assert receipt.to_diagnostic_detail()["excluded_subpaths"] == [["4-4", "subsection:3"]]

    # The same carve-out with the evidence at section granularity only: the
    # whole section is excluded, as under W-100.
    coarse = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-727", (statement,))],
        _w100_evidence(law_section_labels={_W100_LAW_A: frozenset({"4-4", "4-6"})}),
    )
    assert coarse.section_scoped_authorizations[0].excluded_section_labels == ("4-4", "4-6")
    assert coarse.section_scoped_authorizations[0].excluded_subpaths == ()


def test_w102_renumber_into_a_named_path_from_outside_falls_back_to_the_whole_section() -> None:
    """The repeal of ledd 2 carved out while old ledd 3 is renumbered to 2:
    dating the shift by the binding would land it on an occupied slot, so the
    whole section stays carved out."""
    statement = NOCommencementScopeStatement(
        subject=_w100_item("act"),
        date="2025-04-01",
        excluded=(_w100_item("sections", "5", qualified=("5",), subpaths=(("5", ("subsection:2",)),)),),
    )
    authorization = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-728", (statement,))],
        _w102_evidence(("5", "subsection:2"), ("5", "subsection:3", ("5", "subsection:2")), ("7", "")),
    )
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.excluded_section_labels == ("5",)
    assert receipt.excluded_subpaths == ()
    assert receipt.qualified_fallback_reasons == (
        ("5", "op on § 5 subsection:3 moves into the named subsection:2 from outside every named path"),
    )

    across = _w100_authorize(
        [_w100_instrument("no/forskrift/2025-03-01-729", (statement,))],
        _w102_evidence(("5", "subsection:2", ("6", "subsection:1")), ("7", "")),
    )
    assert across.section_scoped_authorizations[0].qualified_fallback_reasons == (
        ("5", "op on § 5 moves across sections"),
    )


def test_w102_shifts_inside_a_ledd_range_are_admitted_and_across_two_dates_refused() -> None:
    """``§ 62 annet til syvende ledd`` (no/forskrift/2016-09-30-1136) names
    every ledd its five shifts touch, so the insert and the shifts all take
    the date; the same shifts under two differently dated paths are refused."""
    ops = (
        ("62", "subsection:2"),
        ("62", "subsection:6", ("62", "subsection:7")),
        ("62", "subsection:5", ("62", "subsection:6")),
        ("62", "subsection:4", ("62", "subsection:5")),
        ("62", "subsection:3", ("62", "subsection:4")),
        ("62", "subsection:2", ("62", "subsection:3")),
    )
    paths = tuple(f"subsection:{n}" for n in range(2, 8))
    authorization = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-730",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "62", qualified=("62",), subpaths=(("62", paths),)),
                        date="2025-04-01",
                    ),
                ),
            )
        ],
        _w102_evidence(*ops),
    )
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.qualified_fallback_reasons == ()
    assert receipt.subpath_dates == tuple(("62", path, "2025-04-01") for path in paths)
    assert receipt.complete is True

    staged = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-731",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "62", qualified=("62",), subpaths=(("62", paths[:3]),)),
                        date="2025-04-01",
                    ),
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "62", qualified=("62",), subpaths=(("62", paths[3:]),)),
                        date="2025-07-01",
                    ),
                ),
                effective_dates=("2025-04-01", "2025-07-01"),
            )
        ],
        _w102_evidence(*ops),
    )
    assert staged.section_scoped_authorizations == ()
    assert [r.reason for r in staged.section_scoped_refusals] == [f"every dated label of {_W100_LAW_A} is ledd-qualified"]


def test_w102_two_paths_of_one_section_on_two_dates_stage_and_overlapping_ones_conflict() -> None:
    """The staged pattern lands both paths; a path dated against a path above it does not."""
    disjoint = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-732",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "4-5", qualified=("4-5",), subpaths=(("4-5", ("subsection:2",)),)),
                        date="2025-04-01",
                    ),
                    NOCommencementScopeStatement(
                        subject=_w100_item(
                            "sections", "4-5", qualified=("4-5",), subpaths=(("4-5", ("subsection:1", "subsection:3")),)
                        ),
                        date="2025-07-01",
                    ),
                ),
                effective_dates=("2025-04-01", "2025-07-01"),
            )
        ],
        _w102_evidence(("4-5", "subsection:1"), ("4-5", "subsection:2"), ("4-5", "subsection:3/sentence:2")),
    )
    assert disjoint.section_scoped_conflicts == ()
    receipt = disjoint.section_scoped_authorizations[0]
    assert receipt.subpath_dates == (
        ("4-5", "subsection:1", "2025-07-01"),
        ("4-5", "subsection:2", "2025-04-01"),
        ("4-5", "subsection:3", "2025-07-01"),
    )
    assert receipt.complete is True

    overlapping = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-733",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "4-5", qualified=("4-5",), subpaths=(("4-5", ("subsection:2",)),)),
                        date="2025-04-01",
                    ),
                ),
            ),
            _w100_instrument(
                "no/forskrift/2025-03-01-734",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item(
                            "sections", "4-5", qualified=("4-5",), subpaths=(("4-5", ("subsection:2/sentence:1",)),)
                        ),
                        date="2025-07-01",
                    ),
                ),
                effective_dates=("2025-07-01",),
            ),
        ],
        _w102_evidence(("4-5", "subsection:2/sentence:1"), ("4-5", "subsection:2/sentence:2")),
    )
    assert overlapping.section_scoped_authorizations == ()
    conflict = overlapping.section_scoped_conflicts[0]
    assert conflict.section_label == "4-5"
    assert conflict.effective_dates == ("2025-04-01", "2025-07-01")

    # The same path on two dates in ONE instrument refuses at the proposal.
    repeated = _w100_authorize(
        [
            _w100_instrument(
                "no/forskrift/2025-03-01-735",
                (
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "4-5", qualified=("4-5",), subpaths=(("4-5", ("subsection:2",)),)),
                        date="2025-04-01",
                    ),
                    NOCommencementScopeStatement(
                        subject=_w100_item("sections", "4-5", qualified=("4-5",), subpaths=(("4-5", ("subsection:2",)),)),
                        date="2025-07-01",
                    ),
                ),
                effective_dates=("2025-04-01", "2025-07-01"),
            )
        ],
        _w102_evidence(("4-5", "subsection:2")),
    )
    assert repeated.section_scoped_authorizations == ()
    assert [r.reason for r in repeated.section_scoped_refusals] == [
        f"two dates for § 4-5 subsection:2 of {_W100_LAW_A}"
    ]


def test_w102_carved_out_path_dated_by_a_later_instrument_drops_the_exclusion() -> None:
    """The 2020-05-20-1032 / 2023-09-01-1380 pair on § 44 tredje ledd: carved
    out of the 2020 binding, dated straks by the 2023 instrument; the binding
    completes and § 44's other ops keep the binding date."""
    first = _w100_instrument(
        "no/forskrift/2025-03-01-736",
        (
            NOCommencementScopeStatement(
                subject=_w100_item("act"),
                date="2025-04-01",
                excluded=(
                    _w100_item("sections", "44", "47", qualified=("44",), subpaths=(("44", ("subsection:3",)),)),
                ),
            ),
        ),
    )
    second = _w100_instrument(
        "no/forskrift/2025-03-01-737",
        (
            NOCommencementScopeStatement(
                subject=_w100_item("sections", "44", "47", qualified=("44",), subpaths=(("44", ("subsection:3",)),)),
                date="2025-07-01",
            ),
        ),
        effective_dates=("2025-07-01",),
    )
    evidence = _w102_evidence(("44", "subsection:3"), ("44", "subsection:1/sentence:2"), ("47", ""))
    authorization = _w100_authorize([first, second], evidence)
    assert authorization.section_scoped_conflicts == ()
    receipt = authorization.section_scoped_authorizations[0]
    assert receipt.binding_date == "2025-04-01"
    assert receipt.section_dates == (("47", "2025-07-01"),)
    assert receipt.subpath_dates == (("44", "subsection:3", "2025-07-01"),)
    assert receipt.excluded_subpaths == ()
    assert receipt.excluded_section_labels == ()
    assert receipt.complete is True

    # The carve-out alone: § 44 excluded by path, § 47 whole, the binding partial.
    alone = _w100_authorize([first], evidence)
    receipt = alone.section_scoped_authorizations[0]
    assert receipt.excluded_subpaths == (("44", "subsection:3"),)
    assert receipt.excluded_section_labels == ("47",)
    assert receipt.complete is False


def test_w100_title_cited_subject_accepts_the_act_cited_by_date_and_number() -> None:
    """no/forskrift/2013-05-24-533, and the Bouvetøya instrument it must not take with it."""
    assert _title_cited_whole_act_subject(
        ("Lov 11. januar 2013 nr. 3 om Statens innkrevingssentral trer i kraft 1. juni 2013.",),
        title="Ikraftsetting lov 11. januar 2013 nr. 3 om Statens innkrevingssentral",
        cited_law_ids=("no/lov/2013-01-11-3",),
    )
    assert _title_cited_whole_act_subject(
        ("Lov av 21. juni 2002 nr. 45 om yrkestransport med motorvogn og fartøy (yrkestransportlova) gjeld frå 1. januar 2003.",),
        title="Ikraftsetjing av lov av 21. juni 2002 nr. 45 om yrkestransport med motorvogn og fartøy (yrkestransportlova)",
        cited_law_ids=("no/lov/2002-06-21-45",),
    )
    # Title agreement still carries the widened shape.
    assert not _title_cited_whole_act_subject(
        ("Lov 11. januar 2013 nr. 3 om Statens innkrevingssentral trer i kraft 1. juni 2013.",),
        title="Ikraftsetting av lov om noe annet",
        cited_law_ids=("no/lov/2013-01-11-3",),
    )
    # no/forskrift/2005-02-25-173: a territorial qualifier between verb and date refuses.
    assert not _title_cited_whole_act_subject(
        ("Lov 27. juni 2003 nr. 57 om Norges territorialfarvann og tilstøtende sone trer i kraft for Bouvetøya 1. april 2005.",),
        title="Ikrafttredelse av lov 27. juni 2003 nr. 57 om Norges territorialfarvann og tilstøtende sone",
        cited_law_ids=("no/lov/2003-06-27-57",),
    )


def test_w100_parse_sets_aside_a_forskrift_only_block_for_the_widened_route() -> None:
    """no/forskrift/2015-06-12-633's shape: a whole-act block, then a forskrift carve-out block."""
    payload = (
        "<html><body>\n"
        '<dd class="title">Ikraftsetting av lov 2. februar 2025 nr. 5 om testdata</dd>\n'
        '<dd class="basedOn"><a href="lov/2025-02-02-5">lov 2. februar 2025 nr. 5</a></dd>\n'
        '<dd class="dateInForce">2025-04-01</dd>\n'
        '<main class="documentBody">'
        '<article class="legalP">Lov 2. februar 2025 nr. 5 om testdata trer i kraft 1. april 2025.</article>'
        '<article class="legalP">Fra samme tidspunkt oppheves § 2-5 og § 2-6 i forskrift 28. februar 1997 nr. 153 om kringkasting.</article>'
        "</main></body></html>"
    ).encode("utf-8")
    result = parse_no_commencement_instrument(
        payload,
        source_id="no/forskrift/2025-03-01-720",
        locator="no://forskrift/2025-03-01-720/original.lti.xml",
        archive="lovtidend-avd1-2025.tar.bz2",
        member_name="lti/2025/sf-20250301-0720.xml",
    )
    candidate = result.candidate
    assert candidate is not None
    assert result.parse_status is NOCommencementParseStatus.BLOCKED_UNRESOLVED
    assert candidate.forskrift_blocks_dropped == 1
    assert candidate.title_cited_whole_act_scope is True
    assert candidate.widened_whole_act_scope is True
    # W-47's reader keeps reading the RAW blocks: the ``§`` in the forskrift block still refuses it.
    assert candidate.whole_act_operative_text is False
    # And the section-scoped reader read the act block as one act statement.
    assert candidate.scope_reading.total is True
    assert [s.to_dict() for s in candidate.scope_reading.statements] == [
        {"subject": {"kind": "act", "part_label": "", "law_ref": "", "section_labels": [], "qualified_section_labels": [], "qualified_section_subpaths": []}, "date": "2025-04-01", "excluded": []}
    ]
    reloaded = NOCommencementInstrumentCandidate.from_dict(candidate.to_dict())
    assert reloaded == candidate


def test_w100_corpus_the_seven_kringkasting_chain_acts() -> None:
    """The witness: the seven contingent acts in kringkastingsloven's chain, after W-100."""
    if _NO_FARCHIVE_PATH is None:
        pytest.skip("local Norway public archive is not installed")
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    entries = {e.source_id: e for e in index.entries}
    kk = "no/lov/1992-12-04-127"

    # Lane A: a principal act cited by date and number, dated whole.
    assert entries["no/lovtid/2013-01-11-3"].effective_status == "instrument_authorized"
    assert entries["no/lovtid/2013-01-11-3"].effective_date == "2013-06-01"

    # Sections only, two dates; W-102: the two ledd-qualified labels (§ 2-3
    # andre ledd, § 10-4 første ledd) are dated by path, since the act's one op
    # on each sits inside the named ledd, and the binding is complete.
    e = entries["no/lovtid/2009-06-19-92"]
    assert e.effective_status == "contingent"
    assert e.section_scoped_binding_dates == ((kk, ""),)
    assert e.section_scoped_effective_dates == (
        (kk, "2-13", "2009-07-01"), (kk, "4-2", "2009-07-01"), (kk, "6-1a", "2009-07-01"),
        (kk, "6-4", "2010-01-01"), (kk, "8-5", "2009-07-01"),
    )
    assert e.section_scoped_subpath_dates == (
        (kk, "10-4", "subsection:1", "2009-07-01"), (kk, "2-3", "subsection:2", "2009-07-01"),
    )
    assert e.section_scoped_complete_laws == (kk,)
    assert e.effective_date_for_base(kk) == (None, "section_instrument_authorized")
    assert e.effective_date_for_op(kk, "6-4") == ("2010-01-01", "section_instrument_authorized")
    assert e.effective_date_for_op(kk, "2-3", "subsection:2") == ("2009-07-01", "section_instrument_authorized")
    assert e.effective_date_for_op(kk, "2-3", "subsection:3") == (None, "contingent")
    assert e.effective_date_for_op(kk, "2-3") == (None, "contingent")

    # A binding date with one targeted carve-out — W-102: ``nytt § 4-4 tredje
    # ledd`` excludes the path alone (the act's RENUMBER of old ledd 3 to 4 sits
    # inside it); § 10-3 første og annet ledd, dated 2008 by
    # no/forskrift/2008-05-30-524, lands by path on a section the act never
    # yielded ops for (unbound, as before).
    e = entries["no/lovtid/2005-06-17-98"]
    assert e.section_scoped_binding_dates == ((kk, "2005-07-01"),)
    assert e.section_scoped_exclusions == ()
    assert e.section_scoped_subpath_exclusions == ((kk, "4-4", "subsection:3"),)
    assert e.section_scoped_subpath_dates == (
        (kk, "10-3", "subsection:1", "2008-07-01"), (kk, "10-3", "subsection:2", "2008-07-01"),
    )
    assert e.effective_date_for_op(kk, None) == ("2005-07-01", "section_instrument_authorized")
    assert e.effective_date_for_op(kk, "4-4", "subsection:3") == (None, "contingent")
    assert e.effective_date_for_op(kk, "4-4", "subsection:1") == ("2005-07-01", "section_instrument_authorized")
    assert e.effective_date_for_op(kk, "4-4") == ("2005-07-01", "section_instrument_authorized")

    # A forskrift-tail instrument citing kringkastingsloven as hjemmel: both bindings complete.
    e = entries["no/lovtid/2015-02-06-7"]
    assert e.section_scoped_binding_dates == (("no/lov/1987-05-15-21", "2015-07-01"), (kk, "2015-07-01"))
    assert e.section_scoped_complete_laws == ("no/lov/1987-05-15-21", kk)
    assert e.effective_date_for_base(kk) == ("2015-07-01", "section_instrument_authorized")

    # Part V of the 2020 act, dated by the 2023 ``straks`` instrument; part I's
    # § 44 tredje ledd, carved out in 2020 and dated straks in 2023, lands by
    # path (W-102) and markedsføringsloven's binding completes.
    e = entries["no/lovtid/2020-05-20-42"]
    assert (kk, "2023-09-01") in e.section_scoped_binding_dates
    assert kk in e.section_scoped_complete_laws
    assert ("no/lov/2009-01-09-2", "44") not in e.section_scoped_exclusions
    assert ("no/lov/2009-01-09-2", "44", "subsection:3", "2023-09-01") in e.section_scoped_subpath_dates
    assert ("no/lov/2009-01-09-2", "47", "2023-09-01") in e.section_scoped_effective_dates
    assert "no/lov/2009-01-09-2" in e.section_scoped_complete_laws

    # Part I of the 2025 act with §§ 2-22 and 2-23 carved out.
    e = entries["no/lovtid/2025-02-28-2"]
    assert (kk, "2025-05-01") in e.section_scoped_binding_dates
    assert e.section_scoped_exclusions == ((kk, "2-22"), (kk, "2-23"))
    assert kk not in e.section_scoped_complete_laws

    # The gradual-application instrument stays refused, by the reader.
    e = entries["no/lovtid/2025-04-25-12"]
    assert e.effective_status == "contingent"
    assert not e.has_section_scope(kk)
    refused = {
        d["instrument_source_id"]
        for d in index.diagnostics
        if d.get("rule_id") == NO_COMMENCEMENT_EXECUTION_REFUSED and d.get("source_id") == "no/lovtid/2025-04-25-12"
    }
    assert "no/forskrift/2025-06-10-967" in refused


def test_w100_corpus_totals() -> None:
    """The lane's corpus footprint, pinned so a grammar change has to move it deliberately."""
    if _NO_FARCHIVE_PATH is None:
        pytest.skip("local Norway public archive is not installed")
    index = build_no_amendment_index(_NO_FARCHIVE_PATH)
    grants = [d for d in index.diagnostics if d.get("rule_id") == NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_AUTHORIZED]
    conflicts = [d for d in index.diagnostics if d.get("rule_id") == NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_DATE_CONFLICT]
    refusals = [d for d in index.diagnostics if d.get("rule_id") == NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_REFUSED]
    # W-100 (2026-09-05): 261 bindings of 110 acts on 160 laws dated below
    # binding level (204 complete, 223 with a binding date, 38 sections-only; 70
    # ledd-qualified labels refused), one genuine conflict
    # (no/lovtid/2004-03-05-11 under two whole-act instruments a year apart),
    # 131 read-but-unresolved pairs (51 section lists under a short name on a
    # multi-law act, 28 keys whose every dated label was ledd-qualified, 13
    # act-level carve-outs naming a section without a law, …). Lane A moved 29
    # acts to instrument_authorized (widened 440 -> 469) and the generic
    # refusals fell 882 -> 728.
    # W-102 (2026-09-06): ledd-precise grants. 261 -> 280 bindings (124 acts,
    # 165 laws; complete 204 -> 224; binding-dated 223 unmoved), 138 dates
    # landed below section level over 91 labels of 42 bindings, 4 carve-outs
    # by path, whole-section carve-outs 32 -> 18, refused qualified labels
    # 70 -> 17 (reasons on the receipts), refusals 131 -> 108 (the 28
    # all-ledd-qualified keys -> 8; the 3 one-instrument staged keys land).
    assert len(grants) == 280
    assert sum(1 for g in grants if g["complete"]) == 224
    assert sum(1 for g in grants if g["binding_date"]) == 223
    assert len({g["source_id"] for g in grants}) == 124
    assert len({g["law_id"] for g in grants}) == 165
    assert [(c["source_id"], c["law_id"]) for c in conflicts] == [("no/lovtid/2004-03-05-11", "no/lov/1995-05-26-25")]
    assert len(refusals) == 108
    assert sum(1 for r in refusals if "ledd-qualified" in r["refusal"]) == 8
    assert sum(len(g["subpath_dates"]) for g in grants) == 138
    assert len({(g["source_id"], g["law_id"], label) for g in grants for label, _p, _d in g["subpath_dates"]}) == 91
    assert sum(1 for g in grants if g["subpath_dates"]) == 42
    assert sum(len(g["excluded_subpaths"]) for g in grants) == 4
    assert sum(len(g["excluded_section_labels"]) for g in grants) == 18
    assert sum(len(g["qualified_refused_labels"]) for g in grants) == 17
    # Every refused qualified label carries its reason, and none of the
    # reasons is a renumber straddle: the two shapes the corpus has (a shift
    # inside ``annet til syvende ledd``; ``nytt tredje ledd`` shifting old 3
    # to 4) are admitted by the union rule.
    reasons = [reason for g in grants for _label, reason in g["qualified_fallback_reasons"]]
    assert len(reasons) == 17
    assert not [r for r in reasons if "moves" in r]
    assert sum(1 for r in reasons if r == "the qualifier spells no path") == 4
    widened = [d for d in index.diagnostics if d.get("rule_id") == NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED]
    assert len(widened) == 469
    # No act-level grant of this lane, ever: the histogram's contingent column
    # only moves through lane A.
    assert index.status_counts()[NOEffectiveStatus.CONTINGENT] == 511
