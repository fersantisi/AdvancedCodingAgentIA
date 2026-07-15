"""OpenAI implementation of the ``LLMClient`` contract.

This is the only module in the project that imports the ``openai`` SDK.
It translates between the provider-neutral models and the OpenAI
Chat Completions format in both directions.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import openai

from coding_agent.llm.base import LLMClient, LLMError
from coding_agent.models import AssistantTurn, Message, Role, ToolCall, ToolSpec

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    """Talks to the OpenAI Chat Completions API with native tool calling."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> AssistantTurn:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [_to_openai_message(message) for message in messages],
        }
        if tools:
            request["tools"] = [_to_openai_tool(tool) for tool in tools]

        logger.debug("LLM request: %d messages, %d tools", len(messages), len(tools))
        try:
            response = self._client.chat.completions.create(**request)
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise LLMError(f"Could not reach OpenAI: {exc}", retryable=True) from exc
        except openai.RateLimitError as exc:
            raise LLMError(f"OpenAI rate limit hit: {exc}", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise LLMError(
                f"OpenAI returned HTTP {exc.status_code}: {exc.message}",
                retryable=exc.status_code >= 500,
            ) from exc
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        return _parse_response(response)


def _to_openai_message(message: Message) -> dict[str, Any]:
    if message.role is Role.TOOL:
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }

    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["content"] = message.content or None
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return payload


def _to_openai_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_response(response: Any) -> AssistantTurn:
    if not response.choices:
        raise LLMError("OpenAI returned an empty response", retryable=True)

    message = response.choices[0].message
    tool_calls = tuple(
        ToolCall(id=call.id, name=call.function.name, arguments=_parse_arguments(call))
        for call in (message.tool_calls or ())
    )
    logger.debug(
        "LLM response: text=%s, tool_calls=%s",
        bool(message.content),
        [call.name for call in tool_calls],
    )
    return AssistantTurn(text=message.content, tool_calls=tool_calls)


def _parse_arguments(call: Any) -> dict[str, Any]:
    raw = call.function.arguments or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(
            f"Model returned malformed JSON arguments for tool '{call.function.name}'",
            retryable=True,
        ) from exc
    if not isinstance(parsed, dict):
        raise LLMError(
            f"Model returned non-object arguments for tool '{call.function.name}'",
            retryable=True,
        )
    return parsed
