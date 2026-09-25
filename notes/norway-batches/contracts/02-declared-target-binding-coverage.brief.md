# Batch 02 brief — declared-vs-bound amendment target coverage

Authoritative rationale for `02-declared-target-binding-coverage.json`.
The JSON carries the machine-checked contract; this file carries the reasoning
the implementer and reviewers must read. Source: `notes/NORWAY_VERIFY_FINDINGS_LEDGER.md` F-10 / W-8.

## Objective

Read Lovdata's declared-target list on every Norway amendment artifact, store it on the index entry, and emit one typed blocking adjudication per act whose bound base_ids do not cover its declared targets. The reading primitives already exist in grafter.py and are extracted, not rewritten. A completeness assertion only: it must not bind a new target, change an op, or move the verify scoreboard.

## Requirements

1. Extract, do not duplicate. grafter.py:_iter_unstructured_no_change_groups already xpaths the changesToDocuments dd class, reads its <li> descendants, and normalizes each via normalize_lovdata_refid. Move that block into ONE shared helper in sources.py called from both the grafter and the index. Behavior-preserving: changed_docs and default_base_id identical. Do NOT reuse parse_header_value here: its XPath string() flattening returns one separator-free token. Do NOT write a new id normalizer: normalize_lovdata_refid already maps lov/<date>-<number> and lov/<date> to no/lov ids and forskrift/null to None. Pin both behaviors in tests.
2. Bucket the 109 'lov/<date>' items separately. They normalize to well-formed ids like no/lov/1967-02-10, but no corpus law id has that shape, so they can never bind. Counted as ordinary unbound targets they inflate the gap by 109 and stop it reconciling with the probe.
3. Settle the block-presence definition in code and in test names: 2942 of 3089 artifacts carry a block (all non-empty), 147 carry none, and 2941 blocks hold at least one lov-form target. no/lovtid/2021-06-18-115 declares only forskrift/1952-04-21-4287 and must neither raise nor emit a false unbound adjudication.
4. Add a declared-targets field to NOAmendmentIndexEntry with a default that preserves existing call sites, and extend from_dict with .get so an index JSON written before this change still loads. to_dict is generic via asdict and should need no change.
5. Emit one adjudication per act whose declared law targets are not covered by its bound base_ids, appended to NOAmendmentIndex.diagnostics via diagnostic_detail: rule_id 'no_amendment_index_declared_target_unbound', family 'source_pathology', phase 'acquisition', blocking=True, strict_disposition='block', quirks_disposition=QuirksDisposition.RECORD.
6. The adjudication detail must carry source_id, the declared count, the bound count, and the sorted unbound target ids, so it can be acted on without re-deriving it.
7. Add the _NO_RULE_SPECS entry in the siblings behavioral voice: the gap is recorded, not repaired. It must NOT claim the declared list never authorizes a binding anywhere in the frontend — false today, since the grafter uses a sole declared ref as default_base_id. Scope the claim to the index.
8. Test no/lovtid/2022-12-20-115 end to end: 14 declared, 6 bound, adjudication names exactly the 8 unbound.
9. Test that a fully-covered act emits NO adjudication, else the check is vacuous.
10. Test the separator trap: the helper returns multiple distinct ids, and not the single concatenated token parse_header_value gives for the same input.

## Invariants

- base_ids stays derived solely from extracted ops; this batch adds, removes, or reorders none.
- The grafter's sole-declared-ref default_base_id is PRE-EXISTING and must be preserved exactly: same acts, same ids.
- n_ops unchanged for every act.
- No replay behavior change: no op created, dropped, retargeted, or reordered.
- The verify scoreboard at 2026-07-10 stays 12 consistent / 8 divergent / 0 error, every per-law divergence count byte-identical.
- The 147 block-less acts and the forskrift-only no/lovtid/2021-06-18-115 neither raise nor emit a false unbound adjudication.
- Existing index diagnostics keep their rule ids, blocking flags, and dispositions.
- Every no_* rule id emitted under src/lawvm/norway/ has a _NO_RULE_SPECS entry.
- The norway and tools_cli_debug shards pass.

