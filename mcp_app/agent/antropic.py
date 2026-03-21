# mcp_app/agent/groq_agent.py
import json, os, asyncio
import anthropic
from dotenv import load_dotenv
from ..permission import get_user_info

load_dotenv()

class Anthropic:  # keep class name to avoid breaking imports
    def __init__(self):
        self.client        = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model         = "claude-haiku-4-5"  # ← cheapest Anthropic model
        self._tools        = []
        self._session      = None
        self._stdio_cm     = None
        self._categories_shown  = False
        self._selected_category = None

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

        # ── Convert MCP tools to Anthropic format ─────────────
        self._tools = [
            {
                "name":         t.name,
                "description":  (t.description or "")[:200],
                "input_schema": t.inputSchema or {
                    "type": "object", "properties": {}
                },
            }
            for t in tools_result.tools
        ]

        print(f"✅ Anthropic + MCP ready | {len(self._tools)} tools loaded")
        for t in self._tools:
            print(f"   🔧 {t['name']}")

    async def _call_tool(self, name: str, args: dict) -> str:
        print(f"🔧 Calling: {name}")
        try:
            result  = await self._session.call_tool(name, args)
            content = result.content[0].text if result.content else "{}"
            if len(content) > 3000:
                content = content[:3000] + "... (truncated)"
            return content
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def chat(self, message: str, history: list = []) -> str:
        from mcp_app.agent.system_prompt import get_system_prompt

        system = get_system_prompt(get_user_info())

        # ── Build messages — Anthropic format ─────────────────
        messages = []
        recent_history = history[-4:] if len(history) > 4 else history
        for h in recent_history:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({
                    "role":    h["role"],
                    "content": h["content"][:300],
                })

        messages.append({"role": "user", "content": message})

        # ── Tool decision ──────────────────────────────────────
        msg_lower        = message.lower()
        tool_keywords    = [
            "order", "discount", "revenue", "sales", "package",
            "pending", "customer", "performance", "trend", "create",
            "deactivate", "show", "list", "get", "fetch", "total",
            "report", "analyze", "best", "worst", "summary", "today",
            "week", "month", "follow", "urgent", "latest", "how many",
            "how much", "give me", "check", "holiday", "thingyan",
        ]
        package_keywords    = ["package", "show package", "which package", "all package", "specific package"]
        asking_for_packages = any(kw in msg_lower for kw in package_keywords)
        needs_tools         = any(kw in msg_lower for kw in tool_keywords)

        excluded_tools = set()
        if self._categories_shown and asking_for_packages:
            excluded_tools.add("get_categories")
            print("🚫 Blocking get_categories — already shown")

        active_tools = [
            t for t in self._tools
            if t["name"] not in excluded_tools
        ] if needs_tools else None

        called_tools   = set()
        max_iterations = 2
        iterations     = 0

        while iterations < max_iterations:
            iterations += 1

            try:
                # ── Anthropic API call ─────────────────────────
                kwargs = {
                    "model":      self.model,
                    "max_tokens": 1024,
                    "system":     system,
                    "messages":   messages,
                }
                if active_tools:
                    kwargs["tools"] = active_tools

                loop     = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.messages.create(**kwargs)
                )

            except Exception as e:
                print(f"⚠️ Anthropic error: {e} — retrying without tools")
                try:
                    loop     = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.client.messages.create(
                            model      = self.model,
                            max_tokens = 1024,
                            system     = system,
                            messages   = messages,
                        )
                    )
                except Exception as e2:
                    return f"Sorry, I encountered an error. Please try again."

            # ── Check stop reason ──────────────────────────────
            stop_reason = response.stop_reason

            # No tool use — return text response
            if stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_blocks) or "No response"

            # Tool use
            if stop_reason == "tool_use":
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

                if not tool_use_blocks:
                    text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                    return "\n".join(text_blocks) or "No response"

                # Filter duplicates
                unique_calls = []
                for tc in tool_use_blocks:
                    if tc.name not in called_tools:
                        called_tools.add(tc.name)
                        unique_calls.append(tc)
                    else:
                        print(f"⚠️ Skipping duplicate: {tc.name}")

                if not unique_calls:
                    text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                    return "\n".join(text_blocks) or "No response"

                # ── Add assistant message with tool use ────────
                messages.append({
                    "role":    "assistant",
                    "content": response.content,  # Anthropic needs full content blocks
                })

                # ── Execute tools + build tool results ─────────
                tool_results = []
                for tc in unique_calls:
                    try:
                        result = await self._call_tool(tc.name, tc.input)
                    except Exception as e:
                        result = json.dumps({"error": str(e)})

                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": tc.id,
                        "content":     result,
                    })

                    # ── State tracking ─────────────────────────
                    if tc.name == "get_categories":
                        self._categories_shown = True
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": tc.id + "_instruction",
                            "content": (
                                "Display the complete category list in numbered format "
                                "showing ID and name. Ask discount details. No more tools."
                            )
                        })
                        active_tools = None

                    if tc.name == "get_packages_by_category":
                        self._categories_shown = False
                        active_tools = None

                # ── Add tool results as user message ───────────
                messages.append({
                    "role":    "user",
                    "content": tool_results,
                })

                active_tools = None  # force final answer next iteration
                continue

            # Unexpected stop reason
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(text_blocks) or "Please try again."

        return "Please try again."

    async def close(self):
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)
        except Exception:
            pass