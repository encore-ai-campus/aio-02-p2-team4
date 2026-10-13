"""Offline API boundary checks; no provider calls."""
import importlib.util
import json

import httpx
import pytest
from pydantic import ValidationError


def test_health_and_status_do_not_claim_provider_readiness(monkeypatch):
    assert importlib.util.find_spec("main") is not None, "FastAPI application is missing"
    from fastapi.testclient import TestClient
    import main
    from main import app
    from pydantic import SecretStr
    from runtime import Settings

    monkeypatch.setattr(main, "load_settings", lambda: Settings(api_key=SecretStr("")))
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok" and body["service"] == "factlens-backend"
        assert isinstance(body.get("revision"), str) and body["revision"]
        status = client.get("/api/fact-check")
        assert status.status_code == 200
        assert status.headers["cache-control"] == "no-store"
        assert status.json() == {
            "configured": False, "jevConfigured": False, "workflowReady": False,
            "engine": "langgraph", "model": None, "reasoning": None,
            "webSearch": False, "phase": "api-foundation",
            "modelOptions": [
                {"id": "deepseek-v4.1-flash", "label": "DeepSeek V4.1 Flash Max", "configured": False},
                {"id": "gpt-6-luna", "label": "GPT-6 Luna Max", "configured": False},
                {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "configured": False},
                {"id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash", "configured": False},
            ],
        }
        assert client.post("/api/fact-check", json={
            "text": "claim", "focus": "", "consent": True,
        }).status_code == 503
        assert client.get("/openapi.json").status_code == 200


def test_shared_secret_gate_is_open_by_default_but_enforced_when_set(monkeypatch):
    import os

    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.delenv("BACKEND_SHARED_SECRET", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/fact-check").status_code == 200

    monkeypatch.setenv("BACKEND_SHARED_SECRET", "test-secret")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        denied = client.get("/api/fact-check")
        assert denied.status_code == 403
        assert denied.json()["code"] == "FORBIDDEN"
        allowed = client.get("/api/fact-check", headers={"x-factlens-secret": "test-secret"})
        assert allowed.status_code == 200
        assert client.get("/api/fact-check", headers={"x-factlens-secret": "wrong"}).status_code == 403


def test_stream_rejects_bad_link_and_image_attachments():
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        bad_image = client.post("/api/fact-check/stream", json={
            "text": "hi", "focus": "", "consent": True,
            "image": {"mime": "image/gif", "data": "eA=="},
        })
        assert bad_image.status_code == 422
        bad_link = client.post("/api/fact-check/stream", json={
            "text": "hi", "focus": "", "consent": True, "linkUrl": "ftp://x/y",
        })
        assert bad_link.status_code == 422
        blank_text = client.post("/api/fact-check/stream", json={
            "text": "   ", "focus": "", "consent": True,
        })
        assert blank_text.status_code == 422


def test_jev_endpoint_rejects_non_jev_and_image_requests():
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        assert client.post("/api/fact-check/jev", json={
            "text": "hi", "focus": "", "consent": True,
        }).status_code == 422
        assert client.post("/api/fact-check/jev", json={
            "text": "hi", "focus": "", "consent": True, "jevMode": True,
            "image": {"mime": "image/jpeg", "data": "eA=="},
        }).status_code == 422


def test_jev_endpoint_returns_scored_result(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from main import app
    from pydantic import SecretStr
    from runtime import Settings
    import runtime

    real_async_client = httpx.AsyncClient

    seen = []

    def handler(request):
        if request.url.host == "api.openai.com":
            seen.append("search")
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "web_search_call", "status": "completed", "action": {"sources": [
                    {"url": "https://example.org/boiling-point", "title": "Boiling point reference"},
                ]}},
            ]})

        assert request.url.host == "api.typesafe.ai"
        seen.append("jev")
        state = json.loads(request.content)["state"]
        assert "Water boils at 100 degrees Celsius" in state["evidence"]
        return httpx.Response(200, json={
            "model": "jev-latest",
            "answers": {
                "verdict": {
                    "type": "choice", "choice": "contradicted",
                    "probabilities": {"contradicted": 0.9},
                    "confidence": 0.9,
                },
                "strength": {
                    "type": "score", "score": 0.5,
                    "legend": {str(index): f"level {index}" for index in range(5)},
                    "probabilities": {"0": 0.5, "1": 0.5, "2": 0.0, "3": 0.0, "4": 0.0},
                    "confidence": 0.8,
                },
            },
            "usage": {"input_tokens": 50, "output_tokens": 5},
        })

    def mock_client(*args, **kwargs):
        return real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    async def fake_fetch(url):
        return "Water boils at 100 degrees Celsius at sea level.", url

    monkeypatch.setattr(main.httpx, "AsyncClient", mock_client)
    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(
            api_key=SecretStr("test-openai-key"),
            typesafe_api_key=SecretStr("gw-test"),
        ),
    )
    with TestClient(app) as client:
        response = client.post("/api/fact-check/jev", json={
            "text": "Water boils at 50C.", "focus": "", "consent": True, "jevMode": True,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["model"] == "jev-latest"
        assert [(c["id"], c["verdictCode"]) for c in body["claims"]] == [("c1", "contradicted")]
        assert body["claims"][0]["evidenceIds"] == []
        assert [source["url"] for source in body["sources"]] == [
            "https://example.org/boiling-point",
        ]
        assert seen == ["search", "jev"]


def test_jev_endpoint_maps_gateway_failure_to_502(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from main import app
    from pydantic import SecretStr
    from runtime import Settings
    import runtime

    real_async_client = httpx.AsyncClient

    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "web_search_call", "status": "completed", "action": {"sources": [
                    {"url": "https://example.org/source", "title": "Test source"},
                ]}},
            ]})
        return httpx.Response(500, json={"error": "busy"})

    def mock_client(*args, **kwargs):
        return real_async_client(
            *args,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    async def fake_fetch(url):
        return "Relevant source text.", url

    monkeypatch.setattr(main.httpx, "AsyncClient", mock_client)
    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(
            api_key=SecretStr("test-openai-key"),
            typesafe_api_key=SecretStr("gw-test"),
        ),
    )
    with TestClient(app) as client:
        response = client.post("/api/fact-check/jev", json={
            "text": "Water boils at 50C.", "focus": "", "consent": True, "jevMode": True,
        })
        assert response.status_code == 502
        assert response.json()["code"] == "GATEWAY_ERROR"


