from __future__ import annotations

import io
import tarfile
from typing import Any, cast

import pytest

from lawvm.norway.commencement import apply_no_commencement_overrides
from lawvm.norway.commencement_instruments import (
    NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
    NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
    NO_COMMENCEMENT_EXECUTION_REFUSED,
)
from lawvm.norway.index import (
    NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR,
    NO_AMENDMENT_INDEX_STAGED_COMMENCEMENT_COLLAPSED,
    NOAmendmentIndex,
    build_no_amendment_index,
    load_no_amendment_index,
    save_no_amendment_index,
)
from lawvm.norway.sources import (
    NO_UNRESOLVED_EFFECTIVE_STATUSES,
    NOCommencementShape,
    NOLocatedArtifact,
    declared_change_targets_from_amendment,
    load_available_lti_law_ids,
    load_no_current_law_ids,
    parse_header_value,
    resolve_no_source_path,
)

# Lovdata's declared ``changesToDocuments`` list for no/lovtid/2022-12-20-115, in
# document order, and the six targets the index actually binds from extracted ops.
_LOVTID_2022_12_20_115_DECLARED = (
    "lov/1950-12-15-7",
    "lov/1967-02-10",
    "lov/1979-05-18-18",
    "lov/1980-06-13-35",
    "lov/1989-06-16-65",
    "lov/1992-12-04-126",
    "lov/1999-07-02-62",
    "lov/1999-07-02-64",
    "lov/2006-05-19-16",
    "lov/2016-05-27-14",
    "lov/2017-06-16-50",
    "lov/2017-06-16-67",
    "lov/2020-06-19-80",
    "lov/2021-05-21-42",
)
_LOVTID_2022_12_20_115_BOUND = (
    "lov/1950-12-15-7",
    "lov/1979-05-18-18",
    "lov/1992-12-04-126",
    "lov/2017-06-16-67",
    "lov/2020-06-19-80",
    "lov/2021-05-21-42",
)


def _amendment_xml(date_in_force: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">{date_in_force}</dd>
    <article class="document-change" data-document="lov/2025-01-01-1">
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


def _non_operational_amendment_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-02-10</dd>
    <p>No document-change payload is present.</p>
  </body>
</html>
"""


def _unresolved_base_amendment_xml() -> bytes:
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-02-10</dd>
    <article class="document-change" data-document="not-a-lovdata-ref">
      <article class="change" data-change-part="lov/2025-01-01-1/§1">
        <article class="legalP">§ 1 skal lyde:</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _unresolved_structured_target_amendment_xml() -> bytes:
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-02-10</dd>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change" data-change-part="lov/2022-05-12-28/ukjent">
        <article class="legalP">§ 12 skal lyde:</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _declared_targets_amendment_xml(
    declared: tuple[str, ...],
    bound: tuple[str, ...],
) -> bytes:
    items = "".join(f"<li>{ref}</li>" for ref in declared)
    changes = "\n".join(
        f"""<article class="document-change" data-document="{ref}">
      <article class="change" data-change-part="{ref}/§1">
        <article class="futureLegalArticle" data-name="§1">
          <span class="futureLegalArticleHeader">
            <span class="legalArticleValue">§ 1</span>.
            <span class="legalArticleTitle">Nytt krav</span>
          </span>
          <article class="legalP">Oppdatert paragraftekst.</article>
        </article>
      </article>
    </article>"""
        for ref in bound
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2023-01-01</dd>
    <dd class="changesToDocuments"><ul>{items}</ul></dd>
    {changes}
  </body>
</html>
""".encode("utf-8")


def _whole_act_instrument_xml(law_ref: str, date_in_force: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="title">Ikraftsetting av {law_ref}</dd>
    <dd class="basedOn"><a href="{law_ref}">endringsloven</a></dd>
    <dd class="dateInForce">{date_in_force}</dd>
    <main class="documentBody">
      <article class="legalP">Loven trer i kraft {date_in_force}.</article>
    </main>
  </body>
</html>
""".encode("utf-8")


def _partial_instrument_xml(law_ref: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="title">Delt ikraftsetting av {law_ref}</dd>
    <dd class="basedOn"><a href="{law_ref}">endringsloven</a></dd>
    <dd class="dateInForce">2025-04-01</dd>
    <main class="documentBody">
      <article class="legalP">Loven § 2 trer i kraft 1. april 2025.</article>
    </main>
  </body>
</html>
""".encode("utf-8")


def _write_archive(archive_path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(archive_path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def test_build_no_amendment_index_captures_member_and_status(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10")),
            ("lti/2025/nl-20250303-006.xml", _amendment_xml("Kongen bestemmer")),
        ],
    )

    index = build_no_amendment_index(tmp_path)

    assert len(index.entries) == 2
    first = index.entries[0]
    assert first.archive == "lovtidend-avd1-2025.tar.bz2"
    assert first.member_name == "lti/2025/nl-20250202-005.xml"
    assert first.effective_status == "dated"
    assert first.effective_date == "2025-02-10"
    assert first.base_ids == ("no/lov/2025-01-01-1",)


def test_build_no_amendment_index_records_identical_duplicate_logical_locator(tmp_path) -> None:
    payload = _amendment_xml("2025-02-10")
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", payload)],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025-2026.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", payload)],
    )

    index = build_no_amendment_index(tmp_path)

    assert len(index.entries) == 1
    assert index.entries[0].archive == "lovtidend-avd1-2025-2026.tar.bz2"
    assert [diagnostic["rule_id"] for diagnostic in index.diagnostics] == [
        NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR
    ]
    diagnostic = index.diagnostics[0]
    assert diagnostic["phase"] == "acquisition"
    assert diagnostic["family"] == "source_pathology"
    assert diagnostic["source_id"] == "no/lovtid/2025-02-02-5"
    assert diagnostic["locator"] == "no://lovtid/2025-02-02-5/amendment.xml"
    assert diagnostic["duplicate_count"] == 2
    assert diagnostic["identical_payloads"] is True
    assert diagnostic["blocking"] is True
    assert diagnostic["strict_disposition"] == "block"
    assert diagnostic["quirks_disposition"] == "select_first_identical"
    assert diagnostic["selected_archive"] == "lovtidend-avd1-2025-2026.tar.bz2"
    assert diagnostic["selected_source_locator"] == (
        "lovtidend-avd1-2025-2026.tar.bz2:lti/2025/nl-20250202-005.xml"
    )
    assert diagnostic["source_lane_selection"] == {
        "rule_id": NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR,
        "family": "source_lane_selection",
        "phase": "acquisition",
        "reason": (
            "Norway amendment indexing selected one byte-identical duplicate "
            "source witness deterministically."
        ),
        "blocking": True,
        "strict_disposition": "block",
        "quirks_disposition": "select_first_identical",
        "selected_source_lane": "norway_lovtidend_archive_member",
        "selected_source_locator": (
            "lovtidend-avd1-2025-2026.tar.bz2:lti/2025/nl-20250202-005.xml"
        ),
        "source_lane_attempts": (
            {
                "lane": "norway_lovtidend_archive_member",
                "lane_attempt_status": "selected_identical_duplicate",
                "locator": "lovtidend-avd1-2025-2026.tar.bz2:lti/2025/nl-20250202-005.xml",
                "logical_id": "no/lovtid/2025-02-02-5",
                "logical_locator": "no://lovtid/2025-02-02-5/amendment.xml",
                "payload_digest": diagnostic["payload_digests"][0],
            },
            {
                "lane": "norway_lovtidend_archive_member",
                "lane_attempt_status": "duplicate_identical_not_selected",
                "locator": "lovtidend-avd1-2025.tar.bz2:lti/2025/nl-20250202-005.xml",
                "logical_id": "no/lovtid/2025-02-02-5",
                "logical_locator": "no://lovtid/2025-02-02-5/amendment.xml",
                "payload_digest": diagnostic["payload_digests"][0],
            },
        ),
        "logical_id": "no/lovtid/2025-02-02-5",
        "logical_locator": "no://lovtid/2025-02-02-5/amendment.xml",
        "identical_payloads": True,
    }
    assert len(diagnostic["payload_digests"]) == 1
    assert [item["archive"] for item in diagnostic["candidates"]] == [
        "lovtidend-avd1-2025-2026.tar.bz2",
        "lovtidend-avd1-2025.tar.bz2",
    ]


