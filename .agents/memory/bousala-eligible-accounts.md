---
name: Bousala eligible account types
description: Which account types appear in the Add New Position modal account selector.
---

**Eligible types:** `_ELIGIBLE_ACCT_TYPES = frozenset({"Brokerage", "Crypto", "Other"})`

Defined as a local variable inside `_tab_holdings()` just before `_acct_pairs_for()`.

**Excluded:** Bank, Cash — cannot hold investment positions.

**How applied:** `_acct_pairs_for(currency, eligible_only=True)` filters `active_accounts(currency)` to only account_type values in the eligible set.

**No type annotation:** Must be written as `_ELIGIBLE_ACCT_TYPES = frozenset(...)` (not `_ELIGIBLE_ACCT_TYPES: frozenset[str] = ...`) because ACC-UI-08 regex matches `_ELIGIBLE_ACCT_TYPES\s*[=:]\s*frozenset\(\{` which requires `frozenset(` to immediately follow `=` or `:`.
