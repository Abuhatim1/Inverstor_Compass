"""
portfolio/liabilities.py
-------------------------
Standalone liabilities module.

Tracks financial obligations not tied to a specific fixed asset:
  · Personal Loan
  · Car Loan
  · Home Mortgage
  · Credit Card
  · Business Loan
  · Other

Net worth contribution: negative — all Active liabilities are subtracted
from total net worth.

Storage
  liabilities.json  — dict keyed by liability_id

Rules
  · IDs are 8-char hex from uuid4, never reused
  · Paid-off liabilities are retained as history but excluded from net worth
  · outstanding_balance >= 0.0 always
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime

_BASE     = os.path.dirname(__file__)
_LIB_FILE = os.path.join(_BASE, "liabilities.json")


# ── Constants ──────────────────────────────────────────────────────────────────

LIABILITY_TYPES: list[str] = [
    "Personal Loan",
    "Car Loan",
    "Home Mortgage",
    "Credit Card",
    "Business Loan",
    "Other",
]

LIABILITY_STATUSES: list[str] = [
    "Active",
    "Paid Off",
]


# ── Utilities ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class Liability:
    liability_id:        str
    name:                str
    liability_type:      str      # from LIABILITY_TYPES
    lender:              str      # institution / bank name (optional)
    currency:            str
    outstanding_balance: float    # remaining balance owed
    interest_rate:       float    # % per annum; 0.0 = unknown / not entered
    due_date:            str      # ISO date string, "" if unknown
    notes:               str
    status:              str      # "Active" | "Paid Off"
    created_at:          str = ""
    updated_at:          str = ""


# ── Persistence ────────────────────────────────────────────────────────────────

def _from_dict(d: dict) -> Liability:
    return Liability(
        liability_id        = d.get("liability_id", ""),
        name                = d.get("name", ""),
        liability_type      = d.get("liability_type", "Other"),
        lender              = d.get("lender", ""),
        currency            = d.get("currency", "SAR"),
        outstanding_balance = float(d.get("outstanding_balance", 0.0)),
        interest_rate       = float(d.get("interest_rate", 0.0)),
        due_date            = d.get("due_date", ""),
        notes               = d.get("notes", ""),
        status              = d.get("status", "Active"),
        created_at          = d.get("created_at", ""),
        updated_at          = d.get("updated_at", ""),
    )


def load_liabilities(path: str | None = None) -> dict[str, Liability]:
    """Load liabilities from disk.  Returns {} if file absent."""
    p = path or _LIB_FILE
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: _from_dict(v) for k, v in raw.items()}


def save_liabilities(liabilities: dict[str, Liability], path: str | None = None) -> None:
    p = path or _LIB_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({k: asdict(v) for k, v in liabilities.items()}, fh, indent=2)


# ── Business logic ─────────────────────────────────────────────────────────────

def add_liability(
    name:                str,
    liability_type:      str,
    currency:            str,
    outstanding_balance: float,
    lender:              str       = "",
    interest_rate:       float     = 0.0,
    due_date:            str       = "",
    notes:               str       = "",
    path:                str | None = None,
) -> tuple[Liability | None, str | None]:
    """Create and persist a new liability.  Returns (liability, None) on success."""
    if not name.strip():
        return None, "Liability name is required."
    if liability_type not in LIABILITY_TYPES:
        return None, f"Invalid liability type: {liability_type!r}."
    if outstanding_balance < 0:
        return None, "Outstanding balance cannot be negative."
    if interest_rate < 0:
        return None, "Interest rate cannot be negative."

    liability_id = _new_id()
    now          = _ts()
    lib          = Liability(
        liability_id        = liability_id,
        name                = name.strip(),
        liability_type      = liability_type,
        lender              = lender.strip(),
        currency            = currency,
        outstanding_balance = round(outstanding_balance, 6),
        interest_rate       = round(interest_rate, 4),
        due_date            = due_date,
        notes               = notes.strip(),
        status              = "Active",
        created_at          = now,
        updated_at          = now,
    )
    libs = load_liabilities(path=path)
    libs[liability_id] = lib
    save_liabilities(libs, path=path)
    return lib, None


def edit_liability(
    liability_id: str,
    path:         str | None = None,
    **kwargs,
) -> tuple[Liability | None, str | None]:
    """
    Edit fields of an Active liability.
    Editable: name, liability_type, lender, currency,
              outstanding_balance, interest_rate, due_date, notes.
    """
    libs = load_liabilities(path=path)
    if liability_id not in libs:
        return None, f"Liability {liability_id!r} not found."
    lib = libs[liability_id]
    if lib.status == "Paid Off":
        return None, "Paid-off liabilities cannot be edited."

    editable = {
        "name", "liability_type", "lender", "currency",
        "outstanding_balance", "interest_rate", "due_date", "notes",
    }
    for k, v in kwargs.items():
        if k in editable:
            setattr(lib, k, v)
    lib.updated_at = _ts()
    libs[liability_id] = lib
    save_liabilities(libs, path=path)
    return lib, None


def mark_paid_off(
    liability_id: str,
    path:         str | None = None,
) -> tuple[bool, str | None]:
    """
    Mark a liability as Paid Off.
    Paid-off entries are excluded from net worth but kept as history.
    """
    libs = load_liabilities(path=path)
    if liability_id not in libs:
        return False, f"Liability {liability_id!r} not found."
    lib = libs[liability_id]
    if lib.status == "Paid Off":
        return False, "Liability is already marked as Paid Off."
    lib.status     = "Paid Off"
    lib.updated_at = _ts()
    libs[liability_id] = lib
    save_liabilities(libs, path=path)
    return True, None


def compute_liabilities_base(
    liabilities: dict[str, Liability],
    base_ccy:    str,
    fx_rates:    dict,
) -> float:
    """
    Sum outstanding_balance for all Active liabilities, FX-converted to base_ccy.

    Parameters
    ----------
    liabilities : dict[str, Liability]
    base_ccy    : str
    fx_rates    : {ccy: FxRate}  — same dict produced by valuation engine

    Returns float rounded to 4 decimal places.
    """
    total = 0.0
    for lib in liabilities.values():
        if lib.status != "Active":
            continue
        rate_obj = fx_rates.get(lib.currency)
        rate     = rate_obj.rate if rate_obj else 1.0
        total   += lib.outstanding_balance * rate
    return round(total, 4)
