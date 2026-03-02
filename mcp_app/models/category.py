from .base_model import Model

class Category(Model):
    table = "category"

    @classmethod
    def orders(cls, category_id: int):
        """Get all orders in this category — hasMany"""
        from .order import Order
        return cls.has_many(Order, "package_id", category_id)
    