# from mcp_app.models.order import Order
from mcp_app.models.category_model import Category
from mcp_app.mcp_tools.order import get_order_by_date , get_latest_order_from_db
from mcp_app.repository.coupon_repository import CategoryRepository

# print(Category.latest())
# print(Category.orders(1))
# print(Order.get_latest_order_with_category())
# print(get_order_by_date('2026-02-24'))
# print(get_latest_order_from_db())
print(CategoryRepository.get_all())