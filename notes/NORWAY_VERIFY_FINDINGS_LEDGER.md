# Norway Verify Findings Ledger

> **Status (2026-07-31):** Living triage ledger. Companion to
> `NORWAY_LAWVM_STATUS.md` (the normative claim/limits doc — this file never
> overrides it). Records what the replay-vs-consolidation verification of the
> currently replayable corpus actually found, one finding per defect family,
> and the ordered burn-down queue. Update this file as findings are fixed,
> reclassified, or added; append to the changelog at the bottom.

## 1. Scope And Method

Full verify scan over every executable fully-replayable current law in the
local snapshot (58 laws after batch 03; local packages as listed 2026-07-11,
consolidation snapshot `gjeldende-lover` dated 2026-07-10):

```bash
uv run lawvm no-verify-scan --limit 200 --as-of 2026-07-10 --json
uv run lawvm no-verify-partition --limit 200
uv run lawvm no-divergence <BASE_ID> --as-of 2026-07-10 --max-divergences 500 --json
```

Divergences were then classified by hand/script into: engine defect, missing
amendment (index/acquisition), compare-lane noise, editorial/oracle issue,
temporal-horizon artifact, sparse-source ceiling. Per
`NORWAY_LAWVM_STATUS.md` §2.2, a divergence never authorizes preferring the
consolidation; every class below is evidence to triage, not a repair license.

## 2. Scoreboard

| as-of / cohort | consistent | divergent | error |
|---|---:|---:|---:|
| 2026-03-29 (scan default, original 20) | 8 | 12 | 0 |
| 2026-07-10 (snapshot-commensurable, original 20) | 11 | 9 | 0 |
| **2026-07-10, after batch 01 (original 20, f4eae341a)** | **12** | **8** | 0 |
| **2026-07-10, after batch 03 (original 20, 2c76cedec)** | **12** | **8** | 0 |
| **2026-07-10, batch 03 newly unlocked 38** | **6** | **32** | 0 |
| **2026-07-10, after batch 03 (all 58)** | **18** | **40** | 0 |

Batch 03 increased coverage rather than changing an existing verdict: all 20
old rows stayed byte-identical, and 38 laws that had previously been excluded
for unresolved commencement entered the scan. Their first durable baseline is:

| newly unlocked law | verdict | divergences |
|---|---|---:|
| `no/lov/2010-06-25-28` | divergent | 29 |
| `no/lov/2013-06-21-102` | divergent | 55 |
| `no/lov/2017-06-16-67` | divergent | 6 |
| `no/lov/2019-06-14-21` | divergent | 28 |
| `no/lov/2001-06-15-65` | divergent | 4 |
| `no/lov/2010-02-19-5` | divergent | 32 |
| `no/lov/2015-05-22-33` | divergent | 3 |
| `no/lov/2017-06-16-51` | divergent | 215 |
| `no/lov/2004-05-28-29` | divergent | 9 |
| `no/lov/2005-06-03-34` | divergent | 3 |
| `no/lov/2016-06-17-29` | divergent | 21 |
| `no/lov/2017-06-16-65` | divergent | 57 |
| `no/lov/2005-05-27-31` | divergent | 10 |
| `no/lov/2018-06-15-38` | divergent | 716 |
| `no/lov/2021-06-18-115` | consistent | 0 |
| `no/lov/2022-03-18-12` | consistent | 0 |
| `no/lov/2024-12-13-76` | divergent | 1 |
| `no/lov/2002-04-26-12` | divergent | 8 |
| `no/lov/2003-06-27-57` | divergent | 2 |
| `no/lov/2007-06-29-89` | divergent | 1 |
| `no/lov/2009-03-06-12` | divergent | 3 |
| `no/lov/2012-01-27-9` | divergent | 6 |
| `no/lov/2012-11-30-70` | divergent | 1 |
| `no/lov/2013-06-07-31` | consistent | 0 |
| `no/lov/2016-06-17-46` | divergent | 2 |
| `no/lov/2017-05-22-28` | divergent | 1 |
| `no/lov/2017-05-22-29` | divergent | 6 |
| `no/lov/2017-05-22-30` | divergent | 6 |
| `no/lov/2020-06-19-95` | divergent | 1 |
| `no/lov/2020-11-27-131` | divergent | 15 |
| `no/lov/2020-12-04-136` | divergent | 3 |
| `no/lov/2020-12-18-153` | consistent | 0 |
| `no/lov/2021-04-16-18` | divergent | 1 |
| `no/lov/2021-06-18-121` | divergent | 2 |
| `no/lov/2022-12-20-118` | divergent | 8 |
| `no/lov/2022-12-20-97` | divergent | 6 |
| `no/lov/2024-06-25-69` | consistent | 0 |
| `no/lov/2024-12-13-77` | consistent | 0 |

Two rows need a temporal-ordering caveat before their divergence shape is used
as replay-fidelity evidence: `no/lov/2010-02-19-5` and
`no/lov/2010-06-25-28` have amendment sanction-date order different from
commencement-date order, while replay currently orders by `source_id`.

The delta between the first two rows is itself finding F-01: three laws
(`no/lov/2020-05-07-38`, `no/lov/2025-06-20-102`, `no/lov/2025-12-22-116`)
read as defective at the default date purely because an amendment took effect
between 2026-03-29 and the snapshot, and `no/lov/2022-03-11-9` showed 9
divergences instead of its real 1.

