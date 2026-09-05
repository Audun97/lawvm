"""W-100. The section- and part-scoped commencement statement reader.

Norsk Lovtidend commencement instruments (``sf`` documents titled *Delt
ikraftsetting av lov …*, *Delvis ikraftsetjing av …*, *Ikraftsetting av …*) very
often commence LESS than a whole act, and say so in one of a small number of
recurring sentence shapes:

* a section list under the act or under one of its parts —
  ``Lovens § 2-3 andre ledd, § 2-13, § 4-2, § 6-1a, § 8-5 og § 10-4 første ledd
  skal gjelde fra 1. juli 2009.`` (``no/forskrift/2009-06-19-702``);
* a whole-act or whole-part clause with a carve-out —
  ``Lov 17. juni 2005 nr. 98 om endringar i lov 4. desember 1992 nr. 127 om
  kringkasting trer i kraft frå 1. juli 2005 med unntak av nytt § 4-4 tredje
  ledd, endring i § 10-3 første og annet ledd, samt opphevinga av § 4-6.``
  (``no/forskrift/2005-06-17-631``);
* a header followed by a list of scope items —
  ``Følgende trer i kraft 1. mai 2025: Endringsloven del I (kringkastingsloven)
  med unntak av ny §§ 2-22 og 2-23. Endringsloven del II (tobakksskadeloven).``
  (``no/forskrift/2025-04-04-601``).

Measured over the 884 blocked instruments that cite an act the gate offers,
these three families cover 224 + 187 + 86 + 67 + 28 documents; before W-100 every
one of them was refused for want of a whole-act scope proof, and the acts they
date stayed ``contingent`` — seven of them in kringkastingsloven's own chain.

This module reads those sentences into typed :class:`NOCommencementScopeStatement`
values and nothing else. It resolves no law, dates no act and consults no
evidence about the act's parts or ops: that is the gate's business
(``commencement_instruments._section_scoped_authorization_scope``), which reads
the statements this module returns against the act's part map and op stream.

The safety argument is the same one every reader in this lane makes, stated
once here:

* **Totality.** The reading is all-or-nothing over the instrument's operative
  text. Every sentence must be either a statement this grammar reads end to end,
  a title echo (``Delt ikraftsetting av lov …`` with no commencement verb), or a
  list header; the first sentence that is none of these refuses the WHOLE
  reading, and the refusing sentence is recorded. A transitional provision, a
  ``får ikke anvendelse`` clause, a ``gradvis til anvendelse`` clause — anything
  the grammar does not know — therefore cannot sit beside a statement it does
  know and be skipped over. Under-reading is safe; reading past is not.
* **Closed vocabulary.** The section-list scanner, the exception opener, the
  commencement verb, the deferral phrase and the date are each a closed set of
  spellings; an unknown token CLOSES a list or refuses the sentence, never gets
  skipped.
* **Dates are cross-checked.** Every date read from prose must also appear in
  the instrument's own ``dateInForce`` field (``straks`` resolves to the
  instrument's own date, which must appear there too). A prose date the
  metadata does not carry refuses the reading.
* **Ledd-level qualifiers are recorded, never resolved.** ``§ 2-3 andre ledd``
  names a section and a subdivision of it. The reader keeps the section label
  and marks it qualified; the gate refuses to GRANT a qualified label (it cannot
  prove the act's ops on that section stay inside the named ledd) and, in a
  carve-out, excludes the whole section (which under-claims). Either way the
  ledd is never read as more than it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

_WS_RE = re.compile(r"\s+")

_MONTH_NUMBERS = {
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
_MONTHS = "|".join(_MONTH_NUMBERS)

# The commencement verb vocabulary, the same closed set
# ``commencement_instruments._COMMENCEMENT_VERB`` carries, plus the bare
# ``gjelder`` / ``gjeld`` that precede ``fra`` in the section-scoped shapes.
_VERB_RE = re.compile(
    r"(?:trer\s+i\s+kraft|trer\s+ikraft|trer\s+i\s+verk|skal\s+tre\s+i\s+kraft|tek\s+til\s+å\s+gjelde"
    r"|tar\s+til\s+å\s+gjelde|gjelder|gjeld|skal\s+gjelde"
    r"|blir\s+satt\s+i\s+kraft|blir\s+sett\s+i\s+kraft|blir\s+sette\s+i\s+kraft"
    r"|settes\s+i\s+kraft|setjast\s+i\s+kraft|setjes\s+i\s+kraft|iverksettes)\b",
    re.IGNORECASE,
)
# lawvm-regex: owning_parser this IS the prose date reader; day and month are
# separated by a mandatory single space run and the month is a closed list
# Every optional prefix in this module is spelled ``(?:word)?\s*`` rather than
# ``(?:word\s+)?``: a quantifier nested inside an optional group is what the
# classifier-safety lint refuses, and the two spellings read the same
# whitespace-collapsed text.
_DATE_RE = re.compile(
    r"(?:fra\s+og\s+med|frå\s+og\s+med|fra|frå)?\s*(\d{1,2})\.?\s+(" + _MONTHS + r")\s+(\d{4})\b",
    re.IGNORECASE,
)
_STRAKS_RE = re.compile(r"(?:fra|frå)?\s*straks\b", re.IGNORECASE)
_DEFERRED_RE = re.compile(
    r"(?:når|frå\s+den\s+tid|fra\s+den\s+tid|frå\s+det\s+tidspunktet?|fra\s+det\s+tidspunktet?)"
    r"\s+(?:Kongen|departementet)\s+(?:bestemmer|fastset|fastsetter|bestemmer\s+det)",
    re.IGNORECASE,
)
_ECHO_RE = re.compile(
    r"(?:delt|delvis|utsatt|utsett|ytterligere|ny)?\s*ikraft(?:setting|setjing|tredelse|setjinga|settinga|treding)\b",
    re.IGNORECASE,
)
_HEADER_START_RE = re.compile(
    r"(?:følgende|følgjande|desse|disse)\s+"
    r"(?:bestemmelser|bestemmelsene|føresegner|føresegnene|deler|delar|delene|endringer|endringene|endringar|endringane)?",
    re.IGNORECASE,
)
_ROMAN_RE = re.compile(r"([IVXLC]+)\b")
_ROMAN_DIGIT_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ROMAN_LABEL_STEPS = ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
# lawvm-regex: owning_parser a law citation by date and number; the only shape
# the gate can resolve to a law id without a name table
_LAW_CITE_RE = re.compile(
    r"lov(?:a|en)?\s(?:av\s)?(\d{1,2})\.?\s+(" + _MONTHS + r")\s+(\d{4})\s+nr\.?\s*(\d+)\b",
    re.IGNORECASE,
)
_ACT_WORD_RE = re.compile(
    r"(?:denne)?\s*(?:loven|lova|endringsloven|endringslova|endringslovens|lovendringene|lovendringane)\b",
    re.IGNORECASE,
)
_LAW_WORD_RE = re.compile(r"(?:lovens|lovas|loven|lova)\b", re.IGNORECASE)
_PART_RE = re.compile(
    r"(?:lovens|lovas|loven|lova|endringsloven|endringslova|endringslovens)?\s*"
    r"(?:del|delen|romertall|romartal|romartall)\s+([IVXLC]+)\b",
    re.IGNORECASE,
)
_PART_WORD_RE = re.compile(r"(?:del|delen|romertall|romartal|romartall)\s+", re.IGNORECASE)
_RANGE_DASH_RE = re.compile(r"\s*[–—-]\s*")
_COMMA_RE = re.compile(r",\s*")
_WORD_RE = re.compile(r"\S+")
_PART_NAME_RE = re.compile(r"\s*\(([^()§:]{1,160})\)")
_CHANGES_IN_RE = re.compile(
    r"(?:endring(?:en|ene|ane|a|ar|er)?|tilføy(?:elsen|inga|ingen|elsene)|opphev(?:inga|ingen|elsen|else|ing|ingane|elsene))"
    r"\s+(?:i|av)\s+",
    re.IGNORECASE,
)
_NEW_PREFIX_RE = re.compile(r"(?:nytt|ny|nye|nyt)\s+", re.IGNORECASE)
_SHORT_NAME_RE = re.compile(r"([a-zæøåA-ZÆØÅ][\w-]*(?:lov|lova|loven|lova)(?:en|a)?)\s+(?=§)")
_SECTION_OPEN_RE = re.compile(r"§§?\s*")
# lawvm-regex: owning_parser the section label: ``2-3``, ``6-1a``, ``6-1 a``,
# ``55 b``, ``418a``, ``7b``; a detached ``i`` is never a suffix (it is the
# preposition in ``§ 2-6 i forskrift``)
_LABEL_RE = re.compile(r"(\d+-\d+|\d+)(?:([a-hj-zæøå])\b|\s([a-hj-zæøå])\b)?", re.IGNORECASE)
_ORDINAL_RE = re.compile(
    r"(?:første|fyrste|andre|annet|annen|tredje|fjerde|femte|sjette|sjuende|syvende|åttende|niende"
    r"|tiende|ellevte|tolvte|siste|nytt|ny|nye)\b",
    re.IGNORECASE,
)
_QUAL_KEYWORD_RE = re.compile(
    r"(?:ledd|leddet|ledda|punktum|punkta|punktumet|nr\.?|bokstav(?:ene|ane|en)?)(?![\w-])",
    re.IGNORECASE,
)
_QUAL_VALUE_RE = re.compile(r"(?:\d+|[a-zæøå])(?![\w-])", re.IGNORECASE)
_CONJ_RE = re.compile(
    r"(?:,\s*og\s+|,\s*samt\s+|,\s*eller\s+|,\s*|\bog\s+med\s+|\bog\s+|\bsamt\s+|\beller\s+|\btil\s+)",
    re.IGNORECASE,
)
_EXC_OPEN_RE = re.compile(
    r",?\s*(?:med\s+unntak\s+av|med\s+unntak\s+for|med\s+unnatak\s+av|med\s+unnatak\s+for"
    r"|unntatt|unnateke|unnateken|bortsett\s+frå|bortsett\s+fra)\s+",
    re.IGNORECASE,
)
_SOM_RE = re.compile(r",?\s*(?:som|der)\s+", re.IGNORECASE)
_TRAILING_RE = re.compile(r"[\s.;]*$")
_LEADING_JUNK_RE = re.compile(r"^[\s.;:–—-]+")
_SENTENCE_BREAK_RE = re.compile(r"(?<=[a-zæøåA-ZÆØÅ0-9)\]»])\.\s+(?=[A-ZÆØÅ§])|:\s+(?=[A-ZÆØÅ§])")
# Abbreviations whose trailing period never ends a sentence.
_ABBREVIATIONS = frozenset(
    {"mv", "m.v", "nr", "jf", "kgl", "res", "kgl.res", "evt", "mfl", "m.fl", "pkt", "bl.a", "ca", "osv", "f.eks", "mm", "m.m", "st", "prop", "innst", "ot.prp", "kap"}
)
# Consequential blocks about a forskrift, not about the act: ``Fra samme
# tidspunkt oppheves § 2-5 og § 2-6 i forskrift 28. februar 1997 nr. 153 …``.
_FORSKRIFT_WORD_RE = re.compile(r"\bforskrift(?:a|en|er|ene|s)?\b", re.IGNORECASE)
_ACT_VOCAB_RE = re.compile(
    r"\b(?:lov|loven|lova|lovens|lovas|endringsloven|endringslova|del|delen|romertall|romartal)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NOCommencementScopeItem:
    """One scope term.

    ``kind`` is ``act`` (the cited act itself), ``part`` (one romertall part of
    it, optionally narrowed to ``section_labels``), ``sections`` (a section list
    under the act's single law, or under the law ``law_ref`` names) or ``law``
    (everything the act does to the law ``law_ref`` names).

    ``law_ref`` is either a resolved ``no/lov/<date>-<n>`` from a date-and-number
    citation, a short name the reader could not resolve (no slash — the gate may
    only accept it where the act binds exactly one law), or empty.

    Section labels are normalized to the grafter's own spelling (``§`` dropped,
    inner spaces removed, lower-cased). ``qualified_section_labels`` is the subset
    the text narrowed below section level (``andre ledd``, ``nr. 1``,
    ``bokstav c``, ``første punktum``).
    """

    kind: str
    part_label: str = ""
    law_ref: str = ""
    section_labels: tuple[str, ...] = ()
    qualified_section_labels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "part_label": self.part_label,
            "law_ref": self.law_ref,
            "section_labels": list(self.section_labels),
            "qualified_section_labels": list(self.qualified_section_labels),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NOCommencementScopeItem":
        return cls(
            kind=str(data.get("kind", "")),
            part_label=str(data.get("part_label", "")),
            law_ref=str(data.get("law_ref", "")),
            section_labels=tuple(str(x) for x in data.get("section_labels", []) or []),
            qualified_section_labels=tuple(
                str(x) for x in data.get("qualified_section_labels", []) or []
            ),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementScopeStatement:
    """``subject`` commences on ``date``, less ``excluded``.

    ``date`` is ISO; ``None`` means the text deferred it (``når Kongen
    bestemmer``), which the gate treats as an exclusion with no date. An
    exclusion that carries its own date (``… med unntak av § 13a som trer i
    kraft 1. juli 2014``) is read as BOTH an exclusion here and a separate
    statement of its own with that date.
    """

    subject: NOCommencementScopeItem
    date: str | None
    excluded: tuple[NOCommencementScopeItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject.to_dict(),
            "date": self.date,
            "excluded": [item.to_dict() for item in self.excluded],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NOCommencementScopeStatement":
        raw_date = data.get("date")
        return cls(
            subject=NOCommencementScopeItem.from_dict(dict(data.get("subject", {}) or {})),
            date=str(raw_date) if isinstance(raw_date, str) else None,
            excluded=tuple(
                NOCommencementScopeItem.from_dict(dict(item))
                for item in data.get("excluded", []) or []
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class NOCommencementScopeReading:
    """The reader's total outcome over one instrument's operative text."""

    statements: tuple[NOCommencementScopeStatement, ...] = ()
    total: bool = False
    refused_sentence: str = ""
    dates: tuple[str, ...] = ()
    forskrift_blocks_dropped: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "statements": [statement.to_dict() for statement in self.statements],
            "total": self.total,
            "refused_sentence": self.refused_sentence,
            "dates": list(self.dates),
            "forskrift_blocks_dropped": self.forskrift_blocks_dropped,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NOCommencementScopeReading":
        return cls(
            statements=tuple(
                NOCommencementScopeStatement.from_dict(dict(item))
                for item in data.get("statements", []) or []
                if isinstance(item, dict)
            ),
            total=bool(data.get("total", False)),
            refused_sentence=str(data.get("refused_sentence", "") or ""),
            dates=tuple(str(x) for x in data.get("dates", []) or []),
            forskrift_blocks_dropped=int(data.get("forskrift_blocks_dropped", 0) or 0),
        )


class _Refuse(Exception):
    """Raised inside the reader on the first sentence the grammar cannot read."""


@dataclass
class _Cursor:
    text: str
    pos: int = 0

    def rest(self) -> str:
        return self.text[self.pos :]

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def take(self, pattern: re.Pattern[str]) -> re.Match[str] | None:
        self.skip_ws()
        match = pattern.match(self.text, self.pos)
        if match is not None:
            self.pos = match.end()
        return match

    def peek(self, pattern: re.Pattern[str]) -> re.Match[str] | None:
        self.skip_ws()
        return pattern.match(self.text, self.pos)


def _normalize_section_label(number: str, letter: str | None) -> str:
    return (number + (letter or "")).lower()


@dataclass
class _Reading:
    instrument_date: str
    declared_dates: frozenset[str]
    dates_read: set[str] = field(default_factory=set)
    pending_date: str | None = None
    pending_date_set: bool = False

    def iso(self, day: str, month: str, year: str) -> str:
        return f"{year}-{_MONTH_NUMBERS[month.lower()]}-{int(day):02d}"

    def check_date(self, date: str) -> str:
        if date not in self.declared_dates:
            raise _Refuse(f"prose date {date} is not in dateInForce")
        self.dates_read.add(date)
        return date


def is_forskrift_only_block(block: str) -> bool:
    """Is this operative block about a forskrift and not about any act?

    True only when the block names a forskrift AND carries none of the act
    vocabulary (``lov``, ``loven``, ``del``, ``romertall`` …). A block that names
    both is about the act as far as this reader can tell and is kept.
    """
    return bool(_FORSKRIFT_WORD_RE.search(block)) and not _ACT_VOCAB_RE.search(block)


def act_scoped_operative_blocks(operative_blocks: Sequence[str]) -> tuple[tuple[str, ...], int]:
    """Drop forskrift-only consequential blocks; the first block is always kept.

    Returns the kept blocks and the number dropped.
    """
    kept: list[str] = []
    dropped = 0
    for index, block in enumerate(operative_blocks):
        if index > 0 and is_forskrift_only_block(block):
            dropped += 1
            continue
        kept.append(block)
    return tuple(kept), dropped


def split_sentences(text: str) -> list[str]:
    """Split on ``. `` or ``: `` before a capital or a ``§``, abbreviations aside."""
    parts: list[str] = []
    start = 0
    for match in _SENTENCE_BREAK_RE.finditer(text):
        if match.group(0).startswith("."):
            head = text[start : match.start()]
            last = head.rsplit(None, 1)[-1].lower() if head.strip() else ""
            if last.rstrip(".") in _ABBREVIATIONS or last.split(".")[-1] in _ABBREVIATIONS:
                continue
        parts.append(text[start : match.start()])
        start = match.end()
    parts.append(text[start:])
    cleaned = [_LEADING_JUNK_RE.sub("", part).strip() for part in parts]
    return [part for part in cleaned if part]


def _read_date(cursor: _Cursor, reading: _Reading) -> str | None:
    """A date, ``straks``, or a deferral (``None``); refuses if none is present."""
    match = cursor.take(_DATE_RE)
    if match is not None:
        return reading.check_date(reading.iso(match.group(1), match.group(2), match.group(3)))
    if cursor.take(_STRAKS_RE) is not None:
        return reading.check_date(reading.instrument_date)
    if cursor.take(_DEFERRED_RE) is not None:
        return None
    raise _Refuse("no date after the commencement verb")


def _read_section_list(cursor: _Cursor) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``§ a[ quals][, § b …][ og § c]`` → (labels, qualified labels).

    The scanner accepts a label, then any run of qualifier tokens, then either a
    conjunction followed by another label (with or without a repeated ``§``) or
    the end of the list. Under a single ``§`` a number after a conjunction
    continues a ``nr.``/``bokstav`` qualifier rather than opening a new label;
    under ``§§`` it is a new label. Anything else closes the list.
    """
    opener = cursor.take(_SECTION_OPEN_RE)
    if opener is None:
        raise _Refuse("expected a section list")
    plural = opener.group(0).startswith("§§")
    labels: list[str] = []
    qualified: list[str] = []
    while True:
        label_match = cursor.take(_LABEL_RE)
        if label_match is None:
            raise _Refuse("section sign without a label")
        label = _normalize_section_label(
            label_match.group(1), label_match.group(2) or label_match.group(3)
        )
        labels.append(label)
        last_keyword = ""
        is_qualified = False
        # Qualifier run.
        while True:
            if cursor.take(_ORDINAL_RE) is not None:
                is_qualified = True
                continue
            keyword = cursor.take(_QUAL_KEYWORD_RE)
            if keyword is not None:
                is_qualified = True
                last_keyword = keyword.group(0).lower().rstrip(".")
                continue
            if last_keyword in {"nr", "bokstav", "bokstaven", "bokstavene", "bokstavane"}:
                value = cursor.peek(_QUAL_VALUE_RE)
                if value is not None:
                    cursor.take(_QUAL_VALUE_RE)
                    continue
            # A conjunction inside the qualifier run: ``første og fjerde ledd``,
            # ``nr. 1 og 3``, ``annet til fjerde punktum``.
            saved = cursor.pos
            if cursor.take(_CONJ_RE) is not None:
                if cursor.peek(_ORDINAL_RE) is not None:
                    is_qualified = True
                    continue
                if (
                    not plural
                    and last_keyword in {"nr", "bokstav", "bokstaven", "bokstavene", "bokstavane"}
                    and cursor.peek(_QUAL_VALUE_RE) is not None
                    and cursor.peek(_SECTION_OPEN_RE) is None
                ):
                    cursor.take(_QUAL_VALUE_RE)
                    continue
                cursor.pos = saved
            break
        if is_qualified:
            qualified.append(label)
        # Continuation?
        saved = cursor.pos
        if cursor.take(_CONJ_RE) is None:
            break
        if cursor.take(_SECTION_OPEN_RE) is not None:
            continue
        if plural and cursor.peek(_LABEL_RE) is not None:
            continue
        cursor.pos = saved
        break
    return tuple(labels), tuple(qualified)


