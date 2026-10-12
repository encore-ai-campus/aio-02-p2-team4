"""Server settings and the five-stage workflow with one bounded re-search."""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, SecretStr

from answer_synthesis import insufficient_answer
from contracts import (
    FactCheckProgressCitation,
    FactCheckProgressClaim,
    FactCheckProgressSource,
    FactCheckResult,
)
from extraction import extract_claims, extract_image_claims, extract_page_claims
from jev import JevError
from schemas import ModelPreference
from tavily_search import TavilyUnavailable, search_tavily
from providers import ProviderCallError, providers_for_preference, run_with_fallback
from recovery import review_recovery
from schemas import FactCheckRequest
from search import _source_identity, apply_shared_origin_groups, build_search_query, origin_group_for_url, search_sources, source_type_for_url
from sources import SourceReadResult, fetch_public_text, read_sources
from verification import (
    _empty_judgments,
    ground_judgments,
    verify_claims,
    verify_claims_jev,
)
from youtube import fetch_youtube_data
from workflow import FactCheckState, Stage, build_workflow


_MODEL = "gpt-6-luna"
_logger = logging.getLogger(__name__)


def _http_status_from_exception(error: BaseException) -> int | None:
    """Return only an upstream HTTP status from an exception chain."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        current = current.__cause__ or current.__context__
    return None


class Settings(BaseModel):
    api_key: SecretStr
    hive_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    youtube_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")
    typesafe_api_key: SecretStr = SecretStr("")
    finnhub_api_key: SecretStr = SecretStr("")


def load_settings(env_path: Path | None = None) -> Settings:
    """Read the backend-local file without mutating process environment."""
    path = env_path if env_path is not None else Path(__file__).with_name(".env")
    values = dotenv_values(path, encoding="utf-8-sig", interpolate=False)
    key = os.environ.get("OPENAI_API_KEY", values.get("OPENAI_API_KEY") or "")
    hive_key = os.environ.get("HIVE_API_KEY", values.get("HIVE_API_KEY") or "")
    gemini_key = os.environ.get("GEMINI_API_KEY", values.get("GEMINI_API_KEY") or "")
    youtube_key = os.environ.get("YOUTUBE_API_KEY", values.get("YOUTUBE_API_KEY") or "")
    tavily_key = os.environ.get("TAVILY_API_KEY", values.get("TAVILY_API_KEY") or "")
    gateway_key = os.environ.get("TYPESAFE_API_KEY", values.get("TYPESAFE_API_KEY") or "")
    finnhub_key = os.environ.get("FINNHUB_API_KEY", values.get("FINNHUB_API_KEY") or "")
    return Settings(
        api_key=SecretStr(key.strip()),
        hive_api_key=SecretStr(hive_key.strip()),
        gemini_api_key=SecretStr(gemini_key.strip()),
        youtube_api_key=SecretStr(youtube_key.strip()),
        tavily_api_key=SecretStr(tavily_key.strip()),
        typesafe_api_key=SecretStr(gateway_key.strip()),
        finnhub_api_key=SecretStr(finnhub_key.strip()),
    )


@dataclass(frozen=True)
class RuntimeAdapters:
    """The five graph stages, injectable for offline orchestration tests."""

    extract: Stage
    search: Stage
    read: Stage
    verify: Stage
    synthesize: Stage


def make_runtime_adapters(settings: Settings) -> RuntimeAdapters:
    """Create provider-backed stages without exposing credentials to graph state."""
    async def with_client(operation):
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            return await operation(client)

    async def with_fallback(state: FactCheckState, operation, failure_code: str):
        preference = state.get("modelPreference", "auto")
        try:
            providers = providers_for_preference(settings, preference, search=failure_code == "SEARCH_FAILED")
        except ValueError as exc:
            if str(exc) == "MODEL_UNAVAILABLE":
                raise
            raise ValueError("MODEL_UNAVAILABLE") from None

        async def attempt(provider, client):
            try:
                return await operation(provider, client)
            except ProviderCallError as exc:
                _logger.warning(
                    "provider attempt failed stage=%s provider=%s error_type=%s http_status=%s",
                    failure_code,
                    provider.model,
                    type(exc).__name__,
                    _http_status_from_exception(exc),
                )
                raise
            except ValueError as exc:
                _logger.warning(
                    "provider attempt failed stage=%s provider=%s error_type=%s http_status=%s",
                    failure_code,
                    provider.model,
                    type(exc).__name__,
                    _http_status_from_exception(exc),
                )
                if str(exc) in {"INVALID_REQUEST", "NOT_CONFIGURED", "MODEL_UNAVAILABLE"}:
                    raise
                raise ProviderCallError("Provider stage failed") from None

        try:
            update, provider = await with_client(
                lambda client: run_with_fallback(
                    providers,
                    lambda provider: attempt(provider, client),
                )
            )
        except ProviderCallError:
            if preference != "auto":
                raise ValueError("MODEL_FAILED") from None
            raise ValueError(failure_code) from None
        except ValueError as exc:
            if str(exc) == "NOT_CONFIGURED":
                raise
            raise ValueError(failure_code) from None
        return {
            **update,
            "llmModel": provider.model,
            "llmReasoning": provider.reasoning,
        }

    async def extract(state: FactCheckState):
        image = state.get("image")
        if isinstance(image, dict) and image.get("data"):
            return await with_fallback(
                state,
                lambda provider, client: extract_image_claims(
                    state, image, client=client, provider=provider
                ),
                "EXTRACTION_FAILED",
            )
        link_url = state.get("linkUrl")
        has_link = isinstance(link_url, str) and bool(link_url)
        link_only = (
            has_link
            and state.get("text", "").strip() == link_url.strip()
        )

        async def extract_from_page(page_text):
            # Keep the stored text inside the 12,000-unit contract so the
            # final assembly revalidation cannot fail after paid calls.
            page_text = _truncate_units(page_text.strip(), 12_000)
            async def page_operation(provider, client):
                return await extract_page_claims(
                    page_text,
                    focus=state.get("focus", ""),
                    client=client,
                    provider=provider,
                )

            update = await with_fallback(state, page_operation, "EXTRACTION_FAILED")
            return {**update, "text": page_text}

        async def fetch_page():
            try:
                page_text, _ = await fetch_public_text(link_url)
            except Exception:
                return ""
            return page_text if isinstance(page_text, str) else ""

        async def fetch_youtube_transcript():
            from youtube import fetch_transcript_text, youtube_video_id

            video_id = youtube_video_id(link_url) if has_link else None
            if not video_id:
                return ""
            try:
                result = await fetch_transcript_text(video_id)
            except Exception:
                return ""
            text = result.get("text") if isinstance(result, dict) else None
            return text if isinstance(text, str) and text.strip() else ""

        async def fetch_link_text():
            transcript = await fetch_youtube_transcript()
            if transcript.strip():
                return transcript
            return await fetch_page()

        if link_only:
            page_text = await fetch_link_text()
            if page_text.strip():
                return await extract_from_page(page_text)
        update = await with_fallback(
            state,
            lambda provider, client: extract_claims(
                state, client=client, provider=provider
            ),
            "EXTRACTION_FAILED",
        )
        if has_link and not link_only and not update.get("claims"):
            page_text = await fetch_link_text()
            if page_text.strip():
                try:
                    return await extract_from_page(page_text)
                except ValueError:
                    pass
        return update

    async def search(state: FactCheckState):
        from stocks import detect_stock_symbols

        symbols = detect_stock_symbols(state.get("text", ""), state.get("focus", ""))
        search_state = {**state, "stockSymbols": symbols} if symbols else state
        tavily_key = settings.tavily_api_key.get_secret_value()
        if tavily_key.strip():
            try:
                async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                    update = await search_tavily(search_state, api_key=tavily_key, client=client)
            except (TavilyUnavailable, ValueError) as exc:
                _logger.warning("tavily search unavailable reason=%s", type(exc).__name__)
                update = None
            if update is not None:
                market = state.get("market") if state.get("recoveryCount") else await _fetch_market(symbols, settings)
                return {**update, "stockSymbols": symbols, "market": market}
        update = await with_fallback(
            search_state,
            lambda provider, client: search_sources(
                search_state, client=client, provider=provider
            ),
            "SEARCH_FAILED",
        )
        market = state.get("market") if state.get("recoveryCount") else await _fetch_market(symbols, settings)
        return {**update, "stockSymbols": symbols, "market": market}

    async def read(state: FactCheckState):
        sources = state.get("sources", [])
        link_url = state.get("linkUrl")
        if (
            isinstance(link_url, str)
            and link_url
            and _source_identity(link_url) not in {
                _source_identity(url) for url in state.get("excludedSourceUrls", [])
            }
            and not any(
                isinstance(source, dict)
                and (source.get("url") == link_url or source.get("resolvedUrl") == link_url)
                for source in sources
            )
        ):
            host = urlsplit(link_url).hostname or link_url
            seed = {
                "id": "s0",
                "url": link_url,
                "title": host,
                "publisher": host,
                "sourceType": source_type_for_url(link_url),
                "originGroupId": origin_group_for_url(link_url),
                "accessStatus": "pending",
                "searchProvider": None,
                "searchQuery": None,
                "candidateOrder": None,
            }
            # Keep the linked page plus at most five searched candidates.
            sources = [seed, *sources][:6]
        read_state = {**state, "sources": sources}
        link_cache: dict[str, object] = {}

        async def cached_reader(url):
            if url not in link_cache:
                link_cache[url] = await fetch_public_text(url)
            return link_cache[url]

        if (
            isinstance(link_url, str) and link_url and state.get("consent") is True
            and any(isinstance(source, dict) and source.get("id") == "s0" for source in sources)
        ):
            try:
                link_result = await cached_reader(link_url)
                link_title = link_result.title if isinstance(link_result, SourceReadResult) else ""
            except Exception:
                link_title = ""
            tavily_key = settings.tavily_api_key.get_secret_value()
            if link_title.strip() and tavily_key.strip() and not state.get("recoveryCount"):
                try:
                    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as search_client:
                        extra = await search_tavily(
                            state, api_key=tavily_key, client=search_client,
                            queries=[build_search_query(link_title)],
                        )
                    known = {link_url}
                    for source in sources:
                        if isinstance(source, dict):
                            known.add(source.get("url"))
                            known.add(source.get("resolvedUrl"))
                    additions = [
                        source for source in extra.get("sources", [])
                        if source.get("url") not in known
                    ]
                    if additions:
                        max_id = 0
                        for source in sources:
                            if isinstance(source, dict) and isinstance(source.get("id"), str):
                                match = re.fullmatch(r"s(\d+)", source["id"])
                                if match:
                                    max_id = max(max_id, int(match.group(1)))
                        for addition in additions:
                            max_id += 1
                            addition["id"] = f"s{max_id}"
                        sources = [sources[0], *additions, *sources[1:]][:6]
                        read_state = {**state, "sources": sources}
                except (TavilyUnavailable, ValueError) as exc:
                    _logger.warning("link-title search unavailable reason=%s", type(exc).__name__)
        youtube_key = settings.youtube_api_key.get_secret_value()
        if not youtube_key or not any(
            source.get("sourceType") == "유튜브" for source in sources if isinstance(source, dict)
        ):
            read_result = await read_sources(read_state, reader=cached_reader)
        else:
            async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                async def youtube_reader(url):
                    return await fetch_youtube_data(url, api_key=youtube_key, client=client)

                read_result = await read_sources(read_state, reader=cached_reader, youtube_reader=youtube_reader)
        read_result["sources"] = apply_shared_origin_groups(
            read_result.get("sources", []), read_result.get("sourceTexts", {}),
        )
        return read_result

    async def verify(state: FactCheckState):
        if state.get("jevMode"):
            try:
                async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
                    update = await verify_claims_jev(
                        state,
                        client=client,
                        api_key=settings.typesafe_api_key.get_secret_value(),
                    )
                return {**update, "llmModel": "jev-latest"}
            except JevError as exc:
                _logger.warning("jev verify failed, escalating to llm: %s", type(exc).__name__)
        return await with_fallback(
            state,
            lambda provider, client: verify_claims(
                state, client=client, provider=provider
            ),
            "VERIFICATION_FAILED",
        )

    async def synthesize(state: FactCheckState):
        # 기존 스트림 단계 이름을 유지하며 판정은 별도 생성 없이 반환합니다.
        return {
            "answer": insufficient_answer("judgment_only"),
            "answerModel": None,
            "answerReasoning": None,
        }

    return RuntimeAdapters(
        extract=extract, search=search, read=read, verify=verify, synthesize=synthesize,
    )


def _normalize_source(raw: dict, checked_at: str) -> dict:
    """Project internal source state onto the public TypeScript contract."""
    if not isinstance(raw, dict):
        raise ValueError("INVALID_STATE")

    raw_url = raw.get("resolvedUrl") or raw.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("INVALID_STATE")
    hostname = urlsplit(raw_url).hostname
    publisher = raw.get("publisher") or hostname or "알 수 없는 출처"
    title = raw.get("title") or raw_url
    access_status = raw.get("accessStatus")
    if access_status not in {"verified", "unavailable"}:
        raise ValueError("INVALID_STATE")

    return {
        "id": raw.get("id"),
        "url": raw_url,
        "title": title,
        "publisher": publisher,
        "publishedAt": raw.get("publishedAt"),
        "retrievedAt": raw.get("retrievedAt") or checked_at,
        "accessStatus": access_status,
        "sourceType": raw.get("sourceType") or "유형 미확인",
        "originGroupId": raw.get("originGroupId"),
        "searchProvider": raw.get("searchProvider"),
        "searchQuery": raw.get("searchQuery"),
        "candidateOrder": raw.get("candidateOrder"),
        "youtubeTitle": raw.get("youtubeTitle"),
        "youtubeChannelTitle": raw.get("youtubeChannelTitle"),
        "youtubePublishedAt": raw.get("youtubePublishedAt"),
        "youtubeViewCount": raw.get("youtubeViewCount"),
        "youtubeComments": raw.get("youtubeComments", []),
        "youtubeDataStatus": raw.get("youtubeDataStatus", "not_applicable"),
    }


async def _fetch_market(symbols: list[str], settings: Settings) -> dict | None:
    """Fetch quote plus candles for the first detected symbol, if configured.

    Best-effort: any Finnhub failure omits market context without failing
    verification. Quote and candle access depend on the configured account.
    """
    from datetime import datetime, timezone

    from finnhub import fetch_candles as finnhub_candles
    from finnhub import fetch_stock_quote as finnhub_quote
    from stocks import build_market_context, display_name_for

    if not symbols:
        return None
    symbol = symbols[0]
    finnhub_key = settings.finnhub_api_key.get_secret_value()
    if not finnhub_key.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            quote = await finnhub_quote(symbol, api_key=finnhub_key, client=client)
            if quote.get("error"):
                return None
            candles = await finnhub_candles(symbol, api_key=finnhub_key, client=client)
        if candles.get("error"):
            return None
        context = build_market_context(
            symbol, display_name_for(symbol), quote, candles,
            data_as_of=datetime.now(timezone.utc).isoformat(),
        )
        if context is not None:
            context["source"] = "finnhub"
        return context
    except Exception:
        return None


def _result_warnings(
    sources: list[dict],
    search_notice: str | None = None,
    youtube_transcript_verified: bool = False,
) -> list[str]:
    warnings = [
        "최대 3개 주장·6개 출처를 대상으로 한 제한된 검증입니다.",
    ]
    groups: dict[str, int] = {}
    for source in sources:
        group = source.get("originGroupId") if isinstance(source, dict) else None
        if isinstance(group, str) and group.startswith("shared-"):
            groups[group] = groups.get(group, 0) + 1
    if not any(count >= 2 for count in groups.values()):
        warnings.append(
            "출처 간 독립성과 원자료 계보는 확인되지 않았습니다.",
        )
    if any(source.get("accessStatus") == "unavailable" for source in sources):
        warnings.append(
            "일부 출처 원문에 접근하지 못했습니다. 검색 요약은 직접 인용으로 사용하지 않았습니다."
        )
    youtube_sources = [
        source for source in sources if source.get("sourceType") == "유튜브"
    ]
    if youtube_sources and not youtube_transcript_verified:
        warnings.append(
            "유튜브 공개 댓글은 영상별 의견 맥락으로만 표시하며 판정과 인용 근거에는 사용하지 않았습니다."
        )
    if search_notice == "LLM_SEARCH_UNAVAILABLE":
        warnings.append(
            "웹검색을 사용할 수 없어 검색 원문을 확보하지 못했습니다."
        )
    return warnings


def build_fact_check_result(
    state: FactCheckState,
    update: dict,
    *,
    checked_at: str | None = None,
) -> FactCheckResult:
    """Validate and assemble the only result shape exposed by the API."""
    if not isinstance(update, dict):
        raise ValueError("INVALID_STATE")
    merged_state = {**state, **update}
    request = FactCheckRequest.model_validate({
        "text": state.get("text"),
        "focus": state.get("focus"),
        "consent": state.get("consent"),
    })
    claims = state.get("claims")
    evidence = state.get("evidence")
    raw_sources = state.get("sources", [])
    if not isinstance(claims, list) or not isinstance(evidence, list) or not isinstance(raw_sources, list):
        raise ValueError("INVALID_STATE")

    timestamp = checked_at or datetime.now(timezone.utc).isoformat()
    sources = [_normalize_source(source, timestamp) for source in raw_sources]
    answer = merged_state.get("answer") if "answer" in update else None
    if not isinstance(answer, dict):
        answer = insufficient_answer()
    answer = {
        **answer,
        "model": update.get("answerModel"),
        "reasoning": update.get("answerReasoning"),
    }
    warnings = _result_warnings(
        sources,
        merged_state.get("searchNotice"),
        youtube_transcript_verified=any(
            isinstance(raw, dict) and raw.get("youtubeTranscript") for raw in raw_sources
        ),
    )
    if merged_state.get("recoveryCount"):
        warnings.append("원문 수집·인용 검증 문제로 검색어를 바꿔 1회 재탐색했습니다.")
    return FactCheckResult.model_validate({
        "text": request.text,
        "focus": request.focus,
        "demo": False,
        "model": state.get("llmModel") or _MODEL,
        "reasoning": state.get("llmReasoning") or "max",
        "checkedAt": timestamp,
        "claims": claims,
        "sources": sources,
        "evidence": evidence,
        "warnings": warnings,
        "market": merged_state.get("market"),
        "answer": answer,
    })


def _truncate_units(text: str, max_units: int) -> str:
    """Truncate to a UTF-16 unit budget without splitting astral characters."""
    units = 0
    out: list[str] = []
    for char in text:
        units += 2 if ord(char) > 0xFFFF else 1
        if units > max_units:
            break
        out.append(char)
    return "".join(out)


async def run_jev_fast_check(
    *,
    text: str,
    focus: str = "",
    link_url: str | None = None,
    client: httpx.AsyncClient,
    api_key: str | None,
    settings: Settings,
    model_preference: ModelPreference = "auto",
    consent: bool = True,
) -> FactCheckResult:
    """Search and read evidence, then return Jev's score-only claim result."""
    full_text = _truncate_units(text, 12_000)
    if not full_text.strip():
        raise JevError("Nothing to judge", code="INVALID_REQUEST")

    claim = {
        "id": "c1",
        "quote": full_text,
        "start": 0,
        "end": len(full_text.encode("utf-16-le")) // 2,
        "kind": "fact",
    }
    query_text = focus.strip() or full_text
    state = {
        "text": full_text,
        "focus": focus,
        "consent": consent,
        "claims": [claim],
        "searchQueries": {"c1": build_search_query(query_text)},
    }
    sources: list[dict] = []
    if link_url:
        host = urlsplit(link_url).hostname or link_url
        sources.append({
            "id": "s0",
            "url": link_url,
            "title": host,
            "publisher": host,
            "sourceType": source_type_for_url(link_url),
            "originGroupId": origin_group_for_url(link_url),
            "accessStatus": "pending",
            "searchProvider": None,
            "searchQuery": None,
            "candidateOrder": None,
        })

    search_notice = None
    read_result = None
    if consent and link_url and sources:
        link_read = await read_sources({"sources": sources}, reader=fetch_public_text)
        if link_read.get("sourceTexts"):
            read_result = link_read
    if read_result is None:
        if not consent:
            search_notice = "LLM_SEARCH_UNAVAILABLE"
        else:
            async def search_once(provider):
                try:
                    return await search_sources(state, client=client, provider=provider)
                except ValueError as exc:
                    raise ProviderCallError(str(exc)) from None

            search_result = None
            tavily_key = settings.tavily_api_key.get_secret_value()
            if tavily_key.strip():
                try:
                    search_result = await search_tavily(state, api_key=tavily_key, client=client)
                except (TavilyUnavailable, ValueError) as exc:
                    _logger.warning("Jev Tavily search unavailable reason=%s", type(exc).__name__)
            if search_result is None:
                try:
                    providers = providers_for_preference(settings, model_preference, search=True)
                    search_result, _ = await run_with_fallback(providers, search_once)
                except (ProviderCallError, ValueError) as exc:
                    _logger.warning("Jev LLM search unavailable reason=%s", type(exc).__name__)
                    search_notice = "LLM_SEARCH_UNAVAILABLE"
            if search_result is not None:
                sources.extend(search_result.get("sources", []))

    if read_result is None:
        state["sources"] = sources[:6]
        youtube_key = settings.youtube_api_key.get_secret_value()
        if youtube_key.strip() and any(
            isinstance(source, dict) and source.get("sourceType") == "유튜브"
            for source in sources
        ):
            async def youtube_reader(url):
                return await fetch_youtube_data(url, api_key=youtube_key, client=client)

            read_result = await read_sources(state, reader=fetch_public_text, youtube_reader=youtube_reader)
        else:
            read_result = await read_sources(state, reader=fetch_public_text)
    state.update(read_result)
    try:
        judgment_result = await verify_claims_jev(
            state,
            client=client,
            api_key=api_key,
        )
    except JevError as exc:
        if exc.code != "LOW_CONFIDENCE":
            raise
        # Low confidence is deterministic: retrying the same evidence cannot
        # help, so conclude with insufficient evidence instead of failing.
        judgment_result = ground_judgments(
            [claim],
            _empty_judgments([claim]),
            state.get("sources", []),
            state.get("sourceTexts", {}),
            source_sections=state.get("sourceSections", {}),
        )
    if not judgment_result.get("claims"):
        raise JevError("Jev returned no judgment", code="NO_JUDGMENT")

    timestamp = datetime.now(timezone.utc).isoformat()
    normalized_sources = [
        _normalize_source(source, timestamp) for source in read_result.get("sources", [])
    ]
    warnings = _result_warnings(
        normalized_sources,
        search_notice,
        youtube_transcript_verified=any(
            isinstance(raw, dict) and raw.get("youtubeTranscript")
            for raw in read_result.get("sources", [])
        ),
    )
    return FactCheckResult.model_validate({
        "text": full_text,
        "focus": focus,
        "demo": False,
        "model": "jev-latest",
        "reasoning": "max",
        "checkedAt": timestamp,
        "claims": judgment_result["claims"],
        "sources": normalized_sources,
        "evidence": judgment_result.get("evidence", []),
        "warnings": warnings,
        "answer": insufficient_answer(),
    })