## Exclusions

- Fixing extraction so a declared target actually binds. This batch measures; closing the gap is F-10 steps (b) and (c). A patch that newly binds a target has violated the contract.
- The bulk-rename list grammar and its terminology-substitution lowering (F-10 family 1, 53 acts) — separate batch, gated behind W-7 since 322 of its 402 bindings are contingent.
- Making the 109 'lov/<date>' targets resolvable. Bucket them; changing the id grammar or the corpus is its own decision.
- Changing or extending the grafter's default_base_id rule. The extraction is a pure refactor.
- The 286 bound-but-not-declared bindings. Surface them if free, do not act on them.
- Commencement and the contingent/dated split. This batch is indifferent to whether an act would apply.
- F-04's OPS_MISSING half (§8(4) of no/lov/2015-05-12-27).
- Ledger and progress updates: the human apply step.

## Stop conditions

- If a declared <li> payload outside the measured closed set appears, stop and record the counter-example rather than widening a rule to swallow it.
- If the declared-targets field cannot keep from_dict backward-compatible with a pre-change index JSON, stop and report; silent migration of persisted state is out of scope.
- If emitting the adjudication changes any law's replay output or divergence count, stop: the declared list has leaked into binding authority.

## Review focus

- Authority leakage is the central risk: the declared list is oracle-grade metadata and §2.2 makes evidence never a repair permission. Read the diff and confirm no declared id reaches base_ids, op construction, or target resolution through anything this batch ADDED, including error and fallback branches. Baseline precisely: the grafter ALREADY binds from a sole declared ref, so the question is whether this patch widens that, not whether it ever happens.
- Confirm the grafter block was EXTRACTED and reused, not copied — a second parser in sources.py reimplementing the same xpath and normalization is the defect to catch, since two copies diverge. Confirm normalize_lovdata_refid was reused, not reimplemented. Confirm the extraction preserves changed_docs and default_base_id.
- Confirm the helper reads <li> elements, not the string() flattening; a regex splitting the concatenated token apart is a workaround for the wrong helper.
- Confirm the 109 non-resolving 'lov/<date>' ids are bucketed apart from real unbound targets, else the gap inflates by 109 and stops reconciling with the probe.
- Confirm the no-gap case is tested and passes. If every act emits an adjudication the check is vacuous — the failure batch 01's reviewers caught.
- Confirm the 147 block-less acts, the forskrift-only act no/lovtid/2021-06-18-115, and the literal 'null' item each take a path that neither raises nor invents an unbound target.
- A new no_* rule id is found by AST scan and must be cataloged; confirm the _NO_RULE_SPECS entry exists and reads in the siblings voice. Batch 01 aborted on this coupling.
- Confirm the round-trip: build an index, to_dict, from_dict, and assert declared targets and adjudications survive unchanged.

## Field verification

- uv run lawvm no-verify-scan --limit 50 --as-of 2026-07-10 — MUST still be 12 consistent / 8 divergent / 0 error. Any movement means the declared list leaked into binding authority: revert, do not accept the improvement.
- uv run lawvm no-divergence no/lov/2015-05-12-27 --as-of 2026-07-10 — still 5 Fylkesmannen/Statsforvaltaren MISMATCHes plus the §8(4) OPS_MISSING. This measures F-04's cause, it does not fix it.
- uv run python scripts/probes/no_declared_target_coverage.py — reconcile the emitted adjudication count against the probe's 4088 across 1245 acts. Record both and explain any difference; do not tune either to match.
- Confirm the adjudication is present and blocking for no/lovtid/2022-12-20-115 and absent for a fully-bound act.
- Update the ledger: F-10 step (a) done with the apply commit, W-8 struck, changelog line, and whether the count matched 4088.
