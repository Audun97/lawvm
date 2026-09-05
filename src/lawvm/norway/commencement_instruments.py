"""Typed Norsk Lovtidend commencement-instrument surface.

Parses commencement instruments into typed candidates, and owns the
execution-authorization gate that re-dates unresolved amendment acts from a
whole-act, single-date instrument. Parsing itself still authorizes nothing: only
a candidate that passes every conjunct of the gate re-dates the act it cites.

W-39 adds the gate's second, narrower route: a PART-SCOPED authorization. A
staged multi-part amending act is commenced one *romertall* at a time
("Delvis/Delt ikraftsetting"), so no single instrument can ever satisfy
``whole_act_scope`` and the act stays contingent even when every part it
contains has in fact been commenced. The part route authorizes the act's ops
for ONE law — the law of the one part the instrument's own ``Endrer`` header
names — and leaves every other part of the act exactly as unresolved as it was.
Its scope proof is structural, not textual: see
:class:`NOCommencementAuthorizationConjunct`.

W-47 adds the gate's third route, for the pairs the W-39 matcher refuses
because the ``Endrer`` header spans SEVERAL parts. The census behind it settled
two facts that between them decide the route's whole shape:

* the header is a faithful PART-to-LAW map — in all 168 refused pairs the
  spanned parts amend exactly the laws the header names, in both directions;
* the header is NOT a faithful statement of the INSTRUMENT's scope — eleven of
  those 168 have operative text commencing strictly less than the header names
  ("Loven del I trer i kraft" against a two-part header; "Romertall II, III og
  IV" against a I/III/IV header; "Del VI punkt 1" against a I-V header).

So a spanning header licenses nothing on its own. What licenses the multi-part
grant is the instrument's own text saying the WHOLE act commences: then dating
the header's parts is dating a SUBSET of what the text commences, and the header
supplies the part-to-law mapping those dates are keyed by. Deliberately NOT
routed through ``whole_act_scope``: that would re-date the act wholesale,
including parts the header never named, and move its act-level status. See
:class:`NOCommencementMultiPartAuthorizationConjunct`.

W-49 adds the gate's fourth route, for the largest sub-shape W-47's text guard
refuses: an instrument that names a part LIST agreeing with the header ("del I
og III trer i kraft", "Romertall II, III og IV trer i kraft straks", "del I-V og
del VII og VIII"). W-47 refuses those by construction — its guard forbids the
very word ``del`` — so nothing here loosens that guard; the list is read by a
separate, TOTAL reader (:func:`_named_part_labels`) that refuses anything it
cannot account for, and the two routes are mutually exclusive because a text
naming a part can never satisfy ``whole_act_operative_text``.

The route's crux is not the list grammar but the refutation semantics. W-47's
``ACT_HAS_NO_LATER_INSTRUMENT`` is act-global: ANY later instrument on the act
refutes "the act came into force as a whole then". For a part-LIST claim that is
wrong in both directions. A later instrument commencing OTHER parts is the
expected staged pattern and must not refute — measured, act-global semantics
would cost 4 of this route's 12 pairs, two of them purely on that pattern — while
a later instrument re-commencing one of the NAMED parts must refute even though
the act-global rule would notice it too. See
:class:`NOCommencementNamedPartListAuthorizationConjunct`.

W-51 adds no route. It repairs the OLDEST one: measured over the corpus's 542
whole-act authorizations, the shipped whole-act route was in act-level soundness
breach at 8 EARLY rows over 5 acts — grants dating an act's whole op stream on a
day when another instrument had not yet commenced part of it. Three repairs, in
dependency order, and the first is shared by all four routes:

* the SIBLING predicate is sharpened. Every route that refutes a claim does so
  from the set of instruments citing the same act, and that set was built from
  ``basedOn`` alone — which conflates "commences this act" with "was made under
  this act". Five of the eight EARLY rows were the second kind: an instrument
  commencing a *forskrift* whose enabling statute happens to be the act. See
  :func:`_cites_acts_as_hjemmel_only`. Sharpening only ever REMOVES siblings, so
  it can only ever remove refutations: measured, it adds 0 and loses 0 of the
  part routes' 416 grants and it clears 5 of the 8 EARLY rows.
* the CARVE-OUT tail is fenced. ``_WHOLE_ACT_RE`` accepted "Loven trer i kraft
  <date>" followed by up to 400 non-``§`` characters, and that tail swallowed
  "…, med unntak av kapittel 6 …". See ``_WHOLE_ACT_TAIL_HAZARD_RE``.
* the act-level REFUTATION becomes a conjunct of the gate rather than a
  property the outside probe measures — the same move W-49 made for its own
  route. See
  :attr:`NOCommencementAuthorizationConjunct.ACT_HAS_NO_LATER_INSTRUMENT`.

W-53 adds the gate's FIFTH route, and the first since W-39 to make an act-level
claim. ``_WHOLE_ACT_RE`` is a shape, not a reading: it demands a single operative
block that BEGINS with ``(denne )?loven trer i kraft``, so it misses every
instrument that says the same thing with a different subject or a different verb.
The W-50 census swept all 2,365 parsed instruments and measured the miss at 518
mechanical misses over 449 offered acts, 7× the estimate that opened the item —
and the three miss classes the ledger had guessed did not survive contact: 0
title-prefix hits. What actually breaks is the SUBJECT (317 cited-act subjects
like "Lov 17. juni 2005 nr. 62 om … trer i kraft 1. januar 2006", 181 adjacent
subjects whose verb is outside the anchored set) and the verb vocabulary
(``gjelder fra``, ``skal gjelde``, the nynorsk forms).

The widened route reads those with the reader W-47 already built and W-49 already
depends on (:func:`_whole_act_operative_text`) instead of with a new pattern, and
bounds it in three ways rather than replacing the shape test:

* the instrument must say ONE thing, in ONE operative block. The reader joins
  blocks, so a two-block instrument can pass it while one block commences the act
  and the other defers a chapter of it; requiring a single block is what makes
  "the text commences the act" a statement about the whole document. Measured,
  this is the difference between the ``reader`` variant (which admits delegation
  and forskrift-amendment texts) and this one;
* W-51's carve-out fence applies UNCHANGED. ``_whole_act_operative_text``'s own
  refusing half misses exactly two of ``_WHOLE_ACT_TAIL_HAZARD_RE``'s phrases —
  ``unntak for`` and ``foreløpig ikke`` — so the widened scope proof runs the same
  fence over the same single block, from the same computed value the shipped
  reader uses. The module's readers agree on carve-outs by construction, not by
  coincidence;
* the act-level refutation is the same conjunct, over the same sharpened sibling
  set, through the same helper as W-47 and W-51
  (:func:`_act_has_later_commencement_sibling`).

It is a separate route rather than a loosening of ``_WHOLE_ACT_RE`` because the
shipped 540 must keep their proof: a route that could only ever be entered by a
pair the shipped route already refused cannot take a grant away from it, and the
two receipts stay separately countable. See
:class:`NOCommencementWidenedWholeActAuthorizationConjunct`.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, cast

from lxml import etree

from lawvm.core.diagnostic_records import diagnostic_detail
from lawvm.core.quirks_disposition import QuirksDisposition
from lawvm.core.regex_safety import compile_classifier_regex
from lawvm.core.xml_parse import parse_corpus_xml
from lawvm.norway.commencement_scope import (
    NOCommencementScopeItem,
    NOCommencementScopeReading,
    act_scoped_operative_blocks,
    read_no_commencement_scope_statements,
)

NO_COMMENCEMENT_INSTRUMENT_RULE = "no_lovtidend_commencement_instrument_candidate"
NO_COMMENCEMENT_SCOPE_UNRESOLVED = "no_lovtidend_commencement_scope_unresolved"
NO_COMMENCEMENT_INSTRUMENT_PARSE_FAILED = "no_lovtidend_commencement_instrument_parse_failed"
NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID = "no_lovtidend_commencement_instrument_coverage_invalid"
NO_COMMENCEMENT_EXECUTION_AUTHORIZED = "no_lovtidend_commencement_execution_authorized"
NO_COMMENCEMENT_EXECUTION_REFUSED = "no_lovtidend_commencement_execution_refused"
NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT = "no_lovtidend_commencement_execution_date_conflict"
NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_part_execution_authorized"
)
NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT = (
    "no_lovtidend_commencement_part_execution_date_conflict"
)
NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_multi_part_execution_authorized"
)
NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_named_part_list_execution_authorized"
)
NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_widened_whole_act_execution_authorized"
)
# W-100. The section-scoped lane's three receipts: a grant per (act, law)
# binding, a date conflict per key, and a refusal per (instrument, act) pair the
# reader read but the gate could not resolve.
NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_AUTHORIZED = (
    "no_lovtidend_commencement_section_scope_execution_authorized"
)
NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_DATE_CONFLICT = (
    "no_lovtidend_commencement_section_scope_execution_date_conflict"
)
NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_REFUSED = (
    "no_lovtidend_commencement_section_scope_execution_refused"
)
NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_DATE_CONFLICT = (
    "no_lovtidend_commencement_widened_whole_act_execution_date_conflict"
)

_WS_RE = re.compile(r"\s+")
_LAW_REF_RE = re.compile(r"(?:^|[/\s])lov/(?P<date>\d{4}-\d{2}-\d{2})-(?P<num>\d+)(?:$|[/\s#?])")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_COMMENCEMENT_TITLE_RE = compile_classifier_regex(
    r"\b(?:ikraftsetting|ikraftsetjing|ikrafttredelse)\b",
    re.IGNORECASE,
    classifier_id="no.lovtidend.commencement_instrument_title",
)
_LAW_COMMENCEMENT_RE = compile_classifier_regex(
    r"\b(?:loven|lova)\s+trer\s+i\s+(?:kraft|verk)\b",
    re.IGNORECASE,
    classifier_id="no.lovtidend.law_commencement_clause",
)
# The section labels a commencement instrument's operative text names. Shapes
# attested in the 246 exact part matches: ``§ 16``, ``§ 14a``, ``§ 20-14``,
# ``§ 4 a``. The label body is the grafter's own section-label alphabet; the
# comparison downstream is set equality, so a shape this misses shows up as a
# refusal, never as an over-authorization.
# The two label shapes are spelled as an alternation rather than as an optional
# ``-<n>`` suffix group: a quantifier nested inside an optional group is exactly
# what the classifier-safety lint refuses, and the chapter-numbered form is
# listed FIRST so ``§ 20-14`` never matches as ``20``.
_COMMENCED_SECTION_RE = compile_classifier_regex(
    r"§+ ?([0-9]+-[0-9]+ ?[a-zA-Z]?|[0-9]+ ?[a-zA-Z]?)",
    classifier_id="no.lovtidend.commenced_section_label",
)
_WHOLE_ACT_RE = compile_classifier_regex(
    r"^(?:denne )?(?:loven|lova) trer i (?:kraft|verk)\b[^§]{0,400}$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.whole_act_commencement",
)
# W-51. The fence on ``_WHOLE_ACT_RE``'s tail, and purely REFUSING: nothing here
# can make a text acceptable. The pattern above ends in ``[^§]{0,400}$``, which
# was meant to let an innocuous trailing clause through ("Loven trer i kraft 1.
# januar 2012, med virkning for regnskapsår påbegynt etter …") but also swallows
# a CARVE-OUT: ``no/forskrift/2020-05-07-944`` reads "Loven trer i kraft 1. juli
# 2020, med unntak av kapittel 6 …, som trer i kraft når departementet
# bestemmer" and authorized the whole of ``no/lovtid/2020-05-07-40`` on
# 2020-07-01 while ``2021-08-26-2589`` commenced that chapter fifteen months
# later. A whole-act claim cannot survive a sentence that names an exception.
#
# The vocabulary is the hazard set W-41 and W-47 catalogued, not a fresh
# invention: the negative/exception phrases plus the subdivision nouns. It is
# deliberately spelled out here rather than shared with ``_SUBDIVISION_SCOPE_RE``
# below, which serves a different route over a different measured population —
# widening THAT one to cover ``unntak for`` and ``foreløpig ikke`` could only
# take grants away from W-47. ``§`` is absent because ``_WHOLE_ACT_RE``'s own
# ``[^§]`` already excludes it.
#
# Measured over the 608 instruments the shipped regex accepts today, this fence
# refuses exactly one: ``2020-05-07-944``. The two sibling carve-out texts
# W-50 found (``2010-06-04-771``, ``2011-12-09-1221``) never reach it — each
# carries two ``dateInForce`` dates, so they were already inert.
_WHOLE_ACT_TAIL_HAZARD_RE = compile_classifier_regex(
    r"(?:\bmed\s+unntak\b|\bunntak\s+for\b|\bunntatt\b"
    r"|\bbortsett\s+fra\b|\bfor\s+så\s+vidt\b|\bmed\s+mindre\b"
    r"|\bikke\s+i\s+kraft\b|\bforeløpig\s+ikke\b"
    r"|\bdel(?:en|ene|er|e|s)?\b"
    r"|\bromertall\b|\bromartal\b|\bromartall\b"
    r"|\bpunkt(?:um|et|a)?\b"
    r"|\bavsnitt(?:et|a)?\b"
    r"|\bkapit(?:tel|let|la|lene|el)\b"
    r"|\bbokstav(?:en|ene|er)?\b"
    r"|\bledd(?:et)?\b)",
    re.IGNORECASE,
    classifier_id="no.lovtidend.whole_act_tail_hazard",
)
# W-51. The definite act-word, and the textual half of the hjemmel-only sibling
# predicate. An instrument that commences an act — the whole of it, a chapter of
# it, one section of it — says so with the definite form: "Loven trer i kraft",
# "Lovens kapittel 6 trer i kraft", "Loven § 7-3 trer i kraft straks". An
# instrument that merely rests on the act says "med hjemmel i lov 24. juni 2011
# nr. 29 …" and never needs the definite form at all. Word-bounded on purpose:
# the short-title compounds Norwegian statutes are named by (``folkehelseloven``,
# ``finansforetaksloven``) end in the same letters and are NOT this word.
_DEFINITE_ACT_WORD_RE = compile_classifier_regex(
    r"\b(?:loven|lova|lovens|lovas)\b",
    re.IGNORECASE,
    classifier_id="no.lovtidend.definite_act_word",
)
# W-47. The multi-part route's text guard, in two halves that must BOTH hold.
#
# Half one, ``_SUBDIVISION_SCOPE_RE``, is purely REFUSING: any of these tokens
# in the operative text means the instrument may be scoping to a proper part of
# the act, and the pair refuses. Nothing in it can ever accept. The list is the
# subdivision vocabulary Norwegian commencement instruments actually use
# (romertall part, punkt, avsnitt, kapittel, bokstav, ledd, the section sign)
# plus the negative/exception phrases that carve a hole in an otherwise
# whole-act sentence ("med unntak av", "settes ikke i kraft"). Measured over the
# 168 spanning-header pairs it refuses 96, including all eleven whose text is
# PROVEN to commence less than their header names.
_SUBDIVISION_SCOPE_RE = compile_classifier_regex(
    r"(?:§"
    r"|\bdel(?:en|ene|er|e|s)?\b"
    r"|\bromertall\b|\bromartal\b|\bromartall\b"
    r"|\bpunkt(?:um|et|a)?\b"
    r"|\bavsnitt(?:et|a)?\b"
    r"|\bkapit(?:tel|let|la|lene|el)\b"
    r"|\bbokstav(?:en|ene|er)?\b"
    r"|\bledd(?:et)?\b"
    r"|\bmed\s+unntak\b|\bunntatt\b|\bikke\s+i\s+kraft\b"
    r"|\bfor\s+så\s+vidt\b|\bbortsett\s+fra\b|\bmed\s+mindre\b)",
    re.IGNORECASE,
    classifier_id="no.lovtidend.commencement_subdivision_scope",
)
_COMMENCEMENT_VERB = (
    r"(?:trer\s+i\s+kraft|trer\s+ikraft|trer\s+i\s+verk|tek\s+til\s+å\s+gjelde"
    r"|gjelder\s+fra|gjelder\s+frå|gjeld\s+frå|skal\s+gjelde"
    r"|blir\s+satt\s+i\s+kraft|blir\s+sett\s+i\s+kraft|blir\s+sette\s+i\s+kraft"
    r"|settes\s+i\s+kraft|setjast\s+i\s+kraft|iverksettes)"
)
# Half two is the POSITIVE half, and it exists for the one narrowing half one
# cannot see: an instrument scoping by LAW rather than by subdivision
# ("Endringene i folketrygdloven trer i kraft" under a three-law header). The
# subject of the commencement clause must therefore be the ACT, in one of two
# closed shapes — a generic act-word IMMEDIATELY before the verb (the adjacency
# is the whole point; "Endringene i X-loven trer" has a preposition phrase in
# between and fails), or a sentence-initial citation of the amending act itself.
_WHOLE_ACT_SUBJECT_RE = compile_classifier_regex(
    r"\b(?:loven|lova|lovens|endringsloven|endringslova|endringslovene"
    r"|lovendringene|lovendringane|endringene|endringane)\s+" + _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.whole_act_commencement_subject",
)
_CITED_ACT_SUBJECT_RE = compile_classifier_regex(
    r"(?:^|(?<=[.:])\s)lov\b[^§]{0,400}?\bom\s+endring(?:er|ar|a)?\b[^§]{0,400}?"
    + _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.cited_act_commencement_subject",
)
_COMMENCEMENT_VERB_RE = compile_classifier_regex(
    _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.commencement_verb",
)
# W-73. The third whole-act subject shape, and the one neither reader above can
# take: an instrument commencing a NEW act names it the only way a new act can
# be named — by its TITLE, in the indefinite ("Lov om bustøtte skal gjelde frå
# 1. januar 2013."). ``_WHOLE_ACT_SUBJECT_RE`` wants a definite act-word
# adjacent to the verb and there is none; ``_CITED_ACT_SUBJECT_RE`` wants
# ``om endring`` and a new act amends nothing in its own title.
#
# Read alone this shape is far too loose — "lov" opens a great many sentences —
# so it is never read alone. :func:`_title_cited_whole_act_subject` pairs it
# with a TITLE-AGREEMENT witness (the subject's own title phrase must appear in
# the instrument's declared title) and with an unambiguity witness (exactly one
# cited act, exactly one such subject in the text), and those three together are
# what carry the claim. The bound on the title phrase is the same shape
# ``_CITED_ACT_SUBJECT_RE`` uses — lazy, ``§``-excluding, and length-capped — so
# a runaway subject cannot swallow a following sentence.
#
# Spelled with single ``\s`` separators rather than ``\s+``, and with the lazy
# span running straight into the verb with no separator of its own: a variable
# repeat adjacent to another whose starts overlap is what the classifier-safety
# lint refuses, and ``[^§]`` overlaps ``\s``. The operative blocks arrive
# whitespace-collapsed from ``_operative_blocks``, so a single ``\s`` is the
# whole vocabulary there is to match. This is character-for-character the shape
# ``_CITED_ACT_SUBJECT_RE`` already passes the lint with.
# W-100 widens the subject by one optional group: the act's own date-and-number
# citation between ``lov`` and ``om`` (``Lov 11. januar 2013 nr. 3 om Statens
# innkrevingssentral trer i kraft 1. juni 2013``, ``no/forskrift/2013-05-24-533``).
# A NEW act is cited that way at least as often as by bare title, and the four
# conjuncts below carry the widened shape unchanged: the title phrase still has
# to agree with the instrument's declared title. Measured: 18 blocked instruments
# of this shape cite an offered act.
_TITLE_CITED_ACT_SUBJECT_RE = compile_classifier_regex(
    r"^lov\s(?P<title_phrase>om\s[^§]{1,300}?)" + _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.title_cited_act_commencement_subject",
)
# The unambiguity witness's counter. Word-bounded ``lov om`` is how an act is
# cited by title, and a text carrying two of them is commencing two acts in one
# sentence (``no/forskrift/2009-03-06-266``, "Lov om Statens finansfond og lov om
# Statens obligasjonsfond trer i kraft straks") — a claim this reader refuses
# rather than attributes to whichever act it happens to be paired with.
# W-100. The same subject with the act's own date-and-number citation between
# ``lov`` and ``om``. Spelled as a SECOND pattern rather than an optional group
# in the first, because a quantified citation inside an optional group is
# exactly the nesting the classifier-safety lint refuses; the reader tries the
# plain shape first and this one second, and the counter below adds the two.
_TITLE_CITED_ACT_CITATION_SUBJECT_RE = compile_classifier_regex(
    r"^lov\s(?:av\s)?\d{1,2}\.?\s[a-zæøå]+\s\d{4}\snr\.?\s?\d+\s"
    r"(?P<title_phrase>om\s[^§]{1,300}?)" + _COMMENCEMENT_VERB,
    re.IGNORECASE,
    classifier_id="no.lovtidend.title_cited_act_citation_commencement_subject",
)
_BARE_DATE_TAIL_RE = compile_classifier_regex(
    r"\s(?:fra|frå)?\s?\d{1,2}\.?\s[a-zæøå]+\s\d{4}\.?$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.bare_date_tail",
)
_INDEFINITE_ACT_TITLE_CITATION_SUBJECT_RE = compile_classifier_regex(
    r"\blov\s(?:av\s)?\d{1,2}\.?\s[a-zæøå]+\s\d{4}\snr\.?\s?\d+\som\s",
    re.IGNORECASE,
    classifier_id="no.lovtidend.indefinite_act_title_citation_subject",
)
_INDEFINITE_ACT_TITLE_SUBJECT_RE = compile_classifier_regex(
    r"\blov\s+om\s+",
    re.IGNORECASE,
    classifier_id="no.lovtidend.indefinite_act_title_subject",
)
# W-49. The named-part-list reader's refusing guard: ``_SUBDIVISION_SCOPE_RE``
# with the PART vocabulary taken out (this reader's whole job is to read those
# words) and the sub-part qualifiers W-47 never needed put in. Every token here
# only ever REFUSES; none can make a text acceptable.
#
# The two additions are measured, not speculative. ``setning`` is what stops
# ``no/forskrift/2019-11-22-1552`` ("romertall I siste setning og romertall
# II-VII"), a PROVEN header/text disagreement whose part list otherwise reads as
# a clean superset of its header. ``overskrift`` is its sibling shape, and the
# delegated-date phrases ("fra det tidspunkt ... bestemmer", "Kongen bestemmer")
# refuse an instrument that commences some named parts now and defers others —
# the one way a single-dated text can still be staged inside itself.
_PART_LIST_HAZARD_RE = compile_classifier_regex(
    r"(?:§"
    r"|\bpunkt(?:um|et|a)?\b"
    r"|\bavsnitt(?:et|a)?\b"
    r"|\bkapit(?:tel|let|la|lene|el)\b"
    r"|\bbokstav(?:en|ene|er)?\b"
    r"|\bledd(?:et)?\b"
    r"|\bsetning(?:en|a|er|ene)?\b"
    r"|\boverskrift(?:en|a|er|ene)?\b"
    r"|\bmed\s+unntak\b|\bunntak\s+for\b|\bunntatt\b|\bikke\s+i\s+kraft\b"
    r"|\bfor\s+så\s+vidt\b|\bbortsett\s+fra\b|\bmed\s+mindre\b"
    r"|\bfra\s+det\s+tidspunkt\b|\bbestemmer\b|\bforeløpig\s+ikke\b)",
    re.IGNORECASE,
    classifier_id="no.lovtidend.commencement_part_list_hazard",
)
# The list grammar itself is a hand-written scanner, not a regex: the shapes it
# has to accept ("del I, II, III, IV og V", "Romertall II, III og IV", "del I-V
# og del VII og VIII", "Endringsloven del I til III") are a token language, and
# the property that makes the reader safe — every token accounted for, anything
# unknown CLOSES the list rather than being skipped over — is a property of the
# scanner's control flow, not of a pattern.
_PART_LIST_PART_WORDS = frozenset(
    {"del", "delen", "delene", "deler", "dele", "dels", "romertall", "romartal", "romartall"}
)
_PART_LIST_CONJUNCTIONS = frozenset({",", "og", "eller"})
_PART_LIST_RANGE_TOKENS = frozenset({"-", "–", "—", "til"})
_PART_LIST_PUNCTUATION = ",.;:()[]«»/–—-"
_ROMAN_DIGIT_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ROMAN_LABEL_STEPS = (
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


class NOCommencementParseStatus(StrEnum):
    CANDIDATE = "candidate"
    BENIGN_NOT_COMMENCEMENT = "benign_not_commencement"
    BLOCKED_UNRESOLVED = "blocked_unresolved"


class NOCommencementScopeStatus(StrEnum):
    WHOLE_ACT = "whole_act"
    UNRESOLVED = "unresolved"


class NOCommencementAuthorizationConjunct(StrEnum):
    """The conjuncts an (instrument, act) pair must satisfy to re-date the act."""

    PARSE_STATUS_CANDIDATE = "parse_status_candidate"
    WHOLE_ACT_SCOPE = "whole_act_scope"
    SINGLE_EFFECTIVE_DATE = "single_effective_date"

    ACT_HAS_NO_LATER_INSTRUMENT = "act_has_no_later_instrument"
    """No commencement-relevant instrument commences anything of this act LATER.

    W-51. The oldest route's claim is the strongest one the lane makes — every
    op of the act, for every law it binds, in force on this one day — and a
    later instrument commencing part of the same act is direct evidence against
    it, whatever that instrument's own scope. W-47 already asserts exactly this
    for the multi-part route (:attr:`NOCommencementMultiPartAuthorizationConjunct.ACT_HAS_NO_LATER_INSTRUMENT`);
    the whole-act route asserted it nowhere, and the outside soundness probe
    measured the gap at 8 EARLY rows over 5 acts. Both now call one helper,
    :func:`_act_has_later_commencement_sibling`, over one sibling set.

    W-49's route needed a two-witness DISJOINTNESS proof in place of this
    conjunct because its claim is about named parts, so a later instrument on
    OTHER parts is the ordinary staged pattern and must not refute. None of that
    applies here, and the difference is worth stating rather than inheriting: a
    whole-act claim leaves no part of the act un-claimed, so there is no
    disjointness to prove and no sibling that can be "about something else in
    this act". ANY later commencement-relevant sibling refutes.

    What "commencement-relevant" means is the other half of the repair, and it
    is shared with both older conjuncts: see :func:`_cites_acts_as_hjemmel_only`.
    """


class NOCommencementPartAuthorizationConjunct(StrEnum):
    """The conjuncts an (instrument, act) pair must satisfy to date ONE part.

    Deliberately a separate closed set from the whole-act conjuncts: the two
    routes prove different things, and a refusal that lists both sets' names in
    one field would say nothing about which route was even attempted.
    """

    SINGLE_EFFECTIVE_DATE = "single_effective_date"
    """The instrument's ``dateInForce`` carries exactly one ISO date."""

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse failed for no reason other than whole-act scope.

    A ``blocked_unresolved`` parse has exactly three causes: no affected law, no
    effective date, or no whole-act scope proof. The first is excluded because
    the pair exists only when the instrument cites an offered act; the second by
    ``SINGLE_EFFECTIVE_DATE``. What is left is an instrument that IS a
    commencement and names its act, and whose only defect is that it commences
    less than the whole act — which is precisely the population this route is
    for. A genuine parse failure (malformed XML) never reaches here at all.
    """

    INSTRUMENT_DECLARES_CHANGED_LAWS = "instrument_declares_changed_laws"
    """The instrument's own ``Endrer`` (``changesToDocuments``) block is present
    and non-empty. This is the scope evidence; without it there is nothing to
    match a part against, and the instrument stays evidence."""

    ACT_PART_LAW_MAP_INJECTIVE = "act_part_law_map_injective"
    """No law is amended by two of the act's parts.

    A law appearing in two parts makes "the part this instrument commences"
    undecidable from the ``Endrer`` header alone — the same ambiguity W-24's
    part resolver refuses when a part's ``document-change`` wrappers disagree.
    """

    ACT_BINDINGS_INSIDE_PART_MAP = "act_bindings_inside_part_map"
    """Every law the act actually binds is the law of some part.

    Without this, an op bound by a carried-over base id from a part that
    resolved no law of its own could be dated by a part authorization that never
    covered it.
    """

    ENDRER_MATCHES_ONE_PART_EXACTLY = "endrer_matches_one_part_exactly"
    """The ``Endrer`` law set equals the law set of exactly one part.

    Equality in BOTH directions: every named law lives in that part, and the
    part amends no law the header omits. A header spanning two parts, or naming
    a law the act's structure cannot place, refuses.
    """

    WHOLE_PART_SCOPE = "whole_part_scope"
    """The instrument commences the whole part, not a slice of it.

    The ``Endrer`` match proves WHICH part; it does not prove HOW MUCH of it. A
    "Delvis ikraftsetting" that names individual sections inside the part
    commences less than the part, and dating the part's whole op stream from it
    would apply ops that are not yet in force. Proof, mirroring ``_WHOLE_ACT_RE``'s
    own ``[^§]{0,400}`` guard one level down: the operative text names no section
    at all, or the sections it names are exactly the sections the part's ops
    target. Measured over the 246 exact ``Endrer``-to-part matches in the corpus,
    122 name no section and 15 name the part's own section set; the other 109 are
    genuinely narrower and are refused here.
    """


class NOCommencementMultiPartAuthorizationConjunct(StrEnum):
    """The conjuncts an (instrument, act) pair must satisfy to date SEVERAL parts.

    A third closed set beside the whole-act and single-part ones, for the same
    reason those two are separate: naming a conjunct only says something if the
    reader knows which route was attempted. Five of these are the single-part
    route's conjuncts unchanged — the part-structure requirements do not weaken
    when more than one part is in play — and three are this route's own.
    """

    SINGLE_EFFECTIVE_DATE = "single_effective_date"
    """The instrument's ``dateInForce`` carries exactly one ISO date."""

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse failed for no reason other than whole-act scope."""

    INSTRUMENT_DECLARES_CHANGED_LAWS = "instrument_declares_changed_laws"
    """The instrument's own ``Endrer`` block is present and non-empty."""

    ACT_PART_LAW_MAP_INJECTIVE = "act_part_law_map_injective"
    """No law is amended by two of the act's parts."""

    ACT_BINDINGS_INSIDE_PART_MAP = "act_bindings_inside_part_map"
    """Every law the act actually binds is the law of some part.

    One-directional, as at W-39: a part may resolve a law the act's lowered ops
    never bind, and a grant for such a part dates nothing at all, because
    ``effective_date_for_base`` is only ever asked about a law in ``base_ids``.
    Measured, 27 of this route's 260 grants are inert that way (2 of W-39's 123
    already were). They are left in rather than filtered, so both routes behave
    alike and the commencement fact stays receipted; the count is pinned.
    """

    ENDRER_MATCHES_A_PART_SET_EXACTLY = "endrer_matches_a_part_set_exactly"
    """The ``Endrer`` law set equals the union of the law sets of the parts it
    spans, and that span is more than one part.

    The generalization of ``ENDRER_MATCHES_ONE_PART_EXACTLY``, and equally
    two-directional: every named law lives in one of the spanned parts, and no
    spanned part amends a law the header omits. Requiring MORE than one part is
    what keeps the two routes disjoint — a single-part header is the W-39
    route's business and is never re-examined here.

    Honest note on its strength today: given ``ACT_PART_LAW_MAP_INJECTIVE`` and
    an evidence model where a part resolves at most ONE law, the reverse
    direction is structurally implied, and the census bears that out — the
    reverse check refuses 0 of the 168 pairs, at either granularity. It is
    asserted rather than dropped because the implication is a property of the
    evidence shape, not of the law: the day ``part_law_ids`` carries several
    laws per part, this is the conjunct that stops a header naming one of them
    from dating all of them.
    """

    WHOLE_ACT_OPERATIVE_TEXT = "whole_act_operative_text"
    """The instrument's operative text commences the act as a WHOLE.

    This is the conjunct that does the licensing work, because the header alone
    is not evidence of the instrument's scope — measured, eleven of the 168
    spanning-header pairs commence strictly less than their header names. Proof
    has two halves: the text names no subdivision of the act anywhere and
    carries no negative/exception phrase (``_SUBDIVISION_SCOPE_RE``, refusing
    only), and the subject of its commencement clause is the act rather than one
    of the laws the act amends (``_WHOLE_ACT_SUBJECT_RE`` /
    ``_CITED_ACT_SUBJECT_RE``). Given both, what the instrument commences is a
    superset of the parts the header names, so dating exactly those parts claims
    strictly less than the instrument says.
    """

    WHOLE_PART_SCOPE_PER_PART = "whole_part_scope_per_part"
    """Every spanned part passes the single-part route's ``whole_part_scope``.

    Vacuous as things stand — ``WHOLE_ACT_OPERATIVE_TEXT`` refuses any text
    containing ``§`` at all, so the named-section set is always empty here and
    the check passes for every part. It is asserted per part rather than assumed
    so that the day the text guard is loosened, a slice named inside a spanned
    part refuses the part it is inside instead of silently dating it.
    """

    ACT_HAS_NO_LATER_INSTRUMENT = "act_has_no_later_instrument"
    """No other instrument commences anything of this act at a LATER date.

    The route's claim is that the act came into force as a whole on this date.
    Another instrument commencing (or re-commencing) part of the same act
    afterwards is direct evidence that it did not, whatever that instrument's
    own scope, so the whole match refuses. Not a hypothetical guard: without it
    the W-39 soundness probe FIRES on ``no/lovtid/2019-12-06-76``, whose
    whole-act instrument ``2019-12-20-1913`` is contradicted first by
    ``2020-01-10-15`` revoking the commencement of verdipapirhandelloven
    § 3-1 første ledd and then by ``2021-01-29-266`` re-commencing del I on
    2021-03-01 — a 15-month early application of that part's ops.
    """


