---
name: norway-batch-author
description: Use when authoring, promoting, running, or applying a contract-driven Norway batch in this repo — anything touching notes/norway-batches/, scripts/norway_batch_preflight.py, or .claude/workflows/norway-batch.js. Covers writing a contract from the findings ledger, validating it, promoting it, running the workflow, and applying the result. Triggers on "run batch NN", "next norway batch", "write a contract for", "promote batch", or a request to apply a reviewed batch patch.
---

# Authoring and running a Norway batch

Read `notes/NORWAY_VERIFY_FINDINGS_LEDGER.md` first — it is the source of
batches: each work-queue item (W-1..) becomes at most one contract. This file
is the procedure only. The pipeline is ported from read-aloud-2's
typescript-batch harness; its hard-won rules carry over unless marked lawvm.

## 1. Write the contract from evidence, never from inspection

Establish the facts by doing, not by reading. A contract written by only
reading the code has been wrong every time it was tried in the source repo —
two contracts cost a full run each.

Which instrument depends on what is uncertain (the **norway-batch-spike** skill
opens with the full table):

- **Blast radius unknown** (deletion, `core/` seam, parse/lowering/index path)
  → run the spike skill. Its deliverable maps one-to-one onto contract fields:
  blast radius becomes scope, traps become preflight checks, the measured field
  delta becomes `fieldVerification`.
- **Scope known, one mechanism in doubt** → write a read-only probe over the
  corpus instead. Minutes, no worktree. Batch 01's digit rule died this way,
  before any agent ran.
- **Neither** → straight to the contract.

Either way, the evidence is what the contract records — and a probe or spike
that kills a requirement is a success, not a delay. Record the counter-evidence
in the findings ledger so the question stays answered.

**Scope tight, solution loose.** Pin what must be true and which files are in
play; do not prescribe the implementation. Naming a file that does not exist
yet, or dictating exact rule regexes/type names, leaves reviewers nothing to
catch.

**Scope has two levels.** `scope.boundary` is the hard limit (patterns:
`dir/`, `*` within a segment, `**` across). `allowedPaths` is the manifest of
what you expect to change; in-boundary-off-manifest paths are surfaced to
reviewers rather than aborting. Required paths stay literal.

**Each preflight check asserts the minimum fact the batch depends on.** One
atomic, provable claim per check. lawvm: checks may cite read-only CLI output
(`uv run lawvm no-divergence ... --as-of <date>`); always pin the `--as-of`
date, or the claim goes stale the day the corpus snapshot moves (the F-01
lesson — three laws read as defective purely from a horizon mismatch).

**Re-verify every check when reopening an old contract.** Batches land under
each other; a check that asserts already-finished work sends the implementer
to "fix" correct code.

**lawvm invariants worth restating per contract** (reviewers are primed for
them, the contract should still pin the applicable ones):

- compare-only lanes never mutate replay-authoritative state;
- new filter/recovery/projection behavior emits its typed receipt or
  projection — silent behavior change is a defect even when tests pass;
- the consolidation is evidence, never repair permission (`NORWAY_LAWVM_STATUS.md` §2.2).

## Experiments are not batches

The harness runs `confirmed` and `security` contracts only; the preflight
rejects anything else. Measure-look-adjust work is interactive: do it by hand,
and if it earns promotion the experiment *is* the spike — write a `confirmed`
contract from the resulting diff.

## 2. Validate before spending anything

```bash
uv run python scripts/norway_batch_preflight.py <contract> --audit
```

Deterministic, about a second, no agents. **errors** mean something is wrong;
**readiness** means valid but not authorised; **warnings** are style tells.
Fix errors and warnings before promoting. The preflight also fails loud when
`data/norway.farchive` is a stub — a Norway batch cannot be judged without the
corpus.

## 3. Promote — contract and ledger in one commit

The preflight requires the ledger's recorded hash to match the contract at
HEAD, so a split commit leaves a state the harness refuses to run from.

1. Set the contract's `productBaseline` to the current product commit.
2. Hash the edited contract (`sha256sum`).
3. Set the ledger entry's `state: "ready"`, `readyAtHead` to the same commit,
   and `contract.sha256` to that hash. Recompute `sourceReview.sha256` if the
   findings ledger changed.
4. Commit both together.

