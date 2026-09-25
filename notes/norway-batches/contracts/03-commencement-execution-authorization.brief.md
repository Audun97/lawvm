# Batch 03 brief — commencement execution authorization

This brief is the binding detail behind
`03-commencement-execution-authorization.json`. The contract's requirement
lines are summaries; where they and this brief differ in precision, the brief
wins. Evidence base: W-7 tranches 1–2 in
`notes/NORWAY_VERIFY_FINDINGS_LEDGER.md` (2026-07-31 changelog entries), the
probes `scripts/probes/no_w7_unlock_landscape.py` and
`scripts/probes/no_zero_amendment_divergence.py`, and
`NORWAY_LAWVM_STATUS.md` §2.3 and §7 item 4.

## 1. What exists, and what is missing

The instrument lane is fully built and deliberately stops one step short:

- `parse_no_commencement_instrument`
  (`src/lawvm/norway/commencement_instruments.py`) classifies every
  `no://forskrift/` artifact into a total partition. Over the freshly ingested
  corpus: **35,955 instruments = 608 whole-act candidates + 33,590 benign +
  1,757 blocked-unresolved**, asserted by `is_partition()` in
  `build_no_amendment_index` (`index.py:337`).
- The `whole_act` classification is already strict (`commencement_instruments.py:282`):
  exactly one operative `legalP` block, that block *fully* matching
  `_WHOLE_ACT_RE` (`^(?:denne )?(?:loven|lova) trer i (?:kraft|verk)\b[^§]{0,400}$` —
  the `[^§]` guard excludes provision-scoped commencements), AND exactly one
  ISO date in `dateInForce`. Partial commencements ("Delvis ikraftsetting …
  § 10-3") land in `unresolved` scope. Do not weaken any of this.
- `NOCommencementInstrumentCandidate.replay_authorized` is hardcoded `False`:
  the field exists, `to_dict` writes the literal `False`
  (`commencement_instruments.py:81`), and `from_dict` never reads the key.
  This was the design placeholder for exactly this batch
  (`NORWAY_LAWVM_STATUS.md` §2.3: "until a separate typed
  execution-authorization validator is implemented").

Missing: the validator. Nothing consumes the 608 candidates; 1,436 amendment
acts sit unresolved (1,430 `contingent`, 4 `unknown`, 2 `missing`) and 217 of
237 amended executable laws are commencement-blocked because of them.

## 2. The measured payoff, which is also the reconciliation target

From `scripts/probes/no_w7_unlock_landscape.py` on the ingested corpus
(2026-07-31):

| | |
|---|---|
| Unresolved acts with a single-date whole-act instrument | **520** |
| Same-act different-date conflicts | **0** |
| Blocked laws whose every blocker is such an act | **38** |
| Scan candidate set after authorization | **58** (from 20) |

These are assertions, not aspirations. If the built validator authorizes any
number other than 520, stop and record the delta — the probe or the gate is
wrong, and either is a finding. Do not adjust the gate to reach 520.

## 3. The gate, precisely

Authorize the pair (instrument, act) iff ALL of:

1. the instrument's parse result is `CANDIDATE` (never resurrect benign or
   blocked parses);
2. `scope_status == WHOLE_ACT`;
3. `len(effective_dates) == 1`;
4. some id in `affected_law_ids` aliases to the act:
   `"no/lov/" + act.source_id.removeprefix("no/lovtid/")` — instruments cite
   the amending act by its **law** id, the index keys it by **lovtid** id, the
   date-and-number segment is shared;
5. the act's `effective_status` is in `NO_UNRESOLVED_EFFECTIVE_STATUSES`.

Conjunct 5 doubles as the **enabling-statute filter** and it is
load-bearing: thousands of instruments commence a *forskrift* and cite the
forskrift's hjemmel statutes in `basedOn` (e.g.
`no/forskrift/2001-02-13-128` cites `no/lov/1952-11-21-2` and
`no/lov/1997-02-28-19`). Those statutes are principal laws, not unresolved
amendment acts, so the alias join finds nothing and nothing authorizes. A
cited id matching no unresolved act is the *normal case*, not an error — no
receipt for it.

