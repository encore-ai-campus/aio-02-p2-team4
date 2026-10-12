"""NDJSON boundary: only stage labels and validated final results are public."""
import asyncio
from contextlib import aclosing
import json
from contracts import FactCheckResponse
from runtime import build_progress_preview, build_progress_sources

STAGES = ('extracting', 'searching', 'reading', 'verifying', 'synthesizing')
MESSAGES = ('주장을 추출하고 있습니다.', '근거 출처를 검색하고 있습니다.', '출처 원문을 읽고 있습니다.', '인용과 판정을 검증하고 있습니다.', '확인된 원문 근거로 답변을 구성하고 있습니다.')


def encode(event):
    return json.dumps(event, ensure_ascii=False) + '\n'


async def stream_events(graph, payload, *, timeout=240):
    """Propagate cancellation and close the graph iterator on every exit path."""
    try:
        async with asyncio.timeout(timeout):
            yield encode({'type':'stage','stage':STAGES[0],'message':MESSAGES[0]})
            expected = STAGES[0]
            recoveries = 0
            state = dict(payload)
            async with aclosing(graph.astream(payload, stream_mode='updates')) as updates:
                async for update in updates:
                    for stage, values in update.items():
                        if stage != expected:
                            raise ValueError('Unexpected stage')
                        if values is None:
                            values = {}
                        if not isinstance(values, dict):
                            raise ValueError('Invalid stage update')
                        state.update(values)
                        if stage == 'synthesizing':
                            expected = None
                            response = FactCheckResponse.model_validate({'result':values.get('result')})
                            yield encode({'type':'result','result':response.result.model_dump(mode='json')})
                        else:
                            recovering = stage == 'verifying' and state.get('recoveryRequested') is True
                            if recovering:
                                if recoveries or state.get('recoveryCount') != 1:
                                    raise ValueError('Unexpected recovery')
                                recoveries += 1
                                expected = 'searching'
                            else:
                                expected = STAGES[STAGES.index(stage) + 1]
                            if stage in {'searching', 'reading'}:
                                sources = build_progress_sources(state)
                                if sources or state.get('recoveryCount') == 1:
                                    phase = 'found' if stage == 'searching' else 'read'
                                    yield encode({'type':'sources','phase':phase,'sources':sources})
                            elif stage == 'verifying' and not recovering:
                                preview = build_progress_preview(state)
                                yield encode({'type':'preview',**preview})
                            message = ('다른 출처를 한 번 더 검색하고 있습니다.' if recovering
                                       else MESSAGES[STAGES.index(expected)])
                            yield encode({'type':'stage','stage':expected,'message':message})
            if expected is not None:
                raise ValueError('Incomplete graph')
    except TimeoutError:
        yield encode({'type':'error','code':'TIMEOUT','message':'검증 시간이 초과되었습니다.'})
    except ValueError as exc:
        code = str(exc).split(':', 1)[0]
        if code == 'MODEL_FAILED':
            yield encode({'type':'error','code':'MODEL_FAILED','message':'선택한 모델이 응답하지 않았습니다. 다른 모델을 선택해 다시 시도해 주세요.'})
        elif code == 'MODEL_UNAVAILABLE':
            yield encode({'type':'error','code':'MODEL_UNAVAILABLE','message':'선택한 모델의 API 키가 설정되어 있지 않습니다.'})
        elif code == 'PROVIDER_AUTH_FAILED':
            yield encode({'type':'error','code':'PROVIDER_AUTH_FAILED','message':'모델 인증이 거부되었습니다. 서버의 API 키와 사용 권한을 확인해 주세요.'})
        elif code == 'PROVIDER_TIMEOUT':
            yield encode({'type':'error','code':'PROVIDER_TIMEOUT','message':'모델 응답이 지연되어 검증을 중단했습니다. 다른 모델로 다시 시도해 주세요.'})
        elif code == 'MODEL_OUTPUT_INVALID':
            yield encode({'type':'error','code':'MODEL_OUTPUT_INVALID','message':'모델 응답 형식이 올바르지 않아 판정을 확인하지 못했습니다. 다시 시도해 주세요.'})
        elif code == 'VERIFICATION_FAILED':
            yield encode({'type':'error','code':'VERIFICATION_FAILED','message':'출처 대조 과정에서 실패했습니다. 잠시 후 다시 시도해 주세요.'})
        else:
            yield encode({'type':'error','code':'AGENT_FAILED','message':'검증을 완료하지 못했습니다.'})
    except Exception:
        yield encode({'type':'error','code':'AGENT_FAILED','message':'검증을 완료하지 못했습니다.'})
