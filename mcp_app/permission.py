# mcp_app/permission.py
from contextvars import ContextVar
from mcp_app.db import get_connection

MODEL_TYPE = "App\\Domains\\Auth\\Models\\User"

# ── Per-async-task user context (safe for concurrent connections) ──
_current_user_id: ContextVar[int] = ContextVar('current_user_id', default=0)

# ── Permission cache: { user_id: (data, expires_at) } ──
_perm_cache: dict = {}

# ── User info cache: { user_id: (data, expires_at) } ──
_user_info_cache: dict = {}

PERM_CACHE_TTL = 300  # 5 minutes

def set_current_user(user_id: int):
    _current_user_id.set(user_id)

def get_current_user() -> int:
    return _current_user_id.get()

def clear_current_user():
    _current_user_id.set(0)

def get_user_info() -> dict:
    import time
    user_id = _current_user_id.get()
    if not user_id:
        return {}
    cached, expires = _user_info_cache.get(user_id, (None, 0))
    if cached and time.time() < expires:
        return cached
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT u.name, u.email, r.name as role
            FROM users u
            LEFT JOIN model_has_roles mhr ON mhr.model_id = u.id
                AND mhr.model_type = %s
            LEFT JOIN roles r ON r.id = mhr.role_id
            WHERE u.id = %s LIMIT 1
        """, (MODEL_TYPE, user_id))
        result = cur.fetchone() or {}
        _user_info_cache[user_id] = (result, time.time() + 300)
        return result
    finally:
        conn.close()

def invalidate_permission_cache(user_id: int = None):
    """Call this if roles/permissions change. Pass user_id or None to clear all."""
    if user_id:
        _perm_cache.pop(user_id, None)
    else:
        _perm_cache.clear()

def _load_permissions(user_id: int) -> dict:
    """Load and cache permissions for a user with TTL."""
    import time
    entry = _perm_cache.get(user_id)
    if entry and time.time() < entry[1]:
        return entry[0]

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        # Get roles
        cur.execute("""
            SELECT r.id, r.name FROM roles r
            INNER JOIN model_has_roles mhr ON mhr.role_id = r.id
            WHERE mhr.model_id = %s AND mhr.model_type = %s
        """, (user_id, MODEL_TYPE))
        roles = cur.fetchall()
        role_names = [r["name"] for r in roles]
        role_ids   = [r["id"]   for r in roles]

        if "Administrator" in role_names:
            cur.execute("SELECT name FROM permissions")
            permissions = {r["name"] for r in cur.fetchall()}
        else:
            permissions = set()
            if role_ids:
                ph = ",".join(["%s"] * len(role_ids))
                cur.execute(f"""
                    SELECT DISTINCT p.name FROM permissions p
                    INNER JOIN role_has_permissions rhp ON rhp.permission_id = p.id
                    WHERE rhp.role_id IN ({ph})
                """, role_ids)
                permissions = {r["name"] for r in cur.fetchall()}

            # Direct user permissions
            cur.execute("""
                SELECT p.name FROM permissions p
                INNER JOIN model_has_permissions mhp ON mhp.permission_id = p.id
                WHERE mhp.model_id = %s AND mhp.model_type = %s
            """, (user_id, MODEL_TYPE))
            permissions |= {r["name"] for r in cur.fetchall()}

        result = {"roles": role_names, "permissions": permissions}
        _perm_cache[user_id] = (result, time.time() + PERM_CACHE_TTL)
        return result
    finally:
        conn.close()

def can(permission: str) -> bool:
    user_id = _current_user_id.get()
    if not user_id:
        return False
    data = _load_permissions(user_id)
    parts = permission
    while parts:
        if parts in data["permissions"]:
            return True
        dot = parts.rfind(".")
        if dot == -1:
            break
        parts = parts[:dot]
    return False

def has_role(role: str) -> bool:
    user_id = _current_user_id.get()
    if not user_id:
        return False
    return role in _load_permissions(user_id)["roles"]

def is_admin() -> bool:
    return has_role("Administrator")
