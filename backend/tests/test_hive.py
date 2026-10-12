"""Hive routing boundaries; synthetic credentials and no network calls."""
import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from providers import LLMProvider, ProviderCallError, configured_providers, providers_for_preference, request_search, request_structured, request_structured_image, run_with_fallback
from runtime import Settings, load_settings


def settings():
    return Settings(api_key=SecretStr('openai-test-only'), gemini_api_key=SecretStr('gemini-test-only'), hive_api_key=SecretStr('hive-test-only'))


def test_gateway_key_loads_from_file_then_environment_and_is_redacted(tmp_path, monkeypatch):
    monkeypatch.delenv('HIVE_API_KEY', raising=False)
    path = tmp_path / '.env'
    path.write_text('HIVE_API_KEY=gateway-file-test-only\n', encoding='utf-8')
    value = load_settings(path)
    assert value.hive_api_key.get_secret_value() == 'gateway-file-test-only'
    assert 'gateway-file-test-only' not in repr(value)
    monkeypatch.setenv('HIVE_API_KEY', 'gateway-process-test-only')
    assert load_settings(path).hive_api_key.get_secret_value() == 'gateway-process-test-only'


def test_auto_tries_deepseek_first_then_preserves_all_existing_models():
    providers = configured_providers(settings())
    attempts = []

    async def attempt(provider):
        attempts.append((provider.model, provider.reasoning))
        if provider.model != 'gemini-3.7-flash':
            raise ProviderCallError('synthetic failure')
        return 'final'

    result, used = asyncio.run(run_with_fallback(providers, attempt))
    assert attempts == [('deepseek-v4.1-flash', 'max'), ('gpt-6-luna', 'max'), ('gemini-3.8-flash', 'high'), ('gemini-3.7-flash', 'high')]
    assert result == 'final' and used.model == 'gemini-3.7-flash'
    assert providers[0].api_key == 'hive-test-only'


def test_deepseek_selection_pins_it_and_missing_key_rejects_selection():
    assert [p.model for p in providers_for_preference(settings(), 'deepseek-v4.1-flash')] == ['deepseek-v4.1-flash']
    with pytest.raises(ValueError, match='MODEL_UNAVAILABLE'):
        providers_for_preference(Settings(api_key=SecretStr('openai-test-only')), 'deepseek-v4.1-flash')


def test_deepseek_search_uses_existing_native_tools_not_generated_urls():
    providers = providers_for_preference(settings(), 'deepseek-v4.1-flash', search=True)
    assert [p.model for p in providers] == ['gpt-6-luna', 'gemini-3.8-flash', 'gemini-3.7-flash']
    assert [p.model for p in providers_for_preference(settings(), 'gemini-3.8-flash', search=True)] == ['gemini-3.8-flash']


def completion(content='{"reply":"연결 확인"}', **extra):
    return {'id': 'chatcmpl-test', 'object': 'chat.completion', 'model': 'deepseek-ai/deepseek-v4.1-flash',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': content}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}, **extra}


def call(response, *, image=None, max_output_tokens=400):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json=response)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            kwargs = dict(instructions='Return a JSON reply.', input_data={'text': '합성 입력'},
                          schema={'type': 'object', 'properties': {'reply': {'type': 'string'}}, 'required': ['reply'], 'additionalProperties': False}, max_output_tokens=max_output_tokens)
            provider = LLMProvider('hive', 'deepseek-v4.1-flash', 'max', 'gateway-test-only')
            if image is not None:
                return await request_structured_image(provider, client, image=image, **kwargs)
            return await request_structured(provider, client, **kwargs)

    return asyncio.run(run()), seen


def test_structured_call_uses_gateway_max_json_mode_and_only_gateway_credential():
    raw, seen = call(completion())
    assert json.loads(raw) == {'reply': '연결 확인'}
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == 'https://api-cdn.thehive.ai/api/v3/chat/completions'
    assert request.headers['Authorization'] == 'Bearer gateway-test-only'
    assert 'x-goog-api-key' not in request.headers
    body = json.loads(request.content)
    assert body['model'] == 'deepseek-ai/deepseek-v4.1-flash'
    assert body['reasoning_effort'] == 'max'
    assert body['response_format'] == {'type': 'json_object'}
    assert body['max_completion_tokens'] == 16000
    assert 'store' not in body
    assert 'service_tier' not in body and 'input' not in body and 'tools' not in body
    assert '"required": ["reply"]' in body['messages'][0]['content']
    assert json.loads(body['messages'][1]['content']) == {'text': '합성 입력'}


