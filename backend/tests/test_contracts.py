"""Final Python contract tests; no provider calls."""
import pytest
from pydantic import ValidationError

from contracts import FactCheckResponse, FactCheckResult


def result_payload():
    return {
        "text": "Claim",
        "focus": "",
        "demo": False,
        "model": "gpt-6-luna",
        "reasoning": "max",
        "checkedAt": "2026-09-20T00:00:00+00:00",
        "claims": [{
            "id": "c1",
            "quote": "Claim",
            "start": 0,
            "end": 5,
            "kind": "fact",
            "verdictCode": "mostly_supported",
            "verdict": "대체로 확인됨",
            "tone": "positive",
            "summary": "원문이 주장을 뒷받침합니다.",
            "confirmed": ["Claim"],
            "unresolved": [],
            "warnings": [],
            "evidenceIds": ["e1"],
        }],
        "sources": [{
            "id": "s1",
            "url": "https://example.org/source",
            "title": "Example source",
            "publisher": "example.org",
            "publishedAt": None,
            "retrievedAt": "2026-09-20T00:00:00+00:00",
            "accessStatus": "verified",
            "sourceType": "유형 미확인",
            "originGroupId": None,
        }],
        "evidence": [{
            "id": "e1",
            "claimId": "c1",
            "sourceId": "s1",
            "quote": "Claim is supported.",
            "quoteVerified": True,
            "relation": "supports",
        }],
        "warnings": [],
    }


def grounded_answer():
    citation = {"sourceId": "s1", "quote": "Claim is supported."}
    return {
        "status": "grounded",
        "overview": {"text": "AGI 전망은 아직 불확실합니다.", "citations": [citation]},
        "sections": [],
        "conclusion": {"text": "확정할 수 없습니다.", "citations": [citation]},
        "model": "gemini-3.8-flash",
        "reasoning": "high",
    }


def test_final_contract_accepts_frontend_shape_and_wrapper():
    parsed = FactCheckResponse.model_validate({"result": result_payload()})
    assert parsed.result.demo is False
    assert parsed.result.claims[0].evidenceIds == ["e1"]
    assert parsed.model_dump(mode="json")["result"]["sources"][0]["publishedAt"] is None


def test_market_context_is_optional_but_validated():
    from pydantic import ValidationError

    from contracts import FactCheckResult

    base = result_payload()
    assert FactCheckResult.model_validate(base).market is None

    market = {
        "source": "finnhub",
        "symbol": "TSLA",
        "displayName": None,
        "current": 250.0,
        "previousClose": 200.0,
        "changePercent": 25.0,
        "dataAsOf": "2026-09-30T00:00:00+00:00",
        "candles": [
            {"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.2, "volume": 10.0},
        ],
    }
    assert FactCheckResult.model_validate({**base, "market": market}).market.symbol == "TSLA"

    oversized = {**market, "candles": [market["candles"][0]] * 91}
    try:
        FactCheckResult.model_validate({**base, "market": oversized})
    except ValidationError:
        pass
    else:
        raise AssertionError("oversized candles must be rejected")


def test_market_context_rejects_retired_toss_source():
    from contracts import MarketContext

    assert MarketContext.model_validate({"symbol": "TSLA", "candles": []}).source == "finnhub"
    with pytest.raises(ValidationError):
        MarketContext.model_validate({"source": "tossinvest", "symbol": "TSLA", "candles": []})


def test_evidence_may_expose_only_a_bounded_matching_article_section():
    payload = result_payload()
    payload["evidence"][0].update({
        "sectionTitle": "4. 텔러린 앱",
        "sectionText": "텔러린 앱은 여러 기능을 통합해 제공하는 서비스입니다.",
        "sectionTruncated": False,
    })

    evidence = FactCheckResult.model_validate(payload).evidence[0]
    assert evidence.sectionTitle == "4. 텔러린 앱"
    assert evidence.sectionText == "텔러린 앱은 여러 기능을 통합해 제공하는 서비스입니다."
    assert evidence.sectionTruncated is False

    payload["evidence"][0]["sectionText"] = "가" * 8_001
    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)


