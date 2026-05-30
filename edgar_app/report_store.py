"""
report_store.py — Timestamped report persistence with FIFO retention.

Saves Test Runner and Punch List reports as Excel files under:
    edgar_app/reports/test_runner/   test_report_YYYY-MM-DD_HH-MM-SS.xlsx
    edgar_app/reports/punch_list/    punch_list_YYYY-MM-DD_HH-MM-SS.xlsx

Retention policy: keep the latest RETENTION files per type; delete the
oldest when a (RETENTION+1)-th file is created.  No report is ever
overwritten — each run produces a new timestamped file.
"""

from __future__ import annotations

import glob
import io
import os
from datetime import datetime

import pandas as pd

# ── Directory layout ──────────────────────────────────────────────────────────
_ROOT       = os.path.join(os.path.dirname(__file__), "reports")
_TR_DIR     = os.path.join(_ROOT, "test_runner")
_PL_DIR     = os.path.join(_ROOT, "punch_list")
RETENTION   = 3


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    os.makedirs(_TR_DIR, exist_ok=True)
    os.makedirs(_PL_DIR, exist_ok=True)


def _ts_now() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _prune(directory: str, glob_pattern: str, keep: int) -> None:
    """Delete oldest matching files so at most `keep` remain."""
    files = sorted(glob.glob(os.path.join(directory, glob_pattern)))
    while len(files) > keep:
        try:
            os.remove(files.pop(0))
        except OSError:
            pass


def _report_to_bytes(report) -> bytes:
    """Serialise a TestReport to an in-memory Excel workbook (bytes)."""
    results_rows = [
        {
            "Test ID":         r.test_id,
            "Test Name":       r.test_name,
            "Category":        r.category,
            "Status":          r.status,
            "Expected":        r.expected,
            "Actual":          r.actual,
            "Module":          r.module,
            "Severity":        r.severity,
            "Release Blocker": "Yes" if r.is_release_blocker else "No",
        }
        for r in report.results
    ]
    summary_rows = [
        {
            "Timestamp":        report.timestamp,
            "Total Tests":      report.total,
            "Passed":           report.passed,
            "Failed":           report.failed,
            "Release Blockers": report.release_blockers,
            "Release Ready":    "Yes" if report.release_ready else "No",
        }
    ]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(results_rows).to_excel(writer, sheet_name="Results",  index=False)
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary",  index=False)
    return buf.getvalue()


def _punch_list_to_bytes(report) -> bytes:
    """Serialise the punch list portion of a TestReport to Excel bytes."""
    if report.punch_list:
        rows = [
            {
                "Item ID":      p.item_id,
                "Bug Title":    p.bug_title,
                "Severity":     p.severity,
                "Status":       p.status,
                "Expected":     p.expected,
                "Actual":       p.actual,
                "Description":  p.description,
                "Repro Steps":  p.repro_steps,
            }
            for p in report.punch_list
        ]
    else:
        rows = [{"Result": "All tests passed — punch list is empty."}]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Punch List", index=False)
        pd.DataFrame([{
            "Timestamp":    report.timestamp,
            "Open Items":   len(report.punch_list),
            "Release Ready": "Yes" if report.release_ready else "No",
        }]).to_excel(writer, sheet_name="Summary", index=False)
    return buf.getvalue()


# ── Public API ────────────────────────────────────────────────────────────────

def save_test_report(report) -> str:
    """
    Save report as a timestamped Excel file.
    Prunes to RETENTION files after writing.
    Returns the absolute path of the saved file.
    """
    _ensure_dirs()
    filename = f"test_report_{_ts_now()}.xlsx"
    path = os.path.join(_TR_DIR, filename)
    with open(path, "wb") as f:
        f.write(_report_to_bytes(report))
    _prune(_TR_DIR, "test_report_*.xlsx", RETENTION)
    return path


def save_punch_list_report(report) -> str:
    """
    Save punch list as a timestamped Excel file.
    Prunes to RETENTION files after writing.
    Returns the absolute path of the saved file.
    """
    _ensure_dirs()
    filename = f"punch_list_{_ts_now()}.xlsx"
    path = os.path.join(_PL_DIR, filename)
    with open(path, "wb") as f:
        f.write(_punch_list_to_bytes(report))
    _prune(_PL_DIR, "punch_list_*.xlsx", RETENTION)
    return path


def list_test_reports(n: int = RETENTION) -> list[str]:
    """Return up to `n` most-recent test report paths (oldest-first)."""
    files = sorted(glob.glob(os.path.join(_TR_DIR, "test_report_*.xlsx")))
    return files[-n:]


def list_punch_list_reports(n: int = RETENTION) -> list[str]:
    """Return up to `n` most-recent punch list report paths (oldest-first)."""
    files = sorted(glob.glob(os.path.join(_PL_DIR, "punch_list_*.xlsx")))
    return files[-n:]


def read_bytes(path: str) -> bytes:
    """Read a stored report file and return its raw bytes."""
    with open(path, "rb") as f:
        return f.read()


def label_from_path(path: str) -> str:
    """
    Derive a human-readable label from a report filename.
    'test_report_2026-05-30_14-22-05.xlsx' → '2026-05-30 14:22:05'
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    for prefix in ("test_report_", "punch_list_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    return stem.replace("_", " ").replace("-", ":", 2)
