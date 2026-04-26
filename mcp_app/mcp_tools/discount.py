
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from mcp_app.core import mcp
from mcp_app.repository.discount_repository import DiscountRepository
import json


# ─────────────────────────────────────────────
# Input Models
# ─────────────────────────────────────────────

class CreateDiscountInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    category_id: Optional[int] = Field(
        default=None,
        description=(
            "ID of the category to discount. "
            "⚠️ Call get_categories first to resolve a category name → ID. "
            "Pass null to apply to ALL categories (creates one discount row per category)."
        ),
    )
    package_ids: Optional[list[int]] = Field(
        default=None,
        description=(
            "Specific package IDs to discount within the category. "
            "Pass null to automatically include ALL packages in the category."
        ),
    )
    discount_type: Literal["percentage", "amount"] = Field(
        ...,
        description=(
            "Type of discount: "
            "'percentage' = reduce price by % (e.g. 20 = 20% off), "
            "'amount' = reduce by fixed MMK value (e.g. 5000 = 5,000 MMK off)."
        ),
    )
    amount: float = Field(
        ...,
        gt=0,
        description=(
            "Discount value. "
            "For percentage: 1–100. "
            "For amount: any positive MMK value (e.g. 5000)."
        ),
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "Human-readable label for this discount shown in the admin panel. "
            "Examples: '20% Off', 'Valentine Sale', '5000 MMK Off Love Reading'."
        ),
    )
    start_date: str = Field(
        ...,
        description="Discount activation date in YYYY-MM-DD format (e.g. '2025-12-01').",
    )
    end_date: str = Field(
        ...,
        description="Discount expiry date in YYYY-MM-DD format (e.g. '2025-12-31'). Must be after start_date.",
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be greater than 0.")
        return v

    @model_validator(mode="after")
    def validate_percentage_range(self) -> "CreateDiscountInput":
        if self.discount_type == "percentage" and self.amount > 100:
            raise ValueError("Percentage discount cannot exceed 100.")
        return self


class DeactivateDiscountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discount_id: int = Field(
        ...,
        gt=0,
        description="ID of the discount to deactivate. Call get_discounts first to find the ID.",
    )

# ─────────────────────────────────────────────
# Tool 3 — create_discount
# ─────────────────────────────────────────────

@mcp.tool(
    name="create_discount",
    annotations={
        "title": "Create Discount for Category or All Categories",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def create_discount(params: CreateDiscountInput) -> str:
    """
    Apply a percentage or fixed MMK discount to a tarot category or all categories.

    This tool creates one discount row per category in the discount table,
    with the associated package IDs stored as a JSON array.

    ── Recommended call order ──────────────────────────────────────────────
    1. Call get_categories      → resolve category name to category_id
    2. Call get_packages_by_category (optional) → if user wants specific packages
    3. Call create_discount     → create the discount

    ── Examples ────────────────────────────────────────────────────────────
    User: "20% off Love Reading from Dec 1 to Dec 31"
      → get_categories() to find Love Reading category_id
      → create_discount(category_id=1, discount_type="percentage", amount=20,
                        title="20% Off Love Reading",
                        start_date="2025-12-01", end_date="2025-12-31")

    User: "5000 MMK off all categories for New Year"
      → create_discount(category_id=None, discount_type="amount", amount=5000,
                        title="New Year 5000 MMK Off",
                        start_date="2026-01-01", end_date="2026-01-07")

    Args:
        params (CreateDiscountInput): Validated input containing:
            - category_id (int | None):       Target category or null for all
            - package_ids (list[int] | None): Specific packages or null for all in category
            - discount_type (str):            'percentage' or 'amount'
            - amount (float):                 Discount value (% or MMK)
            - title (str):                    Label shown in admin panel
            - start_date (str):               YYYY-MM-DD activation date
            - end_date (str):                 YYYY-MM-DD expiry date

    Returns:
        str: JSON object with:
            - success (bool)
            - discount_summary (str): Human-readable confirmation in MMK
            - created_count (int):    Number of discount rows created
            - discounts (list):       Full detail of each created discount
    """
    try:
        if hasattr(params, 'amount'):
            params.amount = float(str(params.amount).replace('%', '').replace(',', '').strip())
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
        
        result = DiscountRepository.create_discount(
            category_id=params.category_id,
            discount_type=params.discount_type,
            amount=params.amount,
            title=params.title,
            start_date=params.start_date,
            end_date=params.end_date,
            package_ids=params.package_ids,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except (ValueError, TypeError) as e:
        return json.dumps({"success": False, "error": f"Type error: {e}"})


# ─────────────────────────────────────────────
# Tool 4 — get_discounts
# ─────────────────────────────────────────────

@mcp.tool(
    name="get_discounts",
    annotations={
        "title": "Get Active Discounts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def get_discounts(category_id: Optional[int] = None, include_expired: bool = False) -> str:
    """
    Retrieve active discounts, optionally filtered by category.

    Args:
        category_id (int | None): Filter by category. Pass null to see all.
        include_expired (bool): True = include date-expired but still active=1 discounts (use for deactivation). Default False = only currently running discounts.

    Returns:
        str: JSON array of discount objects.
    """
    try:
        if category_id:
            discounts = DiscountRepository.get_by_category(category_id)
        elif include_expired:
            discounts = DiscountRepository.get_all_including_expired()
        else:
            discounts = DiscountRepository.get_all_active()
        return json.dumps(discounts, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ─────────────────────────────────────────────
# Tool 5 — deactivate_discount
# ─────────────────────────────────────────────

@mcp.tool(
    name="deactivate_discount",
    annotations={
        "title": "Deactivate a Discount",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def deactivate_discount(params: DeactivateDiscountInput) -> str:
    """
    Deactivate an existing discount by setting active=0 (soft delete, not permanent).

    ⚠️  Call get_discounts first to find the discount_id before using this tool.

    Args:
        params (DeactivateDiscountInput):
            - discount_id (int): ID of the discount to deactivate

    Returns:
        str: JSON object with success (bool) and message (str).
    """
    try:
        result = DiscountRepository.deactivate(params.discount_id)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ─────────────────────────────────────────────
# Tool 6 — get_discount_usage
# ─────────────────────────────────────────────
@mcp.tool(
    name="get_discount_usage",
    annotations={"title": "Get Discount Usage Stats", "readOnlyHint": True},
)
def get_discount_usage(discount_id: int) -> str:
    """
    Show how many orders used a specific discount and total revenue generated.
    Use when admin asks if a discount is working or how many people used it.

    Args:
        discount_id: ID from get_discounts
    """
    from mcp_app.db import get_connection
    from decimal import Decimal

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM discounts WHERE id = %s AND deleted_at IS NULL", (discount_id,))
        discount = cur.fetchone()
        if not discount:
            return json.dumps({"error": f"Discount ID {discount_id} not found"})

        cur.execute("""
            SELECT COUNT(*) AS total_orders,
                   SUM(CASE WHEN o.status='complete' THEN 1 ELSE 0 END) AS completed,
                   COALESCE(SUM(CASE WHEN o.status='complete' THEN o.total_amount END), 0) AS revenue
            FROM orders o
            WHERE o.deleted_at IS NULL
              AND o.promotion_type = 'discount'
              AND o.created_at BETWEEN %s AND %s
              AND o.package_id IN (
                  SELECT id FROM packages
                  WHERE category_id = %s AND deleted_at IS NULL
              )
        """, (discount["start_date"], discount["end_date"], discount["category_id"]))
        stats = cur.fetchone()

        amount = float(discount["amount"]) if isinstance(discount["amount"], Decimal) else discount["amount"]
        revenue = float(stats["revenue"]) if isinstance(stats["revenue"], Decimal) else (stats["revenue"] or 0)

        return json.dumps({
            "discount_id":   discount_id,
            "title":         discount["title"],
            "amount":        f"{amount}%" if discount["type"] == "percentage" else f"{amount:,.0f} MMK",
            "period":        f"{str(discount['start_date'])[:10]} → {str(discount['end_date'])[:10]}",
            "active":        bool(discount["active"]),
            "total_orders":  int(stats["total_orders"] or 0),
            "completed":     int(stats["completed"] or 0),
            "revenue":       f"{int(revenue):,} MMK",
        })
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Tool 7 — remove_package_from_discount
# ─────────────────────────────────────────────
@mcp.tool(
    name="remove_package_from_discount",
    annotations={"title": "Remove a Package from a Discount", "readOnlyHint": False, "destructiveHint": False},
)
def remove_package_from_discount(discount_id: int, package_id: int) -> str:
    """
    Remove a specific package from an existing discount without affecting other packages.
    Deactivates the old discount and recreates it with the package removed.

    Args:
        discount_id: ID of the discount (from get_discounts)
        package_id:  ID of the package to remove (from get_packages_by_category)
    """
    from mcp_app.db import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM discounts WHERE id = %s AND deleted_at IS NULL", (discount_id,))
        discount = cur.fetchone()
        if not discount:
            return json.dumps({"error": f"Discount ID {discount_id} not found"})

        raw = discount.get("package_id", "[]")
        try:
            pkg_ids = json.loads(raw) if isinstance(raw, str) else (raw or [])
            pkg_ids = [int(p) for p in pkg_ids]
        except Exception:
            pkg_ids = []

        if package_id not in pkg_ids:
            return json.dumps({"error": f"Package {package_id} is not in discount {discount_id}"})

        new_pkg_ids = [p for p in pkg_ids if p != package_id]

        if not new_pkg_ids:
            # No packages left — just deactivate
            cur.execute("UPDATE discounts SET active = 0, updated_at = NOW() WHERE id = %s", (discount_id,))
            conn.commit()
            return json.dumps({"success": True, "message": "Last package removed — discount deactivated.", "discount_id": discount_id})

        # Deactivate old, create new with remaining packages
        cur.execute("UPDATE discounts SET active = 0, updated_at = NOW() WHERE id = %s", (discount_id,))
        conn.commit()

        result = DiscountRepository.create_discount(
            category_id=discount["category_id"],
            discount_type=discount["type"],
            amount=float(discount["amount"]),
            title=discount["title"],
            start_date=str(discount["start_date"])[:10],
            end_date=str(discount["end_date"])[:10],
            package_ids=new_pkg_ids,
        )
        result["removed_package_id"] = package_id
        result["old_discount_id"] = discount_id
        return json.dumps(result, ensure_ascii=False)
    finally:
        conn.close()
