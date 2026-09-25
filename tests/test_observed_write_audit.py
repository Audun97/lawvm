from __future__ import annotations

from typing import cast

import pytest

from lawvm.core import tree_ops
from lawvm.core.apply_seam import (
    OCCUPANCY_TRANSITION_BLOCKED_FINDING_CODE,
    WRITE_RECEIPT_AUDIT_VIOLATION_FINDING_CODE,
    ApplyProfile,
    MaterializeResult,
    apply_op,
)
from lawvm.core.occupancy import OccupancyClass
from lawvm.core.ir import IRNode, LegalAddress, LegalOperation, OperationSource
from lawvm.core.observed_write_audit import (
    ObservedWriteAudit,
    build_observed_write_audit,
)
from lawvm.core.provenance import SourceAnchor
from lawvm.core.phase_result import Finding
from lawvm.core.semantic_types import IRNodeKind, StructuralAction
from lawvm.core.write_receipt import WriteReceipt


def _section(label: str, text: str) -> IRNode:
    return IRNode(kind=IRNodeKind.SECTION, label=label, text=text)


def _body(*children: IRNode) -> IRNode:
    return IRNode(kind=IRNodeKind.BODY, children=children)


def test_observed_write_audit_clean_when_observed_and_receipt_paths_match() -> None:
    before = _body(_section("1", "old"))
    after = _body(_section("1", "new"))
    receipt = WriteReceipt(
        op_id="replace_1",
        helper="test",
        action="replace",
        bound_target_path=(("section", "1"),),
        landed_primary_path=(("section", "1"),),
        replaced_paths=((("section", "1"),),),
    )

    audit = build_observed_write_audit(before, after, receipt)

    assert audit.audit_status == "clean"
    assert audit.observed_changed_paths == ((("section", "1"),),)
    assert audit.receipt_declared_paths == ((("section", "1"),),)
    assert audit.undeclared_paths == ()
    assert audit.unobserved_declared_paths == ()
    assert audit.matched_rule_ids == ()


def test_observed_write_audit_qualified_for_named_relabel_parent_child_granularity() -> None:
    before = _body(_section("1", "same"))
    after = _body(_section("2", "same"))
    receipt = WriteReceipt(
        op_id="renumber_1_to_2",
        helper="test",
        action="renumber",
        bound_target_path=(("section", "1"),),
        landed_primary_path=(("section", "2"),),
        renumbered_paths=(((("section", "1"),), (("section", "2"),)),),
        migration_rule_ids=("section_relabel_renumber",),
    )

    audit = build_observed_write_audit(before, after, receipt)

    assert audit.audit_status == "qualified"
    assert audit.observed_changed_paths == ((),)
    assert audit.receipt_declared_paths == ((("section", "1"),), (("section", "2"),))
    assert audit.undeclared_paths == ()
    assert audit.unobserved_declared_paths == ()
    assert audit.matched_rule_ids == ("section_relabel_renumber",)


def test_observed_write_audit_flags_declared_write_with_no_observed_change() -> None:
    before = _body(_section("1", "same"))
    after = before
    receipt = WriteReceipt(
        op_id="false_replace",
        helper="test",
        action="replace",
        bound_target_path=(("section", "1"),),
        landed_primary_path=(("section", "1"),),
        replaced_paths=((("section", "1"),),),
    )

    audit = build_observed_write_audit(before, after, receipt)

    assert audit.audit_status == "violation"
    assert audit.observed_changed_paths == ()
    assert audit.receipt_declared_paths == ((("section", "1"),),)
    assert audit.undeclared_paths == ()
    assert audit.unobserved_declared_paths == ((("section", "1"),),)


def test_observed_write_audit_flags_observed_write_outside_receipt() -> None:
    before = _body(_section("1", "old"), _section("2", "old"))
    after = _body(_section("1", "old"), _section("2", "new"))
    receipt = WriteReceipt(
        op_id="misdeclared_replace",
        helper="test",
        action="replace",
        bound_target_path=(("section", "1"),),
        landed_primary_path=(("section", "1"),),
        replaced_paths=((("section", "1"),),),
    )

    audit = build_observed_write_audit(before, after, receipt)

    assert audit.audit_status == "violation"
    assert audit.observed_changed_paths == ((("section", "2"),),)
    assert audit.undeclared_paths == ((("section", "2"),),)
    assert audit.unobserved_declared_paths == ((("section", "1"),),)


def test_observed_write_audit_validates_qualified_rule_ids() -> None:
    with pytest.raises(ValueError, match="qualified requires matched_rule_ids"):
        ObservedWriteAudit(
            op_id="op",
            observed_changed_paths=(),
            receipt_declared_paths=(),
            undeclared_paths=(),
            unobserved_declared_paths=(),
            audit_status="qualified",
        )


def test_apply_seam_carries_recovery_source_and_observed_write_evidence() -> None:
    before = IRNode(kind=IRNodeKind.BODY)
    anchor = SourceAnchor(
        source_artifact_id="test/source",
        byte_offset=4,
        byte_len=12,
        quote_hash="sha256:" + "c" * 64,
    )
    op = LegalOperation(
        op_id="recovered-insert",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="2", text="Inserted."),
        source=OperationSource(statute_id="test/source", source_anchor=anchor),
    )

    def materialize(state: IRNode, typed_op: LegalOperation) -> MaterializeResult[IRNode]:
        assert typed_op.payload is not None
        return MaterializeResult(
            new_state=tree_ops.insert_sorted(
                state,
                (),
                typed_op.payload,
                sort_key_fn=lambda label: (0, label or "", 0),
            ),
            declared_recovery_prefixes=((),),
            declared_recovery_rule_ids=("test_replace_absent_insert",),
            executed_action=StructuralAction.INSERT,
        )

    result = apply_op(
        before,
        op,
        provenance=op.source,
        profile=ApplyProfile(
            jurisdiction="test",
            materializer=materialize,
            boundary_mode="off",
            emit_coverage=False,
            occupancy_resolver=lambda _op, _before, _after: OccupancyClass.ABSENT,
            occupancy_mode="block",
            receipt_audit_mode="observe",
            receipt_footprint_mode="observed",
        ),
        source_statute="test/base",
    )

    assert result.applied is True
    assert result.write_receipt is not None
    receipt = result.write_receipt
    assert receipt.action == "insert"
    assert receipt.created_paths == ((),)
    assert receipt.recovery_rule_ids == ("test_replace_absent_insert",)
    assert receipt.source_anchor == anchor
    assert set(receipt.pre_hashes) == {""}
    assert set(receipt.post_hashes) == {""}
    assert receipt.pre_hashes[""] != receipt.post_hashes[""]

    assert result.observed_write_audit is not None
    audit = result.observed_write_audit
    assert audit.op_id == op.op_id
    assert audit.receipt_declared_paths == receipt.declared_footprint
    assert audit.audit_status == "clean"
    assert audit.matched_rule_ids == ()
    assert not any(
        isinstance(finding, Finding)
        and finding.kind == OCCUPANCY_TRANSITION_BLOCKED_FINDING_CODE
        for finding in result.findings
    )


def _chapter(label: str, *children: IRNode) -> IRNode:
    return IRNode(kind=IRNodeKind.CHAPTER, label=label, children=children)


def _cross_container_renumber_profile(
    materialize,
) -> ApplyProfile[IRNode]:
    return ApplyProfile(
        jurisdiction="test",
        materializer=materialize,
        boundary_mode="off",
        emit_coverage=False,
        receipt_audit_mode="block",
        receipt_footprint_mode="observed",
        renumber_migration_rule_ids=("test_renumber_relabel",),
    )


def test_recovery_removed_paths_declare_collateral_outside_the_renumber_legs() -> None:
    """A named recovery that clears an occupied renumber destination living in
    a DIFFERENT container declares that removal on the receipt.

    This is the W-52 corpus defect in miniature (``no/lov/2004-12-17-99``
    op ``no/lovtid/2012-05-25-29:24``): the occupant of label ``9`` lives under
    chapter ``A`` while the relabelled node lands under chapter ``B``, so
    NEITHER renumber leg covers the occupant's path. Without
    ``recovery_removed_paths`` the receipt declares only the legs, the
    independent before/after audit reads chapter ``A``'s mutation as an
    ``undeclared`` escape, and the write audits as ``violation`` even though
    a catalogued recovery rule authored it.
    """
    occupant_path = (("chapter", "A"), ("section", "9"))
    source_path = (("chapter", "B"), ("section", "2"))
    landed_path = (("chapter", "B"), ("section", "9"))
    before = _body(
        _chapter("A", _section("9", "occupant")),
        _chapter("B", _section("2", "moving")),
    )
    op = LegalOperation(
        op_id="renumber-into-occupied-other-chapter",
        sequence=1,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=source_path),
        destination=LegalAddress(path=(("section", "9"),)),
    )

    def materialize(state: IRNode, _op: LegalOperation) -> MaterializeResult[IRNode]:
        cleared = tree_ops.remove_at(state, occupant_path)
        lifted = tree_ops.remove_at(cleared, source_path)
        moved = tree_ops.insert_sorted(
            lifted,
            (("chapter", "B"),),
            _section("9", "moving"),
            sort_key_fn=lambda label: (0, label or "", 0),
        )
        return MaterializeResult(
            new_state=moved,
            declared_recovery_rule_ids=("test_renumber_occupied_destination_removed",),
            landed_primary_path=landed_path,
            renumbered_paths=((source_path, landed_path),),
            recovery_removed_paths=(occupant_path,),
        )

    result = apply_op(
        before,
        op,
        provenance=None,
        profile=_cross_container_renumber_profile(materialize),
    )

    assert result.write_receipt is not None
    receipt = result.write_receipt
    assert receipt.action == "renumber"
    assert receipt.renumbered_paths == ((source_path, landed_path),)
    # The collateral removal is declared under ``removed_paths`` — the receipt
    # category that already means "this path's content is gone".
    assert receipt.removed_paths == (occupant_path,)
    assert occupant_path in receipt.declared_footprint
    # The occupant's subtree is hashed at the write: present before, absent after.
    occupant_key = "chapter:A/section:9"
    assert receipt.pre_hashes[occupant_key] != ""
    assert receipt.post_hashes[occupant_key] == ""

    assert result.observed_write_audit is not None
    audit = result.observed_write_audit
    assert audit.undeclared_paths == ()
    # Not ``clean``: the observed diff is container-granular while the receipt
    # declares leaf paths. ``qualified`` is the correct verdict — a named rule
    # stands behind every declared leg.
    assert audit.audit_status == "qualified"
    assert "test_renumber_occupied_destination_removed" in audit.matched_rule_ids
    assert not any(
        isinstance(finding, Finding)
        and finding.kind == WRITE_RECEIPT_AUDIT_VIOLATION_FINDING_CODE
        for finding in result.findings
    )


def test_recovery_removed_paths_do_not_duplicate_an_already_declared_leg() -> None:
    """When the occupant stood exactly at the renumber's destination leg, that
    leg already declares the path, so the receipt is left untouched.

    This is what keeps the change inert for every same-container occupied
    destination in the corpus (7 of the 10 Norway firings): ``removed_paths``
    stays empty and the receipt is byte-identical to the pre-change one.
    """
    source_path = (("section", "2"),)
    destination_path = (("section", "9"),)
    before = _body(_section("2", "moving"), _section("9", "occupant"))
    op = LegalOperation(
        op_id="renumber-into-occupied-sibling",
        sequence=1,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=source_path),
        destination=LegalAddress(path=destination_path),
    )

    def materialize(state: IRNode, _op: LegalOperation) -> MaterializeResult[IRNode]:
        cleared = tree_ops.remove_at(state, destination_path)
        lifted = tree_ops.remove_at(cleared, source_path)
        moved = tree_ops.insert_sorted(
            lifted,
            (),
            _section("9", "moving"),
            sort_key_fn=lambda label: (0, label or "", 0),
        )
        return MaterializeResult(
            new_state=moved,
            declared_recovery_rule_ids=("test_renumber_occupied_destination_removed",),
            landed_primary_path=destination_path,
            renumbered_paths=((source_path, destination_path),),
            recovery_removed_paths=(destination_path,),
        )

    result = apply_op(
        before,
        op,
        provenance=None,
        profile=_cross_container_renumber_profile(materialize),
    )

    assert result.write_receipt is not None
    assert result.write_receipt.removed_paths == ()
    assert result.write_receipt.declared_footprint == (source_path, destination_path)
    assert result.observed_write_audit is not None
    assert result.observed_write_audit.undeclared_paths == ()


def test_materialize_result_rejects_unowned_recovery_removed_paths() -> None:
    """``recovery_removed_paths`` is not a free licence to declare collateral:
    without a named recovery rule owning the write it is rejected at the
    carrier boundary, so a producer can never silence the audit by declaring
    an unexplained removal.
    """
    with pytest.raises(ValueError, match="requires a named recovery rule"):
        MaterializeResult(
            new_state=IRNode(kind=IRNodeKind.BODY),
            recovery_removed_paths=((("section", "9"),),),
        )


def test_materialize_result_rejects_unowned_or_untyped_executed_action() -> None:
    with pytest.raises(ValueError, match="requires a named recovery rule"):
        MaterializeResult(
            new_state=IRNode(kind=IRNodeKind.BODY),
            executed_action=StructuralAction.INSERT,
        )
    with pytest.raises(TypeError, match="must be StructuralAction"):
        MaterializeResult(
            new_state=IRNode(kind=IRNodeKind.BODY),
            declared_recovery_rule_ids=("test_rule",),
            executed_action=cast(StructuralAction, "insert"),
        )


def test_apply_seam_uses_explicit_provenance_for_receipt_anchor() -> None:
    before = IRNode(kind=IRNodeKind.BODY)
    op_anchor = SourceAnchor("op/source", 1, 2, "sha256:" + "a" * 64)
    explicit_anchor = SourceAnchor("authoritative/source", 3, 4, "sha256:" + "b" * 64)
    op = LegalOperation(
        op_id="explicit-provenance",
        sequence=1,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=(("section", "1"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="1", text="New."),
        source=OperationSource(statute_id="op/source", source_anchor=op_anchor),
    )

    def materialize(state: IRNode, typed_op: LegalOperation) -> MaterializeResult[IRNode]:
        assert typed_op.payload is not None
        return MaterializeResult(
            new_state=tree_ops.insert_sorted(
                state,
                (),
                typed_op.payload,
                sort_key_fn=lambda label: (0, label or "", 0),
            )
        )

    result = apply_op(
        before,
        op,
        provenance=OperationSource(
            statute_id="authoritative/source",
            source_anchor=explicit_anchor,
        ),
        profile=ApplyProfile(
            jurisdiction="test",
            materializer=materialize,
            boundary_mode="off",
            emit_coverage=False,
        ),
    )

    assert result.write_receipt is not None
    assert result.write_receipt.source_anchor == explicit_anchor


def test_apply_seam_blocks_observed_write_audit_violation() -> None:
    before = IRNode(
        kind=IRNodeKind.BODY,
        children=(IRNode(kind=IRNodeKind.SECTION, label="9", text="Old."),),
    )
    op = LegalOperation(
        op_id="misdirected-renumber",
        sequence=1,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=(("section", "2"),)),
        destination=LegalAddress(path=(("section", "3"),)),
    )

    result = apply_op(
        before,
        op,
        provenance=None,
        profile=ApplyProfile(
            jurisdiction="test",
            materializer=lambda state, _op: MaterializeResult(
                new_state=tree_ops.replace_at(
                    state,
                    (("section", "9"),),
                    IRNode(kind=IRNodeKind.SECTION, label="9", text="Wrong."),
                )
            ),
            boundary_mode="off",
            receipt_audit_mode="block",
            receipt_footprint_mode="observed",
            emit_coverage=False,
            renumber_migration_rule_ids=("test_renumber",),
        ),
    )

    assert result.observed_write_audit is not None
    assert result.observed_write_audit.audit_status == "violation"
    assert any(
        isinstance(finding, Finding)
        and finding.kind == WRITE_RECEIPT_AUDIT_VIOLATION_FINDING_CODE
        and finding.blocking
        for finding in result.findings
    )


def test_receipt_hashes_exact_changed_path_when_labels_repeat() -> None:
    before = IRNode(
        kind=IRNodeKind.BODY,
        children=(
            IRNode(
                kind=IRNodeKind.CHAPTER,
                label="1",
                children=(IRNode(kind=IRNodeKind.SECTION, label="1", text="First."),),
            ),
            IRNode(
                kind=IRNodeKind.CHAPTER,
                label="2",
                children=(IRNode(kind=IRNodeKind.SECTION, label="1", text="Second."),),
            ),
        ),
    )
    landed = (("chapter", "2"), ("section", "1"))
    op = LegalOperation(
        op_id="duplicate-label-scoped-write",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "1"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="1", text="Changed second."),
    )

    def materialize(state: IRNode, typed_op: LegalOperation) -> MaterializeResult[IRNode]:
        assert typed_op.payload is not None
        return MaterializeResult(
            new_state=tree_ops.replace_at(state, landed, typed_op.payload),
            declared_recovery_rule_ids=("test_scoped_binding",),
            landed_primary_path=landed,
        )

    result = apply_op(
        before,
        op,
        provenance=None,
        profile=ApplyProfile(
            jurisdiction="test",
            materializer=materialize,
            boundary_mode="off",
            emit_coverage=False,
        ),
    )

    assert result.write_receipt is not None
    receipt = result.write_receipt
    assert set(receipt.pre_hashes) == {"chapter:2/section:1"}
    assert set(receipt.post_hashes) == {"chapter:2/section:1"}
    assert receipt.pre_hashes["chapter:2/section:1"] != receipt.post_hashes[
        "chapter:2/section:1"
    ]
