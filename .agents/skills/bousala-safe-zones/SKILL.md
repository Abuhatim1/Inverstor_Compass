---
name: bousala-safe-zones
description: Protected zones and minimal-change principles for the Bousala project. Load before any implementation to identify high-risk components, classify risk level, and enforce the golden rule that UI changes stay UI-only and filters never affect accounting calculations.
---

# Bousala Safe Zones

## Purpose

Protect critical portfolio-accounting and valuation components from accidental modification.

This skill applies to every implementation request.

────────────────────────────

## Golden Rule

A UI request must remain a UI change.

A reporting request must remain a reporting change.

Do not expand implementation scope unless explicitly approved.

────────────────────────────

## Protected Zones

Treat the following as high-risk areas.

Do not modify them unless the user explicitly requests it.

### Portfolio Accounting

* Holdings Engine
* Transaction Engine
* Account Engine
* Cash Engine
* FIFO Logic
* Realized P&L Logic
* Unrealized P&L Logic

### Valuation

* Valuation Engine
* Portfolio Value Calculation
* Position Value Calculation
* Cost Basis Calculation

### FX

* FX Engine
* Currency Conversion Logic
* Base Currency Logic

### Market Data

* Yahoo Layer
* SAHMK Layer
* SEC Layer
* Price Routing Logic

────────────────────────────

## Before Any Change

Explicitly determine whether the request affects:

* Holdings
* Transactions
* Accounts
* Cash
* Valuation
* FX
* Market Data

If yes:

State impact before implementation.

────────────────────────────

## UI Change Rule

For UI-only requests:

Do not modify:

* Portfolio calculations
* Holdings calculations
* Valuation calculations
* FX calculations

UI work should remain inside UI components whenever possible.

────────────────────────────

## Filter Rule

Filters must never modify underlying data.

Filters may only affect:

* visibility
* reporting
* chart scope
* table scope

Filters must not change accounting calculations.

────────────────────────────

## Minimal Change Principle

Prefer:

* one function change
* one component change
* one file change

Avoid broad refactoring.

Avoid touching unrelated modules.

────────────────────────────

## Risk Classification

P0 = Data Integrity Risk

P1 = Portfolio Accounting Risk

P2 = Valuation / FX Risk

P3 = Reporting Risk

P4 = UI Risk

Every implementation review must identify the highest applicable risk level.

────────────────────────────

## KPI Duplication Rule

Before building any new KPI panel or adding a metric to a tab:

1. `grep` for the underlying field name (`holdings_value_base`, `daily_change_pct`,
   `base_market_value`, etc.) across all render functions.
2. If the metric is already rendered elsewhere, **reuse the already-computed
   variable or shared helper** — do not re-derive independently.
3. Any metric shown in ≥2 tabs must route through ONE function in
   `portfolio/display_metrics.py` (no `st.*`, takes data as args so tests can
   exercise it without Streamlit).
4. Use `fmt_money_compact` from `portfolio.display_metrics` as the canonical
   formatter for all monetary KPIs. Do not add a new money formatter.

Independent re-derivation is the root cause of cross-tab mismatch bugs. The
`_cat_consist()` test category in `dev_test_runner.py` is the regression guard
for this contract — never remove or reduce it.

────────────────────────────

## Escalation Rule

If implementation requires touching a protected zone:

Stop.

Explain:

* why it is required
* files affected
* risks introduced
* safer alternatives

Wait for approval before proceeding.
