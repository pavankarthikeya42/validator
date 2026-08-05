"""
comparator.py — Field-by-Field Comparison Logic

Compares UI-extracted data against PDF-extracted data for every mapped field.
Returns a structured ComparisonResult per document.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Optional

from section_matcher import (
    SemanticMatcher,
    parse_blocks,
    unmatched_pdf_blocks,
    validate_section,
)


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
class TableRowResult:
    row_index: int
    status: FieldStatus
    ui_row: list[str]
    pdf_row: list[str]


@dataclass
class TableResult:
    table_name: str
    status: FieldStatus
    row_results: list[TableRowResult] = field(default_factory=list)


@dataclass
class ComparisonResult:
    doc_id: str
    doc_index: int
    fields: list[FieldResult] = field(default_factory=list)
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    tables: list[TableResult] = field(default_factory=list)

    # Computed properties
    @property
    def total_fields(self) -> int:
        field_count = len([f for f in self.fields if f.status != FieldStatus.SKIPPED])
        table_count = sum(len(t.row_results) for t in self.tables)
        return field_count + table_count

    @property
    def matches(self) -> int:
        f_match = sum(1 for f in self.fields if f.status == FieldStatus.MATCH)
        t_match = sum(sum(1 for r in t.row_results if r.status == FieldStatus.MATCH) for t in self.tables)
        return f_match + t_match

    @property
    def mismatches(self) -> int:
        f_mis = sum(1 for f in self.fields if f.status == FieldStatus.MISMATCH)
        t_mis = sum(sum(1 for r in t.row_results if r.status == FieldStatus.MISMATCH) for t in self.tables)
        return f_mis + t_mis

    @property
    def missing_in_pdf(self) -> int:
        f_miss = sum(1 for f in self.fields if f.status == FieldStatus.MISSING_IN_PDF)
        t_miss = sum(sum(1 for r in t.row_results if r.status == FieldStatus.MISSING_IN_PDF) for t in self.tables)
        # Also add tables entirely missing
        t_miss += sum(1 for t in self.tables if t.status == FieldStatus.MISSING_IN_PDF)
        return f_miss + t_miss

    @property
    def missing_in_ui(self) -> int:
        f_miss = sum(1 for f in self.fields if f.status == FieldStatus.MISSING_IN_UI)
        t_miss = sum(sum(1 for r in t.row_results if r.status == FieldStatus.MISSING_IN_UI) for t in self.tables)
        return f_miss + t_miss

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
            "tables": [
                {
                    "table_name": t.table_name,
                    "status": t.status.value,
                    "row_results": [
                        {
                            "row_index": r.row_index,
                            "status": r.status.value,
                            "ui_row": r.ui_row,
                            "pdf_row": r.pdf_row,
                        }
                        for r in t.row_results
                    ]
                }
                for t in self.tables
            ]
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

        validation = config.get("validation") or {}
        self._section_validation: bool = validation.get("section_matching", True)
        self._threshold: float = float(validation.get("match_threshold", 0.85))
        self._semantic_threshold: float = float(
            validation.get("semantic_threshold", 0.75)
        )
        self._semantic_sections: list[str] = [
            s.lower() for s in validation.get("semantic_sections", ["Metadata", "Indication"])
        ]
        self._semantic = SemanticMatcher(
            validation.get("semantic_model", "all-MiniLM-L6-v2")
        )

    def _is_semantic(self, section: str) -> bool:
        name = section.lower()
        return any(s in name for s in self._semantic_sections)

    def compare_sections(
        self, doc_id: str, doc_index: int, ui_data: dict[str, str], pdf_raw: str
    ) -> ComparisonResult:
        """
        Heading-anchored validation.

        Each UI section is anchored to the PDF by the heading it starts with,
        and only the text under that heading is compared. Sections listed in
        `validation.semantic_sections` are compared by meaning instead.
        """
        result = ComparisonResult(doc_id=doc_id, doc_index=doc_index)
        pdf_blocks = parse_blocks(pdf_raw)
        section_results = []

        grouped: dict[str, list[str]] = {}
        for ui_path, ui_val in ui_data.items():
            if ui_path.startswith("__") or not (ui_val or "").strip():
                continue
            grouped.setdefault(ui_path.split(">")[0].strip(), []).append(ui_val.strip())

        for section, values in grouped.items():
            ui_val = "\n".join(values)
            semantic = self._is_semantic(section)
            section_res = validate_section(
                section=section,
                ui_text=ui_val,
                pdf_blocks=pdf_blocks,
                pdf_raw=pdf_raw,
                threshold=self._semantic_threshold if semantic else self._threshold,
                semantic=semantic,
                matcher=self._semantic,
            )
            section_results.append(section_res)
            for block in section_res.blocks:
                result.fields.append(
                    FieldResult(
                        field_path=f"{section} > {block.heading}",
                        ui_value=block.ui_text,
                        pdf_value=block.pdf_text or None,
                        status=FieldStatus(block.status),
                        normalised_ui=f"similarity={block.similarity:.2f}",
                        normalised_pdf="semantic" if block.semantic else "literal",
                    )
                )

        for block in unmatched_pdf_blocks(pdf_blocks, section_results):
            result.fields.append(
                FieldResult(
                    field_path=block.heading,
                    ui_value=None,
                    pdf_value=block.body,
                    status=FieldStatus.MISSING_IN_UI,
                )
            )

        return result

    def compare(
        self,
        doc_id: str,
        doc_index: int,
        ui_data: dict[str, str],
        pdf_data: dict[str, str],
        ui_tables: list[dict] = None,
        pdf_tables: list[list[list[str]]] = None,
    ) -> ComparisonResult:
        if self._section_validation and not self._mappings:
            raw = pdf_data.get("__raw__", "")
            if raw:
                return self.compare_sections(doc_id, doc_index, ui_data, raw)

        result = ComparisonResult(doc_id=doc_id, doc_index=doc_index)

        ui_tables = ui_tables or []
        pdf_tables = pdf_tables or []

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

                if not pdf_val and raw_pdf_text and field_name and len(field_name) > 3 and field_name != "Content":
                    # 1. Search raw PDF text for field_name label
                    pattern = re.escape(field_name) + r"[\s:\-]*([^\n\r]{1,150})"
                    match = re.search(pattern, raw_pdf_text, re.IGNORECASE)
                    if match:
                        pdf_val = match.group(1).strip()
                
                ui_present = ui_val is not None and ui_val.strip() != ""
                
                def is_fuzzy_match(u_text, p_text):
                    if not u_text or not p_text: return False
                    n_u = _normalise(u_text)
                    n_p = _normalise(p_text)
                    if len(n_u) > 5 and n_u in n_p: return True
                    if len(n_u) > 0 and len(n_u) <= 5:
                        return bool(re.search(r'\b' + re.escape(n_u) + r'\b', n_p))
                    
                    # For very large texts, headers/footers in the PDF interrupt the text.
                    # We chunk the normalized UI text and ensure a high percentage of chunks exist in the PDF.
                    chunk_size = 50
                    if len(n_u) > chunk_size:
                        chunks = [n_u[i:i+chunk_size] for i in range(0, len(n_u), chunk_size)]
                        matches = sum(1 for c in chunks if c in n_p)
                        if matches / len(chunks) >= 0.7:  # 70% of chunks match perfectly
                            return True
                    return False

                if not pdf_val and ui_present:
                    # 2. If it's a content section (or value wasn't found by label), just check if the UI value exists anywhere in the PDF!
                    if is_fuzzy_match(ui_val, raw_pdf_text):
                        pdf_val = ui_val # Long text exists perfectly (or close enough), treat as match!

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
                    
                    # Also use fuzzy match for the final status check if they are explicitly mapped
                    status = FieldStatus.MATCH if (
                        norm_ui == norm_pdf or 
                        norm_ui in norm_pdf or 
                        norm_pdf in norm_ui or 
                        is_fuzzy_match(ui_val, pdf_val)
                    ) else FieldStatus.MISMATCH
                    
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

        # 3. Table Comparison
        for ui_table in ui_tables:
            table_name = ui_table["name"]
            pdf_idx = ui_table["pdf_table_index"]
            normalise = ui_table["normalise"]
            ui_rows = ui_table["ui_data"]
            
            table_res = TableResult(table_name=table_name, status=FieldStatus.MATCH)
            
            if pdf_idx >= len(pdf_tables):
                table_res.status = FieldStatus.MISSING_IN_PDF
                result.tables.append(table_res)
                continue
                
            pdf_rows = pdf_tables[pdf_idx]
            
            # Compare rows up to the max length
            max_rows = max(len(ui_rows), len(pdf_rows))
            for i in range(max_rows):
                u_row = ui_rows[i] if i < len(ui_rows) else []
                p_row = pdf_rows[i] if i < len(pdf_rows) else []
                
                if not u_row and p_row:
                    row_status = FieldStatus.MISSING_IN_UI
                elif u_row and not p_row:
                    row_status = FieldStatus.MISSING_IN_PDF
                else:
                    row_status = FieldStatus.MATCH
                    # Simple cell-by-cell comparison
                    max_cells = max(len(u_row), len(p_row))
                    for j in range(max_cells):
                        u_cell = u_row[j] if j < len(u_row) else ""
                        p_cell = p_row[j] if j < len(p_row) else ""
                        
                        if normalise:
                            if _normalise(u_cell) != _normalise(p_cell):
                                row_status = FieldStatus.MISMATCH
                                break
                        else:
                            if u_cell.strip() != p_cell.strip():
                                row_status = FieldStatus.MISMATCH
                                break
                                
                table_res.row_results.append(TableRowResult(
                    row_index=i, status=row_status, ui_row=u_row, pdf_row=p_row
                ))
                if row_status != FieldStatus.MATCH:
                    table_res.status = FieldStatus.MISMATCH
                    
            result.tables.append(table_res)

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
