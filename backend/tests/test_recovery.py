"""Recovery trigger tests; a single failed source is a warning, not a retry."""
from recovery import review_recovery


def base_state():
    return {
        "claims": [{"id": "c1", "kind": "fact", "verdictCode": "insufficient_evidence"}],
        "searchQueries": {"c1": "query"},
        "sources": [],
        "diagnostics": [],
    }


def source(sid, access):
    return {"id": sid, "url": f"https://example.org/{sid}", "accessStatus": access}


def test_single_unavailable_source_does_not_trigger_recovery():
    state = base_state()
    state["sources"] = [source("s1", "verified"), source("s2", "verified"), source("s3", "unavailable")]

    assert review_recovery(state) == {"recoveryRequested": False}


def test_lone_failed_source_does_not_trigger_recovery():
    state = base_state()
    state["sources"] = [source("s1", "unavailable")]

    assert review_recovery(state) == {"recoveryRequested": False}


def test_half_failed_sources_do_not_trigger_recovery():
    state = base_state()
    state["sources"] = [
        source("s1", "verified"), source("s2", "verified"), source("s3", "verified"),
        source("s4", "unavailable"), source("s5", "unavailable"), source("s6", "unavailable"),
    ]

    assert review_recovery(state) == {"recoveryRequested": False}


def test_strict_majority_failed_sources_trigger_recovery():
    state = base_state()
    state["sources"] = [
        source("s1", "verified"), source("s2", "verified"),
        source("s4", "unavailable"), source("s5", "unavailable"),
        source("s6", "unavailable"), source("s7", "unavailable"),
    ]

    result = review_recovery(state)
    assert result["recoveryRequested"] is True
    assert result["recoveryCount"] == 1


def test_majority_unavailable_sources_trigger_recovery():
    state = base_state()
    state["sources"] = [source("s1", "verified"), source("s2", "unavailable"), source("s3", "unavailable")]

    result = review_recovery(state)
    assert result["recoveryRequested"] is True
    assert result["recoveryCount"] == 1


def test_rejected_citation_triggers_recovery_without_failed_sources():
    state = base_state()
    state["sources"] = [source("s1", "verified")]
    state["diagnostics"] = [{"code": "CITATION_REJECTED", "claimId": "c1", "sourceIds": ["s1"]}]

    result = review_recovery(state)
    assert result["recoveryRequested"] is True
    assert result["recoveryCount"] == 1
