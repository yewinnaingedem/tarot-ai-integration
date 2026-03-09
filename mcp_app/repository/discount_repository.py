import json
from datetime import datetime
from ..models.discount_model import Discount
from ..models.category_model import Category
from ..models.package_model import Package

class DiscountRepository:

    @staticmethod
    def get_all_active() -> list[dict]:
        try:
            rows = Discount.join_query("""
                SELECT d.*, c.name AS category_name
                FROM discounts d
                LEFT JOIN category c ON c.id = d.category_id
                WHERE d.deleted_at IS NULL AND d.active = 1
                ORDER BY d.created_at DESC
            """)
            return [DiscountRepository._format(row) for row in rows]
        except Exception as e:
            raise

    @staticmethod
    def get_by_category(category_id: int) -> list[dict]:
        try:
            rows = Discount.join_query("""
                SELECT d.*, c.name AS category_name
                FROM discounts d
                LEFT JOIN category c ON c.id = d.category_id
                WHERE d.category_id = %s
                  AND d.deleted_at IS NULL
                  AND d.active = 1
                ORDER BY d.created_at DESC
            """, (category_id,))
            return [DiscountRepository._format(row) for row in rows]
        except Exception as e:
            raise

    @staticmethod
    def _check_date_overlap(category_id: int, start_date: str, end_date: str) -> dict | None:
        """
        Check if an active discount already exists for this category
        that overlaps with the requested date range.

        Overlap condition:
            existing.start_date <= new.end_date
            AND existing.end_date >= new.start_date

        Returns a conflict dict if overlap found, None if clear.
        """
        try:
            conflicts = Discount.join_query("""
                SELECT d.id, d.title, d.start_date, d.end_date, d.amount, d.type
                FROM discounts d
                WHERE d.category_id = %s
                  AND d.active = 1
                  AND d.deleted_at IS NULL
                  AND d.start_date <= %s
                  AND d.end_date   >= %s
            """, (category_id, f"{end_date} 23:59:00", f"{start_date} 00:00:00"))

            if conflicts:
                c = conflicts[0]
                return {
                    "discount_id":  c["id"],
                    "title":        c["title"],
                    "start_date":   str(c["start_date"]),
                    "end_date":     str(c["end_date"]),
                    "amount":       float(c["amount"]),
                    "type":         c["type"],
                }
            return None
        except Exception as e:
            raise

    @staticmethod
    def get_available_dates(category_id: int) -> list[dict]:
        """
        Return all active discount date ranges for a category so the AI
        can suggest free date windows to the user.
        """
        try:
            rows = Discount.join_query("""
                SELECT id, title, start_date, end_date, amount, type
                FROM discounts
                WHERE category_id = %s
                  AND active = 1
                  AND deleted_at IS NULL
                ORDER BY start_date ASC
            """, (category_id,))
            return [
                {
                    "discount_id": r["id"],
                    "title":       r["title"],
                    "start_date":  str(r["start_date"]),
                    "end_date":    str(r["end_date"]),
                    "amount":      float(r["amount"]),
                    "type":        r["type"],
                }
                for r in rows
            ]
        except Exception as e:
            raise

    @staticmethod
    def create_discount(
        category_id: int | None,
        discount_type: str,
        amount: float,
        title: str,
        start_date: str,
        end_date: str,
        package_ids: list[int] | None = None,
        created_user: int = 1,
    ) -> dict:

        # Validate type
        if discount_type not in ("percentage", "amount"):
            msg = "discount_type must be 'percentage' or 'amount'."
            return {"success": False, "error": msg}

        if discount_type == "percentage" and not (0 < amount <= 100):
            msg = "Percentage must be between 1 and 100."
            return {"success": False, "error": msg}

        if amount <= 0:
            msg = "amount must be > 0."
            return {"success": False, "error": msg}

        # Validate dates
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            if s >= e:
                msg = "start_date must be before end_date."
                return {"success": False, "error": msg}
        except ValueError as ve:
            msg = f"Invalid date format: {ve}"
            return {"success": False, "error": msg}

        # Resolve categories
        try:
            if category_id is None:
                categories = Category.all()
            else:
                cat = Category.find(category_id)
                if not cat:
                    msg = f"Category ID {category_id} not found."
                    return {"success": False, "error": msg}
                categories = [cat]
        except Exception as e:
            return {"success": False, "error": f"DB error fetching categories: {e}"}

        # Insert per category
        created = []
        for cat in categories:
            cat_id = cat["id"]
            cat_name = cat.get("name", str(cat_id))

            try:
                if package_ids is not None:
                    pkg_ids = [str(p) for p in package_ids]
                else:
                    pkgs = Package.where("category_id", cat_id)
                    pkg_ids = [str(p["id"]) for p in pkgs]
            except Exception as e:
                continue

            if not pkg_ids:
                continue

            # ── Date overlap check ─────────────────────────────────────────
            try:
                conflict = DiscountRepository._check_date_overlap(cat_id, start_date, end_date)
                if conflict:
                    existing_dates = DiscountRepository.get_available_dates(cat_id)
                    booked = [
                        f"#{d['discount_id']} '{d['title']}': {d['start_date'][:10]} to {d['end_date'][:10]}"
                        for d in existing_dates
                    ]
                    return {
                        "success": False,
                        "error": "date_overlap",
                        "message": (
                            f"Category '{cat_name}' already has a discount "
                            f"(#{conflict['discount_id']} '{conflict['title']}') "
                            f"overlapping {start_date} to {end_date}. "
                            f"Please choose different dates."
                        ),
                        "conflicting_discount": conflict,
                        "all_booked_periods": booked,
                        "suggestion": (
                            "Inform the user about the conflict and ask them "
                            "to pick dates outside the booked periods listed above."
                        ),
                    }
            except Exception as e:
                return {"success": False, "error": f"Overlap check failed: {e}"}

            payload = {
                "category_id":  cat_id,
                "package_id":   json.dumps(pkg_ids),
                "title":        title,
                "type":         discount_type,
                "amount":       amount,
                "start_date":   f"{start_date} 00:00:00",
                "end_date":     f"{end_date} 23:59:00",
                "active":       1,
                "created_user": created_user,
                "updated_user": created_user,
            }

            try:
                row = Discount.create(payload)
                created.append(DiscountRepository._format(row))
            except Exception as e:
                return {
                    "success": False,
                    "error": f"DB insert failed for '{cat_name}': {e}",
                }

        if not created:
            msg = "No discounts created — no packages found."
            return {"success": False, "error": msg}

        value_str = f"{amount}%" if discount_type == "percentage" else f"{amount:,.0f} MMK"
        scope = f"category {category_id}" if category_id else "all categories"

        result = {
            "success": True,
            "discount_summary": f"Applied {value_str} '{title}' to {scope} ({start_date} → {end_date}).",
            "created_count": len(created),
            "discounts": created,
        }
        return result

    @staticmethod
    def deactivate(discount_id: int) -> dict:
        try:
            existing = Discount.find(discount_id)
            if not existing:
                msg = f"Discount ID {discount_id} not found."
                return {"success": False, "error": msg}
            Discount.update(discount_id, {"active": 0})
            return {"success": True, "message": f"Discount #{discount_id} '{existing.get('title')}' deactivated."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _format(row: dict) -> dict:
        raw_pkg = row.get("package_id", "[]")
        try:
            packages = json.loads(raw_pkg) if isinstance(raw_pkg, str) else raw_pkg
        except (json.JSONDecodeError, TypeError):
            packages = []
        return {
            "id":            row.get("id"),
            "category_id":   row.get("category_id"),
            "category_name": row.get("category_name", ""),
            "package_ids":   packages,
            "title":         row.get("title", ""),
            "type":          row.get("type", ""),
            "amount":        float(row.get("amount", 0)),
            "start_date":    str(row.get("start_date", "")),
            "end_date":      str(row.get("end_date", "")),
            "active":        bool(row.get("active", 1)),
            "created_at":    str(row.get("created_at", "")),
        }