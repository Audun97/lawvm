from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from typing import cast

from lxml import etree
import pytest


from lawvm.core.ir import (
    IRNode,
    IRStatute,
    LegalAddress,
    LegalOperation,
    OperationSource,
    TextPatchSpec,
    TextSelector,
)
from lawvm.core.semantic_types import IRNodeKind, StructuralAction, TextPatchKindEnum
from lawvm.replay_adjudication import CompileAdjudication
from lawvm.norway.grafter import (
    NO_PARSE_COLLECTIVE_REENACTMENT_PART_UNRESOLVED,
    NOHeadingGroup,
    _extract_no_embedded_multi_act_lead,
    _no_collective_reenactment_lead_base_id,
    no_part_law_ids,
    _extract_no_law_announcement_base_id,
    _extract_no_law_citation_base_id,
    _extract_no_section_base_id_from_lead,
    _infer_no_multi_item_specs_from_lead,
    _infer_same_base_sentence_target_specs_from_lead,
    _no_rettelse_item_target_from_lead,
    _normalize_no_chapter_scoped_section_lead,
    _no_element_lead_text,
    _no_unstructured_law_switch_lead_base_id,
    _no_section_repeal_list_labels,
    _no_unstructured_section_renumber_labels,
    _no_unstructured_section_repeal_renumber_labels,
    _split_no_run_on_lead_node,
    _split_no_trapped_payload_leads,
    _no_unstructured_lead_looks_operative,
    _split_no_sentences,
    apply_no_heading_groups,
    apply_no_ops,
    iter_no_document_change_ops,
    lovdata_amendment_filename_to_id,
    lovdata_filename_to_id,
    lovdata_path_to_address,
    normalize_lovdata_refid,
    open_lovdata_amendment_archive,
    parse_no_heading_groups,
    parse_no_amendment_ops,
    parse_no_statute,
)
from lawvm.norway.sources import load_no_amendment_bytes
from lawvm.tools.build import _build_no


def _kind_value(kind: object) -> object:
    if isinstance(kind, IRNodeKind):
        return kind.value
    return kind


def _action_value(action: object) -> object:
    if isinstance(action, StructuralAction):
        return action.value
    return action


_STATUTE_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head>
    <title>Testlov om data</title>
  </head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-1">
      <section class="section" data-name="kap1" data-lovdata-URL="NL/lov/2025-01-01-1/KAPITTEL_1">
        <h2>Kapittel 1. Innledning</h2>
        <article class="legalArticle" data-name="§1" data-lovdata-URL="NL/lov/2025-01-01-1/§1">
          <h3 class="legalArticleHeader">§ 1. Formaal</h3>
          <article class="legalP" id="ledd1">Loven gjelder testdata.</article>
        </article>
        <article class="legalArticle" data-name="§2" data-lovdata-URL="NL/lov/2025-01-01-1/§2">
          <h3 class="legalArticleHeader">§ 2. Krav</h3>
          <article class="legalP" id="ledd1">
            Kravene er:
            <ol>
              <li data-li-identifier="1." data-name="1.">ett krav</li>
              <li data-li-identifier="2." data-name="2.">to krav</li>
            </ol>
          </article>
          <article class="changesToParent">Endret ved lov ...</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


_AMENDMENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-change-part="lov/2025-01-01-1/§2/nummer/1"
               data-add-new-part="lov/2025-01-01-1/§2/nummer/3">
        <article class="defaultP">I loven skal nr. 1 endres og ny nr. 3 tilfoyes.</article>
        <li data-li-identifier="1." data-name="1.">oppdatert krav</li>
        <li data-li-identifier="3." data-name="3.">tredje krav</li>
      </article>
      <article class="change"
               data-repeal-part="lov/2025-01-01-1/§1">
        <article class="defaultP">Paragraf 1 oppheves.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def test_lovdata_filename_to_id_skips_nynorsk_and_normalizes_number() -> None:
    assert lovdata_filename_to_id("nl/nl-18840614-003.xml") == "no/lov/1884-06-14-3"
    assert lovdata_filename_to_id("nl/nl-18840614-003-nn.xml") is None


def test_lovdata_amendment_filename_to_id_normalizes_lovtidend_member_path() -> None:
    assert (
        lovdata_amendment_filename_to_id("lti/2025/nl-20250202-005.xml")
        == "no/lovtid/2025-02-02-5"
    )


def test_normalize_lovdata_refid_handles_noisy_document_refs() -> None:
    assert normalize_lovdata_refid("lov/2005-05-20-28/§1/ledd/2") == "no/lov/2005-05-20-28"
    assert normalize_lovdata_refid("no/lov/2005-05-20-28") == "no/lov/2005-05-20-28"
    assert (
        normalize_lovdata_refid("lov/2020-12-18-139 lov/1997-02-28-19")
        == "no/lov/2020-12-18-139"
    )


def test_lovdata_path_to_address_maps_structured_path_components() -> None:
    address = lovdata_path_to_address("lov/2008-06-27-71/§11-10/ledd/1/nummer/5")

    assert address is not None
    assert address.path == (
        ("section", "11-10"),
        ("subsection", "1"),
        ("item", "5"),
    )


def test_parse_no_statute_preserves_chapter_section_and_item_structure() -> None:
    statute = parse_no_statute(_STATUTE_XML, "no/lov/2025-01-01-1")

    assert statute.title == "Testlov om data"
    assert [child.kind for child in statute.body.children] == [IRNodeKind.CHAPTER]

    chapter = statute.body.children[0]
    assert chapter.label == "1"
    assert chapter.children[0].kind == IRNodeKind.HEADING
    assert [child.label for child in chapter.children[1:]] == ["1", "2"]

    section_two = chapter.children[2]
    assert section_two.children[0].kind == IRNodeKind.HEADING
    subsection = section_two.children[1]
    assert subsection.kind == IRNodeKind.SUBSECTION
    assert subsection.text == "Kravene er:"
    assert [(item.label, item.text) for item in subsection.children] == [
        ("1", "ett krav"),
        ("2", "to krav"),
    ]


_MIXED_SHAPE_STATUTE_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head>
    <title>Blandalov om data</title>
  </head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-2">
      <h1>Blandalov om data</h1>
      <article class="legalArticle" data-name="§1" data-lovdata-URL="NL/lov/2025-01-01-2/§1">
        <h3 class="legalArticleHeader">§ 1. Verkeområde</h3>
        <article class="legalP" id="ledd1">Lova gjeld testdata.</article>
      </article>
      <article class="legalArticle" data-name="§2" data-lovdata-URL="NL/lov/2025-01-01-2/§2">
        <h3 class="legalArticleHeader">§ 2. Ikraftsetjing</h3>
        <article class="legalP" id="ledd1">Lova gjeld frå den tid Kongen fastset.</article>
      </article>
      <section class="section" data-name="kap1" data-lovdata-URL="NL/lov/2025-01-01-2/KAPITTEL_1">
        <h2>Vedlegg. Forordninga</h2>
        <article class="legalArticle" data-name="§3" data-lovdata-URL="NL/lov/2025-01-01-2/§3">
          <h3 class="legalArticleHeader">Artikkel 1. Foremaal</h3>
          <article class="legalP" id="ledd1">Forordninga gjeld dette.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_parse_no_statute_keeps_top_level_sections_and_chapters_in_source_order() -> None:
    # W-43: a documentBody mixing top-level `article.legalArticle` with
    # `section.section` must yield BOTH, in document order. The pre-W-43 walk ran
    # the article pass only as an `if not body_children:` fallback to the chapter
    # pass, so the act's own §§ were dropped whenever any chapter parsed non-empty.
    statute = parse_no_statute(_MIXED_SHAPE_STATUTE_XML, "no/lov/2025-01-01-2")

    assert [(child.kind, child.label) for child in statute.body.children] == [
        (IRNodeKind.SECTION, "1"),
        (IRNodeKind.SECTION, "2"),
        (IRNodeKind.CHAPTER, "1"),
    ]

    chapter = statute.body.children[2]
    assert chapter.children[0].kind == IRNodeKind.HEADING
    assert [child.label for child in chapter.children[1:]] == ["3"]


def test_parse_no_statute_keeps_top_level_order_when_chapter_precedes_sections() -> None:
    # W-43: the mirror shape (`S…A`) does not occur in today's corpus, but the
    # merged walk must emit document order rather than a fixed chapters-then-
    # articles order, so pin it here.
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Blandalov om data</title></head>
  <body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2025-01-01-2">
      <section class="section" data-name="kap1" data-lovdata-URL="NL/lov/2025-01-01-2/KAPITTEL_1">
        <h2>Kapittel 1. Innleiing</h2>
        <article class="legalArticle" data-name="§3">
          <h3 class="legalArticleHeader">§ 3. Definisjonar</h3>
          <article class="legalP" id="ledd1">Med data meiner ein testdata.</article>
        </article>
      </section>
      <article class="legalArticle" data-name="§1">
        <h3 class="legalArticleHeader">§ 1. Verkeområde</h3>
        <article class="legalP" id="ledd1">Lova gjeld testdata.</article>
      </article>
      <article class="legalArticle" data-name="§2">
        <h3 class="legalArticleHeader">§ 2. Ikraftsetjing</h3>
        <article class="legalP" id="ledd1">Lova gjeld frå den tid Kongen fastset.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-2")

    assert [(child.kind, child.label) for child in statute.body.children] == [
        (IRNodeKind.CHAPTER, "1"),
        (IRNodeKind.SECTION, "1"),
        (IRNodeKind.SECTION, "2"),
    ]


def test_parse_no_statute_normalizes_letter_item_labels_with_trailing_paren() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Lettered testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§1">
        <article class="legalP">
          Punkter:
          <ol>
            <li data-name="a)">første</li>
            <li data-name="b)">andre</li>
          </ol>
        </article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsection = section.children[0]
    assert [(item.label, item.text) for item in subsection.children] == [
        ("a", "første"),
        ("b", "andre"),
    ]


def test_parse_no_statute_assigns_unique_labels_to_unlabeled_bullet_items() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Bullet testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§1">
        <article class="numberedLegalP" data-numerator="1">
          (1) Foretak som oppfyller følgende vilkår:
          <ul>
            <li data-name="-">ett</li>
            <li data-name="-">to</li>
            <li data-name="-">tre</li>
          </ul>
        </article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsection = section.children[0]
    assert [(item.label, item.text) for item in subsection.children] == [
        ("1", "ett"),
        ("2", "to"),
        ("3", "tre"),
    ]


def test_parse_no_statute_preserves_nested_list_article_item_text() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Nested list article testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§2">
        <h2 class="legalArticleHeader">§ 2. Begreper</h2>
        <article class="legalP">
          I denne lov forstås med:
          <ol class="defaultList" type="1">
            <li data-name="1">
              <article class="listArticle">
                <article class="legalP">Betalingsmidler:<br />Kontanter.</article>
              </article>
            </li>
            <li data-name="2">
              <article class="listArticle">
                <article class="legalP">Valutaveksling:<br />Kjøp og salg.</article>
              </article>
            </li>
          </ol>
        </article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsection = section.children[1]
    assert [(item.label, item.text) for item in subsection.children] == [
        ("1", "Betalingsmidler: Kontanter."),
        ("2", "Valutaveksling: Kjøp og salg."),
    ]


def test_parse_no_statute_reads_numbered_legal_p_as_subsections() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Numbered testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§7-3">
        <h4 class="legalArticleHeader">§ 7-3. Regler om skatt ved utdeling</h4>
        <article class="numberedLegalP" data-numerator="1">(1) Første ledd.</article>
        <article class="numberedLegalP" data-numerator="5">(5) Femte ledd.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    assert [_kind_value(child.kind) for child in section.children] == [
        "heading",
        "subsection",
        "subsection",
    ]
    assert [(child.label, child.text) for child in section.children[1:]] == [
        ("1", "Første ledd."),
        ("5", "Femte ledd."),
    ]


def test_parse_no_statute_merges_unlabeled_punktum_continuation_into_prior_itemized_subsection() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nn">
  <head><title>Språk testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§3">
        <h4 class="legalArticleHeader">§ 3. Verkeområde</h4>
        <article class="legalP">
          Når det ikkje er fastsett noko anna, gjeld lova for
          <ul>
            <li data-li-identifier="a">staten</li>
            <li data-li-identifier="b">kommunane</li>
          </ul>
        </article>
        <article class="legalP">Første punktum bokstav b gjeld ikkje i slike saker.</article>
        <article class="legalP">Lova gjeld ikkje for intern sakshandsaming.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsections = [child for child in section.children if child.kind is IRNodeKind.SUBSECTION]
    assert [child.label for child in subsections] == ["1", "2"]
    assert subsections[0].text == (
        "Når det ikkje er fastsett noko anna, gjeld lova for "
        "Første punktum bokstav b gjeld ikkje i slike saker."
    )
    assert [item.label for item in subsections[0].children] == ["a", "b"]
    assert subsections[1].text == "Lova gjeld ikkje for intern sakshandsaming."


def test_parse_no_statute_merges_leddfortsettelse_into_prior_numbered_subsection() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Vareførsel testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§6-3" id="kapittel-6-paragraf-3">
        <h3 class="legalArticleHeader"><span class="legalArticleValue">§ 6-3</span>. <span class="legalArticleTitle">Varens transaksjonsverdi</span></h3>
        <article class="numberedLegalP" data-numerator="1" id="kapittel-6-paragraf-3-nummer-1">
          (1) Tollverdien av en vare er transaksjonsverdien.
          <ul>
            <li data-li-identifier="a"><article class="listArticle"><article class="legalP">første vilkår</article></article></li>
          </ul>
        </article>
        <p class="leddfortsettelse">Kjøper og selger anses å være avhengig av hverandre.</p>
        <article class="numberedLegalP" data-numerator="2">(2) Andre ledd.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsections = [child for child in section.children if child.kind is IRNodeKind.SUBSECTION]
    assert [child.label for child in subsections] == ["1", "2"]
    assert subsections[0].text == "Tollverdien av en vare er transaksjonsverdien."
    assert [(child.kind, child.label) for child in subsections[0].children] == [
        (IRNodeKind.ITEM, "a"),
        (IRNodeKind.SENTENCE, "1"),
    ]
    assert subsections[0].children[-1].text == "Kjøper og selger anses å være avhengig av hverandre."


def test_parse_no_statute_keeps_internal_leddfortsettelse_as_sentence_child() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Vareførsel testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§6-3" id="kapittel-6-paragraf-3">
        <h3 class="legalArticleHeader"><span class="legalArticleValue">§ 6-3</span>. <span class="legalArticleTitle">Varens transaksjonsverdi</span></h3>
        <article class="numberedLegalP" data-numerator="1" id="kapittel-6-paragraf-3-nummer-1">
          (1) Tollverdien av en vare er transaksjonsverdien.
          <ul>
            <li data-li-identifier="a"><article class="listArticle"><article class="legalP">første vilkår</article></article></li>
          </ul>
          <p class="leddfortsettelse">Kjøper og selger anses å være avhengig av hverandre.</p>
        </article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsections = [child for child in section.children if child.kind is IRNodeKind.SUBSECTION]
    assert [child.label for child in subsections] == ["1"]
    assert subsections[0].text == "Tollverdien av en vare er transaksjonsverdien."
    assert [(child.kind, child.label) for child in subsections[0].children] == [
        (IRNodeKind.ITEM, "a"),
        (IRNodeKind.SENTENCE, "1"),
    ]
    assert subsections[0].children[-1].text == "Kjøper og selger anses å være avhengig av hverandre."


def test_parse_no_statute_keeps_nested_item_prefix_out_of_parent_item_text() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Suppleringsskatt testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§7-1">
        <article class="numberedLegalP" data-numerator="1">
          (1) Er øverste morselskap en enhet med deltakerfastsetting, skal justert overskudd reduseres dersom:
          <ul class="defaultList">
            <li data-li-identifier="b." data-name="b.">
              <article class="listArticle">
                <article class="legalP">eieren er en fysisk person som
                  <ul class="defaultList">
                    <li data-li-identifier="1." data-name="1.">
                      <article class="listArticle"><article class="legalP">er skattemessig bosatt i samme jurisdiksjon som det øverste morselskapet, og</article></article>
                    </li>
                    <li data-li-identifier="2." data-name="2.">
                      <article class="listArticle"><article class="legalP">har en direkte eierinteresse som gir rett til maksimalt 5 prosent.</article></article>
                    </li>
                  </ul>
                </article>
              </article>
            </li>
          </ul>
        </article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    subsection = [child for child in section.children if child.kind is IRNodeKind.SUBSECTION][0]
    item_b = [child for child in subsection.children if child.kind is IRNodeKind.ITEM][0]
    assert item_b.text == "eieren er en fysisk person som"
    assert [(child.kind, child.label, child.text) for child in item_b.children] == [
        (IRNodeKind.ITEM, "1", "er skattemessig bosatt i samme jurisdiksjon som det øverste morselskapet, og"),
        (IRNodeKind.ITEM, "2", "har en direkte eierinteresse som gir rett til maksimalt 5 prosent."),
    ]


def test_parse_no_statute_dedupes_mixed_explicit_and_implicit_subsection_labels() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Mixed numbering testlov</title></head>
  <body>
    <main class="documentBody">
      <article class="legalArticle" data-name="§14-3">
        <article class="legalP">Innledende ledd.</article>
        <article class="defaultP">1. Første endring.</article>
        <article class="defaultP">2. Andre endring.</article>
        <article class="numberedLegalP" data-numerator="2">(2) Nummerert annet ledd.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    section = statute.body.children[0]
    assert [child.label for child in section.children] == ["1", "2", "3", "4"]


def test_iter_no_document_change_ops_infers_subsection_target_from_lead_when_attr_only_marks_section() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2010-06-04-21">
      <article class="change" data-add-new-part="lov/2010-06-04-21/§10-13">
        <article class="defaultP">I lov 4. juni 2010 nr. 21 om fornybar energiproduksjon til havs skal § 10-13 nytt andre ledd lyde:</article>
        <article class="legalP">Nytt andre ledd.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    grouped = iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-06-20-109")

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2010-06-04-21"
    assert len(ops) == 1
    assert ops[0].action is StructuralAction.INSERT
    assert ops[0].target.path == (("section", "10-13"), ("subsection", "2"))
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SUBSECTION
    assert ops[0].payload.text == "Nytt andre ledd."


def test_parse_no_amendment_ops_unstructured_supports_new_section_insert() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2013-01-11-3</li></ul></dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">Ny § 6 a skal lyde:</article>
        <article class="futureLegalArticle" data-name="§6a">
          <span class="futureLegalArticleHeader">§ 6 a. Tittel</span>
          <article class="legalP">Første ledd.</article>
          <article class="legalP">Andre ledd.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2018-12-20-109")

    assert len(ops) == 1
    assert ops[0].action is StructuralAction.INSERT
    assert ops[0].target.path == (("section", "6a"),)
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SECTION
    assert [child.kind for child in ops[0].payload.children] == [
        IRNodeKind.HEADING,
        IRNodeKind.SUBSECTION,
        IRNodeKind.SUBSECTION,
    ]


def test_parse_no_amendment_ops_unstructured_whole_section_replace_without_future_article() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2013-01-11-3</li></ul></dd>
    <main>
      <article class="legalArticle">
        <article class="defaultP">§ 12 skal lyde:</article>
        <article class="legalP">De straffer som anvendes etter denne lov er fengsel og bot.</article>
        <article class="defaultP">§ 15 skal lyde:</article>
        <article class="legalP">Arrest anvendes kun på militære personer.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2015-06-19-65")

    assert [op.action for op in ops] == [StructuralAction.REPLACE, StructuralAction.REPLACE]
    assert [op.target.path for op in ops] == [(("section", "12"),), (("section", "15"),)]
    first = ops[0]
    assert first.payload is not None
    assert first.payload.kind is IRNodeKind.SECTION
    assert first.payload.label == "12"
    assert [child.kind for child in first.payload.children] == [IRNodeKind.SUBSECTION]
    assert first.payload.children[0].text == "De straffer som anvendes etter denne lov er fengsel og bot."


def test_parse_no_amendment_ops_unstructured_whole_section_replace_with_inline_payload() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2013-01-11-3</li></ul></dd>
    <main>
      <article class="legalArticle">
        <article class="defaultP">§ 7 skal lyde: De alminnelige reglene om foreldelse gjelder tilsvarende.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2015-06-19-65")

    assert len(ops) == 1
    assert ops[0].action is StructuralAction.REPLACE
    assert ops[0].target.path == (("section", "7"),)
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SECTION
    assert ops[0].payload.children[0].text == "De alminnelige reglene om foreldelse gjelder tilsvarende."


def test_parse_no_amendment_ops_unstructured_new_section_insert_without_future_article() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2013-01-11-3</li></ul></dd>
    <main>
      <article class="legalArticle">
        <article class="defaultP">Ny § 6 a skal lyde:</article>
        <article class="legalP">Departementet kan gi forskrift om gjennomføringen.</article>
        <article class="defaultP">§ 9 skal lyde:</article>
        <article class="legalP">Loven trer i kraft straks.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2015-06-19-65")

    assert [op.action for op in ops] == [StructuralAction.INSERT, StructuralAction.REPLACE]
    assert [op.target.path for op in ops] == [(("section", "6a"),), (("section", "9"),)]
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SECTION
    assert ops[0].payload.children[0].text == "Departementet kan gi forskrift om gjennomføringen."


def test_parse_no_amendment_ops_unstructured_unparseable_lead_still_drops() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2013-01-11-3</li></ul></dd>
    <main>
      <article class="legalArticle">
        <article class="defaultP">Kapittel 4 endres slik at det nye kapitlet får anvendelse.</article>
      </article>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    ops = parse_no_amendment_ops(
        amendment_xml,
        "no/lovtid/2015-06-19-65",
        adjudications_out=adjudications,
    )

    assert ops == []
    assert "no_parse_unstructured_lead_unmatched" in {item.kind for item in adjudications}


def test_parse_no_amendment_ops_unstructured_supports_item_target_lead() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2022-03-11-9</li></ul></dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">
          § 12-2 fyrste ledd bokstav a skal lyde:
          <ul class="defaultList">
            <li data-name="a.">
              <article class="listArticle">
                <article class="legalP">overtrer plikter etter kapittel 2</article>
              </article>
            </li>
          </ul>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2023-06-16-52")

    assert len(ops) == 1
    assert ops[0].action is StructuralAction.REPLACE
    assert ops[0].target.path == (("section", "12-2"), ("subsection", "1"), ("item", "a"))
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.ITEM
    assert ops[0].payload.text == "overtrer plikter etter kapittel 2"


def test_parse_no_amendment_ops_unstructured_supports_global_text_replace_clause() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/2003-07-04-84</li>
        <li>lov/2003-12-12-108</li>
      </ul>
    </dd>
    <main>
      <section data-name="kapII">
        <article class="legalP">
          I følgende lover skal «friskolelova» erstattes med «privatskolelova» og
          «frittstående skoler» med «skoler godkjent etter privatskolelova»:
        </article>
        <ul>
          <li><article class="listArticle"><article class="legalP">lov 4. juli 2003 nr. 84 om frittståande skolar.</article></article></li>
          <li><article class="listArticle"><article class="legalP">lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner.</article></article></li>
        </ul>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2022-06-10-39")

    text_ops = [op for op in ops if op.action is StructuralAction.TEXT_PATCH]
    assert len(text_ops) == 4
    assert {op.source.title for op in text_ops if op.source is not None} == {
        "no/lov/2003-07-04-84",
        "no/lov/2003-12-12-108",
    }
    patches = []
    for op in text_ops:
        assert op.text_patch is not None
        patches.append(op.text_patch)
    assert {patch.selector.match_text for patch in patches} == {
        "friskolelova",
        "frittstående skoler",
    }


def test_parse_no_amendment_ops_unstructured_flattens_nested_legal_article_children() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/1915-08-13-5</li>
        <li>lov/2003-12-12-108</li>
      </ul>
    </dd>
    <main>
      <section class="section" data-name="kap16">
        <article class="legalArticle" data-name="§16-3">
          <article class="defaultP">1. I lov 13. august 1915 nr. 5 om domstolene gjøres følgende endringer:</article>
          <article class="defaultP">§ 2 skal lyde:</article>
          <article class="futureLegalArticle" data-name="§2">
            <article class="futureLegalArticleHeader">§ 2.</article>
            <article class="legalP">Annan lov.</article>
          </article>
          <article class="defaultP">26. I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
          <article class="defaultP">Ny § 6 a skal lyde:</article>
          <article class="futureLegalArticle" data-name="§6a">
            <article class="futureLegalArticleHeader">§ 6 a.</article>
            <article class="legalP">Ny operativ regel.</article>
          </article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2016-05-27-14")

    assert len(ops) == 2
    assert [op.target.path for op in ops] == [
        (("section", "2"),),
        (("section", "6a"),),
    ]
    assert {op.source.title for op in ops if op.source is not None} == {
        "no/lov/1915-08-13-5",
        "no/lov/2003-12-12-108",
    }


def test_parse_no_amendment_ops_unstructured_supports_heading_repeal_range_and_repeal_renumber() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kap16">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
        <article class="defaultP">§ 6 overskriften skal lyde:</article>
        <article class="legalP">Beløpsgrenser og tidfesting</article>
        <article class="defaultP">§ 6 første ledd oppheves. Nåværende annet ledd blir første ledd.</article>
        <article class="defaultP">§ 7 oppheves.</article>
        <article class="defaultP">§§ 13 til 15 oppheves.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2016-05-27-14")

    assert [(op.action, op.target.path, op.destination.path if op.destination else None) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "6"),), None),
        (StructuralAction.REPEAL, (("section", "6"), ("subsection", "1")), None),
        (StructuralAction.RENUMBER, (("section", "6"), ("subsection", "2")), (("section", "6"), ("subsection", "1"))),
        (StructuralAction.REPEAL, (("section", "7"),), None),
        (StructuralAction.REPEAL, (("section", "13"),), None),
        (StructuralAction.REPEAL, (("section", "14"),), None),
        (StructuralAction.REPEAL, (("section", "15"),), None),
    ]
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SECTION
    assert ops[0].payload.children[0].kind is IRNodeKind.HEADING
    assert ops[0].payload.children[0].text == "Beløpsgrenser og tidfesting"


def test_iter_no_document_change_ops_unstructured_records_renumber_arity_mismatch() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kap16">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
        <article class="defaultP">§ 6 første ledd oppheves. Nåværende annet og tredje ledd blir første ledd.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = dict(
        iter_no_document_change_ops(
            amendment_xml,
            "no/lovtid/2016-05-27-14",
            adjudications_out=adjudications,
        )
    )

    ops = grouped["no/lov/2003-12-12-108"]
    assert [(op.action, op.target.path, op.destination.path if op.destination else None) for op in ops] == [
        (StructuralAction.REPEAL, (("section", "6"), ("subsection", "1")), None),
        (
            StructuralAction.RENUMBER,
            (("section", "6"), ("subsection", "2")),
            (("section", "6"), ("subsection", "1")),
        ),
    ]
    assert [item.kind for item in adjudications] == [
        "no_parse_unstructured_renumber_arity_mismatch_skipped"
    ]
    adjudication = adjudications[0]
    assert adjudication.detail["rule_id"] == "no_parse_unstructured_renumber_arity_mismatch_skipped"
    assert adjudication.detail["phase"] == "parse"
    assert adjudication.detail["family"] == "unsupported_or_unresolved_action"
    assert adjudication.detail["blocking"] is True
    assert adjudication.detail["strict_disposition"] == "block"
    assert adjudication.detail["quirks_disposition"] == "record"
    assert adjudication.detail["source_count"] == 2
    assert adjudication.detail["destination_count"] == 1
    assert adjudication.detail["paired_count"] == 1
    assert adjudication.detail["unmatched_source_targets"] == ("section:6/subsection:3",)
    assert adjudication.detail["unmatched_destination_targets"] == ()


def _no_unstructured_repeal_shift_ops(lead: str) -> list[tuple[object, tuple, tuple | None]]:
    """Lower ONE unstructured lead against a fixed base act, ops only."""
    amendment_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kap16">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
        <article class="defaultP">{lead}</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2016-05-27-14")
    return [(op.action, op.target.path, op.destination.path if op.destination else None) for op in ops]


def test_no_unstructured_repeal_shift_lead_admits_the_qualifier_variants() -> None:
    """W-61. The shipped production required the literal ``Nåværende`` in the
    shift sentence; 24 corpus leads spell it otherwise or not at all.

    The named witness is the last line: ``no/lovtid/2008-12-12-100``'s § 8-2
    repeal, which W-58 recorded as a missing archive artifact and W-60 as a
    run-on part boundary. It was neither — the sentence is archived, indexed and
    applied, and simply did not lower.
    """
    bare = [
        (StructuralAction.REPEAL, (("section", "6"), ("subsection", "1")), None),
        (StructuralAction.RENUMBER, (("section", "6"), ("subsection", "2")), (("section", "6"), ("subsection", "1"))),
    ]
    # No qualifier at all.
    assert _no_unstructured_repeal_shift_ops("§ 6 første ledd oppheves. Annet ledd blir første ledd.") == bare
    # The currency spellings that carry no address information.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Gjeldende annet ledd blir første ledd."
    ) == bare
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Någjeldende annet ledd blir nytt første ledd."
    ) == bare
    # The shift sentence may repeat its OWN section, as long as it is the same one.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. § 6 nåværende annet ledd blir første ledd."
    ) == bare
    # A letter-suffixed section resolves whole (W-32(c)'s class), instead of
    # cutting off at the digits and absorbing the letter into the ordinal phrase.
    assert _no_unstructured_repeal_shift_ops("§ 6 a første ledd oppheves. Annet ledd blir første ledd.") == [
        (StructuralAction.REPEAL, (("section", "6a"), ("subsection", "1")), None),
        (
            StructuralAction.RENUMBER,
            (("section", "6a"), ("subsection", "2")),
            (("section", "6a"), ("subsection", "1")),
        ),
    ]
    # ``til`` RANGES on either side — the shipped ``skal lyde`` round-trip
    # resolved these to NO targets at all, which is why the witness needed the
    # widening twice over.
    assert _no_unstructured_repeal_shift_ops(
        "§ 8-2 første ledd oppheves. Annet til femte ledd blir første til fjerde ledd."
    ) == [
        (StructuralAction.REPEAL, (("section", "8-2"), ("subsection", "1")), None),
        *(
            (
                StructuralAction.RENUMBER,
                (("section", "8-2"), ("subsection", str(src))),
                (("section", "8-2"), ("subsection", str(src - 1))),
            )
            for src in (2, 3, 4, 5)
        ),
    ]


def test_no_unstructured_repeal_shift_lead_refuses_what_it_cannot_account_for() -> None:
    """W-61's polarity: a lead this production cannot fully own lowers NOTHING.

    Each case below is a real corpus shape, and each stays on
    ``no_parse_unstructured_lead_unmatched`` rather than lowering a partial or
    mis-anchored answer.
    """
    # A trailing clause the shift does not account for — every one of the 19
    # corpus leads in this bucket introduces a PAYLOAD, so lowering the shift
    # alone would state a half-truth.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Nåværende annet ledd blir første ledd og skal lyde:"
    ) == []
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Annet ledd blir første ledd. Tredje ledd skal lyde:"
    ) == []
    # The shift sentence names a DIFFERENT section than the one repealed: this
    # production speaks for one section, so it speaks for neither.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. § 7 annet ledd blir første ledd."
    ) == []
    # A multi-section repeal list ("§ 4 femte ledd, § 5 annet ledd og § 6 annet
    # ledd oppheves.") — the embedded citations are not ordinals, so the phrase
    # is refused rather than silently attributed to the first section.
    assert _no_unstructured_repeal_shift_ops(
        "§ 4 femte ledd, § 5 annet ledd og § 6 annet ledd oppheves. § 5 tredje ledd blir nytt annet ledd."
    ) == []
    # An ordinal outside ``_NORWEGIAN_ORDINALS`` refuses the whole lead.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Ellevte ledd blir tiende ledd."
    ) == []


def test_no_unstructured_repeal_shift_widening_leaves_the_shipped_form_alone() -> None:
    """W-61 is strictly additive: the shipped ``Nåværende`` pattern is tried
    FIRST and byte-for-byte, so no lead that lowered before lowers differently.

    A first cut that replaced the production outright regressed 14 corpus leads.
    The two below are that regression's two shapes, and both must keep their
    SHIPPED answer — a partial lowering — rather than the widened pattern's
    all-or-nothing refusal.
    """
    # Qualifier BEFORE the section. The widened pattern reads the two in the
    # other order and would refuse; the shipped one lowers.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Nåværende § 6 annet ledd blir første ledd."
    ) == [(StructuralAction.REPEAL, (("section", "6"), ("subsection", "1")), None)]
    # Vocabulary the ordinal map does not carry ("henholdsvis"): the shipped
    # round-trip resolves an empty destination list and lowers the repeal plus an
    # arity receipt, which is a pin (8 corpus-wide) this widening must not move.
    assert _no_unstructured_repeal_shift_ops(
        "§ 6 første ledd oppheves. Nåværende annet og tredje ledd blir henholdsvis første og annet ledd."
    ) == [(StructuralAction.REPEAL, (("section", "6"), ("subsection", "1")), None)]


def test_apply_no_ops_supports_global_text_replace() -> None:
    statute = parse_no_statute(_STATUTE_XML, "no/lov/2025-01-01-1")
    chapter = statute.body.children[0]
    section = chapter.children[1]
    sentence = section.children[1]
    section_children = list(section.children)
    section_children[1] = replace(sentence, text="Skole etter friskolelova.")
    chapter_children = list(chapter.children)
    chapter_children[1] = replace(section, children=section_children)
    body_children = list(statute.body.children)
    body_children[0] = replace(chapter, children=chapter_children)
    statute = replace(statute, body=replace(statute.body, children=body_children))

    ops = [
        LegalOperation(
            op_id="no/lovtid/2022-06-10-39:1",
            sequence=1,
            action=StructuralAction.TEXT_PATCH,
            target=LegalAddress(path=()),
            text_patch=TextPatchSpec(
                kind=TextPatchKindEnum.REPLACE,
                selector=TextSelector(match_text="friskolelova", occurrence=0),
                replacement="privatskolelova",
            ),
            source=OperationSource(statute_id="no/lovtid/2022-06-10-39", raw_text="generic replace"),
        )
    ]

    updated = apply_no_ops(statute, ops)

    section = updated.body.children[0].children[1]
    assert section.children[1].text == "Skole etter privatskolelova."


