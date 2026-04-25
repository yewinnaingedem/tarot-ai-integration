"""
mcp_app/mcp_tools/logs.py

Read and analyze Laravel + Python backend logs.
Token-efficient: deduplicates repeated errors, strips stack traces,
returns compact summary instead of raw entries.
"""

import os
import re
import json
from datetime import datetime, date, timedelta
from collections import Counter
from mcp_app.core import mcp
from mcp_app.permission import is_admin

_LARAVEL_LOG_DIR = "/home/gmbf/Desktop/ai/miniapp-web/storage/logs"
_PYTHON_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "backend.log"
)

# Known error patterns → fix suggestions (no unescaped brackets in patterns)
_FIX_HINTS = [
    (r"Table .+ doesn't exist",          "Run `php artisan migrate` — a DB table is missing."),
    (r"SQLSTATE",                         "Database error. Check DB connection and schema."),
    (r"Class .+ not found",               "Run `composer dump-autoload` — a PHP class is missing."),
    (r"No such file or directory",        "A required file is missing. Check storage paths and symlinks."),
    (r"TokenMismatchException",           "CSRF token expired. User needs to refresh the page."),
    (r"Unauthenticated",                  "Session expired or invalid token. User needs to log in again."),
    (r"Connection refused",               "A service (DB/Redis/Python backend) is not running."),
    (r"Call to .+ on null",               "Null pointer error. A model returned null unexpectedly."),
    (r"Maximum execution time",           "Request timed out. Optimize the slow query or increase PHP timeout."),
    (r"Allowed memory size",              "PHP ran out of memory. Increase `memory_limit` in php.ini."),
    (r"Route .+ not defined",             "A named route is missing. Check `php artisan route:list`."),
    (r"permission denied",                "File permission error. Run `chmod -R 775 storage bootstrap/cache`."),
    (r"Integrity constraint violation",   "Duplicate or invalid DB insert. Check unique constraints."),
]


def _get_fix_hint(message: str) -> str:
    for pattern, hint in _FIX_HINTS:
        if re.search(pattern, message, re.IGNORECASE):
            return hint
    return None


def _parse_laravel_log(path: str) -> list:
    """Parse a Laravel daily log file. Returns compact entries (no stack traces)."""
    try:
        with open(path, "r", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        return []

    entries = []
    # Split on log entry boundaries
    blocks = re.split(r"(?=\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\])", content)
    for block in blocks:
        first_line = block.split("\n")[0].strip()
        m = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \w+\.(\w+): (.+)", first_line)
        if not m:
            continue
        ts, level, message = m.group(1), m.group(2).upper(), m.group(3).strip()
        # Strip JSON context appended to message
        message = re.sub(r'\s*\{.*$', '', message).strip()[:150]

        uid_m = re.search(r'"userId"\s*:\s*(\d+)', block)
        entries.append({
            "ts":      ts,
            "level":   level,
            "msg":     message,
            "user_id": int(uid_m.group(1)) if uid_m else None,
        })
    return entries


def _parse_python_log(target_date: str) -> list:
    entries = []
    _PY_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\w+): (.+?)(?:\s+\{|$)")
    try:
        with open(_PYTHON_LOG_PATH, "r", errors="replace") as f:
            for line in f:
                m = _PY_RE.match(line.strip())
                if m and m.group(1).startswith(target_date):
                    entries.append({
                        "ts":    m.group(1),
                        "level": m.group(2),
                        "msg":   m.group(3)[:150],
                    })
    except FileNotFoundError:
        pass
    return entries


def _summarize(entries: list, level_filter: set = None) -> dict:
    """
    Convert raw entries into a token-efficient summary:
    - counts by level
    - deduplicated error groups (message → count)
    - fix hints (deduplicated)
    """
    if level_filter:
        entries = [e for e in entries if e["level"] in level_filter]

    counts = Counter(e["level"] for e in entries)

    # Group errors by message prefix (first 80 chars) to deduplicate
    error_levels = {"ERROR", "CRITICAL", "EMERGENCY", "ALERT"}
    error_msgs = [e["msg"][:80] for e in entries if e["level"] in error_levels]
    error_groups = Counter(error_msgs).most_common(10)

    # Collect unique fix hints
    fix_hints = []
    seen_hints = set()
    for e in entries:
        if e["level"] in error_levels:
            hint = _get_fix_hint(e["msg"])
            if hint and hint not in seen_hints:
                fix_hints.append(hint)
                seen_hints.add(hint)

    # Recent errors (last 5, compact)
    recent_errors = [
        {"ts": e["ts"], "msg": e["msg"][:100]}
        for e in entries if e["level"] in error_levels
    ][-5:]

    return {
        "total":         len(entries),
        "counts":        dict(counts),
        "error_groups":  [{"message": msg, "count": cnt} for msg, cnt in error_groups],
        "recent_errors": recent_errors,
        "fix_hints":     fix_hints,
    }


@mcp.tool()
def read_logs(
    date_str: str = "today",
    level: str = "error",
    source: str = "both",
) -> str:
    """
    Read and analyze Laravel and Python backend logs. Returns compact summary.

    ⚠️ ALWAYS use this tool when admin asks about:
    - check logs / today's logs / any errors
    - what went wrong / debug issues / system errors
    - python backend errors / laravel errors

    Args:
        date_str: "today" | "yesterday" | "YYYY-MM-DD"
        level:    "error" (default) | "all" | "warning"
        source:   "both" | "laravel" | "python"

    Returns:
        Compact summary: error counts, deduplicated error groups, fix hints.
    """
    if not is_admin():
        return json.dumps({"message": "Permission denied."})

    if date_str == "today":
        target = str(date.today())
    elif date_str == "yesterday":
        target = str(date.today() - timedelta(days=1))
    else:
        target = date_str

    level_filter = None
    if level == "error":
        level_filter = {"ERROR", "CRITICAL", "EMERGENCY", "ALERT"}
    elif level == "warning":
        level_filter = {"WARNING", "ERROR", "CRITICAL", "EMERGENCY", "ALERT"}

    result = {"date": target, "sources": {}}

    if source in ("both", "laravel"):
        path    = os.path.join(_LARAVEL_LOG_DIR, f"laravel-{target}.log")
        entries = _parse_laravel_log(path)
        result["sources"]["laravel"] = _summarize(entries, level_filter)

    if source in ("both", "python"):
        entries = _parse_python_log(target)
        result["sources"]["python"] = _summarize(entries, level_filter)

    total_errors = sum(
        s.get("counts", {}).get("ERROR", 0) +
        s.get("counts", {}).get("CRITICAL", 0)
        for s in result["sources"].values()
    )
    all_hints = list({
        h for s in result["sources"].values() for h in s.get("fix_hints", [])
    })

    result["summary"] = {
        "status":       "Errors found" if total_errors > 0 else "No errors",
        "total_errors": total_errors,
        "fix_hints":    all_hints,
    }

    return json.dumps(result)


@mcp.tool()
def list_log_dates() -> str:
    """List all available Laravel log dates."""
    if not is_admin():
        return json.dumps({"message": "Permission denied."})
    try:
        files = sorted([
            f.replace("laravel-", "").replace(".log", "")
            for f in os.listdir(_LARAVEL_LOG_DIR)
            if re.match(r"laravel-\d{4}-\d{2}-\d{2}\.log", f)
        ], reverse=True)
        return json.dumps({"available_dates": files})
    except Exception as e:
        return json.dumps({"error": str(e)})