def test_build_no_amendment_index_blocks_conflicting_duplicate_logical_locator(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10"))],
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2025-2026.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-03-15"))],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert [diagnostic["rule_id"] for diagnostic in index.diagnostics] == [
        NO_ACQUISITION_DUPLICATE_LOGICAL_LOCATOR
    ]
    diagnostic = index.diagnostics[0]
    assert diagnostic["source_id"] == "no/lovtid/2025-02-02-5"
    assert diagnostic["identical_payloads"] is False
    assert diagnostic["quirks_disposition"] == "block"
    assert diagnostic["selected_archive"] == ""
    source_lane_selection = diagnostic["source_lane_selection"]
    assert source_lane_selection["selected_source_lane"] == "no_source_lane_selected_conflicting_duplicates"
    assert source_lane_selection["selected_source_locator"] == ""
    assert source_lane_selection["quirks_disposition"] == "block"
    assert {
        attempt["lane_attempt_status"]
        for attempt in source_lane_selection["source_lane_attempts"]
    } == {"blocked_conflicting_duplicate"}
    assert len(diagnostic["payload_digests"]) == 2


def test_build_no_amendment_index_records_artifacts_without_change_ops(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _non_operational_amendment_xml())],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert index.diagnostics == [
        {
            "rule_id": "no_amendment_index_no_change_ops",
            "family": "source_pathology",
            "phase": "extraction",
            "reason": "Norway amendment artifact did not yield document-change operations",
            "source_id": "no/lovtid/2025-02-02-5",
            "locator": "no://lovtid/2025-02-02-5/amendment.xml",
            "archive": "lovtidend-avd1-2025.tar.bz2",
            "member_name": "lti/2025/nl-20250202-005.xml",
            "blocking": True,
            "strict_disposition": "block",
            "quirks_disposition": "record",
        }
    ]
    assert index.to_dict()["diagnostics"] == index.diagnostics


def test_build_no_amendment_index_forwards_parser_adjudications(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _unresolved_base_amendment_xml())],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert [diagnostic["rule_id"] for diagnostic in index.diagnostics] == [
        "no_parse_document_change_base_unresolved",
        "no_amendment_index_no_change_ops",
    ]
    parser_diagnostic = index.diagnostics[0]
    assert parser_diagnostic["kind"] == "no_parse_document_change_base_unresolved"
    assert parser_diagnostic["family"] == "source_pathology"
    assert parser_diagnostic["phase"] == "parse"
    assert parser_diagnostic["source_id"] == "no/lovtid/2025-02-02-5"
    assert parser_diagnostic["locator"] == "no://lovtid/2025-02-02-5/amendment.xml"
    assert parser_diagnostic["archive"] == "lovtidend-avd1-2025.tar.bz2"
    assert parser_diagnostic["member_name"] == "lti/2025/nl-20250202-005.xml"
    assert parser_diagnostic["blocking"] is True
    assert parser_diagnostic["strict_disposition"] == "block"
    assert parser_diagnostic["quirks_disposition"] == "record"
    assert parser_diagnostic["detail"]["source_doc"] == "not-a-lovdata-ref"
    assert parser_diagnostic["detail"]["reason"] == "unmappable_data_document"


def test_build_no_amendment_index_forwards_unresolved_structured_target_adjudication(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _unresolved_structured_target_amendment_xml())],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert [diagnostic["rule_id"] for diagnostic in index.diagnostics] == [
        "no_parse_unresolved_structured_target_skipped",
        "no_amendment_index_no_change_ops",
    ]
    parser_diagnostic = index.diagnostics[0]
    assert parser_diagnostic["kind"] == "no_parse_unresolved_structured_target_skipped"
    assert parser_diagnostic["family"] == "target_resolution_recovery"
    assert parser_diagnostic["phase"] == "parse"
    assert parser_diagnostic["source_id"] == "no/lovtid/2025-02-02-5"
    assert parser_diagnostic["blocking"] is True
    assert parser_diagnostic["strict_disposition"] == "block"
    assert parser_diagnostic["quirks_disposition"] == "record"
    assert parser_diagnostic["detail"]["base_id"] == "no/lov/2022-05-12-28"
    assert parser_diagnostic["detail"]["raw_target"] == "lov/2022-05-12-28/ukjent"


def test_build_no_amendment_index_records_unmapped_xml_members(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/unexpected-name.xml", _amendment_xml("2025-02-10"))],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert index.diagnostics == [
        {
            "rule_id": "no_amendment_index_unmapped_lovtidend_xml_member",
            "family": "source_pathology",
            "phase": "acquisition",
            "reason": "Norway Lovtidend XML member filename could not be mapped to a law or amendment source id",
            "source_id": "",
            "locator": "",
            "archive": "lovtidend-avd1-2025.tar.bz2",
            "member_name": "lti/2025/unexpected-name.xml",
            "blocking": True,
            "strict_disposition": "block",
            "quirks_disposition": "record",
        }
    ]


