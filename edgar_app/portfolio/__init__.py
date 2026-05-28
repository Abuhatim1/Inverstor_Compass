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
from .decision_ranking import (
    ACTION_BADGE,
    DecisionQueueResult,
    DecisionSignal,
    HoldingDecision,
    SIGNAL_NAMES,
    URGENCY_BADGE,
    compute_decision_queue,
    compute_holding_decision,
)
from .core_thesis import (
    THESIS_STATUSES,
    THESIS_STATUS_BADGE,
    THESIS_STATUS_BROKEN,
    THESIS_STATUS_STABLE,
    THESIS_STATUS_STRENGTHENING,
    THESIS_STATUS_WEAKENING,
    TIME_HORIZONS,
    CONVICTION_BADGE,
    CONVICTION_FALLING,
    CONVICTION_RISING,
    CONVICTION_STABLE,
    CONVICTION_TRENDS,
    EVENT_BADGE,
    EVENT_BREAK,
    EVENT_CONFIRMATION,
    EVENT_DETERIORATION,
    EVENT_OPTIONALITY,
    EVENT_TYPES,
    RISK_CATEGORIES,
    RISK_KINDS,
    RISK_SEVERITIES,
    RISK_STATUSES,
    CoreThesis,
    RiskMatrixItem,
    ScenarioCase,
    ThesisValidationEvent,
    apply_evaluation,
    delete_core_thesis,
    delete_risk_item,
    evaluate_thesis_against_analysis,
    load_all_core_theses,
    load_core_thesis,
    save_core_thesis,
    upsert_core_thesis_fields,
    upsert_risk_item,
)
from .thesis_importer import (
    ImportError_ as ThesisImportError,
    ThesisQuotaExceeded,
    build_preview_thesis,
    extract_text as extract_text_from_document,
    extract_thesis_from_text,
    extract_thesis_rule_based,
    normalize_scenario_probabilities,
    preview_summary as thesis_preview_summary,
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
    # Decision Ranking Engine
    "ACTION_BADGE",
    "URGENCY_BADGE",
    "SIGNAL_NAMES",
    "DecisionSignal",
    "HoldingDecision",
    "DecisionQueueResult",
    "compute_holding_decision",
    "compute_decision_queue",
    # Dynamic Thesis State Engine
    "CoreThesis",
    "RiskMatrixItem",
    "ScenarioCase",
    "ThesisValidationEvent",
    "THESIS_STATUSES",
    "THESIS_STATUS_BADGE",
    "THESIS_STATUS_STRENGTHENING",
    "THESIS_STATUS_STABLE",
    "THESIS_STATUS_WEAKENING",
    "THESIS_STATUS_BROKEN",
    "TIME_HORIZONS",
    "CONVICTION_BADGE",
    "CONVICTION_TRENDS",
    "CONVICTION_RISING",
    "CONVICTION_STABLE",
    "CONVICTION_FALLING",
    "EVENT_BADGE",
    "EVENT_TYPES",
    "EVENT_CONFIRMATION",
    "EVENT_DETERIORATION",
    "EVENT_BREAK",
    "EVENT_OPTIONALITY",
    "RISK_CATEGORIES",
    "RISK_STATUSES",
    "RISK_SEVERITIES",
    "RISK_KINDS",
    "load_core_thesis",
    "load_all_core_theses",
    "save_core_thesis",
    "delete_core_thesis",
    "upsert_core_thesis_fields",
    "upsert_risk_item",
    "delete_risk_item",
    "evaluate_thesis_against_analysis",
    "apply_evaluation",
    # Thesis import (PDF / DOCX / TXT → CoreThesis)
    "ThesisImportError",
    "ThesisQuotaExceeded",
    "extract_text_from_document",
    "extract_thesis_from_text",
    "extract_thesis_rule_based",
    "build_preview_thesis",
    "thesis_preview_summary",
    "normalize_scenario_probabilities",
]
