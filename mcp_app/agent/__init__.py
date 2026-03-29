from mcp_app.agent.antropic import Anthropic

_agent: Anthropic = None

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

async def handle_message_stream(message: str, history: list = [], on_chunk=None, on_status=None) -> str:
    try:
        agent    = await get_agent()
        response = await agent.chat_stream(message, history, on_chunk=on_chunk, on_status=on_status)
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Agent error: {str(e)}"
