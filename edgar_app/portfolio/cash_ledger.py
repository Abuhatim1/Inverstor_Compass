"""
portfolio/cash_ledger.py
------------------------
Cash Ledger — append-only log of all cash movements.

Every debit or credit to any account is recorded here.
The cash_balance on Account is the running total; the ledger
gives the full audit trail.

Storage: cash_ledger.json  (same directory as holdings.json)

Transaction types:
  INITIAL_BALANCE  — opening balance entry
  DEPOSIT          — cash added by user (wire, transfer in)
  WITHDRAWAL       — cash removed by user
  BUY              — outflow for asset purchase (negative)
  SELL             — inflow from asset sale (positive)
  DIVIDEND         — dividend / coupon received
  FEE              — broker/custody fees (negative)
  TRANSFER_IN      — cash received from another account
  TRANSFER_OUT     — cash sent to another account
  FX_CONVERSION    — currency conversion
  OTHER            — catch-all
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime


_DIR         = os.path.dirname(__file__)
_LEDGER_FILE = os.path.join(_DIR, "cash_ledger.json")

CASH_TXN_TYPES: list[str] = [
    "INITIAL_BALANCE",
    "DEPOSIT",
    "WITHDRAWAL",
    "BUY",
    "SELL",
    "DIVIDEND",
    "FEE",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "FX_CONVERSION",
    "OTHER",
]

_TXN_ICON: dict[str, str] = {
    "INITIAL_BALANCE": "🏦",
    "DEPOSIT":         "💰",
    "WITHDRAWAL":      "💸",
    "BUY":             "🛒",
    "SELL":            "💹",
    "DIVIDEND":        "🎁",
    "FEE":             "💳",
    "TRANSFER_IN":     "➡️",
    "TRANSFER_OUT":    "⬅️",
    "FX_CONVERSION":   "💱",
    "OTHER":           "📋",
}


def txn_icon(txn_type: str) -> str:
    return _TXN_ICON.get(txn_type, "📋")


@dataclass
class CashEntry:
    entry_id:         str   = field(default_factory=lambda: str(uuid.uuid4())[:12])
    date:             str   = field(default_factory=lambda: date.today().isoformat())
    account_id:       str   = ""
    transaction_type: str   = "OTHER"
    currency:         str   = "SAR"
    amount:           float = 0.0     # positive = inflow, negative = outflow
    fx_rate:          float = 1.0     # to account's base_currency (if same, 1.0)
    linked_ticker:    str   = ""      # optional — for BUY/SELL/DIVIDEND
    notes:            str   = ""
    recorded_at:      str   = field(default_factory=lambda: datetime.now().isoformat())


# ── Persistence ───────────────────────────────────────────────────────────────

def load_ledger() -> list[CashEntry]:
    """Load all ledger entries; return [] on missing or corrupt file."""
    if not os.path.exists(_LEDGER_FILE):
        return []
    try:
        with open(_LEDGER_FILE, "r", encoding="utf-8") as f:
            raw: list = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    import dataclasses
    valid = {f.name for f in dataclasses.fields(CashEntry)}
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            filtered = {k: v for k, v in entry.items() if k in valid}
            out.append(CashEntry(**filtered))
        except Exception:
            continue
    return out


def save_ledger(entries: list[CashEntry]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    with open(_LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in entries], f, indent=2, ensure_ascii=False)


# ── Write helpers ─────────────────────────────────────────────────────────────

def append_cash_entry(
    account_id:       str,
    transaction_type: str,
    currency:         str,
    amount:           float,
    fx_rate:          float = 1.0,
    linked_ticker:    str   = "",
    notes:            str   = "",
    entry_date:       str   = "",
) -> CashEntry:
    """Append one entry to the ledger; returns the new CashEntry."""
    entries = load_ledger()
    e = CashEntry(
        account_id       = account_id,
        date             = entry_date or date.today().isoformat(),
        transaction_type = transaction_type,
        currency         = currency,
        amount           = round(amount, 8),
        fx_rate          = fx_rate,
        linked_ticker    = linked_ticker,
        notes            = notes,
    )
    entries.append(e)
    save_ledger(entries)
    return e


# ── Query helpers ─────────────────────────────────────────────────────────────

def ledger_for_account(account_id: str) -> list[CashEntry]:
    return [e for e in load_ledger() if e.account_id == account_id]


def ledger_for_ticker(ticker: str) -> list[CashEntry]:
    return [e for e in load_ledger() if e.linked_ticker == ticker]
