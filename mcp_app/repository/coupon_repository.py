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
        """
        Insert a new category and return the created record.

        Args:
            name:        Category display name (must be unique).
            description: Optional description text.

        Returns:
            Formatted dict of the newly created category.
        """
        row = Category.create({"name": name, "description": description})
        return CategoryRepository._format(row)

    @staticmethod
    def update(category_id: int, data: dict) -> dict | None:
        """
        Update an existing category by ID.

        Args:
            category_id: Primary key of the category to update.
            data:        Dict of columns to update, e.g. {"name": "New Name"}.

        Returns:
            Formatted dict of the updated category, or None if not found.
        """
        existing = Category.find(category_id)
        if not existing:
            return None
        row = Category.update(category_id, data)
        return CategoryRepository._format(row)

    @staticmethod
    def delete(category_id: int) -> bool:
        """
        Delete a category by ID.

        Returns:
            True if deleted, False if category did not exist.
        """
        existing = Category.find(category_id)
        if not existing:
            return False
        return Category.delete(category_id)

    # ─────────────────────────────────────────────
    # Private formatter
    # ─────────────────────────────────────────────

    @staticmethod
    def _format(row: dict) -> dict:
        """
        Normalize a raw DB row into a clean, consistent response shape.
        Add or remove fields here to control what the MCP tool exposes.
        """
        return {
            "id":          row.get("id"),
            "name":        row.get("name", ""),
            "description": row.get("description", ""),
            "created_at":  str(row.get("created_at", "")),
            "updated_at":  str(row.get("updated_at", "")),
        }