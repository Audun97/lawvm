"""Norway (NO) believed_spec catalog — the discovered-spec hypotheses, one per rule.

This is a standalone, import-light sibling of ``spec_ledger.py``'s ``_FI_RULE_SPECS``.
The main ledger's NO adapter will guard-import ``_NO_RULE_SPECS`` once its dispatch is
generalized; nothing here imports the norway frontend, so it carries no heavy deps and
stays conflict-free with parallel ``spec_ledger.py`` edits.

Voice and contract (see ``spec_ledger.py`` and ``notes_internal/SPEC_DISCOVERY_DESIGN.md``):
each entry is a one-line, falsifiable hypothesis about the *legal-amendment semantics*
the witness rule encodes — the believed spec the compiler is testing against the
authoritative Lovdata consolidated law. NO replays as consistency verification
against the live consolidated text (see ``notes/NORWAY_LAWVM_STATUS.md``), so these
describe genuine amendment semantics, not editorial conventions. Grounded in the
rule-emitting code under ``src/lawvm/norway/`` (acquisition, index, grafter, replay,
verify, statsrad, sources, inventory).

Coverage is anti-drift-guarded by ``tests/test_spec_ledger_no_catalog.py``: every
statically discoverable NO ``rule_id`` literal must have a non-empty entry, and
every key here must map to a real literal in the norway source (no dead entries).

Honest scope note — what is and is not statically enumerable.

* Discovery is by AST over ``src/lawvm/norway/*.py`` and captures every Str literal
  that ``startswith("no_")`` or ``startswith("no_verify.")``. The rule-id population
  is therefore the union of:

    - module-level ``NO_*_RULE_ID`` constants aliased to a string (e.g.
      ``NO_PARSE_STRUCTURED_TARGET_REBOUND_FROM_LEAD``) and their inline twin at
      the call site ``rule_id="no_parse_..."``;
    - inline ``rule_id=`` / ``kind=`` / ``name=`` string literals at emit sites
      (the ``ComparisonNormalizationRule.name`` and the ``NOFilteredDivergence.rule_id``
      literals under ``no_verify.``);
    - ``detail={"rule_id": "no_..."}`` payloads on action_family /
      migration_or_lineage / ontology_normalization / target_resolution_recovery
      findings, where the detail rule ids name the specific recovery contract while
      the ``kind`` (top-level) identifies the family.

* Three ``"no_..."`` literals are deliberately NOT rule ids and are excluded from
  the coverage denominator:
    - ``no_amendments`` — a replay-status enum value returned by
      ``_base_replay_status_from_statuses`` (``commencement.py``). Not a hypothesis.
    - ``no_list_items`` — a ``stopped_reason`` enum value (``statsrad.py``). Not a
      hypothesis.
    - ``no_replay_`` — a *prefix* matched by ``kind.startswith("no_replay_")`` in
      the diagnostic family-stratification path (``grafter.py``); the bare prefix
      is never an emitted rule id, only its suffixed instances are.
    - ``no_addressed_substitution`` — W-69a's provenance tag on the addressed
      word-substitution production's ops (``NO_SUBSTITUTION_PROVENANCE_TAG``), the
      apply seam's mark for its own ops. A carrier mark, not a hypothesis; the rule
      it gates (``no_replay_substitution_term_not_uniquely_present``) IS cataloged.
    - ``no_stored_consolidation`` — the W-45 census key under
      ``build_no_verify_partition``'s ``unverifiable`` sibling (``verify.py``). A
      report dict key naming a corpus population ("laws with a replayable original
      and no stored consolidation"), not a falsifiable claim about amendment
      semantics; nothing emits it as a ``rule_id`` and no finding carries it. The
      family labels on its rows (``amending_act`` / ``temporary_act`` /
      ``wage_board_act`` / ``substantive_act``) are likewise data values, and are
      outside the ``no_*`` discovery surface anyway.

* Dynamic op-id prefixes: there is no Norway counterpart of Estonia's
  ``ee_snap_{n}``. Norway does not synthesize prefix+runtimesuffix op ids, so no
  dynamic-prefix exclusion registry is required.

Every ``"no_*"`` / ``"no_verify.*"`` literal maps to exactly one believed-spec
hypothesis here.
"""
from __future__ import annotations

from typing import Dict

