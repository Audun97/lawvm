from __future__ import annotations

import io
import json
import tarfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import lawvm.tools.no_divergence as no_divergence
from lawvm.norway.index import NOAmendmentIndex, build_no_amendment_index


def _fake_result(*, source_signal: str = "", divergences: list[object] | None = None):
    counts: dict[str, int] = {}
    for divergence in divergences or []:
        kind = getattr(divergence, "divergence_type", "MISMATCH")
        counts[kind] = counts.get(kind, 0) + 1
    return SimpleNamespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        current_title="Lov om suppleringsskatt på underbeskattet inntekt i konsern (suppleringsskatteloven)",
        replay_status="replayed",
        consistent=False,
        divergence_count=len(divergences or []),
        divergence_counts=counts,
        raw_divergence_count=len(divergences or []),
        raw_divergence_counts=counts,
        divergences=divergences or [],
        indexed_amendment_count=3,
        applied_amendment_count=3,
        replay_op_count=115,
        source_signal=source_signal,
        error=None,
    )


def _fake_divergence(kind: str, path: list[tuple[str, str]], ops_text: str, consolidated_text: str):
    return SimpleNamespace(
        address=SimpleNamespace(path=tuple(path)),
        divergence_type=kind,
        ops_text=ops_text,
        consolidated_text=consolidated_text,
    )


def _fake_saved_index(monkeypatch, tmp_path) -> None:
    """The command loads the ``--index`` file once, for verify and the coverage
    split; these tests fake both consumers, so the file need not exist."""
    monkeypatch.setattr(
        "lawvm.norway.index.load_no_amendment_index",
        lambda path: SimpleNamespace(data_dir=str(tmp_path), entries=[]),
    )


def test_no_divergence_json_emits_bounded_primary_divergences(monkeypatch, capsys, tmp_path) -> None:
    _fake_saved_index(monkeypatch, tmp_path)
    divergences = [
        _fake_divergence("MISMATCH", [("chapter", "I"), ("section", "4-2")], "ops-1", "cur-1"),
        _fake_divergence("OPS_MISSING", [("section", "7-1")], "ops-2", "cur-2"),
    ]
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda *args, **kwargs: _fake_result(divergences=divergences),
    )
    monkeypatch.setattr(
        "lawvm.tools.no_coverage.build_no_coverage_report",
        lambda *args, **kwargs: {
            "touched_divergence_count": 2,
            "untouched_divergence_count": 0,
        },
    )

    args = Namespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        data_dir="data/norway.farchive",
        index=str(tmp_path / "no_index_farchive.json"),
        commencement=None,
        max_divergences=1,
        json=True,
    )

    no_divergence.main(args)
    payload = json.loads(capsys.readouterr().out)

    assert payload["base_id"] == "no/lov/2024-01-12-1"
    assert payload["overall_hint"] == "mixed_replay_and_text_drift"
    assert payload["touched_divergence_count"] == 2
    assert payload["untouched_divergence_count"] == 0
    assert payload["divergence_count"] == 2
    assert len(payload["divergences"]) == 1
    assert payload["divergences"][0]["address_text"] == "chapter:I/section:4-2"
    assert payload["divergences"][0]["hint"] == "text_drift"


def test_no_divergence_text_prints_hints_and_texts(monkeypatch, capsys, tmp_path) -> None:
    _fake_saved_index(monkeypatch, tmp_path)
    divergences = [
        _fake_divergence("MISMATCH", [("chapter", "I"), ("section", "7-1")], "ops-1", "cur-1"),
        _fake_divergence("OPS_MISSING", [("section", "6")], "ops-2", "cur-2"),
    ]
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda *args, **kwargs: _fake_result(source_signal="sparse_indexed_history", divergences=divergences),
    )
    monkeypatch.setattr(
        "lawvm.tools.no_coverage.build_no_coverage_report",
        lambda *args, **kwargs: {
            "touched_divergence_count": 1,
            "untouched_divergence_count": 1,
        },
    )

    args = Namespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        data_dir="data/norway.farchive",
        index=str(tmp_path / "no_index_farchive.json"),
        commencement=None,
        max_divergences=1,
        json=False,
    )

    no_divergence.main(args)
    output = capsys.readouterr().out

    assert "Norway Divergence Explainer" in output
    assert "overall hint    : sparse_indexed_history" in output
    assert "[source_sparse|MISMATCH] chapter:I/section:7-1" in output
    assert "ops : ops-1" in output
    assert "cur : cur-1" in output
    assert "section:6" not in output


def test_no_divergence_json_prefers_untouched_drift_hint_when_no_touched_divergences(monkeypatch, capsys, tmp_path) -> None:
    _fake_saved_index(monkeypatch, tmp_path)
    divergences = [
        _fake_divergence("OPS_MISSING", [("section", "28"), ("subsection", "3")], "ops-1", "cur-1"),
    ]
    monkeypatch.setattr(
        "lawvm.norway.verify.verify_no_against_current",
        lambda *args, **kwargs: _fake_result(divergences=divergences),
    )
    monkeypatch.setattr(
        "lawvm.tools.no_coverage.build_no_coverage_report",
        lambda *args, **kwargs: {
            "touched_divergence_count": 0,
            "untouched_divergence_count": 1,
        },
    )

    args = Namespace(
        base_id="no/lov/2024-01-12-1",
        as_of="2026-03-29",
        data_dir="data/norway.farchive",
        index=str(tmp_path / "no_index_farchive.json"),
        commencement=None,
        max_divergences=1,
        json=True,
    )

    no_divergence.main(args)
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


