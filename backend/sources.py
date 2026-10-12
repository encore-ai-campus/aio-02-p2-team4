"""Bounded public-source reader. TLS validation stays enabled; no credentials."""
import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from search import _source_identity, candidate_url
from youtube import MIN_YOUTUBE_VIEWS

import aiohttp
from aiohttp.abc import AbstractResolver


_JAPANESE_SCRIPT = re.compile(r'[\u3040-\u30ff]')
_KOREAN_SCRIPT = re.compile(r'[\uac00-\ud7a3]')
_MAX_SECTIONS_PER_PAGE = 80
_MAX_SECTION_TEXT = 12_000
_DOORWAY_MARKERS = (
    'the document has moved',
    'document has been moved',
    'page has moved',
    'you are being redirected',
    'if you are not redirected',
    'click here to continue',
    'redirecting you',
    'will be redirected shortly',
)
_MAX_DOORWAY_TEXT = 300
_MAX_CONCURRENT_READS = 4


def _is_japanese_page_text(text):
    japanese = len(_JAPANESE_SCRIPT.findall(text))
    korean = len(_KOREAN_SCRIPT.findall(text))
    return japanese >= 8 and japanese > korean


def public_ip(raw):
    try:
        ip = ipaddress.ip_address(raw)
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            return False
        if ip.version == 6:
            return ip in ipaddress.ip_network('2000::/3') and not any(ip in ipaddress.ip_network(n) for n in ('2001::/23','2002::/16','3fff::/20'))
        return not any(ip in ipaddress.ip_network(n) for n in ('192.0.0.0/24','192.88.99.0/24'))
    except ValueError:
        return False


class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        answers = await asyncio.get_running_loop().getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        if not answers or any(not public_ip(a[4][0]) for a in answers):
            raise ValueError('UNSAFE_SOURCE')
        # Connector connects directly to these numeric addresses, without re-resolving.
        return [dict(hostname=host, host=a[4][0], port=port, family=a[0], proto=a[2], flags=socket.AI_NUMERICHOST) for a in answers]

    async def close(self):
        pass


