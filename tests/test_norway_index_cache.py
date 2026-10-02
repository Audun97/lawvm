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
import shutil
import subprocess
import sys
import tarfile
import time
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
    log = directory / "events.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _event_names(directory: Path) -> list[object]:
    return [row["event"] for row in _events(directory)]


def _copy_of(warm_directory: Path, tmp_path: Path) -> Path:
    """The warm cache, copied: a test that adds entries must not show them to the others."""
    directory = tmp_path / "cache"
    shutil.copytree(warm_directory, directory)
    return directory


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
    events = _event_names(directory)
    assert events.count("build_started") == 1, events
    assert events.count("built") == 1, events
    assert len(events) == 3, events
    assert set(events) - {"build_started", "built"} <= {"hit", "hit_after_wait"}, events
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
    assert cache.first_exact_difference(fresh, cached) is None
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


#: A flag the Norway build reads (pinned below, on the real closure), so it is in the key.
_BUILD_FLAG = "LAWVM_MAX_ARCHIVE_MEMBER_BYTES"


def test_a_flag_set_after_the_first_call_gets_its_own_index_and_takes_it_away_again(
    _warm_cache, tmp_path, monkeypatch
) -> None:
    """The memo is per process and a test may set a build flag for its own body. It
    must then get the index built under that flag, and the next test must get the
    plain one back: remembering the first answer by path alone would do neither,
    and no key on disk would ever notice."""
    db_path, warm_directory = _warm_cache
    directory = _copy_of(warm_directory, tmp_path)
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(directory))
    monkeypatch.setattr(cache, "_BLOBS", {})
    monkeypatch.delenv(_BUILD_FLAG, raising=False)
    seen_before = len(_events(directory))

    cache.cached_no_amendment_index(db_path)
    plain_blob = cache._memoized_blob(db_path)
    assert plain_blob is not None

    monkeypatch.setenv(_BUILD_FLAG, "64")
    assert cache._memoized_blob(db_path) is None
    cache.cached_no_amendment_index(db_path)
    flagged_blob = cache._memoized_blob(db_path)
    assert flagged_blob is not None and flagged_blob is not plain_blob

    monkeypatch.delenv(_BUILD_FLAG)
    assert cache._memoized_blob(db_path) is plain_blob
    cache.cached_no_amendment_index(db_path)
    monkeypatch.setenv(_BUILD_FLAG, "64")
    assert cache._memoized_blob(db_path) is flagged_blob
    cache.cached_no_amendment_index(db_path)

    # One lookup and one build, under two keys; the last two calls cost nothing.
    rows = _events(directory)[seen_before:]
    assert [row["event"] for row in rows] == ["hit", "build_started", "built"]
    plain_key, flagged_key = rows[0]["key"], rows[2]["key"]
    assert plain_key != flagged_key
    receipts = {
        key: json.loads((directory / f"{key}.json").read_text(encoding="utf-8"))
        for key in (plain_key, flagged_key)
    }
    assert receipts[plain_key]["inputs"]["env"][_BUILD_FLAG] is None
    assert receipts[flagged_key]["inputs"]["env"][_BUILD_FLAG] == "64"


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
    assert {_BUILD_FLAG, "LAWVM_NO_MUTATION_BOUNDARY_PER_OP"} <= names


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


class _ComesBackAsAPlainDict(dict):
    """A dict subclass whose pickle form forgets the subclass, as ``FrozenDict``'s
    would if its ``__reduce_ex__`` were dropped. It still compares equal."""

    def __reduce__(self):
        return (dict, (dict(self),))


