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
| **2026-07-10, after batch 04 (all 58, byte-identical rows)** | **18** | **40** | 0 |
| **2026-07-10, after W-15 (56 candidates; see caveat)** | **21** | **35** | 0 |
| **2026-07-10, after W-19/W-20 (57 candidates; see note)** | **21** | **36** | 0 |
| **2026-07-10, after W-18 (57 candidates)** | **22** | **35** | 0 |
| **2026-07-10, after W-30 (56 candidates; see note)** | **22** | **34** | 0 |
| **2026-07-10, after W-34 (56 candidates; see note)** | **21** | **35** | 0 |
| **2026-07-10, after W-35 (56 candidates)** | **22** | **34** | 0 |

W-15 commensurability caveat: the candidate set moved 58 → 56, so the 21/35
row is not row-for-row comparable with the 18/40 row above. On the 54 laws
present in both scans, divergences went 1,515 → 1,504 and 48 rows are
byte-identical; two laws became consistent (`no/lov/2005-06-03-34`,
`no/lov/2020-06-19-95`) and the witness improved (215 → 210). Four
previously-divergent laws (58 divergences between them) left the candidate
set because they gained a newly-bound, correctly-cited amending act with
contingent commencement — unresolved, not repaired — and two laws entered
(`2012-01-27-10` consistent, `2021-06-11-79` at 4).

W-19/W-20 note: the candidate set moved 56 → 57 — `no/lov/2014-08-15-59`
entered divergent at 5 via its recovered sole binding (W-20 fallback, from
`no/lovtid/2019-05-24-18`). 55 of the 56 shared rows are byte-identical;
the 56th (`no/lov/2010-06-25-28`) gained one amendment/op with its
divergence count unchanged. Corpus divergence total 1,508 → 1,513, all
+5 from the entering law.

W-17 note (verdicts unmoved, so no new scoreboard row): the 1,513
divergences now read as `total=1513 (ceiling=1129, unexplained=384)` —
the annexed-instrument ceiling typed per-row with receipts, conservation
exact. Ranked by UNEXPLAINED divergences the corpus's top laws are
`2001-01-05-1` (83, F-09 sparse), `2017-06-16-65` (57) and
`2013-06-21-102` (55); the three annex laws report 2, 6 and 1
unexplained rows respectively.

W-18 note: `no/lov/2020-12-18-156` went divergent (1) → consistent (0)
via its lowered erratum — the F-07 witness. 56 of 57 rows byte-identical;
totals now `total=1512 (ceiling=1129, unexplained=383)`.

W-30 note: candidates 57 → 56 — `no/lov/2006-06-30-50` decertified by
its newly-bound contingent amender `2007-06-29-81` (took 212
divergences off-scan: 211 annex ceiling incl. all 107 counterpart rows,
1 unexplained; returns when the commencement resolves). Two repairs:
`2017-06-16-65` 57 → 13 and `2017-06-16-67` 6 → 2 (instrument-
authorized amenders). Totals `total=1252 (ceiling=918,
unexplained=334)`; 53 of 56 shared rows byte-identical; the
zero-amendment surface (97 laws, 57/40/0) fully byte-identical. The
corpus-wide annex family measured at W-17 (1,129) is unchanged — only
the candidate set shrank.

W-34 note (candidates stay 56, membership swaps 1): `2013-06-21-102`
(55 div) decertified via a newly-bound `Kongen bestemmer` act;
`2013-06-21-75` enters at 1; `2012-01-27-9` repairs 6 → 5; and
`2005-06-03-34` flips consistent → divergent at 3 — honest exposure of
the `futureLegalArticle`-internal trapped-lead seam (W-35), whose fix
returns it to consistent. Totals `total=1196 (ceiling=918,
unexplained=278)`. (W-32, landed the same day, had already moved
`2017-06-16-65` 13 → 9 within the 22/34 row.)

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

~~Two rows need a temporal-ordering caveat before their divergence shape is
used as replay-fidelity evidence: `no/lov/2010-02-19-5` and
`no/lov/2010-06-25-28` have amendment sanction-date order different from
commencement-date order, while replay currently orders by `source_id`.~~
Caveat lifted 2026-08-02 — W-10's investigation proved apply order is decided
by the shared ordering kernel with effective date primary, and both laws'
replayed text is byte-identical under either collection order. Their rows are
trustworthy replay-fidelity evidence.

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

### F-01 — Scan default `as_of` is not snapshot-commensurable — fixed for `no-verify-scan` (W-4); sibling commands remain (W-14)

`no-verify-scan` defaulted to an `--as-of` (2026-03-29 at the time of the
scan) that predates the consolidation snapshot it compares against, exactly
the incommensurability `NORWAY_LAWVM_STATUS.md` §5 warns about. Effect
measured above. The skip lane works correctly
(`no_replay_future_effective_skipped` receipts were emitted); only the
comparison framing misleads.