def test_build_no_amendment_index_records_unrecognized_amendment_lane(tmp_path, monkeypatch) -> None:
    artifact = NOLocatedArtifact(
        locator="no://unexpected/2025-02-02-5/amendment.xml",
        logical_id="no/lovtid/2025-02-02-5",
        source_name="synthetic.farchive",
        member_name="unexpected-member.xml",
        payload=_amendment_xml("2025-02-10"),
    )

    monkeypatch.setattr(
        "lawvm.norway.index.iter_no_amendment_artifacts",
        lambda _data_dir: iter((artifact,)),
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert index.diagnostics == [
        {
            "rule_id": "no_amendment_index_unrecognized_amendment_locator",
            "family": "source_pathology",
            "phase": "acquisition",
            "reason": "Norway amendment index skipped artifact whose member name and locator did not identify an amendment source lane",
            "source_id": "no/lovtid/2025-02-02-5",
            "locator": "no://unexpected/2025-02-02-5/amendment.xml",
            "archive": "synthetic.farchive",
            "member_name": "unexpected-member.xml",
            "blocking": True,
            "strict_disposition": "block",
            "quirks_disposition": "record",
        }
    ]


def test_save_and_load_no_amendment_index_round_trips(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10"))],
    )
    index = build_no_amendment_index(tmp_path)
    index_path = tmp_path / "no_index.json"

    save_no_amendment_index(index, index_path)
    loaded = load_no_amendment_index(index_path)

    assert loaded.to_dict() == index.to_dict()


def test_declared_change_targets_reads_list_items_not_the_string_flattening() -> None:
    payload = _declared_targets_amendment_xml(("lov/2013-01-11-3", "lov/2022-03-11-9"), ())

    declared = declared_change_targets_from_amendment(payload)

    assert declared.law_ids == ("no/lov/2013-01-11-3", "no/lov/2022-03-11-9")
    # The reason the reader may not go through parse_header_value: its XPath
    # string() flattening concatenates the declared ids into one token.
    assert parse_header_value(payload, "changesToDocuments") == (
        "lov/2013-01-11-3lov/2022-03-11-9"
    )


def test_declared_change_targets_marks_block_present_like_the_2942_acts_that_carry_one() -> None:
    # 2,942 of the 3,089 amendment artifacts carry a changesToDocuments block and
    # 2,941 of those hold at least one lov-form target.
    declared = declared_change_targets_from_amendment(
        _declared_targets_amendment_xml(_LOVTID_2022_12_20_115_DECLARED, ())
    )

    assert declared.block_present is True
    assert len(declared.law_ids) == 14
    assert declared.unnumbered_law_ids == ("no/lov/1967-02-10",)


def test_declared_change_targets_marks_block_absent_like_the_147_acts_without_one() -> None:
    declared = declared_change_targets_from_amendment(_non_operational_amendment_xml())

    assert declared.block_present is False
    assert declared.law_ids == ()
    assert declared.unnumbered_law_ids == ()


def test_declared_change_targets_drops_forskrift_and_null_like_no_lovtid_2021_06_18_115() -> None:
    declared = declared_change_targets_from_amendment(
        _declared_targets_amendment_xml(("forskrift/1952-04-21-4287", "null"), ())
    )

    assert declared.block_present is True
    assert declared.law_ids == ()


def test_build_no_amendment_index_adjudicates_declared_targets_no_op_bound(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2022.tar.bz2",
        [
            (
                "lti/2022/nl-20221220-115.xml",
                _declared_targets_amendment_xml(
                    _LOVTID_2022_12_20_115_DECLARED,
                    _LOVTID_2022_12_20_115_BOUND,
                ),
            )
        ],
    )

    index = build_no_amendment_index(tmp_path)

    entry = index.entries[0]
    assert entry.source_id == "no/lovtid/2022-12-20-115"
    assert len(entry.declared_target_ids) == 14
    assert entry.base_ids == (
        "no/lov/1950-12-15-7",
        "no/lov/1979-05-18-18",
        "no/lov/1992-12-04-126",
        "no/lov/2017-06-16-67",
        "no/lov/2020-06-19-80",
        "no/lov/2021-05-21-42",
    )
    assert index.diagnostics == [
        {
            "rule_id": "no_amendment_index_declared_target_unbound",
            "family": "source_pathology",
            "phase": "acquisition",
            "reason": "Norway amendment act declared amendment targets that no extracted operation bound",
            "source_id": "no/lovtid/2022-12-20-115",
            "locator": "no://lovtid/2022-12-20-115/amendment.xml",
            "archive": "lovtidend-avd1-2022.tar.bz2",
            "member_name": "lti/2022/nl-20221220-115.xml",
            "declared_target_count": 14,
            "bound_base_id_count": 6,
            "unbound_target_ids": [
                "no/lov/1967-02-10",
                "no/lov/1980-06-13-35",
                "no/lov/1989-06-16-65",
                "no/lov/1999-07-02-62",
                "no/lov/1999-07-02-64",
                "no/lov/2006-05-19-16",
                "no/lov/2016-05-27-14",
                "no/lov/2017-06-16-50",
            ],
            "unnumbered_unbound_target_ids": ["no/lov/1967-02-10"],
            "blocking": True,
            "strict_disposition": "block",
            "quirks_disposition": "record",
        }
    ]


def test_build_no_amendment_index_emits_no_declared_target_adjudication_when_covered(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            (
                "lti/2025/nl-20250202-005.xml",
                _declared_targets_amendment_xml(("lov/2025-01-01-1",), ("lov/2025-01-01-1",)),
            )
        ],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries[0].declared_target_ids == ("no/lov/2025-01-01-1",)
    assert index.entries[0].base_ids == ("no/lov/2025-01-01-1",)
    assert index.diagnostics == []


def test_build_no_amendment_index_declares_no_target_gap_without_a_lov_form_target(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2021.tar.bz2",
        [
            (
                "lti/2021/nl-20210618-115.xml",
                _declared_targets_amendment_xml(("forskrift/1952-04-21-4287", "null"), ()),
            )
        ],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries == []
    assert [diagnostic["rule_id"] for diagnostic in index.diagnostics] == [
        "no_amendment_index_no_change_ops"
    ]


def test_no_amendment_index_round_trips_declared_targets_and_adjudications(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2022.tar.bz2",
        [
            (
                "lti/2022/nl-20221220-115.xml",
                _declared_targets_amendment_xml(
                    _LOVTID_2022_12_20_115_DECLARED,
                    _LOVTID_2022_12_20_115_BOUND,
                ),
            )
        ],
    )
    index = build_no_amendment_index(tmp_path)
    index_path = tmp_path / "no_index.json"

    save_no_amendment_index(index, index_path)
    loaded = load_no_amendment_index(index_path)

    assert loaded.entries[0].declared_target_ids == index.entries[0].declared_target_ids
    assert loaded.diagnostics == index.diagnostics
    assert loaded.to_dict() == index.to_dict()


def test_no_amendment_index_from_dict_loads_json_written_before_declared_targets(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10"))],
    )
    data = build_no_amendment_index(tmp_path).to_dict()
    for entry in cast(list[dict[str, Any]], data["entries"]):
        entry.pop("declared_target_ids")

    loaded = NOAmendmentIndex.from_dict(data)

    assert loaded.entries[0].base_ids == ("no/lov/2025-01-01-1",)
    assert loaded.entries[0].declared_target_ids == ()


def test_build_no_amendment_index_authorizes_a_whole_act_commencement_instrument(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("Kongen bestemmer")),
            (
                "lti/2025/sf-20250301-0100.xml",
                _whole_act_instrument_xml("lov/2025-02-02-5", "2025-04-01"),
            ),
        ],
    )

    index = build_no_amendment_index(tmp_path)

    entry = index.entries[0]
    assert entry.source_id == "no/lovtid/2025-02-02-5"
    assert entry.effective_status == "instrument_authorized"
    assert entry.effective_date == "2025-04-01"
    # The act's own header stays untouched evidence of why it was unresolved, and
    # binding is unchanged: this re-dates an act, it binds nothing.
    assert entry.raw_date_in_force == "Kongen bestemmer"
    assert entry.base_ids == ("no/lov/2025-01-01-1",)
    assert entry.n_ops == 1
    assert [item.replay_authorized for item in index.commencement_instruments] == [True]
    receipts = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    ]
    assert len(receipts) == 1
    assert receipts[0]["source_id"] == "no/lovtid/2025-02-02-5"
    assert receipts[0]["instrument_source_ids"] == ["no/forskrift/2025-03-01-100"]
    assert receipts[0]["effective_date"] == "2025-04-01"
    assert receipts[0]["blocking"] is False
    assert not [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"]
        in {NO_COMMENCEMENT_EXECUTION_REFUSED, NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT}
    ]

    reloaded = NOAmendmentIndex.from_dict(index.to_dict())
    assert reloaded.entries[0].effective_status == "instrument_authorized"
    assert reloaded.entries[0].effective_date == "2025-04-01"
    assert reloaded.commencement_instruments[0].replay_authorized is True


