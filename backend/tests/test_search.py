"""Offline search fixtures, not verified sources."""
import asyncio
import importlib.util
import json
import httpx
import pytest


@pytest.mark.parametrize(("urls", "expected"), [
    (["https://a.example/1", "https://b.example/2", "https://youtube.com/watch?v=3"],
     ["https://a.example/1", "https://b.example/2", "https://youtube.com/watch?v=3"]),
    (["https://dailymotion.com/1", "https://dailymotion.com/2", "https://dailymotion.com/3"],
     ["https://dailymotion.com/1", "https://dailymotion.com/2"]),
    (["https://a.example/story?id=1&utm_source=x", "https://a.example/story?id=1&utm_source=y", "https://a.example/story?id=2"],
     ["https://a.example/story?id=1&utm_source=x", "https://a.example/story?id=2"]),
    (["https://www.a.example/story/?utm_source=x", "https://a.example/story/"],
     ["https://www.a.example/story/?utm_source=x"]),
])
def test_search_preserves_candidate_order_and_strict_duplicate_limits(urls, expected):
    from search import search_sources

    def handler(request):
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed", "action": {
                "sources": [{"url": url, "title": f"Result {i}"} for i, url in enumerate(urls)],
            }},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources({"claims": [{"id": "c1", "quote": "AGI", "kind": "fact"}],
                                         "consent": True}, api_key="test-only", client=client)

    result = asyncio.run(run())
    assert [s["url"] for s in result["sources"]] == expected
    assert [s["id"] for s in result["sources"]] == [f"s{i+1}" for i in range(len(expected))]


def test_search_candidates_exclude_japanese_pages_across_providers():
    from search import _project_candidates

    sources = _project_candidates([
        {"url": "https://dx.mri.co.jp/agi", "title": "AGI forecast", "searchProvider": "openai_web_search", "searchQuery": "AGI 2030"},
        {"url": "https://example.com/jp", "title": "AGI ニュース", "searchProvider": "gemini_google_search", "searchQuery": "AGI 2030"},
        {"url": "https://news.example.kr/agi", "title": "한국 AGI 전망", "searchProvider": "openai_web_search", "searchQuery": "AGI 2030"},
    ])

    assert [source["url"] for source in sources] == ["https://news.example.kr/agi"]


def test_search_candidates_exclude_naver_kin_answers():
    from search import _project_candidates

    sources = _project_candidates([
        {"url": "https://kin.naver.com/qna/detail.naver?d1id=1&dirId=1&docId=123", "title": "마크저커버그 뱀파이어인가요", "searchProvider": "serpapi_google", "searchQuery": "마크저커버그"},
        {"url": "https://m.kin.naver.com/qna/detail.naver?d1id=1&dirId=2&docId=456", "title": "모바일 지식인 답변", "searchProvider": "gemini_google_search", "searchQuery": "마크저커버그"},
        {"url": "https://namu.wiki/w/reptilian", "title": "렙틸리언", "searchProvider": "serpapi_google", "searchQuery": "마크저커버그"},
    ])

    assert [source["url"] for source in sources] == ["https://namu.wiki/w/reptilian"]


def test_search_candidates_exclude_reported_ad_doorway_hosts():
    from search import _project_candidates

    sources = _project_candidates([
        {"url": "https://sziaeletem.hu/cikk/reptilian-zuckerberg", "title": "광고 도어웨이", "searchProvider": "serpapi_google", "searchQuery": "마크저커버그"},
        {"url": "https://namu.wiki/w/reptilian", "title": "렙틸리언", "searchProvider": "serpapi_google", "searchQuery": "마크저커버그"},
    ])

    assert [source["url"] for source in sources] == ["https://namu.wiki/w/reptilian"]


def _finance_candidate(url, title="t"):
    return {"url": url, "title": title, "searchProvider": "openai_web_search",
            "searchQuery": "테슬라 실적", "originGroupId": url,
            "accessStatus": "pending"}


def test_preferred_finance_hosts_move_first_for_stock_questions():
    from search import _select_diverse_sources

    candidates = [
        _finance_candidate("https://blog.example.com/tesla"),
        _finance_candidate("https://www.bloomberg.com/tesla-earnings"),
        _finance_candidate("https://news.example.kr/tesla"),
        _finance_candidate("https://www.reuters.com/tesla-results"),
    ]
    selected = _select_diverse_sources(candidates, prefer_finance=True)
    assert [s["url"] for s in selected[:2]] == [
        "https://www.bloomberg.com/tesla-earnings",
        "https://www.reuters.com/tesla-results",
    ]
    assert len(selected) == 4


