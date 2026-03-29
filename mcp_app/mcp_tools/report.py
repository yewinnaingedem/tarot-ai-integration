"""
mcp_app/mcp_tools/report.py

Generate CSV reports that the AI can send to the frontend for download.
"""

import csv, io, base64
from datetime import datetime, timedelta
from ..core import mcp
from ..db import get_connection
from ..permission import can

_DENY = {"message": "You don't have permission to generate reports."}


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


def _query(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return [_clean_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _to_csv_base64(headers, rows):
    buf = io.StringIO()
    buf.write('\ufeff')  # BOM for Excel Myanmar text support
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    b64 = base64.b64encode(buf.getvalue().encode('utf-8-sig')).decode()
    return b64


@mcp.tool()
def generate_order_report(report_type: str = "all_orders", start_date: str = None, end_date: str = None) -> dict:
    """
    Generate a downloadable CSV report.

    ⚠️ Use when admin asks:
    - generate report / export report / download report
    - CSV report / Excel report
    - export orders / export sales
    - report ထုတ်ပေး / report လုပ်ပေး

    Args:
        report_type: One of: all_orders, today_orders, unreplied_orders, revenue_summary, package_performance, age_gender_analysis
        start_date: Start date YYYY-MM-DD (default: last 30 days)
        end_date: End date YYYY-MM-DD (default: today)
    """
    if not can('admin.access.order'):
        return _DENY

    now = datetime.now()
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    filename = f"{report_type}_{start_date}_to_{end_date}.csv"

    if report_type == "today_orders":
        today = now.strftime("%Y-%m-%d")
        return _report_orders(today, today, f"today_orders_{today}.csv")
    elif report_type == "unreplied_orders":
        return _report_unreplied(filename)
    elif report_type == "revenue_summary":
        return _report_revenue(start_date, end_date, filename)
    elif report_type == "package_performance":
        return _report_packages(start_date, end_date, filename)
    elif report_type == "age_gender_analysis":
        return _report_age_gender(start_date, end_date, filename)
    else:
        return _report_orders(start_date, end_date, filename)


def _report_orders(start, end, filename):
    rows = _query("""
        SELECT o.order_ref, o.customer_name, o.customer_phone,
               o.customer_gender, o.date_of_birth,
               o.status, o.payment_complete, o.total_amount,
               p.name AS package_name, c.name AS category_name,
               o.remark, o.created_at
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE DATE(o.created_at) BETWEEN %s AND %s
          AND o.deleted_at IS NULL
        ORDER BY o.created_at DESC
    """, (start, end))

    headers = ["Order Ref", "Customer", "Phone", "Gender", "Date of Birth",
               "Status", "Paid", "Amount (MMK)", "Package", "Category", "Remark", "Date"]
    data = [
        [r["order_ref"], r["customer_name"], r["customer_phone"],
         r["customer_gender"] or "", r["date_of_birth"] or "",
         r["status"], "Yes" if r["payment_complete"] else "No",
         r["total_amount"], r["package_name"], r["category_name"],
         (r["remark"] or "")[:100], str(r["created_at"])]
        for r in rows
    ]
    total_amt = sum(r["total_amount"] or 0 for r in rows)
    data.append(["", "", "", "", "", "", f"Total: {len(data)} orders", total_amt, "", "", "", ""])

    return {
        "type": "csv_download",
        "filename": filename,
        "data": _to_csv_base64(headers, data),
        "row_count": len(data) - 1,
        "summary": f"Order report: {len(data) - 1} orders from {start} to {end}, total {total_amt:,.0f} MMK",
    }


def _report_unreplied(filename):
    rows = _query("""
        SELECT o.order_ref, o.customer_name, o.customer_phone,
               o.customer_gender, o.date_of_birth,
               o.total_amount, o.remark, o.created_at, o.payment_received_date,
               p.name AS package_name, c.name AS category_name,
               TIMESTAMPDIFF(HOUR, o.created_at, NOW()) AS hours_waiting
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
        WHERE o.payment_complete = 1 AND o.deleted_at IS NULL AND r.id IS NULL
        ORDER BY o.created_at ASC
    """)

    headers = ["Order Ref", "Customer", "Phone", "Gender", "Date of Birth",
               "Package", "Category", "Amount (MMK)", "Question",
               "Ordered At", "Paid At", "Hours Waiting", "Urgency"]
    data = [
        [r["order_ref"], r["customer_name"], r["customer_phone"],
         r["customer_gender"] or "", r["date_of_birth"] or "",
         r["package_name"], r["category_name"], r["total_amount"],
         (r["remark"] or "")[:100], str(r["created_at"]),
         str(r["payment_received_date"]) if r["payment_received_date"] else "",
         r["hours_waiting"],
         "CRITICAL" if r["hours_waiting"] > 72 else "URGENT" if r["hours_waiting"] > 48 else "Follow up"]
        for r in rows
    ]
    total_amt = sum(r["total_amount"] or 0 for r in rows)
    data.append(["", "", "", "", "", "", f"Total: {len(data)} orders", total_amt, "", "", "", "", ""])

    return {
        "type": "csv_download",
        "filename": f"unreplied_orders_{datetime.now().strftime('%Y-%m-%d')}.csv",
        "data": _to_csv_base64(headers, data),
        "row_count": len(data) - 1,
        "summary": f"Unreplied paid orders: {len(data) - 1} orders, total {total_amt:,.0f} MMK waiting",
    }


def _report_revenue(start, end, filename):
    rows = _query("""
        SELECT DATE(o.created_at) AS date,
               COUNT(*) AS total_orders,
               SUM(CASE WHEN o.payment_complete = 1 THEN 1 ELSE 0 END) AS paid_orders,
               SUM(CASE WHEN o.payment_complete = 1 THEN o.total_amount ELSE 0 END) AS revenue
        FROM orders o
        WHERE DATE(o.created_at) BETWEEN %s AND %s AND o.deleted_at IS NULL
        GROUP BY DATE(o.created_at)
        ORDER BY date DESC
    """, (start, end))

    headers = ["Date", "Total Orders", "Paid Orders", "Revenue (MMK)"]
    data = [[str(r["date"]), r["total_orders"], r["paid_orders"], r["revenue"]] for r in rows]
    total_orders = sum(r["total_orders"] for r in rows)
    total_revenue = sum(r["revenue"] or 0 for r in rows)
    data.append([f"Total: {len(data)} days", total_orders, "", total_revenue])

    return {
        "type": "csv_download",
        "filename": filename,
        "data": _to_csv_base64(headers, data),
        "row_count": len(data) - 1,
        "summary": f"Revenue report: {len(data) - 1} days from {start} to {end}, total {total_revenue:,.0f} MMK",
    }


def _report_packages(start, end, filename):
    rows = _query("""
        SELECT p.name AS package_name, c.name AS category_name,
               COUNT(*) AS total_orders,
               SUM(CASE WHEN o.payment_complete = 1 THEN 1 ELSE 0 END) AS paid,
               SUM(CASE WHEN o.payment_complete = 1 THEN o.total_amount ELSE 0 END) AS revenue
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE DATE(o.created_at) BETWEEN %s AND %s AND o.deleted_at IS NULL
        GROUP BY o.package_id
        ORDER BY revenue DESC
    """, (start, end))

    headers = ["Package", "Category", "Total Orders", "Paid Orders", "Revenue (MMK)"]
    data = [[r["package_name"], r["category_name"], r["total_orders"], r["paid"], r["revenue"]] for r in rows]
    total_orders = sum(r["total_orders"] for r in rows)
    total_revenue = sum(r["revenue"] or 0 for r in rows)
    data.append([f"Total: {len(data)} packages", "", total_orders, "", total_revenue])

    return {
        "type": "csv_download",
        "filename": filename,
        "data": _to_csv_base64(headers, data),
        "row_count": len(data) - 1,
        "summary": f"Package performance: {len(data) - 1} packages from {start} to {end}, total {total_revenue:,.0f} MMK",
    }


def _report_age_gender(start, end, filename):
    rows = _query("""
        SELECT o.customer_name, o.customer_phone, o.customer_gender,
               o.date_of_birth, o.total_amount,
               p.name AS package_name, c.name AS category_name,
               o.created_at
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE DATE(o.created_at) BETWEEN %s AND %s
          AND o.deleted_at IS NULL AND o.payment_complete = 1
        ORDER BY o.created_at DESC
    """, (start, end))

    from datetime import date as dt_date
    headers = ["Customer", "Phone", "Gender", "Date of Birth", "Age",
               "Age Group", "Package", "Category", "Amount (MMK)", "Date"]
    data = []
    age_groups = {}
    gender_counts = {}
    for r in rows:
        age = ""
        group = "Unknown"
        if r["date_of_birth"]:
            try:
                parts = r["date_of_birth"].split("-")
                dob = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                age = (dt_date.today() - dob).days // 365
                if age < 18:     group = "Under 18"
                elif age <= 24:  group = "18-24"
                elif age <= 34:  group = "25-34"
                elif age <= 44:  group = "35-44"
                elif age <= 54:  group = "45-54"
                else:            group = "55+"
            except (ValueError, IndexError):
                pass
        gender = r["customer_gender"] or "Unknown"
        age_groups[group] = age_groups.get(group, 0) + 1
        gender_counts[gender] = gender_counts.get(gender, 0) + 1
        data.append([
            r["customer_name"], r["customer_phone"], gender,
            r["date_of_birth"] or "", age, group,
            r["package_name"], r["category_name"],
            r["total_amount"], str(r["created_at"])
        ])

    total_amt = sum(r["total_amount"] or 0 for r in rows)
    data.append(["", "", "", "", "", f"Total: {len(data)} orders", "", "", total_amt, ""])
    # Add summary rows
    data.append([])
    data.append(["=== Age Group Summary ===", "", "", "", "", "", "", "", "", ""])
    for grp in ["Under 18", "18-24", "25-34", "35-44", "45-54", "55+", "Unknown"]:
        if grp in age_groups:
            data.append([grp, age_groups[grp], "", "", "", "", "", "", "", ""])
    data.append([])
    data.append(["=== Gender Summary ===", "", "", "", "", "", "", "", "", ""])
    for g, cnt in sorted(gender_counts.items(), key=lambda x: -x[1]):
        data.append([g, cnt, "", "", "", "", "", "", "", ""])

    return {
        "type": "csv_download",
        "filename": filename,
        "data": _to_csv_base64(headers, data),
        "row_count": len(rows),
        "summary": f"Age & Gender analysis: {len(rows)} paid orders from {start} to {end}, total {total_amt:,.0f} MMK. Gender: {gender_counts}. Age groups: {age_groups}",
    }


@mcp.tool()
def get_customer_demographics(start_date: str = None, end_date: str = None) -> dict:
    """
    Analyze customer age groups and gender distribution from paid orders.

    ⚠️ Use when admin asks:
    - age analysis / age group / demographics
    - gender analysis / male female ratio
    - customer profile / who are our customers
    - အသက်အရွယ် / ကျား/မ ခွဲခြမ်းစိတ်ဖြာ

    Args:
        start_date: Start date YYYY-MM-DD (default: last 30 days)
        end_date: End date YYYY-MM-DD (default: today)
    """
    if not can('admin.access.order'):
        return {"message": "You don't have permission."}

    now = datetime.now()
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    rows = _query("""
        SELECT o.customer_gender, o.date_of_birth, o.total_amount,
               c.name AS category_name
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
        WHERE DATE(o.created_at) BETWEEN %s AND %s
          AND o.deleted_at IS NULL AND o.payment_complete = 1
    """, (start_date, end_date))

    from datetime import date as dt_date
    gender_stats = {}
    age_groups = {}
    category_by_gender = {}
    total_amt = 0

    for r in rows:
        gender = r["customer_gender"] or "Unknown"
        amt = r["total_amount"] or 0
        total_amt += amt
        cat = r["category_name"] or "Unknown"

        gender_stats.setdefault(gender, {"count": 0, "revenue": 0})
        gender_stats[gender]["count"] += 1
        gender_stats[gender]["revenue"] += amt

        category_by_gender.setdefault(gender, {})
        category_by_gender[gender][cat] = category_by_gender[gender].get(cat, 0) + 1

        group = "Unknown"
        if r["date_of_birth"]:
            try:
                parts = r["date_of_birth"].split("-")
                dob = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                age = (dt_date.today() - dob).days // 365
                if age < 18:     group = "Under 18"
                elif age <= 24:  group = "18-24"
                elif age <= 34:  group = "25-34"
                elif age <= 44:  group = "35-44"
                elif age <= 54:  group = "45-54"
                else:            group = "55+"
            except (ValueError, IndexError):
                pass
        age_groups.setdefault(group, {"count": 0, "revenue": 0})
        age_groups[group]["count"] += 1
        age_groups[group]["revenue"] += amt

    # Top category per gender
    top_cats = {}
    for g, cats in category_by_gender.items():
        top_cats[g] = max(cats, key=cats.get) if cats else "N/A"

    return {
        "period": f"{start_date} to {end_date}",
        "total_paid_orders": len(rows),
        "total_revenue": f"{total_amt:,.0f} MMK",
        "gender_breakdown": {g: {"count": s["count"], "revenue": f"{s['revenue']:,.0f} MMK"} for g, s in gender_stats.items()},
        "age_group_breakdown": {g: {"count": s["count"], "revenue": f"{s['revenue']:,.0f} MMK"} for g, s in sorted(age_groups.items())},
        "top_category_by_gender": top_cats,
    }
