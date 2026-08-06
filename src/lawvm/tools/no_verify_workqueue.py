"""lawvm no-verify-workqueue -- actionable Norway verify bucket queue."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, cast

if TYPE_CHECKING:
    import argparse


def main(args: "argparse.Namespace") -> None:
    from lawvm.norway.sources import no_consolidation_snapshot_date
    from lawvm.norway.verify import build_no_verify_partition

    bucket = str(getattr(args, "bucket", "replay_defect") or "replay_defect")
    partition_arg = getattr(args, "partition", None)
    if partition_arg:
        report = json.loads(Path(partition_arg).read_text(encoding="utf-8"))
    else:
        data_dir_arg = getattr(args, "data_dir", None)
        data_dir = Path(data_dir_arg) if data_dir_arg else None
        index_arg = getattr(args, "index", None)
        index_path = Path(index_arg) if index_arg else None
        commencement_arg = getattr(args, "commencement", None)
        commencement_path = Path(commencement_arg) if commencement_arg else None
        # F-01: absent --as-of, the comparison horizon comes from the corpus, not a
        # literal that predates the consolidation this is compared against. Explicit
        # flag passes through verbatim. Same derivation as `no-verify-scan`. Scoped
        # to this branch: a --partition file already carries its own horizon, so
        # reading a prebuilt queue must not need the corpus.
        as_of = getattr(args, "as_of", None) or no_consolidation_snapshot_date(data_dir)

        report = build_no_verify_partition(
            as_of=as_of,
            data_dir=data_dir,
            index_path=index_path,
            commencement_path=commencement_path,
            limit=getattr(args, "limit", 10),
            base_ids=list(getattr(args, "base_id", []) or []),
            progress_callback=(lambda msg: print(msg, file=sys.stderr)) if getattr(args, "progress", False) else None,
        )

    partitions = report["partitions"]
    if bucket not in partitions:
        valid = ", ".join(sorted(partitions))
        raise SystemExit(f"unknown Norway verify bucket: {bucket} (valid: {valid})")

    label_map = {
        "replay_defect": "Replay Defects",
        "untouched_drift": "Untouched Drift",
        "source_sparse": "Sparse Source Cases",
        "annex_ceiling": "Annexed-Instrument Ceiling",
        "consistent": "Consistent",
        "error": "Errors",
    }
    bucket_label = label_map.get(bucket, bucket)
    queue = partitions[bucket]
    payload = {
        "data_dir": report["data_dir"],
        "as_of": report["as_of"],
        "candidate_count": report["candidate_count"],
        "scanned_count": report["scanned_count"],
        "bucket": bucket,
        "bucket_label": bucket_label,
        "queue_count": len(queue),
        "queue": queue,
        "source_signal_counts": report.get("source_signal_counts", {}),
    }

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print()
    print("=== Norway Verify Work Queue ===")
    print(f"  as of           : {payload['as_of']}")
    print(f"  candidate count : {payload['candidate_count']}")
    print(f"  scanned count   : {payload['scanned_count']}")
    print(f"  bucket          : {payload['bucket_label']}")
    print(f"  bucket count    : {payload['queue_count']}")
    signal_counts: Dict[str, Any] = cast(Dict[str, Any], payload.get("source_signal_counts") or {})
    if signal_counts:
        print(
            "  source signals  : "
            + ", ".join(f"{k}={v}" for k, v in sorted(signal_counts.items()))
        )
    if queue:
        print("  queue:")
        for item in queue:
            # W-23: in a work QUEUE the actionable number for a ceiling-carrying
            # law is its unexplained residue, not the total. Only rows that
            # carry a ceiling grow the column; every other row is byte-identical.
            ceiling = (
                f" | ceiling={item['ceiling_divergence_count']}"
                f" | unexplained={item['unexplained_divergence_count']}"
                if item.get("ceiling_divergence_count")
                else ""
            )
            print(
                f"    {item['base_id']} | divergences={item['divergence_count']}{ceiling} | "
                f"ops={item['replay_op_count']} | amendments={item['indexed_amendment_count']}"
            )
