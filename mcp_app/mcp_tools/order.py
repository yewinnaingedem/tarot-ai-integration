"""
mcp_app/mcp_tools/order.py
"""

from datetime import datetime, timedelta
from ..core import mcp
from ..models.order_model import Order
from ..db import get_connection


# ─────────────────────────────────────────────
# Shared formatter (your existing one)
# ─────────────────────────────────────────────
def format_orders(orders: list) -> list:
    formatted = []
    for o in orders:
        formatted.append({
            "id":       o.get("id"),
            "order_ref": o.get("order_ref"),
            "status":   o.get("status"),
            "customer": {
                "name":         o.get("customer_name"),
                "phone":        o.get("customer_phone"),
                "gender":       o.get("customer_gender"),
                "date_of_birth": o.get("date_of_birth"),
                "address":      o.get("address"),
            },
            "payment": {
                "method":        o.get("payment_method"),
                "complete":      bool(o.get("payment_complete")),
                "received_date": o.get("payment_received_date").strftime("%Y-%m-%d %H:%M")
                                 if o.get("payment_received_date") else None,
            },
            "pricing": {
                "total_amount":   o.get("total_amount"),
                "original_price": o.get("original_price"),
                "promotion_price": o.get("promotion_price"),
                "promotion_type": o.get("promotion_type"),
            },
            "package": {
                "package":       o.get("package_name"),
                "package_price": o.get("package_price"),
                "category":      o.get("category_name"),
            },
            "vendor_id":  o.get("vendor_id"),
            "remark":     o.get("remark"),
            "created_at": o.get("created_at").strftime("%Y-%m-%d %H:%M") if o.get("created_at") else None,
            "updated_at": o.get("updated_at").strftime("%Y-%m-%d %H:%M") if o.get("updated_at") else None,
        })
    return formatted


def _fmt_mmk(amount) -> str:
    return f"{int(amount or 0):,} MMK"


def _query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        conn.close()


