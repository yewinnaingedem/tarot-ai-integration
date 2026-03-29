import json, os, asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv
from ..permission import get_user_info

load_dotenv()


class GoogleAgent:
    def __init__(self):
        self._client            = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model_heavy        = "gemini-2.5-flash"
        self.model_light        = "gemini-2.0-flash-lite"
        self._tools             = []
        self._gemini_tools      = None
        self._session           = None
        self._stdio_cm          = None
        self._categories_shown  = False
        self._selected_category = None
        self._coupon_flow       = False
        self._cached_categories = None
        self._cache_name        = None  # explicit context cache

    # ── MCP connection ────────────────────────────────────────
    async def _connect_mcp(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(command="python", args=["main.py"])

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
            if t.name != "set_user_context"
        ]

        self._gemini_tools = self._build_gemini_tools()

        # Create explicit context cache for static system prompt
        await self._create_prompt_cache()

        print(f"✅ Google AI + MCP ready | {len(self._tools)} tools loaded")
        for t in self._tools:
            print(f"   🔧 {t['function']['name']}")

    # ── Explicit context caching ──────────────────────────────
    async def _create_prompt_cache(self):
        """Cache the static system prompt for cost savings."""
        from mcp_app.agent.system_prompt import STATIC_SYSTEM_PROMPT
        try:
            cache = self._client.caches.create(
                model=f"models/{self.model_heavy}",
                config=types.CreateCachedContentConfig(
                    display_name="pinky-tarot-system-prompt",
                    system_instruction=STATIC_SYSTEM_PROMPT,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[types.Part(text="System context loaded.")]
                        )
                    ],
                    ttl="3600s",  # 1 hour
                ),
            )
            self._cache_name = cache.name
            print(f"✅ Context cache created: {cache.name}")
        except Exception as e:
            print(f"⚠️ Cache creation failed (will use uncached): {e}")
            self._cache_name = None

    async def _refresh_cache(self):
        """Refresh cache TTL if it exists."""
        if self._cache_name:
            try:
                self._client.caches.update(
                    name=self._cache_name,
                    config=types.UpdateCachedContentConfig(ttl="3600s"),
                )
            except Exception:
                await self._create_prompt_cache()

    # ── Build Gemini tools ────────────────────────────────────
    def _build_gemini_tools(self):
        declarations = []
        for t in self._tools:
            fn = t["function"]
            params = fn.get("parameters", {})
            clean = self._clean_schema(params)
            decl = {"name": fn["name"], "description": fn["description"]}
            if clean.get("properties"):
                decl["parameters"] = clean
            declarations.append(decl)
        return types.Tool(function_declarations=declarations)

    _UNSUPPORTED_KEYS = {
        "additionalProperties", "exclusiveMinimum", "exclusiveMaximum",
        "minimum", "maximum", "minLength", "maxLength", "pattern",
        "minItems", "maxItems", "uniqueItems", "default", "$schema",
    }

    def _clean_schema(self, schema: dict) -> dict:
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        type_map = {
            "string": "STRING", "integer": "INTEGER", "number": "NUMBER",
            "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
        }
        for k, v in schema.items():
            if k in self._UNSUPPORTED_KEYS:
                continue
            if k == "type" and isinstance(v, str):
                cleaned[k] = type_map.get(v, v)
            elif k == "properties" and isinstance(v, dict):
                cleaned[k] = {pk: self._clean_schema(pv) for pk, pv in v.items()}
            elif k == "items" and isinstance(v, dict):
                cleaned[k] = self._clean_schema(v)
            else:
                cleaned[k] = v
        return cleaned

    # ── MCP tool execution ────────────────────────────────────
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
        return "\n".join(
            f"{i+1}. {c.get('name')} (ID: {c.get('id')})"
            for i, c in enumerate(cats)
        )

    def _parse_packages(self, result: str) -> str:
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
        if not self._cached_categories:
            raw = await self._call_tool("get_categories", {})
            try:
                self._cached_categories = json.loads(raw)
            except Exception:
                self._cached_categories = []
        return self._cached_categories

    def _find_category_id(self, text: str) -> int | None:
        if not self._cached_categories:
            return None
        text_lower = text.lower()
        best_match, best_len = None, 0
        for c in self._cached_categories:
            cname = (c.get("name") or "").lower()
            if cname and cname in text_lower and len(cname) > best_len:
                best_match, best_len = c.get("id"), len(cname)
        return best_match

    # ── Gemini API call ───────────────────────────────────────
    async def _gemini_call(self, system_text: str, contents: list, tools=None, temperature: float = 0.1, light: bool = False):
        model_name = self.model_light if light else self.model_heavy

        config_kwargs = {
            "temperature": temperature,
            "max_output_tokens": 1024,
        }

        # Use cached content for heavy model if cache exists
        if not light and self._cache_name:
            config_kwargs["cached_content"] = self._cache_name
            # Dynamic context goes as first user message (cache has static part)
            config = types.GenerateContentConfig(
                tools=[tools] if tools else None,
                **config_kwargs,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_text,
                tools=[tools] if tools else None,
                **config_kwargs,
            )

        for attempt in range(3):
            try:
                return self._client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                err = str(e)
                if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt < 2:
                    wait = (attempt + 1) * 2
                    print(f"⏳ Rate limited, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                # If cache expired, retry without cache
                if "cached_content" in err.lower() or "cache" in err.lower():
                    print("⚠️ Cache expired, recreating...")
                    await self._create_prompt_cache()
                    config_kwargs.pop("cached_content", None)
                    config = types.GenerateContentConfig(
                        system_instruction=system_text,
                        tools=[tools] if tools else None,
                        **config_kwargs,
                    )
                    continue
                raise

    LIGHT_SYSTEM_PROMPT = (
        "သင်သည် Pinky Tarot ၏ admin AI assistant ဖြစ်ပါသည်။ "
        "မြန်မာ online tarot reading platform ဖြစ်ပြီး orders, categories, packages, discounts, coupons များကို စီမံခန့်ခွဲပေးပါသည်။ "
        "⚠️ အမြဲတမ်း မြန်မာဘာသာဖြင့်သာ ပြန်ဖြေပါ။ English လုံးဝ မသုံးပါနဲ့။ "
        "ငွေပမာဏ format: 9,000 MMK။ "
        "Data မဟုတ်တာ လုံးဝ မဖန်တီးပါနဲ့ — tool results ကိုသာ ပြပါ။ "
        "Lists များကို bullet points ဖြင့် တိုတိုရှင်းရှင်း ဖြေပါ။"
    )

    # ── Main chat method ──────────────────────────────────────
    async def chat(self, message: str, history: list = []) -> str:
        from mcp_app.agent.system_prompt import get_dynamic_context, STATIC_SYSTEM_PROMPT
        from mcp_app.permission import get_current_user

        # Sync user context to MCP subprocess
        uid = get_current_user()
        if uid:
            await self._call_tool("set_user_context", {"user_id": uid})

        dynamic_ctx = get_dynamic_context(get_user_info())

        # ── Intent detection ──────────────────────────────────
        msg_lower = message.lower()

        wants_all_categories = any(kw in msg_lower for kw in [
            "all category", "all categories", "every category", "ခုလုံး", "အားလုံး",
        ])
        wants_all_packages = any(kw in msg_lower for kw in [
            "all package", "all packages", "every package", "i want all", "want all",
        ])
        asking_for_packages = any(kw in msg_lower for kw in [
            "package", "show package", "which package", "specific package", "all package", "check",
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
        active_tools = self._gemini_tools if needs_tools else None

        # ── PRE-RESOLVE: packages of a named category ────────
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
                return f"**{cat_name}** အတွက် packages များ:\n\n{pkg_list}"

        # ── Model selection ───────────────────────────────────
        heavy_keywords = [
            "analyze", "analysis", "suggest", "recommendation", "trend",
            "compare", "revenue", "performance", "report", "summary",
            "create", "make", "add", "new", "holiday", "strategy",
            "what can", "help", "hello", "hi", "mingalaba", "how are",
        ]
        use_light = needs_tools and not any(kw in msg_lower for kw in heavy_keywords)

        # ── Build contents ────────────────────────────────────
        if use_light:
            system_text = self.LIGHT_SYSTEM_PROMPT
            contents = []
            for h in (history[-4:] if len(history) > 4 else history):
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    role = "model" if h["role"] == "assistant" else "user"
                    contents.append(types.Content(role=role, parts=[types.Part(text=h["content"][:300])]))
        else:
            system_text = STATIC_SYSTEM_PROMPT + "\n" + dynamic_ctx
            contents = []
            # If using cache, inject dynamic context as first user message
            if self._cache_name:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Dynamic context]\n{dynamic_ctx}")]
                ))
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text="နားလည်ပါပြီ။ ဆက်လက်ကူညီပေးပါမည်။")]
                ))
            for h in (history[-6:] if len(history) > 6 else history):
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    role = "model" if h["role"] == "assistant" else "user"
                    contents.append(types.Content(role=role, parts=[types.Part(text=h["content"][:800])]))

        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        called_tools   = set()
        max_iterations = 2
        iterations     = 0

        while iterations < max_iterations:
            iterations += 1

            try:
                response = await self._gemini_call(system_text, contents, active_tools, light=use_light)
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ Gemini error: {err_str[:150]}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    return "Rate limit ရောက်နေပါသည်။ ခဏစောင့်ပြီး ထပ်ကြိုးစားပါ။"
                try:
                    response = await self._gemini_call(system_text, contents, tools=None)
                except Exception:
                    return "တစ်ခုခု မှားယွင်းနေပါသည်။ ထပ်ကြိုးစားပါ။"

            # ── Extract function calls ────────────────────────
            candidate = response.candidates[0]
            parts = candidate.content.parts

            function_calls = []
            for p in parts:
                if p.function_call and p.function_call.name:
                    function_calls.append(p.function_call)

            if not function_calls:
                return response.text or "ပြန်ဖြေချက် မရှိပါ။"

            # ── First new tool call only ──────────────────────
            unique_calls = []
            for fc in function_calls:
                if fc.name not in called_tools:
                    called_tools.add(fc.name)
                    unique_calls.append(fc)
                    break

            if not unique_calls:
                return response.text or "ပြန်ဖြေချက် မရှိပါ။"

            # ── Add model turn to contents ────────────────────
            contents.append(candidate.content)

            # ── Execute tools ─────────────────────────────────
            for fc in unique_calls:
                args = dict(fc.args) if fc.args else {}

                # ── INTERCEPT: create without categories ──────
                if fc.name in ("create_coupon", "create_discount"):
                    has_category = args.get("category_id") is not None
                    if not has_category and not self._categories_shown and not wants_all_categories:
                        print(f"🚫 Intercepting {fc.name} — no category_id")
                        self._coupon_flow = (fc.name == "create_coupon")
                        cats     = await self._ensure_categories()
                        cat_list = self._parse_categories(cats)
                        self._categories_shown = True
                        flow_name = "coupon" if self._coupon_flow else "discount"
                        contents.append(types.Content(role="user", parts=[
                            types.Part(function_response=types.FunctionResponse(
                                name=fc.name, id=getattr(fc, 'id', None),
                                response={"result": (
                                    f"EXACT DATABASE RESULT:\n{cat_list}\n\n"
                                    f"Show ONLY these categories. Ask which category for the {flow_name}."
                                )},
                            ))
                        ]))
                        active_tools = None
                        continue

                # ── INTERCEPT: validate get_packages_by_category
                if fc.name == "get_packages_by_category":
                    cat_id = args.get("category_id")
                    cats   = await self._ensure_categories()
                    valid_ids = {c.get("id") for c in cats}
                    if cat_id not in valid_ids:
                        resolved = self._find_category_id(message)
                        if resolved:
                            cat_id = resolved
                        else:
                            cat_list = self._parse_categories(cats)
                            self._categories_shown = True
                            contents.append(types.Content(role="user", parts=[
                                types.Part(function_response=types.FunctionResponse(
                                    name=fc.name, id=getattr(fc, 'id', None),
                                    response={"result": f"EXACT DATABASE RESULT:\n{cat_list}\n\nCategory not found. Show these and ask user."},
                                ))
                            ]))
                            active_tools = None
                            continue
                    result   = await self._call_tool(fc.name, {"category_id": cat_id})
                    pkg_list = self._parse_packages(result)
                    contents.append(types.Content(role="user", parts=[
                        types.Part(function_response=types.FunctionResponse(
                            name=fc.name, id=getattr(fc, 'id', None),
                            response={"result": f"EXACT DATABASE RESULT:\n{pkg_list}\n\nShow ONLY these packages."},
                        ))
                    ]))
                    self._categories_shown = False
                    active_tools = None
                    continue

                # ── INTERCEPT: get_categories — cache + format
                if fc.name == "get_categories":
                    result = await self._call_tool(fc.name, {})
                    try:
                        self._cached_categories = json.loads(result)
                    except Exception:
                        self._cached_categories = []
                    self._categories_shown = True
                    cat_list = self._parse_categories(self._cached_categories)
                    contents.append(types.Content(role="user", parts=[
                        types.Part(function_response=types.FunctionResponse(
                            name=fc.name, id=getattr(fc, 'id', None),
                            response={"result": f"EXACT DATABASE RESULT:\n{cat_list}\n\nShow ONLY these categories."},
                        ))
                    ]))
                    active_tools = None
                    continue

                # ── Normal tool execution ─────────────────────
                try:
                    result = await self._call_tool(fc.name, args)
                except Exception as e:
                    result = json.dumps({"error": str(e)})

                # ── Permission denied check ───────────────────
                try:
                    parsed = json.loads(result) if isinstance(result, str) else result
                except Exception:
                    parsed = {}
                if isinstance(parsed, dict) and "don't have permission" in str(parsed.get("message", "")):
                    return parsed["message"]

                contents.append(types.Content(role="user", parts=[
                    types.Part(function_response=types.FunctionResponse(
                        name=fc.name, id=getattr(fc, 'id', None),
                        response={"result": result},
                    ))
                ]))

                if fc.name in ("create_coupon", "create_discount"):
                    self._categories_shown = False
                    self._coupon_flow      = False

            active_tools = None

        return "ထပ်ကြိုးစားပါ။"

    async def close(self):
        # Clean up cache
        if self._cache_name:
            try:
                self._client.caches.delete(self._cache_name)
            except Exception:
                pass
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)
        except Exception:
            pass
