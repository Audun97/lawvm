"""Norway (Lovdata) frontend for LawVM.

The Norway path is structurally different from Finland and Estonia:

- consolidated base acts come from Lovdata public bulk downloads as HTML-in-XML
- amending acts also come from public bulk downloads
- amendment targeting is encoded directly in attributes such as
  ``data-change-part`` / ``data-add-new-part`` / ``data-remove-part``

That means Norway should be compiler-first but not NLP-first. The main task is
to normalize Lovdata structure into IR trees and LegalOperation objects.
"""

from __future__ import annotations

import contextvars
import copy
import re
import tarfile
from collections import Counter
from dataclasses import dataclass, replace as dc_replace
from pathlib import Path
from typing import Any, Generator, List, Mapping, Optional, Sequence, Tuple, cast

from lxml import etree

from lawvm.core import tree_ops
from lawvm.core.archive_safety import (
    ArchiveMemberTooLarge,
    log_archive_member_too_large,
    safe_tar_read,
)
from lawvm.core.diagnostic_records import diagnostic_detail
from lawvm.core.filter_result import FilterResult, RejectedItem
from lawvm.core.invariant_profiles import CORE_REPLAY_DELTA_MINIMAL_FAMILIES
from lawvm.core.op_ordering import OrderingProfile, order_ops
from lawvm.core.provenance import compute_source_anchor
from lawvm.core.regex_safety import compile_classifier_regex
from lawvm.core.apply_seam import (
    ApplyProfile,
    AppliedOp,
    MaterializeResult,
    OpAcceptance,
    apply_op,
)
from lawvm.core.execution_authorization import ExecutionAuthorization
from lawvm.core.mutation_boundary import RenumberedTreePaths, diff_ir_paths_identity_pruned
from lawvm.core.observed_write_audit import ObservedWriteAudit
from lawvm.core.phase_result import Finding
from lawvm.core.xml_parse import parse_corpus_xml
from lawvm.replay_adjudication import CompileAdjudication
from lawvm.roman import roman_to_arabic as _shared_roman_to_int
from lawvm.core.ir import (
    IRNode,
    IRStatute,
    LegalAddress,
    LegalOperation,
    OperationSource,
    TextPatchSpec,
    TextSelector,
)
from lawvm.core.semantic_types import (
    IRNodeKind,
    StructuralAction,
    TextPatchKindEnum,
    legacy_text_action_value,
    structural_action_from_str,
    structural_action_value,
)
from lawvm.core.quirks_disposition import QuirksDisposition
from lawvm.core.write_receipt import WriteReceipt
from lawvm.norway.mutation_boundary_per_op_probe import (
    drain_seam_boundary_observations as _no_drain_seam_boundary_observations,
)
from lawvm.norway.scope_confidence import NOScopeConfidence
from lawvm.core.totalization import (
    FailureClass,
    NoopIdempotent,
    Recover,
    Reject,
)
from lawvm.norway.totalization_table import NO_TOTALIZATION_TABLE

NO_PARSE_REPLACE_PROMOTED_TO_INSERT_FOR_RENUMBER = "no_parse_replace_promoted_to_insert_for_same_target_renumber"
NO_PARSE_STRUCTURED_TARGET_REBOUND_FROM_LEAD = "no_parse_structured_target_rebound_from_lead"
NO_PARSE_ACTION_RECOVERED_FROM_STRUCTURED_LEAD = "no_parse_action_recovered_from_structured_lead"
NO_RETTELSE_LOWERED = "no_rettelse_lowered"
NO_RETTELSE_NOT_LOWERED = "no_rettelse_not_lowered"
NO_BERIKTIGET_REANNOUNCEMENT_LOWERED = "no_beriktiget_reannouncement_lowered"
# W-84 PROVENANCE TAG prefix. Stamped on every op lowered out of a *beriktiget*
# (rectified) re-announcement so the op stream records BOTH ids: ``op.source``
# and ``op_id`` carry the ACT that enacted the text (the re-announcement is a
# republication, not a new law), and this tag carries the Lovtidend document the
# corrected bytes were actually read from. A carrier mark, not a hypothesis.
NO_BERIKTIGET_PROVENANCE_TAG = "beriktiget_announcement"
NO_RESANCTIONED_REPLACEMENT_LOWERED = "no_resanctioned_replacement_lowered"
# W-85 PROVENANCE TAG prefix. Stamped on every op lowered out of a re-sanctioned
# act (one whose own prose says it was "første gang sanksjonert som lov …" and is
# now sanctioned anew) so the op stream records BOTH acts: ``op.source``/``op_id``
# carry the re-sanctioned act itself — unlike W-84's republication, this IS a new
# law with its own identity and dates — and this tag carries the defective act it
# replaced. A carrier mark, not a hypothesis: it restates what the document says
# about itself, whether or not the index pairing suppresses the counterpart.
NO_RESANCTIONED_PROVENANCE_TAG = "resanctioned_from"


def _no_action_value(action: StructuralAction | str) -> str:
    """Normalize action to string value for comparisons and serialization.

    Fail-loud on an unrecognized ``str``: the shared jurisdiction-neutral
    ``structural_action_value`` is intentionally non-validating (it is the
    inverse direction; a caller may feed an already-valid boundary string).
    This wrapper is the only Norway action boundary and is reached with raw
    parsed action strings -- so it routes through ``structural_action_from_str``
    (raise) to mirror EE/UK's ``_to_structural_action`` and close the
    producer-side hole where an unknown action would otherwise pass through the
    comparison/serialization boundary unlabelled.
    """
    validated = structural_action_from_str(action, on_unknown="raise")
    return structural_action_value(validated)


def _no_kind_value(kind: IRNodeKind | str) -> str:
    """Normalize IR node kinds to string values for comparisons."""
    return kind.value if isinstance(kind, IRNodeKind) else kind


_FILENAME_RE = re.compile(r"^(?:nl/)?nl-(\d{4})(\d{2})(\d{2})-(\d+)(?:-(nn))?\.xml$")
_AMENDMENT_FILENAME_RE = re.compile(r"^(?:lti/\d{4}/)?nl-(\d{4})(\d{2})(\d{2})-(\d+)(?:-(nn))?\.xml$")
_REFID_RE = re.compile(r"lov/\d{4}-\d{2}-\d{2}(?:-\d+)?")
_SPACE_RE = re.compile(r"\s+")
_SECTION_LABEL_RE = re.compile(r"^\s*§\s*")
_NUMBERED_SUBSECTION_RE = re.compile(r"^\(\s*(\d+)\s*\)\s*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Abbreviations whose trailing period is NOT a sentence end. Every member is
# corpus-measured: each appears at a split boundary only inside sentences the
# multi-sentence-target family then mis-counts, and never as a legitimate
# sentence-final token. ``jfr.``/``m.m.``/``iht.`` were added by W-19 after a
# corpus sweep found 3 leads whose split arity goes wrong -> right and 0 that go
# right -> wrong. Single-letter forms are deliberately absent: bare item letters
# ("bokstav e.", "b.", "g.") DO end sentences in this corpus, so admitting them
# would flip correct splits.
_SENTENCE_ABBREVIATIONS = {"jf.", "jfr.", "nr.", "pkt.", "mv.", "m.m.", "iht.", "osv."}
_CONTINUATION_PUNKTUM_RE = re.compile(
    r"^(?:Første|Fyrste|Andre|Annet|Tredje|Fjerde|Femte|Sjette|Sjuende|Syvende|Åttende|Niende|Tiende)\s+punktum\b",
    re.IGNORECASE,
)
_NORWEGIAN_ORDINALS = {
    "første": "1",
    "fyrste": "1",
    "andre": "2",
    "annet": "2",
    "tredje": "3",
    "fjerde": "4",
    "femte": "5",
    "sjette": "6",
    "sjuende": "7",
    "syvende": "7",
    "åttende": "8",
    "niende": "9",
    "tiende": "10",
}
_NORWEGIAN_MONTHS = {
    "januar",
    "februar",
    "mars",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "desember",
}
# Trailing punctuation stripped off a month token before the day-number guard's
# membership test below. Corpus-measured over a full index build (W-22): the only
# suffixes that ever ride a month token at a split boundary are "," (2) and "."
# (1), and all three sit in a single text — skattebetalingsloven's four payment
# dates, "… terminer 15. mars, 15. juni, 15. september og 15. desember …" — which
# the unstripped guard over-split into 5 fragments against 2 declared targets. A
# 16-character strip set (adding ; : ! ? brackets quotes dashes) was swept and
# changes exactly the same one split, so the set is held to what is measured.
_MONTH_TOKEN_TRAILING_PUNCTUATION = ".,"
# The number token of a Lovtidend law citation, ``nr. 16`` or (W-25) ``nr 16``.
# Every citation regex in this module shares this spelling so the grammar cannot
# drift between the lead-side and payload-side extractors. Corpus-measured at
# W-25 over every text node of every amendment artifact: dropping the period
# requirement adds 29 unique spans across 9 acts, and all 29 are genuine law
# citations — 0 false positives. It cannot be otherwise: the full date prefix
# ("lov <day>. <month> <year>") must already have matched, so ``nr`` here is
# never the loose ``nr`` of an address ("§ 2 første ledd nr. 1") or of prose.
_NO_LAW_CITATION_NUMBER = r"nr\.?\s+(\d+)"
# The item ordinal an enumerated consequential-amendment lead carries ("1.",
# "1 a.", "93 a."). Non-capturing so it can prefix a capturing citation pattern.
# W-26 widened the section-lead strip and the enumerated embedded pattern from a
# bare ``\d+\.`` to this, the spelling ``_extract_no_law_announcement_base_id``
# already used. Corpus-measured over every unstructured lead at any nesting
# depth: 140 leads carry an ordinal this admits and the bare ``\d+\.`` does not,
# across 3 acts. Only 3 are genuinely letter-suffixed (``1 a.``, ``5 a.``,
# ``93 a.``, all in `no/lovtid/2009-06-19-74`); the rest are the spaced ``1 . ``
# form Lovdata produces when the item number sits in its own ``<strong>``
# (`no/lovtid/2020-11-20-128` § 16-3, `no/lovtid/2021-05-07-34`'s law list). The
# widened strip newly resolves 7 of the 140 and leaves the other 133 exactly
# where they were: the post-strip guards, not the strip, decide. No lead in the
# corpus opens with a bare ``<digit> <letter>.`` that is an amended section LABEL
# rather than an item ordinal — section labels are written with the sign
# ("§ 1 a"), which this anchor cannot reach.
_NO_LEAD_ITEM_ORDINAL = r"\d+\s*[a-zA-Z]?\."
_NO_LEAD_ITEM_ORDINAL_PREFIX = r"^" + _NO_LEAD_ITEM_ORDINAL + r"\s*"
# The two spellings of a dated law citation the extractors below search for: the
# ``lov <date> nr N`` head form and the ``… av <date> nr N`` tail form. Composed
# rather than written out so ``_NO_LAW_CITATION_NUMBER`` is the single place the
# ``nr`` grammar lives.
# Split from ``_NO_LAW_CITATION_DATE`` so the numberless spellings below can
# compose the date without the separator the ``nr`` token needs in front of it.
# W-99: the day's period is OPTIONAL. Norsk Lovtidend's pre-2001 house style
# cites without it — "59. I lov 4 desember 1992 nr 127 om kringkasting skal
# § 6-1 første ledd annet punktum lyde:" (1997 nr. 44, the print-era witness) —
# and the shipped requirement dropped that lead SILENTLY: no op, and no refusal
# either, because ``_no_unstructured_lead_looks_operative`` capped the span
# between ``skal`` and ``lyde`` at five tokens (fixed there, same item).
# Corpus-measured 2026-09-05 over every text node of all 3,089 unstructured
# artifacts: 40 period-less numbered spans across 12 acts, every one a genuine
# citation (`2003-06-20-45` alone carries 27, an old-law list written "Lov 14
# juni 1912 nr. 1"), 0 false positives — the month must still be a month name
# and a four-digit year plus ``nr N`` must still follow, so prose cannot reach
# it. Which of the 40 change an op is the after-diff recorded in the ledger.
_NO_LAW_CITATION_BARE_DATE = r"(\d{1,2})\.?\s+([A-Za-zæøåÆØÅ]+)\s+(\d{4})"
_NO_LAW_CITATION_DATE = _NO_LAW_CITATION_BARE_DATE + r"\s+"
_NO_LAW_CITATION_PATTERN = (
    r"(?:^|\b)(?:Midlertidig\s+)?lov\s+" + _NO_LAW_CITATION_DATE + _NO_LAW_CITATION_NUMBER
)
_NO_LAW_CITATION_AV_PATTERN = r"av\s+" + _NO_LAW_CITATION_DATE + _NO_LAW_CITATION_NUMBER
# W-28. Acts predating Lovtidend numbering carry no ``nr`` token at all, so both
# patterns above miss them outright: `2009-01-30-7` part I ("I lov 10. februar
# 1967 om behandlingsmåten i forvaltningssaker (forvaltningsloven) skal § 19
# fyrste ledd lyde:"), `2009-06-19-74` item 1 (Lappekodisillen 1751),
# `2015-06-19-65` items 42 and 58.
#
# The ledger proposed resolving these by DATE and disambiguating on title. The
# measurement says no such rule is needed, because the corpus already encodes the
# missing number: Lovdata's own DokumentID for these acts is date-only
# (``NL/lov/1967-02-10``), and the LTI filename convention writes that as number
# ``000``, which `_no_law_id_from_lti_filename` normalizes to ``-0``. Measured
# over both id populations: the current-law set holds 645 ids of which exactly 22
# end in ``-0``, every one of them 1687–1968 and every one a genuine
# pre-numbering act (forvaltningsloven `1967-02-10-0`, bilansvarslova
# `1961-02-03-0`, servituttlova `1968-11-29-0`, Lappekodisillen `1751-10-02-0`,
# Grunnloven `1814-05-17-0`, Christian V's Norske Lov `1687-04-15-0`); the 3,089
# LTI base ids contain none, because that archive only covers the numbered era.
# So the resolution is DETERMINISTIC and not a date-uniqueness guess: a
# numberless citation names the ``-0`` act of its date, one id, no candidate set
# to be ambiguous about. Only one date in the whole corpus carries both a ``-0``
# act and a numbered one (1962-03-23), and even there the two ids differ.
#
# The negative lookahead is what keeps this a FALLBACK rather than a re-reading
# of the numbered grammar: a citation that carries a number can never reach it.
# Corpus-wide there are 334 numberless ``lov <date>`` spans over 131 artifacts,
# and the tail is not a usable guard — 302 are followed by ``om``, but the other
# 32 include servituttlova's nynorsk ``um``, Lappekodisillen's bare Danish title
# and "Kong Christian Den Femtis Norske Lov 15. april 1687." — so the pattern
# takes the date and lets the ranking below decide.
# The number slot of a numberless citation: matches and captures nothing, so a
# numberless pattern keeps the same group story as its numbered siblings (date is
# 1–3, the embedded lead is always the LAST group) while carrying one group
# fewer — which is how ``_extract_no_embedded_multi_act_lead`` tells them apart.
_NO_LAW_CITATION_ABSENT_NUMBER = r"\b(?!\s*nr\.?\s+\d)"
_NO_LAW_CITATION_NUMBERLESS_PATTERN = (
    r"(?:^|\b)(?:Midlertidig\s+)?lov\s+(?:av\s+)?" + _NO_LAW_CITATION_BARE_DATE + _NO_LAW_CITATION_ABSENT_NUMBER
)
# The number a pre-numbering act carries in every corpus id it appears under.
_NO_NUMBERLESS_LAW_NUMBER = 0
# The dates the corpus ATTESTS as belonging to a numberless act. This closed set
# is what keeps W-28 from guessing, and it is not optional: Lovdata sometimes
# omits the number of an act that HAS one — `2008-12-19-115` writes "I lov 20.
# april 2001 om erstatning frå staten for personskade valda ved straffbar
# handling m.m. (valdsoffererstatningslova)" for `no/lov/2001-04-20-13` — and an
# ungated rule answers `no/lov/2001-04-20-0`, an id no corpus holds and a law
# that does not exist. Membership is decided by Lovdata twice over, never by
# this module: a date is here iff the corpus files a law under ``<date>-0``
# (22 dates, the LTI ``000`` number) or an amending act declares
# ``no/lov/<date>`` as a changed document (20 dates); 11 dates carry both
# attestations and the union is 31. The latest is 1968-11-29 — the set is
# closed by history, since no act enacted after Lovtidend numbering can enter
# it. ``test_no_w28_numberless_law_dates_match_the_corpus`` re-derives it from
# the archive, so a corpus that gains an old act fails loudly instead of
# silently under-resolving.
_NO_NUMBERLESS_LAW_DATES = frozenset(
    {
        "1687-04-15",  # Kong Christian Den Femtis Norske Lov
        "1751-10-02",  # Lappekodisillen
        "1775-06-08",  # Jorddelingen i Finmarken
        "1812-02-25",  # declared-only
        "1814-05-17",  # Grunnloven
        "1898-06-04",  # declared-only
        "1898-11-28",  # declared-only
        "1909-03-23",  # Instruks for Regjeringen
        "1916-03-17",  # straff for utenlandske militærpersoner
        "1917-03-09",  # declared-only
        "1918-02-08",  # declared-only
        "1920-02-09",  # Svalbardtraktaten
        "1925-08-07",  # Bergverksordning for Svalbard
        "1930-02-21",  # skifteloven (declared-only)
        "1930-03-14",  # landslottloven
        "1931-01-30",  # overenskomst med Storbritannia, sivil rettergang
        "1931-02-06",  # nordisk konvensjon, ekteskap
        "1933-11-07",  # nordisk konkurskonvensjon
        "1934-11-19",  # nordisk konvensjon, arv og dødsboskifte
        "1937-04-16",  # declared-only
        "1957-05-03",  # pensjonering av militært tilsatte
        "1961-02-03",  # bilansvarslova
        "1961-05-05",  # grannegjerdelova
        "1961-06-12",  # overenskomst med Storbritannia, dommer
        "1962-03-23",  # nordisk konvensjon, underholdsbidrag
        "1963-11-15",  # fullbyrding av nordiske straffedommer
        "1965-03-12",  # declared-only
        "1965-05-21",  # skogbruk og skogvern (declared-only)
        "1966-05-06",  # pensjonsordning for Sivilombudsmannen
        "1967-02-10",  # forvaltningsloven
        "1968-11-29",  # servituttlova
    }
)
# The amending tail that turns an ``I lov <citation> …`` lead into a PART
# ANNOUNCEMENT rather than a passing citation ("I lov 29. juni 1990 nr. 50 om
# … blir det gjort følgjande endringar:"). The tail IS the guard: an ``I lov …``
# lead without one names a law the item merely refers to and must not re-seed
# the part's base act — the same reasoning as the sibling announcement
# extractor's ``endres slik`` requirement below.
#
# W-30 replaced a hand-kept 11-member literal tuple with this shape. Measured
# over the EXACT population the gate is asked about — every lead reaching
# ``_extract_no_section_base_id_from_lead`` in a full corpus parse (47,455
# distinct leads, 5,722 of which pass its ``i `` prefix guard): the 11 literals
# admitted 1,907, this admits 2,442. The 535 newly-admitted leads (346 acts)
# carry 37 further spellings of the ONE construction and nothing else; every
# lead the literals admitted is still admitted, unchanged.
#
# The determiner slot is CLOSED, and that is load-bearing, not decoration. A
# drafted alternative that allowed any ≤40 characters between the verb and the
# noun also admitted substantive statutory prose — "I et varemerke som er søkt
# registrert kan det gjøres uvesentlige endringer …" — which is not this
# construction at all. Requiring an attested determiner immediately before the
# noun excludes it, at the measured cost of 2 genuine leads whose scope
# adverbial runs long ("… gjøres i avsnitt II om endringer i lov 2. juli 1999
# nr. 64 … følgende endring:") and 1 whose noun phrase is coordinated ("…
# gjøres følgende tillegg og endring:"). Those three are a deliberate
# conservative miss, not an oversight.
#
# Both word orders occur — verb-first ("gjort følgjande endringar", 177 of the
# newly admitted) and noun-first ("desse endringane gjerast", 41). ``ein``
# ("gjer ein følgjande endring", 45), the expletive ``det`` ("gjøres det
# følgende endringer", 3), a ``del``/``avsnitt`` scope ("gjøres i del II
# følgende endringer" and "gjøres i avsnitt I følgende endringer", 1 each) and
# ``midlertidige`` ("gjøres følgende midlertidige endringer", 1) are the only
# fillers the corpus puts inside the phrase. Every
# alternative listed below is corpus-attested, misspellings included
# (``fylgjande`` 2, ``føljande`` 1, ``følgene`` 1, ``følge`` 1) — Lovtidend's
# Nynorsk drafting is not spell-checked and the tail is the only guard there is.
#
# Word gaps are a single ``\s`` rather than ``\s+``, and the ``del``/``avsnitt``
# ordinal is an alternation rather than ``[ivx]+``, because both callers feed
# this ``_normalize_space``d text (every whitespace run is already one space) and
# because ``compile_classifier_regex``'s backtracking lint refuses a repeat
# nested inside the optional filler group. Verified equivalent: over all 47,455
# leads the ``\s+``/``[ivx]+`` draft and this spelling admit the identical set.
_NO_SECTION_INTRO_VERB = r"gj(?:erast|orde|orte|øres|eres|ere|ort|øre|ør|er)"
_NO_SECTION_INTRO_QUANTIFIED_NOUN = (
    r"(?:følgjande|fylgjande|føljande|følgande|følgende|følgene|følge"
    r"|desse|disse|denne|slike|slik)"
    r"(?:\smidlertidige)?\sendring(?:a|ar|ane|er|ene)?"
)
_NO_SECTION_INTRO_MARKER_RE = compile_classifier_regex(
    r"\b"
    + _NO_SECTION_INTRO_VERB
    + r"\b(?:\s(?:ein|det|i\s(?:del|avsnitt)\s(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)))?\s"
    + _NO_SECTION_INTRO_QUANTIFIED_NOUN
    + r"\b|\b"
    + _NO_SECTION_INTRO_QUANTIFIED_NOUN
    + r"\s"
    + _NO_SECTION_INTRO_VERB
    + r"\b",
    classifier_id="no.lovtidend.section_intro_amending_tail",
)
# ``skal\s+(?:\S+\s+)*?`` tolerates intervening qualifier words between the
# ``skal`` verb and the ``§`` target ("skal ny § 12 a lyde", "skal nytt § 4 a
# lyde"). The capture begins at ``§`` so the rebuilt embedded lead stays a ``§ …``
# form the section/subsection lowering families consume.
_NO_EMBEDDED_LEAD_TAIL = r"\s+.+?\s+skal\s+(?:\S+\s+)*?(§.+)$"
# W-99: the ADDRESS-AFTER-CITATION spelling. The section address follows the
# cited act's title and the verb CLOSES the lead: "47. Lov 4. desember 1992
# nr. 127 om kringkasting § 8-2 fjerde ledd annet punktum skal lyde:" (1998
# nr. 56, print-era witness); "12. I lov 8. juni 1984 nr. 59 om
# fordringshavernes dekningsrett (dekningsloven) § 9-4 annet ledd skal lyde:"
# (`2005-06-17-67`). The capture starts at the first ``§`` after the citation
# and runs to the end, so the rebuilt embedded lead is already in the
# ``§ … skal lyde:`` form the section families consume, INCLUDING a payload
# Lovdata ran on after the colon ("5. Lov 13. juni 1997 nr. 42 om Kystvakten
# § 9 første ledd bokstav b skal lyde: lov om matproduksjon …",
# `2003-12-19-124`) — without that the run-on lead is no switch, and its
# address binds to the PREVIOUS item's act (measured: 3 such mis-bindings,
# `2002-05-03-13` ekteskapsloven § 12, `2004-03-26-17` banksikringsloven § 4-6,
# and the Kystvakten item). Tempered so neither the title span nor the address
# span can cross a ``§`` or a colon: a title never carries either, and the
# colon is what keeps the W-36 run-on PART ANNOUNCEMENT out ("I lov … gjøres
# følgende endringer: § 4-1 andre ledd skal lyde: …" has its colon before the
# ``§`` and stays the announcement resolver's). The address span additionally
# cannot cross a sentence end (``. `` followed by a capital; ``nr. 3`` is
# followed by a digit and passes): "120. I lov 25. juni 1999 nr. 46 om
# finansavtaler … blir § 1 andre ledd bokstav g oppheva. Bokstav f skal lyde:
# …" (`2003-06-20-45`) is a nynorsk repeal-then-replace item, not this
# production, and reading it here swung the five ops after it onto
# finansavtaleloven. What keeps this DISJOINT from ``_NO_EMBEDDED_LEAD_TAIL``:
# that tail needs ``skal`` before the ``§``, this one needs ``skal lyde:``
# after it, so no lead can match both.
_NO_EMBEDDED_ADDRESS_FIRST_TAIL = (
    r"\s+(?:(?!§)[^:]){0,200}?(§(?:(?!§)(?!\.\s[A-ZÆØÅ])[^:]){0,160}?\bskal\s+lyde\s*:(?:\s.*)?)$"
)
_NO_EMBEDDED_MULTI_ACT_PATTERNS = (
    r"^"
    + _NO_LEAD_ITEM_ORDINAL
    + r"\s+I lov\s+"
    + _NO_LAW_CITATION_DATE
    + _NO_LAW_CITATION_NUMBER
    + _NO_EMBEDDED_LEAD_TAIL,
    r"^I\s+(?:lov\s+|midlertidig\s+lov\s+)?(?:.+?\s+av\s+)?"
    + _NO_LAW_CITATION_DATE
    + _NO_LAW_CITATION_NUMBER
    + _NO_EMBEDDED_LEAD_TAIL,
    # W-99, address-after-citation: both the nominative ``Lov …`` and the
    # prepositional ``I lov …`` head, ordinal optional. Ranked after the two
    # ``skal § …`` spellings above (disjoint anyway, see the tail) and before
    # the numberless W-28 pair: numbered citations only, because no numberless
    # lead of this shape exists in the corpus. Corpus-measured 2026-09-05: 29
    # leads across 15 acts. 27 produced nothing (refused base-unresolved or
    # unmatched); the other 2 — `2008-06-27-72` "Lov 16. februar 2007 nr. 9 om
    # skipssikkerhet … § 47 annet ledd skal lyde:" and `2018-06-01-23` item 5
    # (inkassoloven § 28) — LOWERED AGAINST THE PREVIOUS PART'S BASE ACT: the
    # citation was walked past as prose and the address bound to whatever law
    # the cursor still held (sjøloven, and a 1927 act). This production makes
    # the lead a law switch of its own, so both rebind to the act the drafter
    # named.
    r"^(?:"
    + _NO_LEAD_ITEM_ORDINAL
    + r"\s+)?(?:I\s+)?(?:midlertidig\s+)?lov\s+"
    + _NO_LAW_CITATION_DATE
    + _NO_LAW_CITATION_NUMBER
    + _NO_EMBEDDED_ADDRESS_FIRST_TAIL,
    # W-28, ranked LAST and behind an explicit ``lov`` token: the same two shapes
    # for a pre-numbering act, which carries no ``nr`` to match on. Both numbered
    # patterns above are tried first, so a citation that has a number can never
    # fall through to these. The ``lov`` optionality the second numbered pattern
    # allows is deliberately NOT carried over — without a number the word is the
    # only thing left that says this is a law citation at all.
    #
    # Needed because the intro-marker resolver
    # (`_extract_no_section_base_id_from_lead`) only covers the "gjøres følgende
    # endringer" announcement, so `2015-06-19-65` item 42 resolved through it
    # while the ledger's primary witness — `2009-01-30-7` part I, "I lov 10.
    # februar 1967 om behandlingsmåten i forvaltningssaker (forvaltningsloven)
    # skal § 19 fyrste ledd lyde:" — did not, and its § 19 op stayed dropped.
    r"^"
    + _NO_LEAD_ITEM_ORDINAL
    + r"\s+I lov\s+(?:av\s+)?"
    + _NO_LAW_CITATION_BARE_DATE
    + _NO_LAW_CITATION_ABSENT_NUMBER
    + _NO_EMBEDDED_LEAD_TAIL,
    r"^I\s+(?:midlertidig\s+)?lov\s+(?:av\s+)?"
    + _NO_LAW_CITATION_BARE_DATE
    + _NO_LAW_CITATION_ABSENT_NUMBER
    + _NO_EMBEDDED_LEAD_TAIL,
)
_NORWEGIAN_MONTH_NUMBERS = {
    "januar": "01",
    "februar": "02",
    "mars": "03",
    "april": "04",
    "mai": "05",
    "juni": "06",
    "juli": "07",
    "august": "08",
    "september": "09",
    "oktober": "10",
    "november": "11",
    "desember": "12",
}


def _repair_no_mojibake(text: str) -> str:
    if not text or not any(marker in text for marker in ("Ã", "Â", "â")):
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if repaired == text:
        return text
    original_markers = sum(text.count(marker) for marker in ("Ã", "Â", "â"))
    repaired_markers = sum(repaired.count(marker) for marker in ("Ã", "Â", "â"))
    if repaired_markers > original_markers:
        return text
    return repaired


_FUTURE_HEADING_RANGE_RE = re.compile(
    r"Ny deloverskrift til (?:ny |nye )?§{1,2}\s*([0-9A-Za-z-]+)(?:\s+til\s+([0-9A-Za-z-]+))?",
    re.IGNORECASE,
)
_SECTION_HEADING_ONLY_RE = re.compile(r"^Overskrift(?:en|a) til §", re.IGNORECASE)
_QUOTED_NO_TEXT_REPLACE_RE = re.compile(
    r"[«\"]([^»\"]+)[»\"](?:\s+erstattes)?\s+med\s+[«\"]([^»\"]+)[»\"]", re.IGNORECASE
)
_TEXT_BLOCK_CLASSES = {"legalP", "defaultP", "legalArticleHeader"}
_ITEM_CONTAINER_TAGS = {"ol", "ul"}


@dataclass(frozen=True)
class NOHeadingGroup:
    start_label: str
    end_label: str
    title: str
    sequence: int
    # The affecting-act provenance carrier ORDINARY ops get (``op.source``).
    # Heading groups are folded after the op fold, in their own pass, so
    # without this they carried no temporal coordinates at all and the fold ran
    # in archive-iteration order — the one Norway replay surface where
    # collection order was not inert (W-12; found by the W-10 investigation).
    # Carrying the SAME carrier means the fold's sort key can be computed by
    # the ordering kernel's own ``no_ordering_profile().temporal_key`` rather
    # than by a second, driftable copy of ``(effective, enacted, source_id,
    # sequence)``. ``None`` = parser-only caller that never reaches a fold with
    # a second contributor (see the guard in ``apply_no_heading_groups``).
    source: Optional[OperationSource] = None


def lovdata_filename_to_id(filename: str) -> Optional[str]:
    """Convert ``nl/nl-18840614-003.xml`` to ``no/lov/1884-06-14-3``.

    Returns ``None`` for Nynorsk duplicates (``-nn.xml``).
    """
    basename = filename.rsplit("/", 1)[-1]
    match = _FILENAME_RE.match(filename) or _FILENAME_RE.match(basename)
    if not match:
        return None
    year, month, day, number, nynorsk = match.groups()
    if nynorsk:
        return None
    return f"no/lov/{year}-{month}-{day}-{int(number)}"


def lovdata_amendment_filename_to_id(filename: str) -> Optional[str]:
    """Convert Lovtidend archive filenames to canonical amendment statute IDs."""
    basename = filename.rsplit("/", 1)[-1]
    match = _AMENDMENT_FILENAME_RE.match(filename) or _AMENDMENT_FILENAME_RE.match(basename)
    if not match:
        return None
    year, month, day, number, nynorsk = match.groups()
    if nynorsk:
        return None
    return f"no/lovtid/{year}-{month}-{day}-{int(number)}"


def normalize_lovdata_refid(raw: str) -> Optional[str]:
    """Normalize noisy Lovdata act references to canonical ``no/lov/...`` IDs."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("no/lov/"):
        raw = raw.removeprefix("no/")
    match = _REFID_RE.search(raw)
    if not match:
        return None
    return f"no/{match.group(0)}"


def _parse_document(html_bytes: bytes) -> etree._Element:
    """Parse Lovdata HTML/XML bytes into a tolerant element tree."""
    try:
        root = parse_corpus_xml(html_bytes, recover=True)
        if root is not None:
            return root
    except etree.XMLSyntaxError:
        pass

    html_parser = etree.HTMLParser(recover=True)
    root = etree.fromstring(html_bytes, parser=html_parser)
    if root is None:
        raise ValueError("unable to parse Lovdata document")
    return root


def _local_name(el: etree._Element) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _classes(el: etree._Element) -> set[str]:
    raw = el.get("class", "")
    return {part for part in raw.split() if part}


def _has_class(el: etree._Element, cls: str) -> bool:
    return cls in _classes(el)


def _normalize_space(text: str) -> str:
    return _SPACE_RE.sub(" ", text.replace("\xa0", " ")).strip()


def _normalize_label(label: str) -> str:
    label = _normalize_space(label)
    label = _SECTION_LABEL_RE.sub("", label)
    label = label.rstrip(".:;,)")
    return label.strip()


def _normalize_no_section_label(label: str) -> str:
    return _normalize_label(label).replace(" ", "")


def _first_heading_text(el: etree._Element) -> str:
    for child in el:
        if _local_name(child) in {"h1", "h2", "h3", "h4"}:
            text = _normalize_space("".join(str(_t) for _t in child.itertext()))
            if text:
                return text
    return ""


def _node_text_without_structural_children(
    el: etree._Element,
    *,
    skip_direct_classes: frozenset[str] = frozenset(),
) -> str:
    """Extract text while excluding nested structural blocks/lists."""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        classes = _classes(child)
        if skip_direct_classes and skip_direct_classes & classes:
            if child.tail:
                parts.append(child.tail)
            continue
        lname = _local_name(child)
        if lname not in {"article", "section", "li", "ol", "ul"}:
            child_text = _normalize_space("".join(str(_t) for _t in child.itertext()))
            if child_text:
                parts.append(child_text)
        if child.tail:
            parts.append(child.tail)
    return _normalize_space(" ".join(parts))


def _direct_children(el: etree._Element, tag: Optional[str] = None) -> list[etree._Element]:
    out: list[etree._Element] = []
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if tag is None or _local_name(child) == tag:
            out.append(child)
    return out


def _find_direct_children_with_class(el: etree._Element, cls: str) -> list[etree._Element]:
    return [child for child in _direct_children(el) if _has_class(child, cls)]


def _iter_change_descendants(el: etree._Element) -> list[etree._Element]:
    """Return change blocks under a document-change container without nested duplicates."""
    change_nodes: list[etree._Element] = []
    stack = list(reversed(_direct_children(el)))
    while stack:
        node = stack.pop()
        if "change" in _classes(node):
            change_nodes.append(node)
            continue
        stack.extend(reversed(_direct_children(node)))
    return change_nodes


def _extract_items(container: etree._Element) -> list[IRNode]:
    items: list[IRNode] = []
    used_labels: set[str] = set()
    next_index = 1
    for child in _direct_children(container):
        lname = _local_name(child)
        if lname == "article":
            for item in _extract_items(child):
                relabeled = _with_no_node_label(
                    item,
                    _dedupe_no_sibling_label(item.label or str(next_index), next_index, used_labels),
                )
                items.append(relabeled)
                next_index += 1
        elif lname in _ITEM_CONTAINER_TAGS:
            for grandchild in _direct_children(child, "li"):
                item = _parse_item(grandchild, next_index, used_labels)
                if item is not None:
                    items.append(item)
                    next_index += 1
        elif lname == "li":
            item = _parse_item(child, next_index, used_labels)
            if item is not None:
                items.append(item)
                next_index += 1
    return items


def _index_no_item_candidates(
    candidates: dict[tuple[str, str], IRNode],
    item: IRNode,
) -> None:
    if item.label:
        candidates[("item", item.label)] = item
    for child in item.children:
        if _no_kind_value(child.kind) == "item":
            _index_no_item_candidates(candidates, child)


def _dedupe_no_sibling_label(
    preferred: str,
    sequence_index: int,
    used_labels: set[str],
) -> str:
    label = _normalize_label(preferred) or str(sequence_index)
    if label not in used_labels:
        used_labels.add(label)
        return label
    fallback = sequence_index
    while str(fallback) in used_labels:
        fallback += 1
    label = str(fallback)
    used_labels.add(label)
    return label


def _parse_item(
    li_el: etree._Element,
    sequence_index: int,
    used_labels: set[str],
) -> Optional[IRNode]:
    label = li_el.get("data-name") or li_el.get("data-li-identifier") or li_el.get("id") or ""
    if _normalize_label(label) in {"", "-"}:
        label = str(sequence_index)
    label = _dedupe_no_sibling_label(label, sequence_index, used_labels)
    text = _node_text_without_structural_children(li_el)
    if not text:
        for child in _direct_children(li_el, "article"):
            child_text = _node_text_without_structural_children(child)
            if not child_text:
                for grandchild in _direct_children(child, "article"):
                    child_text = _node_text_without_structural_children(grandchild)
                    if child_text:
                        break
            if child_text:
                text = child_text
                break
    children = _extract_items(li_el)
    if not label and not text and not children:
        return None
    return IRNode(kind=IRNodeKind.ITEM, label=label, text=text, children=tuple(children))


def _parse_subsection(article_el: etree._Element, index: int, used_labels: set[str]) -> Optional[IRNode]:
    raw_label = article_el.get("data-numerator", "").strip() or str(index)
    label = _dedupe_no_sibling_label(raw_label, index, used_labels)
    text = _node_text_without_structural_children(
        article_el,
        skip_direct_classes=frozenset({"leddfortsettelse"}),
    )
    if article_el.get("data-numerator"):
        text = _NUMBERED_SUBSECTION_RE.sub("", text, count=1)
    items = _extract_items(article_el)
    continuation_texts = [
        _normalize_space("".join(str(_t) for _t in child.itertext()))
        for child in _direct_children(article_el)
        if "leddfortsettelse" in _classes(child)
    ]
    continuation_texts = [part for part in continuation_texts if part]
    sentence_children = [
        IRNode(kind=IRNodeKind.SENTENCE, label=str(index), text=part)
        for index, part in enumerate(continuation_texts, start=1)
    ]
    children = tuple(items + sentence_children)
    if not text and not children:
        return None
    return IRNode(
        kind=IRNodeKind.SUBSECTION,
        label=label,
        text=text,
        children=children,
    )


def _merge_no_unlabeled_subsection_continuation(
    children: list[IRNode],
    article_el: etree._Element,
    subsection: IRNode,
    used_labels: set[str],
) -> bool:
    if article_el.get("data-numerator"):
        return False
    if subsection.children:
        return False
    text = _normalize_space(subsection.text or "")
    if not _CONTINUATION_PUNKTUM_RE.match(text):
        return False
    if not children:
        return False
    prev = children[-1]
    if _no_kind_value(prev.kind) != "subsection":
        return False
    prev_text = _normalize_space(prev.text or "")
    merged_text = " ".join(part for part in [prev_text, text] if part).strip()
    children[-1] = IRNode(
        kind=prev.kind,
        label=prev.label,
        text=merged_text,
        attrs=dict(prev.attrs),
        children=prev.children,
    )
    used_labels.discard(subsection.label or "")
    return True


def _merge_no_leddfortsettelse_paragraph(
    children: list[IRNode],
    paragraph_el: etree._Element,
) -> bool:
    classes = _classes(paragraph_el)
    if "leddfortsettelse" not in classes:
        return False
    if not children:
        return False
    prev = children[-1]
    if _no_kind_value(prev.kind) != "subsection":
        return False
    text = _normalize_space(" ".join(str(_t) for _t in paragraph_el.itertext()))
    if not text:
        return False
    if any(_no_kind_value(child.kind) in {"item", "sentence"} for child in prev.children):
        sentence_labels = [
            int(child.label)
            for child in prev.children
            if _no_kind_value(child.kind) == "sentence" and child.label and re.fullmatch(r"\d+", child.label)
        ]
        next_label = str(max(sentence_labels) + 1) if sentence_labels else "1"
        children[-1] = IRNode(
            kind=prev.kind,
            label=prev.label,
            text=prev.text,
            attrs=dict(prev.attrs),
            children=tuple(
                [child for child in prev.children] + [IRNode(kind=IRNodeKind.SENTENCE, label=next_label, text=text)]
            ),
        )
        return True
    prev_text = _normalize_space(prev.text or "")
    merged_text = " ".join(part for part in [prev_text, text] if part).strip()
    children[-1] = IRNode(
        kind=prev.kind,
        label=prev.label,
        text=merged_text,
        attrs=dict(prev.attrs),
        children=prev.children,
    )
    return True


def _section_label_from_element(section_el: etree._Element) -> str:
    label = section_el.get("data-name", "")
    if not label:
        url = section_el.get("data-lovdata-url") or section_el.get("data-lovdata-URL") or ""
        label = url.rsplit("/", 1)[-1]
    return _normalize_label(label)


def _parse_section(section_el: etree._Element) -> Optional[IRNode]:
    label = _section_label_from_element(section_el)
    heading_text = _first_heading_text(section_el)
    children: list[IRNode] = []
    if heading_text:
        title = heading_text
        if label:
            title = re.sub(rf"^\s*§\s*{re.escape(label)}\s*", "", title).strip(" .:-")
        if title:
            children.append(IRNode(kind=IRNodeKind.HEADING, text=title))

    subsection_index = 1
    used_subsection_labels: set[str] = set()
    for child in _direct_children(section_el):
        lname = _local_name(child)
        if lname == "p":
            _merge_no_leddfortsettelse_paragraph(children, child)
            continue
        if lname != "article":
            continue
        classes = _classes(child)
        if "changesToParent" in classes:
            continue
        if not ({"legalP", "defaultP", "numberedLegalP"} & classes):
            continue
        subsection = _parse_subsection(child, subsection_index, used_subsection_labels)
        if subsection is not None:
            if _merge_no_unlabeled_subsection_continuation(children, child, subsection, used_subsection_labels):
                continue
            children.append(subsection)
            subsection_index += 1

    if not children:
        text = _node_text_without_structural_children(section_el)
        if not text:
            return None
        return IRNode(kind=IRNodeKind.SECTION, label=label or None, text=text)

    return IRNode(kind=IRNodeKind.SECTION, label=label or None, children=tuple(children))


def _parse_future_section(section_el: etree._Element) -> Optional[IRNode]:
    label = _normalize_label(section_el.get("data-name", "") or "")
    children: list[IRNode] = []

    for child in _direct_children(section_el):
        if "futureLegalArticleHeader" not in _classes(child):
            continue
        title = _normalize_space("".join(str(_t) for _t in child.itertext()))
        if label:
            title = re.sub(rf"^\s*§\s*{re.escape(label)}\s*", "", title).strip(" .:-")
        if title:
            children.append(IRNode(kind=IRNodeKind.HEADING, text=title))

    subsection_index = 1
    used_subsection_labels: set[str] = set()
    for child in _direct_children(section_el, "article"):
        classes = _classes(child)
        if not ({"legalP", "defaultP", "numberedLegalP"} & classes):
            continue
        subsection = _parse_subsection(child, subsection_index, used_subsection_labels)
        if subsection is not None:
            if _merge_no_unlabeled_subsection_continuation(children, child, subsection, used_subsection_labels):
                continue
            children.append(subsection)
            subsection_index += 1
    for child in _direct_children(section_el, "p"):
        _merge_no_leddfortsettelse_paragraph(children, child)

    if not children:
        return IRNode(kind=IRNodeKind.SECTION, label=label or None, text="")
    return IRNode(kind=IRNodeKind.SECTION, label=label or None, children=tuple(children))


def _label_from_container_url(section_el: etree._Element) -> Optional[str]:
    url = section_el.get("data-lovdata-url") or section_el.get("data-lovdata-URL") or ""
    tail = (url or "").rsplit("/", 1)[-1]
    match = re.match(r"KAPITTEL_(.+)$", tail)
    if match:
        return _normalize_label(match.group(1).replace("_", "-")) or None
    return _normalize_label(tail) or None


def _container_kind_and_label(section_el: etree._Element) -> tuple[str, Optional[str]]:
    data_name = section_el.get("data-name", "") or ""
    if data_name.startswith("del"):
        label = _normalize_label(data_name.removeprefix("del")) or None
        if label and re.search(r"\d", label):
            return "part", label
        return "part", _label_from_container_url(section_el)
    if data_name.startswith("kap"):
        label = _normalize_label(data_name.removeprefix("kap")) or None
        if label and (re.search(r"\d", label) or re.fullmatch(r"[ivxlcdm]+", label, re.IGNORECASE)):
            return "chapter", label
        return "chapter", _label_from_container_url(section_el)

    return "chapter", _label_from_container_url(section_el)


def _parse_container(section_el: etree._Element) -> Optional[IRNode]:
    kind, label = _container_kind_and_label(section_el)
    heading_text = _first_heading_text(section_el)
    children: list[IRNode] = []
    if heading_text:
        children.append(IRNode(kind=IRNodeKind.HEADING, text=heading_text))

    for child in _direct_children(section_el):
        lname = _local_name(child)
        if lname == "section" and _has_class(child, "section"):
            parsed = _parse_container(child)
            if parsed is not None:
                children.append(parsed)
        elif lname == "article" and _has_class(child, "legalArticle"):
            parsed = _parse_section(child)
            if parsed is not None:
                children.append(parsed)

    if not any(_no_kind_value(child.kind) != "heading" for child in children):
        return None
    return IRNode(kind=IRNodeKind(kind), label=label, children=tuple(children))


def parse_no_statute(html_bytes: bytes, statute_id: str) -> IRStatute:
    """Parse a Lovdata consolidated document into canonical IR."""
    root = _parse_document(html_bytes)
    title = _normalize_space(str(root.xpath("string(//title[1])")))
    main_nodes = cast(
        list[etree._Element], root.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' documentBody ')]")
    )
    main = main_nodes[0] if main_nodes else root

    # W-43: one order-preserving pass over the top level, mirroring `_parse_container`.
    # Previously the article walk was an `if not body_children:` fallback to the chapter
    # walk, so any document mixing top-level `§§` with chapters (typically act-own
    # provisions followed by an annexed instrument) silently lost every article.
    body_children: list[IRNode] = []
    for child in _direct_children(main):
        lname = _local_name(child)
        if lname == "section" and _has_class(child, "section"):
            parsed = _parse_container(child)
        elif lname == "article" and _has_class(child, "legalArticle"):
            parsed = _parse_section(child)
        else:
            continue
        if parsed is not None:
            body_children.append(parsed)

    return IRStatute(
        statute_id=statute_id,
        title=title,
        body=IRNode(kind=IRNodeKind.BODY, children=tuple(body_children)),
        metadata={"source_format": "lovdata_html"},
    )


def _eli_kind_and_step(parts: Sequence[str], idx: int) -> tuple[Optional[tuple[str, str]], int]:
    token = parts[idx]
    if token.startswith("KAPITTEL_"):
        return ("chapter", _normalize_label(token.split("_", 1)[1].replace("_", "-"))), idx
    if token.startswith("§"):
        return ("section", _normalize_label(token)), idx
    if token in {"ledd", "nummer", "bokstav", "setning"} and idx + 1 < len(parts):
        label = _normalize_label(parts[idx + 1])
        kind = {
            "ledd": "subsection",
            "nummer": "item",
            "bokstav": "item",
            "setning": "sentence",
        }[token]
        return (kind, label), idx + 1
    return None, idx


def lovdata_path_to_address(path: str) -> Optional[LegalAddress]:
    """Convert a Lovdata ELI-like path to a LegalAddress."""
    if not path:
        return None
    parts = [part for part in path.strip().split("/") if part]
    steps: list[tuple[str, str]] = []
    idx = 0
    while idx < len(parts):
        step, idx = _eli_kind_and_step(parts, idx)
        if step is not None:
            steps.append(step)
        idx += 1
    if not steps:
        return None
    return LegalAddress(path=tuple(steps))


def _split_change_attr(value: str, default_action: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for token in value.split():
        token = token.strip()
        if not token:
            continue
        if ";;" in token:
            out.append(("renumber", token))
            continue
        if token.startswith("tilføyer="):
            out.append(("insert", token.split("=", 1)[1]))
        else:
            out.append((default_action, token))
    return out


NO_PARSE_MALFORMED_STRUCTURED_RENUMBER_ATTR_SKIPPED = "no_parse_malformed_structured_renumber_attr_skipped"
NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE = "no_parse_structured_move_legs_completed_from_lead_prose"
#: W-70. Non-blocking: the attribute was repaired and its legs LOWERED, so this
#: is a provenance receipt for a write that happened, not a refusal.
NO_PARSE_STRUCTURED_MOVE_ATTR_NORMALIZED = "no_parse_structured_move_attr_normalized"
#: W-70b. Same polarity as its W-70 sibling: the legs LANDED, and this receipt is
#: their provenance plus the prose sentence that proved the repair.
NO_PARSE_STRUCTURED_MOVE_ATTR_DESTINATION_SECTION_NORMALIZED = (
    "no_parse_structured_move_attr_destination_section_normalized"
)


def _structured_move_attr_skip_reason(token: str) -> Optional[str]:
    separator_count = token.count(";;")
    if separator_count == 0:
        return "missing_separator"
    if separator_count > 1:
        return "multiple_separators"
    src, dst = token.split(";;", 1)
    if not src and not dst:
        return "missing_source_and_destination"
    if not src:
        return "missing_source"
    if not dst:
        return "missing_destination"
    return None


# ── W-70: the malformed ``data-move-part``, and what may be recovered from it ──
#
# A well-formed ``data-move-part`` is whitespace-separated ``<source>;;<dest>``
# tokens. 286 of the corpus's 3,885 change blocks carry the attribute; SIX carry
# a value the token grammar above refuses. Before this production those six mint
# 14 ``no_parse_malformed_structured_renumber_attr_skipped`` receipts (one per
# malformed token) and lower nothing; after it, four recover and 3 receipts
# remain. The population GROWS with archive refreshes — three of the six arrived
# in the one refresh between W-56 and W-62 — which is why the membership is
# pinned by a standing tripwire (``test_no_renumber_migration.py``) rather than
# left to accumulate in silence.
#
# WHAT THE SIX ACTUALLY ARE, read off the ``article.change`` node the parser
# itself reads (not a text-plane grep), attribute value verbatim:
#
#   1. ``…§19-1/ledd/5;; …§19-1/ledd/3``            (2024-06-25-60)
#   2. ``…§8/ledd/2;; …§8/ledd/3 …§8/ledd/3;; …§8/ledd/4``   (2025-02-07-1)
#   3. ``…§3-2/ledd/3;; …§3-2/ledd/2 …§3-2/ledd/4;; …§3-2/ledd/3`` (2025-04-10-11)
#        — a STRAY SPACE after the separator. Whitespace is the pair delimiter,
#          so ``a;; b`` splits into ``a;;`` (no destination) and ``b`` (no
#          separator): one intended pair read as two broken tokens.
#   4. ``…§4/ledd/4::…§4/ledd/5``                    (2025-06-20-74)
#        — ``::`` typed for ``;;``. One intended pair, one wrong glyph.
#   5. ``…§65/ledd/2 …§65/ledd/3``                   (2024-06-21-46)
#        — no separator ANYWHERE. Which address is the source is not stated by
#          the markup, and this production does not guess: NO RULE.
#   6. ``…bokstav/u;;…bokstav/vlov/…/bokstav/v;;…bokstav/w`` (2026-02-06-2)
#        — two pairs fused at a missing space. Recoverable in principle; NO RULE
#          here, see the cross-base gate below.
#
# THE SHAPE OF THE REPAIR. Each rule is a total function on the token list, and
# every rule is a SEPARATOR repair: it may move, retype or delete separator
# glyphs and whitespace and nothing else. That is enforced, not asserted — the
# ``skeleton`` (every token concatenated with ``;`` and ``:`` removed) must be
# byte-identical before and after, so no rule can invent an address, drop one,
# or reorder two. Lovdata paths contain no ``;`` or ``:``, which is what makes
# the skeleton a faithful identity for "the addresses, in order".
#
# TWO GATES, and both are load-bearing for the two blocks that must NOT recover:
#
#   * CROSS-BASE. Every address in the attribute must name the block's own base
#     act. Block 5 names ``lov/2010-03-26-9`` under base ``lov/2022-05-12-28``
#     and block 6 names ``lov/2024-06-21-41`` under ``lov/2022-12-16-91``: the
#     archive has mis-attributed those endringsdeler to the preceding base, so a
#     "repair" would relabel a law the instrument never addressed here. Both are
#     declined before any rule is tried, and the pin in
#     ``test_no_renumber_migration.py`` holds them refused.
#   * FULLY DETERMINED. After the rewrite EVERY token must be well-formed and
#     every side must lower to an address. A partial repair is not taken; the
#     block keeps its existing typed receipts (now carrying the decline reason).
#
# WHAT LANDS. Four blocks recover, minting six RENUMBER legs. They are ordinary
# structured legs — same emission site, same provenance, no new tag — because
# the normalizer repairs a separator rather than founding a production with its
# own semantics; a repaired leg must behave exactly like the well-formed leg it
# was meant to be. The corpus consequence was MEASURED, not assumed: none of the
# six destinations is occupied when its leg runs, because the kernel's
# structural-vacate stage (``no_ordering_profile``) already runs REPEALs first
# and then topologically sorts RENUMBERs, and each of the four blocks either has
# its destination repealed by the same instrument first (§19-1's own
# ``data-repeal-part``, §3-2's sibling "§ 3-2 annet ledd oppheves." block) or
# shifts UPWARD past the section's last ledd (§8 has three, §4 has four). So the
# corpus firing census is 10 → 10 and the pinned verdict table gains no row —
# which is also why the W-66
# refuse-on-occupied tag is deliberately NOT stamped here: there is nothing to
# refuse, and stamping it would make a repaired leg quieter than the well-formed
# leg beside it.
#
# The well-formed path is untouched byte for byte: ``_no_normalize_move_attr``
# returns immediately when no token is malformed, so no attribute that parses
# today can change what it parses.
_NO_MOVE_ATTR_RULE_SEPARATOR_SPACING = "separator_spacing"
_NO_MOVE_ATTR_RULE_ALTERNATE_SEPARATOR = "alternate_separator"
_NO_MOVE_ATTR_DECLINED_WELL_FORMED = "declined:well_formed"
_NO_MOVE_ATTR_DECLINED_CROSS_BASE = "declined:cross_base_tokens"
_NO_MOVE_ATTR_DECLINED_NO_RULE = "declined:no_rule_matched"
_NO_MOVE_ATTR_DECLINED_UNRESOLVED = "declined:unresolvable_address"
#: The alternate separator glyph block 4 was typed with. Kept as a constant so
#: the skeleton below and the rule agree on exactly which glyphs are separators.
_NO_MOVE_ATTR_ALTERNATE_SEPARATOR = "::"


@dataclass(frozen=True)
class _NOMoveAttrNormalization:
    """The normalizer's verdict on one ``data-move-part`` value.

    ``pairs`` is ``None`` when nothing was repaired, and ``rule`` then names WHY
    (a ``declined:`` reason); otherwise ``rule`` names which repair fired. The
    rule id is reported both ways so the ordering of the rules is a test's fact
    rather than a comment's claim.
    """

    pairs: Optional[Tuple[Tuple[str, str], ...]]
    rule: str


def _no_move_attr_skeleton(tokens: Sequence[str]) -> str:
    """Every address character in the value, in order, separators removed.

    The invariant a repair must preserve. Whitespace is already gone (the caller
    split on it), so removing the two separator glyph characters leaves exactly
    the address text — reorder, drop or invent one character of an address and
    this string moves.
    """
    return "".join(char for token in tokens for char in token if char not in ";:")


def _no_fuse_separator_spaced_tokens(tokens: Sequence[str]) -> list[str]:
    """``["a;;", "b"]`` → ``["a;;b"]`` — the stray space after the separator.

    A token that ENDS with the separator has an empty destination slot, and the
    token after it carries no separator of its own, so it can only be that
    destination. Anything else is left exactly as it was.
    """
    out: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if token.endswith(";;") and token.count(";;") == 1 and following is not None and ";;" not in following:
            out.append(token + following)
            index += 2
            continue
        out.append(token)
        index += 1
    return out


def _no_retype_alternate_separator_tokens(tokens: Sequence[str]) -> list[str]:
    """``a::b`` → ``a;;b`` — the wrong glyph, on a token with no real separator.

    Guarded on ``";;" not in token`` so this can never touch a token that
    already carries the real separator, and on a single occurrence so a token
    with two ``::`` is left to be declined rather than split on a guess.
    """
    return [
        token.replace(_NO_MOVE_ATTR_ALTERNATE_SEPARATOR, ";;")
        if ";;" not in token and token.count(_NO_MOVE_ATTR_ALTERNATE_SEPARATOR) == 1
        else token
        for token in tokens
    ]


#: Tried in order; the FIRST rule that yields a fully well-formed token list
#: wins. Order is reported on every receipt, so which rule fired is testable.
_NO_MOVE_ATTR_NORMALIZATION_RULES = (
    (_NO_MOVE_ATTR_RULE_SEPARATOR_SPACING, _no_fuse_separator_spaced_tokens),
    (_NO_MOVE_ATTR_RULE_ALTERNATE_SEPARATOR, _no_retype_alternate_separator_tokens),
)


def _no_move_attr_tokens_share_base(tokens: Sequence[str], base_id: str) -> bool:
    """Does every address in the value name ``base_id``?

    Read across the alternate separator too, so a cross-base ``a::b`` is caught
    before the rule that would retype it.
    """
    for token in tokens:
        for side in token.replace(_NO_MOVE_ATTR_ALTERNATE_SEPARATOR, ";;").split(";;"):
            if not side:
                continue
            if normalize_lovdata_refid(side) != base_id:
                return False
    return True


def _no_normalize_move_attr(tokens: Sequence[str], *, base_id: str) -> _NOMoveAttrNormalization:
    """Repair a malformed ``data-move-part`` token list, or decline it."""
    if all(_structured_move_attr_skip_reason(token) is None for token in tokens):
        return _NOMoveAttrNormalization(None, _NO_MOVE_ATTR_DECLINED_WELL_FORMED)
    if not base_id or not _no_move_attr_tokens_share_base(tokens, base_id):
        return _NOMoveAttrNormalization(None, _NO_MOVE_ATTR_DECLINED_CROSS_BASE)
    skeleton = _no_move_attr_skeleton(tokens)
    for rule_id, rewrite in _NO_MOVE_ATTR_NORMALIZATION_RULES:
        repaired = rewrite(tokens)
        if repaired == list(tokens):
            continue
        if any(_structured_move_attr_skip_reason(token) is not None for token in repaired):
            continue
        if _no_move_attr_skeleton(repaired) != skeleton:
            continue
        pairs = tuple(cast(Tuple[str, str], tuple(token.split(";;", 1))) for token in repaired)
        if any(lovdata_path_to_address(side) is None for pair in pairs for side in pair):
            return _NOMoveAttrNormalization(None, _NO_MOVE_ATTR_DECLINED_UNRESOLVED)
        return _NOMoveAttrNormalization(pairs, rule_id)
    return _NOMoveAttrNormalization(None, _NO_MOVE_ATTR_DECLINED_NO_RULE)


def _split_move_attr(
    value: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
    source_id: str = "",
    base_id: str = "",
    source_doc: str = "",
    raw_text: str = "",
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    tokens = [token.strip() for token in value.split() if token.strip()]
    normalization = _no_normalize_move_attr(tokens, base_id=base_id)
    if normalization.pairs is not None:
        _append_no_parse_adjudication(
            adjudications_out,
            kind=NO_PARSE_STRUCTURED_MOVE_ATTR_NORMALIZED,
            message=(
                "Norway parser normalized a malformed structured renumber attribute "
                "into well-formed source/destination pairs."
            ),
            source_id=source_id,
            detail=diagnostic_detail(
                rule_id=NO_PARSE_STRUCTURED_MOVE_ATTR_NORMALIZED,
                phase="parse",
                family="source_pathology",
                blocking=False,
                quirks_disposition=QuirksDisposition.APPLY,
                reason=normalization.rule,
                base_id=base_id,
                source_doc=source_doc,
                attr_name="data-move-part",
                declared_tokens=tuple(tokens),
                normalized_legs=tuple(f"{src};;{dst}" for src, dst in normalization.pairs),
                raw_text=raw_text,
            ),
        )
        # Same convention as the loop below: legs are handed back REVERSED,
        # because Lovtidend writes them in ascending prose order.
        return [(src, dst) for src, dst in reversed(normalization.pairs)]
    for token in reversed(tokens):
        reason = _structured_move_attr_skip_reason(token)
        if reason is not None:
            _append_no_parse_adjudication(
                adjudications_out,
                kind=NO_PARSE_MALFORMED_STRUCTURED_RENUMBER_ATTR_SKIPPED,
                message="Norway parser skipped malformed structured renumber token.",
                source_id=source_id,
                detail=diagnostic_detail(
                    rule_id=NO_PARSE_MALFORMED_STRUCTURED_RENUMBER_ATTR_SKIPPED,
                    phase="parse",
                    family="source_pathology",
                    blocking=True,
                    reason=reason,
                    base_id=base_id,
                    source_doc=source_doc,
                    attr_name="data-move-part",
                    raw_token=token,
                    # W-70: WHY the normalizer left this token refused, so the
                    # standing population pin can hold the decline reason and
                    # not merely the count.
                    normalization=normalization.rule,
                    raw_text=raw_text,
                ),
            )
            continue
        src, dst = token.split(";;", 1)
        out.append((src, dst))
    return out


# W-56: Lovtidend's ``data-move-part`` sometimes UNDER-DECLARES a ledd shift.
# The change block's own lead sentence is the operative instruction
# ("Nåværende tredje og fjerde ledd blir fjerde og nytt femte ledd." — TWO
# limbs), but the markup carries only some of the matching move legs
# (``§24-8/ledd/3;;§24-8/ledd/4`` — ONE). Lowering the markup verbatim then
# emits a PARTIAL cascade, and a partial cascade is what destroys live law: the
# surviving 3→4 leg lands on a slot whose occupant is never moved out, so
# (RENUMBER, dest_occupied) recovers by REMOVING that occupant. W-54 proved two
# such firings wrong; tvisteloven § 24-8 lost the in-force vitneforsikring ledd
# exactly this way. The markup is the defect, not the prose.
#
# Corpus sweep (W-56, all 3,089 amendment artifacts / 3,885 change blocks / 286
# with ``data-move-part``): 166 blocks carry ledd-shift prose. 148 agree with
# their markup, 1 has RICHER markup than prose (a ledd→punktum move the prose
# spells as one limb), and 17 declare more limbs than the markup has legs. The
# 17 split three ways and only ONE class is repaired here:
#
#   * 10 blocks carry NO ``data-move-part`` at all — a total drop with no anchor
#     to template from. Repairing those means minting a base act, a section and
#     a container from prose alone; that is a different (larger) production with
#     its own blast radius, recorded rather than guessed at.
#   * 3 blocks carry only MALFORMED tokens (``::`` for ``;;``, a stray space
#     after ``;;``, tokens with no separator at all), already receipted by
#     ``no_parse_malformed_structured_renumber_attr_skipped``. Zero valid legs
#     means zero template, so they stay refused.
#   * 4 blocks carry a well-formed but INCOMPLETE leg set — this production.
#     ``no/lovtid/2024-12-13-78`` (tvisteloven § 24-8, the W-54 firing),
#     ``no/lovtid/2024-05-31-26`` (lov/2018-06-08-28 § 7),
#     ``no/lovtid/2024-06-21-44`` (lov/1999-07-02-64 § 57),
#     ``no/lovtid/2025-12-22-129`` (lov/2020-04-17-29 § 11).
#
# The completion is pure TEMPLATING off markup the block already carries: every
# existing leg must read ``<prefix>/ledd/<n>`` on BOTH sides under one shared
# ``<prefix>``, and the completed set is that same prefix carrying the prose's
# ledd numbers. Nothing about the base act, the section or the container comes
# from the prose — only the shift MAP does. Conservative polarity throughout:
# every check below leaves the markup's own legs exactly as they were rather
# than emitting a guessed set, so a sentence this production cannot fully
# account for lowers to nothing NEW (never to a different partial set).
_NO_LEDD_SHIFT_SECTION_PREFIX_RE = compile_classifier_regex(
    r"^§+\s*[0-9A-Za-z-]+\s+",
    re.IGNORECASE,
    classifier_id="norway.grafter.ledd_shift_section_prefix",
)
_NO_LEDD_SHIFT_MARKER_RE = compile_classifier_regex(
    r"^(?:nåværende|noverande|nåverande|nuværende)\s+",
    re.IGNORECASE,
    classifier_id="norway.grafter.ledd_shift_marker",
)
_NO_LEDD_SHIFT_PIVOT_RE = compile_classifier_regex(
    r"\s+ledd\s+blir\s+",
    re.IGNORECASE,
    classifier_id="norway.grafter.ledd_shift_pivot",
)
_NO_LEDD_SHIFT_TAIL_RE = compile_classifier_regex(
    r"\s+ledd\.?$",
    re.IGNORECASE,
    classifier_id="norway.grafter.ledd_shift_tail",
)
# Newness/currency markers that may sit in front of any ordinal in either list
# ("blir fjerde og NYTT femte ledd"). They carry no address information — the
# ordinal does — so they are stripped before the ordinal lookup.
_NO_LEDD_SHIFT_NEWNESS_MARKERS = ("nytt ", "nye ", "ny ", "nåværende ", "noverande ", "nåverande ")
_NO_LEDD_PATH_STEP = "/ledd/"


def _no_strip_ledd_shift_newness(token: str) -> str:
    token = token.strip()
    changed = True
    while changed:
        changed = False
        for marker in _NO_LEDD_SHIFT_NEWNESS_MARKERS:
            if token.startswith(marker):
                token = token[len(marker) :].strip()
                changed = True
    return token


def _no_ledd_shift_ordinals(phrase: str) -> Optional[list[int]]:
    """``"tredje og fjerde"`` → ``[3, 4]``; ``"nytt tredje til sjette"`` → ``[3, 4, 5, 6]``.

    The ordinal vocabulary is ``_NORWEGIAN_ORDINALS`` verbatim — deliberately NOT
    widened here. An ordinal this grammar cannot name returns ``None`` and the
    whole completion is refused, which is the all-or-nothing rule at the grammar.
    """
    ordinals: list[int] = []
    for chunk in re.split(r"\s*(?:,| og )\s*", _normalize_space(phrase).lower()):
        chunk = _no_strip_ledd_shift_newness(chunk)
        if not chunk:
            return None
        low, separator, high = chunk.partition(" til ")
        first = _NORWEGIAN_ORDINALS.get(_no_strip_ledd_shift_newness(low))
        if first is None:
            return None
        if not separator:
            ordinals.append(int(first))
            continue
        last = _NORWEGIAN_ORDINALS.get(_no_strip_ledd_shift_newness(high))
        if last is None or int(last) < int(first):
            return None
        ordinals.extend(range(int(first), int(last) + 1))
    return ordinals


def _no_ledd_shift_pairs_from_sentence(sentence: str) -> Optional[tuple[str, list[tuple[int, int]]]]:
    """Lower one ledd-shift sentence to ``(section_label, [(src, dst), …])``.

    ``section_label`` is ``""`` when the sentence does not spell one (the common
    shape — the block inherits its section from the preceding lead). Returns
    ``None`` for anything that is not exactly one fully-accounted ledd shift.
    """
    residue = _normalize_space(sentence)
    section_label = ""
    # The section may be spelled before OR after the currency marker, so the
    # prefix anchor is tried on both sides of it.
    # lawvm-regex: owning_parser this IS the ledd-shift sentence parser
    prefix_match = _NO_LEDD_SHIFT_SECTION_PREFIX_RE.match(residue)
    if prefix_match is not None:
        section_label = _normalize_no_section_label(prefix_match.group(0).lstrip("§").strip())
        residue = residue[prefix_match.end() :]
    # lawvm-regex: owning_parser this IS the ledd-shift sentence parser
    marker_match = _NO_LEDD_SHIFT_MARKER_RE.match(residue)
    if marker_match is None:
        return None
    residue = residue[marker_match.end() :]
    # lawvm-regex: owning_parser this IS the ledd-shift sentence parser
    prefix_match = _NO_LEDD_SHIFT_SECTION_PREFIX_RE.match(residue)
    if prefix_match is not None:
        if section_label:
            return None
        section_label = _normalize_no_section_label(prefix_match.group(0).lstrip("§").strip())
        residue = residue[prefix_match.end() :]
    # lawvm-regex: owning_parser this IS the ledd-shift sentence parser
    tail_match = _NO_LEDD_SHIFT_TAIL_RE.search(residue)
    if tail_match is None:
        return None
    residue = residue[: tail_match.start()]
    # Exactly one pivot: "… ledd blir …" twice in one sentence is a shape this
    # grammar cannot attribute, so it is refused rather than split on the first.
    pivots = list(_NO_LEDD_SHIFT_PIVOT_RE.finditer(residue))  # lawvm-regex: owning_parser this IS the ledd-shift sentence parser
    if len(pivots) != 1:
        return None
    sources = _no_ledd_shift_ordinals(residue[: pivots[0].start()])
    destinations = _no_ledd_shift_ordinals(residue[pivots[0].end() :])
    if sources is None or destinations is None or len(sources) != len(destinations):
        return None
    if len(set(sources)) != len(sources) or len(set(destinations)) != len(destinations):
        return None
    if any(src == dst for src, dst in zip(sources, destinations, strict=True)):
        return None
    return section_label, list(zip(sources, destinations, strict=True))


#: The currency qualifiers a Lovtidend drafter may put in front of an address to
#: mean "the one that is there BEFORE this act lands" — bokmål and nynorsk, plus
#: the older ``nuværende`` spelling. Every member carries the same information:
#: none. They do not narrow, widen or relocate the address they precede, which is
#: why a production may admit the whole set wherever it admits one of them.
#:
#: W-61 established the set (measured on the repeal-then-shift lead, where 24 of
#: 45 corpus leads spell the qualifier as something other than ``Nåværende`` or
#: omit it); W-67 reuses it verbatim for the section-renumber lead rather than
#: minting a second, drifting copy. The alternation is spelled here WITHOUT its
#: surrounding group so each use site can choose whether the qualifier is
#: optional — it is on the repeal-then-shift lead, required on the renumber lead.
_NO_CURRENCY_QUALIFIER_ALTERNATION = (
    r"nåværende|noverande|nåverande|nuværende|någjeldende|nogjeldande|gjeldende|gjeldande"
)


# ── W-66: the atomic sibling-set relabel, and where its address comes from ────
#
# THE CONSTRUCT. "Nåværende femte og sjette ledd blir sjette og sjuende ledd."
# is not two independent renumbers. It is ONE relabel of a sibling SET, read
# against the PRE-operation snapshot, and its source and destination sets
# OVERLAP: relabelling 5→6 first writes onto the live sixth ledd, which the
# occupied-destination recovery then clears — the exact shape W-54 caught
# destroying tvisteloven's vitneforsikring. Applied in the other order (6→7,
# then 5→6) nothing is ever written onto an occupant.
#
# Two things make that safe here rather than lucky. (i) The pairs are emitted in
# a proven VACATE-BEFORE-OCCUPY order by ``_no_ordered_set_relabel_pairs``, so
# the op stream is safe read straight through, without appealing to any later
# stage. (ii) The kernel's within-group structural-vacate stage
# (``no_ordering_profile``, ``renumber_vacate=True``) independently topologically
# sorts RENUMBERs that vacate each other's destinations. The two agree by
# construction, and a pair set for which NO safe order exists (a cycle — a pure
# swap, which sequential relabelling cannot express at all) is REFUSED rather
# than emitted in some order and hoped over. Corpus-wide today no accepted lead
# is cyclic, so the guard costs the production nothing; it is there because the
# absence of a cycle is the only reason the emitted order is a proof.
#
# THE MEASURED POPULATION, read back off the ops actually minted (not off a
# prediction), against the 9,265 corpus ``no_parse_unstructured_lead_unmatched``
# refusals: 642 lead OCCURRENCES accept — 622 distinct (instrument, lead) pairs
# over 421 instruments and 207 base acts, minting 1,147 RENUMBER legs — and every
# one is in W-62's ``renumber_shift`` family at ``ledd`` depth. Split by how the
# address is found: 250 occurrences name their own ``§``, 392 inherit it. Split by
# sentence pattern: 592 are accepted by W-56's SHIPPED
# ``_no_ledd_shift_pairs_from_sentence`` unchanged, 50 need only the currency
# qualifier widened to ``_NO_CURRENCY_QUALIFIER_ALTERNATION`` (W-61's measured
# set). 244 of the 642 have OVERLAPPING source and destination sets, which is the
# population this whole ordering argument exists for.
#
# Shift signatures, and they are why the ordering below is a real topological sort
# rather than "descending if k > 0": 502 shift by +1, 63 by −1, 55 by +2, 9 by −2,
# 8 by +3, 2 by +4, 2 by −3, and ONE lead is not a uniform shift at all (a {+1,+2}
# map). Legs per occurrence run 1 to 7 (380 singletons, 132 pairs, then a tail).
#
# WHAT IS DELIBERATELY LEFT REFUSED.
#   * The qualifier is REQUIRED. "Femte ledd blir nytt sjette ledd." (55 further
#     occurrences, 55 distinct leads) says nothing about WHICH edition its
#     ordinals are read against, and reading the source set against the
#     pre-operation snapshot is this whole production's premise. A production may
#     not assume the premise it exists to honour. Sized, not taken.
#   * Depths other than ``ledd`` — ``punktum``, ``bokstav``, ``nr`` — are a
#     different address arithmetic (they hang below a ledd that must itself be
#     resolved) and are not in this population.
#   * 40 receipt triples over 37 distinct leads whose address this grammar cannot
#     establish get the typed receipt below rather than a guess.
NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED = "no_parse_ledd_set_relabel_address_unresolved"
NO_PARSE_LEDD_SET_RELABEL_ORDER_UNPROVABLE = "no_parse_ledd_set_relabel_order_unprovable"
#: W-66b. The SECOND way a punktum-depth relabel's address can fail. The section
#: half reuses the kind above verbatim — it is the same helper failing the same
#: way — so this member names only what is new at this depth: the LEDD the
#: punktum hangs below could not be established. See the W-66b block comment.
NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED = "no_parse_punktum_set_relabel_ledd_unresolved"
#: W-76. The same failure one family further out: a bokstav/nr. relabel resolved
#: its SECTION but not the LEDD its item hangs below. It is a kind of its own
#: rather than a reuse of the punktum member above — unlike W-66c, which reuses
#: both kinds because it runs the reader UNCHANGED, this production retargets the
#: reader's depth conjunct, so it is not the same reader failing the same way. A
#: census tells bokstav from nr. by the receipt's own ``depth`` detail key.
NO_PARSE_ITEM_SET_RELABEL_LEDD_UNRESOLVED = "no_parse_item_set_relabel_ledd_unresolved"
#: Stamped on every op this production mints, and read by the apply seam. It is
#: the ONLY thing that tells the (RENUMBER, dest_occupied) branch that this op
#: must refuse rather than clear its destination — see the block comment there.
NO_LEDD_SET_RELABEL_PROVENANCE_TAG = "no_ledd_set_relabel"
NO_REPLAY_LEDD_SET_RELABEL_OCCUPIED_DESTINATION_REFUSED = (
    "no_replay_ledd_set_relabel_occupied_destination_refused"
)
#: W-77, the item-depth PAYLOAD production's three parse-plane refusals. The
#: address and ledd members are kinds of their own rather than reuses of W-66's
#: and W-76's: this production resolves the SAME two helpers but it is a
#: different instruction failing (a payload that cannot be placed, not a relabel
#: that cannot be spelled), and a census must be able to tell the two apart
#: without reading a detail key. The extent member has no sibling at any depth —
#: it is what a production that ADDS text owes the reader when it cannot prove
#: which text. All three are parse-plane and therefore OUT of
#: ``_NO_SKIP_ADJUDICATION_KINDS`` (the conserved-partition rule); the apply-plane
#: refusal below is IN it.
NO_PARSE_ITEM_INSERT_PAYLOAD_ADDRESS_UNRESOLVED = "no_parse_item_insert_payload_address_unresolved"
NO_PARSE_ITEM_INSERT_PAYLOAD_LEDD_UNRESOLVED = "no_parse_item_insert_payload_ledd_unresolved"
NO_PARSE_ITEM_INSERT_PAYLOAD_EXTENT_UNPROVABLE = "no_parse_item_insert_payload_extent_unprovable"
#: Stamped on every op W-77 mints, and read by the apply seam. It is the ONLY
#: thing that tells the (INSERT, target_occupied) branch that this op must refuse
#: rather than replace the occupant — see the block comment there.
NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG = "no_item_insert_payload"
NO_REPLAY_ITEM_INSERT_PAYLOAD_OCCUPIED_TARGET_REFUSED = (
    "no_replay_item_insert_payload_occupied_target_refused"
)

# ── W-98: the pre-2001 lead grammar, closed on the kringkastingsloven witness ──
#
# Item 97 (W-91) ran the OCR-reconstructed 1992 broadcasting act and its eleven
# cached amending acts through this walk and found the OCR side clean and the
# LEAD GRAMMAR binding: nine distinct shapes on certified lines were refused
# ``no_parse_unstructured_lead_unmatched``. Each shape below is one production,
# sized over the 7,853 corpus refusals at the W-98 base pin (``79a4987e``),
# harvested UNTRUNCATED through the adjudication appender rather than off the
# 240-char ``source_excerpt`` — the counts live on the production that owns them.
#
# The provenance tags are read by the apply seam. W-66's and W-77's pattern is
# kept exactly: a tag on the op is the ONLY thing that turns a θ recovery cell
# into a refusal for that op, so every shipped cell stays untouched for every op
# that is not one of these productions'.
#: Stamped on the CHAPTER op a ``Kapittel N skal lyde:`` / ``Nytt kapittel N skal
#: lyde:`` lead mints. The REPLACE branch reads it to run the uncarried-sections
#: guard; the INSERT branch reads it to refuse an occupied chapter label.
NO_CHAPTER_REENACTMENT_PROVENANCE_TAG = "no_chapter_reenactment"
#: Stamped on the heading-only CHAPTER op an ``Overskriften til kapittel N skal
#: lyde:`` lead mints. Carried for census visibility; the apply seam's
#: heading-only merge is keyed on the payload SHAPE, not on this tag.
NO_CHAPTER_HEADING_PROVENANCE_TAG = "no_chapter_heading"
#: Stamped on every op the compound ``§ X <ord> ledd oppheves. Nytt <ord> ledd
#: … skal lyde:`` lead mints. Its INSERT legs refuse an occupied slot rather than
#: take the θ (INSERT, target_occupied) recovery.
NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG = "no_ledd_repeal_reenact"
#: Stamped on an item REPLACE whose payload was read off the ONE ``legalP`` that
#: follows a single-item lead (no ``li`` carrier). Census visibility only.
NO_ITEM_PAYLOAD_SINGLE_TEXT_ARTICLE_PROVENANCE_TAG = "no_item_payload_single_text_article"
#: Parse-plane refusals. All OUT of ``_NO_SKIP_ADJUDICATION_KINDS`` (the
#: conserved-partition rule: parse refusals mint nothing to skip).
NO_PARSE_CHAPTER_REENACTMENT_PAYLOAD_UNRESOLVED = "no_parse_chapter_reenactment_payload_unresolved"
NO_PARSE_CHAPTER_HEADING_PAYLOAD_UNRESOLVED = "no_parse_chapter_heading_payload_unresolved"
NO_PARSE_MIXED_MEMBER_PAYLOAD_ARITY_MISMATCH = "no_parse_mixed_member_payload_arity_mismatch"
NO_PARSE_LEDD_REPEAL_REENACT_PAYLOAD_ARITY_MISMATCH = "no_parse_ledd_repeal_reenact_payload_arity_mismatch"
NO_PARSE_SECTION_RANGE_UNEXPANDABLE = "no_parse_section_range_unexpandable"
#: Apply-plane refusals, both IN ``_NO_SKIP_ADJUDICATION_KINDS``: nothing lands.
NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED = (
    "no_replay_chapter_reenactment_uncarried_sections_refused"
)
NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED = (
    "no_replay_reenactment_insert_occupied_target_refused"
)
#: The (INSERT, target_occupied) refusal, keyed on provenance tag: W-77's tag keeps
#: W-77's kind byte-for-byte; the W-98 productions share one generic kind and are
#: told apart by the ``production`` detail key. One branch on the load-bearing
#: seam, not three.
_NO_INSERT_OCCUPIED_REFUSING_TAGS: dict[str, str] = {
    NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG: NO_REPLAY_ITEM_INSERT_PAYLOAD_OCCUPIED_TARGET_REFUSED,
    NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG: NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED,
    NO_CHAPTER_REENACTMENT_PROVENANCE_TAG: NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED,
}

# ── W-69c: the same atomic ordering, generalized to (parent_path, label) ──────
#
# W-66's ``_no_ordered_set_relabel_pairs`` orders a relabel over integer ORDINALS
# inside ONE sibling set. The structured ``data-move-part`` lane mints legs that
# leave their container — ``§3/ledd/3 → §2/ledd/4`` — so a relocation belongs to
# TWO sibling sets and the leg that frees its destination lives in the other one.
# The dependency node therefore has to be the resolved ``(parent_path, label)``
# pair, which is exactly ``LegalAddress.path``: a full path IS its parent path
# plus its own ``(kind, label)`` step.
#
# WHERE THIS LIVES, AND WHY IT IS THE APPLY PLANE. The two colliding legs on
# ``no/lov/2009-06-19-44`` come from TWO DIFFERENT ``data-move-part`` attributes
# on two different ``article.change`` elements of one instrument. No parse-plane
# production sees both — each production sees one attribute — so the parse plane
# is structurally unable to detect the collision. The apply seam is the first
# place the legs meet, so the check is here, alongside W-66's own apply-plane
# refusal and in the same receipt family.
#
# WHY ``renumber_vacate=True`` DID NOT ALREADY DO THIS, which the design pass
# asked to be answered before any code. The kernel's structural-vacate stage
# (``core/op_ordering._ordered_renumber_group``) is ALREADY keyed on full paths —
# ``by_target = {op.target.path: op}`` and ``by_target.get(op.destination.path)``
# — so it is cross-container-capable in principle, and on this law it worked
# exactly as advertised: it hoisted ``§2/ledd/4 → §2/ledd/5`` in front of
# ``§3/ledd/3 → §2/ledd/4``. What it cannot express is the constraint that is
# actually violated. It models ONE relation — "the leg whose TARGET is my
# destination must run first" — and it answers by producing a PERMUTATION. Here
# two legs, ``§3/ledd/3 → §2/ledd/4`` and ``§2/ledd/3 → §2/ledd/4``, claim the
# SAME destination, and no permutation of them exists in which the second does
# not land on the first: whichever runs last writes onto a live sibling. A
# topological sort is the wrong shape of answer to a question whose answer is
# "there is no order". The stage did not miss the case; it is incapable of
# reporting it, and it has no ``by_destination`` map to notice it with. W-66's
# parse-plane function has the identical hole (its ``by_source`` dict likewise
# never looks for a repeated destination); it is unreachable there today only
# because a single lead's grammar cannot spell one destination twice.
#
# SO THE GUARD IS A PROVABILITY TEST, NOT A REORDERING. Over one affecting-act
# group's DISTINCT RENUMBER legs, keyed on ``(parent_path, label)``:
#   * a destination claimed by more than one leg is UNSATISFIABLE;
#   * a cycle in "my destination is your source" is UNSATISFIABLE (W-66's guard,
#     unchanged, lifted to the same keying);
#   * a source sent to two different destinations is UNSATISFIABLE.
# "Distinct" is load-bearing: a leg announced twice is one instruction, and two
# corpus groups repeat one — see the docstring of the helper.
# Any of those makes the CONNECTED COMPONENT they sit in unprovable, and every
# leg of that component refuses with a typed receipt and no write. The component
# — not the group, and not the single leg — is the unit because legs in
# different components cannot interfere, and because refusing a leg out of the
# middle of a shift chain would leave the chain half-applied, which is the W-56
# failure mode this whole lane exists to prevent. Under-application is safe;
# picking a winner between two contradictory instructions is not, and would be
# a semantics change on landed ops (W-70's precedent).
NO_REPLAY_RELOCATION_ORDER_UNPROVABLE_REFUSED = "no_replay_relocation_order_unprovable_refused"

# The section address as a node's OWN text spells it. The trailing letter class
# is guarded by a negative lookahead on the next letter, and that guard is not
# cosmetic: without it "§ 12-1 nytt tredje ledd skal lyde:" reads its section as
# "12-1 n", silently inventing a section that does not exist. Measured — the
# first cut of this reader made exactly that mistake on 25 of 30 sampled
# antecedents before the lookahead was added.
_NO_ANTECEDENT_SECTION_RE = compile_classifier_regex(
    r"§ ?((?:[0-9][0-9-]*[0-9]|[0-9])(?: [A-Za-z](?![A-Za-zÆØÅæøå]))?)",
    re.IGNORECASE,
    classifier_id="norway.grafter.antecedent_section_address",
)
# An antecedent that amends ANOTHER AMENDMENT establishes an address in that
# amendment, not in the base act ("I endringen av § 19-8 skal nytt sjette ledd
# lyde:", "I lovens del XIV skal endringen av folketrygdloven § 16-11 femte ledd
# lyde:"). 7 corpus antecedents are of this shape and all 7 are refused here:
# the ledd numbering a meta-amendment talks about is the numbering of a text
# that has not landed yet, so inheriting from it would relabel the wrong tree.
_NO_META_AMENDMENT_ANTECEDENT_RE = compile_classifier_regex(
    r"\bendring(?:en|a|ene|ane)\s+(?:av|i)\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.meta_amendment_antecedent",
)
#: The widened sibling-set relabel sentence. Tried ONLY after W-56's shipped
#: helper has declined, so no sentence that parses today can change what it
#: parses. It differs from the shipped helper in exactly one token — the
#: currency qualifier is drawn from the measured set instead of the four
#: ``nåværende`` spellings — and it is anchored end to end, which is what keeps
#: ordinary statutory prose containing "… første ledd blir …" out: everything
#: between the anchors must reduce to two ordinal lists.
#:
#: The qualifier is REQUIRED and may sit on either side of the ``§`` — both word
#: orders are attested ("Nåværende § 2 fjerde og femte ledd blir …" beside
#: "§ 29 nåværende fjerde til sjette ledd blir …"), which is why the head is two
#: explicit branches rather than two optional groups. Two optional groups would
#: make the qualifier optional by accident, and that single character of slack
#: admits ordinary drafting prose ("Andre ledd blir nytt tredje ledd.") whose
#: source edition is exactly what is unstated.
_NO_SET_RELABEL_SECTION_LABEL = r"[0-9][0-9A-Za-z-]*(?:\s+[A-Za-z])?"
#: The SHARED head of every sibling-set relabel sentence in this module: a
#: required currency qualifier and an optional ``§``, in either word order,
#: capturing the section into ``qualifier_first_section`` /
#: ``section_first_section``. Named at W-76 rather than spelled a third time —
#: the rule-of-three point, and the FW-08 ``clause_boundary_dup`` sensor's. The
#: three patterns built from it are byte-identical to the strings they were
#: before the extraction, which is pinned as a test fact.
_NO_SET_RELABEL_QUALIFIED_SECTION_HEAD = (
    r"^(?:(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+"
    r"(?:§\s*(?P<qualifier_first_section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+)?"
    r"|§\s*(?P<section_first_section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+"
    r"(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+)"
)
_NO_SET_RELABEL_WIDENED_PATTERN = (
    _NO_SET_RELABEL_QUALIFIED_SECTION_HEAD
    + r"(?P<source>.+?)\s+ledd\s+blir\s+(?P<destination>.+?)\s+ledd\.?$"
)


def _no_ledd_set_relabel_pairs(lead: str) -> Optional[tuple[str, list[tuple[int, int]], str]]:
    """``Gjeldende femte og sjette ledd blir sjette og sjuende ledd.`` → pairs.

    Returns ``(section_label, [(src, dst), …], pattern)`` where ``section_label``
    is ``""`` when the sentence does not spell one, or ``None`` when this grammar
    declines the sentence. ``pattern`` names WHICH of the two attempts matched, so
    the additive ordering below is a test's fact rather than a comment's claim.

    Attempt order is the W-61/W-67 shape: W-56's SHIPPED
    ``_no_ledd_shift_pairs_from_sentence`` first, character for character, then
    the widened sibling. Both go through the same ``_no_ledd_shift_ordinals``
    vocabulary, so ``til`` ranges and the ``nytt``/``nye`` newness markers behave
    identically on both paths and there is only ever one ordinal grammar.
    """
    shipped = _no_ledd_shift_pairs_from_sentence(lead)
    if shipped is not None:
        return shipped[0], shipped[1], "shipped"
    # Inline ``re.match`` rather than a compiled classifier constant, for the
    # reason the two sibling productions above already record: the adjacent
    # ``(.+?)`` spans cannot pass ``compile_classifier_regex``'s backtracking lint.
    # lawvm-regex: owning_parser this IS the widened sibling-set relabel sentence parser
    match = re.match(_NO_SET_RELABEL_WIDENED_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        # W-98 (h): the third attempt, tried only after both qualified readers
        # have declined. See ``_no_unqualified_self_addressed_ledd_shift``.
        return _no_unqualified_self_addressed_ledd_shift(lead)
    sources = _no_ledd_shift_ordinals(match.group("source"))
    destinations = _no_ledd_shift_ordinals(match.group("destination"))
    if sources is None or destinations is None or len(sources) != len(destinations):
        return None
    if len(set(sources)) != len(sources) or len(set(destinations)) != len(destinations):
        return None
    if any(src == dst for src, dst in zip(sources, destinations, strict=True)):
        return None
    section = match.group("qualifier_first_section") or match.group("section_first_section")
    return (
        _normalize_no_section_label(section) if section else "",
        list(zip(sources, destinations, strict=True)),
        "widened",
    )


# ── W-66b: the same sibling-set relabel, one depth word down (PUNKTUM) ────────
#
# THE CONSTRUCT is W-66's, character for character, with ``punktum`` where
# ``ledd`` stood: "Nåværende annet punktum blir nytt tredje punktum." It is one
# relabel of ONE sibling set read against the pre-operation snapshot, its source
# and destination sets overlap, and the ordering argument is therefore identical
# — which is why ``_no_ordered_set_relabel_pairs`` is REUSED here rather than
# forked. A punktum relabel stays inside one ledd's sentence list, so it is a
# single-sibling-set problem exactly as the ledd case is, and none of W-69c's
# cross-container machinery is needed for it (item 76 (c), confirmed).
#
# WHAT IS GENUINELY NEW, and it is the address, not the sentence. A punktum
# address hangs below a LEDD that must itself resolve, so this grammar has to
# establish TWO levels where W-66 established one, and it has one more way to
# fail. Measured over the 8,583 ``no_parse_unstructured_lead_unmatched`` refusals
# at the W-66b base pin (`5c0fb190d`), harvested UNTRUNCATED — the shipped
# adjudication detail clips ``source_excerpt`` at 240 chars, so a depth word past
# that bound is invisible to a receipt-plane census:
#
#   165 refusals / 84 distinct leads / 115 instruments / 78 base acts.
#
# Of the 165, only 23 spell a ``§`` of their own and only 16 spell a ledd, so the
# DOM-local antecedent carries this family rather than decorating it. Split by
# what the production does with them:
#
#   * 112 LOWER (59 distinct leads, 161 RENUMBER legs);
#   *  27 refuse ``NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED``, every one
#         ``antecedent_names_no_ledd`` — a punktum hanging directly under a
#         section, or under a ``nr.``/``bokstav`` container the ledd reader is
#         deliberately blind to;
#   *  10 refuse ``NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED`` (W-66's kind,
#         reused because it is the same helper failing the same way): 5
#         ``part_has_no_antecedent_lead``, 4 ``antecedent_names_no_section``, 1
#         ``antecedent_names_several_sections``;
#   *  16 are DECLINED by this grammar and keep their shipped refusal.
#
# WHAT IS DELIBERATELY LEFT REFUSED, and each limb is a shape in that 16.
#   * The DESTINATION side must reduce to ordinals ALONE. A destination that
#     respells a ledd is either a RELOCATION out of the sibling set ("Nåværende
#     annet til fjerde punktum blir nytt fjerde ledd første til tredje punktum."
#     — W-69's territory, and the shape this production must never lower) or a
#     harmless restatement of the same ledd ("… blir første ledd andre og nytt
#     tredje punktum."). Refusing BOTH is the point: the anchored destination is
#     the only thing that makes the cross-container case impossible by
#     construction rather than by a check someone can delete. 5 leads pay for it.
#   * ``bokstav``/``nr.`` sub-containers between the ledd and the punktum
#     ("§ 18-3 nåværende annet ledd bokstav b annet punktum blir …") decline at
#     the ordinal vocabulary, because the residue is not a list of ordinals. 6
#     leads, and lowering them needs an address level this production does not
#     model.
#   * The ordinal vocabulary is ``_NORWEGIAN_ORDINALS`` VERBATIM, so "sjuande"
#     declines (1 lead) exactly as it does at ledd depth. One ordinal grammar.
#   * "blir TIL" (2 leads) and a parenthetical currency aside (1 lead) decline at
#     the anchors, unchanged from W-66's reasoning about what an anchor is for.
#
# NOT IN THIS POPULATION AT ALL, and the census says so rather than the charter:
# ``bokstav`` and ``nr.`` are NOT this grammar one word further down. They PREFIX
# their depth word to a letter or an arabic numeral ("Nåværende bokstav c blir
# bokstav d.", "Nåværende nr. 2 blir ny nr. 3."), where ``ledd``/``punktum``
# POSTFIX it to a Norwegian ordinal. Zero of the 8,583 refusals match this
# pattern at either depth. Sized with a classifier of the RIGHT shape they are 27
# refusals / 23 leads / 17 bases (``bokstav``) and 36 / 33 / 19 (``nr.``) — a
# real family, but a different sentence grammar over a different label
# vocabulary, and therefore a different item. W-76 is that item; its block
# comment carries the counts re-derived at its own pin, where they are unmoved.
_NO_SET_RELABEL_PUNKTUM_PATTERN = (
    _NO_SET_RELABEL_QUALIFIED_SECTION_HEAD
    + r"(?P<source>.+?)\s+punktum\s+blir\s+(?P<destination>.+?)\s+punktum\.?$"
)
#: Splits an optional ``<ordinal> ledd`` phrase off the front of the SOURCE side.
#: It is applied to the source residue rather than spelled as an optional group
#: in the pattern above, so the ledd ordinal goes through the SAME
#: ``_no_ledd_shift_ordinals`` vocabulary as every other ordinal in this module
#: — a second ordinal alternation inside a regex is exactly the drift W-56's
#: single-vocabulary rule exists to prevent.
_NO_SET_RELABEL_PUNKTUM_LEDD_SPLIT = r"^(?P<ledd>.+?)\s+ledd\s+(?P<rest>.+)$"


def _no_punktum_set_relabel_pairs(
    lead: str,
) -> Optional[tuple[str, str, list[tuple[int, int]], str]]:
    """``Nåværende annet punktum blir nytt tredje punktum.`` → pairs.

    Returns ``(section_label, ledd_label, [(src, dst), …], pattern)``.
    ``section_label`` and ``ledd_label`` are ``""`` when the sentence does not
    spell one (the caller then inherits them from the DOM-local antecedent), and
    the whole result is ``None`` when this grammar declines the sentence.

    ``pattern`` is always ``"punktum"``. It exists for the same reason W-66's
    does: the caller tries the shipped LEDD grammar FIRST and this one only after
    it has declined, and naming the winner makes that ordering a test's fact
    rather than a comment's claim. The two are disjoint by their tail anchors, so
    the ordering costs nothing and buys the guarantee that nothing W-66 lowers
    today can change what it lowers.
    """
    # Inline ``re.match`` rather than a compiled classifier constant, for the
    # reason W-66's sibling records: the adjacent ``(.+?)`` spans cannot pass
    # ``compile_classifier_regex``'s backtracking lint.
    # lawvm-regex: owning_parser this IS the punktum sibling-set relabel sentence parser
    match = re.match(_NO_SET_RELABEL_PUNKTUM_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    source_phrase = match.group("source")
    ledd_label = ""
    # lawvm-regex: owning_parser the same parser's optional ledd-phrase split, validated by the ordinal vocabulary below
    ledd_split = re.match(_NO_SET_RELABEL_PUNKTUM_LEDD_SPLIT, source_phrase, re.IGNORECASE)
    if ledd_split is not None:
        ledd_ordinals = _no_ledd_shift_ordinals(ledd_split.group("ledd"))
        if ledd_ordinals is None or len(ledd_ordinals) != 1:
            return None
        ledd_label = str(ledd_ordinals[0])
        source_phrase = ledd_split.group("rest")
    sources = _no_ledd_shift_ordinals(source_phrase)
    # The DESTINATION is read WITHOUT the ledd split, and that asymmetry is the
    # whole cross-container guard: a destination that respells a ledd cannot
    # reduce to ordinals, so it declines here instead of being lowered into
    # another sibling set.
    destinations = _no_ledd_shift_ordinals(match.group("destination"))
    if sources is None or destinations is None or len(sources) != len(destinations):
        return None
    if len(set(sources)) != len(sources) or len(set(destinations)) != len(destinations):
        return None
    if any(src == dst for src, dst in zip(sources, destinations, strict=True)):
        return None
    section = match.group("qualifier_first_section") or match.group("section_first_section")
    return (
        _normalize_no_section_label(section) if section else "",
        ledd_label,
        list(zip(sources, destinations, strict=True)),
        "punktum",
    )


# ── W-66c: the punktum-depth REPEAL, the relabel's companion ──────────────────
#
# THE CONSTRUCT. "§ 20 første ledd annet punktum oppheves." — the shipped
# ledd-depth repeal lane one address level down, with the SAME address
# arithmetic W-66b established for the relabel: a section spelled or inherited,
# then a ledd spelled or inherited, both from the ONE ``defaultP`` antecedent.
# The op is the SHIPPED ``StructuralAction.REPEAL`` at a ``sentence`` leaf, which
# is the ledd-depth lane's own op shape with the target one level deeper: the
# apply-plane REPEAL branch is ``tree_ops.remove_at(body, resolved_path)`` and is
# depth-agnostic, and W-69b's ``_materialize_sentence_parent_for`` runs
# unconditionally ahead of target resolution on the structural arm, so a
# ``setning/N`` target resolves without one apply-plane edit.
#
# WHY IT MATTERS BEYOND ITS OWN LEADS. W-66b's one candidate-coincident relabel
# leg (`no/lovtid/2022-06-10-38` on `no/lov/2021-06-18-121` § 20 første ledd)
# refuses at apply under W-66's occupied-destination guard, because the slot the
# relabel aims at is still held by the sentence THIS production repeals. The
# ordering that makes the pair work is not document order and not luck: the
# kernel's structural-vacate stage (``no_ordering_profile``, ``_no_group_key`` =
# ``(effective, enacted, source_id)``) runs every REPEAL in a group before every
# RENUMBER in it, and both legs come from one instrument at one moment, so they
# are always in one group and the repeal always runs first.
#
# THIS PRODUCTION DESTROYS TEXT, which no other lowering item in this programme
# has done at this scale, and the grammar is drawn tighter than the relabel's
# because of it:
#
#   * The verb is ``oppheves`` ALONE — the shipped ledd-depth lane's own anchor
#     (``r"^§ … ledd oppheves\.?$"``), not W-74's wider
#     ``(?:blir\s+)?opphev(?:es|a)``. Measured cost of the narrowing: 24 refusals
#     / 24 leads / 15 base acts spell ``blir oppheva``/``opphevast``/``skal
#     opphevast``, and they keep their shipped refusal. Widening the verb of a
#     text-destroying production is a separate decision from founding it.
#   * The sentence must END at the verb. Every run-on ("§ 8-7 første ledd annet
#     punktum oppheves. Nåværende tredje punktum blir annet punktum.") declines,
#     because its second sentence is a relabel this grammar does not read and
#     lowering only the destroying half would leave the statute mis-numbered.
#   * The target side reduces through ``_no_ledd_shift_ordinals`` VERBATIM, so
#     ``siste punktum`` (an address the apply plane can in fact resolve, via
#     ``sentence/last``) declines here: "the last sentence" is a count of what is
#     standing, and a repeal that destroys by counting is the one shape this item
#     must not take on trust. ``bokstav``/``nr.`` sub-containers between the ledd
#     and the punktum decline at the same vocabulary.
#   * A LEDD is REQUIRED. 43 refusals spell a section and no ledd
#     ("§ 16 annet punktum oppheves.") — a punktum hanging directly under a
#     section — and take the typed ledd receipt rather than a shallow-host guess.
#
# Measured over the 8,434 ``no_parse_unstructured_lead_unmatched`` refusals at
# the W-66c base pin (``f076323d8``), harvested UNTRUNCATED: the family is 293
# refusals / 235 distinct leads / 135 instruments / 136 base acts, of which 248
# lower (207 leads, 279 REPEAL legs over 120 bases), 43 take the ledd receipt and
# 2 the section receipt. Only 46 of the 136 written bases have a replayable
# source at all (item 81's standing caution, re-derived), which is why 279 minted
# legs are a much smaller number of actual destructions.
_NO_PUNKTUM_REPEAL_PATTERN = (
    r"^(?:§\s*(?P<section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+)?"
    r"(?P<targets>.+?)\s+punktum\s+oppheves\.?$"
)


def _no_punktum_repeal_targets(lead: str) -> Optional[tuple[str, str, list[int]]]:
    """``§ 20 første ledd annet punktum oppheves.`` → ``("20", "1", [2])``.

    Returns ``(section_label, ledd_label, [ordinal, …])``. ``section_label`` and
    ``ledd_label`` are ``""`` when the sentence does not spell one (the caller
    then inherits from the DOM-local antecedent, exactly as the relabel does),
    and the whole result is ``None`` when this grammar declines the sentence.

    The optional ``<ordinal> ledd`` phrase is split off the residue in code
    rather than spelled as a group in the pattern, for W-66b's reason: the ledd
    ordinal then reads through the SAME ``_no_ledd_shift_ordinals`` vocabulary as
    every other ordinal in this module.
    """
    # Inline ``re.match`` rather than a compiled classifier constant, for the
    # reason W-66's and W-66b's siblings record: the adjacent ``(.+?)`` span
    # cannot pass ``compile_classifier_regex``'s backtracking lint.
    # lawvm-regex: owning_parser this IS the punktum-depth repeal sentence parser
    match = re.match(_NO_PUNKTUM_REPEAL_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    residue = match.group("targets")
    ledd_label = ""
    # lawvm-regex: owning_parser the same parser's optional ledd-phrase split, validated by the ordinal vocabulary below
    ledd_split = re.match(_NO_SET_RELABEL_PUNKTUM_LEDD_SPLIT, residue, re.IGNORECASE)
    if ledd_split is not None:
        ledd_ordinals = _no_ledd_shift_ordinals(ledd_split.group("ledd"))
        if ledd_ordinals is None or len(ledd_ordinals) != 1:
            return None
        ledd_label = str(ledd_ordinals[0])
        residue = ledd_split.group("rest")
    targets = _no_ledd_shift_ordinals(residue)
    if not targets:
        return None
    # A repeated ordinal would mint two REPEALs at one address, the second of
    # which destroys whatever the relabel arithmetic has since moved into it.
    if len(set(targets)) != len(targets):
        return None
    section = match.group("section")
    return (
        _normalize_no_section_label(section) if section else "",
        ledd_label,
        targets,
    )


# ── W-76: the sibling-set relabel at ITEM depth (bokstav / nr.) ───────────────
#
# THE CONSTRUCT is W-66's, unchanged: ONE relabel of ONE sibling set, read
# against the pre-operation snapshot, source and destination sets overlapping.
# The atomicity argument therefore transfers whole and
# ``_no_ordered_set_relabel_pairs`` is REUSED rather than forked — a bokstav or
# nr. relabel stays inside one ledd's child list, so it is a single-sibling-set
# problem exactly as the ledd and punktum cases are, and none of W-69c's
# cross-container machinery is needed. The ops carry W-66's OWN provenance tag
# for W-66b's reason: the apply-plane refuse-on-occupied branch keyed on it
# compares RESOLVED PATHS and is depth-agnostic, so reusing the tag generalizes
# it unchanged and keeps these legs visible to W-72's occupied-destination sweep
# and inside the conserved partition's existing skip kind. An item-depth firing
# is told from a ledd or punktum one by the receipt's own paths.
#
# WHAT IS GENUINELY NEW IS THE SENTENCE AND THE LABEL VOCABULARY, and that is
# why this is a separate production rather than W-66b one word further down.
# ``ledd``/``punktum`` POSTFIX their depth word to a Norwegian ordinal ("tredje
# punktum"); ``bokstav``/``nr.`` PREFIX it to a letter or an arabic numeral
# ("bokstav c", "nr. 2"). The two shapes cannot collide: every shipped
# sibling-set relabel and repeal grammar in this module anchors its tail on
# ``ledd`` or ``punktum`` (the section-level lanes on a ``§`` label), and a
# sentence ending "… bokstav d." or "… nr. 3." matches none of them.
# Disjointness is pinned as a test fact rather than left as this claim, and the
# block's POSITION in the walk — last, behind every shipped production and
# immediately ahead of the operative fallback — is the additivity proof: a lead
# only reaches here once every other family has declined it, so this production
# can convert nothing but leads carrying ``no_parse_unstructured_lead_unmatched``
# today.
#
# THE ADDRESS, and it is measured rather than assumed. A bokstav/nr node is an
# ``item`` in the IR (``_eli_kind_and_step`` maps BOTH depth words onto that one
# kind), and a corpus probe over the replayed trees of every censused base act
# that replays at all finds 1,529 ``item`` nodes, EVERY one of them below a
# ``subsection`` — 1,477 directly (``…/section/subsection/item``) and 52 nested
# one further (``…/subsection/item/item``, a bokstav under an nr.). ZERO hang
# anywhere else, and in particular none hangs straight off a section in a tree
# this replay can build. So the address arithmetic is W-66b's exactly: a
# section spelled or inherited, then a LEDD that must itself resolve, then the
# item label. The ledd is REQUIRED for that reason, and because the resolver's
# ``tree_ops.find`` is a first-match DFS at any depth — a shallow
# ``(section, item)`` address would silently pick whichever ledd's bokstav "b"
# it reached first.
#
# THE LEDD IS NEVER SPELLED IN THIS FAMILY, which is the one place the address
# discipline is tighter than W-66b's. The sized grammar's source side reduces to
# LABELS ALONE, so a lead that spells its own ledd ("Nåværende § 18-3 sjette ledd
# bokstav b blir ny bokstav c.") DECLINES here — it is a different, larger
# sentence shape and it was not in the sized population. It is therefore always
# the DOM-local antecedent that supplies the ledd, through
# ``_no_antecedent_ledd_label`` with its depth conjunct retargeted from
# ``punktum`` to this depth's own word. The conjunct's purpose is W-66b's: an
# antecedent that establishes a PAYLOAD must not donate an address. Measured, it
# changes NO element of the frozen withdrawal set (every antecedent that resolves
# a ledd here also names the item depth word), and for ``nr.`` it is admittedly
# weak — an ordinary Lovtidend law citation spells "nr. 12" — so the LEDD reader,
# not this conjunct, is the real gate. It is carried anyway for W-66's cycle-
# guard reason: today's corpus not exercising a rule is not a property of it.
#
# THE MEASURED POPULATION, re-derived UNTRUNCATED at the W-76 base pin
# (``2e667312f``) over 8,141 ``no_parse_unstructured_lead_unmatched`` refusals —
# the shipped adjudication detail clips ``source_excerpt`` at 240 chars, so a
# receipt-plane census cannot see this family whole:
#
#   bokstav  27 refusals / 23 distinct leads / 27 instruments / 17 base acts
#   nr.      36 refusals / 33 distinct leads / 28 instruments / 19 base acts
#
# Split by what this production does with them: 28 LOWER (18 bokstav, 10 nr.),
# minting 67 RENUMBER legs over 17 base acts; 22 refuse
# ``NO_PARSE_ITEM_SET_RELABEL_LEDD_UNRESOLVED``, every one
# ``antecedent_names_no_ledd``; 13 refuse
# ``NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED`` (W-66's kind, reused because
# it is the same helper failing the same way) — 9 ``antecedent_names_several_
# sections``, 3 ``antecedent_names_no_section``, 1 ``part_has_no_antecedent_
# lead``. Nothing declines at the grammar and nothing is cyclic.
#
# MINTED LEGS ARE NOT WRITES, and at this depth the gap is wide (item 81's
# standing caution, re-derived). Of the 67 legs, only EIGHT are picked up by any
# base law's replay at the sweep's ``as_of``, on five acts: six land and two
# refuse at apply under W-66's occupied-destination guard, because the companion
# item-depth REPEAL their antecedent announces ("§ 8-1 første ledd nr. 6
# oppheves.") has no production — the exact W-66b→W-66c relationship, one family
# out, and a correctly refused leg rather than a defect. NONE of the 17 written
# base acts is a scan candidate, so the projected AND realized divergence-row
# yield is zero and the scoreboard does not move.
#
# THE HOLE THIS PRODUCTION MAKES VISIBLE, recorded because it is the honest
# reading of the three laws whose text moves. A relabel is half of a two-part
# instruction: the antecedent announces a payload ("§ 6-2 første ledd ny bokstav
# c skal lyde: …") and the relabel makes room for it. When the payload lead spells
# no ``ny``, the shipped item-target reader lowers it to a REPLACE and
# ``_promote_no_replace_with_following_renumber_insert`` turns that into the
# INSERT the pair needs — five corpus ops are promoted that way and those sites
# come out exactly right. When it DOES spell ``ny``, the shipped reader's
# ``ledd bokstav`` adjacency breaks and NOTHING is minted, so the relabel vacates
# a label nothing refills and the statute is left with a gap. 146 refusals / 146
# leads / 113 instruments / 64 base acts carry that payload lead today; building
# it is the follow-up, and it is what closes the gap rather than any narrowing
# here. The relabel itself is verbatim what the instrument commands, no op
# destroys text, and the corpus content-removing-write census is unchanged.
#
# WHAT IS DELIBERATELY LEFT REFUSED, each limb sized:
#   * A SPELLED LEDD, as above. 58 refusals sit in the qualifier-headed
#     neighbourhood this grammar declines, and they break down as: 26 spell their
#     own ledd (24 leads, 14 bases; 17 ``bokstav``, 9 ``nr.``), 12 reach a
#     punktum/avsnitt BELOW the item, 8 mark newness inside a list or drop the
#     depth word off the destination, 7 run on past the relabel or carry a
#     payload tail, 1 is ``blir til``, 1 spells its numeral out, 1 uses a
#     relocation verb, 2 are otherwise out of shape. The 26 are the natural next
#     widening; the rest are other families.
#   * Letters OUTSIDE ``a``–``z``. ``æ``/``ø``/``å`` never appear as a corpus
#     bokstav label, and their position relative to ``z`` in Lovdata's lettering
#     is unproven, so a range that crossed it would be expanded on a guess. They
#     decline; the refusal costs nothing measured.
#   * NEWNESS INSIDE A LIST ("blir bokstav k og ny bokstav l"). The newness
#     marker is admitted ONCE, in front of the destination's depth word, exactly
#     where the sized shape puts it; inside a list it declines, because a list
#     whose members are individually marked is announcing an insertion this
#     production does not model.
#   * ``siste bokstav`` and every other counted address. The label vocabulary is
#     explicit expansion — a range is enumerated, never trusted to a count — so
#     an address that names a position rather than a label declines.
#   * A relabel that crosses sibling sets. It cannot be spelled at all: both
#     sides of the pivot are anchored to labels of ONE depth word, so a
#     destination that respells a ledd or a section has nowhere to go. That is
#     W-69's territory by construction rather than by a check.
#
#: The letters a bokstav label may take, in the order a ``til`` range is expanded
#: over. Deliberately ASCII — ``æ``/``ø``/``å`` decline; see the block comment.
_NO_ITEM_RELABEL_LETTER_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
#: Per depth: (the depth WORD as the sentence spells it, the LABEL-LIST shape).
#: The separators are spelled with their surrounding whitespace REQUIRED, which
#: is not cosmetic — an unspaced ``og`` alternative lets a bare letter class read
#: "dog" as the two labels ``d`` and ``e``'s separator plus a stray, and every
#: corpus separator is spaced.
_NO_SET_RELABEL_ITEM_SEPARATOR = r"(?:\s*,\s*|\s+og\s+|\s+til\s+)"
_NO_SET_RELABEL_ITEM_DEPTHS: dict[str, tuple[str, str]] = {
    "bokstav": (
        r"bokstav(?:ene|ane)?",
        r"[a-z](?:" + _NO_SET_RELABEL_ITEM_SEPARATOR + r"[a-z])*",
    ),
    "nr": (
        r"nr\.?",
        r"[0-9]+(?:" + _NO_SET_RELABEL_ITEM_SEPARATOR + r"(?:nr\.?\s*)?[0-9]+)*",
    ),
}
#: The head is the SHARED ``_NO_SET_RELABEL_QUALIFIED_SECTION_HEAD``, which is
#: W-66's two explicit branches: two optional groups would make the currency
#: qualifier optional by accident, and that single character of slack admits
#: ordinary drafting prose.
_NO_SET_RELABEL_ITEM_PATTERNS: dict[str, str] = {
    depth: (
        _NO_SET_RELABEL_QUALIFIED_SECTION_HEAD
        + word + r"\s+(?P<source>" + labels + r")\s+blir\s+"
        r"(?:ny(?:tt|e)?\s+)?" + word + r"\s+(?P<destination>" + labels + r")\.?$"
    )
    for depth, (word, labels) in _NO_SET_RELABEL_ITEM_DEPTHS.items()
}
#: What the DOM-local antecedent must mention for it to donate a ledd at this
#: depth. See the block comment: for ``nr.`` this is a weak test by nature.
_NO_ITEM_RELABEL_ANTECEDENT_MARKERS: dict[str, tuple[str, ...]] = {
    "bokstav": ("bokstav",),
    "nr": ("nr.", "nr ", "nummer"),
}


def _no_strip_item_relabel_repeated_depth(token: str) -> str:
    """Strip a repeated depth word off a label-list member.

    ``"nr. 8 til nr. 10"`` spells its depth word twice, and the second one is a
    restatement rather than an address step. Stripped in code rather than
    swallowed by a regex group so the label vocabulary below sees a bare label.
    """
    stripped = token.strip()
    folded = stripped.casefold()
    for marker in ("nr. ", "nr.", "nr ", "nummer "):
        if folded.startswith(marker):
            return stripped[len(marker) :].strip()
    return stripped


def _no_item_relabel_label_index(depth: str, token: str) -> Optional[int]:
    """One label token → its 1-based INDEX inside its sibling ordering.

    Indexes rather than labels because ``_no_ordered_set_relabel_pairs`` — W-66's
    topological sort, reused verbatim — is the ONE ordering implementation in
    this module and it orders integers. ``None`` is "this production cannot name
    that label", and the whole lead is then refused.
    """
    token = token.strip().casefold()
    if depth == "nr":
        return int(token) if token.isdigit() else None
    if len(token) != 1:
        return None
    position = _NO_ITEM_RELABEL_LETTER_ALPHABET.find(token)
    return position + 1 if position >= 0 else None


def _no_item_relabel_label(depth: str, index: int) -> str:
    """The inverse of :func:`_no_item_relabel_label_index`, for the emitted path."""
    if depth == "nr":
        return str(index)
    return _NO_ITEM_RELABEL_LETTER_ALPHABET[index - 1]


def _no_item_relabel_indexes(depth: str, phrase: str) -> Optional[list[int]]:
    """``"b til e"`` → ``[2, 3, 4, 5]``; ``"nr. 3, 4 og 5"`` → ``[3, 4, 5]``.

    A range is EXPANDED, never counted on trust, and a member this vocabulary
    cannot name returns ``None`` so the whole lead is refused — the all-or-
    nothing rule ``_no_ledd_shift_ordinals`` states at the other depths.
    """
    indexes: list[int] = []
    # lawvm-regex: owning_parser this IS the item-relabel label-list splitter, and every member it yields is validated by the vocabulary below
    for chunk in re.split(r"\s*,\s*|\s+og\s+", _normalize_space(phrase)):
        chunk = _no_strip_item_relabel_repeated_depth(chunk)
        if not chunk:
            return None
        low, separator, high = chunk.partition(" til ")
        first = _no_item_relabel_label_index(depth, _no_strip_item_relabel_repeated_depth(low))
        if first is None:
            return None
        if not separator:
            indexes.append(first)
            continue
        last = _no_item_relabel_label_index(depth, _no_strip_item_relabel_repeated_depth(high))
        if last is None or last < first:
            return None
        indexes.extend(range(first, last + 1))
    return indexes


def _no_item_set_relabel_pairs(lead: str) -> Optional[tuple[str, str, list[tuple[int, int]]]]:
    """``Nåværende bokstav c blir ny bokstav d.`` → pairs.

    Returns ``(section_label, depth, [(src_index, dst_index), …])``.
    ``section_label`` is ``""`` when the sentence does not spell one (the caller
    then inherits it from the DOM-local antecedent), and the whole result is
    ``None`` when this grammar declines the sentence.

    ``depth`` is ``"bokstav"`` or ``"nr"``. It names WHICH pattern matched, so
    the two-depth dispatch is a test's fact rather than a comment's claim, and it
    selects both the label vocabulary and the antecedent's depth conjunct. The
    two patterns are mutually exclusive by their depth words, so the iteration
    order over them is immaterial — pinned as a test fact.
    """
    normalized = _normalize_space(lead)
    for depth, pattern in _NO_SET_RELABEL_ITEM_PATTERNS.items():
        # Inline ``re.match`` rather than a compiled classifier constant, for the
        # reason the sibling productions above record: the adjacent label spans
        # cannot pass ``compile_classifier_regex``'s backtracking lint.
        # lawvm-regex: owning_parser this IS the item-depth sibling-set relabel sentence parser
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match is None:
            continue
        sources = _no_item_relabel_indexes(depth, match.group("source"))
        destinations = _no_item_relabel_indexes(depth, match.group("destination"))
        if sources is None or destinations is None or len(sources) != len(destinations):
            return None
        if len(set(sources)) != len(sources) or len(set(destinations)) != len(destinations):
            return None
        if any(src == dst for src, dst in zip(sources, destinations, strict=True)):
            return None
        section = match.group("qualifier_first_section") or match.group("section_first_section")
        return (
            _normalize_no_section_label(section) if section else "",
            depth,
            list(zip(sources, destinations, strict=True)),
        )
    return None


# ── W-77: the item-depth PAYLOAD production ───────────────────────────────────
#
# WHAT THIS CLOSES. A relabel at this depth is HALF of a two-part instruction.
# W-76 lowers the half that makes room ("Nåværende bokstav c blir ny bokstav d.");
# the other half is the announcement that fills the vacated label
# ("§ 6-2 første ledd ny bokstav c skal lyde: …") and nothing lowers it today.
# The shipped item-target reader
# (``_infer_same_base_item_target_specs_from_lead``) requires ``ledd bokstav``
# ADJACENCY, which the ``ny`` marker breaks, so the payload half is never minted
# and W-76's relabel vacates a label nothing refills. This production mints that
# INSERT.
#
# WHY A SIBLING PRODUCTION RATHER THAN A WIDENING OF THE SHIPPED READER. The
# shipped reader is a pure ``lead -> specs`` function: it has no access to the
# DOM, so it cannot inherit a section or a ledd from an antecedent, and this
# family needs both (8 of the 225 refusals spell no section, 77 spell no ledd).
# It also reads the node's FULL text, payload included, which this family cannot
# afford — see the next paragraph. Widening it would therefore mean either
# threading the walk's node list through a reader that four other call sites
# share, or accepting a shallower address. Both are worse than a block that sits
# where W-76's sits and reads what W-76 reads.
#
# THE ANNOUNCEMENT IS READ OFF THE LEAD NODE'S OWN TEXT, not off the walk's
# ``lead``. Lovdata carries this family's payload INSIDE the announcing node, as
# a ``<ul>`` sibling of the sentence's text: 178 of the 225 refusals are shaped
#
#     <article class="defaultP">§ 6-2 første ledd ny bokstav c skal lyde:
#       <ul class="defaultList"><li data-name="c)">…the new item's text…</li></ul>
#     </article>
#
# so the walk's ``lead`` (the node's full ``itertext``) is announcement AND
# payload concatenated. A grammar reading that string would have to end in an
# unbounded tail, and an unbounded tail cannot tell a payload from a run-on
# second instruction. ``_node_text_without_structural_children`` excludes
# ``ul``/``li``/``article``, so the announcement can be anchored END TO END —
# which is the W-75 discipline stated positively: the node must declare its own
# operative payload, and here it does, in its own text. The remaining 47
# refusals carry the payload in following siblings and their own text is the
# announcement already, so ONE anchored grammar reads both carriers.
#
# THE ADDRESS is W-76's, and the measurement it rests on is W-76's 1,529-node
# probe: every ``item`` in every replayed base tree hangs below a ``subsection``.
# So the address is a section (spelled, or inherited through
# ``_no_antecedent_section_label``), then a LEDD that must itself resolve
# (spelled, or inherited through ``_no_antecedent_ledd_label`` with its depth
# conjunct retargeted to this depth's word), then the item label. The ledd is
# REQUIRED for that reason and because ``tree_ops.find`` is a first-match DFS: a
# shallow ``(section, item)`` address would silently pick whichever ledd's
# bokstav "b" it reached first. UNLIKE W-76 the ledd IS usually spelled here
# (148 of 225), and where it is not the inheritance is nearly inert — measured,
# it supplies the ledd for exactly ONE lowered lead and the section for exactly
# one other. It is carried anyway, for W-66's cycle-guard reason.
#
# THE PAYLOAD EXTENT IS PROVED, never assumed, and the proof is what bounds a
# production that ADDS text at scale:
#
#   * A LIST CARRIER (inline ``<ul>``, or a following sibling that carries one)
#     must yield top-level items whose labels EQUAL the announced labels, IN
#     ORDER, one for one. ``_extract_items`` is used rather than
#     ``_extract_payload_candidates``: the latter FLATTENS nested items into the
#     candidate map, so a payload with sub-items ("ny bokstav q skal lyde: …
#     1. … 2. … 3. …") presents labels ``q, 1, 2, 3`` and no extent test on that
#     map can tell a nested payload from a mis-sized one. Top-level items keep
#     the nesting inside the payload where it belongs; measured, this is the
#     difference between refusing and lowering 3 corpus ops.
#   * A TEXT CARRIER (no list anywhere) is admitted only in the single-label
#     case, with EXACTLY ONE following payload node, and only when that node is
#     an ``article.legalP``. ``numberedLegalP`` declines: its text opens with its
#     own numerator ("(4) opplysninger om …", "3. Dersom skyldneren …"), which is
#     a second address claim this production would have to discard on trust. One
#     corpus refusal costs that; it is a sized follow-up, not a guess.
#   * Anything else — no payload at all, several payload nodes, a list whose
#     labels do not match — refuses with
#     ``NO_PARSE_ITEM_INSERT_PAYLOAD_EXTENT_UNPROVABLE``.
#
# MULTI-LABEL ANNOUNCEMENTS ARE HANDLED, and provably: 16 of the 225 announce
# several labels ("ny bokstav g og h skal lyde:", "nye nr. 15 til 19 skal
# lyde:"), and in every one the DOM carries one top-level ``<li>`` per announced
# label, in order, each with its own ``data-name``. The extent test above IS the
# W-32(a)/W-19 all-or-nothing rule at this depth: the labels match one for one or
# the whole lead refuses. A range is EXPANDED over the shared vocabulary, never
# counted on trust.
#
# THE OCCUPIED DESTINATION is the heart of this item, and this production does
# not take the shipped recovery. θ ``(INSERT, target_occupied)`` recovers by
# REPLACING the occupant — correct for the "ny § 4 a skal lyde" surface the
# table documents, and wrong here. An announcement that says "NY bokstav c" and
# finds bokstav c standing means one of: the relabel that should have vacated it
# did not fire, or the archived base edition already carries this amendment. In
# neither case is the occupant's in-force text the thing to delete. So the op
# carries ``NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG`` and the apply seam refuses
# it, exactly as W-66 refuses its own occupied relabel destinations — same
# polarity, same shape, and the shipped θ cell is untouched for every op that is
# not this production's, so the corpus-wide firing census cannot move.
#
# THE PAIR COMPOSES, and the ordering proof is the kernel's rather than this
# module's. ``no_ordering_profile`` sets ``renumber_vacate=True`` with
# ``renumber_group_key=_no_group_key`` = ``(effective, enacted, source_id)``, and
# ``_structural_vacate_order`` emits, WITHIN each group: REPEALs by sequence,
# then RENUMBERs topologically, then EVERY OTHER OP by sequence. An INSERT is in
# that third stage. The relabel and the payload announcement come from the same
# instrument and the same commencement, so they share a group, so the RENUMBER
# that vacates bokstav c is ordered before the INSERT that fills it — not by
# luck of ``sequence`` but by the stage split. Where the relabel does NOT fire,
# the slot is still occupied when the INSERT runs and the guard above refuses it.
#
# THE MEASURED POPULATION, re-derived UNTRUNCATED at the W-77 base pin
# (``e260e5930``) over 8,078 ``no_parse_unstructured_lead_unmatched`` refusals —
# the shipped adjudication detail clips ``source_excerpt`` at 240 chars, and in
# this family the clip is fatal, because the payload sits in the same string:
#
#   225 refusals / 225 distinct leads / 165 instruments / 96 base acts
#   (125 bokstav, 100 nr.; 148 spell their ledd, 217 spell their section,
#    16 announce several labels)
#
# Split by what this production does with them: 144 LOWER, minting 160 INSERT
# ops over 62 base acts and 112 instruments; 73 refuse
# ``NO_PARSE_ITEM_INSERT_PAYLOAD_LEDD_UNRESOLVED`` (29
# ``antecedent_is_not_item_depth``, 28 ``antecedent_names_no_ledd``, 15
# ``part_has_no_antecedent_lead``, 1 ``antecedent_names_several_ledd``); 7 refuse
# ``NO_PARSE_ITEM_INSERT_PAYLOAD_ADDRESS_UNRESOLVED``; 1 refuses
# ``NO_PARSE_ITEM_INSERT_PAYLOAD_EXTENT_UNPROVABLE`` (the ``numberedLegalP``
# carrier). Nothing is cyclic and nothing declines at the label vocabulary.
#
# WHAT IS DELIBERATELY LEFT REFUSED, each limb sized against the 99 refusals that
# mention ``ny`` next to an item depth word and ``lyde`` but decline here:
#   * A MIXED LIST that names existing labels AND a new one ("§ 78 bokstav h og
#     ny bokstav i skal lyde:", "§ 5 a annet ledd nr. 7 og ny nr. 8 skal lyde:").
#     55 refusals, and they are a DIFFERENT instruction: part REPLACE, part
#     INSERT, with the split carried by which member the ``ny`` sits in front of.
#     The shipped multi-item reader already models mixed lists at the adjacent
#     surface; widening it is its own item, not a limb of this one.
#   * A NESTED item address ("§ 2-30 første ledd bokstav g ny nr. 7 skal lyde:",
#     "§ 23-3 annet ledd nr. 1 ny bokstav d skal lyde:"). 21 refusals. The
#     address has a fourth step this grammar cannot spell, and the 1,529-node
#     probe attests only 52 such nodes corpus-wide — too thin a population to
#     write an address arithmetic against.
#   * A DEEPER or OTHER depth between the ledd and the item ("§ 59 a første ledd
#     første punktum nytt nr. 6 skal lyde:"). 10 refusals; punktum-depth
#     containers are W-66b/W-66c territory.
#   * A RUN-ON or a relabel with a payload tail ("§ 8-10 nr. 3 blir ny nr. 2. Ny
#     nr. 2 skal lyde:"). 8 refusals. The own-text anchor declines them by
#     construction, which is the point of anchoring end to end.
#   * Letters outside ``a``–``z``, and every counted address ("siste bokstav").
#     W-76's limbs verbatim, for W-76's reasons: the vocabulary is explicit
#     expansion, and ``æ``/``ø``/``å``'s position in Lovdata's lettering is
#     unproven. Zero corpus cost.
#
#: The LEDD ordinal alternation, DERIVED from ``_NORWEGIAN_ORDINALS`` rather than
#: spelled a second time, so the regex and the lookup that follows it cannot
#: disagree about which words are ordinals. Longest-first for determinism.
_NO_ITEM_INSERT_PAYLOAD_LEDD_ALTERNATION = "|".join(
    sorted(_NORWEGIAN_ORDINALS, key=lambda word: (-len(word), word))
)
#: Per depth: (the depth WORD as the announcement spells it, the LABEL-LIST
#: shape). The separators are W-76's ``_NO_SET_RELABEL_ITEM_SEPARATOR`` — the one
#: separator vocabulary at this depth — and the label classes are W-76's widened
#: by the LIST PUNCTUATION this family prints ("ny bokstav t) skal lyde:").
_NO_ITEM_INSERT_PAYLOAD_DEPTHS: dict[str, tuple[str, str]] = {
    "bokstav": (
        r"bokstav(?:ene|ane)?",
        r"[a-z]\)?(?:" + _NO_SET_RELABEL_ITEM_SEPARATOR + r"[a-z]\)?)*",
    ),
    "nr": (
        r"(?:nummer|nr\.?)",
        r"[0-9]+(?:" + _NO_SET_RELABEL_ITEM_SEPARATOR + r"(?:nr\.?\s*)?[0-9]+)*",
    ),
}
#: Anchored END TO END on the lead node's OWN text — see the block comment. The
#: section head is optional (inherited when absent) and so is the ledd; the
#: newness marker is admitted ONCE, immediately in front of the depth word, which
#: is what keeps a mixed list ("bokstav h og ny bokstav i") out.
_NO_ITEM_INSERT_PAYLOAD_PATTERNS: dict[str, str] = {
    depth: (
        r"^(?:§\s*(?P<section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+)?"
        r"(?:(?P<ledd>" + _NO_ITEM_INSERT_PAYLOAD_LEDD_ALTERNATION + r")\s+ledd\s+)?"
        r"ny(?:tt|e)?\s+" + word + r"\s+(?P<labels>" + labels + r")\s+skal\s+lyde\s*:?$"
    )
    for depth, (word, labels) in _NO_ITEM_INSERT_PAYLOAD_DEPTHS.items()
}


def _no_item_insert_payload_indexes(depth: str, phrase: str) -> Optional[list[int]]:
    """``"g og h"`` → ``[7, 8]``; ``"nr. 15 til 19"`` → ``[15, …, 19]``.

    W-76's ``_no_item_relabel_indexes`` with ONE pre-step: this family spells its
    labels with the list punctuation Lovdata prints them with ("bokstav t)",
    "bokstav e) og f)"), which the relabel family never does. The punctuation is
    stripped per token BEFORE the shared vocabulary sees it, so there is exactly
    one label vocabulary at this depth rather than two that could drift apart.
    """
    # lawvm-regex: owning_parser this IS the item-insert label-list punctuation stripper; every token it yields is validated by W-76's shared vocabulary
    stripped = re.sub(r"([0-9A-Za-z])\)", r"\1", _normalize_space(phrase))
    indexes = _no_item_relabel_indexes(depth, stripped)
    if indexes is None or len(set(indexes)) != len(indexes):
        return None
    return indexes


def _no_item_insert_payload_target(own_text: str) -> Optional[tuple[str, str, str, list[str]]]:
    """``§ 6-2 første ledd ny bokstav c skal lyde:`` → the address and labels.

    Returns ``(section_label, ledd_label, depth, [item_label, …])``.
    ``section_label`` and ``ledd_label`` are ``""`` when the sentence spells
    neither (the caller then inherits them from the DOM-local antecedent), and
    the whole result is ``None`` when this grammar declines the sentence.

    ``own_text`` is the announcing node's text WITHOUT its structural children —
    see the block comment: the payload is a ``<ul>`` inside that same node, and
    excluding it is what lets the sentence be anchored end to end.

    ``depth`` is ``"bokstav"`` or ``"nr"``; it names WHICH pattern matched, so
    the two-depth dispatch is a test's fact rather than a comment's claim, and it
    selects both the label vocabulary and the antecedent's depth conjunct. The
    two patterns are mutually exclusive by their depth words, so the iteration
    order over them is immaterial — pinned as a test fact.
    """
    normalized = _normalize_space(own_text)
    for depth, pattern in _NO_ITEM_INSERT_PAYLOAD_PATTERNS.items():
        # Inline ``re.match`` rather than a compiled classifier constant, for the
        # reason every sibling production above records: the adjacent label spans
        # cannot pass ``compile_classifier_regex``'s backtracking lint.
        # lawvm-regex: owning_parser this IS the item-depth newness-payload announcement parser
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match is None:
            continue
        indexes = _no_item_insert_payload_indexes(depth, match.group("labels"))
        if indexes is None:
            return None
        section = match.group("section")
        ledd_word = match.group("ledd")
        return (
            _normalize_no_section_label(section) if section else "",
            _NORWEGIAN_ORDINALS[_normalize_space(ledd_word).casefold()] if ledd_word else "",
            depth,
            [_no_item_relabel_label(depth, index) for index in indexes],
        )
    return None


def _no_item_insert_payloads(
    lead_node: etree._Element,
    payload_nodes: Sequence[etree._Element],
    labels: Sequence[str],
) -> Optional[list[IRNode]]:
    """The item payloads an item-depth newness announcement introduces.

    ``None`` means the extent is UNPROVABLE and the whole lead must refuse — the
    all-or-nothing rule, because a lead that declares several labels is one
    indivisible instruction and a payload that does not split to match it is no
    evidence for which label the halves belong to.

    Two carriers, in this order and no others; see the block comment for why the
    list test runs on ``_extract_items`` rather than on the flattened candidate
    map, and why ``numberedLegalP`` is not admitted here.
    """
    items = _extract_items(lead_node)
    if not items:
        items = [item for node in payload_nodes for item in _extract_items(node)]
    if items:
        if [(item.label or "").casefold() for item in items] != [label.casefold() for label in labels]:
            return None
        return [_with_no_node_label(item, label) for item, label in zip(items, labels, strict=True)]
    if len(labels) != 1 or len(payload_nodes) != 1:
        return None
    node = payload_nodes[0]
    if _local_name(node) != "article" or "legalP" not in _classes(node):
        return None
    text = _node_text_without_structural_children(node)
    if not text:
        return None
    return [IRNode(kind=IRNodeKind.ITEM, label=labels[0], text=text)]


# ── W-70b: the ``data-move-part`` that names the WRONG destination SECTION ─────
#
# THE DEFECT, read off the ``article.change`` node the parser reads.
# ``no/lovtid/2025-06-20-42`` amends ``no/lov/2009-06-19-44`` with two move
# attributes. Its §2 block is a clean +1 vacate chain
# (``3→4, 4→5, 5→6, 6→7``). Its §3 block reads
#
#     §3/ledd/2 ;; §2/ledd/3      §3/ledd/3 ;; §2/ledd/4
#
# — it sends §3's ledd INTO §2 — while the announcement it annotates says
# "Noverande § 3 andre og tredje ledd blir tredje og nytt fjerde ledd.", an
# intra-§3 shift, under a §3 block whose sibling op inserts a new §3 andre ledd.
# The ATTRIBUTE names the wrong destination section; the prose is the authority.
#
# WHAT THE DEFECT COST, before this production. ``§2/ledd/3 → §2/ledd/4`` (the
# §2 chain's own leg) and ``§3/ledd/3 → §2/ledd/4`` (the mis-addressed leg) claim
# ONE destination, so W-69c's provability guard correctly refuses the whole
# six-leg component. Nothing is vacated, and the instrument's two "skal lyde"
# INSERTs then land on live slots, where the shipped ``(INSERT, occupied)`` cell
# recovers by REPLACING the occupant: base § 2 tredje ledd ("Enkeltpersonar kan
# vende seg direkte …") and base § 3 andre ledd ("Kommunen skal sørgje for å ta
# vare på barn …") were overwritten instead of shifted down. Repairing the
# attribute makes the component provable, the relocation lands, and both
# provisions are recovered.
#
# THE POPULATION, censused BEFORE this production was written and pinned by
# content in ``tests/test_no_renumber_migration.py``. Of the corpus's 286
# ``data-move-part`` attributes / 504 legs, 35 attributes carry at least one leg
# whose RESOLVED destination section differs from that same leg's resolved source
# section — 54 such legs. They split cleanly by leg SHAPE, and the split is why
# this production can be narrow:
#
#   * 51 legs over 33 attributes are ``section -> section``: ordinary section
#     renumbering ("Nåværende §§ 4 til 7 blir § 5 til ny § 8."). The destination
#     section differing IS the instruction. Untouched.
#   * 1 leg is ``sentence -> section`` (``no/lovtid/2024-04-12-14``:
#     ``§3/ledd/1/setning/2 ;; §4``, "Nåværende § 3 første ledd andre punktum
#     blir ny § 4."). A genuine promotion out of its container, commanded by the
#     prose. Untouched.
#   * 2 legs over 1 attribute are ``subsection -> subsection`` — and they are the
#     defect above. This production's entire reach.
#
# THE PROOF, and it is a CONJUNCTION every limb of which must hold. Nothing is
# repaired on a resemblance:
#
#   1. Every leg reads ``<prefix>/ledd/<n>`` on BOTH sides — the only shape whose
#      destination section is separable from the rest of the address.
#   2. One shared source prefix, one shared destination prefix, and they DIFFER
#      (otherwise there is no defect to repair and the value passes through).
#   3. Both prefixes resolve, both are SECTION addresses, and both name the
#      block's own base act. A cross-base value is declined before anything else,
#      on W-70's precedent: the archive mis-attributes some endringsdeler, and a
#      "repair" there would relabel a law the instrument never addressed.
#   4. The block's OWN announcement parses as a ledd-set relabel that SPELLS its
#      section (``_no_ledd_set_relabel_pairs``, W-56's shipped grammar first and
#      W-66's widened sibling after — no new sentence grammar is minted here).
#   5. The section the prose spells is the SOURCE section. The prose is talking
#      about the block's own provisions, which is what makes it authority over
#      where they go.
#   6. The prose's shift map EQUALS the markup's ledd map, pair for pair. The
#      prose is allowed to correct the SECTION and nothing else; a prose that
#      disagreed about which ledd moves where would be a different (larger)
#      instruction and is refused.
#   7. NO OTHER SECTION is named ANYWHERE in the announcement. A single stray
#      ``jf. § 4`` is enough to decline, because then the sentence is no longer
#      unambiguously about one section.
#
# WHAT IS REWRITTEN: the destination's SECTION component, to the source's. The
# ledd ordinals on both sides, the base act, and every other path step are
# carried through untouched — the repaired value is rebuilt as
# ``<source prefix>/ledd/<declared destination ordinal>``, so this production is
# structurally incapable of moving a leg to a different ledd than the markup
# declared.
#
# POLARITY. Under-application is safe and over-application is not. An attribute
# whose prose cannot prove the repair keeps its declared destination and, if it
# contests a slot, keeps refusing under W-69c's guard — which is the correct
# standing state for an instruction the system cannot read. The 34 members this
# production leaves alone are pinned byte-identical through the lowering, and the
# whole 35-member population is pinned by content, so a corpus refresh that grows
# the family FAILS the tripwire and the new member gets its own prose
# adjudication before any repair can fire on it.
_NO_MOVE_ATTR_DESTINATION_SECTION_RULE = "prose_names_source_section_only"
_NO_MOVE_ATTR_DESTINATION_DECLINED_NOT_LEDD_LEGS = "declined:legs_not_ledd_addressed"
_NO_MOVE_ATTR_DESTINATION_DECLINED_SECTION_AGREES = "declined:destination_section_agrees"
_NO_MOVE_ATTR_DESTINATION_DECLINED_PREFIX_NOT_SECTION = "declined:prefix_not_a_section_address"
_NO_MOVE_ATTR_DESTINATION_DECLINED_CROSS_BASE = "declined:cross_base_prefix"
_NO_MOVE_ATTR_DESTINATION_DECLINED_NO_PROSE = "declined:announcement_not_a_ledd_set_relabel"
_NO_MOVE_ATTR_DESTINATION_DECLINED_PROSE_SECTION = "declined:announcement_section_is_not_the_source"
_NO_MOVE_ATTR_DESTINATION_DECLINED_PROSE_MAP = "declined:announcement_shift_map_disagrees"
_NO_MOVE_ATTR_DESTINATION_DECLINED_OTHER_SECTION = "declined:announcement_names_another_section"


@dataclass(frozen=True)
class _NOMoveAttrDestinationSectionNormalization:
    """The verdict on one ``data-move-part``'s destination SECTION.

    ``legs`` is ``None`` when nothing was rewritten and ``reason`` then names why
    (a ``declined:`` string); otherwise ``reason`` is the rule that fired and
    ``pattern`` names which sentence grammar proved it. Both are reported on the
    receipt, so which limb of the conjunction declined is a test's fact rather
    than a comment's claim.
    """

    legs: Optional[Tuple[Tuple[str, str], ...]]
    reason: str
    pattern: str = ""
    source_section: str = ""
    destination_section: str = ""


def _no_split_ledd_leg(path: str) -> Optional[tuple[str, int]]:
    """``"lov/X/§3/ledd/2"`` → ``("lov/X/§3", 2)``; anything else → ``None``.

    Deliberately a suffix test rather than a regex: the ordinal must be the LAST
    step, so a ``…/ledd/2/setning/3`` address (whose destination section is not
    separable from a deeper container) cannot enter this production.
    """
    prefix, separator, ordinal = path.rpartition(_NO_LEDD_PATH_STEP)
    if not separator or not prefix or not ordinal.isdigit():
        return None
    return prefix, int(ordinal)


def _no_normalize_move_attr_destination_section(
    legs: Sequence[tuple[str, str]],
    *,
    announcement: str,
    base_id: str,
) -> _NOMoveAttrDestinationSectionNormalization:
    """Repair a ``data-move-part`` whose destination names the wrong SECTION.

    Returns rewritten legs only when the block's own announcement PROVES the
    shift is intra-section — the seven-limb conjunction in the block comment
    above. Order-insensitive: each leg's destination is rebuilt from its own
    declared ordinal, so the caller may pass the legs in markup or reversed order
    and get the same answer in the same order.
    """
    if not base_id or not legs:
        return _NOMoveAttrDestinationSectionNormalization(
            None, _NO_MOVE_ATTR_DESTINATION_DECLINED_NOT_LEDD_LEGS
        )
    split: list[tuple[str, int, str, int]] = []
    for source, destination in legs:
        source_parts = _no_split_ledd_leg(source)
        destination_parts = _no_split_ledd_leg(destination)
        if source_parts is None or destination_parts is None:
            return _NOMoveAttrDestinationSectionNormalization(
                None, _NO_MOVE_ATTR_DESTINATION_DECLINED_NOT_LEDD_LEGS
            )
        split.append((source_parts[0], source_parts[1], destination_parts[0], destination_parts[1]))
    source_prefixes = {prefix for prefix, _n, _dp, _dn in split}
    destination_prefixes = {prefix for _sp, _n, prefix, _dn in split}
    if len(source_prefixes) != 1 or len(destination_prefixes) != 1:
        return _NOMoveAttrDestinationSectionNormalization(
            None, _NO_MOVE_ATTR_DESTINATION_DECLINED_NOT_LEDD_LEGS
        )
    source_prefix = next(iter(source_prefixes))
    destination_prefix = next(iter(destination_prefixes))
    if source_prefix == destination_prefix:
        return _NOMoveAttrDestinationSectionNormalization(
            None, _NO_MOVE_ATTR_DESTINATION_DECLINED_SECTION_AGREES
        )
    if (
        normalize_lovdata_refid(source_prefix) != base_id
        or normalize_lovdata_refid(destination_prefix) != base_id
    ):
        return _NOMoveAttrDestinationSectionNormalization(
            None, _NO_MOVE_ATTR_DESTINATION_DECLINED_CROSS_BASE
        )
    source_address = lovdata_path_to_address(source_prefix)
    destination_address = lovdata_path_to_address(destination_prefix)
    if (
        source_address is None
        or destination_address is None
        or source_address.leaf_kind() != "section"
        or destination_address.leaf_kind() != "section"
    ):
        return _NOMoveAttrDestinationSectionNormalization(
            None, _NO_MOVE_ATTR_DESTINATION_DECLINED_PREFIX_NOT_SECTION
        )
    source_section = source_address.path[-1][1]
    destination_section = destination_address.path[-1][1]
    prose = _no_ledd_set_relabel_pairs(announcement)
    if prose is None or not prose[0]:
        return _NOMoveAttrDestinationSectionNormalization(
            None,
            _NO_MOVE_ATTR_DESTINATION_DECLINED_NO_PROSE,
            source_section=source_section,
            destination_section=destination_section,
        )
    prose_section, prose_pairs, pattern = prose
    if prose_section != _normalize_no_section_label(source_section):
        return _NOMoveAttrDestinationSectionNormalization(
            None,
            _NO_MOVE_ATTR_DESTINATION_DECLINED_PROSE_SECTION,
            pattern=pattern,
            source_section=source_section,
            destination_section=destination_section,
        )
    if sorted(prose_pairs) != sorted((n, dn) for _sp, n, _dp, dn in split):
        return _NOMoveAttrDestinationSectionNormalization(
            None,
            _NO_MOVE_ATTR_DESTINATION_DECLINED_PROSE_MAP,
            pattern=pattern,
            source_section=source_section,
            destination_section=destination_section,
        )
    # Limb 7. Every ``§`` the announcement spells must be the one section this
    # sentence is about; one stray cross-reference and the sentence stops being
    # unambiguous evidence about where these ledd go.
    named: set[str] = set()
    # Reused verbatim rather than as a second, drifting copy of the same reader.
    # lawvm-regex: owning_parser this IS the shipped section-address reader for a node's own text
    for match in _NO_ANTECEDENT_SECTION_RE.finditer(announcement):
        named.add(_normalize_no_section_label(match.group(1)))
    if named != {prose_section}:
        return _NOMoveAttrDestinationSectionNormalization(
            None,
            _NO_MOVE_ATTR_DESTINATION_DECLINED_OTHER_SECTION,
            pattern=pattern,
            source_section=source_section,
            destination_section=destination_section,
        )
    return _NOMoveAttrDestinationSectionNormalization(
        tuple(
            (f"{prefix}{_NO_LEDD_PATH_STEP}{n}", f"{prefix}{_NO_LEDD_PATH_STEP}{dn}")
            for prefix, n, _dp, dn in split
        ),
        _NO_MOVE_ATTR_DESTINATION_SECTION_RULE,
        pattern=pattern,
        source_section=source_section,
        destination_section=destination_section,
    )


def _no_ordered_set_relabel_pairs(
    pairs: Sequence[tuple[int, int]],
) -> Optional[list[tuple[int, int]]]:
    """Order a sibling-set relabel so no leg ever writes onto a live sibling.

    A leg ``(s, d)`` may only run once every leg whose SOURCE is ``d`` has run —
    otherwise ``d``'s occupant is still standing when ``s`` lands on it. That is a
    dependency DAG, and its topological order is the atomic group's proven-safe
    internal order. ``None`` means the dependency graph has a CYCLE (``3→4`` with
    ``4→3``: a swap, which no sequential relabel can express without a scratch
    slot), and the caller must refuse the whole lead.

    Legs with no dependency between them keep their source order, so the emitted
    stream is deterministic.
    """
    by_source: dict[int, int] = {}
    for index, (src, _dst) in enumerate(pairs):
        by_source[src] = index
    ordered: list[int] = []
    state: dict[int, int] = {}  # 0 = in progress, 1 = done

    def visit(index: int) -> bool:
        mark = state.get(index)
        if mark == 1:
            return True
        if mark == 0:
            return False
        state[index] = 0
        blocker = by_source.get(pairs[index][1])
        if blocker is not None and not visit(blocker):
            return False
        state[index] = 1
        ordered.append(index)
        return True

    for index in range(len(pairs)):
        if not visit(index):
            return None
    return [tuple(pairs[index]) for index in ordered]  # type: ignore[misc]


def _no_antecedent_section_label(
    children: Sequence[etree._Element],
    part_indexes: Sequence[int],
    position: int,
) -> tuple[Optional[str], str]:
    """The section address a shift lead with no ``§`` of its own inherits.

    Returns ``(label, reason)``; ``label`` is ``None`` and ``reason`` says why
    when nothing unambiguous is available.

    THE RULE, and it is deliberately DOM-local rather than carried state: the
    antecedent is the nearest preceding ``article.defaultP`` IN THE SAME PART, and
    it must name exactly one distinct section. ``defaultP`` is Lovdata's
    instruction-lead class; the payload classes (``legalP``, ``numberedLegalP``,
    ``futureLegalArticle``) are excluded, which matters — in
    ``no/lovtid/2017-06-16-67`` the node physically preceding the shift is the
    payload of the lead before it and names a foreign "§ 9", so a
    nearest-any-node rule would inherit the wrong section.

    Being DOM-local rather than a carried "last section seen in this part" is
    what makes the rule SELF-GUARDING across law switches. A part that changes
    base act does so with a lead of its own ("6. I lov 19. juni 2015 nr. 70 …
    gjøres følgende endringer:"), that lead is a ``defaultP`` naming no section,
    and a shift immediately after it therefore inherits NOTHING and refuses —
    instead of silently carrying the previous law's section across the boundary.
    A switch lead that DOES name a section ("5. I lov 13. februar 2015 nr. 9 …
    skal § 3 femte ledd lyde:") is the case where inheriting is right, and the
    walk has already rebound ``lead_base_id`` to the new act by then.

    Measured: 392 of the 642 accepted lead occurrences take this route, and the
    refusals here are 40 receipt triples over 37 distinct leads — 20
    ``antecedent_names_no_section``, 13 ``part_has_no_antecedent_lead``, 7
    ``antecedent_is_meta_amendment``.
    """
    index = position - 1
    part = part_indexes[position] if position < len(part_indexes) else None
    while index >= 0 and (part_indexes[index] if index < len(part_indexes) else None) == part:
        node = children[index]
        if _local_name(node) == "article" and "defaultP" in _classes(node):
            text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
            # lawvm-regex: owning_parser this IS the sibling-set relabel's antecedent reader, on the antecedent node's own text
            if _NO_META_AMENDMENT_ANTECEDENT_RE.search(text) is not None:
                return None, "antecedent_is_meta_amendment"
            # lawvm-regex: owning_parser the same antecedent reader's address scan; the single-distinct-label conjunct below validates every match
            raw_labels = _NO_ANTECEDENT_SECTION_RE.findall(text)
            labels = {_normalize_no_section_label(raw) for raw in raw_labels}
            if len(labels) == 1:
                return labels.pop(), "antecedent_names_section"
            if len(labels) > 1:
                return None, "antecedent_names_several_sections"
            return None, "antecedent_names_no_section"
        index -= 1
    return None, "part_has_no_antecedent_lead"


#: The LEDD an antecedent names, in the antecedent's own text. Deliberately the
#: same ordinal vocabulary as everything else in this module, spelled as an
#: alternation because this reader SCANS for the phrase rather than parsing a
#: sentence into it.
_NO_ANTECEDENT_LEDD_RE = compile_classifier_regex(
    r"\b(første|fyrste|andre|annet|tredje|fjerde|femte|sjette|sjuende|syvende|åttende|niende|tiende)"
    r"\s+ledd\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.antecedent_ledd_address",
)


def _no_antecedent_ledd_label(
    children: Sequence[etree._Element],
    part_indexes: Sequence[int],
    position: int,
    *,
    depth_name: str = "punktum",
    depth_markers: tuple[str, ...] = ("punktum",),
) -> tuple[Optional[str], str]:
    """The ledd address a punktum relabel with no ledd of its own inherits.

    Returns ``(label, reason)``; ``label`` is ``None`` and ``reason`` says why
    when nothing unambiguous is available.

    THE RULE is W-66's ``_no_antecedent_section_label`` at one more level, and it
    reads THE SAME antecedent node — the nearest preceding ``article.defaultP``
    in the same part. That the two levels come from ONE node is the reason the
    pair is coherent: "§ 3-4 fjerde ledd nytt annet punktum skal lyde:" followed
    by "Nåværende annet punktum blir nytt tredje punktum." is one instruction in
    two sentences, and reading the section from one antecedent and the ledd from
    another could silently compose an address neither sentence names.

    THE EXTRA CONJUNCT, which W-66 has no need of: the antecedent must ITSELF be
    a punktum-depth instruction. An antecedent that names a ledd while talking
    about whole ledds ("§ 13 nytt tredje ledd skal lyde:") establishes that ledd
    as a PAYLOAD, not as a container whose sentences are being renumbered — its
    text is given in full, so it has no "nåværende" punktums for a follower to
    relabel, and inheriting from it would relabel sentences of a provision that
    was just written. Measured: the conjunct changes NO element of the frozen
    withdrawal set — every lead it would refuse already declines at the grammar
    for an independent reason. It is carried for W-66's cycle-guard reason: the
    absence of that pairing in today's corpus is not a property of the rule, and
    the rule is what a corpus refresh will be read against.

    Measured over the 165 punktum refusals at the base pin: 128 antecedents name
    exactly one ledd, 32 name none, and 5 parts have no antecedent lead at all;
    after the grammar has declined the 16 it declines, the surviving refusals
    here are 27, every one ``antecedent_names_no_ledd``.

    W-76 RETARGETS the extra conjunct rather than copying the reader. Everything
    above — the DOM-local rule, the meta-amendment guard, the single-distinct-
    label requirement, the ordinal vocabulary — is depth-independent; only the
    word that says "this antecedent is talking at MY depth" is not. ``depth_name``
    and ``depth_markers`` default to W-66b's ``punktum``, so every shipped call
    site is byte-identical, and the item-depth caller passes its own word. The
    reason string is built from ``depth_name`` for the same purpose it always
    served: a census must be able to tell WHICH depth's conjunct declined.
    """
    index = position - 1
    part = part_indexes[position] if position < len(part_indexes) else None
    while index >= 0 and (part_indexes[index] if index < len(part_indexes) else None) == part:
        node = children[index]
        if _local_name(node) == "article" and "defaultP" in _classes(node):
            text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
            # lawvm-regex: owning_parser this IS the punktum relabel's antecedent reader, on the antecedent node's own text
            if _NO_META_AMENDMENT_ANTECEDENT_RE.search(text) is not None:
                return None, "antecedent_is_meta_amendment"
            if not any(marker in text.casefold() for marker in depth_markers):
                return None, f"antecedent_is_not_{depth_name}_depth"
            # lawvm-regex: owning_parser the same antecedent reader's ledd scan; the single-distinct-label conjunct below validates every match
            raw_labels = _NO_ANTECEDENT_LEDD_RE.findall(text)
            labels = {_NORWEGIAN_ORDINALS[raw.casefold()] for raw in raw_labels}
            if len(labels) == 1:
                return labels.pop(), "antecedent_names_ledd"
            if len(labels) > 1:
                return None, "antecedent_names_several_ledd"
            return None, "antecedent_names_no_ledd"
        index -= 1
    return None, "part_has_no_antecedent_lead"


def _no_unstructured_repeal_renumber_legs(
    lead: str,
) -> Optional[tuple[str, list[LegalAddress], list[LegalAddress], list[LegalAddress]]]:
    """Resolve a repeal-then-shift lead to ``(section, repealed, source, dest)``.

    ``None`` means "this production declines the lead" and the walk falls through
    to its ordinary refusal. Returning TARGETS rather than ordinals keeps the call
    site's arity receipt and op minting exactly as they were before W-61.

    Two attempts, in this order and for this reason:

    1. The shipped pattern, resolved exactly as it always was — including the case
       where ``_infer_same_base_subsection_targets_from_lead`` resolves NOTHING and
       the production returns empty target lists. That is a silent drop, and an
       honest receipt would be better, but it is the SHIPPED answer for 14 corpus
       leads and changing it is not this widening's business.
    2. Only if the shipped pattern does not match: W-61's widened pattern, whose
       ordinal phrases go through W-56's ``_no_ledd_shift_ordinals`` — the same
       ``_NORWEGIAN_ORDINALS`` vocabulary and the same all-or-nothing refusal, but
       it also spans ``til`` RANGES ("annet til femte"), which the ``skal lyde``
       round-trip resolves to no targets at all. Reusing that helper is what keeps
       this from becoming a second ordinal grammar.

    The widened attempt refuses, rather than guesses, two shapes it cannot own:
    an ordinal phrase outside the vocabulary — which is also what declines the one
    corpus lead whose repeal side is a MULTI-SECTION list ("§ 4 femte ledd, § 5
    annet ledd og § 6 annet ledd oppheves."), since the embedded "§ 5 annet ledd"
    is not an ordinal and so is never silently attributed to § 4 — and a shift
    sentence that repeats a section OTHER than the repealed one.
    """
    # Both patterns stay inline ``re.match`` rather than module-level
    # ``re.compile``: this is a scanned semantic-plane module (FW-07), and the
    # two adjacent ``(.+?)`` spans cannot pass the ``compile_classifier_regex``
    # wrap — the same reason W-32(c) records for the sibling production.
    #
    # The shipped pattern, UNCHANGED, character for character.
    shipped = re.match(
        r"^§\s*([0-9A-Za-z-]+)\s+(.+?)\s+ledd\s+oppheves\.\s*Nåværende\s+(.+?)\s+ledd\s+blir\s+(.+?)\s+ledd\.?$",
        lead,
        re.IGNORECASE,
    )
    if shipped is not None:
        section_label = _normalize_no_section_label(shipped.group(1))
        shipped_legs = [
            _infer_same_base_subsection_targets_from_lead(f"§ {section_label} {shipped.group(index)} ledd skal lyde")
            for index in (2, 3, 4)
        ]
        return section_label, shipped_legs[0], shipped_legs[1], shipped_legs[2]
    # W-61's widened sibling. The qualifier is optional and admits the currency
    # spellings that carry no address information; the shift sentence may repeat
    # its own ``§`` (required below to EQUAL the repealed section); the section
    # class carries W-32(c)'s ``(?:\s+[A-Za-z])?`` suffix so "§ 3 c" and "§ 41 a"
    # resolve their section instead of cutting it short at the digits.
    # lawvm-regex: owning_parser this IS the unstructured repeal-then-shift lead parser
    widened = re.match(
        r"^§\s*(?P<section>[0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+"
        r"(?P<repealed>.+?)\s+ledd\s+oppheves\.\s*"
        r"(?:§\s*(?P<shift_section>[0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+)?"
        r"(?:(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+)?"
        r"(?P<source>.+?)\s+ledd\s+blir\s+(?P<destination>.+?)\s+ledd\.?$",
        lead,
        re.IGNORECASE,
    )
    if widened is None:
        return None
    section_label = _normalize_no_section_label(widened.group("section"))
    shift_section_label = widened.group("shift_section")
    if shift_section_label is not None and _normalize_no_section_label(shift_section_label) != section_label:
        return None
    phrases = [_no_ledd_shift_ordinals(widened.group(name)) for name in ("repealed", "source", "destination")]
    if any(ordinals is None for ordinals in phrases):
        return None
    widened_legs = [
        [LegalAddress(path=(("section", section_label), ("subsection", str(ordinal)))) for ordinal in ordinals or ()]
        for ordinals in phrases
    ]
    return section_label, widened_legs[0], widened_legs[1], widened_legs[2]


# W-67. The section-renumber lead, widened off two literal tokens.
#
# The shipped production reads exactly ``Nåværende § X blir ny § Y.``. Two tokens
# in it carry no address information and yet decide whether the act lowers at all:
#
#   * the literal ``Nåværende`` — the currency qualifier, which drafters spell
#     eight ways (``_NO_CURRENCY_QUALIFIER_ALTERNATION``, W-61's measured set);
#   * the literal ``ny`` in ``blir ny §`` — a purely stylistic marker. The
#     collective re-enactment production at ``_NO_COLLECTIVE_RENUMBER_RE`` already
#     records that both spellings occur inside ONE part of one act ("Nåværende
#     § 12 blir § 14." beside "Nåværende § 16 blir ny § 20."), and deliberately
#     left this production alone because it had not measured it. W-62 measured it.
#
# The census over all 9,454 corpus ``no_parse_unstructured_lead_unmatched``
# refusals: relaxing BOTH tokens admits 64 refusal occurrences — 62 distinct
# leads, 44 instruments, 44 base acts — and every single one is classified by
# W-62's family census as ``renumber_shift/section:nåværende:single``, the family
# this production exists to lower. Zero matches fall outside it. Split by token:
# 20 need only the qualifier, 36 need only the optional ``ny``, 8 need both.
# Witness: ``Gjeldende § 10-10 blir ny § 10-13.``, a leaf
# ``<article class="defaultP">`` in part ``kapV`` of ``no/lovtid/2020-12-18-157``,
# address-coincident with two live ``OPS_MISSING`` divergence rows on scan
# candidate ``no/lov/2010-06-04-21``.
#
# STRICTLY ADDITIVE, in W-61's shape and for W-61's reason: the shipped pattern
# is attempted FIRST, character for character, and only a lead it does not match
# at all reaches the widened one. W-61's first cut replaced its production
# outright and regressed 14 leads; nothing here can, because nothing that lowers
# today takes a different path.
#
# The widened pattern keeps the shipped label class ``[0-9A-Za-z-]+`` rather than
# borrowing W-32(c)'s ``(?:\s+[A-Za-z])?`` suffix. That suffix would admit leads
# the census never priced ("§ 3 c"), and a widening whose claim is a measured
# population must not quietly exceed it. ``ny`` is admitted only in the masculine
# singular: ``§`` is a masculine noun, so ``nytt``/``nye`` before it would not be
# this sentence, and neither spelling occurs in the corpus refusals.
_NO_UNSTRUCTURED_SECTION_RENUMBER_WIDENED_RE = compile_classifier_regex(
    r"^(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r") §\s*([0-9A-Za-z-]+)"
    r"\s+blir (?:ny )?§\s*([0-9A-Za-z-]+)\.?$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.unstructured_section_renumber_widened",
)


def _no_unstructured_section_renumber_labels(lead: str) -> Optional[tuple[str, str, str]]:
    """``Nåværende § X blir ny § Y.`` → ``(source_label, destination_label, pattern)``.

    ``pattern`` is ``"shipped"`` or ``"widened"`` — returned, rather than kept
    private, so the additive ordering is a fact a test can assert instead of a
    claim a comment makes. See the block above for the measurement.
    """
    # The shipped pattern, UNCHANGED, character for character, and tried first.
    # It stays an inline ``re.match`` for the reason W-32(c) records for its
    # siblings: this is a scanned semantic-plane module (FW-07), and moving a
    # shipped production to a module-level compile is not this widening's
    # business.
    # lawvm-regex: owning_parser this IS the unstructured section-renumber lead parser
    shipped = re.match(
        r"^Nåværende §\s*([0-9A-Za-z-]+)\s+blir ny §\s*([0-9A-Za-z-]+)\.?$",
        lead,
        re.IGNORECASE,
    )
    match = shipped if shipped is not None else _NO_UNSTRUCTURED_SECTION_RENUMBER_WIDENED_RE.match(lead)
    if match is None:
        return None
    return (
        _normalize_label(match.group(1)),
        _normalize_label(match.group(2)),
        "shipped" if shipped is not None else "widened",
    )


# W-74. The SECTION-level repeal-then-shift run-on, and its self-proving guard.
#
# One lead, two sentences: a section-list repeal followed by a section shift into
# a slot the repeal just vacated. The witness is
# ``§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 10.``
# (``no/lovtid/2012-08-24-64``, bustøttelova), and before this production every
# lead of the shape was refused outright — every shipped section-repeal pattern is
# anchored ``oppheves\.?$`` and every shipped renumber pattern is anchored
# ``^Nåværende``, so a lead carrying both sentences matches neither.
#
# THE PRECEDENT, which is why this is one pattern and not a sentence splitter.
# The LEDD-level sibling of exactly this family already ships as
# ``_no_unstructured_repeal_renumber_legs`` ("§ X <ord> ledd oppheves. <ord> ledd
# blir <ord> ledd"), W-61 widened it, and it reads its two sentences as ONE
# combined pattern. This production is that one's section-level analogue, member
# for member: its own combined regex, its own optional currency qualifier drawn
# from ``_NO_CURRENCY_QUALIFIER_ALTERNATION``, and W-32(c)'s ``(?:\s+[A-Za-z])?``
# label suffix so "§ 3 i" resolves its section instead of stopping at the digit.
# No general sentence splitter is introduced, and none is needed.
#
# MEASURED POPULATION: 10 leads corpus-wide over the 9,454
# ``no_parse_unstructured_lead_unmatched`` refusals, on 7 instruments and 7 base
# laws. Every one is a genuine repeal-then-shift; the five neighbouring leads that
# carry both verbs in the OTHER order ("Nåværende § 18-11 blir ny § 18-10.
# Paragrafens bokstav d og e oppheves.") or with a trailing payload ("… blir ny
# § 27 og skal lyde:") are refused by construction — the first because ``§`` and
# ``.`` are outside the repeal list's character class, the second because the
# shift tail is anchored at the destination label.
#
# THE SAFETY RESTRICTION, and it is a hard conjunct rather than a heuristic: the
# shift's DESTINATION must be a label THIS SAME LEAD repeals. That makes the
# production self-proving. It cannot write into occupied law, because the only
# slot it will ever write into is one it has already emitted a REPEAL for, in the
# same op group and at a lower sequence number. This is precisely W-54's concern,
# and precisely what went wrong on husbankloven when W-67's textually correct 2017
# renumber landed on a § 13 that no applied op had vacated.
#
# Under the restriction 7 of the 10 accept and 3 refuse. The three refusals are
# all ``no/lovtid/2015-04-10-17`` CROSS-CHAPTER shifts ("§ 7-1 oppheves. Nåværende
# § 7-2 blir ny § 2-2." and two siblings): the lead vacates a chapter 7 label and
# writes into a chapter 2 one, so nothing here proves § 2-2 is free and the lead
# keeps its existing refusal receipt. That is the conservative polarity the ledd
# sibling already uses for its 19 trailing-clause leads — a lead this grammar
# cannot fully account for lowers nothing.

# The label class, and it is DIGIT-INITIAL on purpose. The shipped section
# productions spell theirs ``[0-9A-Za-z-]+``, which also admits a bare word — and
# a bare word reaching the repeal list is not harmless here, because the list is
# both the set the REPEAL ops are minted from and the set the destination conjunct
# is checked against ("… og siste" would repeal a § siste and could satisfy the
# conjunct against itself). Every label in the measured population is
# digit-initial (10, 7-3, 1-2, 41, 3 i), so requiring it costs the production
# nothing and closes that shape by construction rather than by a guard.
_NO_SECTION_LABEL_WITH_LETTER_SUFFIX = r"[0-9][0-9A-Za-z-]*(?:\s+[A-Za-z])?"

# The repeal head and the shift tail, as one anchored pattern. The repeal list is
# captured as a bounded character class rather than ``.+?`` — ``§`` and ``.`` are
# deliberately OUTSIDE it, which is what stops the pattern from reading across a
# sentence boundary and taking a shift sentence for a repeal list. The span is
# then parsed by ``_no_section_repeal_list_labels``, which refuses anything that
# is not a closed set of section labels.
#
# It stays an inline ``re.match`` in the function below rather than a
# ``compile_classifier_regex`` constant, for the reason the ledd-level sibling
# already records: the letter-suffixed label class is an adjacent variable repeat
# with overlapping starts and the classifier-safety gate refuses the wrap. Checked,
# not assumed — the gate rejects this exact pattern with "adjacent variable
# backtracking repeats … have overlapping starts".
#
# ``opphev(?:es|a)`` is the two spellings the measured population uses (``oppheves``
# on nine leads, the nynorsk periphrastic ``blir oppheva`` on the witness). Other
# nynorsk forms the module recognises elsewhere are deliberately NOT admitted here:
# a widening whose claim is a measured population must not quietly exceed it.
_NO_UNSTRUCTURED_SECTION_REPEAL_RENUMBER_PATTERN = (
    r"^(?:(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+)?"
    r"§{1,2}\s*(?P<repealed>[0-9][0-9A-Za-z,\s-]*?)\s+(?:blir\s+)?opphev(?:es|a)\.\s+"
    r"(?:(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+)?"
    r"§\s*(?P<source>" + _NO_SECTION_LABEL_WITH_LETTER_SUFFIX + r")\s+blir\s+(?:ny\s+)?"
    r"§\s*(?P<destination>" + _NO_SECTION_LABEL_WITH_LETTER_SUFFIX + r")\.?$"
)


def _no_section_repeal_list_labels(text: str) -> Optional[list[str]]:
    """``"10, 11 og 12"`` → ``["10", "11", "12"]``; ``"1-2 til 1-7"`` → the range.

    ``None`` means the span is not a closed set of section labels, and the caller
    must refuse the whole lead rather than repeal a guess.

    The ``til`` range goes through ``_expand_no_section_range_labels``, the same
    helper the shipped standalone ``§§ X til Y oppheves.`` production uses. Until
    W-98 (c) that helper truncated a hyphenated range to its two ENDPOINTS (an
    under-repeal this docstring recorded as the shipped behaviour); it now
    enumerates chapter-numbered ranges and returns ``None`` for a range it
    cannot enumerate, which refuses the whole lead here. The destination
    conjunct is evaluated against the same set the REPEAL ops are minted from,
    so the two can never disagree.
    """
    # lawvm-regex: owning_parser this IS the section-list parser for the
    # repeal-then-shift lead, and it runs on a span the anchored production above
    # already captured
    range_match = re.fullmatch(
        r"(?P<start>" + _NO_SECTION_LABEL_WITH_LETTER_SUFFIX + r")\s+til\s+"
        r"(?P<end>" + _NO_SECTION_LABEL_WITH_LETTER_SUFFIX + r")",
        text,
        re.IGNORECASE,
    )
    if range_match is not None:
        return _expand_no_section_range_labels(range_match.group("start"), range_match.group("end"))
    labels: list[str] = []
    # lawvm-regex: owning_parser splits the captured list on its separators; every
    # member is validated below and one invalid member refuses the whole lead
    for part in re.split(r",\s*|\s+og\s+", text, flags=re.IGNORECASE):
        part = part.strip()
        # lawvm-regex: owning_parser validates one member of the captured list
        if re.fullmatch(_NO_SECTION_LABEL_WITH_LETTER_SUFFIX, part) is None:
            return None
        labels.append(_normalize_no_section_label(part))
    return labels or None


def _no_unstructured_section_repeal_renumber_labels(
    lead: str,
) -> Optional[tuple[list[str], str, str]]:
    """``§§ 10, 11 og 12 blir oppheva. Noverande § 13 blir ny § 10.`` → ``(repealed, src, dst)``.

    ``None`` means this production declines the lead and the walk falls through to
    its ordinary refusal. The destination-vacated conjunct is enforced here, so a
    caller holding a tuple may mint the repeals and the shift without re-checking
    anything: ``dst`` is guaranteed to be a member of ``repealed``.
    """
    # lawvm-regex: owning_parser this IS the unstructured section-level repeal-then-shift lead parser
    match = re.match(_NO_UNSTRUCTURED_SECTION_REPEAL_RENUMBER_PATTERN, lead, re.IGNORECASE)
    if match is None:
        return None
    repealed = _no_section_repeal_list_labels(match.group("repealed"))
    if repealed is None:
        return None
    source_label = _normalize_no_section_label(match.group("source"))
    destination_label = _normalize_no_section_label(match.group("destination"))
    # THE hard conjunct. Not a heuristic and not a preference: without it this
    # production is a way to write into law it has not proven is vacant.
    if destination_label not in repealed:
        return None
    return repealed, source_label, destination_label


def _no_split_ledd_path(path: str) -> Optional[tuple[str, int]]:
    """``"lov/2005-06-17-90/§24-8/ledd/3"`` → ``("lov/2005-06-17-90/§24-8/ledd/", 3)``."""
    prefix, separator, tail = path.rpartition(_NO_LEDD_PATH_STEP)
    if not separator or not tail.isdigit() or "§" not in prefix:
        return None
    return prefix + separator, int(tail)


def _no_completed_move_legs_from_ledd_shift_prose(
    lead: str,
    legs: Sequence[tuple[str, str]],
) -> Optional[list[tuple[str, str]]]:
    """Complete an under-declared ``data-move-part`` from the block's own prose.

    Returns the FULL leg list in markup order (ascending prose order — the same
    order Lovtidend writes a complete attribute in, so the caller's ordinary
    reversal applies unchanged), or ``None`` to leave ``legs`` exactly as given.
    """
    if not legs:
        return None
    shifts = [
        parsed
        for parsed in (_no_ledd_shift_pairs_from_sentence(sentence) for sentence in _split_no_sentences(lead))
        if parsed is not None
    ]
    if len(shifts) != 1:
        return None
    section_label, prose_pairs = shifts[0]
    if len(prose_pairs) <= len(legs):
        return None
    template = ""
    declared: set[tuple[int, int]] = set()
    for raw_source, raw_destination in legs:
        source_step = _no_split_ledd_path(raw_source)
        destination_step = _no_split_ledd_path(raw_destination)
        if source_step is None or destination_step is None:
            return None
        if source_step[0] != destination_step[0]:
            return None
        if template and template != source_step[0]:
            return None
        template = source_step[0]
        declared.add((source_step[1], destination_step[1]))
    if not declared.issubset(set(prose_pairs)):
        return None
    if section_label:
        markup_section = template[: -len(_NO_LEDD_PATH_STEP)].rpartition("/")[2]
        if _normalize_no_section_label(markup_section.lstrip("§")) != section_label:
            return None
    return [(f"{template}{src}", f"{template}{dst}") for src, dst in prose_pairs]


def _payload_from_direct_text_article(
    article_el: etree._Element,
    target: LegalAddress,
) -> Optional[IRNode]:
    kind = target.leaf_kind()
    label = target.leaf_label() or None
    if kind == "subsection":
        payload = _parse_subsection(article_el, 1, set())
        if payload is None:
            return None
        return _with_no_node_label(payload, label)
    if kind == "sentence":
        text = _node_text_without_structural_children(article_el)
        if not text:
            return None
        return IRNode(kind=IRNodeKind.SENTENCE, label=label, text=text)
    return None


def _split_no_sentences(text: str) -> list[str]:
    raw_parts = [
        _normalize_space(part) for part in _SENTENCE_SPLIT_RE.split(_normalize_space(text)) if _normalize_space(part)
    ]
    parts: list[str] = []
    for part in raw_parts:
        first_token = part.split()[0].lower() if part.split() else ""
        if (
            parts
            and parts[-1].split()
            and (
                parts[-1].split()[-1].lower() in _SENTENCE_ABBREVIATIONS
                or (
                    re.fullmatch(r"\d+\.", parts[-1].split()[-1]) is not None
                    and first_token.strip(_MONTH_TOKEN_TRAILING_PUNCTUATION) in _NORWEGIAN_MONTHS
                )
            )
        ):
            parts[-1] = _normalize_space(f"{parts[-1]} {part}")
        else:
            parts.append(part)
    return parts


def _extract_payload_candidates(
    change_el: etree._Element,
    targets: Sequence[LegalAddress],
) -> dict[tuple[str, str], IRNode]:
    """Build leaf-kind/label payload candidates from a Lovdata change block."""
    candidates: dict[tuple[str, str], IRNode] = {}

    used_item_labels: set[str] = set()
    next_item_index = 1

    for li_el in _direct_children(change_el, "li"):
        item = _parse_item(li_el, next_item_index, used_item_labels)
        if item is not None and item.label:
            _index_no_item_candidates(candidates, item)
            next_item_index += 1

    for container in _direct_children(change_el):
        if _local_name(container) in _ITEM_CONTAINER_TAGS:
            for li_el in _direct_children(container, "li"):
                item = _parse_item(li_el, next_item_index, used_item_labels)
                if item is not None and item.label:
                    _index_no_item_candidates(candidates, item)
                    next_item_index += 1

    for article in _direct_children(change_el, "article"):
        classes = _classes(article)
        if "legalArticle" in classes:
            section = _parse_section(article)
            if section is not None and section.label:
                candidates[("section", section.label)] = section
        elif "futureLegalArticle" in classes:
            section = _parse_future_section(article)
            if section is not None and section.label:
                candidates[("section", section.label)] = section

    direct_text_articles = [
        article
        for article in _direct_children(change_el, "article")
        if {"legalP", "numberedLegalP"} & _classes(article)
    ]
    direct_targets = [
        target for target in targets if target.leaf_kind() in {"subsection", "sentence"} and target.leaf_label()
    ]
    if direct_text_articles and direct_targets:
        leaf_kinds = {target.leaf_kind() for target in direct_targets}
        if len(direct_text_articles) >= len(direct_targets) and len(leaf_kinds) == 1:
            for article, target in zip(direct_text_articles, direct_targets, strict=False):
                payload = _payload_from_direct_text_article(article, target)
                if payload is not None and target.leaf_label():
                    candidates[(target.leaf_kind(), target.leaf_label())] = payload
        elif len(direct_text_articles) == 1 and leaf_kinds == {"sentence"} and len(direct_targets) > 1:
            text = _node_text_without_structural_children(direct_text_articles[0])
            sentences = _split_no_sentences(text)
            if len(sentences) == len(direct_targets):
                for sentence_text, target in zip(sentences, direct_targets, strict=True):
                    if not target.leaf_label():
                        continue
                    candidates[("sentence", target.leaf_label())] = IRNode(
                        kind=IRNodeKind.SENTENCE,
                        label=target.leaf_label(),
                        text=sentence_text,
                    )
    if direct_targets and {target.leaf_kind() for target in direct_targets} == {"sentence"} and len(direct_targets) > 1:
        raw_text = _normalize_space(" ".join(str(_t) for _t in change_el.itertext()))
        if ":" in raw_text:
            tail = _normalize_space(raw_text.split(":", 1)[1])
            sentences = _split_no_sentences(tail)
            if len(sentences) == len(direct_targets):
                for sentence_text, target in zip(sentences, direct_targets, strict=True):
                    if not target.leaf_label():
                        continue
                    candidates[("sentence", target.leaf_label())] = IRNode(
                        kind=IRNodeKind.SENTENCE,
                        label=target.leaf_label(),
                        text=sentence_text,
                    )

    return candidates


def _extract_payload_candidates_from_nodes(
    nodes: Sequence[etree._Element],
    targets: Sequence[LegalAddress],
) -> dict[tuple[str, str], IRNode]:
    container = etree.Element("payload")
    for node in nodes:
        # XML elements are mutable and get re-parented when appended, so keep a
        # detached clone at the boundary before building payload candidates.
        cloned = copy.deepcopy(node)
        container.append(cloned)
        if _local_name(cloned) == "article":
            for child in _direct_children(cloned):
                if _local_name(child) in _ITEM_CONTAINER_TAGS or _local_name(child) == "li":
                    container.append(child)
    return _extract_payload_candidates(container, targets)


def _infer_same_base_subsection_targets_from_lead(lead: str) -> list[LegalAddress]:
    return [target for _action, target in _infer_same_base_subsection_target_specs_from_lead(lead)]


def _infer_same_base_subsection_target_specs_from_lead(
    lead: str,
) -> list[tuple[StructuralAction, LegalAddress]]:
    lead = _normalize_space(lead).rstrip(":")
    match = re.search(
        r"§\s*([0-9A-Za-z-]+)\s+(.+?)\s+ledd\s+(?:skal\s+)?lyde$",
        lead,
        re.IGNORECASE,
    )
    if not match:
        return []
    section_label = _normalize_no_section_label(match.group(1))
    ordinal_phrase = _normalize_space(match.group(2)).lower()
    tokens = re.split(r"\s*(?:,| og )\s*", ordinal_phrase)
    specs: list[tuple[StructuralAction, LegalAddress]] = []
    current_action: StructuralAction = StructuralAction.REPLACE
    for token in tokens:
        token = token.strip()
        if re.match(r"^(?:nytt|nye)\s+", token, re.IGNORECASE):
            current_action = StructuralAction.INSERT
        elif re.match(r"^nåværende\s+", token, re.IGNORECASE):
            current_action = StructuralAction.REPLACE
        token = re.sub(r"^(?:nytt|nye|nåværende)\s+", "", token, flags=re.IGNORECASE)
        label = _NORWEGIAN_ORDINALS.get(token.strip())
        if not label:
            return []
        specs.append((current_action, LegalAddress(path=(("section", section_label), ("subsection", label)))))
    return specs


# W-32(c): Lovtidend spells a letter-suffixed section label with a SPACE
# ("§ 28 b", "§ 216 i"), which the bare ``[0-9A-Za-z-]+`` label class cannot
# span. In the sentence grammar the failure was not a non-match but something
# worse: the narrow class matched with the SECTION cut short ("216") and the
# stray letter absorbed into the ordinal phrase ("d første"), which then failed
# ``_NORWEGIAN_ORDINALS`` and returned no specs -- a silent drop, not a receipt.
#
# Differential sweep over every ``defaultP``/``legalP`` text in all 3,089
# amendment artifacts, comparing the SPECS the two classes produce (not the
# regex groups): 294 texts gain specs, 0 lose specs, 0 resolve to different
# specs. Every absorbed suffix letter was checked against its act: a=166, b=55,
# c=22, d=16, e=13, f=6, g=5, m=3, h=2, j=2, and one each of l/i/o/n -- the
# single-letter Norwegian words that could have been prose rather than a label
# ("i") occur only as straffeprosessloven § 216 i, a real section in the
# § 216 a-o run, so there is no prose reading to lose.
#
# Scoped to this grammar on purpose: the class is used by other §-anchored
# productions too, and each of those needs its own differential before it is
# widened. This one is measured; the others are not.
#
# BOUNDED by the same sweep, at op level rather than spec level: widening the
# LEDD-LESS production below as well cost 2 ops right->wrong
# (``no/lovtid/2025-06-20-38``), because that production resolves a
# section/sentence address with NO subsection step and the structured lowering
# lets an inferred sentence spec override the markup's own — fuller — target.
# The widening therefore applies only to the ledd-carrying production, which
# always resolves all three steps and so can never shorten an address.
#
# Spelled inline as ``[0-9A-Za-z-]+(?:\s+[A-Za-z])?`` rather than interpolated
# from a shared constant: an f-string-built regex inside a per-lead function is
# a frozen-residue smell (FW-08), and hoisting it to a module constant would
# need the classifier wrap, which the two adjacent ``(.+?)`` spans in this
# production cannot pass. The space is collapsed downstream by
# ``_normalize_no_section_label``, which already strips spaces.


def _infer_same_base_sentence_targets_from_lead(lead: str) -> list[LegalAddress]:
    return [target for _action, target in _infer_same_base_sentence_target_specs_from_lead(lead)]


def _infer_same_base_sentence_target_specs_from_lead(
    lead: str,
) -> list[tuple[StructuralAction, LegalAddress]]:
    lead = _normalize_space(lead).rstrip(":")
    match = re.match(
        r"^§\s*([0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+(.+?)\s+ledd\s+(.+?)\s+punktum\s+(?:skal\s+lyde|oppheves)$",
        lead,
        re.IGNORECASE,
    )
    if match:
        section_label = _normalize_no_section_label(match.group(1))
        subsection_label = _NORWEGIAN_ORDINALS.get(_normalize_space(match.group(2)).lower())
        if not subsection_label:
            return []
        ordinal_phrase = _normalize_space(match.group(3)).lower()
        tokens = re.split(r"\s*(?:,| og )\s*", ordinal_phrase)
        specs: list[tuple[StructuralAction, LegalAddress]] = []
        current_action: StructuralAction = StructuralAction.REPLACE
        for token in tokens:
            token = token.strip()
            if re.match(r"^(?:nytt|nye)\s+", token, re.IGNORECASE):
                current_action = StructuralAction.INSERT
            elif re.match(r"^nåværende\s+", token, re.IGNORECASE):
                current_action = StructuralAction.REPLACE
            token = re.sub(r"^(?:nåværende|nytt|nye)\s+", "", token, flags=re.IGNORECASE)
            if token == "siste":
                label = "last"
            else:
                label = _NORWEGIAN_ORDINALS.get(token)
            if not label:
                return []
            specs.append(
                (
                    current_action,
                    LegalAddress(
                        path=(("section", section_label), ("subsection", subsection_label), ("sentence", label))
                    ),
                )
            )
        return specs
    # NOT widened: see the bound recorded at ``_NO_SPACED_SECTION_LABEL``. This
    # ledd-less production yields a section/sentence address with no subsection
    # step, and the structured lowering lets an inferred sentence spec OVERRIDE
    # the markup's own target -- so widening here turned
    # ``§ 13 a nytt fjerde og femte punktum skal lyde`` (no/lovtid/2025-06-20-38,
    # whose markup already said ``§13a/ledd/1/setning/4``) into a subsection-less
    # address: 2 ops right->wrong. The ledd-carrying production above cannot do
    # that, because it always resolves all three steps.
    match = re.match(
        r"^§\s*([0-9A-Za-z-]+)\s+(.+?)\s+punktum\s+(?:skal\s+lyde|oppheves)$",
        lead,
        re.IGNORECASE,
    )
    if not match:
        return []
    section_label = _normalize_no_section_label(match.group(1))
    ordinal_phrase = _normalize_space(match.group(2)).lower()
    tokens = re.split(r"\s*(?:,| og )\s*", ordinal_phrase)
    specs: list[tuple[StructuralAction, LegalAddress]] = []
    current_action: StructuralAction = StructuralAction.REPLACE
    for token in tokens:
        token = token.strip()
        if re.match(r"^(?:nytt|nye)\s+", token, re.IGNORECASE):
            current_action = StructuralAction.INSERT
        elif re.match(r"^nåværende\s+", token, re.IGNORECASE):
            current_action = StructuralAction.REPLACE
        token = re.sub(r"^(?:nåværende|nytt|nye)\s+", "", token, flags=re.IGNORECASE)
        if token == "siste":
            label = "last"
        else:
            label = _NORWEGIAN_ORDINALS.get(token)
        if not label:
            return []
        specs.append((current_action, LegalAddress(path=(("section", section_label), ("sentence", label)))))
    return specs


# W-32(a): a lettered-item lead may name MORE THAN ONE ``bokstav`` in one
# sentence ("§ 49 andre ledd bokstav e og ny bokstav f skal lyde:"). The
# single-item grammar below cannot see the second item, so BOTH ops used to
# drop silently.  Measured surface (census over every ``defaultP``/``legalP``
# lead in all 3,089 amendment artifacts): 157 leads name two or more letters.
# This production is bounded to the 126 that carry the SAME address shape the
# single-item grammar already addresses -- ``§ X <ordinal> ledd bokstav ...``
# with no intervening ``nr.`` -- so the only dimension widened here is item
# ARITY.  The two measured residue shapes stay unreachable on purpose and are
# recorded rather than guessed at: 26 ledd-less leads ("§ 12-2 bokstav h og ny
# bokstav i skal lyde", a section->item address the ordinary path has no
# grammar for at all) and 12 with a ``nr.`` between the ledd and the bokstav
# ("§ 23-3 annet ledd nr. 2 bokstav c ..."), whose extra item step the
# single-item grammar only spells on the OTHER side of ``bokstav``.
#
# The grammar is split into a HEAD anchor and a TAIL anchor rather than written
# as one pattern with a ``.+?`` item span: a variable item span sitting directly
# against the ``\s+skal\s+lyde`` terminator is two adjacent variable repeats with
# overlapping starts, which the classifier-safety gate rejects. The item list is
# taken from between the two matches, the same prefix/residue shape W-24's
# Del-scope productions use.
_NO_MULTI_ITEM_LEAD_HEAD_RE = compile_classifier_regex(
    r"^§\s*([0-9A-Za-z-]+)\s+([A-Za-zÆØÅæøå]+)\s+ledd\s+bokstav(?:ene)?\s",
    re.IGNORECASE,
    classifier_id="norway.grafter.multi_item_bokstav_lead_head",
)
_NO_MULTI_ITEM_LEAD_TAIL_RE = compile_classifier_regex(
    r"\s*skal\s+lyde\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.multi_item_bokstav_lead_tail",
)

# One item token: an optional newness marker, an optional re-spelling of
# ``bokstav`` (Lovtidend writes both "bokstav e og f" and "bokstav e og ny
# bokstav f"), then exactly ONE letter. Anything else in the token -- a nested
# ``punktum``/``nr.``/``ledd`` address, a ``til`` range, a trailing ``)`` --
# fails the anchor and the whole lead falls through to the single-item grammar
# unchanged, which is the all-or-nothing rule applied at the grammar. Stripped
# marker by marker, again for the safety gate: an OPTIONAL group wrapping an
# alternation of variable-length literals reads as a nested quantifier.
_NO_MULTI_ITEM_NEWNESS_RE = compile_classifier_regex(
    r"^(ny|nye|nytt|nåværende|noverande)\s+",
    re.IGNORECASE,
    classifier_id="norway.grafter.multi_item_bokstav_newness",
)
_NO_MULTI_ITEM_BOKSTAV_RE = compile_classifier_regex(
    r"^(?:bokstavene|bokstav)\s+",
    re.IGNORECASE,
    classifier_id="norway.grafter.multi_item_bokstav_marker",
)
_NO_MULTI_ITEM_LETTER_RE = compile_classifier_regex(
    r"^[a-zæøå]$",
    re.IGNORECASE,
    classifier_id="norway.grafter.multi_item_bokstav_letter",
)


def _infer_no_multi_item_specs_from_lead(lead: str) -> list[tuple[StructuralAction, LegalAddress]]:
    """Recover two or more lettered-item targets declared by one lead sentence.

    Returns ``[]`` for anything that is not an unambiguous multi-item lead --
    including a lead that names exactly one item, which stays the single-item
    grammar's business.
    """
    # lawvm-regex: owning_parser this IS the multi-item lead parser
    head = _NO_MULTI_ITEM_LEAD_HEAD_RE.match(lead)
    if head is None:
        return []
    section_label = _normalize_no_section_label(head.group(1))
    subsection_label = _NORWEGIAN_ORDINALS.get(head.group(2).lower())
    if not section_label or not subsection_label:
        return []
    residue = lead[head.end() :]
    # lawvm-regex: owning_parser this IS the multi-item lead parser
    tail = _NO_MULTI_ITEM_LEAD_TAIL_RE.search(residue)
    if tail is None:
        return []
    items = _normalize_space(residue[: tail.start()])
    tokens = [token.strip() for token in re.split(r"\s*,\s*|\s+og\s+", items) if token.strip()]
    specs: list[tuple[StructuralAction, LegalAddress]] = []
    letters: list[str] = []
    for token in tokens:
        action = StructuralAction.REPLACE
        # lawvm-regex: owning_parser this IS the multi-item lead parser
        newness = _NO_MULTI_ITEM_NEWNESS_RE.match(token)
        if newness is not None:
            if newness.group(1).lower() in {"ny", "nye", "nytt"}:
                action = StructuralAction.INSERT
            token = token[newness.end() :]
        # lawvm-regex: owning_parser this IS the multi-item lead parser
        marker = _NO_MULTI_ITEM_BOKSTAV_RE.match(token)
        if marker is not None:
            token = token[marker.end() :]
        # lawvm-regex: owning_parser this IS the multi-item lead parser
        if _NO_MULTI_ITEM_LETTER_RE.match(token) is None:
            return []
        letter = _normalize_label(token).lower()
        if not letter:
            return []
        letters.append(letter)
        specs.append(
            (
                action,
                LegalAddress(
                    path=(
                        ("section", section_label),
                        ("subsection", subsection_label),
                        ("item", letter),
                    )
                ),
            )
        )
    if len(specs) < 2 or len(set(letters)) != len(letters):
        return []
    return specs


def _infer_same_base_item_targets_from_lead(lead: str) -> list[LegalAddress]:
    return [target for _action, target in _infer_same_base_item_target_specs_from_lead(lead)]


def _infer_same_base_item_target_specs_from_lead(lead: str) -> list[tuple[StructuralAction, LegalAddress]]:
    lead = _normalize_space(lead).rstrip(":")
    multi_specs = _infer_no_multi_item_specs_from_lead(lead)
    if multi_specs:
        return multi_specs
    match = re.search(
        # W-98 (d): ``\)?`` after the letter admits the print-era ``bokstav a)``
        # spelling (3 corpus leads + the 1994 witness); a bare letter is
        # byte-identical to the shipped read.
        r"§\s*([0-9A-Za-z-]+)\s+(.+?)\s+ledd\s+bokstav\s+([A-Za-z])\)?(?:\s+(?:nr\.|nummer)\s+([0-9A-Za-z-]+))?\s+(?:skal\s+)?lyde\b",
        lead,
        re.IGNORECASE,
    )
    if match:
        section_label = _normalize_no_section_label(match.group(1))
        subsection_label = _NORWEGIAN_ORDINALS.get(_normalize_space(match.group(2)).lower())
        if not subsection_label:
            return []
        item_label = _normalize_label(match.group(3)).lower()
        if not item_label:
            return []
        nested_label = _normalize_label(match.group(4) or "").lower()
        path = [
            ("section", section_label),
            ("subsection", subsection_label),
            ("item", item_label),
        ]
        if nested_label:
            path.append(("item", nested_label))
        return [(StructuralAction.REPLACE, LegalAddress(path=tuple(path)))]
    match = re.search(
        r"§\s*([0-9A-Za-z-]+)\s+(.+?)\s+ledd\s+nytt\s+siste\s+strekpunkt\s+(?:skal\s+)?lyde\b",
        lead,
        re.IGNORECASE,
    )
    if not match:
        return []
    section_label = _normalize_no_section_label(match.group(1))
    subsection_label = _NORWEGIAN_ORDINALS.get(_normalize_space(match.group(2)).lower())
    if not subsection_label:
        return []
    return [
        (
            StructuralAction.REPLACE,
            LegalAddress(
                path=(
                    ("section", section_label),
                    ("subsection", subsection_label),
                    ("item", "last"),
                )
            ),
        )
    ]


def _infer_same_base_subsection_targets(
    change_el: etree._Element,
) -> list[LegalAddress]:
    """Recover malformed same-section subsection targets from amendment lead text.

    Some Lovdata amendment blocks carry one correct same-base target and one bogus
    cross-act target even though the lead text is unambiguous, e.g.
    ``§ 11 andre og tredje ledd skal lyde:``. In that narrow case we recover the
    intended same-base subsection targets from the prose instead of silently
    dropping the extra payload.
    """
    lead_articles = [article for article in _direct_children(change_el, "article") if "defaultP" in _classes(article)]
    if not lead_articles:
        return []
    return _infer_same_base_subsection_targets_from_lead(
        _normalize_space(" ".join(str(_t) for _t in lead_articles[0].itertext()))
    )


def _infer_same_base_sentence_targets(
    change_el: etree._Element,
) -> list[LegalAddress]:
    lead_articles = [article for article in _direct_children(change_el, "article") if "defaultP" in _classes(article)]
    if not lead_articles:
        return []
    return _infer_same_base_sentence_targets_from_lead(
        _normalize_space(" ".join(str(_t) for _t in lead_articles[0].itertext()))
    )


def _heading_only_section_payload(
    change_el: etree._Element,
    action: StructuralAction | str,
    target: LegalAddress,
    *,
    allow_future_title: bool = False,
) -> Optional[IRNode]:
    """The heading a ``Overskriften til § …`` lead announces, as a heading-only payload.

    ``allow_future_title`` widens WHERE the title may live — Lovdata writes it
    either as a second ``defaultP`` article or as a ``span.futuretitle`` — and is
    set only by W-82's carrier reach, behind W-79's declaration gate. The lead
    predicate and the payload shape are the same either way, so nothing that used
    to lower can change.
    """
    if _no_action_value(action) != "replace" or target.leaf_kind() != "section":
        return None
    text_articles = [article for article in _direct_children(change_el, "article") if "defaultP" in _classes(article)]
    if not text_articles:
        return None
    lead = _normalize_space(" ".join(str(_t) for _t in text_articles[0].itertext()))
    if not _SECTION_HEADING_ONLY_RE.match(lead):
        return None
    title = ""
    for article in text_articles[1:]:
        candidate = _normalize_space(" ".join(str(_t) for _t in article.itertext()))
        if candidate:
            title = candidate
            break
    if not title and allow_future_title:
        title = _no_structured_future_title(change_el)
    if not title:
        return None
    return IRNode(
        kind=IRNodeKind.SECTION,
        label=target.leaf_label() or None,
        children=(IRNode(kind=IRNodeKind.HEADING, text=title),),
    )


def _heading_only_unstructured_section_payload(
    target_label: str,
    payload_nodes: Sequence[etree._Element],
) -> Optional[IRNode]:
    title = ""
    for node in payload_nodes:
        if _local_name(node) != "article" or not ({"defaultP", "legalP"} & _classes(node)):
            continue
        candidate = _normalize_space(" ".join(str(_t) for _t in node.itertext()))
        if candidate:
            title = candidate
            break
    if not title:
        return None
    return IRNode(
        kind=IRNodeKind.SECTION,
        label=target_label,
        children=(IRNode(kind=IRNodeKind.HEADING, text=title),),
    )


def _no_heading_only_section_lead_label(lead: str) -> Optional[str]:
    """The section a heading-only lead addresses ("§ 26 overskriften skal lyde:").

    Lifted out of the unstructured walk so the payload BOUNDARY and the
    production that consumes the payload recognize ONE surface rather than two:
    the boundary hands the heading over precisely when this production is the one
    that will want it. Widening the surface is grammar (W-65), not boundary, and
    is deliberately not done here.
    """
    # lawvm-regex: owning_parser this IS the heading-only section lead parser
    match = re.match(r"^§\s*([0-9A-Za-z-]+)\s+overskriften\s+skal\s+lyde:?$", lead, re.IGNORECASE)
    return _normalize_no_section_label(match.group(1)) if match is not None else None


# W-64. Lovdata marks a NEW SECTION'S HEADING with ``class="defaultP"`` -- the
# same class it uses for amendment leads -- so the payload cursor's "stop at the
# next ``defaultP``" boundary stops ON the heading and collects ZERO payload
# nodes. The section body behind it is stranded and the lead refuses.
#
# Witness, probed at the DOM nodes the walk actually reads (``no/lovtid/
# 2003-12-19-129`` part II, veterinaerloven): ``<article class="defaultP">Ny §
# 37 a skal lyde:</article>`` is followed by ``<article class="defaultP">Avgift
# og gebyr</article>`` and then SIX ``<article class="legalP">`` ledd. The same
# instrument repeats the shape three more times (parts I and III, and again at §
# 3 / § 18), so it is markup convention, not a one-off.
#
# The cardinal risk is the opposite polarity: absorbing a genuine amendment lead
# into some other lead's payload silently DELETES an operation. So the
# discriminator is built to refuse when uncertain, and every clause below is a
# measured separation rather than a plausible one. Over all 3,089 unstructured
# artifacts there are 23,716 (lead, next-node-is-``defaultP``) pairs; 569 of them
# sit behind a lead that ends in ``lyde:``, and of those 569 exactly 21 have a
# successor that DOES parse as a lead today (it produces an op at base). All 21
# are excluded by THREE independent clauses at once -- every one of them carries
# an operative verb, carries a ``§``, and ends in ``:`` or ``.`` -- so no single
# clause is load-bearing for the safety property. The admitted set contains zero
# nodes that produce an op at base.
#
#   1. the lead must END in ``lyde:``. A lead that announces no payload (a
#      repeal, a renumber, a bare law switch) can never gain one here; a lead
#      that carries INLINE payload after the colon is a different family and is
#      left where it is.
#   2. no operative verb (``skal ... lyde``, ``oppheves``, ``endres``, ...). A
#      heading is a noun phrase; a lead states an action.
#   3. no ``§``. Norwegian amendment leads address by section sign; headings in
#      the census's admitted set carry none.
#   4. no sentence-final punctuation (``.``, ``:``, ``;``, ``,``). A lead is a
#      sentence or a colon-command; a heading is a bare phrase.
#   5. at most 80 characters. Measured: the admitted headings run 3-79
#      characters, so this refuses only prose that no clause above caught.
#   6. the node the heading introduces must be there -- either a body node
#      (``legalP``/``numberedLegalP``/``listArticle``) immediately after it, or a
#      lead whose SHIPPED production wants the heading and nothing else
#      (``§ X overskriften skal lyde:``). Absorbing a ``defaultP`` that
#      introduces nothing buys no payload and only spends risk.
#
# Only the FIRST node after the lead is ever tested (the caller's ``cursor ==
# idx + 1`` guard), so at most ONE ``defaultP`` per lead can be absorbed and the
# walk still stops at the next one. Chapter-level inserts whose body is itself a
# run of ``defaultP`` sections ("Nytt kapittel 5A skal lyde:", 185 pairs) fail
# clause 6 by construction and keep their present receipts -- that surface is
# W-65's address grammar, not this boundary.
_NO_PAYLOAD_HEADING_MAX_LEN = 80
_NO_PAYLOAD_BODY_CLASSES = frozenset({"legalP", "numberedLegalP", "listArticle"})


def _no_unstructured_payload_heading_node(
    lead: str,
    node: etree._Element,
    following: Optional[etree._Element],
) -> bool:
    """Is this boundary ``defaultP`` a section heading rather than the next lead?"""
    # lawvm-regex: owning_parser this IS the payload-announcing lead tail test
    if not re.search(r"\blyde\s*:\s*$", lead, re.IGNORECASE):
        return False
    text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
    if not text or len(text) > _NO_PAYLOAD_HEADING_MAX_LEN:
        return False
    if "§" in text or text[-1] in ".:;,":
        return False
    if _no_unstructured_lead_looks_operative(text):
        return False
    if _no_heading_only_section_lead_label(lead) is not None:
        return True
    # W-98 (f): the CHAPTER heading lead wants the same one node, for the same
    # reason — its title is a bare noun phrase Lovdata marks ``defaultP``.
    if _no_chapter_heading_lead(lead) is not None:
        return True
    return (
        following is not None
        and _local_name(following) == "article"
        and bool(_NO_PAYLOAD_BODY_CLASSES & _classes(following))
    )


_NO_WHOLE_SECTION_LEAD_RE = re.compile(
    r"^(?P<insert>Ny\s+)?§\s*(?P<label>[0-9]+(?:-[0-9]+)*(?:\s*[A-Za-z])?)\s+skal\s+lyde:\s*(?P<inline>.*)$",
    re.IGNORECASE | re.DOTALL,
)


# A chapter-scoped whole-section lead ("I kapittel III skal ny § 16-2 lyde:")
# carries the same operative content as the canonical "Ny § 16-2 skal lyde:"
# form, but the locative ``I kapittel <X>`` prefix and the ``skal ny § X lyde``
# verb order defeat ``_NO_WHOLE_SECTION_LEAD_RE``. Norwegian § numbering is
# act-global (the chapter is redundant for addressing), so we can safely drop
# the chapter scope and rewrite the lead into the canonical form the existing
# section lowering consumes.
_NO_CHAPTER_SCOPED_SECTION_LEAD_RE = re.compile(
    r"^I\s+kapit(?:tel|let|tlet)\s+\S+(?:\s+\S+?)?\s+skal\s+"
    r"(?P<insert>ny(?:tt|e)?\s+)?§\s*(?P<label>[0-9]+(?:-[0-9]+)*(?:\s*[A-Za-z])?)"
    r"\s+lyde:\s*(?P<inline>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_no_chapter_scoped_section_lead(lead: str) -> str:
    """Rewrite a chapter-scoped whole-section lead into the canonical form.

    "I kapittel III skal ny § 16-2 lyde: …" -> "Ny § 16-2 skal lyde: …" so the
    existing ``_NO_WHOLE_SECTION_LEAD_RE`` section lowering recognizes it. Leaves
    leads that do not match this exact shape untouched.
    """
    match = _NO_CHAPTER_SCOPED_SECTION_LEAD_RE.match(lead)
    if match is None:
        return lead
    prefix = "Ny " if match.group("insert") else ""
    inline = match.group("inline")
    return f"{prefix}§ {match.group('label')} skal lyde: {inline}".rstrip()


def _build_no_unstructured_section_payload(
    label: str,
    inline_text: str,
    payload_nodes: Sequence[etree._Element],
) -> Optional[IRNode]:
    """Build a whole-section payload from an unstructured ``§ X skal lyde:`` lead.

    Reuses the structured ``_parse_future_section`` lowering by wrapping the lead's
    inline tail text plus the following non-lead payload articles into a synthetic
    ``futureLegalArticle`` element. Returns ``None`` when no payload content can be
    recovered so the caller can honestly drop the lead.
    """
    synthetic = etree.Element("article")
    synthetic.set("class", "futureLegalArticle")
    synthetic.set("data-name", f"§{label}")

    inline_text = _normalize_space(inline_text)
    if inline_text:
        # An inline tail frequently re-states the section header (``§ 2-2. Title``)
        # before the body. Split it into a header span + body so the reused
        # ``_parse_future_section`` lowering treats the title as a heading, not text.
        header_match = re.match(
            rf"^§\s*{re.escape(label)}\s*\.\s*(?P<title>[^.]*?\S)?\s+(?P<body>[A-ZÆØÅ].*)$",
            inline_text,
            re.DOTALL,
        )
        if header_match:
            header_span = etree.SubElement(synthetic, "span")
            header_span.set("class", "futureLegalArticleHeader")
            header_span.text = f"§ {label}. {header_match.group('title') or ''}".strip()
            body = _normalize_space(header_match.group("body"))
            if body:
                body_article = etree.SubElement(synthetic, "article")
                body_article.set("class", "legalP")
                body_article.text = body
        else:
            inline_article = etree.SubElement(synthetic, "article")
            inline_article.set("class", "legalP")
            inline_article.text = inline_text

    for node in payload_nodes:
        if _local_name(node) != "article":
            continue
        classes = _classes(node)
        if "defaultP" in classes and not (_NO_PAYLOAD_BODY_CLASSES & classes):
            # W-64: the section HEADING the boundary now hands over. It has to
            # become the synthetic section's header span, not a body article:
            # ``_parse_future_section`` reads ``defaultP`` children as ledd, so
            # appending it verbatim would make the heading subsection 1 and shift
            # every real ledd's label by one -- the witness's six ledd would land
            # at ``subsection:2..7`` against a consolidation that prints 1..6.
            # Only the first such node is taken, and only when the lead's inline
            # tail did not already build a header.
            if len(synthetic) == 0:
                heading = _normalize_space(" ".join(str(_t) for _t in node.itertext()))
                if heading:
                    header_span = etree.SubElement(synthetic, "span")
                    header_span.set("class", "futureLegalArticleHeader")
                    header_span.text = f"§ {label}. {heading}"
            continue
        if not (_NO_PAYLOAD_BODY_CLASSES & classes):
            continue
        synthetic.append(copy.deepcopy(node))

    if len(synthetic) == 0:
        return None
    payload = _parse_future_section(synthetic)
    if payload is None or (not payload.children and not _normalize_space(payload.text or "")):
        return None
    return payload


# W-98 (c). A section RANGE, expanded arithmetically over chapter-numbered labels.
#
# The shipped expander enumerated ``§§ 16 til 19`` and returned only the two
# ENDPOINTS for anything else, so ``§§ 5-16 til 5-19 oppheves.`` repealed § 5-16
# and § 5-19 and left §§ 5-17 and 5-18 standing — an under-repeal W-74's list
# parser recorded as "the shipped behaviour" rather than fixed. Measured over
# every unstructured lead in the corpus, 20 range leads exist; 6 carry a
# chapter-numbered label (``5-16 til 5-19``, ``10-8 til 10-16``, ``12-8 til
# 12-16``, ``6-1 til 6-5``, ``15-2 til 15-8``, ``1-2 til 1-7``) and every one of
# them was silently truncated to its endpoints.
#
# THE RULE. A label is ``[<chapter>-]<number>[<letter>]``. A range expands when
# both ends share the chapter prefix (both none, or equal) and the numbers are
# ordered: every integer from the start number to the end number, with a
# letter-suffixed START kept as its own first label and a letter-suffixed END
# closed out by the letters ``a`` to that letter (``2 til 5a`` → 2, 3, 4, 5, 5a;
# ``5a til 7`` → 5a, 6, 7; ``5a til 5c`` → 5a, 5b, 5c). Lettered labels STRICTLY
# INSIDE the range (a § 3 a between § 3 and § 4) cannot be enumerated at the
# parse plane and are NOT repealed — that is an under-repeal, the safe wrong,
# recorded here as the production's limit rather than papered over with a
# tree-dependent guess.
#
# Anything else — a cross-chapter range (``2-4 til 3-2``), an unordered pair,
# a label shape outside the grammar — is ``None``: the caller REFUSES the whole
# lead with a typed receipt instead of the shipped silent endpoint pair. Zero
# corpus leads hit that branch today; it exists so the silent drop cannot come
# back.
# Inline ``re.match`` rather than a compiled classifier constant, for the reason
# the sibling productions record: the optional chapter prefix and the number are
# adjacent digit repeats with overlapping starts, which the classifier-safety
# lint refuses to wrap.
_NO_SECTION_RANGE_LABEL_PATTERN = r"^(?:(?P<chapter>[0-9]+)-)?(?P<number>[0-9]+)(?P<letter>[a-z]?)$"


def _expand_no_section_range_labels(start_label: str, end_label: str) -> Optional[list[str]]:
    """``("5-16", "5-19")`` → ``["5-16", "5-17", "5-18", "5-19"]``; ``None`` when unexpandable."""
    start = _normalize_no_section_label(start_label)
    end = _normalize_no_section_label(end_label)
    # lawvm-regex: owning_parser this IS the section-range label parser
    start_match = re.match(_NO_SECTION_RANGE_LABEL_PATTERN, start, re.IGNORECASE)
    # lawvm-regex: owning_parser this IS the section-range label parser
    end_match = re.match(_NO_SECTION_RANGE_LABEL_PATTERN, end, re.IGNORECASE)
    if start_match is None or end_match is None:
        return None
    chapter = start_match.group("chapter") or ""
    if chapter != (end_match.group("chapter") or ""):
        return None
    prefix = f"{chapter}-" if chapter else ""
    start_number = int(start_match.group("number"))
    end_number = int(end_match.group("number"))
    start_letter = (start_match.group("letter") or "").lower()
    end_letter = (end_match.group("letter") or "").lower()
    if start_number > end_number:
        return None
    if start_number == end_number:
        if start_letter and end_letter:
            if start_letter > end_letter:
                return None
            return [f"{prefix}{start_number}{chr(code)}" for code in range(ord(start_letter), ord(end_letter) + 1)]
        if start_letter:
            return None
        labels = [f"{prefix}{start_number}"]
        if end_letter:
            labels.extend(f"{prefix}{end_number}{chr(code)}" for code in range(ord("a"), ord(end_letter) + 1))
        return labels
    labels = []
    first_number = start_number
    if start_letter:
        labels.append(f"{prefix}{start_number}{start_letter}")
        first_number = start_number + 1
    labels.extend(f"{prefix}{number}" for number in range(first_number, end_number + 1))
    if end_letter:
        labels.extend(f"{prefix}{end_number}{chr(code)}" for code in range(ord("a"), ord(end_letter) + 1))
    return labels


# W-79: the structured payload lane's OWN-TEXT INVARIANT.
#
# ``_fallback_payload`` is the last resort of the structured ``document-change``
# lane: when no structured payload candidate matches a declared target, it takes
# the change node's OWN TEXT and writes it into the statute at that address. It
# never asked whether the node CLAIMED to carry a payload — so any node whose own
# text is an INSTRUCTION rather than content had its instruction written into
# in-force law. W-75 found one dialect of that (an address list under a word
# substitution), W-78 closed a second (``Følgende steder …``), and both were
# closed dialect by dialect in the announcement grammar. This is the general
# closure: the FALLBACK ITSELF must require the declaration.
#
# The rule, stated positively and reusing W-78's head discipline: the text the
# fallback is about to write must declare its own payload — a payload-introducing
# operative phrase (``skal … lyde`` / ``lyda`` / ``lyder`` / ``skal ha følgende
# ordlyd``) standing in the HEAD, i.e. before the first colon, with the colon
# closing the declaration and CONTENT following it. The instruction must be
# complete before the colon and the payload must exist after it; a node that
# satisfies neither is refused typed rather than lowered on a guess.
#
# The colon is also what makes the payload extractable, so the two halves are one
# rule: the payload IS the tail. The narrow ``^§ N skal lyde:`` strip this
# replaced only fired on section-initial leads, which left the lead prose glued to
# the front of the payload of every other declaring shape ("I lov 21. november
# 1952 nr. 3 … skal § 6 lyde: <law>" wrote its own citation into § 6).
#
# Measured over EVERY own-text-fallback payload the corpus produces (217 over
# 3,089 instruments; 556 fallback calls, the rest already returning None):
#   * 68 declare a payload and keep lowering — 61 byte-identical to today, 7 with
#     the lead prefix now removed (each adjudicated at the landing);
#   * 149 declare none and refuse — 66 declare a payload that is NOT in their own
#     text (the lead survives alone: 23 of them were writing an EMPTY node over
#     their target), 37 relabel announcements ("Nåværende § 66 blir § 84."), 37
#     repeal announcements (including ``2025-06-20-88``'s 29-address heading-
#     punctuation announcement, the W-78 shape in a dialect the substitution
#     grammar cannot see), 8 in-place word substitutions and 1 move announcement.
# Not one of the 149 carries statute content; not one of the 68 carries an
# instruction. The separation is the node's own claim, not a shape allowlist.
_NO_STRUCTURED_PAYLOAD_DECLARATION_RE = compile_classifier_regex(
    r"\bskal\b[^:]{0,300}?\b(?:lyde|lyda|lyder|ordlyd)\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.structured_payload_declaration",
)

#: A structured change node whose OWN TEXT would have been written into the
#: statute as a payload, and which declares no payload of its own. Parse-plane,
#: blocking: nothing lands and the reason is typed.
NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED = "no_parse_structured_payload_not_declared"


def _no_structured_payload_is_declared(text: str) -> bool:
    """Whether ``text``'s HEAD declares a payload — W-79's gate, on its own.

    W-82 splits W-79's one question ("does this node declare a payload that is
    also IN its own text?") into the two questions it always was: does the node
    DECLARE a payload, and WHERE does the declared payload live. This is the
    first half and it is unchanged: a payload-introducing operative phrase must
    stand in the head, i.e. before the first colon, and the colon must be there
    to close the declaration.
    """
    head, separator, _tail = _normalize_space(text).partition(":")
    if not separator:
        return False
    # lawvm-regex: owning_parser this IS the structured payload-declaration parser
    return _NO_STRUCTURED_PAYLOAD_DECLARATION_RE.search(head) is not None


def _no_structured_declared_own_payload(text: str) -> Optional[str]:
    """The payload ``text`` declares for itself, or ``None`` when it declares none.

    ``text`` is the change node's own flattened text — exactly what
    :func:`_fallback_payload` would otherwise write. The head (everything before
    the first colon) must carry a payload-introducing operative phrase, and the
    tail must be non-empty; the tail is the payload.
    """
    if not _no_structured_payload_is_declared(text):
        return None
    tail = _normalize_space(_normalize_space(text).partition(":")[2])
    return tail or None


# W-82: the own-text fallback's PAYLOAD REACH.
#
# W-79's gate (above) asks whether the change node DECLARES a payload and reads
# that payload out of the node's own flattened text — the tail after the colon.
# Its census found 66 ops over 43 nodes / 25 instruments that pass the gate and
# still have an EMPTY tail: the declaration is real, but Lovdata put the payload
# in a SIBLING STRUCTURE the flattener never reads, because
# ``_node_text_without_structural_children`` deliberately steps over ``article``
# / ``li`` / ``ol`` / ``ul`` and ``_TEXT_BLOCK_CLASSES`` admits only ``legalP`` /
# ``defaultP`` / ``legalArticleHeader``. Before W-79 those 66 wrote their own LEAD
# into the statute; after it they refuse. This widens WHERE the declared payload
# may live. It does NOT widen the gate: a node that declares nothing still
# refuses, byte for byte.
#
# The reach is granted only to carriers whose EXTENT can be proved from Lovdata's
# OWN machine labels rather than from the amendment's prose — the change node
# carries the target address in ``data-change-part`` / ``data-add-new-part``, and
# the carriers carry ``data-name`` / ``data-numerator``, so the match is
# machine-to-machine. Three carrier shapes are proved and admitted:
#
#   * ``article.futureLegalArticle`` sets (17 ops / 3 nodes) — a whole new chapter
#     announced as one block. Admitted only when the node's section targets and
#     its future-article carriers are in BIJECTION by label (case-folded: Lovdata
#     writes ``§5A-1`` in the carrier and ``§5a-1`` in the address). All or
#     nothing per W-77: one unmatched target refuses every target of the node.
#   * ``span.futuretitle`` (13 ops / 10 nodes) — a subdivision or section heading.
#     For a SECTION target the payload is the heading-only shape
#     ``_heading_only_section_payload`` already builds, behind the SAME
#     ``Overskriften til §`` lead predicate; only the title's LOCATION widens from
#     "a second defaultP article" to "the futuretitle span". For a CHAPTER target
#     the heading is the whole of what a deloverskrift/avsnitt announcement says,
#     so the payload is a chapter carrying that heading and nothing else — and
#     only when the node announces exactly one address and carries no body.
#   * a SINGLE leaf carrier (``li`` or ``article.numberedLegalP``) against a
#     SINGLE non-repeal target whose leaf is BELOW section level (5 ops / 5
#     nodes). Arity one on both sides is the extent proof; where the carrier
#     declares a label of its own it must also name a component of the target's
#     address path, which is what separates "§ 4 tredje ledd nr. 2" (carrier
#     unlabelled, target ``…/nummer/2``) from "§ 18-3 annet ledd bokstav a nr. 4"
#     (carrier ``4.``, target only ``…/bokstav/a`` — the address is a LEVEL
#     SHALLOWER than the declaration and the write would flatten all of bokstav a).
#     The carrier must ALSO be wholly reachable as text: a leaf carrier holding
#     nested structure would land truncated, which is the wrong-text class again.
#
# 35 of the 66 come back that way; the other 31 stay refused under the SAME kind
# — the remainder is not a different failure, it is the same failure: the declared
# payload cannot be proved to belong at the declared address. Sized in the landing
# note (4 carrier-is-the-parent-section, 8 two-targets-one-carrier, 6
# many-carriers-one-target, 4 address-shallower-than-declaration, 3
# carrier-set-misses-the-target-label, 1 carrier-not-wholly-text, 5 no-carrier).
_NO_W82_CONTAINER_LEAF_KINDS = frozenset({"", "section", "chapter", "part"})


def _no_structured_future_title(change_el: etree._Element) -> str:
    """The single ``span.futuretitle`` a change node carries, if it carries one."""
    titles = [
        child
        for child in _direct_children(change_el)
        if _local_name(child) == "span" and "futuretitle" in _classes(child)
    ]
    if len(titles) != 1:
        return ""
    return _normalize_space("".join(str(_t) for _t in titles[0].itertext()))


def _no_structured_carrier_label(carrier: etree._Element) -> str:
    """Lovdata's own label for a leaf payload carrier, normalized ("" when none)."""
    if _local_name(carrier) == "li":
        raw = carrier.get("data-name") or carrier.get("data-li-identifier") or ""
    else:
        raw = carrier.get("data-numerator") or carrier.get("data-name") or ""
    label = _normalize_label(raw)
    return "" if label == "-" else label


def _no_structured_future_section_payload(
    change_el: etree._Element,
    target: LegalAddress,
    declared_specs: Sequence[tuple[StructuralAction, LegalAddress]],
) -> Optional[IRNode]:
    """A declared payload living in ``article.futureLegalArticle`` siblings.

    W-77's extent discipline, applied to Lovdata's machine labels: the node's
    SECTION targets and its future-article carriers must be in bijection by
    case-folded label, or no target of the node is served.
    """
    carriers = [
        child
        for child in _direct_children(change_el, "article")
        if "futureLegalArticle" in _classes(child)
    ]
    if not carriers:
        return None
    by_label: dict[str, etree._Element] = {}
    for carrier in carriers:
        label = _normalize_no_section_label(carrier.get("data-name", "") or "").casefold()
        if not label or label in by_label:
            return None
        by_label[label] = carrier
    section_targets = [
        spec_target
        for _action, spec_target in declared_specs
        if spec_target.leaf_kind() == "section" and spec_target.leaf_label()
    ]
    if len(section_targets) != len(carriers):
        return None
    matched: set[str] = set()
    for spec_target in section_targets:
        key = _normalize_no_section_label(spec_target.leaf_label()).casefold()
        if key not in by_label or key in matched:
            return None
        matched.add(key)
    carrier = by_label.get(_normalize_no_section_label(target.leaf_label() or "").casefold())
    if carrier is None:
        return None
    payload = _parse_future_section(carrier)
    if payload is None or not payload.children:
        return None
    return _with_no_node_label(payload, target.leaf_label() or None)


def _no_structured_future_title_container_payload(
    change_el: etree._Element,
    target: LegalAddress,
    declared_specs: Sequence[tuple[StructuralAction, LegalAddress]],
) -> Optional[IRNode]:
    """A subdivision heading announcement whose title lives in ``span.futuretitle``.

    The announcement ("Kapittel 8 avsnitt III overskriften skal lyde:", "Ny
    deloverskrift til §§ 18-2 til 18-8 skal lyde:") declares a HEADING and nothing
    else, so the payload is a container carrying that heading alone. Refused
    unless the node announces exactly one address and carries no body alongside
    the title — a title that heads a body is a chapter announcement, not a
    heading one, and the body's extent is a different proof.
    """
    if target.leaf_kind() != "chapter" or len(declared_specs) != 1:
        return None
    if any(
        "futureLegalArticle" in _classes(child)
        for child in _direct_children(change_el, "article")
    ):
        return None
    title = _no_structured_future_title(change_el)
    if not title:
        return None
    return IRNode(
        kind=IRNodeKind.CHAPTER,
        label=target.leaf_label() or None,
        children=(IRNode(kind=IRNodeKind.HEADING, text=title),),
    )


def _no_structured_single_leaf_carrier_payload(
    change_el: etree._Element,
    target: LegalAddress,
    declared_specs: Sequence[tuple[StructuralAction, LegalAddress]],
) -> Optional[IRNode]:
    """A declared payload living in the node's ONE ``li`` / ``numberedLegalP``.

    Arity is the extent proof: one carrier, one payload-taking target, and a
    target leaf BELOW section level so a leaf payload can never be written over a
    whole section or chapter. A carrier that declares a label of its own must
    also name a component of the target's address path.
    """
    leaf_kind = target.leaf_kind()
    if leaf_kind in _NO_W82_CONTAINER_LEAF_KINDS:
        return None
    carriers = [
        child
        for child in _direct_children(change_el)
        if _local_name(child) == "li"
        or (_local_name(child) == "article" and "numberedLegalP" in _classes(child))
    ]
    if len(carriers) != 1:
        return None
    payload_specs = [
        spec
        for spec in declared_specs
        if _no_action_value(spec[0]) not in {"repeal", "text_repeal"}
    ]
    if len(payload_specs) != 1:
        return None
    carrier = carriers[0]
    label = _no_structured_carrier_label(carrier)
    if label:
        path_labels = {_normalize_label(part_label).casefold() for _kind, part_label in target.path}
        if label.casefold() not in path_labels:
            return None
    if _local_name(carrier) == "li":
        item = _parse_item(carrier, 1, set())
        text = _normalize_space(item.text or "") if item is not None else ""
    else:
        text = _node_text_without_structural_children(carrier)
        if carrier.get("data-numerator"):
            # lawvm-regex: owning_parser the numbered-subsection numerator strip
            text = _NUMBERED_SUBSECTION_RE.sub("", text, count=1)
        text = _normalize_space(text)
    if not text:
        return None
    # The payload must be WHOLLY reachable as text. A leaf carrier that also holds
    # nested structure (``no/lovtid/2025-06-20-109``'s § 2 nr. 2 is a numerator
    # heading over two ledd, each with its own letter list) would land TRUNCATED to
    # whatever the flattener could see, which is the wrong-text class this lane
    # exists to close. Compare ignoring whitespace: the flattener spaces inline
    # markup apart (``CO<sub>2</sub>`` → ``CO 2``) without dropping anything.
    # The only thing the extractors above ever drop from the FRONT is a numerator,
    # so "wholly reachable" is exactly "the extracted text is a suffix of the
    # carrier's full flattening".
    whole = "".join("".join(str(_t) for _t in carrier.itertext()).split())
    if not whole.endswith("".join(text.split())):
        return None
    return IRNode(
        kind=cast(IRNodeKind, leaf_kind),
        label=target.leaf_label() or None,
        text=text,
    )


def _no_structured_carried_payload(
    change_el: etree._Element,
    action: StructuralAction | str,
    target: LegalAddress,
    declared_specs: Sequence[tuple[StructuralAction, LegalAddress]],
) -> Optional[IRNode]:
    """The declared payload, read from a PROVEN carrier outside the node's own text."""
    if not declared_specs:
        return None
    payload = _no_structured_future_section_payload(change_el, target, declared_specs)
    if payload is not None:
        return payload
    payload = _heading_only_section_payload(change_el, action, target, allow_future_title=True)
    if payload is not None:
        return payload
    payload = _no_structured_future_title_container_payload(change_el, target, declared_specs)
    if payload is not None:
        return payload
    return _no_structured_single_leaf_carrier_payload(change_el, target, declared_specs)


def _fallback_payload(
    change_el: etree._Element,
    action: StructuralAction | str,
    target: LegalAddress,
    *,
    undeclared_out: Optional[list[str]] = None,
    declared_specs: Sequence[tuple[StructuralAction, LegalAddress]] = (),
) -> Optional[IRNode]:
    """The change node's own text as a payload — only when the node declares one.

    ``undeclared_out``, when given, receives the text that WOULD have been
    written for a node that carries text but declares no payload. That is the
    W-79 refusal signal: ``None`` alone cannot distinguish "this node has no text
    to offer" (always been a silent, payload-free op) from "this node's text is an
    instruction" (the wrong-text class), and only the second refuses.

    ``declared_specs`` is every ``(action, target)`` the change node announces.
    W-82 needs it because the extent of a payload carrier is provable only
    against ALL of the node's addresses, not against the one being served; a
    caller that passes none gets W-79's behaviour unchanged.
    """
    if _no_action_value(action) == "repeal":
        return None
    text_blocks = [
        _node_text_without_structural_children(article)
        for article in _direct_children(change_el, "article")
        if _classes(article) & _TEXT_BLOCK_CLASSES
    ]
    text = _normalize_space(" ".join(block for block in text_blocks if block))
    if not text:
        text = _node_text_without_structural_children(change_el)
    if not text:
        return None
    declared = _no_structured_declared_own_payload(text)
    if declared is None:
        if _no_structured_payload_is_declared(text):
            # W-82. The node DOES declare a payload; the tail is empty because the
            # payload is in a sibling structure the flattener steps over. Read it
            # from a carrier whose extent can be proved, or keep refusing.
            carried = _no_structured_carried_payload(change_el, action, target, declared_specs)
            if carried is not None:
                return carried
        if undeclared_out is not None:
            undeclared_out.append(text)
        return None
    return IRNode(
        kind=cast(IRNodeKind, target.leaf_kind() or "content"),
        label=target.leaf_label() or None,
        text=declared,
    )


def parse_no_heading_groups(
    html_bytes: bytes,
    base_id: str,
    *,
    source: Optional[OperationSource] = None,
) -> list[NOHeadingGroup]:
    """Parse Norway section-range heading groups such as 'Ny deloverskrift til §§ 2-1 til 2-5'.

    ``source`` is the affecting-act provenance carrier for the amendment these
    bytes came from; the production caller (``replay_no_to_pit``) passes the
    same ``(statute_id, enacted, effective)`` triple it stamps onto every
    ordinary op of that amendment, so the fold can order groups from different
    amendments by the kernel's temporal key (W-12).
    """
    root = _parse_document(html_bytes)
    raw_base = base_id.removeprefix("no/")
    groups: list[NOHeadingGroup] = []
    sequence = 1

    for doc_change in cast(
        list[etree._Element],
        root.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' document-change ')]"),
    ):
        source_doc = (doc_change.get("data-document") or "").strip()
        if source_doc != raw_base:
            continue
        children = _direct_children(doc_change)
        for idx, child in enumerate(children):
            if "defaultP" not in _classes(child):
                continue
            text = _normalize_space(" ".join(str(_t) for _t in child.itertext()))
            match = _FUTURE_HEADING_RANGE_RE.search(text)
            if not match:
                continue
            title_el = children[idx + 1] if idx + 1 < len(children) else None
            if title_el is None or "futuretitle" not in _classes(title_el):
                continue
            title = _normalize_space(" ".join(str(_t) for _t in title_el.itertext()))
            if not title:
                continue
            start_label = _normalize_label(match.group(1))
            end_label = _normalize_label(match.group(2) or match.group(1))
            groups.append(
                NOHeadingGroup(
                    start_label=start_label,
                    end_label=end_label,
                    title=title,
                    sequence=sequence,
                    source=source,
                )
            )
            sequence += 1

    return groups


# Raw-amendment-source context for the byte-span SourceAnchor program (task
# #92, mirroring the Estonia pilot at estonia/peg.py). The raw Lovdata HTML
# bytes are in scope only at the top entry ``parse_no_amendment_ops`` (every
# per-op clause below it has already been text-flattened via
# ``_normalize_space(" ".join(el.itertext()))`` — exactly the EE flattening
# shape — so the byte/char offset into the raw artifact is lost at the op
# emission sites). Rather than thread ``html_bytes`` through the many
# op-emission call sites and the ``iter_no_document_change_ops`` generator
# contract, the top entry publishes the raw artifact in this ContextVar for the
# duration of one amendment's parse; the uniform provenance post-pass
# (:func:`mint_no_source_anchors`) reads it and mints a TRUE SourceAnchor for
# every op whose recorded clause text survives flattening as a single verbatim,
# unique byte run of the raw artifact. When it does not (clause reconstructed
# across tag boundaries / whitespace-collapsed, or repeated/ambiguous),
# ``compute_source_anchor`` returns None and the anchor is honestly left absent
# — never fabricated.
_NO_RAW_SOURCE_CTX: "contextvars.ContextVar[tuple[str, bytes] | None]" = contextvars.ContextVar(
    "no_raw_source_ctx", default=None
)


def set_no_raw_source_context(
    source_artifact_id: str, raw_bytes: bytes
) -> "contextvars.Token[tuple[str, bytes] | None]":
    """Publish the raw amendment artifact for SourceAnchor minting in this parse.

    Returns a token the caller MUST pass to :func:`reset_no_raw_source_context`
    in a ``finally`` so the context never leaks across amendments.
    """
    return _NO_RAW_SOURCE_CTX.set((source_artifact_id, raw_bytes))


def reset_no_raw_source_context(
    token: "contextvars.Token[tuple[str, bytes] | None]",
) -> None:
    """Clear the raw-source context published by :func:`set_no_raw_source_context`."""
    _NO_RAW_SOURCE_CTX.reset(token)


def mint_no_source_anchors(ops: List[LegalOperation]) -> List[LegalOperation]:
    """Stamp a TRUE byte-span :class:`SourceAnchor` on every anchorable op.

    Final, uniform post-pass over the WHOLE emitted op stream (every mint path),
    run by :func:`parse_no_amendment_ops` once the raw amendment artifact has
    been published in the parse context (see
    :func:`set_no_raw_source_context`).

    For each op that already carries an ``OperationSource`` but no anchor, the
    op's recorded clause text (``source.raw_text`` — falling back to the op's
    ``raw_text``) is located in the raw artifact bytes via
    :func:`lawvm.core.provenance.compute_source_anchor`. The anchor is built on
    that EXACT recorded clause string, so a verifier re-slicing the raw bytes at
    the anchor span gets back precisely the clause text. When the clause is not
    a single verbatim, unique byte run of the artifact (flattened across HTML
    tags, whitespace-collapsed, or repeated/ambiguous), ``compute_source_anchor``
    returns ``None`` and the anchor is honestly left absent — never fabricated.

    Additive metadata only: it touches solely ``source.source_anchor`` and never
    an apply-authoritative field, so NO replay output is byte-identical
    (AGENTS.md §0 grounding-neutral). Idempotent: an op that already carries an
    anchor is left untouched. A no-op when no raw artifact is in context.
    """
    raw_ctx = _NO_RAW_SOURCE_CTX.get()
    if raw_ctx is None or not ops:
        return ops
    artifact_id, raw_bytes = raw_ctx
    anchored: List[LegalOperation] = []
    for op in ops:
        src = op.source
        if src is None or src.source_anchor is not None:
            anchored.append(op)
            continue
        clause = src.raw_text or op.raw_text or ""
        anchor = (
            compute_source_anchor(
                source_artifact_id=artifact_id,
                raw_bytes=raw_bytes,
                clause_text=clause,
            )
            if clause
            else None
        )
        if anchor is None:
            anchored.append(op)
            continue
        anchored.append(dc_replace(op, source=dc_replace(src, source_anchor=anchor)))
    return anchored


def parse_no_amendment_groups(
    html_bytes: bytes,
    source_id: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Parse and source-anchor Lovdata amendment operations grouped by base act."""
    # Publish the raw amendment artifact so the final anchor pass
    # (:func:`mint_no_source_anchors`, applied to the assembled op stream below)
    # can mint a TRUE byte-span SourceAnchor for every op whose recorded clause
    # text survives text-flattening as a verbatim, unique byte run of these
    # bytes (task #92). The token is reset in the finally below so the context
    # never leaks across amendments or to other frontends.
    _raw_source_token = set_no_raw_source_context(source_id, html_bytes)
    try:
        groups = iter_no_document_change_ops(
            html_bytes,
            source_id,
            adjudications_out=adjudications_out,
        )
        # Preserve the base-act grouping replay needs while applying the same
        # uniform anchor pass to every emitted operation.
        return [(base_id, mint_no_source_anchors(doc_ops)) for base_id, doc_ops in groups]
    finally:
        reset_no_raw_source_context(_raw_source_token)


def parse_no_amendment_ops(
    html_bytes: bytes,
    source_id: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> List[LegalOperation]:
    """Parse Lovdata amendment blocks into LegalOperation objects."""
    ops: list[LegalOperation] = []
    for _base_id, doc_ops in parse_no_amendment_groups(
        html_bytes,
        source_id,
        adjudications_out=adjudications_out,
    ):
        ops.extend(doc_ops)
    return ops


# ── W-98: the nine pre-2001 lead productions, one per gap ────────────────────
#
# Every production below is STRICTLY ADDITIVE in W-61's sense: it is reached only
# after every shipped pattern has declined the lead (position in the walk), or it
# is a widening tried only when the shipped reader returned nothing (the two
# reader-level widenings, (a) and (h)). The corpus census for each is in the
# production's own comment, re-derived at the W-98 base pin over 7,853
# ``no_parse_unstructured_lead_unmatched`` refusals harvested UNTRUNCATED.

#: The container kinds whose heading-only REPLACE merges into the standing node
#: instead of replacing it whole. ``section`` is the shipped member; ``chapter``
#: and ``part`` are W-98 (f).
_NO_HEADING_ONLY_MERGE_KINDS = frozenset({"section", "chapter", "part"})


def _no_descendant_section_label_keys(node: IRNode) -> set[str]:
    """Every SECTION label standing anywhere below ``node``, as case-folded keys.

    Sub-containers are walked (a chapter's subdivisions count), sections are not
    (a section's own children are never sections).
    """
    keys: set[str] = set()
    for child in node.children:
        if _no_kind_value(child.kind) == "section":
            if child.label:
                keys.add(_normalize_no_section_label(child.label).casefold())
            continue
        keys |= _no_descendant_section_label_keys(child)
    return keys


# W-98 (a). The repeated-noun ledd list: "§ 7-2 første ledd og tredje ledd skal
# lyde:". The shipped subsection reader splits its ordinal phrase on ``og`` and
# looks each token up in ``_NORWEGIAN_ORDINALS``; a token that still carries the
# noun ("første ledd") is not an ordinal and the whole lead fell through.
#
# Read here ONLY when the shipped reader has returned nothing (the walk tries it
# first), and only when every member but the last carries the noun — the
# single-noun list ("første og tredje ledd") is the shipped grammar's and is
# declined by construction. A NEWNESS MARKER SCOPES OVER ITS OWN MEMBER: in
# "Nytt tredje ledd og fjerde ledd" the repeated noun closes the first noun
# phrase, so ``fjerde ledd`` is the standing fourth ledd (REPLACE), not a second
# new one. The shipped single-noun reader carries a marker forward across the
# list ("nytt tredje og fjerde ledd" → both INSERT), and that difference is the
# grammatical content of the repeated noun, not a divergence between two readers.
#
# Census at the W-98 base pin: 24 refusals / 24 distinct leads / 22 instruments
# / 18 bases read here (4 are the witness's pure shape, "§ 62 femte ledd og
# sjette ledd skal lyde:"; 20 carry a newness marker on one member, "§ 10-1
# første ledd og nytt annet ledd skal lyde:"), plus the 1993 witness; all lower,
# minting 50 ops. Two shipped REPLACEs on ``no/lovtid/2011-06-24-23`` and
# ``2015-08-07-81`` are PROMOTED to INSERT by the shipped
# ``_promote_no_replace_with_following_renumber_insert`` once (h) lowers the
# relabel beside them — the pair the promotion exists for, not a loss.
_NO_REPEATED_LEDD_NOUN_LEAD_PATTERN = (
    r"^§\s*(?P<section>[0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+(?P<members>.+?)\s+ledd\s+(?:skal\s+)?lyde:?$"
)
_NO_LEDD_MEMBER_NEWNESS_PATTERN = r"^(?P<marker>nytt|nye|ny|nåværende|noverande|nåverande)\s+"
_NO_LEDD_MEMBER_INSERT_MARKERS = frozenset({"nytt", "nye", "ny"})


def _no_repeated_ledd_noun_member_specs(
    section_label: str, phrase: str
) -> list[tuple[StructuralAction, LegalAddress]]:
    tokens = [token.strip() for token in re.split(r"\s*,\s*|\s+og\s+", _normalize_space(phrase)) if token.strip()]
    if len(tokens) < 2:
        return []
    # lawvm-regex: owning_parser this IS the repeated-noun member reader
    if not all(re.search(r"\sledd$", token, re.IGNORECASE) for token in tokens[:-1]):
        return []
    specs: list[tuple[StructuralAction, LegalAddress]] = []
    for token in tokens:
        # lawvm-regex: owning_parser strips the noun the pattern above required
        token = re.sub(r"\s+ledd$", "", token, flags=re.IGNORECASE)
        action = StructuralAction.REPLACE
        # lawvm-regex: owning_parser this IS the member newness reader
        marker = re.match(_NO_LEDD_MEMBER_NEWNESS_PATTERN, token, re.IGNORECASE)
        if marker is not None:
            if marker.group("marker").lower() in _NO_LEDD_MEMBER_INSERT_MARKERS:
                action = StructuralAction.INSERT
            token = token[marker.end() :]
        label = _NORWEGIAN_ORDINALS.get(token.strip().lower())
        if not label:
            return []
        specs.append((action, LegalAddress(path=(("section", section_label), ("subsection", label)))))
    return specs


def _no_repeated_ledd_noun_subsection_specs(lead: str) -> list[tuple[StructuralAction, LegalAddress]]:
    """``§ 7-2 første ledd og tredje ledd skal lyde:`` → two REPLACE specs, or ``[]``."""
    # lawvm-regex: owning_parser this IS the repeated-noun ledd lead parser
    match = re.match(_NO_REPEATED_LEDD_NOUN_LEAD_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return []
    return _no_repeated_ledd_noun_member_specs(
        _normalize_no_section_label(match.group("section")), match.group("members")
    )


# W-98 (d), the payload half. A single-item lead ("§ 13-2 tredje ledd bokstav a
# skal lyde:") followed by ONE ``legalP`` carrying the item's new text and no
# ``li`` carrier at all. The shipped candidate builder reads items only off
# ``li`` elements, so this shape resolved its address and then refused
# ``no_parse_unstructured_payload_unresolved`` / ``item``: 68 such refusals at
# the W-98 base pin, every one of them this shape, plus the 1994 witness.
#
# Arity is the extent proof, exactly as W-82's single-leaf carrier states it:
# one declared item, one text article, no item candidate of any label. A
# ``siste``/``last`` address is declined (a counted address is the shipped
# lane's), and so is a multi-item lead (W-32(a)'s all-or-nothing rule owns it).
def _no_item_payload_from_single_text_article(
    item_specs: Sequence[tuple[StructuralAction, LegalAddress]],
    target: LegalAddress,
    payload_candidates: Mapping[tuple[str, str], IRNode],
    text_articles: Sequence[etree._Element],
) -> Optional[IRNode]:
    if len(item_specs) != 1 or len(text_articles) != 1:
        return None
    label = target.leaf_label()
    if target.leaf_kind() != "item" or not label or label == "last":
        return None
    if any(kind == "item" for kind, _label in payload_candidates):
        return None
    text = _node_text_without_structural_children(text_articles[0])
    if not text:
        return None
    return IRNode(kind=IRNodeKind.ITEM, label=label, text=text)


# W-98 (b). The mixed member list: "§ 2-5 første ledd første punktum og andre
# ledd skal lyde:" — one lead, members at TWO depths, one payload article per
# member in document order. The shipped sentence reader requires every member
# to be a punktum and the shipped subsection reader requires every member to be
# a ledd, so the mixed list matched neither and fell through.
#
# Each member is read on its own: ``[<marker>] <ord> ledd`` or ``<ord> ledd
# [<marker>] <ord|siste> punktum``; a newness marker scopes over its own member
# (INSERT), the default is REPLACE. The list must carry at least one member of
# EACH depth — a homogeneous list is the shipped grammar's and is declined by
# construction — and the payload must carry exactly one text article per
# member, or the whole lead refuses with a typed arity receipt (W-19's
# all-or-nothing rule: a payload that does not split to the declared arity
# gives no evidence which half belongs where).
#
# Census at the W-98 base pin: 8 refusals / 8 distinct leads / 7 instruments /
# 8 bases carry a punktum member beside a ledd member, plus the 2000 witness;
# 7 lower and 1 refuses on arity (``no/lovtid/2012-06-22-35``, whose second
# member's payload is a ``defaultP`` the boundary does not hand over).
_NO_MIXED_MEMBER_LEAD_PATTERN = (
    r"^§\s*(?P<section>[0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+(?P<members>.+?)\s+skal\s+lyde:?$"
)
_NO_MIXED_LEDD_MEMBER_PATTERN = (
    r"^(?:(?P<marker>nytt|nye|ny|nåværende|noverande|nåverande)\s+)?(?P<ledd>[A-Za-zÆØÅæøå]+)\s+ledd$"
)
_NO_MIXED_PUNKTUM_MEMBER_PATTERN = (
    r"^(?P<ledd>[A-Za-zÆØÅæøå]+)\s+ledd\s+"
    r"(?:(?P<marker>nytt|nye|ny|nåværende|noverande|nåverande)\s+)?(?P<punktum>[A-Za-zÆØÅæøå]+)\s+punktum$"
)


def _no_mixed_punktum_ledd_member_specs(lead: str) -> list[tuple[StructuralAction, LegalAddress]]:
    """``§ 2-5 første ledd første punktum og andre ledd skal lyde:`` → a sentence spec and a ledd spec."""
    # lawvm-regex: owning_parser this IS the mixed-depth member lead parser
    match = re.match(_NO_MIXED_MEMBER_LEAD_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return []
    section_label = _normalize_no_section_label(match.group("section"))
    tokens = [token.strip() for token in re.split(r"\s*,\s*|\s+og\s+", match.group("members")) if token.strip()]
    specs: list[tuple[StructuralAction, LegalAddress]] = []
    has_punktum = False
    has_ledd = False
    for token in tokens:
        # lawvm-regex: owning_parser this IS the mixed-depth punktum member reader
        punktum_member = re.match(_NO_MIXED_PUNKTUM_MEMBER_PATTERN, token, re.IGNORECASE)
        if punktum_member is not None:
            ledd_label = _NORWEGIAN_ORDINALS.get(punktum_member.group("ledd").lower())
            punktum_word = punktum_member.group("punktum").lower()
            punktum_label = "last" if punktum_word == "siste" else _NORWEGIAN_ORDINALS.get(punktum_word)
            if not ledd_label or not punktum_label:
                return []
            marker = (punktum_member.group("marker") or "").lower()
            action = StructuralAction.INSERT if marker in _NO_LEDD_MEMBER_INSERT_MARKERS else StructuralAction.REPLACE
            specs.append(
                (
                    action,
                    LegalAddress(
                        path=(("section", section_label), ("subsection", ledd_label), ("sentence", punktum_label))
                    ),
                )
            )
            has_punktum = True
            continue
        # lawvm-regex: owning_parser this IS the mixed-depth ledd member reader
        ledd_member = re.match(_NO_MIXED_LEDD_MEMBER_PATTERN, token, re.IGNORECASE)
        if ledd_member is None:
            return []
        ledd_label = _NORWEGIAN_ORDINALS.get(ledd_member.group("ledd").lower())
        if not ledd_label:
            return []
        marker = (ledd_member.group("marker") or "").lower()
        action = StructuralAction.INSERT if marker in _NO_LEDD_MEMBER_INSERT_MARKERS else StructuralAction.REPLACE
        specs.append((action, LegalAddress(path=(("section", section_label), ("subsection", ledd_label)))))
        has_ledd = True
    if not (has_punktum and has_ledd):
        return []
    return specs


# W-98 (e). The compound lead: "§ 1-1 tredje ledd oppheves. Nytt tredje ledd og
# fjerde ledd skal lyde:" — a ledd repeal and a re-enactment in one lead, the
# payload carrying one article per re-enacted member. The shipped two-sentence
# reader is the repeal-then-SHIFT lead (W-61); this is repeal-then-PAYLOAD, and
# nothing shipped reads it.
#
# The repeal ordinals go through ``_no_ledd_shift_ordinals`` (one ordinal
# grammar), the re-enactment through the shipped subsection reader with the
# repeated-noun reader (a) behind it. The kernel's stage order lands the REPEAL
# before either payload op, so an INSERT into the repealed slot finds it vacant
# by construction; an INSERT into any OTHER slot carries the production's
# provenance tag and REFUSES if that slot is occupied, rather than take the θ
# (INSERT, target_occupied) recovery — a re-enactment must not clear a ledd the
# lead never repealed.
#
# Census at the W-98 base pin: ZERO corpus refusals — this is a print-era
# drafting shape the 2001+ Lovdata corpus does not carry; the 2000 witness is
# its only occurrence. Lowered because it is one closed composition of two
# shipped readers, with the synthetic test as its regression.
_NO_LEDD_REPEAL_REENACT_LEAD_PATTERN = (
    r"^§\s*(?P<section>[0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+(?P<repealed>.+?)\s+ledd\s+"
    r"(?:oppheves|opphevast|(?:vert|blir)\s+oppheva)\.\s+"
    r"(?P<reenact>ny(?:tt|e)?\s+.+?\s+ledd\s+skal\s+lyde:?)$"
)


def _no_ledd_repeal_reenact_specs(
    lead: str,
) -> Optional[tuple[str, list[int], list[tuple[StructuralAction, LegalAddress]]]]:
    """→ ``(section_label, [repealed ordinal, …], [(action, target), …])`` or ``None``."""
    # lawvm-regex: owning_parser this IS the compound repeal-then-reenact lead parser
    match = re.match(_NO_LEDD_REPEAL_REENACT_LEAD_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    section_label = _normalize_no_section_label(match.group("section"))
    repealed = _no_ledd_shift_ordinals(match.group("repealed"))
    if not repealed or len(set(repealed)) != len(repealed):
        return None
    reenact_lead = f"§ {section_label} {match.group('reenact')}"
    specs = _infer_same_base_subsection_target_specs_from_lead(reenact_lead) or _no_repeated_ledd_noun_subsection_specs(
        reenact_lead
    )
    if not specs:
        return None
    return section_label, repealed, specs


# W-98 (i). The nynorsk ledd repeal: "§ 6-1 tredje ledd vert oppheva.", "… blir
# oppheva.", "… opphevast." The shipped bokmål branch is anchored on the literal
# ``oppheves`` and deliberately NOT widened — it round-trips its ordinals
# through the ``skal lyde`` reader and mints nothing, silently, on an ordinal
# that reader cannot name (``siste ledd``). Widening its verb would turn the
# loud refusal these nynorsk leads carry today into that silent drop. This
# production reads through ``_no_ledd_shift_ordinals`` instead and DECLINES on
# anything outside the vocabulary, so the refusal survives.
#
# Census at the W-98 base pin: 35 refusals / 34 distinct leads / 30 instruments
# / 26 bases carry a nynorsk repeal verb behind ``ledd``; 28 lower, 7 decline
# (``siste ledd``, a punktum member beside the ledd, a ``nr.`` container) and
# keep their refusal.
_NO_NYNORSK_LEDD_REPEAL_PATTERN = (
    r"^§\s*(?P<section>[0-9A-Za-z-]+(?:\s+[A-Za-z])?)\s+"
    r"(?:(?:" + _NO_CURRENCY_QUALIFIER_ALTERNATION + r")\s+)?"
    r"(?P<ordinals>.+?)\s+ledd\s+(?:opphevast|(?:vert|blir)\s+oppheva)\.?$"
)


def _no_nynorsk_ledd_repeal_targets(lead: str) -> Optional[tuple[str, list[int]]]:
    """``§ 6-1 tredje ledd vert oppheva.`` → ``("6-1", [3])``, or ``None``."""
    # lawvm-regex: owning_parser this IS the nynorsk ledd repeal lead parser
    match = re.match(_NO_NYNORSK_LEDD_REPEAL_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    ordinals = _no_ledd_shift_ordinals(match.group("ordinals"))
    if not ordinals or len(set(ordinals)) != len(ordinals):
        return None
    return _normalize_no_section_label(match.group("section")), ordinals


# W-98 (c), the lead half. The section range spelled with a ``§`` on BOTH ends
# ("§ 5-1 til § 5-6 oppheves.") or with a nynorsk verb ("§§ 36 til 38 blir
# oppheva."). The shipped production reads exactly ``§§ A til B oppheves.`` and
# is tried first; this one is reached only when it has declined. Expansion goes
# through ``_expand_no_section_range_labels`` (one range grammar).
#
# Census at the W-98 base pin: 3 refusals / 3 distinct leads / 3 instruments /
# 3 bases, plus the 1998 witness; all lower.
_NO_SECTION_RANGE_REPEAL_LEAD_PATTERN = (
    r"^§§?\s*(?P<start>[0-9][0-9A-Za-z-]*)\s+til\s+§?\s*(?P<end>[0-9][0-9A-Za-z-]*)\s+"
    r"(?:oppheves|opphevast|(?:vert|blir)\s+oppheva)\.?$"
)


def _no_section_range_repeal_lead(lead: str) -> Optional[tuple[str, str]]:
    # lawvm-regex: owning_parser this IS the widened section-range repeal lead parser
    match = re.match(_NO_SECTION_RANGE_REPEAL_LEAD_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    return match.group("start"), match.group("end")


# W-98 (h). The self-addressed, unqualified single-ledd shift: "§ 2-1 sjette
# ledd blir nytt fjerde ledd." W-66 REQUIRED the currency qualifier and sized
# the unqualified form at 55 leads without taking it, on the ground that a bare
# "Femte ledd blir nytt sjette ledd." does not say which edition its ordinals
# are read against. That ground has two halves, and this production takes only
# the lead shape where both are closed:
#
#   * the SECTION is spelled in the lead, so nothing is inherited from an
#     antecedent that might be a payload announcement (W-66b's hazard);
#   * the source is ONE ordinal, so there is exactly one standing ledd it can
#     name; the kernel's stage order (REPEAL, then RENUMBER, then everything
#     else) evaluates it against the pre-operation snapshot by construction, and
#     W-66's occupied-destination guard — the ops carry W-66's provenance tag —
#     turns any reading that would land on a standing sibling into a typed
#     refusal instead of a destruction.
#
# The result feeds W-66's own walk block unchanged: same address handling, same
# ordering, same tag, same apply-plane guard. ``pattern`` is
# ``"unqualified_self_addressed"`` so a census can tell the three attempts apart.
#
# Census at the W-98 base pin: 25 refusals / 24 distinct leads / 24 instruments
# / 21 bases, every one section-spelled and single-ordinal on both sides, plus
# the 1993 witness; all lower at the parse plane.
_NO_UNQUALIFIED_LEDD_SHIFT_PATTERN = (
    r"^§\s*(?P<section>" + _NO_SET_RELABEL_SECTION_LABEL + r")\s+"
    r"(?P<source>[A-Za-zÆØÅæøå]+)\s+ledd\s+blir\s+(?:ny(?:tt|e)?\s+)?(?P<destination>[A-Za-zÆØÅæøå]+)\s+ledd\.?$"
)


def _no_unqualified_self_addressed_ledd_shift(lead: str) -> Optional[tuple[str, list[tuple[int, int]], str]]:
    # lawvm-regex: owning_parser this IS the unqualified self-addressed ledd shift parser
    match = re.match(_NO_UNQUALIFIED_LEDD_SHIFT_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    source = _NORWEGIAN_ORDINALS.get(match.group("source").lower())
    destination = _NORWEGIAN_ORDINALS.get(match.group("destination").lower())
    if source is None or destination is None or source == destination:
        return None
    return (
        _normalize_no_section_label(match.group("section")),
        [(int(source), int(destination))],
        "unqualified_self_addressed",
    )


# W-98 (f) and (g). Chapter-level leads.
#
# A chapter label as Lovtidend spells it: decimal with an optional letter
# ("5", "5 A", "9a") or roman with an optional letter ("VI", "II a"). Spaces are
# removed for the address, as ``_normalize_no_section_label`` does for sections;
# case is left as spelled and folded by the resolver's label match.
_NO_CHAPTER_LABEL = r"(?:[0-9]+(?:\s?[A-Za-z])?|[IVXLC]+(?:\s?[A-Za-z])?)"
_NO_CHAPTER_WORD = r"kapit(?:tel|let|tlet)"


def _normalize_no_chapter_label(label: str) -> str:
    return _normalize_label(label).replace(" ", "")


# (f) The chapter heading lead, both word orders and both nynorsk spellings:
# "Overskriften til kapittel 3 skal lyde:", "Overskrifta til kapittel 2 skal
# lyde:", "Overskriften i kapittel 8 skal lyde:", "Kapittel 4 overskriften skal
# lyde:". The title is either INLINE after the colon or the ONE node that
# follows the lead (a ``defaultP`` the W-64 boundary now hands over for this
# lead, a ``legalP`` on the witness, a ``span.futuretitle``). It lands as a
# heading-only CHAPTER payload, which the apply seam merges into the standing
# chapter's heading — the chapter's sections are never touched by a heading
# announcement.
#
# Census at the W-98 base pin: 181 refusals / 97 distinct leads / 126
# instruments / 91 bases read here (87 spell ``Overskrift… kapittel``, the rest
# ``Kapittel N overskriften``), plus the 2000 witness; every one lowers, 182
# heading-only CHAPTER ops. The one lead with a placement aside ("…, plassert
# umiddelbart foran § 17a, skal lyde:") declines and keeps its refusal.
_NO_CHAPTER_HEADING_LEAD_PATTERNS = (
    r"^Overskrift(?:en|a)\s+(?:til|i)\s+" + _NO_CHAPTER_WORD + r"\s+(?P<label>" + _NO_CHAPTER_LABEL + r")"
    r"\s+skal\s+(?:lyde|lyda):?\s*(?P<inline>.*)$",
    r"^" + _NO_CHAPTER_WORD + r"\s+(?P<label>" + _NO_CHAPTER_LABEL + r")\s+overskrift(?:en|a)"
    r"\s+skal\s+(?:lyde|lyda):?\s*(?P<inline>.*)$",
)


def _no_chapter_heading_lead(lead: str) -> Optional[tuple[str, str]]:
    """``Overskriften til kapittel 3 skal lyde:`` → ``("3", "")``; inline title in the second slot."""
    normalized = _normalize_space(lead)
    for pattern in _NO_CHAPTER_HEADING_LEAD_PATTERNS:
        # lawvm-regex: owning_parser this IS the chapter heading lead parser
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match is not None:
            return _normalize_no_chapter_label(match.group("label")), _normalize_space(match.group("inline"))
    return None


@dataclass(frozen=True, slots=True)
class _NOChapterHeadingRead:
    """The chapter heading a lead announces: the title, where the lead's reach ends, or a typed refusal."""

    title: str
    end_index: int
    refusal: str


def _no_chapter_heading_read(
    children: Sequence[etree._Element],
    part_indexes: Sequence[int],
    position: int,
    inline_title: str,
) -> _NOChapterHeadingRead:
    """Read the title off the DOM: inline after the colon, or EXACTLY ONE title node after the lead.

    Read from the DOM rather than from the walk's ``payload_nodes`` because the
    walk's cursor stops on the ``defaultP`` Lovdata marks the title with, and
    W-64's boundary hands that node over only under its section-heading length
    bound (80 chars), which chapter titles routinely exceed. The arity is still
    the proof: the node after the title must be a lead, a section carrier or the
    part's end — a second body node means the announcement carries more than a
    heading, and the whole lead refuses.
    """
    part = part_indexes[position] if position < len(part_indexes) else None

    def node_at(index: int) -> Optional[etree._Element]:
        if index >= len(children) or (part_indexes[index] if index < len(part_indexes) else None) != part:
            return None
        return children[index]

    following = node_at(position + 1)
    following_text = (
        _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in following.itertext())))
        if following is not None
        else ""
    )
    if inline_title:
        if following is not None and _no_chapter_title_text(following, following_text):
            return _NOChapterHeadingRead(title="", end_index=position + 1, refusal="inline_title_with_trailing_title")
        return _NOChapterHeadingRead(title=inline_title, end_index=position + 1, refusal="")
    if following is None or not _no_chapter_title_text(following, following_text):
        return _NOChapterHeadingRead(title="", end_index=position + 1, refusal="payload_is_not_a_heading")
    after_title = node_at(position + 2)
    if after_title is not None:
        after_name = _local_name(after_title)
        after_classes = _classes(after_title) if after_name == "article" else set()
        if not (
            after_name == "article"
            and ({"defaultP", "futureLegalArticle"} & after_classes)
        ):
            return _NOChapterHeadingRead(title="", end_index=position + 1, refusal="payload_node_count_not_one")
    return _NOChapterHeadingRead(title=following_text, end_index=position + 2, refusal="")


# (g) The whole-chapter re-enactment: "Kapittel 6 skal lyde:" (REPLACE) and
# "Nytt kapittel 5 A skal lyde:" (INSERT). The payload is the chapter's new text
# and it is read off the DOM from the lead forward, because the walk's payload
# cursor stops at the next ``defaultP`` and Lovdata's chapter payload shapes
# all put a ``defaultP`` right there:
#
#   * a chapter title — ``defaultP`` ("Kapittel 9. Forskjellige bestemmelser"),
#     ``span.futuretitle``, or the ``<h2>`` the print-era emitter writes;
#   * then sections, as ``futureLegalArticle`` carriers (2002 onward) or as the
#     2001 shape: a ``defaultP`` header "§ 5B-1. (Energiplanlegging)" followed by
#     that section's ``legalP``/``numberedLegalP`` ledd.
#
# The reader walks members in that CLOSED SET until the first ``defaultP`` it
# does not own — an operative lead, or a ``§`` lead that is not a bare section
# header — which ends the payload without being consumed. Anything else
# (a second title once sections have started = a subdivision this reader does
# not model; body text with no section open; a carrier without a label) REFUSES
# the whole lead with a typed receipt naming the member (W-39's all-or-nothing
# rule: a partially read chapter is a wrong chapter, not a partial one).
#
# THE OVER-REPEAL DECISION lives at the apply seam, not here, because it needs
# the tree: a REPLACE lands only when every section standing under the chapter
# is carried by the payload (``NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_
# REFUSED`` otherwise), and an INSERT refuses an occupied chapter label
# (``NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED``) rather than take
# the θ recovery that would replace the standing chapter.
#
# Census at the W-98 base pin: 149 refusals / 97 distinct leads / 119
# instruments / 80 bases read here, plus the 1996 and 1998 witnesses. 124 lower
# (86 leads, 76 bases — 62 REPLACE, 62 INSERT) and 25 refuse typed: 14
# ``subdivision_heading_unsupported`` (a chapter with ``I.``/``II.`` avsnitt), 6
# ``chapter_carried_no_section`` (a ``Nytt kapittel`` whose sections follow as
# leads of their own), 5 ``body_outside_section`` (folketrygdloven's chapter
# index paragraph, text the CHAPTER node does not model). The apply-plane
# guard is exercised by the 1996 witness: its OCR-fused payload carries only
# § 6-1 of §§ 6-1–6-5 and is refused with the four uncarried labels named.
_NO_CHAPTER_REENACTMENT_LEAD_PATTERN = (
    r"^(?P<insert>Nytt\s+)?" + _NO_CHAPTER_WORD + r"\s+(?P<label>" + _NO_CHAPTER_LABEL + r")\s+skal\s+(?:lyde|lyda):?$"
)
# The 2001-shape section header: "§ 5B-1. (Energiplanlegging)", "§ 9 c. Virkeområde",
# "§ 5A-3. (Leveringskvalitet)". The label class admits a letter INSIDE a
# chapter-numbered label (``5A-3``) and a single-letter suffix that must not be
# the first letter of the title (``(?![A-Za-zÆØÅæøå])``).
_NO_CHAPTER_SECTION_HEADER_PATTERN = (
    r"^§\s*(?P<label>[0-9]+(?:\s?[A-Za-z](?![A-Za-zÆØÅæøå]))?"
    r"(?:-[0-9]+(?:\s?[A-Za-z](?![A-Za-zÆØÅæøå]))?)*)\s*\.?\s*(?P<title>.*)$"
)
_NO_CHAPTER_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4"})
_NO_CHAPTER_SECTION_BODY_CLASSES = frozenset({"legalP", "numberedLegalP"})
_NO_CHAPTER_TITLE_ARTICLE_CLASSES = frozenset({"defaultP", "legalP"})
#: W-64's section-heading bound is 80 characters, measured on section titles.
#: Chapter titles run longer — the longest of the 182 heading announcements in
#: the corpus is 210 characters ("Kapittel 8. Særlige regler for utlendinger som
#: omfattes av Avtale om Det europeiske økonomiske samarbeidsområde …") and four
#: exceed 80 — so the chapter bound is set above the measured maximum. The
#: length clause is the weakest of the four; the ``§``, verb and punctuation
#: clauses carry the discrimination.
_NO_CHAPTER_TITLE_MAX_LEN = 240


def _no_chapter_title_text(node: etree._Element, text: str) -> bool:
    """Is this node a chapter TITLE — a bare noun phrase, never an instruction or body text?

    W-64's discriminator clauses, reused member for member: a title carries no
    ``§``, no operative verb, no sentence-final punctuation and is at most
    ``_NO_CHAPTER_TITLE_MAX_LEN`` long. ``<h1>``–``<h4>`` and ``span.futuretitle``
    are titles by markup; a ``defaultP`` or ``legalP`` is a title only by these
    clauses — the ``legalP`` case is the print-era emitter's, which has no
    heading class to write and marks a non-lead line ``legalP``.
    """
    name = _local_name(node)
    classes = _classes(node) if name in {"article", "span"} else set()
    if name in _NO_CHAPTER_HEADING_TAGS or (name == "span" and "futuretitle" in classes):
        return bool(text)
    if name != "article" or not (_NO_CHAPTER_TITLE_ARTICLE_CLASSES & classes):
        return False
    if not text or len(text) > _NO_CHAPTER_TITLE_MAX_LEN:
        return False
    if "§" in text or text[-1] in ":;,":
        return False
    return not _no_unstructured_lead_looks_operative(text)


def _no_chapter_reenactment_lead(lead: str) -> Optional[tuple[str, StructuralAction]]:
    """``Kapittel 6 skal lyde:`` → ``("6", REPLACE)``; ``Nytt kapittel 5 A skal lyde:`` → ``("5A", INSERT)``."""
    # lawvm-regex: owning_parser this IS the chapter re-enactment lead parser
    match = re.match(_NO_CHAPTER_REENACTMENT_LEAD_PATTERN, _normalize_space(lead), re.IGNORECASE)
    if match is None:
        return None
    action = StructuralAction.INSERT if match.group("insert") else StructuralAction.REPLACE
    return _normalize_no_chapter_label(match.group("label")), action


@dataclass(frozen=True, slots=True)
class _NOChapterReenactmentRead:
    """What the chapter payload reader found: a payload and where it ended, or a typed refusal."""

    payload: Optional[IRNode]
    end_index: int
    refusal: str
    member: str


def _no_chapter_reenactment_section_from_header(
    label: str, title: str, body_nodes: Sequence[etree._Element]
) -> Optional[IRNode]:
    """The 2001 shape: a ``§ X. Title`` header and its body articles, as one section."""
    synthetic = etree.Element("article")
    synthetic.set("class", "futureLegalArticle")
    synthetic.set("data-name", f"§{label}")
    header_span = etree.SubElement(synthetic, "span")
    header_span.set("class", "futureLegalArticleHeader")
    header_span.text = f"§ {label}. {title}".strip()
    for node in body_nodes:
        synthetic.append(copy.deepcopy(node))
    payload = _parse_future_section(synthetic)
    if payload is None or (not payload.children and not _normalize_space(payload.text or "")):
        return None
    return payload


def _no_chapter_reenactment_payload(
    children: Sequence[etree._Element],
    part_indexes: Sequence[int],
    position: int,
    chapter_label: str,
    action: StructuralAction,
) -> _NOChapterReenactmentRead:
    part = part_indexes[position] if position < len(part_indexes) else None
    heading: Optional[str] = None
    sections: list[IRNode] = []
    seen_labels: set[str] = set()
    open_label: Optional[str] = None
    open_title = ""
    open_body: list[etree._Element] = []

    def refuse(reason: str, member: str, index: int) -> _NOChapterReenactmentRead:
        return _NOChapterReenactmentRead(payload=None, end_index=index, refusal=reason, member=member[:200])

    def flush() -> Optional[str]:
        nonlocal open_label, open_title, open_body
        if open_label is None:
            return None
        section = _no_chapter_reenactment_section_from_header(open_label, open_title, open_body)
        label_key = open_label.casefold()
        open_label, open_title, open_body = None, "", []
        if section is None:
            return "section_payload_unresolved"
        if label_key in seen_labels:
            return "duplicate_section_label"
        seen_labels.add(label_key)
        sections.append(section)
        return None

    index = position + 1
    while index < len(children) and (part_indexes[index] if index < len(part_indexes) else None) == part:
        node = children[index]
        name = _local_name(node)
        text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
        classes = _classes(node) if name in {"article", "span"} else set()
        # A title is read ONLY before the first section; the same shape after a
        # section has started is a subdivision heading this reader does not
        # model, and refuses. A ``legalP`` is tested as a title only in that
        # first position — once a section is open it is that section's body.
        if heading is None and not sections and open_label is None and _no_chapter_title_text(node, text):
            heading = text
            index += 1
            continue
        if (
            name in _NO_CHAPTER_HEADING_TAGS
            or (name == "span" and "futuretitle" in classes)
            or (name == "article" and "defaultP" in classes and _no_chapter_title_text(node, text))
        ):
            return refuse("subdivision_heading_unsupported", text, index)
        if name == "article" and "futureLegalArticle" in classes:
            flushed = flush()
            if flushed is not None:
                return refuse(flushed, text, index)
            label = _no_future_section_label(node)
            if not label:
                return refuse("future_section_without_label", text, index)
            section = _parse_future_section(node)
            if section is None or (not section.children and not _normalize_space(section.text or "")):
                return refuse("section_payload_unresolved", text, index)
            if label.casefold() in seen_labels:
                return refuse("duplicate_section_label", text, index)
            seen_labels.add(label.casefold())
            sections.append(section)
            index += 1
            continue
        if name == "article" and "defaultP" in classes:
            # lawvm-regex: owning_parser this IS the 2001-shape section header reader
            header = re.match(_NO_CHAPTER_SECTION_HEADER_PATTERN, text)
            if header is not None and not _no_unstructured_lead_looks_operative(text):
                flushed = flush()
                if flushed is not None:
                    return refuse(flushed, text, index)
                open_label = _normalize_no_section_label(header.group("label"))
                open_title = _normalize_space(header.group("title"))
                index += 1
                continue
            break
        if name == "article" and (_NO_CHAPTER_SECTION_BODY_CLASSES & classes):
            if open_label is None:
                return refuse("body_outside_section", text, index)
            open_body.append(node)
            index += 1
            continue
        return refuse("member_outside_closed_set", f"<{name}> {text}", index)
    flushed = flush()
    if flushed is not None:
        return refuse(flushed, "", index)
    if not sections:
        # A title and nothing else. Measured (10 corpus leads): the chapter's
        # sections follow as leads of their OWN ("§ 30 skal lyde:", "Ny § 10-5
        # skal lyde:") which the walk lowers independently, so the lead itself
        # states only the heading. For a REPLACE that is exactly a heading-only
        # payload, which the apply seam MERGES over the standing chapter (its
        # sections are never touched). For an INSERT it would be an empty
        # container whose sections this reader cannot prove belong to it, so
        # it refuses.
        if heading is None or action is not StructuralAction.REPLACE:
            return refuse("chapter_carried_no_section", "", index)
    payload_children: list[IRNode] = []
    if heading:
        payload_children.append(IRNode(kind=IRNodeKind.HEADING, text=heading))
    payload_children.extend(sections)
    return _NOChapterReenactmentRead(
        payload=IRNode(kind=IRNodeKind.CHAPTER, label=chapter_label, children=tuple(payload_children)),
        end_index=index,
        refusal="",
        member="",
    )


def _iter_unstructured_no_change_groups(
    root: etree._Element,
    source_id: str,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Parse older Lovtidend amendment acts without ``document-change`` wrappers."""
    # Function-local: sources.py imports from grafter at module load, so the
    # shared declared-target reader is only reachable from inside the function.
    from lawvm.norway.sources import declared_change_targets_from_root

    changed_docs = declared_change_targets_from_root(root).law_ids
    default_base_id = changed_docs[0] if len(changed_docs) == 1 else None

    sequence = 1
    doc_ops_by_base: dict[str, list[LegalOperation]] = {}
    all_sections = cast(list[etree._Element], root.xpath("//main/section"))
    kapi_sections = [section for section in all_sections if (section.get("data-name") or "").lower() == "kapi"]
    seen_sections = {id(section) for section in kapi_sections}
    sections = kapi_sections + [section for section in all_sections if id(section) not in seen_sections]
    if sections:
        children = []
        section_base_ids: list[str | None] = []
        # Which flattened ``<section>`` (part) each child came from. Parts are a
        # law boundary in this grammar ("I ... II I lov X ... gjøres følgende
        # endringer:"), so the walk below needs to see the boundary the flatten
        # would otherwise erase.
        child_part_indexes: list[int] = []
        # The base act each part resolved from its own lead, indexed by part.
        part_base_ids: list[str | None] = []
        for part_index, section in enumerate(sections):
            section_children: list[etree._Element] = []
            section_child_base_ids: list[str | None] = []
            direct_children = _direct_children(section)
            section_base_id = _infer_no_unstructured_section_base_id(direct_children)
            part_base_ids.append(section_base_id)
            for direct_child in direct_children:
                if _local_name(direct_child) == "article" and "legalArticle" in _classes(direct_child):
                    article_children = _direct_children(direct_child)
                    section_children.extend(article_children)
                    section_child_base_ids.extend([None] * len(article_children))
                    continue
                section_children.append(direct_child)
                section_child_base_ids.append(section_base_id)
            children.extend(section_children)
            section_base_ids.extend(section_child_base_ids)
            child_part_indexes.extend([part_index] * len(section_children))
    else:
        mains = cast(list[etree._Element], root.xpath("//main"))
        if not mains:
            return []
        children = []
        section_base_ids = []
        child_part_indexes = []
        part_base_ids = [None]
        for container in _direct_children(mains[0]):
            if _local_name(container) != "article":
                continue
            if "legalArticle" in _classes(container):
                direct_children = _direct_children(container)
                children.extend(direct_children)
                section_base_ids.extend([None] * len(direct_children))
                child_part_indexes.extend([0] * len(direct_children))
            else:
                children.append(container)
                section_base_ids.append(None)
                child_part_indexes.append(0)

    # W-36 before W-35: a run-on hiding inside a ``futureLegalArticle``'s payload
    # has to become an ordinary trapped lead before the trapped pass can lift it
    # the rest of the way out. Both passes are monotone — each split removes the
    # boundary it fired on — so this reaches a fixpoint. The second turn is not
    # decoration: corpus-wide it fires exactly once, on `2016-06-17-29`, where a
    # lead the trapped pass frees is itself a run-on carrying item 11.
    while (
        _split_no_run_on_lead_nodes(children, section_base_ids, child_part_indexes)
        + _split_no_trapped_payload_leads(children, section_base_ids, child_part_indexes)
    ):
        pass

    def _part_index(position: int) -> int | None:
        return child_part_indexes[position] if position < len(child_part_indexes) else None

    # W-39, half (i). A collective re-enactment part is lowered as ONE unit
    # before the ordinary lead walk starts, because its members are not leads:
    # the announcement states the end state and the sections that follow are
    # bare ``futureLegalArticle`` siblings, which the lead/payload cursor reads
    # as the announcement's payload and drops. The pre-pass runs after the
    # run-on/trapped fixpoint above so it sees the same node list the walk does.
    #
    # A part the pre-pass refuses is handed back to the walk EXACTLY as it stood
    # before this production existed: its ``part_base_ids`` entry is cleared so
    # the collective resolver added to ``_infer_no_unstructured_section_base_id``
    # cannot seed ``active_base_id`` for a part whose members were never
    # adjudicated, and the walk reproduces its prior receipts unchanged.
    consumed_part_indexes: set[int] = set()
    collective_part_indexes = [
        part_index
        for part_index, part_base_id in enumerate(part_base_ids)
        if part_base_id is not None
        and any(
            _no_collective_reenactment_lead_base_id(
                _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
            )
            is not None
            for position, node in enumerate(children)
            if _part_index(position) == part_index
            and _local_name(node) == "article"
            and ({"defaultP", "legalP"} & _classes(node))
        )
    ]
    for part_index in collective_part_indexes:
        part_base_id = part_base_ids[part_index]
        assert part_base_id is not None
        part_children = [
            node
            for position, node in enumerate(children)
            if _part_index(position) == part_index
            and _no_collective_reenactment_lead_base_id(
                _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
            )
            is None
        ]
        lowered = _lower_no_collective_reenactment_part(
            part_children,
            source_id=source_id,
            base_id=part_base_id,
            start_sequence=sequence,
            adjudications_out=adjudications_out,
        )
        if lowered is None:
            part_base_ids[part_index] = None
            continue
        part_ops, sequence = lowered
        doc_ops_by_base.setdefault(part_base_id, []).extend(part_ops)
        consumed_part_indexes.add(part_index)

    idx = 0
    active_base_id: str | None = None
    active_part_index: int | None = None
    while idx < len(children):
        child = children[idx]
        section_base_id = section_base_ids[idx] if idx < len(section_base_ids) else None
        child_part_index = _part_index(idx)
        # Crossing into a new part whose own lead resolved a base act makes that
        # act authoritative for everything the part introduces: the previous
        # part's carried-over ``active_base_id`` is stale by construction and
        # must not outrank it. Parts that resolve no law of their own keep the
        # carried-over id, which is the only evidence they have.
        if child_part_index != active_part_index:
            active_part_index = child_part_index
            part_base_id = (
                part_base_ids[child_part_index]
                if child_part_index is not None and child_part_index < len(part_base_ids)
                else None
            )
            if part_base_id is not None:
                active_base_id = part_base_id
        # W-39: a part the collective pre-pass already lowered is done. Its
        # announcement still sets ``active_base_id`` above (a later part with no
        # lead of its own inherits it exactly as before), but its members must
        # not be re-read as leads.
        if child_part_index in consumed_part_indexes:
            idx += 1
            continue
        child_classes = _classes(child)
        if _local_name(child) != "article" or not ({"defaultP", "legalP"} & child_classes):
            idx += 1
            continue
        lead = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in child.itertext())))
        explicit_section_base_id = _extract_no_section_base_id_from_lead(lead)
        if explicit_section_base_id is None:
            # W-28. The nominative announcement ("3. Lov 30. august 1991 nr. 71 om
            # statsforetak endres slik:") switches law exactly as the ``I lov …``
            # form does, and W-34's cursor-stop predicate has always treated it
            # that way — but this walk did not, so an announcement could never
            # displace a carried-over ``active_base_id``. That asymmetry was
            # invisible while nothing upstream of it resolved: in
            # `2005-06-17-103` part V no lead set ``active_base_id`` at all and
            # the act lowered nothing. Once item 2's numberless forvaltningsloven
            # citation resolves, items 3–6 inherit it, and 9 ops land on the
            # wrong law. Reading the announcement here is what keeps the walk's
            # base tracking and the cursor boundary telling the same story.
            explicit_section_base_id = _extract_no_law_announcement_base_id(lead)
        if explicit_section_base_id is not None:
            active_base_id = explicit_section_base_id
        lead_base_id = default_base_id or explicit_section_base_id or active_base_id or section_base_id
        embedded = _extract_no_embedded_multi_act_lead(lead)
        if embedded is not None:
            lead_base_id, lead = embedded
            active_base_id = lead_base_id
        payload_nodes: list[etree._Element] = []
        cursor = idx + 1
        while cursor < len(children):
            nxt = children[cursor]
            # Stop at the part boundary as well as at the next ``defaultP``
            # lead: the next part's law-switch lead is a ``legalP``, and
            # swallowing it as this lead's payload both loses the payload
            # boundary and leaves the switch unprocessed.
            if _part_index(cursor) != child_part_index:
                break
            if _local_name(nxt) == "article" and "defaultP" in _classes(nxt):
                # W-64: unless it is the section's HEADING, which Lovdata marks
                # with the same class. Only the first node after the lead is
                # tested, so the boundary still closes on the next ``defaultP``.
                if cursor == idx + 1 and _no_unstructured_payload_heading_node(
                    lead,
                    nxt,
                    children[cursor + 1]
                    if cursor + 1 < len(children) and _part_index(cursor + 1) == child_part_index
                    else None,
                ):
                    payload_nodes.append(nxt)
                    cursor += 1
                    continue
                break
            # W-34: the same boundary one level down. Inside a part, a numbered
            # enumeration item that opens with its own law-switch ("59. I lov 16.
            # juni 1967 nr. 3 … skal § 2 lyde:") is a SIBLING lead, not this
            # lead's payload; collecting it loses the item's own op and leaves
            # every later item bound to a stale base act.
            if (
                _local_name(nxt) == "article"
                and "legalP" in _classes(nxt)
                and _no_unstructured_law_switch_lead_base_id(
                    _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in nxt.itertext())))
                )
                is not None
            ):
                break
            payload_nodes.append(nxt)
            cursor += 1

        future_articles = [
            node for node in payload_nodes if _local_name(node) == "article" and "futureLegalArticle" in _classes(node)
        ]
        text_articles = [
            node
            for node in payload_nodes
            if _local_name(node) == "article" and {"legalP", "numberedLegalP"} & _classes(node)
        ]

        text_replace_pairs = _extract_no_global_text_replace_pairs(lead)
        if text_replace_pairs:
            cited_base_ids = _extract_no_law_citation_base_ids(lead)
            for node in payload_nodes:
                cited_text = _normalize_space(" ".join(str(_t) for _t in node.itertext()))
                cited_base_ids.extend(_extract_no_law_citation_base_ids(cited_text))
            cited_base_ids = list(dict.fromkeys(cited_base_ids))
            # W-20: a global text-replace lead that cites no law of its own is
            # still scoped to the part it sits in. Before W-15 these bound by
            # accident, on citations harvested from the NEXT part's swallowed
            # lead -- i.e. to the wrong law. With part boundaries closed there is
            # no citation left to harvest, so fall back to the lead's own
            # resolved base act rather than dropping the ops.
            if not cited_base_ids and lead_base_id is not None:
                cited_base_ids = [lead_base_id]
            if cited_base_ids:
                for cited_base_id in cited_base_ids:
                    cited_doc_ops = doc_ops_by_base.setdefault(cited_base_id, [])
                    for old_text, new_text in text_replace_pairs:
                        cited_doc_ops.append(
                            LegalOperation(
                                op_id=f"{source_id}:{sequence}",
                                sequence=sequence,
                                action=StructuralAction.TEXT_PATCH,
                                target=LegalAddress(path=()),
                                text_patch=TextPatchSpec(
                                    kind=TextPatchKindEnum.REPLACE,
                                    selector=TextSelector(
                                        match_text=old_text,
                                        occurrence=0,
                                    ),
                                    replacement=new_text,
                                ),
                                source=OperationSource(
                                    statute_id=source_id,
                                    raw_text=lead,
                                    title=cited_base_id,
                                ),
                                provenance_tags=(f"base_act:{cited_base_id}", "fallback:unstructured", "scope:global"),
                                group_id=f"{source_id}:{cited_base_id}:{sequence}",
                            )
                        )
                        sequence += 1
                idx = cursor
                continue

        if lead_base_id is None:
            if _no_unstructured_lead_looks_operative(lead):
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_lead_base_unresolved",
                    message="Norway unstructured amendment lead looked operative, but no base act could be resolved.",
                    source_id=source_id,
                    lead=lead,
                    base_id="",
                    detail={},
                )
            idx += 1
            continue
        doc_ops = doc_ops_by_base.setdefault(lead_base_id, [])

        heading_only_label = _no_heading_only_section_lead_label(lead)
        if heading_only_label is not None:
            target_label = heading_only_label
            payload = _heading_only_unstructured_section_payload(target_label, payload_nodes)
            if payload is not None:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPLACE,
                        target=LegalAddress(path=(("section", target_label),)),
                        payload=payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
                idx = cursor
                continue
            _append_no_unstructured_parse_adjudication(
                adjudications_out,
                kind="no_parse_unstructured_payload_unresolved",
                message="Norway unstructured heading replacement lead resolved a target but no heading payload could be extracted.",
                source_id=source_id,
                lead=lead,
                base_id=lead_base_id,
                detail={"target": f"section:{target_label}", "payload_family": "heading_only"},
            )

        # W-61. The repeal-then-shift lead, widened off the literal ``Nåværende``.
        #
        # W-58 recorded skattebetalingsloven § 8-2's missing first-ledd repeal as
        # an ARCHIVE gap, and W-60's Rider B re-read it as a run-on part boundary
        # (``…kommunene.III§ 8-2 første ledd oppheves…``). Both are wrong, and the
        # second is measurably so: the ``.<ROMAN>§`` concatenation occurs ZERO
        # times in the raw bytes of all 3,089 amendment artifacts, and zero times
        # in any single leaf text node. It exists only in an ``itertext()``
        # rendering of the WHOLE document, which walks straight across the
        # ``<section data-name="kapIII">`` boundary Lovdata marks up correctly.
        # The instrument is archived, indexed, applied, and its part III is one
        # clean ``<article class="defaultP">``.
        #
        # What actually refuses it is this production, which already lowers the
        # exact family ("§ X <ord> ledd oppheves. <ord> ledd blir <ord> ledd") —
        # but only when the shift sentence opens with the literal ``Nåværende``.
        # The witness says "Annet til femte ledd blir …", so the whole lead fell
        # through to ``no_parse_unstructured_lead_unmatched``.
        #
        # Measured over the corpus's 9,478 unstructured-lead refusals: 45 carry
        # the "§ S <ord> ledd oppheves. …" head, and they divide cleanly.
        #   * 24 are this family with the qualifier absent or spelled otherwise
        #     (bare, ``Gjeldende``, ``Någjeldende``, or a repeat of the section).
        #     23 are admitted below, over 14 instruments and 21 base acts (24
        #     receipt triples — one lead amends two acts at once); the 24th is
        #     the multi-section repeal list the guard declines;
        #   * 19 carry a TRAILING clause the shift does not account for
        #     ("… og skal lyde:", "… Tredje ledd skal lyde:") — every one of them
        #     introduces a PAYLOAD, so lowering the shift alone would state a
        #     half-truth. The anchored ``ledd\.?$`` tail refuses all 19 by
        #     construction, which is the conservative polarity: a lead this
        #     grammar cannot fully account for lowers nothing.
        #   * 2 are not a ledd shift at all and stay refused.
        #
        # The widening is STRICTLY ADDITIVE, and deliberately so. The first
        # attempt inside ``_no_unstructured_repeal_renumber_legs`` is the shipped
        # production, byte-for-byte — same anchored ``Nåværende`` regex, same
        # ``_infer_same_base_subsection_targets_from_lead`` round-trip, same empty
        # target lists where that round-trip resolves nothing. Only a lead the
        # SHIPPED regex does not match at all reaches the widened one, so no lead
        # that lowers today can change what it lowers.
        #
        # That ordering is not defensive dressing; it was forced by measurement.
        # A first cut replaced the production outright and regressed 14 leads:
        # 7 spell the qualifier BEFORE the section ("Nåværende § 2 fjerde og femte
        # ledd blir …") which the widened pattern reads in the other order, and 7
        # carry vocabulary outside ``_NORWEGIAN_ORDINALS`` ("henholdsvis", "eneste",
        # "siste", ordinals past "tiende") on which the shipped round-trip returns
        # an empty list and lowers a partial answer plus an arity receipt. Both
        # populations belong to whoever revisits this grammar next (W-62), not to a
        # widening whose whole claim is that it takes nothing away: the corpus-wide
        # count of ``no_parse_unstructured_renumber_arity_mismatch_skipped`` is a
        # pin (8), and the first cut drove it to 0.
        repeal_renumber_legs = _no_unstructured_repeal_renumber_legs(lead)
        if repeal_renumber_legs is not None:
            section_label, repeal_targets, source_targets, dest_targets = repeal_renumber_legs
            paired_renumber_count = min(len(source_targets), len(dest_targets))
            if len(source_targets) != len(dest_targets):
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_renumber_arity_mismatch_skipped",
                    message=(
                        "Norway unstructured repeal/renumber lead resolved unequal source "
                        "and destination target counts; unmatched targets were not compiled."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "section": section_label,
                        "source_count": len(source_targets),
                        "destination_count": len(dest_targets),
                        "paired_count": paired_renumber_count,
                        "source_targets": [_no_address_detail(target) for target in source_targets],
                        "destination_targets": [_no_address_detail(target) for target in dest_targets],
                        "unmatched_source_targets": [
                            _no_address_detail(target) for target in source_targets[paired_renumber_count:]
                        ],
                        "unmatched_destination_targets": [
                            _no_address_detail(target) for target in dest_targets[paired_renumber_count:]
                        ],
                    },
                )
            for target in repeal_targets:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=target,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            for src_target, dst_target in zip(source_targets, dest_targets, strict=False):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.RENUMBER,
                        target=src_target,
                        destination=dst_target,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                        witness_rule_id="no_section_renumber_relabel",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        section_lead = _normalize_no_chapter_scoped_section_lead(lead)
        section_match = _NO_WHOLE_SECTION_LEAD_RE.match(section_lead)
        if section_match:
            target = LegalAddress(path=(("section", _normalize_no_section_label(section_match.group("label"))),))
            action = StructuralAction.INSERT if section_match.group("insert") else StructuralAction.REPLACE
            if future_articles:
                payload = _parse_future_section(future_articles[0])
            else:
                payload = _build_no_unstructured_section_payload(
                    _normalize_no_section_label(section_match.group("label")),
                    section_match.group("inline"),
                    payload_nodes,
                )
            if payload is not None:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=action,
                        target=target,
                        payload=payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
                idx = cursor
                continue
            _append_no_unstructured_parse_adjudication(
                adjudications_out,
                kind="no_parse_unstructured_payload_unresolved",
                message="Norway unstructured section lead resolved a target but no section payload could be extracted.",
                source_id=source_id,
                lead=lead,
                base_id=lead_base_id,
                detail={"target": _no_address_detail(target), "payload_family": "future_section"},
            )

        sentence_specs = _infer_same_base_sentence_target_specs_from_lead(lead)
        if sentence_specs:
            sentence_targets = [target for _action, target in sentence_specs]
            sentence_payloads: list[IRNode] = []
            if len(text_articles) >= len(sentence_targets):
                for target, article in zip(sentence_targets, text_articles, strict=False):
                    payload = _payload_from_direct_text_article(article, target)
                    if payload is None:
                        sentence_payloads = []
                        break
                    sentence_payloads.append(payload)
            elif len(text_articles) == 1:
                text = _node_text_without_structural_children(text_articles[0])
                sentences = _split_no_sentences(text)
                if len(sentences) == len(sentence_targets):
                    sentence_payloads = [
                        IRNode(kind=IRNodeKind.SENTENCE, label=target.leaf_label() or None, text=sentence_text)
                        for target, sentence_text in zip(sentence_targets, sentences, strict=True)
                    ]
            if sentence_payloads and len(sentence_payloads) == len(sentence_targets):
                for (action, target), payload in zip(sentence_specs, sentence_payloads, strict=True):
                    doc_ops.append(
                        LegalOperation(
                            op_id=f"{source_id}:{sequence}",
                            sequence=sequence,
                            action=action,
                            target=target,
                            payload=payload,
                            source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                            provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                            group_id=f"{source_id}:{lead_base_id}:{sequence}",
                        )
                    )
                    sequence += 1
                idx = cursor
                continue
            _append_no_unstructured_parse_adjudication(
                adjudications_out,
                kind="no_parse_unstructured_payload_unresolved",
                message="Norway unstructured sentence lead resolved targets but payload extraction did not cover them.",
                source_id=source_id,
                lead=lead,
                base_id=lead_base_id,
                detail={
                    "targets": tuple(_no_address_detail(target) for target in sentence_targets),
                    "payload_family": "sentence",
                },
            )

        subsection_specs = _infer_same_base_subsection_target_specs_from_lead(lead)
        if not subsection_specs:
            # W-98 (a): the repeated-noun list ("§ 7-2 første ledd og tredje
            # ledd skal lyde:"), tried only once the shipped single-noun grammar
            # has returned nothing. See ``_no_repeated_ledd_noun_subsection_specs``.
            subsection_specs = _no_repeated_ledd_noun_subsection_specs(lead)
        if subsection_specs and len(text_articles) >= len(subsection_specs):
            unresolved_targets: list[LegalAddress] = []
            for (action, target), article in zip(subsection_specs, text_articles, strict=False):
                payload = _payload_from_direct_text_article(article, target)
                if payload is None:
                    unresolved_targets.append(target)
                    continue
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=action,
                        target=target,
                        payload=payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            for target in unresolved_targets:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_payload_unresolved",
                    message="Norway unstructured subsection lead resolved a target but no subsection payload could be extracted.",
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={"target": _no_address_detail(target), "payload_family": "subsection"},
                )
            idx = cursor
            continue

        item_specs = _infer_same_base_item_target_specs_from_lead(lead)
        if item_specs:
            item_targets = [target for _action, target in item_specs]
            payload_candidates = _extract_payload_candidates_from_nodes([child, *payload_nodes], item_targets)
            resolved: list[tuple[StructuralAction, LegalAddress, IRNode]] = []
            unresolved_targets: list[LegalAddress] = []
            single_text_article_paths: set[tuple[tuple[str, str], ...]] = set()
            for action, target in item_specs:
                payload = payload_candidates.get((target.leaf_kind(), target.leaf_label()))
                if payload is None and target.leaf_kind() == "item" and target.leaf_label() == "last":
                    item_payloads = [
                        candidate for (kind, _label), candidate in payload_candidates.items() if kind == "item"
                    ]
                    if len(item_payloads) == 1:
                        payload = _with_no_node_label(item_payloads[0], "last")
                if payload is None:
                    # W-98 (d): the single-item lead whose new text is the ONE
                    # ``legalP`` that follows it. See
                    # ``_no_item_payload_from_single_text_article``.
                    payload = _no_item_payload_from_single_text_article(
                        item_specs, target, payload_candidates, text_articles
                    )
                    if payload is not None:
                        single_text_article_paths.add(target.path)
                if payload is None:
                    unresolved_targets.append(target)
                    continue
                resolved.append((action, target, payload))
            # W-32(a), the W-19 all-or-nothing rule: a lead that DECLARES several
            # lettered items is one indivisible instruction. If the payload does
            # not split to match the declared arity we have no evidence for which
            # item the recovered halves belong to, so nothing lowers and the whole
            # lead receipts. A single-item lead keeps its per-target behaviour:
            # there is no arity to guess at, and the existing receipt already
            # names the one target that failed.
            if len(item_specs) > 1 and unresolved_targets:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_multi_item_payload_arity_mismatch",
                    message=(
                        "Norway unstructured multi-item lead declared several lettered "
                        "items but the payload did not cover all of them; the whole "
                        "lead was dropped rather than lowered against a guessed split."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "declared_count": len(item_specs),
                        "resolved_count": len(resolved),
                        "targets": tuple(_no_address_detail(target) for target in item_targets),
                        "unresolved_targets": tuple(_no_address_detail(target) for target in unresolved_targets),
                        "payload_family": "item",
                    },
                )
                idx = cursor
                continue
            for action, target, payload in resolved:
                item_tags: tuple[str, ...] = (f"base_act:{lead_base_id}", "fallback:unstructured")
                if target.path in single_text_article_paths:
                    item_tags = (*item_tags, NO_ITEM_PAYLOAD_SINGLE_TEXT_ARTICLE_PROVENANCE_TAG)
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=action,
                        target=target,
                        payload=payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=item_tags,
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            for target in unresolved_targets:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_payload_unresolved",
                    message="Norway unstructured item lead resolved a target but no item payload could be extracted.",
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={"target": _no_address_detail(target), "payload_family": "item"},
                )
            idx = cursor
            continue

        repeal_match = re.match(r"^§\s*([0-9A-Za-z-]+)\s+(.+?)\s+ledd\s+oppheves\.?$", lead, re.IGNORECASE)
        if repeal_match:
            for target in _infer_same_base_subsection_targets_from_lead(
                f"§ {repeal_match.group(1)} {repeal_match.group(2)} ledd skal lyde"
            ):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=target,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        plural_section_repeal_match = re.match(
            r"^§§\s*([0-9A-Za-z-]+)\s+og\s+([0-9A-Za-z-]+)\s+oppheves\.?$",
            lead,
            re.IGNORECASE,
        )
        if plural_section_repeal_match:
            for label in (
                _normalize_no_section_label(plural_section_repeal_match.group(1)),
                _normalize_no_section_label(plural_section_repeal_match.group(2)),
            ):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(path=(("section", label),)),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        section_repeal_match = re.match(r"^§\s*([0-9A-Za-z-]+)\s+oppheves\.?$", lead, re.IGNORECASE)
        if section_repeal_match:
            label = _normalize_no_section_label(section_repeal_match.group(1))
            doc_ops.append(
                LegalOperation(
                    op_id=f"{source_id}:{sequence}",
                    sequence=sequence,
                    action=StructuralAction.REPEAL,
                    target=LegalAddress(path=(("section", label),)),
                    source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                    provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                    group_id=f"{source_id}:{lead_base_id}:{sequence}",
                )
            )
            sequence += 1
            idx = cursor
            continue

        range_section_repeal_match = re.match(
            r"^§§\s*([0-9A-Za-z-]+)\s+til\s+([0-9A-Za-z-]+)\s+oppheves\.?$",
            lead,
            re.IGNORECASE,
        )
        if range_section_repeal_match:
            shipped_range_labels = _expand_no_section_range_labels(
                range_section_repeal_match.group(1),
                range_section_repeal_match.group(2),
            )
            if shipped_range_labels is None:
                # W-98 (c): the expander now refuses what it used to truncate
                # to two endpoints; the refusal is typed rather than silent.
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_SECTION_RANGE_UNEXPANDABLE,
                    message=(
                        "Norway unstructured section-range repeal names a range this grammar "
                        "cannot enumerate (cross-chapter, unordered or unlabelled); nothing was repealed."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "start": _normalize_no_section_label(range_section_repeal_match.group(1)),
                        "end": _normalize_no_section_label(range_section_repeal_match.group(2)),
                    },
                )
                idx += 1
                continue
            for label in shipped_range_labels:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(path=(("section", label),)),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        renumber_labels = _no_unstructured_section_renumber_labels(lead)
        if renumber_labels is not None:
            src_label, dst_label, _renumber_pattern = renumber_labels
            doc_ops.append(
                LegalOperation(
                    op_id=f"{source_id}:{sequence}",
                    sequence=sequence,
                    action=StructuralAction.RENUMBER,
                    target=LegalAddress(path=(("section", src_label),)),
                    destination=LegalAddress(path=(("section", dst_label),)),
                    source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                    provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                    group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    witness_rule_id="no_section_renumber_relabel",
                )
            )
            sequence += 1
            idx = cursor
            continue

        plural_renumber_match = re.match(
            r"^Nåværende §§\s*([0-9A-Za-z-]+)\s+og\s+([0-9A-Za-z-]+)\s+blir §§\s*([0-9A-Za-z-]+)\s+og\s+([0-9A-Za-z-]+)\.?$",
            lead,
            re.IGNORECASE,
        )
        if plural_renumber_match:
            pairs = [
                (_normalize_label(plural_renumber_match.group(1)), _normalize_label(plural_renumber_match.group(3))),
                (_normalize_label(plural_renumber_match.group(2)), _normalize_label(plural_renumber_match.group(4))),
            ]
            for src_label, dst_label in pairs:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.RENUMBER,
                        target=LegalAddress(path=(("section", src_label),)),
                        destination=LegalAddress(path=(("section", dst_label),)),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                        witness_rule_id="no_section_renumber_relabel",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # W-74, and it sits HERE — last, immediately before the refusal — on
        # purpose. Every shipped production above has already declined the lead,
        # so this one is reachable only on a lead that lowers nothing today and
        # cannot change what any shipped pattern does. That is the same additive
        # ordering W-61 and W-67 use inside their own functions, expressed as
        # position in the walk because this production has no shipped ancestor to
        # try first. See the block comment on
        # ``_NO_UNSTRUCTURED_SECTION_REPEAL_RENUMBER_RE`` for the measurement and
        # for the destination-vacated conjunct.
        #
        # The op ORDER is load-bearing: every REPEAL is minted before the RENUMBER,
        # at a lower sequence in the same group. The destination is a label this
        # lead repeals, so by the time the shift applies its slot is provably free
        # — which is exactly why the occupied-destination recovery must not fire on
        # anything this production emits.
        section_repeal_renumber = _no_unstructured_section_repeal_renumber_labels(lead)
        if section_repeal_renumber is not None:
            repealed_labels, shift_source, shift_destination = section_repeal_renumber
            for label in repealed_labels:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(path=(("section", label),)),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            doc_ops.append(
                LegalOperation(
                    op_id=f"{source_id}:{sequence}",
                    sequence=sequence,
                    action=StructuralAction.RENUMBER,
                    target=LegalAddress(path=(("section", shift_source),)),
                    destination=LegalAddress(path=(("section", shift_destination),)),
                    source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                    provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                    group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    witness_rule_id="no_section_renumber_relabel",
                )
            )
            sequence += 1
            idx = cursor
            continue

        # W-66, and it sits here for the same reason W-74's block above does:
        # every shipped production has already declined the lead, so this one is
        # reachable only on a lead that lowers nothing today. See the block
        # comment on ``_no_ledd_set_relabel_pairs`` for the measurement, the
        # atomicity argument and what is deliberately left refused.
        set_relabel = _no_ledd_set_relabel_pairs(lead)
        if set_relabel is not None:
            relabel_section, relabel_pairs, relabel_pattern = set_relabel
            address_reason = "lead_names_section"
            if not relabel_section:
                inherited_label, address_reason = _no_antecedent_section_label(
                    children, child_part_indexes, idx
                )
                relabel_section = inherited_label or ""
            if not relabel_section:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED,
                    message=(
                        "Norway sibling-set ledd relabel named no section of its own and no "
                        "unambiguous antecedent supplied one; the relabel was not lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "address_reason": address_reason,
                        "pattern": relabel_pattern,
                        "pairs": tuple(f"{src}->{dst}" for src, dst in relabel_pairs),
                    },
                )
                idx += 1
                continue
            ordered_pairs = _no_ordered_set_relabel_pairs(relabel_pairs)
            if ordered_pairs is None:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ORDER_UNPROVABLE,
                    message=(
                        "Norway sibling-set ledd relabel has no vacate-before-occupy order "
                        "(the source and destination sets form a cycle); nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "section": relabel_section,
                        "pattern": relabel_pattern,
                        "pairs": tuple(f"{src}->{dst}" for src, dst in relabel_pairs),
                    },
                )
                idx += 1
                continue
            for src_ordinal, dst_ordinal in ordered_pairs:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.RENUMBER,
                        target=LegalAddress(
                            path=(("section", relabel_section), ("subsection", str(src_ordinal)))
                        ),
                        destination=LegalAddress(
                            path=(("section", relabel_section), ("subsection", str(dst_ordinal)))
                        ),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(
                            f"base_act:{lead_base_id}",
                            "fallback:unstructured",
                            NO_LEDD_SET_RELABEL_PROVENANCE_TAG,
                        ),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                        witness_rule_id="no_section_renumber_relabel",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # W-66b, and it sits BEHIND W-66's block for the reason its ``pattern``
        # field exists: the shipped ledd grammar is tried first and must be
        # byte-identical for everything it already handles. The two are disjoint
        # by their tail anchors (``… ledd.`` against ``… punktum.``), so the
        # ordering costs nothing and buys the guarantee outright. See the block
        # comment on ``_no_punktum_set_relabel_pairs`` for the measurement and for
        # what is deliberately left refused.
        #
        # The ops are stamped with W-66's OWN provenance tag rather than a
        # sibling, and that is a decision rather than an economy. The apply-plane
        # refuse-on-occupied branch keyed on that tag is depth-agnostic already —
        # it compares resolved paths — so reusing the tag generalizes it unchanged
        # (item 76 (b)), while a second tag would need either a duplicated branch
        # or a widened condition on a load-bearing safety seam, for no semantic
        # gain. It also keeps these legs VISIBLE to W-72's occupied-destination
        # sweep and inside the conserved partition's existing skip kind; a fresh
        # tag would make a punktum firing invisible to both, which is exactly the
        # wrong polarity. A punktum firing is still told apart from a ledd one by
        # the receipt's own ``source_path``/``destination_path``.
        punktum_relabel = _no_punktum_set_relabel_pairs(lead)
        if punktum_relabel is not None:
            (
                punktum_section,
                punktum_ledd,
                punktum_pairs,
                punktum_pattern,
            ) = punktum_relabel
            punktum_address_reason = "lead_names_section"
            if not punktum_section:
                inherited_section, punktum_address_reason = _no_antecedent_section_label(
                    children, child_part_indexes, idx
                )
                punktum_section = inherited_section or ""
            if not punktum_section:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED,
                    message=(
                        "Norway sibling-set punktum relabel named no section of its own and no "
                        "unambiguous antecedent supplied one; the relabel was not lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "address_reason": punktum_address_reason,
                        "pattern": punktum_pattern,
                        "pairs": tuple(f"{src}->{dst}" for src, dst in punktum_pairs),
                    },
                )
                idx += 1
                continue
            punktum_ledd_reason = "lead_names_ledd"
            if not punktum_ledd:
                inherited_ledd, punktum_ledd_reason = _no_antecedent_ledd_label(
                    children, child_part_indexes, idx
                )
                punktum_ledd = inherited_ledd or ""
            if not punktum_ledd:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED,
                    message=(
                        "Norway sibling-set punktum relabel named no ledd of its own and no "
                        "unambiguous antecedent supplied one; the relabel was not lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "section": punktum_section,
                        "address_reason": punktum_address_reason,
                        "ledd_reason": punktum_ledd_reason,
                        "pattern": punktum_pattern,
                        "pairs": tuple(f"{src}->{dst}" for src, dst in punktum_pairs),
                    },
                )
                idx += 1
                continue
            punktum_ordered = _no_ordered_set_relabel_pairs(punktum_pairs)
            if punktum_ordered is None:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ORDER_UNPROVABLE,
                    message=(
                        "Norway sibling-set punktum relabel has no vacate-before-occupy order "
                        "(the source and destination sets form a cycle); nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "section": punktum_section,
                        "ledd": punktum_ledd,
                        "pattern": punktum_pattern,
                        "pairs": tuple(f"{src}->{dst}" for src, dst in punktum_pairs),
                    },
                )
                idx += 1
                continue
            for src_ordinal, dst_ordinal in punktum_ordered:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.RENUMBER,
                        target=LegalAddress(
                            path=(
                                ("section", punktum_section),
                                ("subsection", punktum_ledd),
                                ("sentence", str(src_ordinal)),
                            )
                        ),
                        destination=LegalAddress(
                            path=(
                                ("section", punktum_section),
                                ("subsection", punktum_ledd),
                                ("sentence", str(dst_ordinal)),
                            )
                        ),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(
                            f"base_act:{lead_base_id}",
                            "fallback:unstructured",
                            NO_LEDD_SET_RELABEL_PROVENANCE_TAG,
                        ),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                        witness_rule_id="no_section_renumber_relabel",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # W-66c, and it sits LAST — behind every shipped production and
        # immediately ahead of the operative fallback. The position is the
        # additivity proof rather than a preference: a lead only reaches here
        # once every other family has declined it, so this block can convert
        # nothing but leads that carry ``no_parse_unstructured_lead_unmatched``
        # today. For a production that DESTROYS TEXT that guarantee is worth
        # more than the tail-anchor disjointness argument W-66b could make.
        #
        # The receipt kinds are REUSED, both of them, and the reuse is W-66b's
        # own precedent one step further: the section half already reuses W-66's
        # ``..._ADDRESS_UNRESOLVED`` because it is the same helper failing the
        # same way, and the ledd half reuses W-66b's ``..._LEDD_UNRESOLVED`` for
        # the same reason — the reader, the DOM-local antecedent rule and the
        # failure are identical; only the production that goes unlowered
        # differs. The shipped constant names say ``set_relabel`` and are now
        # historical twice over; a census tells a repeal refusal from a relabel
        # one by the ``production`` detail key below, which is the same answer
        # W-66b gave at the apply plane (a punktum firing is told from a ledd one
        # by the receipt's own paths, not by a second kind).
        punktum_repeal = _no_punktum_repeal_targets(lead)
        if punktum_repeal is not None:
            repeal_section, repeal_ledd, repeal_targets = punktum_repeal
            repeal_address_reason = "lead_names_section"
            if not repeal_section:
                inherited_section, repeal_address_reason = _no_antecedent_section_label(
                    children, child_part_indexes, idx
                )
                repeal_section = inherited_section or ""
            if not repeal_section:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED,
                    message=(
                        "Norway punktum repeal named no section of its own and no unambiguous "
                        "antecedent supplied one; nothing was repealed."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "punktum_repeal",
                        "address_reason": repeal_address_reason,
                        "targets": tuple(str(ordinal) for ordinal in repeal_targets),
                    },
                )
                idx += 1
                continue
            repeal_ledd_reason = "lead_names_ledd"
            if not repeal_ledd:
                inherited_ledd, repeal_ledd_reason = _no_antecedent_ledd_label(
                    children, child_part_indexes, idx
                )
                repeal_ledd = inherited_ledd or ""
            if not repeal_ledd:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_PUNKTUM_SET_RELABEL_LEDD_UNRESOLVED,
                    message=(
                        "Norway punktum repeal named no ledd of its own and no unambiguous "
                        "antecedent supplied one; nothing was repealed."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "punktum_repeal",
                        "section": repeal_section,
                        "address_reason": repeal_address_reason,
                        "ledd_reason": repeal_ledd_reason,
                        "targets": tuple(str(ordinal) for ordinal in repeal_targets),
                    },
                )
                idx += 1
                continue
            # Descending order, and it is not cosmetic. ``tree_ops.remove_at``
            # removes a node without relabelling its siblings, so the legs are
            # order-independent TODAY; emitting the highest ordinal first keeps
            # them order-independent under any future sibling-compaction, which
            # is the direction a repeal at this depth would plausibly grow.
            for target_ordinal in sorted(repeal_targets, reverse=True):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(
                            path=(
                                ("section", repeal_section),
                                ("subsection", repeal_ledd),
                                ("sentence", str(target_ordinal)),
                            )
                        ),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # W-76, and it sits LAST — behind W-66c and immediately ahead of the
        # operative fallback. The position is the additivity proof rather than a
        # preference, exactly as it is for the block above: a lead only reaches
        # here once every other family has declined it, so this block can convert
        # nothing but leads that carry ``no_parse_unstructured_lead_unmatched``
        # today. The tail-anchor disjointness argument is available too and is
        # pinned as a test fact, but it is the weaker of the two. See the block
        # comment on ``_no_item_set_relabel_pairs`` for the measurement, the
        # address probe and what is deliberately left refused.
        item_relabel = _no_item_set_relabel_pairs(lead)
        if item_relabel is not None:
            item_section, item_depth, item_pairs = item_relabel
            item_pair_detail = tuple(
                f"{_no_item_relabel_label(item_depth, src)}->{_no_item_relabel_label(item_depth, dst)}"
                for src, dst in item_pairs
            )
            item_address_reason = "lead_names_section"
            if not item_section:
                inherited_section, item_address_reason = _no_antecedent_section_label(
                    children, child_part_indexes, idx
                )
                item_section = inherited_section or ""
            if not item_section:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ADDRESS_UNRESOLVED,
                    message=(
                        "Norway sibling-set item relabel named no section of its own and no "
                        "unambiguous antecedent supplied one; the relabel was not lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "item_set_relabel",
                        "depth": item_depth,
                        "address_reason": item_address_reason,
                        "pairs": item_pair_detail,
                    },
                )
                idx += 1
                continue
            # The ledd is ALWAYS inherited at this depth: the sized grammar's
            # source side reduces to labels alone, so a lead that spells its own
            # ledd never reaches here. See the block comment.
            inherited_ledd, item_ledd_reason = _no_antecedent_ledd_label(
                children,
                child_part_indexes,
                idx,
                depth_name="item",
                depth_markers=_NO_ITEM_RELABEL_ANTECEDENT_MARKERS[item_depth],
            )
            item_ledd = inherited_ledd or ""
            if not item_ledd:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_ITEM_SET_RELABEL_LEDD_UNRESOLVED,
                    message=(
                        "Norway sibling-set item relabel resolved its section but no unambiguous "
                        "antecedent supplied the ledd its item hangs below; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "item_set_relabel",
                        "depth": item_depth,
                        "section": item_section,
                        "address_reason": item_address_reason,
                        "ledd_reason": item_ledd_reason,
                        "pairs": item_pair_detail,
                    },
                )
                idx += 1
                continue
            item_ordered = _no_ordered_set_relabel_pairs(item_pairs)
            if item_ordered is None:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_SET_RELABEL_ORDER_UNPROVABLE,
                    message=(
                        "Norway sibling-set item relabel has no vacate-before-occupy order "
                        "(the source and destination sets form a cycle); nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "item_set_relabel",
                        "depth": item_depth,
                        "section": item_section,
                        "ledd": item_ledd,
                        "pairs": item_pair_detail,
                    },
                )
                idx += 1
                continue
            for src_index, dst_index in item_ordered:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.RENUMBER,
                        target=LegalAddress(
                            path=(
                                ("section", item_section),
                                ("subsection", item_ledd),
                                ("item", _no_item_relabel_label(item_depth, src_index)),
                            )
                        ),
                        destination=LegalAddress(
                            path=(
                                ("section", item_section),
                                ("subsection", item_ledd),
                                ("item", _no_item_relabel_label(item_depth, dst_index)),
                            )
                        ),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(
                            f"base_act:{lead_base_id}",
                            "fallback:unstructured",
                            NO_LEDD_SET_RELABEL_PROVENANCE_TAG,
                        ),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                        witness_rule_id="no_section_renumber_relabel",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # W-77, and it sits LAST — behind W-76 and immediately ahead of the
        # operative fallback. The position is the additivity proof rather than a
        # preference, exactly as it is for the two blocks above: a lead only
        # reaches here once every other family has declined it, so this block can
        # convert nothing but leads that carry
        # ``no_parse_unstructured_lead_unmatched`` today. See the block comment
        # on ``_no_item_insert_payload_target`` for the measurement, the payload
        # extent proof, the occupied-destination polarity and what is
        # deliberately left refused.
        #
        # The grammar reads the announcing node's OWN text, not ``lead``: this
        # family's payload sits INSIDE the announcing node as a ``<ul>``, so
        # ``lead`` is announcement and payload concatenated and cannot be
        # anchored. ``payload_nodes`` is still the boundary's answer for the
        # sibling-carried shape, and both carriers go through one extent proof.
        item_insert = _no_item_insert_payload_target(
            _repair_no_mojibake(_node_text_without_structural_children(child))
        )
        if item_insert is not None:
            insert_section, insert_ledd, insert_depth, insert_labels = item_insert
            insert_address_reason = "lead_names_section"
            if not insert_section:
                inherited_section, insert_address_reason = _no_antecedent_section_label(
                    children, child_part_indexes, idx
                )
                insert_section = inherited_section or ""
            if not insert_section:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_ITEM_INSERT_PAYLOAD_ADDRESS_UNRESOLVED,
                    message=(
                        "Norway item-depth newness payload named no section of its own and no "
                        "unambiguous antecedent supplied one; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "item_insert_payload",
                        "depth": insert_depth,
                        "address_reason": insert_address_reason,
                        "labels": tuple(insert_labels),
                    },
                )
                idx += 1
                continue
            insert_ledd_reason = "lead_names_ledd"
            if not insert_ledd:
                inherited_ledd, insert_ledd_reason = _no_antecedent_ledd_label(
                    children,
                    child_part_indexes,
                    idx,
                    depth_name="item",
                    depth_markers=_NO_ITEM_RELABEL_ANTECEDENT_MARKERS[insert_depth],
                )
                insert_ledd = inherited_ledd or ""
            if not insert_ledd:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_ITEM_INSERT_PAYLOAD_LEDD_UNRESOLVED,
                    message=(
                        "Norway item-depth newness payload resolved its section but no unambiguous "
                        "antecedent supplied the ledd its item hangs below; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "item_insert_payload",
                        "depth": insert_depth,
                        "section": insert_section,
                        "address_reason": insert_address_reason,
                        "ledd_reason": insert_ledd_reason,
                        "labels": tuple(insert_labels),
                    },
                )
                idx += 1
                continue
            insert_payloads = _no_item_insert_payloads(child, payload_nodes, insert_labels)
            if insert_payloads is None:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_ITEM_INSERT_PAYLOAD_EXTENT_UNPROVABLE,
                    message=(
                        "Norway item-depth newness payload resolved its address but the payload's "
                        "extent could not be proved against the announced labels; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "production": "item_insert_payload",
                        "depth": insert_depth,
                        "section": insert_section,
                        "ledd": insert_ledd,
                        "labels": tuple(insert_labels),
                        "payload_node_count": len(payload_nodes),
                    },
                )
                idx += 1
                continue
            for insert_label, insert_payload in zip(insert_labels, insert_payloads, strict=True):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.INSERT,
                        target=LegalAddress(
                            path=(
                                ("section", insert_section),
                                ("subsection", insert_ledd),
                                ("item", insert_label),
                            )
                        ),
                        payload=insert_payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(
                            f"base_act:{lead_base_id}",
                            "fallback:unstructured",
                            NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG,
                        ),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # ── W-98. Six productions, each behind every shipped one (additivity by
        # position, W-66c's argument) and immediately ahead of the operative
        # fallback. See the block comments on their readers for the census and
        # for what each deliberately leaves refused.

        # (i) The nynorsk ledd repeal.
        nynorsk_repeal = _no_nynorsk_ledd_repeal_targets(lead)
        if nynorsk_repeal is not None:
            nynorsk_section, nynorsk_ordinals = nynorsk_repeal
            # Descending, for W-66c's reason: order-independent under any
            # future sibling compaction.
            for ordinal in sorted(nynorsk_ordinals, reverse=True):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(path=(("section", nynorsk_section), ("subsection", str(ordinal)))),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # (c) The section range with a ``§`` on both ends, or a nynorsk verb.
        range_lead = _no_section_range_repeal_lead(lead)
        if range_lead is not None:
            range_start, range_end = range_lead
            range_labels = _expand_no_section_range_labels(range_start, range_end)
            if range_labels is None:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_SECTION_RANGE_UNEXPANDABLE,
                    message=(
                        "Norway unstructured section-range repeal names a range this grammar "
                        "cannot enumerate (cross-chapter, unordered or unlabelled); nothing was repealed."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "start": _normalize_no_section_label(range_start),
                        "end": _normalize_no_section_label(range_end),
                    },
                )
                idx += 1
                continue
            for label in range_labels:
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(path=(("section", label),)),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # (b) The mixed punktum + ledd member list.
        mixed_specs = _no_mixed_punktum_ledd_member_specs(lead)
        if mixed_specs:
            mixed_targets = [target for _action, target in mixed_specs]
            if len(text_articles) != len(mixed_specs):
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_MIXED_MEMBER_PAYLOAD_ARITY_MISMATCH,
                    message=(
                        "Norway unstructured mixed-depth lead declared members at two depths but "
                        "the payload does not carry exactly one text article per member; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "declared_count": len(mixed_specs),
                        "payload_count": len(text_articles),
                        "targets": tuple(_no_address_detail(target) for target in mixed_targets),
                    },
                )
                idx += 1
                continue
            mixed_payloads = [
                _payload_from_direct_text_article(article, target)
                for (_action, target), article in zip(mixed_specs, text_articles, strict=True)
            ]
            if any(payload is None for payload in mixed_payloads):
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_payload_unresolved",
                    message=(
                        "Norway unstructured mixed-depth lead resolved its members but a member's "
                        "payload could not be extracted; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "targets": tuple(_no_address_detail(target) for target in mixed_targets),
                        "payload_family": "mixed_member",
                    },
                )
                idx += 1
                continue
            for (action, target), payload in zip(mixed_specs, mixed_payloads, strict=True):
                assert payload is not None
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=action,
                        target=target,
                        payload=payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(f"base_act:{lead_base_id}", "fallback:unstructured"),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # (e) The compound ledd repeal-then-reenact lead.
        compound = _no_ledd_repeal_reenact_specs(lead)
        if compound is not None:
            compound_section, compound_repealed, compound_specs = compound
            compound_targets = [target for _action, target in compound_specs]
            if len(text_articles) != len(compound_specs):
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_LEDD_REPEAL_REENACT_PAYLOAD_ARITY_MISMATCH,
                    message=(
                        "Norway unstructured repeal-then-reenact lead declared re-enacted ledd but the "
                        "payload does not carry exactly one text article per member; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "section": compound_section,
                        "repealed": tuple(str(ordinal) for ordinal in compound_repealed),
                        "declared_count": len(compound_specs),
                        "payload_count": len(text_articles),
                        "targets": tuple(_no_address_detail(target) for target in compound_targets),
                    },
                )
                idx += 1
                continue
            compound_payloads = [
                _payload_from_direct_text_article(article, target)
                for (_action, target), article in zip(compound_specs, text_articles, strict=True)
            ]
            if any(payload is None for payload in compound_payloads):
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unstructured_payload_unresolved",
                    message=(
                        "Norway unstructured repeal-then-reenact lead resolved its members but a "
                        "member's payload could not be extracted; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "targets": tuple(_no_address_detail(target) for target in compound_targets),
                        "payload_family": "ledd_repeal_reenact",
                    },
                )
                idx += 1
                continue
            for ordinal in sorted(compound_repealed, reverse=True):
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.REPEAL,
                        target=LegalAddress(path=(("section", compound_section), ("subsection", str(ordinal)))),
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(
                            f"base_act:{lead_base_id}",
                            "fallback:unstructured",
                            NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG,
                        ),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            for (action, target), payload in zip(compound_specs, compound_payloads, strict=True):
                assert payload is not None
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=action,
                        target=target,
                        payload=payload,
                        source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                        provenance_tags=(
                            f"base_act:{lead_base_id}",
                            "fallback:unstructured",
                            NO_LEDD_REPEAL_REENACT_PROVENANCE_TAG,
                        ),
                        group_id=f"{source_id}:{lead_base_id}:{sequence}",
                    )
                )
                sequence += 1
            idx = cursor
            continue

        # (f) The chapter heading.
        chapter_heading = _no_chapter_heading_lead(lead)
        if chapter_heading is not None:
            heading_chapter, inline_title = chapter_heading
            heading_read = _no_chapter_heading_read(children, child_part_indexes, idx, inline_title)
            heading_title = heading_read.title
            if not heading_title:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_CHAPTER_HEADING_PAYLOAD_UNRESOLVED,
                    message=(
                        "Norway unstructured chapter heading lead resolved its chapter but no single "
                        "heading payload could be extracted; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "chapter": heading_chapter,
                        "refusal": heading_read.refusal,
                    },
                )
                idx += 1
                continue
            doc_ops.append(
                LegalOperation(
                    op_id=f"{source_id}:{sequence}",
                    sequence=sequence,
                    action=StructuralAction.REPLACE,
                    target=LegalAddress(path=(("chapter", heading_chapter),)),
                    payload=IRNode(
                        kind=IRNodeKind.CHAPTER,
                        label=heading_chapter,
                        children=(IRNode(kind=IRNodeKind.HEADING, text=heading_title),),
                    ),
                    source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                    provenance_tags=(
                        f"base_act:{lead_base_id}",
                        "fallback:unstructured",
                        NO_CHAPTER_HEADING_PROVENANCE_TAG,
                    ),
                    group_id=f"{source_id}:{lead_base_id}:{sequence}",
                )
            )
            sequence += 1
            idx = heading_read.end_index
            continue

        # (g) The whole-chapter re-enactment.
        chapter_reenactment = _no_chapter_reenactment_lead(lead)
        if chapter_reenactment is not None:
            reenact_chapter, reenact_action = chapter_reenactment
            read = _no_chapter_reenactment_payload(
                children, child_part_indexes, idx, reenact_chapter, reenact_action
            )
            if read.payload is None:
                _append_no_unstructured_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_CHAPTER_REENACTMENT_PAYLOAD_UNRESOLVED,
                    message=(
                        "Norway unstructured chapter re-enactment lead resolved its chapter but the "
                        "payload did not read as one closed chapter; nothing was lowered."
                    ),
                    source_id=source_id,
                    lead=lead,
                    base_id=lead_base_id,
                    detail={
                        "chapter": reenact_chapter,
                        "action": _no_action_value(reenact_action),
                        "refusal": read.refusal,
                        "member": read.member,
                    },
                )
                idx += 1
                continue
            doc_ops.append(
                LegalOperation(
                    op_id=f"{source_id}:{sequence}",
                    sequence=sequence,
                    action=reenact_action,
                    target=LegalAddress(path=(("chapter", reenact_chapter),)),
                    payload=read.payload,
                    source=OperationSource(statute_id=source_id, raw_text=lead, title=lead_base_id),
                    provenance_tags=(
                        f"base_act:{lead_base_id}",
                        "fallback:unstructured",
                        NO_CHAPTER_REENACTMENT_PROVENANCE_TAG,
                    ),
                    group_id=f"{source_id}:{lead_base_id}:{sequence}",
                )
            )
            sequence += 1
            idx = read.end_index
            continue

        if _no_unstructured_lead_looks_operative(lead):
            _append_no_unstructured_parse_adjudication(
                adjudications_out,
                kind="no_parse_unstructured_lead_unmatched",
                message="Norway unstructured amendment lead looked operative but matched no supported lowering family.",
                source_id=source_id,
                lead=lead,
                base_id=lead_base_id,
                detail={},
            )
        idx += 1

    return [
        (base_id, _promote_no_replace_with_following_renumber_insert(doc_ops))
        for base_id, doc_ops in doc_ops_by_base.items()
        if doc_ops
    ]


# W-39, half (i). The collective re-enactment part lead.
#
# Three acts corpus-wide open a part with "I lov <cite> skal følgende
# bestemmelser lyde:" (`2006-06-30-41`, `2009-06-19-85`, `2021-06-11-60`); a
# fourth carries the ``paragrafer`` spelling but as a CHAPTER scope inside an
# already-resolved part ("I kapitlene 34 og 35 skal følgende paragrafer lyde:",
# `2009-05-08-27`), which is why the head anchor below is ``I lov`` and not the
# bare tail. Measured against 1,810 acts spelling ``gjøres følgende endringer``:
# this is a four-act family, and its tail is the only one in the corpus that
# announces an END STATE ("the following provisions shall read") rather than an
# amending action.
#
# The consequence is the whole design of the part lowering below. Because the
# payloads state the resulting text, their order among themselves is inert; but
# a pure-renumber statement inside the same part says "Nåværende § X", an
# explicit reference to the PRE-amendment law. On the witness the two
# interleave and overlap: renumber sources {12,13,16,17,18} intersect payload
# addresses {1..13,16,17,18,19}, so applying the part in document order would
# renumber sections this same act has already overwritten. Sequencing every
# RENUMBER before every payload is not a preference — it is the only order in
# which "Nåværende § 12" still denotes what the drafter meant, and it
# reproduces the published consolidation exactly (old §12→§14, §13→§15,
# §16→§20, §17→§21, §18→§22, with §1–13/§16–19 taking the act's own text).
#
# Word gaps are a single space, not ``\s+``, for the reason the intro-marker
# above records: every caller feeds ``_normalize_space``d text, and the
# classifier-safety gate refuses adjacent variable repeats.
_NO_COLLECTIVE_REENACTMENT_TAIL_RE = compile_classifier_regex(
    r"\bskal følgende (?:bestemmelser|paragrafer) lyde:?$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.collective_reenactment_lead",
)
# ``blir §`` and ``blir ny §`` are both attested inside one part of the witness
# ("Nåværende § 12 blir § 14." beside "Nåværende § 16 blir ny § 20."). The
# ordinary unstructured renumber production (which requires ``blir ny``) is
# deliberately left untouched: widening it would move ops in acts this item
# never measured.
# Plain integer labels, optionally letter-suffixed — the shape every measured
# renumber in the family carries (12→14, 13→15, 16→20, 17→21, 18→22). A
# chapter-numbered ``§ 12-3`` label would refuse the part rather than half-lower
# it, which is the all-or-nothing contract, not an oversight.
_NO_COLLECTIVE_SECTION_LABEL = r"([0-9]+ ?[A-Za-z]?)"
_NO_COLLECTIVE_RENUMBER_RE = compile_classifier_regex(
    r"^Nåværende § " + _NO_COLLECTIVE_SECTION_LABEL + r" blir (?:ny )?§ "
    + _NO_COLLECTIVE_SECTION_LABEL + r"\.?$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.collective_reenactment_renumber",
)
_NO_COLLECTIVE_TITLE_MARKER_RE = compile_classifier_regex(
    r"^Lovens tittel:?$",
    re.IGNORECASE,
    classifier_id="no.lovtidend.collective_reenactment_title_marker",
)
NO_PARSE_COLLECTIVE_REENACTMENT_PART_UNRESOLVED = (
    "no_parse_collective_reenactment_part_unresolved"
)
NO_PARSE_COLLECTIVE_REENACTMENT_TITLE_NOT_LOWERED = (
    "no_parse_collective_reenactment_title_not_lowered"
)


def _no_collective_reenactment_lead_base_id(lead: str) -> str | None:
    """Resolve ``I lov <cite> skal følgende bestemmelser lyde:`` to its law."""
    lead = _repair_no_mojibake(_normalize_space(lead))
    # lawvm-regex: owning_parser strips the enumeration ordinal ahead of the head anchor,
    # exactly as the two sibling part-lead resolvers do
    lowered = re.sub(_NO_LEAD_ITEM_ORDINAL_PREFIX, "", lead.lower()).strip()
    if not lowered.startswith("i lov"):
        return None
    # lawvm-regex: owning_parser this IS the collective re-enactment lead parser
    if _NO_COLLECTIVE_REENACTMENT_TAIL_RE.search(lead) is None:
        return None
    return _extract_no_law_citation_base_id(lead)


def _no_future_section_label(node: etree._Element) -> str:
    return _normalize_no_section_label(node.get("data-name", "") or "")


def _lower_no_collective_reenactment_part(
    part_children: Sequence[etree._Element],
    *,
    source_id: str,
    base_id: str,
    start_sequence: int,
    adjudications_out: Optional[List[CompileAdjudication]],
) -> tuple[list[LegalOperation], int] | None:
    """Lower one collective re-enactment part, all-or-nothing (W-19).

    Every member of the part must fall into the closed set below; one member
    that does not refuses the WHOLE part, because a partially applied
    re-enactment is not a partial law — it is a wrong one. Returns ``None``
    after recording a typed receipt in that case, leaving the ordinary walk to
    produce exactly the receipts it produced before this production existed.

    The closed member set, every kind of it measured on the three carriers:

    * a ``futureLegalArticle`` — the section's whole new text, at the address
      its own ``data-name`` states;
    * ``Nåværende § X blir [ny] § Y.`` — a pure renumber;
    * ``[Ny] § X skal lyde:`` — a marker whose payload is the NEXT
      ``futureLegalArticle``; the labels must agree, and ``Ny`` forces INSERT;
    * ``Lovens tittel:`` plus the restated title — recognized, NOT lowered
      (there is no law-title op in the Norway lowering), receipted so the drop
      is on the record rather than silent;
    * the part's own ``<h2>`` heading, inert.
    """
    ops: list[LegalOperation] = []
    sequence = start_sequence
    renumbers: list[tuple[str, str, str]] = []
    payloads: list[tuple[str, StructuralAction, IRNode, str]] = []
    pending_marker: tuple[str, StructuralAction, str] | None = None
    title_marker_lead = ""

    def refuse(reason: str, member: str) -> None:
        _append_no_unstructured_parse_adjudication(
            adjudications_out,
            kind=NO_PARSE_COLLECTIVE_REENACTMENT_PART_UNRESOLVED,
            message=(
                "Norway collective re-enactment part refused: a member of the part did "
                "not fall in the closed member set, so the whole part stays unlowered."
            ),
            source_id=source_id,
            lead=member,
            base_id=base_id,
            detail={"refusal": reason, "part_family": "collective_reenactment"},
        )

    index = 0
    while index < len(part_children):
        node = part_children[index]
        index += 1
        name = _local_name(node)
        if name in {"h1", "h2", "h3", "h4"}:
            continue
        if name != "article":
            refuse("non_article_member", f"<{name}>")
            return None
        classes = _classes(node)
        text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
        if "futureLegalArticle" in classes:
            label = _no_future_section_label(node)
            if not label:
                refuse("future_section_without_label", text[:200])
                return None
            payload = _parse_future_section(node)
            if payload is None:
                refuse("future_section_payload_unresolved", text[:200])
                return None
            action = StructuralAction.REPLACE
            if pending_marker is not None:
                marker_label, marker_action, marker_lead = pending_marker
                if marker_label != label:
                    refuse("marker_label_disagrees_with_payload", marker_lead)
                    return None
                action = marker_action
                pending_marker = None
                text = marker_lead
            payloads.append((label, action, payload, text))
            continue
        if pending_marker is not None:
            refuse("marker_without_following_section", pending_marker[2])
            return None
        if not ({"defaultP", "legalP"} & classes):
            refuse("unsupported_member_class", text[:200])
            return None
        if title_marker_lead:
            # The node after ``Lovens tittel:`` is the restated title itself.
            _append_no_unstructured_parse_adjudication(
                adjudications_out,
                kind=NO_PARSE_COLLECTIVE_REENACTMENT_TITLE_NOT_LOWERED,
                message=(
                    "Norway collective re-enactment part restates the law's title; the "
                    "Norway lowering has no law-title operation, so the restatement is "
                    "recorded and not applied."
                ),
                source_id=source_id,
                lead=f"{title_marker_lead} {text}"[:400],
                base_id=base_id,
                detail={"new_title": text[:200], "part_family": "collective_reenactment"},
            )
            title_marker_lead = ""
            continue
        # lawvm-regex: owning_parser this IS the collective re-enactment member parser
        renumber_match = _NO_COLLECTIVE_RENUMBER_RE.match(text)
        if renumber_match is not None:
            renumbers.append(
                (
                    _normalize_no_section_label(renumber_match.group(1)),
                    _normalize_no_section_label(renumber_match.group(2)),
                    text,
                )
            )
            continue
        # lawvm-regex: owning_parser this IS the collective re-enactment member parser
        if _NO_COLLECTIVE_TITLE_MARKER_RE.match(text) is not None:
            title_marker_lead = text
            continue
        # The SAME whole-section lead pattern the ordinary unstructured lowering
        # consumes, reused so a marker inside a collective part and a lead
        # outside one recognize the identical surface.
        # lawvm-regex: owning_parser this IS the whole-section lead parser
        section_match = _NO_WHOLE_SECTION_LEAD_RE.match(text)
        if section_match is not None and not _normalize_space(section_match.group("inline")):
            pending_marker = (
                _normalize_no_section_label(section_match.group("label")),
                StructuralAction.INSERT if section_match.group("insert") else StructuralAction.REPLACE,
                text,
            )
            continue
        refuse("member_outside_closed_set", text[:200])
        return None

    if pending_marker is not None:
        refuse("marker_without_following_section", pending_marker[2])
        return None
    if title_marker_lead:
        refuse("title_marker_without_restatement", title_marker_lead)
        return None
    if not payloads and not renumbers:
        refuse("part_carried_no_member", "")
        return None

    payload_labels = [label for label, _action, _payload, _lead in payloads]
    renumber_sources = [src for src, _dst, _lead in renumbers]
    renumber_destinations = [dst for _src, dst, _lead in renumbers]
    if len(set(payload_labels)) != len(payload_labels):
        refuse("duplicate_payload_address", ", ".join(payload_labels))
        return None
    if len(set(renumber_sources)) != len(renumber_sources):
        refuse("duplicate_renumber_source", ", ".join(renumber_sources))
        return None
    if len(set(renumber_destinations)) != len(renumber_destinations):
        refuse("duplicate_renumber_destination", ", ".join(renumber_destinations))
        return None
    # A renumber DESTINATION that the same part also restates is the one shape
    # this ordering cannot adjudicate: renumber-first would have the payload
    # overwrite the moved section, payload-first would move the payload. Neither
    # reading is the drafter's without more evidence, so refuse.
    collision = sorted(set(renumber_destinations) & set(payload_labels))
    if collision:
        refuse("renumber_destination_is_also_restated", ", ".join(collision))
        return None

    for src_label, dst_label, lead in renumbers:
        ops.append(
            LegalOperation(
                op_id=f"{source_id}:{sequence}",
                sequence=sequence,
                action=StructuralAction.RENUMBER,
                target=LegalAddress(path=(("section", src_label),)),
                destination=LegalAddress(path=(("section", dst_label),)),
                source=OperationSource(statute_id=source_id, raw_text=lead, title=base_id),
                provenance_tags=(f"base_act:{base_id}", "fallback:unstructured", "scope:collective_reenactment"),
                group_id=f"{source_id}:{base_id}:{sequence}",
                witness_rule_id="no_section_renumber_relabel",
            )
        )
        sequence += 1
    for label, action, payload, lead in payloads:
        ops.append(
            LegalOperation(
                op_id=f"{source_id}:{sequence}",
                sequence=sequence,
                action=action,
                target=LegalAddress(path=(("section", label),)),
                payload=payload,
                source=OperationSource(statute_id=source_id, raw_text=lead, title=base_id),
                provenance_tags=(f"base_act:{base_id}", "fallback:unstructured", "scope:collective_reenactment"),
                group_id=f"{source_id}:{base_id}:{sequence}",
            )
        )
        sequence += 1
    return ops, sequence


def _infer_no_unstructured_section_base_id(children: list[etree._Element]) -> str | None:
    for child in children:
        if _local_name(child) != "article" or not ({"defaultP", "legalP"} & _classes(child)):
            continue
        lead = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in child.itertext())))
        embedded = _extract_no_embedded_multi_act_lead(lead)
        if embedded is not None:
            return embedded[0]
        section_base_id = _extract_no_section_base_id_from_lead(lead)
        if section_base_id is not None:
            return section_base_id
        announced_base_id = _extract_no_law_announcement_base_id(lead)
        if announced_base_id is not None:
            return announced_base_id
        # W-39. The collective re-enactment announcement is the third part-lead
        # spelling, and the only one whose tail states an END STATE rather than
        # an amending action. Resolving it here — beside its two siblings, not
        # in a fourth resolver — is what makes the part's law visible to BOTH
        # consumers of this function: the unstructured walk's ``part_base_ids``
        # and W-24's ``_no_part_base_id`` (which the W-39 part-scoped
        # commencement gate reads as its scope proof).
        collective_base_id = _no_collective_reenactment_lead_base_id(lead)
        if collective_base_id is not None:
            return collective_base_id
    return None


def _no_unstructured_law_switch_lead_base_id(lead: str) -> str | None:
    """Resolve the base act iff ``lead`` OPENS with a law-switch of its own.

    The payload cursor's second boundary (W-34), the W-15 part boundary carried
    down to numbered enumeration items. The predicate has to separate two things
    the corpus mixes freely inside one part:

    * a SIBLING enumeration item that switches law ("59. I lov 16. juni 1967
      nr. 3 … skal § 2 lyde:") — the cursor must stop, or the item's own op is
      lost and every later item binds to a stale base act; and
    * QUOTED amendment text inside a payload — statutory prose that happens to
      carry a law citation, up to and including a whole nested amending
      instruction. Tearing those apart would destroy the payload.

    The W-21 witness `2009-06-19-74` is where that risk is sharpest: its new
    § 412 "Endringer i andre lover" introduces a run of nested consequential
    items. Measured, that witness is untouched — its nested items are all
    ``defaultP``, which the cursor has always treated as a boundary, and the
    § 412 payload itself is a single ``futureLegalArticle``. Its 483 ops are
    byte-identical across this change. The class the cursor CAN reach is the
    ``legalP`` sibling, and that is what the census below is over.

    Measured 2026-08-07 over all 2,761 unstructured artifacts: 299 distinct
    nodes are crossed by some payload run and resolve a law under any of the
    three lead resolvers. Two candidate signals fail outright and are recorded
    here so they are not re-proposed: DOM depth and parenthood discriminate
    nothing (all 299 share their enclosing lead's parent — the part flatten has
    already erased the nesting), and the item ordinal is not necessary (260 of
    the 299 carry one; the other 39 are ordinary un-numbered part leads).

    What does separate them is where the citation sits. After the item ordinal
    is stripped, the text preceding the citation is exactly four spellings over
    297 of the 299 rows — ``I `` (290), the empty prefix (3, the nominative
    ``Lov … endres slik``), ``I endringen i `` (2) and ``I endringene i `` (2) —
    none of which closes a sentence. The remaining 2 are Lovdata run-on nodes
    that concatenate one lead's payload with the NEXT lead
    (`2004-06-25-53` [180], `2005-06-17-84` [81]): their citation sits 97 and
    195 characters in, behind a completed sentence of quoted statutory text.
    Requiring the citation to fall in the node's first sentence therefore admits
    all 297 genuine leads and rejects both run-ons, with no threshold to tune.
    The run-ons stay collected as payload, which is what they half are; the
    lead buried in their tail is a separate, older defect and is not this
    predicate's to fix.

    ``_extract_no_embedded_multi_act_lead`` and
    ``_extract_no_law_announcement_base_id`` are already head-anchored (both
    ``re.match``), so only the ``I lov … gjøres følgende endringer`` resolver
    needs the guard; it alone searches for its marker anywhere in the lead.
    """
    lead = _repair_no_mojibake(lead)
    embedded = _extract_no_embedded_multi_act_lead(lead)
    if embedded is not None:
        return embedded[0]
    announced = _extract_no_law_announcement_base_id(lead)
    if announced is not None:
        return announced
    section_base_id = _extract_no_section_base_id_from_lead(lead)
    if section_base_id is None:
        return None
    stripped = re.sub(_NO_LEAD_ITEM_ORDINAL_PREFIX, "", lead)
    # Recognizes nothing new: the same pattern object
    # ``_extract_no_section_base_id_from_lead`` has ALREADY matched above, run
    # again only to read off WHERE in the lead the citation sits.
    # lawvm-regex: witness_only position of an already-resolved citation
    citation = re.search(_NO_LAW_CITATION_PATTERN, stripped, re.IGNORECASE)
    if citation is None:
        # W-28: the same probe for the numberless spelling. Without it a lead that
        # resolves only through the pre-numbering branch is admitted by
        # ``_extract_no_section_base_id_from_lead`` and then dropped here, so the
        # freed leads W-36 hands over would still never become a cursor boundary.
        # lawvm-regex: witness_only position of an already-resolved citation
        citation = re.search(_NO_LAW_CITATION_NUMBERLESS_PATTERN, stripped, re.IGNORECASE)
    if citation is None:
        # Resolved only through the ``… av <date> nr N`` tail fallback, which no
        # crossed node in the corpus uses. Nothing anchors the head, so the
        # cursor keeps collecting rather than guessing at a boundary.
        return None
    if "." in stripped[: citation.start()]:
        return None
    return section_base_id


def _no_element_lead_text(element: etree._Element) -> str:
    """The lead/payload text of one element, as every boundary predicate reads it."""
    return _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in element.itertext())))


# Non-``article`` wrappers Lovdata puts between a run-on node and the lead it
# swallowed, plus the two ``article`` classes that are pure wrappers. Measured
# over the whole run-on population (W-36): the freed subtree is reached through
# ``ul.defaultList`` → ``li`` → ``article.listArticle`` and nothing else, and
# ``legalArticle`` is here only because the flatten above already treats it as a
# splice-through container, so the two rules cannot disagree.
_NO_RUN_ON_WRAPPER_TAGS = frozenset({"ul", "ol", "li"})
_NO_RUN_ON_WRAPPER_CLASSES = frozenset({"listArticle", "legalArticle"})
# The node classes a run-on can hide a lead inside. ``numberedLegalP`` is not
# decoration: the ledger's three named witnesses (`2014-05-09-16` item 17,
# `2015-06-19-65` item 107, `2016-06-17-29` item 11) are all numbered paragraphs
# whose lead hangs off a ``(N)`` subsection, which is never a lead itself.
_NO_RUN_ON_LEAD_NODE_CLASSES = frozenset({"defaultP", "legalP", "numberedLegalP"})


def _no_unwrap_run_on_freed_node(element: etree._Element) -> list[etree._Element]:
    """Reduce a freed subtree to the ``article`` nodes the sibling stream reads.

    The sibling walk only recognizes ``article`` elements, so a freed
    ``ul.defaultList`` would be skipped outright and the lead lost a second time.
    Unwrapping is total and order-preserving; a wrapper carrying its own text is
    kept whole rather than unwrapped, so no text can be dropped on the way out.
    """
    is_wrapper = _local_name(element) in _NO_RUN_ON_WRAPPER_TAGS or (
        _local_name(element) == "article" and bool(_NO_RUN_ON_WRAPPER_CLASSES & _classes(element))
    )
    if not is_wrapper:
        return [element]
    if (element.text or "").strip():
        return [element]
    unwrapped: list[etree._Element] = []
    for kid in _direct_children(element):
        unwrapped.extend(_no_unwrap_run_on_freed_node(kid))
        if (kid.tail or "").strip():
            return [element]
    return unwrapped or [element]


def _no_run_on_lead_boundary_path(element: etree._Element) -> tuple[int, ...] | None:
    """Index path to the OUTERMOST descendant of ``element`` that opens a lead.

    Pre-order, so the shallowest enclosing element whose own text already reads
    as a law-switch lead wins: a ``ul`` holding nothing but the lead is the
    boundary, while a ``ul`` whose first ``li`` is genuine payload is descended
    into and the boundary lands on the later ``li``.
    """

    def walk(node: etree._Element, prefix: tuple[int, ...]) -> tuple[int, ...] | None:
        for index, kid in enumerate(_direct_children(node)):
            path = (*prefix, index)
            if _no_unstructured_law_switch_lead_base_id(_no_element_lead_text(kid)) is not None:
                return path
            found = walk(kid, path)
            if found is not None:
                return found
        return None

    return walk(element, ())


def _split_no_run_on_lead_node(
    element: etree._Element,
) -> tuple[etree._Element, list[etree._Element]] | None:
    """Split one Lovdata run-on node into (payload head, freed lead nodes)."""
    if _no_unstructured_law_switch_lead_base_id(_no_element_lead_text(element)) is not None:
        # The node OPENS with a lead of its own; W-34's sibling boundary owns it.
        return None
    path = _no_run_on_lead_boundary_path(element)
    if path is None:
        return None
    # Copy rather than mutate: ``root`` belongs to the caller, and the structured
    # reader and the rettelse reader walk the same tree.
    truncated = copy.deepcopy(element)
    chain: list[tuple[etree._Element, int]] = []
    node = truncated
    for index in path:
        chain.append((node, index))
        node = _direct_children(node)[index]
    freed: list[etree._Element] = []
    for depth, (parent, index) in enumerate(reversed(chain)):
        kids = _direct_children(parent)
        # At the boundary's own level the boundary leaves too; at every shallower
        # level the element on the path is the truncated head and stays.
        tail = kids[index:] if depth == 0 else kids[index + 1 :]
        for kid in tail:
            parent.remove(kid)
        freed.extend(tail)
    head = _no_element_lead_text(truncated)
    if not head:
        return None
    # lawvm-regex: owning_parser the same lead grammar `_extract_no_section_base_id_from_lead` owns
    if head.endswith(":") and _NO_SECTION_INTRO_MARKER_RE.search(head.lower()) is None:
        # The head is an amendment DIRECTIVE whose colon opens its own payload, so
        # the nested lead is quoted content — a consequential-amendments section
        # being enacted verbatim — not a swallowed lead. Measured over the whole
        # DOM-boundary population (57): 52 heads end a sentence and 5 end in a
        # colon, and those 5 divide exactly on this marker. The 3 that carry it
        # are part intros ("Fra den tid loven trer i kraft, gjøres følgende
        # endringer i andre lover:") whose colon introduces the consequential
        # LIST, and freeing it is the whole point. The 2 that do not are
        # `2006-06-16-32` "§ 17-3 nr. 4 skal lyde:" and `2009-06-19-100`
        # "§ 35-1 nr. 8 skal lyde:" — plan- og bygningsloven's own § 35-1
        # consequential list, quoted as the new text of that provision. Splitting
        # those emitted an op against kulturminneloven that the act never made.
        return None
    unwrapped: list[etree._Element] = []
    for kid in freed:
        unwrapped.extend(_no_unwrap_run_on_freed_node(kid))
    return truncated, unwrapped


def _split_no_run_on_lead_nodes(
    children: list[etree._Element],
    section_base_ids: list[str | None],
    child_part_indexes: list[int],
) -> int:
    """Lift law-switch leads Lovdata RAN ON into the preceding item's payload node.

    W-34 stopped the payload cursor at a sibling law-switch lead and W-35 lifted
    the leads trapped inside a ``futureLegalArticle``. This is the last reachable
    member of the family: the lead is not a sibling and not trapped in an
    inserted section — it hangs INSIDE the previous item's own payload node, so
    the node reads as one paragraph that concatenates one lead's payload tail
    with the next lead's head.

    The ledger proposed the W-34 predicate at SENTENCE granularity. Measured
    that way over all 2,761 unstructured artifacts, 69 nodes are not a lead
    themselves yet carry a later sentence that fully parses as one — and the
    measurement immediately says the sentence is the wrong unit. The run-on is
    not a text defect at all: in 58 of the 69 the swallowed lead has its OWN
    ELEMENT (a nested ``article.legalP``; a ``ul.defaultList`` holding nothing
    else; a later ``li`` of such a list). Lovdata gave the lead a paragraph and
    then closed the enclosing paragraph too late, so the run-on exists only in
    the ``itertext()`` concatenation. Of the other 11, 10 are a node whose text
    merely OPENS with a bare item ordinal (``258.``, ``a.``) that the splitter
    cuts off — nothing is swallowed there, the node is a single lead the
    ordinal-aware head anchors miss — and 1 is the citing-prose false positive
    the ledger predicted: `2015-06-19-48` § 3, quoted statutory text whose later
    sentence begins "I den utstrekning en klage gjelder et spørsmål …".
    Anchoring the boundary on an ELEMENT rejects both by construction, with
    nothing to tune.

    Walking the DOM rather than the sentence stream also finds 4 run-ons the
    sentence census cannot see, because a colon does not end a sentence — and
    those are what make the second, load-bearing guard necessary. Over the
    resulting population of 62, 57 heads end a sentence and 5 end in a colon,
    and a colon means the head INTRODUCES what follows. Those 5 divide exactly
    on ``_NO_SECTION_INTRO_MARKER_RE``, W-30's measured grammar for "the
    following changes are made": the 3 that carry it are part intros ("Fra den
    tid loven trer i kraft, gjøres følgende endringer i andre lover:") whose
    colon opens the consequential LIST, and freeing it is the point. The 2 that
    do not are `2006-06-16-32` "§ 17-3 nr. 4 skal lyde:" and `2009-06-19-100`
    "§ 35-1 nr. 8 skal lyde:" — plan- og bygningsloven's own § 35-1
    consequential list, quoted verbatim as that provision's new text. They carry
    the identical markup to the 57 and are genuine content; splitting them
    emitted a kulturminneloven op the act never made.

    So: 60 split over 12 acts, 2 held back. The freed nodes re-enter
    ``children`` immediately after the truncated head, where the W-34 cursor
    stop, the W-21/W-30 base inference and the W-15 part boundaries all apply to
    them unchanged, and the pass does not skip them so a freed node that is
    itself a run-on chains.

    External check, recomputed from the raw document at sentence granularity so
    that it sees mid-node leads and never consults this split: over the acts
    W-36 and W-28 touch together, ops agreeing with their governing lead go
    2,634 → 2,983 and disagreements 286 → 41, with no artifact getting worse.

    ``2005-06-17-84`` [81] — W-34's other predicate-reject — is deliberately NOT
    reached: its nested lead reads "I nr. 34 gjøres følgende endringer i
    endringene i lov 26. juni 1992 nr. 86 …", an amendment OF AN AMENDMENT whose
    base act is this act's own item 34, not tvangsfullbyrdelsesloven. The W-34
    predicate declines it (a period precedes the citation) and binding it would
    be a wrong answer, not a recovered one.
    """
    split_count = 0
    position = 0
    while position < len(children):
        element = children[position]
        position += 1
        if _local_name(element) != "article":
            continue
        classes = _classes(element)
        if "futureLegalArticle" in classes:
            # A run-on that sits inside an inserted section's payload: split it
            # in place, so the W-35 pass below sees an ordinary trapped lead and
            # lifts it the rest of the way out.
            rebuilt = copy.deepcopy(element)
            kids = _direct_children(rebuilt)
            replacement: list[etree._Element] | None = None
            for kid_index, kid in enumerate(kids):
                if not (_NO_RUN_ON_LEAD_NODE_CLASSES & _classes(kid)):
                    continue
                result = _split_no_run_on_lead_node(kid)
                if result is None:
                    continue
                truncated_kid, freed_kid = result
                replacement = [*kids[:kid_index], truncated_kid, *freed_kid, *kids[kid_index + 1 :]]
                break
            if replacement is not None:
                for old in kids:
                    rebuilt.remove(old)
                for new in replacement:
                    rebuilt.append(new)
                children[position - 1] = rebuilt
                split_count += 1
            continue
        if not (_NO_RUN_ON_LEAD_NODE_CLASSES & classes):
            continue
        result = _split_no_run_on_lead_node(element)
        if result is None:
            continue
        truncated, freed = result
        children[position - 1] = truncated
        children[position:position] = freed
        section_base_ids[position:position] = [section_base_ids[position - 1]] * len(freed)
        child_part_indexes[position:position] = [child_part_indexes[position - 1]] * len(freed)
        split_count += 1
        # Do not skip the freed nodes: one of them may itself be a run-on.
    return split_count


def _split_no_trapped_payload_leads(
    children: list[etree._Element],
    section_base_ids: list[str | None],
    child_part_indexes: list[int],
) -> int:
    """Lift law-switch leads TRAPPED inside ``futureLegalArticle`` payloads out to sibling level.

    W-34 stopped the payload cursor at a sibling law-switch lead. This is the
    same boundary one level further in: Lovdata's markup sometimes closes an
    inserted section's ``futureLegalArticle`` LATE, so the enumeration items
    that follow it — their leads and their own quoted payloads — end up as
    CHILDREN of the inserted section instead of siblings of it. The cursor
    cannot reach them there; they are neither collected nor lowered, and the
    inserted section's payload silently carries a foreign act's amendment text.

    The split is positional and total: the FIRST direct child on which the W-34
    predicate fires opens the trapped tail, and everything from there to the end
    of the element leaves it, in document order, re-entering ``children``
    immediately after the (truncated) element. Nothing downstream is special
    cased — the freed leads are ordinary siblings, so the W-34 cursor stop, the
    W-21/W-30 base inference and the W-15 part boundaries all apply to them
    unchanged, including to a freed lead whose own payload is the NEXT
    ``futureLegalArticle`` sibling (`2016-06-17-29` § 8-8 → § 10a).

    Measured 2026-08-07 over all 2,761 unstructured artifacts: 7,538
    ``futureLegalArticle`` elements are crossed by some payload run, and exactly
    41 of them contain a trapped lead — 52 leads over 6 artifacts. Every one of
    the 52 is ``legalP``, the same class W-34's sibling boundary uses, and none
    sits at child position 0, so every element keeps its header and 40 of 41
    keep at least one body node (the exception is `2015-06-19-65` § 9-3, whose
    lead is "§ 9-3 overskriften skal lyde:" — a heading-only payload by
    request).

    That the tail is markup error and not the inserted section's own content is
    settled by the enumeration, not by a threshold. 50 of the 52 open with an
    item ordinal; taken per artifact, those ordinals are DISJOINT from every
    ordinal that already opens a sibling lead and each one fills a GAP in that
    artifact's enumeration — 42/42 in `2015-06-19-65`, and in `2015-09-04-85`,
    `2016-06-17-29` and `2016-08-12-77` the split closes the run completely
    (0 gaps left). A quoted citation inside genuine inserted content could not
    do that: it would have to duplicate a number the artifact uses elsewhere or
    invent one outside the run. The other 2 (`2013-12-13-106` § 15-6 and
    § 14-3) are un-numbered part leads, and there the tail opens with the
    ``centeredP`` roman marker of the NEXT part ("III", "IV") flattened into the
    section — the part boundary itself is in the payload. Those markers stay in
    the truncated element deliberately: ``_parse_future_section`` reads only
    ``legalP``/``defaultP``/``numberedLegalP`` children, so a ``centeredP`` is
    already invisible to the payload, and moving it would be a second rule
    buying a byte-identical result.

    The W-21 § 412 witness `2009-06-19-74` is the case this must not touch: 184
    ``futureLegalArticle`` elements, 0 trapped leads. Its nested consequential
    items are ``defaultP`` siblings, which have always been a cursor boundary.
    """
    split_count = 0
    position = 0
    while position < len(children):
        element = children[position]
        position += 1
        if _local_name(element) != "article" or "futureLegalArticle" not in _classes(element):
            continue
        kids = _direct_children(element)
        boundary = None
        for kid_index, kid in enumerate(kids):
            kid_text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in kid.itertext())))
            if _no_unstructured_law_switch_lead_base_id(kid_text) is not None:
                boundary = kid_index
                break
        if boundary is None:
            continue
        # Copy rather than mutate: ``root`` belongs to the caller, and the
        # structured reader walks the same tree.
        truncated = copy.deepcopy(element)
        freed = _direct_children(truncated)[boundary:]
        for node in freed:
            truncated.remove(node)
        children[position - 1] = truncated
        children[position:position] = freed
        section_base_ids[position:position] = [section_base_ids[position - 1]] * len(freed)
        child_part_indexes[position:position] = [child_part_indexes[position - 1]] * len(freed)
        split_count += 1
        # Do not skip the freed nodes: one of them may itself be a
        # ``futureLegalArticle`` carrying a further trapped lead, which is the
        # `2016-06-17-29` § 8-8 → § 10a → item 9 chain.
    return split_count


def _promote_no_replace_with_following_renumber_insert(
    ops: list[LegalOperation],
) -> list[LegalOperation]:
    """Treat replace+same-target-renumber as insertion of new content.

    If an amendment says content at address X "skal lyde" and separately says the
    current content at X becomes the new X+1, the semantic effect is insertion of
    new content at X plus renumbering of the old X.
    """
    renumber_targets = {
        op.target.path for op in ops if op.action is StructuralAction.RENUMBER and op.destination is not None
    }
    promoted: list[LegalOperation] = []
    for op in ops:
        if (
            op.action is StructuralAction.REPLACE
            and op.payload is not None
            and op.target.path in renumber_targets
            and _no_kind_value(op.payload.kind) == op.target.leaf_kind()
        ):
            promoted.append(
                dc_replace(
                    op,
                    action=StructuralAction.INSERT,
                    provenance_tags=(
                        *op.provenance_tags,
                        NO_PARSE_REPLACE_PROMOTED_TO_INSERT_FOR_RENUMBER,
                    ),
                )
            )
            continue
        promoted.append(op)
    return promoted


def _extract_no_embedded_multi_act_lead(lead: str) -> tuple[str, str] | None:
    lead = _repair_no_mojibake(lead)
    patterns = _NO_EMBEDDED_MULTI_ACT_PATTERNS
    match = None
    for pattern in patterns:
        match = re.match(pattern, lead, re.IGNORECASE)
        if match is not None:
            break
    if match is None:
        return None
    day = int(match.group(1))
    month = _NORWEGIAN_MONTH_NUMBERS.get(match.group(2).lower())
    year = match.group(3)
    if month is None:
        return None
    # W-28: the numberless patterns carry no number group, so the embedded lead
    # is group 4 rather than 5, and the act resolves only if the corpus attests
    # this date as a numberless one.
    lead_group = match.re.groups
    if lead_group == 4:
        base_id = _no_numberless_law_base_id(day, month, year)
        if base_id is None:
            return None
        number = _NO_NUMBERLESS_LAW_NUMBER
    else:
        number = int(match.group(4))
    # An intervening ``ny``/``nytt``/``nye`` qualifier immediately before the
    # ``§`` means the section is being inserted, not replaced; surface it as the
    # ``Ny § …`` prefix that the ``_NO_WHOLE_SECTION_LEAD_RE`` insert branch
    # recognizes.
    insert_qualifier = bool(re.search(r"\bskal\s+ny(?:tt|e)?\s+$", lead[: match.start(lead_group)], re.IGNORECASE))
    embedded_lead = match.group(lead_group).strip()
    if " skal " not in embedded_lead.lower():
        embedded_lead = re.sub(r"\s+lyd([ea]):?$", r" skal lyd\1:", embedded_lead, flags=re.IGNORECASE)
    if insert_qualifier and not re.match(r"^ny(?:tt|e)?\b", embedded_lead, re.IGNORECASE):
        embedded_lead = f"Ny {embedded_lead}"
    return (f"no/lov/{year}-{month}-{day:02d}-{number}", embedded_lead)


def _extract_no_section_base_id_from_lead(lead: str) -> str | None:
    lead = _repair_no_mojibake(lead)
    lowered = lead.lower()
    lowered = re.sub(_NO_LEAD_ITEM_ORDINAL_PREFIX, "", lowered)
    if not lowered.startswith("i "):
        return None
    # ``lowered`` is already lower-cased, so the marker carries no IGNORECASE.
    # lawvm-regex: owning_parser this IS the part-announcement lead parser
    if _NO_SECTION_INTRO_MARKER_RE.search(lowered) is None:
        return None
    return _extract_no_law_citation_base_id(lead)


def _extract_no_law_announcement_base_id(lead: str) -> str | None:
    """Resolve the ``Lov <date> nr. N om X endres slik:`` part announcement.

    A sibling of ``_extract_no_section_base_id_from_lead`` for the older
    Lovtidend generation that announces a part's base act in the nominative
    ("Lov 20. mai 2005 nr. 28 om straff endres slik:") rather than as an
    ``I lov …`` prepositional lead. Measured 2026-08-06 over all 9,100
    unstructured parts: 69 parts match, across four tail surfaces only —
    ``endres slik`` (29), ``blir endra slik`` (20), ``vert endra slik`` (18),
    ``blir endret slik`` (2). No ``Lov <cite> … gjøres følgende endringer`` form exists
    (extending the tail set with the ``section_intro_markers`` above changes
    nothing corpus-wide), so the tail stays narrow. 67 of the 69 currently
    resolve nothing; the other 2 fall through to a consequential ``I lov …``
    item nested deep in the part's payload and resolve the wrong act
    (`2008-03-07-4`, `2009-06-19-74`).

    Only the amending tail makes this a part announcement. A bare citation
    ("Lov 22. mai 1902 nr. 13 § 107 oppheves.", "Lov … om domstolene") names a
    law the part acts *on as a whole* and introduces no items to bind, so it
    must not seed the part's base act.
    """
    lead = _repair_no_mojibake(lead)
    # Item ordinals ("1.", "1 a.") prefix announcements inside enumerated lists.
    lowered = re.sub(_NO_LEAD_ITEM_ORDINAL_PREFIX, "", lead.lower()).strip()
    # lawvm-regex: owning_parser this IS the part-announcement lead parser
    if not re.match(r"^lov[ai]?\b", lowered):
        return None
    # lawvm-regex: owning_parser this IS the part-announcement lead parser
    if not re.search(r"\b(?:endres|endras|endrast|endret|endra|endrar)\s+slik\s*:?\s*$", lowered):
        return None
    return _extract_no_law_citation_base_id(lead)


def _no_numberless_law_base_id(day: int, month: str, year: str) -> str | None:
    """The corpus id of the numberless act dated ``<year>-<month>-<day>``, if attested."""
    date = f"{year}-{month}-{day:02d}"
    if date not in _NO_NUMBERLESS_LAW_DATES:
        return None
    return f"no/lov/{date}-{_NO_NUMBERLESS_LAW_NUMBER}"


def _extract_no_law_citation_base_id(text: str) -> str | None:
    """Resolve the law a citation names, numbered spellings first.

    Rank, and it is load-bearing: the ``lov <date> nr N`` head form, then the
    ``… av <date> nr N`` tail form, then (W-28) the numberless pre-numbering form.
    The numberless branch is reached only when no numbered citation is present
    anywhere in ``text``, so it can never outrank a number the drafter wrote.
    """
    text = _repair_no_mojibake(text)
    match = re.search(_NO_LAW_CITATION_PATTERN, text, re.IGNORECASE)
    if match is None:
        fallback = re.search(_NO_LAW_CITATION_AV_PATTERN, text, re.IGNORECASE)
        if fallback is None:
            # lawvm-regex: owning_parser this IS the law-citation parser, numberless spelling
            numberless = re.search(_NO_LAW_CITATION_NUMBERLESS_PATTERN, text, re.IGNORECASE)
            if numberless is None:
                return None
            month = _NORWEGIAN_MONTH_NUMBERS.get(numberless.group(2).lower())
            if month is None:
                return None
            return _no_numberless_law_base_id(int(numberless.group(1)), month, numberless.group(3))
        prefix = text[max(0, fallback.start() - 80) : fallback.start()].lower()
        if "lov" not in prefix:
            return None
        match = fallback
    day = int(match.group(1))
    month = _NORWEGIAN_MONTH_NUMBERS.get(match.group(2).lower())
    year = match.group(3)
    number = int(match.group(4))
    if month is None:
        return None
    return f"no/lov/{year}-{month}-{day:02d}-{number}"


def _extract_no_law_citation_base_ids(text: str) -> list[str]:
    base_ids: list[str] = []
    for match in re.finditer(_NO_LAW_CITATION_PATTERN, text, re.IGNORECASE):
        day = int(match.group(1))
        month = _NORWEGIAN_MONTH_NUMBERS.get(match.group(2).lower())
        year = match.group(3)
        number = int(match.group(4))
        if month is None:
            continue
        base_ids.append(f"no/lov/{year}-{month}-{day:02d}-{number}")
    return list(dict.fromkeys(base_ids))


def _extract_no_global_text_replace_pairs(lead: str) -> list[tuple[str, str]]:
    return [
        (_normalize_space(old), _normalize_space(new))
        for old, new in _QUOTED_NO_TEXT_REPLACE_RE.findall(lead)
        if _normalize_space(old) and _normalize_space(new)
    ]


def _no_unstructured_lead_looks_operative(lead: str) -> bool:
    return bool(
        re.search(
            # ``skal(?:\s+\S+){1,5}?\s+lyde`` admits the intervening-qualifier
            # framing with one *or several* tokens between the ``skal`` verb and
            # ``lyde`` ("skal ny § X lyde", "skal ny § 4 a lyde", "skal nytt ledd
            # lyde"); the prior single-token bound silently dropped the multi-token
            # chapter-scoped insert leads. The trailing alternatives add the
            # nynorsk action verbs (gjer/vert gjort/gjerast/endrast/opphevast)
            # alongside the bokmål forms so genuinely operative leads are honestly
            # adjudicated rather than silently treated as inert prose.
            # W-99: ``skal § <address> lyde`` with the address of ANY depth —
            # "skal § 6-1 første ledd annet punktum lyde" is six tokens and the
            # bound above left it inert, so the 1997 nr. 44 lead that also
            # failed the citation grammar vanished with neither op nor refusal.
            # Anchored on the ``§`` right after ``skal`` (optionally ``ny``), so
            # prose that happens to hold ``skal`` and ``lyde`` far apart stays
            # inert. Corpus-measured 2026-09-05 (after-diff, not a text census
            # — the text census misread ``§`` through Lovdata's mojibake): 21
            # leads in 21 acts were silent drops and are now refused loudly,
            # every one operative ("I lov 21. juni 1963 nr. 23 skal § 60 andre
            # ledd første punktum lyde:", `2001-06-15-78`; "I kapittel 5 B skal
            # nye §§ 28-2 a til 28-2 v lyde:", `2012-05-25-28`). None lowers
            # yet — they are the next grammar gaps, now visible.
            r"(\bskal\s+lyde\b|\bskal(?:\s+\S+){1,5}?\s+lyde\b"
            r"|\bskal\s+(?:ny(?:tt|e)?\s+)?§.{0,120}?\blyde\b"
            r"|\boppheves\b|\bopphevast\b"
            r"|\bblir\b|\bendres\b|\bendrast\b|\btilf[øo]yes\b|\btilf[øo]yast\b"
            r"|\bf[øo]yes\b|\bf[øo]yast\b|\bflyttes\b|\bflyttast\b"
            r"|\bgjer\b|\bgjerast\b|\bvert\s+gjort\b)",
            lead,
            re.IGNORECASE,
        )
    )


def _no_address_detail(address: LegalAddress) -> str:
    return "/".join(f"{kind}:{label}" for kind, label in address.path)


def _append_no_unstructured_parse_adjudication(
    adjudications_out: Optional[List[CompileAdjudication]],
    *,
    kind: str,
    message: str,
    source_id: str,
    lead: str,
    base_id: str,
    detail: dict[str, object],
) -> None:
    _append_no_parse_adjudication(
        adjudications_out,
        kind=kind,
        message=message,
        source_id=source_id,
        detail=diagnostic_detail(
            rule_id=kind,
            family="unsupported_or_unresolved_action",
            phase="parse",
            blocking=True,
            source_excerpt=_normalize_space(lead)[:240],
            base_id=base_id,
            detail=detail,
        ),
    )


def _append_no_parse_adjudication(
    adjudications_out: Optional[List[CompileAdjudication]],
    *,
    kind: str,
    message: str,
    source_id: str,
    detail: dict[str, object],
) -> None:
    if adjudications_out is None:
        return
    adjudications_out.append(
        CompileAdjudication(
            kind=kind,
            message=message,
            source_statute=source_id,
            blocking=_no_adjudication_blocking(kind, detail),
            phase=_no_adjudication_phase(kind, detail),
            detail=detail,
        )
    )


def _no_adjudication_blocking(kind: str, detail: Mapping[str, object]) -> bool:
    blocking = detail.get("blocking")
    if not isinstance(blocking, bool):
        raise ValueError(
            f"Norway adjudication kind={kind!r} envelope is missing a typed "
            "'blocking'; build the detail via diagnostic_detail()."
        )
    return blocking


def _no_adjudication_phase(kind: str, detail: Mapping[str, object]) -> str:
    phase = detail.get("phase")
    if not isinstance(phase, str) or not phase:
        raise ValueError(
            f"Norway adjudication kind={kind!r} envelope is missing 'phase'; build the detail via diagnostic_detail()."
        )
    return phase


def _no_structured_spec_detail(
    specs: Sequence[tuple[StructuralAction, LegalAddress]],
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "action": _no_action_value(action),
            "target": _no_address_detail(target),
        }
        for action, target in specs
    )


def _append_no_structured_parse_recovery_adjudications(
    adjudications_out: Optional[List[CompileAdjudication]],
    *,
    source_id: str,
    base_id: str,
    source_doc: str,
    raw_text: str,
    reason: str,
    scope_confidence: NOScopeConfidence,
    original_specs: Sequence[tuple[StructuralAction, LegalAddress]],
    recovered_specs: Sequence[tuple[StructuralAction, LegalAddress]],
) -> None:
    """Emit adjudications for a structured-target recovery, carrying a typed scope witness.

    ``scope_confidence`` is a typed ``NOScopeConfidence`` (inheriting the
    ``lawvm.core.scope_confidence.ScopeConfidence`` marker protocol). The §2.2
    ladder rung is projected onto the detail-map string surface via
    ``.rung_id`` so the existing ``core.compile_result``'s string-typed
    ``scope_confidence`` reader continues to work byte-identically, while the
    producer boundary stays typed (AGENTS.md §1.9): a bare string cannot cross
    this signature or the ``LegalOperation.scope_confidence`` waist.
    """
    if not original_specs or list(original_specs) == list(recovered_specs):
        return
    scope_confidence_rung = scope_confidence.rung_id
    _append_no_parse_adjudication(
        adjudications_out,
        kind=NO_PARSE_STRUCTURED_TARGET_REBOUND_FROM_LEAD,
        message=(
            "Norway parser replaced structured target attributes with narrower "
            "targets inferred from the operative lead or payload."
        ),
        source_id=source_id,
        detail=diagnostic_detail(
            rule_id=NO_PARSE_STRUCTURED_TARGET_REBOUND_FROM_LEAD,
            phase="parse",
            family="target_resolution_recovery",
            blocking=True,
            reason=reason,
            base_id=base_id,
            source_doc=source_doc,
            scope_confidence=scope_confidence_rung,
            original_specs=_no_structured_spec_detail(original_specs),
            recovered_specs=_no_structured_spec_detail(recovered_specs),
            raw_text=raw_text,
        ),
    )
    original_actions = tuple(_no_action_value(action) for action, _target in original_specs)
    recovered_actions = tuple(_no_action_value(action) for action, _target in recovered_specs)
    if original_actions == recovered_actions:
        return
    _append_no_parse_adjudication(
        adjudications_out,
        kind=NO_PARSE_ACTION_RECOVERED_FROM_STRUCTURED_LEAD,
        message="Norway parser recovered structured operation action family from the operative lead.",
        source_id=source_id,
        detail=diagnostic_detail(
            rule_id=NO_PARSE_ACTION_RECOVERED_FROM_STRUCTURED_LEAD,
            phase="parse",
            family="action_family_recovery",
            blocking=True,
            reason=reason,
            base_id=base_id,
            source_doc=source_doc,
            scope_confidence=scope_confidence_rung,
            original_actions=original_actions,
            recovered_actions=recovered_actions,
            original_specs=_no_structured_spec_detail(original_specs),
            recovered_specs=_no_structured_spec_detail(recovered_specs),
            raw_text=raw_text,
        ),
    )


# ── Published errata (``Rettelser``) lowering — W-18 ──────────────────────────
#
# Lovdata publishes an editorial correction to an already-kunngjort act as a
# ``Rettelser`` block INSIDE that act's own artifact, written in canonical
# amending grammar ("§ 5 første ledd annet strekpunkt skal lyde: …"). The
# correction is therefore derivable from source bytes, so replaying it is not
# preferring the consolidation (NORWAY_LAWVM_STATUS.md §2.2) — it is reading the
# act's own published text completely.
#
# Corpus measurement (2026-08-05, 3,089 amendment artifacts): 25 artifacts carry
# a "Det som er rettet" block. They split into two generations:
#
#   * 11 artifacts / 12 notes (2017 →) wrap each correction in a machine-typed
#     ``<article class="gazettenote" data-gazette-note-type="rettelse"
#     data-gazette-note-date="…">``. That attribute is Lovdata's OWN erratum
#     marker and the only non-heuristic anchor in the corpus, so it — not the
#     word "rettet" — is what this rule keys on.
#   * 14 artifacts (2003–2011) carry the block as untyped sibling paragraphs
#     under an ``<h2>Rettelse(r)</h2>``, with the directive embedded in
#     narrative prose ("Ved en inkurie ble …", "I 2010 hefte 5 (Rettelse)") and
#     the target/payload boundary only positional. Deliberately OUT of this
#     rule's domain: no typed date, no typed directive, and measured payoff zero
#     — of those 14, only 2 address law text at all and neither law is a verify
#     candidate, so lowering them would move nothing while risking text
#     corruption.
#
# Of the 12 typed notes 3 resolve a clean address: the W-18 witness
# ``no/lovtid/2020-12-18-156`` (§ 5 første ledd annet strekpunkt, same-act) and,
# via the W-24 Del-scope resolution below, ``no/lovtid/2019-12-20-110`` Del I
# (kringkastingsloven § 8-2's heading) and ``no/lovtid/2023-12-20-98`` Del V
# (skatteloven § 5-42 bokstav a). The other 9 are excluded with a typed
# ``no_rettelse_not_lowered`` receipt naming which of the measured shapes
# stopped them:
#   * 7 correct publication metadata the IR does not model ("Referansefeltet …",
#     "Hjemmelsfeltet …") — a permanent recorded ceiling.
#   * ``2022-05-12-28``'s ``§ 73 nr. 7 § 6-7 …`` reaches another act through the
#     host act's own body WITHOUT naming it; only the host's ordinal position
#     could name it, so lowering would bind a law the directive never cites.
#     Excluded by the single-``§`` guard, receipted ``no_nested_cross_act_address``.
#   * ``2020-12-04-137`` Del IV and ``2025-06-20-101`` Del II resolve their part
#     and their law, but the host act's OWN amendment at the corrected address
#     is not lowered (a multi-``bokstav`` lead and a renumber-plus-replace lead
#     respectively), so there is no corrected text to bind and the address means
#     something different in the law's live text — see ``no_corrected_host_op``.
# The single-``§`` guard below is what makes the nested form an excluded shape
# by construction rather than by regex luck.
_NO_RETTELSE_NOTE_TYPE = "rettelse"

# ── Superseded gazette announcements (``utgått``) — W-84 ─────────────────────
#
# The SECOND value Lovdata writes into ``data-gazette-note-type``, read at the
# same site as ``rettelse`` above so the note vocabulary has one reader. Censused
# at W-84 over all 42,899 archive members: 374 members carry a gazettenote, 383
# notes in all — ``rettelse`` 314, ``utgått`` 69. Of the 69 ``utgått`` notes only
# THREE sit in the amendment (``lovtid``) lane, and those three are this rule's
# whole domain; the other 66 are forskrift/lov-lane members that feed no lowering.
#
# What ``utgått`` means, and it is NOT what ``rettelse`` means. A ``rettelse`` is
# a correction written INSIDE the announcement in amending grammar, so it is
# lowered as an op. An ``utgått`` note carries no directive at all: it marks the
# announcement as SUPERSEDED, and the corrected text is published separately as a
# *beriktiget* (rectified) re-announcement. Nothing here is lowerable; the note is
# a pointer, and the reader below returns only its dates.
#
# The note's PLACEMENT is a measured quirk worth stating: in all three lovtid-lane
# cases Lovdata wraps the announcement's FINAL Del (the commencement part) rather
# than the whole document — ``2021-06-11-80`` Del IV, ``2021-06-18-129`` Del II,
# ``2024-03-15-10`` Del II. The mark is nonetheless DOCUMENT-scoped, on Lovdata's
# own word: each act's ``lastupdated`` field says "se ny kunngjøring av beriktiget
# versjon av loven i kunngj. …", of the LAW, not of a part; and each rectified
# instrument re-announces the act in full, including provisions (klimaloven § 3,
# § 4) that sit OUTSIDE the wrapped Del. A part-scoped reading would leave the
# never-enacted klimaloven § 6/2/e in the replay, which is the defect W-83 found.
_NO_UTGATT_NOTE_TYPE = "utgått"

_NO_GAZETTENOTE_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' gazettenote ')]"
)


def _no_gazette_note_dates(root: etree._Element, note_type: str) -> tuple[str, ...]:
    """The ``data-gazette-note-date`` values of one note type, in document order."""
    dates: list[str] = []
    for note in cast(list[etree._Element], root.xpath(_NO_GAZETTENOTE_XPATH)):
        if (note.get("data-gazette-note-type") or "").strip() != note_type:
            continue
        dates.append((note.get("data-gazette-note-date") or "").strip())
    return tuple(dates)


def no_superseded_announcement_dates(html_bytes: bytes) -> tuple[str, ...]:
    """The dates on which this announcement was marked ``utgått``, if any.

    Empty for every artifact Lovdata has not superseded — which is 3,086 of the
    3,089 amendment artifacts. Returning the DATES rather than a bool is what lets
    the pairing gate cross-check the mark against the rectified instrument's own
    publication date without a second parse (see :mod:`lawvm.norway.index`).
    """
    try:
        root = _parse_document(html_bytes)
    except (etree.XMLSyntaxError, ValueError):
        return ()
    return _no_gazette_note_dates(root, _NO_UTGATT_NOTE_TYPE)


# ── Rectified re-announcements (``beriktiget``) — W-84 ───────────────────────
#
# The other half of the supersession pair. Lovdata publishes the corrected text as
# "Kunngjøring av beriktiget versjon av lov <date> nr. <n> om …", filed in the
# FORSKRIFT lane (``no://forskrift/<id>/original.lti.xml``) even though it
# announces an ACT. Our lanes split at the iterator, so the amendment index never
# sees it and the commencement parser — the forskrift lane's only consumer —
# classifies it BENIGN_NOT_COMMENCEMENT and drops it.
#
# This reader is the gate that admits those documents to the amendment lane, and
# it is deliberately NOT a blanket opening of the forskrift lane. Three conjuncts,
# every one of them written by Lovdata rather than inferred:
#
#   1. the title carries the ``beriktiget versjon av lov`` marker;
#   2. the title names EXACTLY ONE act by numbered citation — two citations, or
#      none, and the document names no unambiguous act to re-announce;
#   3. the document carries a ``changesToDocuments`` declaration block, i.e. it
#      declares itself to change documents at all.
#
# Measured corpus-wide: 3 of 35,955 forskrift artifacts pass, exactly the 3 the
# W-83 census froze. The marker phrase alone would NOT be a gate — it also occurs
# in 14 lov/lovtid-lane members, all of them prose ABOUT a rectification ("basert
# på en beriktiget versjon av lovvedtak nr. 5"); those carry no numbered act
# citation in their ``title`` field and are excluded by conjunct 1 reading the
# title rather than the body.
_NO_BERIKTIGET_TITLE_MARKER = "beriktiget versjon av lov"
# The same marker as raw bytes, so the reader below can reject a document without
# parsing it. Load-bearing for cost, not for correctness: this reader runs on
# EVERY amendment artifact the index and replay lower (3,089 of them, plus one
# pass over the 35,955-artifact forskrift lane), and 42,882 of the 42,899 archive
# members do not contain the phrase anywhere at all.
_NO_BERIKTIGET_MARKER_BYTES = _NO_BERIKTIGET_TITLE_MARKER.encode("utf-8")
_NO_DOKID_XPATH = "string(//dd[contains(concat(' ', normalize-space(@class), ' '), ' dokid ')][1])"
_NO_TITLE_DD_XPATH = "string(//dd[contains(concat(' ', normalize-space(@class), ' '), ' title ')][1])"
_NO_CHANGES_TO_DOCUMENTS_DD_XPATH = (
    "//dd[contains(concat(' ', normalize-space(@class), ' '), ' changesToDocuments ')]"
)


@dataclass(frozen=True)
class NOBeriktigetReannouncement:
    """One rectified re-announcement, as the document itself describes it."""

    # ``no/forskrift/<date>-<n>`` — the Lovtidend document the corrected bytes
    # were published as, read from the document's own ``dokid`` field.
    announcement_id: str
    # ``no/lovtid/<date>-<n>`` — the amendment-lane id of the ACT re-announced,
    # derived from the single numbered citation in the title.
    announced_act_id: str
    # The re-announcement's own publication date, from ``announcement_id``.
    announcement_date: str


def no_beriktiget_reannouncement(html_bytes: bytes) -> Optional[NOBeriktigetReannouncement]:
    """Read a rectified re-announcement's identity, or ``None`` for anything else."""
    if _NO_BERIKTIGET_MARKER_BYTES not in html_bytes:
        return None
    try:
        root = _parse_document(html_bytes)
    except (etree.XMLSyntaxError, ValueError):
        return None
    title = _repair_no_mojibake(_normalize_space(str(root.xpath(_NO_TITLE_DD_XPATH))))
    if _NO_BERIKTIGET_TITLE_MARKER not in title.lower():
        return None
    if not root.xpath(_NO_CHANGES_TO_DOCUMENTS_DD_XPATH):
        return None
    cited = _extract_no_law_citation_base_ids(title)
    if len(cited) != 1:
        return None
    dokid = _normalize_space(str(root.xpath(_NO_DOKID_XPATH)))
    announcement_id = dokid.removeprefix("LTI/")
    if not announcement_id.startswith("forskrift/"):
        return None
    announcement_id = f"no/{announcement_id}"
    return NOBeriktigetReannouncement(
        announcement_id=announcement_id,
        announced_act_id=f"no/lovtid/{cited[0].removeprefix('no/lov/')}",
        announcement_date=announcement_id.removeprefix("no/forskrift/").rsplit("-", 1)[0],
    )


def _with_no_beriktiget_provenance(
    grouped: list[tuple[str, list[LegalOperation]]],
    html_bytes: bytes,
    source_id: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Stamp the re-announcement's own id onto every op lowered out of it.

    Reached whenever these bytes ARE a rectified re-announcement, which the
    document says about itself — so the index and replay planes agree without the
    caller plumbing anything. ``source_id`` is the ACT's id (the index binds the
    corrected bytes to the act that enacted them), which is exactly why the
    forskrift id has to travel on the ops: without it, nothing downstream could
    say which document the text was read from.
    """
    if not grouped:
        return grouped
    reannouncement = no_beriktiget_reannouncement(html_bytes)
    if reannouncement is None:
        return grouped
    tag = f"{NO_BERIKTIGET_PROVENANCE_TAG}:{reannouncement.announcement_id}"
    stamped = [
        (
            base_id,
            [
                dc_replace(op, provenance_tags=(*op.provenance_tags, tag))
                if tag not in op.provenance_tags
                else op
                for op in ops
            ],
        )
        for base_id, ops in grouped
    ]
    _append_no_parse_adjudication(
        adjudications_out,
        kind=NO_BERIKTIGET_REANNOUNCEMENT_LOWERED,
        message=(
            "Norway parser lowered a rectified (beriktiget) re-announcement in place "
            "of the superseded gazette announcement it replaces."
        ),
        source_id=source_id,
        detail=diagnostic_detail(
            rule_id=NO_BERIKTIGET_REANNOUNCEMENT_LOWERED,
            phase="parse",
            family="source_pathology",
            blocking=False,
            quirks_disposition=QuirksDisposition.APPLY,
            announcement_id=reannouncement.announcement_id,
            announced_act_id=reannouncement.announced_act_id,
            announcement_date=reannouncement.announcement_date,
            base_ids=[base_id for base_id, _ops in stamped],
            n_ops=sum(len(ops) for _base_id, ops in stamped),
        ),
    )
    return stamped


# ── Re-sanctioned acts (supersession by re-sanctioning) — W-85 ───────────────
#
# Lovdata's SECOND supersession mechanism, surfaced at W-84's landing: an act is
# sanctioned, found defective, and RE-SANCTIONED AS A NEW ACT. Both halves sit in
# the lovtid lane as ordinary indexed acts — there is no ``utgått`` gazettenote
# and no rectified re-announcement — and the only machine-readable signal is
# prose: the superseded act says it was "sanksjonert (og kunngjort) på nytt som
# lov <date> nr. <n>", and the replacement says it was "første gang sanksjonert
# som lov <date> nr. <n>". Each half names the OTHER by numbered citation, which
# is what makes the pairing bilateral rather than a phrase match: a document
# that merely talks about re-sanctioning cites no counterpart that cites it back.
#
# WHERE the prose lives is measured, not assumed (W-85 census, ``.tmp/w85/``):
# the 2012 pair's superseded half carries it in ``miscInformation``, the 2025
# pair's in a leading ``defaultP`` article; both replacements use a leading
# ``defaultP``. So the reader below scans both surfaces. The phrase set is NOT
# assumed closed — the census's independent generators (same-title pairs,
# duplicate op-content joins, broad prose sweeps) are what bound the population,
# and an unmatched half fails closed in the index with a blocking receipt.
_NO_RESANCTIONED_ACT_REF = (
    r"lov (\d{1,2})\.?\s+(januar|februar|mars|april|mai|juni|juli|august|"
    r"september|oktober|november|desember)\s+(\d{4}) nr\.?\s*(\d+)"
)
# lawvm-regex: owning_parser this IS the re-sanctioning note parser
_NO_RESANCTIONED_FORWARD_RE = re.compile(
    r"sanksjonert(?:\s+og\s+kunngjort)?\s+på nytt som " + _NO_RESANCTIONED_ACT_REF
)
# lawvm-regex: owning_parser this IS the re-sanctioning note parser
_NO_RESANCTIONED_BACKWARD_RE = re.compile(
    r"første gang sanksjonert som " + _NO_RESANCTIONED_ACT_REF
)
# Byte prefilters, load-bearing for cost only: the reader below runs on every
# amendment artifact the index pre-pass sweeps (3,089), and 3,085 of them contain
# neither phrase anywhere in their bytes.
_NO_RESANCTIONED_FORWARD_BYTES = "på nytt som lov".encode("utf-8")
_NO_RESANCTIONED_BACKWARD_BYTES = "første gang sanksjonert som lov".encode("utf-8")
_NO_MISC_INFORMATION_DD_XPATH = (
    "//dd[contains(concat(' ', normalize-space(@class), ' '), ' miscInformation ')]"
)
_NO_DEFAULTP_ARTICLE_XPATH = (
    "//article[contains(concat(' ', normalize-space(@class), ' '), ' defaultP ')]"
)


@dataclass(frozen=True)
class NOResanctioningNote:
    """What one lovtid document says about a re-sanctioning, read off its prose."""

    # ``superseded`` — these bytes say they were re-sanctioned as ``counterpart_id``.
    # ``superseding`` — these bytes say they re-sanction ``counterpart_id``.
    role: str
    # ``no/lovtid/<date>-<n>`` of the OTHER half, from the numbered citation.
    counterpart_id: str


def _no_resanctioning_prose(root: etree._Element) -> list[str]:
    """The prose surfaces a re-sanctioning note can live on: misc + defaultP."""
    texts: list[str] = []
    for node in cast(list[etree._Element], root.xpath(_NO_MISC_INFORMATION_DD_XPATH)):
        texts.append(_repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext()))))
    for node in cast(list[etree._Element], root.xpath(_NO_DEFAULTP_ARTICLE_XPATH)):
        text = _repair_no_mojibake(_normalize_space(" ".join(str(_t) for _t in node.itertext())))
        if text.startswith(("Endringer i følgende", "Endring i følgende")):
            continue
        texts.append(text)
    return [text for text in texts if text]


def no_resanctioning_note(html_bytes: bytes) -> Optional[NOResanctioningNote]:
    """Read a document's re-sanctioning note, or ``None`` for anything else.

    Returns a note only when the prose is UNAMBIGUOUS: exactly one direction
    present, citing exactly one act. A document carrying both directions, or one
    direction with two different citations, names no single counterpart — the
    reader returns ``None`` and the ops stand, which is the safe direction (the
    index then has no note to pair, so nothing is suppressed).
    """
    if (
        _NO_RESANCTIONED_FORWARD_BYTES not in html_bytes
        and _NO_RESANCTIONED_BACKWARD_BYTES not in html_bytes
    ):
        return None
    try:
        root = _parse_document(html_bytes)
    except (etree.XMLSyntaxError, ValueError):
        return None
    forward: set[str] = set()
    backward: set[str] = set()
    for text in _no_resanctioning_prose(root):
        # lawvm-regex: owning_parser this IS the re-sanctioning note parser
        for day, month, year, number in _NO_RESANCTIONED_FORWARD_RE.findall(text):
            forward.add(f"{year}-{_NORWEGIAN_MONTH_NUMBERS[month]}-{int(day):02d}-{number}")
        # lawvm-regex: owning_parser this IS the re-sanctioning note parser
        for day, month, year, number in _NO_RESANCTIONED_BACKWARD_RE.findall(text):
            backward.add(f"{year}-{_NORWEGIAN_MONTH_NUMBERS[month]}-{int(day):02d}-{number}")
    if forward and backward:
        return None
    if len(forward) == 1:
        return NOResanctioningNote(role="superseded", counterpart_id=f"no/lovtid/{forward.pop()}")
    if len(backward) == 1:
        return NOResanctioningNote(role="superseding", counterpart_id=f"no/lovtid/{backward.pop()}")
    return None


def _with_no_resanctioned_provenance(
    grouped: list[tuple[str, list[LegalOperation]]],
    html_bytes: bytes,
    source_id: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Stamp the superseded act's id onto every op lowered out of its replacement.

    Reached whenever these bytes say they re-sanction another act, which the
    document says about itself — so the index and replay planes agree without the
    caller plumbing anything. Unconditional on the index's pairing verdict by
    design: the tag restates the document's own claim, and an unpaired
    replacement whose claim binds nothing is receipted in the index, not here.
    """
    if not grouped:
        return grouped
    note = no_resanctioning_note(html_bytes)
    if note is None or note.role != "superseding":
        return grouped
    tag = f"{NO_RESANCTIONED_PROVENANCE_TAG}:{note.counterpart_id}"
    stamped = [
        (
            base_id,
            [
                dc_replace(op, provenance_tags=(*op.provenance_tags, tag))
                if tag not in op.provenance_tags
                else op
                for op in ops
            ],
        )
        for base_id, ops in grouped
    ]
    _append_no_parse_adjudication(
        adjudications_out,
        kind=NO_RESANCTIONED_REPLACEMENT_LOWERED,
        message=(
            "Norway parser lowered a re-sanctioned act that declares itself the "
            "replacement of a defective, superseded sanctioning of the same law."
        ),
        source_id=source_id,
        detail=diagnostic_detail(
            rule_id=NO_RESANCTIONED_REPLACEMENT_LOWERED,
            phase="parse",
            family="source_pathology",
            blocking=False,
            quirks_disposition=QuirksDisposition.APPLY,
            superseded_act_id=note.counterpart_id,
            base_ids=[base_id for base_id, _ops in stamped],
            n_ops=sum(len(ops) for _base_id, ops in stamped),
        ),
    )
    return stamped


# Same-act ITEM addresses, anchored end to end. Both productions land on an
# ITEM leaf, which is why they share the one payload path below; admitting a
# second leaf kind would mean a second, unmeasured payload builder. A dash item
# is addressed by ORDINAL ("annet strekpunkt" -> item 2, its position), a
# lettered item by its own letter ("bokstav e" -> item e) — so the two
# productions read their item token differently and must not share a fallback.
_NO_RETTELSE_STREKPUNKT_LEAD_RE = compile_classifier_regex(
    r"^§\s*([0-9A-Za-z-]+)\s+([A-Za-zÆØÅæøå]+)\s+ledd\s+([A-Za-zÆØÅæøå]+)\s+strekpunkt\s+skal\s+lyde$",
    re.IGNORECASE,
    classifier_id="norway.grafter.rettelse_item_strekpunkt_lead",
)
_NO_RETTELSE_BOKSTAV_LEAD_RE = compile_classifier_regex(
    r"^§\s*([0-9A-Za-z-]+)\s+([A-Za-zÆØÅæøå]+)\s+ledd\s+bokstav\s+([A-Za-zÆØÅæøå])\s+skal\s+lyde$",
    re.IGNORECASE,
    classifier_id="norway.grafter.rettelse_item_bokstav_lead",
)


def _no_rettelse_item_target_from_lead(lead: str) -> Optional[LegalAddress]:
    """Resolve a ``Rettelser`` directive to a same-act ITEM address, or ``None``.

    Deliberately anchored and single-``§``: an erratum whose lead reaches into
    another act through the host act's part structure ("§ 73 nr. 7 § 6-7 første
    ledd bokstav e skal lyde") names two sections, and a search-anchored grammar
    would silently bind the WRONG one. Requiring exactly one ``§`` makes that
    whole family an excluded shape rather than a mis-lowering.
    """
    lead = _normalize_space(lead).rstrip(":")
    if lead.count("§") != 1 or not lead.startswith("§"):
        return None
    # lawvm-regex: owning_parser this IS the Rettelser directive parser
    match = _NO_RETTELSE_STREKPUNKT_LEAD_RE.match(lead)
    if match is not None:
        item_label = _NORWEGIAN_ORDINALS.get(match.group(3).lower()) or ""
    else:
        # lawvm-regex: owning_parser this IS the Rettelser directive parser
        match = _NO_RETTELSE_BOKSTAV_LEAD_RE.match(lead)
        if match is None:
            return None
        item_label = _normalize_label(match.group(3)).lower()
    section_label = _normalize_no_section_label(match.group(1))
    subsection_label = _NORWEGIAN_ORDINALS.get(match.group(2).lower()) or ""
    if not section_label or not subsection_label or not item_label:
        return None
    return LegalAddress(
        path=(
            ("section", section_label),
            ("subsection", subsection_label),
            ("item", item_label),
        )
    )


# ── W-24: Del-scoped erratum addresses ───────────────────────────────────────
#
# Four of W-18's eleven exclusions scope their address to a PART of the host act
# ("Del V, § 5-42 bokstav a skal lyde"), so the target law is the law that part
# amends, not the host act. The part→law step reuses the resolver the grafter
# already runs over that same part — there is deliberately no second resolver:
#
#   * structured artifacts (``document-change`` wrappers) — the part's law is the
#     ``data-document`` of the ``document-change`` nodes inside the part, read
#     through the same ``normalize_lovdata_refid`` the structured lowering uses.
#     Requiring the part's wrappers to AGREE is the guard; a part that amends two
#     laws names neither unambiguously.
#   * unstructured artifacts — the part's law is
#     ``_infer_no_unstructured_section_base_id`` over the part's own children,
#     byte-for-byte the call ``_iter_unstructured_no_change_groups`` makes.
#
# The dispatch between the two is the SAME predicate ``iter_no_document_change_ops``
# already dispatches on (presence of ``document-change`` nodes), so a part
# resolves here exactly as it resolves for ordinary ops or not at all.
#
# Parts are addressed by Lovdata's own ``data-name="kap<ROMAN>"`` attribute. The
# roman-only production is load-bearing: chapter-numbered acts spell the same
# attribute ``kap15`` (advokatloven), and a digit-admitting pattern would let
# "Del 15" style prose reach a chapter that is not a part at all.
_NO_PART_SECTION_NAME_RE = compile_classifier_regex(
    r"^kap([IVXL]+)$",
    re.IGNORECASE,
    classifier_id="norway.grafter.part_section_data_name",
)

# The two measured Del-scope prefixes, anchored and disjoint by their first
# token. ``Del <N>[,]`` is the nominative form; ``I del <N> skal`` is the
# locative form, whose trailing ``skal`` belongs to the PREFIX — the residue
# ("§ 28 b andre ledd tredje punktum skal lyde") carries its own. Each pattern
# matches the PREFIX only and the residue is taken from ``match.end()``; a
# trailing ``(.+)$`` capture would put two overlapping variable repeats next to
# each other and the classifier-safety gate rejects it.
_NO_RETTELSE_PART_SCOPE_RES = (
    compile_classifier_regex(
        r"^Del\s+([IVXL]+),?\s",
        re.IGNORECASE,
        classifier_id="norway.grafter.rettelse_part_scope_nominative",
    ),
    compile_classifier_regex(
        r"^I\s+del\s+([IVXL]+)\s+skal\s",
        re.IGNORECASE,
        classifier_id="norway.grafter.rettelse_part_scope_locative",
    ),
)

# One measured directive interposes an explicit citation of the very law the
# part amends between the Del scope and the address ("Del IV endringen i lov
# 16. juni 2017 nr. 65 om eierseksjoner § 49 …"). It is not a shortcut around
# the part resolution — it is a CROSS-CHECK: the cited law and the part's law
# must agree, or the erratum is excluded rather than adjudicated between. The
# clause runs from this head to the residue's first ``§``, which is the address
# boundary the single-``§`` guard downstream already depends on.
_NO_RETTELSE_PART_CITED_ACT_RE = compile_classifier_regex(
    r"^endringen\s+i\s+lov\s",
    re.IGNORECASE,
    classifier_id="norway.grafter.rettelse_part_cited_act",
)

# The two address shapes the measured Del-scoped directives need beyond W-18's
# item grammar. Both are anchored end to end like their W-18 ancestors.
#   * ``§ 8-2 overskriften`` — a SECTION-heading address, payload built by the
#     heading-only builder the unstructured lowering already uses.
#   * ``§ 5-42 bokstav a`` — a lettered item with NO ledd between it and the
#     section. Verified against the host act's own op for the same address
#     (``2023-12-20-98`` seq 40 targets exactly ``section 5-42 / item a``), so
#     the missing ledd is the law's shape, not a dropped token.
_NO_RETTELSE_HEADING_LEAD_RE = compile_classifier_regex(
    r"^§\s*([0-9A-Za-z-]+)\s+overskriften\s+skal\s+lyde$",
    re.IGNORECASE,
    classifier_id="norway.grafter.rettelse_section_heading_lead",
)
_NO_RETTELSE_LEDDLESS_BOKSTAV_LEAD_RE = compile_classifier_regex(
    r"^§\s*([0-9A-Za-z-]+)\s+bokstav\s+([A-Za-zÆØÅæøå])\s+skal\s+lyde$",
    re.IGNORECASE,
    classifier_id="norway.grafter.rettelse_leddless_item_bokstav_lead",
)


def _no_part_law_ids_from_root(root: etree._Element) -> dict[str, str]:
    """``romertall`` label -> the law that part amends, for every resolvable part.

    The one place the grafter's two part→law resolvers are applied per part (see
    the header comment); adds no third one. A part whose ``document-change``
    wrappers disagree, or whose lead resolves nothing, is simply absent from the
    result — the same "``None`` means undecidable" contract
    :func:`_no_part_base_id` has always had, expressed as omission.
    """
    out: dict[str, str] = {}
    for section in cast(list[etree._Element], root.xpath("//main/section")):
        # lawvm-regex: owning_parser this IS the part-attribute parser
        name_match = _NO_PART_SECTION_NAME_RE.match((section.get("data-name") or "").strip())
        if name_match is None:
            continue
        label = name_match.group(1).upper()
        if label in out:
            continue
        change_nodes = cast(
            list[etree._Element],
            section.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' document-change ')]"),
        )
        if change_nodes:
            base_ids = {
                normalize_lovdata_refid((node.get("data-document") or "").strip())
                for node in change_nodes
            }
            if len(base_ids) != 1:
                continue
            resolved: str | None = base_ids.pop()
        else:
            resolved = _infer_no_unstructured_section_base_id(_direct_children(section))
        if resolved:
            out[label] = resolved
    return out


def no_part_law_ids(html_bytes: bytes) -> dict[str, str]:
    """Public reader of one amendment artifact's per-part law map.

    The W-39 part-scoped commencement gate's scope proof. Returns ``{}`` for an
    artifact with no roman-numbered parts or unparseable bytes.
    """
    try:
        root = parse_corpus_xml(html_bytes)
    except etree.XMLSyntaxError:
        return {}
    return _no_part_law_ids_from_root(root)


def _no_part_base_id(root: etree._Element, part_label: str) -> str | None:
    """Resolve ``Del <part_label>`` of this artifact to the law that part amends."""
    return _no_part_law_ids_from_root(root).get(part_label.upper())


def _no_rettelse_part_scope_from_directive(directive: str) -> tuple[str, str] | None:
    """Split a ``Del <N>``-scoped directive into ``(part label, residual address)``."""
    directive = _normalize_space(directive)
    for pattern in _NO_RETTELSE_PART_SCOPE_RES:
        # lawvm-regex: owning_parser this IS the Rettelser directive parser
        match = pattern.match(directive)
        if match is not None:
            return match.group(1).upper(), _normalize_space(directive[match.end() :])
    return None


def _no_rettelse_part_target_from_residual(residual: str) -> Optional[LegalAddress]:
    """Resolve the address a Del-scoped directive names inside the part's law.

    Single-``§`` like its W-18 ancestor: a residual naming two sections is the
    nested shape, excluded by construction rather than by regex luck. The item
    and sentence productions are reused from the grammars that already own them
    (``_no_rettelse_item_target_from_lead``, ``_infer_same_base_sentence_target_specs_from_lead``);
    only the heading and ledd-less-item shapes are new here.
    """
    residual = _normalize_space(residual).rstrip(":")
    if residual.count("§") != 1 or not residual.startswith("§"):
        return None
    # lawvm-regex: owning_parser this IS the Rettelser directive parser
    heading_match = _NO_RETTELSE_HEADING_LEAD_RE.match(residual)
    if heading_match is not None:
        section_label = _normalize_no_section_label(heading_match.group(1))
        return LegalAddress(path=(("section", section_label),)) if section_label else None
    item_target = _no_rettelse_item_target_from_lead(residual)
    if item_target is not None:
        return item_target
    # lawvm-regex: owning_parser this IS the Rettelser directive parser
    bokstav_match = _NO_RETTELSE_LEDDLESS_BOKSTAV_LEAD_RE.match(residual)
    if bokstav_match is not None:
        section_label = _normalize_no_section_label(bokstav_match.group(1))
        item_label = _normalize_label(bokstav_match.group(2)).lower()
        if section_label and item_label:
            return LegalAddress(path=(("section", section_label), ("item", item_label)))
        return None
    sentence_specs = _infer_same_base_sentence_target_specs_from_lead(residual)
    if len(sentence_specs) == 1 and sentence_specs[0][0] is StructuralAction.REPLACE:
        return sentence_specs[0][1]
    return None


def _no_rettelse_part_payload(
    target: LegalAddress,
    payload_nodes: Sequence[etree._Element],
) -> Optional[IRNode]:
    """Build the payload for a Del-scoped erratum target, or ``None``.

    ``payload_nodes`` is the note's WHOLE child list, exactly as W-18 hands it to
    the payload extractor — the measured item notes carry their ``<ul>`` payload
    nested INSIDE the directive paragraph, so dropping that paragraph would drop
    the payload with it.

    The heading branch is the one exception and drops it deliberately: the
    heading-only builder reads the first ``defaultP``/``legalP`` it finds as the
    title, and the directive paragraph is one. Its corrected title arrives
    wrapped in a ``futureLegalArticle``, which is flattened one level to expose
    the paragraph the builder reads. Every other leaf kind goes through the same
    one-candidate path W-18 uses, so admitting a leaf kind here never means a
    new payload builder.
    """
    if target.leaf_kind() == "section":
        flattened: list[etree._Element] = []
        for node in payload_nodes[1:]:
            if _local_name(node) == "article" and "futureLegalArticle" in _classes(node):
                flattened.extend(_direct_children(node))
                continue
            flattened.append(node)
        return _heading_only_unstructured_section_payload(target.leaf_label() or "", flattened)
    candidates = _extract_payload_candidates_from_nodes(payload_nodes, [target])
    leaf_kind = target.leaf_kind()
    matching = [node for (kind, _label), node in candidates.items() if kind == leaf_kind]
    if len(matching) != 1:
        return None
    return _with_no_node_label(matching[0], target.leaf_label())


def _no_rettelse_directive_children(
    children: list[etree._Element],
    note_date: str,
) -> list[etree._Element]:
    """Drop a leading paragraph that only restates the note's own typed date.

    Artifacts carrying more than one erratum head each note with its
    announcement date as a standalone paragraph ("**7. desember 2020:**"), which
    the directive reader would otherwise consume as the directive. The guard is
    that the paragraph must resolve to EXACTLY the note's ``data-gazette-note-date``
    — a date paragraph that disagrees with the typed attribute is not this shape
    and is left in place rather than discarded.
    """
    if len(children) < 2 or not note_date:
        return children
    head = _normalize_space(" ".join(str(_t) for _t in children[0].itertext())).rstrip(":")
    # lawvm-regex: owning_parser this IS the Rettelser directive parser
    match = re.fullmatch(r"(\d{1,2})\.\s*([A-Za-zÆØÅæøå]+)\s+(\d{4})", head)
    if match is None:
        return children
    month = _NORWEGIAN_MONTH_NUMBERS.get(match.group(2).lower())
    if month is None or f"{match.group(3)}-{month}-{int(match.group(1)):02d}" != note_date:
        return children
    return children[1:]


def _no_op_targets_for_base(
    grouped: Sequence[tuple[str, list[LegalOperation]]],
    base_id: str,
) -> set[tuple[tuple[str, str], ...]]:
    """Every address this artifact's ORDINARY ops already touch in ``base_id``."""
    return {
        op.target.path
        for group_base, ops in grouped
        if group_base == base_id
        for op in ops
    }


def _no_rettelse_groups(
    root: etree._Element,
    source_id: str,
    *,
    grouped: Sequence[tuple[str, list[LegalOperation]]] = (),
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Lower this artifact's typed ``Rettelser`` notes into REPLACE ops.

    ``grouped`` is the artifact's ORDINARY change groups, read (never rewritten)
    for one purpose: a Del-scoped erratum corrects an amendment this artifact
    makes, so the corrected op must already be in that stream at the erratum's
    own address. See ``no_corrected_host_op`` below.

    An erratum corrects what was KUNNGJORT, so its op is dated by the host act's
    own commencement (the index entry's effective date), not by the rettelse
    announcement date: the corrected words have been the law since the act took
    effect, and dating the op at the announcement would let it overwrite genuine
    amendments enacted in between. The announcement date is carried in
    provenance (``rettelse_date:<date>``) instead, where it is greppable but
    apply-inert.
    """
    host_base_id = f"no/lov/{source_id.removeprefix('no/lovtid/')}"
    ops_by_base: dict[str, list[LegalOperation]] = {}
    sequence = 0
    for note in cast(list[etree._Element], root.xpath(_NO_GAZETTENOTE_XPATH)):
        if (note.get("data-gazette-note-type") or "").strip() != _NO_RETTELSE_NOTE_TYPE:
            # The other value this attribute takes is ``utgått``, and it is read —
            # by :func:`no_superseded_announcement_dates` above, not here: an
            # ``utgått`` note carries no amending directive to lower, so it can
            # only be acted on where the pairing evidence lives (the index).
            continue
        note_date = (note.get("data-gazette-note-date") or "").strip()
        children = _no_rettelse_directive_children(_direct_children(note), note_date)
        raw_text = _normalize_space(" ".join(str(_t) for _t in note.itertext()))
        lead = _normalize_space(" ".join(str(_t) for _t in children[0].itertext())) if children else raw_text
        directive = lead.split(":", 1)[0] if ":" in lead else lead
        part_scope = _no_rettelse_part_scope_from_directive(directive)
        base_id = host_base_id
        part_label = ""
        target: Optional[LegalAddress] = None
        payload: Optional[IRNode] = None
        reason = ""
        if part_scope is None:
            target = _no_rettelse_item_target_from_lead(directive)
            if target is not None:
                candidates = _extract_payload_candidates_from_nodes(children, [target])
                item_payloads = [node for (kind, _label), node in candidates.items() if kind == "item"]
                # One directive, one corrected provision: a note that yields more
                # than one item payload has no unambiguous binding, so it is
                # excluded rather than guessed at. The surviving payload is
                # relabelled onto the target because its own label is its position
                # INSIDE the erratum block (always "1"), not in the host act.
                if len(item_payloads) == 1:
                    payload = _with_no_node_label(item_payloads[0], target.leaf_label())
                if payload is None:
                    reason = "no_unique_item_payload"
            else:
                # A directive that starts at a ``§`` and names a SECOND one reaches
                # another act through the host act's own body ("§ 73 nr. 7 § 6-7
                # …"). It is excluded for the same reason as before — binding
                # either section corrupts text — but it is a materially different
                # failure from "this is not an address at all", so it says so.
                stripped = _normalize_space(directive).rstrip(":")
                reason = (
                    "no_nested_cross_act_address"
                    if stripped.startswith("§") and stripped.count("§") > 1
                    else "no_same_act_item_address"
                )
        else:
            part_label, residual = part_scope
            base_id = _no_part_base_id(root, part_label) or ""
            # lawvm-regex: owning_parser this IS the Rettelser directive parser
            cited_match = _NO_RETTELSE_PART_CITED_ACT_RE.match(residual)
            cited_base_id: str | None = None
            if cited_match is not None and "§" in residual:
                address_start = residual.index("§")
                cited_base_id = _extract_no_law_citation_base_id(residual[:address_start])
                residual = _normalize_space(residual[address_start:])
            if not base_id:
                reason = "no_part_base_act"
            elif cited_base_id is not None and cited_base_id != base_id:
                # Two independent resolutions of the same law disagreeing is
                # never adjudicated in favour of one of them.
                reason = "no_part_citation_agreement"
            else:
                target = _no_rettelse_part_target_from_residual(residual)
                if target is None:
                    reason = "no_part_scoped_target_address"
                elif target.path not in _no_op_targets_for_base(grouped, base_id):
                    # A Del-scoped erratum corrects the host act's OWN amendment
                    # text, so the corrected words must be in this artifact's
                    # lowered op stream at exactly that address. When they are
                    # not — because the host act's own directive for that address
                    # is itself an unlowered shape — the erratum has nothing to
                    # correct, and its address means something DIFFERENT in the
                    # law's live text than it means inside the part. Measured on
                    # both sides: the two errata that pass name an address the
                    # host act's own op already targets; the two that fail would
                    # otherwise land on unrelated live provisions.
                    reason = "no_corrected_host_op"
                else:
                    payload = _no_rettelse_part_payload(target, children)
                    if payload is None:
                        reason = "no_part_scoped_payload"
        if target is None or payload is None:
            _append_no_parse_adjudication(
                adjudications_out,
                kind=NO_RETTELSE_NOT_LOWERED,
                message="Norway parser did not lower a published Rettelser correction.",
                source_id=source_id,
                detail=diagnostic_detail(
                    rule_id=NO_RETTELSE_NOT_LOWERED,
                    phase="parse",
                    family="unsupported_or_unresolved_action",
                    blocking=False,
                    quirks_disposition=QuirksDisposition.RECORD,
                    base_id=base_id or host_base_id,
                    rettelse_date=note_date,
                    reason=reason or "no_same_act_item_address",
                    part=part_label,
                    directive=directive[:240],
                    raw_text=raw_text[:240],
                ),
            )
            continue
        sequence += 1
        ops_by_base.setdefault(base_id, []).append(
            LegalOperation(
                op_id=f"{source_id}:rettelse:{sequence}",
                sequence=sequence,
                action=StructuralAction.REPLACE,
                target=target,
                payload=payload,
                source=OperationSource(statute_id=source_id, raw_text=raw_text, title=base_id),
                provenance_tags=(
                    f"base_act:{base_id}",
                    "rettelse:published_correction",
                    f"rettelse_date:{note_date}",
                    *((f"rettelse_part:{part_label}",) if part_label else ()),
                ),
                group_id=f"{source_id}:rettelse:{base_id}:{sequence}",
                witness_rule_id=NO_RETTELSE_LOWERED,
            )
        )
    return [(base_id, ops) for base_id, ops in ops_by_base.items() if ops]


def _with_no_rettelse_groups(
    grouped: list[tuple[str, list[LegalOperation]]],
    root: etree._Element,
    source_id: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Merge lowered erratum ops into the artifact's ordinary change groups.

    Errata are appended to an existing group for the same base act rather than
    forming a second group, so ``entries_for_base``/replay keep seeing one group
    per (artifact, base act). Since W-24 that base act can be the law a PART of
    the host act amends rather than the host act itself; the merge is unchanged
    because it was already keyed on the base act the erratum resolved.

    Appending is what puts the erratum LAST: the offset is the highest sequence
    already in that group, which for a multi-part artifact is the artifact's
    highest, so the correction applies after every op it could correct.
    """
    rettelse_groups = _no_rettelse_groups(
        root,
        source_id,
        grouped=grouped,
        adjudications_out=adjudications_out,
    )
    if not rettelse_groups:
        return grouped
    merged = [(base_id, list(ops)) for base_id, ops in grouped]
    by_base = {base_id: ops for base_id, ops in merged}
    for base_id, rettelse_ops in rettelse_groups:
        existing = by_base.get(base_id)
        if existing is None:
            merged.append((base_id, list(rettelse_ops)))
            continue
        offset = max((op.sequence for op in existing), default=0)
        existing.extend(
            dc_replace(op, sequence=op.sequence + offset) for op in rettelse_ops
        )
    return merged


# W-32(b): the lead half of a renumber-plus-replace instruction. The ADDRESSES
# come from ``data-move-part`` (authoritative markup, not prose); this anchor
# only has to answer "does the lead also declare that the moved provision shall
# now read as follows". It therefore requires the move verb ``blir`` and a
# terminal ``skal lyde`` -- "og skal lyde:", "som skal lyde:", "og overskriften
# skal lyde:" all end that way, and a lead whose "skal lyde" is followed by
# further clauses is not one this recovery can attribute.
# Two anchors, not one: a variable gap between them would be an unbounded repeat
# adjacent to the terminator's own, which the classifier-safety gate rejects.
_NO_STRUCTURED_RENUMBER_MOVE_VERB_RE = compile_classifier_regex(
    r"\bblir\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.structured_renumber_move_verb",
)
_NO_STRUCTURED_RENUMBER_REPLACEMENT_TAIL_RE = compile_classifier_regex(
    r"\bskal\s+lyde\s*:?$",
    re.IGNORECASE,
    classifier_id="norway.grafter.structured_renumber_replacement_tail",
)


def _no_structured_renumber_lead_declares_replacement(lead: str) -> bool:
    """Does this move block's lead ALSO say the moved provision shall now read …?"""
    lead = _normalize_space(lead)
    # lawvm-regex: owning_parser this IS the structured renumber-lead parser
    if _NO_STRUCTURED_RENUMBER_MOVE_VERB_RE.search(lead) is None:
        return False
    # lawvm-regex: owning_parser this IS the structured renumber-lead parser
    return _NO_STRUCTURED_RENUMBER_REPLACEMENT_TAIL_RE.search(lead) is not None


# W-75: Lovdata renders a word substitution spanning many provisions as an
# ANNOUNCEMENT plus an ADDRESS LIST:
#
#     I følgende bestemmelser skal ordet «tilsettingsmyndigheten» endres til
#     «ansettelsesmyndigheten»:
#     § 13 første ledd, § 13 andre ledd første punktum, … § 20 fjerde ledd.
#
# The list carries ``data-change-part`` naming every listed address, so the
# structured lane reads N targets and takes the node's OWN text as the payload
# — and the node's own text is the announcement and/or the address list. Every
# op it mints overwrites a provision of in-force law with the amendment's own
# prose. Until the substitution can be lowered for real (a substitution op, or
# a REPLACE whose payload is derived from the target's existing text — the
# ``content_policy`` vocabulary question), the only sound thing to do with the
# construct is to refuse it and say so.
NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED = "no_parse_substitution_announcement_not_lowered"

# W-69a: the substitution is now LOWERED, as an addressed ``TEXT_PATCH`` — one
# op per (listed address × announced pair). The receipt above survives as the
# S3 conjunct's refusal (an announcement whose pair grammar does not parse) and
# these three join it, one per boundary of the lowering envelope. Every one is
# measured against a population, named at its emit site.
#
# W-69a's fourth, ``no_parse_substitution_sentence_address_out_of_scope``, is
# RETIRED by W-69b: it named a phase boundary (sentence materialization was not
# reachable from the text-patch apply branch) rather than a property of the
# construct, and lifting the materializer removed the boundary. Its 21 receipts
# became 17 landed substitutions, 1 op on a base act with no replayed statute,
# 1 apply-plane ``no_replay_substitution_term_not_uniquely_present`` and 2
# ``replay_unresolved_target``. Deleted rather than left at zero, so no reader
# has to work out which of the two W-69 halves it still guards.
NO_PARSE_SUBSTITUTION_MULTIPLE_ANNOUNCEMENTS = "no_parse_substitution_multiple_announcements"
NO_PARSE_SUBSTITUTION_MULTI_BASE_ADDRESS_LIST = "no_parse_substitution_multi_base_address_list"
NO_PARSE_SUBSTITUTION_ADDRESS_NOT_LOWERABLE = "no_parse_substitution_address_not_lowerable"
#: Stamped on every op the addressed-substitution production mints, and read by
#: the apply seam. It is the ONLY thing that tells the ``text_replace`` branch
#: that this op must prove its FROM term is uniquely present before writing —
#: see ``_no_substitution_term_refusal_reason``. A carrier mark, not a rule id.
NO_SUBSTITUTION_PROVENANCE_TAG = "no_addressed_substitution"
#: The apply-plane conjuncts S6 (exactly one announced term present) and S7 (it
#: occurs exactly once, as a whole word). They CANNOT run at parse: the parse
#: plane has no statute — replay consumes parse output, so the addressed node's
#: text is not in hand until apply. Refusing here (rather than letting a
#: content-identical write fall through to the θ ``replay_noop`` cell) is what
#: keeps the reason typed, so it is a genuine per-op SKIP and joins
#: :data:`_NO_SKIP_ADJUDICATION_KINDS`.
NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT = (
    "no_replay_substitution_term_not_uniquely_present"
)

# The announcement is SENTENCE-INITIAL: "hjemmel i følgende bestemmelser med
# tilhørende forskrifter:" (no/lovtid/2025-04-25-12) is ordinary payload prose
# containing the same words mid-sentence, and an unanchored test refuses two
# genuine replacements on it.
#
# W-78: the NOUN after ``følgende`` is decoration, and enumerating it was the
# defect. W-69a's list (``bestemmelser|bestemmelse|paragrafer|paragraf|
# lovbestemmelser|lover``) does not contain ``steder``, so
# "Følgende steder endres ordene «X» til «Y»: <address list>" — the same
# construct, seven nodes over ``no/lovtid/2026-06-19-45`` and
# ``no/lovtid/2026-06-12-31`` — fell past this predicate into the structured
# payload lane, which read the flat ``data-change-part`` list as REPLACE targets
# and the node's own text as their payload: 116 REPLACE ops writing the
# announcement sentence itself into in-force law. The opener is therefore
# generalised to ``følgende`` sentence-initially (the leading ``i`` optional,
# since "Følgende steder …" has none), and the weight is carried instead by the
# conjuncts that are actually load-bearing: a quoted FROM term and a
# substitution verb, both BEFORE the node's payload-introducing colon (so the
# instruction is complete without the list), plus the caller's operative-payload
# veto. Measured over every ``data-change-part`` node in the corpus (2,704):
# governing nodes 17 → 24, the seven added being exactly the defect; the five
# nodes that carry a quoted term and a substitution verb in their head AND
# declare their own payload ("§ 55 a første ledd nr. 4 skal lyde: …") stay
# declined on the operative conjunct.
_NO_SUBSTITUTION_ANNOUNCEMENT_OPENER_RE = compile_classifier_regex(
    r"^(?:i\s+følgende|følgende)\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.substitution_announcement_opener",
)
# Both remaining conjuncts of the announcement: the substituted term is quoted
# in guillemets, and the verb is a substitution verb. Corpus phrasings covered:
# "skal ordet «X» endres til «Y»", "skal «X» endres til «Y»", "skal ordene «X»
# og «Y» endres til henholdsvis …", "skal uttrykket/formuleringene «X» endres
# til «Y»", "endres ordet «X» til «Y»", "erstattes uttrykket «X» av «Y»".
_NO_SUBSTITUTION_ANNOUNCEMENT_TERM_RE = compile_classifier_regex(
    r"«[^»]+»",
    classifier_id="norway.grafter.substitution_announcement_term",
)
_NO_SUBSTITUTION_ANNOUNCEMENT_VERB_RE = compile_classifier_regex(
    r"\b(?:endres|erstattes)\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.substitution_announcement_verb",
)
# A node that declares its own operative payload is NOT an address list, even
# when an announcement happens to precede it. no/lovtid/2026-06-19-45 puts four
# genuine "§ X skal lyde: <payload>" change nodes immediately after
# announcements, so keying on the preceding sibling alone would refuse real
# amendments — this conjunct is what keeps the refusal off them.
_NO_SUBSTITUTION_ANNOUNCEMENT_OPERATIVE_RE = compile_classifier_regex(
    r"\b(?:skal\s+lyde|oppheves|skal\s+ha\s+følgende\s+ordlyd)\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.substitution_announcement_operative",
)
# S1's counter: the same opener, UNANCHORED, so a governing text carrying more
# than one announcement is visible. ``no/lovtid/2026-06-19-48`` concatenates
# FOUR announcements into one node and hangs 82 addresses over 35 base acts off
# them; nothing in the flat ``data-change-part`` token list says which address
# belongs to which announcement, and the damage is already measurable — 8 of the
# 13 corpus addresses that resolve but do not carry their announced term are
# that node's, i.e. later-announcement addresses measured against the first
# announcement's pair. Such a node refuses WHOLE; partial acceptance is
# forbidden. (The W-69 design says 9 of 13; re-derived at this base it is 8.)
#
# W-78 generalises it in lockstep with the anchored opener above — a counter
# that cannot see the new dialect would mis-type every "Følgende steder …" node
# as S1 "more than one announcement". Verdicts are unchanged on every governing
# text in the corpus: each of the 23 single-announcement texts counts exactly 1,
# and ``2026-06-19-48`` still counts more than 1.
_NO_SUBSTITUTION_ANNOUNCEMENT_OPENER_SCAN_RE = compile_classifier_regex(
    r"\bfølgende\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.substitution_announcement_opener_scan",
)
# The pair grammar. ``henholdsvis`` is FROM × TO — "ordene «namsmannen» og
# «namsmannens» endres til henholdsvis «namsfogden» og «namsfogdens»" names a
# pair SET that applies to EVERY listed address, NOT an address-positional
# match. Corpus shapes, all measured on the 17-node family:
#   * ``«A» endres til «B»``            — terms on both sides of the verb
#   * ``endres ordet «A» til «B»``      — verb first, both terms after it
#   * ``endres ordene «A» og «B» til henholdsvis «C» og «D»``  — verb first,
#     2N terms after it, first half FROM, second half TO
#   * ``skal ordene «A» og «B» endres til henholdsvis «C» og «D»`` — N before,
#     N after.
# Anything else refuses under S3 with the W-75 receipt.
_NO_SUBSTITUTION_PAIR_VERB_RE = compile_classifier_regex(
    r"\b(?:endres\s+til|erstattes\s+med|erstattes\s+av|erstattes|endres)\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.substitution_pair_verb",
)
_NO_SUBSTITUTION_QUOTED_TERM_RE = compile_classifier_regex(
    r"«([^»]+)»",
    classifier_id="norway.grafter.substitution_quoted_term",
)
_NO_SUBSTITUTION_HENHOLDSVIS_RE = compile_classifier_regex(
    r"\bhenholdsvis\b",
    re.IGNORECASE,
    classifier_id="norway.grafter.substitution_henholdsvis",
)


def _no_text_announces_word_substitution(text: str) -> bool:
    """Is this text a multi-provision word-substitution announcement?

    W-78: the quoted term and the substitution verb must both stand in the HEAD
    — everything before the first colon, which is exactly the span
    :func:`_extract_no_substitution_pairs` reads. That is what makes the colon a
    LIST introducer rather than a payload introducer: the instruction is already
    complete without whatever follows it. Requiring it also keeps the loosened
    opener honest — "Følgende endringer gjøres: … «X» endres til «Y» …" declares
    its substitution inside a payload, not in an announcement head, and this
    conjunct declines it where the old closed noun list did the work by accident.
    Every one of the 24 governing nodes in the corpus satisfies it.
    """
    text = _normalize_space(text)
    if ":" not in text:
        return False
    head = text.split(":", 1)[0]
    # lawvm-regex: owning_parser this IS the substitution-announcement parser
    if _NO_SUBSTITUTION_ANNOUNCEMENT_OPENER_RE.match(head) is None:
        return False
    # lawvm-regex: owning_parser this IS the substitution-announcement parser
    if _NO_SUBSTITUTION_ANNOUNCEMENT_TERM_RE.search(head) is None:
        return False
    # lawvm-regex: owning_parser this IS the substitution-announcement parser
    return _NO_SUBSTITUTION_ANNOUNCEMENT_VERB_RE.search(head) is not None


def _no_substitution_announcement_governing(
    change_el: etree._Element,
) -> Optional[tuple[str, str]]:
    """Return ``(source, announcement)`` when a word substitution governs this node.

    ``source`` is where the announcement was read: ``own_text`` when the change
    node itself opens with it (Lovdata's usual rendering) or
    ``preceding_sibling`` when it sits in the sibling ``defaultP`` before the
    node (``no/lovtid/2025-02-07-1``, ``no/lovtid/2024-06-21-52``). Both are the
    DOM the lowering reads; neither is an address-count or law-list guess.
    """
    own = _normalize_space(" ".join(str(_t) for _t in change_el.itertext()))
    # lawvm-regex: owning_parser this IS the substitution-announcement parser
    if _NO_SUBSTITUTION_ANNOUNCEMENT_OPERATIVE_RE.search(own) is not None:
        return None
    if _no_text_announces_word_substitution(own):
        return ("own_text", own)
    previous = change_el.getprevious()
    if previous is None or not isinstance(previous.tag, str):
        return None
    prior = _normalize_space(" ".join(str(_t) for _t in previous.itertext()))
    if _no_text_announces_word_substitution(prior):
        return ("preceding_sibling", prior)
    return None


def _extract_no_substitution_pairs(announcement: str) -> tuple[tuple[tuple[str, str], ...], str]:
    """Read the announced ``(FROM, TO)`` pairs out of a substitution announcement.

    Returns ``(pairs, shape)``; ``pairs`` is empty when the grammar does not
    parse, and ``shape`` names what was seen so the S3 refusal receipt says why.
    Only the head of the announcement (everything before the first colon) is
    read: the colon is what separates the announcement from the address list,
    and a listed address never carries guillemets.
    """
    head = _normalize_space(announcement).split(":", 1)[0]
    # lawvm-regex: owning_parser this IS the substitution-announcement pair parser
    verb = _NO_SUBSTITUTION_PAIR_VERB_RE.search(head)
    if verb is None:
        return (), "verb_not_found"
    # lawvm-regex: owning_parser this IS the substitution-announcement pair parser
    before = _NO_SUBSTITUTION_QUOTED_TERM_RE.findall(head[: verb.start()])
    # lawvm-regex: owning_parser this IS the substitution-announcement pair parser
    after = _NO_SUBSTITUTION_QUOTED_TERM_RE.findall(head[verb.start() :])
    # lawvm-regex: owning_parser this IS the substitution-announcement pair parser
    henholdsvis = _NO_SUBSTITUTION_HENHOLDSVIS_RE.search(head) is not None
    before = [_normalize_space(term) for term in before if _normalize_space(term)]
    after = [_normalize_space(term) for term in after if _normalize_space(term)]
    if not before and not after:
        return (), "quoted_terms_not_found"
    if len(before) == 1 and len(after) == 1:
        return ((before[0], after[0]),), "single_pair"
    if before and len(before) == len(after):
        return (
            tuple(zip(before, after, strict=True)),
            "positional_pairs_henholdsvis" if henholdsvis else "positional_pairs",
        )
    if not before and len(after) == 2:
        return ((after[0], after[1]),), "single_pair_verb_first"
    if not before and len(after) >= 4 and len(after) % 2 == 0 and henholdsvis:
        half = len(after) // 2
        return (
            tuple(zip(after[:half], after[half:], strict=True)),
            "positional_pairs_verb_first_henholdsvis",
        )
    return (), f"unpaired_{len(before)}_{len(after)}"


def _no_substitution_term_counts(node: IRNode, term: str) -> tuple[int, int, int]:
    """``(whole_word, substring, case_insensitive)`` counts of ``term`` under ``node``.

    Counted per OWN text, node by node, and summed — which is exactly what
    :func:`_apply_no_text_replace` does (a recursive ``str.replace`` over each
    node's own text). Counting over a flattened join would let a multi-word term
    match across a node boundary that ``str.replace`` can never see. Measured on
    the corpus at W-69a's base: the two counters agree on every one of the 27
    resolvable addresses, so this is a soundness guard, not a behaviour change.
    """
    whole_word = 0
    substring = 0
    case_insensitive = 0
    lowered = term.lower()
    stack = [node]
    while stack:
        current = stack.pop()
        text = current.text or ""
        if text:
            whole_word += _no_whole_word_count(text, term)
            substring += text.count(term)
            case_insensitive += text.lower().count(lowered)
        stack.extend(current.children)
    return whole_word, substring, case_insensitive


def _no_is_word_char(char: str) -> bool:
    """``re``'s ``\\w`` for str patterns: unicode alphanumeric, or underscore."""
    return char.isalnum() or char == "_"


def _no_whole_word_count(text: str, term: str) -> int:
    """``(?<!\\w)TERM(?!\\w)`` occurrences, counted WITHOUT a regex.

    The rule is the design's; the implementation is a scan because the pattern
    would have to be built per FROM term from corpus data. A per-term
    ``re.compile`` of an f-string is the frozen-residue shape the FW-07/FW-08
    ratchets exist to keep out of a parser module, and there is nothing here a
    regex buys: ``str.find`` plus a boundary test on the two adjacent characters
    is the same predicate, and ``_no_is_word_char`` is exactly how CPython's
    ``sre`` defines ``\\w`` for str patterns.

    Whole-word, not substring, and that costs something measurable: it refuses 2
    of the 42 exact-substring-deterministic corpus addresses, both Norwegian
    genitive-``s`` cases, one of which is a live divergence row (karanteneloven
    ``§ 20 fjerde ledd``, ``tilsettingsmyndighetens``). That row stays open,
    honestly. What it buys is the guarantee that a FROM term never fires inside
    a longer word — under-application is the safe direction.
    """
    if not term:
        return 0
    count = 0
    start = 0
    width = len(term)
    while True:
        found = text.find(term, start)
        if found < 0:
            return count
        before_ok = found == 0 or not _no_is_word_char(text[found - 1])
        after = found + width
        after_ok = after >= len(text) or not _no_is_word_char(text[after])
        if before_ok and after_ok:
            # Non-overlapping, exactly as ``re.findall`` advances: past a match
            # it counted, by one on a failed boundary test. It matters for a
            # multi-word FROM term — ``"a a"`` occurs ONCE in ``"a a a"``, not
            # twice — and it keeps this count comparable with the ``str.count``
            # substring count, which is non-overlapping too.
            count += 1
            start = after
            continue
        start = found + 1


def _no_substitution_term_refusal_reason(
    node: IRNode,
    match_text: str,
    announced_terms: tuple[str, ...],
) -> Optional[tuple[str, dict[str, int]]]:
    """S6 + S7 at the apply plane: may this substitution op write, and if not why?

    Returns ``None`` when the op may write, otherwise ``(reason, counts)``.

    * **S6** — exactly one of the announcement's FROM terms may be present as a
      whole word in the addressed node. The prefix-nested pairs are why this is
      not redundant with S7: ``gjeldsforhandling`` / ``gjeldsforhandlingen`` and
      ``namsmannen`` / ``namsmannens`` are each other's proper prefixes, so a
      node carrying both would take two writes from one announcement whose
      grammar says one pair applies.
    * **S7** — that term occurs exactly once, as a whole word, AND exactly once
      as a raw substring. The second half is not belt-and-braces: the shipped
      :func:`_apply_no_text_replace` is an unguarded recursive ``str.replace``
      that honours neither ``TextSelector.occurrence`` nor a word boundary, so a
      substring count above one means the write would also fire inside a longer
      word. Proving both counts are 1 is what makes the shipped helper's
      semantics equal to the announced whole-word substitution.
    """
    stats = {term: _no_substitution_term_counts(node, term) for term in announced_terms}
    mine = stats.get(match_text) or _no_substitution_term_counts(node, match_text)
    counts = {"whole_word": mine[0], "substring": mine[1], "case_insensitive": mine[2]}
    present = [term for term in announced_terms if stats[term][0] >= 1]
    if len(present) > 1:
        return "term_ambiguous", counts
    if not present:
        if mine[1] >= 1:
            return "substring_only", counts
        if mine[2] >= 1:
            # The design's word for this cell, kept so the receipt vocabulary
            # stays auditable against it. What it actually measures is a
            # CASE-insensitive-only match; the genuine morphological inflection
            # (a Norwegian genitive ``-s``) is a substring match and lands in
            # ``substring_only`` above. Matching is deliberately case-SENSITIVE:
            # the announcement quotes the exact word it replaces.
            return "inflection_only", counts
        return "absent", counts
    if present[0] != match_text:
        return "other_announced_term_matches", counts
    if mine[0] != 1:
        return "multiple", counts
    if mine[1] != 1:
        return "substring_overlap", counts
    return None


def iter_no_document_change_ops(
    html_bytes: bytes,
    source_id: str,
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> list[tuple[str, list[LegalOperation]]]:
    """Group compiled amendment ops by base act for one Lovtidend document.

    Architectural note:
    this is still a direct lowering seam from source-local change markup into
    `LegalOperation`. The long-term Norway shape should insert explicit
    change-surface and payload-surface waists above this function so replay no
    longer depends on frontend-local recovery decisions.
    """
    root = _parse_document(html_bytes)
    grouped: list[tuple[str, list[LegalOperation]]] = []
    sequence = 1

    change_nodes = cast(
        list[etree._Element],
        root.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' document-change ')]"),
    )
    if not change_nodes:
        return _with_no_resanctioned_provenance(
            _with_no_beriktiget_provenance(
                _with_no_rettelse_groups(
                    _iter_unstructured_no_change_groups(root, source_id, adjudications_out=adjudications_out),
                    root,
                    source_id,
                    adjudications_out=adjudications_out,
                ),
                html_bytes,
                source_id,
                adjudications_out=adjudications_out,
            ),
            html_bytes,
            source_id,
            adjudications_out=adjudications_out,
        )
    for doc_change in change_nodes:
        source_doc = doc_change.get("data-document", "").strip()
        base_id = normalize_lovdata_refid(source_doc)
        if not source_doc or base_id is None:
            _append_no_parse_adjudication(
                adjudications_out,
                kind="no_parse_document_change_base_unresolved",
                message="Norway parser skipped structured document-change with missing or unmappable base act.",
                source_id=source_id,
                detail=diagnostic_detail(
                    rule_id="no_parse_document_change_base_unresolved",
                    phase="parse",
                    family="source_pathology",
                    blocking=True,
                    reason="missing_data_document" if not source_doc else "unmappable_data_document",
                    source_doc=source_doc,
                ),
            )
            continue
        doc_ops: list[LegalOperation] = []
        for change_el in _iter_change_descendants(doc_change):
            raw_text = _normalize_space(" ".join(str(_t) for _t in change_el.itertext()))
            lead_articles = [
                article for article in _direct_children(change_el, "article") if "defaultP" in _classes(article)
            ]
            lead_text = (
                _normalize_space(" ".join(str(_t) for _t in lead_articles[0].itertext())) if lead_articles else raw_text
            )

            # W-75/W-69a: an address list under a word-substitution announcement.
            # Its ``data-change-part`` addresses are the provisions to substitute
            # IN, not provisions to overwrite, and the node carries no payload
            # for them — so the shipped structured lane wrote the amendment's own
            # announcement prose into every listed provision of in-force law.
            # W-75 refused the whole node. W-69a LOWERS it, as one addressed
            # ``TEXT_PATCH`` per (listed address × announced pair), behind the
            # S1-S7 envelope: S1-S4 here (they are string tests on the
            # announcement), S5-S7 at apply (they need the addressed node's text,
            # and the parse plane has no statute — replay consumes parse output).
            #
            # The node is still refused WHOLE on S1/S2/S3; only per-address
            # boundaries refuse per address. Whichever way a boundary refuses, it
            # refuses TYPED: nothing about this construct is allowed to go quiet.
            change_part_token = change_el.get("data-change-part", "").strip()
            announcement = _no_substitution_announcement_governing(change_el)
            if change_part_token and announcement is not None:
                announcement_source, announcement_text = announcement
                refused_addresses = tuple(change_part_token.split())
                other_structured_attributes = tuple(
                    sorted(
                        name
                        for name in change_el.attrib
                        if name.startswith("data-")
                        and name
                        in {"data-add-new-part", "data-remove-part", "data-repeal-part", "data-move-part"}
                    )
                )
                node_detail: dict[str, Any] = dict(
                    base_id=base_id,
                    source_doc=source_doc,
                    announcement_source=announcement_source,
                    announcement=announcement_text,
                    refused_address_count=len(refused_addresses),
                    refused_addresses=refused_addresses,
                    other_structured_attributes=other_structured_attributes,
                    raw_text=raw_text,
                )
                # lawvm-regex: owning_parser this IS the substitution-announcement parser
                opener_count = len(_NO_SUBSTITUTION_ANNOUNCEMENT_OPENER_SCAN_RE.findall(announcement_text))
                address_bases = tuple(
                    sorted({normalize_lovdata_refid(raw) or "" for raw in refused_addresses})
                )
                pairs, pair_shape = _extract_no_substitution_pairs(announcement_text)
                if opener_count != 1:
                    # S1. no/lovtid/2026-06-19-48: FOUR announcements concatenated
                    # into one governing text, 82 addresses over 35 base acts, and
                    # only the first announcement's pair is readable. 8 of the 13
                    # corpus addresses that resolve without carrying their term are
                    # this node's — the hazard is live, not theoretical.
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind=NO_PARSE_SUBSTITUTION_MULTIPLE_ANNOUNCEMENTS,
                        message=(
                            "Norway structured change block's governing text carries more than "
                            "one word-substitution announcement; nothing in the flat address "
                            "list says which address belongs to which announcement, so the "
                            "whole block was refused rather than measured against the first."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id=NO_PARSE_SUBSTITUTION_MULTIPLE_ANNOUNCEMENTS,
                            phase="parse",
                            family="unsupported_or_unresolved_action",
                            blocking=True,
                            announcement_count=opener_count,
                            address_base_count=len(address_bases),
                            **node_detail,
                        ),
                    )
                    continue
                if len(address_bases) != 1 or address_bases[0] != base_id:
                    # S2. The structured lane binds the whole node to the enclosing
                    # ``data-document`` base act; an address list that names another
                    # act (or several) is a different construct and its ops would be
                    # bound to the wrong law.
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind=NO_PARSE_SUBSTITUTION_MULTI_BASE_ADDRESS_LIST,
                        message=(
                            "Norway word-substitution address list does not name exactly the "
                            "enclosing document-change base act; the block was refused rather "
                            "than bound to a base act its addresses do not belong to."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id=NO_PARSE_SUBSTITUTION_MULTI_BASE_ADDRESS_LIST,
                            phase="parse",
                            family="source_pathology",
                            blocking=True,
                            address_bases=address_bases,
                            address_base_count=len(address_bases),
                            **node_detail,
                        ),
                    )
                    continue
                if not pairs:
                    # S3. The W-75 receipt survives here, and only here: an
                    # announcement whose (FROM, TO) grammar does not parse.
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind=NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED,
                        message=(
                            "Norway structured change block is the address list of a word "
                            "substitution announced in prose, but the announcement's "
                            "(from, to) pair grammar did not parse, so the block was refused "
                            "instead of overwriting each listed provision with the "
                            "amendment's own text."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id=NO_PARSE_SUBSTITUTION_ANNOUNCEMENT_NOT_LOWERED,
                            phase="parse",
                            family="unsupported_or_unresolved_action",
                            blocking=True,
                            pair_shape=pair_shape,
                            **node_detail,
                        ),
                    )
                    continue
                group_sequence = sequence
                for raw_address in refused_addresses:
                    target = lovdata_path_to_address(raw_address)
                    if target is None:
                        _append_no_parse_adjudication(
                            adjudications_out,
                            kind=NO_PARSE_SUBSTITUTION_ADDRESS_NOT_LOWERABLE,
                            message=(
                                "Norway word-substitution address could not be lowered to a "
                                "legal address; the substitution was refused for that address."
                            ),
                            source_id=source_id,
                            detail=diagnostic_detail(
                                rule_id=NO_PARSE_SUBSTITUTION_ADDRESS_NOT_LOWERABLE,
                                phase="parse",
                                family="target_resolution_recovery",
                                blocking=True,
                                raw_address=raw_address,
                                base_id=base_id,
                                source_doc=source_doc,
                                announcement=announcement_text,
                            ),
                        )
                        continue
                    # W-69b: ``setning/N`` addresses are IN scope. W-69a refused
                    # them here (``no_parse_substitution_sentence_address_out_of_scope``,
                    # 21 receipts) because the apply plane materialized sentence
                    # children only on the structural branch, AFTER the text-patch
                    # branch had returned, so a sentence-addressed TEXT_PATCH could
                    # not resolve at all. ``_materialize_sentence_parent_for`` now
                    # runs on both branches, so the address resolves whenever its
                    # PARENT ledd does — and when the parent does not resolve (2 of
                    # the 21, both on ``no/lov/2020-04-17-29``, whose § 11 and § 18
                    # ledd are missing from the replayed tree) the op refuses at
                    # apply as ``replay_unresolved_target``, the same typed receipt
                    # the five unresolvable LEDD-addressed ops on that law already
                    # take (§ 11 andre ledd twice, tredje, fjerde, § 18 første). The
                    # parse plane has no statute, so resolution is not a conjunct it
                    # can evaluate; keeping a parse-plane sentence guard would only
                    # re-refuse the 17 addresses that do resolve.
                    for from_term, to_term in pairs:
                        doc_ops.append(
                            LegalOperation(
                                op_id=f"{source_id}:{sequence}",
                                sequence=sequence,
                                action=StructuralAction.TEXT_PATCH,
                                target=target,
                                text_patch=TextPatchSpec(
                                    kind=TextPatchKindEnum.REPLACE,
                                    selector=TextSelector(
                                        match_text=from_term,
                                        occurrence=0,
                                    ),
                                    replacement=to_term,
                                ),
                                # DEVIATION from W-69 design §1.2, recorded rather
                                # than taken silently: the design's op shape sets
                                # ``occurrence_mode="First"``. ``TextSelector``'s
                                # annotation is ``Literal["Auto", "Last"]`` (its
                                # ``__post_init__`` accepts "First", so core's type
                                # and its runtime contract already disagree), and
                                # NO's ``_apply_no_text_replace`` reads NEITHER
                                # ``occurrence`` nor ``occurrence_mode``. The
                                # exactly-one guarantee is carried by the apply-plane
                                # conjunct instead, which makes the field pure
                                # decoration here — and widening a core Literal for
                                # decoration reaches three ``us_federal`` branches
                                # that test ``occurrence_mode != "Auto"``.
                                source=OperationSource(
                                    statute_id=source_id,
                                    raw_text=announcement_text,
                                    title=source_doc,
                                ),
                                provenance_tags=(
                                    f"base_act:{base_id}",
                                    "scope:addressed",
                                    NO_SUBSTITUTION_PROVENANCE_TAG,
                                ),
                                # One group per (instrument, base act,
                                # announcement). The apply plane reads it together
                                # with the target path to recover the announcement's
                                # full FROM-term set for S6 — the pairs of one
                                # announcement are exactly the ops sharing this id
                                # and this address.
                                group_id=f"{source_id}:{base_id}:{group_sequence}",
                            )
                        )
                        sequence += 1
                continue

            specs: list[tuple[str, str]] = []
            renumber_specs = _split_move_attr(
                change_el.get("data-move-part", ""),
                adjudications_out=adjudications_out,
                source_id=source_id,
                base_id=base_id,
                source_doc=source_doc,
                raw_text=raw_text,
            )
            # W-56: the markup may under-declare the shift its own lead spells.
            # ``_split_move_attr`` hands back the legs already REVERSED (Lovtidend
            # writes them in ascending prose order and the shift must be applied
            # top-down), so the completion is computed in markup order and
            # reversed back on the same convention.
            completed_move_legs = _no_completed_move_legs_from_ledd_shift_prose(
                lead_text, list(reversed(renumber_specs))
            )
            if completed_move_legs is not None:
                _append_no_parse_adjudication(
                    adjudications_out,
                    kind=NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE,
                    message=(
                        "Norway parser completed an under-declared structured move attribute "
                        "from the change block's own ledd-shift lead sentence."
                    ),
                    source_id=source_id,
                    detail=diagnostic_detail(
                        rule_id=NO_PARSE_MOVE_LEGS_COMPLETED_FROM_LEAD_PROSE,
                        phase="parse",
                        family="source_pathology",
                        blocking=False,
                        base_id=base_id,
                        source_doc=source_doc,
                        declared_leg_count=len(renumber_specs),
                        completed_leg_count=len(completed_move_legs),
                        declared_legs=tuple(f"{src};;{dst}" for src, dst in reversed(renumber_specs)),
                        completed_legs=tuple(f"{src};;{dst}" for src, dst in completed_move_legs),
                        lead=lead_text,
                    ),
                )
                renumber_specs = list(reversed(completed_move_legs))
            # W-70b: the destination may name the WRONG SECTION. Runs LAST of the
            # three ``data-move-part`` productions — after W-70's separator repair
            # and after W-56's completion — so both see exactly the legs they saw
            # before this item, and the section repair applies to whatever leg set
            # they settled on. It is order-insensitive anyway (each destination is
            # rebuilt from its own declared ordinal), so ``renumber_specs`` stays
            # in the reversed convention it arrives in.
            if renumber_specs:
                destination_normalization = _no_normalize_move_attr_destination_section(
                    renumber_specs, announcement=lead_text, base_id=base_id
                )
                if destination_normalization.legs is not None:
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind=NO_PARSE_STRUCTURED_MOVE_ATTR_DESTINATION_SECTION_NORMALIZED,
                        message=(
                            "Norway parser rewrote a structured move attribute's destination "
                            "section to the change block's own section, on the block's own "
                            "announcement prose."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id=NO_PARSE_STRUCTURED_MOVE_ATTR_DESTINATION_SECTION_NORMALIZED,
                            phase="parse",
                            family="source_pathology",
                            blocking=False,
                            quirks_disposition=QuirksDisposition.APPLY,
                            reason=destination_normalization.reason,
                            base_id=base_id,
                            source_doc=source_doc,
                            attr_name="data-move-part",
                            prose_pattern=destination_normalization.pattern,
                            declared_destination_section=(
                                destination_normalization.destination_section
                            ),
                            normalized_destination_section=destination_normalization.source_section,
                            declared_legs=tuple(
                                f"{src};;{dst}" for src, dst in reversed(renumber_specs)
                            ),
                            normalized_legs=tuple(
                                f"{src};;{dst}"
                                for src, dst in reversed(destination_normalization.legs)
                            ),
                            announcement=lead_text,
                            raw_text=raw_text,
                        ),
                    )
                    renumber_specs = list(destination_normalization.legs)
            specs.extend(_split_change_attr(change_el.get("data-change-part", ""), "replace"))
            specs.extend(_split_change_attr(change_el.get("data-add-new-part", ""), "insert"))
            specs.extend(_split_change_attr(change_el.get("data-remove-part", ""), "repeal"))
            specs.extend(_split_change_attr(change_el.get("data-repeal-part", ""), "repeal"))

            parsed_specs: list[tuple[StructuralAction, LegalAddress]] = []
            skipped_cross_base_specs: list[tuple[str, str]] = []
            for action, raw_target in specs:
                if action == "renumber":
                    if ";;" not in raw_target:
                        continue
                    src, dst = raw_target.split(";;", 1)
                    renumber_specs.append((src, dst))
                    continue
                target_base = normalize_lovdata_refid(raw_target)
                if target_base is not None and target_base != base_id:
                    skipped_cross_base_specs.append((action, raw_target))
                    continue
                target = lovdata_path_to_address(raw_target)
                if target is not None:
                    parsed_specs.append((StructuralAction(action), target))
                    continue
                _append_no_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_unresolved_structured_target_skipped",
                    message="Norway parser skipped structured target whose path could not be lowered.",
                    source_id=source_id,
                    detail=diagnostic_detail(
                        rule_id="no_parse_unresolved_structured_target_skipped",
                        phase="parse",
                        family="target_resolution_recovery",
                        blocking=True,
                        base_id=base_id,
                        source_doc=source_doc,
                        action=action,
                        raw_target=raw_target,
                        target_base=target_base or "",
                        raw_text=raw_text,
                    ),
                )

            if skipped_cross_base_specs and parsed_specs:
                non_skipped_actions = {_no_action_value(action) for action, _target in parsed_specs}
                skipped_actions = {action for action, _raw_target in skipped_cross_base_specs}
                inferred_targets = _infer_same_base_subsection_targets(change_el)
                if (
                    len(non_skipped_actions | skipped_actions) == 1
                    and len(inferred_targets) == len(parsed_specs) + len(skipped_cross_base_specs)
                    and all(target.leaf_kind() == "subsection" for target in inferred_targets)
                ):
                    inferred_map = {target.path: target for target in inferred_targets}
                    existing_paths = {target.path for _action, target in parsed_specs}
                    if existing_paths.issubset(inferred_map):
                        action = next(iter(non_skipped_actions | skipped_actions))
                        recovered_specs = [(StructuralAction(action), target) for target in inferred_targets]
                        _append_no_structured_parse_recovery_adjudications(
                            adjudications_out,
                            source_id=source_id,
                            base_id=base_id,
                            source_doc=source_doc,
                            raw_text=raw_text,
                            reason="cross_base_structured_target_recovered_from_lead",
                            scope_confidence=NOScopeConfidence(rung_id="inferred_from_payload"),
                            original_specs=parsed_specs,
                            recovered_specs=recovered_specs,
                        )
                        parsed_specs = recovered_specs
                        skipped_cross_base_specs = []

            for action, raw_target in skipped_cross_base_specs:
                _append_no_parse_adjudication(
                    adjudications_out,
                    kind="no_parse_cross_base_structured_target_skipped",
                    message="Norway parser skipped structured target for a different base act.",
                    source_id=source_id,
                    detail=diagnostic_detail(
                        rule_id="no_parse_cross_base_structured_target_skipped",
                        phase="parse",
                        family="source_pathology",
                        blocking=True,
                        base_id=base_id,
                        source_doc=source_doc,
                        action=action,
                        raw_target=raw_target,
                        target_base=normalize_lovdata_refid(raw_target) or "",
                        raw_text=raw_text,
                    ),
                )

            inferred_sentence_specs = _infer_same_base_sentence_target_specs_from_lead(lead_text)
            if inferred_sentence_specs:
                recovered_specs = list(inferred_sentence_specs)
                _append_no_structured_parse_recovery_adjudications(
                    adjudications_out,
                    source_id=source_id,
                    base_id=base_id,
                    source_doc=source_doc,
                    raw_text=raw_text,
                    reason="sentence_targets_inferred_from_lead",
                    scope_confidence=NOScopeConfidence(rung_id="explicit_source_with_context"),
                    original_specs=parsed_specs,
                    recovered_specs=recovered_specs,
                )
                parsed_specs = recovered_specs

            inferred_targets = _infer_same_base_subsection_targets(change_el)
            if (
                inferred_targets
                and len(parsed_specs) == 1
                and parsed_specs[0][1].leaf_kind() == "section"
                and parsed_specs[0][0] in {StructuralAction.INSERT, StructuralAction.REPLACE}
            ):
                recovered_specs = [(parsed_specs[0][0], target) for target in inferred_targets]
                _append_no_structured_parse_recovery_adjudications(
                    adjudications_out,
                    source_id=source_id,
                    base_id=base_id,
                    source_doc=source_doc,
                    raw_text=raw_text,
                    reason="section_target_expanded_to_subsections_from_payload",
                    scope_confidence=NOScopeConfidence(rung_id="inferred_from_payload"),
                    original_specs=parsed_specs,
                    recovered_specs=recovered_specs,
                )
                parsed_specs = recovered_specs

            if (
                not inferred_sentence_specs
                and " nytt " in f" {lead_text.lower()} "
                and all(target.leaf_kind() == "subsection" for _action, target in parsed_specs)
            ):
                recovered_specs = [(StructuralAction.INSERT, target) for _action, target in parsed_specs]
                _append_no_structured_parse_recovery_adjudications(
                    adjudications_out,
                    source_id=source_id,
                    base_id=base_id,
                    source_doc=source_doc,
                    raw_text=raw_text,
                    reason="new_subsection_lead_recovered_insert_action",
                    scope_confidence=NOScopeConfidence(rung_id="explicit_source_with_context"),
                    original_specs=parsed_specs,
                    recovered_specs=recovered_specs,
                )
                parsed_specs = recovered_specs

            inferred_sentence_targets = _infer_same_base_sentence_targets(change_el)
            if (
                inferred_sentence_targets
                and parsed_specs
                and all(target.leaf_kind() in {"section", "subsection"} for _action, target in parsed_specs)
                and len({target.path[0] for _action, target in parsed_specs}) == 1
            ):
                recovered_specs = [(StructuralAction.REPLACE, target) for target in inferred_sentence_targets]
                _append_no_structured_parse_recovery_adjudications(
                    adjudications_out,
                    source_id=source_id,
                    base_id=base_id,
                    source_doc=source_doc,
                    raw_text=raw_text,
                    reason="sentence_targets_inferred_from_payload",
                    scope_confidence=NOScopeConfidence(rung_id="inferred_from_payload"),
                    original_specs=parsed_specs,
                    recovered_specs=recovered_specs,
                )
                parsed_specs = recovered_specs

            payload_candidates = _extract_payload_candidates(
                change_el,
                [target for _action, target in parsed_specs],
            )

            emitted_renumber_destinations: list[LegalAddress] = []
            for raw_target, raw_destination in renumber_specs:
                target_base = normalize_lovdata_refid(raw_target)
                dest_base = normalize_lovdata_refid(raw_destination)
                target_cross_base = target_base is not None and target_base != base_id
                destination_cross_base = dest_base is not None and dest_base != base_id
                if target_cross_base or destination_cross_base:
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind="no_parse_cross_base_structured_renumber_skipped",
                        message=(
                            "Norway parser skipped structured renumber whose source "
                            "or destination belongs to a different base act."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id="no_parse_cross_base_structured_renumber_skipped",
                            phase="parse",
                            family="source_pathology",
                            blocking=True,
                            base_id=base_id,
                            source_doc=source_doc,
                            raw_target=raw_target,
                            raw_destination=raw_destination,
                            target_base=target_base or "",
                            destination_base=dest_base or "",
                            target_cross_base=target_cross_base,
                            destination_cross_base=destination_cross_base,
                            raw_text=raw_text,
                        ),
                    )
                    continue
                target = lovdata_path_to_address(raw_target)
                destination = lovdata_path_to_address(raw_destination)
                if target is None or destination is None:
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind="no_parse_unresolved_structured_renumber_skipped",
                        message=(
                            "Norway parser skipped structured renumber whose source "
                            "or destination path could not be lowered."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id="no_parse_unresolved_structured_renumber_skipped",
                            phase="parse",
                            family="target_resolution_recovery",
                            blocking=True,
                            base_id=base_id,
                            source_doc=source_doc,
                            raw_target=raw_target,
                            raw_destination=raw_destination,
                            target_resolved=target is not None,
                            destination_resolved=destination is not None,
                            raw_text=raw_text,
                        ),
                    )
                    continue
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=StructuralAction.RENUMBER,
                        target=target,
                        destination=destination,
                        source=OperationSource(
                            statute_id=source_id,
                            raw_text=raw_text,
                            title=source_doc,
                        ),
                        provenance_tags=(f"base_act:{base_id}",),
                        group_id=f"{source_id}:{source_doc}:{sequence}",
                        witness_rule_id="no_section_renumber_relabel",
                    )
                )
                emitted_renumber_destinations.append(destination)
                sequence += 1

            # W-32(b): "§ 14 a blir ny § 28 b og skal lyde:" is TWO instructions --
            # a move and a replacement of the moved provision -- but Lovdata spells
            # only the move in markup (``data-move-part``) and leaves the
            # replacement to the lead sentence, so the payload used to be dropped
            # and the provision survived at its new address with its OLD text.
            # Measured surface: 286 change blocks carry ``data-move-part``; 25 have
            # a "skal lyde" lead; 18 of those ALSO carry a ``data-change-part``
            # naming the destination, so their payload already lowers and this
            # recovery must not fire for them (hence the ``not parsed_specs``
            # guard). The remaining 7 are the gap. The replacement targets the
            # DESTINATION and is sequenced after the renumber, because it is the
            # moved provision that is being rewritten.
            if (
                not parsed_specs
                and _no_structured_renumber_lead_declares_replacement(lead_text)
                and emitted_renumber_destinations
            ):
                if len(emitted_renumber_destinations) != 1:
                    # Several moves and one replacement clause: which moved
                    # provision the payload rewrites is not recoverable from the
                    # markup, and guessing would land live text on the wrong
                    # address. Receipt and drop (the W-19 all-or-nothing rule).
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind="no_parse_structured_renumber_replacement_not_lowered",
                        message=(
                            "Norway structured renumber lead declared a replacement but the "
                            "change block moved more than one provision; the replacement was "
                            "not lowered."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id="no_parse_structured_renumber_replacement_not_lowered",
                            phase="parse",
                            family="target_resolution_recovery",
                            blocking=True,
                            reason="move_arity_not_one",
                            base_id=base_id,
                            source_doc=source_doc,
                            move_count=len(emitted_renumber_destinations),
                            destinations=tuple(
                                _no_address_detail(dest) for dest in emitted_renumber_destinations
                            ),
                            raw_text=raw_text,
                        ),
                    )
                else:
                    destination = emitted_renumber_destinations[0]
                    replacement_candidates = _extract_payload_candidates(change_el, [destination])
                    payload = replacement_candidates.get((destination.leaf_kind(), destination.leaf_label()))
                    if payload is None:
                        payload = _heading_only_section_payload(change_el, StructuralAction.REPLACE, destination)
                    if payload is None:
                        # W-79's invariant needs no second refusal kind here: this
                        # site ALREADY refuses typed and blocking on a None payload,
                        # so a node that declares no payload of its own falls
                        # straight into ``payload_unresolved`` below rather than
                        # writing its own lead over the moved provision.
                        payload = _fallback_payload(change_el, StructuralAction.REPLACE, destination)
                    if payload is None:
                        _append_no_parse_adjudication(
                            adjudications_out,
                            kind="no_parse_structured_renumber_replacement_not_lowered",
                            message=(
                                "Norway structured renumber lead declared a replacement but no "
                                "payload could be extracted for the destination address."
                            ),
                            source_id=source_id,
                            detail=diagnostic_detail(
                                rule_id="no_parse_structured_renumber_replacement_not_lowered",
                                phase="parse",
                                family="payload_normalization",
                                blocking=True,
                                reason="payload_unresolved",
                                base_id=base_id,
                                source_doc=source_doc,
                                destination=_no_address_detail(destination),
                                raw_text=raw_text,
                            ),
                        )
                    else:
                        doc_ops.append(
                            LegalOperation(
                                op_id=f"{source_id}:{sequence}",
                                sequence=sequence,
                                action=StructuralAction.REPLACE,
                                target=destination,
                                payload=payload,
                                source=OperationSource(
                                    statute_id=source_id,
                                    raw_text=raw_text,
                                    title=source_doc,
                                ),
                                provenance_tags=(f"base_act:{base_id}", "recovery:renumber_replacement"),
                                group_id=f"{source_id}:{source_doc}:{sequence}",
                            )
                        )
                        sequence += 1

            for action, target in parsed_specs:
                payload = payload_candidates.get((target.leaf_kind(), target.leaf_label()))
                if payload is None:
                    payload = _heading_only_section_payload(change_el, action, target)
                if payload is None:
                    # W-79. The own-text fallback is the ONLY payload source in
                    # this lane that reads the amendment's own prose rather than a
                    # payload structure, so it is the only one that can write an
                    # instruction into a statute. It now refuses unless the node
                    # declares a payload; the refusal is per (action, target),
                    # because a node's other targets may resolve against a real
                    # candidate and must keep lowering.
                    undeclared: list[str] = []
                    payload = _fallback_payload(
                        change_el,
                        action,
                        target,
                        undeclared_out=undeclared,
                        declared_specs=parsed_specs,
                    )
                    if payload is None and undeclared:
                        _append_no_parse_adjudication(
                            adjudications_out,
                            kind=NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED,
                            message=(
                                "Norway structured change block declared a target but no "
                                "payload of its own; its own text is an instruction, not "
                                "content, so the target was refused rather than "
                                "overwritten with the amendment's own prose."
                            ),
                            source_id=source_id,
                            detail=diagnostic_detail(
                                rule_id=NO_PARSE_STRUCTURED_PAYLOAD_NOT_DECLARED,
                                phase="parse",
                                family="payload_normalization",
                                blocking=True,
                                base_id=base_id,
                                source_doc=source_doc,
                                action=_no_action_value(action),
                                target=_no_address_detail(target),
                                undeclared_text=undeclared[0],
                                declared_targets=len(parsed_specs),
                                raw_text=raw_text,
                            ),
                        )
                        continue
                if payload is not None and _no_action_value(action) in ("repeal", "text_repeal"):
                    # The payload-candidate map is consulted for every action with
                    # no filter, so a structured REPEAL/TEXT_REPEAL can pick up a
                    # synthesised structural payload.  (The ``_*_payload`` fallbacks
                    # are already repeal-gated to None.)  Repeals never carry
                    # content, so we coerce the payload to None here to keep the
                    # repeal-payload=None invariant structurally enforced and record
                    # the dropped payload kind/label so the closed hole stays
                    # auditable.
                    dropped_kind = _no_kind_value(payload.kind)
                    dropped_label = payload.label or ""
                    _append_no_parse_adjudication(
                        adjudications_out,
                        kind="no_repeal_payload_dropped",
                        message=(
                            "Norway repeal/text_repeal lowering carried a synthesised "
                            f"structural payload (kind={dropped_kind!r}, "
                            f"label={dropped_label!r}); repeals never carry content, "
                            "so lowering coerced the payload to None."
                        ),
                        source_id=source_id,
                        detail=diagnostic_detail(
                            rule_id="no_repeal_payload_dropped",
                            phase="parse",
                            family="payload_normalization",
                            blocking=False,
                            quirks_disposition=QuirksDisposition.APPLY,
                            base_id=base_id,
                            source_doc=source_doc,
                            action=_no_action_value(action),
                            target=str(target),
                            dropped_payload_kind=dropped_kind,
                            dropped_payload_label=dropped_label,
                            raw_text=raw_text,
                        ),
                    )
                    payload = None
                doc_ops.append(
                    LegalOperation(
                        op_id=f"{source_id}:{sequence}",
                        sequence=sequence,
                        action=action,
                        target=target,
                        payload=payload if payload is not None else None,
                        source=OperationSource(
                            statute_id=source_id,
                            raw_text=raw_text,
                            title=source_doc,
                        ),
                        provenance_tags=(f"base_act:{base_id}",),
                        group_id=f"{source_id}:{source_doc}:{sequence}",
                    )
                )
                sequence += 1
        if doc_ops:
            grouped.append((base_id, _promote_no_replace_with_following_renumber_insert(doc_ops)))

    return _with_no_resanctioned_provenance(
        _with_no_beriktiget_provenance(
            _with_no_rettelse_groups(grouped, root, source_id, adjudications_out=adjudications_out),
            html_bytes,
            source_id,
            adjudications_out=adjudications_out,
        ),
        html_bytes,
        source_id,
        adjudications_out=adjudications_out,
    )


def _no_sort_key(
    label: Optional[str],
    *,
    roman_single_letters: bool = False,
) -> tuple[int, str, int]:
    if not label:
        return (-1, "", 0)
    cased = _normalize_label(label)
    normalized = cased.lower()
    hyphen_match = re.match(r"^(\d+)-(\d+)([a-z]*)$", normalized)
    if hyphen_match:
        major, minor, suffix = hyphen_match.groups()
        return (int(major) * 10000 + int(minor), suffix, 0)
    letter_match = re.match(r"^(\d+)([a-z]*)$", normalized)
    if letter_match:
        number, suffix = letter_match.groups()
        return (int(number), suffix, 0)
    # Roman-numeral ordering is genuine for chapter/part labels (uppercase
    # ``I, II, ... IX``) and for multi-character lowercase roman sub-items
    # (``ii, iii, iv``). A *single* lowercase Latin letter is normally a
    # Norwegian litra (bokstav: ``a, b, c, d, e, ...``), NOT a roman numeral --
    # treating ``c`` as 100 or ``d`` as 500 breaks the alphabetic ordering of
    # litra lists and spuriously trips the replay order invariant on untouched
    # subtrees. The single exception is a sibling group that is itself a roman
    # sequence (``i, ii, ..., v, ..., ix``), where a lone ``v``/``x`` IS roman;
    # callers that know the sibling context pass ``roman_single_letters=True``.
    is_single_lowercase_letter = len(cased) == 1 and cased.islower() and cased.isalpha()
    if roman_single_letters or not is_single_lowercase_letter:
        roman = _roman_to_int(cased)
        if roman is not None:
            return (roman, "", 0)
    return tree_ops.default_label_sort_key(normalized)


def _no_sibling_group_uses_roman_single_letters(labels: Sequence[Optional[str]]) -> bool:
    """Decide whether an ordered same-kind sibling group is a roman sequence.

    Lone lowercase ``i``/``v``/``x``/``l``/``c``/``d``/``m`` are ambiguous: they
    are litra in an alphabetic bokstav list (``a, b, c, ...``) but roman in a
    roman list (``i, ii, iii, iv, v, ...``). The deciding signal is the sibling
    set: a roman list contains a multi-character lowercase roman label
    (``ii``/``iii``/...) and never contains a non-roman litra letter
    (``a``/``b``/``f``/``g``/``h``/``j``/``k``/...).
    """
    norm = [(_normalize_label(label).lower()) for label in labels if label]
    if not norm:
        return False
    has_multichar_roman = any(len(s) > 1 and re.fullmatch(r"[ivxlcdm]+", s) for s in norm)
    if not has_multichar_roman:
        return False
    # Any single letter outside the roman alphabet means this is a litra list.
    return all(re.fullmatch(r"[ivxlcdm]+", s) for s in norm)


def _resolve_no_path(body: IRNode, target: LegalAddress) -> Optional[tree_ops.Path]:
    """Resolve a possibly shallow Lovdata target against the current tree."""
    full_path: Optional[tree_ops.Path] = None
    for idx, (kind, label) in enumerate(target.path):
        if idx == 0:
            full_path = tree_ops.find(body, kind, label)
        elif full_path is not None:
            parent_node = tree_ops.resolve(body, full_path)
            if parent_node is None:
                return None
            if kind == "sentence" and label == "last":
                parent_path = full_path
                body = _materialize_no_sentence_children(body, parent_path)
                full_path = _find_last_direct_child_path(body, parent_path, "sentence")
                if full_path is None:
                    return None
                continue
            inner_path = tree_ops.find(parent_node, kind, label)
            if inner_path is None:
                return None
            full_path = full_path + inner_path
        if full_path is None:
            return None
    return full_path


def _find_insert_parent(scope_node: IRNode, content_kind: str) -> Optional[tree_ops.Path]:
    """Find a unique descendant container whose direct children match content kind."""
    matches: list[tree_ops.Path] = []

    def _walk(node: IRNode, prefix: tree_ops.Path) -> None:
        if any(_no_kind_value(child.kind) == content_kind for child in node.children):
            matches.append(prefix)
        for child in node.children:
            step = (str(child.kind), child.label or "")
            _walk(child, prefix + (step,))

    _walk(scope_node, ())
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_no_last_child_path(
    body: IRNode,
    parent_path: tree_ops.Path,
    child_kind: str,
) -> Optional[tree_ops.Path]:
    parent_node = tree_ops.resolve(body, parent_path) if parent_path else body
    if parent_node is None:
        return None
    matches = [
        parent_path + ((str(child.kind), child.label or ""),)
        for child in parent_node.children
        if child.kind == child_kind and child.label
    ]
    if not matches:
        return None
    return max(matches, key=lambda path: _no_sort_key(path[-1][1]))


def _next_no_child_label(parent_node: IRNode, child_kind: str) -> str:
    labels = [child.label or "" for child in parent_node.children if child.kind == child_kind and child.label]
    numeric = [int(label) for label in labels if label.isdigit()]
    if labels and len(numeric) == len(labels):
        return str(max(numeric) + 1)
    alpha = [label for label in labels if len(label) == 1 and label.isalpha()]
    if labels and len(alpha) == len(labels):
        return chr(max(ord(label.lower()) for label in alpha) + 1)
    if numeric:
        return str(max(numeric) + 1)
    return "1"


def _section_family_prefix(label: str) -> Optional[str]:
    normalized = _normalize_label(label)
    hyphen_match = re.match(r"^(\d+)-", normalized)
    if hyphen_match:
        return f"{hyphen_match.group(1)}-"
    number_match = re.match(r"^(\d+)", normalized)
    if number_match:
        return number_match.group(1)
    return None


def _iter_paths(node: IRNode, prefix: Optional[tree_ops.Path] = None) -> Generator[tree_ops.Path, None, None]:
    prefix = prefix or ()
    for child in node.children:
        path = prefix + ((str(child.kind), child.label or ""),)
        yield path
        yield from _iter_paths(child, path)


def _infer_section_parent_path(body: IRNode, section_label: str) -> Optional[tree_ops.Path]:
    """Infer chapter/container for a new Norway section from nearby existing section labels."""
    family = _section_family_prefix(section_label)
    if not family:
        return None
    parent_paths: set[tuple[tuple[str, str], ...]] = set()
    for path in _iter_paths(body):
        if not path:
            continue
        kind, label = path[-1]
        if kind != "section":
            continue
        normalized = _normalize_label(label)
        if family.endswith("-"):
            matches = normalized.startswith(family)
        else:
            matches = normalized == family or normalized.startswith(f"{family}-") or normalized.startswith(f"{family}a")
        if matches and path[:-1]:
            parent_paths.add(tuple(path[:-1]))
    if len(parent_paths) == 1:
        return next(iter(parent_paths))
    return None


def _resolve_existing_prefix(
    body: IRNode,
    target: LegalAddress,
) -> tuple[Optional[tree_ops.Path], int]:
    """Resolve the longest existing prefix of a Norway target address."""
    if not target.path:
        return None, 0
    full_path: Optional[tree_ops.Path] = None
    matched = 0
    for idx, (kind, label) in enumerate(target.path):
        if idx == 0:
            candidate = tree_ops.find(body, kind, label)
        elif full_path is not None:
            scope_kind, scope_label = full_path[-1]
            candidate = tree_ops.find(
                body,
                kind,
                label,
                scope_kind=scope_kind,
                scope_label=scope_label,
            )
        else:
            candidate = None
        if candidate is None:
            break
        full_path = candidate
        matched = idx + 1
    return full_path, matched


def _ensure_no_container_chain(
    body: IRNode,
    base_path: tree_ops.Path,
    missing_steps: Sequence[tuple[str, str]],
) -> tuple[IRNode, tree_ops.Path]:
    """Create missing address containers before inserting leaf content."""
    current_path = list(base_path)
    for kind, label in missing_steps:
        body = tree_ops.insert_sorted(
            body,
            current_path,
            IRNode(kind=IRNodeKind(kind), label=label),
            sort_key_fn=_no_sort_key,
        )
        current_path = current_path + [(kind, label)]
    return body, tuple(current_path)


def _materialize_no_sentence_children_with_count(body: IRNode, parent_path: tree_ops.Path) -> tuple[IRNode, int]:
    """Split raw subsection/item text into sentence children on demand."""
    parent = tree_ops.resolve(body, parent_path)
    if parent is None:
        return body, 0
    if _no_kind_value(parent.kind) not in {"subsection", "item"}:
        return body, 0
    if not parent.text or any(_no_kind_value(child.kind) == "sentence" for child in parent.children):
        return body, 0
    sentences = _split_no_sentences(parent.text)
    if not sentences:
        return body, 0
    replacement = IRNode(
        kind=parent.kind,
        label=parent.label,
        text="",
        attrs=dict(parent.attrs),
        children=tuple(
            [
                IRNode(kind=IRNodeKind.SENTENCE, label=str(index), text=sentence_text)
                for index, sentence_text in enumerate(sentences, start=1)
            ]
            + [child for child in parent.children]
        ),
    )
    return tree_ops.replace_at(body, parent_path, replacement), len(sentences)


def _materialize_no_sentence_children(body: IRNode, parent_path: tree_ops.Path) -> IRNode:
    materialized_body, _count = _materialize_no_sentence_children_with_count(body, parent_path)
    return materialized_body


def _resolve_shallow_no_sentence_path(
    body: IRNode,
    target: LegalAddress,
) -> tuple[IRNode, Optional[tree_ops.Path], Optional[tree_ops.Path], int]:
    """Resolve section-level sentence targets via a unique direct text container."""
    if len(target.path) != 2 or target.path[0][0] != "section" or target.path[1][0] != "sentence":
        return body, None, None, 0
    section_path = _resolve_no_path(body, LegalAddress(path=(target.path[0],)))
    if section_path is None:
        return body, None, None, 0
    section_node = tree_ops.resolve(body, section_path)
    if section_node is None:
        return body, None, None, 0
    hosts = [child for child in section_node.children if _no_kind_value(child.kind) in {"subsection", "item"}]
    if len(hosts) != 1:
        return body, None, None, 0
    host = hosts[0]
    host_path = section_path + ((str(host.kind), host.label or ""),)
    body, materialized_count = _materialize_no_sentence_children_with_count(body, host_path)
    if target.path[1][1] == "last":
        resolved = _find_last_direct_child_path(body, host_path, "sentence")
    else:
        resolved = _find_direct_child_path(body, host_path, "sentence", target.path[1][1])
    return body, resolved, host_path, materialized_count


def _resolve_shallow_no_sentence_host_path(
    body: IRNode,
    target: LegalAddress,
) -> tuple[IRNode, Optional[tree_ops.Path], int]:
    """Resolve the unique host path for section-level sentence targets."""
    if len(target.path) != 2 or target.path[0][0] != "section" or target.path[1][0] != "sentence":
        return body, None, 0
    section_path = _resolve_no_path(body, LegalAddress(path=(target.path[0],)))
    if section_path is None:
        return body, None, 0
    section_node = tree_ops.resolve(body, section_path)
    if section_node is None:
        return body, None, 0
    hosts = [child for child in section_node.children if _no_kind_value(child.kind) in {"subsection", "item"}]
    if len(hosts) != 1:
        return body, None, 0
    host = hosts[0]
    host_path = section_path + ((str(host.kind), host.label or ""),)
    body, materialized_count = _materialize_no_sentence_children_with_count(body, host_path)
    return body, host_path, materialized_count


def _roman_to_int(label: str) -> Optional[int]:
    """Norway-side wrapper that normalises the label first then delegates.

    The shared ``lawvm.roman`` parser rejects non-canonical spellings via
    round-trip canonicalization, fixing a latent bug in the previous
    inline implementation where the ``prev`` tracker only updated in the
    additive branch.
    """
    return _shared_roman_to_int(_normalize_label(label))


def _numeric_chapter_label(label: str) -> str:
    roman = _roman_to_int(label)
    if roman is not None:
        return str(roman)
    return _normalize_label(label)


def _label_in_range(label: str, start_label: str, end_label: str) -> bool:
    key = _no_sort_key(label)
    return _no_sort_key(start_label) <= key <= _no_sort_key(end_label)


def _replace_node_at_path(tree: IRNode, path: tree_ops.Path, replacement: IRNode) -> IRNode:
    if not path:
        return replacement
    head_kind, head_label = path[0]
    new_children: list[IRNode] = []
    for child in tree.children:
        if _no_kind_value(child.kind) == head_kind and (child.label or "") == head_label:
            new_children.append(_replace_node_at_path(child, path[1:], replacement))
        else:
            new_children.append(child)
    return IRNode(
        kind=tree.kind,
        label=tree.label,
        text=tree.text,
        attrs=dict(tree.attrs),
        children=tuple(new_children),
    )


def _with_no_node_label(node: IRNode, label: str | None) -> IRNode:
    return IRNode(
        kind=node.kind,
        label=label,
        text=node.text,
        attrs=dict(node.attrs),
        children=node.children,
    )


def _find_direct_child_path(
    body: IRNode,
    parent_path: tree_ops.Path,
    kind: str,
    label: Optional[str],
) -> Optional[tree_ops.Path]:
    parent = tree_ops.resolve(body, parent_path) if parent_path else body
    if parent is None:
        return None
    normalized_label = label or ""
    for child in parent.children:
        if _no_kind_value(child.kind) == kind and (child.label or "") == normalized_label:
            return parent_path + ((str(child.kind), child.label or ""),)
    return None


def _find_last_direct_child_path(
    body: IRNode,
    parent_path: tree_ops.Path,
    kind: str,
) -> Optional[tree_ops.Path]:
    parent = tree_ops.resolve(body, parent_path) if parent_path else body
    if parent is None:
        return None
    numeric_children = [
        child
        for child in parent.children
        if _no_kind_value(child.kind) == kind and child.label and re.fullmatch(r"\d+", child.label)
    ]
    if not numeric_children:
        return None
    last_label = str(max(int(child.label) for child in numeric_children if child.label))
    return _find_direct_child_path(body, parent_path, kind, last_label)


def _appendable_no_sentence_target(
    body: IRNode,
    parent_path: tree_ops.Path,
    target_label: Optional[str],
) -> bool:
    if not target_label or re.fullmatch(r"\d+", target_label) is None:
        return False
    parent = tree_ops.resolve(body, parent_path)
    if parent is None:
        return False
    sentence_labels = [
        int(child.label)
        for child in parent.children
        if _no_kind_value(child.kind) == "sentence" and child.label and re.fullmatch(r"\d+", child.label)
    ]
    if not sentence_labels:
        return False
    return int(target_label) == max(sentence_labels) + 1


def _appendable_no_item_payload(
    body: IRNode,
    parent_path: tree_ops.Path,
    payload: IRNode,
) -> IRNode:
    if _no_kind_value(payload.kind) != "item" or payload.label != "last":
        return payload
    parent = tree_ops.resolve(body, parent_path)
    if parent is None:
        return payload
    item_labels = [
        int(child.label)
        for child in parent.children
        if _no_kind_value(child.kind) == "item" and child.label and re.fullmatch(r"\d+", child.label)
    ]
    next_label = str(max(item_labels) + 1) if item_labels else "1"
    return IRNode(
        kind=payload.kind,
        label=next_label,
        text=payload.text,
        attrs=dict(payload.attrs),
        children=payload.children,
    )


def _apply_no_text_replace(node: IRNode, match: str, replacement: str) -> IRNode:
    return IRNode(
        kind=node.kind,
        label=node.label,
        text=node.text.replace(match, replacement) if node.text else node.text,
        attrs=dict(node.attrs),
        children=tuple(_apply_no_text_replace(child, match, replacement) for child in node.children),
    )


def _apply_heading_group(body: IRNode, group: NOHeadingGroup) -> IRNode:
    start_path = tree_ops.find(body, "section", group.start_label)
    if start_path is None or not start_path:
        return body
    parent_path = start_path[:-1]
    parent_node = tree_ops.resolve(body, parent_path)
    if parent_node is None:
        return body

    matched_sections = [
        child
        for child in parent_node.children
        if _no_kind_value(child.kind) == "section"
        and child.label
        and _label_in_range(child.label, group.start_label, group.end_label)
    ]
    if not matched_sections:
        return body

    chapter_labels = [_numeric_chapter_label(label) for kind, label in parent_path if kind == "chapter" and label]
    if not chapter_labels:
        return body
    group_label = "-".join(chapter_labels + [str(group.sequence)])

    if any(_no_kind_value(child.kind) == "chapter" and child.label == group_label for child in parent_node.children):
        return body

    section_labels = {child.label for child in matched_sections}
    grouped_children = (IRNode(kind=IRNodeKind.HEADING, text=group.title), *matched_sections)
    grouped_node = IRNode(kind=IRNodeKind.CHAPTER, label=group_label, children=grouped_children)

    new_children: list[IRNode] = []
    inserted = False
    for child in parent_node.children:
        if _no_kind_value(child.kind) == "section" and child.label in section_labels:
            if not inserted:
                new_children.append(grouped_node)
                inserted = True
            continue
        new_children.append(child)
    if not inserted:
        new_children.append(grouped_node)

    replacement = IRNode(
        kind=parent_node.kind,
        label=parent_node.label,
        text=parent_node.text,
        attrs=dict(parent_node.attrs),
        children=tuple(new_children),
    )
    return _replace_node_at_path(body, parent_path, replacement)


NO_HEADING_GROUP_MULTI_SOURCE_FOLD = "no_heading_group_multi_source_fold"


def _emit_no_heading_group_fold_witness(
    statute: IRStatute,
    heading_groups: Sequence[NOHeadingGroup],
    *,
    adjudications_out: Optional[List[CompileAdjudication]],
) -> None:
    """Receipt the first time one law's heading groups come from two amendments.

    §2.9 guard liveness: the multi-contributor case is unreached in today's
    corpus (measured: 0 of 3,089 laws with an original LTI), so the fix for it
    is unobservable unless the case announces itself. This witness makes the
    transition from latent to live visible in the receipt plane instead of
    silent.

    ``blocking`` is set only when a contributing group reached the fold with NO
    temporal coordinates (``source`` absent or undated). With coordinates the
    order is proven by the kernel's temporal key and the fold is trustworthy —
    the receipt is then a non-blocking notice. Without them the sort degenerates
    to the input order the item was filed against, so the order is unproven and
    the law must not be reported as cleanly replayed (§1.10 fail loud).
    """
    if adjudications_out is None:
        return
    distinct = sorted(
        {group.source.statute_id for group in heading_groups if group.source and group.source.statute_id}
    )
    unidentified = any(not (group.source and group.source.statute_id) for group in heading_groups)
    # Groups with no affecting-act identity count as ONE unknown contributor:
    # two of them are indistinguishable, so counting them individually would
    # fire this receipt on the single-amendment parser-only path.
    if len(distinct) + (1 if unidentified else 0) <= 1:
        return
    undated = sorted(
        {
            (group.source.statute_id if group.source else "")
            for group in heading_groups
            if group.source is None or not group.source.effective
        }
    )
    blocking = bool(undated)
    adjudications_out.append(
        CompileAdjudication(
            kind=NO_HEADING_GROUP_MULTI_SOURCE_FOLD,
            message=(
                "Norway heading-group fold received groups from more than one amendment"
                + (
                    "; at least one carries no effective date, so the fold order is unproven."
                    if blocking
                    else "; folded in ordering-kernel temporal order."
                )
            ),
            source_statute=statute.statute_id,
            op_id="",
            blocking=blocking,
            phase="replay",
            detail=diagnostic_detail(
                rule_id=NO_HEADING_GROUP_MULTI_SOURCE_FOLD,
                phase="replay",
                blocking=blocking,
                family="ordering",
                base_id=statute.statute_id,
                source_ids=distinct,
                group_count=len(heading_groups),
                undated_source_ids=undated,
            ),
        )
    )


def _no_heading_group_order_carrier(group: NOHeadingGroup) -> LegalOperation:
    """A key-only ``LegalOperation`` standing in for ``group`` in the temporal sort.

    Heading groups are not state-mutating ops: they carry no target address and
    are folded in their own pass AFTER ``apply_no_ops``, so they cannot be run
    through ``order_ops`` itself — its stage 3 (same-moment cross-act conflict)
    and stage 5 (renumber vacate) are op-semantics stages that would fabricate
    findings about ops that do not exist. What heading groups DO need is stage
    1, the temporal sort, and that stage's key is ``profile.temporal_key``.
    This carrier exists so that key is computed by the kernel's own
    ``no_ordering_profile()`` rather than by a second copy of ``(effective,
    enacted, source_id, sequence)`` — the parallel-ordering-surface drift W-12
    exists to close. It never leaves this module: no op id, no receipt, no
    apply.
    """
    return LegalOperation(
        op_id="",
        sequence=group.sequence,
        action=StructuralAction.INSERT,
        target=LegalAddress(path=()),
        source=group.source,
    )


def _no_heading_group_temporal_key(group: NOHeadingGroup) -> tuple[Any, int]:
    """The kernel's stage-1 sort key for a heading group.

    Mirrors ``order_ops``' stage 1 exactly: ``(temporal_key(op), op.sequence)``.
    """
    carrier = _no_heading_group_order_carrier(group)
    return (no_ordering_profile().temporal_key(carrier), carrier.sequence)


def apply_no_heading_groups(
    statute: IRStatute,
    heading_groups: Sequence[NOHeadingGroup],
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
) -> IRStatute:
    """Regroup flat Norway section ranges under synthetic subchapter containers.

    The fold is temporally ordered (W-12). Before this, groups were folded in
    the order ``replay_no_to_pit`` collected them — which is the index's
    ``source_id`` string order, not effective-date order. Latent at the time of
    the fix: a census over all 2,544 index entries × their declared base ids
    found heading groups for exactly ONE law (``no/lov/2024-01-12-1``, three
    groups, all from ``no/lovtid/2024-12-20-92``), so no corpus law had two
    contributors and every replay is byte-identical across the change. It stops
    being latent the first time two amendments carry ``Ny deloverskrift`` for
    one act.

    Two things had to change for the multi-contributor case to be correct, not
    just ordered:

    * the sort — by the ordering kernel's own temporal key (see
      :func:`_no_heading_group_temporal_key`);
    * the ``sequence`` re-stamp — ``sequence`` is not an identity, it is the
      namespace of the synthetic container label ``_apply_heading_group``
      mints (``<chapter labels>-<sequence>``), and the parser restarts it at 1
      per amendment document. Two amendments touching one chapter would both
      mint label ``…-1``, and the second would hit the idempotence guard in
      ``_apply_heading_group`` and be SILENTLY DROPPED. Re-stamping to the
      1-based position in the temporally sorted fold makes the namespace
      global. For a single contributor whose parser sequences are already
      ``1..n`` this is the identity (the corpus witness's are ``1,2,3``).
    """
    ordered_groups = [
        dc_replace(group, sequence=position)
        for position, group in enumerate(sorted(heading_groups, key=_no_heading_group_temporal_key), start=1)
    ]
    _emit_no_heading_group_fold_witness(statute, heading_groups, adjudications_out=adjudications_out)
    body = statute.body
    for group in ordered_groups:
        body = _apply_heading_group(body, group)
    return IRStatute(
        statute_id=statute.statute_id,
        title=statute.title,
        body=body,
        supplements=statute.supplements,
        metadata=dict(statute.metadata),
    )


def _append_no_replay_adjudication(
    adjudications_out: Optional[List[CompileAdjudication]],
    *,
    kind: str,
    message: str,
    op: LegalOperation,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Append a Norway replay adjudication when a sink list is available."""
    if adjudications_out is None:
        return
    raw_detail = dict(detail or {})
    detail_rule_id = str(raw_detail.pop("rule_id", "") or "")
    detail_family = str(raw_detail.pop("family", "") or "")
    detail_reason = str(raw_detail.pop("reason", "") or "")
    detail_message = str(raw_detail.pop("message", "") or "")
    if kind in {"replay_unsupported_action", "replay_unresolved_target", "replay_noop"}:
        family = "unsupported_or_unresolved_action"
    elif kind in {
        "replay_tree_invariant_violation",
        "replay_tree_invariant_violation_downgraded",
    }:
        family = "tree_invariant_violation"
    elif kind.startswith("no_replay_"):
        family = "action_family_recovery"
    else:
        family = ""
    normalized_detail = diagnostic_detail(
        rule_id=detail_rule_id or kind,
        phase="replay",
        blocking=True,
        family=detail_family or family,
        reason=detail_reason,
        message=detail_message,
        detail=raw_detail,
    )
    adjudications_out.append(
        CompileAdjudication(
            kind=kind,
            message=message,
            source_statute=op.source.statute_id if op.source else "",
            op_id=op.op_id,
            blocking=True,
            phase="replay",
            detail=normalized_detail,
        )
    )


def _no_path_label(path: tree_ops.Path) -> str:
    return "/".join(f"{kind}:{label}" for kind, label in path)


def _no_replay_payload_detail(payload: Optional[IRNode]) -> dict[str, str]:
    if payload is None:
        return {}
    return {
        "payload_kind": _no_kind_value(payload.kind),
        "payload_label": payload.label or "",
    }


def _no_temporal_key(op: LegalOperation) -> tuple[str, str, str, int]:
    """NO's temporal/group sort key: ``(effective, enacted, source_id, sequence)``.

    The verbatim lift of ``apply_no_ops``'s old ``_group_sort_key``. The shared
    kernel's stage-1 temporal sort uses this; its first three components also
    serve as the structural-vacate group identity (see :func:`_no_group_key`).
    """
    effective = op.source.effective if op.source and op.source.effective else ""
    enacted = op.source.enacted if op.source and op.source.enacted else ""
    source_id = op.source.statute_id if op.source and op.source.statute_id else ""
    return (effective, enacted, source_id, op.sequence)


def _no_group_key(op: LegalOperation) -> tuple[str, str, str]:
    """NO's structural-vacate group identity: ``(effective, enacted, source_id)``.

    The verbatim lift of ``apply_no_ops``'s old ``_group_identity`` — the
    temporal key minus its ``sequence`` tail. The kernel partitions the
    temporally sorted ops by this so REPEAL-first / topological-RENUMBER /
    rest-by-sequence is applied per affecting-act moment.
    """
    effective = op.source.effective if op.source and op.source.effective else ""
    enacted = op.source.enacted if op.source and op.source.enacted else ""
    source_id = op.source.statute_id if op.source and op.source.statute_id else ""
    return (effective, enacted, source_id)


def _no_renumber_tiebreak_key(
    op: LegalOperation,
) -> tuple[int, tuple[tuple[int, str, int], ...], int]:
    """NO's independent-renumber tiebreak: the verbatim old ``_renumber_sort_key``.

    Orders genuinely independent RENUMBER ops (no vacate dependency between
    them) inside the topological sort by ``(path-depth, label-sort-keys,
    sequence)``; the kernel's DFS enforces vacate-before-occupy regardless.
    """
    return (
        len(op.target.path),
        tuple(_no_sort_key(label) for _kind, label in op.target.path),
        op.sequence,
    )


#: A dependency node in the generalized atomic ordering: the resolved
#: ``(parent_path, label)`` pair, spelled as the full ``LegalAddress.path`` it
#: already is (``path[:-1]`` is the parent, ``path[-1]`` is the ``(kind, label)``
#: step). Nothing in the analysis below is ordinal, so a leg that leaves its
#: container is an ordinary node like any other.
_NORelocationNode = tuple[tuple[str, str], ...]


def _no_unprovable_relocation_targets(
    renumbers: Sequence[LegalOperation],
) -> frozenset[_NORelocationNode]:
    """Target paths of the RENUMBER legs whose relocation has no safe order.

    ``renumbers`` is one affecting-act group's RENUMBER legs (``destination`` not
    ``None``). Returns the ``target.path`` of every leg that must refuse.

    THE GRAPH. Vertices are ``(parent_path, label)`` nodes — every path that
    appears as a leg's source or destination. Each leg is an edge between its two
    endpoints. Two legs are in the same ATOMIC COMPONENT when the edges connect
    them, transitively; legs in different components address disjoint sets of
    nodes and therefore cannot interfere, so each component is judged alone.

    THE THREE WAYS A COMPONENT IS UNPROVABLE, all of them "no permutation of
    these legs satisfies the constraint", none of them fixable by sorting:

    * **Contested destination** — two legs name the same destination. Whichever
      runs second writes onto the first. This is the shape that aborts
      ``no/lov/2009-06-19-44`` today, and it is invisible to a sort that only
      maps destinations back to sources.
    * **Contested source** — two legs move the same node somewhere DIFFERENT. The
      second finds it gone, or finds a later occupant standing at the old
      address and moves the wrong node.
    * **Cycle** — ``3→4`` with ``4→3``, a swap, which sequential relabelling
      cannot express without a scratch slot. W-66's guard, at the new keying.

    WHAT IS NOT A CONFLICT, and both cases are in the corpus, so neither is
    hypothetical:

    * **A repeated leg.** The same ``(source, destination)`` announced twice is
      ONE instruction, not two contradictory ones — it is satisfied by applying
      it once, and today the second copy simply fails to resolve its source and
      takes the typed ``replay_unresolved_target`` skip. Legs are deduplicated
      before the analysis so a repeat cannot be mistaken for a contest.
      Measured: ``no/lov/1999-03-26-14`` (``§10-65/ledd/2 → ledd/3`` twice, from
      ``no/lovtid/2013-12-13-117``) and ``no/lov/2017-06-16-53``
      (``§30/ledd/2 → ledd/3`` twice, from ``no/lovtid/2018-06-15-38``) would
      both refuse a legitimate move without this.
    * **A leg that goes nowhere.** ``source == destination`` is a no-op edge; it
      joins its component but conflicts with nothing.

    Deterministic and order-independent: the analysis reads only op ADDRESSES, so
    the same group yields the same refusal set regardless of the order the kernel
    emitted, which is what makes "nothing half-applies" a property rather than a
    hope.
    """
    seen_legs: set[tuple[_NORelocationNode, _NORelocationNode]] = set()
    legs: list[tuple[_NORelocationNode, _NORelocationNode]] = []
    for op in renumbers:
        if op.destination is None:
            continue
        leg = (op.target.path, op.destination.path)
        if leg in seen_legs:
            continue
        seen_legs.add(leg)
        legs.append(leg)
    if not legs:
        return frozenset()

    # Union-find over the nodes; each leg unions its two endpoints.
    parent: dict[_NORelocationNode, _NORelocationNode] = {}

    def _find(node: _NORelocationNode) -> _NORelocationNode:
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:  # path compression
            parent[node], node = root, parent[node]
        return root

    def _union(left: _NORelocationNode, right: _NORelocationNode) -> None:
        left_root, right_root = _find(left), _find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    for source, destination in legs:
        _union(source, destination)

    # Conflicting components: a destination or a source claimed by two legs.
    conflicted: set[_NORelocationNode] = set()
    seen_destinations: set[_NORelocationNode] = set()
    seen_sources: set[_NORelocationNode] = set()
    for source, destination in legs:
        if destination in seen_destinations:
            conflicted.add(_find(destination))
        seen_destinations.add(destination)
        if source in seen_sources:
            conflicted.add(_find(source))
        seen_sources.add(source)

    # Cycles in "my destination is your source" — the same relation the kernel's
    # structural-vacate stage sorts on, re-read here for provability rather than
    # for an order. Iterative DFS with a three-colour marking (0 = on stack,
    # 1 = finished) so a deep chain cannot blow the interpreter stack.
    by_source: dict[_NORelocationNode, _NORelocationNode] = {}
    for source, destination in legs:
        by_source.setdefault(source, destination)
    state: dict[_NORelocationNode, int] = {}
    for start, _destination in legs:
        if state.get(start) is not None:
            continue
        chain: list[_NORelocationNode] = []
        node: Optional[_NORelocationNode] = start
        while node is not None and state.get(node) is None:
            state[node] = 0
            chain.append(node)
            node = by_source.get(node)
        if node is not None and state.get(node) == 0:
            conflicted.add(_find(node))  # closed back onto the live chain
        for visited in chain:
            state[visited] = 1

    if not conflicted:
        return frozenset()
    return frozenset(
        source for source, _destination in legs if _find(source) in conflicted
    )


def no_ordering_profile() -> OrderingProfile:
    """The NO jurisdiction ordering profile fed to the unified kernel.

    Wave 0 (``notes/CORE_PIPELINE_UNIFICATION_DESIGN.md`` §3.2 / §4): NO's
    ordering is the temporal group sort ``(effective, enacted, source_id,
    sequence)`` followed by the within-group structural-vacate order
    (REPEAL-first, then topological RENUMBER vacating destinations before
    occupying them, then the rest by sequence), with same-moment cross-act
    detection delegated to the shared ``cross_act_same_moment`` detector. The
    profile encodes exactly that prior contract so ``order_ops`` reproduces the
    old group-sort + ``_ordered_renumber_group`` + direct-detector path
    byte-for-byte:

    - ``finder_kind_prefix="no"`` — the prefix the direct detector call used.
    - ``incompatible_payload_predicate=None`` — the detector's *default*
      conservative predicate (NO carries no jurisdiction-specific predicate).
    - ``temporal_key=_no_temporal_key`` — ``(effective, enacted, source_id,
      sequence)``, the old ``_group_sort_key``.
    - ``lex_posterior=False`` (implicit) — NO had no affecting-act lexical
      tiebreak; the within-group order is the structural-vacate stage.
    - no ``precedence_claims`` — NO has no validated precedence-rule registry.
    - ``renumber_vacate=True`` with ``renumber_group_key=_no_group_key`` and
      ``renumber_tiebreak_key=_no_renumber_tiebreak_key`` — the shared lift of
      NO's ``_ordered_renumber_group`` group fold (kernel §3.2 step 5).
    """
    return OrderingProfile(
        finder_kind_prefix="no",
        temporal_key=_no_temporal_key,
        renumber_vacate=True,
        renumber_group_key=_no_group_key,
        renumber_tiebreak_key=_no_renumber_tiebreak_key,
    )


# ── EV-05 execution-authorization: NO proof minting + resolver ────────────────
#
# The genuine authority for a NO state-mutating op is its AFFECTING ACT — the
# source document/act whose change-instructions (johtolause / endringslov lead)
# directed the change. NO lowers every op from a real amendment source and
# stamps that source's id onto ``op.source.statute_id`` (NO's ``source_id``: the
# act directing the change, distinct from the ``base_act:`` target it amends).
# ``_mint_no_execution_authorization`` projects that known authority into a typed
# :class:`ExecutionAuthorization` proof; the NO resolver
# (:func:`_no_execution_authorization`) prefers a proof already minted onto the
# op's carrier and otherwise mints one HERE from the op's source identity, so NO
# need not re-stamp every upstream op-construction site (byte-identity-safe). An
# op with NO affecting-act identity (``op.source`` is ``None`` / blank
# ``statute_id``) has UNKNOWN authority — no proof is fabricated, so the EV-05
# observe gate fires honestly on it (the real unauthorized residue).

#: The NO execution-authorization rule family stamped into a minted proof's
#: ``authorization_rule_id``. The actual rule_id appends the affecting act id, so
#: the proof points at the concrete authorizing act (``no_affecting_act:<statute>``).
_NO_EXECUTION_AUTHORIZATION_RULE = "no_affecting_act_authorizes_apply"


def _mint_no_execution_authorization(
    op: LegalOperation,
) -> Optional[ExecutionAuthorization]:
    """Mint a typed ``ExecutionAuthorization`` from a NO op's affecting-act identity.

    The authority a NO op carries is its source affecting act: the act whose
    change-instructions directed this change is what authorizes the apply. When
    the op carries a real ``op.source.statute_id`` (the affecting act id), that is
    a GENUINELY KNOWN authority, so we mint a replay-authorized proof whose
    ``authorization_rule_id`` names the concrete act
    (``no_affecting_act:<statute_id>``) and whose ``detail`` records the witness
    rule + scope-confidence rung (read-as-witness only — §2.10). When the op
    carries no affecting-act identity (no ``source`` / blank ``statute_id``), the
    authority is UNKNOWN: we return ``None`` and never fabricate a proof, so the
    EV-05 gate honestly witnesses that op as unauthorized.

    The proof is replay-authorized (``executable``/``replay_authorized`` both
    ``True``) because the affecting act IS the apply authority for NO's replay
    lane — NO's apply is the act executing its own directed changes. This is the
    honest NO footing, not a blanket pass: the gate still fires on every op whose
    authorizing act is not identified.
    """
    source = op.source
    statute_id = (source.statute_id if source is not None else "") or ""
    if not statute_id:
        return None
    rung = ""
    scope_confidence = op.scope_confidence
    if scope_confidence is not None:
        rung = getattr(scope_confidence, "rung_id", "") or ""
    return ExecutionAuthorization(
        executable=True,
        replay_authorized=True,
        authorization_status="replay_authorized",
        authorization_rule_id=f"no_affecting_act:{statute_id}",
        owner_phase="apply",
        strict_disposition="record",
        quirks_disposition=QuirksDisposition.RECORD,
        safe_default="execute_only_after_affecting_act_identity_is_known",
        required_proofs=(),
        forbidden_shortcuts=("treat_op_existence_as_replay_authority_without_affecting_act",),
        detail={
            "rule_family": _NO_EXECUTION_AUTHORIZATION_RULE,
            "affecting_act": statute_id,
            "witness_rule_id": op.witness_rule_id or "",
            "scope_confidence_rung": rung,
            "owner": "norway/grafter:_mint_no_execution_authorization",
        },
    )


def _no_execution_authorization(
    op: LegalOperation,
) -> Optional[ExecutionAuthorization]:
    """NO ``authorization_resolver``: read a minted proof, else mint from source.

    Prefers an ``ExecutionAuthorization`` already minted onto the op's
    ``execution_authorization`` carrier (the generic
    ``core/apply_seam.read_op_execution_authorization`` path); if the op carries
    none, mints one from its affecting-act identity via
    :func:`_mint_no_execution_authorization`. Returns ``None`` only when the op's
    authority is genuinely unknown (no affecting act) — the honest EV-05 residue.
    """
    if op.execution_authorization is not None:
        return op.execution_authorization
    return _mint_no_execution_authorization(op)


# ── AM-01 provenance-acceptance: NO Parsed-vs-Recovered verdict ───────────────
#
# NO marks a RECOVERED (recognizer/fallback-guessed) op by carrying a typed
# ``NOScopeConfidence`` (``op.scope_confidence``) whose ``rung_id`` is an
# inferred/fallback §2.2 ladder value (AGENTS.md §2.2). A grammar-recognized
# (``Parsed``) op carries an explicit-source rung or no scope_confidence at all.
# The FI reference (``finland/op_provenance.admits``) admits only ``Parsed``
# under strict; a ``Recovered`` op is refused. NO mirrors that here WITHOUT
# importing ``finland/``: it reads its OWN typed ``op.scope_confidence`` carrier
# and computes the core-neutral ``OpAcceptance`` verdict the seam records.

#: Scope-confidence rungs that mark a RECOVERED (guessed/inferred) op — the
#: AGENTS.md §2.2 inferred/fallback ladder values. A Parsed op carries an
#: explicit rung (``explicit_source`` / ``explicit_source_with_context``) or no
#: scope_confidence carrier at all.
_NO_RECOVERED_SCOPE_CONFIDENCE_RUNGS: frozenset[str] = frozenset(
    {
        "inferred_from_group",
        "inferred_from_payload",
        "inferred_from_live_unique",
        "inferred_singleton_path",
        "fallback",
    }
)


def _no_op_provenance_acceptance(op: LegalOperation) -> Optional[OpAcceptance]:
    """NO ``provenance_resolver``: the core-neutral AM-01 acceptance verdict.

    Reads NO's OWN derivation signal — the typed ``NOScopeConfidence`` carried on
    ``op.scope_confidence`` (its ``rung_id``) — to classify the op as ``Parsed``
    (admitted) or ``Recovered`` (refused under strict), mirroring the FI reference
    (``admits``/``mode_for``: STRICT admits only ``Parsed``) without importing
    ``finland/``. A recovered op (an inferred/fallback rung) yields a NOT-admitted
    verdict under NO's ``strict`` acceptance mode → the AM-01 observe gate
    witnesses it. A parsed op (explicit rung / no scope_confidence carrier) yields
    an admitted verdict → silent. The seam merely records this decision; NO does
    not block on it (observe-first — the AM-01 block promotion is a future
    measure-then-flip step).
    """
    rung = ""
    scope_confidence = op.scope_confidence
    if scope_confidence is not None:
        rung = getattr(scope_confidence, "rung_id", "") or ""
    recovered = rung in _NO_RECOVERED_SCOPE_CONFIDENCE_RUNGS
    if recovered:
        return OpAcceptance(
            admitted=False,
            acceptance_mode="strict",
            provenance_kind="recovered",
            detail={
                "scope_confidence_rung": rung,
                "witness_rule_id": op.witness_rule_id or "",
                "owner": "norway/grafter:_no_op_provenance_acceptance",
            },
        )
    return OpAcceptance(
        admitted=True,
        acceptance_mode="strict",
        provenance_kind="parsed",
        detail={
            "scope_confidence_rung": rung,
            "owner": "norway/grafter:_no_op_provenance_acceptance",
        },
    )


@dataclass(frozen=True, slots=True)
class _NOOpApplyOutcome:
    op: LegalOperation
    landed: bool
    rejection: Optional[RejectedItem[LegalOperation]]
    write_receipt: Optional[WriteReceipt]
    observed_write_audit: Optional[ObservedWriteAudit]


@dataclass(frozen=True, slots=True)
class _NOApplyFoldResult:
    statute: IRStatute
    outcomes: tuple[_NOOpApplyOutcome, ...]


def _apply_no_ops_fold(
    statute: IRStatute,
    ops: List[LegalOperation],
    adjudications_out: Optional[List[CompileAdjudication]] = None,
    strict_invariants: bool = True,
    strict_action_family: bool = False,
    strict_recovery: bool = False,
    seam_observations_out: Optional[list[Finding]] = None,
    emit_receipts: bool = False,
) -> _NOApplyFoldResult:
    """Apply a minimal structural Norway operation set to a statute tree.

    Architectural note:
    this function still carries some target completion / structural recovery
    debt that should move upward into elaboration. Replay should converge on an
    execution-only contract over fully resolved canonical operations.
    """
    # Keep an internal ledger even when the caller does not request the legacy
    # out-parameter. Per-op conservation and rollback must not depend on whether
    # an evidence projection was supplied.
    if adjudications_out is None:
        adjudications_out = []

    # §1.7 same-moment cross-act conflict pre-pass (AGENTS.md §1.7).
    #
    # Runs BEFORE the apply fold to emit a blocking finding for incompatible
    # whole-target payloads from distinct affecting acts at the same
    # (effective_date, target) moment. The finding is ADDITIVE: apply order is
    # unchanged so non-ambiguous cases are byte-identical to the pre-detection
    # path; the finding surfaces the silent group-order pick so strict mode can
    # reject. The cross-act finding carries an empty op_id so the
    # conserved-wrapper partition (which keys per-op skips by op_id) is
    # unaffected.
    #
    # Routed through the shared module exactly as EE/UK do (B1: NO/SE wiring of
    # the §1.7 silent-last-wins risk). NO uses the shared module's *default*
    # conservative compatibility predicate (no jurisdiction-specific
    # re-implementation): NO ops carry StructuralAction enum actions, which the
    # default predicate classifies directly. NO has no validated precedence-rule
    # registry yet, so every detected conflict emits
    # ``resolution: "sequence_order_unproven"``.
    # Unified ordering kernel (Wave 0). ``order_ops`` composes the temporal
    # group sort ``(effective, enacted, source_id, sequence)``, the same-moment
    # cross-act conflict pre-pass (DELEGATED verbatim to the shared
    # ``detect_cross_act_same_moment_conflicts`` — the §1.7 finding, ADDITIVE and
    # carrying an empty op_id so the conserved-wrapper partition is unaffected),
    # and the structural-vacate stage (REPEAL-first, then topological RENUMBER
    # vacating destinations before they are occupied, then the rest by
    # sequence). The ordered op list and the findings are byte-identical to the
    # old group-sort + ``_ordered_renumber_group`` + direct-detector path —
    # proven by ``tests/test_no_order_ops_parallel_run.py``.
    ordered_result = order_ops(ops, no_ordering_profile())
    adjudications_out.extend(ordered_result.findings)

    body = statute.body
    op_outcomes: list[_NOOpApplyOutcome] = []

    # Reconstruct the per-op ``renumber_sources`` carrier the apply fold below
    # consumes: the set of RENUMBER source paths within the op's affecting-act
    # group ``(effective, enacted, source_id)``. The kernel returns a flat
    # ordered op list, so derive each group's renumber-source set once and pair
    # it with every op of that group (the old fold paired the per-group set with
    # each op of the group identically).
    _no_renumber_sources_by_group: dict[tuple[str, str, str], set[tuple[tuple[str, str], ...]]] = {}
    for op in ordered_result.ops:
        if op.action is StructuralAction.RENUMBER and op.destination is not None:
            _no_renumber_sources_by_group.setdefault(_no_group_key(op), set()).add(op.target.path)
    ordered_ops: list[tuple[LegalOperation, set[tuple[tuple[str, str], ...]]]] = [
        (op, _no_renumber_sources_by_group.get(_no_group_key(op), set())) for op in ordered_result.ops
    ]

    # ── W-69c: the generalized atomic ordering's provability verdict, decided
    # ONCE per affecting-act group, before any op runs. The kernel's
    # structural-vacate stage answers "in what order?" and can only ever answer
    # with a permutation; this answers the prior question "is there an order at
    # all?" over ``(parent_path, label)`` dependency nodes — see the block
    # comment on ``NO_REPLAY_RELOCATION_ORDER_UNPROVABLE_REFUSED``. Keyed by
    # ``(group, target path)`` so the RENUMBER branch can read its verdict off
    # the op alone, without a second per-op closure slot.
    _no_renumbers_by_group: dict[tuple[str, str, str], list[LegalOperation]] = {}
    for op in ordered_result.ops:
        if op.action is StructuralAction.RENUMBER and op.destination is not None:
            _no_renumbers_by_group.setdefault(_no_group_key(op), []).append(op)
    _no_unprovable_relocation_legs: frozenset[
        tuple[tuple[str, str, str], tuple[tuple[str, str], ...]]
    ] = frozenset(
        (group_key, target_path)
        for group_key, group_renumbers in _no_renumbers_by_group.items()
        for target_path in _no_unprovable_relocation_targets(group_renumbers)
    )

    no_replay_tree_invariant_families = CORE_REPLAY_DELTA_MINIMAL_FAMILIES

    def _resolve_invariant_parent(path: tree_ops.InvariantPath) -> Optional[IRNode]:
        """Walk ``body`` along an invariant path (root step is the body itself)."""
        node: Optional[IRNode] = body
        for kind, label in path[1:]:
            if node is None:
                return None
            node = next(
                (
                    child
                    for child in node.children
                    if _no_kind_value(child.kind) == kind and (child.label or None) == label
                ),
                None,
            )
        return node

    def _sort_order_violation_is_spurious(violation: tree_ops.TreeInvariantViolation) -> bool:
        """True if a roman sibling group is actually ordered under roman semantics.

        The context-free ``_no_sort_key`` treats a lone lowercase ``i``/``v``/``x``
        as litra, which is correct for bokstav lists but wrong inside a roman
        sub-item sequence (``i, ii, ..., v, ..., ix``). Re-check the offending
        sibling group with sibling context before flagging it.
        """
        if violation.kind != "sort_order":
            return False
        parent = _resolve_invariant_parent(violation.path)
        if parent is None:
            return False
        labels = [
            child.label
            for child in parent.children
            if _no_kind_value(child.kind) == violation.child_kind and child.label
        ]
        if not _no_sibling_group_uses_roman_single_letters(labels):
            return False
        keys = [_no_sort_key(label, roman_single_letters=True) for label in labels]
        return keys == sorted(keys)

    def _assert_no_invariant_violations(op: LegalOperation) -> None:
        all_violations = tuple(
            tree_ops.iter_tree_invariant_violations(
                body,
                sort_key=_no_sort_key,
                families=no_replay_tree_invariant_families,
            )
        )
        typed_violations = tuple(
            violation for violation in all_violations if not _sort_order_violation_is_spurious(violation)
        )
        # Witness-required-for-downgrade: a sort_order violation dropped from the
        # blocking set as "spurious" must leave an attributable witness, never
        # vanish silently. Record the downgrade (the roman-semantics re-check is
        # its justification) so a future regression in the spurious predicate is
        # auditable rather than invisible.
        spurious_downgrades = tuple(
            violation
            for violation in all_violations
            if violation.kind == "sort_order" and _sort_order_violation_is_spurious(violation)
        )
        if spurious_downgrades:
            _append_no_replay_adjudication(
                adjudications_out,
                kind="replay_tree_invariant_violation_downgraded",
                message="Norway sort_order invariant violation downgraded as spurious.",
                op=op,
                detail={
                    "action": legacy_text_action_value(op),
                    "target": str(op.target),
                    "nonblocking_reclassification_rule_id": ("no_sort_order_spurious_roman_single_letter_recheck"),
                    "reclassification_reason": (
                        "The flagged sibling group is correctly ordered under "
                        "roman-numeral semantics (i, ii, ..., v, ...); the "
                        "context-free litra sort key mis-flagged it."
                    ),
                    "downgraded_violations": tuple(violation.to_dict() for violation in spurious_downgrades),
                },
            )
        violations = tuple(violation.message for violation in typed_violations)
        if not violations:
            return
        joined = "; ".join(violations)
        _append_no_replay_adjudication(
            adjudications_out,
            kind="replay_tree_invariant_violation",
            message="Norway replay violated order/duplication invariant.",
            op=op,
            detail={
                "action": legacy_text_action_value(op),
                "target": str(op.target),
                "violations": joined,
                "invariant_violations": tuple(violation.to_dict() for violation in typed_violations),
            },
        )
        if not strict_invariants:
            return
        source_id = op.source.statute_id if op.source else ""
        raise ValueError(
            f"Norway replay invariant violation after {op.action} {op.target.path!r} "
            f"from {source_id or '<unknown>'}: {joined}"
        )

    # §2.9 per-op carrier: when a recovery lane INTENTIONALLY retargets the write
    # to a node outside the op's nominal storage boundary (e.g. a missing-target
    # REPLACE recovered by INSERT at a resolved parent / body root), the recovered
    # write parent path is appended here so the per-op mutation-boundary probe can
    # declare it as an authorized ``declared_recovery`` boundary extension. Reset
    # per op below; stays empty (and is ignored) when the probe is off.
    _no_declared_recovery_paths: list[tree_ops.Path] = []
    _no_declared_recovery_rule_ids: list[str] = []
    _no_executed_action: StructuralAction | None = None
    _no_landed_primary_path: tree_ops.Path | None = None
    _no_renumbered_paths: RenumberedTreePaths = ()
    # §2.3 receipt completeness: paths a NAMED recovery destroyed as collateral
    # of the primary write. Today the sole producer is the
    # ``(RENUMBER, dest_occupied)`` table cell — it clears the occupant standing
    # at the renumber destination, a real content write that the RENUMBER
    # receipt's (from, to) legs do not describe. Threaded to the seam as
    # ``MaterializeResult.recovery_removed_paths`` so the receipt declares it and
    # the independent observed-write audit can judge the write as an explained
    # named recovery instead of an undeclared escape. Reset per op below.
    _no_recovery_removed_paths: list[tree_ops.Path] = []

    def _record_action_family_recovery(
        *,
        kind: str,
        message: str,
        op: LegalOperation,
        detail: dict[str, str],
        recovered_path: Optional[tree_ops.Path] = None,
    ) -> None:
        nonlocal _no_executed_action
        _append_no_replay_adjudication(
            adjudications_out,
            kind=kind,
            message=message,
            op=op,
            detail=detail,
        )
        if recovered_path is not None:
            _no_declared_recovery_paths.append(tuple(recovered_path))
        rule_id = detail.get("rule_id")
        if rule_id:
            _no_declared_recovery_rule_ids.append(rule_id)
        executed_action = detail.get("executed_action")
        if executed_action:
            _no_executed_action = structural_action_from_str(
                executed_action,
                on_unknown="raise",
            )
        if not strict_action_family:
            return
        source_id = op.source.statute_id if op.source else ""
        raise ValueError(
            f"Norway replay action-family recovery {kind} after {op.action} "
            f"{op.target.path!r} from {source_id or '<unknown>'}"
        )

    def _record_lineage_recovery(
        *,
        kind: str,
        message: str,
        op: LegalOperation,
        detail: dict[str, str | bool],
    ) -> None:
        _append_no_replay_adjudication(
            adjudications_out,
            kind=kind,
            message=message,
            op=op,
            detail=detail,
        )
        rule_id = detail.get("rule_id")
        if isinstance(rule_id, str) and rule_id:
            _no_declared_recovery_rule_ids.append(rule_id)
        if not strict_recovery:
            return
        source_id = op.source.statute_id if op.source else ""
        raise ValueError(
            f"Norway replay recovery {kind} after {op.action} {op.target.path!r} from {source_id or '<unknown>'}"
        )

    def _record_structural_recovery(
        *,
        kind: str,
        message: str,
        op: LegalOperation,
        detail: dict[str, Any],
    ) -> None:
        _append_no_replay_adjudication(
            adjudications_out,
            kind=kind,
            message=message,
            op=op,
            detail=detail,
        )
        rule_id = detail.get("rule_id")
        if isinstance(rule_id, str) and rule_id:
            _no_declared_recovery_rule_ids.append(rule_id)
        if not strict_recovery:
            return
        source_id = op.source.statute_id if op.source else ""
        raise ValueError(
            f"Norway replay recovery {kind} after {op.action} {op.target.path!r} from {source_id or '<unknown>'}"
        )

    # §2.9 per-op mutation-boundary observation: the seam (``core/apply_seam
    # .apply_op``) is the UNIVERSAL always-on LS-01 observer — it runs the core
    # ``audit_op_mutation_boundary`` on every landed write and routes the witness
    # to ``AppliedOp.observations`` (``boundary_mode="off"``). The retired in-fold
    # probe is gone; ``apply_no_ops`` now DRAINS that observation into the same
    # env-gated ``no_replay_mutation_boundary_per_op_violation_observed``
    # adjudication in the seam loop below (default-off → byte-stable bench output).
    # Per-op ``renumber_sources`` carrier the materializer reads. The seam loop
    # sets it before each ``apply_op`` call (the seam materializer signature is
    # ``(state, op)``; ``renumber_sources`` travels via this closure slot rather
    # than a second argument so the universal seam interface stays op-only).
    _no_active_renumber_sources: set[tuple[tuple[str, str], ...]] = set()

    # ── W-69a: the announced FROM-term set, per (announcement group, address).
    # S6 says at most one of an announcement's pairs may fire on any one listed
    # address, and the prefix-nested pairs (``namsmannen``/``namsmannens``,
    # ``gjeldsforhandling``/``gjeldsforhandlingen``) are why that is not implied
    # by S7. The parse plane mints one op per (address × pair), so the sibling
    # pairs of one announcement at one address are exactly the ops sharing this
    # op's ``group_id`` AND its target path — recovered here, once, from the op
    # list the fold already has, rather than smuggled onto a new op carrier.
    _no_substitution_terms: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[str, ...]] = {}
    for _sub_op in ops:
        if NO_SUBSTITUTION_PROVENANCE_TAG not in _sub_op.provenance_tags:
            continue
        if _sub_op.text_patch is None:
            continue
        _sub_key = (_sub_op.group_id or "", tuple(_sub_op.target.path))
        _sub_terms = _no_substitution_terms.get(_sub_key, ())
        _sub_match = _sub_op.text_patch.selector.match_text
        if _sub_match not in _sub_terms:
            _no_substitution_terms[_sub_key] = (*_sub_terms, _sub_match)

    # ── NO materializer (Wave 1, design §3.1/§3.5). ──────────────────────────
    # The per-op tree dispatch — NO's REPLACE/INSERT/REPEAL/RENUMBER/text_replace
    # apply with its inline sentence-materialization, container-chain and
    # occupied-target recovery transforms — IS the NO :class:`Materializer`. The
    # dispatch body below is the verbatim prior inline fold body (no re-indent):
    # it mutates the closure ``body`` seeded from the seam-supplied
    # ``before_body``, and every prior ``continue`` is now a bare ``return``
    # (control-flow only; the landed/skipped signal is derived by the caller
    # from ``body is not before_body``). The closures it captures (the recovery
    # recorders,
    # ``_assert_no_invariant_violations``, ``adjudications_out``) are unchanged,
    # so NO's three strict flags still raise IN PLACE exactly as before — the
    # "strictness = profile policy" mapping (design §2.1 #3) is realized by those
    # raises propagating through ``apply_op`` to the caller.
    def _no_materialize_one(before_body: IRNode, op: LegalOperation) -> MaterializeResult[IRNode]:
        nonlocal body, _no_executed_action, _no_landed_primary_path, _no_renumbered_paths
        body = before_body
        renumber_sources = _no_active_renumber_sources
        # Reset the per-op declared-recovery carrier so a recovery retarget from a
        # prior op never leaks into this op's boundary.
        _no_declared_recovery_paths.clear()
        _no_declared_recovery_rule_ids.clear()
        _no_recovery_removed_paths.clear()
        _no_executed_action = None
        _no_landed_primary_path = None
        _no_renumbered_paths = ()

        def _record_landed_path(path: tree_ops.Path) -> None:
            nonlocal _no_landed_primary_path
            _no_landed_primary_path = tuple(path)

        def _materialize_sentence_parent_for(op: LegalOperation) -> None:
            """W-69b: read-only sentence materialization, before target resolution.

            Lifted verbatim out of the structural arm (where it sat between the
            unsupported-action guard and ``_resolve_no_path``) so BOTH arms of the
            dispatch reach it. It had to move: a ``setning/N`` ``TEXT_PATCH`` could
            not resolve at all, because the text-patch arm returns before the
            structural arm's materialization ever runs — which is why W-69a refused
            every sentence-addressed substitution rather than half-serving it.

            READ-ONLY means read-only on CONTENT, not on shape. The parent ledd goes
            from text-carrying to children-carrying, and that shape change is exactly
            what makes the address resolvable — but no byte of the provision's text is
            added, dropped or rewritten: :func:`_split_no_sentences` partitions
            ``_normalize_space(parent.text)`` at sentence boundaries, so space-joining
            the sentence children reproduces the former ledd text exactly. The
            tripwire that holds this is
            ``test_no_w69b_text_patch_path_materialization_conserves_text``.

            Emits the SHIPPED ``no_replay_sentence_children_materialized`` receipt: the
            mechanism is unchanged, only its reachability is, so a new receipt kind
            here would name a distinction that does not exist.
            """
            nonlocal body
            if op.target.leaf_kind() != "sentence" or op.target.parent() is None:
                return
            parent_path = _resolve_no_path(body, cast(LegalAddress, op.target.parent()))
            if parent_path is None:
                return
            body, materialized_count = _materialize_no_sentence_children_with_count(body, parent_path)
            if not materialized_count:
                return
            _record_structural_recovery(
                kind="no_replay_sentence_children_materialized",
                message=(
                    "Norway replay materialized sentence children from parent text "
                    "before applying a sentence-level operation."
                ),
                op=op,
                detail={
                    "rule_id": "no_sentence_text_materialized_for_sentence_target",
                    "family": "ontology_normalization",
                    "target": str(op.target),
                    "materialized_parent_path": _no_path_label(parent_path),
                    "materialized_sentence_count": materialized_count,
                },
            )

        def _dispatch() -> None:
            """Run one op's tree dispatch (mutating the closure ``body``).

            Verbatim lift of the prior inline per-op fold body. Each prior
            ``continue`` (a skip / early-applied path) is now a bare ``return``,
            and the natural fall-through end (a REPLACE/REPEAL/INSERT/RENUMBER
            landed) also ``return``s. Whether the op landed a write is derived by
            the caller from ``body is not before_body`` (the persistent-CoW
            identity test) — so the dispatch itself needs no return value; the
            ``continue`` → ``return`` rewrite is purely control-flow, leaving the
            mutation semantics byte-identical.
            """
            nonlocal body, _no_renumbered_paths
            if legacy_text_action_value(op) == "text_replace":
                patch = op.text_patch
                if patch is None:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unsupported_action",
                        message="Norway replay skipped text_replace without structured text_patch.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                text_match = patch.selector.match_text
                text_replacement = patch.replacement if patch.replacement is not None else ""
                if not text_match or text_replacement is None:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unsupported_action",
                        message="Norway replay skipped text_replace without match/replacement.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                if not op.target.path:
                    body = _apply_no_text_replace(body, text_match, text_replacement)
                    _record_landed_path(())
                    _assert_no_invariant_violations(op)
                    return
                # W-69b: a ``setning/N`` TEXT_PATCH resolves only after its parent
                # ledd's text has been split into sentence children. The call is a
                # no-op for every other target shape (and for a ledd that already
                # carries sentence children), which is why it can sit unconditionally
                # ahead of the resolve rather than behind a substitution-only guard:
                # the population it newly serves is bounded by what the parse plane
                # mints, and at the base pin NO text_replace op targeted a sentence
                # leaf at all — W-69a refused every one of them.
                _materialize_sentence_parent_for(op)
                resolved_path = _resolve_no_path(body, op.target)
                if resolved_path is None:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unresolved_target",
                        message="Norway replay skipped text_replace: target not found.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                node = tree_ops.resolve(body, resolved_path)
                if node is None:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unresolved_target",
                        message="Norway replay skipped text_replace: target not found.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                if NO_SUBSTITUTION_PROVENANCE_TAG in op.provenance_tags:
                    # W-69a S6 + S7. The addressed node's text is only in hand
                    # HERE, so this is where the announced term has to prove
                    # itself: exactly one of the announcement's FROM terms
                    # present, occurring exactly once, as a whole word, and not
                    # also inside a longer word. Anything else refuses and writes
                    # nothing. Letting a term-absent op fall through to the θ
                    # content-identical ``replay_noop`` cell would conserve the
                    # partition but throw the REASON away, and two of the reasons
                    # (``substring_only``, ``multiple``) are not no-ops at all —
                    # the shipped ``_apply_no_text_replace`` would write, wrongly.
                    refusal = _no_substitution_term_refusal_reason(
                        node,
                        text_match,
                        _no_substitution_terms.get(
                            (op.group_id or "", tuple(op.target.path)), (text_match,)
                        ),
                    )
                    if refusal is not None:
                        reason, counts = refusal
                        _append_no_replay_adjudication(
                            adjudications_out,
                            kind=NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT,
                            message=(
                                "Norway replay refused an addressed word substitution: the "
                                "announced term is not uniquely present as a whole word in "
                                "the addressed provision."
                            ),
                            op=op,
                            detail={
                                "rule_id": NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT,
                                "family": "unsupported_or_unresolved_action",
                                "reason": reason,
                                "target": str(op.target),
                                "match_text": text_match,
                                "replacement": text_replacement,
                                "announced_terms": list(
                                    _no_substitution_terms.get(
                                        (op.group_id or "", tuple(op.target.path)), (text_match,)
                                    )
                                ),
                                **counts,
                            },
                        )
                        _assert_no_invariant_violations(op)
                        return
                body = tree_ops.replace_at(
                    body,
                    resolved_path,
                    _apply_no_text_replace(node, text_match, text_replacement),
                )
                _record_landed_path(resolved_path)
                _assert_no_invariant_violations(op)
                return
            if not op.target.path:
                _append_no_replay_adjudication(
                    adjudications_out,
                    kind="replay_noop",
                    message="Norway replay skipped operation with missing target path.",
                    op=op,
                    detail={"action": legacy_text_action_value(op)},
                )
                _assert_no_invariant_violations(op)
                return
            if op.action not in {
                StructuralAction.REPLACE,
                StructuralAction.REPEAL,
                StructuralAction.INSERT,
                StructuralAction.RENUMBER,
            }:
                _append_no_replay_adjudication(
                    adjudications_out,
                    kind="replay_unsupported_action",
                    message="Norway replay skipped unsupported action.",
                    op=op,
                    detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                )
                _assert_no_invariant_violations(op)
                return
            _materialize_sentence_parent_for(op)
            resolved_path = _resolve_no_path(body, op.target)
            if (
                resolved_path is None
                and op.target.leaf_kind() == "sentence"
                and op.target.leaf_label() == "last"
                and op.target.parent() is not None
            ):
                parent_path = _resolve_no_path(body, cast(LegalAddress, op.target.parent()))
                if parent_path is not None:
                    resolved_path = _resolve_no_last_child_path(body, parent_path, "sentence")
            if resolved_path is None and op.target.leaf_kind() == "sentence":
                body, resolved_path, shallow_host_path, materialized_count = _resolve_shallow_no_sentence_path(
                    body,
                    op.target,
                )
                if shallow_host_path is not None and materialized_count:
                    _record_structural_recovery(
                        kind="no_replay_sentence_children_materialized",
                        message=(
                            "Norway replay materialized sentence children from a unique shallow "
                            "sentence host before applying a sentence-level operation."
                        ),
                        op=op,
                        detail={
                            "rule_id": "no_sentence_text_materialized_for_shallow_sentence_target",
                            "family": "ontology_normalization",
                            "target": str(op.target),
                            "materialized_parent_path": _no_path_label(shallow_host_path),
                            "materialized_sentence_count": materialized_count,
                        },
                    )
                if resolved_path is not None and shallow_host_path is not None:
                    _record_structural_recovery(
                        kind="no_replay_shallow_sentence_target_rebound",
                        message=(
                            "Norway replay resolved a section-level sentence target through "
                            "the section's unique direct sentence host."
                        ),
                        op=op,
                        detail={
                            "rule_id": "no_shallow_sentence_target_rebound_to_unique_host",
                            "family": "target_resolution_recovery",
                            "target": str(op.target),
                            "resolved_path": _no_path_label(resolved_path),
                            "host_path": _no_path_label(shallow_host_path),
                        },
                    )

            if op.action is StructuralAction.REPLACE and op.payload is not None:
                payload = op.payload
                if resolved_path is not None and _no_kind_value(payload.kind) == "sentence" and payload.label == "last":
                    resolved_node = tree_ops.resolve(body, resolved_path)
                    if resolved_node is not None and resolved_node.label:
                        payload = _with_no_node_label(payload, resolved_node.label)
                if resolved_path is None:
                    if (
                        op.target.leaf_kind() == "sentence"
                        and _no_kind_value(payload.kind) == "sentence"
                        and op.target.parent() is not None
                    ):
                        target_parent = cast(LegalAddress, op.target.parent())
                        resolved_parent = _resolve_no_path(body, target_parent)
                        if (
                            resolved_parent is not None
                            and _find_direct_child_path(
                                body,
                                resolved_parent,
                                "sentence",
                                op.payload.label,
                            )
                            is None
                            and _appendable_no_sentence_target(
                                body,
                                resolved_parent,
                                op.target.leaf_label(),
                            )
                        ):
                            _record_action_family_recovery(
                                kind="no_replay_replace_recovered_by_insert",
                                message="Norway replay recovered missing-target replace by inserting a sentence.",
                                op=op,
                                detail={
                                    "rule_id": "no_replace_missing_sentence_append_to_resolved_parent",
                                    "original_action": "replace",
                                    "executed_action": "insert",
                                    "target": str(op.target),
                                    "insert_parent_path": _no_path_label(resolved_parent),
                                    **_no_replay_payload_detail(payload),
                                },
                                recovered_path=resolved_parent,
                            )
                            body = tree_ops.insert_sorted(
                                body,
                                resolved_parent,
                                payload,
                                sort_key_fn=_no_sort_key,
                            )
                            _record_landed_path(
                                resolved_parent
                                + ((_no_kind_value(payload.kind), payload.label or ""),)
                            )
                            _assert_no_invariant_violations(op)
                            return
                    if op.target.leaf_kind() == "sentence" and _no_kind_value(payload.kind) == "sentence":
                        body, shallow_host_path, materialized_count = _resolve_shallow_no_sentence_host_path(
                            body, op.target
                        )
                        if shallow_host_path is not None and materialized_count:
                            _record_structural_recovery(
                                kind="no_replay_sentence_children_materialized",
                                message=(
                                    "Norway replay materialized sentence children from a unique shallow "
                                    "sentence host before recovering replace as insert."
                                ),
                                op=op,
                                detail={
                                    "rule_id": "no_sentence_text_materialized_for_shallow_sentence_target",
                                    "family": "ontology_normalization",
                                    "target": str(op.target),
                                    "materialized_parent_path": _no_path_label(shallow_host_path),
                                    "materialized_sentence_count": materialized_count,
                                },
                            )
                        if shallow_host_path is not None:
                            _record_structural_recovery(
                                kind="no_replay_shallow_sentence_target_rebound",
                                message=(
                                    "Norway replay resolved a section-level sentence target through "
                                    "the section's unique direct sentence host."
                                ),
                                op=op,
                                detail={
                                    "rule_id": "no_shallow_sentence_target_rebound_to_unique_host",
                                    "family": "target_resolution_recovery",
                                    "target": str(op.target),
                                    "host_path": _no_path_label(shallow_host_path),
                                },
                            )
                        if (
                            shallow_host_path is not None
                            and _find_direct_child_path(
                                body,
                                shallow_host_path,
                                "sentence",
                                op.payload.label,
                            )
                            is None
                            and _appendable_no_sentence_target(
                                body,
                                shallow_host_path,
                                op.target.leaf_label(),
                            )
                        ):
                            _record_action_family_recovery(
                                kind="no_replay_replace_recovered_by_insert",
                                message="Norway replay recovered missing-target replace by inserting a sentence.",
                                op=op,
                                detail={
                                    "rule_id": "no_replace_missing_sentence_append_to_shallow_host",
                                    "original_action": "replace",
                                    "executed_action": "insert",
                                    "target": str(op.target),
                                    "insert_parent_path": _no_path_label(shallow_host_path),
                                    **_no_replay_payload_detail(payload),
                                },
                                recovered_path=shallow_host_path,
                            )
                            body = tree_ops.insert_sorted(
                                body,
                                shallow_host_path,
                                payload,
                                sort_key_fn=_no_sort_key,
                            )
                            _record_landed_path(
                                shallow_host_path
                                + ((_no_kind_value(payload.kind), payload.label or ""),)
                            )
                            _assert_no_invariant_violations(op)
                            return
                    if (
                        op.target.leaf_kind() == "item"
                        and _no_kind_value(payload.kind) == "item"
                        and payload.label == "last"
                        and op.target.parent() is not None
                    ):
                        target_parent = cast(LegalAddress, op.target.parent())
                        resolved_parent = _resolve_no_path(body, target_parent)
                        if resolved_parent is not None:
                            append_payload = _appendable_no_item_payload(body, resolved_parent, payload)
                            if (
                                _find_direct_child_path(
                                    body,
                                    resolved_parent,
                                    "item",
                                    append_payload.label,
                                )
                                is None
                            ):
                                _record_action_family_recovery(
                                    kind="no_replay_replace_recovered_by_insert",
                                    message="Norway replay recovered missing-target replace by inserting an item.",
                                    op=op,
                                    detail={
                                        "rule_id": "no_replace_missing_last_item_append_to_parent",
                                        "original_action": "replace",
                                        "executed_action": "insert",
                                        "target": str(op.target),
                                        "insert_parent_path": _no_path_label(resolved_parent),
                                        **_no_replay_payload_detail(append_payload),
                                    },
                                    recovered_path=resolved_parent,
                                )
                                body = tree_ops.insert_sorted(
                                    body,
                                    resolved_parent,
                                    append_payload,
                                    sort_key_fn=_no_sort_key,
                                )
                                _record_landed_path(
                                    resolved_parent
                                    + ((
                                        _no_kind_value(append_payload.kind),
                                        append_payload.label or "",
                                    ),)
                                )
                                _assert_no_invariant_violations(op)
                                return
                    if _no_kind_value(payload.kind) == "section" and op.target.leaf_kind() == "section":
                        parent_path: tree_ops.Path = ()
                        if op.target.parent() is not None:
                            target_parent = cast(LegalAddress, op.target.parent())
                            resolved_parent = _resolve_no_path(body, target_parent)
                            if resolved_parent is not None:
                                parent_path = resolved_parent
                            else:
                                prefix_path, matched = _resolve_existing_prefix(body, target_parent)
                                if prefix_path is None and matched == 0:
                                    _append_no_replay_adjudication(
                                        adjudications_out,
                                        kind="replay_unresolved_target",
                                        message="Norway replay skipped operation: parent not found.",
                                        op=op,
                                        detail={
                                            "action": legacy_text_action_value(op),
                                            "target": str(op.target),
                                            "target_parent": str(target_parent),
                                        },
                                    )
                                    _assert_no_invariant_violations(op)
                                    return
                                body, parent_path = _ensure_no_container_chain(
                                    body,
                                    prefix_path or (),
                                    target_parent.path[matched:],
                                )
                        elif payload.label:
                            inferred_section_parent = _infer_section_parent_path(
                                body,
                                payload.label,
                            )
                            if inferred_section_parent is not None:
                                parent_path = inferred_section_parent
                        # θ: (REPLACE, target_absent) — the table declares NO
                        # recovers a missing-target section REPLACE by rewriting
                        # to INSERT (§2.3). The recovery rule_id + the rewritten
                        # action come from the table cell.
                        disposition = NO_TOTALIZATION_TABLE.lookup(StructuralAction.REPLACE, FailureClass.TARGET_ABSENT)
                        assert isinstance(disposition, Recover)
                        _record_action_family_recovery(
                            kind="no_replay_replace_recovered_by_insert",
                            message="Norway replay recovered missing-target replace by inserting a section.",
                            op=op,
                            detail={
                                "rule_id": disposition.rule_id,
                                "original_action": legacy_text_action_value(op),
                                "executed_action": _no_action_value(disposition.rewritten_action),
                                "target": str(op.target),
                                "insert_parent_path": _no_path_label(parent_path),
                                **_no_replay_payload_detail(payload),
                            },
                            recovered_path=parent_path,
                        )
                        body = tree_ops.insert_sorted(
                            body,
                            parent_path,
                            payload,
                            sort_key_fn=_no_sort_key,
                        )
                        _record_landed_path(
                            parent_path
                            + ((_no_kind_value(payload.kind), payload.label or ""),)
                        )
                        _assert_no_invariant_violations(op)
                        return
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unresolved_target",
                        message="Norway replay skipped operation: target not found.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return

                existing = tree_ops.resolve(body, resolved_path)
                # W-98 (g). THE OVER-REPEAL GUARD on a whole-chapter re-enactment.
                # "Kapittel N skal lyde:" states the chapter's new text, and a
                # section the payload does not carry would be destroyed by the
                # replace below. Whether that destruction is what the act says
                # or an artefact of the payload (the W-91 witness for chapter 6
                # is an OCR segmentation that fused §§ 6-2–6-5 into § 6-1's
                # body) is not decidable from the op, so the production refuses
                # to decide: it applies only when every section standing under
                # the chapter is carried by the payload, and otherwise lands
                # NOTHING with a typed receipt naming the uncarried labels.
                # Over-retention is the safe wrong; a whole-chapter destruction
                # on an incomplete payload is the forbidden one.
                if existing is not None and NO_CHAPTER_REENACTMENT_PROVENANCE_TAG in (op.provenance_tags or ()):
                    standing_labels = _no_descendant_section_label_keys(existing)
                    carried_labels = {
                        _normalize_no_section_label(child.label or "").casefold()
                        for child in payload.children
                        if _no_kind_value(child.kind) == "section" and child.label
                    }
                    uncarried = sorted(standing_labels - carried_labels, key=_no_sort_key)
                    if uncarried:
                        _append_no_replay_adjudication(
                            adjudications_out,
                            kind=NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED,
                            message=(
                                "Norway replay refused a whole-chapter re-enactment whose payload "
                                "does not carry every section standing under the chapter; nothing landed."
                            ),
                            op=op,
                            detail={
                                "rule_id": NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED,
                                "family": "unsupported_or_unresolved_action",
                                "target": str(op.target),
                                "resolved_path": _no_path_label(resolved_path),
                                "standing_sections": tuple(sorted(standing_labels, key=_no_sort_key)),
                                "carried_sections": tuple(sorted(carried_labels, key=_no_sort_key)),
                                "uncarried_sections": tuple(uncarried),
                            },
                        )
                        _assert_no_invariant_violations(op)
                        return
                # The heading-only merge, generalized from ``section`` to every
                # container kind that carries a heading (W-98 (f)): a payload
                # that is exactly one HEADING over an existing node of the same
                # kind replaces that node's heading and keeps its body. For a
                # section this is byte-identical to the shipped branch; for a
                # chapter it is what stops a heading announcement from wiping
                # the chapter's sections (the structured W-82 chapter-heading
                # payloads reached the bare replace below before this).
                if (
                    existing is not None
                    and _no_kind_value(existing.kind) in _NO_HEADING_ONLY_MERGE_KINDS
                    and _no_kind_value(op.payload.kind) == _no_kind_value(existing.kind)
                    and not op.payload.text
                    and len(op.payload.children) == 1
                    and _no_kind_value(op.payload.children[0].kind) == "heading"
                ):
                    merged_children = [op.payload.children[0]]
                    merged_children.extend(
                        child for child in existing.children if _no_kind_value(child.kind) != "heading"
                    )
                    body = tree_ops.replace_at(
                        body,
                        resolved_path,
                        IRNode(
                            kind=existing.kind,
                            label=existing.label,
                            text=existing.text,
                            attrs=dict(existing.attrs),
                            children=tuple(merged_children),
                        ),
                    )
                    _record_landed_path(resolved_path)
                    _assert_no_invariant_violations(op)
                    return
                body = tree_ops.replace_at(body, resolved_path, payload)
                _record_landed_path(resolved_path)

            elif op.action is StructuralAction.REPEAL:
                if resolved_path is None:
                    # θ: (REPEAL, target_absent) — the table is the source of the
                    # off-domain disposition (§2.3). NO declares this a strict
                    # Reject; the grafter reads the code from the table cell.
                    disposition = NO_TOTALIZATION_TABLE.lookup(StructuralAction.REPEAL, FailureClass.TARGET_ABSENT)
                    assert isinstance(disposition, Reject)
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind=disposition.code,
                        message="Norway replay skipped operation: target not found.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                body = tree_ops.remove_at(body, resolved_path)
                _record_landed_path(resolved_path)

            elif op.action is StructuralAction.INSERT and op.payload is not None:
                payload = op.payload
                # W-77, and it is the reason the item-depth payload production
                # can be shipped at all. It sits BEFORE the θ cell below, and
                # the placement is the whole point.
                #
                # θ ``(INSERT, target_occupied)`` recovers by REPLACING the
                # occupant, which is right for the surface §2.3 documents: a
                # "ny § 4 a skal lyde" whose slot the archived edition already
                # carries, where the replacement is content-identical or a
                # later revision of the same provision. It is NOT right for an
                # item-depth newness payload. That announcement is half of a
                # two-part instruction whose other half VACATES the label; if
                # the label is standing when this op runs, the vacate did not
                # happen — either because the relabel declined at the parse
                # plane, or because the archived base edition already carries
                # this amendment and the replay is landing it a second time. In
                # neither reading is the occupant's in-force text the thing to
                # delete. W-66 measured exactly that failure at the ledd depth
                # (straffeloven 2005 § 3 femte ledd, verdipapirhandelloven
                # § 9-21 fjerde ledd) and it is W-54's ``removal_wrong``.
                #
                # So this production does not take the recovery: it refuses,
                # with a typed receipt and no write. Under-applying leaves the
                # new item missing, which is a divergence row; over-applying
                # destroys law that is in force. The guard is gated on the
                # production's own provenance tag, so the shipped θ cell is
                # UNTOUCHED for every op that is not this production's and the
                # corpus-wide firing census cannot move.
                # W-98 generalizes the KEY, not the branch: the tag→kind table
                # keeps W-77's kind byte-for-byte for W-77's tag and gives the
                # two re-enactment productions (a ledd repeal-then-reenact, a
                # ``Nytt kapittel``) one generic kind, told apart by
                # ``production``. Still one branch on the load-bearing seam.
                refusing_tag = next(
                    (tag for tag in (op.provenance_tags or ()) if tag in _NO_INSERT_OCCUPIED_REFUSING_TAGS),
                    None,
                )
                if resolved_path is not None and refusing_tag is not None:
                    refusing_kind = _NO_INSERT_OCCUPIED_REFUSING_TAGS[refusing_tag]
                    standing = tree_ops.resolve(body, resolved_path)
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind=refusing_kind,
                        message=(
                            "Norway replay refused an item-depth newness payload whose target "
                            "label is still occupied when the insert runs."
                            if refusing_tag == NO_ITEM_INSERT_PAYLOAD_PROVENANCE_TAG
                            else "Norway replay refused a re-enactment insert whose target label "
                            "is still occupied when the insert runs."
                        ),
                        op=op,
                        detail={
                            "rule_id": refusing_kind,
                            "production": refusing_tag,
                            "family": "unsupported_or_unresolved_action",
                            "target": str(op.target),
                            "resolved_path": _no_path_label(resolved_path),
                            "occupant_kind": _no_kind_value(standing.kind) if standing is not None else "",
                            "occupant_label": (standing.label or "") if standing is not None else "",
                            **_no_replay_payload_detail(payload),
                        },
                    )
                    _assert_no_invariant_violations(op)
                    return
                if resolved_path is not None:
                    # θ: (INSERT, target_occupied) — the table declares NO
                    # recovers by rewriting to REPLACE (§2.3). The rule_id the
                    # WriteReceipt/adjudication cites comes from the table cell.
                    disposition = NO_TOTALIZATION_TABLE.lookup(StructuralAction.INSERT, FailureClass.TARGET_OCCUPIED)
                    assert isinstance(disposition, Recover)
                    _record_action_family_recovery(
                        kind="no_replay_insert_occupied_target_replaced",
                        message="Norway replay recovered insert into an occupied target by replacing that target.",
                        op=op,
                        detail={
                            "rule_id": disposition.rule_id,
                            "original_action": "insert",
                            "executed_action": _no_action_value(disposition.rewritten_action),
                            "target": str(op.target),
                            "resolved_path": _no_path_label(resolved_path),
                            **_no_replay_payload_detail(payload),
                        },
                    )
                    body = tree_ops.replace_at(body, resolved_path, payload)
                    _record_landed_path(resolved_path)
                    _assert_no_invariant_violations(op)
                    return
                parent_path: tree_ops.Path = ()
                if op.target.parent() is not None:
                    target_parent = cast(LegalAddress, op.target.parent())
                    resolved_parent = _resolve_no_path(body, target_parent)
                    if resolved_parent is not None:
                        parent_path = resolved_parent
                    else:
                        prefix_path, matched = _resolve_existing_prefix(body, target_parent)
                        if prefix_path is None and matched == 0:
                            _append_no_replay_adjudication(
                                adjudications_out,
                                kind="replay_unresolved_target",
                                message="Norway replay skipped operation: parent not found.",
                                op=op,
                                detail={
                                    "action": legacy_text_action_value(op),
                                    "target": str(op.target),
                                    "target_parent": str(target_parent),
                                },
                            )
                            _assert_no_invariant_violations(op)
                            return
                        body, parent_path = _ensure_no_container_chain(
                            body,
                            prefix_path or (),
                            target_parent.path[matched:],
                        )
                elif _no_kind_value(payload.kind) == "section" and payload.label:
                    inferred_section_parent = _infer_section_parent_path(body, payload.label)
                    if inferred_section_parent is not None:
                        parent_path = inferred_section_parent
                parent_node = tree_ops.resolve(body, parent_path) if parent_path else body
                if parent_node is not None and _no_kind_value(payload.kind) == "item" and payload.label == "last":
                    payload = _with_no_node_label(payload, _next_no_child_label(parent_node, "item"))
                if parent_node is not None:
                    inferred = _find_insert_parent(parent_node, str(payload.kind))
                    if inferred is not None:
                        parent_path = parent_path + inferred
                direct_existing_path = _find_direct_child_path(
                    body,
                    parent_path,
                    str(payload.kind),
                    payload.label,
                )
                if direct_existing_path is not None:
                    # W-63 POLARITY: REFUSE, do not overwrite.
                    #
                    # This lane is reached ONLY when the op's own target address
                    # did NOT resolve (``resolved_path is None``) and the
                    # payload's ``(kind, label)`` nevertheless collides with a
                    # direct child of a parent this code INFERRED. The write it
                    # used to perform therefore landed at an address the
                    # amendment never named, chosen by label match — destroying
                    # the occupant's in-force text while the commanded address
                    # stayed empty. That is not a source-noise recovery; it is a
                    # wrong-slot signature.
                    #
                    # Distinguish it from its declared sibling
                    # ``no_replay_insert_occupied_target_replaced``
                    # (θ ``(INSERT, target_occupied)``, 194 firings over 73 laws
                    # in the 2026-07-10 corpus), which fires when the op's OWN
                    # address resolves — the Lovdata "ny § 4 a skal lyde" over an
                    # existing slot that §2.3 documents. That cell keeps its
                    # RECOVER polarity and is untouched.
                    #
                    # Census at W-63's base (all 782 base laws, apply fold run
                    # NON-STRICT so a firing hidden behind an earlier raise is
                    # still counted): ZERO firings of this cell. Its only two
                    # observed firings are counterfactual — W-54's ``refuse``
                    # policy A/B (overwrote tvisteloven § 24-8's third ledd) and
                    # W-60's ``D4_m3`` mutant (overwrote havenergilova § 10-9's
                    # fourth ledd with content-identical text, so the destruction
                    # was invisible to the divergence plane and visible only in
                    # this receipt). Refusal costs zero corpus movement today and
                    # converts a silent destructive write into a typed blocking
                    # refusal the acceptance lane must adjudicate.
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="no_replay_insert_occupied_direct_child_refused",
                        message=(
                            "Norway replay refused an insert whose unresolved target would have "
                            "overwritten an occupied direct child at an address the operation "
                            "never named."
                        ),
                        op=op,
                        detail={
                            "rule_id": "no_insert_occupied_direct_child_refuse",
                            "family": "unsupported_or_unresolved_action",
                            "action": legacy_text_action_value(op),
                            "original_action": "insert",
                            "executed_action": "none",
                            "target": str(op.target),
                            "parent_path": _no_path_label(parent_path),
                            "occupied_child_path": _no_path_label(direct_existing_path),
                            **_no_replay_payload_detail(payload),
                        },
                    )
                    _assert_no_invariant_violations(op)
                    return
                body = tree_ops.insert_sorted(
                    body,
                    parent_path,
                    payload,
                    sort_key_fn=_no_sort_key,
                )
                _record_landed_path(
                    parent_path + ((_no_kind_value(payload.kind), payload.label or ""),)
                )

            elif op.action is StructuralAction.RENUMBER and op.destination is not None:
                # W-69c. FIRST in the branch, ahead of target resolution: the
                # verdict is a fact about the group's ADDRESSES, so refusing here
                # makes it independent of the tree and of the order the kernel
                # emitted — the property that lets "the component drops whole"
                # be proven rather than observed. A leg that also fails to
                # resolve would otherwise report the accident
                # (``replay_unresolved_target``) instead of the cause.
                if (
                    _no_group_key(op),
                    op.target.path,
                ) in _no_unprovable_relocation_legs:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind=NO_REPLAY_RELOCATION_ORDER_UNPROVABLE_REFUSED,
                        message=(
                            "Norway replay refused a relocation leg whose atomic group "
                            "admits no order in which every leg avoids a live sibling."
                        ),
                        op=op,
                        detail={
                            "rule_id": NO_REPLAY_RELOCATION_ORDER_UNPROVABLE_REFUSED,
                            "family": "unsupported_or_unresolved_action",
                            "action": legacy_text_action_value(op),
                            "source_path": _no_path_label(op.target.path),
                            "destination_path": _no_path_label(op.destination.path),
                            "destination_target": _no_address_detail(op.destination),
                            "reason": (
                                "relocation component has a contested destination, a "
                                "contested source, or a cycle over (parent_path, label)"
                            ),
                        },
                    )
                    _assert_no_invariant_violations(op)
                    return
                if resolved_path is None:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unresolved_target",
                        message="Norway replay skipped operation: target not found.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                node = tree_ops.resolve(body, resolved_path)
                if node is None:
                    _append_no_replay_adjudication(
                        adjudications_out,
                        kind="replay_unresolved_target",
                        message="Norway replay skipped operation: target not found.",
                        op=op,
                        detail={"action": legacy_text_action_value(op), "target": str(op.target)},
                    )
                    _assert_no_invariant_violations(op)
                    return
                moved = node
                if op.destination.leaf_label():
                    moved = _with_no_node_label(moved, op.destination.leaf_label())
                source_parent_path = resolved_path[:-1]
                destination_path = _resolve_no_path(body, op.destination)
                # W-66, and it is the reason the sibling-set relabel can be
                # shipped at all.
                #
                # The parse plane can prove that a destination INSIDE the
                # relabel's own source set will be vacated by the same atomic
                # group. It can prove nothing about a destination OUTSIDE it:
                # whether the section really ends where the drafter's ordinals say
                # it does is a fact about the TREE, not about the sentence. Under
                # the shipped θ cell below the tree answers that question by
                # DELETING whatever is standing there, and W-66's own corpus
                # measurement caught it doing exactly that twice — straffeloven
                # 2005 § 3 femte ledd ("Ved domfellelse etter gjenåpning …", in
                # force at that very address in the published consolidation) and
                # verdipapirhandelloven § 9-21 fjerde ledd. In both, the archived
                # BASE edition already carries the amendment being replayed, so the
                # relabel lands a second time and eats a live provision. That is
                # W-54's ``removal_wrong``, and it is a stop condition.
                #
                # So this production does not take the recovery. An op it minted
                # whose destination is OCCUPIED refuses, with a typed receipt and
                # no write. Under-applying a relabel leaves the ledd sequence one
                # slot out of step, which is a divergence row; over-applying
                # destroys law that is in force.
                #
                # Note where this sits: BEFORE the ``destination in
                # renumber_sources`` exemption, not inside it, and the placement is
                # load-bearing. That exemption exists because the kernel's
                # structural-vacate stage promises to run the leg that frees a slot
                # before the leg that fills it — a promise that holds only while
                # every leg APPLIES. Once a leg may refuse, an exempted follower
                # would land on a sibling that never moved, and the tree invariant
                # catches it as a duplicate label (measured: verdipapirhandelloven
                # § 15-2, ``duplicate subsection:4``). Checking occupancy for real,
                # for every leg, is what makes the refusal CASCADE instead: the leg
                # that would free slot N runs first, and if it refuses, slot N is
                # still occupied when the leg aiming at N is evaluated, so that one
                # refuses too. The whole relabel drops together — never in halves,
                # which is the W-56 failure mode.
                #
                # The shipped θ cell is UNTOUCHED for every op that is not this
                # production's, which is why the corpus-wide firing census does not
                # move and the pinned verdict table gains no row.
                if (
                    destination_path is not None
                    and destination_path != resolved_path
                    and NO_LEDD_SET_RELABEL_PROVENANCE_TAG in (op.provenance_tags or ())
                ):
                    standing = tree_ops.resolve(body, destination_path)
                    if standing is not None:
                        _append_no_replay_adjudication(
                            adjudications_out,
                            kind=NO_REPLAY_LEDD_SET_RELABEL_OCCUPIED_DESTINATION_REFUSED,
                            message=(
                                "Norway replay refused a sibling-set ledd relabel leg whose "
                                "destination is still occupied when the leg runs."
                            ),
                            op=op,
                            detail={
                                "rule_id": NO_REPLAY_LEDD_SET_RELABEL_OCCUPIED_DESTINATION_REFUSED,
                                "family": "unsupported_or_unresolved_action",
                                "source_path": _no_path_label(resolved_path),
                                "destination_path": _no_path_label(destination_path),
                                "destination_target": _no_address_detail(op.destination),
                                "occupant_kind": _no_kind_value(standing.kind),
                                "occupant_label": standing.label or "",
                                "destination_was_renumber_source": op.destination.path in renumber_sources,
                            },
                        )
                        _assert_no_invariant_violations(op)
                        return
                if (
                    destination_path is not None
                    and destination_path != resolved_path
                    and op.destination.path not in renumber_sources
                ):
                    occupied_destination = tree_ops.resolve(body, destination_path)
                    # θ: (RENUMBER, dest_occupied) — the table declares NO
                    # recovers by removing the occupant and proceeding with the
                    # RENUMBER (§2.3). The recovery rule_id comes from the table
                    # cell (the rewritten action is RENUMBER itself).
                    disposition = NO_TOTALIZATION_TABLE.lookup(StructuralAction.RENUMBER, FailureClass.DEST_OCCUPIED)
                    assert isinstance(disposition, Recover)
                    _record_lineage_recovery(
                        kind="no_replay_renumber_occupied_destination_removed",
                        message=(
                            "Norway replay cleared an occupied renumber destination "
                            "that was not itself moved by the same renumber group."
                        ),
                        op=op,
                        detail={
                            "rule_id": disposition.rule_id,
                            "family": "migration_or_lineage_recovery",
                            "source_path": _no_path_label(resolved_path),
                            "destination_path": _no_path_label(destination_path),
                            "destination_target": _no_address_detail(op.destination),
                            "removed_kind": _no_kind_value(occupied_destination.kind)
                            if occupied_destination is not None
                            else "",
                            "removed_label": occupied_destination.label
                            if occupied_destination is not None and occupied_destination.label is not None
                            else "",
                            "destination_was_renumber_source": False,
                        },
                    )
                    body = tree_ops.remove_at(body, destination_path)
                    # Declare the occupant's removal on the receipt. Without
                    # this the write receipt described only the (from, to)
                    # renumber legs, so the occupant's subtree was destroyed
                    # under no declared path at all. That under-declaration is
                    # what the independent before/after audit reads as an
                    # ``undeclared`` escape whenever the occupant did not live
                    # under a leg's parent (the cross-chapter case); when it did,
                    # the coarse identity-pruned diff path stayed *related* to a
                    # leg and the same undeclared removal passed unseen. Both
                    # arms are now declared, so the audit judges every occupied-
                    # destination removal against the rule that authored it.
                    _no_recovery_removed_paths.append(tuple(destination_path))
                body = tree_ops.remove_at(body, resolved_path)
                destination_parent = op.destination.parent()
                if destination_parent is not None:
                    parent_path = _resolve_no_path(body, destination_parent) or ()
                else:
                    parent_path = source_parent_path
                body = tree_ops.insert_sorted(
                    body,
                    parent_path,
                    moved,
                    sort_key_fn=_no_sort_key,
                )
                landed_path = parent_path + (
                    (_no_kind_value(moved.kind), moved.label or ""),
                )
                _record_landed_path(landed_path)
                _no_renumbered_paths = ((tuple(resolved_path), landed_path),)
            _assert_no_invariant_violations(op)
            # Natural fall-through: a REPLACE/REPEAL/INSERT/RENUMBER landed.
            return

        # §2.9 per-op mutation-boundary observation: the in-fold env-probe is
        # RETIRED. The seam's always-on observer (``core/apply_seam.apply_op``)
        # runs the IDENTICAL core ``audit_op_mutation_boundary`` on the landed
        # write and routes the witness to ``AppliedOp.observations``; the seam
        # loop below drains that observation into the same env-gated
        # ``no_replay_mutation_boundary_per_op_violation_observed`` adjudication
        # (carrying these ``declared_recovery_prefixes`` via the
        # ``MaterializeResult`` below, so the recovery-aware verdict is identical).
        _dispatch()
        nominal_landed_path = (
            tuple(op.destination.path)
            if op.action is StructuralAction.RENUMBER and op.destination is not None
            else tuple(op.target.path)
        )
        if (
            emit_receipts
            and
            _no_landed_primary_path is not None
            and _no_landed_primary_path != nominal_landed_path
            and op.action is not StructuralAction.RENUMBER
            and not _no_declared_recovery_rule_ids
        ):
            rule_id = "no_receipt_storage_path_resolution"
            _append_no_replay_adjudication(
                adjudications_out,
                kind="no_replay_receipt_storage_path_projected",
                message=(
                    "Norway replay projected a chapter-free legal address to the "
                    "exact resolved IR storage path for write accounting."
                ),
                op=op,
                detail={
                    "rule_id": rule_id,
                    "family": "presentation_cleanup",
                    "bound_target_path": nominal_landed_path,
                    "landed_primary_path": _no_landed_primary_path,
                },
            )
            _no_declared_recovery_rule_ids.append(rule_id)
        applied = body is not before_body
        return MaterializeResult(
            new_state=body,
            applied=applied,
            declared_recovery_prefixes=tuple(_no_declared_recovery_paths),
            declared_recovery_rule_ids=tuple(
                dict.fromkeys(_no_declared_recovery_rule_ids)
            ),
            executed_action=_no_executed_action,
            landed_primary_path=_no_landed_primary_path,
            renumbered_paths=_no_renumbered_paths,
            recovery_removed_paths=tuple(_no_recovery_removed_paths),
        )

    # ── NO apply profile (Wave 1, design §3.1). ──────────────────────────────
    # ``boundary_mode="off"``: the seam's always-on observer is the SINGLE LS-01
    # producer; the in-fold probe is retired and the seam loop below drains the
    # observation into the env-gated ``no_replay_mutation_boundary_per_op_*``
    # adjudication, so the env-flag-ON output is byte-identical to the
    # pre-cutover fold. ``emit_receipts``/``emit_coverage`` are False in the bare
    # fold: the additive per-op receipt lane is requested by
    # ``apply_no_ops_conserved``, while the bare ``apply_no_ops`` projection stays
    # byte-identical (no new artifacts)
    # — the equality gate is confined to the materialized IRStatute +
    # adjudications. ``renumber_migration_rule_ids`` names the migration that
    # explains a RENUMBER's bound→landed relabel divergence when receipts ARE
    # requested (the additive lane).
    # ── NO EV-05 authorization resolver + AM-01 provenance resolver (this task).
    # ``authorization_resolver`` mints/reads a real ``ExecutionAuthorization``
    # proof from each op's affecting-act identity (``_no_execution_authorization``)
    # so the EV-05 observe gate goes QUIET for every op whose authorizing act is
    # known and fires only on the genuinely unauthorized residue (the firewall
    # hole drops from ~100% to the real unauthorized fraction). ``provenance_
    # resolver`` hands the seam NO's core-neutral Parsed-vs-Recovered acceptance
    # verdict (``_no_op_provenance_acceptance``), read from NO's typed
    # ``op.scope_confidence`` carrier, so the AM-01 gate measures NO's
    # Recovered-vs-Parsed op population. BOTH are OBSERVE-only: their witnesses
    # route to ``AppliedOp.observations`` (never production ``findings``), so NO's
    # materialized statute + adjudications stay byte-identical. NO is NOT flipped
    # to block on either gate — that is a future measure-then-promote step.
    no_apply_profile: ApplyProfile[IRNode] = ApplyProfile(
        jurisdiction="no",
        materializer=_no_materialize_one,
        boundary_mode="off",
        emit_receipts=emit_receipts,
        emit_coverage=False,
        receipt_audit_mode="block" if strict_invariants else "observe",
        receipt_footprint_mode="observed",
        renumber_migration_rule_ids=("no_section_renumber_relabel",),
        receipt_helper_prefix="apply_no_ops",
        authorization_resolver=_no_execution_authorization,
        provenance_resolver=_no_op_provenance_acceptance,
    )

    # ── Seam loop (design §3.1): order_ops already ran; apply each op through
    # the unified per-op kernel. The NO materializer carries the substantive
    # dispatch; the seam owns the (here-disabled) receipt/coverage outputs and
    # the boundary gate. ``_no_active_renumber_sources`` is set per op so the
    # materializer reads the right renumber-source set (the seam interface is
    # op-only). ──────────────────────────────────────────────────────────────
    for op, renumber_sources in ordered_ops:
        _no_active_renumber_sources = renumber_sources
        pre_op_body = body
        adjudication_start = len(adjudications_out)
        applied_result: AppliedOp[IRNode] = apply_op(
            body,
            op,
            provenance=op.source,
            profile=no_apply_profile,
            source_statute=statute.statute_id,
        )
        body = applied_result.new_state

        # ── I1-strong conservation: derive the applied signal from the CONTENT
        # footprint, not object identity (#186, mirroring EE #185). ────────────
        # ``applied_result.applied`` is the seam's OBJECT-IDENTITY signal — the NO
        # materializer derives it from ``body is not before_body``. NO's tree_ops
        # (``replace_at`` / ``insert_sorted``) rebuild the targeted subtree on
        # every landed REPLACE / text_replace, so a REPLACE (or text_replace)
        # whose payload equals the live text returns a FRESH-but-content-equal
        # node: object identity reports ``applied=True`` for a write that landed
        # NOTHING. The op was then counted ACCEPTED-without-write (the conserved
        # partition keys on the enumerated skip kinds, and NO's ``replay_noop`` was
        # only emitted for the missing-target-path case, never for a content-equal
        # no-op) — the exact conservation leak AGENTS.md §1.8 / the
        # universal-algebra I1 strong form ("accepted ⟺ op landed a write")
        # forbids.
        #
        # The ground-truth footprint is the identity-pruned content diff — the
        # SAME signal the authoritative receipt fold uses to decide whether a
        # write receipt exists (empty diff ⇒ no receipt ⇒ no write).
        # Object identity is a NECESSARY precondition (no fresh object ⇒ definitely
        # no write); a fresh object counts as a write ONLY when the content
        # actually differs. A genuine landed write always has a non-empty diff, so
        # this is byte-identical for every op that truly mutated; it only
        # reclassifies the false-positive content-identical no-ops, which now emit
        # ``replay_noop`` and land REJECTED in the conserved partition.
        changed = applied_result.applied and bool(diff_ir_paths_identity_pruned(pre_op_body, body))
        if applied_result.applied and not changed:
            # θ: content_identical — the op resolved and applied but landed no
            # content write. The table declares this the I1-strong NoopIdempotent
            # conservation cell (§2.3); the grafter detects content_identical (the
            # identity-pruned empty diff above) and reads the no-op code from the
            # table. NO's no-op disposition is uniform across the resolving
            # actions (REPLACE / text_replace), so the canonical REPLACE cell is
            # the source of the code.
            disposition = NO_TOTALIZATION_TABLE.lookup(StructuralAction.REPLACE, FailureClass.CONTENT_IDENTICAL)
            assert isinstance(disposition, NoopIdempotent)
            _append_no_replay_adjudication(
                adjudications_out,
                kind=disposition.code,
                message="Norway replay emitted a content-identical no-op for operation.",
                op=op,
                detail={"action": legacy_text_action_value(op), "target": str(op.target)},
            )

        per_op_adjudications = tuple(adjudications_out[adjudication_start:])
        skip_adjudication = next(
            (
                item
                for item in per_op_adjudications
                if item.op_id == op.op_id
                and item.kind in _NO_SKIP_ADJUDICATION_KINDS
            ),
            None,
        )
        rejection: Optional[RejectedItem[LegalOperation]] = None
        if skip_adjudication is not None:
            # Structural preparation performed before a later resolution failure
            # is not authorized legal state. Persistent CoW lets us discard the
            # entire tentative per-op state rather than legitimizing a partial
            # write with a receipt.
            body = pre_op_body
            changed = False
            rejection = RejectedItem(
                item=op,
                reason=skip_adjudication.message,
                reason_code=skip_adjudication.kind,
                blocking=skip_adjudication.blocking,
            )
        elif not changed:
            raise ValueError(
                "Norway apply produced neither a landed write nor a typed rejection "
                f"for op {op.op_id or '<no-id>'}"
            )

        if changed and applied_result.observed_write_audit is not None:
            audit = applied_result.observed_write_audit
            if audit.audit_status == "violation":
                _append_no_replay_adjudication(
                    adjudications_out,
                    kind="no_replay_observed_write_audit_violation",
                    message=(
                        "Norway replay blocked a landed write whose receipt did not "
                        "match the independent before/after footprint."
                    ),
                    op=op,
                    detail={
                        "rule_id": "no_observed_write_audit_must_match_receipt",
                        "family": "mutation_boundary",
                        "action": legacy_text_action_value(op),
                        "target": str(op.target),
                        "observed_changed_paths": audit.observed_changed_paths,
                        "receipt_declared_paths": audit.receipt_declared_paths,
                        "undeclared_paths": audit.undeclared_paths,
                        "unobserved_declared_paths": audit.unobserved_declared_paths,
                    },
                )
                if strict_invariants:
                    raise ValueError(
                        "Norway observed-write audit violation after "
                        f"{op.action} {op.target.path!r}"
                    )

        # ── B-enforcement (LS-01): drain the seam's OBSERVE lane. ─────────────
        # The universal apply seam runs the always-on per-op mutation-boundary
        # audit on every landed write (``boundary_mode="off"`` routes the
        # ``APPLY.MUTATION_BOUNDARY_FINDING_AT_OP`` escape witness to
        # ``AppliedOp.observations``, NEVER to ``findings`` — production output
        # stays byte-identical). When a caller asks for the observations
        # (``seam_observations_out`` provided — the corpus boundary-cleanliness
        # MEASUREMENT and the block-mode promotion decision read it), they are
        # appended verbatim. Default ``None`` is a pure no-op: production replay
        # never allocates or reads the lane, so byte-identity is unconditional.
        if seam_observations_out is not None and applied_result.observations:
            seam_observations_out.extend(applied_result.observations)

        # ── B-enforcement (LS-01 cleanup): drain the seam's boundary observation
        # into the env-gated NO adjudication (the retired in-fold probe's surface).
        # When ``LAWVM_NO_MUTATION_BOUNDARY_PER_OP=1`` and ``adjudications_out`` is
        # supplied, project the seam's ``APPLY.MUTATION_BOUNDARY_FINDING_AT_OP``
        # observation — produced by the IDENTICAL core ``audit_op_mutation_boundary``
        # the probe consumed, carrying the same ``declared_recovery_prefixes`` from
        # the ``MaterializeResult`` — into the ``no_replay_mutation_boundary_per_op_
        # violation_observed`` ``CompileAdjudication`` the in-fold probe used to emit.
        # Default (env-off or ``adjudications_out is None``) is a pure no-op →
        # byte-identical production.
        _no_drain_seam_boundary_observations(
            applied_result.observations,
            adjudications_out=adjudications_out,
            source_statute=statute.statute_id,
            op_id=op.op_id,
        )

        op_outcomes.append(
            _NOOpApplyOutcome(
                op=op,
                landed=changed,
                rejection=rejection,
                write_receipt=(applied_result.write_receipt if changed else None),
                observed_write_audit=(
                    applied_result.observed_write_audit if changed else None
                ),
            )
        )

    return _NOApplyFoldResult(
        statute=IRStatute(
            statute_id=statute.statute_id,
            title=statute.title,
            body=body,
            supplements=statute.supplements,
            metadata=dict(statute.metadata),
        ),
        outcomes=tuple(op_outcomes),
    )


def apply_no_ops(
    statute: IRStatute,
    ops: List[LegalOperation],
    adjudications_out: Optional[List[CompileAdjudication]] = None,
    strict_invariants: bool = True,
    strict_action_family: bool = False,
    strict_recovery: bool = False,
    seam_observations_out: Optional[list[Finding]] = None,
) -> IRStatute:
    """Apply Norway operations and project only the authoritative statute.

    Norway remains observation-only at the mutation boundary
    (``boundary_mode="off"``); the internal fold owns that profile setting.
    """
    return _apply_no_ops_fold(
        statute,
        ops,
        adjudications_out=adjudications_out,
        strict_invariants=strict_invariants,
        strict_action_family=strict_action_family,
        strict_recovery=strict_recovery,
        seam_observations_out=seam_observations_out,
    ).statute


# ---------------------------------------------------------------------------
# Typed apply-result carrier (AGENTS.md §1.8 — replay conservation contract).
#
# The classic ``apply_no_ops`` returns only the mutated :class:`IRStatute` and
# shuttles skipped-op evidence through an ``adjudications_out`` out-parameter.
# The AGENTS.md §1.8 contract requires the apply path to return accepted AND
# rejected carriers (``FilterResult`` shape) so a downstream consumer cannot
# silently lose track of filtered ops. ``apply_no_ops_conserved`` is the typed
# wrapper that mirrors ``apply_no_ops``'s behaviour and surfaces both lanes
# via the contract-shape FilterResult[LegalOperation]. Production routing to
# the conserved wrapper is a separate per-frontend decision (AGENTS.md §1.8);
# this wrapper is added WITHOUT touching callers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NOApplyResult:
    """Typed apply-result conservation carrier (AGENTS.md §1.8).

    Mirrors the FilterResult contract shape: every op in the input set is
    either in ``applied_ops`` (its binding landed in the output statute) or
    surfaces as a :class:`RejectedItem[LegalOperation]` witness in
    ``skipped_items`` with a ``reason`` / ``reason_code`` and ``blocking``
    disposition. The mutation footprint (the IRStatute returned by
    :func:`apply_no_ops`) is the ``statute`` field.

    The ``filter_result`` field is the canonical ``FilterResult`` projection
    of the same accepted/rejected partition, so callers that already consume
    the shared core type can reuse it without unpacking ``applied_ops`` /
    ``skipped_items`` separately.

    Recovery adjudications (the ``no_replay_*`` family — e.g.
    ``no_replay_replace_recovered_by_insert``) are emitted by the bare variant
    when an op is APPLIED via a named recovery transformation (REPLACE
    recovered to INSERT, INSERT into an occupied slot recovered to REPLACE,
    etc.), NOT when it is skipped. They are therefore intentionally NOT in
    :data:`_NO_SKIP_ADJUDICATION_KINDS`; only the genuine per-op skip kinds
    (``replay_unsupported_action`` / ``replay_unresolved_target`` /
    ``replay_noop``, plus W-63's typed refusal
    ``no_replay_insert_occupied_direct_child_refused`` — the one ``no_replay_*``
    kind that names a REFUSAL rather than a recovery) mark an op as rejected.
    The post-apply
    ``replay_tree_invariant_violation*`` records are emitted AFTER an op was
    applied (or raised in strict mode before the conserved wrapper returns),
    so they are also NOT in the skip set.

    The optional ``write_receipts`` field carries per-op landed-write receipts
    (AGENTS.md §2.3 + notes/APPLY_RESOLUTION_AND_RECEIPT_CONTRACT.md §4) when
    the conserved wrapper is invoked with ``emit_receipts=True``. Default
    ``()`` so receipt-free callers (existing tests + the cheaper apply fold)
    pay no per-op snapshot overhead. Production lanes (NO replay's
    ``replay_no_to_pit``) request receipts so the §4 mutation-boundary
    contract is auditable downstream — without this, a guard that exists but
    is unreachable from production is the §2.9 worst-case silent failure.
    Mirrors the SE precedent at ``sweden/grafter.py:3800``.
    """

    statute: IRStatute
    filter_result: "FilterResult[LegalOperation]"
    write_receipts: tuple["WriteReceipt", ...] = ()
    observed_write_audits: tuple[ObservedWriteAudit, ...] = ()

    @property
    def applied_ops(self) -> tuple["LegalOperation", ...]:
        return self.filter_result.accepted_items

    @property
    def skipped_items(self) -> tuple["RejectedItem[LegalOperation]", ...]:
        return self.filter_result.rejected_items


# Per-op skip adjudication kinds emitted by :func:`apply_no_ops`. Each is
# emitted ONLY at a per-op skip path that emits an adjudication and then
# ``continue``s (the op is NOT applied). Recovery adjudications
# (``no_replay_*``) and post-apply violation records
# (``replay_tree_invariant_violation*``) are intentionally excluded: those are
# emitted when an op WAS applied (with a recovery transformation or a
# downstream-invariant finding) rather than skipped.
#
# The single ``no_replay_*`` member is W-63's
# ``no_replay_insert_occupied_direct_child_refused``: it is Norway-namespaced
# because it is a NO-specific typed refusal with a cataloged rule id, but it
# names a REFUSAL (no write lands), so it must be in the skip set — otherwise
# the op would be counted accepted while landing nothing, which the apply fold
# rejects fail-loud ("neither a landed write nor a typed rejection").
_NO_SKIP_ADJUDICATION_KINDS = frozenset(
    {
        "replay_unsupported_action",
        "replay_unresolved_target",
        "replay_noop",
        "no_replay_insert_occupied_direct_child_refused",
        # W-66: a sibling-set relabel leg that refused rather than clear its
        # destination is a genuine per-op SKIP — nothing landed, the tentative
        # per-op state is discarded, and the conserved partition must see it as
        # rejected rather than as a recovery that applied.
        NO_REPLAY_LEDD_SET_RELABEL_OCCUPIED_DESTINATION_REFUSED,
        # W-69a: an addressed word substitution whose announced term is not
        # uniquely present in the addressed provision. Same shape: a REFUSAL, no
        # write, so the conserved partition must see it as rejected.
        #
        # The W-69 design (§4.1) states that half 2 "needs nothing here" because
        # its refusals are all parse-plane. That is not implementable: S5-S7 need
        # the addressed node's TEXT, the parse plane has no statute (replay
        # consumes parse output), and the design's own §3.2 header says so ("the
        # first four are cheap string tests on the announcement; the rest need
        # the tree"). §4.1's conclusion does not survive its own premise; the
        # refusing direction is to register the kind.
        NO_REPLAY_SUBSTITUTION_TERM_NOT_UNIQUELY_PRESENT,
        # W-69c: a relocation leg whose atomic component admits no safe order.
        # Same shape as W-66's: a REFUSAL, no write, so the conserved partition
        # must see it as rejected rather than as a recovery that applied.
        NO_REPLAY_RELOCATION_ORDER_UNPROVABLE_REFUSED,
        # W-77: an item-depth newness payload whose target label is still
        # occupied when the insert runs. Same shape as W-66's: a REFUSAL, no
        # write, so the conserved partition must see it as rejected rather than
        # as the recovery the shipped θ cell would have performed.
        NO_REPLAY_ITEM_INSERT_PAYLOAD_OCCUPIED_TARGET_REFUSED,
        # W-98: the two re-enactment refusals. Same shape as W-66's and W-77's:
        # a REFUSAL, no write, so the conserved partition sees them as rejected.
        NO_REPLAY_CHAPTER_REENACTMENT_UNCARRIED_SECTIONS_REFUSED,
        NO_REPLAY_REENACTMENT_INSERT_OCCUPIED_TARGET_REFUSED,
    }
)


def apply_no_ops_conserved(
    statute: IRStatute,
    ops: List[LegalOperation] | Tuple["LegalOperation", ...],
    *,
    adjudications_out: Optional[List[CompileAdjudication]] = None,
    strict_invariants: bool = True,
    strict_action_family: bool = False,
    strict_recovery: bool = False,
    emit_receipts: bool = False,
) -> NOApplyResult:
    """Apply a Norway op set with a typed conservation receipt (§1.8).

    Mirrors :func:`apply_no_ops` exactly (same replay semantics, same
    ``adjudications_out`` side channel — when the caller passes one, both the
    conserved typed result AND the existing descriptive adjudications are
    populated). Returns a :class:`NOApplyResult` whose ``filter_result``
    partitions every input op into accepted (its replay applied) or rejected
    (its replay skipped, with a witness adjudication carrying the reason).
    The contract is monotone: every input op ends up either accepted or
    rejected, never silently dropped.

    The partition keys on ``op_id`` (the NO bare variant emits one
    ``CompileAdjudication`` per skipped op carrying that op's ``op_id``). An
    op is rejected iff its ``op_id`` appears in a per-op SKIP adjudication
    (``replay_unsupported_action`` / ``replay_unresolved_target`` /
    ``replay_noop`` / W-63's
    ``no_replay_insert_occupied_direct_child_refused``). Other recovery
    adjudications (``no_replay_*``) and post-apply
    invariant records (``replay_tree_invariant_violation*``) do NOT mark an op
    as rejected — those are emitted when the op WAS applied (with a recovery or
    downstream violation), not when it was skipped. Empty or duplicate
    ``op_id`` values would mis-partition and are rejected with a
    ``ValueError`` rather than silently dropping or mis-bucketing an op.

    When ``emit_receipts=True`` is passed, per-op landed-write receipts
    (§2.3 + notes/APPLY_RESOLUTION_AND_RECEIPT_CONTRACT.md §4) are produced by
    the authoritative fold and surfaced on :attr:`NOApplyResult.write_receipts`.
    Each receipt records the landed
    footprint (created/replaced/removed/renumbered paths) plus pre/post
    structural subtree hashes for the covering region. Production lanes
    (NO replay's ``replay_no_to_pit``) pass ``emit_receipts=True`` so the
    §4 mutation-boundary contract is auditable downstream — without this,
    a guard that exists but is unreachable from production is the §2.9
    worst-case silent failure (the bug that previously read: conserved
    wrapper bypassed by production ``apply_no_ops`` call site). Mirrors the
    SE precedent at ``sweden/grafter.py:3811``.
    """
    ops_list = list(ops)
    # Conservation requires a robust op IDENTITY for the accepted/rejected
    # partition. The op_id string is NOT a safe identity key: it defaults to
    # "" (a SKIPPED op with an empty op_id would be filtered out of the
    # skipped set and silently land in the accepted lane — a §1.8
    # "never silently dropped" violation) and it is not guaranteed unique
    # (a duplicate/shared op_id mis-partitions both ops). Fail loud on either
    # degenerate case so the op_id-keyed partition below is provably bijective.
    op_ids = [op.op_id for op in ops_list]
    if any(not op_id for op_id in op_ids):
        empty_positions = [i for i, op_id in enumerate(op_ids) if not op_id]
        raise ValueError(
            "apply_no_ops_conserved requires every op to carry a non-empty op_id "
            "(the conservation partition keys on op_id and an empty op_id would be "
            f"silently dropped from the skipped lane). Empty op_id at positions {empty_positions}."
        )
    if len(set(op_ids)) != len(op_ids):
        counts = Counter(op_ids)
        duplicates = sorted(op_id for op_id, n in counts.items() if n > 1)
        raise ValueError(
            "apply_no_ops_conserved requires op_ids to be unique (the conservation "
            "partition keys on op_id and duplicate op_ids would mis-partition). "
            f"Duplicate op_ids: {duplicates}."
        )
    # Trust the bare-apply contract: ``apply_no_ops`` appends each per-op
    # adjudication to ``adjudications_out`` in place. Routing the caller's
    # list directly through bare apply means a mid-apply raise (the §1.10
    # fail-loud path under ``strict_action_family=True`` for the
    # NO insert-occupied-target recovery collision) preserves the recovery
    # adjudication witnesses emitted BEFORE the raise on the caller's
    # accumulator — the caller can then diagnose via the partial
    # adjudications (AGENTS.md §1.0 evidence is not silently destroyed).
    # When the caller did not pass an ``adjudications_out``, use a throwaway
    # local buffer so bare-apply's mutations stay scoped and the partition
    # below still has a source to read from.
    adjudications: List[CompileAdjudication] = adjudications_out if adjudications_out is not None else []
    fold_result = _apply_no_ops_fold(
        statute,
        ops_list,
        adjudications_out=adjudications,
        strict_invariants=strict_invariants,
        strict_action_family=strict_action_family,
        strict_recovery=strict_recovery,
        emit_receipts=emit_receipts,
    )
    outcome_by_id = {outcome.op.op_id: outcome for outcome in fold_result.outcomes}
    if set(outcome_by_id) != set(op_ids):
        raise ValueError("Norway apply outcomes do not conserve the input op-id set")
    accepted = tuple(
        op
        for op in ops_list
        if outcome_by_id[op.op_id].landed
        and outcome_by_id[op.op_id].rejection is None
    )
    rejected_list: list[RejectedItem[LegalOperation]] = []
    for op in ops_list:
        rejection = outcome_by_id[op.op_id].rejection
        if rejection is not None:
            rejected_list.append(rejection)
    rejected = tuple(rejected_list)
    # Propagation: bare apply already mutated ``adjudications_out`` in place
    # (the caller's list when one was provided) — no local-copy / clear /
    # extend round-trip needed. The previous local-copy-then-extend pattern
    # silently dropped bare-apply's partial adjudication witness when bare
    # apply raised mid-fold (the §1.0 evidence-loss failure mode that
    # ``test_replay_no_to_pit_strict_action_family_rejects_recovery``
    # surfaced — bare apply raised after emitting the recovery adjudication
    # witness, but the caller's ``adjudications_out`` stayed empty); routing
    # the caller's list directly closes that hole.
    write_receipts = tuple(
        outcome.write_receipt
        for outcome in fold_result.outcomes
        if outcome.landed and outcome.write_receipt is not None
    )
    observed_write_audits = tuple(
        outcome.observed_write_audit
        for outcome in fold_result.outcomes
        if outcome.landed and outcome.observed_write_audit is not None
    )
    if emit_receipts:
        accepted_ids = {op.op_id for op in accepted}
        receipt_ids = {receipt.op_id for receipt in write_receipts}
        audit_ids = {audit.op_id for audit in observed_write_audits}
        if accepted_ids != receipt_ids or accepted_ids != audit_ids:
            raise ValueError(
                "Norway apply accounting mismatch: accepted ops, write receipts, "
                "and observed-write audits must have identical op-id sets"
            )
    elif write_receipts or observed_write_audits:
        raise ValueError(
            "Norway apply emitted receipt evidence while emit_receipts is false"
        )
    return NOApplyResult(
        statute=fold_result.statute,
        filter_result=FilterResult(
            accepted_items=accepted,
            rejected_items=rejected,
        ),
        write_receipts=write_receipts,
        observed_write_audits=observed_write_audits,
    )


def _no_record_archive_skip(
    rejected_items: list[RejectedItem[str]] | None,
    *,
    exc: ArchiveMemberTooLarge,
) -> None:
    """Append a typed ``RejectedItem`` receipt for an oversized archive member.

    Local twin of :func:`lawvm.norway.sources._no_record_archive_skip` (kept
    local to avoid a circular top-level import between ``norway.sources`` and
    ``norway.grafter``; mirrors the precedent at
    ``us_federal/import_plaw.py:63`` and ``tools/import_zip.py:95`` whose
    ``_record_import_skip`` helpers are local-per-module too). When
    ``rejected_items`` is ``None`` the prior structured stderr receipt via
    :func:`log_archive_member_too_large` is preserved so the skip stays
    greppable (the §1.8 minimum for destructuring consumers of
    ``open_lovdata_archive`` / ``open_lovdata_amendment_archive`` whose
    ``(id, bytes)`` yield shape cannot carry a typed rejection without
    breaking unpacking). When ``rejected_items`` is a list, a typed
    ``RejectedItem(item=member_name, reason=..., reason_code=..., blocking=False)``
    is appended instead — the §1.8 contract surface upstream tooling reads.

    Per AGENTS.md §1.10 the reason embeds the offending archive_path /
    member_name / declared_size / cap_bytes so triage does not have to
    re-run extraction to identify the rejected member (the companion
    ``ArchiveMemberTooLargeDiagnostic.render_reason`` in
    ``core/archive_safety.py`` omits these — this helper layers them on at
    the §1.8 receipt surface).
    """
    if rejected_items is None:
        log_archive_member_too_large(exc)
        return
    rejected_items.append(
        RejectedItem(
            item=exc.member_name,
            reason=(
                f"archive member {exc.member_name} from "
                f"{exc.archive_path or '<archive>'} declares "
                f"{exc.declared_size} bytes (cap {exc.cap_bytes}); "
                "refusing to materialise into memory. Raise "
                "LAWVM_MAX_ARCHIVE_MEMBER_BYTES to admit it, or trim "
                "the source archive."
            ),
            reason_code=NO_ARCHIVE_MEMBER_TOO_LARGE_REASON_CODE,
            blocking=False,
        )
    )


# §1.8 typed-receipt reason_code for archive members that declare more bytes
# than ``$LAWVM_MAX_ARCHIVE_MEMBER_BYTES``. Twin of
# :data:`lawvm.norway.sources.NO_ARCHIVE_MEMBER_TOO_LARGE_REASON_CODE` — kept
# local here to avoid a circular top-level import (sources.py imports from
# grafter at module load). Both must agree byte-for-byte.
NO_ARCHIVE_MEMBER_TOO_LARGE_REASON_CODE = "no_archive_member_too_large"


def open_lovdata_archive(
    tar_bz2_path: str,
    *,
    rejected_items: list[RejectedItem[str]] | None = None,
) -> Generator[Tuple[str, bytes], None, None]:
    """Yield ``(statute_id, bytes)`` pairs from a Lovdata public tarball.

    Members declaring more bytes than ``$LAWVM_MAX_ARCHIVE_MEMBER_BYTES`` are
    skipped. When ``rejected_items`` is threaded, a typed ``RejectedItem``
    receipt (``reason_code=no_archive_member_too_large``, ``blocking=False``)
    is appended so the §1.8 conservation lane inspects the skip in the
    accumulator surface (mirrors ``us_federal/import_plaw.py:212``). When no
    sink is threaded, the prior structured stderr receipt via
    :func:`log_archive_member_too_large` is preserved so the skip stays
    greppable — the destructuring consumer protocol
    (``for sid, html_bytes in open_lovdata_archive(...)``) is preserved either
    way (pattern B sink-threading: the union ``(id, bytes) | RejectedItem``
    yield would break the unpacking at out-of-scope call sites).
    """
    with tarfile.open(tar_bz2_path, "r:bz2") as tf:
        for member in tf.getmembers():
            if not member.name.endswith(".xml"):
                continue
            statute_id = lovdata_filename_to_id(member.name)
            if statute_id is None:
                continue
            try:
                payload = safe_tar_read(tf, member, archive_path=Path(tar_bz2_path).name)
            except ArchiveMemberTooLarge as exc:
                # §1.8 typed receipt (AGENTS.md §1.8) — see
                # :func:`_no_record_archive_skip`.
                _no_record_archive_skip(rejected_items, exc=exc)
                continue
            if payload is None:
                continue
            yield statute_id, payload


def open_lovdata_amendment_archive(
    tar_bz2_path: str,
    *,
    rejected_items: list[RejectedItem[str]] | None = None,
) -> Generator[Tuple[str, bytes], None, None]:
    """Yield ``(source_id, bytes)`` pairs from a Lovtidend tarball.

    Oversized members are skipped with a typed ``RejectedItem`` receipt when
    ``rejected_items`` is threaded (AGENTS.md §1.8) — see
    :func:`open_lovdata_archive`.
    """
    with tarfile.open(tar_bz2_path, "r:bz2") as tf:
        for member in tf.getmembers():
            if not member.name.endswith(".xml"):
                continue
            source_id = lovdata_amendment_filename_to_id(member.name)
            if source_id is None:
                continue
            try:
                payload = safe_tar_read(tf, member, archive_path=Path(tar_bz2_path).name)
            except ArchiveMemberTooLarge as exc:
                # §1.8 typed receipt (AGENTS.md §1.8) — see
                # :func:`_no_record_archive_skip`.
                _no_record_archive_skip(rejected_items, exc=exc)
                continue
            if payload is None:
                continue
            yield source_id, payload