def _law_ref_from_cite(match: re.Match[str]) -> str:
    day, month, year, number = match.group(1), match.group(2), match.group(3), match.group(4)
    return f"no/lov/{year}-{_MONTH_NUMBERS[month.lower()]}-{int(day):02d}-{int(number)}"


def _skip_title_tail(cursor: _Cursor) -> None:
    """Consume a law title (``om kringkasting og audiovisuelle …``) up to a stop.

    Stops before a ``§``, a part word, a commencement verb, an exception opener,
    a ``som``, a sentence end, or a conjunction that introduces a new scope item
    (``, del V``, ``og del VI``, ``, endringer i lov …``). Anything in between
    is title, and ``og`` inside a title is title.
    """
    while not cursor.at_end():
        cursor.skip_ws()
        if cursor.at_end():
            return
        if (
            cursor.peek(_SECTION_OPEN_RE) is not None
            or cursor.peek(_PART_RE) is not None
            or cursor.peek(_VERB_RE) is not None
            or cursor.peek(_EXC_OPEN_RE) is not None
            or cursor.peek(_SOM_RE) is not None
        ):
            return
        conj = cursor.peek(_CONJ_RE)
        if conj is not None:
            look = _Cursor(cursor.text, conj.end())
            if (
                look.peek(_PART_RE) is not None
                or look.peek(_SECTION_OPEN_RE) is not None
                or look.peek(_CHANGES_IN_RE) is not None
                or look.peek(_NEW_PREFIX_RE) is not None
                or look.peek(_LAW_CITE_RE) is not None
            ):
                return
        # One word of title.
        word = _WORD_RE.match(cursor.text, cursor.pos)
        if word is None:
            return
        cursor.pos = word.end()


