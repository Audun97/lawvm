from __future__ import annotations

import io
import json
import tarfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import lawvm.tools.no_debug as no_debug
from lawvm.norway.index import NOAmendmentIndex, build_no_amendment_index


def _fake_index(data_dir: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(data_dir=data_dir, entries=[])


def _fake_verify_result() -> SimpleNamespace:
    divergence = SimpleNamespace(
        address=SimpleNamespace(path=(("section", "7-1"), ("subsection", "1"))),
        divergence_type="MISMATCH",
        ops_text="ops-1",
        consolidated_text="cur-1",
    )
    return SimpleNamespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        current_title="Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
        replay_status="replayed",
        consistent=False,
        divergence_count=1,
        divergence_counts={"MISMATCH": 1},
        raw_divergence_count=1,
        raw_divergence_counts={"MISMATCH": 1},
        divergences=[divergence],
        indexed_amendment_count=3,
        applied_amendment_count=3,
        replay_op_count=115,
        source_signal="",
        error=None,
    )


def test_no_debug_json_combines_reports(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "lawvm.norway.index.load_no_amendment_index",
        lambda path: _fake_index(str(tmp_path)),
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda *args, **kwargs: _fake_verify_result(),
    )
    monkeypatch.setattr(
        "lawvm.norway.commencement.build_no_law_report",
        lambda *args, **kwargs: {
            "title": "Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
            "amendment_count": 3,
            "replay_status": "fully_replayable",
            "executable_replay_status": "fully_replayable",
            "blocking_count": 0,
            "blocking_ops": 0,
        },
    )
    monkeypatch.setattr(
        "lawvm.tools.no_coverage.build_no_coverage_report",
        lambda *args, **kwargs: {
            "touched_divergence_count": 1,
            "untouched_divergence_count": 0,
        },
    )
    monkeypatch.setattr(
        "lawvm.tools.no_op_trace.build_no_op_trace_report",
        lambda *args, **kwargs: {
            "source_count": 2,
            "matched_source_count": 1,
            "op_count": 4,
            "sources": [
                {
                    "source_id": "no/lovtid/2025-12-22-123",
                    "effective_status": "dated",
                    "title": "Lov om endringer i suppleringsskatteloven",
                    "compiled_op_count": 59,
                    "matched_op_count": 1,
                }
            ],
            "ops": [
                {
                    "source_id": "no/lovtid/2025-12-22-123",
                    "sequence": 46,
                    "action": "replace",
                    "target_text": "section:7-1/subsection:1/item:c/item:1",
                }
            ],
        },
    )

    no_debug.main(
        Namespace(
            base_id="no/lov/2024-01-12-1",
            as_of="2026-03-29",
            data_dir="data/norway.farchive",
            index=str(tmp_path / "no_index_farchive.json"),
            commencement=None,
            path=["section:7-1"],
            limit=1,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["base_id"] == "no/lov/2024-01-12-1"
    assert payload["overall_hint"] == "text_drift"
    assert payload["amendment_count"] == 3
    assert payload["source_count"] == 2
    assert payload["matched_source_count"] == 1
    assert payload["touched_divergence_count"] == 1
    assert payload["untouched_divergence_count"] == 0
    assert payload["divergences"][0]["address_text"] == "section:7-1/subsection:1"
    assert payload["ops"][0]["target_text"] == "section:7-1/subsection:1/item:c/item:1"


def test_no_debug_text_prints_combined_summary(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "lawvm.norway.index.load_no_amendment_index",
        lambda path: _fake_index(str(tmp_path)),
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda *args, **kwargs: _fake_verify_result(),
    )
    monkeypatch.setattr(
        "lawvm.norway.commencement.build_no_law_report",
        lambda *args, **kwargs: {
            "title": "Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
            "amendment_count": 3,
            "replay_status": "fully_replayable",
            "executable_replay_status": "fully_replayable",
            "blocking_count": 0,
            "blocking_ops": 0,
        },
    )
    monkeypatch.setattr(
        "lawvm.tools.no_coverage.build_no_coverage_report",
        lambda *args, **kwargs: {
            "touched_divergence_count": 1,
            "untouched_divergence_count": 0,
        },
    )
    monkeypatch.setattr(
        "lawvm.tools.no_op_trace.build_no_op_trace_report",
        lambda *args, **kwargs: {
            "source_count": 1,
            "matched_source_count": 1,
            "op_count": 1,
            "sources": [],
            "ops": [],
        },
    )

    no_debug.main(
        Namespace(
            base_id="no/lov/2024-01-12-1",
            as_of="2026-03-29",
            data_dir="data/norway.farchive",
            index=str(tmp_path / "no_index_farchive.json"),
            commencement=None,
            path=[],
            limit=1,
            json=False,
        )
    )

    output = capsys.readouterr().out
    assert "Norway Debug" in output
    assert "overall hint" in output
    assert "law coverage" in output
    assert "trace coverage" in output
    assert "divergence split" in output
    assert "divergences:" in output


def test_no_debug_json_prefers_untouched_drift_hint_when_no_touched_divergences(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "lawvm.norway.index.load_no_amendment_index",
        lambda path: _fake_index(str(tmp_path)),
    )
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda *args, **kwargs: _fake_verify_result(),
    )
    monkeypatch.setattr(
        "lawvm.norway.commencement.build_no_law_report",
        lambda *args, **kwargs: {
            "title": "Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
            "amendment_count": 3,
            "replay_status": "fully_replayable",
            "executable_replay_status": "fully_replayable",
            "blocking_count": 0,
            "blocking_ops": 0,
        },
    )
    monkeypatch.setattr(
        "lawvm.tools.no_coverage.build_no_coverage_report",
        lambda *args, **kwargs: {
            "touched_divergence_count": 0,
            "untouched_divergence_count": 1,
        },
    )
    monkeypatch.setattr(
        "lawvm.tools.no_op_trace.build_no_op_trace_report",
        lambda *args, **kwargs: {
            "source_count": 1,
            "matched_source_count": 1,
            "op_count": 1,
            "sources": [],
            "ops": [],
        },
    )

    no_debug.main(
        Namespace(
            base_id="no/lov/2024-01-12-1",
            as_of="2026-03-29",
            data_dir="data/norway.farchive",
            index=str(tmp_path / "no_index_farchive.json"),
            commencement=None,
            path=[],
            limit=1,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["overall_hint"] == "untouched_base_current_drift"
    assert payload["touched_divergence_count"] == 0
    assert payload["untouched_divergence_count"] == 1


# ── W-110: a refused id stops before the index; one index per run; exit 1 ────


def _write_archive(archive_path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(archive_path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def _law_xml(text: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html><body><main class="documentBody"><section class="section" data-name="kap1">
<article class="legalArticle" data-name="§1"><article class="legalP">{text}</article></article>
</section></main></body></html>""".encode("utf-8")


_AMENDMENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<html><body><dd class="dateInForce">2025-02-10</dd>
<article class="document-change" data-document="lov/2025-01-01-1">
<article class="change" data-change-part="lov/2025-01-01-1/§1">
<article class="legalArticle" data-name="§1"><article class="legalP">endret tekst</article></article>
</article></article></body></html>""".encode("utf-8")


def _write_small_corpus(tmp_path: Path) -> None:
    """One law, one amendment, and a current text that agrees with the replay."""
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _law_xml("grunntekst")),
            ("lti/2025/nl-20250202-005.xml", _AMENDMENT_XML),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _law_xml("endret tekst"))],
    )


def _index_must_not_be_resolved(*_args: object, **_kwargs: object) -> NOAmendmentIndex:
    raise AssertionError("no-debug resolved the amendment index for a law id replay refuses on sight")


@pytest.mark.parametrize("json_output", [True, False])
@pytest.mark.parametrize(
    ("base_id", "said"),
    [
        ("no/lov", "expected no/<kind>/<date>"),
        ("no/forordning/2024-01-12-1", "unsupported Norway ref kind: forordning"),
        ("se/sfs/1962:700", "unsupported Norway base_id: 'se/sfs/1962:700'"),
    ],
)
def test_no_debug_command_refuses_a_malformed_id_before_the_index(
    monkeypatch, capsys, tmp_path, base_id: str, said: str, json_output: bool
) -> None:
    monkeypatch.setattr("lawvm.norway.index.build_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.index.load_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.verify.build_no_amendment_index", _index_must_not_be_resolved)

    with pytest.raises(SystemExit) as exit_info:
        no_debug.main(
            Namespace(
                base_id=base_id,
                as_of="2026-03-29",
                data_dir=None,
                index=str(tmp_path / "unreadable_index.json"),
                commencement=None,
                path=[],
                limit=5,
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
        assert "Norway Debug" in output
        assert said in output


def test_no_debug_command_builds_the_index_once(tmp_path, monkeypatch, capsys) -> None:
    """The op-trace part used to build a second index of its own (another ~90 s
    and ~800 MB on the full archive, with the first still held)."""
    _write_small_corpus(tmp_path)
    built: list[object] = []

    def _recording_builder(data_dir: object) -> NOAmendmentIndex:
        built.append(data_dir)
        return build_no_amendment_index(tmp_path)

    monkeypatch.setattr("lawvm.norway.index.build_no_amendment_index", _recording_builder)
    monkeypatch.setattr("lawvm.norway.verify.build_no_amendment_index", _recording_builder)
    monkeypatch.setattr("lawvm.norway.replay.build_no_amendment_index", _recording_builder)

    no_debug.main(
        Namespace(
            base_id="no/lov/2025-01-01-1",
            as_of="2025-02-15",
            data_dir=str(tmp_path),
            index=None,
            commencement=None,
            path=[],
            limit=5,
            json=True,
        )
    )
    payload = json.loads(capsys.readouterr().out)

    assert built == [tmp_path]
    assert payload["error"] == ""
    assert payload["consistent"] is True
    assert payload["indexed_amendment_count"] == 1
    assert payload["source_count"] == 1
    assert payload["op_count"] == 1


@pytest.mark.parametrize("json_output", [True, False])
def test_no_debug_command_exits_1_when_it_reports_an_error(tmp_path, capsys, json_output: bool) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _AMENDMENT_XML)],
    )

    with pytest.raises(SystemExit) as exit_info:
        no_debug.main(
            Namespace(
                base_id="no/lov/2025-01-01-1",
                as_of="2025-02-15",
                data_dir=str(tmp_path),
                index=None,
                commencement=None,
                path=[],
                limit=5,
                json=json_output,
            )
        )

    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    reason = "no original-act source available for no/lov/2025-01-01-1 (year 2025)"
    if json_output:
        payload = json.loads(output)
        assert payload["error"] == reason
        assert payload["indexed_amendment_count"] == 1
    else:
        assert f"error              : {reason}" in output
