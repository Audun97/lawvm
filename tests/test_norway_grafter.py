from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from typing import Sequence, cast

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
    NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED,
    NO_PARSE_ITEM_SET_RELABEL_LEDD_UNRESOLVED,
    NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED,
    NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED,
    NO_PARSE_SUBSTITUTION_MULTI_BASE_ADDRESS_LIST,
    NO_PARSE_SUBSTITUTION_MULTIPLE_ANNOUNCEMENTS,
    NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED,
    NO_CHAPTER_HEADING_PROVENANCE_TAG,
    NO_CHAPTER_REENACTMENT_PROVENANCE_TAG,
    NO_ITEM_PAYLOAD_SINGLE_TEXT_ARTICLE_PROVENANCE_TAG,
    NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG,
    NO_LEDD_SET_RELABEL_PROVENANCE_TAG,
    NO_PARSE_CHAPTER_HEADING_PAYLOAD_UNRESOLVED,
    NO_PARSE_CHAPTER_REENACTMENT_PAYLOAD_UNRESOLVED,
    NO_PARSE_MIXED_MEMBER_PAYLOAD_ARITY_MISMATCH,
    NO_PARSE_SECTION_RANGE_UNEXPANDABLE,
    NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED,
    NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED,
    _expand_no_section_range_labels,
    _no_chapter_heading_lead,
    _no_chapter_reenactment_lead,
    _no_ledd_repeal_reenact_specs,
    _no_mixed_punktum_ledd_member_specs,
    _no_nynorsk_ledd_repeal_targets,
    _no_repeated_ledd_noun_subsection_specs,
    NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT,
    NO_SUBSTITUTION_PROVENANCE_TAG,
    NOHeadingGroup,
    _no_structured_declared_own_payload,
    _no_structured_payload_is_declared,
    _extract_no_substitution_pairs,
    apply_no_ops_conserved,
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
    _no_antecedent_ledd_label,
    _no_antecedent_section_label,
    _no_item_relabel_indexes,
    _no_item_relabel_label,
    _no_item_set_relabel_pairs,
    _no_ledd_set_relabel_pairs,
    _no_punktum_repeal_targets,
    _no_punktum_set_relabel_pairs,
    _no_move_attr_skeleton,
    _no_normalize_move_attr,
    _no_ordered_set_relabel_pairs,
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
    NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED,
    NO_PARSE_STRUCTURED_SECTION_LABEL_CASED_FROM_CARRIER,
    NO_PARSE_STRUCTURED_SECTION_TARGET_SCOPED_TO_NEW_CHAPTER,
    NO_NEW_CHAPTER_SECTION_PROVENANCE_TAG,
    NO_REPLAY_NEW_CHAPTER_SECTION_RELOCATED_FROM_OCCUPIED_LABEL,
    _no_lead_announces_subdivision,
    _no_lead_names_chapter,
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
    # W-70: nothing here is repairable — the well-formed token carries the real
    # separator, so the stray-space rule cannot fuse ``§6`` onto it.
    assert adjudications[0].detail["normalization"] == "declined:no_rule_matched"


# ── W-70: the malformed ``data-move-part`` normalizer ─────────────────────────
#
# One test per rule and one per decline reason, because "the normalizer works"
# is not a claim any single corpus assertion can carry: what has to hold is that
# each repair fires on exactly its own defect and that everything else is left
# refused. The corpus population itself is pinned in
# ``tests/test_no_renumber_migration.py``.


def _move_attr_change_block(base: str, move: str, lead: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <article class="document-change" data-document="{base}">
      <article class="change" data-move-part="{move}">
        <article class="defaultP">{lead}</article>
      </article>
    </article>
  </body>
</html>
""".encode("utf-8")


def test_no_normalize_move_attr_repairs_a_stray_space_after_the_separator() -> None:
    """``a;; b`` is ONE pair Lovtidend split with a space, not two broken tokens."""
    result = _no_normalize_move_attr(
        ["lov/2025-01-01-1/§8/ledd/2;;", "lov/2025-01-01-1/§8/ledd/3"],
        base_id="no/lov/2025-01-01-1",
    )

    assert result.rule == "separator_spacing"
    assert result.pairs == (("lov/2025-01-01-1/§8/ledd/2", "lov/2025-01-01-1/§8/ledd/3"),)


def test_no_normalize_move_attr_repairs_the_alternate_separator_glyph() -> None:
    """``a::b`` is ``a;;b`` mistyped; source order is the token's own order."""
    result = _no_normalize_move_attr(
        ["lov/2025-01-01-1/§4/ledd/4::lov/2025-01-01-1/§4/ledd/5"],
        base_id="no/lov/2025-01-01-1",
    )

    assert result.rule == "alternate_separator"
    assert result.pairs == (("lov/2025-01-01-1/§4/ledd/4", "lov/2025-01-01-1/§4/ledd/5"),)


def test_no_normalize_move_attr_declines_a_value_with_no_separator_anywhere() -> None:
    """Two bare addresses do not say WHICH is the source, so nothing is guessed.

    This is the corpus shape of ``no/lovtid/2024-06-21-46``, and the decline is
    the second, independent reason that block stays refused (the first is the
    cross-base gate below).
    """
    result = _no_normalize_move_attr(
        ["lov/2025-01-01-1/§65/ledd/2", "lov/2025-01-01-1/§65/ledd/3"],
        base_id="no/lov/2025-01-01-1",
    )

    assert result == type(result)(None, "declined:no_rule_matched")


def test_no_normalize_move_attr_declines_when_a_token_names_another_base_act() -> None:
    """The gate that keeps W-70's two named blocks refused.

    Both carry addresses in an act the block is not filed under, because the
    archive mis-attributed the endringsdel to the preceding base. Repairing the
    separator there would relabel a law this instrument never addressed at this
    address, so the value is declined BEFORE any rule is tried.
    """
    result = _no_normalize_move_attr(
        ["lov/2010-03-26-9/§65/ledd/2;;", "lov/2010-03-26-9/§65/ledd/3"],
        base_id="no/lov/2022-05-12-28",
    )

    assert result.pairs is None
    assert result.rule == "declined:cross_base_tokens"


def test_no_normalize_move_attr_declines_a_partial_repair() -> None:
    """All or nothing: a rule that leaves ANY token malformed is not taken.

    ``a;; b;; c`` fuses only its second pair; the first token still has no
    destination, so the block keeps its receipts rather than lowering half a
    shift — the W-56 failure mode this codebase already paid for once.
    """
    result = _no_normalize_move_attr(
        [
            "lov/2025-01-01-1/§8/ledd/2;;",
            "lov/2025-01-01-1/§8/ledd/3;;",
            "lov/2025-01-01-1/§8/ledd/4",
        ],
        base_id="no/lov/2025-01-01-1",
    )

    assert result.pairs is None
    assert result.rule == "declined:no_rule_matched"


def test_no_normalize_move_attr_applies_at_most_one_rule() -> None:
    """Two different defects in one value is not a clean-up pass; it is a decline.

    Each rule must produce a FULLY well-formed token list on its own. Chaining
    them would make the repaired value depend on rule order in a way no receipt
    could explain, so the value is refused instead.
    """
    result = _no_normalize_move_attr(
        [
            "lov/2025-01-01-1/§4/ledd/4::lov/2025-01-01-1/§4/ledd/5",
            "lov/2025-01-01-1/§8/ledd/2;;",
            "lov/2025-01-01-1/§8/ledd/3",
        ],
        base_id="no/lov/2025-01-01-1",
    )

    assert result.pairs is None
    assert result.rule == "declined:no_rule_matched"


def test_no_normalize_move_attr_leaves_a_well_formed_value_alone() -> None:
    """The shipped path is not merely unchanged — it is not entered at all."""
    result = _no_normalize_move_attr(
        ["lov/2025-01-01-1/§4;;lov/2025-01-01-1/§5"], base_id="no/lov/2025-01-01-1"
    )

    assert result.pairs is None
    assert result.rule == "declined:well_formed"


def test_no_move_attr_skeleton_is_blind_to_separators_and_nothing_else() -> None:
    """The invariant every rule is checked against.

    Both repairs preserve the skeleton; a rewrite that swapped, dropped or
    invented an address would not, and the normalizer rejects any rule whose
    output moves it.
    """
    spaced = ["lov/2025-01-01-1/§8/ledd/2;;", "lov/2025-01-01-1/§8/ledd/3"]
    typo = ["lov/2025-01-01-1/§8/ledd/2::lov/2025-01-01-1/§8/ledd/3"]
    fused = ["lov/2025-01-01-1/§8/ledd/2;;lov/2025-01-01-1/§8/ledd/3"]
    swapped = ["lov/2025-01-01-1/§8/ledd/3;;lov/2025-01-01-1/§8/ledd/2"]

    assert _no_move_attr_skeleton(spaced) == _no_move_attr_skeleton(typo)
    assert _no_move_attr_skeleton(fused) == _no_move_attr_skeleton(spaced)
    assert _no_move_attr_skeleton(swapped) != _no_move_attr_skeleton(spaced)


def test_iter_no_document_change_ops_lowers_a_separator_spaced_move_attr() -> None:
    """The karanteneloven § 8 shape, end to end: two legs, one receipt, no refusal.

    The legs come out in the shipped REVERSED order — Lovtidend writes them in
    ascending prose order — so the 3->4 leg vacates before 2->3 fills, exactly as
    a well-formed attribute of the same shape would.
    """
    xml = _move_attr_change_block(
        "lov/2015-06-19-70",
        "lov/2015-06-19-70/§8/ledd/2;; lov/2015-06-19-70/§8/ledd/3 "
        "lov/2015-06-19-70/§8/ledd/3;; lov/2015-06-19-70/§8/ledd/4",
        "Nåværende § 8 andre og tredje ledd blir tredje og nytt fjerde ledd.",
    )
    adjudications: list[CompileAdjudication] = []

    grouped = dict(
        iter_no_document_change_ops(xml, "no/lovtid/2025-02-07-1", adjudications_out=adjudications)
    )

    ops = grouped["no/lov/2015-06-19-70"]
    assert [(op.action, op.target.path, op.destination.path if op.destination else ()) for op in ops] == [
        (
            StructuralAction.RENUMBER,
            (("section", "8"), ("subsection", "3")),
            (("section", "8"), ("subsection", "4")),
        ),
        (
            StructuralAction.RENUMBER,
            (("section", "8"), ("subsection", "2")),
            (("section", "8"), ("subsection", "3")),
        ),
    ]
    # A repaired leg is an ORDINARY structured leg: same provenance, and
    # deliberately NOT W-66's refuse-on-occupied tag — see the block comment at
    # the normalizer for why a separator repair must not change apply semantics.
    assert all(op.provenance_tags == ("base_act:no/lov/2015-06-19-70",) for op in ops)
    assert [item.kind for item in adjudications] == ["no_parse_structured_move_attr_normalized"]
    detail = adjudications[0].detail
    assert detail["rule_id"] == "no_parse_structured_move_attr_normalized"
    assert detail["phase"] == "parse"
    assert detail["family"] == "source_pathology"
    assert detail["blocking"] is False
    assert detail["quirks_disposition"] == "apply"
    assert detail["attr_name"] == "data-move-part"
    assert detail["reason"] == "separator_spacing"
    assert detail["normalized_legs"] == (
        "lov/2015-06-19-70/§8/ledd/2;;lov/2015-06-19-70/§8/ledd/3",
        "lov/2015-06-19-70/§8/ledd/3;;lov/2015-06-19-70/§8/ledd/4",
    )


def test_iter_no_document_change_ops_lowers_an_alternate_separator_move_attr() -> None:
    """The ``no/lovtid/2025-06-20-74`` shape: one glyph, one leg."""
    xml = _move_attr_change_block(
        "lov/2017-12-15-107",
        "lov/2017-12-15-107/§4/ledd/4::lov/2017-12-15-107/§4/ledd/5",
        "Nåværende § 4 fjerde ledd blir nytt femte ledd.",
    )
    adjudications: list[CompileAdjudication] = []

    grouped = dict(
        iter_no_document_change_ops(xml, "no/lovtid/2025-06-20-74", adjudications_out=adjudications)
    )

    assert [
        (op.action, op.target.path, op.destination.path if op.destination else ())
        for op in grouped["no/lov/2017-12-15-107"]
    ] == [
        (
            StructuralAction.RENUMBER,
            (("section", "4"), ("subsection", "4")),
            (("section", "4"), ("subsection", "5")),
        )
    ]
    assert [item.kind for item in adjudications] == ["no_parse_structured_move_attr_normalized"]
    assert adjudications[0].detail["reason"] == "alternate_separator"


def test_iter_no_document_change_ops_keeps_a_cross_base_malformed_move_attr_refused() -> None:
    """``no/lovtid/2024-06-21-46``, verbatim: refused, and the receipt says why.

    Nothing is lowered, the two per-token receipts survive unchanged, and each
    now carries the decline reason so the standing population pin can hold the
    REASON and not merely the count.
    """
    xml = _move_attr_change_block(
        "lov/2022-05-12-28",
        "lov/2010-03-26-9/§65/ledd/2 lov/2010-03-26-9/§65/ledd/3",
        "§ 65 nåværende andre ledd blir tredje ledd.",
    )
    adjudications: list[CompileAdjudication] = []

    grouped = iter_no_document_change_ops(
        xml, "no/lovtid/2024-06-21-46", adjudications_out=adjudications
    )

    assert grouped == []
    assert [item.kind for item in adjudications] == [
        "no_parse_malformed_structured_renumber_attr_skipped",
        "no_parse_malformed_structured_renumber_attr_skipped",
    ]
    assert {item.detail["normalization"] for item in adjudications} == {"declined:cross_base_tokens"}
    assert {item.detail["reason"] for item in adjudications} == {"missing_separator"}


def test_iter_no_document_change_ops_does_not_receipt_a_well_formed_move_attr() -> None:
    """Additivity, asserted where it matters: no new receipt on the shipped path."""
    xml = _move_attr_change_block(
        "lov/2025-01-01-1",
        "lov/2025-01-01-1/§4;;lov/2025-01-01-1/§5",
        "Nåværende § 4 blir ny § 5.",
    )
    adjudications: list[CompileAdjudication] = []

    grouped = dict(
        iter_no_document_change_ops(xml, "no/lovtid/2025-06-20-90", adjudications_out=adjudications)
    )

    assert [
        (op.action, op.target.path, op.destination.path if op.destination else ())
        for op in grouped["no/lov/2025-01-01-1"]
    ] == [(StructuralAction.RENUMBER, (("section", "4"),), (("section", "5"),))]
    assert [
        item.kind
        for item in adjudications
        if item.kind
        in {
            "no_parse_structured_move_attr_normalized",
            "no_parse_malformed_structured_renumber_attr_skipped",
        }
    ] == []


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


def test_w102_ledd_renumber_onto_an_occupied_slot_refuses_and_cascades() -> None:
    """W-102. konsesjonsloven § 4 under no/lovtid/2025-06-06-27 on a base that
    already carries the amendment: ``nåværende andre og tredje ledd blir tredje
    og nytt fjerde ledd`` runs 3 -> 4 onto an occupied fourth ledd. The leg
    refuses (no clearing), and 2 -> 3 then finds slot 3 still occupied and
    refuses too: the shift drops whole and the standing text survives."""
    statute = IRStatute(
        statute_id="no/lov/2003-11-28-98",
        title="Ledd renumber refusal test",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="4",
                    children=(
                        IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="ledd 1"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="new ledd 2, already in the base"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="old ledd 2"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="4", text="old ledd 3, in force"),
                    ),
                ),
            ),
        ),
    )
    source = OperationSource(statute_id="no/lovtid/2025-06-06-27")
    ops = [
        LegalOperation(
            op_id="renumber-3-4",
            sequence=1,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "4"), ("subsection", "3"))),
            destination=LegalAddress(path=(("section", "4"), ("subsection", "4"))),
            source=source,
        ),
        LegalOperation(
            op_id="renumber-2-3",
            sequence=2,
            action=StructuralAction.RENUMBER,
            target=LegalAddress(path=(("section", "4"), ("subsection", "2"))),
            destination=LegalAddress(path=(("section", "4"), ("subsection", "3"))),
            source=source,
        ),
    ]
    adjudications: list[CompileAdjudication] = []
    updated = apply_no_ops(statute, ops, adjudications_out=adjudications)
    section = updated.body.children[0]
    assert [child.text for child in section.children] == [
        "ledd 1", "new ledd 2, already in the base", "old ledd 2", "old ledd 3, in force",
    ]
    refusals = [a for a in adjudications if a.kind == "no_replay_ledd_renumber_occupied_destination_refused"]
    assert [a.op_id for a in refusals] == ["renumber-3-4", "renumber-2-3"]
    assert all(a.blocking for a in refusals)
    assert [(a.detail or {}).get("destination_path") for a in refusals] == [
        "section:4/subsection:4",
        "section:4/subsection:3",
    ]
    assert [(a.detail or {}).get("destination_was_renumber_source") for a in refusals] == [False, True]
    assert (refusals[0].detail or {}).get("rule_id") == "no_replay_ledd_renumber_occupied_destination_refused"
    assert not [a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"]
    assert not [a for a in adjudications if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"]

    # A free slot is untouched by the guard: on a base WITHOUT the amendment the
    # same two legs shift 3 -> 4 and 2 -> 3 as before.
    fresh = IRStatute(
        statute_id="no/lov/2003-11-28-98",
        title="Ledd renumber on a fresh base",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="4",
                    children=(
                        IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="ledd 1"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="old ledd 2"),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="3", text="old ledd 3, in force"),
                    ),
                ),
            ),
        ),
    )
    adjudications = []
    updated = apply_no_ops(fresh, ops, adjudications_out=adjudications)
    section = updated.body.children[0]
    assert [(child.label, child.text) for child in section.children] == [
        ("1", "ledd 1"), ("3", "old ledd 2"), ("4", "old ledd 3, in force"),
    ]
    assert not [a for a in adjudications if "occupied" in a.kind]


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

    # 22 -> 24 at W-66: the act's item for straffeloven 2005 carries
    # "Nåværende femte til sjette ledd blir sjette til syvende ledd." (§ 5), a
    # two-leg sibling-set relabel that was refused whole. The W-21/W-26 property
    # this pin exists for — WHICH act each item binds to — is unchanged.
    assert len(grouped["no/lov/2005-05-20-28"]) == 24
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

    # 13 -> 14 on folketrygdloven at W-98 (i): the act's nynorsk ``§ 3-15 fjerde
    # ledd blir oppheva.`` lowers to a REPEAL; nothing else in the act moves.
    assert {base_id: len(ops) for base_id, ops in grouped.items()} == {
        "no/lov/1991-11-08-76": 3,
        "no/lov/1997-02-28-19": 14,
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

    # W-66 re-pin: +1 on ``1956-12-07-1`` and +4 on ``2007-06-29-75``, all five of
    # them the sibling-set ledd relabel this act spells in prose and the grammar
    # used to refuse — ``Nåværende tredje ledd blir nytt fjerde ledd.`` (§ 3 a) and
    # ``Nåværende tredje til sjette ledd blir fjerde til syvende ledd.`` (§ 21-3,
    # three RENUMBERs plus the REPLACE→INSERT promotion of the co-located
    # ``§ 21-3 tredje ledd skal lyde:``). Nothing else in the act moves.
    assert {base_id: len(ops) for base_id, ops in grouped.items()} == {
        "no/lov/1956-12-07-1": 2,
        "no/lov/1985-06-21-83": 1,
        "no/lov/1991-08-30-71": 1,
        "no/lov/1997-06-13-44": 5,
        "no/lov/1997-06-13-45": 5,
        "no/lov/2007-06-29-75": 10,
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
    # 4 on base + the two recovered items + the erratum; 7 -> 8 at W-98 (f), the
    # act's ``Overskrifta til kapittel IV skal lyde:`` lowering to a heading-only
    # CHAPTER op. The § 49 item chain below is untouched.
    assert len(ops) == 8
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

    # 218 -> 227 at W-66c, and it is the group COUNT moving for the first time
    # since W-28 — the property this pin was written for. Nine base acts gain a
    # group of their own because the punktum-depth REPEAL is the FIRST op this
    # omnibus straffelov consequential act lowers for them, and eight of the nine
    # were never in its ``changesToDocuments`` list at all (see the binding note
    # in ``tests/test_norway_index.py``). Nothing is regrouped and no group is
    # lost.
    # 227 -> 228 at W-98 (h): ``no/lov/1961-06-09-1`` gains a group of its own
    # because the unqualified self-addressed shift "§ 33 tredje ledd blir nytt
    # annet ledd." is the first op this act lowers for it.
    assert len(grouped) == 228
    # 484 -> 493 at W-66: nine sibling-set ledd relabel legs across six of this
    # act's consequential items (straffeloven 2005 § 5, straffeprosessloven
    # § 13, § 41 a, § 32, § 47, § 50). The group COUNT is unmoved, which is the
    # base-binding property this pin was written for.
    # 493 -> 527 at W-66c: THIRTY-FOUR punktum-depth repeals, this act being the
    # single largest carrier of the family in the corpus. Six of them come from
    # three PLURAL leads ("§ 56 annet ledd første og annet punktum oppheves.",
    # "§ 17 første ledd annet og tredje punktum oppheves.", "§ 7 første ledd
    # annet og tredje punktum oppheves.") and each pair emits DESCENDING —
    # ``sentence:2`` before ``sentence:1`` — which is the production's own
    # ordering rule visible in the stream.
    # 527 -> 534 at W-98: the one relabel above, FIVE single-item leads whose
    # payload is the one ``legalP`` behind them (W-98 (d): "§ 29 første ledd
    # bokstav e skal lyde:" and "§ 30 annet ledd bokstav c" on 1988-06-24-64,
    # "§ 4-5 første ledd bokstav d" on kringkastingsloven, "§ 13-12 første ledd
    # bokstav e" on folketrygdloven, "§ 54 første ledd bokstav d" on
    # 2001-05-18-21), and one chapter heading ("Overskriften til kapittel 5 skal
    # lyde:" on 1998-03-20-10). Straffeloven 2005 and utleveringsloven are
    # untouched.
    assert sum(len(ops) for _base_id, ops in grouped) == 534

    by_base = dict(grouped)
    assert len(by_base["no/lov/2005-05-20-28"]) == 24
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
    # W-66 re-digest: the nine new relabel legs are part of the digested stream,
    # so the digest necessarily moves with them. Everything the digest was written
    # to hold — which base act each op binds to, and the payload under each — is
    # asserted above it and is unchanged.
    # W-66c re-digest, for the same reason and with the same guarantee: the 34
    # punktum repeals join the digested stream. They carry no payload at all, so
    # every payload the digest already held is byte-identical under it.
    # W-98 re-digest, same reason, same guarantee: the seven new ops above join
    # the stream (one relabel with no payload, five single-article item payloads
    # and one heading-only chapter payload); every payload the digest already
    # held is byte-identical under it.
    assert digest.hexdigest()[:32] == "ad4b7a2f6cb3d01f7d264b4318f6e9b6"


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
    # the shared ``_expand_no_section_range_labels``. Until W-98 (c) that
    # expander truncated a hyphenated range to its two ENDPOINTS (an under-repeal
    # this test pinned as the shipped behaviour); it now enumerates the range.
    assert _no_unstructured_section_repeal_renumber_labels(
        "§§ 1-2 til 1-7 oppheves. Nåværende § 1-8 blir ny § 1-2."
    ) == (["1-2", "1-3", "1-4", "1-5", "1-6", "1-7"], "1-8", "1-2")
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
    # Ranges expand through the shared ``_expand_no_section_range_labels`` —
    # chapter-numbered ones too since W-98 (c); a cross-chapter range refuses.
    assert _no_section_repeal_list_labels("1-2 til 1-7") == ["1-2", "1-3", "1-4", "1-5", "1-6", "1-7"]
    assert _no_section_repeal_list_labels("10 til 13") == ["10", "11", "12", "13"]
    assert _no_section_repeal_list_labels("2-4 til 3-2") is None
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


# --------------------------------------------------------------------------
# W-75: the multi-provision word substitution whose address list was lowered
# as N REPLACEs carrying the amendment's own prose.
# --------------------------------------------------------------------------


def _w75_substitution_change_html(*, announcement_node: str, change_node: str) -> bytes:
    """A ``document-change`` container holding one announcement and one change node.

    Raw markup, not a builder: the whole subject is which SIBLING carries the
    operative sentence, so a helper that placed the text for the test would beg
    the question.
    """
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="document-change" data-document="lov/2015-06-19-70">
{announcement_node}
{change_node}
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def _no_substitution_ops(grouped: list) -> list:
    return [op for _base, ops in grouped for op in ops if NO_SUBSTITUTION_PROVENANCE_TAG in op.provenance_tags]


def test_no_w69a_substitution_announcement_in_sibling_lowers_to_addressed_text_patches() -> None:
    """W-69a: the announcement sits in the preceding sibling; the list is the ADDRESSES.

    ``I følgende bestemmelser skal ordet «X» endres til «Y»:`` announces the
    operation and the ``change`` node carries only the provisions it applies to.
    W-75 refused the node because there was no producer for the construct;
    W-69a mints one addressed ``TEXT_PATCH`` per listed address, whose selector
    is the announced FROM term and whose replacement is the announced TO term —
    never the node's own prose, which is what the pre-W-75 lowering wrote.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node=(
                '<article class="defaultP">I følgende bestemmelser skal ordet '
                "«tilsettingsmyndigheten» endres til «ansettelsesmyndigheten»:</article>"
            ),
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1 '
                'lov/2015-06-19-70/§14/ledd/2">'
                '<article class="defaultP">§ 13 første ledd, § 14 andre ledd.</article>'
                "</article>"
            ),
        ),
        "no/lovtid/2025-02-07-1",
        adjudications_out=adjudications,
    )

    assert not [a for a in adjudications if a.kind.startswith("no_parse_substitution")]
    ops = _no_substitution_ops(grouped)
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.TEXT_PATCH, (("section", "13"), ("subsection", "1"))),
        (StructuralAction.TEXT_PATCH, (("section", "14"), ("subsection", "2"))),
    ]
    for op in ops:
        assert op.payload is None
        assert op.text_patch is not None
        assert op.text_patch.kind is TextPatchKindEnum.REPLACE
        assert op.text_patch.selector.match_text == "tilsettingsmyndigheten"
        assert op.text_patch.replacement == "ansettelsesmyndigheten"
        assert "scope:addressed" in op.provenance_tags
    # One group per (instrument, base act, announcement): the apply plane reads
    # it with the target path to recover the announcement's FROM-term set.
    assert len({op.group_id for op in ops}) == 1


def test_no_w69a_substitution_announcement_in_the_node_itself_lowers() -> None:
    """W-69a: Lovdata's other rendering puts the announcement INSIDE the change node.

    ``no/lovtid/2025-12-22-129`` and ``no/lovtid/2026-06-19-45`` write the
    announcement as the change node's own first line. Both renderings must reach
    the same production — a discriminator that only read the preceding sibling
    would leave these minting REPLACEs whose payload is the announcement.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node='<article class="defaultP">II</article>',
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1 '
                'lov/2015-06-19-70/§14/ledd/2">'
                '<article class="defaultP">I følgende bestemmelser skal «Markedsrådet» endres '
                "til «Konkurranseklagenemnda»:</article>"
                '<article class="defaultP">§ 13 første ledd, § 14 andre ledd.</article>'
                "</article>"
            ),
        ),
        "no/lovtid/2025-12-22-129",
        adjudications_out=adjudications,
    )

    assert not [a for a in adjudications if a.kind.startswith("no_parse_substitution")]
    ops = _no_substitution_ops(grouped)
    assert len(ops) == 2
    assert {op.text_patch.selector.match_text for op in ops if op.text_patch} == {"Markedsrådet"}
    assert {op.text_patch.replacement for op in ops if op.text_patch} == {"Konkurranseklagenemnda"}


def test_no_w69a_multiple_announcements_refuse_the_whole_node() -> None:
    """W-69a S1: two announcements, one flat address list — refuse whole.

    ``no/lovtid/2026-06-19-48`` concatenates FOUR announcement openers into one
    governing text and hangs 82 addresses over 35 base acts off them. Nothing in
    ``data-change-part`` says which address belongs to which announcement, and
    the damage is measurable rather than theoretical: most of the corpus
    addresses that resolve without carrying their announced term are that node's
    later-announcement addresses measured against the first announcement's pair.
    Partial acceptance of such a node is forbidden — no op is minted at all.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node='<article class="defaultP">II</article>',
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1 '
                'lov/2015-06-19-70/§14/ledd/2">'
                '<article class="defaultP">I følgende bestemmelser skal ordene «gjeldsforhandling» '
                "og «gjeldsforhandlingen» endres til henholdsvis «rekonstruksjonsforhandling» og "
                "«rekonstruksjonsforhandlingen»: I følgende bestemmelser skal ordet "
                "«gjeldsforhandlinger» endres til «rekonstruksjonsforhandling»:</article>"
                "</article>"
            ),
        ),
        "no/lovtid/2026-06-19-48",
        adjudications_out=adjudications,
    )

    assert _no_substitution_ops(grouped) == []
    refusals = [a for a in adjudications if a.kind == NO_PARSE_SUBSTITUTION_MULTIPLE_ANNOUNCEMENTS]
    assert len(refusals) == 1
    assert refusals[0].blocking is True
    assert refusals[0].detail["announcement_count"] == 2
    assert refusals[0].detail["refused_address_count"] == 2


def test_no_w69a_address_list_naming_another_base_act_refuses_the_whole_node() -> None:
    """W-69a S2: the address list must name exactly the enclosing block's base act.

    ``no/lovtid/2025-06-20-39`` lists addresses across six different acts under
    one ``document-change`` bound to one of them. Lowering that list binds a
    substitution to laws its addresses do not belong to.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node='<article class="defaultP">II</article>',
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1 '
                'lov/1991-07-04-47/§26a/ledd/2">'
                '<article class="defaultP">I følgende bestemmelser skal ordet «X» endres '
                "til «Y»:</article>"
                "</article>"
            ),
        ),
        "no/lovtid/2025-06-20-39",
        adjudications_out=adjudications,
    )

    assert _no_substitution_ops(grouped) == []
    refusals = [a for a in adjudications if a.kind == NO_PARSE_SUBSTITUTION_MULTI_BASE_ADDRESS_LIST]
    assert len(refusals) == 1
    assert refusals[0].detail["address_bases"] == (
        "no/lov/1991-07-04-47",
        "no/lov/2015-06-19-70",
    )


def test_no_w69a_unparseable_pair_grammar_keeps_the_w75_refusal() -> None:
    """W-69a S3: the W-75 receipt survives, scoped to the pair grammar alone.

    Two full substitutions written sequentially in one announcement
    (``formuleringene «A» endres til «B» og «C» endres til «D»``) do not parse
    to a pair set under this grammar. Which pair applies where is then unknown,
    so the node refuses exactly as it did before W-69a — with the same receipt.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node='<article class="defaultP">II</article>',
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1">'
                '<article class="defaultP">I følgende bestemmelser skal formuleringene '
                "«har vist alvorlige atferdsvansker» endres til «utsetter sin utvikling for "
                "alvorlig fare» og «å ha vist annen form for utpreget normløs atferd» endres "
                "til «andre utpreget skadelige handlinger»:</article>"
                "</article>"
            ),
        ),
        "no/lovtid/2025-06-20-39",
        adjudications_out=adjudications,
    )

    assert _no_substitution_ops(grouped) == []
    refusals = [a for a in adjudications if a.kind == NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED]
    assert len(refusals) == 1
    assert refusals[0].blocking is True
    assert refusals[0].detail["pair_shape"] == "unpaired_1_3"


def test_no_w69b_sentence_addresses_lower_alongside_their_ledd_siblings() -> None:
    """W-69b: ``setning/N`` is in scope, and it lowers per ADDRESS like the rest.

    W-69a refused this address typed
    (``no_parse_substitution_sentence_address_out_of_scope``, 21 corpus
    receipts) because the apply plane materialized sentence children only on
    the structural branch, AFTER the text-patch branch had returned, so a
    sentence-addressed TEXT_PATCH could not resolve at all. W-69b lifts the
    materializer onto both branches, so the sentence address lowers to an
    ordinary addressed TEXT_PATCH sitting beside its ledd sibling — no
    redirection to the parent ledd, which is the reading that fails OPEN when
    the term recurs in a sibling sentence.

    The retired receipt kind must be GONE from the parse plane, not merely
    unfired: an address list mixing both depths raises no substitution
    adjudication at all now.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node=(
                '<article class="defaultP">I følgende bestemmelser skal ordet '
                "«tilsettingsmyndigheten» endres til «ansettelsesmyndigheten»:</article>"
            ),
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1 '
                'lov/2015-06-19-70/§13/ledd/2/setning/1">'
                '<article class="defaultP">§ 13 første ledd, § 13 andre ledd første '
                "punktum.</article>"
                "</article>"
            ),
        ),
        "no/lovtid/2025-02-07-1",
        adjudications_out=adjudications,
    )

    assert not [a for a in adjudications if a.kind.startswith("no_parse_substitution")]
    assert not [
        a for a in adjudications if a.kind == "no_parse_substitution_sentence_address_out_of_scope"
    ]
    ops = _no_substitution_ops(grouped)
    assert [op.target.path for op in ops] == [
        (("section", "13"), ("subsection", "1")),
        (("section", "13"), ("subsection", "2"), ("sentence", "1")),
    ]
    # Both carry the same announced pair; only the address depth differs.
    assert {
        (op.text_patch.selector.match_text, op.text_patch.replacement) for op in ops if op.text_patch
    } == {("tilsettingsmyndigheten", "ansettelsesmyndigheten")}


def test_no_w69a_henholdsvis_is_from_by_to_not_address_positional() -> None:
    """W-69a: ``henholdsvis`` names a PAIR SET applying to every listed address.

    The queue entry read it as address-positional (address 1 takes term 1). It
    is not: *"ordene «namsmannen» og «namsmannens» endres til henholdsvis
    «namsfogden» og «namsfogdens»"* is a FROM × TO zip, and the resulting pair
    set applies to all of ``§§ 2-2, 2-3, …``. So N addresses × M pairs is N*M
    ops carrying the SAME pair set, and which one fires is decided at apply
    against the provision's own text.
    """
    assert _extract_no_substitution_pairs(
        "I følgende bestemmelser endres ordene «namsmannen» og «namsmannens» til "
        "henholdsvis ordene «namsfogden» og «namsfogdens»: §§ 2-2 og 2-3."
    ) == (
        (("namsmannen", "namsfogden"), ("namsmannens", "namsfogdens")),
        "positional_pairs_verb_first_henholdsvis",
    )
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node='<article class="defaultP">II</article>',
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13 '
                'lov/2015-06-19-70/§14">'
                '<article class="defaultP">I følgende bestemmelser endres ordene «namsmannen» '
                "og «namsmannens» til henholdsvis ordene «namsfogden» og «namsfogdens»: "
                "§§ 13 og 14.</article>"
                "</article>"
            ),
        ),
        "no/lovtid/2026-06-19-45",
        adjudications_out=adjudications,
    )
    ops = _no_substitution_ops(grouped)
    assert [
        (op.target.path, op.text_patch.selector.match_text, op.text_patch.replacement)
        for op in ops
        if op.text_patch
    ] == [
        ((("section", "13"),), "namsmannen", "namsfogden"),
        ((("section", "13"),), "namsmannens", "namsfogdens"),
        ((("section", "14"),), "namsmannen", "namsfogden"),
        ((("section", "14"),), "namsmannens", "namsfogdens"),
    ]


def test_no_w69a_whole_word_scanner_is_the_regex_it_replaces() -> None:
    """The matching rule is ``(?<!\\w)TERM(?!\\w)``; the implementation is a scan.

    A per-FROM-term ``re.compile`` of an f-string is the frozen-residue shape
    the FW-07/FW-08 ratchets keep out of a parser module, so the predicate is
    written with ``str.find`` plus a boundary test. That is only legitimate if
    it is the SAME predicate, including the non-overlapping advance (``"a a"``
    occurs once in ``"a a a"``, not twice), so the equivalence is proven here
    rather than asserted in a comment.
    """
    import random
    import re as _re

    from lawvm.norway.grafter import _no_whole_word_count

    assert _no_whole_word_count("a a a", "a a") == 1
    assert _no_whole_word_count("namsmannens kontor", "namsmannen") == 0
    assert _no_whole_word_count("namsmannen og namsmannens", "namsmannen") == 1
    assert _no_whole_word_count("", "x") == 0
    assert _no_whole_word_count("x", "") == 0

    random.seed(20690)
    alphabet = "ab X_ ,.-«»\u00e50"
    for _ in range(4000):
        text = "".join(random.choice(alphabet) for _ in range(random.randint(0, 30)))
        term = "".join(random.choice(alphabet) for _ in range(random.randint(1, 5)))
        expected = len(_re.findall(rf"(?<!\w){_re.escape(term)}(?!\w)", text))
        assert _no_whole_word_count(text, term) == expected, (text, term)


