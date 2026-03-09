"""
mcp_app/agent/host.py
─────────────────────
FastAPI agent host — mounts on your existing project.

Endpoints:
  GET  /health     → check agent + tools status
  POST /api/chat   → REST (non-streaming)
  WS   /ws/chat    → WebSocket (streaming, recommended)
"""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from mcp_app.agent.claude_agent import ClaudeAgent

# ─────────────────────────────────────────────
# Single shared agent instance
# ─────────────────────────────────────────────
agent: ClaudeAgent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent

    # Import tools so they register with FastMCP
    import mcp_app.mcp_tools.order
    import mcp_app.mcp_tools.discount

    agent = ClaudeAgent()

    await agent._get_tools()

    yield


app = FastAPI(title="Tarot AI Agent Host", lifespan=lifespan)


# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────
@app.get("/health")
async def health():
    tools = [t["name"] for t in agent._tools] if agent else []
    return JSONResponse({
        "status": "ok",
        "tools_loaded": len(tools),
        "tools": tools,
    })


# ─────────────────────────────────────────────
# REST endpoint (non-streaming)
# ─────────────────────────────────────────────
@app.post("/api/chat")
async def rest_chat(body: dict):
    """
    Body:  { "message": "...", "history": [{role, content}] }
    Returns: { "response": "..." }
    """
    message: str       = body.get("message", "").strip()
    history: list[dict] = body.get("history", [])

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    conversation = history + [{"role": "user", "content": message}]

    full_response = ""
    async for chunk in agent.stream(conversation):
        full_response += chunk

    return JSONResponse({"response": full_response})


# ─────────────────────────────────────────────
# WebSocket endpoint (streaming)
# ─────────────────────────────────────────────
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """
    Client sends: { "message": "...", "history": [{role, content}] }
    Server sends chunks: { "type": "chunk", "text": "..." }
    Server sends done:   { "type": "done" }
    Server sends error:  { "type": "error", "text": "..." }
    """
    await websocket.accept()

    try:
        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)

            message: str        = data.get("message", "").strip()
            history: list[dict] = data.get("history", [])

            if not message:
                continue

            conversation = history + [{"role": "user", "content": message}]

            async for chunk in agent.stream(conversation):
                await websocket.send_text(json.dumps({
                    "type": "chunk",
                    "text": chunk,
                }))

            await websocket.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "text": str(e),
            }))
        except Exception:
            pass