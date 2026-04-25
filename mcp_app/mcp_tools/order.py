"""
mcp_app/mcp_tools/order.py
"""

from datetime import datetime, timedelta
from ..core import mcp
from ..models.order_model import Order
from ..db import get_connection
from ..agent.myanmar_holidays import get_upcoming_holidays , HOLIDAY_PERIODS 
from ..permission import can

_DENY = {"message": "You don't have permission to view orders."}


# ─────────────────────────────────────────────
# Shared formatter (your existing one)
# ─────────────────────────────────────────────
def _fmt_dt(val, fmt="%Y-%m-%d %H:%M"):
    if not val:
        return None
    if hasattr(val, 'strftime'):
        return val.strftime(fmt)
    return str(val)[:16]

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
                "received_date": _fmt_dt(o.get("payment_received_date")),
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
            "created_at": _fmt_dt(o.get("created_at")),
            "updated_at": _fmt_dt(o.get("updated_at")),
        })
    return formatted


from decimal import Decimal

def _fmt_mmk(amount) -> str:
    return f"{int(amount or 0):,} MMK"


def _clean_row(row: dict) -> dict:
    from datetime import date, datetime
    return {
        k: (int(v) if isinstance(v, Decimal) and v == int(v) else float(v))
           if isinstance(v, Decimal)
           else str(v) if isinstance(v, (date, datetime))
           else v
        for k, v in row.items()
    }


def _query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return [_clean_row(r) for r in cursor.fetchall()]
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
@mcp.tool()
def get_orders_by_ref(order_refs: str) -> dict:
    """
    Look up one or more orders by their reference codes.
    order_refs: comma-separated order refs, e.g. "PKTR-AAIYS,PKTR-AAIYP"
    """
    if not can('admin.access.order'):
        return _DENY

    refs = [r.strip() for r in order_refs.split(",") if r.strip()]
    if not refs:
        return {"error": "No order refs provided"}

    # Auto-fix common typos: add PKTR- prefix if missing
    fixed_refs = []
    for r in refs:
        r = r.upper()
        if not r.startswith("PKTR-"):
            fixed_refs.append("PKTR-" + r.replace("KTR-", "").replace("PTR-", ""))
        else:
            fixed_refs.append(r)
    refs = fixed_refs

    placeholders = ",".join(["%s"] * len(refs))
    rows = _query(f"""
        SELECT o.*, p.name AS package_name, p.amount AS package_price,
               c.name AS category_name,
               r.id AS reply_id, r.answer AS reply_answer
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.order_ref IN ({placeholders}) AND o.deleted_at IS NULL
    """, tuple(refs))

    if not rows:
        return {"message": "No orders found", "refs": refs}

    orders = []
    for o in rows:
        orders.append({
            "order_ref":     o["order_ref"],
            "customer":      o["customer_name"],
            "phone":         o["customer_phone"],
            "gender":        o.get("customer_gender"),
            "date_of_birth": o.get("date_of_birth"),
            "package":       o.get("package_name"),
            "category":      o.get("category_name"),
            "amount":        _fmt_mmk(o["total_amount"]),
            "remark":        (o.get("remark") or "")[:300],
            "status":        o["status"],
            "payment_complete": bool(o["payment_complete"]),
            "replied":       bool(o.get("reply_id")),
            "reply_answer":  (o.get("reply_answer") or "")[:200] if o.get("reply_id") else None,
            "created_at":    str(o["created_at"]),
        })
    return {"total": len(orders), "orders": orders}


