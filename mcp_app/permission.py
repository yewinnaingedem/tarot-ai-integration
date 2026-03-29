# mcp_app/permission.py
from mcp_app.db import get_connection

MODEL_TYPE = "App\\Domains\\Auth\\Models\\User"

# ── Session store — keyed by user_id ─────────────────────────
_sessions: dict = {}
_current_user_id: int = 0

def set_current_user(user_id: int):
    global _current_user_id
    _current_user_id = user_id

def get_current_user() -> int:
    return _current_user_id

def clear_current_user():
    global _current_user_id
    _current_user_id = 0

# ── can() — no args needed, uses current user ─────────────────
def can(permission: str) -> bool:
    user_id = _current_user_id
    if not user_id:
        return False
    return _check_permission(user_id, permission)

def has_role(role: str) -> bool:
    user_id = _current_user_id
    if not user_id:
        return False
    return _check_role(user_id, role)

def is_admin() -> bool:
    return _check_role(_current_user_id, "Administrator")

# ── DB queries ────────────────────────────────────────────────
def _check_permission(user_id: int, permission: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Administrator has all permissions
        cur.execute("""
            SELECT COUNT(*) FROM model_has_roles mhr
            INNER JOIN roles r ON r.id = mhr.role_id
            WHERE mhr.model_id   = %s
              AND mhr.model_type = %s
              AND r.name         = 'Administrator'
        """, (user_id, MODEL_TYPE))
        if cur.fetchone()[0]:
            return True

        # Build list: exact permission + all parent prefixes
        # e.g. "admin.access.order.view" → also check "admin.access.order"
        perms_to_check = [permission]
        parts = permission.rsplit(".", 1)
        while len(parts) == 2:
            perms_to_check.append(parts[0])
            parts = parts[0].rsplit(".", 1)

        placeholders = ",".join(["%s"] * len(perms_to_check))

        # Via role
        cur.execute(f"""
            SELECT COUNT(*)
            FROM permissions p
            INNER JOIN role_has_permissions rhp ON rhp.permission_id = p.id
            INNER JOIN model_has_roles mhr      ON mhr.role_id       = rhp.role_id
            WHERE mhr.model_id   = %s
              AND mhr.model_type = %s
              AND p.name IN ({placeholders})
        """, (user_id, MODEL_TYPE, *perms_to_check))
        if cur.fetchone()[0]:
            return True

        # Direct
        cur.execute(f"""
            SELECT COUNT(*)
            FROM permissions p
            INNER JOIN model_has_permissions mhp ON mhp.permission_id = p.id
            WHERE mhp.model_id   = %s
              AND mhp.model_type = %s
              AND p.name IN ({placeholders})
        """, (user_id, MODEL_TYPE, *perms_to_check))
        return bool(cur.fetchone()[0])

    finally:
        conn.close()

def _check_role(user_id: int, role: str) -> bool:
    if not user_id:
        return False
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM model_has_roles mhr
            INNER JOIN roles r ON r.id = mhr.role_id
            WHERE mhr.model_id   = %s
              AND mhr.model_type = %s
              AND r.name         = %s
        """, (user_id, MODEL_TYPE, role))
        return bool(cur.fetchone()[0])
    finally:
        conn.close()

def get_user_info() -> dict:
    """Get current user info from DB"""
    if not _current_user_id:
        return {}
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT u.name, u.email, r.name as role
            FROM users u
            LEFT JOIN model_has_roles mhr ON mhr.model_id = u.id
                AND mhr.model_type = %s
            LEFT JOIN roles r ON r.id = mhr.role_id
            WHERE u.id = %s
            LIMIT 1
        """, (MODEL_TYPE, _current_user_id))
        return cur.fetchone() or {}
    finally:
        conn.close()