# ── W-69a apply plane: S6 + S7, where the addressed node's text is in hand ───


def _w69a_substitution_op(
    sequence: int,
    *,
    section: str,
    from_term: str,
    to_term: str,
    group: str = "g1",
) -> LegalOperation:
    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.TEXT_PATCH,
        target=LegalAddress(path=(("section", section),)),
        text_patch=TextPatchSpec(
            kind=TextPatchKindEnum.REPLACE,
            selector=TextSelector(match_text=from_term, occurrence=0),
            replacement=to_term,
        ),
        source=OperationSource(statute_id="no/lovtid/9999-01-01-1", raw_text="ann", title="x"),
        provenance_tags=("base_act:no/lov/1999-01-01-1", "scope:addressed", NO_SUBSTITUTION_PROVENANCE_TAG),
        group_id=group,
    )


def _w69a_statute(*texts: str) -> IRStatute:
    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=tuple(
                IRNode(kind=IRNodeKind.SECTION, label=str(i), text=text)
                for i, text in enumerate(texts, start=1)
            ),
        ),
    )


def test_no_w69a_apply_replaces_the_announced_term_and_nothing_else() -> None:
    """The happy path: one whole-word occurrence, one replacement, one section."""
    before = _w69a_statute("Namsmannen varsler. Tilsettingsmyndigheten treffer vedtaket.", "Uendret.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [_w69a_substitution_op(1, section="1", from_term="Tilsettingsmyndigheten", to_term="Ansettelsesmyndigheten")],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children] == [
        "Namsmannen varsler. Ansettelsesmyndigheten treffer vedtaket.",
        "Uendret.",
    ]
    assert not [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]


def test_no_w69a_apply_refuses_when_the_term_is_absent() -> None:
    """The addressed provision ALREADY carries the amendment — W-66 finding (v).

    An archived base edition that already reads the NEW word has nothing to
    substitute; writing anything would be inventing a change. Refuse, typed, so
    the reason survives instead of dissolving into a content-identical no-op —
    the two are the same state change and very different evidence.
    """
    before = _w69a_statute("Ansettelsesmyndigheten treffer vedtaket.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [_w69a_substitution_op(1, section="1", from_term="tilsettingsmyndigheten", to_term="ansettelsesmyndigheten")],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children] == ["Ansettelsesmyndigheten treffer vedtaket."]
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert [a.detail["reason"] for a in refusals] == ["absent"]
    assert (refusals[0].detail["whole_word"], refusals[0].detail["substring"]) == (0, 0)
    assert not [a for a in adjudications if a.kind == "replay_noop"]


def test_no_w69a_apply_refuses_a_case_only_match() -> None:
    """``inflection_only``: the term is present only under case folding.

    Naming note, because the label is the design's and the design's word is
    looser than the test: this conjunct measures a CASE-insensitive-only match,
    not a morphological inflection. The genuine morphological case — a Norwegian
    genitive ``-s`` — is caught by ``substring_only``, which is why that reason
    exists separately. Matching is case-SENSITIVE: an announcement quotes the
    exact word it replaces, and folding case would let a sentence-initial
    occurrence take a lower-case replacement.
    """
    before = _w69a_statute("Tilsettingsmyndigheten treffer vedtaket.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [_w69a_substitution_op(1, section="1", from_term="tilsettingsmyndigheten", to_term="ansettelsesmyndigheten")],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children] == ["Tilsettingsmyndigheten treffer vedtaket."]
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert [a.detail["reason"] for a in refusals] == ["inflection_only"]
    assert (refusals[0].detail["substring"], refusals[0].detail["case_insensitive"]) == (0, 1)


def test_no_w69a_apply_refuses_a_genitive_rather_than_fire_inside_a_longer_word() -> None:
    """W-69a's matching rule is WHOLE WORD, and this is what it costs.

    ``tilsettingsmyndighetens`` contains ``tilsettingsmyndigheten``. Exact
    substring matching would fire and produce ``ansettelsesmyndighetens`` — which
    happens to be right here and would be wrong in the general case, because
    nothing in the announcement licenses a match inside a longer word. Measured
    price over the corpus: exactly one live divergence row (karanteneloven
    ``§ 20 fjerde ledd``) stays open, honestly.
    """
    before = _w69a_statute("Vedtaket treffes av tilsettingsmyndighetens leder.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [_w69a_substitution_op(1, section="1", from_term="tilsettingsmyndigheten", to_term="ansettelsesmyndigheten")],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children] == ["Vedtaket treffes av tilsettingsmyndighetens leder."]
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert [a.detail["reason"] for a in refusals] == ["substring_only"]
    assert refusals[0].detail["substring"] == 1
    assert refusals[0].detail["whole_word"] == 0


def test_no_w69a_apply_refuses_more_than_one_occurrence() -> None:
    """``_apply_no_text_replace`` is an unguarded recursive ``str.replace``.

    It honours neither ``TextSelector.occurrence`` nor a word boundary, so the
    only way an addressed substitution can mean "replace THE occurrence" is for
    the parse-to-apply conjunction to prove there is exactly one. Two occurrences
    refuse rather than take both.
    """
    before = _w69a_statute("Markedsrådet avgjør. Markedsrådet kan delegere.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [_w69a_substitution_op(1, section="1", from_term="Markedsrådet", to_term="Konkurranseklagenemnda")],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children] == ["Markedsrådet avgjør. Markedsrådet kan delegere."]
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert [a.detail["reason"] for a in refusals] == ["multiple"]
    assert refusals[0].detail["whole_word"] == 2


def test_no_w69a_apply_counts_occurrences_across_the_whole_addressed_subtree() -> None:
    """A section-depth address covers its ledd; the count is over all of them.

    Counted node by node on OWN text and summed — exactly what
    ``_apply_no_text_replace``'s recursion does. A term appearing once in each of
    two ledd of the addressed section is two occurrences and refuses.
    """
    before = IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=(
                        IRNode(kind=IRNodeKind.SUBSECTION, label="1", text="Markedsrådet avgjør."),
                        IRNode(kind=IRNodeKind.SUBSECTION, label="2", text="Markedsrådet kan delegere."),
                    ),
                ),
            ),
        ),
    )
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [_w69a_substitution_op(1, section="1", from_term="Markedsrådet", to_term="Konkurranseklagenemnda")],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children[0].children] == [
        "Markedsrådet avgjør.",
        "Markedsrådet kan delegere.",
    ]
    assert [
        a.detail["reason"] for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT
    ] == ["multiple"]


def test_no_w69a_apply_refuses_both_legs_when_two_announced_terms_are_present() -> None:
    """S6, and why it is not implied by S7: the pairs are PREFIX-NESTED.

    One announcement, two pairs (``namsmannen``/``namsmannens``). A provision
    carrying both would take two writes from an announcement whose grammar says
    one pair applies at a time — and ``namsmannen``'s ``str.replace`` would also
    eat the genitive's stem. Both legs refuse; the provision is untouched.
    """
    before = _w69a_statute("Namsmannen sender namsmannen sitt varsel til namsmannens kontor.")
    ops = [
        _w69a_substitution_op(1, section="1", from_term="namsmannen", to_term="namsfogden"),
        _w69a_substitution_op(2, section="1", from_term="namsmannens", to_term="namsfogdens"),
    ]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)
    assert [child.text for child in result.body.children] == [
        "Namsmannen sender namsmannen sitt varsel til namsmannens kontor."
    ]
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert sorted(a.detail["reason"] for a in refusals) == ["term_ambiguous", "term_ambiguous"]


def test_no_w69a_apply_lets_the_sibling_pair_fire_when_only_one_term_is_present() -> None:
    """The other side of S6: exactly one announced term present, so it lands.

    Only the genitive occurs. ``namsmannens`` fires; ``namsmannen`` records that
    a sibling pair of its own announcement matched instead — a typed rejection,
    not a silent drop, so the conserved partition still sees every op.
    """
    before = _w69a_statute("Varselet sendes til namsmannens kontor.")
    ops = [
        _w69a_substitution_op(1, section="1", from_term="namsmannen", to_term="namsfogden"),
        _w69a_substitution_op(2, section="1", from_term="namsmannens", to_term="namsfogdens"),
    ]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)
    assert [child.text for child in result.body.children] == ["Varselet sendes til namsfogdens kontor."]
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert [(a.op_id, a.detail["reason"]) for a in refusals] == [
        ("no/lovtid/9999-01-01-1:1", "other_announced_term_matches"),
    ]


def test_no_w69a_a_refused_substitution_is_a_typed_rejection_in_the_conserved_partition() -> None:
    """§1.8: every op is a landed write or a typed rejection — never neither.

    The apply fold raises fail-loud on an op that lands nothing without a skip
    adjudication, so the refusal kind has to be in ``_NO_SKIP_ADJUDICATION_KINDS``.
    The W-69 design says half 2 needs nothing there because its refusals are all
    parse-plane; that does not survive its own premise (S5-S7 need the addressed
    node's TEXT, and the parse plane has no statute), so the kind is registered.
    """
    before = _w69a_statute("Ansettelsesmyndigheten treffer vedtaket.")
    ops = [
        _w69a_substitution_op(1, section="1", from_term="tilsettingsmyndigheten", to_term="ansettelsesmyndigheten"),
        _w69a_substitution_op(2, section="1", from_term="Ansettelsesmyndigheten", to_term="Vedtaksmyndigheten", group="g2"),
    ]
    result = apply_no_ops_conserved(before, ops)
    assert [op.op_id for op in result.applied_ops] == ["no/lovtid/9999-01-01-1:2"]
    assert [(item.item.op_id, item.reason_code) for item in result.skipped_items] == [
        ("no/lovtid/9999-01-01-1:1", NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT),
    ]
    assert all(item.blocking for item in result.skipped_items)


# ── W-69b apply plane: read-only sentence materialization on the patch path ──


def _w69b_sentence_substitution_op(
    sequence: int,
    *,
    section: str,
    subsection: str,
    sentence: str,
    from_term: str,
    to_term: str,
    group: str = "g1",
) -> LegalOperation:
    """W-69a's op, addressed one level deeper: ``§ N/ledd/M/setning/K``."""
    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.TEXT_PATCH,
        target=LegalAddress(
            path=(("section", section), ("subsection", subsection), ("sentence", sentence))
        ),
        text_patch=TextPatchSpec(
            kind=TextPatchKindEnum.REPLACE,
            selector=TextSelector(match_text=from_term, occurrence=0),
            replacement=to_term,
        ),
        source=OperationSource(statute_id="no/lovtid/9999-01-01-1", raw_text="ann", title="x"),
        provenance_tags=("base_act:no/lov/1999-01-01-1", "scope:addressed", NO_SUBSTITUTION_PROVENANCE_TAG),
        group_id=group,
    )


def _w69b_ledd_statute(*ledd_texts: str) -> IRStatute:
    """One section whose subsections carry RAW multi-sentence text, no children."""
    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="1",
                    children=tuple(
                        IRNode(kind=IRNodeKind.SUBSECTION, label=str(i), text=text)
                        for i, text in enumerate(ledd_texts, start=1)
                    ),
                ),
            ),
        ),
    )


def _w69b_ledd(result: IRStatute, index: int) -> IRNode:
    return result.body.children[0].children[index]


def _w69b_sentence_texts(ledd: IRNode) -> list[str]:
    return [
        child.text or ""
        for child in ledd.children
        if getattr(child.kind, "value", child.kind) == "sentence"
    ]


def test_no_w69b_text_patch_path_materializes_and_lands_on_the_addressed_sentence() -> None:
    """W-69b's whole point: a ``setning/N`` TEXT_PATCH now resolves.

    At the base pin the text-patch branch resolved the target and returned long
    before the structural branch's materialization call, so this op could only
    ever produce ``replay_unresolved_target``. Lifting the call gives the
    text-patch branch the same sentence children the structural branch has had
    all along — and the write lands on the ADDRESSED sentence, not on a sibling
    that happens to carry the same word.
    """
    before = _w69b_ledd_statute(
        "Tilsettingsmyndigheten varsler. Tilsettingsmyndigheten treffer vedtaket."
    )
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [
            _w69b_sentence_substitution_op(
                1,
                section="1",
                subsection="1",
                sentence="2",
                from_term="Tilsettingsmyndigheten",
                to_term="Ansettelsesmyndigheten",
            )
        ],
        adjudications_out=adjudications,
    )
    ledd = _w69b_ledd(result, 0)
    assert _w69b_sentence_texts(ledd) == [
        "Tilsettingsmyndigheten varsler.",
        "Ansettelsesmyndigheten treffer vedtaket.",
    ]
    assert not ledd.text
    assert not [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert not [a for a in adjudications if a.kind == "replay_unresolved_target"]
    materialized = [a for a in adjudications if a.kind == "no_replay_sentence_children_materialized"]
    assert [
        (a.detail["rule_id"], a.detail["target"], a.detail["materialized_sentence_count"])
        for a in materialized
    ] == [
        ("no_sentence_text_materialized_for_sentence_target", "section:1/subsection:1/sentence:2", 2),
    ]


def test_no_w69b_text_patch_path_materialization_conserves_text() -> None:
    """The read-only tripwire: materializing changes SHAPE, never text bytes.

    ``_split_no_sentences`` partitions ``_normalize_space(parent.text)`` at
    sentence boundaries, so space-joining the sentence children reproduces the
    former ledd text exactly. That is the whole licence for reaching the
    materializer from a *content*-writing branch, and it is the property the
    item's full-corpus statute diff allows as a tree-shape-only delta — so it is
    asserted here byte-for-byte, on a ledd whose sentences carry the boundary
    cases the splitter has rules for: an abbreviation ending in a full stop
    (``jf.``) and a numbered date (``1. januar 2020``), neither of which may be
    read as a sentence end.

    Two ledd are exercised: the one the op addresses (whose text changes by
    exactly the announced substitution and nothing else) and the one it merely
    passes over (which must not be materialized at all).
    """
    from lawvm.norway.grafter import _normalize_space

    addressed = (
        "Vedtak treffes av Tilsettingsmyndigheten innen 1. januar 2020. "
        "Klage behandles etter forvaltningsloven kapittel VI, jf. § 28. "
        "Departementet kan gi forskrift."
    )
    untouched = "Denne paragrafen gjelder ikke for embetsmenn. Kongen kan gjøre unntak."
    before = _w69b_ledd_statute(addressed, untouched)
    result = apply_no_ops(
        before,
        [
            _w69b_sentence_substitution_op(
                1,
                section="1",
                subsection="1",
                sentence="1",
                from_term="Tilsettingsmyndigheten",
                to_term="Ansettelsesmyndigheten",
            )
        ],
    )

    sentences = _w69b_sentence_texts(_w69b_ledd(result, 0))
    assert sentences == [
        "Vedtak treffes av Ansettelsesmyndigheten innen 1. januar 2020.",
        "Klage behandles etter forvaltningsloven kapittel VI, jf. § 28.",
        "Departementet kan gi forskrift.",
    ]
    # The ONLY difference between the space-joined children and the former ledd
    # text is the announced substitution: undo it and the bytes are identical.
    assert " ".join(sentences).replace(
        "Ansettelsesmyndigheten", "Tilsettingsmyndigheten"
    ) == _normalize_space(addressed)
    # …and the substitution really did land (the assertion above would also pass
    # on a no-op, which is the failure this pairing rules out).
    assert " ".join(sentences) != _normalize_space(addressed)

    # A ledd no sentence-addressed op names keeps its raw text: the lift is
    # reached from the op's own target, never swept over the tree.
    second = _w69b_ledd(result, 1)
    assert second.text == untouched
    assert _w69b_sentence_texts(second) == []


def test_no_w69b_a_refused_sentence_substitution_leaves_no_materialization_residue() -> None:
    """Materialization runs BEFORE the term conjuncts — and is rolled back with them.

    Resolution has to happen before the addressed node's text can be read at
    all, so the ledd IS split into sentence children before S6/S7 get to refuse.
    What happens to that shape change when the op then writes nothing is a
    property of the apply seam, not of this item, and it is worth pinning
    because the whole read-only argument would be weaker if a refusal could
    leave a half-materialized ledd behind: the seam discards the op's state
    entirely, so the tree is returned IDENTICAL — same object, not merely equal.

    The ``no_replay_sentence_children_materialized`` receipt still fires. It
    describes work the dispatch really did; the receipt lane is deliberately
    wider than the landed-write lane here, and the alternative (suppressing a
    receipt for a shape change that was computed) would make the two lanes lie
    about each other. Same behaviour the structural branch has always had.
    """
    text = "Tilsettingsmyndigheten treffer vedtaket. Klagen avgjøres av departementet."
    before = _w69b_ledd_statute(text)
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [
            _w69b_sentence_substitution_op(
                1,
                section="1",
                subsection="1",
                sentence="1",
                from_term="tilsettingsmyndigheten",
                to_term="ansettelsesmyndigheten",
            )
        ],
        adjudications_out=adjudications,
    )
    assert result.body is before.body
    ledd = _w69b_ledd(result, 0)
    assert ledd.text == text
    assert _w69b_sentence_texts(ledd) == []
    refusals = [a for a in adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT]
    assert [a.detail["reason"] for a in refusals] == ["inflection_only"]
    assert [a.kind for a in adjudications if a.kind == "no_replay_sentence_children_materialized"] == [
        "no_replay_sentence_children_materialized"
    ]


def test_no_w69b_a_sentence_address_whose_parent_ledd_is_missing_refuses_typed() -> None:
    """The 2 corpus addresses W-69b does NOT serve, in miniature.

    ``lov/2020-04-17-29/§11/ledd/1/setning/1`` and ``…/§18/ledd/2/setning/2``
    are unresolvable because their PARENT ledd is absent from the replayed tree
    — the same defect as that law's five unresolvable LEDD-addressed ops, and so
    it takes the same typed receipt. Materialization cannot invent a parent, and
    the parse plane cannot see one (it has no statute), so this refusal belongs
    at apply and nowhere else.
    """
    before = _w69b_ledd_statute("Ett enkelt ledd med Tilsettingsmyndigheten i.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before,
        [
            _w69b_sentence_substitution_op(
                1,
                section="1",
                subsection="4",
                sentence="1",
                from_term="Tilsettingsmyndigheten",
                to_term="Ansettelsesmyndigheten",
            )
        ],
        adjudications_out=adjudications,
    )
    assert [child.text for child in result.body.children[0].children] == [
        "Ett enkelt ledd med Tilsettingsmyndigheten i."
    ]
    assert [a.kind for a in adjudications] == ["replay_unresolved_target"]
    assert adjudications[0].detail["target"] == "section:1/subsection:4/sentence:1"
    assert not [a for a in adjudications if a.kind == "no_replay_sentence_children_materialized"]


def test_no_w75_a_real_replacement_after_an_announcement_still_lowers() -> None:
    """W-75: the conjunct that keeps the refusal off genuine amendments.

    ``no/lovtid/2026-06-19-45`` puts four ordinary ``§ X skal lyde: <payload>``
    change nodes immediately AFTER substitution announcements. Keying the
    refusal on the preceding sibling alone would refuse all four and delete real
    replacements, so a node that declares its own operative payload is never a
    substitution address list — whatever precedes it.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w75_substitution_change_html(
                announcement_node=(
                    '<article class="defaultP">I følgende bestemmelser endres ordet '
                    "«politimann» til «en polititjenesteperson»: §§ 176, 198, 206 og 216.</article>"
                ),
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1">'
                    '<article class="defaultP">§ 13 første ledd skal lyde:</article>'
                    '<article class="legalP">Ansettelsesmyndigheten treffer vedtaket.</article>'
                    "</article>"
                ),
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED]
    ops = grouped["no/lov/2015-06-19-70"]
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "13"), ("subsection", "1"))),
    ]
    assert ops[0].payload is not None
    assert "Ansettelsesmyndigheten treffer vedtaket." in (ops[0].payload.text or "")


def test_no_w75_announcement_must_open_the_sentence() -> None:
    """W-75: ``… hjemmel i følgende bestemmelser med tilhørende forskrifter:`` is payload.

    ``no/lovtid/2025-04-25-12`` § 3 first subsection contains the announcement's
    words mid-sentence in ordinary operative prose. An unanchored test refuses
    two genuine replacements on it, so the opener is anchored.
    """
    from lawvm.norway.grafter import _no_text_announces_word_substitution

    assert not _no_text_announces_word_substitution(
        "Plikten til å gi opplysninger etter denne lov omfatter opplysninger som skal gis "
        "med hjemmel i følgende bestemmelser med tilhørende forskrifter: skatteforvaltningsloven "
        "«§ 7-2» endres til «§ 7-3»"
    )
    # All three conjuncts are load-bearing.
    assert not _no_text_announces_word_substitution("I følgende bestemmelser skal § 13 endres:")
    assert not _no_text_announces_word_substitution("I følgende bestemmelser skal «X» lyde slik:")
    assert _no_text_announces_word_substitution(
        "I følgende bestemmelser skal ordet «tilsettingsmyndigheten» endres til «ansettelsesmyndigheten»:"
    )
    assert _no_text_announces_word_substitution(
        "I følgende bestemmelser erstattes uttrykket «politi- og lensmannsetaten» av «politiet»: §§ 1, 18, 21 og 24 b."
    )


def test_no_w78_announcement_opener_is_not_a_closed_noun_list() -> None:
    """W-78: the noun after ``følgende`` is decoration, and enumerating it was the defect.

    W-69a's opener listed ``bestemmelser|bestemmelse|paragrafer|paragraf|
    lovbestemmelser|lover``. ``no/lovtid/2026-06-19-45`` and
    ``no/lovtid/2026-06-12-31`` write the SAME construct as "Følgende steder
    endres …", which the list did not contain — so seven nodes fell past this
    predicate into the structured payload lane and minted 116 REPLACE ops whose
    payload was the announcement sentence itself.

    The opener is therefore ``følgende`` sentence-initially (the leading ``i``
    optional), and the load-bearing conjuncts are that a quoted FROM term and a
    substitution verb both stand BEFORE the payload-introducing colon: the
    instruction is complete without the list, which is exactly what makes the
    colon a LIST introducer.
    """
    from lawvm.norway.grafter import _no_text_announces_word_substitution

    # The W-78 dialect, in all four surfaces the two instruments print.
    assert _no_text_announces_word_substitution(
        "Følgende steder endres ordet «ansiktsfoto» til «ansiktsbilde»: § 100 første ledd."
    )
    assert _no_text_announces_word_substitution(
        "Følgende steder endres «den biometriske informasjonen» til «de biometriske "
        "opplysningene»: § 100 a fjerde ledd."
    )
    assert _no_text_announces_word_substitution(
        "Følgende steder endres ordene «namsmann» og «namsmannen» til henholdsvis ordene "
        "«namsfogd» og «namsfogden»: §§ 2-1 og 2-2."
    )
    assert _no_text_announces_word_substitution("Følgende steder endres ordet «namsmenn» til ordet «namsfogder»: §§ 5-2 og 5-7.")

    # The W-69a dialect is unchanged.
    assert _no_text_announces_word_substitution(
        "I følgende bestemmelser skal ordet «tilsettingsmyndigheten» endres til «ansettelsesmyndigheten»:"
    )

    # A text with no colon cannot be an announcement: there is no list to govern.
    assert not _no_text_announces_word_substitution("Følgende steder endres ordet «X» til «Y»")
    # The instruction must be COMPLETE before the colon. A node whose quoted term
    # and verb only appear AFTER it is declaring a payload, not an address list.
    assert not _no_text_announces_word_substitution(
        "Følgende endringer gjøres: ordet «X» endres til «Y» i § 13 første ledd."
    )
    # Still sentence-initial: the W-75 payload-prose false positive stays refused.
    assert not _no_text_announces_word_substitution(
        "Plikten til å gi opplysninger etter denne lov omfatter opplysninger som skal gis "
        "med hjemmel i følgende bestemmelser med tilhørende forskrifter: skatteforvaltningsloven "
        "«§ 7-2» endres til «§ 7-3»"
    )


def test_no_w78_folgende_steder_address_list_lowers_as_addressed_substitution() -> None:
    """W-78: the defect, end to end — announcement text must never become payload.

    Before the fix this node minted one REPLACE per ``data-change-part`` address
    whose payload was the announcement head ("Følgende steder endres ordet
    «ansiktsfoto» til «ansiktsbilde»:"), writing the amendment's own prose into
    in-force law at every listed provision. It must now reach the W-69a
    production and mint addressed TEXT_PATCHes instead.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w75_substitution_change_html(
            announcement_node='<article class="defaultP">II</article>',
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1 '
                'lov/2015-06-19-70/§14/ledd/2">'
                '<article class="defaultP">Følgende steder endres ordet «ansiktsfoto» '
                "til «ansiktsbilde»: § 13 første ledd og § 14 andre ledd.</article>"
                "</article>"
            ),
        ),
        "no/lovtid/2026-06-12-31",
        adjudications_out=adjudications,
    )

    assert not [a for a in adjudications if a.kind.startswith("no_parse_substitution")]
    ops = _no_substitution_ops(grouped)
    assert len(ops) == 2
    assert {op.action for op in ops} == {StructuralAction.TEXT_PATCH}
    assert {op.text_patch.selector.match_text for op in ops if op.text_patch} == {"ansiktsfoto"}
    assert {op.text_patch.replacement for op in ops if op.text_patch} == {"ansiktsbilde"}
    # …and nothing carries the announcement as a payload, in any op on the block.
    assert not [
        op
        for _base, block in grouped
        for op in block
        if op.payload is not None and "Følgende steder" in (op.payload.text or "")
    ]


def test_no_w78_a_real_replacement_after_a_folgende_steder_announcement_still_lowers() -> None:
    """W-78: the operative conjunct is what keeps the widening off genuine payloads.

    Both instruments interleave the new-dialect announcements with ordinary
    ``§ X skal lyde: <payload>`` change nodes. Corpus-wide there are five
    ``data-change-part`` nodes that carry a quoted term AND a substitution verb
    in their head and yet declare their own payload; every one must keep lowering
    as a REPLACE. Under-application is safe here; withdrawing a real replacement
    is not.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w75_substitution_change_html(
                announcement_node=(
                    '<article class="defaultP">Følgende steder endres ordet «namsmann» '
                    "til «namsfogd»: §§ 176, 198.</article>"
                ),
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1">'
                    '<article class="defaultP">§ 13 første ledd skal lyde: ordet «namsmann» '
                    "endres til «namsfogd» i vedtaket.</article>"
                    "</article>"
                ),
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind.startswith("no_parse_substitution")]
    ops = grouped["no/lov/2015-06-19-70"]
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "13"), ("subsection", "1"))),
    ]


# ---------------------------------------------------------------------------
# W-79: the structured payload lane's own-text invariant.
#
# One test per SHAPE CLASS of the corpus-wide own-text-fallback census (217
# payloads: 68 declaring, 149 not), not one per node. The five refusing shapes
# and the two keeping shapes below are exactly that census's classes.
# ---------------------------------------------------------------------------


def _w79_change_html(*, change_node: str, base: str = "lov/2015-06-19-70") -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <main>
      <section class="document-change" data-document="{base}">
{change_node}
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_no_w79_payload_declaration_predicate_separates_instruction_from_content() -> None:
    """The invariant itself: a declaration in the head, and content after the colon.

    The five refusing shapes are the corpus census's, verbatim; the accepting
    ones are the two surfaces that carry a real payload in their own text.
    """
    # Refuses: no colon at all, so nothing can be a declared payload.
    assert _no_structured_declared_own_payload("Nåværende § 66 blir § 84.") is None
    assert (
        _no_structured_declared_own_payload("§ 36 tredje ledd andre punktum blir oppheva.")
        is None
    )
    assert (
        _no_structured_declared_own_payload(
            "I § 45 erstattes henvisningen til «§§ 39, 40» av en henvisning til «§§ 39»."
        )
        is None
    )
    assert (
        _no_structured_declared_own_payload(
            "Overskriften til avsnitt IV i kapittel 14 flyttes til etter § 14-17."
        )
        is None
    )
    # Refuses: a colon, but the head declares no payload — it announces a repeal
    # and the colon introduces an ADDRESS LIST (``no/lovtid/2025-06-20-88``).
    assert (
        _no_structured_declared_own_payload(
            "I følgende paragrafer oppheves punktumet i paragrafoverskriften: § 1, § 2."
        )
        is None
    )
    # Refuses: a declaration with NOTHING after the colon — the payload lives in
    # structure this fallback cannot read, so writing the lead would be wrong.
    assert _no_structured_declared_own_payload("§ 4 tredje ledd nr. 2 skal lyde:") is None
    # Accepts, and the payload is the TAIL — the lead never reaches the statute.
    assert (
        _no_structured_declared_own_payload("§ 30 skal lyde: Lova gjeld frå 1. januar.")
        == "Lova gjeld frå 1. januar."
    )
    assert (
        _no_structured_declared_own_payload(
            "I lov 21. november 1952 nr. 3 om tjenesteplikt i politiet skal § 6 lyde: "
            "Forsvarsloven kapittel 8 får anvendelse."
        )
        == "Forsvarsloven kapittel 8 får anvendelse."
    )


@pytest.mark.parametrize(
    ("shape", "own_text"),
    [
        # The relabel announcement — 37 ops over 22 nodes in the census, the
        # largest refusing shape. ``data-change-part`` names the provisions being
        # RENUMBERED, and the node has no payload for any of them.
        ("relabel", "Nåværende § 66 blir § 84."),
        # The repeal announcement, including ``2025-06-20-88``'s 29-address
        # heading-punctuation form — the W-78 construct in a dialect with no
        # quoted term for the substitution grammar to see.
        (
            "repeal",
            "I følgende paragrafer oppheves punktumet i paragrafoverskriften: § 1, § 2.",
        ),
        # The in-place word substitution, addressed inside the sentence rather
        # than by a trailing list (so W-78's opener never matches it).
        (
            "substitution",
            "I § 45 erstattes henvisningen til «§§ 39, 40» av en henvisning til «§§ 39».",
        ),
        # The move announcement.
        ("move", "Overskriften til avsnitt IV i kapittel 14 flyttes til etter § 14-17."),
        # A declaration whose payload is NOT in the node's own text: the lead
        # survives alone and used to be written over the target (or, once the
        # narrow ``§ N skal lyde:`` strip consumed it, an EMPTY node was).
        ("declaration_only", "§ 4 tredje ledd nr. 2 skal lyde:"),
    ],
)
def test_no_w79_undeclared_own_text_refuses_typed(shape: str, own_text: str) -> None:
    """No shape whose own text is an INSTRUCTION may become a payload.

    The refusal is per (action, target) and blocking: nothing lands, and the
    reason is typed rather than a silent drop.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = iter_no_document_change_ops(
        _w79_change_html(
            change_node=(
                '<article class="change" data-change-part="lov/2015-06-19-70/§13">'
                f'<article class="defaultP">{own_text}</article>'
                "</article>"
            )
        ),
        "no/lovtid/2026-06-19-45",
        adjudications_out=adjudications,
    )

    assert grouped == [], f"{shape}: an instruction was lowered as a payload"
    refusals = [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    assert len(refusals) == 1
    detail = refusals[0].detail or {}
    assert detail["phase"] == "parse"
    assert detail["blocking"] is True
    assert detail["target"] == "section:13"
    assert detail["undeclared_text"] == own_text


def test_no_w79_declared_own_text_payload_still_lowers_without_its_lead() -> None:
    """The keeping direction, and the reason the two halves are one rule.

    A node that DECLARES its payload keeps lowering — and the payload is the tail
    the declaration introduces, so the amendment's own lead prose ("I lov 21.
    november 1952 nr. 3 … skal § 6 lyde:") stops being written into § 6 alongside
    the law it introduces.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§6">'
                    '<article class="defaultP">I lov 19. juni 2015 nr. 70 om karantene '
                    "skal § 6 lyde:</article>"
                    '<article class="legalP">Forsvarsloven kapittel 8 får anvendelse.</article>'
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2015-06-19-70"]
    assert [(op.action, op.target.path) for op in ops] == [
        (StructuralAction.REPLACE, (("section", "6"),)),
    ]
    assert ops[0].payload is not None
    assert ops[0].payload.text == "Forsvarsloven kapittel 8 får anvendelse."


def test_no_w79_structured_payload_candidates_are_untouched_by_the_invariant() -> None:
    """The zero-loss half: the invariant guards ONE payload source, not the lane.

    196 of the 267 undeclared ``data-change-part`` nodes resolve their payload
    against a structured candidate rather than their own text, and the fallback is
    never consulted for them. They must keep lowering whatever their lead says.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§13/ledd/1">'
                    '<article class="defaultP">Nåværende § 13 blir § 14.</article>'
                    '<article class="legalP">Fristen er tre måneder.</article>'
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2015-06-19-70"]
    assert len(ops) == 1
    assert ops[0].payload is not None
    assert ops[0].payload.text == "Fristen er tre måneder."


def test_no_w79_refusal_is_per_target_not_per_node() -> None:
    """A node's other targets keep lowering when only one has no payload.

    The refusal sits at the (action, target) loop, not at the node, so a block
    that resolves one address against a structured candidate and offers only its
    own instruction prose for another loses exactly the second.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§14 '
                    'lov/2015-06-19-70/§13/ledd/1">'
                    '<article class="defaultP">Nåværende § 14 blir § 15.</article>'
                    '<article class="legalP">Fristen er tre måneder.</article>'
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    ops = grouped["no/lov/2015-06-19-70"]
    assert [op.target.path for op in ops] == [(("section", "13"), ("subsection", "1"))]
    assert ops[0].payload is not None and ops[0].payload.text == "Fristen er tre måneder."
    refusals = [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    assert [(a.detail or {})["target"] for a in refusals] == ["section:14"]


# ── W-82: the own-text fallback's PAYLOAD REACH ──────────────────────────────
#
# One test per PROVEN CARRIER SHAPE of the base census (66 ops over 43 nodes /
# 25 instruments whose declaration passes W-79's gate and whose tail is empty
# because the payload lives in a sibling structure), plus the extent limbs that
# keep the rest refused and the invariant that the 83 instruction-prose refusals
# are untouched.
# ---------------------------------------------------------------------------


def test_no_w82_the_gate_is_unchanged_only_the_reach_widens() -> None:
    """W-79's gate, split out and asserted on its own.

    W-82 asks the same first question W-79 did — is a payload DECLARED in the
    head? — and only then asks a second one W-79 never asked: where does the
    declared payload live. Nothing that failed the gate may pass it.
    """
    # Declares: the operative phrase stands in the head and a colon closes it.
    assert _no_structured_payload_is_declared("§ 4 tredje ledd nr. 2 skal lyde:")
    assert _no_structured_payload_is_declared("§ 30 skal lyde: Lova gjeld frå 1. januar.")
    # Declares nothing: no colon, or no operative phrase before it.
    assert not _no_structured_payload_is_declared("Nåværende § 66 blir § 84.")
    assert not _no_structured_payload_is_declared(
        "I følgende paragrafer oppheves punktumet i paragrafoverskriften: § 1, § 2."
    )
    # And the own-text reader is unchanged: the tail is still the payload, and an
    # empty tail is still "not in this node's own text".
    assert _no_structured_declared_own_payload("§ 4 tredje ledd nr. 2 skal lyde:") is None
    assert (
        _no_structured_declared_own_payload("§ 30 skal lyde: Lova gjeld frå 1. januar.")
        == "Lova gjeld frå 1. januar."
    )


def _w82_future_article(name: str, title: str, body: str) -> str:
    return (
        f'<article class="futureLegalArticle" data-name="{name}">'
        f'<span class="futureLegalArticleHeader"><span class="legalArticleValue">{name}</span>'
        f'<span class="legalArticleTitle">{title}</span></span>'
        f'<article class="legalP">{body}</article>'
        "</article>"
    )


def test_no_w82_future_article_carriers_land_label_for_label() -> None:
    """Carrier shape 1: a new chapter announced as one block (17 ops / 3 nodes).

    Lovdata writes the destination labels lower-case in the address
    (``§5a-1``) and upper-case in the carrier (``data-name="§5A-1"``), which is
    why the existing candidate map missed them and the own-text fallback — the
    lane's last resort — was reached at all. The match is machine-to-machine on
    Lovdata's own labels, case-folded, and it is a BIJECTION.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-add-new-part="lov/2015-06-19-70/kap5A '
                    'lov/2015-06-19-70/§5a-1 lov/2015-06-19-70/§5a-2">'
                    '<article class="defaultP">Nytt kapittel 5 A skal lyde:</article>'
                    '<span class="futuretitle">Kap. 5 A. Videodelingsplattformer</span>'
                    + _w82_future_article("§5A-1", "Jurisdiksjon", "Kongen kan gi forskrift.")
                    + _w82_future_article("§5A-2", "Registreringsplikt", "Tilbydere plikter å registrere seg.")
                    + "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2015-06-19-70"]
    # W-101 moved this pin: ``kap5A`` now lowers (the chapter op stands first,
    # heading-only), the section addresses take the CARRIER's case (``5A-1``,
    # the consolidation's spelling) and start at the new chapter. The bijection
    # this test is about is unchanged — each address still gets its own article.
    assert [op.target.path for op in ops] == [
        (("chapter", "5A"),),
        (("chapter", "5A"), ("section", "5A-1")),
        (("chapter", "5A"), ("section", "5A-2")),
    ]
    first, second = (op.payload for op in ops[1:])
    assert first is not None and second is not None
    assert (_kind_value(first.kind), first.label) == ("section", "5A-1")
    assert [child.text for child in first.children] == [
        "Jurisdiksjon",
        "Kongen kan gi forskrift.",
    ]
    assert [child.text for child in second.children] == [
        "Registreringsplikt",
        "Tilbydere plikter å registrere seg.",
    ]