class NOCommencementNamedPartListAuthorizationConjunct(StrEnum):
    """The conjuncts a pair must satisfy to date the parts its TEXT names.

    A fourth closed set. Six of these are the multi-part route's conjuncts
    unchanged — the part-structure requirements do not weaken when the scope
    proof moves from the header to the text — and five are this route's own.
    """

    SINGLE_EFFECTIVE_DATE = "single_effective_date"
    """The instrument's ``dateInForce`` carries exactly one ISO date."""

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse failed for no reason other than whole-act scope."""

    INSTRUMENT_DECLARES_CHANGED_LAWS = "instrument_declares_changed_laws"
    """The instrument's own ``Endrer`` block is present and non-empty."""

    INSTRUMENT_CITES_ONE_ACT = "instrument_cites_one_act"
    """The instrument's operative text is about ONE amending act.

    This route's only conjunct with no counterpart above it, and it exists
    because this route is the first to read a scope out of PROSE. An instrument
    may commence parts of two different acts in one document
    (``no/forskrift/2020-04-29-885`` commences del I and del II of
    ``2018-04-20-12`` and del II of ``2019-03-08-5``), and the operative blocks
    are read joined, so its two part lists would merge into one. Nothing in the
    merged list says which act each label came from. Rather than guess at
    per-sentence attribution, the route refuses the whole shape: measured, no
    pair it would otherwise grant cites more than one act.
    """

    ACT_PART_LAW_MAP_INJECTIVE = "act_part_law_map_injective"
    """No law is amended by two of the act's parts."""

    ACT_BINDINGS_INSIDE_PART_MAP = "act_bindings_inside_part_map"
    """Every law the act actually binds is the law of some part."""

    ENDRER_MATCHES_A_PART_SET_EXACTLY = "endrer_matches_a_part_set_exactly"
    """The ``Endrer`` law set equals the union of the spanned parts' law sets,
    and that span is more than one part — as at W-47, and for the same reasons.
    """

    OPERATIVE_TEXT_NAMES_A_PART_LIST = "operative_text_names_a_part_list"
    """The operative text reads as a romertall part list, TOTALLY.

    ``_named_part_labels`` is a refusing reader: it returns labels only for a
    text that carries no ``§``, no sub-part qualifier (``punkt``, ``ledd``,
    ``bokstav``, ``setning``, ``kapittel``, ``avsnitt``, ``overskrift``), no
    negative or exception phrase, no delegated-date phrase, and exactly one
    commencement verb — and inside the list itself, any token the grammar does
    not know CLOSES the list rather than being skipped. The asymmetry is
    deliberate and is the reader's safety argument: under-reading a list only
    ever shrinks the claim (and then ``PART_LIST_COVERS_THE_HEADER`` refuses),
    while over-reading one would date a part the instrument never commenced.
    """

    PART_LIST_COVERS_THE_HEADER = "part_list_covers_the_header"
    """Every part the ``Endrer`` header spans is named in the text's list.

    This is the licensing conjunct, and it is the part-list analogue of W-47's
    ``WHOLE_ACT_OPERATIVE_TEXT``: given it, the parts dated are a SUBSET of the
    parts the instrument says it commences, so the grant claims strictly less
    than the text does. Equality is not required — three of the granting pairs
    name a part the header omits (``no/forskrift/2010-09-03-1239`` names del II,
    III and IV under a II/III header) — and the extra parts are simply not
    dated, exactly as W-47 leaves unnamed parts alone.

    The eleven proven header/text disagreements of the W-47 census are this
    conjunct's built-in negative suite: six of them are refused right here
    (their list is missing a header part), the other five never reach it because
    the reader refuses their text outright.
    """

    WHOLE_PART_SCOPE_PER_PART = "whole_part_scope_per_part"
    """Every spanned part passes the single-part route's ``whole_part_scope``.

    Vacuous by construction, as at W-47 and for a stronger reason: the reader
    refuses any text containing ``§``, and ``_COMMENCED_SECTION_RE`` can only
    produce a label from a ``§``, so ``commenced_section_labels`` is
    NECESSARILY empty on every pair that reaches this route. That is also this
    route's corruption-immunity proof: the W-48 ordinal-swallowing defect in
    that reader cannot make a W-49 pair authorize, because no W-49 pair ever has
    a label for it to corrupt.
    """

    LATER_INSTRUMENTS_NAME_OTHER_PARTS = "later_instruments_name_other_parts"
    """Every strictly later instrument on the act is PROVABLY about other parts.

    The per-part reading of W-47's ``ACT_HAS_NO_LATER_INSTRUMENT``, and the
    reason this route needed its own conjunct set. Act-global refutation is
    wrong here in both directions: a later instrument commencing OTHER parts is
    the ordinary staged pattern this whole lane exists for and must not refute
    (measured: the act-global rule costs 4 of 12 pairs, two of them purely on
    that pattern), while a later instrument re-commencing a NAMED part must.

    "Provably about other parts" needs TWO independent witnesses, and both must
    clear:

    * the STRUCTURAL one — the parts of the laws that later instrument's own
      ``Endrer`` header names, disjoint from the parts claimed here. This is
      precisely the sibling test the W-39/W-41/W-47 zero-early soundness probe
      applies from the outside, so requiring it makes the probe's verdict a
      property of the gate rather than a measurement of it;
    * the TEXTUAL one — the same reader run over that instrument's own operative
      text, yielding a list disjoint from the parts claimed here. A text the
      reader cannot account for is not evidence of anything and refutes.

    Two witnesses rather than one because neither is sound alone. The header is
    not an upper bound on scope (``no/forskrift/2017-12-19-2156``'s header spans
    I-V while its text commences del VI), so the structural witness can miss.
    The textual witness costs one otherwise-granting pair where the two
    disagree: ``no/forskrift/2017-06-16-758``'s text commences only del III
    while its header spans I, II and III, which would clear the text witness but
    not the structural one, and it is the later sibling of a pair claiming del I
    and del II. Refusing on disagreement is the right call — a header/text
    disagreement is exactly the unfaithfulness W-47 measured, and this route is
    not the place to adjudicate it.
    """


