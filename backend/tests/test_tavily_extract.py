"""Public-source extraction uses offline HTTP and DNS fixtures."""
import asyncio
import importlib.util
import json

import httpx
import pytest


def run_extract(monkeypatch, handler, urls, api_key='tvly-test'):
    assert importlib.util.find_spec('tavily_extract') is not None, 'Tavily extraction adapter missing'
    import tavily_extract

    async def resolve(self, host, port=0, family=0):
        if host == 'private.example':
            raise ValueError('UNSAFE_SOURCE')
        return [{'host': '8.8.8.8'}]

    monkeypatch.setattr(tavily_extract.PublicResolver, 'resolve', resolve)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            return await tavily_extract.extract_public_texts(urls, api_key=api_key, client=client)
    return asyncio.run(run())


def test_only_requested_public_pages_with_nonempty_raw_content_are_accepted(monkeypatch):
    def handler(request):
        assert str(request.url) == 'https://api.tavily.com/extract'
        assert request.headers['authorization'] == 'Bearer tvly-test'
        payload = json.loads(request.content)
        assert payload['urls'] == ['https://example.org/a', 'https://example.org/b']
        assert payload['extract_depth'] == 'advanced'
        assert payload['timeout'] <= 10
        return httpx.Response(200, json={'results': [
            {'url': 'https://example.org/a', 'raw_content': 'Retrieved article.\n\nSecond paragraph.'},
            {'url': 'https://example.org/b', 'raw_content': ' ', 'content': 'Search snippet is not evidence.'},
            {'url': 'https://other.example/not-requested', 'raw_content': 'Unrequested content.'},
        ], 'failed_results': [], 'response_time': 0.5})

    result = run_extract(monkeypatch, handler, ['https://example.org/a', 'https://example.org/b'])
    assert list(result) == ['https://example.org/a']
    assert result['https://example.org/a'].text == 'Retrieved article.\n\nSecond paragraph.'


def test_private_urls_and_videos_are_not_sent_to_tavily(monkeypatch):
    def handler(request):
        pytest.fail('No external request is allowed for unsafe URLs or videos')

    assert run_extract(monkeypatch, handler, [
        'http://127.0.0.1/', 'http://169.254.169.254/', 'https://private.example/',
        'https://www.youtube.com/watch?v=aB_12345678',
    ]) == {}


@pytest.mark.parametrize('payload', [{'results': [], 'failed_results': [{'url': 'https://example.org/a', 'error': 'failed'}]}, [], {'results': None}])
def test_empty_or_malformed_success_never_becomes_evidence(monkeypatch, payload):
    assert run_extract(monkeypatch, lambda request: httpx.Response(200, json=payload), ['https://example.org/a']) == {}


def test_missing_key_makes_no_request(monkeypatch):
    assert run_extract(monkeypatch, lambda request: pytest.fail('No configured key'), ['https://example.org/a'], api_key='') == {}


def test_extraction_deadline_cancels_pending_http(monkeypatch):
    import tavily_extract
    real_timeout = asyncio.timeout
    monkeypatch.setattr(tavily_extract.asyncio, 'timeout', lambda delay: real_timeout(0.01))
    cancelled = []

    async def handler(request):
        try:
            await asyncio.sleep(1)
            return httpx.Response(200, json={'results': []})
        finally:
            cancelled.append(True)

    assert run_extract(monkeypatch, handler, ['https://example.org/a']) == {}
    assert cancelled == [True]


def test_upstream_http_failure_does_not_leak_diagnostics(monkeypatch, caplog):
    def handler(request):
        raise httpx.ReadTimeout('PRIVATE_UPSTREAM_DETAIL')

    assert run_extract(monkeypatch, handler, ['https://example.org/a']) == {}
    assert 'PRIVATE_UPSTREAM_DETAIL' not in caplog.text
