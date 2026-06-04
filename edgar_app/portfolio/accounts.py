"""
portfolio/accounts.py
---------------------
Investment Accounts Module.

Stores brokerage accounts, bank accounts, and cash wallets.
Each account has an independent cash balance tracked in its own currency.

Storage: accounts.json  (same directory as holdings.json)

Design notes:
- account_id is an 8-char UUID prefix, generated once at creation.
- Cash balance is maintained here AND reflected in the cash ledger.
- update_account_cash() applies a signed delta (positive = inflow).
- Never import from holdings.py — keeps modules independent.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date


_DIR           = os.path.dirname(__file__)
_ACCOUNTS_FILE = os.path.join(_DIR, "accounts.json")

ACCOUNT_TYPES: list[str] = ["Brokerage", "Bank", "Cash", "Crypto", "Other"]


@dataclass
class Account:
    account_id:    str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    account_name:  str   = ""
    institution:   str   = ""
    account_type:  str   = "Brokerage"
    base_currency: str   = "SAR"
    cash_balance:  float = 0.0
    notes:         str   = ""
    active:        bool  = True
    created_at:    str   = field(default_factory=lambda: date.today().isoformat())


# ── Persistence ───────────────────────────────────────────────────────────────

def load_accounts() -> dict[str, Account]:
    """Load accounts.json; return {} on missing or corrupt file."""
    if not os.path.exists(_ACCOUNTS_FILE):
        return {}
    try:
        with open(_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    import dataclasses
    valid = {f.name for f in dataclasses.fields(Account)}
    out: dict[str, Account] = {}
    for aid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            filtered = {k: v for k, v in entry.items() if k in valid}
            out[aid] = Account(**filtered)
        except Exception:
            continue
    return out


def save_accounts(accounts: dict[str, Account]) -> None:
    from portfolio._io import atomic_json_write
    atomic_json_write(_ACCOUNTS_FILE, {aid: asdict(a) for aid, a in accounts.items()})


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def upsert_account(
    account_id:    str | None = None,
    account_name:  str        = "",
    institution:   str        = "",
    account_type:  str        = "Brokerage",
    base_currency: str        = "SAR",
    opening_cash:  float      = 0.0,
    notes:         str        = "",
    active:        bool       = True,
) -> Account:
    """Create or update an account. Returns the saved Account."""
    accounts = load_accounts()
    if account_id and account_id in accounts:
        a = accounts[account_id]
        a.account_name = account_name or a.account_name
        a.institution  = institution  or a.institution
        a.account_type = account_type
        a.base_currency = base_currency
        a.notes  = notes
        a.active = active
    else:
        a = Account(
            account_id    = account_id or str(uuid.uuid4())[:8],
            account_name  = account_name,
            institution   = institution,
            account_type  = account_type,
            base_currency = base_currency,
            cash_balance  = opening_cash,
            notes         = notes,
            active        = active,
        )
        accounts[a.account_id] = a
    save_accounts(accounts)
    return a


def update_account_cash(account_id: str, delta: float) -> float:
    """
    Apply a signed cash delta to an account.
    Positive delta = cash inflow (deposit / sale proceeds).
    Negative delta = cash outflow (purchase / withdrawal).
    Returns the new cash balance.
    """
    accounts = load_accounts()
    if account_id not in accounts:
        raise KeyError(f"Account '{account_id}' not found.")
    accounts[account_id].cash_balance = round(
        accounts[account_id].cash_balance + delta, 8
    )
    save_accounts(accounts)
    return accounts[account_id].cash_balance


def set_account_cash(account_id: str, balance: float) -> None:
    """Overwrite the cash balance directly (e.g. correction / reconciliation)."""
    accounts = load_accounts()
    if account_id not in accounts:
        raise KeyError(f"Account '{account_id}' not found.")
    accounts[account_id].cash_balance = round(balance, 8)
    save_accounts(accounts)


def _guard_delete_account(
    account_id:   str,
    cash_balance: float,
    holdings:     dict,   # dict[str, Holding] or dict[str, dict]
    transactions: list,   # list[Transaction]  or list[dict]
    closed_lots:  list,   # list[ClosedLot]    or list[dict]
) -> str | None:
    """
    Return an error string if the account cannot safely be deleted, else None.

    Accepts both dataclass instances and plain dicts so it is testable
    with in-memory sandbox objects and callable from delete_account().
    """
    _ERR = (
        "Cannot delete account with cash, holdings, transactions, or closed lots."
    )

    def _attr(obj, name: str, default=""):
        return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)

    # 1 — non-zero cash balance
    if cash_balance != 0.0:
        return _ERR

    # 2 — any holding linked to this account
    for h in holdings.values():
        if _attr(h, "default_account_id") == account_id:
            return _ERR

    # 3 — any transaction referencing this account
    for txn in transactions:
        if _attr(txn, "account_id") == account_id:
            return _ERR

    # 4 — any non-voided closed lot referencing this account
    for lot in closed_lots:
        if _attr(lot, "account_id") == account_id and not _attr(lot, "voided", False):
            return _ERR

    return None


def delete_account(account_id: str) -> None:
    """
    Permanently remove an account.

    Raises ValueError if the account has a non-zero cash balance, linked
    holdings, transactions, or closed lots.  Only completely unused accounts
    (empty, no references anywhere) may be hard-deleted.
    """
    # Deferred imports avoid circular dependencies (accounts ↛ holdings/closed_holdings).
    from .holdings       import load_holdings, load_transactions
    from .closed_holdings import load_closed_lots

    accounts = load_accounts()
    if account_id not in accounts:
        return                          # nothing to delete — silent no-op

    acct  = accounts[account_id]
    error = _guard_delete_account(
        account_id,
        acct.cash_balance,
        load_holdings(),
        load_transactions(),
        load_closed_lots(),
    )
    if error:
        raise ValueError(error)

    accounts.pop(account_id)
    save_accounts(accounts)


# ── Query helpers ─────────────────────────────────────────────────────────────

def active_accounts(currency: str | None = None) -> dict[str, Account]:
    """Return active accounts, optionally filtered by base_currency."""
    all_accts = load_accounts()
    return {
        aid: a for aid, a in all_accts.items()
        if a.active and (currency is None or a.base_currency == currency)
    }


def account_display_name(a: Account) -> str:
    """Human-readable label for dropdowns."""
    parts = [a.account_name]
    if a.institution:
        parts.append(f"({a.institution})")
    parts.append(f"[{a.base_currency}]")
    return " ".join(parts)
