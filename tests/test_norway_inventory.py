from __future__ import annotations

import io
import json
import tarfile
from collections import Counter
from typing import Any, cast

import pytest

from lawvm.norway.index import NOAmendmentIndex, NOAmendmentIndexEntry
from lawvm.norway.index import build_no_amendment_index, save_no_amendment_index
from lawvm.norway.inventory import NOInventory, build_no_inventory, build_no_missing_base_report
from lawvm.norway.sources import ingest_no_public_archives, open_no_archive


_BASE_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Testlov om data</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-1">
      <article class="legalArticle" data-name="§1">
        <h3 class="legalArticleHeader">§ 1. Formaal</h3>
        <article class="legalP">Loven gjelder testdata.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_open_no_archive_defaults_readonly_without_creating_missing_archive(tmp_path) -> None:
    missing = tmp_path / "unused.farchive"

    try:
        archive = open_no_archive(missing)
    except Exception:
        pass
    else:
        archive.close()

    assert not missing.exists()


def _amendment_xml(date_in_force: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">{date_in_force}</dd>
    <article class="document-change" data-document="lov/2025-01-01-1/§1">
      <article class="change" data-change-part="lov/2025-01-01-1/§1">
        <article class="futureLegalArticle" data-name="§1">
          <span class="futureLegalArticleHeader">
            <span class="legalArticleValue">§ 1</span>.
            <span class="legalArticleTitle">Nytt krav</span>
          </span>
          <article class="legalP">Oppdatert paragraftekst.</article>
        </article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _write_archive(archive_path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(archive_path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def test_build_no_inventory_summarizes_replayability(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10")),
            ("lti/2025/nl-20250303-006.xml", _amendment_xml("Kongen bestemmer")),
        ],
    )

    inventory = build_no_inventory(tmp_path).to_dict()

    assert inventory["current_laws"] == 1
    assert inventory["amendment_documents"] == 2
    assert inventory["amendment_documents_by_status"] == {"dated": 1, "contingent": 1}
    assert inventory["current_laws_with_amendments"] == 1
    assert inventory["current_laws_blocked_contingent"] == 1
    assert inventory["top_executable_blocked_current_laws"] == [
        {"base_id": "no/lov/2025-01-01-1", "amendments": 2}
    ]
    assert inventory["current_laws_fully_replayable"] == 0


def test_build_no_inventory_accepts_prebuilt_index(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10")),
        ],
    )
    index = build_no_amendment_index(tmp_path)
    index_path = tmp_path / "no_index.json"
    save_no_amendment_index(index, index_path)

    inventory = build_no_inventory(tmp_path, index_path=index_path).to_dict()

    assert inventory["amendment_documents_by_status"] == {"dated": 1}
    assert inventory["current_laws_fully_replayable"] == 1
    assert inventory["current_laws_with_amendments_fully_replayable_executable"] == 1


def test_build_no_inventory_preserves_current_law_source_diagnostics(tmp_path, monkeypatch) -> None:
    def fake_current_law_ids(_data_dir, *, diagnostics_out=None):
        if diagnostics_out is not None:
            diagnostics_out.append(
                {
                    "rule_id": "no_current_law_id_parse_marker_fallback_used",
                    "family": "source_pathology",
                    "phase": "parse",
                    "blocking": True,
                    "strict_disposition": "block",
                    "quirks_disposition": "record",
                }
            )
        return {"no/lov/2025-01-01-1"}

    monkeypatch.setattr("lawvm.norway.inventory.load_no_current_law_ids", fake_current_law_ids)
    monkeypatch.setattr("lawvm.norway.inventory.load_available_lti_law_ids", lambda _data_dir: set())

    inventory = build_no_inventory(tmp_path, index=NOAmendmentIndex(data_dir=str(tmp_path))).to_dict()

    assert inventory["current_law_source_diagnostic_count"] == 1
    assert inventory["current_law_source_diagnostic_rule_counts"] == {
        "no_current_law_id_parse_marker_fallback_used": 1
    }
    assert inventory["current_law_source_diagnostics"][0]["strict_disposition"] == "block"


def test_build_no_inventory_records_current_law_id_artifact_fallback(tmp_path, monkeypatch) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    monkeypatch.setattr("lawvm.norway.inventory.load_no_current_law_ids", lambda _data_dir, *, diagnostics_out=None: set())
    monkeypatch.setattr("lawvm.norway.inventory.load_available_lti_law_ids", lambda _data_dir: set())

    inventory = build_no_inventory(tmp_path, index=NOAmendmentIndex(data_dir=str(tmp_path))).to_dict()

    assert inventory["current_laws"] == 1
    assert inventory["current_law_source_diagnostic_rule_counts"] == {
        "no_inventory_current_law_id_artifact_fallback_used": 1
    }
    diagnostic = inventory["current_law_source_diagnostics"][0]
    assert diagnostic["phase"] == "acquisition"
    assert diagnostic["family"] == "source_pathology"
    assert diagnostic["fallback_current_law_count"] == 1
    assert diagnostic["strict_disposition"] == "block"


def test_build_no_inventory_accepts_farchive_source_path(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10")),
        ],
    )
    db_path = tmp_path / "norway.farchive"
    ingest_no_public_archives(tmp_path, db_path)

    index = build_no_amendment_index(db_path)
    inventory = build_no_inventory(db_path, index=index).to_dict()

    assert index.source_kind == "farchive"
    assert inventory["current_laws"] == 1
    assert inventory["amendment_documents_by_status"] == {"dated": 1}
    assert inventory["current_laws_fully_replayable"] == 1
    assert inventory["current_laws_with_amendments_fully_replayable_executable"] == 1


