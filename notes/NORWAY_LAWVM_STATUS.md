# Norway Frontend Status And Source Regime

> **Status (2026-07-10):** Current. Normative for the Norway frontend's source
> authority, replay claim, benchmark interpretation, and historical-source
> boundary. Implementation details remain subordinate to the repository-wide
> invariants in `AGENTS.md` and the shared contracts indexed by `SPEC_INDEX.md`.

## 1. Current Claim

Norway is an experimental replay-first frontend for statutes published in the
public Norsk Lovtidend Avdeling I data from 2001 onward. For a law whose original
promulgated text, affecting instruments, and effective dates are available, the
frontend can compile Lovdata's structured amendment markup into typed operations,
replay them over the original text, and compare the result with Lovdata's current
consolidated rendering.

The claim is deliberately bounded:

```text
archived original LTI bytes
+ archived affecting-instrument bytes
+ execution-authorized operations
+ resolved temporal evidence
-> source-faithful replay candidate

source-faithful replay candidate
<-> current Lovdata consolidation
-> agreement evidence or typed residuals
```

The current Lovdata consolidation is a high-value editorial comparison surface.
It is not replay authority and does not silently repair replay. A difference can
be a LawVM defect, an incomplete source history, a temporal mismatch, a
manual-compilation frontier, or an oracle/editorial issue.

## 2. Source Hierarchy

The frontend keeps these source roles distinct.

### 2.1 Original and amending Norsk Lovtidend artifacts

The open Lovdata Avdeling I archives are the primary post-2001 source lane. They
contain original promulgated laws, amending laws, central regulations,
commencement decisions, delegation decisions, and other announcements as
HTML-shaped XML. LawVM currently ingests law members and preserves exact bytes in
Farchive.

Canonical locators are:

```text
no://lov/<date-number>/original.lti.xml
no://lovtid/<date-number>/amendment.xml
```

The public inventory and downloads are exposed through:

```text
https://api.lovdata.no/v1/publicData/list
https://api.lovdata.no/v1/publicData/get/<filename>
```

The open dataset is licensed under NLOD 2.0. Acquisition must use the public bulk
packages rather than systematic extraction from Lovdata's ordinary website.

### 2.2 Current consolidated laws

`gjeldende-lover.tar.bz2` provides the current editorial consolidation and is
stored at:

```text
no://lov/<date-number>/current.xml
```

This lane is an oracle/witness plane only. It may identify replay defects, but
agreement does not prove source completeness and disagreement does not authorize
a mutation. Lovdata can make editorial corrections that do not correspond to an
amending act. Confirmed cases remain exact-text-pinned oracle findings, never
generic permission to prefer the consolidation.

### 2.3 Commencement evidence

Lovdata `dateInForce` metadata supplies the current act-level temporal surface.
`Offisielt fra statsråd` and manually curated commencement evidence are sidecars.
They can support a typed override after review; they do not directly authorize
replay merely because they were acquired or matched by title.

The public Avdeling I packages also contain `sf-*.xml` forskrift instruments.
LawVM now preserves those exact bytes under stable `no://forskrift/...` locators
and runs one typed, non-authorizing commencement parser over them. Structured
`basedOn` references may bind a candidate to an amending law, but every resulting
candidate explicitly carries `replay_authorized=False`. Whole-act scope candidates
and blocked partial/ambiguous candidates remain evidence until a separate typed
execution-authorization validator is implemented.

The current model cannot represent provision-level staged commencement. A
contingent, partial, missing, or unknown commencement that cannot be proved is a
blocking temporal residual, not permission to choose a date.

### 2.4 Corrections

Official corrections, withdrawn announcements, and renewed sanctions require a
distinct corrigendum lane. The Norway frontend does not yet acquire or execute
that lane. Compare-only knowledge of a Lovdata editorial correction is evidence,
not a substitute for an official correction event.

### 2.5 Historical scans and reconstructed sources

The frontend has no admitted pre-2001 scan/OCR source lane. Norsk Lovtidend scans,
annual registers, historical editions of *Norges Lover*, and other material from
Nasjonalbiblioteket are candidate source witnesses only until a governed
reconstruction pipeline emits content-addressed source claims with page/region
anchors, validation results, uncertainty, and an explicit authority class.

