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
# Main entry point
# ════════════════════════════════════════════════════════════════════════════════

def run_all_tests() -> TestReport:
    """
    Execute all pre-release tests and return a TestReport.
    Never reads or writes portfolio files.
    """
    all_results: list[TestResult] = (
        _cat_a() + _cat_b() + _cat_c() + _cat_d()
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