def test_apply_no_ops_supports_typed_text_patch() -> None:
    statute = parse_no_statute(_STATUTE_XML, "no/lov/2025-01-01-1")
    chapter = statute.body.children[0]
    section = chapter.children[1]
    sentence = section.children[1]
    section_children = list(section.children)
    section_children[1] = replace(sentence, text="Skole etter friskolelova.")
    chapter_children = list(chapter.children)
    chapter_children[1] = replace(section, children=section_children)
    body_children = list(statute.body.children)
    body_children[0] = replace(chapter, children=chapter_children)
    statute = replace(statute, body=replace(statute.body, children=body_children))

    ops = [
        LegalOperation(
            op_id="no/lovtid/2022-06-10-39:1",
            sequence=1,
            action=StructuralAction.TEXT_PATCH,
            target=LegalAddress(path=()),
            text_patch=TextPatchSpec(
                kind=TextPatchKindEnum.REPLACE,
                selector=TextSelector(match_text="friskolelova", occurrence=0),
                replacement="privatskolelova",
            ),
            source=OperationSource(statute_id="no/lovtid/2022-06-10-39", raw_text="typed replace"),
        )
    ]

    updated = apply_no_ops(statute, ops)

    section = updated.body.children[0].children[1]
    assert section.children[1].text == "Skole etter privatskolelova."


def test_parse_no_amendment_ops_unstructured_supports_embedded_multi_act_lead() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/2004-12-17-99</li>
        <li>lov/2009-06-19-58</li>
      </ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="legalP">
          206. I lov 17. desember 2004 nr. 99 om kvoteplikt og handel med kvoter for utslipp av klimagasser (klimakvoteloven) skal § 21 nytt annet punktum lyde:
        </article>
        <article class="legalP">Medvirkning straffes ikke.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = iter_no_document_change_ops(amendment_xml, "no/lovtid/2015-06-19-65")

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2004-12-17-99"
    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            StructuralAction.INSERT,
            (("section", "21"), ("sentence", "2")),
            "Medvirkning straffes ikke.",
        ),
    ]


def test_no_unstructured_lead_looks_operative_tolerates_multiple_intervening_tokens() -> None:
    # Single-token framing (already covered) and multi-token chapter-scoped
    # framing must both register as operative so they are honestly adjudicated
    # rather than silently treated as inert prose.
    assert _no_unstructured_lead_looks_operative("§ 12 a skal lyde:")
    assert _no_unstructured_lead_looks_operative("skal ny § 12 a lyde:")
    assert _no_unstructured_lead_looks_operative("I kapittel I skal ny § 4 a lyde:")
    assert _no_unstructured_lead_looks_operative("I kapittel III skal ny § 16-2 lyde:")
    # Nynorsk action verbs are recognized.
    assert _no_unstructured_lead_looks_operative("§ 5 vert gjort gjeldande.")
    assert _no_unstructured_lead_looks_operative("§ 5 opphevast.")
    # Inert prose stays inert.
    assert not _no_unstructured_lead_looks_operative("Loven trer i kraft fra den tid Kongen bestemmer.")


def test_normalize_no_chapter_scoped_section_lead_rewrites_to_canonical_form() -> None:
    assert (
        _normalize_no_chapter_scoped_section_lead("I kapittel I skal ny § 4 a lyde:")
        == "Ny § 4 a skal lyde:"
    )
    assert (
        _normalize_no_chapter_scoped_section_lead("I kapittel III skal ny § 16-2 lyde: Foo bar.")
        == "Ny § 16-2 skal lyde: Foo bar."
    )
    # A bare (non-insert) chapter-scoped replace drops the chapter scope too.
    assert (
        _normalize_no_chapter_scoped_section_lead("I kapittel 5 skal § 25 lyde:")
        == "§ 25 skal lyde:"
    )
    # Leads that are not chapter-scoped whole-section leads are untouched.
    assert (
        _normalize_no_chapter_scoped_section_lead("§ 3 bokstav b skal lyde:")
        == "§ 3 bokstav b skal lyde:"
    )


def test_iter_no_document_change_ops_unstructured_supports_chapter_scoped_new_section_insert() -> None:
    # "I kapittel <X> skal ny § <Y> lyde:" carries a whole-section insert whose
    # chapter scope is redundant (Norwegian section numbering is act-global). The
    # base resolves from the preceding "I lov ... gjøres følgende endring:"
    # preamble; the chapter-scoped lead must lower to a section INSERT.
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1991-11-08-76</li></ul></dd>
    <main>
      <section data-name="kapI">
        <h2>I</h2>
        <article class="defaultP">I lov 8. november 1991 nr. 76 om kommunale eldreråd gjøres følgende endringer:</article>
        <article class="defaultP">I kapittel I skal ny § 4 a lyde:</article>
        <article class="futureLegalArticle" data-name="§4a">
          <span class="futureLegalArticleHeader">§ 4 a. Felles råd</span>
          <article class="legalP">Kommunane kan vedta å opprette felles råd.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2005-06-17-58"))

    assert "no/lov/1991-11-08-76" in grouped
    ops = grouped["no/lov/1991-11-08-76"]
    assert [(op.action, op.target.path, op.payload.kind if op.payload else None) for op in ops] == [
        (StructuralAction.INSERT, (("section", "4a"),), IRNodeKind.SECTION),
    ]
    assert ops[0].payload is not None
    body_texts = [child.text for child in ops[0].payload.children if child.kind is IRNodeKind.SUBSECTION]
    assert "Kommunane kan vedta å opprette felles råd." in body_texts


def test_iter_no_document_change_ops_unstructured_lov_preamble_plus_section_lowers() -> None:
    # "I lov ... gjøres følgende endring:" preamble resolves the base, and the
    # following whole-section "§ X skal lyde:" lead is lowered as a REPLACE op.
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1975-06-13-35</li></ul></dd>
    <main>
      <section data-name="kapI">
        <h2>I</h2>
        <article class="defaultP">I lov 13. juni 1975 nr. 35 om skattlegging gjøres følgende endring:</article>
        <article class="defaultP">§ 3 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§3">
          <span class="futureLegalArticleHeader">§ 3. Avskrivning</span>
          <article class="legalP">Utgifter kan avskrivast.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2002-06-28-48"))

    assert "no/lov/1975-06-13-35" in grouped
    ops = grouped["no/lov/1975-06-13-35"]
    assert [(op.action, op.target.path, op.payload.kind if op.payload else None) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "3"),), IRNodeKind.SECTION),
    ]


def test_iter_no_document_change_ops_unstructured_chapter_scoped_nynorsk_preamble() -> None:
    # Nynorsk "gjer ... følgjande endringar:" preamble plus a nynorsk-spelled
    # chapter-scoped section insert.
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nn">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1991-11-08-76</li></ul></dd>
    <main>
      <section data-name="kapII">
        <h2>II</h2>
        <article class="defaultP">I lov 8. november 1991 nr. 76 om kommunale eldreråd vert det gjort følgjande endringar:</article>
        <article class="defaultP">I kapittel II skal ny § 8 a lyde:</article>
        <article class="futureLegalArticle" data-name="§8a">
          <span class="futureLegalArticleHeader">§ 8 a. Felles råd</span>
          <article class="legalP">Fylkeskommunane kan vedta å opprette felles råd.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2005-06-17-58"))

    assert "no/lov/1991-11-08-76" in grouped
    ops = grouped["no/lov/1991-11-08-76"]
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.INSERT, (("section", "8a"),)),
    ]


def test_iter_no_document_change_ops_unstructured_chapter_scoped_lead_without_base_still_drops() -> None:
    # An operative chapter-scoped lead with no resolvable base act must not guess
    # a target; it drops honestly as a typed adjudication.
    # Two changed docs means there is no single default base, and the operative
    # chapter-scoped lead carries no embedded citation of its own, so the base
    # stays unresolved.
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1991-11-08-76</li><li>lov/2005-06-17-62</li></ul></dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">I kapittel I skal ny § 4 a lyde:</article>
        <article class="legalP">Kommunane kan vedta å opprette felles råd.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2005-06-17-58",
        adjudications_out=adjudications,
    )

    assert grouped == []
    assert "no_parse_unstructured_lead_base_unresolved" in {item.kind for item in adjudications}


def test_iter_no_document_change_ops_unstructured_supports_section_scoped_base_lead() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/2005-12-21-124</li>
        <li>lov/2005-06-17-62</li>
      </ul>
    </dd>
    <main>
      <section data-name="kapI">
        <h2>I</h2>
        <article class="defaultP">I lov 17. juni 2005 nr. 62 om arbeidsmiljø, arbeidstid og stillingsvern mv. gjøres følgende endring:</article>
        <article class="defaultP">§ 18-1 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§18-1">
          <span class="futureLegalArticleHeader">§ 18-1. Tilsyn</span>
          <article class="legalP">Arbeidstilsynet fører tilsyn.</article>
        </article>
      </section>
      <section data-name="kapII">
        <h2>II</h2>
        <article class="defaultP">I lov 21. desember 2005 nr. 124 om obligatorisk tjenestepensjon gjøres følgende endringer:</article>
        <article class="defaultP">§ 8 nytt annet ledd skal lyde:</article>
        <article class="numberedLegalP" data-numerator="2">(2) Departementet kan gi forskrift om nivået på og utmåling av tvangsmulkten.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2020-12-21-167"))

    assert "no/lov/2005-12-21-124" in grouped
    ops = grouped["no/lov/2005-12-21-124"]
    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            StructuralAction.INSERT,
            (("section", "8"), ("subsection", "2")),
            "Departementet kan gi forskrift om nivået på og utmåling av tvangsmulkten.",
        ),
    ]


def test_iter_no_document_change_ops_unstructured_supports_named_law_section_intro() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/1993-06-11-100</li>
        <li>lov/2005-06-03-34</li>
      </ul>
    </dd>
    <main>
      <section data-name="kapI">
        <h2>I</h2>
        <article class="legalP">I jernbaneundersøkelsesloven av 3. juni 2005 nr. 34 gjøres følgende endring:</article>
        <article class="defaultP">Ny § 8 a skal lyde:</article>
        <article class="futureLegalArticle" data-name="§8a">
          <span class="futureLegalArticleHeader">§ 8 a. Taushetsplikt</span>
          <article class="legalP">Enhver har taushetsplikt.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2016-12-16-102"))

    assert "no/lov/2005-06-03-34" in grouped
    ops = grouped["no/lov/2005-06-03-34"]
    assert [(op.action, op.target.path, op.payload.kind if op.payload else None) for op in ops] == [
        (StructuralAction.INSERT, (("section", "8a"),), IRNodeKind.SECTION),
    ]


def test_iter_no_document_change_ops_unstructured_supports_direct_section_lead_with_base() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/1993-06-11-100</li>
        <li>lov/2005-06-03-34</li>
      </ul>
    </dd>
    <main>
      <section data-name="kapII">
        <h2>II</h2>
        <article class="defaultP">I lov 3. juni 2005 nr. 34 om varsling, rapportering og undersøkelse av jernbaneulykker og jernbanehendelser m.m. skal § 13 lyde:</article>
        <article class="futureLegalArticle" data-name="§13">
          <span class="futureLegalArticleHeader">§ 13. Tiltak</span>
          <article class="legalP">Undersøkelsesmyndigheten kan kreve hjelp av politiet.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2021-06-11-87"))

    assert "no/lov/2005-06-03-34" in grouped
    ops = grouped["no/lov/2005-06-03-34"]
    assert [(op.action, op.target.path, op.payload.kind if op.payload else None) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "13"),), IRNodeKind.SECTION),
    ]


def test_iter_no_document_change_ops_unstructured_multi_part_binds_each_part_to_its_own_law() -> None:
    """W-15: a ``<section>`` part binds its ops to the law ITS OWN lead resolves.

    Shape of the corpus witness ``no/lovtid/2019-06-21-57``: several parts, each
    opening with a ``legalP`` law-switch lead, each part's last lead carrying a
    ``legalP`` payload. Before the fix, the payload scan after part I's last
    ``defaultP`` lead ran past the ``</section>`` to the next ``defaultP``,
    swallowing part II's law-switch lead so it was never processed as a lead;
    the stale ``active_base_id`` from part I then outranked the (correctly
    resolved) part base id, and part II's ops landed on part I's law.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments">
      <ul>
        <li>lov/2017-06-16-51</li>
        <li>lov/1997-06-13-55</li>
      </ul>
    </dd>
    <main>
      <section data-name="kapI">
        <h2>I</h2>
        <article class="legalP">I lov 16. juni 2017 nr. 51 om likestilling og forbud mot diskriminering gjøres følgende endringer:</article>
        <article class="defaultP">§ 13 sjette ledd skal lyde:</article>
        <article class="legalP">Arbeidsgivere skal forebygge trakassering.</article>
      </section>
      <section data-name="kapII">
        <h2>II</h2>
        <article class="legalP">I lov av 13. juni 1997 nr. 55 om serveringsvirksomhet (serveringsloven) gjøres følgende endringer:</article>
        <article class="defaultP">§ 6 første ledd skal lyde:</article>
        <article class="legalP">Bevillingshaver og daglig leder må ha utvist uklanderlig vandel.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2019-06-21-57"))

    assert sorted(grouped) == ["no/lov/1997-06-13-55", "no/lov/2017-06-16-51"]
    assert [(op.target.path, op.payload.text if op.payload else None) for op in grouped["no/lov/2017-06-16-51"]] == [
        ((("section", "13"), ("subsection", "6")), "Arbeidsgivere skal forebygge trakassering."),
    ]
    # The op the defect misfiled: § 6 belongs to serveringsloven, not to the
    # anti-discrimination act that part I amended.
    assert [(op.target.path, op.payload.text if op.payload else None) for op in grouped["no/lov/1997-06-13-55"]] == [
        ((("section", "6"), ("subsection", "1")), "Bevillingshaver og daglig leder må ha utvist uklanderlig vandel."),
    ]


def test_iter_no_document_change_ops_unstructured_payload_stops_at_part_boundary() -> None:
    """W-15: a commencement part is never absorbed as the previous part's payload.

    Shape of ``no/lovtid/2018-12-20-119``: one amending part whose payload is a
    ``futureLegalArticle`` (which the subsection family does not accept as a
    text article), followed by a commencement part. Before the fix the payload
    scan crossed the boundary and the commencement sentence became the new text
    of § 28 first subsection.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1978-06-09-50</li></ul></dd>
    <main>
      <section data-name="kapI">
        <h2>I</h2>
        <article class="legalP">I lov 9. juni 1978 nr. 50 om kulturminner blir følgjande endring gjort:</article>
        <article class="defaultP">§ 28 første ledd skal lyde:</article>
        <article class="futureLegalArticle" data-name="§28">
          <span class="futureLegalArticleHeader">§ 28. Rette myndighet etter loven</span>
        </article>
      </section>
      <section data-name="kapII">
        <h2>II</h2>
        <article class="legalP">Lova tek til å gjelde straks.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2018-12-20-119"))

    payload_texts = [op.payload.text for ops in grouped.values() for op in ops if op.payload is not None]
    assert "Lova tek til å gjelde straks." not in payload_texts
    assert grouped == {}


def test_parse_no_amendment_ops_unstructured_supports_plural_section_repeal() -> None:
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/2004-12-17-99</li></ul></dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§§ 8a og 8b oppheves.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2012-05-25-29")

    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPEAL, (("section", "8a"),)),
        (StructuralAction.REPEAL, (("section", "8b"),)),
    ]


def test_parse_no_statute_recurses_part_chapter_section_structure() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <head><title>Nested testlov</title></head>
  <body>
    <main class="documentBody">
      <section class="section" data-name="del1" data-lovdata-URL="NL/lov/2025-01-01-1/KAPITTEL_1">
        <h2>Første del</h2>
        <section class="section" data-name="kap2" data-lovdata-URL="NL/lov/2025-01-01-1/KAPITTEL_1-2">
          <h3>Kapittel 2</h3>
          <article class="legalArticle" data-name="§7">
            <h4 class="legalArticleHeader">§ 7. Tittel</h4>
            <article class="legalP">Innhold.</article>
          </article>
        </section>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    statute = parse_no_statute(xml, "no/lov/2025-01-01-1")

    assert [child.kind for child in statute.body.children] == [IRNodeKind.PART]
    part = statute.body.children[0]
    assert part.label == "1"
    chapter = next(child for child in part.children if child.kind is IRNodeKind.CHAPTER)
    assert chapter.label == "2"
    section = next(child for child in chapter.children if child.kind is IRNodeKind.SECTION)
    assert section.label == "7"


def test_parse_no_amendment_ops_uses_lovdata_change_attributes() -> None:
    ops = parse_no_amendment_ops(_AMENDMENT_XML, "no/lovtid/2025-02-02-5")

    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "2"), ("item", "1"))),
        (StructuralAction.INSERT, (("section", "2"), ("item", "3"))),
        (StructuralAction.REPEAL, (("section", "1"),)),
    ]
    assert ops[0].payload is not None
    assert ops[0].payload.label == "1"
    assert ops[1].payload is not None
    assert ops[1].payload.label == "3"
    assert ops[2].payload is None


def test_parse_no_amendment_ops_supports_future_legal_article_payloads() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change" data-change-part="lov/2025-01-01-1/§2">
        <article class="defaultP">§ 2 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§2">
          <span class="futureLegalArticleHeader">
            <span class="legalArticleValue">§ 2</span>.
            <span class="legalArticleTitle">Nytt krav</span>
          </span>
          <article class="legalP">Oppdatert paragraftekst.</article>
        </article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-03-03-7")

    assert len(ops) == 1
    assert ops[0].target.path == (("section", "2"),)
    assert ops[0].payload is not None
    assert ops[0].payload.label == "2"
    assert ops[0].payload.children[0].kind is IRNodeKind.HEADING


def test_parse_no_amendment_ops_indexes_nested_item_payload_for_structured_target() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change" data-change-part="lov/2024-01-12-1/§7-1/ledd/1/bokstav/b/nummer/2">
        <article class="defaultP">§ 7-1 fyrste ledd bokstav b nr. 2 skal lyde:</article>
        <li class="consolidationElement">
          <article class="listArticle">
            <ul class="defaultList">
              <li data-li-identifier="2." data-name="2.">
                <article class="listArticle">
                  <article class="legalP">har en direkte eierinteresse som gir rett til maksimalt 5 prosent.</article>
                </article>
              </li>
            </ul>
          </article>
        </li>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2024-06-25-66")

    assert len(ops) == 1
    assert ops[0].target.path == (
        ("section", "7-1"),
        ("subsection", "1"),
        ("item", "b"),
        ("item", "2"),
    )
    assert ops[0].payload is not None
    assert ops[0].payload.text == "har en direkte eierinteresse som gir rett til maksimalt 5 prosent."


def test_parse_no_amendment_ops_parses_section_heading_only_replace_without_dropping_section_shape() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change" data-change-part="lov/2024-01-12-1/§2-4">
        <article class="defaultP">Overskriften til § 2-4 skal lyde:</article>
        <article class="defaultP"><i>Fordeling av suppleringsskatt etter skatteinkluderingsregelen</i></article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2024-12-20-92")

    assert len(ops) == 1
    assert ops[0].action is StructuralAction.REPLACE
    assert ops[0].target.path == (("section", "2-4"),)
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SECTION
    assert [(child.kind, child.text) for child in ops[0].payload.children] == [
        (IRNodeKind.HEADING, "Fordeling av suppleringsskatt etter skatteinkluderingsregelen"),
    ]


def test_iter_no_document_change_ops_finds_nested_change_blocks() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <section class="wrapper">
        <article class="change" data-change-part="lov/2025-01-01-1/§2/ledd/1">
          <article class="legalP">Oppdatert første ledd.</article>
        </article>
      </section>
    </article>
  </body>
</html>
""".encode("utf-8")

    grouped = iter_no_document_change_ops(xml, "no/lovtid/2025-03-03-7")

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2025-01-01-1"
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "2"), ("subsection", "1"))),
    ]
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SUBSECTION
    assert ops[0].payload.text == "Oppdatert første ledd."


def test_parse_and_apply_no_heading_groups_regroups_section_ranges_under_subchapter() -> None:
    statute = IRStatute(
        statute_id="no/lov/2024-01-12-1",
        title="Test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="I",
                    children=(IRNode(kind=IRNodeKind.HEADING, text="Del I"),
                        IRNode(
                            kind=IRNodeKind.CHAPTER,
                            label="2",
                            children=(IRNode(kind=IRNodeKind.HEADING, text="Kapittel 2"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-1", text="a"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-2", text="b"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-3", text="c"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-4", text="d"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-5", text="e"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-10", text="f"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-11", text="g"),
                                IRNode(kind=IRNodeKind.SECTION, label="2-20", text="h"),),
                        ),),
                ),),
        ),
    )
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="defaultP">Ny deloverskrift til §§ 2-1 til 2-5 skal lyde:</article>
      <span class="futuretitle">Skatteinkluderingsregelen</span>
      <article class="defaultP">Ny deloverskrift til nye §§ 2-10 til 2-14 skal lyde:</article>
      <span class="futuretitle">Skattefordelingsregelen</span>
      <article class="defaultP">Ny deloverskrift til ny § 2-20 skal lyde:</article>
      <span class="futuretitle">Nasjonal suppleringsskatt</span>
    </article>
  </body>
</html>
""".encode("utf-8")

    groups = parse_no_heading_groups(amendment_xml, "no/lov/2024-01-12-1")
    assert [(group.start_label, group.end_label, group.title) for group in groups] == [
        ("2-1", "2-5", "Skatteinkluderingsregelen"),
        ("2-10", "2-14", "Skattefordelingsregelen"),
        ("2-20", "2-20", "Nasjonal suppleringsskatt"),
    ]

    updated = apply_no_heading_groups(statute, groups)
    part = updated.body.children[0]
    chapter_2 = next(child for child in part.children if child.kind is IRNodeKind.CHAPTER and child.label == "2")
    assert [(child.kind, child.label) for child in chapter_2.children] == [
        (IRNodeKind.HEADING, None),
        (IRNodeKind.CHAPTER, "1-2-1"),
        (IRNodeKind.CHAPTER, "1-2-2"),
        (IRNodeKind.CHAPTER, "1-2-3"),
    ]
    group_121 = chapter_2.children[1]
    assert [child.label for child in group_121.children if child.kind is IRNodeKind.SECTION] == ["2-1", "2-2", "2-3", "2-4", "2-5"]
    group_122 = chapter_2.children[2]
    assert [child.label for child in group_122.children if child.kind is IRNodeKind.SECTION] == ["2-10", "2-11"]
    group_123 = chapter_2.children[3]
    assert [child.label for child in group_123.children if child.kind is IRNodeKind.SECTION] == ["2-20"]


def test_parse_no_amendment_ops_splits_multi_target_legalp_block_into_subsections() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2004-12-17-99">
      <article class="change"
               data-change-part="lov/2004-12-17-99/§3/ledd/1"
               data-add-new-part="lov/2004-12-17-99/§3/ledd/2">
        <article class="defaultP">§ 3 første og andre ledd skal lyde:</article>
        <article class="legalP">Første ledd tekst.</article>
        <article class="legalP">Andre ledd tekst.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-06-20-91")

    assert [(op.action, op.target.path, op.payload.label if op.payload else None, op.payload.text if op.payload else None) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "3"), ("subsection", "1")), "1", "Første ledd tekst."),
        (StructuralAction.INSERT, (("section", "3"), ("subsection", "2")), "2", "Andre ledd tekst."),
    ]


def test_parse_no_amendment_ops_splits_single_legalp_multi_sentence_payload_across_targets() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change"
               data-change-part="lov/2024-01-12-1/§3-2/ledd/8/setning/2 lov/2024-01-12-1/§3-2/ledd/8/setning/3">
        <article class="defaultP">§ 3-2 åttende ledd andre og tredje punktum skal lyde:</article>
        <article class="legalP">Valget er et femårsvalg. For det året valget tas eller oppheves, skal det gjøres korreksjoner.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-12-22-123")

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            StructuralAction.REPLACE,
            (("section", "3-2"), ("subsection", "8"), ("sentence", "2")),
            "Valget er et femårsvalg.",
        ),
        (
            StructuralAction.REPLACE,
            (("section", "3-2"), ("subsection", "8"), ("sentence", "3")),
            "For det året valget tas eller oppheves, skal det gjøres korreksjoner.",
        ),
    ]


def test_parse_no_amendment_ops_splits_single_legalp_sentence_payload_without_lead_tail() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change"
               data-change-part="lov/2024-01-12-1/§3-2/ledd/8/setning/2 lov/2024-01-12-1/§3-2/ledd/8/setning/3">
        <article class="legalP">Første nye punktum. Andre nye punktum.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-12-22-123")

    assert [(op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            (("section", "3-2"), ("subsection", "8"), ("sentence", "2")),
            "Første nye punktum.",
        ),
        (
            (("section", "3-2"), ("subsection", "8"), ("sentence", "3")),
            "Andre nye punktum.",
        ),
    ]


def test_parse_no_amendment_ops_inferrs_sentence_targets_from_structured_subsection_lead() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change"
               data-change-part="lov/2022-05-12-28/§45/ledd/2"
               data-add-new-part="lov/2022-05-12-28/§45/ledd/3 lov/2022-05-12-28/§45/ledd/4">
        <article class="defaultP">§ 45 andre ledd nytt tredje og fjerde punktum skal lyde:</article>
        <article class="legalP">Advokattilsynet kan kreve refusjon. Kravet er tvangsgrunnlag for utlegg.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2024-06-21-46")

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            StructuralAction.INSERT,
            (("section", "45"), ("subsection", "2"), ("sentence", "3")),
            "Advokattilsynet kan kreve refusjon.",
        ),
        (
            StructuralAction.INSERT,
            (("section", "45"), ("subsection", "2"), ("sentence", "4")),
            "Kravet er tvangsgrunnlag for utlegg.",
        ),
    ]


def test_split_no_sentences_does_not_split_after_numeric_day_marker() -> None:
    assert _split_no_sentences(
        "Dersom den kvotepliktige ikke innen 1. juni året etter at oppgjøret skulle ha funnet sted."
    ) == [
        "Dersom den kvotepliktige ikke innen 1. juni året etter at oppgjøret skulle ha funnet sted."
    ]


def test_split_no_sentences_still_splits_after_section_citation() -> None:
    assert _split_no_sentences(
        "Klimakvotemyndigheten skal kontrollere rapportering etter § 14. Kongen kan gi forskrift."
    ) == [
        "Klimakvotemyndigheten skal kontrollere rapportering etter § 14.",
        "Kongen kan gi forskrift.",
    ]


def test_split_no_sentences_does_not_split_after_jfr_abbreviation() -> None:
    """W-19 casualty 1: ``no/lovtid/2021-12-22-166`` § 25 first subsection.

    The lead declares two target sentences ("annet og tredje punktum"); the
    unknown ``jfr.`` split the single payload into three, so the family's
    all-or-nothing arity check emitted nothing.
    """
    assert _split_no_sentences(
        "For forkynnelse av betalingsoppfordring etter konkursloven 8 juni 1984 nr. 58 § 63 "
        "betales likevel 0,4 ganger rettsgebyret. For forkynnelse ved stevnevitne i andre "
        "tilfelle enn nevnt i første, jfr. annet punktum, betales halvparten av rettsgebyret."
    ) == [
        "For forkynnelse av betalingsoppfordring etter konkursloven 8 juni 1984 nr. 58 § 63 "
        "betales likevel 0,4 ganger rettsgebyret.",
        "For forkynnelse ved stevnevitne i andre tilfelle enn nevnt i første, jfr. annet "
        "punktum, betales halvparten av rettsgebyret.",
    ]


def test_split_no_sentences_does_not_split_after_mm_abbreviation() -> None:
    """W-19 casualty 2: ``no/lovtid/2016-12-16-91`` § 7 first subsection.

    This is the one genuine binding W-15 lost: the finanstilsynsloven
    (``no/lov/1956-12-07-1``) sentences 3 and 4. ``m.m.`` in the cited
    børsvirksomhet act's title split the second sentence in two.
    """
    assert _split_no_sentences(
        "Taushetsplikten etter denne bestemmelse gjelder ikke overfor Norges Bank. "
        "Taushetsplikten er heller ikke til hinder for at Finanstilsynet gir opplysninger "
        "til børs med tillatelse etter lov 29. juni 2007 nr. 74 om børsvirksomhet m.m. § 4, "
        "verdipapirregister med tillatelse etter lov 5. juli 2002 nr. 64 § 3-1."
    ) == [
        "Taushetsplikten etter denne bestemmelse gjelder ikke overfor Norges Bank.",
        "Taushetsplikten er heller ikke til hinder for at Finanstilsynet gir opplysninger "
        "til børs med tillatelse etter lov 29. juni 2007 nr. 74 om børsvirksomhet m.m. § 4, "
        "verdipapirregister med tillatelse etter lov 5. juli 2002 nr. 64 § 3-1.",
    ]


def test_split_no_sentences_does_not_split_after_iht_abbreviation() -> None:
    """W-19 casualty 3: ``no/lovtid/2022-02-18-5`` § 19-7 third subsection.

    Found by the corpus sweep, not named in the ledger: ``iht.`` is the only
    other abbreviation form that breaks an arity check corpus-wide.
    """
    assert _split_no_sentences(
        "Retten til å fortsette forsikringsforholdet etter første ledd gjelder tilsvarende "
        "for arbeidstaker som er medlem av pensjonsordning under permittering iht. "
        "innskuddspensjonsloven § 4-3 fjerde ledd. Forsikringsforetaket skal sende melding "
        "som nevnt i første ledd tredje punktum til medlemmene."
    ) == [
        "Retten til å fortsette forsikringsforholdet etter første ledd gjelder tilsvarende "
        "for arbeidstaker som er medlem av pensjonsordning under permittering iht. "
        "innskuddspensjonsloven § 4-3 fjerde ledd.",
        "Forsikringsforetaket skal sende melding som nevnt i første ledd tredje punktum til "
        "medlemmene.",
    ]


def test_split_no_sentences_still_splits_after_letter_item_label() -> None:
    """W-19 guard: bare item letters DO end sentences, so they stay out of the set.

    ``no/lovtid/2016-12-16-91`` § 11-15 relies on this: a two-target lead whose
    first sentence ends "... bokstav e." Admitting single-letter abbreviations
    to recover ``m.m.`` would have flipped this correct split to wrong.
    """
    assert _split_no_sentences(
        "Kongen kan gjøre unntak for fordringer som nevnt i § 11-8 første ledd bokstav e. "
        "Slike forskrifter kan fravike reglene i kapittel 11 II."
    ) == [
        "Kongen kan gjøre unntak for fordringer som nevnt i § 11-8 første ledd bokstav e.",
        "Slike forskrifter kan fravike reglene i kapittel 11 II.",
    ]


def test_split_no_sentences_does_not_split_after_punctuated_month_token() -> None:
    """W-22 witness: ``no/lovtid/2020-12-21-166`` § 10-20 first subsection.

    The lead declares two target sentences ("første og annet punktum"). The
    payload's instalment list carries a comma on two of its month tokens
    ("15. mars," / "15. juni,") and a period on the closing "15. juni.", and the
    day-number guard tested membership on the raw token, so it failed at all
    three — five fragments for two targets, and the all-or-nothing arity check
    emitted nothing. Text verbatim from the corpus.
    """
    assert _split_no_sentences(
        "Forskuddsskatt for personlige skattytere forfaller til betaling i fire like store "
        "terminer 15. mars, 15. juni, 15. september og 15. desember i inntektsåret. Er "
        "forskuddsskatten under 2 000 kroner, forfaller den i sin helhet til betaling 15. juni."
    ) == [
        "Forskuddsskatt for personlige skattytere forfaller til betaling i fire like store "
        "terminer 15. mars, 15. juni, 15. september og 15. desember i inntektsåret.",
        "Er forskuddsskatten under 2 000 kroner, forfaller den i sin helhet til betaling "
        "15. juni.",
    ]


def test_split_no_sentences_still_splits_after_sentence_final_month() -> None:
    """W-22 guard: a month token that genuinely ENDS a sentence still splits.

    Corpus counterexample — ``no/lov/1999-01-29-6`` § 27 fourth subsection, one
    of the 47 replay-side texts whose split the strip changes (7 -> 5). Two
    boundaries are repaired ("senest 31." | "mars." and "senest 15." | "mai."),
    but the three boundaries that follow a sentence-final "mars." / "februar
    året …" / "mai." must survive: the strip is applied to the token AFTER a
    candidate boundary, never to the token before it.
    """
    assert _split_no_sentences(
        "Daglig leder skal utarbeide årsregnskapet senest 22. februar året etter "
        "regnskapsåret. Styret skal avlegge årsregnskapet og årsberetningen senest 31. mars. "
        "Årsregnskapet og årsberetningen skal revideres av regnskapsrevisor. "
        "Revisjonsberetningen skal avgis til representantskapet med kopi til styret senest "
        "15. mai. Styret legger frem forslag til vedtak om årsregnskap og årsberetning for "
        "representantskapet."
    ) == [
        "Daglig leder skal utarbeide årsregnskapet senest 22. februar året etter "
        "regnskapsåret.",
        "Styret skal avlegge årsregnskapet og årsberetningen senest 31. mars.",
        "Årsregnskapet og årsberetningen skal revideres av regnskapsrevisor.",
        "Revisjonsberetningen skal avgis til representantskapet med kopi til styret senest "
        "15. mai.",
        "Styret legger frem forslag til vedtak om årsregnskap og årsberetning for "
        "representantskapet.",
    ]


def test_iter_no_document_change_ops_global_text_replace_falls_back_to_lead_base_id() -> None:
    """W-20: a citation-less global text-replace lead binds to its part's own law.

    The part announces its law once; the replace lead names only a section, so
    no citation can be harvested from lead or payload. Before the fallback the
    op was dropped outright.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="del1">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
        <article class="defaultP">I § 6 første ledd skal ordet «kompensasjon» erstattes med «refusjon».</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == ["no/lov/2003-12-12-108"]
    (op,) = grouped["no/lov/2003-12-12-108"]
    assert op.action is StructuralAction.TEXT_PATCH
    assert op.text_patch is not None
    assert op.text_patch.selector.match_text == "kompensasjon"
    assert op.text_patch.replacement == "refusjon"
    assert "base_act:no/lov/2003-12-12-108" in op.provenance_tags
    assert "scope:global" in op.provenance_tags


def test_iter_no_document_change_ops_global_text_replace_prefers_cited_law_over_lead_base() -> None:
    """W-20 guard: the fallback only fires when nothing was cited.

    An explicit citation in the replace lead still wins over the part's law, so
    the fallback cannot capture cross-act replaces that already bound correctly.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="del1">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
        <article class="defaultP">I lov 8. november 1991 nr. 76 om kommunale eldreråd § 2 skal ordet «kompensasjon» erstattes med «refusjon».</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == ["no/lov/1991-11-08-76"]