class _TextParser(HTMLParser):
    _HIDDEN_TAGS = {
        'head', 'script', 'style', 'noscript', 'template', 'svg', 'nav',
        'header', 'footer', 'aside', 'button', 'input', 'select', 'option',
        'textarea', 'form', 'dialog', 'iframe', 'video', 'audio',
    }
    _VOID_TAGS = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr',
    }
    _BLOCK_TAGS = {
        'address', 'article', 'aside', 'blockquote', 'details', 'dialog', 'div',
        'dl', 'dd', 'dt', 'fieldset', 'figcaption', 'figure', 'footer', 'form',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'li',
        'main', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'tr', 'ul',
    }
    _CONTENT_HINTS = {
        'article-body', 'articlebody', 'article-content', 'articlecontent',
        'story-body', 'storybody', 'story-content', 'storycontent',
        'post-body', 'postbody', 'post-content', 'postcontent',
        'entry-content', 'entrycontent', 'news-body', 'newsbody',
        'news-content', 'newscontent', 'main-content', 'maincontent',
        'content-body', 'contentbody',
    }
    _UI_HINTS = {
        'nav', 'navigation', 'navbar', 'menu', 'sidebar', 'toolbar', 'player',
        'playlist', 'related', 'recommend', 'recommended', 'cookie', 'consent',
        'advert', 'advertisement', 'ad-container', 'promo', 'promotion',
        'share-tool', 'share-tools', 'toc', 'table-of-contents', 'tableofcontents',
        'wiki-toc', 'contents-nav', 'contents-list',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.refresh_target = None
        self.fallback_parts = []
        self.content_parts = []
        self.section_records = []
        self.active_sections = []
        self.current_heading = None

    @staticmethod
    def _normalized_token(value):
        value = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', value)
        return re.sub(r'[^a-zA-Z0-9]+', '-', value).strip('-').lower()

    @classmethod
    def _is_content_root(cls, tag, attrs):
        if tag in {'main', 'article'} or attrs.get('role', '').lower() == 'main':
            return True
        if attrs.get('itemprop', '').lower() == 'articlebody':
            return True
        for name in ('id', 'class'):
            tokens = attrs.get(name, '').split()
            if any(cls._normalized_token(token) in cls._CONTENT_HINTS for token in tokens):
                return True
        return False

    @classmethod
    def _is_ui(cls, tag, attrs):
        role = attrs.get('role', '').lower()
        normalized_tag = cls._normalized_token(tag)
        if (
            tag in cls._HIDDEN_TAGS
            or 'player' in normalized_tag.split('-')
            or role in {
                'navigation', 'banner', 'complementary', 'contentinfo', 'search',
                'dialog', 'menu', 'toolbar',
            }
        ):
            return True
        if (
            'hidden' in attrs
            or 'inert' in attrs
            or attrs.get('aria-hidden', '').lower() == 'true'
        ):
            return True
        for name in ('id', 'class', 'aria-label'):
            tokens = attrs.get(name, '').split()
            for token in tokens:
                normalized = cls._normalized_token(token)
                pieces = set(normalized.split('-'))
                if normalized in cls._UI_HINTS or pieces.intersection(cls._UI_HINTS):
                    return True
        return False

    def _append_section_text(self, value, sections=None):
        targets = self.active_sections if sections is None else sections
        for section in targets:
            remaining = _MAX_SECTION_TEXT - section['_size']
            if remaining > 0:
                piece = value[:remaining]
                section['parts'].append(piece)
                section['_size'] += len(piece)
            if len(value) > max(remaining, 0):
                section['truncated'] = True

    def handle_starttag(self, tag, attrs):
        attributes = {name.lower(): value or '' for name, value in attrs}
        if tag == 'meta' and self.refresh_target is None:
            if attributes.get('http-equiv', '').strip().lower() == 'refresh':
                match = re.search(r'url\s*=\s*(.+)', attributes.get('content', ''), re.IGNORECASE)
                if match:
                    target = match.group(1).strip().strip('\'"').strip()
                    if target:
                        self.refresh_target = target
        parent = self.stack[-1] if self.stack else {'excluded': False, 'content': False}
        excluded = parent['excluded'] or self._is_ui(tag, attributes)
        content = not excluded and (parent['content'] or self._is_content_root(tag, attributes))
        heading_match = re.fullmatch(r'h([2-6])', tag)
        heading_section = None
        if not excluded:
            self.fallback_parts.append(' ')
            if content:
                self.content_parts.append(' ')
            if self.current_heading is None:
                self._append_section_text(' ')
            if tag == 'br' or tag in self._BLOCK_TAGS:
                self.fallback_parts.append('\n')
                if content:
                    self.content_parts.append('\n')
                if self.current_heading is None:
                    self._append_section_text('\n')
        if not excluded and heading_match:
            level = int(heading_match.group(1))
            while self.active_sections and self.active_sections[-1]['level'] >= level:
                self.active_sections.pop()
            if len(self.section_records) < _MAX_SECTIONS_PER_PAGE:
                heading_section = {
                    'level': level,
                    'title_parts': [],
                    'parts': [],
                    '_size': 0,
                    'truncated': False,
                }
                self.section_records.append(heading_section)
                self.active_sections.append(heading_section)
            self.current_heading = heading_section
        if tag not in self._VOID_TAGS:
            self.stack.append({
                'tag': tag,
                'excluded': excluded,
                'content': content,
                'heading_section': heading_section,
            })

    def handle_endtag(self, tag):
        match = next((i for i in range(len(self.stack) - 1, -1, -1)
                      if self.stack[i]['tag'] == tag), None)
        if match is None:
            return
        frame = self.stack[match]
        if not frame['excluded']:
            self.fallback_parts.append(' ')
            if frame['content']:
                self.content_parts.append(' ')
            if tag in self._BLOCK_TAGS:
                self.fallback_parts.append('\n')
                if frame['content']:
                    self.content_parts.append('\n')
            if frame['heading_section'] is not None:
                section = frame['heading_section']
                section['title'] = self._normalize(section.pop('title_parts'))[:300]
                if self.current_heading is section:
                    self.current_heading = None
                self._append_section_text(' ')
                if tag in self._BLOCK_TAGS:
                    self._append_section_text('\n')
            elif self.current_heading is None:
                self._append_section_text(' ')
                if tag in self._BLOCK_TAGS:
                    self._append_section_text('\n')
        del self.stack[match:]

    def handle_data(self, data):
        if self.stack and self.stack[-1]['excluded']:
            return
        self.fallback_parts.append(data)
        if self.stack and self.stack[-1]['content']:
            self.content_parts.append(data)
        if self.current_heading is not None:
            self.current_heading['title_parts'].append(data)
            self._append_section_text(data, self.active_sections[:-1])
        else:
            self._append_section_text(data)

    @staticmethod
    def _normalize(parts):
        text = ''.join(parts).replace('\r\n', '\n').replace('\r', '\n')
        lines = [' '.join(line.split()) for line in text.split('\n')]
        collapsed = []
        blank = False
        for line in lines:
            if line:
                collapsed.append(line)
                blank = False
            elif collapsed and not blank:
                collapsed.append('')
                blank = True
        while collapsed and not collapsed[-1]:
            collapsed.pop()
        return '\n'.join(collapsed)

    def text(self):
        content = self._normalize(self.content_parts)
        return content or self._normalize(self.fallback_parts)

    def sections(self):
        sections = []
        for section in self.section_records:
            title = section.get('title') or self._normalize(section.get('title_parts') or [])[:300]
            text = self._normalize(section['parts'])
            if title and text:
                sections.append({
                    'level': section['level'],
                    'title': title,
                    'text': text,
                    'truncated': section['truncated'],
                })
        return sections


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data)