class NOCommencementWidenedWholeActAuthorizationConjunct(StrEnum):
    """The conjuncts a pair must satisfy to re-date an act on a READ whole-act text.

    A fifth closed set, and the second that makes an ACT-level claim. It is
    deliberately not the whole-act route's set with one member swapped: the two
    routes prove the same conclusion from different evidence — a matched SHAPE
    there, a read TEXT here — and a refusal naming ``whole_act_scope`` would say
    nothing about which reading was even attempted.
    """

    SINGLE_EFFECTIVE_DATE = "single_effective_date"
    """The instrument's ``dateInForce`` carries exactly one ISO date.

    Same conjunct as everywhere else in this gate. Two dates in the field is an
    instrument staging itself, and an act-level claim cannot be read out of it.
    """

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse failed for no reason other than whole-act scope.

    As at W-39: the pair exists only because the instrument cites an offered act,
    so "no affected law" is excluded; ``SINGLE_EFFECTIVE_DATE`` excludes "no
    effective date"; what is left is an instrument that IS a commencement, names
    its act, and whose only defect is that ``_WHOLE_ACT_RE`` did not match its
    text. That is exactly this route's population, and it is also what keeps the
    two act-level routes disjoint — a pair the shipped route ACCEPTED never
    reaches here, so this route can never take a shipped grant away or re-date an
    act the older proof already dated.
    """

    SINGLE_OPERATIVE_BLOCK = "single_operative_block"
    """The instrument has exactly one operative block.

    The bound that separates this route from the ``reader`` variant W-50 priced
    and rejected. :func:`_whole_act_operative_text` reads the operative blocks
    JOINED, so on a two-block document "the text commences the act as a whole"
    is a claim about a concatenation: one block may commence the act while the
    next defers a chapter of it, or amends a forskrift, or delegates the real
    date. Requiring a single block makes the reader's verdict a statement about
    the whole document rather than about part of it.

    Witnessed by the parse-time ``widened_whole_act_scope`` flag, because the
    block COUNT is XML-only evidence: the gate sees typed candidates and never
    the document.
    """

    WHOLE_ACT_OPERATIVE_TEXT = "whole_act_operative_text"
    """The instrument's operative text commences the act as a WHOLE.

    The same conjunct, the same name and the same reader as W-47's
    (:attr:`NOCommencementMultiPartAuthorizationConjunct.WHOLE_ACT_OPERATIVE_TEXT`):
    the text names no subdivision of the act and carries no negative or exception
    phrase (``_SUBDIVISION_SCOPE_RE``, refusing only), and the subject of its
    commencement clause is the act itself rather than one of the laws it amends
    (``_WHOLE_ACT_SUBJECT_RE`` / ``_CITED_ACT_SUBJECT_RE``).

    W-73 gives the subject half a THIRD reader, :func:`_title_cited_whole_act_subject`,
    and this route accepts either. Neither of W-47's two can read an instrument
    commencing a NEW act, because a new act has no definite act-word in its
    commencement sentence and nothing to call an ``om endring``: it is named by
    its title ("Lov om bustøtte skal gjelde frå 1. januar 2013"). That reader
    carries four conjuncts of its own — one cited act, one title subject, the
    subject sentence-initial and adjacent to the verb, and the subject's title
    phrase present in the instrument's declared title — because a title-cited
    subject is the loosest shape in the module and the surrounding proof is what
    makes it safe. Which reader carried a grant is recorded per candidate
    (``title_cited_whole_act_scope``), so the evidence plane can say why.

    W-47 could route that reading to PARTS only, and said so in as many words:
    "this flag deliberately feeds ONLY the multi-part route, never the whole-act
    one, so a looser reading can never re-date an act wholesale". This route is
    the deliberate reversal of that restriction, and what pays for it is the
    other four conjuncts — a single block, W-51's carve-out fence, and an
    act-level refutation the multi-part route did not have when that line was
    written.

    Plus the fence, and the fence is the point. Measured over the shipped
    reader's vocabulary, ``_SUBDIVISION_SCOPE_RE`` misses exactly two of
    ``_WHOLE_ACT_TAIL_HAZARD_RE``'s phrases — ``unntak for`` and ``foreløpig
    ikke`` — which is to say the two W-51 had to ADD when it fenced
    ``_WHOLE_ACT_RE``'s tail. An act-level claim read out of prose cannot be
    allowed to survive a sentence the shipped route would refuse for naming an
    exception, so ``widened_whole_act_scope`` applies that same fence, to the same
    block, from the same computed value.
    """

    ACT_HAS_NO_LATER_INSTRUMENT = "act_has_no_later_instrument"
    """No commencement-relevant instrument commences anything of this act LATER.

    Same name, same value, same code and same sibling set as W-47's and W-51's:
    :func:`_act_has_later_commencement_sibling` over the sharpened list built once
    in :func:`authorize_no_commencement_instruments`. The claim here is the
    strongest the lane makes — every op of the act, for every law it binds, in
    force on this one day — so W-49's per-part disjointness reading does not
    apply for exactly the reason W-51 gave: a whole-act claim leaves no part of
    the act un-claimed, so ANY later commencement-relevant sibling refutes.

    Asserted AFTER the date-conflict branch, as at W-51 and for the same reason.
    Applying it while proposals are gathered would quietly resolve every
    disagreement between two instruments in favour of the later date and the
    blocking conflict receipt would never be written.
    """


class NOCommencementSectionScopeAuthorizationConjunct(StrEnum):
    """W-100. What must hold for the section-scoped route to date a binding.

    The route is the first in this gate to grant BELOW a binding: its landing is
    a per-(act, law) record carrying an optional binding date, per-section dates,
    and the sections carved out. All-or-nothing per (instrument, act) pair — one
    statement the gate cannot resolve refuses the whole pair — and per-key
    conflict-checked across every instrument that speaks to the same act.
    """

    BLOCKED_ONLY_ON_SCOPE = "blocked_only_on_scope"
    """The parse blocked, and every failed whole-act conjunct is one this route
    reads past on its own terms: the scope proof (this route's whole business)
    and the single-date requirement (a staged instrument legitimately carries
    several ``dateInForce`` dates, and the reader cross-checks each prose date
    against that set)."""

    STATEMENTS_TOTAL = "statements_total"
    """The reader accounted for every sentence of the operative text."""

    INSTRUMENT_CITES_ONE_ACT = "instrument_cites_one_act"
    """One cited act, as W-49 requires: the statements are read off one text and
    two acts' statements would merge."""

    EVERY_SCOPE_RESOLVES_TO_ONE_LAW = "every_scope_resolves_to_one_law"
    """Every statement subject and every carved-out item resolves to exactly
    one law of the act — through the act's part map, through a date-and-number
    citation the act binds, or through the act's single bound law."""

    QUALIFIED_LABELS_NEVER_GRANTED = "qualified_labels_never_granted"
    """A section named with a ledd-level qualifier is never granted a date (the
    route cannot prove the act's ops on it stay inside the named ledd); in a
    carve-out it excludes the whole section, which under-claims."""

    STATEMENTS_DO_NOT_CONTRADICT = "statements_do_not_contradict"
    """No two statements — in this instrument or across the act's instruments —
    give one binding or one section two dates, and no section is dated
    differently from a binding date it was not carved out of."""


class NOCommencementInstrumentCoverageError(ValueError):
    """Persisted commencement-instrument coverage has an invalid shape."""


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentCandidate:
    source_id: str
    locator: str
    archive: str
    member_name: str
    title: str
    affected_law_ids: tuple[str, ...]
    effective_dates: tuple[str, ...]
    scope_status: NOCommencementScopeStatus
    source_excerpt: str
    rule_id: str = NO_COMMENCEMENT_INSTRUMENT_RULE
    replay_authorized: bool = False
    # W-39. The instrument's own ``Endrer`` (``changesToDocuments``) law ids —
    # the laws Lovdata records this instrument as changing. For a commencement
    # instrument those are not the instrument's own targets: they are the laws
    # the commenced PART of the cited act amends, which is what makes them a
    # scope proof. Read through ``declared_change_targets_from_root``, the
    # corpus's single reader of that block.
    changed_law_ids: tuple[str, ...] = ()
    # The section labels the operative text names, normalized to the grafter's
    # own section-label spelling so the two sets are comparable. Empty means the
    # operative text names no section at all.
    commenced_section_labels: tuple[str, ...] = ()
    # W-47. The operative text commences the act as a WHOLE — it names no
    # subdivision of the act and its commencement clause's subject is the act
    # itself. Read at parse time, where the operative blocks are already in
    # hand, so the gate stays a pure function of typed evidence and parses no
    # XML. Strictly weaker than ``scope_status is WHOLE_ACT``, which additionally
    # demands a single operative block matching ``_WHOLE_ACT_RE`` end to end;
    # this flag deliberately feeds ONLY the multi-part route, never the whole-act
    # one, so a looser reading can never re-date an act wholesale.
    whole_act_operative_text: bool = False
    # W-49. The romertall parts the operative text names, in romertall order.
    # EMPTY MEANS REFUSED, not "names none": the reader only ever returns a
    # non-empty tuple, so callers need no second flag to tell "no list here"
    # from "a list the reader could not account for" — both refuse.
    named_part_labels: tuple[str, ...] = ()
    # W-51. The acts this instrument cites appear in it only as HJEMMEL: its own
    # commencement action is about some other document. Read at parse time, from
    # the two pieces of evidence that are in hand there and nowhere else — the
    # ``Endrer`` block and the operative text — and consumed by every route that
    # refutes a claim from a sibling set. Defaults to False, which is the safe
    # value: an unproven sibling counts and refutes.
    cites_acts_as_hjemmel_only: bool = False
    # W-53. The widened whole-act route's SCOPE proof, in one flag, because both
    # halves of it are things only the parser can see: the instrument has exactly
    # one operative block, that block's text commences the act as a whole, and it
    # clears W-51's carve-out fence. Stored as the conjunction rather than as two
    # fields on purpose — the polarity of this gate is that over-authorization is
    # the danger, and a single conjunctive flag cannot be assembled into an
    # authorizing candidate one half at a time. ``whole_act_operative_text``
    # remains separately readable beside it, so the route can still assert its
    # text conjunct in its own right.
    widened_whole_act_scope: bool = False
    # W-73. The widened route's text conjunct, proven the third way: the
    # operative clause's subject is the cited act named by TITLE. Kept as its own
    # field beside ``whole_act_operative_text`` rather than folded into it,
    # because the two readers do not serve the same routes — W-47's multi-part
    # route asserts ``whole_act_operative_text`` and must keep reading exactly
    # what it read before, while W-53's act-level route accepts either proof.
    # Recording which one carried a grant is also the honest receipt: a lane
    # whose evidence plane cannot say WHY it authorized is a lane that cannot be
    # audited.
    title_cited_whole_act_scope: bool = False
    # W-100. The section-scoped statement reader's total outcome over the
    # operative text (``commencement_scope.read_no_commencement_scope_statements``).
    # Typed statements, read at parse time where the blocks are in hand, and
    # consumed only by the section-scoped route; every older route reads exactly
    # what it read before. ``total`` False means the reader refused, and the
    # refusing sentence is on the reading for the audit.
    scope_reading: NOCommencementScopeReading = NOCommencementScopeReading()
    # W-100. How many forskrift-only consequential blocks the widened route's
    # single-block reader set aside (``Fra samme tidspunkt oppheves § 2-5 … i
    # forskrift …``). Zero for every instrument that is not of that shape.
    forskrift_blocks_dropped: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "archive": self.archive,
            "member_name": self.member_name,
            "title": self.title,
            "affected_law_ids": list(self.affected_law_ids),
            "effective_dates": list(self.effective_dates),
            "scope_status": self.scope_status,
            "source_excerpt": self.source_excerpt,
            "rule_id": self.rule_id,
            "replay_authorized": self.replay_authorized,
            "changed_law_ids": list(self.changed_law_ids),
            "commenced_section_labels": list(self.commenced_section_labels),
            "whole_act_operative_text": self.whole_act_operative_text,
            "named_part_labels": list(self.named_part_labels),
            "cites_acts_as_hjemmel_only": self.cites_acts_as_hjemmel_only,
            "widened_whole_act_scope": self.widened_whole_act_scope,
            "title_cited_whole_act_scope": self.title_cited_whole_act_scope,
            "scope_reading": self.scope_reading.to_dict(),
            "forskrift_blocks_dropped": self.forskrift_blocks_dropped,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "NOCommencementInstrumentCandidate":
        raw_affected_law_ids = data.get("affected_law_ids", [])
        raw_effective_dates = data.get("effective_dates", [])
        affected_law_ids = (
            tuple(item for item in raw_affected_law_ids if isinstance(item, str))
            if isinstance(raw_affected_law_ids, list)
            else ()
        )
        effective_dates = (
            tuple(item for item in raw_effective_dates if isinstance(item, str))
            if isinstance(raw_effective_dates, list)
            else ()
        )

        def _str_tuple(key: str) -> tuple[str, ...]:
            raw = data.get(key, [])
            if not isinstance(raw, list):
                return ()
            return tuple(item for item in raw if isinstance(item, str))

        return cls(
            changed_law_ids=_str_tuple("changed_law_ids"),
            commenced_section_labels=_str_tuple("commenced_section_labels"),
            named_part_labels=_str_tuple("named_part_labels"),
            source_id=str(data["source_id"]),
            locator=str(data["locator"]),
            archive=str(data.get("archive", "")),
            member_name=str(data.get("member_name", "")),
            title=str(data.get("title", "")),
            affected_law_ids=affected_law_ids,
            effective_dates=effective_dates,
            scope_status=NOCommencementScopeStatus(str(data.get("scope_status", "unresolved"))),
            source_excerpt=str(data.get("source_excerpt", "")),
            replay_authorized=bool(data.get("replay_authorized", False)),
            whole_act_operative_text=bool(data.get("whole_act_operative_text", False)),
            cites_acts_as_hjemmel_only=bool(data.get("cites_acts_as_hjemmel_only", False)),
            widened_whole_act_scope=bool(data.get("widened_whole_act_scope", False)),
            title_cited_whole_act_scope=bool(
                data.get("title_cited_whole_act_scope", False)
            ),
            scope_reading=NOCommencementScopeReading.from_dict(
                cast(dict[str, Any], data.get("scope_reading", {}) or {})
            ),
            forskrift_blocks_dropped=int(cast(int, data.get("forskrift_blocks_dropped", 0) or 0)),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentResidual:
    rule_id: str
    reason: str
    clause_text: str
    blocking: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "family": "temporal_recovery",
            "phase": "parse",
            "reason": self.reason,
            "clause_text": self.clause_text[:400],
            "blocking": self.blocking,
            "strict_disposition": "block" if self.blocking else "record",
        }


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentParseResult:
    parse_status: NOCommencementParseStatus
    candidate: NOCommencementInstrumentCandidate | None = None
    residuals: tuple[NOCommencementInstrumentResidual, ...] = ()


@dataclass(frozen=True, slots=True)
class NOCommencementInstrumentCoverage:
    total_instruments: int = 0
    candidates: int = 0
    benign_non_commencement: int = 0
    blocked_unresolved: int = 0

    def is_partition(self) -> bool:
        return self.total_instruments == (
            self.candidates + self.benign_non_commencement + self.blocked_unresolved
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "total_instruments": self.total_instruments,
            "candidates": self.candidates,
            "benign_non_commencement": self.benign_non_commencement,
            "blocked_unresolved": self.blocked_unresolved,
        }

    @classmethod
    def from_dict(cls, data: object) -> "NOCommencementInstrumentCoverage":
        if not isinstance(data, dict):
            raise NOCommencementInstrumentCoverageError(
                f"{NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID}: expected an object"
            )
        typed_data = cast(dict[str, object], data)

        def count(key: str) -> int:
            value = typed_data.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise NOCommencementInstrumentCoverageError(
                    f"{NO_COMMENCEMENT_INSTRUMENT_COVERAGE_INVALID}: "
                    f"{key} must be a non-negative integer"
                )
            return value

        return cls(
            total_instruments=count("total_instruments"),
            candidates=count("candidates"),
            benign_non_commencement=count("benign_non_commencement"),
            blocked_unresolved=count("blocked_unresolved"),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementAuthorizationReceipt:
    """One unresolved amendment act re-dated by a whole-act instrument."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    effective_date: str

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument authorized an unresolved amendment act: "
                "the act takes the instrument's whole-act commencement date."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_date=self.effective_date,
        )


@dataclass(frozen=True, slots=True)
class NOCommencementRefusalReceipt:
    """One (instrument, unresolved act) pair the authorization gate refused."""

    act_source_id: str
    instrument_source_id: str
    failed_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...]
    parse_status: NOCommencementParseStatus
    scope_status: NOCommencementScopeStatus
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_EXECUTION_REFUSED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument cites an unresolved amendment act but fails the "
                "execution-authorization gate; it stays evidence and re-dates nothing."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_id=self.instrument_source_id,
            failed_conjuncts=[str(conjunct) for conjunct in self.failed_conjuncts],
            parse_status=str(self.parse_status),
            scope_status=str(self.scope_status),
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementDateConflictReceipt:
    """Two instruments commencing one act at different dates; both refused."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_EXECUTION_DATE_CONFLICT,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instruments give one amendment act contradictory whole-act "
                "commencement dates; neither date is applied."
            ),
            blocking=True,
            strict_disposition="block",
            quirks_disposition=QuirksDisposition.BLOCK,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementWidenedWholeActAuthorizationReceipt:
    """One unresolved amendment act re-dated by a READ whole-act text.

    Carries the same three fields as :class:`NOCommencementAuthorizationReceipt`
    and lands in the same act-level date map, plus the conjuncts it passed. Its
    own rule id, for the reason W-47 took one: the two act-level routes prove the
    same conclusion from different evidence, and a pin that could not tell them
    apart would move for either.
    """

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    effective_date: str
    passed_conjuncts: tuple[NOCommencementWidenedWholeActAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument's single operative block commences an "
                "unresolved amendment act as a WHOLE — naming no subdivision of it and no "
                "exception, with the act itself as the commencement clause's subject — and "
                "no later instrument commences anything of it; the act takes that date."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_date=self.effective_date,
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementWidenedWholeActDateConflictReceipt:
    """Two READ whole-act texts commencing one act at different dates; both refused."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_WIDENED_WHOLE_ACT_EXECUTION_DATE_CONFLICT,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instruments whose operative texts each commence one "
                "amendment act as a whole give it contradictory dates; neither date is "
                "applied."
            ),
            blocking=True,
            strict_disposition="block",
            quirks_disposition=QuirksDisposition.BLOCK,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementPartAuthorizationReceipt:
    """One PART of one multi-part amending act, dated by one instrument.

    ``law_id`` is not decoration beside ``part_label``: it is how the
    authorization is applied. A part resolves to exactly one law (the gate
    refuses otherwise), and the act's ops are keyed by law, so "this part's ops"
    and "this act's ops for this law" are the same set of ops.
    """

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_date: str
    passed_conjuncts: tuple[NOCommencementPartAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_PART_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument authorized ONE part of a staged "
                "multi-part amendment act: the act's operations on that part's law take "
                "the instrument's date; every other part stays as unresolved as before."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_date=self.effective_date,
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementMultiPartAuthorizationReceipt:
    """One part of a multi-part act dated by a WHOLE-ACT-text instrument.

    Carries the same fields as the single-part receipt and lands in the same
    ``part_scoped_effective_dates`` map, but keeps its own rule id so the two
    routes' grants stay separately countable: they prove different things, and
    a corpus pin that could not tell them apart would move for either.
    """

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_date: str
    spanned_part_labels: tuple[str, ...]
    passed_conjuncts: tuple[NOCommencementMultiPartAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_MULTI_PART_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument commences a multi-part amendment act as a "
                "WHOLE, so each part its Endrer header names takes the instrument's date; "
                "parts the header does not name stay as unresolved as before."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_date=self.effective_date,
            spanned_part_labels=list(self.spanned_part_labels),
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementNamedPartListAuthorizationReceipt:
    """One part of a multi-part act dated by an instrument that NAMES it.

    Same fields as the other two part receipts and the same landing place, plus
    the list the instrument's own text named — which is what a reader of this
    receipt needs in order to check the subset claim by hand. Its own rule id,
    for the same reason W-47 took one: the three routes prove different things
    and a pin that could not tell them apart would move for any of them.
    """

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_date: str
    spanned_part_labels: tuple[str, ...]
    named_part_labels: tuple[str, ...]
    passed_conjuncts: tuple[NOCommencementNamedPartListAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_NAMED_PART_LIST_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument names the romertall parts it commences and "
                "that list covers every part the act's Endrer header spans, so each of those "
                "parts takes the instrument's date; parts the header does not name, and any "
                "part a later instrument may still touch, stay as unresolved as before."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_date=self.effective_date,
            spanned_part_labels=list(self.spanned_part_labels),
            named_part_labels=list(self.named_part_labels),
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementPartDateConflictReceipt:
    """Two instruments commencing one part at different dates; both refused."""

    act_source_id: str
    instrument_source_ids: tuple[str, ...]
    part_label: str
    law_id: str
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_PART_EXECUTION_DATE_CONFLICT,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instruments give one part of an amendment act "
                "contradictory commencement dates; neither date is applied."
            ),
            blocking=True,
            strict_disposition="block",
            quirks_disposition=QuirksDisposition.BLOCK,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            part_label=self.part_label,
            law_id=self.law_id,
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementSectionScopeAuthorizationReceipt:
    """W-100. One (act, law) binding dated below binding level.

    ``binding_date`` is the date every op of the act on this law takes unless a
    finer entry says otherwise; ``None`` when only sections were dated.
    ``section_dates`` are the per-section dates; ``excluded_section_labels`` the
    sections carved out and still undated (restricted to sections the act's
    ops actually target); ``qualified_refused_labels`` the sections the text
    named with a ledd-level qualifier in a granting position, which this route
    refuses to date. ``complete`` says whether every targeted op of the binding
    now resolves to a date.
    """

    act_source_id: str
    law_id: str
    instrument_source_ids: tuple[str, ...]
    binding_date: str | None
    section_dates: tuple[tuple[str, str], ...]
    excluded_section_labels: tuple[str, ...]
    qualified_refused_labels: tuple[str, ...]
    unbound_section_labels: tuple[str, ...]
    complete: bool
    passed_conjuncts: tuple[NOCommencementSectionScopeAuthorizationConjunct, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_AUTHORIZED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway commencement instrument(s) dated ONE binding of an amendment act "
                "below binding level: a binding date and/or per-section dates, with the "
                "carved-out sections recorded; the act's other bindings stay as they were."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_ids=list(self.instrument_source_ids),
            law_id=self.law_id,
            binding_date=self.binding_date,
            section_dates=[[label, date] for label, date in self.section_dates],
            excluded_section_labels=list(self.excluded_section_labels),
            qualified_refused_labels=list(self.qualified_refused_labels),
            unbound_section_labels=list(self.unbound_section_labels),
            complete=self.complete,
            passed_conjuncts=[str(conjunct) for conjunct in self.passed_conjuncts],
        )


@dataclass(frozen=True, slots=True)
class NOCommencementSectionScopeDateConflictReceipt:
    """W-100. Two statements gave one key two dates; the key dates nothing."""

    act_source_id: str
    law_id: str
    section_label: str
    instrument_source_ids: tuple[str, ...]
    effective_dates: tuple[str, ...]

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_DATE_CONFLICT,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway section-scoped commencement statements disagree on the date of one "
                "binding or section; the whole binding is refused rather than resolved."
            ),
            blocking=True,
            strict_disposition="block",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            law_id=self.law_id,
            section_label=self.section_label,
            instrument_source_ids=list(self.instrument_source_ids),
            effective_dates=list(self.effective_dates),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementSectionScopeRefusalReceipt:
    """W-100. The reader read the text, the gate could not resolve it."""

    act_source_id: str
    instrument_source_id: str
    reason: str

    def to_diagnostic_detail(self) -> dict[str, Any]:
        return diagnostic_detail(
            rule_id=NO_COMMENCEMENT_SECTION_SCOPE_EXECUTION_REFUSED,
            family="temporal_recovery",
            phase="temporal",
            reason=(
                "Norway section-scoped commencement statements were read in full but a "
                "scope term could not be resolved against the act; the pair re-dates nothing."
            ),
            blocking=False,
            strict_disposition="record",
            quirks_disposition=QuirksDisposition.RECORD,
            source_id=self.act_source_id,
            instrument_source_id=self.instrument_source_id,
            refusal=self.reason,
        )


@dataclass(frozen=True, slots=True)
class NOCommencementActPartEvidence:
    """What the gate needs to know about ONE amendment act's part structure.

    Supplied by the caller that owns the artifacts (``index.py``); the gate
    computes none of it and parses no act XML.
    """

    part_law_ids: Mapping[str, str]
    """``romertall`` label -> the law that part amends. Parts that resolve no
    law of their own are simply absent."""

    bound_law_ids: tuple[str, ...]
    """The laws the act's lowered ops actually bind."""

    law_section_labels: Mapping[str, frozenset[str]]
    """law -> the section labels this act's ops on that law target."""

    unsectioned_op_laws: tuple[str, ...] = ()
    """W-100. The laws on which at least one of this act's ops targets no
    section (a chapter heading, a whole-part directive). Such an op can only
    take a BINDING-level date, so a law here is never section-complete without
    one."""


@dataclass(frozen=True, slots=True)
class NOCommencementExecutionAuthorization:
    """The gate's total outcome: the instruments, and a receipt per decision."""

    instruments: tuple[NOCommencementInstrumentCandidate, ...] = ()
    authorizations: tuple[NOCommencementAuthorizationReceipt, ...] = ()
    refusals: tuple[NOCommencementRefusalReceipt, ...] = ()
    conflicts: tuple[NOCommencementDateConflictReceipt, ...] = ()
    part_authorizations: tuple[NOCommencementPartAuthorizationReceipt, ...] = ()
    part_conflicts: tuple[NOCommencementPartDateConflictReceipt, ...] = ()
    multi_part_authorizations: tuple[NOCommencementMultiPartAuthorizationReceipt, ...] = ()
    named_part_list_authorizations: tuple[
        NOCommencementNamedPartListAuthorizationReceipt, ...
    ] = ()
    widened_whole_act_authorizations: tuple[
        NOCommencementWidenedWholeActAuthorizationReceipt, ...
    ] = ()
    widened_whole_act_conflicts: tuple[
        NOCommencementWidenedWholeActDateConflictReceipt, ...
    ] = ()
    section_scoped_authorizations: tuple[
        NOCommencementSectionScopeAuthorizationReceipt, ...
    ] = ()
    section_scoped_conflicts: tuple[NOCommencementSectionScopeDateConflictReceipt, ...] = ()
    section_scoped_refusals: tuple[NOCommencementSectionScopeRefusalReceipt, ...] = ()

    def section_scoped_landings(
        self,
    ) -> dict[str, list[NOCommencementSectionScopeAuthorizationReceipt]]:
        """act -> its section-scoped receipts, one per dated binding. W-100.

        A fourth landing place, beside the two maps below, because what it
        carries is neither an act date nor a binding date but a binding's date
        PLUS its per-section overrides and carve-outs; the index writes it into
        the entry's ``section_scoped_*`` fields and the replay resolves each op
        against it.
        """
        out: dict[str, list[NOCommencementSectionScopeAuthorizationReceipt]] = {}
        for receipt in self.section_scoped_authorizations:
            out.setdefault(receipt.act_source_id, []).append(receipt)
        return out

    def authorized_effective_dates(self) -> dict[str, str]:
        """act -> date, the act-level dates BOTH whole-act routes granted.

        Both routes grant the same KIND of thing — one date for the act's whole op
        stream — and every consumer wants one map, exactly as the three part
        routes share ``part_authorized_effective_dates``. Written widened-first so
        that if the two ever proposed the same act the older, shape-proved
        authorization would win; they cannot, because the widened route declines
        any act the shipped one so much as proposed a date for.
        """
        dates = {
            receipt.act_source_id: receipt.effective_date
            for receipt in self.widened_whole_act_authorizations
        }
        dates.update(
            {
                receipt.act_source_id: receipt.effective_date
                for receipt in self.authorizations
            }
        )
        return dates

    def part_authorized_effective_dates(self) -> dict[str, dict[str, str]]:
        """act -> {law -> date}, the per-binding dates the part routes granted.

        All three part routes land here: they grant the same KIND of thing (one
        binding's date) and every consumer wants one map. They are written
        weakest-proof first so that if two ever proposed the same binding the
        older, narrower proof would win; measured over the corpus none of the
        three ever overlap, and each later route refuses a key an earlier one
        already holds before it gets this far.
        """
        out: dict[str, dict[str, str]] = {}
        for named_receipt in self.named_part_list_authorizations:
            out.setdefault(named_receipt.act_source_id, {})[
                named_receipt.law_id
            ] = named_receipt.effective_date
        for multi_receipt in self.multi_part_authorizations:
            out.setdefault(multi_receipt.act_source_id, {})[
                multi_receipt.law_id
            ] = multi_receipt.effective_date
        for receipt in self.part_authorizations:
            out.setdefault(receipt.act_source_id, {})[receipt.law_id] = receipt.effective_date
        return out


def no_commencement_act_id_from_law_id(law_id: str) -> str:
    """Alias an instrument's ``basedOn`` law id onto the amendment-act id.

    Instruments cite the amending act by its law id (``no/lov/<date>-<num>``)
    while the index keys the same act by its Lovtidend id
    (``no/lovtid/<date>-<num>``); the date-and-number segment is shared.
    Returns ``""`` for an id that is not in law form.
    """
    if not law_id.startswith("no/lov/"):
        return ""
    return "no/lovtid/" + law_id.removeprefix("no/lov/")


def authorize_no_commencement_instruments(
    parsed_instruments: Sequence[
        tuple[NOCommencementParseStatus, NOCommencementInstrumentCandidate]
    ],
    *,
    offered_act_ids: Collection[str],
    act_part_evidence: Mapping[str, NOCommencementActPartEvidence] | None = None,
) -> NOCommencementExecutionAuthorization:
    """Gate already-parsed instruments into whole-act re-dating authorizations.

    Consumes parse results; it never re-parses instrument XML and never
    reclassifies a parse. An (instrument, act) pair authorizes only when every
    conjunct of ``NOCommencementAuthorizationConjunct`` holds and the cited law
    id aliases to an act in ``offered_act_ids``.

    ``offered_act_ids`` is whatever set the caller judges re-datable by an
    official instrument — this gate does not define it and does not inspect the
    acts' statuses. The production offering policy lives with the comprehension
    that defines it, in ``index.py``'s
    ``_authorize_no_commencement_instruments_into_index``.

    An instrument citing no offered act authorizes nothing and records nothing:
    that is the enabling-statute filter — an instrument commencing a *forskrift*
    cites the forskrift's hjemmel statutes, which are principal laws, not
    offered amendment acts.

    W-39: when the whole-act conjuncts fail, the pair is offered to the
    PART-SCOPED route (``NOCommencementPartAuthorizationConjunct``) before it is
    refused. The two routes are ordered, not alternative — an act the whole-act
    route dates is never re-examined per part, so the coarser, older
    authorization always wins where it exists. ``act_part_evidence`` left at
    ``None`` disables the part route entirely and this function behaves exactly
    as it did before W-39.

    W-47 adds a THIRD route in the same ordering, tried only where the
    single-part route declined: a header spanning several parts under an
    operative text that commences the whole act. It reads one thing the other
    two do not — the dates every OTHER instrument gives the same act, gathered
    below into ``instrument_dates_by_act`` — because its claim is about the act
    as a whole, and a later instrument is exactly what refutes such a claim.

    W-49 adds a FOURTH, last in the same ordering: an instrument whose text
    names the parts it commences. Its claim is about those parts only, so it
    needs more of each sibling than a date — the sibling's own declared laws and
    its own named parts, gathered below into ``instrument_scopes_by_act`` — to
    tell the staged pattern (a later instrument on OTHER parts, which does not
    refute) from a genuine contradiction.

    W-51 adds no route and changes no offering. It changes WHO IS A SIBLING —
    once, for all three refuting conjuncts, at the two maps below — and gives
    the whole-act route the act-level refutation the other two already had.
    Being a property of the ACT rather than of any one candidate, that conjunct
    is asserted where the act's proposals have already been gathered and
    reconciled, not in :func:`_failed_authorization_conjuncts`, whose signature
    says plainly that it sees one candidate and no act.

    W-53 adds a FIFTH route, and it does not slot into the existing ordering: it
    is act-level, so it sits between the shipped whole-act route and the three
    part routes, and it is resolved there. Two consequences worth stating rather
    than leaving to be inferred from the code:

    * a pair is offered to it and STILL offered to the part routes. The routes
      claim different things — one date for the act against one date per binding
      — so a widened claim that is later refuted or contradicted must leave the
      part grants standing exactly as they were. Nothing consumes the pair.
    * where it grants, the part routes yield to it per ACT, on exactly the terms
      they already yield to the shipped whole-act route: the act carries the date
      those part grants would have given it, so the proposals are dropped without
      a receipt. Measured, that absorbs most of the part lane, and the retirement
      is the deliberate, signed-off consequence of the widening rather than a
      side effect of it.
    """
    offered = frozenset(offered_act_ids)
    part_evidence = dict(act_part_evidence or {})
    # act -> [(instrument id, date)] over every parsed candidate that commences
    # something of it, authorized or not: what refutes "the whole act commenced
    # then" is that another instrument commenced part of it later, whatever that
    # instrument's own scope was and whether or not it went on to authorize
    # anything itself.
    instrument_dates_by_act: dict[str, list[tuple[str, str]]] = {}
    # act -> [(instrument id, date, declared laws, named parts)], the same
    # population with the two scope witnesses the part-list route's refutation
    # needs. Kept beside rather than folded into the pair list above so W-47's
    # conjunct keeps reading exactly what it read before.
    instrument_scopes_by_act: dict[
        str, list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]
    ] = {}
    for _parse_status, sibling in parsed_instruments:
        # W-51. THE sharpening, and it is applied once, here, so all three
        # refuting conjuncts read one sibling set: an instrument whose own
        # commencement action is about another document does not speak to when
        # this act came into force, however prominently the act appears in its
        # ``basedOn``. Dropping a sibling can only ever REMOVE a refutation, so
        # no route can lose a grant to this line.
        if sibling.cites_acts_as_hjemmel_only:
            continue
        for sibling_law_id in sibling.affected_law_ids:
            sibling_act_id = no_commencement_act_id_from_law_id(sibling_law_id)
            if not sibling_act_id:
                continue
            for sibling_date in sibling.effective_dates:
                instrument_dates_by_act.setdefault(sibling_act_id, []).append(
                    (sibling.source_id, sibling_date)
                )
                instrument_scopes_by_act.setdefault(sibling_act_id, []).append(
                    (
                        sibling.source_id,
                        sibling_date,
                        sibling.changed_law_ids,
                        sibling.named_part_labels,
                    )
                )
    proposals: dict[str, dict[str, list[str]]] = {}
    part_proposals: dict[
        tuple[str, str, str], dict[str, list[str]]
    ] = {}
    part_conjuncts: dict[
        tuple[str, str, str], tuple[NOCommencementPartAuthorizationConjunct, ...]
    ] = {}
    multi_part_proposals: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    multi_part_spans: dict[tuple[str, str, str], tuple[str, ...]] = {}
    named_part_list_proposals: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    named_part_list_spans: dict[tuple[str, str, str], tuple[str, ...]] = {}
    widened_proposals: dict[str, dict[str, list[str]]] = {}
    # W-100. act, law -> [(instrument id, its proposal)], every instrument that
    # read a section-scoped statement about that binding; resolved per key
    # below, after every older route has had its turn.
    section_scope_proposals: dict[
        tuple[str, str], list[tuple[str, _SectionScopeProposal]]
    ] = {}
    section_scope_refusals: list[NOCommencementSectionScopeRefusalReceipt] = []
    refusals: list[NOCommencementRefusalReceipt] = []
    for parse_status, candidate in parsed_instruments:
        cited_act_ids = tuple(
            sorted(
                {
                    act_id
                    for act_id in (
                        no_commencement_act_id_from_law_id(law_id)
                        for law_id in candidate.affected_law_ids
                    )
                    if act_id in offered
                }
            )
        )
        if not cited_act_ids:
            continue
        failed_conjuncts = _failed_authorization_conjuncts(parse_status, candidate)
        if failed_conjuncts:
            for act_id in cited_act_ids:
                # W-53. The widened route proposes first and CONSUMES NOTHING:
                # its claim is act-level, the part routes' are per-binding, and
                # an act-level claim that the conflict branch or the refutation
                # later throws out must leave those part grants exactly as they
                # would have been. So no ``continue`` here — every pair the
                # widened route proposes is still offered to all three below.
                if _widened_whole_act_authorization_scope(
                    parse_status, candidate, failed_conjuncts
                ):
                    widened_proposals.setdefault(act_id, {}).setdefault(
                        candidate.effective_dates[0], []
                    ).append(candidate.source_id)
                part_match = _part_scoped_authorization_scope(
                    parse_status,
                    candidate,
                    failed_conjuncts,
                    part_evidence.get(act_id),
                )
                if part_match is not None:
                    part_label, law_id, passed = part_match
                    key = (act_id, part_label, law_id)
                    part_proposals.setdefault(key, {}).setdefault(
                        candidate.effective_dates[0], []
                    ).append(candidate.source_id)
                    part_conjuncts[key] = passed
                    continue
                multi_part_match = _multi_part_scoped_authorization_scope(
                    parse_status,
                    candidate,
                    failed_conjuncts,
                    part_evidence.get(act_id),
                    instrument_dates_by_act.get(act_id, ()),
                )
                if multi_part_match is not None:
                    for part_label, law_id in multi_part_match:
                        key = (act_id, part_label, law_id)
                        multi_part_proposals.setdefault(key, {}).setdefault(
                            candidate.effective_dates[0], []
                        ).append(candidate.source_id)
                        multi_part_spans[key] = tuple(
                            sorted(label for label, _law in multi_part_match)
                        )
                    continue
                named_part_list_match = _named_part_list_authorization_scope(
                    parse_status,
                    candidate,
                    failed_conjuncts,
                    part_evidence.get(act_id),
                    instrument_scopes_by_act.get(act_id, ()),
                )
                if named_part_list_match is not None:
                    for part_label, law_id in named_part_list_match:
                        key = (act_id, part_label, law_id)
                        named_part_list_proposals.setdefault(key, {}).setdefault(
                            candidate.effective_dates[0], []
                        ).append(candidate.source_id)
                        named_part_list_spans[key] = tuple(
                            sorted(label for label, _law in named_part_list_match)
                        )
                    continue
                # W-100. The section-scoped route proposes LAST and, like the
                # widened route, consumes nothing here: the generic refusal below
                # is still written and is withdrawn only for a pair the route
                # goes on to GRANT. A pair the reader read but the gate could not
                # resolve gets its own receipt with the reason, beside the
                # generic one.
                section_match, section_reason = _section_scoped_authorization_scope(
                    parse_status,
                    candidate,
                    failed_conjuncts,
                    part_evidence.get(act_id),
                    part_evidence,
                )
                if section_match is not None:
                    for law_id, proposal in section_match.items():
                        section_scope_proposals.setdefault((act_id, law_id), []).append(
                            (candidate.source_id, proposal)
                        )
                elif section_reason:
                    section_scope_refusals.append(
                        NOCommencementSectionScopeRefusalReceipt(
                            act_source_id=act_id,
                            instrument_source_id=candidate.source_id,
                            reason=section_reason,
                        )
                    )
                refusals.append(
                    NOCommencementRefusalReceipt(
                        act_source_id=act_id,
                        instrument_source_id=candidate.source_id,
                        failed_conjuncts=failed_conjuncts,
                        parse_status=parse_status,
                        scope_status=candidate.scope_status,
                        effective_dates=candidate.effective_dates,
                    )
                )
            continue
        for act_id in cited_act_ids:
            proposals.setdefault(act_id, {}).setdefault(
                candidate.effective_dates[0], []
            ).append(candidate.source_id)

    authorizations: list[NOCommencementAuthorizationReceipt] = []
    conflicts: list[NOCommencementDateConflictReceipt] = []
    authorized_instrument_ids: set[str] = set()
    for act_id, instrument_ids_by_date in sorted(proposals.items()):
        if len(instrument_ids_by_date) > 1:
            conflicts.append(
                NOCommencementDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        # W-51. The act-level refutation, and it is asserted HERE — after the
        # date-conflict branch, on the single surviving proposal — rather than
        # while proposals are gathered. Two instruments giving the act two
        # different whole-act dates is a CONFLICT, and a conflict blocks: were
        # the refutation applied upstream it would quietly resolve every such
        # disagreement in favour of the later date and the blocking receipt
        # would never be written. Measured, the corpus has no whole-act date
        # conflict at all, so the ordering costs nothing today and keeps the
        # older, louder verdict where the two could ever meet.
        if _act_has_later_commencement_sibling(
            effective_date,
            instrument_source_ids,
            instrument_dates_by_act.get(act_id, ()),
        ):
            for instrument_source_id in sorted(set(instrument_source_ids)):
                refusals.append(
                    NOCommencementRefusalReceipt(
                        act_source_id=act_id,
                        instrument_source_id=instrument_source_id,
                        failed_conjuncts=(
                            NOCommencementAuthorizationConjunct.ACT_HAS_NO_LATER_INSTRUMENT,
                        ),
                        parse_status=NOCommencementParseStatus.CANDIDATE,
                        scope_status=NOCommencementScopeStatus.WHOLE_ACT,
                        effective_dates=(effective_date,),
                    )
                )
            continue
        authorizations.append(
            NOCommencementAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                effective_date=effective_date,
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # W-53. The widened whole-act route resolves next, and it yields to the
    # shipped one on a STRONGER rule than "was it authorized": an act the shipped
    # route so much as PROPOSED a date for is skipped outright. The two routes
    # reach the same act-level conclusion, so a shipped proposal that did not
    # authorize is a decision about this very claim — it either conflicted with
    # another shape-proved instrument or was refuted by a later sibling — and it
    # has already written its own receipt. Re-deciding it here on a read text
    # would in particular resolve a shipped/widened date disagreement silently in
    # favour of whichever date the shipped route's refutation happened to leave
    # standing, which is the ordering mistake W-51 found and fixed.
    whole_act_proposed = frozenset(proposals)
    widened_whole_act_authorizations: list[
        NOCommencementWidenedWholeActAuthorizationReceipt
    ] = []
    widened_whole_act_conflicts: list[
        NOCommencementWidenedWholeActDateConflictReceipt
    ] = []
    for act_id, instrument_ids_by_date in sorted(widened_proposals.items()):
        if act_id in whole_act_proposed:
            continue
        if len(instrument_ids_by_date) > 1:
            widened_whole_act_conflicts.append(
                NOCommencementWidenedWholeActDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        # ``ACT_HAS_NO_LATER_INSTRUMENT``, asserted here rather than upstream for
        # the reason spelled out on the conjunct and on the shipped route's own
        # copy of it twenty lines up: the conflict branch must get first refusal,
        # or contradictory dates would be resolved in favour of the later one
        # instead of blocking.
        if _act_has_later_commencement_sibling(
            effective_date,
            instrument_source_ids,
            instrument_dates_by_act.get(act_id, ()),
        ):
            continue
        widened_whole_act_authorizations.append(
            NOCommencementWidenedWholeActAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                effective_date=effective_date,
                passed_conjuncts=tuple(
                    NOCommencementWidenedWholeActAuthorizationConjunct
                ),
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # A pair the widened route GRANTED must not also carry the whole-act
    # route's refusal. The refusal is written up in the loop above, before any
    # route has resolved, and its own reason says the instrument "stays evidence
    # and re-dates nothing" — which is false once the act takes its date. The
    # three part routes avoid this by consuming the pair on match; this route
    # cannot, because its proposal has to leave the part routes their chance, so
    # it withdraws the refusal here instead. Only on a GRANT: a widened claim
    # that the conflict branch or the refutation threw out re-dates nothing, and
    # the whole-act route's refusal is then exactly the right receipt for it.
    widened_granted_pairs = {
        (receipt.act_source_id, instrument_source_id)
        for receipt in widened_whole_act_authorizations
        for instrument_source_id in receipt.instrument_source_ids
    }
    if widened_granted_pairs:
        refusals = [
            refusal
            for refusal in refusals
            if (refusal.act_source_id, refusal.instrument_source_id)
            not in widened_granted_pairs
        ]

    # An act EITHER act-level route already dated is not re-examined per part:
    # the coarser authorization stands, and a part proposal for it is dropped
    # without a receipt because the act already carries the date it would grant.
    whole_act_authorized = {
        receipt.act_source_id for receipt in authorizations
    } | {receipt.act_source_id for receipt in widened_whole_act_authorizations}
    part_authorizations: list[NOCommencementPartAuthorizationReceipt] = []
    part_conflicts: list[NOCommencementPartDateConflictReceipt] = []
    for (act_id, part_label, law_id), instrument_ids_by_date in sorted(part_proposals.items()):
        if act_id in whole_act_authorized:
            continue
        if len(instrument_ids_by_date) > 1:
            part_conflicts.append(
                NOCommencementPartDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    part_label=part_label,
                    law_id=law_id,
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        part_authorizations.append(
            NOCommencementPartAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                part_label=part_label,
                law_id=law_id,
                effective_date=effective_date,
                passed_conjuncts=part_conjuncts[(act_id, part_label, law_id)],
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # The multi-part route resolves last, and yields to both routes above it:
    # to the whole-act one per act, and to the single-part one per BINDING. A
    # key either already holds the date this route would grant or holds a
    # narrower proof of it, so the proposal is dropped without a receipt for the
    # same reason W-39's is. Measured over the corpus neither collision occurs.
    single_part_authorized_keys = {
        (receipt.act_source_id, receipt.part_label, receipt.law_id)
        for receipt in part_authorizations
    }
    multi_part_authorizations: list[NOCommencementMultiPartAuthorizationReceipt] = []
    for (act_id, part_label, law_id), instrument_ids_by_date in sorted(
        multi_part_proposals.items()
    ):
        if act_id in whole_act_authorized:
            continue
        if (act_id, part_label, law_id) in single_part_authorized_keys:
            continue
        if len(instrument_ids_by_date) > 1:
            part_conflicts.append(
                NOCommencementPartDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    part_label=part_label,
                    law_id=law_id,
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        multi_part_authorizations.append(
            NOCommencementMultiPartAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                part_label=part_label,
                law_id=law_id,
                effective_date=effective_date,
                spanned_part_labels=multi_part_spans[(act_id, part_label, law_id)],
                passed_conjuncts=tuple(NOCommencementMultiPartAuthorizationConjunct),
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # The named-part-list route resolves after all three, and yields to each of
    # them on the same terms: to the whole-act route per act, to the two
    # part-scoped ones per BINDING. Its proof is the newest and reads the most
    # prose, so where an older route already holds a key that key keeps its
    # older proof. Measured over the corpus none of the three collisions occur.
    multi_part_authorized_keys = {
        (receipt.act_source_id, receipt.part_label, receipt.law_id)
        for receipt in multi_part_authorizations
    }
    named_part_list_authorizations: list[
        NOCommencementNamedPartListAuthorizationReceipt
    ] = []
    for (act_id, part_label, law_id), instrument_ids_by_date in sorted(
        named_part_list_proposals.items()
    ):
        if act_id in whole_act_authorized:
            continue
        if (act_id, part_label, law_id) in single_part_authorized_keys:
            continue
        if (act_id, part_label, law_id) in multi_part_authorized_keys:
            continue
        if len(instrument_ids_by_date) > 1:
            part_conflicts.append(
                NOCommencementPartDateConflictReceipt(
                    act_source_id=act_id,
                    instrument_source_ids=tuple(
                        sorted(
                            source_id
                            for source_ids in instrument_ids_by_date.values()
                            for source_id in source_ids
                        )
                    ),
                    part_label=part_label,
                    law_id=law_id,
                    effective_dates=tuple(sorted(instrument_ids_by_date)),
                )
            )
            continue
        effective_date, instrument_source_ids = next(iter(instrument_ids_by_date.items()))
        named_part_list_authorizations.append(
            NOCommencementNamedPartListAuthorizationReceipt(
                act_source_id=act_id,
                instrument_source_ids=tuple(sorted(set(instrument_source_ids))),
                part_label=part_label,
                law_id=law_id,
                effective_date=effective_date,
                spanned_part_labels=named_part_list_spans[(act_id, part_label, law_id)],
                named_part_labels=_named_part_labels_of(
                    parsed_instruments, instrument_source_ids
                ),
                passed_conjuncts=tuple(NOCommencementNamedPartListAuthorizationConjunct),
            )
        )
        authorized_instrument_ids.update(instrument_source_ids)

    # W-100. The section-scoped route resolves last of all and yields to every
    # route above it on the terms they already use among themselves: to the two
    # act-level routes per act, to the three part routes per binding. What it
    # adds is a per-KEY conflict check finer than any of theirs — a binding date,
    # each section date, and the consistency of the two (a section dated
    # differently from a binding it was not carved out of is a contradiction,
    # not a refinement) — and it drops the WHOLE binding on any contradiction
    # rather than keeping the parts that happen to agree.
    named_part_list_authorized_keys = {
        (receipt.act_source_id, receipt.part_label, receipt.law_id)
        for receipt in named_part_list_authorizations
    }
    part_dated_bindings = {
        (act_id, law_id)
        for act_id, _label, law_id in (
            single_part_authorized_keys | multi_part_authorized_keys | named_part_list_authorized_keys
        )
    }
    section_scoped_authorizations: list[NOCommencementSectionScopeAuthorizationReceipt] = []
    section_scoped_conflicts: list[NOCommencementSectionScopeDateConflictReceipt] = []
    for (act_id, law_id), claims in sorted(section_scope_proposals.items()):
        if act_id in whole_act_authorized:
            continue
        if (act_id, law_id) in part_dated_bindings:
            continue
        instrument_ids = tuple(sorted({source_id for source_id, _proposal in claims}))
        binding_dates = sorted({p.binding_date for _s, p in claims if p.binding_date is not None})
        conflict: tuple[str, tuple[str, ...]] | None = None
        if len(binding_dates) > 1:
            conflict = ("", tuple(binding_dates))
        section_dates: dict[str, set[str]] = {}
        qualified_dates: dict[str, set[str]] = {}
        excluded: set[str] = set()
        for _source_id, proposal in claims:
            for label, date in proposal.section_dates.items():
                section_dates.setdefault(label, set()).add(date)
            for label, date in proposal.qualified_dates.items():
                qualified_dates.setdefault(label, set()).add(date)
            excluded.update(proposal.excluded)
        binding_date = binding_dates[0] if len(binding_dates) == 1 else None
        if conflict is None:
            # A whole-section date conflicts with any other date for that
            # section (another whole-section date, a ledd-level date, or a
            # binding date it was not carved out of). Two LEDD-level dates for
            # one section do not conflict with each other: ``§ 4-5 andre ledd``
            # and ``§ 4-5 første, tredje, fjerde og femte ledd`` commencing on
            # different days is the staged pattern itself
            # (``no/lovtid/2021-06-11-84`` under its 2021 and 2025 instruments).
            for label, dates in sorted(section_dates.items()):
                all_dates = set(dates) | qualified_dates.get(label, set())
                if len(all_dates) > 1:
                    conflict = (label, tuple(sorted(all_dates)))
                    break
                if (
                    binding_date is not None
                    and label not in excluded
                    and next(iter(dates)) != binding_date
                ):
                    conflict = (label, tuple(sorted(dates | {binding_date})))
                    break
            for label, dates in sorted(qualified_dates.items()):
                if conflict is not None or label in section_dates:
                    break
                if (
                    binding_date is not None
                    and label not in excluded
                    and any(date != binding_date for date in dates)
                ):
                    conflict = (label, tuple(sorted(dates | {binding_date})))
                    break
        if conflict is not None:
            section_label, dates = conflict
            section_scoped_conflicts.append(
                NOCommencementSectionScopeDateConflictReceipt(
                    act_source_id=act_id,
                    law_id=law_id,
                    section_label=section_label,
                    instrument_source_ids=instrument_ids,
                    effective_dates=dates,
                )
            )
            continue
        # A key whose every dated label was ledd-qualified dates nothing; it is
        # refused with that reason rather than landed as an empty grant, so the
        # binding keeps its whole-entry contingent skip instead of a per-op one.
        if binding_date is None and not section_dates:
            for instrument_source_id in instrument_ids:
                section_scope_refusals.append(
                    NOCommencementSectionScopeRefusalReceipt(
                        act_source_id=act_id,
                        instrument_source_id=instrument_source_id,
                        reason=f"every dated label of {law_id} is ledd-qualified",
                    )
                )
            continue
        evidence = part_evidence.get(act_id)
        targeted = set(evidence.law_section_labels.get(law_id, frozenset())) if evidence else set()
        has_unsectioned_ops = bool(evidence and law_id in evidence.unsectioned_op_laws)
        landed_sections = {label: next(iter(dates)) for label, dates in section_dates.items()}
        landed_excluded = sorted((excluded - set(landed_sections)) & targeted)
        qualified_refused = sorted(set(qualified_dates) - set(landed_sections))
        unbound = sorted((set(section_dates) | excluded) - targeted)
        # A targeted section is dated by its own entry, or by the binding date
        # when it was not carved out. A qualified-refused label that was not
        # carved out takes the binding date like any other (the consistency
        # check above has already established the two dates agree).
        dated_targets = {
            label
            for label in targeted
            if label in landed_sections or (binding_date is not None and label not in excluded)
        }
        complete = (
            bool(targeted or binding_date is not None)
            and not (targeted - dated_targets)
            and (binding_date is not None or not has_unsectioned_ops)
        )
        section_scoped_authorizations.append(
            NOCommencementSectionScopeAuthorizationReceipt(
                act_source_id=act_id,
                law_id=law_id,
                instrument_source_ids=instrument_ids,
                binding_date=binding_date,
                section_dates=tuple(sorted(landed_sections.items())),
                excluded_section_labels=tuple(landed_excluded),
                qualified_refused_labels=tuple(qualified_refused),
                unbound_section_labels=tuple(unbound),
                complete=complete,
                passed_conjuncts=tuple(NOCommencementSectionScopeAuthorizationConjunct),
            )
        )
        authorized_instrument_ids.update(instrument_ids)
    # A pair this route granted must not also carry the generic refusal, for
    # the reason W-53 gave: that receipt says the instrument re-dates nothing.
    section_granted_pairs = {
        (receipt.act_source_id, instrument_source_id)
        for receipt in section_scoped_authorizations
        for instrument_source_id in receipt.instrument_source_ids
    }
    if section_granted_pairs:
        refusals = [
            refusal
            for refusal in refusals
            if (refusal.act_source_id, refusal.instrument_source_id)
            not in section_granted_pairs
        ]

    return NOCommencementExecutionAuthorization(
        instruments=tuple(
            replace(
                candidate,
                replay_authorized=candidate.source_id in authorized_instrument_ids,
            )
            for _parse_status, candidate in parsed_instruments
        ),
        authorizations=tuple(authorizations),
        refusals=tuple(refusals),
        conflicts=tuple(conflicts),
        part_authorizations=tuple(part_authorizations),
        part_conflicts=tuple(part_conflicts),
        multi_part_authorizations=tuple(multi_part_authorizations),
        named_part_list_authorizations=tuple(named_part_list_authorizations),
        widened_whole_act_authorizations=tuple(widened_whole_act_authorizations),
        widened_whole_act_conflicts=tuple(widened_whole_act_conflicts),
        section_scoped_authorizations=tuple(section_scoped_authorizations),
        section_scoped_conflicts=tuple(section_scoped_conflicts),
        section_scoped_refusals=tuple(section_scope_refusals),
    )


def _named_part_labels_of(
    parsed_instruments: Sequence[
        tuple[NOCommencementParseStatus, NOCommencementInstrumentCandidate]
    ],
    instrument_source_ids: Sequence[str],
) -> tuple[str, ...]:
    """The union of the named part lists of the instruments granting one key.

    Sorted in romertall order. A one-element union in every measured case — a
    key with two granting instruments would have had to agree on the date, which
    the conflict branch above has already established.
    """
    wanted = set(instrument_source_ids)
    labels: set[str] = set()
    for _parse_status, candidate in parsed_instruments:
        if candidate.source_id in wanted:
            labels.update(candidate.named_part_labels)
    return tuple(sorted(labels, key=_roman_label_sort_key))


def _part_scoped_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
    evidence: "NOCommencementActPartEvidence | None",
) -> tuple[str, str, tuple[NOCommencementPartAuthorizationConjunct, ...]] | None:
    """Prove which single part this instrument commences, or return ``None``.

    Every conjunct of :class:`NOCommencementPartAuthorizationConjunct` must
    hold; there is no partial credit and no ranking among them. Returns
    ``(part label, law id, the conjuncts it passed)``.
    """
    if evidence is None:
        return None
    if len(candidate.effective_dates) != 1:
        return None
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return None
    if set(failed_whole_act_conjuncts) != {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    }:
        return None
    changed = set(candidate.changed_law_ids)
    if not changed:
        return None

    parts_by_law: dict[str, list[str]] = {}
    for part_label, law_id in evidence.part_law_ids.items():
        parts_by_law.setdefault(law_id, []).append(part_label)
    if any(len(labels) > 1 for labels in parts_by_law.values()):
        return None
    if any(law_id not in parts_by_law for law_id in evidence.bound_law_ids):
        return None
    if any(law_id not in parts_by_law for law_id in changed):
        return None
    part_labels = {parts_by_law[law_id][0] for law_id in changed}
    if len(part_labels) != 1:
        return None
    part_label = part_labels.pop()
    part_laws = {
        law_id for law_id, labels in parts_by_law.items() if labels[0] == part_label
    }
    if part_laws != changed:
        return None
    law_id = next(iter(changed))
    named_sections = set(candidate.commenced_section_labels)
    if named_sections and named_sections != set(
        evidence.law_section_labels.get(law_id, frozenset())
    ):
        return None
    return (
        part_label,
        law_id,
        tuple(NOCommencementPartAuthorizationConjunct),
    )


def _multi_part_scoped_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
    evidence: "NOCommencementActPartEvidence | None",
    instrument_dates_for_act: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...] | None:
    """Prove which SEVERAL parts this instrument commences, or return ``None``.

    Every conjunct of :class:`NOCommencementMultiPartAuthorizationConjunct` must
    hold; there is no partial credit, and in particular no per-part credit — the
    span authorizes whole or not at all, because what proves it is a single
    statement about the whole act. Returns the ``(part label, law id)`` pairs in
    part-label order.
    """
    if evidence is None:
        return None
    if len(candidate.effective_dates) != 1:
        return None
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return None
    if set(failed_whole_act_conjuncts) != {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    }:
        return None
    changed = set(candidate.changed_law_ids)
    if not changed:
        return None

    parts_by_law: dict[str, list[str]] = {}
    for part_label, law_id in evidence.part_law_ids.items():
        parts_by_law.setdefault(law_id, []).append(part_label)
    if any(len(labels) > 1 for labels in parts_by_law.values()):
        return None
    if any(law_id not in parts_by_law for law_id in evidence.bound_law_ids):
        return None
    if any(law_id not in parts_by_law for law_id in changed):
        return None
    spanned_labels = {parts_by_law[law_id][0] for law_id in changed}
    # One part is the W-39 route's business; it has already declined this pair
    # for some other reason, and re-deciding it here on weaker evidence would
    # overrule it.
    if len(spanned_labels) < 2:
        return None
    spanned_laws = {
        law_id for law_id, labels in parts_by_law.items() if labels[0] in spanned_labels
    }
    if spanned_laws != changed:
        return None
    if not candidate.whole_act_operative_text:
        return None
    named_sections = set(candidate.commenced_section_labels)
    if named_sections and any(
        named_sections != set(evidence.law_section_labels.get(law_id, frozenset()))
        for law_id in changed
    ):
        return None
    if _act_has_later_commencement_sibling(
        candidate.effective_dates[0], (candidate.source_id,), instrument_dates_for_act
    ):
        return None
    return tuple(
        sorted(
            (parts_by_law[law_id][0], law_id) for law_id in changed
        )
    )


def _widened_whole_act_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
) -> bool:
    """Does this pair's own evidence support an act-level claim? W-53.

    All-or-nothing, like the three scope functions above it, and returning a bare
    bool rather than a scope because an act-level claim has nothing to scope: the
    grant is "this act, every op, this date". Four of the five conjuncts of
    :class:`NOCommencementWidenedWholeActAuthorizationConjunct` are decided here,
    one per statement; the fifth is a property of the ACT and is asserted by
    :func:`authorize_no_commencement_instruments` once the act's proposals have
    been gathered and the date-conflict branch has had first refusal.
    """
    # SINGLE_EFFECTIVE_DATE.
    if len(candidate.effective_dates) != 1:
        return False
    # BLOCKED_ONLY_ON_SCOPE, in the two halves W-39 established: the parse must
    # have blocked, and it must have blocked for no reason but the missing
    # whole-act scope proof. Together these are also what keeps this route off
    # every pair the shipped whole-act route accepted.
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return False
    if set(failed_whole_act_conjuncts) != {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    }:
        return False
    # WHOLE_ACT_OPERATIVE_TEXT — W-47's reader, asserted in its own right so the
    # route reads as its conjunct set and so a later change to what
    # ``widened_whole_act_scope`` records cannot quietly drop it.
    #
    # W-73 adds the second reader of the SAME conjunct, spelled as an explicit
    # disjunction here rather than hidden inside either flag. The conjunct's
    # claim is "the operative text commences the act as a whole"; W-47's reader
    # proves it from a generic act-word or an ``om endring`` citation, W-73's
    # from the act's own title plus a title-agreement witness. Both are proofs of
    # one proposition, so the route asserts the proposition and names both
    # witnesses — and W-47's own multi-part route, which reads
    # ``whole_act_operative_text`` alone, is untouched by the addition.
    if not (
        candidate.whole_act_operative_text or candidate.title_cited_whole_act_scope
    ):
        return False
    # SINGLE_OPERATIVE_BLOCK, plus W-51's carve-out fence over that block. Both
    # are parse-time facts about the document, which the gate never sees.
    return candidate.widened_whole_act_scope


def _act_has_later_commencement_sibling(
    effective_date: str,
    claiming_source_ids: Collection[str],
    instrument_dates_for_act: Sequence[tuple[str, str]],
) -> bool:
    """Does another instrument commence something of this act LATER?

    W-51 makes this one function, called from two conjuncts — W-47's
    ``ACT_HAS_NO_LATER_INSTRUMENT`` on the multi-part route and the whole-act
    route's new one of the same name. Both claims are act-global ("the act, or
    every part of it the header names, was in force on this day"), so both are
    refuted by the same fact, and having them share a helper is what makes the
    two conjunct names mean the same thing.

    ``instrument_dates_for_act`` is the SHARPENED sibling list built by
    :func:`authorize_no_commencement_instruments` — an instrument that cites the
    act only as its hjemmel is not in it. This function only compares dates.
    ``claiming_source_ids`` are the instruments making the claim under test; the
    whole-act route can have several agreeing on one date, the multi-part route
    is always one.
    """
    claiming = frozenset(claiming_source_ids)
    return any(
        source_id not in claiming and date > effective_date
        for source_id, date in instrument_dates_for_act
    )


def _named_part_list_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
    evidence: "NOCommencementActPartEvidence | None",
    instrument_scopes_for_act: Sequence[tuple[str, str, tuple[str, ...], tuple[str, ...]]],
) -> tuple[tuple[str, str], ...] | None:
    """Prove which NAMED parts this instrument commences, or return ``None``.

    Every conjunct of
    :class:`NOCommencementNamedPartListAuthorizationConjunct` must hold, and as
    at W-47 there is no per-part credit: what proves the span is one sentence
    about a list, so the list authorizes whole or not at all. Returns the
    ``(part label, law id)`` pairs the act's Endrer header spans — a subset of
    the parts the text names — in part-label order.
    """
    if evidence is None:
        return None
    if len(candidate.effective_dates) != 1:
        return None
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return None
    if set(failed_whole_act_conjuncts) != {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
    }:
        return None
    changed = set(candidate.changed_law_ids)
    if not changed:
        return None
    # One document, one amending act: the operative blocks are read joined, so
    # two acts' part lists would merge into one unattributable list.
    cited_act_ids = {
        act_id
        for act_id in (
            no_commencement_act_id_from_law_id(law_id)
            for law_id in candidate.affected_law_ids
        )
        if act_id
    }
    if len(cited_act_ids) != 1:
        return None

    parts_by_law: dict[str, list[str]] = {}
    for part_label, law_id in evidence.part_law_ids.items():
        parts_by_law.setdefault(law_id, []).append(part_label)
    if any(len(labels) > 1 for labels in parts_by_law.values()):
        return None
    if any(law_id not in parts_by_law for law_id in evidence.bound_law_ids):
        return None
    if any(law_id not in parts_by_law for law_id in changed):
        return None
    spanned_labels = {parts_by_law[law_id][0] for law_id in changed}
    if len(spanned_labels) < 2:
        return None
    spanned_laws = {
        law_id for law_id, labels in parts_by_law.items() if labels[0] in spanned_labels
    }
    if spanned_laws != changed:
        return None
    named_labels = set(candidate.named_part_labels)
    if not named_labels:
        return None
    # The subset claim: dating the header's parts claims strictly less than the
    # text says, because the text names all of them and possibly more.
    if not spanned_labels <= named_labels:
        return None
    named_sections = set(candidate.commenced_section_labels)
    if named_sections and any(
        named_sections != set(evidence.law_section_labels.get(law_id, frozenset()))
        for law_id in changed
    ):
        return None
    effective_date = candidate.effective_dates[0]
    for source_id, date, sibling_changed, sibling_named in instrument_scopes_for_act:
        if source_id == candidate.source_id or date <= effective_date:
            continue
        sibling_header_labels = {
            parts_by_law[law_id][0] for law_id in sibling_changed if law_id in parts_by_law
        }
        # Witness one, structural. An empty set means the sibling's declared
        # laws place it nowhere in this act's part structure, which is not a
        # proof of disjointness — it is an absence of evidence, and refutes.
        if not sibling_header_labels or sibling_header_labels & named_labels:
            return None
        # Witness two, textual, read by this same reader. A text it cannot
        # account for bounds nothing and refutes.
        if not sibling_named or set(sibling_named) & named_labels:
            return None
    return tuple(
        sorted(
            (parts_by_law[law_id][0], law_id) for law_id in changed
        )
    )


class _SectionScopeRefusal(Exception):
    """Raised inside the section-scoped route on the first unresolvable term."""


@dataclass(slots=True)
class _SectionScopeProposal:
    """One instrument's claims about one (act, law) binding. W-100."""

    binding_date: str | None = None
    section_dates: dict[str, str] = field(default_factory=dict)
    excluded: set[str] = field(default_factory=set)
    qualified_dates: dict[str, str] = field(default_factory=dict)


def _section_scoped_authorization_scope(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
    failed_whole_act_conjuncts: tuple[NOCommencementAuthorizationConjunct, ...],
    evidence: "NOCommencementActPartEvidence | None",
    amendment_act_ids: Collection[str],
) -> tuple[dict[str, _SectionScopeProposal] | None, str]:
    """Resolve this pair's scope statements to per-law proposals, or refuse. W-100.

    Returns ``(proposals, "")`` on success, ``(None, reason)`` when the reader
    read the text but a term could not be resolved (the reason is receipted),
    and ``(None, "")`` when the pair is simply not this route's business (the
    reader refused, or an older route's conjunct set applies).

    Resolution rules, each refusing rather than guessing:

    * a PART resolves through the act's part map, and only if the law that
      part amends is amended by no other part;
    * a SECTION LIST or a LAW under a date-and-number citation resolves to that
      law, which must be one the act binds;
    * a section list under a short name or under no law at all resolves only
      when the act binds exactly one law;
    * an ACT-level statement targets every law the act binds; its carve-outs
      resolve like subjects, and a carved-out whole part or law simply drops
      out of the target set;
    * a carve-out under a section-list subject, or an act-level carve-out that
      names a section without a law on a multi-law act, refuses.
    """
    if evidence is None:
        return None, ""
    if parse_status is not NOCommencementParseStatus.BLOCKED_UNRESOLVED:
        return None, ""
    if not set(failed_whole_act_conjuncts) <= {
        NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE,
        NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE,
        NOCommencementAuthorizationConjunct.SINGLE_EFFECTIVE_DATE,
    }:
        return None, ""
    reading = candidate.scope_reading
    if not reading.total or not reading.statements:
        return None, ""
    # One AMENDMENT act. An instrument commencing an act and, in the same
    # document, amending a forskrift cites the forskrift's hjemmel statute in
    # the same ``basedOn`` field (``no/forskrift/2015-06-12-633`` cites
    # kringkastingsloven beside the act it commences); a principal law is not an
    # act whose statements could merge with this one's, so only cited ids that
    # ARE amendment acts in the index — the ones with act evidence — count.
    cited_amendment_act_ids = {
        act_id
        for act_id in (
            no_commencement_act_id_from_law_id(law_id)
            for law_id in candidate.affected_law_ids
        )
        if act_id and act_id in amendment_act_ids
    }
    if len(cited_amendment_act_ids) != 1:
        return None, "instrument cites several acts"

    parts_by_law: dict[str, list[str]] = {}
    for part_label, law_id in evidence.part_law_ids.items():
        parts_by_law.setdefault(law_id, []).append(part_label)
    bound = set(evidence.bound_law_ids)
    known_laws = bound | set(parts_by_law)
    single_law = next(iter(bound)) if len(bound) == 1 else ""

    def resolve(item: NOCommencementScopeItem) -> str:
        if item.kind == "part":
            law_id = evidence.part_law_ids.get(item.part_label)
            if law_id is None:
                raise _SectionScopeRefusal(f"part {item.part_label} resolves no law")
            if len(parts_by_law.get(law_id, ())) > 1:
                raise _SectionScopeRefusal(f"law {law_id} spans several parts")
            if item.law_ref.startswith("no/lov/") and item.law_ref != law_id:
                raise _SectionScopeRefusal(
                    f"part {item.part_label} cites {item.law_ref} but amends {law_id}"
                )
            return law_id
        if item.kind in {"sections", "law"}:
            if item.law_ref.startswith("no/lov/"):
                if item.law_ref not in known_laws:
                    raise _SectionScopeRefusal(f"cited law {item.law_ref} is not bound by the act")
                return item.law_ref
            if single_law:
                return single_law
            raise _SectionScopeRefusal(
                "section list without a resolvable law on a multi-law act"
                + (f" ({item.law_ref})" if item.law_ref else "")
            )
        raise _SectionScopeRefusal(f"unexpected scope term kind {item.kind}")

    proposals: dict[str, _SectionScopeProposal] = {}

    def proposal(law_id: str) -> _SectionScopeProposal:
        return proposals.setdefault(law_id, _SectionScopeProposal())

    def set_binding(law_id: str, date: str) -> None:
        current = proposal(law_id)
        if current.binding_date is not None and current.binding_date != date:
            raise _SectionScopeRefusal(f"two binding dates for {law_id}")
        current.binding_date = date

    def grant_sections(law_id: str, item: NOCommencementScopeItem, date: str) -> None:
        current = proposal(law_id)
        qualified = set(item.qualified_section_labels)
        for label in item.section_labels:
            target = current.qualified_dates if label in qualified else current.section_dates
            if label in target and target[label] != date:
                raise _SectionScopeRefusal(f"two dates for § {label} of {law_id}")
            target[label] = date

    def exclude(law_id: str, item: NOCommencementScopeItem) -> None:
        proposal(law_id).excluded.update(item.section_labels)

    try:
        for statement in reading.statements:
            subject = statement.subject
            date = statement.date
            if date is None:
                continue
            if subject.kind == "act":
                if not known_laws:
                    raise _SectionScopeRefusal("act binds no law")
                targets = set(known_laws)
                carve_outs: list[tuple[str, NOCommencementScopeItem]] = []
                for item in statement.excluded:
                    if item.kind == "act":
                        raise _SectionScopeRefusal("act carved out of itself")
                    if item.kind == "sections" and not item.law_ref and not single_law:
                        raise _SectionScopeRefusal(
                            "act-level carve-out names a section without a law on a multi-law act"
                        )
                    law_id = resolve(item)
                    if item.section_labels:
                        carve_outs.append((law_id, item))
                    else:
                        targets.discard(law_id)
                for law_id in sorted(targets):
                    set_binding(law_id, date)
                for law_id, item in carve_outs:
                    if law_id in targets:
                        exclude(law_id, item)
                continue
            law_id = resolve(subject)
            if subject.section_labels:
                if statement.excluded:
                    raise _SectionScopeRefusal("carve-out under a section-list subject")
                grant_sections(law_id, subject, date)
                continue
            set_binding(law_id, date)
            for item in statement.excluded:
                if item.kind == "act":
                    raise _SectionScopeRefusal("act carved out of a part")
                if item.kind == "part" and not item.section_labels:
                    raise _SectionScopeRefusal("whole part carved out of a part")
                if item.kind in {"sections", "law"} and not item.law_ref:
                    excluded_law = law_id
                else:
                    excluded_law = resolve(item)
                if excluded_law != law_id:
                    raise _SectionScopeRefusal(
                        f"carve-out under {law_id} names {excluded_law}"
                    )
                if not item.section_labels:
                    raise _SectionScopeRefusal("whole law carved out of itself")
                exclude(law_id, item)
    except _SectionScopeRefusal as refusal:
        return None, str(refusal)
    if not proposals:
        return None, "no statement dated anything"
    return proposals, ""


def _failed_authorization_conjuncts(
    parse_status: NOCommencementParseStatus,
    candidate: NOCommencementInstrumentCandidate,
) -> tuple[NOCommencementAuthorizationConjunct, ...]:
    failed: list[NOCommencementAuthorizationConjunct] = []
    if parse_status is not NOCommencementParseStatus.CANDIDATE:
        failed.append(NOCommencementAuthorizationConjunct.PARSE_STATUS_CANDIDATE)
    if candidate.scope_status is not NOCommencementScopeStatus.WHOLE_ACT:
        failed.append(NOCommencementAuthorizationConjunct.WHOLE_ACT_SCOPE)
    if len(candidate.effective_dates) != 1:
        failed.append(NOCommencementAuthorizationConjunct.SINGLE_EFFECTIVE_DATE)
    return tuple(failed)


def _normalized_text(root: etree._Element) -> str:
    return _WS_RE.sub(
        " ",
        " ".join(str(item) for item in root.itertext()).replace("\xa0", " "),
    ).strip()


def _class_text(root: etree._Element, class_name: str) -> str:
    value = root.xpath(
        "string(//dd[contains(concat(' ', normalize-space(@class), ' '), "
        f"' {class_name} ')][1])"
    )
    return _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()


def _body_text(root: etree._Element) -> str:
    value = root.xpath(
        "string(//*[contains(concat(' ', normalize-space(@class), ' '), ' documentBody ')][1])"
    )
    return _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()


def _operative_blocks(root: etree._Element) -> tuple[str, ...]:
    blocks: list[str] = []
    for node in cast(
        list[etree._Element],
        root.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' documentBody ')]"
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' legalP ')]"
        ),
    ):
        text = _WS_RE.sub(" ", " ".join(str(item) for item in node.itertext())).strip()
        if text:
            blocks.append(text)
    return tuple(blocks)


