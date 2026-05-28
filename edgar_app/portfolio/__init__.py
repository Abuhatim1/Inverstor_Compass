"""
portfolio/__init__.py
---------------------
Portfolio State Engine + Delta Intelligence Engine + Historical Comparison Store.
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

__all__ = [
    # State
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
]
