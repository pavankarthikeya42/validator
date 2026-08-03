"""
comparator.py — Field-by-Field Comparison Logic

Compares UI-extracted data against PDF-extracted data for every mapped field.
Returns a structured ComparisonResult per document.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FieldStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MISSING_IN_PDF = "MISSING_IN_PDF"
    MISSING_IN_UI = "MISSING_IN_UI"
    SKIPPED = "SKIPPED"         # field not in mappings list (extra)


@dataclass
class FieldResult:
    field_path: str             # e.g. "Section 1 > Document Number"
    ui_value: Optional[str]
    pdf_value: Optional[str]
    status: FieldStatus
    normalised_ui: Optional[str] = None
    normalised_pdf: Optional[str] = None
    screenshot_path: Optional[str] = None


@dataclass
class ComparisonResult:
    doc_id: str
    doc_index: int
    fields: list[FieldResult] = field(default_factory=list)
    error: Optional[str] = None
    screenshot_path: Optional[str] = None

    # Computed properties
    @property
    def total_fields(self) -> int:
        return len([f for f in self.fields if f.status != FieldStatus.SKIPPED])

    @property
    def matches(self) -> int:
        return sum(1 for f in self.fields if f.status == FieldStatus.MATCH)

    @property
    def mismatches(self) -> int:
        return sum(1 for f in self.fields if f.status == FieldStatus.MISMATCH)

    @property
    def missing_in_pdf(self) -> int:
        return sum(1 for f in self.fields if f.status == FieldStatus.MISSING_IN_PDF)

    @property
    def missing_in_ui(self) -> int:
        return sum(1 for f in self.fields if f.status == FieldStatus.MISSING_IN_UI)

    @property
    def has_mismatches(self) -> bool:
        return self.mismatches > 0 or self.missing_in_pdf > 0 or self.missing_in_ui > 0

    def summary_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "doc_index": self.doc_index,
            "fields_validated": self.total_fields,
            "matches": self.matches,
            "mismatches": self.mismatches,
            "missing_in_pdf": self.missing_in_pdf,
            "missing_in_ui": self.missing_in_ui,
            "error": self.error,
            "screenshot_path": self.screenshot_path,
            "fields": [
                {
                    "field": f.field_path,
                    "ui_value": f.ui_value,
                    "pdf_value": f.pdf_value,
                    "status": f.status.value,
                    "screenshot": f.screenshot_path,
                }
                for f in self.fields
            ],
        }


class Comparator:
    """
    Compares UI data against PDF data using the configured field_mappings.

    Normalisation (when mapping.normalise is True):
      - Lowercase
      - Collapse whitespace
      - Strip trailing/leading punctuation
      - Normalise date formats (DD/MM/YYYY ↔ DD-MM-YYYY ↔ YYYY-MM-DD)
      - Normalise currency (remove $ , symbols)
    """

    def __init__(self, config: dict) -> None:
        self.cfg = config
        self._mappings: list[dict] = config.get("field_mappings", [])

    def compare(
        self,
        doc_id: str,
        doc_index: int,
        ui_data: dict[str, str],
        pdf_data: dict[str, str],
    ) -> ComparisonResult:
        result = ComparisonResult(doc_id=doc_id, doc_index=doc_index)

    def compare(
        self,
        doc_id: str,
        doc_index: int,
        ui_data: dict[str, str],
        pdf_data: dict[str, str],
    ) -> ComparisonResult:
        result = ComparisonResult(doc_id=doc_id, doc_index=doc_index)

        # 1. Use configured mappings if valid
        valid_mappings = [
            m for m in self._mappings
            if m.get("ui_path") and m.get("ui_path") not in ("Section 1 > Document Number", "Section 2 > Invoice Date")
        ]

        if valid_mappings:
            for mapping in valid_mappings:
                ui_path = mapping.get("ui_path", "")
                should_normalise = mapping.get("normalise", True)
                ui_val: Optional[str] = ui_data.get(ui_path)
                pdf_val: Optional[str] = pdf_data.get(ui_path)

                ui_present = ui_val is not None and ui_val.strip() != ""
                pdf_present = pdf_val is not None and pdf_val.strip() != ""

                if not ui_present and not pdf_present:
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=FieldStatus.MISSING_IN_PDF))
                elif ui_present and not pdf_present:
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=FieldStatus.MISSING_IN_PDF))
                elif not ui_present and pdf_present:
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=FieldStatus.MISSING_IN_UI))
                else:
                    norm_ui = _normalise(ui_val) if should_normalise else ui_val.strip()
                    norm_pdf = _normalise(pdf_val) if should_normalise else pdf_val.strip()
                    status = FieldStatus.MATCH if norm_ui == norm_pdf else FieldStatus.MISMATCH
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=status, normalised_ui=norm_ui, normalised_pdf=norm_pdf))
        else:
            # 2. AUTO-MATCH: Automatically map all extracted UI keys to PDF
            raw_pdf_text = pdf_data.get("__raw__", "") or " ".join(f"{k} {v}" for k, v in pdf_data.items() if not k.startswith("__"))

            for ui_path, ui_val in ui_data.items():
                if ui_path.startswith("__"):
                    continue

                # Extract pure field label (after '>')
                field_name = ui_path.split(">")[-1].strip() if ">" in ui_path else ui_path.strip()
                pdf_val = pdf_data.get(ui_path)

                if not pdf_val and raw_pdf_text and field_name:
                    # Search raw PDF text for field_name
                    pattern = re.escape(field_name) + r"[\s:\-]*([^\n\r,;]{1,60})"
                    match = re.search(pattern, raw_pdf_text, re.IGNORECASE)
                    if match:
                        pdf_val = match.group(1).strip()

                ui_present = ui_val is not None and ui_val.strip() != ""
                pdf_present = pdf_val is not None and pdf_val.strip() != ""

                if not ui_present and not pdf_present:
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=FieldStatus.MISSING_IN_PDF))
                elif ui_present and not pdf_present:
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=FieldStatus.MISSING_IN_PDF))
                elif not ui_present and pdf_present:
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=FieldStatus.MISSING_IN_UI))
                else:
                    norm_ui = _normalise(ui_val)
                    norm_pdf = _normalise(pdf_val)
                    status = FieldStatus.MATCH if (norm_ui == norm_pdf or norm_ui in norm_pdf or norm_pdf in norm_ui) else FieldStatus.MISMATCH
                    result.fields.append(FieldResult(field_path=ui_path, ui_value=ui_val, pdf_value=pdf_val, status=status, normalised_ui=norm_ui, normalised_pdf=norm_pdf))

        # Detect extra fields in PDF that are not mapped
        mapped_paths = {f.field_path for f in result.fields}
        for pdf_key in pdf_data:
            if pdf_key.startswith("__"):
                continue
            if pdf_key not in mapped_paths:
                result.fields.append(
                    FieldResult(
                        field_path=pdf_key,
                        ui_value=None,
                        pdf_value=pdf_data[pdf_key],
                        status=FieldStatus.SKIPPED,
                    )
                )

        return result


# ------------------------------------------------------------------
# Normalisation helpers
# ------------------------------------------------------------------

_DATE_PATTERNS = [
    # Match DD/MM/YYYY, DD-MM-YYYY, MM/DD/YYYY, YYYY-MM-DD
    (re.compile(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})"), r"\1-\2-\3"),
    (re.compile(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})"), r"\3-\2-\1"),
]

_CURRENCY_RE = re.compile(r"[$£€,]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalise(value: str) -> str:
    """Apply all normalisation rules to a value string."""
    v = value.strip()
    # Currency
    v = _CURRENCY_RE.sub("", v)
    # Dates → DD-MM-YYYY
    for pattern, repl in _DATE_PATTERNS:
        v = pattern.sub(repl, v)
    # Whitespace
    v = _WHITESPACE_RE.sub(" ", v).strip()
    # Case
    v = v.lower()
    return v
