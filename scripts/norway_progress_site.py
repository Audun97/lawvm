#!/usr/bin/env python3
"""Build the tailnet-only Norway progress dashboard (static HTML, inline SVG).

Reads the findings ledger, git history and the kringkastingsloven witness
artifacts under .tmp/w97 and .tmp/w87, and writes index.html + data.json to
--out (default ~/serveradmin/public-lawvm, served by lawvm-static.service).

Live inputs (read every run):
  notes/NORWAY_VERIFY_FINDINGS_LEDGER.md   scoreboard table, work-queue item status
  .tmp/w97/verify_glm_full*.json           full-chain witness (per-section rows)
  .tmp/w97/verify_glm*.json                as-of 2000-12-31 witness
  .tmp/w97/verify_glm_full_head.log        replay status / acts applied / ops
  .tmp/w97/kk_chains.json                  the 75 sections and their amendment chains
  .tmp/w97/ladder.json                     evidence-ladder classes per act
  git log                                  commits per day

Curated inputs (numbers quoted from the ledger changelog; extend by hand):
  WITNESS_HISTORY, SCOREBOARD_EXTRA, OCR_CHANNELS, ITEMS
"""
from __future__ import annotations

import collections
import datetime as dt
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "notes" / "NORWAY_VERIFY_FINDINGS_LEDGER.md"
W97 = ROOT / ".tmp" / "w97"
W87 = ROOT / ".tmp" / "w87"

# ---------------------------------------------------------------- curated data
# Zero-divergence sections of kringkastingsloven (75 sections) per landing.
# full = full chain to 2026 vs today's consolidation; asof2000 = pre-2001 chain
# only vs today's consolidation (its ceiling is the 13 OCR-only sections);
# rows = divergence rows on the full chain. Sources: ledger changelog entries.
WITNESS_HISTORY = [
    ("W-91", "2026-08-25", 28, 11, None, "evidence ladder, segmenter, first end-to-end receipt"),
    ("W-98", "2026-08-25", 31, 13, None, "nine pre-2001 lead gaps lowered"),
    ("W-99", "2026-09-05", 32, 14, 122, "omnibus hosts carved, two lead grammars"),
    ("W-100", "2026-09-05", 52, 14, 68, "section-scoped commencement lane"),
    ("W-101", "2026-09-06", 61, 14, 29, "structured chapter address (kap5A)"),
    ("W-102", "2026-09-06", 62, 14, 28, "ledd-precise section grants"),
    ("W-103", "2026-09-06", 62, 14, 28, "print-era lane promoted: fixture + tests pin 62/75"),
    ("W-104", "2026-09-11", 63, 14, 26, "inline addressed word substitution (2004 Medietilsynet act); § 4-6 closes"),
]
# Scoreboard rows the ledger records in prose after its table ended.
SCOREBOARD_EXTRA = [
    ("2026-08-17, after W-84 (75 candidates)", 30, 45, 0),
    ("2026-08-18, after W-86 (75 candidates)", 30, 45, 0),
    ("2026-09-06, after W-102 (82 candidates)", 30, 52, 0),
]
# Second-channel word agreement against NB ALTO over the pilot pages.
OCR_CHANNELS = [
    ("EasyOCR", 85.4, 36.7, "W-88"),
    ("NorPrint (Transkribus)", 94.4, 64.2, "W-89"),
    ("tesseract 5.5 nor", 95.8, 72.4, "W-88 take 2"),
    ("GLM-OCR 0.9B", 96.5, None, "W-90, proposal-only"),
]
LADDER_SHARE = [("A", 72.7), ("A+B", 87.2), ("A+B+C", 97.1), ("R", 2.8)]

