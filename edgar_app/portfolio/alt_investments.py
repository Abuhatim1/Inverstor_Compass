"""
portfolio/alt_investments.py
-----------------------------
Investment Grade Income (IGI) module.

Tracks investments not represented by the unit-priced Holdings engine:
  · Islamic savings accounts / profit-bearing accounts
  · Islamic deposits / Murabaha placements
  · Government and Corporate Sukuk
  · Money Market Products

Storage
  alt_investments.json        — dict keyed by investment_id
  alt_igi_transactions.json   — list of IGITransaction records

Rules
  · IDs are 8-char hex from uuid4, never reused
  · Closed investments are never deleted
  · Expected profit is NEVER used in calculations — only actual cash flows
  · Sharia metadata is informational only; does not affect any calculation
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import date as _date, datetime

_BASE         = os.path.dirname(__file__)
_IGI_FILE     = os.path.join(_BASE, "alt_investments.json")
_IGI_TXN_FILE = os.path.join(_BASE, "alt_igi_transactions.json")


# ── Constants ──────────────────────────────────────────────────────────────────

SHARIA_STRUCTURES: list[str] = [
    "Not Specified", "Unknown", "Murabaha", "Mudaraba", "Musharaka",
    "Ijara", "Wakala", "Sukuk Ijara", "Sukuk Murabaha", "Sukuk Wakala",
    "Commodity Murabaha / Tawarruq", "Hybrid Structure", "Other",
]

SHARIA_COMPLIANCE_STATUSES: list[str] = [
    "Shariah Compliant", "Conventional", "Mixed / Unclear",
    "Under Review", "Not Applicable",
]

PROFIT_PAYMENT_STRUCTURES: list[str] = [
    "At Maturity", "Periodic", "Mixed",
]

LIQUIDITY_TYPES: list[str] = [
    "Daily", "Monthly", "Locked Until Maturity", "Other",
]

IGI_STATUSES: list[str] = [
    "Pending Funding", "Active", "Maturity Action Required", "Closed",
]

MATURITY_INSTRUCTIONS: list[str] = [
    "Principal Returned",
    "Reinvest Principal",
    "Reinvest Principal + Profit",
    "Manual Decision At Maturity",
]

IGI_TRANSACTION_TYPES: list[str] = [
    "Initial Investment",
    "Additional Investment",
    "Profit Received",
    "Principal Returned",
    "Withdrawal",
    "Manual Adjustment",
]

# Transaction types that are cash outflows (reduce invested principal net)
_IGI_OUTFLOW_TYPES = {"Initial Investment", "Additional Investment"}
# Transaction types that are inflows
_IGI_INFLOW_TYPES  = {"Profit Received", "Principal Returned", "Withdrawal"}


# ── Utilities ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ── XIRR (pure Python / Newton-Raphson, no scipy) ─────────────────────────────

def compute_xirr(
    cash_flows: list[tuple[str, float]],
    guess: float = 0.1,
) -> float | None:
    """
    Compute XIRR from (date_str, amount) tuples.

    Convention: outflows are negative, inflows are positive.
    Returns the annualised rate (e.g. 0.065 = 6.5%) or None if
    computation fails (too few flows, no sign change, no convergence).
    """
    if not cash_flows or len(cash_flows) < 2:
        return None

    amounts = [a for _, a in cash_flows]
    # Need at least one sign change
    has_pos = any(a > 0 for a in amounts)
    has_neg = any(a < 0 for a in amounts)
    if not (has_pos and has_neg):
        return None

    try:
        dates = [_date.fromisoformat(d) for d, _ in cash_flows]
    except ValueError:
        return None

    t0    = dates[0]
    years = [(d - t0).days / 365.0 for d in dates]

    def _npv(r: float) -> float:
        return sum(a / (1.0 + r) ** t for a, t in zip(amounts, years))

    def _dnpv(r: float) -> float:
        return sum(-t * a / (1.0 + r) ** (t + 1.0) for a, t in zip(amounts, years))

    rate = guess
    for _ in range(200):
        f  = _npv(rate)
        df = _dnpv(rate)
        if abs(df) < 1e-14:
            break
        new_rate = rate - f / df
        if abs(new_rate - rate) < 1e-8:
            return round(new_rate, 8)
        rate = new_rate
        if rate <= -1.0:
            rate = -0.9999
    return None


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class IGIInvestment:
    investment_id:           str
    investment_name:         str
    institution:             str
    currency:                str
    principal_amount:        float
    current_value:           float
    start_date:              str      # ISO date
    maturity_date:           str      # ISO date
    expected_yield_pct:      float    # e.g. 5.5 for 5.5 %
    profit_payment_structure: str
    liquidity_type:          str
    status:                  str
    maturity_instruction:    str
    notes:                   str = ""
    sharia_structure:        str = "Not Specified"
    sharia_status:           str = "Not Applicable"
    sharia_notes:            str = ""
    parent_investment_id:    str = ""
    child_investment_id:     str = ""
    created_at:              str = ""


@dataclass
class IGITransaction:
    txn_id:        str
    investment_id: str
    date:          str      # ISO date
    txn_type:      str      # from IGI_TRANSACTION_TYPES
    amount:        float    # always positive; sign derived from txn_type in metrics
    notes:         str = ""
    recorded_at:   str = ""


# ── Persistence ────────────────────────────────────────────────────────────────

def _from_dict_igi(d: dict) -> IGIInvestment:
    return IGIInvestment(
        investment_id           = d.get("investment_id", ""),
        investment_name         = d.get("investment_name", ""),
        institution             = d.get("institution", ""),
        currency                = d.get("currency", "SAR"),
        principal_amount        = float(d.get("principal_amount", 0.0)),
        current_value           = float(d.get("current_value", 0.0)),
        start_date              = d.get("start_date", ""),
        maturity_date           = d.get("maturity_date", ""),
        expected_yield_pct      = float(d.get("expected_yield_pct", 0.0)),
        profit_payment_structure= d.get("profit_payment_structure", "At Maturity"),
        liquidity_type          = d.get("liquidity_type", "Locked Until Maturity"),
        status                  = d.get("status", "Active"),
        maturity_instruction    = d.get("maturity_instruction", "Principal Returned"),
        notes                   = d.get("notes", ""),
        sharia_structure        = d.get("sharia_structure", "Not Specified"),
        sharia_status           = d.get("sharia_status", "Not Applicable"),
        sharia_notes            = d.get("sharia_notes", ""),
        parent_investment_id    = d.get("parent_investment_id", ""),
        child_investment_id     = d.get("child_investment_id", ""),
        created_at              = d.get("created_at", ""),
    )


def _from_dict_igi_txn(d: dict) -> IGITransaction:
    return IGITransaction(
        txn_id        = d.get("txn_id", ""),
        investment_id = d.get("investment_id", ""),
        date          = d.get("date", ""),
        txn_type      = d.get("txn_type", ""),
        amount        = float(d.get("amount", 0.0)),
        notes         = d.get("notes", ""),
        recorded_at   = d.get("recorded_at", ""),
    )


def load_igi_investments(path: str | None = None) -> dict[str, IGIInvestment]:
    """Load IGI investments and auto-flag maturity where applicable."""
    p = path or _IGI_FILE
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    investments = {k: _from_dict_igi(v) for k, v in raw.items()}

    # Auto-flag: Active investments past maturity date → Maturity Action Required
    today = _date.today().isoformat()
    changed = False
    for inv in investments.values():
        if inv.status == "Active" and inv.maturity_date and inv.maturity_date <= today:
            inv.status = "Maturity Action Required"
            changed = True
    if changed:
        save_igi_investments(investments, path=p)
    return investments


def save_igi_investments(investments: dict[str, IGIInvestment], path: str | None = None) -> None:
    p = path or _IGI_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({k: asdict(v) for k, v in investments.items()}, fh, indent=2)


def load_igi_transactions(path: str | None = None) -> list[IGITransaction]:
    p = path or _IGI_TXN_FILE
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return [_from_dict_igi_txn(d) for d in raw]


def save_igi_transactions(txns: list[IGITransaction], path: str | None = None) -> None:
    p = path or _IGI_TXN_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump([asdict(t) for t in txns], fh, indent=2)


# ── Maturity split calculation ─────────────────────────────────────────────────

def compute_maturity_split(
    principal_outstanding: float,
    actual_total_received: float,
) -> dict:
    """
    Calculate principal returned, profit received, and principal loss
    from an actual maturity / withdrawal receipt.

    Expected profit is NEVER used here.
    """
    if actual_total_received >= principal_outstanding:
        return {
            "principal_returned": round(principal_outstanding, 6),
            "profit_received":    round(actual_total_received - principal_outstanding, 6),
            "principal_loss":     0.0,
        }
    return {
        "principal_returned": round(actual_total_received, 6),
        "profit_received":    0.0,
        "principal_loss":     round(principal_outstanding - actual_total_received, 6),
    }


# ── Business logic ─────────────────────────────────────────────────────────────

def add_igi_investment(
    investment_name:         str,
    institution:             str,
    currency:                str,
    principal_amount:        float,
    current_value:           float,
    start_date:              str,
    maturity_date:           str,
    expected_yield_pct:      float,
    profit_payment_structure: str,
    liquidity_type:          str,
    maturity_instruction:    str,
    notes:                   str = "",
    sharia_structure:        str = "Not Specified",
    sharia_status:           str = "Not Applicable",
    sharia_notes:            str = "",
    parent_investment_id:    str = "",
    status:                  str = "Active",
    path:                    str | None = None,
    txn_path:                str | None = None,
) -> tuple[IGIInvestment | None, str | None]:
    """Create and persist a new IGI investment + Initial Investment transaction."""
    if not investment_name.strip():
        return None, "Investment name is required."
    if not institution.strip():
        return None, "Institution is required."
    if principal_amount <= 0:
        return None, "Principal amount must be positive."
    if current_value < 0:
        return None, "Current value cannot be negative."
    if profit_payment_structure not in PROFIT_PAYMENT_STRUCTURES:
        return None, f"Invalid profit payment structure: {profit_payment_structure!r}."
    if liquidity_type not in LIQUIDITY_TYPES:
        return None, f"Invalid liquidity type: {liquidity_type!r}."
    if maturity_instruction not in MATURITY_INSTRUCTIONS:
        return None, f"Invalid maturity instruction: {maturity_instruction!r}."
    if status not in IGI_STATUSES:
        return None, f"Invalid status: {status!r}."

    inv_id = _new_id()
    inv = IGIInvestment(
        investment_id           = inv_id,
        investment_name         = investment_name.strip(),
        institution             = institution.strip(),
        currency                = currency,
        principal_amount        = round(principal_amount, 6),
        current_value           = round(current_value, 6),
        start_date              = start_date,
        maturity_date           = maturity_date,
        expected_yield_pct      = round(expected_yield_pct, 4),
        profit_payment_structure= profit_payment_structure,
        liquidity_type          = liquidity_type,
        status                  = status,
        maturity_instruction    = maturity_instruction,
        notes                   = notes.strip(),
        sharia_structure        = sharia_structure,
        sharia_status           = sharia_status,
        sharia_notes            = sharia_notes.strip(),
        parent_investment_id    = parent_investment_id,
        child_investment_id     = "",
        created_at              = _ts(),
    )

    investments = load_igi_investments(path=path)
    investments[inv_id] = inv
    save_igi_investments(investments, path=path)

    # Record the Initial Investment transaction
    if status != "Pending Funding":
        txns = load_igi_transactions(path=txn_path)
        txns.append(IGITransaction(
            txn_id        = _new_id(),
            investment_id = inv_id,
            date          = start_date,
            txn_type      = "Initial Investment",
            amount        = round(principal_amount, 6),
            notes         = f"Initial investment — {investment_name.strip()}",
            recorded_at   = _ts(),
        ))
        save_igi_transactions(txns, path=txn_path)

    return inv, None


def edit_igi_investment(
    investment_id:   str,
    path:            str | None = None,
    **kwargs,
) -> tuple[IGIInvestment | None, str | None]:
    """Edit non-status fields of an existing IGI investment."""
    investments = load_igi_investments(path=path)
    if investment_id not in investments:
        return None, f"Investment {investment_id!r} not found."
    inv = investments[investment_id]

    editable = {
        "investment_name", "institution", "currency", "current_value",
        "expected_yield_pct", "profit_payment_structure", "liquidity_type",
        "maturity_date", "maturity_instruction", "notes",
        "sharia_structure", "sharia_status", "sharia_notes",
    }
    for k, v in kwargs.items():
        if k in editable:
            setattr(inv, k, v)

    investments[investment_id] = inv
    save_igi_investments(investments, path=path)
    return inv, None


def record_igi_transaction(
    investment_id: str,
    txn_type:      str,
    amount:        float,
    txn_date:      str,
    notes:         str = "",
    path:          str | None = None,
    txn_path:      str | None = None,
) -> tuple[IGITransaction | None, str | None]:
    """Record a transaction against an existing IGI investment."""
    investments = load_igi_investments(path=path)
    if investment_id not in investments:
        return None, f"Investment {investment_id!r} not found."
    if txn_type not in IGI_TRANSACTION_TYPES:
        return None, f"Invalid transaction type: {txn_type!r}."
    if amount <= 0:
        return None, "Amount must be positive."

    txn = IGITransaction(
        txn_id        = _new_id(),
        investment_id = investment_id,
        date          = txn_date,
        txn_type      = txn_type,
        amount        = round(amount, 6),
        notes         = notes.strip(),
        recorded_at   = _ts(),
    )
    txns = load_igi_transactions(path=txn_path)
    txns.append(txn)
    save_igi_transactions(txns, path=txn_path)
    return txn, None


def process_maturity(
    investment_id:         str,
    actual_total_received: float,
    actual_maturity_date:  str,
    notes:                 str,
    final_action:          str | None = None,
    path:                  str | None = None,
    txn_path:              str | None = None,
) -> tuple[dict | None, str | None]:
    """
    Process maturity for a Maturity Action Required investment.

    final_action overrides the stored maturity_instruction for investments
    with maturity_instruction == "Manual Decision At Maturity".

    Returns a result dict with:
      principal_returned, profit_received, principal_loss,
      child_investment_id (if reinvest), action_taken
    """
    investments = load_igi_investments(path=path)
    if investment_id not in investments:
        return None, f"Investment {investment_id!r} not found."
    inv = investments[investment_id]
    if inv.status not in ("Maturity Action Required", "Active"):
        return None, f"Investment is not eligible for maturity processing (status: {inv.status})."
    if actual_total_received < 0:
        return None, "Actual total received cannot be negative."

    action = final_action or inv.maturity_instruction
    if action not in MATURITY_INSTRUCTIONS:
        return None, f"Invalid action: {action!r}."
    if action == "Manual Decision At Maturity" and not final_action:
        return None, "A final action must be selected for Manual Decision investments."

    split = compute_maturity_split(inv.principal_amount, actual_total_received)
    txns  = load_igi_transactions(path=txn_path)

    # Record actual transactions
    if split["principal_returned"] > 0:
        txns.append(IGITransaction(
            txn_id=_new_id(), investment_id=investment_id,
            date=actual_maturity_date, txn_type="Principal Returned",
            amount=split["principal_returned"],
            notes=f"[Maturity] {notes.strip()}", recorded_at=_ts(),
        ))
    if split["profit_received"] > 0:
        txns.append(IGITransaction(
            txn_id=_new_id(), investment_id=investment_id,
            date=actual_maturity_date, txn_type="Profit Received",
            amount=split["profit_received"],
            notes=f"[Maturity profit] {notes.strip()}", recorded_at=_ts(),
        ))
    save_igi_transactions(txns, path=txn_path)

    # Close original investment
    inv.status = "Closed"
    child_id = ""

    # Reinvestment paths
    if action in ("Reinvest Principal", "Reinvest Principal + Profit"):
        new_principal = split["principal_returned"]
        if action == "Reinvest Principal + Profit":
            new_principal = round(split["principal_returned"] + split["profit_received"], 6)

        new_inv = IGIInvestment(
            investment_id           = _new_id(),
            investment_name         = inv.investment_name + " [Reinvested]",
            institution             = inv.institution,
            currency                = inv.currency,
            principal_amount        = new_principal,
            current_value           = new_principal,
            start_date              = actual_maturity_date,
            maturity_date           = "",
            expected_yield_pct      = 0.0,
            profit_payment_structure= inv.profit_payment_structure,
            liquidity_type          = inv.liquidity_type,
            status                  = "Pending Funding",
            maturity_instruction    = "Principal Returned",
            notes                   = f"Draft — reinvested from {investment_id}. Confirm all terms.",
            sharia_structure        = inv.sharia_structure,
            sharia_status           = inv.sharia_status,
            sharia_notes            = "",
            parent_investment_id    = investment_id,
            child_investment_id     = "",
            created_at              = _ts(),
        )
        child_id = new_inv.investment_id
        inv.child_investment_id = child_id
        investments[child_id] = new_inv

    investments[investment_id] = inv
    save_igi_investments(investments, path=path)

    return {
        "principal_returned":  split["principal_returned"],
        "profit_received":     split["profit_received"],
        "principal_loss":      split["principal_loss"],
        "child_investment_id": child_id,
        "action_taken":        action,
    }, None


def process_early_withdrawal(
    investment_id:       str,
    withdrawal_date:     str,
    actual_total:        float,
    early_withdrawal_cost: float,
    notes:               str,
    path:                str | None = None,
    txn_path:            str | None = None,
) -> tuple[dict | None, str | None]:
    """Full early withdrawal (MVP — partial not supported)."""
    investments = load_igi_investments(path=path)
    if investment_id not in investments:
        return None, f"Investment {investment_id!r} not found."
    inv = investments[investment_id]
    if inv.status == "Closed":
        return None, "Investment is already closed."
    if actual_total < 0:
        return None, "Actual total received cannot be negative."
    if early_withdrawal_cost < 0:
        return None, "Early withdrawal cost cannot be negative."

    split = compute_maturity_split(inv.principal_amount, actual_total)
    txns  = load_igi_transactions(path=txn_path)

    if split["principal_returned"] > 0:
        txns.append(IGITransaction(
            txn_id=_new_id(), investment_id=investment_id,
            date=withdrawal_date, txn_type="Principal Returned",
            amount=split["principal_returned"],
            notes=f"[Early Withdrawal] {notes.strip()}", recorded_at=_ts(),
        ))
    if split["profit_received"] > 0:
        txns.append(IGITransaction(
            txn_id=_new_id(), investment_id=investment_id,
            date=withdrawal_date, txn_type="Profit Received",
            amount=split["profit_received"],
            notes=f"[Early Withdrawal profit] {notes.strip()}", recorded_at=_ts(),
        ))
    if early_withdrawal_cost > 0:
        txns.append(IGITransaction(
            txn_id=_new_id(), investment_id=investment_id,
            date=withdrawal_date, txn_type="Manual Adjustment",
            amount=early_withdrawal_cost,
            notes=f"[Early Withdrawal cost] {notes.strip()}", recorded_at=_ts(),
        ))
    save_igi_transactions(txns, path=txn_path)

    inv.status = "Closed"
    investments[investment_id] = inv
    save_igi_investments(investments, path=path)

    return {
        "principal_returned":     split["principal_returned"],
        "profit_received":        split["profit_received"],
        "principal_loss":         split["principal_loss"],
        "early_withdrawal_cost":  early_withdrawal_cost,
    }, None


def compute_igi_metrics(
    investment_id: str,
    path:          str | None = None,
    txn_path:      str | None = None,
    _investments:  "dict[str, IGIInvestment] | None" = None,
    _all_txns:     "list[IGITransaction] | None"     = None,
) -> dict:
    """
    Compute performance metrics for a single IGI investment.

    Only actual cash flows are used — expected yield is NEVER used.

    Pass ``_investments`` and ``_all_txns`` when the caller has already loaded
    the data to avoid redundant file reads (e.g. inside a render loop).
    """
    investments = _investments if _investments is not None else load_igi_investments(path=path)
    inv = investments.get(investment_id)
    if inv is None:
        return {}

    all_txns = _all_txns if _all_txns is not None else load_igi_transactions(path=txn_path)
    txns     = [t for t in all_txns if t.investment_id == investment_id]

    total_invested       = sum(t.amount for t in txns if t.txn_type in _IGI_OUTFLOW_TYPES)
    total_profit_received = sum(t.amount for t in txns if t.txn_type == "Profit Received")
    total_returned        = sum(t.amount for t in txns if t.txn_type == "Principal Returned")

    current_value    = inv.current_value
    unrealized_profit = current_value - (total_invested - total_returned)
    total_return      = total_profit_received + unrealized_profit

    # Build XIRR cash flows
    xirr_flows: list[tuple[str, float]] = []
    for t in sorted(txns, key=lambda x: x.date):
        if t.txn_type in _IGI_OUTFLOW_TYPES:
            xirr_flows.append((t.date, -t.amount))
        elif t.txn_type in _IGI_INFLOW_TYPES:
            xirr_flows.append((t.date, t.amount))
    # Add current value as a theoretical inflow today (for open investments)
    if inv.status not in ("Closed",) and current_value > 0:
        xirr_flows.append((_date.today().isoformat(), current_value - (total_invested - total_returned)))

    xirr = compute_xirr(xirr_flows)

    return {
        "investment_id":         investment_id,
        "current_value":         current_value,
        "total_invested":        total_invested,
        "total_profit_received": total_profit_received,
        "total_returned":        total_returned,
        "unrealized_profit":     unrealized_profit,
        "total_return":          total_return,
        "xirr":                  xirr,
    }
