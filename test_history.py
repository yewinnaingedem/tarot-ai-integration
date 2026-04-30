"""
Test chat history: DB schema, store, load, and API endpoint logic.
Run: .venv/bin/python test_history.py
"""
import sys, os
os.environ.setdefault("FASTMCP_STATELESS_HTTP", "true")
from dotenv import load_dotenv
load_dotenv()

from mcp_app.db import get_connection
from mcp_app.models.chat_session import create_chat_session, store_message
from mcp_app.conversation import (
    load_history, load_history_from_db,
    append_to_history, clear_history, new_session_history, _cache
)

PASS = "✅"
FAIL = "❌"
results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, label, detail))
    print(f"  {status}  {label}" + (f"  →  {detail}" if detail else ""))

print("\n── 1. DB connectivity ───────────────────────────────────")
try:
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT 1 AS ok")
    row = cur.fetchone()
    conn.close()
    check("DB connection", row["ok"] == 1)
except Exception as e:
    check("DB connection", False, str(e))
    print("\nCannot continue without DB. Exiting.")
    sys.exit(1)

print("\n── 2. Schema check ──────────────────────────────────────")
conn = get_connection()
cur  = conn.cursor(dictionary=True)

cur.execute("SHOW COLUMNS FROM chat_sessions")
session_cols = {r["Field"] for r in cur.fetchall()}
for col in ["id", "user_id", "title", "created_at", "updated_at"]:
    check(f"chat_sessions.{col}", col in session_cols)

cur.execute("SHOW COLUMNS FROM chat_messages")
msg_cols = {r["Field"] for r in cur.fetchall()}
for col in ["id", "chat_session_id", "user_id", "role", "content", "voice_path", "created_at"]:
    check(f"chat_messages.{col}", col in msg_cols)

check("chat_sessions.summary (optional)", "summary" in session_cols,
      "missing — get_summary/set_summary will fail" if "summary" not in session_cols else "")
conn.close()

print("\n── 3. Create session + store messages ───────────────────")
try:
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM users WHERE deleted_at IS NULL AND active=1 LIMIT 1")
    user_row = cur.fetchone()
    conn.close()
    check("At least one active user exists", user_row is not None)
    user_id = user_row["id"] if user_row else 1

    session_id = create_chat_session(user_id, "Test history session")
    check("create_chat_session returns int", isinstance(session_id, int) and session_id > 0, str(session_id))

    store_message(session_id, user_id, "user",      "Hello, test message")
    store_message(session_id, user_id, "assistant", "Hello back, test reply")
    store_message(session_id, user_id, "user",      "Second user message")
    check("store_message (3 rows)", True)
except Exception as e:
    check("create/store", False, str(e))
    session_id = None

print("\n── 4. load_history (cache miss → DB) ────────────────────")
if session_id:
    try:
        clear_history(session_id)
        msgs = load_history(session_id)
        check("Returns list",              isinstance(msgs, list))
        check("Correct message count",     len(msgs) == 3, f"got {len(msgs)}")
        check("First role = user",         msgs[0]["role"] == "user")
        check("Second role = assistant",   msgs[1]["role"] == "assistant")
        check("Has 'content' key",         "content" in msgs[0])
        check("Has 'created_at' key",      "created_at" in msgs[0])
        check("Session cached after load", session_id in _cache)
    except Exception as e:
        check("load_history", False, str(e))

print("\n── 5. load_history (cache hit) ──────────────────────────")
if session_id:
    try:
        msgs2 = load_history(session_id)
        check("Cache hit returns same data", msgs2 == msgs)
    except Exception as e:
        check("cache hit", False, str(e))

print("\n── 6. load_history_from_db (HTTP endpoint path) ─────────")
if session_id:
    try:
        msgs3 = load_history_from_db(session_id)
        check("Returns list",         isinstance(msgs3, list))
        check("Correct count",        len(msgs3) == 3, f"got {len(msgs3)}")
        check("Has 'voice_path' key", "voice_path" in msgs3[0])
        check("voice_path is None",   msgs3[0]["voice_path"] is None)
    except Exception as e:
        check("load_history_from_db", False, str(e))

print("\n── 7. append_to_history ─────────────────────────────────")
if session_id:
    try:
        before = len(_cache.get(session_id, []))
        append_to_history(session_id, "user", "Appended message")
        after  = len(_cache.get(session_id, []))
        check("Appended to cache",          after == before + 1, f"{before} → {after}")
        check("Appended content correct",   _cache[session_id][-1]["content"] == "Appended message")
    except Exception as e:
        check("append_to_history", False, str(e))

print("\n── 8. new_session_history ───────────────────────────────")
h = new_session_history()
check("Returns empty list", h == [])

print("\n── 9. LRU eviction ──────────────────────────────────────")
from mcp_app.conversation import _MAX_CACHED_SESSIONS, _evict
for fake_id in range(99000, 99000 + _MAX_CACHED_SESSIONS + 5):
    _cache[fake_id] = [{"role": "user", "content": "x"}]
_evict()
check("LRU evicts to max", len(_cache) <= _MAX_CACHED_SESSIONS, f"size={len(_cache)}")

print("\n── 10. Cleanup test session ─────────────────────────────")
if session_id:
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute("DELETE FROM chat_messages WHERE chat_session_id = %s", (session_id,))
        cur.execute("DELETE FROM chat_sessions  WHERE id = %s",             (session_id,))
        conn.commit()
        conn.close()
        clear_history(session_id)
        check("Test data cleaned up", True)
    except Exception as e:
        check("Cleanup", False, str(e))

passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
print(f"\n{'─'*50}")
print(f"  {PASS} {passed} passed   {FAIL} {failed} failed   ({len(results)} total)")
print(f"{'─'*50}\n")
sys.exit(0 if failed == 0 else 1)
