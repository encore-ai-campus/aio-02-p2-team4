"""Offline citation-grounding and judgment tests; no provider traffic."""

import asyncio
import json

import httpx

from sources import html_text
from verification import ground_judgments, verify_claims


def claim(claim_id, quote, kind):
    return {
        "id": claim_id,
        "quote": quote,
        "kind": kind,
        "start": 0,
        "end": len(quote),
    }


def test_ground_judgments_marks_opinions_and_predictions_not_checkable():
    result = ground_judgments(
        [
            claim("c1", "이 정책은 훌륭하다", "opinion"),
            claim("c2", "내년에는 물가가 내려갈 것이다", "prediction"),
        ],
        [],
        [],
        {},
    )

    assert [item["verdictCode"] for item in result["claims"]] == [
        "not_checkable",
        "not_checkable",
    ]
    assert result["evidence"] == []
    assert all(item["evidenceIds"] == [] for item in result["claims"])


def test_ground_judgments_accepts_a_verified_contiguous_quote():
    quote = "The river reached record levels in 2024."
    result = ground_judgments(
        [claim("c1", "The river reached record levels.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "mostly_supported",
                "factScore": 85,
                "summary": "The source directly reports the record level.",
                "confirmed": ["The source reports record levels."],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": quote,
                        "relation": "supports",
                        "comparison": "same",
                    }
                ],
            }
        ],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": quote},
    )

    assert result["claims"][0]["verdictCode"] == "mostly_supported"
    assert result["claims"][0]["evidenceIds"] == ["e1"]
    assert result["evidence"] == [
        {
            "id": "e1",
            "claimId": "c1",
            "sourceId": "s1",
            "quote": quote,
            "quoteVerified": True,
            "relation": "supports",
        }
    ]


def test_ground_judgments_emits_one_quote_per_source_page():
    first_quote = "The agency reported a 4 percent rate in June."
    second_quote = "The agency confirmed the rate remained 4 percent in June."
    result = ground_judgments(
        [claim("c1", "The rate was 4 percent in June.", "fact")],
        [{
            "claimId": "c1",
            "verdictCode": "mostly_supported",
            "factScore": 85,
            "summary": "The source directly reports the rate.",
            "confirmed": [],
            "unresolved": [],
            "evidence": [
                {"sourceId": "s1", "quote": first_quote, "relation": "supports", "comparison": "same"},
                {"sourceId": "s1", "quote": second_quote, "relation": "supports", "comparison": "same"},
            ],
        }],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": f"{first_quote} {second_quote}"},
    )

    assert result["claims"][0]["verdictCode"] == "mostly_supported"
    assert result["claims"][0]["evidenceIds"] == ["e1"]
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["quote"] == first_quote


