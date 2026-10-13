"""Jev verdicts through AI Gateway; no live traffic (all transports mocked)."""
import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from jev import JevError, evaluate_claims_jev


JEV_URL = "https://api.typesafe.ai/v1/systemone"


def jev_response(verdict="mostly_supported", score=3.2, confidence=0.9):
    return httpx.Response(200, json={
        "model": "jev-latest",
        "answers": {
            "verdict": {
                "type": "choice", "choice": verdict,
                "probabilities": {verdict: confidence},
                "confidence": confidence,
            },
            "strength": {
                "type": "score", "score": score,
                "legend": {str(index): f"level {index}" for index in range(5)},
                "probabilities": {str(index): 1.0 if index == round(score) else 0.0 for index in range(5)},
                "confidence": confidence,
            },
        },
        "usage": {"input_tokens": 100, "output_tokens": 10},
    })


def test_evaluate_maps_verdict_and_strength_to_fact_score():
    seen = {}

    def handler(request):
        assert str(request.url) == JEV_URL
        assert request.headers["authorization"] == "Bearer gw-test-key"
        body = json.loads(request.content)
        assert body["model"] == "jev-latest"
        assert set(body["questions"]) == {"verdict", "strength"}
        assert body["questions"]["verdict"]["type"] == "choice"
        assert body["questions"]["strength"]["type"] == "score"
        seen["state"] = body["state"]
        return jev_response()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await evaluate_claims_jev(
                [{"id": "c1", "quote": "Water boils at 100C.", "kind": "fact"}],
                {"c1": "[s1] Water boils at 100 degrees Celsius at sea level."},
                client=client, api_key="gw-test-key",
            )

    result = asyncio.run(run())
    assert result == [{"claimId": "c1", "verdictCode": "mostly_supported", "factScore": 80}]
    assert seen["state"]["claim"] == "Water boils at 100C."
    assert "Water boils at 100 degrees" in seen["state"]["evidence"]


def test_strength_score_scales_to_0_100():
    async def run(score):
        async def handler(request):
            return jev_response(score=score)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await evaluate_claims_jev(
                [{"id": "c1", "quote": "q", "kind": "fact"}],
                {"c1": "e"},
                client=client, api_key="k",
            )
            return result[0]["factScore"]

    assert asyncio.run(run(0.0)) == 0
    assert asyncio.run(run(4.0)) == 100
    assert asyncio.run(run(1.0)) == 25


@pytest.mark.parametrize("make_response", [
    lambda: httpx.Response(500, json={"error": "busy"}),
    lambda: httpx.Response(200, json={"model": "x"}),
    lambda: httpx.Response(200, json={
        "model": "x",
        "answers": {"verdict": {"type": "choice", "choice": "bogus", "confidence": 0.9},
                    "strength": {"type": "score", "score": 3.0, "confidence": 0.9}},
    }),
    lambda: httpx.Response(200, json={
        "model": "x",
        "answers": {"verdict": {"type": "choice", "choice": "contradicted", "confidence": 0.9},
                    "strength": {"type": "score", "score": 9.0, "confidence": 0.9}},
    }),
])
def test_transport_and_shape_failures_raise_jev_error(make_response):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: make_response())) as client:
            await evaluate_claims_jev(
                [{"id": "c1", "quote": "q", "kind": "fact"}],
                {"c1": "e"},
                client=client, api_key="k",
            )

    with pytest.raises(JevError):
        asyncio.run(run())


def test_low_confidence_escalates_and_missing_key_fails_fast():
    async def run(response):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as client:
            return await evaluate_claims_jev(
                [{"id": "c1", "quote": "q", "kind": "fact"}],
                {"c1": "e"},
                client=client, api_key="k",
            )

    with pytest.raises(JevError):
        asyncio.run(run(jev_response(confidence=0.2)))

    async def run_no_key():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: jev_response())
        ) as client:
            return await evaluate_claims_jev(
                [{"id": "c1", "quote": "q", "kind": "fact"}],
                {"c1": "e"},
                client=client, api_key="  ",
            )

    with pytest.raises(JevError):
        asyncio.run(run_no_key())


