# mcp_app/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from mcp_app.auth import verify_token
from mcp_app.permission import set_current_user, clear_current_user
from mcp_app.agent import handle_message_stream
from mcp_app.conversation import load_history, append_to_history, clear_history, new_session_history
from mcp_app.models.chat_session import create_chat_session, store_message
from mcp_app.logger import logger
import asyncio, json

_disconnected = set()  # track closed websocket ids

def _mark_disconnected(ws_id: int):
    _disconnected.add(ws_id)
    if len(_disconnected) > 1000:   # prevent unbounded growth
        _disconnected.clear()

async def _safe_send(websocket: WebSocket, data: dict):
    """Send JSON to websocket, silently ignore if already closed."""
    try:
        await websocket.send_json(data)
    except (WebSocketDisconnect, RuntimeError):
        _mark_disconnected(id(websocket))

async def handle_websocket(websocket: WebSocket):
    try:
        await websocket.accept()
    except Exception:
        return

    ws_id      = id(websocket)
    user_id    = None
    session_id = None
    history    = []
    loop       = asyncio.get_event_loop()

    try:
        # ── Connect + verify token ────────────────────────────
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        except (WebSocketDisconnect, RuntimeError):
            return
        data  = json.loads(raw)
        token = data.get("token", "")

        user = await loop.run_in_executor(None, verify_token, token)
        if not user:
            await _safe_send(websocket, {"event": "error", "message": "Unauthorized"})
            await websocket.close(code=4003)
            return

        user_id    = user["id"]
        session_id = data.get("session_id", None)
        set_current_user(user_id)

        # ── Load history if resuming existing session ─────────
        if session_id:
            history = await loop.run_in_executor(None, load_history, session_id)
            print(f"📋 Resumed session {session_id} with {len(history)} messages")
        else:
            history = new_session_history()

        await _safe_send(websocket, {
            "event":      "connected",
            "user_id":    user_id,
            "session_id": session_id,
        })

        # ── Message loop ──────────────────────────────────────
        while True:
            try:
                raw = await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                break
            payload = json.loads(raw)

            # ── New chat ──────────────────────────────────────
            if payload.get("new_chat"):
                session_id = None
                history    = new_session_history()
                print(f"🆕 User {user_id} started new chat")
                continue

            # ── Switch session — load history once ────────────
            if payload.get("switch_session"):
                session_id = int(payload["switch_session"])
                history    = await loop.run_in_executor(
                    None, load_history, session_id
                )
                print(f"🔄 Switched to session {session_id} | {len(history)} messages loaded")
                await _safe_send(websocket, {
                    "event":      "session_switched",
                    "session_id": session_id,
                })
                continue

            message = payload.get("message", "").strip()
            if not message:
                continue

            # ── Update session_id from payload first ──────────
            if payload.get("session_id"):
                session_id = int(payload["session_id"])

            # ── Inject last AI plan into confirmation messages ─
            msg_lower = message.lower()
            is_confirm = (
                "အတည်ပြုပြီး" in message
                or "[confirm_action" in msg_lower
                or ("confirm" in msg_lower and any(t in msg_lower for t in ["coupon", "discount"]))
            )
            original_message = message
            if is_confirm and session_id:
                from mcp_app.conversation import _cache
                cached = _cache.get(session_id, [])
                last_ai = next(
                    (h["content"] for h in reversed(cached) if h.get("role") == "assistant"),
                    None,
                )
                if last_ai:
                    message = f"{last_ai}\n\n{message}"
                    print(f"💉 Injected AI plan into confirm message for session {session_id}")

            await _safe_send(websocket, {"event": "typing"})

            # ── Auto-create session on first message ──────────
            if not session_id:
                session_id = await loop.run_in_executor(
                    None, create_chat_session, user_id, message[:50]
                )
                history = new_session_history()
                print(f"✅ New session {session_id} created")
                await _safe_send(websocket, {
                    "event":      "session_created",
                    "session_id": session_id,
                    "title":      message[:50],
                })

            # ── Store user message to DB ──────────────────────
            # Skip if voice message already stored by /transcribe
            if not payload.get("voice_stored"):
                await loop.run_in_executor(
                    None, store_message, session_id, user_id, "user", original_message
                )

            # ── Append to memory cache ────────────────────────
            append_to_history(session_id, "user", original_message)

            # ── Stream response chunk-by-chunk ────────────────
            async def send_chunk(text):
                if ws_id not in _disconnected:
                    await _safe_send(websocket, {"event": "stream", "content": text})

            async def send_status(text):
                if ws_id not in _disconnected:
                    await _safe_send(websocket, {"event": "status", "content": text})

            response = await handle_message_stream(message, history, on_chunk=send_chunk, on_status=send_status, session_id=session_id)

            # ── Check for pending file download ───────────────
            from mcp_app.agent import get_agent
            agent = await get_agent()
            download = agent._pending_download
            agent._pending_download = None

            # ── Append report marker to response if report was generated
            if download:
                response += f"\n\n[REPORT_DOWNLOAD:{download['filename']}]"

            # ── Store response to DB ──────────────────────────
            await loop.run_in_executor(
                None, store_message, session_id, user_id, "assistant", response
            )

            # ── Append response to memory cache ──────────────
            append_to_history(session_id, "assistant", response)

            await _safe_send(websocket, {
                "event":      "stream_end",
                "content":    response,
                "session_id": session_id,
            })

            # ── Send file download if report was generated ────
            if download:
                await _safe_send(websocket, {
                    "event":    "file_download",
                    "filename": download["filename"],
                    "data":     download["data"],
                })

    except asyncio.TimeoutError:
        logger.error(f"WebSocket timeout for user {user_id}")
        try:
            await websocket.close(code=4008)
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception(f"Unhandled WebSocket error for user {user_id}: {e}")
    finally:
        _disconnected.discard(ws_id)
        clear_current_user()
        if user_id:
            print(f"🔴 User {user_id} disconnected")
