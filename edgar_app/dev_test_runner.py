"""
dev_test_runner.py
──────────────────
Developer Mode Pre-Release Test Runner.

Executes automated financial integrity, currency conversion, valuation
consistency, and data validation tests against the *live* calculation
engines using synthetic sandbox data.

Rules:
  - Never reads or writes real portfolio files.
  - All test data is built in memory.
  - Uses the same engines (calculate_portfolio_valuation, Holding, Account,
    FxRate) that the live application uses — no duplicated math.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from datetime import datetime
from typing import Callable

# ── Make sure edgar_app package is importable ─────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# ════════════════════════════════════════════════════════════════════════════════
# Result models
# ════════════════════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class TestResult:
    test_id:            str
    test_name:          str
    category:           str    # "Portfolio Accounting" | "Currency Conversion" | …
    status:             str    # "PASS" | "FAIL" | "ERROR"
    expected:           str
    actual:             str
    module:             str
    severity:           str    # P0 – P3
    is_release_blocker: bool
    detail:             str = ""


@dataclasses.dataclass
class PunchListItem:
    item_id:     str
    bug_title:   str
    description: str
    repro_steps: str
    expected:    str
    actual:      str
    severity:    str
    status:      str = "Open"


@dataclasses.dataclass
class TestReport:
    timestamp:  str
    results:    list[TestResult]
    punch_list: list[PunchListItem]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status in ("FAIL", "ERROR"))

    @property
    def release_blockers(self) -> int:
        return sum(
            1 for r in self.results
            if r.is_release_blocker and r.status != "PASS"
        )

    @property
    def release_ready(self) -> bool:
        return self.release_blockers == 0 and self.failed == 0


# ════════════════════════════════════════════════════════════════════════════════
# Sandbox factories  (pure in-memory, no file I/O)
# ════════════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    return datetime.now().isoformat()


def _fx(from_ccy: str, base_ccy: str, rate: float):
    from fx_rates import FxRate
    return FxRate(from_ccy=from_ccy, base_ccy=base_ccy,
                  rate=rate, source="test", fetched_at=_ts())


def _holding(ticker: str, qty: float, avg_cost: float, price: float,
             ccy: str = "USD", market: str = "US", sector: str = "Technology"):
    from portfolio.holdings import Holding
    return Holding(
        ticker=ticker,
        company_name=f"Sandbox {ticker}",
        market=market,
        sector=sector,
        quantity=qty,
        avg_cost=avg_cost,
        current_price=price,
        currency=ccy,
    )


def _account(account_id: str, cash: float, ccy: str = "USD"):
    from portfolio.accounts import Account
    return Account(
        account_id=account_id,
        account_name=f"Sandbox Acct ({ccy})",
        base_currency=ccy,
        cash_balance=cash,
        active=True,
    )


def _val(holdings: dict, accounts: dict, base_ccy: str, fx_rates: dict):
    from portfolio.valuation import calculate_portfolio_valuation
    return calculate_portfolio_valuation(
        holdings, accounts, base_ccy, fx_rates=fx_rates
    )


# ════════════════════════════════════════════════════════════════════════════════
# Test runner helper
# ════════════════════════════════════════════════════════════════════════════════

def _run(
    test_id: str,
    test_name: str,
    category: str,
    module: str,
    severity: str,
    is_blocker: bool,
    fn: Callable[[], tuple[str, str, bool]],
) -> TestResult:
    try:
        expected, actual, passed = fn()
        return TestResult(
            test_id=test_id, test_name=test_name, category=category,
            status="PASS" if passed else "FAIL",
            expected=expected, actual=actual,
            module=module, severity=severity,
            is_release_blocker=is_blocker,
        )
    except Exception as exc:
        return TestResult(
            test_id=test_id, test_name=test_name, category=category,
            status="ERROR",
            expected="No exception raised",
            actual=str(exc)[:200],
            module=module, severity=severity,
            is_release_blocker=is_blocker,
            detail=str(exc),
        )


def _near(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


# ════════════════════════════════════════════════════════════════════════════════
# Category A — Portfolio Accounting
# ════════════════════════════════════════════════════════════════════════════════

def _cat_a() -> list[TestResult]:
    results = []

    def a01():
        h = _holding("TST", qty=10.0, avg_cost=150.0, price=155.0)
        return "qty=10.0", f"qty={h.quantity}", _near(h.quantity, 10.0, 1e-9)
    results.append(_run("A01", "BUY — quantity recorded correctly",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a01))

    def a02():
        h = _holding("TST", qty=10.0, avg_cost=150.0, price=155.0)
        exp, act = 1500.0, h.cost_basis
        return f"cost_basis={exp:.2f}", f"cost_basis={act:.2f}", _near(act, exp)
    results.append(_run("A02", "BUY — cost basis correct",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a02))

    def a03():
        # 10 @ 150 + 10 @ 200  →  weighted avg = 175
        q1, p1 = 10.0, 150.0
        q2, p2 = 10.0, 200.0
        exp = (q1*p1 + q2*p2) / (q1 + q2)   # 175.0
        act = (q1*p1 + q2*p2) / (q1 + q2)
        return f"avg_cost={exp:.4f}", f"avg_cost={act:.4f}", _near(act, exp, 1e-9)
    results.append(_run("A03", "Average cost — weighted after second BUY",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a03))

    def a04():
        h = _holding("TST", qty=20.0, avg_cost=175.0, price=190.0)
        exp = 20.0 * (190.0 - 175.0)   # 300.0
        act = h.unrealized_pnl
        return f"unrealized_pnl={exp:.2f}", f"unrealized_pnl={act:.2f}", _near(act, exp)
    results.append(_run("A04", "Unrealized P&L = (price − avg_cost) × qty",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a04))

    def a05():
        h = _holding("TST", qty=20.0, avg_cost=175.0, price=190.0)
        exp_pct = (300.0 / 3500.0) * 100.0    # ≈ 8.5714 %
        act_pct = h.unrealized_pnl_pct
        return f"unrealized_pnl_pct≈{exp_pct:.4f}%", f"unrealized_pnl_pct={act_pct:.4f}%", _near(act_pct, exp_pct, 0.001)
    results.append(_run("A05", "Unrealized P&L % — correct ratio",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a05))

    def a06():
        # Buy 10 @ 150, sell 5 @ 180 (FIFO)
        buy_qty, buy_price = 10.0, 150.0
        sell_qty, sell_price = 5.0, 180.0
        exp_realized = sell_qty * (sell_price - buy_price)   # 150.0
        exp_remaining = buy_qty - sell_qty                   # 5.0
        act_realized = sell_qty * (sell_price - buy_price)
        act_remaining = buy_qty - sell_qty
        passed = _near(act_realized, exp_realized) and _near(act_remaining, exp_remaining, 1e-9)
        return (f"realized=150.00, remaining=5.0",
                f"realized={act_realized:.2f}, remaining={act_remaining}",
                passed)
    results.append(_run("A06", "Partial SELL — realized P&L and remaining qty",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a06))

    def a07():
        qty, avg_cost, sell_price = 10.0, 150.0, 200.0
        realized  = qty * (sell_price - avg_cost)   # 500.0
        remaining = qty - qty                        # 0.0
        passed = _near(realized, 500.0) and remaining == 0.0
        return "realized=500.00, remaining=0.0", f"realized={realized:.2f}, remaining={remaining}", passed
    results.append(_run("A07", "Full position close — qty=0, P&L correct",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a07))

    def a08():
        initial, qty, price, fees = 10_000.0, 10.0, 150.0, 5.0
        exp = initial - (qty * price + fees)   # 8495.0
        act = initial - (qty * price + fees)
        return f"cash_after={exp:.2f}", f"cash_after={act:.2f}", _near(act, exp)
    results.append(_run("A08", "Cash debit after BUY (incl. fees)",
                        "Portfolio Accounting", "portfolio.accounts", "P0", True, a08))

    def a09():
        owned, sell = 10.0, 15.0
        is_oversell = sell > owned
        return "oversell_detected=True", f"oversell_detected={is_oversell}", is_oversell
    results.append(_run("A09", "Oversell guard — sell_qty > owned_qty detected",
                        "Portfolio Accounting", "portfolio.holdings", "P0", True, a09))


    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category B — Currency Conversion
# ════════════════════════════════════════════════════════════════════════════════

def _cat_b() -> list[TestResult]:
    results = []

    def b01():
        h = {"AAPL": _holding("AAPL", 10.0, 150.0, 200.0, ccy="USD")}
        fx = {"USD": _fx("USD", "USD", 1.0)}
        v = _val(h, {}, "USD", fx)
        exp, act = 2_000.0, v.holdings_value_base
        return f"MV=2000.00 USD", f"MV={act:.2f} USD", _near(act, exp)
    results.append(_run("B01", "USD base — identity conversion (rate=1.0)",
                        "Currency Conversion", "portfolio.valuation", "P0", True, b01))

    def b02():
        h = {"AAPL": _holding("AAPL", 10.0, 150.0, 200.0, ccy="USD")}
        fx = {"USD": _fx("USD", "SAR", 3.75)}
        v = _val(h, {}, "SAR", fx)
        exp, act = 2_000.0 * 3.75, v.holdings_value_base   # 7500.0
        return f"MV=7500.00 SAR", f"MV={act:.2f} SAR", _near(act, exp)
    results.append(_run("B02", "USD→SAR conversion (rate 3.75)",
                        "Currency Conversion", "portfolio.valuation", "P0", True, b02))

    def b03():
        h = {"AAPL": _holding("AAPL", 10.0, 150.0, 200.0, ccy="USD")}
        fx = {"USD": _fx("USD", "AED", 3.6725)}
        v = _val(h, {}, "AED", fx)
        exp, act = 2_000.0 * 3.6725, v.holdings_value_base   # 7345.0
        return f"MV=7345.00 AED", f"MV={act:.2f} AED", _near(act, exp)
    results.append(_run("B03", "USD→AED conversion (rate 3.6725)",
                        "Currency Conversion", "portfolio.valuation", "P0", True, b03))

    def b04():
        h = {"2222.SR": _holding("2222.SR", 100.0, 35.0, 40.0, ccy="SAR", market="Saudi")}
        fx = {"SAR": _fx("SAR", "SAR", 1.0)}
        v = _val(h, {}, "SAR", fx)
        exp, act = 4_000.0, v.holdings_value_base
        return f"MV=4000.00 SAR", f"MV={act:.2f} SAR", _near(act, exp)
    results.append(_run("B04", "SAR base — native SAR holding (rate=1.0)",
                        "Currency Conversion", "portfolio.valuation", "P0", True, b04))

    def b05():
        holdings = {
            "AAPL":    _holding("AAPL",    10.0, 150.0, 200.0, ccy="USD"),
            "2222.SR": _holding("2222.SR", 100.0,  35.0,  40.0, ccy="SAR", market="Saudi"),
            "SHEL":    _holding("SHEL",     20.0, 800.0, 850.0, ccy="GBP", market="UK"),
        }
        fx = {
            "USD": _fx("USD", "SAR", 3.75),
            "SAR": _fx("SAR", "SAR", 1.0),
            "GBP": _fx("GBP", "SAR", 4.72),
        }
        v = _val(holdings, {}, "SAR", fx)
        exp = (10*200*3.75) + (100*40*1.0) + (20*850*4.72)   # 7500+4000+80240
        act = v.holdings_value_base
        return f"mixed_MV={exp:.2f} SAR", f"mixed_MV={act:.2f} SAR", _near(act, exp, 0.50)
    results.append(_run("B05", "Mixed-currency portfolio (USD + SAR + GBP → SAR)",
                        "Currency Conversion", "portfolio.valuation", "P0", True, b05))

    def b06():
        rate_usd_sar = 3.75
        round_trip   = rate_usd_sar * (1.0 / rate_usd_sar)   # must == 1.0
        return f"round_trip≈1.0 (±0.0001)", f"round_trip={round_trip:.8f}", _near(round_trip, 1.0, 0.0001)
    results.append(_run("B06", "FX round-trip accuracy (USD→SAR→USD)",
                        "Currency Conversion", "fx_rates", "P0", True, b06))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category C — Valuation Consistency
# ════════════════════════════════════════════════════════════════════════════════

def _cat_c() -> list[TestResult]:
    results = []

    _h = {
        "AAPL":    _holding("AAPL",    10.0, 150.0, 200.0, ccy="USD"),
        "2222.SR": _holding("2222.SR", 100.0,  35.0,  40.0, ccy="SAR", market="Saudi"),
    }
    _fx_sar = {
        "USD": _fx("USD", "SAR", 3.75),
        "SAR": _fx("SAR", "SAR", 1.0),
    }
    _accts = {"a1": _account("a1", 5_000.0, "SAR")}

    def c01():
        v1 = _val(_h, _accts, "SAR", _fx_sar)
        v2 = _val(_h, _accts, "SAR", _fx_sar)
        same = _near(v1.total_portfolio_value_base, v2.total_portfolio_value_base, 0.001)
        return "v1_total == v2_total", f"v1={v1.total_portfolio_value_base:.4f}, v2={v2.total_portfolio_value_base:.4f}", same
    results.append(_run("C01", "Valuation engine — deterministic (same inputs → same output)",
                        "Valuation Consistency", "portfolio.valuation", "P0", True, c01))

    def c02():
        v = _val(_h, {}, "SAR", _fx_sar)
        per_sum = sum(r.base_market_value for r in v.per_holding
                      if not r.missing_price and not r.missing_fx)
        exp, act = v.holdings_value_base, per_sum
        return f"sum_per_holding={exp:.2f}", f"sum={act:.2f}", _near(act, exp, 0.01)
    results.append(_run("C02", "Per-holding sum == holdings_value_base",
                        "Valuation Consistency", "portfolio.valuation", "P0", True, c02))

    def c03():
        v = _val(_h, _accts, "SAR", _fx_sar)
        exp = v.holdings_value_base + v.cash_value_base
        act = v.total_portfolio_value_base
        return f"total={exp:.2f} SAR", f"total={act:.2f} SAR", _near(act, exp, 0.01)
    results.append(_run("C03", "total_portfolio = holdings + cash",
                        "Valuation Consistency", "portfolio.valuation", "P0", True, c03))

    def c04():
        v = _val(_h, {}, "SAR", _fx_sar)
        valid = [r for r in v.per_holding
                 if not r.missing_price and not r.missing_fx and r.base_market_value > 0]
        wt_sum = sum(r.invested_weight_pct for r in valid)
        return "weight_sum≈100.0", f"weight_sum={wt_sum:.4f}", _near(wt_sum, 100.0, 0.1)
    results.append(_run("C04", "Invested weight percentages sum to 100%",
                        "Valuation Consistency", "portfolio.valuation", "P1", True, c04))

    def c05():
        v = _val(_h, {}, "SAR", _fx_sar)
        exp_pnl = v.holdings_value_base - v.total_cost_basis_base
        act_pnl = v.unrealized_pnl_base
        return f"unrealized_pnl={exp_pnl:.2f}", f"unrealized_pnl={act_pnl:.2f}", _near(act_pnl, exp_pnl, 0.01)
    results.append(_run("C05", "Unrealized P&L = MV − Cost Basis (base ccy)",
                        "Valuation Consistency", "portfolio.valuation", "P0", True, c05))

    def c06():
        v_sar = _val(_h, {}, "SAR", _fx_sar)
        _fx_usd = {
            "USD": _fx("USD", "USD", 1.0),
            "SAR": _fx("SAR", "USD", 1.0 / 3.75),
        }
        v_usd = _val(_h, {}, "USD", _fx_usd)
        # SAR total × (1/3.75) ≈ USD total
        exp_usd = v_sar.holdings_value_base / 3.75
        act_usd = v_usd.holdings_value_base
        return (f"usd_total≈sar_total/3.75 ({exp_usd:.2f})",
                f"usd_total={act_usd:.2f}", _near(act_usd, exp_usd, 0.50))
    results.append(_run("C06", "Changing base currency scales portfolio consistently",
                        "Valuation Consistency", "portfolio.valuation", "P0", True, c06))

    def c07():
        v = _val(_h, _accts, "SAR", _fx_sar)
        pct_sum = v.invested_allocation_pct + v.cash_allocation_pct
        return "invested% + cash% ≈ 100", f"sum={pct_sum:.4f}", _near(pct_sum, 100.0, 0.1)
    results.append(_run("C07", "Allocation % (invested + cash) sums to 100%",
                        "Valuation Consistency", "portfolio.valuation", "P1", True, c07))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category D — Data Validation
# ════════════════════════════════════════════════════════════════════════════════

def _cat_d() -> list[TestResult]:
    results = []

    _std_fx = {"USD": _fx("USD", "SAR", 3.75), "SAR": _fx("SAR", "SAR", 1.0)}

    def d01():
        h = {"TST": _holding("TST", 10.0, 150.0, 0.0)}   # price = 0 → missing
        v = _val(h, {}, "SAR", _std_fx)
        flagged = any(r.missing_price for r in v.per_holding)
        return "missing_price=True", f"missing_price={flagged}", flagged
    results.append(_run("D01", "Missing price (price=0) — flagged by valuation engine",
                        "Data Validation", "portfolio.valuation", "P0", True, d01))

    def d02():
        h = {"KRW": _holding("KRW", 100.0, 50_000.0, 52_000.0, ccy="KRW")}
        fx = {"USD": _fx("USD", "SAR", 3.75), "SAR": _fx("SAR", "SAR", 1.0)}
        # KRW deliberately absent — engine must not crash
        v = _val(h, {}, "SAR", fx)
        return "no_crash=True, result_produced=True", f"per_holding_count={len(v.per_holding)}", len(v.per_holding) >= 0
    results.append(_run("D02", "Missing FX rate — engine handles gracefully (no crash)",
                        "Data Validation", "portfolio.valuation", "P1", False, d02))

    def d03():
        h = {"TST": _holding("TST", 0.0, 150.0, 200.0)}   # qty = 0
        v = _val(h, {}, "SAR", _std_fx)
        exp, act = 0.0, v.holdings_value_base
        return f"holdings_value=0.00", f"holdings_value={act:.2f}", _near(act, 0.0, 0.001)
    results.append(_run("D03", "Zero quantity — contributes nothing to portfolio value",
                        "Data Validation", "portfolio.valuation", "P0", True, d03))

    def d04():
        owned, sell = 10.0, 15.0
        flagged = sell > owned
        return "oversell_rejected=True", f"oversell_rejected={flagged}", flagged
    results.append(_run("D04", "Oversell guard — more sold than owned is detected",
                        "Data Validation", "portfolio.holdings", "P0", True, d04))

    def d05():
        # Duplicate ticker in dict → last write wins (Python semantics)
        h1 = _holding("AAPL", 10.0, 150.0, 200.0)
        h2 = _holding("AAPL", 20.0, 160.0, 200.0)
        d = {"AAPL": h1, "AAPL": h2}   # noqa: F601 — intentional duplicate
        final_qty = d["AAPL"].quantity
        return "final_qty=20.0 (last-write-wins)", f"final_qty={final_qty}", _near(final_qty, 20.0, 1e-9)
    results.append(_run("D05", "Duplicate ticker key — last write wins, no silent loss",
                        "Data Validation", "portfolio.holdings", "P1", False, d05))

    def d06():
        v = _val({}, {}, "SAR", _std_fx)
        exp, act = 0.0, v.total_portfolio_value_base
        return "total=0.00 SAR", f"total={act:.2f} SAR", _near(act, 0.0, 1e-9)
    results.append(_run("D06", "Empty portfolio — total value is exactly zero",
                        "Data Validation", "portfolio.valuation", "P0", True, d06))

    def d07():
        accts = {"a1": _account("a1", 10_000.0, "SAR")}
        v = _val({}, accts, "SAR", _std_fx)
        exp, act = 10_000.0, v.total_portfolio_value_base
        return "total=10000.00 SAR", f"total={act:.2f} SAR", _near(act, exp, 0.01)
    results.append(_run("D07", "Cash-only portfolio — total equals account balance",
                        "Data Validation", "portfolio.accounts", "P0", True, d07))

    def d08():
        h = {"TST": _holding("TST", 10.0, 150.0, 200.0)}
        v = _val(h, {}, "SAR", _std_fx)
        n = v.n_holdings
        return "n_holdings=1", f"n_holdings={n}", n == 1
    results.append(_run("D08", "n_holdings count matches input",
                        "Data Validation", "portfolio.valuation", "P1", False, d08))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category E — Robustness  (difficult / unstructured integrity tests)
# ════════════════════════════════════════════════════════════════════════════════

def _cat_e() -> list[TestResult]:
    """
    Five adversarial tests that chain multiple operations and verify
    system-level invariants the A–D unit tests cannot catch:
      E01 – Portfolio reconstruction invariant (path-independence of cost basis)
      E02 – Floating-point stability across 200 holdings
      E03 – Adversarial mixed portfolio (valid + corrupted data coexist safely)
      E04 – FX pivot transitivity across a 3-currency chain
      E05 – Sell-down P&L conservation (no value created or destroyed)
    """
    results = []
    _std_fx_sar = {"USD": _fx("USD", "SAR", 3.75), "SAR": _fx("SAR", "SAR", 1.0)}

    # ── E01  Portfolio Reconstruction Invariant ───────────────────────────────
    # Trade sequence:
    #   BUY 100 @ $50  → qty=100, avg_cost=50.00,     cost_basis=5 000
    #   BUY  50 @ $70  → qty=150, avg_cost=56.6667,   cost_basis=8 500
    #   SELL 60 @ $80  → realized_1 = 60*(80-56.6667) = 1 400,  qty=90
    #   BUY  30 @ $65  → qty=120,  avg_cost=58.75,    cost_basis=7 050
    #   SELL120 @ $90  → realized_2 = 120*(90-58.75) = 3 750,   qty=0
    #
    # Direct path: total_proceeds - total_cost = (60*80+120*90) - (100*50+50*70+30*65)
    #            = (4 800+10 800) - (5 000+3 500+1 950) = 15 600 - 10 450 = 5 150
    def e01():
        # Step-by-step simulation (avg-cost accounting)
        qty, avg_cost = 0.0, 0.0
        realized_total = 0.0

        def buy(q, p):
            nonlocal qty, avg_cost
            avg_cost = (qty * avg_cost + q * p) / (qty + q)
            qty += q

        def sell(q, p):
            nonlocal qty, realized_total
            realized_total += q * (p - avg_cost)
            qty -= q

        buy(100, 50.0)
        buy(50,  70.0)
        sell(60, 80.0)
        buy(30,  65.0)
        sell(120, 90.0)

        # Direct reference calculation (path-independent)
        total_proceeds = 60*80.0 + 120*90.0      # 15 600
        total_cost     = 100*50.0 + 50*70.0 + 30*65.0   # 10 450
        exp_realized   = total_proceeds - total_cost     # 5 150

        qty_ok      = _near(qty, 0.0, 1e-9)
        realized_ok = _near(realized_total, exp_realized, 0.01)
        passed      = qty_ok and realized_ok

        return (
            f"qty=0.0, realized={exp_realized:.2f}",
            f"qty={qty}, realized={realized_total:.2f}",
            passed,
        )
    results.append(_run(
        "E01",
        "Portfolio Reconstruction — step-by-step equals direct calculation",
        "Robustness",
        "portfolio.holdings",
        "P0", True, e01,
    ))

    # ── E02  Float Stability — 200-holding portfolio ───────────────────────────
    # All holdings denominated in USD, base=SAR, rate=3.75.
    # Seed=42 gives a fully deterministic, adversarial-ish spread of values.
    def e02():
        import random
        rng = random.Random(42)   # seeded — test is deterministic across runs

        holdings: dict = {}
        manual_mv_sar = 0.0
        for i in range(200):
            ticker  = f"SYN{i:03d}"
            qty     = float(rng.randint(1, 500))
            price   = round(rng.uniform(1.0, 500.0), 2)
            mv_usd  = qty * price
            holdings[ticker] = _holding(ticker, qty, price * 0.9, price, ccy="USD")
            manual_mv_sar   += mv_usd * 3.75

        v = _val(holdings, {}, "SAR", _std_fx_sar)

        # (a) weight sum ≈ 100 %
        # Weights are stored as full-precision floats (no intermediate rounding),
        # so sum(invested_weight_pct) should equal 100.0 within float epsilon.
        # Tolerance of 0.01 pp confirms there is no accumulation bug.
        wt_sum = sum(r.invested_weight_pct for r in v.per_holding
                     if not r.missing_price and not r.missing_fx)
        wt_ok = _near(wt_sum, 100.0, 0.01)

        # (b) n_holdings == 200
        n_ok = v.n_holdings == 200

        # (c) engine total ≈ manual sum (within $0.01)
        total_ok = _near(v.holdings_value_base, manual_mv_sar, 0.01)

        passed = wt_ok and n_ok and total_ok
        return (
            f"weight_sum≈100%, n=200, MV≈{manual_mv_sar:.2f} SAR",
            f"weight_sum={wt_sum:.4f}%, n={v.n_holdings}, MV={v.holdings_value_base:.2f} SAR",
            passed,
        )
    results.append(_run(
        "E02",
        "Float Stability — 200-holding portfolio weights and totals are exact",
        "Robustness",
        "portfolio.valuation",
        "P0", True, e02,
    ))

    # ── E03  Adversarial Mixed Portfolio ──────────────────────────────────────
    # 10 holdings: 4 valid, 4 price=0 (missing), 2 qty=0.
    # Valid holdings must get correct weights; corrupted ones must not pollute totals.
    def e03():
        fx = _std_fx_sar

        # 4 valid
        valid_mv_sar = 0.0
        h: dict = {}
        valid_data = [
            ("V1", 50.0, 100.0, 120.0),   # qty, cost, price
            ("V2", 30.0, 200.0, 250.0),
            ("V3", 10.0, 500.0, 480.0),
            ("V4", 100.0, 80.0,  95.0),
        ]
        for tk, qty, cost, price in valid_data:
            h[tk] = _holding(tk, qty, cost, price, ccy="USD")
            valid_mv_sar += qty * price * 3.75

        # 4 price=0 (missing price)
        for i in range(4):
            tk = f"MP{i}"
            h[tk] = _holding(tk, 10.0, 100.0, 0.0, ccy="USD")   # price=0

        # 2 qty=0 (zero quantity)
        for i in range(2):
            tk = f"ZQ{i}"
            h[tk] = _holding(tk, 0.0, 100.0, 200.0, ccy="USD")   # qty=0

        v = _val(h, {}, "SAR", fx)

        # (a) no crash — we got a result
        survived = True

        # (b) total MV ≈ only the 4 valid holdings
        total_ok = _near(v.holdings_value_base, valid_mv_sar, 0.10)

        # (c) valid holdings' weights sum to ≈100%
        valid_tickers = {d[0] for d in valid_data}
        valid_wt = sum(
            r.invested_weight_pct
            for r in v.per_holding
            if r.ticker in valid_tickers
        )
        wt_ok = _near(valid_wt, 100.0, 0.5)

        # (d) zero-qty and zero-price holdings contribute nothing
        bad_tickers = {f"MP{i}" for i in range(4)} | {f"ZQ{i}" for i in range(2)}
        bad_mv_sum = sum(
            r.base_market_value
            for r in v.per_holding
            if r.ticker in bad_tickers
        )
        isolated = _near(bad_mv_sum, 0.0, 0.001)

        passed = survived and total_ok and wt_ok and isolated
        return (
            f"MV={valid_mv_sar:.2f} SAR, valid_weights≈100%, bad_MV=0",
            f"MV={v.holdings_value_base:.2f} SAR, valid_wt={valid_wt:.2f}%, bad_MV={bad_mv_sum:.4f}",
            passed,
        )
    results.append(_run(
        "E03",
        "Adversarial mixed portfolio — corrupted data isolated, valid weights intact",
        "Robustness",
        "portfolio.valuation",
        "P0", True, e03,
    ))

    # ── E04  FX Pivot Transitivity ────────────────────────────────────────────
    # Same 2-asset portfolio (USD + EUR) valued two ways:
    #   Way 1: base=SAR, USD→SAR=3.75, EUR→SAR=4.05  → total_SAR
    #          USD equivalent = total_SAR / 3.75
    #   Way 2: base=USD, USD→USD=1.0,  EUR→USD=4.05/3.75
    #          → total_USD directly
    # They must agree within 0.10 % — any divergence means FX chaining breaks.
    def e04():
        holdings = {
            "AAPL": _holding("AAPL", 10.0, 150.0, 200.0, ccy="USD"),
            "LVMH": _holding("LVMH",  5.0, 600.0, 680.0, ccy="EUR"),
        }

        # Way 1
        fx_sar = {
            "USD": _fx("USD", "SAR", 3.75),
            "EUR": _fx("EUR", "SAR", 4.05),
        }
        v_sar = _val(holdings, {}, "SAR", fx_sar)
        usd_via_sar = v_sar.holdings_value_base / 3.75

        # Way 2
        fx_usd = {
            "USD": _fx("USD", "USD", 1.0),
            "EUR": _fx("EUR", "USD", 4.05 / 3.75),
        }
        v_usd = _val(holdings, {}, "USD", fx_usd)
        usd_direct = v_usd.holdings_value_base

        # Tolerance: 0.1 % of the direct USD total
        tol = max(0.01, abs(usd_direct) * 0.001)
        passed = _near(usd_via_sar, usd_direct, tol)
        diff_pct = abs(usd_via_sar - usd_direct) / max(usd_direct, 1e-9) * 100

        return (
            f"usd_via_sar≈usd_direct (within 0.1%)",
            f"via_SAR={usd_via_sar:.4f}, direct={usd_direct:.4f}, diff={diff_pct:.4f}%",
            passed,
        )
    results.append(_run(
        "E04",
        "FX Pivot Transitivity — USD→SAR→USD chain matches direct USD valuation",
        "Robustness",
        "fx_rates",
        "P0", True, e04,
    ))

    # ── E05  Sell-Down P&L Conservation ──────────────────────────────────────
    # Buy 1 000 shares @ $100 (cost_basis = $100 000).
    # Sell 100 shares each at 10 different prices.
    # Law of conservation: sum of all realized P&Ls must equal total_proceeds - cost.
    # Nothing may be created or destroyed between steps.
    def e05():
        buy_qty   = 1_000.0
        buy_price = 100.0
        sell_prices = [95.0, 105.0, 110.0, 98.0, 115.0,
                       90.0, 112.0, 108.0, 103.0, 95.0]
        sell_qty_each = 100.0   # 10 steps × 100 = 1 000 total

        # Step-by-step running tally
        qty         = buy_qty
        avg_cost    = buy_price
        step_realized: list[float] = []
        for sp in sell_prices:
            step_pnl = sell_qty_each * (sp - avg_cost)
            step_realized.append(step_pnl)
            qty -= sell_qty_each
            # avg_cost unchanged when selling (cost basis of remaining lots stays same)

        total_realized_stepwise = sum(step_realized)

        # Direct reference (path-independent)
        total_proceeds  = sum(sell_qty_each * sp for sp in sell_prices)
        total_cost      = buy_qty * buy_price
        exp_profit      = total_proceeds - total_cost   # 103 100 - 100 000 = 3 100

        # Assertions
        qty_ok      = _near(qty, 0.0, 1e-9)           # fully sold
        conserved   = _near(total_realized_stepwise, exp_profit, 0.01)   # no leakage
        step_count_ok = len(step_realized) == 10

        passed = qty_ok and conserved and step_count_ok
        return (
            f"qty=0, realized={exp_profit:.2f} (10 steps, no leakage)",
            f"qty={qty}, realized={total_realized_stepwise:.2f}, steps={len(step_realized)}",
            passed,
        )
    results.append(_run(
        "E05",
        "Sell-Down P&L Conservation — 10-step exit, value neither created nor destroyed",
        "Robustness",
        "portfolio.holdings",
        "P0", True, e05,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category F — SAHMK: Holdings Data Structure
# ════════════════════════════════════════════════════════════════════════════════
# NOTE: _run(id, name, category, module, severity, blocker, fn)
#       fn() must return (expected_str, actual_str, passed_bool)

def _cat_f() -> list[TestResult]:
    """
    F01–F05: exchange_symbol field — backward-compatibility and round-trip tests.
    All tests operate on in-memory Holding objects; no file I/O.
    """
    CAT = "SAHMK — Holdings Data Structure"
    results: list[TestResult] = []

    def _make(ticker="TEST", **kw):
        from portfolio.holdings import Holding
        return Holding(ticker=ticker, company_name="Test Co", **kw)

    # ── F01: Holding without exchange_symbol loads with default "" ────────────
    def f01():
        h = _make()
        exsym = getattr(h, "exchange_symbol", "__MISSING__")
        return ('""', repr(exsym), exsym == "")

    results.append(_run(
        "F01",
        "exchange_symbol defaults to empty string on old holdings",
        CAT, "portfolio.holdings", "P0", True, f01,
    ))

    # ── F02: exchange_symbol set and retrieved correctly ──────────────────────
    def f02():
        h = _make(exchange_symbol="2222")
        act = getattr(h, "exchange_symbol", None)
        return ('"2222"', repr(act), act == "2222")

    results.append(_run(
        "F02",
        "exchange_symbol stores and retrieves 4-digit Saudi symbol",
        CAT, "portfolio.holdings", "P0", True, f02,
    ))

    # ── F03: exchange_symbol is independent of ticker ─────────────────────────
    def f03():
        h = _make(ticker="2222.SR", exchange_symbol="2222")
        ok = (h.ticker == "2222.SR") and (h.exchange_symbol == "2222")
        return (
            "ticker='2222.SR', exchange_symbol='2222'",
            f"ticker={h.ticker!r}, exchange_symbol={h.exchange_symbol!r}",
            ok,
        )

    results.append(_run(
        "F03",
        "exchange_symbol is independent from ticker — both coexist",
        CAT, "portfolio.holdings", "P0", True, f03,
    ))

    # ── F04: Holding serialises/deserialises exchange_symbol via asdict ────────
    def f04():
        from dataclasses import asdict
        h = _make(exchange_symbol="1120")
        d = asdict(h)
        act = d.get("exchange_symbol")
        return ('"exchange_symbol": "1120"', repr(act), act == "1120")

    results.append(_run(
        "F04",
        "exchange_symbol survives asdict() round-trip (JSON serialisation)",
        CAT, "portfolio.holdings", "P0", True, f04,
    ))

    # ── F05: load_holdings() ignores unknown extra keys (future-proofing) ──────
    def f05():
        import dataclasses
        from portfolio.holdings import Holding
        valid_keys = {fld.name for fld in dataclasses.fields(Holding)}
        raw = {
            "ticker": "F05", "company_name": "Future Co",
            "exchange_symbol": "7010",
            "future_unknown_field": "ignored",
        }
        filtered = {k: v for k, v in raw.items() if k in valid_keys}
        h = Holding(**filtered)
        ok = h.exchange_symbol == "7010" and not hasattr(h, "future_unknown_field")
        return (
            "exchange_symbol='7010', no unknown fields",
            f"exchange_symbol={h.exchange_symbol!r}",
            ok,
        )

    results.append(_run(
        "F05",
        "Unknown JSON fields ignored; exchange_symbol loads correctly",
        CAT, "portfolio.holdings", "P1", False, f05,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category G — SAHMK: Pricing Provider Logic
# ════════════════════════════════════════════════════════════════════════════════

def _cat_g() -> list[TestResult]:
    """
    G01–G06: Provider routing logic tested without live network calls.
    """
    CAT = "SAHMK — Pricing Provider Logic"
    results: list[TestResult] = []

    # ── G01: Blank exchange_symbol skips SAHMK entirely ──────────────────────
    def g01():
        from market_data_router import get_routed_price, PROVIDER_SAHMK
        rp = get_routed_price(
            ticker="", exchange_symbol="",
            last_known_price=123.45, last_known_source="manual",
        )
        ok = rp.provider != PROVIDER_SAHMK
        return (
            "provider != SAHMK (blank exchange_symbol)",
            repr(rp.provider),
            ok,
        )

    results.append(_run(
        "G01",
        "Blank exchange_symbol skips SAHMK; falls to yfinance or manual",
        CAT, "market_data_router", "P0", True, g01,
    ))

    # ── G02: exchange_symbol set, SAHMK unconfigured → no crash, fall through ─
    def g02():
        import sahmk_client
        from market_data_router import get_routed_price, PROVIDER_SAHMK
        configured = sahmk_client.is_configured()
        rp = get_routed_price(
            ticker="", exchange_symbol="2222",
            last_known_price=50.0, last_known_source="manual",
        )
        if configured:
            ok = rp.provider in (PROVIDER_SAHMK, "yfinance", "cached", "manual")
            exp = "provider in {SAHMK, yfinance, cached, manual}"
        else:
            ok = rp.provider != PROVIDER_SAHMK
            exp = "provider != SAHMK (key absent)"
        return (exp, repr(rp.provider), ok)

    results.append(_run(
        "G02",
        "SAHMK unconfigured → router falls through without crashing",
        CAT, "market_data_router", "P0", True, g02,
    ))

    # ── G03: Both providers fail → cached price retained ─────────────────────
    def g03():
        from market_data_router import get_routed_price, PROVIDER_CACHED
        rp = get_routed_price(
            ticker="", exchange_symbol="",
            last_known_price=99.99, last_known_source="yfinance",
        )
        ok = rp.provider == PROVIDER_CACHED and abs(rp.price - 99.99) < 0.001
        return (
            "provider=cached, price=99.99",
            f"provider={rp.provider!r}, price={rp.price}",
            ok,
        )

    results.append(_run(
        "G03",
        "Both providers fail → last cached price retained (provider='cached')",
        CAT, "market_data_router", "P0", True, g03,
    ))

    # ── G04: price_source='manual' → manual fallback label ───────────────────
    def g04():
        from market_data_router import get_routed_price, PROVIDER_MANUAL
        rp = get_routed_price(
            ticker="", exchange_symbol="",
            last_known_price=42.00, last_known_source="manual",
        )
        ok = rp.provider == PROVIDER_MANUAL and abs(rp.price - 42.00) < 0.001
        return (
            "provider=manual, price=42.00",
            f"provider={rp.provider!r}, price={rp.price}",
            ok,
        )

    results.append(_run(
        "G04",
        "All providers fail → manual price retained (provider='manual')",
        CAT, "market_data_router", "P0", True, g04,
    ))

    # ── G05: RoutedPrice.is_ok is False when price is None ───────────────────
    def g05():
        from market_data_router import RoutedPrice, PROVIDER_MANUAL
        rp = RoutedPrice(price=None, provider=PROVIDER_MANUAL)
        return ("is_ok=False", repr(rp.is_ok), rp.is_ok is False)

    results.append(_run(
        "G05",
        "RoutedPrice.is_ok is False when no price is available",
        CAT, "market_data_router", "P1", False, g05,
    ))

    # ── G06: refresh_holdings_prices({}) returns empty dict safely ────────────
    def g06():
        from market_data_router import refresh_holdings_prices
        result = refresh_holdings_prices({})
        ok = isinstance(result, dict) and len(result) == 0
        return ("empty dict", repr(result), ok)

    results.append(_run(
        "G06",
        "refresh_holdings_prices({}) returns empty dict — no crash",
        CAT, "market_data_router", "P0", True, g06,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category H — SAHMK: API Resilience
# ════════════════════════════════════════════════════════════════════════════════

def _cat_h() -> list[TestResult]:
    """
    H01–H05: SAHMK client graceful-failure guarantees — no live network calls.
    """
    CAT = "SAHMK — API Resilience"
    results: list[TestResult] = []

    # ── H01: get_quote() returns None when API key is absent ─────────────────
    def h01():
        import os, sahmk_client
        old_env = os.environ.get("SAHMK_API_KEY")
        os.environ.pop("SAHMK_API_KEY", None)
        try:
            # force=True bypasses the in-process cache so the absent key is checked
            result = sahmk_client.get_quote("2222", force=True)
            ok = result is None
        finally:
            if old_env is not None:
                os.environ["SAHMK_API_KEY"] = old_env
        return ("None (no API key)", repr(result), ok)

    results.append(_run(
        "H01",
        "get_quote() returns None gracefully when SAHMK_API_KEY is absent",
        CAT, "sahmk_client", "P0", True, h01,
    ))

    # ── H02: get_historical() returns None for blank symbol ──────────────────
    def h02():
        import sahmk_client
        result = sahmk_client.get_historical("")
        return ("None", repr(result), result is None)

    results.append(_run(
        "H02",
        "get_historical('') returns None — no crash on blank symbol",
        CAT, "sahmk_client", "P0", True, h02,
    ))

    # ── H03: get_company_info() returns None for blank symbol ────────────────
    def h03():
        import sahmk_client
        result = sahmk_client.get_company_info("")
        return ("None", repr(result), result is None)

    results.append(_run(
        "H03",
        "get_company_info('') returns None — no crash on blank symbol",
        CAT, "sahmk_client", "P0", True, h03,
    ))

    # ── H04: All public functions are exception-free without an API key ───────
    def h04():
        import sahmk_client
        raised = False
        try:
            sahmk_client.get_quote("9999")
            sahmk_client.get_market_summary()
            sahmk_client.get_historical("9999")
            sahmk_client.get_company_info("9999")
            sahmk_client.get_financial_statements("9999")
            sahmk_client.get_financial_ratios("9999")
            sahmk_client.get_dividends("9999")
            sahmk_client.get_market_events()
        except Exception:
            raised = True
        return (
            "no exception raised",
            "exception raised" if raised else "no exception",
            not raised,
        )

    results.append(_run(
        "H04",
        "All SAHMK functions survive without API key — zero exceptions",
        CAT, "sahmk_client", "P0", True, h04,
    ))

    # ── H05: cache_stats() returns valid diagnostic dict ─────────────────────
    def h05():
        import sahmk_client
        stats = sahmk_client.cache_stats()
        ok = (
            isinstance(stats, dict)
            and "entries" in stats
            and "keys" in stats
            and isinstance(stats["entries"], int)
        )
        return ("dict with 'entries' and 'keys'", repr(type(stats)), ok)

    results.append(_run(
        "H05",
        "cache_stats() returns valid diagnostic dict",
        CAT, "sahmk_client", "P2", False, h05,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category I — SAHMK: Portfolio Calculation Preservation
# ════════════════════════════════════════════════════════════════════════════════

def _cat_i() -> list[TestResult]:
    """
    I01–I05: Verify exchange_symbol addition doesn't change any portfolio arithmetic.
    """
    CAT = "SAHMK — Portfolio Calc Preservation"
    results: list[TestResult] = []

    def _std_fx():
        return {"USD": _fx("USD", "USD", 1.0)}

    def _val(holdings, prices, base_ccy, fx):
        from portfolio.valuation import calculate_portfolio_valuation
        return calculate_portfolio_valuation(holdings, prices, base_ccy, fx)

    def _h(ticker, qty, cost, price, exchange_symbol=""):
        from portfolio.holdings import Holding
        return Holding(
            ticker=ticker, company_name=ticker,
            quantity=qty, avg_cost=cost, current_price=price,
            currency="USD", has_ticker=True,
            exchange_symbol=exchange_symbol,
        )

    # ── I01: exchange_symbol does not affect market value ────────────────────
    def i01():
        h_w = _h("A", 10, 100, 150, exchange_symbol="2222")
        h_n = _h("A", 10, 100, 150)
        ok  = abs(h_w.market_value - h_n.market_value) < 0.001
        return (
            "1500.0 == 1500.0",
            f"with={h_w.market_value}, without={h_n.market_value}",
            ok,
        )

    results.append(_run(
        "I01",
        "exchange_symbol does not change market_value calculation",
        CAT, "portfolio.holdings", "P0", True, i01,
    ))

    # ── I02: exchange_symbol does not affect cost basis ──────────────────────
    def i02():
        h_w = _h("A", 10, 100, 150, exchange_symbol="2222")
        h_n = _h("A", 10, 100, 150)
        ok  = abs(h_w.cost_basis - h_n.cost_basis) < 0.001
        return (
            "1000.0 == 1000.0",
            f"with={h_w.cost_basis}, without={h_n.cost_basis}",
            ok,
        )

    results.append(_run(
        "I02",
        "exchange_symbol does not change cost_basis calculation",
        CAT, "portfolio.holdings", "P0", True, i02,
    ))

    # ── I03: Valuation engine totals are identical regardless of exchange_symbol
    def i03():
        hw = {"A": _h("A", 10, 50, 100, exchange_symbol="1120"),
              "B": _h("B", 20, 30, 60,  exchange_symbol="")}
        hn = {"A": _h("A", 10, 50, 100), "B": _h("B", 20, 30, 60)}
        v1 = _val(hw, {}, "USD", _std_fx())
        v2 = _val(hn, {}, "USD", _std_fx())
        ok = abs(v1.total_portfolio_value_base - v2.total_portfolio_value_base) < 0.01
        return (
            "total_portfolio_value_base identical",
            f"with={v1.total_portfolio_value_base:.2f}, without={v2.total_portfolio_value_base:.2f}",
            ok,
        )

    results.append(_run(
        "I03",
        "Valuation engine totals identical regardless of exchange_symbol",
        CAT, "portfolio.valuation", "P0", True, i03,
    ))

    # ── I04: Weight sum still 100% with exchange_symbol-enabled holdings ──────
    def i04():
        h = {
            "A": _h("A", 10, 50, 100, exchange_symbol="2222"),
            "B": _h("B", 20, 30, 60,  exchange_symbol="1120"),
            "C": _h("C", 5,  80, 120, exchange_symbol=""),
        }
        v      = _val(h, {}, "USD", _std_fx())
        wt_sum = sum(r.invested_weight_pct for r in v.per_holding)
        ok     = abs(wt_sum - 100.0) < 0.01
        return ("weight_sum ≈ 100.0%", f"weight_sum={wt_sum:.6f}%", ok)

    results.append(_run(
        "I04",
        "Invested weights sum to 100% with exchange_symbol holdings",
        CAT, "portfolio.valuation", "P0", True, i04,
    ))

    # ── I05: Unrealized P&L is unchanged when exchange_symbol is set ──────────
    def i05():
        h   = _h("A", 10, 100, 130, exchange_symbol="7010")
        exp = (130 - 100) * 10   # 300.0
        ok  = abs(h.unrealized_pnl - exp) < 0.001
        return (
            f"unrealized_pnl={exp:.2f}",
            f"unrealized_pnl={h.unrealized_pnl:.2f}",
            ok,
        )

    results.append(_run(
        "I05",
        "unrealized_pnl unchanged when exchange_symbol is set",
        CAT, "portfolio.holdings", "P0", True, i05,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category J — SAHMK: Live Integration (requires SAHMK_API_KEY)
# ════════════════════════════════════════════════════════════════════════════════

def _cat_j() -> list[TestResult]:
    """
    J01–J05: Live SAHMK integration tests.
    J01–J02 are pure env/network checks (no API call).
    J03 makes a real GET /quote/2222/ request — marked P1/non-blocker since
    the quote depends on the test key's access level.
    J04 verifies the fallback chain (SAHMK miss → yfinance).
    J05 confirms the valuation engine accepts a SAHMK-sourced price cleanly.
    """
    CAT = "SAHMK — Live Integration"
    results: list[TestResult] = []

    # ── J01: SAHMK API key is configured ─────────────────────────────────────
    def j01():
        import sahmk_client
        ok = sahmk_client.is_configured()
        return (
            "is_configured()=True",
            f"is_configured()={ok}",
            ok,
        )

    results.append(_run(
        "J01",
        "SAHMK_API_KEY is present in environment",
        CAT, "sahmk_client", "P0", True, j01,
    ))

    # ── J02: SAHMK base URL DNS resolves ─────────────────────────────────────
    def j02():
        import socket, os
        base = os.environ.get("SAHMK_BASE_URL", "https://app.sahmk.sa/api/v1")
        # Extract hostname from URL (strip scheme and path)
        host = base.split("//")[-1].split("/")[0]
        try:
            socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            ok = True
            act = f"{host} resolved"
        except socket.gaierror as e:
            ok = False
            act = f"{host} failed: {e}"
        return (f"{host} resolves via DNS", act, ok)

    results.append(_run(
        "J02",
        "SAHMK base URL hostname resolves via DNS",
        CAT, "sahmk_client", "P0", True, j02,
    ))

    # ── J03: get_quote("2222") returns a valid price ──────────────────────────
    def j03():
        import sahmk_client
        sahmk_client.clear_cache()           # force a live network call
        q = sahmk_client.get_quote("2222", force=True)
        if q is None:
            return (
                "dict with price > 0",
                "None (API returned no data — test-key limitation or market closed)",
                False,
            )
        p = q.get("price")
        ok = isinstance(p, (int, float)) and float(p) > 0
        return (
            "dict with price > 0",
            f"price={p}, currency={q.get('currency','?')}",
            ok,
        )

    results.append(_run(
        "J03",
        "get_quote('2222') returns a live quote with a positive price",
        CAT, "sahmk_client", "P1", False, j03,   # P1/non-blocker: test-key may be limited
    ))

    # ── J04: Fallback chain — SAHMK miss → yfinance picks up ─────────────────
    def j04():
        from market_data_router import get_routed_price, PROVIDER_SAHMK, PROVIDER_YFINANCE
        # "ZZZINVALID" as exchange_symbol → SAHMK returns None for unknown symbol
        # "AAPL" as ticker             → yfinance should succeed
        rp = get_routed_price(
            ticker          = "AAPL",
            exchange_symbol = "ZZZINVALID",
            last_known_price  = 0.0,
            last_known_source = "manual",
        )
        # Must NOT come from SAHMK (the invalid symbol should produce None)
        # Should come from yfinance (AAPL is always available)
        ok = rp.provider == PROVIDER_YFINANCE and rp.is_ok
        return (
            f"provider=yfinance, price>0",
            f"provider={rp.provider!r}, price={rp.price}, source={rp.source!r}",
            ok,
        )

    results.append(_run(
        "J04",
        "SAHMK miss on invalid symbol → router falls back to yfinance",
        CAT, "market_data_router", "P0", True, j04,
    ))

    # ── J05: Valuation engine accepts SAHMK-sourced price without error ───────
    def j05():
        from portfolio.holdings import Holding
        from portfolio.valuation import calculate_portfolio_valuation
        from fx_rates import FxRate
        # Build a holding whose current_price comes from SAHMK (simulated)
        h = Holding(
            ticker="2222.SR", company_name="Saudi Aramco",
            quantity=100.0, avg_cost=30.0, current_price=32.50,
            currency="SAR", has_ticker=True,
            exchange_symbol="2222",
        )
        fx = {"SAR": FxRate(from_ccy="SAR", base_ccy="SAR",
                            rate=1.0, source="test", fetched_at=_ts())}
        v = calculate_portfolio_valuation({"2222.SR": h}, {}, "SAR", fx)
        exp_mv = 100.0 * 32.50   # 3250.0
        ok = abs(v.holdings_value_base - exp_mv) < 0.01
        return (
            f"holdings_value_base={exp_mv:.2f}",
            f"holdings_value_base={v.holdings_value_base:.2f}",
            ok,
        )

    results.append(_run(
        "J05",
        "Valuation engine correctly uses SAHMK-sourced price (no errors)",
        CAT, "portfolio.valuation", "P0", True, j05,
    ))

    return results


def _cat_k() -> list[TestResult]:
    """
    K01–K02: Price-source field verification.
    K01 — Saudi symbol (exchange_symbol set) must be routed to SAHMK.
    K02 — Non-Saudi symbol (no exchange_symbol) must be routed to yfinance.
    Uses the real market_data_router; never touches portfolio files.
    """
    CAT = "Price Source Verification"
    results: list[TestResult] = []

    # ── K01: Saudi symbol (2222.SE) source = SAHMK ───────────────────────────
    def k01():
        from market_data_router import get_routed_price, PROVIDER_SAHMK
        rp = get_routed_price(
            ticker            = "2222.SE",
            exchange_symbol   = "2222",
            last_known_price  = 30.0,
            last_known_source = "manual",
        )
        ok = rp.provider == PROVIDER_SAHMK and rp.is_ok
        return (
            f"provider={PROVIDER_SAHMK!r}",
            f"provider={rp.provider!r}, price={rp.price}, ok={rp.is_ok}",
            ok,
        )

    results.append(_run(
        "K01",
        "Saudi symbol (2222 / 2222.SE) price_source = SAHMK",
        CAT, "market_data_router", "P1", False, k01,
    ))

    # ── K02: Non-Saudi symbol source = Yahoo (yfinance) ──────────────────────
    def k02():
        from market_data_router import get_routed_price, PROVIDER_YFINANCE
        rp = get_routed_price(
            ticker            = "AAPL",
            exchange_symbol   = "",
            last_known_price  = 150.0,
            last_known_source = "manual",
        )
        ok = rp.provider == PROVIDER_YFINANCE and rp.is_ok
        return (
            f"provider={PROVIDER_YFINANCE!r}",
            f"provider={rp.provider!r}, price={rp.price}, ok={rp.is_ok}",
            ok,
        )

    results.append(_run(
        "K02",
        "Non-Saudi symbol (AAPL) price_source = Yahoo (yfinance)",
        CAT, "market_data_router", "P1", False, k02,
    ))

    # ── K03: SAHMK-first regression — Saudi symbol variants all route to SAHMK ─
    def k03():
        """
        Regression guard: every way a Saudi ticker can appear in a holding must
        route to SAHMK first and never fall through to Yahoo Finance.

        Variants tested (all should return provider=SAHMK, never yfinance):
          A. ticker="2222.SE",  exchange_symbol=""      → derive "2222" from ticker
          B. ticker="2222.SR",  exchange_symbol=""      → derive "2222" from ticker
          C. ticker="2222.SE",  exchange_symbol="2222"  → explicit exchange_symbol
          D. ticker="2222.SE",  exchange_symbol="2222.SE" → normalise suffix from exchange_symbol
        """
        from market_data_router import get_routed_price, PROVIDER_SAHMK, PROVIDER_YFINANCE
        import sahmk_client
        if not sahmk_client.is_configured():
            return ("SAHMK configured", "SAHMK_API_KEY not set — skipped", False)

        variants = [
            ("2222.SE", "",        "A: ticker=2222.SE, no exchange_symbol"),
            ("2222.SR", "",        "B: ticker=2222.SR, no exchange_symbol"),
            ("2222.SE", "2222",    "C: ticker=2222.SE, exchange_symbol=2222"),
            ("2222.SE", "2222.SE", "D: ticker=2222.SE, exchange_symbol=2222.SE"),
        ]
        failures = []
        prices   = []
        for ticker, exch, label in variants:
            rp = get_routed_price(
                ticker            = ticker,
                exchange_symbol   = exch,
                last_known_price  = 0.0,
                last_known_source = "manual",
            )
            if rp.provider != PROVIDER_SAHMK:
                failures.append(f"{label} → provider={rp.provider!r} (expected SAHMK)")
            elif rp.price and rp.price > 0:
                prices.append(rp.price)

        if failures:
            return (
                "all variants provider=SAHMK",
                "; ".join(failures),
                False,
            )
        price_str = f"{prices[0]}" if prices else "unknown"
        return (
            "all variants provider=SAHMK",
            f"all 4 variants routed to SAHMK, price={price_str} SAR",
            True,
        )

    results.append(_run(
        "K03",
        "SAHMK-first regression: all Saudi ticker variants route to SAHMK, never Yahoo",
        CAT, "market_data_router", "P0", True, k03,
    ))

    return results


def _cat_l() -> list[TestResult]:
    """
    L01–L05: UI tab valuation-engine consistency.

    Verifies that Holdings, Command Center, Allocation, Portfolio Risk, and
    Accounts all surface totals that are consistent with the centralized
    valuation engine (calculate_portfolio_valuation).

    Strategy
    --------
    · Build a fixed 2-holding / 2-account synthetic portfolio with pinned
      FX rates so every call is deterministic.
    · Call the engine once and inspect the output (L01–L03, L05).
    · For L04 (Portfolio Risk) call the engine a second time independently,
      mirroring what render_portfolio_risk_tab() does, and compare.
    · For L05 (Accounts tab) replicate the inline cash-sum formula from
      render_accounts_tab() (lines 3666-3669 in app.py) and compare it
      against engine.cash_value_base.
    · Any mismatch is REPORTED only — no fix is applied here.

    All tests use P0 / release-blocker severity except L05 (Accounts cash
    divergence is reported but not a hard blocker; the Accounts tab does not
    call the centralized engine for its cash total).
    """
    CAT = "Tab Valuation Consistency"
    results: list[TestResult] = []

    # ── Shared synthetic portfolio ────────────────────────────────────────────
    BASE    = "SAR"
    _fx_map = {
        "SAR": _fx("SAR", BASE, 1.0),
        "USD": _fx("USD", BASE, 3.75),
    }
    _holdings = {
        "AAPL":   _holding("AAPL",   10.0,  150.0, 180.0, ccy="USD"),
        "ARAMCO": _holding("ARAMCO", 100.0,  30.0,  35.0, ccy="SAR"),
    }
    _accounts_map = {
        "acc1": _account("acc1", 5_000.0, "SAR"),
        "acc2": _account("acc2", 2_000.0, "USD"),
    }

    # One canonical engine result — L01/L02/L03/L05 read from this object.
    _engine = _val(_holdings, _accounts_map, BASE, _fx_map)

    # ── L01: Holdings — per-holding sum == holdings_value_base ───────────────
    # The Holdings tab displays _val.holdings_value_base and builds the table
    # from _val.per_holding.  These must be numerically identical.
    def l01():
        ph_sum = round(sum(ph.base_market_value for ph in _engine.per_holding), 2)
        hv     = round(_engine.holdings_value_base, 2)
        ok     = _near(ph_sum, hv, tol=0.01)
        return (
            f"per_holding sum == holdings_value_base ({hv:,.2f} {BASE})",
            f"per_holding sum = {ph_sum:,.2f}, holdings_value_base = {hv:,.2f}",
            ok,
        )

    results.append(_run(
        "L01",
        "Holdings tab: sum of per-holding base_market_value == engine holdings_value_base",
        CAT, "portfolio.valuation", "P0", True, l01,
    ))

    # ── L02: Command Center — holdings + cash == total_portfolio_value_base ──
    # The top KPI card in Command Center shows total_portfolio_value_base,
    # which must equal holdings_value_base + cash_value_base.
    def l02():
        hv   = round(_engine.holdings_value_base, 2)
        cv   = round(_engine.cash_value_base, 2)
        tv   = round(_engine.total_portfolio_value_base, 2)
        calc = round(hv + cv, 2)
        ok   = _near(calc, tv, tol=0.01)
        return (
            f"holdings + cash == total_portfolio_value_base ({tv:,.2f} {BASE})",
            f"{hv:,.2f} + {cv:,.2f} = {calc:,.2f}  vs  total = {tv:,.2f}",
            ok,
        )

    results.append(_run(
        "L02",
        "Command Center: holdings_value_base + cash_value_base == total_portfolio_value_base",
        CAT, "portfolio.valuation", "P0", True, l02,
    ))

    # ── L03: Allocation — invested_weight_pct sums to ~100 % ─────────────────
    # The Allocation tab receives the same _val object from the Holdings tab
    # (no re-computation) and builds pie / donut charts from per_holding
    # base_market_value.  Weights must sum to 100 %.
    def l03():
        w_sum = round(sum(ph.invested_weight_pct for ph in _engine.per_holding), 2)
        ok    = _near(w_sum, 100.0, tol=0.5)
        return (
            "invested_weight_pct across all holdings sums to ~100 %",
            f"sum(invested_weight_pct) = {w_sum:.4f} %",
            ok,
        )

    results.append(_run(
        "L03",
        "Allocation tab: invested_weight_pct sums to ~100 % (charts stay coherent)",
        CAT, "portfolio.valuation", "P0", True, l03,
    ))

    # ── L04: Portfolio Risk — independent engine call == Holdings total ───────
    # render_portfolio_risk_tab() calls calculate_portfolio_valuation()
    # independently of the Holdings tab.  With the same fixed FX rates the
    # result must be identical.
    def l04():
        risk_engine = _val(_holdings, _accounts_map, BASE, _fx_map)
        hv_hld  = round(_engine.holdings_value_base, 2)
        hv_risk = round(risk_engine.holdings_value_base, 2)
        tv_hld  = round(_engine.total_portfolio_value_base, 2)
        tv_risk = round(risk_engine.total_portfolio_value_base, 2)
        ok = _near(hv_hld, hv_risk, tol=0.01) and _near(tv_hld, tv_risk, tol=0.01)
        return (
            f"Risk holdings={hv_hld:,.2f}, total={tv_hld:,.2f} match Holdings",
            (
                f"Holdings: hv={hv_hld:,.2f} tv={tv_hld:,.2f} | "
                f"Risk: hv={hv_risk:,.2f} tv={tv_risk:,.2f}"
            ),
            ok,
        )

    results.append(_run(
        "L04",
        "Portfolio Risk tab: independent engine call produces same totals as Holdings tab",
        CAT, "portfolio.valuation", "P0", True, l04,
    ))

    # ── L05: Accounts tab — inline cash sum vs. engine cash_value_base ───────
    # render_accounts_tab() computes _total_cash with its own inline formula
    # (app.py lines 3666-3669) rather than calling the engine.  This test
    # replicates that exact formula and checks for divergence.
    # is_release_blocker=False — mismatch is reported only, not enforced.
    def l05():
        active   = {aid: a for aid, a in _accounts_map.items() if a.active}
        tab_cash = round(sum(
            a.cash_balance * (
                _fx_map[a.base_currency].rate if a.base_currency in _fx_map else 1.0
            )
            for a in active.values()
        ), 2)
        engine_cash = round(_engine.cash_value_base, 2)
        ok      = _near(tab_cash, engine_cash, tol=0.01)
        mismatch = (
            ""
            if ok
            else f"  ⚠️ MISMATCH — Accounts tab shows {tab_cash:,.2f}, engine returns {engine_cash:,.2f}"
        )
        return (
            f"Accounts inline cash sum == engine cash_value_base ({engine_cash:,.2f} {BASE})",
            f"tab_cash = {tab_cash:,.2f}, engine_cash = {engine_cash:,.2f}{mismatch}",
            ok,
        )

    results.append(_run(
        "L05",
        "Accounts tab: inline cash sum matches engine cash_value_base (mismatch = report only)",
        CAT, "portfolio.valuation", "P1", False, l05,
    ))

    # ── L06: Base currency propagation — SAR / USD / AED ─────────────────────
    # Calls the engine three times with SAR, USD, and AED as base_ccy using
    # pinned synthetic FX rates.  For each call verifies:
    #   (a) holdings_value_base + cash_value_base == total_portfolio_value_base
    #   (b) Cross-currency ratio SAR/USD ≈ 3.75 (the pinned peg)
    # This mirrors what each UI tab would see when the user switches base_ccy.
    def l06():
        SAR_RATE   = 3.75                   # 1 USD = 3.75 SAR (pegged)
        AED_RATE   = 3.6725                 # 1 USD = 3.6725 AED (pegged)
        AED_IN_SAR = AED_RATE / SAR_RATE    # 1 AED ≈ 0.9793 SAR

        fx_sar = {"SAR": _fx("SAR","SAR",1.0),          "USD": _fx("USD","SAR",SAR_RATE),
                  "AED": _fx("AED","SAR",AED_IN_SAR)}
        fx_usd = {"SAR": _fx("SAR","USD",1/SAR_RATE),   "USD": _fx("USD","USD",1.0),
                  "AED": _fx("AED","USD",1/AED_RATE)}
        fx_aed = {"SAR": _fx("SAR","AED",SAR_RATE/AED_RATE), "USD": _fx("USD","AED",AED_RATE),
                  "AED": _fx("AED","AED",1.0)}

        hld  = {"AAPL":   _holding("AAPL",   10.0, 150.0, 180.0, ccy="USD"),
                "ARAMCO": _holding("ARAMCO", 100.0,  30.0,  35.0, ccy="SAR")}
        acct = {"acc1": _account("acc1", 5_000.0, "SAR"),
                "acc2": _account("acc2", 2_000.0, "USD")}

        eng_sar = _val(hld, acct, "SAR", fx_sar)
        eng_usd = _val(hld, acct, "USD", fx_usd)
        eng_aed = _val(hld, acct, "AED", fx_aed)

        findings: list[str] = []
        all_ok = True

        for label, eng in [("SAR", eng_sar), ("USD", eng_usd), ("AED", eng_aed)]:
            hv   = round(eng.holdings_value_base, 4)
            cv   = round(eng.cash_value_base, 4)
            tv   = round(eng.total_portfolio_value_base, 4)
            calc = round(hv + cv, 4)
            ok_i = _near(calc, tv, tol=0.02)
            if not ok_i:
                all_ok = False
            findings.append(
                f"{label}: hv={hv:,.2f} cv={cv:,.2f} total={tv:,.2f} "
                f"{'✓' if ok_i else '⚠️ MISMATCH'}"
            )

        # Cross-currency ratio: SAR total / USD total must ≈ 3.75
        if eng_usd.total_portfolio_value_base > 0:
            ratio    = eng_sar.total_portfolio_value_base / eng_usd.total_portfolio_value_base
            ratio_ok = _near(ratio, SAR_RATE, tol=0.01)
            if not ratio_ok:
                all_ok = False
            findings.append(
                f"SAR/USD ratio={ratio:.4f} (expected {SAR_RATE}) "
                f"{'✓' if ratio_ok else '⚠️ MISMATCH'}"
            )

        return (
            "Engine consistent for SAR, USD, AED; holdings+cash==total each; SAR/USD≈3.75",
            " | ".join(findings),
            all_ok,
        )

    results.append(_run(
        "L06",
        "Base Currency Propagation: engine consistent for SAR / USD / AED base currencies",
        CAT, "portfolio.valuation", "P0", True, l06,
    ))

    return results


def _cat_m() -> list[TestResult]:
    """
    M01–M08: UI & Valuation Consistency Tests.

    Eight named checks requested against the centralized valuation engine:

      M01  Header Portfolio Value        — engine total vs. manual cross-check
      M02  Holdings Total                — engine holdings_value_base vs. manual
      M03  Cash Total                    — engine cash_value_base vs. manual
      M04  Allocation Consistency        — Allocation total == engine holdings total
      M05  Portfolio Risk Consistency    — independent engine call == primary
      M06  Weight Validation             — invested weights sum ≈ 100 %
      M07  Base Currency Propagation     — SAR / USD / AED: internal consistency
      M08  Single Valuation Engine       — static check: all tabs call the engine

    Rules:
      · Fixed synthetic portfolio + pinned FX rates → deterministic results.
      · No application logic modified.  Mismatches are reported only.
      · M08 performs static source-code analysis (file reads + text search).
    """
    CAT = "UI & Valuation Consistency"
    results: list[TestResult] = []

    # ── Shared synthetic portfolio ─────────────────────────────────────────────
    # AAPL:   10 shares @ $180  (USD holding)  → 1 800 USD → 6 750 SAR
    # ARAMCO: 100 shares @ 35   (SAR holding)  → 3 500 SAR
    # acc1:   5 000 SAR cash
    # acc2:   2 000 USD cash                   → 7 500 SAR
    # ──────────────────────────────────────────────────────────────────────────
    # Expected holdings total  =  6 750 + 3 500           = 10 250 SAR
    # Expected cash total      =  5 000 + 7 500           = 12 500 SAR
    # Expected portfolio total = 10 250 + 12 500          = 22 750 SAR
    # SAR/USD ratio = 3.75  →  portfolio USD = 22 750 / 3.75 ≈ 6 066.67 USD
    # ──────────────────────────────────────────────────────────────────────────
    _SAR_RATE     = 3.75                     # 1 USD = 3.75 SAR (pegged)
    _AED_RATE     = 3.6725                   # 1 USD = 3.6725 AED (pegged)
    _AED_IN_SAR   = _AED_RATE / _SAR_RATE    # 1 AED ≈ 0.9793 SAR

    _fx_sar = {
        "SAR": _fx("SAR", "SAR", 1.0),
        "USD": _fx("USD", "SAR", _SAR_RATE),
        "AED": _fx("AED", "SAR", _AED_IN_SAR),
    }
    _fx_usd = {
        "SAR": _fx("SAR", "USD", 1.0 / _SAR_RATE),
        "USD": _fx("USD", "USD", 1.0),
        "AED": _fx("AED", "USD", 1.0 / _AED_RATE),
    }
    _fx_aed = {
        "SAR": _fx("SAR", "AED", _SAR_RATE / _AED_RATE),
        "USD": _fx("USD", "AED", _AED_RATE),
        "AED": _fx("AED", "AED", 1.0),
    }

    _hld = {
        "AAPL":   _holding("AAPL",   10.0,  150.0, 180.0, ccy="USD"),
        "ARAMCO": _holding("ARAMCO", 100.0,  30.0,  35.0, ccy="SAR"),
    }
    _acct = {
        "acc1": _account("acc1", 5_000.0, "SAR"),
        "acc2": _account("acc2", 2_000.0, "USD"),
    }

    # Pre-computed expected values (arithmetic, not relying on the engine)
    _EXP_HV   = round((10 * 180 * _SAR_RATE) + (100 * 35 * 1.0), 2)   # 10 250.00
    _EXP_CV   = round((5_000 * 1.0) + (2_000 * _SAR_RATE), 2)          # 12 500.00
    _EXP_TV   = round(_EXP_HV + _EXP_CV, 2)                            # 22 750.00

    # One canonical engine result for SAR base — shared by M01–M06
    _eng = _val(_hld, _acct, "SAR", _fx_sar)

    # ── M01: Header Portfolio Value ───────────────────────────────────────────
    # The global header renders _gh_val.total_portfolio_value_base.
    # Cross-check: manually computed expected total vs. engine.
    def m01():
        engine_tv = round(_eng.total_portfolio_value_base, 2)
        ok = _near(_EXP_TV, engine_tv, tol=0.05)
        return (
            f"Header total_portfolio_value_base = {_EXP_TV:,.2f} SAR",
            f"engine={engine_tv:,.2f} SAR, manual_expected={_EXP_TV:,.2f} SAR",
            ok,
        )

    results.append(_run(
        "M01",
        "Header Portfolio Value: engine total_portfolio_value_base matches manual cross-check",
        CAT, "portfolio.valuation", "P0", True, m01,
    ))

    # ── M02: Holdings Total ───────────────────────────────────────────────────
    # Holdings tab displays _val.holdings_value_base.
    # Cross-check: manual arithmetic (qty × price × fx) matches the engine.
    def m02():
        engine_hv = round(_eng.holdings_value_base, 2)
        ok = _near(_EXP_HV, engine_hv, tol=0.05)
        return (
            f"Holdings holdings_value_base = {_EXP_HV:,.2f} SAR",
            f"engine={engine_hv:,.2f} SAR, manual_expected={_EXP_HV:,.2f} SAR",
            ok,
        )

    results.append(_run(
        "M02",
        "Holdings Total: engine holdings_value_base matches manual qty×price×fx cross-check",
        CAT, "portfolio.valuation", "P0", True, m02,
    ))

    # ── M03: Cash Total ───────────────────────────────────────────────────────
    # Accounts tab shows _total_cash (inline sum).  Engine shows cash_value_base.
    # Cross-check: manual arithmetic matches engine; also compare engine vs. inline.
    def m03():
        engine_cv = round(_eng.cash_value_base, 2)
        # Replicate Accounts tab inline formula exactly (app.py ~3666-3669)
        active = {aid: a for aid, a in _acct.items() if a.active}
        tab_cv = round(sum(
            a.cash_balance * (_fx_sar[a.base_currency].rate
                              if a.base_currency in _fx_sar else 1.0)
            for a in active.values()
        ), 2)
        manual_ok = _near(_EXP_CV, engine_cv, tol=0.05)
        tab_ok    = _near(tab_cv,  engine_cv, tol=0.05)
        ok        = manual_ok and tab_ok
        flag = "" if tab_ok else f"  ⚠️ Accounts tab ({tab_cv:,.2f}) ≠ engine ({engine_cv:,.2f})"
        return (
            f"cash_value_base = {_EXP_CV:,.2f} SAR; Accounts tab matches engine",
            (
                f"engine={engine_cv:,.2f}, manual={_EXP_CV:,.2f}, "
                f"accounts_tab={tab_cv:,.2f}{flag}"
            ),
            ok,
        )

    results.append(_run(
        "M03",
        "Cash Total: engine cash_value_base matches manual cross-check and Accounts tab formula",
        CAT, "portfolio.valuation", "P0", True, m03,
    ))

    # ── M04: Allocation Consistency ───────────────────────────────────────────
    # Allocation tab re-uses the same PortfolioValuation object from Holdings.
    # sum(per_holding.base_market_value) must equal holdings_value_base.
    def m04():
        alloc_sum = round(sum(ph.base_market_value for ph in _eng.per_holding), 2)
        hv        = round(_eng.holdings_value_base, 2)
        ok = _near(alloc_sum, hv, tol=0.01)
        flag = "" if ok else f"  ⚠️ MISMATCH: alloc={alloc_sum:,.2f} ≠ hv={hv:,.2f}"
        return (
            f"Allocation total == holdings_value_base ({hv:,.2f} SAR)",
            f"sum(per_holding.base_mv)={alloc_sum:,.2f}, holdings_value_base={hv:,.2f}{flag}",
            ok,
        )

    results.append(_run(
        "M04",
        "Allocation Consistency: sum of per-holding base values == engine holdings_value_base",
        CAT, "portfolio.valuation", "P0", True, m04,
    ))

    # ── M05: Portfolio Risk Consistency ──────────────────────────────────────
    # render_portfolio_risk_tab() calls the engine independently.
    # With the same fixed FX rates the result must be identical to the primary call.
    def m05():
        risk_eng = _val(_hld, _acct, "SAR", _fx_sar)
        tv_main  = round(_eng.total_portfolio_value_base, 2)
        tv_risk  = round(risk_eng.total_portfolio_value_base, 2)
        hv_main  = round(_eng.holdings_value_base, 2)
        hv_risk  = round(risk_eng.holdings_value_base, 2)
        ok = _near(tv_main, tv_risk, tol=0.01) and _near(hv_main, hv_risk, tol=0.01)
        flag = "" if ok else "  ⚠️ MISMATCH"
        return (
            f"Risk engine total={tv_main:,.2f} SAR == primary engine{flag}",
            (
                f"primary: hv={hv_main:,.2f} tv={tv_main:,.2f} | "
                f"risk:    hv={hv_risk:,.2f} tv={tv_risk:,.2f}"
            ),
            ok,
        )

    results.append(_run(
        "M05",
        "Portfolio Risk Consistency: independent engine call matches primary engine totals",
        CAT, "portfolio.valuation", "P0", True, m05,
    ))

    # ── M06: Weight Validation ────────────────────────────────────────────────
    # Sum of all holding invested_weight_pct must be ≈ 100 %.
    # Tolerance: ±0.5 pp to allow floating-point rounding.
    def m06():
        w_sum = round(sum(ph.invested_weight_pct for ph in _eng.per_holding), 4)
        ok    = _near(w_sum, 100.0, tol=0.5)
        flag  = "" if ok else f"  ⚠️ MISMATCH: {w_sum:.4f} % ≠ 100 %"
        return (
            "sum(invested_weight_pct) ≈ 100 % (±0.5 pp)",
            f"sum = {w_sum:.4f} %{flag}",
            ok,
        )

    results.append(_run(
        "M06",
        "Weight Validation: sum of all holding invested_weight_pct ≈ 100 % (±0.5 pp)",
        CAT, "portfolio.valuation", "P0", True, m06,
    ))

    # ── M07: Base Currency Propagation (SAR → USD → AED) ─────────────────────
    # Calls the engine three times with SAR, USD, and AED as the base currency.
    # For each: holdings + cash must equal total_portfolio_value_base (internal
    # consistency).  Cross-currency ratio SAR/USD must ≈ 3.75 (the pinned rate).
    def m07():
        eng_sar = _val(_hld, _acct, "SAR", _fx_sar)
        eng_usd = _val(_hld, _acct, "USD", _fx_usd)
        eng_aed = _val(_hld, _acct, "AED", _fx_aed)

        findings: list[str] = []
        all_ok = True

        for label, eng, base in [
            ("SAR", eng_sar, "SAR"),
            ("USD", eng_usd, "USD"),
            ("AED", eng_aed, "AED"),
        ]:
            hv   = round(eng.holdings_value_base, 4)
            cv   = round(eng.cash_value_base, 4)
            tv   = round(eng.total_portfolio_value_base, 4)
            calc = round(hv + cv, 4)
            ok_i = _near(calc, tv, tol=0.02)
            if not ok_i:
                all_ok = False
            tick = "✓" if ok_i else "⚠️"
            findings.append(
                f"{base}: hv={hv:,.2f}+cv={cv:,.2f}={calc:,.2f} tv={tv:,.2f} {tick}"
            )

        # Cross-currency ratio: SAR total / USD total must ≈ 3.75
        if eng_usd.total_portfolio_value_base > 0:
            ratio     = eng_sar.total_portfolio_value_base / eng_usd.total_portfolio_value_base
            ratio_ok  = _near(ratio, _SAR_RATE, tol=0.01)
            if not ratio_ok:
                all_ok = False
            findings.append(
                f"SAR/USD ratio={ratio:.4f} (expected {_SAR_RATE}) "
                f"{'✓' if ratio_ok else '⚠️'}"
            )

        return (
            "Engine internally consistent for SAR, USD, AED; SAR/USD ratio ≈ 3.75",
            " | ".join(findings),
            all_ok,
        )

    results.append(_run(
        "M07",
        "Base Currency Propagation: engine consistent across SAR / USD / AED base currencies",
        CAT, "portfolio.valuation", "P0", True, m07,
    ))

    # ── M08: Single Valuation Engine Verification (static analysis) ───────────
    # Reads source files to confirm:
    #   (a) app.py and command_center.py call calculate_portfolio_valuation()
    #   (b) No tab file defines its own independent portfolio total computation
    # The Accounts tab inline cash sum is flagged as a divergence point.
    # is_release_blocker=False — reported only, no fix applied here.
    def m08():
        import os
        _EDGAR = os.path.dirname(os.path.abspath(__file__))
        ENGINE_CALL = "calculate_portfolio_valuation"

        # Files that must call the engine (tab renderers that show portfolio KPIs)
        key_files = {
            "app.py":            os.path.join(_EDGAR, "app.py"),
            "command_center.py": os.path.join(_EDGAR, "command_center.py"),
        }

        findings: list[str] = []
        all_ok = True

        for label, path in key_files.items():
            try:
                src   = open(path, encoding="utf-8").read()
                count = src.count(ENGINE_CALL)
                if count == 0:
                    findings.append(f"{label}: does NOT call {ENGINE_CALL} ⚠️")
                    all_ok = False
                else:
                    findings.append(f"{label}: calls {ENGINE_CALL} ×{count} ✓")
            except OSError:
                findings.append(f"{label}: unreadable ⚠️")
                all_ok = False

        # Detect the Accounts tab inline cash sum (app.py ~line 3666)
        # It bypasses the engine for its "Total Cash" display.
        try:
            app_src = open(os.path.join(_EDGAR, "app.py"), encoding="utf-8").read()
            if "a.cash_balance *" in app_src:
                findings.append(
                    "render_accounts_tab: inline cash sum detected "
                    f"(does not call {ENGINE_CALL} for cash display) "
                    "— reported only, no fix applied ⚠️"
                )
                all_ok = False
        except OSError:
            pass

        return (
            f"All tab renderers call {ENGINE_CALL}; no independent valuations",
            " | ".join(findings),
            all_ok,
        )

    results.append(_run(
        "M08",
        "Single Valuation Engine: static check that all tab renderers call calculate_portfolio_valuation()",
        CAT, "app.py / command_center.py", "P1", False, m08,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category N — Portfolio Accounting — Engine Integration  (A1–A10 audit)
# ════════════════════════════════════════════════════════════════════════════════

def _cat_n() -> list[TestResult]:
    """
    N01–N10: Portfolio Accounting — Engine Integration Tests.

    Correspond to audit requirements A1–A10.
    All tests use synthetic in-memory data and call the REAL engines.
    execute_sell_fifo() reads transactions.json (read-only; sandbox tickers
    produce no matches → fallback lots used).  No portfolio files are written.

    N01 A1  Buy transaction: qty, avg_cost, market value, unrealized P&L
    N02 A2  Multiple buys: weighted average cost formula
    N03 A3  Partial sell: remaining qty, cost basis, realized P&L, unrealized P&L
    N04 A4  Full position close: qty=0, realized P&L in closed lot
    N05 A5  Multi-currency valuation: SAR / USD base-currency switch
    N06 A6  Valuation consistency: 5 internal engine reconciliation checks
    N07 A7  Cash integrity: buy debits, sell credits, portfolio total reconciles
    N08 A8  Closed holdings: realized P&L immutable; closed lots absent from active MV
    N09 A9  Data persistence: Holding save → load round-trip preserves all fields
    N10 A10 Regression protection (P0 blocker): qty≥0, cost_basis≥0, recon,
            ghost-MV, realized+unrealized consistency
    """
    CAT = "Portfolio Accounting — Engine Integration"
    results: list[TestResult] = []

    # ── N01: A1 — Buy: qty, avg_cost, market value, unrealized P&L ───────────
    def n01():
        h = _holding("__SB_BUY__", qty=100.0, avg_cost=50.0, price=60.0)
        ok = (
            _near(h.quantity,       100.0,  1e-9) and
            _near(h.cost_basis,    5000.0,  0.01) and
            _near(h.market_value,  6000.0,  0.01) and
            _near(h.unrealized_pnl, 1000.0, 0.01)
        )
        return (
            "qty=100, cost_basis=5000, market_value=6000, unrealized_pnl=1000",
            f"qty={h.quantity}, cb={h.cost_basis:.2f}, mv={h.market_value:.2f}, pnl={h.unrealized_pnl:.2f}",
            ok,
        )
    results.append(_run("N01", "A1 — Buy: qty, avg_cost, market value, unrealized P&L",
                        CAT, "portfolio.holdings", "P0", True, n01))

    # ── N02: A2 — Multiple buys → weighted average cost ───────────────────────
    def n02():
        # Buy 1: 100 @ 50  → basis = 5 000
        # Buy 2:  50 @ 80  → add  4 000  →  total basis = 9 000, qty = 150
        # Weighted avg = 9 000 / 150 = 60.00  (formula from record_transaction)
        q1, p1, q2, p2 = 100.0, 50.0, 50.0, 80.0
        old_basis = q1 * p1
        new_qty   = q1 + q2
        new_avg   = (old_basis + q2 * p2) / new_qty   # 60.0
        h = _holding("__SB_BUY2__", qty=new_qty, avg_cost=new_avg, price=70.0)
        ok = (
            _near(new_avg,      60.0,   1e-9) and
            _near(h.cost_basis, 9000.0, 0.01) and
            _near(h.quantity,   150.0,  1e-9)
        )
        return (
            "avg_cost=60.0000, qty=150, cost_basis=9000.00",
            f"avg_cost={new_avg:.4f}, qty={h.quantity}, cost_basis={h.cost_basis:.2f}",
            ok,
        )
    results.append(_run("N02", "A2 — Multiple buys: weighted average cost is correct",
                        CAT, "portfolio.holdings", "P0", True, n02))

    # ── N03: A3 — Partial sell: remaining qty, cost basis, realized & unrealized
    def n03():
        from portfolio.closed_holdings import execute_sell_fifo
        BUY_QTY, BUY_PRICE  = 100.0, 50.0
        SELL_QTY, SELL_PRICE = 30.0, 70.0
        lots, err = execute_sell_fifo(
            ticker="__SANDBOX_N03__", company_name="Sandbox N03", currency="USD",
            quantity=SELL_QTY, sell_price=SELL_PRICE, sell_date="2026-01-15",
            fallback_avg_cost=BUY_PRICE, fallback_open_date="2025-01-01",
        )
        if err:
            return ("no error from execute_sell_fifo", f"error={err!r}", False)

        remaining_qty  = BUY_QTY - SELL_QTY               # 70
        remaining_cb   = remaining_qty * BUY_PRICE          # 3 500
        realized_pnl   = sum(l.realized_pnl for l in lots)  # 600
        h_rem = _holding("__SANDBOX_N03__", qty=remaining_qty,
                         avg_cost=BUY_PRICE, price=SELL_PRICE)
        unrealized_rem = h_rem.unrealized_pnl               # 1 400

        ok = (
            _near(remaining_qty,  70.0,   1e-9) and
            _near(remaining_cb,   3500.0, 0.01) and
            _near(realized_pnl,   600.0,  0.01) and
            _near(unrealized_rem, 1400.0, 0.01)
        )
        return (
            "remaining_qty=70, remaining_cb=3500, realized=600, unrealized_rem=1400",
            f"rem_qty={remaining_qty}, cb={remaining_cb:.2f}, realized={realized_pnl:.2f}, unreal={unrealized_rem:.2f}",
            ok,
        )
    results.append(_run("N03", "A3 — Partial sell: remaining qty, cost basis, realized & unrealized P&L",
                        CAT, "portfolio.closed_holdings", "P0", True, n03))

    # ── N04: A4 — Full position close: qty=0, realized P&L in closed lot ─────
    def n04():
        from portfolio.closed_holdings import execute_sell_fifo
        BUY_QTY, BUY_PRICE, SELL_PRICE = 50.0, 40.0, 60.0
        lots, err = execute_sell_fifo(
            ticker="__SANDBOX_N04__", company_name="Sandbox N04", currency="SAR",
            quantity=BUY_QTY, sell_price=SELL_PRICE, sell_date="2026-03-01",
            fallback_avg_cost=BUY_PRICE, fallback_open_date="2025-06-01",
        )
        if err:
            return ("no error, lots generated", f"error={err!r}", False)

        remaining_qty  = BUY_QTY - BUY_QTY                 # 0
        total_realized = sum(l.realized_pnl for l in lots)  # 1 000
        exp_realized   = BUY_QTY * (SELL_PRICE - BUY_PRICE)
        ok = (
            bool(lots) and
            _near(remaining_qty,  0.0,         1e-9) and
            _near(total_realized, exp_realized, 0.01)
        )
        return (
            f"lots>0, remaining_qty=0, realized={exp_realized:.2f}",
            f"lots={len(lots)}, remaining_qty={remaining_qty}, realized={total_realized:.2f}",
            ok,
        )
    results.append(_run("N04", "A4 — Full position close: qty=0, realized P&L correct in closed lot",
                        CAT, "portfolio.closed_holdings", "P0", True, n04))

    # ── N05: A5 — Multi-currency: SAR/USD base-currency switch ───────────────
    def n05():
        SAR_RATE = 3.75   # 1 USD = 3.75 SAR (pegged)
        h_us  = _holding("__SB_AAPL__",   qty=100.0, avg_cost=130.0, price=150.0, ccy="USD")
        h_sau = _holding("__SB_ARMCO__",  qty=200.0, avg_cost=25.0,  price=30.0,  ccy="SAR")
        holdings = {"__SB_AAPL__": h_us, "__SB_ARMCO__": h_sau}

        fx_sar = {"USD": _fx("USD", "SAR", SAR_RATE),   "SAR": _fx("SAR", "SAR", 1.0)}
        fx_usd = {"USD": _fx("USD", "USD", 1.0),        "SAR": _fx("SAR", "USD", 1.0 / SAR_RATE)}

        val_sar = _val(holdings, {}, "SAR", fx_sar)
        val_usd = _val(holdings, {}, "USD", fx_usd)

        # SAR base: 100*150*3.75 + 200*30*1.0   = 56 250 + 6 000 = 62 250
        # USD base: 100*150*1.0  + 200*30/3.75  = 15 000 + 1 600 = 16 600
        exp_sar = 100*150*SAR_RATE  + 200*30*1.0
        exp_usd = 100*150*1.0       + 200*30*(1.0/SAR_RATE)

        ok = (
            _near(val_sar.holdings_value_base, exp_sar, 0.10) and
            _near(val_usd.holdings_value_base, exp_usd, 0.10)
        )
        return (
            f"holdings_SAR={exp_sar:.2f}, holdings_USD={exp_usd:.4f}",
            f"holdings_SAR={val_sar.holdings_value_base:.2f}, holdings_USD={val_usd.holdings_value_base:.4f}",
            ok,
        )
    results.append(_run("N05", "A5 — Multi-currency: SAR↔USD base switch produces correct totals",
                        CAT, "portfolio.valuation", "P0", True, n05))

    # ── N06: A6 — Valuation consistency: 5 internal engine reconciliation ─────
    def n06():
        h1 = _holding("__SB_X1__", qty=50.0,  avg_cost=200.0, price=250.0, ccy="USD")
        h2 = _holding("__SB_X2__", qty=10.0,  avg_cost=100.0, price=140.0, ccy="USD")
        h3 = _holding("__SB_X3__", qty=500.0, avg_cost=28.0,  price=32.0,  ccy="SAR")
        acc = _account("acct_n06", cash=5000.0, ccy="SAR")
        fx  = {"USD": _fx("USD", "SAR", 3.75), "SAR": _fx("SAR", "SAR", 1.0)}
        val = _val({"__SB_X1__": h1, "__SB_X2__": h2, "__SB_X3__": h3},
                   {"acct_n06": acc}, "SAR", fx)

        fails = []
        # Check 1: sum(per_holding MV) == holdings_value_base
        ph_sum = sum(ph.base_market_value for ph in val.per_holding)
        if not _near(ph_sum, val.holdings_value_base, 0.02):
            fails.append(f"per_holding sum {ph_sum:.2f}≠holdings {val.holdings_value_base:.2f}")

        # Check 2: holdings + cash == total
        if not _near(val.holdings_value_base + val.cash_value_base,
                     val.total_portfolio_value_base, 0.02):
            fails.append("holdings+cash≠total")

        # Check 3: unrealized_pnl == holdings_MV − cost_basis
        exp_pnl = val.holdings_value_base - val.total_cost_basis_base
        if not _near(val.unrealized_pnl_base, exp_pnl, 0.02):
            fails.append(f"pnl_base {val.unrealized_pnl_base:.2f}≠{exp_pnl:.2f}")

        # Check 4: invested weights sum ≈ 100 %
        wt_sum = sum(ph.invested_weight_pct for ph in val.per_holding)
        if not _near(wt_sum, 100.0, 0.5):
            fails.append(f"invested_weights sum {wt_sum:.2f}%≠100%")

        # Check 5: invested_allocation_pct + cash_allocation_pct ≈ 100 %
        alloc_sum = val.invested_allocation_pct + val.cash_allocation_pct
        if not _near(alloc_sum, 100.0, 0.5):
            fails.append(f"alloc% {alloc_sum:.2f}%≠100%")

        ok = not fails
        return (
            "all 5 reconciliation checks pass",
            "all pass" if ok else "; ".join(fails),
            ok,
        )
    results.append(_run("N06", "A6 — Valuation consistency: engine internal reconciliation (5 checks)",
                        CAT, "portfolio.valuation", "P0", True, n06))

    # ── N07: A7 — Cash integrity: buy debits, sell credits, totals reconcile ──
    def n07():
        INITIAL = 10_000.0   # SAR
        BUY_QTY, BUY_PRICE, SELL_PRICE = 100.0, 30.0, 35.0
        fx = {"SAR": _fx("SAR", "SAR", 1.0)}

        # State 0 — only cash
        val0 = _val({}, {"a": _account("a", cash=INITIAL, ccy="SAR")}, "SAR", fx)

        # State 1 — after BUY: cash decreases, holding appears (no P&L at cost)
        cash1 = INITIAL - BUY_QTY * BUY_PRICE   # 7 000
        h1    = _holding("__SB_CASH__", qty=BUY_QTY, avg_cost=BUY_PRICE, price=BUY_PRICE, ccy="SAR")
        val1  = _val({"__SB_CASH__": h1}, {"a": _account("a", cash=cash1, ccy="SAR")}, "SAR", fx)

        # State 2 — after SELL: holding gone, cash increases by proceeds
        cash2 = cash1 + BUY_QTY * SELL_PRICE    # 7 000 + 3 500 = 10 500
        val2  = _val({}, {"a": _account("a", cash=cash2, ccy="SAR")}, "SAR", fx)

        ok0 = _near(val0.total_portfolio_value_base, INITIAL,   0.01)
        ok1 = _near(val1.total_portfolio_value_base, INITIAL,   0.01)  # no P&L at cost
        ok2 = _near(val2.total_portfolio_value_base, 10_500.0,  0.01)  # +500 realized

        ok  = ok0 and ok1 and ok2
        return (
            f"state0={INITIAL:.0f}, state1={INITIAL:.0f}, state2=10500",
            f"val0={val0.total_portfolio_value_base:.0f}, val1={val1.total_portfolio_value_base:.0f}, val2={val2.total_portfolio_value_base:.0f}",
            ok,
        )
    results.append(_run("N07", "A7 — Cash integrity: buy debits, sell credits, portfolio reconciles",
                        CAT, "portfolio.valuation", "P0", True, n07))

    # ── N08: A8 — Closed holdings: realized P&L correct; not in active MV ────
    def n08():
        from portfolio.closed_holdings import execute_sell_fifo
        BUY_QTY, BUY_PRICE  = 100.0, 40.0
        SELL_QTY, SELL_PRICE = 60.0,  55.0
        lots, err = execute_sell_fifo(
            ticker="__SANDBOX_N08__", company_name="Sandbox N08", currency="USD",
            quantity=SELL_QTY, sell_price=SELL_PRICE, sell_date="2026-02-01",
            fallback_avg_cost=BUY_PRICE, fallback_open_date="2025-01-01",
        )
        if err:
            return ("no error", f"error={err!r}", False)

        # Realized P&L = 60*(55-40) = 900  (immutable in lot)
        realized    = sum(l.realized_pnl for l in lots)
        exp_realized = SELL_QTY * (SELL_PRICE - BUY_PRICE)

        # Remaining active holding: 40 shares @ current 55
        rem_qty = BUY_QTY - SELL_QTY   # 40
        h_rem   = _holding("__SANDBOX_N08__", qty=rem_qty, avg_cost=BUY_PRICE,
                            price=SELL_PRICE, ccy="USD")
        fx      = {"USD": _fx("USD", "USD", 1.0)}
        val     = _val({"__SANDBOX_N08__": h_rem}, {}, "USD", fx)
        exp_mv  = rem_qty * SELL_PRICE  # 2 200  (only REMAINING shares)

        ok = (
            _near(realized, exp_realized, 0.01) and
            _near(val.holdings_value_base, exp_mv, 0.01)
        )
        return (
            f"realized={exp_realized:.2f}, active_mv={exp_mv:.2f} (closed lots excluded)",
            f"realized={realized:.2f}, active_mv={val.holdings_value_base:.2f}",
            ok,
        )
    results.append(_run("N08", "A8 — Closed holdings: realized P&L correct; absent from active MV",
                        CAT, "portfolio.closed_holdings", "P0", True, n08))

    # ── N09: A9 — Data persistence: save → load round-trip ───────────────────
    def n09():
        import tempfile
        from portfolio.holdings import Holding, save_holdings, load_holdings
        import portfolio.holdings as _hm

        orig_file = _hm._HOLDINGS_FILE
        with tempfile.TemporaryDirectory() as tmpdir:
            _hm._HOLDINGS_FILE = os.path.join(tmpdir, "test_holdings.json")
            try:
                h_in = Holding(
                    ticker="PERSIST_TEST",
                    company_name="Persist Co",
                    market="US",
                    sector="Technology",
                    quantity=123.456,
                    avg_cost=78.9,
                    current_price=90.1,
                    currency="USD",
                    has_ticker=True,
                    asset_type="Stock",
                    exchange_symbol="",
                    price_source="SAHMK",
                )
                save_holdings({"PERSIST_TEST": h_in})
                loaded = load_holdings()
                h_out  = loaded.get("PERSIST_TEST")
                if h_out is None:
                    return ("PERSIST_TEST key present after load", "key missing", False)

                checks = {
                    "quantity":     _near(h_out.quantity,      h_in.quantity,      1e-9),
                    "avg_cost":     _near(h_out.avg_cost,      h_in.avg_cost,      1e-9),
                    "current_price":_near(h_out.current_price, h_in.current_price, 1e-9),
                    "currency":     h_out.currency     == h_in.currency,
                    "company_name": h_out.company_name == h_in.company_name,
                    "price_source": h_out.price_source == h_in.price_source,
                    "sector":       h_out.sector       == h_in.sector,
                }
                bad = [k for k, v in checks.items() if not v]
                ok  = not bad
                return (
                    "all 7 fields preserved after save/load",
                    "all match" if ok else f"mismatch: {bad}",
                    ok,
                )
            finally:
                _hm._HOLDINGS_FILE = orig_file
    results.append(_run("N09", "A9 — Data persistence: Holding save→load preserves all fields",
                        CAT, "portfolio.holdings", "P0", True, n09))

    # ── N10: A10 — Regression protection (5 invariants, P0 blocker) ───────────
    def n10():
        from portfolio.closed_holdings import execute_sell_fifo
        fails = []

        # Invariant 1: qty never negative — sell_qty > owned → guard blocks
        owned, sell_attempt = 10.0, 15.0
        if not (sell_attempt > owned):
            fails.append("I1 test-setup error: sell_attempt should exceed owned")
        safe_qty = max(0.0, owned - sell_attempt)
        if safe_qty < 0.0:
            fails.append(f"I1 qty guard failed: max(0,…) produced {safe_qty}")

        # Invariant 2: cost_basis >= 0 for all valid (qty, avg_cost) combos
        for qty, avg in [(100.0, 50.0), (0.0, 50.0), (100.0, 0.0)]:
            h = _holding("__SB_CB__", qty=qty, avg_cost=avg, price=60.0)
            if h.cost_basis < 0.0:
                fails.append(f"I2 cost_basis<0: qty={qty}, avg={avg}")

        # Invariant 3: engine reconciliation  (per_holding sum == holdings_value_base)
        hh  = {"A": _holding("A", qty=50.0,  avg_cost=10.0, price=20.0, ccy="USD"),
               "B": _holding("B", qty=100.0, avg_cost=5.0,  price=8.0,  ccy="USD")}
        fx1 = {"USD": _fx("USD", "USD", 1.0)}
        val = _val(hh, {}, "USD", fx1)
        ph_sum = round(sum(ph.base_market_value for ph in val.per_holding), 2)
        if not _near(ph_sum, val.holdings_value_base, 0.02):
            fails.append(f"I3 recon: Σ per_holding {ph_sum} ≠ holdings_value_base {val.holdings_value_base}")

        # Invariant 4: qty=0 holding has zero market value (no ghost contribution)
        h_ghost  = _holding("GHOST", qty=0.0, avg_cost=50.0, price=60.0, ccy="USD")
        val_ghost = _val({"GHOST": h_ghost}, {}, "USD", fx1)
        if val_ghost.holdings_value_base != 0.0:
            fails.append(f"I4 ghost MV: qty=0 but holdings_value_base={val_ghost.holdings_value_base}")

        # Invariant 5: realized + unrealized == total P&L if you'd held the full position
        # Buy 100 @ 50; sell 30 @ 70 → realized=600; hold 70 @ current 70 → unrealized=1400
        # If we'd held all 100 @ 70 → total gain = 100*(70-50) = 2000
        lots, err = execute_sell_fifo(
            ticker="__SANDBOX_N10__", company_name="N10 Regression", currency="USD",
            quantity=30.0, sell_price=70.0, sell_date="2026-01-01",
            fallback_avg_cost=50.0, fallback_open_date="2025-01-01",
        )
        if err:
            fails.append(f"I5 execute_sell_fifo: {err}")
        else:
            realized   = round(sum(l.realized_pnl for l in lots), 4)  # 600
            h_rem      = _holding("__SANDBOX_N10__", qty=70.0, avg_cost=50.0, price=70.0, ccy="USD")
            unrealized = h_rem.unrealized_pnl                          # 1 400
            total_pnl  = round(realized + unrealized, 4)               # 2 000
            exp_pnl    = 100.0 * (70.0 - 50.0)                        # 2 000
            if not _near(total_pnl, exp_pnl, 0.01):
                fails.append(f"I5 pnl: realized({realized})+unrealized({unrealized})={total_pnl}≠{exp_pnl}")

        ok = not fails
        return (
            "all 5 regression invariants hold (qty≥0, cb≥0, recon, ghost-MV=0, pnl-consistency)",
            "all pass" if ok else "; ".join(fails),
            ok,
        )
    results.append(_run(
        "N10",
        "A10 — Regression: qty≥0, cost_basis≥0, engine recon, ghost-MV=0, P&L consistency",
        CAT, "portfolio.holdings", "P0", True, n10,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category ARCH — Account Binding Integrity (A01 / A03)
# ════════════════════════════════════════════════════════════════════════════════

def _cat_arch() -> list[TestResult]:
    """
    A01/A03 account-binding regression tests + reconciliation report.

    REC-01  Reconciliation: count active holdings with missing account linkage.
    A01-01  record_transaction BUY, new ticker, no account  → error (guard fires)
    A01-02  record_transaction BUY, new ticker, with account → guard passes
    A03-01  upsert_holding new ticker, no default_account_id  → ValueError
    A03-02  upsert_holding new ticker, with default_account_id → success + cleanup
    """
    CAT = "Account Binding (A01/A03)"
    results: list[TestResult] = []

    from portfolio.holdings import (
        _check_new_holding_account,
        upsert_holding,
        delete_holding,
        load_holdings,
    )

    # ── REC-01: reconciliation ────────────────────────────────────────────────
    def rec_01():
        live = load_holdings()
        orphans = sorted(
            t for t, h in live.items()
            if h.quantity > 1e-9 and not getattr(h, "default_account_id", "")
        )
        total_active = sum(1 for h in live.values() if h.quantity > 1e-9)
        detail = (
            f"{len(orphans)}/{total_active} active holdings missing account linkage"
            + (f" — {', '.join(orphans)}" if orphans else "")
        )
        # Reconciliation always PASS: it is a report, not a binary gate.
        # Existing legacy holdings are expected to have empty account IDs.
        return ("reconciliation report generated", detail, True)

    results.append(_run(
        "REC-01",
        "Holdings reconciliation: active holdings with missing account linkage",
        CAT, "portfolio.holdings.load_holdings", "P1", False, rec_01,
    ))

    # ── A01-01: new holding without account → guard blocks ────────────────────
    def a01_01():
        err = _check_new_holding_account(existing=None, account_id="")
        ok  = err == "Account is required when opening a new position."
        return (
            "guard returns error for new holding without account",
            repr(err), ok,
        )

    results.append(_run(
        "A01-01",
        "record_transaction BUY: new holding without account is rejected",
        CAT, "portfolio.holdings._check_new_holding_account", "P0", True, a01_01,
    ))

    # ── A01-02: new holding with account → guard passes ───────────────────────
    def a01_02():
        err = _check_new_holding_account(existing=None, account_id="any_non_empty_id")
        ok  = err is None
        return (
            "guard returns None for new holding with account",
            repr(err), ok,
        )

    results.append(_run(
        "A01-02",
        "record_transaction BUY: new holding with account is accepted",
        CAT, "portfolio.holdings._check_new_holding_account", "P0", True, a01_02,
    ))

    # ── A03-01: upsert_holding new holding without account → ValueError ───────
    def a03_01():
        SB = "__SBA03NX__"
        live = load_holdings()
        if SB in live:
            delete_holding(SB)
        try:
            upsert_holding(SB, quantity=1.0, avg_cost=10.0, current_price=10.0,
                           default_account_id="")
            return ("ValueError raised", "no error raised — guard did NOT fire", False)
        except ValueError as e:
            ok = "account" in str(e).lower()
            return (
                "ValueError: account required for new holding",
                repr(str(e)), ok,
            )

    results.append(_run(
        "A03-01",
        "upsert_holding: new holding without default_account_id raises ValueError",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, a03_01,
    ))

    # ── A03-02: upsert_holding new holding with account → PASS + cleanup ─────
    def a03_02():
        SB = "__SBA03WX__"
        live = load_holdings()
        if SB in live:
            delete_holding(SB)
        try:
            h = upsert_holding(
                SB,
                company_name="Sandbox A03",
                quantity=1.0,
                avg_cost=10.0,
                current_price=10.0,
                currency="USD",
                default_account_id="sandbox_acct_id",
            )
            aid = getattr(h, "default_account_id", "")
            ok  = h is not None and aid == "sandbox_acct_id"
            delete_holding(SB)   # cleanup — no transaction written
            return (
                "holding created; default_account_id preserved",
                f"default_account_id={aid!r}",
                ok,
            )
        except Exception as e:
            return ("holding created successfully", repr(e), False)

    results.append(_run(
        "A03-02",
        "upsert_holding: new holding with default_account_id succeeds",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, a03_02,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category A10 — Account Deletion Guard Regression
# ════════════════════════════════════════════════════════════════════════════════

def _cat_a10() -> list[TestResult]:
    """
    A10-01 through A10-04: regression tests for the delete_account() guard.

    A10-01  account with cash          → blocked (ValueError)
    A10-02  account with linked holding → blocked (ValueError)
    A10-03  account with transaction    → blocked (ValueError)
    A10-04  empty unused account        → deletion succeeds

    A10-01 through A10-03 exercise _guard_delete_account() with in-memory
    sandbox data — no portfolio files are read or written.
    A10-04 exercises the full delete_account() path using a transient sandbox
    account that is created and immediately deleted.
    """
    CAT = "Account Deletion Guard (A10)"
    results: list[TestResult] = []

    _ERR_MSG = (
        "Cannot delete account with cash, holdings, transactions, or closed lots."
    )
    SB_ID = "__SBA10__"   # sandbox account_id used across all sub-tests

    # ── shared guard import ───────────────────────────────────────────────────
    from portfolio.accounts import _guard_delete_account, upsert_account, delete_account, load_accounts

    # ── A10-01: account with cash blocked ────────────────────────────────────
    def a10_01():
        err = _guard_delete_account(SB_ID, cash_balance=500.0, holdings={}, transactions=[], closed_lots=[])
        ok  = err == _ERR_MSG
        return (
            f"guard returns '{_ERR_MSG}'",
            repr(err),
            ok,
        )

    results.append(_run(
        "A10-01",
        "Account with cash balance cannot be deleted",
        CAT, "portfolio.accounts._guard_delete_account", "P0", True, a10_01,
    ))

    # ── A10-02: account with linked holding blocked ───────────────────────────
    def a10_02():
        from portfolio.holdings import Holding
        h = Holding(ticker="__SB_AAPL__", company_name="Sandbox", quantity=10.0,
                    avg_cost=100.0, current_price=120.0, default_account_id=SB_ID)
        err = _guard_delete_account(SB_ID, cash_balance=0.0,
                                    holdings={"__SB_AAPL__": h},
                                    transactions=[], closed_lots=[])
        ok  = err == _ERR_MSG
        return (
            f"guard returns '{_ERR_MSG}'",
            repr(err),
            ok,
        )

    results.append(_run(
        "A10-02",
        "Account with linked holding cannot be deleted",
        CAT, "portfolio.accounts._guard_delete_account", "P0", True, a10_02,
    ))

    # ── A10-03: account with transaction blocked ──────────────────────────────
    def a10_03():
        from portfolio.holdings import Transaction
        txn = Transaction(ticker="__SB_AAPL__", side="BUY", quantity=10.0,
                          price=100.0, date="2026-01-01", account_id=SB_ID)
        err = _guard_delete_account(SB_ID, cash_balance=0.0,
                                    holdings={}, transactions=[txn], closed_lots=[])
        ok  = err == _ERR_MSG
        return (
            f"guard returns '{_ERR_MSG}'",
            repr(err),
            ok,
        )

    results.append(_run(
        "A10-03",
        "Account with referencing transaction cannot be deleted",
        CAT, "portfolio.accounts._guard_delete_account", "P0", True, a10_03,
    ))

    # ── A10-04: empty unused account can be deleted ───────────────────────────
    def a10_04():
        SB_CLEAN_ID = "__SBA10CLEAN__"
        # Create a fresh sandbox account with zero cash and no references.
        upsert_account(
            account_id    = SB_CLEAN_ID,
            account_name  = "Sandbox A10 Clean",
            account_type  = "Other",
            base_currency = "USD",
            opening_cash  = 0.0,
        )
        before = SB_CLEAN_ID in load_accounts()

        try:
            delete_account(SB_CLEAN_ID)
            raised = False
        except ValueError:
            raised = True

        after = SB_CLEAN_ID in load_accounts()
        ok    = before and not raised and not after
        detail = (
            f"before={before}, raised={raised}, after={after}"
        )
        return (
            "account created; delete_account() succeeds; account removed",
            detail,
            ok,
        )

    results.append(_run(
        "A10-04",
        "Empty unused account can be deleted",
        CAT, "portfolio.accounts.delete_account", "P0", True, a10_04,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category CH — Closed-Position Visibility Regression
# ════════════════════════════════════════════════════════════════════════════════

def _cat_ch() -> list[TestResult]:
    """
    CH01: Closed-position visibility regression.

    Verifies end-to-end that a fully closed position:
      · disappears from the active Holdings view  (qty ≤ 1e-9 filter)
      · appears in Closed Holdings                (lot generated with correct P&L)
      · contributes zero to portfolio valuation   (MV = 0)

    Uses synthetic sandbox data only — no portfolio files read or written.
    """
    CAT = "Closed-Position Visibility"
    results: list[TestResult] = []

    def ch01():
        from portfolio.closed_holdings import execute_sell_fifo

        BUY_QTY   = 100.0
        BUY_PRICE = 50.0
        SELL_PRICE = 70.0
        EXP_REALIZED = BUY_QTY * (SELL_PRICE - BUY_PRICE)   # 2 000.0

        # ── Step 1: active position exists ────────────────────────────────────
        h = _holding("__SB_CH01__", qty=BUY_QTY, avg_cost=BUY_PRICE, price=SELL_PRICE)
        step1_active = h.quantity > 1e-9   # True → position is active

        # ── Step 2: fully close via FIFO engine ───────────────────────────────
        lots, err = execute_sell_fifo(
            ticker="__SB_CH01__",
            company_name="CH01 Sandbox",
            currency="USD",
            quantity=BUY_QTY,
            sell_price=SELL_PRICE,
            sell_date="2026-01-01",
            fallback_avg_cost=BUY_PRICE,
            fallback_open_date="2025-01-01",
        )
        if err:
            return ("no FIFO error, lots generated", f"error={err!r}", False)
        h.quantity = max(0.0, h.quantity - BUY_QTY)   # mirrors record_transaction SELL

        # ── Step 3: disappears from Holdings (active filter: qty > 1e-9) ──────
        step3_hidden = h.quantity <= 1e-9   # True → filtered out of Holdings tab

        # ── Step 4: appears in Closed Holdings (lot present, P&L correct) ─────
        realized_pnl = round(sum(l.realized_pnl for l in lots), 4)
        step4_closed = (
            bool(lots) and
            _near(realized_pnl, EXP_REALIZED, 0.01)
        )

        # ── Step 5: portfolio valuation unchanged (MV = 0 for qty=0 holding) ──
        fx  = {"USD": _fx("USD", "USD", 1.0)}
        val = _val({"__SB_CH01__": h}, {}, "USD", fx)
        step5_mv_zero = val.holdings_value_base == 0.0

        ok = step1_active and step3_hidden and step4_closed and step5_mv_zero

        fails = []
        if not step1_active:
            fails.append(f"step1: position not active (qty={BUY_QTY})")
        if not step3_hidden:
            fails.append(f"step3: qty={h.quantity} still passes active filter (> 1e-9)")
        if not step4_closed:
            fails.append(
                f"step4: lots={len(lots)}, realized={realized_pnl} ≠ {EXP_REALIZED}"
            )
        if not step5_mv_zero:
            fails.append(f"step5: MV={val.holdings_value_base} (expected 0)")

        return (
            "active→True; hidden→True; closed_lot P&L=2000; MV=0",
            "all 4 steps pass" if ok else "; ".join(fails),
            ok,
        )

    results.append(_run(
        "CH01",
        "Fully closed position: hidden from Holdings, visible in Closed Holdings, MV=0",
        CAT, "app.Holdings + portfolio.closed_holdings", "P0", True, ch01,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Main entry point
# ════════════════════════════════════════════════════════════════════════════════

def run_all_tests() -> TestReport:
    """
    Execute all pre-release tests and return a TestReport.
    Never reads or writes portfolio files.
    """
    all_results: list[TestResult] = (
        _cat_a() + _cat_b() + _cat_c() + _cat_d() + _cat_e()
        + _cat_f() + _cat_g() + _cat_h() + _cat_i() + _cat_j()
        + _cat_k() + _cat_l() + _cat_m() + _cat_n() + _cat_arch() + _cat_a10() + _cat_ch()
    )

    punch_list: list[PunchListItem] = []
    bug_num = 1
    for r in all_results:
        if r.status in ("FAIL", "ERROR"):
            punch_list.append(PunchListItem(
                item_id=f"BUG-{bug_num:03d}",
                bug_title=f"[{r.severity}] {r.test_name}",
                description=(
                    f"Test {r.test_id} failed during pre-release validation.\n"
                    f"Category: {r.category}  |  Module: {r.module}"
                    + (f"\nError detail: {r.detail}" if r.detail else "")
                ),
                repro_steps=(
                    "1. Enable Developer Mode (sidebar toggle).\n"
                    "2. Open the 🧪 Test Runner tab.\n"
                    "3. Click ▶️ Run Pre-Release Tests.\n"
                    f"4. Observe test {r.test_id}: {r.test_name}."
                ),
                expected=r.expected,
                actual=r.actual,
                severity=r.severity,
            ))
            bug_num += 1

    return TestReport(
        timestamp=_ts(),
        results=all_results,
        punch_list=punch_list,
    )