@pytest.mark.parametrize(
    "lead",
    [
        # The W-21 witness, verbatim from ``no/lovtid/2009-06-19-74`` part I.
        "Lov 20. mai 2005 nr. 28 om straff endres slik:",
        # The three other tail surfaces the 2026-08-06 corpus sweep found, all
        # nynorsk: ``no/lovtid/2002-12-20-104``, ``no/lovtid/2004-06-25-51``,
        # ``no/lovtid/2009-06-19-61`` (law citations swapped for the witness's
        # so the parametrization tests the tail, not the citation).
        "Lov 20. mai 2005 nr. 28 om straff vert endra slik:",
        "Lov 20. mai 2005 nr. 28 om straff blir endra slik:",
        "Lov 20. mai 2005 nr. 28 om straff blir endret slik:",
    ],
)
def test_no_law_announcement_lead_resolves_the_part_base_act(lead: str) -> None:
    """W-21: a nominative ``Lov <date> nr. N om X endres slik:`` part announcement.

    The older Lovtidend generation announces a part's base act without the
    ``I lov …`` preposition the other extractors require, so inference used to
    fall through to whatever consequential ``I lov …`` item appeared later in
    the part's payload.
    """
    assert _extract_no_law_announcement_base_id(lead) == "no/lov/2005-05-20-28"


@pytest.mark.parametrize(
    "lead",
    [
        # No amending tail: the part acts on the law as a whole and introduces
        # no items to bind (``no/lovtid/2005-12-21-131`` part I).
        "Lov 31. mai 1900 nr. 5 om Løsgjængeri, Betleri og Drukkenskab blir oppheva.",
        "Lov 17. juni 2005 nr. 103 om statens embets- og tjenestemenn oppheves.",
        # A bare title line, and a nested consequential repeal item.
        "Lov 13. august 1915 nr. 5 om domstolene",
        "1. Militær straffelov 22. mai 1902 nr. 13 § 107 oppheves.",
        # ``Lovens del …`` is a commencement clause, not an announcement
        # (``no/lovtid/2007-04-13-14`` part V).
        "Lovens del I-III trer i kraft straks. Del IV trer i kraft når lov 20. mai 2005 nr. 28 § 102 nr. 4 trer i kraft.",
        # The ``I lov …`` forms stay the other extractors' business.
        "I lov 13. juni 1975 nr. 39 om utlevering av lovbrytere mv. skal § 9 annet punktum lyde:",
    ],
)
def test_no_law_announcement_lead_requires_an_amending_tail(lead: str) -> None:
    """W-21 guard: naming a law is not announcing a part of amendments to it."""
    assert _extract_no_law_announcement_base_id(lead) is None