At the commensurable horizon the original cohort's 9 divergent laws carried
313 provision-level divergences, of which **295 sit in the two known
sparse-source laws** (`no/lov/2006-06-30-50`: 212,
`no/lov/2001-01-05-1`: 83). Outside those, the corpus had **18 divergences
across 7 laws**, classified below. Batch 01 cleared one of them (F-06), leaving
17 across 6 laws; batch 03 left that cohort unchanged and exposed the separate
38-law baseline above.

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

> **Field evidence (2026-07-31, W-7 tranche 1).** The zero-amendment sweep
> (`scripts/probes/no_zero_amendment_divergence.py`) independently corroborates
> the hypothesis. `no/lovtid/2026-06-19-48` declares `no/lov/2025-04-10-9` as a
> target the index never bound; if the act were in force act-wide at
> 2026-06-19, that law's consolidation should differ from its original text.
> It does not — `no/lov/2025-04-10-9` was the **only** one of six
> predicted-divergent zero-amendment laws to come back `consistent` at
> 2026-07-10. Lovdata's own consolidation treats this act's changes as not yet
> commenced, at least for that target, exactly what "premature commencement"
> predicts.

> **Second field evidence (2026-07-31, W-7 tranche 2).** The forskrift lane is
> now ingested (35,955 instruments), and the check this entry asked for has an
> answer: **no commencement instrument cites `no/lov/2026-06-19-48`** anywhere
> in the lane, through the archive's 2026 horizon. 520 other "Kongen
> bestemmer" acts have exactly such an instrument; this act does not. Replay
> applies it at 2026-06-19 with no published commencement decision in
> evidence. Two independent confirmations now support demoting mixed
> "DATE, Kongen bestemmer" fields to `contingent` pending typed evidence —
> W-5 is ready to be decided, and tranche 3's validator would then be the
> mechanism that re-dates such acts when their instrument exists.
>
> **Negative gate witness (2026-07-31, batch 03).** The execution validator
> independently preserved that boundary: `no/lovtid/2026-06-19-48` remains
> `dated` at `2026-06-19`, not `instrument_authorized`, because no instrument
> cites it. Batch 03 therefore supplies no accidental repair for F-03; W-5 must
> still decide the mixed-field classification.

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

`NOAmendmentIndexEntry.base_ids` is derived solely from successfully-extracted
ops (`index.py:268`), so a law the extractor fails to reach is silently absent
from the binding — with no receipt, because a target that was never bound is
never adjudicated as missed.

> **Correction (2026-07-31, batch 02 preflight).** This entry originally said
> "nothing in `src/lawvm/norway/` reads it". **That is false**, and the batch-02
> preflight caught it before any code was written. `grafter.py:1490`, inside
> `_iter_unstructured_no_change_groups`, already xpaths the
> `changesToDocuments` class, reads its `<li>` descendants, normalizes each
> through `normalize_lovdata_refid`, and then sets
> `default_base_id = changed_docs[0] if len(changed_docs) == 1 else None`.
>
> Two consequences, both material:
>
> 1. **The reading primitives already exist.** A `<li>` parser and a working id
>    normalizer are both in the tree. Batch 02 extracts and reuses them instead
>    of adding a second copy, which is what the original contract would have
>    produced.
> 2. **"The declared list never authorizes a binding" is not true of the
>    frontend as a whole.** On the unstructured path, a sole declared ref
>    already determines an op's base id today. The claim is true of the *index*,
>    and only the index. Any spec wording must say so.
>
> The measurement below is unaffected — it was taken from the artifacts, not
> from this claim. What changes is the diagnosis: the field is read in one
> narrow place and never used as a completeness denominator.

> **Second correction (2026-07-31, batch 02 review).** "One narrow place" also
> understated it. Both reviewers and the adjudicator independently measured the
> grafter's `default_base_id` rule by counterfactual — strip every
> `changesToDocuments` carrier from the tree and rebuild the index:
>
> | | |
> |---|---|
> | Index entries | 2,466 |
> | Entries whose `base_ids` change | 397 |
> | **Entries that lose `base_ids` entirely** | **393** |
> | ...whose lost ids came from that act's own declared list | 393 (100%) |
>
> So **16% of the Norway amendment index binds solely through the declared
> list**. `default_base_id` outranks every extracted signal
> (`grafter.py` ~:1557: `lead_base_id = default_base_id or explicit_section_base_id
> or active_base_id or section_base_id`) and becomes the entry's `base_ids`.
> `no/lovtid/2001-01-19-3` has exactly one `base_id`, taken verbatim from its
> declared list, and ceases to exist without it; `no/lovtid/2001-06-15-61` binds
> the *unnumbered* declared id `no/lov/1961-02-03`.
>
> The declared list is therefore **not evidence-only in this frontend** — it is
> load-bearing authority for a sixth of the index, and has been all along,
> undocumented. Any future statement about its authority must say so. Batch 02
> shipped two comments denying it; the harness caught both.

