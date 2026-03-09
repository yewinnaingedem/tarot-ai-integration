from mcp_app.core import mcp
import mcp_app.mcp_tools.order
import mcp_app.mcp_tools.discount

if __name__ == "__main__":
    mcp.run(
        transport="stdio",
    )