def test_no_w82_future_article_extent_mismatch_refuses_every_target() -> None:
    """W-77's extent discipline: label-for-label, ALL OR NOTHING.

    ``no/lovtid/2024-06-21-42`` announces "Etter § 7-9 skal nytt avsnitt III
    lyde:" and carries a § 7-9 **a**; the address it declares is § 7-9. One
    unmatched target refuses every target of the node rather than letting the
    carriers slide onto whichever addresses happen to be left.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§7-9 '
                    'lov/2015-06-19-70/§7-10">'
                    '<article class="defaultP">Etter § 7-9 skal nytt avsnitt III lyde:</article>'
                    '<span class="futuretitle">III. Bærekraftsrapportering</span>'
                    + _w82_future_article("§7-9a", "Bærekraftsrapportering", "Selskapet skal rapportere.")
                    + "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert grouped == {}
    refusals = [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    assert sorted((a.detail or {})["target"] for a in refusals) == ["section:7-10", "section:7-9"]


def test_no_w82_future_title_lands_as_a_heading_only_section_payload() -> None:
    """Carrier shape 2a: ``span.futuretitle`` behind an ``Overskriften til §`` lead.

    The lead predicate and the payload shape are the ones
    ``_heading_only_section_payload`` already had; only the title's LOCATION
    widens, from "a second defaultP article" to "the futuretitle span". The
    payload is heading-only, so a section's BODY is never touched by a heading
    announcement — which is what makes one title over three addresses safe.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/§10-30 '
                    'lov/2015-06-19-70/§10-31">'
                    '<article class="defaultP">Overskriften til §§ 10-30 og 10-31 skal '
                    "lyde:</article>"
                    '<span class="futuretitle">Merverdiavgift, særavgifter og tollavgift</span>'
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2015-06-19-70"]
    assert [op.target.path for op in ops] == [(("section", "10-30"),), (("section", "10-31"),)]
    for op, label in zip(ops, ("10-30", "10-31"), strict=True):
        payload = op.payload
        assert payload is not None
        assert (_kind_value(payload.kind), payload.label, payload.text) == ("section", label, "")
        assert [(_kind_value(c.kind), c.text) for c in payload.children] == [
            ("heading", "Merverdiavgift, særavgifter og tollavgift")
        ]


def test_no_w82_future_title_lands_a_subdivision_heading_at_a_chapter_address() -> None:
    """Carrier shape 2b: the same span, at a KAPITTEL address.

    "Kapittel 8 avsnitt III overskriften skal lyde:" and "Ny deloverskrift til §§
    18-2 til 18-8 skal lyde:" declare a heading and nothing else, so the payload
    is a container carrying that heading alone.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/KAPITTEL_8-3">'
                    '<article class="defaultP">Kapittel 8 avsnitt III overskriften skal '
                    "lyde:</article>"
                    '<span class="futuretitle">III. Daglig ledelse og personer med '
                    "nøkkelfunksjoner</span>"
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2015-06-19-70"]
    assert [op.target.path for op in ops] == [(("chapter", "8-3"),)]
    payload = ops[0].payload
    assert payload is not None
    assert (_kind_value(payload.kind), payload.label, payload.text) == ("chapter", "8-3", "")
    assert [(_kind_value(c.kind), c.text) for c in payload.children] == [
        ("heading", "III. Daglig ledelse og personer med nøkkelfunksjoner")
    ]


def test_no_w82_future_title_over_a_body_is_not_a_heading_announcement() -> None:
    """The limb that keeps shape 2b narrow.

    A title that HEADS A BODY is a chapter announcement, and the body's extent is
    a different proof — the one shape 1 makes. A chapter address with articles
    behind it stays refused rather than landing the title alone over a chapter
    that has sections in it.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" data-change-part="lov/2015-06-19-70/KAPITTEL_8-3">'
                    '<article class="defaultP">Nytt kapittel 8 skal lyde:</article>'
                    '<span class="futuretitle">III. Daglig ledelse</span>'
                    + _w82_future_article("§8-1", "Ledelse", "Foretaket skal ha en daglig leder.")
                    + "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert grouped == {}
    assert [
        (a.detail or {})["target"]
        for a in adjudications
        if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED
    ] == ["chapter:8-3"]


def test_no_w82_single_leaf_carrier_lands_at_its_declared_leaf() -> None:
    """Carrier shape 3: ONE ``li`` / ``numberedLegalP``, ONE payload-taking target.

    Arity one on both sides is the extent proof. ``no/lovtid/2023-12-20-104`` is
    the whole of its instrument — the op W-79 refused was the only one it had, and
    it is the entry the index lost.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" '
                    'data-change-part="lov/2015-06-19-70/§4/ledd/3/nummer/2">'
                    '<article class="defaultP">§ 4 tredje ledd nr. 2 skal lyde:</article>'
                    '<li><article class="listArticle"><article class="legalP">'
                    "avgiftsinntekter ved utslipp i petroleumsvirksomhet"
                    "</article></article></li>"
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2015-06-19-70"]
    assert [op.target.path for op in ops] == [
        (("section", "4"), ("subsection", "3"), ("item", "2"))
    ]
    payload = ops[0].payload
    assert payload is not None
    assert (_kind_value(payload.kind), payload.label, payload.text) == (
        "item",
        "2",
        "avgiftsinntekter ved utslipp i petroleumsvirksomhet",
    )


@pytest.mark.parametrize(
    ("limb", "change_part", "carrier"),
    [
        # The address is a LEVEL SHALLOWER than the declaration: "§ 18-3 annet
        # ledd bokstav a nr. 4" carries nr. 4 and Lovdata's change-part stops at
        # bokstav a, so the write would flatten all of bokstav a to one nummer.
        (
            "address_shallower_than_carrier",
            "lov/2015-06-19-70/§18-3/ledd/2/bokstav/a",
            '<li data-li-identifier="4." data-name="4."><article class="listArticle">'
            '<article class="legalP">Kraft som leveres til en strømleverandør</article>'
            "</article></li>",
        ),
        # The address is a whole SECTION: "§ 25 nr. 10 skal lyde:" against
        # ``…/§25``. A leaf carrier may never be written over a container.
        (
            "leaf_carrier_at_a_section_address",
            "lov/2015-06-19-70/§25",
            '<li data-li-identifier="10." data-name="10."><article class="listArticle">'
            '<article class="legalP">behandling av personopplysninger</article>'
            "</article></li>",
        ),
        # Two carriers, one address: "§ 4 første ledd nr. 1 og 2 skal lyde:"
        # against a single ledd. Arity is the proof and there is none here.
        (
            "two_carriers_one_address",
            "lov/2015-06-19-70/§4/ledd/2",
            '<li data-li-identifier="1." data-name="1."><article class="legalP">'
            "ubebygde enkelttomter for bolig</article></li>"
            '<li data-li-identifier="2." data-name="2."><article class="legalP">'
            "ubebygde enkelttomter for fritidshus</article></li>",
        ),
        # The carrier holds nested structure the flattener cannot reach:
        # ``no/lovtid/2025-06-20-109``'s § 2 nr. 2 is a numerator heading over a
        # ledd with its own letter list, and a flat text payload would land
        # TRUNCATED to the heading.
        (
            "carrier_text_is_not_the_whole_carrier",
            "lov/2015-06-19-70/§2/nummer/2",
            '<article class="numberedLegalP" data-numerator="2">2. (Arbeidstakere på skip)'
            '<article class="legalP">Loven omfatter<ul class="defaultList">'
            '<li data-name="a."><article class="legalP">arbeidstakere på skip i NOR</article>'
            "</li></ul></article></article>",
        ),
    ],
)
def test_no_w82_unprovable_leaf_carriers_keep_refusing(
    limb: str, change_part: str, carrier: str
) -> None:
    """The limbs deliberately left refused, each a shape the extent proof rejects.

    31 of the 66 stay refused under the SAME kind — the remainder is not a
    different failure, it is the same one: the declared payload cannot be proved
    to belong at the declared address.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    f'<article class="change" data-change-part="{change_part}">'
                    '<article class="defaultP">§ 4 tredje ledd nr. 2 skal lyde:</article>'
                    f"{carrier}</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert grouped == {}, f"{limb}: an unprovable carrier was written into law"
    refusals = [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    assert len(refusals) == 1
    assert (refusals[0].detail or {})["blocking"] is True


@pytest.mark.parametrize(
    ("shape", "own_text"),
    [
        ("relabel", "Nåværende § 66 blir § 84."),
        (
            "repeal",
            "I følgende paragrafer oppheves punktumet i paragrafoverskriften: § 1, § 2.",
        ),
        (
            "substitution",
            "I § 45 erstattes henvisningen til «§§ 39, 40» av en henvisning til «§§ 39».",
        ),
        ("move", "Overskriften til avsnitt IV i kapittel 14 flyttes til etter § 14-17."),
    ],
)
def test_no_w82_instruction_prose_refusals_are_untouched_even_beside_a_carrier(
    shape: str, own_text: str
) -> None:
    """The W-79 invariant holds: 83 of the 149 declare nothing and still refuse.

    And the reach cannot be reached AROUND: putting a payload carrier next to an
    instruction does not make the instruction a declaration. The gate is asked
    first and it answers on the head alone.
    """
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(
                change_node=(
                    '<article class="change" '
                    'data-change-part="lov/2015-06-19-70/§4/ledd/3/nummer/2">'
                    f'<article class="defaultP">{own_text}</article>'
                    '<li><article class="listArticle"><article class="legalP">'
                    "avgiftsinntekter ved utslipp</article></article></li>"
                    "</article>"
                )
            ),
            "no/lovtid/2026-06-19-45",
            adjudications_out=adjudications,
        )
    )

    assert grouped == {}, f"{shape}: an instruction reached a payload through W-82"
    refusals = [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    assert len(refusals) == 1
    assert (refusals[0].detail or {})["undeclared_text"] == own_text


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w82_corpus_witness_the_instrument_the_index_lost_comes_back() -> None:
    """``no/lovtid/2023-12-20-104`` — one op, and it was the instrument's only one.

    W-79 refused it and the act left the amendment index entirely (entries 2,578
    -> 2,576, two acts departing). Its declared payload was one ``li`` behind a
    one-address change part; that is the arity proof, and the op is back.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2023-12-20-104", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2023-12-20-104", adjudications_out=adjudications
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    ops = grouped["no/lov/2005-12-21-123"]
    assert [op.target.path for op in ops] == [
        (("section", "4"), ("subsection", "3"), ("item", "2"))
    ]
    payload = ops[0].payload
    assert payload is not None
    assert payload.text == (
        "avgiftsinntekter ved utslipp av CO 2 i petroleumsvirksomhet på kontinentalsokkelen"
    )


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w82_corpus_witness_the_second_lost_instrument_stays_refused() -> None:
    """``no/lovtid/2025-03-28-4`` — the other act W-79's closure cost, still out.

    It declares "… skal § 2 nr. 4 lyde:" and carries the new nr. 4, but Lovdata's
    change part stops at ``§2``: the address is a level shallower than the
    declaration, so landing the carrier would write one nummer over the whole
    section. Under-application is safe; a guess here is not. Sized and named as
    the item's largest single follow-up.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2025-03-28-4", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2025-03-28-4", adjudications_out=adjudications
        )
    )

    assert grouped == {}
    refusals = [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    assert [(a.detail or {})["target"] for a in refusals] == ["section:2"]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w82_corpus_witness_a_whole_new_chapter_lands_one_section_per_address() -> None:
    """``no/lovtid/2025-02-28-2`` — the census's largest single node: 9 ops.

    ``data-add-new-part`` names ``kap5A`` and §§ 5a-1 … 5a-9. Until W-101
    ``kap5A`` did not lower at all (one of the 111
    ``no_parse_unresolved_structured_target_skipped``); now it is the chapter op
    the nine section inserts follow, and their addresses carry the carrier's
    case and the chapter step. The bijection is over the NINE section addresses
    and the nine ``futureLegalArticle`` carriers, as before.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2025-02-28-2", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2025-02-28-2", adjudications_out=adjudications
        )
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED]
    chapter_ops = [op for op in grouped["no/lov/1992-12-04-127"] if op.target.path[0] == ("chapter", "5A")]
    assert [op.target.path for op in chapter_ops[:1]] == [(("chapter", "5A"),)]
    ops = chapter_ops[1:]
    assert [op.target.path for op in ops] == [(("chapter", "5A"), ("section", f"5A-{n}")) for n in range(1, 10)]
    # Each address gets its OWN article's heading, not the block's title and not
    # a neighbour's text.
    headings = []
    for op in ops:
        payload = op.payload
        assert payload is not None
        headings.append(next(c.text for c in payload.children if _kind_value(c.kind) == "heading"))
    assert headings[0] == "§ 5 A-1. Jurisdiksjon"
    assert headings[-1] == "§ 5 A-9. Tilsyn"


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w69b_karanteneloven_substitution_witness_lowers_all_15_addresses() -> None:
    """W-69a/b corpus witness: karanteneloven's 15 substitution addresses.

    ``no/lovtid/2025-02-07-1`` announces ``tilsettingsmyndigheten`` →
    ``ansettelsesmyndigheten`` over 13 provisions of ``no/lov/2015-06-19-70``
    in a sibling ``change`` node, and ``tilsettingen`` → ``ansettelsen`` over 2
    more in a node carrying its own announcement. Before W-75 every one of those
    15 lowered as a REPLACE whose payload was the address list; W-75 refused them
    all; W-69a lowered the 7 ledd addresses as addressed TEXT_PATCHes and refused
    the 8 sentence addresses typed; **W-69b lowers all 15**, the sentence ones
    included. Nothing carries the announcement as payload in any of the four
    states, and the instrument's genuine work — the new § 1 a — is untouched
    throughout.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2025-02-07-1", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(html_bytes, "no/lovtid/2025-02-07-1", adjudications_out=adjudications)
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED]
    assert not [a for a in adjudications if a.kind.startswith("no_parse_substitution")]

    ops = grouped["no/lov/2015-06-19-70"]
    substitutions = [op for op in ops if NO_SUBSTITUTION_PROVENANCE_TAG in op.provenance_tags]
    assert [
        (op.target.path, op.text_patch.selector.match_text) for op in substitutions if op.text_patch
    ] == [
        ((("section", "13"), ("subsection", "1")), "tilsettingsmyndigheten"),
        ((("section", "13"), ("subsection", "2"), ("sentence", "1")), "tilsettingsmyndigheten"),
        ((("section", "14"), ("subsection", "2")), "tilsettingsmyndigheten"),
        ((("section", "14"), ("subsection", "4")), "tilsettingsmyndigheten"),
        ((("section", "15"), ("subsection", "1")), "tilsettingsmyndigheten"),
        ((("section", "17"), ("subsection", "1"), ("sentence", "1")), "tilsettingsmyndigheten"),
        ((("section", "17"), ("subsection", "1"), ("sentence", "3")), "tilsettingsmyndigheten"),
        ((("section", "18"), ("subsection", "1"), ("sentence", "1")), "tilsettingsmyndigheten"),
        ((("section", "18"), ("subsection", "2"), ("sentence", "1")), "tilsettingsmyndigheten"),
        ((("section", "18"), ("subsection", "3"), ("sentence", "2")), "tilsettingsmyndigheten"),
        ((("section", "19"), ("subsection", "1"), ("sentence", "1")), "tilsettingsmyndigheten"),
        ((("section", "20"), ("subsection", "1")), "tilsettingsmyndigheten"),
        ((("section", "20"), ("subsection", "4")), "tilsettingsmyndigheten"),
        ((("section", "14"), ("subsection", "1"), ("sentence", "1")), "tilsettingen"),
        ((("section", "14"), ("subsection", "4")), "tilsettingen"),
    ]
    # Not one op is left carrying the address list or the announcement.
    assert not [
        op
        for op in ops
        if op.payload is not None
        and ("I følgende bestemmelser" in (op.payload.text or "") or "§ 13 første ledd," in (op.payload.text or ""))
    ]
    # The instrument's genuine work survives: the new § 1 a it enacts.
    assert (("section", "1a"),) in [op.target.path for op in ops]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w69b_karanteneloven_replay_lands_its_substitutions_and_refuses_two() -> None:
    """W-69a/b end to end, on the payoff law, against the real archive.

    Thirteen of karanteneloven's fifteen lowered addresses land and two refuse,
    both on the matching rule rather than on addressing:

    * ``§ 20 fjerde ledd`` carries only the genitive ``tilsettingsmyndighetens``
      (``substring_only``) — W-69a's measured price, one row that stays open;
    * ``§ 17 første ledd første punktum`` carries only ``Tilsettingsmyndigheten``
      capitalised (``inflection_only``) — W-69b's, and the reason the item's
      eight sentence addresses on this law close SIX divergence rows and not
      seven: ``§ 17 første ledd`` holds two of them, ``tredje punktum`` lands
      and ``første punktum`` refuses, so that ledd still diverges.

    Six of the landings are W-69a's ledd addresses; the other seven are the
    sentence addresses this item put in scope, each one landing on the addressed
    ``punktum`` rather than on its ledd.
    """
    from lawvm.norway.index import build_no_amendment_index
    from lawvm.norway.replay import replay_no_to_pit

    data_dir = cast(Path, _NO_FARCHIVE_PATH)
    result = replay_no_to_pit(
        "no/lov/2015-06-19-70",
        "2026-07-10",
        data_dir=data_dir,
        index=build_no_amendment_index(data_dir),
    )
    replayed = result.replayed
    assert replayed is not None
    refusals = [
        a for a in result.adjudications if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT
    ]
    assert sorted(
        ((a.detail or {}).get("target"), (a.detail or {}).get("reason")) for a in refusals
    ) == [
        ("section:17/subsection:1/sentence:1", "inflection_only"),
        ("section:20/subsection:4", "substring_only"),
    ]
    landed = [
        receipt
        for receipt in (result.write_receipts or ())
        if str(receipt.action) == "text_replace"
    ]
    assert len(landed) == 13
    # W-69b's own contribution: the materialization the text-patch branch could
    # not reach before, once per ledd a landed sentence address names.
    materialized = [
        a for a in result.adjudications if a.kind == "no_replay_sentence_children_materialized"
    ]
    assert sorted((a.detail or {}).get("target", "") for a in materialized) == [
        "section:13/subsection:2/sentence:1",
        "section:14/subsection:1/sentence:1",
        "section:17/subsection:1/sentence:1",
        "section:17/subsection:1/sentence:3",
        "section:18/subsection:1/sentence:1",
        "section:18/subsection:2/sentence:1",
        "section:18/subsection:3/sentence:2",
        "section:19/subsection:1/sentence:1",
    ]

    def _ledd_text(label: str, subsection: str) -> str:
        section = next(
            node
            for node in _no_walk(replayed.body)
            if getattr(node.kind, "value", node.kind) == "section" and node.label == label
        )
        ledd = next(child for child in section.children if child.label == subsection)
        return " ".join(part for part in _no_all_texts(ledd))

    assert "ansettelsesmyndigheten" in _ledd_text("13", "1")
    assert "tilsettingsmyndigheten" not in _ledd_text("13", "1")
    # …and the whole-word refusal leaves § 20 fjerde ledd standing, honestly.
    assert "tilsettingsmyndighetens" in _ledd_text("20", "4")


#: W-69b's population, membership-level: every substitution op the parse plane
#: mints whose target leaf is a SENTENCE, keyed on content
#: ``(instrument, base act, address, FROM, TO)``. It is exactly the 21 addresses
#: W-69a refused with ``no_parse_substitution_sentence_address_out_of_scope`` —
#: the frozen withdrawal set, matched element for element. Four instruments,
#: four base acts, five announced pairs; ``§ 12 første ledd første/tredje
#: punktum`` of ``no/lov/2020-04-17-29`` appears twice because TWO announcements
#: in ``no/lovtid/2025-12-22-129`` list it, and each lowers its own op.
_NO_W69B_SENTENCE_ADDRESSED_SUBSTITUTIONS = (
    ("no/lovtid/2024-06-21-42", "no/lov/1998-07-17-56", "section:7-6/subsection:4/sentence:1", "store foretak", "foretak av allmenn interesse"),
    ("no/lovtid/2024-06-21-52", "no/lov/2008-06-27-71", "section:11-12/subsection:2/sentence:2", "gjennom elektroniske medier", "på internett"),
    ("no/lovtid/2024-06-21-52", "no/lov/2008-06-27-71", "section:11-14/subsection:1/sentence:1", "gjennom elektroniske medier", "på internett"),
    ("no/lovtid/2024-06-21-52", "no/lov/2008-06-27-71", "section:11-15/subsection:2/sentence:1", "gjennom elektroniske medier", "på internett"),
    ("no/lovtid/2024-06-21-52", "no/lov/2008-06-27-71", "section:12-10/subsection:1/sentence:2", "gjennom elektroniske medier", "på internett"),
    ("no/lovtid/2024-06-21-52", "no/lov/2008-06-27-71", "section:12-8/subsection:3/sentence:1", "gjennom elektroniske medier", "på internett"),
    ("no/lovtid/2024-06-21-52", "no/lov/2008-06-27-71", "section:8-5/subsection:5/sentence:1", "gjennom elektroniske medier", "på internett"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:13/subsection:2/sentence:1", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:14/subsection:1/sentence:1", "tilsettingen", "ansettelsen"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:17/subsection:1/sentence:1", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:17/subsection:1/sentence:3", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:18/subsection:1/sentence:1", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:18/subsection:2/sentence:1", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:18/subsection:3/sentence:2", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-02-07-1", "no/lov/2015-06-19-70", "section:19/subsection:1/sentence:1", "tilsettingsmyndigheten", "ansettelsesmyndigheten"),
    ("no/lovtid/2025-12-22-129", "no/lov/2020-04-17-29", "section:11/subsection:1/sentence:1", "Dagligvaretilsynet", "Konkurransetilsynet"),
    ("no/lovtid/2025-12-22-129", "no/lov/2020-04-17-29", "section:12/subsection:1/sentence:1", "Dagligvaretilsynet", "Konkurransetilsynet"),
    ("no/lovtid/2025-12-22-129", "no/lov/2020-04-17-29", "section:12/subsection:1/sentence:1", "Markedsrådet", "Konkurranseklagenemnda"),
    ("no/lovtid/2025-12-22-129", "no/lov/2020-04-17-29", "section:12/subsection:1/sentence:3", "Dagligvaretilsynet", "Konkurransetilsynet"),
    ("no/lovtid/2025-12-22-129", "no/lov/2020-04-17-29", "section:12/subsection:1/sentence:3", "Markedsrådet", "Konkurranseklagenemnda"),
    ("no/lovtid/2025-12-22-129", "no/lov/2020-04-17-29", "section:18/subsection:2/sentence:2", "Markedsrådet", "Konkurranseklagenemnda"),
)

_W69B_POPULATION_INSTRUCTION = (
    "Re-derive with `.tmp/w69b/f4_pinlit.py` (or an equivalent corpus scan for "
    "substitution-tagged TEXT_PATCH ops whose target leaf is a sentence) and "
    "adjudicate every added, removed or retargeted row BEFORE moving the pin: "
    "each of these writes live law at PUNKTUM depth, where a wrong address is "
    "invisible in a ledd-level diff."
)


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w69b_sentence_addressed_substitution_population_is_pinned() -> None:
    """W-69b's standing tripwire: the sentence-addressed population, membership-level.

    Twenty-one ops over 3,089 amendment artifacts, on four base acts. This is
    the SAME 21 that W-69a refused with
    ``no_parse_substitution_sentence_address_out_of_scope``, which is why that
    receipt kind is retired rather than left at zero — and the test asserts the
    retirement directly: no adjudication anywhere in the corpus may carry the
    dead kind, and every sentence address must arrive as an op instead.

    A 22nd row is not automatically wrong, but it is automatically a finding:
    the parse plane cannot see whether the address resolves, so the only thing
    standing between a new row and a wrong write at punktum depth is this pin
    plus the apply-plane term conjuncts.
    """
    from lawvm.norway.grafter import parse_no_amendment_groups
    from lawvm.norway.sources import iter_no_amendment_artifacts

    artifacts = 0
    found: list[tuple[str, str, str, str, str]] = []
    dead_kind: list[str] = []
    for artifact in iter_no_amendment_artifacts(cast(Path, _NO_FARCHIVE_PATH)):
        artifacts += 1
        adjudications: list[CompileAdjudication] = []
        groups = parse_no_amendment_groups(
            artifact.payload, artifact.logical_id, adjudications_out=adjudications
        )
        dead_kind.extend(
            a.kind
            for a in adjudications
            if a.kind == "no_parse_substitution_sentence_address_out_of_scope"
        )
        for base_id, ops in groups:
            for op in ops:
                if NO_SUBSTITUTION_PROVENANCE_TAG not in (op.provenance_tags or ()):
                    continue
                if not op.target.path or op.target.leaf_kind() != "sentence":
                    continue
                assert op.text_patch is not None
                found.append(
                    (
                        artifact.logical_id,
                        base_id,
                        "/".join(f"{kind}:{label}" for kind, label in op.target.path),
                        op.text_patch.selector.match_text,
                        op.text_patch.replacement or "",
                    )
                )

    assert artifacts == 3089, (
        f"the amendment plane holds {artifacts} artifacts, not 3,089; the census "
        "below is measured over a different corpus. " + _W69B_POPULATION_INSTRUCTION
    )
    assert dead_kind == [], (
        "`no_parse_substitution_sentence_address_out_of_scope` is retired by W-69b; "
        "something is still emitting it. " + _W69B_POPULATION_INSTRUCTION
    )
    assert tuple(sorted(found)) == _NO_W69B_SENTENCE_ADDRESSED_SUBSTITUTIONS, (
        "The sentence-addressed word substitutions are not the pinned set. "
        + _W69B_POPULATION_INSTRUCTION
    )


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w69b_the_two_unservable_sentence_addresses_stay_refused_typed() -> None:
    """The 2 of 21 W-69b does not serve, on the corpus, with their siblings.

    ``no/lov/2020-04-17-29`` § 11 første ledd and § 18 andre ledd are absent
    from the replayed tree — that law's own ``§ 11 fjerde ledd oppheves`` +
    relabel sequence is not lowered, so five of its LEDD-addressed substitution
    ops have never resolved either (§ 11 andre ledd is refused twice, once per
    announcement). The two sentence addresses beneath those ledd fail for
    exactly that reason and no other, so they take exactly that receipt:
    ``replay_unresolved_target``, alongside the five. Read the assertion
    as a claim about the DEFECT, not about sentences — if sentence addresses
    ever started refusing for a reason of their own, this list would stop
    interleaving with the ledd list and the test would say so.
    """
    from lawvm.norway.index import build_no_amendment_index
    from lawvm.norway.replay import replay_no_to_pit

    data_dir = cast(Path, _NO_FARCHIVE_PATH)
    result = replay_no_to_pit(
        "no/lov/2020-04-17-29",
        "2026-07-10",
        data_dir=data_dir,
        index=build_no_amendment_index(data_dir),
    )
    assert result.replayed is not None
    unresolved = sorted(
        str((a.detail or {}).get("target", ""))
        for a in result.adjudications
        if a.kind == "replay_unresolved_target"
        and "text_replace" == str((a.detail or {}).get("action", ""))
    )
    assert unresolved == [
        "section:11/subsection:1/sentence:1",
        "section:11/subsection:2",
        "section:11/subsection:2",
        "section:11/subsection:3",
        "section:11/subsection:4",
        "section:18/subsection:1",
        "section:18/subsection:2/sentence:2",
    ]
    # No sentence op on this law may reach a WRITE it could not resolve: the
    # twelve that land are the four sentence-addressed ones under § 12 plus the
    # eight ledd-addressed ones whose ledd do exist.
    landed = [r for r in (result.write_receipts or ()) if str(r.action) == "text_replace"]
    assert len(landed) == 12
    assert not [
        a
        for a in result.adjudications
        if a.kind == NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT
    ]


def _no_walk(node: IRNode):
    yield node
    for child in node.children:
        yield from _no_walk(child)


