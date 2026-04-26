# database.py
from mcp_app.db import get_connection
from datetime import datetime

def create_chat_session(user_id: int, title: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
        """, (user_id, title, datetime.now(), datetime.now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def store_message(session_id: int, user_id: int, role: str, content: str, voice_path: str = None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_messages
                (chat_session_id, user_id, role, content, voice_path, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (session_id, user_id, role, content, voice_path, datetime.now(), datetime.now()))
        conn.commit()
    finally:
        conn.close()

def get_session_messages(session_id: int) -> list:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT role, content FROM chat_messages
            WHERE chat_session_id = %s
            ORDER BY created_at ASC
        """, (session_id,))
        return cur.fetchall()
    finally:
        conn.close()