# mcp_app/auth.py
import secrets
import hashlib
import os
import bcrypt
from datetime import datetime
from mcp_app.db import get_connection


# ── Password verify ───────────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Generate Sanctum-style opaque token ──────────────────────
def generate_token() -> tuple[str, str]:
    plain  = secrets.token_hex(40)
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    return plain, hashed


# ── Token verify cache: { token_id: (user_dict, expires_at) } ──
import time as _time
_token_cache: dict = {}
_TOKEN_CACHE_TTL = 60  # seconds — short enough to respect revocation


# ── Login ─────────────────────────────────────────────────────
def login(email: str, password: str) -> dict | None:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        # Find user
        cur.execute("""
            SELECT id, name, email, password
            FROM users
            WHERE email      = %s
              AND deleted_at IS NULL
              AND active     = 1
            LIMIT 1
        """, (email,))
        user = cur.fetchone()

        if not user:
            return None

        # Verify password
        if not verify_password(password, user["password"]):
            return None

        # Clean up old tokens for this user (keep last 5)
        cur.execute("""
            DELETE FROM personal_access_tokens
            WHERE tokenable_id = %s
              AND tokenable_type = %s
              AND id NOT IN (
                SELECT id FROM (
                    SELECT id FROM personal_access_tokens
                    WHERE tokenable_id = %s AND tokenable_type = %s
                    ORDER BY created_at DESC LIMIT 5
                ) t
              )
        """, (
            user["id"], "App\\Domains\\Auth\\Models\\User",
            user["id"], "App\\Domains\\Auth\\Models\\User",
        ))

        # Generate token
        plain, hashed = generate_token()
        now           = datetime.now()

        # Store in personal_access_tokens (same table as Sanctum)
        cur.execute("""
            INSERT INTO personal_access_tokens
                (tokenable_type, tokenable_id, name, token, abilities, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "App\\Domains\\Auth\\Models\\User",
            user["id"],
            "api-token",
            hashed,
            '["*"]',
            now,
            now,
        ))
        conn.commit()
        token_id = cur.lastrowid

        return {
            "token":   f"{token_id}|{plain}",
            "user_id": user["id"],
            "name":    user["name"],
            "email":   user["email"],
        }

    finally:
        conn.close()


# ── Verify token ──────────────────────────────────────────────
def verify_token(raw_token: str) -> dict | None:
    if "|" not in raw_token:
        return None

    token_id, plain = raw_token.split("|", 1)
    hashed          = hashlib.sha256(plain.encode()).hexdigest()

    # Check cache first
    cached = _token_cache.get(token_id)
    if cached and _time.time() < cached[1]:
        return cached[0]

    ttl_days = int(os.getenv("TOKEN_TTL_DAYS", "30"))

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT pat.tokenable_id, pat.created_at, u.name, u.email
            FROM   personal_access_tokens pat
            INNER JOIN users u ON u.id = pat.tokenable_id
            WHERE  pat.id    = %s
              AND  pat.token = %s
            LIMIT 1
        """, (token_id, hashed))
        row = cur.fetchone()

        if not row:
            _token_cache.pop(token_id, None)
            return None

        # Token TTL check
        age = (datetime.now() - row["created_at"]).days
        if age > ttl_days:
            cur.execute("DELETE FROM personal_access_tokens WHERE id = %s", (token_id,))
            conn.commit()
            _token_cache.pop(token_id, None)
            return None

        cur.execute(
            "UPDATE personal_access_tokens SET last_used_at = %s WHERE id = %s",
            (datetime.now(), token_id)
        )
        conn.commit()

        result = {
            "id":    row["tokenable_id"],
            "name":  row["name"],
            "email": row["email"],
        }
        _token_cache[token_id] = (result, _time.time() + _TOKEN_CACHE_TTL)
        return result

    finally:
        conn.close()


# ── Load permissions from DB ──────────────────────────────────
def load_permissions(user_id: int) -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        model_type = "App\\Domains\\Auth\\Models\\User"

        # Get roles
        cur.execute("""
            SELECT r.id, r.name
            FROM   roles r
            INNER JOIN model_has_roles mhr ON mhr.role_id = r.id
            WHERE  mhr.model_id   = %s
              AND  mhr.model_type = %s
        """, (user_id, model_type))
        roles      = cur.fetchall()
        role_ids   = [r["id"]   for r in roles]
        role_names = [r["name"] for r in roles]

        # Administrator gets all permissions
        if "Administrator" in role_names:
            cur.execute("SELECT name FROM permissions")
            permissions = [r["name"] for r in cur.fetchall()]
        else:
            permissions = []

            if role_ids:
                placeholders = ",".join(["%s"] * len(role_ids))
                cur.execute(f"""
                    SELECT DISTINCT p.name
                    FROM   permissions p
                    INNER JOIN role_has_permissions rhp ON rhp.permission_id = p.id
                    WHERE  rhp.role_id IN ({placeholders})
                """, role_ids)
                permissions = [r["name"] for r in cur.fetchall()]

            # Direct user permissions
            cur.execute("""
                SELECT p.name
                FROM   permissions p
                INNER JOIN model_has_permissions mhp ON mhp.permission_id = p.id
                WHERE  mhp.model_id   = %s
                  AND  mhp.model_type = %s
            """, (user_id, model_type))
            direct      = [r["name"] for r in cur.fetchall()]
            permissions = list(set(permissions + direct))

        return {"roles": role_names, "permissions": permissions}

    finally:
        conn.close()