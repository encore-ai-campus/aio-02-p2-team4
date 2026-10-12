"""인증 거절을 실제 의도 분류 경로에서 재현하며 외부 호출은 하지 않습니다."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from runtime import Settings, _http_status_from_exception
from providers import LLMProvider, ProviderCallError, request_structured


@pytest.mark.parametrize('status,code', [(401, 'PROVIDER_AUTH_FAILED'), (403, 'PROVIDER_AUTH_FAILED'), (500, 'AGENT_FAILED')])
@pytest.mark.parametrize('image', [None, {'mime': 'image/png', 'data': 'aW1hZ2U='}])
def test_intent_reports_authentication_rejection_without_exposing_provider_body(monkeypatch, status, code, image):
    real_client = httpx.AsyncClient
    attempts = []

    def handle(request):
        attempts.append(request.url.host)
        return httpx.Response(status, json={'message': 'Invalid or expired token gateway-test-only'})

    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda *args, **kwargs: real_client(
        *args, transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(main, 'load_settings', lambda: Settings(
        api_key=SecretStr('openai-test-only'), hive_api_key=SecretStr('gateway-test-only')))
    with TestClient(main.app) as client:
        response = client.post('/api/intent', json={
            'text': '2024년 한국 합계출산율은 0.75명이다.', 'consent': True,
            'modelPreference': 'deepseek-v4.1-flash', 'image': image,
        })
    assert response.status_code == 502
    assert response.json()['code'] == code
    assert 'gateway-test-only' not in response.text
    assert 'Invalid or expired token' not in response.text
    assert attempts == ['api-cdn.thehive.ai']


def test_auto_can_recover_after_authentication_rejection(monkeypatch):
    real_client = httpx.AsyncClient
    attempts = []

    def handle(request):
        attempts.append(request.url.host)
        if request.url.host == 'api-cdn.thehive.ai':
            return httpx.Response(401, json={'message': 'Invalid or expired token'})
        return httpx.Response(200, json={'status': 'completed', 'output': [{
            'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'action': 'verify'})}],
        }]})

    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda *args, **kwargs: real_client(
        *args, transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(main, 'load_settings', lambda: Settings(
        api_key=SecretStr('openai-test-only'), hive_api_key=SecretStr('gateway-test-only')))
    with TestClient(main.app) as client:
        response = client.post('/api/intent', json={
            'text': '2024년 한국 합계출산율은 0.75명이다.', 'consent': True, 'modelPreference': 'auto',
        })
    assert response.status_code == 200
    assert response.json()['action'] == 'verify'
    assert attempts == ['api-cdn.thehive.ai', 'api.openai.com']


@pytest.mark.parametrize('status', [401, 403])
def test_authentication_error_preserves_http_status_for_existing_diagnostics(status):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={'message': 'Invalid or expired token'}))) as client:
            try:
                await request_structured(LLMProvider('hive', 'deepseek-v4.1-flash', 'max', 'test-only'), client,
                    instructions='Return JSON.', input_data={'text': 'public claim'}, schema={'type': 'object'}, max_output_tokens=400)
            except ProviderCallError as exc:
                return _http_status_from_exception(exc)

    assert asyncio.run(run()) == status
