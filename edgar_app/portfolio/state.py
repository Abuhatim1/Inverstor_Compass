"""
portfolio/state.py
------------------
Portfolio State Engine.

update_portfolio() now accepts an optional conviction_adjustment (from the
Historical Filing Comparison) so the final stored conviction score reflects
both the AI's base score and the comparative trend data.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import date

from .delta import DeltaRecord, detect_delta, save_delta

_STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")


@dataclass
class PortfolioEntry:
    ticker:             str
    company_name:       str
    last_filing_type:   str
    thesis_status:      str     # "Strong" | "Stable" | "Weak" | "Broken"
    catalysts:          list[str]
    risks:              list[str]
    conviction_score:   int     # 0–100 (base AI score + comparison adjustment)
    recommended_action: str     # "Buy" | "Hold" | "Reduce" | "Exit"
    last_updated:       str     # ISO date
    analyses_count:     int = 1


def load_portfolio() -> dict[str, PortfolioEntry]:
    if not os.path.exists(_STATE_FILE):
        return {}
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return {t: PortfolioEntry(**e) for t, e in raw.items()}


def save_portfolio(portfolio: dict[str, PortfolioEntry]) -> None:
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {t: asdict(e) for t, e in portfolio.items()},
            f, indent=2, ensure_ascii=False,
        )


def update_portfolio(
    ticker:               str,
    company_name:         str,
    analysis,             # AnalysisResult — typed loosely to avoid circular import
    filing_type:          str,
    conviction_adjustment: int = 0,
) -> tuple[PortfolioEntry, DeltaRecord]:
    """
    Compare new analysis against previous state, record the delta,
    then save the updated entry.

    conviction_adjustment: integer from FilingComparison (-20 … +20).
    The final stored conviction score is clamped to [0, 100].

    Returns (updated_entry, delta_record).
    """
    portfolio = load_portfolio()
    existing  = portfolio.get(ticker.upper())
    count     = (existing.analyses_count + 1) if existing else 1

    # Adjusted conviction score
    raw_score   = analysis.confidence_score + conviction_adjustment
    final_score = max(0, min(100, raw_score))

    # Detect delta BEFORE overwriting the state
    delta = detect_delta(existing, analysis, ticker, company_name, filing_type)
    save_delta(delta)

    entry = PortfolioEntry(
        ticker=ticker.upper(),
        company_name=company_name,
        last_filing_type=filing_type,
        thesis_status=analysis.thesis_impact,
        catalysts=analysis.key_catalysts,
        risks=analysis.key_risks,
        conviction_score=final_score,
        recommended_action=analysis.suggested_action,
        last_updated=date.today().isoformat(),
        analyses_count=count,
    )
    portfolio[ticker.upper()] = entry
    save_portfolio(portfolio)
    return entry, delta


def delete_ticker(ticker: str) -> bool:
    portfolio = load_portfolio()
    existed   = ticker.upper() in portfolio
    if existed:
        del portfolio[ticker.upper()]
        save_portfolio(portfolio)
    return existed
