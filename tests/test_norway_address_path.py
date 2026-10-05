"""W-65: the address-path lead (``§ <label> <step>* <verb>``) in the unstructured lane.

Three planes are pinned here: the reader (what the grammar reads, declines and
refuses), the lowering through the production walk (payload proof, additivity,
the typed receipt), and the apply seam (strict resolution, no recovery).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lawvm.core.ir import IRNode, IRStatute, LegalAddress, LegalOperation, OperationSource
from lawvm.core.semantic_types import IRNodeKind, StructuralAction
from lawvm.norway.grafter import (
    NO_ADDRESS_PATH_PROVENANCE_TAG,
    NO_PARSE_ADDRESS_PATH_NOT_LOWERED,
    NO_REPLAY_ADDRESS_PATH_INSERT_OCCUPIED_TARGET_REFUSED,
    NO_REPLAY_ADDRESS_PATH_TARGET_REFUSED,
    _no_address_path_detail,
    _no_address_path_refusal,
    _no_lead_address_path,
    apply_no_ops,
    iter_no_document_change_ops,
)
from lawvm.norway.replay import replay_no_to_pit
from lawvm.norway.sources import iter_no_amendment_artifacts, load_no_amendment_bytes
from lawvm.replay_adjudication import CompileAdjudication

_BASE = "no/lov/1992-12-04-127"
_SOURCE = "no/lovtid/2000-01-14-5"


def _read(lead: str) -> tuple[str, str] | None:
    read = _no_lead_address_path(lead)
    return None if read is None else (_no_address_path_detail(read), read.verb)


@pytest.mark.parametrize(
    ("lead", "address", "verb"),
    [
        # The spaced letter suffix (W-32(c)), which the shipped ledd grammar cuts short.
        ("§ 28 a tredje ledd skal lyde:", "section:28a/subsection:3", "replace"),
        # Ordinals past ``tiende`` and in nynorsk.
        ("§ 2-2 ellevte ledd skal lyde:", "section:2-2/subsection:11", "replace"),
        ("§ 15-1 åttande ledd skal lyde:", "section:15-1/subsection:8", "replace"),
        # Steps in the order the lead writes them, at any depth.
        ("§ 53 nr. 2 første ledd skal lyde:", "section:53/item:2/subsection:1", "replace"),
        ("§ 12 nr. 1 annet punktum skal lyde:", "section:12/item:1/sentence:2", "replace"),
        (
            "§ 14-42 andre ledd bokstav a fjerde punktum skal lyde:",
            "section:14-42/subsection:2/item:a/sentence:4",
            "replace",
        ),
        ("§ 5 første ledd nr. 1 bokstav g oppheves.", "section:5/subsection:1/item:1/item:g", "repeal"),
        # Lists, ranges and the per-member newness marker.
        ("§ 282 annet til fjerde ledd skal lyde:", "section:282/subsection:2,3,4", "replace"),
        ("§ 27 b annet og nytt tredje ledd skal lyde:", "section:27b/subsection:2,+3", "replace"),
        ("§ 9 nytt sjuande til niande ledd skal lyde:", "section:9/subsection:+7,+8,+9", "replace"),
        ("§ 3-4 nr. 3 og nr. 4 skal lyde:", "section:3-4/item:3,4", "replace"),
        ("§ 5 første ledd bokstavene d og e oppheves.", "section:5/subsection:1/item:d,e", "repeal"),
        ("§ 1 første ledd bokstav e) oppheves.", "section:1/subsection:1/item:e", "repeal"),
        # The repeated-noun leaf list.
        (
            "§ 3 andre ledd tredje punktum og nytt fjerde punktum skal lyde:",
            "section:3/subsection:2/sentence:3,+4",
            "replace",
        ),
        # Repeal verbs, bokmål and nynorsk, and the section-level repeal.
        ("§ 16 blir oppheva.", "section:16", "repeal"),
        ("§ 4-17 skal opphevast.", "section:4-17", "repeal"),
        ("§ 3 annet ledd siste punktum oppheves.", "section:3/subsection:2/sentence:last", "repeal"),
        # Read, so the receipt can name them; never lowered.
        ("§ 5-9 overskriften skal lyde:", "section:5-9/heading", "replace"),
        ("§ 15-8 første ledd innledningen skal lyde:", "section:15-8/subsection:1/intro", "replace"),
    ],
)
def test_no_w65_reader_reads_the_corpus_shapes(lead: str, address: str, verb: str) -> None:
    assert _read(lead) == (address, verb)


@pytest.mark.parametrize(
    "lead",
    [
        # The whole-section production's lead; it fails there on payload, not grammar.
        "§ 7-4 skal lyde:",
        # Another family's lead: a renumber that also announces text.
        "§ 10-2 åttende ledd blir syvende ledd og skal lyde:",
        # Two addresses conjoined; this grammar reads one.
        "§ 73 første og annet ledd og tredje ledd første punktum skal lyde:",
        "§ 10-2 tredje ledd andre punktum og femte ledd blir oppheva.",
        "§ 27 første ledd tredje punktum og § 52 e femte ledd fjerde punktum oppheves.",
        # A token the grammar does not know anywhere in the middle.
        "§ 6-2 første ledd ny post C II 2 skal lyde:",
        "§ 3 (2) første ledd første punktum skal lyde:",
        "§ 39 nr. 1, første punktum skal lyde:",
        # A dangling separator or marker names nothing.
        "§ 5 første ledd og skal lyde:",
        "§ 5 nytt skal lyde:",
        # Inline payload after the colon, a section list, a non-lead.
        "§ 5 første ledd nr. 2 skal lyde: bebygd eiendom.",
        "§§ 112-114 oppheves.",
        "Lovens tittel skal lyde:",
        # A descending range.
        "§ 5 fjerde til annet ledd skal lyde:",
    ],
)
def test_no_w65_reader_declines_what_it_does_not_read_to_the_end(lead: str) -> None:
    assert _no_lead_address_path(lead) is None


@pytest.mark.parametrize(
    ("lead", "refusal"),
    [
        ("§ 5-9 overskriften skal lyde:", "step_not_lowerable:heading"),
        ("§ 15-8 første ledd innledningen skal lyde:", "step_not_lowerable:intro"),
        ("§ 19-3 nr. 8 annet avsnitt skal lyde:", "step_not_lowerable:avsnitt"),
        ("§ 5 første og annet ledd første punktum skal lyde:", "list_above_leaf"),
        ("§ 20 nytt annet ledd første punktum skal lyde:", "newness_above_leaf"),
        ("§ 5 siste ledd skal lyde:", "last_not_a_sentence"),
        ("§ 5 første og første ledd skal lyde:", "repeated_label"),
        ("§ 5 nytt annet ledd oppheves.", "repeal_of_new_provision"),
        ("§ 28 a tredje ledd skal lyde:", ""),
    ],
)
def test_no_w65_refusal_names_why_a_read_address_does_not_lower(lead: str, refusal: str) -> None:
    read = _no_lead_address_path(lead)
    assert read is not None
    assert _no_address_path_refusal(read) == refusal


def _amendment(members: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1992-12-04-127</li></ul></dd>
    <dd class="dateInForce">2000-01-20</dd>
    <main>
      <section data-name="kapI">
        <article class="legalP">I lov av 4. desember 1992 nr. 127 om kringkasting gjøres følgende endringer:</article>
{members}
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _lower(members: str) -> tuple[list[LegalOperation], list[CompileAdjudication]]:
    adjudications: list[CompileAdjudication] = []
    grouped = dict(iter_no_document_change_ops(_amendment(members), _SOURCE, adjudications_out=adjudications))
    return list(grouped.get(_BASE, [])), adjudications


def _shape(op: LegalOperation) -> tuple[str, tuple[tuple[str, str], ...], str | None]:
    return (
        str(getattr(op.action, "value", op.action)),
        op.target.path,
        None if op.payload is None else op.payload.text,
    )


def _tagged(ops: list[LegalOperation]) -> list[LegalOperation]:
    return [op for op in ops if NO_ADDRESS_PATH_PROVENANCE_TAG in (op.provenance_tags or ())]


def test_no_w65_lowers_each_leaf_kind_through_the_production_walk() -> None:
    ops, adjudications = _lower(
        """
        <article class="defaultP">§ 28 a tredje ledd skal lyde:</article>
        <article class="legalP">Nytt tredje ledd i tjueåtte a.</article>
        <article class="defaultP">§ 9 a annet og nytt tredje ledd skal lyde:</article>
        <article class="legalP">Annet ledd.</article>
        <article class="legalP">Tredje ledd.</article>
        <article class="defaultP">§ 2 nr. 2 skal lyde:</article>
        <article class="legalP">Nummer to.</article>
        <article class="defaultP">§ 12 nr. 1 annet og nytt tredje punktum skal lyde:</article>
        <article class="legalP">Annet punktum her. Tredje punktum her.</article>
        <article class="defaultP">§ 5 første ledd bokstavene d og e oppheves.</article>
        <article class="defaultP">§ 16 blir oppheva.</article>
        """
    )
    assert [_shape(op) for op in ops] == [
        ("replace", (("section", "28a"), ("subsection", "3")), "Nytt tredje ledd i tjueåtte a."),
        ("replace", (("section", "9a"), ("subsection", "2")), "Annet ledd."),
        ("insert", (("section", "9a"), ("subsection", "3")), "Tredje ledd."),
        ("replace", (("section", "2"), ("item", "2")), "Nummer to."),
        ("replace", (("section", "12"), ("item", "1"), ("sentence", "2")), "Annet punktum her."),
        ("insert", (("section", "12"), ("item", "1"), ("sentence", "3")), "Tredje punktum her."),
        # A repeal's legs run highest label first.
        ("repeal", (("section", "5"), ("subsection", "1"), ("item", "e")), None),
        ("repeal", (("section", "5"), ("subsection", "1"), ("item", "d")), None),
        ("repeal", (("section", "16"),), None),
    ]
    assert _tagged(ops) == ops
    assert not [a for a in adjudications if a.blocking]


def test_no_w65_is_additive_a_shipped_shape_keeps_its_shipped_production() -> None:
    """The walk position is the additivity proof: a lead a shipped reader lowers never reaches W-65."""
    ops, _adjudications = _lower(
        """
        <article class="defaultP">§ 5 første ledd skal lyde:</article>
        <article class="legalP">Første ledd.</article>
        <article class="defaultP">§ 6 første ledd annet punktum skal lyde:</article>
        <article class="legalP">Annet punktum.</article>
        <article class="defaultP">§ 7 oppheves.</article>
        """
    )
    assert [_shape(op)[:2] for op in ops] == [
        ("replace", (("section", "5"), ("subsection", "1"))),
        ("replace", (("section", "6"), ("subsection", "1"), ("sentence", "2"))),
        ("repeal", (("section", "7"),)),
    ]
    assert _tagged(ops) == []


def test_no_w65_a_repeal_consumes_no_payload_so_the_next_lead_is_still_read() -> None:
    """Also the silent drop this item found: the shipped ledd-repeal block matched a
    spaced label, resolved no ledd, and consumed the lead with neither op nor receipt."""
    ops, _adjudications = _lower(
        """
        <article class="defaultP">§ 28 a annet ledd oppheves.</article>
        <article class="legalP">§ 28 b tredje ledd oppheves.</article>
        """
    )
    assert [_shape(op)[:2] for op in ops] == [
        ("repeal", (("section", "28a"), ("subsection", "2"))),
        ("repeal", (("section", "28b"), ("subsection", "3"))),
    ]


@pytest.mark.parametrize(
    ("members", "refusal"),
    [
        ('<article class="defaultP">§ 28 a tredje ledd skal lyde:</article>', "payload_absent"),
        (
            '<article class="defaultP">§ 28 a tredje og fjerde ledd skal lyde:</article>'
            '<article class="legalP">Bare ett ledd.</article>',
            "payload_arity",
        ),
        (
            '<article class="defaultP">§ 28 a tredje ledd skal lyde:</article>'
            '<article class="futureLegalArticle" data-name="§28a"><article class="legalP">Ledd.</article></article>',
            "payload_not_text_articles",
        ),
        (
            '<article class="defaultP">§ 8-10 nr. 1 skal lyde:</article>'
            '<article class="numberedLegalP" data-numerator="1">1. Nummerert.</article>',
            "numbered_payload_for_item",
        ),
        (
            '<article class="defaultP">§ 8 nr. 2 bokstav b skal lyde:</article>'
            '<article class="legalP">Tekst<ul><li data-name="1">en</li></ul></article>',
            "payload_has_structure",
        ),
        (
            '<article class="defaultP">§ 12 nr. 1 annet punktum skal lyde:</article>'
            '<article class="legalP">Ett punktum. Og ett til.</article>',
            "payload_sentence_arity",
        ),
        ('<article class="defaultP">§ 5-9 ny overskrift skal lyde:</article>', "step_not_lowerable:heading"),
    ],
)
def test_no_w65_unproven_payload_refuses_the_whole_lead_with_a_typed_receipt(members: str, refusal: str) -> None:
    """Guard liveness: the refusal is reached through the production walk, and it embeds the clause."""
    ops, adjudications = _lower(members)
    assert ops == []
    receipts = [a for a in adjudications if a.kind == NO_PARSE_ADDRESS_PATH_NOT_LOWERED]
    assert len(receipts) == 1
    detail = receipts[0].detail or {}
    assert receipts[0].blocking
    assert detail["refusal"] == refusal
    assert detail["source_excerpt"].startswith("§ ")
    assert detail["base_id"] == _BASE
    # One receipt per lead: the generic fallback does not also fire.
    assert not [a for a in adjudications if a.kind == "no_parse_unstructured_lead_unmatched"]


def test_no_w65_lead_is_withdrawn_when_the_relabel_after_its_payload_did_not_lower() -> None:
    """The over-repeal this item found on its own blast, as a synthetic.

    ``no/lovtid/2016-12-16-93`` (finnmarksloven § 43): "… første til fjerde ledd
    skal lyde:" then "Nåværende andre, tredje og fjerde ledd blir nye femte,
    sjette og syvende ledd." The relabel refuses, and lowered alone the first
    half wrote the new text over three ledd the consolidation still prints.
    """
    ops, adjudications = _lower(
        """
        <article class="defaultP">§ 43 a første til tredje ledd skal lyde:</article>
        <article class="legalP">Nytt første.</article>
        <article class="legalP">Nytt andre.</article>
        <article class="legalP">Nytt tredje.</article>
        <article class="defaultP">Nåværende andre og tredje ledd blir nye fjerde og femte ledd, og blir stående.</article>
        """
    )
    assert ops == []
    withdrawn = [a for a in adjudications if a.kind == NO_PARSE_ADDRESS_PATH_NOT_LOWERED]
    assert len(withdrawn) == 1
    detail = withdrawn[0].detail or {}
    assert detail["refusal"] == "relabel_follows_unlowered"
    assert detail["source_excerpt"] == "§ 43 a første til tredje ledd skal lyde:"
    assert detail["follower"].startswith("Nåværende andre og tredje ledd blir")
    assert list(detail["withdrawn_targets"]) == [
        "section:43a/subsection:1",
        "section:43a/subsection:2",
        "section:43a/subsection:3",
    ]


def test_no_w65_lead_stands_when_the_relabel_lowers_or_the_follower_is_no_relabel() -> None:
    # The relabel lowers: its RENUMBER vacates the label, and the overlapping
    # REPLACE is promoted to an INSERT, which the apply seam refuses if occupied.
    ops, _adjudications = _lower(
        """
        <article class="defaultP">§ 43 a tredje ledd skal lyde:</article>
        <article class="legalP">Nytt tredje.</article>
        <article class="defaultP">Nåværende tredje ledd blir nytt fjerde ledd.</article>
        """
    )
    assert [_shape(op)[:2] for op in ops] == [
        ("insert", (("section", "43a"), ("subsection", "3"))),
        ("renumber", (("section", "43a"), ("subsection", "3"))),
    ]
    # A follower whose ``blir`` is statute prose behind a colon, or a nynorsk repeal.
    ops, adjudications = _lower(
        """
        <article class="defaultP">§ 19 nr. 5 annet punktum skal lyde:</article>
        <article class="legalP">Nytt punktum.</article>
        <article class="defaultP">§ 20 a tredje ledd skal lyde:</article>
        <article class="legalP">Blir hun på ny enke, gjelder første ledd.</article>
        <article class="defaultP">§ 21 a annet ledd blir oppheva.</article>
        """
    )
    assert [_shape(op)[:2] for op in ops] == [
        ("replace", (("section", "19"), ("item", "5"), ("sentence", "2"))),
        ("replace", (("section", "20a"), ("subsection", "3"))),
        ("repeal", (("section", "21a"), ("subsection", "2"))),
    ]
    assert not [a for a in adjudications if a.kind == NO_PARSE_ADDRESS_PATH_NOT_LOWERED]


def test_no_w65_repeal_then_shift_read_that_names_nothing_is_refused_not_dropped() -> None:
    """The second silent drop: a spaced label emptied every round-trip of the shipped
    repeal-then-shift production, which then consumed the lead with no op and no receipt."""
    lead = "§ 2-1 b femte ledd oppheves. Nåværende sjette til niende ledd blir femte til åttende ledd."
    ops, adjudications = _lower(f'<article class="defaultP">{lead}</article>')
    assert ops == []
    assert [(a.kind, (a.detail or {}).get("source_excerpt")) for a in adjudications] == [
        ("no_parse_unstructured_lead_unmatched", lead)
    ]


def _statute() -> IRStatute:
    """§ 9: two ledd, each with bokstav a/b. § 10: one ledd with nr. 1/2. § 11: one bare ledd."""

    def items(*labels: str) -> tuple[IRNode, ...]:
        return tuple(IRNode(kind=IRNodeKind.ITEM, label=label, text=f"punkt {label}") for label in labels)

    def ledd(label: str, text: str, *labels: str) -> IRNode:
        return IRNode(kind=IRNodeKind.SUBSECTION, label=label, text=text, children=items(*labels))

    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(kind=IRNodeKind.SECTION, label="9", children=(ledd("1", "", "a", "b"), ledd("2", "", "a", "b"))),
                IRNode(kind=IRNodeKind.SECTION, label="10", children=(ledd("1", "", "1", "2"),)),
                IRNode(kind=IRNodeKind.SECTION, label="11", children=(ledd("1", "Eneste ledd."),)),
            ),
        ),
    )


def _op(
    sequence: int,
    action: StructuralAction,
    path: tuple[tuple[str, str], ...],
    payload: IRNode | None = None,
    *,
    tagged: bool = True,
) -> LegalOperation:
    tags = ("base_act:no/lov/1999-01-01-1", "fallback:unstructured")
    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=action,
        target=LegalAddress(path=path),
        payload=payload,
        source=OperationSource(statute_id="no/lovtid/9999-01-01-1", raw_text="address path", title="x"),
        provenance_tags=(*tags, NO_ADDRESS_PATH_PROVENANCE_TAG) if tagged else tags,
        group_id=f"no/lovtid/9999-01-01-1:{sequence}",
    )


def _texts(statute: IRStatute) -> dict[str, str]:
    out: dict[str, str] = {}

    def walk(node: IRNode, prefix: str) -> None:
        for child in node.children:
            path = f"{prefix}/{getattr(child.kind, 'value', child.kind)}:{child.label}".lstrip("/")
            out[path] = child.text or ""
            walk(child, path)

    walk(statute.body, "")
    return out


def _apply(ops: list[LegalOperation]) -> tuple[dict[str, str], list[CompileAdjudication]]:
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(_statute(), ops, adjudications_out=adjudications)
    return _texts(result), adjudications


def _refusals(adjudications: list[CompileAdjudication]) -> list[tuple[str, str]]:
    return [
        (a.op_id.rsplit(":", 1)[1], str((a.detail or {}).get("refusal")))
        for a in adjudications
        if a.kind == NO_REPLAY_ADDRESS_PATH_TARGET_REFUSED
    ]


def test_no_w65_apply_lands_an_address_that_resolves_to_one_node() -> None:
    item = IRNode(kind=IRNodeKind.ITEM, label="b", text="ny b")
    texts, adjudications = _apply(
        [
            _op(1, StructuralAction.REPLACE, (("section", "9"), ("subsection", "2"), ("item", "b")), item),
            # The ledd-less item address resolves through § 10's ONE ledd.
            _op(2, StructuralAction.REPEAL, (("section", "10"), ("item", "2"))),
        ]
    )
    assert texts["section:9/subsection:2/item:b"] == "ny b"
    assert texts["section:9/subsection:1/item:b"] == "punkt b"
    assert "section:10/subsection:1/item:2" not in texts
    assert "section:10/subsection:1/item:1" in texts
    assert _refusals(adjudications) == []


def test_no_w65_apply_refuses_rather_than_guess_or_recover() -> None:
    """Every refusal leaves the tree byte-identical: over-retention is the safe wrong."""
    before = _texts(_statute())
    item = IRNode(kind=IRNodeKind.ITEM, label="a", text="FEIL")
    ledd = IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="FEIL")
    texts, adjudications = _apply(
        [
            # § 9 has two ledd, each with a bokstav a: first-match would pick ledd 1.
            _op(1, StructuralAction.REPLACE, (("section", "9"), ("item", "a")), item),
            _op(2, StructuralAction.REPEAL, (("section", "9"), ("item", "a"))),
            # An absent ledd is not inserted under cover of a REPLACE.
            _op(3, StructuralAction.REPLACE, (("section", "11"), ("subsection", "3")), ledd),
            # "nr. 2 første ledd" where nr. 2 carries no ledd.
            _op(4, StructuralAction.REPLACE, (("section", "10"), ("item", "2"), ("subsection", "1")), ledd),
            _op(5, StructuralAction.REPEAL, (("section", "12"),)),
        ]
    )
    assert texts == before
    # Sorted: the fold orders the legs itself.
    assert sorted(_refusals(adjudications)) == [
        ("1", "item_host_not_unique"),
        ("2", "item_host_not_unique"),
        ("3", "unresolved"),
        ("4", "unresolved"),
        ("5", "unresolved"),
    ]
    assert not [a for a in adjudications if a.kind == "no_replay_replace_recovered_by_insert"]


def test_no_w65_apply_refuses_an_insert_onto_an_occupied_label() -> None:
    before = _texts(_statute())
    ledd = IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="FEIL")
    texts, adjudications = _apply([_op(1, StructuralAction.INSERT, (("section", "11"), ("subsection", "1")), ledd)])
    assert texts == before
    assert [a.kind for a in adjudications if a.blocking] == [NO_REPLAY_ADDRESS_PATH_INSERT_OCCUPIED_TARGET_REFUSED]
    assert not [a for a in adjudications if a.kind == "no_replay_insert_occupied_target_replaced"]


def test_no_w65_apply_guard_is_keyed_on_the_tag_the_shipped_lane_is_untouched() -> None:
    """Negative: the same op without the tag keeps the shipped θ recovery."""
    ledd = IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Erstattet.")
    texts, adjudications = _apply(
        [_op(1, StructuralAction.INSERT, (("section", "11"), ("subsection", "1")), ledd, tagged=False)]
    )
    assert texts["section:11/subsection:1"] == "Erstattet."
    assert [a.kind for a in adjudications] == ["no_replay_insert_occupied_target_replaced"]


def test_no_w65_synthetic_marker_does_not_leak_into_addresses_or_text() -> None:
    ops, _adjudications = _lower(
        '<article class="defaultP">§ 3 annet ledd siste punktum oppheves.</article>'
        '<article class="defaultP">§ 9 nytt tredje ledd skal lyde:</article>'
        '<article class="legalP">Tredje ledd.</article>'
    )
    for op in ops:
        assert all("+" not in label and NO_ADDRESS_PATH_PROVENANCE_TAG not in label for _kind, label in op.target.path)
        assert op.payload is None or NO_ADDRESS_PATH_PROVENANCE_TAG not in (op.payload.text or "")


def _no_farchive_path() -> Path | None:
    root = os.environ.get("LAWVM_CANONICAL_DATA_ROOT")
    if root:
        candidate = Path(root) / "data" / "norway.farchive"
        if candidate.exists():
            return candidate
    fallback = Path(__file__).resolve().parent.parent / "data" / "norway.farchive"
    return fallback if fallback.exists() else None


_NO_FARCHIVE_PATH = _no_farchive_path()


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w65_corpus_witness_lowers_and_keeps_every_shipped_op() -> None:
    """``no/lovtid/2001-05-04-16``: "§ 28 a tredje ledd skal lyde:" into ``no/lov/1980-06-13-35``.

    The shipped ledd grammar read the label as ``28`` and the ordinal phrase as
    "a tredje", so the lead lowered nothing. Pinned structurally: the address,
    the tag, and that the act's other ops are the ones the shipped readers mint.
    """
    source_id = "no/lovtid/2001-05-04-16"
    html_bytes = load_no_amendment_bytes(source_id, _NO_FARCHIVE_PATH)
    assert html_bytes is not None
    adjudications: list[CompileAdjudication] = []
    grouped = dict(iter_no_document_change_ops(html_bytes, source_id, adjudications_out=adjudications))
    minted = _tagged(list(grouped["no/lov/1980-06-13-35"]))
    assert (("section", "28a"), ("subsection", "3")) in [op.target.path for op in minted]
    witness = next(op for op in minted if op.target.path == (("section", "28a"), ("subsection", "3")))
    assert witness.action is StructuralAction.REPLACE
    assert witness.source is not None and witness.source.raw_text == "§ 28 a tredje ledd skal lyde:"
    assert witness.payload is not None and (witness.payload.text or "").startswith("For den som har fått underretning")
    assert not [
        a
        for a in adjudications
        if a.kind == "no_parse_unstructured_lead_unmatched"
        and (a.detail or {}).get("source_excerpt") == "§ 28 a tredje ledd skal lyde:"
    ]


# The sentences W-65's repeals remove in the corpus replay, with their own text.
# W-66c pins its production's the same way and for the same reason: an address
# can stay right while the sentence splitter counts to a different sentence.
# Each row was adjudicated at entry. The lead, read off its ``defaultP`` node,
# names the section and the ordinal, and the ledd was printed as it stood just
# before the removal:
#   * ``2003-12-12-108`` § 4 tredje ledd held three sentences and the last went
#     ("§ 4 tredje ledd siste punktum oppheves.", `2006-12-15-83`);
#   * ``2005-06-17-67`` § 10-11 has one ledd of three sentences and the third
#     went ("§ 10-11 tredje punktum blir oppheva.", `2016-06-17-42`); § 16-20
#     første ledd held four and the last went (`2016-12-20-114`);
#   * ``2010-06-25-28`` § 4 ("§ 4 sjette punktum blir oppheva.", `2022-12-20-100`)
#     and ``2017-06-16-65`` § 25 første ledd ("… tredje og fjerde punktum blir
#     oppheva.", `2020-12-04-137`) each close divergence rows against the
#     published consolidation and open none.
_W65_CORPUS_SENTENCE_DESTRUCTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "no/lov/2003-12-12-108",
        "section:4/subsection:3/sentence:last",
        "Kompensasjon ytes også for anskaffelser til kommunale havner på virksomhetsområder hvor det oppkreves havneavgifter.",
    ),
    (
        "no/lov/2005-06-17-67",
        "section:10-11/sentence:3",
        "Lønnstrekk skal også betales når arbeidsgiver opphører med virksomhet på Svalbard eller aktiviteten der på annen måte opphører.",
    ),
    (
        "no/lov/2005-06-17-67",
        "section:16-20/subsection:1/sentence:last",
        "Når selskap eller innlåner er pålagt trekkplikt etter § 5-4 annet ledd gjelder ikke ansvarsbegrensningen i tredje punktum.",
    ),
    (
        "no/lov/2010-06-25-28",
        "section:4/sentence:6",
        "Ved regulering av forsørgingstillegg legges reguleringsfaktoren etter folketrygdloven § 19-14 tredje ledd til grunn.",
    ),
    (
        "no/lov/2017-06-16-65",
        "section:25/subsection:1/sentence:3",
        "En seksjonseier kan med samtykke fra styret anlegge ladepunkt for elbil og ladbare hybrider i tilknytning til en parkeringsplass seksjonen disponerer, eller andre steder som styret anviser.",
    ),
    (
        "no/lov/2017-06-16-65",
        "section:25/subsection:1/sentence:4",
        "Styret kan bare nekte å samtykke dersom det foreligger en saklig grunn.",
    ),
)


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w65_corpus_sentence_destructions_are_pinned_by_content() -> None:
    """Do NOT relax this pin. For each row that enters, read the lead off its node,
    confirm it names that section and that ordinal, and print the ledd as it stood
    before the removal; for each that leaves, say in the ledger what stopped it."""
    from lawvm.core import tree_ops
    from tests.norway_index_cache import cached_no_amendment_index

    assert _NO_FARCHIVE_PATH is not None
    minted: dict[str, tuple[str, str]] = {}
    for artifact in iter_no_amendment_artifacts(_NO_FARCHIVE_PATH):
        for base_id, ops in iter_no_document_change_ops(artifact.payload, artifact.logical_id):
            for op in _tagged(list(ops)):
                if op.action is StructuralAction.REPEAL and op.target.leaf_kind() == "sentence":
                    minted[op.op_id] = (base_id, "/".join(f"{k}:{v}" for k, v in op.target.path))
    index = cached_no_amendment_index(_NO_FARCHIVE_PATH)
    realized: list[tuple[str, str, str]] = []
    original = tree_ops.remove_at
    for base_id in sorted({base for base, _address in minted.values()}):
        removed: list[tuple[tuple[tuple[str, str], ...], str]] = []

        def probe(tree: IRNode, path, _sink=removed) -> IRNode:  # noqa: ANN001
            node = tree_ops.resolve(tree, path)
            if node is not None and path:
                _sink.append((tuple(path), node.text or ""))
            return original(tree, path)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(tree_ops, "remove_at", probe)
            replay = replay_no_to_pit(base_id, as_of="2026-07-10", data_dir=_NO_FARCHIVE_PATH, index=index)
        for receipt in replay.write_receipts:
            if receipt.op_id not in minted or not receipt.removed_paths:
                continue
            host = tuple(receipt.removed_paths[0])
            texts = [text for path, text in removed if path[:-1] == host and path[-1][0] == "sentence"]
            leaf = minted[receipt.op_id][1].rsplit(":", 1)[1]
            labelled = [text for path, text in removed if path[:-1] == host and path[-1] == ("sentence", leaf)]
            realized.append((*minted[receipt.op_id], (labelled or texts or [""])[0]))
    assert tuple(sorted(realized)) == _W65_CORPUS_SENTENCE_DESTRUCTIONS
