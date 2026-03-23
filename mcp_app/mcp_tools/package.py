from ..core import mcp
from mcp_app.models.package_model import Package
import json

@mcp.tool()
def get_packages_by_category(category_id: int) -> str:
    """
    Retrieve all packages (sub-products) that belong to a specific category.

    Call this when the user wants to apply a discount to specific packages
    rather than all packages in a category.

    Args:
        category_id (int): Category ID from get_categories.

    Returns:
        str: JSON array of packages. Each object contains:
            - id (int):    Use this in package_ids when calling create_discount
            - name (str):  Package display name
            - price (int): Package price in MMK
    """
    try:
        rows = Package.where("category_id", category_id)
        packages = [
            {
                "id":    row.get("id"),
                "name":  row.get("name", ""),
                "price": row.get("price", 0),
            }
            for row in rows
        ]
        return json.dumps(packages, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