def test_ground_judgments_keeps_same_page_conflict_when_emitting_one_quote():
    support = "The agency reported that the rate was 4 percent in June."
    contradiction = "The agency reported that the rate was 6 percent in June."
    result = ground_judgments(
        [claim("c1", "The rate was 4 percent in June.", "fact")],
        [{
            "claimId": "c1",
            "verdictCode": "mostly_supported",
            "factScore": 85,
            "summary": "The source supports the claim.",
            "confirmed": [],
            "unresolved": [],
            "evidence": [
                {"sourceId": "s1", "quote": support, "relation": "supports", "comparison": "same"},
                {"sourceId": "s1", "quote": contradiction, "relation": "contradicts", "comparison": "same"},
            ],
        }],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": f"{support} {contradiction}"},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert "같은 출처" in result["claims"][0]["summary"]
    assert len(result["evidence"]) == 1


def test_ground_judgments_attaches_only_the_matching_section_not_the_whole_page():
    quote = '텔러린 앱은 여러 기능을 통합해 제공하는 서비스입니다.'
    section_text = quote + ' 사용자는 앱에서 메시지와 일정을 관리할 수 있습니다.'
    result = ground_judgments(
        [claim('c1', '텔러린 앱은 메시지와 일정을 제공한다.', 'fact')],
        [{
            'claimId': 'c1',
            'verdictCode': 'mostly_supported',
            'factScore': 85,
            'summary': '출처가 앱 기능을 설명합니다.',
            'confirmed': [],
            'unresolved': [],
            'evidence': [{
                'sourceId': 's1',
                'quote': quote,
                'relation': 'supports',
                'comparison': 'same',
            }],
        }],
        [{'id': 's1', 'url': 'https://example.org/mark', 'accessStatus': 'verified'}],
        {'s1': '4. 텔러린 앱 ' + section_text + ' 5. 자선 활동 별도 단락.'},
        source_sections={'s1': [
            {'level': 2, 'title': '4. 텔러린 앱', 'text': section_text, 'truncated': False},
            {'level': 2, 'title': '5. 자선 활동', 'text': '별도 단락.', 'truncated': False},
        ]},
    )

    assert result['evidence'][0]['sectionTitle'] == '4. 텔러린 앱'
    assert result['evidence'][0]['sectionText'] == section_text
    assert '5. 자선 활동' not in result['evidence'][0]['sectionText']
    assert result['evidence'][0]['sectionTruncated'] is False


def test_ground_judgments_omits_section_when_quote_matches_multiple_sections():
    quote = '공통 문장입니다. 여러 곳에 나옵니다.'
    result = ground_judgments(
        [claim('c1', '공통 주장이다.', 'fact')],
        [{
            'claimId': 'c1',
            'verdictCode': 'mostly_supported',
            'factScore': 85,
            'summary': '두 섹션에 같은 문장이 있습니다.',
            'confirmed': [],
            'unresolved': [],
            'evidence': [{
                'sourceId': 's1',
                'quote': quote,
                'relation': 'supports',
                'comparison': 'same',
            }],
        }],
        [{'id': 's1', 'url': 'https://example.org/dup', 'accessStatus': 'verified'}],
        {'s1': '첫 번째 섹션 공통 문장입니다. 여러 곳에 나옵니다. 두 번째 섹션 공통 문장입니다. 여러 곳에 나옵니다.'},
        source_sections={'s1': [
            {'level': 2, 'title': '첫 번째', 'text': '첫 번째 섹션 공통 문장입니다. 여러 곳에 나옵니다.', 'truncated': False},
            {'level': 2, 'title': '두 번째', 'text': '두 번째 섹션 공통 문장입니다. 여러 곳에 나옵니다.', 'truncated': False},
        ]},
    )

    assert 'sectionTitle' not in result['evidence'][0]
    assert 'sectionText' not in result['evidence'][0]


def test_ground_judgments_keeps_korean_translation_for_english_quote():
    quote = "A research prototype for a universal AI assistant."
    translation = "범용 AI 비서를 위한 연구용 프로토타입."
    result = ground_judgments(
        [claim("c1", "아스트라는 범용 AI 비서다", "unclear")],
        [{
            "claimId": "c1",
            "verdictCode": "mostly_supported",
            "factScore": 85,
            "summary": "출처가 해당 설명을 직접 제시합니다.",
            "confirmed": [],
            "unresolved": [],
            "evidence": [{
                "sourceId": "s1",
                "quote": quote,
                "quoteTranslation": translation,
                "relation": "supports",
                "comparison": "same",
            }],
        }],
        [{"id": "s1", "url": "https://example.org/ai", "accessStatus": "verified"}],
        {"s1": quote},
    )

    assert result["evidence"][0]["quoteTranslation"] == translation


def test_ground_judgments_accepts_a_verified_quote_for_an_unclear_checkable_claim():
    quote = "Astra is not AGI yet."
    result = ground_judgments(
        [claim("c1", "아스트라가 AGI라는게 사실이야?", "unclear")],
        [
            {
                "claimId": "c1",
                "verdictCode": "contradicted",
                "factScore": 10,
                "summary": "The source does not support calling Astra AGI.",
                "confirmed": ["The source says Astra is not AGI yet."],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": quote,
                        "relation": "contradicts",
                        "comparison": "same",
                    }
                ],
            }
        ],
        [{"id": "s1", "url": "https://example.org/astra", "accessStatus": "verified"}],
        {"s1": quote},
    )

    assert result["claims"][0]["verdictCode"] == "contradicted"
    assert result["claims"][0]["evidenceIds"] == ["e1"]


