# mcp_app/mcp_tools/coupon.py
from ..core import mcp
from ..models.coupon_model import Coupon
from ..permission import can
from datetime import datetime
import json


def format_coupon(c: dict) -> dict:
    now      = datetime.now()
    end_date = c.get("end_date")
    expired  = end_date < now if end_date else False
    used     = int(c.get("used_times") or 0)
    avail    = int(c.get("available_times") or 0)

    return {
        "id":             c.get("id"),
        "code":           c.get("code"),
        "type":           c.get("coupon_type"),
        "amount":         c.get("amount"),
        "display_amount": (
            f"{int(c.get('amount') or 0)}%"
            if c.get("coupon_type") == "percentage"
            else f"{int(c.get('amount') or 0):,} MMK"
        ),
        "category":       c.get("category_name") or "All Categories",
        "category_id":    c.get("category_id"),
        "usage": {
            "used":      used,
            "available": avail,
            "remaining": max(0, avail - used),
            "fully_used": used >= avail if avail > 0 else False,
        },
        "period": {
            "start": c.get("start_date").strftime("%Y-%m-%d") if c.get("start_date") else None,
            "end":   end_date.strftime("%Y-%m-%d")            if end_date              else None,
        },
        "active":      bool(c.get("active")),
        "expired":     expired,
        "status": (
            "✅ Active"   if bool(c.get("active")) and not expired and used < avail else
            "⏰ Expired"  if expired                                                  else
            "🚫 Used Up"  if used >= avail and avail > 0                              else
            "❌ Inactive"
        ),
        "with_discount": bool(c.get("with_discount")),
        "created_by":    c.get("created_by"),
        "created_at":    c.get("created_at").strftime("%Y-%m-%d %H:%M") if c.get("created_at") else None,
    }


# ── Tool 1: Get all coupons ───────────────────────────────────
@mcp.tool()
def get_coupons(active_only: bool = False) -> dict:
    """
    Get all coupons.
    active_only: true = only show active non-expired coupons
    """
    # if not can("admin.access.coupon"):
    #     return {"message": "You don't have permission to view coupons"}

    try:
        coupons   = Coupon.all_with_relations(active_only=active_only)
        formatted = [format_coupon(c) for c in coupons]
        stats     = Coupon.get_usage_stats()

        return {
            "total":    len(formatted),
            "stats": {
                "total":       int(stats.get("total")           or 0),
                "active":      int(stats.get("active")          or 0),
                "inactive":    int(stats.get("inactive")        or 0),
                "expired":     int(stats.get("expired")         or 0),
                "fully_used":  int(stats.get("fully_used")      or 0),
                "total_used":  int(stats.get("total_used_times") or 0),
            },
            "coupons": formatted,
        }
    except Exception as e:
        return {"error": str(e)}


# ── Tool 2: Get single coupon ─────────────────────────────────
@mcp.tool()
def get_coupon(coupon_id: int) -> dict:
    """Get a single coupon by ID."""
    # if not can("admin.access.coupon"):
    #     return {"message": "You don't have permission"}

    try:
        coupon = Coupon.find_with_relations(coupon_id)
        if not coupon:
            return {"message": f"Coupon {coupon_id} not found"}
        return {"coupon": format_coupon(coupon)}
    except Exception as e:
        return {"error": str(e)}


# ── Tool 3: Find coupon by code ───────────────────────────────
@mcp.tool()
def find_coupon_by_code(code: str) -> dict:
    """Find a coupon by its code. Useful to check if a coupon is valid."""
    # if not can("admin.access.coupon"):
    #     return {"message": "You don't have permission"}

    try:
        coupon = Coupon.find_by_code(code)
        if not coupon:
            return {"message": f"Coupon code '{code}' not found"}
        return {"coupon": format_coupon(coupon)}
    except Exception as e:
        return {"error": str(e)}


