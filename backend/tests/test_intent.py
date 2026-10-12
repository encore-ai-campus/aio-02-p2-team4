"""Intent gate tests; no external traffic (all transports mocked)."""
import asyncio
import json

import httpx
import pytest


def decision_response(decision):
    return httpx.Response(200, json={
        "status": "completed",
        "steps": [{
            "type": "model_output",
            "content": [{"type": "text", "text": json.dumps(decision, ensure_ascii=False)}],
        }],
    })


def test_intent_verify_passes_focus_through(monkeypatch):
    import intent
    from providers import LLMProvider

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: decision_response(
                    {"action": "verify", "reply": "", "focus": "그럼 검색해서 찾아"}))
        ) as client:
            return await intent.classify_intent(
                "그럼 검색해서 찾아", {"previousText": "기사 원문"},
                client=client,
                provider=LLMProvider("gemini", "gemini-3.8-flash", "high", "k"),
            )

    assert asyncio.run(run()) == {
        "action": "verify", "target": "current", "reply": None, "focus": "그럼 검색해서 찾아"}


def test_intent_reply_requires_text():
    import intent
    from providers import LLMProvider, ProviderCallError

    async def run_empty():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: decision_response({"action": "reply", "reply": "  ", "focus": ""}))
        ) as client:
            return await intent.classify_intent(
                "하이", {}, client=client,
                provider=LLMProvider("gemini", "gemini-3.8-flash", "high", "k"))

    with pytest.raises(ProviderCallError):
        asyncio.run(run_empty())

    async def run_reply():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={
                    "status": "completed",
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps(
                                {"action": "reply", "reply": "안녕!", "focus": ""},
                                ensure_ascii=False),
                        }],
                    }],
                }))
        ) as client:
            return await intent.classify_intent(
                "하이", {}, client=client,
                provider=LLMProvider("openai", "gpt-6-luna", "max", "k"))

    assert asyncio.run(run_reply()) == {"action": "reply", "target": "current", "reply": "안녕!", "focus": None}


def test_intent_endpoint_rejects_bad_payloads_and_reports_unconfigured(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings
    import main
    from main import app

    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(api_key=SecretStr(""), gemini_api_key=SecretStr("")),
    )
    with TestClient(app) as client:
        assert client.post("/api/intent", json={"consent": True}).status_code == 422
        assert client.post("/api/intent", json={"text": "", "consent": True}).status_code == 422
        assert client.post(
            "/api/intent", json={"text": "하이", "consent": True, "context": {"previousText": 1}}).status_code == 422
        assert client.post(
            "/api/intent", json={"text": "하이", "consent": True, "modelPreference": "nope"}).status_code == 422
        unconfigured = client.post("/api/intent", json={"text": "하이", "consent": True})
        assert unconfigured.status_code == 503


def test_intent_endpoint_uses_selected_model(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from main import app
    from pydantic import SecretStr
    from runtime import Settings
    import runtime

    real_async_client = httpx.AsyncClient
    hits: list[str] = []

    def handler(request):
        hits.append(request.url.host + request.url.path)
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json={
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": json.dumps(
                            {"action": "reply", "reply": "hi", "focus": ""},
                            ensure_ascii=False),
                    }],
                }],
            })
        return decision_response({"action": "reply", "reply": "hi", "focus": ""})

    def mock_client(*args, **kwargs):
        return real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(main.httpx, "AsyncClient", mock_client)
    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(api_key=SecretStr("openai-test-only"), gemini_api_key=SecretStr("gemini-test-only")),
    )
    with TestClient(app) as client:
        response = client.post("/api/intent", json={
            "text": "하이", "modelPreference": "gpt-6-luna", "consent": True,
        })
        assert response.status_code == 200
        assert response.json() == {"action": "reply", "target": "current", "reply": "hi", "focus": None}
        assert hits == ["api.openai.com/v1/responses"]
        picked = client.post("/api/intent", json={
            "text": "하이", "modelPreference": "gemini-3.7-flash", "consent": True,
        })
        assert picked.status_code == 200
        assert picked.json() == {"action": "reply", "target": "current", "reply": "hi", "focus": None}
        assert hits[-1] == "generativelanguage.googleapis.com/v1beta/interactions"


def test_intent_endpoint_reports_missing_selected_model(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from main import app
    from pydantic import SecretStr
    from runtime import Settings

    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(api_key=SecretStr("openai-test-only"), gemini_api_key=SecretStr("")),
    )
    with TestClient(app) as client:
        missing = client.post("/api/intent", json={
            "text": "하이", "modelPreference": "gemini-3.7-flash", "consent": True,
        })
        assert missing.status_code == 503


def test_intent_can_clarify_instead_of_starting_verification():
    import intent
    from providers import LLMProvider

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: decision_response({
                'action': 'clarify', 'target': 'current',
                'reply': '내용 설명과 사실 검증 중 어떤 작업을 원하시나요?', 'focus': '',
            })
        )) as client:
            return await intent.classify_intent('이거 봐줘', {}, client=client,
                provider=LLMProvider('gemini', 'gemini-3.8-flash', 'high', 'test-only'))

    assert asyncio.run(run()) == {
        'action': 'clarify', 'target': 'current',
        'reply': '내용 설명과 사실 검증 중 어떤 작업을 원하시나요?', 'focus': None,
    }


