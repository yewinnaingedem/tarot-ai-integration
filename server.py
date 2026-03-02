from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Tarot-Analyzer", json_response=True)

# --- Your Tarot/Sales Tool ---
@mcp.tool()
def analyze_sales(csv_path: str) -> str:
    """Analyzes the tarot sales data for the admin."""
    # We will add pandas logic here later!
    return f"Analyzing {csv_path}... Found high demand for 'Love Tarot' readings."

# --- Your Traffic Crash Tool ---
@mcp.tool()
def analyze_crashes(csv_path: str) -> str:
    """Analyzes traffic crash patterns."""
    return f"Scanning {csv_path}... Identifying hotspots near intersection X."

# CHANGE THIS LINE:
if __name__ == "__main__":
    mcp.run() # Default is stdio, which Askimo prefers