# ── Tool 4: Create coupon ─────────────────────────────────────
@mcp.tool()
def create_coupon(
    coupon_type:     str,
    amount:          float,
    available_times: int,
    start_date:      str,
    end_date:        str,
    category_id:     int        = None,
    package_ids:     list[int]  = None,   # ← add package_ids
    with_discount:   bool       = False,
    active:          bool       = True,
) -> dict:
    """
    Create coupon. WORKFLOW:
    1. Call get_categories first to get category_id
    2. Call get_packages_by_category if specific packages needed
    3. Call create_coupon with correct IDs

    Args:
        coupon_type:     percentage or amount
        amount:          discount value
        available_times: max uses
        start_date:      YYYY-MM-DD
        end_date:        YYYY-MM-DD
        category_id:     from get_categories
        package_ids:     list of package IDs from get_packages_by_category
        with_discount:   stack with discounts
        active:          activate immediately
    """
    # if not can("admin.access.coupon.create"):
    #     return {"message": "You don't have permission to create coupons"}

    if coupon_type not in ("percentage", "amount"):
        return {"error": "coupon_type must be 'percentage' or 'amount'"}

    if coupon_type == "percentage" and (amount <= 0 or amount > 100):
        return {"error": "Percentage must be between 1 and 100"}

    # ── Validate dates ────────────────────────────────────────
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end   = datetime.strptime(end_date,   "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    if end < start:
        return {"error": f"end_date must be after start_date"}

    if end < datetime.now():
        return {"error": f"end_date is in the past"}

    # ── Check date overlap ────────────────────────────────────
    overlapping = Coupon.check_date_overlap(
        start_date  = start_date,
        end_date    = end_date,
        category_id = category_id,
    )

    if overlapping:
        conflicts = [{
            "id":       o["id"],
            "code":     o["code"],
            "amount":   f"{int(o['amount'])}%" if o["coupon_type"] == "percentage" else f"{int(o['amount']):,} MMK",
            "period":   f"{o['start_date'].strftime('%Y-%m-%d')} → {o['end_date'].strftime('%Y-%m-%d')}",
            "category": o["category_name"] or "All Categories",
        } for o in overlapping]

        return {
            "error":      "Date overlap detected",
            "message":    f"Cannot create — {len(conflicts)} existing coupon(s) overlap this period.",
            "conflicts":  conflicts,
            "suggestion": f"Deactivate coupon {conflicts[0]['id']} ({conflicts[0]['code']}) first.",
        }

    # ── Create coupon ─────────────────────────────────────────
    try:
        code = Coupon.generate_code()
        while Coupon.find_by_code(code):
            code = Coupon.generate_code()

        from ..permission import get_current_user
        import json
        now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = get_current_user()

        coupon = Coupon.create({
            "code":            code,
            "coupon_type":     coupon_type,
            "amount":          amount,
            "available_times": available_times,
            "used_times":      0,
            "package_id":      json.dumps(package_ids) if package_ids else json.dumps([]),
            "category_id":     category_id,
            "start_date":      start_date + " 00:00:00",
            "end_date":        end_date   + " 23:59:59",
            "active":          1 if active        else 0,
            "created_user":    1,
            "updated_user":    1,
            "created_at":      now,
            "updated_at":      now,
        })

        # Build confirmation message
        scope = "All categories"
        if category_id and package_ids:
            scope = f"Category {category_id} — {len(package_ids)} specific packages"
        elif category_id:
            scope = f"Category {category_id} — all packages"

        return {
            "success": True,
            "message": f"✅ Coupon created!",
            "code":    code,
            "scope":   scope,
            "coupon":  format_coupon(Coupon.find_with_relations(coupon["id"])),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Tool 5: Update coupon ─────────────────────────────────────
@mcp.tool()
def update_coupon(
    coupon_id:       int,
    available_times: int   = None,
    start_date:      str   = None,
    end_date:        str   = None,
    active:          bool  = None,
    with_discount:   bool  = None,
    amount:          float = None,
) -> dict:
    """Update a coupon. Only provide fields you want to change."""
    # if not can("admin.access.coupon.edit"):
    #     return {"message": "You don't have permission to edit coupons"}

    try:
        coupon = Coupon.find(coupon_id)
        if not coupon:
            return {"message": f"Coupon {coupon_id} not found"}
        # ── If dates are being changed — check overlap ────────
        if start_date or end_date:
            new_start = start_date or coupon["start_date"].strftime("%Y-%m-%d")
            new_end   = end_date   or coupon["end_date"].strftime("%Y-%m-%d")

            # Validate date logic
            try:
                s = datetime.strptime(new_start, "%Y-%m-%d")
                e = datetime.strptime(new_end,   "%Y-%m-%d")
            except ValueError:
                return {"error": "Invalid date format. Use YYYY-MM-DD"}

            if e < s:
                return {"error": f"end_date ({new_end}) must be after start_date ({new_start})"}

            # Check overlap — exclude current coupon
            overlapping = Coupon.check_date_overlap(
                start_date  = new_start,
                end_date    = new_end,
                category_id = coupon.get("category_id"),
                exclude_id  = coupon_id,   # ← exclude self
            )

            if overlapping:
                conflicts = [{
                    "id":     o["id"],
                    "code":   o["code"],
                    "period": f"{o['start_date'].strftime('%Y-%m-%d')} → {o['end_date'].strftime('%Y-%m-%d')}",
                } for o in overlapping]

                return {
                    "error":     "Date overlap detected",
                    "message":   f"Cannot update — overlaps with {len(conflicts)} existing coupon(s)",
                    "conflicts": conflicts,
                }

        # ── Build update data ─────────────────────────────────
        from ..permission import get_current_user
        data = {
            "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_user": get_current_user(),
        }

        if available_times is not None: data["available_times"] = available_times
        if amount          is not None: data["amount"]          = amount
        if active          is not None: data["active"]          = 1 if active else 0
        if with_discount   is not None: data["with_discount"]   = 1 if with_discount else 0
        if start_date      is not None: data["start_date"]      = start_date + " 00:00:00"
        if end_date        is not None: data["end_date"]         = end_date   + " 23:59:59"

        Coupon.update(coupon_id, data)

        return {
            "success": True,
            "message": "Coupon updated successfully",
            "coupon":  format_coupon(Coupon.find_with_relations(coupon_id)),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}



# ── Tool 6: Deactivate coupon ─────────────────────────────────
@mcp.tool()
def deactivate_coupon(coupon_id: int) -> dict:
    """Deactivate a coupon so it can no longer be used."""
    # if not can("admin.access.coupon.edit"):
    #     return {"message": "You don't have permission"}

    try:
        coupon = Coupon.find(coupon_id)
        if not coupon:
            return {"message": f"Coupon {coupon_id} not found"}

        Coupon.update(coupon_id, {
            "active":     0,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        return {
            "success": True,
            "message": f"Coupon '{coupon.get('code')}' deactivated",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 7: Get expiring soon ─────────────────────────────────
@mcp.tool()
def get_expiring_coupons(days: int = 7) -> dict:
    """
    Get coupons expiring soon.
    days: how many days ahead to check (default 7)
    """
    # if not can("admin.access.coupon"):
    #     return {"message": "You don't have permission"}

    try:
        coupons   = Coupon.get_expiring_soon(days)
        formatted = [format_coupon(c) for c in coupons]

        return {
            "days_ahead": days,
            "total":      len(formatted),
            "message":    f"{len(formatted)} coupons expiring in next {days} days",
            "coupons":    formatted,
        }
    except Exception as e:
        return {"error": str(e)}