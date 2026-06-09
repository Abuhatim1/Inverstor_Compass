"""
portfolio/tax_report.py
-----------------------
READ-ONLY realized-gains reporting for tax / record-keeping.

Source of truth: non-voided ClosedLot records (FIFO realized P&L).

Currency handling (architect guidance):
  · PRIMARY output is per-currency NATIVE totals — exact, because each lot's
    realized P&L is computed in the lot's own currency.
  · A single base-converted convenience total is provided at CURRENT FX and is
    explicitly labelled approximate. Per-lot history is never silently converted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


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
class PeriodCurrencyRow:
    period:       str       # "2026" or "2026-06"
    currency:     str
    proceeds:     float     # Σ sell_value (native)
    cost:         float     # Σ buy_value  (native)
    realized_pnl: float     # native
    fees:         float     # native
    n_lots:       int


@dataclass
class RealizedReport:
    rows:               list           # list[PeriodCurrencyRow], sorted
    by_currency_total:  dict           # {ccy: realized_pnl_native}
    base_total_approx:  float          # single base-converted total (approximate)
    base_ccy:           str
    approximate:        bool
    notes:              list[str] = field(default_factory=list)


def _period_key(iso_date: str, period: str) -> str:
    d = _parse_date(iso_date)
    return d.strftime("%Y") if period == "year" else d.strftime("%Y-%m")


def realized_report(
    closed_lots: list,
    base_ccy:    str,
    fx_rates:    dict | None,
    period:      str = "year",
) -> RealizedReport:
    """Group non-voided closed lots by (period, currency) with native totals."""
    groups: dict[tuple, PeriodCurrencyRow] = {}
    by_ccy_total: dict[str, float] = {}
    base_total = 0.0
    approximate = False

    for lot in closed_lots or []:
        if getattr(lot, "voided", False):
            continue
        ccy  = getattr(lot, "currency", base_ccy) or base_ccy
        pk   = _period_key(getattr(lot, "close_date", ""), period)
        pnl  = float(getattr(lot, "realized_pnl", 0.0))
        key  = (pk, ccy)

        row = groups.get(key)
        if row is None:
            row = PeriodCurrencyRow(period=pk, currency=ccy, proceeds=0.0,
                                    cost=0.0, realized_pnl=0.0, fees=0.0, n_lots=0)
            groups[key] = row
        row.proceeds     = round(row.proceeds + float(getattr(lot, "sell_value", 0.0)), 4)
        row.cost         = round(row.cost + float(getattr(lot, "buy_value", 0.0)), 4)
        row.realized_pnl = round(row.realized_pnl + pnl, 4)
        row.fees         = round(row.fees + float(getattr(lot, "sell_fees", 0.0)), 4)
        row.n_lots      += 1

        by_ccy_total[ccy] = round(by_ccy_total.get(ccy, 0.0) + pnl, 4)
        if ccy != base_ccy:
            approximate = True
        base_total += pnl * _rate(ccy, base_ccy, fx_rates)

    rows = sorted(groups.values(), key=lambda r: (r.period, r.currency), reverse=True)
    notes: list[str] = []
    if approximate:
        notes.append("Per-currency totals are exact; the base total uses current FX (approximate).")

    return RealizedReport(
        rows              = rows,
        by_currency_total = by_ccy_total,
        base_total_approx = round(base_total, 4),
        base_ccy          = base_ccy,
        approximate       = approximate,
        notes             = notes,
    )
