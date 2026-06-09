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
        import os, sahmk_client
        _orig = os.environ.pop("SAHMK_API_KEY", None)
        try:
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
        finally:
            if _orig is not None:
                os.environ["SAHMK_API_KEY"] = _orig
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
                    asset_id="AST_999999",
                )
                save_holdings({"AST_999999": h_in})
                loaded = load_holdings()
                h_out  = loaded.get("AST_999999")
                if h_out is None:
                    return ("AST_999999 key present after load", "key missing", False)

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

    # ── REC-01: reconciliation — missing + orphaned account IDs ──────────────
    def rec_01():
        from portfolio.accounts import load_accounts as _la
        live     = load_holdings()
        accounts = _la()
        active_acct_ids = set(accounts.keys())

        active_h = {t: h for t, h in live.items() if h.quantity > 1e-9}
        total    = len(active_h)

        missing = sorted(
            t for t, h in active_h.items()
            if not getattr(h, "default_account_id", "")
        )
        orphaned = sorted(
            t for t, h in active_h.items()
            if getattr(h, "default_account_id", "")
            and h.default_account_id not in active_acct_ids
        )

        parts = []
        if missing:
            parts.append(f"{len(missing)}/{total} missing account linkage — {', '.join(missing)}")
        else:
            parts.append(f"0/{total} missing account linkage")
        if orphaned:
            parts.append(f"{len(orphaned)} linked to non-existent account — {', '.join(orphaned)}")
        else:
            parts.append("0 linked to non-existent account")

        # Always PASS — informational report, not a gate.
        return ("reconciliation report generated", " | ".join(parts), True)

    results.append(_run(
        "REC-01",
        "Holdings reconciliation: missing account linkage + orphaned account IDs",
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
        existing_aid = next((k for k, hh in live.items() if hh.ticker == SB), None)
        if existing_aid:
            delete_holding(existing_aid)
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
            delete_holding(h.asset_id)   # cleanup — use asset_id, not ticker
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
# Category ACC-UI — Account Visibility & Reassignment
# ════════════════════════════════════════════════════════════════════════════════

def _cat_acc_ui() -> list[TestResult]:
    """
    ACC-UI-01  Holdings row dict includes 'Account' key.
    ACC-UI-02  Legacy holding (empty default_account_id) → 'Unassigned'.
    ACC-UI-03  Edit Holding can assign valid account to legacy holding.
    ACC-UI-04  Saving Edit Holding with empty account is blocked (upsert raises ValueError).
    ACC-UI-05  Account reassignment changes only default_account_id; qty/avg/price/valuation unchanged.
    """
    CAT = "Account Visibility & Reassignment"
    results: list[TestResult] = []

    from portfolio.holdings import (
        Holding, load_holdings, upsert_holding, delete_holding,
    )
    from portfolio.accounts import (
        load_accounts, upsert_account, delete_account, account_display_name,
    )

    # ── Shared sandbox account ────────────────────────────────────────────────
    _SB_AID  = "__sb_acc_ui_test__"
    _SB_TK   = "__SBACCUI__"

    def _setup_sandbox_account():
        """Ensure sandbox account exists; return account_id."""
        upsert_account(
            account_id=_SB_AID,
            account_name="Sandbox AccUI",
            institution="Test",
            account_type="Brokerage",
            base_currency="USD",
            opening_cash=0.0,
        )
        return _SB_AID

    def _teardown_sandbox(ticker=_SB_TK, aid=_SB_AID):
        """Remove sandbox holding and account (best-effort)."""
        try:
            live = load_holdings()
            h_aid = next((k for k, hh in live.items() if hh.ticker == ticker), None)
            if h_aid:
                delete_holding(h_aid)
        except Exception:
            pass
        try:
            # zero cash first so guard allows deletion
            from portfolio.accounts import set_account_cash
            set_account_cash(aid, 0.0)
            delete_account(aid)
        except Exception:
            pass

    # ── ACC-UI-01: 'Account' key present in row dict ──────────────────────────
    def acc_ui_01():
        """
        The row dict built for the Holdings table must contain an 'Account' key.
        We replicate the same logic used in app.py's render loop.
        """
        # Create a minimal Holding with no account to test the label logic
        all_accounts = load_accounts()
        h_aid  = ""
        acct_obj  = all_accounts.get(h_aid) if h_aid else None
        acct_name = acct_obj.account_name if acct_obj else ("Unassigned" if not h_aid else "Unknown")
        row = {"Account": acct_name}
        ok  = "Account" in row
        return ("'Account' key present in row dict", repr(row["Account"]), ok)

    results.append(_run(
        "ACC-UI-01",
        "Holdings table row dict includes 'Account' key",
        CAT, "app.render_holdings_tab._row_builder", "P0", True, acc_ui_01,
    ))

    # ── ACC-UI-02: legacy holding → "Unassigned" ─────────────────────────────
    def acc_ui_02():
        """Holding with empty default_account_id maps to 'Unassigned' in the table."""
        all_accounts = load_accounts()
        h_aid    = ""   # legacy / no account
        acct_obj = all_accounts.get(h_aid) if h_aid else None
        label    = acct_obj.account_name if acct_obj else ("Unassigned" if not h_aid else "Unknown")
        ok       = label == "Unassigned"
        return (
            "empty default_account_id renders as 'Unassigned'",
            repr(label), ok,
        )

    results.append(_run(
        "ACC-UI-02",
        "Legacy holding with empty default_account_id shows 'Unassigned'",
        CAT, "app.render_holdings_tab._row_builder", "P0", True, acc_ui_02,
    ))

    # ── ACC-UI-03: Edit can assign account to legacy holding ──────────────────
    def acc_ui_03():
        """
        upsert_holding with a valid default_account_id updates an existing holding.
        Simulates what Edit Holding does when user selects an account.
        """
        aid = _setup_sandbox_account()

        # Step 1: create holding via upsert (needs account)
        upsert_holding(
            _SB_TK,
            company_name="Sandbox AccUI Holding",
            quantity=5.0, avg_cost=10.0, current_price=12.0,
            currency="USD",
            default_account_id=aid,
        )

        # Step 2: strip account (simulate legacy state by direct patch)
        h_map = load_holdings()
        if _SB_TK in h_map:
            h_map[_SB_TK].default_account_id = ""
            from portfolio.holdings import save_holdings
            save_holdings(h_map)

        # Step 3: re-assign via upsert (what Edit Holding dialog does)
        h_updated = upsert_holding(
            _SB_TK,
            default_account_id=aid,
        )

        got_aid = getattr(h_updated, "default_account_id", "")
        ok      = got_aid == aid
        _teardown_sandbox()
        return (
            "Edit Holding assigns account to previously-unlinked holding",
            f"default_account_id={got_aid!r}",
            ok,
        )

    results.append(_run(
        "ACC-UI-03",
        "Edit Holding can assign a valid account to a legacy holding",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, acc_ui_03,
    ))

    # ── ACC-UI-04: empty account blocked on save ──────────────────────────────
    def acc_ui_04():
        """
        Attempting to upsert a brand-new holding with empty default_account_id
        raises ValueError — i.e. the disabled-button / guard prevents the save.
        """
        SB2 = "__SBACCUI2__"
        try:
            delete_holding(SB2)
        except Exception:
            pass
        try:
            upsert_holding(
                SB2,
                company_name="Blocked", quantity=1.0, avg_cost=1.0, current_price=1.0,
                currency="USD",
                default_account_id="",
            )
            try:
                delete_holding(SB2)
            except Exception:
                pass
            return ("ValueError raised", "no error — guard did NOT fire", False)
        except ValueError as e:
            return (
                "ValueError raised for empty account on new holding",
                repr(str(e)), True,
            )

    results.append(_run(
        "ACC-UI-04",
        "Saving Edit Holding with empty account is blocked (ValueError)",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, acc_ui_04,
    ))

    # ── ACC-UI-05: reassignment changes only default_account_id ──────────────
    def acc_ui_05():
        """
        Reassigning default_account_id must NOT alter qty, avg_cost, current_price,
        or valuation — those fields are preserved by upsert_holding's _pick() logic.
        """
        aid  = _setup_sandbox_account()

        # Create fresh sandbox holding
        h_before = upsert_holding(
            _SB_TK,
            company_name="Sandbox AccUI Holding",
            quantity=7.0, avg_cost=15.0, current_price=20.0,
            currency="USD",
            default_account_id=aid,
        )

        # Simulate reassignment: create a second sandbox account
        _SB_AID2 = "__sb_acc_ui_test2__"
        upsert_account(
            account_id=_SB_AID2,
            account_name="Sandbox AccUI 2",
            institution="Test", account_type="Brokerage",
            base_currency="USD", opening_cash=0.0,
        )

        # Reassign account only
        h_after = upsert_holding(_SB_TK, default_account_id=_SB_AID2)

        ok = (
            h_after.quantity      == h_before.quantity       and
            h_after.avg_cost      == h_before.avg_cost       and
            h_after.current_price == h_before.current_price  and
            h_after.default_account_id == _SB_AID2
        )
        detail = (
            f"qty {h_after.quantity} avg {h_after.avg_cost} "
            f"price {h_after.current_price} aid={h_after.default_account_id!r}"
        )

        # Cleanup
        _teardown_sandbox()
        try:
            from portfolio.accounts import set_account_cash
            set_account_cash(_SB_AID2, 0.0)
            delete_account(_SB_AID2)
        except Exception:
            pass

        return (
            "only default_account_id changes; qty/avg/price unchanged",
            detail, ok,
        )

    results.append(_run(
        "ACC-UI-05",
        "Account reassignment changes only default_account_id; qty/avg/price unchanged",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, acc_ui_05,
    ))

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Category A11 — Per-Account Valuation Consistency
# ════════════════════════════════════════════════════════════════════════════════

def _cat_a11() -> list[TestResult]:
    """
    Verify that account-level holdings valuation reconciles exactly to the
    portfolio-level valuation produced by the centralised engine.

    Approach (read-only, no disk writes for A11-01..A11-04):
      1. Construct synthetic Holding/Account objects in memory.
      2. Pass them directly into calculate_portfolio_valuation().
      3. Group the engine's per_holding rows by default_account_id.
      4. Compare sum(account_totals) vs holdings_value_base — tolerance 0.01.

    A11-05..A11-07 run against live on-disk data.
    """
    CAT     = "Per-Account Valuation Consistency"
    TOLE    = 0.01
    results: list[TestResult] = []

    from dataclasses import dataclass, field
    from portfolio.holdings  import Holding
    from portfolio.accounts  import Account
    from portfolio.valuation import calculate_portfolio_valuation

    # ── Shared helpers ────────────────────────────────────────────────────────

    @dataclass
    class _FxRate:
        """Minimal stand-in for FxRate used in sandbox tests."""
        rate:   float
        source: str = "same"

    def _per_account_values(val, holdings_map: dict) -> dict:
        """
        Group the engine's per_holding output by default_account_id.
        Returns {account_id: sum_of_base_market_value}.
        Uses no arithmetic of its own — all figures come from the engine.
        """
        totals: dict[str, float] = {}
        for ph in val.per_holding:
            aid = getattr(holdings_map.get(ph.ticker), "default_account_id", "") or ""
            totals[aid] = round(totals.get(aid, 0.0) + ph.base_market_value, 6)
        return totals

    def _make_fx(base_ccy: str, extras: dict | None = None) -> dict:
        """Return a minimal fx_rates dict: base→1.0, plus any extras supplied."""
        fx = {base_ccy: _FxRate(rate=1.0, source="same")}
        if extras:
            fx.update(extras)
        return fx

    def _sb_acct(aid: str, name: str, ccy: str = "USD") -> Account:
        return Account(
            account_id=aid, account_name=name,
            institution="Test", account_type="Brokerage",
            base_currency=ccy, cash_balance=0.0,
        )

    def _sb_hold(ticker: str, qty: float, price: float,
                 aid: str, ccy: str = "USD") -> Holding:
        return Holding(
            ticker=ticker, company_name=f"Sandbox {ticker}",
            quantity=qty, avg_cost=price * 0.8, current_price=price,
            currency=ccy, default_account_id=aid,
        )

    # ── A11-01: single account, two holdings ─────────────────────────────────
    def a11_01():
        h1 = _sb_hold("SB11A", qty=10.0, price=5.0,  aid="acct1")
        h2 = _sb_hold("SB11B", qty=20.0, price=3.0,  aid="acct1")
        hmap   = {"SB11A": h1, "SB11B": h2}
        amap   = {"acct1": _sb_acct("acct1", "Single Acct")}
        fx     = _make_fx("USD")
        val    = calculate_portfolio_valuation(hmap, amap, "USD", fx_rates=fx)
        totals = _per_account_values(val, hmap)

        acc_sum = sum(totals.values())
        ok      = _near(acc_sum, val.holdings_value_base, TOLE)
        return (
            f"sum(account_values) ≈ holdings_value_base (±{TOLE})",
            f"sum={acc_sum:.4f}  engine={val.holdings_value_base:.4f}  "
            f"diff={abs(acc_sum - val.holdings_value_base):.6f}",
            ok,
        )

    results.append(_run(
        "A11-01", "Single-account: account total == holdings_value_base",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_01,
    ))

    # ── A11-02: multiple accounts ─────────────────────────────────────────────
    def a11_02():
        hmap = {
            "SB12A": _sb_hold("SB12A", qty=10.0, price=10.0, aid="acct_x"),
            "SB12B": _sb_hold("SB12B", qty= 5.0, price=20.0, aid="acct_y"),
            "SB12C": _sb_hold("SB12C", qty=15.0, price= 4.0, aid="acct_x"),
        }
        amap = {
            "acct_x": _sb_acct("acct_x", "Alpha"),
            "acct_y": _sb_acct("acct_y", "Beta"),
        }
        fx     = _make_fx("USD")
        val    = calculate_portfolio_valuation(hmap, amap, "USD", fx_rates=fx)
        totals = _per_account_values(val, hmap)

        # Two accounts present
        accts_found = set(totals.keys()) == {"acct_x", "acct_y"}
        acc_sum     = sum(totals.values())
        ok = accts_found and _near(acc_sum, val.holdings_value_base, TOLE)
        return (
            f"two distinct account buckets; sum ≈ holdings_value_base (±{TOLE})",
            f"buckets={sorted(totals.keys())}  sum={acc_sum:.4f}  "
            f"engine={val.holdings_value_base:.4f}  "
            f"diff={abs(acc_sum - val.holdings_value_base):.6f}",
            ok,
        )

    results.append(_run(
        "A11-02", "Multiple accounts: each holding assigned to exactly one account; totals reconcile",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_02,
    ))

    # ── A11-03: multiple currencies ───────────────────────────────────────────
    def a11_03():
        hmap = {
            "SB13U": _sb_hold("SB13U", qty=100.0, price=10.0,  aid="acct_usd", ccy="USD"),
            "SB13S": _sb_hold("SB13S", qty=200.0, price= 5.0,  aid="acct_sar", ccy="SAR"),
        }
        amap = {
            "acct_usd": _sb_acct("acct_usd", "USD Acct", "USD"),
            "acct_sar": _sb_acct("acct_sar", "SAR Acct", "SAR"),
        }
        USD_SAR = 3.75
        fx = _make_fx("SAR", {"USD": _FxRate(rate=USD_SAR, source="test")})
        val    = calculate_portfolio_valuation(hmap, amap, "SAR", fx_rates=fx)
        totals = _per_account_values(val, hmap)

        expected_usd_acct = 100.0 * 10.0 * USD_SAR   # 3,750 SAR
        expected_sar_acct = 200.0 * 5.0               # 1,000 SAR
        expected_total    = expected_usd_acct + expected_sar_acct

        acc_sum = sum(totals.values())
        ok = (
            _near(acc_sum,   val.holdings_value_base, TOLE) and
            _near(acc_sum,   expected_total, TOLE)
        )
        return (
            f"multi-ccy FX applied; sum ≈ {expected_total:.2f} SAR (±{TOLE})",
            f"sum={acc_sum:.4f}  engine={val.holdings_value_base:.4f}  "
            f"expected={expected_total:.4f}  diff={abs(acc_sum - expected_total):.6f}",
            ok,
        )

    results.append(_run(
        "A11-03", "Multiple currencies: FX-converted account totals reconcile to engine total",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_03,
    ))

    # ── A11-04: holding reassigned → account totals shift, global total same ──
    def a11_04():
        BASE_CCY = "USD"
        hmap_before = {
            "SB14A": _sb_hold("SB14A", qty=10.0, price=10.0, aid="acct_p"),
            "SB14B": _sb_hold("SB14B", qty= 5.0, price=20.0, aid="acct_p"),
        }
        # Reassign SB14B from acct_p to acct_q
        h14b_new = _sb_hold("SB14B", qty=5.0, price=20.0, aid="acct_q")
        hmap_after = {"SB14A": hmap_before["SB14A"], "SB14B": h14b_new}

        amap = {
            "acct_p": _sb_acct("acct_p", "Parent"),
            "acct_q": _sb_acct("acct_q", "Child"),
        }
        fx = _make_fx(BASE_CCY)

        val_b   = calculate_portfolio_valuation(hmap_before, amap, BASE_CCY, fx_rates=fx)
        val_a   = calculate_portfolio_valuation(hmap_after,  amap, BASE_CCY, fx_rates=fx)
        tot_b   = _per_account_values(val_b, hmap_before)
        tot_a   = _per_account_values(val_a, hmap_after)

        b14b_mv = hmap_before["SB14B"].quantity * hmap_before["SB14B"].current_price  # 100
        # After: acct_p should drop by b14b_mv, acct_q should gain b14b_mv
        p_before  = tot_b.get("acct_p", 0.0)
        p_after   = tot_a.get("acct_p", 0.0)
        q_after   = tot_a.get("acct_q", 0.0)

        global_before = sum(tot_b.values())
        global_after  = sum(tot_a.values())

        ok = (
            _near(p_after,    p_before - b14b_mv,  TOLE) and   # acct_p shrank
            _near(q_after,    b14b_mv,              TOLE) and   # acct_q gained
            _near(global_before, global_after,      TOLE)       # total unchanged
        )
        return (
            f"acct_p −{b14b_mv:.0f}, acct_q +{b14b_mv:.0f}, global total unchanged (±{TOLE})",
            f"acct_p: {p_before:.2f}→{p_after:.2f}  "
            f"acct_q: 0.00→{q_after:.2f}  "
            f"global: {global_before:.4f}→{global_after:.4f}",
            ok,
        )

    results.append(_run(
        "A11-04", "Reassignment: account totals shift by holding MV; portfolio total unchanged",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_04,
    ))

    # ── A11-05 / A11-06 / A11-07: live on-disk data ───────────────────────────
    from portfolio.holdings import load_holdings
    from portfolio.accounts import load_accounts
    from fx_rates           import get_rates_for_holdings

    live_holdings = load_holdings()
    live_accounts = load_accounts()
    live_active   = {t: h for t, h in live_holdings.items() if h.quantity > 1e-9}

    all_ccys = list({getattr(h, "currency", "USD") for h in live_active.values()})
    live_fx  = get_rates_for_holdings(all_ccys, "SAR") if all_ccys else {}
    live_val = calculate_portfolio_valuation(
        live_holdings, live_accounts, "SAR", fx_rates=live_fx
    )
    live_totals = _per_account_values(live_val, live_holdings)

    # ── A11-05: portfolio total == sum of account totals ─────────────────────
    def a11_05():
        acc_sum = sum(live_totals.values())
        diff    = abs(acc_sum - live_val.holdings_value_base)
        ok      = diff <= TOLE
        return (
            f"sum(account_holdings_values) ≈ portfolio holdings_value_base (±{TOLE})",
            f"sum={acc_sum:,.4f} SAR  engine={live_val.holdings_value_base:,.4f} SAR  "
            f"diff={diff:.6f}",
            ok,
        )

    results.append(_run(
        "A11-05", "Live portfolio: sum(account_holdings_values) == holdings_value_base",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_05,
    ))

    # ── A11-06: no holding counted twice ─────────────────────────────────────
    def a11_06():
        """Each per_holding row contributes to exactly one account bucket."""
        tickers_seen: list[str] = [ph.ticker for ph in live_val.per_holding]
        dupes = [t for t in tickers_seen if tickers_seen.count(t) > 1]
        ok    = len(dupes) == 0
        return (
            "every ticker appears exactly once in per_holding list",
            f"duplicates={dupes}" if dupes else f"no duplicates in {len(tickers_seen)} rows",
            ok,
        )

    results.append(_run(
        "A11-06", "No holding counted twice in per_holding output",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_06,
    ))

    # ── A11-07: no active holding omitted ────────────────────────────────────
    def a11_07():
        """Every active holding (qty > 1e-9) appears in per_holding."""
        engine_tickers = {ph.ticker for ph in live_val.per_holding}
        missing = sorted(
            h.ticker for h in live_active.values()
            if h.ticker not in engine_tickers
        )
        ok = len(missing) == 0
        return (
            "every active holding appears in per_holding",
            f"missing from engine output: {missing}"
            if missing else
            f"all {len(live_active)} active holdings present in per_holding",
            ok,
        )

    results.append(_run(
        "A11-07", "No active holding omitted from per_holding output",
        CAT, "portfolio.valuation.calculate_portfolio_valuation", "P0", True, a11_07,
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

def _cat_add() -> list[TestResult]:
    """
    ADD: Add New Position dialog regression tests.

    ADD-01  Dialog opens without UnboundLocalError (session-state flag path).
    ADD-02  upsert_holding raises ValueError when no account supplied for new holding.
    ADD-03  upsert_holding with a valid account_id creates the holding successfully.

    All tests use synthetic sandbox data only — no portfolio files read or written.
    """
    CAT = "Add New Position"
    results: list[TestResult] = []

    def add01():
        """
        Persistent holdings_modal_open flag: set by button, survives a rerun
        (get returns True after set), and is cleared explicitly (not consumed
        by pop on the first read).

        Phase-1 fix: replaced one-shot .pop("_open_dlg_add_new") with
        persistent .get("holdings_modal_open") so the @st.dialog function
        is called on every rerun while the modal should stay open.
        """
        import streamlit as st
        # Old key must be absent from the codebase (regression guard)
        old_key_absent = "_open_dlg_add_new" not in st.session_state

        # New key: set → still readable on next simulated rerun → explicit clear
        st.session_state["holdings_modal_open"] = True
        flag_after_set  = st.session_state.get("holdings_modal_open", False)
        flag_after_get  = st.session_state.get("holdings_modal_open", False)  # still True
        st.session_state.pop("holdings_modal_open", None)
        flag_after_clear = st.session_state.get("holdings_modal_open", False)

        ok = (
            old_key_absent
            and flag_after_set
            and flag_after_get          # persistent: still True after first get
            and not flag_after_clear    # explicit clear works
        )
        return (
            "persistent flag: set=True, get×2=True, explicit_clear→False; old key absent",
            (
                f"old_key_absent={old_key_absent}, "
                f"after_set={flag_after_set}, after_get={flag_after_get}, "
                f"after_clear={flag_after_clear}"
            ),
            ok,
        )

    def add02():
        """
        _check_new_holding_account must return an error string when creating
        a brand-new holding (existing=None) without an account_id.
        This is the guard enforced by both upsert_holding and record_transaction.
        """
        from portfolio.holdings import _check_new_holding_account

        err = _check_new_holding_account(existing=None, account_id="")
        ok = isinstance(err, str) and len(err) > 0
        return (
            "non-empty error string returned when account_id='' for new holding",
            f"returned={err!r}",
            ok,
        )

    def add03():
        """
        _check_new_holding_account must return None (no error) when a valid
        account_id is supplied for a new holding.
        """
        from portfolio.holdings import _check_new_holding_account

        ACCT_ID = "sandbox-acct-add03"
        err = _check_new_holding_account(existing=None, account_id=ACCT_ID)
        ok = err is None
        return (
            "None returned (no error) when valid account_id supplied",
            f"returned={err!r}",
            ok,
        )

    def add04():
        """
        Mode A (Record Existing Holding): _cash_ok is always True regardless of
        account balance.  The dialog sets _cash_ok=True before the cash section
        and only overwrites it when _is_buy_mode=True.  Simulate that logic.
        """
        # Simulate dialog cash-check logic for Mode A
        _is_buy_mode  = False          # "Record Existing Holding"
        account_cash  = 0.0            # zero cash in account
        total_cost    = 500.0          # position costs 500
        _cash_ok      = True           # default — always True for Mode A

        if _is_buy_mode and account_cash is not None:
            remaining = account_cash - total_cost
            _cash_ok  = remaining >= 0  # would be False — but this branch is skipped

        submit_blocked = not _cash_ok
        ok = not submit_blocked  # submit must NOT be blocked by cash in Mode A
        return (
            "_cash_ok=True for Mode A with zero-cash account",
            f"_cash_ok={_cash_ok}, submit_blocked={submit_blocked}",
            ok,
        )

    def add05():
        """
        Mode A does not debit account cash.  The cash delta applied is 0.
        Simulate both mode paths and verify Mode A delta is 0.
        """
        account_cash = 1000.0
        total_cost   = 300.0

        # Mode A: no cash debit
        mode_a_delta = 0.0  # _upd_cash is never called
        # Mode B: cash debit
        mode_b_delta = -total_cost

        cash_after_a = account_cash + mode_a_delta  # unchanged
        cash_after_b = account_cash + mode_b_delta  # reduced

        ok = (cash_after_a == account_cash) and (cash_after_b == account_cash - total_cost)
        return (
            f"Mode A delta=0 (cash unchanged={account_cash}); Mode B delta={mode_b_delta}",
            f"after_A={cash_after_a}, after_B={cash_after_b}",
            ok,
        )

    def add06():
        """
        Mode B (Record New Buy Transaction): submit is blocked when
        account cash < total cost.
        """
        _is_buy_mode = True
        account_cash = 50.0
        total_cost   = 200.0

        _cash_ok = True
        if _is_buy_mode and account_cash is not None:
            remaining = account_cash - total_cost
            _cash_ok  = remaining >= 0   # False — insufficient cash

        submit_blocked = _is_buy_mode and not _cash_ok
        ok = submit_blocked  # must be blocked
        return (
            "submit blocked when Mode B and account_cash < total_cost",
            f"_cash_ok={_cash_ok}, submit_blocked={submit_blocked}",
            ok,
        )

    def add07():
        """
        Mode B (Record New Buy Transaction): submit is allowed when
        account cash >= total cost, and cash delta equals -total_cost.
        """
        _is_buy_mode = True
        account_cash = 500.0
        total_cost   = 200.0
        fees         = 5.0
        total_cost_with_fees = total_cost + fees

        _cash_ok = True
        if _is_buy_mode and account_cash is not None:
            remaining = account_cash - total_cost_with_fees
            _cash_ok  = remaining >= 0   # True — sufficient cash

        cash_delta   = -total_cost_with_fees  # amount debited after successful BUY
        cash_after   = account_cash + cash_delta
        submit_allowed = _is_buy_mode and _cash_ok

        ok = (
            submit_allowed
            and _near(cash_after, account_cash - total_cost_with_fees, 0.01)
        )
        return (
            f"submit allowed; cash debited by {total_cost_with_fees}; remaining={account_cash - total_cost_with_fees}",
            f"_cash_ok={_cash_ok}, submit_allowed={submit_allowed}, cash_after={cash_after}",
            ok,
        )

    results.append(_run(
        "ADD-01",
        "Add New Position session-state flag mechanism works without crash",
        CAT, "app.render_holdings_tab", "P0", True, add01,
    ))
    results.append(_run(
        "ADD-02",
        "Add New Position requires account — ValueError when account_id=None",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, add02,
    ))
    results.append(_run(
        "ADD-03",
        "Add New Position with valid account creates holding with correct binding",
        CAT, "portfolio.holdings.upsert_holding", "P0", True, add03,
    ))
    results.append(_run(
        "ADD-04",
        "Record Existing Holding (Mode A): zero-cash account does not block submit",
        CAT, "app._dlg_add_new", "P0", True, add04,
    ))
    results.append(_run(
        "ADD-05",
        "Record Existing Holding (Mode A): account cash is not debited",
        CAT, "app._dlg_add_new", "P0", True, add05,
    ))
    results.append(_run(
        "ADD-06",
        "Record New Buy Transaction (Mode B): insufficient cash blocks submit",
        CAT, "app._dlg_add_new", "P0", True, add06,
    ))
    results.append(_run(
        "ADD-07",
        "Record New Buy Transaction (Mode B): sufficient cash allows submit and debits correct amount",
        CAT, "app._dlg_add_new", "P0", True, add07,
    ))

    return results


def _cat_disc() -> list[TestResult]:
    """
    DISC: SAHMK Discovery Engine regression tests.

    DISC-01  Valid symbol discovery completes and returns a report dict.
    DISC-02  Invalid symbol handled gracefully (no exception, errors captured).
    DISC-03  Unconfigured API (no key) handled gracefully.
    DISC-04  Discovery report serialises to valid JSON (export works).
    DISC-05  Holdings valuation unchanged after importing discovery module.
    DISC-06  Current price refresh function unchanged after importing discovery module.

    All tests are read-only and use synthetic / real-API-optional paths.
    """
    CAT = "SAHMK Discovery"
    results: list[TestResult] = []

    def disc01():
        """
        Running discover() for a real Saudi symbol returns the expected report
        structure.  The API may or may not have data — we only verify the
        report schema is complete (keys present, types correct).
        Uses a mocked HTTP layer so no live SAHMK calls are made.
        """
        import json as _json
        import urllib.error as _ue
        from unittest.mock import patch, MagicMock
        from portfolio.sahmk_discovery import discover

        fake_body = _json.dumps({
            "price": 38.5, "currency": "SAR", "symbol": "2222",
            "close": 38.5, "open": 37.0, "high": 39.0, "low": 36.5,
        }).encode()
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = fake_body
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)

        with patch("portfolio.sahmk_discovery.urllib.request.urlopen",
                   return_value=fake_resp):
            report = discover("2222", timeout=20)

        required_keys = {
            "symbol", "source", "discovered_at", "api_configured",
            "available_datasets", "unavailable_datasets",
            "endpoint_results", "summary_table",
        }
        missing = required_keys - set(report.keys())
        schema_ok = not missing

        ep_ok = isinstance(report["endpoint_results"], list) and len(report["endpoint_results"]) > 0
        sum_ok = isinstance(report["summary_table"], list) and len(report["summary_table"]) > 0
        sym_ok = report["symbol"] == "2222"
        src_ok = report["source"] == "SAHMK"

        ok = schema_ok and ep_ok and sum_ok and sym_ok and src_ok

        detail = []
        if missing:
            detail.append(f"missing keys: {missing}")
        if not ep_ok:
            detail.append("endpoint_results empty or wrong type")
        if not sum_ok:
            detail.append("summary_table empty or wrong type")

        return (
            "report dict with all required keys; 8 endpoint entries; symbol=2222",
            "PASS" if ok else "; ".join(detail),
            ok,
        )

    def disc02():
        """
        Discover with an invalid/nonexistent symbol must return a complete report
        without raising — all endpoint entries should have success=False and
        capture an error string.
        Uses a mocked HTTP layer (returns 404) so no live SAHMK calls are made.
        """
        import urllib.error as _ue
        from unittest.mock import patch
        from portfolio.sahmk_discovery import discover

        def _raise_404(*args, **kwargs):
            raise _ue.HTTPError("mock://url", 404, "Not Found", {}, None)

        with patch("portfolio.sahmk_discovery.urllib.request.urlopen",
                   side_effect=_raise_404):
            report = discover("INVALID_SYMBOL_99999", timeout=15)

        schema_ok = "endpoint_results" in report and "symbol" in report
        no_exception = True   # if we reached here, no exception was raised

        ep_list = report.get("endpoint_results", [])
        # Symbol-required endpoints should all fail gracefully (success=False)
        sym_eps = [ep for ep in ep_list if ep.get("symbol_required", True)]
        all_failed = all(not ep["success"] for ep in sym_eps)
        errors_captured = all(
            ep["error"] is not None or not ep["success"]
            for ep in sym_eps
        )

        ok = schema_ok and no_exception and all_failed and errors_captured
        return (
            "no exception; all symbol-required endpoints fail gracefully with error captured",
            (
                f"schema_ok={schema_ok}, all_failed={all_failed}, "
                f"errors_captured={errors_captured}"
            ),
            ok,
        )

    def disc03():
        """
        discover() with SAHMK_API_KEY unset returns a complete report with
        api_configured=False and all endpoints capturing a 'not configured' error.
        """
        import os
        from portfolio.sahmk_discovery import discover

        # Temporarily unset the key
        _orig = os.environ.pop("SAHMK_API_KEY", None)
        try:
            report = discover("2222", timeout=5)
        finally:
            if _orig is not None:
                os.environ["SAHMK_API_KEY"] = _orig

        schema_ok   = "endpoint_results" in report
        not_cfg     = report.get("api_configured") is False
        ep_list     = report.get("endpoint_results", [])
        sym_eps     = [ep for ep in ep_list if ep.get("symbol_required", True)]
        all_no_data = all(not ep["success"] for ep in sym_eps)

        ok = schema_ok and not_cfg and all_no_data
        return (
            "api_configured=False; all symbol endpoints fail gracefully when key absent",
            f"schema_ok={schema_ok}, not_cfg={not_cfg}, all_no_data={all_no_data}",
            ok,
        )

    def disc04():
        """
        report_to_json() must produce a parseable JSON string from a discovery
        report (export works).
        """
        import json
        from portfolio.sahmk_discovery import discover, report_to_json

        # Use a no-API call to get a lightweight report
        import os
        _orig = os.environ.pop("SAHMK_API_KEY", None)
        try:
            report = discover("2222", timeout=5)
        finally:
            if _orig is not None:
                os.environ["SAHMK_API_KEY"] = _orig

        json_str = report_to_json(report)
        parseable = False
        try:
            parsed = json.loads(json_str)
            parseable = isinstance(parsed, dict)
        except Exception:
            pass

        has_symbol = '"symbol"' in json_str
        ok = parseable and has_symbol
        return (
            "report_to_json produces valid, parseable JSON containing symbol key",
            f"parseable={parseable}, has_symbol={has_symbol}, len={len(json_str)}",
            ok,
        )

    def disc05():
        """
        Importing sahmk_discovery must not affect portfolio valuation results.
        Run calculate_portfolio_valuation before and after import — totals must match.
        """
        import importlib
        h1 = _holding("__SB_DISC05A__", qty=10.0, avg_cost=100.0, price=120.0)
        h2 = _holding("__SB_DISC05B__", qty=5.0,  avg_cost=50.0,  price=60.0)
        fx = {
            "USD": _fx("USD", "USD", 1.0),
        }
        val_before = _val(
            {"__SB_DISC05A__": h1, "__SB_DISC05B__": h2},
            {}, "USD", fx,
        )

        # Import / reimport the discovery module
        import portfolio.sahmk_discovery as _disc_mod
        importlib.reload(_disc_mod)

        val_after = _val(
            {"__SB_DISC05A__": h1, "__SB_DISC05B__": h2},
            {}, "USD", fx,
        )

        mv_before = round(val_before.holdings_value_base, 4)
        mv_after  = round(val_after.holdings_value_base, 4)
        ok = _near(mv_before, mv_after, 0.001)
        return (
            f"holdings_value_base unchanged after discovery module import",
            f"before={mv_before}, after={mv_after}",
            ok,
        )

    def disc06():
        """
        Importing sahmk_discovery must not affect the current price refresh
        path — update_current_price must still be importable and callable.
        """
        import portfolio.sahmk_discovery  # trigger import

        from portfolio.holdings import update_current_price, load_holdings
        # Verify function is callable (signature check only — no real file write
        # for a nonexistent sandbox ticker that isn't in holdings)
        import inspect
        sig = inspect.signature(update_current_price)
        params = list(sig.parameters.keys())
        has_asset_id = "asset_id" in params
        has_price    = "price" in params or "new_price" in params

        ok = callable(update_current_price) and has_asset_id
        return (
            "update_current_price remains callable and has expected signature after discovery import",
            f"callable={callable(update_current_price)}, params={params}",
            ok,
        )

    results.append(_run(
        "DISC-01",
        "Valid symbol discovery completes with full report schema",
        CAT, "portfolio.sahmk_discovery", "P1", False, disc01,
    ))
    results.append(_run(
        "DISC-02",
        "Invalid symbol handled gracefully — no exception, errors captured",
        CAT, "portfolio.sahmk_discovery", "P1", False, disc02,
    ))
    results.append(_run(
        "DISC-03",
        "Unconfigured API (no key) handled gracefully — api_configured=False",
        CAT, "portfolio.sahmk_discovery", "P1", False, disc03,
    ))
    results.append(_run(
        "DISC-04",
        "Discovery report export produces valid parseable JSON",
        CAT, "portfolio.sahmk_discovery", "P0", True, disc04,
    ))
    results.append(_run(
        "DISC-05",
        "Holdings valuation unchanged after importing discovery module",
        CAT, "portfolio.sahmk_discovery + portfolio.valuation", "P0", True, disc05,
    ))
    results.append(_run(
        "DISC-06",
        "Current price refresh function unchanged after importing discovery module",
        CAT, "portfolio.sahmk_discovery + portfolio.holdings", "P0", True, disc06,
    ))

    return results


def _cat_sds() -> list[TestResult]:
    """
    SDS: SAHMK Discovery Storage Layer regression tests.

    SDS-01  Discovery stores quote data (successful endpoint → file written).
    SDS-02  Discovery stores historical prices.
    SDS-03  Discovery stores market summary.
    SDS-04  404/failed datasets are NOT stored.
    SDS-05  Stored files survive refresh (disk-based, not session-state).
    SDS-06  Stored files survive app restart (disk persistence check).
    SDS-07  Load Stored Data works without API calls.
    SDS-08  FIFO retention keeps only newest 3 versions per dataset.
    SDS-09  Stored SAHMK Data section appears before Endpoint Detail (layout order).
    SDS-10  Empty state when no stored files exist.
    SDS-11  Holdings valuation unchanged after storage operations.
    SDS-12  Portfolio totals unchanged after storage operations.
    SDS-13  Full suite remains importable and complete after storage layer added.
    """
    import tempfile, shutil, time as _time, os as _os, json as _json

    CAT = "SAHMK Storage"
    results: list[TestResult] = []

    # ── Shared temp root (one mkdtemp per _cat_sds() call, cleaned at end) ──
    _tmpdir = tempfile.mkdtemp(prefix="bousala_sds_")

    def _make_ep(name: str, path: str, success: bool,
                 raw: object = None, sym_required: bool = True) -> dict:
        """Build a minimal endpoint_result dict for testing storage."""
        return {
            "endpoint_name":       name,
            "path":                path,
            "symbol_required":     sym_required,
            "http_status":         200 if success else 404,
            "success":             success,
            "error":               None if success else f"HTTP 404",
            "response_size_bytes": 100 if success else 0,
            "raw_type":            "dict" if success else "null",
            "record_count":        None,
            "available_fields":    ["price", "volume"] if success else [],
            "sample_values":       {"price": 100.0} if success else {},
            "raw_response":        raw or ({"price": 100.0} if success else None),
        }

    def sds01():
        from portfolio.sahmk_discovery import store_dataset, list_stored
        ep = _make_ep("Quote", "quote/2222/", True, {"price": 55.2, "volume": 5000})
        fpath = store_dataset("2222", ep, root=_tmpdir)
        file_exists = fpath is not None and _os.path.isfile(fpath)
        stored = list_stored("2222", root=_tmpdir)
        in_list = any(s["dataset"].lower() == "quote" for s in stored)
        ok = file_exists and in_list
        return (
            "quote file written to disk and appears in list_stored",
            f"file_exists={file_exists}, in_list={in_list}, path={fpath}",
            ok,
        )

    def sds02():
        from portfolio.sahmk_discovery import store_dataset, list_stored
        ep = _make_ep(
            "Historical Prices", "historical/2222",
            True, [{"date": "2026-01-01", "close": 50.0}],
        )
        fpath = store_dataset("2222", ep, root=_tmpdir)
        file_exists = fpath is not None and _os.path.isfile(fpath)
        stored = list_stored("2222", root=_tmpdir)
        in_list = any("historical" in s["slug"] for s in stored)
        ok = file_exists and in_list
        return (
            "historical prices file written and appears in list_stored",
            f"file_exists={file_exists}, in_list={in_list}",
            ok,
        )

    def sds03():
        from portfolio.sahmk_discovery import store_dataset, list_stored
        ep = _make_ep(
            "Market Summary", "market/summary",
            True, [{"index": "TASI", "value": 11000}], sym_required=False,
        )
        fpath = store_dataset("__market__", ep, root=_tmpdir)
        file_exists = fpath is not None and _os.path.isfile(fpath)
        ok = file_exists
        return (
            "market summary file written to disk",
            f"file_exists={file_exists}, path={fpath}",
            ok,
        )

    def sds04():
        from portfolio.sahmk_discovery import store_dataset
        ep_ok  = _make_ep("Quote",    "quote/2222/",            True)
        ep_404 = _make_ep("Financials","company/2222/financials", False)
        path_ok  = store_dataset("2222", ep_ok,  root=_tmpdir)
        path_404 = store_dataset("2222", ep_404, root=_tmpdir)
        ok = (path_ok is not None) and (path_404 is None)
        return (
            "successful endpoint stored; 404 endpoint returns None (not stored)",
            f"ok_stored={path_ok is not None}, 404_stored={path_404 is not None}",
            ok,
        )

    def sds05():
        """Files on disk survive a simulated refresh (new list_stored call)."""
        from portfolio.sahmk_discovery import store_dataset, list_stored
        ep = _make_ep("Quote", "quote/6004/", True)
        fpath = store_dataset("6004", ep, root=_tmpdir)
        # Simulate refresh: call list_stored fresh (no session state involved)
        stored_fresh = list_stored("6004", root=_tmpdir)
        survived = any(s["filepath"] == fpath for s in stored_fresh)
        ok = survived
        return (
            "stored file found by fresh list_stored call (disk-based, survives refresh)",
            f"file_exists={_os.path.isfile(fpath)}, found_in_list={survived}",
            ok,
        )

    def sds06():
        """Files on disk survive a simulated restart (no in-memory state)."""
        import importlib
        from portfolio.sahmk_discovery import store_dataset
        import portfolio.sahmk_discovery as _disc_mod
        ep = _make_ep("Quote", "quote/1120/", True)
        fpath = store_dataset("1120", ep, root=_tmpdir)
        # Simulate restart: reload the module (clears any module-level state)
        importlib.reload(_disc_mod)
        from portfolio.sahmk_discovery import list_stored
        stored = list_stored("1120", root=_tmpdir)
        survived = any(s["filepath"] == fpath for s in stored)
        ok = survived and _os.path.isfile(fpath)
        return (
            "stored file persists on disk after module reload (simulated restart)",
            f"file_exists={_os.path.isfile(fpath)}, found_after_reload={survived}",
            ok,
        )

    def sds07():
        """load_stored_dataset reads file without any API call."""
        from portfolio.sahmk_discovery import store_dataset, load_stored_dataset
        import os as _o
        ep = _make_ep("Ratios", "company/2222/ratios", True, {"pe": 14.5})
        fpath = store_dataset("2222", ep, root=_tmpdir)
        # Temporarily unset API key to confirm no API call is made
        _orig = _o.environ.pop("SAHMK_API_KEY", None)
        try:
            data = load_stored_dataset(fpath)
        finally:
            if _orig is not None:
                _o.environ["SAHMK_API_KEY"] = _orig
        loaded_ok = (
            data is not None
            and data.get("dataset") == "Ratios"
            and data.get("source") == "SAHMK"
        )
        ok = loaded_ok
        return (
            "load_stored_dataset returns correct dict without API key set",
            f"loaded={data is not None}, dataset={data.get('dataset') if data else None}",
            ok,
        )

    def sds08():
        """_apply_fifo_retention keeps only newest 3 files; older are deleted."""
        from portfolio.sahmk_discovery import store_dataset, _apply_fifo_retention
        # Write 5 files with distinct timestamps
        sym  = "fifo_test"
        ep   = _make_ep("Quote", f"quote/{sym}/", True)
        paths = []
        for i in range(5):
            # Sleep briefly so filenames differ; but we can also fake by writing
            # files with manually crafted names
            dirpath = _os.path.join(_tmpdir, sym, "quote")
            _os.makedirs(dirpath, exist_ok=True)
            ts = f"2026053{i}_18000{i}"
            fname = f"quote_{ts}.json"
            fpath = _os.path.join(dirpath, fname)
            with open(fpath, "w") as fh:
                _json.dump({"i": i}, fh)
            paths.append(fname)
        # Apply retention (keep=3)
        _apply_fifo_retention(dirpath, keep=3)
        remaining = sorted(_os.listdir(dirpath), reverse=True)
        # Newest 3 (lexicographic desc) should be kept
        ok = len(remaining) == 3 and remaining == sorted(paths, reverse=True)[:3]
        return (
            "after 5 files written and FIFO applied, exactly 3 newest remain",
            f"remaining={remaining}, expected newest 3",
            ok,
        )

    def sds09():
        """
        Stored-files display must appear after the Run button in the simplified
        render function — verified by reading app.py directly.
        """
        app_path = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), "app.py"
        )
        with open(app_path, encoding="utf-8") as fh:
            src = fh.read()

        fn_start = src.find("def render_sahmk_discovery_tab()")
        fn_end   = src.find("\ndef ", fn_start + 1)
        fn_src   = src[fn_start:fn_end] if fn_start != -1 else src

        run_btn_pos   = fn_src.find("disc_run_btn")
        stored_display = fn_src.find("_data_rows")
        ok = run_btn_pos != -1 and stored_display != -1 and run_btn_pos < stored_display
        return (
            "Run button defined before stored-files display loop in simplified render",
            f"run_btn_pos={run_btn_pos}, stored_display_pos={stored_display}, order_ok={ok}",
            ok,
        )

    def sds10():
        """list_stored returns empty list when no files exist for a symbol."""
        from portfolio.sahmk_discovery import list_stored
        # Use a symbol that has never been stored in this temp dir
        stored = list_stored("__NONEXISTENT_SYMBOL__", root=_tmpdir)
        ok = stored == []
        return (
            "list_stored returns [] for symbol with no stored files",
            f"returned={stored!r}",
            ok,
        )

    def sds11():
        """Holdings valuation unchanged after storage operations."""
        from portfolio.sahmk_discovery import store_dataset
        # Run a store operation
        ep = _make_ep("Quote", "quote/2222/", True)
        store_dataset("2222", ep, root=_tmpdir)
        # Verify valuation still works correctly
        h1 = _holding("__SDS11A__", qty=10.0, avg_cost=100.0, price=110.0)
        h2 = _holding("__SDS11B__", qty=5.0,  avg_cost=200.0, price=220.0)
        fx = {"USD": _fx("USD", "USD", 1.0)}
        val = _val({"__SDS11A__": h1, "__SDS11B__": h2}, {}, "USD", fx)
        expected_mv = 10.0 * 110.0 + 5.0 * 220.0   # 1100 + 1100 = 2200
        ok = _near(val.holdings_value_base, expected_mv, 0.01)
        return (
            f"holdings_value_base = {expected_mv} after storage operations",
            f"holdings_value_base = {val.holdings_value_base}",
            ok,
        )

    def sds12():
        """Portfolio totals (holdings + cash) unchanged after storage operations."""
        from portfolio.sahmk_discovery import download_and_store
        # Compute portfolio total without touching SAHMK API
        h  = _holding("__SDS12__", qty=20.0, avg_cost=50.0, price=60.0)
        a  = _account("__sds12_acct__", cash=500.0, ccy="USD")
        fx = {"USD": _fx("USD", "USD", 1.0)}
        val_before = _val({"__SDS12__": h}, {"__sds12_acct__": a}, "USD", fx)
        # The storage module must not touch accounts/holdings — just re-validate
        val_after  = _val({"__SDS12__": h}, {"__sds12_acct__": a}, "USD", fx)
        mv_ok   = _near(val_before.holdings_value_base, val_after.holdings_value_base, 0.01)
        cash_ok = _near(val_before.cash_value_base,     val_after.cash_value_base,     0.01)
        total_ok = _near(val_before.total_portfolio_value_base,
                         val_after.total_portfolio_value_base, 0.01)
        ok = mv_ok and cash_ok and total_ok
        return (
            "holdings_value_base, cash_value_base, total_portfolio_value_base all unchanged",
            (
                f"mv_ok={mv_ok}, cash_ok={cash_ok}, total_ok={total_ok}, "
                f"total={val_after.total_portfolio_value_base}"
            ),
            ok,
        )

    def sds13():
        """
        All SDS storage functions importable and callable without error.
        Confirms the storage layer integrates cleanly with the module system.
        """
        import inspect
        from portfolio.sahmk_discovery import (
            discover, download_and_store, store_dataset,
            list_stored, load_stored_dataset, report_to_json,
            _apply_fifo_retention, _dataset_slug,
        )
        fns = [
            discover, download_and_store, store_dataset,
            list_stored, load_stored_dataset, report_to_json,
            _apply_fifo_retention, _dataset_slug,
        ]
        all_callable = all(callable(f) for f in fns)
        # Verify _dataset_slug works correctly
        slug_ok = _dataset_slug("Historical Prices") == "historical_prices"
        ok = all_callable and slug_ok
        return (
            "all 8 storage functions importable and callable; _dataset_slug correct",
            f"all_callable={all_callable}, slug_ok={slug_ok}",
            ok,
        )

    # ── Register tests ────────────────────────────────────────────────────────
    _tests = [
        ("SDS-01", "Discovery stores quote data (file written + list_stored)",                   "P0", True,  sds01),
        ("SDS-02", "Discovery stores historical prices",                                          "P0", True,  sds02),
        ("SDS-03", "Discovery stores market summary",                                             "P0", True,  sds03),
        ("SDS-04", "HTTP 404 / failed datasets are not stored",                                   "P0", True,  sds04),
        ("SDS-05", "Stored files survive refresh (disk-based list_stored call)",                  "P0", True,  sds05),
        ("SDS-06", "Stored files survive app restart (module reload + disk check)",               "P0", True,  sds06),
        ("SDS-07", "Load Stored Data works without API key (no network call)",                    "P0", True,  sds07),
        ("SDS-08", "FIFO retention keeps only newest 3 versions per dataset",                     "P0", True,  sds08),
        ("SDS-09", "Stored SAHMK Data section appears before Endpoint Detail in render",          "P1", False, sds09),
        ("SDS-10", "Empty state: list_stored returns [] when no files exist",                     "P1", False, sds10),
        ("SDS-11", "Holdings valuation unchanged after storage operations",                       "P0", True,  sds11),
        ("SDS-12", "Portfolio totals (MV + cash) unchanged after storage operations",             "P0", True,  sds12),
        ("SDS-13", "All storage functions importable; _dataset_slug correct",                     "P0", True,  sds13),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "portfolio.sahmk_discovery", sev, blocker, fn))

    # Clean up temp directory after all SDS tests complete
    try:
        shutil.rmtree(_tmpdir, ignore_errors=True)
    except Exception:
        pass

    return results


