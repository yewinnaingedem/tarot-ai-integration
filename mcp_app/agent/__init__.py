from mcp_app.agent.groq_agent import GroqAgent
# from mcp_app.agent.gemini_agent import GeminiAgent
from mcp_app.agent.antropic import Anthropic
from mcp_app.permission import can

_agent: Anthropic  = None

async def get_agent() -> Anthropic:
    global _agent
    if _agent is None:
        import mcp_app.mcp_tools.order
        import mcp_app.mcp_tools.discount
        _agent = Anthropic()
        await _agent._connect_mcp()
    return _agent

async def handle_message(message: str, history: list = []) -> str:
    try:
        agent    = await get_agent()
        response = await agent.chat(message, history)
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Agent error: {str(e)}"
