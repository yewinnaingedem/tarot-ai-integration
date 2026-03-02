from mcp_app.db import get_connection

class Model:
    table = ""  

    @classmethod
    def all(cls):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {cls.table}")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    @classmethod
    def find(cls, id: int):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {cls.table} WHERE id = %s", (id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row

    @classmethod
    def where(cls, column: str, value):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {cls.table} WHERE {column} = %s", (value,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    @classmethod
    def create(cls, data: dict):
        conn = get_connection()
        cursor = conn.cursor()
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        cursor.execute(
            f"INSERT INTO {cls.table} ({columns}) VALUES ({placeholders})",
            list(data.values())
        )
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return cls.find(new_id)

    @classmethod
    def update(cls, id: int, data: dict):
        conn = get_connection()
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        cursor.execute(
            f"UPDATE {cls.table} SET {set_clause} WHERE id = %s",
            [*data.values(), id]
        )
        conn.commit()
        cursor.close()
        conn.close()
        return cls.find(id)

    @classmethod
    def delete(cls, id: int):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {cls.table} WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        return True

    @classmethod
    def latest(cls, limit: int = 1):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {cls.table} ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows[0] if limit == 1 else rows
    
    @classmethod
    def belongs_to(cls, related_model, foreign_key_value: int):
        """Get parent record by foreign key value"""
        return related_model.find(foreign_key_value)

    @classmethod
    def has_many(cls, related_model, foreign_key: str, id: int):
        """Get child records — e.g. category.has_many(Order, 'category_id', category_id)"""
        return related_model.where(foreign_key, id)
    
    @classmethod
    def where_like(cls, column: str, value):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {cls.table} WHERE {column} LIKE %s", (f"{value}%",))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    
    @classmethod
    def join_query(cls, sql, params=None):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows