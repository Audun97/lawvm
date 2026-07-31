# Norway Verify Findings Ledger

> **Status (2026-07-30):** Living triage ledger. Companion to
> `NORWAY_LAWVM_STATUS.md` (the normative claim/limits doc — this file never
> overrides it). Records what the replay-vs-consolidation verification of the
> currently replayable corpus actually found, one finding per defect family,
> and the ordered burn-down queue. Update this file as findings are fixed,
> reclassified, or added; append to the changelog at the bottom.

## 1. Scope And Method

Full verify scan over every executable fully-replayable current law in the
local snapshot (20 laws; local packages as listed 2026-07-11, consolidation
snapshot `gjeldende-lover` dated 2026-07-10):

```bash
uv run lawvm no-verify-scan --limit 50 --as-of 2026-07-10 --json
uv run lawvm no-verify-partition --limit 50
uv run lawvm no-divergence <BASE_ID> --as-of 2026-07-10 --max-divergences 500 --json
```

Divergences were then classified by hand/script into: engine defect, missing
amendment (index/acquisition), compare-lane noise, editorial/oracle issue,
temporal-horizon artifact, sparse-source ceiling. Per
`NORWAY_LAWVM_STATUS.md` §2.2, a divergence never authorizes preferring the
consolidation; every class below is evidence to triage, not a repair license.

## 2. Scoreboard

| as-of | consistent | divergent | error |
|---|---|---|---|
| 2026-03-29 (scan default) | 8 | 12 | 0 |
| 2026-07-10 (snapshot-commensurable) | 11 | 9 | 0 |
| **2026-07-10, after batch 01 (f4eae341a)** | **12** | **8** | 0 |

The delta between the first two rows is itself finding F-01: three laws
(`no/lov/2020-05-07-38`, `no/lov/2025-06-20-102`, `no/lov/2025-12-22-116`)
read as defective at the default date purely because an amendment took effect
between 2026-03-29 and the snapshot, and `no/lov/2022-03-11-9` showed 9
divergences instead of its real 1.

At the commensurable horizon the 9 divergent laws carried 313 provision-level
divergences, of which **295 sit in the two known sparse-source laws**
(`no/lov/2006-06-30-50`: 212, `no/lov/2001-01-05-1`: 83). Outside those, the
corpus had **18 divergences across 7 laws**, classified below. Batch 01 has
since cleared one of them (F-06), leaving 17 across 6 laws.

## 3. Findings

Statuses: `open`, `fixed (<commit>)`, `reclassified`, `wontfix (<reason>)`.

### F-01 — Scan default `as_of` is not snapshot-commensurable — open (tooling)

`no-verify-scan` defaults to an `--as-of` (2026-03-29 at the time of the scan)
that predates the consolidation snapshot it compares against, exactly the
incommensurability `NORWAY_LAWVM_STATUS.md` §5 warns about. Effect measured
above. The skip lane works correctly (`no_replay_future_effective_skipped`
receipts were emitted); only the comparison framing misleads.

Action: derive the default comparison date from the consolidation package
date (or refuse/warn when `as_of` < snapshot horizon).

### F-02 — Sentence-level (punktum) unstructured leads not lowered — open (engine, deferred behind W-7)

