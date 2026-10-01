"""The test-side Norway amendment index cache (``tests/norway_index_cache.py``).

A cache that can serve a stale index hides exactly the regression the corpus pins
exist to catch, so what is pinned here is the staleness detection and the refusals,
each driven until it fires, plus the one property the cache is for: the object it
returns is the object a fresh build returns.
"""

from __future__ import annotations

import ast
import io
import json
import os
import pickle
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.sources import ingest_no_public_archives, resolve_no_source_path
from tests import norway_index_cache as cache


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


def _write_tar(archive_path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(archive_path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def _tiny_archive(directory: Path, *, amendments: tuple[str, ...] = ("2025-02-10",)) -> Path:
    """A one-law farchive with one amendment act per commencement date given."""
    directory.mkdir(parents=True, exist_ok=True)
    _write_tar(directory / "gjeldende-lover.tar.bz2", [("nl/nl-20250101-001.xml", _BASE_XML)])
    members = [("lti/2025/nl-20250101-001.xml", _BASE_XML)]
    for number, date_in_force in enumerate(amendments, start=5):
        members.append((f"lti/2025/nl-20250202-{number:03d}.xml", _amendment_xml(date_in_force)))
    _write_tar(directory / "lovtidend-avd1-2025.tar.bz2", members)
    db_path = directory / "norway.farchive"
    db_path.unlink(missing_ok=True)
    ingest_no_public_archives(directory, db_path)
    return db_path


def _fake_checkout(root: Path) -> Path:
    """A source tree just big enough for the closure walk: index imports replay."""
    package = root / "src" / "lawvm" / "norway"
    package.mkdir(parents=True)
    (root / "src" / "lawvm" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "index.py").write_text(
        "import os\nfrom lawvm.norway import replay\n"
        "LIMIT = os.environ.get('LAWVM_FAKE_BUILD_LIMIT')\n",
        encoding="utf-8",
    )
    (package / "replay.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "inventory.py").write_text("", encoding="utf-8")
    return root


def _events(directory: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


#: One caller of the cache, as its own process: xdist workers are processes, and
#: the archive reader is not safe to drive from two threads of one.
_ONE_CALLER = (
    "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
    "from tests import norway_index_cache as cache; "
    "cache.cached_index_blob(Path(sys.argv[2]), Path(sys.argv[3]))"
)


@pytest.fixture(scope="module")
def _warm_cache(tmp_path_factory) -> tuple[Path, Path]:
    """A tiny archive and a cache directory two processes raced to fill."""
    base = tmp_path_factory.mktemp("no_index_cache")
    db_path = _tiny_archive(base / "corpus")
    directory = base / "cache"
    callers = [
        subprocess.Popen(
            [sys.executable, "-c", _ONE_CALLER, str(cache._REPO_ROOT), str(db_path), str(directory)]
        )
        for _n in range(2)
    ]
    assert [caller.wait() for caller in callers] == [0, 0]
    return db_path, directory


def test_a_cold_cache_builds_once_however_many_callers_miss_together(_warm_cache) -> None:
    """Four xdist workers miss at the same instant on a cold run. One build, not four:
    the rest wait on the lock and then read the entry the first one stored."""
    _db_path, directory = _warm_cache
    events = [row["event"] for row in _events(directory)]
    assert len(events) >= 2, events
    assert events.count("built") == 1, events
    assert set(events) - {"built"} <= {"hit", "hit_after_wait"}, events
    assert len(list(directory.glob("*.pickle"))) == 1


def test_the_cached_index_is_the_index_a_fresh_build_returns(_warm_cache) -> None:
    """The whole claim, through the production path: the entry was built by the
    child process and read back here, and it equals a build made in this process.
    ``generated_at_utc`` is the build's own clock reading and is aligned first."""
    db_path, directory = _warm_cache
    cached = pickle.loads(cache.cached_index_blob(db_path, directory))
    fresh = build_no_amendment_index(db_path)
    assert cached.generated_at_utc != ""
    fresh.generated_at_utc = cached.generated_at_utc
    assert cached == fresh
    assert cached.source_kind == "farchive"
    assert [entry.source_id for entry in cached.entries] == ["no/lovtid/2025-02-02-5"]


def test_every_call_gets_its_own_object(_warm_cache, monkeypatch) -> None:
    """One test mutating its index must not reach the next, as when each built its own."""
    db_path, directory = _warm_cache
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(directory))
    monkeypatch.setattr(cache, "_BLOBS", {})
    first = cache.cached_no_amendment_index(db_path)
    first.entries.clear()
    first.diagnostics.append({"rule_id": "poisoned_by_a_neighbouring_test"})

    second = cache.cached_no_amendment_index(db_path)

    assert second is not first
    assert len(second.entries) == 1
    assert {"rule_id": "poisoned_by_a_neighbouring_test"} not in second.diagnostics


def test_the_key_moves_when_the_corpus_moves(tmp_path) -> None:
    """Same path, one more amendment act in the archive: a different key, and the
    receipt says it was the amendment plane that grew."""
    db_path = _tiny_archive(tmp_path)
    before = cache.cache_key_inputs(db_path)
    _tiny_archive(tmp_path, amendments=("2025-02-10", "2025-03-01"))
    after = cache.cache_key_inputs(db_path)

    assert cache.cache_key(before) != cache.cache_key(after)
    planes_before = {p["plane"]: p["artifacts"] for p in before["corpus"]["planes"]}
    planes_after = {p["plane"]: p["artifacts"] for p in after["corpus"]["planes"]}
    assert planes_after["amendment"] == planes_before["amendment"] + 1
    assert before["code"] == after["code"]


def test_the_key_moves_when_a_module_in_the_closure_is_edited(tmp_path) -> None:
    """The W-67 shape: the archive did not move, the code did. Editing a module the
    index only reaches through an import is enough."""
    db_path = _tiny_archive(tmp_path / "corpus")
    root = _fake_checkout(tmp_path / "checkout")
    before = cache.cache_key_inputs(db_path, root=root)
    assert cache.cache_key(cache.cache_key_inputs(db_path, root=root)) == cache.cache_key(before)

    (root / "src" / "lawvm" / "norway" / "replay.py").write_text("VALUE = 2\n", encoding="utf-8")
    after = cache.cache_key_inputs(db_path, root=root)

    assert cache.cache_key(before) != cache.cache_key(after)
    moved = [
        was["module"]
        for was, now in zip(before["code"]["files"], after["code"]["files"], strict=True)
        if was["digest"] != now["digest"]
    ]
    assert moved == ["lawvm.norway.replay"]
    assert before["corpus"] == after["corpus"]


def test_the_key_tracks_the_environment_flags_the_closure_reads_and_no_others(
    tmp_path, monkeypatch
) -> None:
    """A flag the code reads decides the build, so it is in the key. A flag it never
    names is not: the CI run id changes every run and must not empty the cache."""
    db_path = _tiny_archive(tmp_path / "corpus")
    root = _fake_checkout(tmp_path / "checkout")
    monkeypatch.delenv("LAWVM_FAKE_BUILD_LIMIT", raising=False)
    before = cache.cache_key_inputs(db_path, root=root)
    assert before["env"] == {"LAWVM_FAKE_BUILD_LIMIT": None}

    monkeypatch.setenv("LAWVM_SHARD_TIMING_RUN_ID", "another-run")
    assert cache.cache_key(cache.cache_key_inputs(db_path, root=root)) == cache.cache_key(before)

    monkeypatch.setenv("LAWVM_FAKE_BUILD_LIMIT", "1")
    assert cache.cache_key(cache.cache_key_inputs(db_path, root=root)) != cache.cache_key(before)


def test_the_real_closure_names_the_flags_the_norway_build_reads() -> None:
    """Liveness for the environment half of the key on the real tree: a regex that
    quietly matched nothing would give a stable key and a guard that cannot fire."""
    data_dir = resolve_no_source_path(None)
    if cache.cache_refusal(data_dir) is not None:
        pytest.skip("local Norway farchive is not installed")
    root = cache.source_root()
    assert root is not None
    names: set[str] = set()
    for path in cache._sweep().code_closure(root).values():
        names.update(cache._ENV_NAME_RE.findall(path.read_text(encoding="utf-8")))
    assert {"LAWVM_MAX_ARCHIVE_MEMBER_BYTES", "LAWVM_NO_MUTATION_BOUNDARY_PER_OP"} <= names


def test_an_entry_is_not_stored_when_the_inputs_move_during_the_build(
    tmp_path, monkeypatch
) -> None:
    """A file saved while the index is building: the result matches neither the key
    from before nor the key from after, so it is stored under neither."""
    db_path = _tiny_archive(tmp_path / "corpus")
    root = _fake_checkout(tmp_path / "checkout")
    directory = tmp_path / "cache"
    directory.mkdir()

    def build_while_someone_saves_a_file(data_dir: Path):
        (root / "src" / "lawvm" / "norway" / "replay.py").write_text("VALUE = 3\n", encoding="utf-8")
        return build_no_amendment_index(data_dir)

    monkeypatch.setattr(cache, "build_no_amendment_index", build_while_someone_saves_a_file)
    with pytest.raises(cache.NOIndexCacheError, match="changed while"):
        cache.build_entry(db_path, directory, root=root)
    assert list(directory.iterdir()) == []

    # Negative: at rest, the same call stores an entry and names it by the key.
    monkeypatch.setattr(cache, "build_no_amendment_index", build_no_amendment_index)
    key = cache.build_entry(db_path, directory, root=root)
    assert key == cache.cache_key(cache.cache_key_inputs(db_path, root=root))
    assert sorted(p.name for p in directory.iterdir()) == [f"{key}.json", f"{key}.pickle"]
    receipt = json.loads((directory / f"{key}.json").read_text(encoding="utf-8"))
    assert receipt["entries"] == 1
    assert [f["module"] for f in receipt["inputs"]["code"]["files"]] == [
        "lawvm",
        "lawvm.norway",
        "lawvm.norway.index",
        "lawvm.norway.inventory",
        "lawvm.norway.replay",
    ]


def test_the_child_refuses_to_build_for_another_tree(tmp_path, capsys) -> None:
    """The build process must be running the code the test process is running."""
    db_path = _tiny_archive(tmp_path / "corpus")
    code = cache._main(
        [
            "--data-dir",
            str(db_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--expect-lawvm",
            str(tmp_path / "elsewhere" / "src" / "lawvm" / "__init__.py"),
        ]
    )
    assert code == 3
    assert "refusing to build for another tree" in capsys.readouterr().err
    assert not (tmp_path / "cache").exists()


def test_the_cache_steps_aside_and_builds_in_process_when_it_cannot_vouch(
    tmp_path, monkeypatch
) -> None:
    """Switched off, or a tar directory rather than an farchive: no entry is written
    and the caller still gets a correct index, built the way it always was."""
    db_path = _tiny_archive(tmp_path)
    directory = tmp_path / "cache"
    directory.mkdir()
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(directory))
    monkeypatch.setattr(cache, "_BLOBS", {})

    assert cache.cache_refusal(db_path) is None
    assert cache.cache_refusal(tmp_path) == "source is not an farchive file"
    from_directory = cache.cached_no_amendment_index(tmp_path)
    assert from_directory.source_kind == "dir"
    assert len(from_directory.entries) == 1

    monkeypatch.setenv(cache.CACHE_SWITCH_ENV, "off")
    assert cache.cache_refusal(db_path) == f"{cache.CACHE_SWITCH_ENV} is off"
    switched_off = cache.cached_no_amendment_index(db_path)
    assert switched_off.source_kind == "farchive"

    assert list(directory.glob("*.pickle")) == []
    assert [row["event"] for row in _events(directory)] == ["refused", "refused"]


def test_prune_keeps_the_most_recently_used_entries(tmp_path) -> None:
    for age, key in enumerate(("newest", "newer", "older", "oldest")):
        entry = tmp_path / f"{key}.pickle"
        entry.write_bytes(b"")
        entry.with_suffix(".json").write_text("{}", encoding="utf-8")
        os.utime(entry, ns=(10**18 - age * 10**9, 10**18 - age * 10**9))
    (tmp_path / "events.jsonl").write_text("", encoding="utf-8")

    assert cache._prune(tmp_path, keep=2) == ["older", "oldest"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "events.jsonl",
        "newer.json",
        "newer.pickle",
        "newest.json",
        "newest.pickle",
    ]


# The spellings a corpus test uses for the real archive. A test that hands one of
# them to ``build_no_amendment_index`` pays a full build for an object the cache
# already holds; 35 call sites did, which is what made the shard take 39 minutes.
_REAL_ARCHIVE_NAMES = frozenset({"_REAL_ARCHIVE", "_NO_FARCHIVE_PATH"})


def _real_archive_index_builds(source: str) -> list[int]:
    """Line numbers where test source builds the index over the real archive."""

    def names_the_real_archive(function: ast.AST) -> bool:
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and node.id in _REAL_ARCHIVE_NAMES:
                return True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "resolve_no_source_path"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value is None
            ):
                return True
        return False

    lines: list[int] = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "build_no_amendment_index"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
            ):
                continue
            argument = node.args[0].id
            if argument in _REAL_ARCHIVE_NAMES or (
                argument == "data_dir" and names_the_real_archive(function)
            ):
                lines.append(node.lineno)
    return sorted(set(lines))


def test_the_call_site_guard_sees_each_real_archive_spelling_and_no_tmp_corpus() -> None:
    """Liveness for the guard below, on the three spellings it replaced and on the
    one it must leave alone."""
    source = """
def test_by_module_constant():
    index = build_no_amendment_index(_REAL_ARCHIVE)

def test_by_resolved_default():
    data_dir = resolve_no_source_path(None)
    index = build_no_amendment_index(data_dir)

def test_by_cast_constant():
    data_dir = cast(Path, _NO_FARCHIVE_PATH)
    replay(index=build_no_amendment_index(data_dir))

def test_over_a_tmp_corpus(tmp_path):
    data_dir = tmp_path / "corpus"
    index = build_no_amendment_index(tmp_path)
    other = build_no_amendment_index(data_dir)
"""
    assert _real_archive_index_builds(source) == [3, 7, 11]


def test_no_norway_test_builds_the_real_index_by_hand() -> None:
    """Every corpus test takes the real-archive index from the cache. A new one that
    builds it adds about 90 s and 800 MB to every run of the shard, per test."""
    offenders = {
        path.name: lines
        for path in sorted(Path(__file__).parent.glob("test_no*.py"))
        if path.name != Path(__file__).name
        and (lines := _real_archive_index_builds(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}, (
        "These tests build the Norway amendment index over the real archive. Use "
        "`cached_no_amendment_index(...)` from tests/norway_index_cache.py instead "
        f"(same object, built once per code and corpus state): {offenders}"
    )


@pytest.mark.slow
def test_real_corpus_cached_index_equals_a_fresh_build() -> None:
    """The deliberate lever (``pytest -m slow -k cached_index_equals``, about 90 s):
    over the real archive, what the cache serves is what a build in this process
    returns, field for field. The synthetic test above proves the mechanism; this
    one proves it on the entries and diagnostics the corpus pins actually read."""
    data_dir = resolve_no_source_path(None)
    if cache.cache_refusal(data_dir) is not None:
        pytest.skip("local Norway farchive is not installed")
    cached = cache.cached_no_amendment_index(data_dir)
    fresh = build_no_amendment_index(data_dir)
    fresh.generated_at_utc = cached.generated_at_utc
    assert cached.entries == fresh.entries
    assert cached.commencement_instruments == fresh.commencement_instruments
    assert cached.diagnostics == fresh.diagnostics
    assert cached == fresh
