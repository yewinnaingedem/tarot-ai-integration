# mcp_app/conversation.py
from collections import OrderedDict
from mcp_app.db import get_connection
import asyncio

_MAX_CACHED_SESSIONS = 200

# OrderedDict used as LRU: oldest sessions evicted when limit hit
_cache: OrderedDict = OrderedDict()


def _evict():
    while len(_cache) > _MAX_CACHED_SESSIONS:
        _cache.popitem(last=False)


def load_history(session_id: int) -> list:
    if session_id in _cache:
        _cache.move_to_end(session_id)
        print(f"📋 Cache hit for session {session_id}")
        return _cache[session_id]

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT role, content, created_at FROM chat_messages
            WHERE chat_session_id = %s
            ORDER BY created_at ASC
        """, (session_id,))
        messages = [{"role": r["role"], "content": r["content"], "created_at": str(r["created_at"]) if r["created_at"] else None} for r in cur.fetchall()]
        _cache[session_id] = messages
        _evict()
        print(f"📋 Loaded {len(messages)} messages for session {session_id}")
        return messages
    finally:
        conn.close()


def load_history_from_db(session_id: int) -> list:
    """Always query DB directly — used by HTTP endpoint to get latest messages."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT role, content, voice_path, created_at FROM chat_messages
            WHERE chat_session_id = %s
            ORDER BY created_at ASC
        """, (session_id,))
        messages = [
            {
                "role": r["role"],
                "content": r["content"],
                "voice_path": r.get("voice_path"),
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            }
            for r in cur.fetchall()
        ]
        _cache[session_id] = messages
        _cache.move_to_end(session_id)
        return messages
    finally:
        conn.close()


def append_to_history(session_id: int, role: str, content: str):
    if session_id not in _cache:
        _cache[session_id] = []
    _cache[session_id].append({"role": role, "content": content})
    _cache.move_to_end(session_id)


def clear_history(session_id: int):
    _cache.pop(session_id, None)


# Per-session summary storage: {session_id: (summary_text, history_len_at_summarization)}
_summaries: dict = {}

def get_summary(session_id: int) -> tuple[str, int] | tuple[None, int]:
    if session_id in _summaries:
        return _summaries[session_id]
    # Fall back to DB
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT summary FROM chat_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if row and row.get("summary"):
            _summaries[session_id] = (row["summary"], 0)
            return _summaries[session_id]
    finally:
        conn.close()
    return (None, 0)

def set_summary(session_id: int, summary: str, history_len: int):
    _summaries[session_id] = (summary, history_len)
    # Persist to DB
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE chat_sessions SET summary = %s WHERE id = %s", (summary, session_id))
        conn.commit()
    finally:
        conn.close()


def get_history(session_id: int) -> list:
    return load_history(session_id)


def new_session_history() -> list:
    return []


async def get_conversation(chat_session_id: int):
    loop = asyncio.get_event_loop()
    messages = await loop.run_in_executor(None, load_history, chat_session_id)
    return {"messages": messages}
