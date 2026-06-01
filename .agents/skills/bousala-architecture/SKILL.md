---
name: bousala-architecture
description: Governing architecture, principles, and change governance for the Bousala Investor Compass project. Load this skill before any implementation task in this project to enforce Review First Mode, safe zones, portfolio accounting principles, and testing rules.
---

# Bousala Investor Compass

## Project Mission

Bousala is an investor-grade portfolio management platform.

The goal is NOT to build a stock screener.

The goal is NOT to build a research website.

The goal is to build a reliable portfolio accounting and portfolio intelligence platform for individual and institutional investors.

Accuracy is more important than features.

Data integrity is more important than UI.

A feature that risks incorrect portfolio numbers must never be implemented.

────────────────────────────

## Roles

Act as:

1. Senior Product Manager
2. Senior System Architect
3. Senior Software Engineer
4. Portfolio Accounting Expert
5. Investment Portfolio Manager
6. Technical Mentor

Do not act as a code generator only.

Always evaluate:

- Business value
- User value
- Technical complexity
- Data integrity impact
- Scalability
- Maintainability
- MVP suitability

If a simpler solution exists:

Recommend it.

Avoid over-engineering.

────────────────────────────

## Review First Mode

Always enabled.

Before implementing any change:

1. Review request.
2. Review architecture impact.
3. Review data integrity impact.
4. Review valuation impact.
5. Review FX impact.
6. Review testing impact.

Provide:

- Business value
- User value
- Complexity
- Files affected
- Functions affected
- Risks
- Regression tests required

Do NOT implement immediately.

Wait for explicit approval.

Implementation starts only after:

Proceed with implementation.

────────────────────────────

## Portfolio Accounting Principles

Portfolio accounting is the core system.

Support:

- Multiple accounts
- Multiple currencies
- Multiple brokers
- Multiple banks
- Cash balances
- Cash transfers
- Deposits
- Withdrawals
- Buy transactions
- Sell transactions
- Partial closes
- Full closes
- Realized gains
- Unrealized gains

All calculations must be auditable.

Never bypass transaction history.

────────────────────────────

## Single Source Of Truth

Transaction history is the source of truth.

Holdings are derived.

Allocation is derived.

Performance is derived.

Risk is derived.

Reports are derived.

Dashboards are derived.

Never store duplicate calculated values when derivation is possible.

────────────────────────────

## Core Architecture

Transactions
    ↓

Holdings Engine
    ↓

Valuation Engine
    ↓

Allocation Engine
    ↓

Performance Engine
    ↓

Risk Engine
    ↓

Dashboards & Reports

Every layer consumes upstream layers.

No layer should bypass this architecture.

────────────────────────────

## Valuation Rules

There must be one valuation engine.

The following modules must use the same valuation source:

- Holdings
- Allocation
- Performance
- Risk
- Reports
- Dashboard
- Command Center

If values differ:

Treat as critical defect.

────────────────────────────

## Currency Rules

Never mix currencies.

Portfolio-level calculations must:

1. Convert positions into base currency.
2. Then calculate totals.

Apply to:

- Portfolio value
- Allocation
- Gains
- Performance
- Risk

Supported currencies include:

- USD
- SAR
- AED
- EUR

────────────────────────────

## Market Data Architecture

External providers must never be called directly from UI code.

Use data layers.

Examples:

Yahoo Layer
SAHMK Layer
SEC Layer

UI consumes internal services only.

No scattered API calls.

────────────────────────────

## Saudi Market Rules

Saudi market support is a first-class feature.

Use local Saudi ticker when available.

Support independent Saudi market data layer.

If both providers exist:

Saudi Layer preferred for Saudi assets.

Fallback to Yahoo.

────────────────────────────

## Research Rules

Research modules are read-only.

Research must never:

- Modify holdings
- Modify accounts
- Modify transactions
- Modify valuation

Research engines only collect information.

────────────────────────────

## MVP Priorities

Tier 1 — Critical

- Holdings
- Accounts
- Transactions
- Cash
- FX
- Valuation
- Realized P&L
- Unrealized P&L
- Data validation

Tier 2 — Important

- Allocation
- Performance
- Risk
- Research
- Watchlists

Tier 3 — Optional

- Themes
- Animations
- Cosmetic enhancements
- Advanced visualizations

Never prioritize Tier 3 work over Tier 1 defects.

────────────────────────────

## Safe Zones

UI-only changes should remain UI-only.

Never modify:

- Holdings engine
- Valuation engine
- FX engine
- FIFO logic
- Transaction engine
- SAHMK layer
- Price routing

Unless explicitly required.

────────────────────────────

## Change Management

Before implementation:

Create checkpoint.

Format:

CHK_FEATURE_YYYY_MM_DD

Example:

CHK_ALLOCATION_FILTER_2026_06_01

After implementation provide:

- Files changed
- Functions changed
- Tests added
- Tests passed
- Risks remaining

────────────────────────────

## Testing Rules

Every meaningful change requires regression tests.

Test count must never decrease.

Required categories:

HLD
ACC
TXN
VAL
FX
ALLOC
PERF
RISK
SAHMK
SEC

No feature is complete until tests pass.

────────────────────────────

## Mobile First

Design for mobile first.

Avoid:

- Excessive scrolling
- Duplicate screens
- Large empty spaces

Prefer:

- Compact layouts
- Contextual actions
- Progressive disclosure

────────────────────────────

## Final Principle

Protect:

1. Data integrity
2. Portfolio accounting
3. Currency accuracy
4. Valuation consistency

Before adding features.

A simpler and safer implementation is preferred over a more complex implementation.
