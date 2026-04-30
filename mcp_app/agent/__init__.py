from mcp_app.agent.antropic import Anthropic
from mcp_app.agent.google_agent import GoogleAgent

_agent: Anthropic = None
_google: GoogleAgent = None

async def get_agent() -> Anthropic:
    global _agent
    if _agent is None:
        # Ensure tool modules are registered before connecting
        import mcp_app.mcp_tools.order
        import mcp_app.mcp_tools.discount
        import mcp_app.mcp_tools.coupon
        import mcp_app.mcp_tools.category
        import mcp_app.mcp_tools.package
        import mcp_app.mcp_tools.report
        import mcp_app.mcp_tools.analyise
        import mcp_app.mcp_tools.admin
        import mcp_app.mcp_tools.logs
        import mcp_app.mcp_tools.server_monitor
        _agent = Anthropic()
        await _agent._connect_mcp()
        # start background metrics recording
        import asyncio as _asyncio
        from mcp_app.agent.host import _metrics_loop
        _asyncio.create_task(_metrics_loop())
    return _agent

async def get_google_agent() -> GoogleAgent:
    global _google
    if _google is None:
        _google = GoogleAgent()
        await _google._connect_mcp()
    return _google

async def handle_message(message: str, history: list = [], session_id: int | None = None) -> str:
    try:
        agent    = await get_agent()
        response = await agent.chat(message, history, session_id=session_id)

        if "အလုပ်များနေပါသည်" in response:
            print("🔄 Anthropic overloaded, falling back to Google Gemini...")
            google = await get_google_agent()
            response = await google.chat(message, history)

        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Agent error: {str(e)}"

async def handle_message_stream(message: str, history: list = [], on_chunk=None, on_status=None, session_id: int | None = None) -> str:
    try:
        agent    = await get_agent()
        response = await agent.chat_stream(message, history, on_chunk=on_chunk, on_status=on_status, session_id=session_id)

        # If Anthropic returned overloaded error, try Google
        if "အလုပ်များနေပါသည်" in response:
            print("🔄 Anthropic overloaded, falling back to Google Gemini...")
            if on_status:
                await on_status("🔄 Google Gemini ဖြင့် ပြန်ကြိုးစားနေပါတယ်...")
            google = await get_google_agent()
            response = await google.chat(message, history)
            if on_chunk:
                await on_chunk(response)

        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Agent error: {str(e)}"
