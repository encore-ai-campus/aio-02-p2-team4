"""Tavily search discovery; no live traffic (all transports mocked)."""
import asyncio
import json

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


def test_youtube_search_is_restricted_and_kept_within_six_sources():
    requests = []
    excluded_video = "https://www.youtube.com/watch?v=abcdefghijk"
    kept_video = "https://www.youtube.com/watch?v=lmnopqrstuv"

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if "include_domains" in body:
            return tavily_response([
                {"url": "https://www.youtube.com/@channel", "title": "Channel", "content": "Context."},
                {"url": excluded_video, "title": "Excluded video", "content": "Context."},
                {"url": kept_video, "title": "Related video", "content": "Context."},
            ])
        query = body["query"].lower()
        return tavily_response([
            {"url": f"https://{query}{index}.example/reference", "title": "Reference", "content": "Context."}
            for index in range(3)
        ])

    result = run_search({
        "consent": True,
        "claims": [
            {"id": "c1", "kind": "fact", "quote": "Alpha claim"},
            {"id": "c2", "kind": "fact", "quote": "Beta claim"},
        ],
        "searchQueries": {"c1": "Alpha", "c2": "Beta"},
        "excludedSourceUrls": [excluded_video],
    }, handler)

    restricted = [body for body in requests if "include_domains" in body]
    assert len(requests) == 4
    assert {body["query"] for body in restricted} == {"Alpha", "Beta"}
    assert all(body["include_domains"] == ["youtube.com", "youtu.be"] for body in restricted)
    assert all(body["include_domains_mode"] == "restrict" for body in restricted)
    assert len(result["sources"]) == 6
    assert result["sources"][-1]["url"] == kept_video
    assert result["sources"][-1]["sourceType"] == "유튜브"
    assert all(source["url"] != excluded_video for source in result["sources"])


def test_youtube_search_failure_preserves_general_sources(caplog):
    def handler(request):
        if "include_domains" in json.loads(request.content):
            return httpx.Response(503, json={"error": "unavailable"})
        return tavily_response([
            {"url": "https://example.org/report", "title": "Report", "content": "Context."},
        ])

    result = run_search({
        "consent": True,
        "claims": [{"id": "c1", "kind": "fact", "quote": "Claim"}],
    }, handler)
    assert [source["url"] for source in result["sources"]] == ["https://example.org/report"]
    assert "Separate YouTube search failed" in caplog.text


def test_supplemental_title_search_does_not_repeat_youtube_search():
    from tavily_search import search_tavily

    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return tavily_response([])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_tavily(
                {"consent": True}, api_key="tvly-test", client=client, queries=["Link title"],
            )

    assert asyncio.run(run()) == {"sources": []}
    assert len(requests) == 1
    assert requests[0]["query"] == "Link title"
    assert "include_domains" not in requests[0]
