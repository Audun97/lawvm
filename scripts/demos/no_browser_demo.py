#!/usr/bin/env -S uv run python
"""Build a self-contained browser view of one Norway law over time.

Replays a Norwegian law at several dates, walks the resulting IR tree into
structured chapters/sections/subsections, diffs consecutive dates, and writes a
single standalone HTML file (no server, no build step, no network).

    uv run scripts/demos/no_browser_demo.py no/lov/2020-05-07-38 \
        --date 2020-06-01 --date 2022-01-01 --date 2026-03-29 \
        --out .tmp/no_demo/index.html

This is a DEMO surface, not an engine component: it renders what
``replay_no_to_pit`` already produces. The engine remains the only authority for
what the law said on a date.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
from pathlib import Path
from typing import Any


def _node_to_dict(node: Any) -> dict[str, Any]:
    return {
        "kind": str(getattr(node, "kind", "") or ""),
        "label": (node.label or "") if getattr(node, "label", None) else "",
        "text": (node.text or "") if getattr(node, "text", None) else "",
        "children": [_node_to_dict(c) for c in getattr(node, "children", ()) or ()],
    }


def _heading_of(node: dict[str, Any]) -> str:
    for child in node["children"]:
        if child["kind"] == "heading":
            return child["text"]
    return ""


def _flatten_law(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Body tree -> a flat ordered list of renderable blocks."""
    blocks: list[dict[str, Any]] = []

    def walk_section(section: dict[str, Any], chapter_label: str) -> None:
        paras: list[dict[str, str]] = []
        for child in section["children"]:
            if child["kind"] == "heading":
                continue
            text = child["text"].strip()
            if text:
                paras.append({"label": child["label"], "text": text})
            for grand in child["children"]:
                gtext = grand["text"].strip()
                if gtext:
                    paras.append(
                        {"label": f"{child['label']}.{grand['label']}".strip("."), "text": gtext}
                    )
        own = section["text"].strip()
        if own:
            paras.insert(0, {"label": "", "text": own})
        blocks.append(
            {
                "type": "section",
                "chapter": chapter_label,
                "label": section["label"],
                "heading": _heading_of(section),
                "paras": paras,
            }
        )

    for chapter in body["children"]:
        if chapter["kind"] == "chapter":
            blocks.append(
                {
                    "type": "chapter",
                    "label": chapter["label"],
                    "heading": _heading_of(chapter),
                }
            )
            for child in chapter["children"]:
                if child["kind"] == "section":
                    walk_section(child, chapter["label"])
        elif chapter["kind"] == "section":
            walk_section(chapter, "")
    return blocks


def _block_lines(blocks: list[dict[str, Any]]) -> list[str]:
    """Stable one-line-per-paragraph view, used for the between-date diff."""
    lines: list[str] = []
    for b in blocks:
        if b["type"] == "chapter":
            lines.append(f"### Kapittel {b['label']} {b['heading']}")
        else:
            lines.append(f"## § {b['label']} {b['heading']}")
            for p in b["paras"]:
                lines.append(f"{b['label']}|{p['label']}|{p['text']}")
    return lines


