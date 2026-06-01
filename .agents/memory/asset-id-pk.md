---
name: Asset-ID primary key
description: Holdings are now keyed by an 8-char UUID asset_id, not ticker — enables multiple holdings with the same pricing ticker.
---

## Rule
Holdings dict (in memory and on disk) is keyed by `asset_id` (8-char alphanumeric UUID prefix).
`Holding.ticker` is the pricing symbol; `Holding.asset_id` is the stable unique key.

**Why:** Two assets may share the same pricing ticker (e.g. "Gold Bank Account" and "Physical Gold" both fetch price via GC=F). Keying by ticker collapsed them into one row.

## How to apply
- Any loop over `holdings` uses `for asset_id, h in holdings.items()` — never `for ticker, h`.
- Display always uses `h.ticker`; internal targeting uses `asset_id`.
- `upsert_holding(asset_id=..., ...)` bypasses ticker scan; `upsert_holding(ticker=..., ...)` scans by ticker (used for new holdings).
- `record_transaction(ticker=h.ticker, asset_id=asset_id, ...)` routes to the correct holding.
- `update_current_price(asset_id, price)` — takes asset_id, NOT ticker.
- Duplicate-ticker guard in "Add New" is a **soft warning**, not a hard block.

## Migration
`load_holdings()` auto-migrates old ticker-keyed JSON on first load:
- Entries with no `asset_id`, or with an `asset_id` that is not 8-char alphanumeric, get a fresh `_gen_asset_id()`.
- Migrated data is written back to disk (production path only; test path= param suppresses resave).

## Test isolation
`load_holdings(path=...)` and `update_current_price(..., path=...)` and `save_holdings(holdings, path=...)` all accept an optional `path` keyword so tests can use temp files without touching the real holdings.json.
