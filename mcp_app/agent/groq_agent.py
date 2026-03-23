# mcp_app/agent/groq_agent.py
import json, os, asyncio
from groq import Groq
from dotenv import load_dotenv
from ..permission import get_user_info

load_dotenv()

class GroqAgent:
    def __init__(self):
        self.client             = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model              = "llama-3.3-70b-versatile"
        self._tools             = []
        self._session           = None
        self._stdio_cm          = None
        self._categories_shown  = False
        self._selected_category = None
        self._coupon_flow       = False

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

        SHORT_DESCRIPTIONS = {
            "get_latest_order_from_db":  "Get the most recent order",
            "get_order_by_date":         "Get orders by date range. start_date: YYYY-MM-DD, end_date: YYYY-MM-DD",
            "get_order_summary":         "Get order stats. period: today|yesterday|this_week|this_month|last_month",
            "get_pending_followups":     "Get pending orders needing follow-up. older_than_hours: int",
            "get_package_performance":   "Get package sales stats. period: this_week|this_month|last_month|all_time",
            "get_revenue_trends":        "Get revenue trends. granularity: daily|weekly, days: int",
            "get_ai_sales_suggestions":  "Get AI sales recommendations",
            "get_holiday_sales_analysis":"Analyze holiday sales and upcoming holiday preparation",
            "get_holiday_comparison":    "Compare holiday sales year over year. holiday_name: thingyan|thadingyut",
            "get_categories":            "Get all categories with IDs and names",
            "get_packages_by_category":  "Get packages in a category. category_id: int",
            "create_discount":           "Create discount. amount must be number. category_id null for all",
            "get_discounts":             "Get active discounts. category_id optional",
            "deactivate_discount":       "Deactivate a discount. discount_id: int",
            "get_coupons":               "List all coupons. active_only: bool",
            "get_coupon":                "Get single coupon by ID",
            "find_coupon_by_code":       "Find coupon by code string",
            "create_coupon":             "Create coupon. amount must be number. category_id from get_categories",
            "update_coupon":             "Update coupon fields. coupon_id required",
            "deactivate_coupon":         "Deactivate a coupon. coupon_id: int",
            "get_expiring_coupons":      "Get coupons expiring soon. days: int",
        }

        self._tools = [
            {
                "type": "function",
                "function": {
                    "name":        t.name,
                    "description": SHORT_DESCRIPTIONS.get(t.name, (t.description or "")[:100]),
                    "parameters":  t.inputSchema or {"type": "object", "properties": {}},
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
            if name not in ("get_categories", "get_packages_by_category"):
                if len(content) > 2000:
                    content = content[:2000] + "... (truncated)"
            return content
        except Exception as e:
            print(f"❌ Tool error: {e}")
            return json.dumps({"error": str(e)})

    def _parse_categories(self, result: str) -> str:
        """Parse tool result into numbered category list"""
        try:
            cats_data = json.loads(result)
            if isinstance(cats_data, list):
                return "\n".join(
                    f"{i+1}. {c.get('name')} (ID: {c.get('id')})"
                    for i, c in enumerate(cats_data)
                )
        except Exception:
            pass
        return result[:500]

    def _parse_packages(self, result: str) -> str:
        """Parse tool result into numbered package list"""
        try:
            data = json.loads(result)
            if isinstance(data, list):
                return "\n".join(
                    f"{i+1}. {p.get('name')} (ID: {p.get('id')}) — {p.get('price', p.get('amount', '?'))} MMK"
                    for i, p in enumerate(data)
                )
        except Exception:
            pass
        return result[:500]

    async def _groq_call(self, messages: list, tools=None, temperature: float = 0.1):
        """Single Groq API call with error handling"""
        return self.client.chat.completions.create(
            model       = self.model,
            messages    = messages,
            tools       = tools,
            tool_choice = "auto" if tools else "none",
            max_tokens  = 1024,
            temperature = temperature,
        )

    async def chat(self, message: str, history: list = []) -> str:
        from mcp_app.agent.system_prompt import get_system_prompt

        system   = get_system_prompt(get_user_info())
        messages = [{"role": "system", "content": system}]

        recent_history = history[-4:] if len(history) > 4 else history
        for h in recent_history:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({
                    "role":    h["role"],
                    "content": h["content"][:300],
                })

        messages.append({"role": "user", "content": message})

        # ── Intent detection ──────────────────────────────────
        msg_lower = message.lower()

        wants_all_categories = any(kw in msg_lower for kw in [
            "all category", "all categories", "every category",
            "ခုလုံး", "အားလုံး",
        ])
        wants_all_packages = any(kw in msg_lower for kw in [
            "all package", "all packages", "every package",
            "i want all", "want all",
        ])

        tool_keywords = [
            "order", "discount", "coupon", "revenue", "sales", "package",
            "pending", "customer", "performance", "trend", "create",
            "deactivate", "show", "list", "get", "fetch", "total",
            "report", "analyze", "best", "worst", "summary", "today",
            "week", "month", "follow", "urgent", "latest", "how many",
            "how much", "give me", "check", "holiday", "thingyan",
            "yesterday", "date", "when", "last", "this", "category",
            "all", "want", "make", "add", "new",
        ]
        package_keywords    = ["package", "show package", "which package", "specific package"]
        needs_tools         = any(kw in msg_lower for kw in tool_keywords)
        asking_for_packages = any(kw in msg_lower for kw in package_keywords)

        # ── Excluded tools ────────────────────────────────────
        excluded_tools = set()
        if self._categories_shown and asking_for_packages:
            excluded_tools.add("get_categories")

        # ── Active tools ──────────────────────────────────────
        all_tools    = self._tools
        active_tools = [
            t for t in all_tools
            if t["function"]["name"] not in excluded_tools
        ] if needs_tools else None

        # ── Inject intent context ─────────────────────────────
        if wants_all_categories and self._categories_shown:
            messages.append({
                "role":    "system",
                "content": (
                    "User wants ALL categories. Set category_id=null. "
                    "Collect remaining details then call the tool immediately."
                )
            })

        if wants_all_packages and not wants_all_categories:
            messages.append({
                "role":    "system",
                "content": (
                    "User wants ALL packages. Set package_ids=null. "
                    "Proceed to collect details and call the tool."
                )
            })

        called_tools   = set()
        max_iterations = 2
        iterations     = 0

        while iterations < max_iterations:
            iterations += 1

            # ── Groq API call ─────────────────────────────────
            try:
                response = await self._groq_call(messages, active_tools)
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ Groq error: {err_str[:150]}")

                if "rate_limit" in err_str or "429" in err_str:
                    return "Rate limit reached. Please wait a few minutes and try again."

                if "tool_use_failed" in err_str or "tool call validation" in err_str:
                    # ── Retry without tools ───────────────────
                    print("🔄 Tool call failed — retrying without tools")
                    try:
                        response = await self._groq_call(messages, tools=None)
                    except Exception as e2:
                        return f"Sorry, encountered an error. Please try again."
                else:
                    return "Sorry, encountered an error. Please try again."

            choice = response.choices[0]
            msg    = choice.message

            # ── No tool calls — final answer ──────────────────
            if not msg.tool_calls:
                return msg.content or "No response"

            # ── Filter duplicate tool calls ───────────────────
            unique_calls = []
            for tc in msg.tool_calls:
                if tc.function.name not in called_tools:
                    called_tools.add(tc.function.name)
                    unique_calls.append(tc)
                else:
                    print(f"⚠️ Skipping duplicate: {tc.function.name}")

            if not unique_calls:
                return msg.content or "No response"

            # ── Add assistant message ─────────────────────────
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

            # ── Execute tools ─────────────────────────────────
            for tc in unique_calls:

                # ── INTERCEPT: block create without categories ─
                if tc.function.name in ("create_coupon", "create_discount"):
                    if not self._categories_shown and not wants_all_categories:
                        print(f"🚫 Intercepting {tc.function.name}")

                        self._coupon_flow = (tc.function.name == "create_coupon")

                        # Call get_categories directly
                        cat_result = await self._call_tool("get_categories", {})
                        cat_list   = self._parse_categories(cat_result)

                        # Add as tool result for this tool call
                        messages.append({
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "content":      cat_result,
                        })

                        self._categories_shown = True
                        flow_name = "coupon" if self._coupon_flow else "discount"

                        messages.append({
                            "role":    "user",
                            "content": (
                                f"IMPORTANT — display ONLY these exact categories from database:\n\n"
                                f"{cat_list}\n\n"
                                f"Ask user which category for the {flow_name}. "
                                f"Ask: specific packages or all packages? "
                                f"Do not call any more tools yet."
                            )
                        })

                        active_tools = None
                        continue  # skip normal execution

                # ── Normal tool execution ─────────────────────
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

                # ── Post-tool state tracking ──────────────────
                if tc.function.name == "get_categories":
                    self._categories_shown = True
                    cat_list  = self._parse_categories(result)
                    flow_name = "coupon" if self._coupon_flow else "discount"
                    messages.append({
                        "role":    "user",
                        "content": (
                            f"IMPORTANT — display ONLY these exact categories from database:\n\n"
                            f"{cat_list}\n\n"
                            f"Ask user which category for the {flow_name}. "
                            f"Ask: specific packages or all packages? "
                            f"Do not call any more tools yet."
                        )
                    })
                    active_tools = None

                elif tc.function.name == "get_packages_by_category":
                    self._categories_shown = False
                    pkg_list  = self._parse_packages(result)
                    flow_name = "coupon" if self._coupon_flow else "discount"
                    messages.append({
                        "role":    "user",
                        "content": (
                            f"IMPORTANT — display ONLY these exact packages from database:\n\n"
                            f"{pkg_list}\n\n"
                            + (
                                "Ask which packages for the coupon (or all). "
                                "Then collect: type (percentage/amount), amount (number), "
                                "available_times (integer), start_date, end_date."
                                if self._coupon_flow else
                                "Ask which packages to discount (or all). "
                                "Then collect: type (percentage/amount), amount (number), "
                                "title, start_date, end_date."
                            ) +
                            " Do not call any more tools yet."
                        )
                    })
                    active_tools = None

                elif tc.function.name in ("create_coupon", "create_discount"):
                    self._categories_shown = False
                    self._coupon_flow      = False

            # ── Force final answer after tools ────────────────
            active_tools = None

        return "Please try again."

    async def close(self):
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)
        except Exception:
            pass