def build_progress_sources(state: FactCheckState) -> list[dict[str, object]]:
    """Expose only source identity and access state before final answer assembly."""
    raw_sources = state.get("sources", [])
    if not isinstance(raw_sources, list):
        return []

    projected: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        source_id = raw.get("id")
        raw_url = raw.get("resolvedUrl") or raw.get("url")
        if not isinstance(source_id, str) or not source_id or source_id in seen_ids:
            continue
        if not isinstance(raw_url, str) or len(raw_url) > 2048:
            continue
        try:
            parsed_url = urlsplit(raw_url)
        except ValueError:
            continue
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            continue

        status = raw.get("accessStatus")
        if status not in {"verified", "unavailable"}:
            status = "candidate"
        source = FactCheckProgressSource.model_validate({
            "id": source_id,
            "url": raw_url,
            "title": str(raw.get("title") or parsed_url.hostname)[:300],
            "publisher": str(raw.get("publisher") or parsed_url.hostname)[:300],
            "accessStatus": status,
            "sourceType": str(raw.get("sourceType") or "유형 미확인")[:100],
        })
        projected.append(source.model_dump(mode="json"))
        seen_ids.add(source_id)
        if len(projected) == 6:
            break
    return projected


def build_progress_preview(state: FactCheckState) -> dict[str, object]:
    """Build an early, strictly projected claim summary from validated evidence."""
    result = build_fact_check_result(state, {})
    evidence_by_id = {evidence.id: evidence for evidence in result.evidence}
    sources_by_id = {source.id: source for source in result.sources}
    claims: list[dict[str, object]] = []

    for claim in result.claims:
        citations: list[dict[str, str]] = []
        seen_sources: set[str] = set()
        for evidence_id in claim.evidenceIds:
            evidence = evidence_by_id.get(evidence_id)
            source = sources_by_id.get(evidence.sourceId) if evidence else None
            if (
                evidence is None
                or source is None
                or source.accessStatus != "verified"
                or source.sourceType == "유튜브"
                or evidence.sourceId in seen_sources
            ):
                continue
            seen_sources.add(evidence.sourceId)
            citation = FactCheckProgressCitation.model_validate({
                "sourceId": evidence.sourceId,
                "quote": evidence.quote,
            })
            citations.append(citation.model_dump(mode="json"))
            if len(citations) == 3:
                break

        preview_claim = FactCheckProgressClaim.model_validate({
            "id": claim.id,
            "quote": claim.quote,
            "summary": claim.summary,
            "verdict": claim.verdict,
            "citations": citations,
        })
        claims.append(preview_claim.model_dump(mode="json"))

    return {"claims": claims}


