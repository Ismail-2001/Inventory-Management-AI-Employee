"""
Shared LLM Client for all agents.

Single httpx.AsyncClient instance per agent lifecycle.
Exponential backoff retry (3 attempts).
Circuit breaker (5 failures -> 60s open).
Prompt injection boundary tagging.
Structured error handling.
Cost tracking.
"""

import asyncio
import json
import os
import random
import re
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMToolResult(LLMResult):
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class StreamEvent:
    """One event from :meth:`LLMClient.call_stream` — ``delta`` carries a text
    fragment, ``final`` the complete result (with any tool calls)."""

    kind: str  # "delta" | "final"
    text: str = ""
    result: LLMToolResult | None = None


MODEL_PRICING = {
    "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
}

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class CircuitBreaker:
    def __init__(self, threshold: int = 5, recovery_timeout: float = 60.0) -> None:
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        if time.time() < self._open_until:
            return True
        if self._failures >= self.threshold:
            self._open_until = time.time() + self.recovery_timeout
            return True
        return False

    def success(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def failure(self) -> None:
        self._failures += 1


_PROMPT_BOUNDARY_START = "[PROMPT_START_BOUNDARY]"
_PROMPT_BOUNDARY_END = "[PROMPT_END_BOUNDARY]"


def _sanitize_for_prompt(user_input: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", user_input)
    cleaned = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    cleaned = cleaned.replace("[", "\\[").replace("]", "\\]")
    boundary = secrets.token_hex(8)
    return f"{_PROMPT_BOUNDARY_START}{boundary}\n{cleaned}\n{_PROMPT_BOUNDARY_END}{boundary}"


class LLMClient:
    def __init__(
        self,
        system_prompt: str = "",
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout: float = 30.0,
        max_retries: int = 3,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

        self.system_prompt = system_prompt
        self.model = model or os.getenv("MODEL_NAME", "gemini-2.0-flash")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

        if GROQ_API_KEY:
            self._use_gemini = False
            self._use_groq = True
            self._api_key = GROQ_API_KEY
        elif GOOGLE_API_KEY:
            self._use_gemini = True
            self._use_groq = False
            self._api_key = GOOGLE_API_KEY
        elif OPENAI_API_KEY:
            self._use_gemini = False
            self._use_groq = False
            self._api_key = OPENAI_API_KEY
        else:
            self._use_gemini = True
            self._use_groq = False
            self._api_key = ""

        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits)

    async def close(self) -> None:
        await self._client.aclose()

    async def call(self, user_prompt: str, response_model: type[T] | None = None) -> LLMResult:
        if self.circuit_breaker.is_open:
            raise RuntimeError("Circuit breaker is open — LLM unavailable, using rule-based fallback")

        safe_prompt = _sanitize_for_prompt(user_prompt)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                start = time.perf_counter()
                text = await self._do_call(safe_prompt)
                latency = (time.perf_counter() - start) * 1000

                self.circuit_breaker.success()

                result = LLMResult(
                    text=text,
                    model=self.model,
                    latency_ms=round(latency, 1),
                )

                if response_model:
                    try:
                        parsed = response_model.model_validate_json(text)
                        result.text = parsed.model_dump_json()
                    except Exception:
                        data = self._extract_json(text)
                        if data:
                            result.text = json.dumps(data)
                        else:
                            result.text = text

                return result

            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                self.circuit_breaker.failure()
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt + random.uniform(0, 1)
                    await asyncio.sleep(wait)

        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts") from last_error

    async def _do_call(self, prompt: str) -> str:
        if not self._api_key:
            return ""

        if self._use_gemini:
            return await self._call_gemini(prompt)
        elif self._use_groq:
            return await self._call_openai(prompt, base_url=GROQ_URL)
        else:
            return await self._call_openai(prompt, base_url=OPENAI_URL)

    async def _call_gemini(self, prompt: str) -> str:
        url = GEMINI_URL.format(model=self.model)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        r = await self._client.post(url, json=payload, params={"key": self._api_key})
        r.raise_for_status()
        data = r.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return str(text)
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Gemini response missing expected structure: {data}") from exc

    async def _call_openai(self, prompt: str, base_url: str = OPENAI_URL) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        r = await self._client.post(base_url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"]
            return str(text)
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"OpenAI response missing expected structure: {data}") from exc

    async def call_with_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMToolResult:
        """Chat-style completion with optional tool calling.

        ``messages`` uses the plain internal format (role/content/tool_calls
        with a flat ``{"id", "name", "arguments"}`` tool_call shape) and is
        converted per provider. User-role content is prompt-injection
        sanitized; system/assistant/tool content passes through untouched so
        tool payloads stay machine-readable.
        """
        if self.circuit_breaker.is_open:
            raise RuntimeError("Circuit breaker is open — LLM unavailable, using rule-based fallback")
        return await self._call_with_tools(self._sanitize_messages(messages), tools)

    async def _call_with_tools(
        self, outbound: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> LLMToolResult:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                start = time.perf_counter()
                text, tool_calls, usage = await self._do_call_tools(outbound, tools)
                latency = (time.perf_counter() - start) * 1000
                self.circuit_breaker.success()
                input_tokens = int(usage.get("input", 0))
                output_tokens = int(usage.get("output", 0))
                return LLMToolResult(
                    text=text,
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=_price_usage(self.model, input_tokens, output_tokens),
                    latency_ms=round(latency, 1),
                    tool_calls=tool_calls,
                )
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                self.circuit_breaker.failure()
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt + random.uniform(0, 1)
                    await asyncio.sleep(wait)

        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts") from last_error

    async def call_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[StreamEvent]:
        """Stream deltas as they arrive, then one ``final`` event.

        Falls back to a single non-streamed call when the provider stream
        fails before any delta was emitted (or no API key is configured).
        Streaming itself is not retried; the non-streamed fallback is.
        """
        if self.circuit_breaker.is_open:
            raise RuntimeError("Circuit breaker is open — LLM unavailable, using rule-based fallback")
        outbound = self._sanitize_messages(messages)

        if not self._api_key:
            yield StreamEvent(kind="final", result=LLMToolResult(text="", model=self.model))
            return

        emitted = False
        try:
            if self._use_gemini:
                stream: AsyncIterator[StreamEvent] = self._stream_gemini(outbound, tools)
            else:
                base_url = GROQ_URL if self._use_groq else OPENAI_URL
                stream = self._stream_openai(outbound, tools, base_url)
            async for event in stream:
                if event.kind == "delta":
                    emitted = True
                yield event
            return
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            if emitted:
                raise

        result = await self._call_with_tools(outbound, tools)
        if result.text:
            yield StreamEvent(kind="delta", text=result.text)
        yield StreamEvent(kind="final", result=result)

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        outbound: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content")
            if message.get("role") == "user" and isinstance(content, str):
                outbound.append({**message, "content": _sanitize_for_prompt(content)})
            else:
                outbound.append(dict(message))
        return outbound

    async def _do_call_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> tuple[str, list[ToolCall], dict[str, int]]:
        if not self._api_key:
            return "", [], {}
        if self._use_gemini:
            return await self._call_gemini_tools(messages, tools)
        base_url = GROQ_URL if self._use_groq else OPENAI_URL
        return await self._call_openai_tools(messages, tools, base_url)

    def _wire_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Internal message dicts -> OpenAI chat-completions wire format."""
        wire: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", "user"))
            entry: dict[str, Any] = {"role": role, "content": message.get("content") or ""}
            tool_calls = message.get("tool_calls")
            if tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("arguments") or {}),
                        },
                    }
                    for tc in tool_calls
                ]
            if role == "tool":
                entry["tool_call_id"] = message.get("tool_call_id", "")
                entry.pop("tool_calls", None)
            wire.append(entry)
        return wire

    async def _call_openai_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, base_url: str
    ) -> tuple[str, list[ToolCall], dict[str, int]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._wire_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        r = await self._client.post(base_url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"OpenAI response missing expected structure: {data}") from exc
        text = str(message.get("content") or "")
        tool_calls = [
            ToolCall(
                id=str(tc.get("id") or f"call_{index}"),
                name=str(tc.get("function", {}).get("name", "")),
                arguments=_parse_tool_args(tc.get("function", {}).get("arguments")),
            )
            for index, tc in enumerate(message.get("tool_calls") or [])
            if tc.get("function", {}).get("name")
        ]
        usage_raw = data.get("usage") or {}
        usage = {
            "input": int(usage_raw.get("prompt_tokens") or 0),
            "output": int(usage_raw.get("completion_tokens") or 0),
        }
        return text, tool_calls, usage

    async def _call_gemini_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> tuple[str, list[ToolCall], dict[str, int]]:
        url = GEMINI_URL.format(model=self.model)
        system_parts, contents = _gemini_contents(messages)
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": _to_gemini_tools(tools)}]
        payload["generationConfig"] = {"temperature": self.temperature, "maxOutputTokens": self.max_tokens}
        r = await self._client.post(url, json=payload, params={"key": self._api_key})
        r.raise_for_status()
        data = r.json()
        try:
            parts = data["candidates"][0]["content"].get("parts") or []
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Gemini response missing expected structure: {data}") from exc
        text = "".join(str(p.get("text", "")) for p in parts if "text" in p)
        tool_calls = [
            ToolCall(
                id=f"call_{index}_{p['functionCall'].get('name', 'tool')}",
                name=str(p["functionCall"].get("name", "")),
                arguments=dict(p["functionCall"].get("args") or {}),
            )
            for index, p in enumerate(parts)
            if "functionCall" in p and p["functionCall"].get("name")
        ]
        usage_raw = data.get("usageMetadata") or {}
        usage = {
            "input": int(usage_raw.get("promptTokenCount") or 0),
            "output": int(usage_raw.get("candidatesTokenCount") or 0),
        }
        return text, tool_calls, usage

    async def _stream_openai(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, base_url: str
    ) -> AsyncIterator[StreamEvent]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._wire_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        full_text: list[str] = []
        pending_fragments: dict[int, dict[str, str]] = {}
        usage = {"input": 0, "output": 0}

        async with self._client.stream("POST", base_url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:") :].strip()
                if not raw or raw == "[DONE]":
                    continue
                chunk = json.loads(raw)
                chunk_usage = chunk.get("usage") or {}
                if chunk_usage:
                    usage = {
                        "input": int(chunk_usage.get("prompt_tokens") or 0),
                        "output": int(chunk_usage.get("completion_tokens") or 0),
                    }
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    full_text.append(str(piece))
                    yield StreamEvent(kind="delta", text=str(piece))
                for fragment in delta.get("tool_calls") or []:
                    index = int(fragment.get("index") or 0)
                    slot = pending_fragments.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if fragment.get("id"):
                        slot["id"] = str(fragment["id"])
                    function = fragment.get("function") or {}
                    if function.get("name"):
                        slot["name"] += str(function["name"])
                    if function.get("arguments"):
                        slot["arguments"] += str(function["arguments"])

        tool_calls = [
            ToolCall(
                id=pending_fragments[i]["id"] or f"call_{i}",
                name=pending_fragments[i]["name"],
                arguments=_parse_tool_args(pending_fragments[i]["arguments"]),
            )
            for i in sorted(pending_fragments)
            if pending_fragments[i]["name"]
        ]
        yield StreamEvent(
            kind="final",
            result=LLMToolResult(
                text="".join(full_text),
                model=self.model,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                cost_usd=_price_usage(self.model, usage["input"], usage["output"]),
                tool_calls=tool_calls,
            ),
        )

    async def _stream_gemini(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> AsyncIterator[StreamEvent]:
        url = GEMINI_URL.format(model=self.model).replace(":generateContent", ":streamGenerateContent")
        system_parts, contents = _gemini_contents(messages)
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": _to_gemini_tools(tools)}]
        payload["generationConfig"] = {"temperature": self.temperature, "maxOutputTokens": self.max_tokens}

        full_text: list[str] = []
        tool_calls: list[ToolCall] = []
        usage = {"input": 0, "output": 0}
        call_index = 0

        async with self._client.stream(
            "POST", url, json=payload, params={"key": self._api_key, "alt": "sse"}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:") :].strip()
                if not raw:
                    continue
                chunk = json.loads(raw)
                chunk_usage = chunk.get("usageMetadata") or {}
                if chunk_usage:
                    usage = {
                        "input": int(chunk_usage.get("promptTokenCount") or 0),
                        "output": int(chunk_usage.get("candidatesTokenCount") or 0),
                    }
                for candidate in chunk.get("candidates") or []:
                    for part in (candidate.get("content") or {}).get("parts") or []:
                        if "text" in part:
                            piece = str(part["text"])
                            full_text.append(piece)
                            yield StreamEvent(kind="delta", text=piece)
                        elif "functionCall" in part:
                            call = part["functionCall"]
                            if call.get("name"):
                                tool_calls.append(
                                    ToolCall(
                                        id=f"call_{call_index}_{call['name']}",
                                        name=str(call["name"]),
                                        arguments=dict(call.get("args") or {}),
                                    )
                                )
                                call_index += 1

        yield StreamEvent(
            kind="final",
            result=LLMToolResult(
                text="".join(full_text),
                model=self.model,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                cost_usd=_price_usage(self.model, usage["input"], usage["output"]),
                tool_calls=tool_calls,
            ),
        )

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        try:
            if "```json" in text:
                data = json.loads(text.split("```json")[1].split("```")[0])
                return data if isinstance(data, dict) else None
            if "```" in text:
                data = json.loads(text.split("```")[1].split("```")[0])
                return data if isinstance(data, dict) else None
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, IndexError):
            return None


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    """Tolerant parse of tool-call arguments (JSON string or already-decoded)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _price_usage(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 0.15, "output": 0.60})
    return round(input_tokens / 1000 * pricing["input"] + output_tokens / 1000 * pricing["output"], 6)


def _gemini_contents(messages: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Internal messages -> (system parts, Gemini contents list)."""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content") or "")
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            if content:
                parts.append({"text": content})
            for tc in message.get("tool_calls") or []:
                parts.append({"functionCall": {"name": tc.get("name", ""), "args": tc.get("arguments") or {}}})
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            try:
                parsed = json.loads(content) if content else {}
            except json.JSONDecodeError:
                parsed = {"raw": content}
            response: dict[str, Any] = parsed if isinstance(parsed, dict) else {"result": parsed}
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message.get("tool_name", ""),
                                "response": response,
                            }
                        }
                    ],
                }
            )
    return system_parts, contents


def _to_gemini_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenAI tool schemas -> Gemini functionDeclarations (schema subset)."""
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function", tool)
        declaration: dict[str, Any] = {
            "name": str(function.get("name", "")),
            "description": str(function.get("description", "")),
        }
        parameters = function.get("parameters")
        if isinstance(parameters, dict):
            declaration["parameters"] = _clean_schema(parameters)
        declarations.append(declaration)
    return declarations


def _clean_schema(node: Any) -> Any:
    """Flatten a JSON schema to Gemini's supported subset: drop titles/$defs and
    unwrap ``anyOf`` nullability (optional fields are simply non-required)."""
    if isinstance(node, list):
        return [_clean_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    if "$ref" in node:
        target = str(node["$ref"]).split("/")[-1]
        defs = node.get("$defs") or node.get("definitions") or {}
        if isinstance(defs, dict) and target in defs:
            return _clean_schema(defs[target])

    if "anyOf" in node and isinstance(node["anyOf"], list):
        branches = [b for b in node["anyOf"] if isinstance(b, dict) and b.get("type") != "null"]
        if len(branches) == 1:
            return _clean_schema(branches[0])

    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in ("title", "$schema", "default", "$defs", "definitions"):
            continue
        cleaned[key] = _clean_schema(value)
    return cleaned