def test_build_no_amendment_index_refuses_a_partial_instrument_and_keeps_dated_acts(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("Kongen bestemmer")),
            ("lti/2025/nl-20250303-006.xml", _amendment_xml("2025-03-15")),
            ("lti/2025/sf-20250301-0100.xml", _partial_instrument_xml("lov/2025-02-02-5")),
            (
                "lti/2025/sf-20250401-0200.xml",
                _whole_act_instrument_xml("lov/2025-03-03-6", "2025-09-01"),
            ),
        ],
    )

    index = build_no_amendment_index(tmp_path)

    assert [
        (entry.source_id, entry.effective_status, entry.effective_date)
        for entry in index.entries
    ] == [
        ("no/lovtid/2025-02-02-5", "contingent", None),
        ("no/lovtid/2025-03-03-6", "dated", "2025-03-15"),
    ]
    assert all(item.replay_authorized is False for item in index.commencement_instruments)
    assert not [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    ]
    refusals = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_REFUSED
    ]
    assert len(refusals) == 1
    assert refusals[0]["source_id"] == "no/lovtid/2025-02-02-5"
    assert refusals[0]["instrument_source_id"] == "no/forskrift/2025-03-01-100"
    assert refusals[0]["failed_conjuncts"] == ["parse_status_candidate", "whole_act_scope"]


def test_commencement_override_outranks_an_instrument_authorization(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("Kongen bestemmer")),
            (
                "lti/2025/sf-20250301-0100.xml",
                _whole_act_instrument_xml("lov/2025-02-02-5", "2025-04-01"),
            ),
        ],
    )
    index = build_no_amendment_index(tmp_path)

    overridden = apply_no_commencement_overrides(
        index,
        {"no/lovtid/2025-02-02-5": {"effective_date": "2025-05-01", "note": "kgl.res."}},
    )

    assert overridden.entries[0].effective_status == "override"
    assert overridden.entries[0].effective_date == "2025-05-01"


def test_build_no_amendment_index_labels_and_receipts_a_staged_delegated_act(tmp_path) -> None:
    """A dateInForce carrying a date AND a delegated tail is labelled, not demoted."""
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            (
                "lti/2025/nl-20250202-005.xml",
                _amendment_xml("2025-07-01, 2025-02-10, Kongen bestemmer"),
            ),
            ("lti/2025/nl-20250303-006.xml", _amendment_xml("2025-03-15")),
        ],
    )

    index = build_no_amendment_index(tmp_path)

    staged, plain = index.entries
    # The staged act keeps a resolved date at min(dates) — the collapse is
    # unchanged — and gains only the label saying the field staged commencement.
    assert (staged.effective_status, staged.effective_date) == ("dated", "2025-02-10")
    assert staged.commencement_shape == NOCommencementShape.STAGED_DELEGATED
    assert (plain.effective_status, plain.effective_date) == ("dated", "2025-03-15")
    assert plain.commencement_shape == NOCommencementShape.PLAIN

    receipts = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_AMENDMENT_INDEX_STAGED_COMMENCEMENT_COLLAPSED
    ]
    assert len(receipts) == 1
    assert receipts[0]["source_id"] == "no/lovtid/2025-02-02-5"
    assert receipts[0]["raw_date_in_force"] == "2025-07-01, 2025-02-10, Kongen bestemmer"
    assert receipts[0]["effective_date"] == "2025-02-10"
    assert receipts[0]["date_count"] == 2
    assert receipts[0]["commencement_shape"] == "staged_delegated"
    # Non-blocking: the act IS in force at the stated date; what is recorded is
    # the narrower fact that a staged tail was collapsed away.
    assert receipts[0]["blocking"] is False
    assert receipts[0]["strict_disposition"] == "record"

    # Readable off a serialized index without re-parsing raw_date_in_force.
    reloaded = NOAmendmentIndex.from_dict(index.to_dict())
    assert reloaded.entries[0].commencement_shape == "staged_delegated"
    assert reloaded.entries[1].commencement_shape == "plain"


def test_no_amendment_index_from_dict_loads_json_written_before_commencement_shape() -> None:
    loaded = NOAmendmentIndex.from_dict(
        {
            "data_dir": "data/norway",
            "entries": [
                {
                    "source_id": "no/lovtid/2025-02-02-5",
                    "archive": "a.tar.bz2",
                    "member_name": "m.xml",
                    "effective_status": "dated",
                    "effective_date": "2025-02-10",
                }
            ],
        }
    )

    assert loaded.entries[0].commencement_shape == "plain"


def test_no_amendment_index_from_dict_coerces_commencement_shape() -> None:
    entry = {
        "source_id": "no/lovtid/2025-02-02-5",
        "archive": "a.tar.bz2",
        "member_name": "m.xml",
        "effective_status": "dated",
        "effective_date": "2025-02-10",
    }

    # A null shape (or any falsy carrier) is the "written before the field
    # existed" case and coerces to PLAIN — never to the string "None".
    loaded = NOAmendmentIndex.from_dict(
        {"data_dir": "data/norway", "entries": [dict(entry, commencement_shape=None)]}
    )
    assert loaded.entries[0].commencement_shape is NOCommencementShape.PLAIN

    loaded = NOAmendmentIndex.from_dict(
        {
            "data_dir": "data/norway",
            "entries": [dict(entry, commencement_shape="staged_delegated")],
        }
    )
    assert loaded.entries[0].commencement_shape is NOCommencementShape.STAGED_DELEGATED

    # A string outside the closed set is a registration gap and fails loud.
    with pytest.raises(ValueError):
        NOAmendmentIndex.from_dict(
            {
                "data_dir": "data/norway",
                "entries": [dict(entry, commencement_shape="staged_delegatd")],
            }
        )


def test_build_no_amendment_index_lets_an_instrument_redate_a_staged_delegated_act(tmp_path) -> None:
    """Official instrument evidence outranks the min(dates) metadata guess.

    The act's own header names a planned date; the Lovtidend instrument names
    the date commencement was actually executed. Corpus-wide this fires on 8 of
    the 167 staged acts and always moves the date EARLIER.
    """
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            (
                "lti/2025/nl-20250202-005.xml",
                _amendment_xml("2026-01-01, Kongen bestemmer"),
            ),
            (
                "lti/2025/sf-20250301-0100.xml",
                _whole_act_instrument_xml("lov/2025-02-02-5", "2025-04-01"),
            ),
        ],
    )

    index = build_no_amendment_index(tmp_path)

    entry = index.entries[0]
    assert entry.effective_status == "instrument_authorized"
    assert entry.effective_date == "2025-04-01"
    # The act carries BOTH receipts, and keeps the label: the shape records how
    # its own metadata was written and is not overwritten by the authorization.
    assert entry.commencement_shape == NOCommencementShape.STAGED_DELEGATED
    assert entry.raw_date_in_force == "2026-01-01, Kongen bestemmer"
    assert [
        diagnostic["rule_id"]
        for diagnostic in index.diagnostics
        if diagnostic["source_id"] == "no/lovtid/2025-02-02-5"
    ] == [
        NO_AMENDMENT_INDEX_STAGED_COMMENCEMENT_COLLAPSED,
        NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
    ]


