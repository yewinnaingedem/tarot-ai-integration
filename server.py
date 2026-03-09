"""
server.py
─────────
Single entry point that runs both:
  - FastAPI agent host  (REST + WebSocket)
  - MCP server          (HTTP transport for external clients)

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from mcp_app.agent.host import app

from mcp_app.core import mcp
mcp_http = mcp.http_app(path="/mcp")
app.mount("/mcp", mcp_http)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)