OCR, vision models, historical consolidations, and old Lovdata media may propose
or corroborate a reconstruction. They may not silently become the original legal
text or replay authority. Reconstructed-source benchmarks must remain separate
from deterministic source-only replay.

Acquisition research for this lane is kept in `NORWAY_PRE2001_SOURCES.md`
(2026-08-18 memo): no released pre-2001 Lovdata dataset exists, so the
born-digital corroboration channel is a negotiated agreement, never scraping
(HR-2019-1725-A, åvl. § 24); the source of record is the Nasjonalbiblioteket
facsimile run (IIIF + ALTO, gazette items flagged public domain), with UiO
Juridisk bibliotek rescans for missing hefter.

### 2.6 Authority boundary by era

Norsk Lovtidend is governed by lov 19. juni 1969 nr. 53 (successor to the 1876
law; first volume 1877). § 3 runs the default commencement clock from the
publication day of the *issue*. The statute was never amended for the
electronic edition; the switch is administrative practice, not a dated
amendment, and provenance must record it as such:

| Era | Authoritative artifact | Note |
| --- | --- | --- |
| 1877–2000 | The printed hefte only | § 3 clock runs against the printed issue's publication date; Lovdata CD-ROM/Pro texts are commercial derivatives, corroboration only |
| 2001–2016 (print volumes through 2017) | The electronic edition, by ministry practice under the 1969 law | Print still produced; "kunngjøringsdato" of the electronic version is decisive |
| 2018– | The electronic edition only | Print ceased |

Era flags the print-era parser must carry:

- **1974 avdeling split.** From 1974, Avd. I = laws and central forskrifter
  (incl. Svalbard/biland/university), Avd. II = regional/local. Pre-1974
  volumes allocate content differently than the post-2001 model assumes and
  need direct inspection before segmentation rules are written.
- **2001 format change.** A5 through the 2000 volume, A4 from 2001; running
  heads, chronological tables of contents and per-item date+number headers
  are era-specific.
- **Print-era corrections.** Rettelser appear in the next printed issue and in
  a consolidated "Oversikt over rettelser" at the back of each hefte/volume,
  cross-referenced by issue + page (not URN). Lovdata's online overview is
  complete only from 2017; 2001–2016 sit at the back of the electronic
  hefter; earlier years only in the scans.
- **Register as manifest.** Each annual volume carries a chronological and a
  subject register per avdeling; the chronological register enumerates every
  kunngjøring and is the print-era completeness oracle (the analogue of
  `gjeldende-lover` for the consolidation lane).

## 3. Implemented Pipeline

The current production path is:

```text
local public tarballs
-> Norway Farchive ingestion
-> affecting-act index
-> typed Lovtidend commencement-candidate inventory (non-authorizing)
-> structured/unstructured change extraction
-> typed LegalOperation stream
-> conserved apply seam + adjudications + write receipts
-> replayed IR statute
-> compare-only normalization
-> current-consolidation consistency residuals
-> unified bench / attribution ledger
```

The source XML often provides structured targets through attributes such as
`data-change-part`, `data-add-new-part`, `data-remove-part`,
`data-repeal-part`, and `data-move-part`. Source-local parsing and recovery remain
Norway frontend responsibilities. Core owns canonical operation semantics, tree
mutation, receipts, mutation-boundary accounting, lineage, and timelines.

Production replay conserves skipped and rejected work through typed receipts and
adjudications. Renumbering emits migration evidence. Source anchors are additive
provenance and must not change any apply-authoritative field.

The commencement-instrument inventory is total in the accounting sense. On the
2026-07-11 local public 2001-2026 package snapshot, 35,955 forskrift artifacts
partitioned into 33,590 benign non-commencement instruments, 608 structurally
complete whole-law candidates, and 1,757 blocking unresolved candidates. These
counts measure source classification, not replay authorization or national
commencement coverage.

## 4. Replay And Strictness

Ordinary replay currently permits named recovery rules for known source shapes,
including occupied insert, absent replace, and occupied renumber destinations.
These are declared in `norway/totalization_table.py`, emit adjudications, and are
strict-rejectable. They describe current implementation behavior, not general
Norwegian legal semantics.

