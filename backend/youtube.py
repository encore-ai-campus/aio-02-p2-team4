"""Small, read-only adapter for documented public YouTube Data API fields."""
import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx


API_ROOT = "https://www.googleapis.com/youtube/v3"
MAX_COMMENT_COUNT = 10
MAX_RESPONSE_BYTES = 256_000
MAX_TRANSCRIPT_SECONDS = 1800
MAX_TRANSCRIPT_CHARS = 20_000
MIN_YOUTUBE_VIEWS = 10_000
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIEW_COUNT = re.compile(r"^\d{1,30}$")
_PUBLISHED_AT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)


def youtube_video_id(raw_url: str) -> str | None:
    """Extract an 11-character video ID from a recognized YouTube video URL."""
    if not isinstance(raw_url, str) or len(raw_url) > 2048:
        return None
    try:
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            return None
        if host == "youtu.be":
            parts = parsed.path.strip("/").split("/")
            candidate = parts[0] if len(parts) == 1 else ""
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                values = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
                candidate = values[0] if len(values) == 1 else ""
            else:
                parts = parsed.path.strip("/").split("/")
                candidate = parts[1] if len(parts) == 2 and parts[0] in {
                    "embed", "live", "shorts", "v",
                } else ""
        else:
            return None
    except ValueError:
        return None
    return candidate if _VIDEO_ID.fullmatch(candidate) else None


async def _request_json(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    params: dict[str, str],
) -> dict:
    async with client.stream("GET", endpoint, params=params) as response:
        response.raise_for_status()
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise ValueError("INVALID_API_RESPONSE")
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                raise ValueError("INVALID_API_RESPONSE") from None
            if length < 0:
                raise ValueError("INVALID_API_RESPONSE")
            if length > MAX_RESPONSE_BYTES:
                raise ValueError("API_RESPONSE_TOO_LARGE")
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise ValueError("API_RESPONSE_TOO_LARGE")
            body.extend(chunk)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("INVALID_API_RESPONSE") from None
    if not isinstance(payload, dict):
        raise ValueError("INVALID_API_RESPONSE")
    return payload


def _bounded_text(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized and len(normalized) <= max_length else None


def _published_at(value: object) -> str | None:
    if not isinstance(value, str) or not _PUBLISHED_AT.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if parsed.tzinfo is not None else None


def _unavailable(
    title: str | None = None,
    channel_title: str | None = None,
    published_at: str | None = None,
    view_count: str | None = None,
) -> dict:
    return {
        "title": title,
        "channelTitle": channel_title,
        "publishedAt": published_at,
        "viewCount": view_count,
        "comments": [],
        "status": "unavailable",
    }


async def fetch_transcript_text(video_id: str) -> dict:
    """Fetch caption text for grounding; 30-minute videos and over are blocked.

    Returns {"text": str | None, "status": "collected" | "too_long" | "unavailable"}.
    The unofficial caption endpoint runs in a thread and never spends API quota.
    """
    if not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id):
        return {"text": None, "status": "unavailable"}
    import asyncio

    def _load():
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        last_error: Exception | None = None
        for languages in (["ko"], ["en"]):
            try:
                fetched = api.fetch(video_id, languages=languages)
                return list(fetched.snippets)
            except Exception as exc:  # noqa: BLE001 - any fetch failure means no captions
                last_error = exc
        raise last_error if last_error is not None else ValueError("NO_TRANSCRIPT")

    try:
        snippets = await asyncio.to_thread(_load)
    except Exception:
        return {"text": None, "status": "unavailable"}
    if not snippets:
        return {"text": None, "status": "unavailable"}
    try:
        last = snippets[-1]
        duration = float(last.start) + float(last.duration)
    except (AttributeError, TypeError, ValueError):
        return {"text": None, "status": "unavailable"}
    if duration >= MAX_TRANSCRIPT_SECONDS:
        return {"text": None, "status": "too_long"}
    text = " ".join(
        snippet.text for snippet in snippets
        if isinstance(getattr(snippet, "text", None), str)
    )
    text = " ".join(text.split())
    if not text:
        return {"text": None, "status": "unavailable"}
    return {"text": text[:MAX_TRANSCRIPT_CHARS], "status": "collected"}


async def fetch_youtube_data(
    raw_url: str,
    *,
    api_key: str,
    client: httpx.AsyncClient,
) -> dict:
    """Fetch public video metadata and at most ten top-level comments."""
    if not isinstance(api_key, str) or not api_key.strip():
        return {
            "title": None,
            "channelTitle": None,
            "publishedAt": None,
            "viewCount": None,
            "comments": [],
            "status": "not_configured",
        }
    video_id = youtube_video_id(raw_url)
    if video_id is None:
        return _unavailable()

    try:
        video_payload = await _request_json(
            client,
            f"{API_ROOT}/videos",
            params={"part": "snippet,statistics", "id": video_id, "key": api_key},
        )
    except (httpx.HTTPError, TimeoutError, ValueError):
        return _unavailable()

    videos = video_payload.get("items")
    snippet = videos[0].get("snippet") if isinstance(videos, list) and videos and isinstance(videos[0], dict) else None
    title = _bounded_text(snippet.get("title"), 300) if isinstance(snippet, dict) else None
    if title is None:
        return _unavailable()
    channel_title = _bounded_text(snippet.get("channelTitle"), 300)
    published_at = _published_at(snippet.get("publishedAt"))
    statistics = videos[0].get("statistics") if isinstance(videos[0], dict) else None
    raw_view_count = statistics.get("viewCount") if isinstance(statistics, dict) else None
    view_count = raw_view_count if isinstance(raw_view_count, str) and _VIEW_COUNT.fullmatch(raw_view_count) else None
    if view_count is not None and int(view_count) <= MIN_YOUTUBE_VIEWS:
        # Low-reach videos are doorway-grade noise; skip the comment quota.
        return _unavailable(title, channel_title, published_at, view_count)

    try:
        comments_payload = await _request_json(
            client,
            f"{API_ROOT}/commentThreads",
            params={
                "part": "snippet",
                "videoId": video_id,
                "maxResults": str(MAX_COMMENT_COUNT),
                "order": "relevance",
                "textFormat": "plainText",
                "key": api_key,
            },
        )
    except (httpx.HTTPError, TimeoutError, ValueError):
        return _unavailable(title, channel_title, published_at, view_count)

    threads = comments_payload.get("items")
    if not isinstance(threads, list):
        return _unavailable(title, channel_title, published_at, view_count)
    comments = []
    for thread in threads[:MAX_COMMENT_COUNT]:
        thread_snippet = thread.get("snippet") if isinstance(thread, dict) else None
        top_level = thread_snippet.get("topLevelComment") if isinstance(thread_snippet, dict) else None
        comment_snippet = top_level.get("snippet") if isinstance(top_level, dict) else None
        comment_text = comment_snippet.get("textDisplay") if isinstance(comment_snippet, dict) else None
        if isinstance(comment_text, str) and comment_text.strip():
            comments.append(comment_text)
    transcript = await fetch_transcript_text(video_id)
    return {
        "title": title,
        "channelTitle": channel_title,
        "publishedAt": published_at,
        "viewCount": view_count,
        "comments": comments,
        "status": "collected",
        "transcript": transcript["text"],
        "transcriptStatus": transcript["status"],
    }