ITEMS = {
    87: ("W-81", "2026-08-20", "blocked", "Pre-2001 format probe re-chartered: no Lovdata pre-2001 dataset exists; born-digital corroboration only by agreement."),
    88: ("W-82", "2026-08-17", "done", "Own-text fallback payload reach: 35 declared ops lower with real payloads."),
    89: ("W-83", "2026-08-17", "done", "Klimaloven audit: the 'Lovdata defect' was a superseded (utgått) announcement."),
    90: ("W-84", "2026-08-17", "done", "Beriktiget/utgått correction lane; first verdict-column movement (30/45/0)."),
    91: ("W-85", "2026-08-18", "done", "Re-sanctioning supersession family withdrawn behind a bilateral prose gate."),
    92: ("W-86", "2026-08-18", "done", "2026-08-14 capture re-pin; scoreboard conserved row-for-row."),
    93: ("W-87", "2026-08-20", "probe", "Pilot law chosen by measurement: kringkastingsloven 1992-12-04-127; all 14 print-era acts located on NB."),
    94: ("W-88", "2026-08-20", "probe", "Two-channel agreement: EasyOCR inadequate; tesseract nor 95.8% words. Qualified go."),
    95: ("W-89", "2026-08-23", "probe", "NorPrint third channel: modest lift, hallucinated punctuation, ceiling not broken."),
    96: ("W-90", "2026-08-24", "probe", "GLM-OCR local proposal channel: 96.5% words but silent word fusion, so never certifying."),
    97: ("W-91", "2026-08-25", "probe", "Evidence ladder A/B/C/R, print-era segmenter, first end-to-end replay through the real pipeline."),
    98: ("W-98", "2026-08-25", "done", "Nine pre-2001 lead grammar gaps lowered (corpus refusals -431)."),
    99: ("W-99", "2026-09-05", "done", "Omnibus hosts carved into the witness; period-less citations and address-after-citation leads."),
    100: ("W-100", "2026-09-05", "done", "Section-scoped commencement lane; seven contingent acts dated below binding level."),
    101: ("W-101", "2026-09-06", "done", "Structured chapter address kap<label>; kringkastingsloven chapter 5 A closes."),
    102: ("W-102", "2026-09-06", "done", "Ledd-precise section grants; § 2-3 closes; ledd-depth occupied-destination refusal."),
    103: ("W-103", "2026-09-06", "done", "Print-era lane promoted to src/lawvm/norway/print_era.py; 14-act fixture with ladder provenance; tests pin 14/75 source-absent and 62/75 full chain."),
    104: ("W-104", "2026-09-11", "done", "Inline addressed word substitution in the unstructured lane (family 2: the 2004 Medietilsynet act); term-first and address-first shapes, W-102 qualifier grammar widened to several ledd groups."),
}

NEXT_STEPS = [
    ("Make the ladder itself reproducible",
     "W-103 committed the ladder's output with every candidate, but ladder.py and the four OCR channel outputs (41 MB) "
     "still live under .tmp/w87. Decide what of the per-page engine output is worth committing, or record the exact "
     "engine versions and re-derivation recipe so the classes can be regenerated."),
    ("Close the 12 divergent witness sections by amending act",
     "Family 1, the 2005 act (2005-06-17-98): §§ 10-1, 10-4, 10-5, 10-6 and § 10-3 ledd 2 — seven unmatched leads and the § 10-4/10-5 renumber, "
     "with the 2007 and 2015 ops cascading into target-not-found. Family 3, the 2019 act (2019-06-21-58): §§ 6-1a, 7-1 unmatched leads. "
     "Family 4, pre-2001 OCR leads: § 2-1 ledd relabels (which also block the 2004 substitution's three ops: term absent at the addressed ledd) and the § 4-4 straddle. "
     "§ 8-4 and parts of §§ 10-3/10-4 wait on the 2025 acts (step 3). §§ 9-2, 9-3 need a typed dash policy. Family 2 (the 2004 Medietilsynet act) closed § 4-6 in W-104."),
    ("Date the last contingent act",
     "no/lovtid/2025-04-25-12 is still skipped whole and three per-op skips remain. Once dated, replay_status can leave blocked_contingent."),
    ("Prove the double-application class",
     "W-102 refuses ledd-depth renumbers onto occupied slots but cannot prove a base edition already carries the amendment. "
     "The recorded spike: compare the base edition's date against the op's effective date (4,078 hazard writes in the W-72 census)."),
    ("Lift the OCR ceiling where it is cheap",
     "A tesstrain fine-tune with § in the charset converts most C lines (146) to A lines; the 40 R lines are almost all § N-N address leads."),
    ("Second pilot law, then the [1997, 2000] window",
     "Reuse the manifest tooling from W-87 for a second law with a different chain shape, then build the annual-register "
     "completeness manifest (Stage 1) and the back-matter rettelser lane before widening to the whole window."),
]


# ---------------------------------------------------------------- live inputs
def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False).stdout


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def parse_scoreboard(text: str) -> list[tuple[str, int, int, int]]:
    rows = []
    sec = text.split("## 2. Scoreboard", 1)[1].split("## 3.", 1)[0]
    for line in sec.splitlines():
        m = re.match(r"^\|\s*\**(.+?)\**\s*\|\s*\**(\d+)\**\s*\|\s*\**(\d+)\**\s*\|\s*\**(\d+)\**\s*\|$", line.strip())
        if m and not m.group(1).startswith("as-of"):
            rows.append((m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))))
    return rows + SCOREBOARD_EXTRA


