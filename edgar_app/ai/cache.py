"""
ai/cache.py
-----------
Two independent protections:

1. Analysis cache  — saves every successful live result keyed by filing
   accession number so the same filing is never sent to OpenAI twice.
   File: edgar_app/ai/analysis_cache.json  (max 200 entries)

2. Daily usage tracker — counts live OpenAI calls made today and
   enforces a configurable daily cap.
   File: edgar_app/ai/usage.json  (keeps last 30 days)

Both files live next to this module and are created on first write.
"""

import json
import os
from datetime import date

_DIR        = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_DIR, "analysis_cache.json")
_USAGE_FILE = os.path.join(_DIR, "usage.json")

# Maximum cached entries before the oldest are evicted
_MAX_ENTRIES = 200

# Maximum live OpenAI calls per calendar day (demo mode does NOT count)
DAILY_LIMIT = 20


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis cache
# ═══════════════════════════════════════════════════════════════════════════════

def _load_cache() -> dict:
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_cached(cache_key: str) -> dict | None:
    """
    Return the cached result dict for this key, or None if not cached.

    The dict mirrors AnalysisResult fields plus a 'cached_at' date string.
    """
    return _load_cache().get(cache_key)


def save_to_cache(cache_key: str, result_dict: dict) -> None:
    """
    Store a result dict under cache_key.
    Evicts the oldest entries if the cache exceeds _MAX_ENTRIES.
    """
    result_dict["cached_at"] = date.today().isoformat()
    cache = _load_cache()
    cache[cache_key] = result_dict

    # Evict oldest when over the limit
    if len(cache) > _MAX_ENTRIES:
        ordered = sorted(
            cache.keys(),
            key=lambda k: cache[k].get("cached_at", "1970-01-01"),
            reverse=True,
        )
        cache = {k: cache[k] for k in ordered[:_MAX_ENTRIES]}

    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def cache_size() -> int:
    """Return the number of currently cached analyses."""
    return len(_load_cache())


# ═══════════════════════════════════════════════════════════════════════════════
# Daily usage tracker
# ═══════════════════════════════════════════════════════════════════════════════

def _load_usage() -> dict:
    if not os.path.exists(_USAGE_FILE):
        return {}
    try:
        with open(_USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_today_count() -> int:
    """Return the number of live OpenAI calls made today."""
    today = date.today().isoformat()
    return _load_usage().get(today, {}).get("count", 0)


def is_limit_reached() -> bool:
    """Return True when today's live call count has hit DAILY_LIMIT."""
    return get_today_count() >= DAILY_LIMIT


def increment_usage() -> int:
    """
    Add 1 to today's count, save, and return the new count.
    Automatically trims the file to the last 30 days.
    """
    usage = _load_usage()
    today = date.today().isoformat()
    count = usage.get(today, {}).get("count", 0) + 1
    usage[today] = {"count": count}

    # Keep only the most recent 30 days
    recent_keys = sorted(usage.keys(), reverse=True)[:30]
    usage = {k: usage[k] for k in recent_keys}

    os.makedirs(os.path.dirname(_USAGE_FILE), exist_ok=True)
    with open(_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, indent=2)
    return count
