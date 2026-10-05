"""The real-archive Norway amendment index: built once per (code, corpus), then loaded.

WHY THIS EXISTS
---------------
Corpus tests ask for ``build_no_amendment_index(<data/norway.farchive>)`` inside
the test function.  One build is ~87 s and ~800 MB.  On 2026-10-01 the norway
shard had 45 call sites in test code that reached one (35 by hand, 10 inside
replay/verify calls given no index), every build returning the same object, and
four xdist workers building at once pushed a 12 GB laptop into swap, which
stretched each build to 140-290 s.  With the bench sweep's own per-row builds
that was a 39-minute shard.

``cached_no_amendment_index(path)`` returns what ``build_no_amendment_index(path)``
returns, from a disk entry when one exists for exactly these inputs.  A cached
measurement is only worth as much as its staleness detection, so the entry is
named by a digest of everything that decides the answer:

  * CODE — every source file in the static import closure of the replay entry
    points, by AST walk.  The same receipt the occupied-destination sweep
    baseline carries, computed by the same code
    (``scripts/inventory_no_occupied_destination_sweep.py``), read off the tree
    ``lawvm`` was actually imported from.
  * CORPUS — every artifact in every Norway plane as
    ``(logical_id, sha256(payload))``, plus the archive's size and mtime, which
    the index records in ``archive_metadata``.
  * RUNTIME — the Python version and the third-party distributions the closure
    imports.
  * ENVIRONMENT — the value of every ``LAWVM_*`` variable the closure names.

An edit to any Norway module therefore misses the cache and rebuilds.  A false
miss costs one build; that is why the key is wide.

THREE DECISIONS THAT ARE NOT OBVIOUS
------------------------------------
PICKLE, NOT ``save_no_amendment_index``.  When this was written the JSON round trip
was lossy on the real index (every entry's status came back a ``str``, and 2,231 of
15,180 diagnostics had ``tuple`` turned into ``list``, ``FrozenDict`` into ``dict``
or an enum into ``str``).  W-111 made it exact, and
``test_real_corpus_saved_index_loads_as_the_index_that_was_built`` pins that, so
the choice is now one of speed only: an entry is unpickled once per call, 0.09 s
against 0.3 s for the JSON.  The builder checks the pickle round trip before it
stores anything, with ``first_exact_difference`` rather than ``==``: ``FrozenDict``
is a ``dict`` subclass, so ``==`` cannot see a copy that came back with plain dicts.
The entry is only ever read back from the directory this module wrote it to.

THE BUILD RUNS IN A CHILD PROCESS.  A test worker is the wrong place to build a
shared entry: a ``monkeypatch`` still active in it would be cached for everyone,
and its modules may have been imported before a file on disk was edited.  The
child imports the code fresh, computes the key itself before and after the build,
and stores nothing if the two differ.  The worker then looks the entry up under
its own key, so an entry is only ever used by a process that agrees on the inputs.
The child inherits the build lock and stops itself after ``BUILD_TIMEOUT_SECONDS``,
so a worker killed mid-build leaves neither a second build beside the first nor a
lock nobody will release.

EVERY CALL GETS ITS OWN OBJECT.  The entry is unpickled per call, so one test
mutating its index cannot reach another, exactly as when each test built its own.
The bytes are remembered per process, together with the environment flags they
were keyed on, and reused only while those flags still hold: a test that sets one
gets the index built under it, and the next test gets the plain one back.

WHAT THE KEY CANNOT SEE.  The key is read off the files on disk, once per process
and flag setting.  A process that already imported a module and then has it edited
under it will pair old replay code with an index built by the new code.  Do not
edit Norway code while the shard runs; re-run if you did.

``generated_at_utc`` is the one field that differs from a fresh build: it is the
time the entry was built.

Knobs: ``LAWVM_NORWAY_INDEX_CACHE=off`` builds in-process every time, as before.
``LAWVM_NORWAY_INDEX_CACHE_DIR`` moves the cache (default ``.tmp/norway-index-cache``).
``events.jsonl`` in that directory records every hit, build and refusal, and each
entry's ``<key>.json`` lists the inputs it was built from, module by module, so
"why did it rebuild" is a diff of two receipts.  Deleting the directory is always
safe.  ``tests/test_norway_index_cache.py`` holds the guard that keeps new corpus
tests on this path.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import hashlib
import importlib.util
import json
import os
import pickle
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import IO, Any, Iterator

import lawvm
from lawvm.norway.index import NOAmendmentIndex, build_no_amendment_index
from lawvm.norway.sources import is_no_farchive_path, resolve_no_source_path

#: ``fcntl`` is POSIX only; without it the cache refuses and every call builds in-process.
_HAS_FLOCK = importlib.util.find_spec("fcntl") is not None

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SWEEP_SCRIPT_PATH = _REPO_ROOT / "scripts" / "inventory_no_occupied_destination_sweep.py"

#: Bump when the entry layout or the meaning of a key input changes.
CACHE_SCHEMA = 1
CACHE_SWITCH_ENV = "LAWVM_NORWAY_INDEX_CACHE"
CACHE_DIR_ENV = "LAWVM_NORWAY_INDEX_CACHE_DIR"
DEFAULT_CACHE_DIR = _REPO_ROOT / ".tmp" / "norway-index-cache"

#: Entries kept after a build, newest first.  A before/after comparison needs
#: two; the rest is slack for switching between branches.
KEEP_ENTRIES = 4

#: How long the build child may run before it stops itself.  A build is ~90 s and
#: has been seen at 290 s on a swapping laptop; past this it is hung, and every
#: other worker is waiting on its lock.
BUILD_TIMEOUT_SECONDS = 900

_ENV_NAME_RE = re.compile(r"\bLAWVM_[A-Z0-9_]+\b")

#: Pickled entries this process already resolved, by the path string asked for,
#: each with the environment-flag values its key was computed from.
_BLOBS: dict[str, list[tuple[dict[str, str | None], bytes]]] = {}


class NOIndexCacheError(RuntimeError):
    """The cache could not produce an entry it can vouch for.

    Raised instead of falling back to an in-process build: by the time this
    fires the inputs are moving under a running test session, and a quiet
    fallback would turn that into an unexplained slow run.
    """


@functools.cache
def _sweep() -> ModuleType:
    """The sweep script, imported by path: it owns the code and corpus digests."""
    spec = importlib.util.spec_from_file_location(
        "lawvm_inventory_no_occupied_destination_sweep", _SWEEP_SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lawvm_package_file() -> Path:
    assert lawvm.__file__ is not None
    return Path(lawvm.__file__).resolve()


def source_root() -> Path | None:
    """The checkout ``lawvm`` was imported from, or ``None`` when it is not one.

    The code digest has to be read off the files that are actually running, which
    is not always this repo: a before/after comparison points ``PYTHONPATH`` at
    another worktree's ``src``.
    """
    package_file = _lawvm_package_file()
    root = package_file.parents[2]
    return root if root / "src" / "lawvm" / "__init__.py" == package_file else None


def cache_dir() -> Path:
    override = os.environ.get(CACHE_DIR_ENV)
    return Path(override) if override else DEFAULT_CACHE_DIR


def cache_refusal(data_dir: Path) -> str | None:
    """Why this call must build in-process, or ``None`` when the cache may serve it."""
    if os.environ.get(CACHE_SWITCH_ENV, "").strip().lower() in {"0", "off", "false", "no"}:
        return f"{CACHE_SWITCH_ENV} is off"
    if not _HAS_FLOCK:
        return "no fcntl file locking on this platform"
    if not (is_no_farchive_path(data_dir) and data_dir.is_file()):
        # A tar directory also feeds the build its unmapped members, which the
        # corpus digest deliberately leaves out.
        return "source is not an farchive file"
    if source_root() is None:
        return "lawvm is not imported from a source checkout, so its code cannot be digested"
    return None


def cache_key_inputs(data_dir: Path, *, root: Path | None = None) -> dict[str, Any]:
    """Everything that decides what ``build_no_amendment_index(data_dir)`` returns."""
    sweep = _sweep()
    root = root or source_root()
    assert root is not None, "cache_refusal() must be consulted first"
    stat = data_dir.stat()
    env_names: set[str] = set()
    for path in sweep.code_closure(root).values():
        env_names.update(_ENV_NAME_RE.findall(path.read_text(encoding="utf-8")))
    return {
        "schema": CACHE_SCHEMA,
        "data_dir": str(data_dir),
        "archive_stat": {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
        "corpus": sweep.corpus_identity(data_dir),
        "code": sweep.code_identity(root),
        "runtime": {**sweep.runtime_identity(root), "python_full": sys.version},
        "env": {name: os.environ.get(name) for name in sorted(env_names)},
    }


def cache_key(inputs: dict[str, Any]) -> str:
    canonical = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _entry_path(directory: Path, key: str) -> Path:
    return directory / f"{key}.pickle"


def _record(directory: Path, event: str, **fields: Any) -> None:
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "event": event,
        "test": os.environ.get("PYTEST_CURRENT_TEST", ""),
        **fields,
    }
    with (directory / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


@contextmanager
def _build_lock(directory: Path) -> Iterator[IO[str]]:
    """One build at a time per cache directory, across processes.

    Also what keeps four xdist workers that miss together from building four
    times: three wait here and then find the entry.  Yields the locked file so
    the build child can be handed it (see ``_build_in_child``).
    """
    import fcntl

    with (directory / "build.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield fh
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _read_entry(entry: Path) -> bytes | None:
    """The entry's bytes, or ``None`` when there is no such entry.

    Reading is the test for existence.  Another session's build prunes old
    entries without asking this one, so an ``exists()`` followed by a read can
    fail in between; here the entry is either read whole or reported missing.
    """
    try:
        blob = entry.read_bytes()
    except FileNotFoundError:
        return None
    # Recency, for _prune.  Pruned since the read: the bytes are still the entry.
    with contextlib.suppress(FileNotFoundError):
        os.utime(entry)
    return blob


def first_exact_difference(left: Any, right: Any, where: str = "index") -> str | None:
    """Where ``right`` first stops being ``left``, exact types included; ``None`` if nowhere.

    ``==`` is too weak for "the cached index is the built index": ``FrozenDict``
    is a ``dict`` subclass, so a copy that came back with plain dicts still
    compares equal.  The answer names the place, so a failure says what was lost.
    """
    if type(left) is not type(right):
        return f"{where}: {type(left).__name__} became {type(right).__name__}"
    if dataclasses.is_dataclass(left):
        for field in dataclasses.fields(left):
            found = first_exact_difference(
                getattr(left, field.name), getattr(right, field.name), f"{where}.{field.name}"
            )
            if found is not None:
                return found
        return None
    if isinstance(left, dict):
        if list(left) != list(right):
            return f"{where}: keys {list(left)!r:.200} became {list(right)!r:.200}"
        for key in left:
            found = first_exact_difference(left[key], right[key], f"{where}[{key!r}]")
            if found is not None:
                return found
        return None
    if isinstance(left, (list, tuple)):
        if len(left) != len(right):
            return f"{where}: {len(left)} items became {len(right)}"
        for position, (was, now) in enumerate(zip(left, right, strict=True)):
            found = first_exact_difference(was, now, f"{where}[{position}]")
            if found is not None:
                return found
        return None
    return None if left == right else f"{where}: {left!r:.200} became {right!r:.200}"


def _prune(directory: Path, *, keep: int = KEEP_ENTRIES) -> list[str]:
    """Drop all but the ``keep`` most recently used entries; return the dropped keys."""
    entries = sorted(directory.glob("*.pickle"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    dropped = []
    for entry in entries[keep:]:
        entry.unlink()
        entry.with_suffix(".json").unlink(missing_ok=True)
        dropped.append(entry.stem)
    return dropped


def build_entry(data_dir: Path, directory: Path, *, root: Path | None = None) -> str:
    """Build in THIS process and store the result under the key it was built from.

    Runs in the child (``python tests/norway_index_cache.py``); tests call it
    directly to drive the refusals.  The key is computed before and after the
    build and nothing is stored when they differ, so an entry never names inputs
    it was not built from.
    """
    before = cache_key_inputs(data_dir, root=root)
    started = time.perf_counter()
    index = build_no_amendment_index(data_dir)
    seconds = round(time.perf_counter() - started, 2)
    if cache_key_inputs(data_dir, root=root) != before:
        raise NOIndexCacheError(
            "The code, corpus or environment changed while the Norway amendment index "
            "was building, so the result matches no key and was not stored. Re-run "
            "once the tree is at rest."
        )
    blob = pickle.dumps(index, protocol=pickle.HIGHEST_PROTOCOL)
    lost = first_exact_difference(index, pickle.loads(blob))
    if lost is not None:
        raise NOIndexCacheError(
            "The Norway amendment index does not survive a pickle round trip, so it "
            f"cannot be cached. First difference: {lost}. Give that type a pickle "
            f"form that restores it, or set {CACHE_SWITCH_ENV}=off to run without "
            "the cache."
        )
    key = cache_key(before)
    entry = _entry_path(directory, key)
    scratch = entry.with_suffix(f".{os.getpid()}.tmp")
    scratch.write_bytes(blob)
    os.replace(scratch, entry)
    receipt = {
        "key": key,
        "built_at_utc": index.generated_at_utc,
        "build_seconds": seconds,
        "entries": len(index.entries),
        "diagnostics": len(index.diagnostics),
        "commencement_instruments": len(index.commencement_instruments),
        "inputs": before,
    }
    entry.with_suffix(".json").write_text(
        json.dumps(receipt, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    _prune(directory)
    return key


def _build_in_child(data_dir: Path, directory: Path, lock: IO[str]) -> None:
    """Build the entry in a fresh process that holds ``lock`` for as long as it lives.

    The child inherits the locked file, and a lock is released only when every
    process holding the file has closed it.  So when this process is killed
    mid-build (the laptop's out-of-memory killer picks exactly the big ones) the
    build that is still running keeps the others waiting, instead of a second
    ~800 MB build starting beside it.
    """
    cmd = [
        sys.executable,
        "-P",  # keep tests/ off sys.path: this file runs as a script, not a package member
        str(Path(__file__).resolve()),
        "--data-dir",
        str(data_dir),
        "--cache-dir",
        str(directory),
        "--expect-lawvm",
        str(_lawvm_package_file()),
        "--timeout",
        str(BUILD_TIMEOUT_SECONDS),
    ]
    done = subprocess.run(cmd, capture_output=True, text=True, pass_fds=(lock.fileno(),))
    if done.returncode == -signal.SIGALRM:
        raise NOIndexCacheError(
            "The Norway amendment index build for the test cache was stopped after "
            f"{BUILD_TIMEOUT_SECONDS} s without finishing; a build is about 90 s. "
            "Check free memory (`free -m`) and for leftover build processes "
            "(`pgrep -af norway_index_cache`), then re-run."
        )
    if done.returncode != 0:
        raise NOIndexCacheError(
            "The Norway amendment index build for the test cache failed "
            f"(exit {done.returncode}). Child stderr, last lines:\n"
            + "\n".join(done.stderr.strip().splitlines()[-25:])
        )


def _resolve_entry(data_dir: Path, directory: Path) -> tuple[dict[str, Any], bytes]:
    """The key inputs this process computes for ``data_dir``, and the entry stored under them."""
    directory.mkdir(parents=True, exist_ok=True)
    key = ""
    # Two attempts: when a file moved between this process computing its key and
    # the child computing its own, the child stored under a newer key, and the
    # second pass recomputes and finds it.
    for _attempt in range(2):
        started = time.perf_counter()
        inputs = cache_key_inputs(data_dir)
        key = cache_key(inputs)
        entry = _entry_path(directory, key)
        event = "hit"
        blob = _read_entry(entry)
        if blob is None:
            with _build_lock(directory) as lock:
                blob = _read_entry(entry)
                if blob is not None:
                    event = "hit_after_wait"
                else:
                    event = "built"
                    _build_in_child(data_dir, directory, lock)
                    blob = _read_entry(entry)
        seconds = round(time.perf_counter() - started, 2)
        if blob is not None:
            _record(directory, event, key=key, seconds=seconds)
            return inputs, blob
        _record(directory, "key_moved", key=key, seconds=seconds)
    raise NOIndexCacheError(
        "The Norway amendment index was built twice and neither build matched the key "
        f"this process computes ({key}). The code or corpus is being edited under a "
        f"running test session; re-run once the tree is at rest, or set "
        f"{CACHE_SWITCH_ENV}=off."
    )


def cached_index_blob(data_dir: Path, directory: Path) -> bytes:
    """The pickled index for ``data_dir``: read from ``directory``, built into it on a miss."""
    return _resolve_entry(data_dir, directory)[1]


def _memoized_blob(path: Path) -> bytes | None:
    """An entry this process already resolved for ``path``, if it is still the answer.

    It is while every environment flag in its key has the value it had then.  A
    test that sets one (``LAWVM_MAX_ARCHIVE_MEMBER_BYTES``, say) must get the
    index built under it and must not leave that index behind for the next test.
    """
    for env, blob in _BLOBS.get(str(path), ()):
        if all(os.environ.get(name) == value for name, value in env.items()):
            return blob
    return None


def cached_no_amendment_index(data_dir: Path | None = None) -> NOAmendmentIndex:
    """``build_no_amendment_index(data_dir)``, from the disk cache when it may serve.

    A drop-in for corpus tests that build the index over the real archive.  Tests
    of the builder itself, and anything over a ``tmp_path`` corpus, should keep
    calling ``build_no_amendment_index``: those builds are milliseconds and are
    the thing under test.
    """
    path = resolve_no_source_path(data_dir)
    refusal = cache_refusal(path)
    if refusal is not None:
        directory = cache_dir()
        if directory.is_dir():
            _record(directory, "refused", reason=refusal, data_dir=str(path))
        return build_no_amendment_index(path)
    blob = _memoized_blob(path)
    if blob is None:
        inputs, blob = _resolve_entry(path, cache_dir())
        _BLOBS.setdefault(str(path), []).append((inputs["env"], blob))
    return pickle.loads(blob)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Norway amendment index into the test cache."
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--expect-lawvm",
        type=Path,
        default=None,
        help="Fail unless lawvm was imported from this file (the parent's lawvm).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Stop this process after so many seconds (0: never).",
    )
    args = parser.parse_args(argv)
    if args.timeout > 0:
        # The default action for SIGALRM ends the process, hung or not, which
        # also closes the inherited build lock.  Nobody else can do this once
        # the test worker that started the build is gone.
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(args.timeout)
    if args.expect_lawvm is not None and args.expect_lawvm != _lawvm_package_file():
        print(
            f"lawvm resolved to {_lawvm_package_file()} in the build process but to "
            f"{args.expect_lawvm} in the test process; refusing to build for another tree.",
            file=sys.stderr,
        )
        return 3
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    _record(args.cache_dir, "build_started", data_dir=str(args.data_dir))
    print(build_entry(args.data_dir, args.cache_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