def parse_items(text: str) -> list[dict]:
    body = text.split("## 4. Work Queue", 1)[1].split("## 5.", 1)[0]
    items = []
    for m in re.finditer(r"^(\d+)\. \*\*(W-[0-9a-z]+) \((.*?)\):\*\*([^\n]*(?:\n[^\n]*){0,2})", body, flags=re.M | re.S):
        head = re.sub(r"\s+", " ", m.group(4)[:200]).strip()
        status = "done" if re.match(r"(?i)done", head) else "open"
        if re.search(r"(?i)done as a probe", head):
            status = "probe"
        if re.search(r"(?i)^open|blocked", head):
            status = "blocked" if "BLOCKED" in head else "open"
        n = int(m.group(1))
        if n in ITEMS:
            status = ITEMS[n][2]
        items.append({"n": n, "id": m.group(2), "title": re.sub(r"\s+", " ", m.group(3)), "status": status})
    return items


def parse_head_log(path: Path) -> dict:
    out: dict = {}
    if not path.exists():
        return out
    t = path.read_text(encoding="utf-8")
    m = re.search(r"replay_status=(\S+)", t)
    out["replay_status"] = m.group(1) if m else None
    for key in ("scanned", "applied", "contingent"):
        m = re.search(key + r"=\[(.*?)\]", t)
        out[key] = [s.strip(" '") for s in m.group(1).split(",")] if m and m.group(1).strip() else []
    m = re.search(r"ops accepted=(\d+) rejected=(\d+)", t)
    if m:
        out["ops_accepted"], out["ops_rejected"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"n_ops=(\d+)", t)
    out["n_ops"] = int(m.group(1)) if m else None
    m = re.search(r"sections with ZERO divergence rows: (\d+)/(\d+)", t)
    if m:
        out["clean"], out["total"] = int(m.group(1)), int(m.group(2))
    return out


def commits_per_day(since: str = "2026-07-30") -> list[tuple[str, int]]:
    counts = collections.Counter(sh("git", "log", f"--since={since}", "--date=short", "--format=%ad").split())
    if not counts:
        return []
    d0 = dt.date.fromisoformat(min(counts))
    d1 = dt.date.today()
    return [((d0 + dt.timedelta(i)).isoformat(), counts.get((d0 + dt.timedelta(i)).isoformat(), 0)) for i in range((d1 - d0).days + 1)]


def section_states(full, asof, chains) -> list[dict]:
    """One record per kringkastingsloven section with its status on both witnesses."""
    def cls_of(chain: str) -> str:
        yrs = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", chain or "")]
        return "NONE" if not yrs else ("PRE2001" if max(yrs) < 2001 else "POST2001")

    def rows_by_sec(v):
        by: dict[str, list[str]] = collections.defaultdict(list)
        for d in (v or {}).get("divergences", []):
            by[d["sec"].replace(" ", "")].append(d["kind"])
        return by

    full_rows, asof_rows = rows_by_sec(full), rows_by_sec(asof)
    out = []
    for s in chains:
        label = s["sec"].replace("§ ", "").replace(" ", "")
        chap = label.split("-")[0].rstrip("aAbB")
        chap = re.sub(r"[a-zA-Z]$", "", label.split("-")[0]) if "-" in label else "?"

        def status(rows: list[str]) -> str:
            if not rows:
                return "clean"
            if all(r == "MISMATCH:dash-class-only" for r in rows):
                return "dash"
            return "divergent"

        out.append({
            "sec": label, "chapter": chap, "cls": cls_of(s["chain"]),
            "full": status(full_rows.get(label, [])), "full_rows": full_rows.get(label, []),
            "asof2000": status(asof_rows.get(label, [])), "asof_rows": asof_rows.get(label, []),
        })
    return out


