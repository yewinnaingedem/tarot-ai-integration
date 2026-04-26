from mcp_app.db import get_connection
from datetime import datetime

class Model:
    table = ""

    @classmethod
    def _safe_col(cls, column: str) -> str:
        """Prevent SQL injection in dynamic column names."""
        if not column.replace("_", "").isalnum():
            raise ValueError(f"Invalid column name: {column}")
        return column

    @classmethod
    def all(cls):
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM `{cls.table}` WHERE deleted_at IS NULL")
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            conn.close()

    @classmethod
    def find(cls, id: int):
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM `{cls.table}` WHERE id = %s AND deleted_at IS NULL", (id,))
            row = cursor.fetchone()
            cursor.close()
            return row
        finally:
            conn.close()

    @classmethod
    def where(cls, column: str, value):
        col = cls._safe_col(column)
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM `{cls.table}` WHERE `{col}` = %s AND deleted_at IS NULL", (value,))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            conn.close()

    @classmethod
    def where_like(cls, column: str, value):
        col = cls._safe_col(column)
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM `{cls.table}` WHERE `{col}` LIKE %s AND deleted_at IS NULL", (f"{value}%",))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            conn.close()

    @classmethod
    def create(cls, data: dict):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            columns = ", ".join(f"`{k}`" for k in data.keys())
            placeholders = ", ".join(["%s"] * len(data))
            cursor.execute(
                f"INSERT INTO `{cls.table}` ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            new_id = cursor.lastrowid
            cursor.close()
        finally:
            conn.close()
        return cls.find(new_id)

    @classmethod
    def update(cls, id: int, data: dict):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            set_clause = ", ".join([f"`{k}` = %s" for k in data.keys()])
            updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            set_clause += ", updated_at = %s"
            cursor.execute(
                f"UPDATE `{cls.table}` SET {set_clause} WHERE id = %s",
                [*data.values(), updated_at, id]
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return cls.find(id)

    @classmethod
    def delete(cls, id: int):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(f"UPDATE `{cls.table}` SET deleted_at = %s WHERE id = %s", (deleted_at, id))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return True

    @classmethod
    def latest(cls, limit: int = 1):
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM `{cls.table}` WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cursor.fetchall()
            cursor.close()
        finally:
            conn.close()
        return rows[0] if limit == 1 else rows

    @classmethod
    def belongs_to(cls, related_model, foreign_key_value: int):
        return related_model.find(foreign_key_value)

    @classmethod
    def has_many(cls, related_model, foreign_key: str, id: int):
        return related_model.where(foreign_key, id)

    @classmethod
    def join_query(cls, sql, params=None):
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            conn.close()
