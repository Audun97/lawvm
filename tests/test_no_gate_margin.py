"""W-63: the gate's margin — the apply-plane typed conjuncts are load-bearing.

W-60's proposer–verifier spike ran a MUTANT CONTROL arm: take a proposal that
passed the full gate, mutate it into structurally plausible false law, and
require the gate to reject every mutant. Two mutants exposed that the gate's
divergence-based conjuncts (``G1`` divergence count closes / strictly reduces,
``G2`` zero new divergence rows, ``G4`` no ``base_ids`` movement) do NOT carry
the margin on their own. This module pins that property with both mutants
reproduced as self-contained fixtures.

WHY FIXTURES AND NOT THE CORPUS. The mutants live in ``.tmp/w60/proposals/``
(gitignored) and their corpus coordinates are pinned to the 2026-07-10 archive
snapshot — which has already moved once under a landed finding (W-55: the
2026-07-31 refresh put the live oracle ahead of a frozen anchor window and
convicted a correct replay). What is durable is the MECHANISM, so each mutant
is rebuilt here as a minimal inline op stream in the unit-fixture style of
``tests/test_no_renumber_migration.py``, and the divergence half is scored with
the SAME production comparator ``verify_no_against_current`` uses
(``ingest_consolidated`` + ``verify_consistency`` under NO's text projection
and normalizer), so neither half of the property is asserted by narration.

THE TWO MECHANISMS (each measured at W-63's base, not inherited from W-60):

* ``D2_m3`` — a wrong-slot REPLACE cascade (``2015-06-19-79`` →
  ``2011-06-24-39``, every ledd-suffixed target shifted one ledd later while
  the payload labels stayed put). Under production polarity the apply plane
  RAISES on a duplicate-label tree invariant, and
  :func:`~lawvm.norway.verify.verify_no_against_current` short-circuits on
  ``replay.error`` BEFORE it compares anything — so the mutant's divergence
  evidence is ``0 divergences / 0 rows opened``, the best score obtainable and
  strictly better than the untouched baseline's. The divergence plane is not
  merely blind here, it is INVERTED: the apply-plane failure MANUFACTURES the
  number a divergence-only reader treats as success. Measured on the corpus at
  W-63's base: baseline 5 divergences → mutant 0, 5 rows closed, 0 opened, no
  ``base_ids`` movement; with the invariant downgraded to a non-blocking record
  the false law lands and scores 1 divergence with 1 row OPENED — i.e. the
  full conjunct set still catches the landed law, and it is the error
  short-circuit alone that produces the perfect score.

* ``D4_m3`` — a wrong-address INSERT (``2020-12-18-157`` → ``2010-06-04-21``,
  ``§ 10-9 nytt fjerde ledd`` retargeted to a non-existent fifth ledd). The op
  is refused-or-rewritten entirely on the apply plane: pre-W-63 the
  ``(INSERT, occupied direct child)`` cell silently rewrote the write onto
  ``chapter:10/section:10-9/subsection:4`` — an address the op never named,
  matched only by payload ``(kind, label)`` under an INFERRED parent. Measured
  at W-63's base, that overwrite was CONTENT-IDENTICAL (``replay_noop`` fired
  on the same op) and the replayed statute came out byte-identical to the
  accepted control's (``8240bd16e2d11247`` for both) — so every divergence
  conjunct passed, correctly, and the ONLY trace of the wrong-address write
  was the typed receipt. That is the sharp form of the property: two different
  op streams, identical divergence evidence, and the difference visible only on
  the apply plane. Where the occupant's content differs, the same cell destroys
  in-force text with the same divergence-plane silence (W-54 observed exactly
  that under its ``refuse`` policy A/B, overwriting tvisteloven § 24-8's third
  ledd).

Both fixtures assert BOTH halves: (a) the divergence-based evidence alone would
accept, naming which conjuncts pass; (b) the apply-plane typed conjunct fires
and blocks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lawvm.core.ir import IRNode, IRStatute, LegalAddress, LegalOperation, OperationSource
from lawvm.core.semantic_types import IRNodeKind, StructuralAction
from lawvm.core.timeline_consistency import ingest_consolidated, verify_consistency
from lawvm.norway.grafter import apply_no_ops, apply_no_ops_conserved
from lawvm.norway.replay import NOReplayResult
from lawvm.norway.verify import (
    irnode_to_no_comparison_text,
    normalize_no_comparison_text,
    verify_no_against_current,
)
from lawvm.replay_adjudication import CompileAdjudication

_AS_OF = "2026-07-10"
_BASE_ID = "no/lov/2011-06-24-39"
_SOURCE_ID = "no/lovtid/2015-06-19-79"


# --------------------------------------------------------------------------
# The divergence plane, scored exactly the way the gate scores it.
# --------------------------------------------------------------------------


def _divergence_rows(replayed: IRStatute | None, consolidated: IRStatute) -> tuple[str, ...]:
    """The gate's divergence evidence for one replay outcome.

    Mirrors :func:`lawvm.norway.verify.verify_no_against_current`'s contract,
    including its short-circuit: when the apply plane raised there is no
    replayed statute, the function returns BEFORE comparing anything, and the
    resulting ``divergence_count`` is 0. ``None`` here stands for that outcome;
    :func:`test_gate_margin_zero_divergence_count_is_manufactured_by_an_apply_plane_failure`
    pins the short-circuit against the real production function so this mirror
    is not a fiction.
    """
    if replayed is None:
        return ()
    divergences = verify_consistency(
        ingest_consolidated(replayed, as_of=_AS_OF),
        ingest_consolidated(consolidated, as_of=_AS_OF),
        as_of=_AS_OF,
        irnode_to_text=irnode_to_no_comparison_text,
        text_normalizer=normalize_no_comparison_text,
        missing_equals_empty=True,
    )
    return tuple(
        sorted(
            f"{d.divergence_type}|" + "/".join(f"{k}:{lbl}" for k, lbl in d.address.path)
            for d in divergences
        )
    )


def _statute(title: str, *sections: IRNode) -> IRStatute:
    return IRStatute(
        statute_id=_BASE_ID,
        title=title,
        body=IRNode(kind=IRNodeKind.BODY, children=tuple(sections)),
    )


def _section(label: str, *children: IRNode) -> IRNode:
    return IRNode(kind=IRNodeKind.SECTION, label=label, children=tuple(children))


def _ledd(label: str, text: str) -> IRNode:
    return IRNode(kind=IRNodeKind.SUBSECTION, label=label, text=text)


def _op(
    op_id: str,
    sequence: int,
    action: StructuralAction,
    target: tuple[tuple[str, str], ...],
    payload: IRNode | None = None,
) -> LegalOperation:
    return LegalOperation(
        op_id=op_id,
        sequence=sequence,
        action=action,
        target=LegalAddress(path=target),
        payload=payload,
        source=OperationSource(
            statute_id=_SOURCE_ID,
            enacted="2015-06-19",
            effective="2016-01-01",
        ),
    )


def _labels_and_texts(section: IRNode) -> list[tuple[str | None, str]]:
    return [(child.label, child.text) for child in section.children]


# --------------------------------------------------------------------------
# The short-circuit that makes a zero divergence count uninterpretable alone.
# --------------------------------------------------------------------------


def test_gate_margin_zero_divergence_count_is_manufactured_by_an_apply_plane_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed apply yields the BEST divergence score, not the worst.

    ``verify_no_against_current`` returns as soon as ``replay.error`` is set,
    before any consolidated text is loaded or compared. Every divergence-plane
    field therefore reads as a perfect close: ``divergence_count == 0``,
    ``unexplained_divergence_count == 0``, no rows. An acceptance lane that
    scores a candidate on ``divergence_count`` alone (W-60's ``G1_closes``)
    reads an apply-plane CRASH as the strongest possible evidence of
    correctness. The only field that distinguishes the two is
    ``replay_status`` / ``error`` — i.e. an apply-plane conjunct.
    """
    errored = NOReplayResult(
        base_id=_BASE_ID,
        as_of=_AS_OF,
        replayed=None,
        error=(
            "Failed to apply ops: Norway replay invariant violation after replace "
            "(('section', '8'), ('subsection', '2')) from no/lovtid/2015-06-19-79: "
            "body/chapter:2/section:8: duplicate subsection:1 (2 times)"
        ),
    )
    monkeypatch.setattr("lawvm.norway.verify.replay_no_to_pit", lambda *a, **k: errored)
    monkeypatch.setattr(
        "lawvm.norway.verify.build_no_amendment_index",
        lambda *a, **k: _EmptyIndex(),
    )

    result = verify_no_against_current(_BASE_ID, as_of=_AS_OF, data_dir=tmp_path)

    assert result.error == errored.error
    assert str(result.replay_status) == "error"
    # The divergence plane's entire evidence surface, on false law:
    assert result.divergence_count == 0
    assert result.unexplained_divergence_count == 0
    assert not result.divergences
    assert not result.divergence_counts


