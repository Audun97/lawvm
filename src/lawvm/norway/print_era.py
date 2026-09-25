"""Print-era (pre-2001) Norsk Lovtidend: evidence-ladder lines -> Lovdata-shaped LTI XML.

Promoted from the W-91/W-99 probe (``.tmp/w97/segment.py``, ``emit.py``,
``emit_amend.py``) at W-103. The lane is a WITNESS lane, not an admitted source
lane (``notes/NORWAY_LAWVM_STATUS.md`` §2.5): its product is an emitted act in
the unstructured pre-2001 shape the grafter already parses, carrying on every
article the evidence-ladder class of each print line it was built from.

Input is the reduced evidence ladder (``PrintEraLadder``): one record per NB
ALTO spine line with its geometry, its ladder class (``A`` ABBYY == tesseract,
``B`` two print engines agree, ``C`` GLM-OCR agrees with one print engine,
``R`` no two channels agree) and, for ``R`` lines, every candidate reading.
Landing policy is explicit (``PrintEraLandingVariant``): STRICT lands the
spine (ABBYY) reading for an ``R`` line, PROPOSAL lands the GLM-OCR reading.
Neither is agreed text; both are marked on the emitted article
(``data-lawvm-ladder`` carries the classes, ``data-lawvm-proposal`` the
proposal landings, ``data-lawvm-refused`` an instruction lead built from an
``R`` line) and receipted (``PrintEraEmissionReceipt``).

Two typographic units are applied at emission and receipted, nothing else is
normalised: the wide print dash inside a ``§ N-N`` address token folds to ``-``
in instruction leads and section headers only (W-88), and a line-end hyphen
attached to a word joins the wrapped word (a spaced line-end ``-`` is a dash
and stays).

Commencement: the pre-2001 acts carry ``dd.dateInForce`` read from the
consolidation's ``changesToParent`` ``ikr.`` metadata (the print-era
ikrafttredelse lane is not built); the receipt names the source.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lawvm.core.regex_safety import compile_classifier_regex

# --------------------------------------------------------------------------- rule ids
#: An instruction lead (``defaultP``) built from at least one ``R`` line: no two OCR
#: channels agreed on the lead's text, so the landed lead is a proposal, never agreed.
NO_PRINT_ERA_LEAD_REFUSED = "no_print_era_lead_refused"
#: A body line of class ``R`` landed from the proposal channel (GLM-OCR) under the
#: PROPOSAL variant, or from the spine (ABBYY) under STRICT.
NO_PRINT_ERA_PROPOSAL_TEXT_LANDED = "no_print_era_proposal_text_landed"
#: The print's wide dash inside a ``§ N-N`` token folded to ``-`` in a lead or header.
NO_PRINT_ERA_ADDRESS_DASH_FOLDED = "no_print_era_address_dash_folded"
#: One consequential item carved out of an omnibus act; the act's other targets are
#: not represented (not landed, not repealed).
NO_PRINT_ERA_OMNIBUS_CARVE = "no_print_era_omnibus_carve"
#: ``dd.dateInForce`` taken from the consolidation's ``ikr.`` chain metadata, or the
#: act's own date where the chain names none.
NO_PRINT_ERA_DATE_FROM_CONSOLIDATION_CHAIN = "no_print_era_date_from_consolidation_chain"

# Body-ledd indent (ALTO HPOS pixels beyond the page's body margin) and the roman
# part-marker indent of the amending acts' printed layout.
_LEDD_INDENT_PX = 22
_PART_MARKER_INDENT_PX = 400
_OLD_STYLE_HEADER_WIDTH_PX = 700

# --------------------------------------------------------------------------- patterns
_SECTION_HEADER_LOOSE_RE = compile_classifier_regex(
    r"^(?:[§S&8%$][\s§]*(\d+)[\s\-–—]*(\d+|[lI]|B)|§?\s*(\d+)\s*[-–—]\s*(\d+|[lI]|B))\s*\.\s*(\S.*)$",
    classifier_id="norway.print_era.section_header_loose",
    enable_prefilter=False,
)
# The chapter title is the remainder after the number (an optional ``.`` then spaces);
# it is sliced in ``_chapter_header`` so the pattern carries no trailing ``.*``.
_CHAPTER_HEADER_RE = compile_classifier_regex(
    r"^Kap\.?\s*(\d+)", classifier_id="norway.print_era.chapter_header", enable_prefilter=False
)
_LIST_ITEM_RE = compile_classifier_regex(
    r"^([a-zæøå]\)|\d+\.|[a-z]\.)\s+\S", classifier_id="norway.print_era.list_item", enable_prefilter=False
)
_ADDRESS_DASH_RE = compile_classifier_regex(
    r"(§§?\s*\d+)\s*[‐‑‒–—―−-]\s*(\d+)",
    classifier_id="norway.print_era.address_dash",
    enable_prefilter=False,
)
_ACT_TITLE_RE = compile_classifier_regex(r"^Lov om ", classifier_id="norway.print_era.act_title", enable_prefilter=False)
_RESOLUTION_HEAD_RE = compile_classifier_regex(
    r"^\d{1,2}\. \w+\.? Nr\. \d+", classifier_id="norway.print_era.resolution_head", enable_prefilter=False
)
_PREPARATORY_META_RE = compile_classifier_regex(
    r"^(Ot\.prp|Dok\.nr|Innst\.O|Besl\.O|St\.prp)", classifier_id="norway.print_era.meta", enable_prefilter=False
)
_LEAD_PROSE_RE = compile_classifier_regex(
    r"^I lov|^I kapittel|^I Almindelig", classifier_id="norway.print_era.lead_prose", enable_prefilter=False
)
_INSTRUCTION_VERB_RE = compile_classifier_regex(
    r"(skal lyde|oppheves|oppheva|opphevast|blir nytt|blir ny|blir |tilføyes|tilføyast|vert |skal ha|flyttes)",
    classifier_id="norway.print_era.instruction_verb",
    enable_prefilter=False,
)
_INSTRUCTION_START_RE = compile_classifier_regex(
    r"^(§|§§|[S&8%$]\s?\d|Ny |Nye |Nytt |Nåværende|Noverande|Overskrift|Kapittel|Kap\.|I lov|I kapittel|Paragraf)",
    classifier_id="norway.print_era.instruction_start",
    enable_prefilter=False,
)
_AMENDING_SECTION_HEADER_RE = compile_classifier_regex(
    r"^(§|[S&8%$])[\s§]*(\d+)[\s\-–—]*(\d+|[lI]|B)\s*\.(.*)$",
    classifier_id="norway.print_era.amending_section_header",
    enable_prefilter=False,
)
_LAW_LIST_ROW_RE = compile_classifier_regex(
    r"^\d+\.\s+Lov av ", classifier_id="norway.print_era.law_list_row", enable_prefilter=False
)
_OMNIBUS_ITEM_RE = compile_classifier_regex(
    r"^\d+\.\s+(I lov|Lov) ", classifier_id="norway.print_era.omnibus_item", enable_prefilter=False
)
_OMNIBUS_TARGET_RE = compile_classifier_regex(
    r"1992 nr\.? 127 om kringkasting", classifier_id="norway.print_era.omnibus_target", enable_prefilter=False
)
_CHAIN_ACT_RE = compile_classifier_regex(
    r"(\d{1,2}) (\w+) (\d{4}) nr\. (\d+)", classifier_id="norway.print_era.chain_act", enable_prefilter=False
)
_CHAIN_IKR_RE = compile_classifier_regex(
    r"^ \(ikr\. (\d{1,2}) (\w+) (\d{4})", classifier_id="norway.print_era.chain_ikr", enable_prefilter=False
)
_MONTHS = {
    "jan": 1, "feb": 2, "mars": 3, "apr": 4, "mai": 5, "juni": 6,
    "juli": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}
_NO_JOIN_WORDS = frozenset({"og", "eller", "m.v.", "m.v"})


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _chapter_header(text: str) -> tuple[str, str] | None:
    """``Kap. 3. Title`` -> ``("3", "Title")``; ``None`` when the line is not a chapter header."""
    match = _CHAPTER_HEADER_RE.match(text)
    if match is None:
        return None
    rest = text[match.end():]
    if rest.startswith("."):
        rest = rest[1:]
    return match.group(1), rest.strip()


def _section_label(chapter: str, number: str) -> str:
    return f"{chapter}-{number.replace('l', '1').replace('I', '1').replace('B', '8')}"


# --------------------------------------------------------------------------- ladder carriers
class PrintEraLandingVariant(str, Enum):
    """Which reading an ``R`` (refused) line lands with. Neither is agreed."""

    STRICT = "strict"
    PROPOSAL = "proposal"


@dataclass(frozen=True, slots=True)
class PrintEraLine:
    """One NB ALTO spine line with its evidence-ladder class."""

    index: int
    hpos: int
    vpos: int
    width: int
    ladder_class: str
    agreed_text: str | None
    spine_text: str | None = None
    proposal_text: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PrintEraPage:
    act_id: str
    issue_id: str
    canvas: int
    printed_page: int
    lines: tuple[PrintEraLine, ...]


@dataclass(frozen=True, slots=True)
class PrintEraLadder:
    pages: tuple[PrintEraPage, ...]

    def class_totals(self, act_id: str | None = None) -> dict[str, int]:
        totals = {"A": 0, "B": 0, "C": 0, "R": 0}
        for page in self.pages:
            if act_id is not None and page.act_id != act_id:
                continue
            for line in page.lines:
                totals[line.ladder_class] += 1
        return totals


@dataclass(frozen=True, slots=True)
class PrintEraActManifest:
    act_id: str
    issue_id: str
    issue_nr: int
    urn: str
    start_canvas: int
    start_page: int
    canvases: tuple[int, ...]
    carve_item_canvas: int | None = None


@dataclass(frozen=True, slots=True)
class LandedLine:
    """A ladder line with its landed text and page-relative indent."""

    canvas: int
    index: int
    ladder_class: str
    text: str
    indent: int
    width: int
    agreed: bool
    proposal_landed: bool


def load_print_era_ladder(path: Path) -> PrintEraLadder:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pages = []
    for page in raw["pages"]:
        lines = tuple(
            PrintEraLine(
                index=int(line["i"]),
                hpos=int(line["h"]),
                vpos=int(line["v"]),
                width=int(line["w"]),
                ladder_class=str(line["cls"]),
                agreed_text=line["text"],
                spine_text=line.get("spine"),
                proposal_text=line.get("proposal"),
                candidates=tuple(line.get("candidates") or ()),
            )
            for line in page["lines"]
        )
        pages.append(
            PrintEraPage(
                act_id=str(page["act"]),
                issue_id=str(page["issue"]),
                canvas=int(page["canvas"]),
                printed_page=int(page["printed"]),
                lines=lines,
            )
        )
    return PrintEraLadder(pages=tuple(pages))


def load_print_era_manifest(path: Path) -> tuple[PrintEraActManifest, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        PrintEraActManifest(
            act_id=str(entry["act_id"]),
            issue_id=str(entry["issue_id"]),
            issue_nr=int(entry["issue_nr"]),
            urn=str(entry["urn"]),
            start_canvas=int(entry["start_canvas"]),
            start_page=int(entry["start_page"]),
            canvases=tuple(int(c) for c in entry["canvases"]),
            carve_item_canvas=entry.get("carve_item_canvas"),
        )
        for entry in raw["acts"]
    )


def landed_lines(ladder: PrintEraLadder, act_id: str, variant: PrintEraLandingVariant) -> list[LandedLine]:
    """Every ladder line of one act with its landed text and body-margin-relative indent."""
    out: list[LandedLine] = []
    for page in ladder.pages:
        if page.act_id != act_id:
            continue
        wide = sorted(line.hpos for line in page.lines if line.width > 300)
        if wide:
            margin = wide[max(0, len(wide) // 6)]  # low quantile of the wide lines = body margin
        else:
            margin = min(line.hpos for line in page.lines)
        for line in page.lines:
            agreed = line.agreed_text is not None
            proposal_landed = False
            if agreed:
                text = line.agreed_text or ""
            elif variant is PrintEraLandingVariant.PROPOSAL and line.proposal_text:
                text = line.proposal_text
                proposal_landed = True
            else:
                text = line.spine_text or ""
            out.append(
                LandedLine(
                    canvas=page.canvas,
                    index=line.index,
                    ladder_class=line.ladder_class,
                    text=text,
                    indent=line.hpos - margin,
                    width=line.width,
                    agreed=agreed,
                    proposal_landed=proposal_landed,
                )
            )
    return out


# --------------------------------------------------------------------------- segmenter
@dataclass(frozen=True, slots=True)
class SegmentedItem:
    label: str
    text: str
    classes: tuple[str, ...]
    joins: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SegmentedLedd:
    text: str
    classes: tuple[str, ...]
    joins: tuple[str, ...]
    proposal_lines: int
    items: tuple[SegmentedItem, ...]

    @property
    def proposal_landed(self) -> bool:
        return self.proposal_lines > 0


@dataclass(frozen=True, slots=True)
class SegmentedSection:
    label: str
    title: str
    raw_header: str
    header_class: str
    header_proposal: bool
    ledd: tuple[SegmentedLedd, ...]


@dataclass(frozen=True, slots=True)
class SegmentedChapter:
    label: str
    title: str
    header_class: str
    header_proposal: bool
    sections: tuple[SegmentedSection, ...]


@dataclass(frozen=True, slots=True)
class SegmentedAct:
    act_id: str
    title: str
    chapters: tuple[SegmentedChapter, ...]
    preamble: tuple[SegmentedLedd, ...]

    def emitted_proposal_lines(self) -> int:
        """Proposal-landed lines that reach the emission (the preamble is not emitted)."""
        return sum(
            int(chapter.header_proposal)
            + sum(int(section.header_proposal) + sum(ledd.proposal_lines for ledd in section.ledd) for section in chapter.sections)
            for chapter in self.chapters
        )


@dataclass(slots=True)
class _Unit:
    kind: str
    lines: list[LandedLine] = field(default_factory=list)
    items: list[list[LandedLine]] = field(default_factory=list)
    label: str = ""
    title: str = ""
    raw: str = ""


def join_wrapped_lines(lines: list[LandedLine]) -> tuple[str, tuple[str, ...]]:
    """Join physical lines; a hyphen attached to a line-end word joins the wrapped word."""
    text = ""
    joins: list[str] = []
    for line in lines:
        piece = line.text
        if not text:
            text = piece
            continue
        first = piece.split(" ")[0] if piece else ""
        attached_hyphen = text.endswith("-") and not text.endswith(" -")
        if attached_hyphen and first and first[0].islower() and first not in _NO_JOIN_WORDS:
            joins.append(text.split(" ")[-1] + "|" + first)
            text = text[:-1] + piece
        else:
            text = text + " " + piece
    return text, tuple(joins)


def _ledd_from_unit(unit: _Unit) -> SegmentedLedd:
    text, joins = join_wrapped_lines(unit.lines)
    items = []
    for item_lines in unit.items:
        item_text, item_joins = join_wrapped_lines(item_lines)
        marker = _LIST_ITEM_RE.match(item_text)
        if marker is None:  # the unit was opened by a matching line, so this cannot happen
            raise ValueError(f"print-era list item lost its marker: {item_text[:80]!r}")
        items.append(
            SegmentedItem(
                label=marker.group(1),
                text=item_text[len(marker.group(1)):].strip(),
                classes=tuple(line.ladder_class for line in item_lines),
                joins=item_joins,
            )
        )
    return SegmentedLedd(
        text=text,
        classes=tuple(line.ladder_class for line in unit.lines),
        joins=joins,
        proposal_lines=sum(1 for line in unit.lines if line.proposal_landed)
        + sum(1 for item in unit.items for line in item if line.proposal_landed),
        items=tuple(items),
    )


def segment_founding_act(act_id: str, lines: list[LandedLine]) -> SegmentedAct:
    """Chapters by ``Kap. N.``, sections by ``§ N-N.`` at the margin, ledd by indent, items by marker."""
    units: list[_Unit] = []
    current: _Unit | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.lines:
            units.append(current)
        current = None

    for line in lines:
        text = line.text
        chapter = _chapter_header(text)
        if chapter is not None:
            flush()
            units.append(_Unit(kind="kap", lines=[line], label=chapter[0], title=chapter[1]))
            continue
        header = _SECTION_HEADER_LOOSE_RE.match(text)
        if header is not None and line.indent < _LEDD_INDENT_PX:
            groups = header.groups()
            chap, num = (groups[0], groups[1]) if groups[0] else (groups[2], groups[3])
            flush()
            units.append(
                _Unit(kind="sec", lines=[line], label=_section_label(chap, num), title=groups[4].strip(), raw=text)
            )
            continue
        if _LIST_ITEM_RE.match(text):
            if current is None:
                current = _Unit(kind="ledd")
            current.items.append([line])
            continue
        if current is not None and current.items and line.indent < _LEDD_INDENT_PX:
            current.items[-1].append(line)
            continue
        if line.indent >= _LEDD_INDENT_PX:
            flush()
            current = _Unit(kind="ledd", lines=[line])
            continue
        if current is None:
            current = _Unit(kind="ledd", lines=[line])
        else:
            current.lines.append(line)
    flush()

    chapters: list[tuple[_Unit, list[tuple[_Unit, list[SegmentedLedd]]]]] = []
    preamble: list[SegmentedLedd] = []
    for unit in units:
        if unit.kind == "kap":
            chapters.append((unit, []))
        elif unit.kind == "sec":
            if not chapters:
                raise ValueError(f"print-era section {unit.label} precedes the first chapter header")
            chapters[-1][1].append((unit, []))
        elif chapters and chapters[-1][1]:
            chapters[-1][1][-1][1].append(_ledd_from_unit(unit))
        else:
            preamble.append(_ledd_from_unit(unit))
    title = lines[0].text if lines and _ACT_TITLE_RE.match(lines[0].text) else (preamble[0].text if preamble else "Lov")
    return SegmentedAct(
        act_id=act_id,
        title=title,
        chapters=tuple(
            SegmentedChapter(
                label=kap.label,
                title=kap.title,
                header_class=kap.lines[0].ladder_class,
                header_proposal=kap.lines[0].proposal_landed,
                sections=tuple(
                    SegmentedSection(
                        label=sec.label,
                        title=sec.title,
                        raw_header=sec.raw,
                        header_class=sec.lines[0].ladder_class,
                        header_proposal=sec.lines[0].proposal_landed,
                        ledd=tuple(ledd),
                    )
                    for sec, ledd in sections
                ),
            )
            for kap, sections in chapters
        ),
        preamble=tuple(preamble),
    )


# --------------------------------------------------------------------------- emission receipts
@dataclass(frozen=True, slots=True)
class PrintEraPartReceipt:
    marker: str
    line_count: int
    targets_base: bool


@dataclass(frozen=True, slots=True)
class PrintEraCarveReceipt:
    item_no: str
    item_canvas: int
    items_on_page: int
    rule_id: str = NO_PRINT_ERA_OMNIBUS_CARVE


@dataclass(frozen=True, slots=True)
class PrintEraEmissionReceipt:
    act_id: str
    title: str
    line_count: int
    parts: tuple[PrintEraPartReceipt, ...]
    refused_leads: tuple[str, ...]
    address_folds: int
    proposal_lines: int
    date_in_force: str
    date_source: str
    carve: PrintEraCarveReceipt | None
    rule_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "act_id": self.act_id,
            "title": self.title,
            "line_count": self.line_count,
            "parts": [(p.marker, p.line_count, p.targets_base) for p in self.parts],
            "refused_leads": list(self.refused_leads),
            "address_folds": self.address_folds,
            "proposal_lines": self.proposal_lines,
            "date_in_force": self.date_in_force,
            "date_source": self.date_source,
            "carve": None
            if self.carve is None
            else {"item_no": self.carve.item_no, "item_canvas": self.carve.item_canvas, "items_on_page": self.carve.items_on_page},
            "rule_ids": list(self.rule_ids),
        }


@dataclass(frozen=True, slots=True)
class PrintEraEmission:
    act_id: str
    file_name: str
    xml: str
    receipt: PrintEraEmissionReceipt


@dataclass(slots=True)
class _ReceiptBuilder:
    refused_leads: list[str] = field(default_factory=list)
    address_folds: int = 0
    proposal_lines: int = 0

    def fold_address(self, text: str) -> str:
        folded = _ADDRESS_DASH_RE.sub(lambda m: f"{m.group(1)}-{m.group(2)}", text)
        if folded != text:
            self.address_folds += 1
        return folded

    def rule_ids(self, *, carve: bool, date_source: str) -> tuple[str, ...]:
        ids = []
        if self.refused_leads:
            ids.append(NO_PRINT_ERA_LEAD_REFUSED)
        if self.proposal_lines:
            ids.append(NO_PRINT_ERA_PROPOSAL_TEXT_LANDED)
        if self.address_folds:
            ids.append(NO_PRINT_ERA_ADDRESS_DASH_FOLDED)
        if carve:
            ids.append(NO_PRINT_ERA_OMNIBUS_CARVE)
        if date_source == "consolidation-chain-ikr":
            ids.append(NO_PRINT_ERA_DATE_FROM_CONSOLIDATION_CHAIN)
        return tuple(ids)


# --------------------------------------------------------------------------- commencement dates
def commencement_dates_from_chains(chains: list[dict[str, str]]) -> dict[str, tuple[str, ...]]:
    """Pre-2001 act id -> its ``ikr.`` dates as printed in the consolidation's ``changesToParent`` chains."""
    dates: dict[str, set[str]] = {}
    for section in chains:
        chain = section["chain"]
        for match in _CHAIN_ACT_RE.finditer(chain):
            day, month, year, number = match.groups()
            if int(year) >= 2001 or month not in _MONTHS:
                continue
            act_id = f"{year}-{_MONTHS[month]:02d}-{int(day):02d}-{number}"
            bucket = dates.setdefault(act_id, set())
            ikr = _CHAIN_IKR_RE.match(chain[match.end():])
            if ikr is not None and ikr.group(2) in _MONTHS:
                bucket.add(f"{ikr.group(3)}-{_MONTHS[ikr.group(2)]:02d}-{int(ikr.group(1)):02d}")
    return {act_id: tuple(sorted(found)) for act_id, found in dates.items()}


