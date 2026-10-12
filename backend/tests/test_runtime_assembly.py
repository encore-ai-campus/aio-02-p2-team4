"""Runtime assembly tests; explicit adapters keep the five-node graph offline."""
import asyncio

from contracts import FactCheckResponse
from runtime import RuntimeAdapters, Settings, build_fact_check_result, build_runtime_workflow, make_runtime_adapters
from pydantic import SecretStr


def test_final_result_warns_when_llm_search_was_unavailable():
    result = build_fact_check_result(
        {
            "text": "Claim", "focus": "", "consent": True,
            "claims": [], "sources": [], "evidence": [],
            "searchNotice": "LLM_SEARCH_UNAVAILABLE",
        },
        {},
    )
    assert any("웹검색을 사용할 수 없어" in warning for warning in result.warnings)


def test_forecast_keywords_reach_search_through_graph_without_leaking_into_result():
    import json
    import httpx
    from extraction import extract_claims
    from search import search_sources
    from verification import verify_claims

    question = "AGI는 2030년 안에 오나?"
    # Distinct from the fallback query to detect a graph-state field being dropped.
    keywords = "AGI 2030년 전문가 전망"
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps({
                    "claims": [{"quote": question, "kind": "prediction", "searchQuery": keywords}],
                })}]},
            ]})
        assert json.loads(body["input"])["primaryQueries"] == [keywords]
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed", "action": {"sources": []}},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async def extract(state):
                return await extract_claims(state, api_key="test-only", client=client)

            async def search(state):
                return await search_sources(state, api_key="test-only", client=client)

            async def read(state):
                return {"sources": state["sources"], "sourceTexts": {}}

            async def verify(state):
                return await verify_claims(state, api_key="test-only", client=client)

            async def synthesize(state):
                return {"answer": {"status": "judgment_only", "overview": None, "sections": [], "conclusion": None, "model": None, "reasoning": None}, "answerModel": None, "answerReasoning": None}

            graph = build_runtime_workflow(
                Settings(api_key=SecretStr("test-only")),
                adapters=RuntimeAdapters(
                    extract=extract, search=search, read=read, verify=verify,
                    synthesize=synthesize,
                ),
            )
            return await graph.ainvoke({"text": question, "focus": "", "consent": True})

    state = asyncio.run(run())
    assert len(requests) == 2
    assert state["searchQueries"] == {"c1": keywords}
    result = FactCheckResponse.model_validate({"result": state["result"]}).result
    assert result.claims[0].kind == "prediction"
    assert result.claims[0].verdictCode == "not_checkable"
    assert result.answer.status == "judgment_only"
    assert "searchQueries" not in result.model_dump()
    assert "searchQuery" not in result.claims[0].model_dump()


def test_runtime_graph_assembles_valid_final_result_after_five_stages():
    seen = []

    async def extract(state):
        seen.append("extracting")
        return {"claims": [{
            "id": "c1", "quote": state["text"], "start": 0, "end": 5,
            "end": 5, "kind": "fact",
        }]}

    async def search(state):
        seen.append("searching")
        return {"sources": [{
            "id": "s1", "url": "https://example.org/source", "title": "Example source",
            "publisher": "example.org", "accessStatus": "pending",
        }]}

    async def read(state):
        seen.append("reading")
        return {"sources": [{
            "id": "s1", "url": "https://example.org/source", "title": "Example source",
            "publisher": "example.org", "accessStatus": "verified",
            "retrievedAt": "2026-09-20T00:00:00+00:00",
        }], "sourceTexts": {"s1": "Claim is supported."}}

    async def verify(state):
        seen.append("verifying")
        return {"claims": [{
            "id": "c1", "quote": "Claim", "start": 0, "end": 5, "kind": "fact",
            "verdictCode": "mostly_supported", "verdict": "대체로 확인됨",
            "tone": "positive", "summary": "원문이 주장을 뒷받침합니다.",
            "confirmed": ["Claim"], "unresolved": [], "warnings": [], "evidenceIds": ["e1"],
        }], "evidence": [{
            "id": "e1", "claimId": "c1", "sourceId": "s1",
            "quote": "Claim is supported.", "quoteVerified": True, "relation": "supports",
        }], "llmModel": "gpt-6-luna", "llmReasoning": "max"}

    async def synthesize(state):
        seen.append("synthesizing")
        assert state["llmModel"] == "gpt-6-luna"
        citation = {"sourceId": "s1", "quote": "Claim is supported."}
        return {
            "answer": {
                "status": "grounded",
                "overview": {"text": "원문은 주장을 뒷받침합니다.", "citations": [citation]},
                "sections": [],
                "conclusion": {"text": "제한된 근거에 따른 결론입니다.", "citations": [citation]},
                "model": "gemini-3.8-flash", "reasoning": "high",
            },
            "answerModel": "gemini-3.8-flash",
            "answerReasoning": "high",
        }

    graph = build_runtime_workflow(
        Settings(api_key=SecretStr("test-only")),
        adapters=RuntimeAdapters(
            extract=extract, search=search, read=read, verify=verify, synthesize=synthesize,
        ),
    )
    state = asyncio.run(graph.ainvoke({
        "text": "Claim", "focus": "", "consent": True,
    }))

    assert seen == ["extracting", "searching", "reading", "verifying", "synthesizing"]
    parsed = FactCheckResponse.model_validate({"result": state["result"]})
    assert parsed.result.sources[0].url == "https://example.org/source"
    assert parsed.result.claims[0].evidenceIds == ["e1"]
    assert parsed.result.model == "gpt-6-luna"
    assert parsed.result.reasoning == "max"
    assert parsed.result.answer.model == "gemini-3.8-flash"
    assert parsed.result.answer.reasoning == "high"
    assert "sourceTexts" in state


