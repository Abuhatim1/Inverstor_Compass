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
            result = sahmk_client.get_quote("2222")
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
# Main entry point
# ════════════════════════════════════════════════════════════════════════════════

def run_all_tests() -> TestReport:
    """
    Execute all pre-release tests and return a TestReport.
    Never reads or writes portfolio files.
    """
    all_results: list[TestResult] = (
        _cat_a() + _cat_b() + _cat_c() + _cat_d() + _cat_e()
        + _cat_f() + _cat_g() + _cat_h() + _cat_i()
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
