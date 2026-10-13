"""Link and image attachment paths; no external traffic (all transports mocked)."""
import asyncio
import base64
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError


def test_request_accepts_blank_text_only_with_image():
    from schemas import FactCheckRequest

    payload = {
        "text": "", "focus": "", "consent": True,
        "image": {"mime": "image/jpeg", "data": base64.b64encode(b"x" * 100).decode()},
    }
    request = FactCheckRequest.model_validate(payload)
    assert request.text == "" and request.image is not None


def test_request_rejects_blank_text_without_image():
    from schemas import FactCheckRequest

    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate({"text": "  ", "focus": "", "consent": True})


def test_request_rejects_bad_link_and_image():
    from schemas import FactCheckRequest

    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate(
            {"text": "hi", "focus": "", "consent": True, "linkUrl": "ftp://x/y"})
    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate(
            {"text": "hi", "focus": "", "consent": True,
             "image": {"mime": "image/gif", "data": "eA=="}})
    with pytest.raises(ValidationError):
        FactCheckRequest.model_validate(
            {"text": "hi", "focus": "", "consent": True,
             "image": {"mime": "image/png", "data": "!!!"}})


def test_structured_image_payload_shapes():
    from providers import LLMProvider, request_structured_image

    seen = {}

    def handler(request):
        seen[request.url.host] = json.loads(request.content)
        if "openai" in request.url.host:
            return httpx.Response(200, json={"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]})
        return httpx.Response(200, json={"status": "completed", "output_text": "{}"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gemini = LLMProvider("gemini", "gemini-3.8-flash", "high", "k")
            await request_structured_image(
                gemini, client, instructions="i", input_data={"caption": "c"},
                image={"mime": "image/jpeg", "data": "eA=="},
                schema={"type": "object"}, max_output_tokens=10)
            openai = LLMProvider("openai", "gpt-6-luna", "max", "k")
            await request_structured_image(
                openai, client, instructions="i", input_data={"caption": "c"},
                image={"mime": "image/png", "data": "eA=="},
                schema={"type": "object"}, max_output_tokens=10)

    asyncio.run(run())
    parts = seen["generativelanguage.googleapis.com"]["input"]
    assert parts[0] == {"type": "text", "text": '{"caption": "c"}'}
    assert parts[1] == {"type": "image", "data": "eA==", "mime_type": "image/jpeg"}
    content = seen["api.openai.com"]["input"]
    assert content[0]["role"] == "user"
    assert content[0]["content"][1] == {
        "type": "input_image", "image_url": "data:image/png;base64,eA=="}


def test_extract_image_claims_replaces_state_text(monkeypatch):
    import extraction
    from providers import LLMProvider

    async def fake_image(provider, client, **kwargs):
        assert kwargs["image"] == {"mime": "image/jpeg", "data": "eA=="}
        return json.dumps({"observedText": "Zucc is a lizard.", "claims": [
            {"quote": "Zucc is a lizard", "kind": "fact", "searchQuery": "Zucc lizard"}]})

    monkeypatch.setattr(extraction, "request_structured_image", fake_image)
    state = {"text": "", "focus": "", "consent": True,
             "image": {"mime": "image/jpeg", "data": "eA=="}}
    update = asyncio.run(extraction.extract_image_claims(
        state, state["image"], client=None,
        provider=LLMProvider("gemini", "gemini-3.8-flash", "high", "k")))
    assert update["text"] == "Zucc is a lizard."
    assert update["claims"][0]["start"] == 0
    assert update["searchQueries"] == {"c1": "Zucc lizard"}


def test_extract_page_claims_replaces_state_text(monkeypatch):
    import extraction
    from providers import LLMProvider

    async def fake_structured(provider, client, **kwargs):
        assert kwargs["input_data"] == {"text": "Page body text.", "focus": ""}
        return json.dumps({"claims": [
            {"quote": "Page body", "kind": "fact", "searchQuery": ""}]})

    monkeypatch.setattr(extraction, "request_structured", fake_structured)
    update = asyncio.run(extraction.extract_page_claims(
        "Page body text.", client=None,
        provider=LLMProvider("openai", "gpt-6-luna", "max", "k")))
    assert update["text"] == "Page body text."
    assert update["claims"][0]["quote"] == "Page body"
    assert "searchQueries" not in update


def test_read_prepends_link_seed_without_network(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    async def fake_read(state, reader=None, youtube_reader=None, extractor=None):
        return {"sources": state["sources"], "sourceTexts": {}, "sourceSections": {}}

    monkeypatch.setattr(runtime, "read_sources", fake_read)
    settings = Settings(api_key=SecretStr(""))
    adapters = make_runtime_adapters(settings)
    state = {"sources": [{"id": "s1", "url": "https://example.org/a"}],
             "linkUrl": "https://example.com/page"}
    update = asyncio.run(adapters.read(state))
    assert update["sources"][0]["id"] == "s0"
    assert update["sources"][0]["url"] == "https://example.com/page"
    assert update["sources"][0]["accessStatus"] == "pending"


def test_read_searches_related_coverage_from_the_linked_page_title(monkeypatch):
    import runtime
    from sources import SourceReadResult
    from runtime import Settings, make_runtime_adapters

    async def fake_fetch(url):
        return SourceReadResult("Linked article body.", url, "Test Title Query")

    seen_queries = []

    real_async_client = httpx.AsyncClient

    def handler(request):
        seen_queries.append(json.loads(request.content)["query"])
        return httpx.Response(200, json={
            "query": "Test Title Query",
            "results": [{"title": "Related", "url": "https://example.org/related", "content": "Snippet."}],
        })

    def mock_async_client(**kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    async def fake_read(state, reader=None, youtube_reader=None, extractor=None):
        assert reader is not None
        texts = {}
        for source in state["sources"]:
            text, _ = await reader(source["url"])
            texts[source["id"]] = text
        return {"sources": state["sources"], "sourceTexts": texts, "sourceSections": {}}

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(runtime, "read_sources", fake_read)
    monkeypatch.setattr(runtime.httpx, "AsyncClient", mock_async_client)
    settings = Settings(
        api_key=SecretStr(""),
        tavily_api_key=SecretStr("tvly-test"),
    )
    adapters = make_runtime_adapters(settings)
    update = asyncio.run(adapters.read({
        "sources": [], "linkUrl": "https://example.com/page", "consent": True,
    }))
    assert [s["id"] for s in update["sources"]] == ["s0", "s1"]
    assert update["sources"][1]["url"] == "https://example.org/related"
    assert seen_queries == ["Test Title Query"]


def test_workflow_preserves_link_and_image_state_keys():
    from workflow import build_workflow

    seen = {}

    async def capture(state):
        seen.update({key: state.get(key) for key in ("text", "linkUrl", "image")})
        return {}

    graph = build_workflow(
        extract=capture, search=capture, read=capture, verify=capture, synthesize=capture)
    asyncio.run(graph.ainvoke({
        "text": "https://example.com/", "focus": "", "consent": True,
        "linkUrl": "https://example.com/",
        "image": {"mime": "image/jpeg", "data": "eA=="},
    }))
    assert seen == {
        "text": "https://example.com/",
        "linkUrl": "https://example.com/",
        "image": {"mime": "image/jpeg", "data": "eA=="},
    }


def test_extract_url_only_fetches_page(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    async def fake_fetch(url):
        assert url == "https://example.com/page"
        return ("Fetched page body.", url)

    async def fake_page(page_text, **kwargs):
        assert page_text == "Fetched page body."
        return {"claims": [{"id": "c1", "quote": "Fetched page", "kind": "fact",
                            "start": 0, "end": 12}], "text": page_text}

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(runtime, "extract_page_claims", fake_page)
    settings = Settings(api_key=SecretStr("test-only"))
    adapters = make_runtime_adapters(settings)
    state = {"text": "https://example.com/page", "focus": "", "consent": True,
             "linkUrl": "https://example.com/page"}
    update = asyncio.run(adapters.extract(state))
    assert update["text"] == "Fetched page body."
    assert update["llmModel"] == "gpt-6-luna"


def test_extract_url_only_truncates_long_pages_to_the_contract_limit(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    long_page = '가' * 15000

    async def fake_fetch(url):
        return (long_page, url)

    async def fake_page(page_text, **kwargs):
        assert len(page_text.encode('utf-16-le')) // 2 <= 12000
        return {'claims': [], 'text': page_text}

    monkeypatch.setattr(runtime, 'fetch_public_text', fake_fetch)
    monkeypatch.setattr(runtime, 'extract_page_claims', fake_page)
    settings = Settings(api_key=SecretStr('test-only'))
    adapters = make_runtime_adapters(settings)
    state = {'text': 'https://example.com/page', 'focus': '', 'consent': True,
             'linkUrl': 'https://example.com/page'}
    update = asyncio.run(adapters.extract(state))
    assert len(update['text'].encode('utf-16-le')) // 2 <= 12000


def test_extract_link_with_extra_words_falls_back_to_page(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    async def fake_fetch(url):
        assert url == "https://example.com/page"
        return ("Fetched page body.", url)

    async def fake_claims(state, **kwargs):
        return {"claims": []}

    async def fake_page(page_text, **kwargs):
        assert page_text == "Fetched page body."
        return {"claims": [{"id": "c1", "quote": "Fetched page", "kind": "fact",
                            "start": 0, "end": 12}], "text": page_text}

    monkeypatch.setattr(runtime, "fetch_public_text", fake_fetch)
    monkeypatch.setattr(runtime, "extract_claims", fake_claims)
    monkeypatch.setattr(runtime, "extract_page_claims", fake_page)
    settings = Settings(api_key=SecretStr("test-only"))
    adapters = make_runtime_adapters(settings)
    state = {"text": "https://example.com/page 팩트체크해줘", "focus": "", "consent": True,
             "linkUrl": "https://example.com/page"}
    update = asyncio.run(adapters.extract(state))
    assert update["text"] == "Fetched page body."
    assert update["claims"][0]["quote"] == "Fetched page"


def test_extract_link_with_real_claims_keeps_draft_text(monkeypatch):
    import runtime
    from runtime import Settings, make_runtime_adapters

    async def no_fetch(url):
        raise AssertionError("page fetch must not run when the draft yields claims")

    async def fake_claims(state, **kwargs):
        return {"claims": [{"id": "c1", "quote": "Draft claim", "kind": "fact",
                            "start": 0, "end": 11}]}

    monkeypatch.setattr(runtime, "fetch_public_text", no_fetch)
    monkeypatch.setattr(runtime, "extract_claims", fake_claims)
    settings = Settings(api_key=SecretStr("test-only"))
    adapters = make_runtime_adapters(settings)
    state = {"text": "Draft claim https://example.com/page", "focus": "", "consent": True,
             "linkUrl": "https://example.com/page"}
    update = asyncio.run(adapters.extract(state))
    assert "text" not in update
    assert update["claims"][0]["quote"] == "Draft claim"


def test_extract_youtube_link_with_words_falls_back_to_transcript(monkeypatch):
    import runtime
    import youtube
    from runtime import Settings, make_runtime_adapters

    async def fake_transcript(video_id):
        assert video_id == "aB_12345678"
        return {"text": "영상에서 설명합니다.", "status": "collected"}

    async def no_page_fetch(url):
        raise AssertionError("page fetch must not run for YouTube links with transcripts")

    async def fake_claims(state, **kwargs):
        return {"claims": []}

    async def fake_page(page_text, **kwargs):
        assert page_text == "영상에서 설명합니다."
        return {"claims": [{"id": "c1", "quote": "영상에서 설명", "kind": "fact",
                            "start": 0, "end": 8}], "text": page_text}

    monkeypatch.setattr(youtube, "fetch_transcript_text", fake_transcript)
    monkeypatch.setattr(runtime, "fetch_public_text", no_page_fetch)
    monkeypatch.setattr(runtime, "extract_claims", fake_claims)
    monkeypatch.setattr(runtime, "extract_page_claims", fake_page)
    settings = Settings(api_key=SecretStr("test-only"))
    adapters = make_runtime_adapters(settings)
    state = {"text": "https://www.youtube.com/watch?v=aB_12345678 파악해줘", "focus": "",
             "consent": True, "linkUrl": "https://www.youtube.com/watch?v=aB_12345678"}
    update = asyncio.run(adapters.extract(state))
    assert update["text"] == "영상에서 설명합니다."
    assert update["claims"][0]["quote"] == "영상에서 설명"


def test_extract_youtube_link_without_transcript_keeps_old_behavior(monkeypatch):
    import runtime
    import youtube
    from runtime import Settings, make_runtime_adapters

    async def no_transcript(video_id):
        return {"text": None, "status": "unavailable"}

    async def fake_page_fetch(url):
        return ("", url)

    async def fake_claims(state, **kwargs):
        return {"claims": []}

    monkeypatch.setattr(youtube, "fetch_transcript_text", no_transcript)
    monkeypatch.setattr(runtime, "fetch_public_text", fake_page_fetch)
    monkeypatch.setattr(runtime, "extract_claims", fake_claims)
    settings = Settings(api_key=SecretStr("test-only"))
    adapters = make_runtime_adapters(settings)
    state = {"text": "https://www.youtube.com/watch?v=aB_12345678 파악해줘", "focus": "",
             "consent": True, "linkUrl": "https://www.youtube.com/watch?v=aB_12345678"}
    update = asyncio.run(adapters.extract(state))
    assert update["claims"] == []
    assert "text" not in update
