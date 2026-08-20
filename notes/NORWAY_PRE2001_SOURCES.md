# Pre-2001 Norsk Lovtidend: Source Authority And Acquisition (research memo)

> **Status (2026-08-18):** Distillation of an external deep-research report
> (claude.ai, commissioned by the user) on acquiring pre-2001 Norsk Lovtidend
> from legally authoritative sources, for the W-80 era-expansion plan and
> item 87 (W-81). Claims below are the report's, kept with its confidence;
> items marked VERIFY must be independently confirmed before anything is
> built on them.

## 1. The authority boundary (corrects our working model)

- Governing statute: **lov 19. juni 1969 nr. 53 om Norsk Lovtidend m.v.**
  (successor to the 1876 law; first volume 1877). § 3: default commencement
  one month after the *issue's publication day*; § 2 authorizes the
  avdeling split; fvl. § 38 requires forskrift promulgation.
- **The 2001 electronic-authority transition was NOT a statutory amendment.**
  The 1969 law was never amended for it (nor in 2018 when print ceased).
  Electronic became authoritative from the **2001 volume by ministry
  practice/interpretation** (Lovdata: "Den elektroniske versjonen ble
  offisiell fra 2001, og lovparagrafen er deretter blitt tolket dithen at
  det er kunngjøringsdatoen for den elektroniske versjonen som er
  utslagsgivende"). Print continued through the 2017 print volume
  (2016 årgang); digital-only from 2018.
- Therefore: **pre-2001 the printed hefte is the sole authoritative
  artifact** — the § 3 commencement clock ran against the printed issue's
  publication date. Lovdata's 1990s CD-ROMs / Pro texts are commercial
  derivatives with no legal status (corroboration channel only, never
  source of record). Provenance should record the boundary as
  "2001 volume onward: electronic authoritative by administrative
  practice under lov 1969-06-19-53", not as a dated amendment.
- **Avd. I / Avd. II split changed in 1974** (from 1974: Avd. I = laws +
  central forskrifter incl. Svalbard/biland/university; Avd. II =
  regional/local). Pre-1974 volumes allocate content differently than the
  post-2001 model assumes. Print format A5 → A4 at 2001.
- **European analogue (Austria RIS) is a direct model for the boundary
  encoding**: online edition legally non-binding from June 1997, authentic
  and legally binding from 2004-01-01 by explicit statute
  (Kundmachungsreformgesetz, BGBl. I Nr. 100/2003; signed PDFs), with
  1945–2003 as non-binding electronic versions and 1780–1940 as national-
  library scans. Germany: BGBl online 1998, exclusively-online promulgation
  only from 2023-01-01, pre-2023 online texts explicitly "electronic
  copies, not the authoritative version"; the offenegesetze/BGBl copyright
  dispute is a cautionary analogue on gazette database/terms rights.

## 2. Print-era corrections lane (ancestor of the W-84 beriktiget lane)

- Rettelser were published in the **next available printed issue**, with a
  consolidated "Oversikt over rettelser" at the **back of each hefte /
  volume**; cross-references are **issue + page**, not URN.
- Lovdata's online rettelser overview is complete only from 2017;
  2001–2016 live at the back of the (electronic) hefter; earlier years
  only in the scans.
- Each annual volume carries **chronological + subject registers per
  avdeling** — the chronological register enumerates every kunngjøring →
  natural machine-checkable completeness manifest. Hefte covers state
  their page range (finer-grained check).
- Layout for segmentation: running heads ("Norsk Lovtidend … Nr. X …
  Side Y"), chronological table of contents, per-item headers giving
  date + number ("3. mai. Lov nr. 13 …"), typographic § structure.
  The 1974 division change and 2001 A5→A4 change require era-specific
  segmentation.

## 3. Source of record: Nasjonalbiblioteket facsimiles

- NB is digitizing the whole 1877–2000 print run into
  Bokhylla/Nettbiblioteket; pipeline yields page images + **ALTO-XML OCR
  per page keyed by URN**, served via **IIIF Image API v2**
  (`URN:NBN:no-nb_digibok_…` items; catalog API
  `api.nb.no/catalog/v1/items`; DH-lab REST `api.nb.no/dhlab` +
  `dhlab` Python pkg).
- **The run is NOT complete.** Documented gaps include 1998 Avd. II
  missing hefter 2,3,5,7,8,9 (Avd. II — likely outside our corpus lane)
  and gaps in 1976/1978/1980/1987–1989 Avd. I outside the pilot.
  **VERIFY: Avd. I 1997–2000 completeness issue-by-issue against the
  annual chronological registers before building anything.**
- **Access regime — report's Bokhylla worry DEFUSED for the gazette
  itself (probed 2026-08-18, api.nb.no/catalog/v1/items):** every
  pilot-window Lovtidend issue and register found is flagged
  `license: publicdomain`, `accessAllowedFrom: EVERYWHERE`,
  `viewability: ALL` — per-hefte `digitidsskrift` items (e.g. 1998
  Avd. I Nr. 1 = `URN:NBN:no-nb_digitidsskrift_2015102680002_001`).
  The Bokhylla restriction observed applies to *books about* Lovtidend,
  not the gazette volumes. Bulk etiquette/rate limits still unpublished —
  confirm with nb@nb.no.
- **Pilot-window per-issue gap map (same probe; fuzzy search, so
  apparent gaps must be re-enumerated via proper series pagination
  before being treated as real):** 1997 Avd. I highest Nr. 29, nrs.
  2, 5, 6, 14 not returned; 1998 Avd. I 27 issues + register (numbers
  not enumerated); 1999 Avd. I highest Nr. 19, nr. 13 not returned;
  2000 Avd. I highest Nr. 37, nrs. 3, 4, 12, 15, 20, 34, 36 not
  returned. Annual registers for the pilot years ARE digitized and
  public domain → the Stage-1 manifest is buildable immediately.
- Gap-fill fallback: **UiO Juridisk bibliotek holds a complete printed
  set** — re-scan specific missing hefter from there (own-scan also
  sidesteps the Bokhylla flag entirely).

## 4. Corroboration channels (born-digital)

- **Lovdata Pro holds promulgated lovvedtak (Avd. I) from 1980 onward**
  (+ historical paragraph versions from 1999-01-01; report's inventory
  table adds "some XML internally back to ~1982"). Pre-1980 promulgated
  text exists only in print. ⇒ the [1997, 2000] pilot (and everything back
  to 1980) has BOTH channels; pre-1980 is single-channel (print only).
  **VERIFY by sampling: whether the Pro 1980+ text is as-announced or
  consolidated at source** (report risk 7).
- **No released pre-2001 dataset exists** (public NLOD XML dataset on
  data.norge.no covers post-2001 only; a Lovdata rep confirmed Nov 2025
  no complete historical datasets published yet). **This breaks item 87's
  recorded premise** that a "1999 tarball" is acquirable self-serve: the
  acquisition path is a negotiated agreement via **utvikling@lovdata.no**.
  No pricing signal found.
- **HR-2019-1725-A** (rettspraksis.no): Lovdata's database enjoys åvl. § 24
  sui generis protection; § 14 exemption of the underlying texts does NOT
  defeat it, and mass extraction infringes. Lovdata's user agreement
  prohibits mass/automated downloading. ⇒ the corroboration corpus must
  come by agreement, never scraping.
- Third channel (weak, vedtak not kunngjøring): Stortinget's enacted-text
  records — "Forarbeid til lovene" (1894–2010), Stortingsforhandlinger
  (1814–2007, digitized: DigiStorting / nb.no / statsmaktene).
- The 1990s CD-ROMs contain *consolidated* law (from 1990) — weak
  corroboration only (consolidation ≠ as-announced text).
- Språkbanken / DH-lab: no dedicated Lovtidend corpus identified; NB's
  public-domain book corpus reports ~90% avg word confidence (OCR-quality
  signal only).

## 5. OCR feasibility and prior art

- Modern OCR/HTR of 20th-c. Nordic antiqua: CER ~≤1% on clean print
  (Transkribus print models, vision-LLM pipelines; Swedish newspaper
  model "much below 1%"). NB's legacy book OCR is worse (~90% word
  confidence). Pre-1917/1938 orthography raises OCR and comparison
  complexity but does not break a dual-channel design.
- **The binding metric is the certified-agreement rate per hefte**
  (passages where the two channels agree byte-for-byte), NOT average
  CER. Disagreements become typed refusals, not silent errors.
- Prior art supports the design: UK legislation.gov.uk (revised from
  1267, original from 1988, editorial QA over authoritative sources),
  Austria RIS, Germany BGBl — none documented writing raw single-channel
  OCR into a consolidated corpus; second-channel/editorial checks are
  the norm. Finland/EUR-Lex back-capture flagged as unverified
  comparators.

## 6. Staged plan (report's recommendation, matches our discipline)

- **Stage 0 — fix the authority record** (no cost): encode the boundary
  triple (pre-2001 print authoritative / 2001–2016 electronic
  authoritative, print still produced / 2018+ electronic only), note the
  never-amended 1969 statute, add 1974-split and 2001-format era flags.
- **Stage 1 — completeness manifest first**: obtain the 1997–2000 annual
  chronological registers (per avdeling) and enumerate every announced
  item (date, number, page) — the print-era analogue of the
  gjeldende-lover oracle. Anything later unlowered = typed refusal
  against this manifest.
- **Stage 2 — acquire source of record**: NB images + ALTO for the pilot
  window via IIIF/api.nb.no; email nb@nb.no + DH-lab for per-volume
  license flags, bulk delivery, rate limits; UiO rescans for gaps.
- **Stage 3 — acquire corroboration**: data agreement with
  utvikling@lovdata.no for born-digital Avd. I text 1997–2000; never
  scrape; Stortinget vedtak text as supplementary third channel.
- **Stage 4 — pilot extraction with dual-channel certification**:
  payload lands only on byte-faithful agreement; measure
  certified-agreement rate per hefte as the go/no-go.
- **Benchmarks/fallbacks**: high agreement ⇒ extend to 1990–1996 then
  toward 1974. Bokhylla flag blocks bulk OCR ⇒ pivot source-of-record to
  UiO rescans, NB as second image channel. Lovdata declines ⇒ fall back
  to two independent OCR engines (Transkribus vs Tesseract `nor`) as
  channels — weaker, higher refusal rate, acceptable. Pre-1917/1938
  orthography ⇒ era-specific OCR models, higher disagreement budget.

## 7. Consequences for the programme

1. **Item 87 (W-81) needs re-chartering**: the precondition is not "the
   1999 tarball on disk" but "a negotiated pre-2001 data channel"; the
   format probe's target artifact may end up being NB ALTO + Lovdata Pro
   text rather than a Lovdata XML tarball, in which case the probe's
   dialect questions (`changesToDocuments`, `data-change-part`) are moot
   (unless Lovdata's internal ~1982+ XML is what arrives) and its real
   question becomes the drafting-grammar refusal rate over clean text.
2. **The dual-channel byte-agreement gate is ratified** as the landing
   condition for OCR-era payloads, with certified-agreement rate per
   hefte as the go/no-go metric. Pre-1980: no born-digital channel —
   stricter charter (two-OCR-engine channels or consolidation-oracle
   adjudication) needed.
3. **New parser obligations for the print era**: back-matter rettelser
   lane (issue+page cross-refs), per-volume register-as-manifest
   ingestion, 1974 avdeling-split awareness, era-specific segmentation
   (A5 pre-2001; pre-1974 header conventions need direct inspection —
   report risk 9).
4. **Immediate actionable steps** (user-facing): (a) contact
   utvikling@lovdata.no re: pre-2001 Avd. I text under agreement —
   ask specifically what born-digital/XML exists back to ~1982 and its
   as-announced fidelity; (b) contact nb@nb.no / DH-lab re: bulk
   images+ALTO for Avd. I 1997–2000, per-item § 14 flags, rate limits;
   (c) issue-by-issue completeness check of the pilot window against
   the annual registers.

## 8. Risks (report's ranking)

Known bad (verified): NB pilot-window incompleteness — 1998 Avd. II
hefter gaps per the forum inventory, plus apparent Avd. I gaps from our
own 2026-08-18 probe (1997: 2,5,6,14; 1999: 13; 2000: 3,4,12,15,20,34,36
— fuzzy-search caveat, re-enumerate before trusting); Lovdata § 24 +
contract bars mass download (HR-2019-1725-A). ~~Bokhylla regime~~ —
DEFUSED by probe: gazette items are flagged publicdomain/EVERYWHERE.

Unknown (open): exact per-issue URN enumeration for the pilot window
(needs series pagination, not fuzzy search); NB bulk-download etiquette /
API rate limits; depth/fidelity/pricing of Lovdata's internal pre-2001
born-digital holdings (as-announced vs consolidated — sample on receipt);
Finland/EUR-Lex back-capture methods; pre-1974 volume structure vs
current parser assumptions.