def _date_in_force(act_id: str, dates: dict[str, tuple[str, ...]]) -> tuple[str, str]:
    found = dates.get(act_id, ())
    if found:
        return found[0], "consolidation-chain-ikr"
    return act_id[:10], "act-date"


def lti_file_name(act_id: str) -> str:
    year, month, day, number = act_id[:4], act_id[5:7], act_id[8:10], int(act_id[11:])
    return f"nl-{year}{month}{day}-{number:03d}.xml"


# --------------------------------------------------------------------------- founding act
def _proposal_attribute(proposal_landed: bool) -> str:
    return ' data-lawvm-proposal="glm"' if proposal_landed else ""


def _ledd_attributes(ledd: SegmentedLedd) -> str:
    classes = "".join(ledd.classes) + "".join("|" + "".join(item.classes) for item in ledd.items)
    return f'data-lawvm-ladder="{classes}"{_proposal_attribute(ledd.proposal_landed)}'


def _ledd_xml(ledd: SegmentedLedd, indent: str = "          ") -> str:
    attrs = _ledd_attributes(ledd)
    if not ledd.items:
        return f'{indent}<article class="legalP" {attrs}>{_esc(ledd.text)}</article>\n'
    out = f'{indent}<article class="legalP" {attrs}>{_esc(ledd.text)}\n{indent}  <ol>\n'
    for item in ledd.items:
        out += f'{indent}    <li data-name="{_esc(item.label)}">{_esc(item.text)}</li>\n'
    return out + f"{indent}  </ol>\n{indent}</article>\n"


