"""
mcp_app/mcp_tools/admin.py

Admin / permission management tools.
"""

from mcp_app.core import mcp
from mcp_app.db import get_connection
from mcp_app.permission import can, is_admin, invalidate_permission_cache
import json


_DENY = {"message": "You don't have permission."}


@mcp.tool()
def get_roles_and_permissions() -> str:
    """
    List all roles and their permissions in the system.

    ⚠️ Use when admin asks about:
    - what roles exist
    - what permissions does a role have
    - user access levels
    """
    if not is_admin():
        return json.dumps(_DENY)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name FROM roles ORDER BY id")
        roles = cur.fetchall()

        result = []
        for role in roles:
            cur.execute("""
                SELECT p.name FROM permissions p
                INNER JOIN role_has_permissions rhp ON rhp.permission_id = p.id
                WHERE rhp.role_id = %s ORDER BY p.name
            """, (role["id"],))
            perms = [r["name"] for r in cur.fetchall()]
            result.append({"role": role["name"], "permissions": perms, "count": len(perms)})

        return json.dumps({"roles": result, "total_roles": len(result)})
    finally:
        conn.close()


@mcp.tool()
def get_admin_users() -> str:
    """
    List all admin users and their roles.

    ⚠️ Use when admin asks about:
    - who has access to the system
    - list admin users
    - user roles
    """
    if not is_admin():
        return json.dumps(_DENY)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT u.id, u.name, u.email, u.active,
                   GROUP_CONCAT(r.name ORDER BY r.name SEPARATOR ', ') AS roles
            FROM users u
            LEFT JOIN model_has_roles mhr ON mhr.model_id = u.id
                AND mhr.model_type = 'App\\\\Domains\\\\Auth\\\\Models\\\\User'
            LEFT JOIN roles r ON r.id = mhr.role_id
            WHERE u.deleted_at IS NULL
            GROUP BY u.id, u.name, u.email, u.active
            ORDER BY u.id
        """)
        users = cur.fetchall()
        return json.dumps({
            "total": len(users),
            "users": [{"id": u["id"], "name": u["name"], "email": u["email"],
                       "active": bool(u["active"]), "roles": u["roles"] or "No role"} for u in users]
        })
    finally:
        conn.close()


@mcp.tool()
def check_user_permission(user_id: int, permission: str) -> str:
    """
    Check if a specific user has a specific permission.

    Args:
        user_id:    The user's ID
        permission: Permission name e.g. "admin.access.order"
    """
    if not is_admin():
        return json.dumps(_DENY)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        MODEL_TYPE = "App\\Domains\\Auth\\Models\\User"

        # Check admin role
        cur.execute("""
            SELECT COUNT(*) cnt FROM model_has_roles mhr
            INNER JOIN roles r ON r.id = mhr.role_id
            WHERE mhr.model_id = %s AND mhr.model_type = %s AND r.name = 'Administrator'
        """, (user_id, MODEL_TYPE))
        if cur.fetchone()["cnt"]:
            return json.dumps({"user_id": user_id, "permission": permission, "has_permission": True, "via": "Administrator role"})

        # Check via role
        cur.execute("""
            SELECT r.name role_name FROM permissions p
            INNER JOIN role_has_permissions rhp ON rhp.permission_id = p.id
            INNER JOIN model_has_roles mhr ON mhr.role_id = rhp.role_id
            INNER JOIN roles r ON r.id = mhr.role_id
            WHERE mhr.model_id = %s AND mhr.model_type = %s AND p.name = %s LIMIT 1
        """, (user_id, MODEL_TYPE, permission))
        row = cur.fetchone()
        if row:
            return json.dumps({"user_id": user_id, "permission": permission, "has_permission": True, "via": f"Role: {row['role_name']}"})

        return json.dumps({"user_id": user_id, "permission": permission, "has_permission": False})
    finally:
        conn.close()
