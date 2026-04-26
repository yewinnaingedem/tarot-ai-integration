from mcp_app.models.category_model import Category


class CategoryRepository:

    # ─────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────

    @staticmethod
    def get_all() -> list[dict]:
        """
        Fetch every category row.

        Returns:
            [
                {"id": 1, "name": "Tarot Reading", "description": "...", ...},
                ...
            ]
        """
        rows = Category.all()
        return [CategoryRepository._format(row) for row in rows]

    @staticmethod
    def get_by_id(category_id: int) -> dict | None:
        """
        Fetch a single category by primary key.

        Returns formatted dict, or None if not found.
        """
        row = Category.find(category_id)
        if not row:
            return None
        return CategoryRepository._format(row)

    @staticmethod
    def get_by_name(name: str) -> list[dict]:
        """
        Fetch categories whose name starts with `name` (case-insensitive prefix search).

        Useful for resolving user input like "Tarot" → category_id.
        """
        rows = Category.where_like("name", name)
        return [CategoryRepository._format(row) for row in rows]

    # ─────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────

    @staticmethod
    def create(name: str, description: str = "") -> dict:
        row = Category.create({"name": name, "description": description})
        return CategoryRepository._format(row)

    @staticmethod
    def update(category_id: int, data: dict) -> dict | None:
        existing = Category.find(category_id)
        if not existing:
            return None
        row = Category.update(category_id, data)
        return CategoryRepository._format(row)

    @staticmethod
    def delete(category_id: int) -> bool:
        existing = Category.find(category_id)
        if not existing:
            return False
        return Category.delete(category_id)

    @staticmethod
    def _format(row: dict) -> dict:
        return {
            "id":          row.get("id"),
            "name":        row.get("name", ""),
            "description": row.get("description", ""),
            "created_at":  str(row.get("created_at", "")),
            "updated_at":  str(row.get("updated_at", "")),
        }