def test_build_no_amendment_index_never_offers_a_plain_dated_act_to_the_gate(tmp_path) -> None:
    """The widening is offer-side and narrow: only the staged label is added.

    A plainly dated act cited by a perfectly valid whole-act instrument still
    keeps its own date and produces no authorization — otherwise the instrument
    lane would start rewriting ordinary commencement dates wholesale.
    """
    _write_archive(
        tmp_path / "lovtidend-avd1-2025.tar.bz2",
        [
            ("lti/2025/nl-20250202-005.xml", _amendment_xml("2026-01-01")),
            (
                "lti/2025/sf-20250301-0100.xml",
                _whole_act_instrument_xml("lov/2025-02-02-5", "2025-04-01"),
            ),
        ],
    )

    index = build_no_amendment_index(tmp_path)

    assert index.entries[0].effective_status == "dated"
    assert index.entries[0].effective_date == "2026-01-01"
    assert index.entries[0].commencement_shape == NOCommencementShape.PLAIN
    assert not [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"]
        in {NO_COMMENCEMENT_EXECUTION_AUTHORIZED, NO_COMMENCEMENT_EXECUTION_REFUSED}
    ]
    assert all(item.replay_authorized is False for item in index.commencement_instruments)


# The eight staged acts an official instrument re-dates, with the metadata date
# their own header stated and the instrument date that supersedes it. Every one
# moves EARLIER: the header named a planned commencement the instrument then
# executed ahead of schedule (or, for 2013-01-11-1, retroactively).
_STAGED_INSTRUMENT_REDATINGS = {
    "no/lovtid/2013-01-11-1": ("2013-01-11", "2013-01-01"),
    "no/lovtid/2020-05-07-38": ("2022-01-01", "2020-05-11"),
    "no/lovtid/2022-06-10-35": ("2023-07-01", "2022-06-15"),
    "no/lovtid/2022-06-17-58": ("2024-01-01", "2022-07-01"),
    "no/lovtid/2022-06-17-60": ("2023-07-01", "2022-06-24"),
    "no/lovtid/2024-06-21-50": ("2026-07-01", "2024-07-01"),
    "no/lovtid/2024-06-25-53": ("2026-07-01", "2024-07-01"),
    "no/lovtid/2026-06-12-22": ("2028-07-01", "2026-07-01"),
}


def test_corpus_staged_commencement_population_reconciles() -> None:
    """W-5's answer, asserted against the ingested corpus rather than a fixture.

    W-5 asked whether the mixed ``DATE, Kongen bestemmer`` field must demote to
    contingent. Measured: demoting all of them costs 8 of the 58 replayable
    laws and makes 7 of those 8 diverge MORE, because Lovdata's consolidation
    shows the acts ARE in force at their leading date. So the population is
    typed and receipted, and nothing is demoted.
    """
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("local Norway corpus is not installed")
    index = build_no_amendment_index(data_dir)
    if index.commencement_instrument_coverage.total_instruments == 0:
        pytest.skip("local Norway corpus is not installed")

    staged = [
        entry
        for entry in index.entries
        if entry.commencement_shape == NOCommencementShape.STAGED_DELEGATED
    ]
    # 166 under the marker vocabulary this batch inherited, plus exactly one act
    # the batch's own marker widening adds; see the widening test below.
    # 167 -> 170 at W-21 (part-announcement lead recognition): three of the 13
    # acts that entered the index for the first time carry genuine mixed
    # date-plus-delegated commencement fields (2005-06-17-59, 2007-04-13-14,
    # 2009-06-19-108); no existing entry's shape changed. Signed off 2026-08-06.
    # 170 -> 174 at W-30 (intro-marker morphology): four of the 64 acts gaining
    # their first index entry carry mixed date-plus-delegated fields; all four
    # are first-time entries, none dropped, no existing entry's shape changed.
    # Signed off 2026-08-06.
    assert len(staged) == 174
    assert len([entry for entry in staged if entry.source_id != _WIDENED_MARKER_STAGED_ACT]) == 173

    # Total and queryable: one receipt per staged act, no more and no fewer.
    receipts = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_AMENDMENT_INDEX_STAGED_COMMENCEMENT_COLLAPSED
    ]
    assert len(receipts) == len(staged)
    assert {receipt["source_id"] for receipt in receipts} == {
        entry.source_id for entry in staged
    }
    assert all(receipt["date_count"] >= 1 for receipt in receipts)
    assert all(receipt["blocking"] is False for receipt in receipts)

    # Every staged act stays resolved: the label is orthogonal to the status.
    assert {entry.effective_status for entry in staged} == {"dated", "instrument_authorized"}
    assert all(entry.effective_date for entry in staged)

    # Exactly the eight instrument-proved acts move, each to the pinned date.
    redated = {
        entry.source_id: entry.effective_date
        for entry in staged
        if entry.effective_status == "instrument_authorized"
    }
    assert redated == {
        act_id: instrument_date
        for act_id, (_metadata_date, instrument_date) in _STAGED_INSTRUMENT_REDATINGS.items()
    }
    # The displaced metadata dates are read back off the staged receipts, which
    # are emitted before authorization runs and so keep the collapsed
    # ``min(dates)`` value. Both halves of the pinned table are thereby checked
    # against the corpus (instrument dates via the entries above, metadata dates
    # here), and the EARLIER claim is asserted over corpus values, not over the
    # table's own literals.
    receipt_metadata_dates = {
        receipt["source_id"]: receipt["effective_date"] for receipt in receipts
    }
    assert {act_id: receipt_metadata_dates[act_id] for act_id in redated} == {
        act_id: metadata_date
        for act_id, (metadata_date, _instrument_date) in _STAGED_INSTRUMENT_REDATINGS.items()
    }
    assert all(
        redated[act_id] < receipt_metadata_dates[act_id] for act_id in redated
    )
    authorized_ids = {
        diagnostic["source_id"]
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    }
    # The eight carry BOTH the staged receipt and the authorization receipt.
    assert set(redated) <= authorized_ids
    # 520 acts batch 03 authorized + the 8 this batch adds; no conflicts appear.
    # 528 -> 539 at W-30: eleven of the 64 first-time entries have commencement
    # instruments that authorize them; the offer-gate conjuncts are unchanged,
    # only the population grew. Signed off 2026-08-06.
    # 539 -> 540 at W-32: four artifacts gained their FIRST index entry (their
    # only amendment lead was one of the two silently-dropped shapes), and one of
    # the four — ``no/lovtid/2022-12-20-116``, patentloven § 62 a fjerde ledd
    # første punktum, a spaced letter-suffixed label — has a commencement
    # instrument that authorizes it at 2023-02-01. The offer-gate conjuncts are
    # again unchanged; only the population grew. Signed off 2026-08-07.
    assert len(authorized_ids) == 540
    assert not [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT
    ]
    assert index.status_counts() == {
        # contingent 914 -> 920 and dated 1021 -> 1028 at W-21: the 13 acts
        # gaining their first index entry via the part-announcement lead form
        # split +6 contingent / +7 dated; no existing entry's status moved.
        # Signed off 2026-08-06 together with the staged pin above.
        # contingent 920 -> 921 at W-25/W-26: no/lovtid/2020-11-20-128
        # (revisorloven's consequential-amendments act) gains its first index
        # entry — 29 ops across 8 laws, commencement "trer i kraft fra den tid
        # Kongen bestemmer" — once the spaced item ordinals its <strong>-wrapped
        # numbers produce are stripped. No existing entry moved. Signed off
        # 2026-08-06.
        # 921 -> 953, 1028 -> 1049, 528 -> 539 at W-30 (intro-marker
        # morphology): the 64 acts gaining their first index entry split
        # +32 contingent / +21 dated / +11 instrument_authorized — exactly
        # conserving the 64; no existing entry's status moved. Signed off
        # 2026-08-06.
        # 953 -> 954, 1049 -> 1051, 539 -> 540 at W-32 (multi-``bokstav`` and
        # spaced-label leads): the FOUR acts gaining their first index entry
        # split +1 contingent (`2007-06-01-18`), +2 dated (`2006-06-30-48`,
        # `2021-04-16-19`) and +1 instrument_authorized (`2022-12-20-116`) —
        # exactly conserving the 4; no existing entry's status moved. Signed off
        # 2026-08-07.
        "contingent": 954,
        # 1021 -> 1020 at W-15 (multi-part misbinding fix): the sole moved entry
        # is no/lovtid/2018-12-20-119, whose only "op" was its own part II
        # commencement sentence ("Lova tek til å gjelde straks.") swallowed as a
        # payload and misbound onto kulturminnelova §28(1). With part boundaries
        # respected the act emits zero ops and leaves the index entirely — pure
        # corruption removal, verified at op level by implementer and reviewer.
        # 1020 -> 1021 at W-18 (Rettelser lowering): no/lovtid/2020-12-18-156
        # gains its FIRST index entry — its lowered erratum op — and its own
        # commencement field is a plain date (2020-12-18), so it lands in the
        # dated bucket. Every other bucket unchanged. Signed off 2026-08-06.
        # 1021 -> 1028 at W-21: see the contingent comment above.
        # 1028 -> 1049 at W-30: see the contingent comment above.
        # 1049 -> 1051 at W-32: see the contingent comment above.
        "dated": 1051,
        "immediate": 1,
        "instrument_authorized": 540,
        "unknown": 2,
    }

    # F-03's act is the one act carrying a not-in-force signal, and even it
    # carries counter-evidence on one law. It belongs to the manual-override /
    # provision-level lane, so this batch labels it and moves nothing.
    f03 = next(entry for entry in index.entries if entry.source_id == "no/lovtid/2026-06-19-48")
    assert f03.commencement_shape == NOCommencementShape.STAGED_DELEGATED
    assert (f03.effective_status, f03.effective_date) == ("dated", "2026-06-19")


