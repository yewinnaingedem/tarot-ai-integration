# mcp_app/agent/groq_agent.py
import json, os, asyncio
# from groq import Groq
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class GeminiAgent:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

        self.model = genai.GenerativeModel("gemini-2.5-flash")

        self._tools = []
        self._session = None
        self._stdio_cm = None

    async def _connect_mcp(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command = "python",
            args    = ["main.py"],
        )

        self._stdio_cm          = stdio_client(server_params)
        self._read, self._write = await self._stdio_cm.__aenter__()
        self._session           = ClientSession(self._read, self._write)

        await self._session.__aenter__()
        await self._session.initialize()

        tools_result = await self._session.list_tools()

        # ── Keep tool descriptions short to save tokens ───────
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name":        t.name,
                    "description": (t.description or "")[:200],  # ← truncate
                    "parameters":  t.inputSchema or {
                        "type": "object", "properties": {}
                    },
                }
            }
            for t in tools_result.tools
        ]

        print(f"✅ Gemini + MCP ready | {len(self._tools)} tools loaded")
        for t in self._tools:
            print(f"   🔧 {t['function']['name']}")

    async def _call_tool(self, name: str, args: dict) -> str:
        print(f"🔧 Calling: {name}")
        try:
            result  = await self._session.call_tool(name, args)
            content = result.content[0].text if result.content else "{}"
            # ── Truncate large tool results to save tokens ────
            if len(content) > 3000:
                content = content[:3000] + "... (truncated)"        
            return content
        except Exception as e:
            return json.dumps({"error": str(e)})

    # groq_agent.py — update chat() method
    async def chat(self, message: str, history: list = []):
        from mcp_app.agent.system_prompt import get_system_prompt
        system = get_system_prompt()
        prompt = system + "\n\n"
        for h in history[-10:]:
            prompt += f"{h['role']}: {h['content']}\n"
        prompt += f"user: {message}\nassistant:"
        response = self.model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 1024
            }
        )
        return response.text
    
    async def close(self):
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)
        except Exception:
            pass