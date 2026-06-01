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

## Escalation Rule

If implementation requires touching a protected zone:

Stop.

Explain:

* why it is required
* files affected
* risks introduced
* safer alternatives

Wait for approval before proceeding.