**Conflict gate.** If two instruments would authorize the same act at
different dates, refuse both and emit a typed conflict receipt naming both
instruments and both dates. The corpus measures zero conflicts today; the
gate exists because the corpus grows. Two instruments agreeing on the same
date are not a conflict (dedupe to one authorization; name either or both
instruments in the receipt, your choice, but deterministically).

**Anchor case** (also the preflight's live pair): `no/forskrift/2012-01-27-71`
— "Ikrafttredelse av lov 27. januar 2012 nr. 9 om arbeidstvister
(arbeidstvistloven)", whole-act, single date `2012-03-01`, citing
`no/lov/2012-01-27-9`; the index holds `no/lovtid/2012-01-27-9` as
`contingent` / `"Kongen bestemmer."`. After the batch that entry carries the
new status and `effective_date == "2012-03-01"`.

**Negative anchor**: no instrument cites `no/lov/2026-06-19-48` (F-03's
mixed-commencement act). It must remain exactly as it is — still classified
`dated` by the metadata parser (its demotion is W-5's separate decision, not
this batch), and gaining nothing from this validator.

## 4. The new status and how it must flow

Add ONE new member to `NOEffectiveStatus` (`sources.py:131`; name is yours —
something like `INSTRUMENT_AUTHORIZED`, but the contract does not pin it) and
add it to `NO_RESOLVED_EFFECTIVE_STATUSES`. It must be distinct from:

- `DATED` — metadata-derived, no official instrument in evidence;
- `OVERRIDE` — manually curated evidence via the sidecar.

The point of the three-way distinction is provenance: a reader of any serialized
index must be able to tell *why* an act has a date.

The status plumbing is designed to need **no other special-casing**. Verify,
don't assume, and if one of these needs patching, treat it as a design leak
and stop:

- `replay.py:305,320` gates on the string values `"contingent"` /
  `"missing"` / `"unknown"` and replays anything else carrying an
  `effective_date`;
- `no_base_replay_status_from_statuses` (`sources.py:240`) blocks only on
  `CONTINGENT`, `UNKNOWN`, `MISSING`;
- `inventory.py`, `verify.py`, and the report lanes in `commencement.py`
  filter on the two frozensets, not on enumerated members.

`apply_no_commencement_overrides` (`commencement.py:145`) replaces the status
of any entry with a dated override *after* the index is built, so a manual
override naturally outranks an instrument authorization. Preserve that: do
not make the validator skip overridden acts or otherwise interleave the two
lanes — the ordering IS the precedence rule.

Authorization runs **inside `build_no_amendment_index`**, after entries are
built and instruments parsed, so inventory, scan, replay, and reports all see
one consistent view. No consumer applies authorization itself.

## 5. Receipts

Two new receipt families, both into `NOAmendmentIndex.diagnostics` via
`diagnostic_detail` (`rule_id, phase, blocking, family, reason, message,
strict_disposition, quirks_disposition, detail, **extra` — no `role`, no
`default_enforcement`):

- **Authorization receipt** — one per authorized act: instrument
  `source_id`, act `source_id`, date. This is a positive provenance record,
  not a pathology: `blocking=False`, `strict_disposition="record"`,
  `quirks_disposition=RECORD`.
- **Refusal receipt** — for every whole-act candidate that cites at least one
  unresolved act and still fails the gate (multi-date, conflict): name the
  conjunct that failed. Conflicts are `blocking=True` (same-act contradictory
  official evidence is a source pathology); a lone multi-date refusal is
  `blocking=False` — the instrument simply remains evidence.

Candidates citing no unresolved act emit nothing (see §3). Rule-id naming
follows the lane's existing `no_lovtidend_commencement_*` prefix. Every new
rule id needs a `_NO_RULE_SPECS` entry
(`src/lawvm/tools/spec_ledger_no_catalog.py`, shard `tools_cli_debug`) in the
sibling voice — batch 01 aborted for missing exactly this.

`replay_authorized` becomes real: `to_dict` writes the actual value,
`from_dict` reads it with default `False` (a hand-built dict without the key
deserializes `False` — pin in a test). Only gate-passing candidates carry
`True`, and only their paired act re-dates.

## 6. Test menu (minimum, from the contract, expanded)

1. Anchor: `no/lovtid/2012-01-27-9` authorized at `2012-03-01` by
   `no/forskrift/2012-01-27-71` (corpus-backed or fixture mirroring it).
2. Non-whole-act candidate (partial commencement) → no authorization,
   refusal receipt only if it cites an unresolved act.
3. Multi-date instrument → refused, receipt names the date conjunct.
4. Synthetic conflict: two fixtures, same act, different dates → both
   refused, blocking conflict receipt naming both.
5. Same act, same date, two instruments → one authorization, no conflict.
6. Enabling-statute case: instrument citing only principal-law ids → no
   authorization, no receipt.
7. Already-dated act cited by a valid instrument → untouched (gate conjunct
   5), no receipt.
8. `replay_authorized` round-trip, including the missing-key default.
9. Corpus reconciliation (source-present test, skipped on stub archive):
   exactly 520 authorized, 0 conflicts, scan candidate set 58.
10. Serialization back-compat: an index dict written before this batch (no
    new status, no `replay_authorized` values) still loads.

## 7. Field verification at apply (the human's, in order)

1. `uv run lawvm no-verify-scan --as-of 2026-07-10 --limit 200` —
   `candidate_count` **58**; the original 20 rows **byte-identical** at
   12/8/0. Any movement in those 20 means authorization leaked into laws that
   were already replayable: revert. (Why they cannot move: a law is in the
   old set only if it has zero unresolved blockers, and the validator touches
   only unresolved acts.)
2. Record the 38 new rows as the new baseline. Verdicts unknown ex ante —
   divergences among them are *findings for the ledger*, not defects of this
   batch. Runtime note: the 20-law scan takes ~10 minutes with index build;
   expect ~2–3× for 58.
3. `scripts/probes/no_w7_unlock_landscape.py` — authorizable drops to 0,
   blocked 217 → 179, unresolved acts 1,436 → 916.
4. Spot-check one flipped law end-to-end: its previously-contingent
   amendment applies at the instrument date, not the sanction date.
5. `no/lov/2026-06-19-48` unchanged (negative anchor).
6. `tools_cli_debug` may be red from the pre-existing finlex corpus-absence
   rows — prove pre-existing by stash-and-rerun before attributing to the
   patch (`notes/IMPLEMENTATION_DIVERGENCE_LEDGER.md`).

## 8. Traps, restated once

- **The id-form alias.** `basedOn` gives `no/lov/D-N`; the index keys
  `no/lovtid/D-N`. The first landscape probe measured **0** authorizable acts
  because of this. The alias is one line; forgetting it is silent and total.
- **The enabling-statute shape.** "Ikrafttredelse av forskrift …" instruments
  cite hjemmel statutes. Matching against *unresolved amendment acts* is the
  filter; matching against all known laws would authorize garbage.
- **`is_partition()` is an assertion that throws.** The validator must not
  consume or reclassify parse results, or index build fails loudly.
- **Numbers are frozen to this corpus snapshot.** 35,955 / 608 / 1,757 / 520 /
  38 / 58 hold for the farchive as ingested 2026-07-31 (locator/digest state
  hash of the 6,944 pre-forskrift rows: `abda820f…`). If the archive moved,
  re-run the landscape probe and re-pin before running the batch.
- **`effective_date` vs the instrument's own date fields.** The instrument's
  `dateInForce` (its §2 text) is the commencement date; the instrument's own
  publication date is not. `effective_dates[0]` of the candidate is already
  the right value — use it, don't re-derive.
