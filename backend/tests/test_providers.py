"""Provider priority and fallback policy tests; no network traffic."""

import asyncio

import pytest
from pydantic import SecretStr


def test_configured_provider_chain_is_ordered_and_skips_missing_keys():
    from providers import configured_providers
    from runtime import Settings

    providers = configured_providers(
        Settings(
            api_key=SecretStr("openai-test-only"),
            gemini_api_key=SecretStr("gemini-test-only"),
        )
    )

    assert [(provider.kind, provider.model, provider.reasoning) for provider in providers] == [
        ("openai", "gpt-6-luna", "max"),
        ("gemini", "gemini-3.8-flash", "high"),
        ("gemini", "gemini-3.7-flash", "high"),
    ]

    only_gemini = configured_providers(
        Settings(api_key=SecretStr(""), gemini_api_key=SecretStr("gemini-test-only"))
    )
    assert [provider.model for provider in only_gemini] == [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
    ]


def test_explicit_provider_preference_pins_one_configured_model():
    from providers import providers_for_preference
    from runtime import Settings

    providers = providers_for_preference(
        Settings(
            api_key=SecretStr("openai-test-only"),
            gemini_api_key=SecretStr("gemini-test-only"),
        ),
        "gpt-6-luna",
    )

    assert [provider.model for provider in providers] == ["gpt-6-luna"]


def test_explicit_provider_preference_rejects_unconfigured_model():
    from providers import providers_for_preference
    from runtime import Settings

    with pytest.raises(ValueError, match="MODEL_UNAVAILABLE"):
        providers_for_preference(
            Settings(api_key=SecretStr(""), gemini_api_key=SecretStr("gemini-test-only")),
            "gpt-6-luna",
        )


def test_run_with_fallback_tries_next_provider_after_failure():
    from providers import LLMProvider, ProviderCallError, run_with_fallback

    providers = (
        LLMProvider("gemini", "gemini-3.8-flash", "high", "test-gemini"),
        LLMProvider("gemini", "gemini-3.7-flash", "high", "test-gemini"),
    )
    attempts = []

    async def operation(provider):
        attempts.append(provider.model)
        if provider.model == "gemini-3.8-flash":
            raise ProviderCallError("provider failed")
        return {"ok": True}

    result = asyncio.run(run_with_fallback(providers, operation))

    assert result == ({"ok": True}, providers[1])
    assert attempts == ["gemini-3.8-flash", "gemini-3.7-flash"]


def test_run_with_fallback_reaches_third_provider_when_first_two_fail():
    from providers import LLMProvider, ProviderCallError, run_with_fallback

    providers = (
        LLMProvider("gemini", "gemini-3.8-flash", "high", "test-gemini"),
        LLMProvider("gemini", "gemini-3.7-flash", "high", "test-gemini"),
        LLMProvider("openai", "gpt-6-luna", "max", "test-openai"),
    )
    attempts = []

    async def operation(provider):
        attempts.append(provider.model)
        if provider.model != "gpt-6-luna":
            raise ProviderCallError("provider failed")
        return {"ok": True}

    result = asyncio.run(run_with_fallback(providers, operation))

    assert result == ({"ok": True}, providers[2])
    assert attempts == [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gpt-6-luna",
    ]


def test_openai_structured_schema_requires_defaulted_properties_too():
    from providers import LLMProvider, _structured_payload
    from verification import JudgmentResponse

    schema = JudgmentResponse.model_json_schema()
    payload = _structured_payload(
        LLMProvider("openai", "gpt-6-luna", "max", "test-only"),
        instructions="test",
        input_data={},
        schema=schema,
        max_output_tokens=100,
    )
    judgment_schema = payload["text"]["format"]["schema"]["$defs"]["Judgment"]

    assert set(judgment_schema["required"]) == set(judgment_schema["properties"])
    assert "default" not in judgment_schema["properties"]["factScore"]


def test_openai_payloads_request_fast_service_tier():
    from providers import LLMProvider, _search_payload, _structured_payload
    from verification import JudgmentResponse

    provider = LLMProvider("openai", "gpt-6-luna", "max", "test-only")
    structured = _structured_payload(
        provider,
        instructions="test",
        input_data={},
        schema=JudgmentResponse.model_json_schema(),
        max_output_tokens=100,
    )
    search = _search_payload(
        provider, instructions="test", input_data={"primaryQueries": []}
    )
    assert structured["service_tier"] == "fast"
    assert search["service_tier"] == "fast"


def test_runtime_stage_retries_next_provider_after_adapter_failure(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    attempts = []

    async def fake_extract(state, *, client, provider):
        attempts.append(provider.model)
        if provider.model == "gpt-6-luna":
            raise ValueError("EXTRACTION_FAILED")
        return {"claims": [], "llmModel": provider.model}

    monkeypatch.setattr(runtime, "extract_claims", fake_extract)
    adapters = make_runtime_adapters(
        Settings(
            api_key=SecretStr("openai-test-only"),
            gemini_api_key=SecretStr("gemini-test-only"),
        )
    )

    result = asyncio.run(
        adapters.extract({"text": "claim", "focus": "", "consent": True})
    )

    assert attempts == ["gpt-6-luna", "gemini-3.8-flash"]
    assert result["llmModel"] == "gemini-3.8-flash"


def test_runtime_stage_keeps_explicit_provider_selection_pinned_after_failure(monkeypatch):
    import pytest
    import runtime
    from runtime import Settings, make_runtime_adapters

    attempts = []

    async def fake_extract(state, *, client, provider):
        attempts.append(provider.model)
        raise ValueError("EXTRACTION_FAILED")

    monkeypatch.setattr(runtime, "extract_claims", fake_extract)
    adapters = make_runtime_adapters(
        Settings(
            api_key=SecretStr("openai-test-only"),
            gemini_api_key=SecretStr("gemini-test-only"),
        )
    )

    with pytest.raises(ValueError, match="MODEL_FAILED"):
        asyncio.run(adapters.extract({
            "text": "claim", "focus": "", "consent": True,
            "modelPreference": "gpt-6-luna",
        }))

    assert attempts == ["gpt-6-luna"]