# ─────────────────────────────────────────────
@mcp.tool()
def get_orders_by_holiday(holiday_name: str, include_pre_period: bool = False) -> dict:
    """
    Get orders for a specific Myanmar holiday period by name.
    Use when admin asks about sales/orders during a specific festival or holiday.

    Examples:
    - "သီတင်းကျွတ်ပွဲ sale" → holiday_name="thadingyut"
    - "သင်္ကြန် orders" → holiday_name="thingyan"
    - "တန်ဆောင်တိုင် sales" → holiday_name="tazaungdaing"

    Args:
        holiday_name: keyword to match — "thadingyut", "thingyan", "tazaungdaing",
                      or any Myanmar name like "သီတင်းကျွတ်", "သင်္ကြန်", "တန်ဆောင်တိုင်"
        include_pre_period: if True, include pre-holiday boost period too
    """
    if not can('admin.access.order'):
        return _DENY

    from mcp_app.agent.myanmar_holidays import HOLIDAY_PERIODS

    # Keyword → period key mapping
    keyword_map = {
        "thadingyut":    "thadingyut",
        "သီတင်းကျွတ်":  "thadingyut",
        "thingyan":      "thingyan",
        "သင်္ကြန်":     "thingyan",
        "tazaungdaing":  "tazaungdaing",
        "တန်ဆောင်တိုင်": "tazaungdaing",
        "valentine":     "valentine",
        "ချစ်သူ":        "valentine",
        "christmas":     "christmas",
        "ခရစ်စမတ်":     "christmas",
        "new year":      "new_year",
        "နှစ်သစ်ကူး":   "new_year",
        "chinese":       "chinese_new_year",
        "တရုတ်":         "chinese_new_year",
    }

    name_lower = holiday_name.lower().strip()
    matched_key = None
    for kw, key in keyword_map.items():
        if kw in name_lower or kw in holiday_name:
            matched_key = key
            break

    # Find all matching periods (e.g. thadingyut_2025)
    matched_periods = {
        k: v for k, v in HOLIDAY_PERIODS.items()
        if matched_key and matched_key in k
    }

    if not matched_periods:
        available = list(HOLIDAY_PERIODS.keys())
        return {"error": f"Holiday '{holiday_name}' not found. Available: {available}"}

    results = []
    for period_key, period in sorted(matched_periods.items()):
        start = period["pre_start"] if include_pre_period else period["start"]
        end = period["end"]
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        rows = _query("""
            SELECT o.*, p.name AS package_name, p.amount AS package_price,
                   c.name AS category_name
            FROM orders o
            LEFT JOIN packages p ON o.package_id = p.id
            LEFT JOIN category c ON p.category_id = c.id
            WHERE DATE(o.created_at) BETWEEN %s AND %s
              AND o.deleted_at IS NULL
            ORDER BY o.created_at DESC
        """, (start_str, end_str))

        total_revenue = sum(r["total_amount"] or 0 for r in rows if r["status"] == "complete")
        completed = sum(1 for r in rows if r["status"] == "complete")
        conv = round(completed / len(rows) * 100, 1) if rows else 0

        results.append({
            "period":       period["name"],
            "period_mm":    period["name_mm"],
            "date_range":   f"{start_str} → {end_str}",
            "total_orders": len(rows),
            "completed":    completed,
            "conversion":   f"{conv}%",
            "revenue":      _fmt_mmk(total_revenue),
            "orders": [
                {
                    "order_ref":  r["order_ref"],
                    "customer":   r["customer_name"],
                    "package":    r.get("package_name"),
                    "category":   r.get("category_name"),
                    "amount":     _fmt_mmk(r["total_amount"]),
                    "status":     r["status"],
                    "created_at": str(r["created_at"])[:16],
                }
                for r in rows[:50]
            ],
        })

    return {"holidays": results, "total_periods_found": len(results)}
    """GET LATEST ORDER from Database."""
    if not can('admin.access.order.view') :
        return _DENY
    order = Order.get_latest_order_with_category()
    if not order:
        return {"message": "Something wrong"}
    return format_orders([order])[0]


