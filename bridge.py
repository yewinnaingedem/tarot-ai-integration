# bridge.py
from fastapi import FastAPI, WebSocket, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from mcp_app.auth import login, verify_token
from mcp_app.permission import set_current_user
from mcp_app.websocket import handle_websocket
from mcp_app.conversation import load_history, load_history_from_db
from mcp_app.logger import logger
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os

app      = FastAPI()
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

INTERNAL_SECRET = os.getenv("MCP_INTERNAL_SECRET", "")

# ── Auth dependency ───────────────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    loop = asyncio.get_event_loop()
    user = await loop.run_in_executor(None, verify_token, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    set_current_user(user["id"])
    return user

# ── Routes ────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email:    str
    password: str

class ConversationRequest(BaseModel):
    chat_session_id : int

@app.post("/auth/login")
async def auth_login(req: LoginRequest):
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, login, req.email, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": result["token"], "user": {"id": result["user_id"], "name": result["name"]}}

@app.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {"user": user}

@app.post("/auth/get-conversation")
async def get_conversation(
    req:         ConversationRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    # Verify token
    loop = asyncio.get_event_loop()
    user = await loop.run_in_executor(None, verify_token, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    messages = await loop.run_in_executor(None, load_history_from_db, req.chat_session_id)
    return {"messages": messages}

# ── WebSocket — just delegates to handler ─────────────────────
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await handle_websocket(websocket)

# ── Dashboard endpoint ────────────────────────────────────────
@app.get("/api/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    from mcp_app.db import get_connection
    from datetime import datetime, timedelta
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # KPI: today
        cur.execute("""
            SELECT COUNT(*) total,
                   SUM(status='complete') completed,
                   SUM(status='pending') pending,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue
            FROM orders WHERE deleted_at IS NULL AND created_at >= %s
        """, (today_start,))
        today = cur.fetchone()

        # KPI: this month
        cur.execute("""
            SELECT COUNT(*) total,
                   SUM(status='complete') completed,
                   SUM(status='pending') pending,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue
            FROM orders WHERE deleted_at IS NULL AND created_at >= %s AND created_at < %s
        """, (month_start, now))
        this_month = cur.fetchone()

        # KPI: last month
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue
            FROM orders WHERE deleted_at IS NULL AND created_at >= %s AND created_at < %s
        """, (last_month_start, month_start))
        last_month = cur.fetchone()

        # Unreplied paid orders
        cur.execute("""
            SELECT COUNT(*) cnt FROM orders o
            LEFT JOIN reply r ON r.order_id = o.id
            WHERE o.payment_complete=1 AND o.deleted_at IS NULL AND r.id IS NULL
        """)
        unreplied = cur.fetchone()

        # Revenue last 30 days (daily)
        cur.execute("""
            SELECT DATE(created_at) day,
                   COALESCE(SUM(CASE WHEN status='complete' THEN total_amount END),0) revenue,
                   COUNT(*) orders
            FROM orders WHERE deleted_at IS NULL AND created_at >= %s
            GROUP BY DATE(created_at) ORDER BY day ASC
        """, (now - timedelta(days=30),))
        revenue_trend = [{"day": str(r["day"]), "revenue": float(r["revenue"]), "orders": r["orders"]} for r in cur.fetchall()]

        # Category breakdown this month
        cur.execute("""
            SELECT c.name category,
                   COUNT(o.id) total,
                   SUM(o.status='complete') completed,
                   COALESCE(SUM(CASE WHEN o.status='complete' THEN o.total_amount END),0) revenue
            FROM orders o
            JOIN packages p ON p.id=o.package_id
            JOIN category c ON c.id=p.category_id
            WHERE o.deleted_at IS NULL AND o.created_at >= %s AND o.created_at < %s
            GROUP BY c.id, c.name ORDER BY revenue DESC
        """, (month_start, now))
        categories = [{"category": r["category"], "total": r["total"],
                       "completed": int(r["completed"] or 0), "revenue": float(r["revenue"])} for r in cur.fetchall()]

        # Pending orders needing follow-up (>24h)
        cutoff = now - timedelta(hours=24)
        cur.execute("""
            SELECT o.order_ref, o.customer_name, o.customer_phone, o.total_amount,
                   p.name package_name, c.name category_name,
                   TIMESTAMPDIFF(HOUR, o.created_at, NOW()) hours_waiting
            FROM orders o
            JOIN packages p ON p.id=o.package_id
            JOIN category c ON c.id=p.category_id
            WHERE o.status='pending' AND o.deleted_at IS NULL AND o.created_at <= %s
            ORDER BY o.created_at ASC LIMIT 10
        """, (cutoff,))
        pending_list = [{"ref": r["order_ref"], "customer": r["customer_name"],
                         "phone": r["customer_phone"], "amount": float(r["total_amount"] or 0),
                         "package": r["package_name"], "category": r["category_name"],
                         "hours": r["hours_waiting"]} for r in cur.fetchall()]

        # Conversion rate this month
        total_m = int(this_month["total"] or 0)
        completed_m = int(this_month["completed"] or 0)
        conv = round(completed_m / total_m * 100, 1) if total_m else 0

        # Revenue change %
        rev_this = float(this_month["revenue"] or 0)
        rev_last = float(last_month["revenue"] or 0)
        rev_change = round((rev_this - rev_last) / rev_last * 100, 1) if rev_last else 0

        return {
            "kpi": {
                "today_orders":   int(today["total"] or 0),
                "today_revenue":  float(today["revenue"] or 0),
                "today_pending":  int(today["pending"] or 0),
                "month_revenue":  rev_this,
                "month_orders":   total_m,
                "conversion":     conv,
                "unreplied":      int(unreplied["cnt"] or 0),
                "revenue_change": rev_change,
            },
            "revenue_trend": revenue_trend,
            "categories":    categories,
            "pending_list":  pending_list,
        }
    finally:
        conn.close()


class ReplyRequest(BaseModel):
    order_ref: str
    answer:    str

@app.post("/api/reply")
async def reply_to_order(
    req:  ReplyRequest,
    user: dict = Depends(get_current_user),
):
    from mcp_app.db import get_connection
    text = req.order_ref.strip()
    if not text.startswith("PKTR-"):
        text = "PKTR-" + text.replace("KTR-", "").replace("PTR-", "")
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT o.id, o.order_ref, o.customer_name, o.status, o.payment_complete,
                   r.id AS reply_id
            FROM orders o
            LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
            WHERE o.order_ref = %s AND o.deleted_at IS NULL
        """, (text,))
        order = cur.fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        if order["reply_id"]:
            raise HTTPException(400, "Already replied")
        if not order["payment_complete"]:
            raise HTTPException(400, "Payment not complete")

        cur.execute(
            "INSERT INTO reply (order_id, answer, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
            (order["id"], req.answer),
        )
        cur.execute("UPDATE orders SET status='complete', updated_at=NOW() WHERE id=%s", (order["id"],))
        conn.commit()
        return {"success": True, "order_ref": order["order_ref"], "customer": order["customer_name"]}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.exception(f"reply_to_order failed for {req.order_ref}: {e}")
        raise HTTPException(500, str(e))
    finally:
        conn.close()

# ── TTS endpoint (edge-tts, free) ─────────────────────────────
from fastapi.responses import StreamingResponse
import hashlib

_tts_cache: dict = {}  # simple in-memory cache: hash -> mp3 bytes

class TTSRequest(BaseModel):
    text:  str
    voice: str = "my-MM-ThihaNeural"

@app.post("/api/tts")
async def text_to_speech(
    req:  TTSRequest,
    user: dict = Depends(get_current_user),
):
    import edge_tts

    text = req.text.strip()[:4096]
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    # Check cache
    cache_key = hashlib.md5(f"{text}:{req.voice}".encode()).hexdigest()
    if cache_key in _tts_cache:
        return StreamingResponse(
            iter([_tts_cache[cache_key]]),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline"},
        )

    # Stream and cache
    try:
        chunks = []
        tts = edge_tts.Communicate(text, voice=req.voice)
        async for chunk in tts.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
    except Exception as e:
        raise HTTPException(status_code=503, detail="TTS service unavailable, try again")

    audio = b"".join(chunks)
    if len(_tts_cache) > 200:
        _tts_cache.pop(next(iter(_tts_cache)))
    _tts_cache[cache_key] = audio

    return StreamingResponse(
        iter([audio]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline"},
    )