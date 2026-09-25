#!/usr/bin/env python
"""Corpus-wide ``(RENUMBER, dest_occupied)`` sweep + its staleness receipt (W-72).

WHY THIS EXISTS
---------------
``tests/test_no_renumber_migration.py`` pins every ``(RENUMBER, dest_occupied)``
recovery firing per-op in ``_NO_OCCUPIED_DESTINATION_VERDICTS``, and asserts the
wrong-list is empty — "no adjudicated occupied-destination removal destroys live
law".  Until W-72 that pin replayed only the laws hardcoded in
``_NO_OCCUPIED_DESTINATION_LAWS``, so the claim was true of nine laws while its
docstring asserted it of the corpus.  W-67 proved the gap is not theoretical: it
lowered a renumber that destroyed husbankloven § 13, and because husbankloven was
not on the list the whole ladder stayed GREEN with a destruction in the corpus.

Replaying all 783 base laws is ~10 CPU-minutes, which does not fit the norway
shard.  So the sweep runs HERE, and commits its result as a baseline the test
compares against.  A cached measurement is only worth as much as its staleness
detection, so the baseline carries a receipt of the two things that decide the
answer, and the test recomputes BOTH cheaply:

  * CORPUS IDENTITY — every artifact in every Norway plane, as
    ``(logical_id, sha256(payload))``, digested per plane.  ~2s.  Immune to
    physical churn (VACUUM, WAL, recompression) because it digests logical
    content, not the file.
  * CODE IDENTITY — the sha256 of every source file in the STATIC IMPORT CLOSURE
    of the replay entry points, derived by AST walk rather than hand-listed.
    ~0.3s.  This is the half a corpus-only receipt would have missed, and it is
    exactly the half W-67 needed: the archive did not move, the parser did.

Together with the pinned ``as_of`` and the determinism firewall
(``notes/DETERMINISM_FIREWALL.md``), those two fix the sweep's answer.  A change
to either makes the test FAIL with a regenerate instruction rather than pass on
stale data.  The residual is the third-party runtime: its versions are RECORDED
in the baseline for triage but deliberately not asserted, because worktree venvs
resolve extras differently and a false red trains reflexive regeneration, which
is the one failure mode that would defeat the whole mechanism.

The sweep also carries W-73's rider census (the known-incomplete-base hazard),
because it is the same replay pass: a base is KNOWN-INCOMPLETE when its own
replay receipted at least one SKIPPED amendment, and a write is DESTRUCTIVE when
its landed footprint removes, replaces or renumbers existing content.  The
intersection is the posture that produced the husbankloven destruction.  Pinning
the census does not fix the hazard; it stops the number drifting silently.

usage:
  uv run python scripts/inventory_no_occupied_destination_sweep.py
  uv run python scripts/inventory_no_occupied_destination_sweep.py --update-baseline
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Iterable

BASELINE_PATH = "tests/data/no_occupied_destination_sweep_baseline.json"

#: The point in time the sweep replays to.  A CONSTANT, not "today": the baseline
#: would otherwise go stale by the calendar and its digests could not fix the
#: answer.  Must equal the ``as_of`` the corpus pins in
#: ``tests/test_no_renumber_migration.py`` replay to.
AS_OF = "2026-07-10"

#: The recovery whose every corpus firing this sweep enumerates —
#: ``(RENUMBER, dest_occupied)`` in ``lawvm.norway.totalization_table``.
RULE_ID = "no_replay_renumber_occupied_destination_removed"

#: Import roots of the replay path.  The closure below is derived from these, so
#: the receipt tracks the code rather than a hand-maintained module list: a new
#: dependency can only enter by an edit to a module already inside the closure,
#: which moves the digest on its own.
CODE_ROOTS = ("lawvm.norway.replay", "lawvm.norway.index", "lawvm.norway.inventory")

#: The Norway artifact planes, digested whole.  All four are included even though
#: the firing sweep reads only three (``current`` belongs to the verify lane), so
#: that the receipt is "the Norway corpus" rather than a guess at the subset this
#: pass happened to touch.  The two ``unmapped`` iterators are deliberately out:
#: by construction nothing reads them, and an artifact can only move from
#: unmapped to mapped by a code change, which the code identity already carries.
CORPUS_PLANES = ("original_lti", "amendment", "forskrift", "current")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Corpus identity
# ---------------------------------------------------------------------------


def _plane_iterators(data_dir: Path) -> dict[str, Iterable[Any]]:
    from lawvm.norway.sources import (
        iter_no_amendment_artifacts,
        iter_no_current_artifacts,
        iter_no_forskrift_artifacts,
        iter_no_original_lti_artifacts,
    )

    return {
        "original_lti": iter_no_original_lti_artifacts(data_dir),
        "amendment": iter_no_amendment_artifacts(data_dir),
        "forskrift": iter_no_forskrift_artifacts(data_dir),
        "current": iter_no_current_artifacts(data_dir),
    }


def corpus_identity(data_dir: Path) -> dict[str, Any]:
    """Digest the Norway corpus by LOGICAL content, one entry per plane.

    Per plane rather than one opaque number so a stale baseline says WHICH plane
    moved: "the forskrift plane grew by 40" is a triageable message, "the corpus
    digest differs" is not.
    """
    iterators = _plane_iterators(data_dir)
    planes = []
    combined = hashlib.sha256()
    for name in CORPUS_PLANES:
        h = hashlib.sha256()
        count = 0
        for art in iterators[name]:
            h.update(art.logical_id.encode("utf-8"))
            h.update(b"\0")
            h.update(hashlib.sha256(art.payload).digest())
            count += 1
        digest = h.hexdigest()
        planes.append({"plane": name, "artifacts": count, "digest": digest})
        combined.update(name.encode("utf-8"))
        combined.update(b"\0")
        combined.update(digest.encode("utf-8"))
    return {"planes": planes, "digest": combined.hexdigest()}


# ---------------------------------------------------------------------------
# Code identity
# ---------------------------------------------------------------------------


def _module_file(src: Path, name: str) -> Path | None:
    rel = Path(*name.split("."))
    for candidate in (src / rel.with_suffix(".py"), src / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imported_names(tree: ast.AST, package: str) -> list[str]:
    """Every ``lawvm.*`` name an import statement anywhere in ``tree`` reaches.

    Walks the WHOLE tree, not just module level, so a function-local import
    (this codebase uses them heavily to keep import time down) is still inside
    the closure.  ``from X import y`` contributes both ``X`` and ``X.y``,
    because ``y`` may be a submodule; non-module names resolve to no file and
    drop out.
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names if a.name.split(".")[0] == "lawvm")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            if module.split(".")[0] != "lawvm":
                continue
            names.append(module)
            names.extend(f"{module}.{a.name}" for a in node.names)
    return names