def test_exact_difference_sees_what_equality_cannot() -> None:
    """Liveness for the round-trip check: each loss the JSON pair has on the real
    index is named with its place, and an exact copy has none."""
    from lawvm.core.frozen_values import FrozenDict
    from lawvm.norway.index import NOAmendmentIndex

    built = NOAmendmentIndex(data_dir="d")
    built.diagnostics.append({"rule_id": "r", "detail": FrozenDict({"path": ("a", "b")})})

    as_plain_dict = NOAmendmentIndex(data_dir="d")
    as_plain_dict.diagnostics.append({"rule_id": "r", "detail": {"path": ("a", "b")}})
    assert as_plain_dict == built  # which is why ``==`` is not the check
    assert (
        cache.first_exact_difference(built, as_plain_dict)
        == "index.diagnostics[0]['detail']: FrozenDict became dict"
    )

    as_list = NOAmendmentIndex(data_dir="d")
    as_list.diagnostics.append({"rule_id": "r", "detail": FrozenDict({"path": ["a", "b"]})})
    assert (
        cache.first_exact_difference(built, as_list)
        == "index.diagnostics[0]['detail']['path']: tuple became list"
    )

    other_value = NOAmendmentIndex(data_dir="elsewhere")
    assert cache.first_exact_difference(built, other_value) == (
        "index.data_dir: 'd' became 'elsewhere'"
    )

    # Negative: a pickle round trip of the same object loses nothing.
    assert cache.first_exact_difference(built, pickle.loads(pickle.dumps(built))) is None


def test_an_index_that_pickles_to_an_equal_but_different_object_is_not_stored(
    tmp_path, monkeypatch
) -> None:
    """Through the builder: the copy compares equal to the index, so an ``==`` check
    stores it. The exact check refuses and says which value changed type."""
    db_path = _tiny_archive(tmp_path / "corpus")
    root = _fake_checkout(tmp_path / "checkout")
    directory = tmp_path / "cache"
    directory.mkdir()

    def build_with_a_value_pickle_cannot_restore(data_dir: Path):
        index = build_no_amendment_index(data_dir)
        index.diagnostics.append(_ComesBackAsAPlainDict(rule_id="lossy"))
        assert pickle.loads(pickle.dumps(index)) == index
        return index

    monkeypatch.setattr(cache, "build_no_amendment_index", build_with_a_value_pickle_cannot_restore)
    with pytest.raises(
        cache.NOIndexCacheError,
        match=r"index\.diagnostics\[1\]: _ComesBackAsAPlainDict became dict",
    ):
        cache.build_entry(db_path, directory, root=root)
    assert list(directory.iterdir()) == []


def test_an_entry_pruned_under_a_reader_is_served_or_rebuilt_never_an_error(
    _warm_cache, tmp_path, monkeypatch
) -> None:
    """Another session's build prunes old entries while this one is reading. Pruned
    after the read: the bytes in hand are still the entry. Pruned before it: the
    entry is rebuilt. Neither is a ``FileNotFoundError`` out of a corpus test."""
    db_path, warm_directory = _warm_cache
    directory = _copy_of(warm_directory, tmp_path)
    (entry,) = directory.glob("*.pickle")
    stored = entry.read_bytes()
    seen_before = len(_events(directory))
    touch = os.utime

    def another_session_prunes_first(target, *args, **kwargs):
        cache._prune(directory, keep=0)
        return touch(target, *args, **kwargs)  # raises: the file is gone

    monkeypatch.setattr(cache.os, "utime", another_session_prunes_first)
    assert cache.cached_index_blob(db_path, directory) == stored
    assert not entry.exists()

    monkeypatch.setattr(cache.os, "utime", touch)
    assert cache._read_entry(entry) is None
    rebuilt = pickle.loads(cache.cached_index_blob(db_path, directory))

    assert _event_names(directory)[seen_before:] == ["hit", "build_started", "built"]
    was = pickle.loads(stored)
    was.generated_at_utc = rebuilt.generated_at_utc
    assert cache.first_exact_difference(was, rebuilt) is None


