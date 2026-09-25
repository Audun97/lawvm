"""W-3 step 2e: is the declared-but-unbound gap an EXTRACTION failure or an
over-inclusive declared list?

For a sample of `dated` acts, take each declared-but-unbound target and ask
whether the act's own operative text actually names that law (by "<dato> nr. N"
or by title). If it does, extraction failed. If it does not, Lovdata's declared
list is broader than the act's operative content and the gap is not ours.

Read-only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from lxml import etree

from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.sources import (
    load_no_amendment_artifact_bytes,
    load_no_current_law_ids,
    resolve_no_source_path,
)

MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
          "august", "september", "oktober", "november", "desember"]

d = resolve_no_source_path(None)
idx = build_no_amendment_index(d)
by_id = {e.source_id: e for e in idx.entries}
current_ids = set(load_no_current_law_ids(d))
COVERAGE_JSON = (
    Path(__file__).resolve().parents[2] / ".tmp" / "no_declared_target_coverage.json"
)
if not COVERAGE_JSON.exists():
    raise SystemExit(f"run no_declared_target_coverage.py first ({COVERAGE_JSON} missing)")
rows = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))

DECL_BLOCK = re.compile(r'<dd\s+class="changesToDocuments">(.*?)</dd>', re.DOTALL | re.I)
DECL_ITEM = re.compile(r"<li>\s*(?:no://)?(?:lov|LOV)/([0-9]{4}-[0-9]{2}-[0-9]{2}(?:-[0-9]+)?)\s*</li>")

dated = [r for r in rows if r["status"] == "dated" and r["missed_verifiable"]]
dated.sort(key=lambda r: -r["missed_verifiable"])
sample = dated[:6] + dated[len(dated) // 2: len(dated) // 2 + 6] + dated[-6:]

named = unnamed = 0
detail = []
for r in sample:
    e = by_id[r["id"]]
    raw = load_no_amendment_artifact_bytes(r["id"], e.archive, e.member_name, d)
    if raw is None:
        continue
    rawtext = raw.decode("utf-8", errors="replace")
    try:
        text = " ".join(
            str(t).strip() for t in etree.fromstring(raw).itertext() if t and str(t).strip()
        )
    except etree.XMLSyntaxError:
        text = rawtext
    # strip the metadata header (which contains the declared list itself) so we
    # only search the OPERATIVE body
    cut = text.find("RefID")
    body = text[cut:] if cut > 0 else text

    declared = {f"no/lov/{m}" for b in DECL_BLOCK.findall(rawtext) for m in DECL_ITEM.findall(b)}
    missed = sorted((declared - set(e.base_ids)) & current_ids)
    hits = []
    for law in missed:
        m = re.match(r"no/lov/(\d{4})-(\d{2})-(\d{2})-(\d+)$", law)
        if not m:
            continue
        y, mo, dd, n = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        pat = re.compile(rf"{dd}\.?\s*{MONTHS[mo - 1]}\s*{y}\s*nr\.?\s*{n}\b", re.I)
        found = bool(pat.search(body))
        hits.append((law, found))
        if found:
            named += 1
        else:
            unnamed += 1
    detail.append((r["id"], r["title"], hits))

print("=" * 74)
print(f"sampled {len(detail)} DATED acts; declared-but-unbound VERIFIABLE targets:")
print(f"  named in the act's operative text  (extraction failed) : {named}")
print(f"  NOT named (declared list over-inclusive / title-only)  : {unnamed}")
tot = named + unnamed
if tot:
    print(f"  => extraction-failure share: {named / tot:.0%}")
print("=" * 74)
for act, title, hits in detail:
    n = sum(1 for _, f in hits if f)
    print(f"\n{act}  {n}/{len(hits)} named in body")
    print(f"  {title}")
    for law, f in hits[:8]:
        print(f"    {'NAMED  ' if f else 'absent '} {law}")