def code_closure(root: Path | None = None) -> dict[str, Path]:
    """The static import closure of ``CODE_ROOTS``, module name -> source file.

    Ancestor packages are pulled in with every module because importing
    ``lawvm.a.b`` executes ``lawvm/__init__.py`` and ``lawvm/a/__init__.py``
    too, so their contents are part of the behaviour being receipted.
    """
    src = (root or repo_root()) / "src"
    found: dict[str, Path] = {}
    stack = list(CODE_ROOTS)
    while stack:
        name = stack.pop()
        if name in found:
            continue
        path = _module_file(src, name)
        if path is None:
            continue
        found[name] = path
        parts = name.split(".")
        stack.extend(".".join(parts[:i]) for i in range(1, len(parts)))
        package = name if path.name == "__init__.py" else ".".join(parts[:-1])
        stack.extend(_imported_names(ast.parse(path.read_text(encoding="utf-8")), package))
    return found


def code_identity(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    closure = code_closure(root)
    h = hashlib.sha256()
    files = []
    for name in sorted(closure):
        digest = hashlib.sha256(closure[name].read_bytes()).hexdigest()
        files.append({"module": name, "digest": digest})
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("utf-8"))
    return {"roots": list(CODE_ROOTS), "modules": len(files), "files": files, "digest": h.hexdigest()}