def _no_all_texts(node: IRNode):
    if node.text:
        yield node.text
    for child in node.children:
        yield from _no_all_texts(child)


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w75_multi_address_non_substitution_change_node_is_untouched() -> None:
    """W-75 corpus witness: the 232 legitimate multi-address nodes keep lowering.

    ``no/lovtid/2022-05-12-28`` re-enacts domstolloven chapter 11 with a
    four-address ``data-change-part`` and a real payload. Nothing about it is a
    substitution, and the refusal must not see it.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2022-05-12-28", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(html_bytes, "no/lovtid/2022-05-12-28", adjudications_out=adjudications)
    )

    assert not [a for a in adjudications if a.kind == NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED]
    ops = grouped["no/lov/1915-08-13-5"]
    # W-101 moved this pin: the block's ``kap11`` token now lowers to a
    # heading-only chapter REPLACE that stands before the sections it announces
    # (``Kapittel 11 med §§ 218, 219 og 220 skal lyde:``); 20 → 21 ops.
    assert [(str(op.action.value), op.target.path) for op in ops][:5] == [
        ("insert", (("section", "217a"),)),
        ("replace", (("chapter", "11"),)),
        ("replace", (("section", "218"),)),
        ("replace", (("section", "219"),)),
        ("replace", (("section", "220"),)),
    ]
    assert len(ops) == 21
    replace_218 = next(op for op in ops if op.target.path == (("section", "218"),))
    assert replace_218.payload is not None
    assert (replace_218.payload.children[0].text or "").startswith(
        "For å få tillatelse til å være advokat ved Høyesterett"
    )


# ── W-66: the atomic sibling-set ledd relabel ────────────────────────────────


def test_no_w66_set_relabel_tries_the_shipped_sentence_parser_first() -> None:
    """W-66: the additive ordering is a test's fact, not a comment's claim.

    ``_no_ledd_set_relabel_pairs`` returns WHICH attempt matched. Everything
    W-56's shipped ``_no_ledd_shift_pairs_from_sentence`` already parses must come
    back tagged ``shipped`` — the widened pattern is only ever reached on a
    sentence the shipped one declined, so no sentence that parses today can change
    what it parses.
    """
    # The W-66 payoff witness, no/lovtid/2017-06-16-67 → no/lov/2015-02-13-9.
    # NOTE the arity: "og nytt syvende" is the SECOND destination of a 2 → 2
    # bijection with the newness marker on it, NOT a third limb. The ledger's
    # sizing called this an unequal 2 → 3 shape; it is not, and no unequal-arity
    # relabel occurs anywhere in the accepted population.
    assert _no_ledd_set_relabel_pairs("Nåværende § 3 femte og sjette ledd blir sjette og nytt syvende ledd.") == (
        "3",
        [(5, 6), (6, 7)],
        "shipped",
    )
    # Section spelled AFTER the qualifier — no/lovtid/2009-06-19-109.
    assert _no_ledd_set_relabel_pairs("§ 29 nåværende fjerde til sjette ledd blir femte til sjuende ledd.") == (
        "29",
        [(4, 5), (5, 6), (6, 7)],
        "shipped",
    )
    # No section of its own: the address is the walk's problem, not the
    # sentence parser's. Empty string, never a guess.
    assert _no_ledd_set_relabel_pairs("Nåværende femte og sjette ledd blir sjette og sjuende ledd.") == (
        "",
        [(5, 6), (6, 7)],
        "shipped",
    )


def test_no_w66_set_relabel_widening_is_the_currency_qualifier_and_nothing_else() -> None:
    """W-66: 50 accepted occurrences (47 distinct leads) need only W-61's set.

    The widened attempt differs from the shipped one in exactly one token. Both
    word orders are attested, so both are witnessed here.
    """
    # no/lovtid/2003-07-04-78 → straffeprosessloven 1902.
    assert _no_ledd_set_relabel_pairs("Gjeldende fjerde ledd blir nytt tredje ledd.") == ("", [(4, 3)], "widened")
    # no/lovtid/2018-06-15-38 → no/lov/2017-06-16-53.
    assert _no_ledd_set_relabel_pairs("Någjeldende annet ledd blir tredje ledd.") == ("", [(2, 3)], "widened")
    # nynorsk, with a ``til`` range through the shared ordinal vocabulary.
    assert _no_ledd_set_relabel_pairs("Gjeldande andre til fjerde ledd blir tredje til femte ledd.") == (
        "",
        [(2, 3), (3, 4), (4, 5)],
        "widened",
    )


def test_no_w66_set_relabel_requires_the_currency_qualifier() -> None:
    """W-66: the qualifier is the premise, so it cannot be optional.

    "Andre ledd blir nytt tredje ledd." says nothing about which edition its
    ordinals are read against, and reading the source set against the
    PRE-operation snapshot is this production's whole claim. 55 further corpus
    occurrences, 55 distinct leads, are left refused by this line — deliberately
    and measurably.

    The same anchoring is what keeps ordinary statutory prose out: a sentence
    that merely CONTAINS "… ledd blir …" cannot reduce, end to end, to two
    ordinal lists.
    """
    assert _no_ledd_set_relabel_pairs("Andre ledd blir nytt tredje ledd.") is None
    assert _no_ledd_set_relabel_pairs("Femte ledd blir nytt sjette ledd.") is None
    assert (
        _no_ledd_set_relabel_pairs(
            "Dersom slikt pålegg som nevnt i femte ledd ikke blir fulgt, avgjøres saken etter tredje ledd."
        )
        is None
    )
    # Two pivots in one sentence: a shape this grammar cannot attribute.
    assert (
        _no_ledd_set_relabel_pairs(
            "Gjeldende femte ledd blir sjette ledd og gjeldende sjette ledd blir syvende ledd."
        )
        is None
    )
    # A trailing payload clause — the lead is not fully accounted for, so it
    # lowers nothing (the same polarity W-61's 19 trailing-clause leads get).
    assert _no_ledd_set_relabel_pairs("Nåværende tredje ledd blir nytt fjerde ledd og skal lyde:") is None
    # Another container depth is a different address arithmetic.
    assert _no_ledd_set_relabel_pairs("Nåværende annet punktum blir nytt tredje punktum.") is None
    # An identity leg means the sentence is not a relabel at all.
    assert _no_ledd_set_relabel_pairs("Nåværende tredje ledd blir tredje ledd.") is None
    # Unequal arity: nothing pairs the surplus, so nothing lowers.
    assert _no_ledd_set_relabel_pairs("Nåværende tredje og fjerde ledd blir femte ledd.") is None


def test_no_w66_relabel_order_vacates_before_it_occupies() -> None:
    """W-66: the atomicity property, stated as an order and proven as a DAG.

    A leg may only run once every leg whose SOURCE is its destination has run.
    For an overlapping +1 shift that is descending order; for a −1 shift it is
    ascending; and for the one corpus lead that is not a uniform shift at all it
    is neither, which is why this is a topological sort rather than a sign test.
    """
    assert _no_ordered_set_relabel_pairs([(5, 6), (6, 7)]) == [(6, 7), (5, 6)]
    assert _no_ordered_set_relabel_pairs([(4, 3), (5, 4)]) == [(4, 3), (5, 4)]
    assert _no_ordered_set_relabel_pairs([(2, 3), (3, 4), (4, 5)]) == [(4, 5), (3, 4), (2, 3)]
    # Independent legs keep their source order.
    assert _no_ordered_set_relabel_pairs([(1, 9), (2, 8)]) == [(1, 9), (2, 8)]


def test_no_w66_relabel_refuses_a_pair_set_with_no_safe_order() -> None:
    """W-66: a swap has no sequential relabel, so it is refused, not ordered.

    No accepted corpus lead is cyclic today, so this guard fires nowhere. It is
    here because the ABSENCE of a cycle is the only reason the emitted order is a
    proof rather than a preference.
    """
    assert _no_ordered_set_relabel_pairs([(3, 4), (4, 3)]) is None
    assert _no_ordered_set_relabel_pairs([(1, 2), (2, 3), (3, 1)]) is None


def _w66_children(*nodes: str) -> list[etree._Element]:
    xml = "<main>" + "".join(nodes) + "</main>"
    return list(etree.fromstring(xml.encode("utf-8")))


def test_no_w66_address_inheritance_reads_the_preceding_instruction_lead() -> None:
    """W-66: the antecedent is the nearest preceding ``article.defaultP``.

    The payload classes are excluded, and that is load-bearing rather than tidy:
    on the witness instrument the node physically preceding the shift is the
    PAYLOAD of the lead before it and names a foreign "§ 9". A nearest-any-node
    rule inherits the wrong section; this rule inherits § 3.
    """
    children = _w66_children(
        '<article class="defaultP">5. I lov 13. februar 2015 nr. 9 om utenrikstjenesten skal § 3 femte ledd lyde:</article>',
        '<article class="legalP">Statsansatteloven § 9 tredje ledd om at statsansatt som er midlertidig ansatt …</article>',
        '<article class="defaultP">Nåværende femte og sjette ledd blir sjette og nytt syvende ledd.</article>',
    )
    assert _no_antecedent_section_label(children, [0, 0, 0], 2) == ("3", "antecedent_names_section")
    # A letter-suffixed section survives; a following word does NOT become one.
    assert _no_antecedent_section_label(
        _w66_children(
            '<article class="defaultP">§ 12-1 nytt tredje ledd skal lyde:</article>',
            '<article class="defaultP">Nåværende tredje ledd blir nytt fjerde ledd.</article>',
        ),
        [0, 0],
        1,
    ) == ("12-1", "antecedent_names_section")
    assert _no_antecedent_section_label(
        _w66_children(
            '<article class="defaultP">§ 391 a tredje ledd oppheves.</article>',
            '<article class="defaultP">Gjeldende fjerde ledd blir nytt tredje ledd.</article>',
        ),
        [0, 0],
        1,
    ) == ("391a", "antecedent_names_section")


def test_no_w66_address_inheritance_refuses_rather_than_guesses() -> None:
    """W-66: every way the antecedent can fail, and the typed reason for it.

    The law-switch case is the one that matters most. A part that changes base act
    does so with a ``defaultP`` lead naming no section, so a shift immediately
    after it inherits NOTHING — the rule is self-guarding across law boundaries
    instead of silently carrying the previous act's section over.
    """
    shift = '<article class="defaultP">Nåværende annet ledd blir tredje ledd.</article>'
    assert _no_antecedent_section_label(
        _w66_children(
            '<article class="defaultP">6. I lov 19. juni 2015 nr. 70 om karantene gjøres følgende endringer:</article>',
            shift,
        ),
        [0, 0],
        1,
    ) == (None, "antecedent_names_no_section")
    assert _no_antecedent_section_label(
        _w66_children('<article class="defaultP">§ 5 og § 7 oppheves.</article>', shift),
        [0, 0],
        1,
    ) == (None, "antecedent_names_several_sections")
    # Amending another AMENDMENT establishes an address in that amendment, not in
    # the base act. 7 corpus antecedents, all refused.
    assert _no_antecedent_section_label(
        _w66_children('<article class="defaultP">I endringen av § 19-8 skal nytt sjette ledd lyde:</article>', shift),
        [0, 0],
        1,
    ) == (None, "antecedent_is_meta_amendment")
    # A part boundary stops the search; so does the start of the document.
    assert _no_antecedent_section_label(
        _w66_children('<article class="defaultP">§ 4 tredje ledd skal lyde:</article>', shift),
        [0, 1],
        1,
    ) == (None, "part_has_no_antecedent_lead")


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w66_set_relabel_lowers_on_the_payoff_witness_instrument() -> None:
    """W-66 corpus witness: ``no/lovtid/2017-06-16-67`` → ``no/lov/2015-02-13-9``.

    Item 5 of part ``kapVII`` is two nodes: "… skal § 3 femte ledd lyde:" with its
    payload, then "Nåværende § 3 femte og sjette ledd blir sjette og nytt syvende
    ledd." Before W-66 the second node was refused whole and § 3's ledd sequence
    stayed one slot out of step with the consolidation — five unexplained
    divergence rows.

    Three separate facts are pinned here, because three separate things have to be
    right for the result to be right:
      1. the relabel lowers to TWO RENUMBER ops, not one and not three;
      2. they are emitted VACATE-FIRST (6 → 7 before 5 → 6), so neither ever
         lands on a live sibling;
      3. the co-located "skal lyde" REPLACE at § 3 ledd 5 is promoted to INSERT by
         the shipped ``_promote_no_replace_with_following_renumber_insert``, which
         is what makes the pair "insert a new fifth ledd and push the old ones
         down" rather than "overwrite the fifth ledd and then move it".
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2017-06-16-67", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(html_bytes, "no/lovtid/2017-06-16-67", adjudications_out=adjudications)
    )
    ops = grouped["no/lov/2015-02-13-9"]

    relabel = [
        op
        for op in ops
        if op.action is StructuralAction.RENUMBER
        and op.source is not None
        and op.source.raw_text
        == "Nåværende § 3 femte og sjette ledd blir sjette og nytt syvende ledd."
    ]
    assert [(op.target.path, cast(LegalAddress, op.destination).path) for op in relabel] == [
        ((("section", "3"), ("subsection", "6")), (("section", "3"), ("subsection", "7"))),
        ((("section", "3"), ("subsection", "5")), (("section", "3"), ("subsection", "6"))),
    ]
    assert {op.witness_rule_id for op in relabel} == {"no_section_renumber_relabel"}
    assert [op.sequence for op in relabel] == sorted(op.sequence for op in relabel)

    promoted = [
        op
        for op in ops
        if op.target.path == (("section", "3"), ("subsection", "5"))
        and op.action is not StructuralAction.RENUMBER
    ]
    assert [str(op.action.value) for op in promoted] == ["insert"]

    assert "Nåværende § 3 femte og sjette ledd blir sjette og nytt syvende ledd." not in {
        (item.detail or {}).get("source_excerpt")
        for item in adjudications
        if item.kind == "no_parse_unstructured_lead_unmatched"
    }


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w66_unaddressable_relabel_gets_a_typed_receipt_not_a_guess() -> None:
    """W-66: 40 corpus receipt triples over 37 leads refuse on the address.

    ``no/lovtid/2019-12-13-79`` part ``kapXIV`` opens a law-switch item whose lead
    names no section, so the relabel immediately after it has no antecedent to
    inherit from. It gets the typed receipt rather than the generic
    ``no_parse_unstructured_lead_unmatched`` — and, crucially, no ops.

    Since W-76 this instrument carries a THIRD receipt of the same kind, on
    ``no/lov/1999-12-17-95``, from the item-depth relabel lane failing the same
    helper the same way in the same part. The kind is deliberately shared (see
    the catalog entry); the ``production`` detail key is what separates the
    lanes, and it is asserted here so the sharing stays visible rather than
    silently absorbing a fourth family.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2019-12-13-79", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(html_bytes, "no/lovtid/2019-12-13-79", adjudications_out=adjudications)
    )

    typed = [item for item in adjudications if item.kind == NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED]
    assert {(item.detail or {}).get("base_id") for item in typed} == {
        "no/lov/1999-12-17-95",
        "no/lov/2000-03-24-16",
        "no/lov/2000-11-24-81",
    }
    assert {
        ((item.detail or {}).get("base_id"), (item.detail or {}).get("production"))
        for item in typed
    } == {
        ("no/lov/1999-12-17-95", "item_set_relabel"),
        ("no/lov/2000-03-24-16", None),
        ("no/lov/2000-11-24-81", None),
    }
    assert {(item.detail or {}).get("address_reason") for item in typed} == {"part_has_no_antecedent_lead"}
    assert all(
        op.action is not StructuralAction.RENUMBER or "subsection" not in dict(op.target.path)
        for op in grouped.get("no/lov/2000-03-24-16", ())
    )


def _w66_relabel_op(sequence: int, section: str, src: int, dst: int) -> LegalOperation:
    from lawvm.norway.grafter import NO_LEDD_SET_RELABEL_PROVENANCE_TAG

    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=(("section", section), ("subsection", str(src)))),
        destination=LegalAddress(path=(("section", section), ("subsection", str(dst)))),
        source=OperationSource(statute_id="no/lovtid/9999-01-01-1", raw_text="relabel", title="x"),
        provenance_tags=("base_act:no/lov/1999-01-01-1", "fallback:unstructured", NO_LEDD_SET_RELABEL_PROVENANCE_TAG),
        group_id=f"no/lovtid/9999-01-01-1:{sequence}",
        witness_rule_id="no_section_renumber_relabel",
    )


def _w66_statute(n_ledd: int) -> IRStatute:
    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="7",
                    children=tuple(
                        IRNode(kind=IRNodeKind.SUBSECTION, label=str(i), text=f"ledd {i}")
                        for i in range(1, n_ledd + 1)
                    ),
                ),
            ),
        ),
    )


def test_no_w66_relabel_applies_when_the_top_destination_is_free() -> None:
    """W-66 apply: the ordinary case, and it must still work.

    A five-ledd section, "current fourth and fifth become fifth and sixth". Slot 6
    does not exist, so nothing is written over and both legs land.
    """
    ops = [_w66_relabel_op(1, "7", 5, 6), _w66_relabel_op(2, "7", 4, 5)]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(_w66_statute(5), ops, adjudications_out=adjudications)
    section = result.body.children[0]
    assert [(child.label, child.text) for child in section.children] == [
        ("1", "ledd 1"),
        ("2", "ledd 2"),
        ("3", "ledd 3"),
        ("5", "ledd 4"),
        ("6", "ledd 5"),
    ]
    assert not [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]


def test_no_w66_relabel_refuses_whole_rather_than_eat_an_occupant() -> None:
    """W-66 apply: the safety property, and the CASCADE that makes it whole.

    Same relabel against a SIX-ledd section — the shape of a base edition that
    already carries the amendment being replayed, which is what straffeloven 2005
    § 3 and verdipapirhandelloven § 9-21 actually are. Slot 6 is occupied by live
    text this relabel does not move.

    Under the declared θ (RENUMBER, dest_occupied) recovery, ledd 6 would be
    DELETED and 4/5 shifted onto 5/6. Here the 5 → 6 leg refuses; slot 5 is
    therefore still occupied when the 4 → 5 leg runs, so that one refuses too —
    and the tree comes out untouched rather than half-shifted, which is the W-56
    partial-cascade failure mode.
    """
    ops = [_w66_relabel_op(1, "7", 5, 6), _w66_relabel_op(2, "7", 4, 5)]
    before = _w66_statute(6)
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)
    assert [(child.label, child.text) for child in result.body.children[0].children] == [
        (child.label, child.text) for child in before.body.children[0].children
    ]
    refusals = [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert [a.op_id for a in refusals] == [
        "no/lovtid/9999-01-01-1:1",
        "no/lovtid/9999-01-01-1:2",
    ]
    assert all(a.blocking for a in refusals)
    assert [(a.detail or {}).get("destination_path") for a in refusals] == [
        "section:7/subsection:6",
        "section:7/subsection:5",
    ]
    # The second leg's destination IS a source of the same group — the condition
    # the shipped code exempts from the occupancy check because the ordering
    # promises it will have been vacated. Once a leg may refuse that promise is
    # void, and the receipt records which case it was.
    assert [(a.detail or {}).get("destination_was_renumber_source") for a in refusals] == [False, True]
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


# ── W-66b: the same sibling-set relabel, one depth word down (PUNKTUM) ────────


def test_no_w66b_punktum_relabel_grammar_accepts_the_corpus_shapes() -> None:
    """W-66b: every shape the 112 lowering occurrences actually take.

    The return is ``(section, ledd, pairs, pattern)``: BOTH address levels may be
    spelled or left to the antecedent, and the pattern names the winner so the
    additive ordering below is a test's fact.
    """
    # The dominant shape: neither level spelled, both inherited (135 of 165).
    assert _no_punktum_set_relabel_pairs("Nåværende annet punktum blir nytt tredje punktum.") == (
        "",
        "",
        [(2, 3)],
        "punktum",
    )
    # A pair relabel, overlapping source and destination sets.
    assert _no_punktum_set_relabel_pairs(
        "Nåværende annet og tredje punktum blir nye tredje og fjerde punktum."
    ) == ("", "", [(2, 3), (3, 4)], "punktum")
    # The currency qualifier is drawn from W-61's measured set, exactly as at ledd
    # depth, and it may sit on either side of the ``§``.
    assert _no_punktum_set_relabel_pairs("Gjeldende tredje punktum blir nytt fjerde punktum.") == (
        "",
        "",
        [(3, 4)],
        "punktum",
    )
    assert _no_punktum_set_relabel_pairs("Nåværende § 155 annet punktum blir tredje punktum.") == (
        "155",
        "",
        [(2, 3)],
        "punktum",
    )
    assert _no_punktum_set_relabel_pairs(
        "§ 23-4 a nåværende tredje punktum blir nytt fjerde punktum."
    ) == ("23-4a", "", [(3, 4)], "punktum")
    # BOTH levels spelled — the ledd phrase is split off the SOURCE side and read
    # through the shipped ordinal vocabulary.
    assert _no_punktum_set_relabel_pairs(
        "Nåværende § 14-70 tredje ledd annet punktum blir nytt tredje punktum."
    ) == ("14-70", "3", [(2, 3)], "punktum")
    assert _no_punktum_set_relabel_pairs(
        "Nåværende annet ledd annet punktum blir nytt tredje punktum."
    ) == ("", "2", [(2, 3)], "punktum")
    # ``til`` ranges and the ``nytt``/``nye`` newness markers behave exactly as at
    # ledd depth, because they go through the same helper.
    assert _no_punktum_set_relabel_pairs(
        "Nåværende annet til fjerde punktum blir nye tredje til femte punktum."
    ) == ("", "", [(2, 3), (3, 4), (4, 5)], "punktum")
    # A decreasing relabel is not special-cased anywhere.
    assert _no_punktum_set_relabel_pairs("Någjeldende fjerde punktum blir tredje punktum.") == (
        "",
        "",
        [(4, 3)],
        "punktum",
    )
    # No trailing full stop — one corpus lead is spelled that way.
    assert _no_punktum_set_relabel_pairs("Nåværende annet punktum blir nytt tredje punktum") == (
        "",
        "",
        [(2, 3)],
        "punktum",
    )


def test_no_w66b_punktum_relabel_grammar_refuses_what_it_must() -> None:
    """W-66b: the 16 corpus leads this grammar declines, one limb each.

    The destination-side limb is the safety-critical one. A destination that
    respells a ledd is a RELOCATION out of the sibling set, which is W-69's
    territory and the one thing this production must never lower — so the
    destination is read as ordinals ALONE and the cross-container case is
    impossible by construction rather than by a check that can be deleted.
    """
    # Cross-container: the destination names a DIFFERENT ledd.
    assert (
        _no_punktum_set_relabel_pairs(
            "Nåværende annet til fjerde punktum blir nytt fjerde ledd første til tredje punktum."
        )
        is None
    )
    # Same ledd, respelled on the destination side. Refused too, and deliberately:
    # the grammar does not get to decide which restatements are harmless.
    assert (
        _no_punktum_set_relabel_pairs(
            "Nåværende første ledd annet, tredje og fjerde punktum blir "
            "første ledd tredje, fjerde og femte punktum."
        )
        is None
    )
    # A ``bokstav``/``nr.`` container between the ledd and the punktum is an
    # address level this production does not model; the residue is not ordinals.
    assert (
        _no_punktum_set_relabel_pairs(
            "§ 18-3 nåværende annet ledd bokstav b annet punktum blir nytt tredje punktum."
        )
        is None
    )
    assert (
        _no_punktum_set_relabel_pairs("Noverande § 21 nr. 2 tredje punktum blir nytt fjerde punktum.")
        is None
    )
    # The currency qualifier is REQUIRED, for W-66's reason: a sentence that does
    # not say which edition its ordinals are read against cannot be read against
    # the pre-operation snapshot, which is this production's premise.
    assert _no_punktum_set_relabel_pairs("Annet punktum blir nytt tredje punktum.") is None
    # A payload tail. The pattern is anchored end to end.
    assert (
        _no_punktum_set_relabel_pairs("Nåværende annet punktum blir nytt tredje punktum og skal lyde:")
        is None
    )
    assert _no_punktum_set_relabel_pairs("Gjeldande andre punktum blir til nytt tredje punktum.") is None
    # The WRONG depth word is simply a different sentence.
    assert _no_punktum_set_relabel_pairs("Nåværende annet ledd blir nytt tredje ledd.") is None
    assert _no_punktum_set_relabel_pairs("Nåværende bokstav b blir ny bokstav c.") is None
    # The ordinal vocabulary is ``_NORWEGIAN_ORDINALS`` verbatim — not widened
    # here any more than it was at ledd depth.
    assert _no_punktum_set_relabel_pairs("Gjeldande sjette punktum blir nytt sjuande punktum.") is None
    # A parenthetical currency aside is not an ordinal list.
    assert (
        _no_punktum_set_relabel_pairs(
            "Nåværende (vedtatt, ikke ikrafttrådt) annet punktum blir nytt tredje punktum."
        )
        is None
    )
    # Degenerate pair sets, refused exactly as W-66 refuses them.
    assert _no_punktum_set_relabel_pairs("Nåværende tredje punktum blir tredje punktum.") is None
    assert (
        _no_punktum_set_relabel_pairs("Nåværende tredje og fjerde punktum blir femte punktum.") is None
    )


def test_no_w66b_punktum_grammar_leaves_the_shipped_ledd_grammar_alone() -> None:
    """W-66b is strictly ADDITIVE: the two grammars are disjoint by their anchors.

    The ledd grammar is tried first at the call site. Pinning the disjointness
    here means the ordering can never become load-bearing by accident — nothing
    W-66 lowers today can be captured by the new production, and nothing the new
    production lowers was reachable before.
    """
    ledd_sentence = "Nåværende femte og sjette ledd blir sjette og sjuende ledd."
    punktum_sentence = "Nåværende annet punktum blir nytt tredje punktum."
    assert _no_ledd_set_relabel_pairs(ledd_sentence) == ("", [(5, 6), (6, 7)], "shipped")
    assert _no_punktum_set_relabel_pairs(ledd_sentence) is None
    assert _no_ledd_set_relabel_pairs(punktum_sentence) is None
    assert _no_punktum_set_relabel_pairs(punktum_sentence) == ("", "", [(2, 3)], "punktum")


def test_no_w66b_ledd_inheritance_reads_the_same_antecedent_as_the_section() -> None:
    """W-66b: two levels, ONE antecedent node.

    That both come from the same ``article.defaultP`` is what makes the pair
    coherent — "§ 3-4 fjerde ledd nytt annet punktum skal lyde:" followed by
    "Nåværende annet punktum blir nytt tredje punktum." is one instruction in two
    sentences. Reading the section from one antecedent and the ledd from another
    could compose an address neither sentence names.
    """
    children = _w66_children(
        '<article class="defaultP">§ 3-4 fjerde ledd nytt annet punktum skal lyde:</article>',
        '<article class="legalP">Departementet kan gi forskrift om beregningen.</article>',
        '<article class="defaultP">Nåværende annet punktum blir nytt tredje punktum.</article>',
    )
    assert _no_antecedent_section_label(children, [0, 0, 0], 2) == ("3-4", "antecedent_names_section")
    assert _no_antecedent_ledd_label(children, [0, 0, 0], 2) == ("4", "antecedent_names_ledd")
    # The ordinal vocabulary is the shipped one, and both spellings of "2" work.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 5-2 andre ledd nytt annet punktum skal lyde:</article>',
            '<article class="defaultP">Nåværende annet punktum blir nytt tredje punktum.</article>',
        ),
        [0, 0],
        1,
    ) == ("2", "antecedent_names_ledd")


def test_no_w66b_ledd_inheritance_refuses_rather_than_guesses() -> None:
    """W-66b: every way the LEDD half can fail, and the typed reason for it.

    ``antecedent_is_not_punktum_depth`` is the conjunct W-66 has no need of. An
    antecedent that names a ledd while talking about whole ledds establishes that
    ledd as a PAYLOAD — its text is given in full, so it has no "nåværende"
    punktums for a follower to relabel, and inheriting from it would renumber the
    sentences of a provision that was just written. It changes no element of the
    measured corpus population; it is carried for W-66's cycle-guard reason.
    """
    shift = '<article class="defaultP">Nåværende annet punktum blir nytt tredje punktum.</article>'
    # 27 corpus refusals, every one of them this reason: a punktum hanging
    # directly under a section, or under a container the ledd reader cannot see.
    assert _no_antecedent_ledd_label(
        _w66_children('<article class="defaultP">§ 12 nytt annet punktum skal lyde:</article>', shift),
        [0, 0],
        1,
    ) == (None, "antecedent_names_no_ledd")
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 48 nr. 5 nytt annet punktum skal lyde:</article>', shift
        ),
        [0, 0],
        1,
    ) == (None, "antecedent_names_no_ledd")
    # Two ledd named: nothing unambiguous to inherit.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 59 første ledd og tredje ledd nytt annet punktum skal lyde:</article>',
            shift,
        ),
        [0, 0],
        1,
    ) == (None, "antecedent_names_several_ledd")
    # A whole-ledd antecedent: names a ledd, but not at punktum depth.
    assert _no_antecedent_ledd_label(
        _w66_children('<article class="defaultP">§ 13 nytt tredje ledd skal lyde:</article>', shift),
        [0, 0],
        1,
    ) == (None, "antecedent_is_not_punktum_depth")
    # W-66's meta-amendment guard, unchanged and for the same reason.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">I endringen av § 19-8 skal nytt sjette ledd annet punktum lyde:</article>',
            shift,
        ),
        [0, 0],
        1,
    ) == (None, "antecedent_is_meta_amendment")
    # A part boundary stops the search, exactly as it does for the section half.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 4 tredje ledd annet punktum skal lyde:</article>', shift
        ),
        [0, 1],
        1,
    ) == (None, "part_has_no_antecedent_lead")


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w66b_punktum_relabel_lowers_on_the_corpus_witness() -> None:
    """W-66b corpus witness: ``no/lovtid/2001-12-21-117`` → ``no/lov/1985-06-21-83``.

    The instrument carries the family's canonical pair twice: a "§ X <ord> ledd
    nytt <ord> punktum skal lyde:" INSERT and, right after it, "Nåværende annet
    punktum blir nytt tredje punktum." Before W-66b the second node refused whole.

    Three facts are pinned, because three things have to be right:
      1. the relabel lowers to a RENUMBER at SENTENCE depth whose ledd came from
         the antecedent and whose section came from the same node;
      2. the co-located payload op is already there at the very address the
         relabel vacates — which is what makes "insert a new second punktum and
         push the old one down" expressible at all;
      3. the op carries W-66's provenance tag, so the apply-plane refuse-on-
         occupied branch sees it without any change of its own.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2001-12-21-117", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(html_bytes, "no/lovtid/2001-12-21-117", adjudications_out=adjudications)
    )
    ops = grouped["no/lov/1985-06-21-83"]

    relabel = [
        op
        for op in ops
        if op.action is StructuralAction.RENUMBER
        and op.source is not None
        and op.source.raw_text == "Nåværende annet punktum blir nytt tredje punktum."
    ]
    assert [(op.target.path, cast(LegalAddress, op.destination).path) for op in relabel] == [
        (
            (("section", "3-4"), ("subsection", "4"), ("sentence", "2")),
            (("section", "3-4"), ("subsection", "4"), ("sentence", "3")),
        ),
        (
            (("section", "3-27"), ("subsection", "2"), ("sentence", "2")),
            (("section", "3-27"), ("subsection", "2"), ("sentence", "3")),
        ),
    ]
    from lawvm.norway.grafter import NO_LEDD_SET_RELABEL_PROVENANCE_TAG

    assert all(
        NO_LEDD_SET_RELABEL_PROVENANCE_TAG in (op.provenance_tags or ()) for op in relabel
    )
    assert {op.witness_rule_id for op in relabel} == {"no_section_renumber_relabel"}

    # The co-located payload sits at the address the relabel vacates.
    payload = [
        op
        for op in ops
        if op.target.path == (("section", "3-4"), ("subsection", "4"), ("sentence", "2"))
        and op.action is not StructuralAction.RENUMBER
    ]
    assert [str(op.action.value) for op in payload] == ["insert"]

    assert "Nåværende annet punktum blir nytt tredje punktum." not in {
        (item.detail or {}).get("source_excerpt")
        for item in adjudications
        if item.kind == "no_parse_unstructured_lead_unmatched"
    }


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w66b_unresolvable_ledd_gets_a_typed_receipt_not_a_guess() -> None:
    """W-66b: 27 corpus refusals resolve their SECTION but not their LEDD.

    The same witness instrument carries one: "§ 10-18 nytt annet punktum skal
    lyde:" names a section but no ledd, because that punktum hangs directly under
    the section. The relabel after it gets the new typed receipt — carrying the
    section it DID resolve, so the receipt says exactly how far the address got —
    and mints nothing.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2001-12-21-117", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(html_bytes, "no/lovtid/2001-12-21-117", adjudications_out=adjudications)
    )
    typed = [item for item in adjudications if item.kind == NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED]
    assert [
        (
            (item.detail or {}).get("base_id"),
            (item.detail or {}).get("section"),
            (item.detail or {}).get("address_reason"),
            (item.detail or {}).get("ledd_reason"),
            (item.detail or {}).get("pattern"),
        )
        for item in typed
    ] == [("no/lov/1997-06-13-44", "10-18", "antecedent_names_section", "antecedent_names_no_ledd", "punktum")]
    # Nothing was minted at that address on a guessed ledd.
    assert not [
        op
        for op in grouped.get("no/lov/1997-06-13-44", ())
        if op.action is StructuralAction.RENUMBER and op.target.path[0] == ("section", "10-18")
    ]


def _w66b_relabel_op(sequence: int, section: str, ledd: str, src: int, dst: int) -> LegalOperation:
    from lawvm.norway.grafter import NO_LEDD_SET_RELABEL_PROVENANCE_TAG

    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(
            path=(("section", section), ("subsection", ledd), ("sentence", str(src)))
        ),
        destination=LegalAddress(
            path=(("section", section), ("subsection", ledd), ("sentence", str(dst)))
        ),
        source=OperationSource(statute_id="no/lovtid/9999-01-01-1", raw_text="punktum relabel", title="x"),
        provenance_tags=(
            "base_act:no/lov/1999-01-01-1",
            "fallback:unstructured",
            NO_LEDD_SET_RELABEL_PROVENANCE_TAG,
        ),
        group_id=f"no/lovtid/9999-01-01-1:{sequence}",
        witness_rule_id="no_section_renumber_relabel",
    )


def _w66b_statute(ledd_text: str) -> IRStatute:
    """A one-ledd section carrying TEXT, not sentence children.

    That is the corpus shape, and it is the whole reason this production depended
    on W-69b: a ``setning/N`` address does not resolve until the parent ledd's
    text has been split into sentence children.
    """
    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="7",
                    children=(IRNode(kind=IRNodeKind.SUBSECTION, label="4", text=ledd_text),),
                ),
            ),
        ),
    )


def test_no_w66b_punktum_relabel_materializes_its_sibling_set_then_applies() -> None:
    """W-66b apply: the ordinary case, and it proves the W-69b dependency.

    The destination sibling set is SENTENCE children, which do not exist until
    something materializes them — the base ledd is a single text node. W-69b
    moved ``_materialize_sentence_parent_for`` ahead of target resolution on both
    dispatch arms, so a punktum-depth RENUMBER reaches it: the parent ledd is
    split into sentence children, the ``setning/2`` target then resolves, and slot
    3 does not exist so nothing is written over.

    The materialization is read-only on CONTENT: space-joining the sentence
    children reproduces the former ledd text exactly, which is asserted here
    rather than assumed.
    """
    before = _w66b_statute("Setning en. Setning to.")
    ops = [_w66b_relabel_op(1, "7", "4", 2, 3)]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert [(child.label, child.text) for child in ledd.children] == [
        ("1", "Setning en."),
        ("3", "Setning to."),
    ]
    assert " ".join(child.text or "" for child in ledd.children) == "Setning en. Setning to."
    # The shipped materialization receipt fired, and it is the shipped kind: the
    # mechanism is unchanged, only its reachability from this op is new.
    materialized = [
        a for a in adjudications if a.kind == "no_replay_sentence_children_materialized"
    ]
    assert [(a.detail or {}).get("materialized_parent_path") for a in materialized] == [
        "section:7/subsection:4"
    ]
    assert not [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]


def test_no_w66b_punktum_relabel_refuses_whole_rather_than_eat_an_occupant() -> None:
    """W-66b apply: the safety property CASCADES at punktum depth unchanged.

    A three-sentence ledd is the shape of a base edition that already carries the
    amendment being replayed — W-66's ``removal_wrong`` hazard, one depth down.
    "Current second and third become third and fourth" against it: the 3 → 4 leg
    finds slot 4 free and lands, but this statute has only three sentences, so the
    2 → 3 leg's destination is the slot the first leg just vacated.

    The case pinned here is the one that has teeth: a FOUR-sentence ledd, where
    the 3 → 4 leg lands on live text. It refuses, slot 3 is therefore still
    occupied when the 2 → 3 leg runs, so that one refuses too, and the ledd comes
    out untouched rather than half-shifted. No θ cell is reached.

    And "untouched" is literal, down to the SHAPE: a refused op's tentative state
    is discarded whole, so the materialization it performed to resolve its own
    target is rolled back with it. The ledd is still the single text node it was.
    That is worth pinning — a read-only shape change that SURVIVED a refusal
    would leave the statute in a form no landed op produced.
    """
    before = _w66b_statute("Setning en. Setning to. Setning tre. Setning fire.")
    ops = [_w66b_relabel_op(1, "7", "4", 3, 4), _w66b_relabel_op(2, "7", "4", 2, 3)]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert ledd.children == ()
    assert ledd.text == "Setning en. Setning to. Setning tre. Setning fire."
    assert ledd.text == before.body.children[0].children[0].text
    refusals = [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert [a.op_id for a in refusals] == [
        "no/lovtid/9999-01-01-1:1",
        "no/lovtid/9999-01-01-1:2",
    ]
    assert all(a.blocking for a in refusals)
    assert [(a.detail or {}).get("destination_path") for a in refusals] == [
        "section:7/subsection:4/sentence:4",
        "section:7/subsection:4/sentence:3",
    ]
    # The second leg's destination IS a source of the same group — the exemption
    # W-66 had to move the check in front of. Once a leg may refuse, the vacate
    # promise is void, and checking occupancy for real is what makes the whole
    # relabel drop together.
    assert [(a.detail or {}).get("destination_was_renumber_source") for a in refusals] == [False, True]
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


# ── W-66c: the punktum-depth REPEAL, the relabel's companion ─────────────────


def test_no_w66c_punktum_repeal_grammar_accepts_the_corpus_shapes() -> None:
    """W-66c: every shape the 248 lowering occurrences actually take.

    Measured over the 8,434 ``no_parse_unstructured_lead_unmatched`` refusals at
    the base pin, harvested UNTRUNCATED: 293 refusals / 235 distinct leads / 135
    instruments / 136 base acts, of which 248 lower over 279 REPEAL legs. The
    four address shapes below are the whole vocabulary — section and ledd both
    spelled, section spelled and ledd inherited, both inherited, and the plural /
    range target list.
    """
    assert _no_punktum_repeal_targets("§ 20 første ledd annet punktum oppheves.") == (
        "20",
        "1",
        [2],
    )
    # Section spelled, ledd absent: it must reach the antecedent, so the grammar
    # returns an empty ledd rather than declining. 43 corpus refusals take this
    # route and every one of them ends up refused typed.
    assert _no_punktum_repeal_targets("§ 16 annet punktum oppheves.") == ("16", "", [2])
    # Both inherited. The lead is a bare sentence; the antecedent carries it.
    assert _no_punktum_repeal_targets("Annet punktum oppheves.") == ("", "", [2])
    # A currency qualifier in front of the ordinal is absorbed by the SHIPPED
    # ordinal vocabulary (``_no_strip_ledd_shift_newness``), not by a second
    # alternation of this grammar's own.
    assert _no_punktum_repeal_targets("Nåværende tredje punktum oppheves.") == ("", "", [3])
    # Plural and range target lists, both through ``_no_ledd_shift_ordinals``.
    assert _no_punktum_repeal_targets("§ 27 tredje og fjerde punktum oppheves.") == (
        "27",
        "",
        [3, 4],
    )
    assert _no_punktum_repeal_targets(
        "§ 10-34 annet ledd femte til syvende punktum oppheves."
    ) == ("10-34", "2", [5, 6, 7])
    # Hyphenated and letter-suffixed section labels, normalized by the shipped
    # helper exactly as the relabel's are.
    assert _no_punktum_repeal_targets("§ 19-1 tredje ledd første punktum oppheves.") == (
        "19-1",
        "3",
        [1],
    )
    assert _no_punktum_repeal_targets("§ 38b annet ledd fjerde og femte punktum oppheves.") == (
        "38b",
        "2",
        [4, 5],
    )


def test_no_w66c_punktum_repeal_grammar_refuses_what_it_must() -> None:
    """W-66c: the corpus leads this grammar declines, one limb each.

    A production that DESTROYS TEXT is drawn tighter than its relabel sibling,
    and every limb below is paid for in leads that keep their shipped refusal.
    """
    # THE VERB IS ``oppheves`` ALONE — the shipped ledd-depth repeal lane's own
    # anchor. 24 refusals / 24 leads / 15 base acts spell the nynorsk forms and
    # stay refused. Widening the verb of a destroying production is a separate
    # decision from founding it.
    assert _no_punktum_repeal_targets("§ 3-2 andre punktum blir oppheva.") is None
    assert _no_punktum_repeal_targets("§ 12-12 andre ledd tredje punktum skal opphevast.") is None
    assert _no_punktum_repeal_targets("§ 32 første ledd andre punktum opphevast.") is None
    # THE SENTENCE MUST END AT THE VERB. Every run-on carries a second
    # instruction this grammar does not read, and lowering only the destroying
    # half would leave the statute mis-numbered.
    assert (
        _no_punktum_repeal_targets(
            "§ 8-7 første ledd annet punktum oppheves. Nåværende tredje punktum blir annet punktum."
        )
        is None
    )
    # ``siste`` IS an address the apply plane can resolve (``sentence/last``),
    # and it declines here anyway: "the last sentence" is a count of what is
    # standing, and a repeal that destroys by counting is the one shape this item
    # must not take on trust.
    assert _no_punktum_repeal_targets("§ 20 første ledd siste punktum oppheves.") is None
    # ``bokstav``/``nr.`` sub-containers between the ledd and the punktum decline
    # at the ordinal vocabulary — the residue is not a list of ordinals, and
    # lowering them needs an address level this production does not model.
    assert _no_punktum_repeal_targets("§ 5 b første ledd nr. 3 annet punktum oppheves.") is None
    assert _no_punktum_repeal_targets("§ 3-13 nr. 2 bokstav f siste punktum oppheves.") is None
    assert _no_punktum_repeal_targets("§ 10-6 nr. 1 første punktum oppheves.") is None
    # A MULTI-ADDRESS repeal list names two ledds; the residue does not reduce.
    assert (
        _no_punktum_repeal_targets(
            "§ 58 første ledd annet punktum og tredje ledd første punktum oppheves."
        )
        is None
    )
    # The section-list repeal that merely CONTAINS a punktum item is not this
    # family: it does not end at ``punktum oppheves``.
    assert (
        _no_punktum_repeal_targets(
            "§ 27 annet ledd tredje punktum, §§ 34 til 38, § 59 og § 59 a oppheves."
        )
        is None
    )
    # The cross-act inverted form ("I lov … oppheves § X … punktum.") puts the
    # verb before the address and is a different family.
    assert (
        _no_punktum_repeal_targets(
            "2. I lov 29. november 1996 nr. 72 om petroleumsvirksomhet oppheves "
            "§ 11-3 annet ledd annet punktum."
        )
        is None
    )
    # A repeated ordinal would mint two REPEALs at one address, the second of
    # which destroys whatever the relabel arithmetic has since moved in.
    assert _no_punktum_repeal_targets("§ 7 annet og annet punktum oppheves.") is None
    # An ordinal outside ``_NORWEGIAN_ORDINALS`` declines, one ordinal grammar.
    assert _no_punktum_repeal_targets("§ 7 sjuande punktum oppheves.") is None


def test_no_w66c_punktum_repeal_leaves_the_shipped_lanes_alone() -> None:
    """W-66c is strictly ADDITIVE, and the block's POSITION is the proof.

    The repeal block sits LAST in the unstructured walk, immediately ahead of the
    operative fallback, so a lead only reaches it once every shipped family has
    declined. Two of those families are close enough to be worth pinning from
    both sides: the shipped ledd-depth repeal, whose anchor is ``ledd
    oppheves``, and W-66b's punktum relabel, whose anchor is ``punktum.``.
    """
    # The shipped ledd-depth repeal's own lead is not a punktum repeal.
    assert _no_punktum_repeal_targets("§ 8-2 første ledd oppheves.") is None
    # W-66b's relabel lead is not a repeal, and this grammar's own lead is not a
    # relabel — the two are disjoint by their tails, in both directions.
    assert _no_punktum_repeal_targets("Nåværende annet punktum blir nytt tredje punktum.") is None
    assert _no_punktum_set_relabel_pairs("§ 20 første ledd annet punktum oppheves.") is None
    # The section-level repeal lanes are untouched.
    assert _no_punktum_repeal_targets("§ 20 oppheves.") is None
    assert _no_punktum_repeal_targets("§§ 10 og 11 oppheves.") is None


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w66c_punktum_repeal_lowers_on_the_corpus_witness() -> None:
    """W-66c corpus witness, parse plane: ``no/lovtid/2022-06-10-38``.

    The instrument commands exactly two instructions on ``no/lov/2021-06-18-121``
    § 20 første ledd, in two ``defaultP`` nodes:

        § 20 første ledd annet punktum oppheves.
        Nåværende tredje punktum blir annet punktum.

    W-66b lowered the second and left the first refused, which is why its relabel
    leg then refused at apply. Both now lower, and the pair is pinned here as a
    pair — a repeal at ``setning/2`` and a relabel from ``setning/3`` INTO the
    slot that repeal vacates.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2022-06-10-38", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2022-06-10-38", adjudications_out=adjudications
        )
    )
    ops = grouped["no/lov/2021-06-18-121"]

    assert [
        (
            str(op.action.value),
            op.target.path,
            None if op.destination is None else op.destination.path,
            None if op.source is None else op.source.raw_text,
        )
        for op in ops
    ] == [
        (
            "repeal",
            (("section", "20"), ("subsection", "1"), ("sentence", "2")),
            None,
            "§ 20 første ledd annet punktum oppheves.",
        ),
        (
            "renumber",
            (("section", "20"), ("subsection", "1"), ("sentence", "3")),
            (("section", "20"), ("subsection", "1"), ("sentence", "2")),
            "Nåværende tredje punktum blir annet punktum.",
        ),
    ]
    # The repeal mirrors the SHIPPED ledd-depth repeal lane's op shape exactly:
    # no destination, no relabel provenance tag, no witness rule id. A repeal has
    # no destination for the occupied-destination guard to key on, so a tag whose
    # only purpose was this item's own bookkeeping would be dead weight on a
    # load-bearing safety seam.
    repeal = ops[0]
    assert repeal.destination is None
    assert repeal.witness_rule_id is None
    assert set(repeal.provenance_tags or ()) == {
        "base_act:no/lov/2021-06-18-121",
        "fallback:unstructured",
    }
    assert "§ 20 første ledd annet punktum oppheves." not in {
        (item.detail or {}).get("source_excerpt")
        for item in adjudications
        if item.kind == "no_parse_unstructured_lead_unmatched"
    }


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w66c_unresolvable_ledd_gets_a_typed_receipt_not_a_guess() -> None:
    """W-66c: 43 corpus refusals resolve their SECTION but not their LEDD.

    A punktum hanging directly under a section ("§ 16 annet punktum oppheves.")
    has no ledd to inherit, and the apply plane's shallow-sentence-host rebinding
    would in fact resolve such an address. This production does not use it: a
    guess about WHICH container holds the sentences is a guess about which
    sentence gets destroyed. The receipt kind is W-66b's, REUSED — the same
    reader failing the same way — and the ``production`` detail key is what tells
    a repeal refusal from a relabel one in a census.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2009-06-19-74", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2009-06-19-74", adjudications_out=adjudications
        )
    )
    typed = [
        item
        for item in adjudications
        if item.kind == NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED
        and (item.detail or {}).get("production") == "punktum_repeal"
    ]
    assert typed, "the punktum-repeal ledd receipt is missing"
    assert {(item.detail or {}).get("section") for item in typed} >= {"4", "5", "6", "7"}
    assert {(item.detail or {}).get("ledd_reason") for item in typed} <= {
        "antecedent_names_no_ledd",
        "antecedent_is_not_punktum_depth",
        "antecedent_names_several_ledd",
        "part_has_no_antecedent_lead",
        "antecedent_is_meta_amendment",
    }
    # Nothing was minted for any of them — not at a guessed ledd, not anywhere.
    # Keyed on the refused LEAD rather than on its section label, because a
    # section number refused against one base act is routinely a live section of
    # another act the same omnibus instrument amends.
    refused_leads = {(item.detail or {}).get("source_excerpt") for item in typed}
    assert not [
        op
        for base_ops in grouped.values()
        for op in base_ops
        if op.source is not None and op.source.raw_text in refused_leads
    ]


def _w66c_repeal_op(sequence: int, section: str, ledd: str, sentence: int) -> LegalOperation:
    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.REPEAL,
        target=LegalAddress(
            path=(("section", section), ("subsection", ledd), ("sentence", str(sentence)))
        ),
        source=OperationSource(
            statute_id="no/lovtid/9999-01-01-1", raw_text="punktum repeal", title="x"
        ),
        provenance_tags=("base_act:no/lov/1999-01-01-1", "fallback:unstructured"),
        group_id=f"no/lovtid/9999-01-01-1:{sequence}",
    )


def test_no_w66c_punktum_repeal_materializes_its_parent_then_removes_one_sentence() -> None:
    """W-66c apply: the ordinary case, and the W-69b dependency it shares.

    The parent ledd is a single text node, so ``setning/2`` does not resolve
    until W-69b's ``_materialize_sentence_parent_for`` has split it. The REPEAL
    branch is then the shipped ``tree_ops.remove_at`` and is depth-agnostic: ZERO
    apply-plane edits were needed for this item.

    What is asserted is the DESTRUCTION, by text: sentence two is gone and the
    other two are byte-identical. A repeal that trimmed a neighbour would pass a
    label-only assertion.
    """
    before = _w66b_statute("Setning en. Setning to. Setning tre.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, [_w66c_repeal_op(1, "7", "4", 2)], adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert [(child.label, child.text) for child in ledd.children] == [
        ("1", "Setning en."),
        ("3", "Setning tre."),
    ]
    materialized = [
        a for a in adjudications if a.kind == "no_replay_sentence_children_materialized"
    ]
    assert [(a.detail or {}).get("materialized_sentence_count") for a in materialized] == [3]


def test_no_w66c_repeal_vacates_the_slot_the_relabel_needs() -> None:
    """W-66c: the interplay, and the ORDERING that makes it hold.

    This is the corpus witness's shape in one statute: repeal sentence two, then
    relabel sentence three into slot two. The ops are handed to the apply lane in
    the WRONG order on purpose — the relabel first — because the ordering that
    makes the pair work is not the order they were minted in.

    ``no_ordering_profile``'s structural-vacate stage runs every REPEAL in a
    group before every RENUMBER in it, and ``_no_group_key`` is ``(effective,
    enacted, source_id)`` — so a repeal and a relabel from ONE instrument at ONE
    moment are always in one group and the repeal always runs first. Without it
    the relabel would find slot two occupied and refuse under W-66's guard, which
    is exactly what the corpus did before this item.
    """
    before = _w66b_statute("Setning en. Setning to. Setning tre.")
    ops = [_w66b_relabel_op(1, "7", "4", 3, 2), _w66c_repeal_op(2, "7", "4", 2)]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert [(child.label, child.text) for child in ledd.children] == [
        ("1", "Setning en."),
        ("2", "Setning tre."),
    ]
    # The guard did not fire, and neither did the θ cell it stands in front of.
    assert not [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


def test_no_w66c_relabel_still_refuses_when_no_repeal_vacates_the_slot() -> None:
    """W-66c does NOT weaken W-66's guard: the refusal is still there for the
    relabel that has no companion repeal.

    Same statute, same relabel, no repeal. Slot two is live text the relabel does
    not move, so the leg refuses and the ledd comes out untouched — down to the
    shape, the read-only materialization rolled back with the refused op. This is
    the state the corpus witness was in at the W-66b landing, and it must stay
    reachable, because the only thing that changed it there was a repeal proving
    its own address.
    """
    before = _w66b_statute("Setning en. Setning to. Setning tre.")
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        before, [_w66b_relabel_op(1, "7", "4", 3, 2)], adjudications_out=adjudications
    )

    ledd = result.body.children[0].children[0]
    assert ledd.children == ()
    assert ledd.text == "Setning en. Setning to. Setning tre."
    refusals = [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert [(a.detail or {}).get("destination_path") for a in refusals] == [
        "section:7/subsection:4/sentence:2"
    ]


def test_no_w66c_plural_repeal_legs_are_order_independent() -> None:
    """W-66c: a plural repeal names two sentences, and neither order can go wrong.

    ``tree_ops.remove_at`` removes a node without relabelling its siblings, so
    ``setning/2`` still means the same sentence after ``setning/3`` is gone. The
    production emits DESCENDING anyway; both orders are pinned here so that a
    future sibling-compaction cannot make the emission order load-bearing in
    silence.
    """
    for ordinals in ((3, 2), (2, 3)):
        before = _w66b_statute("Setning en. Setning to. Setning tre. Setning fire.")
        ops = [
            _w66c_repeal_op(i, "7", "4", ordinal) for i, ordinal in enumerate(ordinals, start=1)
        ]
        result = apply_no_ops(before, ops, adjudications_out=[])
        ledd = result.body.children[0].children[0]
        assert [(child.label, child.text) for child in ledd.children] == [
            ("1", "Setning en."),
            ("4", "Setning fire."),
        ], ordinals


# ── W-69c: the atomic ordering generalized to (parent_path, label) ────────────
#
# W-66's machinery orders a relabel over integer ORDINALS inside ONE sibling set.
# The structured ``data-move-part`` lane mints legs that LEAVE their container,
# so a relocation belongs to two sibling sets and the leg that frees its
# destination lives in the other one. These four tests fix the generalization at
# the apply plane, which is where the legs actually meet: the two colliding legs
# on ``no/lov/2009-06-19-44`` come from two DIFFERENT ``data-move-part``
# attributes, so no parse-plane production can see both.
#
# Note what these ops do NOT carry: ``NO_LEDD_SET_RELABEL_PROVENANCE_TAG``. The
# structured lane stamps only ``base_act:``, so W-66's refusal cannot fire on
# them and the guard under test is reached on its own terms.


def _w69c_move_op(
    sequence: int, source: tuple[str, str], destination: tuple[str, str]
) -> LegalOperation:
    """A structured-lane relocation leg, ``(§, ledd)`` to ``(§, ledd)``."""
    return LegalOperation(
        op_id=f"no/lovtid/9999-02-02-2:{sequence}",
        sequence=sequence,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=(("section", source[0]), ("subsection", source[1]))),
        destination=LegalAddress(
            path=(("section", destination[0]), ("subsection", destination[1]))
        ),
        source=OperationSource(statute_id="no/lovtid/9999-02-02-2", raw_text="move", title="x"),
        provenance_tags=("base_act:no/lov/1999-01-01-1",),
        group_id=f"no/lovtid/9999-02-02-2:{sequence}",
        witness_rule_id="no_section_renumber_relabel",
    )


def _w69c_statute(sections: dict[str, int]) -> IRStatute:
    """A statute of ``{section label: ledd count}``, each ledd labelled by text."""
    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=tuple(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label=label,
                    children=tuple(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label=str(i),
                            text=f"§{label} ledd {i}",
                        )
                        for i in range(1, count + 1)
                    ),
                )
                for label, count in sections.items()
            ),
        ),
    )


def _w69c_shape(body: IRNode) -> dict[str, list[tuple[str, str]]]:
    return {
        section.label or "": [(child.label or "", child.text or "") for child in section.children]
        for section in body.children
    }


def test_no_w69c_cross_container_in_migration_lands_after_its_vacate() -> None:
    """The SATISFIABLE cross-container shape, and it must keep working unchanged.

    ``§3/ledd/3 → §2/ledd/4`` is a genuine relocation (the apply plane resolves
    ``op.destination.parent()`` and re-parents the node), and its destination is
    freed by ``§2/ledd/4 → §2/ledd/5`` living in the OTHER sibling set. There is
    an order in which no leg writes onto a live sibling, so the component is
    provable and both legs land — vacate first, occupy second. W-69c adds a
    provability TEST, not a reordering; this is the witness that it does not
    disturb the case the kernel already gets right.
    """
    ops = [
        _w69c_move_op(1, ("2", "4"), ("2", "5")),
        _w69c_move_op(2, ("3", "3"), ("2", "4")),
    ]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(_w69c_statute({"2": 4, "3": 3}), ops, adjudications_out=adjudications)
    assert _w69c_shape(result.body) == {
        "2": [
            ("1", "§2 ledd 1"),
            ("2", "§2 ledd 2"),
            ("3", "§2 ledd 3"),
            # the in-migrated node, carrying its ORIGINAL text under its new label
            ("4", "§3 ledd 3"),
            ("5", "§2 ledd 4"),
        ],
        "3": [("1", "§3 ledd 1"), ("2", "§3 ledd 2")],
    }
    assert not [
        a for a in adjudications if a.kind == "no_replay_relocation_order_unprovable_refused"
    ]
    # Nothing was written onto a live sibling, so the θ recovery never ran.
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


def test_no_w69c_contested_destination_refuses_the_whole_component() -> None:
    """``no/lov/2009-06-19-44`` in miniature: two legs claim ONE destination.

    The law's own shape, reduced. ``§2/ledd/3 → §2/ledd/4`` is the destination
    parent's own vacate shift; ``§3/ledd/3 → §2/ledd/4`` is a cross-container
    in-migration minted by a DIFFERENT ``data-move-part`` attribute of the same
    instrument. Both name ``§2/ledd/4``. No permutation of these legs exists in
    which the second does not land on the first — which is why the kernel's
    structural-vacate stage cannot help: a topological sort's only possible
    answer is a permutation. At HEAD the second leg wrote a duplicate label and
    the tree invariant aborted the whole law's apply, discarding its receipts and
    its adjudications with it.

    The component drops WHOLE — including ``§2/ledd/4 → §2/ledd/5``, which is
    provable on its own but shares a node with the contested pair. Refusing a leg
    out of the middle of a shift chain would leave the chain half-applied, which
    is the W-56 failure mode; and choosing which of two contradictory
    instructions to honour would be a semantics change on landed ops (W-70).
    """
    ops = [
        _w69c_move_op(1, ("2", "4"), ("2", "5")),
        _w69c_move_op(2, ("2", "3"), ("2", "4")),
        _w69c_move_op(3, ("3", "3"), ("2", "4")),
    ]
    before = _w69c_statute({"2": 4, "3": 3})
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)
    # Nothing half-applied: the tree is identical to the pre-op statute.
    assert _w69c_shape(result.body) == _w69c_shape(before.body)
    refusals = [
        a for a in adjudications if a.kind == "no_replay_relocation_order_unprovable_refused"
    ]
    assert sorted((a.detail or {}).get("source_path") for a in refusals) == [
        "section:2/subsection:3",
        "section:2/subsection:4",
        "section:3/subsection:3",
    ]
    assert all(a.blocking for a in refusals)
    # Under-application, never over-application: the θ recovery that would have
    # DELETED an occupant to make room never ran.
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


def test_no_w69c_cross_container_cycle_refuses_at_the_new_keying() -> None:
    """W-66's cycle guard, unchanged, lifted to ``(parent_path, label)``.

    A pure swap across containers — ``§2/ledd/1 → §3/ledd/1`` with
    ``§3/ledd/1 → §2/ledd/1``. Sequential relabelling cannot express a swap
    without a scratch slot, so no order exists and both legs refuse. W-66's guard
    could not see this one at all: its dependency nodes are integer ordinals
    inside one sibling set, and these two legs are in different sections.
    """
    ops = [
        _w69c_move_op(1, ("2", "1"), ("3", "1")),
        _w69c_move_op(2, ("3", "1"), ("2", "1")),
    ]
    before = _w69c_statute({"2": 2, "3": 2})
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)
    assert _w69c_shape(result.body) == _w69c_shape(before.body)
    refusals = [
        a for a in adjudications if a.kind == "no_replay_relocation_order_unprovable_refused"
    ]
    assert sorted((a.detail or {}).get("source_path") for a in refusals) == [
        "section:2/subsection:1",
        "section:3/subsection:1",
    ]


def test_no_w69c_an_unprovable_component_does_not_take_its_neighbours_down() -> None:
    """The refusal unit is the COMPONENT, not the affecting-act group.

    Legs that address disjoint sets of ``(parent_path, label)`` nodes cannot
    interfere, so a contested destination in §2 says nothing about a shift in §7.
    Refusing the whole group would be under-application with no argument behind
    it; this pins that the guard does not do that.
    """
    ops = [
        _w69c_move_op(1, ("2", "3"), ("2", "4")),
        _w69c_move_op(2, ("3", "3"), ("2", "4")),
        _w69c_move_op(3, ("7", "2"), ("7", "3")),
    ]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(
        _w69c_statute({"2": 3, "3": 3, "7": 2}), ops, adjudications_out=adjudications
    )
    shape = _w69c_shape(result.body)
    assert shape["2"] == [("1", "§2 ledd 1"), ("2", "§2 ledd 2"), ("3", "§2 ledd 3")]
    assert shape["3"] == [("1", "§3 ledd 1"), ("2", "§3 ledd 2"), ("3", "§3 ledd 3")]
    # The independent component landed.
    assert shape["7"] == [("1", "§7 ledd 1"), ("3", "§7 ledd 2")]
    refusals = [
        a for a in adjudications if a.kind == "no_replay_relocation_order_unprovable_refused"
    ]
    assert sorted((a.detail or {}).get("source_path") for a in refusals) == [
        "section:2/subsection:3",
        "section:3/subsection:3",
    ]


def test_no_w69c_a_leg_announced_twice_is_one_instruction_not_a_contest() -> None:
    """A repeated leg must NOT be read as two legs contesting a slot.

    Two corpus groups announce one move twice — ``no/lov/1999-03-26-14``
    (``§10-65/ledd/2 → ledd/3``, from ``no/lovtid/2013-12-13-117``) and
    ``no/lov/2017-06-16-53`` (``§30/ledd/2 → ledd/3``, from
    ``no/lovtid/2018-06-15-38``). Identical source AND destination is ONE
    instruction: it is satisfied by applying it once, and the shipped ordering
    stage already treats it that way — ``_ordered_renumber_group``'s DFS is keyed
    on ``op.target.path``, so the second copy is collapsed into the first and a
    single leg reaches the fold.

    Without deduplication the guard reads the repeat as a contested destination
    AND a contested source and refuses a perfectly good move — under-application
    with nothing behind it. Neither group reaches the apply seam at
    ``as_of=2026-07-10`` (one law has no original-act source, the other applies
    no ops), so this would have been a LATENT wrong answer with no corpus blast
    to reveal it; it is pinned here instead.
    """
    ops = [
        _w69c_move_op(1, ("2", "2"), ("2", "3")),
        _w69c_move_op(2, ("2", "2"), ("2", "3")),
    ]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(_w69c_statute({"2": 2}), ops, adjudications_out=adjudications)
    assert not [
        a for a in adjudications if a.kind == "no_replay_relocation_order_unprovable_refused"
    ]
    # The move landed exactly once, and nothing was written onto a live sibling.
    assert _w69c_shape(result.body)["2"] == [("1", "§2 ledd 1"), ("3", "§2 ledd 2")]
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


# ── W-76: the sibling-set relabel at ITEM depth (bokstav / nr.) ───────────────


def test_no_w76_item_relabel_grammar_accepts_the_corpus_shapes() -> None:
    """W-76: every shape the 28 lowering occurrences actually take.

    The return is ``(section, depth, pairs)``. ``depth`` names WHICH of the two
    patterns matched — it selects the label vocabulary AND the antecedent's depth
    conjunct — and the pairs are LABEL INDEXES, because W-66's topological sort is
    the one ordering implementation in this module and it orders integers.
    """
    # The dominant shape: no section spelled, one leg, newness on the destination.
    assert _no_item_set_relabel_pairs("Nåværende bokstav b blir ny bokstav c.") == (
        "",
        "bokstav",
        [(2, 3)],
    )
    assert _no_item_set_relabel_pairs("Nåværende nr. 2 blir ny nr. 3.") == ("", "nr", [(2, 3)])
    # A pair relabel with OVERLAPPING source and destination sets — the population
    # this production's ordering argument exists for.
    assert _no_item_set_relabel_pairs("Nåværende bokstav g og h blir bokstav h og i.") == (
        "",
        "bokstav",
        [(7, 8), (8, 9)],
    )
    # The currency qualifier is W-61's measured set, and it may sit on either side
    # of the ``§`` — both word orders are attested at this depth too.
    assert _no_item_set_relabel_pairs("Gjeldande nr. 3 blir nr. 2.") == ("", "nr", [(3, 2)])
    assert _no_item_set_relabel_pairs("Noverande bokstav d blir ny bokstav e.") == (
        "",
        "bokstav",
        [(4, 5)],
    )
    assert _no_item_set_relabel_pairs("Nåværende § 3-1 bokstav b blir ny bokstav c.") == (
        "3-1",
        "bokstav",
        [(2, 3)],
    )
    assert _no_item_set_relabel_pairs("§ 14 noverande nr. 2 og nr. 3 blir nr. 1 og nr. 2.") == (
        "14",
        "nr",
        [(2, 1), (3, 2)],
    )
    # The plural depth word, bokmål and nynorsk.
    assert _no_item_set_relabel_pairs("Nåværende bokstavene f og g blir bokstavene g og h.") == (
        "",
        "bokstav",
        [(6, 7), (7, 8)],
    )
    # ``til`` ranges EXPAND. Four legs from six words, and the arithmetic is the
    # letter alphabet's position rather than a count of what is standing.
    assert _no_item_set_relabel_pairs("Nåværende bokstav b til e blir bokstav c til f.") == (
        "",
        "bokstav",
        [(2, 3), (3, 4), (4, 5), (5, 6)],
    )
    assert _no_item_set_relabel_pairs("Nåværende nr. 1 til 3 blir nye nr. 2 til 4.") == (
        "",
        "nr",
        [(1, 2), (2, 3), (3, 4)],
    )
    # A comma list, and a DECREASING relabel — not special-cased anywhere.
    assert _no_item_set_relabel_pairs("Nåværende bokstav e, f og g blir bokstav d, e og f.") == (
        "",
        "bokstav",
        [(5, 4), (6, 5), (7, 6)],
    )
    assert _no_item_set_relabel_pairs(
        "§ 41 nåværende nr. 30, 31, 32 og 33 blir nr. 31, 32, 33 og 34."
    ) == ("41", "nr", [(30, 31), (31, 32), (32, 33), (33, 34)])
    # The depth word RESTATED inside a list, which only ``nr.`` does.
    assert _no_item_set_relabel_pairs("§ 4-7 nåværende nr. 8 til nr. 10 blir nr. 6 til nr. 8.") == (
        "4-7",
        "nr",
        [(8, 6), (9, 7), (10, 8)],
    )
    # ``nye`` on a plural destination, and a hyphenated section label.
    assert _no_item_set_relabel_pairs("Nåværende bokstav e og f blir nye bokstav f og g.") == (
        "",
        "bokstav",
        [(5, 6), (6, 7)],
    )
    assert _no_item_set_relabel_pairs("Gjeldande § 9-2 nr. 9 blir ny nr. 8.") == (
        "9-2",
        "nr",
        [(9, 8)],
    )


def test_no_w76_item_relabel_grammar_refuses_what_it_must() -> None:
    """W-76: one assertion per deliberately-refused limb of the block comment."""
    # A SPELLED LEDD. The sized shape's source side reduces to labels alone, so
    # the larger sentence declines whole rather than being half-read. 26 of the
    # 58 declined qualifier-headed neighbourhood refusals are of this family.
    assert (
        _no_item_set_relabel_pairs("Nåværende § 18-3 sjette ledd bokstav b blir ny bokstav c.")
        is None
    )
    assert (
        _no_item_set_relabel_pairs(
            "Nåværende første ledd nr. 2 til 6 blir nye første ledd nr. 3 til 7."
        )
        is None
    )
    # NEWNESS INSIDE A LIST is an insertion this production does not model.
    assert (
        _no_item_set_relabel_pairs("Nåværende bokstav j og k blir bokstav k og ny bokstav l.") is None
    )
    assert _no_item_set_relabel_pairs("Nåværende nr. 8 og nr. 9 blir nr. 9 og ny nr. 10.") is None
    # A destination that DROPS the depth word is not this sentence.
    assert _no_item_set_relabel_pairs("Nåværende bokstav c, d og e blir d, e og f.") is None
    # The currency qualifier is REQUIRED, for W-66's reason: a sentence that does
    # not say which edition its labels are read against cannot be read against the
    # pre-operation snapshot, which is this production's premise.
    assert _no_item_set_relabel_pairs("Bokstav b blir ny bokstav c.") is None
    # Anchored end to end: a payload tail, a run-on, and ``blir til``.
    assert (
        _no_item_set_relabel_pairs("Nåværende nr. 6 blir nr. 7 og skal lyde: Universitetene …") is None
    )
    assert (
        _no_item_set_relabel_pairs("Gjeldande § 9-2 nr. 8 blir ny nr. 7. Første punktum skal lyde:")
        is None
    )
    assert (
        _no_item_set_relabel_pairs("§ 18 a nåværende bokstav f til i blir til nye bokstav g til j.")
        is None
    )
    # A COUNTED address — the one shape a production that expands ranges must not
    # take on trust.
    assert _no_item_set_relabel_pairs("Nåværende siste bokstav blir ny bokstav l.") is None
    # Letters outside ``a``–``z``: their position relative to ``z`` in Lovdata's
    # lettering is unproven, so a range crossing it would be a guess.
    assert _no_item_set_relabel_pairs("Nåværende bokstav ø blir ny bokstav å.") is None
    # A SPELLED-OUT numeral is not the arabic vocabulary.
    assert _no_item_set_relabel_pairs("Gjeldande nr. tre blir nr. fire.") is None
    # Degenerate pair sets, refused exactly as W-66 and W-66b refuse them.
    assert _no_item_set_relabel_pairs("Nåværende bokstav c blir bokstav c.") is None
    assert _no_item_set_relabel_pairs("Nåværende bokstav c og d blir bokstav e.") is None
    assert _no_item_set_relabel_pairs("Nåværende bokstav c og c blir bokstav d og e.") is None
    # A descending range names nothing.
    assert _no_item_set_relabel_pairs("Nåværende bokstav e til b blir bokstav f til c.") is None


def test_no_w76_item_label_vocabulary_expands_rather_than_counts() -> None:
    """W-76: the label vocabulary, in isolation, both directions.

    Indexes are 1-based inside their own alphabet so a letter relabel and a
    numeral relabel present the SAME shape to W-66's topological sort. The round
    trip is asserted because the emitted op path is built from it.
    """
    assert _no_item_relabel_indexes("bokstav", "b til e") == [2, 3, 4, 5]
    assert _no_item_relabel_indexes("bokstav", "g, h og i") == [7, 8, 9]
    assert _no_item_relabel_indexes("nr", "8 til nr. 10") == [8, 9, 10]
    assert _no_item_relabel_indexes("nr", "30, 31, 32 og 33") == [30, 31, 32, 33]
    # A range is ENUMERATED, so a single-member range is a single member.
    assert _no_item_relabel_indexes("bokstav", "c til c") == [3]
    # Nothing this vocabulary cannot name is guessed at.
    assert _no_item_relabel_indexes("bokstav", "æ") is None
    assert _no_item_relabel_indexes("bokstav", "aa") is None
    assert _no_item_relabel_indexes("bokstav", "siste") is None
    assert _no_item_relabel_indexes("nr", "tre") is None
    assert _no_item_relabel_indexes("bokstav", "e til b") is None
    assert [_no_item_relabel_label("bokstav", i) for i in (1, 2, 26)] == ["a", "b", "z"]
    assert [_no_item_relabel_label("nr", i) for i in (1, 10, 33)] == ["1", "10", "33"]


def test_no_w76_item_relabel_ordering_is_w66s_sort_over_label_indexes() -> None:
    """W-76: the vacate-before-occupy order, on the corpus's own worst case.

    "Nåværende bokstav b til e blir bokstav c til f." overlaps its source and
    destination sets three ways. Read in source order it writes onto a live
    sibling three times; ordered, it never does. That the sort is W-66's own
    helper — not a second implementation — is the point of carrying label INDEXES
    through the grammar.
    """
    parsed = _no_item_set_relabel_pairs("Nåværende bokstav b til e blir bokstav c til f.")
    assert parsed is not None
    _section, depth, pairs = parsed
    ordered = _no_ordered_set_relabel_pairs(pairs)
    assert ordered is not None
    assert [
        (_no_item_relabel_label(depth, src), _no_item_relabel_label(depth, dst))
        for src, dst in ordered
    ] == [("e", "f"), ("d", "e"), ("c", "d"), ("b", "c")]
    # A swap has no order at this depth either, and the whole lead is refused.
    assert _no_ordered_set_relabel_pairs([(3, 4), (4, 3)]) is None


def test_no_w76_item_grammar_leaves_the_shipped_lanes_alone() -> None:
    """W-76 is strictly ADDITIVE, and its POSITION in the walk is the proof.

    The block sits LAST, behind W-66c and immediately ahead of the operative
    fallback, so a lead only reaches it once every shipped family has declined.
    The tail anchors say the same thing independently and are pinned here from
    BOTH sides: every shipped relabel and repeal grammar in this module anchors on
    ``ledd`` or ``punktum``, and this one on a bare label.
    """
    ledd_sentence = "Nåværende femte og sjette ledd blir sjette og sjuende ledd."
    punktum_sentence = "Nåværende annet punktum blir nytt tredje punktum."
    repeal_sentence = "§ 20 første ledd annet punktum oppheves."
    bokstav_sentence = "Nåværende bokstav b blir ny bokstav c."
    nr_sentence = "Nåværende nr. 2 blir ny nr. 3."
    for shipped in (ledd_sentence, punktum_sentence, repeal_sentence):
        assert _no_item_set_relabel_pairs(shipped) is None
    for mine in (bokstav_sentence, nr_sentence):
        assert _no_ledd_set_relabel_pairs(mine) is None
        assert _no_punktum_set_relabel_pairs(mine) is None
        assert _no_punktum_repeal_targets(mine) is None
    # The two item patterns are mutually exclusive by their depth words, so the
    # iteration order over them is immaterial rather than load-bearing.
    bokstav_parsed = _no_item_set_relabel_pairs(bokstav_sentence)
    nr_parsed = _no_item_set_relabel_pairs(nr_sentence)
    assert bokstav_parsed is not None and bokstav_parsed[1] == "bokstav"
    assert nr_parsed is not None and nr_parsed[1] == "nr"


def test_no_w76_shared_relabel_head_is_byte_identical_to_what_it_replaced() -> None:
    """W-76: naming the shared sentence head changed no pattern's TEXT.

    Three sibling-set relabel grammars now build on
    ``_NO_SET_RELABEL_QUALIFIED_SECTION_HEAD`` instead of spelling the required-
    qualifier / optional-``§`` head out. That is the rule-of-three extraction the
    FW-08 ``clause_boundary_dup`` sensor asks for, and an extraction is only free
    if the resulting patterns are the same STRING they were — which is what this
    pins, by rebuilding the head from its own two vocabularies.
    """
    from lawvm.norway.grafter import (
        _NO_CURRENCY_QUALIFIER_ALTERNATION,
        _NO_SET_RELABEL_PUNKTUM_PATTERN,
        _NO_SET_RELABEL_QUALIFIED_SECTION_HEAD,
        _NO_SET_RELABEL_SECTION_LABEL,
        _NO_SET_RELABEL_WIDENED_PATTERN,
    )

    head = (
        r"^(?:(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+"
        r"(?:§\s*(?P<qualifier_first_section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+)?"
        r"|§\s*(?P<section_first_section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+"
        r"(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+)"
    )
    assert _NO_SET_RELABEL_QUALIFIED_SECTION_HEAD == head
    assert _NO_SET_RELABEL_WIDENED_PATTERN == (
        head + r"(?P<source>.+?)\s+ledd\s+blir\s+(?P<destination>.+?)\s+ledd\.?$"
    )
    assert _NO_SET_RELABEL_PUNKTUM_PATTERN == (
        head + r"(?P<source>.+?)\s+punktum\s+blir\s+(?P<destination>.+?)\s+punktum\.?$"
    )
    # And the two item patterns are the same head plus their own depth word.
    from lawvm.norway.grafter import _NO_SET_RELABEL_ITEM_PATTERNS

    assert set(_NO_SET_RELABEL_ITEM_PATTERNS) == {"bokstav", "nr"}
    assert all(p.startswith(head) for p in _NO_SET_RELABEL_ITEM_PATTERNS.values())


def test_no_w76_item_ledd_inheritance_retargets_the_depth_conjunct() -> None:
    """W-76: ONE antecedent reader, one depth word swapped.

    Everything about ``_no_antecedent_ledd_label`` is depth-independent except the
    conjunct that says "this antecedent is talking at MY depth", so W-76 retargets
    that conjunct rather than forking the reader. The defaults are W-66b's, which
    is what keeps every shipped call site byte-identical.
    """
    bokstav_shift = '<article class="defaultP">Nåværende bokstav b blir ny bokstav c.</article>'
    nr_shift = '<article class="defaultP">Nåværende nr. 2 blir ny nr. 3.</article>'
    bokstav_markers = ("bokstav",)
    nr_markers = ("nr.", "nr ", "nummer")
    # The dominant corpus shape: the antecedent is an item-depth instruction on
    # the same ledd, and it donates that ledd.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 9 første ledd ny bokstav b skal lyde:</article>',
            bokstav_shift,
        ),
        [0, 0],
        1,
        depth_name="item",
        depth_markers=bokstav_markers,
    ) == ("1", "antecedent_names_ledd")
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 1-2 første ledd nr. 11 skal lyde: stiftelser,</article>',
            nr_shift,
        ),
        [0, 0],
        1,
        depth_name="item",
        depth_markers=nr_markers,
    ) == ("1", "antecedent_names_ledd")
    # 22 corpus refusals, every one of them this reason: an item hanging directly
    # under a section, which is the older acts' shape ("§ 24 nr. 2 oppheves.").
    assert _no_antecedent_ledd_label(
        _w66_children('<article class="defaultP">§ 24 nr. 2 blir oppheva.</article>', nr_shift),
        [0, 0],
        1,
        depth_name="item",
        depth_markers=nr_markers,
    ) == (None, "antecedent_names_no_ledd")
    # The retargeted conjunct itself. An antecedent that writes a WHOLE LEDD
    # establishes that ledd as a payload, not as a container whose items are being
    # relabelled — inheriting from it would renumber the bokstavs of a provision
    # that was just written. It changes no element of the measured population; it
    # is carried for W-66's cycle-guard reason.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 13 nytt tredje ledd skal lyde:</article>', bokstav_shift
        ),
        [0, 0],
        1,
        depth_name="item",
        depth_markers=bokstav_markers,
    ) == (None, "antecedent_is_not_item_depth")
    # Two ledd named: nothing unambiguous to inherit.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 59 første ledd og tredje ledd ny bokstav b skal lyde:</article>',
            bokstav_shift,
        ),
        [0, 0],
        1,
        depth_name="item",
        depth_markers=bokstav_markers,
    ) == (None, "antecedent_names_several_ledd")
    # W-66's meta-amendment guard and the part boundary, both unchanged.
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">I endringen av § 19-8 skal første ledd ny bokstav b lyde:</article>',
            bokstav_shift,
        ),
        [0, 0],
        1,
        depth_name="item",
        depth_markers=bokstav_markers,
    ) == (None, "antecedent_is_meta_amendment")
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 4 tredje ledd ny bokstav b skal lyde:</article>',
            bokstav_shift,
        ),
        [0, 1],
        1,
        depth_name="item",
        depth_markers=bokstav_markers,
    ) == (None, "part_has_no_antecedent_lead")
    # The shipped punktum call site is byte-identical: the defaults ARE W-66b's.
    punktum_shift = (
        '<article class="defaultP">Nåværende annet punktum blir nytt tredje punktum.</article>'
    )
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 3-4 fjerde ledd nytt annet punktum skal lyde:</article>',
            punktum_shift,
        ),
        [0, 0],
        1,
    ) == ("4", "antecedent_names_ledd")
    assert _no_antecedent_ledd_label(
        _w66_children(
            '<article class="defaultP">§ 13 nytt tredje ledd skal lyde:</article>', punktum_shift
        ),
        [0, 0],
        1,
    ) == (None, "antecedent_is_not_punktum_depth")


def _w76_relabel_op(sequence: int, section: str, ledd: str, src: str, dst: str) -> LegalOperation:
    from lawvm.norway.grafter import NO_LEDD_SET_RELABEL_PROVENANCE_TAG

    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.RENUMBER,
        target=LegalAddress(path=(("section", section), ("subsection", ledd), ("item", src))),
        destination=LegalAddress(path=(("section", section), ("subsection", ledd), ("item", dst))),
        source=OperationSource(
            statute_id="no/lovtid/9999-01-01-1", raw_text="item relabel", title="x"
        ),
        provenance_tags=(
            "base_act:no/lov/1999-01-01-1",
            "fallback:unstructured",
            NO_LEDD_SET_RELABEL_PROVENANCE_TAG,
        ),
        group_id=f"no/lovtid/9999-01-01-1:{sequence}",
        witness_rule_id="no_section_renumber_relabel",
    )


def _w76_statute(*letters: str) -> IRStatute:
    """A one-ledd section whose children are ITEM nodes — the corpus shape.

    Measured over the replayed trees of every censused base act that replays at
    all: 1,529 ``item`` nodes, 1,477 directly below a ``subsection`` and 52
    nested one further below another ``item``. ZERO hang anywhere else — in
    particular none straight off a section — which is why this production
    requires a ledd rather than guessing a shallow host.
    """
    return IRStatute(
        statute_id="no/lov/1999-01-01-1",
        title="Testlov",
        body=IRNode(
            kind=IRNodeKind.BODY,
            children=(
                IRNode(
                    kind=IRNodeKind.SECTION,
                    label="9",
                    children=(
                        IRNode(
                            kind=IRNodeKind.SUBSECTION,
                            label="1",
                            children=tuple(
                                IRNode(kind=IRNodeKind.ITEM, label=letter, text=f"bokstav {letter}")
                                for letter in letters
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_no_w76_item_relabel_applies_with_zero_apply_plane_edits() -> None:
    """W-76 apply: the shipped RENUMBER branch, one address level across.

    The apply plane was not touched for this item. The branch that runs here is
    W-66's, keyed on W-66's provenance tag, and it compares RESOLVED PATHS — so it
    is depth-agnostic and generalizes to ``item`` unchanged, exactly as W-66b
    generalized it to ``sentence``.
    """
    before = _w76_statute("a", "b", "c")
    ops = [_w76_relabel_op(1, "9", "1", "c", "d"), _w76_relabel_op(2, "9", "1", "b", "c")]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert [(child.label, child.text) for child in ledd.children] == [
        ("a", "bokstav a"),
        ("c", "bokstav b"),
        ("d", "bokstav c"),
    ]
    assert not [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


def test_no_w76_item_relabel_refuses_whole_rather_than_eat_an_occupant() -> None:
    """W-76 apply: W-66's safety property, unchanged at ITEM depth.

    A ledd that already carries the amendment being replayed is the
    ``removal_wrong`` hazard this guard exists for. Against a four-item ledd the
    ``c → d`` leg lands on live text, so it refuses; ``d`` is therefore still
    occupied when ``b → c`` runs, so that refuses too, and the ledd comes out
    untouched rather than half-relabelled. No θ cell is reached and nothing is
    destroyed.
    """
    before = _w76_statute("a", "b", "c", "d")
    ops = [_w76_relabel_op(1, "9", "1", "c", "d"), _w76_relabel_op(2, "9", "1", "b", "c")]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert [(child.label, child.text) for child in ledd.children] == [
        ("a", "bokstav a"),
        ("b", "bokstav b"),
        ("c", "bokstav c"),
        ("d", "bokstav d"),
    ]
    refusals = [
        a
        for a in adjudications
        if a.kind == "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    assert [a.op_id for a in refusals] == [
        "no/lovtid/9999-01-01-1:1",
        "no/lovtid/9999-01-01-1:2",
    ]
    assert all(a.blocking for a in refusals)
    assert [(a.detail or {}).get("destination_path") for a in refusals] == [
        "section:9/subsection:1/item:d",
        "section:9/subsection:1/item:c",
    ]
    assert not [
        a for a in adjudications if a.kind == "no_replay_renumber_occupied_destination_removed"
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w76_item_relabel_lowers_on_the_corpus_witness() -> None:
    """W-76 corpus witness: ``no/lovtid/2003-05-23-33`` → ``no/lov/1997-06-13-42``.

    Two ``defaultP`` nodes, one instruction:

        § 9 første ledd ny bokstav b skal lyde: lov 28. mai 1959 nr. 12 …
        Nåværende bokstav b til e blir bokstav c til f.

    Three facts are pinned, because three things have to be right: the range
    EXPANDS to four legs; the legs come out in vacate-before-occupy order rather
    than source order; and the address is ``section/subsection/item`` with the
    ledd taken from the same antecedent node as the section.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2003-05-23-33", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2003-05-23-33", adjudications_out=adjudications
        )
    )
    relabel = [
        op
        for op in grouped["no/lov/1997-06-13-42"]
        if op.action is StructuralAction.RENUMBER
        and op.source is not None
        and op.source.raw_text == "Nåværende bokstav b til e blir bokstav c til f."
    ]
    assert [(op.target.path, cast(LegalAddress, op.destination).path) for op in relabel] == [
        (
            (("section", "9"), ("subsection", "1"), ("item", "e")),
            (("section", "9"), ("subsection", "1"), ("item", "f")),
        ),
        (
            (("section", "9"), ("subsection", "1"), ("item", "d")),
            (("section", "9"), ("subsection", "1"), ("item", "e")),
        ),
        (
            (("section", "9"), ("subsection", "1"), ("item", "c")),
            (("section", "9"), ("subsection", "1"), ("item", "d")),
        ),
        (
            (("section", "9"), ("subsection", "1"), ("item", "b")),
            (("section", "9"), ("subsection", "1"), ("item", "c")),
        ),
    ]
    from lawvm.norway.grafter import NO_LEDD_SET_RELABEL_PROVENANCE_TAG

    assert all(NO_LEDD_SET_RELABEL_PROVENANCE_TAG in (op.provenance_tags or ()) for op in relabel)


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w76_unresolvable_ledd_gets_a_typed_receipt_not_a_guess() -> None:
    """W-76: 22 corpus refusals resolve their SECTION but not their LEDD.

    The older acts subdivide a section straight into ``nr.`` with no ledd at all
    ("§ 24 nr. 2 oppheves."), and this production will not guess which container
    holds the items — at this depth the resolver's first-match DFS would happily
    pick whichever ledd's bokstav carried the label. The receipt kind is W-76's
    OWN, not a reuse of W-66b's, because the reader's depth conjunct differs; the
    ``depth`` detail key tells a bokstav refusal from an nr. one.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2008-05-09-21", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2008-05-09-21", adjudications_out=adjudications
        )
    )
    typed = [
        item for item in adjudications if item.kind == NO_PARSE_ITEM_SET_RELABEL_LEDD_UNRESOLVED
    ]
    assert [(item.detail or {}).get("section") for item in typed] == ["3-13"]
    assert [(item.detail or {}).get("depth") for item in typed] == ["bokstav"]
    assert [(item.detail or {}).get("ledd_reason") for item in typed] == ["antecedent_names_no_ledd"]
    assert [(item.detail or {}).get("pairs") for item in typed] == [("g->h", "h->i", "i->j")]
    # Nothing was minted for it — not at a guessed ledd, not anywhere. Keyed on
    # the refused LEAD rather than its section label, for W-66c's reason.
    refused_leads = {(item.detail or {}).get("source_excerpt") for item in typed}
    assert not [
        op
        for base_ops in grouped.values()
        for op in base_ops
        if op.source is not None and op.source.raw_text in refused_leads
    ]


# ── W-77: the item-depth PAYLOAD production (``ny bokstav|nr Y skal lyde:``) ───


def test_no_w77_item_insert_grammar_accepts_the_corpus_shapes() -> None:
    """W-77: every shape the 225 censused refusals actually take.

    The return is ``(section, ledd, depth, labels)``. ``section`` and ``ledd`` are
    ``""`` when the announcement spells neither (the call site then inherits them
    from the DOM-local antecedent), ``depth`` names WHICH pattern matched — it
    selects the label vocabulary AND the antecedent's depth conjunct — and the
    labels are already normalized to the form the emitted op path uses.

    The argument is the announcing node's OWN text, not the walk's ``lead``: this
    family's payload sits INSIDE the announcing node as a ``<ul>``, so ``lead``
    is announcement and payload concatenated and cannot be anchored end to end.
    """
    from lawvm.norway.grafter import _no_item_insert_payload_target

    # The dominant shape: section and ledd both spelled, one new label.
    assert _no_item_insert_payload_target("§ 6-2 første ledd ny bokstav c skal lyde:") == (
        "6-2",
        "1",
        "bokstav",
        ["c"],
    )
    assert _no_item_insert_payload_target("§ 5 b første ledd ny nr. 15 skal lyde:") == (
        "5b",
        "1",
        "nr",
        ["15"],
    )
    # ``nytt``/``nye`` are the same marker; ``nummer`` is the same depth word.
    assert _no_item_insert_payload_target("§ 3 første ledd nytt nr. 13 skal lyde:") == (
        "3",
        "1",
        "nr",
        ["13"],
    )
    assert _no_item_insert_payload_target("§ 4 nytt nummer 9 og 10 skal lyde:") == (
        "4",
        "",
        "nr",
        ["9", "10"],
    )
    # Multi-label announcements: a list, and a RANGE that is EXPANDED rather than
    # counted on trust. 16 of the 225 are shaped this way.
    assert _no_item_insert_payload_target("§ 2 første ledd ny bokstav g og h skal lyde:") == (
        "2",
        "1",
        "bokstav",
        ["g", "h"],
    )
    assert _no_item_insert_payload_target("§ 13 første ledd ny bokstav c, d, e og f skal lyde:") == (
        "13",
        "1",
        "bokstav",
        ["c", "d", "e", "f"],
    )
    assert _no_item_insert_payload_target("Første ledd nye nr. 15 til 19 skal lyde:") == (
        "",
        "1",
        "nr",
        ["15", "16", "17", "18", "19"],
    )
    # The LIST PUNCTUATION Lovdata prints its letters with. W-76's family never
    # spells it; this one does, and it is stripped before the SHARED vocabulary
    # sees the token rather than by a second vocabulary of its own.
    assert _no_item_insert_payload_target("§ 4 første ledd ny bokstav t) skal lyde:") == (
        "4",
        "1",
        "bokstav",
        ["t"],
    )
    assert _no_item_insert_payload_target("§ 2 første ledd ny bokstav e) og f) skal lyde:") == (
        "2",
        "1",
        "bokstav",
        ["e", "f"],
    )
    # Neither the section nor the ledd is required in the sentence; both are then
    # inherited, and the caller refuses when the antecedent cannot supply them.
    assert _no_item_insert_payload_target("§ 5-31 ny bokstav c skal lyde:") == (
        "5-31",
        "",
        "bokstav",
        ["c"],
    )
    assert _no_item_insert_payload_target("Nytt nr. 10 skal lyde:") == ("", "", "nr", ["10"])
    # The colon is optional (``no/lovtid/2003-12-12-105`` spells none) and the
    # older ordinals resolve through the SHARED ordinal table.
    assert _no_item_insert_payload_target("§ 4-7 nytt nr. 3 skal lyde") == ("4-7", "", "nr", ["3"])
    assert _no_item_insert_payload_target("§ 14-43 annet ledd ny bokstav c skal lyde:") == (
        "14-43",
        "2",
        "bokstav",
        ["c"],
    )
    assert _no_item_insert_payload_target("§ 18-3 sjette ledd ny bokstav b skal lyde:") == (
        "18-3",
        "6",
        "bokstav",
        ["b"],
    )


def test_no_w77_item_insert_grammar_declines_the_neighbouring_shapes() -> None:
    """W-77: the limbs deliberately left refused, each one a sized population.

    Every assertion here is a shape that occurs in the corpus neighbourhood and
    that this production declines AT THE GRAMMAR — so it keeps its existing
    ``no_parse_unstructured_lead_unmatched`` receipt rather than gaining a typed
    W-77 one. Under-application is safe; a guess at any of them is not.
    """
    from lawvm.norway.grafter import _no_item_insert_payload_target

    # A MIXED list: existing labels AND a new one. 55 refusals, and a different
    # instruction — part REPLACE, part INSERT.
    assert _no_item_insert_payload_target("§ 78 bokstav h og ny bokstav i skal lyde:") is None
    assert _no_item_insert_payload_target("§ 5 a annet ledd nr. 7 og ny nr. 8 skal lyde:") is None
    assert (
        _no_item_insert_payload_target("§ 12 første ledd bokstav i til ny bokstav k skal lyde:")
        is None
    )
    # A NESTED item address (an item below an item). 21 refusals; the address has
    # a fourth step this grammar cannot spell.
    assert _no_item_insert_payload_target("§ 2-30 første ledd bokstav g ny nr. 7 skal lyde:") is None
    assert _no_item_insert_payload_target("§ 23-3 annet ledd nr. 1 ny bokstav d skal lyde:") is None
    # A DEEPER or other depth between the ledd and the item.
    assert (
        _no_item_insert_payload_target("§ 59 a første ledd første punktum nytt nr. 6 skal lyde:")
        is None
    )
    # A RUN-ON, or a relabel carrying a payload tail. The end-to-end anchor
    # declines them by construction, which is the point of anchoring at all.
    assert _no_item_insert_payload_target("§ 8-10 nr. 3 blir ny nr. 2. Ny nr. 2 skal lyde:") is None
    assert (
        _no_item_insert_payload_target(
            "Nåværende bokstav f og g blir ny bokstav g og h. Ny bokstav h skal lyde:"
        )
        is None
    )
    # Other depths entirely: ``ny`` in front of a punktum or a whole ledd.
    assert _no_item_insert_payload_target("§ 21 nr. 2 nytt tredje punktum skal lyde:") is None
    assert _no_item_insert_payload_target("§ 2-1 nytt åttende ledd skal lyde:") is None
    # A plain REPLACE with no newness marker at all is the SHIPPED reader's.
    assert _no_item_insert_payload_target("§ 6-2 første ledd bokstav c skal lyde:") is None
    # Letters outside ``a``–``z``, a spelled-out numeral, and every COUNTED
    # address. W-76's limbs verbatim: the vocabulary is explicit expansion.
    assert _no_item_insert_payload_target("§ 9 første ledd ny bokstav ø skal lyde:") is None
    assert _no_item_insert_payload_target("§ 9 første ledd ny nr. tre skal lyde:") is None
    assert _no_item_insert_payload_target("§ 9 første ledd ny siste bokstav skal lyde:") is None
    # A descending range names nothing, and a repeated label is not a set.
    assert _no_item_insert_payload_target("§ 9 første ledd nye nr. 8 til 5 skal lyde:") is None
    assert _no_item_insert_payload_target("§ 9 første ledd ny bokstav c og c skal lyde:") is None


def test_no_w77_item_insert_grammar_is_disjoint_from_the_shipped_readers() -> None:
    """W-77 is strictly ADDITIVE, and its POSITION in the walk is the proof.

    The block sits LAST, behind W-76's and immediately ahead of the operative
    fallback, so a lead only reaches it once every shipped family has declined it.
    The grammar disjointness says the same thing independently and is pinned here
    from BOTH sides: the shipped item-target reader requires ``ledd bokstav``
    ADJACENCY (which the ``ny`` marker breaks) and W-76's relabel requires a
    currency qualifier and the verb ``blir`` (which this family never spells).
    """
    from lawvm.norway.grafter import (
        _NO_ITEM_INSERT_PAYLOAD_LEDD_ALTERNATION,
        _NO_ITEM_INSERT_PAYLOAD_PATTERNS,
        _NORWEGIAN_ORDINALS,
        _infer_same_base_item_target_specs_from_lead,
        _no_item_insert_payload_target,
    )

    mine = (
        "§ 6-2 første ledd ny bokstav c skal lyde:",
        "§ 5 b første ledd ny nr. 15 skal lyde:",
        "§ 2 første ledd ny bokstav g og h skal lyde:",
    )
    shipped_item = "§ 6-2 første ledd bokstav c skal lyde:"
    shipped_relabel = "Nåværende bokstav c blir ny bokstav d."
    shipped_ledd_relabel = "Nåværende femte og sjette ledd blir sjette og sjuende ledd."
    for lead in mine:
        # The shipped item-target reader cannot span the ``ny`` marker: this is
        # exactly the adjacency break that left the payload half unminted.
        assert _infer_same_base_item_target_specs_from_lead(lead) == []
        assert _no_item_set_relabel_pairs(lead) is None
        assert _no_ledd_set_relabel_pairs(lead) is None
        assert _no_punktum_set_relabel_pairs(lead) is None
    for shipped in (shipped_item, shipped_relabel, shipped_ledd_relabel):
        assert _no_item_insert_payload_target(shipped) is None
    # And the shipped reader still owns the no-``ny`` variant, whose REPLACE
    # ``_promote_no_replace_with_following_renumber_insert`` promotes to the same
    # INSERT — the five corpus ops W-76 recorded. This production does not touch
    # that lane.
    assert _infer_same_base_item_target_specs_from_lead(shipped_item) == [
        (
            StructuralAction.REPLACE,
            LegalAddress(path=(("section", "6-2"), ("subsection", "1"), ("item", "c"))),
        )
    ]
    # The two item patterns are mutually exclusive by their depth words, so the
    # iteration order over them is immaterial rather than load-bearing.
    assert set(_NO_ITEM_INSERT_PAYLOAD_PATTERNS) == {"bokstav", "nr"}
    bokstav = _no_item_insert_payload_target("§ 9 første ledd ny bokstav b skal lyde:")
    numeral = _no_item_insert_payload_target("§ 9 første ledd ny nr. 2 skal lyde:")
    assert bokstav is not None and bokstav[2] == "bokstav"
    assert numeral is not None and numeral[2] == "nr"
    # The ledd alternation is DERIVED from the ordinal table it then looks up in,
    # so the regex and the lookup cannot disagree about which words are ordinals.
    assert set(_NO_ITEM_INSERT_PAYLOAD_LEDD_ALTERNATION.split("|")) == set(_NORWEGIAN_ORDINALS)


def _w77_lead_node(html: str) -> etree._Element:
    return etree.fromstring(html.encode("utf-8"))


def test_no_w77_payload_extent_is_proved_against_the_announced_labels() -> None:
    """W-77: the extent proof, which is what bounds a production that ADDS text.

    Two carriers and no others. A LIST carrier must yield top-level items whose
    labels equal the announced labels one for one and in order; a TEXT carrier is
    admitted only for a single label, a single following payload node, and only
    when that node is an ``article.legalP``. Anything else refuses whole.
    """
    from lawvm.norway.grafter import _no_item_insert_payloads

    # The dominant carrier: the payload is a ``<ul>`` INSIDE the announcing node.
    # Verbatim markup from ``no/lovtid/2007-01-26-3`` (the § 6-2 gap case).
    inline = _w77_lead_node(
        '<article class="defaultP">§ 6-2 første ledd ny bokstav c skal lyde:'
        '<ul class="defaultList"><li data-li-identifier="c)" data-name="c)">'
        '<article class="listArticle"><article class="legalP">saker om patenter,'
        " kretsmønstre til integrerte kretser, planteforedlerretter, varemerker og design,"
        "</article></article></li></ul></article>"
    )
    payloads = _no_item_insert_payloads(inline, [], ["c"])
    assert payloads is not None
    assert [(_kind_value(p.kind), p.label) for p in payloads] == [("item", "c")]
    assert payloads[0].text == (
        "saker om patenter, kretsmønstre til integrerte kretser, planteforedlerretter,"
        " varemerker og design,"
    )
    # A multi-label announcement: one top-level ``<li>`` per announced label, in
    # order, each with its own ``data-name``.
    multi = _w77_lead_node(
        '<article class="defaultP">§ 2 første ledd ny bokstav g og h skal lyde:'
        '<ul class="defaultList">'
        '<li data-name="g)"><article class="legalP">skriftlig: elektronisk melding.</article></li>'
        '<li data-name="h)"><article class="legalP">nedtegning og protokollering.</article></li>'
        "</ul></article>"
    )
    assert [p.label for p in (_no_item_insert_payloads(multi, [], ["g", "h"]) or [])] == ["g", "h"]
    # NESTED sub-items stay INSIDE the payload. This is why the extent test runs
    # on ``_extract_items`` rather than on the flattened candidate map, which
    # would present ``q, 1, 2`` and make a nested payload indistinguishable from
    # a mis-sized one. Measured: 3 corpus ops turn on this.
    nested = _w77_lead_node(
        '<article class="defaultP">§ 5-15 første ledd ny bokstav q skal lyde:'
        '<ul class="defaultList"><li data-name="q."><article class="listArticle">'
        '<article class="legalP">arbeidsgivers dekning av følgende merkostnader:</article>'
        '<ul class="defaultList">'
        '<li data-name="1."><article class="legalP">Kostutgifter.</article></li>'
        '<li data-name="2."><article class="legalP">Losji.</article></li>'
        "</ul></article></li></ul></article>"
    )
    nested_payloads = _no_item_insert_payloads(nested, [], ["q"])
    assert nested_payloads is not None
    assert [p.label for p in nested_payloads] == ["q"]
    assert [(c.label, c.text) for c in nested_payloads[0].children] == [
        ("1", "Kostutgifter."),
        ("2", "Losji."),
    ]
    # The SIBLING carrier: no list anywhere, one announced label, exactly one
    # following ``article.legalP``.
    bare = _w77_lead_node('<article class="defaultP">§ 1-6 ny bokstav m skal lyde:</article>')
    sibling = _w77_lead_node(
        '<article class="legalP">Oppstrøms gassrørledningsnett, enhver gassrørledning.</article>'
    )
    text_payloads = _no_item_insert_payloads(bare, [sibling], ["m"])
    assert text_payloads is not None
    assert [(_kind_value(p.kind), p.label, p.text) for p in text_payloads] == [
        ("item", "m", "Oppstrøms gassrørledningsnett, enhver gassrørledning.")
    ]
    # ``numberedLegalP`` DECLINES: its text opens with its own numerator, which is
    # a second address claim this production will not discard on trust. One
    # corpus refusal costs that.
    numbered = _w77_lead_node(
        '<article class="numberedLegalP">(4) opplysninger om navn og adresse.</article>'
    )
    assert _no_item_insert_payloads(bare, [numbered], ["m"]) is None
    # No payload at all, several payload nodes, and a heading + text pair: all
    # unprovable extents, all refused whole.
    assert _no_item_insert_payloads(bare, [], ["m"]) is None
    assert _no_item_insert_payloads(bare, [sibling, sibling], ["m"]) is None
    heading = _w77_lead_node('<article class="defaultP">(Fravikelighet)</article>')
    assert _no_item_insert_payloads(bare, [heading, sibling], ["m"]) is None
    # The all-or-nothing rule: a list that does not split to match the declared
    # arity is no evidence for which label the halves belong to.
    assert _no_item_insert_payloads(multi, [], ["g"]) is None
    assert _no_item_insert_payloads(multi, [], ["g", "h", "i"]) is None
    assert _no_item_insert_payloads(multi, [], ["h", "g"]) is None
    assert _no_item_insert_payloads(inline, [], ["d"]) is None
    # …and the text carrier is single-label only, for the same reason.
    assert _no_item_insert_payloads(bare, [sibling], ["m", "n"]) is None


def _w77_insert_op(sequence: int, section: str, ledd: str, item: str, text: str) -> LegalOperation:
    from lawvm.norway.grafter import NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG

    return LegalOperation(
        op_id=f"no/lovtid/9999-01-01-1:{sequence}",
        sequence=sequence,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=(("section", section), ("subsection", ledd), ("item", item))),
        payload=IRNode(kind=IRNodeKind.ITEM, label=item, text=text),
        source=OperationSource(
            statute_id="no/lovtid/9999-01-01-1", raw_text="item insert payload", title="x"
        ),
        provenance_tags=(
            "base_act:no/lov/1999-01-01-1",
            "fallback:unstructured",
            NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG,
        ),
        group_id=f"no/lovtid/9999-01-01-1:{sequence}",
    )


def test_no_w77_item_insert_refuses_an_occupied_target_rather_than_replace() -> None:
    """W-77 apply: the occupied destination, and the polarity is the whole item.

    The declared θ ``(INSERT, target_occupied)`` cell RECOVERS by replacing the
    occupant. That is right for the ``ny § 4 a skal lyde`` surface §2.3
    documents and wrong for an item-depth newness payload: an announcement that
    says NY bokstav c and finds bokstav c standing means the vacate did not
    happen, and the occupant's in-force text is not the thing to delete. W-66
    measured exactly that destruction one depth up.
    """
    before = _w76_statute("a", "b", "c")
    ops = [_w77_insert_op(1, "9", "1", "c", "den nye bokstav c")]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    # Nothing landed and, crucially, the occupant survives byte-identical.
    assert [(child.label, child.text) for child in ledd.children] == [
        ("a", "bokstav a"),
        ("b", "bokstav b"),
        ("c", "bokstav c"),
    ]
    refusals = [
        a for a in adjudications if a.kind == "no_replay_item_insert_payload_occupied_target_refused"
    ]
    assert [a.op_id for a in refusals] == ["no/lovtid/9999-01-01-1:1"]
    assert all(a.blocking for a in refusals)
    assert (refusals[0].detail or {}).get("resolved_path") == "section:9/subsection:1/item:c"
    assert (refusals[0].detail or {}).get("occupant_label") == "c"
    # The shipped θ cell did NOT fire: it keeps its RECOVER polarity for every op
    # that is not this production's, which is why the corpus firing census cannot
    # move.
    assert not [a for a in adjudications if a.kind == "no_replay_insert_occupied_target_replaced"]
    # A conserved apply sees the op as REJECTED rather than as a recovery that
    # applied — the reason the kind is in ``_NO_SKIP_ADJUDICATION_KINDS``.
    conserved = apply_no_ops_conserved(before, ops, adjudications_out=[])
    assert conserved.applied_ops == ()
    assert len(conserved.skipped_items) == 1
    # An UNoccupied target is the ordinary path and lands.
    landed = apply_no_ops(_w76_statute("a", "b"), ops, adjudications_out=[])
    landed_ledd = landed.body.children[0].children[0]
    assert [(child.label, child.text) for child in landed_ledd.children] == [
        ("a", "bokstav a"),
        ("b", "bokstav b"),
        ("c", "den nye bokstav c"),
    ]


def test_no_w77_relabel_and_payload_compose_in_the_kernels_vacate_order() -> None:
    """W-77: the pair composes, and the ordering proof is the KERNEL's.

    ``no_ordering_profile`` sets ``renumber_vacate=True`` with
    ``renumber_group_key=_no_group_key`` = ``(effective, enacted, source_id)``,
    and ``_structural_vacate_order`` emits, within each group: REPEALs by
    sequence, then RENUMBERs topologically, then EVERY OTHER OP by sequence. An
    INSERT is in that third stage — so the relabel that vacates bokstav c is
    ordered before the INSERT that fills it, and NOT by luck of ``sequence``.

    The ops are handed to ``apply_no_ops`` in MINT order, which on the corpus
    witness puts the INSERT first (the announcement precedes the relabel in the
    instrument). Read in that order the INSERT would land on a live bokstav c and
    refuse; ordered, it lands in an empty slot.
    """
    before = _w76_statute("a", "b", "c", "d", "e")
    ops = [
        _w77_insert_op(1, "9", "1", "c", "den nye bokstav c"),
        _w76_relabel_op(2, "9", "1", "c", "d"),
        _w76_relabel_op(3, "9", "1", "d", "e"),
        _w76_relabel_op(4, "9", "1", "e", "f"),
    ]
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(before, ops, adjudications_out=adjudications)

    ledd = result.body.children[0].children[0]
    assert [(child.label, child.text) for child in ledd.children] == [
        ("a", "bokstav a"),
        ("b", "bokstav b"),
        ("c", "den nye bokstav c"),
        ("d", "bokstav c"),
        ("e", "bokstav d"),
        ("f", "bokstav e"),
    ]
    # No leg refused, and the INSERT did not take the shipped occupied recovery.
    assert not [
        a
        for a in adjudications
        if a.kind
        in {
            "no_replay_item_insert_payload_occupied_target_refused",
            "no_replay_ledd_set_relabel_occupied_destination_refused",
            "no_replay_insert_occupied_target_replaced",
        }
    ]
    # And where the relabel is ABSENT, the same INSERT refuses rather than eating
    # the occupant — the two halves are independent and the polarity holds.
    solo: list[CompileAdjudication] = []
    apply_no_ops(before, [ops[0]], adjudications_out=solo)
    assert [a.kind for a in solo if a.blocking] == [
        "no_replay_item_insert_payload_occupied_target_refused"
    ]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w77_item_insert_lowers_on_the_corpus_gap_witness() -> None:
    """W-77 corpus witness: ``no/lovtid/2007-01-26-3`` → ``no/lov/2005-06-17-90``.

    This is the gap W-76 recorded and could not close. The instrument says

        § 6-2 første ledd ny bokstav c skal lyde: saker om patenter, …
        Nåværende bokstav c, d og e blir bokstav d, e og f.

    W-76 lowers the relabel, which VACATES bokstav c; nothing refilled it,
    because the shipped item-target reader's ``ledd bokstav`` adjacency breaks on
    the ``ny`` marker. Three facts are pinned: the address is
    ``section/subsection/item`` with the ledd from the sentence's own text, the
    action is INSERT (not the promoted REPLACE lane), and the payload is the
    instrument's own words.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2007-01-26-3", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    from lawvm.norway.grafter import NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2007-01-26-3", adjudications_out=adjudications
        )
    )
    minted = [
        op
        for op in grouped["no/lov/2005-06-17-90"]
        if NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG in (op.provenance_tags or ())
    ]
    assert [op.target.path for op in minted] == [
        (("section", "6-2"), ("subsection", "1"), ("item", "c"))
    ]
    assert [_action_value(op.action) for op in minted] == ["insert"]
    payload = minted[0].payload
    assert payload is not None
    assert (_kind_value(payload.kind), payload.label) == ("item", "c")
    assert payload.text == (
        "saker om patenter, kretsmønstre til integrerte kretser, planteforedlerretter,"
        " varemerker og design,"
    )
    # The relabel W-76 mints is still there, and the pair shares a group key, so
    # the kernel's structural-vacate stage runs the vacate first.
    relabel = [
        op
        for op in grouped["no/lov/2005-06-17-90"]
        if op.action is StructuralAction.RENUMBER
        and op.target.path[:2] == (("section", "6-2"), ("subsection", "1"))
    ]
    assert [op.target.path[-1] for op in relabel] == [("item", "e"), ("item", "d"), ("item", "c")]


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w77_unresolvable_ledd_gets_a_typed_receipt_not_a_guess() -> None:
    """W-77: 73 of the 225 censused refusals resolve their section, not their ledd.

    The older acts subdivide a section straight into ``nr.`` with no ledd in the
    sentence at all ("§ 65 nytt nr. 4 skal lyde:"), and here the nearest
    preceding instruction lead is a WHOLE-LEDD one — an antecedent that writes a
    ledd establishes that ledd as a payload, not as a container whose items are
    being addressed, so the retargeted depth conjunct declines it. Every corpus
    item node sits under a ledd and the resolver's find is a first-match DFS, so
    a shallow address would silently pick whichever ledd carried the label.
    Nothing is minted.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2008-03-07-4", _NO_FARCHIVE_PATH)
    assert html_bytes is not None

    from lawvm.norway.grafter import (
        NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG,
        NO_PARSE_ITEM_INSERT_PAYLOAD_LEDD_UNRESOLVED,
    )

    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            html_bytes, "no/lovtid/2008-03-07-4", adjudications_out=adjudications
        )
    )
    typed = [
        item for item in adjudications if item.kind == NO_PARSE_ITEM_INSERT_PAYLOAD_LEDD_UNRESOLVED
    ]
    assert [(item.detail or {}).get("section") for item in typed] == ["65"]
    assert [(item.detail or {}).get("depth") for item in typed] == ["nr"]
    assert [(item.detail or {}).get("labels") for item in typed] == [("4",)]
    assert [(item.detail or {}).get("ledd_reason") for item in typed] == [
        "antecedent_is_not_item_depth"
    ]
    # Nothing was minted for it — not at a guessed ledd, not anywhere.
    assert not [
        op
        for base_ops in grouped.values()
        for op in base_ops
        if NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG in (op.provenance_tags or ())
    ]


# ── W-98: the pre-2001 lead grammar, closed on the kringkastingsloven witness ─
#
# Item 97 (W-91) ran the OCR-reconstructed 1992 broadcasting act and its eleven
# cached amending acts through the unstructured walk; nine lead shapes on
# certified lines refused ``no_parse_unstructured_lead_unmatched``. Every test
# below carries the witness lead VERBATIM and a minimal inline fixture in the
# pre-2001 shape the print-era emitter writes.

_W98_BASE = "no/lov/1992-12-04-127"


def _w98_amendment(members: str) -> bytes:
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


def _w98_ops(
    members: str, source_id: str = "no/lovtid/2000-01-14-5"
) -> tuple[list[LegalOperation], list[CompileAdjudication]]:
    adjudications: list[CompileAdjudication] = []
    grouped = dict(iter_no_document_change_ops(_w98_amendment(members), source_id, adjudications_out=adjudications))
    return list(grouped.get(_W98_BASE, [])), adjudications


def _w98_shape(op: LegalOperation) -> tuple[object, tuple[tuple[str, str], ...], object, object]:
    return (
        _action_value(op.action),
        op.target.path,
        None if op.destination is None else op.destination.path,
        None if op.source is None else op.source.raw_text,
    )


def _w98_future_article(name: str, title: str, ledd: Sequence[str]) -> str:
    body = "".join(f'<article class="legalP">{text}</article>' for text in ledd)
    return (
        f'<article class="futureLegalArticle" data-name="{name}">'
        f'<span class="futureLegalArticleHeader">{name[0]} {name[1:]}. <span class="legalArticleTitle">{title}</span></span>'
        f"{body}</article>"
    )


def _w98_statute(chapters: Sequence[tuple[str, str, Sequence[tuple[str, str, Sequence[str]]]]]) -> IRStatute:
    """A Lovdata-shaped consolidated statute: ``(chapter label, title, [(section label, title, [ledd…])])``."""
    parts = []
    for chapter_label, chapter_title, sections in chapters:
        articles = "".join(
            f'<article class="legalArticle" data-name="§{label}"><h3 class="legalArticleHeader">§ {label}. {title}</h3>'
            + "".join(f'<article class="legalP">{text}</article>' for text in ledd)
            + "</article>"
            for label, title, ledd in sections
        )
        parts.append(
            f'<section class="section" data-name="kap{chapter_label}"><h2>{chapter_title}</h2>{articles}</section>'
        )
    xml = (
        '<?xml version="1.0" encoding="utf-8"?><html lang="nb"><head><title>Lov om kringkasting.</title></head>'
        f'<body><main class="documentBody">{"".join(parts)}</main></body></html>'
    )
    return parse_no_statute(xml.encode("utf-8"), _W98_BASE)


def _w98_chapter(statute: IRStatute, label: str) -> IRNode:
    return next(
        child for child in statute.body.children if _kind_value(child.kind) == "chapter" and child.label == label
    )


def _w98_sections(node: IRNode) -> list[tuple[str | None, list[str]]]:
    return [
        (child.label, [ledd.text or "" for ledd in child.children if _kind_value(ledd.kind) == "subsection"])
        for child in node.children
        if _kind_value(child.kind) == "section"
    ]


def _w98_heading(node: IRNode) -> str:
    return next(child.text or "" for child in node.children if _kind_value(child.kind) == "heading")


def _w98_unmatched(adjudications: Sequence[CompileAdjudication]) -> list[str]:
    return [
        str((item.detail or {}).get("source_excerpt"))
        for item in adjudications
        if item.kind == "no_parse_unstructured_lead_unmatched"
    ]


# (a) the repeated-noun ledd list ------------------------------------------------


def test_no_w98_repeated_ledd_noun_list_lowers_the_witness() -> None:
    """W-91 gap 3, ``no/lovtid/1993-12-17-126``: ``§ 7-2 første ledd og tredje ledd skal lyde:``."""
    lead = "§ 7-2 første ledd og tredje ledd skal lyde:"
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article>'
        '<article class="legalP">Kringkastingsrådet består av 14 medlemmer med personlige varamedlemmer.</article>'
        '<article class="legalP">Lederen eller et medlem i dennes sted kan møte i styret og delta i drøftingene.</article>',
        source_id="no/lovtid/1993-12-17-126",
    )
    assert [_w98_shape(op) for op in ops] == [
        ("replace", (("section", "7-2"), ("subsection", "1")), None, lead),
        ("replace", (("section", "7-2"), ("subsection", "3")), None, lead),
    ]
    assert [op.payload.text for op in ops if op.payload is not None] == [
        "Kringkastingsrådet består av 14 medlemmer med personlige varamedlemmer.",
        "Lederen eller et medlem i dennes sted kan møte i styret og delta i drøftingene.",
    ]
    assert _w98_unmatched(adjudications) == []


def test_no_w98_repeated_noun_scopes_newness_per_member_and_declines_the_shipped_shape() -> None:
    """The repeated noun closes each member's noun phrase: ``nytt`` scopes over its own member only."""
    # The single-noun list is the shipped reader's, byte for byte: declined here.
    assert _no_repeated_ledd_noun_subsection_specs("§ 7-2 første og tredje ledd skal lyde:") == []
    assert _no_repeated_ledd_noun_subsection_specs("§ 7-2 nytt tredje og fjerde ledd skal lyde:") == []
    # A second section in the list is not this grammar.
    assert _no_repeated_ledd_noun_subsection_specs("§ 5 første ledd og § 6 tredje ledd skal lyde:") == []
    specs = _no_repeated_ledd_noun_subsection_specs("§ 1-1 nytt tredje ledd og fjerde ledd skal lyde:")
    assert [(_action_value(action), target.path) for action, target in specs] == [
        ("insert", (("section", "1-1"), ("subsection", "3"))),
        ("replace", (("section", "1-1"), ("subsection", "4"))),
    ]
    # The corpus's commonest member of the family: an existing ledd and a new one.
    specs = _no_repeated_ledd_noun_subsection_specs("§ 10-1 første ledd og nytt annet ledd skal lyde:")
    assert [(_action_value(action), target.path) for action, target in specs] == [
        ("replace", (("section", "10-1"), ("subsection", "1"))),
        ("insert", (("section", "10-1"), ("subsection", "2"))),
    ]


