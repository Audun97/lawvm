# Kringkastingsloven print-era witness slice (W-87 … W-103)

The pre-2001 chain of `no/lov/1992-12-04-127` (lov om kringkasting) reconstructed
from Nasjonalbiblioteket's digitised Norsk Lovtidend Avd. I: the founding act and
its 13 print-era amending acts (1993–2000), as located issue-by-issue in W-87 and
read through the four-channel evidence ladder of W-91.

| file | what | source |
|---|---|---|
| `manifest.json` | the 14 acts: NB issue id, URN, canvases, printed pages, ladder class totals; the two omnibus carve canvases | W-87 manifest (`api.nb.no` catalog, IIIF) |
| `ladder_lines.json` | every NB ALTO spine line (geometry, ladder class A/B/C/R, certified text; for R lines the ABBYY spine reading, the GLM-OCR proposal and all candidates) | W-91 ladder over ALTO (ABBYY FineReader 8.1), tesseract 5.5 `nor`, Transkribus NorPrint, GLM-OCR 0.9B |
| `chains.json` | the 75 sections of today's consolidation with their `changesToParent` chains (the `ikr.` dates the emitter reads) | Lovdata `gjeldende-lover` capture 2026-08-14 |
| `current/nl-19921204-127.xml` | today's consolidation, the verify oracle | Lovdata `gjeldende-lover.tar.bz2` capture 2026-08-14 (NLOD 2.0) |
| `lti/*.xml` | the 14 emitted acts in the unstructured pre-2001 LTI shape, each article carrying `data-lawvm-ladder` (the class of every print line it was built from), `data-lawvm-proposal` where an R line landed from the proposal channel, `data-lawvm-refused` on a lead built from an R line | `lawvm.norway.print_era.emit_print_era_slice` over the two files above |
| `receipts.json` | the emission receipt per act (refused leads, address folds, proposal lines, date source, carve) | same |

Authority: **witness only.** The NB gazette scans are public domain, but an OCR
reconstruction is not the promulgated bytes; nothing here is an admitted source
lane (`notes/NORWAY_LAWVM_STATUS.md` §2.5). The fixture exists so that
`tests/test_norway_print_era.py` can (a) prove the emitter reproduces these files
from the ladder, (b) replay the pre-2001 chain source-absent and pin which of the
13 OCR-only sections match today's consolidation, and (c) with the local 2001+
archives present, pin the full-chain witness the ledger quotes (62/75 at W-102).

Regenerate after an emitter change (then re-run the tests and update the ledger):

```bash
uv run python -c "
from pathlib import Path
from lawvm.norway.print_era import *
D=Path('tests/data/norway_print_era/kringkastingsloven')
for e in emit_print_era_slice(load_print_era_ladder(D/'ladder_lines.json'), load_print_era_manifest(D/'manifest.json'), load_print_era_chains(D/'chains.json'), '1992-12-04-127'):
    (D/'lti'/e.file_name).write_text(e.xml, encoding='utf-8')
"
```
