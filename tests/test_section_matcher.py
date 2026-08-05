"""
tests/test_section_matcher.py — Heading-anchored section validation
"""
from comparator import Comparator, FieldStatus
from section_matcher import canonical, parse_blocks, text_similarity, validate_section

PDF_TEXT = """
1. Executive Summary
The product demonstrated a favourable benefit risk profile.
1.1 Scope
Covers all studies completed in 2024.
2. Clinical Overview
No new safety signals were identified.
2.3 Executive Summary
A nested summary repeated for the paediatric population.
"""

CONFIG = {"validation": {"match_threshold": 0.85, "semantic_sections": ["Metadata"]}}


def test_parse_blocks_numbers_and_titles():
    blocks = parse_blocks(PDF_TEXT)
    assert [b.number for b in blocks] == ["1", "1.1", "2", "2.3"]
    assert blocks[0].title == "Executive Summary"
    assert blocks[3].level == 2


def test_parse_blocks_body_stops_at_next_heading():
    blocks = parse_blocks(PDF_TEXT)
    assert blocks[0].body == "The product demonstrated a favourable benefit risk profile."


def test_canonical_strips_punctuation_and_case():
    assert canonical("  Benefit-Risk:  Profile ") == "benefit risk profile"


def test_text_similarity_identical():
    assert text_similarity("Hello world", "hello   world!") == 1.0


def test_text_similarity_unrelated():
    assert text_similarity("alpha beta gamma", "nothing alike here") < 0.85


def test_section_matches_under_its_heading():
    ui = "1. Executive Summary The product demonstrated a favourable benefit risk profile."
    res = validate_section("Executive Summary", ui, parse_blocks(PDF_TEXT), PDF_TEXT, 0.85)
    assert [b.status for b in res.blocks] == ["MATCH"]


def test_section_with_nested_heading_validates_both_blocks():
    ui = (
        "2. Clinical Overview No new safety signals were identified. "
        "2.3 Executive Summary A nested summary repeated for the paediatric population."
    )
    res = validate_section("Clinical Overview", ui, parse_blocks(PDF_TEXT), PDF_TEXT, 0.85)
    assert [b.heading for b in res.blocks] == ["2 Clinical Overview", "2.3 Executive Summary"]
    assert all(b.status == "MATCH" for b in res.blocks)


def test_body_under_correct_heading_but_wrong_text_is_mismatch():
    ui = "1. Executive Summary The product showed an unfavourable profile in all studies."
    res = validate_section("Executive Summary", ui, parse_blocks(PDF_TEXT), PDF_TEXT, 0.85)
    assert res.blocks[0].status == "MISMATCH"


def test_heading_absent_from_pdf_is_missing_in_pdf():
    ui = "9. Appendix Additional supporting tables."
    res = validate_section("Appendix", ui, parse_blocks(PDF_TEXT), PDF_TEXT, 0.85)
    assert res.blocks[0].status == "MISSING_IN_PDF"


def test_comparator_uses_section_matching_and_flags_unmatched_pdf_headings():
    cmp = Comparator(CONFIG)
    ui = {
        "Executive Summary > Content": (
            "1. Executive Summary The product demonstrated a favourable benefit risk profile."
        )
    }
    res = cmp.compare("doc1", 0, ui, {"__raw__": PDF_TEXT})
    statuses = {f.field_path: f.status for f in res.fields}
    assert statuses["Executive Summary > 1 Executive Summary"] == FieldStatus.MATCH
    assert statuses["2 Clinical Overview"] == FieldStatus.MISSING_IN_UI


def test_semantic_section_ignores_heading_anchoring():
    cmp = Comparator(CONFIG)
    ui = {"Metadata > Content": "No new safety signals were identified."}
    res = cmp.compare("doc1", 0, ui, {"__raw__": PDF_TEXT})
    metadata = next(f for f in res.fields if f.field_path.startswith("Metadata"))
    assert metadata.status == FieldStatus.MATCH
    assert metadata.normalised_pdf == "semantic"


def test_semantic_section_falls_back_when_model_unavailable():
    cmp = Comparator(CONFIG)
    cmp._semantic._unavailable = True
    ui = {"Metadata > Content": "No new safety signals were identified."}
    res = cmp.compare("doc1", 0, ui, {"__raw__": PDF_TEXT})
    metadata = next(f for f in res.fields if f.field_path.startswith("Metadata"))
    assert metadata.status == FieldStatus.MATCH