def test_source_discovery_order_is_explicitly_not_a_google_rank():
    payload = result_payload()
    payload["sources"][0].update({
        "searchProvider": "openai_web_search",
        "searchQuery": "AGI 2030년",
        "candidateOrder": 4,
    })
    source = FactCheckResult.model_validate(payload).sources[0]
    assert source.searchProvider == "openai_web_search"
    assert source.candidateOrder == 4

    payload["sources"][0]["candidateOrder"] = 0
    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)


def test_source_contract_accepts_llm_search_provenance():
    payload = result_payload()
    payload["sources"][0].update({
        "searchProvider": "gemini_google_search",
        "searchQuery": "AGI 2030년",
        "candidateOrder": 1,
    })
    source = FactCheckResult.model_validate(payload).sources[0]
    assert source.searchProvider == "gemini_google_search"
    assert source.candidateOrder == 1


def test_source_contract_accepts_bounded_youtube_video_metadata():
    payload = result_payload()
    payload["sources"][0].update({
        "youtubeChannelTitle": "AI 연구 채널",
        "youtubePublishedAt": "2026-09-20T12:30:00Z",
        "youtubeViewCount": "1234567",
    })

    source = FactCheckResult.model_validate(payload).sources[0]
    assert source.youtubeChannelTitle == "AI 연구 채널"
    assert source.youtubePublishedAt == "2026-09-20T12:30:00Z"
    assert source.youtubeViewCount == "1234567"

    payload["sources"][0]["youtubeViewCount"] = "12 views"
    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)

    payload["sources"][0]["youtubeViewCount"] = "123"
    payload["sources"][0]["youtubePublishedAt"] = "not-a-date"
    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)


def test_result_serializes_safe_insufficient_answer_by_default():
    serialized = FactCheckResult.model_validate(result_payload()).model_dump(mode="json")

    assert serialized["answer"] == {
        "status": "insufficient_evidence",
        "overview": None,
        "sections": [],
        "conclusion": None,
        "model": None,
        "reasoning": None,
    }


def test_result_accepts_grounded_answer_with_verified_source_reference():
    payload = result_payload()
    payload["answer"] = grounded_answer()

    parsed = FactCheckResult.model_validate(payload)

    assert parsed.answer.status == "grounded"
    assert parsed.answer.overview.citations[0].sourceId == "s1"


def test_result_accepts_insufficient_answer_without_provider_metadata():
    payload = result_payload()
    payload["answer"] = {
        "status": "insufficient_evidence",
        "overview": None,
        "sections": [],
        "conclusion": None,
        "model": None,
        "reasoning": None,
    }

    answer = FactCheckResult.model_validate(payload).answer

    assert answer.status == "insufficient_evidence"
    assert answer.model is None
    assert answer.reasoning is None


