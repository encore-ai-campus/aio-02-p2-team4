"""Provider-neutral requests and ordered LLM fallback policy.

Credentials stay in server-side provider objects. The adapters expose only
structured text and search citations to the stage modules; raw provider
responses never cross the API boundary.
"""

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Literal

import httpx
from schemas import MODEL_CATALOG, ModelPreference


ProviderKind = Literal["experiential", "openai", "gemini"]
Reasoning = Literal["max", "high"]
_MAX_RESPONSE_BYTES = 1_000_000
_SEARCH_TIMEOUT_SECONDS = 120
_EXPERIENTIAL_BASE_URL = "https://api.experientiallabs.ai/v1"
# OpenAI Fast-mode processing tier (service_tier). Priority-priced at 2x
# standard rates; the project must allow it or the API returns 400.
_SERVICE_TIER = "fast"


@dataclass(frozen=True, slots=True)
class LLMProvider:
    kind: ProviderKind
    model: str
    reasoning: Reasoning
    api_key: str


class ProviderCallError(RuntimeError):
    """A provider attempt failed and the next configured provider may retry."""


def openai_provider(api_key: str | None) -> LLMProvider:
    return LLMProvider("openai", "gpt-6-luna", "max", api_key or "")


def _secret_value(value: Any) -> str:
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return value.strip() if isinstance(value, str) else ""


def configured_providers(settings: Any) -> tuple[LLMProvider, ...]:
    """Return configured providers in the user-requested priority order."""
    openai_key = _secret_value(getattr(settings, "api_key", ""))
    gemini_key = _secret_value(getattr(settings, "gemini_api_key", ""))
    explabs_key = _secret_value(getattr(settings, "explabs_api_key", ""))
    providers: list[LLMProvider] = []
    if explabs_key:
        providers.append(LLMProvider("experiential", "deepseek-v4.1-flash", "max", explabs_key))
    if openai_key:
        providers.append(LLMProvider("openai", "gpt-6-luna", "max", openai_key))
    if gemini_key:
        providers.extend(
            [
                LLMProvider("gemini", "gemini-3.8-flash", "high", gemini_key),
                LLMProvider("gemini", "gemini-3.7-flash", "high", gemini_key),
            ]
        )
    return tuple(providers)


def providers_for_preference(
    settings: Any, preference: ModelPreference = "auto", *, search: bool = False
) -> tuple[LLMProvider, ...]:
    """Return the automatic chain or exactly one explicitly selected model."""
    providers = configured_providers(settings)
    if search:
        # DeepSeek does not supply the provider-native web-search tools.
        providers = tuple(provider for provider in providers if provider.kind != "experiential")
        if preference == "deepseek-v4.1-flash":
            preference = "auto"
    if preference == "auto":
        return providers
    selected = tuple(provider for provider in providers if provider.model == preference)
    if not selected:
        raise ValueError("MODEL_UNAVAILABLE")
    return selected


def configured_model_options(settings: Any) -> list[dict[str, Any]]:
    configured = {provider.model for provider in configured_providers(settings)}
    return [
        {"id": model_id, "label": label, "configured": model_id in configured}
        for model_id, label in MODEL_CATALOG
    ]


async def run_with_fallback(
    providers: tuple[LLMProvider, ...],
    operation: Callable[[LLMProvider], Awaitable[Any]],
) -> tuple[Any, LLMProvider]:
    """Run an operation in priority order and return its result and provider."""
    last_error: ProviderCallError | None = None
    for provider in providers:
        try:
            return await operation(provider), provider
        except ProviderCallError as exc:
            last_error = exc
    raise last_error or ProviderCallError("No provider is configured")


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove JSON Schema keywords unsupported by Gemini structured output."""
    unsupported = {
        "default",
        "examples",
        "maxLength",
        "minLength",
        "pattern",
        "title",
    }

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in unsupported
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(deepcopy(schema))


def _openai_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize Pydantic schemas for OpenAI strict structured output."""

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            normalized = {
                key: clean(item)
                for key, item in value.items()
                if key != "default"
            }
            properties = normalized.get("properties")
            if isinstance(properties, dict):
                # OpenAI strict mode does not support optional object keys.
                # Nullable values remain nullable, but every property is required.
                normalized["required"] = list(properties)
            return normalized
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(deepcopy(schema))


def _endpoint_and_headers(provider: LLMProvider) -> tuple[str, dict[str, str]]:
    if provider.kind == "experiential":
        return (
            f"{_EXPERIENTIAL_BASE_URL}/chat/completions",
            {"Authorization": f"Bearer {provider.api_key}"},
        )
    if provider.kind == "openai":
        return (
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {provider.api_key}"},
        )
    return (
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        {"x-goog-api-key": provider.api_key},
    )