def test_jev_endpoint_concludes_insufficient_evidence_on_low_confidence(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from main import app
    from pydantic import SecretStr
    from runtime import Settings
    import runtime

    real_async_client = httpx.AsyncClient

    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "web_search_call", "status": "completed", "action": {"sources": [
                    {"url": "https://example.org/source", "title": "Test source"},
                ]}},
            ]})
        return httpx.Response(200, json={
            "model": "jev-latest",
            "answers": {
                "verdict": {"type": "choice", "choice": "partially_supported", "confidence": 0.2},
                "strength": {"type": "score", "score": 2.0, "confidence": 0.9},
            },
        })

    def mock_client(*args, **kwargs):
        return real_async_client(
            *args,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    async def fake_fetch(url):
        return "Relevant source text.", url

    monkeypatch.setattr(main.httpx, "AsyncClient", mock_client)
    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(
            api_key=SecretStr("test-openai-key"),
            typesafe_api_key=SecretStr("gw-test"),
        ),
    )
    with TestClient(app) as client:
        response = client.post("/api/fact-check/jev", json={
            "text": "Water boils at 50C.", "focus": "", "consent": True, "jevMode": True,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["claims"][0]["verdictCode"] == "insufficient_evidence"
        assert body["answer"]["status"] == "insufficient_evidence"


def test_status_reports_ready_for_configured_runtime(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings
    import main
    from main import app

    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings(
            api_key=SecretStr("test-only"),
            gemini_api_key=SecretStr("gemini-test-only"),
        ),
    )
    with TestClient(app) as client:
        assert client.get("/api/fact-check").json() == {
            "configured": True, "jevConfigured": False, "workflowReady": True,
            "engine": "langgraph", "model": "gpt-6-luna", "reasoning": "max",
            "webSearch": True, "phase": "workflow-ready",
            "modelOptions": [
                {"id": "deepseek-v4.1-flash", "label": "DeepSeek V4.1 Flash Max", "configured": False},
                {"id": "gpt-6-luna", "label": "GPT-6 Luna Max", "configured": True},
                {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "configured": True},
                {"id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash", "configured": True},
            ],
        }


def test_status_reports_gpt6_luna_when_only_openai_is_configured(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings
    import main
    from main import app

    monkeypatch.setattr(main, "load_settings", lambda: Settings(api_key=SecretStr("test-only")))
    with TestClient(app) as client:
        assert client.get("/api/fact-check").json()["model"] == "gpt-6-luna"


def test_status_reports_gemini_fallback_when_openai_is_missing(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings
    import main
    from main import app

    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: Settings(
            api_key=SecretStr(""),
            gemini_api_key=SecretStr("gemini-test-only"),
        ),
    )
    with TestClient(app) as client:
        assert client.get("/api/fact-check").json() == {
            "configured": True, "jevConfigured": False, "workflowReady": True,
            "engine": "langgraph", "model": "gemini-3.8-flash", "reasoning": "high",
            "webSearch": True, "phase": "workflow-ready",
            "modelOptions": [
                {"id": "deepseek-v4.1-flash", "label": "DeepSeek V4.1 Flash Max", "configured": False},
                {"id": "gpt-6-luna", "label": "GPT-6 Luna Max", "configured": False},
                {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "configured": True},
                {"id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash", "configured": True},
            ],
        }



def test_status_reports_jev_configuration_without_returning_the_key(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from runtime import Settings
    import main
    from main import app

    monkeypatch.setattr(
        main, "load_settings",
        lambda: Settings(api_key=SecretStr(""), typesafe_api_key=SecretStr("gateway-test-only")),
    )
    with TestClient(app) as client:
        response = client.get("/api/fact-check")
        assert response.status_code == 200
        assert response.json()["jevConfigured"] is True
        assert "gateway-test-only" not in response.text


def test_request_preserves_original_text():
    assert importlib.util.find_spec("schemas") is not None, "Request schema is missing"
    from schemas import FactCheckRequest
    request = FactCheckRequest(text="  검증할 주장  ", focus="", consent=True)
    assert request.model_dump() == {
        "text": "  검증할 주장  ", "focus": "", "consent": True,
        "modelPreference": "auto", "linkUrl": None, "image": None, "jevMode": False,
    }
    selected = FactCheckRequest(
        text="claim", focus="", consent=True, modelPreference="gpt-6-luna"
    )
    assert selected.modelPreference == "gpt-6-luna"


@pytest.mark.parametrize("change", [
    {"text": " \n\t"}, {"text": "a" * 12001}, {"text": 123},
    {"text": "😀" * 6001}, {"focus": "a" * 501},
    {"focus": None}, {"consent": False}, {"consent": 1},
    {"consent": "true"}, {"extra": "not allowed"},
])
def test_request_rejects_invalid_input(change):
    assert importlib.util.find_spec("schemas") is not None, "Request schema is missing"
    from schemas import FactCheckRequest
    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate({"text": "claim", "focus": "", "consent": True, **change})


def test_request_rejects_unknown_model_preference():
    assert importlib.util.find_spec("schemas") is not None, "Request schema is missing"
    from schemas import FactCheckRequest
    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate({
            "text": "claim", "focus": "", "consent": True,
            "modelPreference": "unknown-model",
        })


@pytest.mark.parametrize("missing", ["text", "focus", "consent"])
def test_request_requires_all_contract_fields(missing):
    assert importlib.util.find_spec("schemas") is not None, "Request schema is missing"
    from schemas import FactCheckRequest
    payload = {"text": "claim", "focus": "", "consent": True}
    del payload[missing]
    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate(payload)
