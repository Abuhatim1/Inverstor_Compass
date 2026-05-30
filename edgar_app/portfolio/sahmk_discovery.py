"""
sahmk_discovery.py
------------------
SAHMK Discovery Engine + Local Storage Layer.

Discovery
---------
Probes every endpoint available under the current SAHMK subscription and
reports exactly what data is accessible for a given Saudi symbol.

Storage
-------
Persists successful endpoint responses to disk under:
    data/sahmk_discovery/{symbol}/{dataset_slug}/

Each file is named:
    {dataset_slug}_{YYYYMMDD_HHMMSS}.json

FIFO retention: newest 3 files per (symbol, dataset) kept; older deleted.

Design rules
------------
- Never raises.  All failures are captured in the report / returned as None.
- Does NOT use sahmk_client's cache — live HTTP for accurate discovery.
- Does NOT read, write, or affect Holdings, Valuation, Accounts, Transactions,
  FIFO accounting, Performance Engine, or Portfolio Totals.
- Pure discovery + storage.

Output schema (discover())
--------------------------
{
    "symbol":               str,
    "source":               "SAHMK",
    "discovered_at":        str,
    "api_configured":       bool,
    "available_datasets":   list[str],
    "unavailable_datasets": list[str],
    "endpoint_results":     list[EndpointResult],
    "summary_table":        list[dict],
}

Stored file content
-------------------
{
    "symbol":           str,
    "source":           "SAHMK",
    "endpoint":         str,
    "fetched_at":       str,
    "dataset":          str,
    "status":           "success",
    "available_fields": list[str],
    "raw_response":     any,
}
"""

from __future__ import annotations

import json as _json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

# ── Storage root (relative to this file's parent = edgar_app/) ───────────────

_STORAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sahmk_discovery",
)

_FIFO_KEEP = 3   # newest N files retained per (symbol, dataset)

# ── Endpoint catalogue ─────────────────────────────────────────────────────────
# (name, path_template, symbol_required, extra_params)
_ENDPOINTS: list[tuple[str, str, bool, dict]] = [
    ("Quote",            "quote/{symbol}/",            True,  {}),
    ("Historical Prices","historical/{symbol}",         True,  {"period": "1y", "interval": "1d"}),
    ("Company Info",     "company/{symbol}/info",       True,  {}),
    ("Financials",       "company/{symbol}/financials", True,  {}),
    ("Ratios",           "company/{symbol}/ratios",     True,  {}),
    ("Dividends",        "company/{symbol}/dividends",  True,  {}),
    ("Market Summary",   "market/summary",              False, {}),
    ("Market Events",    "market/events",               False, {}),
]

_MAX_SAMPLE_FIELDS  = 10
_MAX_SAMPLE_STR_LEN = 120


# ══════════════════════════════════════════════════════════════════════════════
# Low-level HTTP prober
# ══════════════════════════════════════════════════════════════════════════════

def _probe_endpoint(path: str, params: dict, *, timeout: int = 15) -> dict:
    """Single GET request; returns raw probe dict. Never raises."""
    base_url = os.environ.get("SAHMK_BASE_URL", "https://app.sahmk.sa/api/v1").rstrip("/")
    api_key  = os.environ.get("SAHMK_API_KEY", "").strip()

    result: dict[str, Any] = {
        "path":                path,
        "http_status":         None,
        "success":             False,
        "error":               None,
        "response_size_bytes": 0,
        "raw_type":            "null",
        "record_count":        None,
        "available_fields":    [],
        "sample_values":       {},
        "raw_response":        None,
    }

    if not api_key:
        result["error"] = "SAHMK_API_KEY not configured"
        return result

    url = f"{base_url}/{path.lstrip('/')}"
    if params:
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "X-API-Key":  api_key,
                "Accept":     "application/json",
                "User-Agent": "Bousala-Discovery/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
            result["http_status"]         = resp.status
            result["response_size_bytes"] = len(raw_bytes)
            parsed = _json.loads(raw_bytes.decode("utf-8", errors="replace"))
            result["raw_response"] = parsed
            result["success"] = True
            _extract_fields(parsed, result)

    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        try:
            body = exc.read().decode("utf-8", errors="replace")
            result["error"] = f"HTTP {exc.code} — {body[:200]}"
        except Exception:
            result["error"] = f"HTTP {exc.code}"

    except urllib.error.URLError as exc:
        result["error"] = f"Network error — {exc.reason}"

    except _json.JSONDecodeError as exc:
        result["success"] = False
        result["error"]   = f"JSON parse error — {exc}"

    except Exception as exc:
        result["error"] = str(exc)[:200]

    return result


