"""
portfolio/performance.py
------------------------
READ-ONLY performance analytics. Computes money-weighted return (XIRR),
total return, net external contributions, and growth attribution
(contributions vs. market growth).

Design rules (Bousala governance):
  · Read-only. Never modifies holdings, transactions, accounts, or cash.
  · Transactions / cash-ledger are the source of truth for flows.
  · All amounts are converted to base currency before aggregation.
  · No historical FX is stored, so historical flows are converted at the
    CURRENT FX rate. This is exact for pegged currencies (SAR/AED/QAR→USD)
    and an approximation otherwise — results carry an `approximate` flag.

Money-weighted return scope: the TOTAL portfolio (holdings + cash).
External flows only:
  · INITIAL_BALANCE / DEPOSIT  → money in  (investor outflow,  negative cf)
  · WITHDRAWAL                 → money out (investor inflow,   positive cf)
  · Terminal = current holdings+cash value (positive cf at as_of)
Internal flows (BUY, SELL, DIVIDEND, FEE, TRANSFER_*, FX_CONVERSION) are
EXCLUDED — they move value within the portfolio and are already captured by
the terminal value.

Mode A holdings (imported / "Record Existing Holding") have no BUY transaction
and no cash-ledger entry, so the capital that funded them is invisible to the
flow stream while their value appears in the terminal. To avoid wildly
overstating return, a synthetic opening outflow is added per holding:
    implied_opening_qty = stored_qty − Σ(BUY − SELL for that asset_id)
    opening_outflow      = implied_opening_qty × avg_cost  (if qty > 0)
dated at purchase_date (fallback added_at / as_of).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


# ── helpers ───────────────────────────────────────────────────────────────────

def _rate(ccy: str, base_ccy: str, fx_rates: dict | None) -> float:
    """FX multiplier: 1 unit of `ccy` → this many base units. Falls back to 1.0."""
    if not ccy or ccy == base_ccy:
        return 1.0
    r = (fx_rates or {}).get(ccy)
    return float(getattr(r, "rate", 1.0)) if r is not None else 1.0


def _parse_date(value) -> date:
    """Parse an ISO date / datetime string (or pass through a date). Today on failure."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return date.today()


# ── XIRR (bracketed bisection — robust, no external dependency) ─────────────────

def _npv(rate: float, flows: list[tuple[date, float]], t0: date) -> float:
    total = 0.0
    for d, amt in flows:
        years = (d - t0).days / 365.0
        total += amt / ((1.0 + rate) ** years)
    return total


