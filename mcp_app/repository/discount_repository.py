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
        try:
            if hasattr('amount'):
                params.amount = float(params.amount)
            if hasattr(params, 'category_id') and params.category_id is not None:
                if str(params.category_id).lower() in ("null", "none", ""):
                    params.category_id = None
                else:
                    params.category_id = int(params.category_id)
            if hasattr(params, 'package_ids') and params.package_ids is not None:
                if isinstance(params.package_ids, str):
                    if params.package_ids.lower() in ("null", "none", "[]", ""):
                        params.package_ids = None
                    else:
                        import json as _j
                        params.package_ids = [int(x) for x in _j.loads(params.package_ids)]
        except (ValueError, TypeError) as e:
            return json.dumps({"success": False, "error": f"Type error: {e}"})

        # Validate type
        if discount_type not in ("percentage", "amount"):
            return {"success": False, "error": "discount_type must be 'percentage' or 'amount'."}

        if discount_type == "percentage" and not (0 < amount <= 100):
            return {"success": False, "error": "Percentage must be between 1 and 100."}

        if amount <= 0:
            return {"success": False, "error": "amount must be > 0."}

        # Validate dates
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date,   "%Y-%m-%d")
            if s >= e:
                return {"success": False, "error": "start_date must be before end_date."}
        except ValueError as ve:
            return {"success": False, "error": f"Invalid date format: {ve}"}

        # Resolve categories
        try:
            if category_id is None:
                categories = Category.all()
            else:
                cat = Category.find(category_id)
                if not cat:
                    return {"success": False, "error": f"Category ID {category_id} not found."}
                categories = [cat]
        except Exception as e:
            return {"success": False, "error": f"DB error fetching categories: {e}"}

        # ── Pre-check ALL categories for conflicts first ──────────
        # Collect conflicts without stopping
        all_conflicts  = []
        skipped        = []
        to_create      = []

        for cat in categories:
            cat_id   = cat["id"]
            cat_name = cat.get("name", str(cat_id))

            # Get packages
            try:
                if package_ids is not None:
                    pkg_ids = [str(p) for p in package_ids]
                else:
                    pkgs    = Package.where("category_id", cat_id)
                    pkg_ids = [str(p["id"]) for p in pkgs]
            except Exception as e:
                skipped.append({"category": cat_name, "reason": f"Package fetch failed: {e}"})
                continue

            if not pkg_ids:
                skipped.append({"category": cat_name, "reason": "No packages found"})
                continue

            # Check date overlap
            try:
                conflict = DiscountRepository._check_date_overlap(cat_id, start_date, end_date)
                if conflict:
                    all_conflicts.append({
                        "category_id":   cat_id,
                        "category_name": cat_name,
                        "conflict":      conflict,
                    })
                    continue  # ← skip this category, don't stop entire operation
            except Exception as e:
                skipped.append({"category": cat_name, "reason": f"Overlap check failed: {e}"})
                continue

            to_create.append({
                "cat_id":   cat_id,
                "cat_name": cat_name,
                "pkg_ids":  pkg_ids,
            })

        # ── Create discounts for non-conflicting categories ───────
        created = []
        failed  = []

        for item in to_create:
            payload = {
                "category_id":  item["cat_id"],
                "package_id":   json.dumps(item["pkg_ids"]),
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
                failed.append({"category": item["cat_name"], "error": str(e)})

        # ── Build result ──────────────────────────────────────────
        if not created and not all_conflicts:
            return {"success": False, "error": "No discounts created — no packages found in any category."}

        value_str = f"{amount}%" if discount_type == "percentage" else f"{amount:,.0f} MMK"
        scope     = f"category {category_id}" if category_id else "all categories"

        result = {
            "success":         len(created) > 0,
            "discount_summary": f"Applied {value_str} '{title}' to {scope} ({start_date} → {end_date}).",
            "created_count":   len(created),
            "skipped_count":   len(all_conflicts) + len(skipped),
            "discounts":       created,
        }

        # Add conflict info if any categories were skipped
        if all_conflicts:
            result["conflicts"] = [
                {
                    "category":          c["category_name"],
                    "existing_discount": c["conflict"]["title"],
                    "period":            f"{c['conflict']['start_date'][:10]} → {c['conflict']['end_date'][:10]}",
                }
                for c in all_conflicts
            ]
            result["conflict_message"] = (
                f"{len(all_conflicts)} categories skipped due to existing discounts. "
                f"{len(created)} categories created successfully."
            )

        if skipped:
            result["skipped"] = skipped

        if failed:
            result["failed"] = failed

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