def _extract_fields(parsed: Any, result: dict) -> None:
    if isinstance(parsed, dict):
        result["raw_type"]         = "dict"
        result["available_fields"] = list(parsed.keys())
        result["sample_values"]    = _sample_dict(parsed)
    elif isinstance(parsed, list):
        result["raw_type"]    = "list"
        result["record_count"] = len(parsed)
        if parsed and isinstance(parsed[0], dict):
            result["available_fields"] = list(parsed[0].keys())
            result["sample_values"]    = _sample_dict(parsed[0])
        elif parsed:
            result["available_fields"] = ["<scalar>"]
            result["sample_values"]    = {"<value>": _truncate(parsed[0])}
    else:
        result["raw_type"] = "null"


def _sample_dict(d: dict) -> dict:
    return {k: _truncate(v) for k, v in list(d.items())[:_MAX_SAMPLE_FIELDS]}


def _truncate(v: Any) -> Any:
    if isinstance(v, str) and len(v) > _MAX_SAMPLE_STR_LEN:
        return v[:_MAX_SAMPLE_STR_LEN] + "…"
    if isinstance(v, (list, dict)):
        s = str(v)
        return (s[:_MAX_SAMPLE_STR_LEN] + "…") if len(s) > _MAX_SAMPLE_STR_LEN else s
    return v


# ══════════════════════════════════════════════════════════════════════════════
# Discovery
# ══════════════════════════════════════════════════════════════════════════════

