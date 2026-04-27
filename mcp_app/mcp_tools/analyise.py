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


def _resolve_period(period: str) -> tuple:
    """Return (start, end, label) for a named period. end is exclusive."""
    now = datetime.now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        label = "Today"
    elif period == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "Yesterday"
    elif period == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        label = "This Week"
    elif period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        label = "This Month"
    elif period == "last_month":
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (first_this - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_this
        label = "Last Month"
    else:
        # Try YYYY-MM format (e.g. "2025-04" for April 2025)
        try:
            parsed = datetime.strptime(period, "%Y-%m")
            start = parsed.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if parsed.month == 12:
                end = parsed.replace(year=parsed.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                end = parsed.replace(month=parsed.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            label = parsed.strftime("%B %Y")
            return start, end, label
        except ValueError:
            pass
        start = datetime(2020, 1, 1)
        end = now
        label = "All Time"
    return start, end, label


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
        end   = now.replace(hour=0, minute=0, second=0, microsecond=0)
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
        "pending_all":       pending,
        "cancelled":         cancelled,
        "conversion_rate":   f"{conv_rate}%",
        "revenue":           _fmt_mmk(revenue),
        "revenue_raw":       int(revenue),
        "potential_revenue": _fmt_mmk(potential),
        "lost_from_pending": _fmt_mmk(potential - revenue),
        "note":              "pending_all includes both paid-unreplied and unpaid orders. Use get_unreplied_paid_orders for paid-but-unreplied count.",
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
            "message":      f"No pending orders older than {older_than_hours} hours.",
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
            "urgency":       "URGENT" if r["hours_waiting"] > 48 else ("Follow up" if r["hours_waiting"] > 24 else "Recent"),
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
def get_package_performance(period: str = "this_month", category_id: int = None, compare_period: str = None) -> str:
    """
    Get best and worst performing packages by sales volume and revenue.

    ⚠️ ALWAYS use this tool when admin asks about:
    - which packages sell most / least
    - package performance
    - underperforming packages
    - what to put on discount
    - specific category's package sales
    - compare package sales between months

    Args:
        period: "this_week" | "this_month" | "last_month" | "all_time"
        category_id: Optional category ID to filter by. Get IDs from get_categories.
        compare_period: Optional second period to compare against (e.g. "last_month"). When set, returns both periods side by side with change %.

    Returns:
        Ranked list of packages with order count, revenue, and conversion rate.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)
    start, end, label = _resolve_period(period)

    params = [start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")]
    cat_filter = ""
    if category_id:
        cat_filter = "AND p.category_id = %s"
        params.append(category_id)

    rows = _run_query(f"""
        SELECT
            p.id          AS package_id,
            p.name        AS package_name,
            p.amount      AS package_price,
            c.name        AS category_name,
            COUNT(o.id)   AS total_orders,
            SUM(CASE WHEN o.payment_complete = 1 THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN o.payment_complete = 0 THEN 1 ELSE 0 END) AS unpaid_orders,
            SUM(CASE WHEN o.status = 'complete'  THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN o.status = 'pending'   THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount ELSE 0 END), 0) AS revenue
        FROM orders o
        JOIN packages   p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL
          AND o.created_at >= %s AND o.created_at < %s
          {cat_filter}
        GROUP BY p.id, p.name, p.amount, c.name
        ORDER BY completed DESC, revenue DESC
    """, tuple(params))

    if not rows:
        return json.dumps({"message": "No order data found for this period."})

    def _build_packages(rows):
        result = []
        for i, r in enumerate(rows):
            total     = r["total_orders"] or 0
            completed = r["completed"] or 0
            conv_rate = round(completed / total * 100, 1) if total > 0 else 0
            result.append({
                "rank":          i + 1,
                "package":       r["package_name"],
                "package_id":    r["package_id"],
                "category":      r["category_name"],
                "price":         _fmt_mmk(r["package_price"] or 0),
                "total_orders":  total,
                "paid_orders":   int(r["paid_orders"] or 0),
                "unpaid_orders": int(r["unpaid_orders"] or 0),
                "completed":     completed,
                "cancelled":     r["cancelled"],
                "conversion":    f"{conv_rate}%",
                "revenue":       _fmt_mmk(r["revenue"]),
                "revenue_raw":   int(r["revenue"]),
            })
        return result

    current = _build_packages(rows)

    if not compare_period:
        for p in current:
            p.pop("revenue_raw", None)
            p.pop("package_id", None)
        return json.dumps({
            "period":   label,
            "packages": current,
            "insight":  f"Top package: {current[0]['package']} with {current[0]['completed']} completions. "
                        f"Lowest: {current[-1]['package']} with {current[-1]['completed']} completions.",
        })

    # Comparison mode
    cmp_start, cmp_end, cmp_label = _resolve_period(compare_period)
    cmp_params = [cmp_start.strftime("%Y-%m-%d %H:%M:%S"), cmp_end.strftime("%Y-%m-%d %H:%M:%S")]
    if category_id:
        cmp_params.append(category_id)

    cmp_rows = _run_query(f"""
        SELECT
            p.id AS package_id, p.name AS package_name, p.amount AS package_price,
            c.name AS category_name, COUNT(o.id) AS total_orders,
            SUM(CASE WHEN o.payment_complete = 1 THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN o.payment_complete = 0 THEN 1 ELSE 0 END) AS unpaid_orders,
            SUM(CASE WHEN o.status = 'complete' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN o.status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount ELSE 0 END), 0) AS revenue
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL
          AND o.created_at >= %s AND o.created_at < %s
          {cat_filter}
        GROUP BY p.id, p.name, p.amount, c.name
        ORDER BY completed DESC, revenue DESC
    """, tuple(cmp_params))

    cmp_map = {}
    for r in _build_packages(cmp_rows):
        cmp_map[r["package_id"]] = r

    comparison = []
    for p in current:
        prev = cmp_map.get(p["package_id"], {})
        prev_orders = prev.get("total_orders", 0)
        prev_rev = prev.get("revenue_raw", 0)
        order_change = p["total_orders"] - prev_orders
        rev_change = p["revenue_raw"] - prev_rev
        comparison.append({
            "package":       p["package"],
            "category":      p["category"],
            "current_orders": p["total_orders"],
            "previous_orders": prev_orders,
            "order_change":  f"{order_change:+d} ({round(order_change/prev_orders*100, 1) if prev_orders else 0:+.1f}%)",
            "current_revenue": _fmt_mmk(p["revenue_raw"]),
            "previous_revenue": _fmt_mmk(prev_rev),
            "revenue_change": f"{_fmt_mmk(rev_change)} ({round(rev_change/prev_rev*100, 1) if prev_rev else 0:+.1f}%)",
            "current_conversion": p["conversion"],
            "previous_conversion": prev.get("conversion", "0%"),
        })

    return json.dumps({
        "current_period":  label,
        "compare_period":  cmp_label,
        "packages":        comparison,
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
    trend    = "Growing" if second_h > first_h else ("Declining" if second_h < first_h else "Stable")

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

    # 4. Unreplied PAID orders (the ones actually needing reply)
    pending = _run_query("""
        SELECT COUNT(*) cnt,
               COALESCE(SUM(o.total_amount), 0) total_value,
               MAX(TIMESTAMPDIFF(HOUR, o.created_at, NOW())) max_wait_hours
        FROM orders o
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.status = 'pending'
          AND o.payment_complete = 1
          AND o.deleted_at IS NULL
          AND r.id IS NULL
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
            "priority": "HIGH",
            "title":    "Reply Unreplied Paid Orders",
            "detail":   f"You have {pending_cnt} paid orders waiting for a reply, worth {_fmt_mmk(pending_val)}. "
                        f"Oldest has been waiting {pending['max_wait_hours']} hours. "
                        f"These customers already paid — reply immediately.",
            "action":   "Use get_unreplied_paid_orders tool to see the full list.",
        })

    # Suggestion: discount on weak packages
    if weak_packages:
        pkg_names = ", ".join(p["name"] for p in weak_packages[:3])
        suggestions.append({
            "priority": "MEDIUM",
            "title":    "Run Discount on Underperforming Packages",
            "detail":   f"Packages with low conversion (<50%): {pkg_names}. "
                        f"A 15-20% discount could convert fence-sitters.",
            "action":   f"Create a discount for these packages using create_discount tool.",
        })

    # Suggestion: promote top sellers
    if top_packages:
        top = top_packages[0]
        suggestions.append({
            "priority": "OPPORTUNITY",
            "title":    "Amplify Top Seller",
            "detail":   f"'{top['name']}' ({top['cat']}) is your best seller with {top['cnt']} orders "
                        f"and {top['conv']}% conversion. Push more traffic to it.",
            "action":   "Highlight this package in promotions. Keep it well-stocked with readers.",
        })

    # Suggestion: best days to run promotions
    if best_days:
        day_list = ", ".join(d["day_name"] for d in best_days)
        suggestions.append({
            "priority": "OPPORTUNITY",
            "title":    f"Run Promotions on Peak Days",
            "detail":   f"Your highest revenue days are: {day_list}. "
                        f"Schedule flash discounts or social media posts on these days.",
            "action":   "Plan your discount start dates to land on these high-traffic days.",
        })

    # Suggestion: peak hours
    if peak_hours:
        hours = ", ".join(f"{h['hour']}:00" for h in peak_hours)
        suggestions.append({
            "priority": "OPPORTUNITY",
            "title":    "Optimize for Peak Hours",
            "detail":   f"Most orders come in around {hours}. "
                        f"Ensure readers are available and response time is fast during these hours.",
            "action":   "Staff scheduling and quick response = higher conversion.",
        })

    # Suggestion: conversion rate warning
    if conv_rate < 60:
        suggestions.append({
            "priority": "MEDIUM",
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
def get_category_analysis(period: str = "this_month", compare_period: str = None) -> str:
    """
    Analyze sales performance broken down by each category.

    ⚠️ ALWAYS use this tool when admin asks about:
    - category performance / comparison
    - which category sells best / worst
    - category-level revenue or orders
    - breakdown by category
    - compare categories between months

    Args:
        period: "this_week" | "this_month" | "last_month" | "all_time" | "YYYY-MM" (e.g. "2025-04" for April 2025)
        compare_period: Optional second period in the same format (e.g. "last_month" or "2025-04").

    Returns:
        Per-category stats: orders, revenue, conversion, top package per category.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    start, end, label = _resolve_period(period)

    rows = _run_query("""
        SELECT
            c.id                    AS category_id,
            c.name                  AS category_name,
            COUNT(o.id)             AS total_orders,
            SUM(CASE WHEN o.payment_complete = 1 THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN o.payment_complete = 0 THEN 1 ELSE 0 END) AS unpaid_orders,
            SUM(o.status = 'complete')  AS completed,
            SUM(o.status = 'pending')   AS pending,
            SUM(o.status = 'cancelled') AS cancelled,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount END), 0) AS revenue
        FROM orders o
        JOIN packages  p ON o.package_id  = p.id
        JOIN category  c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s AND o.created_at < %s
        GROUP BY c.id, c.name
        ORDER BY revenue DESC
    """, (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))

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
        WHERE o.deleted_at IS NULL AND o.created_at >= %s AND o.created_at < %s
        GROUP BY c.id, p.id, p.name
        ORDER BY c.id, cnt DESC
    """, (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))

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
            "category_id":  r["category_id"],
            "category":     r["category_name"],
            "total_orders": total,
            "paid_orders":  int(r["paid_orders"] or 0),
            "unpaid_orders": int(r["unpaid_orders"] or 0),
            "completed":    completed,
            "cancelled":    int(r["cancelled"] or 0),
            "conversion":   f"{conv}%",
            "revenue":      _fmt_mmk(rev),
            "revenue_raw":  rev,
            "revenue_share": f"{share}%",
            "top_package":  top_map.get(r["category_id"], "N/A"),
        })

    if not compare_period:
        for c in categories:
            c.pop("revenue_raw", None)
            c.pop("category_id", None)
        return json.dumps({
            "period":        label,
            "total_revenue": _fmt_mmk(total_rev),
            "categories":    categories,
        })

    # Comparison mode
    cmp_start, cmp_end, cmp_label = _resolve_period(compare_period)
    cmp_rows = _run_query("""
        SELECT
            c.id AS category_id, c.name AS category_name,
            COUNT(o.id) AS total_orders,
            SUM(CASE WHEN o.payment_complete = 1 THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN o.payment_complete = 0 THEN 1 ELSE 0 END) AS unpaid_orders,
            SUM(o.status = 'complete') AS completed,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount END), 0) AS revenue
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s AND o.created_at < %s
        GROUP BY c.id, c.name
    """, (cmp_start.strftime("%Y-%m-%d %H:%M:%S"), cmp_end.strftime("%Y-%m-%d %H:%M:%S")))

    cmp_map = {}
    for r in cmp_rows:
        cmp_map[r["category_id"]] = {
            "total_orders": int(r["total_orders"] or 0),
            "completed": int(r["completed"] or 0),
            "revenue": int(r["revenue"] or 0),
        }

    comparison = []
    for c in categories:
        prev = cmp_map.get(c["category_id"], {"total_orders": 0, "completed": 0, "revenue": 0})
        order_diff = c["total_orders"] - prev["total_orders"]
        rev_diff = c["revenue_raw"] - prev["revenue"]
        comparison.append({
            "category":          c["category"],
            "current_orders":    c["total_orders"],
            "previous_orders":   prev["total_orders"],
            "order_change":      f"{order_diff:+d} ({round(order_diff/prev['total_orders']*100, 1) if prev['total_orders'] else 0:+.1f}%)",
            "current_revenue":   _fmt_mmk(c["revenue_raw"]),
            "previous_revenue":  _fmt_mmk(prev["revenue"]),
            "revenue_change":    f"{_fmt_mmk(rev_diff)} ({round(rev_diff/prev['revenue']*100, 1) if prev['revenue'] else 0:+.1f}%)",
            "current_conversion": c["conversion"],
        })

    return json.dumps({
        "current_period": label,
        "compare_period": cmp_label,
        "categories":     comparison,
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
        "SELECT id, name, amount AS price FROM packages WHERE name LIKE %s LIMIT 5",
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
            "cancelled":    int(summary["cancelled"] or 0),
            "conversion":   f"{conv}%",
            "revenue":      _fmt_mmk(summary["revenue"] or 0),
        },
        "daily_trend": [{"day": str(d["day"]), "orders": d["orders"], "revenue": _fmt_mmk(d["revenue"])} for d in daily],
        "recent_customers": [{"name": c["customer_name"], "phone": c["customer_phone"], "status": c["status"], "amount": _fmt_mmk(c["total_amount"]), "date": str(c["created_at"])} for c in customers],
        "other_matches": [p["name"] for p in pkgs[1:]] if len(pkgs) > 1 else [],
    })