def test_finance_boost_off_preserves_provider_order():
    from search import _select_diverse_sources

    candidates = [
        _finance_candidate("https://blog.example.com/tesla"),
        _finance_candidate("https://www.bloomberg.com/tesla-earnings"),
    ]
    selected = _select_diverse_sources(candidates)
    assert [s["url"] for s in selected] == [
        "https://blog.example.com/tesla",
        "https://www.bloomberg.com/tesla-earnings",
    ]


def test_finance_match_covers_subdomains():
    from search import is_preferred_finance_host

    assert is_preferred_finance_host("https://kr.reuters.com/article") is True
    assert is_preferred_finance_host("https://www.investing.com/equities/tesla") is True
    assert is_preferred_finance_host("https://fakeinvesting.com/x") is False
    assert is_preferred_finance_host("not a url") is False


def test_search_collects_deduplicated_candidates_without_evidence():
    assert importlib.util.find_spec("search") is not None, "Search adapter missing"
    from search import search_sources

    def handler(request):
        body = json.loads(request.content)
        assert body["tools"][0]["type"] == "web_search"
        assert body["tools"][0]["search_context_size"] == "medium"
        assert "user_location" not in body["tools"][0]
        assert body["include"] == ["web_search_call.action.sources"]
        assert body["max_tool_calls"] == 4
        assert len(body["input"]) > 0
        assert body["store"] is False
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed", "action": {"sources": [
                {"url": "https://EXAMPLE.org/article#one"}, {"url": "https://example.org/article#two"}]}},
            {"type": "message", "content": [{"type": "output_text", "text": "Not evidence", "annotations": [
                {"type": "url_citation", "url": "https://example.org/article", "title": "Source title"}]}]}
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources({"claims": [{"id": "c1", "quote": "Claim", "kind": "fact"}], "focus": "", "consent": True}, api_key="test-only", client=client)

    result = asyncio.run(run())
    assert result == {"sources": [{
        "id": "s1",
        "url": "https://example.org/article",
        "title": "Source title",
        "publisher": "example.org",
        "sourceType": "웹 출처",
        "originGroupId": "example.org",
        "accessStatus": "pending",
        "searchProvider": "openai_web_search",
        "searchQuery": "Claim",
        "candidateOrder": 1,
    }]}


def test_search_keeps_completed_sources_when_response_has_nonterminal_search_item():
    from search import search_sources

    def handler(request):
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed", "action": {"sources": [
                {"url": "https://example.org/primary", "title": "Primary source"}]}},
            {"type": "web_search_call", "status": "searching"},
            {"type": "message", "content": []},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources(
                {"claims": [{"id": "c1", "quote": "Claim", "kind": "fact"}], "focus": "", "consent": True},
                api_key="test-only",
                client=client,
            )

    assert asyncio.run(run()) == {
        "sources": [{
            "id": "s1",
            "url": "https://example.org/primary",
            "title": "Primary source",
            "publisher": "example.org",
            "sourceType": "웹 출처",
            "originGroupId": "example.org",
            "accessStatus": "pending",
            "searchProvider": "openai_web_search",
            "searchQuery": "Claim",
            "candidateOrder": 1,
        }]
    }


def test_search_keeps_completed_sources_when_response_hits_output_token_limit():
    from search import search_sources

    def handler(request):
        return httpx.Response(200, json={
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {"type": "web_search_call", "status": "completed", "action": {"sources": [
                    {"url": "https://example.org/primary", "title": "Primary source"},
                ]}},
                {"type": "web_search_call", "status": "searching"},
            ],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources(
                {"claims": [{"id": "c1", "quote": "AGI 2030", "kind": "prediction"}],
                 "focus": "", "consent": True},
                api_key="test-only",
                client=client,
            )

    assert [source["url"] for source in asyncio.run(run())["sources"]] == [
        "https://example.org/primary"
    ]


def test_search_still_rejects_token_limited_response_without_completed_search():
    from search import search_sources

    def handler(request):
        return httpx.Response(200, json={
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "web_search_call", "status": "searching"}],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources(
                {"claims": [{"id": "c1", "quote": "AGI 2030", "kind": "prediction"}],
                 "focus": "", "consent": True},
                api_key="test-only",
                client=client,
            )

    with pytest.raises(ValueError, match="SEARCH_FAILED"):
        asyncio.run(run())


def test_search_selects_diverse_source_types_instead_of_one_publisher():
    from search import search_sources

    def handler(request):
        body = json.loads(request.content)
        plan = json.loads(body["input"])["searchPlan"]
        assert {item["sourceType"] for item in plan} >= {
            "한국 기사",
            "한국 블로그",
            "커뮤니티",
            "유튜브",
        }
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed", "action": {"sources": [
                {"url": "https://blog.google/one", "title": "Google one"},
                {"url": "https://blog.google/two", "title": "Google two"},
                {"url": "https://deepmind.google/three", "title": "Google three"},
                {"url": "https://www.hankyung.com/ai/article", "title": "한국 경제 기사"},
                {"url": "https://blog.naver.com/example/post", "title": "한국 블로그 글"},
                {"url": "https://www.reddit.com/r/artificial/comments/example", "title": "Reddit discussion"},
                {"url": "https://www.youtube.com/watch?v=example", "title": "YouTube interview"},
                {"url": "https://www.nytimes.com/2026/01/01/ai.html", "title": "International report"},
            ]}},
            {"type": "message", "content": []},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources(
                {"claims": [{"id": "c1", "quote": "아스트라가 AGI인가", "kind": "unclear"}], "focus": "", "consent": True},
                api_key="test-only",
                client=client,
            )

    sources = asyncio.run(run())["sources"]
    assert len(sources) == 6
    assert {source["sourceType"] for source in sources} >= {
        "공식·기술 문서",
        "한국 기사",
        "한국 블로그",
        "Reddit",
        "유튜브",
    }
    assert sum(source["originGroupId"] == "google" for source in sources) <= 2