def founding_act_xml(act: SegmentedAct) -> str:
    lov_id = act.act_id
    out = (
        '<?xml version="1.0" encoding="utf-8"?>\n<html lang="nb">\n'
        f"  <head><title>{_esc(act.title)}</title></head>\n  <body>\n"
        f'    <main class="documentBody" data-lovdata-URL="LTI/lov/{lov_id}">\n'
    )
    for chapter in act.chapters:
        out += (
            f'      <section class="section" data-name="kap{chapter.label}" '
            f'data-lovdata-URL="LTI/lov/{lov_id}/KAPITTEL_{chapter.label}" data-lawvm-ladder="{chapter.header_class}"'
            f"{_proposal_attribute(chapter.header_proposal)}>\n"
            f"        <h2>Kap. {chapter.label}. {_esc(chapter.title)}</h2>\n"
        )
        for section in chapter.sections:
            out += (
                f'        <article class="legalArticle" data-name="§{section.label}" '
                f'data-lovdata-URL="LTI/lov/{lov_id}/§{section.label}" data-lawvm-ladder="{section.header_class}"'
                f"{_proposal_attribute(section.header_proposal)}>\n"
                f'          <h3 class="legalArticleHeader">§ {section.label}. {_esc(section.title)}</h3>\n'
            )
            for ledd in section.ledd:
                out += _ledd_xml(ledd)
            out += "        </article>\n"
        out += "      </section>\n"
    return out + "    </main>\n  </body>\n</html>\n"