@pytest.mark.parametrize("mutation", [
    "missing_citation",
    "unknown_source",
    "unavailable_source",
    "youtube_source",
    "too_many_sections",
    "too_many_items",
    "too_many_citations",
    "text_too_long",
    "quote_too_long",
    "title_too_long",
    "insufficient_with_sections",
])
def test_result_rejects_invalid_grounded_answer(mutation):
    payload = result_payload()
    answer = grounded_answer()
    citation = answer["overview"]["citations"][0]

    if mutation == "missing_citation":
        answer["overview"]["citations"] = []
    elif mutation == "unknown_source":
        citation["sourceId"] = "unknown"
    elif mutation == "unavailable_source":
        payload["sources"].append({
            **payload["sources"][0], "id": "s2", "accessStatus": "unavailable",
        })
        citation["sourceId"] = "s2"
    elif mutation == "youtube_source":
        payload["sources"][0]["sourceType"] = "유튜브"
    elif mutation == "too_many_sections":
        section = {
            "kind": "supporting", "title": "근거",
            "items": [{"text": "뒷받침합니다.", "citations": [citation]}],
        }
        answer["sections"] = [section] * 5
    elif mutation == "too_many_items":
        answer["sections"] = [{
            "kind": "supporting", "title": "근거",
            "items": [{"text": "뒷받침합니다.", "citations": [citation]}] * 4,
        }]
    elif mutation == "too_many_citations":
        answer["overview"]["citations"] = [citation] * 4
    elif mutation == "text_too_long":
        answer["overview"]["text"] = "가" * 1_201
    elif mutation == "quote_too_long":
        citation["quote"] = "가" * 2_001
    elif mutation == "title_too_long":
        answer["sections"] = [{
            "kind": "supporting", "title": "가" * 121,
            "items": [{"text": "뒷받침합니다.", "citations": [citation]}],
        }]
    elif mutation == "insufficient_with_sections":
        answer = {
            "status": "insufficient_evidence", "overview": None,
            "sections": [{
                "kind": "supporting", "title": "근거",
                "items": [{"text": "확인됐습니다.", "citations": [citation]}],
            }],
            "conclusion": None, "model": None, "reasoning": None,
        }

    payload["answer"] = answer

    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)


@pytest.mark.parametrize("change", [
    {"evidence": [{
        "id": "e1", "claimId": "c1", "sourceId": "unknown",
        "quote": "Claim is supported.", "quoteVerified": True, "relation": "supports",
    }]},
    {"claims": [{**result_payload()["claims"][0], "evidenceIds": ["missing"]}]},
    {"claims": [{**result_payload()["claims"][0], "start": 1}]},
    {"claims": [{**result_payload()["claims"][0], "kind": "opinion"}]},
    {"sources": [{**result_payload()["sources"][0], "accessStatus": "unavailable"}]},
    {"evidence": [{
        "id": "e1", "claimId": "c1", "sourceId": "s1",
        "quote": "Claim is supported.", "quoteVerified": False, "relation": "supports",
    }]},
    {"extra": "not allowed"},
])
def test_final_contract_rejects_broken_links_or_unverified_evidence(change):
    payload = {**result_payload(), **change}
    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)


def test_response_contract_does_not_accept_internal_source_fields():
    payload = result_payload()
    payload["sources"] = [{**payload["sources"][0], "resolvedUrl": "https://example.org/final"}]
    with pytest.raises(ValidationError):
        FactCheckResult.model_validate(payload)


def test_partial_truth_parts_preserve_and_validate_their_own_evidence():
    payload = result_payload()
    payload["evidence"].append({**payload["evidence"][0], "id": "e2", "relation": "contradicts"})
    item = payload["claims"][0]
    item.update(verdictCode="partially_supported", verdict="일부 사실 · 일부 거짓", evidenceIds=["e1", "e2"])
    item["parts"] = [
        {"statement": "첫 항목입니다.", "verdictCode": "mostly_supported", "verdict": "대체로 확인됨",
         "factScore": 90, "summary": "첫 항목은 확인했습니다.", "evidenceIds": ["e1"]},
        {"statement": "둘째 항목입니다.", "verdictCode": "contradicted", "verdict": "반박하는 근거 확인",
         "factScore": 20, "summary": "둘째 항목은 반박했습니다.", "confirmed": ["근거에서 확인된 올바른 내용입니다."], "evidenceIds": ["e2"]},
    ]
    assert len(FactCheckResult.model_validate(payload).claims[0].parts) == 2
    assert FactCheckResult.model_validate(payload).claims[0].parts[1].confirmed == ["근거에서 확인된 올바른 내용입니다."]
    for links in (["e1"], ["missing"], []):
        item["parts"][1]["evidenceIds"] = links
        with pytest.raises(ValidationError):
            FactCheckResult.model_validate(payload)
