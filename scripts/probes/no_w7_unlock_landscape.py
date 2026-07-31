"""W-7 tranche 1: the commencement unlock landscape, measured.

Answers, over the local corpus:
1. effective_status distribution across the amendment index — how much of it
   is commencement-blocked;
2. how many executable current laws (consolidation + original act both
   present) are amended-and-fully-replayable vs blocked, and the blocker-count
   histogram over the blocked ones — the steepness of the unlock curve;
3. how many whole-act commencement-instrument candidates could authorize an
   unresolved act TODAY. As of 2026-07-31 the answer is structurally zero:
   the farchive holds no ``no://forskrift/`` locators because it was ingested
   before the forskrift lane existed, while the public tarballs carry ~36k
   ``sf-*.xml`` instruments. Re-run after re-ingest (tranche 2) to size the
   authorization validator (tranche 3).

Read-only. Writes JSON under .tmp/.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from lawvm.norway.index import build_no_amendment_index
from lawvm.norway.sources import (
    NO_UNRESOLVED_EFFECTIVE_STATUSES,
    load_available_lti_law_ids,
    load_no_current_law_ids,
    resolve_no_source_path,
)

OUT = Path(__file__).resolve().parents[2] / ".tmp" / "no_w7_unlock_landscape.json"


def main() -> int:
    d = resolve_no_source_path(None)
    idx = build_no_amendment_index(d)
    current = load_no_current_law_ids(d)
    executable = current & load_available_lti_law_ids(d)
    print(f"current laws: {len(current)}, executable (original act present): {len(executable)}")

    status = Counter(str(e.effective_status) for e in idx.entries)
    unresolved = {e.source_id: e for e in idx.entries
                  if e.effective_status in NO_UNRESOLVED_EFFECTIVE_STATUSES}
    print(f"amendment acts by effective_status: {dict(status.most_common())}")
    print(f"unresolved (commencement-blocked) amendment acts: {len(unresolved)}")
    print(f"instrument coverage: {idx.commencement_instrument_coverage.to_dict()}")

    by_base: dict[str, list] = {}
    for e in idx.entries:
        for b in e.base_ids:
            by_base.setdefault(b, []).append(e)

    amended_executable = sorted(law for law in executable if law in by_base)
    zero_amendment = sorted(law for law in executable if law not in by_base)
    fully, blocked = [], []
    blocker_hist: Counter[int] = Counter()
    for law in amended_executable:
        n = sum(1 for e in by_base[law]
                if e.effective_status in NO_UNRESOLVED_EFFECTIVE_STATUSES)
        if n:
            blocked.append(law)
            blocker_hist[n] += 1
        else:
            fully.append(law)
    print(f"\namended executable laws: {len(amended_executable)}")
    print(f"  fully replayable (the scan candidate set): {len(fully)}")
    print(f"  commencement-blocked: {len(blocked)}"
          f" ({100 * len(blocked) // max(1, len(amended_executable))}%)")
    print(f"zero-amendment executable laws: {len(zero_amendment)}")

    cum = 0
    print("\nunlock curve (laws by number of unresolved blockers):")
    for k in sorted(blocker_hist):
        cum += blocker_hist[k]
        print(f"  {k:>3} blocker(s): {blocker_hist[k]:>3} laws   (cumulative {cum})")

    # whole-act single-date instrument candidates binding an unresolved act
    authorizable: dict[str, str] = {}
    multi_date = conflicts = 0
    for c in idx.commencement_instruments:
        if str(c.scope_status) != "whole_act":
            continue
        for law_id in c.affected_law_ids:
            if law_id not in unresolved:
                continue
            if len(c.effective_dates) != 1:
                multi_date += 1
                continue
            prev = authorizable.get(law_id)
            if prev is not None and prev != c.effective_dates[0]:
                conflicts += 1
            authorizable[law_id] = c.effective_dates[0]
    would_flip = [law for law in blocked
                  if all(e.source_id in authorizable for e in by_base[law]
                         if e.effective_status in NO_UNRESOLVED_EFFECTIVE_STATUSES)]
    print(f"\nunresolved acts with a single-date whole-act instrument: {len(authorizable)}"
          f" (multi-date skips: {multi_date}, date conflicts: {conflicts})")
    print(f"blocked laws that would flip if those were authorized: {len(would_flip)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "current_laws": len(current),
        "executable_laws": len(executable),
        "status_counts": dict(status),
        "unresolved_acts": len(unresolved),
        "instrument_coverage": idx.commencement_instrument_coverage.to_dict(),
        "amended_executable": len(amended_executable),
        "fully_replayable": fully,
        "blocked": len(blocked),
        "blocker_histogram": {str(k): v for k, v in sorted(blocker_hist.items())},
        "zero_amendment": zero_amendment,
        "authorizable_unresolved_acts": len(authorizable),
        "would_flip": would_flip,
    }, ensure_ascii=False, indent=1))
    print(f"\nfull result -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
