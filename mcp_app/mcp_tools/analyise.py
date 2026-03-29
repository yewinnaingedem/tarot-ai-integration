"""
mcp_app/mcp_tools/analytics.py

Order analytics, sales reporting, follow-up tracking,
and AI-powered sales suggestions.

Tools:
  - get_order_summary            → daily/weekly/monthly stats
  - get_pending_followups        → pending orders needing attention
  - get_package_performance      → best/worst selling packages
  - get_revenue_trends           → revenue over time by period
  - get_ai_sales_suggestions     → AI analysis + actionable suggestions
  - get_category_analysis        → per-category breakdown
  - get_single_package_analysis  → deep-dive into one package
"""

from datetime import datetime, timedelta
from mcp_app.core import mcp
from mcp_app.db import get_connection
from mcp_app.permission import can
import json

_DENY = {"message": "You don't have permission to view orders."}


# ─────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────
from decimal import Decimal


def _clean_row(row: dict) -> dict:
    from datetime import date, datetime
    return {
        k: (int(v) if isinstance(v, Decimal) and v == int(v) else float(v))
           if isinstance(v, Decimal)
           else str(v) if isinstance(v, (date, datetime))
           else v
        for k, v in row.items()
    }


def _run_query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return [_clean_row(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def _fmt_mmk(amount) -> str:
    return f"{int(amount):,} MMK"


# ─────────────────────────────────────────────────────────────
# Tool 1: Order Summary
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_order_summary(period: str = "today") -> str:
    """
    Get order statistics summary for a time period.

    ⚠️ ALWAYS use this tool when admin asks about:
    - today's orders / sales
    - this week / this month performance
    - order counts or revenue totals

    Args:
        period: "today" | "yesterday" | "this_week" | "this_month" | "last_month"

    Returns:
        Summary with total orders, completed, pending, cancelled, and revenue.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)
    now = datetime.now()

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now
        label = "Today"
    elif period == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start.replace(hour=23, minute=59, second=59)
        label = "Yesterday"
    elif period == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now
        label = "This Week"
    elif period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end   = now
        label = "This Month"
    elif period == "last_month":
        first_this = now.replace(day=1)
        start = (first_this - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end   = first_this - timedelta(seconds=1)
        label = "Last Month"
    else:
        return json.dumps({"error": f"Unknown period '{period}'. Use: today, yesterday, this_week, this_month, last_month"})

    rows = _run_query("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'complete'  THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'pending'   THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
            COALESCE(SUM(CASE WHEN status = 'complete' THEN total_amount ELSE 0 END), 0) AS revenue,
            COALESCE(SUM(total_amount), 0) AS potential_revenue
        FROM orders
        WHERE deleted_at IS NULL
          AND created_at BETWEEN %s AND %s
    """, (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))

    r = rows[0]
    total     = r["total"] or 0
    completed = r["completed"] or 0
    pending   = r["pending"] or 0
    cancelled = r["cancelled"] or 0
    revenue   = r["revenue"] or 0
    potential = r["potential_revenue"] or 0
    conv_rate = round((completed / total * 100), 1) if total > 0 else 0

    return json.dumps({
        "period":            label,
        "date_range":        f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')}",
        "total_orders":      total,
        "completed":         completed,
        "pending":           pending,
        "cancelled":         cancelled,
        "conversion_rate":   f"{conv_rate}%",
        "revenue":           _fmt_mmk(revenue),
        "revenue_raw":       int(revenue),
        "potential_revenue": _fmt_mmk(potential),
        "lost_from_pending": _fmt_mmk(potential - revenue),
    })


# ─────────────────────────────────────────────────────────────
# Tool 2: Pending Follow-ups
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_pending_followups(older_than_hours: int = 24) -> str:
    """
    Get pending orders that need admin follow-up.

    ⚠️ ALWAYS use this tool when admin asks about:
    - pending orders
    - orders waiting / not completed
    - follow-up needed
    - customers waiting

    Args:
        older_than_hours: Show pending orders older than this many hours (default 24).

    Returns:
        List of pending orders with customer info, amount, and how long they've been waiting.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)
    cutoff = datetime.now() - timedelta(hours=older_than_hours)

    rows = _run_query("""
        SELECT
            o.id,
            o.order_ref,
            o.customer_name,
            o.customer_phone,
            o.total_amount,
            o.remark,
            o.created_at,
            p.name AS package_name,
            c.name AS category_name,
            TIMESTAMPDIFF(HOUR, o.created_at, NOW()) AS hours_waiting
        FROM orders o
        LEFT JOIN packages  p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE o.status = 'pending'
          AND o.deleted_at IS NULL
          AND o.created_at <= %s
        ORDER BY o.created_at ASC
        LIMIT 50
    """, (cutoff.strftime("%Y-%m-%d %H:%M:%S"),))

    if not rows:
        return json.dumps({
            "message":      f"No pending orders older than {older_than_hours} hours. Great job! ✅",
            "total_pending": 0,
        })

    total_amount = sum(r["total_amount"] for r in rows)
    items = []
    for r in rows:
        items.append({
            "order_ref":     r["order_ref"],
            "customer":      r["customer_name"],
            "phone":         r["customer_phone"],
            "package":       r["package_name"] or "Unknown",
            "category":      r["category_name"] or "Unknown",
            "amount":        _fmt_mmk(r["total_amount"]),
            "remark":        r["remark"],
            "created_at":    str(r["created_at"]),
            "hours_waiting": r["hours_waiting"],
            "urgency":       "🔴 URGENT" if r["hours_waiting"] > 48 else ("🟡 Follow up" if r["hours_waiting"] > 24 else "🟢 Recent"),
        })

    return json.dumps({
        "total_pending":        len(rows),
        "total_pending_amount": _fmt_mmk(total_amount),
        "threshold_hours":      older_than_hours,
        "urgent_count":         sum(1 for i in items if "URGENT" in i["urgency"]),
        "orders":               items,
        "suggestion":           "Contact URGENT orders first. Consider running a limited discount to convert pending to complete.",
    })


# ─────────────────────────────────────────────────────────────
# Tool 3: Package Performance
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_package_performance(period: str = "this_month") -> str:
    """
    Get best and worst performing packages by sales volume and revenue.

    ⚠️ ALWAYS use this tool when admin asks about:
    - which packages sell most / least
    - package performance
    - underperforming packages
    - what to put on discount

    Args:
        period: "this_week" | "this_month" | "last_month" | "all_time"

    Returns:
        Ranked list of packages with order count, revenue, and conversion rate.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)
    now = datetime.now()
    if period == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        label = "This Week"
    elif period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "This Month"
    elif period == "last_month":
        first = now.replace(day=1)
        start = (first - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "Last Month"
    else:
        start = datetime(2020, 1, 1)
        label = "All Time"

    rows = _run_query("""
        SELECT
            p.id          AS package_id,
            p.name        AS package_name,
            p.amount      AS package_price,
            c.name        AS category_name,
            COUNT(o.id)   AS total_orders,
            SUM(CASE WHEN o.status = 'complete'  THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN o.status = 'pending'   THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount ELSE 0 END), 0) AS revenue
        FROM orders o
        JOIN packages   p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL
          AND o.created_at >= %s
        GROUP BY p.id, p.name, p.amount, c.name
        ORDER BY completed DESC, revenue DESC
    """, (start.strftime("%Y-%m-%d %H:%M:%S"),))

    if not rows:
        return json.dumps({"message": "No order data found for this period."})

    result = []
    for i, r in enumerate(rows):
        total     = r["total_orders"] or 0
        completed = r["completed"] or 0
        conv_rate = round(completed / total * 100, 1) if total > 0 else 0
        result.append({
            "rank":          i + 1,
            "package":       r["package_name"],
            "category":      r["category_name"],
            "price":         _fmt_mmk(r["package_price"] or 0),
            "total_orders":  total,
            "completed":     completed,
            "pending":       r["pending"],
            "cancelled":     r["cancelled"],
            "conversion":    f"{conv_rate}%",
            "revenue":       _fmt_mmk(r["revenue"]),
            "status":        "🔥 Top Seller" if i < 3 else ("⚠️ Underperforming" if conv_rate < 40 else "✅ Normal"),
        })

    return json.dumps({
        "period":   label,
        "packages": result,
        "insight":  f"Top package: {result[0]['package']} with {result[0]['completed']} completions. "
                    f"Lowest: {result[-1]['package']} with {result[-1]['completed']} completions.",
    })


# ─────────────────────────────────────────────────────────────
# Tool 4: Revenue Trends
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_revenue_trends(granularity: str = "daily", days: int = 30) -> str:
    """
    Get revenue trends over time broken down by day or week.

    ⚠️ ALWAYS use this tool when admin asks about:
    - revenue trends
    - sales over time
    - best days / weeks
    - revenue growth or decline

    Args:
        granularity: "daily" | "weekly"
        days:        How many past days to include (default 30)

    Returns:
        Time-series revenue data with totals per period.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)
    start = datetime.now() - timedelta(days=days)

    if granularity == "weekly":
        rows = _run_query("""
            SELECT
                YEARWEEK(created_at, 1)  AS period_key,
                MIN(DATE(created_at))    AS period_start,
                COUNT(*)                 AS total_orders,
                SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS completed,
                COALESCE(SUM(CASE WHEN status = 'complete' THEN total_amount ELSE 0 END), 0) AS revenue
            FROM orders
            WHERE deleted_at IS NULL AND created_at >= %s
            GROUP BY YEARWEEK(created_at, 1)
            ORDER BY period_key ASC
        """, (start.strftime("%Y-%m-%d"),))
        label = f"Weekly (last {days} days)"
    else:
        rows = _run_query("""
            SELECT
                DATE(created_at)         AS period_key,
                DATE(created_at)         AS period_start,
                COUNT(*)                 AS total_orders,
                SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS completed,
                COALESCE(SUM(CASE WHEN status = 'complete' THEN total_amount ELSE 0 END), 0) AS revenue
            FROM orders
            WHERE deleted_at IS NULL AND created_at >= %s
            GROUP BY DATE(created_at)
            ORDER BY period_key ASC
        """, (start.strftime("%Y-%m-%d"),))
        label = f"Daily (last {days} days)"

    if not rows:
        return json.dumps({"message": "No revenue data found."})

    periods    = []
    revenues   = []
    total_rev  = 0
    peak_rev   = 0
    peak_date  = ""

    for r in rows:
        rev = int(r["revenue"] or 0)
        revenues.append(rev)
        total_rev += rev
        if rev > peak_rev:
            peak_rev  = rev
            peak_date = str(r["period_start"])
        periods.append({
            "period":       str(r["period_start"]),
            "total_orders": r["total_orders"],
            "completed":    r["completed"],
            "revenue":      _fmt_mmk(rev),
            "revenue_raw":  rev,
        })

    avg_rev = int(total_rev / len(revenues)) if revenues else 0

    # Simple trend: compare first half vs second half
    half     = len(revenues) // 2
    first_h  = sum(revenues[:half]) if half else 0
    second_h = sum(revenues[half:]) if half else 0
    trend    = "📈 Growing" if second_h > first_h else ("📉 Declining" if second_h < first_h else "➡️ Stable")

    return json.dumps({
        "granularity":   label,
        "total_revenue": _fmt_mmk(total_rev),
        "avg_per_period": _fmt_mmk(avg_rev),
        "peak_revenue":  _fmt_mmk(peak_rev),
        "peak_date":     peak_date,
        "trend":         trend,
        "periods":       periods,
    })


# ─────────────────────────────────────────────────────────────
# Tool 5: AI Sales Suggestions
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_ai_sales_suggestions() -> str:
    """
    Analyze recent sales data and generate AI-powered suggestions to improve revenue.

    ⚠️ ALWAYS use this tool when admin asks about:
    - how to improve sales
    - what discount to run
    - AI suggestions
    - sales advice
    - what to do to increase revenue
    - follow-up strategy

    Returns:
        Full analysis with specific actionable suggestions.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)
    now   = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start  = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    last30      = now - timedelta(days=30)

    # 1. This month summary
    month = _run_query("""
        SELECT
            COUNT(*) total,
            SUM(status='complete')  completed,
            SUM(status='pending')   pending,
            SUM(status='cancelled') cancelled,
            COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) revenue
        FROM orders WHERE deleted_at IS NULL AND created_at >= %s
    """, (month_start,))[0]

    # 2. Best selling packages (last 30 days)
    top_packages = _run_query("""
        SELECT p.name, c.name cat, COUNT(*) cnt,
               COALESCE(SUM(CASE WHEN o.status='complete' THEN o.total_amount END), 0) rev,
               ROUND(SUM(o.status='complete') / COUNT(*) * 100, 1) conv
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY p.id, p.name, c.name
        ORDER BY cnt DESC LIMIT 5
    """, (last30,))

    # 3. Underperforming packages (low conversion < 50%)
    weak_packages = _run_query("""
        SELECT p.name, c.name cat, COUNT(*) cnt,
               ROUND(SUM(o.status='complete') / COUNT(*) * 100, 1) conv,
               p.amount
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY p.id, p.name, c.name, p.amount
        HAVING cnt >= 3 AND conv < 50
        ORDER BY conv ASC LIMIT 5
    """, (last30,))

    # 4. Pending orders value at risk
    pending = _run_query("""
        SELECT COUNT(*) cnt,
               COALESCE(SUM(total_amount), 0) total_value,
               MAX(TIMESTAMPDIFF(HOUR, created_at, NOW())) max_wait_hours
        FROM orders
        WHERE status='pending' AND deleted_at IS NULL
    """)[0]

    # 5. Best performing day of week
    best_days = _run_query("""
        SELECT DAYNAME(created_at) day_name,
               COUNT(*) total,
               COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) revenue
        FROM orders
        WHERE deleted_at IS NULL AND created_at >= %s
        GROUP BY DAYNAME(created_at), DAYOFWEEK(created_at)
        ORDER BY revenue DESC LIMIT 3
    """, (last30,))

    # 6. Peak hours
    peak_hours = _run_query("""
        SELECT HOUR(created_at) hour,
               COUNT(*) total,
               COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) revenue
        FROM orders
        WHERE deleted_at IS NULL AND created_at >= %s
        GROUP BY HOUR(created_at)
        ORDER BY revenue DESC LIMIT 3
    """, (last30,))

    # ── Build suggestions ────────────────────────────────────
    suggestions = []
    conv_rate = round(int(month["completed"] or 0) / int(month["total"] or 1) * 100, 1)

    # Suggestion: pending follow-up
    pending_cnt = int(pending["cnt"] or 0)
    pending_val = int(pending["total_value"] or 0)
    if pending_cnt > 0:
        suggestions.append({
            "priority": "🔴 HIGH",
            "title":    "Follow Up Pending Orders",
            "detail":   f"You have {pending_cnt} pending orders worth {_fmt_mmk(pending_val)}. "
                        f"Oldest has been waiting {pending['max_wait_hours']} hours. "
                        f"Reach out via phone/Viber to convert them.",
            "action":   "Use get_pending_followups tool to see the full list and contact customers.",
        })

    # Suggestion: discount on weak packages
    if weak_packages:
        pkg_names = ", ".join(p["name"] for p in weak_packages[:3])
        suggestions.append({
            "priority": "🟡 MEDIUM",
            "title":    "Run Discount on Underperforming Packages",
            "detail":   f"Packages with low conversion (<50%): {pkg_names}. "
                        f"A 15-20% discount could convert fence-sitters.",
            "action":   f"Create a discount for these packages using create_discount tool.",
        })

    # Suggestion: promote top sellers
    if top_packages:
        top = top_packages[0]
        suggestions.append({
            "priority": "🟢 OPPORTUNITY",
            "title":    "Amplify Top Seller",
            "detail":   f"'{top['name']}' ({top['cat']}) is your best seller with {top['cnt']} orders "
                        f"and {top['conv']}% conversion. Push more traffic to it.",
            "action":   "Highlight this package in promotions. Keep it well-stocked with readers.",
        })

    # Suggestion: best days to run promotions
    if best_days:
        day_list = ", ".join(d["day_name"] for d in best_days)
        suggestions.append({
            "priority": "🟢 OPPORTUNITY",
            "title":    f"Run Promotions on Peak Days",
            "detail":   f"Your highest revenue days are: {day_list}. "
                        f"Schedule flash discounts or social media posts on these days.",
            "action":   "Plan your discount start dates to land on these high-traffic days.",
        })

    # Suggestion: peak hours
    if peak_hours:
        hours = ", ".join(f"{h['hour']}:00" for h in peak_hours)
        suggestions.append({
            "priority": "🟢 OPPORTUNITY",
            "title":    "Optimize for Peak Hours",
            "detail":   f"Most orders come in around {hours}. "
                        f"Ensure readers are available and response time is fast during these hours.",
            "action":   "Staff scheduling and quick response = higher conversion.",
        })

    # Suggestion: conversion rate warning
    if conv_rate < 60:
        suggestions.append({
            "priority": "🟡 MEDIUM",
            "title":    "Improve Overall Conversion Rate",
            "detail":   f"Current conversion rate is {conv_rate}%. Target is >70%. "
                        f"Many pending orders may be due to slow response or unclear expectations.",
            "action":   "Review pending orders > 6 hours old and contact them proactively.",
        })

    return json.dumps({
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "month_snapshot": {
            "total_orders":   int(month["total"] or 0),
            "completed":      int(month["completed"] or 0),
            "pending":        int(month["pending"] or 0),
            "revenue":        _fmt_mmk(month["revenue"] or 0),
            "conversion_rate": f"{conv_rate}%",
        },
        "top_packages":  [{"name": p["name"], "category": p["cat"], "orders": p["cnt"], "revenue": _fmt_mmk(p["rev"])} for p in top_packages],
        "weak_packages": [{"name": p["name"], "category": p["cat"], "conversion": f"{p['conv']}%", "price": _fmt_mmk(p["price"] or 0)} for p in weak_packages],
        "best_days":     [{"day": d["day_name"], "revenue": _fmt_mmk(d["revenue"])} for d in best_days],
        "peak_hours":    [{"hour": f"{h['hour']}:00", "revenue": _fmt_mmk(h["revenue"])} for h in peak_hours],
        "suggestions":   suggestions,
        "total_suggestions": len(suggestions),
    })


