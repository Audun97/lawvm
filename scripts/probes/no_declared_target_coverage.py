"""W-3 step 2d: Lovdata publishes a STRUCTURED declared-target list on every
amendment act -- `<dd class="changesToDocuments"><li>lov/YYYY-MM-DD-N</li>...`.
The index ignores it entirely (base_ids are derived from extracted ops only).

Read-only. Corpus-wide: declared targets vs bound base_ids, per act, and how
many of the missed targets we can actually verify (have consolidated text for)
and would actually apply (act is `dated`, not `contingent`).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.sources import (
    iter_no_amendment_artifacts,
    load_no_current_law_ids,
    resolve_no_source_path,
)

# Written under .tmp/ (gitignored) so a rerun is cheap and leaves no artifact.
OUT = Path(__file__).resolve().parents[2] / ".tmp" / "no_declared_target_coverage.json"

DECL_BLOCK = re.compile(
    r'<dd\s+class="changesToDocuments">(.*?)</dd>', re.DOTALL | re.IGNORECASE
)
DECL_ITEM = re.compile(r"<li>\s*(?:no://)?(?:lov|LOV)/([0-9]{4}-[0-9]{2}-[0-9]{2}(?:-[0-9]+)?)\s*</li>")


def main() -> int:
    d = resolve_no_source_path(None)
    idx = build_no_amendment_index(d)
    by_id = {e.source_id: e for e in idx.entries}
    current_ids = set(load_no_current_law_ids(d))
    print(f"index entries {len(by_id)}, laws with consolidated text {len(current_ids)}",
          file=sys.stderr)

    rows: list[dict] = []
    seen = no_decl = 0
    for art in iter_no_amendment_artifacts(d):
        seen += 1
        if seen % 500 == 0:
            print(f"  ... {seen}", file=sys.stderr)
        raw = art.payload.decode("utf-8", errors="replace")
        blocks = DECL_BLOCK.findall(raw)
        if not blocks:
            no_decl += 1
            continue
        declared = {f"no/lov/{m}" for b in blocks for m in DECL_ITEM.findall(b)}
        if not declared:
            no_decl += 1
            continue
        e = by_id.get(art.logical_id)
        bound = set(e.base_ids) if e else set()
        missed = declared - bound
        rows.append({
            "id": art.logical_id,
            "status": e.effective_status if e else "<unindexed>",
            "raw_dif": (e.raw_date_in_force if e else "")[:32],
            "declared": len(declared),
            "bound": len(bound),
            "missed": len(missed),
            "bound_not_declared": len(bound - declared),
            "missed_verifiable": len(missed & current_ids),
            "n_ops": e.n_ops if e else 0,
            "title": (e.title if e else "")[:90],
        })

    print(f"\nscanned {seen} artifacts; {no_decl} had no declared-target field; "
          f"{len(rows)} had one\n")

    tot_decl = sum(r["declared"] for r in rows)
    tot_bound = sum(r["bound"] for r in rows)
    tot_missed = sum(r["missed"] for r in rows)
    tot_ver = sum(r["missed_verifiable"] for r in rows)
    tot_extra = sum(r["bound_not_declared"] for r in rows)
    print("=" * 74)
    print(f"declared target bindings (Lovdata's own list) : {tot_decl}")
    print(f"bound by the index                            : {tot_bound}")
    print(f"declared but NOT bound  (the gap)             : {tot_missed}"
          f"   ({tot_missed / tot_decl:.1%} of declared)")
    print(f"  ...of which we have consolidated text       : {tot_ver}")
    print(f"bound but NOT declared (index over-reach)     : {tot_extra}")
    print(f"acts with a nonempty gap                      : "
          f"{sum(1 for r in rows if r['missed'])} / {len(rows)}")
    print("=" * 74)

    print("\n--- the gap by commencement status (payoff: `dated` applies today) ---")
    g: Counter[str] = Counter()
    v: Counter[str] = Counter()
    a: Counter[str] = Counter()
    for r in rows:
        g[r["status"]] += r["missed"]
        v[r["status"]] += r["missed_verifiable"]
        if r["missed"]:
            a[r["status"]] += 1
    print(f"{'status':<14}{'acts':>7}{'missed':>9}{'verifiable':>12}")
    for k in sorted(g, key=lambda k: -g[k]):
        print(f"{k:<14}{a[k]:>7}{g[k]:>9}{v[k]:>12}")

    dated = [r for r in rows if r["status"] == "dated" and r["missed_verifiable"]]
    dated.sort(key=lambda r: -r["missed_verifiable"])
    print(f"\n--- top 25 DATED acts by verifiable missed targets "
          f"({len(dated)} such acts) ---")
    print(f"{'decl':>5}{'bound':>6}{'miss':>6}{'ver':>5}{'ops':>5}  id")
    for r in dated[:25]:
        print(f"{r['declared']:>5}{r['bound']:>6}{r['missed']:>6}"
              f"{r['missed_verifiable']:>5}{r['n_ops']:>5}  {r['id']}")
        print(f"{'':>27}{r['title']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print(f"\nfull rows -> {OUT} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