def test_result_reports_provider_used_by_the_final_stage():
    result = build_fact_check_result(
        {
            "text": "Claim", "focus": "", "consent": True,
            "sources": [{
                "id": "s1", "url": "https://example.org/source", "title": "Example",
                "publisher": "example.org", "publishedAt": None,
                "retrievedAt": "2026-09-20T00:00:00+00:00", "accessStatus": "verified",
                "sourceType": "기사", "originGroupId": None,
            }],
            "claims": [], "evidence": [],
            "llmModel": "gpt-6-luna", "llmReasoning": "max",
        },
        {
            "answer": {
                "status": "grounded",
                "overview": {"text": "개요입니다.", "citations": [{
                    "sourceId": "s1", "quote": "Verified source text.",
                }]},
                "sections": [],
                "conclusion": {"text": "결론입니다.", "citations": [{
                    "sourceId": "s1", "quote": "Verified source text.",
                }]},
                "model": "gemini-3.8-flash", "reasoning": "high",
            },
            "answerModel": "gemini-3.8-flash",
            "answerReasoning": "high",
        },
    )

    assert result.model == "gpt-6-luna"
    assert result.reasoning == "max"
    assert result.answer.model == "gemini-3.8-flash"
    assert result.answer.reasoning == "high"


def test_runtime_finalization_skips_provider_without_verified_source_text(monkeypatch):
    import httpx
    import runtime
    from runtime import make_runtime_adapters

    def unexpected_client(*args, **kwargs):
        raise AssertionError("No readable source text must not open a provider client")

    monkeypatch.setattr(runtime.httpx, "AsyncClient", unexpected_client)
    adapters = make_runtime_adapters(Settings(
        api_key=SecretStr("openai-test-only"),
        gemini_api_key=SecretStr("gemini-test-only"),
    ))

    result = asyncio.run(adapters.synthesize({
        "sources": [{
            "id": "s1", "url": "https://example.org/source", "accessStatus": "verified",
            "sourceType": "기사",
        }],
        "sourceTexts": {"s1": "  "},
    }))

    assert result["answer"]["status"] == "judgment_only"
    assert result["answerModel"] is None
    assert result["answerReasoning"] is None


def test_finalization_failure_does_not_return_intermediate_result():
    import pytest

    source = {
        "id": "s1", "url": "https://example.org/source", "title": "Example source",
        "publisher": "example.org", "publishedAt": None,
        "retrievedAt": "2026-09-20T00:00:00+00:00", "accessStatus": "verified",
        "sourceType": "기사", "originGroupId": None,
    }

    async def extract(state):
        return {}

    async def search(state):
        return {"sources": [source]}

    async def read(state):
        return {"sources": [source], "sourceTexts": {"s1": "Verified source text."}}

    async def verify(state):
        return {"claims": [], "evidence": [], "llmModel": "gpt-6-luna", "llmReasoning": "max"}

    async def synthesize(state):
        raise RuntimeError("TEST_ONLY synthesis stage failure")

    graph = build_runtime_workflow(
        Settings(api_key=SecretStr("test-only")),
        adapters=RuntimeAdapters(
            extract=extract, search=search, read=read, verify=verify, synthesize=synthesize,
        ),
    )

    with pytest.raises(RuntimeError, match="TEST_ONLY synthesis stage failure"):
        asyncio.run(graph.ainvoke({"text": "Claim", "focus": "", "consent": True}))


def test_result_exposes_youtube_comments_only_as_context_not_verified_content():
    result = build_fact_check_result(
        {
            "text": "Claim",
            "focus": "",
            "consent": True,
            "sources": [{
                "id": "s1",
                "url": "https://www.youtube.com/watch?v=aB_12345678",
                "title": "Search title",
                "youtubeTitle": "API video title",
                "youtubeChannelTitle": "API channel",
                "youtubePublishedAt": "2026-09-20T12:30:00Z",
                "youtubeViewCount": "1234567",
                "youtubeComments": ["Raw public comment"],
                "youtubeDataStatus": "collected",
                "publisher": "www.youtube.com",
                "accessStatus": "unavailable",
                "sourceType": "유튜브",
                "originGroupId": "youtube",
            }],
            "claims": [],
            "evidence": [],
        },
        {
            "answer": {
                "status": "insufficient_evidence", "overview": None, "sections": [],
                "conclusion": None, "model": None, "reasoning": None,
            },
            "answerModel": None,
            "answerReasoning": None,
        },
    )

    parsed = FactCheckResponse.model_validate({"result": result.model_dump(mode="json")}).result
    assert parsed.sources[0].youtubeTitle == "API video title"
    assert parsed.sources[0].youtubeChannelTitle == "API channel"
    assert parsed.sources[0].youtubePublishedAt == "2026-09-20T12:30:00Z"
    assert parsed.sources[0].youtubeViewCount == "1234567"
    assert parsed.sources[0].youtubeComments == ["Raw public comment"]
    assert parsed.sources[0].accessStatus == "unavailable"
    assert any("유튜브 공개 댓글" in warning for warning in parsed.warnings)


def test_youtube_comment_warning_skipped_for_transcript_sources():
    from runtime import _result_warnings

    youtube = [{"sourceType": "유튜브"}]
    assert any("댓글" in warning for warning in _result_warnings(youtube))
    assert not any(
        "댓글" in warning
        for warning in _result_warnings(youtube, youtube_transcript_verified=True)
    )
