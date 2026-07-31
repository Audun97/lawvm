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
    NOAmendmentIndex,
    build_no_amendment_index,
    load_no_amendment_index,
    save_no_amendment_index,
)
from lawvm.norway.sources import (
    NO_UNRESOLVED_EFFECTIVE_STATUSES,
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
    assert len(authorized) == 520
    assert all(entry.effective_date for entry in authorized)
    authorization_receipts = [
        diagnostic
        for diagnostic in index.diagnostics
        if diagnostic["rule_id"] == NO_COMMENCEMENT_EXECUTION_AUTHORIZED
    ]
    assert len(authorization_receipts) == 520
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
    assert len(fully_replayable) == 58


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
