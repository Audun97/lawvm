"""lawvm no-verify-scan -- sample Norway replay-vs-current consistency scan."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def main(args: "argparse.Namespace") -> None:
    from lawvm.norway.sources import no_consolidation_snapshot_date
    from lawvm.norway.verify import build_no_verify_scan

    data_dir_arg = getattr(args, "data_dir", None)
    data_dir = Path(data_dir_arg) if data_dir_arg else None
    index_arg = getattr(args, "index", None)
    index_path = Path(index_arg) if index_arg else None
    commencement_arg = getattr(args, "commencement", None)
    commencement_path = Path(commencement_arg) if commencement_arg else None

    # An explicit --as-of is honoured verbatim. Absent one, the comparison date
    # is derived from the corpus itself rather than frozen at a literal: a
    # default that predates the consolidation snapshot makes every law amended
    # in the gap read as spuriously divergent (finding F-01).
    as_of = getattr(args, "as_of", None) or no_consolidation_snapshot_date(data_dir)

    report = build_no_verify_scan(
        as_of=as_of,
        data_dir=data_dir,
        index_path=index_path,
        commencement_path=commencement_path,
        limit=getattr(args, "limit", 10),
        base_ids=list(getattr(args, "base_id", []) or []),
        progress_callback=(lambda msg: print(msg, file=sys.stderr)) if getattr(args, "progress", False) else None,
    )

    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print()
    print("=== Norway Verify Scan ===")
    print(f"  as of           : {report['as_of']}")
    print(f"  candidate count : {report['candidate_count']}")
    print(f"  scanned count   : {report['scanned_count']}")
    summary = report["summary"]
    print(
        "  summary         : "
        + ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    )
    signal_counts = report.get("source_signal_counts", {})
    if signal_counts:
        print(
            "  source signals  : "
            + ", ".join(f"{k}={v}" for k, v in sorted(signal_counts.items()))
        )
    totals = report.get("divergence_totals", {})
    if totals:
        print(
            f"  divergences     : total={totals.get('total', 0)} "
            f"(ceiling={totals.get('ceiling', 0)}, "
            f"unexplained={totals.get('unexplained', 0)})"
        )
    ceiling_rules = report.get("ceiling_rule_counts", {})
    if ceiling_rules:
        print(
            "  ceiling rules   : "
            + ", ".join(f"{k}={v}" for k, v in sorted(ceiling_rules.items()))
        )
    for item in report["results"]:
        tail = f" | error={item['error']}" if item["error"] else ""
        signal = f" | source_signal={item['source_signal']}" if item["source_signal"] else ""
        # The ceiling split is only printed for the laws that have one, so the
        # scan row of an unaffected law reads exactly as it did before W-17.
        ceiling = (
            f" | ceiling={item['ceiling_divergence_count']}"
            f" | unexplained={item['unexplained_divergence_count']}"
            if item.get("ceiling_divergence_count")
            else ""
        )
        print(
            f"    {item['base_id']} | consistent={item['consistent']} | "
            f"divergences={item['divergence_count']}{ceiling} | amendments={item['amendment_count']} | "
            f"ops={item['replay_op_count']}{signal}{tail}"
        )