def test_invalid_quote_is_removed_and_downgrades_the_judgment():
    result = ground_judgments(
        [claim("c1", "The river reached record levels.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "mostly_supported",
                "factScore": 85,
                "summary": "The source confirms the claim.",
                "confirmed": ["The claim is confirmed."],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": "This sentence is not in the source.",
                        "relation": "supports",
                        "comparison": "same",
                    }
                ],
            }
        ],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": "The river reached record levels in 2024."},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["claims"][0]["evidenceIds"] == []
    assert result["claims"][0]["confirmed"] == []
    assert result["claims"][0]["warnings"]
    assert result["evidence"] == []


def test_valid_evidence_keeps_a_nuanced_summary_when_another_quote_is_rejected():
    valid_quote = "The source says Astra is still a research project."
    result = ground_judgments(
        [claim("c1", "Astra is AGI.", "unclear")],
        [{
            "claimId": "c1",
            "verdictCode": "mostly_supported",
            "factScore": 85,
            "summary": "현재 확인된 자료만으로는 아스트라를 AGI라고 단정하기 어렵다는 쪽에 무게가 실립니다.",
            "confirmed": [],
            "unresolved": ["AGI의 기준과 아스트라의 실제 평가 범위가 더 필요합니다."],
            "evidence": [
                {
                    "sourceId": "s1",
                    "quote": valid_quote,
                    "relation": "contradicts",
                    "comparison": "same",
                },
                {
                    "sourceId": "s1",
                    "quote": "This quote is not present.",
                    "relation": "supports",
                    "comparison": "same",
                },
            ],
        }],
        [{"id": "s1", "url": "https://example.org/astra", "accessStatus": "verified"}],
        {"s1": valid_quote},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["claims"][0]["summary"].startswith("현재 확인된 자료만으로는")
    assert result["evidence"][0]["quote"] == valid_quote


def test_search_summary_is_not_used_when_source_text_is_missing():
    result = ground_judgments(
        [claim("c1", "The river reached record levels.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "mostly_supported",
                "factScore": 85,
                "summary": "The search result says this is true.",
                "confirmed": [],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": "The search snippet says this is true.",
                        "relation": "supports",
                        "comparison": "same",
                    }
                ],
            }
        ],
        [
            {
                "id": "s1",
                "url": "https://example.org/report",
                "accessStatus": "verified",
                "snippet": "The search snippet says this is true.",
            }
        ],
        {},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["evidence"] == []


def test_player_controls_cannot_be_grounded_as_source_evidence():
    page = '''
        <main><article>
          <p>전문가들은 AGI 도달 시점에 관해 서로 다른 전망을 제시했다.</p>
          <div id="video-player">LIVE 00:00 / 20:00 Captions Settings</div>
        </article></main>
    '''
    extracted_text = html_text(page)
    result = ground_judgments(
        [claim("c1", "AGI will arrive by 2030.", "fact")],
        [{
            "claimId": "c1",
            "verdictCode": "mostly_supported",
            "factScore": 85,
            "summary": "The source confirms the timeline.",
            "confirmed": ["The source confirms the timeline."],
            "unresolved": [],
            "evidence": [{
                "sourceId": "s1",
                "quote": "LIVE 00:00 / 20:00 Captions Settings",
                "relation": "supports",
                "comparison": "same",
            }],
        }],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": extracted_text},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["claims"][0]["evidenceIds"] == []
    assert result["evidence"] == []


def test_date_or_context_mismatch_cannot_support_a_claim():
    result = ground_judgments(
        [claim("c1", "The river reached record levels.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "mostly_supported",
                "factScore": 85,
                "summary": "The source supports the claim.",
                "confirmed": [],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": "The river reached record levels in 2023.",
                        "relation": "supports",
                        "comparison": "different",
                    }
                ],
            }
        ],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": "The river reached record levels in 2023."},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert any("비교 조건" in warning for warning in result["claims"][0]["warnings"])
    assert result["evidence"] == []