# ---------------------------------------------------------------- svg helpers
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def line_chart(series: list[tuple[str, str, list[float | None]]], xlabels: list[str], *, ymax: float,
               w=720, h=280, ylabel="", ytick=None, tips: list[list[str]] | None = None, every=1, R=96) -> str:
    """series: (name, css-var, values). Crosshair tooltip per x."""
    L, T, B = 44, 16, 44
    pw, ph = w - L - R, h - T - B
    n = len(xlabels)
    xs = [L + (pw * i / max(n - 1, 1)) for i in range(n)]
    def y(v: float) -> float:
        return T + ph - (ph * v / ymax)

    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img">']
    ticks = ytick or [round(ymax * k / 4) for k in range(5)]
    for tv in ticks:
        parts.append(f'<line class="grid" x1="{L}" x2="{w-R}" y1="{y(tv):.1f}" y2="{y(tv):.1f}"/>'
                     f'<text class="tick" x="{L-6}" y="{y(tv)+4:.1f}" text-anchor="end">{tv}</text>')
    parts.append(f'<line class="axis" x1="{L}" x2="{w-R}" y1="{T+ph}" y2="{T+ph}"/>')
    for i, lab in enumerate(xlabels):
        if i % every == 0 or i == n - 1:
            parts.append(f'<text class="tick" x="{xs[i]:.1f}" y="{h-B+16}" text-anchor="middle">{esc(lab)}</text>')
    for name, var, vals in series:
        pts = [(xs[i], y(v)) for i, v in enumerate(vals) if v is not None]
        d = " ".join(f"{'M' if k == 0 else 'L'}{px:.1f},{py:.1f}" for k, (px, py) in enumerate(pts))
        parts.append(f'<path class="series" style="stroke:var({var})" d="{d}"/>')
        for px, py in pts:
            parts.append(f'<circle class="dot" style="fill:var({var})" cx="{px:.1f}" cy="{py:.1f}" r="4"/>')
        if pts:
            px, py = pts[-1]
            parts.append(f'<text class="dlabel" x="{px+8:.1f}" y="{py+4:.1f}">{esc(name)}</text>')
    for i in range(n):
        tip = "<br>".join(tips[i]) if tips else esc(xlabels[i])
        x0 = xs[i] - pw / max(n - 1, 1) / 2 if i else L
        x1 = xs[i] + pw / max(n - 1, 1) / 2 if i < n - 1 else w - R
        parts.append(f'<rect class="hit" x="{x0:.1f}" y="{T}" width="{x1-x0:.1f}" height="{ph}" data-tip="{esc(tip)}"/>')
    if ylabel:
        parts.append(f'<text class="tick" x="{L}" y="{T-4}">{esc(ylabel)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(labels: list[str], values: list[float], *, ymax: float, w=720, h=240, var="--seq-500",
              tips: list[str] | None = None, fmt=lambda v: f"{v:g}", every=1) -> str:
    L, R, T, B = 44, 16, 16, 44
    pw, ph = w - L - R, h - T - B
    n = len(labels)
    bw = pw / n
    def y(v: float) -> float:
        return T + ph - (ph * v / ymax)

    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img">']
    for k in range(5):
        tv = ymax * k / 4
        parts.append(f'<line class="grid" x1="{L}" x2="{w-R}" y1="{y(tv):.1f}" y2="{y(tv):.1f}"/>'
                     f'<text class="tick" x="{L-6}" y="{y(tv)+4:.1f}" text-anchor="end">{tv:g}</text>')
    parts.append(f'<line class="axis" x1="{L}" x2="{w-R}" y1="{T+ph}" y2="{T+ph}"/>')
    for i, (lab, v) in enumerate(zip(labels, values, strict=True)):
        x0 = L + bw * i + 1
        wd = max(bw - 2, 1)
        top = y(v)
        tip = tips[i] if tips else f"{esc(lab)}: {fmt(v)}"
        if v > 0:
            parts.append(f'<path class="bar" style="fill:var({var})" d="M{x0:.1f},{T+ph} V{top+3:.1f} a3,3 0 0 1 3,-3 H{x0+wd-3:.1f} a3,3 0 0 1 3,3 V{T+ph} Z"/>')
        parts.append(f'<rect class="hit" x="{x0:.1f}" y="{T}" width="{wd:.1f}" height="{ph}" data-tip="{esc(tip)}"/>')
        if i % every == 0:
            parts.append(f'<text class="tick" x="{x0+wd/2:.1f}" y="{h-B+16}" text-anchor="middle">{esc(lab)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def hbar_chart(labels: list[str], values: list[float], *, xmax=100, w=720, rowh=28, var="--seq-500",
               tips: list[str] | None = None, fmt=lambda v: f"{v:g}") -> str:
    L, R, T, B = 150, 56, 8, 8
    n = len(labels)
    h = T + B + rowh * n
    pw = w - L - R
    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img">']
    for i, (lab, v) in enumerate(zip(labels, values, strict=True)):
        y0 = T + rowh * i + 5
        bh = rowh - 10
        x1 = L + pw * v / xmax
        parts.append(f'<text class="tick" x="{L-8}" y="{y0+bh/2+4}" text-anchor="end">{esc(lab)}</text>')
        parts.append(f'<path class="bar" style="fill:var({var})" d="M{L},{y0} H{x1-3:.1f} a3,3 0 0 1 3,3 V{y0+bh-3} a3,3 0 0 1 -3,3 H{L} Z"/>')
        parts.append(f'<text class="dlabel" x="{x1+6:.1f}" y="{y0+bh/2+4}">{fmt(v)}</text>')
        tip = tips[i] if tips else f"{esc(lab)}: {fmt(v)}"
        parts.append(f'<rect class="hit" x="{L}" y="{y0-4}" width="{pw}" height="{rowh}" data-tip="{esc(tip)}"/>')
    parts.append("</svg>")
    return "".join(parts)