# ─────────────────────────────────────────────────────────────
# Tool 6: Category-by-Category Analysis
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_category_analysis(period: str = "this_month") -> str:
    """
    Analyze sales performance broken down by each category.

    ⚠️ ALWAYS use this tool when admin asks about:
    - category performance / comparison
    - which category sells best / worst
    - category-level revenue or orders
    - breakdown by category

    Args:
        period: "this_week" | "this_month" | "last_month" | "all_time"

    Returns:
        Per-category stats: orders, revenue, conversion, top package per category.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    now = datetime.now()
    if period == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        label = "This Week"
    elif period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "This Month"
    elif period == "last_month":
        first = now.replace(day=1)
        start = (first - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "Last Month"
    else:
        start = datetime(2020, 1, 1)
        label = "All Time"

    rows = _run_query("""
        SELECT
            c.id                    AS category_id,
            c.name                  AS category_name,
            COUNT(o.id)             AS total_orders,
            SUM(o.status = 'complete')  AS completed,
            SUM(o.status = 'pending')   AS pending,
            SUM(o.status = 'cancelled') AS cancelled,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount END), 0) AS revenue
        FROM orders o
        JOIN packages  p ON o.package_id  = p.id
        JOIN category  c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY c.id, c.name
        ORDER BY revenue DESC
    """, (start.strftime("%Y-%m-%d %H:%M:%S"),))

    if not rows:
        return json.dumps({"message": "No order data found for this period."})

    # top package per category
    top_pkgs = _run_query("""
        SELECT
            c.id AS category_id,
            p.name AS package_name,
            COUNT(o.id) AS cnt
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY c.id, p.id, p.name
        ORDER BY c.id, cnt DESC
    """, (start.strftime("%Y-%m-%d %H:%M:%S"),))

    top_map = {}
    for tp in top_pkgs:
        cid = tp["category_id"]
        if cid not in top_map:
            top_map[cid] = tp["package_name"]

    total_rev = sum(int(r["revenue"] or 0) for r in rows)
    categories = []
    for i, r in enumerate(rows):
        total = int(r["total_orders"] or 0)
        completed = int(r["completed"] or 0)
        rev = int(r["revenue"] or 0)
        conv = round(completed / total * 100, 1) if total else 0
        share = round(rev / total_rev * 100, 1) if total_rev else 0
        categories.append({
            "rank":         i + 1,
            "category":     r["category_name"],
            "total_orders": total,
            "completed":    completed,
            "pending":      int(r["pending"] or 0),
            "cancelled":    int(r["cancelled"] or 0),
            "conversion":   f"{conv}%",
            "revenue":      _fmt_mmk(rev),
            "revenue_share": f"{share}%",
            "top_package":  top_map.get(r["category_id"], "N/A"),
        })

    return json.dumps({
        "period":        label,
        "total_revenue": _fmt_mmk(total_rev),
        "categories":    categories,
    })


# ─────────────────────────────────────────────────────────────
# Tool 7: Single Package Deep-Dive
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_single_package_analysis(package_name: str, days: int = 30) -> str:
    """
    Deep-dive analysis for a single package by name.

    ⚠️ ALWAYS use this tool when admin asks about:
    - how a specific package is doing
    - stats for a particular package
    - single package performance / trend

    Args:
        package_name: Full or partial name of the package to analyze.
        days:         How many past days to include (default 30).

    Returns:
        Detailed stats: orders, revenue, conversion, daily trend, and customer list.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    start = datetime.now() - timedelta(days=days)

    # find matching package
    pkgs = _run_query(
        "SELECT id, name, price FROM packages WHERE name LIKE %s LIMIT 5",
        (f"%{package_name}%",),
    )
    if not pkgs:
        return json.dumps({"error": f"No package matching '{package_name}'."})

    pkg = pkgs[0]
    pid = pkg["id"]

    # summary
    summary = _run_query("""
        SELECT
            COUNT(*)                    AS total_orders,
            SUM(status = 'complete')    AS completed,
            SUM(status = 'pending')     AS pending,
            SUM(status = 'cancelled')   AS cancelled,
            COALESCE(SUM(CASE WHEN status = 'complete' THEN total_amount END), 0) AS revenue
        FROM orders
        WHERE package_id = %s AND deleted_at IS NULL AND created_at >= %s
    """, (pid, start.strftime("%Y-%m-%d %H:%M:%S")))[0]

    total = int(summary["total_orders"] or 0)
    completed = int(summary["completed"] or 0)
    conv = round(completed / total * 100, 1) if total else 0

    # daily trend
    daily = _run_query("""
        SELECT DATE(created_at) AS day, COUNT(*) AS orders,
               COALESCE(SUM(CASE WHEN status = 'complete' THEN total_amount END), 0) AS revenue
        FROM orders
        WHERE package_id = %s AND deleted_at IS NULL AND created_at >= %s
        GROUP BY DATE(created_at) ORDER BY day ASC
    """, (pid, start.strftime("%Y-%m-%d %H:%M:%S")))

    # recent customers
    customers = _run_query("""
        SELECT customer_name, customer_phone, status, total_amount, created_at
        FROM orders
        WHERE package_id = %s AND deleted_at IS NULL AND created_at >= %s
        ORDER BY created_at DESC LIMIT 10
    """, (pid, start.strftime("%Y-%m-%d %H:%M:%S")))

    return json.dumps({
        "package":    pkg["name"],
        "price":      _fmt_mmk(pkg["price"] or 0),
        "period":     f"Last {days} days",
        "summary": {
            "total_orders": total,
            "completed":    completed,
            "pending":      int(summary["pending"] or 0),
            "cancelled":    int(summary["cancelled"] or 0),
            "conversion":   f"{conv}%",
            "revenue":      _fmt_mmk(summary["revenue"] or 0),
        },
        "daily_trend": [{"day": str(d["day"]), "orders": d["orders"], "revenue": _fmt_mmk(d["revenue"])} for d in daily],
        "recent_customers": [{"name": c["customer_name"], "phone": c["customer_phone"], "status": c["status"], "amount": _fmt_mmk(c["total_amount"]), "date": str(c["created_at"])} for c in customers],
        "other_matches": [p["name"] for p in pkgs[1:]] if len(pkgs) > 1 else [],
    })
