"""The print-era (pre-2001) witness lane: kringkastingsloven reconstructed from NB facsimiles.

Three levels, all over ``tests/data/norway_print_era/kringkastingsloven`` (W-103):

1. the promoted emitter reproduces the committed 14 acts byte for byte from the
   committed evidence ladder, with the receipts the ledger quotes;
2. source-absent, the pre-2001 chain replays end to end and the 13 sections no
   2001+ act ever touched are pinned against today's consolidation (11 byte-equal,
   2 dash-class-only);
3. with the local 2001+ archives present (corpus-gated, ``slow``), the full chain
   to 2026 pins the witness the ledger quotes at W-104: 63 of 75 sections
   byte-identical, 198 ops accepted / 14 rejected, three acts contingent.
"""

from __future__ import annotations

import io
import json
import re
import tarfile
from collections import Counter
from pathlib import Path

import pytest

from lawvm.norway.grafter import parse_no_amendment_groups, parse_no_statute
from lawvm.norway.print_era import (
    NO_PRINT_ERA_ADDRESS_DASH_FOLDED,
    NO_PRINT_ERA_LEAD_REFUSED,
    NO_PRINT_ERA_OMNIBUS_CARVE,
    NO_PRINT_ERA_PROPOSAL_TEXT_LANDED,
    PrintEraLandingVariant,
    commencement_dates_from_chains,
    emit_founding_act,
    emit_print_era_slice,
    join_wrapped_lines,
    landed_lines,
    load_print_era_chains,
    load_print_era_ladder,
    load_print_era_manifest,
    lti_file_name,
    segment_founding_act,
)
from lawvm.norway.verify import verify_no_against_current

_REPO = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO / "tests" / "data" / "norway_print_era" / "kringkastingsloven"
_PUBLIC = _REPO / "data" / "norway" / "public"
_BASE_LOV_ID = "1992-12-04-127"
_BASE_ID = f"no/lov/{_BASE_LOV_ID}"
_DASH_RE = re.compile(r"[‐‑‒–—―−-]")

# The 13 sections of today's consolidation whose ``changesToParent`` chain names no
# 2001+ act: the only sections the pre-2001 chain can match on its own.
_OCR_ONLY_SECTIONS = frozenset({"2-4", "2-5", "2-8", "2-9", "4-1", "5-1", "6-1", "6-3", "6-5", "7-3", "9-1", "9-2", "9-3"})
# W-91 (iv): the print's dash in §§ 9-2 and 9-3 lands as ``-``/``—`` by engine where
# Lovdata prints ``–``; no two channels agree on the dash byte, so the row is a typed
# dash-class divergence, never folded away.
_DASH_ONLY_SECTIONS = frozenset({"9-2", "9-3"})

# W-102's full-chain witness (glm proposal variant, as-of 2026-08-25), moved by
# W-104: the 2004 Medietilsynet act (no/lovtid/2004-07-02-68) now applies through
# the addressed word-substitution production, closing § 4-6 (62 -> 63) and adding
# its twelve ops (accepted 189 -> 198); its three ops on § 2-1 refuse at apply
# (rejected 11 -> 14) because the replay's § 2-1 still carries the pre-2001 ledd
# order, so the addressed ledd is the wrong text.
_FULL_CHAIN_AS_OF = "2026-08-25"
_FULL_CHAIN_CLEAN_SECTIONS = 63
_FULL_CHAIN_CONTINGENT = frozenset({"no/lovtid/2005-06-17-98", "no/lovtid/2025-02-28-2", "no/lovtid/2025-04-25-12"})
_FULL_CHAIN_SKIPPED_WHOLE = frozenset({"no/lovtid/2025-04-25-12"})
_FULL_CHAIN_DIVERGENT_SECTIONS = frozenset(
    {"2-1", "4-4", "6-1a", "7-1", "8-4", "9-2", "9-3", "10-1", "10-3", "10-4", "10-5", "10-6"}
)
# Two of the 26 rows sit on chapter headings, not sections: the print-era heading
# replacements land chapter 3's title without the ``Kap. 3.`` prefix the consolidation
# prints, and chapter 5's re-enactment lands ``Kap. Beriktigelse`` (a lead-grammar gap,
# not an OCR one; W-98 (f)). ``_section_of`` files them under ``?``.
_FULL_CHAIN_CHAPTER_ROWS = frozenset({"3", "5"})