def emit_founding_act(
    ladder: PrintEraLadder, act_id: str, dates: dict[str, tuple[str, ...]], variant: PrintEraLandingVariant
) -> PrintEraEmission:
    lines = landed_lines(ladder, act_id, variant)
    act = segment_founding_act(act_id, lines)
    receipt_builder = _ReceiptBuilder(proposal_lines=act.emitted_proposal_lines())
    date, date_source = _date_in_force(act_id, dates)
    receipt = PrintEraEmissionReceipt(
        act_id=act_id,
        title=act.title,
        line_count=len(lines),
        parts=(),
        refused_leads=(),
        address_folds=0,
        proposal_lines=receipt_builder.proposal_lines,
        date_in_force=date,
        date_source=date_source,
        carve=None,
        rule_ids=receipt_builder.rule_ids(carve=False, date_source=date_source),
    )
    return PrintEraEmission(act_id=act_id, file_name=lti_file_name(act_id), xml=founding_act_xml(act), receipt=receipt)


# --------------------------------------------------------------------------- amending acts
@dataclass(slots=True)
class _Part:
    marker: str
    lines: list[LandedLine] = field(default_factory=list)
    is_list: bool = False


def _act_region(manifest: PrintEraActManifest, lines: list[LandedLine]) -> list[LandedLine]:
    """The act's own lines on its shared pages: from its title line to the next act or resolution."""
    candidates = [
        k
        for k, line in enumerate(lines)
        if line.canvas == manifest.start_canvas and line.indent < _LEDD_INDENT_PX and _ACT_TITLE_RE.match(line.text)
    ]
    if not candidates:
        raise ValueError(
            f"print-era act {manifest.act_id}: no 'Lov om …' title line at the margin of canvas {manifest.start_canvas}"
        )
    picked = [k for k in candidates if "kringkasting" in lines[k].text or "1992 nr. 127" in lines[k].text]
    start = (picked or candidates)[0]
    end = len(lines)
    for k in range(start + 3, len(lines)):
        text = lines[k].text
        at_margin = lines[k].indent < _LEDD_INDENT_PX
        title = at_margin and _ACT_TITLE_RE.match(text) is not None
        next_amending_act = title and "endring" in text.lower() and k > start + 3 and lines[k - 1].indent < -20
        next_act_after_blank = title and _PREPARATORY_META_RE.match(text) is None and lines[k - 1].text == ""
        if _RESOLUTION_HEAD_RE.match(text) or text.startswith("Ikrafttredelse") or next_amending_act or next_act_after_blank:
            end = k
            break
    return lines[start:end]