def _write_small_corpus(tmp_path: Path, *, current_text: str) -> None:
    """One law, one amendment replacing § 1 with ``endret tekst``, one current text."""
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [
            ("lti/2025/nl-20250101-001.xml", _law_xml("grunntekst")),
            ("lti/2025/nl-20250202-005.xml", _AMENDMENT_XML),
        ],
    )
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-20250101-001.xml", _law_xml(current_text))],
    )


def _index_must_not_be_resolved(*_args: object, **_kwargs: object) -> NOAmendmentIndex:
    raise AssertionError("no-divergence resolved the amendment index for a law id replay refuses on sight")


def _record_index_builds(monkeypatch, tmp_path: Path) -> list[object]:
    """Replace every index builder the command can reach with one that records
    the source it was asked for and builds from ``tmp_path``."""
    built: list[object] = []

    def _recording_builder(data_dir: object) -> NOAmendmentIndex:
        built.append(data_dir)
        return build_no_amendment_index(tmp_path)

    monkeypatch.setattr("lawvm.norway.index.build_no_amendment_index", _recording_builder)
    monkeypatch.setattr("lawvm.norway.verify.build_no_amendment_index", _recording_builder)
    monkeypatch.setattr("lawvm.norway.replay.build_no_amendment_index", _recording_builder)
    return built


@pytest.mark.parametrize("json_output", [True, False])
@pytest.mark.parametrize(
    ("base_id", "said"),
    [
        ("no/lov", "expected no/<kind>/<date>"),
        ("no/forordning/2024-01-12-1", "unsupported Norway ref kind: forordning"),
        ("se/sfs/1962:700", "unsupported Norway base_id: 'se/sfs/1962:700'"),
    ],
)
def test_no_divergence_command_refuses_a_malformed_id_before_the_index(
    monkeypatch, capsys, tmp_path, base_id: str, said: str, json_output: bool
) -> None:
    """Verify refuses such an id without an index, but this command then built
    one anyway for its coverage split: ``lawvm no-divergence no/lov`` took 91 s."""
    monkeypatch.setattr("lawvm.norway.index.build_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.index.load_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.verify.build_no_amendment_index", _index_must_not_be_resolved)

    with pytest.raises(SystemExit) as exit_info:
        no_divergence.main(
            Namespace(
                base_id=base_id,
                as_of="2026-03-29",
                data_dir=None,
                index=str(tmp_path / "unreadable_index.json"),
                commencement=None,
                max_divergences=10,
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
        assert "Norway Divergence Explainer" in output
        assert said in output


def test_no_divergence_command_builds_one_index_from_the_source_it_was_given(tmp_path, monkeypatch, capsys) -> None:
    """Verify built an index from ``--data-dir`` and the coverage split then built
    a second one from the DEFAULT archive, whatever ``--data-dir`` and
    ``--index`` said. One index now serves both, and a divergence is still a
    result: the command returns normally."""
    _write_small_corpus(tmp_path, current_text="en annen tekst")
    built = _record_index_builds(monkeypatch, tmp_path)

    no_divergence.main(
        Namespace(
            base_id="no/lov/2025-01-01-1",
            as_of="2025-02-15",
            data_dir=str(tmp_path),
            index=None,
            commencement=None,
            max_divergences=10,
            json=True,
        )
    )
    payload = json.loads(capsys.readouterr().out)

    assert built == [tmp_path]
    assert payload["error"] == ""
    assert payload["consistent"] is False
    assert payload["divergence_count"] == 1
    assert payload["touched_divergence_count"] == 1
    assert payload["untouched_divergence_count"] == 0


def test_no_divergence_command_answers_from_the_saved_index_it_was_given(tmp_path, monkeypatch, capsys) -> None:
    """``--index FILE`` is how a person skips the build; no index is built then."""
    _write_small_corpus(tmp_path, current_text="en annen tekst")
    index_path = tmp_path / "no_index.json"
    index_path.write_text(json.dumps(build_no_amendment_index(tmp_path).to_dict()), encoding="utf-8")
    monkeypatch.setattr("lawvm.norway.index.build_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.verify.build_no_amendment_index", _index_must_not_be_resolved)
    monkeypatch.setattr("lawvm.norway.replay.build_no_amendment_index", _index_must_not_be_resolved)

    no_divergence.main(
        Namespace(
            base_id="no/lov/2025-01-01-1",
            as_of="2025-02-15",
            data_dir=str(tmp_path),
            index=str(index_path),
            commencement=None,
            max_divergences=10,
            json=True,
        )
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["divergence_count"] == 1
    assert payload["touched_divergence_count"] == 1


@pytest.mark.parametrize("json_output", [True, False])
def test_no_divergence_command_exits_1_when_it_reports_an_error(
    tmp_path, monkeypatch, capsys, json_output: bool
) -> None:
    _write_archive(
        tmp_path / "lovtidend-avd1-2001-2025.tar.bz2",
        [("lti/2025/nl-20250202-005.xml", _AMENDMENT_XML)],
    )
    built = _record_index_builds(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exit_info:
        no_divergence.main(
            Namespace(
                base_id="no/lov/2025-01-01-1",
                as_of="2025-02-15",
                data_dir=str(tmp_path),
                index=None,
                commencement=None,
                max_divergences=10,
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
        assert f"error           : {reason}" in output
    assert built == [tmp_path]
