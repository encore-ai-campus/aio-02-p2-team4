"""Offline input-packet and original-citation regression tests."""
import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from providers import LLMProvider
from verification import verify_claims
from contracts import FactCheckResponse
from pydantic import SecretStr
import runtime
from runtime import RuntimeAdapters, Settings, build_runtime_workflow, make_runtime_adapters
from streaming import stream_events


PROVIDER = LLMProvider("openai", "gpt-6-luna", "max", "test-only")
SUPPORT = "The Atlas river reached record levels in 2024."
COUNTER = "The Atlas river did not reach record levels in 2025."
CONDITION = "This record concerns Seoul, 2024, and metres, not another population or unit."
FILLER = "An unrelated cooking recipe discusses ingredients and kitchen equipment. "


def state_for(body, kind="fact"):
    return {
        "text": "Atlas river reached record levels?", "focus": "date and location",
        "claims": [{"id": "c1", "quote": "Atlas river reached record levels?", "kind": kind,
                    "start": 0, "end": 34, "verdictCode": "mostly_supported" if kind == "fact" else "not_checkable",
                    "summary": "출처가 해당 연도의 기록을 설명합니다.", "confirmed": ["지역·연도를 확인했습니다."],
                    "unresolved": ["다른 연도에는 적용하지 않습니다."], "warnings": [], "evidenceIds": ["e1"]}],
        "searchQueries": {"c1": "Atlas river 2024"},
        "sources": [{"id": "s1", "url": "https://example.org/record", "title": "Atlas record",
                     "publisher": "Example", "publishedAt": "2024-06-01", "accessStatus": "verified",
                     "sourceType": "기사", "snippet": "DO-NOT-SEND-SEARCH-SNIPPET"}],
        "sourceTexts": {"s1": body},
        "evidence": [{"id": "e1", "claimId": "c1", "sourceId": "s1", "quote": SUPPORT,
                      "quoteTranslation": "Atlas 강은 2024년에 기록적인 수위에 도달했습니다.",
                      "quoteVerified": True, "relation": "supports"}],
    }


def judgment(quote=SUPPORT):
    return {"claims": [{"claimId": "c1", "verdictCode": "mostly_supported", "factScore": 90,
                        "summary": "출처에서 해당 기록을 확인했습니다.", "confirmed": ["기록을 확인했습니다."],
                        "unresolved": [], "evidence": [{"sourceId": "s1", "quote": quote,
                        "relation": "supports", "comparison": "same"}]}]}


def run_stage(stage, state, response, seen):
    def handler(request):
        body = json.loads(request.content)
        seen.update(json.loads(body["input"]))
        assert body["model"] == "gpt-6-luna" and body["reasoning"]["effort"] == "max"
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message",
            "content": [{"type": "output_text", "text": json.dumps(response, ensure_ascii=False)}]}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await stage(state, client=client, provider=PROVIDER)
    return asyncio.run(run())


def test_verification_selects_late_support_counter_and_nearby_conditions():
    body = "DO-NOT-SEND-LEAD " + FILLER * 180 + CONDITION + " " + SUPPORT + " " + FILLER * 30 + COUNTER
    state = state_for(body)
    before = deepcopy(state)
    seen = {}
    result = run_stage(verify_claims, state, judgment(), seen)
    packet = json.dumps(seen["sources"], ensure_ascii=False)
    assert SUPPORT in packet and COUNTER in packet and CONDITION in packet
    assert "DO-NOT-SEND-LEAD" not in packet and "DO-NOT-SEND-SEARCH-SNIPPET" not in packet
    assert sum(len(p["text"]) for p in seen["sources"][0]["passages"]) < 6_000
    for passage in seen["sources"][0]["passages"]:
        assert body[passage["start"]:passage["end"]] == passage["text"]
    assert result["claims"][0]["verdictCode"] == "mostly_supported"
    assert result["evidence"][0]["quote"] == SUPPORT
    assert state == before


def test_verification_rejects_a_real_quote_outside_the_supplied_passages():
    outside = "The bakery opened a branch in another city."
    body = outside + " " + FILLER * 180 + SUPPORT
    result = run_stage(verify_claims, state_for(body), judgment(outside), {})
    assert result["evidence"] == []
    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["claims"][0]["warnings"]


def test_overbroad_match_keeps_bounded_fallback_instead_of_silently_dropping_windows():
    body = SUPPORT + (" Atlas river data. " + FILLER * 3) * 100
    state = state_for(body)
    seen = {}
    run_stage(verify_claims, state, judgment(), seen)
    assert seen["sources"][0]["selection"] == "fallback"
    assert seen["sources"][0]["passages"] == [{"start": 0, "end": 6_000, "text": body[:6_000]}]


@pytest.mark.parametrize("kind,expected_calls", [("fact", 2), ("prediction", 1)])
def test_real_runtime_stream_finishes_with_late_grounded_passages(monkeypatch, kind, expected_calls):
    quote = SUPPORT if kind == "fact" else "In 2025 Demis forecast AGI around 2030."
    state = state_for("DO-NOT-SEND-LEAD " + FILLER * 180 + quote + " This is not a guaranteed schedule.", kind)
    extracted_quote = "Atlas river reached record levels?" if kind == "fact" else "AGI는 2030년 안에 오나?"
    query = "Atlas river 2024" if kind == "fact" else "AGI 2030년"
    question = extracted_quote + " 지역·시점·조건을 구분하여 자세히 설명해 주세요." * 6
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "deepseek-ai/deepseek-v4.1-flash" and body["reasoning_effort"] == "max"
        if len(requests) == 1:
            value = {"claims": [{"quote": extracted_quote, "kind": kind, "searchQuery": query}]}
        elif kind == "fact" and len(requests) == 2:
            value = judgment(quote)
        else:
            value = answer(quote)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(value, ensure_ascii=False)}}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(runtime.httpx, "AsyncClient", lambda *a, **kw:
                        real_client(*a, transport=httpx.MockTransport(handler), **kw))
    settings = Settings(api_key=SecretStr(""), hive_api_key=SecretStr("test-only"))
    adapters = make_runtime_adapters(settings)

    async def search(current):
        return {"sources": deepcopy(state["sources"])}

    async def read(current):
        return {"sources": deepcopy(state["sources"]), "sourceTexts": dict(state["sourceTexts"])}

    graph = build_runtime_workflow(settings, adapters=RuntimeAdapters(extract=adapters.extract, search=search,
        read=read, verify=adapters.verify, synthesize=adapters.synthesize))

    async def run():
        return [json.loads(event) async for event in stream_events(graph, {"text": question, "focus": "",
            "consent": True, "modelPreference": "deepseek-v4.1-flash"})]

    events = asyncio.run(run())
    assert len(requests) == expected_calls
    assert events[-1]["type"] == "result"
    assert [event["type"] for event in events].count("preview") == 1
    result = FactCheckResponse.model_validate({"result": events[-1]["result"]}).result
    assert result.answer.status == "judgment_only"
    assert result.answer.overview is None
    assert result.answer.model is None and result.answer.reasoning is None
    if kind == "fact":
        assert result.evidence[0].quote == quote and result.evidence[0].quoteVerified
    assert result.sources[0].url == "https://example.org/record"
    assert result.claims[0].verdictCode == ("mostly_supported" if kind == "fact" else "not_checkable")
    assert all("DO-NOT-SEND" not in json.dumps(json.loads(r["messages"][1]["content"]), ensure_ascii=False)
               for r in requests[1:])