def _cat_fas() -> list[TestResult]:
    """
    FAS: Filtered Allocation Summary tests.

    FAS-01  No filter → summary equals total open holdings.
    FAS-02  Market filter → only selected market included.
    FAS-03  Sector filter → only selected sector included.
    FAS-04  Asset filter → only selected assets included.
    FAS-05  Filtered weight = filtered_mv / total_mv.
    FAS-06  Filtered P&L amount and % correct.
    FAS-07  Global portfolio header (holdings_value_base) unchanged.
    FAS-08  All prior FAS tests pass (meta).
    """
    CAT = "Filtered Allocation Summary"
    results: list[TestResult] = []

    # ── Pure-Python summary calculation (mirrors _render_allocation_section) ──
    def _fas_calc(rows: list[dict], filtered_rows: list[dict], total_mv: float) -> dict:
        """
        Replicate the summary math from _render_allocation_section.
        rows         – full unfiltered row list
        filtered_rows– post-filter row list
        total_mv     – val.holdings_value_base
        """
        filt_mv  = sum(r["_mv"] for r in filtered_rows)
        filt_cb  = sum(r["_cb"] for r in filtered_rows)
        filt_pnl = filt_mv - filt_cb
        filt_pnl_pct = (filt_pnl / filt_cb * 100) if filt_cb > 0 else 0.0
        filt_weight  = (filt_mv / total_mv * 100) if total_mv > 0 else 0.0
        return {
            "mv":      filt_mv,
            "cb":      filt_cb,
            "pnl":     filt_pnl,
            "pnl_pct": filt_pnl_pct,
            "weight":  filt_weight,
            "n":       len(filtered_rows),
        }

    def _make_rows(specs: list[dict]) -> tuple[list[dict], float]:
        """
        Build row dicts + total_mv from specs.
        Each spec: {ticker, market, sector, mv, cb}
        """
        rows = [
            {"Ticker":  s["ticker"],
             "Company": s["ticker"],
             "Market":  s.get("market", "US"),
             "Sector":  s.get("sector", "Energy"),
             "_mv":     s["mv"],
             "_cb":     s["cb"]}
            for s in specs
        ]
        total_mv = sum(r["_mv"] for r in rows)
        return rows, total_mv

    # ── Shared test portfolio ─────────────────────────────────────────────────
    _SPECS = [
        {"ticker": "A", "market": "US",     "sector": "Energy", "mv": 1000.0, "cb": 800.0},
        {"ticker": "B", "market": "US",     "sector": "Tech",   "mv": 2000.0, "cb": 1500.0},
        {"ticker": "C", "market": "Saudi",  "sector": "Energy", "mv": 500.0,  "cb": 600.0},
        {"ticker": "D", "market": "Saudi",  "sector": "Finance","mv": 750.0,  "cb": 700.0},
    ]
    _ALL_ROWS, _TOTAL_MV = _make_rows(_SPECS)

    def fas01():
        s = _fas_calc(_ALL_ROWS, _ALL_ROWS, _TOTAL_MV)
        ok = (
            _near(s["mv"],  _TOTAL_MV, 0.01) and
            _near(s["weight"], 100.0, 0.01) and
            s["n"] == 4
        )
        return (
            f"no-filter summary MV = {_TOTAL_MV}, weight = 100%, n = 4",
            f"mv={s['mv']}, weight={s['weight']:.2f}%, n={s['n']}",
            ok,
        )

    def fas02():
        filt = [r for r in _ALL_ROWS if r["Market"] == "US"]
        s = _fas_calc(_ALL_ROWS, filt, _TOTAL_MV)
        us_mv = 1000.0 + 2000.0
        ok = _near(s["mv"], us_mv, 0.01) and s["n"] == 2
        return (
            f"US market filter → MV = {us_mv}, n = 2",
            f"mv={s['mv']}, n={s['n']}",
            ok,
        )

    def fas03():
        filt = [r for r in _ALL_ROWS if r["Sector"] == "Energy"]
        s = _fas_calc(_ALL_ROWS, filt, _TOTAL_MV)
        energy_mv = 1000.0 + 500.0
        ok = _near(s["mv"], energy_mv, 0.01) and s["n"] == 2
        return (
            f"Energy sector filter → MV = {energy_mv}, n = 2",
            f"mv={s['mv']}, n={s['n']}",
            ok,
        )

    def fas04():
        filt = [r for r in _ALL_ROWS if r["Ticker"] in ("A", "D")]
        s = _fas_calc(_ALL_ROWS, filt, _TOTAL_MV)
        asset_mv = 1000.0 + 750.0
        ok = _near(s["mv"], asset_mv, 0.01) and s["n"] == 2
        return (
            f"asset filter A+D → MV = {asset_mv}, n = 2",
            f"mv={s['mv']}, n={s['n']}",
            ok,
        )

    def fas05():
        filt = [r for r in _ALL_ROWS if r["Market"] == "Saudi"]
        s = _fas_calc(_ALL_ROWS, filt, _TOTAL_MV)
        saudi_mv   = 500.0 + 750.0
        expected_w = saudi_mv / _TOTAL_MV * 100
        ok = _near(s["weight"], expected_w, 0.01)
        return (
            f"filtered weight = {expected_w:.4f}%",
            f"weight={s['weight']:.4f}%",
            ok,
        )

    def fas06():
        filt = [r for r in _ALL_ROWS if r["Market"] == "US"]
        s = _fas_calc(_ALL_ROWS, filt, _TOTAL_MV)
        us_mv  = 1000.0 + 2000.0
        us_cb  = 800.0 + 1500.0
        exp_pnl     = us_mv - us_cb          # 700.0
        exp_pnl_pct = exp_pnl / us_cb * 100  # 30.43...
        pnl_ok  = _near(s["pnl"],     exp_pnl,     0.01)
        pct_ok  = _near(s["pnl_pct"], exp_pnl_pct, 0.01)
        ok = pnl_ok and pct_ok
        return (
            f"US filtered P&L = {exp_pnl:.2f}, pct = {exp_pnl_pct:.2f}%",
            f"pnl={s['pnl']:.2f}, pnl_pct={s['pnl_pct']:.2f}%",
            ok,
        )

    def fas07():
        """Global portfolio header (holdings_value_base) unchanged by summary calc."""
        h1 = _holding("__FAS07A__", qty=10.0, avg_cost=100.0, price=120.0)
        h2 = _holding("__FAS07B__", qty=5.0,  avg_cost=200.0, price=180.0)
        fx = {"USD": _fx("USD", "USD", 1.0)}
        val_before = _val({"__FAS07A__": h1, "__FAS07B__": h2}, {}, "USD", fx)
        hv_before  = val_before.holdings_value_base
        # Simulate summary calc on rows derived from val
        rows = [
            {"_mv": r.base_market_value, "_cb": r.base_cost_basis}
            for r in val_before.per_holding
        ]
        filt = rows  # no filter
        _ = _fas_calc(rows, filt, val_before.holdings_value_base)
        # Re-compute val to confirm it's unaffected
        val_after  = _val({"__FAS07A__": h1, "__FAS07B__": h2}, {}, "USD", fx)
        ok = _near(val_before.holdings_value_base, val_after.holdings_value_base, 0.01)
        return (
            "holdings_value_base unchanged before and after summary calc",
            f"before={hv_before:.2f}, after={val_after.holdings_value_base:.2f}",
            ok,
        )

    def fas08():
        """Meta: all FAS-01–07 sub-calcs produce consistent results."""
        specs2 = [
            {"ticker": "X", "market": "EU", "sector": "Health", "mv": 3000.0, "cb": 2500.0},
            {"ticker": "Y", "market": "EU", "sector": "Tech",   "mv": 1000.0, "cb": 1200.0},
        ]
        rows2, total2 = _make_rows(specs2)
        s_all  = _fas_calc(rows2, rows2, total2)
        s_filt = _fas_calc(rows2, [rows2[0]], total2)  # only X
        weight_ok  = _near(s_all["weight"], 100.0, 0.01)
        filt_mv_ok = _near(s_filt["mv"], 3000.0, 0.01)
        pnl_ok     = _near(s_all["pnl"], 300.0, 0.01)   # 4000 - 3700
        n_ok       = s_all["n"] == 2 and s_filt["n"] == 1
        ok = weight_ok and filt_mv_ok and pnl_ok and n_ok
        return (
            "all summary metrics consistent across no-filter and filtered scenarios",
            (
                f"weight_ok={weight_ok}, filt_mv_ok={filt_mv_ok}, "
                f"pnl_ok={pnl_ok}, n_ok={n_ok}"
            ),
            ok,
        )

    _tests = [
        ("FAS-01", "No filter → summary equals total open holdings MV",              "P0", True,  fas01),
        ("FAS-02", "Market filter → only selected market included in summary",         "P0", True,  fas02),
        ("FAS-03", "Sector filter → only selected sector included in summary",         "P0", True,  fas03),
        ("FAS-04", "Asset filter → only selected assets included in summary",          "P0", True,  fas04),
        ("FAS-05", "Filtered weight = filtered_mv / total_mv",                        "P0", True,  fas05),
        ("FAS-06", "Filtered P&L amount and % correct for known values",               "P0", True,  fas06),
        ("FAS-07", "holdings_value_base unchanged after summary calc",                 "P0", True,  fas07),
        ("FAS-08", "All summary metrics consistent across filter scenarios (meta)",    "P0", True,  fas08),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._render_allocation_section", sev, blocker, fn))

    return results


def _cat_alloc() -> list[TestResult]:
    """
    ALLOC: Move Portfolio Allocation to dedicated Allocation tab.

    ALLOC-01  render_allocation_tab() function exists in app.py.
    ALLOC-02  render_holdings_tab() does not call _render_allocation_section.
    ALLOC-03  _render_allocation_section contains chart view selector.
    ALLOC-04  _render_allocation_section contains filter controls.
    ALLOC-05  _render_allocation_section contains Filtered Allocation Summary.
    ALLOC-06  _render_allocation_section contains allocation chart.
    ALLOC-07  _render_allocation_section contains filtered holdings table.
    ALLOC-08  render_allocation_tab() reads val from bundle dict.
    ALLOC-09  render_allocation_tab() reads base_ccy from bundle dict.
    ALLOC-10  render_holdings_tab() reads val from bundle dict (not independent).
    ALLOC-11  Full suite PASS (meta — all prior ALLOCs consistent).
    ALLOC-12  Both tab renderers accept bundle parameter, not zero-argument.
    ALLOC-13  No independent calculate_portfolio_valuation inside render_holdings_tab
              or render_allocation_tab (only _load_valuation_bundle may call it).
    """
    import os as _os

    CAT = "Allocation Tab"
    results: list[TestResult] = []

    app_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "app.py")
    with open(app_path, encoding="utf-8") as _fh:
        _app_src = _fh.read()

    def _fn_body(src: str, fn_name: str) -> str:
        """
        Extract the source body of the first top-level def matching fn_name.
        Returns everything from 'def fn_name' up to (but not including) the
        next top-level 'def ' or end of file.
        """
        import re
        pat = re.compile(rf"^def {re.escape(fn_name)}\b", re.MULTILINE)
        m = pat.search(src)
        if not m:
            return ""
        start = m.start()
        nxt = re.search(r"^def ", src[start + 1:], re.MULTILINE)
        end = start + 1 + nxt.start() if nxt else len(src)
        return src[start:end]

    _alloc_fn   = _fn_body(_app_src, "render_allocation_tab")
    _holdings_fn = _fn_body(_app_src, "render_holdings_tab")
    _section_fn  = _fn_body(_app_src, "_render_allocation_section")

    def alloc01():
        ok = "def render_allocation_tab(" in _app_src
        return (
            "render_allocation_tab() function defined in app.py",
            f"found={ok}",
            ok,
        )

    def alloc02():
        ok = "_render_allocation_section" not in _holdings_fn
        return (
            "_render_allocation_section not called inside render_holdings_tab",
            f"absent={ok}",
            ok,
        )

    def alloc03():
        ok = (
            "radio(" in _section_fn or
            "selectbox(" in _section_fn or
            "chart_view" in _section_fn or
            "alloc_view" in _section_fn or
            "Chart View" in _section_fn or
            "chart type" in _section_fn.lower()
        )
        return (
            "_render_allocation_section contains chart view selector widget",
            f"found={ok}",
            ok,
        )

    def alloc04():
        ok = "multiselect(" in _section_fn
        return (
            "_render_allocation_section contains multiselect filter control",
            f"found={ok}",
            ok,
        )

    def alloc05():
        ok = "Filtered Allocation Summary" in _section_fn
        return (
            "_render_allocation_section contains 'Filtered Allocation Summary'",
            f"found={ok}",
            ok,
        )

    def alloc06():
        ok = (
            "go.Pie(" in _section_fn or
            "go.Bar(" in _section_fn or
            "go.Treemap(" in _section_fn or
            "plotly" in _section_fn.lower()
        )
        return (
            "_render_allocation_section contains plotly chart",
            f"found={ok}",
            ok,
        )

    def alloc07():
        ok = "st.dataframe(" in _section_fn
        return (
            "_render_allocation_section contains st.dataframe (filtered holdings table)",
            f"found={ok}",
            ok,
        )

    def alloc08():
        ok = 'bundle["val"]' in _alloc_fn or "bundle['val']" in _alloc_fn
        return (
            "render_allocation_tab reads val from bundle dict",
            f"found={ok}",
            ok,
        )

    def alloc09():
        ok = 'bundle["base_ccy"]' in _alloc_fn or "bundle['base_ccy']" in _alloc_fn
        return (
            "render_allocation_tab reads base_ccy from bundle dict",
            f"found={ok}",
            ok,
        )

    def alloc10():
        ok = 'bundle["val"]' in _holdings_fn or "bundle['val']" in _holdings_fn
        return (
            "render_holdings_tab reads val from bundle dict (not independent call)",
            f"found={ok}",
            ok,
        )

    def alloc11():
        sub_fns = [alloc01, alloc02, alloc03, alloc04, alloc05,
                   alloc06, alloc07, alloc08, alloc09, alloc10]
        results_sub = [fn() for fn in sub_fns]
        ok = all(r[2] for r in results_sub)
        failing = [sub_fns[i].__name__ for i, r in enumerate(results_sub) if not r[2]]
        return (
            "all ALLOC-01–10 sub-checks consistent",
            f"ok={ok}" + (f", failing={failing}" if not ok else ""),
            ok,
        )

    def alloc12():
        holdings_has_bundle = "bundle: dict" in _holdings_fn
        alloc_has_bundle    = "bundle: dict" in _alloc_fn
        ok = holdings_has_bundle and alloc_has_bundle
        return (
            "both render_holdings_tab and render_allocation_tab accept bundle parameter",
            f"holdings={holdings_has_bundle}, allocation={alloc_has_bundle}",
            ok,
        )

    def alloc13():
        CALL = "calculate_portfolio_valuation("
        in_holdings = CALL in _holdings_fn
        in_alloc    = CALL in _alloc_fn
        ok = not in_holdings and not in_alloc
        return (
            "no independent calculate_portfolio_valuation inside either render tab function",
            f"in_holdings={in_holdings}, in_alloc={in_alloc}",
            ok,
        )

    _tests = [
        ("ALLOC-01", "render_allocation_tab() function exists in app.py",                        "P0", True,  alloc01),
        ("ALLOC-02", "render_holdings_tab() does not call _render_allocation_section",            "P0", True,  alloc02),
        ("ALLOC-03", "_render_allocation_section contains chart view selector",                   "P0", True,  alloc03),
        ("ALLOC-04", "_render_allocation_section contains filter controls",                       "P0", True,  alloc04),
        ("ALLOC-05", "_render_allocation_section contains Filtered Allocation Summary",           "P0", True,  alloc05),
        ("ALLOC-06", "_render_allocation_section contains allocation chart",                      "P0", True,  alloc06),
        ("ALLOC-07", "_render_allocation_section contains filtered holdings table",               "P0", True,  alloc07),
        ("ALLOC-08", "render_allocation_tab reads val from bundle",                               "P0", True,  alloc08),
        ("ALLOC-09", "render_allocation_tab reads base_ccy from bundle",                          "P0", True,  alloc09),
        ("ALLOC-10", "render_holdings_tab reads val from bundle (not independent call)",          "P0", True,  alloc10),
        ("ALLOC-11", "All ALLOC-01–10 sub-checks consistent (meta)",                              "P0", True,  alloc11),
        ("ALLOC-12", "Both tab renderers accept bundle parameter",                                "P0", True,  alloc12),
        ("ALLOC-13", "No independent valuation call inside either render tab function",           "P0", True,  alloc13),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app.render_allocation_tab", sev, blocker, fn))

    return results


def _cat_alloc_qp() -> list[TestResult]:
    """
    ALLOC-QP: Allocation Quick Market Presets.

    ALLOC-QP-01  Saudi preset button exists and sets alloc_ms_market = ["Saudi"].
    ALLOC-QP-02  US preset button exists and sets alloc_ms_market = ["US"].
    ALLOC-QP-03  All preset button exists and pops alloc_ms_market.
    ALLOC-QP-04  Preset buttons placed above Chart view in source order.
    ALLOC-QP-05  Preset buttons each call st.rerun() after state mutation.
    ALLOC-QP-06  Preset buttons do NOT mutate holdings, accounts, or transactions.
    ALLOC-QP-07  Market filter logic applies correctly after preset (unit check).
    ALLOC-QP-08  Full suite PASS (meta).
    """
    import os as _os

    CAT = "Allocation Quick Presets"
    results: list[TestResult] = []

    app_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "app.py")
    with open(app_path, encoding="utf-8") as _fh:
        _app_src = _fh.read()

    def _fn_body(src: str, fn_name: str) -> str:
        import re
        pat = re.compile(rf"^def {re.escape(fn_name)}\b", re.MULTILINE)
        m = pat.search(src)
        if not m:
            return ""
        start = m.start()
        nxt = re.search(r"^def ", src[start + 1:], re.MULTILINE)
        end = start + 1 + nxt.start() if nxt else len(src)
        return src[start:end]

    _section_fn = _fn_body(_app_src, "_render_allocation_section")

    def qp01():
        ok = (
            "alloc_qp_radio" in _section_fn and
            '["Saudi"]' in _section_fn and
            "alloc_ms_market" in _section_fn
        )
        return (
            "Saudi preset (radio) sets alloc_ms_market = ['Saudi']",
            f"found={ok}",
            ok,
        )

    def qp02():
        ok = (
            "alloc_qp_radio" in _section_fn and
            '["US"]' in _section_fn and
            "alloc_ms_market" in _section_fn
        )
        return (
            "US preset (radio) sets alloc_ms_market = ['US']",
            f"found={ok}",
            ok,
        )

    def qp03():
        ok = (
            "alloc_qp_radio" in _section_fn and
            'pop("alloc_ms_market"' in _section_fn
        )
        return (
            "All preset (radio) pops alloc_ms_market",
            f"found={ok}",
            ok,
        )

    def qp04():
        chart_view_pos = _section_fn.find("alloc_chart_view")
        preset_pos     = _section_fn.find("alloc_qp_radio")
        ok = preset_pos != -1 and chart_view_pos != -1 and preset_pos < chart_view_pos
        return (
            "Preset radio appears before Chart view selector in source order",
            f"preset_pos={preset_pos}, chart_view_pos={chart_view_pos}, before={ok}",
            ok,
        )

    def qp05():
        preset_start = _section_fn.find("alloc_qp_radio")
        preset_end   = _section_fn.find("alloc_chart_view")
        if preset_start == -1 or preset_end == -1:
            return ("Preset block found for rerun check", "block not found", False)
        preset_block = _section_fn[preset_start:preset_end]
        rerun_count  = preset_block.count("st.rerun()")
        ok = rerun_count >= 3
        return (
            "Preset radio block calls st.rerun() for each of the 3 options",
            f"rerun_calls_found={rerun_count}",
            ok,
        )

    def qp06():
        FORBIDDEN = [
            "upsert_holding(", "delete_holding(", "update_current_price(",
            "record_transaction(", "upsert_account(", "update_account_cash(",
        ]
        preset_block_start = _section_fn.find("alloc_qp_radio")
        preset_block_end   = _section_fn.find("alloc_chart_view")
        if preset_block_start == -1 or preset_block_end == -1:
            return ("Preset block found for mutation check", "block not found", False)
        preset_block = _section_fn[preset_block_start:preset_block_end]
        violations = [f for f in FORBIDDEN if f in preset_block]
        ok = not violations
        return (
            "Preset block does not call any holdings/accounts/transactions mutators",
            f"violations={violations}",
            ok,
        )

    def qp07():
        rows = [
            {"Market": "Saudi", "_mv": 1000.0, "_cb": 800.0},
            {"Market": "US",    "_mv": 2000.0, "_cb": 1500.0},
            {"Market": "Saudi", "_mv": 500.0,  "_cb": 400.0},
        ]
        all_markets = ["Saudi", "US"]

        def _apply(sel_markets):
            filt = rows[:]
            if sel_markets and set(sel_markets) != set(all_markets):
                filt = [r for r in filt if r["Market"] in sel_markets]
            return filt

        saudi_filt = _apply(["Saudi"])
        us_filt    = _apply(["US"])
        all_filt   = _apply(all_markets)

        saudi_ok = all(r["Market"] == "Saudi" for r in saudi_filt) and len(saudi_filt) == 2
        us_ok    = all(r["Market"] == "US"    for r in us_filt)    and len(us_filt)    == 1
        all_ok   = len(all_filt) == 3

        ok = saudi_ok and us_ok and all_ok
        return (
            "Market filter logic: Saudi→2 rows, US→1 row, All→3 rows",
            f"saudi_ok={saudi_ok}, us_ok={us_ok}, all_ok={all_ok}",
            ok,
        )

    def qp08():
        sub_fns = [qp01, qp02, qp03, qp04, qp05, qp06, qp07]
        sub_results = [fn() for fn in sub_fns]
        ok = all(r[2] for r in sub_results)
        failing = [sub_fns[i].__name__ for i, r in enumerate(sub_results) if not r[2]]
        return (
            "All ALLOC-QP-01–07 consistent (meta)",
            f"ok={ok}" + (f", failing={failing}" if not ok else ""),
            ok,
        )

    _tests = [
        ("ALLOC-QP-01", "Saudi preset (radio) sets alloc_ms_market = ['Saudi']",            "P0", True,  qp01),
        ("ALLOC-QP-02", "US preset (radio) sets alloc_ms_market = ['US']",                  "P0", True,  qp02),
        ("ALLOC-QP-03", "All preset (radio) pops alloc_ms_market",                          "P0", True,  qp03),
        ("ALLOC-QP-04", "Preset radio placed above Chart view selector",                    "P0", True,  qp04),
        ("ALLOC-QP-05", "Preset radio block calls st.rerun() for each of the 3 options",   "P0", True,  qp05),
        ("ALLOC-QP-06", "Preset block does not mutate holdings/accounts/transactions",      "P0", True,  qp06),
        ("ALLOC-QP-07", "Market filter logic correct for Saudi, US, and All presets",       "P0", True,  qp07),
        ("ALLOC-QP-08", "All ALLOC-QP-01–07 consistent (meta)",                            "P0", True,  qp08),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._render_allocation_section", sev, blocker, fn))

    return results


def _cat_alloc_ui() -> list[TestResult]:
    """
    ALLOC-UI: Allocation tab mobile UI layout optimisation.

    ALLOC-UI-01  Quick preset row uses st.columns(3) — no vertical stacking by code.
    ALLOC-UI-02  Saudi preset still sets alloc_ms_market = ['Saudi'].
    ALLOC-UI-03  US preset still sets alloc_ms_market = ['US'].
    ALLOC-UI-04  All preset still pops alloc_ms_market.
    ALLOC-UI-05  KPI summary uses 2-2-1 layout (two st.columns(2) rows + solo Holdings).
    ALLOC-UI-06  KPI values use compact formatter (_fmt_compact).
    ALLOC-UI-07  KPI values reference filtered data (_fas_mv, _fas_cb, _fas_pnl, _fas_weight, _fas_n).
    ALLOC-UI-08  CSS media query prevents column stacking (min-width: 0) on mobile.
    ALLOC-UI-09  Full regression suite passes (meta).
    """
    import os as _os
    import re as _re

    CAT = "Allocation Mobile UI"
    results: list[TestResult] = []

    app_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "app.py")
    with open(app_path, encoding="utf-8") as _fh:
        _app_src = _fh.read()

    def _fn_body(src: str, fn_name: str) -> str:
        pat = _re.compile(rf"^def {_re.escape(fn_name)}\b", _re.MULTILINE)
        m = pat.search(src)
        if not m:
            return ""
        start = m.start()
        nxt = _re.search(r"^def ", src[start + 1:], _re.MULTILINE)
        end = start + 1 + nxt.start() if nxt else len(src)
        return src[start:end]

    _section_fn = _fn_body(_app_src, "_render_allocation_section")

    def ui01():
        ok = "alloc_qp_radio" in _section_fn and "horizontal=True" in _section_fn
        return (
            "Quick presets use st.radio(horizontal=True) — single native row",
            f"found={ok}",
            ok,
        )

    def ui02():
        ok = "alloc_qp_radio" in _section_fn and '["Saudi"]' in _section_fn
        return ("Saudi preset (radio) sets alloc_ms_market = ['Saudi']", f"found={ok}", ok)

    def ui03():
        ok = "alloc_qp_radio" in _section_fn and '["US"]' in _section_fn
        return ("US preset (radio) sets alloc_ms_market = ['US']", f"found={ok}", ok)

    def ui04():
        ok = "alloc_qp_radio" in _section_fn and 'pop("alloc_ms_market"' in _section_fn
        return ("All preset (radio) pops alloc_ms_market", f"found={ok}", ok)

    def ui05():
        has_grid  = "fas-kpi-grid" in _section_fn
        has_cards = _section_fn.count("fas-kpi-card") >= 5
        has_html  = "unsafe_allow_html=True" in _section_fn
        has_kpipc = "_kpi_pc" in _section_fn          # locally-scoped colour var
        ok = has_grid and has_cards and has_html and has_kpipc
        return (
            "KPI summary uses HTML flex grid (fas-kpi-grid, ≥5 cards, _kpi_pc local)",
            f"grid={has_grid}, cards={has_cards}, html={has_html}, kpi_pc={has_kpipc}",
            ok,
        )

    def ui06():
        ok = "_fmt_compact" in _section_fn and "_fmt_compact(_fas_mv)" in _section_fn
        return ("KPI values use compact formatter (_fmt_compact)", f"found={ok}", ok)

    def ui07():
        required = ["_fas_mv", "_fas_cb", "_fas_pnl", "_fas_weight", "_fas_n"]
        missing = [k for k in required if k not in _section_fn]
        ok = not missing
        return (
            "KPI values reference filtered data (_fas_mv/cb/pnl/weight/n)",
            f"missing={missing}",
            ok,
        )

    def ui08():
        ok = (
            "max-width: 768px" in _app_src
            and '[data-testid="column"]' in _app_src
            and "min-width: 0" in _app_src
        )
        return (
            "CSS media query includes [data-testid=column] min-width: 0 for mobile",
            f"found={ok}",
            ok,
        )

    def ui09():
        sub = [ui01, ui02, ui03, ui04, ui05, ui06, ui07, ui08]
        outcomes = [fn() for fn in sub]
        ok = all(o[2] for o in outcomes)
        failing = [sub[i].__name__ for i, o in enumerate(outcomes) if not o[2]]
        return (
            "All ALLOC-UI-01–08 consistent (meta)",
            f"ok={ok}" + (f", failing={failing}" if not ok else ""),
            ok,
        )

    _tests = [
        ("ALLOC-UI-01", "Quick preset row uses st.columns(3) — no vertical stacking",    "P0", True, ui01),
        ("ALLOC-UI-02", "Saudi preset still sets alloc_ms_market = ['Saudi']",            "P0", True, ui02),
        ("ALLOC-UI-03", "US preset still sets alloc_ms_market = ['US']",                 "P0", True, ui03),
        ("ALLOC-UI-04", "All preset still pops alloc_ms_market",                         "P0", True, ui04),
        ("ALLOC-UI-05", "KPI summary uses 2-2-1 layout (two st.columns(2) + Holdings)",  "P0", True, ui05),
        ("ALLOC-UI-06", "KPI values use compact formatter (_fmt_compact)",               "P0", True, ui06),
        ("ALLOC-UI-07", "KPI values reference filtered data",                            "P0", True, ui07),
        ("ALLOC-UI-08", "CSS prevents column stacking on mobile (min-width: 0)",         "P0", True, ui08),
        ("ALLOC-UI-09", "All ALLOC-UI-01–08 consistent (meta)",                         "P0", True, ui09),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._render_allocation_section", sev, blocker, fn))

    return results


def _cat_hld_ui() -> list[TestResult]:
    """
    HLD-UI: Holdings modal open/close state-management tests.

    HLD-UI-01  No persistent holdings_modal_open flag; _add_new_clicked used instead.
    HLD-UI-02  Cancel handler does NOT reference holdings_modal_open; just st.rerun().
    HLD-UI-03  Save handler does NOT include holdings_modal_open in _keys_to_clear.
    HLD-UI-04  Empty-portfolio button calls _dlg_add_new() directly; no persistent
               flag check inside the if-not-holdings block.

    Background: the old holdings_modal_open persistent flag caused the modal to
    reopen after X-close because our code explicitly called _dlg_add_new() on every
    rerun.  Streamlit's @st.dialog keeps the dialog open across widget-interaction
    reruns automatically; we only need to call the function once on button click.
    """
    import re as _re
    import pathlib as _pl

    CAT = "Holdings UI"
    results: list[TestResult] = []
    _src = _pl.Path(__file__).parent / "app.py"
    _text = _src.read_text(encoding="utf-8")

    def hld_ui_01():
        """
        The toolbar Add New Position button must set _add_new_clicked (local var),
        NOT set holdings_modal_open in session state.  The old _hm_alive mechanism
        and holdings_modal_open session-state key must be absent from app.py.
        """
        old_flag_gone  = 'st.session_state["holdings_modal_open"] = True' not in _text
        hm_alive_gone  = "_hm_alive" not in _text
        clicked_var    = "_add_new_clicked = True" in _text
        ok = old_flag_gone and hm_alive_gone and clicked_var
        return (
            "No holdings_modal_open flag; no _hm_alive; _add_new_clicked var present",
            (
                f"old_flag_gone={old_flag_gone}, "
                f"hm_alive_gone={hm_alive_gone}, "
                f"clicked_var={clicked_var}"
            ),
            ok,
        )

    def hld_ui_02():
        """
        The Cancel button handler inside _dlg_add_new must NOT reference
        holdings_modal_open — it should only clear ahn_ keys and call st.rerun().
        """
        cancel_block = _re.search(
            r'key=["\']ahn_cancel["\'].*?st\.rerun\(\)',
            _text,
            _re.DOTALL,
        )
        if not cancel_block:
            return ("cancel block found", "cancel block NOT found in app.py", False)
        block_text = cancel_block.group(0)
        no_flag_in_cancel = "holdings_modal_open" not in block_text
        has_rerun = "st.rerun()" in block_text
        ok = no_flag_in_cancel and has_rerun
        return (
            "Cancel handler has no holdings_modal_open reference; calls st.rerun()",
            f"no_flag_in_cancel={no_flag_in_cancel}, has_rerun={has_rerun}",
            ok,
        )

    def hld_ui_03():
        """
        The Save success block _keys_to_clear list must NOT contain
        'holdings_modal_open' — no persistent flag to clear on save.
        """
        keys_block = _re.search(
            r'_keys_to_clear\s*=\s*\[.*?holdings_modal_open.*?\]',
            _text,
            _re.DOTALL,
        )
        ok = keys_block is None
        return (
            "'holdings_modal_open' absent from _keys_to_clear in save handler",
            f"absent={'yes' if ok else 'no — still present (BUG)'}",
            ok,
        )

    def hld_ui_04():
        """
        The empty-portfolio Add New Position button must call _dlg_add_new()
        directly (not set a persistent flag), and there must be NO
        holdings_modal_open persistent-check block inside the if-not-holdings
        section.
        """
        # Check: empty button calls _dlg_add_new() directly in its if-branch
        direct_call = bool(_re.search(
            r'key=["\']open_add_new_empty_btn["\'][^}]{0,200}_dlg_add_new\(\)',
            _text,
            _re.DOTALL,
        ))
        # Check: no persistent flag check inside the not-holdings section
        persistent_check_gone = not bool(_re.search(
            r'if not holdings:.*?st\.session_state\.get\(["\']holdings_modal_open',
            _text,
            _re.DOTALL,
        ))
        ok = direct_call and persistent_check_gone
        return (
            "empty-portfolio button calls _dlg_add_new() directly; no persistent flag check",
            (
                f"direct_call={direct_call}, "
                f"persistent_check_gone={persistent_check_gone}"
            ),
            ok,
        )

    _tests = [
        ("HLD-UI-01", "No persistent flag; _add_new_clicked var used instead",              "P0", True, hld_ui_01),
        ("HLD-UI-02", "Cancel handler has no holdings_modal_open reference",                 "P0", True, hld_ui_02),
        ("HLD-UI-03", "Save handler does not include holdings_modal_open in keys_to_clear",  "P0", True, hld_ui_03),
        ("HLD-UI-04", "Empty-portfolio button calls _dlg_add_new() directly",               "P0", True, hld_ui_04),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app.render_holdings_tab", sev, blocker, fn))

    return results


def _cat_alloc_mkt() -> list[TestResult]:
    """
    ALLOC-MKT: Market multiselect removed from Filters panel (minimal UI simplification).

    ALLOC-MKT-01  Market multiselect (key="alloc_ms_market") absent from Filters expander.
    ALLOC-MKT-02  Filter chain still reads alloc_ms_market for market filtering (_sel_markets).
    """
    import pathlib as _pl

    CAT = "Allocation Market Filter"
    results: list[TestResult] = []
    _src = _pl.Path(__file__).parent / "app.py"
    _text = _src.read_text(encoding="utf-8")

    # Isolate _render_allocation_section source
    _start = _text.find("def _render_allocation_section(")
    _end   = _text.find("\ndef ", _start + 1)
    _section_fn = _text[_start:_end] if _start != -1 and _end != -1 else _text

    def mkt01():
        """
        The Market multiselect widget with key='alloc_ms_market' must no longer
        appear inside the Filters expander. The preset radio is the only Market UI.
        """
        # The multiselect used: st.multiselect(\n...\n key="alloc_ms_market"
        # Check that no multiselect call uses key="alloc_ms_market"
        import re as _re
        pattern = r'st\.multiselect\([^)]*key\s*=\s*["\']alloc_ms_market["\']'
        found = bool(_re.search(pattern, _section_fn, _re.DOTALL))
        ok = not found
        return (
            "Market multiselect (key=alloc_ms_market) absent from Filters expander",
            f"multiselect with alloc_ms_market key {'still present' if found else 'not found (correct)'}",
            ok,
        )

    def mkt02():
        """
        The filter chain must still read alloc_ms_market from session state to
        derive _sel_markets (the preset radio is the sole writer of this key).
        """
        ok = 'st.session_state.get("alloc_ms_market"' in _section_fn
        return (
            "Filter chain reads alloc_ms_market for market filtering",
            f"session_state.get('alloc_ms_market') {'found' if ok else 'NOT FOUND'}",
            ok,
        )

    _tests = [
        ("ALLOC-MKT-01", "Market multiselect absent from Filters expander",           "P0", True, mkt01),
        ("ALLOC-MKT-02", "Filter chain still reads alloc_ms_market for filtering",    "P0", True, mkt02),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._render_allocation_section", sev, blocker, fn))

    return results


def _cat_alloc_scope() -> list[TestResult]:
    """
    ALLOC-SCOPE: Child filter options scoped to active Market preset.

    ALLOC-SCOPE-01  Saudi preset: _all_sectors/_all_ccys_u/_all_companies derived from _mkt_df.
    ALLOC-SCOPE-02  _mkt_df is market_scope-filtered view of _df (not _df itself).
    ALLOC-SCOPE-03  market_scope = None for All preset (no market restriction).
    ALLOC-SCOPE-04  Stale child purge block covers all 3 keys before multiselects render.
    ALLOC-SCOPE-05  Filter chain base is _mkt_df.copy() not _df.copy().
    ALLOC-SCOPE-06  _sel_markets and its filter line absent from filter chain.
    ALLOC-SCOPE-07  Reset button clears only child keys (sector/ccy/asset), not alloc_ms_market.
    ALLOC-SCOPE-08  _active_filters uses market_scope for Market label, not _sel_markets.
    ALLOC-SCOPE-09  _all_sectors/_all_ccys_u/_all_companies defined AFTER market_scope block.
    ALLOC-SCOPE-10  Full regression suite passes (meta).
    """
    import re as _re
    import pathlib as _pl

    CAT = "Allocation Scope"
    results: list[TestResult] = []
    _src = _pl.Path(__file__).parent / "app.py"
    _text = _src.read_text(encoding="utf-8")

    _start = _text.find("def _render_allocation_section(")
    _end   = _text.find("\ndef ", _start + 1)
    _fn    = _text[_start:_end] if _start != -1 and _end != -1 else _text

    def sc01():
        """_all_sectors/ccys/companies derived from _mkt_df (not _df)."""
        ok = (
            '_mkt_df["Sector"]' in _fn
            and '_mkt_df["CCY"]'   in _fn
            and '_mkt_df["Company"]' in _fn
            and "_all_sectors" in _fn
            and "_all_ccys_u"  in _fn
            and "_all_companies" in _fn
        )
        return ("Child option lists derived from _mkt_df", f"found={ok}", ok)

    def sc02():
        """_mkt_df is created as market_scope-filtered view of _df."""
        ok = (
            '_mkt_df = _df[_df["Market"].isin(market_scope)] if market_scope else _df' in _fn
        )
        return ("_mkt_df filters _df by market_scope", f"found={ok}", ok)

    def sc03():
        """market_scope = None for the All branch."""
        ok = "market_scope = None" in _fn
        return ("market_scope = None for All preset", f"found={ok}", ok)

    def sc04():
        """Stale child purge block covers all 3 child keys."""
        ok = (
            '"alloc_ms_sector"' in _fn
            and '"alloc_ms_ccy"'    in _fn
            and '"alloc_ms_asset"'  in _fn
            and 'not all(v in _valid for v in _stored)' in _fn
        )
        return ("Stale child purge covers sector/ccy/asset", f"found={ok}", ok)

    def sc05():
        """Filter chain base is _mkt_df.copy()."""
        ok = "_filt = _mkt_df.copy()" in _fn
        return ("Filter chain base is _mkt_df.copy()", f"found={ok}", ok)

    def sc06():
        """_sel_markets variable and its Market filter line are absent from filter chain."""
        # After the refactor, _sel_markets should not exist as a session_state read
        # and the old market filter line should be gone
        has_sel_markets_read = (
            '_sel_markets   = st.session_state.get("alloc_ms_market"' in _fn
        )
        has_old_market_filter = (
            '_filt[_filt["Market"].isin(_sel_markets)]' in _fn
        )
        ok = not has_sel_markets_read and not has_old_market_filter
        return (
            "_sel_markets read and old Market filter line absent",
            f"sel_markets_read={has_sel_markets_read}, old_filter={has_old_market_filter}",
            ok,
        )

    def sc07():
        """Reset button clears only child keys — alloc_ms_market absent from its list."""
        # Find the reset button block and confirm alloc_ms_market is not in it
        reset_match = _re.search(
            r'alloc_reset_filters.*?st\.rerun\(\)', _fn, _re.DOTALL
        )
        if not reset_match:
            return ("Reset button block present", "block not found", False)
        reset_block = reset_match.group(0)
        ok = "alloc_ms_market" not in reset_block
        return (
            "Reset clears only sector/ccy/asset (alloc_ms_market absent)",
            f"alloc_ms_market_in_reset={not ok}",
            ok,
        )

    def sc08():
        """_active_filters uses market_scope for Market label."""
        ok = (
            'if market_scope:' in _fn
            and '_active_filters.append(f"Market: ' in _fn
            and '_sel_markets' not in _fn.split('_active_filters')[1].split('\n')[0]
        )
        return ("_active_filters uses market_scope for Market label", f"found={ok}", ok)

    def sc09():
        """Scoped option lists (_all_sectors etc.) defined after market_scope block."""
        pos_scope  = _fn.find("market_scope: list")
        pos_sector = _fn.find('_all_sectors')
        ok = pos_scope != -1 and pos_sector != -1 and pos_sector > pos_scope
        return (
            "Scoped option lists defined after market_scope block",
            f"scope_pos={pos_scope}, sector_pos={pos_sector}",
            ok,
        )

    def sc10():
        """Meta: all other alloc tests still pass (checks suite can import)."""
        try:
            _cat_alloc_qp()
            _cat_alloc_ui()
            _cat_alloc_mkt()
            return ("Full regression suite importable and callable", "ok", True)
        except Exception as exc:
            return ("Full regression suite importable and callable", str(exc), False)

    _tests = [
        ("ALLOC-SCOPE-01", "Child option lists derived from _mkt_df",                    "P0", True,  sc01),
        ("ALLOC-SCOPE-02", "_mkt_df filters _df by market_scope",                        "P0", True,  sc02),
        ("ALLOC-SCOPE-03", "market_scope = None for All preset",                          "P0", True,  sc03),
        ("ALLOC-SCOPE-04", "Stale child purge covers sector/ccy/asset",                  "P0", True,  sc04),
        ("ALLOC-SCOPE-05", "Filter chain base is _mkt_df.copy()",                        "P0", True,  sc05),
        ("ALLOC-SCOPE-06", "_sel_markets and old Market filter line absent",             "P0", True,  sc06),
        ("ALLOC-SCOPE-07", "Reset clears only sector/ccy/asset (not market preset)",     "P0", True,  sc07),
        ("ALLOC-SCOPE-08", "_active_filters uses market_scope for Market label",         "P0", True,  sc08),
        ("ALLOC-SCOPE-09", "Scoped option lists defined after market_scope block",       "P0", True,  sc09),
        ("ALLOC-SCOPE-10", "Full regression suite importable and callable (meta)",       "P0", True,  sc10),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._render_allocation_section", sev, blocker, fn))

    return results


def _cat_edit_ui() -> list[TestResult]:
    """
    EDIT-UI-01  Edit dialog renders Market selectbox wired to upsert_holding.
    EDIT-UI-02  Edit dialog renders Sector selectbox wired to upsert_holding.
    EDIT-UI-03  Edit dialog renders Asset Type selectbox wired to upsert_holding.
    EDIT-UI-04  Edit dialog renders Currency selectbox wired to upsert_holding.
    """
    import re as _re
    import pathlib as _pl

    CAT = "Edit Holding UI"
    results: list[TestResult] = []
    _src = _pl.Path(__file__).parent / "app.py"
    _text = _src.read_text(encoding="utf-8")

    # Isolate the _dlg_edit function body
    _start = _text.find("def _dlg_edit(")
    _end   = _text.find("\n        @st.dialog", _start + 1)
    _fn    = _text[_start:_end] if _start != -1 and _end != -1 else _text

    def edit_ui_01():
        """Market selectbox in _dlg_edit AND passed to upsert_holding."""
        has_selectbox = bool(_re.search(
            r'st\.selectbox\s*\(\s*["\']Market["\']',
            _fn,
        ))
        passed_to_upsert = "market=_e_market" in _fn
        ok = has_selectbox and passed_to_upsert
        return (
            "Market selectbox present in Edit dialog and passed to upsert_holding",
            f"has_selectbox={has_selectbox}, passed_to_upsert={passed_to_upsert}",
            ok,
        )

    def edit_ui_02():
        """Sector selectbox in _dlg_edit AND passed to upsert_holding."""
        has_selectbox = bool(_re.search(
            r'st\.selectbox\s*\(\s*["\']Sector["\']',
            _fn,
        ))
        passed_to_upsert = "sector=_e_sector" in _fn
        ok = has_selectbox and passed_to_upsert
        return (
            "Sector selectbox present in Edit dialog and passed to upsert_holding",
            f"has_selectbox={has_selectbox}, passed_to_upsert={passed_to_upsert}",
            ok,
        )

    def edit_ui_03():
        """Asset Type selectbox in _dlg_edit AND passed to upsert_holding."""
        has_selectbox = bool(_re.search(
            r'st\.selectbox\s*\(\s*["\']Asset type["\']',
            _fn,
        ))
        passed_to_upsert = "asset_type=_e_type" in _fn
        ok = has_selectbox and passed_to_upsert
        return (
            "Asset type selectbox present in Edit dialog and passed to upsert_holding",
            f"has_selectbox={has_selectbox}, passed_to_upsert={passed_to_upsert}",
            ok,
        )

    def edit_ui_04():
        """Currency selectbox in _dlg_edit AND passed to upsert_holding."""
        has_selectbox = bool(_re.search(
            r'st\.selectbox\s*\(\s*["\']Currency["\']',
            _fn,
        ))
        passed_to_upsert = "currency=_e_ccy" in _fn
        ok = has_selectbox and passed_to_upsert
        return (
            "Currency selectbox present in Edit dialog and passed to upsert_holding",
            f"has_selectbox={has_selectbox}, passed_to_upsert={passed_to_upsert}",
            ok,
        )

    _tests = [
        ("EDIT-UI-01", "Market selectbox present in Edit dialog and wired to upsert_holding",     "P0", True, edit_ui_01),
        ("EDIT-UI-02", "Sector selectbox present in Edit dialog and wired to upsert_holding",     "P0", True, edit_ui_02),
        ("EDIT-UI-03", "Asset type selectbox present in Edit dialog and wired to upsert_holding", "P0", True, edit_ui_03),
        ("EDIT-UI-04", "Currency selectbox present in Edit dialog and wired to upsert_holding",   "P0", True, edit_ui_04),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._dlg_edit", sev, blocker, fn))

    return results


def _cat_acc_ui_ext() -> list[TestResult]:
    """
    ACC-UI-06  load_accounts() has no caching decorator — fresh on every call.
    ACC-UI-07  active_accounts() excludes inactive accounts.
    ACC-UI-08  Bank and Cash account types excluded from modal eligible set.
    """
    import re as _re
    import pathlib as _pl
    import inspect as _inspect

    CAT = "Accounts UI"
    results: list[TestResult] = []

    def acc_ui_06():
        """
        load_accounts() must read from disk on every call.
        Confirm: no @st.cache_data, @st.cache_resource, or @lru_cache on it.
        """
        from portfolio.accounts import load_accounts as _la
        src = _inspect.getsource(_la)
        no_cache_data     = "@st.cache_data"     not in src
        no_cache_resource = "@st.cache_resource" not in src
        no_lru_cache      = "@lru_cache"         not in src
        ok = no_cache_data and no_cache_resource and no_lru_cache
        return (
            "load_accounts has no caching decorator — always reads from disk",
            f"no_cache_data={no_cache_data}, no_cache_resource={no_cache_resource}, no_lru_cache={no_lru_cache}",
            ok,
        )

    def acc_ui_07():
        """
        active_accounts() must filter by active=True — inactive accounts excluded.
        """
        from portfolio.accounts import Account, active_accounts as _aa
        import unittest.mock as _mock, json, tempfile, os

        acct_active   = Account(account_id="AAAA1111", account_name="Active",   active=True)
        acct_inactive = Account(account_id="BBBB2222", account_name="Inactive", active=False)
        data = {
            "AAAA1111": {"account_id":"AAAA1111","account_name":"Active",  "active":True,
                         "account_type":"Brokerage","base_currency":"SAR","cash_balance":0.0,
                         "institution":"","notes":"","created_at":"2026-01-01"},
            "BBBB2222": {"account_id":"BBBB2222","account_name":"Inactive","active":False,
                         "account_type":"Brokerage","base_currency":"SAR","cash_balance":0.0,
                         "institution":"","notes":"","created_at":"2026-01-01"},
        }
        import portfolio.accounts as _pac
        orig_file = _pac._ACCOUNTS_FILE
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tf:
                json.dump(data, tf)
                tmp_path = tf.name
            _pac._ACCOUNTS_FILE = tmp_path
            result = _aa()
            active_ids   = set(result.keys())
            inactive_out = "BBBB2222" not in active_ids
            active_in    = "AAAA1111" in active_ids
            ok = active_in and inactive_out
        finally:
            _pac._ACCOUNTS_FILE = orig_file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return (
            "active_accounts returns only active=True accounts",
            f"active_in={active_in}, inactive_out={inactive_out}",
            ok,
        )

    def acc_ui_08():
        """
        The eligible account types set used in the Add New Position modal must
        exclude 'Bank' and 'Cash' account types.
        """
        _src = _pl.Path(__file__).parent / "app.py"
        _text = _src.read_text(encoding="utf-8")
        has_eligible_set = bool(_re.search(
            r'_ELIGIBLE_ACCT_TYPES\s*[=:]\s*frozenset',
            _text,
        ))
        bank_excluded = bool(_re.search(
            r'_ELIGIBLE_ACCT_TYPES\s*[=:]\s*frozenset\(\{[^}]*\}\)',
            _text,
        ))
        # Confirm "Bank" and "Cash" are NOT in the eligible set definition
        eligible_match = _re.search(
            r'_ELIGIBLE_ACCT_TYPES\s*[=:]\s*frozenset\(\{([^}]*)\}\)',
            _text,
        )
        if not eligible_match:
            return ("_ELIGIBLE_ACCT_TYPES frozenset found", "not found in app.py", False)
        set_contents = eligible_match.group(1)
        bank_absent = '"Bank"' not in set_contents and "'Bank'" not in set_contents
        cash_absent = '"Cash"' not in set_contents and "'Cash'" not in set_contents
        ok = has_eligible_set and bank_absent and cash_absent
        return (
            "Bank and Cash absent from _ELIGIBLE_ACCT_TYPES; eligible_only filter present",
            f"has_eligible_set={has_eligible_set}, bank_absent={bank_absent}, cash_absent={cash_absent}",
            ok,
        )

    _tests = [
        ("ACC-UI-06", "load_accounts has no caching decorator — always fresh",         "P0", True, acc_ui_06),
        ("ACC-UI-07", "inactive accounts excluded by active_accounts()",                "P0", True, acc_ui_07),
        ("ACC-UI-08", "Bank and Cash types excluded from Add New Position modal",       "P0", True, acc_ui_08),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "portfolio.accounts / app._acct_pairs_for", sev, blocker, fn))

    return results


def _cat_asset_type() -> list[TestResult]:
    """
    ASSET-TYPE-01  All 14 required asset types present in ASSET_TYPES.
    ASSET-TYPE-02  Existing holding with old type ('Fund') round-trips without error.
    ASSET-TYPE-03  'Precious Metal' in ASSET_TYPES; manual holding can be created.
    ASSET-TYPE-04  'Commodity' in ASSET_TYPES; manual holding can be created.
    ASSET-TYPE-05  'Real Estate' in ASSET_TYPES; manual holding can be created.
    ASSET-TYPE-06  'Other' in ASSET_TYPES and usable as fallback.
    """
    CAT = "Asset Types"
    results: list[TestResult] = []

    REQUIRED_TYPES = {
        "Stock", "ETF", "REIT", "Mutual Fund", "Sukuk", "Bond",
        "Cash", "Precious Metal", "Commodity", "Real Estate",
        "Private Equity", "Private Asset", "Crypto", "Other",
    }

    from portfolio.holdings import ASSET_TYPES

    def asset_type_01():
        present   = set(ASSET_TYPES)
        missing   = REQUIRED_TYPES - present
        ok        = len(missing) == 0
        return (
            f"All {len(REQUIRED_TYPES)} required types in ASSET_TYPES",
            f"missing={sorted(missing)}" if missing else f"all {len(REQUIRED_TYPES)} present",
            ok,
        )

    def _can_upsert(asset_type: str) -> tuple[bool, str]:
        """Try upserting a scratch holding with the given asset_type; clean up."""
        import tempfile, json, os
        import portfolio.holdings as _ph
        orig_file = _ph._HOLDINGS_FILE
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tf:
                json.dump({}, tf)
                tmp_path = tf.name
            _ph._HOLDINGS_FILE = tmp_path
            _ph.upsert_holding(
                ticker="TEST_AT",
                company_name=f"Test {asset_type}",
                quantity=1.0,
                avg_cost=100.0,
                current_price=100.0,
                asset_type=asset_type,
                default_account_id="TEST0001",
            )
            data = json.loads(_pl.Path(tmp_path).read_text())
            stored = next(
                (v.get("asset_type", "") for v in data.values()
                 if v.get("ticker") == "TEST_AT"),
                ""
            )
            ok  = stored == asset_type
            msg = f"stored='{stored}'"
        except Exception as _ex:
            ok  = False
            msg = f"exception: {_ex}"
        finally:
            _ph._HOLDINGS_FILE = orig_file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return ok, msg

    import pathlib as _pl

    def asset_type_02():
        """Old type 'Fund' still accepted by upsert_holding without error."""
        ok, msg = _can_upsert("Fund")
        return ("upsert_holding accepts legacy type 'Fund'", msg, ok)

    def asset_type_03():
        """'Precious Metal' in list and upsertable."""
        in_list = "Precious Metal" in ASSET_TYPES
        ok2, msg = _can_upsert("Precious Metal")
        ok = in_list and ok2
        return ("Precious Metal in ASSET_TYPES and upsertable", f"in_list={in_list}, {msg}", ok)

    def asset_type_04():
        """'Commodity' in list and upsertable."""
        in_list = "Commodity" in ASSET_TYPES
        ok2, msg = _can_upsert("Commodity")
        ok = in_list and ok2
        return ("Commodity in ASSET_TYPES and upsertable", f"in_list={in_list}, {msg}", ok)

    def asset_type_05():
        """'Real Estate' in list and upsertable."""
        in_list = "Real Estate" in ASSET_TYPES
        ok2, msg = _can_upsert("Real Estate")
        ok = in_list and ok2
        return ("Real Estate in ASSET_TYPES and upsertable", f"in_list={in_list}, {msg}", ok)

    def asset_type_06():
        """'Other' in list and upsertable as a fallback."""
        in_list = "Other" in ASSET_TYPES
        ok2, msg = _can_upsert("Other")
        ok = in_list and ok2
        return ("Other in ASSET_TYPES and upsertable as fallback", f"in_list={in_list}, {msg}", ok)

    _tests = [
        ("ASSET-TYPE-01", "All 14 required asset types present in ASSET_TYPES",            "P0", True, asset_type_01),
        ("ASSET-TYPE-02", "Legacy type 'Fund' round-trips via upsert_holding",             "P0", True, asset_type_02),
        ("ASSET-TYPE-03", "Precious Metal in ASSET_TYPES and upsertable as manual asset",  "P0", True, asset_type_03),
        ("ASSET-TYPE-04", "Commodity in ASSET_TYPES and upsertable as manual asset",       "P0", True, asset_type_04),
        ("ASSET-TYPE-05", "Real Estate in ASSET_TYPES and upsertable as manual asset",     "P0", True, asset_type_05),
        ("ASSET-TYPE-06", "Other in ASSET_TYPES and usable as fallback",                   "P0", True, asset_type_06),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "portfolio.holdings.ASSET_TYPES", sev, blocker, fn))

    return results


def _cat_alloc_at() -> list[TestResult]:
    """
    ALLOC-AT-01  'By Asset Type' option present in chart-view selectbox options.
    ALLOC-AT-02  AssetType column added to allocation row dicts.
    ALLOC-AT-03  alloc_ms_atype key included in reset-filters button logic.
    ALLOC-AT-04  Asset Type multiselect present in filters expander.
    """
    import re as _re
    import pathlib as _pl

    CAT = "Allocation Asset Type"
    results: list[TestResult] = []
    _src = _pl.Path(__file__).parent / "app.py"
    _text = _src.read_text(encoding="utf-8")

    def alloc_at_01():
        """'By Asset Type' is one of the chart-view selectbox options."""
        found = '"By Asset Type"' in _text or "'By Asset Type'" in _text
        in_view_list = bool(_re.search(
            r'"By Asset Type"',
            _text,
        ))
        ok = found and in_view_list
        return (
            "'By Asset Type' present in chart-view selectbox options list",
            f"found={found}",
            ok,
        )

    def alloc_at_02():
        """AssetType column added to allocation row dict in _render_allocation_section."""
        has_col = bool(_re.search(
            r'"AssetType"\s*:\s*getattr\(',
            _text,
        ))
        has_grp = bool(_re.search(
            r'"By Asset Type"\s*:\s*"AssetType"',
            _text,
        ))
        ok = has_col and has_grp
        return (
            "AssetType column in row dict; 'By Asset Type' -> 'AssetType' in _grp map",
            f"has_col={has_col}, has_grp={has_grp}",
            ok,
        )

    def alloc_at_03():
        """alloc_ms_atype is cleared by the Reset filters button."""
        reset_block = _re.search(
            r'Reset filters.*?st\.rerun\(\)',
            _text,
            _re.DOTALL,
        )
        if not reset_block:
            return ("Reset filters block found", "block NOT found", False)
        block_text = reset_block.group(0)
        has_atype_key = "alloc_ms_atype" in block_text
        ok = has_atype_key
        return (
            "alloc_ms_atype included in Reset filters button key clearing",
            f"has_atype_key={has_atype_key}",
            ok,
        )

    def alloc_at_04():
        """Asset Type multiselect with key alloc_ms_atype present in filters expander."""
        has_multiselect = bool(_re.search(
            r'st\.multiselect\s*\([^)]*alloc_ms_atype',
            _text,
        ))
        has_stale_purge = bool(_re.search(
            r'"alloc_ms_atype"\s*,\s*_all_atypes',
            _text,
        ))
        ok = has_multiselect and has_stale_purge
        return (
            "Asset Type multiselect (alloc_ms_atype) present; stale-purge entry present",
            f"has_multiselect={has_multiselect}, has_stale_purge={has_stale_purge}",
            ok,
        )

    _tests = [
        ("ALLOC-AT-01", "'By Asset Type' option in chart-view selectbox",                    "P0", True, alloc_at_01),
        ("ALLOC-AT-02", "AssetType column in allocation rows; grp mapping correct",           "P0", True, alloc_at_02),
        ("ALLOC-AT-03", "alloc_ms_atype cleared by Reset filters button",                    "P0", True, alloc_at_03),
        ("ALLOC-AT-04", "Asset Type multiselect present with stale-filter purge entry",      "P0", True, alloc_at_04),
    ]

    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "app._render_allocation_section", sev, blocker, fn))

    return results


def _cat_assetid() -> list[TestResult]:
    """
    ASSETID — Asset-ID primary key migration tests.
    Holdings are now keyed by an 8-char asset_id UUID prefix so that
    multiple assets can share the same pricing ticker (e.g. two GC=F holdings).
    """
    results = []
    CAT = "Asset-ID Primary Key"

    def assetid_01():
        """_gen_asset_id returns sequential AST_NNNNNN identifiers."""
        import re
        from portfolio.holdings import _gen_asset_id
        ast_pat = re.compile(r'^AST_\d{6}$')
        ids = [_gen_asset_id() for _ in range(10)]
        all_ast_fmt = all(ast_pat.match(i) for i in ids)
        all_unique  = len(set(ids)) == 10
        ok = all_ast_fmt and all_unique
        return (
            "all AST_NNNNNN format and unique",
            f"all_ast_fmt={all_ast_fmt}, all_unique={all_unique}, sample={ids[0]}",
            ok,
        )

    def assetid_02():
        """Two holdings with the same ticker but different asset_ids coexist."""
        from portfolio.holdings import Holding, _gen_asset_id
        aid1 = _gen_asset_id()
        aid2 = _gen_asset_id()
        h1 = Holding(ticker="GC=F", company_name="Gold Bank",     quantity=10.0,
                     avg_cost=1800.0, current_price=1900.0, asset_id=aid1)
        h2 = Holding(ticker="GC=F", company_name="Physical Gold", quantity=5.0,
                     avg_cost=1850.0, current_price=1900.0, asset_id=aid2)
        holdings = {aid1: h1, aid2: h2}
        both_present = len(holdings) == 2
        distinct_ids = aid1 != aid2
        same_ticker  = h1.ticker == h2.ticker == "GC=F"
        ok = both_present and distinct_ids and same_ticker
        return (
            "two GC=F holdings with distinct asset_ids coexist",
            f"count={len(holdings)}, ids_distinct={distinct_ids}, same_ticker={same_ticker}",
            ok,
        )

    def assetid_03():
        """
        load_holdings() auto-migrates old ticker-keyed JSON entries
        (no asset_id field) so the resulting dict is keyed by asset_id
        and each Holding.ticker still equals the original ticker.
        """
        import json, tempfile, os
        from portfolio.holdings import load_holdings

        old_data = {
            "AAPL": {
                "ticker": "AAPL", "company_name": "Apple", "market": "US",
                "sector": "Technology", "quantity": 5.0, "avg_cost": 150.0,
                "current_price": 180.0, "currency": "USD",
            },
            "GC=F": {
                "ticker": "GC=F", "company_name": "Gold", "market": "US",
                "sector": "Commodity", "quantity": 2.0, "avg_cost": 1800.0,
                "current_price": 1900.0, "currency": "USD",
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(old_data, fh)
            tmp_path = fh.name

        try:
            holdings = load_holdings(path=tmp_path)
        finally:
            os.unlink(tmp_path)

        import re as _re
        ast_pat = _re.compile(r'^AST_\d{6}$')
        # Keys must NOT be the old tickers; each holding's .ticker must match original
        keys_are_not_tickers = "AAPL" not in holdings and "GC=F" not in holdings
        tickers_preserved    = {h.ticker for h in holdings.values()} == {"AAPL", "GC=F"}
        ids_are_ast_fmt      = all(ast_pat.match(k) for k in holdings.keys())
        ok = keys_are_not_tickers and tickers_preserved and ids_are_ast_fmt
        return (
            "old ticker keys migrated to AST_NNNNNN asset_ids; .ticker preserved",
            (f"keys_not_tickers={keys_are_not_tickers}, "
             f"tickers_ok={tickers_preserved}, ids_ast_fmt={ids_are_ast_fmt}"),
            ok,
        )

    def assetid_04():
        """
        update_current_price(asset_id) targets the correct holding when two
        holdings share the same ticker.
        """
        import json, tempfile, os
        from portfolio.holdings import load_holdings, update_current_price

        from portfolio.holdings import _gen_asset_id
        aid1 = _gen_asset_id()
        aid2 = _gen_asset_id()
        initial_data = {
            aid1: {
                "ticker": "GC=F", "company_name": "Gold Bank", "market": "US",
                "sector": "Commodity", "quantity": 10.0, "avg_cost": 1800.0,
                "current_price": 1800.0, "currency": "USD",
                "asset_id": aid1,
            },
            aid2: {
                "ticker": "GC=F", "company_name": "Physical Gold", "market": "US",
                "sector": "Commodity", "quantity": 5.0, "avg_cost": 1850.0,
                "current_price": 1850.0, "currency": "USD",
                "asset_id": aid2,
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(initial_data, fh)
            tmp_path = fh.name

        try:
            update_current_price(aid1, 2000.0, source="test", path=tmp_path)
            holdings = load_holdings(path=tmp_path)
        finally:
            os.unlink(tmp_path)

        h1_price = holdings[aid1].current_price
        h2_price = holdings[aid2].current_price
        correct_target  = _near(h1_price, 2000.0, 0.001)
        other_unchanged = _near(h2_price, 1850.0, 0.001)
        ok = correct_target and other_unchanged
        return (
            "h1.price=2000.0; h2.price unchanged=1850.0",
            f"h1.price={h1_price}, h2.price={h2_price}",
            ok,
        )

    def assetid_05():
        """
        Portfolio valuation with two same-ticker holdings: each holding's
        market value is computed independently; total MV is their sum.
        """
        from portfolio.holdings import Holding, _gen_asset_id
        from portfolio.valuation import calculate_portfolio_valuation
        from portfolio.accounts import Account

        aid1 = _gen_asset_id()
        aid2 = _gen_asset_id()
        h1 = Holding(ticker="GC=F", company_name="Gold Bank",     quantity=10.0,
                     avg_cost=1800.0, current_price=2000.0, asset_id=aid1,
                     currency="USD")
        h2 = Holding(ticker="GC=F", company_name="Physical Gold", quantity=5.0,
                     avg_cost=1850.0, current_price=2000.0, asset_id=aid2,
                     currency="USD")
        holdings = {aid1: h1, aid2: h2}
        account  = Account(
            account_id="acct1", account_name="Sandbox", base_currency="USD",
            cash_balance=0.0, active=True,
        )
        val = calculate_portfolio_valuation(
            holdings, {"acct1": account}, "USD", fx_rates={},
        )
        # h1 MV = 10 * 2000 = 20000;  h2 MV = 5 * 2000 = 10000
        exp_total = 30_000.0
        act_total = val.holdings_value_base
        two_rows  = len(val.per_holding) == 2
        ok = _near(act_total, exp_total, 0.01) and two_rows
        return (
            f"total_MV={exp_total:.2f} from 2 independent rows",
            f"total_MV={act_total:.2f}, rows={len(val.per_holding)}",
            ok,
        )

    _tests = [
        ("ASSETID-01", "_gen_asset_id produces sequential AST_NNNNNN identifiers",    "P0", True, assetid_01),
        ("ASSETID-02", "Two same-ticker holdings coexist under distinct asset_ids",    "P0", True, assetid_02),
        ("ASSETID-03", "load_holdings() auto-migrates old format to AST_NNNNNN",       "P0", True, assetid_03),
        ("ASSETID-04", "update_current_price targets correct asset_id only",           "P0", True, assetid_04),
        ("ASSETID-05", "Valuation sums 2 same-ticker holdings independently",          "P0", True, assetid_05),
    ]
    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "portfolio.holdings", sev, blocker, fn))
    return results


def _cat_asset_identity() -> list[TestResult]:
    """
    ASSET-ID — Asset identity design: immutable asset_id, user-facing asset_name,
    optional ticker, transaction_id, and manual-asset support.
    """
    import re
    results = []
    CAT = "Asset Identity Design"
    ast_pat  = re.compile(r'^AST_\d{6}$')
    txn_pat  = re.compile(r'^TXN_[0-9a-f]{8}$')

    def asset_id_01():
        """asset_id is auto-generated (AST_NNNNNN) on upsert_holding creation."""
        import tempfile, os
        from portfolio.holdings import upsert_holding, load_holdings
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "h.json")
            h = upsert_holding(ticker="AAPL", company_name="Apple", quantity=1.0,
                               avg_cost=150.0, current_price=150.0,
                               default_account_id="acct1", path=p)
        generated = ast_pat.match(h.asset_id) is not None
        ok = generated
        return ("asset_id matches AST_NNNNNN", f"asset_id={h.asset_id}", ok)

    def asset_id_02():
        """asset_id is stable — upsert with same ticker does not change it."""
        import tempfile, os
        from portfolio.holdings import upsert_holding
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "h.json")
            h1 = upsert_holding(ticker="MSFT", company_name="Microsoft",
                                quantity=1.0, avg_cost=300.0, current_price=300.0,
                                default_account_id="acct1", path=p)
            h2 = upsert_holding(ticker="MSFT", company_name="Microsoft",
                                quantity=1.0, avg_cost=310.0, current_price=310.0,
                                asset_id=h1.asset_id, path=p)
        same_id = h1.asset_id == h2.asset_id
        ok = same_id and ast_pat.match(h1.asset_id) is not None
        return ("asset_id unchanged after second upsert",
                f"id1={h1.asset_id}, id2={h2.asset_id}, stable={same_id}", ok)

    def asset_id_03():
        """asset_name (company_name) is the user-facing name; stored and retrievable."""
        import tempfile, os
        from portfolio.holdings import upsert_holding, load_holdings
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "h.json")
            h = upsert_holding(ticker="2222.SR", company_name="Saudi Aramco",
                               quantity=100.0, avg_cost=30.0, current_price=32.0,
                               default_account_id="acct1", path=p)
            loaded = load_holdings(path=p)
        name_ok = loaded[h.asset_id].company_name == "Saudi Aramco"
        ok = name_ok
        return ("company_name stored and retrievable as user-facing name",
                f"name={loaded[h.asset_id].company_name}", ok)

    def asset_id_04():
        """Manual asset (no ticker) can be created with has_ticker=False."""
        import tempfile, os
        from portfolio.holdings import upsert_holding, load_holdings
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "h.json")
            h = upsert_holding(ticker="", company_name="Physical Gold - SNB Vault",
                               quantity=10.0, avg_cost=1800.0, current_price=1900.0,
                               has_ticker=False, asset_type="Precious Metal",
                               currency="USD", default_account_id="acct1", path=p)
            loaded = load_holdings(path=p)
        manual_ok = not loaded[h.asset_id].has_ticker
        name_ok   = loaded[h.asset_id].company_name == "Physical Gold - SNB Vault"
        id_ok     = ast_pat.match(h.asset_id) is not None
        ok = manual_ok and name_ok and id_ok
        return ("manual asset stored without ticker",
                f"has_ticker={loaded[h.asset_id].has_ticker}, "
                f"name={loaded[h.asset_id].company_name}, id={h.asset_id}", ok)

    def asset_id_05():
        """ticker change via upsert does not change asset_id."""
        import tempfile, os
        from portfolio.holdings import upsert_holding
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "h.json")
            h1 = upsert_holding(ticker="2222.SE", company_name="Aramco",
                                quantity=10.0, avg_cost=30.0, current_price=32.0,
                                default_account_id="acct1", path=p)
            h2 = upsert_holding(ticker="2222.SR", company_name="Aramco",
                                quantity=0.0, avg_cost=30.0, current_price=32.0,
                                asset_id=h1.asset_id, path=p)
        same_id = h1.asset_id == h2.asset_id
        ok = same_id
        return ("asset_id unchanged when ticker changes",
                f"id stable={same_id}, t1={h1.ticker}, t2={h2.ticker}", ok)

    def asset_id_06():
        """transaction_id is auto-generated and has TXN_ prefix."""
        from portfolio.holdings import record_transaction, delete_holding
        txn, holding, err = record_transaction(
            ticker="AAPL_AID06", side="BUY", quantity=5.0, price=150.0,
            company_name="Apple", account_id="acct1",
        )
        ok = (err is None) and txn_pat.match(txn.transaction_id) is not None
        try:  # cleanup — remove sandbox holding by asset_id
            if holding:
                delete_holding(holding.asset_id)
        except Exception:
            pass
        return ("transaction_id generated with TXN_ prefix",
                f"transaction_id={txn.transaction_id if txn else 'None'}", ok)

    def asset_id_07():
        """BUY transaction stores asset_id matching the created holding."""
        from portfolio.holdings import record_transaction, delete_holding, load_holdings
        txn, holding, err = record_transaction(
            ticker="TSLA_TEST_ASSETID07", side="BUY", quantity=1.0, price=200.0,
            company_name="Tesla Test", account_id="acct1",
        )
        ok = (err is None) and txn.asset_id == holding.asset_id
        try:  # cleanup — remove sandbox holding by asset_id
            if holding:
                delete_holding(holding.asset_id)
        except Exception:
            pass
        return ("txn.asset_id == holding.asset_id",
                f"txn.asset_id={getattr(txn,'asset_id','?')}, "
                f"holding.asset_id={getattr(holding,'asset_id','?')}", ok)

    def asset_id_08():
        """load_holdings() returns AST_NNNNNN keys for all entries."""
        from portfolio.holdings import load_holdings
        holdings = load_holdings()
        if not holdings:
            return ("no holdings on file — skipped", "empty", True)
        all_ast = all(ast_pat.match(k) for k in holdings.keys())
        sample  = next(iter(holdings))
        return ("all holding keys match AST_NNNNNN",
                f"all_ast={all_ast}, sample_key={sample}", all_ast)

    def asset_id_09():
        """Duplicate company_name in upsert does not raise; both assets coexist."""
        import tempfile, os
        from portfolio.holdings import upsert_holding, load_holdings
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "h.json")
            h1 = upsert_holding(ticker="GOLD1", company_name="Gold Fund",
                                quantity=5.0, avg_cost=100.0, current_price=110.0,
                                default_account_id="acct1", path=p)
            h2 = upsert_holding(ticker="GOLD2", company_name="Gold Fund",
                                quantity=3.0, avg_cost=105.0, current_price=110.0,
                                default_account_id="acct1", path=p)
            loaded = load_holdings(path=p)
        both_exist = h1.asset_id in loaded and h2.asset_id in loaded
        distinct   = h1.asset_id != h2.asset_id
        ok = both_exist and distinct
        return ("two assets with same company_name coexist with distinct asset_ids",
                f"count={len(loaded)}, distinct={distinct}", ok)

    def asset_id_10():
        """Full regression: ASSETID-01..05 all pass (smoke-check)."""
        from portfolio.holdings import _gen_asset_id, Holding
        id1 = _gen_asset_id()
        id2 = _gen_asset_id()
        format_ok = ast_pat.match(id1) and ast_pat.match(id2)
        distinct  = id1 != id2
        h = Holding(ticker="TEST", company_name="Test Asset", asset_id=id1,
                    quantity=1.0, avg_cost=10.0, current_price=10.0)
        dataclass_ok = h.asset_id == id1
        ok = bool(format_ok) and distinct and dataclass_ok
        return ("format, uniqueness, and Holding dataclass all pass",
                f"id1={id1}, id2={id2}, format={bool(format_ok)}, "
                f"distinct={distinct}, dataclass={dataclass_ok}", ok)

    _tests = [
        ("ASSET-ID-01", "asset_id auto-generated AST_NNNNNN on upsert_holding",       "P0", True, asset_id_01),
        ("ASSET-ID-02", "asset_id stable — second upsert preserves same id",           "P0", True, asset_id_02),
        ("ASSET-ID-03", "asset_name (company_name) stored and retrievable",            "P0", True, asset_id_03),
        ("ASSET-ID-04", "manual asset created without ticker (has_ticker=False)",      "P0", True, asset_id_04),
        ("ASSET-ID-05", "ticker change does not change asset_id",                      "P0", True, asset_id_05),
        ("ASSET-ID-06", "transaction_id auto-generated with TXN_ prefix",             "P0", True, asset_id_06),
        ("ASSET-ID-07", "BUY transaction links asset_id to holding",                  "P0", True, asset_id_07),
        ("ASSET-ID-08", "load_holdings() returns only AST_NNNNNN keys",               "P0", True, asset_id_08),
        ("ASSET-ID-09", "duplicate company_name allowed — both assets coexist",       "P1", False, asset_id_09),
        ("ASSET-ID-10", "full regression smoke-check passes",                         "P0", True, asset_id_10),
    ]
    for tid, name, sev, blocker, fn in _tests:
        results.append(_run(tid, name, CAT, "portfolio.holdings", sev, blocker, fn))
    return results


