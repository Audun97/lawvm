"""W-100. The section- and part-scoped commencement statement reader.

Every positive case here is a corpus sentence, quoted verbatim from the
instrument named beside it; every negative is either a corpus sentence the
reader must refuse or a synthetic minimal pair for one closed-vocabulary rule.
The reader's contract is totality: one unreadable sentence refuses the whole
text, and the refusing sentence is recorded.
"""

from __future__ import annotations

import pytest

from lawvm.norway.commencement_scope import (
    NOCommencementScopeItem,
    NOCommencementScopeReading,
    NOCommencementScopeStatement,
    act_scoped_operative_blocks,
    is_forskrift_only_block,
    read_no_commencement_scope_statements,
    split_sentences,
)

_KK = "no/lov/1992-12-04-127"


def _read(
    text: str,
    *,
    instrument_date: str,
    declared: tuple[str, ...],
    own: tuple[str, ...] = (),
) -> NOCommencementScopeReading:
    return read_no_commencement_scope_statements(
        [text], instrument_date=instrument_date, declared_dates=declared, own_act_law_ids=own
    )


def _sections(
    *labels: str,
    qualified: tuple[str, ...] = (),
    law_ref: str = "",
    subpaths: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> NOCommencementScopeItem:
    return NOCommencementScopeItem(
        kind="sections",
        law_ref=law_ref,
        section_labels=labels,
        qualified_section_labels=qualified,
        qualified_section_subpaths=subpaths,
    )


def _part(
    label: str,
    *labels: str,
    qualified: tuple[str, ...] = (),
    law_ref: str = "",
    subpaths: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> NOCommencementScopeItem:
    return NOCommencementScopeItem(
        kind="part",
        part_label=label,
        law_ref=law_ref,
        section_labels=labels,
        qualified_section_labels=qualified,
        qualified_section_subpaths=subpaths,
    )


_ACT = NOCommencementScopeItem(kind="act")


def test_section_list_under_lovens_with_two_dates_no_forskrift_2009_06_19_702() -> None:
    """Two section-list clauses, two dates, ledd-qualified labels marked."""
    reading = _read(
        "Lovens § 2-3 andre ledd, § 2-13, § 4-2, § 6-1a, § 8-5 og § 10-4 første ledd skal "
        "gjelde fra 1. juli 2009. Lovens § 6-4 skal gjelde fra 1. januar 2010.",
        instrument_date="2009-06-19",
        declared=("2009-07-01", "2010-01-01"),
        own=("no/lov/2009-06-19-92",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_sections(
                "2-3", "2-13", "4-2", "6-1a", "8-5", "10-4",
                qualified=("2-3", "10-4"),
                subpaths=(("10-4", ("subsection:1",)), ("2-3", ("subsection:2",))),
            ),
            date="2009-07-01",
        ),
        NOCommencementScopeStatement(subject=_sections("6-4"), date="2010-01-01"),
    )
    assert reading.dates == ("2009-07-01", "2010-01-01")


def test_whole_act_with_section_carve_outs_no_forskrift_2005_06_17_631() -> None:
    """The act's own citation is the subject; three carved-out items, two ledd-qualified."""
    reading = _read(
        "Lov 17. juni 2005 nr. 98 om endringar i lov 4. desember 1992 nr. 127 om kringkasting "
        "trer i kraft frå 1. juli 2005 med unntak av nytt § 4-4 tredje ledd, endring i § 10-3 "
        "første og annet ledd, samt opphevinga av § 4-6.",
        instrument_date="2005-06-17",
        declared=("2005-07-01",),
        own=("no/lov/2005-06-17-98",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_ACT,
            date="2005-07-01",
            excluded=(
                _sections("4-4", qualified=("4-4",), subpaths=(("4-4", ("subsection:3",)),)),
                _sections("10-3", qualified=("10-3",), subpaths=(("10-3", ("subsection:1", "subsection:2")),)),
                _sections("4-6"),
            ),
        ),
    )


def test_title_echo_then_bare_section_clause_no_forskrift_2008_05_30_524() -> None:
    """A title-echo sentence is benign; the split lands before the ``§``."""
    reading = _read(
        "Delvis ikraftsetting av lov 17. juni 2005 nr. 98 om endringar i lov 4. desember 1992 "
        "nr. 127 om kringkasting. § 10-3 første og andre ledd skal gjelde fra 1. juli 2008.",
        instrument_date="2008-05-30",
        declared=("2008-07-01",),
        own=("no/lov/2005-06-17-98",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_sections("10-3", qualified=("10-3",), subpaths=(("10-3", ("subsection:1", "subsection:2")),)),
            date="2008-07-01",
        ),
    )


def test_header_then_part_items_with_a_carve_out_no_forskrift_2025_04_04_601() -> None:
    """``Følgende trer i kraft <date>:`` dates every bare item after it."""
    reading = _read(
        "Delt ikraftsetting av lov 28. februar 2025 nr. 2 om endringer i kringkastingsloven mv. "
        "(gjennomføring av endringsdirektiv til direktiv om audiovisuelle medietjenester mv.). "
        "Følgende trer i kraft 1. mai 2025: Endringsloven del I (kringkastingsloven) med unntak "
        "av ny §§ 2-22 og 2-23. Endringsloven del II (tobakksskadeloven). Endringsloven del III "
        "(alkoholloven). Endringsloven del IV (legemiddelloven). Endringsloven del V "
        "(bildeprogramloven).",
        instrument_date="2025-04-04",
        declared=("2025-05-01",),
        own=("no/lov/2025-02-28-2",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_part("I"), date="2025-05-01", excluded=(_sections("2-22", "2-23"),)
        ),
        NOCommencementScopeStatement(subject=_part("II"), date="2025-05-01"),
        NOCommencementScopeStatement(subject=_part("III"), date="2025-05-01"),
        NOCommencementScopeStatement(subject=_part("IV"), date="2025-05-01"),
        NOCommencementScopeStatement(subject=_part("V"), date="2025-05-01"),
    )


def test_straks_resolves_to_the_instrument_date_and_part_section_lists_no_forskrift_2023_09_01_1380() -> None:
    reading = _read(
        "Delt ikraftsetting av lov 20. mai 2020 nr. 42 om endringer i markedsføringsloven mv. "
        "(gjennomføring av forordning (EU) 2017/2394 om forbrukervernsamarbeid). Følgende trer i "
        "kraft straks: Endringsloven del I (markedsføringsloven) § 44 tredje ledd og § 47. "
        "Endringsloven del V (kringkastingsloven).",
        instrument_date="2023-09-01",
        declared=("2023-09-01",),
        own=("no/lov/2020-05-20-42",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_part("I", "44", "47", qualified=("44",), subpaths=(("44", ("subsection:3",)),)),
            date="2023-09-01",
        ),
        NOCommencementScopeStatement(subject=_part("V"), date="2023-09-01"),
    )


def test_act_with_part_carve_outs_qualified_by_law_citations_no_forskrift_2020_05_20_1032() -> None:
    """A title containing ``og`` and ``mv.`` is read as title, not as a conjunction or a sentence end."""
    reading = _read(
        "Delt ikraftsetting av endringsloven. Endringsloven trer i kraft 1. juli 2020 med unntak av "
        "del I, endringer i lov 9. januar 2009 nr. 2 om kontroll med markedsføring og avtalevilkår "
        "mv. § 44 tredje ledd og § 47, del V, endringer i lov 4. desember 1992 nr. 127 om "
        "kringkasting og audiovisuelle bestillingstjenester og del VI, endringer i lov 4. desember "
        "1992 nr. 132 om legemidler m.v. § 28 a.",
        instrument_date="2020-05-20",
        declared=("2020-07-01",),
        own=("no/lov/2020-05-20-42",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_ACT,
            date="2020-07-01",
            excluded=(
                _part(
                    "I", "44", "47",
                    qualified=("44",),
                    law_ref="no/lov/2009-01-09-2",
                    subpaths=(("44", ("subsection:3",)),),
                ),
                _part("V", law_ref=_KK),
                _part("VI", "28a", law_ref="no/lov/1992-12-04-132"),
            ),
        ),
    )


def test_carved_out_item_with_its_own_relative_clause_date() -> None:
    """``… med unntak for § 13a som trer i kraft 1. juli 2014`` (no/forskrift/2013-06-21-745, shortened)."""
    reading = _read(
        "Loven trer i kraft fra 1. juli 2013, med unntak for § 13a som trer i kraft 1. juli 2014.",
        instrument_date="2013-06-21",
        declared=("2013-07-01", "2014-07-01"),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(subject=_ACT, date="2013-07-01", excluded=(_sections("13a"),)),
        NOCommencementScopeStatement(subject=_sections("13a"), date="2014-07-01"),
    )


def test_deferred_carve_out_is_an_exclusion_without_a_date() -> None:
    """``§ 14 som trer i kraft når Kongen bestemmer`` (no/forskrift/2016-06-17-686)."""
    reading = _read(
        "Delt ikraftsetting. Loven trer i kraft fra 1. juli 2016 med unntak av § 14 som trer i "
        "kraft når Kongen bestemmer.",
        instrument_date="2016-06-17",
        declared=("2016-07-01",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(subject=_ACT, date="2016-07-01", excluded=(_sections("14"),)),
    )


def test_part_lists_and_ranges_expand_to_one_item_per_part() -> None:
    reading = _read(
        "Loven del II og III trer i kraft 1. juli 2017. Loven del IV til VI trer i kraft 1. januar 2018.",
        instrument_date="2017-06-16",
        declared=("2017-07-01", "2018-01-01"),
    )
    assert reading.total, reading.refused_sentence
    assert [(s.subject.part_label, s.date) for s in reading.statements] == [
        ("II", "2017-07-01"),
        ("III", "2017-07-01"),
        ("IV", "2018-01-01"),
        ("V", "2018-01-01"),
        ("VI", "2018-01-01"),
    ]


def test_short_name_law_hint_is_carried_not_resolved() -> None:
    """``Endringene i barnevernloven § 2-3 …`` (no/forskrift/2011-04-15-405)."""
    reading = _read(
        "Endringene i barnevernloven § 2-3, § 2-3b og § 9-2 trer i kraft straks. Endringene i "
        "barnevernloven § 6-10 trer i kraft 1. september 2011.",
        instrument_date="2011-04-15",
        declared=("2011-04-15", "2011-09-01"),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements[0].subject == _sections("2-3", "2-3b", "9-2", law_ref="barnevernloven")
    assert reading.statements[0].date == "2011-04-15"
    assert reading.statements[1].subject == _sections("6-10", law_ref="barnevernloven")


@pytest.mark.parametrize(
    ("text", "declared", "why"),
    [
        (
            "Delt ikraftsetting av lov 25. april 2025 nr. 12 om innkreving av statlige krav mv. "
            "(innkrevingsloven). Loven trer i kraft 1. januar 2026, med unntak av lovendringene om "
            "utlegg som i saker om utlegg kommer gradvis til anvendelse, og innkrevingsloven § 21 "
            "som trer i kraft 1. januar 2027.",
            ("2026-01-01", "2027-01-01"),
            "no/forskrift/2025-06-10-967: a gradual-application carve-out is not a scope term",
        ),
        (
            "Loven trer i kraft 1. januar 2019. Endringen i § 14-12 andre ledd gis virkning fra "
            "1. juli 2019 når det gjelder konkrete innleieforhold som allerede eksisterer ved "
            "ikrafttredelsen.",
            ("2019-01-01", "2019-07-01"),
            "no/forskrift/2018-06-22-944: an unknown verb refuses the WHOLE text, not just its sentence",
        ),
        (
            "Loven trer i kraft 1. juli 2013. Finansieringsforetak som ved lovens ikrafttredelse "
            "har tillatelse, beholder den.",
            ("2013-07-01",),
            "a transitional provision beside a readable statement refuses the whole text",
        ),
        (
            "Loven trer i kraft 1. juli 2013.",
            ("2013-06-01",),
            "a prose date absent from dateInForce refuses",
        ),
        (
            "Loven § 5 og § 7 trer i kraft.",
            ("2013-07-01",),
            "no date after the verb refuses",
        ),
        (
            "Delt ikraftsetting av lov 2. februar 2025 nr. 5.",
            ("2025-04-01",),
            "a title echo alone reads no statement",
        ),
        (
            "Loven trer i kraft 1. juli 2013 med unntak av § 5 som får ikke anvendelse før 2014.",
            ("2013-07-01",),
            "a relative clause on the carve-out without a commencement verb refuses",
        ),
    ],
)
def test_reader_refuses_the_whole_text_on_one_unreadable_sentence(
    text: str, declared: tuple[str, ...], why: str
) -> None:
    reading = _read(text, instrument_date="2025-06-10", declared=declared)
    assert not reading.total, why
    assert reading.statements == ()
    assert reading.refused_sentence


def test_a_bare_scope_item_without_a_header_refuses() -> None:
    reading = _read("Endringsloven del I (kringkastingsloven).", instrument_date="2025-04-04", declared=("2025-05-01",))
    assert not reading.total
    assert "without a list header" in reading.refused_sentence


def test_forskrift_only_blocks_are_set_aside_and_counted() -> None:
    """no/forskrift/2015-06-12-633: the second block acts on a forskrift and names no act."""
    blocks = (
        "Lov 6. februar 2015 nr. 7 om beskyttelse av mindreårige mot skadelige bildeprogram mv. "
        "trer i kraft 1. juli 2015.",
        "Fra samme tidspunkt oppheves § 2-5 og § 2-6 i forskrift 28. februar 1997 nr. 153 om "
        "kringkasting og audiovisuelle bestillingstjenester.",
    )
    assert is_forskrift_only_block(blocks[1])
    assert not is_forskrift_only_block(blocks[0])
    assert act_scoped_operative_blocks(blocks) == ((blocks[0],), 1)
    # The first block is never dropped, whatever it says.
    assert act_scoped_operative_blocks((blocks[1],)) == ((blocks[1],), 0)
    reading = read_no_commencement_scope_statements(
        blocks,
        instrument_date="2015-06-12",
        declared_dates=("2015-07-01",),
        own_act_law_ids=("no/lov/2015-02-06-7", _KK),
    )
    assert reading.total, reading.refused_sentence
    assert reading.forskrift_blocks_dropped == 1
    assert reading.statements == (NOCommencementScopeStatement(subject=_ACT, date="2015-07-01"),)


def test_sentence_split_respects_abbreviations_and_breaks_before_a_section_sign() -> None:
    assert split_sentences("… avtalevilkår mv. § 44 tredje ledd og § 47, del V.") == [
        "… avtalevilkår mv. § 44 tredje ledd og § 47, del V."
    ]
    assert split_sentences("… om kringkasting. § 10-3 første ledd skal gjelde fra 1. juli 2008.") == [
        "… om kringkasting",
        "§ 10-3 første ledd skal gjelde fra 1. juli 2008.",
    ]
    assert split_sentences("Følgende trer i kraft straks: Endringsloven del V.") == [
        "Følgende trer i kraft straks",
        "Endringsloven del V.",
    ]


def test_reading_round_trips_through_serialization() -> None:
    reading = _read(
        "Loven trer i kraft fra 1. juli 2013, med unntak for § 13a som trer i kraft 1. juli 2014.",
        instrument_date="2013-06-21",
        declared=("2013-07-01", "2014-07-01"),
    )
    assert NOCommencementScopeReading.from_dict(reading.to_dict()) == reading
    assert NOCommencementScopeReading.from_dict({}) == NOCommencementScopeReading()


# --------------------------------------------------------------------------
# W-102: the qualifier run spelled as paths below the section.
# --------------------------------------------------------------------------


def test_w102_ledd_range_spells_every_ledd_no_forskrift_2016_09_30_1136() -> None:
    reading = _read(
        "Delt ikraftsetting av lov 17. juni 2016 nr. 58 om endringer i utlendingsloven mv. "
        "(innstramninger II). Endringene i lov 15. mai 2008 nr. 35 om utlendingers adgang til "
        "riket og deres opphold her § 62 annet til syvende ledd, § 90, § 100 og § 100 a trer i "
        "kraft 1. oktober 2016.",
        instrument_date="2016-09-30",
        declared=("2016-10-01",),
        own=("no/lov/2016-06-17-58",),
    )
    assert reading.total, reading.refused_sentence
    assert reading.statements == (
        NOCommencementScopeStatement(
            subject=_sections(
                "62", "90", "100", "100a",
                qualified=("62",),
                law_ref="no/lov/2008-05-15-35",
                subpaths=(("62", tuple(f"subsection:{n}" for n in range(2, 8))),),
            ),
            date="2016-10-01",
        ),
    )


def test_w102_ledd_bokstav_and_punktum_spell_two_step_paths_no_forskrift_2026_06_19_1151() -> None:
    reading = _read(
        "Følgende trer i kraft 1. juli 2026: Endringsloven del I (finansforetaksloven) § 2-1 "
        "tredje ledd, § 5-1 annet ledd, § 5-2 første ledd bokstav d og e, § 5-9, § 7-5, § 8-5 "
        "fjerde ledd, § 16-2, § 19-11 sjette ledd, og § 20-51 sjette ledd.",
        instrument_date="2026-06-19",
        declared=("2026-07-01",),
        own=("no/lov/2026-06-19-40",),
    )
    assert reading.total, reading.refused_sentence
    item = reading.statements[0].subject
    assert item.kind == "part" and item.part_label == "I"
    assert item.qualified_section_labels == ("2-1", "5-1", "5-2", "8-5", "19-11", "20-51")
    assert item.qualified_section_subpaths == (
        ("19-11", ("subsection:6",)),
        ("2-1", ("subsection:3",)),
        ("20-51", ("subsection:6",)),
        ("5-1", ("subsection:2",)),
        ("5-2", ("subsection:1/item:d", "subsection:1/item:e")),
        ("8-5", ("subsection:4",)),
    )
    assert item.subpaths_of("5-2") == ("subsection:1/item:d", "subsection:1/item:e")
    assert item.subpaths_of("5-9") == ()

    reading = _read(
        "Følgende trer i kraft 1. januar 2027: Endringsloven del I § 9 andre og tredje ledd, § 11, "
        "§ 13, § 13a fjerde og femte punktum, § 13b, § 21 fjerde ledd annet punktum, § 22 første "
        "ledd og § 28 første ledd.",
        instrument_date="2025-06-20",
        declared=("2027-01-01",),
        own=("no/lov/2025-06-20-38",),
    )
    assert reading.total, reading.refused_sentence
    item = reading.statements[0].subject
    # A bare ``punktum`` with no ledd above it spells no path: § 13a stays qualified without one.
    assert item.qualified_section_labels == ("9", "13a", "21", "22", "28")
    assert item.qualified_section_subpaths == (
        ("21", ("subsection:4/sentence:2",)),
        ("22", ("subsection:1",)),
        ("28", ("subsection:1",)),
        ("9", ("subsection:2", "subsection:3")),
    )


def test_w102_nr_after_a_ledd_and_transparent_nytt_no_forskrift_2025_06_06_942_and_2005_04_29_379() -> None:
    reading = _read(
        "Følgende trer i kraft 1. januar 2026: Endringsloven § 4 første ledd nr. 1 og 2 og § 4 "
        "andre til fjerde ledd.",
        instrument_date="2025-06-06",
        declared=("2026-01-01",),
        own=("no/lov/2025-06-06-27",),
    )
    assert reading.total, reading.refused_sentence
    item = reading.statements[0].subject
    assert item.section_labels == ("4", "4")
    assert item.qualified_section_labels == ("4",)
    assert item.qualified_section_subpaths == (
        ("4", ("subsection:1/item:1", "subsection:1/item:2", "subsection:2", "subsection:3", "subsection:4")),
    )

    reading = _read(
        "Lov 29. april 2005 nr. 25 om endringer i lov 7. juni 1996 nr. 31 om Den norske kirke "
        "gjelder fra 1. juni 2005, med unntak for kirkeloven § 23 første ledd ny bokstav f som "
        "gjelder fra 1. juni 2006.",
        instrument_date="2005-04-29",
        declared=("2005-06-01", "2006-06-01"),
        own=("no/lov/2005-04-29-25",),
    )
    assert reading.total, reading.refused_sentence
    carved = _sections(
        "23", qualified=("23",), law_ref="kirkeloven", subpaths=(("23", ("subsection:1/item:f",)),)
    )
    assert reading.statements == (
        NOCommencementScopeStatement(subject=_ACT, date="2005-06-01", excluded=(carved,)),
        NOCommencementScopeStatement(subject=carved, date="2006-06-01"),
    )


@pytest.mark.parametrize(
    "qualifier",
    [
        "siste ledd",
        "nr. 8 første og fjerde ledd",
        "første ledd nr. 1 andre punktum",
        "fjerde og femte punktum",
        "ledd",
        "første ledd bokstav a til c",
        "tredje til andre ledd",
    ],
)
def test_w102_qualifiers_the_path_grammar_cannot_place_leave_the_label_pathless(qualifier: str) -> None:
    reading = _read(
        f"Loven § 5 {qualifier} og § 6 trer i kraft 1. juli 2025.",
        instrument_date="2025-06-01",
        declared=("2025-07-01",),
    )
    assert reading.total, reading.refused_sentence
    item = reading.statements[0].subject
    assert item.section_labels == ("5", "6")
    assert item.qualified_section_labels == ("5",)
    assert item.qualified_section_subpaths == ()


def test_w102_subpaths_round_trip_through_serialization() -> None:
    reading = _read(
        "Lovens § 2-3 andre ledd, § 2-13 og § 10-4 første ledd skal gjelde fra 1. juli 2009.",
        instrument_date="2009-06-19",
        declared=("2009-07-01",),
    )
    assert reading.total
    assert reading.to_dict()["statements"][0]["subject"]["qualified_section_subpaths"] == [
        ["10-4", ["subsection:1"]],
        ["2-3", ["subsection:2"]],
    ]
    assert NOCommencementScopeReading.from_dict(reading.to_dict()) == reading
