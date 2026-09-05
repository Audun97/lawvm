"""Fire-drill tests for Norway RENUMBER migration event stamping (§1.6 + §2.9).

Mirrors the SE precedent
``tests/test_sweden_fetch.py::test_check_se_official_replay_emits_renumber_receipt_with_migration_rule_id``,
adapted for NO's current state:

* op-side ``witness_rule_id`` stamping on every RENUMBER op mint site
  (mirrors EE's ``_EE_SECTION_SEQUENCE_RENUMBER_RULE`` on op construction at
  ``estonia/peg.py:1225``) — Step 2 of iter2 W5 H2;
* receipt-side ``migration_rule_ids`` stamping on the authoritative apply
  seam's per-op ``WriteReceipt``, surfaced through
  ``apply_no_ops_conserved(emit_receipts=True)`` and the production caller in
  ``replay.py``. The SE-style ``WriteReceipt``
  assertions ARE exercised here (``migration_rule_ids == ("no_section_renumber_relabel",)``
  and ``divergence_explained is True``).

The four RENUMBER op mint sites in ``src/lawvm/norway/grafter.py``:

* unstructured repeal+renumber combo (subsection-level, ~line 1583);
* unstructured single renumber (section-level, ~line 1858);
* unstructured plural renumber (section-level, ~line 1879);
* structured renumber XML attr (mixed granularity, ~line 2553).

Plus a guard-liveness test driving the production lane
``replay_no_to_pit`` → ``apply_no_ops_conserved`` so the ``witness_rule_id``
stamping is provably reachable from a real user invocation, not just from
``parse_no_amendment_ops`` in isolation (the §2.9 worst-class silent-failure
form: a guard that exists but is unreachable from production).
"""
from __future__ import annotations

import io
import re
import tarfile
from pathlib import Path as _Path

import pytest

from collections.abc import Sequence

from lawvm.core.ir import IRNode, LegalOperation
from lawvm.core.semantic_types import IRNodeKind, StructuralAction
from lawvm.norway.grafter import (
    apply_no_ops_conserved,
    parse_no_amendment_ops,
)
from lawvm.norway.replay import replay_no_to_pit


_RENUMBER_RULE_ID = "no_section_renumber_relabel"


_BASE_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head>
    <title>Testlov om renumber-witness</title>
  </head>
  <body>
    <main class="documentBody" data-lovdata-URL="LTI/lov/2025-01-01-1">
      <section class="section" data-name="kap1" data-lovdata-URL="LTI/lov/2025-01-01-1/KAPITTEL_1">
        <h2>Kapittel 1. Innledning</h2>
        <article class="legalArticle" data-name="§1" data-lovdata-URL="LTI/lov/2025-01-01-1/§1">
          <h3 class="legalArticleHeader">§ 1. Formaal</h3>
          <article class="legalP" id="ledd1">Loven gjelder testdata.</article>
        </article>
        <article class="legalArticle" data-name="§2" data-lovdata-URL="LTI/lov/2025-01-01-1/§2">
          <h3 class="legalArticleHeader">§ 2. Krav</h3>
          <article class="legalP" id="ledd1">Kravene skal oppfylles.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _unstructured_single_renumber_xml() -> bytes:
    """One ``Nåværende § 2 blir ny § 3.`` lead in proper unstructured wrap."""
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kap16">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om testlov gjøres følgende endringer:</article>
        <article class="defaultP">Nåværende § 2 blir ny § 3.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _unstructured_plural_renumber_xml() -> bytes:
    """``Nåværende §§ 2 og 3 blir §§ 3 og 4.`` (two renumber ops)."""
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kap16">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om testlov gjøres følgende endringer:</article>
        <article class="defaultP">Nåværende §§ 2 og 3 blir §§ 3 og 4.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _unstructured_repeal_renumber_xml() -> bytes:
    """Section-level ``§ 2 første ledd oppheves. Nåværende annet ledd blir første ledd.``"""
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kap16">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om testlov gjøres følgende endringer:</article>
        <article class="defaultP">§ 2 første ledd oppheves. Nåværende annet ledd blir første ledd.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _structured_renumber_xml() -> bytes:
    """``<article data-move-part="...§2;;...§3">``."""
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-move-part="lov/2025-01-01-1/§2;;lov/2025-01-01-1/§3">
        <article class="defaultP">Nåværende § 2 blir ny § 3.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _renumber_amendment_xml_for_replay(date_in_force: str) -> bytes:
    """Production-lane amendment: renumber §2 → §3 within lov/2025-01-01-1."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">{date_in_force}</dd>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-move-part="lov/2025-01-01-1/§2;;lov/2025-01-01-1/§3">
        <article class="defaultP">Nåværende § 2 blir ny § 3.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _write_archive(archive_path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(archive_path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def _renumber_ops(ops: list[LegalOperation]) -> list[LegalOperation]:
    return [op for op in ops if op.action is StructuralAction.RENUMBER]


# ---- op-side witness_rule_id stamping on each mint site ---------------------


def test_no_unstructured_single_renumber_op_carries_witness_rule_id() -> None:
    """Fire-drill §2.9 guard-liveness: the unstructured single-renumber mint
    site (grafter.py:1858-1869, `Nåværende § A blir ny § B` regex path) stamps
    `witness_rule_id="no_section_renumber_relabel"` on the parse-time op.
    Mirrors EE's `witness_rule_id=_EE_SECTION_SEQUENCE_RENUMBER_RULE` on op
    construction at `estonia/peg.py:1225`.

    Pre-fix state: RENUMBER ops minted at this site carried no `witness_rule_id`
    (the §1.6 unstated-migration invariant's identity migration had no named
    owner at the parse→apply waist).
    """
    ops = parse_no_amendment_ops(
        _unstructured_single_renumber_xml(),
        "no/lovtid/2026-06-27-90",
    )

    renumber_ops = _renumber_ops(ops)
    assert len(renumber_ops) == 1, [
        (op.action, op.target.path, op.destination.path if op.destination else None)
        for op in ops
    ]
    op = renumber_ops[0]
    assert op.target.path == (("section", "2"),)
    assert op.destination is not None
    assert op.destination.path == (("section", "3"),)
    assert op.witness_rule_id == _RENUMBER_RULE_ID


def test_no_unstructured_plural_renumber_op_carries_witness_rule_id() -> None:
    """Fire-drill §2.9: the unstructured plural-renumber mint site
    (grafter.py:1879-1897, `Nåværende §§ A og B blir §§ C og D` regex path)."""
    ops = parse_no_amendment_ops(
        _unstructured_plural_renumber_xml(),
        "no/lovtid/2026-06-27-90",
    )

    renumber_ops = _renumber_ops(ops)
    assert len(renumber_ops) == 2
    dst_labels: list[str] = []
    for op in renumber_ops:
        assert op.destination is not None
        dst_labels.append(op.destination.path[0][1])
    assert dst_labels == ["3", "4"]
    for op in renumber_ops:
        assert op.witness_rule_id == _RENUMBER_RULE_ID


def test_no_unstructured_repeal_renumber_subsection_op_carries_witness_rule_id() -> None:
    """Fire-drill §2.9: the unstructured repeal+renumber combo mint site
    (grafter.py:1583-1594, subsection-level path). The rule id's ``section``
    qualifier is the broad family owner per the catalog entry (mirrors the
    SE one-rule-id-for-all-renumbers pattern at sweden/grafter.py:4145)."""
    ops = parse_no_amendment_ops(
        _unstructured_repeal_renumber_xml(),
        "no/lovtid/2026-06-27-90",
    )

    renumber_ops = _renumber_ops(ops)
    assert len(renumber_ops) == 1, [
        (op.action, op.target.path, op.destination.path if op.destination else None)
        for op in ops
    ]
    op = renumber_ops[0]
    assert op.target.path == (("section", "2"), ("subsection", "2"))
    assert op.destination is not None
    assert op.destination.path == (("section", "2"), ("subsection", "1"))
    assert op.witness_rule_id == _RENUMBER_RULE_ID


def test_no_structured_renumber_op_carries_witness_rule_id() -> None:
    """Fire-drill §2.9: the structured renumber XML-attr mint site
    (grafter.py:2553-2570, `data-move-part` parse path)."""
    ops = parse_no_amendment_ops(
        _structured_renumber_xml(),
        "no/lovtid/2026-06-27-90",
    )

    renumber_ops = _renumber_ops(ops)
    assert len(renumber_ops) == 1, [
        (op.action, op.target.path, op.destination.path if op.destination else None)
        for op in ops
    ]
    op = renumber_ops[0]
    assert op.target.path == (("section", "2"),)
    assert op.destination is not None
    assert op.destination.path == (("section", "3"),)
    assert op.witness_rule_id == _RENUMBER_RULE_ID


def test_no_renumber_op_witness_rule_id_reachable_from_production_lane(tmp_path) -> None:
    """Fire-drill §2.9 guard-liveness (the worst-class failure form):
    the `witness_rule_id` stamped on parse-time RENUMBER ops MUST be reachable
    from the production lane, not just from `parse_no_amendment_ops` in
    isolation. Drives:

      replay_no_to_pit (production entry)
        → parse_no_amendment_ops (minting site, stamps witness_rule_id)
        → apply_no_ops_conserved (production routing per iter2 W2)
        → NOApplyResult.filter_result.accepted_items (typed transport)

    Without this assertion, the `witness_rule_id` stamping would be a guard
    that exists but is unreachable from production — a §2.9 worst-class silent
    failure that passes review and creates false confidence.

    The §1.6 unstated-migration invariant: a RENUMBER op's bound target (source
    label) vs landed destination divergence is the typed migration event and
    MUST carry a named rule id. The op-side `witness_rule_id` is the parse-time
    stamping (iter2 W5 H2 Step 2); the receipt-side `migration_rule_ids`
    stamping requires the per-op WriteReceipt helper that does not yet exist
    in the NO frontend (STOP-and-report, see top-of-file docstring).
    """
    archive_path = tmp_path / "lovtidend-avd1-2001-2025.tar.bz2"
    _write_archive(
        archive_path,
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _renumber_amendment_xml_for_replay("2025-02-10")),
        ],
    )

    result = replay_no_to_pit(
        "no/lov/2025-01-01-1",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None, result.error
    assert result.amendments_applied == ["no/lovtid/2025-02-02-5"]
    assert result.apply_filter_result is not None, (
        "apply_no_ops_conserved did not surface a typed FilterResult on the "
        "production lane — the iter2 W2 conserved-wrapper routing may have been "
        "bypassed."
    )
    accepted_renumber_ops = _renumber_ops(list(result.apply_filter_result.accepted_items))
    assert len(accepted_renumber_ops) == 1, [
        (op.action, op.target.path, op.destination.path if op.destination else None)
        for op in result.apply_filter_result.accepted_items
    ]
    op = accepted_renumber_ops[0]
    assert op.witness_rule_id == _RENUMBER_RULE_ID, (
        f"RENUMBER op minted on the production lane lacks the §1.6 witness rule id "
        f"(expected {_RENUMBER_RULE_ID!r}, got {op.witness_rule_id!r}). This is the "
        "§2.9 guard-liveness failure: the op-side stamping exists but is not "
        "reachable from `replay_no_to_pit`."
    )
    assert op.target.path == (("section", "2"),)
    assert op.destination is not None
    assert op.destination.path == (("section", "3"),)

    # The replayed statute actually reflects the renumber: §2 was removed and
    # §3 was inserted with §2's content.
    assert result.replayed is not None
    chapter = result.replayed.body.children[0]
    section_labels = [
        child.label
        for child in chapter.children
        if child.kind is IRNodeKind.SECTION
    ]
    assert "2" not in section_labels, section_labels
    assert "3" in section_labels, section_labels


# ---- receipt-side migration_rule_ids stamping (iter2 W6 H2 follow-up) --------


def test_no_replay_production_lane_emits_renumber_write_receipt_with_migration_rule_id(
    tmp_path,
) -> None:
    """Fire-drill §2.9 guard-liveness (the worst-class failure form): the per-op
    ``WriteReceipt`` with ``migration_rule_ids=("no_section_renumber_relabel",)``
    MUST land on the production apply path
    ``replay_no_to_pit`` → ``apply_no_ops_conserved(emit_receipts=True)`` →
    the authoritative apply seam.

    Pre-fix state (the iter2 W5 H2 STOP-and-report condition):
    * H2 (op-side) stamped ``witness_rule_id="no_section_renumber_relabel"`` on
      every RENUMBER op mint site but STOPPED on the receipt-side stamping
      because NO had no per-op ``WriteReceipt`` helper (the SE analog at
      ``sweden/grafter.py:4145``). The receipt-side stamp was reachable only
      through SE/EE, not through NO's production lane — a §2.9 worst-class
      silent failure (a guard that exists but is unreachable from production).

    The authoritative fold now synthesizes and collects the receipt during the
    same execution that produces the replayed statute; no reconstruction pass
    is involved.

    Mirrors ``tests/test_sweden_fetch.py::test_check_se_official_replay_emits_renumber_receipt_with_migration_rule_id``
    (Wave 2 SE precedent), adapted for NO's archive-driven replay path.
    """
    archive_path = tmp_path / "lovtidend-avd1-2001-2025.tar.bz2"
    _write_archive(
        archive_path,
        [
            ("lti/2025/nl-20250101-001.xml", _BASE_XML),
            ("lti/2025/nl-20250202-005.xml", _renumber_amendment_xml_for_replay("2025-02-10")),
        ],
    )

    result = replay_no_to_pit(
        "no/lov/2025-01-01-1",
        as_of="2025-02-15",
        data_dir=tmp_path,
    )

    assert result.error is None, result.error
    assert result.write_receipts, (
        "Production lane `replay_no_to_pit → apply_no_ops_conserved(emit_receipts=True)` "
        "did not emit any "
        "WriteReceipts. This is the §2.9 worst-class silent failure: the receipt "
        "helper exists but is unreachable from production."
    )
    renumber_receipts = [r for r in result.write_receipts if r.action == "renumber"]
    assert len(renumber_receipts) == 1, [r.action for r in result.write_receipts]
    receipt = renumber_receipts[0]
    renumber_audits = [
        audit
        for audit in result.observed_write_audits
        if audit.op_id == receipt.op_id
    ]
    assert len(renumber_audits) == 1
    assert renumber_audits[0].audit_status == "qualified"

    # The §4 receipt contract: bound_target_path (source label) diverges from
    # landed_primary_path (destination label) — the divergence MUST be
    # explained by a named migration rule.
    assert receipt.bound_target_path == (("section", "2"),)
    assert receipt.landed_primary_path == (("chapter", "1"), ("section", "3"))
    # The RENUMBER footprint is the typed (from_path, to_path) pair. Both legs
    # are the exact resolved paths for the §2→§3 renumber.
    assert receipt.renumbered_paths == (
        (
            (("chapter", "1"), ("section", "2")),
            (("chapter", "1"), ("section", "3")),
        ),
    ), receipt.renumbered_paths
    # The named migration rule that explains the bound→landed divergence
    # (mirrors SE's ``("se_renumber_relabel",)``).
    assert receipt.migration_rule_ids == ("no_section_renumber_relabel",), (
        f"Expected migration_rule_ids=('no_section_renumber_relabel',), "
        f"got {receipt.migration_rule_ids!r}. The §1.6 unstated-migration "
        "invariant's identity migration has no named owner on the receipt — "
        "the receipt audits as `violation` in build_observed_write_audit and "
        "strict mode must reject it."
    )
    assert receipt.recovery_rule_ids == ()
    assert receipt.fallback_rule_ids == ()
    # bound != landed AND migration_rule_ids is non-empty → divergence_explained
    # is True (the §4 receipt-contract property). Without this, the receipt
    # would audit as `violation` (an unexplained mutation-boundary divergence
    # that strict mode must block on).
    assert receipt.divergence_explained is True, (
        "RENUMBER receipt with bound != landed should have divergence_explained=True "
        "via the migration_rule_ids stamp — the §4 receipt-contract property."
    )

    # Hash coverage is exact over both declared migration legs. The source
    # existed before and is absent after; the destination is the inverse.
    source_key = "chapter:1/section:2"
    destination_key = "chapter:1/section:3"
    assert set(receipt.pre_hashes) == {source_key, destination_key}
    assert set(receipt.post_hashes) == {source_key, destination_key}
    assert receipt.pre_hashes[source_key] != ""
    assert receipt.post_hashes[source_key] == ""
    assert receipt.pre_hashes[destination_key] == ""
    assert receipt.post_hashes[destination_key] != ""


def test_apply_no_ops_conserved_emit_receipts_false_does_not_emit() -> None:
    """Negative test §2.9(4): the ``emit_receipts=False`` default keeps the
    existing apply-fold cost — no per-op ``WriteReceipt`` construction,
    ``NOApplyResult.write_receipts`` is the empty tuple. Guards against the
    new ``emit_receipts`` parameter accidentally defaulting to True (which
    would silently pay the per-op-replay overhead for every existing caller).
    """
    from lawvm.norway.grafter import parse_no_statute

    base_statute = parse_no_statute(_BASE_XML, statute_id="no/lov/2025-01-01-1")
    ops = parse_no_amendment_ops(
        _renumber_amendment_xml_for_replay("2025-02-10"),
        "no/lovtid/2025-02-02-5",
    )
    result = apply_no_ops_conserved(base_statute, ops)
    assert result.write_receipts == ()
    # The acceptance partition stays intact regardless of the emit_receipts
    # flag — the receipt lane is purely additive (§1.8 contract preserved).
    renumber_accepted = _renumber_ops(list(result.applied_ops))
    assert len(renumber_accepted) == 1


def test_apply_no_ops_conserved_emit_receipts_true_emits_renumber_receipt() -> None:
    """Unit-level fire-drill: ``apply_no_ops_conserved(emit_receipts=True)``
    directly surfaces a ``WriteReceipt`` for the RENUMBER op on
    ``NOApplyResult.write_receipts``. The receipt carries the
    ``no_section_renumber_relabel`` migration rule id and audits as
    ``divergence_explained is True``.

    Isolates the conserved-wrapper-level fire-drill from the full
    production-lane test (no archive scaffolding needed). Mirrors the SE
    conserved-wrapper test shape.
    """
    from lawvm.norway.grafter import parse_no_statute

    base_statute = parse_no_statute(_BASE_XML, statute_id="no/lov/2025-01-01-1")
    ops = parse_no_amendment_ops(
        _renumber_amendment_xml_for_replay("2025-02-10"),
        "no/lovtid/2025-02-02-5",
    )
    result = apply_no_ops_conserved(base_statute, ops, emit_receipts=True)
    renumber_receipts = [r for r in result.write_receipts if r.action == "renumber"]
    assert len(renumber_receipts) == 1, [r.action for r in result.write_receipts]
    receipt = renumber_receipts[0]
    assert receipt.migration_rule_ids == ("no_section_renumber_relabel",)
    assert receipt.recovery_rule_ids == ()
    assert receipt.fallback_rule_ids == ()
    assert receipt.divergence_explained is True
    # The receipt's partition integrity: the RENUMBER op is in accepted_items
    # AND its receipt is in write_receipts. Mirrors SE's contract.
    renumber_accepted = _renumber_ops(list(result.applied_ops))
    assert len(renumber_accepted) == 1
    assert renumber_accepted[0].op_id == receipt.op_id


# ---- (RENUMBER, dest_occupied): the occupant removal is a DECLARED write ----
#
# W-52. The ``(RENUMBER, dest_occupied)`` totalization cell
# (``no_renumber_occupied_destination_removed``) clears the node standing at the
# renumber destination and then relabels the source onto it. That clearing is a
# real content write, but a RENUMBER receipt's footprint is derived purely from
# the (from, to) legs, so before this pin the occupant's subtree was destroyed
# under no declared path at all. Two arms, and only one of them was ever
# visible:
#
#   * SAME container — the occupant stood exactly at the destination leg, so the
#     leg already declared the path and the coarse identity-pruned diff stayed
#     *related* to it. The undeclared removal passed the independent
#     before/after audit unseen (7 of the 10 corpus firings).
#   * DIFFERENT container — the occupant lived under another chapter/part, so
#     no leg covered it, the audit read the write as an ``undeclared`` escape
#     and strict replay raised (3 of the 10 corpus firings; it is what blocked
#     ``no/lov/2004-12-17-99`` and ``no/lov/2005-06-10-44`` from replaying).
#
# Both arms now declare the removal via ``MaterializeResult.recovery_removed_
# paths``, so the audit judges every occupied-destination removal against the
# rule that authored it instead of against silence.

_OCCUPIED_DESTINATION_RULE_ID = "no_renumber_occupied_destination_removed"

#: The ADJUDICATION kind the recovery emits, which is not the same string as the
#: recovery rule id above (that one names the rule on the write receipt). Hoisted
#: at W-72 because the corpus sweep and these pins have to count the same events,
#: and two near-identical literals a hundred lines apart is how they would come to
#: count different ones.
_OCCUPIED_DESTINATION_ADJUDICATION_KIND = "no_replay_renumber_occupied_destination_removed"

_CROSS_CHAPTER_BASE_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head>
    <title>Testlov om okkupert renumber-destinasjon</title>
  </head>
  <body>
    <main class="documentBody" data-lovdata-URL="LTI/lov/2025-01-01-1">
      <section class="section" data-name="kap5" data-lovdata-URL="LTI/lov/2025-01-01-1/KAPITTEL_5">
        <h2>Kapittel 5. Sanksjoner</h2>
        <article class="legalArticle" data-name="&#167;21" data-lovdata-URL="LTI/lov/2025-01-01-1/&#167;21">
          <h3 class="legalArticleHeader">&#167; 21. Straff</h3>
          <article class="legalP" id="ledd1">Straffebestemmelsen gjelder.</article>
        </article>
        <article class="legalArticle" data-name="&#167;22" data-lovdata-URL="LTI/lov/2025-01-01-1/&#167;22">
          <h3 class="legalArticleHeader">&#167; 22. Inndragning</h3>
          <article class="legalP" id="ledd1">Inndragning kan skje.</article>
        </article>
      </section>
      <section class="section" data-name="kap6" data-lovdata-URL="LTI/lov/2025-01-01-1/KAPITTEL_6">
        <h2>Kapittel 6. Avsluttende bestemmelser</h2>
        <article class="legalArticle" data-name="&#167;23" data-lovdata-URL="LTI/lov/2025-01-01-1/&#167;23">
          <h3 class="legalArticleHeader">&#167; 23. Ikrafttredelse</h3>
          <article class="legalP" id="ledd1">Loven trer i kraft straks.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _cross_chapter_renumber_amendment_xml() -> bytes:
    """``Nåværende § 23 blir ny § 22.`` — § 22 is live in the PREVIOUS chapter.

    The verbatim shape of ``no/lovtid/2012-05-25-29``'s
    ``Nåværende §§ 23 og 24 blir §§ 22 og 23.`` against klimakvoteloven.
    """
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2025-01-01-1</li></ul>
    </dd>
    <main>
      <section data-name="kap1">
        <article class="defaultP">I lov 1. januar 2025 nr. 1 om testlov gj&#248;res f&#248;lgende endringer:</article>
        <article class="defaultP">N&#229;v&#230;rende &#167; 23 blir ny &#167; 22.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _same_chapter_renumber_amendment_xml() -> bytes:
    """``Nåværende § 21 blir ny § 22.`` — § 22 is live in the SAME chapter."""
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2025-01-01-1</li></ul>
    </dd>
    <main>
      <section data-name="kap1">
        <article class="defaultP">I lov 1. januar 2025 nr. 1 om testlov gj&#248;res f&#248;lgende endringer:</article>
        <article class="defaultP">N&#229;v&#230;rende &#167; 21 blir ny &#167; 22.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _under_declared_ledd_shift_amendment_xml() -> bytes:
    """W-56: the tvisteloven shape — prose spells TWO limbs, markup declares ONE.

    Verbatim structure of ``no/lovtid/2024-12-13-78``'s § 24-8 block: a
    ``data-move-part`` carrying only ``ledd/3;;ledd/4`` under a lead sentence
    that commands both ``3 → 4`` and ``4 → 5``.
    """
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-01-01</dd>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-move-part="lov/2025-01-01-1/&#167;2/ledd/3;;lov/2025-01-01-1/&#167;2/ledd/4">
        <article class="defaultP">N&#229;v&#230;rende tredje og fjerde ledd blir fjerde og nytt femte ledd.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def _unparseable_ledd_shift_amendment_xml() -> bytes:
    """W-56 polarity control: the SAME under-declared markup under a lead whose
    ordinal vocabulary this grammar cannot name ("tolvte" is outside
    ``_NORWEGIAN_ORDINALS``). The completion must refuse and leave the markup's
    own single leg exactly as declared — never a differently-guessed set.
    """
    return """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-01-01</dd>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-move-part="lov/2025-01-01-1/&#167;2/ledd/3;;lov/2025-01-01-1/&#167;2/ledd/4">
        <article class="defaultP">N&#229;v&#230;rende tredje og tolvte ledd blir fjerde og nytt trettende ledd.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def test_no_under_declared_move_attr_is_completed_from_its_own_lead_prose() -> None:
    """W-56: an under-declared ``data-move-part`` lowers the WHOLE ledd shift.

    Lovtidend spelled one move leg where its own lead sentence commands two.
    Lowering the partial set is what let ``(RENUMBER, dest_occupied)`` remove
    tvisteloven § 24-8's vitneforsikring (W-54 firing 9, ``removal_wrong``): the
    surviving ``3 → 4`` leg landed on a slot whose occupant no op ever moved
    out. With both legs lowered the destination IS a renumber source, the
    recovery's ``destination not in renumber_sources`` guard suppresses it, and
    the occupant simply shifts down.
    """
    ops = parse_no_amendment_ops(
        _under_declared_ledd_shift_amendment_xml(), "no/lovtid/2025-02-02-5"
    )
    renumbers = _renumber_ops(ops)
    assert [
        (str(op.target), str(op.destination)) for op in renumbers
    ] == [
        ("section:2/subsection:4", "section:2/subsection:5"),
        ("section:2/subsection:3", "section:2/subsection:4"),
    ]
    # Both legs carry the ordinary structured-renumber witness — the completion
    # mints no new migration semantics, only the missing leg.
    assert {op.witness_rule_id for op in renumbers} == {_RENUMBER_RULE_ID}