@pytest.mark.parametrize('requested,expected', [(400, 16000), (4000, 16000), (12000, 16000), (20000, 20000)])
@pytest.mark.parametrize('image', [None, {'mime': 'image/png', 'data': 'dGVzdA=='}])
def test_max_reasoning_budget_has_room_for_final_json_and_preserves_larger_requests(requested, expected, image):
    raw, seen = call(completion(), image=image, max_output_tokens=requested)
    assert json.loads(raw)['reply'] == '연결 확인'
    body = json.loads(seen[0].content)
    assert body['max_completion_tokens'] == expected
    assert body['reasoning_effort'] == 'max'


def test_image_uses_chat_completions_multimodal_message_without_responses_input():
    raw, seen = call(completion(), image={'mime': 'image/png', 'data': 'dGVzdA=='})
    assert json.loads(raw)['reply'] == '연결 확인'
    body = json.loads(seen[0].content)
    assert 'input' not in body
    assert body['messages'][1]['content'] == [
        {'type': 'text', 'text': '{"text": "합성 입력"}'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,dGVzdA=='}},
    ]


@pytest.mark.parametrize('data', [
    {}, {'choices': []},
    {'choices': [{'finish_reason': 'length', 'message': {'content': '{"reply":"partial"}'}}]},
    {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None, 'tool_calls': []}}]},
    {'choices': [{'finish_reason': 'stop', 'message': {'content': '', 'reasoning_content': 'not an answer'}}]},
    {'choices': [{'finish_reason': 'stop', 'message': {'content': '{}', 'refusal': 'refused'}}]},
])
def test_incomplete_refused_or_ignored_max_responses_fail_closed(data):
    with pytest.raises(ProviderCallError):
        call(data)


def test_gateway_never_sends_native_openai_or_gemini_search_tools():
    async def run():
        def fail(request):
            pytest.fail('Unsupported web search must not send a paid gateway request')
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(ProviderCallError):
                await request_search(LLMProvider('hive', 'deepseek-v4.1-flash', 'max', 'test-only'), client, instructions='search', input_data={})
    asyncio.run(run())


def test_intent_invalid_json_schema_falls_back_to_existing_provider():
    from intent import classify_intent
    attempted = []

    def handle(request):
        body = json.loads(request.content)
        attempted.append(body['model'])
        if body['model'] == 'deepseek-ai/deepseek-v4.1-flash':
            return httpx.Response(200, json=completion('{"action":"unsafe"}'))
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"action":"reply","reply":"안녕하세요","focus":""}'}]}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await run_with_fallback(configured_providers(settings()), lambda provider: classify_intent('하이', {}, client=client, provider=provider))
    value, used = asyncio.run(run())
    assert attempted == ['deepseek-ai/deepseek-v4.1-flash', 'gpt-6-luna']
    assert value['reply'] == '안녕하세요' and used.model == 'gpt-6-luna'


def test_deepseek_model_is_accepted_at_request_contract():
    from schemas import FactCheckRequest
    assert FactCheckRequest(text='합성 주장', focus='', consent=True, modelPreference='deepseek-v4.1-flash').modelPreference == 'deepseek-v4.1-flash'


def test_status_does_not_claim_native_search_for_deepseek_only(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, 'load_settings', lambda: Settings(api_key=SecretStr(''), hive_api_key=SecretStr('gateway-test-only')))
    with TestClient(main.app) as client:
        value = client.get('/api/fact-check').json()
    assert value['model'] == 'deepseek-v4.1-flash' and value['reasoning'] == 'max'
    assert value['modelOptions'][0]['configured'] is True
    assert value['webSearch'] is False
