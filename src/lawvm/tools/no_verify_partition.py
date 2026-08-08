"""lawvm no-verify-partition -- classify Norway verify sample into defect buckets."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def main(args: "argparse.Namespace") -> None:
    from lawvm.norway.sources import no_consolidation_snapshot_date
    from lawvm.norway.verify import build_no_verify_partition

    data_dir_arg = getattr(args, "data_dir", None)
    data_dir = Path(data_dir_arg) if data_dir_arg else None
    # F-01: absent --as-of, the comparison horizon comes from the corpus, not a
    # literal that predates the consolidation this is compared against. Explicit
    # flag passes through verbatim. Same derivation as `no-verify-scan`.
    as_of = getattr(args, "as_of", None) or no_consolidation_snapshot_date(data_dir)
    index_arg = getattr(args, "index", None)
    index_path = Path(index_arg) if index_arg else None
    commencement_arg = getattr(args, "commencement", None)
    commencement_path = Path(commencement_arg) if commencement_arg else None
    output_arg = getattr(args, "output", None)
    output_path = Path(output_arg) if output_arg else None

    report = build_no_verify_partition(
        as_of=as_of,
        data_dir=data_dir,
        index_path=index_path,
        commencement_path=commencement_path,
        limit=getattr(args, "limit", 10),
        base_ids=list(getattr(args, "base_id", []) or []),
        progress_callback=(lambda msg: print(msg, file=sys.stderr)) if getattr(args, "progress", False) else None,
    )
    if output_path is not None:
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print()
    print("=== Norway Verify Partition ===")
    print(f"  as of           : {report['as_of']}")
    print(f"  candidate count : {report['candidate_count']}")
    print(f"  scanned count   : {report['scanned_count']}")
    print(
        "  summary         : "
        + ", ".join(f"{k}={v}" for k, v in sorted(report["summary"].items()))
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
    if output_path is not None:
        print(f"  output          : {output_path}")

    # W-45: the laws the run could never have reached, printed beside the
    # verdicts rather than as one of them. ``.get`` because it is a sibling of
    # ``partitions``, not a bucket in it, and a saved pre-W-45 partition JSON
    # replayed through this renderer has no such key.
    no_consolidation = report.get("unverifiable", {}).get("no_stored_consolidation")
    if no_consolidation:
        print(
            f"  unverifiable    : no_stored_consolidation={no_consolidation['total']} "
            f"(would-be candidates={no_consolidation['would_be_candidates']}, "
            f"substantive unexplained={no_consolidation['substantive_unexplained']})"
        )
        print(
            "  ...by family    : "
            + ", ".join(f"{k}={v}" for k, v in sorted(no_consolidation["by_family"].items()))
        )

    partitions = report["partitions"]
    for key, label in [
        ("replay_defect", "Replay Defects"),
        ("untouched_drift", "Untouched Drift"),
        ("source_sparse", "Sparse Source Cases"),
        ("annex_ceiling", "Annexed-Instrument Ceiling"),
        ("consistent", "Consistent"),
        ("error", "Errors"),
    ]:
        items = partitions[key]
        if not items:
            continue
        print(f"  {label} ({len(items)}):")
        for item in items:
            tail = f" | source_signal={item['source_signal']}" if item["source_signal"] else ""
            err = f" | error={item['error']}" if item["error"] else ""
            # Only the laws with an annexed-instrument ceiling grow a column;
            # every other row is byte-identical to the pre-W-17 rendering.
            ceiling = (
                f" | ceiling={item['ceiling_divergence_count']}"
                f" | unexplained={item['unexplained_divergence_count']}"
                if item.get("ceiling_divergence_count")
                else ""
            )
            print(
                f"    {item['base_id']} | divergences={item['divergence_count']}{ceiling} | "
                f"ops={item['replay_op_count']}{tail}{err}"
            )