Measured over all 3,089 amendment artifacts. **2,942 carry a
`changesToDocuments` block and 147 do not**; every block present is non-empty.
Of those, **2,941 contain at least one `lov`-form target** — the odd one out is
`no/lovtid/2021-06-18-115`, whose declared list holds only
`forskrift/1952-04-21-4287`. The probe's `lov`-only regex counts 2,941/148; by
block presence it is 2,942/147. Batch 02 must pick one definition explicitly.

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
3. **Declared targets that normalize to non-resolving ids** — 109 items of the
   form `lov/<date>` with no trailing number, e.g. `lov/1967-02-10`
   (forvaltningsloven). `normalize_lovdata_refid` turns these into well-formed
   `no/lov/1967-02-10` ids, but **no corpus law id has that shape**, so they can
   never bind. They need their own bucket; counted as ordinary unbound targets
   they inflate the headline gap by 109 and stop it reconciling with the probe.
   (An earlier version of this entry called them "unexpressible" — the id
   grammar expresses them fine; nothing resolves them.)

Recommended decomposition, smallest-first, each independently field-measurable:
**(a)** parse and store the declared list as a *typed observed-vs-declared
adjudication* — no behavior change, but it converts an invisible 47% gap into a
receipt; **(b)** measure how many missed bindings family 2 alone recovers;
**(c)** treat family 1's terminology-substitution lowering as its own batch, and
only after W-7 since 322 of its 402 bindings are `contingent`.

Step (a) is the one to do first: it is a small, bounded, testable change that
makes every later step measurable, and it is the only one whose scope is already
known.

#### Step (b) measured 2026-07-31: the dominant cause is identified, and it still cannot pay yet

With step (a) landed, every unbound binding carries a receipt, so the 4,088 can
be split by cause — joining each act's unbound targets to the parse diagnostics
the engine already emits for that act
(`scripts/probes/no_unbound_binding_causes.py`).

| field-relevant | total | acts | cause |
|---:|---:|---:|---|
| **504** | **2,086** | 760 | `no_parse_unstructured_lead_unmatched` |
| 78 | 581 | 36 | bulk-rename list grammar (family 1) |
| 42 | 835 | 262 | `no_parse_unstructured_lead_base_unresolved` |
| 32 | 394 | 118 | no parse diagnostic on the act at all |
| 19 | 36 | 12 | `no_parse_cross_base_structured_target_skipped` |
| 0 | 92 | 67 | declared id resolves to no corpus law (family 3) |

So **one diagnostic accounts for half the gap and three quarters of the
field-relevant part** — and it is the same `no_parse_unstructured_lead_unmatched`
family as F-02/W-2. The W-2 spike measured only its *punktum-repeal* subset (284
leads) and found zero payoff; the family as a whole is far larger.

**But the near-term payoff is still nil, and this time it is measured exactly.**
"Field-relevant" above means *the amending act is `dated` and the target law has
consolidated text* — true of 645 laws. The verify scan covers **20**. Of all
4,088 unbound bindings, the number that target a law in the scan, on a `dated`
act, is:

> **2.**

One is `no/lov/2004-05-14-25`, which is already `consistent` with 0 divergences —
binding it could only break something. The other is `no/lov/2001-01-05-1`, one of
the two known sparse-source acquisition ceilings (F-09). Neither is worth a
batch.

**Verdict: do not batch step (b) now.** The cause is now known and sized, which
is what step (b) was for. The 504 field-relevant bindings are real and will pay —
but only once their target laws become replayable, which is W-7.

*One correction this probe forced.* The first run attributed **83%** of the
field-relevant gap to the bulk-rename family, using a lead pattern that dropped
the substitution verb. That pattern matches `Endringer i følgende lover:` — a
table-of-contents heading carried by nearly every omnibus act — inflating family
1 from 36 acts to 579 and inverting the ranking. Caught by sampling 8 flagged
acts and reading the matched text: only 3 were real. The probe now requires the
verb and colon, and says so in a comment.

#### Re-priced 2026-07-31 (W-7 tranche 1): the payoff is 8, not 2, and 5 of it is field-confirmed

Step (b)'s decisive "2" was measured against the 20-law scan. W-7 tranche 1
widened the comparable set to every executable law replayable today — the 20
amended fully-replayable laws plus the **100 zero-amendment executable laws**,
for which replay is trivially the original act and verification is a pure
consolidation-equality check. Against that 120-law set
(`scripts/probes/no_zero_amendment_divergence.py`):

- **8** unbound bindings from `dated` acts touch the set (up from 2). The six
  new targets are all zero-amendment laws — laws our index believes untouched.
- The sweep verified all 100 zero-amendment laws at 2026-07-10:
  **57 consistent / 43 divergent / 0 error**. Every divergence is Lovdata's
  consolidation differing from original text on a law with no bound amendment.
- **5 of the 6 predicted targets are confirmed divergent** — the unbound
  binding join predicted, from receipts alone, which laws would diverge, and
  the field agreed. The sixth (`no/lov/2025-04-10-9`, declared by F-03's
  mixed-commencement act `no/lovtid/2026-06-19-48`) came back consistent,
  which is evidence for F-03, not against the join.

| act (dated) | unbound target | sweep verdict |
|---|---|---|
| `no/lovtid/2012-12-14-82` | `no/lov/2012-01-27-10` | divergent (1) |
| `no/lovtid/2015-06-19-65` | `no/lov/2001-06-15-73` | divergent (1) |
| `no/lovtid/2015-06-19-65` | `no/lov/2009-05-15-28` | divergent (2) |
| `no/lovtid/2015-06-19-65` | `no/lov/2013-06-21-75` | divergent (3) |
| `no/lovtid/2026-06-19-59` | `no/lov/2025-06-20-99` | divergent (1) |
| `no/lovtid/2026-06-19-48` | `no/lov/2025-04-10-9` | consistent (F-03) |

