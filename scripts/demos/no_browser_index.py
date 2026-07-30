#!/usr/bin/env -S uv run python
"""Build browser views for every replayable Norway law, plus an index page.

    uv run scripts/demos/no_browser_index.py --out .tmp/no_demo

Runs the Norway verify scan to find the replayable laws and their
replay-vs-published verdicts, renders one page per law via
``no_browser_demo.build_snapshots``, and writes an ``index.html`` that lists
every law with its verdict so the good and bad cases are visible together.
"""
from __future__ import annotations

import argparse
import html
import json
import traceback
from pathlib import Path
from typing import Any

from no_browser_demo import amendment_dates, build_snapshots, render_html

_VERDICT_ORDER = {"consistent": 0, "replay_defect": 1, "untouched_drift": 2, "sparse_source": 3}


def scan_laws(limit: int, as_of: str) -> tuple[list[dict[str, Any]], str]:
    from lawvm.norway.verify import build_no_verify_scan

    report = build_no_verify_scan(as_of=as_of, limit=limit)
    return list(report.get("results", [])), str(report.get("as_of") or as_of)


def verdict_for(row: dict[str, Any]) -> str:
    if row.get("consistent"):
        return "consistent"
    if row.get("source_signal") == "sparse_indexed_history":
        return "sparse_source"
    counts = row.get("divergence_counts") or {}
    if "OPS_MISSING" in counts:
        return "replay_defect"
    return "untouched_drift"


_LABEL = {
    "consistent": ("Matches published text", "ok"),
    "replay_defect": ("Engine gap — we missed an amendment effect", "bad"),
    "untouched_drift": ("Published text differs where no amendment applies", "warn"),
    "sparse_source": ("Incomplete amendment history available", "info"),
}