def _diff_pairs(prev: list[str], curr: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    matcher = difflib.SequenceMatcher(a=prev, b=curr, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for line in prev[i1:i2]:
            out.append({"op": "removed", "text": line.split("|", 2)[-1]})
        for line in curr[j1:j2]:
            out.append({"op": "added", "text": line.split("|", 2)[-1]})
    return out


def amendment_dates(base_id: str) -> list[str]:
    """The law's own change dates: the day before its first amendment, then each."""
    from lawvm.norway.index import build_no_amendment_index
    from lawvm.norway.sources import resolve_no_source_path

    index = build_no_amendment_index(resolve_no_source_path(None))
    dates: set[str] = set()
    for entry in index.entries:
        if base_id not in entry.base_ids:
            continue
        date = (entry.effective_date or "").strip()
        if len(date) == 10 and entry.effective_status == "dated":
            dates.add(date)
    if not dates:
        return []
    first = min(dates)
    year, month, day = (int(p) for p in first.split("-"))
    import datetime as _dt

    before = (_dt.date(year, month, day) - _dt.timedelta(days=1)).isoformat()
    return [before, *sorted(dates)]


def build_snapshots(base_id: str, dates: list[str]) -> dict[str, Any]:
    from lawvm.norway.replay import replay_no_to_pit

    snapshots: list[dict[str, Any]] = []
    title = ""
    for date in dates:
        result = replay_no_to_pit(base_id, date)
        if result.error:
            raise SystemExit(f"replay failed for {base_id} @ {date}: {result.error}")
        if result.replayed is None:
            raise SystemExit(f"no replayed tree for {base_id} @ {date}")
        title = title or result.base_title
        blocks = _flatten_law(_node_to_dict(result.replayed.body))
        snapshots.append(
            {
                "date": date,
                "blocks": blocks,
                "lines": _block_lines(blocks),
                "applied": list(result.amendments_applied),
                "n_ops": result.n_ops,
            }
        )

    for idx, snap in enumerate(snapshots):
        snap["changes"] = (
            [] if idx == 0 else _diff_pairs(snapshots[idx - 1]["lines"], snap["lines"])
        )
    for snap in snapshots:
        snap.pop("lines", None)

    return {"base_id": base_id, "title": title, "snapshots": snapshots}


_LOVDATA = "https://lovdata.no/dokument/NL/lov/"


def render_html(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    lovdata_url = _LOVDATA + data["base_id"].removeprefix("no/lov/")
    return f"""<!DOCTYPE html>
<html lang="no"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(data["title"] or data["base_id"])} — LawVM Norge</title>
<style>
  :root {{ color-scheme: light dark;
    --fg:#1a1a1a; --bg:#fbfbfa; --muted:#6b6b6b; --line:#e0e0dc;
    --add:#1a7f37; --addbg:#e8f5ec; --del:#b3261e; --delbg:#fdecea; --accent:#2b5faa; }}
  @media (prefers-color-scheme: dark) {{ :root {{
    --fg:#e6e6e6; --bg:#16171a; --muted:#9a9a9a; --line:#2e3034;
    --add:#5dd47f; --addbg:#12291a; --del:#ff8a80; --delbg:#2c1615; --accent:#7aa7e8; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:16px/1.65 Georgia,'Iowan Old Style',serif; color:var(--fg); background:var(--bg); }}
  header {{ padding:22px 20px 14px; border-bottom:1px solid var(--line); }}
  .wrap {{ max-width:820px; margin:0 auto; }}
  h1 {{ font-size:20px; margin:0 0 6px; line-height:1.35; }}
  .sub {{ color:var(--muted); font-size:13px; font-family:system-ui,sans-serif; }}
  .sub a {{ color:var(--accent); }}
  .dates {{ display:flex; flex-wrap:wrap; gap:8px; padding:14px 0 2px; font-family:system-ui,sans-serif; }}
  .dates button {{ font:600 13px system-ui,sans-serif; padding:7px 13px; border:1px solid var(--line);
    background:transparent; color:var(--fg); border-radius:999px; cursor:pointer; }}
  .dates button[aria-pressed="true"] {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  main {{ padding:20px; }}
  .meta {{ font:13px/1.6 system-ui,sans-serif; color:var(--muted); margin-bottom:18px; }}
  .changes {{ border:1px solid var(--line); border-radius:8px; padding:12px 14px; margin-bottom:26px;
    font:14px/1.6 system-ui,sans-serif; background:color-mix(in srgb, var(--bg) 80%, var(--fg) 4%); }}
  .changes h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.06em; margin:0 0 8px; color:var(--muted); }}
  .chg {{ padding:3px 7px; border-radius:4px; margin:3px 0; }}
  .chg.added {{ color:var(--add); background:var(--addbg); }}
  .chg.removed {{ color:var(--del); background:var(--delbg); text-decoration:line-through; }}
  .chapter {{ font:700 15px system-ui,sans-serif; margin:34px 0 4px; padding-top:14px; border-top:1px solid var(--line); }}
  .section {{ margin:20px 0; }}
  .secnum {{ font:700 15px system-ui,sans-serif; }}
  .sechead {{ font-style:italic; color:var(--muted); }}
  p.para {{ margin:7px 0; }}
  .lbl {{ font:11px system-ui,sans-serif; color:var(--muted); vertical-align:super; margin-right:4px; }}
  .none {{ color:var(--muted); font-style:italic; }}
</style></head><body>
<header><div class="wrap">
  <h1 id="title"></h1>
  <div class="sub"><span id="baseid"></span> ·
    <a id="lovdata" href="{html.escape(lovdata_url)}" target="_blank" rel="noopener">
      compare with lovdata.no ↗</a></div>
  <div class="dates" id="dates"></div>
</div></header>
<main><div class="wrap">
  <div class="meta" id="meta"></div>
  <div class="changes" id="changes"></div>
  <div id="law"></div>
</div></main>
<script>
const DATA = {payload};
let active = DATA.snapshots.length - 1;
const esc = s => s.replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[c]);

function render() {{
  const snap = DATA.snapshots[active];
  document.getElementById('title').textContent = DATA.title || DATA.base_id;
  document.getElementById('baseid').textContent = DATA.base_id;

  document.getElementById('dates').innerHTML = DATA.snapshots.map((s, i) =>
    `<button aria-pressed="${{i === active}}" onclick="pick(${{i}})">${{s.date}}</button>`).join('');

  document.getElementById('meta').textContent =
    `Loven slik den lød ${{snap.date}} — ${{snap.applied.length}} endringslov(er) anvendt, ${{snap.n_ops}} operasjoner.`;

  const box = document.getElementById('changes');
  if (!snap.changes.length) {{
    box.innerHTML = active === 0
      ? '<h2>Endringer</h2><div class="none">Opprinnelig tekst — utgangspunktet for avspillingen.</div>'
      : '<h2>Endringer</h2><div class="none">Ingen tekstendringer siden forrige dato.</div>';
  }} else {{
    box.innerHTML = '<h2>Endringer siden ' + DATA.snapshots[active - 1].date + '</h2>' +
      snap.changes.map(c => `<div class="chg ${{c.op}}">${{esc(c.text)}}</div>`).join('');
  }}

  document.getElementById('law').innerHTML = snap.blocks.map(b => {{
    if (b.type === 'chapter')
      return `<div class="chapter">Kapittel ${{esc(b.label)}}. ${{esc(b.heading)}}</div>`;
    const paras = b.paras.map(p =>
      `<p class="para">${{p.label ? `<span class="lbl">${{esc(p.label)}}</span>` : ''}}${{esc(p.text)}}</p>`
    ).join('');
    return `<div class="section"><span class="secnum">§ ${{esc(b.label)}}.</span> ` +
           `<span class="sechead">${{esc(b.heading)}}</span>${{paras}}</div>`;
  }}).join('');
}}
function pick(i) {{ active = i; render(); window.scrollTo(0, 0); }}
render();
</script></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_id", help="e.g. no/lov/2020-05-07-38")
    ap.add_argument("--date", action="append", dest="dates",
                    help="repeatable, YYYY-MM-DD; omit to use the law's own change dates")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    dates = sorted(args.dates) if args.dates else amendment_dates(args.base_id)
    if not dates:
        raise SystemExit(f"no dated amendments found for {args.base_id}; pass --date explicitly")
    data = build_snapshots(args.base_id, dates)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(data), encoding="utf-8")

    print(f"wrote {args.out}")
    for snap in data["snapshots"]:
        print(f"  {snap['date']}: {len(snap['blocks'])} blocks, {len(snap['changes'])} changed lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
