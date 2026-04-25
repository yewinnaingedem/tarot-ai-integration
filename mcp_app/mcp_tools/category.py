from ..core import mcp
from ..models.category_model import Category
from ..repository.category_repository import CouponRepository as ctr
from ..permission import can
import json

def _fmt_dt(val):
    if not val:
        return None
    if hasattr(val, 'strftime'):
        return val.strftime("%Y-%m-%d %H:%M")
    return str(val)[:16]  # already a string, just trim to "YYYY-MM-DD HH:MM"

def format_category( category : list) -> list:
    formatted = []
    for o in category:
        formatted.append({
            "id":       o.get("id"),
            "name" : o.get("name") ,
            "mm_name" : o.get("mm_name"),
            "category_type" : o.get("category_type"),
            "created_at": _fmt_dt(o.get("created_at")),
            "updated_at": _fmt_dt(o.get("updated_at")),
        })
    return formatted


# ─────────────────────────────────────────────
# Tool 1 — get_categories
# ─────────────────────────────────────────────

@mcp.tool(
    name="get_categories",
    annotations={
        "title": "Get All Tarot Categories",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def get_categories() -> str:
    """
    Retrieve all tarot reading categories from the database.

    ⚠️  ALWAYS call this tool first whenever the user refers to a category by name
    (e.g. 'Love Reading', 'Career'). Use the returned `id` when calling create_discount.

    Returns:
        str: JSON array of categories. Each object contains:
            - id (int):            Use this as category_id in create_discount
            - name (str):          Category display name
            - mm_name (str):       Myanmar name
            - category_type (str): Category type
    """
    try:
        categories = ctr.get_all()
        return json.dumps(categories, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@mcp.tool(
    name="get_category_by_name_or_id"
)
def get_category_by_name_or_id(id: int = None, name: str = None) -> dict:
    """Get Specific category by NAME or ID"""
    # if not can("admin.access.view"):
    #     return {"message": "Current user does not have access to perform this action"}

    category = None
    if id:
        category = ctr.get_by_id(id)
    elif name:
        category = ctr.get_by_name(name)
    else:
        return {"message": "Either ID or Name must be provided"}

    if not category:
        return {"message": "Category not found"}

    # get_by_id returns a dict, get_by_name returns a list of dicts
    if isinstance(category, list):
        return {"categories": format_category(category)}
    return {"categories": format_category([category])}

@mcp.tool(
    name="create_category"
) 
def create_category(name, mm_name, slug) -> dict:
    """Create Category"""
    return ctr.create(name=name, mm_name=mm_name, slug_name=slug)
    