def html_text(raw):
    parser = _TextParser()
    parser.feed(raw)
    return parser.text()


def html_sections(raw):
    parser = _TextParser()
    parser.feed(raw)
    return parser.sections()


def html_title(raw):
    parser = _TitleParser()
    parser.feed(raw)
    return ' '.join(' '.join(parser.parts).split())[:300]


class SourceReadResult:
    """Reader result with optional metadata and backwards-compatible unpacking."""

    __slots__ = ('text', 'url', 'title', 'sections')

    def __init__(self, text, url, title='', sections=None):
        self.text = text
        self.url = url
        self.title = title
        self.sections = sections or []

    def __iter__(self):
        # Existing test and custom readers unpack only (text, url).
        yield self.text
        yield self.url


def checked_url(raw):
    url = candidate_url(raw)
    if url is None:
        raise ValueError('UNSAFE_SOURCE')
    host = urlsplit(url).hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not public_ip(str(ip)):
        raise ValueError('UNSAFE_SOURCE')
    return url


async def _read_url(session, raw, *, include_title=False):
    current = raw
    for attempt in range(3):
        current = checked_url(current)
        async with session.get(current, allow_redirects=False) as response:
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get('Location')
                if not location:
                    raise ValueError('SOURCE_REDIRECT')
                current = urljoin(current, location)
                continue
            media = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
            encoding = response.headers.get('Content-Encoding', 'identity').lower()
            if response.status != 200 or media not in {'text/html', 'text/plain'} or encoding != 'identity':
                raise ValueError('SOURCE_UNAVAILABLE')
            body = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                if len(body) + len(chunk) > 512000:
                    remaining = 512000 - len(body)
                    if remaining > 0:
                        body.extend(chunk[:remaining])
                    break
                body.extend(chunk)
            decoded = body.decode('utf-8', errors='replace')
            title = html_title(decoded) if media == 'text/html' else ''
            if media == 'text/html':
                parser = _TextParser()
                parser.feed(decoded)
                if parser.refresh_target:
                    target = urljoin(current, parser.refresh_target)
                    same_host = (urlsplit(target).hostname or '').lower() == (urlsplit(current).hostname or '').lower()
                    if not same_host:
                        raise ValueError('SOURCE_UNAVAILABLE')
                    current = target
                    continue
                text = parser.text()
                sections = parser.sections()
            else:
                text = _TextParser._normalize([decoded])
                sections = []
            if not text:
                raise ValueError('SOURCE_EMPTY')
            if len(text) < _MAX_DOORWAY_TEXT and any(marker in text.lower() for marker in _DOORWAY_MARKERS):
                raise ValueError('SOURCE_UNAVAILABLE')
            if include_title:
                return SourceReadResult(text[:18000], current, title, sections)
            return text[:18000], current
    raise ValueError('SOURCE_REDIRECT_LIMIT')


async def fetch_public_text(raw):
    # One deadline includes DNS, TLS, redirects, and reads. No proxy or cookie state.
    async with asyncio.timeout(8):
        connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False, force_close=True)
        async with aiohttp.ClientSession(connector=connector, trust_env=False,
                cookie_jar=aiohttp.DummyCookieJar(), auto_decompress=False,
                timeout=aiohttp.ClientTimeout(total=8), headers={
                    'User-Agent':'TrueOrNot/1.0 (source verification)',
                    'Accept':'text/html,text/plain', 'Accept-Encoding':'identity'}) as session:
            return await _read_url(session, raw, include_title=True)


def _generic_title(title, raw_url):
    if not isinstance(title, str) or not title.strip():
        return True
    host = (urlsplit(raw_url).hostname or '').lower().removeprefix('www.')
    normalized = title.strip().lower().rstrip('/')
    return normalized in {host, f'www.{host}', 'source', 'untitled'}