def staleness_reasons(
    baseline: dict[str, Any], live_corpus: dict[str, Any], live_code: dict[str, Any]
) -> list[str]:
    """Why the baseline no longer describes this tree — empty when it still does.

    Lives here rather than inline in the test so the test that USES it and the
    test that PROVES IT FIRES can call the same code: a staleness check nobody
    has ever seen fail is indistinguishable from one that cannot.
    """
    reasons: list[str] = []
    if live_corpus["digest"] != baseline["corpus"]["digest"]:
        was = {p["plane"]: (p["artifacts"], p["digest"]) for p in baseline["corpus"]["planes"]}
        now = {p["plane"]: (p["artifacts"], p["digest"]) for p in live_corpus["planes"]}
        moved = [
            f"{plane}: {was.get(plane, ('-', ''))[0]} -> {now[plane][0]} artifacts"
            for plane in now
            if was.get(plane) != now[plane]
        ]
        moved += [f"{plane}: plane no longer swept" for plane in was if plane not in now]
        reasons.append(
            "THE CORPUS MOVED, so the committed firing census describes a corpus that no "
            "longer exists. Planes that moved: " + "; ".join(moved)
        )
    if live_code["digest"] != baseline["code"]["digest"]:
        was = {f["module"]: f["digest"] for f in baseline["code"]["files"]}
        now = {f["module"]: f["digest"] for f in live_code["files"]}
        moved = sorted(set(was) ^ set(now)) + sorted(
            m for m in set(was) & set(now) if was[m] != now[m]
        )
        reasons.append(
            "THE REPLAY PATH MOVED, so the committed firing census describes behaviour "
            "the code no longer has. This is the W-67 shape exactly: the archive did not "
            f"move, the parser did. Modules that moved ({len(moved)} of "
            f"{live_code['modules']}): " + ", ".join(moved[:12]) + ("…" if len(moved) > 12 else "")
        )
    return reasons


def runtime_identity(root: Path | None = None) -> dict[str, Any]:
    """Third-party versions the closure imports — RECORDED, not asserted.

    A dependency bump can in principle move a firing, so the baseline should say
    what it was built against.  It is not asserted because fresh worktree venvs
    legitimately carry different extras, and a red that fires on an unrelated
    ``uv pip install`` teaches people to regenerate without reading, which is
    the only way this mechanism can be defeated.
    """
    import importlib.metadata as md

    closure = code_closure(root)
    third_party: set[str] = set()
    for path in closure.values():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                third_party.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                third_party.add(node.module.split(".")[0])
    mapping = md.packages_distributions()
    versions = {}
    for name in sorted(third_party):
        dists = mapping.get(name)
        if not dists:
            continue  # stdlib, or vendored — no distribution to pin
        for dist in dists:
            try:
                versions[dist] = md.version(dist)
            except md.PackageNotFoundError:
                versions[dist] = "unknown"
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "distributions": dict(sorted(versions.items())),
    }


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

_DATA: Path | None = None
_INDEX = None


def _index():
    global _INDEX
    if _INDEX is None:
        from lawvm.norway.index import build_no_amendment_index

        _INDEX = build_no_amendment_index(_DATA)
    return _INDEX


def sweep_one(base_id: str) -> dict[str, Any]:
    """Replay one base law and extract both censuses from the single pass."""
    from lawvm.norway.replay import replay_no_to_pit

    row: dict[str, Any] = {"base_id": base_id}
    try:
        res = replay_no_to_pit(base_id, AS_OF, data_dir=_DATA, index=_index())
    except Exception as exc:  # a crashed law is a sweep that did not see it
        row["fatal"] = f"{type(exc).__name__}: {exc}"
        return row
    # An errored replay is only a COMPLETE answer for this sweep when it errored
    # before any op was applied: 440 laws have no original-act source at all
    # (F-09's sparse-source class), return early, and can carry no firing by
    # construction. The other four abort mid-apply on an invariant violation,
    # which discards the apply plane's receipts and adjudications with it — the
    # sweep genuinely does not see whether those laws fire, so they are named
    # rather than counted, and the test pins the set.
    row["error"] = res.error or ""
    row["n_ops"] = res.n_ops
    row["firings"] = [
        {
            "op_id": a.op_id,
            "base_id": base_id,
            "source_path": str((a.detail or {}).get("source_path")),
            "destination_path": str((a.detail or {}).get("destination_path")),
        }
        for a in res.adjudications
        if a.kind == RULE_ID
    ]
    row["collateral"] = sum(
        1 for r in res.write_receipts if r.action == "renumber" and r.removed_paths
    )
    # W-73's rider, from the same pass.
    skipped = {
        "contingent": len(res.amendments_skipped_contingent),
        "unknown_effective": len(res.amendments_skipped_unknown_effective),
        "missing_source": len(res.amendments_skipped_missing_source),
    }
    row["skipped"] = skipped
    row["incomplete_base"] = any(skipped.values())
    destructive = 0
    removing = 0
    for r in res.write_receipts:
        if r.removed_paths or r.replaced_paths or r.renumbered_paths:
            destructive += 1
        if r.removed_paths:
            removing += 1
    row["destructive_writes"] = destructive
    row["content_removing_writes"] = removing
    return row


def _init(data_dir: Path) -> None:
    global _DATA
    _DATA = data_dir


