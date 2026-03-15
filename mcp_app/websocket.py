# mcp_app/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from mcp_app.auth import verify_token
from mcp_app.permission import set_current_user, clear_current_user
from mcp_app.agent import handle_message
from mcp_app.conversation import load_history, append_to_history, clear_history, new_session_history
from mcp_app.models.chat_session import create_chat_session, store_message
import asyncio, json

async def handle_websocket(websocket: WebSocket):
    await websocket.accept()
    user_id    = None
    session_id = None
    history    = []       # ← current session history in memory
    loop       = asyncio.get_event_loop()

    try:
        # ── Connect + verify token ────────────────────────────
        raw   = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        data  = json.loads(raw)
        token = data.get("token", "")

        user = await loop.run_in_executor(None, verify_token, token)
        if not user:
            await websocket.send_json({"event": "error", "message": "Unauthorized"})
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

        await websocket.send_json({
            "event":      "connected",
            "user_id":    user_id,
            "session_id": session_id,
        })

        # ── Message loop ──────────────────────────────────────
        while True:
            raw     = await websocket.receive_text()
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
                await websocket.send_json({
                    "event":      "session_switched",
                    "session_id": session_id,
                })
                continue

            message = payload.get("message", "").strip()
            if not message:
                continue

            if payload.get("session_id"):
                session_id = int(payload["session_id"])

            await websocket.send_json({"event": "typing"})

            # ── Auto-create session on first message ──────────
            if not session_id:
                session_id = await loop.run_in_executor(
                    None, create_chat_session, user_id, message[:50]
                )
                history = new_session_history()
                print(f"✅ New session {session_id} created")
                await websocket.send_json({
                    "event":      "session_created",
                    "session_id": session_id,
                    "title":      message[:50],
                })

            # ── Store user message to DB ──────────────────────
            await loop.run_in_executor(
                None, store_message, session_id, user_id, "user", message
            )

            # ── Append to memory cache ────────────────────────
            append_to_history(session_id, "user", message)

            # ── Pass full history to agent ────────────────────
            response = await handle_message(message, history)

            # ── Store response to DB ──────────────────────────
            await loop.run_in_executor(
                None, store_message, session_id, user_id, "assistant", response
            )

            # ── Append response to memory cache ──────────────
            append_to_history(session_id, "assistant", response)

            await websocket.send_json({
                "event":      "message",
                "content":    response,
                "session_id": session_id,
            })

    except asyncio.TimeoutError:
        await websocket.close(code=4008)
    except WebSocketDisconnect:
        clear_current_user()
        print(f"🔴 User {user_id} disconnected")
    except Exception as e:
        print(f"WS Error: {e}")
        import traceback
        traceback.print_exc()