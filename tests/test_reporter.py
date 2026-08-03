"""
tests/test_reporter.py — Unit tests for the Reporter (output file generation)
"""
import json
import csv
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from comparator import ComparisonResult, FieldResult, FieldStatus
from reporter import Reporter
from state import RunState


@pytest.fixture
def tmp_report_dir(tmp_path):
    return str(tmp_path / "reports")


@pytest.fixture
def config(tmp_report_dir):
    return {
        "output": {
            "directory": tmp_report_dir,
            "screenshots_dir": f"{tmp_report_dir}/screenshots",
            "json_report": "results.json",
            "csv_report": "results.csv",
            "html_report": "report.html",
            "excel_report": "results.xlsx",
        },
        "field_mappings": [],
    }


@pytest.fixture
def sample_state():
    state = RunState()
    state.run_id = "test_run"
    return state


@pytest.fixture
def sample_results():
    r1 = ComparisonResult(doc_id="DOC-001", doc_index=0)
    r1.fields = [
        FieldResult("Sec > Field A", "val1", "val1", FieldStatus.MATCH),
        FieldResult("Sec > Field B", "valX", "valY", FieldStatus.MISMATCH),
        FieldResult("Sec > Field C", "val3", None, FieldStatus.MISSING_IN_PDF),
    ]
    r2 = ComparisonResult(doc_id="DOC-002", doc_index=1, error="Timeout")
    return [r1, r2]


def test_json_report_created(config, sample_state, sample_results, tmp_report_dir):
    reporter = Reporter(config, sample_state)
    for r in sample_results:
        reporter.add_result(r)
    reporter.save_all()

    json_path = Path(tmp_report_dir) / "results.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert "summary" in data
    assert "documents" in data
    assert len(data["documents"]) == 2


def test_csv_report_created(config, sample_state, sample_results, tmp_report_dir):
    reporter = Reporter(config, sample_state)
    for r in sample_results:
        reporter.add_result(r)
    reporter.save_all()

    csv_path = Path(tmp_report_dir) / "results.csv"
    assert csv_path.exists()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    # r1 has 3 fields, r2 has error (0 fields)
    assert len(rows) == 3


def test_excel_report_created(config, sample_state, sample_results, tmp_report_dir):
    reporter = Reporter(config, sample_state)
    for r in sample_results:
        reporter.add_result(r)
    reporter.save_all()

    xlsx_path = Path(tmp_report_dir) / "results.xlsx"
    assert xlsx_path.exists()


def test_html_report_created(config, sample_state, sample_results, tmp_report_dir):
    reporter = Reporter(config, sample_state)
    for r in sample_results:
        reporter.add_result(r)
    reporter.save_all()

    html_path = Path(tmp_report_dir) / "report.html"
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")
    assert "DOC-001" in content
    assert "MISMATCH" in content


def test_summary_counts(config, sample_state, sample_results):
    reporter = Reporter(config, sample_state)
    for r in sample_results:
        reporter.add_result(r)
    summary = reporter.build_summary()
    assert summary["total_documents_processed"] == 2
    assert summary["total_matches"] == 1
    assert summary["total_mismatches"] == 1
    assert summary["total_missing_fields"] == 1
    assert summary["total_failed_documents"] == 1