> **Fixed for the scan (2026-08-02, W-4).** The default is now DERIVED from
> the corpus: `no_consolidation_snapshot_date` in `sources.py` takes the
> latest `last_confirmed_at` over the `no://lov/%/current.xml` locator
> family — the consolidated artifacts replay is actually compared against —
> and it reproduces exactly the documented 2026-07-10 horizon (763 spans,
> all observed 2026-07-10T21:46Z; the archive's later 2026-07-31 forskrift
> observations cannot move it because they are outside the family).
> (Originally shipped reading `observed_from`; the same-day code review
> caught that a change-free re-crawl extends spans without touching
> `observed_from`, which would have frozen the horizon at the last content
> change — re-opening F-01. Corrected to `last_confirmed_at` before the
> defect could ever fire; the two coincide on today's corpus.) An explicit
> `--as-of` passes through verbatim. Fallback
> `NO_FALLBACK_CONSOLIDATION_SNAPSHOT_DATE = "2026-07-10"` covers only
> legacy tar-directory corpora, which record no observation instant; an
> farchive with no consolidated artifacts now raises the named
> `NOConsolidationSnapshotError` instead of borrowing the constant, and a
> corpus-gated test asserts the derivation reproduces the constant so it
> rots loudly on a re-capture. Seven sibling CLI commands still carry the
> stale 2026-03-29 default — that residue is W-14.

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

### F-03 — Mixed `dateInForce` ("DATE, Kongen bestemmer") applied at the date — open (engine/temporal, re-routed to the override / provision-level lane)

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

> **W-5 decided (2026-08-02, batch 04): no demotion; F-03 re-routes.** The
> corpus answered the class-wide question against the hypothesis: a blanket
> demotion of the mixed acts to `contingent` would cost 8 of the 58 scan laws
> and make 7 of those 8 diverge MORE, because Lovdata's own consolidation
> shows most mixed acts ARE in force at their leading date — the mixed field
> marks STAGED commencement (§2.3's unrepresentable case), not deferred
> commencement. Batch 04 instead typed the population
> (`NOCommencementShape.STAGED_DELEGATED`, 167 acts, one receipt each) and
> offered it to batch 03's authorization gate, which re-dated exactly 8 acts
> to EARLIER instrument-proved dates. This entry's act is the leave-one-out
> residual: `no/lovtid/2026-06-19-48` is the only staged act with a
> not-in-force field signal, and even it carries counter-evidence on one law,
> so it belongs to a manual-override / provision-level commencement lane, not
> to a class-wide rule. It remains `dated`/2026-06-19, un-re-dated, carrying
> the staged receipt — the premature-commencement exposure it names is still
> real and still open, now scoped to that lane.

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

#### W-6 triage measurement (2026-08-02): the scan-visible payoff is real but modest, and ~30% of the unbound mass is one extraction defect

The family-first triage of all 40 divergent laws (1,573 provision-level
divergences) measured F-10's payoff against the scan honestly. 31 applicable
unbound bindings (declaring act `dated`/`instrument_authorized`, effective ≤
2026-07-10) touch the 58-law scan — 30 on divergent laws, 1 on a consistent
one — across 14 divergent laws. **Definitely F-10: 8 laws, 24 provision-level
divergences**, proven by requiring the published wording to appear as an
8-gram inside the amending act's segment citing THAT law under an
amending-verb lead (the unsegmented test said 30; segmentation removed 6
table-of-contents false matches). Possibly F-10: 6 further laws with an
applicable unbound act but no proven provision link. Exactly one law goes
fully consistent on binding alone (`no/lov/2005-06-03-34`, 3/3 proven, from
`no/lovtid/2016-12-16-102`). Cleanest witness: `no/lov/2002-04-26-12` §5
from `no/lovtid/2007-01-26-3` ("126. I lov 26. april 2002 nr. 12 om notarius
publicus skal § 5 … lyde: **Anke** …") — replay still says
kjæremål/tvistemålslova. This confirms and modestly raises the re-priced 8;
it does NOT support treating F-10 as a thousand-divergence prize (72% of the
corpus's divergences are the annex representation ceiling, W-17).

**And the biggest single cause of the unbound mass is a live extraction
defect, not missing binding logic**: the multi-part misbinding bug (W-15)
accounts for ~30% of F-10's 4,088 unbound bindings (1,249 lost (part, act)
pairs across 485 acts, 1,247 of them declared). Fixing W-15 first, then
re-measuring, is the ordered plan.

> **W-15 landed (2026-08-02): re-measured.** Lost (part, act) pairs
> 1,249 → 361; `no_amendment_index_declared_target_unbound` receipts
> 1,245 → 1,038 (−207), with the new failure modes receipted
> (`lead_unmatched` +220, `payload_unresolved` +8) rather than silent.
> F-10's residual unbound mass is now ~3,200 bindings corpus-wide; the
> scan-visible slice is the 4 laws that left the candidate set (their
> newly-bound amenders are contingent — the commencement lane's problem,
> not binding's) plus the possibly-F-10 laws from the triage. Next
> re-price after W-16/W-19/W-20 land.

#### Re-priced 2026-08-06 (after W-16→W-26): the gap is 36.3%, the residual is not a binding problem, and binding recovery is net-negative for the scan

Full measurement in `.tmp/f10-reprice/`; every prior number reproduced
exactly (declared total 8,643 invariant; pre-W-15 dump gives 1,245
receipts / 4,088 unbound; the W-18→W-25/26 op chain reconciles to
25,260). Headline: unbound **4,088 → 3,141 (47.3% → 36.3%)**, receipts
1,245 → 1,038 → **1,031**, acts-with-gap 1,245 → 1,031. The landings
recovered 951 bindings (393 acts shrank, 4 grew); `lead_unmatched`
took the bulk (2,086 → 1,422), `lead_base_unresolved` 835 → 751;
family 1 (bulk rename) −79 incidental; family 3 (numberless ids,
W-28) exactly conserved at 92. Gap-nature sample: 250/251 declared-
but-unbound verifiable targets named verbatim in the act body —
still pure extraction failure.

**Re-diagnosis (the important finding): the residual `lead_unmatched`
mass is NOT binding-resolution failure.** Its excerpts on scan-visible
acts show the base act resolved and the ADDRESS/ACTION grammar missing:
`… innledningen skal lyde`, `Nåværende femte ledd blir sjette ledd.`,
`nytt ellevte ledd`, `Innholdsfortegnelsen …`, punktum-level repeal
(= F-02/W-2), inline `skal ordet «X» endres til «Y»`,
amendment-of-an-amendment. F-10's own claim — "the index ignores the
declared field" — is now largely paid off; the residue re-files as
missing lowering families.

**Scan payoff re-priced: 24 → 8 proven divergences (8 laws → 4), and
the ledger's standing pricing rule is now: binding recovery
decertifies more than it repairs.** Since W-6: 2 laws repaired
end-to-end (`2005-06-03-34` consistent exactly as the triage
predicted; `2012-01-27-10` bound and entered the scan consistent), 4
decertified out of the candidate set by newly-bound CONTINGENT
amenders (`2002-04-26-12`, `2005-05-27-31`, `2010-02-19-5`,
`2015-05-12-27`), 3 improved. The corpus's cleanest witness —
`2002-04-26-12` §5 "Anke", 7 divergences, 5 proven from the STILL
UNBOUND `no/lovtid/2007-01-26-3` (dated 2007-02-27) — is alive but
off-scan. Zero-amendment surface: 100 → 97 laws, 57/40/0; 4 of the 5
field-confirmed predictions remain unbound+divergent, one new
predicted-divergent target via `instrument_authorized`
(`2012-05-25-27` ← `2020-06-23-98`, divergent at 6);
`2001-06-15-73` is 1/1 proven — the ONLY law binding alone would make
fully consistent today. Combined provable-today: **13 divergences
across 7 laws**.

**Family 1 (bulk rename) now reaches the scan, field-confirmed** by
the rename-signature test (replay OLD term, published NEW — the
8-gram proven test is structurally BLIND to substitution acts, which
never quote the resulting sentence): `2004-05-28-29` 3/9 and
`2009-03-06-12` 1/3 via `2009-06-19-48` (Kredittilsynet →
Finanstilsynet, applicable), and the biggest single prize —
arveloven `2019-06-14-21`, 19/28 via `2021-05-07-34` (fylkesmannen →
statsforvalteren) — is contingent, so the original "only after W-7"
judgment holds. **Family 3 / W-28 blocks nothing scan-visible** (0 of
the 33 scan-visible unbound pairs). Recommended next tranche: the
`section_intro_markers` closed list (→ **W-30**) — the only bounded
W-21-shaped work left. Clarification for future re-prices: step (b)'s
cause table is a TOP-SIX summing to 4,024 of 4,088 (six small tails
hold the other 64).

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
punctuation). ~~All three key on the marker sitting next to punctuation, which
is what makes them safely bounded.~~ (Corrected at W-16: that claim was true
of only two — the inline rule's regex never keyed on punctuation, and its
"between sentences" description was never true of it either; W-16 re-bounded
it by measured shape instead — lowercase-initial host word, single digit,
capitalized-word follower.) F-05's shape is the one where the marker sits
*before* the period, with nothing but a word to its left — precisely the
position that is indistinguishable from a cross-reference.

Conclusion: not a normalization problem. If it is worth solving at all, it needs
either footnote structure preserved at published-side extraction (so the marker
is typed rather than inlined) or a diff-time tolerance that is not a text rule.
Both are larger than a compare-lane batch. Left as recorded noise: 2 divergences
across the corpus, both in the commencement formula.

> **W-6 triage (2026-08-02): sizing confirmed, and the masking mode this
> entry warns about turns out to already EXIST in the lane.** The triage's
> digit probe re-confirmed exactly 2 genuine inline footnote-marker
> divergences corpus-wide (`2007-06-29-89` §6(1), `2017-05-22-28` §5(2)).
> But `verify.py:105`'s inline-footnote rule
> (`(?<=[a-zæøå])\s+\d+\s+(?=[A-ZÆØÅ])`) deletes STRUCTURAL numbering:
> `'Kapittel 1 Innledende bestemmelser'` normalizes to
> `'Kapittel Innledende bestemmelser'`, so "Kapittel 2 X" and
> "Kapittel 3 X" compare EQUAL — verified directly against
> `normalize_no_comparison_text` in the main checkout. A live masking bug,
> queued as W-16.

> **W-16 fixed (2026-08-02, `6bdbb3b12`).** The rule is re-bounded to fire
> on exactly the 49 measured genuine markers and none of the 502 false
> positives; the masking proved LATENT (zero scan movement, four-counter
> probe over all 56 laws under both regexes). This entry's two genuine
> cases are byte-identical under old and new normalization and are now
> test-pinned so no future footnote rule can start eating the
> marker-before-period shape. See W-16 in the queue for the full record.

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

### F-07 — Published editorial correction without an amending act — re-scoped (Rettelser lowering, W-18)

`no/lov/2020-12-18-156` §5(1) item 2: replay "skatteloven § **23** første ledd
bokstav b" (faithful to source bytes); published "§ **2-3**". Lovdata corrected
a typo editorially. ~~Per `NORWAY_LAWVM_STATUS.md` §2.2 this becomes an
exact-text-pinned oracle finding, not a replay change.~~

> **Misdiagnosed — the correction IS in the source bytes (W-6 triage,
> 2026-08-02).** The act's own artifact `no/lovtid/2020-12-18-156` carries a
> published `Rettelser` block in canonical amending grammar ("Det som er
> rettet er satt i kursiv. § 5 første ledd annet strekpunkt skal lyde: …
> § 2-3 …"), header-flagged `rettelse 2021-01-05 (se nederst)`. Negative
> evidence: only 2 acts bind this law, neither touching §5; zero unbound
> declared targets; the 13 forskrift citations are tilskudd regulations;
> exactly 1 amendment artifact corpus-wide carries the typo form, 6 the
> corrected form. Disposition: a **`Rettelser` lowering** (W-18) — derivable
> from source bytes, so §2.2 is satisfied without preferring the
> consolidation. Corpus: 25 artifacts carry a `Det som er rettet` block, 23
> operative; payoff today 1 divergence and this law goes consistent.
> Regression gate: `no/lovtid/2022-05-12-28` (advokatloven) has an operative
> erratum and its law is currently CONSISTENT — it must stay so.

> **Fixed (W-18, `c8ffa7eb9`, 2026-08-06).** The witness lowers and
> `no/lov/2020-12-18-156` is consistent; the advokatloven gate held
> byte-identical. The "23 operative" figure repriced under measurement —
> exactly 1 erratum is cleanly lowerable today; 7 correct unmodeled
> publication metadata (permanent ceiling), 5 need Del→law resolution
> (→ W-24), 14 are the untyped 2003–2011 generation with zero measured
> payoff. See work-queue item 18 for the full accounting.

### F-08 — CONSOLIDATED_MISSING / mixed clusters needing triage — triaged (W-6, 2026-08-02)

Replay retains provisions the published text no longer carries:

- `no/lov/2022-06-17-49` (Riksrevisjonen info-access, temporary): 3
  CONSOLIDATED_MISSING — plausibly the completed-purpose lifecycle of a
  temporary act (relates to F-03's theme).
- `no/lov/2023-11-24-85` (militærpolitiloven) §28(2): replay "Kongen kan gi
  overgangsregler."; published carries the 1988-act repeal clause instead, plus
  one OPS_MISSING.
- `no/lov/2015-05-12-27` §24(1): published shows "– – –" (collapsed
  consequential-amendment list) where replay keeps the introduction line.

> **Triaged (W-6).** 232 CONSOLIDATED_MISSING rows across 22 laws, in five
> clusters: annex addressing 108 rows / 1 law (recorded ceiling, see the
> annex families under W-17); unlowered repeals from real amending acts ~90
> rows / 6 laws (actionable, downstream of the binding/lowering work);
> **event-conditioned self-repeal** 14 rows / 3 laws — a NEW family: e.g.
> `no/lov/2022-12-20-118` §9(2) "§§ 2 og 4 oppheves når utvalget har
> avsluttet sitt arbeid", no amending act and no date, only Lovdata's
> footnote records the trigger fired; §2.3's floor applied to repeal
> (recorded ceiling; confirmed on `2022-12-20-118`, `2022-12-20-97`,
> `2020-12-04-136`); consequential-amendment sections dropped 9 rows / 8
> laws (recorded ceiling); and one small ACTIONABLE case —
> `no/lov/2022-06-17-49`'s own text says "§ 2 oppheves 31. desember 2022.",
> an explicit past date replay can execute, covering all 3 of that law's
> divergences (unqueued; ride along a future repeal-lowering batch). The
> third bullet above has MOVED: zero divergences corpus-wide now show a
> dash-only published side; `2015-05-12-27`'s 8 remaining rows are the F-04
> rename family.

### F-09 — Sparse-source ceiling (known class, recorded) — recorded; one law re-filed

`no/lov/2006-06-30-50` (SCE-loven, 212 divergences, 1 indexed amendment) and
`no/lov/2001-01-05-1` (vaktvirksomhetsloven, 83, 2 indexed) both carry
`sparse_indexed_history`. Per `NORWAY_LAWVM_STATUS.md` §5 these are
acquisition ceilings, not replay failures; excluded from engine-defect counts.

> **Re-filed (W-6 triage, 2026-08-02).** `2006-06-30-50`'s cause attribution
> was wrong: its divergences are the ANNEX family, not sparsity — the SCE
> Regulation sits on BOTH sides at different addresses (replay
> `chapter:1/chapter:I/section:a1/…`, published `chapter:v22c/…`); all 104
> OPS_MISSING rows pair 1:1 with a CONSOLIDATED_MISSING row after
> normalizing the annex prefix, and 93 of 104 are text-identical once the
> published `[EØS]` bracket adaptations are stripped. It moves to the annex
> ceiling (W-17). Also measured: the `sparse_indexed_history` signal
> OVER-FIRES — it flags 4 laws, not 2 (`2018-06-15-38` carries it while its
> divergences are annex). F-09 proper retains `2001-01-05-1` (83) plus the
> smaller genuine-sparsity rows measured in the triage (97 divergences / 3
> laws total for the family).

> **Second re-file (F-09 probe, 2026-08-07): the family's headline example
> was ALSO mislabeled.** A ground-truth probe on `2001-01-05-1` (parse the
> published consolidation's own `changesToParent` change notes — 22
> provisions, 22 notes, 0 without one — for the TRUE amender list, then
> attribute all 81 divergences) found the law has exactly THREE amending
> acts, ALL in the archive, ALL declaring it: `2015-06-19-65` (binds, 591
> ops), `2023-06-02-19` (binds, 2 ops), and `no/lovtid/2009-06-19-85` —
> which RE-ENACTED THE WHOLE LAW (new §1/§17/§18, old §1–18 renumbered
> §2–22) and binds NOTHING. **Attribution: (a) extraction 81, (b) missing
> data 0, (c) 0.** The single cause is a one-token lead-grammar gap: the
> 2009 act's part lead `"I lov 5. januar 2001 nr. 1 om vaktvirksomhet skal
> følgende bestemmelser lyde:"` — the citation resolves; the tail is not in
> the action grammar (family census: `skal følgende bestemmelser|paragrafer
> lyde` = 4 acts corpus-wide vs 1,810 for `gjøres følgende endringer`).
> Proof: 60/64 quotable rows 8-gram-present in the 2009 act's payload; the
> 4 non-quotable land exactly on its pure-renumber leads; old→new address
> map beats identity on 13 sections. Mechanisms: 60
> wholesale_reenactment_lead / 11 relocated / 6 dropped / 4 pure_renumber.
> The archive itself is CLEAN: 0 pre-2001 artifacts, 0 post-2001-but-absent
> amenders. Repair is TWO-PART BY NECESSITY (→ W-39): the act is contingent
> (`Kongen bestemmer.`), so the lead fix alone decertifies the law; the
> commencement instrument `no/forskrift/2011-04-01-342` commences Part I at
> 2011-04-01 but fails the whole-act-scope gate — part-scoped authorization
> is the other half. F-09 proper is now ONLY the smaller genuine-sparsity
> rows (~16 divergences / 2 laws from the triage); the claim "acquisition
> ceilings, excluded from engine-defect counts" no longer covers this law.
> Secondary observation, not chased: `2009-06-19-74` binds this law 1 op
> WITHOUT declaring it (42 declared vs 218 bound — an inverse-F-10
> signature) and Lovdata credits that provision to `2015-06-19-65`; its
> `dated 2009-06-19` status also deserves a check. Probe artifacts:
> `.tmp/f09-probe/` (p12_final.json holds the full 81-row attribution).

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
7. ~~**W-10 (temporal ordering):** replay orders amendments by `source_id`, not
   effective date. Investigate and pin the intended ordering before treating
   the divergence shapes of `no/lov/2010-02-19-5` and
   `no/lov/2010-06-25-28` as pure replay-fidelity evidence.~~
   **Closed 2026-08-02 — not a defect; the premise was false at the layer that
   matters.** The `source_id` sort at `replay.py:300` only orders op
   *collection*; the apply fold re-sorts every op through the shared kernel
   (`grafter.py:3641` → `core/op_ordering.py:210`) by
   `(effective, enacted, source_id, sequence)` — effective date primary,
   matching Estonia (`estonia/replay.py:78`) and Finland
   (`finland/amendment_selection.py:155`). Field-proven: forcing
   effective-date collection order genuinely flips the two laws'
   `amendments_applied` sequences while the replayed text hashes identically,
   and the 58-law scan stays byte-identical at 18/40/0. Only the two named
   laws reorder among the 58, both from the single pair
   `no/lovtid/2024-04-12-14` / `no/lovtid/2024-12-20-81`, whose targets are
   fully disjoint. The genuine underlying item is that `2024-12-20-81` is a
   staged commencement collapsed to `min(dates)` — the documented
   `NORWAY_LAWVM_STATUS.md` §2.3 floor, not a sort bug. Residuals worth
   remembering: the kernel's `OrderedOps.justification` receipt is unreachable
   from production, and `replay.py:300`'s string tie-break compares the
   trailing Lovtidend number lexically (harmless while the kernel decides
   order). The one live risk moved to W-12.
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
9. **W-4 (F-01):** DONE (hygiene pass, 2026-08-02) — `no-verify-scan`'s
   default `--as-of` is now derived from the corpus via
   `no_consolidation_snapshot_date` (latest `current.xml` observation
   instant), which independently reproduces the documented 2026-07-10
   horizon. Explicit `--as-of` wins verbatim. The seven sibling commands'
   stale defaults are W-14.
10. **W-5 (F-03):** DONE — decided against demotion (batch 04, 2026-08-02).
   The corpus's leave-one-out evidence settled it: blanket demotion of the
   mixed acts would cost 8 of the 58 scan laws and worsen 7 of them, because
   Lovdata's consolidation shows most mixed acts in force at their leading
   date. Batch 04 typed the population instead
   (`NOCommencementShape.STAGED_DELEGATED`, 167 receipted acts), offered it to
   the batch 03 gate (8 acts re-dated EARLIER on instrument evidence), and
   widened the marker vocabulary by the two measured-absent nynorsk siblings.
   F-03's act stays `dated` and re-routes to the override / provision-level
   lane (see the F-03 entry).
11. **W-6 (F-07, F-08):** DONE (2026-08-02) — family-first triage of all 40
   divergent laws complete; artifacts in `.tmp/w6/triage.{json,md}`. 16
   families over 1,573 divergences, every assignment witnessed. Headline: 72%
   is annexed-instrument representation (W-17 ceiling), F-10's proven scan
   payoff is 24 divergences / 8 laws (see F-10's W-6 subsection), F-07 was
   misdiagnosed (Rettelser lowering, W-18), F-08 triaged into clusters (see
   F-08), and two live bugs surfaced: the multi-part misbinding defect (W-15)
   and the compare-lane numbering-deletion masking bug (W-16). Honest
   unclassified bucket: 64 divergences across 17 laws (4.1%).
12. **W-12 (heading groups bypass the ordering kernel):** DONE
   (`6c6d9fdf5`, 2026-08-06). `NOHeadingGroup` now carries the SAME
   `OperationSource` provenance ordinary ops get, stamped by
   `replay_no_to_pit` with the identical (statute_id, enacted,
   effective) triple, and `apply_no_heading_groups` sorts by the
   ordering kernel's own `no_ordering_profile().temporal_key` via a
   key-only carrier — heading groups cannot go through `order_ops`
   itself (no target/action; its op-semantics stages would fabricate
   findings), but the KEY now has exactly one definition in the tree,
   which is the drift this item existed to close. The fix found and
   closed a WORSE second defect in the same latent region: `sequence`
   is the namespace of the synthetic container label and the parser
   restarts it per amendment, so two amendments touching one chapter
   minted colliding labels and the second's group was SILENTLY DROPPED
   by the idempotence guard (the fail-on-base test proves it: base
   yields one group, not two mis-ordered). Fixed by re-stamping
   sequence to fold position (identity for single contributors).
   Liveness guard: `no_heading_group_multi_source_fold` receipt —
   non-blocking when all contributors are dated (order proven by the
   kernel key), BLOCKING when any is undated (order unproven, §1.10).
   Still latent, re-measured against the post-W-30 corpus: census over
   all 2,544 entries × declared base_ids finds heading groups for
   exactly ONE law (`2024-01-12-1`, 3 groups, all from
   `2024-12-20-92`); replay of all 3,089 original-LTI laws
   byte-identical before/after; scan byte-identical; receipt fires on
   0 laws. Found alongside → W-31.
13. **W-13 (batch 04 doc/naming follow-ups):** (a) and (c) DONE (hygiene
   pass, 2026-08-02): `unresolved_act_ids` renamed to `offered_act_ids`
   tree-wide with an accurate docstring (the gate does not define the offered
   set; production passes `unresolved ∪ staged_delegated`), and the
   `STAGED_DELEGATED` docstring now states only the real guarantee — dates
   plus delegated tail, a shape read off the raw field — naming
   `no/lovtid/2024-06-21-50` (repeal-date tail, corpus-verified) as the
   counterexample to the staged reading. **(b) remains OPEN and is
   reclassified: NOT behaviorally inert.** Routing
   `normalize_no_commencement_phrase` through the 7-member
   `NO_DELEGATED_COMMENCEMENT_MARKERS` changes `lawvm no-source --json`'s
   `normalized_phrase` for exactly one act, `no/lovtid/2020-06-23-103`
   (`dated`; its field contains the new `departementet fastset` marker), via
   the unguarded `build_no_source_report` site (`commencement.py:386`,
   reached from `tools/no_source.py:37` for ANY entry). The other three call
   sites are safe (two filtered to unresolved statuses; the `--phrase`
   filter agrees old-vs-new on both new markers). Measured over all 2466
   index entries: exactly 1 divergence, and no routing avoids it — the
   function has no status input to exclude `dated` entries. So (b) is a
   decided behavior change for a future batch: either accept the one-act
   `normalized_phrase` change deliberately (arguably the better value — it
   groups the act under its marker) or add an explicit label map pinning
   emitted labels while single-sourcing the vocabulary. Also note: the
   staged receipt's `effective_date` is the pre-authorization `min(dates)`
   value by design; for the 8 re-dated acts it differs from the entry's
   post-authorization date — deliberate, and what the corpus test asserts
   on.
14. **W-14 (F-01 residue):** DONE (`08a199946`, 2026-08-06). All seven
   sibling commands (`no-frontier`, `no-divergence`, `no-coverage`,
   `no-debug`, `no-verify`, `no-verify-partition`,
   `no-verify-workqueue`) plus the demo script now derive their default
   `--as-of` from `no_consolidation_snapshot_date`, lazily inside
   `main()` exactly as the W-13 scan fix did, so missing-corpus behavior
   is identical across all eight by construction; the explicit flag
   still wins (guard-tested). The full-tree `2026-03-29` census (92
   hits / 22 files) found FOUR same-class instances the item's list
   missed and fixed them too: the three standalone `build_arg_parser`
   defaults (`no_coverage`, `no_debug`, `no_divergence`) and
   `build_no_coverage_report`'s LIBRARY-signature default (derived only
   in the `verify_result is None` branch — a caller passing a
   verify_result already fixed its horizon). One scoped deviation,
   commented in-code: `no-verify-workqueue --partition FILE` reads the
   prebuilt queue's own horizon without touching the corpus. Left
   deliberately, adjudicated: `bench_corpus.csv` (recorded benchmark
   baseline, 17 hits) and `no_anchor_manifest.py` (12 hits — the frozen
   content-pinned CTSF gate corpus plus its ad-hoc-probe fallback date,
   which deliberately matches the frozen rows for commensurability;
   moving either moves gate pins). Verified per-command: all seven
   derive 2026-07-10 with no flag; `no-divergence` with no flag now
   agrees with the scan's horizon (the item's headline case). Corpus
   pins unmoved; scan reproduced byte-exact.
15. **W-15 (multi-part misbinding, live bug):** DONE (`779554cb2`,
   2026-08-02). Multi-part unstructured amending acts misbound ops onto the
   PREVIOUS part's law — replay-corrupting. Witness: `no/lov/2017-06-16-51`
   §6(1) replayed as serveringsloven text from `no/lovtid/2019-06-21-57`
   (which contaminated it with 5 ops, not 1). Both diagnosed mechanisms
   confirmed: payload collection crossed `<section>` part boundaries, and a
   stale `active_base_id` outranked the correctly-resolved
   `section_base_id`. Fix: part boundaries are payload boundaries, and part
   entry re-seeds `active_base_id` from the part's own resolved law — the
   precedence chain itself is deliberately UNCHANGED (reordering would
   regress 1,343 intra-part law-switch leads across 30 acts, measured by
   the reviewer). Corpus effect: lost (part, act) pairs 1,249 → 361 (893
   bound / 5 lost), bindings +902/−6, n_ops 24,659 → 25,021, one
   pure-corruption index entry removed (`2018-12-20-119`), declared-target
   unbound receipts 1,245 → 1,038 with new failures receipted rather than
   silent. Independent review: APPROVE WITH FINDINGS — 18/18
   binding-correctness sample, 120-law replay sweep −9.8% divergences, zero
   genuine replay regressions. Two stop conditions fired (scan moved on 6
   rows; candidate set 58 → 56; two corpus pins) — verified cause-by-cause
   and signed off by the user 2026-08-02; pins updated with explanations
   in-place. Known costs, all recorded: 2 splitter casualties (W-19), one
   genuine lost binding inside them (`2016-12-16-91` finanstilsynsloven
   §7(1) s3), and 6 dropped global-text-replace ops (W-20, one previously
   correctly bound).
16. **W-16 (compare-lane masking bug):** DONE (`6bdbb3b12`, 2026-08-02).
   The inline-footnote rule deleted structural numbering on BOTH sides —
   "Kapittel 2 X" == "Kapittel 3 X" — the masking mode F-05 forbids. The
   fixer measured all 551 alterations the old regex made over 25,742
   compare-lane text units of the 56 candidate laws: 49 genuine markers
   (all the published-side commencement-formula superscript, all digit "1",
   zero replay-side), 487 structural headings, 15 content digits. That
   measurement killed both naive fixes: REMOVAL would add 49 sites of
   published-side noise, and PUNCTUATION-BOUNDING fires on nothing (the
   standalone rule already owns the between-sentences position — the
   inline rule's "between sentences" description was never true of its
   regex, which predates the named-rule refactor). Fix: measured-tight
   bounds (lowercase-initial host word + single digit + capitalized-word
   follower) — fires on exactly the 49 genuine markers and zero of the 502
   false positives. Scan: ZERO rows moved, double-verified by a
   four-counter probe over all 56 laws under both regexes — the masking
   was real but LATENT (both sides agree at every matched address today;
   the corpus even contains the collision pair "Kapittel 7/5 Avsluttende
   bestemmelser" collapsing to one string, in different laws). The fix
   converts a latent silent-failure mode into a guaranteed-visible one at
   zero measured cost. F-05's two genuine cases proven byte-identical
   under old and new normalization, now test-pinned shut.
17. **W-17 (annex families → typed ceiling):** DONE (`a41b79af4`,
   2026-08-06). The annexed-instrument family is now a TYPED, RECEIPTED
   ceiling in the verify lane — rows are annotated, never removed, so
   `ceiling + unexplained == divergence_count` always and no verdict can
   move (`classify_no_annex_ceiling` runs after `consistent` and
   `divergence_count` are final). Two per-row mechanical criteria, both
   cataloged with specs: `ceiling_annexed_instrument_address` (top step
   is a chapter whose label is NOT an ordinary legislative label — the
   four in corpus are `gdpr`, `rdk`, `rdkn`, `v22c` — with the annex
   token duplicated as a slash prefix on an instrument-article section
   label, shared-prefix test because bokmål writes `chapter:rdk` /
   `section:rdke/a1`) and `ceiling_annexed_instrument_counterpart`
   (present-on-one-side-only row at the CANONICAL address of an article
   the same law also carries at an annex address; keyed on the witnessed
   article number, which is what captures the SCE Regulation's 3
   truncated Article-80 signature subsections; MISMATCH excluded — a
   wording difference between the two copies stays unexplained;
   self-limiting — no annex witness, nothing typed). Measured capture:
   1,129 of 1,513 — EXACTLY the W-6 triage's number — as `2018-06-15-38`
   716 = 714 + 2, `2017-06-16-51` 210 = 204 + 6, `2006-06-30-50` 212 =
   211 (104 address + 107 counterpart) + 1, zero rows typed in the other
   54 laws (negative-control-pinned on `2001-01-05-1` and
   `2013-06-21-102`). Verdicts 21/36/0 unchanged, all 57 rows
   byte-identical on every pre-existing field; scan/partition output
   gains `divergence_totals` and `ceiling_rule_counts` conservation
   receipts. Payoff: top laws by UNEXPLAINED divergences are now
   `2001-01-05-1` 83, `2017-06-16-65` 57, `2013-06-21-102` 55 — the
   annex laws no longer drown the scoreboard. Found alongside, recorded:
   `2006-06-30-50`'s single unexplained row (§11a(1), an unlowered
   forskrift-hjemmel present in replay, absent from published) is that
   law's whole actionable surface — 211 of its 212 are ceiling; and the
   `sparse_indexed_history` mis-routing became W-23.
18. **W-18 (F-07 → Rettelser lowering):** DONE (`c8ffa7eb9`,
   2026-08-06). Typed `gazettenote[data-gazette-note-type=rettelse]`
   errata now lower as ordinary same-act REPLACE ops — keyed on
   Lovdata's own erratum attribute, never the word "rettet". The
   enumeration REPRICED the triage's "23 operative": 25 artifacts carry
   the block, split into 11 artifacts / 12 machine-typed notes (2017→,
   this rule's whole domain) and 14 untyped 2003–2011 narrative blocks
   (no typed date, positional payload boundary, only 2 address law text
   and neither law is a scan candidate — excluded, measured payoff
   zero). Of the 12 typed notes exactly 1 lowers: the F-07 witness
   (`2020-12-18-156` §5(1) item 2, "§ 23" → "§ 2-3"). The other 11 are
   excluded with typed `no_rettelse_not_lowered` receipts: 7 correct
   publication metadata the IR does not model (Referansefeltet /
   Hjemmelsfeltet — permanent recorded ceiling) and 4+1 are part-scoped
   or nested addresses needing Del→law resolution (→ W-24). Safety by
   construction: anchored single-`§` grammar (the nested advokatloven
   form `§ 73 nr. 7 § 6-7 …` names two sections and is rejected before
   any regex runs), one-item-payload requirement, erratum ops dated by
   the host act's own commencement (the announcement date rides in
   provenance, apply-inert — dating at announcement would let a
   correction overwrite genuine later amendments). Corpus effect: ops
   25,087 → 25,088, bindings 5,742 → 5,743, entries 2,465 → 2,466, all
   +1 = the witness op; zero pre-existing entries changed. Scan:
   21/36 → 22/35, divergences 1,513 → 1,512 (ceiling 1,129 unmoved,
   unexplained 384 → 383), 56/57 rows byte-identical, advokatloven gate
   held byte-identical. One stop condition fired and was signed off
   2026-08-06: status pin `dated` 1020 → 1021 (the witness artifact's
   first index entry), updated with the explanation in-place.
19. **W-19 (`_split_no_sentences` is abbreviation-unaware):** DONE
   (`4c9e88757`, 2026-08-05, landed jointly with W-20). Added `jfr.`,
   `m.m.`, `iht.` to `_SENTENCE_ABBREVIATIONS`. Corpus sweep over all
   leads: exactly 3 splits change, all arity wrong → right — the two
   ledger casualties (`2021-12-22-166` §25(1) via `jfr.`;
   `2016-12-16-91` §7(1) via `m.m.`, recovering the one genuine binding
   W-15 lost — finanstilsynsloven `1956-12-07-1` sentences 3–4) plus a
   THIRD recovery the sweep found that was not in the ledger:
   `2022-02-18-5` §19-7(3) → forsikringsavtaleloven `1989-06-16-69` (via
   `iht.`). 0 splits go right → wrong; all three forms measured to have
   zero legitimate sentence-final uses in the corpus. Single-letter forms
   (`b.`, `e.`, `g.` …) deliberately excluded — bare item letters DO end
   sentences (witness `2016-12-16-91` §11-15 "… bokstav e.") — and
   guard-tested. Replay-side blast radius: 275 of 91,447 texts (0.30%), 4
   in scan candidates, zero scan rows moved.
20. **W-20 (global-text-replace branch ignores `lead_base_id`):** DONE
   (`4c9e88757`, 2026-08-05). Five-line fallback in
   `_iter_unstructured_no_change_groups`: when a global text-replace lead
   cites no law of its own, bind to the part's resolved `lead_base_id`
   instead of dropping the ops. Scale signed off 2026-08-05: 60 ops, not
   6 — the fallback also emits 55 ops that never existed (classified
   against a pre-W-15 dump: 4 REBIND, 1 RESTORE, 55 NEW); 25 of 26
   (part, act) pairs bind to a declared change target and pass a
   part-announcement check. All three ledger-named acts verified
   op-by-op: `2014-06-20-24` ×4 and `2018-12-20-113` now on their own
   parts' laws; `2005-12-16-118` returns to `no/lov/2005-04-29-21`. ONE
   stop condition fired, verified, and signed off 2026-08-05: 6 inert ops
   bind `2009-06-19-74` → `1975-06-13-39` (utleveringsloven) on a
   `lead_base_id` that is wrong from a PRE-EXISTING inference defect (→
   W-21, not narrowed here); measured harm zero — all 6 `match_text`
   values absent from both original-LTI and current text, and the law is
   not a scan candidate. Combined W-19+W-20 corpus effect: ops 25,021 →
   25,087 (+66, 0 removed); bindings 5,736 → 5,742 (+6, 0 lost); lost
   (part, act) pairs 361 → 356 (0 newly lost); status distribution and
   coverage partition identical. Scan 56/21/35/1508 → 57/21/36/1513, both
   movements traced: `2014-08-15-59` enters divergent at 5 via its
   recovered sole binding (from `2019-05-24-18`), moving the
   `fully_replayable` pin 56 → 57 (authorized, explained in-place), and
   `2010-06-25-28` gains one amendment/op with divergences unchanged; 55
   of 56 shared rows byte-identical.
21. **W-21 (`_infer_no_unstructured_section_base_id` misses the
   "Lov <date> nr. N om X endres slik:" lead form):** DONE
   (`b895fc406`, 2026-08-06). New `_extract_no_law_announcement_base_id`
   at THIRD rank in the existing inference (no precedence reorder):
   recognises the nominative part announcement — head `Lov(a) …` plus a
   MANDATORY amending tail, the four corpus-measured surfaces `endres
   slik` (29) / `blir endra slik` (20) / `vert endra slik` (18) / `blir
   endret slik` (2) — and resolves via the existing citation extractor.
   The tail requirement is the guard: a bare `Lov … oppheves.` names a
   law acted on as a whole and must not seed the part. Sweep over all
   9,100 unstructured parts: 69 parts change — 67 wrong→right from
   nothing, 2 wrong→right rebinds (`2009-06-19-74`; `2008-03-07-4`,
   whose groups were already byte-identical via another route), 0
   right→wrong, 0 unchanged parts disturbed. Witness: 22 ops move to
   `2005-05-20-28` (16 structural + all 6 W-20 ex-inert text-patches,
   each `match_text` verified present in straffeloven's original LTI
   text and absent from utleveringsloven — the exact inverse of the
   W-20 finding) and utleveringsloven keeps the 3 genuinely its own;
   the "auto-corrects all 25" prediction over-counted by 3 (1 correctly
   nested-bound, 2 belonging to `1891-06-06-2` via the `1 a.` ordinal
   gap → W-26). Corpus: ops +140/−0, bindings +39/−0, 13 acts gain
   their first index entry, diagnostics −140 (exact 1:1 with gained
   ops), scan fully byte-identical (all 57 rows, all totals). Two stop
   conditions signed off 2026-08-06: (a) 1 op in `no/lovtid/2009-01-30-7`
   part III converts from receipted drop to harm-free silent misbinding
   via the period-less `nr 16` citation gap (→ W-25); (b) pins staged
   167→170 (+ sibling 166→169) and status contingent 914→920 / dated
   1021→1028, all from the 13 first-time entries, updated with
   explanations in-place. Straffeloven 2005 stays `blocked_contingent`
   (30 blocking sources) and out of the scan — the rebind is
   correctness groundwork, not scan movement.
22. **W-22 (month-token punctuation in the splitter's day-number guard,
   small):** DONE (`2a8302b50`, 2026-08-06). The guard now strips
   trailing punctuation from the month token before the
   `_NORWEGIAN_MONTHS` membership test. The strip set is `.,` — NOT the
   `.,;:` this item guessed — because an instrumented full index build
   recorded every raw token after a day-number boundary and only `,`
   (×2) and `.` (×1) ever occur, all three in the one witness text; a
   16-character strip set was differentially swept and changes exactly
   the same single split. Witness recovered: `no/lovtid/2020-12-21-166`
   § 10-20(1) "første og annet punktum" on skattebetalingsloven
   (`2005-06-17-67`) — the instalment list "15. mars, 15. juni,
   15. september og 15. desember … 15. juni." went 5 fragments → 2, the
   arity check now emits both sentence ops (act 6 → 8 ops), the 4th
   arity recovery W-19 left on the table. Corpus: n_ops +2/−0 (both the
   witness's), bindings/entries/status/`fully_replayable`/lost-pairs
   all identical, scan output byte-identical (same sha256). Replay-side
   blast radius: 47 of 91,447 texts (0.051%) in 31 laws, all 47
   mechanical wrong→right joins, 0 ops re-addressed, the 3 affected
   scan candidates' rows byte-identical. Guard-tested on a real corpus
   counterexample (`1999-01-29-6` §27(4)): boundaries after a
   sentence-final "mars." still split — the strip applies to the token
   AFTER a boundary, never before. No stop condition fired, no pin
   moved. Noted, zero corpus instances, no guard added: a sentence
   ending in "§ N." followed by a sentence opening on a month word
   would merge (the unpunctuated form already did pre-W-22), and the
   guard never validates the day number is a plausible day — both
   measured absent on index-build and replay sides.
23. **W-23 (`sparse_indexed_history` mis-routes the partition, measured
   contradiction):** DONE (`92fee2be5`, 2026-08-06). New partition
   bucket `annex_ceiling`, routed BEFORE `source_signal`: predicate
   `no_partition_is_annex_ceiling_dominated` = strict ceiling majority
   over W-17's conservation fields. Strict-majority rather than a tuned
   ratio because the corpus separation is total — members at 97.1% /
   99.5% / 99.7% ceiling, every one of the other 54 laws at exactly 0 —
   so the weakest predicate whose story is true of every member is the
   honest one. The three annex laws now share one bucket
   (`2018-06-15-38` and `2006-06-30-50` leave `source_sparse`,
   `2017-06-16-51` leaves `replay_defect`, which had claimed 210 replay
   defects where there are 6); `source_sparse` is now exactly F-09
   proper (`2001-01-05-1` 83, `2020-11-27-131` 15, both 0 ceiling) —
   every bucket's story true of every member. The ledger's own
   candidate fix (route by unexplained residue through the coverage
   split) was MEASURED AND REJECTED: it relocates the family split
   (untouched_drift vs replay_defect) instead of closing it. The signal
   itself deliberately unchanged — it is a scan-row field with two
   consumers outside the partition (no_bench SOURCE_UNAVAILABLE,
   no_anchor_manifest oracle-suspect) — but the counterfactual is
   measured: re-run on unexplained counts it fires on exactly F-09
   proper and goes silent on both annex laws (→ W-29). Buckets 16/15/4
   → 15/15/2 (+3 annex_ceiling), 57 laws complete and disjoint before
   and after; scan-level receipts byte-identical (verdicts 22/35,
   totals 1512/1129/383, all 57 rows, 0 field diffs); one intended
   keyset change (annex rows short-circuit the coverage columns, which
   nothing reads off a partition row). CLI: partition/workqueue/
   frontier all render the lane, workqueue and frontier print the
   RESIDUE as the actionable number, frontier's active-lane priority
   places annex_ceiling as least-actionable divergent lane (measured
   no-op today). Corpus-gated test pins the full 57-law membership.
24. **W-24 (Del/part-scoped address → law resolution for errata):** DONE
   (`3acbd3d57`, 2026-08-07). Del-scoped erratum directives now resolve
   their part to its law by REUSING the grafter's two existing resolvers
   (structured: the part's `document-change` `data-document`s, required
   to agree; unstructured: `_infer_no_unstructured_section_base_id` over
   the part's children), dispatched on the same predicate
   `iter_no_document_change_ops` uses — no second resolver. Parts key on
   Lovdata's `data-name="kap<ROMAN>"`, roman-only (chapter-numbered acts
   spell `kap15` and must stay unreachable). New anchored productions
   only as far as the measured five require: two Del-scope prefixes,
   `§ X overskriften` heading address, ledd-less `§ X bokstav <l>`; the
   explicit-citation clause is a CROSS-CHECK (cited law must agree with
   the part's law), and the load-bearing new guard is
   `no_corrected_host_op` — a Del-scoped erratum corrects the host's OWN
   amendment, so the corrected address must already be in the artifact's
   lowered op stream for that law. Adjudication: 2 LOWERED
   (`2019-12-20-110` Del I → kringkastingsloven §8-2 heading;
   `2023-12-20-98` Del V → skatteloven §5-42 bokstav a — both verified
   `host_text.replace(typo, fix) == erratum_text` on corpus bytes, the
   sign-off-accepted method since neither target is replayable; both
   dated per W-18's rule, sequenced after every op they could correct);
   3 EXCLUDED with sharper typed reasons (`2022-05-12-28` nested
   cross-act — the directive never names the target law;
   `2020-12-04-137` `no_corrected_host_op` and `2025-06-20-101`
   `no_part_scoped_target_address` [corrected at W-32 — this entry
   originally recorded both as `no_corrected_host_op`] — their hosts'
   own leads never lowered, → W-32). **The W-18 decertification
   warning proved STALE**: post-W-30 `2020-12-04-137` already binds
   eierseksjonsloven and is `instrument_authorized` at 2021-01-01, not
   contingent — no decertification was possible. Corpus: n_ops +2
   (exactly the two errata), everything else identical, scan 0/56 rows
   moved, receipts 11 → 9. General surface censused, NOT wired (110
   rows / 57 artifacts, → W-33 with the anaphoric-antecedent hazard).
25. **W-25 (period-less `nr` citations defeat every citation regex):**
   DONE (`38d9bc686`, 2026-08-06, landed jointly with W-26). The
   `nr` grammar now lives in ONE shared constant (`nr\.?\s+(\d+)`) used
   by all four citation regexes, lead-side AND payload-side — unscoped
   because the false-positive question was answered by measurement: a
   sweep over EVERY text node of every amendment artifact found 29
   wide-only spans across 9 acts, all 29 genuine citations, 0 false
   positives (structurally guaranteed — the full `lov <day>. <month>
   <year>` date prefix must already have matched, so the bare `nr` can
   never be an address `nr` or prose). Outcomes across all 9
   period-less leads (the sweep found a 9th the W-21 list missed): 3
   wrong→right rebinds — the witness (offentleglova §26 op moves to
   `2006-05-19-16`, straffeprosessloven absent from the act entirely),
   `2015-06-19-59` (apotekloven → alternativ-behandling-loven), and
   `2021-05-07-33` (våpenloven → straffeloven) — 2 neutral
   already-right, 2 correctly-inert payload prose, 1 inert
   global-replace lead, and 1 no-grammar-either-way (→ W-27).
26. **W-26 (letter-suffixed item ordinals not stripped from leads):**
   DONE (`38d9bc686`, 2026-08-06). The lead-side ordinal strip and
   the enumerated embedded pattern now share W-21's announcement-side
   spelling (`\d+\s*[a-zA-Z]?\.`) via one constant. Ordinal sweep over
   every unstructured lead at any depth: 140 leads carry an ordinal the
   widened strip admits and `\d+\.` does not — only 3 genuinely
   letter-suffixed (all in `2009-06-19-74`), 137 the spaced `1 . ` form
   Lovdata emits when the item number sits in its own `<strong>`; the
   strip newly resolves 7, the post-strip guards hold the other 133
   exactly where they were. No corpus lead opens with a bare
   `<digit> <letter>.` that is a section LABEL (labels carry the `§`
   sign, unreachable by the `^\d` anchor) — guard-tested on constructed
   negatives including the real `5 a. Lov … oppheves.` repeal. Witness:
   the 2-op W-21 residue moves to `1891-06-06-2`, utleveringsloven
   drops to exactly its 1 genuine op (the W-21 witness assertion edited
   in-place with justification), item `93 a.` newly emits sjømannsloven
   §54C, and `2020-11-20-128` (revisorloven's consequential act, spaced
   ordinals) goes from binding NOTHING to 29 audited ops across 8 laws
   — per-item counts reconciling exactly, zero misbindings. Combined
   W-25+W-26 corpus effect (fully independent, 3+2 acts): ops
   25,230 → 25,260 (+30/−0), bindings 5,782 → 5,793 (13 gained / 2
   lost — the 2 "lost" are the two parts whose own law is now correctly
   NOT bound), entries +1, lost (part, act) pairs 362 → 364 — metric
   honesty, not regression: both new lost pairs are lowering gaps
   (`første stykket` ops that never lower; an apotekloven op) that the
   misbindings had been masking. Scan fully byte-identical, all 57
   rows. One pin signed off 2026-08-06: contingent 920 → 921
   (revisorloven's act enters the index), updated in-place;
   dated/staged/fully_replayable unchanged.
27. **W-27 (nominative consequential item form, small):**
   `no/lovtid/2003-12-19-124` items 4 and 5 write "Lov 14. juni 1985
   nr 68 … § 5 nr. 3 skal lyde:" — nominative (no `I lov`), with a `§`
   target, but no `endres slik` tail, so neither the announcement
   extractor (requires the tail) nor the embedded/section extractors
   (require `I lov`) cover it, dotted or not. A separate grammar gap
   from W-21/W-25; needs its own measured pass (enumerate the form
   corpus-wide, decide rank).
28. **W-28 (law citations with no `nr` at all):** DONE (`c5224c6c1`,
   2026-08-07, landed jointly with W-36). The id-landscape measurement
   overturned this item's own premise: NO date-only ids exist in the
   corpus — pre-numbering acts are filed under `<date>-0` (22 of the
   645 current ids, 1687–1968: forvaltningsloven `1967-02-10-0`,
   bilansvarslova `1961-02-03-0`, Lappekodisillen `1751-10-02-0`,
   Grunnloven `1814-05-17-0` — the LTI filename's `000` number
   normalized). Resolution is therefore DETERMINISTIC (append `-0`),
   not date-unique-with-title-tiebreak; the guard is
   `_NO_NUMBERLESS_LAW_DATES`, a closed 31-date set Lovdata attests
   twice over (22 `-0` corpus ids + 20 date-only declared targets, 11
   in both, latest 1968, closed by history), re-derived from the
   archive by a test so drift fails loudly. UNGATED the rule invents
   laws — measured: it answered `2001-04-20-0` for
   valdsoffererstatningslova and displaced the correct numbered id.
   Rank: LAST, behind both numbered patterns, in the head extractor
   and the embedded patterns (not the plural free-text harvester).
   Sweep: 334 numberless spans / 131 artifacts; 76 of 151 unresolved
   leads resolve; residue 56 lead-grammar/passing-prose + 11
   drafter-omitted-number (correctly declined) + 8 outside the corpus.
   F-10 family-3 reconciled: the claim "no corpus id has that shape"
   holds LITERALLY, its inference ("109 declared date-only ids can
   never bind") is FALSIFIED — 54 of the 93 pairs name laws the acts
   NOW bind, kept on receipts only by id-exact comparison (→ W-38).
   13 pre-numbering laws gain their first amending op; none is
   executable, so the scan is untouched — F-10's "family 3 blocks
   nothing scan-visible" confirmed from the other side.
29. **W-29 (`_infer_no_source_signal` should read the W-17 residue,
   one-liner, fully measured):** the signal's `divergence_count` input
   counts ceiling rows, which is 100% of its over-firing — the W-23
   counterfactual re-ran it with `unexplained_divergence_count` and it
   fires on exactly F-09 proper (`2001-01-05-1`, `2020-11-27-131`) and
   goes silent on both annex laws. W-23 left it because `source_signal`
   is a scan-row field (conservation constraint) with two consumers
   outside the partition whose semantics need their own check:
   `no_bench.no_bench_unit_result` routes SOURCE_UNAVAILABLE off it,
   and `no_anchor_manifest._no_oracle_suspect` uses it as a
   commensurability witness. Landing it moves scan rows
   (`source_signal_counts` 4 → 2) — needs its own priced pass over
   those two consumers. Counterfactual data: `.tmp/w23/annex_coverage.json`.
30. **W-30 (`section_intro_markers` closed list → measured morphology):**
   DONE (`726da4f49`, 2026-08-06). The 11-literal tuple is replaced by
   `_NO_SECTION_INTRO_MARKER_RE` — a closed morphology over the one
   amending construction, measured on the EXACT gate population (47,455
   distinct leads reaching `_extract_no_section_base_id_from_lead` in a
   full corpus parse; the re-price's 509/270 was a diagnostics-side
   sample — the gate sees 535 leads / 346 acts in 37 further
   spellings). The determiner slot is CLOSED and load-bearing: a
   bounded-wildcard draft admitted substantive varemerkeloven prose and
   was rejected at design time; the cost is 2 genuine long-adverbial
   leads, pinned as deliberate misses. All 11 old literals admit
   identically. Sweep: 556 parts change — 553 first resolutions, 3
   rebinds to the head-cited law, **0 right→wrong**; ops +958/−0 with
   the identity multiset conserved in every one of the 116 changed
   acts; exhaustive audits (part-vs-lead 0 violations; payload-vs-
   target 958/958; 23-act deep sample clean). Corpus: bindings
   5,793 → 6,084 (+311/−20 — the 20 are full rebinds, the same metric
   honesty as W-25/W-26), 64 first-time index entries, declared-unbound
   3,141 → 2,850 (receipts 1,031 → 975), `lead_base_unresolved` −1,648
   with +674 honestly re-filed as `lead_unmatched` (the re-price's
   lowering-gap re-diagnosis confirmed: 200 further acts already bound
   right via inheritance, 38 emit no ops either side). Scan, signed off
   2026-08-06: candidates 57 → 56 — ONE decertification
   (`2006-06-30-50` via contingent `2007-06-29-81`, taking its 211
   ceiling rows incl. all 107 counterpart rows off-scan; returns when
   the commencement resolves), TWO repairs (`2017-06-16-65` 57 → 13,
   `2017-06-16-67` 6 → 2, both via instrument-authorized amenders),
   one ops-only change (`2010-06-25-28`); totals 1512/1129/383 →
   1252/918/334 with exact conservation; zero-amendment surface
   byte-identical. **The re-price's decertification prediction was
   REFUTED**: it conflated this tail family with the bulk-rename
   family — `2010-06-25-28`'s family act is dated and `2017-06-16-67`'s
   only contingent declarer is `2021-05-07-34` (family 1, never
   bindable by W-30); the real decertification was unpredicted. Pins
   signed off and updated in-place: staged 174/173, authorized 539×3
   (+531 non-staged), status 953/1049/539, fully_replayable 56, the
   W-17 subset pin minus the departed law (ceiling 918), the W-23
   partition pin at 56 rows. Found, left: 6 near-miss forms (2
   misspelled nouns, `foretas`, 3 `foreslås` proposal forms — each a
   different morphological dimension needing its own measurement).
31. **W-31 (`_apply_heading_group` has five receiptless failure paths,
   small):** found at W-12. The heading-group fold returns `body`
   unchanged on every failure path — start section not found, no
   parent, no matched sections, no chapter ancestor, label already
   present — with no receipt on any of them. The label-collision path
   was a real silent drop (fixed at W-12 by the sequence re-stamp);
   the other four are the same silent-no-op shape and should receipt,
   mirroring `no_heading_group_multi_source_fold`'s pattern. Also
   noted at W-12, related: `replay.py`'s collection sort tie-breaks on
   the Lovtidend number LEXICALLY (`…-9` sorts after `…-92`) — now
   inert (nothing downstream depends on collection order any more) but
   it is the last reason that sort exists; and `OrderedOps.justification`
   remains unreachable from production (the W-10 residual).
32. **W-32 (two host-lead lowering gaps + spaced labels):** DONE
   (`a60881695`, 2026-08-07). (a) Multi-`bokstav` leads: 157 genuine
   multi-letter enumerations censused; the 126 sharing the single-item
   address shape wired (widening only ARITY), 26 ledd-less + 12
   `nr.`-carrying recorded unreachable; 240 items newly lowered with
   per-item actions (`bokstav e` REPLACE / `ny bokstav f` INSERT),
   all-or-nothing arity enforced and receipted
   (`no_parse_unstructured_multi_item_payload_arity_mismatch`, fires on
   exactly 1 act). (b) Renumber-plus-replace: of 286 structured moves,
   25 carry `skal lyde`, 18 already lowered via their own
   `data-change-part`; the 7-lead gap wired for 6 (REPLACE targets the
   DESTINATION, sequenced after the RENUMBER; the 7th has two move
   tokens, receipted). The stale `§ 14 a. Studentombud` heading was the
   dropped payload, not a renumber defect — replayed §28b now reads
   `§ 28 b. Nasjonalt studentombud`. (c) Spaced labels: the narrow
   class didn't just fail, it truncated (`§ 216 i` → section 216) then
   silently dropped; spec-level differential over 153,100 texts: 294
   gained / 0 lost / 0 changed, BUT the op-level differential forced a
   bound — the ledd-less sentence production widened cost 2 right→wrong
   (it overrides structured markup with a subsection-less address), so
   the widening applies ONLY to the ledd-carrying production,
   negative-test-pinned. Payoff: the eierseksjonsloven erratum lowers
   through unchanged W-24 code (receipts 9 → 8) and its scan row
   repairs 13 → 9 (signed off; all 4 closed divergences traced to
   §49(2) e/f/g); the fagskoleloven erratum stays excluded — W-24's
   guard requires the EXACT corrected address and the recovered host op
   is the whole section; ancestor containment is a W-24 design
   decision, byte relation verified anyway (note: W-24's DONE entry
   misrecorded this receipt as `no_corrected_host_op`; its base-state
   reason was `no_part_scoped_target_address`, now advanced to
   `no_corrected_host_op` by (c)). Corpus: ops +471 (478 gained − 7
   base-changed; all audited), bindings +48/−1, 4 first-time entries,
   declared-unbound 975 → 963, unexplained divergences 334 → 330. One
   stop condition signed off 2026-08-07: 1 op lost + 6 stale→stale
   moves in `2015-06-19-65` via the pre-existing payload-cursor
   boundary defect (c) exposed (→ W-34); zero scan impact. Found, not
   changed: `blir oppheva` (Nynorsk) absent from the sentence grammar's
   `skal lyde|oppheves` alternation — unswept gap.
33. **W-33 (ordinary Del-scope references, wiring after W-24's census):**
   110 rows / 57 artifacts where an ordinary lead scopes an address to
   `Del <N>` (census `.tmp/w24/general_surface_census.json`): 42
   own-part rows (28 already resolve), 34 foreign-part-explicit (16
   misbind hazards), 14 foreign-part-anaphoric (7 hazards), 20 inert
   commencement clauses. HARD-WON WARNING for any wiring: `lovens del
   <N>` is ANAPHORIC to the act announced by the enclosing part, not to
   the host artifact — witness `no/lovtid/2014-12-19-73` Del X, where
   "I lovens del II …" means `2014-03-07-5`'s Del II, and reading the
   host's own Del II binds `1949-07-28-26` instead of `1953-06-26-11`.
   23 of the 48 foreign rows get a confident wrong answer from a naive
   part resolver; the antecedent must resolve first. W-24's shipped
   code is immune (directive-anchored Del prefix, no anaphoric erratum
   exists).
34. **W-34 (payload cursor does not stop at law-switch leads, shared
   seam):** DONE (`310e28d71`, 2026-08-07). The boundary predicate is
   MEASURED, not asserted: a census over all 2,761 unstructured
   artifacts found 1,026 (lead, crossed-node) pairs → 299 distinct
   nodes; the brief's candidate signals FAIL (DOM depth erased by the
   part flatten 299/299; element class degenerate — all bare `legalP`;
   ordinal not necessary). What separates is WHERE THE CITATION SITS:
   after ordinal strip, 297/299 carry it in the node's first sentence
   (four prefix spellings: `I `, nominative, `I endringen(e) i `); the
   2 rejects are Lovdata run-on nodes with the citation at offsets
   97/195 behind a completed quoted sentence. Predicate: the citation
   must fall in the first sentence — no tunable threshold, clean 297/2,
   no receipt needed. Results: 15 acts touched; ops +78 net (434
   rebinds, 79 new, 13 payload truncations all verified as the next
   lead's material, 1 removed — a DUPLICATE that had emitted twice off
   two swallowed leads; zero correctly-bound ops lost). External
   binding check (op vs nearest preceding lead, recomputed from the
   document): 443 disagreements → 3, all verifier artifacts. Witness
   fully recovered: items 59/60/61 bind their own laws; the 2-op
   residue is item 58's numberless citation (W-28), pinned as such.
   W-21's §412 nested-payload witness byte-identical (its items are
   `defaultP`, always stopped at). Bindings +164 = exactly the
   declared-unbound pair drop (2,806 → 2,642); receipts 963 → 960;
   `2013-06-21-75` leaves the zero-amendment set. Scan movement signed
   off 2026-08-07, scoreboard 22/34 → 21/35 at 56 candidates:
   `2013-06-21-102` (55 div) decertified via a newly-bound
   `Kongen bestemmer` act (recoverable); `2013-06-21-75` enters at 1;
   `2012-01-27-9` repairs 6 → 5; and `2005-06-03-34` FLIPS
   consistent → divergent (0 → 3) — honest exposure: its item 209 now
   lowers correctly but Lovdata's markup traps items 210/211's leads
   INSIDE the payload element (→ W-35). `2001-01-05-1` re-routes
   source_sparse → replay_defect (its sparse signal stops firing after
   item 178 binds; sparse count 3 → 2). Unexplained divergences
   330 → 278. Pins updated in-place per the signed-off package.
35. **W-35 (`futureLegalArticle`-internal trapped leads, payload-internal
   seam):** DONE (`6fe57ebec`, 2026-08-07). Corpus census: of 7,538
   `futureLegalArticle` elements crossed by a payload run, 41 contain
   trapped leads (52 leads, 6 artifacts; W-34's "42" was its own
   per-op-payload count). **Classified 52/52 trapped markup, 0 genuine
   content, 0 residue** — the decisive proof is ORDINAL GAP-FILL:
   50/52 carry item ordinals that are disjoint from the sibling
   enumeration's AND fill its gaps exactly (genuine quoted content
   would have to duplicate a used number or invent one outside the
   run); the other 2 trapped tails open with the NEXT PART's flattened
   `centeredP` roman marker. Split design: one positional pass after
   the flatten — the first direct child W-34's law-switch predicate
   fires on opens the trapped tail; everything from there re-enters
   the sibling stream after the truncated element, where the full
   existing machinery handles it (freed leads chain through further
   trapped elements with no special casing). Deep-copies rather than
   mutating (the rettelse reader walks the same tree — receipts 8 → 8
   byte-identical). DOM audit: 65 children removed = 52 leads + 13
   their payloads, 0 orphans, 41/41 retained heads byte-identical.
   Conservation: +16 ops net (30 truncations, 74 pure rebinds, 20 new,
   4 rebind-plus-truncation pairs); rebind adjudication vs the TRUE
   governing item: 62 wrong→right, 13 stale→stale (all under leads no
   resolver can reach — run-ons and numberless citations), 0
   right→wrong. Bindings +37 = exactly the declared-unbound pair drop
   (2,642 → 2,605). W-21 §412 witness pinned byte-identical (214
   groups / 483 ops / payload digest). Scan, signed off 2026-08-07:
   `2005-06-03-34` 3 → 0 divergent → CONSISTENT (the W-34 flip
   returned), `2001-01-05-1` 83 → 81, `2001-06-15-65` 4 → 2 — all
   three the identical mechanism; scoreboard back to 22/34; ceiling
   untouched at 918; unexplained 278 → 271. Residue invariant 57 → 13
   op payloads containing a lead: 7 Lovdata run-ons (→ W-36) + 6
   benign self-referential.
36. **W-36 (Lovdata run-on nodes, mid-node lead extraction):** the last
   reachable class of swallowed leads — a single `legalP` that
   concatenates one lead's payload tail with the NEXT lead's head.
   DONE (`c5224c6c1`, 2026-08-07, landed jointly with W-28). The
   measurement overturned the ledger's proposed fix shape: the run-on
   is a DOM defect, not a text defect — Lovdata closes the paragraph
   late, so the next lead sits in its OWN child element
   (`ul.defaultList > li > article.legalP`) and the run-on exists only
   in `itertext()`. The split anchors on the ELEMENT, which rejects
   both non-run-on classes with nothing to tune (10 ordinal-head nodes
   → W-37; 1 text-only citing-prose node). A second load-bearing head
   guard emerged from the DOM census (62 nodes / 14 acts): a head
   ending `:` WITHOUT an intro marker is an amendment directive whose
   colon opens its own payload — 2 such nodes are plan- og
   bygningsloven's consequential list QUOTED VERBATIM as a provision's
   new text, byte-identical markup to the 57 genuine run-ons, caught
   only because splitting them emitted an op the act never made
   (external-truth audit went 0→1 on that act; guard added,
   negative-controlled). 60 splits / 12 acts; run-on→trapped(W-35)
   fixpoint iteration (max 2 productive turns); joint gap-fill proof
   61/61. `2005-06-17-84`'s nested amendment-of-an-amendment lead
   deliberately NOT reached (binding it would be wrong, not
   recovered). Joint W-36+W-28 results: ops +136, bindings +140/−8
   (the 8 all stale bases losing their last op to a correct rebind),
   10 first-time entries, external truth 286 → 41 disagreements (28
   artifacts better, 0 worse), op-payload invariant 13 → 6 (all
   self-referential), the 14 known stale ops all re-adjudicated to
   their true laws, exactly 1 op dropped corpus-wide (it was wrongly
   bound via a compound-word citation `plan- og bygningslov …` that
   `\b`-anchored `lov` cannot reach — recorded). Scan byte-identical
   on all 56 rows. Signed off 2026-08-07: the §412 witness pin
   movement (W-28's Lappekodisillen witness lives inside that act;
   sub-witnesses now pinned tighter) and the corpus pin package.
37. **W-37 (ordinal-prefix embedded leads, bounded, W-26-shaped):** 10
   nodes / 5 acts where an embedded `I lov …` lead carries an item
   ordinal the head-anchored `_extract_no_embedded_multi_act_lead`
   cannot strip — including bare-letter ordinals (`a.`, `c.`) that
   `_NO_LEAD_ITEM_ORDINAL` cannot match: `2009-06-19-97` (3),
   `2021-06-18-89` (3), `2009-06-19-103` (2), `2002-06-14-20` (1),
   `2009-06-19-74` (1). Fix: extend the ordinal strip to the embedded
   pattern's head (and bare letters), with the usual differential
   sweep.
38. **W-38 (declared-side date-only → `-0` normalization, F-10
   headline mover):** W-28 proved the 109 family-3 declared date-only
   ids CAN bind — normalizing `<date>` → `<date>-0` in
   `_no_index_declared_target_unbound_diagnostic` would clear 54 of
   the 93 current family-3 pairs (laws their acts now bind), leaving
   24 unbound-with-law-present and 15 law-absent. Deliberately left
   at W-28 because it moves F-10's headline totals and the receipt
   docstring pins reconciliation with
   `scripts/probes/no_declared_target_coverage.py` — needs a small
   priced pass that updates both sides together. Also recorded there:
   `2009-06-19-90`'s structured path previously bound the date-only
   id and now binds `-0` (canonicalization improvement costing one
   newly-receipted pair); `future_articles[0]` single-payload
   assumption still latent.
39. **W-39 (vaktvirksomhetsloven repair: re-enactment lead tail +
   part-scoped commencement, TWO-PART BY NECESSITY):** from the F-09
   probe (2026-08-07) — the single fix worth 81 scan divergences, the
   largest single-law prize left on the board, but BOTH halves must
   land together or the law gets worse. (i) Lead grammar: the
   collective re-enactment tail `skal følgende bestemmelser lyde:`
   (and `… paragrafer lyde:`) — 4 acts corpus-wide — is not in the
   action grammar; the witness `no/lovtid/2009-06-19-85` re-enacted
   the whole law (new §1/§17/§18, renumber §1–18 → §2–22) and binds
   nothing, receipted `lead_base_unresolved` ×7. The payload is a
   sequence of full sections plus pure-renumber leads — closer to the
   W-32(b) renumber-plus-replace family at act scale than to ordinary
   leads; sweep the 4 acts before designing. (ii) Commencement: the
   act is contingent (`Kongen bestemmer.`); binding it without
   authorization decertifies the law (standing pricing rule). The
   instrument `no/forskrift/2011-04-01-342` ("Delvis ikraftsetting",
   2011-04-01, header `Endrer lov/2001-01-05-1`) commences exactly
   Part I but fails the whole-act-scope conjunct — the needed
   capability is PART-SCOPED commencement authorization for multi-part
   staged acts (the same gap W-24 recorded for the eierseksjonsloven
   family from the other side; `no/forskrift/2023-05-11-690` is the
   Part II twin). Expected payoff when both land: `2001-01-05-1`
   81 → near-0 (60 rows 8-gram-proven + 11 relocated + 6 dropped + 4
   renumber, all from the one act), scoreboard +1 consistent
   candidate — price the residual honestly at landing. Also check the
   probe's secondary observation while in the area: `2009-06-19-74`
   binds this law without declaring it and Lovdata credits the
   provision elsewhere.

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

- **2026-08-07 (F-09 probe: vaktvirksomhetsloven re-attributed)** —
  **The sparse-source family's headline example is not sparse: all 81
  of `2001-01-05-1`'s divergences are extraction, zero are missing
  data.** Research-only (artifacts `.tmp/f09-probe/`). Method: the
  published consolidation's own per-provision change notes give the
  TRUE amender list (3 acts, all in-archive, all declaring); the
  whole-law re-enactment act `2009-06-19-85` binds nothing on a
  one-token lead-grammar gap (`skal følgende bestemmelser lyde:` — 4
  acts corpus-wide carry the tail), proven by 8-gram containment on
  60/64 quotable rows plus the renumber receipts and the old→new
  address map. The archive is clean both ways (0 pre-2001, 0
  post-2001-absent amenders). F-09 re-filed a second time — the
  family now holds only ~16 genuinely-sparse divergences — and
  **W-39** opened for the two-part repair (lead tail + part-scoped
  commencement authorization, which must land TOGETHER or the law
  decertifies; the instrument for Part I exists and is per-part
  clean). The largest single-law prize on the board: 81 rows behind
  one act.

- **2026-08-07 (W-36 + W-28 applied)** — **The last reachable
  swallowed-lead class is gone and the pre-numbering acts join the
  index: run-ons split at the DOM element Lovdata failed to close, and
  numberless citations resolve deterministically to the corpus's
  `<date>-0` ids** (`c5224c6c1`). Both fixes overturned their
  items' proposed designs by measurement: the run-on is a DOM defect
  (element-anchored split, no sentence heuristics; a head guard holds
  back two verbatim-quoted consequential lists that are byte-identical
  in markup to genuine run-ons), and W-28 needed no title tiebreak —
  pre-numbering acts are filed under `-0`, so resolution is
  deterministic behind a 31-date attested set (ungated, the rule
  invents laws; measured). Joint: +136 ops, +140/−8 bindings, 10
  first-time entries, external truth 286 → 41 (0 artifacts worse),
  op-payload invariant 13 → 6, all 14 known stale ops re-adjudicated.
  Scan byte-identical on all 56 rows — and F-10's family-3 inference
  is falsified (54 of 93 declared date-only pairs name laws now
  bound), opening **W-38** for the declared-side normalization;
  **W-37** opened for the bounded ordinal-prefix family. Signed off:
  the §412 witness pin movement (W-28's own Lappekodisillen witness
  lives in that act) and the pin package.

- **2026-08-07 (W-35 applied)** — **The trapped-lead seam is closed
  with a zero-guess classification, and the W-34 flip comes home:
  `2005-06-03-34` is consistent again, with two bonus repairs by the
  identical mechanism** (`6fe57ebec`). 52/52 trapped leads classified
  markup-error by the ordinal gap-fill proof (trapped ordinals
  disjoint from AND filling the sibling enumeration's gaps — a
  signature genuine quoted content cannot produce). One positional
  split pass; freed leads re-enter the sibling stream and the full
  machinery handles them, chaining included. DOM audit 0 orphans;
  conservation +16 ops with 62 wrong→right rebinds and 0 right→wrong;
  bindings +37 = the declared-unbound pair drop exactly; W-21's §412
  witness byte-identical by digest. Scan signed off: three rows, all
  the same mechanism, scoreboard 21/35 → 22/34, unexplained
  278 → 271, ceiling untouched. Opened **W-36** for the run-on class
  — the last reachable swallowed-lead family, with W-35's
  enumeration-gap lists as its ready-made work queue.

- **2026-08-07 (W-34 applied)** — **The payload cursor stops at
  law-switch leads, and the boundary is a measured predicate, not a
  guess: the citation must sit in the crossed node's first sentence**
  (`310e28d71`). The census killed the plausible signals (DOM depth
  erased by the part flatten; element class degenerate) and found the
  real one — 297/299 crossed nodes carry their citation
  first-sentence, the 2 rejects being Lovdata run-on nodes. 15 acts
  touched, +78 ops net (434 rebinds, 79 recovered, 1 duplicate
  removed, 13 truncations all verified as the next lead's material,
  zero correctly-bound ops lost); the external binding check went 443
  disagreements → 3, all verifier artifacts. Bindings +164, exactly
  the declared-unbound pair drop. W-21's nested-payload witness
  byte-identical. Signed-off scan movement, scoreboard 22/34 → 21/35:
  one recoverable decertification (`2013-06-21-102`, 55 div), one
  entry at 1, one repair (`2012-01-27-9` 6 → 5), and the honest
  consistent→divergent flip of `2005-06-03-34` (0 → 3) caused by the
  `futureLegalArticle`-internal trapped-lead seam — opened as
  **W-35**, whose fix returns it. Unexplained divergences 330 → 278.
  `2001-01-05-1` re-routes to replay_defect as its sparse signal
  stops firing (sparse count 3 → 2 — W-29-relevant).

- **2026-08-07 (W-32 applied)** — **The last unblockable erratum
  lowers, eierseksjonsloven repairs 13 → 9 on the scan, and the
  spaced-label truncation defect is closed with a measured bound**
  (`a60881695`). Three sub-fixes, each swept: multi-`bokstav` arity
  (240 items newly lowered, all-or-nothing enforced),
  renumber-plus-replace (6 destination-targeted REPLACEs recovered —
  the "stale heading" was the dropped payload all along), and the
  spaced-label class widened for the ledd-carrying production only
  (the op-level differential caught the ledd-less production
  overriding structured markup, 2 right→wrong, bounded out and
  negative-pinned). +471 ops all audited; unexplained divergences
  334 → 330. Signed off: the eierseksjonsloven scan repair (4 closed
  rows traced) and the 1-lost-op/6-stale-moves cost of the
  payload-cursor boundary defect W-32(c) exposed — opened as
  **W-34** (shared seam, needs its own measured pass). The
  fagskoleloven erratum stays excluded on W-24's exact-address guard;
  ancestor containment recorded as a design question. W-24's DONE
  entry corrected in-place (misrecorded receipt reason).

- **2026-08-07 (W-24 applied)** — **Del-scoped errata resolve their
  part's law through the grafter's own resolvers, two of the five
  excluded errata lower with byte-exact verification, and the W-18
  decertification warning is measured stale** (`3acbd3d57`). No
  second resolver: parts dispatch on the same predicate ordinary
  lowering uses, roman-keyed so chapter-numbered acts stay
  unreachable. The `no_corrected_host_op` guard is the design's core —
  an erratum corrects the host's own amendment, so the corrected
  address must exist in the artifact's op stream, which splits the
  four Del cases 2/2 and prevents a correction landing on an unrelated
  live provision. The two lowered ops (kringkastingsloven §8-2
  heading, skatteloven §5-42 bokstav a) are verified by
  `host.replace(typo, fix) == erratum` on corpus bytes — the
  sign-off-accepted method where no PIT replay exists — and dated per
  W-18's binding rule. Three sharper exclusions; receipts 11 → 9;
  n_ops +2 and NOTHING else moves (scan 0/56 rows). Stale-warning
  finding: `2020-12-04-137` is instrument_authorized and already bound
  post-W-30, so the feared decertification of eierseksjonsloven was
  never live. Opened **W-32** (the two host-lead lowering gaps that
  now solely block the last two Del errata) and **W-33** (ordinary
  Del-scope wiring, 110-row census, with the anaphoric `lovens del`
  hazard that would misbind 23 of 48 foreign rows under a naive
  resolver).

- **2026-08-06 (W-12 applied)** — **The last parallel ordering surface
  is closed: heading groups fold in kernel-keyed temporal order, and
  the silent-drop defect hiding behind it is fixed** (`6c6d9fdf5`).
  Heading groups now carry the same `OperationSource` ordinary ops get
  and sort by `no_ordering_profile().temporal_key` — one key
  definition tree-wide. The fix surfaced a worse latent defect: the
  parser restarts `sequence` per amendment, and `sequence` namespaces
  the synthetic container label, so two amendments touching one
  chapter minted colliding labels and the second's group was silently
  dropped (base-failure verified: one group survives, not two
  mis-ordered). A liveness receipt (`no_heading_group_multi_source_fold`,
  blocking iff any contributor is undated) makes the latent→live
  transition visible. Re-measured against the post-W-30 corpus: still
  latent — one law, one contributing amendment; all 3,089 replays and
  the scan byte-identical; no pin moved. Opened **W-31** for the four
  remaining receiptless failure paths in the fold.

- **2026-08-06 (W-14 applied)** — **No Norway CLI command defaults to
  the stale horizon any more** (`08a199946`). The seven sibling
  commands and the demo derive `--as-of` from
  `no_consolidation_snapshot_date` lazily in `main()`, the W-13 scan
  pattern extended verbatim, with uniform missing-corpus behavior by
  construction and the explicit flag still winning. The census fixed
  four same-class instances beyond the item's list (three standalone
  parsers + one library default) and adjudicated the deliberate
  keepers (bench baseline; the anchor-manifest's frozen gate corpus).
  `no-divergence` without a flag now drills down at the scan's own
  horizon — F-01's last residue closed. No pin moved; scan byte-exact.

- **2026-08-06 (W-30 applied)** — **The part-announcement tail is a
  measured morphology, not an 11-item list — the largest binding
  tranche of the programme, and the one that proves the F-10 pricing
  rule both ways** (`726da4f49`). 556 parts corrected (0 right→wrong),
  +958 ops with op-identity conserved across all 116 changed acts, 64
  first-time index entries, declared-unbound 3,141 → 2,850. The
  bounded-wildcard design was rejected BY MEASUREMENT when it admitted
  substantive prose; the shipped closed-determiner morphology admits
  exactly the construction (2 genuine long-adverbial leads pinned as
  deliberate misses). Scan: one decertification (`2006-06-30-50`,
  contingent `2007-06-29-81` — recoverable) against two repairs
  (`2017-06-16-65` 57 → 13, `2017-06-16-67` 6 → 2) — and the
  re-price's specific decertification prediction was refuted (it
  conflated this family with bulk-rename). Scoreboard
  22/34 at 56 candidates, totals 1252/918/334, conservation exact.
  Nine pins signed off and updated in-place. The +674 `lead_unmatched`
  growth is the re-diagnosis made visible: parts that now resolve
  correctly receipt their unlowerable items instead of hiding them.

- **2026-08-06 (F-10 re-priced)** — **The declared-target gap is down
  to 36.3%, its residual is re-diagnosed as missing lowering grammar
  rather than unread metadata, and the programme learns its pricing
  rule: binding recovery decertifies more than it repairs.**
  Research-only (no product change); artifacts in `.tmp/f10-reprice/`;
  every prior F-10 measurement reproduced exactly before anything new
  was trusted (declared 8,643 invariant; op/binding/entry chains
  reconcile landing-by-landing). Unbound 4,088 → 3,141; receipts
  1,031; the seven landings since W-15 recovered 951 bindings, mostly
  from `lead_unmatched` (2,086 → 1,422) — but the scan-visible proven
  payoff moved 24 → 8 divergences, with 2 laws repaired end-to-end
  (`2005-06-03-34`, `2012-01-27-10` — both predicted by the earlier
  probes) against 4 decertified by newly-bound contingent amenders,
  the cleanest witness ("Anke", 5 proven, its amender STILL unbound)
  now invisible to the scan. Family 1 reaches the scan field-confirmed
  (rename-signature test — the 8-gram test is structurally blind to
  substitution acts); family 3 / W-28 blocks nothing scan-visible.
  Only ONE law today would go fully consistent on binding alone
  (`2001-06-15-73`). Opened **W-30** (`section_intro_markers` tail
  variants, 509 leads / 270 acts, the one bounded W-21-shaped tranche
  left, priced with possible negative scan movement). The
  `lead_unmatched` residue re-files as missing lowering families
  (`innledningen`, `nytt N ledd`, punktum repeal = F-02/W-2,
  `Nåværende … blir …`, `Innholdsfortegnelsen`, inline word-change,
  amendment-of-an-amendment) — future work items, not F-10 binding
  work.

- **2026-08-06 (W-23 applied)** — **The partition now tells one true
  story per bucket: the annex family shares a typed `annex_ceiling`
  lane, and `source_sparse` is exactly F-09 proper** (`92fee2be5`).
  The new bucket routes before `source_signal` on a strict
  ceiling-majority predicate (corpus separation total: members ≥97%,
  everyone else 0%). The ledger's candidate fix (residue through the
  coverage split) was measured and rejected — it relocates the family
  split instead of closing it. Scan-level receipts byte-identical (0
  field diffs across all 57 rows); the signal deliberately untouched,
  its residue counterfactual measured and filed as **W-29**. CLI lanes
  render the residue as the actionable number so 716-divergence rows
  stop reading as the corpus's biggest problem. Landed alongside: the
  four W-18 rule/reason ids (`no_rettelse_lowered`,
  `no_rettelse_not_lowered`, `no_same_act_item_address`,
  `no_unique_item_payload`) were missing from `_NO_RULE_SPECS` —
  `test_every_discovered_rule_id_is_cataloged` had been failing at base
  since W-18 because no affected-ladder since then selected the tools
  shard; found by W-23's full-shard run, cataloged in `77f8b5396`.

- **2026-08-06 (W-25 + W-26 applied)** — **The citation grammar's two
  punctuation blind spots are closed from one constant each, and an
  amending act that bound nothing now lowers 29 audited ops**
  (`38d9bc686`). W-25: `nr\.?` widening across all four citation
  regexes, payload-side included — unscoped because a sweep of every
  text node in every artifact measured 29 wide-only spans, all genuine
  (the mandatory full-date prefix makes a false positive structurally
  impossible). Three misbindings corrected (offentleglova — the W-21
  signed-off cost — plus alternativ-behandling-loven and straffeloven
  leads), the rest of the 9-lead population neutral and audited. W-26:
  the letter-suffix/spaced ordinal strip shared with W-21's
  announcement extractor; the 1891 Finhed act takes its 2 residue ops,
  utleveringsloven drops to its 1 genuine op, and revisorloven's
  consequential act (`2020-11-20-128`, `<strong>`-spaced ordinals)
  enters the index with 29 ops across 8 laws, each audited against its
  own item lead. Net: ops +30/−0, bindings +13/−2 (the 2 are
  correctly-unbound parts whose lowering gaps the misbindings had
  masked; lost pairs 362 → 364 is the same honesty), scan byte-identical
  on all 57 rows, contingent pin 920 → 921 signed off. Opened **W-27**
  (nominative consequential form) and **W-28** (numberless law
  citations) from the sweep's found-not-changed list.

- **2026-08-06 (W-22 applied)** — **The splitter's day-number guard
  tolerates punctuated month tokens, recovering the fourth arity
  casualty the W-19 sweep found** (`2a8302b50`). One-function fix; the
  strip set is `.,`, held to what an instrumented full index build
  actually measured (a 16-character candidate set was differentially
  swept and is corpus-identical). Exactly one index-build split changes
  corpus-wide — skattebetalingsloven's instalment lead, 5 fragments →
  2, emitting its 2 declared sentence ops (n_ops +2/−0) — and the scan
  output is byte-identical to the same sha256. Replay side: 47/91,447
  texts change (0.051%), all mechanical wrong→right joins, 0 ops
  re-addressed, 3 affected scan candidates byte-identical. Guard-tested
  on a real corpus counterexample that mixes repaired and genuine
  boundaries in one subsection. Zero stop conditions, zero pin moves.
  Measured on a post-W-21 base (W-21's 140 new ops flow through the
  splitter) via a local worktree base commit of the W-21 patch.

- **2026-08-06 (W-21 applied)** — **The nominative part announcement
  ("Lov <date> nr. N om X endres slik:") is recognised, and 69 parts of
  the older Lovtidend generation bind to the law their lead names**
  (`b895fc406`). The fix is one extractor at third rank in the
  existing inference — no precedence reorder (W-15's measured 1,343
  intra-part leads keep their winners) — gated on a mandatory amending
  tail (four corpus-measured surfaces; bare `Lov … oppheves.` stays
  out). Sweep of all 9,100 unstructured parts: 67 parts bind from
  nothing, 2 rebind wrong→right, 0 right→wrong, 0 unchanged parts
  disturbed. The W-20/W-21 witness `2009-06-19-74` moves 22 ops to
  straffeloven 2005 — including the six ex-inert text-patches, each
  `match_text` now verified present in straffeloven and absent from
  utleveringsloven, the exact inverse of the W-20 measurement — while
  utleveringsloven keeps its genuine 3. Corpus: ops +140/−0, bindings
  +39/−0, 13 first-time index entries, unresolved-lead diagnostics −140
  exactly 1:1; the 57-law scan is fully byte-identical (straffeloven
  remains `blocked_contingent`, so this is correctness groundwork, not
  scan movement). Signed off: the period-less `nr 16` citation gap
  converting 1 receipted drop into a harm-free misbinding (opened as
  **W-25**, 8 leads corpus-wide), and pins staged 167→170 / contingent
  914→920 / dated 1021→1028 (the 13 first-time entries). The `1 a.`
  ordinal gap behind the witness's 2-op residue opened as **W-26**.

- **2026-08-06 (W-18 applied)** — **F-07's misdiagnosed "editorial"
  correction now replays: typed `Rettelser` errata lower as same-act
  ops, and the corpus count that justified the item repriced honestly**
  (`c8ffa7eb9`). The rule keys on Lovdata's machine-typed
  `gazettenote[data-gazette-note-type=rettelse]` attribute — the only
  non-heuristic anchor — with an anchored single-`§` target grammar
  that rejects the nested advokatloven shape (`§ 73 nr. 7 § 6-7 …`,
  two sections) by construction, a one-item-payload requirement, and
  ops dated by the host act's own commencement so a correction can
  never overwrite genuine later amendments (announcement date rides in
  provenance, apply-inert). Enumeration re-derived over 3,089
  artifacts: 25 carry the block = 12 typed notes (1 lowered — the F-07
  witness, "§ 23" → "§ 2-3" — 7 unmodeled-metadata + 4 Del-scoped
  excluded with typed receipts) + 14 untyped 2003–2011 narrative
  blocks (2 address law text, neither a scan candidate — zero payoff,
  out of domain). Scan: 21/36 → 22/35, `2020-12-18-156` 1 → 0
  divergences, 56/57 rows byte-identical, advokatloven gate
  byte-identical, totals 1513 → 1512 with ceiling unmoved. Index: +1
  op/binding/entry, zero pre-existing entries changed. One signed-off
  pin: `dated` 1020 → 1021 (the witness's first index entry). Opened
  **W-24** (Del→law resolution, the general lowering gap blocking the
  remaining 5 typed errata — incl. the measured warning that lowering
  the eierseksjonsloven one today would decertify a scan candidate via
  its contingent host act).

- **2026-08-06 (W-17 applied)** — **The corpus's dominant divergence
  family — annexed-instrument representation, 72% — is now a typed,
  receipted ceiling, and the scoreboard is readable** (`a41b79af4`).
  Purely additive in the verify lane: `classify_no_annex_ceiling` runs
  AFTER a law's verdict and divergence count are final, annotating rows
  rather than removing them, so `ceiling + unexplained ==
  divergence_count` by construction (the F-05 rule made structural). Two
  mechanical per-row criteria, both spec-cataloged: the annex-address
  shape (non-legislative top chapter label + token-prefixed
  instrument-article section label, shared-prefix agreement for bokmål's
  `rdk`/`rdke`) and the counterpart shape (one-side-only row at the
  canonical address of an annex-witnessed article; keyed on article
  number, which is exactly what reaches the SCE Regulation's 3 truncated
  Article-80 signature rows — the whole 1,126 → 1,129 gap; MISMATCH
  stays unexplained). Capture: 1,129/1,513, the W-6 triage's number
  reproduced exactly — `2018-06-15-38` 714, `2017-06-16-51` 204,
  `2006-06-30-50` 211 — zero rows in the other 54 laws
  (negative-control-pinned). Verdicts 21/36/0 and all 57 pre-existing
  row fields byte-identical; scan and partition reports carry
  `divergence_totals` + `ceiling_rule_counts` conservation receipts; 11
  new tests incl. a corpus pin of every per-law/per-rule count. Found
  alongside: `2006-06-30-50`'s actionable surface is ONE row (§11a(1)
  unlowered forskrift-hjemmel); `sparse_indexed_history` mis-routing
  measured into a contradiction (→ **W-23**); worktree venv drift
  (`pillow`/`pypdfium2` in the main venv but not `pyproject.toml`, fails
  a fresh worktree's `ty` on clean base — infra, unfixed); norway CI
  shard at 427 s vs 21 s (imbalance 359, split candidate).

- **2026-08-05 (W-19 + W-20 applied)** — **The two W-15 casualties are
  repaired: the sentence splitter knows `jfr.`/`m.m.`/`iht.`, and
  citation-less global text-replace leads bind to their own part's law
  instead of dropping** (`4c9e88757`). W-19's corpus sweep found
  exactly 3 splits change, all arity wrong → right, including a third
  recovery not in the ledger (`2022-02-18-5` → forsikringsavtaleloven,
  via `iht.`); single-letter forms measured as legitimate sentence-enders
  and excluded with a guard test; replay-side blast radius 275/91,447
  texts with zero scan rows moved. W-20's five-line `lead_base_id`
  fallback emits 60 ops (4 REBIND / 1 RESTORE / 55 NEW against a pre-W-15
  dump); all three ledger-named acts verified op-by-op, with
  `2005-12-16-118`'s genuine loss returning to `no/lov/2005-04-29-21`.
  One stop condition fired and was signed off: 6 harm-free inert ops on
  `2009-06-19-74` → utleveringsloven, wrong via a pre-existing
  lead-inference defect — opened as **W-21** rather than narrowed here; a
  month-token punctuation defect from the same sweep opened as **W-22**.
  Net: ops +66/−0, bindings +6/−0, lost pairs 361 → 356, partition and
  status distribution unmoved, scan 56/21/35/1508 → 57/21/36/1513 with
  both movements traced; `fully_replayable` pin 56 → 57 (authorized,
  explained in-place).
- **2026-08-02 (W-16 applied)** — **The compare lane's one unbounded
  footnote rule is re-bounded, and the masking it allowed is proven to
  have been latent** (`6bdbb3b12`). The fixer refused to guess: it
  enumerated all 551 alterations the old regex made across 25,742
  compare-lane text units (49 genuine markers / 487 structural headings /
  15 content digits), which ruled out both removal (would add 49 noise
  sites) and punctuation-bounding (fires on nothing — the standalone rule
  already owns that position; the inline rule's "between sentences"
  description was never true of its regex, which predates the named-rule
  refactor). The chosen bounds fire on exactly the 49 genuine markers and
  zero false positives, and are documented in-place with the probe
  numbers. Scan movement: none — double-verified with a four-counter probe
  per law under both regexes, including filtered divergences the flagless
  scan cannot see. So no divergence was actively hidden today; the fix
  converts a latent silent-failure mode (chapter renumbering swallowed on
  both sides — a shape the lane's own `_is_chapter_relocation_pair` family
  proves occurs) into a guaranteed-visible one, at zero measured cost.
  F-05's boundedness claim about the lane's three footnote rules is
  corrected in place, its two genuine cases test-pinned. No pins moved; no
  reviewer pass was spawned — zero corpus movement plus the main session's
  direct re-verification of both directions in the main checkout stood in
  for it.

- **2026-08-02 (W-15 applied)** — **Multi-part amending acts now bind each
  part to its own law, and five laws' worth of cross-contaminated replay
  text is gone** (`779554cb2`). The fix is 40 lines in
  `_iter_unstructured_no_change_groups`: part boundaries are payload
  boundaries, and entering a part re-seeds `active_base_id` from the part's
  own resolved law. The precedence chain is deliberately unchanged — the
  reviewer measured that the triage's implied reorder would regress 1,343
  intra-part law-switch leads across 30 acts (witness
  `no/lovtid/2001-06-15-64` kapII, four law switches in one section). The
  implementer found a mechanism detail the triage missed: the defect fires
  only after a lead that actually consumes payload, which is why part I→II
  often transitioned correctly "by luck". Corpus effect: 893 (part, act)
  pairs newly bound / 5 lost (net 888), bindings +902/−6 with the −6
  inspected op-by-op, n_ops +362, one pure-corruption entry removed
  (`2018-12-20-119` — its only "op" was its own commencement sentence
  overwriting kulturminnelova §28(1)). Independent correctness review:
  APPROVE WITH FINDINGS — every headline number reproduced exactly, an
  18/18 random binding-correctness sample, a 120-law replay sweep with
  divergences −9.8% and zero genuine regressions. The review corrected the
  implementer on three points, all recorded: one of the six lost bindings
  was real (finanstilsynsloven, via the splitter — W-19's second casualty),
  the splitter casualty count is 2 not 1, and the global-text-replace
  branch drops 6 ops for want of a `lead_base_id` fallback (W-20). Scan:
  56 candidates at 21 consistent / 35 divergent (commensurability caveat
  in §2 — two laws genuinely repaired, incl. the exact "+1 consistent law"
  the triage priced for F-10; four departures are honest decertification).
  Both fired stop conditions (scan movement beyond the named victims; the
  two corpus pins 1021→1020 and 58→56) were verified cause-by-cause by the
  reviewer and signed off by the user 2026-08-02; the pins carry their
  explanations in-place.

- **2026-08-02 (W-6 triage complete)** — **Every one of the corpus's 1,573
  provision-level divergences now has a causal family, and the programme's
  priorities inverted.** Research-only (no product change); artifacts in
  `.tmp/w6/triage.{json,md}`; run by a sub-agent, verified spot-wise by the
  main session (the W-16 masking reproduction was re-run in main directly).
  16 families, every assignment carrying a witnessed replay-vs-published
  example, 4.1% honestly unclassified. The dominant family is one the ledger
  did not have: **annexed-instrument representation, 72%** (GDPR inside
  `2018-06-15-38`, a convention inside `2017-06-16-51`, the SCE Regulation
  on both sides of `2006-06-30-50` — the last re-filed out of F-09, where
  its cause attribution was wrong). F-10's scan payoff measured honestly:
  24 proven divergences across 8 laws, one law fully repaired by binding
  alone — confirms the re-priced 8, kills the thousand-divergence reading.
  F-07 was misdiagnosed: the "editorial" correction is a published
  `Rettelser` block in the act's own source bytes (→ W-18 lowering). F-08
  triaged into five clusters incl. the new event-conditioned self-repeal
  family (a §2.3-floor ceiling). Two live bugs found: **W-15, multi-part
  amending acts misbind ops onto the previous part's law** —
  replay-corrupting, ~30% of F-10's unbound mass from one defect — and
  **W-16, the compare lane's inline-footnote rule deletes structural
  numbering** so "Kapittel 2 X" == "Kapittel 3 X" (the masking mode F-05
  forbids). Negative results kept: relocation small (13 pairs), F-05 sized
  exactly as recorded, F-02 not a distinct family,
  `sparse_indexed_history` over-fires (4 laws, not 2). Next: W-15 fix →
  W-16 → W-18 → re-measure F-10.

- **2026-08-02 (W-4 review fixes)** — **The snapshot-derivation helper
  hardened on five same-day code-review findings** (`9b3e5c8e5`).
  The substantive one: `no_consolidation_snapshot_date` read
  `span.observed_from`, but farchive's digest-identity branch extends a
  span's `last_confirmed_at` without touching `observed_from`, so a future
  change-free re-crawl would have frozen the derived horizon at the last
  content change — recreating exactly the F-01 staleness the helper exists
  to prevent (latent today: all 763 spans have `observation_count == 1`).
  Now reads `last_confirmed_at`, with a re-confirmation test that stores
  identical bytes twice and proves the horizon advances (it fails under the
  old code). Also: an farchive holding zero `no://lov/%/current.xml`
  artifacts now raises the named `NOConsolidationSnapshotError`
  (AGENTS.md §1.10) instead of silently borrowing the legacy-directory
  constant; a corpus-gated test makes the fallback constant's licensing
  claim executable (it passed against the real corpus, not skipped); the
  gate's docstring no longer duplicates index.py's offering policy (the
  coupling the `offered_act_ids` rename was meant to sever); and the
  per-locator `history()` materialization became a single-open-span
  `resolve()` — O(1 row) per locator as spans accumulate on future
  re-crawls. Real-corpus derivation unchanged at 2026-07-10. Norway shard
  503 passed / 1 skipped in the fixer worktree.

- **2026-08-02 (W-13 a/c + W-4 hygiene pass)** — **The gate's offered-set
  naming stopped lying, the scan's default date is now derived from the
  corpus, and the one "inert" cleanup turned out not to be**
  (`30cf4df9b`). Implemented by a sub-agent in an isolated worktree off
  `42b898e57`, reviewed and applied by the main session.

  *W-13(a).* `authorize_no_commencement_instruments`'s parameter is now
  `offered_act_ids` (tree-wide, no alias), and its docstring says what is
  true: the gate does not define the offered set and never inspects act
  statuses; production offers `unresolved ∪ staged_delegated`.

  *W-13(c).* The `STAGED_DELEGATED` docstring claims only the shape (ISO
  date(s) + delegated tail) and names the corpus-verified counterexample
  `no/lovtid/2024-06-21-50`, whose only date is a repeal date.

  *W-13(b) stopped — reclassified as not inert.* The implementer measured old
  vs new normalization over all 2466 entries before touching
  `normalize_no_commencement_phrase`: routing it through the widened marker
  tuple changes `no-source --json`'s `normalized_phrase` for exactly one act
  (`no/lovtid/2020-06-23-103`, `dated`, via the unguarded
  `build_no_source_report` site). The batch-04 review premise ("nothing
  routes the new markers through it") was false. `commencement.py` is
  untouched; the item stays open as a decided behavior change (see W-13).

  *W-4.* `no-verify-scan`'s default `--as-of` (was the frozen literal
  2026-03-29, F-01's incommensurable horizon) is now
  `no_consolidation_snapshot_date(data_dir)`: the latest `last_confirmed_at`
  over the `no://lov/%/current.xml` family, read as UTC — which
  independently reproduces the documented 2026-07-10 snapshot date (763
  spans, one observation window; the archive's later 2026-07-31 forskrift
  observations are outside the family and cannot move it). Explicit
  `--as-of` passes through verbatim; legacy directory corpora fall back to
  the documented literal. Tests pin the derivation, the UTC read, the
  fallback, and flag-wins. Field check: a flagless
  `no-verify-scan --limit 200` now lands on 2026-07-10 and reproduces
  58 candidates at 18/40/0 exactly. Seven sibling commands still carry the
  stale default — recorded as W-14, not silently absorbed here.

  *Environment finding, corrected in-session:* the implementer reported the
  three "pre-existing" tools_cli_debug Finland failures gone in its
  worktree and credited the exported env vars — the real mechanism is data
  layout. The tests guard on `data/finlex.farchive` existing relative to
  the repo root of the test file: an agent worktree has NO finlex archive,
  so the whole Finland-corpus family SKIPS (604 passed / 41 skipped,
  green); the main checkout carries a STUB finlex.farchive that passes the
  existence guard and then fails on missing content (statute 2018/301).
  The env vars are irrelevant to these three. Stash-proof rerun at
  `42b898e57`: identical 3 failures on base. So the red stays exactly what
  batches 03/04 recorded — the stub archive — and a worktree's green
  tools_cli_debug is weaker evidence than main's, since ~41 corpus tests
  skip there.

- **2026-08-02 (batch 04, applied)** — **Mixed "DATE, Kongen bestemmer"
  commencement is now a typed, receipted population, and W-5 is decided
  against demotion** (`6fa7b77fd`). `NOCommencementShape`
  (`plain`/`staged_delegated`) is a field on `NOEffectiveDate` and a
  serialized column on the index entry — a label on a *resolved* date,
  orthogonal to `NOEffectiveStatus`, deliberately NOT a new status: a status
  member could not express the 8 acts that are simultaneously staged and
  instrument-authorized. 167 staged acts each carry one non-blocking
  `temporal_recovery` receipt (`no_amendment_index_staged_commencement_collapsed`)
  naming the raw field, the collapsed date, and `date_count`. The population
  is offered to batch 03's authorization gate (`unresolved ∪ staged`), whose
  conjuncts are byte-untouched: exactly 8 staged acts re-date, every one
  EARLIER, to instrument-proved dates; 528 acts now authorized (batch 03's
  520 receipts byte-identical by full JSON compare, verified independently by
  the correctness reviewer), 0 conflicts. The marker vocabulary widened 5 → 7
  with the two measured-absent nynorsk siblings (`kongen avgjer`,
  `departementet fastset`); corpus effect exactly three acts —
  `no/lovtid/2016-06-17-56` and `no/lovtid/2021-04-23-23` (bare `Kongen
  avgjer`: pre-gate classification UNKNOWN → CONTINGENT; the latter was
  already instrument-authorized by batch 03's gate, so only
  `2016-06-17-56`'s final status moves) and `no/lovtid/2020-06-23-103`
  (`departementet fastset` beside three dates: unremarked DATED → staged).
  Status distribution moved 1029/913/520/3/1 → 1021 dated / 914 contingent /
  528 instrument_authorized / 2 unknown / 1 immediate; all 58 scan rows
  byte-identical at 18/40/0; commencement-blocked laws stayed 179.

  *Contract deviation, signed off.* stopCondition 1 ("mixed-act count not
  exactly 166") literally fired: requirement 3's 166 was written against the
  pre-widening marker vocabulary while requirement 5 mandated the widening
  that preflight fact 12 already predicted would add `2020-06-23-103`. The
  correctness reviewer reproduced the pre-widening state exactly
  (166/913/1021/528/3) by monkeypatching the old tuple — nothing was tuned —
  and both reviewers adjudicated for the implementer. Signed off by the user
  2026-08-02; the frozen contract is left byte-identical and this record is
  the deviation's home. The build-state numbers are 167 staged / 159
  min(dates)-keepers, with 166/158 the pre-widening values.

  *Review pipeline and fixer.* Implementer plus two independent reviewers
  (architecture, correctness) ran in isolated worktrees off frozen baseline
  `31954739d`; both returned APPROVE WITH FINDINGS. The one substantive
  finding was a proven-vacuous test assertion — the "all eight move EARLIER"
  check compared two of the test's own literals and survived a mutated
  2099-12-31 pin — replaced by assertions over corpus values: the displaced
  metadata dates are read back off the staged receipts (emitted before
  authorization, so they keep the collapsed `min(dates)` value), checked
  against the pinned table, and the EARLIER claim is asserted
  receipt-vs-entry. The fixer also corrected stale 166/158 docstring counts
  and added `coerce_no_commencement_shape`
  (mirroring `coerce_quirks_disposition`): `from_dict` now coerces into the
  closed StrEnum — null coerces to PLAIN rather than the string `"None"`, an
  unregistered string fails loud. Also measured and recorded, not changed:
  the offer widening grows the gate's refusal receipts 1120 → 1285 (+165 —
  staged acts offered but uncited by any instrument); the one plausible
  design-leak hypothesis (marker widening moving an act across the
  CONTINGENT/UNKNOWN boundary inside `no_base_replay_status_from_statuses`)
  was tested and its counterfactual measured empty. Doc/naming follow-ups
  recorded as W-13. Norway shard 499 passed / 1 skipped after the fixer;
  full affected ladder run once at apply.

- **2026-08-02 (W-10 closed, fourth red fixed, blind spot closed)** — Three
  landings from the two parallel investigations the W-11 incident triggered.

  *W-10 closed as not-a-defect.* Norway replay was never applying amendments
  in `source_id` order: the shared ordering kernel re-sorts every op by
  `(effective, enacted, source_id, sequence)` before the apply fold, exactly
  as Estonia and Finland do. Proven by experiment — forcing the "corrected"
  collection order flips the two suspect laws' applied sequences while the
  replayed text hashes byte-identical, and the 58-law scan is unchanged at
  18/40/0. The caveat on `no/lov/2010-02-19-5` and `no/lov/2010-06-25-28` is
  lifted; their divergence rows are trustworthy triage evidence. The real
  item behind the scare is staged commencement collapsed to `min(dates)`
  (§2.3 floor), and the one live residual — heading groups folding outside
  the kernel — is now W-12.

  *A fourth silent red fixed* (`88986c876`): `index.py:333` passed the free
  string `'record'` where `QuirksDisposition.RECORD` is required, breaking
  `test_quirks_disposition_enum.py` (shard `core_ir_contracts`) since the same
  2026-07-11 commit as the FW-07 red. Serialized diagnostics proven
  byte-identical (StrEnum), all 1,757 blocked-instrument residuals checked,
  norway shard 489 green.

  *The blind spot itself is closed* (`31954739d`). The full inventory
  measured **24 tree-wide hygiene tests** whose scan roots exceed their home
  shard's scope — 23 unreachable from any Norway ladder, and the 24th
  (`test_no_semantic_notes_reads.py`, wildcard-owned by `norway`) blind for
  every *other* jurisdiction. All 24 are hermetic; their home shards are not
  (Finland corpus reds), so `ci_sharded.sh` now runs the FILES in a new
  always-run stage 6/8 whenever any affected path is under `src/lawvm/`
  (~100-105s at `-n 4`), with `TREE_WIDE_HYGIENE_TESTS` in
  `scripts/test_shard.py` as the single source of truth, a `hygiene-files`
  subcommand, and guard tests in `test_ci_shards.py`. Negative-proven: the
  quirks free string reintroduced makes a Norway-only ladder fail at the
  hygiene stage in ~100s, before the seven-minute shard. Maintenance rule
  lives on the constant: a new tree-wide ratchet must add itself to the list.

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
