# mcp_app/knowledge/context_builder.py
from mcp_app.knowledge.store import search_knowledge
from datetime import datetime, date, timedelta
import pytz


def build_context(message: str, user_info: dict = None) -> str:
    """
    Build minimal dynamic context from ChromaDB.
    Replaces the 2000-token system prompt with 300-500 tokens.
    """
    myanmar_tz = pytz.timezone("Asia/Rangoon")
    now        = datetime.now(myanmar_tz)
    today      = now.date()
    today_str  = now.strftime("%Y-%m-%d")
    date_str   = now.strftime("%A, %B %d, %Y")
    time_str   = now.strftime("%I:%M %p")

    # Last day of month
    if today.month == 12:
        last_day = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # ── User section ──────────────────────────────────────────
    user_name    = "Admin"
    user_section = ""
    if user_info:
        user_name    = user_info.get("name", "Admin")
        role         = user_info.get("role", "Admin")
        user_section = f"Current user: {user_name} | Role: {role}\n"

    # ── Holiday alert (only if within 7 days) ─────────────────
    holiday_alert = _get_holiday_alert(today)

    # ── Search ChromaDB for relevant knowledge ────────────────
    relevant_chunks = search_knowledge(message, n_results=4)
    knowledge_text  = ""
    if relevant_chunks:
        knowledge_text = "\nRelevant context:\n" + "\n".join(
            f"• {chunk}" for chunk in relevant_chunks
        )

    # ── Build final minimal prompt ────────────────────────────
    # context_builder.py — add to prompt
    prompt = f"""You are Pinky Tarot admin AI assistant for {user_name}.
        TODAY: {date_str} | {time_str} Myanmar Time | DATE: {today_str}
        Default discount/coupon end_date: {last_day}
        {user_section}{holiday_alert}{knowledge_text}
        Core rules:
        - Use tools for real data — never fabricate
        - Respond in user's language (English or Myanmar)
        - Address user as {user_name}
        - For create_discount or create_coupon: ALWAYS call get_categories first
        - Call each tool maximum once per response
        - After tool results give final answer immediately
        - For greetings or general questions: respond directly WITHOUT tools
        - NEVER repeat the same sentence — give one clear answer and stop"""

    return prompt.strip()


def _get_holiday_alert(today: date) -> str:
    """Return holiday alert only if within 7 days"""
    try:
        from mcp_app.agent.system_prompt import MYANMAR_HOLIDAYS, HOLIDAY_PATTERNS
        for h_date, info in sorted(MYANMAR_HOLIDAYS.items()):
            delta = (h_date - today).days
            if delta == 0:
                return f"⚠️ TODAY IS HOLIDAY: {info['name']} / {info['name_mm']}\n"
            elif 0 < delta <= 7:
                pattern  = HOLIDAY_PATTERNS.get(info["type"], {})
                strategy = pattern.get("strategy", "")
                return (
                    f"⚠️ HOLIDAY IN {delta} DAYS: "
                    f"{info['name']} ({h_date}). {strategy}\n"
                )
    except Exception:
        pass
    return ""