**This softens the step-(b) verdict.** Binding recovery on `dated` acts now has
a nonzero, named, field-visible payoff without W-7: recovering these bindings
would move up to 5 currently-divergent laws toward consistency (and 11 more
unbound bindings from `contingent` acts touch the set — recovering those would
correctly reclassify their targets from "divergent" to commencement-blocked
rather than leaving a false claim of divergence). The remaining ~38 divergent
zero-amendment laws are unexplained by declared-target receipts and need
triage: candidates are bindings missed by *both* extraction and declaration,
editorial changes (F-07 territory), or original-act extraction noise.

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

*Correction (same day): the role taxonomy does not govern this lane.* The first
version of this entry justified the decision partly via
`observation_registry.validate_finding_projection`, which does reject
`role="observation"` with `blocking=True` and `role="violation"` with
`blocking=False`. That rule is real but applies to **core `Finding` objects**,
and **Norway does not use that registry** — `FINDING_REGISTRY` contains zero
`no_*` codes and nothing under `src/lawvm/norway/` imports
`observation_registry`. Norway's adjudication lane is
`core.diagnostic_records.diagnostic_detail`, whose signature has **no `role`
and no `default_enforcement`**; its parameters are `rule_id`, `phase`,
`blocking`, `family` (a free-form string — Norway already uses
`mutation_boundary`, `orchestration_failure`, `target_resolution_recovery`,
which are not members of the core `FindingFamily` literal),
`strict_disposition`, and `quirks_disposition`. Governance for a NO rule id is
the `_NO_RULE_SPECS` catalog plus the AST-scan guard, not the finding registry.

The decision is unchanged, because it never rested on that argument: it rests on
the Norway-native precedent below and on the measurement. But a contract written
against `role=`/`default_enforcement=` would not compile, so the correction
matters.

*The concern that motivated the question was factually wrong.* I worried a
blocking finding would "fail replay on 1,245 acts overnight". Measured: **13,858
of 13,859** index-build diagnostics are *already* `blocking=True`, and
`no/lov/2020-05-07-38` carries **122 blocking replay adjudications while scoring
`consistent`** in the scan. `blocking` classifies severity for strict mode; it is
not what gates the scan. The precedent is explicit — `no_replay_no_matching_change_group`
is emitted `blocking=True` and the replay loop `continue`s (`replay.py:401-414`).

**Decision**, in the vocabulary Norway actually emits:

```python
diagnostic_detail(
    rule_id="no_amendment_index_declared_target_unbound",
    family="source_pathology",   # act-level coverage gap against declared metadata
    phase="acquisition",
    blocking=True,
    strict_disposition="block",
    quirks_disposition=QuirksDisposition.RECORD,
    ...
)
```

plus a `_NO_RULE_SPECS` entry for the new rule id. No scoreboard movement, and
strict mode gains a real gate.

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
4. ~~**W-8 (F-10):** parse the `changesToDocuments` declared-target list and
   emit a typed declared-vs-bound adjudication.~~ **Done** — batch 02,
   f15b11aee. 1,245 blocking adjudications over 4,088 unbound bindings,
   reconciling exactly with the probe. Scoreboard unmoved (12/8/0, all 20
   per-law rows byte-identical), which was the pass condition. The batch also
   produced the 393-entry measurement now recorded under F-10: the declared
   list is load-bearing authority for 16% of the index, not evidence-only.
   Step (b) then measured the causes (see F-10): one diagnostic,
   `no_parse_unstructured_lead_unmatched`, is 2,086 of the 4,088 bindings and
   504 of the 676 field-relevant ones — but only **2** unbound bindings in the
   whole corpus touch a law the 20-law scan covers, so step (b) is **not** a
   batch now. F-10 (b)/(c) join W-2, F-03 and F-04 behind W-7.