def _roman_value(token: str) -> int | None:
    total = 0
    previous = 0
    for char in reversed(token.upper()):
        value = _ROMAN_DIGIT_VALUES.get(char)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None


def _roman_label(value: int) -> str:
    out = ""
    for step, symbol in _ROMAN_LABEL_STEPS:
        while value >= step:
            out += symbol
            value -= step
    return out


def _read_part_labels(cursor: _Cursor) -> list[str]:
    """``del I``, ``del II, III og IV``, ``del I til V``, ``del I-V`` → labels.

    A bare roman numeral after a conjunction continues the list; ``til`` or a
    dash between two numerals is a range. Anything else closes the list.
    """
    part = cursor.take(_PART_RE)
    if part is None:
        raise _Refuse("expected a part reference")
    labels = [part.group(1).upper()]
    while True:
        saved = cursor.pos
        is_range = False
        if cursor.take(_RANGE_DASH_RE) is not None:
            is_range = True
        elif cursor.take(_CONJ_RE) is not None:
            is_range = cursor.text[saved:cursor.pos].strip().lower() == "til"
        else:
            break
        cursor.take(_PART_WORD_RE)
        roman = cursor.take(_ROMAN_RE)
        if roman is None:
            cursor.pos = saved
            break
        label = roman.group(1).upper()
        if is_range:
            low, high = _roman_value(labels[-1]), _roman_value(label)
            if low is None or high is None or low >= high:
                raise _Refuse("unreadable part range")
            labels.extend(_roman_label(step) for step in range(low + 1, high + 1))
        else:
            labels.append(label)
    return labels


