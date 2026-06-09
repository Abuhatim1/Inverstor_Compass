"""
portfolio/income.py
-------------------
READ-ONLY dividend / income analytics.

Source of truth: SETTLEMENT transactions with settlement_category == "Dividend"
(record_settlement writes one SETTLEMENT transaction AND one cash-ledger entry;
using the transaction avoids double-counting the ledger mirror).

Reports realized income only — no speculative forward projections. Provides:
  · lifetime / YTD / trailing-12-month totals (base ccy)
  · by-ticker and by-month breakdowns
  · per-currency native totals (exact)
  · yield-on-cost and current yield

Currency: settlement amounts are converted to base at CURRENT FX (approximate
for non-pegged currencies); native per-currency totals are exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


def _rate(ccy: str, base_ccy: str, fx_rates: dict | None) -> float:
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
class DividendSummary:
    total_base:        float
    ytd_base:          float
    ttm_base:          float            # trailing 12 months
    by_ticker:         dict             # {ticker: base_total}
    by_month:          dict             # {"YYYY-MM": base_total}
    by_currency:       dict             # {ccy: native_total}  (exact)
    n_payments:        int
    yield_on_cost_pct: float | None     # ttm / cost_basis
    current_yield_pct: float | None     # ttm / market_value
    approximate:       bool
    notes:             list[str] = field(default_factory=list)


def dividend_summary(
    transactions:    list,
    base_ccy:        str,
    fx_rates:        dict | None,
    cost_basis_base: float | None = None,
    market_value_base: float | None = None,
    as_of:           date | None = None,
) -> DividendSummary:
    """Aggregate dividend settlements into an income summary. Read-only."""
    as_of      = as_of or date.today()
    ytd_start  = date(as_of.year, 1, 1)
    ttm_start  = as_of - timedelta(days=365)

    total = ytd = ttm = 0.0
    by_ticker: dict[str, float] = {}
    by_month:  dict[str, float] = {}
    by_ccy:    dict[str, float] = {}
    n = 0
    approximate = False

    for t in transactions or []:
        if getattr(t, "side", "") != "SETTLEMENT":
            continue
        if getattr(t, "settlement_category", "") != "Dividend":
            continue
        amt = float(getattr(t, "settlement_amount", 0.0))
        if amt == 0.0:
            continue
        ccy = getattr(t, "settlement_currency", "") or base_ccy
        if ccy != base_ccy:
            approximate = True
        d        = _parse_date(getattr(t, "date", as_of))
        amt_base = amt * _rate(ccy, base_ccy, fx_rates)

        total += amt_base
        if d >= ytd_start:
            ytd += amt_base
        if d >= ttm_start:
            ttm += amt_base

        tkr = getattr(t, "ticker", "") or "(portfolio)"
        by_ticker[tkr] = round(by_ticker.get(tkr, 0.0) + amt_base, 4)
        mk = d.strftime("%Y-%m")
        by_month[mk]   = round(by_month.get(mk, 0.0) + amt_base, 4)
        by_ccy[ccy]    = round(by_ccy.get(ccy, 0.0) + amt, 4)
        n += 1

    yoc = (round(ttm / cost_basis_base * 100.0, 2)
           if cost_basis_base and cost_basis_base > 0 else None)
    cy  = (round(ttm / market_value_base * 100.0, 2)
           if market_value_base and market_value_base > 0 else None)

    notes: list[str] = []
    if approximate:
        notes.append("Base totals use current FX; per-currency totals are exact.")

    return DividendSummary(
        total_base        = round(total, 4),
        ytd_base          = round(ytd, 4),
        ttm_base          = round(ttm, 4),
        by_ticker         = by_ticker,
        by_month          = dict(sorted(by_month.items())),
        by_currency       = by_ccy,
        n_payments        = n,
        yield_on_cost_pct = yoc,
        current_yield_pct = cy,
        approximate       = approximate,
        notes             = notes,
    )