class _EmptyIndex:
    """Minimal stand-in for ``NOAmendmentIndex`` — the replay is monkeypatched."""

    def entries_for_base(self, base_id: str) -> list[object]:
        return []


# --------------------------------------------------------------------------
# D2_m3 — the wrong-slot REPLACE cascade.
# --------------------------------------------------------------------------


def _d2_base() -> IRStatute:
    return _statute(
        "Lov om elsertifikater (D2 fixture)",
        _section(
            "8",
            _ledd("1", "Gammel fyrste ledd."),
            _ledd("2", "Gammel andre ledd."),
            _ledd("3", "Gammel tredje ledd."),
            _ledd("4", "Gammel fjerde ledd."),
            _ledd("5", "Gammel femte ledd."),
        ),
    )


def _d2_consolidated() -> IRStatute:
    """The true law after ``§ 8 fyrste til tredje ledd skal lyde``."""
    return _statute(
        "Lov om elsertifikater (D2 fixture)",
        _section(
            "8",
            _ledd("1", "Ny fyrste ledd."),
            _ledd("2", "Ny andre ledd."),
            _ledd("3", "Ny tredje ledd."),
            _ledd("4", "Gammel fjerde ledd."),
            _ledd("5", "Gammel femte ledd."),
        ),
    )


def _d2_ops(*, shift: int) -> list[LegalOperation]:
    """The accepted control (``shift=0``) and the ``m3`` mutant (``shift=1``).

    ``m3`` is W-60's mutation family "target one ledd later": every
    ledd-suffixed target moves down one slot while the payload labels — which
    the proposer copied from the amendment text — stay put.
    """
    return [
        _op(
            f"d2-{index}",
            index,
            StructuralAction.REPLACE,
            (("section", "8"), ("subsection", str(index + shift))),
            _ledd(str(index), text),
        )
        for index, text in ((1, "Ny fyrste ledd."), (2, "Ny andre ledd."), (3, "Ny tredje ledd."))
    ]