def test_context_mismatch_is_reported_as_missing_context():
    quote = "The 2023 survey covered only urban households."
    result = ground_judgments(
        [claim("c1", "The survey covered all households.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "missing_context",
                "factScore": 50,
                "summary": "The geographic scope is narrower than the claim.",
                "confirmed": [],
                "unresolved": ["The survey did not cover rural households."],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": quote,
                        "relation": "context",
                        "comparison": "different",
                    }
                ],
            }
        ],
        [{"id": "s1", "url": "https://example.org/survey", "accessStatus": "verified"}],
        {"s1": quote},
    )

    assert result["claims"][0]["verdictCode"] == "missing_context"
    assert result["claims"][0]["evidenceIds"] == ["e1"]
    assert result["evidence"][0]["relation"] == "context"


def test_same_condition_support_and_contradiction_are_conflicting_sources():
    support = "The agency reported that the rate was 4 percent in June."
    contradiction = "The agency reported that the rate was 6 percent in June."
    result = ground_judgments(
        [claim("c1", "The rate was 4 percent in June.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "mostly_supported",
                "factScore": 85,
                "summary": "Only one source supports the claim.",
                "confirmed": [],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s1",
                        "quote": support,
                        "relation": "supports",
                        "comparison": "same",
                    },
                    {
                        "sourceId": "s2",
                        "quote": contradiction,
                        "relation": "contradicts",
                        "comparison": "same",
                    },
                ],
            }
        ],
        [
            {"id": "s1", "url": "https://one.example/report", "accessStatus": "verified"},
            {"id": "s2", "url": "https://two.example/report", "accessStatus": "verified"},
        ],
        {"s1": support, "s2": contradiction},
    )

    assert result["claims"][0]["verdictCode"] == "conflicting_sources"
    assert result["claims"][0]["evidenceIds"] == ["e1", "e2"]
    assert [item["relation"] for item in result["evidence"]] == ["supports", "contradicts"]


def test_unknown_claim_id_is_rejected_as_invalid_model_output():
    try:
        ground_judgments(
            [claim("c1", "A factual claim.", "fact")],
            [
                {
                    "claimId": "c2",
                    "verdictCode": "insufficient_evidence",
                    "factScore": 50,
                    "summary": "No direct source was found.",
                    "confirmed": [],
                    "unresolved": [],
                    "evidence": [],
                }
            ],
            [],
            {},
        )
    except ValueError as exc:
        assert str(exc) == "INVALID_MODEL_OUTPUT"
    else:
        raise AssertionError("unknown claim IDs must not be accepted")


