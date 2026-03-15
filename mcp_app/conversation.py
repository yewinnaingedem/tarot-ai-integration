# mcp_app/conversation.py
from mcp_app.db import get_connection
import asyncio
# ── In-memory cache — { session_id: [messages] } ─────────────
_conversation_cache: dict = {}

def load_history(session_id: int) -> list:
    """Load from DB once, cache in memory"""
    if session_id in _conversation_cache:
        print(f"📋 Cache hit for session {session_id}")
        return _conversation_cache[session_id]

    # Not cached — load from DB
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT role, content
            FROM chat_messages
            WHERE chat_session_id = %s
            ORDER BY created_at ASC
        """, (session_id,))
        messages = [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]
        _conversation_cache[session_id] = messages
        print(f"📋 Loaded {len(messages)} messages for session {session_id}")
        return messages
    finally:
        conn.close()

def append_to_history(session_id: int, role: str, content: str):
    """Append new message to cache — no DB read needed"""
    if session_id not in _conversation_cache:
        _conversation_cache[session_id] = []
    _conversation_cache[session_id].append({
        "role":    role,
        "content": content,
    })

def clear_history(session_id: int):
    """Clear cache for a session"""
    if session_id in _conversation_cache:
        del _conversation_cache[session_id]

def get_history(session_id: int) -> list:
    """Get cached history — load if not cached"""
    return load_history(session_id)

def new_session_history() -> list:
    """Empty history for new chat"""
    return []

async def get_conversation(chat_session_id):

    loop = asyncio.get_event_loop()
    messages = await loop.run_in_executor(None, load_history, chat_session_id)
    return {"messages": messages}