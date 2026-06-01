---
name: Transaction identity
description: Transaction dataclass has transaction_id (TXN_xxxxxxxx) and asset_id; auto-generated in record_transaction, back-filled for old records in load_transactions.
---

## Rule
Every `Transaction` has two identity fields:
- `transaction_id: str` — format `TXN_` + 8 hex chars (e.g. `TXN_a1b2c3d4`); immutable after creation
- `asset_id: str` — links to `Holding.asset_id`; populated at record time from `_eff_asset_id`

**Why:** Audit trail requires a stable per-transaction key. `asset_id` on Transaction allows joining to holdings without scanning by ticker.

## How to apply
- `record_transaction()` sets `transaction_id = "TXN_" + str(uuid.uuid4())[:8]` and `asset_id = _eff_asset_id`.
- `load_transactions()` back-fills `transaction_id` for old records that pre-date the field (same `TXN_` format).
- `transaction_id` is never shown in normal UI — only in audit/history views.
- `Transaction.asset_id` may be empty string for very old records that were loaded before back-fill logic existed; always check before using.