# ─────────────────────────────────────────────────────────────
# Tool 8: Reply Performance
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_reply_performance(period: str = "this_month") -> str:
    """
    Analyze reply speed and response time by category.

    ⚠️ ALWAYS use this tool when admin asks about:
    - how fast orders are being replied
    - reply time / response time
    - which category is slowest to reply
    - average reply hours

    Args:
        period: "this_month" | "last_month" | "all_time"

    Returns:
        Average reply time per category, slowest/fastest, and orders still unreplied.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    start, end, label = _resolve_period(period)

    rows = _run_query("""
        SELECT
            c.name                                                          AS category,
            COUNT(r.id)                                                     AS replied_count,
            ROUND(AVG(TIMESTAMPDIFF(HOUR, o.created_at, r.created_at)), 1) AS avg_hours,
            MIN(TIMESTAMPDIFF(HOUR, o.created_at, r.created_at))           AS min_hours,
            MAX(TIMESTAMPDIFF(HOUR, o.created_at, r.created_at))           AS max_hours
        FROM reply r
        JOIN orders  o ON o.id  = r.order_id
        JOIN packages p ON p.id = o.package_id
        JOIN category c ON c.id = p.category_id
        WHERE o.deleted_at IS NULL
          AND r.created_at >= %s AND r.created_at < %s
        GROUP BY c.id, c.name
        ORDER BY avg_hours ASC
    """, (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))

    # Unreplied paid orders count
    unreplied = _run_query("""
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(o.total_amount), 0) AS value
        FROM orders o
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.deleted_at IS NULL
          AND o.payment_complete = 1
          AND o.status = 'pending'
          AND r.id IS NULL
          AND o.created_at >= %s AND o.created_at < %s
    """, (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))[0]

    categories = []
    for r in rows:
        avg = float(r["avg_hours"] or 0)
        categories.append({
            "category":     r["category"],
            "replied":      r["replied_count"],
            "avg_hours":    avg,
            "avg_display":  f"{int(avg // 24)}d {int(avg % 24)}h" if avg >= 24 else f"{avg}h",
            "min_hours":    r["min_hours"],
            "max_hours":    r["max_hours"],
            "rating":       "Fast" if avg < 48 else ("OK" if avg < 96 else "Slow"),
        })

    return json.dumps({
        "period":           label,
        "categories":       categories,
        "unreplied_paid":   int(unreplied["cnt"] or 0),
        "unreplied_value":  _fmt_mmk(unreplied["value"] or 0),
        "insight":          f"Slowest: {categories[-1]['category']} ({categories[-1]['avg_display']}). "
                            f"Fastest: {categories[0]['category']} ({categories[0]['avg_display']})."
                            if categories else "",
    })


# ─────────────────────────────────────────────────────────────
# Tool 9: Repeat Customer Analysis
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_repeat_customers(min_orders: int = 2, limit: int = 20) -> str:
    """
    Find loyal repeat customers and their spending patterns.

    ⚠️ ALWAYS use this tool when admin asks about:
    - loyal customers / repeat buyers
    - who orders most
    - customer retention
    - VIP customers

    Args:
        min_orders: Minimum order count to qualify (default 2)
        limit:      Max customers to return (default 20)

    Returns:
        List of repeat customers with order count, total spent, and favorite category.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    rows = _run_query("""
        SELECT
            o.customer_name,
            o.customer_phone,
            COUNT(o.id)                                                          AS total_orders,
            SUM(CASE WHEN o.status = 'complete' THEN 1 ELSE 0 END)              AS completed,
            COALESCE(SUM(CASE WHEN o.status = 'complete' THEN o.total_amount END), 0) AS total_spent,
            MAX(o.created_at)                                                    AS last_order,
            MIN(o.created_at)                                                    AS first_order
        FROM orders o
        WHERE o.deleted_at IS NULL AND o.customer_phone IS NOT NULL
        GROUP BY o.customer_phone, o.customer_name
        HAVING total_orders >= %s
        ORDER BY total_orders DESC, total_spent DESC
        LIMIT %s
    """, (min_orders, limit))

    if not rows:
        return json.dumps({"message": f"No customers with {min_orders}+ orders found."})

    customers = []
    for r in rows:
        customers.append({
            "name":         r["customer_name"],
            "phone":        r["customer_phone"],
            "total_orders": r["total_orders"],
            "completed":    r["completed"],
            "total_spent":  _fmt_mmk(r["total_spent"] or 0),
            "last_order":   str(r["last_order"])[:10] if r["last_order"] else None,
            "first_order":  str(r["first_order"])[:10] if r["first_order"] else None,
        })

    total_repeat = _run_query("""
        SELECT COUNT(*) AS cnt FROM (
            SELECT customer_phone FROM orders
            WHERE deleted_at IS NULL AND customer_phone IS NOT NULL
            GROUP BY customer_phone HAVING COUNT(*) >= %s
        ) t
    """, (min_orders,))[0]

    return json.dumps({
        "min_orders":      min_orders,
        "total_repeat_customers": int(total_repeat["cnt"] or 0),
        "showing":         len(customers),
        "customers":       customers,
    })