def test_ingest_no_public_archives_reports_unmapped_xml_members(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/unexpected-current.xml", b"<html/>")],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/unexpected-lovtidend.xml", b"<html/>")],
    )
    db_path = tmp_path / "norway.farchive"

    report = ingest_no_public_archives(tmp_path, db_path)

    assert report["current_locators_stored"] == 0
    assert report["original_locators_stored"] == 0
    assert report["amendment_locators_stored"] == 0
    assert report["skipped_unmapped"] == 2
    assert report["skipped_unmapped_entries"] == [
        {
            "rule_id": "no_ingest_unmapped_xml_member",
            "phase": "acquisition",
            "family": "source_pathology",
            "reason": "Norway Lovdata XML member filename could not be mapped to a legal source id",
            "kind": "current",
            "locator": "",
            "logical_id": "",
            "source_name": "gjeldende-lover.tar.bz2",
            "member_name": "nl/unexpected-current.xml",
            "blocking": True,
            "strict_disposition": "block",
            "quirks_disposition": "record",
        },
        {
            "rule_id": "no_ingest_unmapped_xml_member",
            "phase": "acquisition",
            "family": "source_pathology",
            "reason": "Norway Lovdata XML member filename could not be mapped to a legal source id",
            "kind": "lovtidend",
            "locator": "",
            "logical_id": "",
            "source_name": "lovtidend-avd1-2025.tar.bz2",
            "member_name": "lti/2025/unexpected-lovtidend.xml",
            "blocking": True,
            "strict_disposition": "block",
            "quirks_disposition": "record",
        },
    ]


def test_ingest_no_public_archives_reports_duplicate_logical_locators(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10"))],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025-2026.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-03-15"))],
    )
    db_path = tmp_path / "norway.farchive"

    report = ingest_no_public_archives(tmp_path, db_path)

    assert report["original_locators_stored"] == 1
    assert report["amendment_locators_stored"] == 1
    assert report["duplicate_locator_count"] == 2
    duplicate_entries = cast(list[dict[str, Any]], report["duplicate_locator_entries"])
    amendment_entries = [
        entry
        for entry in duplicate_entries
        if entry["kind"] == "amendment"
    ]
    assert len(amendment_entries) == 1
    entry = amendment_entries[0]
    assert entry["rule_id"] == "no_acquisition_duplicate_logical_locator"
    assert entry["phase"] == "acquisition"
    assert entry["family"] == "source_pathology"
    assert entry["logical_id"] == "no/lovtid/2025-02-02-5"
    assert entry["locator"] == "no://lovtid/2025-02-02-5/amendment.xml"
    assert entry["identical_payloads"] is False
    assert entry["blocking"] is True
    assert entry["strict_disposition"] == "block"
    assert entry["quirks_disposition"] == "block"
    assert entry["source_lane_selection"]["selected_source_lane"] == "existing_farchive_locator"
    assert entry["source_lane_selection"]["selected_source_locator"] == "no://lovtid/2025-02-02-5/amendment.xml"
    assert {
        attempt["lane_attempt_status"]
        for attempt in entry["source_lane_selection"]["source_lane_attempts"]
    } == {"selected_existing_conflict", "blocked_conflicting_duplicate"}


def test_build_no_inventory_accepts_commencement_override(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("Kongen bestemmer")),
        ],
    )
    commencement_path = tmp_path / "commencement.json"
    commencement_path.write_text(
        json.dumps(
            {"no/lovtid/2025-02-02-5": {"effective_date": "2025-02-10", "note": "manual"}}
        ),
        encoding="utf-8",
    )

    inventory = build_no_inventory(tmp_path, commencement_path=commencement_path).to_dict()

    assert inventory["amendment_documents_by_status"] == {"override": 1}
    assert inventory["current_laws_fully_replayable"] == 1
    assert inventory["current_laws_with_amendments_fully_replayable_executable"] == 1
    assert inventory["current_laws_blocked_contingent"] == 0


