---
name: Asset-ID primary key
description: Holdings are keyed by AST_NNNNNN sequential IDs; migration re-IDs any non-AST_ entry on load; counter persisted in _asset_counter.json.
---

## Rule
Holdings dict (in memory and on disk) is keyed by `asset_id` in `AST_NNNNNN` format (e.g. `AST_000001`).
`Holding.ticker` is the pricing symbol (optional for manual assets); `Holding.asset_id` is the stable unique key.
`Holding.company_name` is the user-facing asset name (shown in UI as "Asset name").

**Why:** Two assets may share the same pricing ticker. Sequential AST_ IDs are human-readable and never confused with ticker symbols. The `AST_` prefix makes format validation unambiguous.

## Counter
Counter file: `edgar_app/portfolio/_asset_counter.json` → `{"next": N}`
On first call (no counter file): `_scan_max_asset_num()` scans `holdings.json` for the highest `AST_NNNNNN` and seeds from max+1.

## Migration (load_holdings)
Any entry whose `asset_id` does not match `^AST_\d{6}$` (old 8-char UUIDs, old ticker-string keys, or missing) gets a fresh `_gen_asset_id()`. Migrated data is written back to the real file only (`path is None`).

## How to apply
- Loop variable: `for asset_id, h in holdings.items()` — never `for ticker, h`.
- Display always uses `h.ticker` and `h.company_name`; internal targeting uses `asset_id`.
- `upsert_holding(asset_id=..., ...)` bypasses ticker scan; `upsert_holding(ticker=..., ...)` scans by ticker.
- `record_transaction(ticker=h.ticker, asset_id=asset_id, ...)` routes to the correct holding.
- `update_current_price(asset_id, price)` — takes `asset_id`, NOT ticker.
- Duplicate ticker guard in "Add New" is a **soft warning**, not a hard block.
- `asset_id` is NEVER shown in any user-facing UI label; all labels say "Asset name" or "Ticker symbol".

## Test isolation
`load_holdings(path=...)`, `save_holdings(holdings, path=...)`, `update_current_price(..., path=...)`, and `upsert_holding(..., path=...)` all accept an optional `path` keyword so tests can use temp files without touching the real holdings.json or _asset_counter.json.
Note: `_gen_asset_id()` still writes to the real `_asset_counter.json` even during tests — this is acceptable since sequential IDs are always unique regardless of starting number.
