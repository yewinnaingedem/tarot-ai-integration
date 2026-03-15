# mcp_app/agent/host.py
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from mcp_app.agent.groq_agent import GroqAgent

# ── Single shared agent instance ─────────────────────────────
agent: GroqAgent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent

    # Import tools so they register with FastMCP
    import mcp_app.mcp_tools.order
    import mcp_app.mcp_tools.discount

    agent = GroqAgent()
    await agent._connect_mcp()
    yield

    # Cleanup on shutdown
    await agent.close()

app = FastAPI(title="Tarot AI Agent Host", lifespan=lifespan)

# ── Health check ──────────────────────────────────────────────
@app.get("/health")
async def health():
    tools = [t["function"]["name"] for t in agent._tools] if agent else []
    return JSONResponse({
        "status":       "ok",
        "model":        "groq/llama-3.3-70b-versatile",
        "tools_loaded": len(tools),
        "tools":        tools,
    })

# ── REST endpoint ─────────────────────────────────────────────
@app.post("/api/chat")
async def rest_chat(body: dict):
    message: str        = body.get("message", "").strip()
    history: list[dict] = body.get("history", [])

    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    response = await agent.chat(message, history)
    return JSONResponse({"response": response})

# ── WebSocket endpoint ────────────────────────────────────────
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw     = await websocket.receive_text()
            data    = json.loads(raw)
            message = data.get("message", "").strip()
            history = data.get("history", [])

            if not message:
                continue

            response = await agent.chat(message, history)
            await websocket.send_text(json.dumps({
                "type": "done",
                "text": response,
            }))

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