# Believed-spec hypothesis per NO witness_rule_id / detail rule_id / projection
# rule_id. Keys are the literal rule-id strings bound to ``NO_*_RULE_ID`` constants
# (or passed inline as ``rule_id=`` / ``kind=`` / ``name=``) across
# ``src/lawvm/norway/``.  Each value is a falsifiable one-line claim about the law.
_NO_RULE_SPECS: Dict[str, str] = {
    # --- Acquisition / index / inventory / sources -------------------------------
    "no_acquisition_duplicate_logical_locator": (
        "A Norway artifact emitted a duplicate logical locator across acquisition "
        "attempts; both attempt rows are recorded, not collapsed/silently dropped."
    ),
    "no_amendment_index_declared_target_unbound": (
        "Lovdata's declared change-target list names a law that no operation the "
        "Norway amendment index extracted binds; the shortfall is recorded as "
        "blocking source-pathology and this check never binds a declared target "
        "itself. The declared list is not inert elsewhere: the grafter's "
        "pre-existing sole-declared-ref default_base_id is the one place a "
        "declared id becomes a base_id, and it is left untouched."
    ),
    "no_amendment_index_no_change_ops": (
        "A Norway amendment artifact in the index yielded zero document-change "
        "operations; the artifact is recorded as a no-op finding, not silently "
        "absorbed into the denominator."
    ),
    "no_amendment_index_staged_commencement_collapsed": (
        "A Norwegian act whose dateInForce states a commencement date AND delegates "
        "the remainder to the executive ('Kongen bestemmer' beside a date) IS in "
        "force at the earliest stated date — the delegation stages the rest of the "
        "act, it does not defer the whole of it — so the act stays dated at "
        "min(dates) and the collapsed date count and dropped staged tail are "
        "receipted rather than silently discarded."
    ),
    "no_amendment_index_unmapped_lovtidend_xml_member": (
        "A Norway Lovtidend XML member filename could not be mapped to a law or "
        "amendment source id; recorded as blocking source-pathology under strict "
        "mode, never silently coerced."
    ),
    "no_amendment_index_unrecognized_amendment_locator": (
        "A Norway amendment index artifact whose member name and locator both "
        "failed to identify an amendment lane is recorded as a skipped acquisition."
    ),
    "no_beriktiget_announcement_paired": (
        "A Norwegian gazette announcement Lovdata marked utgått (superseded) was "
        "matched to the rectified (beriktiget) re-announcement that replaces it, "
        "and the superseded announcement's operations were withdrawn WHOLE-"
        "INSTRUMENT in favour of the rectified document's. Identity and dates stay "
        "the ACT's — a kunngjøring av beriktiget versjon republishes a law, it does "
        "not enact one — so enacted, effective, commencement gating and the group "
        "key are unchanged and only the operative text is re-read. The receipt "
        "carries both document ids and both op counts. W-84."
    ),
    "no_beriktiget_announcement_unpaired": (
        "One half of a superseded/rectified announcement pair was found without its "
        "counterpart, and NEITHER suppression nor admission applied. An utgått mark "
        "says an announcement was superseded, not by what, so its ops stand; a "
        "beriktiget re-announcement whose act carries no utgått mark is not admitted, "
        "so the forskrift lane stays shut. Blocking, because either case means a "
        "document Lovdata flagged is knowingly left unread. W-84."
    ),
    "no_beriktiget_reannouncement_lowered": (
        "The lowered operations came from a rectified (beriktiget) re-announcement "
        "filed in the forskrift lane rather than from the act's own superseded "
        "announcement; every op carries the re-announcement's id in provenance so "
        "the op stream records both the enacting act and the document its text was "
        "read from. Admission is gated on Lovdata's own marks — the beriktiget title "
        "naming exactly one act, a changesToDocuments declaration, and a matching "
        "utgått mark on that act — never on the forskrift lane being open. W-84."
    ),
    "no_resanctioned_act_superseded": (
        "A Norwegian act whose own prose says its lovvedtak was defective and could "
        "not take effect ('kunne derfor ikke iverksettes') was matched to the act "
        "that re-sanctions it, and the defective act's operations were withdrawn "
        "WHOLE-ACT — no entry, no ops. Unlike W-84's republication a re-sanctioning "
        "mints a NEW law, so nothing transfers: the replacement replays under its "
        "own id and dates, names the withdrawn act on its entry "
        "(resanctioned_from_source_id), and the gate demands bilateral citation, "
        "title equality and total re-enactment of every withdrawn base. The receipt "
        "carries both act ids and both op counts. W-85."
    ),
    "no_resanctioned_act_unpaired": (
        "One half of a re-sanctioning supersession pair was found without a "
        "counterpart passing the bilateral gate, and NEITHER suppression nor "
        "pairing applied. Prose alone does not unmake a law, so a superseded-"
        "claiming act's ops stand; a replacement whose cited counterpart is absent, "
        "cites elsewhere, differs in title, or is not re-covered base-for-base "
        "withdraws nothing. Blocking, because either case means a document that "
        "flags its own supersession is knowingly not acted on. W-85."
    ),
    "no_resanctioned_replacement_lowered": (
        "The lowered operations came from a re-sanctioned act — one whose own prose "
        "says it was 'første gang sanksjonert' as an earlier, defective act and is "
        "sanctioned anew; every op carries the superseded act's id in provenance "
        "(resanctioned_from:) so the op stream records both the act in force and "
        "the defective sanctioning it replaced. Stamped from the document's own "
        "claim, independent of the index pairing verdict. W-85."
    ),
    "no_current_law_id_parse_marker_fallback_used": (
        "Norway current-law statute id parsing fell back to a marker-bearing "
        "fallback path after the canonical parse failed but operative content is "
        "present; the fallback is recorded so the artifact stays owned."
    ),
    "no_current_law_id_parse_skipped": (
        "Norway current-law statute id parsing was skipped (canonical parse failed "
        "and no marker fallback existed); blocking source-pathology."
    ),
    "no_current_law_title_parse_skipped": (
        "Norway current-law title extraction skipped an artifact whose statute "
        "parse failed; blocking source-pathology."
    ),
    "no_ingest_existing_locator_skipped": (
        "Norway ingestion skipped an artifact whose locator was already present "
        "(skip_existing=True); recorded as transport_cleanup so the skip is "
        "auditable, not silent."
    ),
    "no_ingest_unmapped_xml_member": (
        "Norway Lovdata XML member filename could not be mapped to a legal source "
        "id during ingestion; blocking source-pathology."
    ),
    "no_lovtidend_commencement_execution_authorized": (
        "A whole-act, single-date Norsk Lovtidend commencement instrument citing an "
        "amendment act whose own commencement was unresolved IS that act's in-force "
        "evidence; the act enters force on the instrument's date, not on its own "
        "sanction date, and the authorization is recorded per act."
    ),
    "no_lovtidend_commencement_execution_date_conflict": (
        "Two Norsk Lovtidend instruments commence the same amendment act at different "
        "dates; contradictory official commencement evidence is blocking source "
        "pathology and neither date re-dates the act."
    ),
    "no_lovtidend_commencement_part_execution_authorized": (
        "A Norsk Lovtidend instrument whose own Endrer header names exactly the laws "
        "of ONE romertall part of a staged multi-part amendment act, and whose "
        "operative text does not narrow below that part, IS that part's in-force "
        "evidence; the act's operations on that part's law take the instrument's date "
        "while every other part of the act stays as unresolved as before."
    ),
    "no_lovtidend_commencement_multi_part_execution_authorized": (
        "A Norsk Lovtidend instrument whose operative text commences a multi-part "
        "amendment act as a WHOLE — naming no subdivision of it and no exception, "
        "with the act itself as the commencement clause's subject — dates every part "
        "its Endrer header names, one receipt per part; parts the header omits, and "
        "acts a later instrument commences again, stay as unresolved as before."
    ),
    "no_lovtidend_commencement_named_part_list_execution_authorized": (
        "A Norsk Lovtidend instrument whose operative text names the romertall parts it "
        "commences — a list carrying no section sign, no sub-part qualifier and no "
        "exception — dates every part its Endrer header spans, provided the list covers "
        "them all and every later instrument on the act is provably about other parts, "
        "by both its own declared laws and its own named list."
    ),
    "no_lovtidend_commencement_widened_whole_act_execution_authorized": (
        "A Norsk Lovtidend instrument whose SINGLE operative block commences an "
        "amendment act as a WHOLE — naming no subdivision of it, carrying no "
        "exception or carve-out phrase, with the act itself as the commencement "
        "clause's subject — IS that act's in-force evidence even where the shipped "
        "whole-act pattern does not match its wording; the act enters force on the "
        "instrument's date, provided no later instrument commences anything of it "
        "and the shipped route proposed no date of its own."
    ),
    "no_lovtidend_commencement_widened_whole_act_execution_date_conflict": (
        "Two Norsk Lovtidend instruments whose operative texts each commence the same "
        "amendment act as a whole give it different dates; contradictory official "
        "commencement evidence is blocking source pathology and neither date re-dates "
        "the act."
    ),
    "no_lovtidend_commencement_part_execution_date_conflict": (
        "Two Norsk Lovtidend instruments commence the same part of an amendment act at "
        "different dates; contradictory official commencement evidence is blocking "
        "source pathology and neither date dates that part."
    ),
    "no_lovtidend_commencement_execution_refused": (
        "A Norsk Lovtidend instrument citing an unresolved amendment act failed at "
        "least one execution-authorization conjunct (candidate parse, whole-act scope, "
        "exactly one commencement date); it remains evidence and re-dates nothing, and "
        "the failed conjunct is named."
    ),
    "no_lovtidend_commencement_instrument_candidate": (
        "A Norsk Lovtidend forskrift instrument contains a typed law-commencement "
        "surface and is retained as a non-authorizing candidate; acquisition or "
        "basedOn linkage alone never changes replay state."
    ),
    "no_lovtidend_commencement_instrument_coverage_invalid": (
        "Persisted Norsk Lovtidend commencement coverage contains a malformed "
        "counter; loading fails explicitly rather than silently changing the "
        "instrument-accounting partition."
    ),
    "no_lovtidend_commencement_instrument_parse_failed": (
        "A Norsk Lovtidend forskrift artifact could not be parsed by the owning "
        "commencement-instrument parser; the offending source excerpt remains a "
        "blocking residual rather than disappearing."
    ),
    "no_lovtidend_commencement_scope_unresolved": (
        "A Norsk Lovtidend commencement candidate lacks a single proved whole-law "
        "scope, affected-law binding, or effective date; strict mode blocks any "
        "promotion to replay authority."
    ),
    "no_inventory_current_law_id_artifact_fallback_used": (
        "Norway inventory used current artifact locators as a fallback because "
        "current-law ids could not be resolved directly; blocking source-pathology "
        "that affects the inventory denominator."
    ),
    "no_source_lane_selected_conflicting_duplicates": (
        "A Norway acquisition selected no source lane among conflicting duplicate "
        "logical locators; the selected-lane value records the conflict rather "
        "than silently picking one."
    ),
    "no_statsrad_event_artifact_invalid_json": (
        "A Norway statsrad event artifact failed JSON decoding; recorded with the "
        "parse error so the artifact is owned, not silently skipped."
    ),
    "no_statsrad_event_artifact_invalid_utf8": (
        "A Norway statsrad event artifact failed UTF-8 decoding; recorded with the "
        "decode error so the artifact is owned, not silently skipped."
    ),
    "no_statsrad_event_artifact_missing_payload": (
        "A Norway statsrad event locator had no stored payload; recorded as a "
        "missing acquisition so the locator is owned, not silently skipped."
    ),
    "no_statsrad_event_artifact_non_list": (
        "A Norway statsrad event artifact root was not a list; recorded as a "
        "structural source-pathology, not silently coerced."
    ),
    "no_statsrad_event_lane_unavailable_for_directory_source": (
        "A tar-directory Norway source has no Statsrad artifact namespace; the "
        "optional evidence lane is recorded unavailable instead of being opened "
        "as an Farchive or silently omitted."
    ),
    "no_statsrad_event_item_non_object": (
        "A Norway statsrad event artifact item was not an object; recorded with "
        "the offending index, not silently coerced."
    ),
    "no_statsrad_extract_missing_raw_artifact": (
        "A Norway statsrad article raw HTML artifact was missing; recorded so the "
        "missing acquisition is owned, not silently skipped."
    ),
    "no_statsrad_extract_missing_record_artifact": (
        "A Norway statsrad article metadata record artifact was missing; recorded "
        "so the missing acquisition is owned, not silently skipped."
    ),
    # --- Parse / grafter --------------------------------------------------------
    "no_parse_action_recovered_from_structured_lead": (
        "A Norway structured amendment lead carried an action needing normalization; "
        "the recovered action-family is recorded as a finding so the original "
        "intent stays traceable."
    ),
    "no_parse_collective_reenactment_part_unresolved": (
        "A Norway collective re-enactment part ('I lov X skal følgende bestemmelser "
        "lyde:') carried a member outside the closed member set; a partially applied "
        "re-enactment is a wrong law rather than a partial one, so the WHOLE part "
        "stays unlowered and the offending member is named."
    ),
    "no_parse_collective_reenactment_title_not_lowered": (
        "A Norway collective re-enactment part restates the law's own title; the "
        "Norway lowering carries no law-title operation, so the restatement is "
        "recorded as a known unlowered directive rather than silently dropped."
    ),
    "no_parse_cross_base_structured_renumber_skipped": (
        "A Norway structured renumber crossed base-act boundaries (source or "
        "destination on a different statute); it is skipped, never applied across "
        "an unrelated act."
    ),
    "no_parse_cross_base_structured_target_skipped": (
        "A Norway structured target referenced a different base act than the lead; "
        "the spec is skipped with a typed finding, not applied cross-base."
    ),
    "no_parse_document_change_base_unresolved": (
        "A Norway structured document-change lead referenced a missing or "
        "unmappable base act; the spec is skipped, failing forward to a finding "
        "instead of applying to an unresolved base."
    ),
    "no_parse_ledd_set_relabel_address_unresolved": (
        "A Norway sibling-set relabel (\"Nåværende femte og sjette ledd blir "
        "sjette og sjuende ledd.\") named no section of its own, and the nearest "
        "preceding instruction lead in the same part supplied no unambiguous "
        "antecedent — it named no section, named several, or amends another "
        "amendment rather than the base act. The relabel is refused rather than "
        "attached to a guessed address. W-66; since W-66b the SAME kind carries "
        "the section half at PUNKTUM depth too, because it is the same reader "
        "failing the same way — the depth-specific half is the sibling kind "
        "``no_parse_punktum_set_relabel_ledd_unresolved``. Since W-76 the same "
        "kind also carries the section half at ITEM (bokstav / nr.) depth, and "
        "for the same reason."
    ),
    "no_parse_punktum_set_relabel_ledd_unresolved": (
        "A Norway sibling-set relabel at PUNKTUM depth (\"Nåværende annet punktum "
        "blir nytt tredje punktum.\") resolved its SECTION but not the LEDD the "
        "punktum hangs below: the sentence named no ledd of its own and the "
        "DOM-local antecedent supplied none, named several, was a meta-amendment, "
        "or was not itself a punktum-depth instruction (an antecedent naming a "
        "whole ledd establishes that ledd as a payload, not as a container whose "
        "sentences are being renumbered). The relabel is refused rather than "
        "attached to a guessed ledd. W-66b."
    ),
    "no_parse_item_set_relabel_ledd_unresolved": (
        "A Norway sibling-set relabel at ITEM depth (\"Nåværende bokstav c blir ny "
        "bokstav d.\", \"Nåværende nr. 2 blir ny nr. 3.\") resolved its SECTION but "
        "not the LEDD the bokstav/nr. hangs below. Every corpus item node sits "
        "under a ledd, and this family never spells one, so the ledd always comes "
        "from the DOM-local antecedent — and the antecedent supplied none, named "
        "several, was a meta-amendment, or was not itself an instruction at this "
        "depth. The relabel is refused rather than attached to a guessed ledd, "
        "which at this depth would also mean a first-match DFS picking whichever "
        "ledd's bokstav carried the label. W-76."
    ),
    "no_parse_item_insert_payload_address_unresolved": (
        "A Norway item-depth NEWNESS PAYLOAD announcement (\"§ 6-2 første ledd ny "
        "bokstav c skal lyde: …\", \"Første ledd nye nr. 15 til 19 skal lyde: …\") "
        "spelled no section of its own and the DOM-local antecedent supplied "
        "none, named several, or was a meta-amendment. The INSERT is refused "
        "rather than attached to a guessed section. W-77."
    ),
    "no_parse_item_insert_payload_ledd_unresolved": (
        "A Norway item-depth NEWNESS PAYLOAD announcement resolved its SECTION "
        "but not the LEDD the new bokstav/nr. hangs below: it spelled no ledd and "
        "the DOM-local antecedent supplied none, named several, was a "
        "meta-amendment, or was not itself an instruction at this depth. Every "
        "corpus item node sits under a ledd, and the resolver's find is a "
        "first-match DFS, so a shallow (section, item) address would silently "
        "pick whichever ledd's bokstav carried the label. Refused instead. W-77."
    ),
    "no_parse_item_insert_payload_extent_unprovable": (
        "A Norway item-depth NEWNESS PAYLOAD announcement resolved its address "
        "but the payload's EXTENT could not be proved against the announced "
        "labels: the list carrier's top-level item labels did not equal the "
        "announced labels one for one and in order, or there was no list and the "
        "text carrier was not exactly one article.legalP for exactly one "
        "announced label (a numberedLegalP opens with its own numerator, which is "
        "a second address claim this production will not discard on trust). The "
        "whole lead is refused rather than lowered against a guessed split — the "
        "all-or-nothing rule, because a production that ADDS text owes the reader "
        "a proof of WHICH text. W-77."
    ),
    "no_parse_ledd_set_relabel_order_unprovable": (
        "A Norway sibling-set ledd relabel's source and destination sets form a "
        "CYCLE (a pure swap), so no vacate-before-occupy order exists and no "
        "sequential relabel can express it without a scratch slot. The whole "
        "relabel is refused rather than emitted in an order that would write onto "
        "a live sibling. W-66."
    ),
    "no_parse_malformed_structured_renumber_attr_skipped": (
        "A Norway structured renumber attribute had a malformed token shape "
        "(e.g. trailing separators); skipped with a typed finding, not coerced. "
        "Since W-70 the finding also carries WHY the normalizer declined to "
        "repair it — cross-base tokens, no matching rule, or an address that "
        "will not lower."
    ),
    "no_parse_structured_move_attr_normalized": (
        "A Norway ``data-move-part`` whose token grammar refuses was repaired by "
        "an explicit SEPARATOR rule and its legs lowered: a stray space after "
        "``;;`` (one intended pair split into two broken tokens) or ``::`` typed "
        "for ``;;``. Every rule preserves the value's address skeleton exactly, "
        "so a repair can never invent, drop or reorder an address; a value whose "
        "tokens name another base act, or that no single rule makes wholly "
        "well-formed, stays refused. Non-blocking: the legs LANDED, and this is "
        "their provenance. W-70."
    ),
    "no_parse_structured_move_attr_destination_section_normalized": (
        "A Norway ``data-move-part``'s legs named a DESTINATION SECTION other "
        "than the section their own sources sit in, while the change block's own "
        "announcement provably commands an intra-section ledd shift; the "
        "destination section was rewritten to the source's and the legs lowered. "
        "The proof is a conjunction: every leg ledd-addressed on both sides, one "
        "shared source prefix and one shared destination prefix that differ, both "
        "resolving to SECTIONS of the block's own base act, an announcement that "
        "parses as a ledd-set relabel SPELLING that source section, a prose shift "
        "map equal to the markup's pair for pair, and no other section named "
        "anywhere in the announcement. Only the section component is rewritten — "
        "each destination is rebuilt from its own declared ordinal — so the "
        "repair cannot move a leg to a ledd the markup did not declare. An "
        "attribute whose prose cannot prove the repair keeps its declared "
        "destination and goes on refusing under the relocation-provability guard, "
        "which is the correct standing state. Non-blocking: the legs LANDED, and "
        "this is their provenance. W-70b."
    ),
    "no_parse_structured_move_legs_completed_from_lead_prose": (
        "A Norway structured change block's ``data-move-part`` declared FEWER "
        "ledd move legs than its own lead sentence spells; the missing legs were "
        "templated from the declared ones (same base act, section and container "
        "path — only the shift map comes from the prose) so the cascade lowers "
        "whole. Lowering the partial set instead is what let (RENUMBER, "
        "dest_occupied) remove an occupant the true timeline merely moves down."
    ),
    "no_parse_substitution_announcement_not_lowered": (
        "A Norway structured change block is the ADDRESS LIST of a word "
        "substitution announced in prose (\"I følgende bestemmelser skal ordet "
        "«X» endres til «Y»:\"), and the announcement's (FROM, TO) pair grammar "
        "did not parse, so the pairs the substitution applies are unknown. "
        "Lowering the block anyway wrote the amendment's own announcement/address "
        "prose over every listed provision of in-force law; the block is refused "
        "instead, leaving the superseded word standing. Since W-69a this is the "
        "S3 conjunct alone — a parseable announcement now lowers to addressed "
        "TEXT_PATCH ops."
    ),
    "no_parse_substitution_multiple_announcements": (
        "A Norway word-substitution change block's governing text carries MORE "
        "THAN ONE announcement opener, and its flat ``data-change-part`` list "
        "says nothing about which listed address belongs to which announcement. "
        "Measuring every address against the first announcement's pair is "
        "provably wrong — the corpus witness concatenates four announcements over "
        "82 addresses and 35 base acts, and 8 of the 13 corpus addresses that "
        "resolve without carrying their term are its later announcements'. The "
        "whole block refuses; "
        "partial acceptance of such a node is forbidden."
    ),
    "no_parse_substitution_multi_base_address_list": (
        "A Norway word-substitution address list does not name exactly the base "
        "act of the enclosing ``document-change`` block. The structured lane "
        "binds the whole block to that base act, so lowering the list would bind "
        "a substitution to a law its addresses do not belong to; the block "
        "refuses whole."
    ),
    "no_parse_substitution_address_not_lowerable": (
        "A Norway word-substitution address token could not be lowered to a "
        "``LegalAddress`` by the shipped Lovdata path reader, so the provision to "
        "substitute in is unknown; that address refuses rather than being guessed "
        "from its neighbours in the list."
    ),
    "no_parse_replace_promoted_to_insert_for_same_target_renumber": (
        "A Norway REPLACE targeting the same address as a RENUMBER in the same "
        "group is compiled as an INSERT at the newly-renumbered label; the "
        "action-family conversion is recorded (action_family_recovery)."
    ),
    "no_parse_structured_target_rebound_from_lead": (
        "A Norway structured amendment lead resolved to a target via lead-context "
        "rebound; recorded as target_resolution_recovery so the rebound is "
        "auditable, not silent."
    ),
    "no_parse_structured_renumber_replacement_not_lowered": (
        "A Norway structured renumber lead ALSO declared a replacement of the "
        "moved provision (\"§ 14 a blir ny § 28 b og skal lyde\") but the "
        "replacement was not lowered: either the change block moved more than "
        "one provision, so which one the payload rewrites is not recoverable "
        "(move_arity_not_one), or no payload could be built for the destination "
        "address (payload_unresolved). Typed and blocking rather than a guessed "
        "attribution. W-32."
    ),
    "no_parse_structured_payload_not_declared": (
        "A Norway structured change block declared a target but no payload of its "
        "own: its own text carries no payload-introducing operative phrase in the "
        "head (\"skal … lyde\", \"skal ha følgende ordlyd\"), or carries one with "
        "nothing after the colon. Such a node's own text is an INSTRUCTION — a "
        "relabel (\"Nåværende § 66 blir § 84.\"), a repeal or word-substitution "
        "announcement, or a lead whose payload lives in structure the fallback "
        "cannot read — and the last-resort own-text fallback used to write it into "
        "in-force law at every declared address. The target refuses instead. W-79, "
        "the general closure of the wrong-text class W-75 and W-78 closed dialect "
        "by dialect."
    ),
    "no_parse_unresolved_structured_renumber_skipped": (
        "A Norway structured renumber could not lower its source or destination "
        "path; skipped with a typed finding, not coerced."
    ),
    "no_parse_unresolved_structured_target_skipped": (
        "A Norway structured target could not be lowered into a path; skipped "
        "with a typed finding, not coerced."
    ),
    "no_parse_unstructured_lead_base_unresolved": (
        "An unstructured Norway amendment lead looked operative but no base act "
        "could be resolved; recorded as a parse finding, not silently discarded."
    ),
    "no_rettelse_lowered": (
        "A published Rettelser correction carried by Lovdata's typed "
        "gazettenote/rettelse marker resolved a clean address and was lowered "
        "as an ordinary REPLACE op, dated by the host act's own commencement "
        "(the rettelse announcement date rides in provenance, apply-inert). "
        "The address is same-act, or — since W-24 — scoped to a Del of the host "
        "act and bound to the law that part amends. W-18, W-24."
    ),
    "no_rettelse_not_lowered": (
        "A published Rettelser correction was NOT lowered — excluded with a "
        "typed, non-blocking receipt naming the reason rather than silently "
        "skipped. Covers publication-metadata errata the IR does not model, "
        "nested cross-act addresses that name no law, and Del-scoped addresses "
        "whose corrected host op is itself unlowered. W-18, W-24."
    ),
    "no_same_act_item_address": (
        "Reason detail on a no_rettelse_not_lowered receipt: the correction "
        "directive did not resolve to a single same-act item address (metadata "
        "field or non-item leaf), so no op was emitted."
    ),
    "no_unique_item_payload": (
        "Reason detail on a no_rettelse_not_lowered receipt: the correction "
        "directive resolved an address but its note did not yield exactly one "
        "item payload, so binding would be a guess and no op was emitted."
    ),
    "no_nested_cross_act_address": (
        "Reason detail on a no_rettelse_not_lowered receipt: the correction "
        "directive starts at a section and names a SECOND one, reaching another "
        "act through the host act's own body without citing that act. Binding "
        "either section corrupts text, so the whole shape is excluded. W-24."
    ),
    "no_part_base_act": (
        "Reason detail on a no_rettelse_not_lowered receipt: the correction "
        "directive scoped itself to a Del of the host act, but that part "
        "resolved no base act — absent, or its own change wrappers named more "
        "than one law. W-24."
    ),
    "no_part_citation_agreement": (
        "Reason detail on a no_rettelse_not_lowered receipt: the correction "
        "directive cited a law explicitly AND scoped itself to a Del, and the "
        "two resolutions disagreed. Neither is preferred over the other. W-24."
    ),
    "no_part_scoped_target_address": (
        "Reason detail on a no_rettelse_not_lowered receipt: the Del scope and "
        "its law resolved, but the residual address is not in the erratum "
        "target grammar, so no op was emitted. W-24."
    ),
    "no_part_scoped_payload": (
        "Reason detail on a no_rettelse_not_lowered receipt: the Del-scoped "
        "target resolved but the note yielded no unique payload for its leaf "
        "kind, so binding would be a guess. W-24."
    ),
    "no_corrected_host_op": (
        "Reason detail on a no_rettelse_not_lowered receipt: the Del-scoped "
        "target resolved, but this artifact's own lowered ops touch no such "
        "address in that law. A Del-scoped erratum corrects the host act's own "
        "amendment text, so with that amendment unlowered there is nothing to "
        "correct and the address denotes a DIFFERENT provision in the law's "
        "live text. W-24."
    ),
    "no_parse_unstructured_lead_unmatched": (
        "An unstructured Norway amendment lead looked operative but matched no "
        "supported lowering family; recorded as a parse finding, not silently "
        "discarded."
    ),
    "no_parse_unstructured_multi_item_payload_arity_mismatch": (
        "An unstructured Norway lead declared SEVERAL lettered items in one "
        "sentence (\"§ 49 andre ledd bokstav e og ny bokstav f skal lyde\") but "
        "the payload did not split to cover all of them. The whole lead is "
        "dropped rather than lowered against a guessed split — the W-19 "
        "all-or-nothing rule applied to declared item arity — and the declared "
        "and unresolved targets are both recorded. W-32."
    ),
    "no_parse_unstructured_payload_unresolved": (
        "An unstructured Norway heading-replacement lead resolved a target but no "
        "heading payload could be extracted; recorded with target evidence, not "
        "silently dropped."
    ),
    "no_parse_unstructured_renumber_arity_mismatch_skipped": (
        "An unstructured Norway repeal/renumber lead resolved unequal source and "
        "destination target counts; unmatched targets are not compiled and the "
        "mismatch is recorded."
    ),
    # --- Sort-order reconciliation ---------------------------------------------
    "no_sort_order_spurious_roman_single_letter_recheck": (
        "A Norway sibling-group ordering flagged by the litra sort key is "
        "re-classified as correctly roman-numeral-ordered (i, ii, …, v); the "
        "spurious flag is recorded as a nonblocking reclassification."
    ),
    # --- Replay / apply recovery -----------------------------------------------
    "no_replay_section_commencement_contingent_skipped": (
        "W-100. One op of a Norway amendment whose binding the section-scoped "
        "commencement lane dated only in part is skipped because its own section "
        "is carved out or undated; the sibling ops that resolve to a date are "
        "applied, and each skip is recorded per op, never silent."
    ),
    "no_replay_section_future_effective_skipped": (
        "W-100. One op of a Norway amendment resolves, through the section-scoped "
        "commencement lane, to a date after the requested as-of date and is "
        "skipped; recorded per op, never silent."
    ),
    "no_lovtidend_commencement_section_scope_execution_authorized": (
        "W-100. Official Norsk Lovtidend commencement instrument(s) dated ONE "
        "binding of an amendment act below binding level — a binding date with "
        "carve-outs, per-section dates, or both — through the section-scoped "
        "statement reader; the receipt carries the sections dated, carved out, "
        "refused as ledd-qualified, and whether the binding is complete."
    ),
    "no_lovtidend_commencement_section_scope_execution_date_conflict": (
        "W-100. Two section-scoped commencement statements gave one binding or one "
        "section two dates, or dated a section differently from a binding it was "
        "not carved out of; the whole binding is refused rather than resolved."
    ),
    "no_lovtidend_commencement_section_scope_execution_refused": (
        "W-100. The section-scoped statement reader read an instrument's operative "
        "text in full but the gate could not resolve a scope term against the "
        "act's part map or bound laws; the pair re-dates nothing and the reason is "
        "recorded."
    ),
    "no_replay_contingent_commencement_skipped": (
        "A Norway amendment whose entry-into-force is contingent on royal decree "
        "is skipped from replay until the override sidecar supplies an effective "
        "date; the skip is recorded, never silent."
    ),
    "no_replay_future_effective_skipped": (
        "A Norway amendment with an effective date after the requested as-of date "
        "is skipped; recorded, never silent."
    ),
    "no_replay_missing_amendment_source": (
        "A Norway amendment referenced in the index had no locally available "
        "source artifact; recorded as blocking acquisition, never silent."
    ),
    "no_replay_no_matching_change_group": (
        "A Norway amendment artifact compiled zero change-group matches; the "
        "no-op replay is recorded as a finding so the artifact stays owned."
    ),
    "no_replay_observed_write_audit_violation": (
        "A Norway landed write whose independent before/after path diff is not "
        "fully accounted for by its WriteReceipt is recorded as a blocking "
        "adjudication; strict replay refuses contradictory receipt evidence "
        "rather than trusting the declared footprint."
    ),
    "no_replay_receipt_storage_path_projected": (
        "A chapter-free Norway legal address was projected to its exact nested IR "
        "storage path for write accounting; the receipt keeps the nominal binding "
        "and records the resolved path as landed reality, so the projection is "
        "witnessed instead of silently widening target resolution."
    ),
    "no_replay_unknown_effective_skipped": (
        "A Norway amendment whose effective status is missing or unknown, or whose "
        "effective date is absent, is recorded as blocking and skipped; contingent "
        "commencement uses its dedicated skip lane, while resolved statuses carrying "
        "an effective date, including instrument_authorized, are replayable."
    ),
    # --- Apply-fold orchestration failure (replay.py production caller) ---------------
    # iter4 W1 (silent-failure review HIGH #2): when ``apply_no_ops_conserved``
    # raises mid-fold, the production caller ``replay_no_to_pit`` catches broadly
    # (``except Exception as exc:`` — widened from ``except ValueError`` to mirror
    # the EE/EU/SE precedent, since NO was previously the WEAKEST contract of the
    # four, letting ``AssertionError`` / ``KeyError`` / ``TypeError`` / internal-
    # tree-invariant exceptions escape into the production lane as bare tracebacks
    # and silently discard bare-apply's partial witnesses) and appends a
    # non-blocking ``no_replay_apply_raise`` orchestration adjudication per
    # §1.10 (embedding ``exception_type`` / ``exception`` / ``clause_text`` via
    # ``diagnostic_detail``) before stamping
    # ``result.error = f"Failed to apply ops: {exc}"`` (the blocking gate —
    # ``classify_no_replayability`` and CLI tooling map a non-None
    # ``result.error`` to a blocking replay-failure). The adjudication is a
    # WITNESS, not the gate; bare-apply's partial witnesses (appended in place
    # before the raise by the conserved wrapper which threads
    # ``adjudications_out=result.adjudications`` directly through bare apply per
    # iter2 W2 propagation-on-raise fix) persist on ``result.adjudications`` —
    # §1.0 evidence-not-silently-destroyed contract. Mirrors the EE/EU/SE
    # precedent (silent-failure review HIGH #1-3).
    "no_replay_apply_raise": (
        "An apply-fold exception raised mid-``apply_no_ops_conserved`` is a "
        "non-blocking typed orchestration adjudication carrying the exception "
        "type/exception/clause_text snippet per §1.10 (the blocking gate stays "
        "on ``result.error``); bare-apply's partial witnesses persist on the "
        "production result's adjudication ledger — §1.0 "
        "evidence-not-silently-destroyed contract."
    ),
    # --- Heading-group fold ordering (W-12) -----------------------------------------
    # ``apply_no_heading_groups`` folds ``Ny deloverskrift`` section-range groups
    # after the op fold, in its own pass. Until W-12 that pass had no temporal
    # sort — it ran in ``replay_no_to_pit``'s collection order (the index's
    # ``source_id`` string order), the one Norway replay surface where collection
    # order was not inert. The fold now sorts by the ordering kernel's own
    # ``no_ordering_profile().temporal_key``. The multi-contributor case is
    # unreached in today's corpus (0 of 3,089 original-LTI laws; the sole witness
    # ``no/lov/2024-01-12-1`` gets all 3 groups from ``no/lovtid/2024-12-20-92``),
    # so this receipt is the §2.9 guard-liveness surface that makes the
    # latent→live transition visible instead of silent.
    "no_heading_group_multi_source_fold": (
        "One law's ``Ny deloverskrift`` heading groups arriving from more than "
        "one amendment is receipted at the fold: non-blocking when every "
        "contributor carries an effective date (the fold order is then proven "
        "by the ordering kernel's temporal key), blocking when one does not "
        "(the sort degenerates to collection order, so the order is unproven "
        "and the law must not read as cleanly replayed)."
    ),
    # --- Archive-size capped §1.8 receipts (iter2 W7 M9 5081fd10) --------------------
    # iter2 W7 M9 added ``NO_ARCHIVE_MEMBER_TOO_LARGE_REASON_CODE`` in both
    # ``norway/grafter.py:4591`` and ``norway/sources.py:61`` (twin definitions
    # to avoid a circular top-level import; both must agree byte-for-byte) as
    # a typed ``RejectedItem[str]`` receipt reason_code for archive members
    # that declare more bytes than ``$LAWVM_MAX_ARCHIVE_MEMBER_BYTES`` and are
    # skipped by the Lovdata tarball loaders. Previously the skip surfaced as
    # a stderr log line (silently dropped evidence); the typed receipt upgrades
    # the §1.8 conservation-lane surface so the skip is owned (non-blocking —
    # operator-tunable cap, over-retention per §0). iter4 W1 added the matching
    # believed_spec entry (pre-existing uncataloged since iter2 W7 — concurrent
    # fix to make ``test_every_discovered_rule_id_is_cataloged`` green so the
    # HIGH-2 ``no_replay_apply_raise`` entry can land on a green NO catalog).
    "no_archive_member_too_large": (
        "A Norway archive member (tarball row) that declares more bytes than "
        "``$LAWVM_MAX_ARCHIVE_MEMBER_BYTES`` is skipped by the Lovdata loader "
        "(``open_lovdata_archive`` / ``_iter_current_artifacts_from_dir``) with "
        "a typed ``RejectedItem[str]`` receipt (``reason_code="
        "no_archive_member_too_large``, ``blocking=False``) so the §1.8 "
        "conservation-lane inspects the skip — never a silent stderr drop."
    ),
    "no_repeal_payload_dropped": (
        "A Norway REPEAL/TEXT_REPEAL op arrived at the generic structured-spec mint "
        "boundary carrying a non-None payload (the candidate map is consulted for all "
        "actions); the payload is coerced to None — a repeal removes its target, so a "
        "content payload is contradictory — and the drop is recorded as a non-blocking "
        "adjudication, never silently discarded."
    ),
    "no_replay_insert_occupied_direct_child_refused": (
        "A Norway INSERT whose own target address did NOT resolve would have "
        "overwritten an occupied direct child at an inferred parent — an address "
        "the operation never named, matched only by payload (kind, label). W-63 "
        "refuses it: no write lands, the occupant survives, and the op is "
        "rejected with a typed blocking receipt instead of being silently "
        "converted to a replace. Distinct from the declared θ cell "
        "no_replay_insert_occupied_target_replaced, which keeps its RECOVER "
        "polarity for the case where the op's OWN address resolves."
    ),
    "no_replay_insert_occupied_target_replaced": (
        "A Norway INSERT landed on an occupied single target; replay recovers by "
        "replacing the target, recording the action-family conversion "
        "(insert→replace) rather than silently overwriting it."
    ),
    "no_replay_ledd_set_relabel_occupied_destination_refused": (
        "A leg of a W-66 sibling-set ledd relabel found its destination still "
        "OCCUPIED when it ran. The parse plane cannot prove that a section ends "
        "where the drafter's ordinals say it does, and taking the declared θ "
        "(RENUMBER, dest_occupied) recovery here destroyed in-force law twice in "
        "measurement (straffeloven 2005 § 3 femte ledd, verdipapirhandelloven "
        "§ 9-21 fjerde ledd — base editions that already carry the amendment being "
        "replayed). This production refuses instead: no write lands, the occupant "
        "survives, the op is rejected with a typed blocking receipt, and the "
        "refusal CASCADES down the relabel's vacate-before-occupy chain so the set "
        "drops whole rather than in halves. W-66."
    ),
    "no_replay_item_insert_payload_occupied_target_refused": (
        "A W-77 item-depth newness payload INSERT found its target label already "
        "OCCUPIED when it ran. The declared θ (INSERT, target_occupied) recovery "
        "REPLACES the occupant, which is right for the \"ny § 4 a skal lyde\" "
        "surface §2.3 documents and wrong here: an announcement that says NY "
        "bokstav c and finds bokstav c standing means the relabel that should "
        "have vacated it did not fire, or the archived base edition already "
        "carries this amendment — and in neither reading is the occupant's "
        "in-force text the thing to delete (W-66 measured exactly that "
        "destruction at the ledd depth). This production refuses instead: no "
        "write lands, the occupant survives, and the op is rejected with a typed "
        "blocking receipt. The shipped θ cell keeps its RECOVER polarity for "
        "every op that is not this production's. W-77."
    ),
    "no_replay_relocation_order_unprovable_refused": (
        "A leg of a Norway RENUMBER relocation whose atomic group admits NO order "
        "in which every leg avoids writing onto a live sibling. W-66's ordering is "
        "over integer ordinals inside ONE sibling set; the structured "
        "data-move-part lane mints legs that LEAVE their container, so W-69c "
        "re-keys the dependency node on the resolved (parent_path, label) pair and "
        "judges each connected component of the relocation graph. A component is "
        "unprovable when two legs contest a destination, two legs contest a "
        "source, or the vacate relation closes a cycle — none of which a "
        "topological sort can report, because its only possible answer is a "
        "permutation. Every leg of an unprovable component refuses: no write "
        "lands, the component drops whole rather than in halves (the W-56 failure "
        "mode), and the op is rejected with a typed blocking receipt. "
        "Under-application is safe; choosing a winner between two contradictory "
        "instructions would be a semantics change on landed ops. W-69c."
    ),
    "no_replay_substitution_term_not_uniquely_present": (
        "A W-69a addressed word substitution reached its resolved provision and "
        "the announced term did not prove itself there: either more than one of "
        "the announcement's FROM terms is present as a whole word (the pairs are "
        "prefix-nested, so a node carrying both would take two writes from one "
        "announcement), or this op's own term is absent / present only as an "
        "inflection / present only inside a longer word / present more than once. "
        "The shipped ``_apply_no_text_replace`` is an unguarded recursive "
        "``str.replace`` honouring neither occurrence nor word boundary, so the "
        "op refuses rather than write: no state changes, the superseded word "
        "stands, and the reason is typed instead of vanishing into a "
        "content-identical no-op."
    ),
    "no_replay_renumber_occupied_destination_removed": (
        "A Norway RENUMBER landed on an occupied destination that was not itself "
        "moved by the same group; replay clears the destination and records the "
        "removal as a migration_or_lineage finding rather than silently destroying "
        "it."
    ),
    "no_replay_replace_recovered_by_insert": (
        "A Norway REPLACE whose target is absent is recovered by an INSERT at the "
        "missing location, recording the action-family conversion "
        "(replace→insert) rather than failing silently or widening scope."
    ),
    "no_replay_sentence_children_materialized": (
        "A Norway sentence-level operation targets a shallow sentence host with "
        "sentence children; replay materializes the children and records the "
        "ontology_normalization finding rather than silently picking one."
    ),
    "no_replay_shallow_sentence_target_rebound": (
        "A Norway section-level sentence target resolves through the section's "
        "unique direct sentence host; replay records the target_resolution_recovery "
        "finding rather than silently re-routing."
    ),
    "no_sentence_text_materialized_for_sentence_target": (
        "A Norway sentence-level operation targets a section whose sentence host "
        "was not materialized; replay materializes the sentence text from the "
        "unique host and records the ontology_normalization finding."
    ),
    "no_sentence_text_materialized_for_shallow_sentence_target": (
        "A Norway sentence-level operation targets a shallow sentence host; "
        "replay materializes sentence text from that host and records the "
        "ontology_normalization finding."
    ),
    "no_shallow_sentence_target_rebound_to_unique_host": (
        "A Norway shallow sentence target rebinds to the section's unique direct "
        "sentence host; replay records the target_resolution_recovery finding "
        "rather than silently re-keying the address."
    ),
    # --- Detail rule ids on action_family / migration_or_lineage records ---------
    # These are the detail payload rule ids that name the specific recovery
    # contract paired with their family-level ``kind`` counterparts above.
    "no_insert_occupied_direct_child_refuse": (
        "Detail rule id on the unsupported_or_unresolved_action refusal record "
        "for no_replay_insert_occupied_direct_child_refused — names the specific "
        "W-63 refusal contract: an INSERT whose unresolved target would have "
        "overwritten a label-matched direct child at an inferred parent lands "
        "nothing and is rejected."
    ),
    "no_insert_occupied_target_replace": (
        "Detail rule id on the action_family_recovery record for "
        "no_replay_insert_occupied_target_replaced — names the specific "
        "insert→replace recovery contract on the resolved target path."
    ),
    "no_renumber_occupied_destination_removed": (
        "Detail rule id on the migration_or_lineage recovery record for "
        "no_replay_renumber_occupied_destination_removed — names the specific "
        "destination-clearing recovery contract."
    ),
    # --- Apply receipt contract (§4 WriteReceipt divergence-naming) ----------------------
    # Mirrors SE's ``se_renumber_relabel`` (``sweden/grafter.py:4145``) and EE's
    # ``_EE_SECTION_SEQUENCE_RENUMBER_RULE`` (``estonia/peg.py:1225``) — a RENUMBER
    # op mints an identity migration (bound source label → landed destination
    # label) that the §1.6 unstated-migration invariant MUST carry with a named
    # rule id. Stamped on the op at mint time as ``witness_rule_id`` (the
    # parse→apply waist proof). The authoritative apply fold also stamps the same
    # id on its per-op WriteReceipt.
    "no_section_renumber_relabel": (
        "A Norway RENUMBER op's bound_target_path (source label) vs "
        "landed_primary_path (destination label) divergence is the typed named "
        "migration for a section relabel/renumber — ``witness_rule_id`` stamped "
        "on the op at mint time so the §1.6 unstated-migration invariant's "
        "identity migration has a named owner at the parse→apply waist (mirrors "
        "EE's ``_EE_SECTION_SEQUENCE_RENUMBER_RULE`` on op construction). The "
        "name ``section`` describes the dominant case but the rule id is the "
        "broad family owner for every RENUMBER op (one id per family, mirroring "
        "SE's single ``se_renumber_relabel``). The authoritative apply fold "
        "stamps the same id in the receipt's ``migration_rule_ids``."
    ),
    "no_observed_write_audit_must_match_receipt": (
        "A Norway landed write's independent before/after path diff must be "
        "fully accounted for by its WriteReceipt; strict replay rejects a "
        "violation instead of allowing contradictory receipt evidence."
    ),
    "no_receipt_storage_path_resolution": (
        "A chapter-free Norway legal address was resolved to its exact nested IR "
        "storage path; the receipt preserves the nominal binding and records the "
        "resolved path as landed reality without widening target resolution."
    ),
    "no_replace_missing_last_item_append_to_parent": (
        "Detail rule id on an insert-recovery of a missing-target replace that "
        "appended an item to the parent — names the specific replace→insert "
        "recovery contract on the last item slot."
    ),
    "no_replace_missing_section_insert": (
        "Detail rule id on an insert-recovery of a missing-target replace that "
        "inserted a section at the inferred parent — names the specific "
        "replace→insert recovery contract at section granularity."
    ),
    "no_replace_missing_sentence_append_to_resolved_parent": (
        "Detail rule id on an insert-recovery of a missing-target replace that "
        "inserted a sentence into a resolved parent — names the specific "
        "replace→insert recovery contract at sentence granularity."
    ),
    "no_replace_missing_sentence_append_to_shallow_host": (
        "Detail rule id on an insert-recovery of a missing-target replace that "
        "inserted a sentence into a shallow host — names the specific "
        "replace→insert recovery contract at sentence granularity on a shallow "
        "host."
    ),
    # --- Comparison normalization (verify.compare surface) ---------------------
    "no_compare_nbsp": (
        "Norway comparison text projects non-breaking spaces to ordinary spaces "
        "so equivalent wording is not flagged as a divergence."
    ),
    "no_compare_whitespace_collapse": (
        "Norway comparison text collapses whitespace runs so equivalent wording "
        "is not flagged as a divergence."
    ),
    "no_compare_punctuation_spacing": (
        "Norway comparison text removes spaces before punctuation so equivalent "
        "wording is not flagged as a divergence."
    ),
    "no_compare_open_paren_spacing": (
        "Norway comparison text removes spaces after opening parenthesis so "
        "equivalent wording is not flagged as a divergence."
    ),
    "no_compare_close_paren_spacing": (
        "Norway comparison text removes spaces before a closing parenthesis so "
        "equivalent wording is not flagged as a divergence."
    ),
    "no_compare_inline_footnote_marker": (
        "Norway comparison text removes a single-digit footnote marker attached "
        "to a lowercase-initial word inside a sentence so equivalent wording is "
        "not flagged as a divergence; structural numbering (\"Kapittel 2 …\") is "
        "left intact because deleting it on both sides would mask real "
        "divergences (findings-ledger F-05 / W-16)."
    ),
    "no_compare_standalone_footnote_marker": (
        "Norway comparison text removes standalone numeric footnote markers after "
        "punctuation so equivalent wording is not flagged as a divergence."
    ),
    "no_compare_numeric_hyphen_gap": (
        "Norway comparison text closes a spacing gap before a hyphen after a "
        "digit so equivalent wording is not flagged as a divergence."
    ),
    "no_compare_other_laws_placeholder_dash_tail": (
        "Norway comparison text suppresses pure dash tails inside other-laws "
        "placeholder clauses so the placeholder is not flagged as a divergence."
    ),
    "no_compare_trailing_footnote_marker": (
        "Norway comparison text removes trailing numeric footnote markers after "
        "terminal punctuation so equivalent wording is not flagged as a "
        "divergence."
    ),
    # --- Verify projections (no_verify.* — emitted by NOCompareProjection) ------
    "no_verify.compare_repealed_shell_blanked": (
        "A Norway proforma 'repealed-shell' provision (archived text body for a "
        "repealed section) is blanked on the compare surface so the archived "
        "shell is not a divergence against the live text."
    ),
    "no_verify.compare_sentence_children_collapsed": (
        "Norway comparison collapses a parent's sentence children into the parent "
        "for the compare surface so a folded presentation is not a divergence."
    ),
    "no_verify.compare_nested_item_tail_suppressed": (
        "Norway comparison suppresses a nested item tail where replay and current "
        "diverge only in trailing container membership."
    ),
    "no_verify.compare_self_section_shell_blanked": (
        "A Norway proforma 'self-section shell' (cited section reference "
        "placeholder body) is blanked on the compare surface."
    ),
    "no_verify.compare_contingent_other_laws_placeholder_suppressed": (
        "A Norway contingent 'Kongen bestemmer' other-laws placeholder is "
        "suppressed on the compare surface because its content is not yet "
        "deterministically replayable."
    ),
    "no_verify.compare_definition_subsection_pairs_collapsed": (
        "Norway comparison collapses paired definition subsections whose "
        "replay-vs-current divergence is presentation-only."
    ),
    "no_verify.compare_other_laws_context_suppressed": (
        "Norway comparison suppresses other-laws contextual boilerplate that is "
        "not deterministically replayable."
    ),
    "no_verify.chapter_relocation_pair": (
        "Two divergences whose text matches at different chapter paths are "
        "paired as a chapter relocation, suppressed on the primary surface and "
        "recorded as a single relocation finding rather than two mismatches."
    ),
    "no_verify.annex_prefixed_relocation_pair": (
        "Two divergences whose text matches at non-container paths whose "
        "only difference is a Lovdata Vedlegg-annex-token prefix on the "
        "section label (e.g. chapter:v22c/section:v22c/a1 vs chapter:1/"
        "section:a1) are paired as an annex-encoded relocation and "
        "suppressed on the primary surface, recorded as a single filtered "
        "relocation receipt rather than two mismatches. Distinct from "
        "no_verify.chapter_relocation_pair, which pairs provisionally-"
        "relocated provisions whose section labels match exactly."
    ),
    # The three label lexers the annexed-instrument ceiling is built from.
    # Bounded structural matchers over an address LABEL (never over prose), so
    # they carry no legal claim of their own — they are cataloged because
    # ``compile_classifier_regex``'s ``classifier_id`` is statically
    # discoverable, and the shape each one accepts is the load-bearing part.
    "no_verify.annex_body_chapter_label": (
        "Recognizes an ORDINARY Norwegian legislative chapter label — decimal "
        "(3, 10a) or roman (IV). A top-level chapter label that fails this "
        "match is Lovdata's annex token for an incorporated instrument, which "
        "is how the annexed-instrument ceiling tells an annex chapter from the "
        "enacting law's own body."
    ),
    "no_verify.annex_article_label": (
        "Recognizes an annexed instrument's article label as Lovdata addresses "
        "it (a1 … a99). Norwegian section labels never take this form (they "
        "are 11, 11a, 3-3c), so the shape separates an instrument article from "
        "a section of the enacting law."
    ),
    "no_verify.annex_section_token": (
        "Recognizes the annex token when it prefixes an article label "
        "(the gdpr in gdpr/a1, the v22c in v22c/a80). Split off from the "
        "article label with a one-shot partition so no optional prefix group "
        "wraps a quantifier."
    ),
    "no_verify.ceiling_annexed_instrument_address": (
        "A Norway divergence whose address sits inside a Lovdata annex chapter "
        "carrying an incorporated international instrument (the chapter label "
        "is the annex token and the section label is that token plus an "
        "instrument article, e.g. chapter:gdpr/section:gdpr/a1) is typed as "
        "the annexed-instrument representation ceiling: the consolidation "
        "prints the instrument in full and the original-act replay lane never "
        "had it. The row is NOT suppressed — it stays a counted divergence "
        "and the verdict is unchanged; the receipt only lets the scoreboard "
        "report annex and non-annex divergences separately."
    ),
    "no_verify.ceiling_annexed_instrument_nested_address": (
        "A Norway divergence whose address sits inside a Lovdata annex that is "
        "addressed as a compound SUB-CHAPTER of an ordinary host chapter "
        "rather than by a token chapter of its own (chapter:1 holding "
        "chapter:1-1, then an unprefixed instrument article such as "
        "section:a1) is typed as the annexed-instrument representation "
        "ceiling, the same ceiling as its token-encoded sibling: the "
        "consolidation prints the incorporated instrument in full and the "
        "original-act replay lane never had it. Disjoint from that sibling by "
        "construction — it requires a non-ordinary top chapter label, this "
        "one requires an ordinary one. Types rather than suppresses, so the "
        "row stays counted and no verdict moves."
    ),
    "no_verify.ceiling_annexed_instrument_counterpart": (
        "A Norway present-on-one-side-only divergence at the canonical-body "
        "address of an instrument article that the SAME law also carries at "
        "an annex address (e.g. chapter:1/section:a80 against the witnessed "
        "chapter:v22c/section:v22c/a80) is typed as the counterpart half of "
        "the annexed-instrument representation ceiling: the instrument is "
        "represented twice at two addresses, so each copy reads as missing "
        "from the other side. Self-limiting — with no witnessing annex-address "
        "row for that article the rule cannot fire. Like its sibling it types "
        "rather than suppresses, so no verdict moves."
    ),
    "no_verify.prefix_descendant_suppressed": (
        "A Norway divergence whose address is a strict prefix of another raw "
        "divergence address is suppressed on the primary surface (the more "
        "specific divergence takes priority); the suppression is recorded as a "
        "filtered divergence with a receipt."
    ),
    "no_verify_source_signal_base_year_unresolved": (
        "A Norway base_id does not carry the canonical no/lov/YYYY-MM-DD-N "
        "form, so the source-signal inference cannot use an enactment year "
        "and falls through the sparse-indexed-history branch unconditionally. "
        "Recorded so the malformed base_id surfaces in verify diagnostics "
        "rather than silently behaving as 'year unknown'."
    ),
    # --- EV-05 execution-authorization proof carrier (the firewall waist) ---------------
    # Mirrors SE's ``se_affecting_act_authorizes_apply`` and EU's
    # ``eu_amending_act_authorizes_apply``. The concrete ``authorization_rule_id``
    # appends the affecting act id (``no_affecting_act:<statute>``, a per-instance
    # f-string prefix excluded from the rule-id denominator in the catalog test);
    # this constant is the rule *family* the minted proof stamps into its ``detail``.
    "no_affecting_act_authorizes_apply": (
        "A Norway op's execution authority is its source affecting act: a typed "
        "ExecutionAuthorization proof is minted from the op's affecting-act "
        "identity (``no_affecting_act:<statute>``) so the EV-05 observe gate "
        "stays quiet on authorized ops; an op with no affecting-act identity "
        "carries UNKNOWN authority and no proof is fabricated, so the gate fires "
        "honestly on the real unauthorized residue."
    ),
    # --- Per-op mutation-boundary escape observation (§1.0 in-fold twin) -----------------
    # Mirrors EE's ``ee_replay_mutation_boundary_per_op_violation_observed`` and
    # UK's ``uk_replay_mutation_boundary_per_op_violation_observed``.
    "no_replay_mutation_boundary_per_op_violation_observed": (
        "A per-op Norway write whose changed paths escape the op's declared "
        "section region is recorded as a boundary-escape observation (the in-fold "
        "twin of the apply-seam boundary witness), not silently absorbed."
    ),
}
