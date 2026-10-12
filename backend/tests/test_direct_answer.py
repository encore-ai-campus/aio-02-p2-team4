"""판정 결과와 원문 인용을 유지하면서 추출·판정 호출만 수행합니다."""
import asyncio
from copy import deepcopy
import json

import httpx
import pytest
from pydantic import SecretStr

from contracts import FactCheckResponse
import runtime
from runtime import RuntimeAdapters, Settings, build_runtime_workflow, make_runtime_adapters
from streaming import stream_events


QUESTION = "인류는 달에 갔나?"
QUOTE = "Apollo 11 landed humans on the Moon in July 1969."
SUMMARY = "미국은 1969년 아폴로 11호로 인간을 달에 보냈습니다."
CONFIRMED = "아폴로 11호의 유인 달 착륙 기록이 확인됩니다."
UNRESOLVED = "이 근거는 미국의 아폴로 임무 기록을 다룹니다."


def checked_state():
    return {
        "text": QUESTION, "focus": "달 방문 기록의 사실 여부", "consent": True,
        "modelPreference": "deepseek-v4.1-flash",
        "claims": [{
            "id": "c1", "quote": QUESTION, "kind": "fact", "start": 0, "end": len(QUESTION),
            "factScore": 90, "verdictCode": "mostly_supported", "verdict": "대체로 확인됨",
            "tone": "positive", "summary": SUMMARY, "confirmed": [CONFIRMED],
            "unresolved": [UNRESOLVED], "warnings": [], "evidenceIds": ["e1"],
        }],
        "sources": [{
            "id": "s1", "url": "https://example.org/apollo", "title": "Apollo 11 record",
            "publisher": "Example", "accessStatus": "verified", "sourceType": "기사",
            "retrievedAt": "2026-10-05T00:00:00+00:00", "originGroupId": "example.org",
        }],
        "sourceTexts": {"s1": QUOTE},
        "evidence": [{
            "id": "e1", "claimId": "c1", "sourceId": "s1", "quote": QUOTE,
            "quoteVerified": True, "relation": "supports",
            "quoteTranslation": "아폴로 11호는 1969년 7월 인간을 달에 착륙시켰습니다.",
        }],
        "llmModel": "deepseek-v4.1-flash", "llmReasoning": "max",
    }


def completion(value):
    return httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps(value, ensure_ascii=False)},
    }]})


def provider_adapters(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(runtime.httpx, "AsyncClient", client)
    return make_runtime_adapters(Settings(api_key=SecretStr(""), hive_api_key=SecretStr("test-only")))


@pytest.mark.parametrize("code,score", [("mostly_supported", 90), ("partially_supported", 65)])
def test_runtime_stream_finishes_with_two_llm_requests_and_preserves_verification(monkeypatch, code, score):
    state = checked_state()
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return completion({"claims": [{"quote": QUESTION, "kind": "fact", "searchQuery": "아폴로 11 달 착륙"}]})
        if len(requests) == 2:
            return completion({"claims": [{
                "claimId": "c1", "verdictCode": code, "factScore": score,
                "summary": SUMMARY, "confirmed": [CONFIRMED], "unresolved": [UNRESOLVED],
                "evidence": [{"sourceId": "s1", "quote": QUOTE, "quoteTranslation": state["evidence"][0]["quoteTranslation"],
                              "relation": "supports", "comparison": "same"}],
            }]})
        raise AssertionError("Unexpected extra model request after verification")

    adapters = provider_adapters(monkeypatch, handler)

    async def search(current):
        return {"sources": deepcopy(state["sources"])}

    async def read(current):
        return {"sources": deepcopy(state["sources"]), "sourceTexts": dict(state["sourceTexts"])}

    graph = build_runtime_workflow(
        Settings(api_key=SecretStr(""), hive_api_key=SecretStr("test-only")),
        adapters=RuntimeAdapters(extract=adapters.extract, search=search, read=read,
                                 verify=adapters.verify, synthesize=adapters.synthesize),
    )

    async def run():
        return [json.loads(event) async for event in stream_events(graph, {
            "text": QUESTION, "focus": state["focus"], "consent": True,
            "modelPreference": "deepseek-v4.1-flash",
        })]

    events = asyncio.run(run())
    assert len(requests) == 2
    assert all(request["model"] == "deepseek-ai/deepseek-v4.1-flash" and request["reasoning_effort"] == "max" for request in requests)
    assert events[-1]["type"] == "result"
    assert [event["type"] for event in events].count("preview") == 1
    result = FactCheckResponse.model_validate({"result": events[-1]["result"]}).result
    assert result.answer.status == "judgment_only"
    assert result.answer.overview is None
    assert result.claims[0].summary == SUMMARY
    assert result.answer.model is None and result.answer.reasoning is None
    assert result.model == "deepseek-v4.1-flash" and result.reasoning == "max"
    assert result.claims[0].verdictCode == code
    assert result.claims[0].factScore == score
    assert result.evidence[0].quote == QUOTE and result.evidence[0].quoteVerified is True
    assert result.evidence[0].quoteTranslation == "아폴로 11호는 1969년 7월 인간을 달에 착륙시켰습니다."
    assert result.sources[0].url == "https://example.org/apollo"
