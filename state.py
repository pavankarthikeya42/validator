"""
state.py — Checkpoint / Resume Manager

Persists progress to state.json after every successfully validated document.
Re-running with --resume picks up exactly where the tool left off.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


STATE_FILE = Path("state.json")


@dataclass
class RunState:
    total_documents: int = 0
    last_completed_index: int = -1          # -1 means not started
    last_completed_doc_id: str = ""
    failed_indices: list[int] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    run_id: str = ""                        # timestamp-based unique run ID

    # Cumulative counters (kept in state so resume is accurate in reports)
    total_fields_validated: int = 0
    total_matches: int = 0
    total_mismatches: int = 0
    total_missing: int = 0
    total_failed_docs: int = 0

    def save(self) -> None:
        """Atomically write state to disk."""
        tmp = STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        tmp.replace(STATE_FILE)

    @classmethod
    def load(cls) -> "RunState":
        """Load existing state from disk, or return a fresh instance."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, encoding="utf-8") as fh:
                    data = json.load(fh)
                return cls(**data)
            except (json.JSONDecodeError, TypeError):
                pass
        return cls(run_id=_new_run_id())

    def is_resumable(self) -> bool:
        return STATE_FILE.exists() and self.last_completed_index >= 0

    def mark_completed(self, index: int, doc_id: str, result_summary: dict) -> None:
        self.last_completed_index = index
        self.last_completed_doc_id = doc_id
        self.total_fields_validated += result_summary.get("fields_validated", 0)
        self.total_matches += result_summary.get("matches", 0)
        self.total_mismatches += result_summary.get("mismatches", 0)
        self.total_missing += result_summary.get("missing", 0)
        self.save()

    def mark_failed(self, index: int) -> None:
        if index not in self.failed_indices:
            self.failed_indices.append(index)
        self.total_failed_docs = len(self.failed_indices)
        self.save()

    def reset(self) -> None:
        """Clear state for a fresh run."""
        if STATE_FILE.exists():
            STATE_FILE.unlink()

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def success_rate(self) -> float:
        processed = self.last_completed_index + 1
        if processed == 0:
            return 0.0
        failed = len(self.failed_indices)
        return round((processed - failed) / processed * 100, 2)


def _new_run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S")