def _commenced_section_labels(operative_blocks: Sequence[str]) -> tuple[str, ...]:
    """The section labels the operative text names, in the grafter's spelling.

    Normalized to match ``_normalize_no_section_label`` output (``§`` dropped,
    inner spaces removed, lower-cased) so the set can be compared directly with
    the section labels of the part's own ops. An empty result means the text
    names no section, which is the strongest whole-part evidence there is.
    """
    labels: set[str] = set()
    for block in operative_blocks:
        # lawvm-regex: owning_parser this IS the commenced-section-label reader
        for match in _COMMENCED_SECTION_RE.finditer(block):
            labels.add(_WS_RE.sub("", match.group(1)).lower())
    return tuple(sorted(labels))


def _whole_act_operative_text(operative_blocks: Sequence[str]) -> bool:
    """Does the operative text commence the act as a WHOLE?

    Both halves of the W-47 guard, over the blocks joined: no subdivision of the
    act named anywhere and no negative/exception phrase, AND a commencement
    clause whose subject is the act rather than one of the laws it amends. The
    first half alone would miss a law-scoped narrowing, the second alone would
    miss "Loven trer i kraft ... med unntak av del V"; measured over the
    spanning-header surface, each half catches pairs the other lets through.
    """
    text = " ".join(operative_blocks)
    # lawvm-regex: owning_parser this IS the reader of the instrument's own operative scope; refusing half, cannot accept
    if _SUBDIVISION_SCOPE_RE.search(text):
        return False
    # lawvm-regex: owning_parser same reader, subject half; a closed act-word vocabulary, and absence refuses
    if _WHOLE_ACT_SUBJECT_RE.search(text):
        return True
    # lawvm-regex: owning_parser same reader, the act's own citation as the clause subject
    return bool(_CITED_ACT_SUBJECT_RE.search(text))