def test_no_under_declared_move_attr_completion_is_receipted() -> None:
    """W-56: the completion is never silent — it emits a non-blocking finding
    naming both the declared and the completed leg sets."""
    from lawvm.norway.grafter import NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE

    adjudications: list = []
    parse_no_amendment_ops(
        _under_declared_ledd_shift_amendment_xml(),
        "no/lovtid/2025-02-02-5",
        adjudications_out=adjudications,
    )
    completions = [
        a for a in adjudications if a.kind == NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE
    ]
    assert len(completions) == 1, [a.kind for a in adjudications]
    finding = completions[0]
    assert finding.blocking is False
    assert finding.detail["declared_leg_count"] == 1
    assert finding.detail["completed_leg_count"] == 2
    assert finding.detail["completed_legs"] == (
        "lov/2025-01-01-1/§2/ledd/3;;lov/2025-01-01-1/§2/ledd/4",
        "lov/2025-01-01-1/§2/ledd/4;;lov/2025-01-01-1/§2/ledd/5",
    )


def test_no_move_attr_completion_refuses_a_lead_it_cannot_fully_account_for() -> None:
    """W-56 conservative polarity: a lead this grammar cannot fully lower leaves
    the markup's own legs untouched rather than emitting a different partial set.

    Partial lowering is precisely the failure this work item repairs, so the
    refusal arm must never *replace* the declared legs with a guess — it may only
    decline to add.
    """
    from lawvm.norway.grafter import NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE

    adjudications: list = []
    ops = parse_no_amendment_ops(
        _unparseable_ledd_shift_amendment_xml(),
        "no/lovtid/2025-02-02-5",
        adjudications_out=adjudications,
    )
    assert [
        (str(op.target), str(op.destination)) for op in _renumber_ops(ops)
    ] == [("section:2/subsection:3", "section:2/subsection:4")]
    assert [
        a for a in adjudications if a.kind == NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE
    ] == []


def test_no_renumber_across_chapters_declares_the_removed_occupant() -> None:
    """Cross-chapter occupied destination: the receipt declares the removal and
    strict apply does NOT raise.

    Before W-52 this exact shape raised
    ``Norway observed-write audit violation after renumber (('section','23'),)``
    because the receipt's footprint named only ``chapter:6/section:23`` and
    ``chapter:6/section:22`` while the write also destroyed
    ``chapter:5/section:22``.
    """
    from lawvm.norway.grafter import parse_no_statute

    base_statute = parse_no_statute(
        _CROSS_CHAPTER_BASE_XML, statute_id="no/lov/2025-01-01-1"
    )
    ops = parse_no_amendment_ops(
        _cross_chapter_renumber_amendment_xml(), "no/lovtid/2025-02-02-5"
    )
    assert len(_renumber_ops(ops)) == 1

    adjudications: list = []
    # ``strict_invariants`` defaults to True — the production polarity. A
    # violation would raise out of this call.
    result = apply_no_ops_conserved(
        base_statute, ops, adjudications_out=adjudications, emit_receipts=True
    )

    occupant_path = (("chapter", "5"), ("section", "22"))
    source_path = (("chapter", "6"), ("section", "23"))
    landed_path = (("chapter", "6"), ("section", "22"))

    receipts = [r for r in result.write_receipts if r.action == "renumber"]
    assert len(receipts) == 1, [r.action for r in result.write_receipts]
    receipt = receipts[0]
    assert receipt.renumbered_paths == ((source_path, landed_path),)
    assert receipt.removed_paths == (occupant_path,)
    assert receipt.recovery_rule_ids == (_OCCUPIED_DESTINATION_RULE_ID,)
    assert receipt.migration_rule_ids == (_RENUMBER_RULE_ID,)
    assert receipt.declared_footprint == (occupant_path, source_path, landed_path)
    # The destroyed occupant is hashed at the write: present before, absent after.
    assert receipt.pre_hashes["chapter:5/section:22"] != ""
    assert receipt.post_hashes["chapter:5/section:22"] == ""

    assert len(result.observed_write_audits) == 1
    audit = result.observed_write_audits[0]
    assert audit.audit_status == "qualified"
    assert audit.undeclared_paths == ()
    assert audit.matched_rule_ids == (_OCCUPIED_DESTINATION_RULE_ID, _RENUMBER_RULE_ID)

    # The recovery still emits its own typed adjudication — the receipt
    # declaration is ADDITIVE evidence, it does not replace the witness.
    assert [a.kind for a in adjudications].count(
        _OCCUPIED_DESTINATION_ADJUDICATION_KIND
    ) == 1

    # And the tree really did lose the occupant: chapter 5 keeps only § 21.
    layout = {
        chapter.label: [
            child.label for child in chapter.children if str(child.kind) == "section"
        ]
        for chapter in result.statute.body.children
        if str(chapter.kind) == "chapter"
    }
    assert layout == {"5": ["21"], "6": ["22"]}


def test_no_renumber_within_chapter_does_not_duplicate_the_destination_leg() -> None:
    """Same-chapter occupied destination: the destination leg already declares
    the occupant's path, so ``removed_paths`` stays empty and the receipt is
    byte-identical to the pre-W-52 one.

    This is the arm that keeps the change inert for the 7 corpus firings that
    were never blocked.
    """
    from lawvm.norway.grafter import parse_no_statute

    base_statute = parse_no_statute(
        _CROSS_CHAPTER_BASE_XML, statute_id="no/lov/2025-01-01-1"
    )
    ops = parse_no_amendment_ops(
        _same_chapter_renumber_amendment_xml(), "no/lovtid/2025-02-02-5"
    )
    adjudications: list = []
    result = apply_no_ops_conserved(
        base_statute, ops, adjudications_out=adjudications, emit_receipts=True
    )

    receipts = [r for r in result.write_receipts if r.action == "renumber"]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.removed_paths == ()
    assert receipt.recovery_rule_ids == (_OCCUPIED_DESTINATION_RULE_ID,)
    assert receipt.declared_footprint == (
        (("chapter", "5"), ("section", "21")),
        (("chapter", "5"), ("section", "22")),
    )
    assert len(result.observed_write_audits) == 1
    assert result.observed_write_audits[0].undeclared_paths == ()
    assert [a.kind for a in adjudications].count(
        _OCCUPIED_DESTINATION_ADJUDICATION_KIND
    ) == 1


# ---- corpus pin ------------------------------------------------------------

_REPO_ROOT = _Path(__file__).resolve().parents[1]
_REAL_ARCHIVE = _REPO_ROOT / "data" / "norway.farchive"

#: Every base law in the Lovdata corpus that fires — or used to fire — the
#: occupied-destination recovery at as-of 2026-07-10, with (firings, receipts
#: carrying a collateral ``removed_paths`` entry).
#:
#: This list is the REPLAY SET for the survival probes below, and nothing more.
#: It was written from a sweep and then maintained by hand, and W-72 found what
#: that costs: between W-52 and W-67 it quietly stopped describing the corpus,
#: and a destruction landed on a law it did not name. Its completeness is no
#: longer CLAIMED here — it is proven, per firing and per law, against the
#: committed corpus sweep in
#: ``test_no_corpus_wide_occupied_destination_firings_are_all_adjudicated``.
#: Add a law here only with that sweep agreeing.
#:
#: W-52 measured 10 firings, of which exactly 3 were cross-container; the two
#: laws with a cross-container firing are exactly the two whose strict replay
#: failed with ``Norway observed-write audit violation`` before W-52.
#:
#: W-56 lowered that to **9**. ``no/lov/2005-06-17-90`` (tvisteloven) drops from
#: 1 firing to 0 — that is the two-limb ledd-shift repair's INTENDED effect, not
#: a weakened pin: ``no/lovtid/2024-12-13-78``'s § 24-8 block now lowers BOTH
#: legs it commands, so the destination is itself a renumber source and the
#: recovery's own guard suppresses it. The key is deliberately KEPT at ``(0, 0)``
#: rather than deleted, so a regression that resurrects the firing (and with it
#: the destruction of the vitneforsikring) trips this assertion instead of
#: passing unnoticed under a shorter table.
#:
#: W-61 lowers it to **8**, by the same mechanism and for the same reason.
#: ``no/lov/2005-06-17-67`` (skattebetalingsloven) drops from 1 firing to 0.
#: W-54 adjudicated that firing ``removal_wrong`` — the corpus's last proven
#: destruction of in-force law — and traced it to a § 8-2 with a STALE DUPLICATE
#: fourth ledd, which existed because no lowered instrument repealed the base
#: act's first ledd. The repeal was in the archive all along, in
#: ``no/lovtid/2008-12-12-100``, refused by the unstructured-lead grammar; W-61's
#: widening lowers it together with its four-leg ledd shift, § 8-2 becomes the
#: four-ledd section the later amendments have always read on, and the
#: ``4 → 5`` leg of ``no/lovtid/2024-12-20-87`` no longer lands on an occupied
#: node at all. Kept at ``(0, 0)`` for the same tripwire reason as tvisteloven.
#: W-67 + W-74 raise it to **10**, and this is the first growth in the series.
#: The two-token section-renumber widening lowers 64 previously-refused leads, and
#: three of them move text into a slot that is already occupied. Two are entered
#: here, both adjudicated ``removal_correct`` on their own evidence (see the
#: verdict table). The THIRD — husbankloven ``no/lov/2009-05-29-30``, the 2017
#: renumber § 10 -> § 13 — was W-67's stop condition: it destroyed § 13
#: "Ikraftsetjing o.a", proven present in the consolidation and nowhere in the
#: replay. It is absent from this table because it does not fire any more. W-74
#: lowers the 2012 act's ``§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny
#: § 10.``, so § 13 is VACATED before the 2017 renumber runs and the destination
#: is free. Repaired at the lowering, exactly as W-56 and W-61 repaired theirs;
#: husbankloven is deliberately NOT listed, because a law with no firing has no
#: row to pin, and its positive fact is held by
#: ``test_no_husbankloven_13_commencement_provision_survives`` below.
_NO_OCCUPIED_DESTINATION_LAWS: dict[str, tuple[int, int]] = {
    "no/lov/2001-01-05-1": (2, 0),
    "no/lov/2003-07-04-84": (0, 0),  # W-98: repaired at the lowering; see the table note.
    "no/lov/2004-12-17-99": (2, 1),
    "no/lov/2005-06-10-44": (2, 2),
    "no/lov/2005-06-17-67": (0, 0),  # W-61: repaired at the lowering; see above.
    "no/lov/2005-06-17-90": (0, 0),  # W-56: repaired at the lowering; see above.
    "no/lov/2007-06-29-75": (1, 0),  # W-67: verdipapirhandelloven § 4-3 -> § 4-2.
    "no/lov/2009-06-19-58": (1, 0),  # W-67: merverdiavgiftsloven § 7-9 -> § 7-8.
    "no/lov/2021-06-18-97": (1, 0),
}

#: W-54's per-firing verdict table, pinned (W-56).
#:
#: W-54 deliberately did NOT pin this: two of its ten rows were ``removal_wrong``
#: — proven destruction of in-force law — and pinning them would have frozen a
#: known defect as expected behaviour. W-56 repairs one of the two at the
#: lowering, which is the event that licenses the pin.
#:
#: One entry per surviving firing:
#:   op_id → (base_id, source_path, destination_path, verdict, occupant probe,
#:            the paths where the occupant's text survives IN THE REPLAY).
#:
#: The probe is the normalised opening of the removed occupant's text (W-54
#: ``.tmp/w54/survival.json``); the survival tuple is the honest observed answer
#: to "did this removal destroy live law", re-derived here rather than asserted
#: as a slogan.
#:
#: TRIPWIRE SEMANTICS — deliberately ASYMMETRIC (modelled on W-45's thirteen-id
#: pin):
#:   * a NEW op_id appearing in the corpus = alarm. The table is compared by
#:     equality, so an unadjudicated firing cannot land silently.
#:   * ``no/lovtid/2024-12-20-87:2`` (skattebetalingsloven § 8-2) WAS pinned here
#:     as ``removal_wrong`` on purpose — the corpus's last proven destruction of
#:     in-force law, W-54's finding, held open as W-58's designed handoff. W-61
#:     REMOVED it, and the removal is the whole point of that item, so read the
#:     history before re-adding anything to this table. W-58 recorded the root
#:     cause as a missing archive artifact and W-60 re-read it as a run-on part
#:     boundary; both were wrong. The repealing sentence ("§ 8-2 første ledd
#:     oppheves. Annet til femte ledd blir første til fjerde ledd.") was archived,
#:     indexed and applied all along, in ``no/lovtid/2008-12-12-100``, and simply
#:     did not LOWER: the unstructured repeal-then-shift production required the
#:     literal ``Nåværende`` in the shift sentence. With W-61's widening the
#:     repeal and its four-leg shift both lower, § 8-2's stale duplicate fourth
#:     ledd vacates, and the ``4 → 5`` leg no longer lands on an occupied node —
#:     so there is no firing left to adjudicate. The ``(0, 0)`` entry in
#:     ``_NO_OCCUPIED_DESTINATION_LAWS`` is what keeps a resurrection loud, and
#:     ``test_no_skattebetalingsloven_8_2_regulation_power_survives`` below pins
#:     the positive fact the firing used to destroy.
#:
#: With that row gone the wrong-list is EMPTY, and the tripwire flips polarity:
#: a green run now means "no adjudicated removal destroys live law", and ANY
#: growth of the wrong-list is a new destruction, not a known one.
_NO_OCCUPIED_DESTINATION_VERDICTS: dict[str, tuple[str, str, str, str, str, tuple[str, ...]]] = {
    "no/lovtid/2009-06-19-85:1": (
        "no/lov/2001-01-05-1",
        "section:12",
        "section:14",
        "removal_correct",
        "foretak som utøver vaktvirksomhet plikter å gi tillatelses og",
        ("section:16/subsection:1",),
    ),
    "no/lovtid/2009-06-19-85:2": (
        "no/lov/2001-01-05-1",
        "section:13",
        "section:15",
        "removal_correct",
        "departementet kan gi nærmere forskrifter til gjennomføring av loven",
        (),
    ),
    # ``no/lovtid/2024-06-14-34:3`` (privatskolelova § 2-2 fjerde -> femte ledd,
    # ``removal_correct``) stood here until W-98 removed the firing at the
    # lowering: ``no/lovtid/2007-06-29-92``'s "Kapittel 2 skal lyde:" now lands
    # as a whole-chapter re-enactment (every standing section carried), and the
    # re-enacted § 2-2 has four ledd, so the 2024 shift of the third and fourth
    # ledd finds its fifth slot free and nothing is cleared. The occupant that
    # row probed ("skolen må være registrert i einingsregisteret") is the
    # re-enacted § 2-2's SECOND ledd, where the published consolidation has it.
    "no/lovtid/2012-05-25-29:22": (
        "no/lov/2004-12-17-99",
        "chapter:5/section:21a",
        "chapter:5/section:20",
        "removal_correct",
        "ved overtredelse av rapporteringsplikten etter 16 kan forurensningsmyndighetene fatte",
        (),
    ),
    "no/lovtid/2012-05-25-29:24": (
        "no/lov/2004-12-17-99",
        "chapter:6/section:23",
        "chapter:5/section:22",
        "removal_correct",
        # The occupant is a heading-only § 22 shell in our tree, so there is no
        # body text to probe; the empty probe is skipped by the survival check.
        "",
        (),
    ),
    # ``:27`` -> ``:30`` and ``:106`` -> ``:109`` at W-74. The op_id is
    # ``f"{source_id}:{sequence}"`` over a per-document counter, and W-74's
    # accepted lead in this SAME instrument ("§§ 1-2 til 1-7 oppheves. Nåværende
    # § 1-8 blir ny § 1-2.") mints three ops ahead of both — two REPEALs and one
    # RENUMBER. Pure ordinal churn: same law, same source, same destination, same
    # occupant, same verdict.
    # ``:30`` -> ``:34`` and ``:109`` -> ``:120`` at W-98 (c), the same churn
    # again: the range expander now ENUMERATES "§§ 1-2 til 1-7" (four more
    # REPEALs, §§ 1-3–1-6, ahead of both) and "§§ 12-8 til 12-16 oppheves."
    # (seven more, §§ 12-9–12-15, ahead of the second). Same law, same source,
    # same destination, same occupant, same verdict.
    "no/lovtid/2015-04-10-17:34": (
        "no/lov/2005-06-10-44",
        "part:3/chapter:7/section:7-8",
        "part:2/chapter:2/section:2-4",
        "removal_correct",
        "utenlandsk forsikringsselskap kan gis konsesjon til å drive virksomhet",
        (),
    ),
    "no/lovtid/2015-04-10-17:120": (
        "no/lov/2005-06-10-44",
        "part:6/chapter:16/section:16-1",
        "part:4/chapter:9/section:9-1",
        "removal_correct",
        "bestemmelsene i dette kapittel gjelder for selskaper som yter",
        (),
    ),
    # ``no/lovtid/2024-12-20-87:2`` stood here, pinned ``removal_wrong``, until
    # W-61 removed the firing at the lowering. See the note above the table.
    "no/lovtid/2026-06-19-35:18": (
        "no/lov/2021-06-18-97",
        "chapter:10/section:10-17/subsection:4",
        "chapter:10/section:10-17/subsection:5",
        "removal_correct",
        "avgjørelser om godkjenning kan påklages til sentralt nivå i",
        (),
    ),
    # W-67's two new firings, both adjudicated on their own evidence rather than
    # entered because they are convenient. Both are ``removal_correct``, and they
    # are correct for DIFFERENT reasons, which is why the survival tuple differs.
    #
    # Verdipapirhandelloven: the occupant is not destroyed at all. Every one of
    # § 4-2's five ledd is still at its own address in the replay after the
    # renumber lands, and every one matches the published consolidation. The probe
    # is § 4-2 first ledd's OWN text and the survival tuple is the observed
    # address, so this row asserts the provision is in place rather than that some
    # string exists somewhere.
    "no/lovtid/2019-06-21-41:2": (
        "no/lov/2007-06-29-75",
        "part:2/chapter:4/section:4-3",
        "part:2/chapter:4/section:4-2",
        "removal_correct",
        "hvis en aksjeeiers andel av aksjer med tilknyttet stemmerett når overstiger eller",
        ("part:2/chapter:4/section:4-2/subsection:1",),
    ),
    # Merverdiavgiftsloven: the occupant IS destroyed, and destroying it is what
    # the act commands. ``no/lovtid/2022-03-11-8`` repeals § 7-8 in the same act
    # ("Nåværende § 7-8 oppheves."), and the removed text is absent from the
    # published consolidation too, so nothing in force is lost. Two divergence
    # rows CLOSE on this law with the change (256 -> 254).
    #
    # The probe is the § 7-8 HEADING, and the choice matters for the same reason
    # the skattebetalingsloven pin below is on an address SET. § 7-8's first ledd
    # opens "Departementet kan gi forskrift om at det ikke skal beregnes
    # merverdiavgift ved …", and § 7-6 carries that identical boilerplate — a
    # probe taken from the ledd hits § 7-6 in the replay AND in the consolidation
    # and so proves nothing either way. The heading names what § 7-8 was actually
    # about ("varer av utdannende, vitenskapelig og kulturell art") and is absent
    # from both sides, which is the discriminating measurement. The empty survival
    # tuple is the honest answer, not a missing one.
    # ``:25`` -> ``:29`` at W-98 (a): two repeated-noun leads earlier in the same
    # instrument ("§ 3-29 første ledd og nytt annet ledd skal lyde:", "§ 4-11
    # fjerde ledd og nytt femte ledd skal lyde:") mint two ops each ahead of it.
    # Same law, same source, same destination, same occupant, same verdict.
    "no/lovtid/2022-03-11-8:29": (
        "no/lov/2009-06-19-58",
        "chapter:7/section:7-9",
        "chapter:7/section:7-8",
        "removal_correct",
        "varer av utdannende vitenskapelig og kulturell art",
        (),
    ),
}

#: The vitneforsikring (tvisteloven § 24-8's witness-oath formula) — the live
#: provision W-54 proved the recovery destroyed, and the reason W-56 exists.
#: The replay carries the ledd sentence-split (an earlier amendment addressed
#: § 24-8's punktum individually), so the oath's opening sentence sits one step
#: below the ledd the consolidation prints as a single block. The ADDRESS that
#: matters is the ledd — ``subsection:5`` — and the divergence metric agrees:
#: the ``OPS_MISSING …/section:24-8/subsection:5`` row closes with this fix.
_TVISTELOVEN_OATH_PROBE = "før forklaring gis skal retten formane vitnet til å"
_TVISTELOVEN_OATH_ADDRESS = "part:5/chapter:24/section:24-8/subsection:5/sentence:1"

#: W-61's payoff probe. Skattebetalingsloven § 8-2's Skattedirektoratet
#: regulation power — the provision W-54 proved the ``(RENUMBER, dest_occupied)``
#: recovery destroyed, and the last such destruction in the corpus.
#:
#: § 8-3 carries an identically-worded regulation power of its own, which is why
#: the pin below is on the ADDRESS SET and not on "the probe finds something":
#: under the defect the probe still hit, on § 8-3, and that hit was the proof
#: § 8-2's copy was gone.
_SKATTEBETALINGSLOVEN_REGULATION_PROBE = "skattedirektoratet kan i forskrift gi nærmere regler om gjennomføringen"
_SKATTEBETALINGSLOVEN_8_2_ADDRESS = "part:2/chapter:8/section:8-2/subsection:5"
_SKATTEBETALINGSLOVEN_8_3_ADDRESS = "part:2/chapter:8/section:8-3/subsection:3"

#: W-74's payoff probe, and the reason W-67 could finally land.
#:
#: Husbankloven § 13 "Ikraftsetjing o.a" is the provision W-67's widening
#: destroyed. Its 2017 renumber (§ 10 -> § 13) is textually correct, but the slot
#: it writes into was occupied because the op that vacates it —
#: ``no/lovtid/2012-08-24-64``'s "§§ 10, 11 og 12 blir oppheva. Noverande § 13
#: blir ny § 10." — is a section-level repeal-then-shift run-on the unstructured
#: grammar refused. W-73 made the 2012 act commence; W-74 makes that block lower.
#: With both, § 13 is vacated in 2012, the 2017 renumber lands on a FREE
#: destination, and the firing does not happen at all.
#:
#: Pinned on the ADDRESS SET rather than on "the probe finds something", for the
#: same reason as the skattebetalingsloven pin above: what matters is that both
#: ledd of § 13 are where the consolidation puts them.
_HUSBANKLOVEN = "no/lov/2009-05-29-30"
_HUSBANKLOVEN_13_COMMENCEMENT_PROBE = "lova gjeld frå den tida kongen fastset"
_HUSBANKLOVEN_13_REPEAL_PROBE = "frå same tid vert lov"
_HUSBANKLOVEN_13_COMMENCEMENT_ADDRESS = "section:13/subsection:1"
_HUSBANKLOVEN_13_REPEAL_ADDRESS = "section:13/subsection:2"