def test_verify_claims_jev_builds_score_only_results():
    from verification import verify_claims_jev

    async def handler(request):
        return jev_response(verdict="contradicted", score=0.5, confidence=0.8)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims_jev(
                {
                    "claims": [
                        {"id": "c1", "quote": "Water boils at 50C.", "kind": "fact", "start": 0, "end": 20},
                        {"id": "c2", "quote": "I love this policy.", "kind": "opinion", "start": 0, "end": 20},
                    ],
                    "sources": [{"id": "s1", "url": "https://example.org/r", "accessStatus": "verified"}],
                    "sourceTexts": {"s1": "Water boils at 100 degrees Celsius at sea level."},
                },
                client=client, api_key="k",
            )

    result = asyncio.run(run())
    fact, opinion = result["claims"]
    assert fact["verdictCode"] == "contradicted"
    assert fact["factScore"] == 12
    assert fact["evidenceIds"] == []
    assert fact["warnings"] == ["Jev 고속 판정: 직접 인용을 표시하지 않습니다."]
    assert result["evidence"] == []
    assert opinion["verdictCode"] == "not_checkable"


def test_verify_claims_jev_without_sources_never_calls_gateway():
    from verification import verify_claims_jev

    def handler(request):
        raise AssertionError("no verified sources means no Jev call")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims_jev(
                {
                    "claims": [{"id": "c1", "quote": "q", "kind": "fact", "start": 0, "end": 1}],
                    "sources": [],
                    "sourceTexts": {},
                },
                client=client, api_key="k",
            )

    result = asyncio.run(run())
    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"


def test_fast_check_searches_with_llm_and_sends_read_source_text_to_jev(monkeypatch):
    import runtime
    from runtime import Settings

    claim = "AGI\uB294 2030\uB144 \uC548\uC5D0 \uC624\uB098?"
    seen = {"search_hosts": [], "jev_state": None}

    def handler(request):
        if request.url.host == "api.openai.com":
            seen["search_hosts"].append(request.url.host)
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "web_search_call", "status": "completed", "action": {"sources": [
                    {"url": "https://www.aitimes.com/news/agi-outlook", "title": "AGI timeline outlook"},
                ]}},
            ]})

        assert request.url.host == "api.typesafe.ai"
        seen["jev_state"] = json.loads(request.content)["state"]
        return jev_response(verdict="mostly_supported", score=3.0, confidence=0.9)

    async def fake_fetch(url):
        assert url == "https://www.aitimes.com/news/agi-outlook"
        return (
            "Expert forecasts disagree on AGI arrival timelines.",
            url,
        )

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runtime.run_jev_fast_check(
                text=claim, focus="",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("test-openai-key")),
                consent=True,
            )

    result = asyncio.run(run())
    assert result.model == "jev-latest"
    assert result.text == claim
    assert [(c.id, c.verdictCode, c.factScore) for c in result.claims] == [
        ("c1", "mostly_supported", 75),
    ]
    assert seen["search_hosts"] == ["api.openai.com"]
    assert seen["jev_state"]["claim"] == claim
    assert "Expert forecasts disagree" in seen["jev_state"]["evidence"]
    assert result.claims[0].evidenceIds == []
    assert result.evidence == []
    assert [source.url for source in result.sources] == [
        "https://www.aitimes.com/news/agi-outlook",
    ]


def test_fast_check_llm_search_honors_the_selected_model(monkeypatch):
    import runtime
    from runtime import Settings

    requested_models = []

    def handler(request):
        if request.url.host == "api.openai.com":
            requested_models.append(json.loads(request.content)["model"])
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "web_search_call", "status": "completed", "action": {"sources": [
                    {"url": "https://example.org/found", "title": "Found page"},
                ]}},
            ]})
        return jev_response(verdict="mostly_supported", score=3.0, confidence=0.9)

    async def fake_fetch(url):
        return ("Searched page body text here.", url)

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runtime.run_jev_fast_check(
                text="Some checkable claim.", focus="",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("test-openai-key")),
                model_preference="gpt-6-luna",
            )

    result = asyncio.run(run())
    assert requested_models == ["gpt-6-luna"]
    assert result.claims[0].verdictCode == "mostly_supported"