def _title_cited_whole_act_subject(
    operative_blocks: Sequence[str],
    *,
    title: str,
    cited_law_ids: Sequence[str],
) -> bool:
    """Is the operative clause's subject the cited act, named by its TITLE? W-73.

    The third whole-act subject shape, and it exists because a NEW act cannot be
    named the way the other two require. An instrument commencing an amending act
    writes "Loven trer i kraft" or "Lov 24. juni 2011 nr. 29 om endringer i …
    trer i kraft"; an instrument commencing a new act writes the act's title in
    the indefinite — "Lov om bustøtte skal gjelde frå 1. januar 2013",
    "Lov om dyrevelferd trer i kraft 1. januar 2010". Measured over all 35,955
    Lovtidend forskrift artifacts, that shape reaches 8 instruments no route
    reads today, and this function accepts 7 of them.

    It is the loosest subject shape in the module and so it carries the most
    proof. FOUR conjuncts, all required, none of which can accept on its own:

    * ONE CITED ACT. The grant this feeds is act-level, and the gate applies it
      per (instrument, cited act) pair; with two cited acts a single title
      subject would be attributed to whichever act the pair loop reached. The one
      corpus instrument that cites two (``no/forskrift/2009-03-06-266``) is
      refused here rather than guessed at.
    * ONE TITLE SUBJECT. Its mirror on the text side: two ``lov om`` subjects in
      one text is two acts being commenced, whatever the citation count says.
    * SENTENCE-INITIAL SUBJECT ADJACENT TO THE VERB (``_TITLE_CITED_ACT_SUBJECT_RE``
      anchored with ``match``). "Endringene i lov om dyrevelferd trer i kraft"
      is a law-scoped narrowing, not an act-level claim, and the anchor is what
      refuses it — exactly the adjacency argument ``_WHOLE_ACT_SUBJECT_RE``
      records for its own subject.
    * TITLE AGREEMENT. The subject's title phrase must appear in the
      instrument's own declared title. This is the conjunct that ties a loose
      textual shape to the document's identity: the instrument is titled
      "Ikraftsetjing av lov 24. august 2012 nr. 64 om bustøtte (bustøttelova)"
      and its subject is "Lov om bustøtte", so the phrase "om bustøtte" is the
      instrument saying twice, in two fields, which act it commences. A stray
      "Lov om …" sentence about some other statute agrees with no title and is
      refused.

    Plus ``_SUBDIVISION_SCOPE_RE``, the same purely-refusing fence
    :func:`_whole_act_operative_text` applies, so a title-cited subject cannot
    carry a text that names a chapter or an exception.

    The polarity is the safety argument, as everywhere in this gate:
    over-authorization is the danger, so every conjunct here can only ever
    REFUSE, and the function returns True on all four together or not at all.
    """
    if len(cited_law_ids) != 1:
        return False
    text = " ".join(operative_blocks)
    # lawvm-regex: owning_parser the shared refusing fence, reused verbatim; cannot accept
    if _SUBDIVISION_SCOPE_RE.search(text):
        return False
    # lawvm-regex: owning_parser this reader's unambiguity witness; a counter, refusing only
    subject_count = len(_INDEFINITE_ACT_TITLE_SUBJECT_RE.findall(text)) + len(
        _INDEFINITE_ACT_TITLE_CITATION_SUBJECT_RE.findall(text)
    )
    if subject_count != 1:
        return False
    # lawvm-regex: owning_parser this IS the title-cited subject reader; anchored at the block start
    match = _TITLE_CITED_ACT_SUBJECT_RE.match(text)
    if match is None:
        match = _TITLE_CITED_ACT_CITATION_SUBJECT_RE.match(text)
        # lawvm-regex: owning_parser the citation form's fifth conjunct: nothing
        # but a date after the verb. ``… trer i kraft for Bouvetøya 1. april
        # 2005`` (``no/forskrift/2005-02-25-173``) commences the act for one
        # territory, and a territorial or any other qualifier refuses.
        if match is None or _BARE_DATE_TAIL_RE.match(text, match.end()) is None:
            return False
    phrase = _WS_RE.sub(" ", match.group("title_phrase")).strip().casefold()
    return bool(phrase) and phrase in _WS_RE.sub(" ", title).strip().casefold()