def test_iter_no_document_change_ops_law_announcement_outranks_nested_consequential_item() -> None:
    """W-21: the part announcement wins over an ``I lov …`` item in its payload.

    Reduced from ``no/lovtid/2009-06-19-74``, where the nested item sits inside
    the new § 412 "Endringer i andre lover" text. Without the announcement the
    § 5 op binds to the nested item's law.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2005-05-20-28</li><li>lov/1975-06-13-39</li></ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">Lov 20. mai 2005 nr. 28 om straff endres slik:</article>
        <article class="defaultP">§ 6 annet ledd skal lyde:</article>
        <article class="legalP">Straffelovgivningen gjelder også for handlinger som Norge har rett til å straffe etter overenskomst med fremmed stat.</article>
        <article class="defaultP">3. I lov 13. juni 1975 nr. 39 om utlevering av lovbrytere mv. skal § 9 annet punktum lyde:</article>
        <article class="legalP">Utlevering kan likevel skje dersom siktelsen gjelder folkemord.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == ["no/lov/1975-06-13-39", "no/lov/2005-05-20-28"]
    assert [op.target.path for op in grouped["no/lov/2005-05-20-28"]] == [
        (("section", "6"), ("subsection", "2"))
    ]
    # The nested item still binds to its own cited law.
    assert [op.target.path for op in grouped["no/lov/1975-06-13-39"]] == [
        (("section", "9"), ("sentence", "2"))
    ]


def test_parse_no_amendment_ops_recovers_malformed_cross_act_target_from_lead_text() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2004-12-17-99">
      <article class="change"
               data-change-part="lov/2004-12-17-99/§11/ledd/2 lov/1981-03-13-6/§11/ledd/3">
        <article class="defaultP">§ 11 andre og tredje ledd skal lyde:</article>
        <article class="legalP">Andre ledd tekst.</article>
        <article class="legalP">Tredje ledd tekst.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-06-20-91")

    assert len(ops) == 2
    assert ops[0].target.path == (("section", "11"), ("subsection", "2"))
    assert ops[0].payload is not None
    assert ops[0].payload.label == "2"
    assert ops[0].payload.text == "Andre ledd tekst."
    assert ops[1].target.path == (("section", "11"), ("subsection", "3"))
    assert ops[1].payload is not None
    assert ops[1].payload.label == "3"
    assert ops[1].payload.text == "Tredje ledd tekst."


def test_parse_no_amendment_ops_falls_back_to_unstructured_future_section_blocks() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <header>
      <dd class="changesToDocuments">
        <ul><li>lov/2004-12-17-99</li></ul>
      </dd>
    </header>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 9 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§9">
          <span class="futureLegalArticleHeader">
            <span class="legalArticleValue">§ 9</span>.
            <span class="legalArticleTitle">(salg av kvoter)</span>
          </span>
          <article class="legalP">Kongen kan gi nærmere bestemmelser om organiseringen og gjennomføringen av salg av kvoter.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2012-05-25-29")

    assert len(ops) == 1
    assert ops[0].action is StructuralAction.REPLACE
    assert ops[0].target.path == (("section", "9"),)
    assert ops[0].payload is not None
    assert ops[0].payload.kind is IRNodeKind.SECTION
    assert ops[0].payload.label == "9"
    assert [(child.kind, child.label, child.text) for child in ops[0].payload.children] == [
        (IRNodeKind.HEADING, None, "(salg av kvoter)"),
        (IRNodeKind.SUBSECTION, "1", "Kongen kan gi nærmere bestemmelser om organiseringen og gjennomføringen av salg av kvoter."),
    ]


def test_parse_no_amendment_ops_falls_back_to_unstructured_subsection_and_repeal_blocks() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <header>
      <dd class="changesToDocuments">
        <ul><li>lov/2004-12-17-99</li></ul>
      </dd>
    </header>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 11 andre og tredje ledd skal lyde:</article>
        <article class="legalP">Andre ledd tekst.</article>
        <article class="legalP">Tredje ledd tekst.</article>
        <article class="defaultP">§ 13 tredje ledd oppheves.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2012-05-25-29")

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "11"), ("subsection", "2")), "Andre ledd tekst."),
        (StructuralAction.REPLACE, (("section", "11"), ("subsection", "3")), "Tredje ledd tekst."),
        (StructuralAction.REPEAL, (("section", "13"), ("subsection", "3")), None),
    ]


def test_parse_no_amendment_ops_falls_back_to_unstructured_sentence_target_blocks() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="no">
  <body>
    <header>
      <dd class="changesToDocuments">
        <ul><li>lov/2017-06-16-60</li></ul>
      </dd>
    </header>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 4 annet ledd første punktum skal lyde:</article>
        <article class="legalP">Ved vurdering av om klimamålene for 2030 er nådd, skal det tas hensyn til effekten av norsk deltakelse i EUs klimakvotesystem for virksomheter.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2021-06-18-129")

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            StructuralAction.REPLACE,
            (("section", "4"), ("subsection", "2"), ("sentence", "1")),
            "Ved vurdering av om klimamålene for 2030 er nådd, skal det tas hensyn til effekten av norsk deltakelse i EUs klimakvotesystem for virksomheter.",
        ),
    ]


def test_iter_no_document_change_ops_groups_ops_by_base_act() -> None:
    grouped = iter_no_document_change_ops(_AMENDMENT_XML, "no/lovtid/2025-02-02-5")

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2025-01-01-1"
    assert len(ops) == 3
    assert ops[0].provenance_tags == ("base_act:no/lov/2025-01-01-1",)
    assert all(op.provenance_tags == ("base_act:no/lov/2025-01-01-1",) for op in ops)


def test_iter_no_document_change_ops_compiles_move_part_to_renumber_ops() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-move-part="lov/2025-01-01-1/§4;;lov/2025-01-01-1/§5 lov/2025-01-01-1/§5;;lov/2025-01-01-1/§6 lov/2025-01-01-1/§6;;lov/2025-01-01-1/§7"
               data-add-new-part="lov/2025-01-01-1/§4">
        <article class="defaultP">Nåværende §§ 4 til 6 blir §§ 5 til 7. Ny § 4 tilføyes.</article>
        <article class="futureLegalArticle" data-name="§4">
          <span class="futureLegalArticleHeader">
            <span class="legalArticleValue">§ 4</span>.
            <span class="legalArticleTitle">Ny paragraf</span>
          </span>
          <article class="legalP">Ny tekst.</article>
        </article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-06-20-90")

    assert [(op.action, op.target.path, op.destination.path if op.destination else ()) for op in ops] == [
        (StructuralAction.RENUMBER, (("section", "6"),), (("section", "7"),)),
        (StructuralAction.RENUMBER, (("section", "5"),), (("section", "6"),)),
        (StructuralAction.RENUMBER, (("section", "4"),), (("section", "5"),)),
        (StructuralAction.INSERT, (("section", "4"),), ()),
    ]


def test_parse_no_amendment_ops_treats_embedded_semicolon_pairs_in_add_new_part_as_renumber() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change"
               data-add-new-part="lov/2024-01-12-1/§3-2/ledd/4/setning/2;;lov/2024-01-12-1/§3-2/ledd/4/setning/3 lov/2024-01-12-1/§3-2/ledd/4/setning/3;;lov/2024-01-12-1/§3-2/ledd/4/setning/4">
        <article class="defaultP">§ 3-2 fjerde ledd nåværende annet og tredje punktum blir tredje og fjerde punktum.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2024-12-20-92")

    assert [(op.action, op.target.path, op.destination.path if op.destination else ()) for op in ops] == [
        (
            StructuralAction.RENUMBER,
            (("section", "3-2"), ("subsection", "4"), ("sentence", "2")),
            (("section", "3-2"), ("subsection", "4"), ("sentence", "3")),
        ),
        (
            StructuralAction.RENUMBER,
            (("section", "3-2"), ("subsection", "4"), ("sentence", "3")),
            (("section", "3-2"), ("subsection", "4"), ("sentence", "4")),
        ),
    ]


def test_parse_no_amendment_ops_splits_lead_in_tail_across_sentence_targets() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change"
               data-add-new-part="lov/2024-01-12-1/§4-2/ledd/2/setning/3 lov/2024-01-12-1/§4-2/ledd/2/setning/4">
        <article class="defaultP">§ 4-2 andre ledd nytt tredje og fjerde punktum skal lyde: Første nye punktum. Andre nye punktum.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-12-22-123")

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            StructuralAction.INSERT,
            (("section", "4-2"), ("subsection", "2"), ("sentence", "3")),
            "Første nye punktum.",
        ),
        (
            StructuralAction.INSERT,
            (("section", "4-2"), ("subsection", "2"), ("sentence", "4")),
            "Andre nye punktum.",
        ),
    ]


def test_parse_no_amendment_ops_splits_lead_in_tail_with_jf_abbreviation() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2024-01-12-1">
      <article class="change"
               data-add-new-part="lov/2024-01-12-1/§4-2/ledd/2/setning/3 lov/2024-01-12-1/§4-2/ledd/2/setning/4">
        <article class="defaultP">§ 4-2 andre ledd nytt tredje og fjerde punktum skal lyde: Når det i samsvar med denne loven gjøres justeringer, jf. første og andre punktum. Dette gjelder for inneværende og senere regnskapsår.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2025-12-22-123")

    assert [(op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (
            (("section", "4-2"), ("subsection", "2"), ("sentence", "3")),
            "Når det i samsvar med denne loven gjøres justeringer, jf. første og andre punktum.",
        ),
        (
            (("section", "4-2"), ("subsection", "2"), ("sentence", "4")),
            "Dette gjelder for inneværende og senere regnskapsår.",
        ),
    ]


def test_parse_no_amendment_ops_structured_prefers_sentence_targets_over_subsection_attrs() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change"
               data-change-part="lov/2022-05-12-28/§45/ledd/2"
               data-add-new-part="lov/2022-05-12-28/§45/ledd/3 lov/2022-05-12-28/§45/ledd/4">
        <article class="defaultP">§ 45 andre ledd nytt tredje og fjerde punktum skal lyde:</article>
        <article class="legalP">Første nye punktum. Andre nye punktum.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []

    ops = parse_no_amendment_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (StructuralAction.INSERT, (("section", "45"), ("subsection", "2"), ("sentence", "3")), "Første nye punktum."),
        (StructuralAction.INSERT, (("section", "45"), ("subsection", "2"), ("sentence", "4")), "Andre nye punktum."),
    ]
    assert [item.kind for item in adjudications] == [
        "no_parse_structured_target_rebound_from_lead",
        "no_parse_action_recovered_from_structured_lead",
    ]
    rebind = adjudications[0]
    action_recovery = adjudications[1]
    assert rebind.detail["rule_id"] == "no_parse_structured_target_rebound_from_lead"
    assert rebind.detail["phase"] == "parse"
    assert rebind.detail["family"] == "target_resolution_recovery"
    assert rebind.detail["blocking"] is True
    assert rebind.detail["strict_disposition"] == "block"
    assert rebind.detail["quirks_disposition"] == "record"
    assert rebind.detail["reason"] == "sentence_targets_inferred_from_lead"
    assert rebind.detail["scope_confidence"] == "explicit_source_with_context"
    assert rebind.detail["original_specs"] == (
        {"action": "replace", "target": "section:45/subsection:2"},
        {"action": "insert", "target": "section:45/subsection:3"},
        {"action": "insert", "target": "section:45/subsection:4"},
    )
    assert rebind.detail["recovered_specs"] == (
        {"action": "insert", "target": "section:45/subsection:2/sentence:3"},
        {"action": "insert", "target": "section:45/subsection:2/sentence:4"},
    )
    assert action_recovery.detail["rule_id"] == "no_parse_action_recovered_from_structured_lead"
    assert action_recovery.detail["family"] == "action_family_recovery"
    assert action_recovery.detail["original_actions"] == ("replace", "insert", "insert")
    assert action_recovery.detail["recovered_actions"] == ("insert", "insert")


def test_iter_no_document_change_ops_skips_structured_cross_base_target_without_number() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change" data-change-part="lov/1967-02-10/§12/ledd/2">
        <article class="defaultP">12. I lov 10. februar 1967 om behandlingsmåten i forvaltningssaker skal § 12 andre ledd lyde:</article>
        <article class="legalP">Som fullmektig kan brukes enhver myndig person.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []

    grouped = dict(iter_no_document_change_ops(xml, "no/lovtid/2024-06-21-46", adjudications_out=adjudications))

    assert grouped == {}
    assert len(adjudications) == 1
    adjudication = adjudications[0]
    assert adjudication.kind == "no_parse_cross_base_structured_target_skipped"
    assert adjudication.source_statute == "no/lovtid/2024-06-21-46"
    assert adjudication.detail["rule_id"] == "no_parse_cross_base_structured_target_skipped"
    assert adjudication.detail["phase"] == "parse"
    assert adjudication.detail["strict_disposition"] == "block"
    assert adjudication.detail["quirks_disposition"] == "record"
    assert adjudication.detail["base_id"] == "no/lov/2022-05-12-28"
    assert adjudication.detail["target_base"] == "no/lov/1967-02-10"
    assert adjudication.detail["action"] == "replace"
    assert adjudication.detail["raw_target"] == "lov/1967-02-10/§12/ledd/2"


def test_parse_no_amendment_ops_forwards_structured_cross_base_skip_adjudication() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change" data-change-part="lov/1967-02-10/§12/ledd/2">
        <article class="defaultP">12. I lov 10. februar 1967 om behandlingsmåten i forvaltningssaker skal § 12 andre ledd lyde:</article>
        <article class="legalP">Som fullmektig kan brukes enhver myndig person.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    ops = parse_no_amendment_ops(xml, "no/lovtid/2024-06-21-46", adjudications_out=adjudications)

    assert ops == []
    assert [item.kind for item in adjudications] == ["no_parse_cross_base_structured_target_skipped"]
    assert adjudications[0].detail["target_base"] == "no/lov/1967-02-10"


def test_iter_no_document_change_ops_records_unresolved_structured_target_skip() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change" data-change-part="lov/2022-05-12-28/ukjent">
        <article class="defaultP">§ 12 andre ledd skal lyde:</article>
        <article class="legalP">Som fullmektig kan brukes enhver myndig person.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert grouped == []
    assert [item.kind for item in adjudications] == [
        "no_parse_unresolved_structured_target_skipped"
    ]
    adjudication = adjudications[0]
    assert adjudication.source_statute == "no/lovtid/2024-06-21-46"
    assert adjudication.detail["rule_id"] == "no_parse_unresolved_structured_target_skipped"
    assert adjudication.detail["phase"] == "parse"
    assert adjudication.detail["family"] == "target_resolution_recovery"
    assert adjudication.detail["strict_disposition"] == "block"
    assert adjudication.detail["quirks_disposition"] == "record"
    assert adjudication.detail["base_id"] == "no/lov/2022-05-12-28"
    assert adjudication.detail["target_base"] == "no/lov/2022-05-12-28"
    assert adjudication.detail["action"] == "replace"
    assert adjudication.detail["raw_target"] == "lov/2022-05-12-28/ukjent"


def test_iter_no_document_change_ops_records_cross_base_structured_renumber_skip() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change"
               data-move-part="lov/1967-02-10/§12/ledd/2;;lov/2022-05-12-28/§12/ledd/3">
        <article class="defaultP">Nåværende § 12 andre ledd blir nytt tredje ledd.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert grouped == []
    assert [item.kind for item in adjudications] == [
        "no_parse_cross_base_structured_renumber_skipped"
    ]
    adjudication = adjudications[0]
    assert adjudication.source_statute == "no/lovtid/2024-06-21-46"
    assert adjudication.detail["rule_id"] == "no_parse_cross_base_structured_renumber_skipped"
    assert adjudication.detail["phase"] == "parse"
    assert adjudication.detail["family"] == "source_pathology"
    assert adjudication.detail["strict_disposition"] == "block"
    assert adjudication.detail["quirks_disposition"] == "record"
    assert adjudication.detail["base_id"] == "no/lov/2022-05-12-28"
    assert adjudication.detail["target_base"] == "no/lov/1967-02-10"
    assert adjudication.detail["destination_base"] == "no/lov/2022-05-12-28"
    assert adjudication.detail["target_cross_base"] is True
    assert adjudication.detail["destination_cross_base"] is False


def test_iter_no_document_change_ops_records_unresolved_structured_renumber_skip() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change"
               data-move-part="lov/2022-05-12-28/foo;;lov/2022-05-12-28/§12/ledd/3">
        <article class="defaultP">Nåværende § 12 andre ledd blir nytt tredje ledd.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert grouped == []
    assert [item.kind for item in adjudications] == [
        "no_parse_unresolved_structured_renumber_skipped"
    ]
    adjudication = adjudications[0]
    assert adjudication.source_statute == "no/lovtid/2024-06-21-46"
    assert adjudication.detail["rule_id"] == "no_parse_unresolved_structured_renumber_skipped"
    assert adjudication.detail["phase"] == "parse"
    assert adjudication.detail["family"] == "target_resolution_recovery"
    assert adjudication.detail["strict_disposition"] == "block"
    assert adjudication.detail["quirks_disposition"] == "record"
    assert adjudication.detail["base_id"] == "no/lov/2022-05-12-28"
    assert adjudication.detail["raw_target"] == "lov/2022-05-12-28/foo"
    assert adjudication.detail["target_resolved"] is False
    assert adjudication.detail["destination_resolved"] is True


def test_iter_no_document_change_ops_records_malformed_structured_renumber_tokens() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2022-05-12-28">
      <article class="change"
               data-move-part="lov/2022-05-12-28/§12/ledd/2 lov/2022-05-12-28/§12/ledd/3;;">
        <article class="defaultP">Nåværende § 12 andre ledd blir nytt tredje ledd.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert grouped == []
    assert [item.kind for item in adjudications] == [
        "no_parse_malformed_structured_renumber_attr_skipped",
        "no_parse_malformed_structured_renumber_attr_skipped",
    ]
    missing_destination = adjudications[0]
    missing_separator = adjudications[1]
    assert missing_destination.source_statute == "no/lovtid/2024-06-21-46"
    assert missing_destination.detail["rule_id"] == "no_parse_malformed_structured_renumber_attr_skipped"
    assert missing_destination.detail["phase"] == "parse"
    assert missing_destination.detail["family"] == "source_pathology"
    assert missing_destination.detail["blocking"] is True
    assert missing_destination.detail["strict_disposition"] == "block"
    assert missing_destination.detail["quirks_disposition"] == "record"
    assert missing_destination.detail["base_id"] == "no/lov/2022-05-12-28"
    assert missing_destination.detail["source_doc"] == "lov/2022-05-12-28"
    assert missing_destination.detail["attr_name"] == "data-move-part"
    assert missing_destination.detail["raw_token"] == "lov/2022-05-12-28/§12/ledd/3;;"
    assert missing_destination.detail["reason"] == "missing_destination"
    assert missing_separator.detail["raw_token"] == "lov/2022-05-12-28/§12/ledd/2"
    assert missing_separator.detail["reason"] == "missing_separator"


def test_iter_no_document_change_ops_keeps_valid_structured_renumber_when_malformed_token_present() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2025-01-01-1">
      <article class="change"
               data-move-part="lov/2025-01-01-1/§4;;lov/2025-01-01-1/§5 lov/2025-01-01-1/§6">
        <article class="defaultP">Nåværende § 4 blir § 5.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = dict(
        iter_no_document_change_ops(
            xml,
            "no/lovtid/2025-06-20-90",
            adjudications_out=adjudications,
        )
    )

    ops = grouped["no/lov/2025-01-01-1"]
    assert [(op.action, op.target.path, op.destination.path if op.destination else ()) for op in ops] == [
        (StructuralAction.RENUMBER, (("section", "4"),), (("section", "5"),))
    ]
    assert [item.kind for item in adjudications] == [
        "no_parse_malformed_structured_renumber_attr_skipped"
    ]
    assert adjudications[0].detail["raw_token"] == "lov/2025-01-01-1/§6"
    assert adjudications[0].detail["reason"] == "missing_separator"


def test_iter_no_document_change_ops_records_missing_structured_base() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change">
      <article class="change" data-change-part="lov/2022-05-12-28/§12">
        <article class="legalP">§ 12 skal lyde:</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert grouped == []
    assert [item.kind for item in adjudications] == [
        "no_parse_document_change_base_unresolved"
    ]
    adjudication = adjudications[0]
    assert adjudication.source_statute == "no/lovtid/2024-06-21-46"
    assert adjudication.detail["rule_id"] == "no_parse_document_change_base_unresolved"
    assert adjudication.detail["phase"] == "parse"
    assert adjudication.detail["family"] == "source_pathology"
    assert adjudication.detail["blocking"] is True
    assert adjudication.detail["strict_disposition"] == "block"
    assert adjudication.detail["quirks_disposition"] == "record"
    assert adjudication.detail["source_doc"] == ""
    assert adjudication.detail["reason"] == "missing_data_document"


def test_parse_no_amendment_ops_forwards_missing_structured_base_adjudication() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="not-a-lovdata-ref">
      <article class="change" data-change-part="lov/2022-05-12-28/§12">
        <article class="legalP">§ 12 skal lyde:</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    ops = parse_no_amendment_ops(
        xml,
        "no/lovtid/2024-06-21-46",
        adjudications_out=adjudications,
    )

    assert ops == []
    assert [item.kind for item in adjudications] == [
        "no_parse_document_change_base_unresolved"
    ]
    assert adjudications[0].detail["source_doc"] == "not-a-lovdata-ref"
    assert adjudications[0].detail["reason"] == "unmappable_data_document"


def test_parse_no_amendment_ops_unstructured_supports_mixed_existing_and_new_subsections() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2019-06-21-70</li></ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 17 tredje, nytt fjerde og femte ledd skal lyde:</article>
        <article class="legalP">Eksisterende tredje ledd.</article>
        <article class="legalP">Nytt fjerde ledd.</article>
        <article class="legalP">Nytt femte ledd.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(xml, "no/lovtid/2020-12-18-159"))
    ops = grouped["no/lov/2019-06-21-70"]

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "17"), ("subsection", "3")), "Eksisterende tredje ledd."),
        (StructuralAction.INSERT, (("section", "17"), ("subsection", "4")), "Nytt fjerde ledd."),
        (StructuralAction.INSERT, (("section", "17"), ("subsection", "5")), "Nytt femte ledd."),
    ]


def test_parse_no_amendment_ops_unstructured_marks_new_subsection_as_insert() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2019-06-21-70</li></ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 39 nytt tredje ledd skal lyde:</article>
        <article class="legalP">Nytt tredje ledd.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2020-12-18-159")

    assert [(op.action, op.target.path, op.payload.text if op.payload else None) for op in ops] == [
        (StructuralAction.INSERT, (("section", "39"), ("subsection", "3")), "Nytt tredje ledd."),
    ]


def test_iter_no_document_change_ops_unstructured_records_base_unresolved_lead() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 5 skal lyde:</article>
        <article class="futureLegalArticle"><h3>§ 5. Tittel</h3></article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(xml, "no/lovtid/2020-12-18-159", adjudications_out=adjudications)

    assert grouped == []
    assert [item.kind for item in adjudications] == ["no_parse_unstructured_lead_base_unresolved"]
    assert adjudications[0].detail["rule_id"] == "no_parse_unstructured_lead_base_unresolved"
    assert adjudications[0].detail["phase"] == "parse"
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["quirks_disposition"] == "record"
    assert adjudications[0].detail["base_id"] == ""
    assert "§ 5 skal lyde" in adjudications[0].detail["source_excerpt"]


def test_iter_no_document_change_ops_unstructured_records_payload_unresolved() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2019-06-21-70</li></ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 39 tredje ledd skal lyde:</article>
        <article class="legalP"></article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(xml, "no/lovtid/2020-12-18-159", adjudications_out=adjudications)

    assert grouped == []
    assert [item.kind for item in adjudications] == ["no_parse_unstructured_payload_unresolved"]
    assert adjudications[0].detail["base_id"] == "no/lov/2019-06-21-70"
    assert adjudications[0].detail["target"] == "section:39/subsection:3"
    assert adjudications[0].detail["payload_family"] == "subsection"
    assert adjudications[0].detail["strict_disposition"] == "block"


def test_iter_no_document_change_ops_unstructured_records_unmatched_operative_lead() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2019-06-21-70</li></ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">§ 5 flyttes til § 6.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(xml, "no/lovtid/2020-12-18-159", adjudications_out=adjudications)

    assert grouped == []
    assert [item.kind for item in adjudications] == ["no_parse_unstructured_lead_unmatched"]
    assert adjudications[0].detail["base_id"] == "no/lov/2019-06-21-70"
    assert adjudications[0].detail["family"] == "unsupported_or_unresolved_action"
    assert adjudications[0].detail["blocking"] is True


def test_parse_no_amendment_ops_promotes_replace_plus_same_target_renumber_to_insert() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2023-06-16-62">
      <article class="change" data-change-part="lov/2023-06-16-62/§5-11/ledd/2/setning/3">
        <article class="defaultP">§ 5-11 andre ledd tredje punktum skal lyde: Den tillitsvalgte skal legge ved en erklæring fra den nye kandidaten.</article>
      </article>
      <article class="change" data-move-part="lov/2023-06-16-62/§5-11/ledd/2/setning/3;;lov/2023-06-16-62/§5-11/ledd/2/setning/4">
        <article class="defaultP">Nåværende § 5-11 andre ledd tredje punktum blir nytt fjerde punktum.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    ops = parse_no_amendment_ops(xml, "no/lovtid/2024-06-21-51")

    assert [(_action_value(op.action), op.target.path, op.destination.path if op.destination else None) for op in ops] == [
        (
            _action_value(StructuralAction.INSERT),
            (("section", "5-11"), ("subsection", "2"), ("sentence", "3")),
            None,
        ),
        (
            _action_value(StructuralAction.RENUMBER),
            (("section", "5-11"), ("subsection", "2"), ("sentence", "3")),
            (("section", "5-11"), ("subsection", "2"), ("sentence", "4")),
        ),
    ]
    assert ops[0].payload is not None
    assert ops[0].payload.text == "Den tillitsvalgte skal legge ved en erklæring fra den nye kandidaten."
    assert "no_parse_replace_promoted_to_insert_for_same_target_renumber" in ops[0].provenance_tags


def test_apply_no_ops_replaces_inserts_and_repeals() -> None:
    statute = parse_no_statute(_STATUTE_XML, "no/lov/2025-01-01-1")
    ops = parse_no_amendment_ops(_AMENDMENT_XML, "no/lovtid/2025-02-02-5")

    updated = apply_no_ops(statute, ops)

    chapter = updated.body.children[0]
    assert [child.label for child in chapter.children if child.kind is IRNodeKind.SECTION] == ["2"]

    section_two = next(child for child in chapter.children if child.kind is IRNodeKind.SECTION)
    subsection = section_two.children[1]
    assert [(item.label, item.text) for item in subsection.children] == [
        ("1", "oppdatert krav"),
        ("2", "to krav"),
        ("3", "tredje krav"),
    ]


def test_apply_no_ops_merges_section_heading_only_replace_with_existing_subsections() -> None:
    statute = IRStatute(
        statute_id="no/lov/2024-01-12-1",
        title="Heading merge test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="2-4",
                    children=(IRNode(kind=IRNodeKind.HEADING, text="Gammel tittel"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Første ledd."),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="Andre ledd."),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="1",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2-4"),)),
        payload=IRNode(
            kind=IRNodeKind.SECTION,
            label="2-4",
            children=(IRNode(kind=IRNodeKind.HEADING, text="Ny tittel"),),
        ),
        source=OperationSource(statute_id="no/lovtid/2024-12-20-92"),
    )

    updated = apply_no_ops(statute, [op])

    section = updated.body.children[0]
    assert [(child.kind, child.label, child.text) for child in section.children] == [
        (IRNodeKind.HEADING, None, "Ny tittel"),
        (IRNodeKind.SUBSECTION, "1", "Første ledd."),
        (IRNodeKind.SUBSECTION, "2", "Andre ledd."),
    ]


def test_apply_no_ops_insert_builds_missing_parent_chain_under_existing_scope() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Missing parent test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(kind=IRNodeKind.SECTION, label="7-3", children=(IRNode(kind=IRNodeKind.HEADING, text="Heading"),)),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2024-06-25-66",
        enacted="2024-06-25",
        effective="2024-06-25",
    )
    ops = [
        LegalOperation(
            op_id="1",
            sequence=1,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "7-3"), ("subsection", "5"), ("sentence", "3"))),
            payload=IRNode(kind=IRNodeKind.SENTENCE, label="3", text="Tredje punktum."),
            source=source,
        ),
        LegalOperation(
            op_id="2",
            sequence=2,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "6-2"), ("subsection", "1"), ("sentence", "3"))),
            payload=IRNode(kind=IRNodeKind.SENTENCE, label="3", text="Annet tredje punktum."),
            source=source,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    section_7_3 = next(child for child in updated.body.children if child.kind is IRNodeKind.SECTION and child.label == "7-3")
    subsection_5 = next(child for child in section_7_3.children if child.kind is IRNodeKind.SUBSECTION and child.label == "5")
    assert [(child.kind, child.label, child.text) for child in subsection_5.children] == [
        (IRNodeKind.SENTENCE, "3", "Tredje punktum."),
    ]

    assert not any(
        child.kind is IRNodeKind.SECTION and child.label == "6-2"
        for child in updated.body.children
    )
    assert not any(
        child.kind is IRNodeKind.SENTENCE and child.label == "3"
        for child in updated.body.children
    )


def test_apply_no_ops_materializes_sentence_children_before_sentence_replace() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Sentence split test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="3-2",
                    children=(IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="2",
                            text="Første punktum. Andre gamle punktum.",
                        ),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-sentence",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "3-2"), ("subsection", "2"), ("sentence", "2"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="2", text="Andre nye punktum."),
        source=OperationSource(statute_id="no/lovtid/2024-12-20-92"),
    )

    updated = apply_no_ops(statute, [op])

    section = updated.body.children[0]
    subsection = section.children[0]
    assert subsection.text == ""
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "Første punktum."),
        (IRNodeKind.SENTENCE, "2", "Andre nye punktum."),
    ]


def test_apply_no_ops_appends_shallow_section_sentence_replace_into_sole_subsection() -> None:
    statute = IRStatute(
        statute_id="no/lov/2004-12-17-99",
        title="Shallow sentence append test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="21",
                    children=(IRNode(kind=IRNodeKind.HEADING, text="(straff)"),
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            text="Første punktum.",
                        ),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-shallow-sentence",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "21"), ("sentence", "2"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="2", text="Medvirkning straffes ikke."),
        source=OperationSource(statute_id="no/lovtid/2015-06-19-65"),
    )

    updated = apply_no_ops(statute, [op])

    section = updated.body.children[0]
    subsection = next(child for child in section.children if child.kind is IRNodeKind.SUBSECTION)
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "Første punktum."),
        (IRNodeKind.SENTENCE, "2", "Medvirkning straffes ikke."),
    ]


def test_apply_no_ops_reorders_sentence_renumber_before_insert_after_materialization() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Sentence renumber test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="2-6",
                    children=(IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="2",
                            text="Første punktum. Andre gamle punktum.",
                        ),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2024-06-25-66",
        enacted="2024-06-25",
        effective="2024-06-25",
    )
    ops = [
        LegalOperation(
            op_id="insert-2",
            sequence=4,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "2-6"), ("subsection", "2"), ("sentence", "2"))),
            payload=IRNode(kind=IRNodeKind.SENTENCE, label="2", text="Andre nye punktum."),
            source=source,
        ),
        LegalOperation(
            op_id="move-2-3",
            sequence=5,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "2-6"), ("subsection", "2"), ("sentence", "2"))),
            destination=LegalAddress(path=(("section", "2-6"), ("subsection", "2"), ("sentence", "3"))),
            source=source,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    subsection = updated.body.children[0].children[0]
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "Første punktum."),
        (IRNodeKind.SENTENCE, "2", "Andre nye punktum."),
        (IRNodeKind.SENTENCE, "3", "Andre gamle punktum."),
    ]


def test_apply_no_ops_resolves_sentence_replace_with_repeated_subsection_labels_in_correct_section() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Scoped sentence resolution test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1-4",
                    children=(IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="Old first. Old second."),),
                ),
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="3-2",
                    children=(IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="Other first. Other second."),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-1-4-2-1",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "1-4"), ("subsection", "2"), ("sentence", "1"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="1", text="New first."),
        source=OperationSource(statute_id="no/lovtid/2025-12-22-123"),
    )

    updated = apply_no_ops(statute, [op])

    first_section = updated.body.children[0]
    first_subsection = first_section.children[0]
    assert [(child.kind, child.label, child.text) for child in first_subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "New first."),
        (IRNodeKind.SENTENCE, "2", "Old second."),
    ]

    second_section = updated.body.children[1]
    second_subsection = second_section.children[0]
    assert second_subsection.text == "Other first. Other second."
    assert second_subsection.children == ()


def test_apply_no_ops_resolves_shallow_section_sentence_replace_via_unique_subsection() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Shallow sentence target test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1-2",
                    children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Old only sentence."),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-1-2-s1",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "1-2"), ("sentence", "1"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="1", text="New only sentence."),
        source=OperationSource(statute_id="no/lovtid/2025-12-22-123"),
    )
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    subsection = updated.body.children[0].children[0]
    assert subsection.text == ""
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "New only sentence."),
    ]
    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_sentence_children_materialized", "no_sentence_text_materialized_for_shallow_sentence_target"),
        ("no_replay_shallow_sentence_target_rebound", "no_shallow_sentence_target_rebound_to_unique_host"),
    ]
    assert adjudications[0].detail["family"] == "ontology_normalization"
    assert adjudications[0].detail["materialized_parent_path"] == "section:1-2/subsection:1"
    assert adjudications[1].detail["family"] == "target_resolution_recovery"
    assert adjudications[1].detail["host_path"] == "section:1-2/subsection:1"


def test_apply_no_ops_treats_missing_section_replace_as_insert() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Missing section replace test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="1",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="3", text="three"),
                        IRNode(kind=IRNodeKind.SECTION, label="4", text="four"),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-3a",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "3a"),)),
        payload=IRNode(
            kind=IRNodeKind.SECTION,
            label="3a",
            children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="new section text"),),
        ),
        source=OperationSource(statute_id="no/lovtid/2023-12-15-91"),
    )
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    chapter = updated.body.children[0]
    assert [child.label for child in chapter.children if child.kind is IRNodeKind.SECTION] == ["3", "3a", "4"]
    inserted = next(child for child in chapter.children if child.kind is IRNodeKind.SECTION and child.label == "3a")
    assert [(child.kind, child.label, child.text) for child in inserted.children] == [
        (IRNodeKind.SUBSECTION, "1", "new section text"),
    ]
    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_replace_recovered_by_insert", "no_replace_missing_section_insert")
    ]
    assert adjudications[0].detail["family"] == "action_family_recovery"
    assert adjudications[0].detail["blocking"] is True
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["quirks_disposition"] == "record"


def test_apply_no_ops_materializes_sentence_children_before_existing_items() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Sentence plus items test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1-3",
                    children=(IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="2",
                            text="Old lead sentence.",
                            children=(IRNode(kind=IRNodeKind.ITEM, label="a", text="første"),
                                IRNode(kind=IRNodeKind.ITEM, label="b", text="andre"),),
                        ),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-1-3-2-1",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "1-3"), ("subsection", "2"), ("sentence", "1"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="1", text="New lead sentence."),
        source=OperationSource(statute_id="no/lovtid/2025-12-22-123"),
    )

    updated = apply_no_ops(statute, [op])

    subsection = updated.body.children[0].children[0]
    assert subsection.text == ""
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "New lead sentence."),
        (IRNodeKind.ITEM, "a", "første"),
        (IRNodeKind.ITEM, "b", "andre"),
    ]


def test_apply_no_ops_appends_next_sentence_on_replace_when_target_missing() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Sentence append test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="6",
                    children=(IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            text="Første punktum. Andre punktum.",
                        ),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-6-1-3",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "6"), ("subsection", "1"), ("sentence", "3"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="3", text="Tredje punktum."),
        source=OperationSource(statute_id="no/lovtid/2025-12-22-123"),
    )
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    subsection = updated.body.children[0].children[0]
    assert subsection.text == ""
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.SENTENCE, "1", "Første punktum."),
        (IRNodeKind.SENTENCE, "2", "Andre punktum."),
        (IRNodeKind.SENTENCE, "3", "Tredje punktum."),
    ]
    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_sentence_children_materialized", "no_sentence_text_materialized_for_sentence_target"),
        ("no_replay_replace_recovered_by_insert", "no_replace_missing_sentence_append_to_resolved_parent"),
    ]
    assert adjudications[0].detail["family"] == "ontology_normalization"
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["materialized_parent_path"] == "section:6/subsection:1"
    assert adjudications[0].detail["materialized_sentence_count"] == 2


def test_apply_no_ops_appends_last_item_on_replace_when_target_missing() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Item append test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="5",
                    children=(IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            children=(IRNode(kind=IRNodeKind.ITEM, label="1", text="Første vilkår."),
                                IRNode(kind=IRNodeKind.ITEM, label="2", text="Andre vilkår."),),
                        ),),
                ),),
        ),
    )
    op = LegalOperation(
        op_id="replace-5-1-last",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "5"), ("subsection", "1"), ("item", "last"))),
        payload=IRNode(kind=IRNodeKind.ITEM, label="last", text="Tredje vilkår."),
        source=OperationSource(statute_id="no/lovtid/2025-01-28-3"),
    )
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    subsection = updated.body.children[0].children[0]
    assert [(child.kind, child.label, child.text) for child in subsection.children] == [
        (IRNodeKind.ITEM, "1", "Første vilkår."),
        (IRNodeKind.ITEM, "2", "Andre vilkår."),
        (IRNodeKind.ITEM, "3", "Tredje vilkår."),
    ]
    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_replace_recovered_by_insert", "no_replace_missing_last_item_append_to_parent")
    ]


def test_apply_no_ops_infers_chapter_parent_for_new_section_insert() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Section family test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="2",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="2-1", text="one"),
                        IRNode(kind=IRNodeKind.SECTION, label="2-2", text="two"),),
                ),
                IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="3",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="3-1", text="three"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2024-06-25-66",
        enacted="2024-06-25",
        effective="2024-06-25",
    )
    op = LegalOperation(
        op_id="insert-2-10",
        sequence=1,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=(("section", "2-10"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="2-10", text="new section"),
        source=source,
    )

    updated = apply_no_ops(statute, [op])

    chapter_2 = updated.body.children[0]
    assert [child.label for child in chapter_2.children] == ["2-1", "2-2", "2-10"]
    assert not any(child.kind is IRNodeKind.SECTION and child.label == "2-10" for child in updated.body.children)


def test_apply_no_ops_renumber_keeps_section_under_existing_chapter() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Chapter-preserving renumber test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="6",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="21", text="straff"),
                        IRNode(kind=IRNodeKind.SECTION, label="23", text="endringer"),
                        IRNode(kind=IRNodeKind.SECTION, label="24", text="ikraft"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2012-05-25-29",
        enacted="2012-05-25",
        effective="2012-05-25",
    )
    ops = [
        LegalOperation(
            op_id="renumber-24-23",
            sequence=1,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "24"),)),
            destination=LegalAddress(path=(("section", "23"),)),
            source=source,
        ),
        LegalOperation(
            op_id="renumber-23-22",
            sequence=2,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "23"),)),
            destination=LegalAddress(path=(("section", "22"),)),
            source=source,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    chapter_6 = updated.body.children[0]
    assert [(child.kind, child.label, child.text) for child in chapter_6.children] == [
        (IRNodeKind.SECTION, "21", "straff"),
        (IRNodeKind.SECTION, "22", "endringer"),
        (IRNodeKind.SECTION, "23", "ikraft"),
    ]
    assert not any(child.kind is IRNodeKind.SECTION and child.label == "22" for child in updated.body.children)


def test_apply_no_ops_invariant_check_uses_norway_roman_chapter_sort() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Roman chapter order test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="VIII",
                    children=(IRNode(
                            kind=IRNodeKind.SECTION,
                            label="2",
                            children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Første punktum. Andre punktum."),
                                IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="Eldre tekst. Andre setning."),),
                        ),),
                ),
                IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="IX",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="11", text="Neste kapittel"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2022-12-20-122",
        enacted="2022-12-20",
        effective="2022-12-20",
    )
    op = LegalOperation(
        op_id="replace-roman-chapter-sentence",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2"), ("subsection", "2"), ("sentence", "2"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="2", text="Ny andre setning."),
        source=source,
    )

    updated = apply_no_ops(statute, [op])

    chapter_viii = updated.body.children[0]
    subsection_2 = chapter_viii.children[0].children[1]
    assert subsection_2.kind is IRNodeKind.SUBSECTION
    assert subsection_2.children[1].text == "Ny andre setning."
    assert [child.label for child in updated.body.children if child.kind is IRNodeKind.CHAPTER] == ["VIII", "IX"]


def _no_litra_statute() -> IRStatute:
    """Statute whose UNTOUCHED subtree carries an a..e litra (bokstav) list.

    The lone letters ``c`` (roman 100) and ``d`` (roman 500) previously fooled
    the Norway sort key into reporting ``item out of order: d > e`` and aborting
    the whole replay over a perfectly well-ordered bokstav list.
    """
    return IRStatute(
        statute_id="no/lov/2006-08-18-61",
        title="Litra ordering test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="2",
                            children=tuple(
                                IRNode(kind=IRNodeKind.ITEM, label=litra, text=f"bokstav {litra}")
                                for litra in ("a", "b", "c", "d", "e")
                            ),
                        ),
                    ),
                ),
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="2",
                    children=(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="2",
                            children=(
                                IRNode(kind=IRNodeKind.SENTENCE, label="1", text="Gammel tekst."),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_apply_no_ops_litra_list_in_untouched_subtree_does_not_abort() -> None:
    statute = _no_litra_statute()
    source = OperationSource(
        statute_id="no/lovtid/2022-12-20-122",
        enacted="2022-12-20",
        effective="2022-12-20",
    )
    # The op only touches section:2; the a..e litra list lives under section:1.
    op = LegalOperation(
        op_id="replace-section-2-sentence",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2"), ("subsection", "2"), ("sentence", "1"))),
        payload=IRNode(kind=IRNodeKind.SENTENCE, label="1", text="Ny tekst."),
        source=source,
    )

    updated = apply_no_ops(statute, [op])

    touched = updated.body.children[1].children[0].children[0]
    assert touched.text == "Ny tekst."
    litra = updated.body.children[0].children[0]
    assert [child.label for child in litra.children] == ["a", "b", "c", "d", "e"]


def test_apply_no_ops_genuine_order_violation_still_aborts() -> None:
    """Honesty: a real out-of-order list must still abort the replay.

    The litra/roman relaxation only down-grades the *spurious* ``d > e`` family
    on well-ordered bokstav/roman lists; a genuinely disordered list (here a
    numeric item run ``3, 1``) must still raise.
    """
    statute = IRStatute(
        statute_id="no/lov/2006-08-18-61",
        title="Genuine disorder test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            children=(
                                IRNode(kind=IRNodeKind.ITEM, label="3", text="tredje"),
                                IRNode(kind=IRNodeKind.ITEM, label="1", text="forste"),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2022-12-20-122",
        enacted="2022-12-20",
        effective="2022-12-20",
    )
    op = LegalOperation(
        op_id="replace-item-3",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "1"), ("subsection", "1"), ("item", "3"))),
        payload=IRNode(kind=IRNodeKind.ITEM, label="3", text="tredje endret"),
        source=source,
    )

    with pytest.raises(ValueError, match="out of order"):
        apply_no_ops(statute, [op], strict_invariants=True)


def test_apply_no_ops_lowercase_roman_subitem_list_orders_numerically() -> None:
    """A roman sub-item list (i, ii, ..., v, ..., ix) must not flag v as litra."""
    statute = IRStatute(
        statute_id="no/lov/2005-06-03-33",
        title="Roman sub-item ordering test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            children=tuple(
                                IRNode(kind=IRNodeKind.ITEM, label=rn, text=f"romertall {rn}")
                                for rn in ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix")
                            ),
                        ),
                    ),
                ),
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="2",
                    children=(
                        IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Gammel tekst."),
                    ),
                ),
            ),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2022-12-20-122",
        enacted="2022-12-20",
        effective="2022-12-20",
    )
    op = LegalOperation(
        op_id="replace-section-2",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2"), ("subsection", "1"))),
        payload=IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Ny tekst."),
        source=source,
    )

    # Must not raise: i..ix is a correctly ordered roman sequence even though
    # lone ``v``/``x`` look like litra to a context-free sort key.
    updated = apply_no_ops(statute, [op], strict_invariants=True)
    roman_items = updated.body.children[0].children[0]
    assert [child.label for child in roman_items.children] == [
        "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix",
    ]


def test_apply_no_ops_spurious_sort_order_downgrade_leaves_a_witness() -> None:
    """A spurious sort_order downgrade must record an attributable witness.

    Witness-required-for-downgrade discipline (notes/DISCIPLINE_GATES.md): when a
    ``sort_order`` invariant violation is dropped from the blocking set as
    spurious (roman-numeral semantics), the downgrade must not vanish silently —
    it records a reclassification rule id + reason so a future regression in the
    spurious predicate is auditable rather than invisible.
    """
    from lawvm.core.downgrade_witness import (
        DowngradeRecord,
        downgrade_witness_violation,
    )

    statute = IRStatute(
        statute_id="no/lov/2005-06-03-33",
        title="Roman sub-item downgrade witness test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            children=tuple(
                                IRNode(kind=IRNodeKind.ITEM, label=rn, text=f"romertall {rn}")
                                for rn in ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix")
                            ),
                        ),
                    ),
                ),
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="2",
                    children=(
                        IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Gammel tekst."),
                    ),
                ),
            ),
        ),
    )
    op = LegalOperation(
        op_id="replace-section-2",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2"), ("subsection", "1"))),
        payload=IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Ny tekst."),
        source=OperationSource(
            statute_id="no/lovtid/2022-12-20-122",
            enacted="2022-12-20",
            effective="2022-12-20",
        ),
    )

    sink: list[CompileAdjudication] = []
    apply_no_ops(statute, [op], adjudications_out=sink, strict_invariants=True)

    downgrades = [
        a for a in sink if a.kind == "replay_tree_invariant_violation_downgraded"
    ]
    assert downgrades, "spurious sort_order downgrade left no witness adjudication"
    detail = downgrades[0].detail
    assert detail.get("nonblocking_reclassification_rule_id")
    assert detail.get("reclassification_reason")

    # The recorded witness satisfies the jurisdiction-agnostic invariant.
    record = DowngradeRecord(
        finding_id=downgrades[0].kind,
        bug_kind="sort_order",
        downgraded_to_nonblocking=True,
        reclassification_rule_id=str(detail["nonblocking_reclassification_rule_id"]),
        reclassification_reason=str(detail["reclassification_reason"]),
    )
    assert downgrade_witness_violation(record) is None


def test_apply_no_ops_insert_reuses_existing_target_as_replace() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Insert-as-replace test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="4",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="16", text="old section 16"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2023-12-15-91",
        enacted="2023-12-15",
        effective="2023-12-15",
    )
    op = LegalOperation(
        op_id="insert-16",
        sequence=1,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=(("section", "16"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="16", text="replacement section 16"),
        source=source,
    )
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    chapter_4 = updated.body.children[0]
    assert [(child.label, child.text) for child in chapter_4.children] == [("16", "replacement section 16")]
    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_insert_occupied_target_replaced", "no_insert_occupied_target_replace")
    ]


def test_apply_no_ops_renumber_chain_avoids_duplicate_sections() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Renumbering test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(kind=IRNodeKind.SECTION, label="4", text="old 4"),
                IRNode(kind=IRNodeKind.SECTION, label="5", text="old 5"),
                IRNode(kind=IRNodeKind.SECTION, label="6", text="old 6"),
                IRNode(kind=IRNodeKind.SECTION, label="7", text="old 7"),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    ops = [
        LegalOperation(
            op_id="1",
            sequence=1,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "7"),)),
            destination=LegalAddress(path=(("section", "8"),)),
            source=source,
        ),
        LegalOperation(
            op_id="2",
            sequence=2,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "6"),)),
            destination=LegalAddress(path=(("section", "7"),)),
            source=source,
        ),
        LegalOperation(
            op_id="3",
            sequence=3,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "5"),)),
            destination=LegalAddress(path=(("section", "6"),)),
            source=source,
        ),
        LegalOperation(
            op_id="4",
            sequence=4,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "4"),)),
            destination=LegalAddress(path=(("section", "5"),)),
            source=source,
        ),
        LegalOperation(
            op_id="5",
            sequence=5,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "4"),)),
            payload=IRNode(kind=IRNodeKind.SECTION, label="4", text="new 4"),
            source=source,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    assert [child.label for child in updated.body.children] == ["4", "5", "6", "7", "8"]
    assert [child.text for child in updated.body.children] == ["new 4", "old 4", "old 5", "old 6", "old 7"]


def test_apply_no_ops_renumber_can_clear_occupied_destination_not_moved_elsewhere() -> None:
    statute = IRStatute(
        statute_id="no/lov/2004-12-17-99",
        title="Klimakvoteloven tail test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="5",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="19", text="old 19"),
                        IRNode(kind=IRNodeKind.SECTION, label="20", text="old 20"),
                        IRNode(kind=IRNodeKind.SECTION, label="21", text="old 21"),
                        IRNode(kind=IRNodeKind.SECTION, label="21a", text="old 21a"),
                        IRNode(kind=IRNodeKind.SECTION, label="22", text="old 22"),),
                ),
                IRNode(
                    kind=IRNodeKind.CHAPTER,
                    label="6",
                    children=(IRNode(kind=IRNodeKind.SECTION, label="23", text="old 23"),
                        IRNode(kind=IRNodeKind.SECTION, label="24", text="old 24"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2012-05-25-29",
        enacted="2012-05-25",
        effective="2012-05-25",
    )
    ops = [
        LegalOperation(
            op_id="replace-19",
            sequence=1,
            action=StructuralAction.REPLACE,
            target=LegalAddress(path=(("section", "19"),)),
            payload=IRNode(kind=IRNodeKind.SECTION, label="19", text="new 19"),
            source=source,
        ),
        LegalOperation(
            op_id="renumber-21a-20",
            sequence=2,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "21a"),)),
            destination=LegalAddress(path=(("section", "20"),)),
            source=source,
        ),
        LegalOperation(
            op_id="replace-21",
            sequence=3,
            action=StructuralAction.REPLACE,
            target=LegalAddress(path=(("section", "21"),)),
            payload=IRNode(kind=IRNodeKind.SECTION, label="21", text="new 21"),
            source=source,
        ),
        LegalOperation(
            op_id="renumber-23-22",
            sequence=4,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "23"),)),
            destination=LegalAddress(path=(("section", "22"),)),
            source=source,
        ),
        LegalOperation(
            op_id="renumber-24-23",
            sequence=5,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "24"),)),
            destination=LegalAddress(path=(("section", "23"),)),
            source=source,
        ),
    ]

    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, ops, adjudications_out=adjudications)

    chapter_5 = updated.body.children[0]
    chapter_6 = updated.body.children[1]
    assert [child.label for child in chapter_5.children] == ["19", "20", "21"]
    assert [child.text for child in chapter_5.children] == ["new 19", "old 21a", "new 21"]
    assert [child.label for child in chapter_6.children] == ["22", "23"]
    assert [child.text for child in chapter_6.children] == ["old 23", "old 24"]
    assert [item.kind for item in adjudications] == [
        "no_replay_renumber_occupied_destination_removed",
        "no_replay_renumber_occupied_destination_removed",
    ]
    assert adjudications[0].detail["rule_id"] == "no_renumber_occupied_destination_removed"
    assert adjudications[0].detail["phase"] == "replay"
    assert adjudications[0].detail["family"] == "migration_or_lineage_recovery"
    assert adjudications[0].detail["blocking"] is True
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["quirks_disposition"] == "record"
    assert adjudications[0].detail["source_path"] == "chapter:6/section:23"
    assert adjudications[0].detail["destination_path"] == "chapter:5/section:22"
    assert adjudications[0].detail["removed_kind"] == "section"
    assert adjudications[0].detail["removed_label"] == "22"
    assert adjudications[1].detail["source_path"] == "chapter:5/section:21a"
    assert adjudications[1].detail["destination_path"] == "chapter:5/section:20"
    assert adjudications[1].detail["removed_label"] == "20"


def test_apply_no_ops_strict_recovery_rejects_occupied_renumber_destination_removal() -> None:
    statute = IRStatute(
        statute_id="no/lov/2004-12-17-99",
        title="Strict renumber recovery test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(kind=IRNodeKind.SECTION, label="20", text="old 20"),
                IRNode(kind=IRNodeKind.SECTION, label="21a", text="old 21a"),
            ),
        ),
    )
    source = OperationSource(statute_id="no/lovtid/2012-05-25-29")
    op = LegalOperation(
        op_id="renumber-21a-20",
        sequence=1,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=(("section", "21a"),)),
        destination=LegalAddress(path=(("section", "20"),)),
        source=source,
    )
    adjudications: list[CompileAdjudication] = []

    with pytest.raises(ValueError, match="no_replay_renumber_occupied_destination_removed"):
        apply_no_ops(
            statute,
            [op],
            adjudications_out=adjudications,
            strict_recovery=True,
        )

    assert [item.kind for item in adjudications] == [
        "no_replay_renumber_occupied_destination_removed"
    ]
    assert adjudications[0].detail["strict_disposition"] == "block"


def test_apply_no_ops_sorts_by_effective_date_not_local_sequence() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Ordering test",
        body=IRNode(kind=IRNodeKind.BODY, children=(IRNode(kind=IRNodeKind.SECTION, label="4", text="base"),)),
    )
    older = OperationSource(
        statute_id="no/lovtid/2023-12-15-90",
        enacted="2023-12-15",
        effective="2023-12-15",
    )
    later = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    ops = [
        LegalOperation(
            op_id="later",
            sequence=1,
            action=StructuralAction.REPLACE,
            target=LegalAddress(path=(("section", "4"),)),
            payload=IRNode(kind=IRNodeKind.SECTION, label="4", text="later text"),
            source=later,
        ),
        LegalOperation(
            op_id="older",
            sequence=9,
            action=StructuralAction.REPLACE,
            target=LegalAddress(path=(("section", "4"),)),
            payload=IRNode(kind=IRNodeKind.SECTION, label="4", text="older text"),
            source=older,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    assert updated.body.children[0].text == "later text"


def test_apply_no_ops_reorders_split_block_renumber_chain_before_insert() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Split renumber test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="3",
                    children=(IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="first"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="old second"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="old third"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-91",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    ops = [
        LegalOperation(
            op_id="insert-2",
            sequence=4,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "3"), ("subsection", "2"))),
            payload=IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="new second"),
            source=source,
        ),
        LegalOperation(
            op_id="move-2-3",
            sequence=5,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "3"), ("subsection", "2"))),
            destination=LegalAddress(path=(("section", "3"), ("subsection", "3"))),
            source=source,
        ),
        LegalOperation(
            op_id="move-3-4",
            sequence=6,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "3"), ("subsection", "3"))),
            destination=LegalAddress(path=(("section", "3"), ("subsection", "4"))),
            source=source,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    section = updated.body.children[0]
    assert [child.label for child in section.children] == ["1", "2", "3", "4"]
    assert [child.text for child in section.children] == ["first", "new second", "old second", "old third"]


def test_apply_no_ops_repeal_happens_before_renumber_into_same_label() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Reorder repeal/renumber test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="3-1",
                    children=(IRNode(kind=IRNodeKind.SUBSECTION, label="5", text="old fifth"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="6", text="old sixth"),),
                ),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2024-06-25-66",
        enacted="2024-06-25",
        effective="2024-06-25",
    )
    ops = [
        LegalOperation(
            op_id="repeal-5",
            sequence=8,
            action=StructuralAction.REPEAL,
            target=LegalAddress(path=(("section", "3-1"), ("subsection", "5"))),
            source=source,
        ),
        LegalOperation(
            op_id="move-6-5",
            sequence=9,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "3-1"), ("subsection", "6"))),
            destination=LegalAddress(path=(("section", "3-1"), ("subsection", "5"))),
            source=source,
        ),
    ]

    updated = apply_no_ops(statute, ops)

    section = updated.body.children[0]
    assert [(child.label, child.text) for child in section.children] == [("5", "old sixth")]


def test_apply_no_ops_exact_target_insert_does_not_duplicate_section() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Invariant test",
        body=IRNode(kind=IRNodeKind.BODY, children=(IRNode(kind=IRNodeKind.SECTION, label="4", text="base"),)),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    ops = [
        LegalOperation(
            op_id="dup",
            sequence=1,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "4"),)),
            payload=IRNode(kind=IRNodeKind.SECTION, label="4", text="duplicate"),
            source=source,
        ),
    ]
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, ops, adjudications_out=adjudications)

    assert [(child.label, child.text) for child in updated.body.children] == [("4", "duplicate")]
    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_insert_occupied_target_replaced", "no_insert_occupied_target_replace")
    ]


def test_apply_no_ops_direct_child_insert_is_refused_not_overwritten() -> None:
    """W-63 polarity: the direct-child collision REFUSES instead of overwriting.

    Pre-W-63 this lane emitted ``no_replay_insert_occupied_direct_child_replaced``
    and overwrote ``section:5/subsection:1/item:1`` — an address the op never
    named (its target was ``section:5/item:9``, which does not resolve) chosen
    purely by payload ``(kind, label)`` match under an INFERRED parent. The
    occupant's in-force text was destroyed and the commanded address stayed
    empty. The cell fired ZERO times over all 782 corpus base laws (W-63
    census, apply fold run non-strict), so the flip costs nothing today and
    removes a silent destructive write.

    The occupant must survive byte-identically, nothing may land, and the op
    must be REJECTED with a typed blocking receipt.
    """
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Direct child insert-as-replace test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(
                    kind=IRNodeKind.SECTION,
                    label="5",
                    children=(IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            children=(IRNode(kind=IRNodeKind.ITEM, label="1", text="old item"),),
                        ),),
                ),),
        ),
    )
    source = OperationSource(statute_id="no/lovtid/2025-06-20-90")
    adjudications: list[CompileAdjudication] = []
    op = LegalOperation(
        op_id="insert-item-1",
        sequence=1,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=(("section", "5"), ("item", "9"))),
        payload=IRNode(kind=IRNodeKind.ITEM, label="1", text="new item"),
        source=source,
    )

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    # The occupant survives; the payload lands NOWHERE (not at the commanded
    # ``section:5/item:9`` either — the op is refused whole).
    item = updated.body.children[0].children[0].children[0]
    assert item.text == "old item"
    assert [child.label for child in updated.body.children[0].children] == ["1"]
    assert [(entry.kind, entry.detail["rule_id"]) for entry in adjudications] == [
        ("no_replay_insert_occupied_direct_child_refused", "no_insert_occupied_direct_child_refuse")
    ]
    assert adjudications[0].blocking is True
    assert adjudications[0].detail["family"] == "unsupported_or_unresolved_action"
    assert adjudications[0].detail["executed_action"] == "none"
    assert adjudications[0].detail["target"] == "section:5/item:9"
    assert adjudications[0].detail["occupied_child_path"] == "section:5/subsection:1/item:1"


def test_apply_no_ops_strict_action_family_rejects_recovery() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Strict action family test",
        body=IRNode(kind=IRNodeKind.BODY, children=(IRNode(kind=IRNodeKind.SECTION, label="4", text="base"),)),
    )
    source = OperationSource(statute_id="no/lovtid/2025-06-20-90")
    adjudications: list[CompileAdjudication] = []
    op = LegalOperation(
        op_id="dup",
        sequence=1,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=(("section", "4"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="4", text="duplicate"),
        source=source,
    )

    with pytest.raises(ValueError, match="action-family recovery"):
        apply_no_ops(
            statute,
            [op],
            adjudications_out=adjudications,
            strict_action_family=True,
        )

    assert [(item.kind, item.detail["rule_id"]) for item in adjudications] == [
        ("no_replay_insert_occupied_target_replaced", "no_insert_occupied_target_replace")
    ]


def test_apply_no_ops_collects_missing_target_adjudication() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Adjudication test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(kind=IRNodeKind.SECTION, label="1", text="base"),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    adjudications: list[CompileAdjudication] = []
    op = LegalOperation(
        op_id="no-target-replace",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "9"),)),
        payload=IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="missing section child"),
        source=source,
    )

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    assert len(adjudications) == 1
    assert adjudications[0].kind == "replay_unresolved_target"
    assert adjudications[0].detail["target"] == "section:9"
    assert adjudications[0].detail["action"] == "replace"
    assert adjudications[0].detail["rule_id"] == "replay_unresolved_target"
    assert adjudications[0].detail["phase"] == "replay"
    assert adjudications[0].detail["family"] == "unsupported_or_unresolved_action"
    assert adjudications[0].detail["blocking"] is True
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["quirks_disposition"] == "record"
    assert updated.body.children[0].label == "1"


def test_apply_no_ops_tree_invariant_adjudication_uses_typed_violation_detail() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Invariant detail test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(kind=IRNodeKind.SECTION, label="2", text="old 2"),
                IRNode(kind=IRNodeKind.SECTION, label="1", text="old 1"),
            ),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    op = LegalOperation(
        op_id="replace-section-2",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("section", "2"),)),
        payload=IRNode(kind=IRNodeKind.SECTION, label="2", text="new 2"),
        source=source,
    )
    adjudications: list[CompileAdjudication] = []

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications, strict_invariants=False)

    invariant_adjudications = [
        adjudication for adjudication in adjudications if adjudication.kind == "replay_tree_invariant_violation"
    ]
    assert updated.body.children[0].text == "new 2"
    assert len(invariant_adjudications) == 1
    detail = invariant_adjudications[0].detail
    assert detail["family"] == "tree_invariant_violation"
    assert "section out of order: 2 > 1" in detail["violations"]
    assert detail["invariant_violations"][0]["kind"] == "sort_order"
    assert detail["invariant_violations"][0]["path"] == "body"
    assert detail["invariant_violations"][0]["previous_label"] == "2"
    assert detail["invariant_violations"][0]["next_label"] == "1"


def test_apply_no_ops_collects_noop_for_empty_target_path() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="No-op adjudication test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(IRNode(kind=IRNodeKind.SECTION, label="1", text="base"),),
        ),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    adjudications: list[CompileAdjudication] = []
    op = LegalOperation(
        op_id="empty-target-skip",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=()),
        source=source,
    )

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    assert len(adjudications) == 1
    assert adjudications[0].kind == "replay_noop"
    assert adjudications[0].detail["action"] == "replace"
    assert adjudications[0].detail["rule_id"] == "replay_noop"
    assert adjudications[0].detail["phase"] == "replay"
    assert adjudications[0].detail["family"] == "unsupported_or_unresolved_action"
    assert adjudications[0].detail["blocking"] is True
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["quirks_disposition"] == "record"
    assert updated.statute_id == "no/lov/2025-01-01-1"


def test_apply_no_ops_collects_unsupported_action() -> None:
    statute = IRStatute(
        statute_id="no/lov/2025-01-01-1",
        title="Unsupported action adjudication test",
        body=IRNode(kind=IRNodeKind.BODY, children=(IRNode(kind=IRNodeKind.SECTION, label="1", text="base"),)),
    )
    source = OperationSource(
        statute_id="no/lovtid/2025-06-20-90",
        enacted="2025-06-20",
        effective="2025-06-20",
    )
    with pytest.raises(TypeError, match="LegalOperation.action must be StructuralAction"):
        LegalOperation(
            op_id="unsupported-action",
            sequence=1,
            action=cast(StructuralAction, "unknown"),
            target=LegalAddress(path=(("section", "1"),)),
            source=source,
        )

    adjudications: list[CompileAdjudication] = []
    op = LegalOperation(
        op_id="unsupported-text-repeal",
        sequence=1,
        action=StructuralAction.TEXT_PATCH,
        # DELETE-kind = the former TEXT_REPEAL (§2.1 O6); NO does not support it.
        text_patch=TextPatchSpec(
            kind=TextPatchKindEnum.DELETE,
            selector=TextSelector(match_text="x"),
        ),
        target=LegalAddress(path=(("section", "1"),)),
        source=source,
    )

    updated = apply_no_ops(statute, [op], adjudications_out=adjudications)

    assert len(adjudications) == 1
    assert adjudications[0].kind == "replay_unsupported_action"
    assert adjudications[0].detail["action"] == "text_repeal"
    assert adjudications[0].detail["target"] == "section:1"
    assert adjudications[0].detail["rule_id"] == "replay_unsupported_action"
    assert adjudications[0].detail["phase"] == "replay"
    assert adjudications[0].detail["family"] == "unsupported_or_unresolved_action"
    assert adjudications[0].detail["blocking"] is True
    assert adjudications[0].detail["strict_disposition"] == "block"
    assert adjudications[0].detail["quirks_disposition"] == "record"
    assert updated.body.children[0].text == "base"


def test_open_lovdata_amendment_archive_yields_source_ids(tmp_path) -> None:
    archive_path = tmp_path / "lovtidend-avd1-2025.tar.bz2"
    member_name = "lti/2025/nl-20250202-005.xml"

    with tarfile.open(archive_path, "w:bz2") as tf:
        payload = _AMENDMENT_XML
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    items = list(open_lovdata_amendment_archive(str(archive_path)))

    assert len(items) == 1
    assert items[0][0] == "no/lovtid/2025-02-02-5"
    assert b"document-change" in items[0][1]


def test_build_no_populates_amendment_index_from_lovtidend_archives(tmp_path) -> None:
    base_archive = tmp_path / "gjeldende-lover.tar.bz2"
    amendment_archive = tmp_path / "lovtidend-avd1-2025.tar.bz2"
    output_dir = tmp_path / "out"

    with tarfile.open(base_archive, "w:bz2") as tf:
        payload = _STATUTE_XML
        info = tarfile.TarInfo("nl/nl-20250101-001.xml")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    with tarfile.open(amendment_archive, "w:bz2") as tf:
        payload = _AMENDMENT_XML
        info = tarfile.TarInfo("lti/2025/nl-20250202-005.xml")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    asyncio.run(
        _build_no(
            base_archive,
            output_dir,
            verbose=False,
            amendment_archives=[amendment_archive],
        )
    )

    amendments = json.loads((output_dir / "amendments.json").read_text(encoding="utf-8"))
    stats = json.loads((output_dir / "stats.json").read_text(encoding="utf-8"))
    statutes = json.loads((output_dir / "statutes.json").read_text(encoding="utf-8"))

    assert amendments == {"no/lov/2025-01-01-1": ["no/lovtid/2025-02-02-5"]}
    assert stats["n_statutes"] == 1
    assert stats["n_amendment_links"] == 1
    assert statutes["no/lov/2025-01-01-1"]["title"] == "Testlov om data"


def _no_farchive_path() -> Path | None:
    """Resolve ``norway.farchive`` the way the other NO archive tests do."""
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
def test_no_multi_part_misbinding_witness_stays_pinned() -> None:
    """W-15 corpus witness: ``no/lovtid/2019-06-21-57`` binds all five amended laws.

    Before the fix, parts III/IV/V (serveringsloven, regnskapsloven,
    kommuneloven) all landed on part II's law ``no/lov/2017-06-16-51``, so
    replaying the anti-discrimination act put serveringsloven's
    "Bevillingshaver, daglig leder …" text at its § 6 first subsection.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2019-06-21-57", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2019-06-21-57"))

    assert sorted(grouped) == [
        "no/lov/1997-06-13-55",
        "no/lov/1998-07-17-56",
        "no/lov/2017-06-16-50",
        "no/lov/2017-06-16-51",
        "no/lov/2018-06-22-83",
    ]
    # The witnessed contamination: § 6 first subsection is serveringsloven's.
    assert (("section", "6"), ("subsection", "1")) in [op.target.path for op in grouped["no/lov/1997-06-13-55"]]
    assert (("section", "6"), ("subsection", "1")) not in [op.target.path for op in grouped["no/lov/2017-06-16-51"]]
    assert not any(
        "Bevillingshaver" in (op.payload.text or "")
        for op in grouped["no/lov/2017-06-16-51"]
        if op.payload is not None
    )


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_finanstilsynsloven_sentence_binding_recovered_by_abbreviation_set() -> None:
    """W-19 corpus witness: the one genuine binding W-15 lost comes back.

    ``no/lovtid/2016-12-16-91`` amends finanstilsynsloven § 7 first subsection
    sentences 3 and 4. The payload is a single ``legalP`` whose second sentence
    cites "... om børsvirksomhet m.m. § 4"; with ``m.m.`` unknown the splitter
    produced three fragments for two targets and the all-or-nothing family
    emitted nothing, so ``no/lov/1956-12-07-1`` was not bound by this act.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2016-12-16-91", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2016-12-16-91"))

    assert "no/lov/1956-12-07-1" in grouped
    ops = grouped["no/lov/1956-12-07-1"]
    assert [op.target.path for op in ops] == [
        (("section", "7"), ("subsection", "1"), ("sentence", "3")),
        (("section", "7"), ("subsection", "1"), ("sentence", "4")),
    ]
    # The fourth sentence is the one the splitter used to tear in half.
    assert ops[1].payload is not None
    assert "om børsvirksomhet m.m. § 4" in (ops[1].payload.text or "")
    assert (ops[1].payload.text or "").endswith("lovbestemte oppgaver.")


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_law_announcement_witness_stays_pinned() -> None:
    """W-21 corpus witness: ``no/lovtid/2009-06-19-74`` part I is straffeloven 2005.

    Part I announces "Lov 20. mai 2005 nr. 28 om straff endres slik:". Before the
    fix, inference fell through to a consequential item nested in the new § 412
    text ("3. I lov 13. juni 1975 nr. 39 om utlevering av lovbrytere mv. …"), so
    all 22 of part I's ops — 16 structural plus the 6 global text-replaces W-20
    signed off as inert — bound to utleveringsloven, and straffeloven 2005 got
    zero ops from its own amending act. Measured 2026-08-06: the act's 469 ops
    are unchanged in identity, 22 of them move, and utleveringsloven keeps
    exactly the 3 the nested item and its two followers actually produce.

    Utleveringsloven's 3 -> 1 at W-26 (2026-08-06). Two of those 3 were never
    utleveringsloven's: they belong to the letter-suffixed item that follows,
    "1 a. I lov 6. juni 1891 nr. 2 om Guld-, Sølv- og Platinavarers Finhed …",
    whose ordinal the lead strip could not see, so they inherited the previous
    item's act. Only "§ 9 annet punktum skal lyde:" is genuinely item 3's. The
    expectation is edited rather than pinned because it asserts a witness, and
    the witness's own residue is what W-26 was opened to remove.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-06-19-74", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2009-06-19-74"))

    assert len(grouped["no/lov/2005-05-20-28"]) == 22
    assert len(grouped["no/lov/1975-06-13-39"]) == 1
    # The six ex-inert global text-replaces ride the corrected base act. Every
    # one of their ``match_text`` values occurs in straffeloven 2005's original
    # LTI text and none occurs anywhere in utleveringsloven's.
    text_patches = {
        op.text_patch.selector.match_text: op.text_patch.replacement
        for op in grouped["no/lov/2005-05-20-28"]
        if op.text_patch is not None
    }
    assert text_patches == {
        "legeme": "kropp",
        "legemsdel": "kroppsdel",
        "og som foretar noe som er ment å lede direkte til utføringen": (
            "og som foretar noe som leder direkte mot utføringen"
        ),
        "samtykket til": "samtykket i",
        "er straffri": "ikke kan straffes",
        "helbred": "helse",
    }
    # Utleveringsloven keeps only what its own nested item introduced: § 9.
    assert {op.target.path[0] for op in grouped["no/lov/1975-06-13-39"]} == {("section", "9")}
    assert [
        op.source.raw_text for op in grouped["no/lov/1975-06-13-39"] if op.source is not None
    ] == ["§ 9 annet punktum skal lyde:"]


