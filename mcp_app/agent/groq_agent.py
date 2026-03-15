# mcp_app/agent/groq_agent.py
import json, os, asyncio
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class GroqAgent:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model  = "llama-3.1-8b-instant"  # ← smaller, faster, higher TPM limit
        self._tools  = []
        self._session  = None
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

        print(f"✅ Groq + MCP ready | {len(self._tools)} tools loaded")
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
    async def chat(self, message: str, history: list = []) -> str:
        from mcp_app.agent.system_prompt import get_system_prompt
        # ── Fresh system prompt with current date/time ────────────
        system = get_system_prompt()

        messages = [{"role": "system", "content": system}]

        recent_history = history[-4:] if len(history) > 4 else history
        for h in recent_history:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({
                    "role":    h["role"],
                    "content": h["content"][:300],
                })

        messages.append({"role": "user", "content": message})

        tool_keywords = [
            "order", "discount", "revenue", "sales", "package",
            "pending", "customer", "performance", "trend", "create",
            "deactivate", "show", "list", "get", "fetch", "total",
            "report", "analyze", "best", "worst", "summary", "today",
            "week", "month", "follow", "urgent", "latest", "how many",
            "how much", "what is", "give me", "check",
        ]
        needs_tools = any(kw in message.lower() for kw in tool_keywords)

        called_tools   = set()
        max_iterations = 2
        iterations     = 0

        while iterations < max_iterations:
            iterations += 1

            response = self.client.chat.completions.create(
                model       = self.model,
                messages    = messages,
                tools       = self._tools if needs_tools else None,
                tool_choice = "auto" if needs_tools else "none",
                max_tokens  = 1024,
                temperature = 0.1,  # ← very low = strict, no hallucination
            )

            choice = response.choices[0]
            msg    = choice.message

            if not msg.tool_calls:
                return msg.content or "No response"

            # Filter duplicates
            unique_calls = []
            for tc in msg.tool_calls:
                if tc.function.name not in called_tools:
                    called_tools.add(tc.function.name)
                    unique_calls.append(tc)
                else:
                    print(f"⚠️ Skipping duplicate: {tc.function.name}")

            if not unique_calls:
                return msg.content or "No response"

            messages.append({
                "role":       "assistant",
                "content":    msg.content or "",
                "tool_calls": [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in unique_calls
                ]
            })

            for tc in unique_calls:
                try:
                    args   = json.loads(tc.function.arguments or "{}")
                    result = await self._call_tool(tc.function.name, args)
                except Exception as e:
                    result = json.dumps({"error": str(e)})

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

            # Force final answer after tools
            needs_tools = False

        return "Please try again."

    async def close(self):
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)
        except Exception:
            pass