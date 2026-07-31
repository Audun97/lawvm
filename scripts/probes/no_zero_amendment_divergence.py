"""W-7 tranche 1: verify every zero-amendment executable law against its
Lovdata consolidation, with the F-10 unbound-binding join as a predictor.

For a law with no indexed amendment, replay is trivially the original act, so
this comparison makes a sharp claim either way: consistency means the law
really is untouched as far as the consolidation shows; divergence means either
an amendment the index never bound (the F-10 gap made observable in the field)
or original-act extraction noise. The probe first derives, from the
``no_amendment_index_declared_target_unbound`` adjudications, which
zero-amendment laws a *dated* act declares but never bound — those laws are
PREDICTED divergent — then sweeps all of them and reports the confirmation
rate. On 2026-07-31: 100 laws, 57 consistent / 43 divergent, and 5 of the 6
predicted laws confirmed (the exception is targeted by ``2026-06-19-48``,
F-03's mixed-commencement act, so "not yet in force" is the expected cause).

Read-only. Writes JSON under .tmp/.
"""
from __future__ import annotations

import json
from pathlib import Path

from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.sources import (
    load_available_lti_law_ids,
    load_no_current_law_ids,
    resolve_no_source_path,
)
from lawvm.norway.verify import verify_no_against_current

AS_OF = "2026-07-10"
UNBOUND_RULE = "no_amendment_index_declared_target_unbound"
OUT = Path(__file__).resolve().parents[2] / ".tmp" / "no_zero_amendment_divergence.json"


def main() -> int:
    d = resolve_no_source_path(None)
    idx = build_no_amendment_index(d)
    by_id = {e.source_id: e for e in idx.entries}
    executable = load_no_current_law_ids(d) & load_available_lti_law_ids(d)
    amended: set[str] = set()
    for e in idx.entries:
        amended.update(e.base_ids)
    zero = sorted(executable - amended)
    print(f"zero-amendment executable laws: {len(zero)}")

    # the unbound-binding receipts predict which zero-amendment laws diverge
    predicted: dict[str, list[str]] = {}
    for row in idx.diagnostics:
        if (row.get("rule_id") or row.get("kind")) != UNBOUND_RULE:
            continue
        act = str(row.get("source_id") or "")
        entry = by_id.get(act)
        if entry is None or entry.effective_status != "dated":
            continue
        for target in list(row.get("unbound_target_ids") or row.get("unbound_ids") or ()):
            if target in executable and target not in amended:
                predicted.setdefault(target, []).append(act)
    print(f"predicted divergent (unbound binding from a dated act): {len(predicted)}")
    for target, acts in sorted(predicted.items()):
        print(f"  {target}  <- {', '.join(acts)}")

    rows = []
    verdicts: dict[str, str] = {}
    divergences: dict[str, int] = {}
    summary = {"consistent": 0, "divergent": 0, "error": 0}
    for i, base_id in enumerate(zero, 1):
        try:
            r = verify_no_against_current(base_id, as_of=AS_OF, data_dir=d, index=idx)
            verdict = "consistent" if r.consistent else "divergent"
            divergences[base_id] = r.divergence_count
            rows.append({
                "base_id": base_id, "verdict": verdict,
                "divergences": r.divergence_count,
                "predicted_by": predicted.get(base_id, []),
            })
        except Exception as exc:  # noqa: BLE001 - the sweep must finish
            verdict = "error"
            rows.append({
                "base_id": base_id, "verdict": "error", "error": str(exc)[:200],
                "predicted_by": predicted.get(base_id, []),
            })
        verdicts[base_id] = verdict
        summary[verdict] += 1
        if i % 20 == 0:
            print(f"  [{i}/{len(zero)}] {summary}")

    confirmed = [t for t in predicted if verdicts.get(t) == "divergent"]
    print(f"\nfinal: {summary}")
    print(f"predictions confirmed: {len(confirmed)}/{len(predicted)}")
    for target, acts in sorted(predicted.items()):
        if verdicts.get(target) != "divergent":
            print(f"  NOT divergent despite unbound binding: {target}"
                  f" <- {', '.join(acts)}")
    print("\ndivergent laws:")
    for base_id in zero:
        if verdicts.get(base_id) == "divergent":
            flag = "  <-- predicted" if base_id in predicted else ""
            print(f"  {base_id}  div={divergences.get(base_id, 0)}{flag}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "as_of": AS_OF, "summary": summary,
        "predicted": {k: v for k, v in sorted(predicted.items())},
        "rows": rows,
    }, ensure_ascii=False, indent=1))
    print(f"\nfull rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