def _period_range(period: str):
    """Return (start, end, label) for a named period."""
    now = datetime.now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, "Today"
    if period == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start.replace(hour=23, minute=59, second=59), "Yesterday"
    if period == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, "This Week"
    if period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now, "This Month"
    if period == "last_month":
        first = now.replace(day=1)
        start = (first - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, first - timedelta(seconds=1), "Last Month"
    raise ValueError(f"Unknown period '{period}'")


# ─────────────────────────────────────────────
# Your existing tools (unchanged)
# ─────────────────────────────────────────────
@mcp.tool()
def get_latest_order_from_db() -> dict:
    """GET LATEST ORDER from Database."""
    order = Order.get_latest_order_with_category()
    if not order:
        return {"message": "Something wrong"}
    return format_orders([order])[0]


@mcp.tool()
def get_order_by_date(created_at: str) -> dict:
    """
    GET ORDERS BY DATE from the database.
    Instructions for AI:
    - Always summarize total orders and total revenue first
    - Group orders by status (complete, pending, cancelled)
    - Highlight any suspicious or testing orders (check remark field)
    - Format currency with MMK prefix
    - Present customer info in a readable table format
    - If promotion_type is not null, mention the promotion used
    - Date format should be YYYY-MM-DD (example: 2025-01-09)
    """
    orders = Order.get_orders_by_date(created_at)
    formatted = format_orders(orders)
    return {
        "date":          created_at,
        "total_orders":  len(formatted),
        "total_revenue": sum(o["pricing"]["total_amount"] for o in formatted),
        "orders":        formatted,
    }


# ─────────────────────────────────────────────
# New Tool 1: Order Summary by Period
# ─────────────────────────────────────────────
@mcp.tool()
def get_order_summary(period: str = "today") -> dict:
    """
    Get order statistics for a time period.

    ⚠️ Use when admin asks:
    - today's / this week's / this month's orders
    - revenue totals, order counts
    - conversion rate

    Args:
        period: "today" | "yesterday" | "this_week" | "this_month" | "last_month"
    """
    try:
        start, end, label = _period_range(period)
    except ValueError as e:
        return {"error": str(e)}

    rows = _query("""
        SELECT
            COUNT(*)                                                        AS total,
            SUM(status = 'complete')                                        AS completed,
            SUM(status = 'pending')                                         AS pending,
            SUM(status = 'cancelled')                                       AS cancelled,
            COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) AS revenue,
            COALESCE(SUM(total_amount), 0)                                  AS potential_revenue
        FROM orders
        WHERE deleted_at IS NULL
          AND created_at BETWEEN %s AND %s
    """, (start, end))

    r         = rows[0]
    total     = int(r["total"] or 0)
    completed = int(r["completed"] or 0)
    pending   = int(r["pending"] or 0)
    cancelled = int(r["cancelled"] or 0)
    revenue   = int(r["revenue"] or 0)
    potential = int(r["potential_revenue"] or 0)
    conv_rate = round(completed / total * 100, 1) if total else 0

    return {
        "period":            label,
        "total_orders":      total,
        "completed":         completed,
        "pending":           pending,
        "cancelled":         cancelled,
        "conversion_rate":   f"{conv_rate}%",
        "revenue":           _fmt_mmk(revenue),
        "potential_revenue": _fmt_mmk(potential),
        "lost_from_pending": _fmt_mmk(potential - revenue),
    }


# ─────────────────────────────────────────────
# New Tool 2: Pending Follow-ups
# ─────────────────────────────────────────────
@mcp.tool()
def get_pending_followups(older_than_hours: int = 24) -> dict:
    """
    Get pending orders that need admin follow-up.

    ⚠️ Use when admin asks:
    - pending orders / who's waiting
    - follow-up list
    - customers not yet served

    Args:
        older_than_hours: Show pending orders older than N hours (default 24)
    """
    cutoff = datetime.now() - timedelta(hours=older_than_hours)

    rows = _query("""
        SELECT
            o.id, o.order_ref, o.customer_name, o.customer_phone,
            o.total_amount, o.remark, o.created_at,
            p.name  AS package_name,
            c.name  AS category_name,
            TIMESTAMPDIFF(HOUR, o.created_at, NOW()) AS hours_waiting
        FROM orders o
        LEFT JOIN packages   p ON o.package_id  = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE o.status = 'pending'
          AND o.deleted_at IS NULL
          AND o.created_at <= %s
        ORDER BY o.created_at ASC
        LIMIT 50
    """, (cutoff,))

    if not rows:
        return {
            "message":       f"No pending orders older than {older_than_hours}h. ✅",
            "total_pending": 0,
        }

    items = []
    for r in rows:
        hours = r["hours_waiting"] or 0
        items.append({
            "order_ref":     r["order_ref"],
            "customer":      r["customer_name"],
            "phone":         r["customer_phone"],
            "package":       r["package_name"] or "Unknown",
            "category":      r["category_name"] or "Unknown",
            "amount":        _fmt_mmk(r["total_amount"]),
            "remark":        r["remark"],
            "created_at":    str(r["created_at"]),
            "hours_waiting": hours,
            "urgency":       "🔴 URGENT" if hours > 48 else ("🟡 Follow up" if hours > 24 else "🟢 Recent"),
        })

    return {
        "total_pending":        len(items),
        "total_amount_at_risk": _fmt_mmk(sum(r["total_amount"] for r in rows)),
        "urgent_count":         sum(1 for i in items if "URGENT" in i["urgency"]),
        "orders":               items,
    }


# ─────────────────────────────────────────────
# New Tool 3: Package Performance
# ─────────────────────────────────────────────
@mcp.tool()
def get_package_performance(period: str = "this_month") -> dict:
    """
    Get best and worst performing packages by sales and revenue.

    ⚠️ Use when admin asks:
    - which packages sell most / least
    - underperforming packages
    - what to put on discount

    Args:
        period: "this_week" | "this_month" | "last_month" | "all_time"
    """
    if period == "all_time":
        start = datetime(2020, 1, 1)
        label = "All Time"
    else:
        try:
            start, _, label = _period_range(period)
        except ValueError as e:
            return {"error": str(e)}

    rows = _query("""
        SELECT
            p.id, p.name AS package_name, p.amount AS package_price,
            c.name AS category_name,
            COUNT(o.id)                                                         AS total_orders,
            SUM(o.status = 'complete')                                          AS completed,
            SUM(o.status = 'pending')                                           AS pending,
            SUM(o.status = 'cancelled')                                         AS cancelled,
            COALESCE(SUM(CASE WHEN o.status='complete' THEN o.total_amount END), 0) AS revenue
        FROM orders o
        JOIN packages   p ON o.package_id  = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY p.id, p.name, p.amount, c.name
        ORDER BY completed DESC, revenue DESC
    """, (start,))

    if not rows:
        return {"message": "No data found for this period."}

    result = []
    for i, r in enumerate(rows):
        total     = int(r["total_orders"] or 0)
        completed = int(r["completed"] or 0)
        conv      = round(completed / total * 100, 1) if total else 0
        result.append({
            "rank":         i + 1,
            "package":      r["package_name"],
            "category":     r["category_name"],
            "price":        _fmt_mmk(r["package_price"] or 0),
            "total_orders": total,
            "completed":    completed,
            "pending":      int(r["pending"] or 0),
            "conversion":   f"{conv}%",
            "revenue":      _fmt_mmk(r["revenue"]),
            "status":       "🔥 Top" if i < 3 else ("⚠️ Weak" if conv < 40 else "✅ Normal"),
        })

    return {
        "period":   label,
        "packages": result,
        "top":      result[0]["package"] if result else None,
        "weakest":  result[-1]["package"] if result else None,
    }


# ─────────────────────────────────────────────
# New Tool 4: Revenue Trends
# ─────────────────────────────────────────────
@mcp.tool()
def get_revenue_trends(granularity: str = "daily", days: int = 30) -> dict:
    """
    Get revenue trends over time.

    ⚠️ Use when admin asks:
    - revenue trends / sales over time
    - best days or weeks
    - is revenue growing or declining

    Args:
        granularity: "daily" | "weekly"
        days:        Number of past days to include (default 30)
    """
    start = datetime.now() - timedelta(days=days)

    if granularity == "weekly":
        rows = _query("""
            SELECT YEARWEEK(created_at, 1)  AS period_key,
                   MIN(DATE(created_at))    AS period_start,
                   COUNT(*)                 AS total_orders,
                   SUM(status = 'complete') AS completed,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) AS revenue
            FROM orders
            WHERE deleted_at IS NULL AND created_at >= %s
            GROUP BY YEARWEEK(created_at, 1)
            ORDER BY period_key
        """, (start,))
    else:
        rows = _query("""
            SELECT DATE(created_at)         AS period_key,
                   DATE(created_at)         AS period_start,
                   COUNT(*)                 AS total_orders,
                   SUM(status = 'complete') AS completed,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) AS revenue
            FROM orders
            WHERE deleted_at IS NULL AND created_at >= %s
            GROUP BY DATE(created_at)
            ORDER BY period_key
        """, (start,))

    if not rows:
        return {"message": "No revenue data found."}

    revenues  = [int(r["revenue"] or 0) for r in rows]
    total_rev = sum(revenues)
    peak_idx  = revenues.index(max(revenues))

    half     = len(revenues) // 2
    trend    = "📈 Growing"  if sum(revenues[half:]) > sum(revenues[:half]) else \
               "📉 Declining" if sum(revenues[half:]) < sum(revenues[:half]) else \
               "➡️ Stable"

    return {
        "granularity":    f"{granularity.capitalize()} (last {days} days)",
        "trend":          trend,
        "total_revenue":  _fmt_mmk(total_rev),
        "avg_per_period": _fmt_mmk(total_rev // len(revenues)),
        "peak_date":      str(rows[peak_idx]["period_start"]),
        "peak_revenue":   _fmt_mmk(revenues[peak_idx]),
        "periods": [
            {
                "period":       str(r["period_start"]),
                "total_orders": r["total_orders"],
                "completed":    r["completed"],
                "revenue":      _fmt_mmk(r["revenue"]),
                "revenue_raw":  int(r["revenue"] or 0),
            }
            for r in rows
        ],
    }


# ─────────────────────────────────────────────
# New Tool 5: AI Sales Suggestions
# ─────────────────────────────────────────────
@mcp.tool()
def get_ai_sales_suggestions() -> dict:
    """
    Analyze sales data and return AI-powered suggestions to improve revenue.

    ⚠️ Use when admin asks:
    - how to improve sales
    - what discount to run
    - AI suggestions / advice
    - sales strategy
    """
    now        = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last30      = now - timedelta(days=30)

    month = _query("""
        SELECT COUNT(*) total,
               SUM(status='complete')  completed,
               SUM(status='pending')   pending,
               COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) revenue
        FROM orders WHERE deleted_at IS NULL AND created_at >= %s
    """, (month_start,))[0]

    top_pkgs = _query("""
        SELECT p.name, c.name cat, COUNT(*) cnt,
               ROUND(SUM(o.status='complete') / COUNT(*) * 100, 1) conv,
               COALESCE(SUM(CASE WHEN o.status='complete' THEN o.total_amount END), 0) rev
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY p.id, p.name, c.name
        ORDER BY cnt DESC LIMIT 5
    """, (last30,))

    weak_pkgs = _query("""
        SELECT p.name, c.name cat, COUNT(*) cnt,
               ROUND(SUM(o.status='complete') / COUNT(*) * 100, 1) conv, p.amount
        FROM orders o
        JOIN packages p ON o.package_id = p.id
        JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.created_at >= %s
        GROUP BY p.id, p.name, c.name, p.amount
        HAVING cnt >= 3 AND conv < 50
        ORDER BY conv ASC LIMIT 5
    """, (last30,))

    pending = _query("""
        SELECT COUNT(*) cnt,
               COALESCE(SUM(total_amount), 0) val,
               MAX(TIMESTAMPDIFF(HOUR, created_at, NOW())) max_wait
        FROM orders WHERE status='pending' AND deleted_at IS NULL
    """)[0]

    best_days = _query("""
        SELECT DAYNAME(created_at) day_name,
               COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END), 0) revenue
        FROM orders WHERE deleted_at IS NULL AND created_at >= %s
        GROUP BY DAYNAME(created_at), DAYOFWEEK(created_at)
        ORDER BY revenue DESC LIMIT 3
    """, (last30,))

    # Build suggestions
    total     = int(month["total"] or 0)
    completed = int(month["completed"] or 0)
    conv_rate = round(completed / total * 100, 1) if total else 0
    suggestions = []

    pending_cnt = int(pending["cnt"] or 0)
    if pending_cnt > 0:
        suggestions.append({
            "priority": "🔴 HIGH",
            "title":    "Follow Up Pending Orders",
            "detail":   f"{pending_cnt} pending orders worth {_fmt_mmk(pending['val'])}. "
                        f"Oldest waiting {pending['max_wait']} hours.",
            "action":   "Call get_pending_followups and contact customers via phone/Viber.",
        })

    if weak_pkgs:
        names = ", ".join(p["name"] for p in weak_pkgs[:3])
        suggestions.append({
            "priority": "🟡 MEDIUM",
            "title":    "Discount Underperforming Packages",
            "detail":   f"Low conversion packages: {names}. A 15-20% discount can convert fence-sitters.",
            "action":   "Use create_discount tool for these packages.",
        })

    if top_pkgs:
        t = top_pkgs[0]
        suggestions.append({
            "priority": "🟢 OPPORTUNITY",
            "title":    "Amplify Top Seller",
            "detail":   f"'{t['name']}' ({t['cat']}) leads with {t['cnt']} orders and {t['conv']}% conversion.",
            "action":   "Promote this package more. Ensure enough readers are available.",
        })

    if best_days:
        days_str = ", ".join(d["day_name"] for d in best_days)
        suggestions.append({
            "priority": "🟢 OPPORTUNITY",
            "title":    "Run Promotions on Peak Days",
            "detail":   f"Highest revenue days: {days_str}.",
            "action":   "Schedule discounts to start on these days.",
        })

    if conv_rate < 60:
        suggestions.append({
            "priority": "🟡 MEDIUM",
            "title":    "Improve Conversion Rate",
            "detail":   f"Current rate: {conv_rate}%. Target: >70%. Slow response is likely losing sales.",
            "action":   "Follow up pending orders within 6 hours to boost conversion.",
        })

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "this_month": {
            "total_orders":    total,
            "completed":       completed,
            "pending":         int(month["pending"] or 0),
            "revenue":         _fmt_mmk(month["revenue"]),
            "conversion_rate": f"{conv_rate}%",
        },
        "top_packages":  [{"name": p["name"], "category": p["cat"], "orders": p["cnt"], "conversion": f"{p['conv']}%", "revenue": _fmt_mmk(p["rev"])} for p in top_pkgs],
        "weak_packages": [{"name": p["name"], "category": p["cat"], "conversion": f"{p['conv']}%", "price": _fmt_mmk(p["amount"] or 0)} for p in weak_pkgs],
        "best_days":     [{"day": d["day_name"], "revenue": _fmt_mmk(d["revenue"])} for d in best_days],
        "suggestions":   suggestions,
    }

@mcp.tool()
def get_holiday_sales_analysis() -> dict:
    """
    Analyze sales performance during past holidays and
    predict/prepare for upcoming holidays.

    ⚠️ Use when admin asks:
    - holiday sales analysis
    - how was Thingyan sales last year
    - prepare for upcoming holiday
    - holiday marketing strategy
    """
    today    = datetime.now().date()
    upcoming = get_upcoming_holidays(days_ahead=90)

    # ── Analyze past holiday periods ──────────────────────────
    holiday_analysis = []

    for key, period in HOLIDAY_PERIODS.items():
        if period["end"] >= today:
            continue  # skip future periods

        pre_start = period["pre_start"]
        start     = period["start"]
        end       = period["end"]
        post_end  = end + timedelta(days=7)

        # Pre-holiday sales
        pre = _query("""
            SELECT COUNT(*) total,
                   SUM(status='complete') completed,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue
            FROM orders
            WHERE deleted_at IS NULL
              AND DATE(created_at) BETWEEN %s AND %s
        """, (pre_start, start - timedelta(days=1)))

        # During holiday
        during = _query("""
            SELECT COUNT(*) total,
                   SUM(status='complete') completed,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue
            FROM orders
            WHERE deleted_at IS NULL
              AND DATE(created_at) BETWEEN %s AND %s
        """, (start, end))

        # Post-holiday
        post = _query("""
            SELECT COUNT(*) total,
                   SUM(status='complete') completed,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue
            FROM orders
            WHERE deleted_at IS NULL
              AND DATE(created_at) BETWEEN %s AND %s
        """, (end + timedelta(days=1), post_end))

        pre_rev    = int(pre[0]["revenue"]    or 0)
        during_rev = int(during[0]["revenue"] or 0)
        post_rev   = int(post[0]["revenue"]   or 0)

        holiday_analysis.append({
            "holiday":      period["name"],
            "name_mm":      period["name_mm"],
            "period":       f"{start} to {end}",
            "pre_holiday":  {
                "period":   f"{pre_start} to {start - timedelta(days=1)}",
                "orders":   int(pre[0]["total"]    or 0),
                "revenue":  _fmt_mmk(pre_rev),
            },
            "during_holiday": {
                "period":   f"{start} to {end}",
                "orders":   int(during[0]["total"] or 0),
                "revenue":  _fmt_mmk(during_rev),
            },
            "post_holiday": {
                "period":   f"{end + timedelta(days=1)} to {post_end}",
                "orders":   int(post[0]["total"]   or 0),
                "revenue":  _fmt_mmk(post_rev),
            },
            "insight": (
                "📈 Pre-holiday surge" if pre_rev > during_rev
                else "🎉 Peak during holiday" if during_rev >= pre_rev and during_rev >= post_rev
                else "📉 Post-holiday recovery" if post_rev > during_rev
                else "➡️ Stable across period"
            ),
        })

    # ── Upcoming holiday preparation ──────────────────────────
    preparations = []
    for h in upcoming[:5]:
        days_away = h["days_away"]
        htype     = h["type"]

        if days_away <= 30:
            if htype == "thingyan":
                preparations.append({
                    "holiday":      h["name"],
                    "name_mm":      h["name_mm"],
                    "date":         h["date"],
                    "days_away":    days_away,
                    "urgency":      "🔴 Act Now" if days_away <= 7 else "🟡 Plan Now",
                    "suggestions":  [
                        f"Start pre-Thingyan discount {max(1, days_away-7)} days before ({h['date']})",
                        "Love & Relationship packages sell most during Thingyan",
                        "Create bundle packages for water festival season",
                        "Prepare for high order volume — ensure reader availability",
                        "Send KBZPay push notification to past customers",
                    ],
                })
            elif htype == "festival":
                preparations.append({
                    "holiday":      h["name"],
                    "name_mm":      h["name_mm"],
                    "date":         h["date"],
                    "days_away":    days_away,
                    "urgency":      "🔴 Act Now" if days_away <= 7 else "🟡 Plan Now",
                    "suggestions":  [
                        f"Launch holiday discount 5-7 days before {h['name']}",
                        "Full Moon days are spiritually significant — promote special readings",
                        "Create limited-time festival packages",
                    ],
                })
            else:
                preparations.append({
                    "holiday":      h["name"],
                    "name_mm":      h["name_mm"],
                    "date":         h["date"],
                    "days_away":    days_away,
                    "urgency":      "🟢 Keep in mind",
                    "suggestions":  [
                        f"Consider a small promotion around {h['name']}",
                        "Monitor order volume — public holidays often boost spiritual interest",
                    ],
                })

    return {
        "today":               today.strftime("%Y-%m-%d"),
        "upcoming_holidays":   upcoming,
        "past_holiday_analysis": holiday_analysis,
        "holiday_preparations":  preparations,
        "summary": (
            f"{len(upcoming)} upcoming holidays in next 90 days. "
            f"Analyzed {len(holiday_analysis)} past holiday periods."
        ),
    }


@mcp.tool()
def get_holiday_comparison(holiday_name: str = "thingyan") -> dict:
    """
    Compare sales for the same holiday across different years.

    ⚠️ Use when admin asks:
    - compare Thingyan sales 2024 vs 2025
    - how did sales change year over year during holiday
    - was last year better than this year for a holiday

    Args:
        holiday_name: "thingyan" | "thadingyut" | "tazaungdaing"
    """
    # Find all matching holiday periods
    matching = {
        k: v for k, v in HOLIDAY_PERIODS.items()
        if holiday_name.lower() in k.lower()
    }

    if not matching:
        return {"error": f"No holiday found matching '{holiday_name}'"}

    results = []
    for key, period in sorted(matching.items()):
        rows = _query("""
            SELECT COUNT(*) total,
                   SUM(status='complete') completed,
                   SUM(status='pending')  pending,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue,
                   COUNT(DISTINCT DATE(created_at)) days_active
            FROM orders
            WHERE deleted_at IS NULL
              AND DATE(created_at) BETWEEN %s AND %s
        """, (period["pre_start"], period["end"]))

        r         = rows[0]
        total     = int(r["total"]    or 0)
        completed = int(r["completed"] or 0)
        revenue   = int(r["revenue"]  or 0)
        conv      = round(completed / total * 100, 1) if total else 0

        results.append({
            "year":          period["start"].year,
            "holiday":       period["name"],
            "period":        f"{period['pre_start']} → {period['end']}",
            "total_orders":  total,
            "completed":     completed,
            "pending":       int(r["pending"] or 0),
            "revenue":       _fmt_mmk(revenue),
            "revenue_raw":   revenue,
            "conversion":    f"{conv}%",
        })

    # Year over year comparison
    yoy = None
    if len(results) >= 2:
        curr = results[-1]
        prev = results[-2]
        rev_change = curr["revenue_raw"] - prev["revenue_raw"]
        yoy = {
            "revenue_change":  _fmt_mmk(abs(rev_change)),
            "direction":       "📈 Increased" if rev_change > 0 else "📉 Decreased",
            "order_change":    curr["total_orders"] - prev["total_orders"],
        }

    return {
        "holiday":      holiday_name.title(),
        "years":        results,
        "year_on_year": yoy,
        "recommendation": (
            "Based on historical data, prepare discounts 7 days before the holiday "
            "and ensure full reader availability during peak days."
        ) if results else "Not enough data yet.",
    }