def test_build_no_inventory_tracks_missing_local_base_source(tmp_path) -> None:
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-19461213-021.xml", _BASE_XML)],
    )
    index = NOAmendmentIndex(
        data_dir=str(tmp_path),
        archive_names=[],
        entries=[
            NOAmendmentIndexEntry(
                source_id="no/lovtid/2025-02-02-5",
                archive="lovtidend-avd1-2025.tar.bz2",
                member_name="lti/2025/nl-20250202-005.xml",
                effective_status="dated",
                effective_date="2025-02-10",
                raw_date_in_force="2025-02-10",
                title="A",
                base_ids=("no/lov/1946-12-13-21",),
                n_ops=1,
            )
        ],
    )

    inventory = build_no_inventory(tmp_path, index=index).to_dict()

    assert inventory["current_laws"] == 1
    assert inventory["current_laws_with_local_base_source"] == 0
    assert inventory["current_laws_without_local_base_source"] == 1
    assert inventory["current_laws_with_amendments_missing_base_source"] == 1
    assert inventory["current_laws_with_amendments_fully_replayable_executable"] == 0
    assert inventory["top_executable_blocked_current_laws"] == []
    assert inventory["top_missing_base_source_current_laws"] == [
        {"base_id": "no/lov/1946-12-13-21", "amendments": 1}
    ]


def test_build_no_missing_base_report_groups_laws(tmp_path) -> None:
    inventory = build_no_inventory(tmp_path, index=NOAmendmentIndex(
        data_dir=str(tmp_path),
        archive_names=[],
        entries=[
            NOAmendmentIndexEntry(
                source_id="no/lovtid/2025-02-02-5",
                archive="lovtidend-avd1-2025.tar.bz2",
                member_name="lti/2025/nl-20250202-005.xml",
                effective_status="dated",
                effective_date="2025-02-10",
                raw_date_in_force="2025-02-10",
                title="A",
                base_ids=("no/lov/1946-12-13-21",),
                n_ops=1,
            )
        ],
    ))
    inventory.current_law_ids = {"no/lov/1946-12-13-21"}
    inventory.current_law_ids_with_local_base_source = set()

    report = build_no_missing_base_report(
        inventory,
        current_law_titles={"no/lov/1946-12-13-21": "Old law"},
    )

    assert report["missing_base_source_law_count"] == 1
    assert report["laws"] == [
        {
            "base_id": "no/lov/1946-12-13-21",
            "title": "Old law",
            "amendments": 1,
            "source_ids": ["no/lovtid/2025-02-02-5"],
        }
    ]
    assert report["current_law_title_diagnostic_count"] == 0


def test_build_no_missing_base_report_preserves_title_diagnostics(tmp_path, monkeypatch) -> None:
    def fake_titles(_data_dir, *, diagnostics_out=None):
        if diagnostics_out is not None:
            diagnostics_out.append(
                {
                    "rule_id": "no_current_law_title_parse_skipped",
                    "family": "source_pathology",
                    "phase": "parse",
                    "blocking": True,
                    "strict_disposition": "block",
                    "quirks_disposition": "record",
                }
            )
        return {}

    monkeypatch.setattr("lawvm.norway.inventory.load_no_current_law_titles", fake_titles)
    inventory = NOInventory(data_dir=tmp_path)
    inventory.current_law_ids = {"no/lov/1946-12-13-21"}
    inventory.current_law_ids_with_local_base_source = set()
    inventory.base_to_statuses["no/lov/1946-12-13-21"].append("dated")
    inventory.base_to_sources["no/lov/1946-12-13-21"].append("no/lovtid/2025-02-02-5")

    report = build_no_missing_base_report(inventory)

    assert report["missing_base_source_law_count"] == 1
    assert report["current_law_title_diagnostic_count"] == 1
    assert report["current_law_title_diagnostic_rule_counts"] == {
        "no_current_law_title_parse_skipped": 1
    }
    assert report["current_law_title_diagnostics"][0]["strict_disposition"] == "block"


# ---------------------------------------------------------------------------
# W-45: the "replayable original, no stored consolidation" census
# ---------------------------------------------------------------------------

_LTI_HEADER_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no"><head><title>{title}</title></head><body>
<header class="documentHeader"><dl class="data-document-key-info">
<dt class="dateInForce">I kraft fra</dt><dd class="dateInForce">{date_in_force}</dd>
<dt class="title">Tittel</dt><dd class="title">{title}</dd>
</dl></header>
<main class="documentBody" data-lovdata-URL="LTI/lov/{law}" id="dokument">
<h1>{title}</h1>{body}
<article class="legalArticle" data-name="§1">
  <h3 class="legalArticleHeader">§ 1. Formaal</h3>
  <article class="legalP">Loven gjelder testdata.</article>
