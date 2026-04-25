# mcp_app/models/coupon_model.py
from .base_model import Model
from ..db import get_connection
import json, random, string
from datetime import datetime


class Coupon(Model):
    table = "coupons"

    COUPON_WITH_RELATIONS_SQL = """
        SELECT c.*,
               cat.name  AS category_name,
               u1.name   AS created_by,
               u2.name   AS updated_by
        FROM coupons c
        LEFT JOIN category cat ON cat.id = c.category_id
        LEFT JOIN users u1     ON u1.id  = c.created_user
        LEFT JOIN users u2     ON u2.id  = c.updated_user
    """

    @classmethod
    def generate_code(cls) -> str:
        chars  = string.ascii_uppercase + string.digits
        random_part = "".join(random.choices(chars, k=5))
        code = f"PTR{random_part}"
        return code[:8].upper()

    @classmethod
    def all_with_relations(cls, active_only: bool = False) -> list:
        sql = cls.COUPON_WITH_RELATIONS_SQL + " WHERE c.deleted_at IS NULL"
        if active_only:
            sql += " AND c.active = 1 AND c.end_date >= NOW()"
        sql += " ORDER BY c.created_at DESC"
        return cls.join_query(sql)

    @classmethod
    def find_with_relations(cls, coupon_id: int) -> dict | None:
        rows = cls.join_query(
            cls.COUPON_WITH_RELATIONS_SQL +
            " WHERE c.id = %s AND c.deleted_at IS NULL LIMIT 1",
            (coupon_id,)
        )
        return rows[0] if rows else None

    @classmethod
    def find_by_code(cls, code: str) -> dict | None:
        rows = cls.join_query(
            cls.COUPON_WITH_RELATIONS_SQL +
            " WHERE c.code = %s AND c.deleted_at IS NULL LIMIT 1",
            (code.upper(),)
        )
        return rows[0] if rows else None

    @classmethod
    def get_expiring_soon(cls, days: int = 7) -> list:
        return cls.join_query(
            cls.COUPON_WITH_RELATIONS_SQL + """
            WHERE c.deleted_at IS NULL
              AND c.active      = 1
              AND c.end_date    BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s DAY)
            ORDER BY c.end_date ASC
            """,
            (days,)
        )

    @classmethod
    def get_usage_stats(cls) -> dict:
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    COUNT(*)                           AS total,
                    SUM(active = 1)                    AS active,
                    SUM(active = 0)                    AS inactive,
                    SUM(end_date < NOW())              AS expired,
                    SUM(used_times >= available_times) AS fully_used,
                    SUM(used_times)                    AS total_used_times
                FROM coupons
                WHERE deleted_at IS NULL
            """)
            return cur.fetchone() or {}
        finally:
            conn.close()

    @classmethod
    def check_date_overlap(
        cls,
        start_date:   str,
        end_date:     str,
        coupon_type:  str  = None,
        amount:       float = None,
        category_id:  int  = None,
        exclude_id:   int  = None,
    ) -> list:
        """
        Check if any existing coupon overlaps with given date range.
        Overlap condition:
            existing.start_date <= new.end_date
            AND existing.end_date >= new.start_date
        """
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)

            # Base overlap query — only block exact duplicates (same category + type + amount)
            sql = """
                SELECT c.id, c.code, c.coupon_type, c.amount,
                    c.start_date, c.end_date,
                    cat.name AS category_name
                FROM coupons c
                LEFT JOIN category cat ON cat.id = c.category_id
                WHERE c.deleted_at IS NULL
                AND c.active       = 1
                AND c.start_date  <= %s
                AND c.end_date    >= %s
                AND c.coupon_type  = %s
                AND c.amount       = %s
            """
            params = [end_date, start_date, coupon_type, amount]

            if category_id:
                sql    += " AND c.category_id = %s"
                params.append(category_id)

            if exclude_id:
                sql    += " AND c.id != %s"
                params.append(exclude_id)

            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()