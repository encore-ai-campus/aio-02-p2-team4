"""Choose at most one re-search for concrete collection or citation failures."""
from search import build_search_query


def review_recovery(state: dict) -> dict:
    claims = state.get("claims", [])
    if state.get("recoveryCount", 0) >= 1:
        trace = [dict(item) for item in state.get("recoveryTrace", [])]
        if trace:
            targets = [c for c in claims if c.get("id") in trace[0]["claimIds"]]
            trace[0]["outcome"] = "grounded" if targets and all(
                c.get("evidenceIds") and c.get("verdictCode") != "insufficient_evidence"
                for c in targets
            ) else "unresolved"
        return {"recoveryRequested": False, "recoveryTrace": trace}

    unresolved = [c for c in claims if c.get("kind") in {"fact", "unclear"}
                  and c.get("verdictCode") == "insufficient_evidence"]
    if not unresolved:
        return {"recoveryRequested": False}
    sources = [s for s in state.get("sources", []) if isinstance(s, dict)]
    failed_sources = [s for s in sources if s.get("accessStatus") == "unavailable"]
    diagnostics = [d for d in state.get("diagnostics", [])
                   if d.get("code") == "CITATION_REJECTED"]
    invalid_claims = {d["claimId"] for d in diagnostics}
    targets = [c for c in unresolved if c["id"] in invalid_claims]
    if not targets and len(sources) > 1 and len(failed_sources) * 2 > len(sources):
        # Strict majority unreadable: collection itself likely failed, retry once.
        # A single failed source (even 1 of 1) is only a warning, not a retry.
        targets = unresolved
    if not targets:
        return {"recoveryRequested": False}

    # ponytail: one fixed primary-source query variant; add a planner only if
    # measured recovery quality justifies another model call.
    queries = dict(state.get("searchQueries", {}))
    for claim in targets:
        original = queries.get(claim["id"]) or claim["quote"]
        queries[claim["id"]] = build_search_query(f"공식 원문 {original}")
    target_ids = {c["id"] for c in targets}
    invalid_source_ids = {sid for d in diagnostics if d["claimId"] in target_ids
                          for sid in d.get("sourceIds", [])}
    excluded_sources = [s for s in state.get("sources", [])
                        if s.get("accessStatus") == "unavailable" or s.get("id") in invalid_source_ids]
    excluded = sorted({url for s in excluded_sources for url in (s.get("url"), s.get("resolvedUrl"))
                       if isinstance(url, str) and url})
    reasons = (["SOURCE_UNAVAILABLE"] if failed_sources else [])
    if invalid_claims:
        reasons.append("CITATION_REJECTED")
    return {
        "claims": state.get("claimSnapshot", claims),
        "searchQueries": queries,
        "excludedSourceUrls": excluded,
        "recoveryRequested": True,
        "recoveryCount": 1,
        "recoveryTrace": [{"action": "research", "reasonCodes": reasons,
                           "claimIds": [c["id"] for c in targets], "queries": queries,
                           "excludedSourceUrls": excluded, "outcome": "pending"}],
    }