#: W-66's two rescued provisions, and the reason its apply seam refuses instead
#: of recovering.
#:
#: The sibling-set ledd relabel mints 1,147 RENUMBER legs. 31 of them find their
#: destination still OCCUPIED when they run, and under the declared θ
#: (RENUMBER, dest_occupied) recovery two of those removals were adjudicated
#: ``removal_wrong`` — proven destruction of in-force law:
#:
#:   * straffeloven 2005 § 3 femte ledd ("Ved domfellelse etter gjenåpning …"),
#:     removed by ``no/lovtid/2008-03-07-4``'s "Nåværende annet til fjerde ledd
#:     blir tredje til femte ledd."; the provision stands at that very address in
#:     the published consolidation.
#:   * verdipapirhandelloven § 9-21 fjerde ledd (the konsolidering forskrift
#:     power), removed by ``no/lovtid/2021-04-30-26``'s "Nåværende tredje ledd
#:     blir nytt fjerde ledd."
#:
#: Both base editions ALREADY carry the amendment being replayed, so the relabel
#: lands a second time. That is not a fact any sentence grammar can see, so the
#: production refuses at apply rather than guessing at the parse:
#: ``no_replay_ledd_set_relabel_occupied_destination_refused``, no write, typed
#: rejection, and the refusal cascades down the vacate-before-occupy chain.
#:
#: These two pins hold the POSITIVE fact the way W-56, W-61 and W-74 hold theirs.
#: The negative half — that the corpus firing census does not grow — is held by
#: ``_NO_OCCUPIED_DESTINATION_VERDICTS`` above, which is still exactly 10 rows.
_STRAFFELOVEN_2005 = "no/lov/2005-05-20-28"
_STRAFFELOVEN_3_GJENAAPNING_PROBE = "ved domfellelse etter gjenåpning anvendes samme lovgivning"
_STRAFFELOVEN_3_GJENAAPNING_ADDRESS = "part:1/chapter:1/section:3/subsection:5"
_VERDIPAPIRHANDELLOVEN = "no/lov/2007-06-29-75"
_VERDIPAPIRHANDELLOVEN_9_21_PROBE = "departementet kan i forskrift gi nærmere regler om konsolidering"
_VERDIPAPIRHANDELLOVEN_9_21_ADDRESS = "part:3/chapter:9/chapter:II/section:9-21/subsection:4"


def _no_normalise_probe_text(text: str) -> str:
    import re as _re
    import unicodedata as _ud

    text = _ud.normalize("NFKC", text or "")
    text = _re.sub(r"\s+", " ", text)
    text = _re.sub(r"[^0-9a-zA-ZæøåÆØÅ ]", "", text)
    return text.strip().lower()


def _no_probe_hits(statute, probe: str) -> tuple[str, ...]:
    """Every address in ``statute`` whose own text contains ``probe``."""
    if not probe or statute is None:
        return ()

    def walk(node, path):
        for child in node.children:
            here = path + ((str(child.kind), child.label or ""),)
            if probe in _no_normalise_probe_text(child.text or ""):
                yield "/".join(f"{k}:{lbl}" for k, lbl in here)
            yield from walk(child, here)

    return tuple(walk(statute.body, ()))


@pytest.fixture(scope="module")
def _no_occupied_destination_replays():
    """Replay every law in the pinned table ONCE and share it across the pins."""
    if not _REAL_ARCHIVE.exists():
        pytest.skip("requires the local Lovdata archive (data/norway.farchive)")
    from lawvm.norway.index import build_no_amendment_index

    index = build_no_amendment_index(_REAL_ARCHIVE)
    return {
        base_id: replay_no_to_pit(
            base_id, as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index
        )
        for base_id in sorted(_NO_OCCUPIED_DESTINATION_LAWS)
    }


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_corpus_occupied_renumber_destination_verdicts_are_pinned(
    _no_occupied_destination_replays,
) -> None:
    """Corpus pin (W-56, deferred from W-54): each adjudicated
    ``(RENUMBER, dest_occupied)`` firing has the effect on the occupant's text
    that W-54 recorded — re-derived from a live replay, not asserted.

    SCOPE, corrected at W-72. This test replays the laws in
    ``_NO_OCCUPIED_DESTINATION_LAWS`` and only those, so it owns EFFECT, not
    POPULATION. It used to say "every firing in the corpus", which was false by
    nine laws out of 783 and is how W-67's husbankloven destruction passed a
    green ladder. The population half is now proven separately, over a sweep of
    all 783, in
    ``test_no_corpus_wide_occupied_destination_firings_are_all_adjudicated``;
    the equality below is what makes the two agree on the same event set.

    Read the asymmetry on ``_NO_OCCUPIED_DESTINATION_VERDICTS`` before touching
    this test: one row was pinned WRONG on purpose, and W-61 removed it.
    """
    observed: dict[str, tuple[str, str, str]] = {}
    for base_id, replay in sorted(_no_occupied_destination_replays.items()):
        assert replay.error is None, (base_id, replay.error)
        for a in replay.adjudications:
            if a.kind != _OCCUPIED_DESTINATION_ADJUDICATION_KIND:
                continue
            assert a.op_id is not None, base_id
            observed[a.op_id] = (
                base_id,
                str(a.detail.get("source_path")),
                str(a.detail.get("destination_path")),
            )

    expected = {
        op_id: (base_id, source, destination)
        for op_id, (base_id, source, destination, _v, _p, _s) in
        _NO_OCCUPIED_DESTINATION_VERDICTS.items()
    }
    assert observed == expected

    for op_id, (base_id, _src, _dst, verdict, probe, survives) in sorted(
        _NO_OCCUPIED_DESTINATION_VERDICTS.items()
    ):
        replayed = _no_occupied_destination_replays[base_id].replayed
        assert replayed is not None, base_id
        assert _no_probe_hits(replayed, probe) == survives, (op_id, verdict)

    wrong = sorted(
        op_id
        for op_id, (_b, _s, _d, verdict, _p, _sv) in _NO_OCCUPIED_DESTINATION_VERDICTS.items()
        if verdict == "removal_wrong"
    )
    # W-58's tripwire, flipped by W-61 (see the note on the table). The list is
    # EMPTY: no adjudicated ``(RENUMBER, dest_occupied)`` recovery in the corpus
    # destroys in-force law. Any growth is a NEW destruction — adjudicate it
    # W-54-style (source text, occupant provenance, verdict) before touching this.
    assert wrong == []


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_tvisteloven_vitneforsikring_survives_the_two_limb_ledd_shift(
    _no_occupied_destination_replays,
) -> None:
    """W-56's payoff, pinned at the corpus: tvisteloven § 24-8's witness-oath
    ledd is present in the replay, at the address the consolidation puts it.

    W-54's firing 9: ``no/lovtid/2024-12-13-78``'s ``"Nåværende tredje og fjerde
    ledd blir fjerde og nytt femte ledd."`` lowered only its ``3 → 4`` limb, and
    the occupied-destination recovery removed the oath outright
    (``OPS_MISSING part:5/chapter:24/section:24-8/subsection:5``).
    """
    replay = _no_occupied_destination_replays["no/lov/2005-06-17-90"]
    assert replay.replayed is not None
    hits = _no_probe_hits(replay.replayed, _TVISTELOVEN_OATH_PROBE)
    assert hits == (_TVISTELOVEN_OATH_ADDRESS,)
    # And the ledd itself exists — before W-56 the recovery removed the whole
    # node, so there was no ``subsection:5`` under § 24-8 at all.
    assert hits[0].rsplit("/", 1)[0] == "part:5/chapter:24/section:24-8/subsection:5"
    assert [
        a.op_id
        for a in replay.adjudications
        if a.kind == _OCCUPIED_DESTINATION_ADJUDICATION_KIND
    ] == []


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_skattebetalingsloven_8_2_regulation_power_survives(
    _no_occupied_destination_replays,
) -> None:
    """W-61's payoff, pinned at the corpus: skattebetalingsloven § 8-2's
    Skattedirektoratet regulation power is present in the replay, at the address
    the consolidation puts it, and § 8-2 is the FOUR-ledd section the later
    ledd-targeted amendments have always read on.

    W-54's firing 10 — the last ``removal_wrong`` in the corpus.
    ``no/lovtid/2024-12-20-87``'s § 8-2 block lowered both its legs correctly, but
    our § 8-2 still carried five ledd with a stale duplicate at four, because
    ``no/lovtid/2008-12-12-100``'s "§ 8-2 første ledd oppheves. Annet til femte
    ledd blir første til fjerde ledd." never lowered. So the ``4 → 5`` leg landed
    on the occupant and the recovery removed it
    (``MISMATCH part:2/chapter:8/section:8-2/subsection:5``).
    """
    replay = _no_occupied_destination_replays["no/lov/2005-06-17-67"]
    assert replay.replayed is not None
    hits = _no_probe_hits(replay.replayed, _SKATTEBETALINGSLOVEN_REGULATION_PROBE)
    # Both copies present, § 8-2's restored alongside § 8-3's own. Under the
    # defect this was ``(§ 8-3's address,)`` alone.
    assert hits == (_SKATTEBETALINGSLOVEN_8_2_ADDRESS, _SKATTEBETALINGSLOVEN_8_3_ADDRESS)
    assert [
        a.op_id
        for a in replay.adjudications
        if a.kind == _OCCUPIED_DESTINATION_ADJUDICATION_KIND
    ] == []


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_husbankloven_13_commencement_provision_survives() -> None:
    """W-74's payoff, pinned at the corpus: husbankloven § 13 "Ikraftsetjing o.a"
    survives the replay, at the addresses the consolidation puts it, and NO
    occupied-destination recovery fires on this law at all.

    This is the positive fact behind the missing row in
    ``_NO_OCCUPIED_DESTINATION_LAWS``. W-67 measured a ``removal_wrong`` here and
    was held back for it; the repair is at the LOWERING, not in the recovery, so
    the assertion that matters is that the recovery has nothing to fire on.

    Both probes must hit, and the firing list must be empty. A regression in
    either direction — the provision vanishing, or the recovery waking up — fails
    here rather than silently passing a shorter table.
    """
    from lawvm.norway.index import build_no_amendment_index

    index = build_no_amendment_index(_REAL_ARCHIVE)
    replay = replay_no_to_pit(
        _HUSBANKLOVEN, as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index
    )
    assert replay.error is None
    assert replay.replayed is not None
    assert _no_probe_hits(replay.replayed, _HUSBANKLOVEN_13_COMMENCEMENT_PROBE) == (
        _HUSBANKLOVEN_13_COMMENCEMENT_ADDRESS,
    )
    assert _no_probe_hits(replay.replayed, _HUSBANKLOVEN_13_REPEAL_PROBE) == (
        _HUSBANKLOVEN_13_REPEAL_ADDRESS,
    )
    assert [
        a.op_id
        for a in replay.adjudications
        if a.kind == _OCCUPIED_DESTINATION_ADJUDICATION_KIND
    ] == []


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_corpus_occupied_renumber_destinations_are_all_declared(
    _no_occupied_destination_replays,
) -> None:
    """Corpus pin (W-52): every occupied-destination removal in the corpus is
    declared on its receipt, and no replay is blocked by the observed-write
    audit any more.

    ``no/lov/2004-12-17-99`` (klimakvoteloven) and ``no/lov/2005-06-10-44``
    were the only two laws in the corpus whose strict replay died with
    ``Failed to apply ops: Norway observed-write audit violation after
    renumber``; both now replay to a statute. The other five laws in the table
    are the same defect class that never tripped the audit because the occupant
    stood at the destination leg — their receipts are unchanged, which is what
    the ``0`` collateral count pins.

    W-56 moved the total from 10 to 9: see ``_NO_OCCUPIED_DESTINATION_LAWS`` for
    why tvisteloven's row is now ``(0, 0)``.
    """
    observed: dict[str, tuple[int, int]] = {}
    for base_id, replay in sorted(_no_occupied_destination_replays.items()):
        assert replay.error is None, (base_id, replay.error)
        assert replay.replayed is not None, base_id
        firings = sum(
            1
            for a in replay.adjudications
            if a.kind == _OCCUPIED_DESTINATION_ADJUDICATION_KIND
        )
        collateral = [
            r
            for r in replay.write_receipts
            if r.action == "renumber" and r.removed_paths
        ]
        observed[base_id] = (firings, len(collateral))
        # Every collateral declaration is owned by the recovery rule.
        for r in collateral:
            assert _OCCUPIED_DESTINATION_RULE_ID in r.recovery_rule_ids, (base_id, r.op_id)
        # No landed write in these laws escapes its receipt.
        assert [
            a.op_id for a in replay.observed_write_audits if a.audit_status == "violation"
        ] == [], base_id

    assert observed == _NO_OCCUPIED_DESTINATION_LAWS, observed
    # W-52 measured 10 firings, W-56 repaired one (tvisteloven § 24-8) and W-61
    # one more (skattebetalingsloven § 8-2) — both at the LOWERING, so the
    # recovery simply has nothing left to fire on there.
    # W-67 raises the firing total 8 -> 10 (two new laws enter the table above,
    # both ``removal_correct``); the collateral count is unmoved at 3, because
    # neither new firing removes anything the receipt does not already declare.
    # W-98 lowers the total 10 -> 9: privatskolelova's firing
    # (``no/lovtid/2024-06-14-34:3``) is repaired at the LOWERING — the 2007
    # "Kapittel 2 skal lyde:" now lands as a whole-chapter re-enactment, so the
    # 2024 shift finds its destination free and the recovery has nothing to
    # fire on. The collateral count is unmoved at 3 (that row was ``(1, 0)``).
    assert sum(f for f, _ in observed.values()) == 9
    assert sum(c for _, c in observed.values()) == 3
    # The two tables must agree on the firing population, so neither can drift
    # alone: one row per firing, keyed by op_id.
    assert sum(f for f, _ in observed.values()) == len(_NO_OCCUPIED_DESTINATION_VERDICTS)


# ---- W-72: the sweep that makes the two pins above CORPUS-WIDE ---------------
#
# Everything above this line replays the nine laws in
# ``_NO_OCCUPIED_DESTINATION_LAWS`` and nothing else. That is the right shape for
# the SURVIVAL probes — they need a real replayed tree per law — but on its own it
# licenses no corpus-wide claim, and until W-72 the docstrings made one anyway.
#
# W-67 is what that cost. Its widening lowered a renumber that destroyed
# husbankloven § 13, husbankloven was not on the nine-law list, and the whole
# ladder stayed GREEN with a destruction in the corpus. The gap was not that the
# list was too short; it was that the list was HANDWRITTEN, so it could only ever
# describe firings someone had already found.
#
# The repair is a full sweep of all 783 base laws, run out of band by
# ``scripts/inventory_no_occupied_destination_sweep.py`` (~10 CPU-minutes, which
# the norway shard does not have) and committed as a baseline. What makes the
# cached number trustworthy is the receipt it carries: the sweep records the
# LOGICAL content of every Norway corpus plane and the sha256 of every source file
# in the static import closure of the replay path, and the test below recomputes
# both in ~2.5s. Corpus moved, or code moved, and the test FAILS with a regenerate
# instruction instead of passing on a measurement of something else. The
# code half is not decoration: W-67 did not touch the archive, so a corpus-only
# receipt would have gone on passing exactly as the nine-law list did.
#
# The sweep is exact over 779 of the 783 and names the other four rather than
# rounding them off — see the blind-spot pin below, which is the same discipline
# applied to the sweep's own limits that the sweep applies to the nine-law list.

_SWEEP_SCRIPT_PATH = _REPO_ROOT / "scripts" / "inventory_no_occupied_destination_sweep.py"

