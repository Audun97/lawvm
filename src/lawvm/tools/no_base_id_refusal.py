"""Refuse a Norway law id on sight, before a single-law command resolves its index.

``no-divergence``, ``no-coverage``, ``no-debug``, ``no-op-trace`` and ``no-law``
each take one law id and build their report from the amendment index, which on
the full archive costs ~90 s and ~800 MB to build. An id replay refuses from
the id alone (W-110: ``no/lov``, another jurisdiction's id, a regulation) has
no report to build: the index binds no such id. These commands ask replay's own
id check first and stop with its reason, as ``replay -j no`` and ``no-verify``
do through ``replay_no_to_pit`` and ``verify_no_against_current``.
"""
from __future__ import annotations

import json
import sys


def exit_if_no_base_id_refused(base_id: str, *, heading: str, json_output: bool) -> None:
    """Print replay's reason and exit 1 when ``base_id`` is refused on sight.

    Returns silently for an id replay can address, including a well-formed id
    whose base act the archive does not hold: that one has amendments in the
    index, so the command still has something to report.
    """
    from lawvm.norway.replay import NOBaseIdRefusal, read_no_base_id

    read = read_no_base_id(base_id)
    if not isinstance(read, NOBaseIdRefusal):
        return
    if json_output:
        print(json.dumps({"base_id": read.base_id, "error": read.error}, ensure_ascii=False, indent=2))
    else:
        print()
        print(f"=== {heading} ===")
        print(f"  base id : {read.base_id}")
        print(f"  error   : {read.error}")
    sys.exit(1)