def _cites_acts_as_hjemmel_only(
    operative_blocks: Sequence[str],
    *,
    declared_change_block_present: bool,
    declared_law_ids: Sequence[str],
) -> bool:
    """Is every act this instrument cites merely its legal BASIS?

    W-51. An instrument's ``basedOn`` block answers "under what authority was
    this made", and for an instrument commencing an act that IS the act — so
    the sibling sets every refuting conjunct reads were built from it. But a
    *forskrift* is made under a statute too, and a vedtak commencing that
    forskrift cites the same statute in the same field. Measured over the 542
    whole-act authorizations, five of the eight act-level EARLY rows were
    exactly that: ``no/forskrift/2016-06-29-845`` commences forskrift
    2006-04-21-433 and cites fiskesalslagslova as its hjemmel, and the probe
    read it as fiskesalslagslova commencing something in 2023.

    Proof of irrelevance needs TWO witnesses, and both must hold, for the same
    reason W-49's disjointness proof needs two — neither is sound alone:

    * the STRUCTURAL one — Lovdata's own ``Endrer`` block is present and names
      only non-law documents. An instrument commencing part of an act declares
      the LAWS that part amends (the reading W-39 established) or declares
      nothing at all; one that declares only forskrifter is acting on
      forskrifter. Measured, 242 of the 2,365 parsed instruments.
    * the TEXTUAL one — the operative text never uses the definite act-word.
      An instrument commencing an act says "Loven", "Lovens kapittel 6", "Loven
      § 7-3"; one commencing a forskrift says "Forskriften", "Denne forskrift",
      "Forskriftsendringen".

    The structural witness is not sound alone, and the counterexamples are in
    the corpus rather than hypothetical: ``no/forskrift/2013-12-13-1449``
    ("Utsatt ikrafttredelse av lov 28. mai 2010 nr. 16 … Loven trer i kraft 1.
    juli 2014, unntatt § 57") and ``no/forskrift/2014-06-20-789`` postpone an
    ACT's commencement while their ``Endrer`` block names only the kongelig
    resolusjon they rewrite. Requiring the textual witness too keeps those, and
    six others like them, in the sibling sets where they belong: 242 structural
    hits, 234 excluded, 8 held back by the second witness.

    The polarity is the safety argument. Excluding a sibling removes a
    refutation, so a false exclusion is UNSOUND while a false inclusion merely
    costs a grant. Everything unproven therefore stays in, and this function
    returns True only on the two witnesses together.

    Block PRESENCE stands in for "declares at least one document" because the
    two are the same thing in this corpus: swept over all 35,955 Lovtidend
    forskrift artifacts, of the 2,365 that parse as commencement instruments not
    one carries a ``changesToDocuments`` block with no ``<li>`` in it. (The
    reader's own docstring records the same for the amendment side.) A present
    block with no law in it therefore names a non-law document.
    """
    if not declared_change_block_present:
        return False
    if declared_law_ids:
        return False
    text = " ".join(operative_blocks)
    # lawvm-regex: owning_parser the textual witness of the hjemmel-only reader; presence keeps a sibling, absence is half a proof
    return not _DEFINITE_ACT_WORD_RE.search(text)


