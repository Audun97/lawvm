#!/usr/bin/env python3
"""Deterministic preflight for one Norway batch contract.

Ported from read-aloud-2's tools/batch-preflight.mjs: everything an agent could
be interrogated about is computed here directly, in about a second, and cannot
misquote itself. The workflow (.claude/workflows/norway-batch.js) receives this
output verbatim as its facts and never re-derives a repository fact.

    uv run python scripts/norway_batch_preflight.py <contract-path> [--audit] [--json]

Exit 0 when the batch may run. --audit ignores readiness (state/baseline) so any
contract, including a planned one, can be checked for staleness. --json emits
the facts a caller hands to the workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Mirrors of the workflow's frozen hard rules. These must stay in step with
# .claude/workflows/norway-batch.js; the ledger's executionPolicy is checked against them.
PROGRESS_PATH = "notes/norway-batches/progress.json"
CONTRACT_PREFIX = "notes/norway-batches/contracts/"
WORKFLOW_PATH = ".claude/workflows/norway-batch.js"
# Committed drift that never invalidates a frozen product baseline: the batch control plane
# (.claude/, the contracts and ledger) and notes/, which the repo's own CI treats as docs-only.
CONTROL_PLANE_DRIFT = (
    {"path": ".claude/", "match": "prefix"},
    {"path": "notes/", "match": "prefix"},
)
REQUIRED_RELATIONS = ["dependsOn", "recommendedAfter"]
FIELD_POLICIES = ["not-required", "required-after-application"]
# The apply-time ladder is the repository's own canonical gate over the contract scope. A full
# ladder that ends anywhere else would either skip the gate or run something weaker than it.
APPLY_LADDER_PREFIX = "./scripts/ci.sh --affected "
NORWAY_CORPUS = "data/norway.farchive"
# Below this size the archive is a stub, mirroring lawvm.corpus_store's populated floor intent.
CORPUS_FLOOR_BYTES = 1_000_000

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CONTRACT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

errors: list[str] = []      # contract or repository facts that are wrong
readiness: list[str] = []   # true but not yet authorised to run; ignored under --audit
warnings: list[str] = []    # style tells that have cost real runs before now


def is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def as_string_list(value: Any) -> list[str]:
    return value if is_string_list(value) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_safe_repo_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and not value.startswith("./")
        and ".." not in value.split("/")
        and not CONTROL_RE.search(value)
        and not re.search(r"\s", value)
    )


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def git_ok(*args: str) -> bool:
    return (
        subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True).returncode == 0
    )


def git_status_paths() -> list[str]:
    # Porcelain encodes status in the first two columns, so the leading space of " M path" is
    # significant: stripping whole lines would shift every modified path by one character.
    raw = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [line[3:] for line in raw.split("\n") if line]


def sha256_file(relative: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()


def matches_rule(candidate: str, rule: dict[str, str]) -> bool:
    if rule["match"] == "exact":
        return candidate == rule["path"]
    return candidate.startswith(rule["path"])


# A scope entry is a literal path, a directory prefix ending in "/", or a glob where * matches
# within one path segment and ** matches across segments. Compiled to regex sources here and
# handed to the workflow in facts, so the matcher exists once rather than in two dialects.
def is_pattern(value: str) -> bool:
    return "*" in value or value.endswith("/")


def pattern_to_regex_source(pattern: str) -> str:
    if pattern.endswith("/"):
        return "^" + re.escape(pattern) + ".+$"
    out = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch != "*":
            out += re.escape(ch)
            i += 1
            continue
        if pattern[i + 1 : i + 3] == "*/":
            out += "(?:[^/]+/)*"
            i += 3
        elif pattern[i + 1 : i + 2] == "*":
            out += ".*"
            i += 2
        else:
            out += "[^/]*"
            i += 1
    return f"^{out}$"


def compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern_to_regex_source(p)) for p in patterns]


def matches_any(candidate: str, matchers: list[re.Pattern[str]]) -> bool:
    return any(m.match(candidate) for m in matchers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract_path")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--json", dest="as_json", action="store_true")
    parsed = parser.parse_args()

    rel_contract = (
        Path(parsed.contract_path).resolve().relative_to(REPO_ROOT).as_posix()
        if Path(parsed.contract_path).is_absolute()
        else Path(parsed.contract_path).as_posix()
    )
    if (
        not is_safe_repo_path(rel_contract)
        or not rel_contract.startswith(CONTRACT_PREFIX)
        or not rel_contract.endswith(".json")
    ):
        print(f"- contract path must be a .json file under {CONTRACT_PREFIX}: {rel_contract}", file=sys.stderr)
        return 2

    # ---------------------------------------------------------------- load inputs
    contract: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    try:
        contract = json.loads((REPO_ROOT / rel_contract).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"contract is unreadable or invalid JSON: {exc}")
    try:
        progress = json.loads((REPO_ROOT / PROGRESS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"progress ledger is unreadable or invalid JSON: {exc}")
    if not is_dict(contract) or not is_dict(progress):
        print("\n".join(f"- {item}" for item in errors), file=sys.stderr)
        return 1
    assert contract is not None and progress is not None

    entry_raw = as_dict(progress.get("batches")).get(contract.get("id"))
    entry: dict[str, Any] = as_dict(entry_raw)
    scope = as_dict(contract.get("scope"))
    allowed_paths = as_string_list(scope.get("allowedPaths"))
    required_changed = as_string_list(scope.get("requiredChangedPaths"))
    required_added = as_string_list(scope.get("requiredAddedPaths"))
    required_deleted = as_string_list(scope.get("requiredDeletedPaths"))
    # The boundary is the hard limit a patch may never cross. allowedPaths is the manifest: what
    # the contract expects to change. When no boundary is declared the manifest is also the limit.
    boundary_paths = as_string_list(scope.get("boundary")) or allowed_paths
    boundary_matchers = compile_patterns(boundary_paths)
    verification = as_dict(contract.get("verification"))
    targeted = as_list(verification.get("targeted"))
    full = as_list(verification.get("full"))
    specs = [*targeted, *full]

    # ------------------------------------------------------------ contract shape
    if contract.get("schemaVersion") != 1 or progress.get("schemaVersion") != 1:
        errors.append("unsupported contract or progress schema version")
    if not isinstance(contract.get("id"), str) or not CONTRACT_ID_RE.match(contract.get("id") or ""):
        errors.append("contract id is missing or unsafe")
    if not isinstance(contract.get("title"), str) or not contract.get("title"):
        errors.append("contract title is missing")
    if contract.get("classification") not in ("confirmed", "security"):
        errors.append(
            f"unsupported classification: {contract.get('classification')} — experiments are not "
            "batches; run them interactively and, if promoted, write a confirmed contract from the "
            "resulting diff"
        )
    if contract.get("branch") != progress.get("branch"):
        errors.append(f"contract branch {contract.get('branch')} differs from ledger branch {progress.get('branch')}")
    for key in ("dependsOn", "recommendedAfter", "preflightChecks", "requirements", "invariants", "exclusions", "stopConditions"):
        if not is_string_list(contract.get(key)):
            errors.append(f"contract.{key} must be an array of strings")
    if not is_dict(contract.get("scope")) or not all(
        is_string_list(scope.get(k))
        for k in ("allowedPaths", "requiredChangedPaths", "requiredAddedPaths", "requiredDeletedPaths")
    ):
        errors.append("contract.scope is malformed")
    if scope.get("boundary") is not None and not is_string_list(scope.get("boundary")):
        errors.append("contract.scope.boundary must be an array of strings when present")
    field_verification = as_dict(contract.get("fieldVerification"))
    if (
        not field_verification
        or field_verification.get("policy") not in FIELD_POLICIES
        or not is_string_list(field_verification.get("instructions"))
    ):
        errors.append("contract.fieldVerification is malformed or uses an unsupported policy")

    # ------------------------------------------------------------------- scope
    every_scope_path = [*boundary_paths, *allowed_paths, *required_changed, *required_added, *required_deleted]
    for candidate in every_scope_path:
        if not is_safe_repo_path(candidate):
            errors.append(f"unsafe scope path: {candidate}")
    if len(unique(allowed_paths)) != len(allowed_paths):
        errors.append("allowedPaths contains duplicates")
    required_all = [*required_changed, *required_added, *required_deleted]
    if len(unique(required_all)) != len(required_all):
        errors.append("required path sets overlap or contain duplicates")
    # Required paths name specific files, so they must be literal: a pattern there would leave the
    # contract unable to say which file must change.
    for field, listed in (
        ("requiredChangedPaths", required_changed),
        ("requiredAddedPaths", required_added),
        ("requiredDeletedPaths", required_deleted),
    ):
        for candidate in listed:
            if is_pattern(candidate):
                errors.append(f"{field} must list literal paths, not patterns: {candidate}")
            elif not matches_any(candidate, boundary_matchers):
                errors.append(f"{field} lists a path outside the scope boundary: {candidate}")
    for candidate in allowed_paths:
        if not matches_any(candidate, boundary_matchers) and not is_pattern(candidate):
            errors.append(f"allowedPaths lists a path outside the scope boundary: {candidate}")

    # ------------------------------------------------------- verification ladder
    for spec in specs:
        if (
            not is_dict(spec)
            or not isinstance(spec.get("id"), str)
            or not isinstance(spec.get("command"), str)
            or not isinstance(spec.get("group"), str)
            or spec.get("required") is not True
        ):
            errors.append("every verification stage must declare id, command, group and required: true")
    if not targeted or not full:
        errors.append("verification needs both a targeted and a full ladder")
    if len(unique([spec.get("id") for spec in specs if is_dict(spec)])) != len(specs):
        errors.append("verification stage ids must be unique")
    # The full ladder must end at the repository's canonical gate over the contract scope. The
    # affected paths must cover every literal scope path so the gate cannot silently under-select.
    last_full = full[-1] if full and is_dict(full[-1]) else None
    if last_full is None or not str(last_full.get("command", "")).startswith(APPLY_LADDER_PREFIX):
        errors.append(f"full verification must end with one '{APPLY_LADDER_PREFIX}<scope paths>' stage")
    else:
        ladder_paths = str(last_full["command"])[len(APPLY_LADDER_PREFIX):].split()
        literal_scope = [p for p in unique([*allowed_paths, *required_all]) if not is_pattern(p)]
        missing = [p for p in literal_scope if p not in ladder_paths]
        if missing:
            errors.append(f"apply ladder --affected omits scoped paths: {', '.join(missing)}")
    for spec in specs:
        command = str(spec.get("command", "")) if is_dict(spec) else ""
        if command.startswith("python") or " python " in f" {command} ":
            if "uv run" not in command:
                errors.append(f"verification stage bypasses uv run: {command}")

    # ------------------------------------------------------------ ledger policy
    policy = as_dict(progress.get("executionPolicy"))
    if policy.get("runnableState") != "ready" or policy.get("readyAtHeadMeaning") != "frozen-product-baseline":
        errors.append("ledger executionPolicy is unsupported")
    if policy.get("allowedControlPlaneDrift") != list(CONTROL_PLANE_DRIFT):
        errors.append("ledger control-plane drift policy differs from the workflow hard rules")
    if policy.get("requiredCompletedRelations") != REQUIRED_RELATIONS:
        errors.append("ledger required relations differ from the workflow hard rules")
    if policy.get("fieldVerificationPolicies") != FIELD_POLICIES:
        errors.append("ledger field-verification policies differ from the workflow hard rules")
    source_review = as_dict(progress.get("sourceReview"))
    if source_review:
        review_path = source_review.get("path")
        if not isinstance(review_path, str) or not (REPO_ROOT / review_path).exists():
            errors.append("source review path is missing")
        elif source_review.get("sha256") != sha256_file(review_path):
            errors.append("source review sha256 does not match the file on disk")

    # ------------------------------------------------------------ ledger entry
    contract_sha = sha256_file(rel_contract)
    if not is_dict(entry_raw):
        errors.append(f"ledger has no entry for {contract.get('id')}")
    else:
        if as_dict(entry.get("contract")).get("path") != rel_contract:
            errors.append("ledger contract path does not match the requested contract")
        if as_dict(entry.get("contract")).get("sha256") != contract_sha:
            errors.append(f"ledger contract sha256 is stale; on disk it is {contract_sha}")
        if as_dict(entry.get("fieldVerification")).get("status") != as_dict(field_verification).get("policy"):
            errors.append("ledger and contract field-verification policies differ")
        if entry.get("state") != "ready":
            readiness.append(f"batch state is {entry.get('state')}, not ready")
        if not COMMIT_RE.match(entry.get("readyAtHead") or ""):
            readiness.append("ledger readyAtHead is not a full commit hash")
        elif contract.get("productBaseline") != entry.get("readyAtHead"):
            readiness.append("contract productBaseline and ledger readyAtHead differ")

    # ------------------------------------------------------------ prerequisites
    prerequisite_ids = unique([*as_string_list(contract.get("dependsOn")), *as_string_list(contract.get("recommendedAfter"))])
    for prereq_id in prerequisite_ids:
        prerequisite_raw = as_dict(progress.get("batches")).get(prereq_id)
        if not is_dict(prerequisite_raw):
            errors.append(f"prerequisite references an unknown batch: {prereq_id}")
            continue
        prerequisite = as_dict(prerequisite_raw)
        # Not its turn yet is a readiness condition, not a defect in this contract.
        if prerequisite.get("state") != "complete":
            readiness.append(f"prerequisite {prereq_id} is {prerequisite.get('state')}, not complete")
            continue
        patch_sha = as_dict(prerequisite.get("patch")).get("sha256") or ""
        applied_commit = as_dict(prerequisite.get("application")).get("commit") or ""
        if not SHA256_RE.match(patch_sha) or not COMMIT_RE.match(applied_commit):
            errors.append(f"prerequisite {prereq_id} lacks patch identity or application commit")
        prerequisite_file = as_dict(prerequisite.get("contract")).get("path")
        if not isinstance(prerequisite_file, str) or not (REPO_ROOT / prerequisite_file).exists():
            errors.append(f"prerequisite {prereq_id} contract file is missing")
            continue
        parsed_prereq = as_dict(json.loads((REPO_ROOT / prerequisite_file).read_text(encoding="utf-8")))
        if as_dict(prerequisite.get("contract")).get("sha256") != sha256_file(prerequisite_file):
            errors.append(f"prerequisite {prereq_id} contract sha256 is stale")
        prereq_verification = as_dict(parsed_prereq.get("verification"))
        expected = [
            as_dict(spec).get("command")
            for spec in [
                *as_list(prereq_verification.get("targeted")),
                *as_list(prereq_verification.get("full")),
            ]
        ]
        recorded = as_dict(as_dict(prerequisite.get("evidence")).get("verification")).get("successfulStages")
        if recorded != expected:
            errors.append(f"prerequisite {prereq_id} recorded stages differ from its frozen ladder")
        expected_policy = as_dict(parsed_prereq.get("fieldVerification")).get("policy") or ""
        if as_dict(prerequisite.get("fieldVerification")).get("status") != expected_policy:
            errors.append(f"prerequisite {prereq_id} field-verification policy differs from its contract")
        if as_dict(prerequisite.get("patch")).get("sourceBaseline") != parsed_prereq.get("productBaseline") or prerequisite.get("readyAtHead") != parsed_prereq.get("productBaseline"):
            errors.append(f"prerequisite {prereq_id} completion baseline differs from its frozen contract")
        if applied_commit and not git_ok("merge-base", "--is-ancestor", applied_commit, "HEAD"):
            errors.append(f"prerequisite {prereq_id} application commit is not an ancestor of HEAD")

    # ------------------------------------------------------- repository state
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    head = git("rev-parse", "HEAD")
    dirty_paths = git_status_paths()
    tracked_paths = set(git("ls-files").split("\n"))

    if contract.get("branch") and branch != contract.get("branch"):
        errors.append(f"on branch {branch}, contract expects {contract.get('branch')}")
    if dirty_paths:
        preview = ", ".join(dirty_paths[:5])
        suffix = f" (+{len(dirty_paths) - 5} more)" if len(dirty_paths) > 5 else ""
        errors.append(f"working tree is not clean: {preview}{suffix}")

    # The Norway corpus is gitignored, so its presence is a machine fact, not a contract claim.
    # A batch whose scope reaches src/lawvm/norway/ or whose field verification cites replay
    # output cannot be judged against a stub archive.
    corpus_file = REPO_ROOT / NORWAY_CORPUS
    corpus_populated = corpus_file.exists() and corpus_file.stat().st_size >= CORPUS_FLOOR_BYTES
    if not corpus_populated:
        errors.append(f"{NORWAY_CORPUS} is missing or a stub; Norway batches cannot be verified against it")

    baseline = entry.get("readyAtHead")
    drift_paths: list[str] = []
    if COMMIT_RE.match(baseline or ""):
        assert baseline is not None
        if not git_ok("merge-base", "--is-ancestor", baseline, "HEAD"):
            readiness.append(f"product baseline {baseline[:7]} is not an ancestor of HEAD")
        else:
            drift_paths = [p for p in git("diff", "--name-only", f"{baseline}..HEAD").split("\n") if p]
            product_drift = [p for p in drift_paths if not any(matches_rule(p, rule) for rule in CONTROL_PLANE_DRIFT)]
            if product_drift:
                readiness.append(f"product code changed since the baseline: {', '.join(product_drift)}")

    # A completed batch's contract describes the tree as it was before that batch landed, so its
    # added paths now exist and its deleted paths now do not. Checking scope against today's tree
    # would report the batch's own success as a defect.
    if entry.get("state") == "complete":
        warnings.append(
            "batch is already complete; scope checks against the current tree are skipped because "
            "the contract describes the pre-application tree"
        )
    else:
        for candidate in allowed_paths:
            if is_pattern(candidate):
                continue
            if candidate not in tracked_paths and candidate not in required_added:
                errors.append(f"allowed path is untracked: {candidate}")
        for candidate in [*required_changed, *required_deleted]:
            if not (REPO_ROOT / candidate).exists():
                errors.append(f"required existing path is missing: {candidate}")
        for candidate in required_added:
            if (REPO_ROOT / candidate).exists():
                errors.append(f"required added path already exists: {candidate}")

    # The repo's shard mapper is the oracle for which suites a scope can break. Advisory: the
    # apply ladder already routes through ci.sh --affected; this surfaces the routing so a
    # contract whose targeted stages miss an affected shard is visible before the run.
    affected_shards: list[str] | None = None
    literal_scope = [p for p in unique([*allowed_paths, *required_all]) if not is_pattern(p)]
    if literal_scope:
        proc = subprocess.run(
            ["./scripts/test_shard.sh", "affected", *literal_scope],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            affected_shards = [line for line in proc.stdout.strip().split("\n") if line]
        else:
            warnings.append(
                "shard mapping could not route the scope paths; ci.sh --affected will fail at "
                "apply time until a mapping exists"
            )

    # ------------------------------------------------------------- style tells
    # Each of these has cost a real run in the source repo. They never block; they are advice.
    for candidate in required_added:
        warnings.append(
            f"contract pins a file that does not exist yet ({candidate}) — that is a design "
            "decision made before any code was written; consider leaving the shape open"
        )
    for index, check in enumerate(as_string_list(contract.get("preflightChecks"))):
        if len(check) > 120:
            warnings.append(f"preflightChecks[{index}] is {len(check)} chars — long checks fail on wording, not substance")
        if re.search(r";| and | but ", check) and len(re.split(r";| and | but ", check)) > 2:
            warnings.append(f"preflightChecks[{index}] asserts several clauses — assert the minimum fact the batch depends on")
        if re.search(r"['’]", check):
            warnings.append(f"preflightChecks[{index}] contains an apostrophe — quote substitution has broken round-trips before")

    # ------------------------------------------------------------------ report
    runnable = not errors and (parsed.audit or not readiness)
    facts = {
        "contractPath": rel_contract,
        "contractSha256": contract_sha,
        "batchId": contract.get("id"),
        "progressSha256": sha256_file(PROGRESS_PATH),
        "sourceReviewSha256": sha256_file(source_review["path"]) if isinstance(source_review.get("path"), str) and (REPO_ROOT / source_review["path"]).exists() else "",
        "workflowSha256": sha256_file(WORKFLOW_PATH) if (REPO_ROOT / WORKFLOW_PATH).exists() else "",
        "repositoryRoot": str(REPO_ROOT),
        "branch": branch,
        "head": head,
        "productBaseline": baseline or None,
        "dirtyPaths": dirty_paths,
        "committedDriftPaths": drift_paths,
        "norwayCorpusPopulated": corpus_populated,
        "affectedShards": affected_shards,
        "scopePatterns": {
            "boundary": [pattern_to_regex_source(p) for p in boundary_paths],
            "allowed": [pattern_to_regex_source(p) for p in allowed_paths],
            "declaredBoundary": is_string_list(scope.get("boundary")),
        },
        "prerequisiteCommits": [
            {
                "id": prereq_id,
                "commit": as_dict(as_dict(as_dict(progress.get("batches")).get(prereq_id)).get("application")).get("commit"),
            }
            for prereq_id in prerequisite_ids
        ],
        "runnable": runnable,
        "errors": errors,
        "readiness": readiness,
        "warnings": warnings,
        "contract": contract,
    }

    if parsed.as_json:
        print(json.dumps(facts, indent=2, ensure_ascii=False))
        return 0 if runnable else 1

    label = f"{contract.get('id')} ({contract.get('classification')}, state {entry.get('state') or 'absent'})"
    if errors:
        print("errors:\n" + "\n".join(f"- {item}" for item in errors), file=sys.stderr)
    if readiness:
        heading = "not runnable yet" if parsed.audit else "readiness"
        print(f"{heading}:\n" + "\n".join(f"- {item}" for item in readiness), file=sys.stderr)
    if warnings:
        print("warnings:\n" + "\n".join(f"- {item}" for item in warnings), file=sys.stderr)
    if runnable:
        print(
            f"Batch preflight OK — {label}, {len(allowed_paths)} scoped paths, {len(specs)} "
            f"verification stages, {len(contract.get('preflightChecks') or [])} contract checks "
            "left for an agent to judge"
        )
    else:
        print(f"Batch preflight FAILED — {label}", file=sys.stderr)
    return 0 if runnable else 1


if __name__ == "__main__":
    sys.exit(main())