def _read_scope_items(cursor: _Cursor, *, own_act_refs: frozenset[str]) -> list[NOCommencementScopeItem]:
    """The scope term(s) at the cursor, or refuse.

    Shapes, in the order tried: ``[prefix] del R[, R' …] [(name)] [, endringer i
    (lov <cite> [om …] | <short name> | loven | ∅)] [§ list]``; ``Lov <cite>
    [om …] [§ list]`` (the act itself when the citation is the cited act's, else
    a law); ``[Lovens|Loven] § list``; ``endringene i (loven|<cite>|<short
    name>) § list``; ``<short name> § list``; the bare act word. A part LIST
    followed by a section list is refused: the list cannot say which part the
    sections belong to.
    """
    cursor.take(_NEW_PREFIX_RE)
    cursor.take(_CHANGES_IN_RE)
    cursor.take(_NEW_PREFIX_RE)
    if cursor.peek(_PART_RE) is not None:
        part_labels = _read_part_labels(cursor)
        cursor.take(_PART_NAME_RE)
        law_ref = ""
        saved = cursor.pos
        if cursor.take(_CONJ_RE) is not None and cursor.take(_CHANGES_IN_RE) is not None:
            cite = cursor.take(_LAW_CITE_RE)
            if cite is not None:
                law_ref = _law_ref_from_cite(cite)
                _skip_title_tail(cursor)
            elif cursor.peek(_SECTION_OPEN_RE) is not None:
                pass
            elif cursor.take(_LAW_WORD_RE) is not None:
                pass
            else:
                short = cursor.take(_SHORT_NAME_RE)
                if short is None:
                    raise _Refuse("part qualified by an unreadable law reference")
                law_ref = short.group(1).lower()
        else:
            cursor.pos = saved
        if cursor.take(_NEW_PREFIX_RE) is not None or cursor.take(_CHANGES_IN_RE) is not None:
            cursor.take(_NEW_PREFIX_RE)
        if cursor.peek(_SECTION_OPEN_RE) is not None:
            if len(part_labels) != 1:
                raise _Refuse("section list after a part list")
            labels, qualified = _read_section_list(cursor)
            return [
                NOCommencementScopeItem(
                    kind="part",
                    part_label=part_labels[0],
                    law_ref=law_ref,
                    section_labels=labels,
                    qualified_section_labels=qualified,
                )
            ]
        return [
            NOCommencementScopeItem(kind="part", part_label=label, law_ref=law_ref)
            for label in part_labels
        ]
    cite = cursor.take(_LAW_CITE_RE)
    if cite is not None:
        law_ref = _law_ref_from_cite(cite)
        _skip_title_tail(cursor)
        cursor.take(_NEW_PREFIX_RE)
        if cursor.peek(_SECTION_OPEN_RE) is not None:
            labels, qualified = _read_section_list(cursor)
            return [
                NOCommencementScopeItem(
                    kind="sections",
                    law_ref="" if law_ref in own_act_refs else law_ref,
                    section_labels=labels,
                    qualified_section_labels=qualified,
                )
            ]
        if law_ref in own_act_refs:
            return [NOCommencementScopeItem(kind="act")]
        return [NOCommencementScopeItem(kind="law", law_ref=law_ref)]
    if cursor.peek(_SECTION_OPEN_RE) is not None:
        labels, qualified = _read_section_list(cursor)
        return [
            NOCommencementScopeItem(
                kind="sections", section_labels=labels, qualified_section_labels=qualified
            )
        ]
    saved = cursor.pos
    if cursor.take(_LAW_WORD_RE) is not None:
        cursor.take(_NEW_PREFIX_RE)
        if cursor.peek(_SECTION_OPEN_RE) is not None:
            labels, qualified = _read_section_list(cursor)
            return [
                NOCommencementScopeItem(
                    kind="sections", section_labels=labels, qualified_section_labels=qualified
                )
            ]
        cursor.pos = saved
    short = cursor.take(_SHORT_NAME_RE)
    if short is not None:
        labels, qualified = _read_section_list(cursor)
        return [
            NOCommencementScopeItem(
                kind="sections",
                law_ref=short.group(1).lower(),
                section_labels=labels,
                qualified_section_labels=qualified,
            )
        ]
    if cursor.take(_ACT_WORD_RE) is not None:
        return [NOCommencementScopeItem(kind="act")]
    raise _Refuse("no scope term at: " + cursor.rest()[:80])