def test_unknown_source_id_is_not_exposed_as_evidence():
    quote = "The river reached record levels in 2024."
    result = ground_judgments(
        [claim("c1", "The river reached record levels.", "fact")],
        [
            {
                "claimId": "c1",
                "verdictCode": "mostly_supported",
                "factScore": 85,
                "summary": "The source confirms the claim.",
                "confirmed": [],
                "unresolved": [],
                "evidence": [
                    {
                        "sourceId": "s-missing",
                        "quote": quote,
                        "relation": "supports",
                        "comparison": "same",
                    }
                ],
            }
        ],
        [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        {"s1": quote},
    )

    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["claims"][0]["evidenceIds"] == []
    assert result["evidence"] == []


def test_verify_claims_sends_only_verified_source_text():
    quote = "The river reached record levels in 2024."
    state = {
        "claims": [claim("c1", "The river reached record levels.", "fact")],
        "focus": "date and level",
        "sources": [
            {
                "id": "s1",
                "url": "https://example.org/report",
                "title": "Annual report",
                "publisher": "Example",
                "publishedAt": "2024-06-01",
                "accessStatus": "verified",
            },
            {
                "id": "s2",
                "url": "https://example.org/search-result",
                "accessStatus": "unavailable",
                "sourceType": "유튜브",
                "youtubeTitle": "YouTube API title",
                "youtubeComments": ["YouTube API raw comment must stay out of the judgment prompt."],
                "youtubeDataStatus": "collected",
                "snippet": quote,
            },
        ],
        "sourceTexts": {"s1": quote},
    }

    def handler(request):
        body = json.loads(request.content)
        input_data = json.loads(body["input"])
        assert body["model"] == "gpt-6-luna"
        assert body["reasoning"] == {"effort": "max"}
        assert body["store"] is False
        assert body["max_output_tokens"] >= 12000
        assert body["text"]["format"]["strict"] is True
        assert "For every contradicted claim or part, state the evidence-backed correct alternative in confirmed" in body["instructions"]
        assert [source["id"] for source in input_data["sources"]] == ["s1"]
        assert input_data["sources"][0]["passages"] == [{"start": 0, "end": len(quote), "text": quote}]
        assert "snippet" not in request.content.decode()
        assert "YouTube API raw comment" not in request.content.decode()
        assert "YouTube API title" not in request.content.decode()
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "claims": [
                                            {
                                                "claimId": "c1",
                                                "verdictCode": "mostly_supported",
                                                "factScore": 85,
                                                "summary": "The verified source reports the level.",
                                                "confirmed": ["The source reports record levels."],
                                                "unresolved": [],
                                                "evidence": [
                                                    {
                                                        "sourceId": "s1",
                                                        "quote": quote,
                                                        "relation": "supports",
                                                        "comparison": "same",
                                                    }
                                                ],
                                            }
                                        ]
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims(state, api_key="test-only", client=client)

    result = asyncio.run(run())
    assert result["claims"][0]["verdictCode"] == "mostly_supported"
    assert result["evidence"][0]["quote"] == quote


def test_verify_claims_bounds_source_text_sent_to_model():
    source_text = "A factual claim is reported here. " + ("Additional source text. " * 600)
    state = {
        "claims": [claim("c1", "A factual claim.", "fact")],
        "focus": "",
        "sources": [{"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}],
        "sourceTexts": {"s1": source_text},
    }

    def handler(request):
        body = json.loads(request.content)
        input_data = json.loads(body["input"])
        assert sum(len(passage["text"]) for passage in input_data["sources"][0]["passages"]) <= 6000
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps({"claims": [{
                        "claimId": "c1",
                        "verdictCode": "insufficient_evidence",
                        "factScore": 50,
                        "summary": "The bounded source excerpt is not sufficient.",
                        "confirmed": [],
                        "unresolved": ["The complete source was not supplied to the model."],
                        "evidence": [],
                    }]}),
                }],
            }],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims(state, api_key="test-only", client=client)

    result = asyncio.run(run())
    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"


def test_verify_claims_supports_gemini_interactions_structured_output():
    from providers import LLMProvider

    quote = "The river reached record levels in 2024."
    state = {
        "claims": [claim("c1", "The river reached record levels.", "fact")],
        "focus": "",
        "sources": [{
            "id": "s1",
            "url": "https://example.org/report",
            "title": "Annual report",
            "publisher": "Example",
            "accessStatus": "verified",
        }],
        "sourceTexts": {"s1": quote},
    }

    def handler(request):
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "gemini-test-only"
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.8-flash"
        assert body["generation_config"]["thinking_level"] == "high"
        assert body["response_format"]["mime_type"] == "application/json"
        return httpx.Response(200, json={
            "status": "completed",
            "steps": [{
                "type": "model_output",
                "content": [{
                    "type": "text",
                    "text": json.dumps({"claims": [{
                        "claimId": "c1",
                        "verdictCode": "mostly_supported",
                        "factScore": 85,
                        "summary": "The source reports the record level.",
                        "confirmed": ["The source reports record levels."],
                        "unresolved": [],
                        "evidence": [{
                            "sourceId": "s1",
                            "quote": quote,
                            "relation": "supports",
                            "comparison": "same",
                        }],
                    }]}),
                }],
            }],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims(
                state,
                client=client,
                provider=LLMProvider("gemini", "gemini-3.8-flash", "high", "gemini-test-only"),
            )

    result = asyncio.run(run())
    assert result["claims"][0]["verdictCode"] == "mostly_supported"
    assert result["evidence"][0]["quote"] == quote


def test_verify_claims_without_readable_sources_does_not_call_provider():
    state = {
        "claims": [claim("c1", "A factual claim.", "fact")],
        "focus": "",
        "sources": [
            {"id": "s1", "url": "https://example.org/report", "accessStatus": "unavailable"}
        ],
        "sourceTexts": {},
    }

    def handler(request):
        raise AssertionError("unreadable sources must not trigger a judgment request")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims(state, api_key="", client=client)

    result = asyncio.run(run())
    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert result["evidence"] == []


def test_verify_claims_requires_a_key_when_verified_source_text_exists():
    state = {
        "claims": [claim("c1", "A factual claim.", "fact")],
        "focus": "",
        "sources": [
            {"id": "s1", "url": "https://example.org/report", "accessStatus": "verified"}
        ],
        "sourceTexts": {"s1": "A factual claim is reported here."},
    }

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None)) as client:
            return await verify_claims(state, api_key="", client=client)

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert str(exc) == "NOT_CONFIGURED"
    else:
        raise AssertionError("verified source judgment requires a provider key")