def test_no_period_less_nr_citation_resolves_the_cited_law() -> None:
    """W-25: ``nr 16`` binds the same law as ``nr. 16``.

    The lead is `no/lovtid/2009-01-30-7` part III verbatim. Before the widening
    no citation regex saw it, so the part resolved nothing and its offentleglova
    op inherited part II's straffeprosessloven.
    """
    lead = (
        "I lov 19. mai 2006 nr 16 om rett til innsyn i dokument i offentleg "
        "verksemd (offentleglova) skal § 26 nytt fjerde ledd lyde:"
    )
    assert _extract_no_law_citation_base_id(lead) == "no/lov/2006-05-19-16"
    embedded = _extract_no_embedded_multi_act_lead(lead)
    assert embedded is not None
    assert embedded[0] == "no/lov/2006-05-19-16"
    assert embedded[1] == "§ 26 nytt fjerde ledd skal lyde:"

    # Same widening on the ``I lov … gjøres følgende endringer`` surface
    # (`no/lovtid/2021-05-07-33` part II verbatim).
    assert (
        _extract_no_section_base_id_from_lead("I lov 20. mai 2005 nr 28 om straff gjøres følgende endring:")
        == "no/lov/2005-05-20-28"
    )
    # And the dotted spelling is untouched.
    assert (
        _extract_no_law_citation_base_id("Lov 22. mai 1981 nr. 25 om rettergangsmåten i straffesaker")
        == "no/lov/1981-05-22-25"
    )


def test_no_period_less_nr_widening_does_not_invent_citations() -> None:
    """W-25 negative guard: a bare ``nr`` is only a citation after a full law date.

    Corpus-measured over every text node of every amendment artifact: the
    widening adds 29 spans, all genuine citations. These are the shapes that
    keep it that way — an address ``nr``, a ``nr`` with no date in front, and a
    date whose ``nr`` names something other than a law.
    """
    assert _extract_no_law_citation_base_id("§ 2 første ledd nr 1 skal lyde:") is None
    assert _extract_no_law_citation_base_id("jf. forskrift nr 16 om innsyn") is None
    assert _extract_no_law_citation_base_id("Sak nr 16 av 19. mai 2006 om innsyn") is None
    # ``lov`` plus a bare year is still not a citation: the day-and-month prefix
    # is what makes the trailing ``nr`` unambiguous.
    assert _extract_no_law_citation_base_id("lov 2006 nr 16 om innsyn") is None
    # A month token the grammar does not know must not resolve to a base id.
    assert _extract_no_law_citation_base_id("lov 19. floreal 2006 nr 16 om innsyn") is None


def test_no_letter_suffixed_item_ordinal_is_stripped_from_a_lead() -> None:
    """W-26: ``1 a.`` is an item ordinal, exactly as ``1.`` already was.

    The lead is `no/lovtid/2009-06-19-74` item ``1 a.`` verbatim. Before the
    widening the strip left the ordinal in place, the ``i `` test failed, and the
    item's two ops inherited the previous item's utleveringsloven.
    """
    lead = (
        "1 a. I lov 6. juni 1891 nr. 2 om Guld-, Sølv- og Platinavarers Finhed "
        "og Stempling m.v. gjøres følgende endringer:"
    )
    assert _extract_no_section_base_id_from_lead(lead) == "no/lov/1891-06-06-2"
    # The plain ordinal it generalizes still works, and so does the spaced form
    # `no/lovtid/2020-11-20-128` emits when its item number sits in a <strong>.
    assert (
        _extract_no_section_base_id_from_lead(
            "5. I lov 13. juni 1997 nr. 44 om aksjeselskaper gjøres følgende endringer:"
        )
        == "no/lov/1997-06-13-44"
    )
    assert (
        _extract_no_section_base_id_from_lead(
            "1 . I lov 7. desember 1956 nr. 1 om tilsynet med finansforetak mv. gjøres følgende endringer:"
        )
        == "no/lov/1956-12-07-1"
    )
    # The enumerated embedded form takes the same ordinal
    # (`no/lovtid/2009-06-19-74` item ``93 a.`` verbatim).
    embedded = _extract_no_embedded_multi_act_lead(
        "93 a. I lov 30. mai 1975 nr. 18 sjømannsloven skal ny § 54 C lyde:"
    )
    assert embedded is not None
    assert embedded[0] == "no/lov/1975-05-30-18"


def test_no_letter_suffixed_ordinal_strip_cannot_invent_a_binding() -> None:
    """W-26 negative guard: the strip never makes a non-citation lead resolve.

    No corpus lead opens with a bare ``<digit> <letter>.`` that is an amended
    section LABEL rather than an item ordinal — measured over every unstructured
    lead at any nesting depth, the only three letter-suffixed openers are
    `no/lovtid/2009-06-19-74`'s ``1 a.``, ``5 a.`` and ``93 a.``, all genuine
    enumeration ordinals, and section labels are always written with the sign
    ("§ 1 a"), which the ``^\\d`` anchor cannot reach. 140 leads in all carry an
    ordinal the widened strip admits and the bare form does not; it newly
    resolves 7. These constructed leads pin why the other 133 are unmoved and
    why a mis-strip would still be harmless: the post-strip guards, not the
    strip, decide.
    """
    # A section label the strip DOES eat: no citation follows, so nothing binds.
    assert _extract_no_section_base_id_from_lead("1 a. I § 1 a gjøres følgende endringer:") is None
    # Stripped, but the ``i `` test rejects it.
    assert _extract_no_section_base_id_from_lead("1 a. skal lyde:") is None
    # Stripped and ``i ``-initial, but no section-intro marker.
    assert (
        _extract_no_section_base_id_from_lead("1 a. I lov 6. juni 1891 nr. 2 om Guld- og Sølvvarer § 3 lyde:")
        is None
    )
    # `no/lovtid/2009-06-19-74` item ``5 a.`` verbatim: a bare-citation repeal
    # names a law the item acts on as a whole and introduces no items to bind,
    # so the announcement extractor must keep rejecting it after the strip.
    assert (
        _extract_no_law_announcement_base_id(
            "5 a. Lov 18. august 1914 nr. 3 om forsvarshemmeligheter oppheves."
        )
        is None
    )


@pytest.mark.parametrize(
    "tail",
    [
        # The 11 tails the closed tuple already admitted, kept here so the
        # widening can never silently drop one of them.
        "gjøres følgende endring:",
        "gjøres følgende endringer:",
        "gjøres disse endringene:",
        "gjer følgjande endring:",
        "gjer følgjande endringar:",
        "gjerast følgjande endring:",
        "gjerast følgjande endringar:",
        "blir gjort følgende endring:",
        "blir gjort følgende endringer:",
        "blir gjort følgjande endring:",
        "blir gjort følgjande endringar:",
        # W-30: every tail family the 2026-08-06 corpus sweep found outside the
        # tuple, each taken verbatim off a real lead and re-headed onto one
        # citation so the parametrization tests the TAIL, not the citation.
        # Counts are that family's share of the 535 newly-admitted leads.
        "blir det gjort følgjande endringar:",  # 119
        "gjer ein følgjande endringar:",  # 77
        "vert det gjort følgjande endringar:",  # 66
        "gjer ein følgjande endring:",  # 61
        "skal desse endringane gjerast:",  # 51
        "blir desse endringane gjort:",  # 38
        "blir det gjort desse endringane:",  # 21
        "gjer ein desse endringane:",  # 20
        "vert det gjort følgjande endring:",  # 19
        "blir det gjort følgjande endring:",  # 18
        "skal det gjerast desse endringane:",  # 14
        "skal det gjerast slike endringar:",  # 11
        "blir det gjort følgende endringer:",  # 10
        "gjer ein denne endringa:",  # 8
        "blir det gjort slike endringar:",  # 8
        "vert gjort følgjande endringar:",  # 7
        "blir desse endringane gjorde:",  # 7
        "skal disse endringene gjøres:",  # 5
        "vert det gjort slike endringar:",  # 4
        "vert følgjande endringar gjort:",  # 4
        "vert desse endringane gjort:",  # 2
        "blir følgjande endring gjort:",  # 2
        # The fillers the corpus puts INSIDE the phrase, each attested once or
        # twice: the expletive ``det``, a ``del``/``avsnitt`` scope, and an
        # adjective before the noun.
        "gjøres det følgende endringer:",
        "gjøres i del II følgende endringer:",
        "gjøres i avsnitt I følgende endringer:",
        "gjøres følgende midlertidige endringer:",
        # Lovtidend's Nynorsk drafting is not spell-checked; these four
        # misspellings are each a real corpus lead, and the tail is the only
        # guard there is.
        "vert det gjort fylgjande endringar:",
        "vert det gjort føljande endringar:",
        "gjøres følgene endring:",
        "gjøres følge endringer:",
    ],
)
def test_no_section_intro_marker_admits_every_attested_tail_spelling(tail: str) -> None:
    """W-30: the part-announcement tail is a morphology, not an 11-item list.

    ``_extract_no_section_base_id_from_lead`` gated on a hand-kept tuple of 11
    literal tails. Measured over every lead the gate is actually asked about in
    a full corpus parse (47,455 distinct, 5,722 passing its ``i `` guard), 535
    further leads across 346 acts carry the same construction in 37 other
    spellings and resolved nothing at all.
    """
    lead = f"I lov 20. mai 2005 nr. 28 om straff {tail}"
    assert _extract_no_section_base_id_from_lead(lead) == "no/lov/2005-05-20-28"


@pytest.mark.parametrize(
    "lead",
    [
        # Every one of these is a corpus lead that reaches the gate, opens with
        # ``I ``, and carries a RESOLVABLE citation — so the tail is the only
        # thing keeping it out, which is exactly what makes it a guard.
        "I lov 20. juni 2014 nr. 30 om kredittvurderingsbyråer skal § 1 lyde:",
        "I lov 16. juni 1989 nr. 65 om yrkesskadeforsikring skal lovens tittel lyde:",
        "I lov 21. desember 2020 nr. 168 om endringer i merverdiavgiftsloven skal romartal II lyde:",
        "I lov 5. januar 2001 nr. 1 om vaktvirksomhet skal følgende bestemmelser lyde:",
        "I lov 21. februar 2003 nr. 12 om biobanker (biobankloven) skal dette endrast:",
        (
            "I lov 24. mai 2013 nr. 19 om endringer i straffeprosessloven mv. "
            "(elektronisk kontroll som varetektsurrogat mv.) oppheves del I."
        ),
        (
            "I lov 19. februar 2021 nr. 4 om midlertidige endringer i smittevernloven "
            "(oppholdssted under innreisekarantene mv.) oppheves nr. 2 i lovens del II."
        ),
    ],
)
def test_no_section_intro_marker_still_rejects_the_non_construction_tails(lead: str) -> None:
    """W-30 guard: the 1,202 unlisted leads that are NOT this construction.

    Of the 1,737 ``I lov <citation> …`` part leads whose tail the tuple did not
    list, only 535 are the amending construction. The rest are §-addressed
    operative leads, whole-act repeals, title changes and inline term
    substitutions — each names a law the item acts on directly rather than
    announcing a part of amendments to it, so none may seed a part's base act.
    """
    # The citation itself is resolvable; only the missing tail keeps the lead out.
    assert _extract_no_law_citation_base_id(lead) is not None
    assert _extract_no_section_base_id_from_lead(lead) is None


def test_no_section_intro_marker_determiner_slot_is_closed() -> None:
    """W-30: why the tail is a closed morphology and not a bounded wildcard.

    A drafted alternative allowed any ≤40 characters between the "make" verb and
    the ``endring`` noun. Measured over the same 5,722-lead population it
    admitted one lead that is not this construction at all — a substantive
    provision of varemerkeloven — so the determiner slot was closed to the
    attested set instead. The corpus lead carries no citation, so it is pinned
    beside a constructed twin that does: the tail, not the missing citation, is
    what must reject it.
    """
    assert (
        _extract_no_section_base_id_from_lead(
            "I et varemerke som er søkt registrert kan det gjøres uvesentlige "
            "endringer som ikke påvirker helhetsinntrykket av merket."
        )
        is None
    )
    assert (
        _extract_no_section_base_id_from_lead(
            "I lov 26. mars 2010 nr. 8 om beskyttelse av varemerker kan det gjøres "
            "uvesentlige endringer som ikke påvirker helhetsinntrykket av merket."
        )
        is None
    )
    # The two genuine leads the closed slot costs, pinned so the trade stays
    # visible: both are the construction with an over-long scope adverbial or a
    # coordinated noun phrase, and both resolved nothing before W-30 as well.
    assert (
        _extract_no_section_base_id_from_lead(
            "I lov 27. juni 2008 nr. 65 om endringer i lov 16. juni 1989 nr. 69 om "
            "forsikringsavtaler m.m. gjøres i avsnitt II om endringer i lov 2. juli "
            "1999 nr. 64 om helsepersonell m.v. følgende endring:"
        )
        is None
    )
    assert (
        _extract_no_section_base_id_from_lead(
            "I § 19-3 nr. 5 om endringer i lov 19. juni 1964 nr. 14 om avgift av arv "
            "og visse gaver, gjøres følgende tillegg og endring:"
        )
        is None
    )


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_period_less_nr_witness_binds_offentleglova() -> None:
    """W-25 corpus witness: ``no/lovtid/2009-01-30-7`` part III is offentleglova.

    Part I's forvaltningsloven lead carries no ``nr`` at all and part II's two
    ``første stykket`` ops do not lower, so the act's single op is part III's.
    Before W-25 that op was the act's whole output and it sat on
    straffeprosessloven, inherited from part II's announcement.

    W-28 closes the part I hole this docstring named: the numberless lead now
    resolves and part I's § 19 op is emitted against forvaltningsloven
    ``no/lov/1967-02-10-0``. Part III's op is untouched, which is what this test
    is actually about, and straffeprosessloven is still absent.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-01-30-7", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2009-01-30-7"))

    assert sorted(grouped) == ["no/lov/1967-02-10-0", "no/lov/2006-05-19-16"]
    assert [op.target.path for op in grouped["no/lov/1967-02-10-0"]] == [
        (("section", "19"), ("subsection", "1"))
    ]
    ops = grouped["no/lov/2006-05-19-16"]
    assert [op.target.path for op in ops] == [(("section", "26"), ("subsection", "4"))]
    assert "no/lov/1981-05-22-25" not in grouped


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_letter_suffixed_ordinal_witness_binds_the_1891_finhed_act() -> None:
    """W-26 corpus witness: ``no/lovtid/2009-06-19-74`` item ``1 a.``.

    The two ops the W-21 landing left as utleveringsloven's residue. Their own
    item cites `no/lov/1891-06-06-2`; item ``3.`` above them cites
    utleveringsloven and keeps exactly its one op (pinned in the W-21 witness
    test above).
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-06-19-74", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2009-06-19-74"))

    ops = grouped["no/lov/1891-06-06-2"]
    assert [(op.action, op.source.raw_text) for op in ops if op.source is not None] == [
        (StructuralAction.INSERT, "Ny § 9 skal lyde:"),
        (StructuralAction.RENUMBER, "Nåværende § 9 blir ny § 10."),
    ]
    assert len(grouped["no/lov/1975-06-13-39"]) == 1
    # The same widening recovers item ``93 a.``, whose embedded ``skal ny § 54 C
    # lyde`` form produced no op at all before.
    assert [op.target.path for op in grouped["no/lov/1975-05-30-18"]] == [(("section", "54C"),)]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_industrial_property_act_splits_across_its_six_announcements() -> None:
    """W-30 corpus witness: `no/lovtid/2012-06-22-58`, the cleanest misbinding.

    Six numbered items each announce their own law; items 2-6 use the Nynorsk
    ``blir følgjande endringar gjorde:`` tail the closed tuple did not list, so
    only item 1's embedded ``skal § 3 … lyde`` form resolved and ALL 22 ops
    inherited it — the act read as 22 amendments to the 1953 defence-invention
    act, which genuinely receives exactly one. Each count below is that item's
    own op count, audited against its own lead.

    Patentloven moved 8 → 9 at W-32(c): ``§ 62 a andre ledd første punktum skal
    lyde`` is a real patentloven amendment whose SPACED section label the
    sentence grammar's old label class could not span, so it lowered nothing.
    The binding is unaffected — the op joins item 2's own law, the one its lead
    announces.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2012-06-22-58", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2012-06-22-58"))

    assert {base_id: len(ops) for base_id, ops in grouped.items()} == {
        "no/lov/1953-06-26-8": 1,  # item 1, the embedded form, unchanged
        "no/lov/1967-12-15-9": 9,  # item 2, patentloven (8 + W-32(c)'s § 62 a)
        "no/lov/1985-06-21-79": 2,  # item 3, foretaksnavneloven
        "no/lov/1993-03-12-32": 1,  # item 4, planteforedlerretten
        "no/lov/2003-03-14-15": 4,  # item 5, designloven
        "no/lov/2010-03-26-8": 6,  # item 6, varemerkeloven
    }


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_gjer_ein_folgjande_witness_enters_the_index_at_all() -> None:
    """W-30 corpus witness for the ``gjer ein følgjande …`` family.

    ``no/lovtid/2007-06-15-21`` is one of the 64 acts that gained their FIRST
    index entry: every one of its parts announces its law with a tail outside
    the tuple, so the act resolved no base at all and its 22 ops were dropped
    whole. Nothing about it is exotic — it is simply written in Nynorsk.

    ``2005-06-17-58`` moves 1 -> 3 at W-64. Its two other leads ("I kapittel I
    skal ny § 4 a lyde:", "I kapittel II skal ny § 8 a lyde:") were accepted all
    along and refused for having no payload: each is followed by a ``defaultP``
    heading, and the payload boundary stopped on it. The same two sections are
    where two of that landing's twelve false ``lead_unmatched`` receipts came
    from — the stranded body prose ("Kommunane kan vedta å opprette felles råd
    …") was re-read as a lead and tripped the operative-verb heuristic on
    ``blir``. This act's OTHER three laws are unmoved, which is the property
    worth holding: the boundary reaches only the leads that announce payload.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2007-06-15-21", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2007-06-15-21"))

    assert {base_id: len(ops) for base_id, ops in grouped.items()} == {
        "no/lov/1991-11-08-76": 3,
        "no/lov/1997-02-28-19": 13,
        "no/lov/2005-06-17-58": 3,
        "no/lov/2005-06-17-62": 5,
    }
    assert [
        (op.action, op.target.path)
        for op in grouped["no/lov/2005-06-17-58"]
    ] == [
        (StructuralAction.REPLACE, (("section", "10"),)),
        (StructuralAction.INSERT, (("section", "4a"),)),
        (StructuralAction.INSERT, (("section", "8a"),)),
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_tvisteloven_part_reclaims_its_ops_from_a_stale_carryover() -> None:
    """W-30 corpus witness for the rebind direction, not just first resolution.

    ``no/lovtid/2007-12-21-127``'s tvisteloven part opens
    "I lov 17. juni 2005 nr. 90 om mekling og rettergang i sivile tvister vert
    det gjort følgjande endringar:". With that tail unlisted the part resolved
    nothing and its 7 ops kept the previous part's 1932 arbitration act, which
    then carried 8 ops instead of its own 1. This is one of only 3 parts in the
    whole corpus whose base id the widening REPLACES rather than supplies, and
    all 3 move to the law their own head lead cites.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2007-12-21-127", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2007-12-21-127"))

    assert len(grouped["no/lov/2005-06-17-90"]) == 7
    assert len(grouped["no/lov/1932-05-27-2"]) == 1


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_revisorloven_consequential_items_enter_the_index() -> None:
    """W-26 corpus witness: `no/lovtid/2020-11-20-128` emitted nothing at all.

    Revisorloven's § 16-3 lists 13 consequential items whose numbers Lovdata put
    in a ``<strong>``, so ``itertext`` renders them "1 . ", "2 . " — a space the
    bare ``\\d+\\.`` strip could not cross. Every item therefore failed to
    resolve, the act bound no law, and its 29 lowerable ops were dropped. Each
    op below was audited against its own item's lead.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2020-11-20-128", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2020-11-20-128"))

    assert {base_id: len(ops) for base_id, ops in grouped.items()} == {
        "no/lov/1956-12-07-1": 1,
        "no/lov/1985-06-21-83": 1,
        "no/lov/1991-08-30-71": 1,
        "no/lov/1997-06-13-44": 5,
        "no/lov/1997-06-13-45": 5,
        "no/lov/2007-06-29-75": 6,
        "no/lov/2015-04-10-17": 8,
        "no/lov/2019-06-21-31": 2,
    }


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_skattebetalingsloven_instalment_lead_recovered_by_month_token_strip() -> None:
    """W-22 corpus witness: the fourth arity recovery the W-19 sweep left on the table.

    ``no/lovtid/2020-12-21-166`` amends skattebetalingsloven § 10-20 first
    subsection, "første og annet punktum" — two declared targets. The unstripped
    day-number guard tore the instalment list at "15. mars," / "15. juni," and
    the closing "15. juni.", giving five fragments, so the act emitted nothing
    for this lead: 6 ops on ``no/lov/2005-06-17-67``, none of them § 10-20.
    Measured 2026-08-06: 6 -> 8, no op removed and no binding moved corpus-wide.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2020-12-21-166", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2020-12-21-166"))

    ops = grouped["no/lov/2005-06-17-67"]
    assert len(ops) == 8
    recovered = [op for op in ops if op.target.path[0] == ("section", "10-20")]
    assert [op.target.path for op in recovered] == [
        (("section", "10-20"), ("subsection", "1"), ("sentence", "1")),
        (("section", "10-20"), ("subsection", "1"), ("sentence", "2")),
    ]
    assert [op.payload.text for op in recovered if op.payload is not None] == [
        "Forskuddsskatt for personlige skattytere forfaller til betaling i fire like store "
        "terminer 15. mars, 15. juni, 15. september og 15. desember i inntektsåret.",
        "Er forskuddsskatten under 2 000 kroner, forfaller den i sin helhet til betaling "
        "15. juni.",
    ]


# ── W-18: published ``Rettelser`` (errata) lowering ───────────────────────────

_RETTELSE_WITNESS_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <article class="legalArticle" data-name="§5" id="paragraf-5">
        <h2 class="legalArticleHeader"><span class="legalArticleValue">§ 5</span>. <span class="legalArticleTitle">Vilkår</span></h2>
        <article class="numberedLegalP" data-numerator="1" id="paragraf-5-nummer-1">(1) Vilkårene er:<ul class="defaultList"><li data-li-identifier="-" data-name="-"><article class="listArticle"><article class="legalP">Foretaket må være registrert.</article></article></li><li data-li-identifier="-" data-name="-"><article class="listArticle"><article class="legalP">Foretaket må være skattepliktig etter skatteloven § 23 første ledd bokstav b.</article></article></li></ul></article>
      </article>
      <section class="section" id="kapittel-1">
        <h2>Rettelser</h2>
        <article class="defaultP" data-text-size="small">Det som er rettet er satt i kursiv.</article>
        <article class="gazettenote" data-gazette-note-date="2021-01-05" data-gazette-note-type="rettelse">
          <article class="defaultP">§ 5 første ledd annet strekpunkt skal lyde:<ul class="defaultList"><li data-li-identifier="-" data-name="-"><article class="listArticle"><article class="legalP">Foretaket må være skattepliktig etter skatteloven <i>§ 2-3</i> første ledd bokstav b.</article></article></li></ul></article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_no_rettelse_lowers_witness_grammar_to_a_same_act_item_replace() -> None:
    """The witness shape: an ordinal ``strekpunkt`` erratum against the act's own §.

    The op binds to the host artifact's OWN law (an erratum corrects what that
    act kunngjorde), and the payload is relabelled from its position inside the
    erratum block ("1") onto the addressed item ("2").
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _RETTELSE_WITNESS_XML,
        "no/lovtid/2020-12-18-156",
        adjudications_out=adjudications,
    )

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2020-12-18-156"
    assert len(ops) == 1
    op = ops[0]
    assert op.action is StructuralAction.REPLACE
    assert op.target.path == (("section", "5"), ("subsection", "1"), ("item", "2"))
    assert op.witness_rule_id == "no_rettelse_lowered"
    # Erratum-derived provenance is typed and greppable, and carries the
    # announcement date WITHOUT letting it become the apply-ordering date.
    assert "rettelse:published_correction" in op.provenance_tags
    assert "rettelse_date:2021-01-05" in op.provenance_tags
    assert f"base_act:{base_id}" in op.provenance_tags
    assert op.payload is not None
    assert op.payload.kind is IRNodeKind.ITEM
    assert op.payload.label == "2"
    assert "§ 2-3 første ledd bokstav b" in (op.payload.text or "")
    assert not [a for a in adjudications if a.kind == "no_rettelse_not_lowered"]


@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        # The witness: a dash item is addressed by its ORDINAL position.
        (
            "§ 5 første ledd annet strekpunkt skal lyde:",
            (("section", "5"), ("subsection", "1"), ("item", "2")),
        ),
        # A lettered item is addressed by its own letter, not by position.
        (
            "§ 49 andre ledd bokstav f skal lyde:",
            (("section", "49"), ("subsection", "2"), ("item", "f")),
        ),
        # Nested/part-scoped leads name a second act; excluded by construction.
        ("§ 73 nr. 7 § 6-7 første ledd bokstav e skal lyde:", None),
        ("Del V, § 5-42 bokstav a skal lyde:", None),
        ("I del II skal § 28 b andre ledd tredje punktum skal lyde:", None),
        ("Del I § 8-2 overskriften skal lyde:", None),
        # Publication metadata has no IR address.
        ("Referansefeltet første punktum skal lyde:", None),
        ("Hjemmelsfeltet siste punktum skal lyde:", None),
        # A strekpunkt addressed by a NON-ordinal word has no position to bind
        # to; "siste" must not become the literal item label "siste".
        ("§ 5 første ledd siste strekpunkt skal lyde:", None),
        # An unknown subsection word is likewise not guessed at.
        ("§ 5 ellevte ledd annet strekpunkt skal lyde:", None),
    ],
)
def test_no_rettelse_item_target_grammar_is_anchored_and_single_section(
    lead: str, expected: tuple[tuple[str, str], ...] | None
) -> None:
    target = _no_rettelse_item_target_from_lead(lead)
    assert (target.path if target is not None else None) == expected


def test_no_rettelse_non_operative_metadata_block_is_excluded_with_a_typed_receipt() -> None:
    """A ``Referansefeltet …`` erratum corrects publication metadata, not law text.

    Seven of the corpus's twelve typed notes are this shape. There is no IR
    address for the reference field, so the note is excluded — with a receipt,
    never silently.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" id="kapittel-3">
        <h2>Rettelser</h2>
        <article class="defaultP" data-text-size="small">Det som er rettet er satt i kursiv.</article>
        <article class="gazettenote" data-gazette-note-date="2019-12-03" data-gazette-note-type="rettelse">
          <article class="defaultP">Referansefeltet skal lyde:</article>
          <article class="defaultP">Prop.98 L (2018–2019), Innst.24 L (2019–2020).</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2019-11-29-73",
        adjudications_out=adjudications,
    )

    assert grouped == []
    receipts = [a for a in adjudications if a.kind == "no_rettelse_not_lowered"]
    assert len(receipts) == 1
    assert receipts[0].detail["reason"] == "no_same_act_item_address"
    assert receipts[0].detail["rettelse_date"] == "2019-12-03"
    assert receipts[0].blocking is False


def test_no_rettelse_does_not_bind_a_nested_cross_act_address() -> None:
    """``§ 73 nr. 7 § 6-7 …`` names two sections; binding either one is wrong.

    The advokatloven regression gate. A search-anchored grammar would bind the
    lead ``§ 73`` (or, on backtracking, ``§ 6-7``) onto the host act, corrupting
    text. The single-``§`` precondition makes the whole nested family an
    excluded shape by construction.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" id="kapittel-16">
        <h2>Rettelser</h2>
        <article class="defaultP" data-text-size="small">Det som er rettet er satt i kursiv.</article>
        <article class="gazettenote" data-gazette-note-date="2022-05-16" data-gazette-note-type="rettelse">
          <article class="defaultP">§ 73 nr. 7 § 6-7 første ledd bokstav e skal lyde:<ul class="defaultList"><li data-li-identifier="e" data-name="e"><article class="listArticle"><article class="legalP">ansatt eller annen person,</article></article></li></ul></article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2022-05-12-28",
        adjudications_out=adjudications,
    )

    assert grouped == []
    # W-24 sharpened the reason: this is not "no address at all", it is an
    # address that reaches a second act the directive never names.
    assert [a.detail["reason"] for a in adjudications if a.kind == "no_rettelse_not_lowered"] == [
        "no_nested_cross_act_address"
    ]