#: The known-incomplete-base hazard census (W-73's rider (d), pinned at W-72).
#:
#: A base is KNOWN-INCOMPLETE when its own replay receipted at least one SKIPPED
#: amendment — the system already holds a receipt saying "this is not the whole
#: law" — and a write is DESTRUCTIVE when its landed footprint removes, replaces
#: or renumbers existing content. Applying a correct op to an incomplete base is
#: precisely how husbankloven § 13 was destroyed, so the intersection is the
#: sharpest hazard surface the corpus has.
#:
#: READ THE POLARITY. This is a census receipt, not a licence: 161 laws taking
#: destructive writes into a base the system knows is incomplete is a finding
#: held open, not expected behaviour that has been blessed. W-72 deliberately
#: does NOT refuse those writes — that is a product-behaviour change with its own
#: blast radius — it only stops the number moving in silence. Growth means the
#: hazard surface grew and wants a reading; shrinkage means an item repaired a
#: base, and the ledger should say which.
#:
#: W-73 measured 163 / 3,737 / 159 over 64 laws across 782 bases. At this base it
#: is 161 / 3,713 / 167 over 65 across 783, and the whole delta is attributable:
#: the three laws W-73 moved out of ``blocked_contingent``
#: (``2015-02-13-9``, ``2015-06-19-70``, ``2020-06-19-77``) LEAVE the hazard set,
#: ``no/lov/2020-05-07-40`` ENTERS it by gaining a destructive write from W-67's
#: widening, and 163 - 3 + 1 = 161 conserves exactly.
_NO_INCOMPLETE_BASE_HAZARD = {
    # 198 -> 199 at W-66: ``no/lov/2017-06-16-53`` ENTERS the amended-law
    # population (783 -> 784 base laws with sources) because the sibling-set
    # relabel gives it its first lowered op, and it arrives known-incomplete.
    # 199 -> 201 at W-66c, and it is the SAME two laws that leave the scan
    # candidate set in the same landing: ``no/lov/2010-06-04-21`` and
    # ``no/lov/2011-06-24-39``. The punktum-depth repeal gives
    # ``no/lovtid/2013-01-11-3`` (commencement "fra den tid Kongen bestemmer")
    # its first lowered ops against both, so both replays now receipt a
    # CONTINGENT skip and both become known-incomplete. Nothing leaves. This is
    # a base becoming OBSERVABLE rather than a new hazard being created — the
    # contingent act always amended them.
    # 201 -> 202 at W-98, the W-66c mechanism once more: ``no/lov/2004-03-26-17``
    # takes its first lowered op ever from ``no/lovtid/2016-12-16-91`` (the
    # print-era ``bokstav d)`` spelling, W-98 (d)), an instrument whose
    # commencement is CONTINGENT, so its replay now receipts a contingent skip
    # and it becomes known-incomplete. It leaves the scan candidate set in the
    # same landing (see ``tests/test_norway_verify.py``).
    # 202 -> 190 at W-100 (2026-09-05), and for the first time the count moves
    # DOWN by commencement rather than up by lowering: the section-scoped
    # commencement lane and the title-cited citation form date acts whose
    # contingent skip was what made twelve bases known-incomplete
    # (``no/lovtid/2013-01-11-3`` alone held ``no/lov/2010-06-04-21`` and
    # ``no/lov/2011-06-24-39`` here since W-66c). Two enter
    # (``no/lov/2017-06-16-56``, ``no/lov/2020-04-24-31``): their acts now land
    # per-section dates and skip the rest with a per-op contingent receipt,
    # which is what makes an incomplete base observable.
    "incomplete_bases": 190,
    # 265 -> 266 and 161 -> 162 at W-69c, and it is ONE law ENTERING the census:
    # ``no/lov/2009-06-19-44``. It was already counted incomplete (four
    # `contingent` skips, which the replay receipts before it applies anything,
    # so ``incomplete_bases`` is unchanged at 199) but it aborted mid-apply and
    # therefore took no writes at all. Now that it replays it takes 7, so it
    # joins both the destructive-write population and the intersection. This is
    # a law becoming OBSERVABLE, not a new hazard being created — the same
    # movement W-72's blind-spot narrative said to expect the moment one of the
    # four aborting laws was repaired.
    # 266 -> 265 at W-86, and the leaver is not a corpus event but W-85's
    # op-plane withdrawal finally reaching this baseline (the sweep could not
    # be retaken at W-85 because the corpus digests were already stale with
    # the capture drift — item 92's charter): endringslov
    # ``no/lov/2012-04-27-22`` loses its ONLY destructive write, the withdrawn
    # defective act ``no/lovtid/2012-12-07-71``'s REPLACE of its § 29 — the
    # over-application W-85 existed to close — and drops to zero. It was never
    # a hazard-intersection member (not known-incomplete), so ``hazard_bases``
    # and the membership digest below move for a different, single-row reason.
    # 265 -> 267 at W-100: two laws take their first destructive writes from
    # acts the section-scoped lane dated.
    # 267 -> 268 at W-101: folkehøgskoleloven ``no/lov/2025-06-20-99`` takes
    # its first (and only) write, the ``kap4`` chapter-heading REPLACE of
    # ``no/lovtid/2026-06-19-59`` that lowers now — a heading merge, nothing
    # removed. The base-law population is 789 -> 790 for the same reason.
    "bases_with_destructive_writes": 268,
    # 162 -> 164 at W-66c: the two laws named in the ``incomplete_bases`` note
    # above ENTER the intersection. Both already took destructive writes (6 and
    # 12 of them), so they arrive with a full row rather than a zero one; nothing
    # leaves, and ``hazard_by_skip_kind`` moves by the same two under
    # ``contingent``.
    # 164 -> 165 at W-98: the law named in the ``incomplete_bases`` note above
    # ENTERS the intersection with a [4, 0] row (four writes, none removing).
    # 165 -> 156 at W-100: nine of the twelve bases that stopped being
    # known-incomplete (note above) were in the intersection; the two entrants
    # arrive with rows. See the sweep note in ledger item 100.
    "hazard_bases": 156,
    # 3,713 -> 3,706 at W-75, and exactly one law moves: ``no/lov/2008-06-27-71``
    # [73, 2] -> [66, 2]. Refusing the word-substitution address lists stops seven
    # REPLACEs that had been writing the amendment's own prose into plan- og
    # bygningsloven, a `blocked_contingent` law no scan candidate covers, so this
    # census was the ONLY pin that could see them. Membership, the content-removing
    # count and the incomplete/destructive populations are all unchanged; the other
    # two laws whose text W-75 moves are not known-incomplete, so their writes were
    # never in this intersection. Signed off 2026-08-12.
    #
    # 3,706 -> 3,809 at W-66, across 26 of the 161 hazard laws and no membership
    # change. A RENUMBER is a destructive write by this census's definition (it
    # moves existing content), and the sibling-set relabel mints 1,147 of them
    # corpus-wide; 103 land in laws that are known-incomplete. That is the hazard
    # surface growing, honestly, and it is why the census is a pin and not a
    # licence.
    #
    # 3,809 -> 3,810 at W-69a, and it is exactly ONE write on ONE law:
    # ``no/lov/2008-06-27-71`` [79, 2] -> [80, 2]. The addressed word substitution
    # now lowers, and a landed ``TEXT_PATCH`` records a REPLACED path, so every
    # one of them is destructive by this census's definition. W-69a lands 15
    # corpus-wide; 14 of them are on ``no/lov/2015-06-19-70`` and
    # ``no/lov/2020-04-17-29``, which are NOT known-incomplete, so this census
    # cannot see them — the 15th is plan- og bygningsloven § 12-12 femte ledd
    # (``gjennom elektroniske medier`` -> ``på internett``), and that law is
    # `blocked_contingent`, i.e. exactly the posture this pin exists to watch.
    # Content-removing is UNCHANGED at 168 over the same 65 laws: a text
    # substitution replaces, it never removes. Signed off 2026-08-12.
    #
    # 3,810 -> 3,816 at W-69b, and again it is ONE law:
    # ``no/lov/2008-06-27-71`` [80, 2] -> [86, 2]. Putting ``setning/N``
    # addresses in scope lands 17 substitutions corpus-wide; 11 are on
    # ``no/lov/2015-06-19-70`` and ``no/lov/2020-04-17-29``, which are not
    # known-incomplete, and the other 6 are plan- og bygningsloven's remaining
    # ``gjennom elektroniske medier`` -> ``på internett`` addresses (§§ 8-5
    # femte, 11-12 andre, 11-14 første, 11-15 andre, 12-8 tredje, 12-10 første
    # ledd), the sentence-depth siblings of the § 12-12 address W-69a landed on
    # the same `blocked_contingent` law.
    #
    # This is the pin doing its job rather than a new hazard: the writes go into
    # a base the system knows is incomplete, but each one proved its announced
    # term uniquely present as a whole word in the ADDRESSED punktum before
    # writing, and a term substitution replaces without removing — so the
    # content-removing count is unchanged at 168 over the same 65 laws, and
    # nothing in the base's incompleteness can turn one of these into a wrong
    # removal. The full-corpus statute diff for W-69b confirms it from the other
    # side: 781 of 784 statutes byte-identical, and the 17 word-level changes on
    # the other 3 are exactly the 17 announced substitutions.
    #
    # 3,816 -> 3,823 at W-69c: the 7 writes ``no/lov/2009-06-19-44`` takes now
    # that it replays (3 REPLACEs, 3 INSERTs of which 2 recover onto an occupant,
    # 1 further INSERT). NONE of them removes content — the law's per-law row is
    # ``[7, 0]`` — so ``hazard_content_removing_writes`` and
    # ``hazard_bases_removing_content`` below are unchanged. Its six relocation
    # legs, which WOULD have been destructive, all refuse typed
    # (``no_replay_relocation_order_unprovable_refused``) and write nothing.
    #
    # 3,823 -> 3,827 at W-70b, and it is the SAME law again: ``[7, 0] -> [11, 0]``.
    # With the §3 attribute's destination section repaired, all SIX relocation
    # legs land, and a RENUMBER is destructive by this census's definition — but
    # two of the INSERTs stop being destructive at the same time, because they now
    # arrive at slots the shift genuinely vacated instead of recovering onto an
    # occupant. 7 + 6 - 2 = 11, which is the whole delta; no other law's row
    # moves and membership is unchanged. Content-removing stays 0 on this law and
    # 168 corpus-wide: a relocation moves content, it never removes any, and the
    # two writes that stop being destructive were REPLACEMENTS, which record
    # ``replaced_paths`` and never ``removed_paths``.
    #
    # 3,827 -> 3,828 at W-66b, and it is ONE law: ``no/lov/2008-05-15-35``
    # ``[262, 8] -> [263, 8]``. The delta is +1 but the movement underneath it is
    # +3 and -2, and both halves are W-66's own mechanism one depth word down:
    #   * +3 RENUMBER, the three punktum-relabel legs that LAND on this law
    #     (``§73/ledd/4/setning/3->4`` from ``no/lovtid/2009-12-18-132``, and
    #     ``§92/ledd/4/setning/5->6`` and ``4->5`` from ``no/lovtid/2018-04-20-9``).
    #     A RENUMBER is destructive by this census's definition because it moves
    #     existing content; none of the three REMOVES any, so the per-law
    #     content-removing figure stays 8 and the corpus figure stays 168.
    #   * -2 REPLACE, because a relabel that vacates a slot before the co-located
    #     payload lands turns an overwrite into an insertion. One is the shipped
    #     ``_promote_no_replace_with_following_renumber_insert`` waking up (this
    #     law's ``no_parse_replace_promoted_to_insert_for_same_target_renumber``
    #     goes 4 -> 5); the other is an INSERT that no longer has to recover onto
    #     an occupant (``no_replay_insert_occupied_target_replaced`` 10 -> 9).
    #     Corpus-wide the same two counters move +9 and -4.
    # Membership is unchanged: the only other laws this item touches at all are
    # ``no/lov/2004-12-10-77`` (2 ops, both ``replay_unresolved_target``, so it
    # takes no write and enters no population here) and ``no/lov/2005-06-17-62``
    # (2 further ops behind a PRE-EXISTING mid-apply abort, same error string, so
    # it still takes no writes). Signed off 2026-08-14.
    #
    # 3,828 -> 3,875 at W-66c (+47), and this is the largest move this census
    # has made since W-66 — read the polarity above before reading the number.
    # It decomposes exactly, and the two halves are different in kind:
    #   * +29 across 24 laws already in the intersection, every one a landed
    #     punktum-depth REPEAL. A repeal is destructive by this census's
    #     definition twice over: it removes existing content, and unlike a
    #     RENUMBER it does not put it back anywhere.
    #   * +18 arriving whole with the two ENTERING laws — ``no/lov/2010-06-04-21``
    #     [6, 0] and ``no/lov/2011-06-24-39`` [12, 2]. Those writes are not new;
    #     the laws are new to the census, for the reason the ``incomplete_bases``
    #     note gives.
    # 29 + 18 = 47, and no law's row moves for any other reason.
    #
    # 3,875 -> 3,880 at W-76 (+5), and it is the SMALLEST possible reading of a
    # new lowering family: every other key of this census is unchanged, including
    # ``hazard_content_removing_writes`` (198) and ``hazard_bases_removing_
    # content`` (77). The item-depth (bokstav / nr.) sibling-set relabel mints 67
    # RENUMBER legs, of which EIGHT are picked up by any base law's replay; six
    # land and two refuse at apply under W-66's occupied-destination guard. The
    # six land on three laws already inside the intersection, and the row deltas
    # are exactly:
    #   * ``no/lov/2005-06-17-90``  [49, 0] -> [52, 0]  (+3, tvisteloven § 6-2
    #     første ledd bokstav c/d/e shifted one letter; text preserved verbatim,
    #     nothing removed);
    #   * ``no/lov/2007-12-21-119`` [49, 4] -> [50, 4]  (+2 RENUMBER, -1 REPLACE:
    #     the shipped ``_promote_no_replace_with_following_renumber_insert``
    #     waking up on the co-located ``bokstav g`` payload, exactly as it did at
    #     W-70b);
    #   * ``no/lov/2005-05-20-28``  [130, 3] -> [131, 3] (+1).
    # 3 + 1 + 1 = 5, membership is unchanged (164 hazard bases, both before and
    # after), and the content-removing column does NOT move — a RENUMBER moves
    # content and puts it back, which is the polarity this census was built to
    # separate. The corpus-wide ``remove_at`` probe agrees: 240 -> 240
    # content-removing writes, 307 -> 307 sentence removals.
    #
    # 3,880 -> 3,885 at W-77, and NONE of the five is a W-77 op. The item-depth
    # newness payload production mints INSERTs, which CREATE and are therefore
    # not destructive by this census's definition. What the five are is
    # downstream REPLACEs that were REFUSED at base with
    # ``replay_unresolved_target`` because the bokstav/nr. they address did not
    # exist, and that now resolve because W-77 created the slot the instrument
    # commanded. Membership is unchanged (164 hazard bases), and the row deltas
    # are exactly:
    #   * ``no/lov/2005-06-17-67``  [314, 12] -> [316, 12]  (+2: the later
    #     revisions of skattebetalingsloven § 5-6 første ledd bokstav g and
    #     § 10-40 første ledd bokstav d, both landing on items W-77 created);
    #   * ``no/lov/2008-05-15-35``  [266, 10] -> [269, 10]  (+3: utlendingsloven
    #     § 105 første ledd bokstav f and TWO further writes at § 17 første ledd
    #     bokstav n — see the W-77 report's collateral finding, one of which is a
    #     PRE-EXISTING mis-lowering of ``no/lovtid/2026-06-12-31``'s substitution
    #     announcement that this production newly makes reachable).
    # 2 + 3 = 5, and the content-removing column does NOT move on either law: a
    # REPLACE onto text this same replay just created removes nothing that was in
    # force at base. The corpus-wide ``remove_at`` probe agrees: 240 -> 240
    # content-removing writes, 2,107 -> 2,107 ``remove_at`` calls, 307 -> 307
    # sentence removals.
    #
    # 3,885 -> 3,870 at W-78 (-15), and this is the FIRST SHRINKAGE this census
    # has recorded — read the polarity note above: shrinkage means an item
    # repaired a base, and this is which. ONE law's row moves,
    # ``no/lov/2008-05-15-35`` [269, 10] -> [254, 10], and the whole delta is the
    # substitution-announcement mis-lowering W-77's collateral finding named.
    # ``no/lovtid/2026-06-12-31`` writes "Følgende steder endres ordene «X» til
    # «Y»: <address list>"; W-69a's announcement opener enumerated the noun after
    # ``følgende`` and did not contain ``steder``, so the node fell into the
    # structured payload lane, which read its ``data-change-part`` list as
    # REPLACE targets and the announcement sentence itself as their payload.
    # 23 of those defective REPLACEs LANDED on utlendingsloven, a
    # `blocked_contingent` law no scan candidate covers — this census and the
    # corpus statute diff were the only pins that could see them at all. The 23
    # withdraw and 8 correct addressed TEXT_PATCHes take their place (each having
    # proved its announced FROM term uniquely present as a whole word before
    # writing), which is 23 - 8 = 15.
    # The content-removing column does NOT move, on this law (10) or corpus-wide
    # (198 over 77 laws): the withdrawn writes were REPLACEs, which record
    # ``replaced_paths`` and never ``removed_paths``. The corpus-wide
    # ``remove_at`` probe agrees: 240 -> 240 content-removing writes, 2,107 ->
    # 2,107 ``remove_at`` calls, 307 -> 307 sentence removals, and the removed-node
    # multiset on this law is identical at 134 before and after.
    #
    # 3,870 -> 3,847 at W-79 (-23), the SECOND shrinkage and the general closure
    # of the class W-78 closed one dialect of: the structured lane's own-text
    # fallback now refuses unless the node declares its own payload. EIGHT rows
    # move, all downward, all in the destructive column:
    # ``no/lov/2002-06-21-45`` [67, 2] -> [66, 2] ("Nåværende § 9 d blir § 9 e,
    # og overskriften skal lyde:" written over § 9 d, whose seven-ledd body
    # returns), ``no/lov/2005-06-17-67`` [316, 12] -> [315, 12],
    # ``no/lov/2008-05-15-35`` [254, 10] -> [249, 10] (7 withdrawn REPLACEs, 2
    # addressed substitutions newly landing once the real text they patch is
    # back), ``no/lov/2009-06-19-58`` [207, 20] -> [204, 20],
    # ``no/lov/2016-05-27-14`` [142, 7] -> [141, 7], ``no/lov/2016-08-12-77``
    # [31, 2] -> [25, 2] (six "Nåværende § 66 blir § 84."-shaped relabel
    # announcements written over §§ 66-70 and § 64 andre ledd, 32 child nodes
    # returning), ``no/lov/2023-06-09-30`` [20, 0] -> [19, 0] and
    # ``no/lov/2025-04-25-12`` [8, 0] -> [3, 0].
    # The content-removing column does NOT move, on any row or corpus-wide
    # (198 over 77 laws), for the same reason as W-78: every withdrawn write was
    # a REPLACE, which records ``replaced_paths`` and never ``removed_paths``.
    # Corpus-wide content-removing writes hold at 240.
    #
    # 3,847 -> 3,850 at W-82 (+3), the recovery of the cost W-79 owned. ONE row
    # moves, ``no/lov/2008-05-15-35`` [249, 10] -> [252, 10], and the whole delta
    # is ``no/lovtid/2025-04-04-7``'s three "§ 105/106 første ledd bokstav X
    # første punktum skal lyde:" nodes: each declares a payload W-79's gate
    # accepts and keeps it in a single ``li`` the flattener steps over, and each
    # names ONE sub-section-level address, so arity on both sides proves the
    # extent. All three are REPLACEs of a FIRST PUNKTUM: § 105 (1) b's second
    # sentence survives as ``sentence:2`` beside the new first, § 106 (1) e (the
    # provision the amendment calls bokstav d, relabelled by a later act) the
    # same, and § 106 (1) b's replacement is byte-identical to the text already
    # there. ZERO paths removed corpus-wide.
    # The content-removing column does NOT move, on this row (10) or corpus-wide
    # (198 over 77 laws), for the same reason again: a REPLACE records
    # ``replaced_paths`` and never ``removed_paths``. Corpus-wide content-removing
    # writes hold at 240.
    #
    # 3,850 -> 3,853 at W-84 (+3), and the +3 hides a REPAIR. ONE row moves,
    # ``no/lov/2002-06-21-45`` [66, 2] -> [69, 2], and the arithmetic is +4 -1:
    # the rectified re-announcement of ``no/lovtid/2024-03-15-10`` carries a
    # renumber sentence the superseded announcement OMITTED ("Nåværende andre til
    # femte ledd blir nye § 9 tredje til sjette ledd."), which lowers to four
    # RENUMBERs — destructive by this census's definition because a renumber moves
    # existing content — while the act's INSERT of § 9's new second ledd stops
    # being destructive, because it now arrives at a slot the shift genuinely
    # vacated instead of recovering onto the live occupant.
    # That recovery is what the omission cost: at base the INSERT replaced
    # yrkestransportlova § 9 andre ledd (the ``miljøskadeleg utslepp`` provision)
    # and the ledd was GONE from the replayed law. Post, § 9 carries six ledd in
    # the order Lovdata's own consolidation carries them, the destroyed provision
    # back at (3). The content-removing column does not move, on this row (2) or
    # corpus-wide (198 over 77 laws): a RENUMBER moves content and never removes
    # it, and the withdrawn write was a REPLACE, which records ``replaced_paths``.
    # Corpus-wide content-removing writes hold at 240.
    #
    # 3,853 -> 3,852 at W-86 (the 2026-08-14 capture re-pin), and the -1 is
    # NOT the capture: it is W-85's withdrawal reaching this baseline, ONE row
    # moving — statsborgerloven ``no/lov/2005-06-10-51`` [46, 5] -> [45, 5].
    # The withdrawn defective act ``no/lovtid/2012-12-07-71`` used to land a
    # write on it that byte-duplicated its re-sanctioned replacement's
    # (``no/lovtid/2013-01-11-1``, which still applies); with the duplicate
    # gone the statute is byte-invariant — W-85 proved that at 4 PITs — and
    # the census counts one write fewer. The CAPTURE drift itself moves
    # NOTHING here: the lov lanes are digest-identical, the five departed
    # consolidations are oracle-side artifacts no replay reads, and the 51 new
    # forskrift announcements all parse benign (no commencement date moves, so
    # no op lands or unlands at as_of). Firings hold at 10 over the same 7
    # laws, verdict table untouched, membership unchanged at 164, and the
    # content-removing column does not move (198 over 77 laws).
    #
    # 3,852 -> 3,942 at W-98 (+90), across 31 of the 165 hazard laws plus the
    # entrant, and it is the pre-2001 lead grammar's nine productions landing on
    # known-incomplete bases: whole-chapter re-enactments (a REPLACE of a chapter
    # is one destructive write; privatskolelova ``no/lov/2003-07-04-84`` [81, 1]
    # -> [97, 2] carries three of them plus two item payloads and a nynorsk
    # repeal), chapter-heading merges, enumerated section ranges (§§ 12-9–12-15
    # on ``no/lov/2005-06-10-44`` [87, 10] -> [90, 14]), nynorsk ledd repeals,
    # unqualified single-ledd shifts and single-article item payloads. The
    # content-removing column moves for the FIRST time since W-66c, 198 -> 219
    # over 77 -> 81 laws, and every removing write is a REPEAL the source
    # commands by name (a range member, a nynorsk ``vert oppheva`` ledd) or the
    # repeal half of a repeal-then-reenact lead — never a recovery clearing an
    # occupant: the two W-98 re-enactment productions REFUSE an occupied target
    # rather than take the θ recovery, and their apply-plane refusals are in
    # ``_NO_SKIP_ADJUDICATION_KINDS``.
    #
    # 3,942 -> 3,953 at W-99 (+11), across nine of the 165 hazard laws and no
    # entrant: the period-less citation grammar and the address-after-citation
    # lead binding ops to the act their lead names — verdipapirhandelloven
    # ``no/lov/2007-06-29-75`` [84, 4] -> [85, 4] (`2018-06-01-23` item 7),
    # skipssikkerhetsloven ``no/lov/2007-02-16-9`` [14, 4] -> [15, 4]
    # (`2008-06-27-72` § 47, off sjøloven), skatteforvaltningsloven
    # ``no/lov/2016-05-27-14`` [142, 7] -> [144, 7] (`2019-03-15-6` item 25,
    # bokstav h og i), and six single REPLACEs. The content-removing column
    # does not move (219 over 81 laws): nothing here repeals.
    # 3,953 -> 4,036 at W-100: the surviving 156 take 83 more writes, all from
    # bindings the section-scoped lane dated; the dated acts' writes on the
    # bases that LEFT are no longer hazard writes at all.
    # 4,036 -> 4,039 at W-101: three known-incomplete bases take ONE write each,
    # every one a structured chapter-heading REPLACE (Lovdata's ``kap…`` token
    # lowering for the first time) that merges its heading over the standing
    # chapter — ``no/lov/2001-05-18-21`` [63, 4] -> [64, 4],
    # ``no/lov/2018-04-20-8`` [16 -> 17], ``no/lov/2023-06-09-30`` [19 -> 20].
    # The content-removing column is flat (238 over 76 laws): nothing repeals.
    "hazard_destructive_writes": 4039,
    # 167 -> 168, and the +1 is NOT a relabel op. ``no/lov/2016-05-27-14`` gains
    # ``no/lovtid/2021-12-22-158:1``, a REPEAL of § 7-6 annet ledd that could not
    # bind before because that law's ledd sequence was one slot out of step; with
    # the relabel landed, the address it names exists and the repeal lands too.
    # The removal is an amendment finally taking effect, not a recovery eating an
    # occupant — § 7-6 itself survives, and the receipt's section-level
    # ``removed_paths`` is the known ``no_receipt_storage_path_resolution``
    # projection. Signed off 2026-08-12.
    #
    # 168 -> 198 (+30) over 65 -> 77 laws at W-66c, and THIS is the number this
    # item exists to be judged on. Every previous landing in this series moved
    # ``hazard_destructive_writes`` while leaving content-removing flat, because
    # a RENUMBER moves content and a substitution replaces it. A punktum REPEAL
    # DELETES a sentence of in-force law, so for the first time the destroying
    # column moves, and it moves inside bases the system already knows are
    # incomplete — precisely the posture that destroyed husbankloven § 13.
    #
    # It is not accepted on trust. All 33 corpus destructions are pinned BY
    # CONTENT (base act, address, the sentence's own text) in
    # ``_W66C_CORPUS_DESTRUCTIONS`` below, and every one was adjudicated against
    # its instrument's own ``article.defaultP`` node before landing: 33 of 33
    # name their section AND their ledd in their own text, so not one landed
    # destruction rests on an inherited address. The corpus-wide content-removing
    # figure moves 207 -> 240 in step (+33), of which 30 fall inside this
    # intersection: 28 on laws already in it, and 2 arriving with
    # ``no/lov/2011-06-24-39``, one of which is its own pre-existing write.
    # ``hazard_bases_removing_content`` 65 -> 77 is the 11 laws whose row goes
    # from 0 removals to some, plus that entrant.
    # 219 -> 238 / 81 -> 76 at W-100, the same movement in the removing column.
    "hazard_content_removing_writes": 238,
    "hazard_bases_removing_content": 76,
}

#: Content hash of the per-law hazard list (base_id -> [destructive, removing]).
#: The counts above can hold while their MEMBERSHIP churns — one law leaving and
#: another entering nets to zero — so the set is pinned too, exactly as W-73's
#: own accounting had to reason about which laws moved rather than how many.
_NO_INCOMPLETE_BASE_HAZARD_LAWS_DIGEST = (
    # W-66: the 161-law MEMBERSHIP is unchanged; 26 laws' per-law counts move, so
    # the digest moves with them. See the two count notes above.
    # W-69a: membership again unchanged; ONE law's count moves
    # (``no/lov/2008-06-27-71`` [79, 2] -> [80, 2]), so the digest moves with it.
    # W-69b: membership unchanged a third time; the SAME law moves again
    # ([80, 2] -> [86, 2]) as its six sentence-depth substitution addresses land.
    # W-69c: the first MEMBERSHIP change since W-66 — ``no/lov/2009-06-19-44``
    # enters at [7, 0], nothing leaves, no other law's row moves.
    # W-70b: membership unchanged; the SAME law's row moves again, [7, 0] ->
    # [11, 0], as its six relocation legs land and two INSERTs stop recovering
    # onto an occupant. It is the ONLY row that moves.
    # W-66b: membership unchanged again; ONE row moves, ``no/lov/2008-05-15-35``
    # [262, 8] -> [263, 8]. See the count note above for the +3/-2 underneath it.
    # W-66c: the second MEMBERSHIP change since W-66 — two laws ENTER
    # (``no/lov/2010-06-04-21`` [6, 0], ``no/lov/2011-06-24-39`` [12, 2]),
    # nothing leaves, and 24 further rows move by the punktum repeals they take.
    # Both columns move on 24 of the 26; the destroying column moving at all is
    # this landing's headline, and the destructions are pinned by content below.
    # W-76: MEMBERSHIP UNCHANGED (164 laws, same set, nothing enters or leaves —
    # the two set differences are empty). THREE rows move, and only in the
    # destructive column: ``no/lov/2005-06-17-90`` [49, 0] -> [52, 0],
    # ``no/lov/2007-12-21-119`` [49, 4] -> [50, 4], ``no/lov/2005-05-20-28``
    # [130, 3] -> [131, 3]. Every removing column is byte-identical, which is the
    # column that matters: an item-depth relabel MOVES content, it does not
    # delete it. See the ``hazard_destructive_writes`` note above for the leg-by-
    # leg decomposition of the +5.
    # W-77: MEMBERSHIP UNCHANGED again (164 laws, same set). TWO rows move, and
    # only in the destructive column: ``no/lov/2005-06-17-67`` [314, 12] ->
    # [316, 12] and ``no/lov/2008-05-15-35`` [266, 10] -> [269, 10]. Every
    # removing column is byte-identical. The five writes are not this
    # production's — they are downstream REPLACEs that stopped refusing once the
    # item they address existed; see the count note above.
    # W-78: MEMBERSHIP UNCHANGED (164 laws, same set). ONE row moves, and only in
    # the destructive column: ``no/lov/2008-05-15-35`` [269, 10] -> [254, 10] —
    # the first SHRINKAGE in this series, and the credit belongs to withdrawing
    # 23 REPLACEs that were writing an amendment's own announcement sentence into
    # in-force law. See the count note above.
    # W-79: MEMBERSHIP UNCHANGED (164 laws, same set, both set differences
    # empty). EIGHT rows move, all downward and all in the destructive column;
    # every removing column is byte-identical. The eight are named one by one in
    # the count note above — the general closure of the wrong-text class, so the
    # shrinkage is spread over eight laws rather than concentrated on one.
    # W-82: MEMBERSHIP UNCHANGED (164 laws, same set, both set differences
    # empty). ONE row moves, and only in the destructive column:
    # ``no/lov/2008-05-15-35`` [249, 10] -> [252, 10]. Every removing column is
    # byte-identical, corpus-wide and on this row: the three writes are REPLACEs
    # of a first punktum whose sibling sentence SURVIVES beside the new one. This
    # is the only law in the corpus whose replayed tree moves at all under W-82 —
    # the other 32 recovered ops are inert at ``as_of`` (contingent skips, base
    # acts with no original-act source, or a target that refuses typed at replay).
    # See the count note above.
    # W-84: MEMBERSHIP UNCHANGED (164 laws, same set, both set differences
    # empty). ONE row moves, and only in the destructive column:
    # ``no/lov/2002-06-21-45`` [66, 2] -> [69, 2]. It is the only law in the
    # corpus whose replayed tree moves under W-84 in this direction — klimaloven
    # moves too, but by LOSING a write, which no row here records. See the count
    # note above for the +4/-1 underneath the +3.
    # W-86: MEMBERSHIP UNCHANGED (164 laws, same set, both set differences
    # empty). ONE row moves, downward and only in the destructive column:
    # ``no/lov/2005-06-10-51`` [46, 5] -> [45, 5] — W-85's withdrawal of the
    # re-sanctioned defective act's duplicate write, reaching this baseline on
    # the first regeneration after it (see the count note above). The capture
    # drift itself (forskrift +51, current -5) moves no row at all.
    # W-98: ONE law ENTERS (``no/lov/2004-03-26-17``, [4, 0]) and 31 laws' per-law
    # counts move (the nine productions landing on known-incomplete bases; see
    # the destructive-writes note above), so the digest moves with them.
    # W-99: MEMBERSHIP UNCHANGED (165 laws, same set, both set differences
    # empty). NINE rows move, all upward and only in the destructive column —
    # the period-less citation and address-after-citation leads binding to the
    # act they name, each a REPLACE/INSERT the source commands by name (see the
    # count note above); every removing column is byte-identical.
    # W-100: MEMBERSHIP moves (165 -> 156, twelve leave, two enter) and rows
    # move on the bases the section-scoped lane dated; see the count notes.
    # W-101: MEMBERSHIP UNCHANGED (156 laws, same set). THREE rows move, each
    # +1 in the destructive column only (the chapter-heading REPLACEs named in
    # the count note above); every removing column is byte-identical.
    "8ad2557c6523a12bdf467295962f731d71796395f33304cfe78f843057f27d72"
)

_REGENERATE = (
    "Regenerate with `uv run python "
    "scripts/inventory_no_occupied_destination_sweep.py --update-baseline`, then "
    "adjudicate every NEW firing W-54 style (source text, occupant provenance, does "
    "the removal destroy in-force law) before touching the verdict table. A "
    "`removal_wrong` verdict is a STOP, never a new expected row."
)