5. ~~**W-7:** the three-tranche commencement-evidence programme
   (`NORWAY_LAWVM_STATUS.md` §7 item 4).~~ **Done 2026-07-31.**
   - ~~**Tranche 1** — measure the unlock landscape and widen the comparable
     corpus without engine changes.~~ **Done.** The 20-law scan was already at
     its ceiling: of 237 amended executable laws, **217 (91%) were
     commencement-blocked** (1,436 of 2,466 amendment acts unresolved, 1,430
     of them `contingent`). The unlock curve was steep at the head — 56 laws
     blocked by a single act, 97 by ≤2, 120 by ≤3
     (`scripts/probes/no_w7_unlock_landscape.py`). The corpus grew sideways:
     the **100 zero-amendment executable laws** are verifiable as pure
     consolidation-equality checks — 57 consistent / 43 divergent, with the
     F-10 join predicting 5 of the divergences exactly
     (`scripts/probes/no_zero_amendment_divergence.py`; see F-10 re-pricing).
   - ~~**Tranche 2** — re-ingest so the commencement-instrument lane gets its
     instruments.~~ **Done.** `no-ingest --skip-existing` stored exactly
     **35,955** `no://forskrift/` locators and nothing else; the 6,944
     pre-existing (locator, digest) pairs hash identically before and after
     (`abda820f…`), the 20-law scan stayed byte-identical at 12/8/0, and the
     norway shard passed 475/475 after the mutation. Coverage partition:
     608 whole-act candidates / 33,590 benign / 1,757 blocked-unresolved.
     Sizing found 520 unresolved acts with a single-date whole-act instrument,
     zero conflicting dates, and 38 blocked laws that would flip.
   - ~~**Tranche 3 (batch 03)** — authorize parsed whole-act instruments to
     supply execution dates through a typed status and receipts.~~ **Done in
     `2c76cedec`.** Exactly **520 acts** became `instrument_authorized`; 523
     instruments support them because same-date corroboration deduplicates at
     the act; zero date conflicts surfaced. The parse partition is unchanged at
     35,955 = 608 + 33,590 + 1,757, and the gate leaves enabling-statute,
     partial-scope, multi-date, and already-resolved cases unauthorized. The
     amended-law scan grew **20 → 58**: the original 20 stayed byte-identical at
     12/8/0, and the new 38 established the 6/32/0 baseline above. The remaining
     landscape is 916 unresolved acts, 179 commencement-blocked amended laws,
     and zero acts still authorizable by the implemented gate. End-to-end,
     `no/lovtid/2022-04-01-17` is skipped on 2022-03-31 and applies two ops to
     `no/lov/2010-06-25-28` on 2022-04-01. Positive anchor
     `no/lovtid/2012-01-27-9` is authorized at 2012-03-01 by
     `no/forskrift/2012-01-27-71`; F-03's negative anchor
     `no/lovtid/2026-06-19-48` remains `dated`.
6. ~~**W-9 (commencement report residue):** align
   `src/lawvm/tools/no_commencement_candidates.py` with the typed index
   authorization.~~ **Done 2026-08-01** (`35111fd82`; the PROJ-02 gate
   correction is `f434589c0`) — the report row and the plain-text
   renderer both mirror the index's `replay_authorized` verdict; no second
   authorization model was created (the row reads the flag off the index's own
   candidate). 523 authorized instruments now report `True` across 524 report
   rows (`no/forskrift/2012-04-27-364` is the sole instrument binding two
   indexed acts). Fixing W-9 also surfaced a latent batch-03 defect: the
   authorization gate's `replace(candidate, replay_authorized=True)` violated
   the PROJ-02 author-set-replay-authority ratchet, unseen because the ratchet
   test lives in shard `core_discipline_gates`, outside batch 03's affected
   selection (norway, tools_cli_debug). Fixed by deriving the flag from the
   gate verdict (`candidate.source_id in authorized_instrument_ids`) inside the
   `NOCommencementExecutionAuthorization` construction; the 520/523/0 counts
   are byte-identical.
7. **W-10 (temporal ordering):** replay orders amendments by `source_id`, not
   effective date. Investigate and pin the intended ordering before treating
   the divergence shapes of `no/lov/2010-02-19-5` and
   `no/lov/2010-06-25-28` as pure replay-fidelity evidence.
8. ~~**W-11 (FW-07 classifier-wrap ratchet red at HEAD, pre-existing):**
   `tests/test_classifier_wrap_ratchet.py` fails on the clean tree —
   `commencement_instruments.py` carries 3 raw `re.compile` (baseline 0),
   `sources.py` 8 (baseline 5), `verify.py` 13 (baseline 12).~~
   **Fixed 2026-08-01** (`0c45508ba`). The investigation found a *second*
   standing red behind the first, and the two were fixed opposite ways.

   *FW-07 (shard `core_discipline_gates`)* — all 7 raw `re.compile` sites were
   adjudicated bounded lexers/locators over ids, filenames, locators, metadata
   fields, or whitespace, not classifiers over adversarial prose, and all pass
   `lawvm_regex_risks` clean. Disposition: the ratchet's own documented
   conscious baseline bump (total **1273 → 1280**), not wrap adoption. The bump
   is a *ratification of a correct judgment*, not an exemption: the module's
   three genuine Norwegian-prose classifiers (`_COMMENCEMENT_TITLE_RE`,
   `_LAW_COMMENCEMENT_RE`, `_WHOLE_ACT_RE`) already carry
   `compile_classifier_regex`, so the author drew the classifier/lexer line
   correctly and only the over-including heuristic disagreed. All seven
   patterns were additionally proven **behaviorally inert under the wrap** on
   the full 35,955-artifact corpus (0 mismatches, instrument partition
   byte-identical) — the evidence that made the bump safe rather than merely
   convenient. Wrap adoption was rejected on top of that: the `verify.py` site
   fails `ty` type-checking under the wrap.

   *Regex ratchet (shard `core_ir_contracts`)* — `tests/test_regex_ratchet.py`
   was red on **6 un-waived call sites** (total 2363 vs baseline 2357):
   `commencement_instruments.py` :487 (`_LAW_REF_RE.finditer`), :518 (both
   classifier `.search` calls on one line), :525 (`_ISO_DATE_RE.findall`), and
   `sources.py` :409 (`_NO_FORSKRIFT_FILENAME_RE.search`), :518
   (`_NO_UNNUMBERED_LAW_ID_RE.match`). Disposition: **per-site
   `# lawvm-regex:` waivers, not a baseline bump** — `owning_parser` for the
   instrument-family and source-plane-locator owners, `prefilter` for the two
   already-wrapped classifier guards. The waivers return the un-waived count to
   exactly the committed 2357 with `regex_ratchet_baseline.json` untouched.

   *Attribution corrected.* The red dates to **2026-07-11** (`e2d17d171`, W-7
   tranche 2), which introduced 5 of the 7 sites: all three in
   `commencement_instruments.py` plus `sources.py`'s
   `_NO_FORSKRIFT_FILENAME_RE` and `_NO_FORSKRIFT_LOCATOR_RE`. Batch 01
   (`f4eae341a`) added `verify.py`'s `_NO_VERIFY_PAREN_CLOSE_RE`; batch 02
   (`f15b11aee`) added `_NO_UNNUMBERED_LAW_ID_RE`; **batch 03 added none.** The
   earlier "batches 01 and 03" reading above was wrong — the instrument lane,
   not the batch that consumed it, is where these landed.
