from __future__ import annotations

import io
import json
import tarfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from lawvm.core.ir import LegalAddress, LegalOperation, OperationSource, StructuralAction
from lawvm.norway.index import NOAmendmentIndex, NOAmendmentIndexEntry
from lawvm.tools.no_coverage import build_no_coverage_report, main as no_coverage_main


def _op(target_path: list[tuple[str, str]]) -> LegalOperation:
    return LegalOperation(
        op_id="op-1",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=tuple(target_path)),
        source=OperationSource(statute_id="no/lovtid/2024-06-25-66", title="dummy"),
    )


def _fake_index() -> NOAmendmentIndex:
    return NOAmendmentIndex(
        data_dir="data/norway.farchive",
        source_kind="farchive",
        archive_names=[],
        archive_metadata={},
        entries=[
            NOAmendmentIndexEntry(
                source_id="no/lovtid/2024-06-25-66",
                archive="norway.farchive",
                member_name="no://lovtid/2024-06-25-66/amendment.xml",
                effective_status="dated",
                effective_date="2024-06-25",
                title="Lov om endringar i suppleringsskatteloven",
                base_ids=("no/lov/2024-01-12-1",),
                n_ops=1,
            )
        ],
    )


def _fake_verify() -> SimpleNamespace:
    divergences = [
        SimpleNamespace(
            address=SimpleNamespace(path=(("section", "7-1"), ("subsection", "1"))),
            divergence_type="MISMATCH",
            ops_text="touched text",
            consolidated_text="current text",
        ),
        SimpleNamespace(
            address=SimpleNamespace(path=(("section", "9"), ("subsection", "1"))),
            divergence_type="OPS_MISSING",
            ops_text=None,
            consolidated_text="untouched drift",
        ),
    ]
    return SimpleNamespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        current_title="Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
        replay_status="replayed",
        consistent=False,
        divergence_count=2,
        divergence_counts={"MISMATCH": 1, "OPS_MISSING": 1},
        raw_divergence_count=2,
        raw_divergence_counts={"MISMATCH": 1, "OPS_MISSING": 1},
        divergences=divergences,
        indexed_amendment_count=1,
        applied_amendment_count=1,
        replay_op_count=1,
        source_signal="",
        error=None,
    )