def _read_item_list(cursor: _Cursor, *, own_act_refs: frozenset[str]) -> list[NOCommencementScopeItem]:
    items = _read_scope_items(cursor, own_act_refs=own_act_refs)
    while True:
        saved = cursor.pos
        if cursor.take(_CONJ_RE) is None:
            break
        try:
            items.extend(_read_scope_items(cursor, own_act_refs=own_act_refs))
        except _Refuse:
            cursor.pos = saved
            break
    return items


def _read_sentence(
    sentence: str,
    reading: _Reading,
    *,
    own_act_refs: frozenset[str],
) -> list[NOCommencementScopeStatement]:
    cursor = _Cursor(sentence)
    # Title echo: ``Delt ikraftsetting av lov … .`` with no verb anywhere.
    if cursor.peek(_ECHO_RE) is not None and _VERB_RE.search(sentence) is None:
        return []
    # List header: ``Følgende trer i kraft 1. mai 2025:`` / ``Følgende
    # bestemmelser i lov 21. desember 2005 nr. 130 om … trer i kraft 1. juli
    # 2006:``. The span between the opener and the verb may name the act (that
    # is what the header is about) but never a section or a part.
    header = cursor.take(_HEADER_START_RE)
    if header is not None:
        verb = _VERB_RE.search(sentence, cursor.pos)
        between = sentence[cursor.pos : verb.start()] if verb is not None else ""
        if verb is not None and "§" not in between and _PART_RE.search(between) is None:
            cursor.pos = verb.end()
            date = _read_date(cursor, reading)
            _expect_end(cursor)
            reading.pending_date = date
            reading.pending_date_set = True
            return []
    cursor = _Cursor(sentence)
    subjects = _read_item_list(cursor, own_act_refs=own_act_refs)
    excluded: list[NOCommencementScopeItem] = []
    statements: list[NOCommencementScopeStatement] = []
    # Pre-verb carve-out: ``Loven, med unntak av § 5, trer i kraft …``.
    if cursor.take(_EXC_OPEN_RE) is not None:
        excluded.extend(_read_item_list(cursor, own_act_refs=own_act_refs))
        cursor.take(_COMMA_RE)
    verb = cursor.take(_VERB_RE)
    if verb is None:
        # A bare item under a header takes the header's date.
        _expect_end(cursor)
        if not reading.pending_date_set:
            raise _Refuse("scope term without a verb and without a list header")
        return [
            NOCommencementScopeStatement(
                subject=subject, date=reading.pending_date, excluded=tuple(excluded)
            )
            for subject in subjects
        ]
    date = _read_date(cursor, reading)
    # Post-date carve-out: ``… 1. juli 2005 med unntak av nytt § 4-4 tredje ledd,
    # endring i § 10-3 første og annet ledd, samt opphevinga av § 4-6.``, with an
    # optional relative clause dating the carved-out items themselves.
    if cursor.take(_EXC_OPEN_RE) is not None:
        items = _read_item_list(cursor, own_act_refs=own_act_refs)
        excluded.extend(items)
        if cursor.take(_SOM_RE) is not None:
            if cursor.take(_VERB_RE) is None:
                raise _Refuse("relative clause on the carve-out has no verb")
            carved_date = _read_date(cursor, reading)
            if carved_date is not None:
                statements.extend(
                    NOCommencementScopeStatement(subject=item, date=carved_date) for item in items
                )
    _expect_end(cursor)
    return [
        NOCommencementScopeStatement(subject=subject, date=date, excluded=tuple(excluded))
        for subject in subjects
    ] + statements