# ─────────────────────────────────────────────────────────────
# Tool 10: Promotion Effectiveness
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_promotion_effectiveness(period: str = "this_month") -> str:
    """
    Compare revenue and conversion between full-price, discount, and coupon orders.

    ⚠️ ALWAYS use this tool when admin asks about:
    - are discounts working
    - coupon vs discount effectiveness
    - promotion ROI
    - should we run more discounts

    Args:
        period: "this_month" | "last_month" | "all_time"

    Returns:
        Side-by-side comparison of full-price vs discount vs coupon orders.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    start, end, label = _resolve_period(period)

    rows = _run_query("""
        SELECT
            COALESCE(promotion_type, 'none')                                    AS promo_type,
            COUNT(*)                                                             AS total_orders,
            SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END)               AS completed,
            COALESCE(SUM(CASE WHEN status = 'complete' THEN total_amount END), 0) AS revenue,
            COALESCE(AVG(CASE WHEN status = 'complete' THEN total_amount END), 0) AS avg_order_value
        FROM orders
        WHERE deleted_at IS NULL
          AND created_at >= %s AND created_at < %s
        GROUP BY promotion_type
    """, (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))

    result = {}
    for r in rows:
        total = int(r["total_orders"] or 0)
        completed = int(r["completed"] or 0)
        conv = round(completed / total * 100, 1) if total else 0
        result[r["promo_type"]] = {
            "total_orders":    total,
            "completed":       completed,
            "conversion":      f"{conv}%",
            "revenue":         _fmt_mmk(r["revenue"] or 0),
            "avg_order_value": _fmt_mmk(r["avg_order_value"] or 0),
        }

    return json.dumps({
        "period":     label,
        "breakdown":  result,
        "insight":    "Compare conversion rates — higher conversion on discounted orders means promotions are working.",
    })


# ─────────────────────────────────────────────────────────────
# Tool 11: Holiday Sales Analysis
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_holiday_sales_analysis() -> str:
    """
    Analyze sales performance around upcoming Myanmar holidays and suggest discount timing.
    Use when admin asks about holiday strategy, upcoming festivals, or when to run promotions.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    from mcp_app.agent.myanmar_holidays import MYANMAR_HOLIDAYS, HOLIDAY_PERIODS
    from datetime import date

    today = datetime.now().date()
    upcoming = []
    for h_date, info in sorted(MYANMAR_HOLIDAYS.items()):
        delta = (h_date - today).days
        if 0 <= delta <= 60:
            upcoming.append({"date": str(h_date), "days_away": delta, "name": info["name"], "name_mm": info["name_mm"], "type": info["type"]})

    # Sales around last major holiday (look back 30 days)
    last30 = datetime.now() - timedelta(days=30)
    daily = _run_query("""
        SELECT DATE(created_at) AS day,
               COUNT(*) AS orders,
               COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) AS revenue
        FROM orders
        WHERE deleted_at IS NULL AND created_at >= %s
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """, (last30.strftime("%Y-%m-%d"),))

    peak = max(daily, key=lambda x: x["revenue"]) if daily else {}

    strategies = {
        "thingyan": "Launch discount 7-10 days before. Love & Relationship packages sell most.",
        "fullmoon":  "1-day flash discount on Full Moon day. Spiritual packages best.",
        "festival":  "Discount 5 days before. All categories benefit.",
        "public":    "Optional small discount on the holiday itself.",
    }

    return json.dumps({
        "upcoming_holidays": upcoming,
        "peak_day_last_30":  {"date": str(peak.get("day", "")), "revenue": _fmt_mmk(peak.get("revenue", 0)), "orders": peak.get("orders", 0)} if peak else None,
        "strategies":        strategies,
        "recommendation":    f"Next holiday: {upcoming[0]['name_mm']} in {upcoming[0]['days_away']} days ({upcoming[0]['date']}). Strategy: {strategies.get(upcoming[0]['type'], 'Run a promotion.')}" if upcoming else "No holidays in next 60 days.",
    })