def _structure(lines: list[LandedLine]) -> tuple[str, list[_Part]]:
    """Title lines, then the parts split at the roman part markers (indent > 400 px)."""
    title: list[str] = []
    k = 0
    while k < len(lines) and _PREPARATORY_META_RE.match(lines[k].text) is None and lines[k].indent <= _PART_MARKER_INDENT_PX:
        title.append(lines[k].text)
        k += 1
    while k < len(lines):
        line = lines[k]
        operative = (
            line.indent > _PART_MARKER_INDENT_PX
            or _LEAD_PROSE_RE.match(line.text) is not None
            or _LAW_LIST_ROW_RE.match(line.text) is not None
            or _AMENDING_SECTION_HEADER_RE.match(line.text) is not None
        )
        if _PREPARATORY_META_RE.match(line.text) is None and operative:
            break
        k += 1
    parts: list[_Part] = []
    current: _Part | None = None
    for line in lines[k:]:
        if line.indent > _PART_MARKER_INDENT_PX:
            current = _Part(marker=line.text or "?")
            parts.append(current)
            continue
        if _LAW_LIST_ROW_RE.match(line.text) and (current is None or current.is_list):
            current = _Part(marker=line.text, is_list=True)
            parts.append(current)
            continue
        if current is None:
            current = _Part(marker="")
            parts.append(current)
        current.lines.append(line)
    return " ".join(title), parts


