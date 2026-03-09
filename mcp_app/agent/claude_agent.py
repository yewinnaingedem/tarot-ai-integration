"""
mcp_app/agent/claude_agent.py
"""

import json
import os
from typing import AsyncGenerator

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL      = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096
MAX_ROUNDS = 10


class ClaudeAgent:

    def __init__(self):
        from mcp_app.core import mcp as _mcp
        self._mcp    = _mcp
        self._tools  = []
        self._system = _mcp.instructions or ""
        self._client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    async def _get_tools(self) -> list[dict]:
        if self._tools:
            return self._tools

        raw = await self._mcp.get_tools()
        self._tools = [
            {
                "name":         name,
                "description":  tool.description or "",
                "input_schema": tool.parameters or {
                    "type": "object", "properties": {}
                },
            }
            for name, tool in raw.items()
        ]
        return self._tools

    async def _run_tool(self, name: str, arguments: dict) -> str:
        try:
            result = await self._mcp.call_tool(name, arguments)
            if isinstance(result, list):
                return "\n".join(
                    b.text for b in result if hasattr(b, "text")
                )
            return str(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def stream(
        self,
        conversation: list[dict],
    ) -> AsyncGenerator[str, None]:
        """
        Runs the tool-use loop and yields text chunks.

        Args:
            conversation: Full message history.
                [{"role": "user", "content": "..."},
                 {"role": "assistant", "content": "..."},
                 {"role": "user", "content": "new message"}]

        Yields:
            str — text chunks of Claude's final response.
        """
        tools    = await self._get_tools()
        messages = list(conversation)

        for _ in range(MAX_ROUNDS):

            response = await self._client.messages.create(
                model      = MODEL,
                max_tokens = MAX_TOKENS,
                system     = self._system,
                messages   = messages,
                tools      = tools,
            )

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if block.type == "text":
                        text = block.text
                        for i in range(0, len(text), 8):
                            yield text[i:i + 8]
                return

            if response.stop_reason == "tool_use":
                messages.append({
                    "role":    "assistant",
                    "content": [b.model_dump() for b in response.content],
                })

                tool_names = [
                    b.name for b in response.content if b.type == "tool_use"
                ]
                yield f"\n⚙️ *Using: {', '.join(tool_names)}...*\n"

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = await self._run_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

                messages.append({
                    "role":    "user",
                    "content": tool_results,
                })
                continue

            yield "\n⚠️ Unexpected stop. Please try again."
            return

        yield "\n⚠️ Too many tool rounds. Please simplify your request."