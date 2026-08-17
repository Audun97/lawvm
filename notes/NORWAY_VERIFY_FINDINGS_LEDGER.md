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
| **2026-07-10, after W-39 (58 candidates; see note)** | **23** | **35** | 0 |
| **2026-07-10, after W-47 (65 candidates; see note)** | **25** | **40** | 0 |
| **2026-07-10, after W-53 (73 candidates; see note)** | **29** | **44** | 0 |
| **2026-08-11, after W-73 (76 candidates; see note)** | **29** | **47** | 0 |
| **2026-08-12, after W-66 (76 candidates, unmoved)** | **29** | **47** | 0 |
| **2026-08-12, after W-70 (76 candidates, unmoved)** | **29** | **47** | 0 |

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

W-39 note: the candidate set GROWS for the first time, 56 → 58 —
`2001-01-05-1` repairs 81 → 0 and goes CONSISTENT (F-09's former
headline law), while part-scoped commencement authorization unblocks
two entrants: `2012-12-14-81` at 97 (93 annex-shaped rows → W-40) and
`2019-06-21-63` at 7. Nothing leaves. Totals `total=1212 (ceiling=918,
unexplained=294)` — the unexplained rise is new coverage, not
regression (−81 + 97 + 7); 55 of the 56 prior rows byte-identical.

W-40 note (verdicts unmoved, so no new scoreboard row): the 1,212
divergences now read `total=1212 (ceiling=1011, unexplained=201)` —
the nested (compound sub-chapter) annex encoding typed under its own
rule id (`ceiling_rule_counts` `{address: 918, nested: 93}`).
`2012-12-14-81` reads 97 = 93 ceiling + 4 unexplained and its
partition bucket moves `source_sparse` → `annex_ceiling`; every row's
address and type stayed byte-identical — W-40 types rows, it moves
nothing.

W-43 note (verdicts unmoved, so no new scoreboard row): totals now
`total=1208 (ceiling=1011, unexplained=197)` — the four rows that
close were `2012-12-14-81`'s own §§ 1-4, fabricated by the top-level
parse either/or (W-42's finding), so total and unexplained drop by
the same 4 and the law is wholly ceiling at 93/93. Corpus-wide the
merged walk recovers 103 consolidation sections (16 laws) and 48
replay-base sections (4 laws) as latent coverage; only this law is
currently in the candidate set, and the candidate set provably
cannot move from this fix.

W-47 note: the candidate set grows 58 → 65 — seven entrants via the
multi-part commencement route, 0 repairs, 0 decertifications, 0
pre-existing rows moved. Two entrants arrive already CONSISTENT
(`2022-06-17-56`, `2024-12-20-96` — a series first); the other five:
`2010-06-04-21` (3, replay_defect), `2011-06-24-39` (5,
replay_defect), `2018-04-20-7` (14, untouched_drift),
`2004-12-17-101` (26, replay_defect), `2013-04-12-13` (191,
source_sparse — the F-09 family's next big target). Totals
`total=1447 (ceiling=1011, unexplained=436)` — the +239 is entirely
entrant rows, conservation exact, ceiling untouched.

W-53 note: the candidate set grows 65 → 73 — eight entrants via the
widened whole-act route, 0 repairs, 0 decertifications, all 65
pre-existing rows byte-identical, `base_ids` changed on 0 of 2,559
entries. Four entrants arrive CONSISTENT (`2004-12-17-99` at 124 ops
— the W-52 fix's showcase — `2016-12-16-92`, `2017-04-28-23`,
`2021-06-18-136`); four divergent: `2001-06-15-75` (15, 0 ceiling),
`2004-03-26-17` (1), `2015-05-12-27` (7), `2020-04-17-29` (15) —
buckets replay_defect +3, untouched_drift +1. The error column stays
ZERO (W-52 cleared the only would-be error before the widening
landed). Totals `total=1485 (ceiling=1011, unexplained=474)` — the
+38 entirely entrant rows, ceiling untouched, conservation exact.

W-73 note (row added at the W-74 records commit — the table had gone
two landings stale): the candidate set grows 73 → 76 via the
title-cited commencement reader (`ff202148c`) — three entrants, none
leaves, all 73 pre-existing rows byte-identical. All three enter
divergent (buckets replay_defect +2, untouched_drift +1), totals
`total=1512 (ceiling=1011, unexplained=501)` — the +27 entirely
entrant rows, honest exposure, ceiling untouched. Between this row
and the table's next reader: the W-67/W-74 composed landing
(`cf751dd2b`) closed 11 rows corpus-wide, 2 of them candidate rows
(`total=1510, unexplained=499`), verdicts unmoved at 29/47/0.

W-70 note (verdicts unmoved, so the row above repeats 29/47/0): the
candidate set is 76 element for element and exactly ONE law moves —
karanteneloven `no/lov/2015-06-19-70`, 14 → 12, the two rows W-72(c)
attributed to this item, 0 opened, the other 75 laws byte-identical.
Totals `total=1489 (ceiling=1011, unexplained=478)`; ceiling
untouched.

W-69a note (verdicts again unmoved at 29/47/0, candidates 76): the
first row movement this programme has bought by ADDING a production
rather than refusing one. Exactly TWO laws move and both were named
in advance by W-69's design pass — karanteneloven
`no/lov/2015-06-19-70` 12 → 8 and `no/lov/2020-04-17-29` 15 → 8 —
**11 unexplained rows closed, 0 opened**, the other 74 laws
byte-identical. Totals `total=1478 (ceiling=1011, unexplained=467)`;
ceiling untouched. The one row the matching rule deliberately leaves
open (karanteneloven `§ 20 fjerde ledd`, a genitive) is counted here
as still open, which is the point of taking whole-word matching.

W-69b note (verdicts unmoved at 29/47/0, candidates 76): the same
two design-named laws move and no other — karanteneloven
`no/lov/2015-06-19-70` 8 → 2 and `no/lov/2020-04-17-29` 8 → 7 —
**7 unexplained rows closed, 0 opened**, the other 74 laws
byte-identical. Totals `total=1471 (ceiling=1011, unexplained=460)`;
ceiling untouched. The design priced this phase at 8 rows; the
eighth (karanteneloven `§ 17 første ledd`) holds two sentence
addresses of which one refuses `inflection_only` on a capitalised
`Tilsettingsmyndigheten`, so that row correctly stays open — the
whole-word/exact-case trade costing what it says it costs.

W-66c note (the scan's shape changes for the first time since W-73,
in BOTH directions): candidates **76 → 75** and scoreboard **29/47/0
→ 29/46/0** — the punktum-repeal production gives
`no/lovtid/2013-01-11-3` ("fra den tid Kongen bestemmer") its first
lowered ops, and the contingent binding that was always in the
source downgrades two candidate bases to `blocked_contingent`:
`no/lov/2011-06-24-39` departs with its 5 rows and
`no/lov/2010-06-04-21` with 1, while `no/lov/2009-05-15-28` enters
with 2. W-73's mechanism running backwards; honest exposure, not
coverage. On the STAYING candidates **3 rows genuinely close**, all
named in advance by the coincidence join: `2001-06-15-75` § 31
tredje ledd, `2016-06-17-29` § 5 første ledd, and the witness
`2021-06-18-121` § 20 første ledd (which returns to
`untouched_drift`, closing W-66b's loop). 0 opened. Totals
`total=1464 (ceiling=1011, unexplained=453)`; ceiling untouched.

W-77 note (candidates hold at 75, scoreboard holds at 29/46/0, but
the pinned MEMBERSHIP swaps two laws): the item-depth payload
production closes **2 rows** — `no/lov/2004-03-26-17` § 2/1/g
(OPS_MISSING, the row the coincidence join projected) goes 1 → 0
and the law moves to `consistent`, and `no/lov/2012-01-27-9` goes
5 → 4 (OPS_MISSING) — and **opens 1**, adjudicated deliberate:
klimaloven `no/lov/2017-06-16-60` § 7 andre ledd bokstav e,
CONSOLIDATED_MISSING, moves the law `consistent → replay_defect`.
`no/lovtid/2021-06-18-129` commands the bokstav-e insertion at § 6
andre ledd with "trer i kraft straks", the write lands verbatim and
the 2025 §§ 4–7 renumber carries it to § 7 — but Lovdata's archived
consolidation carries only a–d. An honest report of a gap between
the instrument and the consolidation, not a defect in the lowering.
Totals `total=1463 (ceiling=1011, unexplained=452)`; ceiling
untouched.

W-79 note (candidates hold at 75, scoreboard holds at 29/46/0;
three candidate laws' rows move, all read directly off the
invariant withdrawing wrong text): **12 rows close, 4 open
deliberately — net unexplained 452 → 444.** `no/lov/2010-06-25-28`
26 → 24: the CONSOLIDATED_MISSING at § 6 closes (the "row" was the
announcement `Nytt kapittel 2 etter § 6 skal lyde:` sitting in the
statute) and § 6/1's OPS_MISSING closes as the real
forskrifts-hjemmel returns and matches Lovdata verbatim.
`no/lov/2017-05-22-29` 6 → 3 and `no/lov/2017-05-22-30` 6 → 3
(same instrument `2023-06-20-82`): five rows close each as
withdrawn announcement-writes give way to real law; **two open
each as MISMATCH, adjudicated deliberate** — the `Noverande §§ 29,
30 og 31 blir …` relabel is still not lowered (sized at this
landing as the section-level relabel-announcement family), so our
§§ 30/31 hold the statute's true text at its pre-relabel label
while the consolidation holds it one label up. "Right text, old
label" strictly beats the row it replaces ("nothing here", with
the amendment's own prose in § 29). Both laws re-bucket
`replay_defect → untouched_drift`. Totals `total=1455
(ceiling=1011, unexplained=444)`; ceiling untouched.

W-84 note (the first VERDICT-column movement since the scan began:
29/46/0 → **30/45/0**): klimaloven `no/lov/2017-06-16-60`'s single
row — the CONSOLIDATED_MISSING at § 7/2/e that W-77 opened
deliberately and W-83 adjudicated — **closes**, and the law moves
`replay_defect → consistent`, because the never-enacted bokstav e
is out of the replay: the superseded 2021 announcement is now
suppressed under its `utgått` mark and the rectified re-announcement
(amending only §§ 3 and 4) is lowered in its place with the act's
own identity and dates. Exactly 1 of 75 rows moves; candidates 75
identical. Totals `total=1454 (ceiling=1011, unexplained=443)`;
ceiling untouched.

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
39. **W-39 (re-enactment lead tail + part-scoped commencement):** DONE
   (`36cc59eac`, 2026-08-07). Both halves landed together, their
   inseparability PROVEN both ways (base grafter → the instrument
   verdicts `endrer_law_not_in_part_map`; lead fix alone → 22 ops on a
   `Kongen bestemmer.` act = decertification). **(i)** The collective
   `I lov … skal følgende bestemmelser|paragrafer lyde:` lead lowers as
   a declared END STATE: all RENUMBERs sequence BEFORE all payloads
   (the witness renumbers sections its payloads overwrite — document
   order would corrupt; the chosen order reproduces the published
   consolidation exactly), under all-or-nothing part guards (closed
   member set, disjoint/distinct address sets, every
   `futureLegalArticle` yields a payload, marker label = data-name) —
   one failure refuses the whole part with a typed receipt and hands
   it back to the ordinary walk. Of the 4 family acts: witness lowered
   (22 ops), `2021-06-11-60` lowered (3 ops), `2006-06-30-41` REFUSED
   (bare-address members, cost measured zero), `2009-05-08-27` out of
   scope (chapter-scope, not a part lead). **(ii)** Part-scoped
   authorization is per `(act, base law)` in a NEW
   `part_scoped_effective_dates` field — deliberately NOT act-level
   status (an act with parts commencing 2011 and 2023 has no single
   date; `instrument_authorized` stays 542). Sweep: 551
   Delvis/Delt-style instruments → 1,921 (instrument, act) pairs → 246
   exact `Endrer`→part matches → **123 authorizations** after the
   added-beyond-the-brief `whole_part_scope` conjunct (the Endrer match
   proves WHICH part, not HOW MUCH of it; 109 genuinely narrower
   slices refused → W-41). Soundness probe: 0 of 123 could apply an op
   EARLY; 9 late-in-the-conservative-direction. Joint payoff:
   `2001-01-05-1` **81 → 0, CONSISTENT** — F-09's former headline law
   fully repaired, 4/4 amendments applied. Corpus: +25 ops/+2
   bindings/+1 entry, 0 lost, 0 rebound; declared-target conservation
   exact. Scan signed off 2026-08-07: candidates 56 → 58 (**growth**,
   first time — `2012-12-14-81` enters at 97 [93 annex-shaped rows the
   W-17 classifier doesn't reach at that prefix → W-40] and
   `2019-06-21-63` at 7; NOTHING leaves; neither previously-decertified
   law returns, their blockers have no part instruments); scoreboard
   22/34 → 23/35; totals 1,189 → 1,212 with unexplained 271 → 294 —
   an honest RISE from new coverage. The probe's secondary observation
   (`2009-06-19-74` binds without declaring) remains open — the law
   went consistent regardless, so its §16 op is evidently correct.
40. **W-40 (annex ceiling classifier misses `2012-12-14-81`'s prefix,
   W-17 extension):** DONE (`71d916f1e`, 2026-08-08). The law carries
   regulation (EU) nr. 492/2011 under a SECOND Lovdata annex encoding
   W-17 never saw: not a token chapter of its own but a compound
   sub-chapter of an ordinary host chapter — `chapter:1` ("Forordning")
   holding `chapter:1-1` ("EØS-avtalen vedlegg V punkt 2 …"), the
   regulation's chapters/parts/articles below, and UNPREFIXED article
   labels (`section:a1`), so both halves of
   `_no_annexed_instrument_address` miss every row. New sibling
   matcher `_no_nested_annexed_instrument_address` + third criterion
   `no_verify.ceiling_annexed_instrument_nested_address`, bound to the
   measured shape: ordinary top chapter, second chapter extending the
   host label with `-`, first section an unprefixed article — the
   middle requirement keeps `2006-06-30-50`'s canonical
   `chapter:1/chapter:I/section:a1` rows with the counterpart rule.
   Census over all 1,212 divergence addresses of the 58 candidates:
   93 hits, all in this law, 0 in the other 57, 0 overlap with the
   W-17 typings; `2018-06-15-38`'s GDPR compound sub-chapters
   (`10-3-1`…, 484 rows) are disjoint STRUCTURALLY — the two rules
   demand opposite top-chapter shapes. Deliberate narrowing: the
   nested rule does NOT feed the counterpart `witnessed` map
   (two-address doubling is a measured property of the token encoding
   only). Effect, signed off 2026-08-08: 93 rows unexplained →
   ceiling (`918 → 1,011` / `294 → 201` against an unmoved 1,212,
   `ceiling_rule_counts` `{address: 918, nested: 93}`);
   `2012-12-14-81` reads 97 = 93 + 4; zero verdict, candidate, row or
   index-pin movement. Partition: the law moves `source_sparse` →
   `annex_ceiling`, closing the contradiction W-39 recorded in the pin
   comment by typing the rows rather than re-bucketing (the
   `sparse_indexed_history` signal itself untouched, still 3 laws).
   Ceiling-share floor relaxed `> 0.97` → `> 0.95` (the new member is
   93/97 = 95.9%; descriptive, not the routing predicate — separation
   stays total; consider dropping the constant for the properties
   already asserted separately). The 4 residual rows are the enacting
   act's own §§ 1-4, which the published consolidation does not print
   at all → W-42.
41. **W-41 (partial-part commencement slices, sized surface):** DONE
   (design pass, RESEARCH-ONLY, 2026-08-08; artifacts `.tmp/w41/`,
   no product change). Verdict: **no family implemented — under
   every sound model the whole surface is worth ZERO candidates**
   (+1 only under a deliberately unsound "date every sliced binding
   wholesale" upper bound: `2016-06-17-73`; of the 56 slice-touched
   laws, 55 still carry contingent blockers afterwards). Divergence
   movement is structurally zero and F-10 decert risk nil (the part
   route sets dates, never `base_ids`). Corrections to the record:
   the surface is **121 pairs, not 109** (W-39's sweep regex
   differed from the shipped one), and W-39's shipped
   `_COMMENCED_SECTION_RE` has an **ordinal-swallowing defect** —
   the trailing optional letter eats the first letter of a following
   Norwegian ordinal (`§ 2-7 fjerde ledd` → `2-7f`), corrupting 98
   of 244 compared pairs; direction conservative, 0 corrupted rows
   authorize, W-39's witness reads identically — but it masked the
   real shape (corrected census: 74 genuine subsets, 22 overlap, 15
   equal incl. 13 whole-part matches hidden by corruption, 10
   disjoint, 2 superset). Why no model: 88% of slices qualify to
   ledd/punktum granularity while ops are section-granular (§4(a)
   over-claim, P2 probe: 6 of 9 new grants); slices are prose with
   no closed member set for an all-or-nothing guard; and per-op
   dates need a new plane through index/replay/inventory (the first
   lane to split a binding). **The naive reader fix alone FIRES the
   0-early probe** (smittevernloven: `2021-06-18-1976` "§ 8-1 andre
   ledd" would authorize 2021-06-18, sibling commences §4a-1 of the
   same part 13 days later); the only both-probe-clean combination
   nets zero coverage, loses one authorization, adds one blocking
   staged-commencement conflict, churns ~98 label pins — not
   proposed. Sound-but-nil alternative recorded: model B slice
   union (all named sections together cover the part → existing slot
   at max(dates)), reaches 8/82 bindings, moves nothing. Lane
   ceiling census: **`endrer_spans_multiple_parts` is worth +17
   candidates — 17× this item** → W-47; the slice-lane hygiene
   bundle (reader fix NEVER alone) → W-48. Also from W-39, small,
   still open: `2006-06-30-41`'s bare-address collective members;
   the `Lovens tittel:` restatement recognized-not-applied; the
   spaced `data-name` heading-label artefact (939 base-state ops).
42. **W-42 (`2012-12-14-81`'s consolidation prints only the annex —
   parse defect or source shape?):** DONE (probe, research-only,
   2026-08-08; artifacts `.tmp/w42/`). Verdict: **(a) PARSE DEFECT,
   recurring.** The raw source (`nl/nl-20121214-081.xml`, sha256
   `248e60fa…0615`) DOES carry the act's §§ 1-4, as
   `article.legalArticle` SIBLINGS of the annex `section.section` —
   but `parse_no_statute`'s top-level walk (`grafter.py:944`) makes
   the article walk an `if not body_children:` FALLBACK to the
   chapter walk, so a document that is both chapter- and
   article-structured loses every top-level article. The nested
   `_parse_container` already interleaves both kinds in document
   order; only the top level has the either/or. Census over 763
   stored consolidations: 23 mixed (all `A…A S…S`, articles first), 7
   harmless (their lone section parses to `None`, the fallback fires
   anyway), **16 lose 103 top-level sections** (counterfactual
   full-corpus diff: 103 gained, 0 lost, all strict supersets, other
   747 byte-identical). The replay lane is affected too
   (`replay.py:294` uses the same parser): 4 laws / 48 sections over
   3,089 originals. `2012-12-14-81`'s original is articles-only —
   which is exactly why its rows read CONSOLIDATED_MISSING (replay
   right, consolidation wrong). Scan impact today: only this law is a
   candidate (candidacy comes from `build_no_inventory`, which never
   calls `parse_no_statute`, so the fix cannot move the candidate
   set); measured counterfactual scan 97 → 93 unexplained, exactly
   the 4 rows; the other 102 recovered sections are latent coverage
   for the 13 no-status and 3 blocked laws when they enter. Fix →
   W-43.
43. **W-43 (merge `parse_no_statute`'s top-level body walk, W-42
   fix):** DONE (`609fd7ce8`, 2026-08-08). The either/or at
   `grafter.py:937-950` replaced with one order-preserving pass over
   `_direct_children(main)` dispatching `section.section →
   _parse_container` / `article.legalArticle → _parse_section` — the
   top level now looks exactly like `_parse_container` one level
   down; the `None`-on-heading-only guard untouched. Every W-42
   probe prediction reproduced as an ACTUAL measurement on the first
   try, nothing tuned: current lane 16 laws / 103 sections gained /
   0 lost / all strict supersets / 747 byte-identical (per-law table
   row-for-row identical to the probe's); replay lane 4 laws / 48
   sections / 0 lost / 3,085 byte-identical; scan moves exactly
   `2012-12-14-81` 97 = 93 + 4 → 93 = 93 + 0 (wholly ceiling),
   totals 1,212 → 1,208 with unexplained 201 → 197, ceiling unmoved
   at 1,011, verdicts 23/35/0 and all index pins unmoved (34/34,
   none edited — confirmed empirically and by the strict-superset
   argument: the one indirect candidacy path,
   `_has_operative_content`, can only go False→True and all 16
   changed laws already had non-empty bodies). Two new order tests
   incl. the hypothetical `S…A` mirror that separates the merged
   pass from "run both walks unconditionally". Ceiling-share floor
   deliberately NOT tightened back (0.95 stays a floor to clear, not
   a running record; smallest member is `2017-06-16-51` at 97.1%
   again). Signed off 2026-08-08. Notes: 102 of the 103 recovered
   sections are latent coverage for 15 laws outside today's scan —
   they now enter parsed correctly instead of carrying a fabricated
   CONSOLIDATED_MISSING block; two-lane symmetry (both lanes
   recovering the same sections) is a property of this corpus, not
   enforced — a cheap guard would pin that both lanes parse through
   the same walk. Follow-up census → W-44.
44. **W-44 (laws with a replayable original but NO stored
   consolidation are invisible to verify):** DONE (probe,
   research-only, 2026-08-08; artifacts `.tmp/w44/`). Verdict:
   **(b) typed receipt — NOT an acquisition item; zero demonstrated
   gaps.** Census: 3,089 stored originals (= the Lovtidend 2001–2026
   window, id set byte-identical to the amendment lane) vs 763
   stored consolidations; **2,642** originals have no consolidation
   (the converse 316 is entirely pre-2001 — the known boundary,
   already reported by `no-missing-base`; W-44 is its unreported
   mirror). Snapshot completeness proven locally: of 308 laws
   amended by a 2025+ act, 24 lack consolidations and ALL 24
   adjudicate (unnumbered-ref artifacts, repeal-manifest-named, or
   amending acts); the snapshot even carries 115 amending-act
   consolidations, behaving like a complete alle-gjeldende-lover
   listing. Families: **2,514 amending acts** (95.2%, absorbed into
   targets on commencement), **40 temporary** (built-in expiry),
   **25 wage-board** (self-repeal on Rikslønnsnemnda ruling),
   **63 substantive** — of which 50 are named in another act's
   structural repeal manifest (`Følgjande lover blir oppheva:`,
   read structurally; precision control: of 332 manifest-named laws
   only 24 still have consolidations, all staged repeals) and 13
   are spent/absorbed/never-commenced one-offs, each adjudicated by
   hand. The W-43 seed `2005-06-03-33` is diskrimineringsloven
   (2005), repealed by `2013-06-21-60` — no fetch recovers a
   current text. Scan relation: the block is structural
   (`load_no_current_law_ids` walks stored consolidations only, so
   the family is absent from the inventory universe, no denominator,
   no bucket); counterfactual ceiling if all had consolidations:
   +55 would-be candidates (58 → 113), +35 blocked_contingent,
   2,552 unchanged. The only locally-undecidable sliver: Lovdata
   consolidates ~4% of amending acts, so of the 29 would-be-
   candidate amending acts a fetch would predict ~1 hit. Receipt
   item → W-45.
45. **W-45 (typed no-consolidation receipt, W-44 recommendation,
   size S):** DONE (`ef2a3d9c9`, 2026-08-08). The family is a live,
   runtime-computed receipt: `build_no_no_consolidation_report` in
   `inventory.py` (rows: base_id, title, family, would_be_status,
   repealed_by, amendments; family by title shape, repealed_by via
   the structural manifest reader, all regexes classifier-wrapped
   with ratchet waivers), `lawvm no-no-consolidation` mirroring
   `no_missing_base.py` (+`--family`), inventory counters, and an
   `unverifiable` sibling BESIDE `partitions` (a sixth bucket would
   be a row shape that lies). Runtime reconciliation with the W-44
   probe: **14/14 MATCH** incl. both cross-tabs. **STOP-1 fired and
   was resolved by measurement, not tuning:** the item's stated
   input (`… - current_law_ids`) gave 2,752, not 2,642 — the probe's
   universe is STORED ARTIFACTS (763, new
   `load_no_stored_consolidation_law_ids`), while `current_law_ids`
   is the operative-content-filtered 645; the 110-law delta is
   amending acts whose consolidation is bare change instructions, so
   counting them "no consolidation" would be a false receipt. Both
   universes surfaced side by side; signed off 2026-08-08. Deviation
   from item text, signed off with it: SIX counters (the five plus
   `stored_consolidations`, load-bearing per STOP-1). The tripwire
   pins the 13 ids BY ID, not count (a new id is the alarm; an id
   leaving is benign; never re-derive the list). Catalog:
   `no_stored_consolidation` added to `_NON_RULE_LITERALS` (names a
   population, not a rule); a second collision renamed away. Two
   synthetic partition tests monkeypatch the census out (stub index
   would crash it), all pre-existing asserts byte-identical; zero
   scan movement (58 / 23-35-0 / 1,208-1,011-197). Cost: inventory
   build 48s → 51s. Still open from W-44: the optional XS Lovdata
   live-probe (29 ids now runtime-obtainable via
   `no-no-consolidation --family amending_act --json`). Noted for CI
   hygiene: the norway shard is the long pole (745s vs 195s avg) and
   W-45 adds ~60s of corpus pins to it — split candidate.
46. **W-46 (surface the no-consolidation census in `no-frontier`,
   XS, presentation only):** DONE (`36c7af021`, 2026-08-08). An
   `unverifiable_census` section in both output modes, read straight
   off `build_no_verify_partition`'s W-45 sibling (a call the tool
   already pays for) and `inventory.to_dict()`'s universe pair — the
   load-bearing choice is that the census CANNOT disagree with the
   partition printed beside it, because it is the same object. Text
   mode prints three lines (census, by-family, universe pair)
   between the partition and the queues; JSON gains the key between
   `consistency_partition` and `active_consistency_lane`. Both
   universes printed because substituting 645 for 763 would inflate
   the amending family to 2,624 and the ceiling to 64. 39 product
   lines / 51 test lines; one existing test's partition stub grew
   the new key (addition-only, the stub's own stated convention, all
   10 pre-existing asserts unchanged); indexed `["unverifiable"]`
   directly, matching the tool's in-process composition (unlike
   `no-verify-partition`, which reads saved JSON and `.get`s).
   Reviewer edit at apply: the universe-gap comment softened to what
   W-45 measured (110 of the 118 proven amending acts, not all 118).
   No stop conditions, no scan or pin movement.
47. **W-47 (`endrer_spans_multiple_parts`, the lane's real lever):**
   DONE (`47e49f0ae`, 2026-08-08). The design pass settled the
   structural question both ways: the Endrer header IS a faithful
   part→law map (168/168, implied by injectivity + one-law-per-part
   evidence) but is NOT a statement of instrument scope — eleven
   proven counterexamples (e.g. `2012-12-07-1149` "Loven del I trer
   i kraft" under a I+II header), so forgiving on the header alone
   is unsound and W-41's +17 was a wholesale upper bound, not a
   target. What licenses a grant is the instrument's OWN text
   commencing the whole act — then dating the header's parts is a
   strict subset claim. Shape census: S1-A whole-act text (71 pairs)
   IMPLEMENTED; S1-B/C/D part-naming texts (24, 11 proven narrower,
   ~13 agreeing part-lists → W-49) REFUSED typed; S3 section-naming
   (73) REFUSED — the multi-part analogue of W-41's empty slice
   surface (0/73 reach section-set equality). Guard G1∧G2
   (`_SUBDIVISION_SCOPE_RE` negative half — subsumes W-48(iv)'s
   fence here — ∧ act-level clause subject positive half): 71
   accepted, 0 of the 11 disagreements leak; the route is
   corruption-IMMUNE (G1 refuses any `§`, and label emission
   requires one, so `WHOLE_PART_SCOPE_PER_PART` is unreachable on
   the accept path — verified 0 labels under either reader for all
   70 granted instruments; 1 pair left on the table for W-48).
   **P1 FIRED at 2 EARLY** (`2019-12-06-76` del I: a later
   instrument REVOKED the commencement and re-issued 15 months
   later) — closed by promoting the probe to the
   `ACT_HAS_NO_LATER_INSTRUMENT` conjunct (any later instrument
   citing the act refutes whole-act commencement), cost 2 grants /
   1 act / 0 candidates; shipped P1 over all 383 grants: 0 EARLY,
   10 late-conservative; P2 = 0 (measured, vacuous by construction).
   260 multi-part grants over 70 acts (29 inert grants pinned — a
   part resolving a law the act never binds dates nothing; 2 of
   W-39's 123 already were; decide someday whether they should
   receipt at all). Scan signed off 2026-08-08: 58 → 65, 25/40/0,
   totals 1,208 → 1,447 with unexplained 197 → 436 (all entrant
   rows, ceiling unmoved, conservation exact), 7 entrants / 0
   repairs / 0 decerts (F-10: dates only, asserted three ways).
   Ladder lessons recorded: the catalog discovery scrapes ANY
   `no_`-prefixed literal (conjunct VALUES included — renamed
   `act_has_no_later_instrument`), and each semantic-regex use-site
   needs its own `# lawvm-regex:` waiver line. Also noted:
   `_WHOLE_ACT_RE`'s two mechanical misses (anchored fullmatch,
   narrow verb set) are why 72 genuine whole-act commencements land
   in the part lane → W-50.
48. **W-48 (slice-lane hygiene bundle — the reader fix must NEVER
   land alone):** four interlocking pieces from the W-41 design
   pass, to land together or not at all: (i) fix
   `_COMMENCED_SECTION_RE`'s ordinal swallowing (correct pattern
   with non-ASCII-aware lookahead in `.tmp/w41/s5_label_fix2.py` —
   an ASCII lookahead still corrupts `første`); (ii) the ledd
   conjunct refusing sub-section-qualified pairs (the §4(a)
   over-claim guard, P2); (iii) a staged part-commencement model —
   one date per (act, part, law) currently reads two slices at two
   dates as a blocking contradiction (finansforetaksloven part I:
   `2021-04-23-1251` @2021-07-01 vs `2025-06-24-1204` @2025-08-01);
   (iv) typed refusals for negative/exception instruments (`settes
   ikke i kraft`, `med unntak av`, `for så vidt gjelder`) — today
   harmless only because corrupted labels refuse them by accident,
   dangerous the day the reader improves. Measured effect of the
   clean combination: authorizations 123 → 123 (+`2021-06-18-92`/I,
   −`2021-04-23-22`/I), P1 EARLY 0, zero coverage change, ~98
   instruments' serialized-label pin churn (`guarded_option.json`
   enumerates). Low priority on its own numbers; prerequisite for
   ever revisiting the slice surface, and (iv) is a safety fence.
   Also noted: `2016-06-17-73` is the single law the slice surface
   could unblock — if wanted, a targeted one-off far below the cost
   of a slice model. W-47 datum: the reader fix unlocks exactly 1
   additional multi-part pair (`2017-06-02-745` → `2016-06-17-45`,
   the `2-7a`/`2-7` swallow).
49. **W-49 (named-part-list instruments):** DONE (`f241d8975`,
   2026-08-08). Gated in at zero candidate payoff for lane
   completeness: 33 grants over 10 acts, no status/candidate/
   divergence movement, and the per-part refutation semantics landed
   as the tested asset W-48(iii) and any slice revisit will need.
   Surface measured 12 pairs (the "~13"; a naive covers-check says
   55 but 43 are `§`-carrying slice shapes — W-41's surface). Reader:
   a ~40-line tokenizer + scanner, NO regex for the grammar (one
   refusing hazard regex + one verb-count check); part vocabulary
   closed (`del`/`romertall` morphology; `avsnitt` deliberately
   excluded as ambiguous — `2013-02-01-130` is the measuring pair if
   ever widened); romertall tokens case-sensitive and canonically
   re-rendered (keeps the preposition `i` and `UCITS V` out); the
   safety asymmetry is that under-reading shrinks the claim while
   the first unknown token closes the list, and dangling/descending
   ranges refuse outright. All 11 W-47 disagreements refused, 0
   leaks. **Refutation semantics (the design crux):**
   `LATER_INSTRUMENTS_NAME_OTHER_PARTS` — every strictly later
   instrument on the act must be provably about OTHER parts under
   BOTH witnesses: structural (its own Endrer header's parts,
   disjoint) AND textual (this same reader over its text, disjoint);
   an unreadable text bounds nothing and refutes. Neither witness is
   sound alone — textual-only gains one pair (`2017-09-01-1328`)
   that FIRES P1 (recorded as the near-miss); act-global (W-47's)
   wrongly refuses the staged pattern (2 pairs). W-47's revocation
   witness still caught in list form, pinned both ways. Corruption
   immunity by construction: the reader refuses any `§`, so no pair
   reaching the route has a section label. P1 zero-early over ALL
   416 shipped grants (12 late-conservative); P2 = 0. Routes
   provably disjoint (whole-act reader refuses `del`/`romertall`;
   this reader requires one), pinned. Pin package: exactly one edit,
   inert grants 29 → 31 (signed off 2026-08-08; per-route splits
   pinned separately). CI green on the FIRST run — the W-47 ladder
   lessons (no `no_` conjunct values, per-use-site waivers) landed
   as briefed. Still open from the follow-ups: the 2 reader-clean
   pairs refused on section-naming later siblings (`2012-01-20-36`,
   `2017-09-01-1328`) — W-48's slice reader could serve as a third
   disjointness witness for ~5 more grants at 0 candidates; inert
   population now 31 across three routes, cleanup question
   unchanged.
50. **W-50 (size the `_WHOLE_ACT_RE` widening):** DONE (sizing pass,
   RESEARCH-ONLY, 2026-08-09; artifacts `.tmp/w50/`, no product
   change). **The recommended variant (`route5`) PASSES all four
   gate criteria but is blocked on two discovered prerequisites,
   each bigger than the widening.** Sizing corrections: the surface
   is **518 mechanical misses / 449 offered acts, 7× the item's
   estimate** (swept all 2,365 commencement instruments; the
   ledger's three miss classes did not survive measurement — 0
   title-prefix hits; what breaks is the SUBJECT: 317 cited-act
   subjects, 181 adjacent subjects with verbs outside the anchored
   set; `gjelder fra`/`skal gjelde`/nynorsk forms). Five variants
   built end-to-end; `route5` (shipped ∪ bounded new route over the
   498 single-block misses, with act-level
   `ACT_HAS_NO_LATER_INSTRUMENT`): 428 acts move, ALL forward
   (423 contingent→instrument_authorized, 5 dated→ re-dated all
   LATER); 8 laws blocked_contingent→fully_replayable, candidates
   65 → 73, scoreboard 25/40/0 → 28/44/1, totals 1,447 → 1,485
   (ceiling unmoved, +38 all-entrant); **decert exposure ZERO and
   structurally so** (resolution is monotone; the lane writes dates,
   never base_ids; 0 of the 65 base rows change byte-for-byte).
   Route interaction: absorbs 346 of 416 part grants — 344
   date-identical, 2 later-conservative, scope inflation just 2
   acts / 4 bindings, each proven sound per binding. The two
   blockers: **(1) the SHIPPED whole-act route is already in
   act-level P1 breach** → W-51; **(2) the counterfactual surfaces
   the programme's first `error` verdict** (klimakvoteloven
   `2004-12-17-99`, renumber/observed-write audit violation — an
   impeccable date exposing a replay-engine defect) → W-52. Also
   recorded: `_CITED_ACT_SUBJECT_RE`'s 400-char gap swallows
   qualifiers (witness `2001-05-04-474`, inert today; fence priced
   and rejected — false-positives on act titles); rejected variants
   priced (`reader` admits delegation/forskrift-amendment texts;
   `single` fires P1 on `2019-12-06-76` at act level — strictly
   worse than the part grant W-47 refused); full implementation
   note + expected pin package written for the eventual landing →
   W-53. Deliberate-decision flag for that landing: `route5`
   retires 346 of the 416 part grants.
51. **W-51 (the shipped whole-act route is in act-level P1 breach —
   repair before any widening):** DONE (`7a1ffa41e`, 2026-08-09).
   Three repairs, no fired stop conditions. **(1) Sharpened sibling
   predicate** `_cites_acts_as_hjemmel_only`: a sibling is
   commencement-relevant by DEFAULT and excluded only on a
   two-witness proof of irrelevance (polarity is the safety
   argument — false exclusion is unsound, false inclusion costs a
   grant): structural (Endrer block present and naming no law —
   measured exact, 0 of 2,365 instruments carry a present-but-empty
   block) ∧ textual (no word-bounded definite act-word
   `loven|lova|lovens|lovas`). The 8 instruments the textual
   witness holds back include two that POSTPONE an act while their
   Endrer names only a kgl.res. — the structural witness alone
   would drop the most refuting siblings there are (fresh evidence
   for W-49's "neither witness sound alone"). All three refuting
   conjuncts now read ONE sibling set. **(2) Carve-out tail fence**
   `_WHOLE_ACT_TAIL_HAZARD_RE` (own vocabulary, deliberately NOT
   shared with `_SUBDIVISION_SCOPE_RE` — widening that one could
   only take W-47 grants); flip set exactly 1 (`2020-05-07-944`;
   the other two carve-outs W-50 found were already refused on two
   dates, pinned still-inert). The module's two readers now agree
   on that sentence. **(3) Act-level
   `ACT_HAS_NO_LATER_INSTRUMENT`** on the shipped route, same value
   and same code as W-47's; W-49's textual-disjointness half
   explicitly does NOT apply (a whole-act claim leaves nothing to
   prove disjoint — ANY later commencement-relevant sibling
   refutes); asserted AFTER the date-conflict branch (found by a
   failing test: upstream it would silently resolve conflicts
   toward the later date), pinned. Results: **2 demotions, both
   proven breaches** (bredbåndsutbyggingsloven's act by the fence,
   etterretningstjenesteloven's by the refutation); parts routes
   byte-unchanged 123/260/33 (monotone + measured); **0 candidate
   movement** (65 → 65 identical sets; the three affected laws were
   blocked or off-universe anyway — honest-exposure clause never
   engaged); P1 **0 EARLY over all 540** whole-act grants, now a
   gate property; the lane's single residual P1 row is a
   dateInForce-comparison artefact on W-39's route (superseded
   kgl.res. keeps its abandoned date), 0 under a document-date
   reading — deliberately not adopted (a loosening nothing needs).
   Pin package signed off 2026-08-09: instrument_authorized 542 →
   540 (the pin's FIRST backwards move — the item's intent),
   contingent 962 → 964, coverage 607/1,758; scan byte-identical.
   Recorded for W-53: its numbers must be RE-MEASURED on top of
   this patch (expect ~968 not 970 — neither demoted act returns);
   its route must consume the sharpened sibling set via
   `_act_has_later_commencement_sibling` (seam in place) and check
   `unntak for`/`foreløpig ikke` against its reader. Remaining lane
   asymmetry: W-39's route still has NO later-instrument conjunct
   (its zero-early is a measurement, not a gate invariant; the
   act-global rule is the wrong shape per W-49's argument).
52. **W-52 (klimakvoteloven renumber/observed-write replay defect,
   blocks the first `error` verdict):** DONE (`03cea7ec5`,
   2026-08-09). Triaged to root cause and **FIXED — a
   receipt-completeness defect, not an engine ordering defect.**
   The audit fired TRUE against the receipt: the
   `(RENUMBER, dest_occupied)` totalization cell
   (`no_replay_renumber_occupied_destination_removed`) destroys the
   occupant standing at the renumber destination, but
   `_synthesize_receipt` derived a RENUMBER footprint purely from
   the (from, to) legs — the occupant's subtree was a real content
   write under NO declared path. Only CROSS-container occupants
   tripped the audit (`paths_related` is a prefix relation):
   klimakvoteloven's `no/lovtid/2012-05-25-29:24` (`Nåværende §§ 23
   og 24 blir §§ 22 og 23`, § 22 live in chapter 5 because
   contingent `2007-06-29-93` is rightly skipped) and two ops on
   `2005-06-10-44`. Same-container occupants passed unseen — the
   census found **7 silent undeclared removals across 6 laws**
   (FIRED stop condition, reported and closed by the fix; the
   writes were never unwitnessed — each carries its typed
   adjudication — the RECEIPT was silent). Class total: 10 firings
   / 7 laws; violations exactly 2 laws, both now replay clean. Fix
   (+514/−0): `MaterializeResult.recovery_removed_paths` with a
   `__post_init__` guard (declaring collateral REQUIRES a named
   recovery rule — the channel cannot silence the audit without a
   catalogued rule standing behind the write), folded into
   `removed_paths` with already-declared-leg dedup (keeps the 7
   same-container receipts byte-identical); the grafter's recovery
   site declares the occupant. Audit verdict moves violation →
   `qualified` — the status defined for named-rule-explained
   divergence. Blast radius measured over all 782 base laws
   (receipts/audits/adjudications/IR/divergence rows, patch vs
   base): exactly the 2 previously-dying laws moved; **0 of 65
   candidates; scan byte-identical 25/40/0; totals 1,447 = 1,011 +
   436**; no other frontend sets the field (0-delta by
   short-circuit). Pins: 7-law corpus table by id
   (firings, collateral receipts) summing 10/3 with zero remaining
   violations; unit pins for cross-container declaration,
   same-container no-duplication, and the guard. Recovery-POLICY
   correctness deliberately out of scope → W-54; pre-existing
   ctsf-gate baseline drift found at base → W-55. For W-53:
   klimakvoteloven scores `consistent` / 0 divergences under
   route5 — **the widening's error column stays ZERO** (expected
   scoreboard 29/44/0, not 28/44/1); `2005-06-10-44` also unblocked
   as a side effect (still blocked_contingent, not a route5
   entrant). Artifacts `.tmp/w52/` (census, blast-diff evidence,
   route5 entrant verdicts).
53. **W-53 (land the `route5` widening, after W-51 + W-52):** DONE
   (`83cdbde72`, 2026-08-09). The gate's FIFTH route, the second
   act-level one, resolved BETWEEN the shipped whole-act route and
   the three part routes; conjunct set, receipt id and parse-time
   `widened_whole_act_scope` flag exactly as specified at W-50.
   **430 grants, not 428** — the +2 (`2003-12-12-113`,
   `2011-06-24-39`) is W-51's sibling sharpening, proven by
   counterfactual (the unsharpened set reproduces W-50's 428 to
   the unit), so the W-51 entry's "expect ~968" reads **970**.
   Hard requirements: the refutation conjunct consumes the
   sharpened set via `_act_has_later_commencement_sibling` (same
   helper, same once-built map as W-47/W-51); W-51's carve-out
   fence applied UNCHANGED to the single block (measured flip set
   0 — all 13 corpus texts carrying `unntak for`/`foreløpig ikke`
   are already refused on another token; kept for structure,
   pinned at zero, three unit refusal pins); conflict branch gets
   first refusal before the refutation (the W-51 ordering lesson,
   pinned). Two additions beyond the sizing, both deliberate: **(1)
   the widened route declines any act the shipped route so much as
   PROPOSED a date for** (not just authorized — re-deciding a
   shipped refusal on a read text would resolve a cross-route date
   disagreement silently; fires once, `no/lovtid/2020-06-23-97`,
   pinned); **(2) the whole-act route's refusal receipt is
   WITHDRAWN for pairs the widened route grants** (its reason text
   — "stays evidence and re-dates nothing" — would be false on 274
   receipts; refusals 1,156 → 882, granted∩refused pinned empty;
   the lane's first receipt retraction). The proposal consumes
   nothing — a refuted or conflicted widened claim leaves part
   grants standing (pinned). **Absorption audit: part grants 416 →
   70; 346 absorbed — 344 date-identical, 2 LATER-conservative
   (`2008-12-19-106` part II 2010-02-01→2010-03-01,
   `2009-04-24-22` part I 2009-12-18→2010-01-01), 0 EARLIER; scope
   inflation exactly W-50's 2 acts / 4 bindings (`2005-01-07-2`,
   `2006-06-30-52`); absorption total per act, never partial.**
   P1 act-level probe: **1,040 grants, 0 EARLY** — hard gate
   passed. Both W-51-demoted acts stay demoted under all five
   routes (pinned). Status 539/1,047/970; staged redatings split:
   new `_WIDENED_STAGED_INSTRUMENT_REDATINGS` table of 5, all
   moving LATER (the original 8 all move earlier). Pin package:
   five-route census 540/430/33/4/33; inert 4 (1/1/2); flag
   nesting `shipped(607) ⊆ widened(1107) ⊆ reader(1127)`; verify
   73 routed / 29-44-0 / 1,485 = 1,011 + 474 (consistent +4,
   replay_defect +3, untouched_drift +1); would-be transfer 57 →
   61 fully_replayable / 33 → 29 blocked_contingent (sum 90
   unmoved). **New structural asymmetry, pinned: W-49's route
   loses NOTHING to the absorption (33 grants / 10 acts intact) —
   it fires exactly where a later sibling exists and is provably
   about other parts, which is what the widened route's act-global
   refutation refuses; the two are mutually exclusive by
   construction** (W-39/W-47 lose 90/256). Deferred: the
   20-candidate gap `widened_whole_act_scope` → reader is entirely
   multi-block instruments, unread — a second-block reader is the
   next widening if one is wanted. Still open from W-51: W-39's
   route has no later-instrument conjunct. The inert-part-grant
   cleanup question is now mostly moot (27 of 31 retired with
   their routes). Artifacts `.tmp/w53/` (movement diff, P1 log,
   absorption audit, fence witnesses, variant counterfactuals).

54. **W-54 (audit the `(RENUMBER, dest_occupied)` recovery
   policy):** DONE (audit, RESEARCH-ONLY, 2026-08-09; artifacts
   `.tmp/w54/`, no product change). **8 of 10 corpus firings
   `removal_correct`, 2 `removal_wrong` — the first proven
   live-law destruction by a landed Norway recovery** (fired stop
   condition; evidence complete, fixes priced, signed off). Three
   mechanism classes, not one: **(A) number reuse / supersession
   (6)** — the legislator recycles the number and the occupant's
   substance is repealed or re-enacted elsewhere by the SAME act
   (`"Nåværende § 12 blir § 14"` + a new § 16 carrying old § 14's
   text; klimakvoteloven's `§ 21 skal lyde` freeing § 22 for old
   § 23); 4 oracle-confirmed at 0 divergences. **(B) stale tree
   from a rightly-skipped contingent amender (2)** — the W-52
   mechanism; true slot vacant, removal converges. **(C)
   incomplete ledd-shift cascade (2)** — the occupant is IN FORCE
   at that address and the true timeline moves it one slot down,
   but the mover op is missing: **tvisteloven § 24-8**
   (`2024-12-13-78:8`; `"Nåværende tredje og fjerde ledd blir
   fjerde og nytt femte ledd."` lowers only the 3→4 leg — the
   same sentence yields both legs in `2024-12-20-87` and
   `2024-06-14-34`, so a lowering defect) loses the
   vitneforsikring, `OPS_MISSING …/section:24-8/subsection:5`;
   **skattebetalingsloven § 8-2** (`2024-12-20-87:2`; both legs
   lowered correctly, but the tree carries a stale duplicate
   fourth ledd because no indexed instrument repeals the base
   act's first ledd — a missing archive artifact) loses the
   Skattedirektoratet regulation power, `MISMATCH
   …/section:8-2/subsection:5`. **Structural discriminator: all 4
   same-parent `dest == src+1` shift-down cascades are the
   hazardous subclass (2 proven wrong, 2 right only because the
   section is already stale); all 6 cross-container / number-reuse
   firings are correct.** Alternatives measured end-to-end behind
   a reverted env gate (divergence totals over the 7 laws):
   remove 1,760 < keep-both 1,772 < stash 1,776 < refuse 1,778;
   remove is the ONLY policy holding both scan-visible laws at 0
   divergences. `stash` exactly repairs tvisteloven; `refuse`
   does NOT repair skattebetalingsloven — the follow-on 3→4's
   destination is inside `renumber_sources`, bypasses the guard,
   and leaves a duplicate `subsection:4`. Recorded caveat: the
   divergence metric UNDER-PENALISES destruction (one
   `OPS_MISSING` row vs `MISMATCH`+`CONSOLIDATED_MISSING`), so
   the aggregate gap is not a soundness argument. **Verdict: keep
   the policy; do NOT pin the verdict table** (it would freeze
   two `removal_wrong` rows as expected behaviour — pin with the
   fix; right shape when it lands: per-firing `(op_id → verdict,
   occupant_probe, expected_survival_address)`). Dead cell
   `no_replay_insert_occupied_direct_child_replaced`: same
   polarity, dormant by op-scheduling luck only — it fired live
   under the `refuse` counterfactual, overwriting tvisteloven
   § 24-8's third ledd; not safe by construction. Follow-ups
   opened: W-56 (repair class C — two-limb lowering first,
   cascade-aware polarity priced ~35 lines as fallback), W-57
   (range-renumber lowering sizing), W-58 (the missing-amender
   archive gap).

55. **W-55 (ctsf-gate baseline drift, pre-existing):** DONE
   (`ad03ece3a`, 2026-08-10). **Root cause: CORPUS drift, not
   code — and the honest fix was neither arm as posed but a
   gate-engine soundness gap.** The archive was refreshed
   2026-07-31, after the baseline's 2026-07-04 freeze
   (`714e7d657`), pulling in lov `2026-06-19-48`, which repeals
   `no/lov/2020-05-07-38` § 64 annet ledd effective 2026-06-19;
   the live Lovdata oracle has applied it, and replay CORRECTLY
   withholds it at `as_of=2026-03-29`
   (`no_replay_future_effective_skipped`) — the oracle is ahead
   of the anchor window and the gate convicted a correct replay.
   Dispositive control: the freeze commit's own code re-run on
   today's archive convicts identically, so no landed W-item is
   implicated. Byte-exact witness: replaying to horizon
   2026-06-19 yields 0 divergences act-wide. Since NO's oracle is
   one live consolidation with no PIT addressing, this was a
   standing false-conviction lane firing on the passage of time
   alone. Repaired in the CTSF engine ONLY
   (`tools/no_anchor_manifest.py`, no `norway/` product change —
   zero scan exposure structurally): a per-section TEMPORAL rail
   retypes a penalized section to non-billable
   `temporal_mismatch_commensurability` iff re-replaying to the
   horizon read off replay's OWN typed future-skip receipts
   (never an invented date) reproduces the oracle section
   byte-for-byte; any other drift stays billable; skipped when
   the per-anchor `oracle_suspect` rail already covers the act.
   Baseline re-frozen `1 → 3` residuals, **billable 1 → 0**, all
   rows attributed: `2020-05-07-38 {} → temporal_mismatch 1`
   (this rail); `2025-04-25-12 {} → temporal_mismatch 2` (same
   refresh — three new Innkrevingsloven amendments, one
   contingent → typed by the PRE-existing per-anchor rail);
   `2020-12-18-156 oracle_editorial_pathology 1 → {}`
   (**RESOLVED by W-18 `c8ffa7eb9`** — Lovtidend's typed
   rettelse now lowers as a same-act op and § 5 replays clean;
   the editorial-registry entry is superseded and kept inert as
   a regression backstop). The data-absent test pair was a pure
   cascade of the NO lane failing inside `run_gate()`/`main()`
   — no independent defect. 3 tests added, none weakened; shard
   green (`104 passed, 40 skipped in 803s`). Artifacts
   `.tmp/w55/` (three-way freeze/base/fixed score control,
   row-attributed baseline delta).

56. **W-56 (repair the class-C cascade firings — the two
   `removal_wrong` rows):** DONE (`e2589b292`, 2026-08-09).
   **Root cause RECLASSIFIED: not a prose-parsing defect but
   Lovdata markup under-declaration.** Renumber legs come
   exclusively from `data-move-part` (`_split_move_attr`); the
   prose was never read for the shift. `2024-12-13-78`'s block
   declares ONE leg where its lead sentence commands two — the
   lowering mirrored the markup blindly, and the partial cascade
   is what destroyed the vitneforsikring. Sweep (3,089 artifacts /
   3,885 change blocks / 286 with `data-move-part` / 166 with
   ledd-shift prose): 148 agree, 1 richer-markup (benign), 17
   under-declared in three classes — **4 well-formed-but-
   incomplete (REPAIRED here**: `2024-12-13-78`, `2024-05-31-26`,
   `2024-06-21-44`, `2025-12-22-129` — exactly 4 legs added
   corpus-wide), 10 with NO attribute at all (no anchor — W-59),
   3 malformed-token (already receipted — W-59). Fix:
   `_no_completed_move_legs_from_ledd_shift_prose` — pure
   templating off the legs the markup already carries (base act /
   section / container NEVER from prose, only the shift map);
   add-only polarity (every guard refuses back to the declared
   legs — a sentence the grammar cannot fully account for lowers
   to nothing NEW); non-blocking receipt
   `no_parse_structured_move_legs_completed_from_lead_prose`,
   cataloged. Blast radius (782 laws): 5 moved, exactly ONE
   statute text changed — tvisteloven, the intended repair
   (ops 66→67, `OPS_MISSING …/24-8/subsection:5` CLOSED, 399→398,
   zero rows opened, occupied-destination firing suppressed by
   the `destination not in renumber_sources` guard); the other
   four are op-id shifts / content-neutral completions, incl.
   scan candidate `2020-04-17-29` with divergence rows
   byte-identical. **All 73 candidates byte-identical; totals
   unchanged 1,485 = 1,011 + 474; scoreboard 29/44/0; zero
   binding/`base_ids` movement; zero new recovery firings; the
   insert dead cell still 0.** Recovery census 10 → 9 firings /
   6 laws. **W-54's verdict table now PINNED**
   (`_NO_OCCUPIED_DESTINATION_VERDICTS`, equality-compared:
   per-firing verdict + occupant probe + survival addresses
   re-derived from the replayed statute; a new unadjudicated
   firing is an alarm). The skattebetalingsloven row is pinned
   `removal_wrong` ON PURPOSE with `wrong ==
   ["no/lovtid/2024-12-20-87:2"]` — the designed W-58 handoff:
   list shrinks = W-58 landed (flip consciously), list grows =
   new live-law destruction. `_NO_OCCUPIED_DESTINATION_LAWS`:
   tvisteloven (1,0) → (0,0), key kept so a resurrected firing
   trips. One out-of-plan pin moved, exact re-pin: `n_ops`
   26,946 → 26,950 (+4 = the completed legs, 0 lost, 0 rebound).
   Vitneforsikring survival pinned at
   `part:5/chapter:24/section:24-8/subsection:5/sentence:1`.
   Tvisteloven's vitneforsikring row was the LAST live-law
   destruction reachable by the lowering; the remaining
   `removal_wrong` is W-58's archive gap. **That last clause did
   not survive contact with W-61: skattebetalingsloven was ALSO
   reachable by the lowering, and W-61 retired it the same way —
   `wrong == []`, no adjudicated recovery in the corpus now
   destroys in-force law. The handoff pin flipped as designed.** W-57's surface is
   unaffected (section-level ranges, no `data-move-part` anchor —
   different production). Honesty note: the completion finding is
   document-scoped (like the malformed-attr finding), so it
   appears in every base act the instrument amends (visible as
   `2021-06-18-97`'s +1 adjudication) — noted, not tidied.
   Artifacts `.tmp/w56/`.

57. **W-57 (range-renumber lowering, sizing pass):** from W-54.
   `"Nåværende §§ 9-1 til 9-6 blir ny §§ 3-1 til 3-7"` is never
   lowered — systematic, witnessed at `2015-04-10-17` against
   forsikringsvirksomhetsloven (only that act's single-section
   renumbers exist in the op stream). Content-neutral in the W-54
   case only because the same act re-supplied the text. Size the
   corpus surface (how many range renumbers, how many acts, what
   divergence closure) before any implementation; own design pass
   per the W-41/W-50 discipline. **UNFROZEN and RE-SCOPED at W-62
   (2026-08-10): the second witness exists decisively (98 leads /
   100 refusals / 59 instruments / 49 base acts of
   relocation-and-range shapes, 7 high-value) — but the premise
   is corrected: NO unequal-arity range occurs in any sample (all
   are equal-cardinality order-preserving bijections; W-57's own
   6→7 witness is the rare shape, not the family). The
   load-bearing property is ATOMICITY under overlapping
   source/destination sets, not range arity. Do not implement as
   stated — the family is served by W-66 (atomic set-relabel) +
   W-69 (relocation).** **HALF-SERVED 2026-08-12: W-66 landed the
   LEDD sibling-set relabel (622 leads, 682 refusals withdrawn) and
   its corpus population contains not one unequal-arity range,
   confirming the corrected premise. The SECTION-level range
   ("Nåværende §§ 9-1 til 9-6 blir ny §§ 3-1 til 3-7") is still
   unlowered and is still W-69's, together with relocation.**

58. **W-58 (skattebetalingsloven § 8-2 missing amender —
   index/archive gap):** from W-54. No instrument among the 71
   indexed amenders of `no/lov/2005-06-17-67` repeals § 8-2
   første ledd (`"Tilskudd til folketrygden … folketrygdloven
   § 23-9"`), yet every later ledd-targeted amendment reads on a
   four-ledd section — the true repeal exists but is not in the
   index (text-grep of all 71 sources for `§ 8-2` finds only the
   five ledd-replacement instructions). Find the missing
   instrument (Lovdata live probe or acquisition sweep), ingest
   or type it; this is the actual root cause of the
   skattebetalingsloven `removal_wrong` row. W-56 pinned this row
   as the designed handoff: when the missing repeal lands,
   `test_no_corpus_occupied_renumber_destination_verdicts_are_pinned`
   fails on its `wrong == [...]` assertion — flip the row there,
   consciously. **RECLASSIFIED at W-60 and ABSORBED INTO W-61:
   there is no archive gap.** The Lovdata probe found the repeal
   — `"§ 8-2 første ledd oppheves. Annet til femte ledd blir
   første til fjerde ledd."` in `no/lovtid/2008-12-12-100` — and
   that sentence is PRESENT VERBATIM in our archived copy, which
   is indexed and applied (19 ops). It is not lowered because it
   sits in a run-on part boundary
   (`…kommunene.III§ 8-2 første ledd oppheves…`) refused with the
   typed `no_parse_unstructured_lead_unmatched` (one of 14 on
   that instrument). The earlier text-grep false-negatived on the
   run-on form. The W-56 handoff pin flips when W-61's LOWERING
   fix lands, not an ingestion. **CLOSED at W-61 (2026-08-10) —
   and the run-on reading above is ALSO wrong.** There is no run-on
   anywhere in the corpus (0 occurrences of `.<ROMAN>§` in the raw
   bytes of all 3,089 artifacts; the string was an `itertext()`
   artifact of reading across a correctly marked-up part boundary).
   The lead is refused because the unstructured repeal-then-shift
   production required the literal `Nåværende`. Two successive
   diagnoses of this one row were wrong before the third held; the
   lesson W-61 records is that a text-plane grep and a whole-
   document text rendering are both unsound evidence about a
   DOM-structured corpus — probe the node the parser actually
   reads. See item 61.

59. **W-59 (the anchor-less ledd-shift blocks):** from W-56's
   sweep (`.tmp/w56/sweep2.json`). **10 change blocks carry
   ledd-shift prose and NO `data-move-part` at all** — a total
   drop the W-56 completion cannot reach (nothing to template
   from; repairing means minting base act + section + container
   from prose alone, a genuinely larger production needing its
   own design pass and the full blast discipline). 9 laws:
   `1953-06-26-11`, `1973-03-09-14`, `1982-05-21-25`,
   `1994-06-24-39`, `1994-08-05-55`, `1999-07-02-63`,
   `2005-06-17-67`, `2009-06-19-58`, `2016-08-12-77`. Adjacent
   residue, cheaper but same discipline: **3 malformed-token
   blocks** (`2024-06-21-46` no separator + cross-base,
   `2025-02-07-1` `;; ` with stray space, `2025-06-20-74` `::`
   for `;;`) — one-character source typos a tolerant token
   normalizer could recover; changes op streams, needs the
   W-52/W-56 blast measurement. Size both surfaces before
   implementing either. **RE-SCOPED at W-60: 7 of the 9
   anchor-less laws are in the no-original-source population and
   cannot be replayed, gated, or scored at all; and one of the
   remaining blocks (`2024-06-21-46` → `2022-05-12-28`) is a SEED
   ERROR — its `data-move-part` addresses `lov/2010-03-26-9/§65`,
   caught by W-60's proposer. The reachable surface is 2 blocks
   (`2016-08-12-77`, `2009-06-19-58`), both of which W-60's
   proposers converted at the full gate — their ops exist in
   `.tmp/w60/proposals/` should a landing lane ever open.**

60. **W-60 (proposer–verifier spike — size the LLM lane for
   NL→ops, plus shallow-anchoring and archive-gap riders):** DONE
   (spike, RESEARCH-ONLY, 2026-08-10; brief `.tmp/w60/brief.md`,
   artifacts `.tmp/w60/`, no product change). **Verdict:
   ESCALATE, redirected — no evolver harness.** Panel: 15 live
   sites (7 of the 9 W-59 seed laws are UNREPLAYABLE —
   no-original-source population — trim stated, backfilled).
   **Conversion 7/15 = 47%** at the full gate (fresh oracle-
   redacted proposer subagent per site, span-cited ops, 3-attempt
   cap); D2 closed `2011-06-24-39` 5→0, D1 closed `2004-03-26-17`
   1→0. **Controls: 0 false accepts on both arms** — but arm 1
   (corrupted inputs) was intercepted by the PROPOSER (3 correct
   refusals + 1 contingent-blocked) and never exercised the gate;
   the agent added **arm 2 (15 mutated ops from converting
   proposals): 0 pass, and the load-bearing finding is that TWO
   mutants pass every divergence-based conjunct (one at ZERO
   divergences with false law) and are caught ONLY by the typed
   apply-plane conjuncts** (`replay_tree_invariant_violation`
   duplicate-label; `no_replay_insert_occupied_direct_child_
   replaced` — W-54's dormant cell fired live AGAIN). A
   divergence-only gate admits ~13% false mutants → W-63.
   Failure taxonomy (8 non-converts): only ONE is
   better-proposal-fixable; the rest are a mis-specified W-59
   seed row (proposer caught our own error), the W-57 op-kind
   hole (independently rediscovered from source text),
   a contingent instrument, an upstream lowering defect, an
   oracle normalization artifact (`§§` vs `§ §` — proposer
   correctly refused to chase the target), the sparse ceiling,
   and a "gap" that W-58's answer dissolved. **An evolver would
   search a space where 7 of 8 failures are outside the search.**
   Receipt honesty: all 24 converting-proposal spans verbatim,
   but a third license only half their op (address comes from
   markup the span does not quote); "span-cited" needs a typed
   `span_role` that admits what it cannot prove — below the bar
   as-is. **Rider A (shallow anchoring): CLOSED** — universe
   corrected 439 → 316; 15/15 sampled consolidations parse; but
   consolidation-anchored verification is TAUTOLOGICAL (the
   consolidation IS the oracle); non-vacuous yield = forward
   replay only: **13 laws / 14 ops corpus-wide**. Not a work
   item. **Rider B (archive gaps): NOT MATERIAL** — of 1,007
   apparent gap rows, 998 are the three known
   sparse-indexed-history laws; **~9 genuine gap rows across 9
   laws**; and the probe ANSWERED W-58 (see item 58, reclassified
   — the instrument is in the archive; the blocker is lowering).
   Queue restructure signed off 2026-08-10: W-61/W-62/W-63
   opened, W-58 absorbed into W-61, W-59 re-scoped, W-57 stays
   frozen (needs a cross-container MOVE op kind with range arity
   — confirmed twice independently), shallow anchoring closed.
   Burn ~1.05–1.2M of 1.5M budget (estimated, 22 spawns).

61. **W-61 (the unstructured repeal-then-shift lead — W-58's real
   root cause):** DONE (`d854e93fe`, 2026-08-10, artifacts
   `.tmp/w61/`).
   Absorbs W-58. **The item's own premise was FALSE and the fix is
   somewhere else.** There is no run-on part boundary: the
   `.<ROMAN>§` concatenation occurs **ZERO times in the raw bytes
   of all 3,089 amendment artifacts** and zero times in any single
   leaf text node (`s5_runon_shape.py`). W-60's
   `…kommunene.III§ 8-2…` was an `itertext()` rendering of the
   WHOLE document walking across a `<section data-name="kapIII">`
   boundary Lovdata marks up correctly; part III of
   `no/lovtid/2008-12-12-100` is one clean
   `<article class="defaultP">`. The real blocker: the
   unstructured production that already lowers this exact family
   (`§ X <ord> ledd oppheves. Nåværende <ord> ledd blir <ord>
   ledd.`) **hard-required the literal `Nåværende`**, and the
   witness says "Annet til femte ledd blir …".
   **Census (`s1`/`s2`/`s8`): 9,478 `no_parse_unstructured_lead_
   unmatched` over 1,821 instruments and 645 base acts; 45 carry
   the "§ S <ord> ledd oppheves. …" head; 24 are this family with
   the qualifier absent, spelled `Gjeldende`/`Någjeldende`, or
   repeating the section.** The other 21 are refused BY
   CONSTRUCTION and stay refused: 19 carry a trailing clause that
   introduces a PAYLOAD ("… og skal lyde:") the shift does not
   account for, 2 are not a ledd shift. Of the 24, **23 convert**
   (14 instruments, 21 base acts, 24 (instrument, base, lead)
   receipt triples — one lead amends two acts at once); the 24th is
   the multi-section repeal list the guard declines.
   **Fix: strictly additive.** The shipped pattern is tried first,
   character for character; only a lead it cannot match reaches
   the widened one, whose ordinal phrases go through W-56's
   `_no_ledd_shift_ordinals` — same `_NORWEGIAN_ORDINALS`
   vocabulary, same all-or-nothing refusal, but it spans `til`
   RANGES, which the `skal lyde` round-trip resolved to NO targets
   (the witness needed the widening twice over). Section class
   picks up W-32(c)'s `(?:\s+[A-Za-z])?`. Guards: the shift may
   repeat its `§` only if it EQUALS the repealed section; an
   out-of-vocabulary ordinal refuses the whole lead, which is also
   what declines the one multi-section repeal list.
   **That ordering was forced by measurement, not caution: a first
   cut that replaced the production outright regressed 14 leads**
   (7 spell the qualifier before the section, 7 carry
   `henholdsvis`/`eneste`/`siste`/ordinals past `tiende` on which
   the shipped round-trip lowers a partial answer) and drove
   `no_parse_unstructured_renumber_arity_mismatch_skipped` from 8
   to 0. Final parse-level delta is **exactly −24 refusals and
   nothing else**; 0 introduced.
   **Blast (782 laws, W-52/W-56 discipline): 11 laws' replay moved,
   ALL outside the 73 scan candidates — candidate replay AND verify
   output byte-identical, 0 moved.** Corpus totals held: 1,485 =
   1,011 + 474, scoreboard 29/44/0. Three laws' TEXT moved, every
   move a repair verified against the consolidation: **skatte-
   betalingsloven § 8-2 (223 → 222, `MISMATCH …/section:8-2/
   subsection:5` CLOSED)**, utlendingsloven § 107 (842 → 840, two
   rows closed — the tilsynsråd ledd repealed as `2021-06-11-72`
   moves it to a new § 107 a) and finansforetaksloven § 7-7.
   **No divergence row OPENED anywhere.**
   **The designed success criterion landed, and by SUPPRESSION
   rather than re-verdict:** `no/lovtid/2024-12-20-87:2` no longer
   fires at all — § 8-2 becomes the four-ledd section the later
   amendments have always read on, so the `4 → 5` leg never lands
   on an occupied node. `_NO_OCCUPIED_DESTINATION_LAWS`
   `2005-06-17-67` (1,0) → **(0,0)**, firing total 9 → **8**, the
   verdict row removed and **`wrong == []`** — the W-56 handoff pin
   flipped consciously. **The corpus now has NO adjudicated
   recovery that destroys in-force law** (W-54's two
   `removal_wrong` rows are both retired: tvisteloven at W-56,
   skattebetalingsloven here). New pin
   `test_no_skattebetalingsloven_8_2_regulation_power_survives`
   holds the positive fact.
   **Bindings (stop condition, adjudicated not assumed): +10
   (act, law) pairs, 0 removed, 0 REBOUND** — every one an
   amendment `changesToDocuments` already DECLARED and the index
   already receipted as unbound, so the declared-target gap falls
   in exact step (958 → 956 receipts, 2,534 → 2,524 pairs, 10 = 10,
   the W-34/W-35 conservation). Each verified from source text
   (`s16`/`s17`): every converted lead sits directly under its own
   numbered or part law-switch lead. Pins: `n_ops` 26,950 →
   **27,018**; entries 2,559 → 2,560; bindings 6,466 → 6,476;
   `instrument_authorized` 970 → **971** and staged-population 540
   → 541 (ONE act gains its first index entry — `2014-06-20-26`,
   whose part I carried a single operative lead).
   **One number FELL, and it is honest exposure:
   `would_be_candidates` 61 → 60.** Mineralloven
   (`no/lov/2009-06-19-101`) leaves the counterfactual ceiling
   because it now binds `2013-01-11-3` — an amender whose own
   commencement is "Kongen bestemmer" with no date. The amender was
   always there and always undated; we could not see it only
   because its two leads did not lower. Real candidate set stays 73.
   **For W-62:** the post-fix remainder is **9,454 refusals / 8,245
   distinct leads / 1,820 instruments / 645 base acts**, bucketed in
   `.tmp/w61/w62_census.json` — 4,613 refusals end with a
   payload-introducing colon, 1,686 address `bokstav`/`nr.`, 1,143
   are `Nåværende` renumbers, 608 ledd shifts, 611 repeals, 211
   `skal lyde`, 438 other. Two adjacent findings priced there and
   deliberately NOT taken here: **(a) the unstructured grammar has
   NO ledd-shift family at all** — an anchor-less or even
   §-anchored "X ledd blir Y ledd." sentence lowers nothing
   (`s4_anchor_probe.py`), which is why the § 8-2 shift could only
   be reached through the combined repeal-then-shift production;
   **(b) multi-sentence leads are refused whole** — 47 leads would
   half-lower under naive sentence segmentation and only 6 fully,
   touching 0 scan candidates, and the half-fix is measurably
   HARMFUL: the counterfactual (`s7`) shows repeal-only at the
   witness takes § 8-2 from 223 to **224** divergences by opening
   `OPS_MISSING …/section:8-2/subsection:1`. Segmentation is worth
   nothing without the shift family; price them together or not
   at all.

62. **W-62 (the proposer lane as a TRIAGE instrument):** DONE
   (census, RESEARCH-ONLY, 2026-08-10; artifacts `.tmp/w62/`, no
   product change). **The lowering lane's scoreboard yield is
   measured, and it is nearly exhausted: only 0.97% of the 9,454
   refusals touch a scorable law (82 high-value triples over 23
   of 73 candidates / 38 instruments), and AT MOST 10 of the 474
   unexplained rows are address-coincident with any refused lead
   (all 10 `OPS_MISSING` — the right polarity; 306 of 474 sit on
   laws with NO refused bound lead at all, a hard exclusion).
   After W-64 + W-67 (~8 of the 10), the remaining 9,000+
   refusals are receipt-honesty debt on unscorable laws — priced
   as that, never as scoreboard movement.**
   **CORRECTED at W-69's design pass (2026-08-12), and the
   correction is the headline of that pass.** "Never as scoreboard
   movement" was read forward as *no unexplained row is reachable
   by an open item*, and at HEAD `4a68b5a48` that is false by at
   least 19 rows and arguably by 40. The census's own scope is why:
   it keyed on the UNSTRUCTURED refused-lead population, and the
   substitution family lives in the STRUCTURED lane, where it was
   not a refusal at all until W-75 made it one. Re-derived row by
   row against both texts (`.tmp/w69/rowmap.json`): W-69's
   substitution arm closes **11 unexplained rows today and 19 with
   a read-only sentence materialization** — `no/lov/2015-06-19-70`
   (karanteneloven, 4 + 7 of its 12) and `no/lov/2020-04-17-29`
   (7 + 1 of its 15), every one diverging on exactly the superseded
   word. Separately, `no/lov/2016-06-17-29`'s **21 unexplained rows
   are ALL attributable** to one instrument's unlowered
   restructuring cascade (`no/lovtid/2020-06-23-98`: `Kapittel 5
   oppheves.` + `Nåværende kapittel 6 og 7 blir nytt kapittel 5 og
   6.` + five section moves with a trailing locative + two payload
   leads), and are deliberately NOT bought — reaching them needs a
   chapter-repeal production and a chapter-depth set relabel that
   nothing in the queue describes. The 0.97% / 306-of-474 exclusion
   arithmetic still holds for the unstructured lane; the sentence
   that generalized it beyond that lane does not. Re-derived
   baseline at the same HEAD: 174 of the 478 unexplained rows sit
   on candidates carrying at least one refused unstructured lead,
   304 on the 49 candidates carrying none. Census: full-lead
   re-harvest (W-61's excerpts were 240-char truncations; its
   population reproduced exactly, its coarse-six split reconciles
   as an ordered-cascade partition artifact); 13 families /
   skeleton+depth clustering over 8,258 distinct leads; the
   malformed-attr population is 6 blocks over 6 instruments (3
   NEW since W-56 via the archive refresh; 2 cross-base must
   never be recovered, incl. a new one: `2026-02-06-2` addressing
   `lov/2024-06-21-41` under `lov/2022-12-16-91`). Impact
   ranking inverts size (heading/title replaces carry 15 of 82
   high-value triples but ZERO possible divergence movement —
   candidate rows contain no heading/title addresses). Triage: 4
   of 12 proposer groups returned before budget (97.6% of
   refusals in a triaged pool; 227 explicitly unadjudicated; 8
   groups' classification unadjudicated with sizing standing;
   group J compromised by a harness defect the agent found in
   ITS OWN sampler — 17% chimeric (instrument, base) pairs —
   audited, affected findings DISCARDED not propagated).
   Receipt-honesty note: 267 double-receipted leads matched a
   production and failed on payload — the generic refusal
   receipt overstates the grammar gap by that much. Standing
   questions answered: W-57 second witness YES with corrected
   premise (see item 57); lane yield ~10 rows / 2.1%. Items
   opened: W-64–W-71 (all eight, signed off); W-57 unfrozen and
   re-scoped into W-66 + W-69. **W-66's half landed 2026-08-12 and
   confirms the corrected premise at the corpus: across the 622
   accepted leads NOT ONE is an unequal-arity range — every one is
   an equal-cardinality order-preserving bijection, and the "og nytt
   <ordinal>" suffix that looked like unequal arity is the newness
   marker on an ordinary destination. W-57's 6→7 witness is the rare
   shape, not the family. W-69 still owns relocation.** (Late corroboration from the same
   run: of the ~10 traceable rows, one traces to a chapter-scoped
   insert with trailing locative — `Ny § 39 a i kapittel 6 skal
   lyde:`, 1 row on `2017-06-16-67`, detail in
   `.tmp/w62/coincident_detail.json` — small enough to fold into
   whichever item next touches insert productions.)

63. **W-63 (pin the gate's margin — apply-plane conjuncts are
   load-bearing):** DONE (`6b3f789e7`, 2026-08-10, artifacts `.tmp/w63/`).
   **Both of W-60's mutant readings were re-measured at this base
   and NEITHER survives as stated — but the gate property does, in
   a sharper form, and the polarity question resolves cleanly.**
   **(1) `D2_m3`'s "zero divergences with false law" is a
   DEGENERATE zero.** The duplicate-label tree invariant raises,
   `replay.error` is set, and `verify_no_against_current` returns
   BEFORE it loads or compares any consolidated text — so the
   mutant's divergence evidence is 0 divergences / 0 rows opened /
   5 rows closed against a baseline of 5. The divergence plane is
   not merely blind here, it is **INVERTED: the apply-plane
   failure MANUFACTURES the number a divergence-only reader treats
   as success** (`G1_closes`), and only `replay_status` / `error`
   separates a perfect close from a crash. Counterfactual: downgrade
   the invariant and the false law LANDS at 1 divergence with 1 row
   OPENED — i.e. the full conjunct set does see the landed law; the
   error short-circuit alone produces the perfect score.
   **(2) `D4_m3` is not false law at all.** Moving its target from
   `§ 10-9/ledd/4` to `/ledd/5` took it out of the W-60 harness's
   `(target, action)` supersede key, so the parser's OWN correct op
   survived and landed; the mutant's op then fired the direct-child
   cell onto `chapter:10/section:10-9/subsection:4` with
   **content-identical** text (`replay_noop` fired on the same op)
   and the replayed statute came out **byte-identical to the
   accepted control's** (`8240bd16e2d11247` both). The divergence
   conjuncts accepted it CORRECTLY. What it is instead is the
   sharp form of the property: **two different op streams, identical
   divergence evidence, and the difference visible only in the typed
   receipt** — plus the second live firing of W-54's dormant cell,
   this time writing to an address the amendment never named.
   **Pinned** in `tests/test_no_gate_margin.py` (5 tests): the
   short-circuit against the production `verify_no_against_current`;
   both mutants rebuilt as self-contained inline op streams (not
   corpus-gated — the `.tmp/w60/` proposals are gitignored and their
   coordinates are pinned to an archive snapshot that already moved
   once under W-55) and scored on the divergence plane with the SAME
   production comparator verify uses (`ingest_consolidated` +
   `verify_consistency` under NO's projection/normalizer), each
   asserting BOTH halves; plus an over-reach guard on the declared
   sibling cell.
   **Polarity adjudicated: FLIP the insert-occupied direct-child
   cell to REFUSAL.** Census at this base over **all 782 base laws
   with the apply fold run NON-STRICT** (so a firing hidden behind
   an earlier raise still counts): **ZERO firings** of
   `no_replay_insert_occupied_direct_child_replaced`; its declared
   θ sibling `no_replay_insert_occupied_target_replaced` fires
   **194 times over 73 laws** and keeps its RECOVER polarity
   untouched. **The discriminator is whether the op's OWN address
   resolves**: the sibling is the Lovdata "ny § 4 a skal lyde"
   source-noise policy §2.3 documents; the direct-child lane is
   reached only when the commanded address does NOT resolve and the
   payload's `(kind, label)` collides with a direct child of an
   INFERRED parent — a wrong-slot signature whose write lands where
   the amendment never pointed while the commanded slot stays empty.
   No legitimate corpus use exists to weigh against the two
   counterfactual firings (W-54's `refuse` A/B destroyed tvisteloven
   § 24-8's third ledd; `D4_m3` overwrote havenergilova § 10-9's
   fourth ledd invisibly). Now emits
   `no_replay_insert_occupied_direct_child_refused` /
   `no_insert_occupied_direct_child_refuse`: blocking, **no write**,
   occupant preserved, op REJECTED in the conserved partition — it
   is the only `no_replay_*` member of
   `_NO_SKIP_ADJUDICATION_KINDS`, forced by the fail-loud "neither a
   landed write nor a typed rejection" guard. Two catalog entries
   swapped (the dead `_replaced` / `_replace` keys removed;
   `test_no_dead_catalog_entries` enforces).
   **Blast radius measured over all 782 base laws** (statute,
   adjudications, receipts, observed-write audits, conserved filter
   partition) and all 73 candidates (including full byte-level
   divergence-row lists): **0 laws moved, 0 candidate row diffs, 0
   `base_ids`/binding movement, candidate divergence total
   1485 = 1485** — byte-identical everywhere, as the zero-firing
   census predicts. **Standing tripwire:** the census is now a
   property, not a snapshot — any future firing of the direct-child
   lane surfaces as a blocking refusal receipt and a rejected op
   rather than a silent overwrite, so it cannot pass an acceptance
   lane unadjudicated. W-54's separate advice to pin the
   `(RENUMBER, dest_occupied)` verdict table only alongside its fix
   is untouched.

64. **W-64 (the `defaultP` heading payload boundary — TOP census
   item):** DONE (`81d318af2`, 2026-08-11; artifacts
   `.tmp/w64/`). From W-62. Lovdata marks a new section's HEADING
   with class `defaultP`, the same class as amendment leads; the
   walk's payload rule "stop at the next `defaultP`" stops on the
   heading and collects ZERO payload. Witness
   `no/lovtid/2003-12-19-129` `"Ny § 37 a skal lyde:"` (heading
   `Avgift og gebyr`, six `legalP` ledd stranded; divergence rows
   exactly `chapter:5/section:37a/subsection:1-6` — 6 of the
   census's 10 traceable rows). Touches the payload boundary rule
   only, not the grammar.
   **The discriminator, and why its polarity is safe.** Six
   conjuncts, all measured rather than assumed: the lead must END in
   `lyde:`; the candidate must carry no operative verb, no `§`, no
   sentence-final punctuation, and at most 80 characters; and the
   node it introduces must actually be there — either a body node
   (`legalP`/`numberedLegalP`/`listArticle`) immediately after it, or
   a lead whose shipped production wants the heading and nothing else
   (`§ X overskriften skal lyde:`). **The cardinal risk is the
   opposite polarity**: absorbing a genuine lead into a payload
   silently DELETES an op. Over all 3,089 unstructured artifacts
   there are 23,716 (lead, next-`defaultP`) pairs; 569 sit behind a
   lead ending in `lyde:`, and exactly **21** of those successors
   parse as a lead today. **All 21 are excluded by THREE independent
   conjuncts at once** (operative verb AND `§` AND terminal `:`/`.`),
   so no single conjunct is load-bearing for the safety property, and
   the admitted set contains zero nodes that produce an op at base.
   Only the FIRST node after a lead is ever tested, so at most ONE
   `defaultP` per lead can be absorbed and the boundary still closes
   on the next one — which is what bounds the blast radius.
   **The census's 455 re-derived under the discriminator**: 84
   admitted, 198 refused because nothing the boundary can use follows
   the heading (185 of them chapter-level inserts whose body is
   itself a run of `defaultP` sections — W-65's surface, not this
   boundary), 63 on terminal punctuation, 54 on the lead gate, 29 on
   length, 27 on the `§`. Admitting 98 whole-section pairs plus 23
   heading-only pairs.
   **Measured, composed corpus, base `4d9dde247`.** Ops **27,100 →
   27,206** (+106: 84 REPLACE, 22 INSERT, over 45 instruments), with
   **0 lost, 0 re-addressed, 0 changed kind** — op-identity diff keyed
   on (base act, action, target, destination, payload digest, lead
   text), never `op_id`, which is a per-document sequence that churns
   ordinally. Entries 2,561 → 2,563, bindings 6,477 → 6,489,
   declared-target gap 955 → 951 / 2,523 → 2,511 (the W-34/W-35
   conservation holds exactly: pair drop == binding gain, 12 = 12,
   with zero targets newly unbound and nothing rebound).
   `instrument_authorized` unmoved at 977, widened whole-act route
   unmoved at 436. One base act receives its first op ever
   (verdipapirsentralloven `1985-06-14-62`), so the amended-law
   population goes 782 → 783.
   **Refusals moved, and the movement is fully attributed: −224, 0
   introduced.** The queue's expectation of "unchanged" was wrong
   about the mechanism, not about the risk: `lead_unmatched` is
   emitted at the END of the dispatch chain, so a lead that gains
   payload short-circuits before reaching it. 106 leads withdraw a
   `payload_unresolved` (82 `future_section`, 24 `heading_only`) AND
   its paired `lead_unmatched`; the remaining 12 `lead_unmatched` are
   statutory BODY prose that was stranded behind the boundary,
   re-read as leads, and tripped the operative-verb heuristic on the
   word `blir` ("Blir innskrevet reisegods skadd, …"). Those 12 were
   always false refusals and are now payload.
   **Blast (W-52/W-56 discipline).** Every one of the 45 moved base
   acts replayed at base and at the patch, flattened to
   address → text: **0 addresses lost non-empty text**, 14 added, 6
   changed in place. 33 of the 45 carry a byte-identical pre-existing
   replay error ("no original-act source available", plus
   `2005-06-17-62`'s pre-existing invariant violation); 6 replay
   unchanged because the new op is outside the applied window at
   as-of (`replay_op_count` identical); 6 move. Of those 6, four are
   heading-only replacements that change a `heading` node and nothing
   else — the section BODY survives every one, which is the property
   that mattered, since a heading-only REPLACE that truncated its
   section would have destroyed in-force law. The two statutory-text
   moves are `2003-12-12-108` §§ 14/17 `Fylkesskattekontoret` →
   `Skattekontoret`, which is exactly what `no/lovtid/2007-06-29-64`
   commands; both sit on `CONSOLIDATED_MISSING` rows that were open
   at base and stay open with the same type (the consolidation prints
   nothing at those addresses), so no row opens or closes.
   **Scan.** Candidates unmoved at 76, scoreboard unmoved at
   **29/47/0**, totals **1,510 = 1,011 + 499 → 1,504 = 1,011 + 493**.
   **Exactly one law's rows move and exactly zero rows OPEN**: the
   witness `no/lov/2001-06-15-75` 15 → 9, all six
   `chapter:5/section:37a/subsection:1-6` `OPS_MISSING` rows CLOSED,
   which means the landed ledd match the consolidation under the
   compare lane rather than replacing one row type with another. The
   heading lands as the section's HEADING and not as its first ledd —
   `_parse_future_section` reads `defaultP` children as ledd, so
   appending it verbatim would have shifted every real ledd's label
   by one and turned six closures into six mismatches. Partition
   buckets unmoved: the witness stays `replay_defect` (touched 4
   unmoved, untouched 11 → 5), and the only other in-scan mover
   (`2012-01-27-9`, one heading-only op) stays `untouched_drift`.
   **Only 2 of the 45 moved base acts are in the 76-law candidate
   set**, which is why 104 of the 106 new ops are scan-invisible —
   honest yield, recorded as such rather than dressed up.
   **Occupied-destination census re-run over all 783 base acts:**
   `renumber_occupied_destination_removed` **10, unchanged element
   for element**, `wrong == []`; no new-section insert lands on an
   occupied node. `insert_occupied_target_replaced` holds at 182 with
   one op_id churning ordinally (`2009-06-19-103:23` → `:24`) on the
   same law and the same paths — the `op_id` caveat, observed.
   **W-63's `insert_occupied_direct_child_refused` cell fires zero
   times at base and zero times after**: landing payload for `Ny § X`
   leads does not reach it.
   **The one ratchet the change moves is a tightening**: the un-waived
   semantic-regex count for `grafter.py` falls 45 → 44 (the inline
   heading-only pattern becomes a waived, shared owning-parser
   helper), so `tests/data/regex_ratchet_baseline.json` is
   re-committed one lower. Nothing is waived that was not.
   **Left for W-65, deliberately:** the 185 chapter-level inserts
   (`Nytt kapittel 5A skal lyde:`) whose body is a run of `defaultP`
   sections, and the 121 heading leads outside the shipped
   `§ X overskriften` surface (`Lovens tittel skal lyde:`,
   `Overskriften til kapittel N skal lyde:`, …). Both are grammar.
   `no/lovtid/2017-06-16-67`'s chapter-scoped insert word-order lead —
   the census's 10th traceable row — gains **0 ops** here, confirming
   it is grammar and untouched.
   **Landing note (main ladder, ladder-procedure knowledge):** the
   `regex_ratchet_baseline.json` change routes shard
   `core_ir_contracts` into the affected set, and in main that shard
   halts on pre-existing Finland stub-archive reds. Known-good
   signature with the first two deselected: **6 failed + 1 error, all
   `test_fi_*`** (`ci_main_coreir.log` in `.tmp/w64/`); none of the
   failing files reference the ratchet baseline or any norway module
   (grepped). Same class as the tools_cli_debug triple — deselect and
   move on, never chase. The norway shard was then run explicitly
   (`--shard norway`, passed).

65. **W-65 (recursive address-path grammar for sub-section
   replace/repeal):** from W-62. ~4,131 replace + 989 repeal
   refusals; the triaged sample closes 9/14 via a recursive path
   grammar (`§` token + composable `<ordinal> <level>` qualifiers,
   any order, any depth); zero of the sampled refusals are a VERB
   problem. **HARD DEPENDENCY on W-64**: widening the grammar
   without the boundary fix converts a loud refusal into a silent
   empty replace — the worse outcome. Remaining sample residue:
   conjoined address lists, inline payload, intra-node punktum
   splitting. Pricing note from the census's second synthesis
   pass: this surface carries only 17 high-value triples and NONE
   of the 10 traceable rows — large, but scan-inert; take it
   after W-64 (much of it is payload-blocked anyway) and price it
   as receipt honesty.

66. **W-66 (atomic sibling set-relabel + address inheritance):**
   DONE (`dc4b3e4e4`, 2026-08-12; artifacts `.tmp/w66/`). From
   W-62; absorbs half of the re-scoped W-57. **It is the largest
   single lowering this lane has shipped — 682 refusals withdrawn,
   not the "13 of 16" the sizing suggested — and it fired the
   `removal_wrong` stop condition on the way, which is why the
   production ends where it does.**
   **What was built.** One production, at the bottom of the
   unstructured walk where W-74's sits, for the LEDD sibling-set
   relabel: `Nåværende femte og sjette ledd blir sjette og sjuende
   ledd.` It is not two renumbers. It is one relabel of a sibling
   SET read against the pre-operation snapshot, and its source and
   destination sets OVERLAP, so the order the legs run in is the
   whole safety argument. `_no_ledd_set_relabel_pairs` parses the
   sentence — W-56's shipped `_no_ledd_shift_pairs_from_sentence`
   FIRST, character for character, then a widened sibling that
   differs in exactly one token (the currency qualifier, drawn from
   W-61's `_NO_CURRENCY_QUALIFIER_ALTERNATION`) — and returns WHICH
   attempt matched, so the additive ordering is a test's fact.
   `_no_ordered_set_relabel_pairs` then emits the legs in a proven
   VACATE-BEFORE-OCCUPY order: a leg may run only once every leg
   whose SOURCE is its destination has run. That is a topological
   sort, not "descending if the shift is positive" — one corpus
   lead is a {+1,+2} map and is not a uniform shift at all — and a
   pair set with a CYCLE (a pure swap, which no sequential relabel
   can express) is refused rather than emitted in some order and
   hoped over. No accepted lead is cyclic today; the guard is there
   because the absence of a cycle is the only reason the emitted
   order is a proof. The kernel's own structural-vacate stage
   (`renumber_vacate=True`) reaches the same order independently,
   and the two agree by construction.
   **Rider 1, address inheritance, delivered.** 392 of the 642
   accepted lead occurrences name no `§` of their own. The antecedent is the
   nearest preceding `article.defaultP` IN THE SAME PART, and it
   must name exactly one distinct section. `defaultP` is Lovdata's
   instruction-lead class; the payload classes are excluded, and
   that is load-bearing rather than tidy — on the payoff witness
   the node physically preceding the shift is the PAYLOAD of the
   lead before it and names a foreign "§ 9", so a
   nearest-any-node rule inherits the wrong section. Being
   DOM-local rather than a carried "last section seen" is what
   makes the rule self-guarding across law switches: a part that
   changes base act does so with a `defaultP` lead naming no
   section, so a shift right after it inherits NOTHING and refuses,
   instead of silently carrying the previous act's section over.
   40 relabels refuse here with a typed receipt
   (`no_parse_ledd_set_relabel_address_unresolved`): 20
   `antecedent_names_no_section`, 13 `part_has_no_antecedent_lead`,
   7 `antecedent_is_meta_amendment` (an antecedent that amends
   another AMENDMENT establishes an address in that amendment, not
   in the base act).
   **THE STOP CONDITION, and the design it forced.** Measured with
   the ops taking the declared θ `(RENUMBER, dest_occupied)`
   recovery, the corpus firing census went **10 → 25**, and two of
   the 15 new firings adjudicate **`removal_wrong`**: straffeloven
   2005 § 3 femte ledd ("Ved domfellelse etter gjenåpning …",
   standing at that very address in the published consolidation,
   removed by `2008-03-07-4`'s "Nåværende annet til fjerde ledd
   blir tredje til femte ledd.") and verdipapirhandelloven § 9-21
   fjerde ledd (the konsolidering forskrift power, removed by
   `2021-04-30-26`'s "Nåværende tredje ledd blir nytt fjerde
   ledd."). **The cause is not the grammar and not the address.**
   Both archived BASE editions already carry the amendment being
   replayed — a pre-2008 replay of straffeloven § 3 is already the
   five-ledd section the consolidation prints — so the relabel
   lands a second time and eats a live provision. No sentence
   grammar can see that.
   **So the production refuses at APPLY, and that is the item's
   real content.** Its ops carry
   `NO_LEDD_SET_RELABEL_PROVENANCE_TAG`, and a leg of a tagged op
   whose destination is OCCUPIED when it runs emits
   `no_replay_ledd_set_relabel_occupied_destination_refused` and
   writes nothing. The check sits BEFORE the `destination in
   renumber_sources` exemption, not inside it, and the placement is
   load-bearing: that exemption exists because the vacate stage
   promises to free a slot before filling it, a promise that holds
   only while every leg APPLIES. Once a leg may refuse, an exempted
   follower lands on a sibling that never moved — measured, as
   `duplicate subsection:4` on verdipapirhandelloven § 15-2.
   Checking occupancy for real, for every leg, is what makes the
   refusal CASCADE instead, so the relabel drops WHOLE rather than
   in halves, which is the W-56 failure mode. **Result: the shipped
   θ cell is untouched for every op that is not this production's,
   the corpus firing census is 10 → 10 equal element for element,
   and the pinned verdict table gains no row.** 31 of the 1,147
   legs refuse, over 11 laws; 1,116 land. The corpus's
   `no_replay_insert_occupied_target_replaced` recoveries FALL,
   184 → 138: a relabel that vacates a slot before the co-located
   promoted INSERT lands means 46 fewer inserts have an occupant to
   overwrite, and the promotion receipt
   `no_parse_replace_promoted_to_insert_for_same_target_renumber`
   rises 36 → 113 in step.
   **Measurement (census over all 3,089 artifacts).** Refusals
   **9,265 → 8,583, exactly −682 and nothing else**; 0 introduced.
   The withdrawal reconciles element for element: 682 = **642
   lowered + 40 typed address refusals**, with ZERO accepted leads
   outside the set frozen before implementation and ZERO frozen
   leads left unaccepted. 622 distinct (instrument, lead) pairs
   over 421 instruments and 207 base acts; 592 occurrences accepted
   by the SHIPPED sentence parser unchanged, 50 needing only the
   widened qualifier; 250 naming their own `§`, 392 inheriting it.
   (The pre-registered model predicted 643 occurrences and 1,148
   legs against 642 and 1,147 realised. The one difference is named
   rather than rounded off: "Nåværende tredje ledd blir nytt fjerde
   ledd." occurs twice in `no/lovtid/2013-06-21-85` and the second
   occurrence sits inside a preceding lead's payload window, which
   the walk never reads as a lead — an artifact of the offline
   predictor, which enumerates every candidate node.)
   Every other adjudication kind is unmoved, including W-61's
   `no_parse_unstructured_renumber_arity_mismatch_skipped` at 8 and
   W-75's `no_parse_substitution_announcement_not_lowered` at 17.
   Ops **27,099 → 28,246**. On a CONTENT-keyed identity diff: 1,361
   gained (1,147 RENUMBER + 214 INSERT), 214 lost (all REPLACE) —
   and the 214 are the same ops, promoted. The shipped
   `_promote_no_replace_with_following_renumber_insert` wakes up by
   design: a co-located "§ X <ord> ledd skal lyde:" beside a
   relabel that moves that same ledd is an INSERT of new content
   plus a shift, not an overwrite-then-move. Semantically 0 lost, 0
   rebound.
   **Blast (all 783 base laws, against a pristine checkout of
   `80596cb5a`).** The RAW surface moves on 158 laws and that
   number is worthless: op_id is a per-document ordinal, and a
   PARSE-phase adjudication is a property of the INSTRUMENT that NO
   attaches to every base act that instrument amends. Normalized
   for both, **59 laws move, ALL 59 inside the derived
   expected-change set, 0 outside, 724 byte-identical**; 52 laws'
   TEXT moves. Amended-law population **783 → 784**:
   `no/lov/2017-06-16-53` enters on its first lowered op. Entries
   2,563 → **2,565** (`2001-06-15-33`, `2005-06-17-98`, both
   gaining their first op; none leave), bindings 6,484 → **6,493**,
   +9 and 0 lost.
   **Scan.** Candidates **76 unmoved element for element**,
   scoreboard **29/47/0 unmoved**, ceiling **1,011 unmoved**.
   Divergence total 1,501 → **1,491**, unexplained 490 → **480**:
   **12 rows closed, 2 opened**, over six laws —
   `no/lov/2019-06-14-21` (28→25), `no/lov/2004-12-17-101` (26→24),
   `no/lov/2017-06-16-65` (9→7), `no/lov/2015-02-13-9` (7→5),
   `no/lov/2010-06-25-28` (27→26), `no/lov/2012-01-27-9` (5→5).
   Both entrant rows are adjudicated. `2012-01-27-9` § 46 fjerde
   ledd goes OPS_MISSING → MISMATCH — the ledd EXISTS now and its
   text matches the consolidation except for a trailing full stop
   the published text drops, so the row kind is an improvement, not
   a regression. `2015-02-13-9` § 3 sjette ledd opens OPS_MISSING
   because the ONE remaining unlowered instruction on that section
   is `2023-06-16-34`'s "Nåværende § 3 femte ledd blir sjette ledd
   og skal lyde:" — the shift-plus-payload family, refused by this
   grammar's anchored tail by construction. It was invisible while
   the whole ledd sequence was out of step; it is visible now
   because everything around it is right.
   **W-72's entrant rows, answered honestly.** W-72 traced 5 of
   `no/lov/2015-02-13-9`'s 7 unexplained rows to this item. Three
   close. The other two are § 2's, not § 3's, and were never this
   item's. With the recovery arm this law went 7 → 3; the refusal
   arm costs it two rows, and that is the trade the stop condition
   demands: two divergence rows are worth less than two provisions
   of in-force law.
   **Hazard census moves and is re-pinned, not silently
   overwritten.** Destructive writes 3,706 → **3,809** across 26 of
   the 161 hazard laws, membership unchanged — a RENUMBER is a
   destructive write by that census's definition, and 103 of the
   new legs land in known-incomplete bases. Content-removing 167 →
   **168**, and the +1 is not a relabel op at all:
   `no/lov/2016-05-27-14` gains `no/lovtid/2021-12-22-158:1`, a
   REPEAL of § 7-6 annet ledd that could not bind before because
   that law's ledd sequence was one slot out of step. An amendment
   finally taking effect. Known-incomplete bases 198 → 199 and the
   sweep's law count 783 → 784, both the new entrant.
   **Two corpus pins hold the positive fact**
   (`test_no_w66_relabel_refusal_keeps_two_live_provisions_standing`):
   straffeloven 2005 § 3 femte ledd and verdipapirhandelloven
   § 9-21 fjerde ledd must be at their consolidation addresses, the
   refusal receipt must be present and blocking, and the
   occupied-destination firing list for each law must be exactly
   what the verdict table says — so a regression in either
   direction is loud.
   **What is deliberately left refused, with its size.** (a) The
   currency qualifier is REQUIRED: "Femte ledd blir nytt sjette
   ledd." (55 further leads) says nothing about which edition its
   ordinals are read against, and reading the source set against
   the pre-operation snapshot is this production's premise — a
   production may not assume the premise it exists to honour.
   (b) Depths other than `ledd` (punktum, bokstav, nr) are a
   different address arithmetic and are not in this population.
   (c) The 40 receipt triples (37 distinct leads) whose address the
   immediate antecedent cannot supply could largely be recovered by
   a deeper "last § named in this part" carry; not taken, because
   crossing a law switch silently is exactly the risk the
   immediate-predecessor rule structurally excludes.
   **Report-only findings.** (i) **The sizing in this entry's own
   prior text was wrong twice.** "Closes 13/16 of the triaged
   sample" understates the family by a factor of ~40 — 622 leads,
   not 13 — and the parenthetical calling the payoff witness a 2→3
   unequal-arity shape is incorrect: "Nåværende § 3 femte og sjette
   ledd blir sjette og nytt syvende ledd." is a 2→2 bijection with
   the newness marker on the second destination, which W-56's
   ordinal vocabulary already strips. **No unequal-arity relabel
   occurs anywhere in the accepted population**, confirming W-62's
   corrected premise rather than W-57's original one. A third
   correction, found by sampling 30 inherited cases before trusting
   the reader: the first cut of the section-address regex spelled
   its letter suffix `(?:\s*[A-Za-z])?` and therefore read
   "§ 12-1 nytt tredje ledd" as section "12-1 n" — a section that
   does not exist — on 25 of the 30. The shipped reader carries a
   negative lookahead and a test. (ii) **Rider
   2's named target cannot be reached by intra-part ordering, and
   the reason is measured.** W-74 left three cross-chapter shifts
   on `no/lovtid/2015-04-10-17` refused because nothing proves
   §§ 2-2/2-3/2-6 are free. The op that vacates them is "Kapittel 2
   oppheves." — a CHAPTER repeal, and no production lowers it: of
   the 90 ops that instrument lands on `no/lov/2005-06-10-44`, none
   is a chapter repeal. Widening W-74's destination-vacated
   conjunct to see co-located repeals in the same part would
   therefore unlock nothing; the blocker is a chapter-repeal
   production with its own blast radius. Recorded, not attempted.
   (iii) Noted while measuring (ii): TWO cross-chapter shifts in
   that same part ALREADY land with no vacancy proof at all —
   `§ 7-8 → § 2-4` and `§ 7-13 → § 2-9`, from the shipped
   `Nåværende § X blir ny § Y` production, and the first of them is
   pinned firing `2015-04-10-17:30`. The corpus is already
   inconsistent about this class; W-74's conjunct constrains only
   the leads that happen to carry a repeal sentence. (iv) The
   hyphenated-`til`-range endpoint limitation
   (`_expand_no_section_range_labels`) is untouched; a label
   -sequence oracle over the pre-op snapshot's sibling list is
   still the only way to widen it. (v) **A general hazard this item
   ran into head-on and does not fix:** archived base editions that
   already carry the amendment being replayed. Both `removal_wrong`
   findings are that shape, and the apply-plane refusal contains
   the damage rather than curing it. Worth an item of its own.

   **Item (b) is now OPENED AND PRICED as W-66b (queue item 76
   below), and it is not the small residue this entry implies:** the
   same grammar at PUNKTUM depth is **144 refusals / 63 distinct
   leads / 100 instruments / 69 base acts**, roughly twice all three
   of W-69's relocation arms combined (W-69's design pass, 2026-08-12).

67. **W-67 (the two-token widening):** DONE (`cf751dd2b`,
   2026-08-11; landed TOGETHER with W-74, artifacts `.tmp/w74/`).
   It was BLOCKED for a day on an adjudicated regression, and the
   record of that block is kept below in full because it is the
   reason the item took the shape it did. See the **2026-08-11
   UNBLOCK ADDENDUM** at the end of this entry for what the composed
   landing measured; everything between here and there is the
   2026-08-10 blocked-state reading, preserved as written.
   **What was built.** The shipped section renumber required two
   tokens that carry no address information: the literal
   `Nåværende` and the literal `ny` in `blir ny §`. Both relaxed —
   qualifier to W-61's measured set (hoisted to a shared
   `_NO_CURRENCY_QUALIFIER_ALTERNATION`, byte-identical to W-61's
   inline copy, so neither production can drift alone), `ny`
   optional in the masculine singular only. **Strictly additive in
   W-61's shape:** `_no_unstructured_section_renumber_labels`
   tries the shipped regex first, character for character, and
   returns WHICH pattern matched so the ordering is a test's fact
   rather than a comment's claim.
   **Measurement (census over all 3,089 artifacts, `s1`/`s3`/`s5`).**
   Refusals **9,454 → 9,390, exactly −64 and nothing else**; 0
   introduced. The withdrawn set EQUALS the frozen target set,
   element for element: 64 occurrences, 62 distinct leads, 44
   instruments, 44 base acts, **100% `renumber_shift/
   section:nåværende:single` and ZERO stray matches** — the first
   stop condition, checked and clear. Split by token: 20 need only
   the qualifier, 36 only the optional `ny`, 8 both. Every other
   adjudication kind is unmoved, including the W-61 pin
   `no_parse_unstructured_renumber_arity_mismatch_skipped` at 8.
   Ops 27,018 → **27,082**, semantically 0 lost / 0 rebound (the
   op-identity diff is keyed on CONTENT, not `op_id` — `op_id` is a
   per-document sequence, so 709 ids over 37 instruments remap as
   pure ordinal churn and a key-on-`op_id` diff reports that as
   709 false regressions).
   **A shipped post-pass wakes up, by design.** 11 of the 64 have a
   companion `§ X skal lyde:` in the same part, so
   `_promote_no_replace_with_following_renumber_insert` now sees
   the renumber it always looked for and promotes those REPLACEs to
   INSERTs. That is the promotion's documented purpose: the act
   inserts new content at X and MOVES the old X, and before this
   change the old X was silently overwritten instead.
   **Blast (782 laws, W-52 discipline).** 764 byte-identical; 18
   move. **13 are outside the 44-law expected-change set and their
   movement is fully attributed and inert** (`s8`): a withdrawn
   refusal receipt belonging to a CO-AMENDED base act — parse
   adjudications are collected per INSTRUMENT and replay attaches
   the whole list to every law that instrument amends — plus
   `op_id` ordinal shift. Normalising both away leaves **residue 0
   on all 13**, and no `statute_sha` among them moves. Candidate
   divergence total **1,485 → 1,483**, and the two rows that close
   are both UNEXPLAINED (1,011 + 474 → 1,011 + **472**; the ceiling
   is untouched), which is the class the lane exists to reduce.
   Scoreboard 29/44/0 held (29 consistent, 44 inconsistent, 0
   errored, both sides). **The designed payoff landed exactly**:
   `no/lov/2010-06-04-21`
   3 → 1 divergences, both `OPS_MISSING` rows
   (`chapter:10/section:10-13/subsection:1` and `:2`) CLOSED, 0
   opened, on the ledger's own witness
   `Gjeldende § 10-10 blir ny § 10-13.` — verified at the DOM as a
   leaf `<article class="defaultP">` in part `kapV` of
   `2020-12-18-157`, not a text-plane artefact.
   **Why it is blocked.** THREE laws' text moves and each fires the
   occupied-destination recovery for the first time, corpus firings
   **8 → 11**. Adjudicated W-54-style (`s9`/`s10`/`s11`):
   * `no/lovtid/2022-03-11-8:25`, merverdiavgiftsloven § 7-9 → 7-8
     — **`removal_correct`**. The occupant is the § 7-8 the SAME
     act repeals ("Nåværende § 7-8 oppheves."), absent from the
     consolidation. Divergences 256 → **254**.
   * `no/lovtid/2019-06-21-41:2`, verdipapirhandelloven § 4-3 → 4-2
     — **`removal_correct`**. The removed flagging text is still at
     § 4-2 in the fixed replay and matches the consolidation;
     nothing destroyed, divergences unmoved at 1,564.
   * `no/lovtid/2017-06-21-96:4`, husbankloven § 10 → § 13 —
     **`removal_wrong`. STOP CONDITION.** The recovery destroys
     § 13 "Ikraftsetjing o.a", which IS in the published
     consolidation and survives NOWHERE in the fixed replay.
     Divergences **3 → 6** (three new `MISMATCH` rows at
     `section:13/subsection:1..3`).
   **The root cause is not the widening.** The instrument is
   correctly bound and genuinely says "Noverande § 10 blir ny
   § 13."; what is wrong is the BASE it lands on.
   `no/lovtid/2012-08-24-64` (bustøttelova) is SCANNED but NOT
   APPLIED, so the replay base is still the 2009 original in which
   "Noverande § 10" denotes the bustønad section rather than what
   actually stood at § 10 in 2017. The law is
   `blocked_contingent` — the system already knows the base is
   incomplete — and lowers a destructive write into it anyway. A
   correct op applied to an incomplete base is how coverage turns
   into destruction, and no guard belongs in this production:
   suppressing the renumber when its destination is occupied would
   change the SHIPPED pattern's behaviour too.
   **The tripwire did not catch this, and that is its own finding
   (→ W-72).** `_NO_OCCUPIED_DESTINATION_LAWS` is a hardcoded
   seven-law list, so
   `test_no_corpus_occupied_renumber_destination_verdicts_are_pinned`
   sweeps 7 of 782 laws while its docstring claims "every
   `(RENUMBER, dest_occupied)` firing in the corpus". None of the
   three new firings is on a listed law, so **`wrong == []` still
   passes and the whole ladder is GREEN with a destruction in the
   corpus.** The verdict tables were deliberately NOT extended
   here: adding the `removal_wrong` row would freeze a known defect
   as expected behaviour, which is exactly what W-54's note
   forbids.
   **Pins moved** (all in the archived patch, none in the tree): `n_ops` 27,018 → 27,082;
   entries 2,560 → 2,561; bindings 6,476 → **6,477**
   (one new (act, law) pair, `2004-09-24-72` → plan- og
   bygningsloven 1985, whose only operative lead is
   "Nåværende § 16 blir § 16-1."); declared-target gap 956 → 955
   receipts and 2,524 → 2,523 pairs, the W-34/W-35 conservation
   holding at 1 = 1; `instrument_authorized` 971 → 972 (958 → 959
   non-staged, staged 13 unmoved) and the widened whole-act route
   430 → 431 in all four places it is pinned (`test_norway_index`
   twice, `test_norway_commencement_instruments` twice — the W-51
   five-route census and the W-53 zero-early sweep, whose property
   holds over the grown set). Scan pins: divergence totals
   1,485/1,011/474 → **1,483/1,011/472**, and
   `no/lov/2010-06-04-21` moves partition bucket `replay_defect` →
   `untouched_drift` (21 → 20 and 18 → 19) — with no `OPS_MISSING`
   row left it is not a replay defect any more, the W-23 predicate
   doing what it was built for. `scanned_count` 73 and summary
   29/44/0 unmoved.
   **To unblock:** repair husbankloven's missing
   `2012-08-24-64` application (that is a base-completeness item,
   not a lowering one), then re-run `.tmp/w67/s6`/`s9`/`s11` and
   confirm firing 1 either vanishes or re-adjudicates
   `removal_correct`. Everything else in this item is measured and
   ready.
   **W-73 UPDATE (2026-08-11): the unblock condition is NOT yet
   met, and the premise above was half right.** W-73 repaired the
   commencement gap — `2012-08-24-64` is now
   `instrument_authorized` at 2013-01-01 and APPLIED to
   husbankloven — and re-ran the verification with both patches
   together (they compose cleanly). The firing did not vanish and
   did not re-adjudicate: § 13 "Ikraftsetjing o.a" is still
   destroyed, still absent from the replay, still present in the
   consolidation. Husbankloven 6 → 5 divergences, corpus firings
   still 11 with no new ones. The reason is a SECOND gap W-67's
   root-cause reading did not see: applying the act is not the same
   as applying its ops, and the one op that vacates § 13
   (`§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 10.`)
   is a two-sentence run-on the unstructured grammar refuses. **The
   unblock condition is now W-74, not W-73**; everything else in
   this item remains measured and ready, and it must not land
   before W-74 does.
   **2026-08-11 UNBLOCK ADDENDUM — the condition is MET and the item
   is landed (`cf751dd2b`, with W-74, artifacts `.tmp/w74/`).** The
   unblock path is the two items above it in the queue, in order:
   W-73 made `no/lovtid/2012-08-24-64` commence, and W-74 made its
   third change block LOWER. With both, §§ 10–12 are repealed and
   § 13 → § 10 applied in 2012, so this item's 2017 renumber
   § 10 → § 13 lands on a FREE destination.
   **The husbankloven firing does not re-adjudicate — it VANISHES.**
   Corpus firings 8 → 10 (swept over all 782 laws, not the
   tripwire's seven), and husbankloven is not among them. W-54's
   survival test passes on it: § 13 "Ikraftsetjing o.a" is in the
   replay at `section:13/subsection:1` and `:2` and matches the
   consolidation, all 13 sections align, and its divergence rows are
   **byte-identical to base at 2 → 2** — the three
   `section:13/subsection:1..3` MISMATCH rows this item used to open
   never open. The repair is at the LOWERING, which is what W-67's
   own blocked-state reading argued for ("no guard belongs in this
   production"); the recovery is untouched and simply has nothing to
   fire on.
   **The other two firings re-adjudicate exactly as measured here:**
   merverdiavgiftsloven `no/lovtid/2022-03-11-8:25`
   **`removal_correct`** (256 → 254 divergences) and
   verdipapirhandelloven `no/lovtid/2019-06-21-41:2`
   **`removal_correct`** (unmoved at 1,564). Both are now pinned in
   `_NO_OCCUPIED_DESTINATION_VERDICTS` with their occupant probes and
   observed survival sets; `wrong == []` holds over a table of 10.
   **One measurement note, because it changed a verdict's EVIDENCE
   and nearly its reading.** The pin's survival check matches a probe
   against each node's OWN text, not against its descendants
   concatenated, and the first cut of both rows used descendant text
   — a probe that helper can never find, which failed the pin loudly
   rather than passing a false one. Re-derived from single nodes, the
   verdipapirhandelloven occupant is unambiguous: all FIVE ledd of
   § 4-2 are at their own addresses in the replay and match the
   consolidation. Merverdiavgiftsloven needed more care. Its § 7-8
   first ledd opens with boilerplate ("Departementet kan gi forskrift
   om at det ikke skal beregnes merverdiavgift ved …") that § 7-6
   carries VERBATIM, so a ledd probe hits § 7-6 on both sides and
   discriminates nothing — the same trap the skattebetalingsloven pin
   records for § 8-3. The pinned probe is therefore the § 7-8 HEADING
   ("varer av utdannende, vitenskapelig og kulturell art"), which
   names what the section was about and is absent from the replay AND
   from the consolidation. The verdict is unchanged; the evidence
   behind it now actually supports it.
   **Everything else in this entry re-measured TRUE at the composed
   base**, which is the check the archived patch owed after two later
   landings: refusals −64, 0 introduced, with the withdrawn set still
   EQUAL to the frozen 64-element target set element for element (so
   the "100% `renumber_shift/section:nåværende:single`, 0 strays"
   claim carries over with the SET, rather than being re-derived from
   the family census); 11 REPLACE → INSERT promotions, every one
   attributed to a target lead; the 13 outside-set movers unchanged
   with residue 0; and the designed payoff landing —
   `no/lov/2010-06-04-21` 3 → 1, both `OPS_MISSING` rows closed.
   **The "Pins moved" paragraph earlier in this entry is STALE and
   its numbers were re-derived rather than replayed**: W-61 and W-73
   moved the base under them between the measurement and the landing.
   The landed numbers are ops 27,018 → 27,100 (this item's +64
   plus W-74's +18), entries 2,560 → 2,561, bindings 6,476 → 6,477,
   declared-target gap 956 → 955 / 2,524 → 2,523,
   `instrument_authorized` **976 → 977**, widened whole-act route
   **435 → 436**, and scan totals **1,512/1,011/501 →
   1,510/1,011/499** with candidates unmoved at 76 and the scoreboard
   unmoved at 29/47/0. The partition move is the one this entry
   predicted, at its new numbers: `replay_defect` → `untouched_drift`,
   23 → 22 and 19 → 20.

74. **W-74 (the SECTION-level repeal-then-shift run-on — the real
   W-67 unblock condition):** DONE (`cf751dd2b`, 2026-08-11; landed
   TOGETHER with W-67, artifacts `.tmp/w74/`). Originally from W-73,
   which measured it and did
   not fix it (the lane is lowering-grammar, not the commencement
   lane W-73 was scoped to, and it edits the exact grafter region
   W-67's archived patch also edits — a composition hazard worth
   sequencing rather than racing).
   **The shape.** One lead, two sentences: a section-list repeal
   followed by a section shift into a slot the repeal just vacated.
   `no/lovtid/2012-08-24-64`'s
   `§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 10.`
   is the witness, and it is refused outright
   (`no_parse_unstructured_lead_unmatched`) because every shipped
   section-repeal pattern is anchored `oppheves\.?$` and every
   shipped renumber pattern is anchored `^Nåværende`.
   **It is precedented, which is what makes it cheap.** The LEDD
   -level sibling of exactly this family already ships and W-61
   already widened it:
   `^§ X <ord> ledd oppheves\. <qualifier>? <ord> ledd blir <ord> ledd$`
   is read as ONE combined pattern rather than by splitting
   sentences. This item is that production's section-level analogue,
   so no general sentence-splitter is needed.
   **Measured population: 10 leads corpus-wide** over the 9,454
   unmatched (8 instruments, 7 base laws), enumerated in
   `.tmp/w73/lead_census.json`.
   **The safety restriction, and it is what makes the item
   landable:** accept only where the shift's DESTINATION is a label
   the SAME lead repeals. That makes the production self-proving —
   it can never write into occupied law, which is precisely W-54's
   concern and precisely what went wrong on husbankloven. Under it
   **7 of the 10 accept** (`2003-12-12-105`, `2012-08-24-64`,
   `2013-06-14-40`, `2015-04-10-17`×1, `2016-04-22-5`,
   `2020-05-20-42`, `2022-06-17-47`) and **3 refuse** — all three
   `2015-04-10-17` cross-chapter shifts (`§ 7-1 oppheves. Nåværende
   § 7-2 blir ny § 2-2.` and siblings), whose destination the lead
   does not vacate and which therefore keep their existing refusal
   receipt honestly.
   **Dependency and sequencing.** The shift sentence needs W-61's
   currency-qualifier set and W-67's optional `ny`, so this item
   should land WITH or AFTER W-67 and reuse
   `_NO_CURRENCY_QUALIFIER_ALTERNATION` rather than minting a
   second copy. Landing W-74 is what turns W-67's husbankloven
   firing from `removal_wrong` into a non-firing: with §§ 10–12
   repealed and § 13 → § 10 applied in 2012, the 2017 renumber
   § 10 → § 13 lands on a FREE destination.
   **THE LANDING (2026-08-11).** The sizing above held on every
   axis; what follows is what was measured rather than predicted.
   **The shape, as built.** One anchored production —
   `_no_unstructured_section_repeal_renumber_labels` — placed LAST in
   the unstructured walk, immediately before the refusal, so it is
   reachable only on a lead every shipped pattern has already
   declined. It is the ledd-level sibling's analogue member for
   member: its own combined regex over both sentences, its own
   optional currency qualifier taken from the shared
   `_NO_CURRENCY_QUALIFIER_ALTERNATION` (W-67 hoisted it; no second
   copy exists), W-67's optional `ny` on the shift half, and
   W-32(c)'s `(?:\s+[A-Za-z])?` label suffix so "§ 3 i" resolves its
   section. Three details are load-bearing and each is pinned by a
   test rather than asserted in a comment: the repeal list is
   captured by a bounded character class with `§` and `.` OUTSIDE it,
   which is what refuses the four corpus leads that put the shift
   sentence FIRST — by construction, not by a guard; the label class
   is DIGIT-INITIAL, unlike the shipped `[0-9A-Za-z-]+`, so a bare
   word like "siste" cannot enter the repeal set and then satisfy the
   destination conjunct against itself; and the list parser is
   all-or-nothing, refusing the whole lead on one member it cannot
   read rather than repealing the members it happens to understand.
   Op ORDER is load-bearing too: every REPEAL is minted before the
   RENUMBER, at a lower sequence in the same group, so the
   destination is provably free by the time the shift applies.
   **The population, re-measured at the landing base: 10 leads, 7
   instruments, 7 base laws.** The sizing said 8 instruments; the
   corpus says 7 — `no/lovtid/2015-04-10-17` carries four of the ten
   by itself, which is where the extra instrument came from. 7
   accept, 3 refuse, exactly the split and exactly the members the
   sizing named. Five NEIGHBOURING corpus leads carry both verbs and
   are not this family — four with the shift sentence first, one with
   a trailing payload ("… blir ny § 27 og skal lyde:") — and all five
   are refused; lowering a shift whose lead also announces a payload
   would state a half-truth, which is the ledd sibling's own
   conservative polarity.
   **Measured.** Refusals −7 on top of W-67's −64 (composed 9,454 →
   9,383, 0 introduced, and the two halves partition the withdrawn
   set exactly). Ops +18: 11 REPEALs and 7 RENUMBERs. **Zero strays**
   — every withdrawn refusal is one of the 7 named leads, and the 3
   cross-chapter leads keep their receipt.
   **Blast: W-74 adds no outside-set mover at all.** The 13
   outside-the-expected-set movers in the composed blast are exactly
   W-67's 13, residue 0. W-74's own payoff is on
   `no/lov/2005-06-10-44`: 612 → **607 divergences, 5 rows closed, 0
   opened**, at the § 1-2 / § 1-7 / § 1-8 addresses its accepted lead
   names. Its other six accepted leads move no divergence row —
   three of their base laws have no current bytes at all (the
   sparse-source class, F-09) and the rest are `blocked_contingent`
   for unrelated reasons — so the coverage is real but only one law
   is in a position to show it today.
   **The reason the item exists, delivered.** Husbankloven's firing
   vanishes, § 13 survives, and `removal_wrong` is empty corpus-wide;
   the full firing census is in the W-67 unblock addendum above. A
   new corpus pin,
   `test_no_husbankloven_13_commencement_provision_survives`, holds
   the positive fact the way W-56 and W-61 hold theirs — both § 13
   probes must hit at their consolidation addresses AND the firing
   list must be empty, so a regression in either direction is loud.
   **Report-only findings, not fixed here.** (a) A `til` RANGE over
   HYPHENATED labels ("§§ 1-2 til 1-7") resolves to its two
   ENDPOINTS, because `_expand_no_section_range_labels` only expands
   pure-digit ranges. That is the SHIPPED standalone range-repeal's
   behaviour, reused verbatim rather than forked, and it
   under-repeals (§§ 1-3 to 1-6 are left standing). Under-repealing
   is the safe direction, and the destination conjunct is evaluated
   against the same set the REPEAL ops are minted from, so the two
   can never disagree. Widening it needs a label-sequence oracle,
   which is W-66 territory. **W-66 landed and did NOT take it**;
   the oracle is still unbuilt and the limitation stands as
   written. (b) The three refused cross-chapter
   shifts are a genuine coverage gap rather than noise:
   `no/lovtid/2015-04-10-17` moves §§ 7-2/7-7/7-10 into chapter 2
   slots the lead does not vacate, and proving those destinations
   free needs the co-located repeals elsewhere in the same act — the
   intra-part ordering rider W-66 already carries. **W-66 measured
   that rider and it does not reach these three, so they stay
   refused: the op that vacates §§ 2-2/2-3/2-6 is "Kapittel 2
   oppheves.", a CHAPTER repeal, and no production lowers it (of
   the 90 ops that instrument lands on `no/lov/2005-06-10-44`, none
   is a chapter repeal). Seeing co-located repeals would unlock
   nothing here; the blocker is a chapter-repeal production. W-66
   also recorded that TWO cross-chapter shifts in that same part
   already land with no vacancy proof at all (`§ 7-8 → § 2-4`,
   `§ 7-13 → § 2-9`, from the shipped `Nåværende § X blir ny § Y`
   production; the first is pinned firing `2015-04-10-17:30`), so
   the destination-vacated conjunct constrains only the leads that
   happen to carry a repeal sentence.**

72. **W-72 (the occupied-destination tripwire sweeps 7 of 782):**
   DONE (`c80ce0a6a`, 2026-08-11; artifacts `.tmp/w72/`). Tests,
   tooling and receipts only — **no product behaviour changed, and
   none needed to**. The `(RENUMBER, dest_occupied)` claim in this
   ledger may now be read as corpus-wide, over 779 of the 783 base
   laws, with the other four NAMED rather than rounded off.
   **The design decision, and why the obvious receipt is the wrong
   one.** The item's own sketch offered two routes: derive the law
   list from a corpus sweep (slow), or cache a sweep whose staleness
   is receipted. The sweep is 10 CPU-minutes over 783 laws — 3m28s
   wall at 10 processes — against a ~15-minute budget for the whole
   27-file norway shard, so it is cached, in
   `tests/data/no_occupied_destination_sweep_baseline.json`, written
   by `scripts/inventory_no_occupied_destination_sweep.py
   --update-baseline`. The sketch proposed CORPUS CONTENT as the
   staleness receipt, and **that receipt alone would have been worth
   nothing here**: W-67 did not touch the archive, it changed the
   parser, so a corpus-only check would have gone on passing exactly
   as the seven-law list did. The baseline therefore carries TWO
   digests and the test recomputes both:
   * **corpus identity** — every artifact in all four Norway planes
     as `(logical_id, sha256(payload))`, digested per plane
     (`original_lti` 3,089 / `amendment` 3,089 / `forskrift` 35,955
     / `current` 763). Logical rather than a hash of the
     `.farchive` file, which is WAL-mode SQLite: a VACUUM or a
     recompression would move a file hash without moving a byte of
     law, and a tripwire with false alarms teaches people to
     regenerate without reading, which is the only way this
     mechanism can be defeated.
   * **code identity** — sha256 of every source file in the STATIC
     IMPORT CLOSURE of `lawvm.norway.replay` / `.index` /
     `.inventory`, derived by AST walk over every import node
     (including function-local ones, which this codebase uses
     heavily) rather than hand-listed. **79 modules, 2.3 MB, 0.3s.**
     Derived and not declared is the load-bearing property: a new
     dependency can only enter the closure through an edit to a
     module already inside it, which moves the digest on its own.
     It stays inside the lane — no Finland, Sweden, UK, EE, EU, NZ
     or US module is in it — so a neighbouring frontend's patch does
     not redden Norway.
   Those two plus the pinned `as_of` and the determinism firewall
   fix the answer. Cost at norway-shard time: **2.5s** for the two
   digests; the three assertions that read the cache are ~0.01s
   each. The full sweep ran three times over the item and returned
   the identical census every time.
   **What it proves, and the honest limit.** 10 firings corpus-wide,
   equal element for element to `_NO_OCCUPIED_DESTINATION_VERDICTS`
   — so the 10 rows the table already carried ARE the corpus, which
   is what the item had to check first and what nobody could check
   before. `wrong == []` now holds over the corpus rather than over
   nine laws. **The sweep also found its own blind spot and it is
   four laws wide**: `no/lov/2003-07-04-74`, `no/lov/2005-06-17-62`,
   `no/lov/2009-06-19-44` and `no/lov/2015-04-10-17` abort mid-apply
   on a replay invariant violation, which discards the apply plane's
   receipts and adjudications, so whether they fire is genuinely not
   observable; three of the four do receive RENUMBER ops (the fourth
   receives none and cannot fire at all). That is tolerable and
   still pinned: a firing can only destroy in-force law inside a
   replayed statute and these four produce none, so the moment one
   is repaired it leaves the set, the equality fails, and its
   firings get adjudicated before anything can go green on them. The
   other 440 errored laws error BEFORE any op is applied (F-09's
   sparse-source class), which is a complete answer rather than an
   unobserved one — the sweep separates the two rather than
   reporting one error count.
   **ONE OF THE FOUR IS NOW ROOT-CAUSED, and the cause is a
   soundness defect in a lowering that already ships** (W-69 design
   pass, 2026-08-12; `.tmp/w69/design.md` §4.2). `no/lov/2009-06-19-44`
   aborts with `Norway replay invariant violation after renumber
   (('section','2'),('subsection','3')) from no/lovtid/2025-06-20-42:
   body/section:2: duplicate subsection:4 (2 times)`. Two RENUMBERs
   from one instrument collide: a CROSS-CONTAINER in-migration
   (`§3/ledd/3 → §2/ledd/4`, minted today by the structured
   `data-move-part` lane — the apply plane's RENUMBER branch resolves
   `op.destination.parent()` and re-parents, so it IS a relocation)
   and the destination parent's OWN vacate shift
   (`§2/ledd/3 → §2/ledd/4`). The migration runs first, creates
   `§2/ledd/4`, and the shift then lands on it. **W-66's ordering
   machinery cannot see this and does not generalize as written**:
   `_no_ordered_set_relabel_pairs` takes `Sequence[tuple[int, int]]`
   — integer ordinals inside ONE sibling set — while a
   cross-container move belongs to TWO, and the leg that frees its
   destination lives in the other one. The kernel's independent
   `renumber_vacate=True` stage did not catch it either, so the
   two-stages-agree-by-construction property W-66 relies on is not
   holding here. The fix is W-69c (dependency nodes keyed on the
   resolved `(parent_path, label)` pair, spanning the whole atomic
   group across parents; cycle guard unchanged), and its payoff is
   exactly this: **the blind-spot set goes 4 laws → 3 and this law's
   occupied-destination behaviour becomes observable.** Corpus-wide
   the structured lane mints **14 genuinely cross-container legs**
   (`.tmp/w69/fullleads.json`), so this is a live population and not
   a single-law curiosity. It also settles a standing question the
   other way round: no widening may mint further cross-container
   RENUMBERs before W-69c lands, because converting a parse refusal
   into a mid-apply abort is strictly WORSE — an abort discards the
   law's entire receipt and adjudication plane, which is this item's
   own finding.
   **RESOLVED at W-69c (item 79, `d5699c464`), with the root
   cause corrected.** The two legs are not reorderable but MUTUALLY
   UNSATISFIABLE — the instrument's §3 `data-move-part` attribute
   names the wrong destination section (its annotated prose says an
   intra-§3 shift), so two legs claim `§2/ledd/4` and no permutation
   satisfies both. The kernel's `renumber_vacate` stage worked as
   designed and IS keyed on full paths; what it cannot do is report
   "no order exists" — a topological sort can only answer with a
   permutation, and it has no `by_destination` map to notice a
   contest with. The fix is a provability TEST at the apply seam
   (union-find components over `(parent_path, label)`; contested
   destination, contested source, or cycle refuses the component
   whole, typed, before any write), which un-aborts the law:
   **blind spot 4 → 3, this narrative's prediction honoured — the
   law left the set and its firings were adjudicated (zero new
   firings; all six legs refuse before the θ cell)**. The
   standing prohibition above is DISCHARGED; W-69d is unblocked.
   The design's "14 cross-container legs" re-measures as **7** at
   the post-W-70 base (the separator repair changed the population).
   The design artifact's ordering framing is superseded by item 79.
   **The honesty repair, which is the part the item is named for.**
   `test_no_corpus_occupied_renumber_destination_verdicts_are_pinned`
   said "every `(RENUMBER, dest_occupied)` firing in the corpus"
   while replaying nine laws. Its docstring now says what it does —
   it owns EFFECT (what each firing did to the occupant's text, from
   a live replay) — and the new
   `test_no_corpus_wide_occupied_destination_firings_are_all_adjudicated`
   owns POPULATION (which firings exist, corpus-wide, from cached
   evidence). Neither is redundant and neither claims the other's
   half. A third test,
   `test_no_occupied_destination_sweep_agrees_with_the_live_replay`,
   re-derives the nine replayed laws' firings and compares them to
   the cache, so "identical corpus plus identical code gives
   identical firings" is CHECKED where a live replay is already
   being paid for, not merely argued from the receipt.
   **Guard liveness, because a staleness check nobody has seen fail
   is indistinguishable from one that cannot.** Three corpus-free
   tests: the comparison reports a moved corpus and a moved module
   separately and NAMES what moved; the closure provably contains
   `norway.grafter`, `norway.commencement`,
   `norway.totalization_table`, `core.totalization` and
   `core.apply_seam` (a walker that quietly resolved nothing would
   produce a stable digest and a tripwire that never fires — passing
   for the worst possible reason); and the regenerate instruction
   every failure prints names a script that exists. Verified
   end-to-end too: appending one comment line to `grafter.py` fails
   the pin in 3.3s with "THE REPLAY PATH MOVED … Modules that moved
   (1 of 79): lawvm.norway.grafter".
   **(b) The known-incomplete-base hazard, now ladder-visible.**
   W-73's rider (d) was a number in a `.tmp` artifact that could
   drift with every archive refresh. It rides in the SAME replay
   pass — same 783 laws, same staleness receipt, zero extra cost —
   and is pinned by equality in
   `test_no_incomplete_base_destructive_write_census_is_pinned`:
   **198 known-incomplete bases, 265 taking destructive writes, 161
   in the intersection, 3,713 destructive writes of which 167
   REMOVE content across 65 laws**, plus a content hash of the
   per-law list so membership cannot churn under stable counts.
   W-73 measured 163 / 3,737 / 159 over 64 across 782 bases; the
   whole delta is attributable and conserves exactly — the three
   laws W-73 moved out of `blocked_contingent` (`2015-02-13-9`,
   `2015-06-19-70`, `2020-06-19-77`) LEAVE the set,
   `no/lov/2020-05-07-40` ENTERS it by gaining a destructive write,
   163 − 3 + 1 = 161. The pin is a census receipt, NOT an
   expected-behaviour freeze: 161 laws in this posture is a finding
   held open, and refusing those writes stays out of scope as a
   product change with its own blast radius. **Husbankloven is still
   in the set** — 8 destructive writes, 3 content-removing — because
   W-73 repaired the commencement of one amendment while
   `no/lovtid/2025-04-25-12` is still contingent. § 13 survives
   today because W-74 repaired the specific op, but the POSTURE that
   destroyed it is unchanged on that very law, and reading the green
   ladder as "husbankloven is safe" would repeat W-67's mistake one
   level up.
   **(c) Rider — the 27 entrant rows, and it did not stay a triage.**
   The three laws W-73 admitted are `no/lov/2015-02-13-9` (7 rows),
   `no/lov/2015-06-19-70` (17) and `no/lov/2020-06-19-77` (3), all
   27 unexplained, 0 ceiling. Classified row by row from the
   instruments' DOM and the landed ops rather than from row text
   (`.tmp/w72/entrant_triage.json`): **7 reachable by an open item —
   5 by W-66 (`no/lov/2015-02-13-9` § 3's ledd sequence, offset by
   the refused "Nåværende § 3 femte og sjette ledd blir sjette og
   nytt syvende ledd.") and 2 by W-70 (karanteneloven § 8's
   malformed `data-move-part`) — and 20 reachable by no open item at
   all**, because they belong to a family nothing in the queue
   describes. **Opened as W-75, and 15 of the 20 are a live
   destruction of in-force law.** **W-66 settled its 5 on
   2026-08-12: three close, and the triage over-attributed by two —
   the other two rows are § 2's, not § 3's, and no relabel was ever
   going to reach them. One row OPENS in their place
   (`§ 3/subsection:6`, OPS_MISSING), and it is the residue the
   closure makes visible: `2023-06-16-34`'s "Nåværende § 3 femte
   ledd blir sjette ledd og skal lyde:" is shift-plus-payload, which
   W-66 refuses by construction. Net on the law 7 → 5.**
   **W-70 settled its 2 on 2026-08-12, and here the triage was
   exactly right: both rows close, 0 open, karanteneloven 14 → 12.**
   They are `§ 8/subsection:3` (MISMATCH/`text_drift`) and
   `§ 8/subsection:4` (OPS_MISSING/`replay_lowering_gap`), and they
   were ONE defect wearing two row shapes: with the malformed
   `data-move-part` refused, the block's INSERT of a new andre ledd
   landed on the live andre ledd and the insert-occupied recovery
   replaced it, so the old andre ledd was overwritten (row 1 reads
   the old tredje ledd's text at slot 3) and the fourth ledd never
   came into being (row 2). Normalizing the separator mints the two
   legs and both rows resolve together.
   No receipt-honesty-only rows: the
   `no_replay_*` adjudications on these laws (24 + 11
   `receipt_storage_path_projected`, 13 `sentence_children_
   materialized`, 1 `insert_occupied_target_replaced`) describe how
   landed writes were recorded, not writes that failed to land, and
   none of them corresponds to a divergence row. **The one
   exception is now closed rather than an exception: that single
   `insert_occupied_target_replaced` WAS karanteneloven's, and it
   was not receipt honesty — it was the recovery overwriting a live
   ledd. It withdraws at W-70 (corpus 138 → 137).**

75. **W-75 (multi-address `data-change-part` substitutions write the
   amendment's own address list into in-force law):** **DONE FOR THE
   SAFE DIRECTION** (`c36e2de13`, 2026-08-12; artifacts
   `.tmp/w75/`). The construct is refused with a typed receipt and
   107 destructive REPLACEs stop being minted; **lowering the
   substitution FOR REAL stays OPEN and is W-69's**, because it needs
   an op kind this vocabulary does not have. Sizing for that half is
   measured below and in `.tmp/w75/substitution_sizing.json`.
   **SUPERSEDED FOR THE OTHER HALF at W-69a** (item 77,
   `17e5dcfb4`), and the receipt count moves with it: this
   stopgap's **17 firings become 0**. The construct did NOT need a
   new op kind after all — an addressed `TEXT_PATCH` was already in
   the vocabulary with a shipped apply branch and no producer — and
   `no_parse_substitution_announcement_not_lowered` survives as the
   S3 conjunct alone (the announcement's pair grammar did not parse),
   whose only corpus node is refused one conjunct earlier by S2.
   A live guard with an empty population, not a dead receipt. The
   family's refusals are now 21 sentence-address + 1
   multiple-announcement + 1 multi-base, and 23 addresses lower.
   Three of the five bindings this item removed come back at W-69a,
   as real ops rather than destructive garbage.
   **The shape.** Lovdata renders a word substitution over many
   provisions as an ANNOUNCEMENT plus an ADDRESS LIST:
   `I følgende bestemmelser skal ordet «tilsettingsmyndigheten»
   endres til «ansettelsesmyndigheten»:` followed by the listed
   addresses. The list carries `data-change-part` naming every one of
   them, so the structured lane reads N targets and takes the node's
   OWN text — the announcement, the address list, or both — as the
   payload. Every op it mints overwrites a provision of in-force law
   with the amendment's own prose.
   **The family is 17 nodes, not the 4 W-72's census reported, and
   the correction is the item's main finding.** That census tested
   only the PRECEDING SIBLING, against four loose substring markers.
   It therefore missed the 13 nodes that carry the announcement in
   the change node's OWN text (`no/lovtid/2026-06-19-45` alone has
   six), and one of the 4 it did report
   (`no/lovtid/2025-06-20-38`) was a false positive whose long
   preceding sibling merely contained a marker. Re-probed at the DOM
   node the grafter reads, over all 3,885 structured change nodes:
   **17 nodes over 10 instruments, 193 addresses, 107 landed
   REPLACEs.** The ledger's earlier "20 landed content-destroying
   writes" was the count that reaches a REPLAYED law; 107 is the
   parse-seam universe, and the gap is destruction in laws nothing
   replays.
   **The discriminator is two conjuncts, both DOM evidence, and the
   second one is load-bearing.** (1) A substitution announcement
   governs the node — its own text or its immediately preceding
   sibling STARTS with `I følgende <bestemmelser|paragrafer|…>`,
   quotes a term in guillemets, and carries `endres`/`erstattes`.
   (2) The node declares NO operative payload of its own. Conjunct
   (2) is not decoration: `no/lovtid/2026-06-19-45` puts **four
   genuine `§ X skal lyde: <payload>` change nodes immediately after
   announcements**, so keying on the preceding sibling — which is
   what this item was scoped to do — would have deleted four real
   replacements. The anchor in (1) is load-bearing the same way:
   `no/lovtid/2025-04-25-12` § 3 contains "hjemmel i følgende
   bestemmelser med tilhørende forskrifter:" mid-sentence in ordinary
   payload prose, and an unanchored opener refuses two more genuine
   replacements. Neither conjunct consults address count or a law
   list; the single-address node in the family
   (`no/lovtid/2025-06-20-82`) is caught by the same evidence as the
   82-address one.
   **Measured, base `7a4bd801d` → stopgap.** Ops **27,206 → 27,099**
   on a content-keyed identity diff: **107 lost, 0 gained, 0
   changed**, every one a REPLACE, over 10 instruments and 13 base
   laws. Refusal receipts 0 → 17; `no_parse_cross_base_structured_
   target_skipped` 191 → 105, because the two multi-law nodes are now
   refused before their cross-base skips are counted. Unstructured
   refusals 9,265 and entries 2,563 do not move.
   **Replayed TEXT moves on exactly three laws; 780 of 783 are
   byte-identical.** `no/lov/2015-06-19-70` (35 → 20 ops),
   `no/lov/2008-06-27-71` (168 → 161) and `no/lov/2020-04-17-29`
   (29 → 10). Eleven further laws move only on
   `adjudications_sha`/`receipts_sha` with `statute_sha` untouched:
   80 cross-base-skip receipts leave every law that scans
   `no/lovtid/2026-06-19-48`, and op ids renumber inside instruments
   that now emit fewer ops. No law's text moves outside the three.
   **Karanteneloven's 15 destroyed provisions become 12 stale-word
   rows.** Divergences 17 → 14 (the other two rows are § 8's,
   unrelated). Five `OPS_MISSING` rows CLOSE — the litra under § 13
   first and § 14 second ledd exist again, because their parent is no
   longer overwritten — and two `MISMATCH` rows OPEN on those
   parents, which had been invisible as rows of their own while their
   children carried the damage. **Every one of the 12 remaining rows
   diverges on exactly the superseded word** (`tilsetting…` vs
   `ansettels…`): the row stays open, honestly, and says what is
   actually wrong instead of showing an address list where the law
   should be.
   **Plan- og bygningsloven's 7 destructions are gone, and only a
   direct tree probe can see it.** The law is `blocked_contingent`,
   produces no divergence row, and its § 8-5, §§ 11-12, 11-14, 11-15,
   12-8, 12-10 and 12-12 all carried the amendment's address list at
   base. After the stopgap all seven hold their real text — § 11-15
   second ledd still reads "gjennom elektroniske medier", which is
   the stale word the substitution was going to fix.
   **Hazard census reconciles exactly.** 3,713 → **3,706**
   destructive writes; membership 161 laws, 167 content-removing over
   65 laws, 198 known-incomplete and 265 with destructive writes ALL
   unchanged. One law moves: `no/lov/2008-06-27-71` **[73, 2] →
   [66, 2]** — the seven writes above, and its two content-removing
   writes are a different defect. The other two text-moving laws are
   not known-incomplete, so their 34 removed writes were never in
   this census: the census measures an intersection, and this is a
   reminder of what it does not see.
   **Firings 10 → 10, equal element for element**, so nothing to
   adjudicate under W-54; the sweep baseline is regenerated because
   the grafter is in the replay import closure and the CODE digest
   moves (the corpus digest does not).
   **Scan does not move where it should not.** Candidates 76,
   scoreboard **29/47/0**, ceiling total 1,011 — all unchanged.
   Divergence total 1,504 → **1,501**, entirely karanteneloven's
   −3; unexplained 493 → 490.
   **Bindings 6,489 → 6,484, and this is reported rather than
   buried.** Five `(instrument, base)` bindings disappear because the
   refused ops were the instrument's ONLY ops for that law:
   `2025-06-20-39|1991-07-04-47`, `2025-06-20-40|1989-02-17-2`,
   `2025-06-20-82|1916-07-21-2`, `2026-06-19-45|1984-06-08-59`,
   `2026-06-19-48|1916-06-30-1`. Each was a binding created purely by
   destructive garbage. No law's executable status moves, the status
   map keeps all 241 members, and the replay surface of all five is
   byte-identical — those ops never reached an apply plane.
   **Sizing for the proper op (W-69's half).** Across the 192 refused
   addresses plus the 5 benign stale-word rows, measured against the
   REPAIRED tree: **47 of 197 addresses could be substituted
   deterministically today** (the announced term present exactly
   once). The blockers are what price the follow-up: **103 addresses
   are in a base law with no replayed statute at all**; **30 do not
   resolve in the tree**, and that number is a design constraint
   rather than an accident — they are `setning/N` addresses, and
   sentence children only exist once something has written to the
   ledd, so a substitution op must either address text inside a ledd
   or materialize sentences read-only; 13 resolve but do not contain
   the announced term; 1 has it only under an inflection and 4 only
   as a substring of a longer word. Only **82 of 197 come from an
   announcement naming a single `«X» → «Y»` pair** — 109 are
   `henholdsvis` forms naming several substitutions at once, and 6
   parse to no pair at all. All five benign rows are deterministic.
   **THREE OF THIS SIZING'S CHARACTERIZATIONS DID NOT SURVIVE
   RE-DERIVATION at W-69's design pass** (2026-08-12, HEAD
   `4a68b5a48`; `.tmp/w69/substitution.json`, `s7`/`s8`). The
   POPULATION reproduces exactly — the shipped discriminator
   re-run over all 3,885 structured change nodes returns the same 17
   nodes / 193 addresses / 10 instruments, `own_text` 14 /
   `preceding_sibling` 3 — and so do 104 no-statute, 30 unresolved,
   13 term-absent, 1 inflection-only, 4 substring-only, 109
   `henholdsvis`, 6 no-pair. What moves is what the numbers were
   said to MEAN.
   **(i) The 30 unresolved addresses are not all `setning/N`.** They
   are **21 `sentence` + 5 `subsection` + 3 `section` + 1 `item`**,
   over 6 base acts. The design constraint survives and gets sharper:
   of the 21 sentence addresses, **19 resolve after a read-only
   sentence materialization** and 18 of those carry the term exactly
   once, while only **14** have the term exactly once in the PARENT
   ledd — so materialization beats ledd-text addressing 19 to 14, and
   it fails CLOSED where ledd-text addressing fails OPEN (2 measured
   addresses have the term twice in the ledd, once per sentence). The
   2 sentence addresses materialization does not rescue fail because
   their parent ledd does not resolve either.
   **(ii) The 103/104 base-completeness blockers are not
   commencement work.** **98 of the 104**, over 23 base acts, are
   `no original-act source available for <base> (year YYYY)` — the
   original act is not in the archive at all, an ACQUISITION gap
   outside any lowering item. Largest: `no/lov/1992-07-17-99` (24),
   `no/lov/1984-06-08-59` (15), `no/lov/1984-06-08-58` (9),
   `no/lov/1989-02-17-2` (7), `no/lov/1981-05-22-25` (7). Only **6**
   are `blocked_contingent`, and both of those laws
   (`no/lov/2015-04-10-17`, `no/lov/2005-06-17-62`) are W-72
   blind-spot laws aborting mid-apply. **Zero** are W-73-shaped.
   **(iii) `henholdsvis` pairs FROM-terms with TO-terms, not
   addresses with terms.** "ordene «namsmannen» og «namsmannens»
   endres til henholdsvis «namsfogden» og «namsfogdens»" names a pair
   SET that applies to EVERY listed address, so the follow-up op
   needs no address-positional matching at all — a simplification,
   not a complication. What it DOES need is a refusal this sizing did
   not name: `no/lovtid/2026-06-19-48`'s governing text carries
   **four** announcement openers concatenated into one node with
   **82 addresses over 35 base acts**, and nothing in the flat
   `data-change-part` list says which address belongs to which
   announcement. The hazard is not theoretical: **9 of the 13
   "resolves but term absent" addresses are that node's**, absent
   precisely because they belong to its SECOND announcement
   (`gjeldsforhandlinger` → `rekonstruksjonsforhandling`) while being
   measured against its first. That node must refuse whole.
   Two smaller notes from the same pass: the 6 "no pair" addresses
   (`no/lovtid/2025-06-20-39`) are a PARSER gap, not an unparseable
   construct — the shape is two full pairs written sequentially
   (`«A» endres til «B» og «C» endres til «D»`) — and the term-absent
   set is heterogeneous, including one address
   (`no/lov/2015-06-19-70 § 20 første ledd`) whose archived base
   edition ALREADY reads `ansettelsesmyndigheten`, i.e. W-66's
   finding (v) hazard, where refusing is the correct answer rather
   than a missed opportunity.
   **What is NOT fixed.** The superseded word still stands in every
   one of the 193 provisions. That is coverage loss, it is visible in
   the divergence rows, and it is the trade this item deliberately
   made: 12 honest stale-word rows instead of 15 destroyed
   provisions, and 7 silent destructions removed from a law no scan
   can see.
73. **W-73 (husbankloven base-completeness — the title-cited
   commencement subject):** DONE (`ff202148c`, 2026-08-11;
   artifacts `.tmp/w73/`). The base-completeness gap is repaired
   and measured; **W-67 stays BLOCKED**, and the honest headline of
   this item is WHY.
   **The diagnosis, and it is a commencement-instrument PARSE gap,
   not a binding or lowering one.** `no/forskrift/2012-08-24-826`
   — the kgl.res. that commenced bustøttelova — IS in the corpus,
   parses as a commencement instrument, declares exactly one
   effective date (2013-01-01) and cites exactly one act. Its whole
   operative text is **"Lov om bustøtte skal gjelde frå 1. januar
   2013."**, and that sentence fails every whole-act subject shape
   the module has: `_WHOLE_ACT_RE` wants `(denne) lova trer i
   kraft`; `_WHOLE_ACT_SUBJECT_RE` wants a DEFINITE act-word
   adjacent to the verb and the subject here is the act's TITLE in
   the indefinite; `_CITED_ACT_SUBJECT_RE` wants `om endring`, and
   a NEW act amends nothing in its own title. Scope stayed
   `UNRESOLVED`, the parse blocked, all five routes declined, the
   act stayed `contingent`, and replay skipped it.
   **The instrument genuinely commenced — the branch the brief
   flagged is CLOSED against the corpus, not assumed.**
   Husbankloven's own published consolidation carries, on § 13,
   "Endra ved lover 24 aug 2012 nr. 64 (ikr. 1 jan 2013 iflg. res.
   24 aug 2012 nr. 826, tidlegare § 13, samstundes vart tidlegare
   § 10, § 11 og § 12 oppheva)". The 2012 act's § 9 replacement is
   in the consolidation verbatim. Applying it is sound; no gate was
   bent to reach that conclusion.
   **The repair — a THIRD reader of one existing conjunct, feeding
   one existing route.** `_title_cited_whole_act_subject` proves
   W-53's `WHOLE_ACT_OPERATIVE_TEXT` the one way W-47's two readers
   cannot: the subject is the cited act named by title. It is the
   loosest subject shape in the module, so it carries four
   conjuncts of its own — exactly ONE cited act, exactly ONE `lov
   om` subject in the text, the subject SENTENCE-INITIAL and
   adjacent to the verb, and TITLE AGREEMENT (the subject's title
   phrase must appear in the instrument's own declared title) —
   plus `_SUBDIVISION_SCOPE_RE`, reused verbatim. Every conjunct can
   only REFUSE. Strictly additive: it is OR-ed into
   `widened_whole_act_scope` and NEVER into
   `whole_act_operative_text`, so W-47's multi-part route reads
   exactly what it read before (its reader population is unmoved at
   1,127), and the shipped route cannot move at all because the
   widened route is only reachable by a pair the shipped route
   already refused. Which reader carried a grant is recorded per
   candidate (`title_cited_whole_act_scope`).
   **Measurement.** Corpus-wide, 30 of the 2,365 parsed instruments
   carry the title-cited proof; 8 of those are blocked only on
   scope and gain `widened_whole_act_scope` (1,107 → **1,115**); 5
   of THOSE cite an offered amendment act and become grants. The
   five acts are `2009-01-09-2` (markedsføringsloven),
   `2010-06-04-21` (havenergilova), `2012-08-24-64` (bustøttelova),
   `2017-06-16-67` (statsansatteloven) and `2024-12-13-76`
   (ekomloven), each dated by its own kgl.res., all five `plain`
   rather than staged. The one corpus instrument citing two acts
   (`2009-03-06-266`) is REFUSED rather than guessed at.
   **Blast (782 laws, W-52 discipline).** **772 byte-identical; 10
   move, all 10 inside the 17-law expected-change set, 0 outside —
   no unattributed residue anywhere.** 8 laws' replayed text moves.
   Divergences over the expected-change set **1,687 → 1,680**:
   **7 rows CLOSED, 0 OPENED**, no law worsened. Husbankloven
   **3 → 2** (the closed row is `section:1/subsection:2`, exactly
   the "§ 1 andre ledd skal lyde:" the 2012 act makes);
   `2015-06-19-70` 21 → 17; `2020-05-07-40` 2 → 1;
   `2020-06-19-77` 4 → 3. Three laws move partition
   `blocked_contingent` → `replayed` (`2015-02-13-9`,
   `2015-06-19-70`, `2020-06-19-77`) — the base-completeness repair
   doing exactly what it is for.
   **Scan (the pins DO move, and in the shape the series has moved
   three times before).** Those same three laws become
   `fully_replayable` (73 → **76**) and ENTER the candidate set;
   none leaves. Candidates 73 → **76**, scoreboard 29/44/0 →
   **29/47/0**, totals **1,485 → 1,512**, ceiling **1,011 unmoved
   for the eighth landing running**, unexplained 474 → **501**.
   Total and unexplained move by the SAME +27, so this item explains
   nothing away — it admits 27 previously unreachable rows
   (`2015-06-19-70` 17, `2015-02-13-9` 7, `2020-06-19-77` 3), the
   honest cost of new coverage exactly as at W-39/W-47/W-53. **All
   73 pre-existing candidate rows are byte-identical across the
   change** (`divergence_rows_sha` equal on every one), so no
   existing law's measurement moved. Partition: `replay_defect`
   21 → 23, `untouched_drift` 18 → 19, other buckets unmoved.
   **`(RENUMBER, dest_occupied)` firings: 8 → 8.** The corpus
   count is unmoved by this item, so `wrong == []` holds for the
   reason it held before rather than by luck; the
   `_NO_OCCUPIED_DESTINATION_VERDICTS` pin is untouched.
   **Pins moved:** widened whole-act grants 430 → **435** (all four
   places), `instrument_authorized` 971 → **976** (958 → 963
   non-staged, staged 13 unmoved), `contingent` 539 → **534**,
   widened-scope candidates 1,107 → **1,115**, whole-act REFUSAL
   pairs 882 → **877** (falling by exactly the five grants added —
   the withdraw-on-grant conservation holding), `fully_replayable`
   73 → **76**, and the scan pins above. Entries 2,560, ops 27,018,
   bindings 6,476, instrument coverage 607/33,590/1,758 and the
   shipped route's 541 grants ALL unmoved; so are the part (31),
   multi-part (2) and named-part-list (10) grant SETS, element for
   element, not merely their counts. `test_w53_corpus_the_two_scope_proofs_are_nested_not_overlapping`
   loses its `widened <= reader` containment by design and now pins
   the 8-candidate difference explicitly.
   **(c) THE UNBLOCK VERDICT — NOT MET.** With W-73 + W-67's
   archived product patch applied together (they compose cleanly;
   `git apply --exclude='notes/*'` succeeds), the husbankloven
   firing **does NOT vanish and does NOT re-adjudicate
   `removal_correct`**. W-54's survival test still fails: "Lova
   gjeld frå den tida Kongen fastset" and "Frå same tid vert lov
   1946 nr. 3 … oppheva" are both in the consolidation and survive
   NOWHERE in the replay. Husbankloven divergences 6 → **5** with
   W-73 added (the three `section:13/subsection:1..3` MISMATCH rows
   remain), corpus firings **11, exactly W-67's set — the
   combination introduces no new firing and withdraws none**.
   **Why, and it is a SECOND gap this item found and did not
   fix.** Commencing the act is necessary but NOT sufficient: only
   2 of the 2012 act's 3 change blocks lower. The third,
   `§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 10.`, is
   a two-sentence SECTION-level repeal-then-shift run-on that the
   unstructured grammar refuses outright
   (`no_parse_unstructured_lead_unmatched`). Without it § 13 is
   never vacated, so W-67's textually correct 2017 renumber still
   lands on an occupied § 13. **Opened as W-74 with the sizing
   done** — see below.
   **Rider (d).** Corpus-wide, **163 of 782 base laws take
   destructive writes into a base the system already knows is
   incomplete** (201 laws are known-incomplete, 264 take
   destructive writes, the intersection is 163), totalling **3,737
   destructive writes, of which 159 actually REMOVE content**, spread
   over **64 laws** — the sharpest class, and the one husbankloven is
   in. All 163 are `contingent`, 1 also `unknown_effective`, 0
   `missing_source`. Per-law list at
   `.tmp/w73/blocked_contingent_writes.json`. Research only; the
   diagnosis did NOT point at a guard, because the fix here was to
   complete the base rather than to refuse writes into it. Carried
   to W-72.

68. **W-68 (law-switch failure — correctness-shaped):** from
   W-62. 188 refusals / 115 instruments / 111 stale bases where
   the lead OPENS with a law citation yet is bound to a different
   act — dominated by `I lov <cite> <verb> <address>` (112), the
   verb-before-address order the embedded-multi-act extractor
   does not read; upper bound 335 (147 mid-lead citations are
   addresses, excluded). Only 3 on candidates — priced as
   CORRECTNESS (the switch is sticky), not coverage. Artifacts
   `.tmp/w62/switch_fail.json`.

69. **W-69 (RELOCATE + the proper multi-address substitution op):**
   from W-62; absorbs the other half of the re-scoped W-57 and the
   open half of W-75. **DESIGN PASS DONE 2026-08-12 and SIGNED OFF**
   (read-only, no product change; full document
   `.tmp/w69/design.md`, scripts and artifacts `.tmp/w69/`, all
   sizings re-derived at HEAD `4a68b5a48` rather than copied
   forward). The item is RE-PHASED into W-69a–e below; **W-69a is
   AUTHORIZED and in progress.** No commit hash here on purpose —
   this is a design record, and each phase earns its own when it
   lands.
   **The headline is that the vocabulary question answers itself:
   NEITHER half needs a new canonical op kind, because both are
   already expressible in the shipped vocabulary and both already
   lower somewhere in the corpus today.** (a) The apply plane's
   `RENUMBER`-with-`destination` branch resolves
   `op.destination.parent()` and `insert_sorted`s the SAME `IRNode`
   under a different parent, so it IS a relocation that carries the
   subtree; the structured `data-move-part` lane already mints 14
   genuinely cross-container legs, **including the punktum-between-
   ledd shape this entry previously called the one lead that
   "strictly needs a new op kind"** (`no/lovtid/2026-06-12-24`,
   `§29/ledd/1/setning/4 → §29/ledd/3/setning/3`, on three laws).
   (b) An ADDRESSED `TEXT_PATCH` has a shipped apply branch
   (`legacy_text_action_value(op) == "text_replace"` with a
   non-empty `target.path`) that no producer reaches — only the
   whole-act global text-replace does. `StructuralAction.MOVE`
   exists in the neutral vocabulary and is documented as having no
   runtime dispatch path; NO's structural branch accepts only
   `{REPLACE, REPEAL, INSERT, RENUMBER}`, so minting MOVE would buy
   an adjudication and no semantics. **What both halves are missing
   is PARSE PRODUCTIONS, not vocabulary.**
   **Identity and cross-references, measured rather than assumed as
   the design pass was asked to do.** There are no stable node ids
   in the IR — `IRNode` is `kind/label/text/attrs/children` and
   addressing is positional-by-label throughout — so delete+insert
   breaks no id; what it breaks is content fidelity, since the
   payload is the amendment's restatement. Inbound cross-references
   are plain text that nothing resolves, so no op preserves them and
   none breaks them; the corpus shows the drafter maintaining them
   as SEPARATE amendment sentences (`no/lov/2016-06-17-29` § 2
   bokstav f diverges on exactly `§ 27` vs `§ 25`, and its update is
   its own refused lead). W-69 must therefore not claim
   cross-reference maintenance.
   **Half 1 re-sized (`s2`/`s3`/`s4`/`s10`).** The refused leads were
   re-harvested UNTRUNCATED by wrapping the recorder — 779 of the
   8,583 shipped `source_excerpt` values sit at or over the 240-char
   bound, so a relocation verb past that point is invisible to any
   census read off the adjudication detail. Three arms, union
   **83 refusals / 81 distinct leads / 46 instruments / 41 base acts,
   13 of them in the known-incomplete-base hazard set**; DOM payload
   probe located 81 of 81 and **only 13 of the 81 restate a payload**
   (68 carry existing content). By arm: **A** relocation verb
   (`flyttes`/`flyttast`/`forskyves`) 9 refusals / 8 leads / 7 bases;
   **B** trailing locative (`<qual> § X blir ny § Y i kapittel Z.`,
   which the shipped section-renumber production refuses only because
   it is anchored `\.?$`) 33 / 32 / 15; **C** section-depth set
   relabel (`<qual> §§ A til B blir nye §§ C til D.` — W-57's own
   shape) 41 / 41 / 25.
   **Corrections to this entry's own prior text.** The family is 9
   prose relocation leads and **5 of them restate, not 8** — three
   carry existing content, and they are not the ones this entry
   named: two are HEADING moves with RELATIVE ANCHORS
   (`Overskriften del VII … flyttes til mellom kapittel 20 og
   kapittel 21.`, `Deloverskriften «IV Forskriftsfullmakt» … flyttes
   foran ny § 6-35.`) and the third is the punktum move that already
   lowers structurally. The genuinely unreachable gap is the
   anchor-relative heading destination: placement is
   `insert_sorted(_no_sort_key)` and `_no_sort_key(None)` is
   `(-1,"",0)`, so an unlabelled heading sorts to the FRONT of its
   new parent whatever the amendment said.
   **Arm C's arity, and the shipped expander cannot serve it.**
   `_expand_no_section_range_labels` enumerates only purely numeric
   endpoints. 17 of 41 leads qualify and all 17 are syntactically
   equal-arity — but a label-sequence ORACLE over the replayed
   sibling list disagrees on at least two (`2011-06-24-19` `§§ 23 til
   26` is 4 labels and **7 sections**, the lettered intermediates;
   `2016-09-16-81` `§§ 81 til 83` is 3 and **4**), so endpoint
   arithmetic STRANDS sections. 24 of 41 need the oracle to enumerate
   at all and **21 of the 41 base acts do not replay**, so for half
   the family the oracle has nothing to read. **W-57's own witness is
   genuinely unequal-arity at section depth**: `Nåværende §§ 9-1 til
   9-6 blir ny §§ 3-1 til 3-7` resolves **6** sources against **7**
   destination labels. W-62/W-66's corrected premise ("no
   unequal-arity range anywhere") was measured on the LEDD population
   and holds there; it does not extend to section depth, and arm C
   must refuse unequal arity — which refuses W-57's witness. Three
   further arm-C leads on that instrument resolve 0, 0 and 3 of their
   7/3/7 sources and refuse too.
   **Half 2 re-sized (`s7`/`s8`/`s9`).** W-75's population reproduces
   exactly (17 nodes / 193 addresses / 10 instruments). Deterministic
   **42 exact / 40 whole-word**; **104** no-statute; **30**
   unresolved, and both of those groups are re-characterized in item
   75's entry above (21 sentence + 5 subsection + 3 section + 1 item;
   98 of 104 an ACQUISITION gap, not commencement work). 78
   single-pair / 109 positional / 6 no-pair addresses; leaf kinds
   `subsection` 98, `section` 57, `sentence` 22, `item` 16.
   **THE SCOREBOARD FINDING, which contradicts the standing claim
   that no unexplained row is reachable by an open item** (corrected
   in place at item 62): adjudicated row by row against both texts,
   the substitution arm closes **11 unexplained rows today and 19
   with a read-only sentence materialization** — `no/lov/2015-06-19-70`
   4 + 7 of 12, `no/lov/2020-04-17-29` 7 + 1 of 15. Half 1 by
   contrast touches 41 base acts of which only **2** are scan
   candidates, one of them consistent; its whole exposure is
   `no/lov/2016-06-17-29`'s 21 rows, reachable only by a COMPOSITION
   (chapter repeal + chapter-depth set relabel + arm B) and
   deliberately not bought.
   **DESIGN DECISIONS, ratified 2026-08-12.** (1) No new op kinds;
   `RENUMBER`+`destination` for relocation, addressed `TEXT_PATCH`
   for substitution; `StructuralAction.MOVE` stays dead vocabulary
   and NO's relocation semantics are documented as living on
   RENUMBER. (2) **Whole-word matching** for substitution
   (`(?<!\w)FROM(?!\w)`): measured cost 42 → 40 addresses, of which
   exactly ONE is a live divergence row (karanteneloven `§ 20 fjerde
   ledd`, a genitive `tilsettingsmyndighetens`) — under-application
   is the safe direction and the row stays honestly open. (3)
   **Read-only sentence materialization**, not ledd-text addressing:
   19 of 21 vs 14 of 21, reuses the shipped
   `_materialize_no_sentence_children_with_count` and its shipped
   `no_replay_sentence_children_materialized` receipt, and fails
   closed. The one apply-plane edit is lifting that call above the
   `text_replace` branch, which today sits after it. (4)
   **Multi-announcement nodes refuse whole** (see item 75 (iii)).
   (5) The occurrence rule is a PARSE conjunct — exactly one
   whole-word occurrence or refuse — because `_apply_no_text_replace`
   is a recursive `str.replace` that ignores `TextSelector.occurrence`
   entirely and is not this item's to change; 4 addresses have a term
   more than once and one has both terms, all refusing. (6) The
   known-incomplete-base hazard pin **will move and is to be moved
   consciously**, W-66-style, with the delta attributed address by
   address: `receipt_footprint_mode="observed"` makes every landed
   addressed `TEXT_PATCH` a destructive write, and 17 of the 51
   substitution base acts are in the 161-law hazard set. The two
   payoff laws are NOT in it, so the rows that close are clean. Note
   the non-interaction the other way: the 98 acquisition-gap
   addresses never reach a replay, so they are invisible to that
   census in both directions.
   **APPLY-PLANE DISCIPLINE.** Half 2 needs no new member of
   `_NO_SKIP_ADJUDICATION_KINDS` — its refusals are all parse-plane,
   and an op whose target moves under it already gets the shipped
   `replay_unresolved_target`. Half 1 needs one, for W-66's reason:
   `NO_REPLAY_RELOCATION_OCCUPIED_DESTINATION_REFUSED`, or the apply
   fold's "neither a landed write nor a typed rejection" check trips.
   The destination-free proof is W-66's, not W-74's: W-74's
   self-proving conjunct (the destination must be a label this same
   lead repeals) cannot be reproduced across containers, so the check
   moves to APPLY — per leg, BEFORE the `destination in
   renumber_sources` exemption, refusing with a typed receipt so the
   refusal CASCADES and the relocation drops whole. Stop condition,
   as W-66: firing census **10 → 10 element for element**, verdict
   table gains no row, any `removal_wrong` is a STOP.
   **PHASING (sizes on this session's scale: W-70 small, W-64 medium,
   W-66 large).**
   * **W-69a — addressed substitution at ledd/section/item depth.**
     MEDIUM. **DONE (`17e5dcfb4`, 2026-08-12; artifacts
     `.tmp/w69a/`).** The `TEXT_PATCH` producer plus the full refusal
     envelope shipped as designed, with the two corrections below.
     **11 unexplained rows close, 0 open**, exactly the design's
     projection and on exactly the design's laws. Full narrative at
     item 77.
     **Correction to this phase's own sizing, and it is arithmetic
     the design pass owed itself.** "40 addresses lower" counts the
     `deterministic_whole_word` population WITHOUT subtracting the
     nodes S1/S2 refuse whole — and **17 of those 40 are
     `no/lovtid/2026-06-19-48`'s**, the four-announcement node S1
     exists to refuse. The reachable set is **23 address-lowerings
     over 22 distinct addresses** (one address is named by two
     different announcements of the same instrument), and that is
     what shipped. The row payoff is unaffected: none of the 17 is
     on either payoff law.
     **Correction to "refusals 17 → ~5 typed": it is 17 → 0.** S2
     (address list names exactly one base act) is evaluated before
     S3 (pair grammar parses) as the design's own ordering requires,
     and S3's ONLY corpus node — `no/lovtid/2025-06-20-39` — is also
     the second multi-base node. So S3 keeps the W-75 receipt as a
     live conjunct with an EMPTY population today, and the family's
     17 refusals become 21 sentence-address + 1 multiple-announcement
     + 1 multi-base, all typed.
     Stops: firing census **10 → 10** element for element; hazard
     delta **+1 write, attributed**; **no `removal_wrong`**; the 4
     genuine replacements W-75's conjunct (2) protects still land.
   * **W-69b — read-only sentence materialization on the text-patch
     path.** SMALL. +19 addresses, **+8 rows** → cumulative **19 of
     478**. Stop: the tree SHAPE of every touched ledd changes, so
     the blast measurement is a full-corpus statute diff, not a
     candidate diff, and the materialization receipt count must
     reconcile. **DONE at item 78 (`ccf623ae4`).** Realized: +21
     ops (the parse plane has no statute and cannot pre-refuse the 4
     that fail at apply), 17 landed, **+7 rows, not +8** — one
     karanteneloven ledd holds TWO sentence addresses and the second
     refuses `inflection_only` on a capitalised term, so its row
     correctly stays open. The full-corpus statute diff came in at
     781 of 784 byte-identical, 0 shape-only movers, and the 17
     word-level changes on the 3 movers are exactly the 17 announced
     substitutions.
   * **W-69c — generalize the atomic ordering to
     `(parent_path, label)`.** MEDIUM. No new parse. **Zero
     divergence rows** — the payoff is that `no/lov/2009-06-19-44`
     stops aborting, W-72's blind spot goes **4 laws → 3**, and its
     occupied-destination behaviour becomes observable. Stops: the
     blind-spot list must SHRINK; the newly observable law's firings
     must be adjudicated before anything goes green; all other laws
     byte-identical. **DONE at item 79 (`d5699c464`).** Realized
     with a root-cause CORRECTION: the two legs are not reorderable
     but MUTUALLY UNSATISFIABLE (a Lovdata `data-move-part`
     attribute names the wrong destination section), so the fix is a
     provability REFUSAL over `(parent_path, label)` components, not
     a reordering. Blind spot 4 → 3, firings 10 → 10, 783/784
     byte-identical; the un-aborted law surfaces two pre-existing
     INSERT-occupied replacements the abort was hiding (item 80
     opened to repair the source defect). W-69d's hard prerequisite
     is now satisfied.
   * **W-69d — arms B + C.** LARGE. 74 refusals withdrawn over 38
     base acts / 41 instruments (12 known-incomplete), the
     label-sequence oracle, the apply-plane refusal and the new skip
     kind. **Zero divergence rows on its own.** **W-69c is a HARD
     PREREQUISITE**: widening the parse to mint more cross-container
     RENUMBERs while the existing ones abort a law mid-apply converts
     a refusal into an abort, and an abort discards the law's whole
     receipt plane — strictly worse than the refusal it replaces.
     Expect the `removal_wrong` stop to fire.
   * **W-69e — arm A's heading moves with relative anchors.** Small
     population (3 leads), medium risk, zero rows: the only place a
     new destination shape is arguable, and the only place
     `LegalOperation.anchor` / `move_destination` would earn their
     keep. A heading landing in the wrong position is SILENT, so each
     lead needs a positive pin.
   Recommended order **a → b → c → (decide) d → e**. Open question
   held for a later sign-off: whether to buy `no/lov/2016-06-17-29`'s
   21 rows by opening a composed "restructuring cascade" item with
   W-69d as one of three legs; the design pass recommends not now,
   and the rows stay correctly open in the meantime.
   Superseded by the above, kept for the record: the original entry
   priced this as "production first, op kind only if
   derived-containment risk is judged unacceptable", named ONE lead
   as strictly needing a new op kind, and cited a second
   cross-container witness on candidate `2019-06-14-21`
   (`§ 43 annet ledd blir nytt femte ledd i § 42.`) — that law's 25
   unexplained rows are NOT address-coincident with it, so it carries
   no row after all.

70. **W-70 (malformed `data-move-part` token normalizer +
   tripwire):** DONE (`d7ec7a259`, 2026-08-12; artifacts
   `.tmp/w70/`). From W-62. **The defect turned out to be smaller
   and far more boring than the triage artifact made it look, and
   that is the finding: the whole population is SEPARATOR damage,
   and reading it off the artifact instead of the DOM would have
   inverted every leg.**
   **What the six blocks actually are.** W-62's
   `malformed_analysis.json` lists the tokens in the order
   `_split_move_attr` iterates them, which is REVERSED. Read
   forward off the `article.change` node the parser reads, the
   attribute values are: three with a STRAY SPACE after `;;`
   (`…§8/ledd/2;; …§8/ledd/3` — whitespace is the pair delimiter,
   so one intended pair splits into a token with no destination
   and a token with no separator), one with `::` typed for `;;`,
   one with no separator anywhere, and one with two well-formed
   pairs fused at a missing space. On the reversed reading the
   first three look like `<dest> <source>;;` and a normalizer
   written to that reading would have moved every ledd BACKWARDS.
   The DOM probe is the only reason this item is not a
   destruction.
   **What was built.** `_no_normalize_move_attr` runs ONLY where
   the shipped token grammar already refuses, and every rule is a
   SEPARATOR repair: `separator_spacing` fuses a `;;`-terminated
   token onto the following separator-less one;
   `alternate_separator` retypes a lone `::`. Both are total
   functions on the token list, tried in a fixed order, and the
   rule that fired is reported on the receipt so the ordering is a
   test's fact. The safety property is enforced, not asserted: the
   value's SKELETON — every token concatenated with `;` and `:`
   removed — must be byte-identical before and after, so no rule
   can invent, drop or reorder an address. At most ONE rule
   applies; a rewrite that leaves any token malformed is not
   taken, so a half-repaired attribute lowers nothing (the W-56
   partial-cascade failure mode, refused by construction).
   **The two named cross-base blocks stay refused, and the gate is
   the FIRST thing checked.** Every address in the value must name
   the block's own base act. `2024-06-21-46` names
   `lov/2010-03-26-9` under base `lov/2022-05-12-28` and
   `2026-02-06-2` names `lov/2024-06-21-41` under
   `lov/2022-12-16-91` — the archive mis-filed those endringsdeler
   under the preceding base, so a separator repair on top would
   relabel a law the block does not amend at that address. Both
   keep their receipts, now carrying
   `normalization="declined:cross_base_tokens"`. The fused-pair
   defect deliberately has NO rule: its only corpus instance is
   cross-base, so the rule would be written against evidence that
   could never be allowed to land. `2024-06-21-46` is refused
   twice over — no separator appears in its value at all, so the
   markup does not say which address is the source.
   **The standing tripwire.**
   `test_no_malformed_move_attr_population_is_pinned` re-derives the
   whole census from a live parse of all 3,089 amendment artifacts
   (~13s) and pins it at membership level: which blocks are
   refused with which defect classes and decline reason, and which
   are normalized by which rule with WHICH LEGS. The legs are
   pinned by content because they are RENUMBERs against live law. A
   refresh that adds a seventh block, or changes what an existing
   one lowers, fails with an instruction that names the DOM probe,
   the cross-base rule and the sweep regeneration.
   `test_no_cross_base_malformed_move_attrs_are_never_normalized`
   holds the must-not-recover set on its own so its failure cannot
   read as ordinary drift.
   **No new occupied-destination firing, and no W-66 tag.** The
   recovered legs are ORDINARY structured legs — same mint site,
   same provenance, deliberately NOT
   `NO_LEDD_SET_RELABEL_PROVENANCE_TAG` — because a separator
   repair must not make a leg behave differently from the
   well-formed leg it was meant to be. That was measured rather
   than hoped: the kernel's structural-vacate stage runs REPEALs
   first and then topologically sorts RENUMBERs, and each of the
   four blocks either has its destination repealed by a sibling
   block in the same instrument (`§19-1`, `§3-2`) or shifts upward
   into free space (`§8`, `§4`). **Corpus firing census 10 → 10,
   verdict table unmoved, `removals` unchanged on all 784 laws.**
   **Measurement.** Malformed receipts **14 → 3, exactly −11 and
   nothing else, 0 introduced** — the withdrawal equals the set
   frozen before implementation element for element (`2024-06-25-60`
   2, `2025-02-07-1` 4, `2025-04-10-11` 4, `2025-06-20-74` 1).
   Ops **28,246 → 28,252**, +6 and nothing lost: one leg for
   `§19-1` (5→3), two for karanteneloven `§8` (2→3, 3→4), two for
   `§3-2` (3→2, 4→3), one for `§4` (4→5). Two REPLACEs become
   INSERTs via the shipped
   `_promote_no_replace_with_following_renumber_insert`, which is
   the right reading — "§ 4 fjerde ledd skal lyde:" beside a
   relabel moving that same ledd is new content plus a shift.
   Entries **2,565**, bindings **6,493**, amended-law population
   **784**, unstructured refusals **8,583** — all unmoved. Corpus
   `no_replay_insert_occupied_target_replaced` **138 → 137**.
   **Blast (all 784 base laws, against a pristine checkout of
   `f1b148e6a`).** Four laws move and all four are attributed;
   780 byte-identical. ONE has any op or text movement —
   karanteneloven, below. The other three (`2015-04-10-17`,
   `2020-12-18-146`, `2024-03-08-9`) move by RECEIPT ONLY, zero
   ops and zero text: they are co-amended by `2025-04-10-11`, and
   NO attaches an instrument's parse adjudications to every base
   act that instrument amends. Residue 0.
   **Payoff, and the entrant triage was exactly right this time.**
   `no/lov/2015-06-19-70` § 8: divergences **14 → 12**, both rows
   W-72(c) attributed to this item, 0 opened, the other 12 rows
   byte-identical. The mechanism is worth recording: with the
   attribute refused, only the block's INSERT of a new andre ledd
   lowered, and it landed on the LIVE andre ledd, which the
   insert-occupied recovery then REPLACED — the old andre ledd was
   overwritten and the old tredje ledd never moved, so § 8 read
   three ledd where the consolidation prints four
   (`subsection:3` MISMATCH/`text_drift`, `subsection:4`
   OPS_MISSING/`replay_lowering_gap`). With the legs minted the
   vacate stage runs 3→4 before 2→3 and the insert arrives at an
   empty slot.
   **So this item RESTORES A DESTROYED IN-FORCE PROVISION, which is
   not what a "tripwire" item was priced to do.** The occupant the
   insert-occupied recovery ate is karanteneloven § 8's andre ledd —
   "Lønn eller vederlag for annet arbeid, verv eller oppdrag som
   vedkommende måtte motta eller opptjene i karantenetiden, går til
   fradrag i godtgjørelsen etter første ledd." — standing at
   `§ 8 tredje ledd` in the published consolidation and absent from
   the replayed tree at this base. Replayed § 8 now reads
   1 / new-2 / that ledd at 3 / the old tredje ledd at 4, matching
   the consolidation. It is the W-54/W-67 shape one level over: a
   recovery clearing a slot the amendment intended to VACATE rather
   than to overwrite, invisible precisely because the refused shift
   is what left the slot occupied.
   Candidates **76** and scoreboard **29/47/0** unmoved
   element for element; ceiling **1,011** unmoved; divergence total
   **1,491 → 1,489**, unexplained **480 → 478**.
   **Not taken, deliberately.** The `og skal lyde:` variants
   (`2024-06-25-60` § 19-1, `2025-04-10-11` § 3-2) DO land, but
   only because their payloads are separately addressed by the
   block's own `data-change-part` and their destinations are
   repealed by sibling blocks — the move and the payload never had
   to be inferred from each other. Neither reaches the apply plane
   at 2026-07-10 (`2024-06-25-60` and `2025-06-20-74` are skipped
   contingent for their bases; `1998-07-17-56` has no
   original-act source at all, the F-09 class), so their ops are
   banked against a future commencement rather than measurable
   today. That is stated rather than counted as a win.

71. **W-71 (tighten the operative predicate — receipt hygiene):**
   from W-62. Bare `blir` triggers 278 tail refusals, `endres`
   92, `gjer`/`gjerast` 146 — mostly statutory prose, not
   amendments. Require the verb to govern a structural address.
   Reduces noise receipts; closes NO divergence row. Also carry
   W-62's receipt-honesty note: 267 double-receipted leads
   (production matched, payload failed) overstate the grammar gap
   in the generic refusal receipt.

76. **W-66b (the sibling set relabel at PUNKTUM depth — W-66's
   item (b), now priced):** DONE (`f1673a96c`, 2026-08-14;
   artifacts `.tmp/w66b/`; landing narrative appended after the
   original charter below). OPENED 2026-08-12 by W-69's design
   pass, which found it while censusing something else and is
   recording it as its own item rather than burying it inside a
   relocation item where nobody would look. W-66 left non-`ledd`
   depths refused because "they are a different address arithmetic
   and are not in this population". **They are, however, the
   largest reachable family left in the lowering lane, and it is
   not close.** Measured at HEAD `4a68b5a48` over the UNTRUNCATED
   refused leads (`.tmp/w69/arms.json`, scripts `s2`/`s4`): **144
   refusals / 63 distinct leads / 100 instruments / 69 base acts,
   17 of them in the known-incomplete-base hazard set.** Every one
   is W-66's shipped grammar verbatim except for the depth word —
   `Nåværende annet punktum blir nytt tredje punktum.` (×27 on
   `2001-12-21-117` alone), `Nåværende tredje punktum blir nytt
   fjerde punktum.` (×13), `Nåværende annet og tredje punktum blir
   nye tredje og fjerde punktum.` (×8) — single-sentence,
   currency-qualified, no payload tail. For scale: W-69's three
   relocation arms COMBINED are 83 refusals over 41 base acts, and
   W-69d is priced LARGE to withdraw 74 of them for zero divergence
   rows.
   **What makes it a real item rather than a one-token widening.**
   (a) A punktum address hangs below a ledd that must itself be
   resolved, so W-66's `defaultP` antecedent inheritance has one
   more level to establish and one more way to fail — the receipt
   family needs a ledd-unresolved member alongside
   `no_parse_ledd_set_relabel_address_unresolved`. (b) The
   destination sibling set is SENTENCE children, which exist only
   once something has written to the ledd, so this production
   shares W-69b's read-only materialization dependency and should
   not land before it. (c) `_no_ordered_set_relabel_pairs` and the
   apply-plane refuse-on-occupied tag DO generalize unchanged at
   this depth, because both stay within ONE sibling set — unlike
   W-69's cross-container case, which is why that one needs W-69c
   and this one does not.
   **Row yield is UNMEASURED and must be measured before this is
   sized as coverage.** Exactly one of the 69 base acts is a scan
   candidate (`no/lov/2021-06-18-121`, 2 unexplained rows), which
   on W-62's arithmetic predicts near-zero scoreboard movement —
   but this family was never in W-62's coincidence analysis at the
   depth it actually occurs, and W-69's pass has just shown that
   such generalizations do not survive a re-derivation. First step
   is the address-coincidence join, not a production. Also
   uncounted here: the `bokstav` and `nr.` depths, which the same
   census sees but which W-69's tightened classifier did not
   separate — size them in the same pass.
   **LANDED (`f1673a96c`), sizing pass first as charted, no stop
   condition fired, whole scope, no safe-subset split.**
   **The sizing pass, and two charter corrections.** (i) The
   population re-derived UNTRUNCATED at base `5c0fb190d` is **165
   refusals / 84 leads / 115 instruments / 78 base acts** — up from
   144/63/100/69 on all four axes across the five intervening
   landings; the design's D-arm regex also made the trailing depth
   word optional where the shipped grammar anchors it. (ii)
   **`bokstav`/`nr.` are NOT this grammar one word further down** —
   `ledd`/`punktum` POSTFIX the depth word to a Norwegian ordinal,
   `bokstav`/`nr.` PREFIX it to a letter or arabic numeral; zero of
   the 8,583 refusals match the postfix shape at either depth.
   Sized with a correctly-shaped classifier: **27 refusals / 23
   leads / 17 bases (`bokstav`), 36 / 33 / 19 (`nr.`)** — a real
   family, a different sentence grammar over a different label
   vocabulary, a different item (not opened at this landing). The
   address-coincidence join reproduced the design's finding exactly:
   ONE candidate base (`no/lov/2021-06-18-121`), 1 of its 2 rows
   address-coincident, projected yield ≤ 1; **realized 0**, and the
   zero is structural — see below.
   **What was built.** `_no_punktum_set_relabel_pairs`, W-66's
   anchored sentence with `punktum` for `ledd`, tried strictly
   BEHIND the shipped ledd grammar (disjoint by tail anchor, pinned
   as a test's fact); the optional source-side `<ordinal> ledd`
   phrase split off in code so the ledd ordinal reads through the
   ONE shipped ordinal vocabulary. **The destination side reduces
   to ordinals ALONE** — a destination that respells a ledd cannot
   parse, so the cross-container relocation shape (W-69's
   territory) is impossible by construction rather than by a
   deletable check; 5 leads pay for it, including harmless same-ledd
   restatements (the grammar does not get to decide which
   restatements are harmless). `_no_antecedent_ledd_label` reads
   the LEDD from the SAME `defaultP` antecedent node as the section
   — two levels from one node is what makes the pair coherent —
   with one conjunct W-66 needs not have: the antecedent must
   itself be punktum-depth (an antecedent naming a whole ledd
   establishes a PAYLOAD, and inheriting from it would renumber
   sentences of a provision just written; zero measured elements,
   carried on W-66's cycle-guard reasoning). Ordering:
   `_no_ordered_set_relabel_pairs` reused unchanged (charter (c)
   confirmed). Receipts: new parse-plane
   `no_parse_punktum_set_relabel_ledd_unresolved` (charter (a));
   the section half REUSES `no_parse_ledd_set_relabel_address_unresolved`
   — same reader failing the same way; the shipped constant name is
   now historical, noted rather than renamed. **Apply plane: zero
   edits** — the ops carry W-66's own
   `NO_LEDD_SET_RELABEL_PROVENANCE_TAG` (the refuse-on-occupied
   branch is depth-agnostic; a sibling tag would have needed a
   duplicated branch on a load-bearing safety seam and made punktum
   firings invisible to W-72's sweep — the wrong polarity;
   ratified). The new kind, being parse-plane, is cataloged but
   correctly NOT in `_NO_SKIP_ADJUDICATION_KINDS`.
   **Frozen before implementing, matched after, element for
   element** (`.tmp/w66b/expected_withdrawal_set.json`, simulated
   against antecedents captured from the walk itself): **165/165 —
   112 lowered (59 leads, 161 legs), 27 new-kind refusals (all
   `antecedent_names_no_ledd`), 10 reused-kind refusals, 16
   grammar-declined; 0 strays either direction.** Unstructured
   refusals **8,583 → 8,434 (−149)**; ops **28,384 → 28,545
   (+161)**, exactly the frozen leg count, independently derived
   from the index side.
   **Charter (b) confirmed on the real path**: a punktum RENUMBER's
   `setning/N` target materializes via W-69b's
   `_materialize_sentence_parent_for` on the structural arm before
   resolution; corpus receipts 822 → 824 (+2 — idempotent where
   earlier ops already split the ledd). Finding pinned: **on a
   refused op the materialization rolls back with it**, so no
   statute keeps a shape no landed op produced. W-69c's guard:
   0 → 0, no punktum group unprovable.
   **Blast**: 785 laws (the population GROWS — `no/lov/2004-12-10-77`
   enters on its first lowered ops, both `replay_unresolved_target`,
   no write), 14 movers ALL inside the derived expected set, 771
   byte-identical. The 56 expected non-movers each attributed: **49
   have no original-act source** (the family concentrates on
   pre-2001 acts — the structural reason the row yield is zero), 3
   typed-refusal-only, 4 lowered-but-scanned-not-applied
   (contingent commencement, pre-existing). Index: three
   instruments gain their FIRST entry (2,565 → 2,568); bindings
   6,496 → 6,502 with W-34/W-35 conservation exact (+6 = −6
   unbound pairs).
   **Firings 10 → 10 element for element, content-keyed; zero new
   firings; the `removal_wrong` stop the charter budgeted for never
   engaged.** The one new apply-plane refusal (set-relabel refusals
   31 → 32, 12th law) is the item's most instructive artifact,
   DOM-adjudicated: `no/lovtid/2022-06-10-38` on
   `no/lov/2021-06-18-121` § 20 første ledd commands "annet punktum
   oppheves." then "Nåværende tredje punktum blir annet punktum."
   The relabel now lowers; **the punktum-depth REPEAL does not (no
   production reads one)**, so slot 2 is live and W-66's guard
   refuses — had the θ cell fired it would have deleted the
   sentence, W-54's `removal_wrong` shape one depth down,
   prevented. This flips the candidate's scan bucket
   `untouched_drift` → `replay_defect` (the W-23 predicate in the
   refusing direction; scoreboard unmoved) and names the unlock:
   **item 81**.
   **Scan discipline: every number unmoved** — 76 candidates,
   29/47/0, total 1,471, ceiling 1,011, unexplained 460, 0 rows
   opened, 0 closed. Hazard re-pinned consciously: 3,827 → **3,828**,
   one law (`no/lov/2008-05-15-35` [262,8] → [263,8]; +3 landed
   punktum RENUMBERs − 2 REPLACEs as the shipped promotion helper
   wakes at this depth: `replace_promoted_to_insert` 113 → 122,
   `insert_occupied_target_replaced` 137 → 133); membership,
   content-removing (168/65), incomplete (199) unmoved. Sweep
   baseline keys all adjudicated (code digests — grafter alone —
   the hazard row, `base_laws` 784 → 785 with the entrant, and
   `no/lov/2005-06-17-62` gaining 2 ops behind its PRE-EXISTING
   abort, identical error string).

77. **W-69a (the addressed word substitution, lowered for real):**
   DONE (`17e5dcfb4`, 2026-08-12; artifacts `.tmp/w69a/`). From
   W-69's design pass; replaces W-75's stopgap refusal for every
   node whose announcement and address list the envelope can prove.
   **The construct the corpus writes as "announcement plus address
   list" now lowers to one addressed `TEXT_PATCH` per (listed
   address × announced pair), and 11 unexplained divergence rows
   close — the first time this programme has closed a scoreboard row
   by ADDING a production rather than by refusing one.**
   **What was built.** Parse plane, inside the structured
   document-change walk where W-75's blanket refusal stood: S1 the
   governing text carries exactly ONE announcement opener, S2 the
   address list names exactly the enclosing block's base act, S3 the
   `(FROM, TO)` pair grammar parses, S4 W-75's two shipped
   conjuncts unchanged, plus a per-address gate that refuses a
   `setning/N` leaf as W-69b's and an unlowerable address token as
   its own kind. Surviving addresses mint
   `TEXT_PATCH`/`TextPatchSpec(REPLACE, TextSelector(match_text=FROM),
   replacement=TO)` on the shipped apply branch that had no producer.
   Apply plane: S6 (exactly one of the announcement's FROM terms
   present) and S7 (that term present exactly once, as a whole word,
   and exactly once as a raw substring) with a typed refusal and a
   new `_NO_SKIP_ADJUDICATION_KINDS` member.
   **THE DESIGN IS WRONG ABOUT WHERE HALF 2'S REFUSALS LIVE, and
   this is the item's headline.** §4.1 states that half 2 "needs
   nothing" in the conserved partition because "its refusals are all
   parse-plane (S1–S7): no op is minted". S5–S7 cannot run at parse:
   they need the addressed node's TEXT, and the parse plane has no
   statute — replay CONSUMES parse output, so asking for one is
   circular. The design's own §3.2 header says as much ("the first
   four are cheap string tests on the announcement; the rest need
   the tree"); §4.1's conclusion simply does not survive its own
   premise. Taken in the refusing direction: S6/S7 are an apply-plane
   conjunct emitting
   `no_replay_substitution_term_not_uniquely_present`, registered in
   the skip set so a refused op is a typed REJECTION and not an op
   that landed nothing. Letting it fall through to the θ
   content-identical `replay_noop` cell would have conserved the
   partition and thrown the REASON away — and two of the six reasons
   (`substring_only`, `multiple`) are not no-ops at all: the shipped
   `_apply_no_text_replace` is an unguarded recursive `str.replace`
   honouring neither occurrence nor word boundary, so it would have
   written, wrongly.
   **S5's `no_statute` arm degrades, and it is stated rather than
   quietly dropped.** The design has S5 refuse the 104 addresses
   whose base act has no replayed statute "loudly, with the receipt
   naming the base act so an acquisition sweep can harvest the list".
   No parse-plane receipt can know that either. Those ops are now
   MINTED and simply never applied, which is the corpus-wide norm —
   440 of 784 base laws error before any op. The list stays
   harvestable, better than before: join the ops carrying
   `no_addressed_substitution` against
   `amended_executable_law_status_map()`, which cannot go stale the
   way a frozen receipt can. **Net honesty change: 104 addresses that
   carried a blocking refusal now carry a banked op instead.** That
   is the same treatment every other unreplayable base's ops get, and
   it is the price of lowering the construct at all.
   **Two sizing corrections, both arithmetic the design owed itself
   (detail at item 69's W-69a bullet).** "40 addresses lower" did not
   subtract the 17 that belong to the four-announcement node S1
   refuses whole: the reachable set is **23 lowerings over 22
   addresses**. "Refusals 17 → ~5" is **17 → 0**, because S2 runs
   before S3 and S3's only corpus node is also the second multi-base
   node — the W-75 receipt survives as a live conjunct with an empty
   population.
   **Frozen before implementing, matched after, element for
   element** (`.tmp/w69a/freeze.json`, `f1_freeze.py`). Parse census
   `no_parse_substitution_announcement_not_lowered` **17 → 0**;
   `no_parse_substitution_sentence_address_out_of_scope` **21**,
   `no_parse_substitution_multiple_announcements` **1**,
   `no_parse_substitution_multi_base_address_list` **1**,
   `no_parse_substitution_address_not_lowerable` **0** — the frozen
   set exactly, **0 introduced**. Adjudications 10,885 → 10,891.
   Ops **28,252 → 28,363**: on a content-keyed identity diff (source,
   base, action, target, destination, payload shape,
   match/replacement — never `op_id`) **111 gained, 0 lost, 0
   changed**, every one a `text_patch`. 84 surviving addresses, of
   which 27 sit under two-pair `henholdsvis` announcements, so 57×1 +
   27×2. The family minted NOTHING at base, so this widening is
   purely additive. Unstructured refusals **8,583**, entries
   **2,565**, amended-law population **784**, candidates **76**,
   malformed-attr receipts **3** — all unmoved.
   **Bindings 6,493 → 6,496, reported rather than buried.** Three
   `(instrument, base)` pairs appear because the substitution was the
   instrument's ONLY content for that law:
   `2025-06-20-40|1989-02-17-2`, `2025-06-20-82|1916-07-21-2`,
   `2026-06-19-45|1984-06-08-59`. These are exactly three of the five
   bindings W-75's refusal REMOVED, returning now that the ops are
   real rather than destructive garbage; the other two are its
   multi-base nodes, which S1/S2 refuse whole. The declared-target
   receipt census falls in step — **949 → 947 receipts, 2,507 → 2,504
   pairs** — with the W-34/W-35 conservation exact at 3 = 3, nothing
   rebound and nothing newly unbound. All three bases have no
   original-act source, so no replay reaches them; 0 bindings
   removed, and no base act gains its first op.
   **Blast (all 784 base laws, against a pristine checkout of
   `1ffd5c5a7`; content-keyed on statute digest, per-kind
   adjudication census and receipts keyed on action + bound/landed
   path + footprint, never on `op_id`).** **15 laws move, 769
   byte-identical, residue 0.** Only THREE have any text movement —
   `no/lov/2015-06-19-70`, `no/lov/2020-04-17-29`,
   `no/lov/2008-06-27-71`. The other 12 move by RECEIPT ONLY, zero
   ops and zero text, and NO attaches an instrument's parse
   adjudications to every base act it amends: **11** are co-amended
   by `no/lovtid/2026-06-19-48` and see its one refusal change kind
   from `…announcement_not_lowered` to `…multiple_announcements`;
   **1** (`no/lov/2018-06-15-40`) is co-amended by
   `no/lovtid/2024-06-21-52` and picks up its six sentence-address
   refusals. Corpus receipts 6,032 → 6,047 (+15 landed
   `text_replace`), destructive 4,552 → 4,567, **content-removing
   207 → 207**.
   **The 15 landed writes, by law.** karanteneloven 6 (§ 13 first,
   § 14 second, § 14 fourth ×2 — two different announcements of the
   same instrument name that ledd — § 15 first, § 20 first);
   `no/lov/2020-04-17-29` 8 (§ 13 first ×2, § 14 first, § 14 third,
   § 15 first, § 15 second, § 17 first, § 21 second); plan- og
   bygningsloven 1 (§ 12-12 fifth, `gjennom elektroniske medier` →
   `på internett`). The gap between 23 parse-eligible and 15 landed
   is COMMENCEMENT, not the envelope: `no/lovtid/2026-06-19-45` is
   skipped contingent for `no/lov/2008-05-15-35` and
   `no/lovtid/2025-06-20-93` for plan- og bygningsloven, so their 9
   ops are banked against a future commencement rather than
   measurable today.
   **Payoff: unexplained 478 → 467, ceiling 1,011 UNMOVED, 0 rows
   opened, and only the two design-named laws move.**
   `no/lov/2015-06-19-70` 12 → 8 (§ 13 first, § 14 second, § 14
   fourth, § 15 first); `no/lov/2020-04-17-29` 15 → 8 (§ 13 first,
   § 14 first, § 14 third, § 15 first, § 15 second, § 17 first, § 21
   second). Total 1,489 → **1,478**. Scoreboard **29/47/0** and
   candidates **76** unmoved; no consistent → inconsistent flip.
   **What stays open on those two laws, honestly.** Karanteneloven
   `§ 20 fjerde ledd` reads the genitive `tilsettingsmyndighetens`,
   which whole-word matching declines — the design priced this at
   exactly one row and it cost exactly one row. Its `§ 20 første
   ledd` write DOES land (the ledd is later replaced wholesale by
   another amendment, so the row was never this item's), and the
   design's "term absent, the archived edition already carries the
   amendment" reading was measured against the FINAL tree rather
   than mid-timeline. `no/lov/2020-04-17-29`'s five remaining
   addresses are `§ 11` and `§ 18` ledd that do not exist in the
   replayed tree at all — that law's own `§ 11 fjerde ledd oppheves`
   + relabel sequence, a different defect, correctly out of scope.
   **Hazard census re-pinned CONSCIOUSLY, W-66 style. 3,809 →
   3,810 destructive writes; membership 161 laws, 168
   content-removing over 65, 199 incomplete and 265 with destructive
   writes ALL unchanged.** ONE law moves:
   `no/lov/2008-06-27-71` **[79, 2] → [80, 2]**, the § 12-12 write
   above, and that law is `blocked_contingent` — exactly the posture
   this census exists to watch. The other 14 landed writes are on
   laws that are not known-incomplete, so the census cannot see them;
   the census measures an intersection. Content-removing does not
   move because a text substitution REPLACES and never removes,
   which is the whole reason this widening is cheaper than W-66's.
   **Firings 10 → 10, element for element; verdict table gains no
   row; no `removal_wrong`.** The sweep baseline is regenerated
   because the grafter is in the replay import closure and the CODE
   digest moves; the corpus digest does not, and beyond the code
   digest the ONLY movement is the one hazard count and its
   `laws_digest`. W-72's blind spot is unchanged at 4 laws.
   **Two deviations from `design.md`, both recorded at the code.**
   (a) The op shape's `occurrence_mode="First"`: `TextSelector`'s
   annotation is `Literal["Auto", "Last"]` (its `__post_init__`
   accepts `"First"`, so core's type and runtime contract already
   disagree), NO's apply reads NEITHER occurrence field, and the
   exactly-one guarantee is carried by the apply conjunct — so the
   field would be decoration, and widening a core `Literal` for
   decoration reaches three `us_federal` branches testing
   `occurrence_mode != "Auto"`. Not set. (b) The detail vocabulary's
   `inflection_only` is kept as the design's word, but it measures a
   CASE-insensitive-only match; the genuine Norwegian inflection is a
   substring match and lands in `substring_only`. Named at the emit
   site rather than renamed, so the receipt stays auditable against
   the design.
   **Report-only findings.** (i) The whole-word matcher is a
   `str.find` scan, not a regex: a per-term `re.compile` of an
   f-string is the frozen-residue shape the FW-07/FW-08 ratchets keep
   out of a parser module, and a test proves the scanner equals
   `(?<!\w)TERM(?!\w)` on 4,000 randomized inputs including the
   non-overlapping advance. (ii) Occurrence counting is per node's
   OWN text and summed, matching `_apply_no_text_replace`'s recursion
   exactly; counting over a flattened join could match a multi-word
   term across a node boundary `str.replace` can never see. The two
   agree on all 27 resolvable corpus addresses, so this is a
   soundness guard rather than a behaviour change. (iii) S6's corpus
   population is EMPTY under this envelope — the one address carrying
   two announced terms belongs to the four-announcement node S1
   refuses — but the two-pair announcements that DO survive have
   prefix-nested FROM terms (`namsmannen`/`namsmannens`), so the
   conjunct is a live guard on 27 addresses whose bases are currently
   unacquirable. (iv) One design-pass number does not survive
   re-derivation, and it is the one that JUSTIFIES S1: item 75 (iii)
   and the design's §2.2 say **9** of the 13 term-absent addresses
   belong to `no/lovtid/2026-06-19-48`. Re-derived at this base it is
   **8** (the other five are `2025-06-20-39` 2,
   `2026-06-19-45` 2, `2025-02-07-1` 1). The argument is unchanged —
   a clear majority of the term-absent population is one node's
   announcement crosstalk — and the corrected figure is what the code
   and the catalog say.

78. **W-69b (read-only sentence materialization on the text-patch
   path):** DONE (`ccf623ae4`, 2026-08-13; artifacts `.tmp/w69b/`).
   The second W-69 phase, exactly as re-phased at item 69: two edits,
   both small, **7 more unexplained rows close** and the sentence
   half of the substitution family is fully served or typed.
   **What was built.** Apply plane: the materialization-before-resolve
   block (shipped at W-54's seam, previously reachable only on the
   structural arm AFTER the text-patch arm had returned) is lifted
   verbatim into a closure `_materialize_sentence_parent_for(op)`
   called from BOTH arms of the dispatch, before `_resolve_no_path`.
   Same shipped `_materialize_no_sentence_children_with_count`, same
   shipped `no_replay_sentence_children_materialized` receipt, same
   `rule_id` — the mechanism is unchanged, only its reachability.
   READ-ONLY means read-only on CONTENT: the parent ledd goes from
   text-carrying to children-carrying, but space-joining the children
   reproduces the former ledd text byte-for-byte, and a tripwire test
   holds that conservation with a paired `!=` assertion so a no-op
   cannot satisfy it. Parse plane: W-69a's per-address `setning/N`
   refusal is deleted; sentence addresses fall through to the same op
   minting as ledd/section/item.
   **`no_parse_substitution_sentence_address_out_of_scope` is
   RETIRED — deleted, not zeroed.** It named a phase boundary (the
   materializer's reachability), not a property of the construct, and
   the boundary no longer exists. Constant, emit site, catalog entry
   and test import all removed; the family's surviving conjuncts are
   unchanged (`multiple_announcements` 1, `multi_base_address_list`
   1, `announcement_not_lowered` 0, `address_not_lowerable` 0).
   **The lift is UNCONDITIONAL, licensed by measurement**: at the
   base pin ZERO `text_replace` ops corpus-wide targeted a sentence
   leaf (`.tmp/w69b/sentence_textreplace_census.json`) — W-69a
   refused every one — so the only ops the new reachability serves
   are the 21 this item mints, and the call is a no-op for every
   other target shape.
   **Frozen before implementing, matched after, element for element**
   (`.tmp/w69b/expected_withdrawal_set.json`): 21 receipts, 4
   instruments, 4 base acts → **21 ops minted, 0 strays, 0 survivors
   of the retired kind**. Accounting: **17 `lowered_and_landed`**, 1
   `lowered_no_statute` (`no/lov/1998-07-17-56` § 7-6 — no
   original-act source; the design counted this one as "resolving",
   but the base act has no replayed statute at all), 1
   `lowered_apply_term_refused` (karanteneloven `§ 17 første ledd
   første punktum`, `inflection_only`: the text reads capitalised
   `Tilsettingsmyndigheten`), 2 `lowered_apply_unresolved`
   (`no/lov/2020-04-17-29` `§ 11/1/1` and `§ 18/2/2`, whose parent
   ledd are missing from the replayed tree — the same defect as that
   law's five unresolvable LEDD-addressed ops, so they take the same
   generic `replay_unresolved_target`, interleaved with them in one
   pinned list, rather than a new typed kind that would claim a
   difference which isn't there).
   **Design numbers corrected, all in the refusing direction.**
   "+~19 ops" is **+21** (parse cannot pre-refuse the 4 apply
   failures); "19 resolve" is **17 land**; "**+8 rows**" is **+7**
   (`§ 17 første ledd` holds TWO sentence addresses; `tredje punktum`
   lands, `første punktum` refuses, the row stays open); "13
   materialization receipts on karanteneloven at design time" was
   mis-scoped — the corpus total at base is 807 and karanteneloven's
   is 0.
   **Measured.** Ops **28,363 → 28,384** (+21, content-keyed, 0
   lost, 0 changed, every one a `text_patch`); parse adjudications
   10,891 → 10,870 (−21). Replay:
   `no_replay_sentence_children_materialized` **807 → 822**, the +15
   reconciled op-by-op (`2008-06-27-71` +6 in 6 distinct ledd;
   karanteneloven +8 — 7 ledd plus `§ 17/1` materializing TWICE,
   because the refused `setning/1` op's state was rolled back whole
   and `setning/3` re-materialized; `2020-04-17-29` +1, one receipt
   for `§ 12/1` shared by all four landings there);
   `no_replay_substitution_term_not_uniquely_present` 1 → 2;
   `replay_unresolved_target` 697 → 699. A refused sentence op still
   EMITS a materialization receipt even though the seam rolls its
   state back entirely — pre-existing seam behaviour, pinned by test
   rather than suppressed. Bindings 6,496, entries 2,565, population
   784, candidates 76, unstructured refusals 8,583 all unmoved.
   **Full-corpus statute diff (the item's headline blast cost,
   priced by the design and paid): 781 of 784 byte-identical, 0
   shape-only movers, 3 content movers** — and the word-level diff
   of those three is **17 changes, every one an announced (FROM→TO)
   pair on a lowered sentence address, 0 unadjudicated**. The
   co-amendment leak is stated: the retired receipt's replay-plane
   count was 26, not 21, because parse receipts attach to every base
   act the instrument touches — 6 leaked onto `no/lov/2018-06-15-40`,
   whose statute is byte-identical and which is the corpus's only
   adjudication-only mover.
   **Payoff: unexplained 467 → 460, ceiling 1,011 UNMOVED, 0 rows
   opened, only the two design-named laws move.** Karanteneloven
   8 → 2 (six of its remaining eight rows were sentence-addressed);
   `no/lov/2020-04-17-29` 8 → 7. Total 1,478 → 1,471. Scoreboard
   **29/47/0**, candidates 76, no flips.
   **Hazard census re-pinned CONSCIOUSLY, third time in the W-69
   family and same shape: 3,810 → 3,816 destructive writes, ONE law**
   — `no/lov/2008-06-27-71` [80, 2] → [86, 2], plan- og
   bygningsloven's six remaining `gjennom elektroniske medier` → `på
   internett` addresses at sentence depth, the siblings of the
   § 12-12 write W-69a landed on the same `blocked_contingent` law.
   The design said the payoff laws sit outside the hazard set and did
   not anticipate this third law moving; adjudicated safe at the
   landing: each write proved its term uniquely present as a whole
   word in the ADDRESSED punktum, and a substitution replaces without
   removing — content-removing is unchanged at 168 over the same 65
   laws (corpus-wide 207), membership 161, incomplete 199 all
   unchanged. **No `removal_wrong` anywhere. Firings 10 → 10,
   `firings` and `firing_laws` blocks byte-identical; verdict table
   gains no row.** Sweep baseline regenerated (grafter in the
   closure); beyond the code digest the only movement is the one
   hazard count and its `laws_digest`. W-72's blind spot unchanged
   at 4 laws.
   **Judgement calls ratified at sign-off:** the receipt retirement;
   the generic `replay_unresolved_target` for the 2 unresolvable
   sentence addresses; the unconditional lift; the hazard-set
   landings on `2008-06-27-71`; the materialization receipt surviving
   rollback as pinned seam behaviour.

79. **W-69c (the atomic relocation ordering, generalized to
   `(parent_path, label)` — as a provability refusal):** DONE
   (`d5699c464`, 2026-08-13; artifacts `.tmp/w69c/`). The third
   W-69 phase. **Zero divergence rows, by design; the payoff is
   W-72's blind spot going 4 laws → 3** and the cross-container
   apply plane becoming trustworthy, which unblocks W-69d.
   **THE DESIGN'S FRAMING DID NOT SURVIVE THE DATA, and the
   correction is the item's headline.** §4.2 read the
   `no/lov/2009-06-19-44` abort as an ordering bug: the
   in-migration runs first, the vacate shift lands on it, reorder
   and it is fixed. The two legs are in fact MUTUALLY
   UNSATISFIABLE: `no/lovtid/2025-06-20-42`'s §3 `data-move-part`
   attribute sends `§3/ledd/3 → §2/ledd/4` while its own annotated
   prose says an intra-§3 shift ("Noverande § 3 andre og tredje
   ledd blir tredje og nytt fjerde ledd") — **the Lovdata attribute
   names the wrong destination section**, our lowering is faithful
   to it, and so that leg and the §2 block's own `§2/ledd/3 →
   §2/ledd/4` both claim one slot. No permutation satisfies both
   (DOM evidence `.tmp/w69c/instr_2025-06-20-42.xml`). The design's
   first-hour question is answered the same way: the kernel's
   `renumber_vacate=True` stage is ALREADY full-path-keyed and on
   this law produced exactly the order it promises — but a
   topological sort can only answer with a permutation, has no
   `by_destination` map, and is structurally incapable of reporting
   "no order exists". W-66's `_no_ordered_set_relabel_pairs` has
   the identical hole, unreachable there only because one lead's
   grammar cannot spell a destination twice.
   **What was built: a provability TEST at the apply seam, not a
   reordering** — which is what makes it W-70-safe (no landed op's
   semantics change; proof below). `_no_unprovable_relocation_targets`
   (grafter.py): union-find over `(parent_path, label)` nodes —
   which is exactly `LegalAddress.path` — across one affecting-act
   group's DISTINCT RENUMBER legs; a connected component is
   unprovable on a CONTESTED DESTINATION (this law's shape), a
   CONTESTED SOURCE, or a CYCLE (W-66's guard at the new keying),
   and every leg of an unprovable component refuses
   `no_replay_relocation_order_unprovable_refused` — FIRST in the
   RENUMBER branch, ahead of target resolution, so the verdict is a
   fact about addresses independent of the tree and of emitted
   order, and "the component drops whole" is proven rather than
   observed. Registered in `_NO_SKIP_ADJUDICATION_KINDS`,
   cataloged. The COMPONENT is the refusal unit: refusing one leg
   out of a shift chain is W-56's half-application; refusing the
   whole group would take down disjoint shifts with no argument;
   and there is no principled discriminator between two internally
   consistent but contradictory attributes, so picking a winner
   would be a semantics change on landed ops. It lives at the APPLY
   plane because the two colliding legs come from two different
   `data-move-part` attributes on two different `article.change`
   elements — no parse-plane production ever sees both.
   **A latent wrong answer caught mid-item, in the refusing
   direction's favour**: the first cut counted a REPEATED leg
   (identical source and destination announced twice) as a contest.
   Two corpus groups do this (`no/lov/1999-03-26-14` and
   `no/lov/2017-06-16-53`), neither reaches the apply seam today —
   a wrong answer with zero corpus blast to reveal it. Legs are
   deduplicated before the analysis; pinned by
   `test_no_w69c_a_leg_announced_twice_is_one_instruction_not_a_contest`.
   **The judgement call ratified at sign-off — the un-aborted law
   loses two provisions to a recovery this item did not touch.**
   With the six relocation legs refusing, the instrument's "skal
   lyde" INSERTs land on slots the refused shift never vacated, and
   the SHIPPED `(INSERT, occupied)` θ cell recovers by replacing
   the occupant: base `§ 2 tredje ledd` and `§ 3 andre ledd` are
   overwritten, each carrying a typed blocking
   `no_replay_insert_occupied_target_replaced` receipt (137 → 139;
   the law's third is pre-existing, from `no/lovtid/2021-06-11-78`,
   and ran at the base pin too). The abort was HIDING these two
   firings — this is the blind-spot narrative's prediction
   honoured, not a new defect. Trade taken: a fully receipted
   statute honestly missing two provisions beats no statute and no
   receipts at all; the loss is named in
   `test_no_w69c_witness_2009_06_19_44_replays_to_completion` and
   the repair is item 80.
   **Measured.** Scan totals UNCHANGED and measured, not assumed:
   candidates 76, scoreboard 29/47/0, total 1,471, ceiling 1,011,
   unexplained 460 (the law is not a candidate). Full-corpus
   statute diff: **783 of 784 byte-identical; exactly one law moves,
   and it moves from no-statute to statute** (+8,293 chars).
   Receipts 6,064 → 6,074 (+10, all its), adjudications +6 (the six
   refusals), destructive writes 4,584 → 4,591 (+7, all its),
   content-removing **207 → 207**, `no_replay_apply_raise` 4 → 3,
   bindings and ops flat. **Firings 10 → 10 element for element,
   verdict table gains no row, no `removal_wrong`.** Unprovable
   census: 1 group at apply (the target law, 6/6 legs); 1 more
   corpus-wide at parse (`no/lov/1981-05-22-25` ←
   `no/lovtid/2012-01-20-6`, §186 told to become both `ledd/6` and
   `ledd/4` — genuinely contradictory, F-09 sparse so it never
   reaches apply; W-69d will meet it). Cross-container legs
   re-derived at this base: **7 over 6 base acts / 4 instruments**
   (the design's 14 measured pre-W-70; the separator repair changed
   the population).
   **Sweep baseline: 9 keys moved, each adjudicated** — the code
   digests (grafter only, 1 of 79 modules), the aborting-law rows
   4 → 3 (the payoff), and the law's own hazard membership
   (`bases_with_destructive_writes` 265 → 266, `hazard_bases` 161 →
   162, `hazard_destructive_writes` 3,816 → 3,823, its row
   `[7, 0]` — zero content-removing — and `laws_digest`). Firings,
   corpus digest, content-removing (168/65), incomplete bases (199)
   all unmoved.

80. **W-70b (Lovdata destination-section repair on `data-move-part`,
   behind a population tripwire):** DONE (`a915f7d69`, 2026-08-14;
   artifacts `.tmp/w70b/`). Opened at the W-69c sign-off; landed one
   session later at exactly the size it was priced at. As opened:
   `no/lovtid/2025-06-20-42`'s §3 attribute writes
   `§3/ledd/2;;§2/ledd/3 §3/ledd/3;;§2/ledd/4` where its own
   annotated prose commands an intra-§3 shift — the attribute
   contradicts the prose it annotates, and the prose is the
   authority. **The two provisions item 79's θ cell replaced are
   RECOVERED and in force** — base `§ 2 tredje ledd`
   ("Enkeltpersonar kan vende seg direkte til
   krisesentertilbodet…") now `§ 2 fjerde ledd`, base `§ 3 andre
   ledd` ("Kommunen skal sørgje for å ta vare på barn…") now `§ 3
   tredje ledd` — and the whole six-leg component applies:
   `no_replay_relocation_order_unprovable_refused` **6 → 0** at
   apply (the parse-plane group on `no/lov/1981-05-22-25` remains,
   F-09-blocked; W-69d will meet it),
   `no_replay_insert_occupied_target_replaced` **139 → 137** (the
   law's `section:4` one is from `no/lovtid/2021-06-11-78`,
   unrelated, deliberately left standing).
   **The population, censused BEFORE building and pinned by
   content** (`.tmp/w70b/expected_population.json`): of the
   corpus's 286 `data-move-part` attributes / 504 legs, **35
   attributes carry a leg whose resolved destination section
   differs from its own source section** (54 legs). By leg shape:
   51 legs / 33 attrs `section → section` (ordinary section
   renumbering — the differing section IS the instruction;
   untouched), 1 leg `sentence → section` (a genuine promotion,
   `no/lovtid/2024-04-12-14`; untouched), 2 legs / 1 attr
   `subsection → subsection` — the defect, and the production's
   entire reach. Post: **35/35 accounted, 1 repaired, 34 declined
   typed, 0 strays; 285/286 attributes byte-identical through the
   seam.** A cross-base boundary case outside the resolved
   population (`no/lovtid/2025-06-20-70`, destination does not
   lower) is pinned in the untouched set via a deliberately dumber
   string-level census on the test side — a strict superset that
   cannot go blind on an unresolvable leg.
   **The prose-proof rule is a SEVEN-LIMB conjunction, each limb
   with its own typed decline reason**: every leg
   `<prefix>/ledd/<n>` on both sides (suffix test, not regex, so a
   deeper address cannot enter); one shared source and one shared
   destination prefix, differing; both resolving to sections of
   the block's own base act (cross-base declines first, W-70's
   precedent); the block's own announcement parsing via the SHIPPED
   relabel grammars (W-56 first, W-66's widened sibling after — no
   new sentence grammar minted) and spelling a section; that
   section being the SOURCE; the prose shift map equalling the
   markup's ledd map pair for pair (the prose may correct the
   section and nothing else); and no other section named anywhere
   in the announcement. The rewrite is structurally confined: each
   destination is rebuilt as
   `<source prefix>/ledd/<declared destination ordinal>`, so the
   production cannot move a leg to a ledd the markup did not
   declare. Receipt
   `no_parse_structured_move_attr_destination_section_normalized`
   (non-blocking, APPLY disposition), cataloged; the production
   runs LAST of the three move-attr lanes so the shipped path sees
   base bytes. **Limbs 4–7 have no corpus witness** (all 34
   decliners fall at limb 1) and are held by a seven-case synthetic
   decline suite — kept rather than trimmed, because the limbs
   exist for the member that arrives with a future corpus refresh,
   and the tripwire routes it to a human first. Ratified at
   sign-off.
   **Adjudicated ledd-by-ledd against the instrument's four change
   blocks** (`.tmp/w70b/adjudication_2009-06-19-44.txt`): § 2 goes
   6 → 7 ledd and § 3 goes 3 → 4, both "Noverande …" announcements
   satisfied element for element; every other section
   byte-identical; `statute_len` +302 = exactly the two recovered
   provisions.
   **Measured.** Exactly ONE law of 784 moves. Ops 7,340 flat at
   replay (a destination rewritten, not an op minted; the index
   op-count pin 28,384 unchanged); receipts 6,074 → 6,080 (+6
   landed RENUMBER writes); adjudications 37,255 → 37,248 (−6
   refusals − 2 replacements + 1 receipt); destructive writes
   4,591 → 4,595 (law row `[7,0] → [11,0]`: +6 RENUMBERs, −2
   INSERT recoveries; 7+6−2=11); **content-removing 207 → 207** —
   the disappearing replacements were destructive-but-not-removing
   (`replaced_paths`, never `removed_paths`), so nothing moves.
   **Firings 10 → 10 element for element; no new firing, no
   `removal_wrong`.** Scan totals measured unmoved: 76 candidates,
   29/47/0, total 1,471, ceiling 1,011, unexplained 460, all 76
   candidate rows byte-identical. Sweep baseline: 5 keys moved,
   each adjudicated (the code digests — grafter alone of 79
   modules — `hazard_destructive_writes` 3,823 → 3,827, the law's
   row, its `laws_digest`); firings, corpus digest,
   content-removing (168/65), membership (162/266/199) all
   unmoved.
   **W-69c pins moved consciously**: the corpus witness
   `test_no_w69c_witness_2009_06_19_44_replays_to_completion`
   rewritten from pinning the LOSS to pinning the RECOVERY — 0
   refusals, both provisions asserted BY TEXT (not just label), §2
   labels 1..7, §3 labels 1..4, `insert_occupied ==
   ["section:4"]`, docstring carrying all three states (pre-W-69c
   abort → W-69c typed refusal → W-70b repair); the hazard
   count/digest pins; the blind-spot comment (which claimed "every
   relocation leg refuses", now false — the occupied-destination
   answer stays zero for a DIFFERENT reason: proven-safe ordering,
   not "nothing ran"). Population tripwire
   `test_no_move_attr_destination_section_population_is_pinned`
   (3,089 artifacts, both halves by content) plus
   `test_no_genuine_cross_section_moves_are_never_normalized`, the
   must-not-repair set split out so its failure cannot read as
   drift.

81. **W-66c (the punktum-depth REPEAL production):** DONE
   (`b7a2d76e9`, 2026-08-14; artifacts `.tmp/w66c/`; landing
   narrative appended after the charter below). Opened at the
   W-66b sign-off as the named unlock for that item's machinery. The witness is exact and
   DOM-adjudicated (`.tmp/w66b/`): `no/lovtid/2022-06-10-38`
   commands "§ 20 første ledd annet punktum oppheves." then
   "Nåværende tredje punktum blir annet punktum." on
   `no/lov/2021-06-18-121`. W-66b lowers the relabel; **no
   production reads a punktum-depth REPEAL**, so slot 2 stays
   occupied by live text and the relabel leg refuses under W-66's
   occupied-destination guard — the refusal is correct (the θ cell
   would have deleted an in-force sentence, W-54's `removal_wrong`
   shape one depth down) and it is exactly the relationship W-66
   had with the chapter-repeal gap: the relabel item makes the gap
   VISIBLE AND SAFE; the repeal item closes it. Payoff when built:
   the repeal vacates the slot, the relabel lands, and the one
   address-coincident unexplained row on `no/lov/2021-06-18-121`
   (§ 20/ledd/1) becomes closable — the punktum lane's first
   scoreboard row. Scope sketch: the `<address> punktum oppheves`
   sentence family at ledd context (census before building, W-70's
   discipline; the same DOM-local antecedent inheritance W-66b
   ships; materialization already reachable via W-69b; the vacated
   slot then satisfies W-66's guard with no apply-plane edit).
   Sizing: the family's oppheves leads were not separately counted
   at W-66b — census first. Small-to-medium. Standing caution from
   W-66b's coverage finding: 42 of the 59 punktum-written bases
   have no replayable original-act source, so size yield against
   source availability FIRST.
   **LANDED (`b7a2d76e9`), census first as charted, no stop
   condition fired, whole scope.** The charter's "small" was off by
   an order: the census found **293 refusals / 235 leads / 135
   instruments / 136 base acts** of the strict `oppheves` shape
   (the witness was one lead of 235), plus 202 refusals declined by
   the shipped-shape grammar (run-ons 63, nynorsk verb 41, `siste
   punktum` 33, cross-act inverted 18, sub-containers 9, other 38)
   and a wide-verb arm priced at +24 for a future widening. The
   source-availability join re-derived: only 46 of the 136 written
   bases replay at all; the coincidence join projected ≤ 5 rows on
   5 addresses; **realized 4 rows moved on candidates, 3 genuine
   closes, zero realized-but-unprojected**.
   **What was built.** `_no_punktum_repeal_targets` — W-66b's
   address arithmetic with the shipped ledd-depth repeal lane's own
   verb anchor: `oppheves` ALONE (24 nynorsk refusals priced and
   kept), the sentence must END at the verb (every run-on
   declines: lowering only the destroying half of a run-on would
   mis-number the statute), `siste punktum` declines even though
   `sentence/last` resolves (a repeal that destroys by counting is
   the one shape this item must not take on trust), and a ledd is
   REQUIRED (43 typed refusals rather than a shallow-host guess
   about which sentence dies). Plural and range ordinals read
   through the one shipped vocabulary. Op: the SHIPPED
   `StructuralAction.REPEAL` at a sentence leaf — no new op kind,
   no provenance tag (a repeal has no destination for the guard to
   key on; mirrors the shipped repeal lane), zero apply-plane
   edits. Call site LAST in the unstructured walk, which is the
   additivity proof. **The ordering that makes the repeal-relabel
   pair work is the kernel's structural-vacate stage** (every
   REPEAL in a group runs before every RENUMBER; one instrument at
   one moment is always one group) — pinned by a test that hands
   the ops in the wrong order deliberately.
   **The destroys-text discipline, first use at scale.** The
   census froze the withdrawal set (293) AND the destroyed-sentence
   set (33 destructions over 29 bases, each with the sentence's own
   text) before any production code; both matched element for
   element after (0 unfrozen destructions, 0 lost; one apparent
   stray on the first pass was the freeze script's own
   label-normalization bug — fixed by importing the shipped
   normalizer, re-derived clean). **All 33 adjudicated individually
   against their instrument's DOM: every one commanded by a lead
   spelling its own section and ledd — not a single destruction
   rests on an inherited address.** Op fate over all 279 minted
   legs: 182 on error-before-reach bases, 35 never reach apply, 6
   refuse typed, 33 destroy.
   **Measured.** Unstructured refusals **8,434 → 8,141 (−293)**;
   ledd-unresolved receipt 27 → 70, address kind 50 → 52 (both
   REUSED with a `production` detail key — naming debt noted at the
   code); ops **28,545 → 28,824 (+279)**, the frozen leg count
   exactly; set-relabel refusals **32 → 31** (W-66b's witness leg
   converts to a landing); materialization 824 → 854; bindings
   6,502 → 6,543 (+41, including 8 UNDECLARED bindings on
   `no/lovtid/2009-06-19-74` whose `changesToDocuments` never named
   them); three more base laws enter the sweep (785 → 788, two with
   no source). **Firings 10 → 10, baseline blocks byte-identical,
   no `removal_wrong`.** Statute diff: 38 movers, 0 outside the
   expected set, 747 byte-identical; the two destruction bases with
   no visible text move are later-amendment overwrites, adjudicated
   (`2008-05-15-35` § 76, `2008-06-27-71` § 12-14 — the destruction
   is real at its moment and invisible at the PIT).
   **The two firsts, ratified at sign-off.** (i) **The candidate
   set SHRINKS 76 → 75** (scoreboard 29/47/0 → 29/46/0): the
   production gives `no/lovtid/2013-01-11-3` its first lowered ops
   and the contingent binding that was always in the source
   downgrades `no/lov/2011-06-24-39` (−5 rows) and
   `no/lov/2010-06-04-21` (−1) to `blocked_contingent`, while
   `no/lov/2009-05-15-28` enters (+2) — W-73's mechanism running
   backwards, accepted as the honest label rather than worked
   around. (ii) **The content-removing column moves for the first
   time in the series**: corpus 207 → 240 (+33 = the destructions,
   exactly), hazard 168 → 198 over 65 → 77 laws, 30 of 33 landing
   in known-incomplete bases — which is precisely why the
   destruction set is pinned BY CONTENT (tripwire 2), with the
   pinned population derived from the minted-leg tripwire so a base
   that starts destroying when its source arrives is caught, not
   missed. Totals: **total 1,464 / ceiling 1,011 UNMOVED /
   unexplained 453**; the witness § 20 første ledd row closes, the
   law returns to `untouched_drift`, and W-66b's loop is closed
   end to end with the final ledd pinned by text.

82. **W-76 (the sibling-set relabel at ITEM depth — `bokstav`/`nr.`,
   the PREFIX grammar):** DONE (`82a0c2adc`, 2026-08-16; artifacts
   `.tmp/w76/`). Opened on the user's direct go-ahead from W-66b's
   sizing finding rather than a written charter: `bokstav`/`nr.`
   are NOT the postfix set-relabel grammar one word further down —
   they PREFIX the depth word to a letter or an arabic numeral
   ("bokstav c", "nr. 2") — so the family is a different sentence
   grammar over a different label vocabulary and got its own item.
   **Landed whole scope, no stop condition fired, and — a first —
   the census re-derived at this item's own base pin came back
   IDENTICAL to the sizing pass two landings earlier** (bokstav 27
   refusals / 23 leads / 27 instruments / 17 bases; nr. 36 / 33 /
   28 / 19; union 63 / 56 / 54 / 32): the population did not
   drift, measured, not assumed.
   **What was built.** `_no_item_set_relabel_pairs` — the shared
   qualified-section head (extracted as
   `_NO_SET_RELABEL_QUALIFIED_SECTION_HEAD` on the rule of three,
   all three relabel patterns pinned byte-identical) followed by
   the PREFIX shape per depth; labels are explicit-expansion only
   (a `til` range is enumerated, never counted on trust; letters
   restricted to `a`–`z`, `æ`/`ø`/`å` decline on unproven
   ordering; newness admitted once, ahead of the destination's
   depth word, never inside a list). The address is W-66b's
   arithmetic with the discipline one notch tighter: the corpus
   probe over every replaying censused base finds **1,529 `item`
   nodes, every one below a `subsection`** (1,477 directly, 52
   item-under-item, zero off a section), so the LEDD is REQUIRED —
   the resolver's first-match DFS makes a shallow `(section, item)`
   address a silent guess — and it is ALWAYS inherited, through
   `_no_antecedent_ledd_label` parameterized (`depth_name`/
   `depth_markers`, shipped call sites byte-identical) rather than
   forked; a lead that spells its own ledd DECLINES (26 refusals,
   the sized next widening). New parse-plane kind
   `no_parse_item_set_relabel_ledd_unresolved` (22, every one
   `antecedent_names_no_ledd`) — a kind of its own, unlike W-66c's
   reuse, because the reader's depth conjunct is retargeted, so it
   is not the same reader failing the same way; the section half
   reuses W-66's address kind (52 → 65). Ordering, provenance tag,
   and the occupied-destination guard reused with **zero
   apply-plane edits**; block LAST in the walk as the additivity
   proof.
   **Measured.** Frozen withdrawal set 63/63 element-for-element
   (28 lowered minting 67 legs over 17 bases / 22 + 13 typed, 0
   strays, 0 lost). Unstructured refusals **8,141 → 8,078 (−63)**;
   ops **28,824 → 28,891 (+67, the frozen leg count exactly)**.
   Projected row yield ZERO (none of the 17 written bases is a
   scan candidate; only 8 of 67 legs are picked up by any replay)
   — **realized zero; the verify-partition report is
   byte-identical**, candidates 75, totals 1,464 = 1,011 + 453.
   **Firings 10 → 10 byte-identical, no `removal_wrong`,
   content-removing census unchanged (240/198/77) — no op destroys
   text.** Statute text moves on 3 laws, each DOM-adjudicated;
   5 REPLACE → INSERT promotions are the shipped promoter waking
   up where a relabel vacates the slot its co-located payload
   would have overwritten — exactly right. One instrument
   (`no/lovtid/2011-12-09-55`) gains its first index entry;
   bindings 6,543 → 6,546; apply-plane relabel refusals 31 → 33.
   Sweep baseline: `code` plus a fully-adjudicated destructive-
   count bump (3,875 → 3,880 over three laws, membership and
   content-removing column byte-identical).
   **The hole this production makes visible** (ratified at
   sign-off): the relabel is half of a two-part instruction, and
   where the companion payload lead spells `ny` the shipped
   item-target reader's `ledd bokstav` adjacency breaks and
   nothing is minted — so on `no/lov/2005-06-17-90` § 6-2 the
   relabel vacates bokstav c and nothing refills it (a gap
   faithful to a half-applied instrument; the payload refusal
   predates this item), and on straffeloven `no/lov/2005-05-20-28`
   § 37 a j→k relabel swaps WHICH payload leg fails with no net
   text loss (node count identical). **Item 83 (W-77) opened** for
   the payload production that closes both. The two new
   apply-plane refusals (`no/lov/2002-06-21-45` bokstav b,
   `no/lov/2007-06-29-75` nr. 6) are CORRECT — relabel legs whose
   antecedent announces an item-depth REPEAL with no production,
   the exact W-66b→W-66c relationship one family out; that repeal
   is sized (166 refusals / 160 leads / 113 instruments / 77
   bases) but not opened, as is the ledd-spelling arm (26 / 24 /
   14).

83. **W-77 (the item-depth PAYLOAD production — `§ X <ledd> ny
   bokstav|nr Y skal lyde:`):** DONE (`9c81b2c90`, 2026-08-16;
   artifacts `.tmp/w77/`; landing narrative appended after the
   charter below). Named at W-76's landing as
   the highest-value follow-up: **146 refusals / 146 leads / 113
   instruments / 64 base acts** at base `2e667312f`. The shipped
   item-target reader requires `ledd bokstav` adjacency and the
   `ny` marker breaks it, so today the payload half of a
   relabel+payload pair is never minted: W-76's relabel then
   vacates a label nothing refills. Payoff when built: the INSERT
   lands in the vacated slot (the shipped
   `_promote_no_replace_with_following_renumber_insert` already
   proves the pair semantics on the no-`ny` variant, 5 corpus ops,
   all correct) and the visible gaps on `no/lov/2005-06-17-90`
   § 6-2 and straffeloven `no/lov/2005-05-20-28` § 37 close.
   Scope sketch: teach the item-target reader the `ny` marker (or
   a sibling production minting INSERT directly), census first
   with the frozen expected withdrawal set, source-availability
   join before yield claims (W-66b's standing caution), and the
   occupied-destination guard must see every INSERT — a payload
   INSERT into an occupied slot is exactly what the guard exists
   to refuse. Content-ADDING at scale, so the statute-diff
   discipline (movers all expected, byte-identical count) is the
   load-bearing check. Medium.
   **LANDED (`9c81b2c90`), census first as charted, whole family,
   no stop condition fired — and the census DOUBLED the charter:
   225 refusals / 225 leads / 165 instruments / 96 base acts** (the
   charter's 146 was the spelled-ledd cut of the same family; 148
   of the 225 spell their ledd, 217 their section; 125 bokstav /
   100 nr.; 16 multi-label). The whole family shipped — the
   widening is the same grammar with W-76's antecedent inheritance,
   not new machinery — ratified at sign-off.
   **What was built.** `_no_item_insert_payload_target` — a sibling
   production, NOT a widening of the shipped item-target reader
   (that reader is a pure `lead → specs` function shared by four
   call sites, DOM-blind, so it can inherit nothing) — anchored
   END TO END on the announcing node's OWN text
   (`_node_text_without_structural_children`): 178 of 225 carry
   the payload as a `<ul>` INSIDE the announcing node, so the
   walk's `lead` is announcement+payload concatenated and an
   unbounded-tail grammar could not tell a payload from a run-on
   (the 10 run-on refusals are exactly what that would have
   swallowed) — the W-75 discipline stated positively. Payload
   extent PROVED on `_extract_items` (top-level items; the
   flattened candidate map cannot tell nesting from mis-sizing —
   measured, 3 correct ops' difference): list labels must equal
   announced labels one-for-one in order, all-or-nothing;
   multi-label announcements handled provably (13 lowerings won);
   text carriers admitted only single-label/single-node
   `article.legalP` (`numberedLegalP` declines — its leading
   numerator is a second address claim; 1 refusal, sized).
   Address is W-76's arithmetic (ledd REQUIRED on the 1,529-node
   probe; inheritance kept though nearly inert — it supplies 1
   ledd and 1 section). Three new parse kinds
   (`no_parse_item_insert_payload_{address_unresolved(7),
   ledd_unresolved(73), extent_unprovable(1)}`), one new
   apply-plane refusal in the skip set:
   `no_replay_item_insert_payload_occupied_target_refused`, gated
   on new tag `no_item_insert_payload` BEFORE the shipped θ
   `(INSERT, target_occupied)` recovery — an announcement saying
   NY that finds the label standing means the vacate did not
   happen, so the occupant's in-force text must not be replaced;
   **fires zero times corpus-wide**, carried on the cycle-guard
   rule; the shipped θ census is untouched (133 → 133 over 55
   laws, element-for-element). The relabel+payload pair composes
   in the kernel's structural-vacate stage (REPEAL → RENUMBER →
   everything else within `(effective, enacted, source_id)`),
   pinned by test.
   **Measured.** Both frozen sets matched exactly: withdrawal
   225/225, added-content 160/160 (0 strays, 0 lost). Refusals
   **8,078 → 7,853 (−225)**; ops **28,891 → 29,051 (+160
   INSERTs)**. Statute text: 15 laws move, **22 nodes added, 0
   destroyed, 0 changed in place**, every addition individually
   DOM-adjudicated (16 verbatim W-77 payloads, 5 later-amendment
   REPLACEs landing in now-existing slots, 1 renumber carry).
   Content-removing **240/198/77 unchanged**; firings 10 → 10;
   hazard destructive 3,880 → 3,885 (five downstream REPLACEs now
   resolving, attributed, membership unchanged). Index 2,572 →
   2,578; grants 541 → 542. **Scoreboard: unexplained 453 → 452**
   — the projected row on `2004-03-26-17` closes (law →
   `consistent`), `2012-01-27-9` 5 → 4, and ONE row opens,
   adjudicated deliberate: klimaloven `2017-06-16-60` § 7/2/e
   CONSOLIDATED_MISSING (see the W-77 scan note) — the instrument
   commands it, the consolidation never carried it, the law moves
   `consistent → replay_defect`. Candidates 75, scoreboard
   29/46/0, ceiling 1,011 untouched, totals 1,463.
   **Gap cases from the charter.** (a) `2005-06-17-90` § 6-2:
   CLOSED — første ledd now `a–f`, byte-identical to Lovdata's
   consolidation, bokstav c verbatim from `no/lovtid/2007-01-26-3`,
   W-76's relabel vacating first in the kernel's ordering. (b)
   straffeloven `2005-05-20-28` § 37: **honestly a DIFFERENT
   family, not closed** — its payload half is a two-label REPLACE
   the shipped multi-item reader already lowers; what is missing
   is W-76's spelled-ledd relabel limb plus a `(REPLACE,
   target_absent)` decision at item depth (recorded as sized
   follow-up, not opened).
   **The collateral finding (item 84, W-78, opened).** W-77 makes
   a PRE-EXISTING mis-lowering reachable at one address:
   `no/lovtid/2026-06-12-31` carries a W-69a-style substitution
   announcement whose ADDRESS LIST is mis-read as a `skal lyde`
   payload target, minting REPLACE ops whose payload is the
   announcement sentence itself. **116 such defective REPLACE ops
   exist at base over 2 instruments (`2026-06-19-45`: 87,
   `2026-06-12-31`: 29); 27 already LAND at base over 2
   non-candidate laws** (28 post — W-77's marginal +1 overwrites
   text W-77 itself created, not in-force law; ratified at
   sign-off as JC-8: a correct op is not withheld to keep a latent
   bug latent). Sized-not-opened follow-ups: mixed
   existing+new label lists (55, a widening of the shipped
   multi-item reader), the spelled-ledd relabel limb (26, the
   straffeloven § 37 prerequisite), `numberedLegalP` carriers (5),
   nested item addresses (20, against 52 attested nodes).

84. **W-78 (the substitution-announcement address list mis-lowered
   as a payload target):** DONE (`efc32b19e`, 2026-08-17;
   artifacts `.tmp/w78/`; landing narrative appended after the
   charter below). The highest-value finding W-77
   surfaced, and a CORRECTNESS defect, not coverage: a W-69a-style
   substitution announcement ("Følgende steder endres ordene «X»
   til «Y»: …") has its trailing ADDRESS LIST mis-read by an
   existing production as a `skal lyde` payload, minting REPLACE
   ops that would write the announcement sentence itself into the
   statute at the listed addresses. Sized at W-77's landing: **116
   defective REPLACE ops over 2 instruments (`no/lovtid/
   2026-06-19-45`: 87, `no/lovtid/2026-06-12-31`: 29); 27 land at
   base over 2 laws** (28 after W-77 — the marginal one at
   `no/lov/2008-05-15-35` § 17/1/n replaces W-77's own created
   text). Neither law is a scan candidate and no base-present text
   is destroyed, which is why this sat invisible. Scope sketch:
   find the mis-firing production (the payload-target reader that
   accepts an announcement-with-address-list node), census the
   defective-op population frozen by content, fix the
   discriminator per the W-75 rule (the node must declare its own
   operative payload — an address list is not one), and show the
   116 ops withdraw element-for-element with the 27-28 landed
   writes reverting to refusals or correct substitution ops.
   Blast discipline in full; the two instruments are 2026 laws so
   commencement handling needs care. Small-to-medium, high value:
   every op this closes is a wrong-text write waiting for its
   target to exist.
   **LANDED (`efc32b19e`), no stop condition fired, frozen set
   matched 116/116 — and the root cause is NOT what the charter
   guessed.** No payload reader mis-fired: the W-69a
   substitution-announcement recognizer DECLINED the new dialect
   because `_NO_SUBSTITUTION_ANNOUNCEMENT_OPENER_RE` enumerated
   the noun after `følgende` (`bestemmelser|paragraf|…`) and
   `steder` was not in the list — control then fell through to
   the ordinary structured `document-change` lane, which
   faithfully read the node's `data-change-part` (naming every
   listed address) as 116 REPLACE targets and the node's own text
   as their payload. The family half-works by design: both
   instruments carry `I følgende bestemmelser …` nodes that lower
   correctly beside the broken ones, which is why this sat
   invisible.
   **Two charter numbers corrected by re-derivation.** (i) The
   landed wrong writes are **23 on ONE law** (`2008-05-15-35`);
   the other instrument's 87 ops target tvangsfullbyrdelsesloven
   `no/lov/1992-06-26-86`, which has NO original-act source and
   never replays. (ii) The charter's "no base-present text is
   destroyed" was **FALSE**: 15 distinct wrong-text nodes stood
   in the replayed statute at base, and **11 had destroyed
   substantive in-force text** — 13 child nodes (2 punktum of
   § 93/3, 4 bokstav of § 100/1, 7 bokstav of § 100/2) plus the
   ledd texts of §§ 100/5–7 and 100 a/1–5.
   **The fix** (three edits, all in the announcement grammar,
   each measured corpus-wide first): the opener generalizes to
   `^(?:i\s+følgende|følgende)\b` — the noun is decoration, and
   enumerating it WAS the defect; the weight moves to the rule
   that replaces the list's accidental protection:
   `_no_text_announces_word_substitution` now requires the quoted
   FROM term and the substitution verb both in the HEAD before
   the first colon (the span the pair-extractor already reads),
   making the colon a LIST introducer — the instruction must be
   complete without the list, the W-75 principle stated
   positively; the S1 scan counter generalizes in lockstep.
   Measured over all 2,704 `data-change-part` nodes: governing
   17 → 24, the 7 additions exactly the defect nodes; the 5
   near-miss nodes that carry term+verb but declare their own
   payload stay declined on the untouched operative-payload veto.
   **Fate of all 116**: every one re-routes to the SHIPPED
   addressed-substitution production — +290 correct TEXT_PATCH
   ops (**29,051 → 29,225**), none refuses at parse, unmatched
   refusals **7,853 unchanged**. On `2008-05-15-35`: 8 land as
   correct substitutions (each verified verbatim against a
   base→clean→post pivot; sentence-initial `Ansiktsfoto` refuses
   typed rather than case-folding on a guess — the safety
   asymmetry visible), 19 refuse `term_not_uniquely_present`
   (2 → 21), 6 unresolved targets. The 1992 law's 257 correct
   ops sit INERT until its source is acquired — the moment it is,
   the largest announcement (86 addresses × 3 pairs) lands as
   law instead of as 87 wrong-text writes.
   **The reversion, adjudicated three-way**: all 15 wrong texts
   vanish, the 13 destroyed children return verbatim, node count
   1,083 → 1,096 on the moved law; § 17/1/n returns to W-77's
   created bokstav n. **Blast**: ONE law's normalized surface
   moves, 0 outside the expected set; scoreboard 29/46/0,
   candidates 75 (identical), totals 1,463 / **ceiling 1,011
   unmoved** / unexplained 452 — neither affected law is a
   candidate, as charted. Firings **10 → 10** and θ census
   **133 → 133**, both element-for-element. Content-removing
   **240/198/77 unchanged** (the withdrawn receipts all carried
   `removed: []`). Hazard destructive writes **3,885 → 3,870
   (−15)** — **the hazard census's first recorded shrinkage**,
   fully attributed to the withdrawn wrong writes. Sweep
   baseline: `code` + the adjudicated hazard row. Commencement
   untouched (grants 542, contingent/future skips identical).
   **Item 85 (W-79) opened** for the general closure: the
   structured payload lane's missing own-text invariant. Sized
   but not opened: the `1992-06-26-86` source acquisition
   (fold into the source-availability pricing census) and the
   case-variant substitution terms (a content-policy decision,
   several of the 19 typed refusals).

85. **W-79 (the structured payload lane's missing own-text
   invariant):** DONE (`1f0ca83df`, 2026-08-17; artifacts
   `.tmp/w79/`; landing narrative appended after the charter
   below). The general closure of W-78's wrong-text
   class, named by its landing: the structured `document-change`
   lane reads a node's `data-change-part` as REPLACE targets and
   the node's OWN TEXT as their payload without requiring the
   node to DECLARE an operative payload (`skal lyde`, `oppheves`,
   `skal ha følgende ordlyd`, a payload structure of its own).
   W-78 closed one dialect of this (24 nodes); **267
   `data-change-part` nodes over 337 declared addresses remain
   with no operative payload marker** and could have their own
   text written into law by the same fall-through. Scope sketch:
   shape-by-shape census of the 267 (frozen by content) BEFORE
   any rule — a blanket refusal would withdraw real amendments,
   so each shape needs adjudication: which are genuine payload
   carriers in an unrecognized dialect (lower or refuse typed),
   which are announcements/notes that must never be payloads
   (refuse via the invariant), which are already handled upstream.
   Then the invariant itself: a structured payload node must
   declare its own payload, with the W-78 discriminator
   (term+verb-in-head, operative veto) as the model. The
   endpoint is that the wrong-text class W-78 fixed becomes
   IMPOSSIBLE by construction rather than closed dialect by
   dialect. Medium-to-large; correctness, not coverage.
   **LANDED (`1f0ca83df`), no stop condition fired — and the
   charter's denominator was reframed by the census** (ratified):
   the defect lives in `_fallback_payload`, the ONE payload
   source in the structured lane that reads the amendment's own
   prose, and the charter's 267 marker-filtered nodes excluded
   the `oppheves`-marked dialects that are equally defective. The
   census therefore covered the WHOLE own-text-fallback
   population: 556 calls, 217 payloads over 134 nodes. Shape
   census (all adjudicated): 68 ops DECLARE their payload and
   keep lowering (61 byte-identical, 7 with the lead prefix now
   removed — the old narrow `^§ N skal lyde:` strip generalized
   in the same change, each of the 7 adjudicated); 149 declare
   none and refuse — 37 relabel announcements, 37 repeal/
   punctuation announcements (incl. `2025-06-20-88`'s 29-address
   heading-punctuation instruction, the W-78 construct in a
   dialect with no quoted term), 8 in-place substitutions, 1 move
   announcement, and 66 ops over 43 nodes whose GENUINE payload
   sits outside `_TEXT_BLOCK_CLASSES` (43 wrote their lead into
   law, 23 wrote an EMPTY node over their target). **Measured:
   not one of the 149 carried statute content; not one of the 68
   carries an instruction — the separation is the node's own
   claim, not a shape allowlist.**
   **The invariant**: `_no_structured_declared_own_payload` — a
   payload-introducing operative phrase (`skal … lyde/lyda/
   lyder/ordlyd`) must stand in the HEAD before the first colon
   and content must follow it; the payload IS the tail. Refusal
   per `(action, target)` with new parse-plane blocking kind
   `no_parse_structured_payload_not_declared` (cataloged;
   correctly outside the apply-plane skip set). The
   renumber-replacement site needs no second kind (already
   refuses typed on a None payload). Structured-candidate
   payloads (196 nodes / 255 ops) never consult the fallback —
   untouched by construction.
   **Measured.** Ops **29,225 → 29,076 (−149, the frozen set
   exactly; 7 re-keyed by the lead-strip, 0 strays, 0 lost)**;
   the ONLY refusal-kind movement is the new kind 0 → 149;
   unstructured refusals 7,853 unchanged. **88 of the 149 were
   wrong-text writes armed on pre-2001 source-blocked bases** —
   defused before item 87's acquisition, which is the item's
   forward-looking point. Statute text: 13 laws move — **170
   paths of in-force law RESTORED**, 28 instruction-prose nodes
   replaced by the true occupant's verbatim text, 5 spurious
   paths removed (all `removal_right`; utlendingsloven § 105/1/b
   and § 106/1/e get their destroyed first punktum back; two
   W-69a substitutions on `2008-05-15-35` now land because the
   text they patch is back). **Scoreboard: unexplained 452 → 444**
   (12 close, 4 open deliberately — see the W-79 scan note);
   candidates 75 identical, 29/46/0 identical, **ceiling 1,011
   unmoved**, totals 1,455. Firings **10 → 10 byte-identical**;
   **θ census 133 → 129 — its FIRST movement, every one of the 8
   changed elements a withdrawn defective op** (four were wrong
   text landing VIA the θ recovery cell). Hazard destructive
   **3,870 → 3,847, the second recorded shrinkage**; hazard
   membership 164 and content-removing 240/198/77 unchanged.
   **The owned cost, ratified**: the 66 genuine-amendment ops now
   refuse typed instead of landing wrong text; two instruments
   lose their only op — index entries 2,578 → 2,576, bindings
   6,564 → 6,561, commencement grants 542 → 541 (contingent
   skips 711 → 710). **Item 88 (W-82) opened** to recover all of
   it by widening the fallback's payload reach. Sized, not
   opened: the section-level relabel-announcement family (36 ops
   / 21 nodes — closes the 4 deliberate MISMATCH rows), the
   repeal/punctuation announcement (37 ops / 6 nodes), in-place
   addressed substitution (8), move announcement (1), payload
   arity on `2018-06-15-40` § 87 (1, pre-existing). Seven
   judgement calls ratified at sign-off.

86. **W-80 (the source-availability pricing census):** DONE
   (2026-08-17; read-only, no product commit; artifacts
   `.tmp/w80/` — `w80_summary.json`, `w80_per_base_census.json`
   (788 rows), `w80_era_acquisition_curve.json`, all probe
   scripts reproducible). Opened on the user's go-ahead to price
   the pre-2001 Norsk Lovtidend question; every headline number
   reproduced the committed baselines exactly (sweep 788/201/164/
   3,870/198/77 element-for-element; scan 75 candidates 29/46/0,
   1,463 = 1,011 + 452; parse plane 29,225 ops / 7,853 unmatched).
   **Findings, ratified as the pricing baseline.** (i) **The 2001
   boundary is exact and clean in both directions**: earliest
   archived Lovtidend document `2001-01-05-1`, zero earlier; all
   442 bases missing a founding text are pre-2001; zero 2001+
   bases lack sources; zero amendments are skipped for missing
   source bytes (the archive is complete on its own terms). The
   filename mapper is era-agnostic — the gap is which tarballs
   were acquired, not code. (ii) **61.5% of the parse plane
   (17,979 of 29,225 ops) targets a source-blocked base**; the
   scoreboard measures 3.0% of the parse plane. The waiting ops
   are real: 97.0% of their written section addresses exist in
   today's consolidations (control on replaying laws: 95.2%),
   and 73% of base-attributable unstructured refusals sit on
   source-blocked bases — grammar work and acquisition compound.
   (iii) Class (c) is EMPTY: "incomplete base" and
   "blocked_contingent" are today the same set (198 + the 3
   invariant-violation laws, which are engine defects, not
   acquisition items). (iv) All 1,463 divergence rows sit on
   class-(a) laws BY CONSTRUCTION (candidacy requires source +
   consolidation + full replay), so source-blocked bases have
   zero rows structurally; calibration: 19.5 rows / 6.0
   unexplained per candidate law, 16.4% of unexplained rows
   address-coincident with a lowered op. Ceiling attribution to
   missing sources: ZERO (all 1,011 are W-17 OPS_MISSING).
   **The decision model.** Cherry-picking founding texts is
   WRONG: a lone 1981 original would replay across a 20-year
   amendment hole into the 2001+ instruments — replayable but
   wrong. The ERA model is exact: acquiring Lovtidend avd. 1
   [Y, 2000] makes every act founded in [Y, 2000] COMPLETELY
   replayable (archive contiguous 2001→2026; an act cannot be
   amended before it exists). Knee of the curve: **[1997, 2000] =
   61 bases, 6,693 ops (22.9%), 740 instruments alive**
   (skatteloven 1,665, folketrygdloven 1,639, both aksjelovene);
   [1992, 2000] reaches 32.9% and adds tvangsfullbyrdelsesloven
   (492 waiting ops — W-78's 257 understated it by one
   instrument's worth) and barnevernloven. Acquisition alone
   moves 76 laws into verification; paired with commencement
   resolution the ceiling is **258 new candidates (75 → 333, a
   4.4× frontier expansion)** — the top-20 by op volume
   contribute ZERO new candidates alone (all carry contingent
   amendments). 184 of the 442 have no consolidation (mostly
   repealed laws: opplæringslova, barnevernloven, straffeloven
   1902) — replayable if acquired, but never verifiable.
   **Unpriced risks, stated not guessed**: the pre-2001 XML
   dialect (the archive holds zero pre-2001 artifacts — if the
   dialect differs, nothing lands; gated by item 87), the
   pre-2001 drafting-grammar refusal rate, publisher bundling,
   and ~148 projected new hazard bases (0.82 incomplete→hazard
   rate, flagged as projection). **Standing position adopted:**
   pre-2001 ingestion YES, via the item-87 format probe first,
   then [1997, 2000], era windows only, commencement work paired
   if the goal is verification, pre-1950 tail deprioritized.
   Ten judgement calls ratified, including the era model over the
   footnote-chain proxy (built, validated as noisy — over-counts
   on 122 bases — and demoted, preserved in
   `probe6_consolidation_depth.json`).

87. **W-81 (the pre-2001 format probe, 1999 tarball):**
   OPEN — **BLOCKED ON ACQUISITION** (needs the Lovdata
   `lovtidend-avd1` 1999 tarball on disk; the user acquires it).
   The gating half-day measurement that retires or confirms
   W-80's unpriced risk 1 before any era acquisition: ingest the
   1999 tarball via `ingest_no_public_archives` into a SCRATCH
   farchive (never the production `data/norway.farchive`), then
   count mapped vs unmapped members
   (`iter_no_unmapped_lovtidend_xml_members`), run
   `parse_no_statute` / `parse_no_amendment_groups` over the
   mapped set, and report: member mapping rate, parse success
   rate, unstructured-refusal rate vs the 2001+ baseline
   (7,853 / 29,225), and a shape census of any new dialect
   markers (`changesToDocuments`, `data-change-part`,
   `legalArticle` presence). 1999 chosen as highest marginal
   value (2,761 ops, incl. skatteloven) and boundary-adjacent
   (dialect most likely to match). Read-only against production
   data; no production code. Small.

88. **W-82 (the own-text fallback's payload reach):** DONE
   (`5968e03ff`, 2026-08-17; artifacts `.tmp/w82/`; landing
   narrative appended after the charter below).
   Recovers W-79's owned cost: **66 ops / 43 nodes / 25
   instruments** declare a payload the fallback cannot read
   because it sits in `li` / `numberedLegalP` /
   `futureLegalArticle` / `span.futuretitle` — all outside
   `_TEXT_BLOCK_CLASSES` — so at W-79's base their lead (or an
   empty node) was being written into law, and post-W-79 they
   refuse `no_parse_structured_payload_not_declared`. Payoff
   when built: all 66 lower with their REAL payloads, the two
   dropped instruments (`no/lovtid/2023-12-20-104`,
   `no/lovtid/2025-03-28-4`) return — +2 index entries, +3
   bindings, the 542nd commencement grant. Scope sketch: census
   the 43 nodes' payload-carrier shapes (frozen by content),
   extend the payload extraction to the proven carriers with
   W-77's extent discipline (labels must match announcements
   where present; all-or-nothing), keep the W-79 invariant as the
   gate — the payload must still be DECLARED; this item only
   widens where the declared payload may LIVE. Every newly
   landed write DOM-adjudicated; the θ and firing censuses
   pinned. Small-to-medium.
   **LANDED (`5968e03ff`), no stop condition fired — the
   PROVABLE SUBSET: 35 of the 66 recovered, 31 honestly refused
   under the same kind** (the remainder is the same failure — a
   declared payload unprovable at the declared address — so no
   new kind; ratified with the charter's "all 66" corrected).
   The frozen recovery set re-derived with ZERO drift (66/43/25
   exactly; 83 keep-refusing). **W-79's gate held byte-for-byte**:
   the declaration predicate is split out unchanged
   (`_no_structured_payload_is_declared`), and the corpus-wide
   refusal-set diff at full adjudication-detail granularity shows
   post = base minus exactly 35 — 0 new refusals, 0 of the 83
   instruction-prose refusals lost or altered.
   **The reach, machine-to-machine only**: extent proved from
   Lovdata's own labels (`data-change-part`/`data-add-new-part`
   vs the carriers' `data-name`/`data-numerator`), never from
   prose. Admitted: `futureLegalArticle` sets in label BIJECTION
   with the node's section targets (17 ops / 3 nodes — whole new
   chapters, all-or-nothing per W-77; case-folded labels because
   Lovdata writes `§5A-1` in the carrier and `§5a-1` in the
   address, which is exactly why the candidate map missed);
   `span.futuretitle` headings (13 ops — sections route through
   the EXISTING `_heading_only_section_payload` behind its
   existing lead predicate, flag-gated so nothing outside the
   gate can reach it; chapters only when one address and no
   body); single leaf carriers with arity one on BOTH sides,
   leaf below section level, and a label-in-path test (5 ops).
   Refused remainder sized in 7 limbs: 4 carrier-is-parent-
   section, 8 two-targets-one-carrier, 6 many-carriers-one-
   target, 4 address-shallower-than-declaration, 3 label-miss,
   1 not-wholly-text, 5 no-carrier.
   **Measured.** Ops **29,076 → 29,111 (+35, 0 withdrawn, 0
   strays)**; `no_parse_structured_payload_not_declared` 149 →
   114; every other parse kind unchanged. ONE law's replayed
   tree moves (`2008-05-15-35`, +4 nodes): 3 writes land, each
   DOM-adjudicated single-node own-text (utlendingsloven § 105/
   1/b and § 106/1/b,e — one byte-identical to the in-force
   text; the § 106 e case correctly lands at the RELABELED
   letter, and the instrument is precisely the act inserting the
   § 90 c it cites). All three targets occupied → REPLACE with
   `replaced_paths`, never `removed_paths`: **0 paths removed
   corpus-wide, content-removing 240/198/77 unchanged**. The
   other 32 recovered ops: 23 contingent, 8 source-blocked
   (correct ops waiting on item 87's acquisition), 1 replay-
   unresolved (a chapter op whose Lovdata change-part carries no
   base-act prefix — receipt moves parse→replay plane, JC-6).
   **Scoreboard COMPLETELY unmoved**: 75 candidates identical,
   29/46/0, totals 1,455 = 1,011 + 444. Firings **10 → 10**, θ
   **129 → 129**, both element-for-element. Hazard destructive
   3,847 → 3,850 (the three writes, one row, attributed); sweep
   baseline `code` + that one adjudicated row.
   **Charter bookkeeping corrected by measurement**: index
   entries 2,576 → 2,577, bindings +1, grants stay 541 — NOT
   +2/+3/542, because `no/lovtid/2025-03-28-4` STAYS REFUSED
   deliberately (JC-4): it declares "§ 2 nr. 4 skal lyde" but
   Lovdata's change-part stops at `§ 2`, so landing it would
   write one nummer over the whole section — the wrong-text
   class again. Two more near-misses caught by the same
   label-in-path test. Also caught by measurement (JC-5): the
   first implementation landed one payload TRUNCATED to its
   heading; fixed with a wholly-reachable-as-text check, that op
   now refuses. Seven judgement calls ratified. Follow-ups
   recorded sized, none opened (largest: parent-section descent,
   4 ops; also noted pre-existing, non-W-82: the
   `_parse_future_section` heading-prefix spacing skew and the
   `CO<sub>2</sub>` → "CO 2" flattening convention).

89. **W-83 (the klimaloven full-history audit):** DONE
   (2026-08-17; read-only, no product commit; artifacts
   `.tmp/w83/` — amender enumeration, DOM extracts, replay
   traces, the beriktiget instrument, the freshness download,
   all probes reproducible). Opened on the user's go-ahead to
   adjudicate the one klimaloven divergence row (W-77's
   CONSOLIDATED_MISSING at § 7/2/e) as either the programme's
   first confirmed Lovdata consolidation defect or our own gap.
   **VERDICT: (B) — our coverage gap. Bokstav e was NEVER
   ENACTED.** The 2021 act's FIRST Lovtidend announcement
   (`no/lovtid/2021-06-18-129`, the artifact we replay) carried
   the `§ 6 annet ledd ny bokstav e` command; nine days later
   Lovdata marked that announcement `utgått` (gazettenote
   2021-06-25) and published a RECTIFIED re-announcement —
   `no://forskrift/2021-06-25-2137` "Kunngjøring av beriktiget
   versjon av lov 18. juni 2021 nr. 129", declaring
   `changesToDocuments: lov/2021-06-18-129, lov/2017-06-16-60` —
   whose operative part amends ONLY §§ 3 and 4: no § 6, no
   bokstav e, no `trepartssamarbeid`. Four independent lines
   converge: the rectified instrument's bytes; the
   consolidation's own footnotes (2021 act cited at §§ 3 and 5,
   only the 2025 renumber at § 7); the freshness check via the
   sanctioned bulk API (today's `gjeldende-lover` member
   BYTE-IDENTICAL to our snapshot, five years on); and,
   supplementary and clearly marked, Stortinget's Lovvedtak 159
   (2020–2021), which never contained the provision. Exact-text
   pins for all four are in the audit artifacts. **There is no
   removing lead** — the mechanism is whole-instrument
   supersession, not an unparsed sentence; anyone hunting an
   unlowered removal directive will not find one.
   **Why we cannot see it**: the lanes split at the iterator —
   `iter_no_amendment_artifacts` reads only
   `no://lovtid/%/amendment.xml`, and the forskrift lane feeds
   only the commencement parser, where `2021-06-25-2137`
   classifies BENIGN_NOT_COMMENCEMENT and is dropped with no
   diagnostic. The `utgått` gazettenote on the superseded act is
   filtered by the same code that admits `rettelse` blocks
   (`utgått` appears nowhere in src/tests/scripts/notes).
   Lovdata signalled the correction TWICE; we read neither.
   **The whole shape, censused**: 374 gazettenote members / 383
   notes corpus-wide (`rettelse` 314, `utgått` 69), and exactly
   **3 act-lane documents carry `utgått`** — `2021-06-11-80` →
   `2021-06-25-2136` (13 ops / 3 bases), `2021-06-18-129` →
   `2021-06-25-2137` (2 ops / klimaloven), `2024-03-15-10` →
   `2024-08-15-1960` (23 ops / yrkestransportlova). **38
   declared ops over 5 base laws unreachable**; corrections are
   NOT uniformly subtractive (two rectified versions carry MORE
   ops than what they replace), so no deletion rule can stand in
   for the production. **Item 90 (W-84) opened.**
   Four judgement calls ratified, including the trap recorded
   for the programme: **lane-scoped enumeration is not
   archive-scoped enumeration** — the first full-text sweep
   covered only the 3,089 amendment artifacts and would have
   produced a FALSE (A); widening to all 42,899 locators is what
   surfaced the rectified instrument. F-07's standing caution
   (assume our-gap until alternatives are exhausted) held for
   the second time. Not established (stated, not estimated):
   whether yrkestransportlova's 40+ existing divergences trace
   to its own beriktiget gap — no attribution claimed.

90. **W-84 (the beriktiget/utgått correction lane):** DONE
   (`55e10babd`, 2026-08-17; artifacts `.tmp/w84/`; landing
   narrative appended after the charter below). A
   CORRECTNESS item: our replay currently carries never-enacted
   text (klimaloven § 7/2/e) because we lower a superseded
   announcement, and 38 declared ops across the 3 rectified
   instruments are unreachable. Two limbs, EITHER ALONE
   INSUFFICIENT: (1) read `data-gazette-note-type="utgått"` as a
   typed suppression of a superseded gazette announcement,
   mirroring the shipped W-18 `rettelse` handling at its
   existing filter site; (2) admit the beriktiget
   re-announcement as an AMENDING instrument despite its
   forskrift-lane filing, gated on Lovdata's own
   `changesToDocuments` declaration PLUS the `beriktiget versjon
   av lov` title — NOT a blanket opening of the forskrift lane.
   Population exactly 3 pairs, both signals machine-marked by
   Lovdata; census frozen at `.tmp/w83/`
   (`gazettenote_census.json`, `beriktiget_census.json`). Payoff:
   klimaloven 3 ops → 2, the never-enacted INSERT vacates, the
   CONSOLIDATED_MISSING row closes (`replay_defect →
   consistent`, unexplained −1); the other two pairs swap 12→13
   and 19→23 ops on their bases (one contingent, one
   yrkestransportlova — a scan candidate, so its rows may move
   and each movement needs adjudication). Standard disciplines:
   frozen expected op-delta per instrument (content-keyed),
   statute diff with every changed node adjudicated, firing/θ
   censuses pinned, commencement gating of the rectified
   instruments established rather than assumed (their dates are
   the RE-announcement dates, not the acts' own). Small, high
   value.
   **LANDED (`55e10babd`), both limbs, no stop condition fired,
   all three frozen sets matched exactly** (withdrawal 34 =
   12+3+19; addition 38 = 13+2+23; destroyed-text 1 = klimaloven
   § 6/2/e, adjudicated against the rectified instrument). The
   census re-derived independently: exactly 3 `utgått` marks in
   the lovtid lane, exactly 3 forskrift artifacts passing the
   gate, no act re-announced twice.
   **The design, ratified.** Identity = the ACT: the entry keeps
   `source_id`/`title`/dates while `member_name` points at the
   rectified document, a new `beriktiget_announcement_id` field
   carries the forskrift id on the same row, and every op is
   tagged `beriktiget_announcement:<id>` — both ids visible,
   kernel group keys and commencement gating coherent (verified:
   contingent stays contingent, dated stays 2021-06-18,
   instrument_authorized stays 2024-09-01; grants 541 unchanged).
   PIT = RETROACTIVE-TOTAL, on Lovdata's own consolidation
   practice plus two-of-three windows being legally empty; pinned
   by a replay at 2021-06-19 showing no `trepartssamarbeid` and
   both real §§ 3/4 amendments landed. Suppression =
   WHOLE-INSTRUMENT despite the `utgått` note wrapping only the
   final Del in all three cases (Lovdata's own `lastupdated`
   reads it document-scope; part-scope would have left bokstav e
   standing). An unmatched half suppresses/admits NOTHING — typed
   receipts both ways (`no_beriktiget_announcement_paired` ×3,
   `..._unpaired` 0, `..._reannouncement_lowered` ×3; never a
   silent drop), pinned with four gate counterexamples. Pre-pass
   placement: superseded ops are never minted rather than
   minted-then-withdrawn (~1.5s on a ~45s build via byte
   prefilter).
   **Charter corrections by measurement**: (i) the gate is
   TITLE-DRIVEN — `no/forskrift/2024-08-15-1960` never names its
   superseded act in `changesToDocuments` (2 of 3 do), so the
   declaration is a presence conjunct, the title the signal;
   (ii) yrkestransportlova is NOT a scan candidate at base
   (blocked_contingent) — its changes adjudicated against its
   own DOM and Lovdata's consolidation instead.
   **Measured.** Ops 29,111 → 29,115 (−34 +38, 0 strays, 33 of
   34 returning byte-identical modulo the new tag); index
   entries 2,577, bindings 6,562, declared targets, unbound 927
   — ALL unmoved (conservation intact); unstructured refusals
   7,853 unchanged (5 relocate to the rectified documents'
   locators); structured-payload 114 unchanged. Statute text:
   klimaloven −1 node (the never-enacted e), yrkestransportlova
   +1 node, the contingent pair's three bases byte-identical
   (gating check). **The unbudgeted win**: at base the 2024
   act's INSERT § 9 was landing via the θ recovery and had
   DESTROYED yrkestransportlova § 9 second ledd (the
   miljøskadeleg-utslepp provision) — the rectification's added
   renumber vacates the slot, the provision returns at (3), and
   § 9 now carries six ledd matching Lovdata's consolidation
   order and text. **θ census 129 → 128** (that one recovery
   correctly stops firing; adjudicated per element); firings
   10 → 10; hazard destructive 3,850 → 3,853 (one row,
   attributed: +4 renumbers, −1 recovering INSERT);
   content-removing 240/198/77 unchanged. **Scoreboard: 29/46/0
   → 30/45/0, unexplained 444 → 443, ceiling 1,011 UNMOVED** —
   the first verdict-column movement in the scan's history (see
   the W-84 scan note). Ladder green (norway 1,070 passed);
   19 new tests; 3 new kinds cataloged. Seven judgement calls
   ratified at sign-off. **Item 91 (W-85) opened** for the
   RE-SANCTIONING family the implementation surfaced; sized, not
   opened: the friskolelova § 6A-7 whole-section restatement
   (1 op, refusal-neutral) and the read-only census of the 66
   unread `utgått` notes.

91. **W-85 (the re-sanctioning supersession family):** DONE
   (landed 2026-08-18; charter, stop record and restoration
   record kept as written below, landing record appended after
   them). A
   SECOND supersession mechanism, surfaced at W-84's landing —
   and a LIVE over-application: an act is sanctioned, found
   defective, and RE-SANCTIONED AS A NEW ACT, both halves in the
   lovtid lane, both indexed, both replayed today. Two known
   pairs: `no/lovtid/2012-12-07-71` → `2013-01-11-1` (the
   superseded act's own metadata says "Dette lovvedtaket
   inneholdt en feil og kunne derfor ikke iverksettes", yet its
   2 ops on 2 bases apply today, 25 days before the real act's
   2013-01-01 commencement) and `no/lovtid/2025-04-25-13` →
   `2025-06-20-67` (57 ops on 10 bases duplicated; both
   contingent — inert at as_of, but armed). **59 ops / 12 base
   laws to withdraw.** Materially harder than W-84: there is NO
   typed marker — the signal is prose in `miscInformation` or a
   leading `defaultP`, and the phrase set is NOT closed (W-84's
   5-needle probe missed the 2025 pair's "sanksjonert og
   kunngjort på nytt"). CHARTER: census-first with evidence
   stronger than a phrase list (candidate generators: same-title
   act pairs, duplicate op-content joins across instruments,
   `miscInformation` sweeps — let the data name the signals),
   frozen pair set with per-pair DOM adjudication, then the
   suppression design (W-84's identity/dates discipline as the
   model; note the superseded half here is a WHOLE ACT, not an
   announcement of one, so the identity question differs).
   Every withdrawal frozen and matched; scan movements
   adjudicated per element. Small-to-medium.
   **Execution attempt (2026-08-17): STOPPED AT PRECONDITION, no
   code landed, no census frozen.** The Norway corpus is not
   present on the working machine: `data/norway.farchive` absent,
   `data/norway/` holds only `bench_corpus.csv`, no
   `LAWVM_NORWAY_DB` set (the archives are intentionally not
   shipped in the repository). Receipt: `uv run lawvm
   no-verify-scan --limit 2 --as-of 2026-07-10 --json` runs
   cleanly and returns ZERO candidates against the 30/45/0
   baseline — tooling intact, data absent. Every chartered step
   is corpus-dependent (candidate generators, per-pair DOM
   adjudication, frozen content-keyed op-deltas, θ/firing/hazard
   censuses, scan adjudication), so proceeding would have been
   exactly the blind change this ledger's discipline forbids; a
   `.tmp/w85/` census against an empty corpus would have been
   vacuous, so none was written. What the read-only pass
   confirmed for the eventual run: the W-84 implementation sites
   are `src/lawvm/norway/index.py` (pairing + typed receipts,
   act-identity discipline) and `src/lawvm/norway/grafter.py`
   (the `utgått` note filter and the title-gated re-announcement
   reader), and the W-85 analogue differs as chartered — the
   superseded half is a whole indexed act in the same lane, so
   the suppression point is index/candidate level, not the
   announcement-note filter. **PRECONDITION, now explicit**:
   restore the SAME capture the scoreboard is measured against
   (consolidation snapshot `gjeldende-lover` dated 2026-07-10,
   local packages as listed 2026-07-11) — either at
   `data/norway.farchive` or via `LAWVM_NORWAY_DB` — before any
   W-85 census; a different capture makes every scoreboard row
   incommensurable. Re-attempt only after the receipt above
   reproduces the 30/45/0 cohort.
   **Corpus restored (2026-08-17, same day): PRECONDITION
   SATISFIED — on a NEW capture that reproduces the baseline
   aggregates exactly.** The four public Lovdata tarballs were
   re-downloaded via the sanctioned bulk API
   (`api.lovdata.no/v1/publicData/get/...`; `gjeldende-lover`
   lastModified 2026-08-14, sha256 `06ff01d6…edc70a`;
   `lovtidend-avd1-2001-2025` `b2984e9a…5a955ee`;
   `lovtidend-avd1-2026` `49e1eb29…70be58`;
   `gjeldende-sentrale-forskrifter` 2026-08-15 `6f497dcd…c31f36`),
   hydrated (`no-ingest`: 758 current / 3,089 originals / 3,089
   amendments / 36,006 forskrift) and indexed (2,577 entries —
   matching the W-84 count). Full scan at the new
   snapshot-commensurable `--as-of 2026-08-14`: **30/45/0 over 75
   candidates, `total=1454 (ceiling=1011, unexplained=443)`,
   ceiling rules `{address: 918, nested: 93}` — every aggregate
   identical to the pinned W-84 baseline** (Storting summer
   recess; the corpus did not move the cohort). Honest limit:
   row-level byte-comparison against the old machine's scan
   output is not possible here (that JSON was never committed),
   so commensurability rests on the exact aggregate match plus
   the unchanged index/binding counts; subsequent scoreboard rows
   read as-of 2026-08-14 on this capture.
   **LANDED (`4db511cc9`, 2026-08-18; artifacts `.tmp/w85/` —
   census, per-pair adjudication, frozen delta, base/post index
   snapshots, 12-base × 4-PIT replay dumps, base/post scans,
   corpus-wide op-key sweeps), both pairs, no stop condition
   fired, every frozen set matched exactly** (withdrawal 59 =
   2 + 57 content-keyed ops, byte-matched against the frozen
   census; additions 0; receipts 2 paired / 0 unpaired).
   **The census, generators stronger than a phrase list.** Four
   independent generators converge on EXACTLY the two chartered
   pairs: the bilateral-citation join (each half names the other
   by numbered date-and-nr citation, machine-parsed), same-title
   G1 (181 groups, only these two also citation-joined),
   duplicate-op-content G2 (56 of 57 content keys shared on the
   2025 pair, 1 of 2 on the 2012 pair — the corrected op is
   exactly the unshared one, both directions), and prose needles
   over `miscInformation` + leading `defaultP` in BOTH lovtid
   lanes. The charter's warning about the open phrase set held
   and is closed by generalization: the W-84 probe's missed
   phrase ("sanksjonert og kunngjort på nytt") is caught by the
   forward needle's optional "og kunngjort". Residuals
   adjudicated, none a candidate: G2's top overlap
   (`2009-06-19-74`/`2015-06-19-65`, 193 shared keys) is the
   straffeloven-2005 ikraftsettingslov restating consequential
   amendments — different titles, no supersession claim, no
   citation back; the three inkurie-only documents fix earlier
   acts BY ordinary amendment.
   **The corrections, DOM-adjudicated.** 2012 pair: REPLACE of
   endringslov `2012-04-27-22` § 29 — the defective act hung the
   organ list under second ledd and lacked the third-ledd lead
   ("Dersom det organet …"); the re-sanctioned act carries the
   proper third ledd. 2025 pair: INSERT of pasient- og
   brukerrettighetsloven § 4-6 fjerde ledd — the defective act
   enacted a consent-based ECT rule, the re-sanctioned act
   subordinates ECT to psykisk helsevernloven § 4-4 b. Lovdata's
   consolidation names the family itself: "… som endret ved lov
   7 des 2012 nr. 71 som resanksjonert som lov 11 jan 2013
   nr. 1".
   **The design, ratified — the identity question resolved the
   OTHER way from W-84.** A re-sanctioning mints a NEW LAW, so
   nothing transfers in either direction: the replacement keeps
   its own `source_id`, title, dates and gating (verified:
   `2013-01-11-1` stays instrument_authorized 2013-01-01,
   `2025-06-20-67` stays contingent; kernel group keys
   untouched), the new entry field `resanctioned_from_source_id`
   puts both ids on the surviving row, and every replacement op
   carries a `resanctioned_from:<id>` provenance tag stamped in
   the grafter from the document's own claim. The superseded act
   contributes NO entry and NO ops — pre-pass placement, W-84's
   discipline (byte prefilters reject 3,085 of 3,089 artifacts
   unparsed). Suppression is RETROACTIVE-TOTAL on the act's own
   metadata ("inneholdt en feil og kunne derfor ikke
   iverksettes"). Noted tension, resolved by measurement:
   statsborgerloven's footnotes also record res.
   `2012-12-07-1149` commencing the defective act (ikr. 10 des
   2012), but the replayed statute is byte-invariant to the
   withdrawal at every probed PIT — the defective act's only
   differing op targets the non-statute endringslov base, and
   its shared op θ-rejects on the absent § 29 — so the
   suppression cannot delete text that resolution would have
   commenced.
   **The gate, three conjuncts, all Lovdata's own text, failing
   closed with blocking receipts:** (1) bilateral citation —
   forward "sanksjonert (og kunngjort) på nytt som lov …" must
   meet backward "første gang sanksjonert som lov …" citing
   back; (2) title equality; (3) total re-enactment — the
   replacement's stream is non-empty and covers every base the
   withdrawn stream bound (measured: identical base sets, 2/2
   and 57/57). A document carrying both directions reads as NO
   note — ambiguity fails closed at the reader. An unmatched
   half suppresses and admits NOTHING
   (`no_resanctioned_act_unpaired`, blocking; 0 in corpus),
   pinned with four gate counterexamples in tests.
   **Measured.** Ops 29,115 → 29,056 (−59, 0 strays, 0 gained;
   the replacements' 59 ops were already in the total under
   their own ids and return byte-identical modulo the new tag —
   the corpus-wide per-instrument op-key sweep, base vs post
   over all 3,089 instruments, moved NOTHING else, which
   subsumes the θ/firing summary censuses at the lowering
   plane). Index entries 2,577 → 2,575; bindings 6,562 → 6,550
   (the twelve withdrawn (act, law) pairs; every base keeps the
   same binding from the replacement); declared targets 7,887 →
   7,875 (the withdrawn acts' own lists); unbound 927 UNMOVED.
   Diagnostics, every movement attributed: +2
   `no_resanctioned_act_superseded` (APPLY), +2
   `no_resanctioned_replacement_lowered`, 0 unpaired;
   staged-commencement-collapsed 175 → 174 and
   unstructured-lead-unmatched 7,853 → 7,852 (the 2012 act's own
   rows), cross-base-structured-target-skipped 105 → 104 (the
   2025 act's row), commencement-execution-refused 880 → 879
   (res. `2012-12-07-1149`'s refusal cited the withdrawn act and
   now has nothing to refuse against; its scope-unresolved
   receipt remains — the W-51/W-77 pinned total updated with
   attribution). Statute text: BYTE-IDENTICAL at all 12 bases ×
   4 PITs (2012-12-08, 2012-12-31, 2013-01-02, 2026-08-14) — the
   2012 over-application never surfaced in text (see the tension
   note) and the 2025 duplication was armed, not applied; the
   correction is op-plane and disarmament (replay applied-lists
   lose the withdrawn acts; `skipped_contingent` pools on 8
   bases lose the armed `2025-04-25-13` duplicate).
   **Scoreboard: 30/45/0 UNMOVED, `total=1454 (ceiling=1011,
   unexplained=443)` unmoved, all 75 rows byte-identical** —
   none of the 12 bases is a scan candidate, so this is
   conservation, not silence; no scoreboard row is added.
   Norway ladder green but for the pre-existing capture-drift
   pins (fail identically at base — see item 92); 8 new tests;
   4 corpus pins updated with W-85 attribution (entries,
   bindings, op total, refused pairs). Judgement calls ratified
   at sign-off: seven, recorded with the pair evidence in
   `.tmp/w85/adjudication.json`. **Item 92 (W-86) opened** for
   the capture-drift re-pin the restoration surfaced.
   **Sign-off (2026-08-18), with independent receipts:** the
   supervisor re-ran the full scan and diffed it row-by-row
   against its OWN pre-landing scan artifact (taken at the
   restoration, before any W-85 code existed — evidence the
   implementer never held): candidate sets equal, all 75 rows
   byte-identical, summary and totals unmoved — the conservation
   claim is independently witnessed, not self-reported. The two
   touched suites re-ran green but for the two capture-drift
   pins in `test_norway_index.py`, and both were reproduced
   failing at base commit `6359a7df` in a clean worktree with
   the same signature (36,006 vs pinned 35,955 forskrift) —
   confirming they belong to item 92, not to this landing.
   Working tree clean, sha pin verified, `.tmp/w85/` artifact
   set complete. The seven judgement calls stand ratified.

92. **W-86 (the 2026-08-14 capture re-pin):** OPEN. The corpus
   restoration (item 91) reproduces every scoreboard and index
   aggregate exactly, but SIX corpus-pinned tests fail AT BASE
   against the new capture, identically pre- and post-W-85
   (each verified by stash-rebuild):
   `test_corpus_no_consolidation_census_reproduces_the_w44_measurement`
   (2,647 ≠ 2,642 — five new amending acts),
   `test_corpus_no_consolidation_inventory_counters_and_would_be_ceiling`
   (758 current ≠ 763 — five consolidations left the snapshot),
   `test_no_verify_partition_corpus_membership_is_pinned`
   (amending_act 2,519 ≠ 2,514),
   `test_corpus_commencement_authorization_reconciles_with_the_measured_landscape`
   (36,006 forskrift artifacts ≠ 35,955; benign 33,641 ≠
   33,590),
   `test_corpus_consolidation_snapshot_date_reproduces_the_fallback_constant`
   (the capture's `current.xml` observation reads 2026-08-14,
   the fallback constant still says 2026-07-10), and
   `test_no_occupied_destination_sweep_baseline_is_not_stale`
   (the tripwire fires on corpus-moved: forskrift 35,955 →
   36,006, current 763 → 758; post-W-85 it also lists
   modules-moved for grafter/index, but the corpus trigger alone
   fails it at base). CHARTER: adjudicate the ±5/±51 membership
   drift document-by-document (which acts entered the lovtid
   lane, which current laws left and why — repeals, expiries, or
   snapshot artifacts), confirm no scoreboard candidate is
   affected, decide whether `NO_FALLBACK_CONSOLIDATION_
   SNAPSHOT_DATE` moves to 2026-08-14 (it gates every scan
   reading), regenerate the occupied-destination sweep baseline
   with every NEW firing adjudicated W-54 style, then re-pin the
   tests with the drift recorded in their comments the way every
   prior movement is. Small-to-medium; read-mostly.

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

- **2026-08-18 (W-85 — the re-sanctioning supersession family;
  `4db511cc9`)** — **The live over-application is closed: the
  two defective, re-sanctioned acts (`no/lovtid/2012-12-07-71`,
  `no/lovtid/2025-04-25-13`) are withdrawn WHOLE from the index
  — 59 ops, 12 bindings, 2 entries — and their replacements
  replay under their own identities, every frozen set matched
  exactly.** The census's four independent generators
  (bilateral-citation join, same-title, duplicate-op-content,
  prose needles over both lanes) converge on exactly the two
  chartered pairs; the W-84 probe's missed phrase is caught by
  the generalized forward needle; residuals (the
  ikraftsettingslov overlap, three inkurie documents)
  adjudicated non-candidates. The gate is bilateral prose
  citation + title equality + total re-enactment, failing closed
  with blocking receipts; ambiguity fails closed at the reader;
  the corpus exercises only the paired lane (2 paired, 0
  unpaired). Identity resolved the OTHER way from W-84: a
  re-sanctioning mints a NEW law, nothing transfers — both ids
  ride the surviving row (`resanctioned_from_source_id`) and
  every replacement op (`resanctioned_from:` tag). Statute text
  byte-invariant at all 12 bases × 4 PITs (the 2012
  over-application never reached text; the 2025 duplication was
  armed, not applied — the correction is op-plane and
  disarmament); corpus-wide op-key invariance byte-proven over
  all 3,089 instruments; **scoreboard 30/45/0 and `total=1454
  (ceiling=1011, unexplained=443)` unmoved row-for-row** — no
  affected base is a candidate. Six diagnostic movements, each
  attributed; 8 new tests; 4 corpus pins updated with W-85
  attribution. **Item 92 (W-86, the 2026-08-14 capture re-pin)
  opened**: six pre-existing corpus-pinned tests fail at base
  against the restored capture (membership ±5, forskrift +51,
  snapshot-date constant, sweep-baseline tripwire), enumerated
  and stash-verified pre-existing.

- **2026-08-17 (corpus restored on the new working machine —
  W-85 precondition satisfied)** — The four public tarballs
  re-acquired via the bulk API (capture dated
  2026-08-14/15, sha256s pinned in item 91), hydrated and
  indexed (2,577 entries, matching W-84). Scan at `--as-of
  2026-08-14`: **30/45/0 over 75 candidates, total=1454
  (ceiling=1011, unexplained=443)** — every aggregate identical
  to the pinned baseline. Future scoreboard rows read as-of
  2026-08-14 on this capture; row-level byte-commensurability
  with the old machine's output is unprovable (never committed)
  and is claimed only at aggregate level.

- **2026-08-17 (W-85 execution attempt — stopped at
  precondition; no code landed)** — The W-85 run halted before
  its census: the Norway corpus is absent on the working machine
  (`data/norway.farchive` missing, `data/norway/` holds only the
  bench CSV, no `LAWVM_NORWAY_DB`), receipted by a clean
  `no-verify-scan` returning zero candidates against the 30/45/0
  baseline. Nothing frozen, nothing suppressed, no scoreboard
  movement. Item 91 stays OPEN with an explicit precondition
  appended: restore the 2026-07-10/2026-07-11 capture and
  reproduce the 30/45/0 cohort before any W-85 census. Read-only
  reconnaissance recorded in the item: W-84's implementation
  sites, and the design note that W-85's suppression point is
  index/candidate level (whole indexed act), not the
  announcement-note filter.

- **2026-08-17 (W-84 — the beriktiget/utgått correction lane;
  `55e10babd`)** — **The never-enacted text is out of the
  replay, and the scan's verdict column moves for the first
  time: 29/46/0 → 30/45/0, unexplained 444 → 443** — klimaloven
  closes and becomes `consistent`. Both limbs landed: `utgått`
  announcements suppress whole-instrument with typed receipts
  (never silently), and the rectified re-announcements lower
  from the forskrift lane behind a title-driven gate, carrying
  the ACT's identity and dates (kernel group keys and
  commencement gating verified coherent; retroactive-total PIT
  pinned by replay). All three frozen sets matched exactly
  (34 withdrawn / 38 added / 1 destruction adjudicated).
  **Unbudgeted win**: the 2024 rectification's added renumber
  vacates the slot where the θ recovery had destroyed
  yrkestransportlova § 9 second ledd — the provision returns,
  § 9 matches Lovdata's consolidation, θ census 129 → 128
  adjudicated. Ceiling unmoved; conservation intact everywhere.
  Charter corrected twice by measurement (title-driven gate;
  yrkestransportlova not a candidate). **Item 91 (W-85) opened**:
  the re-sanctioning family — a second supersession mechanism
  with 59 ops / 12 bases double-applied today and no typed
  marker to key on.

- **2026-08-17 (W-83 — the klimaloven full-history audit;
  read-only, records only)** — **The candidate "first confirmed
  Lovdata consolidation defect" dissolves, F-07-style, into our
  own gap — and a new correction mechanism is discovered:
  whole-instrument supersession.** Klimaloven's bokstav e was
  never enacted: the 2021 act's first announcement was marked
  `utgått` nine days after publication and re-announced in a
  rectified (beriktiget) version amending only §§ 3 and 4 —
  filed in the forskrift lane, where our machinery drops it
  without a diagnostic; the `utgått` marker is filtered by the
  same code that reads `rettelse`. Four evidence lines converge
  (rectified bytes, consolidation footnotes, a byte-identical
  freshness download via the sanctioned API, and supplementary
  Stortinget lovvedtak). Corpus-wide census: exactly 3
  superseded/rectified pairs, 38 declared ops unreachable,
  corrections not uniformly subtractive. **Item 90 (W-84, the
  beriktiget/utgått correction lane) opened.** Trap recorded:
  lane-scoped enumeration is not archive-scoped enumeration —
  the first sweep would have produced a false Lovdata-error
  verdict.

- **2026-08-17 (W-82 — the own-text fallback's payload reach;
  `5968e03ff`)** — **W-79's owned cost recovered where provable:
  35 of the 66 declared-but-out-of-reach ops lower with their
  REAL payloads, 31 honestly stay refused, and the gate held
  byte-for-byte** (corpus-wide refusal diff at full detail
  granularity: post = base − exactly 35; all 83 instruction-prose
  refusals untouched). Extent is proved machine-to-machine from
  Lovdata's own labels, never prose: future-article sets in label
  bijection (whole new chapters, all-or-nothing), future-titles
  through the existing heading-only shape (flag-gated), single
  leaf carriers with arity one both sides plus a label-in-path
  test. That test is also why the charter's bookkeeping was
  corrected: `no/lovtid/2025-03-28-4` STAYS refused (its
  declaration is deeper than Lovdata's own change-part — landing
  it would rewrite a whole section with one nummer), so index
  +1/binding +1/grants unchanged, not +2/+3/542. Three writes
  land (utlendingsloven, each DOM-adjudicated; one byte-identical;
  one correctly landing at a later-relabeled letter), 23 sit
  contingent, 8 wait on item 87's acquisition. Scoreboard
  completely unmoved, ceiling 1,011, firings 10 → 10, θ 129 →
  129, content-removing unchanged, 0 paths removed. One
  truncation hazard caught by the agent's own measurement and
  closed with a wholly-reachable-as-text check. Follow-ups sized
  (7 limbs, largest 4 ops), none opened.

- **2026-08-17 (W-79 — the structured payload lane's own-text
  invariant; `1f0ca83df`)** — **The wrong-text class W-78 fixed
  dialect-by-dialect is now impossible by construction: the
  own-text fallback writes a node's prose into law ONLY when the
  node declares its own payload (operative phrase in the head
  before the first colon; the payload IS the tail).** The census
  reframed the charter's denominator to the whole fallback
  population (217 payloads / 134 nodes): 68 declare and keep
  lowering (61 byte-identical), 149 refuse typed — not one
  carrying statute content, 23 of them writing EMPTY nodes, and
  **88 armed on pre-2001 source-blocked bases**, defused before
  item 87's acquisition. 13 laws' statute text moves: **170 paths
  of in-force law restored** (utlendingsloven's destroyed punktum
  back; two W-69a substitutions land on restored text), 28
  instruction-prose nodes replaced by the true occupants, 5
  spurious paths removed, all adjudicated. **Unexplained 452 →
  444** (12 close, 4 deliberate MISMATCH opens — right text at
  the pre-relabel label beats nothing-here), ceiling unmoved.
  **θ census 133 → 129, its first movement** — all 8 elements
  withdrawn defective ops, four of them wrong text landing via
  the recovery cell; firings 10 → 10. Hazard destructive 3,870 →
  3,847, the second shrinkage. Owned cost ratified: 66
  genuine-amendment ops (payload outside the text-block classes)
  refuse typed; **item 88 (W-82, the payload-reach widening)
  opened** to recover them.

- **2026-08-17 (W-80 — the source-availability pricing census;
  read-only, records only)** — **The pre-2001 question is priced:
  the 2001 coverage boundary is exact and clean (all 442
  source-blocked bases pre-2001, zero 2001+ gaps, zero skipped
  amendments), and 61.5% of the parse plane — 17,979 of 29,225
  ops — waits on missing founding texts, with the scoreboard
  currently measuring 3.0% of the parse plane.** The waiting ops
  are real (97.0% of their addresses exist in today's
  consolidations; 73% of the refusal backlog sits on blocked
  bases, so grammar and acquisition compound). Decision model
  ratified: era windows only — cherry-picked founding texts
  replay across amendment holes and are wrong by construction;
  the knee is **[1997, 2000]** (61 bases, 6,693 ops, 22.9%);
  verification needs commencement work paired (alone: 76 new
  candidates; paired: up to 258 — 4.4× frontier expansion).
  Standing position adopted: pre-2001 ingestion YES, gated by
  **item 87 (W-81, the 1999 one-tarball format probe — opened,
  BLOCKED ON ACQUISITION)**, since the pre-2001 XML dialect is
  unknowable from inside the repo and is the one risk that could
  zero the entire payoff. Every census number reproduced the
  committed sweep and scan baselines element-for-element.

- **2026-08-17 (W-78 — the substitution-announcement address list
  mis-lowered as a payload target; `efc32b19e`)** — **The
  programme's only known wrong-text defect is closed, and it was
  worse than sized: 15 wrong-text nodes stood in the replayed
  statute of `no/lov/2008-05-15-35` at base, 11 of them having
  destroyed substantive in-force text (13 child nodes) — all
  reverted, the destroyed children restored verbatim.** Root
  cause corrected from the charter: no payload reader mis-fired —
  the W-69a announcement recognizer's opener enumerated the noun
  after `følgende` and lacked `steder`, so the new dialect fell
  through to the structured lane, which read `data-change-part`
  as 116 REPLACE targets and the announcement as their payload.
  Fix: opener generalized (the noun list WAS the defect), the
  weight moved to a rule — term and verb must stand complete in
  the head before the first colon (the W-75 principle) — with
  the corpus-wide proof: governing nodes 17 → 24, exactly the 7
  defect nodes, the 5 near-miss payload-declaring nodes still
  declined. All 116 re-route to the shipped substitution
  production (+290 correct TEXT_PATCH ops, 29,051 → 29,225): 8
  land verbatim-verified, 19+6 refuse typed, and the 1992 law's
  257 correct ops wait only on source acquisition. Scoreboard,
  ceiling, candidates, content-removing, and both firing
  censuses all unmoved; hazard destructive writes 3,885 → 3,870,
  **the hazard census's first recorded shrinkage**. **Item 85
  (W-79) opened**: the structured lane's missing own-text
  invariant (267 nodes), the general closure that makes this
  wrong-text class impossible by construction.

- **2026-08-16 (W-77 — the item-depth payload production;
  `9c81b2c90`)** — **The programme's first content-ADDING
  production at scale, and the first scoreboard movement since
  W-66c: unexplained 453 → 452** (two rows close — the projected
  `2004-03-26-17` § 2/1/g, whose law returns to `consistent`, and
  `2012-01-27-9` 5 → 4 — and one opens deliberately: klimaloven
  `2017-06-16-60` § 7/2/e CONSOLIDATED_MISSING, an honest
  instrument-vs-consolidation gap). Refusals **8,078 → 7,853
  (−225)**, the census having DOUBLED the charter (225/96, the
  charter's 146 was the spelled-ledd cut); ops +160 INSERTs; both
  frozen sets (withdrawal AND added-content — the discipline's new
  second half) matched exactly. Grammar anchored end-to-end on the
  announcing node's OWN text (the payload sits inside it as a
  `<ul>`); extent proved label-for-label on top-level items,
  all-or-nothing, multi-label handled provably; occupied targets
  REFUSE via a tag-gated guard ahead of the shipped θ recovery
  (fires zero times; θ census 133 → 133 untouched); the
  relabel+payload pair composes in the kernel's vacate ordering.
  **22 statute nodes added, 0 destroyed**, each DOM-adjudicated;
  `2005-06-17-90` § 6-2 is byte-identical to Lovdata's
  consolidation (W-76's gap closed); straffeloven § 37 honestly
  reclassified as a different family. **Item 84 (W-78) opened**:
  a pre-existing mis-lowering W-77 made reachable — substitution
  announcements' address lists mis-read as payloads, 116 defective
  REPLACE ops, 27 already landing at base on 2 non-candidate laws.

- **2026-08-16 (W-76 — the sibling-set relabel at item depth
  (`bokstav`/`nr.`), the prefix grammar; `82a0c2adc`)** —
  **Unstructured refusals 8,078 (−63), the frozen 63-element
  withdrawal set matched exactly, ops +67 = the minted legs, and
  the verify-partition report BYTE-IDENTICAL — the zero yield was
  projected before implementation and realized honestly.** The
  family W-66b's sizing pass separated (prefix depth word on a
  letter/numeral, not the postfix ordinal grammar) lands whole:
  shared qualified-section head extracted on the rule of three,
  explicit-expansion label vocabulary (`a`–`z` and digits only,
  ranges enumerated), ledd REQUIRED and always antecedent-
  inherited (the 1,529-node probe shows every `item` sits below a
  `subsection`; first-match DFS makes shallow addresses unsafe),
  `_no_antecedent_ledd_label` parameterized with shipped call
  sites byte-identical, new kind
  `no_parse_item_set_relabel_ledd_unresolved` (22), W-66's tag /
  ordering / guard reused with zero apply-plane edits. Firings
  10 → 10 byte-identical, content-removing unchanged, no
  `removal_wrong`. Statute text moves on 3 laws (DOM-adjudicated;
  5 REPLACE → INSERT promotions exactly right); the visible gap
  the relabel leaves where a `ny`-marked payload lead has no
  production names **item 83 (W-77, the item-depth payload
  production, 146 refusals / 64 bases — opened)**; the item-depth
  REPEAL (166 refusals, two correct occupied-destination
  refusals naming it) and the ledd-spelling arm (26) sized, not
  opened. Census re-derived identical to the two-landings-old
  sizing — the first population that did not drift.

- **2026-08-14 (W-66c — the punktum-depth REPEAL production;
  `b7a2d76e9`)** — **The first landing to move the
  content-removing column (207 → 240, all 33 destructions frozen
  before implementation, matched element-for-element after, and
  individually DOM-adjudicated — none rests on an inherited
  address), and the first to SHRINK the candidate set (76 → 75,
  honest exposure: a newly lowered instruction reveals a contingent
  binding that was always in the source — W-73 backwards).** The
  charter's "small" was off by an order: 293 refusals / 235 leads /
  136 bases of the strict `oppheves` shape withdraw (8,434 → 8,141),
  +279 REPEAL ops (28,545 → 28,824). Grammar drawn tighter than the
  relabel because it destroys: verb anchored to `oppheves` alone
  (24 nynorsk refusals priced), sentence must end at the verb,
  `siste punktum` refuses on principle, a ledd is required. Shipped
  REPEAL action one level deeper, zero apply-plane edits; the
  repeal-before-relabel ordering is the kernel's structural-vacate
  stage, pinned with deliberately mis-ordered ops. The witness
  closes W-66b's loop: repeal lands, slot vacates, the refused
  relabel converts (32 → 31), § 20 første ledd pinned by text, the
  law returns to `untouched_drift`. Scan: 3 genuine closes (all
  join-projected), 0 opened, total 1,464 / ceiling 1,011 unmoved /
  **unexplained 453**. Firings 10 → 10 byte-identical; 38 statute
  movers all expected, 747 byte-identical; three base laws enter
  the sweep; 8 undeclared bindings surfaced on
  `no/lovtid/2009-06-19-74`; hazard content-removing 168 → 198 over
  77 laws with the destruction set pinned by content as its
  tripwire.

- **2026-08-14 (W-66b — the sibling-set relabel at PUNKTUM depth;
  `f1673a96c`)** — **The largest refusal withdrawal since W-66
  itself: unstructured refusals 8,583 → 8,434 (−149), ops 28,384 →
  28,545 (+161, exactly the frozen leg count), zero scoreboard rows
  — honestly measured, structurally explained — and one would-be
  wrongful sentence deletion prevented by the reused guard.** The
  mandated sizing pass ran first: population re-derived untruncated
  at 165 refusals / 84 leads / 115 instruments / 78 bases (grown
  from the design's 144), the address-coincidence join reproduced
  the single-candidate finding (projected ≤ 1 row), and
  `bokstav`/`nr.` turn out NOT to be this grammar one word down —
  they PREFIX their depth word to letters/numerals (27 and 36
  refusals with a correctly-shaped classifier; a separate item, not
  opened). What shipped: W-66's grammar with `punktum`, strictly
  behind the shipped ledd lane; destination reduces to ordinals
  ALONE so the cross-container relocation is impossible by
  construction; two-level antecedent inheritance from ONE
  `defaultP` node; new parse-plane kind
  `no_parse_punktum_set_relabel_ledd_unresolved` (27); W-66's
  ordering, tag, and occupied-destination guard reused with ZERO
  apply-plane edits. Frozen set 165/165 element-for-element (112
  lowered / 37 typed / 16 declined, 0 strays). Firings 10 → 10;
  statute diff 14 movers all expected, 771 byte-identical; hazard
  3,827 → 3,828 (+3 RENUMBER −2 REPLACE, one law); base-law
  population 784 → 785; three instruments gain first index entries,
  binding conservation exact. The one new apply-plane refusal is
  the item's finding: `no/lov/2021-06-18-121`'s relabel refuses
  because its companion punktum-depth REPEAL has no production —
  had θ fired it would have deleted an in-force sentence. **Item 81
  (W-66c) opened** for the repeal; the family's zero yield is
  otherwise structural (42 of 59 written bases have no original-act
  source).

- **2026-08-14 (W-70b — Lovdata destination-section repair on
  `data-move-part`, behind a population tripwire; `a915f7d69`)** —
  **The two provisions W-69c's landing exposed as overwritten are
  recovered and in force, and the six-leg relocation on
  `no/lov/2009-06-19-44` applies in full** — refusals 6 → 0,
  `insert_occupied_target_replaced` 139 → 137, `statute_len` +302 =
  exactly the two provisions, adjudicated ledd-by-ledd against the
  instrument's four change blocks. The repair is a prose-gated
  destination-section normalizer, W-70's shape: of 35 censused
  cross-section attributes (frozen before building), exactly ONE —
  the `subsection → subsection` defect — passes the seven-limb
  prose proof; 33 ordinary section renumberings and 1 genuine
  sentence→section promotion decline typed and pass through
  byte-identical, pinned by content on both halves so a growing
  family fails closed and a regression that "repairs" genuine moves
  fails loudly. The rewrite is structurally confined to the
  destination's section component; the shipped relabel grammars
  prove the prose (no new sentence grammar); limbs 4–7 are held by
  a synthetic decline suite pending a corpus witness. Firings 10 →
  10, no `removal_wrong`, content-removing 207/168 unmoved, scan
  totals unmoved (76 / 29-47-0 / 1,471 / 1,011 / 460); hazard
  3,823 → 3,827, all the one law's own writes. The W-69c witness
  is rewritten from pinning the loss to pinning the recovery, by
  text.

- **2026-08-13 (W-69c — the atomic relocation ordering generalized
  to `(parent_path, label)`, as a provability refusal;
  `d5699c464`)** — **W-72's blind spot goes 4 laws → 3, zero
  divergence rows by design, and W-69d's hard prerequisite is
  satisfied.** The design's ordering framing did not survive the
  data: `no/lov/2009-06-19-44`'s two colliding legs are mutually
  unsatisfiable — a Lovdata `data-move-part` attribute names the
  wrong destination section against its own prose — so the fix is a
  provability TEST at the apply seam, not a reordering. Union-find
  components over `(parent_path, label)` nodes; a contested
  destination, contested source, or cycle refuses the whole
  component typed
  (`no_replay_relocation_order_unprovable_refused`, in the skip
  set), first in the RENUMBER branch, before any write. The
  un-aborted law surfaces two pre-existing INSERT-occupied
  replacements the abort was hiding (typed blocking receipts, 137 →
  139); ratified as the right trade and item 80 (W-70b) opened to
  repair the source defect. Firings 10 → 10, verdict table
  unchanged, no `removal_wrong`; 783/784 statutes byte-identical;
  scan totals measured unchanged (76 / 29-47-0 / 1,471 / 1,011 /
  460); hazard 3,816 → 3,823, all the one law's own writes, zero
  content-removing. A latent false-contest on repeated legs was
  caught mid-item and deduplicated (two corpus groups protected).
  The kernel's `renumber_vacate` stage is exonerated: full-path
  keyed, worked as designed, structurally incapable of reporting
  "no order exists". Cross-container legs re-measure at 7 (the
  design's 14 was pre-W-70).

- **2026-08-13 (W-69b — read-only sentence materialization on the
  text-patch path; `ccf623ae4`)** — **7 more unexplained rows
  close (467 → 460) and the sentence half of the substitution family
  is fully served or typed.** The materialization-before-resolve
  block is lifted into a closure called from BOTH arms of the replay
  dispatch, so a `setning/N` `TEXT_PATCH` resolves whenever its
  parent ledd does; W-69a's per-address sentence refusal is deleted
  and `no_parse_substitution_sentence_address_out_of_scope` is
  RETIRED (it named a phase boundary that no longer exists). The
  frozen 21-receipt withdrawal set matched element for element: 17
  landed, 1 banked (no original-act source), 1 refused
  `inflection_only`, 2 refused `replay_unresolved_target` alongside
  their five ledd siblings with the same defect. Ops 28,363 →
  28,384; materialization receipts 807 → 822, reconciled op-by-op
  including one double-materialization behind a rolled-back refusal.
  The full-corpus statute diff the design priced was paid: 781 of
  784 byte-identical, 0 shape-only movers, and the 3 movers' 17
  word-level changes are exactly the 17 announced substitutions.
  Hazard 3,810 → 3,816, one law (`no/lov/2008-06-27-71`, six
  sentence-depth siblings of W-69a's § 12-12 write); content-removing
  unchanged; firings 10 → 10 byte-identical; ceiling 1,011 unmoved;
  0 rows opened. Design corrected: +21 ops not +19, 17 landings not
  19, **+7 rows not +8** — one karanteneloven ledd carries two
  sentence addresses and the capitalised term's row stays honestly
  open.

- **2026-08-12 (W-69a — the addressed word substitution lowers for
  real; `17e5dcfb4`)** — **11 unexplained divergence rows close,
  the first this programme has closed by ADDING a production instead
  of refusing one, and the design's projection was right to the row
  and to the law.** W-75's blanket refusal of the "announcement plus
  address list" construct is replaced by a producer minting one
  addressed `TEXT_PATCH` per (listed address × announced pair) onto
  a shipped apply branch that had no producer. Envelope: S1 exactly
  one announcement opener, S2 the address list names exactly the
  block's base act, S3 the `(FROM, TO)` grammar parses, S4 W-75's two
  conjuncts unchanged, a per-address `setning/N` refusal (W-69b's),
  and at apply S6/S7 — exactly one announced term present, occurring
  exactly once as a whole word and exactly once as a substring.
  **The design is wrong that half 2 needs nothing in the conserved
  partition.** S5–S7 need the addressed node's TEXT and the parse
  plane has no statute — replay consumes parse output — so
  `no_replay_substitution_term_not_uniquely_present` joins
  `_NO_SKIP_ADJUDICATION_KINDS`; two of its six reasons would
  otherwise have WRITTEN, wrongly, through an unguarded recursive
  `str.replace`. S5's `no_statute` arm degrades from a receipt to a
  banked op, stated at item 77 rather than dropped. Two sizing
  corrections: 23 addresses lower, not 40 (the design's count did not
  subtract the 17 belonging to the four-announcement node S1 refuses
  whole), and the W-75 receipt goes 17 → 0, not 17 → ~5 (S2 subsumes
  S3's only node). Measured: ops 28,252 → 28,363 (+111, nothing
  lost, content-keyed, every one a `text_patch`); adjudications
  10,885 → 10,891; bindings 6,493 → 6,496 and the declared-target
  receipt census 949 → 947 in step (three bindings W-75 removed,
  returning as real ops); entries 2,565, population 784, candidates
  76, unstructured refusals 8,583 all unmoved. Blast
  over all 784 laws against pristine `1ffd5c5a7`: **15 movers, 769
  byte-identical, residue 0**, only three with text movement, 15
  landed writes, corpus content-removing 207 → 207. Scan: total 1,489
  → 1,478, ceiling **1,011 unmoved**, unexplained 478 → 467,
  scoreboard **29/47/0**, 0 rows opened, no flips. Hazard census
  re-pinned consciously: 3,809 → **3,810**, one law
  (`no/lov/2008-06-27-71` [79, 2] → [80, 2]), membership and
  content-removing unchanged. **Firings 10 → 10 element for element;
  no `removal_wrong`; W-72's blind spot unchanged at 4 laws.**
  (Artifacts `.tmp/w69a/`: frozen expected set, before/after
  censuses, blast attribution, ladder logs.)

- **2026-08-12 (W-69 design pass — records only, no product change)**
  — **Both halves of W-69 turn out to need parse productions and not
  a new op kind, because both already lower somewhere in the corpus
  today; the relocation op that already ships is UNSOUND across
  containers and that is why one of W-72's four blind-spot laws is
  blind; and the standing reading that no unexplained divergence row
  is reachable by an open item is false by 19 rows.** (Design
  document `.tmp/w69/design.md`; ten scripts and their artifacts in
  `.tmp/w69/`, every sizing re-derived at HEAD `4a68b5a48` and none
  copied forward. Baselines reproduce the ledger element for
  element: 3,089 artifacts, 28,252 ops, 8,583 unstructured refusals,
  17 substitution refusals, 76 candidates, total 1,489 / ceiling
  1,011 / unexplained 478.)
  **Vocabulary.** `RENUMBER`+`destination` resolves
  `op.destination.parent()` and re-parents the same `IRNode`, so it
  IS relocation — and the structured `data-move-part` lane already
  mints 14 cross-container legs, including the punktum-between-ledd
  shape the queue called the one lead strictly needing a new op
  kind. An ADDRESSED `TEXT_PATCH` has a shipped apply branch that no
  producer reaches. `StructuralAction.MOVE` stays dead vocabulary.
  **Soundness.** `no/lov/2009-06-19-44` aborts mid-apply with
  `duplicate subsection:4` because a cross-container in-migration
  (`§3/ledd/3 → §2/ledd/4`) is not ordered against the destination
  parent's own vacate shift (`§2/ledd/3 → §2/ledd/4`); W-66's
  ordering is over integer ordinals inside ONE sibling set and a
  cross-container move belongs to two. Recorded against W-72's
  blind-spot narrative; fix is W-69c.
  **Sizings.** Relocation arms A/B/C: **83 refusals / 81 distinct
  leads / 46 instruments / 41 base acts**, 13 known-incomplete, and
  **only 13 of the 81 restate a payload** — the prior "8 of 9 real
  moves are restated" is 5 of 9, and the three carry-existing cases
  are not the ones the entry named. Arm C's endpoint expander
  STRANDS lettered intermediate sections (`§§ 23 til 26` is 4 labels
  and 7 sections), and W-57's own witness is genuinely
  unequal-arity at section depth (6 sources, 7 destination labels) —
  W-62/W-66's corrected premise holds at ledd depth only.
  Substitution: **17 nodes / 193 addresses** reproduce exactly, **42
  exact / 40 whole-word deterministic**, 104 no-statute, 30
  unresolved.
  **Three W-75 characterizations corrected, W-70-style:** the 30
  unresolved are 21 sentence + 5 subsection + 3 section + 1 item,
  not all `setning/N`; **98 of the 104 no-statute blockers are an
  ACQUISITION gap** (`no original-act source available`), not
  W-73-shaped commencement work; and `henholdsvis` pairs FROM-terms
  with TO-terms rather than addresses with terms — with the real
  hazard being the one node carrying FOUR announcements over 82
  addresses and 35 base acts, which explains 9 of the 13
  "term absent" addresses and must refuse whole.
  **Scoreboard.** Adjudicated row by row against both texts, the
  substitution arm closes **11 unexplained rows today and 19 with a
  read-only sentence materialization** — karanteneloven
  `no/lov/2015-06-19-70` (4 + 7 of 12) and `no/lov/2020-04-17-29`
  (7 + 1 of 15). `no/lov/2016-06-17-29`'s **21 unexplained rows are
  fully attributed** to `no/lovtid/2020-06-23-98`'s unlowered
  restructuring cascade and are deliberately NOT bought: reaching
  them needs a chapter-repeal production and a chapter-depth set
  relabel that nothing in the queue describes.
  **Ratified decisions:** no new op kinds; whole-word matching
  (costs exactly one row, karanteneloven `§ 20 fjerde ledd`);
  read-only sentence materialization over ledd-text addressing (19
  of 21 vs 14 of 21, and it fails closed); multi-announcement nodes
  refuse whole; the known-incomplete-base hazard pin moves
  consciously with an attributed delta. **Re-phased into W-69a
  (medium, AUTHORIZED, +11 rows) → W-69b (small, +8) → W-69c
  (medium, 0 rows, blind spot 4 → 3) → W-69d (large, 74 refusals, 0
  rows, HARD-BLOCKED on W-69c) → W-69e (3 leads, 0 rows).**
  **W-66b opened** with its sizing: the same set relabel at PUNKTUM
  depth is **144 refusals / 63 leads / 100 instruments / 69 base
  acts** — roughly twice all three relocation arms combined, one
  token from a production that already ships and is already proven —
  with its row yield explicitly unmeasured.

- **2026-08-12 (W-70 applied)** — **Six malformed `data-move-part`
  attributes turned out to be nothing but separator damage, four of
  them are repaired, and the triage artifact that described them
  would have made a normalizer move every ledd the wrong way.**
  (`d7ec7a259`, artifacts `.tmp/w70/`.) W-62's census lists the
  tokens in the order the splitter iterates them, which is REVERSED;
  read forward off the `article.change` node the parser reads, three
  values carry a STRAY SPACE after `;;` (whitespace is the pair
  delimiter, so one intended pair becomes a token with no
  destination plus a token with no separator), one has `::` typed
  for `;;`, one has no separator anywhere, and one fuses two pairs
  at a missing space. On the reversed reading the first three look
  like `<dest> <source>;;`. The DOM probe is the whole reason this
  item repairs rather than destroys. **Two rules, both pure
  separator repairs, each checked against a SKELETON invariant** —
  the value with `;` and `:` removed must be byte-identical before
  and after, so no rule can invent, drop or reorder an address —
  **at most one rule per value, and a rewrite that leaves any token
  malformed is not taken.** The cross-base gate is checked first and
  keeps the two named blocks refused (`2024-06-21-46` →
  `lov/2010-03-26-9`, `2026-02-06-2` → `lov/2024-06-21-41`, both
  filed under the wrong base by the archive); the fused-pair defect
  deliberately has no rule because its only instance is one of them.
  **Malformed receipts 14 → 3, exactly −11, 0 introduced, equal to
  the frozen expected set element for element;** ops 28,246 →
  28,252 (six legs, nothing lost); entries 2,565, bindings 6,493,
  amended-law population 784, unstructured refusals 8,583 — all
  unmoved. **Standing tripwire:** the population is re-derived from a
  live parse of all 3,089 amendment artifacts and pinned at
  membership level (blocks, defect classes, decline reasons, and the
  exact legs each repair lowers), so an archive refresh that adds a
  malformed block fails loudly instead of accumulating a silent
  refusal. **Blast: 4 of 784 laws move, all attributed, 780
  byte-identical** — three move by RECEIPT ONLY (co-amended by
  `2025-04-10-11`; NO attaches an instrument's parse adjudications
  to every base it amends), one is the payoff. **Payoff:**
  karanteneloven `no/lov/2015-06-19-70` § 8, divergences 14 → 12,
  both rows the ones W-72(c) attributed to this item, 0 opened —
  the refused attribute had left the block's INSERT landing on a
  LIVE andre ledd, which the insert-occupied recovery replaced.
  **That means this item RESTORES A DESTROYED IN-FORCE PROVISION,
  which a tripwire item was not priced to do:** karanteneloven § 8's
  andre ledd ("Lønn eller vederlag for annet arbeid, verv eller
  oppdrag …", printed at § 8 tredje ledd in the consolidation) was
  absent from the replayed tree and is back. The W-54/W-67 shape one
  level over — a recovery clearing a slot the amendment meant to
  VACATE — hidden by the very refusal that left the slot occupied.
  Corpus `insert_occupied_target_replaced` 138 → 137. Candidates
  76, scoreboard 29/47/0, ceiling 1,011 unmoved; divergence total
  1,491 → 1,489, unexplained 480 → 478. **Occupied-destination
  firing census 10 → 10 and the hazard census 161 / 3,809 / 168
  over 65 unmoved** — the recovered legs carry no W-66
  refuse-on-occupied tag on purpose, and they need none: the
  kernel's vacate stage runs REPEALs first and topologically sorts
  the renumbers, and every one of the six destinations is free when
  its leg runs. Sweep baseline regenerated; only the code digest
  moved.

- **2026-08-12 (W-66 applied)** — **The renumber-shift family lowers,
  682 refusals withdraw, and the item's own measurement fired the
  `removal_wrong` stop condition — which is why the production
  refuses at the APPLY plane rather than taking the declared
  recovery.** (`dc4b3e4e4`, artifacts `.tmp/w66/`.) One production
  for the LEDD sibling-set relabel ("Nåværende femte og sjette ledd
  blir sjette og sjuende ledd."), emitted as one atomic group in a
  proven vacate-before-occupy topological order, with the shipped
  W-56 sentence parser tried first character for character and a
  one-token widening (W-61's currency-qualifier set) behind it.
  Address inheritance from the nearest preceding `article.defaultP`
  in the same part — DOM-local, so it is self-guarding across law
  switches — with a typed receipt for the 40 that cannot be
  addressed. **Refusals 9,265 → 8,583, exactly −682, 0 introduced,
  reconciling element for element as 642 lowered + 40 typed;** ops
  27,099 → 28,246; entries 2,563 → 2,565; bindings 6,484 → 6,493;
  amended-law population 783 → 784. **Blast: 59 of 783 laws move,
  all inside the derived expected-change set, 0 outside, 724
  byte-identical** — after normalizing op_id ordinal churn and the
  per-instrument parse adjudications that attach to co-amended laws
  (the raw diff says 158, and the raw diff is worthless). Candidates
  76, scoreboard 29/47/0, ceiling 1,011 — all unmoved; divergence
  total 1,501 → 1,491, unexplained 490 → 480, **12 rows closed / 2
  opened**, both entrants adjudicated. **The stop condition, and it
  is the story:** with the ops taking the declared θ `(RENUMBER,
  dest_occupied)` recovery the firing census went 10 → 25 and two
  new firings were `removal_wrong` — straffeloven 2005 § 3 femte
  ledd and verdipapirhandelloven § 9-21 fjerde ledd, both destroyed
  because the archived BASE edition already carries the amendment
  being replayed. The landed production refuses those legs instead,
  and the refusal cascades so the relabel drops whole; **firing
  census back to 10 → 10 equal element for element, verdict table
  unmoved, both provisions pinned as surviving.** Sizing correction
  recorded: this family is 622 leads, not the "13 of 16" the queue
  entry priced, and no unequal-arity relabel exists anywhere in it.

- **2026-08-12 (W-75 applied)** — **A word substitution announced in
  prose was being lowered as N REPLACEs carrying the announcement,
  and the census that opened the item undercounted it four-fold.**
  (`c36e2de13`, artifacts `.tmp/w75/`.) Lovdata writes "I følgende
  bestemmelser skal ordet «X» endres til «Y»:" and then lists the
  provisions; the list carries `data-change-part`, so the structured
  lane read N targets and used the node's own prose as their payload.
  **107 REPLACEs over 10 instruments and 13 base laws, every one
  overwriting in-force law with the amendment's address list.** The
  stopgap refuses the construct with a typed receipt
  (`no_parse_substitution_announcement_not_lowered`); the substitution
  itself still has no op to lower into and stays open as W-69's.
  **W-72's census said 4 nodes because it tested only the preceding
  sibling.** Thirteen nodes carry the announcement in the change
  node's OWN text, and one of the four it did find was a false
  positive. Re-probed over all 3,885 structured change nodes: 17
  nodes, 193 addresses. **And keying the refusal the way the item was
  scoped would have destroyed real law**: `no/lovtid/2026-06-19-45`
  puts four genuine `§ X skal lyde:` nodes immediately after
  announcements, so the discriminator's second conjunct — the node
  declares no operative payload of its own — is what makes the first
  one safe. The opener is anchored for the same reason:
  `no/lovtid/2025-04-25-12` carries the announcement's words
  mid-sentence in ordinary payload prose.
  **Ops 27,206 → 27,099 with 0 gained and 0 changed** on a
  content-keyed identity diff, all 107 REPLACE. Replayed text moves
  on exactly three laws and **780 of 783 are byte-identical**; the
  eleven further laws that move do so only on adjudication and
  receipt digests, from 80 cross-base-skip receipts that no longer
  exist and op ids renumbering. Karanteneloven's 15 destroyed
  provisions become **12 rows that each diverge on exactly the
  superseded word**, five `OPS_MISSING` litra rows closing as their
  parents come back. Plan- og bygningsloven's seven destructions —
  invisible to every scan, because the law is `blocked_contingent`
  and is not a candidate — are confirmed gone by reading the replayed
  tree directly. Hazard census 3,713 → 3,706 with exactly one law
  moving, `no/lov/2008-06-27-71` [73, 2] → [66, 2]; firings 10 → 10
  equal element for element; candidates 76 and scoreboard 29/47/0
  unmoved; divergence total 1,504 → 1,501.
  **Bindings 6,489 → 6,484, reported not buried**: five
  `(instrument, base)` bindings existed only because of the garbage
  ops and go with them, with no executable status moving.
  **The follow-up is priced, not guessed** (`substitution_sizing.
  json`): of 197 addresses, **47 could be substituted deterministically
  today**. 103 sit in laws with no replayed statute, 30 are
  `setning/N` addresses that do not resolve until something has
  written to the ledd — a design constraint for the real op, not an
  accident — and only 82 come from an announcement naming a single
  pair.

- **2026-08-11 (W-72 applied)** — **The occupied-destination pin
  stops describing nine laws and starts describing the corpus, and
  the cache that makes that affordable cannot lie about being
  stale.** (`c80ce0a6a`, artifacts `.tmp/w72/`.) Tests, tooling and
  receipts only; no product behaviour moved and none needed to.
  A full sweep of all 783 base laws runs out of band
  (`scripts/inventory_no_occupied_destination_sweep.py`, 3m28s at 10
  processes) and commits its census; the shard pays **2.5s** to
  recompute the receipt that says the census still describes this
  tree.
  **The receipt is two digests, and the second one is the whole
  point.** Corpus identity is every artifact in all four Norway
  planes as `(logical_id, sha256(payload))` — logical, not a hash of
  the WAL-mode `.farchive`, so a VACUUM cannot raise a false alarm
  and teach people to regenerate without reading. Code identity is
  the sha256 of every file in the STATIC IMPORT CLOSURE of the
  replay entry points, derived by AST walk: **79 modules, 0.3s**, no
  neighbouring frontend inside it. W-67 changed the parser and not
  the archive, so the corpus half alone would have gone on passing
  exactly as the seven-law list did. Verified end-to-end: one
  comment line appended to `grafter.py` reddens the pin in 3.3s and
  names the module.
  **What it proves.** 10 firings corpus-wide, equal element for
  element to the adjudicated verdict table — the 10 rows the table
  carried ARE the corpus, checked rather than hoped. `wrong == []`
  now holds corpus-wide. **The sweep also found its own blind spot
  and named it**: four laws abort mid-apply on an invariant
  violation, discarding the apply plane, so their firings are
  unobservable; they produce no replayed statute either, so nothing
  is at risk today, and the set is pinned so that repairing one is
  loud. The 440 laws that error before any op is applied are counted
  separately, because "no original-act bytes" is a complete answer
  and "died halfway" is not.
  **The docstring that started the item is now true.** The live pin
  owns EFFECT and says so; a new test owns POPULATION; a third
  compares the cache against the live replay on the nine laws
  already being replayed, so determinism is checked and not merely
  asserted. Three corpus-free guard-liveness tests prove the
  staleness check can fail, names what moved, and points at a script
  that exists.
  **W-73's rider (d) becomes a pin instead of a `.tmp` file**, riding
  the same replay pass for nothing: 198 known-incomplete bases, 265
  taking destructive writes, **161 in the intersection**, 3,713
  destructive writes, 167 removing content across 65 laws, plus a
  membership hash. W-73's 163 / 3,737 / 159 / 64 conserves exactly
  into it — three laws leave as `blocked_contingent` clears, one
  enters. It is a census receipt, not a licence: **husbankloven is
  still in the set**, because W-73 repaired one amendment's
  commencement and another is still contingent.
  **And the rider found a live destruction nobody had recorded.**
  Triaging the 27 rows W-73's three entrants brought in: 7 are
  reachable by an open item (5 W-66, 2 W-70) and 20 are reachable by
  none, because they belong to a family the queue did not describe.
  **Opened as W-75**: a multi-address `data-change-part` word
  substitution has its operative sentence in a SIBLING node, so the
  structured lane mints one REPLACE per listed address using the
  change node's own text — the amendment's address list — as the
  payload. **20 landed content-destroying writes across 2 base
  laws**, and only 15 are visible: plan- og bygningsloven's 7 sit in
  a `blocked_contingent` law that is not a scan candidate and
  produce no divergence row at all. That law is in the hazard census
  above at [73, 2], which is the census doing the job it was pinned
  for on its first day.

- **2026-08-11 (W-64 applied)** — **The `defaultP` heading stops
  being a payload boundary, and 106 leads a shipped production had
  always accepted finally get the text they announce.**
  (`81d318af2`, artifacts `.tmp/w64/`.) Lovdata marks a new
  section's heading with the same class it marks amendment leads
  with, so the payload cursor stopped ON the heading and collected
  nothing; the lead then refused for having no payload and the
  section body was stranded. Probed at the DOM nodes the walk reads,
  not at a text-plane rendering: `no/lovtid/2003-12-19-129` repeats
  the shape four times across three parts.
  **The discriminator is refusing by construction and measured, not
  argued.** Of the 569 corpus pairs behind a `lyde:` lead, the 21
  whose successor really is a lead are each excluded three times
  over, so the failure mode that would have silently deleted an
  operation cannot reach a single one of them; only the first node
  after a lead is ever tested, so a run of `defaultP` nodes can never
  be swallowed wholesale. **Ops 27,100 → 27,206 with zero lost, zero
  re-addressed, zero changed kind** on an identity diff keyed on
  content rather than `op_id`. Refusals fall 224 with none
  introduced, every one attributed: 106 leads that now land (with
  their paired `payload_unresolved`), plus 12 statutory body
  paragraphs that had been re-read as leads and tripped the
  operative-verb heuristic on the word `blir`.
  **The blast is where the honesty is.** All 45 moved base acts were
  replayed on both sides and flattened to address → text: **not one
  address lost non-empty text**. That is the check the change owed,
  because four of the six laws that move do so through a heading-only
  REPLACE — an op shape that would have truncated its section if the
  payload had been read as a whole-section replacement. The witness
  closes exactly as predicted: `no/lov/2001-06-15-75` 15 → 9, all six
  `section:37a/subsection:1-6` rows CLOSED and **zero rows opened**
  anywhere in the scan, so the landed ledd match the consolidation
  rather than trading one row type for another. Candidates hold at
  76, scoreboard at 29/47/0, totals 1,510 → 1,504 with the ceiling
  untouched at 1,011, partition buckets unmoved. **Only 2 of the 45
  moved base acts are scan candidates at all**, so 104 of the 106 new
  ops are invisible to the scoreboard — real corpus repair that the
  headline numbers cannot show, recorded here rather than inflated.
  The occupied-destination census re-ran over all 783 base acts and
  is unchanged element for element (10 firings, `wrong == []`), and
  W-63's insert-occupied refusal cell stays at zero. Left to W-65:
  the 185 chapter-level inserts whose body is a run of `defaultP`
  sections, and the 121 heading leads outside the shipped
  `§ X overskriften` surface — both grammar, not boundary.

- **2026-08-11 (W-67 + W-74 applied together)** — **The two-token
  widening lands, with the destruction it caused repaired at the
  lowering rather than guarded against in the recovery.**
  (`cf751dd2b`, artifacts `.tmp/w74/`.) W-67 was blocked for a day
  on one adjudicated `removal_wrong`: its textually correct 2017
  renumber (husbankloven § 10 → § 13) landed on a § 13 that no
  applied op had vacated, and destroyed "Ikraftsetjing o.a". W-73
  made the 2012 act commence and did not help, because commencing an
  act is not applying its ops. W-74 is the op — a SECTION-level
  repeal-then-shift run-on (`§§ 10, 11 og 12 blir oppheva. Noverande
  § 13 blir ny § 10.`), the section-level analogue of a ledd-level
  production that has shipped since W-61, read as ONE combined
  pattern rather than by splitting sentences. **The restriction that
  makes it landable is a hard conjunct, not a heuristic: the shift's
  destination must be a label the SAME lead repeals.** The
  production is then structurally incapable of writing into occupied
  law — the only slot it writes into is one it has already emitted a
  REPEAL for, at a lower sequence in the same group. 10 leads
  corpus-wide, **7 accept and 3 refuse**; the 3 are all
  `no/lovtid/2015-04-10-17` cross-chapter shifts whose destination
  the lead does not vacate, and they keep their refusal receipt.
  **Parse plane, fully attributed.** Refusals 9,454 → **9,383,
  exactly −71 and nothing else**, 0 introduced: −64 whose withdrawn
  set EQUALS W-67's frozen target set element for element at this
  later base, −7 the W-74 leads named above. Ops 27,018 → **27,100**
  (+64 renumbers, +11 repeals, +7 renumbers), **0 semantically lost,
  0 rebound**; the only other movement is 11 REPLACE → INSERT
  promotions, every one attributed to a W-67 target lead, which is
  `_promote_no_replace_with_following_renumber_insert` doing its
  documented job.
  **The stop condition is CLEARED, and by the mechanism the item
  predicted.** Corpus-wide `(RENUMBER, dest_occupied)` firings
  8 → **10**, swept over all 782 laws rather than the tripwire's
  seven. **The husbankloven firing VANISHES** — §§ 10–12 are
  repealed and § 13 → § 10 applied in 2012, so the 2017 renumber
  lands on a FREE destination and there is nothing to recover. W-54's
  survival test now passes on it: § 13 "Ikraftsetjing o.a" is in the
  replay at `section:13/subsection:1` and `:2`, matches the
  consolidation, and husbankloven's 13 sections align with the
  consolidation one for one. Its divergences are **2 → 2,
  byte-identical rows** — W-67's three `section:13/subsection:1..3`
  MISMATCH rows never open. The two firings that DO appear are
  W-67's other two, both re-adjudicated `removal_correct` on their
  own evidence: verdipapirhandelloven § 4-3 → 4-2 (the occupant is
  back at § 4-2 in the replay and matches the consolidation;
  divergences unmoved at 1,564) and merverdiavgiftsloven § 7-9 → 7-8
  (the occupant is the § 7-8 the SAME act repeals, absent from the
  consolidation; 256 → **254**). **`removal_wrong` is empty
  corpus-wide.**
  **Blast (782 laws, W-52 discipline).** 762 byte-identical; 20
  move. **7 are inside the 49-law expected-change set; the 13
  outside it are exactly W-67's 13, and their residue is 0** —
  withdrawn refusal receipts belonging to CO-AMENDED base acts
  (adjudications are collected per INSTRUMENT and replay attaches
  the whole list to every law that instrument amends) plus `op_id`
  ordinal churn, and normalising both away leaves the two sides
  equal on every one. **W-74 adds no outside-set mover at all.**
  Four laws' text moves. Divergence rows: **11 CLOSED, 0 OPENED**,
  no law worsened anywhere — `2010-06-04-21` 3 → 1 (both
  `OPS_MISSING` rows, W-67's designed payoff, on its own witness
  `Gjeldende § 10-10 blir ny § 10-13.`), `2005-06-10-44` 612 → 607
  (W-74's own accepted lead, § 1-2/§ 1-7/§ 1-8), merverdiavgiftsloven
  256 → 254.
  **Scan.** The first landing in this series that moves the
  scoreboard by CLOSING rows instead of admitting laws. Candidates
  **76, unmoved element for element**; scoreboard **29/47/0
  unmoved**; totals 1,512 → **1,510**, ceiling **1,011 unmoved for
  the ninth landing running**, unexplained 501 → **499**. Exactly
  ONE candidate row moves and the other 75 are byte-identical.
  Partition: `no/lov/2010-06-04-21` moves `replay_defect` →
  `untouched_drift` (23 → 22, 19 → 20) — with no `OPS_MISSING` row
  left it is not a replay defect any more, the W-23 predicate doing
  what it was built for.
  **Pins moved:** ops 27,018 → 27,100; entries 2,560 → 2,561;
  bindings 6,476 → **6,477** (one new (act, law) pair,
  `2004-09-24-72` → plan- og bygningsloven 1985, its only operative
  lead "Nåværende § 16 blir § 16-1."); declared-target
  gap 956 → 955 receipts and 2,524 → 2,523 pairs, the W-34/W-35
  conservation holding at 1 = 1; `instrument_authorized` 976 → 977 in
  all THREE places it is pinned — the route-count assertion, its
  non-staged sub-count (963 → **964**, the new act measured `plain`
  so the staged 13 do not move), and the `status_counts()` histogram.
  Two of the three were caught by the ladder rather than by the
  re-derivation, one per run; the third round re-derived the whole
  commencement pin family in one build (`.tmp/w74/s20`) and swept the
  three test files for every superseded literal, which is the step
  that should have come first. **Decert exposure is structurally
  zero, and measured so rather than argued: NO pre-existing entry's
  `base_ids` changes at all, and no entry's `effective_status`
  changes**, so the histogram's +1 is exactly conserving — a new
  entry, not a re-status. The only per-entry movement is `n_ops` on 49 entries
  (the +82 ops) plus the one new entry with its one binding; `instrument_authorized` 976 → 977
  and the widened whole-act route 435 → **436** in all four places
  it is pinned; scan totals 1,512/1,011/501 → **1,510/1,011/499**.
  `contingent` 534, the shipped route's 541 grants, and the part
  (31), multi-part (2) and named-part-list (10) grant SETS are
  unmoved element for element, as are readers (1,127), widened scope
  (1,115) and shipped scope (607). `_NO_OCCUPIED_DESTINATION_LAWS`
  gains the two proven `removal_correct` laws and husbankloven is
  deliberately absent (a law with no firing has no row); the two
  `2015-04-10-17` verdict rows are re-keyed `:27`/`:106` →
  `:30`/`:109`, pure per-document ordinal churn from W-74's three ops
  ahead of them in the same instrument. The W-58 tripwire row
  `no/lovtid/2024-12-20-87:2` stays removed, and `wrong == []` now
  holds over a table of 10.

- **2026-08-11 (W-73 applied)** — **Husbankloven's base-completeness
  gap was a commencement-instrument PARSE gap, it is repaired, and
  W-67 is still blocked — by a second gap the repair exposed.**
  (`ff202148c`, artifacts `.tmp/w73/`.) `no/forskrift/2012-08-24-826`
  commenced bustøttelova on 2013-01-01 and says so in one sentence —
  "Lov om bustøtte skal gjelde frå 1. januar 2013." — that no
  whole-act subject reader could take, because a NEW act is named by
  its TITLE and both shipped readers want either a definite act-word
  or `om endring`. Verified against the published consolidation
  before touching anything: husbankloven § 13 carries "ikr. 1 jan
  2013 iflg. res. 24 aug 2012 nr. 826", so the act genuinely
  commenced and applying it is sound. The fix is a third reader of
  W-53's existing text conjunct, carrying four conjuncts of its own
  (one cited act, one title subject, sentence-initial subject, and
  title agreement between the subject and the instrument's own
  declared title) plus the shared subdivision fence; OR-ed into
  `widened_whole_act_scope` and never into
  `whole_act_operative_text`, so W-47's route is provably untouched.
  Five acts move `contingent` → `instrument_authorized`; widened
  grants 430 → 435, `instrument_authorized` 971 → 976, entries/ops/
  bindings/coverage unmoved. Blast: **772 of 782 laws byte-identical,
  10 move, all 10 inside the expected-change set, 0 outside**;
  divergences over that set 1,687 → 1,680 with **7 rows closed and 0
  opened**, husbankloven 3 → 2, three laws moving
  `blocked_contingent` → `replayed` — which carries those three into
  the scan candidate set: candidates 73 → 76, scoreboard 29/44/0 →
  29/47/0, totals 1,485 → 1,512 with ceiling unmoved at 1,011 and
  unexplained rising by the same +27 (new coverage, nothing explained
  away), and all 73 pre-existing candidate rows byte-identical.
  Occupied-destination firings 8 → 8. **The W-67 unblock verification FAILED, cleanly and with
  evidence**: with both patches applied the husbankloven firing
  neither vanishes nor re-adjudicates, § 13 "Ikraftsetjing o.a" is
  still destroyed (6 → 5 divergences, corpus firings 11, none new),
  because commencing the act is not the same as applying its ops —
  the one op that vacates § 13 is a two-sentence repeal-then-shift
  run-on the grammar refuses. Opened as **W-74** with the sizing
  done: 10 leads corpus-wide, 7 accepted under a self-proving
  "destination must be a slot this lead vacates" restriction, and
  the ledd-level analogue already shipped. Rider: **163 of 782 base
  laws take destructive writes into a known-incomplete base** (3,737
  writes; 159 of them REMOVE content, over 64 laws) — carried to
  W-72.

- **2026-08-10 (W-67 measured, and BLOCKED on the regression it
  found)** — **The two-token widening closes exactly the 64
  refusals W-62 priced, provenance-clean and with the designed
  payoff landing (`no/lov/2010-06-04-21` 3 → 1 divergences, both
  `OPS_MISSING` rows closed) — and then destroys husbankloven
  § 13.** Product patch ARCHIVED (`.tmp/w67/w67.patch`, sha256 029fba7a…), NOT landed; records-only. Artifacts `.tmp/w67/`. Refusals
  9,454 → 9,390 (−64, withdrawn set EQUALS the frozen target set,
  0 stray, 0 introduced); ops 27,018 → 27,082, 0 semantically lost
  or rebound. Blast: 764 of 782 laws byte-identical; the 13 movers
  outside the expected-change set are fully attributed to
  co-amended refusal receipts plus `op_id` ordinal churn, residue
  0; candidate divergences 1,485 → 1,483, both closed rows
  UNEXPLAINED (474 → 472), scoreboard 29/44/0 held. Three laws'
  text moves, three new occupied-destination
  firings (corpus 8 → 11), adjudicated W-54-style as two
  `removal_correct` and one **`removal_wrong`**:
  `no/lovtid/2017-06-21-96:4` removes husbankloven's
  "Ikraftsetjing o.a", which is in the published consolidation and
  survives nowhere in the replay (3 → 6 divergences). Root cause is
  a base-completeness gap (`2012-08-24-64` scanned, not applied),
  not the widening — but the destruction is real, so the item does
  not land. Second finding, opened as W-72: the occupied-
  destination tripwire replays a hardcoded 7 of 782 laws, so all
  three new firings passed it green.

- **2026-08-10 (W-62 census: the lowering lane's yield is
  measured — ~10 rows, then receipt-honesty debt)** — **The
  refusal-family census clustered all 9,454 lowering refusals
  (13 families over 8,258 distinct leads) and measured the number
  that reframes the lane: only 0.97% touch a scorable law, and at
  most 10 of the 474 unexplained divergence rows are
  address-coincident with any refused lead — 6 of them one
  defect, the `defaultP` heading payload boundary.** Research
  only (artifacts `.tmp/w62/`). Eight items opened as priced:
  W-64 (heading boundary, the top yield), W-65 (address-path
  grammar, hard-dependent on W-64), W-66 (atomic set-relabel),
  W-67 (two-token widening, cheapest), W-68 (law-switch
  correctness), W-69 (RELOCATE, production-first), W-70
  (malformed-token tripwire), W-71 (operative-predicate hygiene).
  W-57 unfrozen and re-scoped into W-66+W-69 — its second
  witness exists (98 leads / 49 acts) but its premise was wrong:
  the load-bearing property is atomicity under overlapping
  source/destination sets, not range arity. Triage coverage
  stated honestly: 4 of 12 proposer groups returned; 8 families'
  classification unadjudicated with sizing standing; the agent
  found a chimeric-pair defect in its own sampling harness and
  discarded the affected findings. Heading/title replaces closed
  as scan-inert (zero candidate rows address a heading).

- **2026-08-10 (W-63 applied)** — **The gate's margin is pinned, and
  re-measuring W-60's two mutants moved both findings: `D2_m3`'s
  "zero divergences with false law" is a DEGENERATE zero (the tree
  invariant raises, `verify_no_against_current` returns before
  comparing, and the apply-plane failure MANUFACTURES `G1_closes`),
  and `D4_m3` is not false law at all (its mutation escaped the
  harness's supersede key, the correct parser op landed, and the
  replayed statute is byte-identical to the accepted control's).
  What survives is sharper: a divergence count is uninterpretable
  without `replay_status`, and two op streams can carry identical
  divergence evidence while differing only in the typed receipt.**
  (`6b3f789e7`)
  Five pins in `tests/test_no_gate_margin.py`, both mutants rebuilt
  as self-contained fixtures scored with the production comparator.
  **W-54's dormant `(INSERT, occupied direct child)` cell FLIPPED
  from overwrite to refusal** — 0 firings over all 782 base laws
  (non-strict census) against 194 firings / 73 laws for its declared
  θ sibling, which is untouched; the discriminator is whether the
  op's own address resolves. Now a blocking
  `no_replay_insert_occupied_direct_child_refused` with no write and
  a rejected op instead of a silent overwrite at an address the
  amendment never named. Blast: all 782 laws and all 73 candidates
  byte-identical (statute / adjudications / receipts / audits /
  filter partition / divergence rows), 0 `base_ids` movement,
  candidate divergence total 1485 = 1485.

- **2026-08-10 (W-61 applied)** — **`wrong == []`: no adjudicated
  recovery in the corpus destroys in-force law any more. The last
  `removal_wrong` row fell to a one-word grammar gap — the
  repeal-then-shift production hard-required `Nåværende` — not to
  the archive gap (W-58) or run-on boundary (W-60) previously
  diagnosed; both prior readings were text-plane evidence about a
  DOM corpus, and the recorded lesson is to probe the node the
  parser actually reads** (`d854e93fe`). Strictly additive
  widening, forced by measurement (an outright replacement
  regressed 14 leads): −24 refusals / 0 introduced, 23 of 24
  family leads convert, three laws repaired against the
  consolidation with zero rows opened, all 73 candidates
  byte-identical. +10 binding pairs, every one previously
  declared-and-receipted-unbound (exact conservation); n_ops
  27,018; one new commencement grant (541, P1 zero-early holds);
  would-be ceiling 61 → 60. W-58 closed; W-62's triage census
  seeded with the 9,454-refusal remainder and the finding that
  the unstructured grammar has NO ledd-shift family — priced
  together with multi-sentence segmentation or not at all.

- **2026-08-10 (W-60 spike: the LLM lane measured — the bottleneck
  is lowering, not translation)** — **The proposer–verifier spike
  ran 15 sites at 47% full-gate conversion with zero control
  false-accepts on both arms, and its sharpest findings were not
  about the proposer at all: W-58's "archive gap" dissolved (the
  repeal is in our archive, refused by a run-on part-boundary
  lowering defect → W-61), and the mutant control proved the
  divergence conjuncts alone would admit false law at zero
  divergences — the typed apply-plane conjuncts carry the gate's
  entire margin (→ W-63, with W-54's dormant insert cell observed
  live a second time).** Research only (brief + artifacts
  `.tmp/w60/`). Verdict ESCALATE, redirected: no evolver (7 of 8
  failures live outside the proposal search space); instead the
  proposer becomes a triage instrument over the refusal
  populations (→ W-62). Shallow anchoring closed (tautological;
  13 laws / 14 forward ops); archive gaps not material (~9 rows
  outside the known sparse ceiling); W-59 re-scoped to 2
  reachable blocks (7 of 9 seed laws unreplayable, 1 seed error
  caught by the proposer); W-57 confirmed to need a new op kind,
  stays frozen. Queue restructure signed off.

- **2026-08-10 (W-55 applied)** — **The CTSF gate is green again,
  and the red was a false conviction: the corpus refresh of
  2026-07-31 put the live oracle AHEAD of the frozen anchor
  window, and the gate billed a correct replay for correctly
  withholding a future-effective repeal** (`ad03ece3a`). Proven
  by control (freeze-commit code convicts identically on today's
  archive) and by a byte-exact horizon replay (0 divergences
  act-wide at 2026-06-19). Fixed in the CTSF engine only: a
  per-section temporal rail, byte-exact gated off replay's own
  future-skip receipts, closes the fires-on-time-alone lane.
  Baseline re-frozen 1 → 3 residuals with billable 1 → 0, every
  row attributed — including one residual RESOLVED by W-18's
  erratum lowering. Main CI returns to all-green-or-known.

- **2026-08-09 (W-56 applied)** — **Tvisteloven's vitneforsikring
  is restored: the dropped renumber leg was Lovdata's own
  `data-move-part` under-declaring the shift, and the lowering now
  completes an incomplete attribute from the block's own lead
  sentence — pure templating off the declared legs, add-only
  polarity, 4 legs added corpus-wide, occupied-destination
  firings 10 → 9, and the W-54 verdict table finally pinned**
  (`e2589b292`). Blast radius: 5 of 782 laws moved, exactly one
  statute text changed (the intended repair; tvisteloven 399→398
  with zero rows opened); all 73 candidates byte-identical,
  totals and scoreboard unchanged, zero binding movement, zero
  new firings. The skattebetalingsloven row is pinned
  `removal_wrong` as W-58's designed handoff tripwire. The
  anchor-less and malformed-token remainders opened as W-59.

- **2026-08-09 (W-54 audit: the occupied-destination recovery is
  right 8 of 10 times, and the 2 misses destroy live law)** —
  **The `(RENUMBER, dest_occupied)` policy audit adjudicated all
  10 corpus firings from the amending-act sources: 6 number-reuse
  (removal is what the statute commands), 2 stale-tree (the W-52
  mechanism), and 2 incomplete ledd-shift cascades where the
  occupant is in force and the recovery deletes it — tvisteloven's
  vitneforsikring (a dropped renumber leg in the lowering) and
  skattebetalingsloven's regulation power (a missing amender in
  the archive).** Research only (artifacts `.tmp/w54/`). All four
  alternative policies measured end-to-end: production `remove` is
  the convergent choice (best aggregate, only policy holding both
  scan-visible laws at 0 divergences) — kept, with the verdict
  table deliberately UNPINNED until a fix lands. The hazardous
  subclass is exactly the same-parent shift-down cascade; the
  dormant insert-overwrite cell shares its polarity and fired
  live under the `refuse` counterfactual. W-56 (repair the
  cascade class), W-57 (range-renumber sizing), W-58 (the archive
  gap) opened.

- **2026-08-09 (W-53 applied)** — **The widened whole-act route
  lands: 430 read-text act-level grants, candidates 65 → 73, scan
  25/40/0 → 29/44/0 with the error column never opening, and the
  part lane deliberately retired to 70 grants — the biggest scan
  growth of the programme, with P1 zero-early over all 1,040 grants
  as a gate property** (`83cdbde72`). The +2 over W-50's sizing is
  W-51's sibling sharpening, proven by counterfactual. All 65
  pre-existing rows byte-identical, `base_ids` changed on 0 of
  2,559 entries — decert exposure zero, structurally. Absorption:
  344/346 date-identical, 2 later-conservative, 0 earlier. Two
  deliberate additions: the widened route declines shipped-PROPOSED
  acts (no silent cross-route date resolution), and the whole-act
  refusal receipt is withdrawn where the widened route grants
  (1,156 → 882 — the lane's first receipt retraction). New pinned
  asymmetry: W-49's named-part-list route is mutually exclusive
  with the widened route by construction and loses nothing.
  Totals 1,485 = 1,011 + 474, ceiling untouched.

- **2026-08-09 (W-52 applied)** — **The replay engine's one receipt
  hole is closed: named-recovery collateral is now declared on
  write receipts — klimakvoteloven and `2005-06-10-44` replay
  clean, the census found and closed 7 silent undeclared removals
  across 6 laws, and W-53's error column never has to open**
  (`03cea7ec5`). The observed-write audit had fired TRUE against
  an under-declared RENUMBER receipt (footprint from the (from, to)
  legs only, while the `(RENUMBER, dest_occupied)` recovery also
  destroyed the occupant); its detection was partial and accidental
  — only cross-container occupants left an unrelated observed path.
  All 10 corpus firings of the recovery are now declared and judged
  by the audit; blast radius 780/782 byte-identical, 0 of 65
  candidates moved, scan unchanged 25/40/0 and 1,447 = 1,011 + 436.
  Recovery-policy audit opened as W-54; pre-existing ctsf-gate
  baseline drift recorded as W-55.

- **2026-08-09 (W-51 applied)** — **The whole-act route's act-level
  P1 breach is repaired: a sharpened commencement-sibling predicate
  (two-witness, exclude-only-on-proof), a carve-out tail fence, and
  the act-level no-later-instrument refutation — two proven-breach
  demotions, zero candidate movement, and P1 zero-early over all
  540 whole-act grants as a gate property** (`7a1ffa41e`). The
  hjemmel artefacts are gone at the source (basedOn alone is not a
  sibling signal; 234 of 2,365 instruments proven
  forskrift-commencements), the regex and W-47's reader now agree
  on the carve-out sentence, and `instrument_authorized` makes its
  first backwards move 542 → 540 — both losses 12-15-month early
  applications. W-53 must re-measure on this base. The lane's one
  remaining asymmetry: W-39's route has no refutation conjunct.

- **2026-08-09 (W-50 sizing: the widening passes its gates but the
  shipped route is already unsound)** — **The whole-act widening is
  a 518-instrument / 449-act surface (7× the estimate) worth +8
  candidates with zero decert exposure — and the sizing found the
  SHIPPED whole-act route in act-level P1 breach today (8 EARLY / 5
  acts, incl. a med-unntak-av carve-out swallowed by the regex
  tail) plus the programme's first `error` verdict waiting behind
  the coverage (klimakvoteloven's renumber/observed-write replay
  defect).** Research only (artifacts `.tmp/w50/`). Five variants
  priced end-to-end; the bounded `route5` passes all four gate
  criteria (0 new EARLY, 0 conflicts, 0 decerts — monotonicity
  argument — 344/346 absorbed part grants date-identical) but
  landing it would bank on a baseline in breach and absorb an
  engine defect, so it waits. W-51 (repair the shipped route's
  soundness), W-52 (triage the replay defect), W-53 (land route5
  after both) opened.

- **2026-08-08 (W-49 applied)** — **The named-part-list route closes
  the commencement lane's readable remainder: 33 grants over 10
  acts, zero scan movement, and per-part refutation semantics proven
  on the corpus** (`f241d8975`). A total-refusing tokenizer (no
  grammar regex) reads `del I og III` / `del I–V` lists; all 11
  W-47 header/text disagreements refuse with 0 leaks. The shipped
  two-witness refutation (later instruments provably about OTHER
  parts, structurally AND textually) is the semantics W-47's
  act-global conjunct could not express — and the textual-only
  variant was measured to fire P1 on one pair, the near-miss that
  justifies the pair of witnesses. P1 zero-early over all 416
  shipped grants. Inert grants 29 → 31 (the one pin edit). What
  remains in the multi-part population is `§`-carrying slice shapes
  (W-41's zero-priced surface, fenced by W-48).

- **2026-08-08 (W-47 applied)** — **The multi-part commencement route
  opens: 260 grants over 70 acts, seven candidate entrants (two
  arriving consistent — a series first), and the biggest scan growth
  of the programme, 58 → 65** (`47e49f0ae`). The Endrer header is a
  faithful part→law map (168/168) but NOT an instrument-scope
  statement (11 proven counterexamples), so the route grants only
  when the instrument's own text commences the WHOLE act — dating
  the header's parts is then a strict subset claim, guarded G1∧G2
  (no subdivision named ∧ act-level clause subject; 0 of 11
  disagreements leak; corruption-immune by construction). P1 fired
  at 2 early on a revoked-and-reissued commencement and was closed
  by promoting the probe to the `ACT_HAS_NO_LATER_INSTRUMENT`
  conjunct (cost 2 grants, 0 candidates); shipped P1 over 383
  grants: 0 early. Scan 25/40/0, totals 1,447 = 1,011 + 436 (+239
  all-entrant, conservation exact, 0 decerts). W-49 opened
  (agreeing part-lists, ~13 pairs) and W-50 opened (size the
  `_WHOLE_ACT_RE` widening — 72 whole-act commencements currently
  routed as parts).

- **2026-08-08 (W-41 design pass: the slice surface is worth zero,
  and the lane's real lever is elsewhere)** — **Every sound model of
  partial-part commencement slices yields 0 candidates, 0
  divergences; the unsound upper bound buys exactly one law. No
  code shipped.** Research only (artifacts `.tmp/w41/`). The pass
  corrected the surface count (121 pairs, not 109), found W-39's
  `_COMMENCED_SECTION_RE` swallowing Norwegian ordinals (98/244
  compared pairs corrupted — conservatively: 0 corrupted rows
  authorize and W-39's landed result is untainted), and proved by
  probe that the naive reader fix ALONE fires the 0-early soundness
  assertion (smittevernloven, 13-day-early §8-1). 88% of slices
  qualify below section granularity, where ops have no finer
  evidence — the model's address plane does not exist. Lane-ceiling
  census: `endrer_spans_multiple_parts` is worth +17 candidates,
  17× this surface → W-47 opened; the interlocking hygiene bundle
  (reader fix + ledd conjunct + staged-part model + negative/
  exception refusals, never separately) → W-48 opened.

- **2026-08-08 (W-46 applied)** — **The frontier dashboard now shows
  the scan's reach, not just its results: `no-frontier` prints the
  no-consolidation census beside the partition it is a sibling of**
  (`36c7af021`). Presentation only, 39 lines: the census is the
  same object the partition call already computed, so the two cannot
  disagree; both universes (763 stored / 645 operative) printed so
  the census total cannot be read against the wrong denominator. No
  stop conditions, no scan or pin movement.

- **2026-08-08 (W-45 applied)** — **The scan's blind spot becomes a
  live receipt: 2,642 laws with a replayable original and no stored
  consolidation are censused at runtime, families and repeal
  evidence recomputed from the archive, with a 13-id tripwire that
  fires if a future corpus loses an in-force law** (`ef2a3d9c9`).
  `build_no_no_consolidation_report` + `lawvm no-no-consolidation`
  (mirror of `no-missing-base`), six inventory counters, and an
  `unverifiable` sibling beside the partition buckets. Runtime
  reconciliation with the W-44 probe 14/14. STOP-1 fired and
  resolved: the census universe is stored artifacts (763), not the
  operative-content-filtered `current_law_ids` (645) — the 110-law
  delta is amending acts consolidated to bare change instructions,
  and both universes are now reported side by side. Zero scan
  movement. W-46 opened (surface the census in `no-frontier`, XS).

- **2026-08-08 (W-44 probe: no consolidation ≠ missing data)** —
  **The 2,642 laws with a replayable original and no stored
  consolidation are amending acts (2,514), expired temporaries (40),
  self-repealing wage-board acts (25), and 63 substantive acts that
  are ALL repealed, spent, absorbed, or never commenced — zero
  demonstrated acquisition gaps.** Research only (artifacts
  `.tmp/w44/`). Snapshot completeness proven locally via the 2025+
  recency test (24 residual absences, all adjudicated) and Lovdata's
  structural repeal manifests (`Følgjande lover blir oppheva:`).
  The W-43 seed `2005-06-03-33` is the repealed 2005
  diskrimineringsloven. The family is structurally invisible to the
  scan (absent from the inventory universe, no denominator); its
  counterfactual would-be-candidate ceiling is +55. W-45 opened:
  typed receipt (report + inventory counters + `unverifiable`
  partition sibling with the `substantive_unexplained == 13`
  tripwire), size S; optional XS live-probe for the 29
  would-be-candidate amending acts (~1 predicted hit).

- **2026-08-08 (W-43 applied)** — **The top-level body walk is merged:
  mixed chapter+article documents keep both kinds in source order,
  103 dropped consolidation sections and 48 replay-base sections are
  recovered, and `2012-12-14-81` closes its last 4 rows — wholly
  ceiling at 93/93** (`609fd7ce8`). The W-42-diagnosed `if not
  body_children:` fallback replaced by one order-preserving dispatch
  pass mirroring `_parse_container`; recovered `§§` land BEFORE the
  annex chapter as in the source, pinned by an `S…A` mirror test that
  a "run both walks" variant would fail. Every probe prediction
  reproduced on first measurement (16/103/0 current lane, 4/48/0
  replay lane, scan −4 exactly); totals 1,212 → 1,208, unexplained
  201 → 197, ceiling/verdicts/index pins byte-identical. W-44 opened:
  census of laws with a replayable original but no stored
  consolidation (found via `2005-06-03-33`), invisible to verify by
  construction.

- **2026-08-08 (W-42 probe: the annex-only consolidation is a parse
  defect)** — **`2012-12-14-81`'s missing §§ 1-4 are in the source;
  `parse_no_statute` drops top-level articles whenever a document is
  both chapter- and article-structured — 16 consolidations lose 103
  sections, the replay lane loses 48 more across 4 laws.** Research
  only (artifacts `.tmp/w42/`). The top-level article walk is an
  `if not body_children:` fallback to the chapter walk
  (`grafter.py:944`) while the nested `_parse_container` interleaves
  correctly. Counterfactual full-corpus diff: 103 gained / 0 lost /
  all strict supersets; counterfactual scan 97 → 93 unexplained
  (exactly the W-42 rows); candidate set provably unmovable by the
  fix (candidacy never calls this parser). Sized fix opened as W-43
  (order-preserving merged walk, ~10 lines).

- **2026-08-08 (W-40 applied)** — **Lovdata's second annex encoding is
  typed: the compound sub-chapter joins the W-17 ceiling and the
  unexplained count drops 294 → 201** (`71d916f1e`). The W-39 entrant
  `2012-12-14-81` carries regulation (EU) nr. 492/2011 as
  `chapter:1`/`chapter:1-1` with unprefixed article labels — no token
  chapter, so both halves of the W-17 matcher miss all 93 rows. New
  sibling matcher + rule id
  `ceiling_annexed_instrument_nested_address`, bound to the measured
  shape with the W-17 negative-control discipline; censused over all
  1,212 divergence addresses: 93 hits in 1 law, 0 elsewhere, 0
  overlap, GDPR compound sub-chapters disjoint structurally
  (opposite top-chapter requirements). The nested rule deliberately
  does not feed the counterpart `witnessed` map. Ceiling 918 → 1,011
  under separate rule counts; the law's partition bucket moves
  `source_sparse` → `annex_ceiling`, closing W-39's recorded
  contradiction; ceiling-share floor 0.97 → 0.95 (descriptive only).
  Zero verdict, row, or index movement. The 4 residual rows (the
  act's own §§ 1-4, absent from the consolidation) → W-42.

- **2026-08-07 (W-39 applied)** — **The commencement lane opens: the
  collective re-enactment lead lowers as a declared end state, part
  instruments authorize per (act, law), vaktvirksomhetsloven goes
  81 → 0 consistent, and the candidate set grows for the first time**
  (`36cc59eac`). Half (i): renumbers-before-payloads ordering (the
  witness renumbers sections its payloads overwrite — the chosen
  order reproduces the published consolidation exactly) under
  all-or-nothing part guards; 2 of the 4 family acts lower, 1 refused
  with a typed receipt at measured-zero cost, 1 out of scope. Half
  (ii): 123 part authorizations from 551 Delvis/Delt instruments via
  exact Endrer→part matching PLUS the beyond-the-brief
  `whole_part_scope` conjunct (109 narrower slices refused → W-41);
  soundness probe 0 early-application risks; deliberately no
  act-level status invention (`part_scoped_effective_dates` per
  binding). Inseparability proven in both directions. Scan signed
  off: 56 → 58 candidates, 23/35, unexplained 271 → 294 as honest
  new coverage (93 of it annex-shaped rows the W-17 classifier
  misses at the entrant's prefix → W-40). Zero ops lost, zero
  rebinds, declared-target conservation exact.

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
