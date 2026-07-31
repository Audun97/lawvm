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
| **2026-07-10 (snapshot-commensurable)** | **11** | **9** | 0 |

The delta between the two rows is itself finding F-01: three laws
(`no/lov/2020-05-07-38`, `no/lov/2025-06-20-102`, `no/lov/2025-12-22-116`)
read as defective at the default date purely because an amendment took effect
between 2026-03-29 and the snapshot, and `no/lov/2022-03-11-9` showed 9
divergences instead of its real 1.

At the commensurable horizon, the 9 divergent laws carry 313 provision-level
divergences, of which **295 sit in the two known sparse-source laws**
(`no/lov/2006-06-30-50`: 212, `no/lov/2001-01-05-1`: 83). Outside those, the
whole corpus has **18 divergences across 7 laws**, classified below.

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

### F-02 — Sentence-level (punktum) unstructured leads not lowered — open (engine, top priority)

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

### F-04 — Statsforvalter renaming absent from the amendment index — open (acquisition/index)

`no/lov/2015-05-12-27` (forsvunne personar): 5 MISMATCHes are all
`Fylkesmannen`→`Statsforvaltaren` (the national 2021 renaming of the county
governor office). The index holds only one amendment for this law
(`no/lovtid/2020-12-18-149`), so the renaming act was never applied. Also one
OPS_MISSING: published §8(4) (death-abroad rule) has no corresponding op.

Action: locate the renaming act (and the §8(4) source) in the local archive;
if absent from the packages, record as acquisition ceiling; if present but
unindexed, index-coverage bug. Note: the renaming act, once found, likely
unblocks the same mismatch in many currently-blocked laws.

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

Conclusion: not a normalization problem. If it is worth solving at all, it needs
either footnote structure preserved at published-side extraction (so the marker
is typed rather than inlined) or a diff-time tolerance that is not a text rule.
Both are larger than a compare-lane batch. Left as recorded noise: 2 divergences
across the corpus, both in the commencement formula.

### F-06 — Footnote-anchor whitespace in published text — open (compare noise, batch 01)

"(forordning (EU) nr. 910/2014 **)**" vs replay "910/2014)"
(`no/lov/2018-06-15-44` §1(1)) — a space left behind by a stripped footnote
anchor. The same probe that killed F-05 measured this rule at **1 altered text
unit in 8,779**: exactly the known case, zero false positives, and the lane
already normalizes the opening-parenthesis mirror of it. Scoped as batch
`01-compare-noise-normalization`.

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

1. **W-1 (F-06):** strip the footnote-anchor space in the compare-only
   normalization (batch 01). F-05 was measured out of this item before any code
   was written — see its entry.
2. **W-2 (F-02):** add the punktum-level repeal (and sentence-move) lowering
   family with full receipts; rerun the scan and count how many laws it clears.
3. **W-3 (F-04):** hunt the statsforvalter renaming act in the archive;
   classify as index bug vs acquisition gap.
4. **W-4 (F-01):** make `no-verify-scan`'s default comparison date
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
