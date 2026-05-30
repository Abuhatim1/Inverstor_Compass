"""
portfolio/valuation.py
----------------------
Centralized Portfolio Valuation Engine — single source of truth.

Every tab that shows portfolio totals, weights, P&L, or cash must call
calculate_portfolio_valuation() instead of independently summing holdings
or currencies.

FX rules:
  · base_market_value = local_market_value × fx_rate(local_ccy → base_ccy)
  · If local_ccy == base_ccy, fx_rate = 1.0 ("same")
  · USD/SAR default = 3.75 (pegged) when live rate unavailable
  · Values from different currencies are NEVER added directly

Cash rules:
  · Each Account has a base_currency; cash_value_base = balance × fx_rate
  · Cash is included in total_portfolio_value_base
  · Holdings value and cash value are reported separately

Weights:
  · invested_weight_pct = base_mv / holdings_value_base × 100
  · total_weight_pct    = base_mv / total_portfolio_value_base × 100

Sanity checks:
  · USD holding + SAR holding are never summed raw
  · invested_weight_pct totals ≈ 100 %
  · per_holding sum == holdings_value_base

Usage:
    from portfolio.valuation import calculate_portfolio_valuation, PortfolioValuation
    val = calculate_portfolio_valuation(holdings, accounts, base_ccy="SAR")
    print(val.total_portfolio_value_base)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# ── Per-holding row ────────────────────────────────────────────────────────────

@dataclass
class PerHoldingValuation:
    """Valuation breakdown for one holding in the base currency."""
    ticker:              str
    company_name:        str
    quantity:            float
    current_price:       float
    local_currency:      str
    local_market_value:  float   # qty × price
    local_cost_basis:    float   # qty × avg_cost
    fx_rate:             float   # local_ccy → base_ccy
    fx_source:           str     # "same" | "live" | "default" | "missing"
    base_market_value:   float   # local_mv × fx_rate
    base_cost_basis:     float   # local_cb × fx_rate
    base_unrealized_pnl: float   # base_mv - base_cb
    invested_weight_pct: float   # base_mv / holdings_value_base × 100
    total_weight_pct:    float   # base_mv / total_portfolio_value_base × 100
    missing_price:       bool    = False
    missing_fx:          bool    = False
    warning:             str     = ""


# ── Full portfolio valuation ───────────────────────────────────────────────────

@dataclass
class PortfolioValuation:
    """
    Full portfolio valuation — the ONLY object tabs should read for totals.
    All values are expressed in base_currency.
    """
    base_currency:               str
    holdings_value_base:         float   # invested assets (MV sum, base ccy)
    cash_value_base:             float   # all active accounts combined
    total_portfolio_value_base:  float   # holdings + cash
    invested_allocation_pct:     float   # holdings / total × 100
    cash_allocation_pct:         float   # cash    / total × 100
    total_cost_basis_base:       float
    unrealized_pnl_base:         float
    unrealized_pnl_pct:          float
    per_holding:                 list[PerHoldingValuation]
    fx_rates_used:               dict    # {ccy: FxRate}
    valuation_timestamp:         str
    warnings:                    list[str]
    n_holdings:                  int
    n_accounts:                  int     # active accounts


# ── Main engine ────────────────────────────────────────────────────────────────

def calculate_portfolio_valuation(
    holdings:   dict,                   # dict[str, Holding]
    accounts:   dict | None  = None,    # dict[str, Account] — pass None to skip cash
    base_ccy:   str          = "SAR",
    fx_rates:   dict | None  = None,    # pre-fetched {ccy: FxRate}; None = auto-fetch
) -> PortfolioValuation:
    """
    Compute the full portfolio valuation expressed in *base_ccy*.

    Parameters
    ----------
    holdings : dict[str, Holding]  — from load_holdings()
    accounts : dict[str, Account]  — from load_accounts(); None skips cash
    base_ccy : str                 — ISO code, e.g. "SAR", "USD"
    fx_rates : dict | None         — pass a pre-fetched {ccy: FxRate} dict to
                                     re-use existing session-state rates and
                                     avoid a second cache lookup.
                                     If None, fetches via get_rates_for_holdings()
                                     which requires a Streamlit session context.

    Returns PortfolioValuation — never raises; uses warnings for missing data.
    """
    from fx_rates import get_rates_for_holdings, get_rate

    _accounts = accounts or {}
    _warnings: list[str] = []
    now = datetime.now().isoformat()

    # ── Empty holdings shortcut (still compute cash if accounts exist) ────────
    if not holdings:
        # Resolve FX rates for account currencies so cash converts correctly.
        _acct_ccys = list({a.base_currency for a in _accounts.values()})
        if fx_rates is not None:
            _fx_empty: dict = dict(fx_rates)
            for _c in _acct_ccys:
                if _c not in _fx_empty:
                    _fx_empty[_c] = get_rate(_c, base_ccy)
        else:
            try:
                _fx_empty = get_rates_for_holdings(_acct_ccys, base_ccy) if _acct_ccys else {}
            except Exception:
                _fx_empty = {_c: get_rate(_c, base_ccy) for _c in _acct_ccys}

        _cash_base = 0.0
        _n_active  = 0
        for _a in _accounts.values():
            if not _a.active:
                continue
            _n_active += 1
            _r = _fx_empty.get(_a.base_currency)
            _rate_val = _r.rate if _r else 1.0
            _cash_base += _a.cash_balance * _rate_val
        _cash_base = round(_cash_base, 4)
        _total     = _cash_base

        return PortfolioValuation(
            base_currency              = base_ccy,
            holdings_value_base        = 0.0,
            cash_value_base            = _cash_base,
            total_portfolio_value_base = _total,
            invested_allocation_pct    = 0.0,
            cash_allocation_pct        = 100.0 if _total > 0 else 0.0,
            total_cost_basis_base      = 0.0,
            unrealized_pnl_base        = 0.0,
            unrealized_pnl_pct         = 0.0,
            per_holding                = [],
            fx_rates_used              = _fx_empty,
            valuation_timestamp        = now,
            warnings                   = [],
            n_holdings                 = 0,
            n_accounts                 = _n_active,
        )

    # ── Collect all needed currencies ─────────────────────────────────────────
    holding_ccys = list({getattr(h, "currency", "USD") for h in holdings.values()})
    account_ccys = list({a.base_currency for a in _accounts.values()})
    all_ccys     = list(set(holding_ccys + account_ccys))

    # ── Resolve FX rates ──────────────────────────────────────────────────────
    if fx_rates is not None:
        _fx = dict(fx_rates)
        # fill any missing currencies not in the pre-fetched dict
        for ccy in all_ccys:
            if ccy not in _fx:
                _fx[ccy] = get_rate(ccy, base_ccy)
    else:
        try:
            _fx = get_rates_for_holdings(all_ccys, base_ccy)
        except Exception as exc:
            _warnings.append(f"FX fetch failed ({exc}); using static defaults.")
            _fx = {ccy: get_rate(ccy, base_ccy) for ccy in all_ccys}

    def _rate(ccy: str) -> tuple[float, str]:
        """(rate, source) for ccy → base_ccy.  Falls back gracefully."""
        if ccy in _fx:
            return _fx[ccy].rate, _fx[ccy].source
        _warnings.append(f"No FX rate for {ccy}→{base_ccy}; using 1.0.")
        return 1.0, "missing"

    # ── Per-holding calculations ───────────────────────────────────────────────
    rows: list[PerHoldingValuation] = []
    sum_base_mv = 0.0
    sum_base_cb = 0.0

    for ticker, h in sorted(holdings.items()):
        ccy      = getattr(h, "currency", "USD")
        price    = float(h.current_price or 0.0)
        qty      = float(h.quantity or 0.0)
        avg_cost = float(h.avg_cost or 0.0)

        local_mv = qty * price
        local_cb = qty * avg_cost
        rate, src = _rate(ccy)
        base_mv  = round(local_mv * rate, 4)
        base_cb  = round(local_cb * rate, 4)
        base_pnl = round(base_mv - base_cb, 4)

        miss_p = price == 0.0 and qty > 0
        miss_f = src == "missing"
        if miss_p:
            _warnings.append(f"{ticker}: price = 0 — MV will be understated.")
        if miss_f:
            _warnings.append(f"{ticker}: no FX rate for {ccy} — using 1.0.")

        sum_base_mv += base_mv
        sum_base_cb += base_cb

        rows.append(PerHoldingValuation(
            ticker              = ticker,
            company_name        = h.company_name,
            quantity            = qty,
            current_price       = price,
            local_currency      = ccy,
            local_market_value  = round(local_mv, 4),
            local_cost_basis    = round(local_cb, 4),
            fx_rate             = rate,
            fx_source           = src,
            base_market_value   = base_mv,
            base_cost_basis     = base_cb,
            base_unrealized_pnl = base_pnl,
            invested_weight_pct = 0.0,  # computed below
            total_weight_pct    = 0.0,  # computed below
            missing_price       = miss_p,
            missing_fx          = miss_f,
            warning             = (
                "⚠️ Missing price"          if miss_p else
                f"⚠️ Missing FX ({ccy})"    if miss_f else ""
            ),
        ))

    # ── Cash calculations ─────────────────────────────────────────────────────
    sum_cash_base = 0.0
    n_active_accts = 0
    for a in _accounts.values():
        if not a.active:
            continue
        n_active_accts += 1
        a_rate, _ = _rate(a.base_currency)
        sum_cash_base += a.cash_balance * a_rate

    sum_base_mv    = round(sum_base_mv, 4)
    sum_base_cb    = round(sum_base_cb, 4)
    sum_cash_base  = round(sum_cash_base, 4)
    total_portfolio = round(sum_base_mv + sum_cash_base, 4)
    total_pnl      = round(sum_base_mv - sum_base_cb, 4)
    pnl_pct        = round(
        (total_pnl / sum_base_cb * 100.0) if sum_base_cb > 0 else 0.0, 2
    )
    invested_pct = round(
        (sum_base_mv   / total_portfolio * 100.0) if total_portfolio > 0 else 100.0, 2
    )
    cash_pct = round(
        (sum_cash_base / total_portfolio * 100.0) if total_portfolio > 0 else 0.0, 2
    )

    # ── Back-fill per-holding weights ─────────────────────────────────────────
    for r in rows:
        r.invested_weight_pct = round(
            (r.base_market_value / sum_base_mv    * 100.0) if sum_base_mv    > 0 else 0.0, 2
        )
        r.total_weight_pct = round(
            (r.base_market_value / total_portfolio * 100.0) if total_portfolio > 0 else 0.0, 2
        )

    # ── Sanity checks ─────────────────────────────────────────────────────────
    wt_sum = round(sum(r.invested_weight_pct for r in rows), 1)
    if rows and abs(wt_sum - 100.0) > 1.0:
        _warnings.append(f"Weight check: invested weights sum to {wt_sum}% (expected ~100%).")

    recon_mv = round(sum(r.base_market_value for r in rows), 2)
    if abs(recon_mv - sum_base_mv) > 0.02:
        _warnings.append(
            f"Reconciliation gap: per-holding total {recon_mv} ≠ holdings_value_base {sum_base_mv}."
        )

    return PortfolioValuation(
        base_currency              = base_ccy,
        holdings_value_base        = sum_base_mv,
        cash_value_base            = sum_cash_base,
        total_portfolio_value_base = total_portfolio,
        invested_allocation_pct    = invested_pct,
        cash_allocation_pct        = cash_pct,
        total_cost_basis_base      = sum_base_cb,
        unrealized_pnl_base        = total_pnl,
        unrealized_pnl_pct         = pnl_pct,
        per_holding                = rows,
        fx_rates_used              = _fx,
        valuation_timestamp        = now,
        warnings                   = _warnings,
        n_holdings                 = len(holdings),
        n_accounts                 = n_active_accts,
    )