# (b) the mixed punktum + ledd member list ---------------------------------------


def test_no_w98_mixed_punktum_ledd_lead_lowers_the_witness() -> None:
    """W-91 gap 2, ``no/lovtid/2000-01-14-5``: a punktum member beside a ledd member, one article each."""
    lead = "§ 2-5 første ledd første punktum og andre ledd skal lyde:"
    first = "Kringkastere skal oppbevare opptak av program i minst to måneder etter sending."
    second = "Kringkastere plikter å utlevere opptak av program til de instanser som har til oppgave å føre tilsyn."
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article>'
        f'<article class="legalP">{first}</article>'
        f'<article class="legalP">{second}</article>'
    )
    assert [_w98_shape(op) for op in ops] == [
        ("replace", (("section", "2-5"), ("subsection", "1"), ("sentence", "1")), None, lead),
        ("replace", (("section", "2-5"), ("subsection", "2")), None, lead),
    ]
    sentence, ledd = (op.payload for op in ops)
    assert sentence is not None and _kind_value(sentence.kind) == "sentence" and sentence.text == first
    assert ledd is not None and _kind_value(ledd.kind) == "subsection" and ledd.text == second
    assert _w98_unmatched(adjudications) == []


def test_no_w98_mixed_member_reader_declines_homogeneous_lists_and_refuses_on_arity() -> None:
    # Homogeneous lists belong to the shipped readers and are declined by construction.
    assert _no_mixed_punktum_ledd_member_specs("§ 2-5 første og andre ledd skal lyde:") == []
    assert _no_mixed_punktum_ledd_member_specs("§ 2-5 første ledd første og annet punktum skal lyde:") == []
    # A run-on with a relabel in front is not a member list.
    assert (
        _no_mixed_punktum_ledd_member_specs(
            "§ 12-5 annet ledd blir nytt tredje punktum i første ledd. Nytt annet og tredje ledd skal lyde:"
        )
        == []
    )
    specs = _no_mixed_punktum_ledd_member_specs("§ 47 første ledd nytt annet punktum og nytt annet ledd skal lyde:")
    assert [(_action_value(action), target.path) for action, target in specs] == [
        ("insert", (("section", "47"), ("subsection", "1"), ("sentence", "2"))),
        ("insert", (("section", "47"), ("subsection", "2"))),
    ]
    # One article for two members: the whole lead refuses, typed, and nothing is minted.
    lead = "§ 2-5 første ledd første punktum og andre ledd skal lyde:"
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article><article class="legalP">Bare én.</article>'
    )
    assert ops == []
    refusals = [item for item in adjudications if item.kind == NO_PARSE_MIXED_MEMBER_PAYLOAD_ARITY_MISMATCH]
    assert len(refusals) == 1
    detail = refusals[0].detail or {}
    assert detail["declared_count"] == 2 and detail["payload_count"] == 1
    assert detail["strict_disposition"] == "block" and refusals[0].blocking
    assert _w98_unmatched(adjudications) == []