def _part_targets_base(part: _Part) -> bool:
    lead = " ".join(line.text for line in part.lines[:2]) + " " + part.marker
    return ("kringkasting" in lead.lower()) or ("1992 nr. 127" in lead)


def _is_instruction(line: LandedLine, text: str) -> bool:
    return (
        line.indent < _LEDD_INDENT_PX
        and _INSTRUCTION_START_RE.match(text) is not None
        and _INSTRUCTION_VERB_RE.search(text) is not None
        and (text.endswith(":") or text.endswith("."))
    )


@dataclass(slots=True)
class _PayloadLedd:
    texts: list[str]
    classes: list[str]
    proposal: bool

    def attributes(self) -> str:
        return f'data-lawvm-ladder="{"".join(self.classes)}"{_proposal_attribute(self.proposal)}'


def _emit_part(part: _Part, part_label: str, receipt: _ReceiptBuilder) -> str:
    out = f'      <section data-name="kap{part_label}">\n'
    lines = part.lines
    k = 0
    if part.is_list:
        out += f'        <article class="defaultP">{_esc(part.marker)}</article>\n'
    if lines and _LEAD_PROSE_RE.match(lines[0].text):
        lead = lines[0].text
        k = 1
        while (
            not lead.rstrip().endswith(":")
            and k < len(lines)
            and lines[k].indent < _LEDD_INDENT_PX
            and _INSTRUCTION_START_RE.match(lines[k].text) is None
        ):
            lead += " " + lines[k].text
            k += 1
        lead_classes = "".join(line.ladder_class for line in lines[:k])
        lead_proposal = _proposal_attribute(any(line.proposal_landed for line in lines[:k]))
        out += f'        <article class="legalP" data-lawvm-ladder="{lead_classes}"{lead_proposal}>{_esc(lead)}</article>\n'
    ledd: _PayloadLedd | None = None
    future_open = False
    in_chapter = False
    previous_instruction = ""

    def close_ledd() -> None:
        nonlocal ledd, out
        if ledd is not None:
            indent = "          " if future_open else "        "
            out += f'{indent}<article class="legalP" {ledd.attributes()}>{_esc(" ".join(ledd.texts))}</article>\n'
            ledd = None

    def close_future() -> None:
        nonlocal future_open, out
        close_ledd()
        if future_open:
            out += "        </article>\n"
            future_open = False

    while k < len(lines):
        line = lines[k]
        text = line.text
        k += 1
        if not text:
            continue
        if _AMENDING_SECTION_HEADER_RE.match(text) or _INSTRUCTION_START_RE.match(text):
            text = receipt.fold_address(text)
        instruction = _is_instruction(line, text)
        opens_new_section = previous_instruction.startswith(("Ny ", "Nye ", "Kapittel")) and (
            _AMENDING_SECTION_HEADER_RE.match(text) is not None or text.startswith("Kap")
        )
        carried_section = (
            future_open and in_chapter and line.indent < _LEDD_INDENT_PX and _AMENDING_SECTION_HEADER_RE.match(text) is not None
        )
        if opens_new_section or carried_section:
            close_future()
            if text.startswith("Kap"):
                out += f'        <h2 data-lawvm-ladder="{line.ladder_class}"{_proposal_attribute(line.proposal_landed)}>{_esc(text)}</h2>\n'
                continue
            header = _AMENDING_SECTION_HEADER_RE.match(text)
            if header is None:  # unreachable: both branches above matched the header
                raise ValueError(f"print-era section header lost: {text[:80]!r}")
            label = _section_label(header.group(2), header.group(3))
            rest = header.group(4).strip()
            future_open = True
            out += (
                f'        <article class="futureLegalArticle" data-name="§{label}" '
                f'data-lawvm-ladder="{line.ladder_class}"{_proposal_attribute(line.proposal_landed)}>\n'
            )
            following = lines[k] if k < len(lines) else None
            old_style = (
                bool(rest)
                and following is not None
                and following.indent < _LEDD_INDENT_PX
                and following.width > _OLD_STYLE_HEADER_WIDTH_PX
                and _INSTRUCTION_START_RE.match(following.text) is None
            )
            if old_style:  # sentence text follows the number directly and continues full-width at the margin
                out += f'          <span class="futureLegalArticleHeader">§ {label}.</span>\n'
                ledd = _PayloadLedd(texts=[rest], classes=[line.ladder_class], proposal=line.proposal_landed)
            else:
                while (
                    k < len(lines)
                    and lines[k].indent < _LEDD_INDENT_PX
                    and lines[k].width <= _OLD_STYLE_HEADER_WIDTH_PX
                    and _INSTRUCTION_START_RE.match(lines[k].text) is None
                    and lines[k].text
                    and lines[k].text[0].islower()
                ):
                    rest += " " + lines[k].text
                    k += 1
                out += (
                    f'          <span class="futureLegalArticleHeader">§ {label}. '
                    f'<span class="legalArticleTitle">{_esc(rest)}</span></span>\n'
                )
            previous_instruction = ""
            continue
        if instruction and not (future_open and line.indent >= _LEDD_INDENT_PX):
            close_future()
            refused = "" if line.agreed else ' data-lawvm-refused="1"'
            out += (
                f'        <article class="defaultP" data-lawvm-ladder="{line.ladder_class}"{refused}'
                f"{_proposal_attribute(line.proposal_landed)}>{_esc(receipt.fold_address(text))}</article>\n"
            )
            if not line.agreed:
                receipt.refused_leads.append(text)
            in_chapter = text.startswith("Kapittel")
            previous_instruction = text
            continue
        # payload line
        if line.indent >= _LEDD_INDENT_PX or ledd is None:
            close_ledd()
            ledd = _PayloadLedd(texts=[text], classes=[line.ladder_class], proposal=line.proposal_landed)
        else:
            last = ledd.texts[-1]
            attached_hyphen = last.endswith("-") and not last.endswith(" -")
            if attached_hyphen and text[0].islower() and text.split(" ")[0] not in ("og", "eller"):
                ledd.texts[-1] = last[:-1] + text
            else:
                ledd.texts.append(text)
            ledd.classes.append(line.ladder_class)
            ledd.proposal = ledd.proposal or line.proposal_landed
    close_future()
    return out + "      </section>\n"


