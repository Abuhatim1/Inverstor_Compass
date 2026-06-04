"""
portfolio/comparison_store.py
------------------------------
Persists FilingComparison results as ComparisonRecord objects so the
"Historical Delta Analysis" dashboard has data to display.

File: edgar_app/portfolio/comparison_history.json
      (list, newest first, max 50 records)
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime

import streamlit as st

_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "comparison_history.json")
_MAX_HISTORY  = 50


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class ComparisonRecord:
    ticker:       str
    company_name: str
    filing_type:  str
    accession:    str    # current filing's accession number
    timestamp:    str    # ISO datetime

    # Four narrative sections
    what_improved:  list[str]
    what_weakened:  list[str]
    new_concerns:   list[str]
    new_catalysts:  list[str]

    # Seven trend fields
    revenue_growth_trend: str
    margin_trend:         str
    cash_trend:           str
    debt_trend:           str
    management_tone:      str
    guidance_trend:       str

    conviction_adjustment: int


# ── Trend display helpers (used by app.py) ────────────────────────────────────

TREND_ICON = {
    "improving": "📈",
    "stable":    "➡️",
    "declining": "📉",
}

TONE_ICON = {
    "positive": "😊",
    "neutral":  "😐",
    "cautious": "😟",
    "negative": "😨",
}

GUIDANCE_ICON = {
    "raised":        "⬆️",
    "maintained":    "➡️",
    "lowered":       "⬇️",
    "withdrawn":     "❌",
    "not_mentioned": "—",
}


# ── Load / save ───────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_comparison_history() -> list[ComparisonRecord]:
    """Load all records from disk. Returns [] if file is missing."""
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [ComparisonRecord(**r) for r in raw]
    except (json.JSONDecodeError, OSError, TypeError):
        return []


def save_comparison(record: ComparisonRecord) -> None:
    """Prepend a new record; evict oldest beyond _MAX_HISTORY."""
    history = load_comparison_history()
    history.insert(0, record)
    history = history[:_MAX_HISTORY]
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in history], f, indent=2, ensure_ascii=False)
    load_comparison_history.clear()


def build_comparison_record(
    ticker:       str,
    company_name: str,
    filing_type:  str,
    accession:    str,
    comparison,              # FilingComparison — typed loosely to avoid circular import
) -> ComparisonRecord:
    """Convenience constructor from a FilingComparison."""
    return ComparisonRecord(
        ticker=ticker.upper(),
        company_name=company_name,
        filing_type=filing_type,
        accession=accession,
        timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        what_improved=comparison.what_improved,
        what_weakened=comparison.what_weakened,
        new_concerns=comparison.new_concerns,
        new_catalysts=comparison.new_catalysts,
        revenue_growth_trend=comparison.revenue_growth_trend,
        margin_trend=comparison.margin_trend,
        cash_trend=comparison.cash_trend,
        debt_trend=comparison.debt_trend,
        management_tone=comparison.management_tone,
        guidance_trend=comparison.guidance_trend,
        conviction_adjustment=comparison.conviction_adjustment,
    )