def test_no_rettelse_rule_ignores_ordinary_act_text_containing_rettet() -> None:
    """The rule keys on Lovdata's typed note attribute, never on the word "rettet".

    An ordinary amending act whose own provision talks about corrections must
    lower exactly its ordinary ops and emit no erratum op and no erratum
    receipt.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="lov/2010-06-04-21">
      <article class="change" data-change-part="lov/2010-06-04-21/§10">
        <article class="defaultP">§ 10 skal lyde:</article>
        <article class="legalP">Det som er rettet er satt i kursiv, jf. Rettelser i Norsk Lovtidend.</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2025-01-01-1",
        adjudications_out=adjudications,
    )

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2010-06-04-21"
    assert len(ops) == 1
    assert ops[0].witness_rule_id != "no_rettelse_lowered"
    assert not any("rettelse" in tag for tag in ops[0].provenance_tags)
    assert not [a for a in adjudications if a.kind.startswith("no_rettelse")]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_rettelse_corpus_enumeration_is_pinned() -> None:
    """The whole ``Det som er rettet`` population, re-measured 2026-08-07 (W-32).

    25 artifacts carry the block; 11 of them (12 notes) use Lovdata's typed
    ``gazettenote``/``rettelse`` marker, which is this rule's entire domain. The
    remaining 14 artifacts are the untyped 2003–2011 generation, deliberately
    out of domain (see the rule's header comment).

    W-18 pinned 1 lowered / 11 excluded. W-24 moved it to 3 / 9 — the two Del-
    scoped errata whose part resolves to a law AND whose corrected address the
    host act's own op stream already touches:

      * ``2019-12-20-110`` Del I → kringkastingsloven ``1992-12-04-127`` § 8-2's
        heading, correcting the host act's own "kringkastingsmottake".
      * ``2023-12-20-98`` Del V → skatteloven ``1999-03-26-14`` § 5-42 bokstav a,
        correcting the host act's own "uføre-ytelser".

    W-32 moves it to 4 / 8, and the edit is justified by a fix to the HOST, not
    by any change to this rule: ``2020-12-04-137`` Del IV → eierseksjonsloven
    ``2017-06-16-65`` § 49 andre ledd bokstav f now lowers because the host act's
    own multi-``bokstav`` lead does, so W-24's ``no_corrected_host_op`` guard
    passes on its own unchanged terms.

    The remaining two Del/nested errata stay excluded on measurement, not on
    grammar convenience: ``2022-05-12-28`` names no target law at all, and
    ``2025-06-20-101`` corrects § 28 b ANDRE LEDD TREDJE PUNKTUM while the host
    op W-32(b) recovered is a whole-section REPLACE at § 28 b — the guard
    requires the corrected address exactly, and an ancestor is not a match.
    """
    from lawvm.norway.sources import iter_no_amendment_artifacts

    artifacts_with_block = 0
    lowered: list[str] = []
    excluded: list[str] = []
    for artifact in iter_no_amendment_artifacts(_NO_FARCHIVE_PATH):
        if b"Det som er rettet" not in artifact.payload:
            continue
        artifacts_with_block += 1
        adjudications: list[CompileAdjudication] = []
        grouped = iter_no_document_change_ops(
            artifact.payload,
            artifact.logical_id,
            adjudications_out=adjudications,
        )
        for _base_id, ops in grouped:
            for op in ops:
                if op.witness_rule_id == "no_rettelse_lowered":
                    lowered.append(artifact.logical_id)
        excluded.extend(
            artifact.logical_id for a in adjudications if a.kind == "no_rettelse_not_lowered"
        )

    assert artifacts_with_block == 25
    assert lowered == [
        "no/lovtid/2019-12-20-110",
        "no/lovtid/2020-12-04-137",
        "no/lovtid/2020-12-18-156",
        "no/lovtid/2023-12-20-98",
    ]
    assert len(excluded) == 8
    assert len(lowered) + len(excluded) == 12


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_rettelse_witness_replay_carries_the_corrected_citation() -> None:
    """F-07's witness: replayed § 5(1) item 2 reads ``§ 2-3``, not the typo ``§ 23``.

    The correction is derivable from the act's own published bytes, so this is
    reading the source completely — not preferring the consolidation
    (NORWAY_LAWVM_STATUS.md §2.2).
    """
    from lawvm.norway.replay import replay_no_to_pit

    result = replay_no_to_pit(
        "no/lov/2020-12-18-156",
        as_of="2026-07-10",
        data_dir=_NO_FARCHIVE_PATH,
    )
    assert not result.error
    assert result.replayed is not None

    def _find(node: IRNode, path: tuple[tuple[str, str], ...]) -> IRNode | None:
        if not path:
            return node
        kind, label = path[0]
        for child in node.children:
            child_kind = child.kind.value if hasattr(child.kind, "value") else str(child.kind)
            if child_kind == kind and child.label == label:
                return _find(child, path[1:])
        return None

    item = _find(result.replayed.body, (("section", "5"), ("subsection", "1"), ("item", "2")))
    assert item is not None
    assert "skatteloven § 2-3 første ledd bokstav b" in (item.text or "")
    assert "skatteloven § 23 " not in (item.text or "")


# ── W-24: Del-scoped erratum addresses resolve to the law the part amends ─────


@pytest.mark.parametrize(
    ("directive", "expected"),
    [
        # The two measured scope prefixes.
        ("Del I § 8-2 overskriften skal lyde:", ("I", "§ 8-2 overskriften skal lyde:")),
        ("Del V, § 5-42 bokstav a skal lyde:", ("V", "§ 5-42 bokstav a skal lyde:")),
        (
            "I del II skal § 28 b andre ledd tredje punktum skal lyde:",
            ("II", "§ 28 b andre ledd tredje punktum skal lyde:"),
        ),
        # The locative form's "skal" belongs to the PREFIX; the residue keeps
        # its own, so it stays a well-formed directive on its own.
        (
            "Del IV endringen i lov 16. juni 2017 nr. 65 om eierseksjoner § 49 andre ledd bokstav f skal lyde:",
            ("IV", "endringen i lov 16. juni 2017 nr. 65 om eierseksjoner § 49 andre ledd bokstav f skal lyde:"),
        ),
        # Not part-scoped: the same-act and nested shapes must not be captured.
        ("§ 5 første ledd annet strekpunkt skal lyde:", None),
        ("§ 73 nr. 7 § 6-7 første ledd bokstav e skal lyde:", None),
        ("Referansefeltet siste punktum skal lyde:", None),
        # Roman-only. "Del 4" is not a Lovtidend part spelling, and admitting
        # digits would let the resolver reach ``kap4``-style chapters.
        ("Del 4 § 8-2 overskriften skal lyde:", None),
    ],
)
def test_no_rettelse_part_scope_split_is_anchored_and_roman_only(
    directive: str, expected: tuple[str, str] | None
) -> None:
    from lawvm.norway.grafter import _no_rettelse_part_scope_from_directive

    assert _no_rettelse_part_scope_from_directive(directive) == expected


@pytest.mark.parametrize(
    ("residual", "expected"),
    [
        # New at W-24: a section-heading address, and a lettered item with no
        # ledd between it and the section (skatteloven § 5-42's actual shape,
        # confirmed by the host act's own op for the same address).
        ("§ 8-2 overskriften skal lyde:", (("section", "8-2"),)),
        ("§ 5-42 bokstav a skal lyde:", (("section", "5-42"), ("item", "a"))),
        # Reused from W-18's item grammar, unchanged.
        (
            "§ 49 andre ledd bokstav f skal lyde:",
            (("section", "49"), ("subsection", "2"), ("item", "f")),
        ),
        # Reused from the shared sentence grammar, single-spec only.
        (
            "§ 28 andre ledd tredje punktum skal lyde:",
            (("section", "28"), ("subsection", "2"), ("sentence", "3")),
        ),
        # A multi-sentence directive has no single address to bind.
        ("§ 28 andre ledd andre og tredje punktum skal lyde:", None),
        # Still single-``§``: the Del scope does not license a nested address.
        ("§ 73 nr. 7 § 6-7 første ledd bokstav e skal lyde:", None),
        # W-24 pinned this as None: the shared sentence grammar could not express
        # a spaced letter-suffixed section label, and widening the class was
        # refused there because its blast radius was unmeasured. W-32(c) measured
        # it (294 corpus texts gain specs, 0 lose specs, 0 resolve differently)
        # and widened the LEDD-CARRYING production, so the address now resolves.
        # It still does not LOWER: W-24's ``no_corrected_host_op`` guard rejects
        # it, because the host op W-32(b) recovered is a whole-section REPLACE at
        # § 28 b and the guard requires the corrected address exactly.
        (
            "§ 28 b andre ledd tredje punktum skal lyde:",
            (("section", "28b"), ("subsection", "2"), ("sentence", "3")),
        ),
        # Not an address at all.
        ("Referansefeltet siste punktum skal lyde:", None),
    ],
)
def test_no_rettelse_part_target_grammar_is_anchored(
    residual: str, expected: tuple[tuple[str, str], ...] | None
) -> None:
    from lawvm.norway.grafter import _no_rettelse_part_target_from_residual

    target = _no_rettelse_part_target_from_residual(residual)
    assert (target.path if target is not None else None) == expected


def test_no_rettelse_del_scoped_erratum_binds_the_law_that_part_amends() -> None:
    """``Del V, § 5-42 bokstav a`` binds skatteloven, not the host act.

    The part's law comes from the SAME resolver the structured lowering uses —
    the ``document-change`` wrapper inside that part — so an erratum can never
    name a law the part's own ops do not.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapI" id="kapittel-1">
        <h2>I</h2>
        <article class="document-change" data-document="lov/1999-03-26-14">
          <article class="change" data-change-part="lov/1999-03-26-14/§4-19">
            <article class="defaultP">§ 4-19 fjerde ledd skal lyde:</article>
            <article class="numberedLegalP" data-numerator="4">(4) Ved beregning av verdien.</article>
          </article>
        </article>
      </section>
      <section class="section" data-name="kapV" id="kapittel-5">
        <h2>V</h2>
        <article class="document-change" data-document="lov/1999-03-26-14">
          <article class="change" data-change-part="lov/1999-03-26-14/§5-42/bokstav/a">
            <article class="defaultP">§ 5-42 bokstav a skal lyde:</article>
            <li data-li-identifier="a." data-name="a."><article class="listArticle"><article class="legalP">stønad og uføre-ytelser fra andre ordninger.</article></article></li>
          </article>
        </article>
      </section>
      <section class="section" id="kapittel-8">
        <h2>Rettelser</h2>
        <article class="defaultP" data-text-size="small">Det som er rettet er satt i kursiv.</article>
        <article class="gazettenote" data-gazette-note-date="2023-12-29" data-gazette-note-type="rettelse">
          <article class="defaultP">Del V, § 5-42 bokstav a skal lyde:<ul class="defaultList"><li data-li-identifier="a." data-name="a."><article class="listArticle"><article class="legalP">stønad og <i>uføreytelser</i> fra andre ordninger.</article></article></li></ul></article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2023-12-20-98",
        adjudications_out=adjudications,
    )

    assert not [a for a in adjudications if a.kind == "no_rettelse_not_lowered"]
    errata = [
        (base_id, op)
        for base_id, ops in grouped
        for op in ops
        if op.witness_rule_id == "no_rettelse_lowered"
    ]
    assert len(errata) == 1
    base_id, op = errata[0]
    # The law the PART amends, never the host act.
    assert base_id == "no/lov/1999-03-26-14"
    assert "base_act:no/lov/1999-03-26-14" in op.provenance_tags
    assert "rettelse_part:V" in op.provenance_tags
    # The announcement date still rides in provenance only (W-18's dating rule
    # is untouched: the op is dated by the host act's own commencement).
    assert "rettelse_date:2023-12-29" in op.provenance_tags
    assert op.target.path == (("section", "5-42"), ("item", "a"))
    assert op.payload is not None
    assert "uføreytelser" in (op.payload.text or "")
    assert "uføre-ytelser" not in (op.payload.text or "")
    # Appended to the part's law group, so it applies after every op it could
    # correct — including the host's own § 5-42 op.
    same_base = [ops for group_base, ops in grouped if group_base == base_id]
    assert op.sequence == max(other.sequence for ops in same_base for other in ops)


def test_no_rettelse_del_scoped_erratum_needs_the_corrected_host_op() -> None:
    """A Del-scoped erratum with no host op at its address is excluded.

    ``2020-12-04-137``'s shape: Del IV resolves eierseksjonsloven and even cites
    it explicitly, but the host's own "§ 49 andre ledd bokstav e og ny bokstav f
    skal lyde" is a multi-``bokstav`` lead the grafter does not lower. With
    nothing lowered at that address the erratum has no corrected text to bind,
    and ``§ 49 andre ledd bokstav f`` denotes a provision that does not exist in
    the live law — so it is receipted, never guessed at.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapIV" id="kapittel-4">
        <h2>IV</h2>
        <article class="defaultP">I lov 16. juni 2017 nr. 65 om eierseksjoner blir det gjort slike endringar:</article>
        <article class="defaultP">§ 49 andre ledd bokstav e og ny bokstav f skal lyde:</article>
        <article class="legalP">samtykke til sammenslåing som nevnt i § 22.</article>
      </section>
      <section class="section" id="kapittel-6">
        <h2>Rettelser</h2>
        <article class="defaultP" data-text-size="small">Det som er rettet er satt i kursiv.</article>
        <article class="gazettenote" data-gazette-note-date="2020-12-07" data-gazette-note-type="rettelse">
          <article class="defaultP"><strong>7. desember 2020:</strong></article>
          <article class="defaultP">Del IV endringen i lov 16. juni 2017 nr. 65 om eierseksjoner § 49 andre ledd bokstav f skal lyde:<ul class="defaultList"><li data-li-identifier="f)" data-name="f)"><article class="listArticle"><article class="legalP">samtykke til sammenslåing som nevnt i § <i>22 a</i>.</article></article></li></ul></article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2020-12-04-137",
        adjudications_out=adjudications,
    )

    assert not [op for _base, ops in grouped for op in ops if op.witness_rule_id == "no_rettelse_lowered"]
    receipts = [a for a in adjudications if a.kind == "no_rettelse_not_lowered"]
    assert len(receipts) == 1
    assert receipts[0].detail["reason"] == "no_corrected_host_op"
    # The receipt still names what it DID resolve: the part, and its law.
    assert receipts[0].detail["part"] == "IV"
    assert receipts[0].detail["base_id"] == "no/lov/2017-06-16-65"
    # The date paragraph was skipped, so the receipt carries the real directive.
    assert receipts[0].detail["directive"].startswith("Del IV endringen i lov")
    assert receipts[0].blocking is False


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_rettelse_del_scoped_errata_correct_their_host_act_verbatim() -> None:
    """The verification the Del-scoped lowering rests on, pinned on real bytes.

    Neither target law is replayable (kringkastingsloven 1992 and skatteloven
    1999 have no original-act source), so the erratum cannot be checked against
    a replayed PIT. It does not need to be: an erratum corrects the HOST act's
    amendment text, and both the erroneous string and its correction are in the
    corpus. This pins that the erratum op lands on the exact address the host
    act's own op targets, and that its payload differs from the host's payload
    in exactly the published typo.
    """
    from lawvm.norway.sources import iter_no_amendment_artifacts

    expected = {
        # host artifact -> (target law, address, host's typo, erratum's fix)
        "no/lovtid/2019-12-20-110": (
            "no/lov/1992-12-04-127",
            (("section", "8-2"),),
            "kringkastingsmottake",
            "kringkastingsmottaker",
        ),
        "no/lovtid/2023-12-20-98": (
            "no/lov/1999-03-26-14",
            (("section", "5-42"), ("item", "a")),
            "uføre-ytelser",
            "uføreytelser",
        ),
    }
    seen: set[str] = set()
    for artifact in iter_no_amendment_artifacts(_NO_FARCHIVE_PATH):
        if artifact.logical_id not in expected:
            continue
        base_id, path, typo, fix = expected[artifact.logical_id]
        grouped = iter_no_document_change_ops(artifact.payload, artifact.logical_id)
        ops = [op for group_base, group_ops in grouped if group_base == base_id for op in group_ops]
        host_ops = [
            op for op in ops if op.target.path == path and op.witness_rule_id != "no_rettelse_lowered"
        ]
        errata = [
            op for op in ops if op.target.path == path and op.witness_rule_id == "no_rettelse_lowered"
        ]
        assert len(host_ops) == 1, artifact.logical_id
        assert len(errata) == 1, artifact.logical_id
        # A heading erratum replaces the section's HEADING only, so the host's
        # whole-section payload is compared on the same surface — its body
        # legitimately spells the word the heading got wrong.
        host_text = _no_corrected_surface_text(host_ops[0])
        erratum_text = _no_corrected_surface_text(errata[0])
        # The exact correction: the erratum surface IS the host surface with the
        # published typo repaired, and nothing else.
        assert fix not in host_text
        assert host_text.replace(typo, fix) == erratum_text
        # The erratum applies after the op it corrects.
        assert errata[0].sequence > host_ops[0].sequence
        seen.add(artifact.logical_id)
    assert seen == set(expected)


def _no_corrected_surface_text(op: LegalOperation) -> str:
    """The payload surface an erratum at this op's address actually replaces.

    For a SECTION payload that is its heading; for every other leaf kind it is
    the payload's own flattened text.
    """
    assert op.payload is not None

    def _walk(node: IRNode) -> list[str]:
        return [node.text or "", *[part for child in node.children for part in _walk(child)]]

    if op.payload.kind is IRNodeKind.SECTION:
        headings = [child for child in op.payload.children if child.kind is IRNodeKind.HEADING]
        return " ".join(part for heading in headings for part in _walk(heading))
    return " ".join(_walk(op.payload))


def test_no_rettelse_part_citation_must_agree_with_the_part() -> None:
    """An explicit citation is a cross-check, not an override.

    ``2020-12-04-137``'s directive names its target law AND scopes to Del IV, and
    the two agree. When they do not, neither wins — the erratum is excluded.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapIV" id="kapittel-4">
        <h2>IV</h2>
        <article class="document-change" data-document="lov/2003-06-06-39">
          <article class="change" data-change-part="lov/2003-06-06-39/§49">
            <article class="defaultP">§ 49 andre ledd bokstav f skal lyde:<ul class="defaultList"><li data-li-identifier="f)" data-name="f)"><article class="listArticle"><article class="legalP">gammel tekst.</article></article></li></ul></article>
          </article>
        </article>
      </section>
      <section class="section" id="kapittel-6">
        <h2>Rettelser</h2>
        <article class="defaultP" data-text-size="small">Det som er rettet er satt i kursiv.</article>
        <article class="gazettenote" data-gazette-note-date="2020-12-07" data-gazette-note-type="rettelse">
          <article class="defaultP">Del IV endringen i lov 16. juni 2017 nr. 65 om eierseksjoner § 49 andre ledd bokstav f skal lyde:<ul class="defaultList"><li data-li-identifier="f)" data-name="f)"><article class="listArticle"><article class="legalP">ny <i>tekst</i>.</article></article></li></ul></article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        amendment_xml,
        "no/lovtid/2020-12-04-137",
        adjudications_out=adjudications,
    )

    assert not [op for _base, ops in grouped for op in ops if op.witness_rule_id == "no_rettelse_lowered"]
    assert [a.detail["reason"] for a in adjudications if a.kind == "no_rettelse_not_lowered"] == [
        "no_part_citation_agreement"
    ]


def test_no_rettelse_part_with_two_amended_laws_names_neither() -> None:
    """A part whose change wrappers disagree resolves no base act."""
    from lawvm.norway.grafter import _no_part_base_id, _parse_document

    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapI" id="kapittel-1">
        <h2>I</h2>
        <article class="document-change" data-document="lov/1999-03-26-14"></article>
        <article class="document-change" data-document="lov/2003-06-06-39"></article>
      </section>
      <section class="section" data-name="kapII" id="kapittel-2">
        <h2>II</h2>
        <article class="defaultP">I lov 16. juni 2017 nr. 65 om eierseksjoner blir det gjort slike endringar:</article>
      </section>
      <section class="section" data-name="kap15" id="kapittel-15">
        <h2>Kapittel 15</h2>
        <article class="document-change" data-document="lov/2005-06-17-90"></article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    root = _parse_document(amendment_xml)
    assert _no_part_base_id(root, "I") is None
    # The unstructured resolver is the same one the ordinary lowering runs.
    assert _no_part_base_id(root, "II") == "no/lov/2017-06-16-65"
    # An arabic-numbered chapter is not a part, and "Del XV" must not reach it.
    assert _no_part_base_id(root, "XV") is None
    assert _no_part_base_id(root, "III") is None


# ── W-12: the heading-group fold's sort key IS the ordering kernel's ──────────


def test_no_heading_group_sort_agrees_with_the_ordering_kernel() -> None:
    """The fold's order must be the order ``order_ops`` gives the same sources.

    W-12 exists because the heading-group fold was a SECOND ordering surface
    with no key at all. The fix routes its key through
    ``no_ordering_profile().temporal_key`` rather than restating
    ``(effective, enacted, source_id, sequence)``; this test is the contract
    that pins the two to each other, so a future change to the NO profile
    cannot silently leave the heading-group fold behind.
    """
    from lawvm.core.op_ordering import order_ops
    from lawvm.norway.grafter import _no_heading_group_temporal_key, no_ordering_profile

    sources = [
        # (statute_id, enacted, effective) — deliberately shuffled so no two of
        # the three orderings (input, lexical, temporal) coincide.
        OperationSource(statute_id="no/lovtid/2024-01-10-1", enacted="2024-01-10", effective="2025-06-01"),
        OperationSource(statute_id="no/lovtid/2024-12-20-92", enacted="2024-12-20", effective="2024-12-20"),
        OperationSource(statute_id="no/lovtid/2023-05-05-7", enacted="2023-05-05", effective="2026-01-01"),
        # Same effective date as the second, later enactment: exercises the
        # key's second component.
        OperationSource(statute_id="no/lovtid/2025-02-02-2", enacted="2025-02-02", effective="2024-12-20"),
    ]
    groups = [
        NOHeadingGroup(start_label="2-1", end_label="2-2", title=f"T{i}", sequence=i + 1, source=source)
        for i, source in enumerate(sources)
    ]
    ops = [
        LegalOperation(
            op_id=f"op-{i}",
            sequence=i + 1,
            action=StructuralAction.INSERT,
            target=LegalAddress(path=(("section", "2-1"),)),
            source=source,
        )
        for i, source in enumerate(sources)
    ]

    def _source_id(source: OperationSource | None) -> str:
        assert source is not None
        return source.statute_id

    fold_order = [
        _source_id(group.source) for group in sorted(groups, key=_no_heading_group_temporal_key)
    ]
    kernel_order = [_source_id(op.source) for op in order_ops(ops, no_ordering_profile()).ops]

    assert fold_order == kernel_order
    assert fold_order == [
        "no/lovtid/2024-12-20-92",
        "no/lovtid/2025-02-02-2",
        "no/lovtid/2024-01-10-1",
        "no/lovtid/2023-05-05-7",
    ]


def test_no_heading_group_fold_blocks_when_a_contributor_is_undated() -> None:
    """The unordered-path guard: two contributors, one with no effective date.

    Without an effective date the kernel's key degenerates and the fold order
    is exactly the collection order W-12 was filed against, so the receipt is
    BLOCKING — the law must not read as cleanly replayed on the strength of an
    order nothing proves.
    """
    statute = IRStatute(statute_id="no/lov/2025-01-01-1", title="T", body=IRNode(kind=IRNodeKind.BODY))
    groups = [
        NOHeadingGroup(
            start_label="2-1",
            end_label="2-2",
            title="A",
            sequence=1,
            source=OperationSource(statute_id="no/lovtid/2025-02-02-5", enacted="2025-02-02", effective="2025-03-01"),
        ),
        NOHeadingGroup(
            start_label="2-10",
            end_label="2-11",
            title="B",
            sequence=1,
            source=OperationSource(statute_id="no/lovtid/2025-03-03-9", enacted="2025-03-03"),
        ),
    ]
    adjudications: list[CompileAdjudication] = []

    apply_no_heading_groups(statute, groups, adjudications_out=adjudications)

    receipts = [a for a in adjudications if a.kind == "no_heading_group_multi_source_fold"]
    assert len(receipts) == 1
    assert receipts[0].blocking is True
    assert tuple(receipts[0].detail["undated_source_ids"]) == ("no/lovtid/2025-03-03-9",)


def test_no_heading_group_fold_is_quiet_for_parser_only_callers() -> None:
    """Groups with no affecting-act identity are ONE unknown contributor.

    ``parse_no_heading_groups`` may be called without a ``source`` (tests,
    ad-hoc probes); several such groups come from ONE document, so counting
    them individually would fire the multi-source receipt on the ordinary
    single-amendment shape.
    """
    statute = IRStatute(statute_id="no/lov/2025-01-01-1", title="T", body=IRNode(kind=IRNodeKind.BODY))
    groups = [
        NOHeadingGroup(start_label="2-1", end_label="2-2", title="A", sequence=1),
        NOHeadingGroup(start_label="2-10", end_label="2-11", title="B", sequence=2),
    ]
    adjudications: list[CompileAdjudication] = []

    apply_no_heading_groups(statute, groups, adjudications_out=adjudications)

    assert [a for a in adjudications if a.kind == "no_heading_group_multi_source_fold"] == []


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_heading_group_corpus_witness_stays_single_sourced() -> None:
    """W-12's latency premise, re-measured against the corpus rather than assumed.

    A census over all 2,544 index entries × their declared base ids found
    heading groups for exactly ONE law, all from ONE amendment; that is why the
    ordering fix is byte-neutral over all 3,089 laws with an original LTI. This
    pins the witness so the premise cannot silently lapse: if a second act ever
    contributes ``Ny deloverskrift`` to suppleringsskatteloven, this test fails
    and the fold's multi-source receipt is the thing to read.
    """
    from lawvm.norway.replay import replay_no_to_pit

    html_bytes = load_no_amendment_bytes("no/lovtid/2024-12-20-92", _NO_FARCHIVE_PATH)
    assert html_bytes is not None
    groups = parse_no_heading_groups(html_bytes, "no/lov/2024-01-12-1")
    assert [(g.start_label, g.end_label, g.title, g.sequence) for g in groups] == [
        ("2-1", "2-5", "Skatteinkluderingsregelen", 1),
        ("2-10", "2-14", "Skattefordelingsregelen", 2),
        ("2-20", "2-20", "Nasjonal suppleringsskatt", 3),
    ]

    result = replay_no_to_pit(
        "no/lov/2024-01-12-1",
        as_of="2026-07-10",
        data_dir=_NO_FARCHIVE_PATH,
    )
    assert not result.error
    assert result.replayed is not None
    # Single contributor => no multi-source fold receipt.
    assert [a for a in result.adjudications if a.kind == "no_heading_group_multi_source_fold"] == []

    containers = []

    def _walk(node: IRNode) -> None:
        if node.kind is IRNodeKind.CHAPTER and (node.label or "").startswith("1-2-"):
            containers.append(node)
        for child in node.children:
            _walk(child)

    _walk(result.replayed.body)
    assert [
        (
            node.label,
            node.children[0].text,
            [c.label for c in node.children if c.kind is IRNodeKind.SECTION],
        )
        for node in containers
    ] == [
        ("1-2-1", "Skatteinkluderingsregelen", ["2-1", "2-2", "2-3", "2-4", "2-5"]),
        ("1-2-2", "Skattefordelingsregelen", ["2-10", "2-11", "2-12", "2-13", "2-14"]),
        ("1-2-3", "Nasjonal suppleringsskatt", ["2-20"]),
    ]


# ── W-32: host-lead lowering gaps that blocked the last Del errata ────────────

_MULTI_BOKSTAV_WITNESS_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapI" id="kapittel-1">
        <h2 data-text-align="center">I</h2>
        <article class="defaultP">I lov 16. juni 2017 nr. 65 om eierseksjoner blir det gjort slike endringar:</article>
        <article class="defaultP" margin-top="true">§ 49 andre ledd bokstav e og ny bokstav f skal lyde:<ul class="defaultList"><li data-li-identifier="e)" data-name="e)"><article class="listArticle"><article class="legalP">samtykke til reseksjonering som nevnt i § 20 annet ledd annet punktum</article></article></li><li data-li-identifier="f)" data-name="f)"><article class="listArticle"><article class="legalP">samtykke til sammenslåing av eierseksjonssameier som nevnt i § 22.</article></article></li></ul></article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_no_multi_bokstav_lead_lowers_every_declared_item_with_its_own_action() -> None:
    """W-32(a): a lead naming two lettered items lowers TWO ops, not zero.

    Fails on base: the single-item grammar required ``bokstav <l>`` to be
    followed directly by ``skal lyde``, so a lead that names a second item
    matched nothing and BOTH ops dropped silently. The newness marker is read
    per item — ``bokstav e`` replaces, ``ny bokstav f`` inserts — because a lead
    that creates an item and a lead that rewrites one are different instructions
    even inside one sentence.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _MULTI_BOKSTAV_WITNESS_XML,
        "no/lovtid/2020-12-04-137",
        adjudications_out=adjudications,
    )

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2017-06-16-65"
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "49"), ("subsection", "2"), ("item", "e"))),
        (StructuralAction.INSERT, (("section", "49"), ("subsection", "2"), ("item", "f"))),
    ]
    assert [op.payload.text for op in ops if op.payload is not None] == [
        "samtykke til reseksjonering som nevnt i § 20 annet ledd annet punktum",
        "samtykke til sammenslåing av eierseksjonssameier som nevnt i § 22.",
    ]
    assert not [
        a
        for a in adjudications
        if a.kind == "no_parse_unstructured_multi_item_payload_arity_mismatch"
    ]


def test_no_multi_bokstav_lead_drops_whole_lead_when_the_payload_arity_disagrees() -> None:
    """W-32(a): the W-19 all-or-nothing rule, applied to declared item arity.

    The shape of corpus witness ``no/lovtid/2011-06-24-31``, the one lead the
    sweep found where the payload does not split to the declared arity: which
    item the single payload belongs to is not recoverable, so NOTHING lowers and
    the whole lead receipts. A half-applied lead would put live text on a
    guessed address.
    """
    html_bytes = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapI" id="kapittel-1">
        <article class="defaultP">I lov 16. juni 2017 nr. 65 om eierseksjoner blir det gjort slike endringar:</article>
        <article class="defaultP" margin-top="true">§ 49 andre ledd bokstav b og c skal lyde:<ul class="defaultList"><li data-li-identifier="b)" data-name="b)"><article class="listArticle"><article class="legalP">bare den ene halvdelen</article></article></li></ul></article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        html_bytes, "no/lovtid/2011-06-24-31", adjudications_out=adjudications
    )

    assert grouped == []
    receipts = [
        a
        for a in adjudications
        if a.kind == "no_parse_unstructured_multi_item_payload_arity_mismatch"
    ]
    assert len(receipts) == 1
    assert receipts[0].detail["declared_count"] == 2
    assert receipts[0].detail["resolved_count"] == 1
    assert receipts[0].detail["unresolved_targets"] == ("section:49/subsection:2/item:c",)
    assert receipts[0].detail["blocking"] is True


@pytest.mark.parametrize(
    "lead",
    [
        # A range, not an enumeration: "a til c" leaves the middle items unnamed,
        # so the declared arity is not recoverable from the lead alone.
        "§ 9 første ledd bokstav a til c skal lyde",
        # A nested address below the item — the payload is a sentence, not an item.
        "§ 5 første ledd bokstav a første punktum og bokstav b skal lyde",
        # ``nr.`` BEFORE the bokstav is an extra item step this production does
        # not spell (measured: 12 corpus leads, deliberately unreachable).
        "§ 23-3 annet ledd nr. 2 bokstav g og ny bokstav h skal lyde",
        # Ledd-less: a section->item address the ordinary path has no grammar for
        # at all (measured: 26 corpus leads).
        "§ 12-2 bokstav h og ny bokstav i skal lyde",
        # Not an ordinal the table knows.
        "§ 7 sjuogtjuende ledd bokstav a og b skal lyde",
        # Exactly one item is the single-item grammar's business, never this one.
        "§ 49 andre ledd bokstav e skal lyde",
        # A repeated letter is a malformed lead, not two targets.
        "§ 49 andre ledd bokstav e og bokstav e skal lyde",
    ],
)
def test_no_multi_bokstav_grammar_is_anchored_and_rejects_unmeasured_shapes(lead: str) -> None:
    """W-32(a): every shape the corpus sweep found but did NOT wire stays out."""
    assert _infer_no_multi_item_specs_from_lead(lead) == []


_RENUMBER_REPLACEMENT_WITNESS_XML = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapII" id="kapittel-2">
        <article class="document-change" data-document="lov/2018-06-08-28">
          <article class="change" data-move-part="lov/2018-06-08-28/§14a;;lov/2018-06-08-28/§28b">
            <article class="defaultP">§ 14 a blir ny § 28 b og skal lyde:</article>
            <article class="futureLegalArticle" data-name="§28b">
              <span class="futureLegalArticleHeader"><span class="legalArticleValue">§ 28 b</span>. <span class="legalArticleTitle">Nasjonalt studentombud</span></span>
              <article class="legalP">Fagskolestudenter skal ha tilgang til et nasjonalt studentombud.</article>
            </article>
          </article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_no_renumber_lead_that_declares_a_replacement_lowers_both_halves() -> None:
    """W-32(b): "§ 14 a blir ny § 28 b og skal lyde" is a move AND a rewrite.

    Fails on base: only ``data-move-part`` was read, so the provision arrived at
    its new address still carrying its OLD text — and, in the corpus witness, the
    stale heading "§ 14 a. Studentombud". The replacement targets the
    DESTINATION and is sequenced after the renumber, because it is the moved
    provision that is being rewritten.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _RENUMBER_REPLACEMENT_WITNESS_XML,
        "no/lovtid/2025-06-20-101",
        adjudications_out=adjudications,
    )

    assert len(grouped) == 1
    base_id, ops = grouped[0]
    assert base_id == "no/lov/2018-06-08-28"
    assert [
        (op.action, op.target.path, op.destination.path if op.destination else None) for op in ops
    ] == [
        (StructuralAction.RENUMBER, (("section", "14a"),), (("section", "28b"),)),
        (StructuralAction.REPLACE, (("section", "28b"),), None),
    ]
    assert ops[0].sequence < ops[1].sequence
    assert "recovery:renumber_replacement" in ops[1].provenance_tags
    assert ops[1].payload is not None
    assert ops[1].payload.label == "28b"
    # The heading travels with the replacement: this is what corrects the stale
    # "§ 14 a. Studentombud" the bare renumber used to leave behind.
    assert ops[1].payload.children[0].text == "§ 28 b. Nasjonalt studentombud"
    assert not [
        a
        for a in adjudications
        if a.kind == "no_parse_structured_renumber_replacement_not_lowered"
    ]


