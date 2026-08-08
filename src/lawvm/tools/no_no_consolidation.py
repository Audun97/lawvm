"""lawvm no-no-consolidation -- Norway laws with a replayable original and no stored consolidation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def main(args: "argparse.Namespace") -> None:
    from lawvm.norway.inventory import build_no_inventory, build_no_no_consolidation_report
    from lawvm.norway.index import load_no_amendment_index

    data_dir_arg = getattr(args, "data_dir", None)
    data_dir = Path(data_dir_arg) if data_dir_arg else None
    index_arg = getattr(args, "index", None)
    index_path = Path(index_arg) if index_arg else None
    index = load_no_amendment_index(index_path) if index_path else None
    if data_dir is None and index is not None and index.data_dir:
        data_dir = Path(index.data_dir)

    inventory = build_no_inventory(
        data_dir,
        index=index,
        index_path=index_path,
    )
    report = build_no_no_consolidation_report(
        inventory,
        family=getattr(args, "family", None),
        base_id=getattr(args, "base_id", None),
        min_amendments=getattr(args, "min_amendments", 0),
    )
    limit = getattr(args, "limit", None)
    if isinstance(limit, int):
        report = dict(report)
        report["laws"] = report["laws"][:limit]
    if index is not None:
        report.update(index.staleness_report(data_dir))

    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print()
    print("=== Norway Originals Without a Stored Consolidation ===")
    print(f"  data dir               : {report['data_dir']}")
    print(f"  stored consolidations  : {report['stored_consolidations']}")
    print(f"  current laws (operative): {report['current_laws']}")
    print(f"  no consolidation count : {report['without_consolidation_law_count']}")
    if report.get("index_stale"):
        print("  index stale            : yes")
    if report["family_filter"]:
        print(f"  family filter          : {report['family_filter']}")
    if report["base_id_filter"]:
        print(f"  base id filter         : {report['base_id_filter']}")
    print(f"  min amendments         : {report['min_amendments']}")
    print(
        "  by family              : "
        + ", ".join(f"{k}={v}" for k, v in sorted(report["counts_by_family"].items()))
    )
    print(f"  would-be candidates    : {report['would_be_candidates']}")
    print(f"  substantive unexplained: {report['substantive_unexplained']}")
    for law_id in report["substantive_unexplained_law_ids"]:
        print(f"    {law_id}")
    laws = report["laws"]
    if laws:
        print("  laws:")
        for item in laws:
            title = item["title"] or "(untitled)"
            repealed_by = ",".join(item["repealed_by"]) or "-"
            print(
                f"    {item['base_id']} | {title} | family={item['family']} | "
                f"would_be={item['would_be_status'] or '-'} | repealed_by={repealed_by} | "
                f"amendments={item['amendments']}"
            )