9. **W-4 (F-01):** make `no-verify-scan`'s default comparison date
   snapshot-commensurable.
10. **W-5 (F-03):** decide whether mixed "DATE, Kongen bestemmer" in-force
   fields must demote to `contingent` (blocking) pending typed evidence. The
   forskrift lane and batch 03 now prove that no instrument cites
   `no/lov/2026-06-19-48`; its zero-amendment target is consistent, and the act
   remained merely `dated` through the authorization gate.
11. **W-6 (F-07, F-08):** pin the editorial correction; triage the
   CONSOLIDATED_MISSING clusters. Both the 43-law divergent zero-amendment set
   from tranche 1 (~38 unexplained by declared-target receipts) and batch 03's
   32 newly visible divergences feed this family-first triage.

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

- **2026-08-01 (W-11)** — **Two standing hygiene ratchets went green, fixed in
  opposite directions, after three weeks red in shards no Norway batch ever
  ran.** The FW-07 classifier-wrap ratchet
  (`tests/test_classifier_wrap_ratchet.py`, shard `core_discipline_gates`) was
  red on 7 raw `re.compile` sites; the regex ratchet
  (`tests/test_regex_ratchet.py`, shard `core_ir_contracts`) was red on 6
  un-waived call sites. Neither was caused by current work, and the two
  disposals differ because the two gates ask different questions.

  FW-07 asks *is this a classifier over adversarial prose?* — and for all seven
  the honest answer is no: they are bounded lexers and locators over law ids,
  archive filenames, `no://` locators, `dateInForce` metadata, and whitespace,
  all clean under `lawvm_regex_risks`. So the disposition is the ratchet's
  documented conscious baseline bump, **1273 → 1280**
  (`commencement_instruments.py` 0 → 3, `sources.py` 5 → 8, `verify.py`
  12 → 13). The bump ratifies a judgment the author already made correctly:
  the same module's three real Norwegian-prose classifiers
  (`_COMMENCEMENT_TITLE_RE`, `_LAW_COMMENCEMENT_RE`, `_WHOLE_ACT_RE`) do carry
  `compile_classifier_regex`. FW-07's own docstring concedes it over-includes —
  it cannot statically separate lexer from classifier — so a bump on a
  correctly-drawn line is the sanctioned outcome, not a dodge. Safety was not
  assumed: all seven patterns were proven behaviorally inert under the wrap
  across the full 35,955-artifact corpus (0 mismatches, instrument partition
  byte-identical). Wrap adoption was additionally blocked at the `verify.py`
  site, which fails `ty` under the wrap.

  The regex ratchet asks a different question — *does a semantic-plane regex
  use-site carry an accountable owner?* — and that one is answered per site,
  not per baseline. Five `# lawvm-regex:` waivers (one covers the two
  classifier `.search` calls sharing line 518) name `owning_parser` for the
  instrument parser and the source-plane locator owners, and `prefilter` for
  the two already-wrapped guards. The un-waived count returns to exactly the
  committed 2357 and `regex_ratchet_baseline.json` is untouched — the right
  shape, since waiving a site is an accountability claim while bumping the
  baseline would have been an amnesty.

  Attribution in the W-11 entry was wrong and is corrected: the red dates to
  **2026-07-11** (`e2d17d171`, W-7 tranche 2 — 5 of 7 sites), not to batches 01
  and 03. Batch 01 (`f4eae341a`) and batch 02 (`f15b11aee`) contributed one
  site each; batch 03 contributed none.

  The blind spot is the finding worth keeping. W-9 already recorded that a
  ratchet scanning all of `src/lawvm` but testing in one shard is invisible to
  Norway-scoped affected ladders (norway, tools_cli_debug). This is the same
  defect twice more, across **two** shards — `core_discipline_gates` *and*
  `core_ir_contracts` — undetected for three weeks. Global hygiene ratchets are
  not affected-ladder material; they need to run on every batch regardless of
  touched-file scope, or the ladder needs to map "any file under `src/lawvm`"
  to the shards that gate it. Documentation defect noted in passing: FW-07's
  failure message directs the author to `notes/LAWVM_AUDIT_INVARIANT_REGISTRY.md`
  row FW-07, and **that file does not exist in the repo** — 16 test modules,
  two `src/lawvm` modules, a script, and three notes cite the registry, so the
  pointer every ratchet hands its reader is dead.