def run_sweep(data_dir: Path, procs: int) -> dict[str, Any]:
    from lawvm.norway.index import build_no_amendment_index
    from lawvm.norway.inventory import build_no_inventory

    _init(data_dir)
    inventory = build_no_inventory(data_dir, index=build_no_amendment_index(data_dir))
    bases = sorted(inventory.base_to_sources)
    print(f"sweeping {len(bases)} base laws at as_of={AS_OF} on {procs} processes", file=sys.stderr)
    rows: list[dict[str, Any]] = []
    with get_context("fork").Pool(procs) as pool:
        for i, row in enumerate(pool.imap_unordered(sweep_one, bases, chunksize=4), 1):
            rows.append(row)
            if i % 100 == 0:
                print(f"  {i}/{len(bases)}", file=sys.stderr, flush=True)
    rows.sort(key=lambda r: r["base_id"])
    return {"base_ids": bases, "rows": rows}


def build_baseline(data_dir: Path, procs: int, root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    swept = run_sweep(data_dir, procs)
    rows = swept["rows"]
    fatals = [r["base_id"] for r in rows if r.get("fatal")]
    firings = [f for r in rows for f in r.get("firings", ())]
    firing_laws = {
        r["base_id"]: [len(r["firings"]), r["collateral"]]
        for r in rows
        if r.get("firings") or r.get("collateral")
    }
    hazard = [
        r for r in rows if r.get("incomplete_base") and r.get("destructive_writes", 0) > 0
    ]
    hazard_laws = {
        r["base_id"]: [r["destructive_writes"], r["content_removing_writes"]] for r in hazard
    }
    hazard_digest = hashlib.sha256(
        json.dumps(hazard_laws, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "_doc": (
            "Corpus-wide (RENUMBER, dest_occupied) firing sweep + the "
            "known-incomplete-base destructive-write census, over EVERY Norway base "
            "law. Cached because the sweep is ~10 CPU-minutes and the norway shard is "
            "not. `corpus` and `code` are the staleness receipt: "
            "tests/test_no_renumber_migration.py recomputes both and FAILS when either "
            "moved, rather than passing on a stale measurement. Regenerate with "
            "`uv run python scripts/inventory_no_occupied_destination_sweep.py "
            "--update-baseline`. NOTE: this file is a RECEIPT of what the corpus does, "
            "never a statement of what it should do -- a new firing row here is an "
            "unadjudicated firing, and it must be adjudicated W-54 style before the "
            "verdict table in the test is extended."
        ),
        "as_of": AS_OF,
        "rule_id": RULE_ID,
        "corpus": corpus_identity(data_dir),
        "code": code_identity(root),
        "runtime": runtime_identity(root),
        "swept": {
            "base_laws": len(swept["base_ids"]),
            "base_law_ids": swept["base_ids"],
            "fatals": fatals,
            "errored_before_any_op": sum(
                1 for r in rows if r.get("error") and not r.get("n_ops")
            ),
            "errored_with_ops_applied": sorted(
                r["base_id"] for r in rows if r.get("error") and r.get("n_ops")
            ),
            "errored_with_ops_applied_detail": [
                {"base_id": r["base_id"], "n_ops": r["n_ops"], "error": r["error"]}
                for r in rows
                if r.get("error") and r.get("n_ops")
            ],
        },
        "firings": sorted(firings, key=lambda f: (f["base_id"], f["op_id"] or "")),
        "firing_laws": dict(sorted(firing_laws.items())),
        "incomplete_base_hazard": {
            "_doc": (
                "W-73's rider, re-measured every sweep. A base is known-incomplete when "
                "its replay receipted a SKIPPED amendment; a write is destructive when "
                "it removes, replaces or renumbers existing content. The intersection is "
                "the posture that destroyed husbankloven § 13. Pinned so the number "
                "cannot drift silently -- NOT because the hazard is acceptable."
            ),
            "incomplete_bases": sum(1 for r in rows if r.get("incomplete_base")),
            "bases_with_destructive_writes": sum(
                1 for r in rows if r.get("destructive_writes", 0) > 0
            ),
            "hazard_bases": len(hazard),
            "hazard_destructive_writes": sum(r["destructive_writes"] for r in hazard),
            "hazard_content_removing_writes": sum(
                r["content_removing_writes"] for r in hazard
            ),
            "hazard_bases_removing_content": sum(
                1 for r in hazard if r["content_removing_writes"] > 0
            ),
            "hazard_by_skip_kind": {
                kind: sum(1 for r in hazard if r["skipped"][kind])
                for kind in ("contingent", "unknown_effective", "missing_source")
            },
            "laws_digest": hazard_digest,
            "laws": hazard_laws,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_baseline(root: Path | None = None) -> dict[str, Any]:
    return json.loads(((root or repo_root()) / BASELINE_PATH).read_text(encoding="utf-8"))


def _report_diff(old: dict[str, Any] | None, new: dict[str, Any]) -> int:
    """Print what moved, and return the count of firings needing adjudication."""
    new_firings = {f["op_id"]: f for f in new["firings"]}
    old_firings = {f["op_id"]: f for f in (old or {}).get("firings", ())}
    added = sorted(set(new_firings) - set(old_firings))
    removed = sorted(set(old_firings) - set(new_firings))
    print(f"firings: {len(old_firings)} -> {len(new_firings)}")
    for op_id in removed:
        print(f"  WITHDRAWN  {op_id}  {old_firings[op_id]['base_id']}")
    for op_id in added:
        f = new_firings[op_id]
        print(f"  NEW        {op_id}  {f['base_id']}  {f['source_path']} -> {f['destination_path']}")
    haz_new = new["incomplete_base_hazard"]
    haz_old = (old or {}).get("incomplete_base_hazard", {})
    print(
        f"known-incomplete-base hazard: {haz_old.get('hazard_bases', '-')} -> "
        f"{haz_new['hazard_bases']} laws, "
        f"{haz_old.get('hazard_destructive_writes', '-')} -> "
        f"{haz_new['hazard_destructive_writes']} destructive writes, "
        f"{haz_old.get('hazard_content_removing_writes', '-')} -> "
        f"{haz_new['hazard_content_removing_writes']} content-removing over "
        f"{haz_new['hazard_bases_removing_content']} laws"
    )
    print(
        f"swept {new['swept']['base_laws']} base laws; "
        f"{new['swept']['errored_before_any_op']} errored before any op (no original-act "
        f"source: they can carry no firing)"
    )
    if new["swept"]["fatals"]:
        print(f"  FATAL laws (sweep did not see them): {new['swept']['fatals']}")
    old_blind = sorted((old or {}).get("swept", {}).get("errored_with_ops_applied", []))
    new_blind = sorted(new["swept"]["errored_with_ops_applied"])
    if new_blind:
        print(
            f"  BLIND SPOT ({len(new_blind)} laws): replay aborts mid-apply, so the sweep "
            f"did not observe their firings: {', '.join(new_blind)}"
        )
    if old is not None and new_blind != old_blind:
        print(
            f"  BLIND SPOT MOVED: {old_blind} -> {new_blind}. A law LEAVING it may reveal "
            "firings nobody has adjudicated; a law entering it hides firings that were "
            "previously visible. Either way, say which in the ledger."
        )
    return len(added)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true", help=f"rewrite {BASELINE_PATH}")
    parser.add_argument("--data-dir", default=None, help="Norway farchive path")
    parser.add_argument(
        "--procs",
        type=int,
        default=int(os.environ.get("LAWVM_NO_SWEEP_PROCS", "10")),
        help="worker processes for the replay sweep",
    )
    args = parser.parse_args(argv)

    from lawvm.norway.sources import resolve_no_source_path

    data_dir = resolve_no_source_path(Path(args.data_dir) if args.data_dir else None)
    root = repo_root()
    baseline = build_baseline(data_dir, args.procs, root)

    path = root / BASELINE_PATH
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    new_firings = _report_diff(old, baseline)

    if args.update_baseline:
        path.write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    else:
        print(f"(dry run; pass --update-baseline to rewrite {BASELINE_PATH})")

    if baseline["swept"]["fatals"]:
        print(
            "REFUSING to call this sweep complete: some laws crashed outright, so their "
            "firings were not observed.",
            file=sys.stderr,
        )
        return 2
    if old is not None and sorted(baseline["swept"]["errored_with_ops_applied"]) != sorted(
        old.get("swept", {}).get("errored_with_ops_applied", [])
    ):
        print("\nThe sweep's blind spot moved; see above.", file=sys.stderr)
        return 1
    if new_firings:
        print(
            f"\n{new_firings} NEW (RENUMBER, dest_occupied) firing(s). Adjudicate each one "
            "W-54 style -- source text, occupant provenance, does the removal destroy "
            "in-force law -- before adding it to _NO_OCCUPIED_DESTINATION_VERDICTS. A "
            "`removal_wrong` verdict must NEVER be entered there as expected behaviour.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
