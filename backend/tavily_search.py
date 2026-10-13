"""Tavily web search discovery. Optional; LLM search remains the fallback."""
import asyncio
import logging

import httpx

from search import _project_candidates_with_youtube, build_search_query


logger = logging.getLogger(__name__)


class TavilyUnavailable(Exception):
    """Tavily could not serve this request; the caller falls back."""


async def search_tavily(
    state: dict, *, api_key: str, client: httpx.AsyncClient,
    queries: list[str] | None = None,
) -> dict:
    """Search each checkable claim with Tavily basic depth (1 credit per query).

    Normal verification also makes one restricted YouTube search per distinct claim query.
    Pass explicit ``queries`` for supplemental searches that should skip YouTube lookup.
    """
    include_youtube_search = queries is None
    if state.get("consent") is not True:
        raise ValueError("INVALID_REQUEST")
    if not api_key.strip():
        raise TavilyUnavailable("not_configured")

    if queries is not None:
        queries = [" ".join(query.split())[:300] for query in queries if isinstance(query, str) and query.strip()]
        if not queries:
            return {"sources": []}
        claims = []
    else:
        claims = [
            claim for claim in state.get("claims", [])
            if claim.get("kind") in {"fact", "unclear", "prediction"}
        ]
        if not claims:
            return {"sources": []}
        if len(claims) > 3:
            raise ValueError("INVALID_REQUEST")

    if queries is None:
        queries = []
        search_queries = state.get("searchQueries") or {}
        for claim in claims:
            extracted = search_queries.get(claim.get("id"))
            query = (
                " ".join(extracted.split())[:300]
                if isinstance(extracted, str) and extracted.strip()
                else build_search_query(claim["quote"])
            )
            if query not in queries:
                queries.append(query)
    else:
        queries = [" ".join(query.split())[:300] for query in queries if isinstance(query, str) and query.strip()]
        if not queries:
            return {"sources": []}

    async def fetch_results(query: str, youtube_only: bool = False) -> list[dict]:
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": False,
            "include_raw_content": False,
        }
        if youtube_only:
            payload["include_domains"] = ["youtube.com", "youtu.be"]
            payload["include_domains_mode"] = "restrict"
        try:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=20.0,
            )
        except (httpx.HTTPError, TimeoutError) as exc:
            raise TavilyUnavailable("upstream_unavailable") from exc
        if response.status_code != 200:
            raise TavilyUnavailable("upstream_unavailable")
        try:
            data = response.json()
        except ValueError as exc:
            raise TavilyUnavailable("invalid_response") from exc
        if not isinstance(data, dict):
            raise TavilyUnavailable("invalid_response")
        if isinstance(data.get("error"), str) and data["error"].strip():
            raise TavilyUnavailable("upstream_unavailable")
        results = data.get("results")
        if not isinstance(results, list):
            raise TavilyUnavailable("missing_results")
        return [
            {
                "url": result.get("url"),
                "title": result.get("title"),
                "snippet": result.get("content"),
                "searchProvider": "tavily_search",
                "searchQuery": query,
            }
            for result in results
            if isinstance(result, dict)
        ]

    candidate_groups = await asyncio.gather(
        *(fetch_results(query) for query in queries), return_exceptions=True,
    )
    for group in candidate_groups:
        if isinstance(group, BaseException):
            raise group
    youtube_groups = []
    if include_youtube_search:
        async def fetch_youtube(query: str) -> list[dict]:
            try:
                return await fetch_results(query, youtube_only=True)
            except TavilyUnavailable as exc:
                logger.warning("Separate YouTube search failed (%s)", type(exc).__name__)
                return []

        youtube_groups = await asyncio.gather(*(fetch_youtube(query) for query in queries))

    candidates = [candidate for group in [*candidate_groups, *youtube_groups] for candidate in group if candidate]
    selected = _project_candidates_with_youtube(
        candidates, prefer_finance=bool(state.get("stockSymbols")),
        exclude_urls=state.get("excludedSourceUrls", []),
    )
    return {"sources": [{"id": f"s{i+1}", **source} for i, source in enumerate(selected)]}