def _lock_is_free(directory: Path) -> bool:
    import fcntl

    with (directory / "build.lock").open("a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(fh, fcntl.LOCK_UN)
        return True


def test_a_build_outlives_the_worker_that_started_it_and_keeps_the_lock(tmp_path) -> None:
    """The out-of-memory killer takes the test worker, not the build it started. The
    build must keep the lock until it is done, or the next worker starts a second
    800 MB build beside it; and what it stores must be usable afterwards."""
    import fcntl

    db_path = _tiny_archive(tmp_path / "corpus")
    directory = tmp_path / "cache"
    worker = subprocess.Popen(
        [sys.executable, "-c", _ONE_CALLER, str(cache._REPO_ROOT), str(db_path), str(directory)]
    )
    deadline = time.monotonic() + 120
    while "build_started" not in _event_names(directory):
        assert worker.poll() is None, "the worker ended before its build started"
        assert time.monotonic() < deadline, "the build child never started"
        time.sleep(0.05)
    worker.kill()
    worker.wait()

    assert not _lock_is_free(directory)
    with (directory / "build.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # returns when the orphaned build ends
        fcntl.flock(fh, fcntl.LOCK_UN)

    assert len(list(directory.glob("*.pickle"))) == 1
    cache.cached_index_blob(db_path, directory)
    assert _event_names(directory) == ["build_started", "hit"]


def test_a_build_that_overruns_is_stopped_and_gives_the_lock_back(tmp_path, monkeypatch) -> None:
    """A hung build would hold every other worker on the lock for good. The child
    stops itself, the caller says how long it was given, and nothing is stored."""
    db_path = _tiny_archive(tmp_path / "corpus")
    directory = tmp_path / "cache"
    monkeypatch.setattr(cache, "BUILD_TIMEOUT_SECONDS", 1)

    with pytest.raises(cache.NOIndexCacheError, match="stopped after 1 s without finishing"):
        cache.cached_index_blob(db_path, directory)

    assert list(directory.glob("*.pickle")) == []
    assert _lock_is_free(directory)


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


# The guard below keeps corpus tests on the cache. Before it, 35 call sites built
# the real-archive index by hand and 10 more reached a build through a replay or
# verify call given no index, which is what made the shard take 39 minutes.
#
# It reads the test source, so it sees what is spelled there and nothing else: a
# build reached through a CLI entry point (``main([...])``, ``no_bench_main``) or
# through an alias of the builder is out of its sight.

_INDEX_BUILDER = "build_no_amendment_index"

#: Calls that build the index themselves when handed none, with the position of
#: ``data_dir`` where it may be passed positionally.
_BUILDS_AN_INDEX_WHEN_GIVEN_NONE: dict[str, int | None] = {
    "replay_no_to_pit": 2,
    "verify_no_against_current": None,
    "build_no_verify_scan": None,
    "build_no_verify_partition": None,
    "build_no_inventory": 0,
    "build_no_no_consolidation_rows": 0,
}

#: Keywords that, all given, make the call derive nothing from an index.
_NEEDS_NO_INDEX_GIVEN = {
    "build_no_no_consolidation_rows": ("base_to_statuses", "base_to_sources"),
}

#: A test that replaces one of these is not building anything.
_BUILDER_SEAMS = ("build_no_amendment_index", "_load_no_index")


def _called(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _is_none(node: ast.expr | None) -> bool:
    return node is None or (isinstance(node, ast.Constant) and node.value is None)


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _positional(call: ast.Call, position: int | None) -> ast.expr | None:
    return call.args[position] if position is not None and len(call.args) > position else None


def _assignments(scope: ast.AST) -> list[tuple[str, ast.expr]]:
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            found.extend((t.id, node.value) for t in node.targets if isinstance(t, ast.Name))
        elif (
            isinstance(node, (ast.AnnAssign, ast.NamedExpr))
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            found.append((node.target.id, node.value))
    return found


def _real_archive_index_builds(source: str) -> list[int]:
    """Line numbers where test source builds the index over the real archive.

    The real archive is followed by name through the module: a path spelled
    ``... / "data" / "norway.farchive"``, ``resolve_no_source_path(None)``, a helper
    or fixture that returns either, and any name assigned from one of those. A call
    is reported when it is the builder on such a value (or on nothing, which is
    the same default), or a replay/verify/inventory call on such a value with no
    ``index=``.
    """
    tree = ast.parse(source)
    functions = [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    module_names: set[str] = set()
    helpers: set[str] = set()

    def is_real(expr: ast.expr, names: set[str]) -> bool:
        strings = [
            node.value
            for node in ast.walk(expr)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        # ``tmp_path / "norway.farchive"`` is a test's own corpus; the real one is
        # the file of that name under ``data``.
        if any(
            "data/norway.farchive" in value or ("norway.farchive" in value and "data" in strings)
            for value in strings
        ):
            return True
        for node in ast.walk(expr):
            if isinstance(node, ast.Name) and node.id in names:
                return True
            if isinstance(node, ast.Call):
                if _called(node) in helpers:
                    return True
                if (
                    _called(node) == "resolve_no_source_path"
                    and _is_none(_positional(node, 0))
                    and _is_none(_keyword(node, "path"))
                ):
                    return True
        return False

    def names_in(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        names = set(module_names)
        # A parameter named after a helper is that helper used as a fixture.
        names.update(a.arg for a in ast.walk(function.args) if isinstance(a, ast.arg) and a.arg in helpers)
        while True:
            more = {
                target
                for target, value in _assignments(function)
                if target not in names and is_real(value, names)
            }
            if not more:
                return names
            names |= more

    while True:  # to a fixpoint: one helper may return what another resolved
        size = (len(module_names), len(helpers))
        for statement in tree.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                module_names.update(
                    target
                    for target, value in _assignments(statement)
                    if is_real(value, module_names)
                )
        for function in functions:
            names = names_in(function)
            if any(
                isinstance(node, ast.Return) and node.value is not None and is_real(node.value, names)
                for node in ast.walk(function)
            ):
                helpers.add(function.name)
        if (len(module_names), len(helpers)) == size:
            break

    def replaces_the_builder(scope: ast.AST) -> bool:
        return any(
            isinstance(node, ast.Call)
            and _called(node) == "setattr"
            and any(
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.endswith(_BUILDER_SEAMS)
                for arg in node.args
            )
            for node in ast.walk(scope)
        )

    def builds_in(scope: ast.AST, names: set[str]) -> set[int]:
        lines: set[int] = set()
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call):
                continue
            called = _called(node)
            if called == _INDEX_BUILDER:
                position: int | None = 0
            elif called in _BUILDS_AN_INDEX_WHEN_GIVEN_NONE:
                position = _BUILDS_AN_INDEX_WHEN_GIVEN_NONE[called]
                given = (
                    not _is_none(_keyword(node, "index"))
                    or not _is_none(_keyword(node, "index_path"))
                    or (position is not None and len(node.args) > position + 1)
                    or (
                        called in _NEEDS_NO_INDEX_GIVEN
                        and not any(
                            _is_none(_keyword(node, name)) for name in _NEEDS_NO_INDEX_GIVEN[called]
                        )
                    )
                )
                if given:
                    continue
            else:
                continue
            source_arg = _positional(node, position) or _keyword(node, "data_dir")
            if _is_none(source_arg) or (source_arg is not None and is_real(source_arg, names)):
                lines.add(node.lineno)
        return lines

    stubbed = {
        node.lineno
        for function in functions
        if replaces_the_builder(function)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    }
    lines = builds_in(tree, module_names)
    for function in functions:
        lines |= builds_in(function, names_in(function))
    return sorted(lines - stubbed)


def test_the_call_site_guard_sees_each_real_archive_spelling_and_no_tmp_corpus() -> None:
    """Liveness for the guard below: every spelling that reaches a real-archive
    build is reported by line, and the ones that do not are left alone."""
    source = '''
_REAL_ARCHIVE = _REPO_ROOT / "data" / "norway.farchive"

def _no_farchive_path():
    fallback = Path(__file__).resolve().parent.parent / "data" / "norway.farchive"
    return fallback if fallback.exists() else None

_NO_FARCHIVE_PATH = _no_farchive_path()

def _no_corpus_dir():
    data_dir = resolve_no_source_path(None)
    if not data_dir.exists():
        pytest.skip("no archive")
    return data_dir

def test_by_module_constant():
    index = build_no_amendment_index(_REAL_ARCHIVE)

def test_by_resolved_default():
    data_dir = resolve_no_source_path(None)
    index = build_no_amendment_index(data_dir)

def test_by_cast_constant():
    data_dir = cast(Path, _NO_FARCHIVE_PATH)
    replay(index=build_no_amendment_index(data_dir))

def test_by_default_argument():
    index = build_no_amendment_index()

def test_by_keyword():
    index = build_no_amendment_index(data_dir=_REAL_ARCHIVE)

def test_by_nested_call():
    index = build_no_amendment_index(resolve_no_source_path(None))

def test_by_helper():
    data_dir = _no_corpus_dir()
    index = build_no_amendment_index(data_dir)

def test_by_another_local_name():
    archive = resolve_no_source_path(None)
    index = build_no_amendment_index(archive)

def test_by_module_attribute():
    index = index_mod.build_no_amendment_index(_REAL_ARCHIVE)

def test_by_fixture(_no_corpus_dir):
    index = build_no_amendment_index(_no_corpus_dir)

def test_replay_given_no_index():
    replay_no_to_pit("no/lov/2020-12-18-156", "2026-07-10", data_dir=_NO_FARCHIVE_PATH)

def test_verify_on_the_default_archive():
    verify_no_against_current("no/lov/2001-01-05-1", as_of="2026-07-10")

def test_inventory_positionally():
    build_no_inventory(_no_corpus_dir())

def test_census_that_derives_its_maps_from_an_index():
    rows = build_no_no_consolidation_rows(_no_corpus_dir(), base_to_statuses={})

def test_census_handed_both_maps():
    build_no_no_consolidation_rows(_no_corpus_dir(), base_to_statuses={}, base_to_sources={})

def test_over_a_tmp_corpus(tmp_path):
    data_dir = tmp_path / "corpus"
    index = build_no_amendment_index(tmp_path)
    other = build_no_amendment_index(data_dir)
    db_path = tmp_path / "norway.farchive"
    third = build_no_amendment_index(db_path)
    replay_no_to_pit("no/lov/2025-01-01-1", "2026-07-10", data_dir=db_path)

def test_given_the_cached_index():
    index = cached_no_amendment_index(_REAL_ARCHIVE)
    replay_no_to_pit("no/lov/2020-12-18-156", "2026-07-10", data_dir=_REAL_ARCHIVE, index=index)
    verify_no_against_current("no/lov/2001-01-05-1", as_of="2026-07-10", index=index)
    replay_no_to_pit("no/lov/2020-12-18-156", "2026-07-10", _REAL_ARCHIVE, index)

def test_with_the_builder_replaced(monkeypatch):
    monkeypatch.setattr("lawvm.norway.verify._load_no_index", lambda **_: SimpleNamespace())
    build_no_verify_partition(as_of="2026-07-10", data_dir=None, limit=10)
'''
    numbered = {number: line for number, line in enumerate(source.splitlines(), start=1)}
    reported = [numbered[number].strip() for number in _real_archive_index_builds(source)]
    assert reported == [
        "index = build_no_amendment_index(_REAL_ARCHIVE)",
        "index = build_no_amendment_index(data_dir)",
        "replay(index=build_no_amendment_index(data_dir))",
        "index = build_no_amendment_index()",
        "index = build_no_amendment_index(data_dir=_REAL_ARCHIVE)",
        "index = build_no_amendment_index(resolve_no_source_path(None))",
        "index = build_no_amendment_index(data_dir)",
        "index = build_no_amendment_index(archive)",
        "index = index_mod.build_no_amendment_index(_REAL_ARCHIVE)",
        "index = build_no_amendment_index(_no_corpus_dir)",
        'replay_no_to_pit("no/lov/2020-12-18-156", "2026-07-10", data_dir=_NO_FARCHIVE_PATH)',
        'verify_no_against_current("no/lov/2001-01-05-1", as_of="2026-07-10")',
        "build_no_inventory(_no_corpus_dir())",
        "rows = build_no_no_consolidation_rows(_no_corpus_dir(), base_to_statuses={})",
    ]


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
    assert cache.first_exact_difference(fresh, cached) is None