def discover(symbol: str, *, timeout: int = 15) -> dict:
    """
    Probe every SAHMK endpoint for *symbol* and return a discovery report.
    Never raises.
    """
    symbol = (symbol or "").strip()
    api_key = os.environ.get("SAHMK_API_KEY", "").strip()
    discovered_at = datetime.now().isoformat()

    endpoint_results: list[dict] = []

    for name, path_tmpl, sym_required, params in _ENDPOINTS:
        if sym_required:
            if not symbol:
                endpoint_results.append({
                    "endpoint_name":       name,
                    "path":                path_tmpl,
                    "symbol_required":     True,
                    "http_status":         None,
                    "success":             False,
                    "error":               "No symbol supplied",
                    "response_size_bytes": 0,
                    "raw_type":            "null",
                    "record_count":        None,
                    "available_fields":    [],
                    "sample_values":       {},
                })
                continue
            path = path_tmpl.replace("{symbol}", symbol)
        else:
            path = path_tmpl

        probe = _probe_endpoint(path, params, timeout=timeout)
        endpoint_results.append({
            "endpoint_name":       name,
            "path":                path,
            "symbol_required":     sym_required,
            "http_status":         probe["http_status"],
            "success":             probe["success"],
            "error":               probe["error"],
            "response_size_bytes": probe["response_size_bytes"],
            "raw_type":            probe["raw_type"],
            "record_count":        probe["record_count"],
            "available_fields":    probe["available_fields"],
            "sample_values":       probe["sample_values"],
            "raw_response":        probe["raw_response"],
        })

    available   = [r["endpoint_name"] for r in endpoint_results if r["success"]]
    unavailable = [r["endpoint_name"] for r in endpoint_results if not r["success"]]

    summary_table = [
        {
            "dataset":  r["endpoint_name"],
            "status":   "✅ Available" if r["success"] else "❌ Not Available",
            "fields":   len(r["available_fields"]),
            "records":  (
                r["record_count"] if r["record_count"] is not None
                else (1 if r["success"] and r["raw_type"] == "dict" else "—")
            ),
            "http":     r["http_status"] if r["http_status"] is not None else "—",
        }
        for r in endpoint_results
    ]

    return {
        "symbol":               symbol,
        "source":               "SAHMK",
        "discovered_at":        discovered_at,
        "api_configured":       bool(api_key),
        "available_datasets":   available,
        "unavailable_datasets": unavailable,
        "endpoint_results":     endpoint_results,
        "summary_table":        summary_table,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Storage helpers
# ══════════════════════════════════════════════════════════════════════════════

def _dataset_slug(name: str) -> str:
    """Convert a dataset display name to a filesystem-safe slug."""
    return name.lower().replace(" ", "_").replace("/", "_")


def _dataset_dir(symbol: str, dataset_name: str, root: str = _STORAGE_ROOT) -> str:
    return os.path.join(root, symbol, _dataset_slug(dataset_name))


def _apply_fifo_retention(dirpath: str, keep: int = _FIFO_KEEP) -> None:
    """Keep the newest *keep* .json files in dirpath; delete the rest."""
    try:
        files = sorted(
            [f for f in os.listdir(dirpath) if f.endswith(".json")],
            reverse=True,   # lexicographic desc = newest first (YYYYMMDD_HHMMSS)
        )
        for old in files[keep:]:
            try:
                os.remove(os.path.join(dirpath, old))
            except OSError:
                pass
    except OSError:
        pass


def store_dataset(
    symbol: str,
    ep: dict,
    *,
    root: str = _STORAGE_ROOT,
) -> str | None:
    """
    Persist a successful endpoint result to disk.

    ep    — one entry from discover()["endpoint_results"]
    root  — override storage root (used in tests)

    Returns the file path written, or None if ep was not successful.
    """
    if not ep.get("success"):
        return None

    name     = ep["endpoint_name"]
    dirpath  = _dataset_dir(symbol, name, root)
    os.makedirs(dirpath, exist_ok=True)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug     = _dataset_slug(name)
    fname    = f"{slug}_{ts}.json"
    fpath    = os.path.join(dirpath, fname)

    payload  = {
        "symbol":           symbol,
        "source":           "SAHMK",
        "endpoint":         ep["path"],
        "fetched_at":       datetime.now().isoformat(),
        "dataset":          name,
        "status":           "success",
        "available_fields": ep["available_fields"],
        "raw_response":     ep.get("raw_response"),
    }

    try:
        with open(fpath, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    except OSError:
        return None

    _apply_fifo_retention(dirpath, keep=_FIFO_KEEP)
    return fpath


def download_and_store(symbol: str, *, timeout: int = 15, root: str = _STORAGE_ROOT) -> dict:
    """
    Run full discovery for *symbol*, store every successful endpoint response,
    also store the discovery report itself, and return a storage summary.

    Returns:
    {
        "symbol":         str,
        "stored":         list[str],    # file paths written
        "skipped":        list[str],    # dataset names with no data
        "discovery":      dict,         # full discover() report
    }
    """
    report    = discover(symbol, timeout=timeout)
    stored    = []
    skipped   = []

    for ep in report["endpoint_results"]:
        if ep["success"]:
            path = store_dataset(symbol, ep, root=root)
            if path:
                stored.append(path)
        else:
            skipped.append(ep["endpoint_name"])

    # Also store the discovery report itself
    disc_ep = {
        "endpoint_name":   "Discovery Report",
        "path":            "discovery/report",
        "success":         True,
        "available_fields": list(report.keys()),
        "raw_response":    {
            k: v for k, v in report.items()
            if k != "endpoint_results"   # keep compact
        },
    }
    disc_ep_full = {**disc_ep, "symbol_required": True, "http_status": None,
                    "error": None, "response_size_bytes": 0,
                    "raw_type": "dict", "record_count": None, "sample_values": {}}
    dp = store_dataset(symbol, disc_ep_full, root=root)
    if dp:
        stored.append(dp)

    return {
        "symbol":    symbol,
        "stored":    stored,
        "skipped":   skipped,
        "discovery": report,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Listing and loading stored data
# ══════════════════════════════════════════════════════════════════════════════

def list_stored(symbol: str = "", root: str = _STORAGE_ROOT) -> list[dict]:
    """
    Return metadata for all stored files.

    symbol  — if provided, filter to that symbol only.
    root    — override storage root (used in tests).

    Each entry:
    {
        "symbol":      str,
        "dataset":     str,          # dataset display name (from slug)
        "slug":        str,          # filesystem slug
        "filename":    str,
        "filepath":    str,
        "fetched_at":  str,          # from YYYYMMDD_HHMMSS in filename
        "size_bytes":  int,
    }
    """
    results: list[dict] = []
    if not os.path.isdir(root):
        return results

    sym_dirs = [symbol] if symbol else _safe_listdir(root)
    for sym in sym_dirs:
        sym_path = os.path.join(root, sym)
        if not os.path.isdir(sym_path):
            continue
        for slug in _safe_listdir(sym_path):
            ds_path = os.path.join(sym_path, slug)
            if not os.path.isdir(ds_path):
                continue
            dataset_display = slug.replace("_", " ").title()
            for fname in sorted(_safe_listdir(ds_path), reverse=True):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(ds_path, fname)
                ts    = _ts_from_filename(fname)
                size  = 0
                try:
                    size = os.path.getsize(fpath)
                except OSError:
                    pass
                results.append({
                    "symbol":     sym,
                    "dataset":    dataset_display,
                    "slug":       slug,
                    "filename":   fname,
                    "filepath":   fpath,
                    "fetched_at": ts,
                    "size_bytes": size,
                })

    return results


def load_stored_dataset(filepath: str) -> dict | None:
    """Load and parse a stored dataset file. Never raises. Returns None on error."""
    try:
        with open(filepath, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return None


def _safe_listdir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _ts_from_filename(fname: str) -> str:
    """Extract a human-readable timestamp from e.g. quote_20260530_173000.json."""
    try:
        parts = fname.replace(".json", "").split("_")
        # Last two parts are YYYYMMDD and HHMMSS
        date_part = parts[-2]
        time_part = parts[-1]
        return (
            f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} "
            f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
        )
    except Exception:
        return fname


# ══════════════════════════════════════════════════════════════════════════════
# Serialisation
# ══════════════════════════════════════════════════════════════════════════════

def report_to_json(report: dict, *, indent: int = 2) -> str:
    """Serialise a discovery report to a JSON string. Never raises."""
    try:
        return _json.dumps(report, indent=indent, ensure_ascii=False, default=str)
    except Exception as exc:
        return _json.dumps({"error": f"Serialisation failed — {exc}"})