def test_gate_margin_d2_wrong_slot_replace_is_caught_only_by_the_tree_invariant() -> None:
    """D2_m3: perfect divergence evidence, false law, one apply-plane conjunct.

    Half (a) — the divergence-based evidence alone would ACCEPT. Under
    production polarity the mutant's evidence is 0 divergences and 0 rows
    opened against a nonzero baseline, so ``G1_reduces`` (strictly fewer),
    ``G1_closes`` (reaches zero), ``G2_no_new_rows`` (nothing opened) and
    ``G4`` (no binding movement — the op set is unchanged in size and source)
    all pass, and the mutant scores IDENTICALLY to the accepted control. The
    corpus run at W-63's base reproduces this: 5 → 0 divergences, 5 rows
    closed, 0 opened.

    Half (b) — the apply-plane conjunct fires and BLOCKS. The first mutated op
    writes a node labelled ``1`` over ``subsection:2``, leaving two
    ``subsection:1`` siblings; ``replay_tree_invariant_violation`` is recorded
    and the strict apply raises, so nothing is accepted.

    The counterfactual pins that the invariant is the load-bearing part: with
    ``strict_invariants=False`` the false law LANDS (duplicate ``1``, the
    fourth ledd destroyed) and only then does the divergence plane see it.
    """
    base, consolidated = _d2_base(), _d2_consolidated()

    # --- calibration: the comparator is live, and the control is correct. ---
    baseline_rows = _divergence_rows(base, consolidated)
    # Three changed ledd plus the section-level rollup row.
    assert len(baseline_rows) == 4, baseline_rows

    control_adjudications: list[CompileAdjudication] = []
    control = apply_no_ops(base, _d2_ops(shift=0), adjudications_out=control_adjudications)
    assert _divergence_rows(control, consolidated) == ()
    assert [a.kind for a in control_adjudications] == []

    # --- half (b): the apply plane raises on the mutant. --------------------
    mutant_adjudications: list[CompileAdjudication] = []
    with pytest.raises(ValueError, match=r"duplicate subsection:1"):
        apply_no_ops_conserved(
            base,
            _d2_ops(shift=1),
            adjudications_out=mutant_adjudications,
            strict_invariants=True,
        )
    invariant_records = [
        a for a in mutant_adjudications if a.kind == "replay_tree_invariant_violation"
    ]
    assert len(invariant_records) == 1
    assert invariant_records[0].blocking is True
    assert "duplicate subsection:1" in invariant_records[0].detail["violations"]

    # --- half (a): the divergence evidence for that same run. ---------------
    # The apply raised, so there is no replayed statute; verify short-circuits
    # and the mutant's divergence evidence is the empty set — strictly better
    # than the baseline's rows, and equal to the accepted control's.
    mutant_rows = _divergence_rows(None, consolidated)
    assert mutant_rows == ()
    assert len(mutant_rows) < len(baseline_rows)          # G1_reduces
    assert mutant_rows == ()                              # G1_closes
    assert set(mutant_rows) - set(baseline_rows) == set()  # G2_no_new_rows
    assert mutant_rows == _divergence_rows(control, consolidated)

    # --- counterfactual: downgrade the invariant and the false law lands. ---
    downgraded: list[CompileAdjudication] = []
    landed = apply_no_ops(
        base,
        _d2_ops(shift=1),
        adjudications_out=downgraded,
        strict_invariants=False,
    )
    assert _labels_and_texts(landed.body.children[0]) == [
        ("1", "Gammel fyrste ledd."),   # never overwritten — the mutant missed it
        ("1", "Ny fyrste ledd."),       # duplicate label
        ("2", "Ny andre ledd."),
        ("3", "Ny tredje ledd."),
        ("5", "Gammel femte ledd."),    # the fourth ledd was destroyed
    ]
    assert any(a.kind == "replay_tree_invariant_violation" for a in downgraded)
    landed_rows = _divergence_rows(landed, consolidated)
    assert set(landed_rows) - set(baseline_rows), (
        "the landed false law must open at least one row the baseline did not "
        "have — otherwise the divergence plane could not see it even with the "
        "invariant downgraded"
    )