def stacked_hbar(labels: list[str], stacks: list[list[float]], names: list[str], vars_: list[str], *, w=720, rowh=24) -> str:
    L, R, T, B = 130, 16, 8, 8
    n = len(labels)
    h = T + B + rowh * n
    pw = w - L - R
    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img">']
    for i, (lab, vals) in enumerate(zip(labels, stacks, strict=True)):
        total = sum(vals) or 1
        y0 = T + rowh * i + 4
        bh = rowh - 8
        x = L
        parts.append(f'<text class="tick" x="{L-8}" y="{y0+bh/2+4}" text-anchor="end">{esc(lab)}</text>')
        for v, nm, var in zip(vals, names, vars_, strict=True):
            wd = pw * v / total
            if wd > 0:
                parts.append(f'<rect class="seg" style="fill:var({var})" x="{x:.1f}" y="{y0}" width="{max(wd-2,0):.1f}" height="{bh}" rx="2" '
                             f'data-tip="{esc(lab)}<br>{esc(nm)}: {v:g} lines ({100*v/total:.1f}%)"/>')
            x += wd
    parts.append("</svg>")
    return "".join(parts)


def section_grid(states: list[dict], key: str) -> str:
    chapters = collections.OrderedDict()
    for s in states:
        chapters.setdefault(s["chapter"], []).append(s)
    out = ['<div class="secgrid">']
    for chap, secs in chapters.items():
        out.append(f'<div class="chap"><div class="chaplabel">Kap. {esc(chap)}</div><div class="cells">')
        for s in secs:
            st = s[key]
            rows = s["full_rows"] if key == "full" else s["asof_rows"]
            kinds = ", ".join(f"{k} ×{v}" for k, v in collections.Counter(rows).items()) or "byte-identical with today's consolidation"
            tip = f"§ {esc(s['sec'])} · chain {esc(s['cls'])}<br>{esc(kinds)}"
            out.append(f'<div class="cell {st} cls-{s["cls"]}" data-tip="{tip}"><span>{esc(s["sec"])}</span></div>')
        out.append("</div></div>")
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------- page
CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--seq-250:#86b6ef;--seq-400:#3987e5;--seq-500:#256abf;--seq-650:#104281;--neutral:#c3c2b7;
--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--critical:#d03b3b;--goodtext:#006300}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--seq-250:#6da7ec;--seq-400:#3987e5;--seq-500:#5598e7;--seq-650:#86b6ef;--neutral:#52514e;--goodtext:#0ca30c}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 20px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 10px}h3{font-size:15px;margin:18px 0 6px;color:var(--ink2)}
.sub{color:var(--ink2);margin:0 0 20px}.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}.kpi .v{font-size:36px;font-weight:600;line-height:1.1}.kpi .l{color:var(--ink2);font-size:13px}.kpi .d{font-size:13px;color:var(--muted)}.kpi .d.up{color:var(--goodtext)}
.verdict{border-left:4px solid var(--critical);padding-left:14px}.verdict.ok{border-color:var(--good)}
svg.chart{width:100%;height:auto;display:block}.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis);stroke-width:1}.tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.series{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.dot{stroke:var(--surface);stroke-width:2}.dlabel{fill:var(--ink2);font-size:12px}.bar{stroke:none}.seg{stroke:none}
.hit{fill:transparent;cursor:crosshair}.hit:hover{fill:rgba(128,128,128,.08)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--ink2);margin:6px 0 0}.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.secgrid{display:flex;flex-direction:column;gap:6px}.chap{display:flex;align-items:center;gap:10px}.chaplabel{width:64px;font-size:12px;color:var(--muted);text-align:right;flex:none}.cells{display:flex;flex-wrap:wrap;gap:4px}
.cell{width:48px;height:30px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff;cursor:default;font-variant-numeric:tabular-nums}
.cell.clean{background:var(--good)}.cell.dash{background:var(--warn);color:#0b0b0b}.cell.divergent{background:var(--critical)}.cell.cls-PRE2001,.cell.cls-NONE{outline:2px dashed var(--ink2);outline-offset:-3px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--grid);vertical-align:top}th{color:var(--ink2);font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid var(--border)}.pill.done{background:var(--good);color:#fff}.pill.probe{background:var(--seq-400);color:#fff}.pill.blocked{background:var(--serious);color:#0b0b0b}.pill.open{background:var(--neutral)}
details{margin-top:10px}summary{cursor:pointer;color:var(--ink2)}code{font-size:13px;background:var(--grid);padding:1px 4px;border-radius:3px}
ol.next li{margin:8px 0}ol.next b{display:block}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:6px 9px;border-radius:6px;font-size:12px;max-width:340px;display:none;z-index:9;line-height:1.35}
footer{color:var(--muted);font-size:12px;margin-top:40px}
"""
JS = """
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{const t=e.target.closest('[data-tip]');if(!t){tip.style.display='none';return}
tip.innerHTML=t.dataset.tip;tip.style.display='block';const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px'});
"""


def kpi(v, label, delta="", up=False) -> str:
    return f'<div class="card kpi"><div class="v">{v}</div><div class="l">{label}</div><div class="d{" up" if up else ""}">{delta}</div></div>'


def build(out: Path) -> dict:
    ledger = LEDGER.read_text(encoding="utf-8")
    scoreboard = parse_scoreboard(ledger)
    items = parse_items(ledger)
    chains = load_json(W97 / "kk_chains.json") or []
    full = load_json(W97 / "verify_glm_full.json")
    asof = load_json(W97 / "verify_glm.json")
    ladder = load_json(W97 / "ladder.json") or {"totals": {}, "per_act": {}}
    head = parse_head_log(W97 / "verify_glm_full_head.log")
    head_src = "fresh run at HEAD"
    if not head.get("scanned"):
        for cand in (
            ROOT / ".tmp" / "w104" / "verify_glm_full.log",
            ROOT / ".tmp" / "w101" / "verify_glm_full.log",
            W97 / "verify_glm_full_w98.log",
        ):
            head = parse_head_log(cand)
            if head.get("scanned"):
                head_src = f"stored run {cand.relative_to(ROOT)}"
                break
    head2000 = parse_head_log(W97 / "verify_glm_2000_head.log")
    states = section_states(full, asof, chains)
    commits = commits_per_day()
    git_head = sh("git", "log", "-1", "--format=%h %ad %s", "--date=short").strip()

    n_total = len(states) or 75
    clean_full = sum(s["full"] == "clean" for s in states)
    dash_full = sum(s["full"] == "dash" for s in states)
    div_full = n_total - clean_full - dash_full
    clean_2000 = sum(s["asof2000"] == "clean" for s in states)
    ocr_only = [s for s in states if s["cls"] != "POST2001"]
    ocr_clean = sum(s["asof2000"] == "clean" for s in ocr_only)
    ocr_dash = sum(s["asof2000"] == "dash" for s in ocr_only)
    rows_full = len((full or {}).get("divergences", []))
    done = sum(i["status"] == "done" for i in items)
    probes = sum(i["status"] == "probe" for i in items)
    sb_last = scoreboard[-1]

    scanned, applied = head.get("scanned", []), head.get("applied", [])
    skipped_whole = [a for a in scanned if a not in applied]
    replay_status = head.get("replay_status") or (full or {}).get("status", "?")
    fully = replay_status == "replayed" and div_full == 0 and dash_full == 0
    head_note = f" Replay figures from the {head_src}."
    if head.get("clean") is not None and head["clean"] != clean_full:
        head_note += f" That run reports {head['clean']}/{head['total']} clean sections; the section grid below is from the stored W-102 artifact."

    # ---- charts
    wl = [w[0] for w in WITNESS_HISTORY] + ["HEAD"]
    full_vals = [w[2] for w in WITNESS_HISTORY] + [head.get("clean", clean_full)]
    asof_vals = [w[3] for w in WITNESS_HISTORY] + [head2000.get("clean", clean_2000)]
    wtips = [[f"<b>{w[0]}</b> {w[1]}", esc(w[5]), f"full chain {w[2]}/75 · as-of 2000 {w[3]}/75"] for w in WITNESS_HISTORY] + \
            [["<b>HEAD</b> " + esc(git_head[:7]), f"full chain {full_vals[-1]}/75 · as-of 2000 {asof_vals[-1]}/75"]]
    witness_chart = line_chart([("full chain to 2026", "--s1", full_vals), ("pre-2001 chain only", "--s2", asof_vals)],
                               wl, ymax=75, ytick=[0, 25, 50, 75], tips=wtips, w=520, h=260, R=150)
    rows_hist = [(w[0], w[4]) for w in WITNESS_HISTORY if w[4] is not None] + [("HEAD", rows_full)]
    rows_chart = bar_chart([r[0] for r in rows_hist], [r[1] for r in rows_hist], ymax=140, h=260, w=520,
                           tips=[f"{r[0]}: {r[1]} divergence rows" for r in rows_hist])

    ocr_chart = hbar_chart([c[0] for c in OCR_CHANNELS], [c[1] for c in OCR_CHANNELS], fmt=lambda v: f"{v:.1f}%", w=520,
                           tips=[f"{esc(c[0])} vs NB ALTO ({esc(c[3])})<br>words {c[1]}%" + (f" · lines {c[2]}%" if c[2] else "") for c in OCR_CHANNELS])
    ladder_chart = hbar_chart([l[0] for l in LADDER_SHARE], [l[1] for l in LADDER_SHARE], fmt=lambda v: f"{v:.1f}%", w=520,
                              tips=["A: ABBYY = tesseract", "A+B: any two print engines agree", "A+B+C: GLM-OCR agrees with one print engine", "R: no two channels agree (refusal, candidates attached)"])
    acts = list(ladder.get("per_act", {}).items())
    stack_chart = stacked_hbar([a for a, _ in acts], [[v.get(k, 0) for k in "ABCR"] for _, v in acts], ["A", "B", "C", "R"],
                               ["--seq-650", "--seq-500", "--seq-250", "--neutral"])

    sb_labels = [re.sub(r".*?(W-\d+|batch \d+|snapshot|scan default).*", r"\1", r[0]) for r in scoreboard]
    sb_labels = [l if len(l) < 14 else l[:12] for l in sb_labels]
    sb_chart = line_chart([("consistent", "--s3", [r[1] for r in scoreboard]), ("divergent", "--s2", [r[2] for r in scoreboard]),
                           ("candidates", "--neutral", [r[1] + r[2] + r[3] for r in scoreboard])],
                          sb_labels, ymax=90, ytick=[0, 30, 60, 90], ylabel="laws", h=300, every=2,
                          tips=[[esc(r[0]), f"consistent {r[1]} · divergent {r[2]} · error {r[3]}"] for r in scoreboard])
    commit_chart = bar_chart([c[0][5:] for c in commits], [c[1] for c in commits], ymax=max([c[1] for c in commits] + [1]), h=180, every=7,
                             tips=[f"{c[0]}: {c[1]} commits" for c in commits])

    # ---- html
    def sec_rows(key):
        return "".join(f"<tr><td>§ {esc(s['sec'])}</td><td>{esc(s['cls'])}</td><td>{esc(s[key])}</td><td>{esc(', '.join(s['full_rows'] if key=='full' else s['asof_rows']))}</td></tr>" for s in states)

    items_rows = "".join(
        f"<tr><td class=n>{i['n']}</td><td>{esc(i['id'])}</td><td>{esc(ITEMS.get(i['n'], ('', '', '', ''))[1])}</td>"
        f"<td><span class='pill {esc(ITEMS.get(i['n'], ('', '', i['status'], ''))[2])}'>{esc(ITEMS.get(i['n'], ('', '', i['status'], ''))[2])}</span></td>"
        f"<td>{esc(i['title'])}<br><span style='color:var(--ink2)'>{esc(ITEMS.get(i['n'], ('', '', '', ''))[3])}</span></td></tr>"
        for i in items if i["n"] >= 87)
    next_html = "".join(f"<li><b>{esc(t)}</b>{esc(b)}</li>" for t, b in NEXT_STEPS)
    verdict_cls = "ok" if fully else ""
    verdict = ("Yes: replayed end to end with zero divergence." if fully else
               f"Not yet. Replay status is <code>{esc(replay_status)}</code>: {len(applied)} of {len(scanned)} amending acts applied "
               f"({len(skipped_whole)} skipped whole as contingent: {esc(', '.join(skipped_whole) or 'none')}), "
               f"{head.get('ops_accepted', '?')} ops accepted / {head.get('ops_rejected', '?')} rejected, and {div_full} of {n_total} sections still diverge "
               f"({rows_full} rows) plus {dash_full} dash-class-only. The pre-2001 sources are OCR witness artifacts under <code>.tmp/</code>, not archived corpus members.")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>lawvm · Norway progress</title><style>{CSS}</style></head><body><div id="tip"></div><main>
<h1>lawvm · Norway frontend progress</h1>
<p class="sub">Branch <code>audun/norway-receipt-spine</code> · HEAD {esc(git_head)} · built {dt.datetime.now():%Y-%m-%d %H:%M}</p>

<div class="kpis">
{kpi(f"{clean_full}<span style='font-size:18px;color:var(--muted)'>/{n_total}</span>", "kringkastingsloven sections byte-identical with today's consolidation, full chain 1992→2026", f"from {WITNESS_HISTORY[0][2]} at W-91 (2026-08-25)", up=True)}
{kpi(rows_full, "divergence rows left on the full chain", "from 122 at W-99", up=True)}
{kpi(f"{ocr_clean}<span style='font-size:18px;color:var(--muted)'>/{len(ocr_only)}</span>", "OCR-only sections (no post-2001 act) byte-equal", f"{ocr_dash} dash-class-only, {len(ocr_only)-ocr_clean-ocr_dash} blocked")}
{kpi(f"{sb_last[1]}<span style='font-size:18px;color:var(--muted)'>/{sb_last[1]+sb_last[2]}</span>", "post-2001 corpus laws consistent (no-verify-scan candidates)", esc(sb_last[0]))}
{kpi(f"{done}<span style='font-size:18px;color:var(--muted)'>+{probes}</span>", "work-queue items done + probes", f"of {len(items)} chartered (W-1 … W-102)")}
</div>

<h2>Is kringkastingsloven fully replayable?</h2>
<div class="card verdict {verdict_cls}"><p style="margin:0">{verdict}{head_note}</p></div>

<h2>Kringkastingsloven (lov 1992-12-04-127): the 75 sections today</h2>
<div class="grid2">
<div class="card"><h3>Full chain: 1992 facsimile + 14 print-era acts + 20 post-2001 acts, compared with today's consolidation</h3>{section_grid(states, "full")}</div>
<div class="card"><h3>Pre-2001 chain only (as-of 2000-12-31), compared with today's consolidation</h3>{section_grid(states, "asof2000")}
<p style="color:var(--ink2);font-size:13px">Only the dashed cells (no post-2001 act in the chain) can match here; solid cells diverge by construction because their later amendments are excluded.</p></div>
</div>
<div class="legend"><span><i style="background:var(--good)"></i>✓ byte-identical</span><span><i style="background:var(--warn)"></i>– dash class only (–/—/- differ)</span><span><i style="background:var(--critical)"></i>✕ divergent rows</span><span><i style="border:2px dashed var(--ink2);background:none"></i>dashed outline: no post-2001 act in the section's chain (OCR-only)</span></div>
<details><summary>Table view: sections</summary><table><tr><th>section</th><th>chain class</th><th>full chain</th><th>rows</th></tr>{sec_rows("full")}</table></details>

<h2>Pilot progression, landing by landing</h2>
<div class="grid2">
<div class="card"><h3>Zero-divergence sections of 75</h3>{witness_chart}
<div class="legend"><span><i style="background:var(--s1)"></i>full chain to 2026</span><span><i style="background:var(--s2)"></i>pre-2001 chain only</span></div></div>
<div class="card"><h3>Divergence rows on the full chain</h3>{rows_chart}</div>
</div>

<h2>OCR evidence over the 36 pilot pages (NB facsimile, 1992–2000)</h2>
<div class="grid2">
<div class="card"><h3>Second-channel word agreement with NB ALTO (ABBYY FineReader 8.1)</h3>{ocr_chart}</div>
<div class="card"><h3>Evidence ladder: share of {sum(ladder.get("totals", {}).values()) or 1571} body lines certified</h3>{ladder_chart}
<p style="color:var(--ink2);font-size:13px">A/B/C lines land as certified text; R lines land with candidates and the GLM proposal drives the address lead.</p></div>
</div>
<div class="card" style="margin-top:16px"><h3>Ladder class per act (founding act + 13 amending acts, lines)</h3>{stack_chart}
<div class="legend"><span><i style="background:var(--seq-650)"></i>A ABBYY = tesseract</span><span><i style="background:var(--seq-500)"></i>B two print engines</span><span><i style="background:var(--seq-250)"></i>C GLM + one print engine</span><span><i style="background:var(--neutral)"></i>R refused</span></div></div>

<h2>Post-2001 corpus: the no-verify-scan scoreboard</h2>
<div class="card">{sb_chart}
<div class="legend"><span><i style="background:var(--s3)"></i>consistent</span><span><i style="background:var(--s2)"></i>divergent</span><span><i style="background:var(--neutral)"></i>candidates</span></div>
<p style="color:var(--ink2);font-size:13px">Candidate laws grow as commencement routes open (each entrant arrives divergent, an honest exposure), so the divergent line rising is coverage, not regression. Rows are ledger scoreboard entries in order; error column has been zero throughout.</p>
<details><summary>Table view: scoreboard</summary><table><tr><th>row</th><th>consistent</th><th>divergent</th><th>error</th></tr>{"".join(f"<tr><td>{esc(r[0])}</td><td class=n>{r[1]}</td><td class=n>{r[2]}</td><td class=n>{r[3]}</td></tr>" for r in scoreboard)}</table></details></div>

<h2>Commits per day on this branch since the ledger opened (2026-07-30)</h2>
<div class="card">{commit_chart}</div>

<h2>The pre-2001 arc: items 87–102</h2>
<div class="card"><table><tr><th>#</th><th>id</th><th>date</th><th>status</th><th>what</th></tr>{items_rows}</table></div>

<h2>Logical next steps</h2>
<div class="card"><ol class="next">{next_html}</ol></div>

<footer>Generated by <code>scripts/norway_progress_site.py</code> from the findings ledger, git history and the witness artifacts in <code>.tmp/w97</code>. Tailnet-only.</footer>
</main><script>{JS}</script></body></html>"""

    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    data = {"built": dt.datetime.now().isoformat(timespec="seconds"), "head": git_head, "witness_history": WITNESS_HISTORY,
            "head_run": head, "head_run_2000": head2000, "scoreboard": scoreboard, "sections": states, "items": items,
            "ladder_totals": ladder.get("totals"), "commits_per_day": commits}
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"clean_full": clean_full, "div_full": div_full, "dash_full": dash_full, "rows": rows_full, "replay_status": replay_status,
            "applied": f"{len(applied)}/{len(scanned)}", "items_done": done, "probes": probes, "out": str(out)}


if __name__ == "__main__":
    out = Path(sys.argv[sys.argv.index("--out") + 1]).expanduser() if "--out" in sys.argv else Path("~/serveradmin/public-lawvm").expanduser()
    print(json.dumps(build(out), indent=1))