# The one act the widened marker vocabulary adds to the staged population: its
# field reads ``departementet fastset`` (nynorsk) beside three dates, so it was
# an unremarked plain DATED before the widening.
_WIDENED_MARKER_STAGED_ACT = "no/lovtid/2020-06-23-103"


def test_corpus_marker_vocabulary_widening_moves_exactly_three_acts() -> None:
    """The widening's whole corpus effect, recorded — not tuned."""
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("local Norway corpus is not installed")
    index = build_no_amendment_index(data_dir)
    if index.commencement_instrument_coverage.total_instruments == 0:
        pytest.skip("local Norway corpus is not installed")

    by_id = {entry.source_id: entry for entry in index.entries}

    # 1. ``departementet fastset`` beside dates: plain dated -> staged, same date.
    widened = by_id[_WIDENED_MARKER_STAGED_ACT]
    assert widened.commencement_shape == NOCommencementShape.STAGED_DELEGATED
    assert (widened.effective_status, widened.effective_date) == ("dated", "2020-06-23")
    assert "departementet fastset" in widened.raw_date_in_force.lower()

    # 2. Bare ``Kongen avgjer``: UNKNOWN (an uninterpretable signal) -> CONTINGENT
    #    (a delegated one). Both are unresolved, so replay is unaffected; what
    #    changes is that the act is now classified for the right reason.
    unknown_to_contingent = by_id["no/lovtid/2016-06-17-56"]
    assert unknown_to_contingent.raw_date_in_force == "Kongen avgjer"
    assert unknown_to_contingent.effective_status == "contingent"

    # 3. The other bare ``Kongen avgjer`` act was already re-dated by an
    #    instrument, so its final status is unchanged — UNKNOWN and CONTINGENT
    #    are both offered to the gate.
    already_authorized = by_id["no/lovtid/2021-04-23-23"]
    assert already_authorized.raw_date_in_force == "Kongen avgjer"
    assert already_authorized.effective_status == "instrument_authorized"

    # Nothing else moves: no other act's field matches only a widened marker.
    widened_only = {
        entry.source_id
        for entry in index.entries
        if any(
            marker in entry.raw_date_in_force.lower()
            for marker in ("departementet fastset", "kongen avgjer")
        )
        and not any(
            marker in entry.raw_date_in_force.lower()
            for marker in ("kongen bestemmer", "kongen fastset", "departementet bestemmer",
                           "fastsettes ved lov", "fra den tid")
        )
    }
    assert widened_only == {
        _WIDENED_MARKER_STAGED_ACT,
        "no/lovtid/2016-06-17-56",
        "no/lovtid/2021-04-23-23",
    }


def test_corpus_commencement_authorization_reconciles_with_the_measured_landscape() -> None:
    """W-7 tranche 3's frozen reconciliation, asserted against the ingested corpus."""
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("local Norway corpus is not installed")

    index = build_no_amendment_index(data_dir)
    # ``resolve_no_source_path`` falls back to the tracked ``data/norway``
    # directory, which exists in every checkout but carries no archives; an empty
    # instrument coverage is the real "corpus absent" signal.
    if index.commencement_instrument_coverage.total_instruments == 0:
        pytest.skip("local Norway corpus is not installed")

    assert index.commencement_instrument_coverage.to_dict() == {
        "total_instruments": 35955,
        "candidates": 608,
        "benign_non_commencement": 33590,
        "blocked_unresolved": 1757,
    }
    authorized = [
        entry for entry in index.entries if entry.effective_status == "instrument_authorized"
    ]
    # 520 acts whose own commencement was unresolved (W-7 tranche 3), plus the 8
    # staged acts batch 04 added to the offer set; the gate's conjuncts are the
    # same four, only the population offered to them grew.
    # 528 -> 539 (and 520 -> 531 non-staged) at W-30: eleven first-time entries
    # with authorizing instruments, none staged. Signed off 2026-08-06.
    # 539 -> 540 (and 531 -> 532 non-staged) at W-32: ONE first-time entry with
    # an authorizing instrument, ``no/lovtid/2022-12-20-116`` (patentloven
    # § 62 a fjerde ledd første punktum, a spaced letter-suffixed label), not
    # staged. Signed off 2026-08-07.
    assert len(authorized) == 540
    assert (
        len([
            entry
            for entry in authorized
            if entry.commencement_shape != NOCommencementShape.STAGED_DELEGATED
        ])
        == 532
    )
    assert all(entry.effective_date for entry in authorized)
    authorization_receipts = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    ]
    assert len(authorization_receipts) == 540
    assert not [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT
    ]

    anchor = next(entry for entry in index.entries if entry.source_id == "no/lovtid/2012-01-27-9")
    assert anchor.effective_status == "instrument_authorized"
    assert anchor.effective_date == "2012-03-01"
    assert anchor.raw_date_in_force == "Kongen bestemmer."
    instrument = next(
        item
        for item in index.commencement_instruments
        if item.source_id == "no/forskrift/2012-01-27-71"
    )
    assert instrument.replay_authorized is True
    assert instrument.affected_law_ids == ("no/lov/2012-01-27-9",)

    # F-03's mixed-commencement act is cited by no instrument and gains nothing.
    negative_anchor = next(
        entry for entry in index.entries if entry.source_id == "no/lovtid/2026-06-19-48"
    )
    assert negative_anchor.effective_status == "dated"
    assert negative_anchor.effective_date == "2026-06-19"

    by_base: dict[str, list[str]] = {}
    for entry in index.entries:
        for base_id in entry.base_ids:
            by_base.setdefault(base_id, []).append(entry.effective_status)
    executable = load_no_current_law_ids(data_dir) & load_available_lti_law_ids(data_dir)
    fully_replayable = [
        law_id
        for law_id in executable
        if law_id in by_base
        and not any(status in NO_UNRESOLVED_EFFECTIVE_STATUSES for status in by_base[law_id])
    ]
    # 58 -> 56 at W-15 (multi-part misbinding fix). Both directions are the
    # certifiability predicate doing its job on newly-CORRECT bindings, not a
    # tuned pin: four laws (2002-04-26-12, 2005-05-27-31, 2010-02-19-5,
    # 2015-05-12-27) gained a newly-bound, correctly-cited amending act whose
    # commencement is contingent — exactly what this predicate excludes — and
    # two laws (2012-01-27-10, 2021-06-11-79) gained their first bound source
    # with a resolved status. Verified cause-by-cause by the independent
    # reviewer; signed off 2026-08-02.
    # 56 -> 57 at W-20 (citation-less global-replace fallback): 2014-08-15-59
    # gained its first bound source with a resolved status — the recovered
    # binding from no/lovtid/2019-05-24-18, the same mechanism as the two
    # W-15 gains above. Signed off 2026-08-05.
    # 57 -> 56 at W-30 (intro-marker morphology): 2006-06-30-50 gained a
    # newly-bound, correctly-cited amending act (no/lovtid/2007-06-29-81)
    # whose commencement is contingent — the W-15 decertification mechanism.
    # It returns whenever that commencement resolves. Signed off 2026-08-06.
    assert len(fully_replayable) == 56


