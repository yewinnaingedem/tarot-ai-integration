
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from mcp_app.core import mcp
from mcp_app.repository.discount_repository import DiscountRepository
from mcp_app.repository.category_repository import CouponRepository
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
# Tool 2 — get_packages_by_category
# ─────────────────────────────────────────────

@mcp.tool(
    name="get_packages_by_category",
    annotations={
        "title": "Get Packages for a Category",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
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
def get_discounts(category_id: Optional[int] = None) -> str:
    """
    Retrieve all currently active discounts, optionally filtered by category.

    Call this before deactivate_discount to find the correct discount_id.

    Args:
        category_id (int | None): Filter by category. Pass null to see all discounts.

    Returns:
        str: JSON array of active discount objects containing:
            - id (int):            Use this in deactivate_discount
            - category_id (int)
            - category_name (str)
            - package_ids (list):  Parsed list of package IDs
            - title (str)
            - type (str):          'percentage' or 'amount'
            - amount (float):      Discount value
            - start_date (str)
            - end_date (str)
    """
    try:
        if category_id:
            discounts = DiscountRepository.get_by_category(category_id)
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