Strict evaluation must block any recovery that lacks its required source witness,
execution authorization, migration record, or mutation-boundary proof. In
particular, ordinary recovery success must not be reported as literal source
execution. Same-effective-date incompatible operations remain ambiguous unless a
documented precedence rule resolves them.

The frontend still performs target completion and structural recovery too late in
some paths. New work should move those decisions into typed elaboration rather
than add replay-time interpretation.

## 5. Benchmark Contract And Baseline

Norway uses the unified benchmark contract. `SCORED` rows report exact per-section
structural divergence against the current consolidated rendering. The text-error
axis is not yet attempted. `SOURCE_UNAVAILABLE`, `NO_TRUTH`, and `ORACLE_STALE`
are non-scored outcomes; `CRASH` is reserved for unexpected execution failure.

The comparison is not a historical point-in-time oracle. Norway currently has one
current consolidated rendering, so a replay `as_of` is commensurable only when it
represents the same legal horizon. Historical `as_of` rows must not be interpreted
as authoritative PIT verification against the current text.

Baseline measured on 2026-07-10 from the public Lovdata packages listed that day,
using `data/norway/bench_corpus.csv`:

```text
18 corpus rows
15 scored
3 source-unavailable
8 exact
7 divergent
7.66% mean structural error over scored rows
0 crashes
```

The baseline is a regression and work-prioritization surface, not a national
accuracy claim. Two small-denominator statutes dominate the mean. Every positive
structural error must reconcile with typed residual buckets.

The source-unavailable rows include contingent commencement and sparse indexed
history. A large current-text difference supported by too few acquired amendments
is an acquisition ceiling, not a saturated replay failure.

## 6. Known Limits

The current claim does not include:

- complete histories for laws enacted before 2001;
- Avdeling II or local-regulation replay;
- provision-level or staged commencement;
- automatic execution authorization from official commencement instruments;
- official corrigendum execution;
- signed-PDF acquisition or signature verification;
- Nasjonalbiblioteket acquisition and scan reconstruction;
- a dated chain of Lovdata consolidated versions;
- aggregate text-similarity scoring;
- full production coverage by byte-span source anchors;
- timeline-primary Norway materialization equivalent to the reference frontend.

The free public archive contains many non-law members. Members outside the current
law mapper remain typed acquisition residuals. Their presence does not expand the
statutory replay claim.

## 7. Next Work

The ordered Norway programme is:

1. keep the public post-2001 archive reproducible and rerun the committed corpus;
2. make source anchors and mutation receipts live on the full production path;
3. tighten strict recovery and same-moment ambiguity blocking;
4. preserve amendment-source part/provision provenance, validate official
   whole-act commencement candidates, then model provision-level commencement;
5. add an official corrections/corrigendum lane;
6. make benchmark dates commensurable with the available oracle horizon;
7. pilot one pre-2001 Norsk Lovtidend window ([1997, 2000] Avd. I) through the
   governed dual-channel pipeline — NB facsimile + ALTO as source of record,
   negotiated Lovdata born-digital text as corroboration, payload landing only
   on byte-faithful agreement, certified-agreement rate per hefte as the
   go/no-go — after the annual-register completeness manifest is built;
8. admit reconstructed historical sources only after page-level verification and
   authority labeling;
9. expand the historical corpus by source family and decade, not by silent OCR
   accumulation.

## 8. Commands

```bash
uv run lawvm no-ingest --data-dir data/norway/public --db data/norway.farchive
uv run lawvm no-index --data-dir data/norway.farchive
uv run lawvm -j no replay no/lov/YYYY-MM-DD-N --as-of YYYY-MM-DD
uv run lawvm no-verify no/lov/YYYY-MM-DD-N --as-of YYYY-MM-DD
uv run lawvm bench -j no --corpus data/norway/bench_corpus.csv --label LABEL
uv run lawvm spec-ledger -j no --corpus-bench
```

Full archive-backed runs require untracked local source data. Committed fixtures
and corpus indexes must remain sufficient for source-absent contract tests.