def render_index(rows: list[dict[str, Any]], as_of: str) -> str:
    cards = []
    for row in sorted(rows, key=lambda r: (_VERDICT_ORDER[verdict_for(r)], r["base_id"])):
        v = verdict_for(row)
        label, cls = _LABEL[v]
        link = row.get("_page")
        title = html.escape(row.get("current_title") or row["base_id"])
        base = html.escape(row["base_id"])
        lovdata = "https://lovdata.no/dokument/NL/lov/" + row["base_id"].removeprefix("no/lov/")
        divs = row.get("divergence_count") or 0
        name = html.escape(link) if link else ""
        cards.append(f"""
    <article class="card {cls}">
      <div class="badge">{html.escape(label)}</div>
      <h2>{title}</h2>
      <div class="ids">{base} · {row.get('amendment_count', 0)} endringslov(er)
        · {row.get('replay_op_count', 0)} operasjoner
        · {"ingen avvik" if not divs else str(divs) + " avvik"}</div>
      <div class="links">
        {'<a href="laws/' + name + '">open law ↗</a>' if link else '<span class="dead">no page</span>'}
        <a href="{html.escape(lovdata)}" target="_blank" rel="noopener">lovdata.no ↗</a>
      </div>
    </article>""")

    counts = {k: sum(1 for r in rows if verdict_for(r) == k) for k in _VERDICT_ORDER}
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LawVM Norge — replayable laws</title>
<style>
  :root {{ color-scheme: light dark;
    --fg:#1a1a1a; --bg:#fbfbfa; --muted:#6b6b6b; --line:#e0e0dc; --accent:#2b5faa;
    --ok:#1a7f37; --bad:#b3261e; --warn:#a8730a; --info:#5a5a8a; }}
  @media (prefers-color-scheme: dark) {{ :root {{
    --fg:#e6e6e6; --bg:#16171a; --muted:#9a9a9a; --line:#2e3034; --accent:#7aa7e8;
    --ok:#5dd47f; --bad:#ff8a80; --warn:#e8b45d; --info:#a9a9d8; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.6 system-ui,-apple-system,sans-serif; color:var(--fg); background:var(--bg); }}
  .wrap {{ max-width:900px; margin:0 auto; padding:0 20px; }}
  header {{ padding:26px 0 18px; border-bottom:1px solid var(--line); }}
  h1 {{ font-size:21px; margin:0 0 6px; }}
  .sub {{ color:var(--muted); font-size:13px; }}
  .tally {{ display:flex; flex-wrap:wrap; gap:16px; margin:16px 0 0; font-size:13px; }}
  .tally b {{ font-size:20px; display:block; }}
  .t-ok b {{ color:var(--ok); }} .t-bad b {{ color:var(--bad); }}
  .t-warn b {{ color:var(--warn); }} .t-info b {{ color:var(--info); }}
  main {{ padding:22px 0 60px; }}
  .card {{ border:1px solid var(--line); border-left-width:4px; border-radius:8px; padding:13px 15px; margin:11px 0; }}
  .card.ok {{ border-left-color:var(--ok); }} .card.bad {{ border-left-color:var(--bad); }}
  .card.warn {{ border-left-color:var(--warn); }} .card.info {{ border-left-color:var(--info); }}
  .badge {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:5px; }}
  .card h2 {{ font-size:15px; margin:0 0 5px; font-weight:600; line-height:1.4; }}
  .ids {{ font-size:12.5px; color:var(--muted); font-variant-numeric:tabular-nums; }}
  .links {{ margin-top:9px; display:flex; gap:14px; font-size:13px; }}
  .links a {{ color:var(--accent); text-decoration:none; }}
  .links a:hover {{ text-decoration:underline; }}
  .dead {{ color:var(--muted); }}
  .note {{ font-size:13px; color:var(--muted); border:1px solid var(--line); border-radius:8px;
    padding:12px 14px; margin:18px 0 4px; }}
</style></head><body>
<header><div class="wrap">
  <h1>LawVM Norge — every replayable law</h1>
  <div class="sub">Each law rebuilt from its original text plus its amendments, then compared
     against the published consolidated version. Comparison date {html.escape(as_of)}.</div>
  <div class="tally">
    <div class="t-ok"><b>{counts['consistent']}</b>match published</div>
    <div class="t-bad"><b>{counts['replay_defect']}</b>engine gap</div>
    <div class="t-warn"><b>{counts['untouched_drift']}</b>unexplained drift</div>
    <div class="t-info"><b>{counts['sparse_source']}</b>incomplete history</div>
  </div>
</div></header>
<main><div class="wrap">
  <div class="note"><b>How to read this.</b> “Match” means our rebuild equals the published law exactly.
    “Engine gap” means an amendment existed that we failed to turn into a change — our bug.
    “Unexplained drift” means the published text differs somewhere no amendment we hold touches
    (often an amendment missing from our index, or an editorial fix by the publisher).
    “Incomplete history” means we only hold a fraction of the law’s amendments, so a mismatch is expected.</div>
  {"".join(cards)}
</div></main>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(".tmp/no_demo"))
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--as-of", default="2026-03-29")
    args = ap.parse_args()

    rows, as_of = scan_laws(args.limit, args.as_of)
    print(f"scanned {len(rows)} laws")
    (args.out / "laws").mkdir(parents=True, exist_ok=True)

    for row in rows:
        base = row["base_id"]
        slug = base.replace("/", "_") + ".html"
        try:
            dates = amendment_dates(base)
            if not dates:
                print(f"  skip {base}: no dated amendments")
                continue
            data = build_snapshots(base, dates)
            (args.out / "laws" / slug).write_text(render_html(data), encoding="utf-8")
            row["_page"] = slug
            changed = sum(len(s["changes"]) for s in data["snapshots"])
            print(f"  {base}: {len(dates)} dates, {changed} changed lines -> laws/{slug}")
        except Exception as exc:  # a demo build must not die on one bad law
            print(f"  FAILED {base}: {exc.__class__.__name__}: {exc}")
            traceback.print_exc(limit=2)

    (args.out / "index.html").write_text(render_index(rows, as_of), encoding="utf-8")
    (args.out / "scan.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