def _document_head(title: str, base_lov_id: str, date_in_force: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<html lang="nb">\n'
        f"  <head><title>{_esc(title)}</title></head>\n  <body>\n"
        f'    <dd class="changesToDocuments"><ul><li>lov/{base_lov_id}</li></ul></dd>\n'
        f'    <dd class="dateInForce">{date_in_force}</dd>\n    <main>\n'
    )


def emit_amending_act(
    ladder: PrintEraLadder,
    manifest: PrintEraActManifest,
    base_lov_id: str,
    dates: dict[str, tuple[str, ...]],
    variant: PrintEraLandingVariant,
) -> PrintEraEmission:
    act_id = manifest.act_id
    region = _act_region(manifest, landed_lines(ladder, act_id, variant))
    title, parts = _structure(region)
    date, date_source = _date_in_force(act_id, dates)
    out = _document_head(title, base_lov_id, date)
    # a repeated law-list row keeps only its last occurrence (the list is reprinted per part)
    last_by_marker: dict[str, int] = {}
    for i, part in enumerate(parts):
        if part.is_list:
            last_by_marker[part.marker[:30]] = i
    kept = [part for i, part in enumerate(parts) if not part.is_list or last_by_marker[part.marker[:30]] == i]
    emitted_parts = [part for part in kept if _part_targets_base(part)]
    receipt = _ReceiptBuilder(
        proposal_lines=sum(1 for part in emitted_parts for line in part.lines if line.text and line.proposal_landed)
    )
    for n, part in enumerate(emitted_parts, start=1):
        out += _emit_part(part, "I" * n if n < 4 else str(n), receipt)
    out += "    </main>\n  </body>\n</html>\n"
    return PrintEraEmission(
        act_id=act_id,
        file_name=lti_file_name(act_id),
        xml=out,
        receipt=PrintEraEmissionReceipt(
            act_id=act_id,
            title=title,
            line_count=len(region),
            parts=tuple(
                PrintEraPartReceipt(marker=part.marker[:40], line_count=len(part.lines), targets_base=_part_targets_base(part))
                for part in parts
            ),
            refused_leads=tuple(receipt.refused_leads),
            address_folds=receipt.address_folds,
            proposal_lines=receipt.proposal_lines,
            date_in_force=date,
            date_source=date_source,
            carve=None,
            rule_ids=receipt.rule_ids(carve=False, date_source=date_source),
        ),
    )


