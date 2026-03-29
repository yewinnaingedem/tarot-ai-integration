from mcp_app.core import mcp
from mcp_app.permission import set_current_user
import mcp_app.mcp_tools.order
import mcp_app.mcp_tools.discount
import mcp_app.mcp_tools.coupon
import mcp_app.mcp_tools.category
import mcp_app.mcp_tools.package
import mcp_app.mcp_tools.report
import mcp_app.mcp_tools.analyise


@mcp.tool()
def set_user_context(user_id: int) -> dict:
    """Set the current user for permission checks. Must be called before any other tool."""
    set_current_user(user_id)
    return {"status": "ok", "user_id": user_id}

if __name__ == "__main__":
    mcp.run(
        transport="stdio",
    )