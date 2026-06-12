---
name: BS snapshot write-once design
description: Why bs_snapshot must be write-once-per-day and never always-overwrite.
---

## Rule
`record_bs_snapshot_if_needed` must write today's entry **only on the first render of a new day**. A second call with different values must be a no-op (skip write if today's entry already exists).

**Why:** The always-overwrite approach was tried and caused a persistent phantom -20% delta. Root cause traced: during development/coding sessions, test runs or intermediate app renders temporarily modified holdings.json (e.g., test fixtures with synthetic prices, or holdings in a partially-updated state). The always-overwrite snapshot captured those inflated values. On the next day's startup, the comparison was inflated-yesterday vs correct-today = large phantom delta. The Jun 11 SAR snapshot showed port=1,590,306 while the simultaneously-written Jun 11 USD snapshot implied only 1,258,169 SAR-equivalent — a 332k SAR inconsistency proving the two entries were written at different moments in different portfolio states.

**How to apply:**
- In `record_bs_snapshot_if_needed`: check if `(today, ccy)` entry already exists before writing. If yes, skip the write entirely.
- BSS02 test verifies: two calls in the same day → only one entry, value = first call's value (not second).
- Never reintroduce always-overwrite semantics, even if the intention is "capture post-refresh prices."

**Contrast with Allocation tab:** The Allocation tab Priority 2 fallback READS the snapshot but never writes it — that is safe. Only the BS tab section calls `record_bs_snapshot_if_needed`.

**What the write-once baseline represents:** First-render-of-day prices = holdings.json `current_price` as of the user's most recent price refresh from a previous session = last saved market close. Tomorrow's delta = tomorrow's first-render prices vs today's first-render prices = honest market movement since last refresh.