def _roman_label_value(token: str) -> int | None:
    """The value of a canonical romertall label, or ``None`` for anything else.

    Case-SENSITIVE on purpose: the Norwegian preposition ``i`` is one lowercase
    letter away from part I, and the operative texts are full of it. Canonical
    spelling is required too — the value is re-rendered and compared — so a
    token like ``IIII`` or a stray uppercase abbreviation is not a part label.
    """
    if not token:
        return None
    value = 0
    previous = 0
    for character in reversed(token):
        digit = _ROMAN_DIGIT_VALUES.get(character)
        if digit is None:
            return None
        value += -digit if digit < previous else digit
        previous = max(previous, digit)
    if value <= 0 or _roman_label(value) != token:
        return None
    return value


def _roman_label(value: int) -> str:
    label = ""
    remainder = value
    for step, symbol in _ROMAN_LABEL_STEPS:
        while remainder >= step:
            label += symbol
            remainder -= step
    return label


def _roman_label_sort_key(label: str) -> tuple[int, str]:
    """Romertall order, with a total fallback for anything not canonical."""
    value = _roman_label_value(label)
    return (value if value is not None else 0, label)


def _part_list_tokens(text: str) -> list[str]:
    """Split the operative text into words and single punctuation tokens.

    Deliberately not a regex: the reader's safety comes from its control flow
    (an unknown token CLOSES the list), and that argument is easier to check
    against a token list than against a pattern. Punctuation is padded rather
    than dropped so that ``del I-V`` and ``del VIII.`` tokenize the way the
    grammar reads them.
    """
    padded = text
    for character in _PART_LIST_PUNCTUATION:
        padded = padded.replace(character, f" {character} ")
    return padded.split()


