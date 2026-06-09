"""
portfolio/zakat.py
------------------
READ-ONLY Zakat estimator for an individual investor.

Simplified, conservative method (zakat on tradable investment assets):
    zakatable = market value of holdings + zakatable cash
    net_base  = max(0, zakatable − short-term deductible liabilities)
    zakat_due = net_base × rate

Rate:
    · 2.5%    (lunar / Hijri year)   — default
    · 2.5775% (Gregorian year)       — optional, accounts for the longer solar year

IMPORTANT: this is an ESTIMATE for planning only — Zakat rulings vary by school
and by holding intent (trading vs. long-term). Users should confirm with a
qualified scholar.

Already-paid Zakat (recorded as a SETTLEMENT with category "Zakat") has already
reduced cash balances via its FEE ledger entry, so the zakat base self-adjusts.
Paid Zakat is reported here for INFORMATION ONLY and is never subtracted from the
base again (that would double-count).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

RATE_LUNAR     = 0.025      # 2.5%   — Hijri year
RATE_GREGORIAN = 0.025775   # 2.5775% — solar year


def _rate_fx(ccy: str, base_ccy: str, fx_rates: dict | None) -> float:
    if not ccy or ccy == base_ccy:
        return 1.0
    r = (fx_rates or {}).get(ccy)
    return float(getattr(r, "rate", 1.0)) if r is not None else 1.0


def _parse_date(value) -> date:
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


@dataclass
class ZakatResult:
    holdings_base:    float
    cash_base:        float
    zakatable_base:   float          # holdings + cash
    deductible_base:  float          # short-term liabilities removed
    net_base:         float          # max(0, zakatable − deductible)
    rate:             float
    rate_label:       str
    zakat_due:        float
    paid_to_date:     float          # informational only
    note:             str = (
        "Estimate for planning only — Zakat rules vary by school and holding "
        "intent. Confirm with a qualified scholar."
    )


def compute_zakat(
    holdings_value_base:        float,
    cash_base:                  float,
    deductible_liabilities_base: float = 0.0,
    rate:                       float = RATE_LUNAR,
) -> ZakatResult:
    """Compute the Zakat estimate. Pure arithmetic — mutates nothing."""
    holdings_value_base = round(float(holdings_value_base), 4)
    cash_base           = round(float(cash_base), 4)
    deductible          = round(max(0.0, float(deductible_liabilities_base)), 4)

    zakatable = round(holdings_value_base + cash_base, 4)
    net_base  = round(max(0.0, zakatable - deductible), 4)
    due       = round(net_base * rate, 4)
    label     = "Gregorian (2.5775%)" if abs(rate - RATE_GREGORIAN) < 1e-9 else "Lunar (2.5%)"

    return ZakatResult(
        holdings_base   = holdings_value_base,
        cash_base       = cash_base,
        zakatable_base  = zakatable,
        deductible_base = deductible,
        net_base        = net_base,
        rate            = rate,
        rate_label      = label,
        zakat_due       = due,
        paid_to_date    = 0.0,
    )


def zakat_paid_to_date(
    transactions: list,
    base_ccy:     str,
    fx_rates:     dict | None,
    since:        date | None = None,
) -> float:
    """
    Sum Zakat already PAID (SETTLEMENT category "Zakat"), base ccy, as a positive
    number. Informational only — do not subtract from the zakat base.
    """
    total = 0.0
    for t in transactions or []:
        if getattr(t, "side", "") != "SETTLEMENT":
            continue
        if getattr(t, "settlement_category", "") != "Zakat":
            continue
        if since is not None and _parse_date(getattr(t, "date", "")) < since:
            continue
        amt = float(getattr(t, "settlement_amount", 0.0))      # stored negative (expense)
        ccy = getattr(t, "settlement_currency", "") or base_ccy
        total += abs(amt) * _rate_fx(ccy, base_ccy, fx_rates)
    return round(total, 4)