@mcp.tool()
def get_order_by_date(start_date: str, end_date: str = None) -> dict:
    """
    Get orders between two dates.
    start_date: YYYY-MM-DD (required)
    end_date: YYYY-MM-DD (optional, defaults to start_date for single day)
    """
    print(f"🔍 get_order_by_date called: start={start_date} end={end_date}")

    if not can('admin.access.order'):
        return _DENY

    if not end_date:
        end_date = start_date

    try:
        orders = Order.get_orders_by_date_range(start_date, end_date)
        print(f"Orders found: {len(orders)}")
    except Exception as e:
        print(f"❌ Error in get_orders_by_date_range: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

    formatted = format_orders(orders)
    result = {
        "start_date":    start_date,
        "end_date":      end_date,
        "total_orders":  len(formatted),
        "total_revenue": sum(o["pricing"]["total_amount"] or 0 for o in formatted),
    }
    if len(formatted) > 50:
        # Too many orders — return summary + category breakdown instead of raw data
        cat_stats = {}
        status_stats = {"complete": 0, "pending": 0, "cancelled": 0}
        for o in formatted:
            cat = o.get("package", {}).get("category") or "Unknown"
            if cat not in cat_stats:
                cat_stats[cat] = {"orders": 0, "revenue": 0}
            cat_stats[cat]["orders"] += 1
            cat_stats[cat]["revenue"] += o["pricing"]["total_amount"] or 0
            s = o.get("status", "")
            if s in status_stats:
                status_stats[s] += 1
        result["status_breakdown"] = status_stats
        result["category_breakdown"] = cat_stats
        result["note"] = f"Too many orders ({len(formatted)}) to list individually. Use get_category_analysis or get_order_summary for detailed analysis."
    else:
        result["orders"] = formatted
    return result
# ─────────────────────────────────────────────
# Paid but unreplied orders — remind admin
# ─────────────────────────────────────────────
@mcp.tool()
def get_unreplied_paid_orders(older_than_hours: int = 0) -> dict:
    """
    Get orders where customer already PAID but admin has NOT replied yet.
    These are the most urgent — customer is waiting for their tarot reading.

    ⚠️ Use when admin asks:
    - unreplied orders / unanswered orders
    - who paid but hasn't received answer
    - remind me to reply / what should I answer
    - orders I need to respond to
    - paid but not answered

    Args:
        older_than_hours: Only show orders older than N hours (default 0 = all unreplied)
    """
    if not can('admin.access.order'):
        return _DENY

    cutoff_clause = ""
    params = ()
    if older_than_hours > 0:
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        cutoff_clause = "AND o.created_at <= %s"
        params = (cutoff,)

    # Accurate totals (no LIMIT)
    stats = _query(f"""
        SELECT
            COUNT(*)                   AS total,
            COALESCE(SUM(o.total_amount), 0) AS total_amt,
            SUM(CASE WHEN TIMESTAMPDIFF(HOUR, o.created_at, NOW()) > 72 THEN 1 ELSE 0 END) AS critical,
            SUM(CASE WHEN TIMESTAMPDIFF(HOUR, o.created_at, NOW()) BETWEEN 49 AND 72 THEN 1 ELSE 0 END) AS urgent
        FROM orders o
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.payment_complete = 1
          AND o.status = 'pending'
          AND o.deleted_at IS NULL
          AND r.id IS NULL
          {cutoff_clause}
    """, params)

    total_count = stats[0]["total"] if stats else 0
    total_amt   = stats[0]["total_amt"] if stats else 0
    critical    = int(stats[0]["critical"] or 0) if stats else 0
    urgent_cnt  = int(stats[0]["urgent"] or 0) if stats else 0

    if total_count == 0:
        return {
            "message": "ငွေလွှဲပြီး မဖြေရသေးတဲ့ order မရှိပါ။",
            "total": 0,
        }

    # Show top 20 oldest (most urgent) with details
    rows = _query(f"""
        SELECT
            o.id, o.order_ref, o.customer_name, o.customer_phone,
            o.customer_gender, o.date_of_birth,
            o.total_amount, o.remark, o.created_at, o.payment_received_date,
            p.name  AS package_name,
            c.name  AS category_name,
            TIMESTAMPDIFF(HOUR, o.created_at, NOW()) AS hours_waiting
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.payment_complete = 1
          AND o.status = 'pending'
          AND o.deleted_at IS NULL
          AND r.id IS NULL
          {cutoff_clause}
        ORDER BY o.created_at ASC
        LIMIT 20
    """, params)

    items = []
    for r in rows:
        hours = r["hours_waiting"] or 0
        items.append({
            "order_ref":     r["order_ref"],
            "customer":      r["customer_name"],
            "phone":         r["customer_phone"],
            "date_of_birth": r["date_of_birth"],
            "package":       r["package_name"] or "Unknown",
            "amount":        _fmt_mmk(r["total_amount"]),
            "question":      (r["remark"] or "")[:100],
            "hours_waiting": hours,
            "urgency": (
                "CRITICAL" if hours > 72 else
                "URGENT"   if hours > 48 else
                "Follow up" if hours > 24 else
                "Recent"
            ),
        })

    return {
        "total":          total_count,
        "critical_count": critical,
        "urgent_count":   urgent_cnt,
        "total_revenue_waiting": _fmt_mmk(total_amt),
        "showing":        len(items),
        "summary": (
            f"ငွေလွှဲပြီး မဖြေရသေးတဲ့ order စုစုပေါင်း {total_count} ခုရှိပါတယ်။ "
            f"{'CRITICAL: ' + str(critical) + ' ခုက 72 နာရီကျော်နေပါပြီ။ ' if critical else ''}"
            f"{'URGENT: ' + str(urgent_cnt) + ' ခုက 48 နာရီကျော်နေပါပြီ။' if urgent_cnt else ''}"
        ),
        "orders": items,
    }


@mcp.tool()
def reply_to_order(order_ref: str, answer: str) -> dict:
    """
    Reply to a paid pending order. Creates reply record and marks order complete.

    Args:
        order_ref: The order reference code (e.g. PKTR-AAGYS)
        answer: The reply text to send to customer
    """
    if not can('admin.access.order'):
        return _DENY

    # Auto-fix common typos
    order_ref = order_ref.upper()
    if not order_ref.startswith("PKTR-"):
        order_ref = "PKTR-" + order_ref.replace("KTR-", "").replace("PTR-", "")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT o.id, o.order_ref, o.customer_name, o.status, o.payment_complete,
                   r.id AS reply_id
            FROM orders o
            LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
            WHERE o.order_ref = %s AND o.deleted_at IS NULL
        """, (order_ref,))
        order = cur.fetchone()

        if not order:
            return {"error": f"Order {order_ref} not found"}
        if order["reply_id"]:
            return {"error": f"Order {order_ref} already has a reply"}
        if not order["payment_complete"]:
            return {"error": f"Order {order_ref} payment not complete yet"}
        if order["status"] != "pending":
            return {"error": f"Order {order_ref} status is {order['status']}, not pending"}

        cur.execute(
            "INSERT INTO reply (order_id, answer, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
            (order["id"], answer),
        )
        cur.execute(
            "UPDATE orders SET status = 'complete', updated_at = NOW() WHERE id = %s",
            (order["id"],),
        )
        conn.commit()

        return {
            "success": True,
            "order_ref": order["order_ref"],
            "customer": order["customer_name"],
        }
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@mcp.tool()
def batch_reply_orders(order_refs: str, answer: str) -> dict:
    """
    Reply to multiple orders at once with the same answer.
    Creates reply records and marks all orders as complete.

    Args:
        order_refs: Comma-separated order refs, e.g. "PKTR-AAHHE,PKTR-AAHKB,PKTR-AAHKI"
        answer: The reply text to send to all customers
    """
    if not can('admin.access.order'):
        return _DENY

    refs = [r.strip() for r in order_refs.split(",") if r.strip()]
    if not refs:
        return {"error": "No order refs provided"}

    # Auto-fix refs
    refs = ["PKTR-" + r.upper().replace("KTR-", "").replace("PTR-", "") if not r.upper().startswith("PKTR-") else r.upper() for r in refs]

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        success = []
        failed = []

        for ref in refs:
            cur.execute("""
                SELECT o.id, o.order_ref, o.customer_name, o.payment_complete, o.status,
                       r.id AS reply_id
                FROM orders o
                LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
                WHERE o.order_ref = %s AND o.deleted_at IS NULL
            """, (ref,))
            order = cur.fetchone()

            if not order:
                failed.append({"ref": ref, "reason": "not found"})
            elif order["reply_id"]:
                failed.append({"ref": ref, "reason": "already replied"})
            elif not order["payment_complete"]:
                failed.append({"ref": ref, "reason": "not paid"})
            elif order["status"] not in ("pending",):
                failed.append({"ref": ref, "reason": f"status is {order['status']}, not pending"})
            else:
                cur.execute(
                    "INSERT INTO reply (order_id, answer, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
                    (order["id"], answer),
                )
                cur.execute("UPDATE orders SET status='complete', updated_at=NOW() WHERE id=%s", (order["id"],))
                success.append({"ref": order["order_ref"], "customer": order["customer_name"]})

        conn.commit()
        return {
            "success_count": len(success),
            "failed_count": len(failed),
            "replied": success,
            "failed": failed if failed else None,
        }
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@mcp.tool()
def search_orders_by_phone(phone: str, limit: int = 20) -> dict:
    """
    Search all orders by customer phone number.
    Use when admin asks about a specific customer by phone.

    Args:
        phone: Customer phone number (partial match supported)
        limit: Max orders to return (default 20)
    """
    if not can('admin.access.order'):
        return _DENY

    rows = _query("""
        SELECT o.*, p.name AS package_name, p.amount AS package_price,
               c.name AS category_name,
               r.answer AS reply_answer
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.deleted_at IS NULL AND o.customer_phone LIKE %s
        ORDER BY o.created_at DESC
        LIMIT %s
    """, (f"%{phone}%", limit))

    if not rows:
        return {"message": f"No orders found for phone: {phone}"}

    orders = []
    total_spent = 0
    for o in rows:
        orders.append({
            "order_ref":     o["order_ref"],
            "customer":      o["customer_name"],
            "phone":         o["customer_phone"],
            "date_of_birth": o.get("date_of_birth"),
            "package":       o.get("package_name"),
            "category":      o.get("category_name"),
            "amount":        _fmt_mmk(o["total_amount"]),
            "status":        o["status"],
            "payment_complete": bool(o["payment_complete"]),
            "replied":       bool(o.get("reply_answer")),
            "remark":        (o.get("remark") or "")[:200],
            "created_at":    str(o["created_at"]),
        })
        if o["status"] == "complete":
            total_spent += o["total_amount"] or 0

    return {
        "phone":       phone,
        "total_orders": len(orders),
        "total_spent":  _fmt_mmk(total_spent),
        "orders":       orders,
    }


@mcp.tool()
def get_order_stats_by_customer(phone: str) -> dict:
    """
    Full KYC + order history for a customer by phone number.
    Use when admin asks about a specific customer's profile, history, or spending.

    Args:
        phone: Customer phone number
    """
    if not can('admin.access.order'):
        return _DENY

    rows = _query("""
        SELECT o.customer_name, o.customer_phone, o.customer_gender, o.date_of_birth,
               o.address, o.status, o.total_amount, o.payment_complete,
               o.order_ref, o.created_at,
               p.name AS package_name, c.name AS category_name
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE o.deleted_at IS NULL AND o.customer_phone LIKE %s
        ORDER BY o.created_at DESC
    """, (f"%{phone}%",))

    if not rows:
        return {"message": f"No customer found with phone: {phone}"}

    first = rows[0]
    total_spent = sum(r["total_amount"] or 0 for r in rows if r["status"] == "complete")
    fav_cats = {}
    for r in rows:
        cat = r["category_name"] or "Unknown"
        fav_cats[cat] = fav_cats.get(cat, 0) + 1
    fav_category = max(fav_cats, key=fav_cats.get) if fav_cats else None

    return {
        "customer": {
            "name":         first["customer_name"],
            "phone":        first["customer_phone"],
            "gender":       first["customer_gender"],
            "date_of_birth": str(first["date_of_birth"]) if first["date_of_birth"] else None,
            "address":      first["address"],
        },
        "stats": {
            "total_orders":  len(rows),
            "completed":     sum(1 for r in rows if r["status"] == "complete"),
            "pending":       sum(1 for r in rows if r["status"] == "pending"),
            "total_spent":   _fmt_mmk(total_spent),
            "favorite_category": fav_category,
            "first_order":   str(rows[-1]["created_at"])[:10],
            "last_order":    str(rows[0]["created_at"])[:10],
        },
        "orders": [
            {
                "order_ref": r["order_ref"],
                "package":   r["package_name"],
                "category":  r["category_name"],
                "amount":    _fmt_mmk(r["total_amount"]),
                "status":    r["status"],
                "date":      str(r["created_at"])[:10],
            } for r in rows
        ],
    }


@mcp.tool()
def update_order_status(order_ref: str, status: str, reason: str = "") -> dict:
    """
    Update an order's status manually (cancel, revert to pending, etc).
    Use when admin wants to cancel an order or change its status.

    Args:
        order_ref: Order reference code (PKTR-XXXXX)
        status:    New status: "cancelled" | "pending" | "complete"
        reason:    Optional reason for the change
    """
    if not can('admin.access.order'):
        return _DENY

    if status not in ("cancelled", "pending", "complete"):
        return {"error": "status must be 'cancelled', 'pending', or 'complete'"}

    order_ref = order_ref.upper()
    if not order_ref.startswith("PKTR-"):
        order_ref = "PKTR-" + order_ref.replace("KTR-", "").replace("PTR-", "")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, order_ref, status, customer_name FROM orders WHERE order_ref = %s AND deleted_at IS NULL", (order_ref,))
        order = cur.fetchone()
        if not order:
            return {"error": f"Order {order_ref} not found"}

        old_status = order["status"]
        cur.execute("UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s", (status, order["id"]))
        conn.commit()
        return {
            "success":    True,
            "order_ref":  order_ref,
            "customer":   order["customer_name"],
            "old_status": old_status,
            "new_status": status,
            "reason":     reason,
        }
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()