def _named_part_labels(operative_blocks: Sequence[str]) -> tuple[str, ...]:
    """The romertall parts the operative text names, or ``()`` for REFUSED.

    Total by construction. Three global refusals run first — a subdivision or
    negation hazard anywhere in the text, and a commencement-verb count other
    than exactly one (two verbs means two clauses, and the second may defer
    what the first commenced). Then the scanner walks the tokens: a part word
    OPENS a list, romertall labels and the conjunction/range vocabulary CONTINUE
    it, and the first token the grammar does not know CLOSES it. Nothing is
    skipped over inside a list, so a qualifier the hazard guard missed can only
    end a list early, never be read past.

    Under-reading is safe and over-reading is not, which is why an orphan part
    word ("Følgende deler av loven trer i kraft ...") is passed over rather than
    refused, while a range that never gets its second end refuses outright.
    """
    text = " ".join(operative_blocks)
    # lawvm-regex: owning_parser this IS the part-list reader's hazard half; refusing only, cannot accept
    if _PART_LIST_HAZARD_RE.search(text):
        return ()
    # lawvm-regex: owning_parser same reader; exactly one commencement clause, else two scopes
    if len(_COMMENCEMENT_VERB_RE.findall(text)) != 1:
        return ()
    tokens = _part_list_tokens(text)
    labels: set[str] = set()
    saw_a_list = False
    index = 0
    while index < len(tokens):
        opener = tokens[index]
        index += 1
        if opener.lower() not in _PART_LIST_PART_WORDS:
            continue
        previous_value: int | None = None
        pending_range = False
        opened = False
        while index < len(tokens):
            token = tokens[index]
            value = _roman_label_value(token)
            if value is not None:
                if pending_range:
                    if previous_value is None or previous_value > value:
                        return ()
                    labels.update(
                        _roman_label(step) for step in range(previous_value, value + 1)
                    )
                    pending_range = False
                else:
                    labels.add(token)
                previous_value = value
                opened = True
            elif not opened:
                break
            elif token.lower() in _PART_LIST_RANGE_TOKENS:
                pending_range = True
            elif token.lower() in _PART_LIST_CONJUNCTIONS:
                pending_range = False
            elif token.lower() not in _PART_LIST_PART_WORDS:
                break
            index += 1
        if pending_range:
            return ()
        saw_a_list = saw_a_list or opened
    if not saw_a_list:
        return ()
    return tuple(sorted(labels, key=_roman_label_sort_key))


def _document_title(root: etree._Element) -> str:
    for value in (
        _class_text(root, "title"),
        _class_text(root, "titleShort"),
        root.xpath("string(//head/title[1])"),
        root.xpath("string(//h1[1])"),
    ):
        normalized = _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()
        if normalized:
            return normalized
    return ""


def _law_ids(root: etree._Element) -> tuple[str, ...]:
    candidates: list[str] = []
    for node in cast(
        list[etree._Element],
        root.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' basedOn ')]"),
    ):
        candidates.append(" ".join(str(item) for item in node.itertext()))
        candidates.extend(str(value) for value in cast(list[str], node.xpath(".//@*")))
    law_ids: set[str] = set()
    for value in candidates:
        # lawvm-regex: owning_parser harvests lov/<date>-<num> ids from basedOn locators, not prose
        for match in _LAW_REF_RE.finditer(value.replace("https://lovdata.no/dokument/NL/", "")):
            law_ids.add(f"no/lov/{match.group('date')}-{int(match.group('num'))}")
    return tuple(sorted(law_ids))


def _instrument_date_from_source_id(source_id: str) -> str:
    """``no/forskrift/2023-09-01-1380`` → ``2023-09-01``; empty when not of that shape."""
    tail = source_id.rsplit("/", 1)[-1]
    parts = tail.split("-")
    if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
        return "-".join(parts[:3])
    return ""


def parse_no_commencement_instrument(
    payload: bytes,
    *,
    source_id: str,
    locator: str,
    archive: str,
    member_name: str,
) -> NOCommencementInstrumentParseResult:
    """Parse one ``sf`` source into a candidate or an accounted non-candidate."""
    try:
        root = parse_corpus_xml(payload)
    except etree.XMLSyntaxError as exc:
        clause_text = payload.decode("utf-8", errors="replace")[:400]
        return NOCommencementInstrumentParseResult(
            parse_status=NOCommencementParseStatus.BLOCKED_UNRESOLVED,
            residuals=(
                NOCommencementInstrumentResidual(
                    rule_id=NO_COMMENCEMENT_INSTRUMENT_PARSE_FAILED,
                    reason=f"Norway Lovtidend instrument XML parse failed: {exc}",
                    clause_text=clause_text,
                ),
            ),
        )
    text = _normalized_text(root)
    title = _document_title(root)
    body_text = _body_text(root) or text
    # lawvm-regex: prefilter compile_classifier_regex-built title/clause guards; route non-commencement out
    if not _COMMENCEMENT_TITLE_RE.search(title) and not _LAW_COMMENCEMENT_RE.search(body_text):
        return NOCommencementInstrumentParseResult(
            parse_status=NOCommencementParseStatus.BENIGN_NOT_COMMENCEMENT
        )

    affected_law_ids = _law_ids(root)
    effective_text = _class_text(root, "dateInForce")
    # lawvm-regex: owning_parser reads ISO dates from the instrument's own dateInForce field
    effective_dates = tuple(sorted(set(_ISO_DATE_RE.findall(effective_text))))
    operative_blocks = _operative_blocks(root)
    single_block = operative_blocks[0] if len(operative_blocks) == 1 else ""
    # lawvm-regex: owning_parser this IS the whole-act scope reader; the shape half
    whole_act_shape = bool(single_block) and bool(_WHOLE_ACT_RE.fullmatch(single_block))
    # lawvm-regex: owning_parser same reader, W-51's carve-out fence on its tail; refusing only, cannot accept
    tail_carve_out = bool(_WHOLE_ACT_TAIL_HAZARD_RE.search(single_block))
    whole_act = whole_act_shape and not tail_carve_out and len(effective_dates) == 1
    # W-53. The widened route's scope proof, off the SAME single block and the
    # SAME fence value the shipped reader just computed — which is the whole
    # point of reading it here rather than in a reader of its own. The two halves
    # ``_whole_act_operative_text`` does not cover are the block COUNT (it reads
    # the blocks joined) and W-51's two extra carve-out phrases (``unntak for``,
    # ``foreløpig ikke``, which ``_SUBDIVISION_SCOPE_RE`` does not carry).
    whole_act_operative_text = _whole_act_operative_text(operative_blocks)
    # W-73. The third proof of the same text conjunct, computed off the same
    # blocks and joined into ``widened_whole_act_scope`` by OR — never into
    # ``whole_act_operative_text``, which W-47's multi-part route reads and which
    # this item does not touch. The block count and W-51's fence still gate it,
    # so a title-cited subject buys the pair nothing the other reader would not
    # have had to buy too.
    # W-100. The widened route reads the ACT-scoped blocks: a consequential
    # block that acts on a forskrift and names no act (``Fra samme tidspunkt
    # oppheves § 2-5 og § 2-6 i forskrift …``, ``no/forskrift/2015-06-12-633``)
    # is not about the act and is set aside before the single-block test. The
    # shipped ``_WHOLE_ACT_RE`` route above and W-47's ``whole_act_operative_text``
    # keep reading the raw blocks, so neither can widen through this. The first
    # block is never dropped, and the count set aside is recorded on the
    # candidate.
    act_blocks, forskrift_blocks_dropped = act_scoped_operative_blocks(operative_blocks)
    act_single_block = act_blocks[0] if len(act_blocks) == 1 else ""
    # lawvm-regex: owning_parser W-51's fence again, on the act-scoped block
    act_tail_carve_out = bool(_WHOLE_ACT_TAIL_HAZARD_RE.search(act_single_block))
    title_cited_whole_act_scope = _title_cited_whole_act_subject(
        act_blocks, title=title, cited_law_ids=affected_law_ids
    )
    widened_whole_act_scope = (
        bool(act_single_block)
        and (_whole_act_operative_text(act_blocks) or title_cited_whole_act_scope)
        and not act_tail_carve_out
    )
    # W-100. The section-scoped statement reader, over the same act-scoped
    # blocks. ``straks`` resolves to the instrument's own date; every prose date
    # must be in ``dateInForce``; the cited law ids are what lets the reader tell
    # the act's own citation from a law's.
    scope_reading = read_no_commencement_scope_statements(
        operative_blocks,
        instrument_date=_instrument_date_from_source_id(source_id),
        declared_dates=effective_dates,
        own_act_law_ids=affected_law_ids,
    )
    scope_status = (
        NOCommencementScopeStatus.WHOLE_ACT
        if whole_act
        else NOCommencementScopeStatus.UNRESOLVED
    )
    # Function-local like the grafter's own use of it: ``sources`` imports from
    # this module at load time, so the corpus's single ``changesToDocuments``
    # reader is only reachable from inside the function.
    from lawvm.norway.sources import declared_change_targets_from_root

    declared_changes = declared_change_targets_from_root(root)
    candidate = NOCommencementInstrumentCandidate(
        source_id=source_id,
        locator=locator,
        archive=archive,
        member_name=member_name,
        title=title,
        affected_law_ids=affected_law_ids,
        effective_dates=effective_dates,
        scope_status=scope_status,
        source_excerpt=text[:400],
        changed_law_ids=declared_changes.law_ids,
        commenced_section_labels=_commenced_section_labels(operative_blocks),
        whole_act_operative_text=whole_act_operative_text,
        named_part_labels=_named_part_labels(operative_blocks),
        cites_acts_as_hjemmel_only=_cites_acts_as_hjemmel_only(
            operative_blocks,
            declared_change_block_present=declared_changes.block_present,
            declared_law_ids=declared_changes.law_ids,
        ),
        widened_whole_act_scope=widened_whole_act_scope,
        title_cited_whole_act_scope=title_cited_whole_act_scope,
        scope_reading=scope_reading,
        forskrift_blocks_dropped=forskrift_blocks_dropped,
    )
    residuals: tuple[NOCommencementInstrumentResidual, ...] = ()
    parse_status = NOCommencementParseStatus.CANDIDATE
    if not affected_law_ids or not effective_dates or scope_status is NOCommencementScopeStatus.UNRESOLVED:
        missing = []
        if not affected_law_ids:
            missing.append("affected law binding")
        if not effective_dates:
            missing.append("effective date")
        if scope_status is NOCommencementScopeStatus.UNRESOLVED:
            missing.append("whole-act scope proof")
        residuals = (
            NOCommencementInstrumentResidual(
                rule_id=NO_COMMENCEMENT_SCOPE_UNRESOLVED,
                reason="Norway commencement instrument remains non-executable: missing " + ", ".join(missing),
                clause_text=text,
            ),
        )
        parse_status = NOCommencementParseStatus.BLOCKED_UNRESOLVED
    return NOCommencementInstrumentParseResult(
        parse_status=parse_status,
        candidate=candidate,
        residuals=residuals,
    )