def test_no_coverage_json_classifies_touched_vs_untouched(monkeypatch, capsys) -> None:
    def fake_load(_source_id, _data_dir):
        return b"payload"

    def fake_iter(_html_bytes, _source_id):
        return [
            (
                "no/lov/2024-01-12-1",
                [_op([("section", "7-1"), ("subsection", "1")])],
            )
        ]

    monkeypatch.setattr("lawvm.norway.sources.load_no_amendment_bytes", fake_load)
    monkeypatch.setattr("lawvm.norway.grafter.iter_no_document_change_ops", fake_iter)
    report = build_no_coverage_report(
        base_id="no/lov/2024-01-12-1",
        data_dir=None,
        index=_fake_index(),
        verify_result=_fake_verify(),
        limit=10,
    )

    assert report["touched_path_count"] == 1
    assert report["touched_divergence_count"] == 1
    assert report["untouched_divergence_count"] == 1
    assert report["divergences"][0]["classification"] == "touched_replay_defect"
    assert report["divergences"][1]["classification"] == "untouched_base_current_drift"
    monkeypatch.setattr("lawvm.tools.no_coverage.build_no_coverage_report", lambda **_: report)

    no_coverage_main(
        Namespace(
            base_id="no/lov/2024-01-12-1",
            as_of="2026-03-29",
            data_dir=None,
            index=None,
            commencement=None,
            limit=10,
            json=True,
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["base_id"] == "no/lov/2024-01-12-1"


def test_no_coverage_text_prints_summary(monkeypatch, capsys) -> None:
    def fake_load(_source_id, _data_dir):
        return b"payload"

    def fake_iter(_html_bytes, _source_id):
        return [
            (
                "no/lov/2024-01-12-1",
                [_op([("section", "7-1"), ("subsection", "1")])],
            )
        ]

    monkeypatch.setattr("lawvm.norway.sources.load_no_amendment_bytes", fake_load)
    monkeypatch.setattr("lawvm.norway.grafter.iter_no_document_change_ops", fake_iter)
    report = build_no_coverage_report(
        base_id="no/lov/2024-01-12-1",
        data_dir=None,
        index=_fake_index(),
        verify_result=_fake_verify(),
        limit=10,
    )
    monkeypatch.setattr("lawvm.tools.no_coverage.build_no_coverage_report", lambda **_: report)

    no_coverage_main(
        Namespace(
            base_id="no/lov/2024-01-12-1",
            as_of="2026-03-29",
            data_dir=None,
            index=None,
            commencement=None,
            limit=10,
            json=False,
        )
    )
    output = capsys.readouterr().out
    assert "Norway Coverage Attribution" in output
    assert "touched coverage" in output
    assert "touched_replay_defect" in output
    assert "untouched_base_current_drift" in output


def test_no_coverage_treats_descendant_paths_under_chapter_wrappers_as_touched(monkeypatch) -> None:
    def fake_load(_source_id, _data_dir):
        return b"payload"

    def fake_iter(_html_bytes, _source_id):
        return [
            (
                "no/lov/2024-01-12-1",
                [_op([("section", "7-1"), ("subsection", "1"), ("item", "b"), ("item", "2")])],
            )
        ]

    verify_result = SimpleNamespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        current_title="Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
        replay_status="replayed",
        consistent=False,
        divergence_count=1,
        divergence_counts={"MISMATCH": 1},
        raw_divergence_count=1,
        raw_divergence_counts={"MISMATCH": 1},
        divergences=[
            SimpleNamespace(
                address=SimpleNamespace(
                    path=(
                        ("chapter", "I"),
                        ("chapter", "7"),
                        ("section", "7-1"),
                        ("subsection", "1"),
                        ("item", "b"),
                    )
                ),
                divergence_type="MISMATCH",
                ops_text="ops child text",
                consolidated_text="current parent text",
            )
        ],
        indexed_amendment_count=1,
        applied_amendment_count=1,
        replay_op_count=1,
        source_signal="",
        error=None,
    )

    monkeypatch.setattr("lawvm.norway.sources.load_no_amendment_bytes", fake_load)
    monkeypatch.setattr("lawvm.norway.grafter.iter_no_document_change_ops", fake_iter)
    report = build_no_coverage_report(
        base_id="no/lov/2024-01-12-1",
        data_dir=None,
        index=_fake_index(),
        verify_result=verify_result,
        limit=10,
    )

    assert report["touched_divergence_count"] == 1
    assert report["untouched_divergence_count"] == 0
    assert report["divergences"][0]["classification"] == "touched_replay_defect"


def test_no_coverage_treats_last_item_anchor_as_touching_concrete_final_item(monkeypatch) -> None:
    def fake_load(_source_id, _data_dir):
        return b"payload"

    def fake_iter(_html_bytes, _source_id):
        return [
            (
                "no/lov/2020-12-18-156",
                [_op([("section", "5"), ("subsection", "1"), ("item", "last")])],
            )
        ]

    verify_result = SimpleNamespace(
        base_id="no/lov/2020-12-18-156",
        as_of="2026-03-29",
        current_title="Tilskuddsloven",
        replay_status="replayed",
        consistent=False,
        divergence_count=1,
        divergence_counts={"OPS_MISSING": 1},
        raw_divergence_count=1,
        raw_divergence_counts={"OPS_MISSING": 1},
        divergences=[
            SimpleNamespace(
                address=SimpleNamespace(path=(("section", "5"), ("subsection", "1"), ("item", "8"))),
                divergence_type="OPS_MISSING",
                ops_text=None,
                consolidated_text="mangler siste punkt",
            )
        ],
        indexed_amendment_count=1,
        applied_amendment_count=1,
        replay_op_count=1,
        source_signal="",
        error=None,
    )

    monkeypatch.setattr("lawvm.norway.sources.load_no_amendment_bytes", fake_load)
    monkeypatch.setattr("lawvm.norway.grafter.iter_no_document_change_ops", fake_iter)
    report = build_no_coverage_report(
        base_id="no/lov/2020-12-18-156",
        data_dir=None,
        index=NOAmendmentIndex(
            data_dir="data/norway.farchive",
            source_kind="farchive",
            archive_names=[],
            archive_metadata={},
            entries=[
                NOAmendmentIndexEntry(
                    source_id="no/lovtid/2022-01-28-3",
                    archive="norway.farchive",
                    member_name="no://lovtid/2022-01-28-3/amendment.xml",
                    effective_status="dated",
                    effective_date="2022-01-28",
                    title="Endringslov",
                    base_ids=("no/lov/2020-12-18-156",),
                    n_ops=1,
                )
            ],
        ),
        verify_result=verify_result,
        limit=10,
    )

    assert report["touched_divergence_count"] == 1
    assert report["untouched_divergence_count"] == 0
    assert report["divergences"][0]["classification"] == "touched_replay_defect"


# ── W-110: a refused id stops before the index; an error is said and exits 1 ─


def _write_archive(archive_path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(archive_path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


_AMENDMENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<html><body><dd class="dateInForce">2025-02-10</dd>
<article class="document-change" data-document="lov/2025-01-01-1">
<article class="change" data-change-part="lov/2025-01-01-1/§1">
<article class="legalArticle" data-name="§1"><article class="legalP">endret tekst</article></article>
</article></article></body></html>""".encode("utf-8")


def _index_must_not_be_resolved(*_args: object, **_kwargs: object) -> NOAmendmentIndex:
    raise AssertionError("no-coverage resolved the amendment index for a law id replay refuses on sight")


@pytest.mark.parametrize("json_output", [True, False])
@pytest.mark.parametrize(
    ("base_id", "said"),
    [
        ("no/lov", "expected no/<kind>/<date>"),
        ("no/forordning/2024-01-12-1", "unsupported Norway ref kind: forordning"),
        ("se/sfs/1962:700", "unsupported Norway base_id: 'se/sfs/1962:700'"),
    ],
)
def test_no_coverage_command_refuses_a_malformed_id_before_the_index(
    monkeypatch, capsys, tmp_path, base_id: str, said: str, json_output: bool
) -> None:
    monkeypatch.setattr("lawvm.norway.index.build_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.index.load_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.verify.build_no_amendment_index", _index_must_not_be_resolved)

    with pytest.raises(SystemExit) as exit_info:
        no_coverage_main(
            Namespace(
                base_id=base_id,
                as_of=None,
                data_dir=None,
                index=str(tmp_path / "unreadable_index.json"),
                commencement=None,
                limit=10,
                json=json_output,
            )
        )

    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    if json_output:
        payload = json.loads(output)
        assert set(payload) == {"base_id", "error"}
        assert said in payload["error"]
    else:
        assert "Norway Coverage Attribution" in output
        assert said in output


@pytest.mark.parametrize("json_output", [True, False])
def test_no_coverage_command_says_why_replay_failed_and_exits_1(tmp_path, capsys, json_output: bool) -> None:
    """A well-formed id whose base act the archive does not hold is not refused on
    sight: its amendment is in the index and is still counted. But replay could
    not serve it, and the report used to say only ``replay status: error``."""
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _AMENDMENT_XML)],
    )

    with pytest.raises(SystemExit) as exit_info:
        no_coverage_main(
            Namespace(
                base_id="no/lov/2025-01-01-1",
                as_of="2025-02-15",
                data_dir=str(tmp_path),
                index=None,
                commencement=None,
                limit=10,
                json=json_output,
            )
        )

    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    reason = "no original-act source available for no/lov/2025-01-01-1 (year 2025)"
    if json_output:
        payload = json.loads(output)
        assert payload["error"] == reason
        assert payload["source_count"] == 1
    else:
        assert f"error                : {reason}" in output
        assert "sources=1/1" in output


def test_no_coverage_report_carries_no_error_for_a_law_replay_serves() -> None:
    """Negative: divergences are a result, not an error."""
    report = build_no_coverage_report(
        base_id="no/lov/2024-01-12-1",
        data_dir=None,
        index=NOAmendmentIndex(data_dir="data/norway.farchive", entries=[]),
        verify_result=_fake_verify(),
        limit=10,
    )

    assert report["divergence_count"] == 2
    assert report["error"] == ""