- **2026-08-01 (W-9)** — **The commencement-candidate report stopped lying
  about authorization, and the fix caught a latent ratchet violation.** Two
  hardcodes in `no_commencement_candidates.py` — the row dict's
  `"replay_authorized": False` and the renderer's literal
  `replay_authorized=no` — now mirror the index's verdict instead. 523
  authorized instruments report `True` across 524 rows; the 1,842
  non-authorized instrument rows stay `False`; the anchor
  `no/forskrift/2012-01-27-71` reads `yes` and F-03's
  `no/lovtid/2026-06-19-48` still shows zero instruments. The residue test
  batch 03 wrote (blanket `all(... is False)`) became a per-instrument mirror
  of the index assertion beside it, plus a fake-index passthrough test and a
  renderer pin. The discovery: running the PROJ-02
  author-set-replay-authority ratchet as part of verification found it RED at
  HEAD — batch 03's own `replace(candidate, replay_authorized=True)` was an
  author-set truthy literal outside the `ExecutionAuthorization` carrier, and
  the ratchet test (shard `core_discipline_gates`) was never selected by the
  batch's affected ladder (norway, tools_cli_debug). A ratchet that scans all
  of `src/lawvm` but tests in one shard is a standing blind spot for
  Norway-scoped batches; worth remembering when composing affected ladders.
  Fixed by deriving the flag from the gate verdict inside the carrier
  construction — proven identity-preserving by the unchanged 2,365/523/520
  counts and the full norway shard. The same blind spot hides a second
  standing red: the FW-07 classifier-wrap ratchet fails at HEAD on regexes
  batches 01 and 03 added (stash-proven pre-existing; recorded as W-11, not
  fixed here because wrap-vs-baseline is a per-regex decision).
- **2026-07-31 (batch 03, applied)** — **Whole-act commencement evidence now
  authorizes execution** (`2c76cedec`). The typed gate runs over already-parsed
  instruments inside index construction: candidate parse + whole-act scope +
  exactly one date + `no/lov`→`no/lovtid` alias to an unresolved amendment act,
  with conflict refusal, enabling-statute filtering, typed receipts, and manual
  override precedence. Exactly **520 acts** moved to `instrument_authorized`
  (523 supporting instruments, zero conflicts), making 38 more amended laws
  replayable. The scan grew 20 → 58 at 2026-07-10: the original 20 rows remained
  byte-identical at 12/8/0; the new 38 established 6/32/0; total 18/40/0. The
  post-application landscape is 916 unresolved acts, 179 blocked amended laws,
  and zero remaining acts authorizable by this gate. The 35,955-instrument parse
  partition stayed 608 + 33,590 + 1,757.

  Recovery mattered. The original bounded fixer corrected a dead absent-corpus
  guard and a stale module docstring, but the final architecture reviewer then
  found the existing `no_replay_unknown_effective_skipped` catalog prose still
  described the old four-status world. Adjudication correctly blocked instead
  of running an unreviewed second fixer. Narrow recovery changed only that
  catalog value relative to the recovered patch; the replacement artifact is
  SHA-256 `3920b47c81a5be5c86edf18414bb8ac80184fba1c4fc9c83c366a9f15c535ce1`
  (45,344 bytes). Independent final correctness and architecture reviewers both
  approved it with no findings.

  Targeted stages passed: Ruff, ty, focused commencement/index tests (38 passed,
  1 skipped), full Norway shard (486 passed, 1 skipped), and catalog guard (6
  passed). At application, the affected ladder passed compile, Ruff, ty, shard
  ownership, boundary (47), and Norway (487); `tools_cli_debug` reported only
  the known three Finland corpus-absence witnesses (154 passed). Reverse the
  patch and rerun that shard produced the identical three failures, then the
  exact reviewed patch was reapplied. Field witnesses pinned before/on-date
  replay, the 2012 positive authorization anchor, and F-03's 2026 negative
  anchor. Outside-contract residue: the candidate report hardcodes
  `replay_authorized=False`, and replay's source-id ordering can invert effective
  dates for two newly unlocked laws; see W-9/W-10.
- **2026-07-31 (W-7 tranche 2)** — **The instrument lane fed, tranche 3 sized
  at 38 laws, and F-03 confirmed a second way.** `no-ingest --skip-existing`
  stored exactly 35,955 `no://forskrift/` locators and nothing else — additive
  by construction and by proof (the 6,944 pre-existing locator/digest pairs
  hash identically, the 20-law scan is byte-identical at 12/8/0, norway shard
  475/475 after the mutation). The parser partitions them 608 whole-act
  candidates / 33,590 benign / 1,757 blocked-unresolved. The sizing the
  tranche existed for: **520 of 1,436 unresolved acts carry a single-date
  whole-act instrument, zero conflicting dates, and authorizing them flips 38
  blocked laws — scan corpus 20 → 58.** A 10-pair random sample is clean;
  every instrument is the awaited royal decision for its "Kongen bestemmer"
  act, title-matched verbatim. One probe correction worth keeping: the first
  join measured **0** because `basedOn` cites the amending act's law id
  (`no/lov/D-N`) while the index keys `no/lovtid/D-N` — and that same alias is
  what filters out the many instruments that commence a forskrift while citing
  its enabling statutes. Bonus: the lane answers W-5's question — **no
  instrument cites `no/lov/2026-06-19-48`**, so F-03's act is applied by
  replay with no published commencement decision in evidence; the
  premature-commencement hypothesis now has two independent field
  confirmations. Next: tranche 3, the execution-authorization validator, as
  batch 03.
