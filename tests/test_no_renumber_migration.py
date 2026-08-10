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
import tarfile
from pathlib import Path as _Path

import pytest

from lawvm.core.ir import LegalOperation
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
        "no_replay_renumber_occupied_destination_removed"
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
        "no_replay_renumber_occupied_destination_removed"
    ) == 1


# ---- corpus pin ------------------------------------------------------------

_REPO_ROOT = _Path(__file__).resolve().parents[1]
_REAL_ARCHIVE = _REPO_ROOT / "data" / "norway.farchive"

#: Every base law in the Lovdata corpus that fires — or used to fire —
#: ``no_replay_renumber_occupied_destination_removed`` at as-of 2026-07-10,
#: with (firings, receipts carrying a collateral ``removed_paths`` entry).
#: Measured over all 782 base laws with an indexed amendment source.
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
_NO_OCCUPIED_DESTINATION_LAWS: dict[str, tuple[int, int]] = {
    "no/lov/2001-01-05-1": (2, 0),
    "no/lov/2003-07-04-84": (1, 0),
    "no/lov/2004-12-17-99": (2, 1),
    "no/lov/2005-06-10-44": (2, 2),
    "no/lov/2005-06-17-67": (0, 0),  # W-61: repaired at the lowering; see above.
    "no/lov/2005-06-17-90": (0, 0),  # W-56: repaired at the lowering; see above.
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
    "no/lovtid/2024-06-14-34:3": (
        "no/lov/2003-07-04-84",
        "chapter:2/section:2-2/subsection:4",
        "chapter:2/section:2-2/subsection:5",
        "removal_correct",
        "skolen må være registrert i einingsregisteret jf lov 3",
        (),
    ),
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
    "no/lovtid/2015-04-10-17:27": (
        "no/lov/2005-06-10-44",
        "part:3/chapter:7/section:7-8",
        "part:2/chapter:2/section:2-4",
        "removal_correct",
        "utenlandsk forsikringsselskap kan gis konsesjon til å drive virksomhet",
        (),
    ),
    "no/lovtid/2015-04-10-17:106": (
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
    """Corpus pin (W-56, deferred from W-54): every ``(RENUMBER, dest_occupied)``
    firing in the corpus is an ADJUDICATED one, and each one's effect on the
    occupant's text is the effect W-54 recorded.

    Read the asymmetry on ``_NO_OCCUPIED_DESTINATION_VERDICTS`` before touching
    this test: one row is pinned WRONG on purpose and belongs to W-58.
    """
    observed: dict[str, tuple[str, str, str]] = {}
    for base_id, replay in sorted(_no_occupied_destination_replays.items()):
        assert replay.error is None, (base_id, replay.error)
        for a in replay.adjudications:
            if a.kind != "no_replay_renumber_occupied_destination_removed":
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
        if a.kind == "no_replay_renumber_occupied_destination_removed"
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
        if a.kind == "no_replay_renumber_occupied_destination_removed"
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
            if a.kind == "no_replay_renumber_occupied_destination_removed"
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
    assert sum(f for f, _ in observed.values()) == 8
    assert sum(c for _, c in observed.values()) == 3
    # The two tables must agree on the firing population, so neither can drift
    # alone: one row per firing, keyed by op_id.
    assert sum(f for f, _ in observed.values()) == len(_NO_OCCUPIED_DESTINATION_VERDICTS)
