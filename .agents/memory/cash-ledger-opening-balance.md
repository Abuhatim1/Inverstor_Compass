---
name: Opening cash must write an INITIAL_BALANCE ledger entry
description: Any code path that sets an account's opening/initial cash must also append a matching INITIAL_BALANCE cash-ledger entry, or performance/XIRR is overstated.
---

# Opening cash ↔ cash-ledger integrity

**Rule:** Whenever a code path creates an account with opening cash > 0 (e.g.
`upsert_account(opening_cash=...)`), it MUST also append a matching
`INITIAL_BALANCE` entry to the cash ledger (`append_cash_entry(...,
transaction_type="INITIAL_BALANCE", ...)`). Setting `Account.cash_balance`
directly without a ledger entry is a data-integrity defect.

**Why:** The cash ledger is the single source of truth for cash. The performance
engine (portfolio/performance.py) builds the external-contribution flow stream
from ledger entries (INITIAL_BALANCE / DEPOSIT = contribution outflow). If
opening cash exists as a bare balance with no ledger entry, it shows up in the
terminal portfolio value with no offsetting contribution → XIRR and growth are
overstated, and any cash audit flags ledger-vs-balance drift. This bit the
inline account-creation path in the Add-Position dialog (it copied only the
upsert_account call, not the INITIAL_BALANCE entry the Accounts tab also writes).

**How to apply:** When adding/duplicating any "create account" flow, mirror the
canonical Accounts-tab pattern: upsert the account, then `if opening_cash > 0:`
append an INITIAL_BALANCE ledger entry. There is a source-scan regression test
(ACCT-INLINE-01) guarding the inline dialog path specifically.