# (c) the section range ----------------------------------------------------------


def test_no_w98_section_range_with_a_section_sign_on_both_ends_lowers_the_witness() -> None:
    """W-91 gap 8, ``no/lovtid/1998-05-22-32``: ``§ 5-1 til § 5-6 oppheves.`` — six repeals, not two."""
    lead = "§ 5-1 til § 5-6 oppheves."
    ops, adjudications = _w98_ops(f'<article class="defaultP">{lead}</article>', source_id="no/lovtid/1998-05-22-32")
    assert [_w98_shape(op) for op in ops] == [
        ("repeal", (("section", f"5-{number}"),), None, lead) for number in range(1, 7)
    ]
    assert _w98_unmatched(adjudications) == []
    # The nynorsk verb on the shipped spelling.
    ops, _ = _w98_ops('<article class="defaultP">§§ 36 til 38 blir oppheva.</article>')
    assert [op.target.path for op in ops] == [(("section", "36"),), (("section", "37"),), (("section", "38"),)]


def test_no_w98_section_range_expander_enumerates_chapter_numbered_ranges_or_refuses() -> None:
    """The one range grammar, and the shipped ``§§ A til B`` lead now goes through it too."""
    assert _expand_no_section_range_labels("16", "19") == ["16", "17", "18", "19"]
    assert _expand_no_section_range_labels("5-16", "5-19") == ["5-16", "5-17", "5-18", "5-19"]
    assert _expand_no_section_range_labels("2", "5a") == ["2", "3", "4", "5", "5a"]
    assert _expand_no_section_range_labels("5a", "7") == ["5a", "6", "7"]
    assert _expand_no_section_range_labels("5a", "5c") == ["5a", "5b", "5c"]
    assert _expand_no_section_range_labels("7", "7") == ["7"]
    # Unexpandable: cross-chapter, unordered, or a label outside the grammar.
    assert _expand_no_section_range_labels("2-4", "3-2") is None
    assert _expand_no_section_range_labels("9", "7") is None
    assert _expand_no_section_range_labels("5a", "5") is None
    assert _expand_no_section_range_labels("x", "y") is None
    # The shipped lead enumerates a chapter-numbered range instead of its endpoints.
    ops, _ = _w98_ops('<article class="defaultP">§§ 5-16 til 5-19 oppheves.</article>')
    assert [op.target.path for op in ops] == [(("section", f"5-{number}"),) for number in (16, 17, 18, 19)]
    # And an unexpandable range refuses TYPED rather than repealing two endpoints.
    ops, adjudications = _w98_ops('<article class="defaultP">§§ 2-4 til 3-2 oppheves.</article>')
    assert ops == []
    assert [item.kind for item in adjudications] == [NO_PARSE_SECTION_RANGE_UNEXPANDABLE]
    detail = adjudications[0].detail or {}
    assert (detail["start"], detail["end"]) == ("2-4", "3-2") and detail["strict_disposition"] == "block"