async def _read_candidate(source, *, reader, youtube_reader):
    """Read one candidate. Returns (item, text, sections); item None drops it."""
    item = {
        **source,
        'accessStatus':'unavailable',
        'retrievedAt':datetime.now(timezone.utc).isoformat(),
        'youtubeTitle':None,
        'youtubeChannelTitle':None,
        'youtubePublishedAt':None,
        'youtubeViewCount':None,
        'youtubeComments':[],
        'youtubeDataStatus':'not_applicable',
    }
    inline_text = source.get('inlineText')
    if isinstance(inline_text, str) and inline_text.strip():
        item.update(accessStatus='verified', resolvedUrl=source['url'])
        return item, inline_text, None
    if source.get('sourceType') == '유튜브':
        item['youtubeDataStatus'] = 'not_configured' if youtube_reader is None else 'unavailable'
        if youtube_reader is not None:
            try:
                data = await youtube_reader(source['url'])
                title = data.get('title') if isinstance(data, dict) else None
                channel_title = data.get('channelTitle') if isinstance(data, dict) else None
                published_at = data.get('publishedAt') if isinstance(data, dict) else None
                view_count = data.get('viewCount') if isinstance(data, dict) else None
                comments = data.get('comments') if isinstance(data, dict) else None
                status = data.get('status') if isinstance(data, dict) else None
                transcript = data.get('transcript') if isinstance(data, dict) else None
                if isinstance(title, str) and title.strip():
                    item['youtubeTitle'] = title.strip()[:300]
                if isinstance(channel_title, str) and channel_title.strip() and len(channel_title) <= 300:
                    item['youtubeChannelTitle'] = channel_title.strip()
                if isinstance(published_at, str) and len(published_at) <= 50:
                    try:
                        parsed_published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_published_at = None
                    if parsed_published_at is not None and parsed_published_at.tzinfo is not None:
                        item['youtubePublishedAt'] = published_at
                if isinstance(view_count, str) and re.fullmatch(r'\d{1,30}', view_count):
                    item['youtubeViewCount'] = view_count
                if isinstance(comments, list):
                    item['youtubeComments'] = [
                        comment for comment in comments[:10]
                        if isinstance(comment, str) and comment.strip()
                    ]
                if status == 'collected' and isinstance(transcript, str) and transcript.strip():
                    item['youtubeTranscript'] = True
                    item['youtubeDataStatus'] = 'collected'
                    item.update(accessStatus='verified', resolvedUrl=source['url'])
                    return item, transcript, None
                if status in {'collected', 'unavailable', 'not_configured'}:
                    item['youtubeDataStatus'] = status
            except Exception:
                # One unavailable YouTube item must not fail other source reads.
                item['youtubeDataStatus'] = 'unavailable'
        if (
            item['youtubeDataStatus'] == 'unavailable'
            and isinstance(item['youtubeViewCount'], str)
            and item['youtubeViewCount'].isdigit()
            and int(item['youtubeViewCount']) <= MIN_YOUTUBE_VIEWS
        ):
            # Low-reach videos are excluded from results entirely.
            return None, None, None
        return item, None, None
    try:
        result = await reader(source['url'])
        if isinstance(result, SourceReadResult):
            text, final_url, page_title = result.text, result.url, result.title
            sections = result.sections
        else:
            text, final_url = result
            page_title = ''
            sections = []
        if not text.strip():
            raise ValueError('SOURCE_EMPTY')
        if _is_japanese_page_text(text):
            return None, None, None
        if page_title and _generic_title(item.get('title'), source['url']):
            item['title'] = page_title
        item.update(accessStatus='verified', resolvedUrl=final_url)
        return item, text, sections if isinstance(sections, list) and sections else None
    except (ValueError, OSError, aiohttp.ClientError, TimeoutError):
        return item, None, None


async def read_sources(state, *, reader=fetch_public_text, youtube_reader=None):
    candidates = state['sources'][:6]
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_READS)

    async def bounded(source):
        async with semaphore:
            return await _read_candidate(source, reader=reader, youtube_reader=youtube_reader)

    # Concurrent reads cut wall time from the sum to roughly the slowest
    # source; gather preserves candidate order for ranking.
    results = await asyncio.gather(*(bounded(source) for source in candidates))
    sources, texts, source_sections = [], {}, {}
    for source, (item, text, sections) in zip(candidates, results):
        if item is None:
            continue
        sources.append(item)
        if text is not None:
            texts[source['id']] = text
        if sections:
            source_sections[source['id']] = sections

    # Redirect aliases often point at the same article. Keep the first
    # (highest-ranked) source and its text so one page cannot count twice.
    unique_sources, unique_texts, unique_sections, seen_pages = [], {}, {}, set()
    for source in sources:
        identity = _source_identity(source.get('resolvedUrl') or source['url'])
        if identity in seen_pages:
            continue
        seen_pages.add(identity)
        unique_sources.append(source)
        source_id = source.get('id')
        if source_id in texts:
            unique_texts[source_id] = texts[source_id]
        if source_id in source_sections:
            unique_sections[source_id] = source_sections[source_id]
    return {
        'sources': unique_sources,
        'sourceTexts': unique_texts,
        'sourceSections': unique_sections,
    }