def test_fast_check_skips_search_when_the_link_reads_cleanly(monkeypatch):
    import runtime
    from runtime import Settings

    async def fake_fetch(url):
        return ("Fetched page body text here.", url)

    def handler(request):
        raise AssertionError(f"no search or gateway call expected except Jev, got {request.url}")

    async def jev_handler(request):
        assert "Fetched page body text here." in json.loads(request.content)["state"]["evidence"]
        return jev_response(verdict="mostly_supported", score=3.0, confidence=0.9)

    def router(request):
        if request.url.host == "api.typesafe.ai":
            return jev_handler(request)
        return handler(request)

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(router)) as client:
            return await runtime.run_jev_fast_check(
                text="Water boils at 50C.", focus="",
                link_url="https://example.org/article",
                client=client, api_key="k",
                settings=Settings(
                    api_key=SecretStr("test-openai-key"),
                    tavily_api_key=SecretStr("tvly-test"),
                ),
            )

    result = asyncio.run(run())
    assert [s.id for s in result.sources] == ["s0"]
    assert result.sources[0].accessStatus == "verified"


def test_fast_check_collects_youtube_context_when_the_key_is_configured(monkeypatch):
    import runtime
    from runtime import Settings

    async def fake_fetch(url):
        raise AssertionError(f"web fetch must not run for a YouTube-only check, got {url}")

    seen = {}

    async def fake_youtube(url, api_key, client):
        seen["key"] = bool(api_key and api_key.strip())
        return {
            "title": "Test video",
            "channelTitle": "Test channel",
            "publishedAt": None,
            "viewCount": "1234567",
            "comments": ["First comment"],
            "status": "collected",
        }

    def handler(request):
        return jev_response(verdict="mostly_supported", score=3.0, confidence=0.9)

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(runtime, "fetch_youtube_data", fake_youtube)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runtime.run_jev_fast_check(
                text="Check this video.",
                link_url="https://www.youtube.com/watch?v=aB_12345678",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr(""), youtube_api_key=SecretStr("yt-test")),
            )

    result = asyncio.run(run())
    assert seen["key"] is True
    assert result.sources[0].youtubeDataStatus == "collected"
    assert result.sources[0].youtubeComments == ["First comment"]


def test_fast_check_uses_linked_source_as_evidence_without_replacing_claim(monkeypatch):
    import runtime
    from runtime import Settings

    async def fake_fetch(url):
        assert url == "https://example.org/article"
        return ("Fetched page body text here.", "https://example.org/article")

    async def handler(request):
        assert "Fetched page body text here." in json.loads(request.content)["state"]["evidence"]
        return jev_response(verdict="partially_supported", score=2.0, confidence=0.8)

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runtime.run_jev_fast_check(
                text="Water boils at 50C.", focus="",
                link_url="https://example.org/article",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("")),
            )

    result = asyncio.run(run())
    assert result.text == "Water boils at 50C."
    assert [s.id for s in result.sources] == ["s0"]
    assert result.sources[0].accessStatus == "verified"
    assert result.claims[0].factScore == 50


def test_fast_check_truncates_long_text_to_contract_limit():
    import runtime
    from runtime import Settings

    seen = {}

    async def handler(request):
        body = json.loads(request.content)
        seen["quote_len"] = len(body["state"]["claim"] if isinstance(body.get("state"), dict) else "")
        return jev_response()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runtime.run_jev_fast_check(
                text="가" * 15000, focus="",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("")),
            )

    result = asyncio.run(run())
    assert len(result.text) <= 12000
    assert result.claims[0].end <= 12000


def test_fast_check_propagates_jev_failure_without_llm_fallback(monkeypatch):
    import runtime
    from runtime import Settings

    async def fake_fetch(url):
        return "Relevant source text.", url

    async def handler(request):
        return httpx.Response(500, json={"error": "busy"})

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runtime.run_jev_fast_check(
                text="Some claim text here.", focus="",
                link_url="https://example.org/source",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("")),
            )

    with pytest.raises(JevError):
        asyncio.run(run())


def test_fast_check_preserves_input_whitespace_for_result_echo(monkeypatch):
    import runtime
    from runtime import Settings

    async def fake_fetch(url):
        return ("Relevant source text.", url)

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: jev_response()
        )) as client:
            return await runtime.run_jev_fast_check(
                text="  padded claim  ", focus="",
                link_url="https://example.org/source",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("")),
            )

    result = asyncio.run(run())
    assert result.text == "  padded claim  "
    assert result.claims[0].quote == "  padded claim  "