Use the **product** baseline, not HEAD: `.claude/` and `notes/` are allowed
control-plane drift, so pinning the product commit keeps the batch runnable
across later control-plane changes. Anything under `src/`, `scripts/`, or
`tests/` moving invalidates readiness — rebase the contract deliberately.

## 4. Run

```bash
uv run python scripts/norway_batch_preflight.py <contract> --json > /tmp/facts.json
```

```
Workflow({scriptPath: ".claude/workflows/norway-batch.js",
          args: {mode: "full", facts: FACTS}})   # reviewed patch out; ladder runs at apply
```

Generate FACTS to a file and pass it verbatim — hand-typing the payload cost a
run in the source repo (a seven-character head).

**Always `scriptPath`, never `name`.** Name resolution serves a script cached
at session start, so an edited workflow silently does not run.

**Do not gate every run with `preflight-only`.** A failing preflight aborts a
`full` run at the same point, before any write-capable agent starts, so the
gate fails no cheaper than the run it guards. Use `preflight-only` only when a
human should read the evidence before committing the spend (contract written
without a spike; reopened contract; one check you are unsure of).

**Never commit, or leave an edit uncommitted, while a run is in flight.** The
facts freeze `head` at launch; every isolated agent aborts on a mismatched
base; the patch applies cleanly only to the tree it was built against.

## 5. Apply — this part is the human's, and never an agent's

The workflow never applies, commits, or edits the ledger; `merged` is always
false. It never runs the full ladder either: the report's `humanVerification`
block carries the checks and the `applyLadder` stages, and the whole ladder
runs exactly once — here, in the main checkout. On a reviewed patch:

```bash
git status --porcelain --untracked-files=all   # nothing new since the facts
sha256sum <patch>                              # must equal the reported hash
git apply --check <patch>
git apply <patch>
# then every applyLadder command from the report, in order, fail fast
# (the ladder is ./scripts/ci.sh --affected over the contract scope)
```

If a ladder stage fails, `git apply -R <patch>` restores the tree; classify
the failure before reacting (see the abort section). Then run the contract's
`fieldVerification.instructions` — for Norway batches that is usually the
replay-vs-consolidation evidence: `no-divergence` / `no-verify-scan` at the
pinned `--as-of`, with the expected delta stated in the contract. **A batch
can be wrong about what verify sees while every test passes; the scan count is
the field truth here** (the source repo's "count it before and after" rule).

Then **two commits**: product files only, then the ledger (an entry cannot
contain its own commit hash). Update `notes/NORWAY_VERIFY_FINDINGS_LEDGER.md`
in the ledger commit: finding status to `fixed (<commit>)`, changelog line,
scoreboard if the scan moved.

Record in the ledger entry: patch identity, `application.commit`, the full
ordered stage list (report's `targetedStages` plus every `applyLadder` stage
run here), `evidence.reviewVerdicts` from the actual per-reviewer verdicts,
and `evidence.rejectedFindings` copied from the report. Do not record every
review as an approval when one raised findings — the rejection reason is what
a later reader has to go on, and it exists nowhere else once the session ends.

## Rules that do not bend

- One implementer, two independent reviewers, fixer acts only on adjudicated
  findings, one bounded fixer cycle.
- Everything Python goes through `uv run`; bare python is the wrong
  interpreter (AGENTS.md). Isolated worktrees export
  `LAWVM_CANONICAL_DATA_ROOT` for corpus access; the workflow injects this.
- No stubs, compatibility layers, or test weakening. Abort instead of
  improvising when an assumption fails — that abort is the loop working.
- The full ladder runs exactly once, at apply time, in the main checkout.
  Targeted stages belong to Implement and Fix.
- Never edit a completed batch's contract; its `productBaseline` is a frozen
  historical record later prerequisite audits check against.
- Report-don't-act is for orphans a reviewer cannot cheaply confirm, not for a
  single unreferenced symbol sitting in the diff they are already reading.

## When a run aborts

Classify before reacting. **Substance** — the contract is wrong about the
code — means fix the contract; that is the system working. **Bookkeeping** —
an agent's report shape, an id collision, a verdict label, a stage count —
means fix the harness, because discarding finished work over a label is a
defect in the harness, not in the batch. Known pre-existing red shards are
listed in `notes/IMPLEMENTATION_DIVERGENCE_LEDGER.md`; check it before
attributing an apply-ladder failure to the patch.