def xirr(
    flows: list[tuple],
    lo: float = -0.9999,
    hi: float = 10.0,
    tol: float = 1e-7,
    max_iter: int = 200,
) -> float | None:
    """
    Money-weighted internal rate of return (annualized, as a decimal e.g. 0.12).

    Returns None when a rate cannot be reliably determined:
      · fewer than 2 flows
      · all flows share the same sign (no solution)
      · total span < 30 days (annualization explodes)
      · the root cannot be bracketed in (lo, hi)
    """
    norm = [(_parse_date(d), float(a)) for d, a in flows]
    if len(norm) < 2:
        return None
    amounts = [a for _, a in norm]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    norm.sort(key=lambda x: x[0])
    t0 = norm[0][0]
    if (norm[-1][0] - t0).days < 30:
        return None

    f_lo = _npv(lo, norm, t0)
    f_hi = _npv(hi, norm, t0)
    if f_lo == 0.0:
        return round(lo, 6)
    if f_hi == 0.0:
        return round(hi, 6)
    if (f_lo > 0.0) == (f_hi > 0.0):
        return None  # cannot bracket a sign change

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _npv(mid, norm, t0)
        if abs(f_mid) < tol or (hi - lo) / 2.0 < 1e-10:
            return round(mid, 6)
        if (f_mid > 0.0) == (f_lo > 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return round((lo + hi) / 2.0, 6)


# ── external flow stream ────────────────────────────────────────────────────────

_DEPOSIT_TYPES  = ("INITIAL_BALANCE", "DEPOSIT")
_WITHDRAW_TYPES = ("WITHDRAWAL",)


def build_external_flows(
    cash_entries: list,
    holdings:     dict,
    transactions: list,
    base_ccy:     str,
    fx_rates:     dict | None,
    as_of:        date | None = None,
) -> tuple[list[tuple[date, float]], float, bool]:
    """
    Build the investor external-cashflow stream (WITHOUT the terminal value).

    Returns (flows, net_contributions_base, approximate):
      · flows               — [(date, signed_base_amount)], deposits negative, withdrawals positive
      · net_contributions   — Σ deposits + Σ synthetic openings − Σ withdrawals (base)
      · approximate         — True if any non-base currency or synthetic opening was used
    """
    as_of = as_of or date.today()
    flows: list[tuple[date, float]] = []
    net_contrib = 0.0
    approximate = False

    # 1 — external cash movements
    for e in cash_entries or []:
        ttype = getattr(e, "transaction_type", "")
        ccy   = getattr(e, "currency", base_ccy)
        amt   = float(getattr(e, "amount", 0.0))
        if ttype not in _DEPOSIT_TYPES and ttype not in _WITHDRAW_TYPES:
            continue
        if ccy and ccy != base_ccy:
            approximate = True
        amt_base = amt * _rate(ccy, base_ccy, fx_rates)
        # investor cashflow sign is the inverse of the account cashflow sign
        flows.append((_parse_date(getattr(e, "date", as_of)), -amt_base))
        net_contrib += amt_base

    # 2 — synthetic opening outflows for Mode A holdings (no BUY transaction)
    txn_qty: dict[str, float] = {}
    for t in transactions or []:
        side = getattr(t, "side", "")
        aid  = getattr(t, "asset_id", "")
        if not aid or side not in ("BUY", "SELL"):
            continue
        q = float(getattr(t, "quantity", 0.0))
        txn_qty[aid] = txn_qty.get(aid, 0.0) + (q if side == "BUY" else -q)

    for h in (holdings or {}).values():
        aid      = getattr(h, "asset_id", "")
        stored   = float(getattr(h, "quantity", 0.0))
        implied  = stored - txn_qty.get(aid, 0.0)
        if implied <= 1e-9:
            continue
        ccy = getattr(h, "currency", base_ccy)
        if ccy and ccy != base_ccy:
            approximate = True
        approximate = True  # synthetic opening always uses current FX + avg_cost proxy
        opening_base = implied * float(getattr(h, "avg_cost", 0.0)) * _rate(ccy, base_ccy, fx_rates)
        d = getattr(h, "purchase_date", "") or getattr(h, "added_at", "") or as_of
        flows.append((_parse_date(d), -opening_base))
        net_contrib += opening_base

    return flows, round(net_contrib, 4), approximate


# ── result + orchestrator ───────────────────────────────────────────────────────

@dataclass
class PerformanceResult:
    current_value_base:     float          # holdings + cash, base ccy
    net_contributions_base: float          # net money the investor put in
    growth_base:            float          # current_value − net_contributions
    growth_pct:             float | None   # money-weighted simple total return %
    xirr_pct:               float | None   # annualized money-weighted return %
    n_flows:                int
    approximate:            bool
    notes:                  list[str] = field(default_factory=list)


def compute_performance(
    holdings:           dict,
    transactions:       list,
    cash_entries:       list,
    current_value_base: float,
    base_ccy:           str,
    fx_rates:           dict | None,
    as_of:              date | None = None,
) -> PerformanceResult:
    """
    Compute total-portfolio performance. Read-only. `current_value_base` must be
    the holdings+cash valuation in base ccy (from the valuation engine).
    """
    as_of = as_of or date.today()
    flows, net_contrib, approximate = build_external_flows(
        cash_entries, holdings, transactions, base_ccy, fx_rates, as_of,
    )

    notes: list[str] = []
    growth_base = round(current_value_base - net_contrib, 4)
    growth_pct  = round(growth_base / net_contrib * 100.0, 2) if net_contrib > 0 else None

    # terminal value closes the stream for XIRR
    xirr_flows = list(flows) + [(as_of, float(current_value_base))]
    rate = xirr(xirr_flows)
    xirr_pct = round(rate * 100.0, 2) if rate is not None else None
    if xirr_pct is None:
        notes.append(
            "Annualized return (XIRR) unavailable — needs ≥30 days of history "
            "and net contributions with a value change."
        )
    if approximate:
        notes.append(
            "Approximate — historical flows are converted at current FX rates; "
            "imported (existing) holdings use their average cost as the opening amount."
        )

    return PerformanceResult(
        current_value_base     = round(float(current_value_base), 4),
        net_contributions_base = net_contrib,
        growth_base            = growth_base,
        growth_pct             = growth_pct,
        xirr_pct               = xirr_pct,
        n_flows                = len(xirr_flows),
        approximate            = approximate,
        notes                  = notes,
    )
