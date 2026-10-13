"""Offline YouTube Data API contract tests; no Google credentials or traffic."""
import asyncio

import httpx

from youtube import MAX_COMMENT_COUNT, fetch_youtube_data, youtube_video_id


def test_youtube_video_id_accepts_video_urls_and_rejects_lookalikes():
    video_id = "aB_12345678"
    assert youtube_video_id(f"https://www.youtube.com/watch?v={video_id}&feature=share") == video_id
    assert youtube_video_id(f"https://youtu.be/{video_id}?si=tracking") == video_id
    assert youtube_video_id(f"https://youtube.com/shorts/{video_id}") == video_id
    assert youtube_video_id(f"https://youtu.be/{video_id}/extra") is None
    assert youtube_video_id(f"https://youtube.com.evil.test/watch?v={video_id}") is None
    assert youtube_video_id("https://www.youtube.com/channel/not-a-video") is None


def test_fetches_official_video_title_and_bounded_plain_text_comments(monkeypatch):
    import youtube

    requests = []
    metadata = {
        "title": "AGI 전망 인터뷰",
        "channelTitle": "AI 연구 채널",
        "publishedAt": "2026-09-20T12:30:00Z",
        "viewCount": "1234567",
    }

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/videos"):
            return httpx.Response(200, json={"items": [{
                "snippet": {
                    "title": metadata["title"],
                    "channelTitle": metadata["channelTitle"],
                    "publishedAt": metadata["publishedAt"],
                },
                "statistics": {"viewCount": metadata["viewCount"]},
            }]})
        return httpx.Response(200, json={"items": [
            {"snippet": {"topLevelComment": {"snippet": {"textDisplay": f"댓글 {index}"}}}}
            for index in range(20)
        ]})

    async def fake_transcript(video_id):
        assert video_id == "aB_12345678"
        return {"text": "자막 본문입니다.", "status": "collected"}

    monkeypatch.setattr(youtube, "fetch_transcript_text", fake_transcript)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_youtube_data(
                "https://www.youtube.com/watch?v=aB_12345678",
                api_key="youtube-test-key",
                client=client,
            )

    result = asyncio.run(run())
    assert result == {
        **metadata,
        "comments": [f"댓글 {index}" for index in range(MAX_COMMENT_COUNT)],
        "status": "collected",
        "transcript": "자막 본문입니다.",
        "transcriptStatus": "collected",
    }
    assert len(requests) == 2
    video_request, comments_request = requests
    assert video_request.url.host == "www.googleapis.com"
    assert video_request.url.path.endswith("/youtube/v3/videos")
    assert video_request.url.params["part"] == "snippet,statistics"
    assert video_request.url.params["id"] == "aB_12345678"
    assert video_request.url.params["key"] == "youtube-test-key"
    assert comments_request.url.path.endswith("/youtube/v3/commentThreads")
    assert comments_request.url.params["videoId"] == "aB_12345678"
    assert comments_request.url.params["maxResults"] == str(MAX_COMMENT_COUNT)
    assert comments_request.url.params["textFormat"] == "plainText"
    assert "author" not in str(result).lower()


