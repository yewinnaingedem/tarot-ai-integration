from .base_model import Model

class Order(Model):
    table = "orders"

    @classmethod
    def pending(cls):
        return cls.where("status", "pending")

    @classmethod
    def completed(cls):
        return cls.where("status", "completed")
    