# ─────────────────────────────────────────────────────────────
# Tool 12: Holiday Comparison
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_holiday_comparison() -> str:
    """
    Compare sales revenue during holiday periods vs normal periods.
    Use when admin asks if holidays boost sales or whether promotions during holidays work.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    from mcp_app.agent.myanmar_holidays import HOLIDAY_PERIODS

    results = []
    for key, period in list(HOLIDAY_PERIODS.items())[:5]:  # last 5 holiday periods
        try:
            start = period["start"]
            end   = period["end"]
            # Holiday window
            holiday_rows = _run_query("""
                SELECT COUNT(*) AS orders,
                       COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) AS revenue,
                       SUM(status='complete') AS completed
                FROM orders WHERE deleted_at IS NULL AND created_at BETWEEN %s AND %s
            """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))

            # Same duration before holiday
            duration = (end - start).days or 1
            pre_start = start - timedelta(days=duration)
            pre_rows = _run_query("""
                SELECT COUNT(*) AS orders,
                       COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) AS revenue
                FROM orders WHERE deleted_at IS NULL AND created_at BETWEEN %s AND %s
            """, (pre_start.strftime("%Y-%m-%d"), start.strftime("%Y-%m-%d")))

            h = holiday_rows[0]
            p = pre_rows[0]
            h_rev = int(h["revenue"] or 0)
            p_rev = int(p["revenue"] or 0)
            change = round((h_rev - p_rev) / p_rev * 100, 1) if p_rev else 0

            results.append({
                "holiday":          period.get("name", "Holiday"),
                "period":           f"{start} → {end}",
                "holiday_orders":   int(h["orders"] or 0),
                "holiday_revenue":  _fmt_mmk(h_rev),
                "pre_period_revenue": _fmt_mmk(p_rev),
                "revenue_change":   f"{change:+.1f}%",
                "verdict":          "Boost" if change > 10 else ("Slight boost" if change > 0 else "No boost"),
            })
        except Exception:
            continue

    return json.dumps({
        "holiday_comparisons": results,
        "insight": "Periods with >10% revenue increase vs pre-holiday = holidays drive sales.",
    })


# ─────────────────────────────────────────────────────────────
# Tool: System Reply Count by Date Range
# ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_system_reply_count(
    start_date: str = None,
    end_date: str = None,
    period: str = None,
    group_by: str = "day",
) -> str:
    """
    Count replied vs not-replied orders by the system for a date range or named period.

    ⚠️ Use this when admin asks:
    - "How many orders did the system reply today/this week/this month?"
    - "System reply count from 2025-01-01 to 2025-01-31"
    - "Show replied and unreplied orders breakdown"
    - "last 30 days replied orders"

    Args:
        start_date: YYYY-MM-DD (required if period not given)
        end_date:   YYYY-MM-DD (required if period not given)
        period:     "today" | "yesterday" | "this_week" | "this_month" | "last_month" | "last_30_days"
                    (overrides start_date/end_date if provided)
        group_by:   "day" | "month" | "week" | "none"  (default: "day")

    Returns:
        Total orders, replied, not_replied + per-period breakdown.
    """
    if not can('admin.access.order'):
        return json.dumps(_DENY)

    # Resolve period or date range
    if period == "last_30_days" or (not period and not start_date):
        now = datetime.now()
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date   = now.strftime("%Y-%m-%d")
        label = "Last 30 Days"
    elif period:
        start, end, label = _resolve_period(period)
        start_date = start.strftime("%Y-%m-%d")
        end_date   = end.strftime("%Y-%m-%d")
    else:
        if not end_date:
            return json.dumps({"error": "Provide 'end_date' or a 'period'."})
        label = f"{start_date} → {end_date}"

    group_expr = {
        "day":   "DATE(o.created_at)",
        "week":  "YEARWEEK(o.created_at, 1)",
        "month": "DATE_FORMAT(o.created_at, '%Y-%m')",
        "none":  "'all'",
    }.get(group_by, "DATE(o.created_at)")

    rows = _run_query(f"""
        SELECT
            {group_expr} AS period_group,
            COUNT(DISTINCT o.id)                                              AS total_orders,
            COUNT(DISTINCT r.order_id)                                        AS replied,
            COUNT(DISTINCT o.id) - COUNT(DISTINCT r.order_id)                AS not_replied,
            ROUND(COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.id) * 100, 1) AS reply_rate_pct
        FROM orders o
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE DATE(o.created_at) BETWEEN %s AND %s
          AND o.deleted_at IS NULL
        GROUP BY period_group
        ORDER BY period_group
    """, (start_date, end_date))

    total_orders  = sum(int(r["total_orders"]) for r in rows)
    total_replied = sum(int(r["replied"])       for r in rows)
    total_not     = total_orders - total_replied

    return json.dumps({
        "label":         label,
        "date_range":    f"{start_date} → {end_date}",
        "group_by":      group_by,
        "summary": {
            "total_orders":  total_orders,
            "replied":       total_replied,
            "not_replied":   total_not,
            "reply_rate":    f"{round(total_replied / total_orders * 100, 1) if total_orders else 0}%",
        },
        "breakdown": [
            {
                "period":       str(r["period_group"]),
                "total_orders": int(r["total_orders"]),
                "replied":      int(r["replied"]),
                "not_replied":  int(r["not_replied"]),
                "reply_rate":   f"{r['reply_rate_pct']}%",
            }
            for r in rows
        ],
    })