# (d) ``bokstav a)`` and the single-text-article item payload ---------------------


def test_no_w98_bokstav_paren_item_lead_lowers_the_witness_off_its_single_text_article() -> None:
    """W-91 gap 6, ``no/lovtid/1994-06-16-18``: the print's ``bokstav a)`` and a bare ``legalP`` payload."""
    lead = "§ 10-1 første ledd bokstav a) skal lyde:"
    text = (
        "overtrer bestemmelser i kapitlene 2, 3, 4, §§ 8-1 og 8-2, eller forskrift gitt med hjemmel i disse "
        "bestemmelser."
    )
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article><article class="legalP">{text}</article>',
        source_id="no/lovtid/1994-06-16-18",
    )
    assert [_w98_shape(op) for op in ops] == [
        ("replace", (("section", "10-1"), ("subsection", "1"), ("item", "a")), None, lead),
    ]
    payload = ops[0].payload
    assert payload is not None and _kind_value(payload.kind) == "item" and payload.label == "a"
    assert payload.text == text
    assert NO_ITEM_PAYLOAD_SINGLE_TEXT_ARTICLE_PROVENANCE_TAG in (ops[0].provenance_tags or ())
    assert _w98_unmatched(adjudications) == []
    # Two text articles behind one item: no single-article proof, the shipped payload receipt stays.
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article>'
        f'<article class="legalP">{text}</article><article class="legalP">Og en til.</article>'
    )
    assert ops == []
    assert [item.kind for item in adjudications] == ["no_parse_unstructured_payload_unresolved"]
    assert (adjudications[0].detail or {}).get("payload_family") == "item"


# (e) the compound repeal-then-reenact lead ---------------------------------------


def test_no_w98_compound_ledd_repeal_then_reenact_lowers_the_witness_and_applies() -> None:
    """W-91 gap 4, ``no/lovtid/2000-01-14-5``: repeal the third ledd, re-enact a third, replace the fourth."""
    lead = "§ 1-1 tredje ledd oppheves. Nytt tredje ledd og fjerde ledd skal lyde:"
    third = "Med kringkaster menes fysisk eller juridisk person som har det redaksjonelle ansvaret."
    fourth = "Med reklame menes enhver form for markedsføring av en vare, tjeneste, sak eller idé."
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article>'
        f'<article class="legalP">{third}</article><article class="legalP">{fourth}</article>'
    )
    assert [_w98_shape(op) for op in ops] == [
        ("repeal", (("section", "1-1"), ("subsection", "3")), None, lead),
        ("insert", (("section", "1-1"), ("subsection", "3")), None, lead),
        ("replace", (("section", "1-1"), ("subsection", "4")), None, lead),
    ]
    assert all(NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG in (op.provenance_tags or ()) for op in ops)
    assert _w98_unmatched(adjudications) == []
    assert _no_ledd_repeal_reenact_specs("§ 1-1 tredje ledd oppheves. Nåværende fjerde ledd blir tredje ledd.") is None

    statute = _w98_statute(
        [("1", "Kap. 1. Definisjoner", [("1-1", "Definisjoner", ["én", "to", "tre", "fire", "fem"])])]
    )
    result = apply_no_ops(statute, ops, adjudications_out=[])
    assert _w98_sections(_w98_chapter(result, "1")) == [("1-1", ["én", "to", third, fourth, "fem"])]


def test_no_w98_compound_reenact_insert_refuses_an_occupied_slot_it_never_repealed() -> None:
    """The production's INSERT legs refuse the θ (INSERT, target_occupied) recovery."""
    lead = "§ 1-1 tredje ledd oppheves. Nytt tredje ledd og nytt fjerde ledd skal lyde:"
    ops, _ = _w98_ops(
        f'<article class="defaultP">{lead}</article>'
        '<article class="legalP">ny tre</article><article class="legalP">ny fire</article>'
    )
    assert [_action_value(op.action) for op in ops] == ["repeal", "insert", "insert"]
    statute = _w98_statute([("1", "Kap. 1", [("1-1", "Definisjoner", ["én", "to", "tre", "fire"])])])
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(statute, ops, adjudications_out=adjudications)
    # The repealed slot is re-enacted; the standing fourth ledd survives byte-identical.
    assert _w98_sections(_w98_chapter(result, "1")) == [("1-1", ["én", "to", "ny tre", "fire"])]
    refusals = [
        item for item in adjudications if item.kind == NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED
    ]
    assert len(refusals) == 1 and refusals[0].blocking
    assert (refusals[0].detail or {}).get("production") == NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG
    assert (refusals[0].detail or {}).get("resolved_path") == "chapter:1/section:1-1/subsection:4"
    assert not [item for item in adjudications if item.kind == "no_replay_insert_occupied_target_replaced"]
    conserved = apply_no_ops_conserved(statute, ops, adjudications_out=[])
    assert len(conserved.applied_ops) == 2 and len(conserved.skipped_items) == 1


# (f) the chapter heading --------------------------------------------------------


def test_no_w98_chapter_heading_lead_lowers_the_witness_and_merges_over_the_standing_chapter() -> None:
    """W-91 gap 5, ``no/lovtid/2000-01-14-5``: ``Overskriften til kapittel 3 skal lyde:`` + one title line."""
    lead = "Overskriften til kapittel 3 skal lyde:"
    ops, adjudications = _w98_ops(
        f'<article class="defaultP">{lead}</article><article class="legalP">Reklame, sponsing m.v.</article>'
        '<article class="defaultP">§ 3-4 andre ledd skal lyde:</article><article class="legalP">Innhold.</article>'
    )
    assert [_w98_shape(op) for op in ops] == [
        ("replace", (("chapter", "3"),), None, lead),
        ("replace", (("section", "3-4"), ("subsection", "2")), None, "§ 3-4 andre ledd skal lyde:"),
    ]
    payload = ops[0].payload
    assert payload is not None and _kind_value(payload.kind) == "chapter" and payload.label == "3"
    assert [(_kind_value(child.kind), child.text) for child in payload.children] == [
        ("heading", "Reklame, sponsing m.v.")
    ]
    assert NO_CHAPTER_HEADING_PROVENANCE_TAG in (ops[0].provenance_tags or ())
    assert _w98_unmatched(adjudications) == []

    statute = _w98_statute(
        [
            (
                "3",
                "Kap. 3. Reklame, sponsing",
                [("3-1", "Varighet", ["Reklameinnslag."]), ("3-2", "Særregler", ["Kringkastere."])],
            )
        ]
    )
    result = apply_no_ops(statute, ops[:1], adjudications_out=[])
    chapter = _w98_chapter(result, "3")
    assert _w98_heading(chapter) == "Reklame, sponsing m.v."
    # The chapter's sections are never touched by a heading announcement.
    assert _w98_sections(chapter) == _w98_sections(_w98_chapter(statute, "3"))


def test_no_w98_chapter_heading_lead_reads_every_corpus_word_order_and_refuses_the_rest() -> None:
    assert _no_chapter_heading_lead("Overskriften til kapittel 3 skal lyde:") == ("3", "")
    assert _no_chapter_heading_lead("Overskrifta til kapittel 2 skal lyde:") == ("2", "")
    assert _no_chapter_heading_lead("Overskriften i kapittel 18 skal lyde:") == ("18", "")
    assert _no_chapter_heading_lead("Kapittel 4 overskriften skal lyde:") == ("4", "")
    assert _no_chapter_heading_lead("Overskrifta til kapittel 4 skal lyda:") == ("4", "")
    assert _no_chapter_heading_lead("Overskriften til kapittel XVI skal lyde: Særlige regler") == (
        "XVI",
        "Særlige regler",
    )
    assert _no_chapter_heading_lead("Overskriften til kapittel III A skal lyde:") == ("IIIA", "")
    # Not this grammar: a section heading, a subdivision, a placement aside.
    assert _no_chapter_heading_lead("Overskriften til § 26 skal lyde:") is None
    assert _no_chapter_heading_lead("Kapittel 8 avsnitt III overskriften skal lyde:") is None
    assert (
        _no_chapter_heading_lead("Overskriften til kapittel III A, plassert umiddelbart foran § 17a, skal lyde:")
        is None
    )
    # Inline title lands without consuming the next lead.
    lead = "Overskriften til kapittel 6 skal lyde: Kapittel 6 Taushetsplikt"
    ops, _ = _w98_ops(f'<article class="defaultP">{lead}</article><article class="defaultP">§ 7-1 oppheves.</article>')
    assert [_w98_shape(op) for op in ops] == [
        ("replace", (("chapter", "6"),), None, lead),
        ("repeal", (("section", "7-1"),), None, "§ 7-1 oppheves."),
    ]
    inline_payload = ops[0].payload
    assert inline_payload is not None and inline_payload.children[0].text == "Kapittel 6 Taushetsplikt"
    # Two body nodes behind the lead: the announcement carries more than a heading — typed refusal.
    ops, adjudications = _w98_ops(
        '<article class="defaultP">Overskriften til kapittel 3 skal lyde:</article>'
        '<article class="legalP">Reklame, sponsing m.v.</article><article class="legalP">Og et ledd.</article>'
    )
    assert ops == []
    refusals = [item for item in adjudications if item.kind == NO_PARSE_CHAPTER_HEADING_PAYLOAD_UNRESOLVED]
    assert [(item.detail or {}).get("refusal") for item in refusals] == ["payload_node_count_not_one"]
    assert (refusals[0].detail or {}).get("strict_disposition") == "block"
    # An operative node behind the lead is not a heading.
    ops, adjudications = _w98_ops(
        '<article class="defaultP">Overskriften til kapittel 3 skal lyde:</article>'
        '<article class="defaultP">§ 3-4 andre ledd skal lyde:</article><article class="legalP">Innhold.</article>'
    )
    assert [_action_value(op.action) for op in ops] == ["replace"]
    assert ops[0].target.path == (("section", "3-4"), ("subsection", "2"))
    assert [
        (item.detail or {}).get("refusal")
        for item in adjudications
        if item.kind == NO_PARSE_CHAPTER_HEADING_PAYLOAD_UNRESOLVED
    ] == ["payload_is_not_a_heading"]


def test_no_w98_heading_only_container_replace_merges_instead_of_wiping() -> None:
    """The apply-seam merge generalized from ``section`` to every heading-carrying container.

    W-82's structured chapter-heading payloads (``Kapittel 8 avsnitt III overskriften
    skal lyde:``) reached the bare replace before this and would have wiped the
    subdivision's sections; a heading-only payload over a container now merges.
    """
    statute = _w98_statute([("8", "Kapittel 8. Gammel", [("8-1", "A", ["a"]), ("8-2", "B", ["b"])])])
    op = LegalOperation(
        op_id="no/lovtid/9999-01-01-1:1",
        sequence=1,
        action=StructuralAction.REPLACE,
        target=LegalAddress(path=(("chapter", "8"),)),
        payload=IRNode(
            kind=IRNodeKind.CHAPTER, label="8", children=(IRNode(kind=IRNodeKind.HEADING, text="Kapittel 8. Ny"),)
        ),
        source=OperationSource(
            statute_id="no/lovtid/9999-01-01-1", raw_text="Kapittel 8 overskriften skal lyde:", title="x"
        ),
        provenance_tags=(f"base_act:{_W98_BASE}",),
        group_id="no/lovtid/9999-01-01-1:1",
    )
    result = apply_no_ops(statute, [op], adjudications_out=[])
    chapter = _w98_chapter(result, "8")
    assert _w98_heading(chapter) == "Kapittel 8. Ny"
    assert _w98_sections(chapter) == [("8-1", ["a"]), ("8-2", ["b"])]


# (g) the whole-chapter re-enactment ---------------------------------------------

_W98_CHAPTER_6_LEAD = "Kapittel 6 skal lyde:"
_W98_CHAPTER_6_MEMBERS = (
    f'<article class="defaultP">{_W98_CHAPTER_6_LEAD}</article>'
    "<h2>Kap. 6 Norsk rikskringkasting AS</h2>"
    + _w98_future_article(
        "§6-1",
        "Organisasjon, eierforhold, formål",
        ["Norsk rikskringkasting er et aksjeselskap.", "Staten skal eie alle aksjer i Norsk rikskringkasting AS."],
    )
    + _w98_future_article("§6-2", "Styret", ["Styret har ingen myndighet i løpende programvirksomhet."])
)


def test_no_w98_chapter_reenactment_lead_lowers_the_witness_as_one_chapter_op() -> None:
    """W-91 gap 1, ``no/lovtid/1996-02-02-6``: ``Kapittel 6 skal lyde:`` + title + section carriers."""
    ops, adjudications = _w98_ops(
        _W98_CHAPTER_6_MEMBERS + '<article class="defaultP">§ 7-1 oppheves.</article>',
        source_id="no/lovtid/1996-02-02-6",
    )
    assert [_w98_shape(op) for op in ops] == [
        ("replace", (("chapter", "6"),), None, _W98_CHAPTER_6_LEAD),
        ("repeal", (("section", "7-1"),), None, "§ 7-1 oppheves."),
    ]
    payload = ops[0].payload
    assert payload is not None and _kind_value(payload.kind) == "chapter" and payload.label == "6"
    assert [_kind_value(child.kind) for child in payload.children] == ["heading", "section", "section"]
    assert payload.children[0].text == "Kap. 6 Norsk rikskringkasting AS"
    assert _w98_sections(payload) == [
        (
            "6-1",
            ["Norsk rikskringkasting er et aksjeselskap.", "Staten skal eie alle aksjer i Norsk rikskringkasting AS."],
        ),
        ("6-2", ["Styret har ingen myndighet i løpende programvirksomhet."]),
    ]
    assert _w98_heading(payload.children[1]) == "Organisasjon, eierforhold, formål"
    assert NO_CHAPTER_REENACTMENT_PROVENANCE_TAG in (ops[0].provenance_tags or ())
    assert _w98_unmatched(adjudications) == []
    assert _no_chapter_reenactment_lead("Nytt kapittel 5 A skal lyde:") == ("5A", StructuralAction.INSERT)
    assert _no_chapter_reenactment_lead("Kapittel II a skal lyde:") == ("IIa", StructuralAction.REPLACE)
    assert _no_chapter_reenactment_lead("Kapittel 8 avsnitt III skal lyde:") is None
    assert _no_chapter_reenactment_lead("I kapittel III skal ny § 16-2 lyde:") is None


def test_no_w98_chapter_reenactment_replaces_only_when_every_standing_section_is_carried() -> None:
    """THE over-repeal decision: full carry replaces; an uncarried section refuses the whole op, typed."""
    ops, _ = _w98_ops(_W98_CHAPTER_6_MEMBERS, source_id="no/lovtid/1996-02-02-6")
    carried = _w98_statute(
        [
            ("5", "Kap. 5. Klage", [("5-1", "Klage", ["klage"])]),
            (
                "6",
                "Kap. 6. Norsk rikskringkasting",
                [("6-1", "Stiftelse", ["stiftelse"]), ("6-2", "Styret", ["gammelt styre"])],
            ),
            ("7", "Kap. 7. Rådet", [("7-1", "Rådet", ["rådet"])]),
        ]
    )
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(carried, ops, adjudications_out=adjudications)
    chapter = _w98_chapter(result, "6")
    assert _w98_heading(chapter) == "Kap. 6 Norsk rikskringkasting AS"
    assert _w98_sections(chapter) == [
        (
            "6-1",
            ["Norsk rikskringkasting er et aksjeselskap.", "Staten skal eie alle aksjer i Norsk rikskringkasting AS."],
        ),
        ("6-2", ["Styret har ingen myndighet i løpende programvirksomhet."]),
    ]
    assert [child.label for child in result.body.children] == ["5", "6", "7"]
    assert _w98_chapter(result, "5") == _w98_chapter(carried, "5")
    assert _w98_chapter(result, "7") == _w98_chapter(carried, "7")
    assert not [
        item for item in adjudications if item.kind == NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED
    ]

    # The W-91 witness's own shape: the OCR segmenter fused §§ 6-2–6-5 into § 6-1's
    # body, so the payload carries fewer sections than the chapter holds. Nothing
    # lands, the chapter is byte-identical, and the receipt names what was missing.
    uncarried = _w98_statute(
        [
            (
                "6",
                "Kap. 6. Norsk rikskringkasting",
                [("6-1", "A", ["a"]), ("6-2", "B", ["b"]), ("6-3", "C", ["c"]), ("6-5", "E", ["e"])],
            )
        ]
    )
    adjudications = []
    result = apply_no_ops(uncarried, ops, adjudications_out=adjudications)
    assert _w98_chapter(result, "6") == _w98_chapter(uncarried, "6")
    refusals = [
        item for item in adjudications if item.kind == NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED
    ]
    assert len(refusals) == 1 and refusals[0].blocking
    detail = refusals[0].detail or {}
    assert detail["uncarried_sections"] == ("6-3", "6-5")
    assert detail["carried_sections"] == ("6-1", "6-2")
    assert detail["standing_sections"] == ("6-1", "6-2", "6-3", "6-5")
    conserved = apply_no_ops_conserved(uncarried, ops, adjudications_out=[])
    assert conserved.applied_ops == () and len(conserved.skipped_items) == 1


def test_no_w98_chapter_reenactment_composes_with_the_range_repeal_on_the_1998_witness() -> None:
    """``no/lovtid/1998-05-22-32``: ``§ 5-1 til § 5-6 oppheves.`` then ``Kapittel 5 skal lyde:`` with one § 5-1.

    The kernel lands the six REPEALs before the chapter REPLACE, so the chapter
    stands empty when the re-enactment is evaluated and nothing is uncarried.
    """
    members = (
        '<article class="defaultP">§ 5-1 til § 5-6 oppheves.</article>'
        '<article class="defaultP">Kapittel 5 skal lyde:</article>'
        "<h2>Kap. 5 Beriktigelse</h2>"
        + _w98_future_article(
            "§5-1",
            "",
            [
                "Enhver fysisk eller juridisk person har rett til å beriktige.",
                "Retten gjelder overfor kringkastingsselskap.",
            ],
        )
        + '<article class="defaultP">§ 6-5 oppheves.</article>'
    )
    ops, adjudications = _w98_ops(members, source_id="no/lovtid/1998-05-22-32")
    assert [_action_value(op.action) for op in ops] == ["repeal"] * 6 + ["replace", "repeal"]
    assert _w98_unmatched(adjudications) == []
    statute = _w98_statute(
        [
            (
                "5",
                "Kap. 5. Klage over kringkastingsprogram",
                [(f"5-{n}", f"S{n}", [f"gammel {n}"]) for n in range(1, 7)],
            ),
            ("6", "Kap. 6. NRK", [("6-5", "Teknisk", ["teknisk"])]),
        ]
    )
    adjudications = []
    result = apply_no_ops(statute, ops, adjudications_out=adjudications)
    chapter = _w98_chapter(result, "5")
    assert _w98_heading(chapter) == "Kap. 5 Beriktigelse"
    assert _w98_sections(chapter) == [
        (
            "5-1",
            [
                "Enhver fysisk eller juridisk person har rett til å beriktige.",
                "Retten gjelder overfor kringkastingsselskap.",
            ],
        )
    ]
    assert _w98_sections(_w98_chapter(result, "6")) == []
    assert not [
        item for item in adjudications if item.kind == NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED
    ]


def test_no_w98_new_chapter_inserts_sorted_and_refuses_an_occupied_label() -> None:
    lead = "Nytt kapittel 5 A skal lyde:"
    members = (
        f'<article class="defaultP">{lead}</article>'
        '<span class="futuretitle">Kap. 5 A. Videodelingsplattformer</span>'
        + _w98_future_article("§5A-1", "Jurisdiksjon", ["Kongen kan gi forskrift."])
    )
    ops, _ = _w98_ops(members)
    assert [_w98_shape(op) for op in ops] == [("insert", (("chapter", "5A"),), None, lead)]
    statute = _w98_statute([("5", "Kap. 5", [("5-1", "A", ["a"])]), ("6", "Kap. 6", [("6-1", "B", ["b"])])])
    result = apply_no_ops(statute, ops, adjudications_out=[])
    assert [child.label for child in result.body.children] == ["5", "5A", "6"]
    assert _w98_heading(_w98_chapter(result, "5A")) == "Kap. 5 A. Videodelingsplattformer"
    assert _w98_sections(_w98_chapter(result, "5A")) == [("5A-1", ["Kongen kan gi forskrift."])]
    # Occupied: the standing chapter is in-force law and is not the thing to delete.
    occupied = _w98_statute(
        [("5", "Kap. 5", [("5-1", "A", ["a"])]), ("5A", "Kap. 5 A. Gammel", [("5A-1", "Z", ["z"])])]
    )
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(occupied, ops, adjudications_out=adjudications)
    assert _w98_chapter(result, "5A") == _w98_chapter(occupied, "5A")
    refusals = [
        item for item in adjudications if item.kind == NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED
    ]
    assert len(refusals) == 1
    assert (refusals[0].detail or {}).get("production") == NO_CHAPTER_REENACTMENT_PROVENANCE_TAG
    assert not [item for item in adjudications if item.kind == "no_replay_insert_occupied_target_replaced"]


def test_no_w98_chapter_reenactment_reads_the_2001_header_shape_and_stops_at_the_next_lead() -> None:
    """Lovdata's 2001 shape: a ``defaultP`` ``§ X. Title`` header and its ledd, no ``futureLegalArticle``."""
    members = (
        '<article class="defaultP">Nytt kapittel 5B skal lyde:</article>'
        '<article class="defaultP">Kap. 5B. Energiplanlegging</article>'
        '<article class="defaultP">§ 5B-1. (Energiplanlegging)</article>'
        '<article class="legalP">Den som har konsesjon plikter å delta i energiplanlegging.</article>'
        '<article class="legalP">Departementet gir forskrifter om planleggingen.</article>'
        '<article class="defaultP">§ 5B-2. (Rasjonering)</article>'
        '<article class="legalP">Departementet kan sette i verk rasjonering.</article>'
        '<article class="defaultP">§ 6-1 fjerde ledd oppheves.</article>'
    )
    ops, adjudications = _w98_ops(members)
    assert [_w98_shape(op) for op in ops] == [
        ("insert", (("chapter", "5B"),), None, "Nytt kapittel 5B skal lyde:"),
        ("repeal", (("section", "6-1"), ("subsection", "4")), None, "§ 6-1 fjerde ledd oppheves."),
    ]
    payload = ops[0].payload
    assert payload is not None and payload.children[0].text == "Kap. 5B. Energiplanlegging"
    assert _w98_sections(payload) == [
        (
            "5B-1",
            [
                "Den som har konsesjon plikter å delta i energiplanlegging.",
                "Departementet gir forskrifter om planleggingen.",
            ],
        ),
        ("5B-2", ["Departementet kan sette i verk rasjonering."]),
    ]
    assert _w98_heading(payload.children[1]) == "(Energiplanlegging)"
    assert _w98_unmatched(adjudications) == []


def test_no_w98_chapter_reenactment_refuses_what_it_cannot_read_whole() -> None:
    # A subdivision heading after sections have started is a structure this reader does not model.
    members = (
        '<article class="defaultP">Nytt kapittel 7 skal lyde:</article>'
        '<span class="futuretitle">Kapittel 7. Sakshandsaminga</span>'
        + _w98_future_article("§48", "Det beste for barnet", ["Avgjerder."])
        + '<span class="futuretitle">II. Mekling</span>'
        + _w98_future_article("§51", "Mekling", ["Foreldre."])
    )
    ops, adjudications = _w98_ops(members)
    assert ops == []
    refusals = [item for item in adjudications if item.kind == NO_PARSE_CHAPTER_REENACTMENT_PAYLOAD_UNRESOLVED]
    assert [(item.detail or {}).get("refusal") for item in refusals] == ["subdivision_heading_unsupported"]
    assert (refusals[0].detail or {}).get("member") == "II. Mekling"
    assert (refusals[0].detail or {}).get("strict_disposition") == "block"
    # A ``Nytt kapittel`` that carries only a title refuses (an empty container proves nothing);
    # the same shape on a REPLACE is a heading-only payload the apply seam merges.
    ops, adjudications = _w98_ops(
        '<article class="defaultP">Nytt kapittel 3 skal lyde:</article>'
        '<span class="futuretitle">Kapittel 3 Stortingets ansvarskommisjon</span>'
        '<article class="defaultP">§ 30 skal lyde:</article><article class="legalP">Når Stortinget ber om det.</article>'
    )
    assert [_action_value(op.action) for op in ops] == ["replace"]
    assert ops[0].target.path == (("section", "30"),)
    assert [
        (item.detail or {}).get("refusal")
        for item in adjudications
        if item.kind == NO_PARSE_CHAPTER_REENACTMENT_PAYLOAD_UNRESOLVED
    ] == ["chapter_carried_no_section"]
    ops, adjudications = _w98_ops(
        '<article class="defaultP">Kapittel 7 skal lyde:</article>'
        '<span class="futuretitle">Kapittel 7. Arbeidsmiljøutvalg</span>'
        '<article class="defaultP">§ 10-4 andre ledd skal lyde:</article><article class="legalP">For arbeid.</article>'
    )
    assert [_w98_shape(op)[:2] for op in ops] == [
        ("replace", (("chapter", "7"),)),
        ("replace", (("section", "10-4"), ("subsection", "2"))),
    ]
    title_only = ops[0].payload
    assert title_only is not None
    assert [(_kind_value(child.kind), child.text) for child in title_only.children] == [
        ("heading", "Kapittel 7. Arbeidsmiljøutvalg")
    ]
    # Body text with no section open (folketrygdloven's chapter index paragraph) refuses.
    ops, adjudications = _w98_ops(
        '<article class="defaultP">Kapittel 14 skal lyde:</article>'
        '<span class="futuretitle">Kapittel 14 Ytelser ved svangerskap</span>'
        '<article class="legalP">Bestemmelser om formål står i § 14-1.</article>'
        + _w98_future_article("§14-1", "Formål", ["Formålet."])
    )
    assert ops == []
    assert [
        (item.detail or {}).get("refusal")
        for item in adjudications
        if item.kind == NO_PARSE_CHAPTER_REENACTMENT_PAYLOAD_UNRESOLVED
    ] == ["body_outside_section"]


# (h) the unqualified, self-addressed single-ledd shift ---------------------------


def test_no_w98_unqualified_self_addressed_ledd_shift_lowers_the_witness_through_w66() -> None:
    """W-91 gap 7, ``no/lovtid/1993-12-17-126``: ``§ 2-1 sjette ledd blir nytt fjerde ledd.``"""
    lead = "§ 2-1 sjette ledd blir nytt fjerde ledd."
    assert _no_ledd_set_relabel_pairs(lead) == ("2-1", [(6, 4)], "unqualified_self_addressed")
    assert _no_ledd_set_relabel_pairs("§ 4 femte ledd blir fjerde ledd.") == ("4", [(5, 4)], "unqualified_self_addressed")
    assert _no_ledd_set_relabel_pairs("§ 3 i tredje ledd blir nytt fjerde ledd.") == (
        "3i",
        [(3, 4)],
        "unqualified_self_addressed",
    )
    # The qualified readers are tried first and are untouched.
    assert _no_ledd_set_relabel_pairs("Nåværende § 2-1 sjette ledd blir nytt fjerde ledd.") == ("2-1", [(6, 4)], "shipped")
    # W-66's refusals stand: no section of its own, a set, a self-map, an ordinal outside the vocabulary.
    assert _no_ledd_set_relabel_pairs("Femte ledd blir nytt sjette ledd.") is None
    assert _no_ledd_set_relabel_pairs("§ 7 fjerde og femte ledd blir femte og sjette ledd.") is None
    assert _no_ledd_set_relabel_pairs("§ 7 femte ledd blir femte ledd.") is None
    assert _no_ledd_set_relabel_pairs("§ 7 sjuande ledd blir nytt sjette ledd.") is None
    ops, adjudications = _w98_ops(f'<article class="defaultP">{lead}</article>', source_id="no/lovtid/1993-12-17-126")
    assert [_w98_shape(op) for op in ops] == [
        ("renumber", (("section", "2-1"), ("subsection", "6")), (("section", "2-1"), ("subsection", "4")), lead),
    ]
    assert NO_LEDD_SET_RELABEL_PROVENANCE_TAG in (ops[0].provenance_tags or ())
    assert ops[0].witness_rule_id == "no_section_renumber_relabel"
    assert _w98_unmatched(adjudications) == []
    # W-66's occupied-destination guard is what makes the reading safe: a standing
    # fourth ledd refuses the leg rather than being cleared.
    statute = _w98_statute([("2", "Kap. 2", [("2-1", "Konsesjon", ["én", "to", "tre", "fire", "fem", "seks"])])])
    adjudications = []
    result = apply_no_ops(statute, ops, adjudications_out=adjudications)
    assert _w98_sections(_w98_chapter(result, "2")) == _w98_sections(_w98_chapter(statute, "2"))
    assert [item.kind for item in adjudications if item.kind.startswith("no_replay_ledd_set_relabel")] == [
        "no_replay_ledd_set_relabel_occupied_destination_refused"
    ]
    # And with the fourth and fifth ledd repealed first (the witness act's own order), it lands.
    repeal_ops, _ = _w98_ops(
        '<article class="defaultP">§ 2-1 fjerde og femte ledd oppheves.</article>', source_id="no/lovtid/1993-12-17-126"
    )
    result = apply_no_ops(statute, [*repeal_ops, *ops], adjudications_out=[])
    assert _w98_sections(_w98_chapter(result, "2")) == [("2-1", ["én", "to", "tre", "seks"])]
    section = next(child for child in _w98_chapter(result, "2").children if _kind_value(child.kind) == "section")
    assert [ledd.label for ledd in section.children if _kind_value(ledd.kind) == "subsection"] == ["1", "2", "3", "4"]