# --------------------------------------------------------------------------
# D4_m3 — the wrong-address INSERT.
# --------------------------------------------------------------------------

_FORSKRIFT = "Departementet kan gi forskrift om utmåling av lovbrotsgebyr."
_MOMENTA = "Ved avgjerd av om gebyr skal påleggjast vert det lagt vekt på momenta i lista."


def _d4_base(*, fourth_ledd_text: str) -> IRStatute:
    return _statute(
        "Lov om fornybar energiproduksjon til havs (D4 fixture)",
        _section(
            "10-9",
            IRNode(kind=IRNodeKind.HEADING, label=None, text="(Lovbrotsgebyr)"),
            _ledd("1", "Departementet kan påleggje gebyr."),
            _ledd("2", "Ved avgjerd av om gebyr skal påleggjast."),
            _ledd("3", "Når eit brot på føresegn er gjort."),
            _ledd("4", fourth_ledd_text),
        ),
    )


def _d4_insert(*, ledd: str) -> LegalOperation:
    """``§ 10-9 nytt fjerde ledd skal lyde`` — control at ``4``, mutant at ``5``.

    The payload label is ``4`` in both: ``m3`` moves only the target address.
    """
    return _op(
        "d4-0",
        1,
        StructuralAction.INSERT,
        (("section", "10-9"), ("subsection", ledd)),
        _ledd("4", _FORSKRIFT),
    )


def test_gate_margin_d4_wrong_address_insert_is_invisible_to_the_divergence_plane() -> None:
    """D4_m3: identical divergence evidence, different provenance.

    This is the shape measured at W-63's base. The ledd-4 slot already carries
    the correct new text (in the corpus run, supplied by the parser op the
    mutation failed to supersede), so the pre-W-63 direct-child overwrite wrote
    the same bytes it destroyed and the replayed statute came out byte-identical
    to the accepted control's.

    Half (a) — every divergence conjunct passes, and passes CORRECTLY: the
    mutant's tree equals the control's tree equals the consolidation, so 0
    divergences, 0 rows opened, nothing to distinguish the two op streams. No
    amount of divergence evidence can separate them.

    Half (b) — the apply plane names what actually happened. W-63's refusal
    emits ``no_replay_insert_occupied_direct_child_refused`` (blocking) and
    REJECTS the op in the conserved partition, so the acceptance lane sees a
    typed signal that the op's commanded address never received its payload.
    """
    base = _d4_base(fourth_ledd_text=_FORSKRIFT)
    consolidated = _d4_base(fourth_ledd_text=_FORSKRIFT)

    # --- half (a): the divergence plane cannot tell the two runs apart. -----
    assert _divergence_rows(base, consolidated) == ()

    mutant_adjudications: list[CompileAdjudication] = []
    mutant = apply_no_ops_conserved(
        base,
        [_d4_insert(ledd="5")],
        adjudications_out=mutant_adjudications,
        strict_invariants=True,
    )
    assert _divergence_rows(mutant.statute, consolidated) == ()  # G1_closes / G2

    # --- half (b): the apply plane refuses and says why. --------------------
    refusals = [
        a
        for a in mutant_adjudications
        if a.kind == "no_replay_insert_occupied_direct_child_refused"
    ]
    assert len(refusals) == 1
    assert refusals[0].blocking is True
    assert refusals[0].detail["target"] == "section:10-9/subsection:5"
    assert refusals[0].detail["occupied_child_path"] == "section:10-9/subsection:4"
    assert refusals[0].detail["executed_action"] == "none"
    # Conserved partition: the op is REJECTED, never counted as applied.
    assert [op.op_id for op in mutant.filter_result.accepted_items] == []
    rejected = mutant.filter_result.rejected_items
    assert [item.item.op_id for item in rejected] == ["d4-0"]
    assert rejected[0].reason_code == "no_replay_insert_occupied_direct_child_refused"
    assert rejected[0].blocking is True
    # Nothing landed at the commanded address either.
    assert [child.label for child in mutant.statute.body.children[0].children] == [
        None,
        "1",
        "2",
        "3",
        "4",
    ]


