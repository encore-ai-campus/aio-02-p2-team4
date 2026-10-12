"""부분 사실 판정 회귀 테스트입니다. 공급자 응답과 원문은 시험 자료입니다."""
import copy

import pytest

from verification import ground_judgments


def mixed_case(text, anchors, statements):
    claims = [{"id": "c1", "quote": text, "kind": "fact", "start": 0, "end": len(text)}]
    texts = {"s1": "시험 원문에서 첫 번째 항목이 사실임을 확인합니다.",
             "s2": "시험 원문에서 두 번째 항목이 사실과 다름을 확인합니다."}
    sources = [{"id": source_id, "accessStatus": "verified"} for source_id in texts]
    parts = [{"quote": anchor, "statement": statement, "verdictCode": code,
              "factScore": score, "summary": f"시험 원문으로 해당 항목을 {status}했습니다.",
              "confirmed": [], "unresolved": [],
              "evidence": [{"sourceId": source_id, "quote": texts[source_id],
                            "relation": relation, "comparison": "same"}]}
             for anchor, statement, code, score, status, source_id, relation in zip(
                 anchors, statements, ["mostly_supported", "contradicted"], [90, 20],
                 ["확인", "반박"], ["s1", "s2"], ["supports", "contradicts"])]
    judgments = [{"claimId": "c1", "verdictCode": "contradicted", "factScore": 20,
                  "summary": "전체가 거짓이라는 잘못된 모델 요약입니다.", "confirmed": [],
                  "unresolved": [], "evidence": [], "parts": parts}]
    return claims, judgments, sources, texts


@pytest.mark.parametrize(("text", "anchors", "statements"), [
    ("이순신 장군은 한산도 대첩과 행주 대첩을 승리로 이끌었다.", ["한산도 대첩", "행주 대첩"],
     ["이순신 장군은 한산도 대첩을 승리로 이끌었다.", "이순신 장군은 행주 대첩을 승리로 이끌었다."]),
    ("세종대왕은 한글과 측우기를 발명했다.", ["한글", "측우기"],
     ["세종대왕은 한글을 발명했다.", "세종대왕은 측우기를 발명했다."]),
])
def test_one_original_claim_retains_separate_supported_and_refuted_parts(text, anchors, statements):
    result = ground_judgments(*mixed_case(text, anchors, statements))
    judged = result["claims"][0]
    assert len(result["claims"]) == 1
    assert judged["quote"] == text
    assert judged["verdictCode"] == "partially_supported"
    assert judged["verdict"] == "일부 사실 · 일부 거짓"
    assert judged["factScore"] == 55
    assert judged["confirmed"] == [statements[0]]
    assert judged["refuted"] == [statements[1]]
    assert [part["verdictCode"] for part in judged["parts"]] == ["mostly_supported", "contradicted"]
    assert [part["evidenceIds"] for part in judged["parts"]] == [["e1"], ["e2"]]
    assert all(item["claimId"] == "c1" for item in result["evidence"])


def test_rejected_counter_quote_is_unknown_instead_of_false():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    case[1][0]["parts"][1]["evidence"][0]["quote"] = "수집 원문에 없는 가짜 반박 인용입니다."
    judged = ground_judgments(*case)["claims"][0]
    assert judged["verdict"] == "일부만 확인됨"
    assert judged["refuted"] == []
    assert judged["parts"][1]["verdictCode"] == "insufficient_evidence"
    assert judged["confirmed"] == ["첫 항목입니다."]


def test_refuted_part_preserves_corrected_facts_and_their_source():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    correction = "시험 기록에는 둘째 항목의 주체가 다른 인물이라고 명시되어 있습니다."
    part = case[1][0]["parts"][1]
    part["confirmed"] = [correction]
    part["summary"] = correction
    case[3]["s2"] = correction
    part["evidence"][0]["quote"] = correction
    result = ground_judgments(*case)
    refuted = result["claims"][0]["parts"][1]
    assert refuted["confirmed"] == [correction]
    assert refuted["summary"] == correction
    assert result["evidence"][1]["sourceId"] == "s2"
    assert refuted["evidenceIds"] == [result["evidence"][1]["id"]]

    part["evidence"][0]["quote"] = "원문에서 확인할 수 없는 정정 인용입니다."
    refuted = ground_judgments(*case)["claims"][0]["parts"][1]
    assert refuted["verdictCode"] == "insufficient_evidence"
    assert refuted["confirmed"] == []


def test_mixed_claim_preserves_a_direct_corrective_summary():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    judgment = case[1][0]
    judgment["verdictCode"] = "partially_supported"
    judgment["summary"] = "첫 항목은 맞지만, 둘째 항목의 주체는 원문에 기록된 다른 인물입니다 [1][2]."
    result = ground_judgments(*case)["claims"][0]
    assert result["summary"] == judgment["summary"]
    assert result["verdict"] == "일부 사실 · 일부 거짓"

    judgment["parts"][1]["evidence"][0]["quote"] = "원문에 없는 반박 내용입니다."
    result = ground_judgments(*case)["claims"][0]
    assert result["verdict"] == "일부만 확인됨"
    assert result["summary"] != judgment["summary"]
    assert "검증 가능한 직접 인용이 부족" in result["summary"]


def test_inconsistent_parent_summary_falls_back_to_each_grounded_explanation():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    result = ground_judgments(*case)["claims"][0]
    assert result["summary"] != case[1][0]["summary"]
    assert all(part["summary"] in result["summary"] for part in result["parts"])
    case[1][0]["parts"][0]["summary"] = "가" * 2_000
    case[1][0]["parts"][1]["summary"] = "나" * 2_000
    result = ground_judgments(*case)["claims"][0]
    assert len(result["summary"]) <= 2_000
    assert "가" in result["summary"] and "나" in result["summary"]
    assert all(len(part["summary"]) == 2_000 for part in result["parts"])


def test_one_source_can_confirm_one_part_and_refute_another():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    case[3]["s1"] += " " + case[3]["s2"]
    case[1][0]["parts"][1]["evidence"][0]["sourceId"] = "s1"
    judged = ground_judgments(case[0], case[1], case[2][:1], {"s1": case[3]["s1"]})["claims"][0]
    assert judged["verdict"] == "일부 사실 · 일부 거짓"
    assert judged["confirmed"] == ["첫 항목입니다."]
    assert judged["refuted"] == ["둘째 항목입니다."]


def test_opposing_sources_for_the_same_part_remain_a_source_conflict():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    parts = case[1][0]["parts"]
    parts[0]["evidence"].append(copy.deepcopy(parts[1]["evidence"][0]))
    parts[1]["evidence"] = []
    judged = ground_judgments(*case)["claims"][0]
    assert judged["parts"][0]["verdictCode"] == "conflicting_sources"
    assert judged["verdictCode"] == "conflicting_sources"
    assert judged["refuted"] == []


def test_overlapping_parts_cannot_count_the_same_content_twice():
    case = mixed_case("첫 항목과 둘째 항목입니다.", ["첫 항목", "둘째 항목"], ["첫 항목입니다.", "둘째 항목입니다."])
    case[1][0]["parts"][0]["quote"] = case[0][0]["quote"]
    with pytest.raises(ValueError, match="INVALID_MODEL_OUTPUT"):
        ground_judgments(*case)
