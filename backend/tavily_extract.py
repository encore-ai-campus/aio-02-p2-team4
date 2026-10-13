"""One bounded batch retry for unreadable public web pages."""
import asyncio
import json
import logging
from urllib.parse import urlsplit

import httpx

from search import source_type_for_url
from sources import PublicResolver, SourceReadResult, _TextParser, checked_url


logger = logging.getLogger(__name__)


async def extract_public_texts(urls, *, api_key: str, client: httpx.AsyncClient):
    if not api_key.strip():
        return {}
    try:
        async with asyncio.timeout(10):
            requested = []
            for raw in urls[:6]:
                try:
                    url = checked_url(raw)
                    if source_type_for_url(url) == '유튜브' or url in requested:
                        continue
                    parsed = urlsplit(url)
                    await PublicResolver().resolve(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
                except (ValueError, OSError):
                    continue
                requested.append(url)
            if not requested:
                return {}
            async with client.stream(
                'POST', 'https://api.tavily.com/extract',
                headers={'Authorization': f'Bearer {api_key}'},
                json={'urls': requested, 'extract_depth': 'advanced', 'format': 'text', 'timeout': 8},
                timeout=10,
            ) as response:
                if response.status_code != 200:
                    return {}
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 1_048_576:
                        return {}
                    body.extend(chunk)
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
                return {}
            results = {}
            for item in payload['results']:
                if not isinstance(item, dict) or item.get('url') not in requested:
                    continue
                raw_content = item.get('raw_content')
                if not isinstance(raw_content, str):
                    continue
                text = _TextParser._normalize([raw_content[:18_000]])
                if text:
                    results[item['url']] = SourceReadResult(text, item['url'])
            return results
    except (httpx.HTTPError, TimeoutError, ValueError, OSError) as exc:
        logger.warning('Tavily extraction unavailable reason=%s', type(exc).__name__)
        return {}