def test_intent_preserves_model_selected_previous_target_without_demonstrative():
    import intent
    from providers import LLMProvider

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: decision_response({
                'action': 'verify', 'target': 'previous', 'reply': '', 'focus': '다시 검색해줘',
            })
        )) as client:
            return await intent.classify_intent('다시 검색해줘', {'previousText': '이전 원문'},
                client=client, provider=LLMProvider('gemini', 'gemini-3.8-flash', 'high', 'test-only'))

    assert asyncio.run(run()) == {
        'action': 'verify', 'target': 'previous', 'reply': None, 'focus': '다시 검색해줘',
    }


def test_intent_endpoint_explains_image_with_failure_context_in_one_model_call(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings

    hits = []
    real_async_client = httpx.AsyncClient

    def handler(request):
        payload = json.loads(request.content)
        hits.append(payload)
        return httpx.Response(200, json={
            'status': 'completed', 'output': [{'type': 'message', 'content': [{
                'type': 'output_text', 'text': json.dumps({
                    'action': 'reply', 'target': 'current', 'reply': '이미지에는 요금제 비교표가 있습니다.', 'focus': '',
                }, ensure_ascii=False),
            }]}],
        })

    monkeypatch.setattr(main.httpx, 'AsyncClient',
        lambda *args, **kwargs: real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(main, 'load_settings', lambda: Settings(api_key=SecretStr('test-only')))
    with TestClient(main.app) as client:
        response = client.post('/api/intent', json={
            'text': '이게 뭐야?', 'focus': '', 'consent': True, 'modelPreference': 'gpt-6-luna',
            'image': {'mime': 'image/png', 'data': 'aW1hZ2U='},
            'context': {
                'recentAssistant': ['링크 원문을 읽지 못했습니다.'],
                'previousSources': [{'url': 'https://example.com/pricing', 'title': '요금제', 'accessStatus': 'unavailable'}],
                'previousWarnings': ['SOURCE_UNREADABLE'],
            },
        })
    assert response.status_code == 200
    assert response.json()['action'] == 'reply'
    assert len(hits) == 1
    parts = hits[0]['input'][0]['content']
    assert parts[1] == {'type': 'input_image', 'image_url': 'data:image/png;base64,aW1hZ2U='}
    context = json.loads(parts[0]['text'])['context']
    assert context['recentAssistant'] == ['링크 원문을 읽지 못했습니다.']
    assert context['previousWarnings'] == ['SOURCE_UNREADABLE']
    assert context['previousSources'][0]['accessStatus'] == 'unavailable'


def test_intent_endpoint_accepts_long_explanation_requests_and_link_metadata(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda *args, **kwargs: real_async_client(
        *args, transport=httpx.MockTransport(lambda request: decision_response({
            'action': 'reply', 'target': 'current', 'reply': '내용을 설명하겠습니다.', 'focus': '',
        })), **kwargs))
    monkeypatch.setattr(main, 'load_settings', lambda: Settings(api_key=SecretStr(''), gemini_api_key=SecretStr('test-only')))
    with TestClient(main.app) as client:
        response = client.post('/api/intent', json={
            'text': '설명이 필요한 원문입니다. ' * 250, 'consent': True,
            'linkUrl': 'https://example.com/article',
        })
    assert response.status_code == 200
    assert response.json()['action'] == 'reply'


def test_intent_marks_only_content_explanations_for_link_reading():
    import intent
    from providers import LLMProvider

    async def run(decision):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: decision_response(decision))) as client:
            return await intent.classify_intent('링크 질문', {}, link_url='https://example.com/article',
                client=client, provider=LLMProvider('gemini', 'gemini-3.8-flash', 'high', 'test-only'))

    explanation = asyncio.run(run({'action': 'reply', 'target': 'current', 'reply': '본문을 읽겠습니다.', 'readLink': True}))
    assert explanation['readLink'] is True
    troubleshooting = asyncio.run(run({'action': 'reply', 'target': 'current', 'reply': '실패 원인은 확인되지 않았습니다.', 'readLink': False}))
    assert 'readLink' not in troubleshooting


def test_pending_clarification_retains_full_material_and_requested_scope():
    from main import IntentRequest

    text = '긴 자료입니다. ' * 1000 + '끝부분 핵심 내용'
    payload = IntentRequest.model_validate({'text': '설명해줘', 'consent': True, 'context': {
        'previousText': text, 'previousFocus': '가격 주장만', 'previousLinkUrl': 'https://example.com/article',
    }})
    assert payload.context.previousText.endswith('끝부분 핵심 내용')
    assert payload.context.previousText == text
    assert payload.context.previousFocus == '가격 주장만'
