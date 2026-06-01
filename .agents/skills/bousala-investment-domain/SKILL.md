---
name: bousala-investment-domain
description: Investment and portfolio-management domain model for the Bousala project. Load when reasoning about holdings, transactions, allocation, performance, cash, P&L, multi-currency, or market rules. Defines what is derived vs. source of truth and enforces accounting separation from UI/research layers.
---

# Bousala Investment Domain

## Purpose

This skill teaches the investment and portfolio-management domain model used by Bousala.

This is not a stock screener.

This is not a research website.

This is a portfolio accounting platform.

Business logic accuracy is more important than UI.

────────────────────────────

## Source Of Truth

Transactions are the source of truth.

Everything else is derived.

Derived items include:

* Holdings
* Allocation
* Performance
* Risk
* Reports
* Dashboards

Never bypass transaction history.

────────────────────────────

## Holdings Rules

Holdings are calculated.

Holdings are not manually maintained.

Holdings are derived from:

* Buy transactions
* Sell transactions
* Corporate actions

If Holdings differ from Transactions:

Treat as critical defect.

────────────────────────────

## Allocation Rules

Allocation is derived from holdings.

Allocation is never a source of truth.

Allocation must not modify holdings.

Allocation must not modify transactions.

Allocation is a reporting layer only.

────────────────────────────

## Accounts

Support:

* Multiple investment accounts
* Multiple bank accounts
* Multiple brokers

Assets belong to accounts.

Cash belongs to accounts.

Performance must remain auditable by account.

────────────────────────────

## Cash Rules

Cash is a first-class asset.

Cash balances must be tracked.

Cash movements include:

* Deposit
* Withdrawal
* Transfer
* Buy
* Sell

Never infer cash without transaction support.

────────────────────────────

## P&L Rules

Support:

* Realized P&L
* Unrealized P&L

Realized P&L comes from closed positions.

Unrealized P&L comes from open positions.

Never mix the two.

────────────────────────────

## Multi-Currency Rules

Portfolio may contain:

* SAR
* USD
* AED
* EUR

Portfolio-level metrics require FX conversion first.

Never aggregate mixed currencies directly.

────────────────────────────

## Market Support

Supported markets include:

* Saudi
* US

Market filters must never affect accounting logic.

Market filters affect UI and reporting only.

────────────────────────────

## Research Separation

Research engines are read-only.

Research must never:

* Create transactions
* Modify holdings
* Modify accounts
* Modify valuation

Research is separate from accounting.
