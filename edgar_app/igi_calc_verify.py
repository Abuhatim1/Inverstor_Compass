#!/usr/bin/env python3
"""
IGI Calculation Verification — 10 dummy scenarios
===================================================
Run:  python edgar_app/igi_calc_verify.py

Saves dummy input data to:   edgar_app/igi_verify_inputs.json
Saves full results table to: edgar_app/igi_verify_results.json
Prints a human-readable report to stdout.

Delete both output files (+ this script) once you've cross-checked.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

from datetime import date
from portfolio.alt_investments import (
    IGIInvestment,
    IGITransaction,
    compute_igi_metrics,
)

TODAY = date.today()


# ── Pure-formula reimplementations (mirrors compute_igi_metrics exactly) ─────

def _expected_yield_schedule(inv: IGIInvestment, txns: list) -> dict:
    """Replicates the yield-schedule block from compute_igi_metrics."""
    if inv.status == "Pending Funding" or not inv.start_date or not inv.maturity_date:
        return {"projected": None, "accrued": 0.0, "outstanding": None,
                "collection_rate": None, "note": "hidden — no schedule"}

    start    = date.fromisoformat(inv.start_date)
    maturity = date.fromisoformat(inv.maturity_date)
    tenor    = max(0, (maturity - start).days)
    if tenor == 0:
        return {"projected": None, "accrued": 0.0, "outstanding": None,
                "collection_rate": None, "note": "hidden — zero tenor"}

    projected = round(inv.principal_amount * (inv.expected_yield_pct / 100) * (tenor / 365), 2)

    if inv.status == "Closed":
        close_dates = [t["date"] for t in txns if t["txn_type"] == "Principal Returned"]
        close_iso   = max(close_dates) if close_dates else inv.maturity_date
        end         = min(date.fromisoformat(close_iso), maturity)
    else:
        end = min(TODAY, maturity)

    elapsed = max(0, (end - start).days)
    accrued = round(inv.principal_amount * (inv.expected_yield_pct / 100) * (elapsed / 365), 2)

    received = round(sum(t["amount"] for t in txns if t["txn_type"] == "Profit Received"), 2)
    outstanding = round(projected - received, 2)
    collection_rate = round(received / accrued * 100, 1) if accrued > 0 else None

    return {
        "tenor_days":   tenor,
        "elapsed_days": elapsed,
        "end_date":     end.isoformat(),
        "projected":    projected,
        "accrued":      accrued,
        "received":     received,
        "outstanding":  outstanding,
        "collection_rate": collection_rate,
        "delta_vs_accrued": round(received - accrued, 2),
    }


def _expected_accounting(inv: IGIInvestment, txns: list) -> dict:
    """Replicates the accounting block from compute_igi_metrics."""
    _OUTFLOWS = {"Initial Investment", "Additional Investment"}
    _INFLOWS  = {"Profit Received", "Principal Returned"}

    total_invested        = round(sum(t["amount"] for t in txns if t["txn_type"] in _OUTFLOWS), 2)
    total_profit_received = round(sum(t["amount"] for t in txns if t["txn_type"] == "Profit Received"), 2)
    total_returned        = round(sum(t["amount"] for t in txns if t["txn_type"] == "Principal Returned"), 2)
    current_value         = inv.current_value
    unrealized_profit     = round(current_value - (total_invested - total_returned), 2)
    total_return          = round(total_profit_received + unrealized_profit, 2)

    return {
        "total_invested":         total_invested,
        "total_profit_received":  total_profit_received,
        "total_returned":         total_returned,
        "current_value":          current_value,
        "unrealized_profit":      unrealized_profit,
        "total_return":           total_return,
    }


# ── Scenario definitions ──────────────────────────────────────────────────────

SCENARIOS = [
    # 1 — Active, mid-term, zero profit received (baseline)
    {
        "id": "S01",
        "label": "Active · mid-term · no profit received (baseline)",
        "inv": {
            "investment_id": "sc01aaaa",
            "investment_name": "S01 Murabaha — ABC Bank",
            "institution": "ABC Bank",
            "principal_amount": 100_000.0,
            "expected_yield_pct": 5.0,
            "start_date": "2026-01-01",
            "maturity_date": "2026-12-31",
            "currency": "SAR",
            "status": "Active",
            "current_value": 100_000.0,
            "sharia_structure": "Murabaha",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Renew",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S01 baseline scenario",
        },
        "txns": [
            {"txn_id": "t01a", "investment_id": "sc01aaaa", "date": "2026-01-01",
             "txn_type": "Initial Investment", "amount": 100_000.0, "notes": "Initial", "recorded_at": "2026-01-01T00:00:00"},
        ],
    },

    # 2 — Active, past maturity date (accrued should equal projected)
    {
        "id": "S02",
        "label": "Active · past maturity date → accrued = projected",
        "inv": {
            "investment_id": "sc02aaaa",
            "investment_name": "S02 Deposit — DEF Bank",
            "institution": "DEF Bank",
            "principal_amount": 80_000.0,
            "expected_yield_pct": 4.0,
            "start_date": "2025-06-01",
            "maturity_date": "2025-12-31",
            "currency": "SAR",
            "status": "Active",
            "current_value": 80_000.0,
            "sharia_structure": "Not Specified",
            "sharia_status": "Conventional",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Return",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S02 — today past maturity",
        },
        "txns": [
            {"txn_id": "t02a", "investment_id": "sc02aaaa", "date": "2025-06-01",
             "txn_type": "Initial Investment", "amount": 80_000.0, "notes": "", "recorded_at": "2025-06-01T00:00:00"},
        ],
    },

    # 3 — Pending Funding → yield schedule entirely hidden
    {
        "id": "S03",
        "label": "Pending Funding → yield schedule hidden",
        "inv": {
            "investment_id": "sc03aaaa",
            "investment_name": "S03 Upcoming Wakala — GHI Bank",
            "institution": "GHI Bank",
            "principal_amount": 50_000.0,
            "expected_yield_pct": 6.0,
            "start_date": "2026-07-01",
            "maturity_date": "2027-06-30",
            "currency": "SAR",
            "status": "Pending Funding",
            "current_value": 0.0,
            "sharia_structure": "Wakala",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Renew",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S03 — pending, no outflow yet",
        },
        "txns": [],
    },

    # 4 — Maturity Action Required, past maturity (accrued = projected)
    {
        "id": "S04",
        "label": "Maturity Action Required · past maturity → accrued = projected",
        "inv": {
            "investment_id": "sc04aaaa",
            "investment_name": "S04 Sukuk — JKL Bank",
            "institution": "JKL Bank",
            "principal_amount": 120_000.0,
            "expected_yield_pct": 5.5,
            "start_date": "2025-09-01",
            "maturity_date": "2026-03-01",
            "currency": "SAR",
            "status": "Maturity Action Required",
            "current_value": 120_000.0,
            "sharia_structure": "Sukuk Ijara",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Renew",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S04 — MAR, waiting for maturity action",
        },
        "txns": [
            {"txn_id": "t04a", "investment_id": "sc04aaaa", "date": "2025-09-01",
             "txn_type": "Initial Investment", "amount": 120_000.0, "notes": "", "recorded_at": "2025-09-01T00:00:00"},
        ],
    },

    # 5 — Closed, fully paid at exact maturity date, all profit received
    {
        "id": "S05",
        "label": "Closed · fully paid at maturity · outstanding = 0",
        "inv": {
            "investment_id": "sc05aaaa",
            "investment_name": "S05 Term Deposit — MNO Bank",
            "institution": "MNO Bank",
            "principal_amount": 200_000.0,
            "expected_yield_pct": 3.5,
            "start_date": "2025-01-01",
            "maturity_date": "2025-12-31",
            "currency": "SAR",
            "status": "Closed",
            "current_value": 0.0,
            "sharia_structure": "Not Specified",
            "sharia_status": "Conventional",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Return",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S05 — fully matured and closed",
        },
        "txns": [
            {"txn_id": "t05a", "investment_id": "sc05aaaa", "date": "2025-01-01",
             "txn_type": "Initial Investment", "amount": 200_000.0, "notes": "", "recorded_at": "2025-01-01T00:00:00"},
            # Profit paid in full on maturity date
            {"txn_id": "t05b", "investment_id": "sc05aaaa", "date": "2025-12-31",
             "txn_type": "Profit Received", "amount": 6_981.37, "notes": "Full profit at maturity", "recorded_at": "2025-12-31T00:00:00"},
            {"txn_id": "t05c", "investment_id": "sc05aaaa", "date": "2025-12-31",
             "txn_type": "Principal Returned", "amount": 200_000.0, "notes": "Principal returned at maturity", "recorded_at": "2025-12-31T00:00:00"},
        ],
    },

    # 6 — Closed via early withdrawal mid-term (accrual capped at close date)
    {
        "id": "S06",
        "label": "Closed · early withdrawal mid-term → accrual capped at close date",
        "inv": {
            "investment_id": "sc06aaaa",
            "investment_name": "S06 Murabaha — PQR Bank",
            "institution": "PQR Bank",
            "principal_amount": 150_000.0,
            "expected_yield_pct": 6.0,
            "start_date": "2026-01-01",
            "maturity_date": "2026-12-31",
            "currency": "SAR",
            "status": "Closed",
            "current_value": 0.0,
            "sharia_structure": "Murabaha",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Return",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S06 — withdrawn early on 2026-03-31",
        },
        "txns": [
            {"txn_id": "t06a", "investment_id": "sc06aaaa", "date": "2026-01-01",
             "txn_type": "Initial Investment", "amount": 150_000.0, "notes": "", "recorded_at": "2026-01-01T00:00:00"},
            # Early withdrawal: partial profit (less than accrued — penalty implied)
            {"txn_id": "t06b", "investment_id": "sc06aaaa", "date": "2026-03-31",
             "txn_type": "Profit Received", "amount": 2_000.0, "notes": "Partial profit — early withdrawal penalty applied", "recorded_at": "2026-03-31T00:00:00"},
            {"txn_id": "t06c", "investment_id": "sc06aaaa", "date": "2026-03-31",
             "txn_type": "Principal Returned", "amount": 150_000.0, "notes": "Principal returned — early withdrawal", "recorded_at": "2026-03-31T00:00:00"},
        ],
    },

    # 7 — Active, profit received AHEAD of accrual (positive delta)
    {
        "id": "S07",
        "label": "Active · received AHEAD of accrual → positive delta",
        "inv": {
            "investment_id": "sc07aaaa",
            "investment_name": "S07 Periodic Wakala — STU Bank",
            "institution": "STU Bank",
            "principal_amount": 75_000.0,
            "expected_yield_pct": 7.0,
            "start_date": "2026-01-01",
            "maturity_date": "2026-12-31",
            "currency": "SAR",
            "status": "Active",
            "current_value": 75_000.0,
            "sharia_structure": "Wakala",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "Periodic",
            "liquidity_type": "Monthly",
            "maturity_instruction": "Renew",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S07 — periodic payments, bank paid ahead",
        },
        "txns": [
            {"txn_id": "t07a", "investment_id": "sc07aaaa", "date": "2026-01-01",
             "txn_type": "Initial Investment", "amount": 75_000.0, "notes": "", "recorded_at": "2026-01-01T00:00:00"},
            # Three monthly profit payments totalling 3,000 — ahead of ~2,215 accrued
            {"txn_id": "t07b", "investment_id": "sc07aaaa", "date": "2026-02-01",
             "txn_type": "Profit Received", "amount": 1_000.0, "notes": "Jan profit", "recorded_at": "2026-02-01T00:00:00"},
            {"txn_id": "t07c", "investment_id": "sc07aaaa", "date": "2026-03-01",
             "txn_type": "Profit Received", "amount": 1_000.0, "notes": "Feb profit", "recorded_at": "2026-03-01T00:00:00"},
            {"txn_id": "t07d", "investment_id": "sc07aaaa", "date": "2026-04-01",
             "txn_type": "Profit Received", "amount": 1_000.0, "notes": "Mar profit", "recorded_at": "2026-04-01T00:00:00"},
        ],
    },

    # 8 — Active, profit received BEHIND accrual (negative delta)
    {
        "id": "S08",
        "label": "Active · received BEHIND accrual → negative delta",
        "inv": {
            "investment_id": "sc08aaaa",
            "investment_name": "S08 Mudaraba — VWX Bank",
            "institution": "VWX Bank",
            "principal_amount": 90_000.0,
            "expected_yield_pct": 4.5,
            "start_date": "2026-01-01",
            "maturity_date": "2026-12-31",
            "currency": "SAR",
            "status": "Active",
            "current_value": 90_000.0,
            "sharia_structure": "Mudaraba",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "Periodic",
            "liquidity_type": "Monthly",
            "maturity_instruction": "Renew",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S08 — bank behind on payments",
        },
        "txns": [
            {"txn_id": "t08a", "investment_id": "sc08aaaa", "date": "2026-01-01",
             "txn_type": "Initial Investment", "amount": 90_000.0, "notes": "", "recorded_at": "2026-01-01T00:00:00"},
            # Only one small payment received — well behind accrual
            {"txn_id": "t08b", "investment_id": "sc08aaaa", "date": "2026-03-01",
             "txn_type": "Profit Received", "amount": 500.0, "notes": "Partial Q1 profit", "recorded_at": "2026-03-01T00:00:00"},
        ],
    },

    # 9 — Active, missing maturity_date → yield schedule hidden
    {
        "id": "S09",
        "label": "Active · no maturity_date → yield schedule hidden",
        "inv": {
            "investment_id": "sc09aaaa",
            "investment_name": "S09 Open-ended Account — YZA Bank",
            "institution": "YZA Bank",
            "principal_amount": 60_000.0,
            "expected_yield_pct": 5.0,
            "start_date": "2026-01-01",
            "maturity_date": None,
            "currency": "SAR",
            "status": "Active",
            "current_value": 60_000.0,
            "sharia_structure": "Not Specified",
            "sharia_status": "Not Applicable",
            "profit_payment_structure": "Periodic",
            "liquidity_type": "Daily",
            "maturity_instruction": "Renew",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S09 — rolling savings, no fixed maturity",
        },
        "txns": [
            {"txn_id": "t09a", "investment_id": "sc09aaaa", "date": "2026-01-01",
             "txn_type": "Initial Investment", "amount": 60_000.0, "notes": "", "recorded_at": "2026-01-01T00:00:00"},
        ],
    },

    # 10 — Active, very short tenor (30 days), high rate, mid-way through
    {
        "id": "S10",
        "label": "Active · 30-day short tenor · high rate 12% · mid-way through",
        "inv": {
            "investment_id": "sc10aaaa",
            "investment_name": "S10 Money Market — BCD Bank",
            "institution": "BCD Bank",
            "principal_amount": 500_000.0,
            "expected_yield_pct": 12.0,
            "start_date": "2026-05-20",
            "maturity_date": "2026-06-19",
            "currency": "SAR",
            "status": "Active",
            "current_value": 500_000.0,
            "sharia_structure": "Commodity Murabaha / Tawarruq",
            "sharia_status": "Shariah Compliant",
            "profit_payment_structure": "At Maturity",
            "liquidity_type": "Locked Until Maturity",
            "maturity_instruction": "Return",
            "parent_investment_id": None,
            "child_investment_id": None,
            "notes": "S10 — short 30-day placement, high rate",
        },
        "txns": [
            {"txn_id": "t10a", "investment_id": "sc10aaaa", "date": "2026-05-20",
             "txn_type": "Initial Investment", "amount": 500_000.0, "notes": "", "recorded_at": "2026-05-20T00:00:00"},
        ],
    },
]


# ── Build IGIInvestment + IGITransaction objects from dicts ───────────────────

def _build_inv(d: dict) -> IGIInvestment:
    return IGIInvestment(
        investment_id=d["investment_id"],
        investment_name=d["investment_name"],
        institution=d["institution"],
        principal_amount=d["principal_amount"],
        expected_yield_pct=d["expected_yield_pct"],
        start_date=d["start_date"],
        maturity_date=d["maturity_date"],
        currency=d["currency"],
        status=d["status"],
        current_value=d["current_value"],
        sharia_structure=d["sharia_structure"],
        sharia_status=d["sharia_status"],
        profit_payment_structure=d["profit_payment_structure"],
        liquidity_type=d["liquidity_type"],
        maturity_instruction=d["maturity_instruction"],
        parent_investment_id=d["parent_investment_id"],
        child_investment_id=d["child_investment_id"],
        notes=d["notes"],
    )


def _build_txn(d: dict) -> IGITransaction:
    return IGITransaction(
        txn_id=d["txn_id"],
        investment_id=d["investment_id"],
        date=d["date"],
        txn_type=d["txn_type"],
        amount=d["amount"],
        notes=d["notes"],
        recorded_at=d["recorded_at"],
    )


# ── Run verification ──────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SEP  = "─" * 90


def _close(a, b, tol=0.02):
    """Numeric comparison with small float tolerance."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def main():
    print(f"\n{'═'*90}")
    print(f"  IGI CALCULATION VERIFICATION — {TODAY.isoformat()}  (10 scenarios)")
    print(f"{'═'*90}\n")

    all_investments: dict[str, IGIInvestment] = {}
    all_txns_obj:   list[IGITransaction]      = []
    inputs_for_json = []
    results_for_json = []

    for sc in SCENARIOS:
        inv  = _build_inv(sc["inv"])
        txns = [_build_txn(t) for t in sc["txns"]]

        all_investments[inv.investment_id] = inv
        all_txns_obj.extend(txns)

        # Expected values (formula reimplementation)
        exp_yield = _expected_yield_schedule(inv, sc["txns"])
        exp_acct  = _expected_accounting(inv, sc["txns"])

        # Actual values from compute_igi_metrics
        actual = compute_igi_metrics(
            inv.investment_id,
            _investments={inv.investment_id: inv},
            _all_txns=txns,
        )

        # ── Accounting checks ─────────────────────────────────────────────────
        chk_acct = {
            "total_invested":        _close(exp_acct["total_invested"],        actual.get("total_invested")),
            "total_profit_received": _close(exp_acct["total_profit_received"], actual.get("total_profit_received")),
            "total_returned":        _close(exp_acct["total_returned"],        actual.get("total_returned")),
            "unrealized_profit":     _close(exp_acct["unrealized_profit"],     actual.get("unrealized_profit")),
            "total_return":          _close(exp_acct["total_return"],          actual.get("total_return")),
        }

        # ── Yield-schedule checks ─────────────────────────────────────────────
        a_proj = actual.get("projected_total_profit")
        a_acc  = actual.get("accrued_to_date", 0.0)
        a_out  = actual.get("outstanding")
        a_cr   = actual.get("collection_rate_pct")

        chk_yield = {
            "projected":       _close(exp_yield.get("projected"),       a_proj),
            "accrued":         _close(exp_yield.get("accrued"),         a_acc),
            "outstanding":     _close(exp_yield.get("outstanding"),      a_out),
            "collection_rate": _close(exp_yield.get("collection_rate"), a_cr),
        }

        all_pass = all(chk_acct.values()) and all(chk_yield.values())
        verdict  = PASS if all_pass else FAIL

        # ── Print scenario block ──────────────────────────────────────────────
        print(f"  {sc['id']}  {verdict}  {sc['label']}")
        print(SEP)

        print(f"  {'INPUT':}")
        print(f"    Principal:       {inv.principal_amount:>12,.2f} {inv.currency}")
        print(f"    Expected rate:   {inv.expected_yield_pct:>12.2f}%")
        print(f"    Start date:      {inv.start_date or '—':>12}")
        print(f"    Maturity date:   {(inv.maturity_date or '—'):>12}")
        print(f"    Status:          {inv.status:>12}")
        print(f"    Current value:   {inv.current_value:>12,.2f}")
        if sc["txns"]:
            print(f"    Transactions:")
            for t in sc["txns"]:
                print(f"      {t['date']}  {t['txn_type']:<26}  {t['amount']:>12,.2f}")

        print()
        print(f"  {'ACCOUNTING METRICS (cash-flow only)':}")
        rows_acct = [
            ("Total Invested",        exp_acct["total_invested"],        actual.get("total_invested"),        chk_acct["total_invested"]),
            ("Total Profit Received", exp_acct["total_profit_received"], actual.get("total_profit_received"), chk_acct["total_profit_received"]),
            ("Total Principal Ret'd", exp_acct["total_returned"],        actual.get("total_returned"),        chk_acct["total_returned"]),
            ("Unrealized Profit",     exp_acct["unrealized_profit"],     actual.get("unrealized_profit"),     chk_acct["unrealized_profit"]),
            ("Total Return",          exp_acct["total_return"],          actual.get("total_return"),          chk_acct["total_return"]),
        ]
        print(f"    {'Field':<26}  {'Expected':>12}  {'Actual':>12}  {'Check'}")
        for label, exp_v, act_v, ok in rows_acct:
            exp_s = f"{exp_v:,.2f}" if exp_v is not None else "—"
            act_s = f"{act_v:,.2f}" if act_v is not None else "—"
            print(f"    {label:<26}  {exp_s:>12}  {act_s:>12}  {'✅' if ok else '❌'}")

        print()
        print(f"  {'YIELD SCHEDULE (projection layer — informational)':}")
        eys = exp_yield

        if eys.get("projected") is None:
            print(f"    ⚑  {eys.get('note', 'Section hidden — no schedule computed')}")
            print(f"       Actual projected_total_profit = {a_proj!r}   {'✅' if a_proj is None else '❌'}")
        else:
            tenor_d   = eys.get("tenor_days")
            elapsed_d = eys.get("elapsed_days")
            end_d     = eys.get("end_date")
            print(f"    Tenor:           {tenor_d:>6} days")
            print(f"    Elapsed:         {elapsed_d:>6} days  (end date: {end_d})")
            rows_yield = [
                ("Projected Total",  eys["projected"],       a_proj,  chk_yield["projected"]),
                ("Accrued to Date",  eys["accrued"],         a_acc,   chk_yield["accrued"]),
                ("Outstanding",      eys["outstanding"],     a_out,   chk_yield["outstanding"]),
                ("Collection Rate",  eys["collection_rate"], a_cr,    chk_yield["collection_rate"]),
            ]
            print(f"    {'Field':<26}  {'Expected':>12}  {'Actual':>12}  {'Check'}")
            for label, exp_v, act_v, ok in rows_yield:
                exp_s = f"{exp_v:,.2f}" if isinstance(exp_v, float) else (f"{exp_v}%" if exp_v is not None else "—")
                act_s = f"{act_v:,.2f}" if isinstance(act_v, float) else (f"{act_v}%" if act_v is not None else "—")
                print(f"    {label:<26}  {exp_s:>12}  {act_s:>12}  {'✅' if ok else '❌'}")

            delta = eys.get("delta_vs_accrued", 0.0)
            actual_delta = round(exp_acct["total_profit_received"] - eys["accrued"], 2)
            direction = "ahead ▲" if delta >= 0 else "behind ▼"
            print(f"    Delta (recv − accrued):  {delta:>+,.2f}  → {direction}")

        xirr_val = actual.get("xirr")
        print(f"    XIRR (accounting):       {f'{xirr_val*100:.4f}%' if xirr_val is not None else 'N/A (insufficient flows)'}")

        print()

        # Build JSON result record
        results_for_json.append({
            "scenario_id": sc["id"],
            "label": sc["label"],
            "verdict": "PASS" if all_pass else "FAIL",
            "input": {
                "principal": inv.principal_amount,
                "rate_pct": inv.expected_yield_pct,
                "start_date": inv.start_date,
                "maturity_date": inv.maturity_date,
                "status": inv.status,
                "current_value": inv.current_value,
                "transactions": sc["txns"],
            },
            "expected": {**exp_acct, **{k: v for k, v in exp_yield.items() if k not in ("note",)}},
            "actual": {
                "total_invested":        actual.get("total_invested"),
                "total_profit_received": actual.get("total_profit_received"),
                "total_returned":        actual.get("total_returned"),
                "unrealized_profit":     actual.get("unrealized_profit"),
                "total_return":          actual.get("total_return"),
                "projected_total_profit": actual.get("projected_total_profit"),
                "accrued_to_date":       actual.get("accrued_to_date"),
                "outstanding":           actual.get("outstanding"),
                "collection_rate_pct":   actual.get("collection_rate_pct"),
                "xirr":                  actual.get("xirr"),
            },
        })

        inputs_for_json.append({
            "scenario_id": sc["id"],
            "label": sc["label"],
            "investment": sc["inv"],
            "transactions": sc["txns"],
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(results_for_json)
    passed = sum(1 for r in results_for_json if r["verdict"] == "PASS")
    failed = total - passed

    print(f"{'═'*90}")
    print(f"  SUMMARY:  {passed}/{total} PASS   {failed} FAIL")
    if failed:
        for r in results_for_json:
            if r["verdict"] == "FAIL":
                print(f"    ❌ {r['scenario_id']} — {r['label']}")
    print(f"  Reference date (TODAY): {TODAY.isoformat()}")
    print(f"{'═'*90}\n")

    # ── Save files ────────────────────────────────────────────────────────────
    base = os.path.dirname(__file__)

    inputs_path  = os.path.join(base, "igi_verify_inputs.json")
    results_path = os.path.join(base, "igi_verify_results.json")

    with open(inputs_path, "w") as f:
        json.dump(inputs_for_json, f, indent=2)

    with open(results_path, "w") as f:
        json.dump(results_for_json, f, indent=2, default=str)

    print(f"  📄 Inputs saved:  edgar_app/igi_verify_inputs.json")
    print(f"  📄 Results saved: edgar_app/igi_verify_results.json")
    print(f"\n  When done cross-checking, delete both .json files and igi_calc_verify.py\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