def test_no_renumber_replacement_receipts_rather_than_guessing_which_move_it_rewrites() -> None:
    """W-32(b): one replacement clause, two moves — no attribution, no op.

    The shape of corpus witness ``no/lovtid/2024-06-21-42``, the one measured
    ``skal lyde`` move-block whose move arity is not one.
    """
    html_bytes = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="section" data-name="kapI" id="kapittel-1">
        <article class="document-change" data-document="lov/1998-07-17-56">
          <article class="change" data-move-part="lov/1998-07-17-56/§3-1/ledd/3;;lov/1998-07-17-56/§3-1/ledd/2 lov/1998-07-17-56/§3-1/ledd/4;;lov/1998-07-17-56/§3-1/ledd/3">
            <article class="defaultP">Tredje og fjerde ledd blir annet og tredje, hvor nytt tredje ledd skal lyde:</article>
            <article class="legalP">Regnskapspliktige skal utarbeide årsregnskap.</article>
          </article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        html_bytes, "no/lovtid/2024-06-21-42", adjudications_out=adjudications
    )

    _base_id, ops = grouped[0]
    assert [op.action for op in ops] == [StructuralAction.RENUMBER, StructuralAction.RENUMBER]
    receipts = [
        a
        for a in adjudications
        if a.kind == "no_parse_structured_renumber_replacement_not_lowered"
    ]
    assert len(receipts) == 1
    assert receipts[0].detail["reason"] == "move_arity_not_one"
    assert receipts[0].detail["move_count"] == 2


@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        # W-32(c): the witness address. Lovtidend spells the letter suffix with a
        # SPACE, which the bare label class could not span — and did not merely
        # fail on: it matched with the section cut short ("28") and the stray
        # letter absorbed into the ordinal phrase ("b andre"), which then failed
        # the ordinal table and returned NOTHING. A silent drop, not a receipt.
        (
            "§ 28 b andre ledd tredje punktum skal lyde",
            [(("section", "28b"), ("subsection", "2"), ("sentence", "3"))],
        ),
        # The single-letter Norwegian word that could have been prose rather than
        # a label occurs only as a real section in straffeprosessloven's
        # § 216 a-o run, so there is no prose reading to lose.
        (
            "§ 216 i første ledd tredje punktum skal lyde",
            [(("section", "216i"), ("subsection", "1"), ("sentence", "3"))],
        ),
        # Unsuffixed labels are untouched.
        (
            "§ 55 første ledd annet punktum skal lyde",
            [(("section", "55"), ("subsection", "1"), ("sentence", "2"))],
        ),
    ],
)
def test_no_spaced_section_label_resolves_in_the_ledd_carrying_sentence_grammar(
    lead: str, expected: list[tuple[tuple[str, str], ...]]
) -> None:
    """W-32(c): the widened label class, in the one production it was measured for."""
    specs = _infer_same_base_sentence_target_specs_from_lead(lead)
    assert [target.path for _action, target in specs] == expected


def test_no_spaced_section_label_is_not_widened_in_the_ledd_less_sentence_grammar() -> None:
    """W-32(c): the bound the op-level sweep forced, pinned so it cannot lapse.

    The ledd-less production resolves a section/sentence address with NO
    subsection step, and the structured lowering lets an inferred sentence spec
    OVERRIDE the markup's own — fuller — target. Widening here shortened
    ``no/lovtid/2025-06-20-38``'s ``§13a/ledd/1/setning/4`` to
    ``§13a/setning/4``: 2 ops right->wrong. The widening therefore stops at the
    ledd-carrying production, which always resolves all three steps.
    """
    assert (
        _infer_same_base_sentence_target_specs_from_lead(
            "§ 13 a nytt fjerde og femte punktum skal lyde"
        )
        == []
    )


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w32_eierseksjonsloven_payoff_chain_lowers_the_del_iv_erratum() -> None:
    """W-32 payoff chain, end to end, through UNCHANGED W-24 machinery.

    The multi-``bokstav`` lead was the sole blocker: with § 49 andre ledd
    bokstav e/f in the host op stream, W-24's ``no_corrected_host_op`` guard
    passes on its own terms and the Del IV erratum lowers. The erratum is
    verified by the sign-off-accepted byte relation against the host op it
    corrects, and it is sequenced after that op.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2020-12-04-137", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2020-12-04-137", adjudications_out=adjudications
        )
    )
    ops = grouped["no/lov/2017-06-16-65"]
    # 4 on base + the two recovered items + the erratum.
    assert len(ops) == 7
    item_ops = [op for op in ops if op.target.path[0] == ("section", "49")]
    assert [(op.action, op.target.path[-1]) for op in item_ops] == [
        (StructuralAction.REPLACE, ("item", "e")),
        (StructuralAction.INSERT, ("item", "f")),
        (StructuralAction.REPLACE, ("item", "f")),
    ]
    host, erratum = item_ops[1], item_ops[2]
    assert erratum.witness_rule_id == "no_rettelse_lowered"
    assert "rettelse:published_correction" in erratum.provenance_tags
    assert "rettelse_date:2020-12-07" in erratum.provenance_tags
    assert "rettelse_part:IV" in erratum.provenance_tags
    assert erratum.sequence > host.sequence
    assert host.payload is not None and erratum.payload is not None
    assert host.payload.text.replace("§ 22.", "§ 22 a .") == erratum.payload.text
    # The artifact's OTHER note corrects publication metadata ("Referansefeltet"),
    # which the IR does not model — a permanent recorded ceiling, not this
    # erratum's business. The Del IV note leaves no receipt behind.
    assert [a.detail["reason"] for a in adjudications if a.kind == "no_rettelse_not_lowered"] == [
        "no_same_act_item_address"
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w32_fagskoleloven_renumber_replacement_lands_but_the_erratum_still_receipts() -> None:
    """W-32(b)+(c) corpus witness, and the ONE blocker they do not clear.

    The replacement half now lowers (and corrects the stale heading), and the
    spaced-label widening moves the erratum's own receipt from
    ``no_part_scoped_target_address`` to ``no_corrected_host_op``. It stops
    there: the erratum addresses § 28 b ANDRE LEDD TREDJE PUNKTUM, while the
    host op is a whole-section REPLACE at § 28 b, and W-24's guard requires the
    corrected address to be in the op stream EXACTLY — an ancestor is not a
    match. Extending the guard to ancestor containment is a W-24 design
    decision, not a W-32 one, so the guard is left exactly as it is and this
    test pins the residue.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2025-06-20-101", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2025-06-20-101", adjudications_out=adjudications
        )
    )
    ops = grouped["no/lov/2018-06-08-28"]
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.RENUMBER, (("section", "14a"),)),
        (StructuralAction.REPLACE, (("section", "28b"),)),
    ]
    assert ops[1].payload is not None
    assert ops[1].payload.children[0].text == "§ 28 b. Nasjonalt studentombud"

    receipts = [a for a in adjudications if a.kind == "no_rettelse_not_lowered"]
    assert len(receipts) == 1
    assert receipts[0].detail["reason"] == "no_corrected_host_op"
    assert receipts[0].detail["base_id"] == "no/lov/2018-06-08-28"
    assert receipts[0].detail["part"] == "II"


# ── W-34: the payload cursor stops at law-switch leads ────────────────────────
# W-15 closed the part boundary. W-34 closes the same boundary one level down,
# at the numbered enumeration items inside a single part.


@pytest.mark.parametrize(
    "lead,expected",
    [
        # The witness: `no/lovtid/2015-06-19-65` items 59, 60, 61 — the three
        # leads the W-32-widened `§ 13 e …` lead swallowed.
        (
            "59. I lov 16. juni 1967 nr. 3 om fullmakt for Kongen til å forby "
            "redere å gi opplysninger m.m. til utenlandske myndigheter skal § 2 lyde:",
            "no/lov/1967-06-16-3",
        ),
        (
            "60. I lov 7. juli 1967 nr. 1 om tiltak mot diskriminering i "
            "internasjonal skipsfart skal § 2 lyde:",
            "no/lov/1967-07-07-1",
        ),
        (
            "61. I lov 15. desember 1967 nr. 9 om patenter gjøres følgende endringer:",
            "no/lov/1967-12-15-9",
        ),
        # 39 of the 299 crossed nodes carry NO ordinal and 37 of those are
        # ordinary leads, so the ordinal is not the signal and is not required.
        (
            "I lov 24. mai 1961 nr. 2 om forretningsbanker gjøres følgende endringer:",
            "no/lov/1961-05-24-2",
        ),
        # The nominative announcement, 3 of the 299.
        ("Lov 20. mai 2005 nr. 28 om straff endres slik:", "no/lov/2005-05-20-28"),
        # `I endringen(e) i lov …`: a lead that amends ANOTHER act's amendments
        # (`no/lovtid/2001-06-15-64`, 4 of the 299). Its citation sits 14-15
        # characters in — still inside the lead's own first sentence.
        (
            "I endringene i lov 11. juni 1971 nr. 52 om strafferegistrering "
            "gjøres følgende endringer:",
            "no/lov/1971-06-11-52",
        ),
    ],
)
def test_no_w34_law_switch_predicate_admits_every_genuine_lead_shape(
    lead: str, expected: str
) -> None:
    """W-34: the four prefix spellings the corpus census found, one case each."""
    assert _no_unstructured_law_switch_lead_base_id(lead) == expected


@pytest.mark.parametrize(
    "text",
    [
        # The two Lovdata run-on nodes: one lead's payload concatenated with the
        # NEXT lead into a single `legalP`. The citation sits 97 / 195 characters
        # in, BEHIND a completed sentence of quoted statutory text, so the node's
        # head is payload and the cursor must keep collecting.
        # `no/lovtid/2004-06-25-53` [180], verbatim.
        "I saker som ikke gjelder § 32 eller kap. VIII, styres skjønnet av "
        "lensmannen eller namsfogden. I lov 26. juni 1992 nr. 86 om "
        "tvangsfullbyrdelse og midlertidig sikring gjøres følgende endringer:",
        # `no/lovtid/2005-06-17-84` [81], verbatim.
        "I saker som ikke gjelder § 32 eller kap. VIII, styres skjønnet av "
        "lensmannen, namsfogden eller politistasjonssjef med sivile "
        "rettspleieoppgaver. I nr. 34 gjøres følgende endringer i endringene i "
        "lov 26. juni 1992 nr. 86 om tvangsfullbyrdelse og midlertidig sikring:",
        # Quoted statutory prose that merely cites a law.
        "Overtreding av taushetsplikt etter dette ledd kan straffes etter "
        "lov 20. mai 2005 nr. 28 om straff § 209.",
        # A bare citation with no amending tail names a law; it does not switch to it.
        "Lov 13. august 1915 nr. 5 om domstolene",
    ],
)
def test_no_w34_law_switch_predicate_rejects_quoted_and_run_on_text(text: str) -> None:
    """W-34's head-anchor guard, on the residue the census isolated."""
    assert _no_unstructured_law_switch_lead_base_id(text) is None


def test_no_w34_cursor_stops_at_a_numbered_law_switch_item() -> None:
    """W-34: the swallowed-lead defect, reduced to its smallest reproduction.

    Shaped after `no/lovtid/2015-06-19-65` [708]-[713]. On the pre-W-34 base the
    `§ 13 e …` sentence lead's payload run reaches the next `defaultP`, so it
    collects items 59 and 60 as payload and both items lose their op.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section data-name="kapI">
        <article class="legalP">58. I lov 16. desember 1966 nr. 9 om anke til Trygderetten gjøres følgende endringer:</article>
        <article class="defaultP">§ 13 e tredje ledd første punktum skal lyde:</article>
        <article class="legalP">Brudd på taushetsplikten straffes etter straffelovens § 209.</article>
        <article class="legalP">59. I lov 16. juni 1967 nr. 3 om fullmakt for Kongen skal § 2 lyde:</article>
        <article class="legalP">Den som overtrer bestemmelser gitt i medhold av denne lov, straffes med bøter.</article>
        <article class="legalP">60. I lov 7. juli 1967 nr. 1 om tiltak mot diskriminering skal § 2 lyde:</article>
        <article class="legalP">Den som overtrer bestemmelser gitt i medhold av denne lov, straffes med bot.</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == [
        "no/lov/1966-12-16-9",
        "no/lov/1967-06-16-3",
        "no/lov/1967-07-07-1",
    ]
    # The enclosing lead keeps its own payload and nothing else.
    trygderetten = grouped["no/lov/1966-12-16-9"]
    assert [op.target.path for op in trygderetten] == [
        (("section", "13e"), ("subsection", "3"), ("sentence", "1"))
    ]
    assert trygderetten[0].payload is not None
    assert trygderetten[0].payload.text == (
        "Brudd på taushetsplikten straffes etter straffelovens § 209."
    )
    # Both swallowed items lower against their OWN cited law.
    for base_id, expected_text in (
        (
            "no/lov/1967-06-16-3",
            "Den som overtrer bestemmelser gitt i medhold av denne lov, straffes med bøter.",
        ),
        (
            "no/lov/1967-07-07-1",
            "Den som overtrer bestemmelser gitt i medhold av denne lov, straffes med bot.",
        ),
    ):
        ops = grouped[base_id]
        assert [op.target.path for op in ops] == [(("section", "2"),)]
        assert ops[0].payload is not None
        assert ops[0].payload.children[0].text == expected_text


def test_no_w34_cursor_does_not_stop_at_a_run_on_payload_node() -> None:
    """W-34's must-not-stop side: the head-anchor guard keeps a payload whole.

    The run-on node's citation sits behind a completed sentence of quoted
    statutory text, so it stays payload rather than becoming a boundary. Shape
    from `no/lovtid/2004-06-25-53` [178]-[180].
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section data-name="kapI">
        <article class="defaultP">I lov 17. desember 1982 nr. 86 om rettsgebyr skal § 14 lyde:</article>
        <article class="legalP">Ved begjæring om utlegg kan namsmannen kreve at gebyret betales forskuddsvis.</article>
        <article class="legalP">I saker som ikke gjelder § 32 eller kap. VIII, styres skjønnet av lensmannen eller namsfogden. I lov 26. juni 1992 nr. 86 om tvangsfullbyrdelse og midlertidig sikring gjøres følgende endringer:</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == ["no/lov/1982-12-17-86"]
    ops = grouped["no/lov/1982-12-17-86"]
    assert [op.target.path for op in ops] == [(("section", "14"),)]
    assert ops[0].payload is not None
    # Both payload nodes survive: the run-on node is not torn off.
    assert len(ops[0].payload.children) == 2


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w34_straffeloven_consequential_act_stops_swallowing_its_own_items() -> None:
    """W-34 corpus witness: `no/lovtid/2015-06-19-65`, signed off as a cost at W-32.

    W-32(c)'s spaced-label widening made `§ 13 e tredje ledd første punktum skal
    lyde:` match the sentence family for the first time, so the lead consumed its
    payload run and swallowed items 59, 60 and 61. Measured 2026-08-07 on the
    post-W-32 base: items 59 and 60 lost their op entirely, and item 61's four
    ops sat on `no/lov/1966-12-16-9` — item 57's law, carried over because item
    58's citation ("lov 10. februar 1967 om behandlingsmåten i
    forvaltningssaker") has no `nr.` and resolves nothing.

    § 13 b and § 13 e stay on that stale carry-over: they are forvaltningsloven's
    sections, and no citation in the document can reach forvaltningsloven, whose
    id carries no number. That residue is item 58's unresolvable citation, not a
    cursor boundary, and is left exactly where W-34 found it.

    W-28 collects that residue, exactly as this docstring predicted: item 58's
    citation resolves to ``no/lov/1967-02-10-0`` and the two forvaltningsloven
    sections move off trygderettsloven onto the law they actually amend. The
    stale base is now empty and drops out of the grouping, so the assertion is
    inverted rather than edited — the residue the test was written to record no
    longer exists. Items 59, 60 and 61, the W-34 subject, are unmoved.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2015-06-19-65", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2015-06-19-65"))

    # Items 59 and 60 recover their op.
    assert [op.target.path for op in grouped["no/lov/1967-06-16-3"]] == [(("section", "2"),)]
    assert [op.target.path for op in grouped["no/lov/1967-07-07-1"]] == [(("section", "2"),)]
    # Item 61 (patentloven) takes its four ops off the stale base.
    assert [op.target.path for op in grouped["no/lov/1967-12-15-9"]] == [
        (("section", "8b"), ("subsection", "4"), ("sentence", "1")),
        (("section", "8c"), ("subsection", "2"), ("sentence", "1")),
        (("section", "57"),),
        (("section", "62"), ("subsection", "2")),
    ]
    # W-28: the two forvaltningsloven sections leave the stale carry-over for
    # the law item 58 names, and trygderettsloven keeps nothing at all.
    assert "no/lov/1966-12-16-9" not in grouped
    assert [op.target.path for op in grouped["no/lov/1967-02-10-0"]] == [
        (("section", "13b"), ("subsection", "2"), ("sentence", "last")),
        (("section", "13e"), ("subsection", "3"), ("sentence", "1")),
    ]


# ── W-35: law-switch leads trapped INSIDE a futureLegalArticle payload ────────
# W-34 stopped the payload cursor at a SIBLING law-switch lead. W-35 is the
# payload-internal sibling of that boundary: when Lovdata's markup closes an
# inserted section's ``futureLegalArticle`` late, the enumeration items that
# follow land INSIDE it, where no inter-node cursor can reach them.


def test_no_w35_trapped_leads_leave_the_payload_and_lower_on_their_own_law() -> None:
    """W-35: the split, reduced to its smallest reproduction.

    Shaped after `no/lovtid/2015-06-19-65` [630]-[631] — item 39's "§ 39 skal
    lyde:" payload, inside which items 40 and 41's leads and item 40's own
    quoted payload sit as ``legalP`` children. On the pre-W-35 base the § 39
    payload carries all four extra nodes and items 40 and 41 lower nothing.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section data-name="kapI">
        <article class="legalP">39. I lov 28. juni 1957 nr. 16 om friluftslivet skal § 39 lyde:</article>
        <article class="futureLegalArticle" data-name="§39">
          <span class="futureLegalArticleHeader">§ 39. (Straff.)</span>
          <article class="legalP">Den som forsettlig overtrer regler gitt i medhold av denne lov, straffes med bøter.</article>
          <article class="legalP">40. I lov 6. juli 1957 nr. 26 om samordning av pensjons- og trygdeytelser skal § 26 lyde:</article>
          <article class="legalP">Den som unnlater å gi opplysninger etter første ledd, straffes med bøter.</article>
          <article class="legalP">41. I lov 19. juni 1959 nr. 2 om avgifter vedrørende motorkjøretøyer skal § 2 lyde:</article>
          <article class="legalP">Med bot straffes den som unnlater å medvirke til kontrollundersøkelse.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == [
        "no/lov/1957-06-28-16",
        "no/lov/1957-07-06-26",
        "no/lov/1959-06-19-2",
    ]
    # The host section keeps its heading and its own body and NOTHING else: the
    # payload truncates to the children that precede the first trapped lead.
    friluftsloven = grouped["no/lov/1957-06-28-16"]
    assert [op.target.path for op in friluftsloven] == [(("section", "39"),)]
    payload = friluftsloven[0].payload
    assert payload is not None
    assert [child.text for child in payload.children] == [
        "(Straff.)",
        "Den som forsettlig overtrer regler gitt i medhold av denne lov, straffes med bøter.",
    ]
    # Both trapped items lower against their OWN cited law, each taking the
    # quoted text that followed it inside the element as its payload.
    samordning = grouped["no/lov/1957-07-06-26"]
    assert [op.target.path for op in samordning] == [(("section", "26"),)]
    assert samordning[0].payload is not None
    assert samordning[0].payload.children[0].text == (
        "Den som unnlater å gi opplysninger etter første ledd, straffes med bøter."
    )
    motorkjoretoy = grouped["no/lov/1959-06-19-2"]
    assert [op.target.path for op in motorkjoretoy] == [(("section", "2"),)]
    assert motorkjoretoy[0].payload is not None
    assert motorkjoretoy[0].payload.children[0].text == (
        "Med bot straffes den som unnlater å medvirke til kontrollundersøkelse."
    )


def test_no_w35_split_chains_through_a_freed_leads_own_future_article() -> None:
    """W-35: a freed lead whose payload is the NEXT ``futureLegalArticle`` sibling.

    `no/lovtid/2016-06-17-29` [163]-[165] in shape: § 8-8's element traps item
    8, whose own "ny § 10a" payload is the element that FOLLOWS it — and that
    element in turn traps item 9. Nothing special cases the chain; the split
    re-visits the freed nodes and the ordinary W-34 cursor does the rest.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section data-name="kapI">
        <article class="legalP">7. I lov 29. juni 2007 nr. 73 om eiendomsmegling gjøres følgende endringer:</article>
        <article class="defaultP">§ 8-8 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§8-8">
          <span class="futureLegalArticleHeader">§ 8-8. Behandling av tvister i klageorgan</span>
          <article class="legalP">Kongen kan godkjenne klageorgan for behandling av tvister mellom foretak og selger.</article>
          <article class="legalP">8. I lov 9. januar 2009 nr. 2 om kontroll med markedsføring skal ny § 10a lyde:</article>
        </article>
        <article class="futureLegalArticle" data-name="§10a">
          <span class="futureLegalArticleHeader">§ 10a. Informasjon om klageorgan</span>
          <article class="legalP">Næringsdrivende skal gi informasjon til forbrukere om klageorgan.</article>
          <article class="legalP">9. I lov 25. november 2011 nr. 44 om verdipapirfond skal § 2-13 lyde:</article>
          <article class="legalP">Departementet kan i forskrift fastsette nærmere regler om klagebehandling.</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == [
        "no/lov/2007-06-29-73",
        "no/lov/2009-01-09-2",
        "no/lov/2011-11-25-44",
    ]
    host = grouped["no/lov/2007-06-29-73"][0]
    assert host.target.path == (("section", "8-8"),)
    assert host.payload is not None
    assert [child.text for child in host.payload.children] == [
        "Behandling av tvister i klageorgan",
        "Kongen kan godkjenne klageorgan for behandling av tvister mellom foretak og selger.",
    ]
    # The freed item 8 takes the FOLLOWING element as its payload, truncated the
    # same way, and item 9 — trapped one level further in — lowers too.
    inserted = grouped["no/lov/2009-01-09-2"][0]
    assert inserted.action is StructuralAction.INSERT
    assert inserted.target.path == (("section", "10a"),)
    assert inserted.payload is not None
    assert [child.text for child in inserted.payload.children] == [
        "Informasjon om klageorgan",
        "Næringsdrivende skal gi informasjon til forbrukere om klageorgan.",
    ]
    assert [op.target.path for op in grouped["no/lov/2011-11-25-44"]] == [(("section", "2-13"),)]


def test_no_w35_split_leaves_a_quoting_inserted_section_whole() -> None:
    """W-35's must-not-split side, the W-21 § 412 hazard in miniature.

    An inserted section may quote a law reference, and may even read like an
    amending instruction, without being one. The predicate is W-34's, unchanged:
    the citation has to open the child's own first sentence. Neither child here
    does, so the element is untouched and no second base act appears.
    """
    amendment_xml = """<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section data-name="kapI">
        <article class="legalP">I lov 19. juni 2009 nr. 74 om skatteforvaltning gjøres følgende endringer:</article>
        <article class="defaultP">Ny § 412 skal lyde:</article>
        <article class="futureLegalArticle" data-name="§412">
          <span class="futureLegalArticleHeader">§ 412. Endringer i andre lover</span>
          <article class="legalP">Overtreding av taushetsplikt etter dette ledd kan straffes etter lov 20. mai 2005 nr. 28 om straff § 209.</article>
          <article class="legalP">Fra den tid loven trer i kraft gjøres endringer i andre lover. I lov 13. august 1915 nr. 5 om domstolene gjøres følgende endringer:</article>
        </article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")

    grouped = dict(iter_no_document_change_ops(amendment_xml, "no/lovtid/2025-01-01-1"))

    assert sorted(grouped) == ["no/lov/2009-06-19-74"]
    ops = grouped["no/lov/2009-06-19-74"]
    assert [op.target.path for op in ops] == [(("section", "412"),)]
    assert ops[0].payload is not None
    # All three children survive: the heading plus BOTH quoting paragraphs.
    assert len(ops[0].payload.children) == 3


def test_no_w35_split_is_a_no_op_when_no_child_switches_law() -> None:
    """W-35: the pass touches nothing it has no evidence for.

    Over the corpus only 41 of the 7,538 ``futureLegalArticle`` elements a
    payload run crosses contain a trapped lead. The other 7,497 have to come
    out of the pass as the very same element objects that went in.
    """
    element = etree.fromstring(
        """<article class="futureLegalArticle" data-name="§5">
             <span class="futureLegalArticleHeader">§ 5. Straff</span>
             <article class="legalP">Den som overtrer denne lov straffes med bøter.</article>
           </article>"""
    )
    children = [element]
    base_ids: list[str | None] = ["no/lov/2000-01-01-1"]
    part_indexes = [0]

    assert _split_no_trapped_payload_leads(children, base_ids, part_indexes) == 0
    assert children[0] is element
    assert base_ids == ["no/lov/2000-01-01-1"]
    assert part_indexes == [0]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w35_jernbaneundersokelsesloven_payload_sheds_its_trapped_items() -> None:
    """W-35 corpus witness: `no/lovtid/2015-06-19-65` item 209, the scan flip.

    W-34 made item 209's "skal § 27 lyde:" lower against its own law for the
    first time, and `no/lov/2005-06-03-34` went consistent -> divergent (0 -> 3)
    because Lovdata had put items 210 and 211's leads, and item 210's quoted
    payload, INSIDE item 209's ``futureLegalArticle``. The three
    CONSOLIDATED_MISSING rows were exactly those three nodes. On the W-34 base
    the § 27 payload has five children and items 210/211 lower nothing.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2015-06-19-65", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2015-06-19-65"))

    section_27 = [
        op for op in grouped["no/lov/2005-06-03-34"] if op.target.path == (("section", "27"),)
    ]
    assert len(section_27) == 1
    payload = section_27[0].payload
    assert payload is not None
    # Heading + the section's own single body paragraph, and no trapped tail.
    assert [child.text for child in payload.children] == [
        "Straff",
        (
            "Den som uaktsomt eller forsettlig overtrer bestemmelser gitt i eller i "
            "medhold av §§ 6, 7, 8, 12 første ledd, 14, 17, 23, 25 og 26 i loven, "
            "straffes med bøter dersom forholdet ikke går inn under strengere "
            "straffebestemmelse."
        ),
    ]

    # Items 210 and 211 lower against their own cited laws.
    assert [op.target.path for op in grouped["no/lov/2005-06-10-40"]] == [
        (("section", "13"), ("subsection", "1"), ("sentence", "1"))
    ]
    assert [op.target.path for op in grouped["no/lov/2005-06-10-41"]] == [
        (("section", "9-5"), ("subsection", "3"))
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w35_w21_section_412_witness_is_byte_identical() -> None:
    """W-35 negative corpus pin: the nested-payload act W-21 built its rule on.

    `no/lovtid/2009-06-19-74` is where the design risk is sharpest — its new
    § 412 "Endringer i andre lover" introduces a run of nested consequential
    items. Measured 2026-08-07: the act carries 184 ``futureLegalArticle``
    elements and NOT ONE of them holds a child the W-34 predicate fires on,
    because its nested items are ``defaultP`` siblings. The split is a no-op
    here and the whole op stream is unmoved.

    W-36 leaves that claim standing — the run-on pass fires ZERO times on this
    act — but W-28 moves the pin, because this act is also where the ledger's
    own second W-28 witness lives. Item 1 is Lappekodisillen 1751, a numberless
    citation, and the numbers below move for that reason alone:

    * 483 -> 484 ops: item 1's "§ 19 siste punktum skal lyde:" is the one op the
      act was dropping, and it is now emitted against `no/lov/1751-10-02-0`.
    * 214 -> 218 groups: four pre-numbering acts gain a group of their own —
      Lappekodisillen, forvaltningsloven `1967-02-10-0`, bilansvarslova
      `1961-02-03-0`, straffebestemmelser for utenlandske militærpersoner
      `1916-03-17-0` — every one of them a law whose ops previously sat on a
      neighbouring numbered act.
    * The digest follows from those two.

    What the pin still holds fixed is what it was written for: straffeloven 2005
    keeps exactly its 22 ops and utleveringsloven exactly its 1, so the W-21 and
    W-26 witnesses in this same act are untouched.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-06-19-74", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = iter_no_document_change_ops(html_bytes, "no/lovtid/2009-06-19-74")

    assert len(grouped) == 218
    assert sum(len(ops) for _base_id, ops in grouped) == 484

    by_base = dict(grouped)
    assert len(by_base["no/lov/2005-05-20-28"]) == 22
    assert len(by_base["no/lov/1975-06-13-39"]) == 1
    assert [op.target.path for op in by_base["no/lov/1751-10-02-0"]] == [
        (("section", "19"), ("sentence", "last"))
    ]

    def _flatten(node, prefix: str = "") -> list[str]:
        if node is None:
            return []
        lines = [f"{prefix}{node.kind}:{node.label or ''}:{node.text or ''}"]
        for child in node.children:
            lines.extend(_flatten(child, prefix + "  "))
        return lines

    digest = hashlib.sha256()
    for base_id, ops in grouped:
        for op in ops:
            destination = op.destination.path if op.destination is not None else ""
            digest.update(f"{base_id}|{op.action.value}|{op.target.path}|{destination}|".encode())
            digest.update("\n".join(_flatten(op.payload)).encode())
    assert digest.hexdigest()[:32] == "4ae75aec8c4e068a383edbf1fe360cff"


# ---------------------------------------------------------------------------
# W-36: Lovdata run-on nodes (a lead nested inside the previous item's payload)
# ---------------------------------------------------------------------------


def _run_on_node(html: str) -> etree._Element:
    return etree.fromstring(html.encode("utf-8"))


def test_no_w36_run_on_node_frees_the_lead_nested_in_its_payload() -> None:
    """W-36 witness, verbatim markup from ``no/lovtid/2004-06-25-53`` node [180].

    Lovdata closes the paragraph LATE: the next item's lead is a real element,
    but it hangs inside the previous item's payload node, four levels down
    through ``ul.defaultList`` -> ``li`` -> ``article.listArticle``. On the base
    the whole thing reads as one ``itertext()`` run, the node is not a lead, and
    the swallowed lead is collected as payload.
    """
    node = _run_on_node(
        '<article class="legalP">I saker som ikke gjelder § 32 eller kap. VIII, styres skjønnet av '
        'lensmannen eller namsfogden.<ul class="defaultList"><li data-li-identifier="34."><article '
        'class="listArticle"><article class="legalP">I lov 26. juni 1992 nr. 86 om tvangsfullbyrdelse '
        "og midlertidig sikring gjøres følgende endringer:</article></article></li></ul></article>"
    )

    # The node itself is not a law-switch lead -- that is why W-34's cursor
    # cannot stop at it and W-36 is needed at all.
    assert _no_unstructured_law_switch_lead_base_id(_no_element_lead_text(node)) is None

    split = _split_no_run_on_lead_node(node)
    assert split is not None
    truncated, freed = split

    assert _no_element_lead_text(truncated) == (
        "I saker som ikke gjelder § 32 eller kap. VIII, styres skjønnet av lensmannen eller namsfogden."
    )
    # The freed node is unwrapped down to the ``article`` the sibling walk reads;
    # a ``ul`` handed back as-is would be skipped and the lead lost a second time.
    assert [element.get("class") for element in freed] == ["legalP"]
    assert _no_unstructured_law_switch_lead_base_id(_no_element_lead_text(freed[0])) == (
        "no/lov/1992-06-26-86"
    )


def test_no_w36_run_on_split_holds_back_a_quoted_consequential_list() -> None:
    """W-36 negative control: identical markup, genuine content.

    ``no/lovtid/2009-06-19-100`` node [399] is plan- og bygningsloven's own
    § 35-1 consequential list being enacted verbatim, so the nested lead is the
    directive's PAYLOAD. The markup is byte-for-byte the shape the test above
    splits; only the head tells them apart, and it ends in the colon that opens
    a payload rather than in a completed sentence. Splitting it emitted a
    kulturminneloven op the act never made.
    """
    node = _run_on_node(
        '<article class="defaultP">§ 35-1 nr. 8 skal lyde:<ul class="defaultList">'
        '<li data-li-identifier="8."><article class="listArticle"><article class="legalP">'
        "I lov 9. juni 1978 nr. 50 om kulturminner (kulturminneloven) gjøres følgende endringer:"
        "</article></article></li></ul></article>"
    )

    assert _split_no_run_on_lead_node(node) is None


def test_no_w36_run_on_split_frees_a_consequential_part_intro() -> None:
    """The other side of the same guard (``no/lovtid/2004-05-28-29`` node [39]).

    A head that ends in a colon is not automatically a payload directive: the
    consequential-part intro "Fra den tid loven trer i kraft, gjøres følgende
    endringer i andre lover:" opens a LIST of amendments, and the intro marker
    W-30 measured is what says so.
    """
    node = _run_on_node(
        '<article class="legalP">Fra den tid loven trer i kraft, gjøres følgende endringer i andre '
        'lover:<ul class="defaultList"><li data-li-identifier="1."><article class="listArticle">'
        '<article class="legalP">I lov 10. juni 1966 nr. 5 om toll (tolloven) skal § 8 nr. 2 '
        "bokstav b lyde:</article></article></li></ul></article>"
    )

    split = _split_no_run_on_lead_node(node)
    assert split is not None
    assert _no_unstructured_law_switch_lead_base_id(_no_element_lead_text(split[1][0])) == (
        "no/lov/1966-06-10-5"
    )


