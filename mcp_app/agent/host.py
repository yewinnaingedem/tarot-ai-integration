# mcp_app/agent/host.py
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from mcp_app.agent.antropic import Anthropic

agent: Anthropic = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    import mcp_app.mcp_tools.order
    import mcp_app.mcp_tools.discount
    import mcp_app.mcp_tools.category
    import mcp_app.mcp_tools.coupon
    import mcp_app.mcp_tools.report
    import mcp_app.mcp_tools.analyise

    agent = Anthropic()
    await agent._connect_mcp()
    yield
    await agent.close()

app = FastAPI(title="Tarot AI Agent Host", lifespan=lifespan)

@app.get("/health")
async def health():
    tools = [t["name"] for t in agent._tools] if agent else []
    return JSONResponse({
        "status":       "ok",
        "model":        agent.model if agent else "not loaded",
        "tools_loaded": len(tools),
        "tools":        tools,
    })

@app.post("/api/chat")
async def rest_chat(body: dict):
    message = body.get("message", "").strip()
    history = body.get("history", [])
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    response = await agent.chat(message, history)
    return JSONResponse({"response": response})

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

            async def send_chunk(text):
                await websocket.send_text(json.dumps({"type": "stream", "text": text}))

            full = await agent.chat_stream(message, history, on_chunk=send_chunk)
            await websocket.send_text(json.dumps({"type": "done", "text": full or ""}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "text": str(e)}))
        except Exception:
            pass
