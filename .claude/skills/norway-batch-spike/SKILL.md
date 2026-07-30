---
name: norway-batch-spike
description: Use before writing any Norway batch contract, plan, or estimate — and before removing a feature, rule, or subsystem anywhere in this repo. Establishes what a change actually touches by performing it in a throwaway worktree and keeping only the map. Triggers on "spike batch NN", "scope this change", "what would it take to remove X", "write a contract for X" when no spike exists yet, or any request to estimate a removal or engine change.
---

# Batch spike

Do the change for real in a worktree you throw away, and keep the map.

Reading the code to predict a change's reach does not work. In the source repo
(read-aloud-2, 2026-07-27) every scope prediction made by reading was wrong and
every one made by doing was right — including confident ones backed by grep.
This repo has already reproduced the lesson: the receipt-spine branch changed a
shared seam that "only Norway used" and broke Sweden's byte-identity gate,
Finland's guard-liveness partition, and the NO rule-id catalog — three
couplings reading did not show.

## Method

**1. Worktree outside the repo**, so the checkout stays clean and nothing can
be committed by accident:

```bash
SPIKE=/tmp/spike-<topic>
git worktree add -q --detach "$SPIKE" HEAD
cd "$SPIKE"
export LAWVM_CANONICAL_DATA_ROOT=<main-checkout-path>
```

The corpus archives are gitignored and will not exist in the worktree; the
resolver reads `LAWVM_CANONICAL_DATA_ROOT` directly, so the export is the whole
data story (no symlinks needed). Everything Python runs through `uv run` —
the first invocation syncs a fresh environment for the worktree; that one-time
cost is real, not a hang. Bare `python` silently uses the wrong interpreter.

**2. Make the obvious change first, then let the gates enumerate the damage.**
Do not trace call sites by hand. Run, fix what is named, repeat:

```bash
uv run ruff check src/ tests/ scripts/ --no-fix
uv run ty check src/ tests/ scripts/
./scripts/test_shard.sh affected <changed paths>   # which suites can break
./scripts/test_shard.sh run <each affected shard>
```

Each round is a fact; a hand-traced dependency graph is a guess.

**3. Run the affected shards for real, not a subset of a shard.** A change
that type-checks can still move behavior, and the tests are the only thing
that knows. Check `notes/IMPLEMENTATION_DIVERGENCE_LEDGER.md` before
attributing a red shard to the spike — some are red on a clean tree.

**4. Count the field truth.** This repo's unique failure mode: a change can
pass every test and still move the replay-vs-consolidation evidence the wrong
way. For anything touching the Norway engine, compare lane, or index, run the
scan before AND after, at a pinned date:

```bash
uv run lawvm no-verify-scan --limit 50 --as-of <snapshot date> --json
uv run lawvm no-divergence <affected law> --as-of <snapshot date>
```

The deltas (which laws flip consistent/divergent, which divergences appear or
vanish) become the contract's `fieldVerification.instructions`. An unpinned
date reproduces finding F-01: three laws misread as defective purely from a
horizon mismatch.

**5. Hunt orphans the gates cannot see** — the step that is always under-done.
Rule-id catalog entries, guard-liveness fire-drill and allowlist rows,
`_KNOWN_*` registries, shard mappings in `scripts/test_shard.py`, spec
sections in `notes/` that name the deleted helper, docstrings in sibling
jurisdictions that mirror it.

**6. Write the map, then `git worktree remove --force` and discard the code.**

## Deliverable

Never the patch. Always:

- **Blast radius** — every file, classified: changed / deleted / references
  removed / orphaned / test updated. This becomes `scope.boundary` and
  `allowedPaths`.
- **Surprises** — couplings that reading would not have shown. Each becomes a
  contract `preflightCheck` (the minimum fact the batch depends on).
- **Orphans** — with, for each, the evidence that nothing else uses it.
- **Field delta** — the before/after scan counts, which become
  `fieldVerification.instructions` with the pinned `--as-of`.
- **Scope** — derived from what happened, not from what was expected.
- **Sequencing** — one batch or several, and why.
- **Traps hit** — each one is worth a preflight check; a fact that is obvious
  once known is exactly what a searching implementer gets wrong.

## Pitfalls that produced wrong answers

- **Grep patterns are false-negative machines.** A pattern matching usage
  misses the declaration and the string-literal form. Search the bare word,
  then filter. (Source repo: this put a whole subsystem outside a contract.)
- **A piped exit code is the pipe's.** `uv run pytest ... | tail && echo ok`
  reads `tail`'s status, so a failing check reports success. Capture the
  program's own `$?`.
- **Dynamic dispatch hides real users.** In this repo that means string
  rule-ids: emit sites are discovered by AST scan and checked against catalogs
  (`spec_ledger_no_catalog`, guard-liveness partitions, finding registries).
  Deleting or renaming an id whose name appears "nowhere" trips a catalog gate
  three shards away — the receipt-spine branch did exactly this. Find where a
  thing is *emitted or cataloged*, not just where its name appears.
- **"Only Norway uses this" is a guess when the code lives in `core/`.** The
  shared apply seam, receipts, and parity audits are byte-identity-gated by
  other jurisdictions' tests. Run `test_shard.sh affected`, believe its answer.
- **Check whether a branch is an else-branch** before calling it dead. A
  catch-all lane looks feature-specific and is not; conversely, this repo also
  contains genuinely unreachable arms (the parity audit's old elif) — the
  difference is established by probing reachability, not by reading.
- **The corpus is part of the environment.** A test that fails with
  `CorpusArchiveMissingError` in the spike worktree is an environment artifact
  (missing `LAWVM_CANONICAL_DATA_ROOT`), not a breakage — it reads exactly
  like one.

## When the answer is "do not do it yet"

Report that too. A spike that finds the change requires a spec decision, a
cross-shard routing decision, or an unbounded rule is done — surface the
trade-off as a stop condition in the ledger rather than deciding it. That is
how batch 09 earned batch 10 in the source repo, and how F-03 here became a
design question instead of a wrong fix.