def test_corpus_section_intro_widening_pays_down_the_declared_target_gap() -> None:
    """W-30's whole corpus effect on F-10's declared-vs-bound gap, recorded.

    The part-announcement tail gate was a closed 11-member literal tuple; 535
    leads across 346 acts carried the same amending construction in another
    spelling and resolved nothing. Widening it to the measured morphology binds
    291 declared targets that Lovdata's ``changesToDocuments`` list had named
    and the index had receipted as unbound.

    The 20 targets that become newly unbound are the counterpart of the 20
    (act, law) group pairs the widening REMOVES: in each, ops that had been
    inherited by a stale carried-over base act move to the law their own part
    announces, and the act's genuine amendment to the old target turns out not
    to lower at all. That is the same metric honesty W-25/W-26 recorded — a
    lowering gap the misbinding had been masking, not a lost op. Nothing is
    lost: the op-identity multiset is conserved act by act across all 116
    changed acts (0 ops dropped, 958 gained).
    """
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("local Norway corpus is not installed")
    index = build_no_amendment_index(data_dir)
    if index.commencement_instrument_coverage.total_instruments == 0:
        pytest.skip("local Norway corpus is not installed")

    unbound = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == "no_amendment_index_declared_target_unbound"
    ]
    # 1,031 -> 975 receipts (one per act with a gap); 3,141 -> 2,850 unbound
    # (act, target) pairs, net of the 20 newly unbound explained above.
    # 975 -> 963 receipts and 2,850 -> 2,806 pairs at W-32: the two host-lead
    # lowering gaps (multi-``bokstav`` leads, spaced letter-suffixed section
    # labels) bind 44 more declared targets across 12 acts that lose their gap
    # entirely. Purely additive here — W-32 removes no binding, and the one
    # act whose bindings move (``no/lovtid/2015-06-19-65``, six ops crossing a
    # swallowed law-switch lead) was already misbound to a different stale base
    # before and after. Signed off 2026-08-07.
    # 963 -> 960 receipts and 2,806 -> 2,642 pairs at W-34: closing the payload
    # cursor at numbered law-switch leads binds 164 more declared targets across
    # 15 acts, three of which lose their gap entirely. The pair drop equals the
    # binding gain below EXACTLY (2,806 - 2,642 = 6,295 - 6,131 = 164): every
    # target W-34 binds was a declared target the index had already receipted,
    # and W-34 un-declares none. Signed off 2026-08-07.
    # 960 -> 959 receipts and 2,642 -> 2,605 pairs at W-35: splitting the leads
    # Lovdata trapped INSIDE ``futureLegalArticle`` payloads binds 37 more
    # declared targets across 6 acts, one of which (``2015-09-04-85``) loses its
    # gap entirely. The pair drop again equals the binding gain below EXACTLY
    # (2,642 - 2,605 = 6,332 - 6,295 = 37), the same conservation W-34 recorded:
    # every target the split binds was already a declared target on the receipt,
    # and the split un-declares none. Signed off 2026-08-07.
    assert len(unbound) == 959
    assert sum(len(diagnostic["unbound_target_ids"]) for diagnostic in unbound) == 2605
    assert len({diagnostic["source_id"] for diagnostic in unbound}) == 959

    # 64 acts gain their FIRST index entry: they announced every one of their
    # parts with an unlisted tail, so they had bound no law at all.
    # 2,544 -> 2,548 and 6,084 -> 6,131 at W-32: four more acts whose only
    # amendment lead was one of the two dropped shapes.
    # 6,131 -> 6,295 at W-34, entries unmoved: the cursor stop introduces no new
    # amending ACT, only new (act, law) pairs inside acts that were already
    # indexed. 166 pairs gained, 2 removed — ``2014-05-09-16``/``1987-06-12-48``
    # and ``2015-06-19-65``/``1984-06-08-55``, both bindings that had been
    # harvested from a swallowed sibling lead's citation and that address a
    # section neither law has (NIS-loven has no § 339, konkursloven no § 6-2;
    # foretaksnavneloven ``1985-06-21-79``, which the second op now binds, does).
    # 6,295 -> 6,332 at W-35, entries again unmoved and for the same reason: the
    # payload split reaches only INTO acts the index already has. 38 pairs
    # gained, 1 removed — ``2015-06-19-65``/``2013-06-21-102``, whose two
    # § 11-1 repeals move to AIF-loven ``2014-06-20-28``. Item 251 announces
    # "gjøres følgende ENDRING" (singular) and its one change is the § 9-3
    # heading; the § 11-1 repeals belong to item 252, which was the lead trapped
    # inside that § 9-3 element.
    assert len(index.entries) == 2548
    bindings = {
        (entry.source_id, base_id) for entry in index.entries for base_id in entry.base_ids
    }
    assert len(bindings) == 6332
    # 26,218 at W-30; +2 at W-24, both reconciled to a named erratum and neither
    # touching this test's own subject. W-24 lowered two Del-scoped Rettelser
    # corrections into the law each part amends — ``2019-12-20-110`` Del I into
    # kringkastingsloven and ``2023-12-20-98`` Del V into skatteloven — and both
    # append to a group this artifact ALREADY bound, so bindings (6,084) and
    # entries (2,544) above are unmoved, as are every status count,
    # ``fully_replayable`` (56) and all 56 scan rows.
    # 26,220 -> 26,691 at W-32: +478 gained ops (240 from multi-``bokstav``
    # leads, 227 from the spaced-label sentence widening, 6 renumber
    # replacements, 4 downstream, 1 erratum) less 7 that left one stale base
    # for another inside ``no/lovtid/2015-06-19-65``. Base-agnostic op identity
    # over the whole corpus: 472 gained, 1 lost — the single lost op is
    # documented in the W-32 report as a fired stop condition.
    # 26,691 -> 26,769 at W-34 (+78 net across 15 acts): 526 ops gained, 448
    # lost, and the classification at three identity levels is 434 pure rebinds,
    # 79 genuinely new ops, 8 rebind-plus-payload-truncation, 5 payload
    # truncations on an unchanged binding, and 1 op removed. That one is the
    # duplicate half of ``2014-05-09-16``'s "I § 339 … erstattes «formann» med
    # «leder»", which used to emit TWICE because the global text-replace path
    # harvested a citation from each of the two sibling leads its payload run had
    # swallowed; one op on one base act now replaces two on two wrong ones.
    # 26,769 -> 26,785 at W-35 (+16 net across the 6 acts holding all 41 trapped
    # elements): 20 genuinely new ops, 4 removed, and the removed four are the
    # pre-truncation half of ops that also changed base act, so nothing is lost.
    # The other movement is 30 payload truncations and 74 pure rebinds; measured
    # against the true governing enumeration item — run-on and numberless leads
    # included, so leads no resolver can reach still count against the change —
    # that is 62 wrong -> right, 13 stale -> stale, and ZERO right -> wrong.
    assert sum(entry.n_ops for entry in index.entries) == 26785