def _expect_end(cursor: _Cursor) -> None:
    cursor.skip_ws()
    tail = cursor.rest()
    if _TRAILING_RE.fullmatch(tail) is None:
        raise _Refuse("unread tail: " + tail[:80])


def read_no_commencement_scope_statements(
    operative_blocks: Sequence[str],
    *,
    instrument_date: str,
    declared_dates: Sequence[str],
    own_act_law_ids: Sequence[str],
) -> NOCommencementScopeReading:
    """Read an instrument's operative text into scope statements, or refuse.

    ``instrument_date`` is what ``straks`` resolves to (the instrument's own ISO
    date); ``declared_dates`` is the ``dateInForce`` set every prose date must
    belong to; ``own_act_law_ids`` are the ``no/lov/…`` ids the instrument cites,
    so that ``Lov 17. juni 2005 nr. 98 om endringar i …`` is read as the act
    itself rather than as some other law.
    """
    blocks, dropped = act_scoped_operative_blocks(operative_blocks)
    text = _WS_RE.sub(" ", " ".join(blocks)).strip()
    reading = _Reading(instrument_date=instrument_date, declared_dates=frozenset(declared_dates))
    own_refs = frozenset(own_act_law_ids)
    statements: list[NOCommencementScopeStatement] = []
    seen: set[tuple[Any, ...]] = set()
    try:
        for sentence in split_sentences(text):
            for statement in _read_sentence(sentence, reading, own_act_refs=own_refs):
                key = (
                    statement.subject,
                    statement.date,
                    statement.excluded,
                )
                if key in seen:
                    continue
                seen.add(key)
                statements.append(statement)
    except _Refuse as refusal:
        return NOCommencementScopeReading(
            statements=(),
            total=False,
            refused_sentence=f"{refusal}",
            dates=tuple(sorted(reading.dates_read)),
            forskrift_blocks_dropped=dropped,
        )
    if not statements:
        return NOCommencementScopeReading(
            statements=(),
            total=False,
            refused_sentence="no scope statement read",
            dates=tuple(sorted(reading.dates_read)),
            forskrift_blocks_dropped=dropped,
        )
    return NOCommencementScopeReading(
        statements=tuple(statements),
        total=True,
        refused_sentence="",
        dates=tuple(sorted(reading.dates_read)),
        forskrift_blocks_dropped=dropped,
    )
