---
name: Bousala test pattern conventions
description: How source-scan tests in dev_test_runner.py match app.py code; what breaks them.
---

Source-scan tests (ALLOC-SCOPE-*, HLD-UI-*, etc.) read app.py as text and do substring matching.

**Rule:** Never use exact whitespace-aligned strings as match targets.
When app.py variable alignment changes (e.g. `_all_sectors   =` to `_all_sectors    =`), exact string tests break silently.

**How to apply:** Prefer token-level patterns:
- Use `'_mkt_df["Sector"]' in _fn` instead of `'_all_sectors   = sorted(_mkt_df["Sector"]'`
- For position-ordering checks, use `.find("_all_sectors")` not `.find("_all_sectors   =")`

**Why:** ALLOC-SCOPE-01 and ALLOC-SCOPE-09 both broke this way when AssetType column was added and variable alignment was adjusted for readability.
