import json, os, asyncio
import anthropic
import httpx
from dotenv import load_dotenv
from ..permission import get_user_info, get_current_user, set_current_user

load_dotenv()


class Anthropic:
    def __init__(self):
        self.client         = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_retries=3,
            timeout=httpx.Timeout(300.0, connect=10.0),
        )
        self.model          = "claude-sonnet-4-20250514"
        self.fast_model     = "claude-haiku-3-5-20241022"
        self._tools         = []
        self._mcp           = None
        self._pending_download = None

    # ── MCP connection (in-process, no subprocess) ────────────
    async def _connect_mcp(self):
        from ..core import mcp
        self._mcp = mcp

        tools_result = await mcp.list_tools()

        self._tools = [
            {
                "name":         t.name,
                "description":  (t.description or "")[:200],
                "input_schema": t.parameters or {"type": "object", "properties": {}},
            }
            for t in tools_result
            if t.name != "set_user_context"
        ]

        print(f"✅ Anthropic Sonnet + MCP ready (in-process) | {len(self._tools)} tools")
        for t in self._tools:
            print(f"   🔧 {t['name']}")

    # ── MCP tool call (direct in-process) ─────────────────────
    async def _call_tool(self, name: str, args: dict) -> str:
        print(f"🔧 Calling: {name}")
        try:
            result  = await self._mcp.call_tool(name, args)
            content = result.content[0].text if result.content else "{}"
            try:
                parsed = json.loads(content)
                if parsed.get("type") == "csv_download":
                    self._pending_download = {
                        "filename": parsed["filename"],
                        "data":     parsed["data"],
                    }
                    return json.dumps({
                        "type": "csv_download",
                        "filename": parsed["filename"],
                        "row_count": parsed.get("row_count", 0),
                        "summary": parsed.get("summary", ""),
                    })
            except (json.JSONDecodeError, KeyError):
                pass
            if len(content) > 3000:
                content = content[:3000] + "... (truncated)"
            return content
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Sync user (in-process, just set directly) ─────────────
    async def _sync_user(self, uid: int):
        if uid:
            set_current_user(uid)

    # ── Build system prompt with cache_control ────────────────
    def _build_system(self, user_info) -> list:
        from mcp_app.agent.system_prompt import STATIC_SYSTEM_PROMPT, get_dynamic_context

        return [
            {
                "type": "text",
                "text": STATIC_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": get_dynamic_context(user_info),
            },
        ]

    # ── Web search tool (Anthropic built-in) ─────────────────
    WEB_SEARCH_TOOL = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    }

    # ── Decide if tools needed ────────────────────────────────
    def _needs_tools(self, message: str, history: list = None):
        msg_lower = message.lower()
        tool_keywords = [
            "order", "discount", "coupon", "revenue", "sales", "package",
            "pending", "customer", "performance", "trend", "create",
            "deactivate", "show", "list", "get", "fetch", "total",
            "report", "analyze", "best", "worst", "summary", "today",
            "week", "month", "follow", "urgent", "latest", "how many",
            "how much", "give me", "check", "holiday", "thingyan",
            "yesterday", "category",
            "reply", "unreplied", "unanswered", "respond", "answer",
            "remind", "paid", "waiting", "overdue", "pktr", "batch",
            "export", "csv", "download", "excel",
            "age", "gender", "demographic", "profile", "အသက်", "ကျား", "မ",
            "yes", "confirm", "အတည်ပြု",
        ]
        # Web search keywords
        web_keywords = [
            "search", "ရှာ", "competitor", "ပြိုင်ဘက်", "market", "ဈေးကွက်",
            "what is", "how to", "latest", "news", "trend", "other platform",
        ]
        needs_web = any(kw in msg_lower for kw in web_keywords)

        if any(kw in msg_lower for kw in tool_keywords):
            tools = list(self._tools)
            if needs_web:
                tools.append(self.WEB_SEARCH_TOOL)
            return tools
        if needs_web:
            return [self.WEB_SEARCH_TOOL]
        # If last AI message mentioned orders/reply, keep tools enabled
        if history:
            for h in history[-2:]:
                if h.get("role") == "assistant":
                    last = (h.get("content") or "").lower()
                    if any(k in last for k in ["pktr-", "reply", "order", "batch", "confirm_reply", "awaiting_reply"]):
                        return self._tools
        return None

    # ── Build messages list ───────────────────────────────────
    def _build_messages(self, message: str, history: list):
        messages = []
        # Use more history (8 msgs, 600 chars) when replying to orders
        has_order_ref = "PKTR-" in message.upper() or "reply" in message.lower()
        limit = 8 if has_order_ref else 4
        max_chars = 600 if has_order_ref else 300
        for h in history[-limit:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"][:max_chars]})
        messages.append({"role": "user", "content": message})
        return messages

    # ── Non-streaming chat (kept for REST API) ────────────────
    async def chat(self, message: str, history: list = []) -> str:
        await self._sync_user(get_current_user())
        system   = self._build_system(get_user_info())
        messages = self._build_messages(message, history)
        active_tools = self._needs_tools(message, history)
        called_tools = set()

        for _ in range(5):
            kwargs = {
                "model": self.model, "max_tokens": 4096,
                "system": system, "messages": messages,
            }
            if active_tools:
                kwargs["tools"] = active_tools

            try:
                response = await self.client.messages.create(**kwargs)
            except Exception as e:
                print(f"⚠️ Anthropic error: {e}")
                if "overloaded" in str(e).lower():
                    print(f"🔄 Retrying with {self.fast_model}...")
                    try:
                        kwargs["model"] = self.fast_model
                        response = await self.client.messages.create(**kwargs)
                    except Exception as e2:
                        return "Server များ အလုပ်များနေပါသည်။ ခဏစောင့်ပြီး ထပ်ကြိုးစားပေးပါ။"
                else:
                    return "တစ်ခုခု မှားယွင်းနေပါသည်။ ထပ်ကြိုးစားပေးပါ။"

            if response.stop_reason == "end_turn":
                return "\n".join(b.text for b in response.content if hasattr(b, "text")) or "ပြန်ဖြေချက် မရှိပါ။"

            if response.stop_reason != "tool_use":
                return "\n".join(b.text for b in response.content if hasattr(b, "text")) or "ထပ်ကြိုးစားပေးပါ။"

            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            unique = [tc for tc in tool_blocks if tc.name not in called_tools]
            for tc in unique:
                called_tools.add(tc.name)

            if not unique:
                return "\n".join(b.text for b in response.content if hasattr(b, "text")) or "ပြန်ဖြေချက် မရှိပါ။"

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tc in unique:
                result = await self._call_tool(tc.name, tc.input)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tc.id, "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
            active_tools = None

        return "ထပ်ကြိုးစားပေးပါ။"

    # ── Friendly tool names for status updates ──────────────────
    TOOL_LABELS = {
        "get_latest_order_from_db":  "နောက်ဆုံး order ကြည့်နေပါတယ်...",
        "get_orders_by_ref":         "Order များ ရှာနေပါတယ်...",
        "get_order_by_date":         "Order များ ရှာနေပါတယ်...",
        "get_order_summary":         "Order အချက်အလက် စုစည်းနေပါတယ်...",
        "get_pending_followups":     "Pending order များ စစ်နေပါတယ်...",
        "get_unreplied_paid_orders": "မဖြေရသေးတဲ့ order များ ရှာနေပါတယ်...",
        "get_package_performance":   "Package performance စစ်နေပါတယ်...",
        "get_revenue_trends":        "Revenue trend ခွဲခြမ်းစိတ်ဖြာနေပါတယ်...",
        "get_ai_sales_suggestions":  "Sales suggestion များ ပြင်ဆင်နေပါတယ်...",
        "get_holiday_sales_analysis":"Holiday sales ခွဲခြမ်းစိတ်ဖြာနေပါတယ်...",
        "get_holiday_comparison":    "Holiday comparison စစ်နေပါတယ်...",
        "get_categories":            "Category များ ကြည့်နေပါတယ်...",
        "get_packages_by_category":  "Package များ ကြည့်နေပါတယ်...",
        "create_discount":           "Discount ဖန်တီးနေပါတယ်...",
        "get_discounts":             "Discount များ ကြည့်နေပါတယ်...",
        "deactivate_discount":       "Discount ပိတ်နေပါတယ်...",
        "get_coupons":               "Coupon များ ကြည့်နေပါတယ်...",
        "create_coupon":             "Coupon ဖန်တီးနေပါတယ်...",
        "generate_order_report":     "📊 Report ထုတ်နေပါတယ်...",
        "get_customer_demographics": "👥 Customer demographics ခွဲခြမ်းစိတ်ဖြာနေပါတယ်...",
        "reply_to_order":            "✍️ Order ကို reply လုပ်နေပါတယ်...",
        "batch_reply_orders":        "✍️ Order များကို reply လုပ်နေပါတယ်...",
    }

    # ── Streaming chat (for WebSocket) ────────────────────────
    async def chat_stream(self, message: str, history: list = [], on_chunk=None, on_status=None):
        """Stream response token-by-token via on_chunk(text) callback."""
        await self._sync_user(get_current_user())
        system   = self._build_system(get_user_info())
        messages = self._build_messages(message, history)
        active_tools = self._needs_tools(message, history)
        called_tools = set()
        full_text = ""
        last_tool_result = "{}"

        for _ in range(5):
            kwargs = {
                "model": self.model, "max_tokens": 4096,
                "system": system, "messages": messages,
            }
            if active_tools:
                kwargs["tools"] = active_tools

            try:
                async with self.client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                            full_text += event.delta.text
                            if on_chunk:
                                await on_chunk(event.delta.text)
                    response = await stream.get_final_message()
            except Exception as e:
                print(f"⚠️ Anthropic stream error: {e}")
                # Retry once with fast model on overload
                if "overloaded" in str(e).lower():
                    print(f"🔄 Retrying with {self.fast_model}...")
                    try:
                        kwargs["model"] = self.fast_model
                        async with self.client.messages.stream(**kwargs) as stream:
                            async for event in stream:
                                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                                    full_text += event.delta.text
                                    if on_chunk:
                                        await on_chunk(event.delta.text)
                            response = await stream.get_final_message()
                    except Exception as e2:
                        print(f"⚠️ Fallback also failed: {e2}")
                        err = "Server များ အလုပ်များနေပါသည်။ ခဏစောင့်ပြီး ထပ်ကြိုးစားပေးပါ။"
                        if on_chunk:
                            await on_chunk(err)
                        return err
                else:
                    err = "တစ်ခုခု မှားယွင်းနေပါသည်။ ထပ်ကြိုးစားပေးပါ။"
                if on_chunk:
                    await on_chunk(err)
                return err

            if response.stop_reason == "end_turn":
                if not full_text and last_tool_result and last_tool_result != "{}":
                    try:
                        import json as _json
                        parsed = _json.loads(last_tool_result)
                        if parsed.get("success_count"):
                            full_text = f"{parsed['success_count']} orders reply ပြီးပါပြီ။"
                        elif parsed.get("success") and parsed.get("order_ref"):
                            full_text = f"{parsed['order_ref']} reply ပြီးပါပြီ။"
                        elif parsed.get("error"):
                            full_text = f"Error: {parsed['error']}"
                    except:
                        pass
                    # If still no text, feed tool result back to AI for one more try
                    if not full_text:
                        messages.append({"role": "assistant", "content": response.content})
                        messages.append({"role": "user", "content": [{"type": "text", "text": "ရလဒ်ကို မြန်မာလို အကျဉ်းချုပ် ပြောပြပါ။"}]})
                        try:
                            async with self.client.messages.stream(
                                model=self.model, max_tokens=4096,
                                system=system, messages=messages,
                            ) as stream:
                                async for event in stream:
                                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                                        full_text += event.delta.text
                                        if on_chunk:
                                            await on_chunk(event.delta.text)
                        except:
                            pass
                return full_text or "ထပ်ကြိုးစားပေးပါ။"

            if response.stop_reason != "tool_use":
                return full_text or "ထပ်ကြိုးစားပေးပါ။"

            # Handle tool calls, then stream the next turn
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            unique = [tc for tc in tool_blocks if tc.name not in called_tools]
            for tc in unique:
                called_tools.add(tc.name)

            if not unique:
                return full_text or "ပြန်ဖြေချက် မရှိပါ။"

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tc in unique:
                if on_status:
                    label = self.TOOL_LABELS.get(tc.name, f"🔧 {tc.name} ခေါ်နေပါတယ်...")
                    await on_status(label)
                result = await self._call_tool(tc.name, tc.input)
                last_tool_result = result
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tc.id, "content": result,
                })
            if on_status:
                await on_status("✍️ ဖြေကြားနေပါတယ်...")
            messages.append({"role": "user", "content": tool_results})
            active_tools = None
            full_text = ""  # reset for the post-tool response

        return "ထပ်ကြိုးစားပေးပါ။"

    async def close(self):
        pass  # no subprocess to clean up
