# bridge.py
from fastapi import FastAPI, WebSocket, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from mcp_app.auth import login, verify_token
from mcp_app.permission import set_current_user
from mcp_app.websocket import handle_websocket
from mcp_app.conversation import load_history 
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

    messages = await loop.run_in_executor(None, load_history, req.chat_session_id)
    return {"messages": messages}

# ── WebSocket — just delegates to handler ─────────────────────
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await handle_websocket(websocket)

# ── Reply endpoint (direct, no AI) ────────────────────────────
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