"""
portfolio/__init__.py
---------------------
Portfolio State Engine — persists investment thesis state per ticker
using a simple JSON file. No database required.
"""

from .state import (
    PortfolioEntry,
    load_portfolio,
    save_portfolio,
    update_portfolio,
    delete_ticker,
)

__all__ = [
    "PortfolioEntry",
    "load_portfolio",
    "save_portfolio",
    "update_portfolio",
    "delete_ticker",
]
