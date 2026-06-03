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

## Settlement Rules

Settlements are a third transaction type alongside BUY and SELL.

A settlement is any financial event tied to an investment that is not a buy or a sell.

Examples: dividend received, brokerage fee, tax withholding, zakat, purification payment, miscellaneous correction.

Categories and cash direction:

| Category | Direction | Typical use |
|---|---|---|
| Dividend | + inflow | Cash dividends, fund distributions |
| Fee | - outflow | Brokerage fees, custody charges |
| Tax | - outflow | Withholding tax, capital gains tax |
| Zakat | - outflow | Annual zakat on investment holdings |
| Purification | - outflow | Haram income purification payment |
| Adjustment | +/- either | Corrections, refunds, miscellaneous |

A settlement NEVER changes:

- share quantity
- avg_cost or cost_basis
- FIFO lots or realized P&L

Settlements affect total return, XIRR, income/expense metrics, cash balance, and cash ledger audit trail.

Settlement scope:

- Asset-level: linked to a specific holding via asset_id
- Portfolio-level: not linked to any holding (asset_id = "")

────────────────────────────

## FIFO Engine Rules

The FIFO engine in closed_holdings.py processes only side == "BUY" and side == "SELL".

When a sell is recorded:

1. _build_fifo_queue() replays ALL transaction history for that ticker
2. Builds a queue of remaining open buy lots (oldest first)
3. execute_sell_fifo() matches sell quantity against the queue
4. Creates ClosedLot records with per-lot realized P&L
5. Fees are prorated proportionally across matched lots
6. Quantity is reduced; if zero, position shows as closed

The FIFO queue is rebuilt from scratch on every sell — no stale state.

Holdings added via "Record Existing Holding" (Mode A / no BUY transaction) use a synthetic fallback lot at avg_cost for FIFO matching.

────────────────────────────

## Research Separation

Research engines are read-only.

Research must never:

* Create transactions
* Modify holdings
* Modify accounts
* Modify valuation

Research is separate from accounting.
