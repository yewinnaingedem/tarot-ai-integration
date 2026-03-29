# mcp_app/agent/groq_agent.py
import json, os, asyncio
from groq import Groq
from dotenv import load_dotenv
from ..permission import get_user_info

load_dotenv()

class GroqAgent:
    def __init__(self):
        self.client             = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model_heavy        = "llama-3.3-70b-versatile"
        self.model_light        = "llama-3.1-8b-instant"
        self._tools             = []
        self._session           = None
        self._stdio_cm          = None
        self._categories_shown  = False
        self._selected_category = None
        self._coupon_flow       = False
        self._cached_categories = None

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

    def _parse_categories(self, cats: list) -> str:
        """Format category list into numbered display string"""
        return "\n".join(
            f"{i+1}. {c.get('name')} (ID: {c.get('id')})"
            for i, c in enumerate(cats)
        )

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

    async def _ensure_categories(self):
        """Fetch and cache categories if not already cached"""
        if not self._cached_categories:
            raw = await self._call_tool("get_categories", {})
            try:
                self._cached_categories = json.loads(raw)
            except Exception:
                self._cached_categories = []
        return self._cached_categories

    def _find_category_id(self, text: str) -> int | None:
        """Try to match a category name from text against cached categories.
        Uses longest-match to avoid 'spouse' matching before 'Lover/ Ex/ Crush/ spouse'."""
        if not self._cached_categories:
            return None
        text_lower = text.lower()
        best_match = None
        best_len   = 0
        for c in self._cached_categories:
            cname = (c.get("name") or "").lower()
            if cname and cname in text_lower and len(cname) > best_len:
                best_match = c.get("id")
                best_len   = len(cname)
        return best_match

    async def _groq_call(self, messages: list, tools=None, temperature: float = 0.1, light: bool = False):
        """Single Groq API call with retry on rate limit"""
        model = self.model_light if light else self.model_heavy
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(
                    model       = model,
                    messages    = messages,
                    tools       = tools,
                    tool_choice = "auto" if tools else "none",
                    max_tokens  = 1024,
                    temperature = temperature,
                )
            except Exception as e:
                if ("429" in str(e) or "rate_limit" in str(e)) and attempt < 2:
                    wait = (attempt + 1) * 2  # 2s, 4s
                    print(f"⏳ Rate limited, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                raise

    LIGHT_SYSTEM_PROMPT = (
        "You are the admin AI assistant for Pinky Tarot — a Myanmar online tarot reading platform. "
        "You help admins manage orders, categories, packages, discounts, and coupons. "
        "You have tools: get_categories, get_packages_by_category, get_order_summary, "
        "get_revenue_trends, create_discount, create_coupon, and more. "
        "Respond in the same language the user uses. Format currency: 9,000 MMK. "
        "NEVER fabricate data — only show what tool results provide. "
        "Keep responses concise with bullet points for lists. "
        "For general questions about what you can do, list your actual capabilities: "
        "view orders, check categories/packages, create discounts/coupons, analyze sales, track revenue."
    )

    async def chat(self, message: str, history: list = []) -> str:
        from mcp_app.agent.system_prompt import get_system_prompt

        full_system = get_system_prompt(get_user_info())

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
        asking_for_packages = any(kw in msg_lower for kw in [
            "package", "show package", "which package", "specific package",
            "all package", "check",
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
        needs_tools = any(kw in msg_lower for kw in tool_keywords)

        # ── Active tools ──────────────────────────────────────
        active_tools = self._tools if needs_tools else None

        # ── PRE-RESOLVE: if user asks for packages of a named category,
        #    resolve it ourselves — no LLM needed, return directly ──
        if asking_for_packages and not wants_all_categories:
            cats = await self._ensure_categories()
            resolved_id = self._find_category_id(message)
            if resolved_id:
                result   = await self._call_tool("get_packages_by_category", {"category_id": resolved_id})
                pkg_list = self._parse_packages(result)
                cat_name = next(
                    (c.get("name") for c in cats if c.get("id") == resolved_id),
                    f"ID {resolved_id}"
                )
                return f"Here are the packages for **{cat_name}**:\n\n{pkg_list}"

        # ── Model selection: light for simple lookups, heavy for analysis ─
        heavy_keywords = [
            "analyze", "analysis", "suggest", "recommendation", "trend",
            "compare", "revenue", "performance", "report", "summary",
            "create", "make", "add", "new", "holiday", "strategy",
            "what can", "help", "hello", "hi", "mingalaba", "how are",
        ]
        # Use light only when tools are needed for simple data lookups
        use_light = needs_tools and not any(kw in msg_lower for kw in heavy_keywords)

        # ── Build messages based on model ─────────────────────
        if use_light:
            messages = [{"role": "system", "content": self.LIGHT_SYSTEM_PROMPT}]
            for h in (history[-4:] if len(history) > 4 else history):
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    messages.append({"role": h["role"], "content": h["content"][:300]})
        else:
            messages = [{"role": "system", "content": full_system}]
            for h in (history[-6:] if len(history) > 6 else history):
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    messages.append({"role": h["role"], "content": h["content"][:800]})
        messages.append({"role": "user", "content": message})

        # ── Inject intent context ─────────────────────────────
        if wants_all_categories and self._categories_shown:
            messages.append({
                "role":    "system",
                "content": "User wants ALL categories. Set category_id=null."
            })
        if wants_all_packages and not wants_all_categories:
            messages.append({
                "role":    "system",
                "content": "User wants ALL packages. Set package_ids=null."
            })

        called_tools   = set()
        max_iterations = 2
        iterations     = 0

        while iterations < max_iterations:
            iterations += 1

            # ── Groq API call ─────────────────────────────────
            try:
                response = await self._groq_call(messages, active_tools, light=use_light)
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ Groq error: {err_str[:150]}")

                if "rate_limit" in err_str or "429" in err_str:
                    return "Rate limit reached. Please wait a few minutes and try again."

                if "tool_use_failed" in err_str or "tool call validation" in err_str:
                    print("🔄 Tool call failed — retrying without tools")
                    try:
                        response = await self._groq_call(messages, tools=None)
                    except Exception as e2:
                        return "Sorry, encountered an error. Please try again."
                else:
                    return "Sorry, encountered an error. Please try again."

            choice = response.choices[0]
            msg    = choice.message

            # ── No tool calls — final answer ──────────────────
            if not msg.tool_calls:
                return msg.content or "No response"

            # ── Only keep the FIRST tool call per turn ────────
            unique_calls = []
            for tc in msg.tool_calls:
                if tc.function.name not in called_tools:
                    called_tools.add(tc.function.name)
                    unique_calls.append(tc)
                    break
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
                    try:
                        create_args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        create_args = {}

                    has_category = create_args.get("category_id") is not None

                    if not has_category and not self._categories_shown and not wants_all_categories:
                        print(f"🚫 Intercepting {tc.function.name} — no category_id")
                        self._coupon_flow = (tc.function.name == "create_coupon")

                        cats     = await self._ensure_categories()
                        cat_list = self._parse_categories(cats)

                        self._categories_shown = True
                        flow_name = "coupon" if self._coupon_flow else "discount"

                        messages.append({
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "content": (
                                f"EXACT DATABASE RESULT — DO NOT ADD, REMOVE, OR RENAME ANY ITEM:\n"
                                f"{cat_list}\n\n"
                                f"Show ONLY these categories. "
                                f"Ask which category for the {flow_name}. "
                                f"Ask: specific packages or all packages?"
                            ),
                        })
                        active_tools = None
                        continue

                # ── INTERCEPT: validate get_packages_by_category ─
                if tc.function.name == "get_packages_by_category":
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}

                    cat_id    = args.get("category_id")
                    cats      = await self._ensure_categories()
                    valid_ids = {c.get("id") for c in cats}

                    if cat_id not in valid_ids:
                        resolved = self._find_category_id(message)
                        if resolved:
                            cat_id = resolved
                            print(f"🔄 Corrected category_id to {cat_id}")
                        else:
                            cat_list = self._parse_categories(cats)
                            self._categories_shown = True
                            messages.append({
                                "role":         "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    f"EXACT DATABASE RESULT — DO NOT ADD, REMOVE, OR RENAME ANY ITEM:\n"
                                    f"{cat_list}\n\n"
                                    f"Could not find that category. "
                                    f"Show these categories and ask the user which one."
                                ),
                            })
                            active_tools = None
                            continue

                    result   = await self._call_tool(tc.function.name, {"category_id": cat_id})
                    pkg_list = self._parse_packages(result)

                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content": (
                            f"EXACT DATABASE RESULT — DO NOT ADD, REMOVE, OR RENAME ANY ITEM:\n"
                            f"{pkg_list}\n\n"
                            f"Show ONLY these packages with their exact IDs, names, and prices. "
                            f"Do NOT invent or guess any package."
                        ),
                    })
                    self._categories_shown = False
                    active_tools = None
                    continue

                # ── INTERCEPT: get_categories — cache + format ─
                if tc.function.name == "get_categories":
                    result = await self._call_tool(tc.function.name, {})
                    try:
                        self._cached_categories = json.loads(result)
                    except Exception:
                        self._cached_categories = []

                    self._categories_shown = True
                    cat_list = self._parse_categories(self._cached_categories)

                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content": (
                            f"EXACT DATABASE RESULT — DO NOT ADD, REMOVE, OR RENAME ANY ITEM:\n"
                            f"{cat_list}\n\n"
                            f"Show ONLY these categories with their exact IDs and names."
                        ),
                    })
                    active_tools = None
                    continue

                # ── Normal tool execution ─────────────────────
                try:
                    args   = json.loads(tc.function.arguments or "{}")
                    result = await self._call_tool(tc.function.name, args)
                except Exception as e:
                    result = json.dumps({"error": str(e)})

                # ── INTERCEPT: permission denied → return directly ─
                try:
                    parsed = json.loads(result) if isinstance(result, str) else result
                except Exception:
                    parsed = {}
                if isinstance(parsed, dict) and "don't have permission" in str(parsed.get("message", "")):
                    return parsed["message"]

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

                if tc.function.name in ("create_coupon", "create_discount"):
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
