"""F-10 step (b): why is each declared-but-unbound amendment target unbound, and
which single parse fix would recover the most FIELD-RELEVANT bindings?

Batch 02 made the gap visible: 1245 acts carry
``no_amendment_index_declared_target_unbound`` over 4088 declared targets the
index never bound. That count is a total, not a work plan. This probe splits it
by cause and weights each cause by payoff, so the next batch is chosen by
measurement rather than by which family is easiest to describe.

Causes are read off the act's own parse diagnostics, which the engine already
emits per lead (8726 unstructured-lead-unmatched, 3710 lead-base-unresolved,
...). Joining them to the unbound targets of the same act answers "if this
parse family were fixed, which bindings could it possibly recover".

FIELD-RELEVANT means the recovered binding could move the verify scan today:
the amending act is ``dated`` (not blocked on commencement) AND the target law
has consolidated text to compare against. Everything else is real but pays
nothing until W-7.

Read-only. Writes JSON under .tmp/.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.sources import (
    load_no_amendment_artifact_bytes,
    load_no_current_law_ids,
    resolve_no_source_path,
)

OUT = Path(__file__).resolve().parents[2] / ".tmp" / "no_unbound_binding_causes.json"
UNBOUND_RULE = "no_amendment_index_declared_target_unbound"
LOCATOR_RE = re.compile(r"^no://lovtid/(?P<id>[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+)/")
# a declared id with no trailing number resolves to nothing in the corpus (F-10 family 3)
NON_RESOLVING_RE = re.compile(r"^no/lov/\d{4}-\d{2}-\d{2}$")
# The bulk-rename lead (F-10 family 1). The trailing substitution verb and colon
# are NOT optional garnish: without them this matches "Endringer i følgende
# lover:", a table-of-contents heading carried by nearly every omnibus act, and
# the family inflates from 53 acts to 579 — which is how the first run of this
# probe attributed 83% of the field-relevant gap to the wrong cause.
BULK_LEAD = re.compile(
    r"I\s+følg(?:jande|ende)\s+"
    r"(?:lovføresegner|lovbestemmelser|lovbestemmelsene|lover|lovar|føresegner"
    r"|bestemmelser|paragrafar|paragrafer|føresegnene|bestemmelsene)"
    r"[^:]{0,300}?"
    r"(?:endra|endres|endrast|erstattes|erstatta|byttes|bytta|lyde|gjerast|gjøres)"
    r"[^:]{0,120}:",
    re.IGNORECASE | re.DOTALL,
)


def act_from_locator(locator: str) -> str:
    m = LOCATOR_RE.match(locator or "")
    return f"no/lovtid/{m.group('id')}" if m else ""


def main() -> int:
    d = resolve_no_source_path(None)
    idx = build_no_amendment_index(d)
    by_id = {e.source_id: e for e in idx.entries}
    current = set(load_no_current_law_ids(d))

    # act -> Counter(parse rule -> n), from the per-lead diagnostics
    parse_rules: dict[str, Counter[str]] = defaultdict(Counter)
    for row in idx.diagnostics:
        rule = str(row.get("rule_id") or row.get("kind") or "")
        if not rule.startswith("no_parse_"):
            continue
        act = act_from_locator(str(row.get("locator") or ""))
        if act:
            parse_rules[act][rule] += 1

    unbound_rows = [
        r for r in idx.diagnostics if (r.get("rule_id") or r.get("kind")) == UNBOUND_RULE
    ]
    print(f"acts with unbound declared targets: {len(unbound_rows)}")

    # which acts use the bulk-rename grammar (F-10 family 1)
    bulk: set[str] = set()
    for row in unbound_rows:
        act = str(row.get("source_id") or "")
        e = by_id.get(act)
        if e is None:
            continue
        raw = load_no_amendment_artifact_bytes(act, e.archive, e.member_name, d)
        if raw and BULK_LEAD.search(raw.decode("utf-8", errors="replace")):
            bulk.add(act)
    print(f"of those, bulk-rename acts: {len(bulk)}")

    per_cause: Counter[str] = Counter()
    per_cause_field: Counter[str] = Counter()
    per_cause_acts: dict[str, set[str]] = defaultdict(set)
    rows = []
    total = field_total = 0

    for row in unbound_rows:
        act = str(row.get("source_id") or "")
        e = by_id.get(act)
        ids = list(row.get("unbound_target_ids") or row.get("unbound_ids") or ())
        dated = bool(e and e.effective_status == "dated")
        rules = parse_rules.get(act, Counter())
        dominant = rules.most_common(1)[0][0] if rules else "<no parse diagnostic on this act>"

        for target in ids:
            total += 1
            relevant = dated and target in current
            field_total += relevant
            if NON_RESOLVING_RE.match(target):
                cause = "family3:declared id resolves to no corpus law"
            elif act in bulk:
                cause = "family1:bulk-rename list grammar"
            else:
                cause = f"family2:{dominant}"
            per_cause[cause] += 1
            per_cause_field[cause] += relevant
            per_cause_acts[cause].add(act)

        rows.append({
            "act": act, "status": e.effective_status if e else "?",
            "declared": len(e.declared_target_ids) if e else 0,
            "bound": len(e.base_ids) if e else 0,
            "unbound": len(ids), "bulk": act in bulk,
            "parse_rules": dict(rules),
        })

    print(f"\nunbound declared bindings total : {total}")
    print(f"  ...field-relevant (dated + consolidated text) : {field_total}")

    print("\n=== cause of unbound binding, ranked by FIELD-RELEVANT recoverable ===")
    print(f"{'field':>7}{'total':>8}{'acts':>7}  cause")
    for cause, n in sorted(per_cause.items(), key=lambda kv: -per_cause_field[kv[0]]):
        print(f"{per_cause_field[cause]:>7}{n:>8}{len(per_cause_acts[cause]):>7}  {cause}")

    print("\n=== the same, ranked by TOTAL (post-W-7 view) ===")
    for cause, n in per_cause.most_common():
        print(f"{n:>8}{per_cause_field[cause]:>7}  {cause}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump({"rows": rows,
                   "byCause": {k: {"total": v, "field": per_cause_field[k],
                                   "acts": len(per_cause_acts[k])}
                               for k, v in per_cause.items()},
                   "total": total, "fieldTotal": field_total}, fh, ensure_ascii=False, indent=1)
    print(f"\nfull rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