def build_runtime_workflow(
    settings: Settings,
    *,
    adapters: RuntimeAdapters | None = None,
):
    """판정 후 별도 모델 생성 없이 결과를 정리하며 필요하면 한 번 재탐색합니다."""
    runtime_adapters = adapters or make_runtime_adapters(settings)

    async def extracting(state: FactCheckState):
        update = await runtime_adapters.extract(state)
        return {**update, "claimSnapshot": [dict(c) for c in update.get("claims", [])],
                "recoveryCount": 0, "recoveryRequested": False, "recoveryTrace": []}

    async def searching(state: FactCheckState):
        update = await runtime_adapters.search(state)
        excluded = {_source_identity(url) for url in state.get("excludedSourceUrls", [])}
        sources = [s for s in update.get("sources", [])
                   if _source_identity(s["url"]) not in excluded]
        return {**update, "sources": sources, "sourceTexts": {}, "sourceSections": {},
                "evidence": [], "diagnostics": [], "recoveryRequested": False}

    async def verifying(state: FactCheckState):
        update = await runtime_adapters.verify(state)
        update = {**update, "diagnostics": update.get("diagnostics", [])}
        return {**update, **review_recovery({**state, **update})}

    async def reading(state: FactCheckState):
        update = await runtime_adapters.read(state)
        excluded = {_source_identity(url) for url in state.get("excludedSourceUrls", [])}
        sources = [s for s in update.get("sources", []) if not any(
            _source_identity(url) in excluded for url in (s.get("url"), s.get("resolvedUrl"))
            if isinstance(url, str) and url
        )]
        ids = {s["id"] for s in sources}
        return {**update, "sources": sources,
                "sourceTexts": {sid: text for sid, text in update.get("sourceTexts", {}).items() if sid in ids},
                "sourceSections": {sid: sections for sid, sections in update.get("sourceSections", {}).items() if sid in ids}}

    async def synthesizing(state: FactCheckState):
        update = await runtime_adapters.synthesize(state)
        if not isinstance(update, dict):
            update = {}
        answer = update.get("answer")
        if not isinstance(answer, dict):
            update = {
                "answer": insufficient_answer(),
                "answerModel": None,
                "answerReasoning": None,
            }
        result = build_fact_check_result(state, update)
        return {**update, "result": result.model_dump(mode="json")}

    return build_workflow(
        extract=extracting,
        search=searching,
        read=reading,
        verify=verifying,
        synthesize=synthesizing,
    )


def build_extraction_graph(extract: Stage):
    """End after extraction; do not simulate search, sources, or judgments."""
    builder = StateGraph(FactCheckState)
    builder.add_node("extracting", extract)
    builder.add_edge(START, "extracting")
    builder.add_edge("extracting", END)
    return builder.compile()
