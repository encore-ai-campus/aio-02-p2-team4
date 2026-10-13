"""Tavily search discovery; no live traffic (all transports mocked)."""
import asyncio

import httpx


def tavily_response(results):
    return httpx.Response(200, json={
        "query": "AGI 2030년",
        "results": results,
        "response_time": 0.5,
    })


def run_search(state, handler, api_key="tvly-test"):
    from tavily_search import search_tavily

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_tavily(state, api_key=api_key, client=client)

    return asyncio.run(run())


def test_tavily_results_become_ranked_sources():
    def handler(request):
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers["authorization"] == "Bearer tvly-test"
        return tavily_response([
            {"title": "AGI outlook", "url": "https://www.aitimes.com/news/1", "content": "Snippet one.", "score": 0.9},
            {"title": "AGI report", "url": "https://example.org/report", "content": "Snippet two.", "score": 0.8},
        ])

    result = run_search({
        "consent": True,
        "claims": [{"id": "c1", "kind": "fact", "quote": "AGI는 2030년 안에 오나?"}],
        "searchQueries": {"c1": "AGI 2030년"},
    }, handler)
    assert [s["id"] for s in result["sources"]] == ["s1", "s2"]
    assert all(s["searchProvider"] == "tavily_search" for s in result["sources"])
    assert result["sources"][0]["url"] == "https://www.aitimes.com/news/1"
    assert result["sources"][0]["searchQuery"] == "AGI 2030년"


def test_tavily_failure_modes_raise_tavily_unavailable():
    import pytest

    from tavily_search import TavilyUnavailable

    cases = [
        httpx.Response(429, json={"error": "rate limited"}),
        httpx.Response(200, json={"error": "bad key"}),
        httpx.Response(200, json=["not", "a", "dict"]),
        httpx.Response(200, json={"query": "x"}),
    ]
    for response in cases:
        def handler(request, response=response):
            return response

        with pytest.raises(TavilyUnavailable):
            run_search({
                "consent": True,
                "claims": [{"id": "c1", "kind": "fact", "quote": "Claim"}],
            }, handler)


def test_tavily_missing_key_and_consent_are_rejected():
    import pytest

    from tavily_search import TavilyUnavailable

    state = {"consent": True, "claims": [{"id": "c1", "kind": "fact", "quote": "Claim"}]}
    with pytest.raises(TavilyUnavailable):
        run_search(state, lambda request: tavily_response([]), api_key="  ")
    with pytest.raises(ValueError):
        run_search({**state, "consent": False}, lambda request: tavily_response([]))