def _structured_payload(
    provider: LLMProvider,
    *,
    instructions: str,
    input_data: dict[str, Any],
    schema: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    serialized_input = json.dumps(input_data, ensure_ascii=False)
    if provider.kind == "experiential":
        return {
            "model": provider.model,
            "reasoning_effort": provider.reasoning,
            "store": False,
            # Leave room for final JSON after MAX reasoning consumes tokens.
            "max_tokens": max(16_000, max_output_tokens),
            "messages": [
                {"role": "system", "content": instructions + "\nReturn only a JSON object matching this schema: " + json.dumps(schema, ensure_ascii=False)},
                {"role": "user", "content": serialized_input},
            ],
            "response_format": {"type": "json_object"},
        }
    if provider.kind == "openai":
        return {
            "model": provider.model,
            "reasoning": {"effort": provider.reasoning},
            "service_tier": _SERVICE_TIER,
            "store": False,
            "max_output_tokens": max_output_tokens,
            "instructions": instructions,
            "input": serialized_input,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "structured_result",
                    "strict": True,
                    "schema": _openai_schema(schema),
                }
            },
        }
    return {
        "model": provider.model,
        "system_instruction": instructions,
        "input": serialized_input,
        "store": False,
        "generation_config": {
            "max_output_tokens": max_output_tokens,
            "thinking_level": provider.reasoning,
            "thinking_summaries": "none",
        },
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": _gemini_schema(schema),
        },
    }


def _search_payload(
    provider: LLMProvider,
    *,
    instructions: str,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    serialized_input = json.dumps(input_data, ensure_ascii=False)
    if provider.kind == "openai":
        web_search: dict[str, Any] = {"type": "web_search", "search_context_size": "medium"}
        primary_queries = input_data.get("primaryQueries", [])
        if isinstance(primary_queries, list) and any(
            isinstance(query, str) and any("가" <= char <= "힣" for char in query)
            for query in primary_queries
        ):
            web_search["user_location"] = {"type": "approximate", "country": "KR"}
        return {
            "model": provider.model,
            "reasoning": {"effort": provider.reasoning},
            "service_tier": _SERVICE_TIER,
            "store": False,
            "max_output_tokens": 6000,
            "instructions": instructions,
            "input": serialized_input,
            "tools": [web_search],
            "tool_choice": "required",
            # Run several targeted search passes so one publisher cannot fill
            # the entire candidate set before the diversity selector sees it.
            "max_tool_calls": 4,
            "include": ["web_search_call.action.sources"],
        }
    return {
        "model": provider.model,
        "system_instruction": instructions,
        "input": serialized_input,
        "store": False,
        "tools": [{"type": "google_search"}],
        "generation_config": {
            "max_output_tokens": 6000,
            "thinking_level": provider.reasoning,
            "thinking_summaries": "none",
            "tool_choice": "any",
        },
    }


def _response_json(response: httpx.Response, *, chat_completion: bool = False) -> dict[str, Any]:
    response.raise_for_status()
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise ProviderCallError("Response too large")
    data = response.json()
    if not isinstance(data, dict):
        raise ProviderCallError("Invalid response")
    if not chat_completion and data.get("status") != "completed":
        raise ProviderCallError("Incomplete response")
    return data


def _experiential_text(data: dict[str, Any]) -> str:
    """Keep final JSON only; never treat reasoning or partial output as an answer."""
    ignored = data.get("x-experiential-ignored-parameters", [])
    if "reasoning_effort" in ignored or "reasoning" in ignored:
        raise ProviderCallError("Requested reasoning was not honored")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProviderCallError("Invalid structured response")
    choice = choices[0]
    message = choice.get("message")
    if choice.get("finish_reason") != "stop" or not isinstance(message, dict):
        raise ProviderCallError("Incomplete response")
    text = message.get("content")
    if message.get("refusal") or message.get("tool_calls") or not isinstance(text, str) or not text.strip():
        raise ProviderCallError("Invalid structured response")
    return text


def _openai_text(data: dict[str, Any]) -> str:
    parts = [
        part
        for item in data.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
    ]
    if any(part.get("type") == "refusal" for part in parts):
        raise ProviderCallError("Refusal")
    texts = [part.get("text") for part in parts if part.get("type") == "output_text"]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise ProviderCallError("Invalid structured response")
    return texts[0]


def _gemini_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    texts: list[str] = []
    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for content in step.get("content", []):
            if content.get("type") == "text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
    if len(texts) != 1:
        raise ProviderCallError("Invalid structured response")
    return texts[0]


async def request_structured(
    provider: LLMProvider,
    client: httpx.AsyncClient,
    *,
    instructions: str,
    input_data: dict[str, Any],
    schema: dict[str, Any],
    max_output_tokens: int,
    timeout_seconds: float = 90,
) -> str:
    """Call a provider's structured-output endpoint and return only model text."""
    if not provider.api_key.strip():
        raise ProviderCallError("Missing provider key")
    endpoint, headers = _endpoint_and_headers(provider)
    payload = _structured_payload(
        provider,
        instructions=instructions,
        input_data=input_data,
        schema=schema,
        max_output_tokens=max_output_tokens,
    )
    try:
        response = await client.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
        data = _response_json(response, chat_completion=provider.kind == "experiential")
        if provider.kind == "experiential":
            return _experiential_text(data)
        return _openai_text(data) if provider.kind == "openai" else _gemini_text(data)
    except ProviderCallError:
        raise
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise ProviderCallError("Provider request failed") from exc


_IMAGE_MIMES = ("image/jpeg", "image/png", "image/webp")
_MAX_IMAGE_DATA = 20_000_000


def _structured_image_input(
    provider: LLMProvider,
    serialized_input: str,
    image: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the multimodal input parts for each provider's wire format."""
    if provider.kind == "experiential":
        return [
            {"type": "text", "text": serialized_input},
            {"type": "image_url", "image_url": {"url": f"data:{image['mime']};base64,{image['data']}"}},
        ]
    if provider.kind == "openai":
        return [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": serialized_input},
                {
                    "type": "input_image",
                    "image_url": f"data:{image['mime']};base64,{image['data']}",
                },
            ],
        }]
    return [
        {"type": "text", "text": serialized_input},
        {"type": "image", "data": image["data"], "mime_type": image["mime"]},
    ]