def emit_omnibus_carve(
    ladder: PrintEraLadder,
    manifest: PrintEraActManifest,
    base_lov_id: str,
    dates: dict[str, tuple[str, ...]],
    variant: PrintEraLandingVariant,
) -> PrintEraEmission:
    """The one consequential item of an omnibus act that names the base law; nothing else lands."""
    if manifest.carve_item_canvas is None:
        raise ValueError(f"print-era omnibus carve needs carve_item_canvas on the manifest of {manifest.act_id}")
    act_id = manifest.act_id
    lines = landed_lines(ladder, act_id, variant)
    title_page = [line for line in lines if line.canvas == manifest.start_canvas]
    title_index = next(
        (k for k, line in enumerate(title_page) if line.indent < _LEDD_INDENT_PX and _ACT_TITLE_RE.match(line.text)),
        None,
    )
    if title_index is None:
        raise ValueError(f"print-era omnibus act {act_id}: no 'Lov om …' title line at the margin of canvas {manifest.start_canvas}")
    title_lines = [title_page[title_index].text]
    k = title_index + 1
    while (
        k < len(title_page)
        and _PREPARATORY_META_RE.match(title_page[k].text) is None
        and title_page[k].indent <= _PART_MARKER_INDENT_PX
        and title_page[k].text
        and title_page[k].text[0].islower()
    ):
        title_lines.append(title_page[k].text)
        k += 1
    title = " ".join(title_lines)
    item_page = [line for line in lines if line.canvas == manifest.carve_item_canvas]
    starts = [
        k
        for k, line in enumerate(item_page)
        if line.indent < _LEDD_INDENT_PX and _OMNIBUS_ITEM_RE.match(line.text) and _OMNIBUS_TARGET_RE.search(line.text)
    ]
    if len(starts) != 1:
        raise ValueError(f"print-era omnibus carve of {act_id}: expected one item naming the base law, found {starts}")
    start = starts[0]
    end = next(
        (k for k in range(start + 1, len(item_page)) if item_page[k].indent < _LEDD_INDENT_PX and _OMNIBUS_ITEM_RE.match(item_page[k].text)),
        len(item_page),
    )
    item = item_page[start:end]
    items_on_page = sum(1 for line in item_page if line.indent < _LEDD_INDENT_PX and _OMNIBUS_ITEM_RE.match(line.text))
    receipt = _ReceiptBuilder(proposal_lines=sum(1 for line in item if line.proposal_landed))
    date, date_source = _date_in_force(act_id, dates)
    lead = item[0].text
    lead_classes = [item[0].ladder_class]
    k = 1
    while not lead.rstrip().endswith(":") and k < len(item):
        lead += " " + item[k].text
        lead_classes.append(item[k].ladder_class)
        k += 1
    lead = receipt.fold_address(lead)
    if any(not line.agreed for line in item[:k]):
        receipt.refused_leads.append(lead)
    payload: list[_PayloadLedd] = []
    for line in item[k:]:
        text = line.text
        if not text:
            continue
        if line.indent >= _LEDD_INDENT_PX or not payload:
            payload.append(_PayloadLedd(texts=[text], classes=[line.ladder_class], proposal=line.proposal_landed))
            continue
        last = payload[-1].texts[-1]
        attached_hyphen = last.endswith("-") and not last.endswith(" -")
        if attached_hyphen and text[0].islower() and text.split(" ")[0] not in ("og", "eller"):
            payload[-1].texts[-1] = last[:-1] + text
        else:
            payload[-1].texts.append(text)
        payload[-1].classes.append(line.ladder_class)
        payload[-1].proposal = payload[-1].proposal or line.proposal_landed
    item_no = item[0].text.split(".")[0]
    carve = PrintEraCarveReceipt(item_no=item_no, item_canvas=manifest.carve_item_canvas, items_on_page=items_on_page)
    out = _document_head(title, base_lov_id, date)
    out += (
        f"      <!-- {NO_PRINT_ERA_OMNIBUS_CARVE}: item {item_no} only (of {items_on_page} items on canvas "
        f"{manifest.carve_item_canvas}); the other targets of this act are not represented -->\n"
    )
    refused = ' data-lawvm-refused="1"' if receipt.refused_leads else ""
    lead_proposal = _proposal_attribute(any(line.proposal_landed for line in item[:k]))
    out += f'      <section data-name="kapI" data-lawvm-carve="item-{item_no}">\n'
    out += (
        f'        <article class="legalP" data-lawvm-ladder="{"".join(lead_classes)}"{refused}{lead_proposal}>'
        f"{_esc(lead)}</article>\n"
    )
    for ledd in payload:
        out += f'        <article class="legalP" {ledd.attributes()}>{_esc(" ".join(ledd.texts))}</article>\n'
    out += "      </section>\n    </main>\n  </body>\n</html>\n"
    return PrintEraEmission(
        act_id=act_id,
        file_name=lti_file_name(act_id),
        xml=out,
        receipt=PrintEraEmissionReceipt(
            act_id=act_id,
            title=title,
            line_count=len(item),
            parts=(PrintEraPartReceipt(marker=item[0].text[:40], line_count=len(item), targets_base=True),),
            refused_leads=tuple(receipt.refused_leads),
            address_folds=receipt.address_folds,
            proposal_lines=receipt.proposal_lines,
            date_in_force=date,
            date_source=date_source,
            carve=carve,
            rule_ids=receipt.rule_ids(carve=True, date_source=date_source),
        ),
    )


# --------------------------------------------------------------------------- the whole slice
def emit_print_era_slice(
    ladder: PrintEraLadder,
    manifests: tuple[PrintEraActManifest, ...],
    chains: list[dict[str, str]],
    base_lov_id: str,
    *,
    founding_variant: PrintEraLandingVariant = PrintEraLandingVariant.STRICT,
    amending_variant: PrintEraLandingVariant = PrintEraLandingVariant.PROPOSAL,
) -> tuple[PrintEraEmission, ...]:
    """The founding act and every amending act of one law slice, in act-id order.

    The default landing policy is the one W-91 (v) measured and the witness pins:
    the founding act lands STRICT (its refused lines are headers the loose header
    reader already accepts, and the proposal channel straddles one of them), the
    amending acts land PROPOSAL (an ``R`` address lead under STRICT costs the whole
    section; the proposal reading recovers it and is marked on the article).
    """
    dates = commencement_dates_from_chains(chains)
    emissions = []
    for manifest in sorted(manifests, key=lambda m: m.act_id):
        if manifest.act_id == base_lov_id:
            emissions.append(emit_founding_act(ladder, manifest.act_id, dates, founding_variant))
        elif manifest.carve_item_canvas is not None:
            emissions.append(emit_omnibus_carve(ladder, manifest, base_lov_id, dates, amending_variant))
        else:
            emissions.append(emit_amending_act(ladder, manifest, base_lov_id, dates, amending_variant))
    return tuple(emissions)


def load_print_era_chains(path: Path) -> list[dict[str, str]]:
    return [{"sec": str(row["sec"]), "chain": str(row["chain"])} for row in json.loads(path.read_text(encoding="utf-8"))]


__all__ = [
    "NO_PRINT_ERA_ADDRESS_DASH_FOLDED",
    "NO_PRINT_ERA_DATE_FROM_CONSOLIDATION_CHAIN",
    "NO_PRINT_ERA_LEAD_REFUSED",
    "NO_PRINT_ERA_OMNIBUS_CARVE",
    "NO_PRINT_ERA_PROPOSAL_TEXT_LANDED",
    "LandedLine",
    "PrintEraActManifest",
    "PrintEraCarveReceipt",
    "PrintEraEmission",
    "PrintEraEmissionReceipt",
    "PrintEraLadder",
    "PrintEraLandingVariant",
    "PrintEraLine",
    "PrintEraPage",
    "PrintEraPartReceipt",
    "SegmentedAct",
    "SegmentedChapter",
    "SegmentedItem",
    "SegmentedLedd",
    "SegmentedSection",
    "commencement_dates_from_chains",
    "emit_amending_act",
    "emit_founding_act",
    "emit_omnibus_carve",
    "emit_print_era_slice",
    "founding_act_xml",
    "join_wrapped_lines",
    "landed_lines",
    "load_print_era_chains",
    "load_print_era_ladder",
    "load_print_era_manifest",
    "lti_file_name",
    "segment_founding_act",
]
