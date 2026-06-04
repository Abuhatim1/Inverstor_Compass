"""
portfolio/crowdfunding.py
--------------------------
Crowdfunding account module.

Each record represents one platform account (e.g. one SME financing account).
Individual deals / contracts are NOT tracked — only account-level cash flows
and periodic snapshots.

Storage
  alt_cf_accounts.json      — dict keyed by account_id
  alt_cf_transactions.json  — list of CFTransaction records
  alt_cf_snapshots.json     — list of CFSnapshot records (historical, never overwritten)

Rules
  · IDs are 8-char hex from uuid4, never reused
  · Closed accounts are never deleted
  · Latest snapshot per account determines displayed position
  · Reconciliation shows unreconciled difference — never treated as automatic error
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime

from .alt_investments import compute_xirr

_BASE           = os.path.dirname(__file__)
_CF_ACCT_FILE   = os.path.join(_BASE, "alt_cf_accounts.json")
_CF_TXN_FILE    = os.path.join(_BASE, "alt_cf_transactions.json")
_CF_SNAP_FILE   = os.path.join(_BASE, "alt_cf_snapshots.json")


# ── Constants ──────────────────────────────────────────────────────────────────

CROWDFUNDING_TYPES: list[str] = [
    "Debt Crowdfunding",
    "Equity Crowdfunding",
]

CF_STATUSES: list[str] = [
    "Active",
    "Closed",
    "Suspended",
]

CF_TRANSACTION_TYPES: list[str] = [
    "Deposit",
    "Withdrawal",
    "Profit Received",
    "Recovery Received",
    "Capital Returned",
    "Loss Write-Off",
    "Fee",
    "Tax",
    "Manual Adjustment",
]

# Types that are cash outflows for XIRR purposes
_CF_OUTFLOW_TYPES = {"Deposit", "Fee", "Tax"}
# Types that are cash inflows for XIRR purposes
_CF_INFLOW_TYPES  = {"Withdrawal", "Profit Received", "Recovery Received", "Capital Returned"}


# ── Utilities ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CFAccount:
    account_id:             str
    platform_name:          str
    account_name:           str
    crowdfunding_type:      str
    institution:            str
    currency:               str
    current_account_value:  float
    available_cash:         float
    active_investments:     float
    delayed_investments:    float
    defaulted_investments:  float
    total_deposits:         float
    total_withdrawals:      float
    total_profit_received:  float
    total_losses:           float
    last_update_date:       str       # ISO date
    status:                 str
    notes:                  str = ""
    sharia_structure:       str = "Not Specified"
    sharia_status:          str = "Not Applicable"
    sharia_notes:           str = ""
    created_at:             str = ""


@dataclass
class CFTransaction:
    txn_id:     str
    account_id: str
    date:       str       # ISO date
    txn_type:   str       # from CF_TRANSACTION_TYPES
    amount:     float     # always positive
    notes:      str = ""
    recorded_at: str = ""


@dataclass
class CFSnapshot:
    snapshot_id:           str
    account_id:            str
    snapshot_date:         str        # ISO date
    current_account_value: float
    available_cash:        float
    active_investments:    float
    delayed_investments:   float
    defaulted_investments: float
    notes:                 str = ""
    recorded_at:           str = ""


# ── Persistence ────────────────────────────────────────────────────────────────

def _from_dict_cf(d: dict) -> CFAccount:
    return CFAccount(
        account_id            = d.get("account_id", ""),
        platform_name         = d.get("platform_name", ""),
        account_name          = d.get("account_name", ""),
        crowdfunding_type     = d.get("crowdfunding_type", "Debt Crowdfunding"),
        institution           = d.get("institution", ""),
        currency              = d.get("currency", "SAR"),
        current_account_value = float(d.get("current_account_value", 0.0)),
        available_cash        = float(d.get("available_cash", 0.0)),
        active_investments    = float(d.get("active_investments", 0.0)),
        delayed_investments   = float(d.get("delayed_investments", 0.0)),
        defaulted_investments = float(d.get("defaulted_investments", 0.0)),
        total_deposits        = float(d.get("total_deposits", 0.0)),
        total_withdrawals     = float(d.get("total_withdrawals", 0.0)),
        total_profit_received = float(d.get("total_profit_received", 0.0)),
        total_losses          = float(d.get("total_losses", 0.0)),
        last_update_date      = d.get("last_update_date", ""),
        status                = d.get("status", "Active"),
        notes                 = d.get("notes", ""),
        sharia_structure      = d.get("sharia_structure", "Not Specified"),
        sharia_status         = d.get("sharia_status", "Not Applicable"),
        sharia_notes          = d.get("sharia_notes", ""),
        created_at            = d.get("created_at", ""),
    )


def _from_dict_cf_txn(d: dict) -> CFTransaction:
    return CFTransaction(
        txn_id      = d.get("txn_id", ""),
        account_id  = d.get("account_id", ""),
        date        = d.get("date", ""),
        txn_type    = d.get("txn_type", ""),
        amount      = float(d.get("amount", 0.0)),
        notes       = d.get("notes", ""),
        recorded_at = d.get("recorded_at", ""),
    )


def _from_dict_cf_snap(d: dict) -> CFSnapshot:
    return CFSnapshot(
        snapshot_id           = d.get("snapshot_id", ""),
        account_id            = d.get("account_id", ""),
        snapshot_date         = d.get("snapshot_date", ""),
        current_account_value = float(d.get("current_account_value", 0.0)),
        available_cash        = float(d.get("available_cash", 0.0)),
        active_investments    = float(d.get("active_investments", 0.0)),
        delayed_investments   = float(d.get("delayed_investments", 0.0)),
        defaulted_investments = float(d.get("defaulted_investments", 0.0)),
        notes                 = d.get("notes", ""),
        recorded_at           = d.get("recorded_at", ""),
    )


def load_cf_accounts(path: str | None = None) -> dict[str, CFAccount]:
    p = path or _CF_ACCT_FILE
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: _from_dict_cf(v) for k, v in raw.items()}


def save_cf_accounts(accounts: dict[str, CFAccount], path: str | None = None) -> None:
    p = path or _CF_ACCT_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({k: asdict(v) for k, v in accounts.items()}, fh, indent=2)


def load_cf_transactions(path: str | None = None) -> list[CFTransaction]:
    p = path or _CF_TXN_FILE
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [_from_dict_cf_txn(d) for d in raw]


def save_cf_transactions(txns: list[CFTransaction], path: str | None = None) -> None:
    p = path or _CF_TXN_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump([asdict(t) for t in txns], fh, indent=2)


def load_cf_snapshots(path: str | None = None) -> list[CFSnapshot]:
    p = path or _CF_SNAP_FILE
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [_from_dict_cf_snap(d) for d in raw]


def save_cf_snapshots(snaps: list[CFSnapshot], path: str | None = None) -> None:
    p = path or _CF_SNAP_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump([asdict(s) for s in snaps], fh, indent=2)


# ── Business logic ─────────────────────────────────────────────────────────────

def add_cf_account(
    platform_name:         str,
    account_name:          str,
    crowdfunding_type:     str,
    institution:           str,
    currency:              str,
    current_account_value: float,
    available_cash:        float,
    active_investments:    float,
    delayed_investments:   float,
    defaulted_investments: float,
    total_deposits:        float,
    total_withdrawals:     float,
    total_profit_received: float,
    total_losses:          float,
    last_update_date:      str,
    notes:                 str = "",
    sharia_structure:      str = "Not Specified",
    sharia_status:         str = "Not Applicable",
    sharia_notes:          str = "",
    path:                  str | None = None,
) -> tuple[CFAccount | None, str | None]:
    if not platform_name.strip():
        return None, "Platform name is required."
    if not account_name.strip():
        return None, "Account name is required."
    if crowdfunding_type not in CROWDFUNDING_TYPES:
        return None, f"Invalid crowdfunding type: {crowdfunding_type!r}."
    if not institution.strip():
        return None, "Institution is required."
    if current_account_value < 0:
        return None, "Current account value cannot be negative."

    acct_id = _new_id()
    acct = CFAccount(
        account_id            = acct_id,
        platform_name         = platform_name.strip(),
        account_name          = account_name.strip(),
        crowdfunding_type     = crowdfunding_type,
        institution           = institution.strip(),
        currency              = currency,
        current_account_value = round(current_account_value, 6),
        available_cash        = round(available_cash, 6),
        active_investments    = round(active_investments, 6),
        delayed_investments   = round(delayed_investments, 6),
        defaulted_investments = round(defaulted_investments, 6),
        total_deposits        = round(total_deposits, 6),
        total_withdrawals     = round(total_withdrawals, 6),
        total_profit_received = round(total_profit_received, 6),
        total_losses          = round(total_losses, 6),
        last_update_date      = last_update_date,
        status                = "Active",
        notes                 = notes.strip(),
        sharia_structure      = sharia_structure,
        sharia_status         = sharia_status,
        sharia_notes          = sharia_notes.strip(),
        created_at            = _ts(),
    )
    accounts = load_cf_accounts(path=path)
    accounts[acct_id] = acct
    save_cf_accounts(accounts, path=path)
    return acct, None


def edit_cf_account(
    account_id: str,
    path:       str | None = None,
    **kwargs,
) -> tuple[CFAccount | None, str | None]:
    accounts = load_cf_accounts(path=path)
    if account_id not in accounts:
        return None, f"Account {account_id!r} not found."
    acct = accounts[account_id]

    editable = {
        "platform_name", "account_name", "institution", "currency",
        "current_account_value", "available_cash", "active_investments",
        "delayed_investments", "defaulted_investments", "total_deposits",
        "total_withdrawals", "total_profit_received", "total_losses",
        "last_update_date", "status", "notes",
        "sharia_structure", "sharia_status", "sharia_notes",
    }
    for k, v in kwargs.items():
        if k in editable:
            setattr(acct, k, v)

    accounts[account_id] = acct
    save_cf_accounts(accounts, path=path)
    return acct, None


def record_cf_transaction(
    account_id: str,
    txn_type:   str,
    amount:     float,
    txn_date:   str,
    notes:      str = "",
    path:       str | None = None,
    txn_path:   str | None = None,
) -> tuple[CFTransaction | None, str | None]:
    accounts = load_cf_accounts(path=path)
    if account_id not in accounts:
        return None, f"Account {account_id!r} not found."
    if txn_type not in CF_TRANSACTION_TYPES:
        return None, f"Invalid transaction type: {txn_type!r}."
    if amount <= 0:
        return None, "Amount must be positive."

    txn = CFTransaction(
        txn_id      = _new_id(),
        account_id  = account_id,
        date        = txn_date,
        txn_type    = txn_type,
        amount      = round(amount, 6),
        notes       = notes.strip(),
        recorded_at = _ts(),
    )
    txns = load_cf_transactions(path=txn_path)
    txns.append(txn)
    save_cf_transactions(txns, path=txn_path)
    return txn, None


def add_cf_snapshot(
    account_id:            str,
    snapshot_date:         str,
    current_account_value: float,
    available_cash:        float,
    active_investments:    float,
    delayed_investments:   float,
    defaulted_investments: float,
    notes:                 str = "",
    path:                  str | None = None,
    snap_path:             str | None = None,
) -> tuple[CFSnapshot | None, str | None]:
    """
    Record a snapshot and update the account's live position fields.
    Latest snapshot per account always wins for the displayed position.
    Historical snapshots are never overwritten.
    """
    accounts = load_cf_accounts(path=path)
    if account_id not in accounts:
        return None, f"Account {account_id!r} not found."
    if current_account_value < 0:
        return None, "Current account value cannot be negative."

    snap = CFSnapshot(
        snapshot_id           = _new_id(),
        account_id            = account_id,
        snapshot_date         = snapshot_date,
        current_account_value = round(current_account_value, 6),
        available_cash        = round(available_cash, 6),
        active_investments    = round(active_investments, 6),
        delayed_investments   = round(delayed_investments, 6),
        defaulted_investments = round(defaulted_investments, 6),
        notes                 = notes.strip(),
        recorded_at           = _ts(),
    )
    snaps = load_cf_snapshots(path=snap_path)
    snaps.append(snap)
    save_cf_snapshots(snaps, path=snap_path)

    # Update live account position from this snapshot
    acct = accounts[account_id]
    acct.current_account_value = snap.current_account_value
    acct.available_cash        = snap.available_cash
    acct.active_investments    = snap.active_investments
    acct.delayed_investments   = snap.delayed_investments
    acct.defaulted_investments = snap.defaulted_investments
    acct.last_update_date      = snapshot_date
    accounts[account_id] = acct
    save_cf_accounts(accounts, path=path)

    return snap, None


def compute_cf_metrics(
    account_id: str,
    path:       str | None = None,
    txn_path:   str | None = None,
) -> dict:
    """Compute performance metrics for a single CF account."""
    accounts = load_cf_accounts(path=path)
    acct = accounts.get(account_id)
    if acct is None:
        return {}

    all_txns = load_cf_transactions(path=txn_path)
    txns     = [t for t in all_txns if t.account_id == account_id]

    total_deposits        = sum(t.amount for t in txns if t.txn_type == "Deposit")
    total_withdrawals     = sum(t.amount for t in txns if t.txn_type == "Withdrawal")
    total_profit_received = sum(t.amount for t in txns if t.txn_type == "Profit Received")
    total_losses          = sum(t.amount for t in txns if t.txn_type == "Loss Write-Off")
    net_deposits          = total_deposits - total_withdrawals
    net_profit_loss       = total_profit_received - total_losses

    # XIRR: deposits = outflows, withdrawals + profits = inflows
    xirr_flows: list[tuple[str, float]] = []
    for t in sorted(txns, key=lambda x: x.date):
        if t.txn_type in _CF_OUTFLOW_TYPES:
            xirr_flows.append((t.date, -t.amount))
        elif t.txn_type in _CF_INFLOW_TYPES:
            xirr_flows.append((t.date, t.amount))
    # Add current value as theoretical inflow today
    if acct.status != "Closed" and acct.current_account_value > 0:
        from datetime import date as _date
        xirr_flows.append((_date.today().isoformat(), acct.current_account_value))

    xirr = compute_xirr(xirr_flows)

    return {
        "account_id":           account_id,
        "current_account_value": acct.current_account_value,
        "available_cash":       acct.available_cash,
        "active_investments":   acct.active_investments,
        "delayed_investments":  acct.delayed_investments,
        "defaulted_investments": acct.defaulted_investments,
        "total_deposits":       total_deposits,
        "total_withdrawals":    total_withdrawals,
        "net_deposits":         net_deposits,
        "total_profit_received": total_profit_received,
        "total_losses":         total_losses,
        "net_profit_loss":      net_profit_loss,
        "xirr":                 xirr,
    }


def compute_cf_reconciliation(
    account_id: str,
    path:       str | None = None,
    txn_path:   str | None = None,
) -> dict:
    """
    Reconcile: current_account_value vs (deposits - withdrawals + profits - losses).

    Unreconciled difference is shown to the user but is NOT auto-treated as an error.
    """
    accounts = load_cf_accounts(path=path)
    acct = accounts.get(account_id)
    if acct is None:
        return {}

    all_txns = load_cf_transactions(path=txn_path)
    txns     = [t for t in all_txns if t.account_id == account_id]

    deposits  = sum(t.amount for t in txns if t.txn_type == "Deposit")
    withdrawals = sum(t.amount for t in txns if t.txn_type == "Withdrawal")
    profits   = sum(t.amount for t in txns if t.txn_type == "Profit Received")
    losses    = sum(t.amount for t in txns if t.txn_type == "Loss Write-Off")
    capital_returned = sum(t.amount for t in txns if t.txn_type == "Capital Returned")
    recoveries = sum(t.amount for t in txns if t.txn_type == "Recovery Received")

    expected_balance = deposits - withdrawals + profits - losses + recoveries + capital_returned
    unreconciled     = acct.current_account_value - expected_balance

    return {
        "deposits":           deposits,
        "withdrawals":        withdrawals,
        "profits":            profits,
        "losses":             losses,
        "capital_returned":   capital_returned,
        "recoveries":         recoveries,
        "expected_balance":   round(expected_balance, 6),
        "current_value":      acct.current_account_value,
        "unreconciled_diff":  round(unreconciled, 6),
    }