`no/lov/2022-03-11-9` (vareførselsloven), its one real divergence: replay
retains the third sentence of chapter:2/section:2-3/subsection:1 ("Melding kan
gis av andre på førerens vegne.") that the published text has removed. The
engine already refuses loudly:

```text
no_parse_unstructured_lead_unmatched (blocking, family unsupported_or_unresolved_action)
  "§ 2-3 første ledd tredje punktum oppheves."
```

The same family also surfaced in the rekonstruksjonsloven chain
("§ 43 annet ledd blir nytt femte ledd i § 42." — a sentence/ledd move). So the
gap is a *lowering family*: punktum-level repeal (and kin) has no supported
lowering, and every occurrence across the corpus produces a retained-text
mismatch. Fix once, fixes a class.

Repro: `uv run lawvm no-divergence no/lov/2022-03-11-9 --as-of 2026-07-10`

**Spiked 2026-07-31. Verdict: do not batch yet — measurable payoff is zero.**

The refusal is not one missing lowering; it is three defects stacked, and the
family is far larger than the payoff.

*Mechanism (measured, not read).* The sentence-lead regex at
`grafter.py:989` already covers `oppheves`, so the family looked implemented.
It is not reached, for three independent reasons:

1. the regex is `$`-anchored right after `oppheves`, and every real lead carries
   a terminal period — all 284 distinct leads fail as-is, 235 match once the
   period is stripped;
2. the token loop only ever assigns `REPLACE` or `INSERT`, so even a matching
   `oppheves` lead lowers as a replace;
3. the sentence lane requires a payload, and a repeal has none — so a matching
   repeal falls through to the refusal anyway.

*Size.* Deduplicated by (act, lead) over the 20 replayable laws' amendment
chains: **8,623 refusals, 7,660 distinct leads, 1,704 source acts**. F-02 is
**284 distinct leads** of that. Of those, 235 are reachable by period tolerance
alone; the remaining 49 need shapes the regex does not model — `nr.` nesting
(17), spaced letter-suffix sections such as `§ 10 b` (9), sentence ranges
("femte til syvende punktum", 9), two sections in one lead (4), `bokstav`
nesting (3), other (7).

*Field impact: nil.* A minimal fix (period tolerance + REPEAL action) was built
in a throwaway worktree. It lowers more ops for `no/lov/2022-03-11-9` (16 -> 18,
applied 3 -> 4) and changes that law's divergent text — but the corpus scan is
**unchanged at 12 consistent / 8 divergent, with no law moving**, and the one
affected law stays divergent with arguably worse text (replay gains
"referanse til deklarasjonen" while still keeping the sentence the repeal
should have removed). The norway shard is unaffected: the 4 red tests in the
spike worktree are identical with the change stashed.

*Why nil.* 283 of the 284 leads belong to base laws that are not replayable —
blocked on commencement (F-03 family, 217 laws) or missing base source (242).
Only one lead touches a replayable law, and its divergence is not caused by the
punktum repeal alone.

*Sequencing.* F-02 is real and worth fixing, but it is **downstream of the
commencement programme, not ahead of it**: the class only pays once its laws
become replayable. Reopen after W-7 (Lovtidend extraction) moves laws out of
the blocked pile, and scope it then as three explicit sub-batches (period +
action + payload-free repeal path; then the 49 unmodelled shapes; then the
range form), not one.

### F-03 — Mixed `dateInForce` ("DATE, Kongen bestemmer") applied at the date — open (engine/temporal, hypothesis)

`no/lov/2019-12-20-109` (kredittopplysningsloven) chapter:2/section:9/subsection:2:
at as-of 2026-07-10 replay says "konkurs, **rekonstruksjonsforhandling** og
gjeldsforhandlinger"; the published snapshot still says "konkurs, **akkord** og
gjeldsforhandlinger". The edit is verified to come from
`no/lovtid/2026-06-19-48` ("Lov om endringer i konkursloven mv.
(rekonstruksjonsforhandling)"), whose raw in-force field is:

```text
dateInForce: "2026-06-19, Kongen bestemmer"
```

The index classifies this as `dated`/2026-06-19 (the sanction date) and replay
applies it, but the "Kongen bestemmer" tail means commencement (at least in
part) awaits a royal decision the published snapshot shows has not happened.
Hypothesis: a mixed `dateInForce` should not authorize whole-act application at
the leading date — this is premature commencement, the exact failure class
`NORWAY_LAWVM_STATUS.md` §2.3 exists to prevent. Verify by checking for a
commencement instrument for 2026-06-19-48 in the forskrift lane; then decide
whether mixed dates must demote to `contingent` (blocking) pending evidence.
Note the same act carries 82 ops against rekonstruksjonsloven, so misdating it
touches multiple corpus laws.

### F-04 — Statsforvalter renaming absent from the amendment index — reclassified (see F-10)

`no/lov/2015-05-12-27` (forsvunne personar): 5 MISMATCHes are all
`Fylkesmannen`→`Statsforvaltaren` (the national 2021 renaming of the county
governor office). The index holds only one amendment for this law
(`no/lovtid/2020-12-18-149`), so the renaming act was never applied. Also one
OPS_MISSING: published §8(4) (death-abroad rule) has no corresponding op.

**Resolved by the 2026-07-31 W-3 probes — it is neither an acquisition gap nor
an index-coverage bug.** The renaming act is present and indexed:
`no/lovtid/2021-05-07-34`, 72,304 bytes, `effective_status: contingent`,
`raw_date_in_force: "Kongen fastset"`. It names **97 laws** in a bulk-rename
list and the index binds **4**, including entry 20 — "*lov 12. mai 2015 nr. 27
om forsvunne personar § 5 første ledd, andre ledd første og andre punktum og
tredje ledd første punktum, § 7, § 23 andre ledd andre punktum*" — which is
exactly the observed mismatch set, §5-clustered.

So the binding, not the acquisition, is the defect. Chasing the general form of
that defect produced **F-10**, which subsumes this finding and is much larger.
F-04 itself stays blocked twice over: on F-10's binding gap, and on the act
being `contingent` (it would not apply even once bound). The OPS_MISSING §8(4)
half is untouched by this and is still open under W-6.

### F-10 — The index ignores Lovdata's declared-target field; 47% of declared amendment bindings are lost — open (index/extraction, highest measured payoff)

Every Lovtidend amendment artifact carries a structured, machine-readable list
of the laws it changes, sitting in the same metadata block as `dateInForce`
(which the index *does* read):

```html
<dt class="changesToDocuments">Endrar</dt>
<dd class="changesToDocuments"><ul>
  <li>lov/1950-12-15-7</li><li>lov/1967-02-10</li>...
</ul></dd>
```

Nothing in `src/lawvm/norway/` reads it. `NOAmendmentIndexEntry.base_ids` is
derived solely from successfully-extracted ops (`index.py:268`), so a law the
extractor fails to reach is silently absent from the binding — with no receipt,
because a target that was never bound is never adjudicated as missed.

Measured over all 3,089 amendment artifacts (2,941 carry the field, 148 do not):

| | |
|---|---|
| Declared target bindings (Lovdata's own list) | **8,643** |
| Bound by the index | 4,841 |
| **Declared but NOT bound** | **4,088 — 47.3% of declared** |
| ...of which we hold consolidated text (verifiable) | 2,544 |
| Bound but NOT declared (index over-reach) | 286 |
| Acts with a nonempty gap | 1,245 / 2,941 |

Gap by commencement status — `dated` is the part that would apply today:

| status | acts | missed | verifiable |
|---|---|---|---|
| contingent | 555 | 1,999 | 1,246 |
| `<unindexed>` | 475 | 1,089 | 621 |
| **dated** | **214** | **999** | **676** |

**The gap is an extraction failure, not an over-inclusive declared list.** On an
18-act `dated` sample, 261 of 264 declared-but-unbound verifiable targets are
named verbatim in the act's own operative body (99%); only 3 were absent. The
declared list is accurate and the extractor is missing the targets.

Field-visible confirmation on the cleanest case — `no/lovtid/2022-12-20-115`
(Sivilombodet rename, `dated 2022-12-20`, no commencement ambiguity): declares
14 targets, binds 6. All four missed verifiable targets show the *new* term in
their consolidated text and zero occurrences of the old one:

| law | bound | "Sivilombudet" | "Stortingets ombudsmann" |
|---|---|---|---|
| `no/lov/1980-06-13-35` | no | 2 | 0 |
| `no/lov/1999-07-02-62` | no | 1 | 0 |
| `no/lov/1999-07-02-64` | no | 1 | 0 |
| `no/lov/2017-06-16-50` | no | 1 | 0 |

The amendment demonstrably happened; our replay cannot reach it.

**Why this is the first finding with a nonzero field payoff.** F-02 (W-2), F-03,
and F-04 all terminate at commencement — their fixes move the scan by zero until
W-7 lands. F-10 does not: 676 of the missed verifiable bindings sit on `dated`
acts with real in-force dates (`2022-12-20`, `2011-01-01`, `2026-06-19`), so
they apply the moment they are bound.

**Sizing caution before this becomes a batch.** The measurement is a *binding*
count, not a fix estimate. Reading the declared field is cheap; making a bound
target produce correct ops is not, and splits into at least three families:

1. **Bulk-rename list grammar** — 53 acts, 402 unreached bindings, 42 of them
   with zero structural markers. Operative form is
   "*I følgjande lovføresegner vert «X» endra til «Y»:*" + a numbered law list.
   This is a **scoped terminology substitution**, a text-patch family the engine
   has no lowering for at all — not a section replace. Largest single act:
   `no/lovtid/2021-05-07-34` (93 unreached).
2. **Ordinary multi-target omnibus acts** — the bulk of the remaining ~3,700,
   where extraction reaches some targets and not others.
3. **Declared-target id forms the current ids cannot express** — e.g.
   `lov/1967-02-10` (forvaltningsloven) has no trailing number.

Recommended decomposition, smallest-first, each independently field-measurable:
**(a)** parse and store the declared list as a *typed observed-vs-declared
adjudication* — no behavior change, but it converts an invisible 47% gap into a
receipt; **(b)** measure how many missed bindings family 2 alone recovers;
**(c)** treat family 1's terminology-substitution lowering as its own batch, and
only after W-7 since 322 of its 402 bindings are `contingent`.

Step (a) is the one to do first: it is a small, bounded, testable change that
makes every later step measurable, and it is the only one whose scope is already
known.

#### Settled 2026-07-31: the adjudication is blocking, and that is not a policy choice

W-8 was held pending a "blocking vs evidentiary" decision. **The question was
malformed** — the repo does not offer that binary, and its actual model answers
it.

*Blocking is three axes, not one.* `diagnostic_detail` carries `blocking`,
`strict_disposition`, and `quirks_disposition` independently. Norway's own index
already emits the combination this finding needs
(`index.py:_no_index_unmapped_member_diagnostic`, `_no_index_skipped_artifact_diagnostic`):

```python
blocking=True, strict_disposition="block", quirks_disposition=QuirksDisposition.RECORD
```

— blocks under strict, records and continues under quirks.

*The role taxonomy constrains the flag; the emitter does not pick freely.*
`observation_registry.validate_finding_projection` **rejects**
`role="observation"` with `blocking=True`, and **rejects** `role="violation"`
with `blocking=False`. So "evidentiary" is not a dial: it is the `observation`
role, and choosing it would have been choosing to assert that a 47.3% binding
loss is informational. `obligation` + `default_enforcement="strict_fail"` is the
registered way to say "this is a real defect, strict fails on it, the quirks
corpus proceeds".

*The concern that motivated the question was factually wrong.* I worried a
blocking finding would "fail replay on 1,245 acts overnight". Measured: **13,858
of 13,859** index-build diagnostics are *already* `blocking=True`, and
`no/lov/2020-05-07-38` carries **122 blocking replay adjudications while scoring
`consistent`** in the scan. `blocking` classifies severity for strict mode; it is
not what gates the scan. The precedent is explicit — `no_replay_no_matching_change_group`
is emitted `blocking=True` and the replay loop `continue`s (`replay.py:401-414`).

**Decision:** `role="obligation"`, `blocking=True`, `strict_disposition="block"`,
`quirks_disposition=RECORD`, `default_enforcement="strict_fail"`. No scoreboard
movement, and strict mode gains a real gate.

#### The same measurement also rescopes W-8

The per-lead extraction failures behind this gap are **already recorded** — the
index build emits 8,726 `no_parse_unstructured_lead_unmatched`, 3,710
`no_parse_unstructured_lead_base_unresolved`, and 623
`no_amendment_index_no_change_ops`. The engine is not silent about failing to
parse a lead.

What is missing is the **completeness assertion**: nothing ever asks whether the
ops that *did* survive cover the targets Lovdata *declared*. So W-8 is not "add
missing diagnostics" — it is "close the loop over diagnostics we already emit"
by making the declared list the denominator. That is a smaller change than the
original framing and a stronger one, because it turns an open-ended pile of
per-lead warnings into a per-act pass/fail with a denominator.

The two reusable measurements are kept, since a fix has to be scored against
them (read-only; JSON under `.tmp/`, gitignored):

```bash
uv run python scripts/probes/no_declared_target_coverage.py    # the 47.3% gap
uv run python scripts/probes/no_declared_target_gap_nature.py  # extraction vs declared list
```

The three one-shot probes behind the bulk-rename numbers were throwaway and are
not kept. One is worth repeating if that family is revisited: measuring the list
grammar needs the XML flattened to text first, because list numbering is split
across markup and a raw-byte regex silently reports zero.

### F-05 — Footnote-marker digits leak into the published compare text — reclassified (not fixable as a normalization rule)

Published-side extraction keeps trailing footnote reference digits:
"Loven trer i kraft fra den tid Kongen bestemmer **1.**"
(`no/lov/2019-12-20-109` §30(1)); "…frå den tid Kongen fastset **1.**"
(`no/lov/2015-05-12-27` §23(1)).

**Measured 2026-07-31, before writing the rule.** A probe collected all 8,779
compare-lane text units from both sides of the 20 replayable laws and applied
two candidate rules:

| candidate | units altered | of which the real footnote case |
|---|---|---|
| trailing digit run before a final period | 211 | 2 |
| same, bounded to 1–2 digits after a letter-ending word | 88 | 2 |

The false positives are ordinary Norwegian legal cross-references, which
routinely end a sentence: "i samsvar med artikkel **12.**", "kommuneloven
kapittel **30.**", "forvaltningsloven §§ 44 og **46.**", "personvernforordningen
artikkel **15.**". Syntactically these are identical to the footnote case
(word, space, digits, period); no tightening separates them, because the
distinction is semantic.

Worse than noise: a compare-lane rule runs on BOTH sides, so eating the trailing
number makes "artikkel 12." and "artikkel **13.**" compare **equal** — the rule
would MASK real cross-reference divergences rather than merely add them. That
is the opposite of what this lane is for.

The lane already carries three footnote rules — `no_compare_inline_footnote_marker`
(marker between sentences), `no_compare_standalone_footnote_marker` and
`no_compare_trailing_footnote_marker` (`([.!?])\s+\d+$`, marker AFTER terminal
punctuation). All three key on the marker sitting next to punctuation, which is
what makes them safely bounded. F-05's shape is the one where the marker sits
*before* the period, with nothing but a word to its left — precisely the
position that is indistinguishable from a cross-reference.

Conclusion: not a normalization problem. If it is worth solving at all, it needs
either footnote structure preserved at published-side extraction (so the marker
is typed rather than inlined) or a diff-time tolerance that is not a text rule.
Both are larger than a compare-lane batch. Left as recorded noise: 2 divergences
across the corpus, both in the commencement formula.

### F-06 — Footnote-anchor whitespace in published text — fixed (f4eae341a, batch 01)

"(forordning (EU) nr. 910/2014 **)**" vs replay "910/2014)"
(`no/lov/2018-06-15-44` §1(1)) — a space left behind by a stripped footnote
anchor. The same probe that killed F-05 measured this rule at **1 altered text
unit in 8,779**: exactly the known case, zero false positives, and the lane
already normalizes the opening-parenthesis mirror of it.

Fixed by batch `01-compare-noise-normalization` (f4eae341a):
`no_compare_close_paren_spacing`, the mirror of the opening-parenthesis rule.
`no/lov/2018-06-15-44` went 1 divergence -> 0 and is now consistent; no other
law's divergence count moved. The batch's boundedness test also pins F-05
shut — it asserts a trailing digit inside the parenthesis survives
normalization, so the `\s+\d*\s*\)` variant cannot be re-introduced.

### F-07 — Published editorial correction without an amending act — open (oracle pin)

`no/lov/2020-12-18-156` §5(1) item 2: replay "skatteloven § **23** første ledd
bokstav b" (faithful to source bytes); published "§ **2-3**". Lovdata corrected
a typo editorially. Per `NORWAY_LAWVM_STATUS.md` §2.2 this becomes an
exact-text-pinned oracle finding, not a replay change.

### F-08 — CONSOLIDATED_MISSING / mixed clusters needing triage — open

Replay retains provisions the published text no longer carries:

- `no/lov/2022-06-17-49` (Riksrevisjonen info-access, temporary): 3
  CONSOLIDATED_MISSING — plausibly the completed-purpose lifecycle of a
  temporary act (relates to F-03's theme).
- `no/lov/2023-11-24-85` (militærpolitiloven) §28(2): replay "Kongen kan gi
  overgangsregler."; published carries the 1988-act repeal clause instead, plus
  one OPS_MISSING.
- `no/lov/2015-05-12-27` §24(1): published shows "– – –" (collapsed
  consequential-amendment list) where replay keeps the introduction line.

### F-09 — Sparse-source ceiling (known class, recorded) — recorded

`no/lov/2006-06-30-50` (SCE-loven, 212 divergences, 1 indexed amendment) and
`no/lov/2001-01-05-1` (vaktvirksomhetsloven, 83, 2 indexed) both carry
`sparse_indexed_history`. Per `NORWAY_LAWVM_STATUS.md` §5 these are
acquisition ceilings, not replay failures; excluded from engine-defect counts.

## 4. Work Queue (ordered)

1. ~~**W-1 (F-06):** strip the footnote-anchor space in the compare-only
   normalization.~~ **Done** — batch 01, f4eae341a. F-05 was measured out of
   this item before any code was written; see its entry.
2. ~~**W-2 (F-02):** add the punktum-level repeal lowering family.~~
   **Deferred** by the 2026-07-31 spike: three stacked defects, 284 leads, and
   a measured field delta of zero because 283 of them sit behind the
   commencement/missing-source blockers. Reopen after W-7.
3. ~~**W-3 (F-04):** hunt the statsforvalter renaming act in the archive;
   classify as index bug vs acquisition gap.~~ **Done** — 2026-07-31 probes.
   Neither: the act is present and indexed, but binds 4 of the 97 laws it
   names. Generalizing that produced **F-10**, and F-04 now depends on it.
4. **W-8 (F-10) — promoted to the head of the engine queue:** parse the
   `changesToDocuments` declared-target list and emit a typed
   declared-vs-bound adjudication. No behavior change, but it turns a
   measured-invisible 47.3% binding gap into a receipt, and makes every
   later extraction fix measurable. **This is the first open item with a
   nonzero field payoff** — 676 missed verifiable bindings sit on `dated`
   acts, unlike W-2/F-03/F-04 which all terminate at commencement. Scope is
   already known, so it goes straight to a contract; no spike. The
   blocking-vs-evidentiary question is **settled** (see F-10): obligation role,
   `blocking=True`, `quirks_disposition=RECORD`, `strict_fail` — measured not to
   move the scoreboard, since 13,858/13,859 existing index diagnostics are
   already blocking.
5. **W-4 (F-01):** make `no-verify-scan`'s default comparison date
   snapshot-commensurable.
5. **W-5 (F-03):** check the forskrift lane for a 2026-06-19-48 commencement
   instrument; decide whether mixed "DATE, Kongen bestemmer" in-force fields
   must demote to `contingent` (blocking) pending typed evidence.
6. **W-6 (F-07, F-08):** pin the editorial correction; triage the
   CONSOLIDATED_MISSING clusters.
7. **W-7:** only then return to the commencement-evidence programme
   (`NORWAY_LAWVM_STATUS.md` §7 items 4 and 7) to grow the corpus past 20.

## 5. Demo / Inspection Tooling

Browser views of any replayable law across its own amendment dates, plus an
index page of the whole scanned corpus with verdicts (output under `.tmp/`,
gitignored):

```bash
uv run scripts/demos/no_browser_demo.py no/lov/2020-05-07-38 --out .tmp/no_demo/law.html
uv run python scripts/demos/no_browser_index.py --out .tmp/no_demo --as-of 2026-07-10
```

These are presentation-only: they render `replay_no_to_pit` output and never
feed anything back into replay. The index page's verdict grouping is a
browsing aid; `no-verify-partition` remains the authoritative classifier.

## 6. Changelog

- **2026-07-31 (design)** — **W-8's blocking-vs-evidentiary question settled by
  measurement, and the question turned out to be malformed.** The repo does not
  offer that binary: `blocking`, `strict_disposition` and `quirks_disposition`
  are independent axes, `validate_finding_projection` forbids
  `observation`+blocking and `violation`+non-blocking, and Norway's index
  already emits `blocking=True` with `quirks_disposition=RECORD`. The concern
  that prompted the hold — that a blocking finding would redden 1,245 acts —
  was wrong by two orders of magnitude: **13,858 of 13,859** index diagnostics
  are already blocking and `no/lov/2020-05-07-38` scores `consistent` while
  carrying 122 blocking adjudications. Decided: obligation / `blocking=True` /
  `strict_disposition="block"` / `quirks_disposition=RECORD` / `strict_fail`.
  The same measurement rescoped W-8: the per-lead failures are already recorded
  (8,726 + 3,710 + 623), so the batch is a **completeness assertion over
  diagnostics that already exist**, not new diagnostics.
- **2026-07-31 (probe)** — **W-3 done; F-04 reclassified and F-10 opened.**
  Five read-only probes, no worktree, no agents. The statsforvalter act turned
  out to be present and indexed but binding 4 of the 97 laws it names, which
  led to the general question and then to the `changesToDocuments` field:
  Lovdata declares its own amendment targets in structured markup and the index
  reads none of it — **4,088 of 8,643 declared bindings (47.3%) are lost**, 99%
  of them extraction failures rather than an over-inclusive declared list
  (18-act sample, 261/264 targets named verbatim in the act body). Two process
  notes worth keeping. First, the initial prevalence pass measured **0**
  unreached bindings for the very act it was built from: list numbering is split
  across markup, so a raw-byte regex could not see it. The pass was only
  trusted after it reproduced the hand-verified case (93). *A corpus probe that
  cannot reproduce its own seed case is measuring nothing.* Second, the count
  alone would have been a bad basis for a batch — the false-positive check is
  what promoted this from "a grammar we don't parse" to "a structured field we
  ignore", and it is also what found the payoff: unlike W-2, F-03 and F-04, this
  one does **not** terminate at commencement (676 missed verifiable bindings sit
  on `dated` acts). W-8 is now ahead of W-4 in the queue.
- **2026-07-31 (spike)** — **W-2 spiked and deferred.** The minimal fix was
  built in a throwaway worktree and moved the corpus scan by nothing; F-02's
  entry now carries the mechanism, the 284/8,623 sizing, the 49 unmodelled
  sub-shapes, and the sequencing behind W-7. The spike also found a harness
  bug: `LAWVM_CANONICAL_DATA_ROOT` alone does NOT resolve Norway sources in a
  worktree (`resolve_no_source_path` reads `LAWVM_NORWAY_DB`), so every replay
  in an isolated agent worktree failed with "no original-act source available"
  — fixed in the spike skill and the workflow's env line.
- **2026-07-31 (applied)** — **Batch 01 landed** (f4eae341a), the harness's
  first completed batch. F-06 fixed; scan 11 -> 12 consistent with every other
  law's row byte-identical. Run 2's fixer cycle replaced a vacuous boundedness
  test the first reviewers caught, and the final reviewers verified the
  replacement by mutation testing — including that it now kills the F-05
  digit-eating variant, so the probe's verdict is enforced in code rather than
  only recorded here. The apply ladder reported tools_cli_debug red; classified
  pre-existing by reversing the patch and re-running to a byte-identical
  14-row failure set (all corpus-absence from the stub finlex archive).
- **2026-07-31 (later)** — Batch 01 run 1 **aborted at Adjudicate**, correctly:
  the new rule id needs a `_NO_RULE_SPECS` catalog entry
  (`tools/spec_ledger_no_catalog.py`, shard `tools_cli_debug`) that the
  norway-only contract scope did not authorize. Reviewers reproduced the guard
  failure against a patched copy, and also caught the implementer writing the
  contract's own boundedness test vacuously (comparing `910/2014` vs `910/2015`
  — a difference outside the region the rule touches, so it passes without the
  rule). Contract amended to include the catalog and a fourth targeted stage;
  the probe had proved the regex bounded but said nothing about reach, which is
  now a documented step in the spike skill.
- **2026-07-31** — Pre-batch probe over all 8,779 compare-lane text units
  reclassified **F-05**: both candidate normalization rules alter ordinary
  legal cross-references ("artikkel 12."), and because compare rules run on
  both sides they would MASK real divergence rather than add noise. Measured
  before writing the rule, so it cost a probe rather than a review cycle.
  **F-06** measured clean at 1/8,779 and became batch 01.
- **2026-07-30** — Initial ledger from the first full 20-law scan.
  Headline: 11/20 exact at the commensurable horizon; outside the two
  sparse-source laws only 18 divergences corpus-wide, dominated by one
  lowering-family gap (F-02), one premature-commencement suspect (F-03), one
  missing renaming act (F-04), and compare-lane noise (F-05/F-06). Two
  in-session corrections worth keeping: the vareførselsloven §7-22 block and
  the viltressursloven divergences were horizon artifacts (F-01), not engine
  gaps; and the kredittopplysningsloven "akkord" divergence traced to a mixed
  in-force field (F-03), not to sunset self-reversal as first hypothesized.
