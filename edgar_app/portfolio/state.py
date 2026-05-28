"""
portfolio/state.py
------------------
Portfolio State Engine.

Stores one state record per ticker in a JSON file:
  edgar_app/portfolio/portfolio_state.json

update_portfolio() now also runs the Delta Intelligence Engine before
saving, recording what changed from the previous state.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import date

from .delta import DeltaRecord, detect_delta, save_delta

_STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class PortfolioEntry:
    ticker:             str
    company_name:       str
    last_filing_type:   str
    thesis_status:      str     # "Strong" | "Stable" | "Weak" | "Broken"
    catalysts:          list[str]
    risks:              list[str]
    conviction_score:   int     # 0–100
    recommended_action: str     # "Buy" | "Hold" | "Reduce" | "Exit"
    last_updated:       str     # ISO date, e.g. "2026-05-28"
    analyses_count:     int = 1


# ── Load / save ───────────────────────────────────────────────────────────────

def load_portfolio() -> dict[str, PortfolioEntry]:
    """Load all entries from the JSON file. Returns {} if the file is missing."""
    if not os.path.exists(_STATE_FILE):
        return {}
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return {t: PortfolioEntry(**e) for t, e in raw.items()}


def save_portfolio(portfolio: dict[str, PortfolioEntry]) -> None:
    """Write the full portfolio to disk."""
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {t: asdict(e) for t, e in portfolio.items()},
            f, indent=2, ensure_ascii=False,
        )


# ── Update (with delta detection) ────────────────────────────────────────────

def update_portfolio(
    ticker:       str,
    company_name: str,
    analysis,           # AnalysisResult — typed loosely to avoid circular import
    filing_type:  str,
) -> tuple[PortfolioEntry, DeltaRecord]:
    """
    Compare new analysis against previous state, record the delta,
    then save the updated entry.

    Returns (updated_entry, delta_record).
    """
    portfolio = load_portfolio()
    existing  = portfolio.get(ticker.upper())    # None on first analysis
    count     = (existing.analyses_count + 1) if existing else 1

    # ── Detect what changed BEFORE overwriting the state ─────────────────────
    delta = detect_delta(existing, analysis, ticker, company_name, filing_type)
    save_delta(delta)

    # ── Build and save the new entry ──────────────────────────────────────────
    entry = PortfolioEntry(
        ticker=ticker.upper(),
        company_name=company_name,
        last_filing_type=filing_type,
        thesis_status=analysis.thesis_impact,
        catalysts=analysis.key_catalysts,
        risks=analysis.key_risks,
        conviction_score=analysis.confidence_score,
        recommended_action=analysis.suggested_action,
        last_updated=date.today().isoformat(),
        analyses_count=count,
    )
    portfolio[ticker.upper()] = entry
    save_portfolio(portfolio)
    return entry, delta


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_ticker(ticker: str) -> bool:
    """Remove a ticker from the portfolio. Returns True if it existed."""
    portfolio = load_portfolio()
    existed   = ticker.upper() in portfolio
    if existed:
        del portfolio[ticker.upper()]
        save_portfolio(portfolio)
    return existed
