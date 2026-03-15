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