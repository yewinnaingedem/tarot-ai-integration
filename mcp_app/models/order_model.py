from .base_model import Model

class Order(Model):
    table = "orders"

    ORDER_WITH_PACKAGE_SQL = """
        SELECT o.*, 
               p.id as package_id, p.name as package_name, p.amount as package_price,
               c.id as category_id, c.name as category_name
        FROM orders o
        LEFT JOIN packages p ON o.package_id = p.id
        LEFT JOIN category c ON p.category_id = c.id
    """

    @classmethod
    def pending(cls):
        return cls.join_query(cls.ORDER_WITH_PACKAGE_SQL + " WHERE o.status = %s", ("pending",))

    @classmethod
    def completed(cls):
        return cls.join_query(cls.ORDER_WITH_PACKAGE_SQL + " WHERE o.status = %s", ("completed",))

    @classmethod
    def get_latest_order_with_category(cls):
        rows = cls.join_query(cls.ORDER_WITH_PACKAGE_SQL + " ORDER BY o.created_at DESC LIMIT 1")
        return rows[0] if rows else None

    @classmethod
    def get_orders_by_date(cls, created_at):
        return cls.join_query(
            cls.ORDER_WITH_PACKAGE_SQL + " WHERE o.created_at LIKE %s",
            (f"{created_at}%",)
        )
    
    
    @classmethod
    def get_orders_by_date_range(cls, start_date: str, end_date: str):
        return cls.join_query(
            cls.ORDER_WITH_PACKAGE_SQL + """
            WHERE DATE(o.created_at) BETWEEN %s AND %s
            ORDER BY o.created_at DESC
            """,
            (start_date, end_date)
        )