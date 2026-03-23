from .base_model import Model

class Category(Model):
    table = "category"

    @classmethod
    def orders(cls, category_id: int):
        """Get all orders in this category — hasMany"""
        from .order_model import Order
        return cls.has_many(Order, "package_id", category_id)
    
    @classmethod
    def get_categories (cls ) : 
        return cls.all() 

    @classmethod 
    def  get_category (cls , category_id) :
        return cls.find(category_id)