def test_gate_margin_d4_wrong_address_insert_refusal_preserves_the_occupant() -> None:
    """The destructive variant of the same cell: the occupant must survive.

    Identical op, but the occupied ledd carries text the payload does not
    reproduce — the W-54 shape (its ``refuse`` policy A/B saw this cell
    overwrite tvisteloven § 24-8's third ledd). Pre-W-63 the in-force momenta
    list was destroyed and the commanded fifth ledd stayed empty. Post-W-63 the
    occupant is byte-identical and the op is refused.

    Half (a) is the same as the content-identical variant wherever the region
    was ALREADY divergent — destruction inside a divergent region opens no new
    row, so ``G2_no_new_rows`` still passes. Asserted here against a
    consolidation that does not match the ledd-4 occupant.
    """
    base = _d4_base(fourth_ledd_text=_MOMENTA)
    # The consolidation disagrees at ledd 4 for an unrelated reason (a lead the
    # lowering never emitted), so the region is already divergent at baseline.
    consolidated = _d4_base(fourth_ledd_text="Ei heilt anna fjerde ledd.")
    baseline_rows = _divergence_rows(base, consolidated)
    # The occupied ledd plus the section-level rollup row.
    assert len(baseline_rows) == 2, baseline_rows

    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops_conserved(
        base,
        [_d4_insert(ledd="5")],
        adjudications_out=adjudications,
        strict_invariants=True,
    )

    # Half (b): refused, and the occupant survives byte-identically.
    assert [a.kind for a in adjudications] == [
        "no_replay_insert_occupied_direct_child_refused"
    ]
    section = result.statute.body.children[0]
    assert _labels_and_texts(section) == [
        (None, "(Lovbrotsgebyr)"),
        ("1", "Departementet kan påleggje gebyr."),
        ("2", "Ved avgjerd av om gebyr skal påleggjast."),
        ("3", "Når eit brot på føresegn er gjort."),
        ("4", _MOMENTA),
    ]
    # Half (a): the refusal opens no divergence row the baseline did not have —
    # and neither did the destructive overwrite it replaced. The divergence
    # plane is silent about both outcomes; only the receipt separates them.
    assert set(_divergence_rows(result.statute, consolidated)) == set(baseline_rows)


def test_gate_margin_declared_insert_occupied_target_recovery_keeps_its_polarity() -> None:
    """Over-reach guard: W-63 flips ONLY the undeclared direct-child cell.

    Its sibling ``(INSERT, target_occupied)`` — the θ table's declared RECOVER
    row ``no_insert_occupied_target_replace``, the Lovdata "ny § 4 a skal lyde"
    over an existing slot that FABLE_UNIVERSAL_ALGEBRA §2.3 documents — fires
    194 times across 73 base laws in the 2026-07-10 corpus (W-63 census) and is
    load-bearing. It keeps its overwrite polarity. The discriminator is whether
    the op's OWN target address resolves: here it does.
    """
    base = _d4_base(fourth_ledd_text=_MOMENTA)
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(base, [_d4_insert(ledd="4")], adjudications_out=adjudications)

    assert [(a.kind, a.detail["rule_id"]) for a in adjudications] == [
        ("no_replay_insert_occupied_target_replaced", "no_insert_occupied_target_replace")
    ]
    assert _labels_and_texts(updated.body.children[0])[-1] == ("4", _FORSKRIFT)