def test_no_amendment_index_staleness_report_detects_archive_change(tmp_path) -> None:
    archive_path = tmp_path / "lovtidend-avd1-2025.tar.bz2"
    _write_archive(
        archive_path,
        [("lti/2025/nl-20250202-005.xml", _amendment_xml("2025-02-10"))],
    )
    index = build_no_amendment_index(tmp_path)

    fresh = index.staleness_report(tmp_path)
    assert fresh["index_stale"] is False

    _write_archive(
        archive_path,
        [("lti/2025/nl-20250303-006.xml", _amendment_xml("2025-03-15"))],
    )
    stale = cast(dict[str, Any], index.staleness_report(tmp_path))

    assert stale["index_stale"] is True
    assert stale["stale_archives"][0]["archive"] == "lovtidend-avd1-2025.tar.bz2"


def test_no_consolidation_snapshot_date_reads_the_archive_observation_instant(tmp_path) -> None:
    """The scan's default comparison date is derived, not frozen (finding F-01).

    The consolidated ``current.xml`` artifacts ARE the snapshot replay is
    compared against, so their latest observation instant is the horizon; a
    later observation of anything else must not move it.
    """
    from datetime import datetime, timezone

    from farchive import Farchive

    from lawvm.norway.sources import (
        NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE,
        no_consolidation_snapshot_date,
    )

    db_path = tmp_path / "norway.farchive"
    archive = Farchive(db_path)
    archive.store(
        "no://lov/2025-01-01-1/current.xml",
        b"<html><body/></html>",
        # 23:30Z falls on the NEXT day in the local Norwegian timezone, so a
        # passing assertion also pins that the instant is read as UTC.
        observed_at=datetime(2025, 3, 4, 23, 30, tzinfo=timezone.utc),
    )
    archive.store(
        "no://lovtid/2025-02-02-5/amendment.xml",
        b"<html><body/></html>",
        observed_at=datetime(2025, 9, 9, 12, 0, tzinfo=timezone.utc),
    )
    archive.close()

    assert no_consolidation_snapshot_date(db_path) == "2025-03-04"

    # A change-free re-crawl: the SAME bytes stored again at a later instant.
    # farchive branches on digest identity, so this extends the open span
    # rather than opening a new one — ``observed_from`` stays pinned at the
    # first appearance while ``last_confirmed_at`` advances. The derived
    # horizon must follow the re-confirmation: reading ``observed_from`` would
    # freeze it at the last content CHANGE and re-open F-01 for every law
    # amended between that change and the crawl that confirmed it.
    reconfirmed = tmp_path / "reconfirmed.farchive"
    archive = Farchive(reconfirmed)
    archive.store(
        "no://lov/2025-01-01-1/current.xml",
        b"<html><body/></html>",
        observed_at=datetime(2025, 3, 4, 23, 30, tzinfo=timezone.utc),
    )
    archive.store(
        "no://lov/2025-01-01-1/current.xml",
        b"<html><body/></html>",
        # 23:40Z is again the next day in local Norwegian time, so the UTC
        # read stays pinned across the re-confirmation too.
        observed_at=datetime(2025, 6, 17, 23, 40, tzinfo=timezone.utc),
    )
    span = archive.resolve("no://lov/2025-01-01-1/current.xml")
    assert span is not None
    # Pin the farchive semantics this helper depends on: one extended span,
    # not two, with the two instants genuinely disagreeing.
    assert len(archive.history("no://lov/2025-01-01-1/current.xml")) == 1
    assert span.observation_count == 2
    assert span.observed_from == datetime(2025, 3, 4, 23, 30, tzinfo=timezone.utc)
    assert span.last_confirmed_at == datetime(2025, 6, 17, 23, 40, tzinfo=timezone.utc)
    archive.close()

    assert no_consolidation_snapshot_date(reconfirmed) == "2025-06-17"

    # A legacy tar-directory corpus records no observation instant at all.
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    assert (
        no_consolidation_snapshot_date(legacy_dir)
        == NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE
    )


def test_no_consolidation_snapshot_date_refuses_an_archive_without_consolidations(
    tmp_path,
) -> None:
    """An farchive holding no ``current.xml`` fails loud, it does not borrow the constant.

    The legacy tar directory legitimately has no observation instant to derive
    from, so it keeps the documented fallback. An farchive is a different
    animal: holding zero consolidated artifacts means the corpus is corrupt or
    mis-populated, and silently returning the legacy constant would make the
    two indistinguishable (AGENTS.md §1.10).
    """
    from datetime import datetime, timezone

    from farchive import Farchive

    from lawvm.norway.sources import (
        NOConsolidationSnapshotError,
        no_consolidation_snapshot_date,
    )

    db_path = tmp_path / "norway.farchive"
    archive = Farchive(db_path)
    # Populated, but with nothing from the consolidated family.
    archive.store(
        "no://lovtid/2025-02-02-5/amendment.xml",
        b"<html><body/></html>",
        observed_at=datetime(2025, 9, 9, 12, 0, tzinfo=timezone.utc),
    )
    archive.close()

    with pytest.raises(NOConsolidationSnapshotError) as excinfo:
        no_consolidation_snapshot_date(db_path)
    message = str(excinfo.value)
    # The diagnostic must name what was expected, what was found, and the fix.
    assert "no://lov/%/current.xml" in message
    assert "Found: none" in message
    assert "no-ingest" in message


def test_corpus_consolidation_snapshot_date_reproduces_the_fallback_constant() -> None:
    """The licensing claim on the fallback constant, made executable.

    ``NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE`` is licensed by the farchive
    derivation independently reproducing it. Asserting that against the
    installed corpus is what makes the constant rot LOUDLY on a future corpus
    re-capture instead of silently drifting away from the snapshot the legacy
    path claims to describe.
    """
    from lawvm.norway.sources import (
        NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE,
        is_no_farchive_path,
        no_consolidation_snapshot_date,
    )

    data_dir = resolve_no_source_path(None)
    if not data_dir.exists() or not is_no_farchive_path(data_dir):
        pytest.skip("local Norway corpus is not installed")

    assert (
        no_consolidation_snapshot_date(data_dir)
        == NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE
    )
