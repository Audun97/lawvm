from __future__ import annotations

from typing import Any, cast

from lawvm.core.ir import IRStatute, LegalAddress, ProvisionTimeline, ProvisionVersion
from lawvm.core.ir_helpers import irnode_to_text

import io
import tarfile

import pytest
from types import SimpleNamespace

from lawvm.core.ir import IRNode
from lawvm.core.semantic_types import IRNodeKind
from lawvm.core.timeline import ingest_consolidated, verify_consistency
from lawvm.core.timeline_consistency import ConsistencyDivergence
from lawvm.norway.sources import ingest_no_public_archives, resolve_no_source_path
from lawvm.norway.verify import (
    NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS,
    NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_COUNTERPART,
    NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_NESTED_ADDRESS,
    NO_VERIFY_COMPARE_CONTINGENT_OTHER_LAWS_PLACEHOLDER_SUPPRESSED,
    NO_VERIFY_COMPARE_DEFINITION_SUBSECTION_PAIRS_COLLAPSED,
    NO_VERIFY_COMPARE_NESTED_ITEM_TAIL_SUPPRESSED,
    NO_VERIFY_COMPARE_OTHER_LAWS_CONTEXT_SUPPRESSED,
    NO_VERIFY_COMPARE_REPEALED_SHELL_BLANKED,
    NO_VERIFY_COMPARE_SELF_SECTION_SHELL_BLANKED,
    NO_VERIFY_COMPARE_SENTENCE_CHILDREN_COLLAPSED,
    classify_no_annex_ceiling,
    _infer_no_source_signal,
    _no_base_year,
    _no_compare_child_path,
    _no_kind_value,
    _NO_VERIFY_INLINE_FOOTNOTE_RE,
    _normalize_no_compare_tree,
    _partition_primary_divergences,
    no_partition_is_annex_ceiling_dominated,
    no_paths_related,
    irnode_to_no_comparison_text,
    normalize_no_comparison_text,
)
from lawvm.norway.verify import build_no_verify_partition, build_no_verify_scan, verify_no_against_current


_BASE_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Testlov om data</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="LTI/lov/2025-01-01-1">
      <section class="section" data-name="kap1" data-lovdata-URL="LTI/lov/2025-01-01-1/KAPITTEL_1">
        <h2>Kapittel 1. Innledning</h2>
        <article class="legalArticle" data-name="§1" data-lovdata-URL="LTI/lov/2025-01-01-1/§1">
          <h3 class="legalArticleHeader">§ 1. Formaal</h3>
          <article class="legalP" id="ledd1">Loven gjelder testdata.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


_CURRENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Testlov om data</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-1">
      <section class="section" data-name="kap1" data-lovdata-URL="NL/lov/2025-01-01-1/KAPITTEL_1">
        <h2>Kapittel 1. Innledning</h2>
        <article class="legalArticle" data-name="§1" data-lovdata-URL="NL/lov/2025-01-01-1/§1">
          <h3 class="legalArticleHeader">§ 1. Formaal</h3>
          <article class="legalP" id="ledd1">Loven gjelder oppdatert testdata.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


_CURRENT_DIVERGENT_XML = _CURRENT_XML.replace(
    b"oppdatert testdata",
    b"annen testdata",
)


def _amendment_xml() -> bytes:
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-02-10</dd>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change" data-change-part="lov/2025-01-01-1/§1">
        <article class="defaultP">Paragraf 1 skal lyde:</article>
        <article class="legalArticle" data-name="§1" data-lovdata-URL="LTI/lov/2025-01-01-1/§1">
          <h3 class="legalArticleHeader">§ 1. Formaal</h3>
          <article class="legalP" id="ledd1">Loven gjelder oppdatert testdata.</article>
        </article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _large_divergent_current_xml(section_count: int = 60) -> bytes:
    sections = []
    for idx in range(1, section_count + 1):
        sections.append(
            f"""
        <article class="legalArticle" data-name="§{idx}" data-lovdata-URL="NL/lov/2010-01-01-1/§{idx}">
          <h3 class="legalArticleHeader">§ {idx}. Tittel</h3>
          <article class="legalP">Gjeldende tekst {idx}.</article>
        </article>"""
        )
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Stor testlov</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2010-01-01-1">
      <section class="section" data-name="kap1" data-lovdata-URL="NL/lov/2010-01-01-1/KAPITTEL_1">
        <h2>Kapittel 1. Innledning</h2>
        {''.join(sections)}
      </section>
    </main>
  </body>
