---
name: Cold-start price cache persistence
description: Why daily-Δ disappeared after restart even within 60-min window, and the fix pattern.
---

## The Problem

`save_to_session()` in `market_prices.py` wrote price data (all `daily_change_pct` values) only to `st.session_state["mp_price_cache"]` (in-memory). The refresh timestamp was written to `portfolio/price_refresh_ts.json` (disk). On app restart, session state is wiped, so only the timestamp survived — the "refreshed N min ago" badge appeared correctly but no Δ values were shown on Portfolio/Allocation KPI or Balance Sheet.

## The Fix

- `save_price_cache(results)` — serialises the full `MarketData` dict to `portfolio/price_cache.json` via `dataclasses.asdict()`; called from `save_to_session()` alongside `save_refresh_ts()`.
- `load_price_cache()` — reads the JSON and reconstructs `MarketData` objects via `MarketData(**d)`; returns `{}` on any error.
- Cold-start block in `app.py` (`render_global_header`): after restoring the epoch from disk, calls `load_price_cache()` and writes the result into `st.session_state["mp_price_cache"]` **only when** cache age < 3600 s and session not already populated.

## How to Apply

**Why:** `st.session_state` is ephemeral — any restart wipes it. Any data that needs to survive a restart must be persisted to disk.

**Pattern:** For every piece of data that should survive a restart, write it to disk at save time and restore it at cold-start time. Gate the restore on a freshness check to avoid showing stale data.

**After a restart:** module imports pick up the new `load_price_cache` name automatically — no additional steps needed, but the Streamlit workflow must be **restarted** (not just reloaded) if `market_prices.py` itself was changed while the server was running, because Python caches modules at the process level.