- **2026-07-31 (W-7 tranche 1)** — **The commencement wall measured, and a
  hundred-law corpus found behind it.** Three results. *First*, the 20-law scan
  was already at its ceiling: `build_no_verify_scan` admits every amended
  executable fully-replayable law and there are exactly 20 — 217 of 237 (91%)
  are commencement-blocked, so no scan parameter grows the corpus; only W-7
  does. The unlock curve is steep (56 laws blocked by one act, 97 by ≤2).
  *Second*, the instrument lane is starving, not broken: the farchive has zero
  `no://forskrift/` locators because it was ingested before the lane existed,
  while the public tarballs hold ~35,955 `sf-*.xml` instruments — tranche 2 is
  a re-ingest, no engine change. *Third*, the corpus grew anyway, sideways: the
  100 zero-amendment executable laws are verifiable today as pure
  consolidation-equality checks, and the sweep came back **57 consistent / 43
  divergent** — each divergence a law Lovdata amended that our index believes
  untouched. The F-10 receipts predicted 6 specific divergences; **5
  confirmed**, and the sixth (`no/lov/2025-04-10-9`) is the F-03
  mixed-commencement act showing Lovdata itself hasn't applied it — the
  prediction failing in the exact direction F-03's hypothesis requires. F-10's
  step-(b) verdict re-priced from "payoff is 2, don't batch" to "payoff is 8,
  5 field-confirmed"; the ~38 unexplained divergent laws feed W-6 triage.
  Probes: `no_w7_unlock_landscape.py`, `no_zero_amendment_divergence.py`.
  Scan re-run at 2026-07-10 unchanged: 12/8/0.
- **2026-07-31 (F-10 step b)** — **Cause of the 4,088-binding gap measured; still
  not batchable.** Step (a)'s receipts made the split possible: joining each
  act's unbound targets to the parse diagnostics it already emits shows
  `no_parse_unstructured_lead_unmatched` is **2,086 of 4,088** bindings and
  **504 of the 676** field-relevant ones — one diagnostic, half the gap. It is
  the same family as F-02/W-2, whose spike had measured only the punktum-repeal
  subset. But the decisive number is smaller and blunter: of all 4,088 unbound
  bindings, exactly **2** target a law the 20-law scan covers, one already
  `consistent` and one a known sparse-source ceiling. Fifth item in a row to
  terminate at commencement, and the first where the terminus is measured to a
  single digit rather than inferred. Also a probe correction worth keeping: the
  first run blamed the bulk-rename family for 83% of the field-relevant gap
  because its lead pattern, without the substitution verb, matches
  `Endringer i følgende lover:` — a table-of-contents heading on nearly every
  omnibus act. Sampling 8 flagged acts showed only 3 were real; the family is 36
  acts, not 579, and the ranking inverts once fixed.
- **2026-07-31 (batch 02, applied)** — **F-10 step (a) landed** (f15b11aee).
  1,245 blocking adjudications over 4,088 unbound bindings, reconciling exactly
  with the probe; `no/lovtid/2022-12-20-115` declares 14, binds 6, names 8. The
  scoreboard stayed at 12/8/0 with all 20 per-law rows byte-identical — proved
  by stashing the patch and re-running, since "nothing moved" was the pass
  condition and an *improvement* would have meant the declared list had leaked
  into binding authority. The check is non-vacuous: 1,696 fully-covered entries
  emit nothing. `tools_cli_debug` red, proved pre-existing by the same
  stash-and-compare (byte-identical 3-row finlex corpus-absence set).

  **The workflow aborted at Adjudicate and that was correct.** Two prose defects
  survived the bounded fixer cycle: the implementer twice asserted the declared
  list "never contributes a binding" — the exact claim shape the contract's
  requirement 7 forbade. Both reviewers *and* the adjudicator independently
  disproved it by counterfactual and produced the 393-entry measurement now in
  F-10. Fixed by hand at apply time, since the required change was two
  sentences with the adjudicator supplying the wording. Worth keeping: the
  contract explicitly warned about this claim and an agent made it anyway,
  twice — a named prohibition in the contract is necessary but not sufficient,
  and the adversarial review is what actually caught it.
- **2026-07-31 (batch 02, run 1)** — **Aborted at Preflight, correctly**, before
  any agent wrote code. Two of the contract's 16 asserted facts were false, and
  the expensive one was mine: F-10 claimed nothing under `src/lawvm/norway/`
  reads `changesToDocuments`, but `grafter.py:1490` has read it all along and
  uses a sole declared ref as `default_base_id`. Had the batch run, it would
  have built a second `<li>` parser and a second id normalizer beside working
  ones, and shipped a catalog entry asserting something false about the
  frontend. The second failure was an off-by-one with a real cause: 2,942 acts
  carry a declared block but only 2,941 declare a `lov`-form target, because
  `no/lovtid/2021-06-18-115` declares only a forskrift. Contract rewritten to
  extract-and-reuse rather than rebuild, `grafter.py` added to scope, the
  109 `lov/<date>` items reclassified from "unexpressible" to "normalize to a
  non-resolving id", and the block-presence definition forced to be explicit.
  Ledger corrected in place. Cost: one preflight, zero review cycles — the
  cheapest possible place to find this.
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
