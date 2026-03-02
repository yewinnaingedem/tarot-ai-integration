from ..core import mcp
from ..models.order import Order

def format_orders(orders: list) -> list:
    """Clean and format raw order data"""
    formatted = []
    for o in orders:
        formatted.append({
            "id": o.get("id"),
            "order_ref": o.get("order_ref"),
            "status": o.get("status"),
            "customer": {
                "name": o.get("customer_name"),
                "phone": o.get("customer_phone"),
                "gender": o.get("customer_gender"),
                "date_of_birth": o.get("date_of_birth"),
                "address": o.get("address"),
            },
            "payment": {
                "method": o.get("payment_method"),
                "complete": bool(o.get("payment_complete")),
                "received_date": o.get("payment_received_date").strftime("%Y-%m-%d %H:%M") if o.get("payment_received_date") else None,
            },
            "pricing": {
                "total_amount": o.get("total_amount"),
                "original_price": o.get("original_price"),
                "promotion_price": o.get("promotion_price"),
                "promotion_type": o.get("promotion_type"),
            },
            "package" : {
                "package" : o.get("package_name") ,
                "package_price" : o.get("package_price"),
                "category" : o.get('category_name')
            },
            "vendor_id": o.get("vendor_id"),
            "remark": o.get("remark"),
            "created_at": o.get("created_at").strftime("%Y-%m-%d %H:%M") if o.get("created_at") else None,
            "updated_at": o.get("updated_at").strftime("%Y-%m-%d %H:%M") if o.get("updated_at") else None,
        })
    return formatted


@mcp.tool()
def get_latest_order_from_db() -> dict: 
    """
        GET LATEST ORDER From Database
        Instructions for AI:
    """
    order = Order.get_latest_order_with_category()
    if not order :
        return {
            "message" : "Something wrong"
        }
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
        "date": created_at,
        "total_orders": len(formatted),
        "total_revenue": sum(o["pricing"]["total_amount"] for o in formatted),
        "orders": formatted
    }