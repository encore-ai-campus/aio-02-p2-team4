"""검증 완료 후 추가 공급자 호출 없이 판정 결과를 반환합니다."""
import asyncio
from copy import deepcopy

import pytest
from pydantic import SecretStr, ValidationError

from contracts import FactCheckAnswer
from runtime import Settings, make_runtime_adapters
import runtime


@pytest.mark.parametrize('material', [
    {'text': '짧은 사실 질문?'},
    {'text': '여러 주장을 포함하는 긴 원문입니다. ' * 200},
    {'text': '링크 내용 검증', 'linkUrl': 'https://example.org/article'},
    {'text': '이미지 내용 검증', 'image': {'mime': 'image/png', 'data': 'test-only'}},
    {'text': '미래 예측', 'claims': [{'kind': 'prediction', 'summary': '미래 예측은 확정할 수 없습니다.'}]},
    {'text': '여러 주장', 'claims': [{'kind': 'fact'}, {'kind': 'opinion'}]},
    {'text': '근거 없음', 'sources': [], 'sourceTexts': {}},
])
def test_finalization_never_opens_a_provider_for_any_material(monkeypatch, material):
    def forbidden(*args, **kwargs):
        raise AssertionError('최종 결과 구성에서 외부 공급자를 호출하면 안 됩니다.')

    monkeypatch.setattr(runtime.httpx, 'AsyncClient', forbidden)
    state = {'sources': [{'id': 's1', 'accessStatus': 'verified', 'sourceType': '기사'}],
             'sourceTexts': {'s1': '읽은 원문입니다.'}, **material}
    before = deepcopy(state)
    update = asyncio.run(make_runtime_adapters(Settings(api_key=SecretStr('test-only'))).synthesize(state))
    assert state == before
    assert update['answer']['status'] == 'judgment_only'
    assert update['answerModel'] is None and update['answerReasoning'] is None


def test_judgment_only_contract_has_no_generated_blocks_or_model():
    empty = {'status': 'judgment_only', 'overview': None, 'sections': [],
             'conclusion': None, 'model': None, 'reasoning': None}
    assert FactCheckAnswer.model_validate(empty).status == 'judgment_only'
    for change in ({'model': 'gpt-6-luna'}, {'reasoning': 'max'},
                   {'overview': {'text': '생성한 설명', 'citations': []}},
                   {'sections': [{'kind': 'context', 'title': '설명', 'items': [{'text': '본문', 'citations': []}]}]}):
        with pytest.raises(ValidationError):
            FactCheckAnswer.model_validate({**empty, **change})


def test_legacy_partial_answers_still_require_cited_overview_and_conclusion():
    block = {'text': '과거 복구 답변입니다.', 'citations': [{'sourceId': 's1', 'quote': '확인된 원문입니다.'}]}
    answer = {'status': 'partial', 'overview': block, 'sections': [],
              'conclusion': block, 'model': None, 'reasoning': None}
    assert FactCheckAnswer.model_validate(answer).status == 'partial'
    for change in ({'overview': None}, {'conclusion': None},
                   {'overview': {**block, 'citations': []}}):
        with pytest.raises(ValidationError):
            FactCheckAnswer.model_validate({**answer, **change})