async def request_structured_image(
    provider: LLMProvider,
    client: httpx.AsyncClient,
    *,
    instructions: str,
    input_data: dict[str, Any],
    image: dict[str, Any],
    schema: dict[str, Any],
    max_output_tokens: int,
) -> str:
    """Call a provider's structured-output endpoint with an attached image."""
    if not provider.api_key.strip():
        raise ProviderCallError("Missing provider key")
    if (
        not isinstance(image, dict)
        or image.get("mime") not in _IMAGE_MIMES
        or not isinstance(image.get("data"), str)
        or not image["data"]
        or len(image["data"]) > _MAX_IMAGE_DATA
    ):
        raise ProviderCallError("Invalid image attachment")
    endpoint, headers = _endpoint_and_headers(provider)
    payload = _structured_payload(
        provider,
        instructions=instructions,
        input_data=input_data,
        schema=schema,
        max_output_tokens=max_output_tokens,
    )
    image_input = _structured_image_input(
        provider, json.dumps(input_data, ensure_ascii=False), image
    )
    if provider.kind == "experiential":
        payload["messages"][1]["content"] = image_input
    else:
        payload["input"] = image_input
    try:
        response = await client.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=90,
        )
        data = _response_json(response, chat_completion=provider.kind == "experiential")
        if provider.kind == "experiential":
            return _experiential_text(data)
        return _openai_text(data) if provider.kind == "openai" else _gemini_text(data)
    except ProviderCallError:
        raise
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise ProviderCallError("Provider request failed") from exc


async def request_search(
    provider: LLMProvider,
    client: httpx.AsyncClient,
    *,
    instructions: str,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """Call a provider's search-grounded endpoint with a bounded response."""
    if provider.kind == "experiential":
        raise ProviderCallError("Provider-native web search is unavailable")
    if not provider.api_key.strip():
        raise ProviderCallError("Missing provider key")
    endpoint, headers = _endpoint_and_headers(provider)
    payload = _search_payload(provider, instructions=instructions, input_data=input_data)
    try:
        async with client.stream(
            "POST",
            endpoint,
            json=payload,
            headers=headers,
            timeout=_SEARCH_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise ProviderCallError("Response too large")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ProviderCallError("Incomplete search response")
        incomplete_details = data.get("incomplete_details")
        output = data.get("output")
        has_completed_search = isinstance(output, list) and any(
            isinstance(item, dict)
            and item.get("type") == "web_search_call"
            and item.get("status") == "completed"
            for item in output
        )
        usable_partial_search = (
            provider.kind == "openai"
            and data.get("status") == "incomplete"
            and isinstance(incomplete_details, dict)
            and incomplete_details.get("reason") in {"max_output_tokens", "max_tokens"}
            and has_completed_search
        )
        if data.get("status") != "completed" and not usable_partial_search:
            raise ProviderCallError("Incomplete search response")
        return data
    except ProviderCallError:
        raise
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise ProviderCallError("Provider search failed") from exc


def search_candidates(data: dict[str, Any], provider: LLMProvider) -> list[dict[str, Any]]:
    """Project provider search output to candidate URL annotations."""
    candidates: list[dict[str, Any]] = []
    if provider.kind == "openai":
        calls = [
            item
            for item in data.get("output", [])
            if item.get("type") == "web_search_call" and item.get("status") == "completed"
        ]
        if not calls:
            raise ProviderCallError("Search not completed")
        for item in calls:
            candidates.extend(item.get("action", {}).get("sources", []))
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "refusal":
                    raise ProviderCallError("Refusal")
                candidates.extend(
                    annotation
                    for annotation in part.get("annotations", [])
                    if annotation.get("type") == "url_citation"
                )
        return candidates

    calls = [step for step in data.get("steps", []) if step.get("type") == "google_search_call"]
    if not calls:
        raise ProviderCallError("Google Search was not used")
    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for content in step.get("content", []):
            candidates.extend(
                annotation
                for annotation in content.get("annotations", [])
                if annotation.get("type") == "url_citation"
            )
    return candidates
