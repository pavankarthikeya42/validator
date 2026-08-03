"""
tests/test_comparator.py — Unit tests for the Comparator and normalisation logic
"""
import pytest
from comparator import Comparator, FieldStatus, _normalise


# =====================================================================
# Normalisation tests
# =====================================================================

def test_normalise_whitespace():
    assert _normalise("  hello   world  ") == "hello world"

def test_normalise_case():
    assert _normalise("Invoice NUMBER") == "invoice number"

def test_normalise_date_slash():
    assert _normalise("01/12/2024") == "01-12-2024"

def test_normalise_date_iso():
    assert _normalise("2024-12-01") == "01-12-2024"

def test_normalise_currency():
    assert _normalise("$1,234.56") == "1234.56"

def test_normalise_combined():
    assert _normalise("  $1,234.56  ") == "1234.56"


# =====================================================================
# Comparator tests
# =====================================================================

CONFIG = {
    "field_mappings": [
        {"ui_path": "Section 1 > Doc Number", "pdf_regex": r"Doc#\s*(\S+)", "normalise": True},
        {"ui_path": "Section 1 > Amount",     "pdf_regex": r"Amount[:\s]+([\d,.]+)", "normalise": True},
        {"ui_path": "Section 2 > Date",        "pdf_regex": r"Date[:\s]+(\S+)", "normalise": True},
    ]
}

def make_comparator() -> Comparator:
    return Comparator(CONFIG)


def test_match():
    cmp = make_comparator()
    ui = {"Section 1 > Doc Number": "DOC-001"}
    pdf = {"Section 1 > Doc Number": "DOC-001"}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 1 > Doc Number")
    assert fr.status == FieldStatus.MATCH


def test_mismatch():
    cmp = make_comparator()
    ui = {"Section 1 > Doc Number": "DOC-001"}
    pdf = {"Section 1 > Doc Number": "DOC-002"}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 1 > Doc Number")
    assert fr.status == FieldStatus.MISMATCH


def test_missing_in_pdf():
    cmp = make_comparator()
    ui = {"Section 1 > Doc Number": "DOC-001"}
    pdf = {}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 1 > Doc Number")
    assert fr.status == FieldStatus.MISSING_IN_PDF


def test_missing_in_ui():
    cmp = make_comparator()
    ui = {}
    pdf = {"Section 1 > Doc Number": "DOC-001"}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 1 > Doc Number")
    assert fr.status == FieldStatus.MISSING_IN_UI


def test_case_insensitive_match():
    cmp = make_comparator()
    ui = {"Section 1 > Doc Number": "DOC-001"}
    pdf = {"Section 1 > Doc Number": "doc-001"}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 1 > Doc Number")
    assert fr.status == FieldStatus.MATCH


def test_currency_normalisation_match():
    cmp = make_comparator()
    ui = {"Section 1 > Amount": "$1,234.56"}
    pdf = {"Section 1 > Amount": "1234.56"}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 1 > Amount")
    assert fr.status == FieldStatus.MATCH


def test_date_normalisation_match():
    cmp = make_comparator()
    ui = {"Section 2 > Date": "01/12/2024"}
    pdf = {"Section 2 > Date": "2024-12-01"}
    result = cmp.compare("doc1", 0, ui, pdf)
    fr = next(f for f in result.fields if f.field_path == "Section 2 > Date")
    assert fr.status == FieldStatus.MATCH


def test_summary_counts():
    cmp = make_comparator()
    ui = {
        "Section 1 > Doc Number": "DOC-001",
        "Section 1 > Amount": "$500.00",
        # Section 2 > Date intentionally missing from UI
    }
    pdf = {
        "Section 1 > Doc Number": "DOC-999",   # mismatch
        "Section 1 > Amount": "500.00",          # match after normalise
        "Section 2 > Date": "2024-01-15",        # missing in UI
    }
    result = cmp.compare("doc1", 0, ui, pdf)
    assert result.mismatches == 1
    assert result.matches == 1
    assert result.missing_in_ui == 1


def test_extra_pdf_field_marked_skipped():
    cmp = make_comparator()
    ui = {"Section 1 > Doc Number": "DOC-001"}
    pdf = {
        "Section 1 > Doc Number": "DOC-001",
        "Unmapped Field": "extra value",         # not in mappings
    }
    result = cmp.compare("doc1", 0, ui, pdf)
    skipped = [f for f in result.fields if f.status == FieldStatus.SKIPPED]
    assert any(f.field_path == "Unmapped Field" for f in skipped)
