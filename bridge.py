# bridge.py
from fastapi import FastAPI, APIRouter, WebSocket, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from mcp_app.auth import login, verify_token
from mcp_app.permission import set_current_user
from mcp_app.websocket import handle_websocket
from mcp_app.conversation import load_history, load_history_from_db
from mcp_app.models.chat_session import store_message
from mcp_app.logger import logger
from fastapi.middleware.cors import CORSMiddleware
import asyncio, os, uuid, io, time, glob

limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
security = HTTPBearer()

VOICE_DIR   = os.path.join(os.path.dirname(__file__), "storage", "voice")
MAX_UPLOAD  = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
VOICE_TTL   = int(os.getenv("VOICE_TTL_DAYS", "30")) * 86400

os.makedirs(VOICE_DIR, exist_ok=True)
app.mount("/storage/voice", StaticFiles(directory=VOICE_DIR), name="voice")

router = APIRouter(prefix="/api")

# CORS from env — set your production domain in ALLOWED_ORIGINS
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
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

@router.post("/auth/login")
@limiter.limit("10/minute")
async def auth_login(request: Request, req: LoginRequest):
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, login, req.email, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": result["token"], "user": {"id": result["user_id"], "name": result["name"]}}

@router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {"user": user}

@router.post("/auth/get-conversation")
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
@app.websocket("/api/ws")
async def websocket_route(websocket: WebSocket):
    await handle_websocket(websocket)

# ── Voice: transcribe + save audio ───────────────────────────
@router.post("/transcribe")
@limiter.limit("30/minute")
async def transcribe(
    request:    Request,
    audio:      UploadFile = File(...),
    session_id: int        = Form(0),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    from groq import AsyncGroq
    loop = asyncio.get_event_loop()
    user = await loop.run_in_executor(None, verify_token, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    audio_bytes = await audio.read(MAX_UPLOAD + 1)
    if len(audio_bytes) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail=f"File too large. Max {os.getenv('MAX_UPLOAD_MB', '10')}MB.")

    # Save audio for replay + cleanup old files
    filename = f"{uuid.uuid4().hex}.webm"
    with open(os.path.join(VOICE_DIR, filename), "wb") as f:
        f.write(audio_bytes)
    _cleanup_old_voice_files()

    # Convert webm → PCM 16kHz mono (AWS requires raw PCM)
    import subprocess
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", "pipe:0",
        "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1",
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    pcm_bytes, _ = await proc.communicate(input=audio_bytes)

    # Transcribe via AWS Transcribe Streaming
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler
    from amazon_transcribe.model import TranscriptEvent

    class Handler(TranscriptResultStreamHandler):
        def __init__(self, stream):
            super().__init__(stream)
            self.transcript = []

        async def handle_transcript_event(self, event: TranscriptEvent):
            for result in event.transcript.results:
                if not result.is_partial:
                    for alt in result.alternatives:
                        self.transcript.append(alt.transcript)

    client = TranscribeStreamingClient(region=os.getenv("AWS_REGION", "ap-southeast-1"))

    stream = await client.start_stream_transcription(
        language_code="my-MM",
        media_sample_rate_hz=16000,
        media_encoding="pcm",
    )

    handler = Handler(stream.output_stream)

    async def send_audio():
        chunk_size = 8192
        for i in range(0, len(pcm_bytes), chunk_size):
            await stream.input_stream.send_audio_event(audio_chunk=pcm_bytes[i:i+chunk_size])
            await asyncio.sleep(0.01)
        await stream.input_stream.end_stream()

    await asyncio.gather(send_audio(), handler.handle_events())
    text = " ".join(handler.transcript).strip()

    from mcp_app.models.chat_session import create_chat_session
    if not session_id:
        session_id = await loop.run_in_executor(
            None, create_chat_session, user["id"], (text[:50] if text else "Voice message")
        )

    await loop.run_in_executor(
        None, store_message, session_id, user["id"], "user", text, f"storage/voice/{filename}"
    )

    return {"text": text, "voice_file": filename, "session_id": session_id}

def _cleanup_old_voice_files():
    """Delete voice files older than VOICE_TTL_DAYS."""
    now = time.time()
    for f in glob.glob(os.path.join(VOICE_DIR, "*.webm")):
        if now - os.path.getmtime(f) > VOICE_TTL:
            try:
                os.remove(f)
            except OSError:
                pass

# ── Dashboard endpoint ────────────────────────────────────────
@router.get("/dashboard")
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
            LEFT JOIN reply r ON r.order_id = o.id AND r.deleted_at IS NULL
            WHERE o.payment_complete=1 AND o.status='pending' AND o.deleted_at IS NULL AND r.id IS NULL
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

@router.post("/reply")
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

_tts_cache: dict = {}  # hash -> mp3 bytes
_TTS_CACHE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB cap

class TTSRequest(BaseModel):
    text:  str
    voice: str = "my-MM-ThihaNeural"

@router.post("/tts")
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
    # Evict oldest entries if cache exceeds size cap
    while sum(len(v) for v in _tts_cache.values()) + len(audio) > _TTS_CACHE_MAX_BYTES and _tts_cache:
        _tts_cache.pop(next(iter(_tts_cache)))
    _tts_cache[cache_key] = audio

    return StreamingResponse(
        iter([audio]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline"},
    )

app.include_router(router)