def _units(text, char_index):
    return len(text[:char_index].encode("utf-16-le")) // 2


def test_neighbor_sentences_resolve_around_claim_offsets():
    from verification import _units_to_index, claim_neighbors

    assert _units_to_index("가나\U0001F600다", 0) == 0
    assert _units_to_index("가나\U0001F600다", 2) == 2
    assert _units_to_index("가나\U0001F600다", 3) == 2
    assert _units_to_index("가나\U0001F600다", 4) == 3
    assert _units_to_index("가나\U0001F600다", 99) == 4

    text = "첫 문장입니다. 이번 인상 폭은 가장 크다. 다음 문장이다. 마지막이다."
    quote = "이번 인상 폭은 가장 크다"
    start = text.index(quote)
    neighbors = claim_neighbors(
        text, {"id": "c1", "quote": quote, "start": _units(text, start), "end": 0})
    assert neighbors["before"] == ["첫 문장입니다."]
    assert neighbors["after"] == ["다음 문장이다."]

    first = claim_neighbors(text, {"id": "c1", "quote": "첫", "start": 0, "end": 1})
    assert first == {"before": [], "after": ["이번 인상 폭은 가장 크다."]}

    assert claim_neighbors("", {"id": "c1", "start": 0}) == {"before": [], "after": []}
    assert claim_neighbors(text, {"id": "c1"}) == {"before": [], "after": []}


def test_article_context_only_resolves_the_linked_source():
    from verification import _article_context

    state = {
        "linkUrl": "https://example.org/article",
        "sources": [
            {"id": "s1", "url": "https://example.org/other", "title": "Other",
             "publishedAt": "2026-01-01"},
            {"id": "s2", "url": "https://example.org/article", "title": "Real title",
             "publishedAt": "2026-02-02"},
        ],
    }
    assert _article_context(state) == {"title": "Real title", "publishedAt": "2026-02-02"}
    assert _article_context({}) == {"title": None, "publishedAt": None}


def test_verify_claims_sends_neighbors_and_article_to_model():
    import json

    import httpx

    from verification import verify_claims

    text = "첫 문장입니다. 이번 인상 폭은 가장 크다. 다음 문장이다."
    quote = "이번 인상 폭은 가장 크다"
    state = {
        "text": text,
        "focus": "",
        "linkUrl": "https://example.org/article",
        "claims": [{"id": "c1", "quote": quote,
                    "start": _units(text, text.index(quote)),
                    "end": _units(text, text.index(quote) + len(quote)),
                    "kind": "fact"}],
        "sources": [{"id": "s1", "url": "https://example.org/article",
                     "title": "기사 제목", "publishedAt": "2026-03-03",
                     "accessStatus": "verified"}],
        "sourceTexts": {"s1": quote + " 추가 원문 내용입니다."},
    }
    seen = {}

    def handler(request):
        body = json.loads(request.content)
        seen["input"] = json.loads(body["input"])
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps({"claims": [{
                        "claimId": "c1",
                        "verdictCode": "insufficient_evidence",
                        "factScore": 50,
                        "summary": "직접 근거가 부족합니다.",
                        "confirmed": [],
                        "unresolved": ["CONDITION_UNKNOWN"],
                        "evidence": [],
                    }]}),
                }],
            }],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify_claims(state, api_key="test-only", client=client)

    result = asyncio.run(run())
    assert result["claims"][0]["verdictCode"] == "insufficient_evidence"
    assert seen["input"]["article"] == {"title": "기사 제목", "publishedAt": "2026-03-03"}
    assert seen["input"]["neighbors"]["c1"]["before"] == ["첫 문장입니다."]
    assert seen["input"]["neighbors"]["c1"]["after"] == ["다음 문장이다."]