def test_search_supports_gemini_google_search_citations():
    from providers import LLMProvider
    from search import search_sources

    def handler(request):
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "gemini-test-only"
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.8-flash"
        assert body["tools"] == [{"type": "google_search"}]
        assert body["generation_config"]["thinking_level"] == "high"
        assert body["generation_config"]["tool_choice"] == "any"
        assert "tool_choice" not in body
        return httpx.Response(200, json={
            "status": "completed",
            "steps": [
                {"type": "google_search_call", "arguments": {"queries": ["claim"]}},
                {"type": "model_output", "content": [{
                    "type": "text",
                    "text": "A grounded answer.",
                    "annotations": [{
                        "type": "url_citation",
                        "url": "https://example.org/gemini-source",
                        "title": "Gemini source",
                    }],
                }]},
            ],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources(
                {"claims": [{"id": "c1", "quote": "Claim", "kind": "fact"}], "focus": "", "consent": True},
                client=client,
                provider=LLMProvider("gemini", "gemini-3.8-flash", "high", "gemini-test-only"),
            )

    assert asyncio.run(run())["sources"] == [{
        "id": "s1",
        "url": "https://example.org/gemini-source",
        "title": "Gemini source",
        "publisher": "example.org",
        "sourceType": "웹 출처",
        "originGroupId": "example.org",
        "accessStatus": "pending",
        "searchProvider": "gemini_google_search",
        "searchQuery": "Claim",
        "candidateOrder": 1,
    }]


def test_build_search_query_keeps_entity_and_year_from_forecast_question():
    from search import build_search_query

    assert build_search_query("AGI는 2030년 안에 오나?") == "AGI 2030년"


@pytest.mark.parametrize(("question", "expected"), [
    ("  AGI는   2030년 안에 오나요?  ", "AGI 2030년"),
    ("AGI는 2030년까지 오지 않는다", "AGI 2030년까지 오지 않는다"),
    ("Is AGI unlikely before 2030?", "Is AGI unlikely before 2030"),
    ("가수 아이유 은퇴설", "가수 아이유 은퇴설"),
    ("GPT-5.6 가격 20달러", "GPT-5.6 가격 20달러"),
])
def test_query_fallback_preserves_negation_names_and_numbers(question, expected):
    from search import build_search_query

    assert build_search_query(question) == expected


def test_prediction_claims_are_searched_with_primary_query_in_provider_order():
    from search import search_sources

    requested = False

    def handler(request):
        nonlocal requested
        requested = True
        body = json.loads(request.content)
        search_input = json.loads(body["input"])
        assert body["tools"][0]["user_location"] == {"type": "approximate", "country": "KR"}
        assert search_input["primaryQueries"] == ["AGI 2030년"]
        assert search_input["claims"][0]["searchQuery"] == "AGI 2030년"
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed", "action": {"sources": [
                {"url": "https://first.example/report", "title": "First result"},
                {"url": "https://second.example/report", "title": "Second result"},
            ]}},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_sources(
                {
                    "claims": [{"id": "c1", "quote": "AGI는 2030년 안에 오나?", "kind": "prediction"}],
                    "focus": "",
                    "consent": True,
                },
                api_key="test-only",
                client=client,
            )

    result = asyncio.run(run())
    assert requested is True
    assert [source["url"] for source in result["sources"]] == [
        "https://first.example/report",
        "https://second.example/report",
    ]
    assert [source["candidateOrder"] for source in result["sources"]] == [1, 2]
    assert {source["searchQuery"] for source in result["sources"]} == {"AGI 2030년"}


def test_aitimes_is_classified_as_korean_news_in_google_results():
    from search import source_type_for_url

    assert source_type_for_url("https://www.aitimes.com/news/articleView.html?idxno=123") == "한국 기사"