def test_no_w36_run_on_split_does_not_tear_citing_prose() -> None:
    """W-36 negative control: the false positive the ledger predicted.

    ``no/lovtid/2015-06-19-48`` § 3 is quoted statutory prose whose later
    sentence opens "I den utstrekning en klage gjelder et spørsmål ..." and
    reads like a lead to a sentence-level predicate. It carries no element
    boundary, which is exactly why the split is anchored on markup rather than
    on sentences.
    """
    node = _run_on_node(
        '<article class="numberedLegalP">Klage avgjøres av Klagenemnda. Klagefristen er 3 uker '
        "regnet fra det tidspunkt ligningen utlegges. I den utstrekning en klage gjelder et "
        "spørsmål som Klagenemnda finner er av liten betydning for den utlignede skatt, kan "
        "Klagenemnda uten realitetsbehandling avvise klagen etter lov 13. juni 1980 nr. 24 om "
        "ligningsforvaltning gjøres følgende endringer i saksbehandlingen.</article>"
    )

    assert _split_no_run_on_lead_node(node) is None


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w36_corpus_witness_finansforetaksloven_item_11() -> None:
    """W-36 corpus witness: ``no/lovtid/2016-06-17-29`` item 11.

    The ledger priced this act at 3 stale ops behind a mid-node item 11. The
    lead sits inside item 10's ``numberedLegalP`` payload, one level below the
    ``futureLegalArticle`` W-35 already splits, so it is reached only by running
    both passes to a fixpoint -- this is the chain the second turn of the loop
    exists for. On the base the three ops bind eiendomsmeglingsloven.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2016-06-17-29", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2016-06-17-29"))

    assert [op.target.path for op in grouped["no/lov/2015-04-10-17"]] == [
        (("section", "2-10"), ("subsection", "4"), ("sentence", "1")),
        (("section", "2-11"), ("subsection", "3")),
        (("section", "16-3"),),
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w36_corpus_witness_allmennaksjeloven_item_17() -> None:
    """W-36 corpus witness: ``no/lovtid/2014-05-09-16`` items 8 and 17-20.

    The ledger priced this act at 9 stale ops behind mid-node items 17 and 20.
    Both leads hang off a ``(1)`` numbered paragraph, which is never a lead of
    its own, so nothing before W-36 could see them; item 8's lead is a run-on
    INSIDE a ``futureLegalArticle``, which is what makes the run-on pass have to
    precede W-35's rather than follow it.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2014-05-09-16", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2014-05-09-16"))

    # Item 17: allmennaksjeloven, which bound nothing at all on the base.
    assert [op.target.path for op in grouped["no/lov/1997-06-13-45"]] == [
        (("section", "8-1"), ("subsection", "2")),
        (("section", "8-1"), ("subsection", "3")),
        (("section", "12-2"), ("subsection", "1"), ("sentence", "1")),
        (("section", "16-9"), ("subsection", "1")),
    ]
    # Item 20: straffegjennomføringsloven.
    assert "no/lov/2001-05-18-21" in grouped


# ---------------------------------------------------------------------------
# W-28: law citations that carry no Lovtidend number at all
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("citation", "base_id"),
    [
        # The ledger's primary witness, ``no/lovtid/2009-01-30-7`` part I.
        (
            "I lov 10. februar 1967 om behandlingsmåten i forvaltningssaker (forvaltningsloven) "
            "skal § 19 fyrste ledd lyde:",
            "no/lov/1967-02-10-0",
        ),
        # ``no/lovtid/2009-06-19-74`` item 1 / ``no/lovtid/2015-06-19-65`` item 1.
        (
            "1. I lov 2. oktober 1751 Første Codicill og Tillæg til Grendse-Tractaten imellem "
            "Kongerigerne Norge og Sverrig Lapperne betreffende (Lappekodisillen) skal § 19 "
            "siste punktum lyde:",
            "no/lov/1751-10-02-0",
        ),
        # ``no/lovtid/2015-06-19-65`` item 42, via the intro-marker resolver.
        (
            "42. I lov 3. februar 1961 om ansvar for skade som motorvogner gjer "
            "gjøres følgende endring:",
            "no/lov/1961-02-03-0",
        ),
        # Nynorsk ``um`` instead of ``om``: servituttlova, the reason no tail
        # word can be required of the numberless spelling.
        (
            "I lov 29. november 1968 um særlege råderettar over framand eigedom (servituttlova) "
            "gjøres følgende endringer:",
            "no/lov/1968-11-29-0",
        ),
    ],
)
def test_no_w28_numberless_citation_resolves_the_zero_numbered_act(citation: str, base_id: str) -> None:
    """W-28: a pre-numbering act resolves to the ``-0`` id the corpus files it under.

    This is not a date-uniqueness guess. Lovdata's own DokumentID for these acts
    is date-only (``NL/lov/1967-02-10``) and the LTI filename writes the missing
    number as ``000``, which the id normalizer turns into ``-0``. Measured over
    the corpus: 22 of the 645 current-law ids end in ``-0``, every one of them
    1687-1968 and every one a genuine pre-numbering act.
    """
    assert _extract_no_law_citation_base_id(citation) == base_id
    assert _no_unstructured_law_switch_lead_base_id(citation) == base_id


@pytest.mark.parametrize(
    "citation",
    [
        # The number is present: the numbered head pattern must win, and the
        # numberless fallback must never see the citation.
        "59. I lov 16. juni 1967 nr. 3 om helsetjenesten skal § 2 lyde:",
        "I lov 22. mai 1981 nr. 25 om rettergangsmåten i straffesaker skal § 67 lyde:",
        "I midlertidig lov 17. juni 2005 nr. 95 om arbeids- og oppholdstillatelse skal § 4 lyde:",
        "Lov 20. mai 2005 nr. 28 om straff endres slik:",
        # The spaced ``nr 24`` spelling W-25 admitted.
        "I lov 13. juni 1980 nr 24 om ligningsforvaltning gjøres følgende endringer:",
    ],
)
def test_no_w28_a_numbered_citation_never_reaches_the_numberless_fallback(citation: str) -> None:
    """Rank control: the ``-0`` id can only ever come from a citation with no number."""
    resolved = _extract_no_law_citation_base_id(citation)
    assert resolved is not None
    assert not resolved.endswith("-0")


@pytest.mark.parametrize(
    "citation",
    [
        # `no/lovtid/2008-12-19-115`: Lovdata omits the number of an act that HAS
        # one. Ungated, W-28 answers ``no/lov/2001-04-20-0`` — an id no corpus
        # holds and a law that does not exist — and displaces the correct
        # ``no/lov/2001-04-20-13`` the declared field already supplies.
        "I lov 20. april 2001 om erstatning frå staten for personskade valda ved straffbar "
        "handling m.m. (valdsoffererstatningslova) skal § 11 første ledd lyde:",
        # The same shape at a date no attestation covers.
        "I lov 4. mars 1994 om noe skal § 2 lyde:",
    ],
)
def test_no_w28_unattested_date_does_not_resolve(citation: str) -> None:
    """W-28's closed set is the whole guard against guessing.

    A numberless citation resolves ONLY at a date the corpus itself attests as
    numberless. Everywhere else the omission is the drafter's, and answering
    would invent a law.
    """
    assert _extract_no_law_citation_base_id(citation) is None
    assert _extract_no_embedded_multi_act_lead(citation) is None
    assert _no_unstructured_law_switch_lead_base_id(citation) is None


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w28_numberless_law_dates_match_the_corpus() -> None:
    """The closed set is Lovdata's, re-derived here so drift fails loudly.

    Two independent attestations, either of which admits a date: the corpus
    files a current or LTI law under ``<date>-0``, or an amending act declares
    ``no/lov/<date>`` as a changed document. Measured 2026-08-07: 22 dates from
    the first, 20 from the second, 11 in both, union 31.
    """
    from lawvm.norway.grafter import _NO_NUMBERLESS_LAW_DATES
    from lawvm.norway.sources import (
        declared_change_targets_from_amendment,
        iter_no_amendment_artifacts,
        load_available_lti_law_ids,
        load_no_current_law_ids,
    )

    law_ids = load_no_current_law_ids(_NO_FARCHIVE_PATH) | load_available_lti_law_ids(_NO_FARCHIVE_PATH)
    zero_numbered = {law_id[len("no/lov/") : -2] for law_id in law_ids if law_id.endswith("-0")}
    declared: set[str] = set()
    for artifact in iter_no_amendment_artifacts(_NO_FARCHIVE_PATH):
        try:
            targets = declared_change_targets_from_amendment(artifact.payload)
        except Exception:  # pragma: no cover - a malformed header is not this test's subject
            continue
        for law_id in targets.law_ids:
            body = law_id.removeprefix("no/lov/")
            if len(body) == len("0000-00-00") and body.count("-") == 2:
                declared.add(body)

    assert len(zero_numbered) == 22
    assert len(declared) == 20
    assert len(zero_numbered & declared) == 11
    assert zero_numbered | declared == set(_NO_NUMBERLESS_LAW_DATES)
    # Closed by history: nothing enacted after Lovtidend numbering can enter.
    assert max(_NO_NUMBERLESS_LAW_DATES) == "1968-11-29"


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w28_corpus_witness_forvaltningsloven_section_19() -> None:
    """W-28 corpus witness: ``no/lovtid/2009-01-30-7`` part I.

    "I lov 10. februar 1967 om behandlingsmåten i forvaltningssaker
    (forvaltningsloven) skal § 19 fyrste ledd lyde:" resolved nothing on the
    base, and because it is the FIRST part there was no ``active_base_id`` to
    inherit, so the § 19 op was dropped outright rather than misbound.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-01-30-7", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2009-01-30-7"))

    assert [op.target.path for op in grouped["no/lov/1967-02-10-0"]] == [
        (("section", "19"), ("subsection", "1"))
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w28_corpus_witness_bilansvarslova_item_42() -> None:
    """W-28 corpus witness: ``no/lovtid/2015-06-19-65`` item 42.

    "42. I lov 3. februar 1961 om ansvar for skade som motorvogner gjer gjøres
    følgende endring:" -- one of the five enumeration gaps W-35's ordinal
    accounting left open, and the ledger filed it as a numberless citation
    rather than a run-on. It is: the item is an ordinary sibling lead whose only
    defect is the missing number.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2015-06-19-65", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2015-06-19-65"))

    assert [op.target.path for op in grouped["no/lov/1961-02-03-0"]] == [
        (("section", "20"), ("subsection", "2"))
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w39_collective_reenactment_witness_vaktvirksomhetsloven() -> None:
    """W-39 half (i) corpus witness: ``no/lovtid/2009-06-19-85`` part I.

    "I lov 5. januar 2001 nr. 1 om vaktvirksomhet skal følgende bestemmelser
    lyde:" re-enacts the whole law. On the base the tail was not in the action
    grammar, the part resolved no law, and the act bound NOTHING of it (7
    ``lead_base_unresolved`` receipts). The ordering assertion is the
    load-bearing half: "Nåværende § 12" names the PRE-amendment § 12, so every
    RENUMBER must be sequenced before every payload — in document order the act
    would move sections it has already overwritten.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-06-19-85", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2009-06-19-85"))
    ops = grouped["no/lov/2001-01-05-1"]

    renumbers = [op for op in ops if op.action is StructuralAction.RENUMBER]
    payloads = [op for op in ops if op.action is not StructuralAction.RENUMBER]
    assert all(op.destination is not None for op in renumbers)
    assert [
        (op.target.path[0][1], op.destination.path[0][1])
        for op in renumbers
        if op.destination is not None
    ] == [("12", "14"), ("13", "15"), ("16", "20"), ("17", "21"), ("18", "22")]
    assert max(op.sequence for op in renumbers) < min(op.sequence for op in payloads)

    # § 12/13/16/17/18 are renumber SOURCES, so their addresses are vacated and
    # the restatement is an INSERT; § 19 is an explicit "Ny § 19 skal lyde:".
    by_label = {op.target.path[0][1]: op.action for op in payloads}
    assert by_label == {
        "1": StructuralAction.REPLACE,
        "2": StructuralAction.REPLACE,
        "3": StructuralAction.REPLACE,
        "4": StructuralAction.REPLACE,
        "5": StructuralAction.REPLACE,
        "6": StructuralAction.REPLACE,
        "7": StructuralAction.REPLACE,
        "8": StructuralAction.REPLACE,
        "9": StructuralAction.REPLACE,
        "10": StructuralAction.REPLACE,
        "11": StructuralAction.REPLACE,
        "12": StructuralAction.INSERT,
        "13": StructuralAction.INSERT,
        "16": StructuralAction.INSERT,
        "17": StructuralAction.INSERT,
        "18": StructuralAction.INSERT,
        "19": StructuralAction.INSERT,
    }
    # Part III still lowers through the ordinary grammar, unchanged.
    assert [op.target.path for op in grouped["no/lov/1997-06-13-55"]] == [
        (("section", "16"), ("subsection", "1"))
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w39_collective_reenactment_refuses_whole_part_on_one_bad_member() -> None:
    """W-39 half (i) negative control: ``no/lovtid/2006-06-30-41``.

    The same collective lead, but its part interleaves bare-address members
    ("§ 7 annet ledd", "§ 8 annet ledd første punktum") with the restated
    sections. A bare address carries no verb, so its structure is exactly the
    ambiguity W-19's all-or-nothing rule refuses to guess at — and a partially
    applied re-enactment is a WRONG law, not a partial one. The whole part stays
    unlowered behind one typed receipt, and the act keeps binding nothing.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2006-06-30-41", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2006-06-30-41", adjudications_out=adjudications
        )
    )

    assert grouped == {}
    refusals = [
        a
        for a in adjudications
        if a.kind == NO_PARSE_COLLECTIVE_REENACTMENT_PART_UNRESOLVED
    ]
    assert len(refusals) == 1
    detail = refusals[0].detail
    assert detail["refusal"] == "member_outside_closed_set"
    assert detail["part_family"] == "collective_reenactment"
    assert detail["base_id"] == "no/lov/1999-07-16-69"
    assert detail["source_excerpt"] == "§ 7 annet ledd"


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w39_collective_reenactment_chapter_scope_is_not_a_part_lead() -> None:
    """W-39 half (i) boundary: the fourth family member is NOT a part lead.

    ``no/lovtid/2009-05-08-27`` carries "I kapitlene 34 og 35 skal følgende
    paragrafer lyde:" — the same tail, but scoping CHAPTERS inside a part whose
    own "I lov 27. juni 2008 nr. 71 … gjøres følgende endringer:" lead has
    already resolved the law. Admitting it as a part announcement would hand a
    whole 190-node part to the collective lowering on the strength of a tail
    alone, so the resolver is anchored on ``I lov``.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-05-08-27", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    assert (
        _no_collective_reenactment_lead_base_id(
            "I kapitlene 34 og 35 skal følgende paragrafer lyde:"
        )
        is None
    )
    assert (
        _no_collective_reenactment_lead_base_id(
            "I lov 5. januar 2001 nr. 1 om vaktvirksomhet skal følgende bestemmelser lyde:"
        )
        == "no/lov/2001-01-05-1"
    )

    adjudications: list = []
    iter_no_document_change_ops(
        html_bytes, "no/lovtid/2009-05-08-27", adjudications_out=adjudications
    )
    assert not [
        a
        for a in adjudications
        if a.kind == NO_PARSE_COLLECTIVE_REENACTMENT_PART_UNRESOLVED
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w39_part_law_map_resolves_the_witness_act() -> None:
    """W-39: the part→law map that half (ii)'s scope proof reads.

    Part II is the act's own commencement/transitional part and amends no law,
    so it is absent — which is what lets the ``Endrer`` header
    ``lov/2001-01-05-1`` match part I and nothing else.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-06-19-85", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    assert no_part_law_ids(html_bytes) == {
        "I": "no/lov/2001-01-05-1",
        "III": "no/lov/1997-06-13-55",
    }


def test_no_w67_section_renumber_shipped_form_still_routes_through_the_shipped_pattern() -> None:
    """W-67: the widening is additive, and the helper says so out loud.

    ``_no_unstructured_section_renumber_labels`` returns which of its two
    patterns matched precisely so that this ordering is a fact a test can assert
    rather than a claim a comment makes. Every lead the SHIPPED pattern accepts
    must still be answered by the shipped pattern — that is the whole safety
    argument for the change, and W-61's regressed first cut is why it is pinned.
    """
    assert _no_unstructured_section_renumber_labels("Nåværende § 9 blir ny § 10.") == ("9", "10", "shipped")
    assert _no_unstructured_section_renumber_labels("nåværende §9 blir ny §10") == ("9", "10", "shipped")
    assert _no_unstructured_section_renumber_labels("Nåværende § 24-8 blir ny § 24-9.") == (
        "24-8",
        "24-9",
        "shipped",
    )


def test_no_w67_section_renumber_widening_admits_both_relaxed_tokens() -> None:
    """W-67: the two tokens the shipped production hard-required.

    64 corpus refusals divide 20 / 36 / 8 across "qualifier only", "optional
    ``ny`` only" and "both", so all three splits are witnessed here with a
    corpus lead. Nynorsk and the older ``nuværende`` spelling come from W-61's
    measured qualifier set, which this production now shares.
    """
    # qualifier only — no/lovtid/2001-06-15-62 → straffeloven 1902
    assert _no_unstructured_section_renumber_labels("Gjeldende § 235 blir ny § 241.") == ("235", "241", "widened")
    # optional ``ny`` only — no/lovtid/2001-06-15-93 → no/lov/1999-07-02-61
    assert _no_unstructured_section_renumber_labels("Nåværende § 6-7 blir § 5-3.") == ("6-7", "5-3", "widened")
    # both — no/lovtid/2020-12-18-157 → no/lov/2010-06-04-21
    assert _no_unstructured_section_renumber_labels("Gjeldende § 10-10 blir ny § 10-13.") == (
        "10-10",
        "10-13",
        "widened",
    )
    # nynorsk, from W-61's shared set — no/lovtid/2002-06-21-46
    assert _no_unstructured_section_renumber_labels("Noverande § 5 blir ny § 7.") == ("5", "7", "widened")


def test_no_w67_section_renumber_widening_refuses_what_it_did_not_measure() -> None:
    """W-67: the widening stops exactly where its measurement stopped.

    ``§`` is a masculine noun, so ``nytt``/``nye`` before it is not this
    sentence and neither spelling occurs in the corpus refusals; a qualifier
    outside W-61's measured set carries meaning this production cannot read; and
    a lead with a trailing clause is a lead this grammar cannot fully account
    for, which lowers nothing rather than half of something.
    """
    assert _no_unstructured_section_renumber_labels("Nåværende § 9 blir nytt § 10.") is None
    assert _no_unstructured_section_renumber_labels("Nåværende § 9 blir nye § 10.") is None
    assert _no_unstructured_section_renumber_labels("Tidligere § 9 blir ny § 10.") is None
    assert _no_unstructured_section_renumber_labels("Gjeldende § 9 blir ny § 10 og skal lyde:") is None
    assert _no_unstructured_section_renumber_labels("Gjeldende §§ 9 og 10 blir §§ 11 og 12.") is None
    assert _no_unstructured_section_renumber_labels("§ 8-2 første ledd oppheves.") is None


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w67_gjeldende_section_renumber_lowers_on_the_witness_instrument() -> None:
    """W-67 corpus witness: ``no/lovtid/2020-12-18-157`` part ``kapV``.

    The lead is one leaf ``<article class="defaultP">`` whose whole text is
    ``Gjeldende § 10-10 blir ny § 10-13.`` — not a text-plane artefact of an
    ``itertext()`` walk across a part boundary (the mistake W-58 was
    mis-diagnosed with twice). It commands exactly the operation the shipped
    production emits and was refused whole with
    ``no_parse_unstructured_lead_unmatched`` because the qualifier is spelled
    ``Gjeldende``. The base act is scan candidate ``no/lov/2010-06-04-21``.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2020-12-18-157", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes,
            "no/lovtid/2020-12-18-157",
            adjudications_out=adjudications,
        )
    )

    renumbers = [
        op
        for op in grouped["no/lov/2010-06-04-21"]
        if op.action is StructuralAction.RENUMBER
        and op.destination is not None
        and op.source is not None
    ]
    assert [
        (op.target.path, cast(LegalAddress, op.destination).path, cast(OperationSource, op.source).raw_text)
        for op in renumbers
    ] == [
        ((("section", "10-10"),), (("section", "10-13"),), "Gjeldende § 10-10 blir ny § 10-13."),
    ]
    assert renumbers[0].witness_rule_id == "no_section_renumber_relabel"
    assert "Gjeldende § 10-10 blir ny § 10-13." not in {
        (item.detail or {}).get("source_excerpt")
        for item in adjudications
        if item.kind == "no_parse_unstructured_lead_unmatched"
    }


def test_no_w74_section_repeal_renumber_accepts_the_measured_population() -> None:
    """W-74: the 7 corpus leads whose destination the same lead vacates.

    All seven are here with their own text, because the production's claim is a
    measured population and a population is a list, not an adjective. Between them
    they witness every axis the pattern relaxes: ``§`` and ``§§``; a comma list, an
    ``og`` list, a ``til`` range and a singleton; ``oppheves`` and the nynorsk
    periphrastic ``blir oppheva``; a leading currency qualifier on the REPEAL
    sentence, a bokmål/nynorsk/``Gjeldende`` qualifier on the SHIFT sentence and no
    qualifier at all; ``blir § Y`` and ``blir ny § Y``; and W-32(c)'s
    letter-suffixed label ("§ 3 i").
    """
    # no/lovtid/2003-12-12-105 → no/lov/1980-06-13-24. ``og`` list, no ``ny``.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§§ 7-3 og 7-4 oppheves. Nåværende § 7-5 blir § 7-3."
    ) == (["7-3", "7-4"], "7-5", "7-3")
    # no/lovtid/2012-08-24-64 → husbankloven. THE witness: comma list, nynorsk
    # ``blir oppheva``, nynorsk qualifier ``Noverande``, and ``blir ny``.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 10."
    ) == (["10", "11", "12"], "13", "10")
    # no/lovtid/2013-06-14-40 → no/lov/1997-06-13-44. A qualifier on BOTH
    # sentences, and a singleton repeal.
    assert _no_unstructured_section_repeal_renumber_labels(
        "Nåværende § 5-8 oppheves. Nåværende § 5-7 blir ny § 5-8."
    ) == (["5-8"], "5-7", "5-8")
    # no/lovtid/2015-04-10-17 → no/lov/2005-06-10-44. A ``til`` RANGE, resolved by
    # the shipped ``_expand_no_section_range_labels`` and therefore to its two
    # endpoints for a hyphenated label — see the note on the list parser.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§§ 1-2 til 1-7 oppheves. Nåværende § 1-8 blir ny § 1-2."
    ) == (["1-2", "1-7"], "1-8", "1-2")
    # no/lovtid/2016-04-22-5 → no/lov/2005-04-01-15.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§ 10-4 oppheves. Nåværende § 10-5 blir § 10-4."
    ) == (["10-4"], "10-5", "10-4")
    # no/lovtid/2020-05-20-42 → markedsføringsloven. ``Gjeldende`` on both.
    assert _no_unstructured_section_repeal_renumber_labels(
        "Gjeldende § 41 oppheves. Gjeldende § 42 blir § 41."
    ) == (["41"], "42", "41")
    # no/lovtid/2022-06-17-47 → no/lov/1975-06-13-35. NO qualifier anywhere, and
    # letter-suffixed labels on every leg.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§ 3 i oppheves. § 3 j blir § 3 i."
    ) == (["3i"], "3j", "3i")


def test_no_w74_section_repeal_renumber_refuses_an_unvacated_destination() -> None:
    """W-74: the safety restriction, on the three corpus leads it refuses.

    All three are ``no/lovtid/2015-04-10-17`` cross-chapter shifts. Each vacates a
    chapter 7 label and writes into a chapter 2 one, so the lead itself proves
    nothing about whether the destination is free — and this production's entire
    licence to write is that proof. They keep their existing refusal receipt,
    which is the honest outcome and not a gap.

    The last case is the restriction stated as a property rather than as a corpus
    row: take the witness and change ONLY the destination, and the production must
    decline.
    """
    assert _no_unstructured_section_repeal_renumber_labels(
        "§ 7-1 oppheves. Nåværende § 7-2 blir ny § 2-2."
    ) is None
    assert _no_unstructured_section_repeal_renumber_labels(
        "§§ 7-3 til 7-6 oppheves. Nåværende § 7-7 blir ny § 2-3."
    ) is None
    assert _no_unstructured_section_repeal_renumber_labels(
        "§ 7-9 oppheves. Nåværende § 7-10 blir ny § 2-6."
    ) is None
    # The witness, with the destination moved off the repealed set by one label.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 9."
    ) is None


def test_no_w74_section_repeal_renumber_declines_the_neighbouring_shapes() -> None:
    """W-74: the five corpus leads that carry both verbs but are not this family.

    Four put the SHIFT sentence first, which this production must not read as a
    repeal-then-shift with the legs swapped; the fifth carries a trailing payload
    ("… blir ny § 27 og skal lyde:"), where lowering the shift alone would state a
    half-truth. All five are refused by construction rather than by a guard: ``§``
    and ``.`` are outside the repeal list's character class, and the shift tail is
    anchored at the destination label.
    """
    for lead in (
        "Nåværende § 27 oppheves. Nåværende § 27 a blir ny § 27 og skal lyde:",
        "Gjeldende § 7 blir § 8. Bestemmelsens annet ledd siste punktum oppheves.",
        "Endringen «Nåværende § 12-16 blir ny § 12-19 og skal lyde:» oppheves.",
        "Nåværende § 18-11 blir ny § 18-10. Paragrafens bokstav d og e oppheves.",
        "Nåværende § 2-1 a blir ny § 2-1. § 2-1 b oppheves.",
    ):
        assert _no_unstructured_section_repeal_renumber_labels(lead) is None, lead


def test_no_w74_section_repeal_renumber_leaves_the_shipped_single_sentence_families_alone() -> None:
    """W-74 is additive: it declines every lead a shipped production owns.

    It also sits LAST in the unstructured walk, after every shipped pattern has
    declined — but position is not the argument, disjointness is, and this pins
    it. The ledd-level sibling's own two-sentence lead is included because the two
    productions are neighbours in the same grammar and must not overlap.
    """
    for lead in (
        "§ 7-1 oppheves.",
        "§§ 7-3 og 7-4 oppheves.",
        "§§ 1-2 til 1-7 oppheves.",
        "Nåværende § 10 blir ny § 13.",
        "Gjeldende § 10-10 blir ny § 10-13.",
        "§ 5 annet ledd oppheves. Nåværende tredje ledd blir annet ledd.",
    ):
        assert _no_unstructured_section_repeal_renumber_labels(lead) is None, lead


def test_no_w74_section_repeal_list_refuses_a_member_it_cannot_read() -> None:
    """W-74: the list parser is all-or-nothing.

    A repeal list is the SET the destination conjunct is checked against and the
    set the REPEAL ops are minted from. One member it cannot resolve makes both
    wrong, so it refuses the whole lead rather than repealing the members it
    happens to understand.
    """
    assert _no_section_repeal_list_labels("10, 11 og 12") == ["10", "11", "12"]
    assert _no_section_repeal_list_labels("3 i") == ["3i"]
    assert _no_section_repeal_list_labels("1-2 til 1-7") == ["1-2", "1-7"]
    # Pure-digit ranges expand, which is the shipped helper's behaviour.
    assert _no_section_repeal_list_labels("10 til 13") == ["10", "11", "12", "13"]
    # A member with prose in it is not a label.
    assert _no_section_repeal_list_labels("10, 11 og siste") is None
    assert _no_section_repeal_list_labels("10, 11 og 12 andre ledd") is None


def _no_heading_boundary_ops(
    *nodes: str,
) -> list[tuple[StructuralAction | str, tuple[tuple[str, str], ...], IRNode | None]]:
    """Lower a run of unstructured nodes against a fixed base act.

    W-64's harness. The nodes are given as raw ``<article>`` markup so each test
    controls the CLASS of every node — this production's whole subject is that
    Lovdata marks a section heading and an amendment lead with the same
    ``defaultP`` class, so a helper that chose the classes would beg the question.
    """
    body = "\n".join(f"        {node}" for node in nodes)
    amendment_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments">
      <ul><li>lov/2003-12-12-108</li></ul>
    </dd>
    <main>
      <section data-name="kapI">
        <article class="defaultP">I lov 12. desember 2003 nr. 108 om kompensasjon av merverdiavgift for kommuner, fylkeskommuner mv. gjøres følgende endringer:</article>
{body}
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")
    ops = parse_no_amendment_ops(amendment_xml, "no/lovtid/2016-05-27-14")
    return [(op.action, op.target.path, op.payload) for op in ops]


def _no_payload_shape(payload: IRNode | None) -> list[tuple[str, str | None, str]]:
    if payload is None:
        return []
    return [
        (str(getattr(child.kind, "value", child.kind)), child.label, (child.text or "")[:60])
        for child in payload.children
    ]


def test_no_w64_section_heading_defaultp_is_payload_not_a_boundary() -> None:
    """W-64, the witness shape: ``no/lovtid/2003-12-19-129`` part II.

    Probed at the DOM nodes the walk reads: ``Ny § 37 a skal lyde:`` is a
    ``defaultP``, the section's heading ``Avgift og gebyr`` is ANOTHER
    ``defaultP``, and six ``legalP`` ledd follow it. The shipped boundary stopped
    on the heading and collected zero payload, so the insert refused and all six
    ledd were stranded (divergence rows ``chapter:5/section:37a/subsection:1-6``
    on veterinærloven).

    The heading must land as the section's HEADING, not as its first ledd: it is
    a ``defaultP``, and ``_parse_future_section`` reads ``defaultP`` children as
    ledd, so appending it verbatim would shift every real ledd's label by one.
    """
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">Ny § 37 a skal lyde:</article>',
        '<article class="defaultP">Avgift og gebyr</article>',
        '<article class="legalP">Kongen kan i forskrifter pålegge enhver å betale gebyr.</article>',
        '<article class="legalP">Avgifter og gebyrer er tvangsgrunnlag for utlegg.</article>',
    )
    assert [(action, path) for action, path, _payload in ops] == [
        (StructuralAction.INSERT, (("section", "37a"),)),
    ]
    assert _no_payload_shape(ops[0][2]) == [
        ("heading", None, "Avgift og gebyr"),
        ("subsection", "1", "Kongen kan i forskrifter pålegge enhver å betale gebyr."),
        ("subsection", "2", "Avgifter og gebyrer er tvangsgrunnlag for utlegg."),
    ]


def test_no_w64_heading_boundary_never_swallows_a_genuine_lead() -> None:
    """W-64's cardinal risk, pinned: absorbing a lead would DELETE an operation.

    Over all 3,089 unstructured artifacts, 569 (lead, next-``defaultP``) pairs sit
    behind a lead ending in ``lyde:``; exactly 21 of those successors parse as a
    lead today. Every one of the 21 is refused by three independent clauses at
    once, so no single clause is load-bearing. The cases below are those three
    clauses in isolation, each with the other two satisfied — the successor keeps
    its own op in all of them.
    """
    # Operative verb only (no ``§``, no terminal punctuation): a section-level
    # repeal spelled without its section sign is still an ACTION, not a heading.
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">§ 4 skal lyde:</article>',
        '<article class="defaultP">Bestemmelsen oppheves</article>',
        '<article class="legalP">Kommunen dekker driftsutgiftene.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == []
    # ``§`` only: the successor is an address, and an address is never a heading.
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">§ 4 skal lyde:</article>',
        '<article class="defaultP">§ 5 skal lyde:</article>',
        '<article class="legalP">Kommunen dekker driftsutgiftene.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == [
        (StructuralAction.REPLACE, (("section", "5"),)),
    ]
    # Terminal punctuation only: a heading is a bare noun phrase, a lead is a
    # sentence or a colon-command.
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">§ 4 skal lyde:</article>',
        '<article class="defaultP">Avgift og gebyr.</article>',
        '<article class="legalP">Kommunen dekker driftsutgiftene.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == []


def test_no_w64_heading_boundary_absorbs_at_most_one_defaultp() -> None:
    """W-64: the boundary still closes, one node later.

    Only the FIRST node after the lead is ever tested, so a second ``defaultP``
    ends the payload exactly as it always has. This is what bounds the blast
    radius: a run of ``defaultP`` nodes can never be swallowed wholesale, and the
    next lead in the run is always still read as a lead.
    """
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">Ny § 6 a skal lyde:</article>',
        '<article class="defaultP">Avgift og gebyr</article>',
        '<article class="legalP">Kongen kan i forskrifter pålegge enhver å betale gebyr.</article>',
        '<article class="defaultP">Ny § 6 b skal lyde:</article>',
        '<article class="defaultP">Klage</article>',
        '<article class="legalP">Vedtak kan påklages til departementet.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == [
        (StructuralAction.INSERT, (("section", "6a"),)),
        (StructuralAction.INSERT, (("section", "6b"),)),
    ]
    assert _no_payload_shape(ops[0][2]) == [
        ("heading", None, "Avgift og gebyr"),
        ("subsection", "1", "Kongen kan i forskrifter pålegge enhver å betale gebyr."),
    ]
    assert _no_payload_shape(ops[1][2]) == [
        ("heading", None, "Klage"),
        ("subsection", "1", "Vedtak kan påklages til departementet."),
    ]


def test_no_w64_heading_boundary_requires_a_payload_announcing_lead() -> None:
    """W-64: a lead that announces no payload can never gain one here.

    The first clause of the discriminator is that the lead ENDS in ``lyde:``. A
    repeal, a renumber or a bare law switch keeps its shipped answer, and so does
    a lead carrying INLINE payload after the colon — that is a different family
    and the boundary leaves it exactly where it was.
    """
    # A repeal lead: the following ``defaultP`` stays a boundary, so the heading
    # is read as its own (unmatched) node rather than becoming the repeal's text.
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">§ 4 oppheves.</article>',
        '<article class="defaultP">Avgift og gebyr</article>',
        '<article class="legalP">Kongen kan i forskrifter pålegge enhver å betale gebyr.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == [
        (StructuralAction.REPEAL, (("section", "4"),)),
    ]
    # An inline-payload lead: its text is already in the lead, and the next
    # ``defaultP`` is the next lead.
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">§ 4 skal lyde: Kongen kan gi forskrift.</article>',
        '<article class="defaultP">Avgift og gebyr</article>',
        '<article class="legalP">Kongen kan i forskrifter pålegge enhver å betale gebyr.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == [
        (StructuralAction.REPLACE, (("section", "4"),)),
    ]
    assert _no_payload_shape(ops[0][2]) == [("subsection", "1", "Kongen kan gi forskrift.")]


def test_no_w64_heading_only_lead_reaches_its_title() -> None:
    """W-64: the shipped heading-only production, whose sole blocker was the boundary.

    ``§ X overskriften skal lyde:`` puts the new heading in a ``defaultP`` with
    NOTHING after it, so clause 6's "a body node follows" is false and the second
    arm carries it: a lead whose shipped production wants the heading and nothing
    else says so in its own words. 23 corpus pairs over 18 instruments.
    """
    ops = _no_heading_boundary_ops(
        '<article class="defaultP">§ 26 overskriften skal lyde:</article>',
        '<article class="defaultP">Gebyr og avgift</article>',
        '<article class="defaultP">§ 27 oppheves.</article>',
    )
    assert [(action, path) for action, path, _p in ops] == [
        (StructuralAction.REPLACE, (("section", "26"),)),
        (StructuralAction.REPEAL, (("section", "27"),)),
    ]
    assert _no_payload_shape(ops[0][2]) == [("heading", None, "Gebyr og avgift")]