# (i) the nynorsk ledd repeal ----------------------------------------------------


def test_no_w98_nynorsk_ledd_repeal_lowers_the_witness_and_declines_what_it_cannot_name() -> None:
    """W-91 gap 9, ``no/lovtid/1994-06-24-45``: ``§ 6-1 tredje ledd vert oppheva.``"""
    lead = "§ 6-1 tredje ledd vert oppheva."
    ops, adjudications = _w98_ops(f'<article class="defaultP">{lead}</article>', source_id="no/lovtid/1994-06-24-45")
    assert [_w98_shape(op) for op in ops] == [("repeal", (("section", "6-1"), ("subsection", "3")), None, lead)]
    assert _w98_unmatched(adjudications) == []
    assert _no_nynorsk_ledd_repeal_targets("§ 2-1 sjette ledd blir oppheva.") == ("2-1", [6])
    assert _no_nynorsk_ledd_repeal_targets("§ 3 tredje ledd opphevast.") == ("3", [3])
    assert _no_nynorsk_ledd_repeal_targets("§ 5-2 tredje og fjerde ledd blir oppheva.") == ("5-2", [3, 4])
    assert _no_nynorsk_ledd_repeal_targets("§ 15-2 noverande fjerde ledd blir oppheva.") == ("15-2", [4])
    assert _no_nynorsk_ledd_repeal_targets("§ 107 b fjerde ledd blir oppheva.") == ("107b", [4])
    # Declined: a counted address, a punktum member beside the ledd, and bokmål (the shipped branch's).
    assert _no_nynorsk_ledd_repeal_targets("§ 20 siste ledd blir oppheva.") is None
    assert _no_nynorsk_ledd_repeal_targets("§ 9-3 første ledd første punktum og andre ledd blir oppheva.") is None
    assert _no_nynorsk_ledd_repeal_targets("§ 6-1 tredje ledd oppheves.") is None
    # ``siste ledd`` keeps its LOUD refusal — the reason the shipped verb was not widened.
    ops, adjudications = _w98_ops('<article class="defaultP">§ 20 siste ledd blir oppheva.</article>')
    assert ops == []
    assert _w98_unmatched(adjudications) == ["§ 20 siste ledd blir oppheva."]


# --- W-99: pre-2001 house-style citations and the address-after-citation lead ---


def _w99_amendment(lead: str, payload: str = "Ny setning.") -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html lang="nb">
  <body>
    <dd class="changesToDocuments"><ul><li>lov/1992-12-04-127</li></ul></dd>
    <dd class="dateInForce">1999-01-01</dd>
    <main>
      <section data-name="kapI">
        <article class="legalP">{lead}</article>
        <article class="legalP">{payload}</article>
      </section>
    </main>
  </body>
</html>
""".encode("utf-8")


def test_no_law_citation_admits_the_period_less_day_of_pre_2001_house_style() -> None:
    """W-99 print-era witness: 1997 nr. 44 item 59, as printed in Norsk Lovtidend.

    The 1997 house style writes "lov 4 desember 1992 nr 127" — no period after
    the day. The shipped date grammar required it, so this lead resolved no law
    and, because the ``skal … lyde`` span is six tokens, was not even refused.
    """
    grouped = iter_no_document_change_ops(
        _w99_amendment(
            "59. I lov 4 desember 1992 nr 127 om kringkasting skal § 6-1 første ledd annet punktum lyde:",
            "Lov om aksjeselskaper gjelder for Norsk rikskringkasting AS om ikke annet følger av denne lov.",
        ),
        "no/lovtid/1997-06-13-44",
    )
    assert [(base_id, [(op.action, op.target.path) for op in ops]) for base_id, ops in grouped] == [
        (
            "no/lov/1992-12-04-127",
            [(StructuralAction.REPLACE, (("section", "6-1"), ("subsection", "1"), ("sentence", "2")))],
        )
    ]


def test_no_address_after_citation_lead_nominative_with_ordinal() -> None:
    """W-99 print-era witness: 1998 nr. 56 item 47 — ``Lov <cite> om X § … skal lyde:``."""
    grouped = iter_no_document_change_ops(
        _w99_amendment(
            "47. Lov 4. desember 1992 nr. 127 om kringkasting § 8-2 fjerde ledd annet punktum skal lyde:",
            "Til dette formål kan det kreves innsyn i registrerte regnskapsopplysninger.",
        ),
        "no/lovtid/1998-07-17-56",
    )
    assert [(base_id, [(op.action, op.target.path) for op in ops]) for base_id, ops in grouped] == [
        (
            "no/lov/1992-12-04-127",
            [(StructuralAction.REPLACE, (("section", "8-2"), ("subsection", "4"), ("sentence", "2")))],
        )
    ]


def test_no_address_after_citation_lead_prepositional_and_insert_forms() -> None:
    """The corpus spellings of the same production (`2005-06-17-67`, `2018-06-01-23`)."""
    assert _extract_no_embedded_multi_act_lead(
        "12. I lov 8. juni 1984 nr. 59 om fordringshavernes dekningsrett (dekningsloven) § 9-4 annet ledd skal lyde:"
    ) == ("no/lov/1984-06-08-59", "§ 9-4 annet ledd skal lyde:")
    assert _extract_no_embedded_multi_act_lead(
        "5. Lov 13. mai 1988 nr. 26 om inkassovirksomhet og annen inndriving av forfalte pengekrav "
        "§ 28 nytt tredje ledd skal lyde:"
    ) == ("no/lov/1988-05-13-26", "§ 28 nytt tredje ledd skal lyde:")
    # A payload Lovdata ran on after the colon rides along; the lead is still a switch (`2003-12-19-124` item 5).
    assert _extract_no_embedded_multi_act_lead(
        "5. Lov 13. juni 1997 nr. 42 om Kystvakten § 9 første ledd bokstav b skal lyde: "
        "lov om matproduksjon og mattrygghet mv. (matloven)."
    ) == (
        "no/lov/1997-06-13-42",
        "§ 9 første ledd bokstav b skal lyde: lov om matproduksjon og mattrygghet mv. (matloven).",
    )
    # The shipped ``skal § …`` spelling is untouched: same act, same rebuilt lead.
    assert _extract_no_embedded_multi_act_lead(
        "206. I lov 17. desember 2004 nr. 99 om kvoteplikt og handel med kvoter for utslipp av klimagasser "
        "(klimakvoteloven) skal § 21 nytt annet punktum lyde:"
    ) == ("no/lov/2004-12-17-99", "§ 21 nytt annet punktum skal lyde:")


def test_no_address_after_citation_lead_does_not_fire_on_nearby_shapes() -> None:
    # A bare citation acted on as a whole, and a part announcement: neither closes with ``skal lyde``.
    assert _extract_no_embedded_multi_act_lead("Lov 22. mai 1902 nr. 13 § 107 oppheves.") is None
    assert _extract_no_embedded_multi_act_lead("Lov 20. mai 2005 nr. 28 om straff endres slik:") is None
    # A W-36 run-on PART ANNOUNCEMENT: the colon before the ``§`` keeps it the announcement resolver's.
    assert (
        _extract_no_embedded_multi_act_lead(
            "I lov 26. mars 1999 nr. 14 om skatt av formue og inntekt gjøres følgende endringer: "
            "§ 4-1 andre ledd skal lyde: (2) For skattyter med avvikende regnskapsår gjelder følgende."
        )
        is None
    )
    # A repeal-then-replace item: the address span may not cross a sentence end (`2003-06-20-45` item 120).
    assert (
        _extract_no_embedded_multi_act_lead(
            "120. I lov 25. juni 1999 nr. 46 om finansavtaler og finansoppdrag blir § 1 andre ledd bokstav g "
            "oppheva. Bokstav f skal lyde: institusjon som loven gjelder for etter forskrift."
        )
        is None
    )
    # The day's period is optional, but a month name, a year and ``nr N`` are not.
    assert _extract_no_embedded_multi_act_lead("I lov 4 dsm 1992 nr 127 om kringkasting skal § 6-1 lyde:") is None


def test_no_unstructured_lead_looks_operative_admits_deep_skal_section_address() -> None:
    """W-99: a ``skal § <address> lyde`` lead is operative at any address depth."""
    assert _no_unstructured_lead_looks_operative(
        "I lov 4 desember 1992 nr 127 om kringkasting skal § 6-1 første ledd annet punktum lyde:"
    )
    assert _no_unstructured_lead_looks_operative("skal ny § 6-1 første ledd annet punktum nr. 3 bokstav a lyde:")
    # Without the ``§`` right after ``skal`` the widened span does not reach prose.
    assert not _no_unstructured_lead_looks_operative("Reglene skal i den grad det er nødvendig lyde likt.")


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_address_after_citation_rebinds_skipssikkerhetsloven_from_sjoloven() -> None:
    """W-99 corpus witness: `no/lovtid/2008-06-27-72` part II.

    "Lov 16. februar 2007 nr. 9 om skipssikkerhet (skipssikkerhetsloven) § 47
    annet ledd skal lyde:" — the citation was walked past as prose and the
    op bound to sjøloven, the previous part's act. The lead is a law switch.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2008-06-27-72", _NO_FARCHIVE_PATH)
    assert html_bytes is not None
    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2008-06-27-72"))

    assert [(op.action, op.target.path) for op in grouped["no/lov/2007-02-16-9"]] == [
        (StructuralAction.REPLACE, (("section", "47"), ("subsection", "2")))
    ]
    assert not any(
        "skipssikkerhet" in (op.source.raw_text if op.source is not None else "")
        for op in grouped["no/lov/1994-06-24-39"]
    )
    # The two sibling items of the same shape enter with it.
    assert ("section", "26b") in {op.target.path[0] for op in grouped["no/lov/1998-06-26-47"]}
    assert ("section", "9") in {op.target.path[0] for op in grouped["no/lov/1987-06-12-48"]}


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_period_less_part_lead_binds_sykepleierpensjonsloven() -> None:
    """W-99 corpus witness: `no/lovtid/2019-06-21-26`.

    "I lov 22 juni 1962 nr. 12 om pensjonsordning for sykepleiere gjøres
    følgende endringer:" — no period after the day, so the part resolved no
    act and its ops rode on samordningsloven from the part before.
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2019-06-21-26", _NO_FARCHIVE_PATH)
    assert html_bytes is not None
    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2019-06-21-26"))

    sykepleier = grouped["no/lov/1962-06-22-12"]
    assert (StructuralAction.INSERT, (("chapter", "4a"),)) in {(op.action, op.target.path) for op in sykepleier}
    assert (StructuralAction.INSERT, (("section", "10d"),)) in {(op.action, op.target.path) for op in sykepleier}
    assert not any(("chapter", "4a") in op.target.path for op in grouped["no/lov/1957-07-06-26"])


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_address_after_citation_with_inline_payload_binds_kystvaktloven() -> None:
    """W-99 corpus witness: `no/lovtid/2003-12-19-124` items 4–6.

    Item 5 runs its payload on after the colon; without inline admission the
    lead was no switch and § 9 bound to item 4's act (oppdrettsloven).
    """
    html_bytes = load_no_amendment_bytes("no/lovtid/2003-12-19-124", _NO_FARCHIVE_PATH)
    assert html_bytes is not None
    grouped = dict(iter_no_document_change_ops(html_bytes, "no/lovtid/2003-12-19-124"))

    assert [(op.action, op.target.path) for op in grouped["no/lov/1997-06-13-42"]] == [
        (StructuralAction.REPLACE, (("section", "9"), ("subsection", "1"), ("item", "b")))
    ]
    assert [(op.action, op.target.path) for op in grouped["no/lov/2000-12-21-118"]] == [
        (StructuralAction.REPLACE, (("section", "3"), ("subsection", "2")))
    ]
    assert not any(op.target.path[0] == ("section", "9") for op in grouped.get("no/lov/1985-06-14-68", []))


# ── W-101: the structured chapter address ────────────────────────────────────


def _w101_change(change_node: str, *, source_id: str = "no/lovtid/2025-02-28-2", base: str = _W98_BASE):
    adjudications: list[CompileAdjudication] = []
    grouped = dict(
        iter_no_document_change_ops(
            _w79_change_html(change_node=change_node, base=base.removeprefix("no/")),
            source_id,
            adjudications_out=adjudications,
        )
    )
    return list(grouped.get(base, [])), adjudications


def _w101_kinds(adjudications: Sequence[CompileAdjudication], kind: str) -> list[dict]:
    return [dict(item.detail or {}) for item in adjudications if item.kind == kind]


_W101_NEW_CHAPTER_BLOCK = (
    f'<article class="change" data-add-new-part="{_W98_BASE.removeprefix("no/")}/kap5A '
    f'{_W98_BASE.removeprefix("no/")}/§5a-1 {_W98_BASE.removeprefix("no/")}/§5a-2">'
    '<article class="defaultP">Nytt kapittel 5 A skal lyde:</article>'
    '<span class="futuretitle">Kap. 5 A. Videodelingsplattformtjenester</span>'
    + _w82_future_article("§5A-1", "Jurisdiksjon", "Kongen kan gi forskrift.")
    + _w82_future_article("§5A-2", "Registreringsplikt", "Tilbydere plikter å registrere seg.")
    + "</article>"
)


def test_no_w101_kap_step_lowers_only_as_the_last_segment() -> None:
    """Lovdata's ``kap<label>`` step, in every case the corpus spells it, and the two forms it must not read."""
    assert lovdata_path_to_address("lov/1992-12-04-127/kap5A") == LegalAddress(path=(("chapter", "5A"),))
    assert lovdata_path_to_address("lov/2014-06-20-49/kapIII") == LegalAddress(path=(("chapter", "III"),))
    assert lovdata_path_to_address("lov/1981-05-22-25/kap17d") == LegalAddress(path=(("chapter", "17d"),))
    assert lovdata_path_to_address("lov/2010-06-25-45/kapVIIA") == LegalAddress(path=(("chapter", "VIIA"),))
    assert lovdata_path_to_address("lov/1949-07-28-26/kap5b") == LegalAddress(path=(("chapter", "5b"),))
    # Something INSIDE the chapter: not this step's to read.
    assert lovdata_path_to_address("lov/2007-06-29-75/kap12/avsnitt/II") is None
    assert lovdata_path_to_address("lov/1998-07-17-56/kap3/overskrift") is None
    # The older ``KAPITTEL_`` form is untouched.
    assert lovdata_path_to_address("lov/1999-03-26-14/KAPITTEL_19-1") == LegalAddress(path=(("chapter", "19-1"),))


@pytest.mark.parametrize(
    ("lead", "label", "expected"),
    [
        ("Nytt kapittel 5 A skal lyde:", "5A", True),
        ("Nytt kapittel 5A skal lyde:", "5A", True),
        ("Kapittel 34, 35 og 36 oppheves.", "35", True),
        ("Kapittel 34, 35 og 36 oppheves.", "36", True),
        ("Overskriften i kapittel III skal lyde:", "III", True),
        ("Nytt kapittel VII A skal lyde:", "VIIA", True),
        ("I fjerde del skal nytt kapittel 17 d lyde:", "17d", True),
        ("Kapitteloverskriften til kapittel 8 skal lyde:", "8", True),
        ("Kapittel 4 kapitteloverskriften skal lyde:", "4", True),
        ("Kap. 15 b skal lyde:", "15b", True),
        ("Nytt kapittel 5 b med §§ 26 m til 26 u skal lyde:", "5b", True),
        # A longer label is not the shorter one.
        ("Kapittel 11 med §§ 218, 219 og 220 skal lyde:", "1", False),
        # The token means a PART, not a chapter.
        ("Lovens del II oppheves. Del III blir del II.", "II", False),
        ("Under del II om endringer i lov om pensjonsordning skal § 3 første ledd lyde:", "II", False),
        # A new heading before an existing section names no chapter.
        ("Ny kapitteloverskrift før § 1 skal lyde:", "1", False),
        # ``I`` the preposition is not a roman suffix.
        ("I kapittel I i loven skal overskriften lyde:", "Ii", False),
        ("I kapittel I i loven skal overskriften lyde:", "I", True),
        # An avsnitt address (Lovdata's ``kap8-3``) is not chapter 8.
        ("Kapittel 8 avsnitt III overskriften skal lyde:", "8-3", False),
    ],
)
def test_no_w101_lead_names_chapter(lead: str, label: str, expected: bool) -> None:
    assert _no_lead_names_chapter(lead, label) is expected


def test_no_w101_lead_announces_subdivision() -> None:
    assert _no_lead_announces_subdivision("I kapittel 9 skal avsnitt VIII lyde:")
    assert _no_lead_announces_subdivision("Ny deloverskrift til §§ 18-2 til 18-8 skal lyde:")
    assert _no_lead_announces_subdivision("Kapittel 12 avsnitt II oppheves.")
    assert not _no_lead_announces_subdivision("Nytt kapittel 5 A skal lyde:")
    assert not _no_lead_announces_subdivision("Overskriften til kapittel 13 skal lyde:")


def test_no_w101_new_chapter_block_mints_the_chapter_first_and_scopes_its_cased_sections() -> None:
    """The witness shape: ``kap5A`` + two lower-case section tokens + a future title + two carriers."""
    ops, adjudications = _w101_change(_W101_NEW_CHAPTER_BLOCK)
    assert [(_action_value(op.action), op.target.path) for op in ops] == [
        ("insert", (("chapter", "5A"),)),
        ("insert", (("chapter", "5A"), ("section", "5A-1"))),
        ("insert", (("chapter", "5A"), ("section", "5A-2"))),
    ]
    chapter_op = ops[0]
    assert chapter_op.payload is not None
    assert (_kind_value(chapter_op.payload.kind), chapter_op.payload.label, chapter_op.payload.text) == (
        "chapter",
        "5A",
        "",
    )
    assert [(_kind_value(c.kind), c.text) for c in chapter_op.payload.children] == [
        ("heading", "Kap. 5 A. Videodelingsplattformtjenester")
    ]
    assert NO_CHAPTER_REENACTMENT_PROVENANCE_TAG in chapter_op.provenance_tags
    # The sections carry the carrier's case on the PAYLOAD too, so the landed
    # label is the consolidation's ``5A-1``, not the attribute's ``5a-1``.
    assert [op.payload.label for op in ops[1:] if op.payload is not None] == ["5A-1", "5A-2"]
    assert all(NO_CHAPTER_REENACTMENT_PROVENANCE_TAG not in op.provenance_tags for op in ops[1:])
    assert all(NO_NEW_CHAPTER_SECTION_PROVENANCE_TAG in op.provenance_tags for op in ops[1:])
    cased = _w101_kinds(adjudications, NO_PARSE_STRUCTURED_SECTION_LABEL_CASED_FROM_CARRIER)
    assert [(d["attribute_label"], d["carrier_label"], d["blocking"]) for d in cased] == [
        ("5a-1", "5A-1", False),
        ("5a-2", "5A-2", False),
    ]
    scoped = _w101_kinds(adjudications, NO_PARSE_STRUCTURED_SECTION_TARGET_SCOPED_TO_NEW_CHAPTER)
    assert [(d["unscoped_target"], d["chapter"], d["blocking"]) for d in scoped] == [
        ("section:5A-1", "5A", False),
        ("section:5A-2", "5A", False),
    ]
    assert not _w101_kinds(adjudications, NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED)
    assert not _w101_kinds(adjudications, "no_parse_unresolved_structured_target_skipped")


def test_no_w101_heading_only_chapter_replace_and_chapter_repeal_after_its_sections() -> None:
    base = _W98_BASE.removeprefix("no/")
    ops, adjudications = _w101_change(
        f'<article class="change" data-change-part="{base}/kap13">'
        '<article class="defaultP">Overskriften til kapittel 13 skal lyde:</article>'
        '<span class="futuretitle">Kapittel 13. Ordenstiltak og skadeførebygging m.m.</span>'
        "</article>"
    )
    assert [(_action_value(op.action), op.target.path) for op in ops] == [("replace", (("chapter", "13"),))]
    assert ops[0].payload is not None
    assert [(_kind_value(c.kind), c.text) for c in ops[0].payload.children] == [
        ("heading", "Kapittel 13. Ordenstiltak og skadeførebygging m.m.")
    ]
    # A REPLACE carries no re-enactment tag: it merges its heading over the
    # standing chapter (W-98 (f)) and must not trip the uncarried-sections guard.
    assert NO_CHAPTER_REENACTMENT_PROVENANCE_TAG not in ops[0].provenance_tags
    assert not _w101_kinds(adjudications, NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED)

    ops, adjudications = _w101_change(
        f'<article class="change" data-repeal-part="{base}/kap34 {base}/kap35 {base}/§34-1 {base}/§35-1">'
        '<article class="defaultP">Kapittel 34 og 35 oppheves.</article>'
        "</article>"
    )
    # The chapters go AFTER the sections the same block repeals, so neither
    # section repeal finds its target already gone.
    assert [(_action_value(op.action), op.target.path, op.payload) for op in ops] == [
        ("repeal", (("section", "34-1"),), None),
        ("repeal", (("section", "35-1"),), None),
        ("repeal", (("chapter", "34"),), None),
        ("repeal", (("chapter", "35"),), None),
    ]
    assert not _w101_kinds(adjudications, NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED)


@pytest.mark.parametrize(
    ("change_node", "reason", "surviving_targets"),
    [
        (
            '<article class="change" data-repeal-part="{base}/kapII">'
            '<article class="defaultP">Lovens del II oppheves. Del III blir del II.</article></article>',
            "lead_disagrees",
            [],
        ),
        (
            '<article class="change" data-add-new-part="{base}/kap1">'
            '<article class="defaultP">Ny kapitteloverskrift før § 1 skal lyde:</article>'
            '<span class="futuretitle">Kapittel 1 Avtalefestet pensjon</span></article>',
            "lead_disagrees",
            [],
        ),
        (
            '<article class="change" data-change-part="{base}/kapII {base}/§3/ledd/1">'
            '<article class="defaultP">Under del II om endringer i lov om pensjonsordning skal § 3 første ledd lyde:</article>'
            '<article class="legalP">Medlemmer har rett til pensjon.</article></article>',
            "lead_disagrees",
            [(("section", "3"), ("subsection", "1"))],
        ),
        (
            '<article class="change" data-change-part="{base}/kap9 {base}/§9-39">'
            '<article class="defaultP">I kapittel 9 skal avsnitt VIII lyde:</article>'
            '<span class="futuretitle">VIII Kapitalforhold mv.</span>'
            + _w82_future_article("§9-39", "Verdipapirisering", "Foretaket kan verdipapirisere.")
            + "</article>",
            "subdivision_announced",
            [(("section", "9-39"),)],
        ),
        (
            '<article class="change" data-change-part="{base}/kapXIV">'
            '<article class="defaultP">Nytt kapittel XVII (nåværende kapittel XIV) skal lyde:</article>'
            '<span class="futuretitle">Kapittel XVII. Tvangsakkord</span>'
            + _w82_future_article("§17-1", "Virkeområde", "Kapitlet gjelder tvangsakkord.")
            + "</article>",
            "carriers_unaccounted",
            [],
        ),
        (
            '<article class="change" data-change-part="{base}/kap15">'
            '<article class="defaultP">I innholdsfortegnelsen i kapittel 15 skal nytt andre strekpunkt lyde:</article>'
            '<li data-li-identifier="-" data-name="-">forholdet til folketrygden</li></article>',
            "heading_payload_missing",
            [],
        ),
        (
            '<article class="change" data-move-part="{base}/kap6;;{base}/kap4">'
            '<article class="defaultP">Nåværende kapittel 6 blir kapittel 4.</article></article>',
            "renumber_unsupported",
            [],
        ),
    ],
)
def test_no_w101_chapter_token_refusals_are_typed_and_leave_the_sections_as_before(
    change_node: str, reason: str, surviving_targets: list
) -> None:
    base = _W98_BASE.removeprefix("no/")
    ops, adjudications = _w101_change(change_node.format(base=base))
    refused = _w101_kinds(adjudications, NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED)
    assert [d["reason"] for d in refused] == [reason]
    assert refused[0]["blocking"] is True
    assert refused[0]["phase"] == "parse"
    assert [op.target.path for op in ops] == surviving_targets
    assert not [op for op in ops if op.target.leaf_kind() == "chapter"]


def test_no_w101_an_avsnitt_segment_and_a_bare_kap_stay_unresolved() -> None:
    base = _W98_BASE.removeprefix("no/")
    ops, adjudications = _w101_change(
        f'<article class="change" data-repeal-part="{base}/kap12/avsnitt/II">'
        '<article class="defaultP">Kapittel 12 avsnitt II oppheves.</article></article>'
    )
    assert ops == []
    assert [item.kind for item in adjudications] == ["no_parse_unresolved_structured_target_skipped"]
    assert not _w101_kinds(adjudications, NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED)


def test_no_w101_carrier_case_is_taken_only_when_the_forms_differ_by_case_alone() -> None:
    base = _W98_BASE.removeprefix("no/")
    # A genuinely lower-case chapter-lettered section (``§ 13a-6``) keeps its label.
    ops, adjudications = _w101_change(
        f'<article class="change" data-change-part="{base}/§13a-6">'
        '<article class="defaultP">§ 13a-6 skal lyde:</article>'
        + _w82_future_article("§13a-6", "Tilsyn", "Tilsynet føres av departementet.")
        + "</article>"
    )
    assert [op.target.path for op in ops] == [(("section", "13a-6"),)]
    assert not _w101_kinds(adjudications, NO_PARSE_STRUCTURED_SECTION_LABEL_CASED_FROM_CARRIER)
    # Two carriers that both fold to the token's label: ambiguous, nothing recased.
    ops, adjudications = _w101_change(
        f'<article class="change" data-change-part="{base}/§5a-1">'
        '<article class="defaultP">§ 5 A-1 skal lyde:</article>'
        + _w82_future_article("§5A-1", "Jurisdiksjon", "Kongen kan gi forskrift.")
        + _w82_future_article("§5a-1", "Jurisdiksjon", "Kongen kan gi forskrift.")
        + "</article>"
    )
    assert [op.target.path for op in ops] == [(("section", "5a-1"),)]
    assert not _w101_kinds(adjudications, NO_PARSE_STRUCTURED_SECTION_LABEL_CASED_FROM_CARRIER)


def test_no_w101_apply_places_the_new_chapter_and_its_sections_and_refuses_an_occupied_label() -> None:
    ops, _ = _w101_change(_W101_NEW_CHAPTER_BLOCK)
    statute = _w98_statute([("5", "Kap. 5", [("5-1", "A", ["a"])]), ("6", "Kap. 6", [("6-1", "B", ["b"])])])
    result = apply_no_ops(statute, ops, adjudications_out=[])
    assert [child.label for child in result.body.children] == ["5", "5A", "6"]
    assert _w98_heading(_w98_chapter(result, "5A")) == "Kap. 5 A. Videodelingsplattformtjenester"
    # Under the NEW chapter, with the consolidation's case — not under chapter 5
    # by label family, and not as ``5a-1``.
    assert _w98_sections(_w98_chapter(result, "5A")) == [
        ("5A-1", ["Kongen kan gi forskrift."]),
        ("5A-2", ["Tilbydere plikter å registrere seg."]),
    ]
    assert _w98_sections(_w98_chapter(result, "5")) == [("5-1", ["a"])]
    # Occupied: the standing chapter is in-force law and is not the thing to delete.
    occupied = _w98_statute(
        [("5", "Kap. 5", [("5-1", "A", ["a"])]), ("5A", "Kap. 5 A. Gammel", [("5A-9", "Z", ["z"])])]
    )
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(occupied, ops, adjudications_out=adjudications)
    assert _w98_heading(_w98_chapter(result, "5A")) == "Kap. 5 A. Gammel"
    refusals = [
        item for item in adjudications if item.kind == NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED
    ]
    assert len(refusals) == 1
    assert (refusals[0].detail or {}).get("production") == NO_CHAPTER_REENACTMENT_PROVENANCE_TAG


@pytest.mark.skipif(
    _NO_FARCHIVE_PATH is None,
    reason="norway.farchive not available (set LAWVM_CANONICAL_DATA_ROOT)",
)
def test_no_w101_corpus_totals() -> None:
    """The W-101 census at its base pin, over every amendment artifact.

    77 change blocks over 45 instruments carry a ``kap…`` token. Chapter ops
    from the structured lane (no ``fallback:unstructured`` tag), W-82's eight
    ``KAPITTEL_`` ops (5 REPLACE, 2 INSERT, 1 REPEAL) included: 40 REPLACE,
    18 INSERT, 5 REPEAL; 117 section inserts scoped to a new chapter (118
    receipts: ``no/lovtid/2024-04-12-14`` scopes § 6 and then refuses its
    payload as undeclared, so that receipt has no op); 17 section addresses
    recased from their carriers; 29 typed chapter refusals by reason;
    3 ``kap…`` tokens still unresolved (an ``avsnitt`` and an ``overskrift``
    segment inside the chapter).
    """
    from collections import Counter

    from lawvm.norway.sources import iter_no_amendment_artifacts

    chapter_ops: Counter[str] = Counter()
    receipts: Counter[str] = Counter()
    reasons: Counter[tuple[str, str]] = Counter()
    unresolved_kap: list[str] = []
    for artifact in iter_no_amendment_artifacts(_NO_FARCHIVE_PATH):
        adjudications: list[CompileAdjudication] = []
        ops = parse_no_amendment_ops(artifact.payload, artifact.logical_id, adjudications_out=adjudications)
        for op in ops:
            if "fallback:unstructured" in (op.provenance_tags or ()):
                continue
            path = op.target.path
            if len(path) == 1 and path[0][0] == "chapter":
                chapter_ops[_action_value(op.action)] += 1
            elif len(path) == 2 and path[0][0] == "chapter" and path[1][0] == "section":
                chapter_ops[f"scoped_section_{_action_value(op.action)}"] += 1
        for item in adjudications:
            if item.kind in {
                NO_PARSE_STRUCTURED_SECTION_LABEL_CASED_FROM_CARRIER,
                NO_PARSE_STRUCTURED_SECTION_TARGET_SCOPED_TO_NEW_CHAPTER,
                NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED,
            }:
                receipts[item.kind] += 1
            if item.kind == NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED:
                detail = item.detail or {}
                reasons[(str(detail.get("reason")), str(detail.get("action")))] += 1
            if item.kind == "no_parse_unresolved_structured_target_skipped" and "/kap" in str(
                (item.detail or {}).get("raw_target", "")
            ):
                unresolved_kap.append(str((item.detail or {}).get("raw_target")))

    # The three ``text_patch`` are W-69a's on ``chapter:2-5-3`` (a ``KAPITTEL_``
    # address in a word-substitution block), untouched by W-101.
    assert dict(chapter_ops) == {
        "replace": 40,
        "insert": 18,
        "repeal": 5,
        "text_patch": 3,
        "scoped_section_insert": 117,
    }
    assert dict(receipts) == {
        NO_PARSE_STRUCTURED_SECTION_LABEL_CASED_FROM_CARRIER: 17,
        NO_PARSE_STRUCTURED_SECTION_TARGET_SCOPED_TO_NEW_CHAPTER: 118,
        NO_PARSE_STRUCTURED_CHAPTER_TARGET_REFUSED: 29,
    }
    assert dict(reasons) == {
        ("renumber_unsupported", "renumber"): 14,
        ("lead_disagrees", "replace"): 5,
        ("lead_disagrees", "insert"): 3,
        ("lead_disagrees", "repeal"): 3,
        ("heading_payload_missing", "replace"): 2,
        ("subdivision_announced", "replace"): 1,
        ("carriers_unaccounted", "replace"): 1,
    }
    assert sorted(unresolved_kap) == [
        "lov/1998-07-17-56/kap3/overskrift",
        "lov/2007-06-29-75/kap12/avsnitt/I",
        "lov/2007-06-29-75/kap12/avsnitt/II",
    ]


def test_no_w101_new_chapter_section_relocates_a_label_standing_elsewhere() -> None:
    """klimakvoteloven's shape: ``Nytt kapittel 4 A med §§ 16 til 16 d`` while chapter 4 still holds a § 16.

    Section labels are law-unique, so the standing § 16 is the provision the
    new chapter re-enacts. Before W-101 the unscoped insert hit it and the θ
    (INSERT, target_occupied) cell replaced it IN PLACE — right text, wrong
    chapter. Now the standing node is removed and the new text lands under
    chapter 4 A, with the occupant on the receipt; a § 16 a with no standing
    twin just lands. Nothing outside the production's own tag reaches this.
    """
    base = _W98_BASE.removeprefix("no/")
    ops, _ = _w101_change(
        f'<article class="change" data-add-new-part="{base}/kap4A {base}/§16 {base}/§16a">'
        '<article class="defaultP">Nytt kapittel 4 A med §§ 16 til 16 a skal lyde:</article>'
        '<span class="futuretitle">Kapittel 4 A. Tilsyn</span>'
        + _w82_future_article("§16", "Tilsyn", "Klimakvotemyndigheten fører tilsyn.")
        + _w82_future_article("§16a", "Pålegg", "Klimakvotemyndigheten kan gi pålegg.")
        + "</article>"
    )
    assert [op.target.path for op in ops] == [
        (("chapter", "4A"),),
        (("chapter", "4A"), ("section", "16")),
        (("chapter", "4A"), ("section", "16a")),
    ]
    statute = _w98_statute(
        [
            ("4", "Kap. 4", [("15", "Kontroll", ["k"]), ("16", "Internkontroll", ["Forurensningsmyndigheten kan gi forskrifter."])]),
            ("5", "Kap. 5", [("17", "Suspensjon", ["s"])]),
        ]
    )
    adjudications: list[CompileAdjudication] = []
    result = apply_no_ops(statute, ops, adjudications_out=adjudications)
    assert [child.label for child in result.body.children] == ["4", "4A", "5"]
    assert _w98_sections(_w98_chapter(result, "4")) == [("15", ["k"])]
    assert _w98_sections(_w98_chapter(result, "4A")) == [
        ("16", ["Klimakvotemyndigheten fører tilsyn."]),
        ("16a", ["Klimakvotemyndigheten kan gi pålegg."]),
    ]
    relocated = [
        item for item in adjudications if item.kind == NO_REPLAY_NEW_CHAPTER_SECTION_RELOCATED_FROM_OCCUPIED_LABEL
    ]
    assert [(item.detail or {}).get("occupant_path") for item in relocated] == ["chapter:4/section:16"]
    assert [(item.detail or {}).get("target") for item in relocated] == ["chapter:4A/section:16"]
    # The same ops without the tag take the shipped path: a second § 16, no relocation.
    untagged = [
        replace(op, provenance_tags=tuple(t for t in op.provenance_tags if t != NO_NEW_CHAPTER_SECTION_PROVENANCE_TAG))
        for op in ops
    ]
    adjudications = []
    result = apply_no_ops(statute, untagged, adjudications_out=adjudications)
    assert _w98_sections(_w98_chapter(result, "4")) == [
        ("15", ["k"]),
        ("16", ["Forurensningsmyndigheten kan gi forskrifter."]),
    ]
    assert not [
        item for item in adjudications if item.kind == NO_REPLAY_NEW_CHAPTER_SECTION_RELOCATED_FROM_OCCUPIED_LABEL
    ]
