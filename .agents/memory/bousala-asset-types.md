---
name: Bousala ASSET_TYPES canonical source
description: Where ASSET_TYPES is defined and how ALLOWED_ASSET_TYPES in bulk upload stays in sync.
---

**Canonical source:** `portfolio/holdings.py` — `ASSET_TYPES: list[str]`

Current list (14 items): Stock, ETF, REIT, Mutual Fund, Sukuk, Bond, Cash, Precious Metal, Commodity, Real Estate, Private Equity, Private Asset, Crypto, Other

**Bulk upload sync:** `ALLOWED_ASSET_TYPES = set(ASSET_TYPES)` inside `_dlg_bulk_upload()` — derives automatically, so adding a type to ASSET_TYPES covers both selectbox and bulk upload validation in one edit.

**Backward compat:** upsert_holding does not validate asset_type against ASSET_TYPES. Old values like "Fund", "Gold", "Silver" round-trip fine. Only UI selectbox and bulk upload enforce the list.

**Why:** Gold and Silver were removed as standalone types (superseded by Precious Metal). Old holdings remain valid.