</html>
"""
    return xml.encode("utf-8")


def _write_archive(path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def test_verify_no_against_current_accepts_exact_match(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _CURRENT_XML)],
    )

    result = verify_no_against_current(
        "no/lov/2025-01-01-1",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None
    assert result.consistent is True
    assert result.divergence_count == 0


def test_verify_no_against_current_reports_divergence(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _CURRENT_DIVERGENT_XML)],
    )

    result = verify_no_against_current(
        "no/lov/2025-01-01-1",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None
    assert result.consistent is False
    assert result.divergence_count == 1
    assert result.divergence_counts == {"MISMATCH": 1}


def test_verify_no_against_current_accepts_farchive_source_path(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _CURRENT_XML)],
    )
    db_path = tmp_path / "norway.farchive"
    ingest_no_public_archives(tmp_path, db_path)

    result = verify_no_against_current(
        "no/lov/2025-01-01-1",
        as_of="2025-02-15",
        data_dir=db_path,
    )

    assert result.error is None
    assert result.consistent is True
    assert result.divergence_count == 0


def test_build_no_verify_scan_checks_executable_replayable_subset(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _CURRENT_XML)],
    )

    report = build_no_verify_scan(
        as_of="2025-02-15",
        data_dir=tmp_path,
        limit=5,
    )

    assert report["candidate_count"] == 1
    assert report["scanned_count"] == 1
    assert report["summary"] == {"consistent": 1, "divergent": 0, "error": 0}
    assert report["source_signal_counts"] == {}
    assert report["results"][0]["base_id"] == "no/lov/2025-01-01-1"

    filtered = build_no_verify_scan(
        as_of="2025-02-15",
        data_dir=tmp_path,
        limit=5,
        base_ids=["no/lov/2099-01-01-1"],
    )
    assert filtered["candidate_count"] == 0
    assert filtered["scanned_count"] == 0
    assert filtered["results"] == []


def test_build_no_verify_scan_skips_empty_current_shell_candidates(tmp_path) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250101-002.xml", _BASE_XML.replace(b"2025-01-01-1", b"2025-01-01-2")),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
            ("lti/2025/nl-20250202-006.xml", _amendment_xml().replace(b"2025-01-01-1", b"2025-01-01-2")),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [
            ("nl/nl-20250101-001.xml", _CURRENT_XML),
            (
                "nl/nl-20250101-002.xml",
                b"<html><head><title>Lov om endringer i testloven</title></head><body><main></main></body></html>",
            ),
        ],
    )

    report = build_no_verify_scan(as_of="2025-02-15", data_dir=tmp_path, limit=5)

    assert report["candidate_count"] == 1
    assert [item["base_id"] for item in report["results"]] == ["no/lov/2025-01-01-1"]


def test_verify_no_against_current_flags_sparse_indexed_history_signal(tmp_path) -> None:
    base_xml = _BASE_XML.replace(b"2025-01-01-1", b"2010-01-01-1")
    amendment_xml = _amendment_xml().replace(b"2025-01-01-1", b"2010-01-01-1")
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2010/nl-20100101-001.xml", base_xml),
            ("lti/2025/nl-20250202-005.xml", amendment_xml),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20100101-001.xml", _large_divergent_current_xml())],
    )

    result = verify_no_against_current(
        "no/lov/2010-01-01-1",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None
    assert result.consistent is False
    assert result.indexed_amendment_count == 1
    assert result.applied_amendment_count == 1
    assert result.replay_op_count == 1
    assert result.divergence_count >= 50
    assert result.source_signal == "sparse_indexed_history"

    report = build_no_verify_scan(
        as_of="2025-02-15",
        data_dir=tmp_path,
        limit=5,
    )
    assert report["summary"] == {"consistent": 0, "divergent": 1, "error": 0}
    assert report["source_signal_counts"] == {"sparse_indexed_history": 1}
    assert report["results"][0]["source_signal"] == "sparse_indexed_history"


def test_infer_no_source_signal_flags_single_op_mid_sized_sparse_case() -> None:
    assert (
        _infer_no_source_signal(
            divergence_count=18,
            indexed_amendment_count=1,
            replay_op_count=1,
            base_year=2005,
        )
        == "sparse_indexed_history"
    )


def test_infer_no_source_signal_leaves_real_two_amendment_case_unclassified() -> None:
    assert (
        _infer_no_source_signal(
            divergence_count=14,
            indexed_amendment_count=2,
            replay_op_count=2,
            base_year=2004,
        )
        is None
    )


def test_infer_no_source_signal_flags_two_indexed_amendment_sparse_case() -> None:
    # Mirrors post-§1-fix shape of no/lov/2001-01-05-1 (Vaktvirksomhetsloven)
    # at as-of 2025-01-01: 2 indexed amendments, 2 applied, 3 replay ops,
    # 83 primary divergences — and 2001 base year. This statute sat at
    # SCORED saturated-1.0 before this widening because indexed_amendment_
    # count=2 exceeded the prior ≤1 threshold while the divergence volume
    # made the structural_err cap fire. Two corpus witnesses (this +
    # SCE-loven) prompted widening the indexed bound from ≤1 → ≤2.
    assert (
        _infer_no_source_signal(
            divergence_count=83,
            indexed_amendment_count=2,
            replay_op_count=3,
            base_year=2001,
        )
        == "sparse_indexed_history"
    )


def test_infer_no_source_signal_leaves_three_indexed_case_unclassified() -> None:
    # §2.9 paired negative for the widended ``<=2`` threshold: 3 indexed
    # amendments + high divergence_count + few ops + old base year does
    # NOT fire sparse_indexed_history. The threshold boundary is ``≤2``:
    # three indexed amendments over multiple enactment-year retirement
    # waves is more substantial coverage than ≤2 indexes across the same
    # window, so the acquisition-ceiling hand-wave stops here. A
    # regression widening to ``<=3`` would silently misclassify the
    # ``reproducing through 3-amendment replay against a clearly real
    # algorithm bug`` shape as a data ceiling.
    assert (
        _infer_no_source_signal(
            divergence_count=50,
            indexed_amendment_count=3,
            replay_op_count=4,
            base_year=2005,
        )
        is None
    )


# --- §1.10: _no_base_year converts silent try/except into a typed finding ---
#
# Before this fix, verify_no_against_current had:
#     try:
#         base_year = int(result.base_id.split("/")[2][:4])
#     except (IndexError, ValueError):
#         base_year = 0
# which (per AGENTS.md §1.10) was the canonical invisible-heuristic smell — a
# malformed base_id silently became "year unknown" with no evidence trail.
# _no_base_year returns (0, finding) for malformed shapes and (year, None)
# for the canonical ``no/lov/YYYY-MM-DD-N`` form. verify_no_against_current
# now attaches the finding as result.source_signal_diagnostic so a triager
# can see the unparseable base_id without re-running extraction.


def test_no_base_year_extracts_canonical_norway_base_id_year() -> None:
    year, finding = _no_base_year("no/lov/2024-01-12-1")

    assert year == 2024
    assert finding is None


def test_no_base_year_emits_typed_finding_for_malformed_segments() -> None:
    year, finding = _no_base_year("no/lov")

    assert year == 0
    assert finding is not None
    assert finding["rule_id"] == "no_verify_source_signal_base_year_unresolved"
    assert finding["phase"] == "verify"
    assert finding["family"] == "source_pathology"
    assert finding["base_id"] == "no/lov"
    assert finding["base_year"] == 0
    # §1.10: the offending base_id is embedded in the finding so triage does
    # not need to re-run extraction to find the malformed id.
    assert "no/lov" in str(finding)


def test_no_base_year_emits_typed_finding_for_non_numeric_year_segment() -> None:
    year, finding = _no_base_year("no/nonexistent/xyz-1")

    assert year == 0
    assert finding is not None
    assert finding["rule_id"] == "no_verify_source_signal_base_year_unresolved"
    assert finding["base_id"] == "no/nonexistent/xyz-1"


def test_no_base_year_emits_typed_finding_for_short_year_segment() -> None:
    # A 3-char or shorter year segment is treated as unresolvable (canonical
    # form is 4-digit year). The bare try/except previously set base_year=0
    # silently; the typed finding now carries the offending base_id.
    year, finding = _no_base_year("no/lov/2-01-01-1")

    assert year == 0
    assert finding is not None
    assert finding["rule_id"] == "no_verify_source_signal_base_year_unresolved"


def test_no_kind_value_coerces_enum_kind() -> None:
    assert _no_kind_value(IRNodeKind.SENTENCE) == "sentence"


def test_no_kind_value_coerces_plain_str_kind() -> None:
    # Some parse paths that build the comparison tree assign a plain str kind
    # rather than the IRNodeKind enum member; the compare/verify path must
    # tolerate both (regression for the _no_kind_value str-vs-enum crash).
    assert _no_kind_value(cast(Any, "sentence")) == "sentence"


def test_no_kind_value_does_not_crash_in_child_path_with_str_kind() -> None:
    # IRNode.kind is statically typed IRNodeKind, but the comparison tree can
    # carry a plain str kind at runtime; exercise that shape end-to-end.
    child = IRNode(kind=cast(Any, "sentence"), label="1", text="x")
    path = _no_compare_child_path((), child)
    assert path == (("sentence", "1"),)


def test_no_paths_related_treats_last_item_anchor_as_touching_concrete_item() -> None:
    assert no_paths_related(
        (("section", "5"), ("subsection", "1"), ("item", "last")),
        (("section", "5"), ("subsection", "1"), ("item", "8")),
    )


def test_build_no_verify_partition_separates_untouched_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_verify_scan",
        lambda **_: {
            "data_dir": "data/norway.farchive",
            "as_of": "2026-03-29",
            "candidate_count": 2,
            "scanned_count": 2,
            "summary": {"consistent": 0, "divergent": 2, "error": 0},
            "source_signal_counts": {},
            "results": [
                {
                    "base_id": "no/lov/2024-01-12-1",
                    "current_title": "A",
                    "replay_status": "replayed",
                    "consistent": False,
                    "divergence_count": 3,
                    "divergence_counts": {"MISMATCH": 3},
                    "indexed_amendment_count": 3,
                    "applied_amendment_count": 3,
                    "replay_op_count": 10,
                    "source_signal": "",
                    "error": "",
                },
                {
                    "base_id": "no/lov/2020-12-18-156",
                    "current_title": "B",
                    "replay_status": "replayed",
                    "consistent": False,
                    "divergence_count": 2,
                    "divergence_counts": {"MISMATCH": 1, "OPS_MISSING": 1},
                    "indexed_amendment_count": 2,
                    "applied_amendment_count": 2,
                    "replay_op_count": 7,
                    "source_signal": "",
                    "error": "",
                },
            ],
        },
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda base_id, **_: SimpleNamespace(base_id=base_id, divergences=[]),
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_verify_coverage_summary",
        lambda *, verify_result, index, data_dir=None: (
            {
                "touched_path_count": 3,
                "touched_source_count": 2,
                "touched_op_count": 7,
                "touched_divergence_count": 3,
                "untouched_divergence_count": 0,
            }
            if verify_result.base_id == "no/lov/2024-01-12-1"
            else {
                "touched_path_count": 1,
                "touched_source_count": 2,
                "touched_op_count": 7,
                "touched_divergence_count": 0,
                "untouched_divergence_count": 2,
            }
        ),
    )
    monkeypatch.setattr(
        "lawvm.norway.verify._load_no_index",
        lambda **_: SimpleNamespace(),
    )
    # W-45: the ``unverifiable`` sibling is a corpus census, and this test's
    # scan is entirely synthetic (``_load_no_index`` is a bare namespace). Stub
    # it so the routing assertions below stay a statement about routing.
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_no_consolidation_rows",
        lambda *_args, **_kwargs: [],
    )

    report = build_no_verify_partition(as_of="2026-03-29", data_dir=None, limit=10)

    assert [item["base_id"] for item in report["partitions"]["replay_defect"]] == ["no/lov/2024-01-12-1"]
    assert [item["base_id"] for item in report["partitions"]["untouched_drift"]] == ["no/lov/2020-12-18-156"]
    # W-23 added a bucket; a scan whose rows carry no W-17 ceiling fields must
    # still route exactly as before, with the new bucket simply empty.
    assert report["partitions"]["annex_ceiling"] == []
    # W-45: the census sits BESIDE the buckets, never in them. A law with no
    # stored consolidation was never scanned, so it carries none of the
    # scan-row fields every ``partitions`` consumer indexes off a row.
    assert "no_stored_consolidation" not in report["partitions"]
    assert report["unverifiable"]["no_stored_consolidation"] == {
        "total": 0,
        "by_family": {
            "amending_act": 0,
            "temporary_act": 0,
            "wage_board_act": 0,
            "substantive_act": 0,
        },
        "would_be_candidates": 0,
        "substantive_unexplained": 0,
    }


# --- W-23: annex-ceiling routing ------------------------------------------
#
# The measured contradiction this fixes, at as-of 2026-07-10 over the 57 scan
# candidates: ``sparse_indexed_history`` fired on 4 laws and
# build_no_verify_partition tested ``source_signal`` before anything else, so
#
#   2018-06-15-38  716 div = 714 ceiling + 2 unexplained  signal -> source_sparse
#   2006-06-30-50  212 div = 211 ceiling + 1 unexplained  signal -> source_sparse
#   2017-06-16-51  210 div = 204 ceiling + 6 unexplained  none   -> replay_defect
#
# — one cause (W-17's annexed-instrument representation), three laws, two
# buckets, and the ``source_sparse`` story ("we never acquired the amending
# history") false of two of its four members at 99.7% and 99.5% ceiling.
#
# The ledger's candidate fix — route the annex laws by their unexplained
# residue through the existing touched/untouched coverage split — was MEASURED
# AND REJECTED here (.tmp/w23/annex_coverage.json): it relocates the split
# rather than closing it, because the residues fall on different sides of the
# coverage test (2018-06-15-38 touched=0 -> untouched_drift; 2006-06-30-50
# touched=1 and 2017-06-16-51 touched=6 -> replay_defect). Only a bucket keyed
# on the ceiling itself puts one cause in one place.


def test_no_partition_annex_ceiling_predicate_flags_ceiling_majority() -> None:
    # 2018-06-15-38's shape: 714 of 716.
    assert no_partition_is_annex_ceiling_dominated(
        {"divergence_count": 716, "ceiling_divergence_count": 714, "unexplained_divergence_count": 2}
    )


def test_no_partition_annex_ceiling_predicate_ignores_law_with_no_ceiling() -> None:
    # 2001-01-05-1's shape: the genuinely sparse law, 83 divergences, 0 ceiling.
    # It must stay reachable by the source-signal branch.
    assert not no_partition_is_annex_ceiling_dominated(
        {"divergence_count": 83, "ceiling_divergence_count": 0, "unexplained_divergence_count": 83}
    )


def test_no_partition_annex_ceiling_predicate_is_a_strict_majority() -> None:
    # A tie is NOT domination: at 50/50 the bucket's story ("this law's
    # divergences are the representation ceiling") is not true of the law. No
    # corpus law is anywhere near this boundary — the members sit at 97.1%,
    # 99.5% and 99.7% and every non-member at 0% — so the boundary is pinned
    # by its meaning, not by a measurement.
    assert not no_partition_is_annex_ceiling_dominated(
        {"divergence_count": 10, "ceiling_divergence_count": 5, "unexplained_divergence_count": 5}
    )
    assert no_partition_is_annex_ceiling_dominated(
        {"divergence_count": 11, "ceiling_divergence_count": 6, "unexplained_divergence_count": 5}
    )


def test_no_partition_annex_ceiling_predicate_tolerates_pre_w17_rows() -> None:
    # A row built without the W-17 split (both fields absent) is never routed
    # to the ceiling bucket — the predicate cannot invent a ceiling.
    assert not no_partition_is_annex_ceiling_dominated({"divergence_count": 716})


def _w23_scan_row(base_id: str, *, total: int, ceiling: int, signal: str) -> dict[str, Any]:
    return {
        "base_id": base_id,
        "current_title": base_id,
        "replay_status": "replayed",
        "consistent": False,
        "divergence_count": total,
        "divergence_counts": {"OPS_MISSING": total},
        "ceiling_divergence_count": ceiling,
        "ceiling_divergence_rule_counts": (
            {NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS: ceiling} if ceiling else {}
        ),
        "unexplained_divergence_count": total - ceiling,
        "amendment_count": 2,
        "indexed_amendment_count": 2,
        "applied_amendment_count": 2,
        "replay_op_count": 3,
        "source_signal": signal,
        "error": "",
    }


def test_build_no_verify_partition_keeps_the_annex_family_in_one_bucket(monkeypatch) -> None:
    """The family-split regression, in the three corpus laws' exact shapes.

    Two of the three carry ``sparse_indexed_history`` and one does not; before
    W-23 that difference alone decided their bucket. All three must now land
    in ``annex_ceiling``, and the genuinely sparse law must still reach
    ``source_sparse``.
    """
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_verify_scan",
        lambda **_: {
            "data_dir": "data/norway.farchive",
            "as_of": "2026-07-10",
            "candidate_count": 4,
            "scanned_count": 4,
            "summary": {"consistent": 0, "divergent": 4, "error": 0},
            "source_signal_counts": {"sparse_indexed_history": 3},
            "results": [
                _w23_scan_row(
                    "no/lov/2018-06-15-38", total=716, ceiling=714, signal="sparse_indexed_history"
                ),
                _w23_scan_row("no/lov/2017-06-16-51", total=210, ceiling=204, signal=""),
                _w23_scan_row(
                    "no/lov/2006-06-30-50", total=212, ceiling=211, signal="sparse_indexed_history"
                ),
                _w23_scan_row(
                    "no/lov/2001-01-05-1", total=83, ceiling=0, signal="sparse_indexed_history"
                ),
            ],
        },
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda base_id, **_: SimpleNamespace(base_id=base_id, divergences=[]),
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_verify_coverage_summary",
        lambda *, verify_result, index, data_dir=None: {
            "touched_path_count": 0,
            "touched_source_count": 0,
            "touched_op_count": 0,
            "touched_divergence_count": 0,
            "untouched_divergence_count": 1,
        },
    )
    monkeypatch.setattr("lawvm.norway.verify._load_no_index", lambda **_: SimpleNamespace())
    # W-45: synthetic scan, so the corpus census is stubbed (see the routing
    # test above). Nothing here depends on it.
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_no_consolidation_rows",
        lambda *_args, **_kwargs: [],
    )

    report = build_no_verify_partition(as_of="2026-07-10", data_dir=None, limit=10)
    partitions = report["partitions"]

    assert [item["base_id"] for item in partitions["annex_ceiling"]] == [
        "no/lov/2018-06-15-38",
        "no/lov/2006-06-30-50",
        "no/lov/2017-06-16-51",
    ]
    # The signal is NOT what routes any more: it still fires on two of the
    # three, and no longer decides where they go.
    assert [item["base_id"] for item in partitions["source_sparse"]] == ["no/lov/2001-01-05-1"]
    assert partitions["replay_defect"] == []
    assert partitions["untouched_drift"] == []
    # Complete and disjoint.
    routed = [item["base_id"] for bucket in partitions.values() for item in bucket]
    assert len(routed) == len(set(routed)) == 4


def test_normalize_no_comparison_text_removes_spacing_noise_only() -> None:
    assert normalize_no_comparison_text("§ 1-2 , kapittel 7 .") == "§ 1-2, kapittel 7."


def test_normalize_no_comparison_text_treats_repealed_shell_as_empty() -> None:
    assert normalize_no_comparison_text("§ 2-6. (Opphevet)") == ""
    assert normalize_no_comparison_text("(Opphevet)") == ""


def test_normalize_no_comparison_text_strips_other_laws_placeholder_dashes() -> None:
    assert (
        normalize_no_comparison_text(
            "I lov 13. mars 1981 nr. 6 om vern mot forurensning og om avfall gjøres følgende endringer: – – –"
        )
        == "I lov 13. mars 1981 nr. 6 om vern mot forurensning og om avfall gjøres følgende endringer:"
    )
    assert (
        normalize_no_comparison_text(
            "Fra det tidspunktet loven trer i kraft, gjøres følgende endringer i andre lover: – – –"
        )
        == "Fra det tidspunktet loven trer i kraft, gjøres følgende endringer i andre lover:"
    )
    assert (
        normalize_no_comparison_text(
            "Frå den tida lova tek til å gjelde, skal desse endringane gjerast i andre lover: – – –"
        )
        == "Frå den tida lova tek til å gjelde, skal desse endringane gjerast i andre lover:"
    )


def test_normalize_no_comparison_text_closes_numeric_hyphen_gap() -> None:
    assert normalize_no_comparison_text("CO 2 -ekvivalenter") == "CO 2-ekvivalenter"


def test_normalize_no_comparison_text_strips_space_after_open_paren() -> None:
    assert normalize_no_comparison_text("§ 7-2 ( sikkerhetslovens anvendelse)") == (
        "§ 7-2 (sikkerhetslovens anvendelse)"
    )


def test_normalize_no_comparison_text_strips_space_before_close_paren() -> None:
    # Corpus shape: the consolidated body wraps the cross-reference in an anchor,
    # and stripping the anchor leaves a space before the closing parenthesis
    # (no/lov/2018-06-15-44 § 1 first paragraph).
    assert normalize_no_comparison_text("(forordning (EU) nr. 910/2014 ) om elektronisk") == (
        "(forordning (EU) nr. 910/2014) om elektronisk"
    )


def test_normalize_no_comparison_text_close_paren_keeps_adjacent_wording_distinct() -> None:
    # Boundedness. A pair differing ONLY inside the span this rule rewrites is
    # unsatisfiable for a pure whitespace-deletion rule: every such pair
    # normalizes equal by construction, which is the point of the rule. The
    # achievable form is a pair differing in the span an OVER-matching variant
    # would reach, so the assertions below fail if the rule widens.
    #
    # First pair: the token immediately before the space. Kills variants that
    # eat a word/non-space run (``\S+\s+\)``, ``\w+\s+\)``) by collapsing two
    # different cross-references into one comparison string.
    assert normalize_no_comparison_text("(forordning (EU) nr. 910/2014 ) om elektronisk") != (
        normalize_no_comparison_text("(forordning (EU) nr. 910/2015 ) om elektronisk")
    )
    assert normalize_no_comparison_text("(forordning (EU) nr. 910/2015 ) om elektronisk") == (
        "(forordning (EU) nr. 910/2015) om elektronisk"
    )
    # Second pair: a trailing footnote digit inside the parenthesis. Kills the
    # digit-swallowing variant (``\s+\d*\s*\)``) — the findings-ledger F-05
    # shape a spike measured masking real cross-reference differences. The
    # digit must survive normalization; only the whitespace is presentation
    # residue.
    assert normalize_no_comparison_text("(forordning (EU) nr. 910/2014 3 ) om elektronisk") != (
        normalize_no_comparison_text("(forordning (EU) nr. 910/2014 ) om elektronisk")
    )
    assert normalize_no_comparison_text("(forordning (EU) nr. 910/2014 3 ) om elektronisk") == (
        "(forordning (EU) nr. 910/2014 3) om elektronisk"
    )


def test_normalize_no_comparison_text_strips_inline_footnote_marker() -> None:
    # The rule's genuine corpus case: the published-side extraction leaves the
    # commencement formula's superscript footnote reference inline, next to the
    # word it annotates (23 of the 56 candidate laws carry this shape).
    assert normalize_no_comparison_text("Loven gjelder fra den tid 1 Kongen bestemmer.") == (
        "Loven gjelder fra den tid Kongen bestemmer."
    )
    # Nynorsk and the non-"Kongen bestemmer" continuation of the same formula.
    assert normalize_no_comparison_text("Lova gjeld frå den tida 1 Kongen fastset.") == (
        "Lova gjeld frå den tida Kongen fastset."
    )
    assert normalize_no_comparison_text(
        "Loven gjelder fra den tid 1 Roma-vedtektene trer i kraft for Norge."
    ) == "Loven gjelder fra den tid Roma-vedtektene trer i kraft for Norge."


def test_normalize_no_comparison_text_inline_footnote_marker_keeps_structural_numbering() -> None:
    # Boundedness (W-16). The rule used to be
    # ``(?<=[a-zæøå])\s+\d+\s+(?=[A-ZÆØÅ])``, which deleted the number out of
    # every "Kapittel N Tittel" heading on BOTH sides of the comparison, so two
    # genuinely different headings compared EQUAL — the masking mode the
    # findings-ledger F-05 entry documents as forbidden for this lane. A
    # measured probe over the 56 candidate laws found 487 structural headings
    # and 15 other content digits altered against 49 genuine markers; the
    # assertions below fail if any of those bounds is dropped again.
    assert normalize_no_comparison_text("Kapittel 2 X") != normalize_no_comparison_text("Kapittel 3 X")
    assert normalize_no_comparison_text("Kapittel 1 Innledende bestemmelser") == (
        "Kapittel 1 Innledende bestemmelser"
    )
    assert normalize_no_comparison_text("Avsnitt 2 Alminnelige regler") == "Avsnitt 2 Alminnelige regler"
    # Rule-unit level: the regex itself must not fire on any of the measured
    # false-positive shapes, and must still fire on the genuine one.
    assert _NO_VERIFY_INLINE_FOOTNOTE_RE.search("Loven gjelder fra den tid 1 Kongen bestemmer.")
    for untouched in (
        "Kapittel 2 X",  # structural heading numbering (487 corpus alterations)
        "Avsnitt 2 Alminnelige regler",  # ditto
        "sjøloven kapittel 6 A. Politiets kompetanse",  # chapter cross-reference
        "§§ 5 A-2 og 5 A-3 gjelder ikke",  # section cross-reference
        "oppgradert til å yte minst 100 Mbit/s nedlastningshastighet.",  # quantity
        "General Assembly resolution 47/111 of 16 December 1992",  # date in an annex
    ):
        assert not _NO_VERIFY_INLINE_FOOTNOTE_RE.search(untouched), untouched
        assert normalize_no_comparison_text(untouched) == untouched


def test_normalize_no_comparison_text_keeps_marker_before_terminal_period() -> None:
    # The findings-ledger F-05 shape — the marker sits BEFORE the period, with
    # only a word to its left ("no/lov/2007-06-29-89" §6(1),
    # "no/lov/2017-05-22-28" §5(2)). It is indistinguishable from an ordinary
    # cross-reference ("i samsvar med artikkel 12."), so the lane leaves it as
    # recorded noise; no footnote rule may start eating it.
    assert normalize_no_comparison_text("Loven trer i kraft fra den tid Kongen bestemmer 1.") == (
        "Loven trer i kraft fra den tid Kongen bestemmer 1."
    )
    assert normalize_no_comparison_text("i samsvar med artikkel 12.") != (
        normalize_no_comparison_text("i samsvar med artikkel 13.")
    )


def test_normalize_no_comparison_text_strips_trailing_footnote_marker() -> None:
    assert normalize_no_comparison_text("Loven trer i kraft fra den tid Kongen bestemmer. 1") == (
        "Loven trer i kraft fra den tid Kongen bestemmer."
    )


def test_irnode_to_no_comparison_text_ignores_direct_section_headings() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="2-1",
        children=(IRNode(kind=IRNodeKind.HEADING, text="Skatteplikt for øverste morselskap"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Operativ tekst."),),
    )

    assert irnode_to_no_comparison_text(section) == "Operativ tekst."
    assert irnode_to_text(section) == "Skatteplikt for øverste morselskap Operativ tekst."


def test_irnode_to_no_comparison_text_combines_subsection_text_with_nested_items() -> None:
    subsection = IRNode(
        kind=IRNodeKind.SUBSECTION,
        label="5",
        text="forutsatt at",
        children=(IRNode(kind=IRNodeKind.ITEM, label="a", text="første vilkår"),
            IRNode(kind=IRNodeKind.ITEM, label="b", text="andre vilkår"),),
    )

    assert irnode_to_no_comparison_text(subsection) == "forutsatt at første vilkår andre vilkår"


def test_normalize_no_compare_tree_flattens_sentence_only_subsection() -> None:
    subsection = IRNode(
        kind=IRNodeKind.SUBSECTION,
        label="2",
        children=(IRNode(kind=IRNodeKind.SENTENCE, label="1", text="Første punktum."),
            IRNode(kind=IRNodeKind.SENTENCE, label="2", text="Andre punktum."),),
    )

    normalized = _normalize_no_compare_tree(subsection)

    assert normalized.kind is IRNodeKind.SUBSECTION
    assert normalized.label == "2"
    assert normalized.text == "Første punktum. Andre punktum."
    assert normalized.children == ()


def test_normalize_no_compare_tree_takes_same_branch_for_str_kind() -> None:
    # Parse paths can assign a plain str kind (e.g. "subsection"/"sentence")
    # instead of the IRNodeKind enum. The compare-tree normalizer must take the
    # same branch for the str case as for the equivalent enum case; otherwise
    # `kind is IRNodeKind.X` silently evaluates False and the sentence-only
    # collapse is skipped, mis-normalizing the compare tree.
    enum_subsection = IRNode(
        kind=IRNodeKind.SUBSECTION,
        label="2",
        children=(
            IRNode(kind=IRNodeKind.SENTENCE, label="1", text="Første punktum."),
            IRNode(kind=IRNodeKind.SENTENCE, label="2", text="Andre punktum."),
        ),
    )
    str_subsection = IRNode(
        kind=cast(Any, "subsection"),
        label="2",
        children=(
            IRNode(kind=cast(Any, "sentence"), label="1", text="Første punktum."),
            IRNode(kind=cast(Any, "sentence"), label="2", text="Andre punktum."),
        ),
    )

    enum_normalized = _normalize_no_compare_tree(enum_subsection)
    str_normalized = _normalize_no_compare_tree(str_subsection)

    # The str case must collapse its sentence children into parent text exactly
    # like the enum case did, rather than leaving them as separate children.
    assert _no_kind_value(str_normalized.kind) == _no_kind_value(enum_normalized.kind)
    assert str_normalized.text == enum_normalized.text == "Første punktum. Andre punktum."
    assert str_normalized.children == enum_normalized.children == ()


def test_normalize_no_compare_tree_flattens_sentence_prefix_but_keeps_items() -> None:
    subsection = IRNode(
        kind=IRNodeKind.SUBSECTION,
        label="2",
        children=(IRNode(kind=IRNodeKind.SENTENCE, label="1", text="Lead sentence."),
            IRNode(kind=IRNodeKind.ITEM, label="a", text="første"),
            IRNode(kind=IRNodeKind.ITEM, label="b", text="andre"),),
    )

    normalized = _normalize_no_compare_tree(subsection)

    assert normalized.text == "Lead sentence."
    assert [(child.kind, child.label, child.text) for child in normalized.children] == [
        (IRNodeKind.ITEM, "a", "første"),
        (IRNodeKind.ITEM, "b", "andre"),
    ]


def test_normalize_no_compare_tree_trims_inline_nested_item_duplication() -> None:
    item = IRNode(
        kind=IRNodeKind.ITEM,
        label="b",
        text=(
            "eieren er en fysisk person som er skattemessig bosatt i samme jurisdiksjon som "
            "det øverste morselskapet, og har en direkte eierinteresse som gir rett til "
            "maksimalt 5 prosent av fortjenesten og eiendelene til det øverste morselskapet, eller"
        ),
        children=(IRNode(
                kind=IRNodeKind.ITEM,
                label="1",
                text="er skattemessig bosatt i samme jurisdiksjon som det øverste morselskapet, og",
            ),
            IRNode(
                kind=IRNodeKind.ITEM,
                label="2",
                text=(
                    "har en direkte eierinteresse som gir rett til maksimalt 5 prosent av "
                    "fortjenesten og eiendelene til det øverste morselskapet, eller"
                ),
            ),),
    )

    normalized = _normalize_no_compare_tree(item)

    assert normalized.text == "eieren er en fysisk person som"
    assert [(child.kind, child.label, child.text) for child in normalized.children] == [
        (
            IRNodeKind.ITEM,
            "1",
            "er skattemessig bosatt i samme jurisdiksjon som det øverste morselskapet, og",
        ),
        (
            IRNodeKind.ITEM,
            "2",
            "har en direkte eierinteresse som gir rett til maksimalt 5 prosent av fortjenesten og eiendelene til det øverste morselskapet, eller",
        ),
    ]


def test_normalize_no_compare_tree_preserves_current_definition_list_items() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="2",
        children=(IRNode(kind=IRNodeKind.HEADING, text="Begreper"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="I denne lov forstås med:",
                children=(IRNode(kind=IRNodeKind.ITEM, label="1", text="Betalingsmidler: Kontanter."),
                    IRNode(kind=IRNodeKind.ITEM, label="2", text="Valutaveksling: Kjøp og salg."),),
            ),),
    )

    normalized = _normalize_no_compare_tree(section)
    subsection = next(child for child in normalized.children if child.kind is IRNodeKind.SUBSECTION)
    assert subsection.text == "I denne lov forstås med:"
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.ITEM, "1", "Betalingsmidler: Kontanter."),
        (IRNodeKind.ITEM, "2", "Valutaveksling: Kjøp og salg."),
    ]


def test_normalize_no_compare_tree_rebuilds_split_definition_pairs_as_items() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="2",
        children=(IRNode(kind=IRNodeKind.HEADING, text="Begreper"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="I denne lov forstås med:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="Betalingsmidler:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="Kontanter."),
            IRNode(kind=IRNodeKind.SUBSECTION, label="4", text="Valutaveksling:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="5", text="Kjøp og salg."),),
    )

    normalized = _normalize_no_compare_tree(section)
    subsection = next(child for child in normalized.children if child.kind is IRNodeKind.SUBSECTION)
    assert subsection.text == "I denne lov forstås med:"
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.ITEM, "1", "Betalingsmidler: Kontanter."),
        (IRNodeKind.ITEM, "2", "Valutaveksling: Kjøp og salg."),
    ]


def test_normalize_no_compare_tree_blanks_repealed_shell_text() -> None:
    section = IRNode(kind=IRNodeKind.SECTION, label="2-6", text="§ 2-6. (Opphevet)")

    normalized = _normalize_no_compare_tree(section)

    assert normalized.text == ""


def test_normalize_no_compare_tree_collapses_other_laws_detail_section() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="22",
        children=(IRNode(kind=IRNodeKind.HEADING, text="(endringer i andre lover)"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="I lov 13. mars 1981 nr. 6 om vern mot forurensning og om avfall gjøres følgende endringer: – – –",
            ),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="§ 11 nytt annet ledd skal lyde:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="Kvotepliktig etter klimakvoteloven § 4 ..."),),
    )

    normalized = _normalize_no_compare_tree(section)

    assert [(child.kind, child.label, child.text) for child in normalized.children] == [
        (IRNodeKind.HEADING, None, "(endringer i andre lover)"),
        (
            IRNodeKind.SUBSECTION,
            "1",
            "I lov 13. mars 1981 nr. 6 om vern mot forurensning og om avfall gjøres følgende endringer:",
        ),
    ]


def test_normalize_no_compare_tree_records_other_laws_projection() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="22",
        children=(IRNode(kind=IRNodeKind.HEADING, text="Endringer i andre lover"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="Fra den tid loven trer i kraft, gjøres følgende endringer i andre lover: – – –",
            ),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="1. I lov 17. juli 1998 nr. 61 ..."),),
    )
    projections = []

    _normalize_no_compare_tree(
        section,
        projections_out=projections,
        surface="current",
        path=(("section", "22"),),
    )

    assert [projection.rule_id for projection in projections] == [NO_VERIFY_COMPARE_OTHER_LAWS_CONTEXT_SUPPRESSED]
    projection = projections[0]
    assert projection.surface == "current"
    assert projection.address == (("section", "22"),)
    assert projection.before_kind == "section"
    assert projection.before_label == "22"
    assert projection.before_child_count == 3
    assert projection.after_child_count == 2
    assert projection.to_dict()["family"] == "editorial_projection"


def test_normalize_no_compare_tree_does_not_record_projection_for_plain_section() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="1",
        children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Plain operative text."),),
    )
    projections = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "1"),))

    assert projections == []


def test_normalize_no_compare_tree_records_repealed_shell_blank_projection() -> None:
    # §2.9 finding-assertion: a repealed-shell section body that normalizes to
    # empty emits the no_verify.compare_repealed_shell_blanked projection, with
    # before/after evidence. The pure-effect test
    # (test_normalize_no_compare_tree_blanks_repealed_shell_text) pins the
    # cosmetic outcome; this one pins the *rule_id* emission so a regression
    # that silently drops the projection (or fires a different one) is caught.
    section = IRNode(kind=IRNodeKind.SECTION, label="2-6", text="§ 2-6. (Opphevet)")
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "2-6"),))

    assert [p.rule_id for p in projections] == [NO_VERIFY_COMPARE_REPEALED_SHELL_BLANKED]
    assert projections[0].surface == "current"
    assert projections[0].before_text == "§ 2-6. (Opphevet)"
    assert projections[0].after_text == ""


def test_normalize_no_compare_tree_records_sentence_children_collapse_projection() -> None:
    # §2.9 finding-assertion: a subsection whose only children are sentence
    # nodes emits no_verify.compare_sentence_children_collapsed when those
    # children are folded into the parent's text.
    subsection = IRNode(
        kind=IRNodeKind.SUBSECTION,
        label="1",
        children=(
            IRNode(kind=IRNodeKind.SENTENCE, label="a", text="Første punktum."),
            IRNode(kind=IRNodeKind.SENTENCE, label="b", text="Andre punktum."),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(subsection, projections_out=projections, surface="replay", path=(("section", "1"), ("subsection", "1")))

    assert [p.rule_id for p in projections] == [NO_VERIFY_COMPARE_SENTENCE_CHILDREN_COLLAPSED]
    assert projections[0].after_child_count == 0
    assert "Første punktum." in projections[0].after_text
    assert "Andre punktum." in projections[0].after_text


def test_normalize_no_compare_tree_records_nested_item_tail_suppression_projection() -> None:
    # §2.9 finding-assertion: an item whose text duplicates the prefix of a
    # nested item child emits no_verify.compare_nested_item_tail_suppressed.
    # Mirrors the trigger shape in
    # test_normalize_no_compare_tree_trims_inline_nested_item_duplication;
    # here we pin the *rule_id* emission rather than the cosmetic text trim.
    item = IRNode(
        kind=IRNodeKind.ITEM,
        label="b",
        text=(
            "eieren er en fysisk person som er skattemessig bosatt i samme jurisdiksjon som "
            "det øverste morselskapet, og har en direkte eierinteresse som gir rett til "
            "maksimalt 5 prosent av fortjenesten og eiendelene til det øverste morselskapet, eller"
        ),
        children=(
            IRNode(
                kind=IRNodeKind.ITEM,
                label="1",
                text="er skattemessig bosatt i samme jurisdiksjon som det øverste morselskapet, og",
            ),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(item, projections_out=projections, surface="current", path=(("section", "1"), ("item", "b")))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_NESTED_ITEM_TAIL_SUPPRESSED in rule_ids
    projection = next(p for p in projections if p.rule_id == NO_VERIFY_COMPARE_NESTED_ITEM_TAIL_SUPPRESSED)
    assert projection.before_text.startswith("eieren er en fysisk person som")
    assert projection.after_text == "eieren er en fysisk person som"


def test_normalize_no_compare_tree_records_self_section_shell_blank_projection() -> None:
    # §2.9 finding-assertion: a section whose text is an "I § N nr. M ..."
    # self-section lead shell emits no_verify.compare_self_section_shell_blanked
    # along with the structural blanking.
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="42",
        text="I § 42 nr. 44 om endringer i skattebetalingsloven skal nye endringer lyde:",
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "42"),))

    assert [p.rule_id for p in projections] == [NO_VERIFY_COMPARE_SELF_SECTION_SHELL_BLANKED]
    assert projections[0].after_text == ""


def test_normalize_no_compare_tree_records_contingent_other_laws_placeholder_projection() -> None:
    # §2.9 finding-assertion: a section whose only substantive content is the
    # "Fra tid Kongen bestemmer, gjøres følgende endringer i andre lover"
    # contingent placeholder emits
    # no_verify.compare_contingent_other_laws_placeholder_suppressed.
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="42",
        children=(
            IRNode(kind=IRNodeKind.HEADING, text="Endringer i andre lover"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="Fra den tid Kongen fastsetter, gjøres følgende endringer i andre lover:",
            ),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "42"),))

    assert [p.rule_id for p in projections] == [NO_VERIFY_COMPARE_CONTINGENT_OTHER_LAWS_PLACEHOLDER_SUPPRESSED]
    assert projections[0].after_text == ""
    assert projections[0].after_child_count == 0


def test_normalize_no_compare_tree_records_definition_subsection_pairs_collapse_projection() -> None:
    # §2.9 finding-assertion: a section where the first subsection ends with
    # "forstås med:" and the remaining subsections are term/value pairs that
    # chain into a single definition list collapses them under
    # no_verify.compare_definition_subsection_pairs_collapsed.
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="3",
        children=(
            IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Med binær option forstås med:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="kjøpsavtale:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="kjøp av finansielt instrument til fast pris"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="4", text="salgsavtale:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="5", text="salg av finansielt instrument til fast pris"),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="replay", path=(("section", "3"),))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_DEFINITION_SUBSECTION_PAIRS_COLLAPSED in rule_ids
    projection = next(p for p in projections if p.rule_id == NO_VERIFY_COMPARE_DEFINITION_SUBSECTION_PAIRS_COLLAPSED)
    assert projection.after_child_count == 1


# --- §2.9 negative tests for the no_verify.compare_* projection family -----
#
# Each test asserts the rule_id DOES NOT fire on a nearby valid shape that
# lacks the rule's specific trigger condition. A regression that lowers the
# trigger threshold (and silently misclassifies valid operative text as an
# editorial projection) would now be caught.


def test_normalize_no_compare_tree_does_not_blank_operative_section_text() -> None:
    # Negative for no_verify.compare_repealed_shell_blanked: a section whose
    # text normalizes to non-empty operative prose (not a "(Opphevet)"
    # repealed shell) must not be blanked or emit the projection.
    section = IRNode(kind=IRNodeKind.SECTION, label="2-6", text="§ 2-6. Helsedeleningstjenester skal gis av regionen.")
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "2-6"),))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_REPEALED_SHELL_BLANKED not in rule_ids


def test_normalize_no_compare_tree_does_not_collapse_subsection_without_sentence_children() -> None:
    # Negative for no_verify.compare_sentence_children_collapsed: a
    # subsection with no SENTENCE children has nothing to collapse into the
    # parent text — the projection must not fire.
    subsection = IRNode(
        kind=IRNodeKind.SUBSECTION,
        label="1",
        text="Loven gjelder omraadet.",
        children=(
            IRNode(kind=IRNodeKind.ITEM, label="a", text="Forste punkt."),
            IRNode(kind=IRNodeKind.ITEM, label="b", text="Andre punkt."),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(subsection, projections_out=projections, surface="current", path=(("section", "1"), ("subsection", "1")))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_SENTENCE_CHILDREN_COLLAPSED not in rule_ids


def test_normalize_no_compare_tree_does_not_suppress_nested_item_tail_when_text_is_disjoint() -> None:
    # Negative for no_verify.compare_nested_item_tail_suppressed: an ITEM
    # with nested item children, but whose parent text does NOT contain any
    # child's text as a substring, has no duplication to suppress.
    item = IRNode(
        kind=IRNodeKind.ITEM,
        label="b",
        text="Heimel for vedtak om prising av statleg teneste.",
        children=(
            IRNode(kind=IRNodeKind.ITEM, label="1", text="Prisfast-setting skjer kvart ar."),
            IRNode(kind=IRNodeKind.ITEM, label="2", text="Klage vert handsama av departementet."),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(item, projections_out=projections, surface="current", path=(("section", "1"), ("item", "b")))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_NESTED_ITEM_TAIL_SUPPRESSED not in rule_ids


def test_normalize_no_compare_tree_does_not_blank_non_shell_section_lead() -> None:
    # Negative for no_verify.compare_self_section_shell_blanked: a section
    # whose text begins with "I lov …" (the citation form) rather than "I § N
    # nr. M …" (the self-section shell form) must NOT fire the shell-blanking
    # projection. The two forms share the "I " lead prefix but only the
    # section-shell regex anchored on § matches the rule's trigger.
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="1",
        text="I lov 17. juni 2005 nr. 62 om arbeidsmiljøloven gjøres følgende endringer:",
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "1"),))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_SELF_SECTION_SHELL_BLANKED not in rule_ids


def test_normalize_no_compare_tree_does_not_suppress_non_contingent_other_laws_lead() -> None:
    # Negative for no_verify.compare_contingent_other_laws_placeholder_
    # suppressed: a section with the "Endringer i andre lover" heading and
    # a subsection whose wording matches the dated-commencement shape — NOT
    # the "Kongen bestemmer / Kongen fastsetter" contingent shape — must
    # not fire the contingent suppression. The contingent regex requires
    # both the "Fra|Frå|Med virkning fra den tid" lead AND a "Kongen
    # bestemmer|Kongen fastsetter" royal-decree phrase.
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="42",
        children=(
            IRNode(kind=IRNodeKind.HEADING, text="Endringer i andre lover"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="Fra den tid loven trer i kraft, gjøres følgende endringer i andre lover:",
            ),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "42"),))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_CONTINGENT_OTHER_LAWS_PLACEHOLDER_SUPPRESSED not in rule_ids


def test_normalize_no_compare_tree_does_not_collapse_pairs_when_intro_does_not_end_in_definition_marker() -> None:
    # Negative for no_verify.compare_definition_subsection_pairs_collapsed:
    # a section with the SAME term/value-pair structure (2 subsections after
    # intro), but whose first subsection does NOT end in "forstås med:" — so
    # it is not a definition-introduction shape — must not fire the collapse.
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="3",
        children=(
            IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Seksjonen omhandlar folgende to omgrep:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="krav:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="dokumentert rapportering"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="4", text="ansvar:"),
            IRNode(kind=IRNodeKind.SUBSECTION, label="5", text="eigedomsskatt"),
        ),
    )
    projections: list[Any] = []

    _normalize_no_compare_tree(section, projections_out=projections, surface="current", path=(("section", "3"),))

    rule_ids = [p.rule_id for p in projections]
    assert NO_VERIFY_COMPARE_DEFINITION_SUBSECTION_PAIRS_COLLAPSED not in rule_ids


def test_normalize_no_compare_tree_collapses_other_laws_detail_section_without_heading() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="11",
        children=(IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="Med virkning fra den tid loven trer i kraft, gjøres følgende endringer i andre lover:",
            ),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="§ 25 annet ledd tredje og fjerde punktum oppheves."),
            IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="2. I lov 24. mai 1929 nr. 4 ..."),),
    )

    normalized = _normalize_no_compare_tree(section)

    assert [(child.kind, child.label, child.text) for child in normalized.children] == [
        (
            IRNodeKind.SUBSECTION,
            "1",
            "Med virkning fra den tid loven trer i kraft, gjøres følgende endringer i andre lover:",
        ),
    ]


def test_normalize_no_compare_tree_collapses_nynorsk_other_laws_detail_section() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="22",
        children=(IRNode(kind=IRNodeKind.HEADING, text="Endringar i andre lover"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="Frå den tida lova tek til å gjelde, skal desse endringane gjerast i andre lover: – – –",
            ),
            IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="1. I lov 17. juli 1998 nr. 61 ..."),
            IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="§ 2-5 overskrifta skal lyde:"),),
    )

    normalized = _normalize_no_compare_tree(section)

    assert [(child.kind, child.label, child.text) for child in normalized.children] == [
        (IRNodeKind.HEADING, None, "Endringar i andre lover"),
        (
            IRNodeKind.SUBSECTION,
            "1",
            "Frå den tida lova tek til å gjelde, skal desse endringane gjerast i andre lover:",
        ),
    ]


def test_normalize_no_compare_tree_collapses_heading_plus_self_section_shell() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="41",
        text=(
            "I § 41 Endringer i tvangsfullbyrdelsesloven skal "
            "tvangsfullbyrdelsesloven § 2-15 tredje ledd passusen "
            "«§§ 7-23, 7-24 og 7-27» erstattes av passusen «§§ 7-23 og 7-27»."
        ),
        children=(IRNode(kind=IRNodeKind.HEADING, text="Endringer i tvangsfullbyrdelsesloven"),),
    )

    normalized = _normalize_no_compare_tree(section)

    assert normalized.text == ""
    assert [(child.kind, child.label, child.text) for child in normalized.children] == [
        (IRNodeKind.HEADING, None, "Endringer i tvangsfullbyrdelsesloven"),
    ]


def test_normalize_no_compare_tree_blanks_contingent_other_laws_placeholder_section() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="42",
        children=(IRNode(kind=IRNodeKind.HEADING, text="Endringer i andre lover"),
            IRNode(
                kind=IRNodeKind.SUBSECTION,
                label="1",
                text="Fra den tid Kongen fastsetter, gjøres følgende endringer i andre lover:",
            ),),
    )

    normalized = _normalize_no_compare_tree(section)

    assert normalized.text == ""
    assert normalized.children == ()


def test_normalize_no_compare_tree_blanks_self_section_other_laws_lead_shell() -> None:
    section = IRNode(
        kind=IRNodeKind.SECTION,
        label="42",
        text="I § 42 nr. 44 om endringer i skattebetalingsloven skal nye endringer lyde:",
    )

    normalized = _normalize_no_compare_tree(section)

    assert normalized.text == ""
    assert normalized.children == ()


def test_verify_consistency_accepts_no_text_normalizer() -> None:
    addr = LegalAddress(path=(("section", "1"), ("item", "a")))
    ops_tl = {
        addr: ProvisionTimeline(
            address=addr,
            versions=[
                ProvisionVersion(
                    effective="0000-00-00",
                    content=IRNode(kind=IRNodeKind.ITEM, label="a", text="§ 1-2, kapittel 7."),
                )
            ],
        )
    }
    oracle = IRStatute(
        statute_id="no/test",
        title="Test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(IRNode(kind=IRNodeKind.ITEM, label="a", text="§ 1-2 , kapittel 7 ."),),
                ),),
        ),
    )
    con_tl = ingest_consolidated(oracle, as_of="0000-00-00")

    raw_divs = verify_consistency(
        ops_tl,
        con_tl,
        as_of="0000-00-00",
        irnode_to_text=irnode_to_text,
    )
    assert len(raw_divs) == 2

    norm_divs = verify_consistency(
        ops_tl,
        con_tl,
        as_of="0000-00-00",
        irnode_to_text=irnode_to_text,
        text_normalizer=normalize_no_comparison_text,
        missing_equals_empty=True,
    )
    assert len(norm_divs) == 1
    assert norm_divs[0].address.path == (("section", "1"),)


def test_verify_consistency_accepts_missing_equals_empty_for_blank_norway_items() -> None:
    oracle = IRStatute(
        statute_id="no/test",
        title="Test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(IRNode(kind=IRNodeKind.ITEM, label="a", text=""),),
                ),),
        ),
    )
    con_tl = ingest_consolidated(oracle, as_of="0000-00-00")

    raw_divs = verify_consistency(
        {},
        con_tl,
        as_of="0000-00-00",
        irnode_to_text=irnode_to_text,
        text_normalizer=normalize_no_comparison_text,
    )
    assert len(raw_divs) == 2

    norm_divs = verify_consistency(
        {},
        con_tl,
        as_of="0000-00-00",
        irnode_to_text=irnode_to_text,
        text_normalizer=normalize_no_comparison_text,
        missing_equals_empty=True,
    )
    assert norm_divs == []


def test_primary_divergences_suppresses_chapter_only_relocation_pairs() -> None:
    ops = IRStatute(
        statute_id="no/test",
        title="Replay",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="2",
                    children=(IRNode(
                            kind=IRNodeKind.SECTION,
                            label="6",
                            children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Samme tekst."),),
                        ),),
                ),),
        ),
    )
    oracle = IRStatute(
        statute_id="no/test",
        title="Current",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="1",
                    children=(IRNode(
                            kind=IRNodeKind.SECTION,
                            label="6",
                            children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Samme tekst."),),
                        ),),
                ),),
        ),
    )

    raw_divs = verify_consistency(
        ingest_consolidated(ops, as_of="0000-00-00"),
        ingest_consolidated(oracle, as_of="0000-00-00"),
        as_of="0000-00-00",
        irnode_to_text=irnode_to_no_comparison_text,
        text_normalizer=normalize_no_comparison_text,
        missing_equals_empty=True,
    )

    from lawvm.norway.verify import _primary_divergences

    assert len(raw_divs) >= 4
    assert _primary_divergences(raw_divs) == []
    partition = _partition_primary_divergences(raw_divs)
    filtered_rule_ids = {row.rule_id for row in partition.filtered}
    assert "no_verify.prefix_descendant_suppressed" in filtered_rule_ids
    assert "no_verify.chapter_relocation_pair" in filtered_rule_ids


def test_primary_divergence_partition_records_prefix_suppression() -> None:
    parent = ConsistencyDivergence(
        address=LegalAddress(path=(("section", "1"),)),
        divergence_type="MISMATCH",
        ops_text="Parent replay",
        consolidated_text="Parent current",
    )
    child = ConsistencyDivergence(
        address=LegalAddress(path=(("section", "1"), ("subsection", "1"))),
        divergence_type="MISMATCH",
        ops_text="Child replay",
        consolidated_text="Child current",
    )

    partition = _partition_primary_divergences([parent, child])

    assert partition.primary == (child,)
    assert len(partition.filtered) == 1
    assert partition.filtered[0].divergence == parent
    assert partition.filtered[0].rule_id == "no_verify.prefix_descendant_suppressed"


def test_primary_divergence_partition_does_not_suppress_sibling_paths() -> None:
    # §2.9 paired negative for no_verify.prefix_descendant_suppressed:
    # two divergences at sibling paths (neither is a strict prefix of the
    # other) must both remain primary — no suppression fires. A regression
    # that confused "sibling" with "parent-of" (e.g. via path label equality
    # alone, ignoring the prefix structure) would now silently suppress
    # one of them, masking a genuine divergence.
    left = ConsistencyDivergence(
        address=LegalAddress(path=(("section", "1"), ("subsection", "1"))),
        divergence_type="MISMATCH",
        ops_text="ops-1",
        consolidated_text="cur-1",
    )
    right = ConsistencyDivergence(
        address=LegalAddress(path=(("section", "1"), ("subsection", "2"))),
        divergence_type="MISMATCH",
        ops_text="ops-2",
        consolidated_text="cur-2",
    )

    partition = _partition_primary_divergences([left, right])

    assert partition.primary == (left, right)
    assert partition.filtered == ()
    # Belt-and-suspenders: the explicit rule_id is absent from any receipt.
    assert all(
        row.rule_id != "no_verify.prefix_descendant_suppressed"
        for row in partition.filtered
    )


def test_primary_divergence_partition_does_not_pair_divergences_with_different_text() -> None:
    # §2.9 paired negative for no_verify.chapter_relocation_pair: two
    # divergences at different chapter paths but with DIFFERENT normalized
    # text are not a relocation of the same provision — they are two distinct
    # mismatches. A regression that paired paths-only (ignoring the
    # equality-on-normalized-text requirement in _is_chapter_relocation_pair)
    # would have silently suppressed both.
    missing_in_replay = ConsistencyDivergence(
        address=LegalAddress(
            path=(("chapter", "1"), ("section", "5"))
        ),
        divergence_type="OPS_MISSING",
        ops_text="Lovens formål er å sikre informative priser.",
        consolidated_text="",
    )
    present_only_in_current = ConsistencyDivergence(
        address=LegalAddress(
            path=(("chapter", "2"), ("section", "5"))
        ),
        divergence_type="CONSOLIDATED_MISSING",
        ops_text="",
        consolidated_text="Et heilt anna formål som ikkje er ei omplassering.",
    )

    partition = _partition_primary_divergences([missing_in_replay, present_only_in_current])

    # Both divergences remain primary; no relocation pair is filtered.
    assert len(partition.primary) == 2
    assert len(partition.filtered) == 0
    assert all(
        row.rule_id != "no_verify.chapter_relocation_pair" for row in partition.filtered
    )


def test_primary_divergence_partition_pairs_annex_prefixed_section_labels() -> None:
    # Synthetic positive for no_verify.annex_prefixed_relocation_pair: two
    # byte-identical-text divergences whose non-container paths differ only
    # by the Lovdata ``v22c/`` annex-token prefix on the section label pair
    # under the new rule, NOT under the chapter_relocation_pair rule. Mirrors
    # the SCE-loven shape on no/lov/2006-06-30-50 chapter I/a1.
    missing_in_replay = ConsistencyDivergence(
        address=LegalAddress(
            path=(("chapter", "1"), ("chapter", "I"), ("section", "a1"), ("subsection", "1"))
        ),
        divergence_type="OPS_MISSING",
        ops_text="Det kan stiftes samvirkeforetak på Fellesskapets territorium.",
        consolidated_text="",
    )
    present_only_in_current = ConsistencyDivergence(
        address=LegalAddress(
            path=(
                ("chapter", "v22c"),
                ("chapter", "I"),
                ("section", "v22c/a1"),
                ("subsection", "1"),
            )
        ),
        divergence_type="CONSOLIDATED_MISSING",
        ops_text="",
        consolidated_text="Det kan stiftes samvirkeforetak på Fellesskapets territorium.",
    )

    partition = _partition_primary_divergences([missing_in_replay, present_only_in_current])

    # Both divergences leave the primary surface; both emit a filtered receipt
    # under the new annex-prefix rule (§1.8 conservation: each suppressed
    # divergence is owned by a typed receipt, never silently dropped).
    assert partition.primary == ()
    assert len(partition.filtered) == 2
    assert all(
        row.rule_id == "no_verify.annex_prefixed_relocation_pair" for row in partition.filtered
    )
    # Disjointness: the annex-prefix rule owns this case; the chapter-only
    # relocation rule does NOT also fire on the same pair.
    assert all(
        row.rule_id != "no_verify.chapter_relocation_pair" for row in partition.filtered
    )


def test_primary_divergence_partition_does_not_pair_annex_prefix_when_text_differs() -> None:
    # §2.9 paired negative for no_verify.annex_prefixed_relocation_pair: two
    # divergences at the annex-prefixed path shape but with DIFFERENT text are
    # not an annex-encoded relocation — they are two distinct mismatches and
    # the residual pair (Lovdata ``[ES]`` annotation drift) belongs to the
    # cross-act-placement frontier as an owned claim, not a code fix. A
    # regression that paired on path shape alone (ignoring the
    # equality-on-normalized-text requirement in _is_annex_prefixed_
    # relocation_pair) would have silently suppressed both real divergences.
    missing_in_replay = ConsistencyDivergence(
        address=LegalAddress(
            path=(("chapter", "1"), ("chapter", "I"), ("section", "a1"), ("subsection", "1"))
        ),
        divergence_type="OPS_MISSING",
        ops_text="Det kan stiftes samvirkeforetak på Fellesskapets territorium.",
        consolidated_text="",
    )
    present_only_in_current = ConsistencyDivergence(
        address=LegalAddress(
            path=(
                ("chapter", "v22c"),
                ("chapter", "I"),
                ("section", "v22c/a1"),
                ("subsection", "1"),
            )
        ),
        divergence_type="CONSOLIDATED_MISSING",
        ops_text="",
        consolidated_text=(
            "Det kan stiftes samvirkeforetak på Fellesskapets [ES] territorium "
            "i form av eit heilt anna rules-in frasedrag."
        ),
    )

    partition = _partition_primary_divergences([missing_in_replay, present_only_in_current])

    assert len(partition.primary) == 2
    assert len(partition.filtered) == 0
    assert all(
        row.rule_id != "no_verify.annex_prefixed_relocation_pair" for row in partition.filtered
    )
    assert all(
        row.rule_id != "no_verify.chapter_relocation_pair" for row in partition.filtered
    )


def test_primary_divergence_partition_does_not_fire_annex_rule_on_pure_chapter_relocation() -> None:
    # §2.9 paired negative for no_verify.annex_prefixed_relocation_pair: when
    # the section labels are byte-identical (no annex-token slash prefix on
    # either side), the pair falls through to no_verify.chapter_relocation_
    # pair — the annex-prefix rule must NOT fire on a pure chapter-only
    # relocation. A regression that conflated the two predicates would
    # mislabel the existing chapter_relocation family's canonical shape.
    missing_in_replay = ConsistencyDivergence(
        address=LegalAddress(path=(("chapter", "1"), ("section", "5"))),
        divergence_type="OPS_MISSING",
        ops_text="Lovens formål er å sikre informative priser.",
        consolidated_text="",
    )
    present_only_in_current = ConsistencyDivergence(
        address=LegalAddress(path=(("chapter", "2"), ("section", "5"))),
        divergence_type="CONSOLIDATED_MISSING",
        ops_text="",
        consolidated_text="Lovens formål er å sikre informative priser.",
    )

    partition = _partition_primary_divergences([missing_in_replay, present_only_in_current])

    # The pair is filtered — but under the chapter_relocation_pair rule,
    # NOT the annex-prefixed rule (no section-label prefix to strip).
    assert partition.primary == ()
    assert len(partition.filtered) == 2
    assert all(
        row.rule_id == "no_verify.chapter_relocation_pair" for row in partition.filtered
    )
    assert all(
        row.rule_id != "no_verify.annex_prefixed_relocation_pair" for row in partition.filtered
    )


def test_primary_divergence_partition_does_not_pair_annex_prefix_when_paths_equal() -> None:
    # §2.9 paired negative for no_verify.annex_prefixed_relocation_pair: two
    # divergences at the SAME exact address (including the same annex-token
    # section label) are NOT a relocation; they are a same-provision
    # mismatch. The ``left_path != right_path`` guard in the predicate
    # prevents a regression that would have suppressed them under the
    # annex-prefix rule when the section label happens to carry a slash.
    # Test earns its keep by using OPS_MISSING/CONSOLIDATED_MISSING types
    # — the only kinds the preceeding membership guard permits — to
    # specifically exercise the path-equality branch rather than the
    # earlier kind guard.
    same_path = (
        ("chapter", "v22c"),
        ("chapter", "I"),
        ("section", "v22c/a1"),
        ("subsection", "1"),
    )
    left = ConsistencyDivergence(
        address=LegalAddress(path=same_path),
        divergence_type="OPS_MISSING",
        ops_text="Ein paragraf om samvirke.",
        consolidated_text="",
    )
    right = ConsistencyDivergence(
        address=LegalAddress(path=same_path),
        divergence_type="CONSOLIDATED_MISSING",
        ops_text="",
        consolidated_text="Ein paragraf om samvirke.",
    )

    partition = _partition_primary_divergences([left, right])

    # Same path → no pairing fires → both remain primary.
    assert len(partition.primary) == 2
    assert len(partition.filtered) == 0
    assert all(
        row.rule_id != "no_verify.annex_prefixed_relocation_pair" for row in partition.filtered
    )


# --- W-17: annexed-instrument representation ceiling ------------------------
#
# The classifier TYPES rows; it never removes them. Every test below therefore
# also asserts that the input divergences are still divergences — a regression
# that turned the ceiling into a filter would make the three affected laws go
# spuriously consistent, exactly the masking failure F-05 forbids.


def _no_div(path, divergence_type, ops_text="", consolidated_text="") -> ConsistencyDivergence:
    return ConsistencyDivergence(
        address=LegalAddress(path=tuple(path)),
        divergence_type=divergence_type,
        ops_text=ops_text,
        consolidated_text=consolidated_text,
    )


def test_annex_ceiling_types_gdpr_annex_chapter_rows() -> None:
    # Positive, no/lov/2018-06-15-38 (personopplysningsloven): Lovdata prints
    # the whole GDPR as chapter:gdpr and duplicates the token onto the section
    # label. 714 rows of the corpus have exactly this shape.
    divergence = _no_div(
        (("chapter", "gdpr"), ("chapter", "I"), ("section", "gdpr/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="1. Denne forordning fastsetter regler om vern av fysiske personer.",
    )

    typed = classify_no_annex_ceiling([divergence])

    assert len(typed) == 1
    assert typed[0].rule_id == NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS
    assert (typed[0].annex_token, typed[0].article) == ("gdpr", "1")
    # Typed, not removed: the receipt points back at the same divergence.
    assert typed[0].divergence is divergence


def test_annex_ceiling_types_both_language_versions_of_one_convention() -> None:
    # Positive, no/lov/2017-06-16-51: the SAME convention is annexed twice,
    # bokmål under chapter:rdk (section token ``rdke``) and nynorsk under
    # chapter:rdkn (section token ``rdkn``), 102 rows each. The bokmål half is
    # why the token agreement is a shared-prefix test and not equality:
    # ``rdke`` extends ``rdk``. The nynorsk half additionally proves the
    # container step below the annex chapter may be a ``part``, not a
    # ``chapter`` — the rule only constrains the top step and the section.
    bokmal = _no_div(
        (("chapter", "rdk"), ("chapter", "I"), ("section", "rdke/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="1. In this Convention, the term «racial discrimination» shall mean …",
    )
    nynorsk = _no_div(
        (("chapter", "rdkn"), ("part", "9-1"), ("section", "rdkn/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="1. I denne konvensjonen tyder «rasediskriminering» …",
    )

    typed = classify_no_annex_ceiling([bokmal, nynorsk])

    assert [record.rule_id for record in typed] == [
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS,
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS,
    ]
    assert [record.annex_token for record in typed] == ["rdk", "rdkn"]


def test_annex_ceiling_types_both_sides_of_a_twice_addressed_instrument() -> None:
    # Positive, no/lov/2006-06-30-50 (SCE-loven): the SCE Regulation is present
    # on BOTH sides at different addresses — replay in the chapter body
    # (chapter:1/…/section:a1), published in the annex (chapter:v22c/…/
    # section:v22c/a1). The annex row is typed by address; the canonical row is
    # typed as its counterpart and carries the annex address as its witness.
    annexed = _no_div(
        (("chapter", "v22c"), ("chapter", "I"), ("section", "v22c/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="1. Det kan stiftes samvirkeforetak [EØS] på Fellesskapets territorium.",
    )
    canonical = _no_div(
        (("chapter", "1"), ("chapter", "I"), ("section", "a1"), ("subsection", "1")),
        "CONSOLIDATED_MISSING",
        ops_text="1. Det kan stiftes samvirkeforetak på Fellesskapets territorium.",
    )

    typed = classify_no_annex_ceiling([annexed, canonical])

    assert [record.rule_id for record in typed] == [
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS,
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_COUNTERPART,
    ]
    assert typed[1].witness_address == tuple(annexed.address.path)
    assert typed[1].article == "1"


def test_annex_ceiling_counterpart_covers_truncated_annex_article_tail() -> None:
    # Positive, no/lov/2006-06-30-50 Article 80: the published annex truncates
    # the Regulation's closing signature block, so replay's subsections 5-7
    # ("For Rådet" / "G. ALEMANNO" / "Formann") have no annex row at the SAME
    # normalized address — only subsection 3 does. The counterpart rule keys on
    # the witnessed ARTICLE, not the full address, so all three are typed. This
    # is the whole difference between the 1,126 an address-pairing rule reaches
    # and the 1,129 the W-6 triage measured.
    witness = _no_div(
        (("chapter", "v22c"), ("chapter", "IX"), ("section", "v22c/a80"), ("subsection", "3")),
        "OPS_MISSING",
        consolidated_text="Utferdiget i Brussel.",
    )
    tail = [
        _no_div(
            (("chapter", "1"), ("chapter", "IX"), ("section", "a80"), ("subsection", str(n))),
            "CONSOLIDATED_MISSING",
            ops_text=text,
        )
        for n, text in ((5, "For Rådet"), (6, "G. ALEMANNO"), (7, "Formann"))
    ]

    typed = classify_no_annex_ceiling([witness, *tail])

    assert len(typed) == 4
    assert [record.rule_id for record in typed[1:]] == [
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_COUNTERPART
    ] * 3


def test_annex_ceiling_does_not_type_ordinary_divergences_of_the_same_laws() -> None:
    # §2.9 paired negative: the three annex laws also carry ordinary
    # divergences, and those must stay unexplained. All three rows below are
    # real corpus rows from the very laws the ceiling covers —
    # 2018-06-15-38 §11(1) (§§ vs § § compare noise), 2017-06-16-51 §26(3)
    # (subsection-boundary shift) and 2006-06-30-50 §11a(1) (sparse source).
    # A rule that keyed on the law rather than the row would swallow them.
    rows = [
        _no_div(
            (("chapter", "3"), ("section", "11"), ("subsection", "1")),
            "MISMATCH",
            ops_text="… samt §§ 6, 7 og 9 i loven her gjelder tilsvarende.",
            consolidated_text="… samt § § 6, 7 og 9 i loven her gjelder tilsvarende.",
        ),
        _no_div(
            (("chapter", "4"), ("section", "26"), ("subsection", "3")),
            "MISMATCH",
            ops_text="Det samme gjelder arbeidsgiver i private virksomheter …",
            consolidated_text="Med ufrivillig deltidsarbeid menes deltidsarbeid …",
        ),
        _no_div(
            (("section", "11a"), ("subsection", "1")),
            "CONSOLIDATED_MISSING",
            ops_text="Departementet kan gi forskrift for å gjennomføre forpliktelser …",
        ),
    ]

    assert classify_no_annex_ceiling(rows) == ()


def test_annex_ceiling_counterpart_is_self_limiting_without_an_annex_witness() -> None:
    # §2.9 paired negative for no_verify.ceiling_annexed_instrument_counterpart:
    # an article-shaped section label alone is NOT enough. Without a row of the
    # same law at an annex address for that article number, nothing is typed —
    # so the rule can never reach a law that annexes no instrument, and it can
    # never reach an article the annex does not witness.
    orphan = _no_div(
        (("chapter", "1"), ("chapter", "I"), ("section", "a1"), ("subsection", "1")),
        "CONSOLIDATED_MISSING",
        ops_text="1. Det kan stiftes samvirkeforetak på Fellesskapets territorium.",
    )
    wrong_article = _no_div(
        (("chapter", "v22c"), ("chapter", "I"), ("section", "v22c/a2"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="2. Noe annet.",
    )

    typed = classify_no_annex_ceiling([orphan])
    assert typed == ()

    # Witnessing a DIFFERENT article does not carry the orphan either.
    typed = classify_no_annex_ceiling([orphan, wrong_article])
    assert [record.rule_id for record in typed] == [NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS]
    assert typed[0].divergence is wrong_article


def test_annex_ceiling_counterpart_does_not_explain_a_text_mismatch() -> None:
    # §2.9 paired negative: the counterpart rule explains a provision that is
    # present on ONE side only — the shape a two-address representation makes.
    # A MISMATCH at a canonical article address means the two copies of the
    # instrument disagree in WORDING, which the annex ceiling does not explain,
    # so it must stay unexplained and visible.
    witness = _no_div(
        (("chapter", "v22c"), ("chapter", "I"), ("section", "v22c/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="1. Det kan stiftes samvirkeforetak.",
    )
    wording_conflict = _no_div(
        (("chapter", "1"), ("chapter", "I"), ("section", "a1"), ("subsection", "1")),
        "MISMATCH",
        ops_text="1. Det kan stiftes samvirkeforetak.",
        consolidated_text="1. Det kan ikke stiftes samvirkeforetak.",
    )

    typed = classify_no_annex_ceiling([witness, wording_conflict])

    assert [record.rule_id for record in typed] == [NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS]


def test_annex_ceiling_address_rule_requires_the_duplicated_annex_token() -> None:
    # §2.9 paired negative for no_verify.ceiling_annexed_instrument_address:
    # each half of the Lovdata annex encoding is load-bearing. A non-ordinary
    # chapter label with an unprefixed or disagreeing section token, and an
    # ordinary (decimal or roman) chapter label, all fail to type.
    unprefixed_section = _no_div(
        (("chapter", "gdpr"), ("chapter", "I"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    disagreeing_token = _no_div(
        (("chapter", "gdpr"), ("chapter", "I"), ("section", "xyz/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    non_article_section = _no_div(
        (("chapter", "gdpr"), ("chapter", "I"), ("section", "gdpr/11a"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    roman_body_chapter = _no_div(
        (("chapter", "IV"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    decimal_body_chapter = _no_div(
        (("chapter", "10a"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )

    assert classify_no_annex_ceiling(
        [
            unprefixed_section,
            disagreeing_token,
            non_article_section,
            roman_body_chapter,
            decimal_body_chapter,
        ]
    ) == ()


# --- W-40: the nested (compound sub-chapter) annex encoding -----------------
#
# All fixtures below are real addresses from no/lov/2012-12-14-81
# (EØS-arbeidstakarlova), taken from the 93-row measurement in
# .tmp/w40/measure_2012-12-14-81.json. Lovdata prints regulation (EU) nr.
# 492/2011 under chapter:1 ("Forordning") / chapter:1-1 ("EØS-avtalen vedlegg
# V punkt 2 …"), so the host chapter is ORDINARY and the article labels carry
# no token prefix — both halves of the W-17 encoding are absent.


def test_annex_ceiling_types_a_nested_compound_subchapter_annex() -> None:
    # Positive, the two path shapes the law actually carries: the regulation's
    # chapters I-III subdivide into ``part`` steps (55 + 27 rows), chapter IV
    # holds its articles directly (11 rows).
    under_part = _no_div(
        (
            ("chapter", "1"),
            ("chapter", "1-1"),
            ("chapter", "I"),
            ("part", "1"),
            ("section", "a1"),
            ("subsection", "1"),
        ),
        "OPS_MISSING",
        consolidated_text="Alle statsborgarar i ein medlemsstat har rett til å ta lønt arbeid.",
    )
    under_chapter = _no_div(
        (
            ("chapter", "1"),
            ("chapter", "1-1"),
            ("chapter", "IV"),
            ("section", "a35"),
            ("subsection", "1"),
        ),
        "OPS_MISSING",
        consolidated_text="Denne forordninga skal ikkje røre ved føresegnene i traktaten.",
    )

    typed = classify_no_annex_ceiling([under_part, under_chapter])

    assert [record.rule_id for record in typed] == [
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_NESTED_ADDRESS
    ] * 2
    assert [(record.annex_token, record.article) for record in typed] == [
        ("1-1", "1"),
        ("1-1", "35"),
    ]
    # Typed, not removed.
    assert [record.divergence for record in typed] == [under_part, under_chapter]


def test_annex_ceiling_nested_rule_reaches_the_deepest_item_nesting() -> None:
    # Positive: 6 of the 93 rows sit three ``item`` levels below the
    # subsection. The rule reads the first ``section`` step, so depth below it
    # is irrelevant — pinned because the shape exists in corpus.
    deep = _no_div(
        (
            ("chapter", "1"),
            ("chapter", "1-1"),
            ("chapter", "I"),
            ("part", "1"),
            ("section", "a3"),
            ("subsection", "1"),
            ("item", "a"),
            ("item", "i"),
            ("item", "1"),
        ),
        "OPS_MISSING",
        consolidated_text="… avgrensar tilbodet om arbeid.",
    )

    typed = classify_no_annex_ceiling([deep])

    assert [record.rule_id for record in typed] == [
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_NESTED_ADDRESS
    ]


def test_annex_ceiling_nested_rule_does_not_type_ordinary_section_addresses() -> None:
    # §2.9 paired negative: ordinary Norwegian section addresses must not match,
    # including the ones inside the very law the rule covers. The first two rows
    # below are §§ 1 and 4 of the enacting act — which W-40 saw as
    # CONSOLIDATED_MISSING divergences and W-43 closed by parsing them (they are
    # printed; the top-level walk dropped them). They stay here as fixtures: the
    # rule must keep refusing to type the law's OWN sections whether or not they
    # currently diverge. The rest are ordinary shapes from elsewhere in corpus.
    rows = [
        _no_div((("section", "1"), ("subsection", "1")), "CONSOLIDATED_MISSING", ops_text="Lova gjeld …"),
        _no_div((("section", "4"), ("subsection", "1")), "CONSOLIDATED_MISSING", ops_text="Kongen kan gi forskrift …"),
        # An ordinary section under an ordinary chapter, with and without a
        # nested ordinary sub-chapter.
        _no_div((("chapter", "1"), ("section", "11"), ("subsection", "1")), "MISMATCH", ops_text="a", consolidated_text="b"),
        _no_div(
            (("chapter", "1"), ("chapter", "1-1"), ("section", "11"), ("subsection", "1")),
            "MISMATCH",
            ops_text="a",
            consolidated_text="b",
        ),
        # A section label that merely STARTS with "a" is not an article.
        _no_div(
            (("chapter", "1"), ("chapter", "1-1"), ("section", "a"), ("subsection", "1")),
            "OPS_MISSING",
            consolidated_text="Tekst.",
        ),
    ]

    assert classify_no_annex_ceiling(rows) == ()


def test_annex_ceiling_nested_rule_requires_the_host_prefixed_sub_chapter() -> None:
    # §2.9 paired negative: each of the three requirements is load-bearing.
    # The middle case is the one that keeps W-40 disjoint from W-17's
    # counterpart criterion — no/lov/2006-06-30-50's canonical-body articles
    # sit at chapter:1/chapter:I/section:a1, an ORDINARY second chapter, and
    # must keep being explained (or not) by the counterpart rule alone.
    no_sub_chapter = _no_div(
        (("chapter", "1"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    ordinary_sub_chapter = _no_div(
        (("chapter", "1"), ("chapter", "I"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    unrelated_sub_chapter = _no_div(
        (("chapter", "1"), ("chapter", "2-1"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    sub_chapter_without_separator = _no_div(
        (("chapter", "1"), ("chapter", "10"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    token_prefixed_section = _no_div(
        (("chapter", "1"), ("chapter", "1-1"), ("section", "1-1/a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    part_not_chapter = _no_div(
        (("part", "1"), ("chapter", "1-1"), ("section", "a1"), ("subsection", "1")),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )

    assert classify_no_annex_ceiling(
        [
            no_sub_chapter,
            ordinary_sub_chapter,
            unrelated_sub_chapter,
            sub_chapter_without_separator,
            token_prefixed_section,
            part_not_chapter,
        ]
    ) == ()


def test_annex_ceiling_nested_rule_is_disjoint_from_the_token_encoding() -> None:
    # The GDPR annex nests compound sub-chapters of its own
    # (chapter:gdpr/chapter:10-3-1, 484 corpus rows). Those stay W-17 address
    # rows: the nested rule needs an ORDINARY top chapter label and the token
    # rule needs a non-ordinary one, so no row can satisfy both.
    token_encoded = _no_div(
        (
            ("chapter", "gdpr"),
            ("chapter", "10-3-1"),
            ("section", "gdpr/a49"),
            ("subsection", "1"),
        ),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )

    typed = classify_no_annex_ceiling([token_encoded])

    assert [record.rule_id for record in typed] == [NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS]


def test_annex_ceiling_nested_rule_does_not_witness_the_counterpart_rule() -> None:
    # The nested encoding deliberately does not feed the counterpart criterion:
    # a two-address representation is a measured property of the TOKEN encoding
    # (2006-06-30-50 carries the SCE Regulation on both sides), and no law in
    # corpus doubles a nested annex into its own body. A canonical-body article
    # row alongside a nested-annex row for the same article therefore stays
    # unexplained.
    nested = _no_div(
        (
            ("chapter", "1"),
            ("chapter", "1-1"),
            ("chapter", "I"),
            ("part", "1"),
            ("section", "a1"),
            ("subsection", "1"),
        ),
        "OPS_MISSING",
        consolidated_text="Tekst.",
    )
    canonical = _no_div(
        (("chapter", "2"), ("chapter", "I"), ("section", "a1"), ("subsection", "1")),
        "CONSOLIDATED_MISSING",
        ops_text="Tekst.",
    )

    typed = classify_no_annex_ceiling([nested, canonical])

    assert [record.rule_id for record in typed] == [
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_NESTED_ADDRESS
    ]
    assert typed[0].divergence is nested


def test_annex_ceiling_conserves_the_divergence_total_and_the_verdict(tmp_path) -> None:
    # The conservation contract, on a synthetic law whose replay lane is
    # complete and whose current text carries an annex chapter: the ceiling
    # types the annex rows but the law still reports divergent, and
    # ceiling + unexplained reproduces divergence_count exactly.
    # The consolidation carries an annex chapter that the enacting act never
    # had, plus one ordinary text drift the ceiling must NOT explain.
    annex_current = _CURRENT_DIVERGENT_XML.replace(
        b"    </main>",
        b"""      <section class="section" data-name="gdpr" data-lovdata-URL="NL/lov/2025-01-01-1/KAPITTEL_gdpr">
        <h2>Vedlegg. Forordningen</h2>
        <article class="legalArticle" data-name="gdpr/a1" data-lovdata-URL="NL/lov/2025-01-01-1/KAPITTEL_gdpr/gdpr/a1">
          <h3 class="legalArticleHeader">Artikkel 1. Formaal</h3>
          <article class="legalP" id="ledd1">1. Denne forordning fastsetter regler.</article>
        </article>
      </section>
    </main>""",
    )
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _amendment_xml()),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", annex_current)],
    )

    result = verify_no_against_current("no/lov/2025-01-01-1", as_of="2025-02-15", data_dir=tmp_path)

    assert result.error is None
    # The verdict does NOT move: a typed row is still a divergence.
    assert result.consistent is False
    assert result.ceiling_divergence_count > 0
    assert (
        result.ceiling_divergence_count + result.unexplained_divergence_count
        == result.divergence_count
    )
    assert len(result.divergences or []) == result.divergence_count
    assert set(result.ceiling_divergence_rule_counts or {}) == {
        NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS
    }
    # The receipt is carried out of the lane, per-row, with its criterion named.
    receipt = (result.ceiling_divergences or [])[0].to_dict()
    assert receipt["family"] == "annexed_instrument_representation"
    assert receipt["annex_token"] == "gdpr"


def test_annex_ceiling_corpus_counts_are_pinned() -> None:
    """The measured capture set, asserted against the corpus rather than a fixture.

    W-17's claim is a NUMBER: 1,129 of the 1,513 provision-level divergences in
    the 57-law scan at as-of 2026-07-10 are annexed-instrument representation,
    reproducing the W-6 triage's hand-verified count exactly (918
    annex-consolidation-only + 211 annex-address-and-eea-adaptation). The pin
    below asserts it per law and per rule, together with the two properties the
    typing must never break: the three laws' divergence counts do not move, and
    the two largest non-annex divergent laws stay wholly unexplained.
    """
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("local Norway corpus is not installed")

    report = build_no_verify_scan(
        as_of="2026-07-10",
        data_dir=data_dir,
        limit=200,
        base_ids=[
            "no/lov/2018-06-15-38",
            "no/lov/2017-06-16-51",
            "no/lov/2006-06-30-50",
            # W-40: the fourth annexing law, under the nested encoding.
            "no/lov/2012-12-14-81",
            # Negative controls: the two largest divergent laws that annex
            # nothing. Neither criterion may reach a single one of their rows.
            "no/lov/2001-01-05-1",
            "no/lov/2013-06-21-102",
        ],
    )
    if report["scanned_count"] == 0:
        pytest.skip("local Norway corpus is not installed")
    rows = {item["base_id"]: item for item in report["results"]}
    # W-30 (2026-08-06, signed off): no/lov/2006-06-30-50 is still requested
    # above but no longer scanned — it left the candidate set when the
    # intro-marker widening bound no/lovtid/2007-06-29-81 to it, whose
    # commencement is contingent. Its 211 ceiling rows (104 address + all 107
    # counterpart) left the scan with it; they are a property of the law, not
    # of the candidate set, and return when that commencement resolves.
    # W-34 (2026-08-07, signed off): the SAME mechanism removes the second
    # negative control, no/lov/2013-06-21-102 (skipsarbeidsloven). Closing the
    # payload cursor at numbered law-switch leads binds it to
    # no/lovtid/2014-05-09-16 item 30, an act whose commencement reads "Kongen
    # bestemmer." — so the law becomes blocked_contingent and leaves the
    # candidate set with all 55 of its (wholly unexplained, 0-ceiling)
    # divergences. no/lov/2001-01-05-1 remains as the negative control and
    # still carries not one ceiling row.
    assert set(rows) == {
        "no/lov/2018-06-15-38",
        "no/lov/2017-06-16-51",
        "no/lov/2012-12-14-81",  # W-40: added, the nested-encoding annex law
        "no/lov/2001-01-05-1",
    }

    address = NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_ADDRESS
    counterpart = NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_COUNTERPART
    nested = NO_VERIFY_CEILING_ANNEXED_INSTRUMENT_NESTED_ADDRESS
    # (divergence_count, ceiling, unexplained, per-rule ceiling counts)
    expected = {
        # personopplysningsloven: the GDPR under chapter:gdpr. The 2 unexplained
        # are the §§-vs-§ § compare noise at §11(1) and §31(1).
        "no/lov/2018-06-15-38": (716, 714, 2, {address: 714}),
        # One convention annexed twice, bokmål (102) + nynorsk (102). The 6
        # unexplained are the §26 subsection-boundary shift family.
        "no/lov/2017-06-16-51": (210, 204, 6, {address: 204}),
        # W-40 (2026-08-08): EØS-arbeidstakarlova, admitted by W-39 and typed
        # here. Regulation (EU) nr. 492/2011 under chapter:1/chapter:1-1, the
        # nested (compound sub-chapter) annex encoding.
        # 97 -> 93 and 4 -> 0 unexplained at W-43 (2026-08-08): the 4 rows were
        # the enacting act's own §§ 1-4, and the published consolidation DOES
        # print them — `parse_no_statute` dropped them. Its top-level article
        # walk was an `if not body_children:` fallback to the chapter walk, so a
        # documentBody carrying both top-level `§§` and the annex `section` lost
        # every article. The merged order-preserving walk recovers them and the
        # four CONSOLIDATED_MISSING rows close. The law is now wholly ceiling.
        "no/lov/2012-12-14-81": (93, 93, 0, {nested: 93}),
        # SCE-loven's row (212, 211, 1, {address: 104, counterpart: 107}) is
        # off-scan since W-30 — see the set(rows) comment above.
        # 83 -> 81 at W-35 (2026-08-07, signed off): still 0 ceiling, which is
        # what this test is about — the negative control's story is unchanged.
        # The two closed rows are one CONSOLIDATED_MISSING and its paired
        # OPS_MISSING, both produced by a spurious extra subsection in
        # no/lovtid/2015-06-19-65's "§ 20 skal lyde:" payload: item 179's lead
        # was trapped inside the futureLegalArticle and rendered as statutory
        # text. Same mechanism as the 2005-06-03-34 witness, one row smaller.
        # 81 -> 0 at W-39 (2026-08-07): the law is now consistent — its whole
        # divergence set was one act, `no/lovtid/2009-06-19-85`, which the
        # collective re-enactment lead binds and the part-scoped commencement
        # instrument dates. It stays listed here because it stays SCANNED and
        # the ceiling criteria must still reach none of it; the row is now
        # vacuously rather than informatively negative, and the informative
        # negative control the bucket relies on is the 918 total below.
        "no/lov/2001-01-05-1": (0, 0, 0, {}),
        # skipsarbeidsloven's row (55, 0, 55, {}) is off-scan since W-34 — see
        # the set(rows) comment above.
    }
    for base_id, (total, ceiling, unexplained, rule_counts) in expected.items():
        row = rows[base_id]
        assert row["divergence_count"] == total, base_id
        assert row["ceiling_divergence_count"] == ceiling, base_id
        assert row["unexplained_divergence_count"] == unexplained, base_id
        assert row["ceiling_divergence_rule_counts"] == rule_counts, base_id
        # Conservation, per law: nothing was deleted from either side.
        assert ceiling + unexplained == total, base_id

    # Over the scanned subset: 714 + 204 = 918 address rows, no counterpart
    # rows (all 107 were SCE-loven's, off-scan since W-30). The corpus-wide
    # annexed-instrument family measured at W-17 (1,022 + 107 = 1,129) still
    # exists — only the candidate set shrank.
    # W-40 (2026-08-08): + 93 nested-encoding rows = 1,011. The two encodings
    # are counted under separate rule ids, which is the point of the split:
    # neither number can drift into the other.
    assert report["ceiling_rule_counts"] == {address: 918, nested: 93}
    assert report["divergence_totals"]["ceiling"] == 1011


def test_no_verify_partition_corpus_membership_is_pinned() -> None:
    """W-23: the whole 57-law partition, bucket by bucket, after the re-routing.

    Complete and disjoint is the property under test — every scan candidate in
    exactly one bucket — plus the three bucket changes W-23 makes and nothing
    else. Baseline captured at ``e95144e09`` in
    ``.tmp/w23/partition_before.json``: the only differences from it are

      * ``no/lov/2018-06-15-38``  source_sparse   -> annex_ceiling  (714/716)
      * ``no/lov/2006-06-30-50``  source_sparse   -> annex_ceiling  (211/212)
      * ``no/lov/2017-06-16-51``  replay_defect   -> annex_ceiling  (204/210)

    The scan-level receipts (verdicts, divergence totals, ceiling totals) are
    asserted UNMOVED alongside, because W-23 is a partition-view change only.
    """
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("local Norway corpus is not installed")

    report = build_no_verify_partition(as_of="2026-07-10", data_dir=data_dir, limit=200)
    if report["scanned_count"] == 0:
        pytest.skip("local Norway corpus is not installed")

    # Conservation: W-23 moves no scan-level number at all. (The numbers below
    # are the post-W-30 corpus — W-30's intro-marker widening moved the SCAN
    # itself, signed off 2026-08-06: no/lov/2006-06-30-50 left the candidate
    # set with its 212 divergences and its sparse signal; 2017-06-16-65
    # dropped 57 -> 13 and 2017-06-16-67 dropped 6 -> 2 via newly-bound
    # instrument-authorized amenders.)
    # W-32 moved the scan again, one row only and priced for sign-off
    # (2026-08-07): 2017-06-16-65 dropped 13 -> 9 as its § 49 andre ledd
    # bokstav e/f/g divergences closed — the multi-``bokstav`` lead that used to
    # drop both ops now lowers them, the Del IV erratum lowers on top, and a
    # second act's ``bokstav f og ny bokstav g`` lead binds. The four closed
    # divergences are exactly those three item addresses plus the matching
    # CONSOLIDATED_MISSING for item e; verdicts, membership, ceiling and the
    # other 55 rows are byte-identical.
    # W-34 moved the scan again (2026-08-07), four rows, each traced to a
    # newly-recovered op that binds to the enumeration item's OWN cited law:
    #   * 2013-06-21-102 leaves the candidate set entirely (-55 divergences):
    #     it newly binds no/lovtid/2014-05-09-16 item 30, whose commencement is
    #     "Kongen bestemmer.", so the law is blocked_contingent — the same
    #     decertification mechanism W-15/W-30 recorded.
    #   * 2013-06-21-75 ENTERS it (+1): no/lovtid/2015-06-19-65 item 250 gives
    #     it its first indexed amendment, from a dated act.
    #   * 2005-06-03-34 goes 0 -> 3 and is the one consistent -> divergent flip.
    #     Item 209's "skal § 27 lyde:" now lowers against its own law, and its
    #     payload is the `futureLegalArticle` element — inside which Lovdata's
    #     markup has PUT items 210 and 211's leads. The three CONSOLIDATED_MISSING
    #     rows are exactly those two trapped leads plus item 210's payload text.
    #     That is a payload-INTERNAL swallow the inter-node cursor cannot reach;
    #     across the 15 acts W-34 touches the class goes 46 -> 42, and every one
    #     of the 42 sits inside a `futureLegalArticle`. Recorded, not fixed here.
    #   * 2012-01-27-9 goes 6 -> 5 as item 248's § 61 first sentence lands.
    # Ceiling is untouched at 918; total and unexplained both drop by the same
    # 52 (-55 +1 +3 -1), so W-34 explains nothing away — it moves rows.
    # W-35 moves it back and closes the flip (2026-08-07). The leads Lovdata
    # trapped INSIDE `futureLegalArticle` payloads now leave the payload and
    # re-enter the lead stream as siblings, so THREE rows move and no other:
    #   * 2005-06-03-34 returns 3 -> 0, divergent -> consistent. The three
    #     CONSOLIDATED_MISSING rows were items 210 and 211's leads plus item
    #     210's quoted payload, rendered as § 27's third, fourth and fifth
    #     subsections; § 27 now holds its heading and its own one paragraph.
    #   * 2001-01-05-1 83 -> 81 and 2001-06-15-65 4 -> 2, both still divergent.
    #     Identical mechanism, one trapped lead each (items 179 and 185),
    #     each costing one CONSOLIDATED_MISSING plus one paired OPS_MISSING.
    #     Traced and signed off as movement beyond the priced witness.
    # Ceiling is untouched at 918 again; total and unexplained both drop by the
    # same 7 (3 + 2 + 2), so W-35 explains nothing away — it removes text that
    # was never the law's.
    # W-39 (2026-08-07). 56 -> 58 candidates and 22/34 -> 23/35. Three rows and
    # only three move, each traced to a named instrument or op change:
    #   * 2001-01-05-1 81 -> 0, divergent -> consistent. The two halves of W-39
    #     landing together: the collective re-enactment lead binds
    #     `no/lovtid/2009-06-19-85`'s 22 ops to it, and the part-scoped
    #     commencement instrument `no/forskrift/2011-04-01-342` dates them
    #     2011-04-01. Half (i) alone would have DECERTIFIED this law.
    #   * 2012-12-14-81 ENTERS divergent at 97, unblocked by the part
    #     authorization of `no/lovtid/2020-12-18-143` del I from
    #     `no/forskrift/2021-02-19-474` (2021-03-01). 93 of its 97 rows are
    #     OPS_MISSING under an annex-shaped address prefix (the W-17 family).
    #   * 2019-06-21-63 ENTERS divergent at 7, unblocked by the part
    #     authorization of `no/lovtid/2021-06-18-135` del I from
    #     `no/forskrift/2022-03-25-466` (2022-03-25).
    # Ceiling is untouched at 918 for the fourth landing running; total and
    # unexplained both move by the same +23 (-81 +97 +7), so W-39 explains
    # nothing away either — it removes 81 rows that WERE the law's, and admits
    # 104 rows on two laws that were previously unreachable.
    # W-40 (2026-08-08) moves no row and no verdict — it TYPES rows that were
    # already counted. 2012-12-14-81's 93 annex-shaped OPS_MISSING rows are
    # the nested (compound sub-chapter) annex encoding, so ceiling 918 -> 1011
    # and unexplained 294 -> 201 against an unmoved total of 1,212. The
    # law's partition bucket moves with them, source_sparse -> annex_ceiling,
    # which is the W-23 predicate doing exactly what it was built for.
    # W-43 (2026-08-08) moves four rows and nothing else — the ONLY corpus
    # numbers that change are total and unexplained, both by the same 4.
    # `parse_no_statute`'s top-level article walk was an `if not body_children:`
    # fallback to the chapter walk, so 2012-12-14-81's own §§ 1-4 (siblings of
    # the annex `section`, not children of it) were dropped from the parsed
    # consolidation and read back as CONSOLIDATED_MISSING. Merging the two walks
    # into one order-preserving pass closes exactly those 4 rows: total
    # 1,212 -> 1,208, unexplained 201 -> 197, ceiling unmoved at 1,011,
    # verdicts, membership and the other 57 laws byte-identical. (Corpus-wide
    # the merge recovers 103 top-level sections across 16 consolidations and 48
    # across 4 replay bases; 15 of those 16 laws are outside the candidate set,
    # so they move no scoreboard number today.)
    # W-47 (2026-08-08). 58 -> 65 candidates and 23/35 -> 25/40. SEVEN laws
    # enter, none leaves, and no pre-existing row moves at all: the multi-part
    # commencement route only ever turns an unresolved binding into a dated one,
    # so a law already scanning keeps every row it had. Each entrant is traced
    # to the grant that unblocked it in
    # ``tests/test_norway_index.py``'s candidate pin; their rows are
    #   * 2022-06-17-56 and 2024-12-20-96 enter CONSISTENT at 0 — the first
    #     landing in this series to admit a law that needs no repair at all.
    #   * 2013-04-12-13 enters divergent at 191, the largest entrant since
    #     W-39's 2012-12-14-81, and carries the sparse-history signal.
    #   * 2004-12-17-101 at 26, 2019-06-14-21's neighbour in replay_defect;
    #     2018-04-20-7 at 14 (untouched_drift); 2011-06-24-39 at 5 and
    #     2010-06-04-21 at 3 (replay_defect).
    # Ceiling is untouched at 1,011 for the sixth landing running; total and
    # unexplained both move by the same +239, so W-47 explains nothing away —
    # it admits 239 rows on five laws that were previously unreachable. That
    # unexplained rise is the honest cost of new coverage, exactly as at W-39.
    # W-53 (2026-08-09). 65 -> 73 candidates and 25/40 -> 29/44, the largest
    # entrant cohort since W-47 and the first bought by an ACT-level route: the
    # widened whole-act route dates 430 acts whose commencement instruments say
    # "the act commences" in wording ``_WHOLE_ACT_RE`` does not match. EIGHT laws
    # enter, none leaves, and no pre-existing row moves at all — the 65 base rows
    # are byte-identical across the change, and so are every entry's ``base_ids``
    # and ``n_ops`` (the lane writes DATES, never bindings; decert exposure is
    # structurally zero, not merely measured as zero).
    #   * 2004-12-17-99 (klimakvoteloven) enters CONSISTENT at 0 — the entrant
    #     W-52 existed to make safe. Under the W-50 counterfactual it was the
    #     programme's only `error` verdict; the receipt fix landed first, so the
    #     error column never opens here.
    #   * 2016-12-16-92, 2017-04-28-23, 2021-06-18-136 also enter consistent at 0.
    #   * 2001-06-15-75 at 15 and 2020-04-17-29 at 15, 2015-05-12-27 at 7,
    #     2004-03-26-17 at 1 — all divergent, all 0 ceiling rows.
    # Ceiling is untouched at 1,011 for the seventh landing running; total and
    # unexplained both move by the same +38, so W-53 explains nothing away — it
    # admits 38 rows on four laws that were previously unreachable. The honest
    # cost of new coverage, exactly as at W-39 and W-47.
    # W-73 (2026-08-11). 73 -> 76 candidates and 29/44 -> 29/47, the fourth
    # landing bought by a commencement route and the same shape as the three
    # before it: THREE laws enter, none leaves, and no pre-existing row moves at
    # all — the 73 base rows are byte-identical across the change. Each entrant's
    # last unresolved binding act is one of the five the title-cited subject
    # reader dates (see ``tests/test_norway_index.py``'s candidate pin):
    #   * 2015-06-19-70 at 17 and 2015-02-13-9 at 7, both divergent, both
    #     `replay_defect`; both unblocked by 2017-06-16-67 @2017-07-01.
    #   * 2020-06-19-77 at 3, divergent, `untouched_drift`; unblocked by
    #     2024-12-13-76 @2025-01-01.
    # Ceiling is untouched at 1,011 for the eighth landing running; total and
    # unexplained both move by the same +27, so W-73 explains nothing away — it
    # admits 27 rows on three laws that were previously unreachable. The honest
    # cost of new coverage, exactly as at W-39, W-47 and W-53.
    # W-66c (2026-08-14). 76 -> 75 candidates and 29/47 -> 29/46, and this is the
    # FIRST landing in the series where the candidate set SHRINKS. The cause is
    # mechanical and is the W-73 mechanism running backwards: a base's replay
    # status is derived from the statuses of the amendments that BIND to it, and
    # the punktum-depth repeal gives ``no/lovtid/2013-01-11-3`` — an instrument
    # whose commencement is CONTINGENT — its first lowered ops against
    # ``no/lov/2010-06-04-21`` and ``no/lov/2011-06-24-39``. One contingent
    # binding downgrades a base from `fully_replayable` to `blocked_contingent`,
    # so both laws leave the candidate set. Their replays are not worse; the
    # LABEL is more honest, because the binding was always in the source and the
    # system simply could not see it. ONE law enters to partly offset:
    # ``no/lov/2009-05-15-28`` takes its first lowered op ever from a `dated`
    # instrument and arrives divergent at 2 rows.
    #   * candidates 76 -> 75  (-2010-06-04-21, -2011-06-24-39, +2009-05-15-28)
    #   * divergent  47 -> 46  (the two leavers were both divergent; the entrant
    #     is too), consistent unmoved at 29, error unmoved at 0.
    assert report["scanned_count"] == 75
    assert report["summary"] == {"consistent": 29, "divergent": 46, "error": 0}
    # W-67 + W-74 (2026-08-11). The first landing in this series that moves the
    # scoreboard by CLOSING rows rather than by admitting laws: the candidate set
    # is unmoved at 76 element for element, the summary is unmoved at 29/47/0, and
    # exactly ONE candidate row changes — ``no/lov/2010-06-04-21`` 3 -> 1, both
    # ``OPS_MISSING`` rows at ``chapter:10/section:10-13/subsection:1`` and ``:2``
    # closing off the two-token section-renumber widening's own witness
    # ("Gjeldende § 10-10 blir ny § 10-13."). The other 75 candidate rows are
    # byte-identical across the change. Total and unexplained both fall by the
    # same 2 and the ceiling is untouched at 1,011 for the NINTH landing running,
    # so this item explains two rows away rather than admitting any.
    # W-64 (2026-08-11). The same shape again, six rows wide: candidates unmoved
    # at 76, summary unmoved at 29/47/0, and exactly ONE candidate row changes —
    # ``no/lov/2001-06-15-75`` 15 -> 9, all six ``OPS_MISSING`` rows at
    # ``chapter:5/section:37a/subsection:1`` through ``:6`` closing off the
    # ``defaultP`` heading-boundary fix's own witness ("Ny § 37 a skal lyde:",
    # whose six ledd were stranded behind the heading ``Avgift og gebyr``). The
    # other 75 candidate rows are byte-identical and ZERO rows open anywhere,
    # which is what says the landed ledd match the consolidation rather than
    # trading one row type for another. Total and unexplained both fall by the
    # same 6, ceiling untouched at 1,011 for the TENTH landing running. Only 2 of
    # the 45 base acts whose ops moved are candidates at all, so the scoreboard
    # sees 2 of the 106 new ops; the other 104 are real and off-scan.
    # W-75 (2026-08-12). Candidates unmoved at 76, summary unmoved at 29/47/0, and
    # exactly ONE candidate row changes -- ``no/lov/2015-06-19-70`` 17 -> 14, where
    # refusing the word-substitution address list gives karanteneloven's destroyed
    # provisions their text back. This is the FIRST landing in the series where
    # rows both close and open, and that is the honest shape of the trade: five
    # ``OPS_MISSING`` rows close (the litra under § 13 first and § 14 second ledd
    # exist again now that their parent is not overwritten) and two ``MISMATCH``
    # rows open on those parents, which had been invisible as rows of their own
    # while their children carried the damage. Every one of the 12 remaining rows
    # on the law now diverges on exactly the superseded word (``tilsetting…`` vs
    # ``ansettels…``) instead of showing an address list where the law should be.
    # Total and unexplained both fall by the same 3, ceiling untouched at 1,011 for
    # the ELEVENTH landing running. Only 1 of the 13 base acts whose ops moved is a
    # candidate at all: the other 12 laws lose 92 of the 107 refused ops off-scan,
    # including plan- og bygningsloven's seven, which no candidate row can see.
    # W-66 (2026-08-12). Candidates unmoved at 76, summary unmoved at 29/47/0, and
    # SIX candidate rows change — the widest scan movement in the series, because
    # the sibling-set ledd relabel is the widest lowering in it (682 refusals
    # withdrawn, 1,147 new RENUMBER legs, 59 of 783 laws moving). ``2019-06-14-21``
    # 28 -> 25, ``2004-12-17-101`` 26 -> 24, ``2017-06-16-65`` 9 -> 7,
    # ``2015-02-13-9`` 7 -> 5, ``2010-06-25-28`` 27 -> 26, ``2012-01-27-9`` 5 -> 5.
    # 12 rows close and 2 open, and BOTH entrants are adjudicated rather than
    # absorbed into the net: ``2012-01-27-9`` § 46 fjerde ledd goes OPS_MISSING ->
    # MISMATCH, which is the ledd EXISTING now and matching the consolidation
    # except for a trailing full stop the published text drops; ``2015-02-13-9``
    # § 3 sjette ledd opens OPS_MISSING because the one remaining unlowered
    # instruction on that section is ``2023-06-16-34``'s "Nåværende § 3 femte ledd
    # blir sjette ledd og skal lyde:", a shift-PLUS-PAYLOAD lead this grammar
    # refuses by construction, which was invisible while the whole ledd sequence
    # was out of step. Total and unexplained both fall by the same 10, ceiling
    # untouched at 1,011 for the TWELFTH landing running. Signed off 2026-08-12.
    # W-70 (2026-08-12). Candidates unmoved at 76, summary unmoved at 29/47/0, and
    # exactly ONE candidate row changes — ``no/lov/2015-06-19-70`` 14 -> 12, the
    # two rows W-72(c)'s entrant triage attributed to this item and no others; the
    # other 75 laws are byte-identical. 2 rows close, 0 open, so total and
    # unexplained fall by the same 2 and the ceiling is untouched at 1,011 for the
    # THIRTEENTH landing running. Both rows were ONE defect wearing two shapes:
    # with the block's malformed ``data-move-part`` refused, its INSERT of a new
    # § 8 andre ledd landed on the LIVE andre ledd and the insert-occupied
    # recovery replaced it, so ``subsection:3`` held the old tredje ledd's text
    # (MISMATCH/text_drift) and ``subsection:4`` never existed
    # (OPS_MISSING/replay_lowering_gap). Normalizing the separator mints 2->3 and
    # 3->4, the vacate stage runs 3->4 first, and the destroyed andre ledd ("Lønn
    # eller vederlag for annet arbeid…") is back at its consolidation address.
    # Only 1 of the 4 base acts this item touches is a candidate at all: two of
    # the other three are skipped contingent and one has no original-act source,
    # so their recovered legs are banked, not scored. Signed off 2026-08-12.
    # W-69a (2026-08-12). Candidates unmoved at 76, summary unmoved at 29/47/0,
    # and exactly TWO candidate rows change — both named in advance by W-69's
    # design pass, which is the first time this programme has predicted a row
    # movement before building the production. ``no/lov/2015-06-19-70`` 12 -> 8
    # and ``no/lov/2020-04-17-29`` 15 -> 8; the other 74 laws are byte-identical.
    # 11 rows CLOSE and 0 open, so total and unexplained fall by the same 11 and
    # the ceiling is untouched at 1,011 for the FOURTEENTH landing running — and
    # this is the first landing in the series to close rows by ADDING a production
    # rather than by refusing one. Every closed row diverged on exactly the
    # superseded word (``tilsetting…``/``ansettels…``,
    # ``Dagligvaretilsynet``/``Konkurransetilsynet``,
    # ``Markedsrådet``/``Konkurranseklagenemnda``), which is what W-75 left
    # standing when it refused the construct rather than lowering it. What stays
    # open is stated rather than netted: karanteneloven ``§ 20 fjerde ledd``
    # carries the genitive ``tilsettingsmyndighetens`` and whole-word matching
    # declines it, the measured price of the matching rule; ``2020-04-17-29``'s
    # five remaining substitution addresses are ``§ 11``/``§ 18`` ledd that do not
    # exist in the replayed tree, a different defect. Signed off 2026-08-12.
    # W-69b (2026-08-13). Candidates unmoved at 76, summary unmoved at 29/47/0,
    # and again exactly TWO candidate rows change — the SAME two laws W-69a
    # moved: ``no/lov/2015-06-19-70`` 8 -> 2 and ``no/lov/2020-04-17-29`` 8 -> 7.
    # The other 74 laws are byte-identical. 7 rows CLOSE and 0 open, so total and
    # unexplained fall by the same 7 and the ceiling is untouched at 1,011 for
    # the FIFTEENTH landing running. Putting ``setning/N`` addresses in scope
    # lands 17 substitutions corpus-wide, but only these two laws are scan
    # candidates: the other 6 landings are on ``no/lov/2008-06-27-71``, which is
    # `blocked_contingent` and not scanned at all.
    #
    # The design pass projected 8 rows (7 + 1) and the measured answer is 7
    # (6 + 1), for a reason worth recording rather than netting: karanteneloven
    # ``§ 17 første ledd`` carries TWO of the eight sentence addresses, and one
    # of them (``første punktum``) reads ``Tilsettingsmyndigheten`` capitalised,
    # which case-sensitive whole-word matching declines (``inflection_only``).
    # ``tredje punktum`` lands, the ledd still diverges on the first, and the row
    # correctly stays open. Seven landings over seven ledd close six rows.
    #
    # W-70b (2026-08-14). NOTHING moves: candidates unmoved at 76, summary
    # unmoved at 29/47/0, totals unmoved at 1,471 / 1,011 / 460, and all 76
    # candidate rows byte-identical. The item repairs one ``data-move-part``
    # whose destination named the wrong section, and the ONE law whose statute it
    # changes — ``no/lov/2009-06-19-44``, krisesenterlova — is not a scan
    # candidate, so the repair is invisible here by construction. Recorded rather
    # than skipped: "no movement" is the measurement this ledger exists for, and
    # a landing that moved these numbers unexpectedly would be the finding.
    #
    # W-66c (2026-08-14). Total and unexplained both fall by the same 7, the
    # CEILING is untouched at 1,011 for the twelfth landing running, and ZERO
    # rows open anywhere. The 7 decomposes exactly, and only 3 of the 7 are rows
    # this item explains away:
    #   * -5  ``no/lov/2011-06-24-39`` LEAVES the candidate set with its rows
    #         (one of which the item had just closed; see the membership note);
    #   * -1  ``no/lov/2010-06-04-21`` LEAVES with its single row;
    #   * +2  ``no/lov/2009-05-15-28`` ENTERS with two;
    #   * -3  three rows CLOSE on candidates that stay, each one a punktum repeal
    #         landing at the ledd the row is addressed to:
    #           ``no/lov/2001-06-15-75``  9 -> 8  (§31 tredje ledd)
    #           ``no/lov/2016-06-17-29`` 21 -> 20 (§5 første ledd)
    #           ``no/lov/2021-06-18-121`` 2 -> 1  (§20 første ledd — W-66b's own
    #             witness, closed by the repeal that vacates the slot its relabel
    #             was refused for).
    # -5 -1 +2 -3 = -7. The address-coincidence join predicted five row-closing
    # candidates and four realized; the fifth (``no/lov/2022-03-11-9``) takes the
    # write at an address its row is at and keeps the row, which is the honest
    # outcome rather than a defect.
    #
    # W-76 (2026-08-16) left these totals at 1,464 / 1,011 / 453 — its 67 relabel
    # legs land on no scan candidate at all.
    #
    # W-77 (2026-08-16). Total and unexplained both fall by ONE, the CEILING is
    # untouched at 1,011 for the fourteenth landing running, and the candidate set
    # is unmoved at 75 with the summary unmoved at 29/46/0. The -1 is a NET, and it
    # decomposes into three rows on three candidates rather than one:
    #   * -1  ``no/lov/2004-03-26-17``  1 -> 0 rows: the ``OPS_MISSING`` row at
    #         § 2 første ledd bokstav g CLOSES, because the item-depth newness
    #         payload production writes the bokstav the instrument commanded (and a
    #         later amendment's REPLACE, which had been refusing at an absent
    #         target, then lands on it);
    #   * -1  ``no/lov/2012-01-27-9``   5 -> 4 rows: the ``OPS_MISSING`` row at
    #         § 1 første ledd bokstav k closes the same way;
    #   * +1  ``no/lov/2017-06-16-60``  0 -> 1 row: a ``CONSOLIDATED_MISSING`` row
    #         OPENS at § 7 andre ledd bokstav e. This one is adjudicated and
    #         deliberate: ``no/lovtid/2021-06-18-129`` commands "§ 6 annet ledd ny
    #         bokstav e skal lyde: …" and "Loven trer i kraft straks"; the write
    #         lands verbatim at the address the instrument names, and a later act's
    #         §§ 4–7 renumber carries it to § 7. Lovdata's archived consolidation
    #         of klimaloven does not carry that bokstav. The row is the honest
    #         report of a gap between the instrument and the consolidation, not a
    #         defect in the lowering.
    # -1 -1 +1 = -1. The address-coincidence join, run at the base pin before any
    # production code existed, predicted exactly ONE row-closing candidate
    # (``no/lov/2004-03-26-17``); the second closure and the one opening were not
    # projected, and both are recorded here rather than netted.
    assert report["divergence_totals"] == {"total": 1463, "ceiling": 1011, "unexplained": 452}
    # 3 -> 2 at W-34: no/lov/2001-01-05-1 gains 4 bound ops from
    # no/lovtid/2015-06-19-65 item 178, so its indexed history is no longer
    # sparse. Its 83 divergences do not move; only the bucket does.
    # 2 -> 3 at W-39: the newly-admitted 2012-12-14-81 carries the signal.
    # 3 -> 4 at W-47: so does the newly-admitted 2013-04-12-13.
    assert report["source_signal_counts"] == {"sparse_indexed_history": 4}

    expected = {
        # W-34 (2026-08-07): -2013-06-21-102 (off-scan, see above),
        # +2001-01-05-1 (source_sparse -> here, its sparse signal stopped firing
        # after item 178 bound), +2005-06-03-34 (consistent -> here, the 3
        # futureLegalArticle rows). 15 -> 16.
        # W-35: -2005-06-03-34, back to consistent with 0 divergences once those
        # three rows leave its § 27 payload. 16 -> 15, and the ONLY membership
        # change in the whole partition.
        # W-39: 2001-01-05-1 leaves for `consistent` (81 -> 0) and
        # 2019-06-21-63 enters with the candidate set. 15 -> 15.
        # W-47: three of the seven entrants land here. 15 -> 18.
        # W-53: three of the eight entrants land here. 18 -> 21.
        "replay_defect": [
            # W-77: ``no/lov/2004-03-26-17`` LEAVES for `consistent` (its single
            # OPS_MISSING row closes when the item-depth newness payload lands
            # § 2 første ledd bokstav g) and ``no/lov/2017-06-16-60`` ENTERS from
            # `consistent` (a CONSOLIDATED_MISSING row opens at § 7 andre ledd
            # bokstav e — the write the instrument commands, which Lovdata's
            # archived consolidation of klimaloven does not carry). One in, one
            # out: the SUMMARY holds at 29/46/0 and only the membership moves,
            # which is exactly what this pin exists to catch.
            "no/lov/2001-06-15-65",
            "no/lov/2001-06-15-75",
            "no/lov/2004-05-28-29",
            "no/lov/2004-12-17-101",
            # W-67 + W-74: ``no/lov/2010-06-04-21`` LEAVES for `untouched_drift`.
            # With its two ``OPS_MISSING`` rows closed it has no replay-defect row
            # left, so the W-23 predicate re-buckets it — the predicate doing what
            # it was built for, not a membership drift. 23 -> 22.
            "no/lov/2010-06-25-28",
            # W-66c: `no/lov/2011-06-24-39` LEAVES — not for another bucket but
            # off the board entirely. The punktum repeal binds
            # `no/lovtid/2013-01-11-3` (contingent commencement) to it for the
            # first time, so the law downgrades to `blocked_contingent` and stops
            # being a scan candidate. 24 -> 23.
            # W-66: ARRIVES from `untouched_drift`, and the direction is the point.
            # Its § 46 fjerde ledd row used to sit at an address no op touched;
            # the sibling-set ledd relabel now LANDS there (the row goes
            # OPS_MISSING -> MISMATCH, the ledd existing and matching the
            # consolidation but for a trailing full stop), so the W-23 predicate
            # re-buckets it as touched. 22 -> 23. Same predicate, opposite
            # direction to W-67+W-74's `2010-06-04-21` move below.
            "no/lov/2012-01-27-9",
            "no/lov/2012-11-30-70",
            "no/lov/2014-08-15-59",
            # W-73: two of the three entrants land here, both unblocked by
            # 2017-06-16-67 @2017-07-01 (statsansatteloven's own kgl.res.).
            # 21 -> 23.
            "no/lov/2015-02-13-9",
            "no/lov/2015-05-22-33",
            "no/lov/2015-06-19-70",
            "no/lov/2016-06-17-29",
            "no/lov/2016-06-17-46",
            "no/lov/2017-05-22-29",
            "no/lov/2017-05-22-30",
            # W-77: ARRIVES from `consistent`. See the note at the head of this
            # bucket.
            "no/lov/2017-06-16-60",
            "no/lov/2019-06-14-21",
            "no/lov/2019-06-21-63",
            "no/lov/2019-12-20-109",
            "no/lov/2020-04-17-29",
            "no/lov/2021-06-11-79",
            # W-66b: ARRIVES from `untouched_drift`, and like W-66's
            # `2012-01-27-9` above this is the W-23 predicate doing its job rather
            # than membership drift — but in the REFUSING direction, which is the
            # more interesting one. `no/lovtid/2022-06-10-38` carries exactly two
            # instructions: "§ 20 første ledd annet punktum oppheves." and
            # "Nåværende tredje punktum blir annet punktum." The punktum relabel
            # now lowers; the punktum-depth REPEAL does not, because no production
            # reads one. So the relabel's destination is still occupied by the live
            # second sentence when the leg runs, and W-66's apply-plane guard
            # REFUSES it (blocking, nothing written) rather than take the θ
            # (RENUMBER, dest_occupied) recovery, which would have deleted that
            # sentence — W-54's `removal_wrong` shape, one depth word down.
            # The law's § 20 første ledd row is therefore no longer "untouched":
            # something addressed it and declined. 22 -> 23.
            #
            # W-66c: and it LEAVES again, back to `untouched_drift`, closing the
            # loop W-66b opened. The companion punktum REPEAL now lowers, vacates
            # slot 2, the relabel lands behind it, and the § 20 første ledd row
            # CLOSES. Nothing on this law declines any more, so the W-23 predicate
            # buckets its one remaining row as ordinary drift. 23 -> 22.
            "no/lov/2022-03-11-9",
        ],
        "untouched_drift": [
            "no/lov/2003-06-27-57",
            "no/lov/2007-06-29-89",
            "no/lov/2009-03-06-12",
            # W-67 + W-74: arrives from `replay_defect` with its two OPS_MISSING
            # rows closed; the one MISMATCH row it keeps is untouched drift.
            # 19 -> 20.
            # W-66c: and LEAVES the board entirely, the same way
            # `no/lov/2011-06-24-39` leaves `replay_defect` — the punktum repeal
            # binds `no/lovtid/2013-01-11-3` (contingent) to it for the first
            # time and the law downgrades to `blocked_contingent`. 20 -> 19.
            # W-66c: `no/lov/2009-05-15-28` ENTERS the candidate set on its first
            # lowered op ever (a punktum repeal from a `dated` instrument),
            # divergent at 2 rows, neither a ceiling row nor traceable to a
            # replay defect. 19 -> 20.
            "no/lov/2009-05-15-28",
            # W-66: `no/lov/2012-01-27-9` LEAVES for `replay_defect`; see the note
            # there. 20 -> 19.
            # W-34: enters the candidate set with its first indexed amendment.
            "no/lov/2013-06-21-75",
            # W-53: the one entrant of the eight that lands here, at 7 rows,
            # none of them a ceiling row and none traceable to a replay defect.
            # 17 -> 18.
            "no/lov/2015-05-12-27",
            "no/lov/2017-05-22-28",
            "no/lov/2017-06-16-65",
            "no/lov/2017-06-16-67",
            # W-47: enters the candidate set at 14 rows, none of them a ceiling
            # row and none of them traceable to a replay defect. 16 -> 17.
            "no/lov/2018-04-20-7",
            # W-73: the third entrant, at 3 rows, unblocked by 2024-12-13-76
            # @2025-01-01 (ekomloven's own kgl.res.). 18 -> 19.
            "no/lov/2020-06-19-77",
            "no/lov/2020-12-04-136",
            "no/lov/2021-04-16-18",
            # W-66b: `no/lov/2021-06-18-121` LEAVES for `replay_defect`; see the
            # note there. 20 -> 19.
            # W-66c: and RETURNS, with the row that sent it away CLOSED — the
            # punktum repeal vacates the slot, the W-66b relabel lands behind it,
            # and § 20 første ledd matches the consolidation. 19 -> 20.
            "no/lov/2021-06-18-121",
            "no/lov/2022-06-17-49",
            "no/lov/2022-12-20-118",
            "no/lov/2022-12-20-97",
            "no/lov/2023-11-24-85",
            "no/lov/2024-12-13-76",
        ],
        # F-09 proper: the two laws whose divergences really are an
        # acquisition ceiling. Both carry 0 annex-ceiling rows, and both are
        # the ONLY two on which the signal would still fire if it were
        # re-derived from the W-17 residue instead of the raw total
        # (.tmp/w23/annex_coverage.json) — the bucket's story is now true of
        # every member.
        # W-34: 2001-01-05-1 leaves — the sparse-history signal stops firing
        # once no/lovtid/2015-06-19-65 item 179 binds to it. The bucket's story
        # (0 annex-ceiling rows, signal would still fire off the W-17 residue)
        # remains true of the one member left.
        # W-39: 2012-12-14-81 enters with the candidate set carrying the signal.
        # W-40 (2026-08-08): and leaves again for annex_ceiling once its 93
        # annex-shaped rows are typed — the contradiction W-39 recorded here
        # ("0 annex-ceiling rows" true of one member and not the other) is
        # closed by typing the rows rather than by re-bucketing the law. The
        # bucket is F-09 proper again: one member, 0 ceiling rows, and the
        # sparse signal would still fire off the W-17 residue.
        # W-47 (2026-08-08): 2013-04-12-13 enters the candidate set carrying the
        # signal, at 191 unexplained rows and 0 ceiling rows — the same shape as
        # the bucket's other member. 1 -> 2.
        "source_sparse": [
            "no/lov/2013-04-12-13",
            "no/lov/2020-11-27-131",
        ],
        # no/lov/2006-06-30-50 left this bucket with the candidate set at
        # W-30 (contingent amender no/lovtid/2007-06-29-81); it returns when
        # that commencement resolves.
        # W-40: 2012-12-14-81 arrives from source_sparse at 93/97 ceiling —
        # the first member routed on the nested annex encoding, and the first
        # whose sparse signal was the thing the bucket had to overrule.
        "annex_ceiling": [
            "no/lov/2012-12-14-81",
            "no/lov/2017-06-16-51",
            "no/lov/2018-06-15-38",
        ],
        # W-34: 2005-06-03-34 leaves for replay_defect (see above). 22 -> 21.
        # W-35: it returns. 21 -> 22.
        # W-39: 2001-01-05-1 arrives from replay_defect at 0 divergences,
        # the largest single-law repair in the series. 22 -> 23.
        # W-47: 2022-06-17-56 and 2024-12-20-96 ENTER the candidate set already
        # consistent — a first for this series, and the cheapest coverage the
        # programme has bought: two laws certified with no repair at all,
        # each on a single multi-part grant. 23 -> 25.
        # W-53: FOUR of the eight entrants enter already consistent, the largest
        # zero-repair cohort the programme has bought in one landing — and one of
        # them (2004-12-17-99, klimakvoteloven) is the law W-52's receipt fix was
        # opened for. 25 -> 29.
        "consistent": [
            # W-77: ``no/lov/2004-03-26-17`` ENTERS here from `replay_defect` and
            # ``no/lov/2017-06-16-60`` LEAVES for it. See the note on the
            # `replay_defect` bucket above.
            "no/lov/2001-01-05-1",
            "no/lov/2004-03-26-17",
            "no/lov/2004-05-14-25",
            "no/lov/2004-12-17-99",
            "no/lov/2005-06-03-34",
            "no/lov/2006-08-18-61",
            "no/lov/2012-01-27-10",
            "no/lov/2013-06-07-31",
            "no/lov/2016-12-16-92",
            "no/lov/2017-04-28-23",
            "no/lov/2018-06-15-44",
            "no/lov/2019-06-21-70",
            "no/lov/2020-05-07-38",
            "no/lov/2020-06-19-95",
            "no/lov/2020-12-18-153",
            "no/lov/2020-12-18-156",
            "no/lov/2021-05-21-42",
            "no/lov/2021-06-18-115",
            "no/lov/2021-06-18-136",
            "no/lov/2022-03-18-12",
            "no/lov/2022-05-12-28",
            "no/lov/2022-06-17-56",
            "no/lov/2023-06-16-62",
            "no/lov/2024-01-12-1",
            "no/lov/2024-06-25-69",
            "no/lov/2024-12-13-77",
            "no/lov/2024-12-20-96",
            "no/lov/2025-06-20-102",
            "no/lov/2025-12-22-116",
        ],
        "error": [],
    }
    partitions = report["partitions"]
    assert set(partitions) == set(expected)
    for bucket, base_ids in expected.items():
        assert sorted(item["base_id"] for item in partitions[bucket]) == base_ids, bucket

    # Complete and disjoint, asserted directly rather than inferred from the
    # per-bucket lists.
    routed = [item["base_id"] for bucket in partitions.values() for item in bucket]
    # 76 -> 75 at W-66c: two candidates downgrade to `blocked_contingent` on a
    # newly-visible contingent binding and one enters. See the membership note.
    assert len(routed) == 75
    assert len(set(routed)) == 75

    # Every member of the ceiling bucket is ceiling-DOMINATED, and the margin
    # to the routing boundary is enormous in both directions: the smallest
    # member sits at 95.8% ceiling, and no law outside the bucket carries a
    # single ceiling row.
    # 97.1% -> 95.8% at W-40 (2026-08-08): the new member 2012-12-14-81 is
    # 93/97. The separation is still total — the next law down carries zero
    # ceiling rows — so this floor stays a description of the corpus, not a
    # routing constant; the predicate itself is still a strict majority.
    # 95.8% -> 97.1% again at W-43 (2026-08-08): 2012-12-14-81 is 93/93, wholly
    # ceiling, and the smallest member is 2017-06-16-51 at 204/210 once more.
    # The 0.95 floor is deliberately NOT tightened back — it is a floor the
    # bucket must clear, not a running record of where the members happen to sit.
    for item in partitions["annex_ceiling"]:
        assert item["ceiling_divergence_count"] > item["unexplained_divergence_count"]
        assert item["ceiling_divergence_count"] / item["divergence_count"] > 0.95
    for bucket, items in partitions.items():
        if bucket == "annex_ceiling":
            continue
        assert all(item["ceiling_divergence_count"] == 0 for item in items), bucket

    # W-45 (2026-08-08): the census of laws this run could never have reached,
    # asserted as a SIBLING of ``partitions``. It adds no row to any bucket and
    # moves no scan number — ``scanned_count``, ``summary``,
    # ``divergence_totals``, ``source_signal_counts`` and all six bucket
    # memberships above are unmoved by its arrival, which is the whole point of
    # keeping it outside ``partitions``.
    #
    # The relation between the two numbers on this line: 73 laws are scannable
    # and 2,642 are not, and the 2,642 are not a backlog. 2,514 are amending
    # acts with no standing text of their own, 65 expired by their own terms,
    # and of the 63 substantive acts 50 are named in another act's structural
    # repeal manifest. The 61 ``would_be_candidates`` are the counterfactual
    # ceiling: if Lovdata published a consolidation for every one of these,
    # the candidate set would go 73 -> 134 and no further.
    # 55 -> 57 at W-47 (2026-08-08): the census counts laws that WOULD be
    # candidates but for the missing consolidation, so a route that resolves
    # commencements moves it exactly as it moves the candidate set. The two
    # extra laws are unreachable for the same reason as the other 55 and this
    # is the only number here W-47 touches — total and the family split are
    # properties of the corpus, not of the index.
    # 57 -> 61 at W-53 (2026-08-09), the same mechanism at the widened route's
    # scale: four more laws whose every amender is now dated and whose only
    # remaining obstacle is the missing consolidation. Total and the family
    # split are again unmoved, which is the check that a commencement route
    # cannot manufacture or destroy a law.
    # 61 -> 60 at W-61 (2026-08-10), and this is the FIRST time this number has
    # fallen. It is honest exposure, not a loss. ``no/lov/2009-06-19-101``
    # (mineralloven) leaves the counterfactual ceiling because the widened
    # repeal-then-shift lead binds it to ``no/lovtid/2013-01-11-3`` (its § 66 and
    # § 67 ledd repeals, item 33 of that act's consequential list) — an amender
    # whose own commencement is "Kongen bestemmer" with no instrument date. The
    # law's would-be status therefore moves ``fully_replayable`` ->
    # ``blocked_contingent``: the amender was always there and always undated,
    # and we could not see it only because its two leads did not lower. Total
    # and the family split are again unmoved, and the real candidate set stays
    # at 73 — mineralloven has no stored consolidation either way.
    assert set(report) >= {"partitions", "unverifiable"}
    assert report["unverifiable"]["no_stored_consolidation"] == {
        "total": 2642,
        "by_family": {
            "amending_act": 2514,
            "temporary_act": 40,
            "wage_board_act": 25,
            "substantive_act": 63,
        },
        "would_be_candidates": 60,
        "substantive_unexplained": 13,
    }


def test_verify_no_against_current_ignores_section_heading_only_drift(tmp_path) -> None:
    base_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Heading drift test</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="LTI/lov/2025-01-01-2">
      <article class="legalArticle" data-name="§1" data-lovdata-URL="LTI/lov/2025-01-01-2/§1">
        <article class="legalP">Gammel tekst.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-02-10</dd>
    <article class="document-change" data-document="lov/2025-01-01-2">
      <article class="change" data-change-part="lov/2025-01-01-2/§1">
        <article class="defaultP">§ 1 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§1">
          <span class="futureLegalArticleHeader">
            <span class="legalArticleValue">§ 1</span>.
            <span class="legalArticleTitle">Kort tittel</span>
          </span>
          <article class="legalP">Oppdatert operativ tekst.</article>
        </article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    current_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Heading drift test</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-2">
      <article class="legalArticle" data-name="§1" data-lovdata-URL="NL/lov/2025-01-01-2/§1">
        <article class="legalP">Oppdatert operativ tekst.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-002.xml", base_xml),
            ("lti/2025/nl-20250202-006.xml", amendment_xml),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-002.xml", current_xml)],
    )

    result = verify_no_against_current(
        "no/lov/2025-01-01-2",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None
    assert result.consistent is True
    assert result.divergence_count == 0


def test_verify_no_against_current_ignores_sentence_only_segmentation_drift(tmp_path) -> None:
    base_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Sentence drift test</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="LTI/lov/2025-01-01-3">
      <article class="legalArticle" data-name="§1" data-lovdata-URL="LTI/lov/2025-01-01-3/§1">
        <article class="numberedLegalP" data-numerator="1">(1) Første punktum. Andre gamle punktum.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-02-10</dd>
    <article class="document-change" data-document="lov/2025-01-01-3">
      <article class="change"
               data-add-new-part="lov/2025-01-01-3/§1/ledd/1/setning/2"
               data-move-part="lov/2025-01-01-3/§1/ledd/1/setning/2;;lov/2025-01-01-3/§1/ledd/1/setning/3">
        <article class="defaultP">§ 1 første ledd nytt annet punktum.</article>
        <article class="legalP">Andre nye punktum.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    current_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Sentence drift test</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-3">
      <article class="legalArticle" data-name="§1" data-lovdata-URL="NL/lov/2025-01-01-3/§1">
        <article class="numberedLegalP" data-numerator="1">(1) Første punktum. Andre nye punktum. Andre gamle punktum.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-003.xml", base_xml),
            ("lti/2025/nl-20250202-007.xml", amendment_xml),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-003.xml", current_xml)],
    )

    result = verify_no_against_current(
        "no/lov/2025-01-01-3",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None
    assert result.consistent is True
    assert result.divergence_count == 0
