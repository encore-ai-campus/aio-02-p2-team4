"""의도 분류 UI 회귀용 합성 서버입니다. 외부 공급자와 실제 DB를 호출하지 않습니다."""
from collections import Counter
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import json
import asyncio
from pydantic import SecretStr
from runtime import RuntimeAdapters, Settings, build_runtime_workflow, make_runtime_adapters
from streaming import stream_events

app = FastAPI()
counts = Counter()
requests = []


@app.get('/qa/requests')
async def observed():
    return {'counts': dict(counts), 'requests': requests}


@app.get('/api/fact-check')
async def status():
    return {'configured': True, 'jevConfigured': False, 'webSearch': True,
            'model': 'gpt-6-luna', 'reasoning': 'max',
            'modelOptions': [{'id': id, 'configured': True} for id in
                            ['deepseek-v4.1-flash', 'gpt-6-luna', 'gemini-3.8-flash', 'gemini-3.7-flash']]}


@app.get('/api/conversations')
async def conversations():
    return {'items': [], 'nextCursor': None}


@app.get('/api/conversations/status')
async def storage_status():
    return {'configured': False, 'sessionAvailable': False}


@app.post('/api/intent')
async def intent(request: Request):
    body = await request.json()
    counts['intent'] += 1
    requests.append({'path': 'intent', 'text': body['text'], 'hasImage': bool(body.get('image')),
                     'linkUrl': body.get('linkUrl'), 'focus': body.get('focus'), 'context': body.get('context', {})})
    text = body['text']
    if text in {'2024년 한국 합계출산율은 0.75명이다.', '이 기사가 사실인지 확인해줘: 경제가 성장했다'}:
        return JSONResponse({'code': 'PROVIDER_AUTH_FAILED'}, status_code=502)
    if text in {'분류 실패 재현', 'ㅎㅇ', '개새야', '경제 성장 주장이 사실인지 확인해줘: 분류 장애 재현'}:
        return JSONResponse({'code': 'AGENT_FAILED'}, status_code=502)
    if text == '분류 중단 재현':
        await asyncio.sleep(20)
    target = 'current'
    focus = ''
    if text.startswith('이거 봐줘'):
        action, reply = 'clarify', '내용 설명과 사실 검증 중 어떤 작업을 원하시나요?'
    elif text in {'검증해줘', '다시 검색해서 검증해줘'}:
        action, reply, target, focus = 'verify', '', 'previous', text
    elif text == '다시 봐줘':
        action, reply, target = 'clarify', '이전 자료의 설명과 검증 중 어떤 작업을 원하시나요?', 'previous'
    elif '사실인지' in text or '사실인지' in body.get('focus', ''):
        action, reply = 'verify', ''
    elif text == '왜 접근이 안되지?' or '왜 접근이' in text:
        action, reply, target = 'reply', '이전 출처를 읽지 못했습니다. 현재 기록만으로 차단이나 로그인 문제인지는 확인할 수 없습니다.', 'previous'
    elif body.get('image'):
        action, reply = 'reply', '이미지에는 Render의 구독 요금제 비교표가 있습니다.'
        target = 'previous' if body.get('context', {}).get('previousAttachment') else 'current'
    else:
        action, reply = 'reply', '검증 없이 질문에 답변했습니다.'
    linked = body.get('linkUrl') or body.get('context', {}).get('previousLinkUrl')
    if linked and '설명해줘' in text and action == 'reply':
        return {'action': action, 'target': 'current' if body.get('linkUrl') else 'previous', 'reply': reply, 'focus': focus, 'readLink': True}
    return {'action': action, 'target': target, 'reply': reply, 'focus': focus}


@app.post('/api/summarize')
async def summarize(request: Request):
    body = await request.json()
    counts['summary'] += 1
    requests.append({'path': 'summary', 'text': body['text'], 'linkUrl': body.get('linkUrl')})
    return {'result': {'title': '합성 링크 설명', 'summary': '이 페이지의 요금제 내용을 설명했습니다.',
                       'points': [], 'sourceUrl': body.get('linkUrl'), 'sourceName': '합성 링크',
                       'warnings': [], 'model': 'gpt-6-luna', 'reasoning': 'max'}}


@app.post('/api/fact-check/stream')
async def verify(request: Request):
    body = await request.json()
    counts['verify'] += 1
    requests.append({'path': 'verify', 'text': body['text'], 'focus': body['focus'],
                     'hasImage': bool(body.get('image')), 'linkUrl': body.get('linkUrl')})
    if '실패 재현' in body['text']:
        return JSONResponse({'code': 'AGENT_FAILED', 'message': '합성 검증 실패입니다.'}, status_code=502)
    if '합성 제거 회귀' in body['text']:
        quote = '합성 제거 회귀'
        source = {'id': 's1', 'url': 'https://example.org/report', 'title': '회귀 시험 원문',
                  'publisher': 'Example', 'accessStatus': 'verified', 'sourceType': '기사'}
        source_text = 'This synthetic source supports the test claim under the stated conditions.'
        if '자막' in body['text']:
            source = {**source, 'url': 'https://www.youtube.com/watch?v=abcdefghijk',
                      'title': '검증 자막 원문', 'sourceType': '유튜브',
                      'youtubeTranscript': True, 'youtubeDataStatus': 'collected'}
        settings = Settings(api_key=SecretStr('test-only'))

        async def extract(state):
            start = state['text'].index(quote)
            return {'claims': [{'id': 'c1', 'quote': quote, 'start': start,
                                'end': start + len(quote), 'kind': 'fact'}]}

        async def search(state):
            return {'sources': [source]}

        async def read(state):
            return {'sources': [source], 'sourceTexts': {'s1': source_text}}

        async def judge(state):
            return {'claims': [{**state['claims'][0], 'factScore': 90, 'verdictCode': 'mostly_supported',
                                'verdict': '대체로 확인됨', 'tone': 'positive',
                                'summary': '시험 원문에서 해당 조건의 주장을 확인했습니다.',
                                'confirmed': ['원문과 인용이 일치합니다.'],
                                'unresolved': ['다른 시점에는 추가 확인이 필요합니다.'],
                                'warnings': [], 'evidenceIds': ['e1']}],
                    'evidence': [{'id': 'e1', 'claimId': 'c1', 'sourceId': 's1', 'quote': source_text,
                                  'quoteVerified': True, 'relation': 'supports'}],
                    'llmModel': 'gpt-6-luna', 'llmReasoning': 'max'}

        graph = build_runtime_workflow(settings, adapters=RuntimeAdapters(
            extract=extract, search=search, read=read, verify=judge,
            synthesize=make_runtime_adapters(settings).synthesize))
        return StreamingResponse(stream_events(graph, body), media_type='application/x-ndjson')
    result = {'text': body['text'], 'focus': body['focus'], 'demo': False,
              'checkedAt': datetime.now(timezone.utc).isoformat(), 'model': 'gpt-6-luna', 'reasoning': 'max',
              'claims': [], 'sources': [], 'evidence': [], 'warnings': ['합성 UI 시험 결과입니다.'],
              'answer': {'status': 'insufficient_evidence', 'overview': None, 'sections': [],
                         'conclusion': None, 'model': None, 'reasoning': None}}
    return StreamingResponse(iter([json.dumps({'type': 'result', 'result': result}, ensure_ascii=False)+'\n']),
                             media_type='application/x-ndjson')
