"""
portfolio/state.py
------------------
Portfolio State Engine.

Stores one state record per ticker in a JSON file:
  edgar_app/portfolio/portfolio_state.json

Each record tracks:
  - ticker & company name
  - last filing type analyzed
  - thesis status  (Strong / Stable / Weak / Broken)
  - catalysts list (from latest analysis)
  - risks list     (from latest analysis)
  - conviction score (0-100)
  - recommended action (Buy / Hold / Reduce / Exit)
  - last_updated date

Usage:
    from portfolio.state import load_portfolio, update_portfolio

    portfolio = load_portfolio()
    update_portfolio("AAPL", "Apple Inc.", analysis_result, "10-K")
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date


# ── Path to the JSON file (lives next to this module) ────────────────────────
_STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class PortfolioEntry:
    ticker: str
    company_name: str
    last_filing_type: str
    thesis_status: str          # "Strong" | "Stable" | "Weak" | "Broken"
    catalysts: list[str]
    risks: list[str]
    conviction_score: int       # 0–100
    recommended_action: str     # "Buy" | "Hold" | "Reduce" | "Exit"
    last_updated: str           # ISO date string, e.g. "2026-05-28"
    analyses_count: int = 1     # how many times this ticker has been analyzed


# ── Load / save ───────────────────────────────────────────────────────────────

def load_portfolio() -> dict[str, PortfolioEntry]:
    """
    Load all portfolio entries from the JSON file.
    Returns an empty dict if the file doesn't exist yet.
    """
    if not os.path.exists(_STATE_FILE):
        return {}

    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    return {
        ticker: PortfolioEntry(**entry)
        for ticker, entry in raw.items()
    }


def save_portfolio(portfolio: dict[str, PortfolioEntry]) -> None:
    """Write the full portfolio state to disk."""
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {ticker: asdict(entry) for ticker, entry in portfolio.items()},
            f,
            indent=2,
            ensure_ascii=False,
        )


# ── Update ────────────────────────────────────────────────────────────────────

def update_portfolio(
    ticker: str,
    company_name: str,
    analysis,             # AnalysisResult — typed loosely to avoid circular import
    filing_type: str,
) -> PortfolioEntry:
    """
    Update (or create) the portfolio entry for a ticker based on an AnalysisResult.
    Saves to disk and returns the updated entry.

    Only updates if the analysis did not hard-fail (error with no data).
    Demo results are accepted — they are marked by is_demo=True on the result.
    """
    portfolio = load_portfolio()
    existing  = portfolio.get(ticker.upper())
    count     = (existing.analyses_count + 1) if existing else 1

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
    return entry


def delete_ticker(ticker: str) -> bool:
    """Remove a ticker from the portfolio. Returns True if it existed."""
    portfolio = load_portfolio()
    existed   = ticker.upper() in portfolio
    if existed:
        del portfolio[ticker.upper()]
        save_portfolio(portfolio)
    return existed