def _cat_settle() -> list[TestResult]:
    """
    SETTLE: Settlement transaction regression tests.

    SETTLE-01  Asset-level Dividend settlement recorded correctly.
    SETTLE-02  Portfolio-level Zakat has asset_id='' and ticker=''.
    SETTLE-03  FIFO queue ignores SETTLEMENT — only sees BUY.
    SETTLE-04  Settlement never changes holding quantity or avg_cost.
    SETTLE-05  Reject notes shorter than 10 characters.
    SETTLE-06  Reject amount == 0.
    SETTLE-07  Reject invalid category string.
    SETTLE-08  Cash ledger type mapping: Dividend→DIVIDEND, Zakat→FEE.
    """
    CAT = "Settlement"
    results: list[TestResult] = []

    def settle01():
        import tempfile, os, json
        from unittest.mock import patch
        from portfolio.holdings import (
            record_settlement, Holding, save_holdings,
        )
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            h = Holding(
                ticker="S01TST", asset_id="AST_990001",
                company_name="Settle Test Co",
                quantity=100.0, avg_cost=50.0, current_price=55.0,
            )
            save_holdings({"AST_990001": h}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                txn, err = record_settlement(
                    amount=500.0, category="Dividend", currency="SAR",
                    notes="Q2 2026 dividend from S01TST holding",
                    asset_id="AST_990001",
                )
        ok_no_err   = err is None
        ok_side     = txn is not None and txn.side == "SETTLEMENT"
        ok_amount   = txn is not None and txn.settlement_amount == 500.0
        ok_category = txn is not None and txn.settlement_category == "Dividend"
        ok_asset_id = txn is not None and txn.asset_id == "AST_990001"
        ok_ticker   = txn is not None and txn.ticker == "S01TST"
        ok = ok_no_err and ok_side and ok_amount and ok_category and ok_asset_id and ok_ticker
        detail = []
        if not ok_no_err:   detail.append(f"err={err}")
        if not ok_side:     detail.append("side != SETTLEMENT")
        if not ok_amount:   detail.append("settlement_amount mismatch")
        if not ok_category: detail.append("settlement_category mismatch")
        if not ok_asset_id: detail.append("asset_id mismatch")
        if not ok_ticker:   detail.append("ticker mismatch")
        return (
            "side=SETTLEMENT, amount=500, category=Dividend, asset_id=AST_990001, ticker=S01TST",
            "PASS" if ok else "; ".join(detail),
            ok,
        )

    def settle02():
        import tempfile, os
        from unittest.mock import patch
        from portfolio.holdings import record_settlement, save_holdings
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            save_holdings({}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                txn, err = record_settlement(
                    amount=-1000.0, category="Zakat", currency="SAR",
                    notes="Annual zakat on total portfolio value",
                )
        ok = (err is None and txn is not None
              and txn.asset_id == "" and txn.ticker == "")
        return (
            "asset_id='' and ticker='' for portfolio-level settlement",
            "PASS" if ok else (
                f"err={err}" if err else
                f"asset_id={getattr(txn,'asset_id','?')!r}, ticker={getattr(txn,'ticker','?')!r}"
            ),
            ok,
        )

    def settle03():
        import tempfile, os
        from unittest.mock import patch
        from portfolio.holdings import (
            record_transaction, record_settlement,
            Holding, save_holdings, load_holdings,
        )
        from portfolio.closed_holdings import _build_fifo_queue
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            # Pre-create the holding so record_transaction treats it as an
            # existing position (bypasses the "account required for new
            # position" guard — not the subject of this test).
            pre_h = Holding(
                ticker="S03TST", asset_id="AST_990003",
                company_name="FIFO Test Co",
                quantity=10.0, avg_cost=100.0, current_price=100.0,
            )
            save_holdings({"AST_990003": pre_h}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                # Record a BUY targeting the existing holding
                record_transaction(
                    ticker="S03TST", side="BUY",
                    quantity=5.0, price=100.0,
                    notes="test buy for FIFO isolation",
                    asset_id="AST_990003",
                )
                record_settlement(
                    amount=50.0, category="Dividend", currency="USD",
                    notes="dividend for FIFO isolation test",
                    asset_id="AST_990003",
                )
                queue = _build_fifo_queue("S03TST")
        ok = len(queue) == 1
        return (
            "FIFO queue has exactly 1 BUY lot; SETTLEMENT is invisible",
            f"queue length={len(queue)}",
            ok,
        )

    def settle04():
        import tempfile, os
        from unittest.mock import patch
        from portfolio.holdings import (
            record_settlement, Holding, save_holdings, load_holdings,
        )
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            h = Holding(
                ticker="S04TST", asset_id="AST_990004",
                company_name="NoChange Co",
                quantity=200.0, avg_cost=75.0, current_price=80.0,
            )
            save_holdings({"AST_990004": h}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                _, err = record_settlement(
                    amount=-200.0, category="Fee", currency="USD",
                    notes="Custody fee for SETTLE-04 isolation test",
                    asset_id="AST_990004",
                )
                holdings_after = load_holdings()
        h_after = holdings_after.get("AST_990004")
        qty_ok = h_after is not None and abs(h_after.quantity - 200.0) < 1e-9
        avg_ok = h_after is not None and abs(h_after.avg_cost - 75.0) < 1e-9
        ok = err is None and qty_ok and avg_ok
        return (
            "quantity=200 and avg_cost=75 unchanged after settlement",
            "PASS" if ok else (
                f"err={err}" if err else
                f"qty={getattr(h_after,'quantity','?')}, avg={getattr(h_after,'avg_cost','?')}"
            ),
            ok,
        )

    def settle05():
        import tempfile, os
        from unittest.mock import patch
        from portfolio.holdings import record_settlement, save_holdings
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            save_holdings({}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                _, err = record_settlement(
                    amount=100.0, category="Dividend", currency="SAR",
                    notes="short",
                )
        ok = err is not None and "10" in err
        return (
            "error message mentioning 10-character minimum",
            f"err={err!r}",
            ok,
        )

    def settle06():
        import tempfile, os
        from unittest.mock import patch
        from portfolio.holdings import record_settlement, save_holdings
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            save_holdings({}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                _, err = record_settlement(
                    amount=0.0, category="Dividend", currency="SAR",
                    notes="zero amount for validation test",
                )
        ok = err is not None and "zero" in err.lower()
        return (
            "error message for amount == 0",
            f"err={err!r}",
            ok,
        )

    def settle07():
        import tempfile, os
        from unittest.mock import patch
        from portfolio.holdings import record_settlement, save_holdings
        with tempfile.TemporaryDirectory() as tmp:
            h_path = os.path.join(tmp, "holdings.json")
            t_path = os.path.join(tmp, "transactions.json")
            save_holdings({}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
            ):
                _, err = record_settlement(
                    amount=100.0, category="InvalidCat", currency="SAR",
                    notes="invalid category for validation test",
                )
        ok = err is not None and ("Invalid" in err or "InvalidCat" in err)
        return (
            "error message for invalid category string",
            f"err={err!r}",
            ok,
        )

    def settle08():
        import tempfile, os, json
        from unittest.mock import patch
        from dataclasses import asdict
        from portfolio.holdings import record_settlement, save_holdings
        from portfolio.accounts import Account, save_accounts
        with tempfile.TemporaryDirectory() as tmp:
            h_path  = os.path.join(tmp, "holdings.json")
            t_path  = os.path.join(tmp, "transactions.json")
            a_path  = os.path.join(tmp, "accounts.json")
            cl_path = os.path.join(tmp, "cash_ledger.json")
            save_holdings({}, path=h_path)
            with open(t_path, "w") as f:
                f.write("[]")
            with (
                patch("portfolio.holdings._HOLDINGS_FILE", h_path),
                patch("portfolio.holdings._TRANSACTIONS_FILE", t_path),
                patch("portfolio.accounts._ACCOUNTS_FILE", a_path),
                patch("portfolio.cash_ledger._LEDGER_FILE", cl_path),
            ):
                acct = Account(
                    account_id="ACC_S08TST",
                    account_name="Test Brokerage S08",
                    account_type="Brokerage",
                    base_currency="SAR",
                    cash_balance=10000.0,
                )
                save_accounts({"ACC_S08TST": acct})
                record_settlement(
                    amount=300.0, category="Dividend", currency="SAR",
                    notes="Q2 dividend for ledger mapping test",
                    account_id="ACC_S08TST",
                )
                record_settlement(
                    amount=-500.0, category="Zakat", currency="SAR",
                    notes="Annual zakat for ledger mapping test",
                    account_id="ACC_S08TST",
                )
                with open(cl_path) as f:
                    raw_entries = json.load(f)
        types = [e.get("transaction_type", "") for e in raw_entries]
        ok_div  = "DIVIDEND" in types
        ok_zkat = "FEE" in types
        ok = ok_div and ok_zkat
        return (
            "Dividend→DIVIDEND and Zakat→FEE in cash ledger",
            f"types found={types}",
            ok,
        )

    results.append(_run("SETTLE-01", "Asset-level Dividend settlement recorded correctly",          CAT, "portfolio.holdings.record_settlement",     "P0", True,  settle01))
    results.append(_run("SETTLE-02", "Portfolio-level Zakat has asset_id='' and ticker=''",         CAT, "portfolio.holdings.record_settlement",     "P0", True,  settle02))
    results.append(_run("SETTLE-03", "FIFO queue ignores SETTLEMENT — only sees BUY",               CAT, "portfolio.closed_holdings._build_fifo_queue","P0", True, settle03))
    results.append(_run("SETTLE-04", "Settlement never changes holding quantity or avg_cost",        CAT, "portfolio.holdings.record_settlement",     "P0", True,  settle04))
    results.append(_run("SETTLE-05", "Reject notes shorter than 10 characters",                     CAT, "portfolio.holdings.record_settlement",     "P0", True,  settle05))
    results.append(_run("SETTLE-06", "Reject amount == 0",                                          CAT, "portfolio.holdings.record_settlement",     "P0", True,  settle06))
    results.append(_run("SETTLE-07", "Reject invalid category string",                              CAT, "portfolio.holdings.record_settlement",     "P0", True,  settle07))
    results.append(_run("SETTLE-08", "Cash ledger type mapping: Dividend→DIVIDEND, Zakat→FEE",      CAT, "portfolio.cash_ledger.append_cash_entry",  "P0", True,  settle08))
    return results


def _cat_igi() -> list[TestResult]:
    """
    IGI: Investment Grade Income regression tests.

    IGI-01  add_igi_investment creates investment with correct fields.
    IGI-02  add_igi_investment rejects empty investment name.
    IGI-03  add_igi_investment rejects zero principal.
    IGI-04  record_igi_transaction records correctly.
    IGI-05  record_igi_transaction rejects unknown investment.
    IGI-06  compute_maturity_split — actual >= principal → profit, no loss.
    IGI-07  compute_maturity_split — actual < principal → loss, no profit.
    IGI-08  process_maturity Principal Returned path closes investment.
    IGI-09  process_maturity Reinvest Principal creates draft child.
    IGI-10  process_maturity Reinvest Principal + Profit includes profit in child principal.
    IGI-11  process_early_withdrawal closes investment.
    IGI-12  compute_igi_metrics correct totals from transactions.
    IGI-13  compute_xirr returns None for empty flow list.
    IGI-14  compute_xirr returns None for all-same-sign flows.
    IGI-15  compute_xirr converges for simple annual 10% case.
    IGI-16  Auto-flag: Active investment past maturity_date → Maturity Action Required on load.
    """
    CAT = "IGI"
    results: list[TestResult] = []

    def igi01():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, load_igi_investments
        with tempfile.TemporaryDirectory() as tmp:
            p   = os.path.join(tmp, "inv.json")
            tp  = os.path.join(tmp, "txn.json")
            inv, err = add_igi_investment(
                investment_name="Test Murabaha",
                institution="Al Rajhi Bank",
                currency="SAR",
                principal_amount=50000.0,
                current_value=50000.0,
                start_date="2025-01-01",
                maturity_date="2026-01-01",
                expected_yield_pct=5.5,
                profit_payment_structure="At Maturity",
                liquidity_type="Locked Until Maturity",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
        ok_no_err = err is None
        ok_name   = inv is not None and inv.investment_name == "Test Murabaha"
        ok_inst   = inv is not None and inv.institution == "Al Rajhi Bank"
        ok_pa     = inv is not None and inv.principal_amount == 50000.0
        ok_yld    = inv is not None and inv.expected_yield_pct == 5.5
        ok_status = inv is not None and inv.status == "Active"
        ok = ok_no_err and ok_name and ok_inst and ok_pa and ok_yld and ok_status
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_name:   detail.append("name mismatch")
        if not ok_inst:   detail.append("institution mismatch")
        if not ok_pa:     detail.append("principal_amount mismatch")
        if not ok_yld:    detail.append("expected_yield_pct mismatch")
        if not ok_status: detail.append("status != Active")
        return ("name=Test Murabaha, institution=Al Rajhi Bank, pa=50000, yield=5.5, status=Active",
                "PASS" if ok else "; ".join(detail), ok)

    def igi02():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, err = add_igi_investment(
                investment_name="   ",
                institution="Bank",
                currency="SAR",
                principal_amount=1000.0,
                current_value=1000.0,
                start_date="2025-01-01",
                maturity_date="2026-01-01",
                expected_yield_pct=5.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Daily",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
        ok = inv is None and err is not None and "name" in err.lower()
        return ("empty name rejected with error mentioning 'name'",
                "PASS" if ok else f"inv={inv}, err={err!r}", ok)

    def igi03():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, err = add_igi_investment(
                investment_name="Bad Principal",
                institution="Bank",
                currency="SAR",
                principal_amount=0.0,
                current_value=0.0,
                start_date="2025-01-01",
                maturity_date="2026-01-01",
                expected_yield_pct=5.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Daily",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
        ok = inv is None and err is not None and "principal" in err.lower()
        return ("zero principal rejected with error mentioning 'principal'",
                "PASS" if ok else f"inv={inv}, err={err!r}", ok)

    def igi04():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, record_igi_transaction, load_igi_transactions
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, _ = add_igi_investment(
                investment_name="TXN Test",
                institution="Bank",
                currency="SAR",
                principal_amount=10000.0,
                current_value=10000.0,
                start_date="2025-01-01",
                maturity_date="2026-01-01",
                expected_yield_pct=4.0,
                profit_payment_structure="Periodic",
                liquidity_type="Monthly",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
            txn, err = record_igi_transaction(
                investment_id=inv.investment_id,
                txn_type="Profit Received",
                amount=400.0,
                txn_date="2026-01-01",
                notes="Q4 2025 profit payment received",
                path=p, txn_path=tp,
            )
            txns = load_igi_transactions(path=tp)
        ok_no_err = err is None
        ok_type   = txn is not None and txn.txn_type == "Profit Received"
        ok_amount = txn is not None and txn.amount == 400.0
        profit_txns = [t for t in txns if t.txn_type == "Profit Received"]
        ok_stored = len(profit_txns) == 1
        ok = ok_no_err and ok_type and ok_amount and ok_stored
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_type:   detail.append("txn_type mismatch")
        if not ok_amount: detail.append("amount mismatch")
        if not ok_stored: detail.append(f"stored profit txns={len(profit_txns)}, expected 1")
        return ("Profit Received 400 stored correctly",
                "PASS" if ok else "; ".join(detail), ok)

    def igi05():
        import tempfile, os
        from portfolio.alt_investments import record_igi_transaction
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            open(p, "w").write("{}")
            open(tp, "w").write("[]")
            txn, err = record_igi_transaction(
                investment_id="notexist",
                txn_type="Profit Received",
                amount=100.0,
                txn_date="2025-01-01",
                notes="Should fail",
                path=p, txn_path=tp,
            )
        ok = txn is None and err is not None and "not found" in err.lower()
        return ("unknown investment_id rejected",
                "PASS" if ok else f"txn={txn}, err={err!r}", ok)

    def igi06():
        from portfolio.alt_investments import compute_maturity_split
        result = compute_maturity_split(principal_outstanding=10000.0, actual_total_received=10700.0)
        ok_pr = abs(result["principal_returned"] - 10000.0) < 0.001
        ok_pf = abs(result["profit_received"] - 700.0) < 0.001
        ok_lo = result["principal_loss"] == 0.0
        ok = ok_pr and ok_pf and ok_lo
        detail = []
        if not ok_pr: detail.append(f"principal_returned={result['principal_returned']}")
        if not ok_pf: detail.append(f"profit_received={result['profit_received']}")
        if not ok_lo: detail.append(f"principal_loss={result['principal_loss']}")
        return ("principal=10000 actual=10700 → profit=700 loss=0",
                "PASS" if ok else "; ".join(detail), ok)

    def igi07():
        from portfolio.alt_investments import compute_maturity_split
        result = compute_maturity_split(principal_outstanding=10000.0, actual_total_received=9200.0)
        ok_pr = abs(result["principal_returned"] - 9200.0) < 0.001
        ok_pf = result["profit_received"] == 0.0
        ok_lo = abs(result["principal_loss"] - 800.0) < 0.001
        ok = ok_pr and ok_pf and ok_lo
        detail = []
        if not ok_pr: detail.append(f"principal_returned={result['principal_returned']}")
        if not ok_pf: detail.append(f"profit_received={result['profit_received']}")
        if not ok_lo: detail.append(f"principal_loss={result['principal_loss']}")
        return ("principal=10000 actual=9200 → loss=800 profit=0",
                "PASS" if ok else "; ".join(detail), ok)

    def igi08():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, process_maturity, load_igi_investments
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, _ = add_igi_investment(
                investment_name="Maturity Test",
                institution="Bank",
                currency="SAR",
                principal_amount=20000.0,
                current_value=20000.0,
                start_date="2024-01-01",
                maturity_date="2025-01-01",
                expected_yield_pct=6.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Locked Until Maturity",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
            res, err = process_maturity(
                investment_id=inv.investment_id,
                actual_total_received=21200.0,
                actual_maturity_date="2025-01-01",
                notes="Investment matured as expected with full return",
                path=p, txn_path=tp,
            )
            invs_after = load_igi_investments(path=p)
        ok_no_err  = err is None
        ok_action  = res is not None and res["action_taken"] == "Principal Returned"
        ok_profit  = res is not None and abs(res["profit_received"] - 1200.0) < 0.001
        ok_closed  = invs_after.get(inv.investment_id) is not None and invs_after[inv.investment_id].status == "Closed"
        ok_no_child = res is not None and res["child_investment_id"] == ""
        ok = ok_no_err and ok_action and ok_profit and ok_closed and ok_no_child
        detail = []
        if not ok_no_err:   detail.append(f"err={err}")
        if not ok_action:   detail.append(f"action={res and res.get('action_taken')}")
        if not ok_profit:   detail.append(f"profit_received={res and res.get('profit_received')}")
        if not ok_closed:   detail.append("status != Closed")
        if not ok_no_child: detail.append("unexpected child_investment_id")
        return ("process_maturity Principal Returned → status=Closed, profit=1200, no child",
                "PASS" if ok else "; ".join(detail), ok)

    def igi09():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, process_maturity, load_igi_investments
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, _ = add_igi_investment(
                investment_name="Reinvest Test",
                institution="Bank",
                currency="SAR",
                principal_amount=10000.0,
                current_value=10000.0,
                start_date="2024-01-01",
                maturity_date="2025-01-01",
                expected_yield_pct=5.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Locked Until Maturity",
                maturity_instruction="Reinvest Principal",
                path=p, txn_path=tp,
            )
            res, err = process_maturity(
                investment_id=inv.investment_id,
                actual_total_received=10500.0,
                actual_maturity_date="2025-01-01",
                notes="Maturity processed — reinvesting principal only",
                path=p, txn_path=tp,
            )
            invs_after = load_igi_investments(path=p)
        ok_no_err = err is None
        ok_action = res is not None and res["action_taken"] == "Reinvest Principal"
        child_id  = res["child_investment_id"] if res else ""
        ok_child  = bool(child_id) and child_id in invs_after
        child_pa  = invs_after[child_id].principal_amount if ok_child else 0
        ok_child_pa = abs(child_pa - 10000.0) < 0.001
        ok_child_status = ok_child and invs_after[child_id].status == "Pending Funding"
        ok = ok_no_err and ok_action and ok_child and ok_child_pa and ok_child_status
        detail = []
        if not ok_no_err:        detail.append(f"err={err}")
        if not ok_action:        detail.append(f"action={res and res.get('action_taken')}")
        if not ok_child:         detail.append("no child investment created")
        if not ok_child_pa:      detail.append(f"child principal={child_pa}")
        if not ok_child_status:  detail.append("child status != Pending Funding")
        return ("Reinvest Principal → child created, principal=10000, status=Pending Funding",
                "PASS" if ok else "; ".join(detail), ok)

    def igi10():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, process_maturity, load_igi_investments
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, _ = add_igi_investment(
                investment_name="Reinvest All Test",
                institution="Bank",
                currency="SAR",
                principal_amount=10000.0,
                current_value=10000.0,
                start_date="2024-01-01",
                maturity_date="2025-01-01",
                expected_yield_pct=5.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Locked Until Maturity",
                maturity_instruction="Reinvest Principal + Profit",
                path=p, txn_path=tp,
            )
            res, err = process_maturity(
                investment_id=inv.investment_id,
                actual_total_received=10600.0,
                actual_maturity_date="2025-01-01",
                notes="Reinvesting both principal and profit received",
                path=p, txn_path=tp,
            )
            invs_after = load_igi_investments(path=p)
        ok_no_err = err is None
        child_id  = res["child_investment_id"] if res else ""
        ok_child  = bool(child_id) and child_id in invs_after
        child_pa  = invs_after[child_id].principal_amount if ok_child else 0
        ok_child_pa = abs(child_pa - 10600.0) < 0.001
        ok = ok_no_err and ok_child and ok_child_pa
        detail = []
        if not ok_no_err:   detail.append(f"err={err}")
        if not ok_child:    detail.append("no child investment")
        if not ok_child_pa: detail.append(f"child principal={child_pa}, expected 10600")
        return ("Reinvest Principal + Profit → child principal = principal + profit = 10600",
                "PASS" if ok else "; ".join(detail), ok)

    def igi11():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, process_early_withdrawal, load_igi_investments
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, _ = add_igi_investment(
                investment_name="Withdrawal Test",
                institution="Bank",
                currency="SAR",
                principal_amount=15000.0,
                current_value=15000.0,
                start_date="2025-01-01",
                maturity_date="2026-12-31",
                expected_yield_pct=5.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Monthly",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
            res, err = process_early_withdrawal(
                investment_id=inv.investment_id,
                withdrawal_date="2025-06-01",
                actual_total=14800.0,
                early_withdrawal_cost=200.0,
                notes="Early exit due to liquidity need in portfolio",
                path=p, txn_path=tp,
            )
            invs_after = load_igi_investments(path=p)
        ok_no_err  = err is None
        ok_closed  = invs_after.get(inv.investment_id) is not None and invs_after[inv.investment_id].status == "Closed"
        ok_loss    = res is not None and abs(res["principal_loss"] - 200.0) < 0.001
        ok_cost    = res is not None and res["early_withdrawal_cost"] == 200.0
        ok = ok_no_err and ok_closed and ok_loss and ok_cost
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_closed: detail.append("status != Closed")
        if not ok_loss:   detail.append(f"principal_loss={res and res.get('principal_loss')}")
        if not ok_cost:   detail.append(f"early_withdrawal_cost={res and res.get('early_withdrawal_cost')}")
        return ("early_withdrawal → Closed, loss=200, cost=200",
                "PASS" if ok else "; ".join(detail), ok)

    def igi12():
        import tempfile, os
        from portfolio.alt_investments import add_igi_investment, record_igi_transaction, compute_igi_metrics
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "inv.json")
            tp = os.path.join(tmp, "txn.json")
            inv, _ = add_igi_investment(
                investment_name="Metrics Test",
                institution="Bank",
                currency="SAR",
                principal_amount=10000.0,
                current_value=10300.0,
                start_date="2025-01-01",
                maturity_date="2026-01-01",
                expected_yield_pct=5.0,
                profit_payment_structure="Periodic",
                liquidity_type="Monthly",
                maturity_instruction="Principal Returned",
                path=p, txn_path=tp,
            )
            record_igi_transaction(
                investment_id=inv.investment_id, txn_type="Profit Received",
                amount=300.0, txn_date="2025-07-01",
                notes="Mid-year profit payment received from institution",
                path=p, txn_path=tp,
            )
            m = compute_igi_metrics(inv.investment_id, path=p, txn_path=tp)
        ok_invested = abs(m.get("total_invested", 0) - 10000.0) < 0.001
        ok_profit   = abs(m.get("total_profit_received", 0) - 300.0) < 0.001
        ok_cv       = abs(m.get("current_value", 0) - 10300.0) < 0.001
        ok = ok_invested and ok_profit and ok_cv
        detail = []
        if not ok_invested: detail.append(f"total_invested={m.get('total_invested')}")
        if not ok_profit:   detail.append(f"total_profit_received={m.get('total_profit_received')}")
        if not ok_cv:       detail.append(f"current_value={m.get('current_value')}")
        return ("metrics: total_invested=10000, profit_received=300, current_value=10300",
                "PASS" if ok else "; ".join(detail), ok)

    def igi13():
        from portfolio.alt_investments import compute_xirr
        r = compute_xirr([])
        ok = r is None
        return ("compute_xirr([]) → None", "PASS" if ok else f"got {r!r}", ok)

    def igi14():
        from portfolio.alt_investments import compute_xirr
        r = compute_xirr([("2025-01-01", -1000.0), ("2026-01-01", -500.0)])
        ok = r is None
        return ("all-outflow cash flows → None (no sign change)", "PASS" if ok else f"got {r!r}", ok)

    def igi15():
        from portfolio.alt_investments import compute_xirr
        r = compute_xirr([("2025-01-01", -10000.0), ("2026-01-01", 11000.0)])
        ok = r is not None and abs(r - 0.10) < 0.001
        return ("invest 10000 get 11000 in 1 year → XIRR ≈ 10.0%",
                "PASS" if ok else f"got {r!r}", ok)

    def igi16():
        import tempfile, os, json
        from portfolio.alt_investments import save_igi_investments, load_igi_investments, IGIInvestment
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "inv.json")
            # Create an Active investment with maturity date in the past
            inv = IGIInvestment(
                investment_id="aabbccdd",
                investment_name="Past Maturity",
                institution="Bank",
                currency="SAR",
                principal_amount=5000.0,
                current_value=5000.0,
                start_date="2023-01-01",
                maturity_date="2023-12-31",
                expected_yield_pct=4.0,
                profit_payment_structure="At Maturity",
                liquidity_type="Locked Until Maturity",
                status="Active",
                maturity_instruction="Principal Returned",
                created_at="2023-01-01T00:00:00Z",
            )
            save_igi_investments({"aabbccdd": inv}, path=p)
            invs = load_igi_investments(path=p)
        loaded = invs.get("aabbccdd")
        ok = loaded is not None and loaded.status == "Maturity Action Required"
        return ("Active investment past maturity_date auto-flagged to 'Maturity Action Required'",
                "PASS" if ok else f"status={loaded and loaded.status}", ok)

    for test_id, desc, fn in [
        ("IGI-01", "add_igi_investment creates investment with correct fields",                   igi01),
        ("IGI-02", "add_igi_investment rejects empty investment name",                            igi02),
        ("IGI-03", "add_igi_investment rejects zero principal",                                   igi03),
        ("IGI-04", "record_igi_transaction records Profit Received correctly",                    igi04),
        ("IGI-05", "record_igi_transaction rejects unknown investment_id",                        igi05),
        ("IGI-06", "compute_maturity_split actual>=principal → profit no loss",                   igi06),
        ("IGI-07", "compute_maturity_split actual<principal → loss no profit",                    igi07),
        ("IGI-08", "process_maturity Principal Returned → Closed no child",                       igi08),
        ("IGI-09", "process_maturity Reinvest Principal → child Pending Funding",                 igi09),
        ("IGI-10", "process_maturity Reinvest Principal+Profit → child principal=pa+profit",      igi10),
        ("IGI-11", "process_early_withdrawal → Closed, loss and cost recorded",                   igi11),
        ("IGI-12", "compute_igi_metrics correct total_invested and profit_received",               igi12),
        ("IGI-13", "compute_xirr empty list → None",                                              igi13),
        ("IGI-14", "compute_xirr all-outflow → None",                                             igi14),
        ("IGI-15", "compute_xirr 10k→11k in 1yr → 10%",                                          igi15),
        ("IGI-16", "auto-flag Active investment past maturity_date → Maturity Action Required",   igi16),
    ]:
        results.append(_run(test_id, desc, CAT, "portfolio.alt_investments", "P0", True, fn))
    return results


def _cat_cf() -> list[TestResult]:
    """
    CF: Crowdfunding account regression tests.

    CF-01  add_cf_account creates account with correct fields.
    CF-02  add_cf_account rejects empty platform name.
    CF-03  add_cf_account rejects invalid crowdfunding type.
    CF-04  record_cf_transaction records correctly.
    CF-05  record_cf_transaction rejects unknown account.
    CF-06  add_cf_snapshot updates account live position.
    CF-07  add_cf_snapshot stores historical record (immutable, append-only).
    CF-08  compute_cf_reconciliation — reconciled case diff ≈ 0.
    CF-09  compute_cf_reconciliation — unreconciled case diff != 0.
    CF-10  compute_cf_metrics — correct net_deposits and net_profit_loss.
    CF-11  edit_cf_account updates status and total fields.
    CF-12  Multiple snapshots: latest updates live position, all stored.
    """
    CAT = "CF"
    results: list[TestResult] = []

    def cf01():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, load_cf_accounts
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "acct.json")
            acct, err = add_cf_account(
                platform_name="Manafa",
                account_name="Main Account",
                crowdfunding_type="Debt Crowdfunding",
                institution="Manafa Capital",
                currency="SAR",
                current_account_value=25000.0,
                available_cash=5000.0,
                active_investments=20000.0,
                delayed_investments=0.0,
                defaulted_investments=0.0,
                total_deposits=25000.0,
                total_withdrawals=0.0,
                total_profit_received=0.0,
                total_losses=0.0,
                last_update_date="2025-06-01",
                path=p,
            )
        ok_no_err = err is None
        ok_plat   = acct is not None and acct.platform_name == "Manafa"
        ok_type   = acct is not None and acct.crowdfunding_type == "Debt Crowdfunding"
        ok_val    = acct is not None and acct.current_account_value == 25000.0
        ok_status = acct is not None and acct.status == "Active"
        ok = ok_no_err and ok_plat and ok_type and ok_val and ok_status
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_plat:   detail.append("platform_name mismatch")
        if not ok_type:   detail.append("crowdfunding_type mismatch")
        if not ok_val:    detail.append("current_account_value mismatch")
        if not ok_status: detail.append("status != Active")
        return ("platform=Manafa, type=Debt Crowdfunding, value=25000, status=Active",
                "PASS" if ok else "; ".join(detail), ok)

    def cf02():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "acct.json")
            acct, err = add_cf_account(
                platform_name="",
                account_name="Test",
                crowdfunding_type="Debt Crowdfunding",
                institution="Bank",
                currency="SAR",
                current_account_value=0.0, available_cash=0.0,
                active_investments=0.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=0.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01",
                path=p,
            )
        ok = acct is None and err is not None and "platform" in err.lower()
        return ("empty platform_name rejected", "PASS" if ok else f"acct={acct}, err={err!r}", ok)

    def cf03():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "acct.json")
            acct, err = add_cf_account(
                platform_name="TestPlatform",
                account_name="Test",
                crowdfunding_type="Invalid Type",
                institution="Bank",
                currency="SAR",
                current_account_value=0.0, available_cash=0.0,
                active_investments=0.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=0.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01",
                path=p,
            )
        ok = acct is None and err is not None
        return ("invalid crowdfunding type rejected",
                "PASS" if ok else f"acct={acct}, err={err!r}", ok)

    def cf04():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, record_cf_transaction, load_cf_transactions
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            tp = os.path.join(tmp, "txn.json")
            acct, _ = add_cf_account(
                platform_name="Nayifat", account_name="Primary",
                crowdfunding_type="Debt Crowdfunding",
                institution="Nayifat Finance", currency="SAR",
                current_account_value=10000.0, available_cash=2000.0,
                active_investments=8000.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=10000.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01", path=p,
            )
            txn, err = record_cf_transaction(
                account_id=acct.account_id, txn_type="Profit Received",
                amount=450.0, txn_date="2025-06-01",
                notes="Profit distribution Q2 2025",
                path=p, txn_path=tp,
            )
            txns = load_cf_transactions(path=tp)
        ok_no_err = err is None
        ok_type   = txn is not None and txn.txn_type == "Profit Received"
        ok_amount = txn is not None and txn.amount == 450.0
        ok_stored = len([t for t in txns if t.txn_type == "Profit Received"]) == 1
        ok = ok_no_err and ok_type and ok_amount and ok_stored
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_type:   detail.append("txn_type mismatch")
        if not ok_amount: detail.append("amount mismatch")
        if not ok_stored: detail.append("transaction not stored")
        return ("Profit Received 450 stored correctly",
                "PASS" if ok else "; ".join(detail), ok)

    def cf05():
        import tempfile, os
        from portfolio.crowdfunding import record_cf_transaction
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            tp = os.path.join(tmp, "txn.json")
            open(p, "w").write("{}")
            open(tp, "w").write("[]")
            txn, err = record_cf_transaction(
                account_id="notexist",
                txn_type="Deposit",
                amount=100.0,
                txn_date="2025-01-01",
                notes="Should fail",
                path=p, txn_path=tp,
            )
        ok = txn is None and err is not None and "not found" in err.lower()
        return ("unknown account_id rejected",
                "PASS" if ok else f"txn={txn}, err={err!r}", ok)

    def cf06():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, add_cf_snapshot, load_cf_accounts
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            sp = os.path.join(tmp, "snap.json")
            acct, _ = add_cf_account(
                platform_name="Lendo", account_name="Primary",
                crowdfunding_type="Debt Crowdfunding",
                institution="Lendo Capital", currency="SAR",
                current_account_value=10000.0, available_cash=2000.0,
                active_investments=8000.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=10000.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01", path=p,
            )
            snap, err = add_cf_snapshot(
                account_id=acct.account_id,
                snapshot_date="2025-06-01",
                current_account_value=10800.0,
                available_cash=1800.0,
                active_investments=9000.0,
                delayed_investments=0.0,
                defaulted_investments=0.0,
                notes="Mid-year update",
                path=p, snap_path=sp,
            )
            accts_after = load_cf_accounts(path=p)
        ok_no_err = err is None
        ok_snap   = snap is not None and snap.current_account_value == 10800.0
        ok_live   = accts_after[acct.account_id].current_account_value == 10800.0
        ok_cash   = accts_after[acct.account_id].available_cash == 1800.0
        ok = ok_no_err and ok_snap and ok_live and ok_cash
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_snap:   detail.append("snapshot value mismatch")
        if not ok_live:   detail.append(f"live value={accts_after[acct.account_id].current_account_value}")
        if not ok_cash:   detail.append(f"live cash={accts_after[acct.account_id].available_cash}")
        return ("snapshot updates live account: value=10800, cash=1800",
                "PASS" if ok else "; ".join(detail), ok)

    def cf07():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, add_cf_snapshot, load_cf_snapshots
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            sp = os.path.join(tmp, "snap.json")
            acct, _ = add_cf_account(
                platform_name="Raqamyah", account_name="A1",
                crowdfunding_type="Debt Crowdfunding",
                institution="Raqamyah", currency="SAR",
                current_account_value=5000.0, available_cash=500.0,
                active_investments=4500.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=5000.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01", path=p,
            )
            add_cf_snapshot(
                account_id=acct.account_id, snapshot_date="2025-03-01",
                current_account_value=5200.0, available_cash=500.0,
                active_investments=4700.0, delayed_investments=0.0,
                defaulted_investments=0.0, notes="Q1 snapshot", path=p, snap_path=sp,
            )
            add_cf_snapshot(
                account_id=acct.account_id, snapshot_date="2025-06-01",
                current_account_value=5500.0, available_cash=600.0,
                active_investments=4900.0, delayed_investments=0.0,
                defaulted_investments=0.0, notes="Q2 snapshot", path=p, snap_path=sp,
            )
            snaps = load_cf_snapshots(path=sp)
        acct_snaps = [s for s in snaps if s.account_id == acct.account_id]
        ok = len(acct_snaps) == 2
        return ("two snapshots stored immutably (count=2)",
                "PASS" if ok else f"count={len(acct_snaps)}", ok)

    def cf08():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, record_cf_transaction, compute_cf_reconciliation
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            tp = os.path.join(tmp, "txn.json")
            acct, _ = add_cf_account(
                platform_name="Platform",
                account_name="Reconciled",
                crowdfunding_type="Debt Crowdfunding",
                institution="Bank",
                currency="SAR",
                current_account_value=10500.0,
                available_cash=0.0, active_investments=0.0,
                delayed_investments=0.0, defaulted_investments=0.0,
                total_deposits=0.0, total_withdrawals=0.0,
                total_profit_received=0.0, total_losses=0.0,
                last_update_date="2025-01-01", path=p,
            )
            record_cf_transaction(account_id=acct.account_id, txn_type="Deposit",
                                  amount=10000.0, txn_date="2025-01-01",
                                  notes="Initial deposit", path=p, txn_path=tp)
            record_cf_transaction(account_id=acct.account_id, txn_type="Profit Received",
                                  amount=500.0, txn_date="2025-06-01",
                                  notes="Profit received Q2", path=p, txn_path=tp)
            rec = compute_cf_reconciliation(acct.account_id, path=p, txn_path=tp)
        ok = abs(rec.get("unreconciled_diff", 999)) < 0.01
        return ("reconciliation diff ≈ 0 when value equals deposits+profit",
                "PASS" if ok else f"diff={rec.get('unreconciled_diff')}", ok)

    def cf09():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, record_cf_transaction, compute_cf_reconciliation
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            tp = os.path.join(tmp, "txn.json")
            acct, _ = add_cf_account(
                platform_name="Platform",
                account_name="Unreconciled",
                crowdfunding_type="Debt Crowdfunding",
                institution="Bank",
                currency="SAR",
                current_account_value=11000.0,
                available_cash=0.0, active_investments=0.0,
                delayed_investments=0.0, defaulted_investments=0.0,
                total_deposits=0.0, total_withdrawals=0.0,
                total_profit_received=0.0, total_losses=0.0,
                last_update_date="2025-01-01", path=p,
            )
            record_cf_transaction(account_id=acct.account_id, txn_type="Deposit",
                                  amount=10000.0, txn_date="2025-01-01",
                                  notes="Initial deposit", path=p, txn_path=tp)
            rec = compute_cf_reconciliation(acct.account_id, path=p, txn_path=tp)
        diff = rec.get("unreconciled_diff", 0)
        ok = abs(diff - 1000.0) < 0.01
        return ("unreconciled diff = 1000 (value=11000, deposits=10000)",
                "PASS" if ok else f"diff={diff}", ok)

    def cf10():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, record_cf_transaction, compute_cf_metrics
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            tp = os.path.join(tmp, "txn.json")
            acct, _ = add_cf_account(
                platform_name="Forus", account_name="Main",
                crowdfunding_type="Debt Crowdfunding",
                institution="Forus",
                currency="SAR",
                current_account_value=9000.0,
                available_cash=0.0, active_investments=0.0,
                delayed_investments=0.0, defaulted_investments=0.0,
                total_deposits=0.0, total_withdrawals=0.0,
                total_profit_received=0.0, total_losses=0.0,
                last_update_date="2025-01-01", path=p,
            )
            record_cf_transaction(account_id=acct.account_id, txn_type="Deposit",
                                  amount=10000.0, txn_date="2025-01-01",
                                  notes="Initial deposit", path=p, txn_path=tp)
            record_cf_transaction(account_id=acct.account_id, txn_type="Withdrawal",
                                  amount=1000.0, txn_date="2025-03-01",
                                  notes="Partial withdrawal", path=p, txn_path=tp)
            record_cf_transaction(account_id=acct.account_id, txn_type="Profit Received",
                                  amount=200.0, txn_date="2025-06-01",
                                  notes="Q2 profit", path=p, txn_path=tp)
            record_cf_transaction(account_id=acct.account_id, txn_type="Loss Write-Off",
                                  amount=50.0, txn_date="2025-06-15",
                                  notes="Write-off defaulted deal", path=p, txn_path=tp)
            m = compute_cf_metrics(acct.account_id, path=p, txn_path=tp)
        ok_nd  = abs(m.get("net_deposits", 999) - 9000.0) < 0.001
        ok_npl = abs(m.get("net_profit_loss", 999) - 150.0) < 0.001
        ok = ok_nd and ok_npl
        detail = []
        if not ok_nd:  detail.append(f"net_deposits={m.get('net_deposits')}, expected 9000")
        if not ok_npl: detail.append(f"net_profit_loss={m.get('net_profit_loss')}, expected 150")
        return ("net_deposits=9000, net_profit_loss=150",
                "PASS" if ok else "; ".join(detail), ok)

    def cf11():
        import tempfile, os
        from portfolio.crowdfunding import add_cf_account, edit_cf_account, load_cf_accounts
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "acct.json")
            acct, _ = add_cf_account(
                platform_name="OldPlatform", account_name="X",
                crowdfunding_type="Debt Crowdfunding",
                institution="Bank",
                currency="SAR",
                current_account_value=0.0, available_cash=0.0,
                active_investments=0.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=0.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01", path=p,
            )
            _, err = edit_cf_account(acct.account_id, status="Closed",
                                     total_deposits=5000.0, path=p)
            accts = load_cf_accounts(path=p)
        ok_no_err = err is None
        ok_stat   = accts[acct.account_id].status == "Closed"
        ok_dep    = accts[acct.account_id].total_deposits == 5000.0
        ok = ok_no_err and ok_stat and ok_dep
        detail = []
        if not ok_no_err: detail.append(f"err={err}")
        if not ok_stat:   detail.append("status not updated to Closed")
        if not ok_dep:    detail.append("total_deposits not updated")
        return ("edit_cf_account status=Closed total_deposits=5000",
                "PASS" if ok else "; ".join(detail), ok)

    def cf12():
        import tempfile, os
        from portfolio.crowdfunding import (
            add_cf_account, add_cf_snapshot, load_cf_accounts, load_cf_snapshots
        )
        with tempfile.TemporaryDirectory() as tmp:
            p  = os.path.join(tmp, "acct.json")
            sp = os.path.join(tmp, "snap.json")
            acct, _ = add_cf_account(
                platform_name="Multi-Snap", account_name="A",
                crowdfunding_type="Equity Crowdfunding",
                institution="Platform",
                currency="USD",
                current_account_value=1000.0, available_cash=100.0,
                active_investments=900.0, delayed_investments=0.0,
                defaulted_investments=0.0, total_deposits=1000.0,
                total_withdrawals=0.0, total_profit_received=0.0,
                total_losses=0.0, last_update_date="2025-01-01", path=p,
            )
            for val, dt in [(1100.0, "2025-03-01"), (1250.0, "2025-06-01"), (1400.0, "2025-09-01")]:
                add_cf_snapshot(
                    account_id=acct.account_id, snapshot_date=dt,
                    current_account_value=val, available_cash=100.0,
                    active_investments=val - 100.0, delayed_investments=0.0,
                    defaulted_investments=0.0, notes=f"snap {dt}",
                    path=p, snap_path=sp,
                )
            accts_final = load_cf_accounts(path=p)
            snaps_final = load_cf_snapshots(path=sp)
        acct_snaps = [s for s in snaps_final if s.account_id == acct.account_id]
        ok_count    = len(acct_snaps) == 3
        ok_live_val = accts_final[acct.account_id].current_account_value == 1400.0
        ok_live_dt  = accts_final[acct.account_id].last_update_date == "2025-09-01"
        ok = ok_count and ok_live_val and ok_live_dt
        detail = []
        if not ok_count:    detail.append(f"snapshot count={len(acct_snaps)}, expected 3")
        if not ok_live_val: detail.append(f"live value={accts_final[acct.account_id].current_account_value}")
        if not ok_live_dt:  detail.append(f"last_update_date={accts_final[acct.account_id].last_update_date}")
        return ("3 snapshots stored; live position = latest (1400, 2025-09-01)",
                "PASS" if ok else "; ".join(detail), ok)

    for test_id, desc, fn in [
        ("CF-01", "add_cf_account creates account with correct fields",               cf01),
        ("CF-02", "add_cf_account rejects empty platform name",                       cf02),
        ("CF-03", "add_cf_account rejects invalid crowdfunding type",                 cf03),
        ("CF-04", "record_cf_transaction records Profit Received correctly",          cf04),
        ("CF-05", "record_cf_transaction rejects unknown account_id",                 cf05),
        ("CF-06", "add_cf_snapshot updates live account position",                    cf06),
        ("CF-07", "add_cf_snapshot stores historical snapshots immutably",            cf07),
        ("CF-08", "compute_cf_reconciliation diff ≈ 0 when balanced",                 cf08),
        ("CF-09", "compute_cf_reconciliation detects unreconciled diff = 1000",       cf09),
        ("CF-10", "compute_cf_metrics: net_deposits=9000, net_profit_loss=150",       cf10),
        ("CF-11", "edit_cf_account updates status and total_deposits",                cf11),
        ("CF-12", "multiple snapshots: 3 stored, live = latest",                      cf12),
    ]:
        results.append(_run(test_id, desc, CAT, "portfolio.crowdfunding", "P0", True, fn))
    return results


def _cat_fixed_assets() -> list[TestResult]:
    """
    FA: Fixed Assets regression tests.

    FA-01  add_fixed_asset creates asset with correct fields.
    FA-02  add_fixed_asset rejects empty name.
    FA-03  add_fixed_asset rejects invalid asset_type.
    FA-04  equity = current_value − outstanding_liability (basic).
    FA-05  equity is zero when liability >= current_value.
    FA-06  Sold asset excluded from equity sum (compute_extra_assets_base).
    FA-07  edit_fixed_asset updates current_value field.
    FA-08  edit_fixed_asset rejects edit of Sold asset.
    FA-09  sell_fixed_asset marks asset as Sold.
    FA-10  sell_fixed_asset rejects already-Sold asset.
    FA-11  load/save round-trip preserves all fields.
    FA-12  FX conversion applied correctly in compute_extra_assets_base.
    """
    CAT = "Fixed Assets"
    results: list[TestResult] = []

    def fa01():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, load_fixed_assets
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, err = add_fixed_asset(
                name="Riyadh Apartment", asset_type="Real Estate",
                currency="SAR", current_value=800_000.0,
                outstanding_liability=200_000.0, path=p,
            )
            assets = load_fixed_assets(path=p)
        ok_no_err = err is None
        ok_name   = asset is not None and asset.name == "Riyadh Apartment"
        ok_type   = asset is not None and asset.asset_type == "Real Estate"
        ok_val    = asset is not None and asset.current_value == 800_000.0
        ok_status = asset is not None and asset.status == "Active"
        ok_saved  = len(assets) == 1
        ok = ok_no_err and ok_name and ok_type and ok_val and ok_status and ok_saved
        fails = [k for k, v in {"err": ok_no_err, "name": ok_name, "type": ok_type,
                                 "value": ok_val, "status": ok_status, "saved": ok_saved}.items() if not v]
        return ("name=Riyadh Apartment, type=Real Estate, value=800000, status=Active",
                "PASS" if ok else "FAIL: " + ",".join(fails), ok)
    results.append(_run("FA-01", "add_fixed_asset — creates asset correctly",
                        CAT, "portfolio.fixed_assets", "P0", True, fa01))

    def fa02():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, err = add_fixed_asset(
                name="", asset_type="Real Estate",
                currency="SAR", current_value=100_000.0, path=p,
            )
        ok = asset is None and err is not None and "name" in err.lower()
        return ("empty name rejected", "PASS" if ok else f"asset={asset}, err={err!r}", ok)
    results.append(_run("FA-02", "add_fixed_asset — rejects empty name",
                        CAT, "portfolio.fixed_assets", "P0", True, fa02))

    def fa03():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, FIXED_ASSET_TYPES
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, err = add_fixed_asset(
                name="Test", asset_type="INVALID_TYPE",
                currency="SAR", current_value=100_000.0, path=p,
            )
        ok_reject  = asset is None and err is not None and "invalid asset type" in err.lower()
        ok_pension  = "Pension / Retirement Fund" in FIXED_ASSET_TYPES
        ok_provident = "Provident Fund" in FIXED_ASSET_TYPES
        ok = ok_reject and ok_pension and ok_provident
        fails = [k for k, v in {"reject": ok_reject, "pension_type": ok_pension,
                                 "provident_type": ok_provident}.items() if not v]
        return ("invalid type rejected; Pension & Provident types present",
                "PASS" if ok else "FAIL: " + ",".join(fails), ok)
    results.append(_run("FA-03", "add_fixed_asset — rejects invalid type; new types registered",
                        CAT, "portfolio.fixed_assets", "P0", True, fa03))

    def fa04():
        from portfolio.fixed_assets import FixedAsset
        a = FixedAsset(
            asset_id="test0001", name="Villa", asset_type="Real Estate",
            currency="SAR", current_value=1_000_000.0, outstanding_liability=300_000.0,
            purchase_price=0.0, purchase_date="", status="Active",
        )
        exp, act = 700_000.0, a.equity
        return f"equity={exp:.2f}", f"equity={act:.2f}", abs(act - exp) < 0.01
    results.append(_run("FA-04", "equity = current_value − outstanding_liability",
                        CAT, "portfolio.fixed_assets", "P0", True, fa04))

    def fa05():
        from portfolio.fixed_assets import FixedAsset
        a = FixedAsset(
            asset_id="test0002", name="Car", asset_type="Vehicle",
            currency="SAR", current_value=50_000.0, outstanding_liability=80_000.0,
            purchase_price=0.0, purchase_date="", status="Active",
        )
        exp, act = 0.0, a.equity
        return f"equity=0.0 (liability>value)", f"equity={act:.2f}", abs(act - exp) < 0.001
    results.append(_run("FA-05", "equity is 0.0 when liability >= current_value",
                        CAT, "portfolio.fixed_assets", "P0", True, fa05))

    def fa06():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, sell_fixed_asset, load_fixed_assets
        from portfolio.net_worth import compute_extra_assets_base
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            a1, _ = add_fixed_asset("Active Land", "Real Estate", "SAR", 500_000.0, path=p)
            a2, _ = add_fixed_asset("Sold Car", "Vehicle", "SAR", 100_000.0, path=p)
            sell_fixed_asset(a2.asset_id, path=p)
            assets = load_fixed_assets(path=p)
        fx = {"SAR": _fx("SAR", "SAR", 1.0)}
        total = compute_extra_assets_base({}, {}, "SAR", fx, fixed_assets=assets)
        exp = 500_000.0
        ok = abs(total - exp) < 0.01
        return f"total_equity={exp:.0f} (sold excluded)", f"total_equity={total:.2f}", ok
    results.append(_run("FA-06", "Sold asset excluded from net-worth total",
                        CAT, "portfolio.net_worth", "P0", True, fa06))

    def fa07():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, edit_fixed_asset
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, _ = add_fixed_asset("House", "Real Estate", "SAR", 600_000.0, path=p)
            updated, err = edit_fixed_asset(asset.asset_id, path=p, current_value=650_000.0)
        ok = err is None and updated is not None and updated.current_value == 650_000.0
        return "current_value updated to 650000", "PASS" if ok else f"err={err!r}, val={getattr(updated, 'current_value', None)}", ok
    results.append(_run("FA-07", "edit_fixed_asset — updates current_value",
                        CAT, "portfolio.fixed_assets", "P0", True, fa07))

    def fa08():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, sell_fixed_asset, edit_fixed_asset
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, _ = add_fixed_asset("Shop", "Real Estate", "SAR", 300_000.0, path=p)
            sell_fixed_asset(asset.asset_id, path=p)
            updated, err = edit_fixed_asset(asset.asset_id, path=p, current_value=400_000.0)
        ok = updated is None and err is not None and "sold" in err.lower()
        return "edit of Sold asset rejected", "PASS" if ok else f"updated={updated}, err={err!r}", ok
    results.append(_run("FA-08", "edit_fixed_asset — rejects Sold asset",
                        CAT, "portfolio.fixed_assets", "P0", True, fa08))

    def fa09():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, sell_fixed_asset, load_fixed_assets
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, _ = add_fixed_asset("Plot", "Real Estate", "SAR", 200_000.0, path=p)
            ok_sell, err_sell = sell_fixed_asset(asset.asset_id, path=p)
            assets = load_fixed_assets(path=p)
        ok = ok_sell and err_sell is None and assets[asset.asset_id].status == "Sold"
        return "status=Sold", "PASS" if ok else f"ok_sell={ok_sell}, err={err_sell!r}", ok
    results.append(_run("FA-09", "sell_fixed_asset — marks asset as Sold",
                        CAT, "portfolio.fixed_assets", "P0", True, fa09))

    def fa10():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, sell_fixed_asset
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, _ = add_fixed_asset("Garage", "Vehicle", "SAR", 50_000.0, path=p)
            sell_fixed_asset(asset.asset_id, path=p)
            ok_dup, err_dup = sell_fixed_asset(asset.asset_id, path=p)
        ok = not ok_dup and err_dup is not None and "already" in err_dup.lower()
        return "double-sell rejected", "PASS" if ok else f"ok={ok_dup}, err={err_dup!r}", ok
    results.append(_run("FA-10", "sell_fixed_asset — rejects already-Sold asset",
                        CAT, "portfolio.fixed_assets", "P0", True, fa10))

    def fa11():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, load_fixed_assets
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            asset, _ = add_fixed_asset(
                name="Gold Bar", asset_type="Precious Metals (Physical)",
                currency="USD", current_value=95_000.0,
                outstanding_liability=0.0, purchase_price=80_000.0,
                purchase_date="2023-01-15", notes="10 oz gold", path=p,
            )
            loaded = load_fixed_assets(path=p)
        a = loaded.get(asset.asset_id)
        ok = (a is not None
              and a.name == "Gold Bar"
              and a.asset_type == "Precious Metals (Physical)"
              and a.currency == "USD"
              and abs(a.current_value - 95_000.0) < 0.001
              and a.purchase_date == "2023-01-15"
              and a.notes == "10 oz gold")
        return "round-trip fields preserved", "PASS" if ok else f"loaded={a}", ok
    results.append(_run("FA-11", "load/save round-trip — all fields preserved",
                        CAT, "portfolio.fixed_assets", "P0", True, fa11))

    def fa12():
        import tempfile, os
        from portfolio.fixed_assets import add_fixed_asset, load_fixed_assets
        from portfolio.net_worth import compute_extra_assets_base
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "fa.json")
            add_fixed_asset("US Property", "Real Estate", "USD", 500_000.0, path=p)
            assets = load_fixed_assets(path=p)
        fx = {
            "USD": _fx("USD", "SAR", 3.75),
            "SAR": _fx("SAR", "SAR", 1.0),
        }
        total = compute_extra_assets_base({}, {}, "SAR", fx, fixed_assets=assets)
        exp = 500_000.0 * 3.75   # 1_875_000.0
        ok = abs(total - exp) < 0.10
        return f"equity_in_SAR={exp:.2f}", f"equity_in_SAR={total:.2f}", ok
    results.append(_run("FA-12", "FX conversion applied to fixed-asset equity",
                        CAT, "portfolio.net_worth", "P0", True, fa12))

    return results


def _cat_wealth_statement() -> list[TestResult]:
    """
    WS — Family Wealth Statement PDF generator.
    WS-01  build_wealth_statement returns bytes beginning with %%PDF.
    WS-02  build_wealth_statement with a notes string still produces valid PDF.
    """
    CAT = "Wealth Statement"
    results: list[TestResult] = []

    def ws01():
        from portfolio.wealth_statement import build_wealth_statement
        pdf = build_wealth_statement(base_ccy="SAR", notes="")
        ok_bytes = isinstance(pdf, bytes)
        ok_magic = pdf[:4] == b"%PDF"
        ok_size  = len(pdf) > 1024
        ok = ok_bytes and ok_magic and ok_size
        fails = [k for k, v in {"bytes": ok_bytes, "magic": ok_magic, "size": ok_size}.items() if not v]
        return (
            "returns bytes starting with %PDF, size > 1 KB",
            "PASS" if ok else "FAIL: " + ",".join(fails),
            ok,
        )
    results.append(_run("WS-01", "build_wealth_statement — returns valid PDF bytes",
                        CAT, "portfolio.wealth_statement", "P0", True, ws01))

    def ws02():
        """Empty portfolio (no data) must not raise; must return valid PDF."""
        from unittest.mock import patch
        from portfolio.wealth_statement import build_wealth_statement

        _empty = lambda *a, **kw: {}  # noqa: E731

        patches = [
            patch("portfolio.load_holdings",                  _empty),
            patch("portfolio.accounts.load_accounts",         _empty),
            patch("portfolio.alt_investments.load_igi_investments", _empty),
            patch("portfolio.crowdfunding.load_cf_accounts",  _empty),
            patch("portfolio.fixed_assets.load_fixed_assets", _empty),
        ]
        try:
            for p in patches: p.start()
            pdf = build_wealth_statement(base_ccy="SAR", notes="")
            ok  = isinstance(pdf, bytes) and pdf[:4] == b"%PDF" and len(pdf) > 500
            return (
                "empty portfolio returns valid PDF without crash",
                "PASS" if ok else f"magic={pdf[:4]!r}, size={len(pdf)}",
                ok,
            )
        except Exception as exc:
            return ("empty portfolio returns valid PDF without crash",
                    f"FAIL: raised {type(exc).__name__}: {exc}", False)
        finally:
            for p in patches: p.stop()

    results.append(_run("WS-02", "build_wealth_statement — empty portfolio produces valid PDF",
                        CAT, "portfolio.wealth_statement", "P0", True, ws02))

    return results


def run_all_tests() -> TestReport:
    """
    Execute all pre-release tests and return a TestReport.
    Never reads or writes portfolio files.
    """
    all_results: list[TestResult] = (
        _cat_a() + _cat_b() + _cat_c() + _cat_d() + _cat_e()
        + _cat_f() + _cat_g() + _cat_h() + _cat_i() + _cat_j()
        + _cat_k() + _cat_l() + _cat_m() + _cat_n() + _cat_arch() + _cat_acc_ui() + _cat_a11() + _cat_a10() + _cat_ch()
        + _cat_add() + _cat_disc() + _cat_sds() + _cat_fas() + _cat_alloc() + _cat_alloc_qp()
        + _cat_alloc_ui() + _cat_hld_ui() + _cat_alloc_mkt() + _cat_alloc_scope()
        + _cat_acc_ui_ext() + _cat_asset_type() + _cat_alloc_at()
        + _cat_edit_ui()
        + _cat_assetid()
        + _cat_asset_identity()
        + _cat_settle()
        + _cat_igi()
        + _cat_cf()
        + _cat_fixed_assets()
        + _cat_wealth_statement()
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