def _load_sweep_module():
    """Import ``scripts/inventory_no_occupied_destination_sweep.py`` by path.

    Same idiom as ``tests/test_module_role_consistency.py`` uses for its own
    scanner: the generator is a script rather than a package module, and the test
    binds THAT code so the digests it recomputes cannot drift from the ones the
    baseline was written with.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lawvm_inventory_no_occupied_destination_sweep", _SWEEP_SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def _no_occupied_destination_sweep():
    sweep = _load_sweep_module()
    path = _REPO_ROOT / sweep.BASELINE_PATH
    assert path.exists(), f"Missing occupied-destination sweep baseline at {path}. {_REGENERATE}"
    import json as _json

    return sweep, _json.loads(path.read_text(encoding="utf-8"))


def test_no_occupied_destination_sweep_baseline_is_not_stale(
    _no_occupied_destination_sweep,
) -> None:
    """W-72: the committed corpus sweep still describes THIS corpus and THIS code.

    The staleness receipt, checked before anything is read out of the baseline.
    Two digests, recomputed live:

    * CORPUS — every artifact in all four Norway planes as
      ``(logical_id, sha256(payload))``. Logical rather than a hash of the
      ``.farchive`` file, so a VACUUM or a recompression cannot raise a false
      alarm; false alarms are the one failure mode that would defeat this pin,
      because they teach people to regenerate without reading the diff.
    * CODE — the sha256 of every source file in the static import closure of
      ``lawvm.norway.replay`` / ``.index`` / ``.inventory``, derived by AST walk
      rather than hand-listed. A new dependency can only enter that closure via
      an edit to a module already inside it, so the digest moves on its own.

    Those two plus the pinned ``as_of`` and the determinism firewall
    (``notes/DETERMINISM_FIREWALL.md``) fix the sweep's answer. The residual is
    the third-party runtime, recorded in the baseline for triage and deliberately
    not asserted here — see the generator's ``runtime_identity`` docstring.
    """
    sweep, baseline = _no_occupied_destination_sweep
    if not _REAL_ARCHIVE.exists():
        pytest.skip("requires the local Lovdata archive (data/norway.farchive)")

    assert baseline["as_of"] == sweep.AS_OF == "2026-07-10", (
        "The sweep replays to a different point in time than the live pins above; "
        "the two measure different corpora. " + _REGENERATE
    )
    assert baseline["rule_id"] == sweep.RULE_ID == _OCCUPIED_DESTINATION_ADJUDICATION_KIND

    reasons = sweep.staleness_reasons(
        baseline, sweep.corpus_identity(_REAL_ARCHIVE), sweep.code_identity(_REPO_ROOT)
    )
    if reasons:
        pytest.fail(
            "; ".join(reasons)
            + ". The corpus-wide claim below is UNPROVEN until the sweep is retaken. "
            + _REGENERATE
        )

    # The receipt covers the WHOLE corpus, and the plane list is pinned HERE
    # rather than only in the generator. Dropping a plane from ``CORPUS_PLANES``
    # does fail the digest comparison above — but the obvious next move is to
    # regenerate, and that would quietly install a weaker receipt. ``forskrift``
    # is the one that matters most: a commencement date moving there changes
    # which amendments apply, and therefore which renumbers land.
    assert sweep.CORPUS_PLANES == ("original_lti", "amendment", "forskrift", "current")
    # forskrift 35,955 -> 36,006 and current 763 -> 758 at W-86, the
    # 2026-08-14 capture re-pin; the two LOV lanes are digest-identical across
    # the re-capture, which is the receipt that no act entered or left the
    # replay's own source plane. The +51 are new Lovtidend forskrift
    # announcements (every one parsing benign, so no commencement date and
    # therefore no landed op moves at ``as_of``); the -5 are the five
    # fully-incorporated endringslover Lovdata dropped from ``gjeldende-lover``
    # — oracle-side artifacts this sweep never replays. Adjudicated
    # document-by-document in the ledger's item 92 and ``.tmp/w86/``.
    assert [(p["plane"], p["artifacts"]) for p in baseline["corpus"]["planes"]] == [
        ("original_lti", 3089),
        ("amendment", 3089),
        ("forskrift", 36006),
        ("current", 758),
    ]

    # The sweep is only a corpus-wide answer where it actually SAW the law, so
    # the exceptions are named here rather than rounded off.
    assert baseline["swept"]["fatals"] == [], baseline["swept"]["fatals"]
    swept = baseline["swept"]["base_law_ids"]
    # 783 -> 784 at W-66: ``no/lov/2017-06-16-53`` enters the amended-law
    # population, its first lowered op being a sibling-set ledd relabel
    # ("Någjeldende annet ledd blir tredje ledd." in ``no/lovtid/2018-06-15-38``,
    # § 30 inherited from the preceding lead). It is not a scan candidate, so the
    # scoreboard does not see it; this census does.
    #
    # 784 -> 785 at W-66b, and by exactly the same mechanism one depth word down:
    # ``no/lov/2004-12-10-77`` enters on its first lowered op, a sibling-set
    # PUNKTUM relabel whose section AND ledd both come from the DOM-local
    # antecedent. It is likewise not a scan candidate.
    #
    # 785 -> 788 at W-66c, three at once and the same mechanism a third time:
    # ``no/lov/1991-11-29-78``, ``no/lov/1998-07-17-54`` and
    # ``no/lov/2009-05-15-28`` enter on their first lowered op ever, each a
    # punktum-depth REPEAL. Two of the three have no original-act source
    # (``errored_before_any_op`` moves 440 -> 442 with them); the third,
    # ``no/lov/2009-05-15-28``, replays and ENTERS the scan candidate set, which
    # is the first time an entrant to this census has also been an entrant there.
    # 788 -> 789 at W-99: ``no/lov/2000-12-21-118`` (havbeiteloven) enters on its
    # first lowered op ever — `no/lovtid/2003-12-19-124` item 6, "Lov 21. desember
    # 2000 nr. 118 om havbeite § 3 andre ledd skal lyde:", an address-after-citation
    # lead that used to bind to the 1933 act before it. No original-act source, so
    # it joins the errored class on arrival (442 -> 443 below).
    # 789 -> 790 at W-101: folkehøgskoleloven ``no/lov/2025-06-20-99`` enters
    # on its first lowered op ever — ``no/lovtid/2026-06-19-59``'s ``kap4``
    # chapter-heading block, Lovdata's structured chapter token lowering for
    # the first time. It has an original-act source and replays (the errored
    # class stays at 443), and it enters the verify scan candidate set too.
    assert len(swept) == baseline["swept"]["base_laws"] == 790
    assert sorted(set(swept)) == swept
    assert set(_NO_OCCUPIED_DESTINATION_LAWS) <= set(swept)
    # 440 laws error before a single op is applied — F-09's sparse-source class,
    # no original-act bytes at all — so "no firing here" is a complete answer for
    # them, not an unobserved one.
    # 440 -> 442 at W-66c: two of the three entrants above have no original-act
    # bytes either, so they join this class on arrival.
    # 442 -> 443 at W-99: the havbeiteloven entrant above.
    assert baseline["swept"]["errored_before_any_op"] == 443
    # THE SWEEP'S BLIND SPOT, and W-69c has taken it from four laws to THREE.
    # These abort mid-apply on a replay invariant violation, which discards the
    # apply plane's receipts and adjudications along with the statute, so whether
    # they fire is genuinely not observable. Two of the three do receive RENUMBER
    # ops (``no/lov/2003-07-04-74`` receives none and so cannot fire at all),
    # which means the corpus-wide claim above is exact over 781 laws and silent
    # about two.
    #
    # Why that is tolerable, and why it still has to be pinned: a firing can only
    # destroy IN-FORCE law inside a replayed statute, and these three produce no
    # statute — they are not scan candidates and contribute no divergence row, so
    # there is nothing for a hidden firing to be wrong about today. The moment one
    # is repaired it leaves this set, this equality fails, and its firings get
    # adjudicated before anything else can go green on them.
    #
    # THAT IS EXACTLY WHAT HAPPENED TO ``no/lov/2009-06-19-44`` (W-69c). It
    # aborted with ``duplicate subsection:4`` because two relocation legs of
    # ``no/lovtid/2025-06-20-42`` — a cross-container in-migration
    # ``§3/ledd/3 → §2/ledd/4`` and the destination parent's own vacate shift
    # ``§2/ledd/3 → §2/ledd/4`` — claim ONE destination, which no ordering can
    # satisfy. W-69c made it replay by refusing the whole component typed
    # (``no_replay_relocation_order_unprovable_refused``, 6 legs), which made its
    # ``(RENUMBER, dest_occupied)`` behaviour observable for the first time.
    #
    # W-70b then removed the CAUSE: the §3 attribute named the wrong destination
    # section, its own announcement proves the shift is intra-§3, and the repaired
    # legs contest nothing. So the refusals are 6 → 0, the relocation LANDS, and
    # the occupied-destination answer is unchanged and still ZERO — the shift
    # vacates before it occupies, the firing census above stays 10, and the
    # verdict table gains no row. The witness, which now pins the recovery of the
    # two provisions W-69c had to record as overwritten, is
    # ``test_no_w69c_witness_2009_06_19_44_replays_to_completion`` below.
    assert baseline["swept"]["errored_with_ops_applied"] == [
        "no/lov/2003-07-04-74",
        "no/lov/2005-06-17-62",
        "no/lov/2015-04-10-17",
    ], baseline["swept"]["errored_with_ops_applied"]


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_w69c_witness_2009_06_19_44_replays_to_completion() -> None:
    """W-69c's corpus witness, now pinning W-70b's RECOVERY of two provisions.

    THE HISTORY, in three states, because this one law is where three items meet.
    Before W-69c the replay returned no statute at all — ``Norway replay
    invariant violation after renumber (('section','2'),('subsection','3')) from
    no/lovtid/2025-06-20-42: body/section:2: duplicate subsection:4`` — and an
    aborted apply discards the law's ENTIRE receipt and adjudication plane, which
    is why the law sat in W-72's blind spot. W-69c made it replay by refusing the
    unsatisfiable relocation component typed, at the cost of two in-force
    provisions the un-vacated INSERTs then overwrote. W-70b removes the cause.

    WHY IT COULD NOT BE ORDERED. ``no/lovtid/2025-06-20-42`` carries two
    ``data-move-part`` attributes. The §2 one is a clean +1 shift
    (``3→4, 4→5, 5→6, 6→7``). The §3 one read ``§3/ledd/2 ;; §2/ledd/3`` and
    ``§3/ledd/3 ;; §2/ledd/4`` — it sent §3's ledd into §2 — while the prose it
    annotates says "Noverande § 3 andre og tredje ledd blir tredje og nytt fjerde
    ledd", an intra-§3 shift. **The Lovdata attribute named the wrong section.**
    So ``§2/ledd/3 → §2/ledd/4`` and ``§3/ledd/3 → §2/ledd/4`` both claimed
    ``§2/ledd/4``, no permutation satisfied both, and W-69c's provability guard
    refused all six legs of the connected component.

    W-70b repairs the ATTRIBUTE at the lowering, on the block's own announcement
    (``no_parse_structured_move_attr_destination_section_normalized``). The two
    legs become ``§3/ledd/2 → §3/ledd/3`` and ``§3/ledd/3 → §3/ledd/4``, nothing
    contests §2 any more, the component is provable, and the whole shift LANDS.
    W-69c's guard is untouched — it simply has nothing to refuse here now, which
    is why the refusal list below is asserted EMPTY rather than deleted.

    The occupied-destination answer W-72 pinned this law for is unchanged and
    still ZERO: the relocation vacates before it occupies, so the corpus firing
    census stays at 10 and the verdict table gains no row. What changes is WHY —
    at W-69c nothing fired because nothing ran; now nothing fires because the
    ordering is proven safe.
    """
    from lawvm.norway.index import build_no_amendment_index

    index = build_no_amendment_index(_REAL_ARCHIVE)
    result = replay_no_to_pit(
        "no/lov/2009-06-19-44", as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index
    )
    assert result.error is None, result.error
    replayed = result.replayed
    assert replayed is not None

    refusals = sorted(
        (
            str((a.detail or {}).get("source_path")),
            str((a.detail or {}).get("destination_path")),
        )
        for a in result.adjudications
        if a.kind == "no_replay_relocation_order_unprovable_refused"
    )
    # 6 -> 0 at W-70b. All six were ONE connected component — §2's four-leg shift
    # chain plus §3's two in-migrations, joined at the contested ``§2/ledd/4`` —
    # so repairing the two mis-addressed legs releases the other four with them.
    assert refusals == []
    # W-70b is a LOWERING repair and must stay one: it may not reach the apply
    # plane's recoveries. The relocation still never writes onto a live sibling.
    assert not [
        a
        for a in result.adjudications
        if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]
    repairs = [
        a
        for a in result.adjudications
        if a.kind == "no_parse_structured_move_attr_destination_section_normalized"
    ]
    assert len(repairs) == 1, [a.kind for a in result.adjudications]
    assert repairs[0].detail["normalized_legs"] == (
        "lov/2009-06-19-44/§3/ledd/2;;lov/2009-06-19-44/§3/ledd/3",
        "lov/2009-06-19-44/§3/ledd/3;;lov/2009-06-19-44/§3/ledd/4",
    )

    def _section(section_label: str):
        return next(
            child
            for child in replayed.body.children
            if (child.kind.value if hasattr(child.kind, "value") else str(child.kind)) == "section"
            and child.label == section_label
        )

    def _ledd(section_label: str) -> list[tuple[str, str]]:
        return [
            (child.label or "", (child.text or "").strip())
            for child in _section(section_label).children
            if (child.kind.value if hasattr(child.kind, "value") else str(child.kind))
            == "subsection"
        ]

    # THE PAYOFF, adjudicated ledd by ledd against the instrument's own four
    # change blocks rather than by count. §2 gains its seventh ledd and §3 its
    # fourth, and the two provisions W-69c had to record as overwritten are back
    # at the addresses the shift sends them to.
    #
    #   block 1  "§ 2 andre og tredje ledd skal lyde:"  -> REPLACE §2/2, INSERT §2/3
    #   block 2  "Noverande § 2 tredje til sjette ledd blir fjerde til nytt
    #             sjuande ledd."                        -> §2 3→4, 4→5, 5→6, 6→7
    #   block 3  "§ 3 første og andre ledd skal lyde:"  -> REPLACE §3/1, INSERT §3/2
    #   block 4  "Noverande § 3 andre og tredje ledd blir tredje og nytt fjerde
    #             ledd."                                -> §3 2→3, 3→4  (W-70b)
    section_2 = _ledd("2")
    assert [label for label, _text in section_2] == ["1", "2", "3", "4", "5", "6", "7"]
    # ledd 3 is block 1's INSERT; ledd 4 is base § 2 tredje ledd, RECOVERED — it
    # was the provision the un-vacated INSERT used to replace.
    assert section_2[2][1].startswith("Tilbodet skal gi brukarane støtte")
    assert section_2[3][1].startswith("Enkeltpersonar kan vende seg direkte")
    assert section_2[4][1].startswith("Kommunen skal sørgje for god kvalitet")
    assert section_2[5][1].startswith("Butilbodet til kvinner")
    assert section_2[6][1].startswith("Departementet kan gi forskrift")

    section_3 = _ledd("3")
    assert [label for label, _text in section_3] == ["1", "2", "3", "4"]
    # ledd 2 is block 3's INSERT; ledd 3 is base § 3 andre ledd, RECOVERED.
    assert section_3[1][1].startswith("Dei særskilde rettane til samiske brukarar")
    assert section_3[2][1].startswith("Kommunen skal sørgje for å ta vare på barn")
    assert section_3[3][1].startswith("Kommunen skal sørgje for at brukarar av bu- og dagtilbodet")

    replaced = sorted(
        str((a.detail or {}).get("resolved_path"))
        for a in result.adjudications
        if a.kind == "no_replay_insert_occupied_target_replaced"
    )
    # 3 -> 1, corpus-wide 139 -> 137. ``section:4`` is neither W-69c's nor
    # W-70b's: it comes from ``no/lovtid/2021-06-11-78``, an earlier affecting-act
    # group that ran to completion even before W-69c, and it is deliberately left
    # standing — this item repairs one mis-addressed attribute, not every
    # occupied INSERT on the law.
    assert replaced == ["section:4"], replaced


def test_no_corpus_wide_occupied_destination_firings_are_all_adjudicated(
    _no_occupied_destination_sweep,
) -> None:
    """W-72, THE point of the item: every ``(RENUMBER, dest_occupied)`` firing
    ANYWHERE in the corpus is in the pinned verdict table — including on laws
    nobody listed.

    This is the assertion
    ``test_no_corpus_occupied_renumber_destination_verdicts_are_pinned`` has
    always claimed and, before W-72, never made: it replays the nine laws it was
    handed, so a firing on a tenth law was invisible to it. Here the population
    comes from a sweep of all 783, and the comparison is equality, so an
    unadjudicated firing on ANY law fails. Exact over 779 of the 783; the other
    four abort mid-apply and are named in
    ``test_no_occupied_destination_sweep_baseline_is_not_stale``.

    The two tests are complements and neither is redundant. This one owns
    POPULATION (which firings exist, corpus-wide, from cached evidence whose
    staleness is receipted). That one owns EFFECT (what each firing did to the
    occupant's text, from a live replay). Together they are the corpus-wide
    claim; apart, each is a half of it.
    """
    _sweep, baseline = _no_occupied_destination_sweep

    swept_firings = {
        f["op_id"]: (f["base_id"], f["source_path"], f["destination_path"])
        for f in baseline["firings"]
    }
    adjudicated = {
        op_id: (base_id, source, destination)
        for op_id, (base_id, source, destination, _v, _p, _s)
        in _NO_OCCUPIED_DESTINATION_VERDICTS.items()
    }
    assert swept_firings == adjudicated, (
        "Corpus-wide occupied-destination firings disagree with the adjudicated verdict "
        "table. Firings the sweep found and the table lacks are UNADJUDICATED removals — "
        "each one may be destroying in-force law, which is what happened to husbankloven "
        "§ 13 under W-67. " + _REGENERATE
    )
    # Per-law, so the sweep and the hand-written law list cannot drift apart
    # either. Laws pinned at ``(0, 0)`` — repaired at the lowering by W-56 and
    # W-61 — must stay absent from the sweep's firing map.
    swept_laws = {law: tuple(counts) for law, counts in baseline["firing_laws"].items()}
    expected_laws = {
        law: counts for law, counts in _NO_OCCUPIED_DESTINATION_LAWS.items() if counts != (0, 0)
    }
    assert swept_laws == expected_laws, swept_laws
    # And the flipped tripwire holds over the corpus rather than over nine laws:
    # no adjudicated occupied-destination removal anywhere destroys in-force law.
    assert [
        op_id
        for op_id, (_b, _s, _d, verdict, _p, _sv) in _NO_OCCUPIED_DESTINATION_VERDICTS.items()
        if verdict == "removal_wrong"
    ] == []


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_occupied_destination_sweep_agrees_with_the_live_replay(
    _no_occupied_destination_sweep, _no_occupied_destination_replays
) -> None:
    """W-72: the cached sweep is checked against a LIVE replay where one is
    already being done.

    The staleness receipt argues that identical corpus plus identical code gives
    identical firings. This test stops that from being an argument. The nine laws
    the pins above replay for real are re-derived here and compared to what the
    baseline says about those same nine — so a baseline written from a different
    code state, or a nondeterminism in the replay, fails HERE rather than being
    taken on the receipt's word.

    It cannot see the other 774 laws. That is the honest limit of the cache, and
    the reason the receipt has to be tight rather than merely present.
    """
    _sweep, baseline = _no_occupied_destination_sweep
    cached = {
        law: sorted(f["op_id"] for f in baseline["firings"] if f["base_id"] == law)
        for law in _NO_OCCUPIED_DESTINATION_LAWS
    }
    live = {
        law: sorted(
            a.op_id
            for a in replay.adjudications
            if a.kind == _OCCUPIED_DESTINATION_ADJUDICATION_KIND
        )
        for law, replay in _no_occupied_destination_replays.items()
    }
    assert live == cached, (
        "The live replay and the cached sweep disagree on which firings these laws "
        "carry, while the staleness receipt says the corpus and the code are unchanged. "
        "Either the baseline was written from a different tree, or the replay is not "
        "deterministic. " + _REGENERATE
    )


def test_no_incomplete_base_destructive_write_census_is_pinned(
    _no_occupied_destination_sweep,
) -> None:
    """W-73's rider (d), made ladder-visible (W-72(b)): how many laws take
    DESTRUCTIVE writes into a base the system already knows is incomplete.

    This is the posture that destroyed husbankloven § 13 — a correctly lowered op
    applied to a base missing an amendment the replay itself receipted as skipped.
    W-73 measured it and left the number in an artifact under ``.tmp``, where it
    could drift with every archive refresh and every widening without anyone
    noticing.

    The pin is EQUALITY and it is a census, not an expected-behaviour freeze: 161
    laws in this posture is a finding held open, and W-72 explicitly does not fix
    it (refusing those writes is a product-behaviour change with its own blast
    radius). Movement in either direction wants a sentence in the ledger — growth
    because the hazard surface grew, shrinkage because some item repaired a base
    and should get the credit.

    It rides in the occupied-destination sweep because it is the same replay pass
    over the same 783 laws, so it costs nothing extra and inherits the same
    staleness receipt.
    """
    _sweep, baseline = _no_occupied_destination_sweep
    hazard = baseline["incomplete_base_hazard"]
    observed = {key: hazard[key] for key in _NO_INCOMPLETE_BASE_HAZARD}
    assert observed == _NO_INCOMPLETE_BASE_HAZARD, observed
    assert hazard["laws_digest"] == _NO_INCOMPLETE_BASE_HAZARD_LAWS_DIGEST, (
        "The hazard census COUNTS held but its MEMBERSHIP changed — some law left the "
        "set and another entered. Name both in the ledger. " + _REGENERATE
    )
    assert len(hazard["laws"]) == _NO_INCOMPLETE_BASE_HAZARD["hazard_bases"]
    # Every hazard law is incomplete for a reason the replay receipted, and
    # ``contingent`` still dominates — the class husbankloven was in.
    # 162 -> 164 at W-66c: the two entrants are both contingent-skip laws, which
    # keeps the dominance argument exact rather than merely still true.
    # 164 -> 165 at W-98: the entrant (``no/lov/2004-03-26-17``) is a
    # contingent-skip law, so the dominance argument stays exact.
    # 165 -> 156 at W-100: nine contingent-skip laws leave (their acts are now
    # dated) and the two entrants are contingent-skip laws (per-op), so the
    # dominance argument stays exact.
    assert hazard["hazard_by_skip_kind"]["contingent"] == 156
    assert hazard["hazard_by_skip_kind"]["missing_source"] == 0
    # Husbankloven is the witness this census exists for, and it is STILL IN THE
    # SET — 8 destructive writes, 3 of them content-removing. W-73 repaired the
    # commencement of ONE amendment (``no/lovtid/2012-08-24-64``); a different one
    # (``no/lovtid/2025-04-25-12``) is still contingent, so the base is still
    # known-incomplete and the law still takes destructive writes into it.
    #
    # That is the whole argument for keeping this census. § 13 survives today
    # because W-74 made the one op that vacates it lower — the specific defect was
    # repaired — but the POSTURE that destroyed it is unchanged on this very law.
    # Reading the green ladder as "husbankloven is safe" would repeat W-67's
    # mistake one level up.
    # [8, 3] -> [9, 4] at W-98 (i): ``no/lovtid/2017-06-21-96``'s nynorsk
    # "§ 4 fjerde ledd blir oppheva." lowers to a REPEAL the act commands by
    # name — one more destructive write, and it removes content.
    assert hazard["laws"][_HUSBANKLOVEN] == [9, 4]


# ---- W-72 guard liveness: prove the staleness check can actually FAIL --------
#
# §2.9's worst class is a guard that exists and cannot fire. Everything above
# rests on the claim that a moved corpus or a moved module makes the sweep
# baseline fail loudly, and until something is seen to fail, that claim is a
# comment. These three run corpus-free.


def test_no_sweep_staleness_fires_on_a_moved_corpus_and_a_moved_module() -> None:
    """The staleness check reports a moved corpus and a moved module, separately.

    Doctored inputs rather than a doctored archive: the point under test is the
    comparison, and it should say WHICH half moved, because "the digest differs"
    sends a reader to the wrong place half the time.
    """
    sweep = _load_sweep_module()
    corpus = {
        "planes": [{"plane": "amendment", "artifacts": 3089, "digest": "aaa"}],
        "digest": "corpus-was",
    }
    code = {
        "modules": 2,
        "files": [
            {"module": "lawvm.norway.grafter", "digest": "g1"},
            {"module": "lawvm.norway.replay", "digest": "r1"},
        ],
        "digest": "code-was",
    }
    baseline = {"corpus": corpus, "code": code}

    assert sweep.staleness_reasons(baseline, corpus, code) == []

    grown = {
        "planes": [{"plane": "amendment", "artifacts": 3125, "digest": "bbb"}],
        "digest": "corpus-now",
    }
    (reason,) = sweep.staleness_reasons(baseline, grown, code)
    assert "THE CORPUS MOVED" in reason
    assert "3089 -> 3125 artifacts" in reason

    edited = {
        "modules": 2,
        "files": [
            {"module": "lawvm.norway.grafter", "digest": "g2"},
            {"module": "lawvm.norway.replay", "digest": "r1"},
        ],
        "digest": "code-now",
    }
    (reason,) = sweep.staleness_reasons(baseline, corpus, edited)
    assert "THE REPLAY PATH MOVED" in reason
    # Named, not counted: the reader has to be able to go and look at it.
    assert "lawvm.norway.grafter" in reason
    assert "lawvm.norway.replay" not in reason

    assert len(sweep.staleness_reasons(baseline, grown, edited)) == 2


def test_no_sweep_code_closure_reaches_the_code_that_decides_a_firing() -> None:
    """The import closure contains the modules a firing actually depends on.

    A closure walker that quietly resolved almost nothing would produce a stable
    digest and a tripwire that never fires — passing for the worst possible
    reason. So this asserts membership for the specific modules that decide
    whether the recovery runs: the grafter that applies the RENUMBER and detects
    the occupied destination, the totalization table that maps
    ``(RENUMBER, dest_occupied)`` to a recovery at all, the apply seam that emits
    the receipt, and the replay/index/commencement path that decides which ops
    reach the law in the first place.
    """
    sweep = _load_sweep_module()
    closure = sweep.code_closure(_REPO_ROOT)
    for module in (
        "lawvm.norway.grafter",
        "lawvm.norway.replay",
        "lawvm.norway.index",
        "lawvm.norway.inventory",
        "lawvm.norway.commencement",
        "lawvm.norway.totalization_table",
        "lawvm.core.totalization",
        "lawvm.core.apply_seam",
    ):
        assert module in closure, sorted(closure)
    # Function-local imports are the codebase's normal idiom, so a module-level
    # only walk would miss most of the graph. Sixty-plus modules is the shape of
    # a real closure; a dozen would mean the walk collapsed.
    assert len(closure) > 60
    # And it stays inside the lane: a Finland or Sweden edit must not invalidate
    # a Norway sweep, or people learn to regenerate without reading.
    other_frontends = {
        "estonia",
        "eu",
        "finland",
        "new_zealand",
        "sweden",
        "uk_legislation",
        "us_federal",
    }
    assert not [m for m in closure if set(m.split(".")[1:2]) & other_frontends]


def test_no_sweep_baseline_regenerate_instruction_names_a_real_script() -> None:
    """The failure messages tell you what to run, and that thing exists.

    Every assertion in this block hands the reader ``_REGENERATE``. A regenerate
    instruction pointing at a moved or renamed script turns a loud failure into a
    dead end, which is how a tripwire gets disabled without anyone deciding to.
    """
    sweep = _load_sweep_module()
    assert _SWEEP_SCRIPT_PATH.is_file()
    assert _SWEEP_SCRIPT_PATH.name in _REGENERATE
    assert (_REPO_ROOT / sweep.BASELINE_PATH).is_file()
    assert "--update-baseline" in _REGENERATE


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_w66_relabel_refusal_keeps_two_live_provisions_standing() -> None:
    """W-66's payoff, pinned at the corpus: the two provisions the recovery ate.

    Both probes must hit at their consolidation addresses AND no
    occupied-destination recovery may fire on either law, so a regression in
    either direction — the provision vanishing, or the θ recovery waking up on
    these ops — fails loudly rather than passing a shorter table.

    The refusal is also asserted POSITIVELY: the typed receipt must be there. A
    silently-dropped op and a refused one look the same in the tree, and only one
    of them is honest.
    """
    from lawvm.norway.index import build_no_amendment_index

    index = build_no_amendment_index(_REAL_ARCHIVE)
    for base_id, probe, address, expected_firings in (
        (
            _STRAFFELOVEN_2005,
            _STRAFFELOVEN_3_GJENAAPNING_PROBE,
            _STRAFFELOVEN_3_GJENAAPNING_ADDRESS,
            [],
        ),
        (
            _VERDIPAPIRHANDELLOVEN,
            _VERDIPAPIRHANDELLOVEN_9_21_PROBE,
            _VERDIPAPIRHANDELLOVEN_9_21_ADDRESS,
            # W-67's own row, unmoved. Verdipapirhandelloven carries a SECTION
            # renumber (§ 4-3 -> § 4-2) whose firing is adjudicated
            # ``removal_correct`` in the verdict table above; W-66 must neither
            # remove it nor add to it.
            ["no/lovtid/2019-06-21-41:2"],
        ),
    ):
        replay = replay_no_to_pit(base_id, as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index)
        assert replay.error is None, base_id
        assert replay.replayed is not None
        assert _no_probe_hits(replay.replayed, probe) == (address,), base_id
        refusals = [
            a
            for a in replay.adjudications
            if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
        ]
        assert refusals, f"{base_id}: the relabel refusal receipt is missing"
        assert all(a.blocking for a in refusals), base_id
        assert [
            a.op_id
            for a in replay.adjudications
            if a.kind == _OCCUPIED_DESTINATION_ADJUDICATION_KIND
        ] == expected_firings, base_id


# ---- W-70: the malformed ``data-move-part`` population, and its tripwire -----
#
# WHY A PIN AND NOT A COUNT. Lovtidend's ``data-move-part`` is authoritative
# markup, and six corpus blocks carry a value the token grammar refuses. That
# population GROWS with archive refreshes — three of the six arrived in the one
# refresh between W-56 and W-62, and until W-70 nothing said so: the refusals
# simply accumulated, each one a shift that silently did not happen. The census
# below is re-derived from a live parse of every amendment artifact (~13s), so a
# refresh that introduces a NEW malformed block, or changes what an existing one
# lowers, fails HERE and forces an adjudication instead of a quiet receipt.
#
# READ THE POLARITY, same as the hazard census above. The refused half is a
# finding held open, not blessed behaviour; the normalized half is a write that
# HAPPENS, and its legs are pinned by content because those legs move live law.
_MALFORMED_MOVE_ATTR_KIND = "no_parse_malformed_structured_renumber_attr_skipped"
_NORMALIZED_MOVE_ATTR_KIND = "no_parse_structured_move_attr_normalized"

_MOVE_ATTR_POPULATION_INSTRUCTION = (
    "The malformed `data-move-part` population moved. Do NOT relax this pin. "
    "For each block that ENTERED: read the attribute off the `article.change` node "
    "the parser reads (never a text-plane grep), decide whether its defect class has "
    "a normalizer rule in `grafter._NO_MOVE_ATTR_NORMALIZATION_RULES`, and if it does "
    "NOT, leave it refused and add it to `_NO_MALFORMED_MOVE_ATTR_REFUSED` with its "
    "decline reason. A block whose tokens name a base act other than the block's own "
    "must STAY refused — repairing it would relabel a law the instrument does not "
    "address there. For each block that LEFT: say in the ledger which item repaired "
    "the archive or the parse. If a block moved from refused to normalized, its new "
    "legs are new RENUMBERs against live law: re-run "
    "`scripts/inventory_no_occupied_destination_sweep.py --update-baseline` and "
    "adjudicate every new firing W-54 style before pinning anything. A "
    "`removal_wrong` verdict is a STOP."
)

#: Blocks whose malformed attribute is DELIBERATELY left refused, keyed
#: ``(instrument, base_id)``. Both members are cross-base: the archive filed the
#: endringsdel under the preceding base act, so every address in the attribute
#: names a law the block is not amending here.
#:
#: * ``no/lovtid/2024-06-21-46`` — value ``…lov/2010-03-26-9/§65/ledd/2
#:   lov/2010-03-26-9/§65/ledd/3`` under base ``no/lov/2022-05-12-28``
#:   (vergemålsloven addresses inside a barnevernsloven part). It is refused
#:   TWICE over: no separator appears anywhere in the value, so which address is
#:   the source is not stated by the markup either.
#: * ``no/lovtid/2026-02-06-2`` — two well-formed pairs fused at a missing space,
#:   naming ``lov/2024-06-21-41`` under base ``no/lov/2022-12-16-91``. The fusion
#:   is repairable in principle and deliberately has no rule: the only corpus
#:   instance is cross-base, so a rule for it would be written against evidence
#:   that could never be allowed to land.
_NO_MALFORMED_MOVE_ATTR_REFUSED: dict[tuple[str, str], dict[str, object]] = {
    ("no/lovtid/2024-06-21-46", "no/lov/2022-05-12-28"): {
        "receipts": 2,
        "defect_reasons": ("missing_separator",),
        "decline": "declined:cross_base_tokens",
    },
    ("no/lovtid/2026-02-06-2", "no/lov/2022-12-16-91"): {
        "receipts": 1,
        "defect_reasons": ("multiple_separators",),
        "decline": "declined:cross_base_tokens",
    },
}

#: Blocks W-70's normalizer repairs, with the legs each one lowers. Content, not
#: counts: these six legs are RENUMBERs against live law, and the whole point of
#: the pin is that a refresh cannot change WHICH provision moves WHERE in silence.
_NO_NORMALIZED_MOVE_ATTR: dict[tuple[str, str], dict[str, object]] = {
    ("no/lovtid/2024-06-25-60", "no/lov/2007-06-29-75"): {
        "rule": "separator_spacing",
        "legs": ("lov/2007-06-29-75/§19-1/ledd/5;;lov/2007-06-29-75/§19-1/ledd/3",),
    },
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70"): {
        "rule": "separator_spacing",
        "legs": (
            "lov/2015-06-19-70/§8/ledd/2;;lov/2015-06-19-70/§8/ledd/3",
            "lov/2015-06-19-70/§8/ledd/3;;lov/2015-06-19-70/§8/ledd/4",
        ),
    },
    ("no/lovtid/2025-04-10-11", "no/lov/1998-07-17-56"): {
        "rule": "separator_spacing",
        "legs": (
            "lov/1998-07-17-56/§3-2/ledd/3;;lov/1998-07-17-56/§3-2/ledd/2",
            "lov/1998-07-17-56/§3-2/ledd/4;;lov/1998-07-17-56/§3-2/ledd/3",
        ),
    },
    ("no/lovtid/2025-06-20-74", "no/lov/2017-12-15-107"): {
        "rule": "alternate_separator",
        "legs": ("lov/2017-12-15-107/§4/ledd/4;;lov/2017-12-15-107/§4/ledd/5",),
    },
}


@pytest.fixture(scope="module")
def _no_move_attr_population():
    """Re-derive the whole ``data-move-part`` pathology census from a live parse.

    Every amendment artifact, through the production entry point, collecting the
    two typed receipts. Keyed ``(instrument, base_id)``: no instrument in this
    corpus carries two malformed blocks against one base, and if one ever does
    the merged row still moves the pin rather than hiding behind it.
    """
    if not _REAL_ARCHIVE.exists():
        pytest.skip("requires the local Lovdata archive (data/norway.farchive)")
    from lawvm.norway.grafter import parse_no_amendment_groups
    from lawvm.norway.sources import iter_no_amendment_artifacts

    receipts: dict[tuple[str, str], int] = {}
    declines: dict[tuple[str, str], str] = {}
    reasons: dict[tuple[str, str], set[str]] = {}
    normalized: dict[tuple[str, str], dict[str, object]] = {}
    leg_counts: dict[tuple[str, str], int] = {}
    artifacts = 0
    for artifact in iter_no_amendment_artifacts(_REAL_ARCHIVE):
        artifacts += 1
        adjudications: list = []
        parse_no_amendment_groups(
            artifact.payload, artifact.logical_id, adjudications_out=adjudications
        )
        for item in adjudications:
            detail = item.detail or {}
            key = (artifact.logical_id, str(detail.get("base_id", "")))
            if item.kind == _MALFORMED_MOVE_ATTR_KIND:
                receipts[key] = receipts.get(key, 0) + 1
                declines[key] = str(detail.get("normalization", ""))
                reasons.setdefault(key, set()).add(str(detail.get("reason", "")))
            elif item.kind == _NORMALIZED_MOVE_ATTR_KIND:
                legs = tuple(detail.get("normalized_legs", ()))
                leg_counts[key] = len(legs)
                normalized[key] = {"rule": str(detail.get("reason", "")), "legs": legs}
    refused: dict[tuple[str, str], dict[str, object]] = {
        key: {
            "receipts": count,
            "defect_reasons": tuple(sorted(reasons[key])),
            "decline": declines[key],
        }
        for key, count in receipts.items()
    }
    return {
        "artifacts": artifacts,
        "refused": refused,
        "normalized": normalized,
        "refused_receipts": sum(receipts.values()),
        "normalized_legs": sum(leg_counts.values()),
    }


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_malformed_move_attr_population_is_pinned(_no_move_attr_population) -> None:
    """W-70's standing tripwire: the malformed-attr population, membership-level.

    Six blocks in 3,089 amendment artifacts carry a ``data-move-part`` the token
    grammar refuses. Four are repaired by an explicit separator rule and lower
    six RENUMBER legs; two are refused, both because their addresses name another
    act. Anything else — a seventh block, a defect class with no rule, a block
    that starts lowering different legs — is a finding, and this is where it
    surfaces.
    """
    population = _no_move_attr_population
    assert population["artifacts"] == 3089, (
        f"the amendment plane holds {population['artifacts']} artifacts, not 3,089; "
        "the census below is measured over a different corpus. "
        + _MOVE_ATTR_POPULATION_INSTRUCTION
    )
    assert population["refused"] == _NO_MALFORMED_MOVE_ATTR_REFUSED, (
        "The REFUSED malformed `data-move-part` blocks are not the pinned set. "
        + _MOVE_ATTR_POPULATION_INSTRUCTION
    )
    assert population["normalized"] == _NO_NORMALIZED_MOVE_ATTR, (
        "The NORMALIZED `data-move-part` blocks, or the legs they lower, are not the "
        "pinned set. These legs move live law. "
        + _MOVE_ATTR_POPULATION_INSTRUCTION
    )
    assert population["refused_receipts"] == 3
    assert population["normalized_legs"] == 6


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_cross_base_malformed_move_attrs_are_never_normalized(
    _no_move_attr_population,
) -> None:
    """W-70's named must-not-recover set, asserted on its own.

    Split out from the census above so its failure message cannot be mistaken for
    ordinary population drift. These two blocks name ``lov/2010-03-26-9`` and
    ``lov/2024-06-21-41`` inside parts filed under ``lov/2022-05-12-28`` and
    ``lov/2022-12-16-91``: the base-tracking defect is in the ARCHIVE, and a
    separator repair applied on top of it would relabel provisions of an act the
    block does not amend at that address. Refusing under-applies; recovering
    would write into the wrong law.
    """
    population = _no_move_attr_population
    for key in (
        ("no/lovtid/2024-06-21-46", "no/lov/2022-05-12-28"),
        ("no/lovtid/2026-02-06-2", "no/lov/2022-12-16-91"),
    ):
        assert key not in population["normalized"], (
            f"{key[0]} was NORMALIZED under base {key[1]}. It is cross-base: every "
            "address in its `data-move-part` names another act. This is a STOP, not a "
            "pin to update — the repair would relabel a law the block does not amend. "
            + _MOVE_ATTR_POPULATION_INSTRUCTION
        )
        assert population["refused"].get(key, {}).get("decline") == "declined:cross_base_tokens", (
            f"{key[0]} is no longer refused for being cross-base. "
            + _MOVE_ATTR_POPULATION_INSTRUCTION
        )


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_karanteneloven_ledd_shift_lands_after_move_attr_normalization() -> None:
    """W-70's payoff at the apply plane, and the only base law it reaches.

    ``no/lovtid/2025-02-07-1`` shifts karanteneloven § 8's second and third ledd
    up one and inserts a new second ledd. With the attribute refused, only the
    INSERT lowered — and it landed on the LIVE second ledd, which the
    insert-occupied recovery then replaced: the old andre ledd was overwritten
    and the old tredje ledd never moved. Normalizing the attribute mints the two
    legs, the kernel's structural-vacate stage runs 3->4 before 2->3, and the
    insert arrives at a slot that is genuinely empty.

    Three things are asserted because three different things could regress: the
    ledd population (the shift happened), the withdrawn recovery (it happened for
    the right reason, not by the insert being dropped), and the absence of any
    occupied-destination firing (the shift did not eat a sibling on the way).
    """
    from lawvm.norway.index import build_no_amendment_index

    index = build_no_amendment_index(_REAL_ARCHIVE)
    replay = replay_no_to_pit(
        "no/lov/2015-06-19-70", as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index
    )
    assert replay.error is None
    assert replay.replayed is not None

    sections = [
        node
        for node in _no_walk_nodes(replay.replayed.body)
        if str(getattr(node.kind, "value", node.kind)) == "section" and node.label == "8"
    ]
    assert len(sections) == 1
    labels = [
        child.label
        for child in sections[0].children
        if str(getattr(child.kind, "value", child.kind)) == "subsection"
    ]
    assert labels == ["1", "2", "3", "4"], labels

    kinds = [a.kind for a in replay.adjudications]
    assert _MALFORMED_MOVE_ATTR_KIND not in kinds
    assert kinds.count(_NORMALIZED_MOVE_ATTR_KIND) == 1
    assert "no_replay_insert_occupied_target_replaced" not in kinds
    assert _OCCUPIED_DESTINATION_ADJUDICATION_KIND not in kinds


def _no_walk_nodes(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.children or ())


# ---- W-70b: the WRONG DESTINATION SECTION population, and its tripwire -------
#
# W-70 above repairs a ``data-move-part`` whose SEPARATORS are malformed. This
# one repairs a ``data-move-part`` that is perfectly well-formed and names the
# WRONG SECTION — a defect no token grammar can see, because every token parses.
# ``no/lovtid/2025-06-20-42`` sends krisesenterlova § 3's ledd into § 2 while its
# own announcement says "Noverande § 3 andre og tredje ledd blir tredje og nytt
# fjerde ledd."; see the block comment on
# ``grafter._no_normalize_move_attr_destination_section`` for the full defect and
# the seven-limb proof the repair is gated on.
#
# TWO POPULATIONS, and both are pinned, because the two failure directions are
# opposite. UNDER-application (a defective attribute the prose cannot prove) is
# safe: the legs keep refusing under W-69c's provability guard. OVER-application
# — "repairing" a genuine cross-section move — would relabel provisions the
# instrument deliberately relocated. So the REPAIRED half is pinned by content
# (which provision moves where, plus which prose pattern proved it) and the
# UNTOUCHED half is pinned by content too, so a regression that starts rewriting
# genuine section renumbering fails here rather than in a statute nobody reads.
#
# The census is re-derived from a live parse of every amendment artifact, so a
# corpus refresh that adds a member fails HERE and forces its own prose
# adjudication before any repair can fire on it.
_DESTINATION_SECTION_KIND = "no_parse_structured_move_attr_destination_section_normalized"

_DESTINATION_SECTION_POPULATION_INSTRUCTION = (
    "The `data-move-part` cross-section population moved. Do NOT relax this pin. "
    "For each attribute that ENTERED: read it off the `article.change` node the parser "
    "reads (never a text-plane grep), read the change node's OWN announcement AND its "
    "preceding sibling, and decide whether the prose commands an INTRA-section ledd "
    "shift (then the attribute is defective and the repair may fire) or a genuine "
    "cross-section move (then it must stay untouched). An attribute you cannot prove "
    "either way STAYS UNTOUCHED and goes in `_NO_MOVE_ATTR_CROSS_SECTION_UNTOUCHED`: "
    "leaving it refused under the relocation-provability guard is the correct standing "
    "state, and guessing a destination writes live law to an address no instrument "
    "names. If an attribute moves into `_NO_MOVE_ATTR_DESTINATION_SECTION_REPAIRED` its "
    "new legs are new RENUMBERs against live law: re-run "
    "`scripts/inventory_no_occupied_destination_sweep.py --update-baseline` and "
    "adjudicate every new firing W-54 style. A `removal_wrong` verdict is a STOP."
)

#: The ONE attribute whose destination section the prose proves wrong, with the
#: legs before and after. Content, not counts: these two legs move live law, and
#: the pin exists so a refresh cannot change WHICH provision lands WHERE in
#: silence. Keyed ``(instrument, base_id)`` on W-70's convention.
_NO_MOVE_ATTR_DESTINATION_SECTION_REPAIRED: dict[tuple[str, str], dict[str, object]] = {
    ("no/lovtid/2025-06-20-42", "no/lov/2009-06-19-44"): {
        "prose_pattern": "shipped",
        "declared_destination_section": "2",
        "normalized_destination_section": "3",
        "declared_legs": (
            "lov/2009-06-19-44/§3/ledd/2;;lov/2009-06-19-44/§2/ledd/3",
            "lov/2009-06-19-44/§3/ledd/3;;lov/2009-06-19-44/§2/ledd/4",
        ),
        "normalized_legs": (
            "lov/2009-06-19-44/§3/ledd/2;;lov/2009-06-19-44/§3/ledd/3",
            "lov/2009-06-19-44/§3/ledd/3;;lov/2009-06-19-44/§3/ledd/4",
        ),
    },
}

#: Every OTHER corpus ``data-move-part`` leg whose destination names a different
#: section from its source — 53 legs over 24 (instrument, base act) pairs — with
#: the leg text the lowering must hand through BYTE-IDENTICAL. Adjudicated by
#: shape, and the shapes are why the repair above can be this narrow:
#:
#: * 51 legs are ``§X ;; §Y`` SECTION relabels ("Nåværende §§ 41 til 43 blir nye
#:   §§ 48 til 50."). The destination section differing IS the instruction.
#: * 1 leg is ``§3/ledd/1/setning/2 ;; §4`` (``no/lovtid/2024-04-12-14``,
#:   "Nåværende § 3 første ledd andre punktum blir ny § 4.") — a genuine
#:   promotion out of its container, commanded by the prose.
#: * 1 leg is ``lov/1972-05-12-28/§55a/ledd/5;;4`` under base
#:   ``no/lov/2018-06-22-76``, which is both CROSS-BASE (the archive filed a
#:   strålevernloven endringsdel under the preceding act) and unresolvable on the
#:   destination side. It refuses at the shipped
#:   ``no_parse_cross_base_structured_renumber_skipped`` seam and must never
#:   reach this production at all.
#:
#: Not one of them is ledd-addressed on BOTH sides, which is limb 1 of the proof
#: — so the whole set declines at the first conjunct today. The set is still
#: pinned by content rather than by that count, because the day a member arrives
#: that DOES clear limb 1, its prose has to be read before anything moves.
_NO_MOVE_ATTR_CROSS_SECTION_UNTOUCHED: dict[tuple[str, str], tuple[str, ...]] = {
    ("no/lovtid/2024-04-12-14", "no/lov/1994-07-01-49"): (
        "lov/1994-07-01-49/§3/ledd/1/setning/2;;lov/1994-07-01-49/§4",
    ),
    ("no/lovtid/2024-04-12-14", "no/lov/2010-06-25-28"): (
        "lov/2010-06-25-28/§6;;lov/2010-06-25-28/§15",
        "lov/2010-06-25-28/§7;;lov/2010-06-25-28/§6",
        "lov/2010-06-25-28/§8;;lov/2010-06-25-28/§17",
    ),
    ("no/lovtid/2024-05-03-20", "no/lov/2011-06-24-30"): (
        "lov/2011-06-24-30/§3-9a;;lov/2011-06-24-30/§3-9b",
        "lov/2011-06-24-30/§3-9b;;lov/2011-06-24-30/§3-9c",
    ),
    ("no/lovtid/2024-12-20-100", "no/lov/2004-03-05-12"): (
        "lov/2004-03-05-12/§41;;lov/2004-03-05-12/§48",
        "lov/2004-03-05-12/§42;;lov/2004-03-05-12/§49",
        "lov/2004-03-05-12/§43;;lov/2004-03-05-12/§50",
    ),
    ("no/lovtid/2024-12-20-80", "no/lov/2021-04-16-18"): (
        "lov/2021-04-16-18/§8;;lov/2021-04-16-18/§9",
        "lov/2021-04-16-18/§9;;lov/2021-04-16-18/§10",
    ),
    ("no/lovtid/2024-12-20-86", "no/lov/1999-03-26-14"): (
        "lov/1999-03-26-14/§7-11;;lov/1999-03-26-14/§7-12",
    ),
    ("no/lovtid/2024-12-20-93", "no/lov/2005-06-10-44"): (
        "lov/2005-06-10-44/§4-17;;lov/2005-06-10-44/§4-21",
        "lov/2005-06-10-44/§4-18;;lov/2005-06-10-44/§4-22",
    ),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70"): (
        "lov/2015-06-19-70/§21;;lov/2015-06-19-70/§22",
    ),
    ("no/lovtid/2025-04-04-7", "no/lov/2008-05-15-35"): (
        "lov/2008-05-15-35/§90a;;lov/2008-05-15-35/§90g",
    ),
    ("no/lovtid/2025-04-10-10", "no/lov/2007-06-29-73"): (
        "lov/2007-06-29-73/§6-8;;lov/2007-06-29-73/§6-9",
        "lov/2007-06-29-73/§6-9;;lov/2007-06-29-73/§6-10",
        "lov/2007-06-29-73/§8-9;;lov/2007-06-29-73/§8-10",
    ),
    ("no/lovtid/2025-06-06-22", "no/lov/1947-06-19-5"): (
        "lov/1947-06-19-5/§2;;lov/1947-06-19-5/§3",
    ),
    ("no/lovtid/2025-06-20-100", "no/lov/2005-06-17-64"): (
        "lov/2005-06-17-64/§14;;lov/2005-06-17-64/§14a",
        "lov/2005-06-17-64/§14a;;lov/2005-06-17-64/§14c",
    ),
    ("no/lovtid/2025-06-20-101", "no/lov/2018-06-08-28"): (
        "lov/2018-06-08-28/§14a;;lov/2018-06-08-28/§28b",
    ),
    ("no/lovtid/2025-06-20-111", "no/lov/2002-06-21-45"): (
        "lov/2002-06-21-45/§9b;;lov/2002-06-21-45/§9c",
        "lov/2002-06-21-45/§9c;;lov/2002-06-21-45/§9d",
        "lov/2002-06-21-45/§9d;;lov/2002-06-21-45/§9e",
        "lov/2002-06-21-45/§9e;;lov/2002-06-21-45/§9g",
        "lov/2002-06-21-45/§9f;;lov/2002-06-21-45/§9h",
        "lov/2002-06-21-45/§9g;;lov/2002-06-21-45/§9i",
    ),
    ("no/lovtid/2025-06-20-46", "no/lov/1990-06-29-50"): (
        "lov/1990-06-29-50/§2-1;;lov/1990-06-29-50/§2-2",
        "lov/1990-06-29-50/§2-2;;lov/1990-06-29-50/§2-4",
        "lov/1990-06-29-50/§2-3;;lov/1990-06-29-50/§2-5",
    ),
    ("no/lovtid/2025-06-20-58", "no/lov/1999-03-26-14"): (
        "lov/1999-03-26-14/§14-82;;lov/1999-03-26-14/§14-83",
        "lov/1999-03-26-14/§14-83;;lov/1999-03-26-14/§14-84",
    ),
    ("no/lovtid/2025-06-20-64", "no/lov/2016-05-27-14"): (
        "lov/2016-05-27-14/§7-11;;lov/2016-05-27-14/§7-13",
        "lov/2016-05-27-14/§7-12;;lov/2016-05-27-14/§7-14",
        "lov/2016-05-27-14/§7-13;;lov/2016-05-27-14/§7-15",
    ),
    ("no/lovtid/2025-06-20-70", "no/lov/2018-06-22-76"): (
        "lov/1972-05-12-28/§55a/ledd/5;;4",
    ),
    ("no/lovtid/2025-06-20-90", "no/lov/2017-06-16-60"): (
        "lov/2017-06-16-60/§4;;lov/2017-06-16-60/§5",
        "lov/2017-06-16-60/§5;;lov/2017-06-16-60/§6",
        "lov/2017-06-16-60/§6;;lov/2017-06-16-60/§7",
        "lov/2017-06-16-60/§7;;lov/2017-06-16-60/§8",
    ),
    ("no/lovtid/2025-06-20-98", "no/lov/2003-07-04-84"): (
        "lov/2003-07-04-84/§7-2c;;lov/2003-07-04-84/§7-2d",
    ),
    ("no/lovtid/2026-06-19-40", "no/lov/2005-06-10-44"): (
        "lov/2005-06-10-44/§9-1;;lov/2005-06-10-44/§9-4",
    ),
    ("no/lovtid/2026-06-19-40", "no/lov/2015-04-10-17"): (
        "lov/2015-04-10-17/§22-5;;lov/2015-04-10-17/§22-6",
        "lov/2015-04-10-17/§22-6;;lov/2015-04-10-17/§22-7",
        "lov/2015-04-10-17/§22-7;;lov/2015-04-10-17/§22-8",
    ),
    ("no/lovtid/2026-06-19-40", "no/lov/2024-06-21-40"): (
        "lov/2024-06-21-40/§10;;lov/2024-06-21-40/§11",
        "lov/2024-06-21-40/§11;;lov/2024-06-21-40/§12",
        "lov/2024-06-21-40/§8;;lov/2024-06-21-40/§9",
        "lov/2024-06-21-40/§9;;lov/2024-06-21-40/§10",
    ),
    ("no/lovtid/2026-06-19-41", "no/lov/2005-06-17-67"): (
        "lov/2005-06-17-67/§10-31;;lov/2005-06-17-67/§10-40",
        "lov/2005-06-17-67/§10-32;;lov/2005-06-17-67/§10-41",
    ),
}


def _no_move_attr_leg_section(path: str) -> str:
    """The ``§X`` step of a Lovdata path, or ``""`` when it names none.

    A deliberately DUMBER reader than the parser's: it works on the raw attribute
    text rather than on a resolved ``LegalAddress``, so the census below stays a
    superset of the resolved population and cannot go blind on a leg whose
    address does not lower (``…§55a/ledd/5;;4`` is exactly that leg).
    """
    match = re.search(r"/(§[^/]+)", path)
    return match.group(1) if match else ""


@pytest.fixture(scope="module")
def _no_move_attr_destination_section_population():
    """Re-derive the whole cross-section ``data-move-part`` census, live.

    Two halves from one pass: the REPAIRED half off the typed receipt (so the pin
    reads what the production actually claims it did) and the UNTOUCHED half off
    the legs ``_split_move_attr`` hands the lowering (so the pin reads what the
    rest of the corpus actually gets, not what the receipt is silent about).
    """
    if not _REAL_ARCHIVE.exists():
        pytest.skip("requires the local Lovdata archive (data/norway.farchive)")
    from lawvm.norway.grafter import (
        _classes,
        _iter_change_descendants,
        _parse_document,
        _split_move_attr,
        normalize_lovdata_refid,
        parse_no_amendment_groups,
    )
    from lawvm.norway.sources import iter_no_amendment_artifacts

    repaired: dict[tuple[str, str], dict[str, object]] = {}
    untouched: dict[tuple[str, str], tuple[str, ...]] = {}
    attributes = 0
    artifacts = 0
    for artifact in iter_no_amendment_artifacts(_REAL_ARCHIVE):
        artifacts += 1
        adjudications: list = []
        parse_no_amendment_groups(
            artifact.payload, artifact.logical_id, adjudications_out=adjudications
        )
        for item in adjudications:
            if item.kind != _DESTINATION_SECTION_KIND:
                continue
            detail = item.detail or {}
            repaired[(artifact.logical_id, str(detail.get("base_id", "")))] = {
                "prose_pattern": str(detail.get("prose_pattern", "")),
                "declared_destination_section": str(
                    detail.get("declared_destination_section", "")
                ),
                "normalized_destination_section": str(
                    detail.get("normalized_destination_section", "")
                ),
                "declared_legs": tuple(detail.get("declared_legs", ())),
                "normalized_legs": tuple(detail.get("normalized_legs", ())),
            }
        root = _parse_document(artifact.payload)
        for doc_change in root.iter():
            if "document-change" not in _classes(doc_change):
                continue
            base_id = (
                normalize_lovdata_refid((doc_change.get("data-document") or "").strip()) or ""
            )
            for change_el in _iter_change_descendants(doc_change):
                value = change_el.get("data-move-part", "")
                if not value.strip():
                    continue
                attributes += 1
                differing = [
                    f"{source};;{destination}"
                    for source, destination in _split_move_attr(value, base_id=base_id)
                    if _no_move_attr_leg_section(source) != _no_move_attr_leg_section(destination)
                ]
                if differing:
                    key = (artifact.logical_id, base_id)
                    untouched[key] = tuple(sorted(set(untouched.get(key, ())) | set(differing)))
    for key in repaired:
        untouched.pop(key, None)
    return {
        "artifacts": artifacts,
        "attributes": attributes,
        "repaired": repaired,
        "untouched": untouched,
        "untouched_legs": sum(len(legs) for legs in untouched.values()),
    }


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_move_attr_destination_section_population_is_pinned(
    _no_move_attr_destination_section_population,
) -> None:
    """W-70b's standing tripwire: the cross-section population, both halves.

    286 of the corpus's amendment change blocks carry a ``data-move-part``. In
    exactly ONE the destination section is provably wrong, and it is repaired; in
    24 more (53 legs) the destination section differs because the instrument says
    so, and every one of those legs passes through byte-identical. Anything else
    — a second repair, a leg that stops being handed through, a new cross-section
    attribute nobody has read the prose of — is a finding, and this is where it
    surfaces.
    """
    population = _no_move_attr_destination_section_population
    assert population["artifacts"] == 3089, (
        f"the amendment plane holds {population['artifacts']} artifacts, not 3,089; "
        "the census below is measured over a different corpus. "
        + _DESTINATION_SECTION_POPULATION_INSTRUCTION
    )
    assert population["attributes"] == 286, (
        f"{population['attributes']} change blocks carry `data-move-part`, not 286. "
        + _DESTINATION_SECTION_POPULATION_INSTRUCTION
    )
    assert population["repaired"] == _NO_MOVE_ATTR_DESTINATION_SECTION_REPAIRED, (
        "The REPAIRED cross-section `data-move-part` attributes, or the legs they "
        "lower, are not the pinned set. These legs move live law. "
        + _DESTINATION_SECTION_POPULATION_INSTRUCTION
    )
    assert population["untouched"] == _NO_MOVE_ATTR_CROSS_SECTION_UNTOUCHED, (
        "The UNTOUCHED cross-section `data-move-part` legs are not the pinned set. A "
        "leg that LEFT this set was rewritten by the destination-section normalizer: "
        "if its prose does not prove an intra-section shift that is a STOP, not a pin "
        "to update. " + _DESTINATION_SECTION_POPULATION_INSTRUCTION
    )
    assert population["untouched_legs"] == 53


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_genuine_cross_section_moves_are_never_normalized(
    _no_move_attr_destination_section_population,
) -> None:
    """W-70b's must-not-repair set, asserted on its own.

    Split out from the census so its failure cannot be mistaken for ordinary
    population drift. These three are the shapes a careless widening would eat
    first: an ordinary section renumber, a genuine promotion out of a container,
    and a cross-base leg the archive mis-filed. Each is named with the prose that
    makes the destination section CORRECT, so "repairing" it would move a
    provision to an address no instrument names.
    """
    population = _no_move_attr_destination_section_population
    for key, leg in (
        # "Nåværende §§ 41 til 43 blir nye §§ 48 til 50." — a section renumber.
        (
            ("no/lovtid/2024-12-20-100", "no/lov/2004-03-05-12"),
            "lov/2004-03-05-12/§41;;lov/2004-03-05-12/§48",
        ),
        # "Nåværende § 3 første ledd andre punktum blir ny § 4." — a genuine
        # promotion of a sentence out of its ledd and into its own section.
        (
            ("no/lovtid/2024-04-12-14", "no/lov/1994-07-01-49"),
            "lov/1994-07-01-49/§3/ledd/1/setning/2;;lov/1994-07-01-49/§4",
        ),
        # A strålevernloven address filed under the preceding base act, whose
        # destination does not even lower. Cross-base first, unresolvable second.
        (
            ("no/lovtid/2025-06-20-70", "no/lov/2018-06-22-76"),
            "lov/1972-05-12-28/§55a/ledd/5;;4",
        ),
    ):
        assert key not in population["repaired"], (
            f"{key[0]} was REPAIRED under base {key[1]}. Its destination section is what "
            "the instrument commands. This is a STOP, not a pin to update. "
            + _DESTINATION_SECTION_POPULATION_INSTRUCTION
        )
        assert leg in population["untouched"].get(key, ()), (
            f"{leg} is no longer handed through byte-identical. "
            + _DESTINATION_SECTION_POPULATION_INSTRUCTION
        )


def _wrong_destination_section_amendment_xml(
    move: str = (
        "lov/2025-01-01-1/&#167;3/ledd/2;;lov/2025-01-01-1/&#167;2/ledd/3 "
        "lov/2025-01-01-1/&#167;3/ledd/3;;lov/2025-01-01-1/&#167;2/ledd/4"
    ),
    lead: str = "Noverande &#167; 3 andre og tredje ledd blir tredje og nytt fjerde ledd.",
) -> bytes:
    """``no/lovtid/2025-06-20-42``'s § 3 block in miniature.

    A well-formed ``data-move-part`` whose legs are ledd-addressed on both sides
    and whose destinations name § 2, under an announcement that spells § 3 and
    the same 2→3, 3→4 shift.
    """
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="dateInForce">2025-01-01</dd>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change" data-move-part="{move}">
        <article class="defaultP">{lead}</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def test_no_wrong_destination_section_is_normalized_from_the_blocks_own_prose() -> None:
    """W-70b: the legs land in the section the announcement names, not the one
    the attribute names.

    The ledd ordinals are asserted alongside the section because the repair is
    only allowed to touch the section component: 2→3 and 3→4 must survive the
    rewrite exactly as the markup declared them.
    """
    ops = parse_no_amendment_ops(
        _wrong_destination_section_amendment_xml(), "no/lovtid/2025-02-02-5"
    )
    assert [(str(op.target), str(op.destination)) for op in _renumber_ops(ops)] == [
        ("section:3/subsection:3", "section:3/subsection:4"),
        ("section:3/subsection:2", "section:3/subsection:3"),
    ]


def test_no_wrong_destination_section_repair_is_receipted() -> None:
    """W-70b: the rewrite is never silent — the receipt carries the attribute as
    declared, the attribute as normalized, and WHICH prose grammar proved it."""
    adjudications: list = []
    parse_no_amendment_ops(
        _wrong_destination_section_amendment_xml(),
        "no/lovtid/2025-02-02-5",
        adjudications_out=adjudications,
    )
    receipts = [a for a in adjudications if a.kind == _DESTINATION_SECTION_KIND]
    assert len(receipts) == 1, [a.kind for a in adjudications]
    receipt = receipts[0]
    assert receipt.blocking is False
    assert receipt.detail["reason"] == "prose_names_source_section_only"
    assert receipt.detail["prose_pattern"] == "shipped"
    assert receipt.detail["declared_destination_section"] == "2"
    assert receipt.detail["normalized_destination_section"] == "3"
    assert receipt.detail["declared_legs"] == (
        "lov/2025-01-01-1/§3/ledd/2;;lov/2025-01-01-1/§2/ledd/3",
        "lov/2025-01-01-1/§3/ledd/3;;lov/2025-01-01-1/§2/ledd/4",
    )
    assert receipt.detail["normalized_legs"] == (
        "lov/2025-01-01-1/§3/ledd/2;;lov/2025-01-01-1/§3/ledd/3",
        "lov/2025-01-01-1/§3/ledd/3;;lov/2025-01-01-1/§3/ledd/4",
    )


@pytest.mark.parametrize(
    ("case", "move", "lead", "expected"),
    [
        # Limb 4/5: the announcement must name the SOURCE section. Here it names
        # the DESTINATION's, so the sentence is evidence FOR the attribute, not
        # against it, and the attribute stands.
        (
            "prose_names_the_destination_section",
            None,
            "Noverande &#167; 2 andre og tredje ledd blir tredje og nytt fjerde ledd.",
            [
                ("section:3/subsection:3", "section:2/subsection:4"),
                ("section:3/subsection:2", "section:2/subsection:3"),
            ],
        ),
        # Limb 4: no currency qualifier, so the sentence never says which edition
        # its ordinals are read against — W-66's deliberate refusal, inherited.
        (
            "prose_has_no_currency_qualifier",
            None,
            "&#167; 3 andre og tredje ledd blir tredje og nytt fjerde ledd.",
            [
                ("section:3/subsection:3", "section:2/subsection:4"),
                ("section:3/subsection:2", "section:2/subsection:3"),
            ],
        ),
        # Limb 4: the announcement spells no section at all, so nothing in it
        # says the shift is intra-§3 rather than the move the markup declares.
        (
            "prose_spells_no_section",
            None,
            "Noverande andre og tredje ledd blir tredje og nytt fjerde ledd.",
            [
                ("section:3/subsection:3", "section:2/subsection:4"),
                ("section:3/subsection:2", "section:2/subsection:3"),
            ],
        ),
        # Limb 6: the prose commands 2→4 and 3→5, the markup declares 2→3 and
        # 3→4. The two disagree about WHICH ledd moves where, which is a larger
        # instruction than a section correction, so nothing is rewritten.
        (
            "prose_shift_map_disagrees",
            None,
            "Noverande &#167; 3 andre og tredje ledd blir fjerde og nytt femte ledd.",
            [
                ("section:3/subsection:3", "section:2/subsection:4"),
                ("section:3/subsection:2", "section:2/subsection:3"),
            ],
        ),
        # Limb 7: one stray cross-reference and the announcement stops being
        # unambiguously about a single section.
        (
            "prose_names_another_section",
            None,
            (
                "Noverande &#167; 3 andre og tredje ledd blir tredje og nytt fjerde "
                "ledd, jf. &#167; 5."
            ),
            [
                ("section:3/subsection:3", "section:2/subsection:4"),
                ("section:3/subsection:2", "section:2/subsection:3"),
            ],
        ),
        # Limb 1: a destination one step deeper than a ledd. Its section is not
        # separably wrong — the whole container might be — so it is out of reach.
        (
            "destination_is_deeper_than_a_ledd",
            (
                "lov/2025-01-01-1/&#167;3/ledd/2;;lov/2025-01-01-1/&#167;2/ledd/3/setning/1"
            ),
            "Noverande &#167; 3 andre ledd blir tredje ledd.",
            [("section:3/subsection:2", "section:2/subsection:3/sentence:1")],
        ),
        # Limb 2: two DIFFERENT destination sections in one attribute. There is no
        # single wrong section to correct, and picking one would be a guess.
        (
            "destinations_disagree_on_their_section",
            (
                "lov/2025-01-01-1/&#167;3/ledd/2;;lov/2025-01-01-1/&#167;2/ledd/3 "
                "lov/2025-01-01-1/&#167;3/ledd/3;;lov/2025-01-01-1/&#167;4/ledd/4"
            ),
            "Noverande &#167; 3 andre og tredje ledd blir tredje og nytt fjerde ledd.",
            [
                ("section:3/subsection:3", "section:4/subsection:4"),
                ("section:3/subsection:2", "section:2/subsection:3"),
            ],
        ),
    ],
)
def test_no_wrong_destination_section_repair_declines_without_a_full_proof(
    case: str, move: object, lead: str, expected: list[tuple[str, str]]
) -> None:
    """W-70b's polarity, limb by limb: anything unproven passes through UNCHANGED.

    Every case here is the SAME defective-looking attribute with one limb of the
    conjunction knocked out, and in every one the declared legs survive verbatim.
    Under-application is the safe direction — an unrepaired leg that contests a
    slot goes on refusing under W-69c's provability guard, which is the correct
    standing state for an instruction the system cannot read.
    """
    adjudications: list = []
    kwargs = {"lead": lead} if move is None else {"move": str(move), "lead": lead}
    ops = parse_no_amendment_ops(
        _wrong_destination_section_amendment_xml(**kwargs),  # type: ignore[arg-type]
        "no/lovtid/2025-02-02-5",
        adjudications_out=adjudications,
    )
    assert [(str(op.target), str(op.destination)) for op in _renumber_ops(ops)] == expected, case
    assert [a for a in adjudications if a.kind == _DESTINATION_SECTION_KIND] == [], case


def test_no_wrong_destination_section_repair_declines_a_cross_base_attribute() -> None:
    """W-70b limb 3, on W-70's precedent: the archive mis-files endringsdeler
    under the preceding base act, and a repair applied on top of that would
    relabel provisions of a law the block does not amend at that address.

    The legs are refused at the shipped cross-base seam, so nothing lowers — and
    crucially no repair receipt is minted either, because the decline happens
    before the prose is ever consulted.
    """
    adjudications: list = []
    ops = parse_no_amendment_ops(
        _wrong_destination_section_amendment_xml(
            move=(
                "lov/2019-01-01-9/&#167;3/ledd/2;;lov/2019-01-01-9/&#167;2/ledd/3 "
                "lov/2019-01-01-9/&#167;3/ledd/3;;lov/2019-01-01-9/&#167;2/ledd/4"
            )
        ),
        "no/lovtid/2025-02-02-5",
        adjudications_out=adjudications,
    )
    assert _renumber_ops(ops) == []
    assert [a for a in adjudications if a.kind == _DESTINATION_SECTION_KIND] == []
    assert [a.kind for a in adjudications] == [
        "no_parse_cross_base_structured_renumber_skipped",
        "no_parse_cross_base_structured_renumber_skipped",
    ]


def test_no_well_formed_intra_section_move_attr_is_left_exactly_alone() -> None:
    """W-70b's additive guarantee: an attribute whose destination section already
    agrees with its source's is not touched, and mints no receipt.

    This is the 180-attribute majority of the corpus, and the shipped lowering
    must be byte-identical for every one of them.
    """
    adjudications: list = []
    ops = parse_no_amendment_ops(
        _wrong_destination_section_amendment_xml(
            move=(
                "lov/2025-01-01-1/&#167;3/ledd/2;;lov/2025-01-01-1/&#167;3/ledd/3 "
                "lov/2025-01-01-1/&#167;3/ledd/3;;lov/2025-01-01-1/&#167;3/ledd/4"
            )
        ),
        "no/lovtid/2025-02-02-5",
        adjudications_out=adjudications,
    )
    assert [(str(op.target), str(op.destination)) for op in _renumber_ops(ops)] == [
        ("section:3/subsection:3", "section:3/subsection:4"),
        ("section:3/subsection:2", "section:3/subsection:3"),
    ]
    assert [a for a in adjudications if a.kind == _DESTINATION_SECTION_KIND] == []


# ── W-66c: the punktum-depth REPEAL, and the two tripwires it owes ────────────
#
# READ THE POLARITY FIRST, because it is not the hazard census's. Every element
# of the table below is a sentence of in-force Norwegian law that this system
# DELETES. That is what the instruments command — "§ 20 første ledd annet
# punktum oppheves." — and each one was adjudicated against its own
# ``article.defaultP`` node's own text before the production landed
# (``.tmp/w66c/dom_adjudications.json``: 33 of 33, and none of them inherited —
# every landed destruction's lead spells BOTH its section and its ledd). But a
# destroying production is the one place in this programme where "the number
# moved" is not a re-pin, and these two tests exist so that it cannot be.
#
# TWO tripwires, because the destroying surface has two sizes and only one of
# them is visible in the replayed corpus:
#
#   1. the PARSE-plane population — every ``setning/N`` REPEAL the production
#      mints corpus-wide, 279 legs over 120 base acts. This is what COULD be
#      destroyed, and it grows with a new lead shape or an archive refresh.
#      Digested rather than listed, because 279 addresses in a test file is a
#      wall nobody reads; the failure message says where the list lives.
#   2. the APPLY-plane set — the 33 sentences actually removed, pinned BY
#      CONTENT (base act, address, the sentence's own text). Most of the 279
#      never destroy anything: the 279 ops name 256 distinct addresses (23 are
#      commanded twice, mostly by the twin omnibus acts ``no/lovtid/2009-06-19-74``
#      and ``no/lovtid/2015-06-19-65``), and of those 256, 182 sit on one of the
#      73 base acts whose replay errors before reaching them — no replayable
#      original-act source (item 81's standing caution, re-derived) — 35 never
#      reach the apply plane, 6 refuse there typed, and 33 destroy.
#      The base acts replayed here are DERIVED from tripwire 1
#      rather than listed, so a law that starts destroying because its source
#      arrived in a refresh is caught here instead of missed.
#
# A NEW row in either is a finding: read the instrument's own DOM node, decide
# whether it commands the destruction of that sentence at that address, and
# record it in the ledger before touching either table. A row that DISAPPEARS is
# equally a finding — a repeal that stops landing means a provision this system
# had removed is standing again.
_W66C_DESTRUCTION_INSTRUCTION = (
    "The punktum-depth repeal's destroying surface moved. Do NOT relax this pin. "
    "For each destruction that ENTERED: read the lead off the `article.defaultP` "
    "node the parser reads (never a text-plane grep), confirm it names THAT "
    "section, THAT ledd and THAT ordinal, and confirm the removed text is the "
    "sentence that ordinal counts to. For each that LEFT: say in the ledger which "
    "item stopped the repeal landing, because a provision this system had removed "
    "is standing again. Re-derive with `.tmp/w66c/s11_removals.py` at both pins "
    "and `.tmp/w66c/s13_destruction_diff.py`."
)

#: Every ``setning/N`` REPEAL the production mints, corpus-wide, as
#: ``<base_id>|<address>`` lines joined by newlines and sha256'd. Regenerate with
#: ``.tmp/w66c/s25_emit_pin.py``.
_W66C_MINTED_REPEAL_LEGS_DIGEST = (
    "2a1577d65bddff9732b169e30a69d97adb7b966861953c70472e214a1ddafdfd"
)

# 33 destructions over 29 base acts; 34/30 at W-98; 50/36 at W-100 (2026-09-05).
# W-100's 18 entrants and 2 leavers are all COMMENCEMENT movements, not grammar
# ones: the section-scoped lane and the title-cited citation form date acts
# whose punktum-depth repeals had been minted since W-66c and refused at replay
# as contingent — ``no/lovtid/2013-01-11-3`` (nine rows over four laws),
# ``2013-06-21-92`` (four), ``2010-03-26-8``, ``2010-06-04-20``, ``2015-06-19-79``,
# ``2015-11-20-94``, ``2016-06-17-72``, ``2016-12-16-90``, ``2018-12-20-98``. Each
# entrant was adjudicated by its lead: the ``article.defaultP`` text names the
# section, ledd and ordinal(s) of exactly the address(es) minted (``§ 73 fjerde
# ledd annet til fjerde punktum oppheves.`` -> sentence 2, 3, 4). The two
# leavers are the SAME two addresses re-entering with different text
# (``no/lov/2006-06-16-20`` § 7 andre ledd andre punktum, ``no/lov/2008-05-15-35``
# § 76 annet ledd annet punktum): an act newly dated EARLIER than the repealing
# one now rewrites that ledd first, so the ordinal counts to a different
# sentence at the repeal's moment. See ledger item 100 for what stands.
_W66C_CORPUS_DESTRUCTIONS: tuple[tuple[str, str, str], ...] = (
    (
        'no/lov/2001-05-18-21',
        'section:16a/subsection:2/sentence:2',
        'Kriminalomsorgen skal vurdere innsatte i avdeling med særlig høyt sikkerhetsnivå for overføring til fengsel med høyt sikkerhetsnivå med ikke mer enn 6 måneders mellomrom.',
    ),
    (
        'no/lov/2001-06-15-75',
        'section:31/subsection:3/sentence:2',
        'Det betales i disse tilfelle et gebyr etter en norm som departementet fastsetter.',
    ),
    (
        'no/lov/2002-06-21-34',
        'section:26/subsection:3/sentence:3',
        'Avtalefriheten gjelder likevel ikke for installeringsforpliktelser som inngår i salgsavtalen.',
    ),
    (
        'no/lov/2002-06-21-45',
        'section:37b/subsection:2/sentence:1',
        'Det blir stilt same krav til helse m.m. som for førarkort klasse D og DE.',
    ),
    (
        'no/lov/2003-02-21-12',
        'section:18/subsection:2/sentence:2',
        'Medvirkning straffes på samme måte.',
    ),
    (
        'no/lov/2003-03-14-15',
        'section:39/subsection:2/sentence:3',
        'Det kan ikke gis oppfriskning mot oversittelse av søksmålsfristen.',
    ),
    (
        'no/lov/2003-06-27-64',
        'section:9/subsection:2/sentence:2',
        'Medvirkning straffes på samme måte.',
    ),
    (
        'no/lov/2003-07-04-80',
        'section:19/subsection:2/sentence:2',
        'Like med offentlige organer regnes organisasjoner og private som utfører oppgaver for stat, fylkeskommune eller kommune.',
    ),
    (
        'no/lov/2003-12-19-130',
        'section:7/subsection:1/sentence:2',
        'Senere endringer av innskuddet vedtas av foretaksmøtet.',
    ),
    (
        'no/lov/2005-04-01-15',
        'section:3-5/subsection:5/sentence:2',
        'Departementet kan i forskrift gi regler om NOKUTs ansvar og myndighet.',
    ),
    (
        'no/lov/2005-05-20-28',
        'section:72/subsection:2/sentence:2',
        'Dette gjelder likevel ikke for formuesgoder som ble overdratt mer enn 5 år før den handling som danner grunnlag for inndragningen, ble begått, eller formuesgoder som er mottatt til vanlig underhold fra en som plikter å yte slikt underhold.',
    ),
    (
        'no/lov/2005-06-10-51',
        'section:20/subsection:1/sentence:2',
        'Melderen må godtgjøre at vedkommende senest ved ervervet er løst fra annet statsborgerskap.',
    ),
    (
        'no/lov/2005-06-17-67',
        'section:11-4/subsection:2/sentence:2',
        'I saker om kildeskatt på utbytte beregnes renten fra det ferdige skatteoppgjøret etter ordinær avregning ble sendt selskapet som har trukket kildeskatten.',
    ),
    (
        'no/lov/2006-06-16-20',
        'section:18/subsection:2/sentence:2',
        'Det kan herunder bestemmes at Statens innkrevingssentral skal foreta innkrevingen av feilutbetalte ytelser etter arbeidsmarkedsloven og etter folketrygdloven kapitlene 4 og 11 og opptre på statens vegne ved innkrevingen i samsvar med tidligere §§ 23 og 24 i arbeidsmarkedsloven.',
    ),
    (
        'no/lov/2006-06-16-20',
        'section:7/subsection:2/sentence:2',
        'Det kan herunder bestemmes at Statens innkrevingssentral skal foreta innkrevingen av feilutbetalte ytelser etter arbeidsmarkedsloven og etter folketrygdloven kapitlene 4 og 11 og opptre på statens vegne ved innkrevingen i samsvar med tidligere §§ 23 og 24 i arbeidsmarkedsloven.',
    ),
    (
        'no/lov/2007-02-16-9',
        'section:57/subsection:1/sentence:2',
        'Ved inndrivelse av overtredelsesgebyr gjelder bestemmelsen i § 48 annet ledd tilsvarende.',
    ),
    (
        'no/lov/2007-06-29-44',
        'section:8/subsection:1/sentence:3',
        'Departementet oppnevner to varamedlemmer til styret.',
    ),
    (
        'no/lov/2007-06-29-75',
        'section:7-8/subsection:6/sentence:2',
        'Departementet kan bestemme at hele eller deler av Kredittilsynets myndighet etter dette kapittelet skal utøves av et regulert marked.',
    ),
    (
        'no/lov/2007-06-29-81',
        'section:8/subsection:2/sentence:2',
        'Umyndige kan ikkje vere stiftarar.',
    ),
    (
        'no/lov/2008-05-15-35',
        'section:104/subsection:3/sentence:2',
        'Vernet mot utsendelse er ikke til hinder for at det treffes vedtak om utvisning etter § 66 første ledd bokstav f, § 67 første ledd bokstav e eller § 68 første ledd bokstav d.',
    ),
    (
        'no/lov/2008-05-15-35',
        'section:73/subsection:4/sentence:2',
        'Vernet mot utsendelse er ikke til hinder for at det treffes vedtak om utvisning etter § 66 første ledd bokstav f, § 67 første ledd bokstav e eller § 68 første ledd bokstav d.',
    ),
    (
        'no/lov/2008-05-15-35',
        'section:73/subsection:4/sentence:3',
        'Slikt vedtak kan ikke iverksettes før grunnlaget for utsendelsesvernet er bortfalt.',
    ),
    (
        'no/lov/2008-05-15-35',
        'section:73/subsection:4/sentence:4',
        'Slikt vedtak kan ikke iverksettes før grunnlaget for utsendelsesvernet er bortfalt.',
    ),
    (
        'no/lov/2008-05-15-35',
        'section:76/subsection:2/sentence:2',
        'Vernet mot utsendelse er ikke til hinder for at det treffes vedtak om utvisning etter § 66 første ledd bokstav f, § 67 første ledd bokstav e eller § 68 første ledd bokstav d.',
    ),
    (
        'no/lov/2008-05-15-35',
        'section:76/subsection:2/sentence:3',
        'Slikt vedtak kan ikke iverksettes før grunnlaget for utsendelsesvernet er bortfalt.',
    ),
    (
        'no/lov/2008-06-27-71',
        'section:12-14/subsection:2/sentence:2',
        'Små endringer kan delegeres til administrasjonen.',
    ),
    (
        'no/lov/2009-04-17-19',
        'section:62/subsection:4/sentence:1',
        'Medvirkning straffes på samme måte.',
    ),
    (
        'no/lov/2009-06-19-101',
        'section:13/subsection:1/sentence:2',
        'Undersøkelsesrett kan bare nektes dersom søkeren tidligere har brutt vesentlige bestemmelser gitt i eller i medhold av denne lov.',
    ),
    (
        'no/lov/2009-06-19-58',
        'section:15-8/subsection:2/sentence:3',
        'Oppgave som er levert på papir anses kommet fram hvis den er poststemplet innen utløpet av fristen.',
    ),
    (
        'no/lov/2009-06-19-58',
        'section:22-1/subsection:1/sentence:2',
        'Omsetningsoppgave som er levert på papir skal undertegnes.',
    ),
    (
        'no/lov/2009-06-19-97',
        'section:36/subsection:1/sentence:2',
        'På samme måte straffes medvirkning.',
    ),
    (
        'no/lov/2009-06-19-97',
        'section:37/subsection:1/sentence:2',
        'På samme måte straffes medvirkning.',
    ),
    (
        'no/lov/2010-03-26-9',
        'section:68/subsection:1/sentence:2',
        'Retten kan oppnevne verge, jf. 25 første ledd annet punktum.',
    ),
    (
        'no/lov/2010-06-04-21',
        'section:10-9/subsection:2/sentence:3',
        'Gebyr blir kravd inn av Statens innkrevjingssentral.',
    ),
    (
        'no/lov/2010-06-04-21',
        'section:10-9/subsection:2/sentence:4',
        'Innkrevjingssentralen kan drive inn kravet ved trekk i lønn og andre liknande ytingar etter reglane i lov 8. juni 1984 nr. 59 om fordringshavernes dekningsrett (dekningsloven) § 2-7.',
    ),
    (
        'no/lov/2010-06-04-21',
        'section:10-9/subsection:2/sentence:5',
        'Innkrevjingssentralen kan òg drive inn kravet ved å stifte utleggspant for kravet dersom panteretten kan gjevast rettsvern ved registrering i eit register eller ved melding til tredjeperson, jf. lov 8. februar 1980 nr. 2 om pant (panteloven) kapittel 5, og utleggsforretninga kan haldast på Innkrevjingssentralens kontor etter lov 19. juni 1992 nr. 86 om tvangsfullbyrdelse (tvangsfullbyrdelsesloven) § 7-9 første ledd.',
    ),
    (
        'no/lov/2011-06-24-29',
        'section:18/subsection:1/sentence:2',
        'Medvirkning straffes på samme måte.',
    ),
    (
        'no/lov/2011-06-24-30',
        'section:10-2/subsection:2/sentence:2',
        'Fylkesnemnda skal samtidig ta stilling til om det skal være adgang til å ta urinprøver av pasienten under institusjonsoppholdet.',
    ),
    (
        'no/lov/2011-06-24-30',
        'section:10-3/subsection:1/sentence:2',
        'Fylkesnemnda skal samtidig ta stilling til om det skal være adgang til å ta urinprøver av pasienten under institusjonsoppholdet.',
    ),
    (
        'no/lov/2011-06-24-39',
        'section:18/subsection:1/sentence:3',
        'Krav på gebyr innkreves av Statens innkrevingssentral.',
    ),
    (
        'no/lov/2011-06-24-39',
        'section:26/subsection:2/sentence:2',
        'Ilagt gebyr er tvangsgrunnlag for utlegg.',
    ),
    (
        'no/lov/2011-06-24-39',
        'section:26/subsection:2/sentence:3',
        'Krav på gebyr innkreves av Statens innkrevingssentral.',
    ),
    (
        'no/lov/2011-06-24-39',
        'section:26/subsection:2/sentence:4',
        'Innkrevingssentralen kan inndrive kravet ved trekk i lønn og andre lignende ytelser etter reglene i dekningsloven § 2-7.',
    ),
    (
        'no/lov/2011-11-25-44',
        'section:11-1/subsection:1/sentence:2',
        'For depotmottaker gjelder tilsvarende ansvar for tap som påføres ved forsømmelser i depotmottakeroppgaven.',
    ),
    (
        'no/lov/2012-06-22-43',
        'section:5/subsection:1/sentence:2',
        'Skattedirektoratet kan etter søknad samtykke til papirinnlevering for private arbeidsgivere.',
    ),
    (
        'no/lov/2016-05-27-14',
        'section:7-5/subsection:1/sentence:2',
        'Den som mot godtgjøring har formidlet leie av fast eiendom, skal gi opplysninger om inngåtte kontrakter siste år med den enkelte utleier, avtalt leie og i tilfelle leie som er påløpt, og leie som vedkommende har betalt eller formidlet betaling av.',
    ),
    (
        'no/lov/2016-06-17-29',
        'section:5/subsection:1/sentence:2',
        'Kravet gjelder ikke for Forbrukerrådet.',
    ),
    (
        'no/lov/2020-11-06-127',
        'section:47/subsection:1/sentence:2',
        'Departementet er klageinstans for enkeltvedtak etter § 46 første ledd bokstav j.',
    ),
    (
        'no/lov/2021-06-18-121',
        'section:20/subsection:1/sentence:2',
        'Unntatt fra dette er regjeringsnotater og dokumenter direkte knyttet til disse.',
    ),
    (
        'no/lov/2022-03-11-9',
        'section:2-3/subsection:1/sentence:3',
        'Melding kan gis av andre på førerens vegne.',
    ),
)


@pytest.fixture(scope="module")
def _no_w66c_minted_repeals():
    """Corpus-wide: every op the punktum-depth repeal production mints.

    Re-derived from a live parse of every amendment artifact through the
    production entry point — the same instrument W-70's malformed-attr census
    uses, and for the same reason: a receipt-plane census cannot see a lead the
    parser has STOPPED refusing.

    The ops are identified by what they ARE, not by a tag: action ``REPEAL``, a
    ``sentence`` leaf, and the unstructured provenance. The structured
    ``data-repeal-part`` lane also reaches sentence leaves (7 corpus-wide) and
    carries only ``base_act:``, so the ``fallback:unstructured`` conjunct is what
    separates the two. That every survivor's own ``raw_text`` re-parses through
    the shipped grammar to the very ordinal the op targets is asserted below
    rather than assumed — the cheapest available proof that the emission site and
    the grammar have not drifted apart.
    """
    if not _REAL_ARCHIVE.exists():
        pytest.skip("requires the local Lovdata archive (data/norway.farchive)")
    from lawvm.norway.grafter import parse_no_amendment_groups
    from lawvm.norway.sources import iter_no_amendment_artifacts

    legs: list[dict] = []
    artifacts = 0
    for artifact in iter_no_amendment_artifacts(_REAL_ARCHIVE):
        artifacts += 1
        for base_id, ops in parse_no_amendment_groups(
            artifact.payload, artifact.logical_id, adjudications_out=[]
        ):
            for op in ops:
                if op.action is not StructuralAction.REPEAL:
                    continue
                if op.target.leaf_kind() != "sentence":
                    continue
                if "fallback:unstructured" not in (op.provenance_tags or ()):
                    continue
                legs.append(
                    {
                        "base_id": base_id,
                        "address": "/".join(f"{k}:{v}" for k, v in op.target.path),
                        "lead": op.source.raw_text if op.source is not None else "",
                        "source_id": artifact.logical_id,
                    }
                )
    return {"artifacts": artifacts, "legs": legs}


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_w66c_minted_punktum_repeal_population_is_pinned(_no_w66c_minted_repeals) -> None:
    """Tripwire 1: what the production COULD destroy, corpus-wide."""
    import hashlib

    from lawvm.norway.grafter import _no_punktum_repeal_targets

    population = _no_w66c_minted_repeals
    assert population["artifacts"] == 3089, (
        f"the amendment plane holds {population['artifacts']} artifacts, not 3,089; "
        "the census below is measured over a different corpus. "
        + _W66C_DESTRUCTION_INSTRUCTION
    )
    legs = population["legs"]
    assert len(legs) == 279, _W66C_DESTRUCTION_INSTRUCTION
    assert len({leg["base_id"] for leg in legs}) == 120, _W66C_DESTRUCTION_INSTRUCTION
    assert len({leg["lead"] for leg in legs}) == 207, _W66C_DESTRUCTION_INSTRUCTION

    digest = hashlib.sha256(
        "\n".join(sorted(f"{leg['base_id']}|{leg['address']}" for leg in legs)).encode("utf-8")
    ).hexdigest()
    assert digest == _W66C_MINTED_REPEAL_LEGS_DIGEST, (
        "The ADDRESSES the punktum repeal mints are not the pinned set. "
        + _W66C_DESTRUCTION_INSTRUCTION
    )

    # The emission site and the grammar still agree, leg by leg: every op's own
    # lead re-parses, and the ordinal it names is the one the op targets.
    for leg in legs:
        parsed = _no_punktum_repeal_targets(leg["lead"])
        assert parsed is not None, leg
        _section, _ledd, ordinals = parsed
        assert leg["address"].rsplit(":", 1)[1] in {str(o) for o in ordinals}, leg


def _w66c_removal_probe(original, sink: list[tuple[str, str]]):
    """A ``tree_ops.remove_at`` that records the node it is about to remove.

    A FACTORY rather than a closure written at the loop body, because both
    linters have an opinion and they pull in opposite directions: a closure over
    the loop's own names is ruff's B023, and a probe with extra defaulted
    parameters does not match the attribute's declared signature. Binding the
    two values as arguments here satisfies both and makes the capture explicit.
    """

    def probe(tree: IRNode, path: Sequence[tuple[str, str]]) -> IRNode:
        from lawvm.core import tree_ops

        node = tree_ops.resolve(tree, path)
        if node is not None and path:
            sink.append((f"{path[-1][0]}:{path[-1][1]}", node.text or ""))
        return original(tree, path)

    return probe


@pytest.fixture(scope="module")
def _no_w66c_realized_destructions(_no_w66c_minted_repeals):
    """The sentences the corpus replay actually removes, with their own text.

    ``tree_ops.remove_at`` is the single seam every removal in the NO apply plane
    goes through, so wrapping it captures the node BEFORE it is gone — which no
    receipt can do, because a receipt names paths and not text. The receipts are
    what ATTRIBUTES a removal, and the minted set from tripwire 1 is what tells
    this production's sentence repeals from the STRUCTURED lane's: seven
    ``data-repeal-part`` repeals reach a sentence leaf corpus-wide, two of them on
    a base act this fixture replays (``no/lov/2008-05-15-35`` § 27 første ledd
    tredje and fjerde punktum), and a receipt carries no provenance tag to
    separate them by. Joining on the ADDRESS the parse plane minted does.
    """
    from lawvm.core import tree_ops
    from lawvm.norway.index import build_no_amendment_index

    minted = {
        (leg["base_id"], leg["address"]) for leg in _no_w66c_minted_repeals["legs"]
    }
    index = build_no_amendment_index(_REAL_ARCHIVE)
    out: list[tuple[str, str, str]] = []
    for base_id in sorted({leg["base_id"] for leg in _no_w66c_minted_repeals["legs"]}):
        removed: list[tuple[str, str]] = []
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                tree_ops, "remove_at", _w66c_removal_probe(tree_ops.remove_at, removed)
            )
            replay = replay_no_to_pit(
                base_id, as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index
            )
        by_leaf: dict[str, list[str]] = {}
        for leaf, text in removed:
            by_leaf.setdefault(leaf, []).append(text)
        for receipt in replay.write_receipts:
            bound = tuple(receipt.bound_target_path or ())
            if str(receipt.action) != "repeal" or not bound or bound[-1][0] != "sentence":
                continue
            if not receipt.removed_paths:
                continue
            address = "/".join(f"{k}:{v}" for k, v in bound)
            if (base_id, address) not in minted:
                continue
            texts = by_leaf.get(f"{bound[-1][0]}:{bound[-1][1]}") or []
            out.append((base_id, address, texts.pop(0) if texts else ""))
    return sorted(out)


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_w66c_corpus_destruction_set_is_pinned_by_content(
    _no_w66c_realized_destructions,
) -> None:
    """Tripwire 2: what the production ACTUALLY destroys, by text.

    50 sentences over 36 base acts (34/30 before W-100, 33/29 before W-98). Pinned with their own TEXT rather than by
    address alone, because an address-only pin would pass while the sentence
    splitter counted to a different sentence — which is the one way this
    production can be wrong and stay quiet.
    """
    realized = _no_w66c_realized_destructions
    # 33/29 -> 34/30 at W-98: one entrant, adjudicated by text in the pinned
    # tuple (yrkestransportlova § 37 b andre ledd første punktum).
    # 34/30 -> 50/36 at W-100: eighteen entrants and two leavers, every one a
    # commencement movement — see the note on the pinned tuple.
    assert len(realized) == 50, _W66C_DESTRUCTION_INSTRUCTION
    assert len({row[0] for row in realized}) == 36, _W66C_DESTRUCTION_INSTRUCTION
    assert tuple(realized) == _W66C_CORPUS_DESTRUCTIONS, _W66C_DESTRUCTION_INSTRUCTION


@pytest.mark.skipif(
    not _REAL_ARCHIVE.exists(),
    reason="requires the local Lovdata archive (data/norway.farchive)",
)
def test_no_w66c_witness_law_reads_as_the_instrument_commands(
    _no_w66c_realized_destructions,
) -> None:
    """W-66c's corpus witness, end to end and BY TEXT.

    ``no/lovtid/2022-06-10-38`` commands exactly two instructions on
    ``no/lov/2021-06-18-121`` § 20 første ledd, and until this item only the
    second of them lowered:

        § 20 første ledd annet punktum oppheves.
        Nåværende tredje punktum blir annet punktum.

    Three states, in order. At W-66 the ledd was one text node and nothing
    addressed it. At W-66b the relabel lowered and REFUSED at apply, because slot
    2 was still held by the sentence this item repeals — had W-66's guard not
    been there the θ ``(RENUMBER, dest_occupied)`` cell would have deleted that
    sentence as a side effect of a renumber, which is W-54's ``removal_wrong``
    shape one depth word down. Now both lower: the repeal runs FIRST (the
    kernel's structural-vacate stage orders every REPEAL in a group ahead of
    every RENUMBER, and ``_no_group_key`` is ``(effective, enacted, source_id)``,
    so one instrument at one moment is one group), the slot is vacated, the
    relabel lands behind it with no apply-plane edit of any kind, and the law's
    § 20 første ledd divergence row CLOSES.

    The surviving text is what is asserted, in order: the repealed sentence
    absent, the relabelled sentence standing in slot 2.
    """
    from lawvm.norway.index import build_no_amendment_index

    index = build_no_amendment_index(_REAL_ARCHIVE)
    replay = replay_no_to_pit(
        "no/lov/2021-06-18-121", as_of="2026-07-10", data_dir=_REAL_ARCHIVE, index=index
    )
    assert replay.error is None
    assert replay.replayed is not None

    ledd = None
    for chapter in replay.replayed.body.children:
        for section in chapter.children:
            if section.label != "20":
                continue
            for child in section.children:
                if child.kind is IRNodeKind.SUBSECTION and child.label == "1":
                    ledd = child
    assert ledd is not None
    assert [(child.label, child.text) for child in ledd.children] == [
        (
            "1",
            "Sivilombudet kan, uten hinder av taushetsplikt, pålegge den som er "
            "omfattet av arbeidsområdet i § 4, å gi enhver opplysning og ethvert "
            "dokument som er nødvendig for å utøve oppgaver etter loven her.",
        ),
        ("2", "Ombudet kan fastsette en frist for å etterkomme et slikt pålegg."),
    ]
    # The sentence that is GONE, named: it is in the corpus destruction table
    # above, and it was the occupant that made W-66b's relabel refuse.
    assert (
        "no/lov/2021-06-18-121",
        "section:20/subsection:1/sentence:2",
        "Unntatt fra dette er regjeringsnotater og dokumenter direkte knyttet til disse.",
    ) in _no_w66c_realized_destructions
    # The relabel LANDED — W-66b's refusal is gone from this law — and it landed
    # as a renumber into a vacated slot, not as a θ recovery that ate an occupant.
    assert not [
        a
        for a in replay.adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert not [
        a
        for a in replay.adjudications
        if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]
