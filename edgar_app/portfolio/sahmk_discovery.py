"""
sahmk_discovery.py
------------------
SAHMK Discovery Engine.

Probes every endpoint available under the current SAHMK subscription and
reports exactly what data is accessible for a given Saudi symbol.

Design rules
------------
- Never raises.  All failures are captured and returned in the report.
- Does NOT use sahmk_client's cache so each probe reflects live API state.
- Does NOT modify any portfolio, holding, valuation, or account data.
- Pure discovery: query → capture → report.

Output schema
-------------
{
    "symbol":               str,          # queried symbol e.g. "2222"
    "source":               "SAHMK",
    "discovered_at":        str,          # ISO timestamp
    "api_configured":       bool,
    "available_datasets":   list[str],    # names of endpoints that responded
    "unavailable_datasets": list[str],    # names that returned no data
    "endpoint_results":     list[dict],   # full per-endpoint detail
    "summary_table":        list[dict],   # [{"dataset", "status", "fields", "records"}]
}

Each entry in endpoint_results
-------------------------------
{
    "endpoint_name":        str,
    "path":                 str,          # URL path (symbol substituted)
    "symbol_required":      bool,
    "http_status":          int | None,   # None = network error or not configured
    "success":              bool,
    "error":                str | None,
    "response_size_bytes":  int,
    "raw_type":             str,          # "dict" | "list" | "null"
    "record_count":         int | None,   # for list responses
    "available_fields":     list[str],    # top-level keys / item keys
    "sample_values":        dict,         # up to 10 field→value pairs (truncated)
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

# ── Endpoint catalogue ─────────────────────────────────────────────────────────
# (name, path_template, symbol_required, extra_params)
_ENDPOINTS: list[tuple[str, str, bool, dict]] = [
    ("Quote",           "quote/{symbol}/",            True,  {}),
    ("Historical Prices","historical/{symbol}",        True,  {"period": "1y", "interval": "1d"}),
    ("Company Info",    "company/{symbol}/info",       True,  {}),
    ("Financials",      "company/{symbol}/financials", True,  {}),
    ("Ratios",          "company/{symbol}/ratios",     True,  {}),
    ("Dividends",       "company/{symbol}/dividends",  True,  {}),
    ("Market Summary",  "market/summary",              False, {}),
    ("Market Events",   "market/events",               False, {}),
]

_MAX_SAMPLE_FIELDS  = 10   # max fields shown in sample_values
_MAX_SAMPLE_STR_LEN = 120  # truncate long strings in sample values


# ── Low-level prober (independent of sahmk_client cache) ──────────────────────

def _probe_endpoint(
    path: str,
    params: dict,
    *,
    timeout: int = 15,
) -> dict:
    """
    Make a single GET request and return a raw probe result dict.

    Never raises — all errors are captured in the result.
    """
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
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            parsed = _json.loads(raw_text)
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
    """Populate raw_type, record_count, available_fields, sample_values."""
    if isinstance(parsed, dict):
        result["raw_type"] = "dict"
        fields = list(parsed.keys())
        result["available_fields"] = fields
        result["sample_values"]    = _sample_dict(parsed)

    elif isinstance(parsed, list):
        result["raw_type"]    = "list"
        result["record_count"] = len(parsed)
        if parsed and isinstance(parsed[0], dict):
            fields = list(parsed[0].keys())
            result["available_fields"] = fields
            result["sample_values"]    = _sample_dict(parsed[0])
        elif parsed:
            result["available_fields"] = ["<scalar>"]
            result["sample_values"]    = {"<value>": _truncate(parsed[0])}

    else:
        result["raw_type"] = "null"


def _sample_dict(d: dict) -> dict:
    """Return up to _MAX_SAMPLE_FIELDS truncated key→value pairs."""
    out: dict = {}
    for k, v in list(d.items())[:_MAX_SAMPLE_FIELDS]:
        out[k] = _truncate(v)
    return out


def _truncate(v: Any) -> Any:
    if isinstance(v, str) and len(v) > _MAX_SAMPLE_STR_LEN:
        return v[:_MAX_SAMPLE_STR_LEN] + "…"
    if isinstance(v, (list, dict)):
        s = str(v)
        return (s[:_MAX_SAMPLE_STR_LEN] + "…") if len(s) > _MAX_SAMPLE_STR_LEN else s
    return v


# ── Public API ─────────────────────────────────────────────────────────────────

def discover(symbol: str, *, timeout: int = 15) -> dict:
    """
    Probe every SAHMK endpoint for *symbol* and return a discovery report.

    symbol  — local Saudi exchange symbol, e.g. "2222"
    timeout — per-endpoint HTTP timeout in seconds

    Returns the standardised report dict described in the module docstring.
    Never raises.
    """
    symbol = (symbol or "").strip()
    api_key = os.environ.get("SAHMK_API_KEY", "").strip()
    discovered_at = datetime.now().isoformat()

    endpoint_results: list[dict] = []

    for name, path_tmpl, sym_required, params in _ENDPOINTS:
        # Resolve path — skip symbol-required endpoints if symbol is blank
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
        })

    available   = [r["endpoint_name"] for r in endpoint_results if r["success"]]
    unavailable = [r["endpoint_name"] for r in endpoint_results if not r["success"]]

    summary_table = [
        {
            "dataset":  r["endpoint_name"],
            "status":   "✅ Available" if r["success"] else "❌ Not Available",
            "fields":   len(r["available_fields"]),
            "records":  r["record_count"] if r["record_count"] is not None else (
                1 if r["success"] and r["raw_type"] == "dict" else "—"
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


def report_to_json(report: dict, *, indent: int = 2) -> str:
    """Serialise a discovery report to a JSON string. Never raises."""
    try:
        return _json.dumps(report, indent=indent, ensure_ascii=False, default=str)
    except Exception as exc:
        return _json.dumps({"error": f"Serialisation failed — {exc}"})