def test_comments_unavailable_keeps_video_title_without_exposing_provider_error():
    def handler(request):
        if request.url.path.endswith("/videos"):
            return httpx.Response(200, json={"items": [{
                "snippet": {
                    "title": "제목",
                    "channelTitle": "채널",
                    "publishedAt": "2026-09-20T12:30:00Z",
                },
                "statistics": {"viewCount": "42"},
            }]})
        return httpx.Response(403, json={"error": {"message": "private diagnostic"}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_youtube_data(
                "https://youtu.be/aB_12345678",
                api_key="youtube-test-key",
                client=client,
            )

    assert asyncio.run(run()) == {
        "title": "제목",
        "channelTitle": "채널",
        "publishedAt": "2026-09-20T12:30:00Z",
        "viewCount": "42",
        "comments": [],
        "status": "unavailable",
    }


def test_low_reach_video_skips_comment_fetch():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [{
            "snippet": {
                "title": "제목",
                "channelTitle": "채널",
                "publishedAt": "2026-09-20T12:30:00Z",
            },
            "statistics": {"viewCount": "9"},
        }]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_youtube_data(
                "https://www.youtube.com/watch?v=aB_12345678",
                api_key="youtube-test-key",
                client=client,
            )

    assert asyncio.run(run()) == {
        "title": "제목",
        "channelTitle": "채널",
        "publishedAt": "2026-09-20T12:30:00Z",
        "viewCount": "9",
        "comments": [],
        "status": "unavailable",
    }
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/youtube/v3/videos")


def test_missing_key_or_invalid_video_url_makes_no_api_request():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500)

    async def run(url, key):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_youtube_data(url, api_key=key, client=client)

    assert asyncio.run(run("https://youtube.com/watch?v=aB_12345678", "")) == {
        "title": None, "channelTitle": None, "publishedAt": None, "viewCount": None,
        "comments": [], "status": "not_configured"
    }
    assert asyncio.run(run("https://youtube.com/channel/abc", "test-key")) == {
        "title": None, "channelTitle": None, "publishedAt": None, "viewCount": None,
        "comments": [], "status": "unavailable"
    }
    assert requests == []


def test_oversized_api_payload_is_treated_as_unavailable():
    def handler(request):
        if request.url.path.endswith("/videos"):
            return httpx.Response(200, json={"items": [{"snippet": {
                "title": "제목", "channelTitle": "채널",
                "publishedAt": "2026-09-20T12:30:00Z",
            }, "statistics": {"viewCount": "42"}}]})
        return httpx.Response(200, content=b"{" + b" " * 300_000 + b"}", headers={"content-type": "application/json"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_youtube_data(
                "https://youtube.com/watch?v=aB_12345678",
                api_key="youtube-test-key",
                client=client,
            )

    assert asyncio.run(run()) == {
        "title": "제목", "channelTitle": "채널",
        "publishedAt": "2026-09-20T12:30:00Z", "viewCount": "42",
        "comments": [], "status": "unavailable",
    }


def test_ignores_malformed_youtube_metadata_without_rejecting_comments():
    def handler(request):
        if request.url.path.endswith("/videos"):
            return httpx.Response(200, json={"items": [{
                "snippet": {
                    "title": "제목",
                    "channelTitle": "채널" * 200,
                    "publishedAt": "not-a-date",
                },
                "statistics": {"viewCount": "12 views"},
            }]})
        return httpx.Response(200, json={"items": []})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_youtube_data(
                "https://youtube.com/watch?v=aB_12345678",
                api_key="youtube-test-key",
                client=client,
            )

    result = asyncio.run(run())
    assert result["title"] == "제목"
    assert result["channelTitle"] is None
    assert result["publishedAt"] is None
    assert result["viewCount"] is None
    assert result["comments"] == []
    assert result["status"] == "collected"

import sys
import types


def _stub_transcript_api(monkeypatch, snippets=None, error=None):
    snippets = snippets if snippets is not None else []

    class Fakeapi:
        def fetch(self, video_id, languages=("en",)):
            if error is not None:
                raise error
            return types.SimpleNamespace(snippets=[
                types.SimpleNamespace(text=text, start=start, duration=duration)
                for text, start, duration in snippets
            ])

    module = types.ModuleType("youtube_transcript_api")
    module.YouTubeTranscriptApi = Fakeapi
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", module)


def test_transcript_prefers_korean_and_blocks_long_videos(monkeypatch):
    import asyncio

    import youtube

    _stub_transcript_api(monkeypatch, snippets=[
        ("첫 문장", 0.0, 2.0),
        ("둘째 문장", 2.0, 1799.0),
    ])
    long_video = asyncio.run(youtube.fetch_transcript_text("aB_12345678"))
    assert long_video == {"text": None, "status": "too_long"}

    _stub_transcript_api(monkeypatch, snippets=[
        ("첫 문장", 0.0, 2.0),
        ("둘째 문장", 2.0, 3.0),
    ])
    short_video = asyncio.run(youtube.fetch_transcript_text("aB_12345678"))
    assert short_video == {"text": "첫 문장 둘째 문장", "status": "collected"}


def test_transcript_failure_stays_unavailable(monkeypatch):
    import asyncio

    import youtube

    _stub_transcript_api(monkeypatch, error=ValueError("NO_TRANSCRIPT"))
    assert asyncio.run(youtube.fetch_transcript_text("aB_12345678")) == {
        "text": None, "status": "unavailable"}
    assert asyncio.run(youtube.fetch_transcript_text("not-an-id!!")) == {
        "text": None, "status": "unavailable"}