</article>
</main></body></html>
"""

# The real Lovdata manifest shape (LOV-2013-06-21-60): a ``defaultP`` block whose
# own lead text carries the discriminator, an inner ``defaultList``, and one
# long-form citation per list item wrapped in nested articles.
_REPEAL_MANIFEST = (
    '<article class="defaultP" data-text-size="small">Følgende lov oppheves:'
    '<ul class="defaultList"><li><article class="listArticle">'
    '<article class="legalP">Lov 3. juni 2005 nr. 33 om forbud mot diskriminering '
    "på grunn av etnisitet, religion mv. (diskrimineringsloven).</article>"
    "</article></li></ul></article>"
)
# Structurally IDENTICAL block, different lead text: amend, not repeal.
_AMEND_MANIFEST = (
    '<article class="defaultP" data-text-size="small">Endringar i følgjande lover:'
    '<ul class="defaultList"><li><article class="listArticle">'
    '<article class="legalP">Lov 17. juni 2005 nr. 58 om skipssikkerhet.</article>'
    "</article></li></ul></article>"
)


def _lti_xml(law: str, title: str, *, date_in_force: str = "2025-01-01", body: str = "") -> bytes:
    return _LTI_HEADER_TEMPLATE.format(
        law=law, title=title, date_in_force=date_in_force, body=body
    ).encode("utf-8")


def test_no_no_consolidation_family_classifies_by_title_shape() -> None:
    from lawvm.norway.inventory import no_no_consolidation_family

    # Amending acts, both målform, and the "oppheving av" repeal-act spelling.
    assert no_no_consolidation_family("Lov om endringer i folketrygdloven") == "amending_act"
    assert (
        no_no_consolidation_family("Lov om endringar i lov 4. desember 1992 nr. 127")
        == "amending_act"
    )
    assert (
        no_no_consolidation_family("Lov om oppheving av lov om Statens obligasjonsfond")
        == "amending_act"
    )
    assert no_no_consolidation_family("Lov om opphevelse av losloven") == "amending_act"
    # An amending act that is ALSO temporary stays an amending act: the ordering
    # inside ``no_no_consolidation_family`` is what decides this, and it decides
    # for the more specific "has no standing text of its own" story.
    assert (
        no_no_consolidation_family("Lov om midlertidige endringer i smittevernloven")
        == "amending_act"
    )
    assert (
        no_no_consolidation_family("Lov om mellombelse endringar i løyveloven")
        == "amending_act"
    )
    # Wage-board acts lapse on the Rikslønnsnemnda ruling.
    assert (
        no_no_consolidation_family("Lov om lønnsnemndbehandling av arbeidstvisten")
        == "wage_board_act"
    )
    # Temporary by title, and temporary by a built-in expiry in dateInForce only.
    assert no_no_consolidation_family("Midlertidig lov om tilpasninger") == "temporary_act"
    assert no_no_consolidation_family("Mellombels lov om tilpassingar") == "temporary_act"
    assert no_no_consolidation_family("Lov om midlertidig tilskudd") == "temporary_act"
    assert (
        no_no_consolidation_family("Lov om tilskudd", "2020-04-01, oppheves 2021-01-01")
        == "temporary_act"
    )
    assert (
        no_no_consolidation_family("Lov om tilskudd", "2020-04-01, oppheves ved kgl.res.")
        == "temporary_act"
    )
    # Everything else is a real standalone act and therefore owes an explanation.
    assert no_no_consolidation_family("Lov om Statens obligasjonsfond") == "substantive_act"
    assert (
        no_no_consolidation_family("Lov om frittståande skolar (friskolelova).")
        == "substantive_act"
    )
    assert no_no_consolidation_family("") == "substantive_act"


def test_read_no_structural_repeal_manifest_reads_the_repeal_block_only() -> None:
    """Repeal manifest and amend manifest are the same markup; the lead decides."""
    from lawvm.norway.inventory import read_no_structural_repeal_manifest

    payload = _lti_xml(
        "2013-06-21-60",
        "Lov om forbud mot diskriminering",
        body=_REPEAL_MANIFEST + _AMEND_MANIFEST,
    )

    named = read_no_structural_repeal_manifest(payload, self_id="no/lov/2013-06-21-60")

    # Only the repeal block's citation; the amend block names a law it AMENDS.
    assert named == ("no/lov/2005-06-03-33",)


def test_read_no_structural_repeal_manifest_ignores_a_self_citation() -> None:
    from lawvm.norway.inventory import read_no_structural_repeal_manifest

    payload = _lti_xml("2005-06-03-33", "Lov om noe", body=_REPEAL_MANIFEST)

    assert read_no_structural_repeal_manifest(payload, self_id="no/lov/2005-06-03-33") == ()
    # Without the suppression the same document names itself as its own repealer.
    assert read_no_structural_repeal_manifest(payload) == ("no/lov/2005-06-03-33",)


def test_read_no_structural_repeal_manifest_survives_documents_with_no_manifest() -> None:
    from lawvm.norway.inventory import read_no_structural_repeal_manifest

    assert read_no_structural_repeal_manifest(b"") == ()
    assert read_no_structural_repeal_manifest(b"<html><body>no manifest</body></html>") == ()
    assert read_no_structural_repeal_manifest(_lti_xml("2025-01-01-1", "Lov om data")) == ()


def test_build_no_inventory_censuses_originals_without_a_consolidation(tmp_path) -> None:
    """An original with no consolidation is invisible to every pre-W-45 counter."""
    # 2025-01-01-1 has BOTH lanes; the other three have an original only.
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _BASE_XML)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            (
                "lti/2025/nl-20250102-002.xml",
                _lti_xml("2025-01-02-2", "Lov om endringer i testloven"),
            ),
            (
                "lti/2025/nl-20250103-003.xml",
                _lti_xml("2025-01-03-3", "Midlertidig lov om tilpasninger"),
            ),
            (
                "lti/2025/nl-20250104-004.xml",
                _lti_xml("2025-01-04-4", "Lov om noe substansielt"),
            ),
        ],
    )

    inventory = build_no_inventory(tmp_path)
    data = inventory.to_dict()

    # The pre-W-45 universe sees one law; the census sees the other three.
    assert data["current_laws"] == 1
    assert data["stored_consolidations"] == 1
    assert data["originals_without_consolidation"] == 3
    assert data["originals_without_consolidation_amending_act"] == 1
    assert data["originals_without_consolidation_temporary_or_wage_board"] == 1
    assert data["originals_without_consolidation_substantive"] == 1
    assert data["originals_without_consolidation_substantive_without_repeal_evidence"] == 1
    assert [row["base_id"] for row in inventory.no_consolidation_rows] == [
        "no/lov/2025-01-02-2",
        "no/lov/2025-01-03-3",
        "no/lov/2025-01-04-4",
    ]


def test_build_no_no_consolidation_report_rows_and_filters(tmp_path) -> None:
    from lawvm.norway.inventory import build_no_no_consolidation_report

    inventory = NOInventory(data_dir=tmp_path)
    inventory.current_law_ids = {"no/lov/2013-06-21-60"}
    inventory.stored_consolidation_law_ids = {"no/lov/2013-06-21-60"}
    inventory.no_consolidation_rows = [
        {
            "base_id": "no/lov/2005-06-03-33",
            "title": "Lov om forbud mot diskriminering",
            "family": "substantive_act",
            "would_be_status": "fully_replayable",
            "repealed_by": ["no/lov/2013-06-21-60"],
            "amendments": 3,
        },
        {
            "base_id": "no/lov/2009-03-06-13",
            "title": "Lov om Statens obligasjonsfond",
            "family": "substantive_act",
            "would_be_status": None,
            "repealed_by": [],
            "amendments": 0,
        },
        {
            "base_id": "no/lov/2025-01-02-2",
            "title": "Lov om endringer i testloven",
            "family": "amending_act",
            "would_be_status": None,
            "repealed_by": [],
            "amendments": 1,
        },
    ]

    report = build_no_no_consolidation_report(inventory)

    assert report["stored_consolidations"] == 1
    assert report["without_consolidation_law_count"] == 3
    # 0, not the missing-base report's 1: the un-amended rows ARE the census.
    assert report["min_amendments"] == 0
    # Sorted by amendment count descending, then id -- the missing-base ordering.
    assert [row["base_id"] for row in report["laws"]] == [
        "no/lov/2005-06-03-33",
        "no/lov/2025-01-02-2",
        "no/lov/2009-03-06-13",
    ]
    assert report["counts_by_family"] == {
        "amending_act": 1,
        "temporary_act": 0,
        "wage_board_act": 0,
        "substantive_act": 2,
    }
    assert report["would_be_candidates"] == 1
    assert report["substantive_unexplained"] == 1
    assert report["substantive_unexplained_law_ids"] == ["no/lov/2009-03-06-13"]

    filtered = build_no_no_consolidation_report(inventory, family="substantive_act")
    assert [row["base_id"] for row in filtered["laws"]] == [
        "no/lov/2005-06-03-33",
        "no/lov/2009-03-06-13",
    ]
    assert filtered["family_filter"] == "substantive_act"

    by_id = build_no_no_consolidation_report(inventory, base_id="no/lov/2009-03-06-13")
    assert by_id["without_consolidation_law_count"] == 1
    assert by_id["base_id_filter"] == "no/lov/2009-03-06-13"

    amended = build_no_no_consolidation_report(inventory, min_amendments=1)
    assert [row["base_id"] for row in amended["laws"]] == [
        "no/lov/2005-06-03-33",
        "no/lov/2025-01-02-2",
    ]


# --- corpus pins -----------------------------------------------------------
#
# These three assert against the ingested corpus, not a fixture. They exist
# because the census's whole claim is a claim about THIS corpus: "2,642 laws
# have a replayable original and no stored consolidation, and every one of them
# is explained". A fixture cannot carry that claim.


def _no_corpus_dir():
    """The ingested Norway corpus, or None when it is not installed."""
    from lawvm.norway.sources import iter_no_original_lti_artifacts, resolve_no_source_path

    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        return None
    for _artifact in iter_no_original_lti_artifacts(data_dir):
        return data_dir
    return None


def test_corpus_no_consolidation_census_reproduces_the_w44_measurement() -> None:
    """W-44's answer, recomputed at runtime rather than replayed from its JSON.

    The four families and their sizes are the whole finding: of 2,642 laws with
    a replayable original and no stored consolidation, 2,514 are amending acts
    (no standing text of their own — Lovdata consolidates ~4% of them), 40 are
    temporaries with a built-in expiry, 25 are wage-board acts that lapse on the
    Rikslønnsnemnda ruling, and only 63 are substantive acts that owe a repeal
    explanation. Zero demonstrated acquisition gaps.

    The precision control on the structural repeal manifest is pinned in the
    same test because the substantive residue below is only meaningful if the
    manifest read is precise: 332 laws corpus-wide are named in some act's
    repeal manifest, and only 24 of them still have a stored consolidation —
    each of those 24 a staged or not-yet-commenced repeal. A manifest read that
    started over-firing would push that 24 up and the residue down, so the two
    numbers move together and are pinned together.

    Index-free on purpose: nothing asserted here depends on the amendment index,
    only on titles and manifests, so the pin costs a corpus walk and not a
    45-second index build. The index-derived half is pinned separately below.

    2,642 -> 2,647 (amending 2,514 -> 2,519) and stored 763 -> 758 at W-86,
    the 2026-08-14 capture re-pin — and the two movements are ONE event, not
    two. The lovtid lanes are digest-identical across the re-capture (zero
    acts entered), so no law was minted: FIVE endringslover left the
    ``gjeldende-lover`` snapshot and thereby ENTERED this census, which counts
    "original present, consolidation absent". The five, each adjudicated at
    W-86 (``.tmp/w86/``): ``no/lov/2026-01-23-1`` (helsepersonelloven mv.,
    ikr. 2026-07-01), ``no/lov/2026-02-13-6`` (opplæringslova, ikr.
    2026-08-01), ``no/lov/2026-03-06-7`` (plan- og bygningsloven, ikr.
    2026-07-01), ``no/lov/2026-04-10-14`` (skipsarbeidsloven/NIS-loven, ikr.
    2026-07-01), ``no/lov/2026-05-07-17`` (domstolloven mv., ikr. 2026-07-01).
    Not repeals, not expiries: all five commenced in the window and their
    changes are incorporated into all 18 host consolidations in THIS capture
    ("Endret/Endra ved lov …" footnotes, ``.tmp/w86/incorporation_receipts.json``)
    — Lovdata drops a fully-incorporated endringslov's own consolidation, so
    the five are exactly the kind of snapshot-lifecycle churn this census
    expects of the amending family. Every one had a consolidation while its
    commencement was pending (Wayback NL captures / LTI self-links pinned in
    the W-86 artifacts), all five were non-operative consolidations (the
    "bare change instruction" class: stored - operative went 118 -> 113 while
    operative held at 645), and the substantive/temporary/wage-board families
    and the manifest cross (332 / 24) are unmoved — no in-force law lost its
    text.
    """
    from lawvm.norway.inventory import (
        build_no_no_consolidation_rows,
        build_no_structural_repeal_manifest,
        load_no_stored_consolidation_law_ids,
        summarize_no_no_consolidation_rows,
    )

    data_dir = _no_corpus_dir()
    if data_dir is None:
        pytest.skip("local Norway corpus is not installed")

    stored = load_no_stored_consolidation_law_ids(data_dir)
    rows = build_no_no_consolidation_rows(
        data_dir,
        stored_consolidation_law_ids=stored,
        base_to_statuses={},
        base_to_sources={},
    )
    summary = summarize_no_no_consolidation_rows(rows)

    assert summary["total"] == 2647
    assert summary["by_family"] == {
        "amending_act": 2519,
        "temporary_act": 40,
        "wage_board_act": 25,
        "substantive_act": 63,
    }
    # "Stored consolidation" is artifact presence (758 since W-86; 763 on the
    # 2026-07-10 capture), NOT ``load_no_current_law_ids``'s narrower
    # operative-content test (645, unmoved by the re-capture). The difference
    # (118 -> 113 at W-86) is amending acts consolidated down to bare change
    # instructions; 108 of them also have an original (110 before W-86), and
    # counting those as "no stored consolidation" would move this census to
    # 2,755 / 2,627 amending. See ``load_no_stored_consolidation_law_ids``.
    assert len(stored) == 758

    manifest = build_no_structural_repeal_manifest(data_dir)
    assert len(manifest) == 332
    assert len(set(manifest) & stored) == 24


def test_corpus_no_consolidation_substantive_residue_is_the_adjudicated_thirteen() -> None:
    """TRIPWIRE. Fires if a future corpus really does lose an in-force law.

    Of the 63 substantive acts with no stored consolidation, 50 are named in
    another act's structural repeal manifest — machine-readable proof they were
    repealed. The remaining 13 have no manifest evidence and were adjudicated
    ONE BY ONE at W-44 (``.tmp/w44/adjudicate_no_repeal_evidence.json``); each is
    spent, absorbed into a successor, or never commenced. They are pinned by ID
    and not merely by count, because the count alone would stay at 13 if one of
    these thirteen gained a consolidation while some genuinely in-force law
    silently lost one — which is the exact failure this guards.

    What a failure means, and what it does NOT mean:

    * a NEW id in the set is the alarm — a substantive act that is in nobody's
      repeal manifest and has no current text is either a real acquisition gap
      or a Lovdata regression, and it must be adjudicated before this pin moves;
    * an id LEAVING the set is benign and expected — it means the corpus gained
      either a consolidation for that law or an act naming it in a repeal
      manifest. Drop it here with a one-line note on which.

    Never re-derive this list from the corpus to make the test pass. The list is
    the human adjudication; the corpus is what it is being checked against.
    """
    from lawvm.norway.inventory import (
        build_no_no_consolidation_report,
        build_no_no_consolidation_rows,
        load_no_stored_consolidation_law_ids,
        summarize_no_no_consolidation_rows,
    )

    data_dir = _no_corpus_dir()
    if data_dir is None:
        pytest.skip("local Norway corpus is not installed")

    rows = build_no_no_consolidation_rows(
        data_dir,
        stored_consolidation_law_ids=load_no_stored_consolidation_law_ids(data_dir),
        base_to_statuses={},
        base_to_sources={},
    )
    summary = summarize_no_no_consolidation_rows(rows)

    assert summary["substantive_unexplained"] == 13
    substantive = [row for row in rows if row["family"] == "substantive_act"]
    assert len(substantive) == 63
    assert sum(1 for row in substantive if row["repealed_by"]) == 50
    assert sorted(row["base_id"] for row in substantive if not row["repealed_by"]) == [
        # Stiftelsen wound up by the act itself; nothing survives to consolidate.
        "no/lov/2002-01-11-1",
        # Mehamn commission of inquiry: discharged when it reported.
        "no/lov/2003-04-11-20",
        # Corrections act ("retting av feil m.m. i lovverket") -- pure errata,
        # absorbed into the laws it corrected.
        "no/lov/2003-06-20-45",
        # Friskolelova: superseded in substance by privatskolelova, whose
        # renaming act does not spell out a structural repeal manifest.
        "no/lov/2003-07-04-85",
        # One-off transfer of asset positions on a change of agency
        # responsibility; spent on execution.
        "no/lov/2003-09-12-94",
        # Statskonsult AS employee preference/wait-pay: spent transitional.
        "no/lov/2003-12-19-118",
        # Statens embets- og tjenestemenn: absorbed by statsansatteloven (2017).
        "no/lov/2005-06-17-103",
        # Addendum to eigedomsskattelova; folded into the host act.
        "no/lov/2008-12-12-103",
        # Statens obligasjonsfond: 2009 crisis vehicle, wound up.
        "no/lov/2009-03-06-13",
        # Second corrections act; same shape as 2003-06-20-45.
        "no/lov/2014-05-09-16",
        # Transitional rule to a 2012 amending act's del V; spent.
        "no/lov/2014-12-19-87",
        # Covid: procedural exemption in konkurranseloven, expired.
        "no/lov/2020-04-17-30",
        # Covid: annual-accounts deadline postponement, expired.
        "no/lov/2021-06-18-102",
    ]

    # The report surfaces the same thirteen, so the CLI receipt and the tripwire
    # cannot drift apart.
    inventory = NOInventory(data_dir=data_dir)
    inventory.no_consolidation_rows = rows
    report = build_no_no_consolidation_report(inventory, family="substantive_act")
    assert report["substantive_unexplained_law_ids"] == sorted(
        row["base_id"] for row in substantive if not row["repealed_by"]
    )


def test_corpus_no_consolidation_inventory_counters_and_would_be_ceiling() -> None:
    """The index-derived half: the five ``to_dict`` counters and the ceiling.

    ``would_be_status`` is the status the inventory WOULD assign each of these
    laws if a consolidation existed, computed off the same per-binding statuses
    ``build_no_inventory`` feeds ``no_base_replay_status_from_statuses``. It is
    the counterfactual ceiling on the scan: 57 of the 2,642 would enter as
    ``fully_replayable`` candidates (65 -> 122), 33 as ``blocked_contingent``,
    and 2,552 have no index binding at all -- ``None``, not ``no_amendments``,
    because "the index has no opinion" is not "the index says zero".

    This pin and the candidate pin in ``test_norway_index.py`` are the two
    halves of one statement about scan coverage, and they move together.

    55 -> 57 / 35 -> 33 at W-47 (2026-08-08). The multi-part commencement route
    resolves bindings, so it moves the counterfactual ceiling exactly as it
    moves the scan: two of these laws stop being blocked by a contingent
    amender. The movement is a pure TRANSFER between the two buckets -- their
    sum is unmoved at 90, and ``None`` is unmoved at 2,552, because no law
    gained or lost an index binding. Same +2 as
    ``test_norway_verify.py``'s ``would_be_candidates``, which is the same
    number read off the partition report.

    57 -> 61 / 33 -> 29 at W-53 (2026-08-09). The widened whole-act route, and
    the identical mechanism at a larger scale: four more of these laws stop
    being blocked by a contingent amender. Again a pure TRANSFER — the sum is
    unmoved at 90 and ``None`` is unmoved at 2,552 — which is the check that an
    ACT-level commencement route still writes only dates and never bindings.
    Same +4 as ``test_norway_verify.py``'s ``would_be_candidates``.

    61 -> 60 / 29 -> 30 at W-61 (2026-08-10), and this one runs BACKWARDS: the
    first time a law has left the counterfactual ceiling. Still a pure TRANSFER
    — the sum is unmoved at 90 and ``None`` is unmoved at 2,552 — but read the
    mechanism, because it is the opposite of the three above. W-47 and W-53 are
    commencement routes: they write DATES and never bindings, so a law moves
    ``blocked_contingent -> fully_replayable`` when its existing amenders stop
    being undated. W-61 is a LOWERING widening: it writes BINDINGS, and
    ``no/lov/2009-06-19-101`` (mineralloven) moves the other way because it
    gains one — ``no/lovtid/2013-01-11-3``, whose § 66 and § 67 ledd repeals now
    lower and whose own commencement is "Kongen bestemmer" with no instrument
    date. Nothing regressed: the amender was always there and always undated,
    and the ceiling could not see it only because its two leads did not lower.
    Same -1 as ``test_norway_verify.py``'s ``would_be_candidates``.

    763 -> 758 stored / 2,642 -> 2,647 census / ``None`` 2,552 -> 2,557 at
    W-86 (the 2026-08-14 capture re-pin), and for the first time in this
    test's history the movement is CORPUS drift, not an index route: five
    fully-commenced endringslover left the ``gjeldende-lover`` snapshot
    (named and adjudicated in the census test above) and entered the census.
    All five land in ``None`` — nothing in the index binds them, because
    nothing amends an endringslov that has just been incorporated — so
    ``fully_replayable`` (60) and ``blocked_contingent`` (30) are unmoved,
    and with them the counterfactual ceiling and ``would_be_candidates``.
    The 90-law sum this docstring has tracked through W-47/W-53/W-61 is
    untouched; only the index-has-no-opinion bucket grows by exactly the
    five entrants.
    """
    data_dir = _no_corpus_dir()
    if data_dir is None:
        pytest.skip("local Norway corpus is not installed")

    inventory = build_no_inventory(data_dir)
    data = inventory.to_dict()

    assert data["stored_consolidations"] == 758
    assert data["originals_without_consolidation"] == 2647
    assert data["originals_without_consolidation_amending_act"] == 2519
    assert data["originals_without_consolidation_temporary_or_wage_board"] == 65
    assert data["originals_without_consolidation_substantive"] == 63
    assert data["originals_without_consolidation_substantive_without_repeal_evidence"] == 13

    would_be = Counter(
        str(row["would_be_status"]) for row in inventory.no_consolidation_rows
    )
    # 60 -> 64 / 30 -> 26 at W-100 (2026-09-05): four laws leave
    # ``blocked_contingent`` because the act that held them there is now dated —
    # through the section-scoped lane's per-binding dates or the title-cited
    # citation form. The 90-law sum and ``None`` (2,557) are unmoved.
    assert would_be == Counter(
        {"None": 2557, "fully_replayable": 64, "blocked_contingent": 26}
    )
