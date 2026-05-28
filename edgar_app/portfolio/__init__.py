"""
portfolio/__init__.py
---------------------
Portfolio System.

Layers (separate concerns):

  · **Research Watchlist** (`state.py`, `PortfolioEntry`)
      Populated automatically by every AI analysis (Filing Search, Upload).
      Tracks thesis, catalysts, risks, conviction, recommended action — the
      *opinion* about a ticker. Does NOT mean you own it.

  · **Actual Holdings** (`holdings.py`, `Holding`)
      Positions you actually own. Quantity, average cost, current price,
      market, sector. Created explicitly via "Add to Holdings" or by
      recording a BUY transaction. Derived metrics: market value,
      unrealized P&L, portfolio weight %.

  · **Transactions** (`holdings.py`, `Transaction`)
      Manual buy/sell history. Each BUY updates the holding's quantity and
      weighted-average cost; SELL reduces quantity.

  · **Delta Engine** (`delta.py`)
      Filing-over-filing change detection (thesis swings, conviction moves).

  · **Comparison Store** (`comparison_store.py`)
      Historical filing comparisons (revenue, margins, guidance trends).

  · **Risk Engine** (`risk.py`)
      Investment-risk (not price-volatility) over **Actual Holdings**,
      enriched with research watchlist signals and market intel.
"""

from .comparison_store import (
    ComparisonRecord,
    TREND_ICON,
    TONE_ICON,
    GUIDANCE_ICON,
    build_comparison_record,
    load_comparison_history,
    save_comparison,
)
from .delta import (
    ALERT_ACTION_DOWNGRADED,
    ALERT_ACTION_UPGRADED,
    ALERT_CONVICTION_DROPPED,
    ALERT_CONVICTION_IMPROVED,
    ALERT_FALLING_RISK,
    ALERT_RISING_RISK,
    ALERT_THESIS_IMPROVED,
    ALERT_THESIS_WEAKENED,
    DeltaRecord,
    load_delta_history,
    save_delta,
)
from .state import (
    PortfolioEntry,
    delete_ticker,
    load_portfolio,
    save_portfolio,
    update_portfolio,
)
from .holdings import (
    Holding,
    Transaction,
    delete_holding,
    load_holdings,
    load_transactions,
    portfolio_weights,
    record_transaction,
    save_holdings,
    save_transactions,
    total_cost_basis,
    total_market_value,
    update_current_price,
    upsert_holding,
)
from .risk import (
    DEFAULT_SECTORS,
    MARKETS,
    RISK_CATEGORIES,
    RISK_REGIME_BADGE,
    PortfolioPosition,
    PortfolioRiskResult,
    RiskCategoryScore,
    build_positions,
    compute_portfolio_risk,
    load_market_intel_state,
    save_market_intel_for_ticker,
)

__all__ = [
    # Research Watchlist (state)
    "PortfolioEntry",
    "load_portfolio",
    "save_portfolio",
    "update_portfolio",
    "delete_ticker",
    # Delta
    "DeltaRecord",
    "load_delta_history",
    "save_delta",
    "ALERT_THESIS_WEAKENED",
    "ALERT_THESIS_IMPROVED",
    "ALERT_RISING_RISK",
    "ALERT_FALLING_RISK",
    "ALERT_ACTION_DOWNGRADED",
    "ALERT_ACTION_UPGRADED",
    "ALERT_CONVICTION_DROPPED",
    "ALERT_CONVICTION_IMPROVED",
    # Comparison
    "ComparisonRecord",
    "TREND_ICON",
    "TONE_ICON",
    "GUIDANCE_ICON",
    "build_comparison_record",
    "load_comparison_history",
    "save_comparison",
    # Actual Holdings + Transactions
    "Holding",
    "Transaction",
    "load_holdings",
    "save_holdings",
    "upsert_holding",
    "delete_holding",
    "update_current_price",
    "load_transactions",
    "save_transactions",
    "record_transaction",
    "total_market_value",
    "total_cost_basis",
    "portfolio_weights",
    # Risk Engine
    "MARKETS",
    "DEFAULT_SECTORS",
    "RISK_REGIME_BADGE",
    "RISK_CATEGORIES",
    "PortfolioPosition",
    "PortfolioRiskResult",
    "RiskCategoryScore",
    "build_positions",
    "compute_portfolio_risk",
    "load_market_intel_state",
    "save_market_intel_for_ticker",
]