def test_fast_check_low_confidence_concludes_insufficient_evidence(monkeypatch):
    import runtime
    from runtime import Settings

    async def fake_fetch(url):
        return ("Relevant source text.", url)

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: jev_response(confidence=0.2)
        )) as client:
            return await runtime.run_jev_fast_check(
                text="Some unverifiable claim.", focus="",
                link_url="https://example.org/source",
                client=client, api_key="k",
                settings=Settings(api_key=SecretStr("")),
            )

    result = asyncio.run(run())
    assert result.claims[0].verdictCode == "insufficient_evidence"
    assert result.answer.status == "insufficient_evidence"


def _jev_runtime_state():
    quote = "Water boils at 100C."
    return {
        "text": quote,
        "focus": "",
        "consent": True,
        "jevMode": True,
        "claims": [{"id": "c1", "quote": quote, "kind": "fact", "start": 0, "end": len(quote)}],
        "sources": [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        "sourceTexts": {"s1": "Water boils at 100 degrees Celsius at sea level."},
    }


def test_runtime_verify_uses_jev_when_mode_on(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    real_async_client = httpx.AsyncClient

    def handler(request):
        assert request.url.host == "api.typesafe.ai"
        return jev_response(verdict="mostly_supported", score=3.6, confidence=0.9)

    def mock_client(*args, **kwargs):
        return real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(runtime.httpx, "AsyncClient", mock_client)
    settings = Settings(
        api_key=SecretStr(""),
        gemini_api_key=SecretStr(""),
        typesafe_api_key=SecretStr("gw-test-only"),
    )
    adapters = make_runtime_adapters(settings)
    update = asyncio.run(adapters.verify(_jev_runtime_state()))
    assert update["claims"][0]["verdictCode"] == "mostly_supported"
    assert update["claims"][0]["factScore"] == 90
    assert update["llmModel"] == "jev-latest"


def test_runtime_verify_escales_to_llm_when_jev_fails(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    real_async_client = httpx.AsyncClient

    def handler(request):
        if request.url.host == "api.typesafe.ai":
            return httpx.Response(500, json={"error": "busy"})
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.8-flash"
        quote = "Water boils at 100 degrees Celsius at sea level."
        return httpx.Response(200, json={
            "status": "completed",
            "steps": [{
                "type": "model_output",
                "content": [{
                    "type": "text",
                    "text": json.dumps({"claims": [{
                        "claimId": "c1",
                        "verdictCode": "mostly_supported",
                        "factScore": 85,
                        "summary": "The source reports the level.",
                        "confirmed": ["The source reports record levels."],
                        "unresolved": [],
                        "evidence": [{
                            "sourceId": "s1",
                            "quote": quote,
                            "relation": "supports",
                            "comparison": "same",
                        }],
                    }]}),
                }],
            }],
        })

    def mock_client(*args, **kwargs):
        return real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(runtime.httpx, "AsyncClient", mock_client)
    settings = Settings(
        api_key=SecretStr(""),
        gemini_api_key=SecretStr("gemini-test-only"),
        typesafe_api_key=SecretStr("gw-test-only"),
    )
    adapters = make_runtime_adapters(settings)
    update = asyncio.run(adapters.verify(_jev_runtime_state()))
    assert update["claims"][0]["verdictCode"] == "mostly_supported"
    assert update["llmModel"] == "gemini-3.8-flash"


def test_jev_coherence_warning_flags_mismatched_bands_only():
    from verification import _JEV_MODE_WARNING, jev_coherence_warning

    assert jev_coherence_warning("mostly_supported", 85) is None
    assert jev_coherence_warning("partially_supported", 65) is None
    assert jev_coherence_warning("contradicted", 10) is None
    assert jev_coherence_warning("insufficient_evidence", 50) is None
    assert jev_coherence_warning("mostly_supported", 75) is not None
    assert jev_coherence_warning("partially_supported", 50) is not None
    assert jev_coherence_warning("contradicted", 60) is not None
    assert _JEV_MODE_WARNING != jev_coherence_warning("mostly_supported", 75)