def _fixture_inputs():
    ladder = load_print_era_ladder(_FIXTURE / "ladder_lines.json")
    manifests = load_print_era_manifest(_FIXTURE / "manifest.json")
    chains = load_print_era_chains(_FIXTURE / "chains.json")
    return ladder, manifests, chains


def _write_archive(path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:bz2") as tf:
        for member_name, payload in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def _fixture_data_dir(tmp_path: Path) -> Path:
    """The committed slice as the two archives the Norway source reader expects."""
    members = []
    for path in sorted((_FIXTURE / "lti").glob("nl-*.xml")):
        year = path.name[3:7]
        members.append((f"lti/{year}/{path.name}", path.read_bytes()))
    _write_archive(tmp_path / "lovtidend-avd1-1992-2000.tar.bz2", members)
    _write_archive(
        tmp_path / "gjeldende-lover.tar.bz2",
        [("nl/nl-19921204-127.xml", (_FIXTURE / "current" / "nl-19921204-127.xml").read_bytes())],
    )
    return tmp_path


def _section_of(divergence) -> str:
    return next((value for level, value in divergence.address.path if level == "section"), "?")


def _divergence_kinds(result) -> dict[str, Counter[str]]:
    """Per section, the divergence kinds with text mismatches split into dash-class-only vs text."""
    kinds: dict[str, Counter[str]] = {}
    for divergence in result.divergences:
        kind = str(divergence.divergence_type).split(".")[-1]
        if kind == "MISMATCH":
            ops_text = _DASH_RE.sub("-", divergence.ops_text or "")
            current_text = _DASH_RE.sub("-", divergence.consolidated_text or "")
            kind = "MISMATCH:dash-class-only" if ops_text == current_text else "MISMATCH:text"
        kinds.setdefault(_section_of(divergence), Counter())[kind] += 1
    return kinds


def _all_sections(chains) -> list[str]:
    return [row["sec"].replace("§ ", "").replace(" ", "") for row in chains]


# --------------------------------------------------------------------------- 1. the emitter
def test_print_era_emitter_reproduces_the_committed_slice_byte_for_byte() -> None:
    ladder, manifests, chains = _fixture_inputs()
    emissions = emit_print_era_slice(ladder, manifests, chains, _BASE_LOV_ID)
    assert [e.act_id for e in emissions] == sorted(m.act_id for m in manifests)
    assert len(emissions) == 14
    for emission in emissions:
        committed = (_FIXTURE / "lti" / emission.file_name).read_text(encoding="utf-8")
        assert emission.xml == committed, f"{emission.file_name} drifted from the committed fixture"
    receipts = json.loads((_FIXTURE / "receipts.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps({e.act_id: e.receipt.to_dict() for e in emissions})) == receipts


def test_print_era_ladder_totals_match_the_manifest() -> None:
    ladder, manifests, _ = _fixture_inputs()
    raw = json.loads((_FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    for entry in raw["acts"]:
        assert ladder.class_totals(entry["act_id"]) == entry["ladder_totals"], entry["act_id"]
    # W-91's ladder over the 36 body pages: A 1,139 · B 246 · C 146 · R 40.
    assert ladder.class_totals() == {"A": 1139, "B": 246, "C": 146, "R": 40}
    assert {m.act_id for m in manifests if m.carve_item_canvas is not None} == {"1997-06-13-44", "1998-07-17-56"}


def test_print_era_receipts_name_what_the_emission_did() -> None:
    ladder, manifests, chains = _fixture_inputs()
    by_act = {e.act_id: e for e in emit_print_era_slice(ladder, manifests, chains, _BASE_LOV_ID)}
    # The founding act lands STRICT: no proposal text, no folds (body only), no leads.
    founding = by_act[_BASE_LOV_ID].receipt
    assert founding.rule_ids == () and founding.proposal_lines == 0 and founding.refused_leads == ()
    assert founding.date_source == "act-date"
    # The two omnibus hosts carve one item each and say so.
    for act_id in ("1997-06-13-44", "1998-07-17-56"):
        receipt = by_act[act_id].receipt
        assert receipt.carve is not None and receipt.carve.items_on_page >= 1
        assert NO_PRINT_ERA_OMNIBUS_CARVE in receipt.rule_ids
        assert f"{NO_PRINT_ERA_OMNIBUS_CARVE}: item {receipt.carve.item_no} only" in by_act[act_id].xml
        assert 'data-lawvm-carve="item-' in by_act[act_id].xml
    # A lead built from an R line is marked on the article and receipted, never silently landed.
    refused = [e for e in by_act.values() if e.receipt.refused_leads]
    assert refused, "the slice has R-class leads (W-91: 1998-05-22-32, 1999-06-25-51, 2000-01-14-5/-6, 1993-12-17-126)"
    for emission in refused:
        assert NO_PRINT_ERA_LEAD_REFUSED in emission.receipt.rule_ids
        assert emission.xml.count('data-lawvm-refused="1"') >= 1
    # Proposal-landed body lines are marked; STRICT never marks one.
    proposal = [e for e in by_act.values() if e.receipt.proposal_lines]
    assert proposal and all(NO_PRINT_ERA_PROPOSAL_TEXT_LANDED in e.receipt.rule_ids for e in proposal)
    assert all('data-lawvm-proposal="glm"' in e.xml for e in proposal)
    strict = emit_print_era_slice(
        ladder, manifests, chains, _BASE_LOV_ID, amending_variant=PrintEraLandingVariant.STRICT
    )
    assert all('data-lawvm-proposal' not in e.xml and e.receipt.proposal_lines == 0 for e in strict)
    # The address-dash fold fires on leads and headers only and is counted.
    folded = [e for e in by_act.values() if e.receipt.address_folds]
    assert folded and all(NO_PRINT_ERA_ADDRESS_DASH_FOLDED in e.receipt.rule_ids for e in folded)
    assert sum(e.receipt.address_folds for e in by_act.values()) == 31


def test_print_era_dates_come_from_the_consolidation_chain_and_say_so() -> None:
    _, _, chains = _fixture_inputs()
    dates = commencement_dates_from_chains(chains)
    assert dates["1998-05-22-32"] == ("1998-06-01",)
    assert dates["2000-01-14-4"] == ("2000-01-20",)
    assert "2003-01-31-8" not in dates, "2001+ acts are the archive's business, not the chain's"
    # An act the chain names without an ``ikr.`` falls back to its own date, receipted.
    assert dates["1994-06-24-45"] == ()
    ladder, manifests, chains = _fixture_inputs()
    by_act = {e.act_id: e for e in emit_print_era_slice(ladder, manifests, chains, _BASE_LOV_ID)}
    assert by_act["1994-06-24-45"].receipt.date_source == "act-date"
    assert by_act["1994-06-24-45"].receipt.date_in_force == "1994-06-24"
    assert by_act["1998-05-22-32"].receipt.date_source == "consolidation-chain-ikr"
    assert '<dd class="dateInForce">1998-06-01</dd>' in by_act["1998-05-22-32"].xml


def test_print_era_segmenter_reads_the_founding_act_structure() -> None:
    ladder, _, _ = _fixture_inputs()
    lines = landed_lines(ladder, _BASE_LOV_ID, PrintEraLandingVariant.STRICT)
    act = segment_founding_act(_BASE_LOV_ID, lines)
    assert act.title == "Lov om kringkasting."
    assert [chapter.label for chapter in act.chapters] == [str(n) for n in range(1, 11)]
    sections = [section for chapter in act.chapters for section in chapter.sections]
    assert len(sections) == 41
    assert sum(len(section.ledd) for section in sections) == 132
    assert sum(len(ledd.items) for section in sections for ledd in section.ledd) == 13
    # Every unit keeps the class of every line it was built from; nothing is dropped.
    assert all(ledd.classes for section in sections for ledd in section.ledd)
    # A header of class R is still a header (the loose reader accepts the print's ``§ 3—l``).
    by_label = {section.label: section for section in sections}
    assert by_label["3-1"].header_class == "R" and by_label["3-1"].raw_header.startswith("§ 3—l.")
    # The real parser reads the emission.
    statute = parse_no_statute(emit_founding_act(ladder, _BASE_LOV_ID, {}, PrintEraLandingVariant.STRICT).xml.encode(), _BASE_ID)
    assert statute.title == "Lov om kringkasting."


def test_join_wrapped_lines_joins_only_an_attached_hyphen() -> None:
    from lawvm.norway.print_era import LandedLine

    def line(text: str) -> LandedLine:
        return LandedLine(canvas=1, index=0, ladder_class="A", text=text, indent=0, width=800, agreed=True, proposal_landed=False)

    assert join_wrapped_lines([line("nær-"), line("kringkasting")]) == ("nærkringkasting", ("nær-|kringkasting",))
    assert join_wrapped_lines([line("territorium -"), line("herunder")]) == ("territorium - herunder", ())
    assert join_wrapped_lines([line("lyd-"), line("og bildeprogram")]) == ("lyd- og bildeprogram", ())


def test_print_era_amending_acts_parse_to_ops_through_the_real_grafter() -> None:
    ladder, manifests, chains = _fixture_inputs()
    total_ops = 0
    for emission in emit_print_era_slice(ladder, manifests, chains, _BASE_LOV_ID):
        if emission.act_id == _BASE_LOV_ID:
            continue
        adjudications: list = []
        groups = parse_no_amendment_groups(emission.xml.encode(), f"no/lovtid/{emission.act_id}", adjudications_out=adjudications)
        ops = [op for _, group_ops in groups for op in group_ops]
        assert ops, f"{emission.act_id} parsed to zero ops"
        total_ops += len(ops)
    assert total_ops >= 75, "W-102 witness: 75 ops accepted on the pre-2001 chain"


# --------------------------------------------------------------------------- 2. source-absent replay
def test_print_era_slice_replays_the_pre2001_chain_source_absent(tmp_path) -> None:
    data_dir = _fixture_data_dir(tmp_path)
    result = verify_no_against_current(_BASE_ID, as_of="2000-12-31", data_dir=data_dir)
    assert result.error is None
    assert result.replay_status == "replayed"
    replay = result.replay
    assert replay is not None
    expected = sorted(f"no/lovtid/{m.act_id}" for m in load_print_era_manifest(_FIXTURE / "manifest.json") if m.act_id != _BASE_LOV_ID)
    assert sorted(replay.amendments_applied) == expected, "all 13 print-era acts apply"
    assert replay.amendments_skipped_contingent == [] and replay.amendments_skipped_missing_source == []
    _, _, chains = _fixture_inputs()
    kinds = _divergence_kinds(result)
    clean = {section for section in _all_sections(chains) if section not in kinds}
    # The OCR-only sections: 11 byte-equal, 2 dash-class-only, none blocked, zero text divergence.
    assert clean & _OCR_ONLY_SECTIONS == _OCR_ONLY_SECTIONS - _DASH_ONLY_SECTIONS
    for section in _DASH_ONLY_SECTIONS:
        assert set(kinds[section]) == {"MISMATCH:dash-class-only"}, (section, kinds[section])
    assert not any("MISMATCH:text" in kinds.get(section, {}) for section in _OCR_ONLY_SECTIONS)
    # Beyond the OCR-only set only sections a 2001+ act rewrote can diverge, by construction.
    assert len(clean) == 14, sorted(clean)


# --------------------------------------------------------------------------- 3. the full-chain witness
@pytest.mark.slow
def test_print_era_slice_full_chain_pins_the_w104_witness(tmp_path) -> None:
    """The ledger's witness: a 1992 facsimile plus 34 years of amendments against today's text."""
    archives = [_PUBLIC / "lovtidend-avd1-2001-2025.tar.bz2", _PUBLIC / "lovtidend-avd1-2026.tar.bz2"]
    if not all(archive.exists() for archive in archives):
        pytest.skip("local Norway public archives are not installed")
    data_dir = _fixture_data_dir(tmp_path)
    for archive in archives:
        (data_dir / archive.name).symlink_to(archive)
    result = verify_no_against_current(_BASE_ID, as_of=_FULL_CHAIN_AS_OF, data_dir=data_dir)
    assert result.error is None
    replay = result.replay
    assert replay is not None
    assert result.replay_status == "blocked_contingent"
    assert set(replay.amendments_skipped_contingent) == _FULL_CHAIN_CONTINGENT
    assert set(replay.amendments_scanned) - set(replay.amendments_applied) == _FULL_CHAIN_SKIPPED_WHOLE
    filtered = replay.apply_filter_result
    assert filtered is not None
    assert (len(filtered.accepted_items), len(filtered.rejected_items)) == (198, 14)
    _, _, chains = _fixture_inputs()
    kinds = _divergence_kinds(result)
    sections = _all_sections(chains)
    clean = [section for section in sections if section not in kinds]
    assert len(sections) == 75
    assert set(kinds) - {"?"} == _FULL_CHAIN_DIVERGENT_SECTIONS
    chapter_rows = {
        next(value for level, value in d.address.path if level == "chapter")
        for d in (result.divergences or ())
        if _section_of(d) == "?"
    }
    assert chapter_rows == _FULL_CHAIN_CHAPTER_ROWS
    assert len(clean) == _FULL_CHAIN_CLEAN_SECTIONS
    assert result.divergence_count == 26


def test_print_era_emitters_fail_loud_when_the_manifest_points_past_the_title() -> None:
    from dataclasses import replace

    from lawvm.norway.print_era import emit_amending_act, emit_omnibus_carve

    ladder, manifests, chains = _fixture_inputs()
    dates = commencement_dates_from_chains(chains)
    by_act = {m.act_id: m for m in manifests}
    # An amending act whose manifest names a canvas the ladder never read (the acts
    # share pages, so a neighbouring act's title would otherwise be picked up).
    wrong = replace(by_act["1993-12-17-126"], start_canvas=999)
    with pytest.raises(ValueError, match="1993-12-17-126.*canvas 999"):
        emit_amending_act(ladder, wrong, _BASE_LOV_ID, dates, PrintEraLandingVariant.PROPOSAL)
    wrong_carve = replace(by_act["1997-06-13-44"], start_canvas=999)
    with pytest.raises(ValueError, match="1997-06-13-44.*canvas 999"):
        emit_omnibus_carve(ladder, wrong_carve, _BASE_LOV_ID, dates, PrintEraLandingVariant.PROPOSAL)
    # An omnibus host whose carve canvas holds no item naming the base law.
    no_item = replace(by_act["1997-06-13-44"], carve_item_canvas=51)
    with pytest.raises(ValueError, match="1997-06-13-44: expected one item naming the base law"):
        emit_omnibus_carve(ladder, no_item, _BASE_LOV_ID, dates, PrintEraLandingVariant.PROPOSAL)


def test_lti_file_name_follows_the_archive_convention() -> None:
    assert lti_file_name("1992-12-04-127") == "nl-19921204-127.xml"
    assert lti_file_name("1996-02-02-6") == "nl-19960202-006.xml"
