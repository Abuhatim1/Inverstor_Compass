---
name: Bousala caching pattern
description: How @st.cache_data is applied to portfolio load/save functions, and how tests must handle cache isolation.
---

## The pattern

**Split pattern** — for load functions with `path=None` test-isolation param:
- Public `load_X(path=None)` → if path: `_load_X_impl(path)`; else: `_load_X_cached()`
- `@st.cache_data(show_spinner=False)` on `_load_X_cached()` which calls `_load_X_impl(_X_FILE)`
- `save_X(..., path=None)`: add `if path is None: _load_X_cached.clear()` after disk write
- Files using split: `holdings.py` (load_holdings), `alt_investments.py` (2 functions), `crowdfunding.py` (3 functions)

**Direct decorator** — for load functions with NO `path=` param:
- Add `@st.cache_data(show_spinner=False)` directly above the function
- `save_X(...)`: add `load_X.clear()` after disk write
- Files using direct: `state.py`, `accounts.py`, `cash_ledger.py`, `closed_holdings.py`, `delta.py`, `risk.py`, `core_thesis.py`, `comparison_store.py`; also `load_transactions` in holdings.py

## Streamlit outside a session

When running tests without a live Streamlit server, `@st.cache_data` logs "No runtime found, using MemoryCacheStorageManager" warnings. This is harmless — the in-memory cache is used and tests pass.

## Test isolation with caching

**Why:** `@st.cache_data` caches on the FUNCTION SIGNATURE (args). `load_X()` with no args always has key `()`. Tests that `patch("module._FILE", tmp_path)` can't invalidate the cache.

**How to apply:**
- Tests using `patch("portfolio.holdings._HOLDINGS_FILE", h_path)` must call `_load_holdings_cached.clear()` + `load_transactions.clear()` BEFORE entering the patch context, and again in a `finally` block after.
- Tests that patch `_pac._ACCOUNTS_FILE` must call `_pac.load_accounts.clear()` immediately after the patch, before calling any function that reads accounts.
- Tests that check for ABSENCE of `@st.cache_data` must be inverted to check for PRESENCE after caching is added.
