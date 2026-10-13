"""대화 저장 API입니다. 소유자는 서명 토큰에서만 확인합니다."""
import os
import time
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pathlib import Path
from dotenv import dotenv_values
from conversation_contracts import ConversationCreate, MessageCreate, StorageConsent
from conversation_session import issue_session, verify_session
from conversation_store import StorageError

router = APIRouter(prefix='/api/conversations')
STATUS = {'NOT_CONFIGURED':503,'STORAGE_UNAVAILABLE':503,'SESSION_REQUIRED':401,'SESSION_INVALID':401,'NOT_FOUND':404,'IDEMPOTENCY_CONFLICT':409,'INVALID_REQUEST':422,'BODY_TOO_LARGE':413}


def storage_error(error):
    return JSONResponse({'code':error.code,'message':'대화 저장 요청을 처리하지 못했습니다. 답변 내용은 유지됩니다.'},status_code=STATUS.get(error.code,503),headers={'Cache-Control':'no-store'})


def secret():
    value = setting('CONVERSATION_SESSION_SECRET')
    if len(value) < 32 or not setting('DATABASE_URL'):
        raise StorageError('NOT_CONFIGURED')
    return value


def setting(name):
    return os.getenv(name, dotenv_values(Path(__file__).with_name('.env')).get(name) or '')


def owner(request: Request):
    key = secret()
    token = request.headers.get('x-ton-session')
    if not token:
        raise StorageError('SESSION_REQUIRED')
    try:
        return verify_session(token,key,int(time.time()))
    except ValueError:
        raise StorageError('SESSION_INVALID') from None


async def body(request: Request):
    if request.headers.get('content-type','').split(';')[0].strip() != 'application/json':
        raise StorageError('INVALID_REQUEST')
    value = bytearray()
    async for chunk in request.stream():
        value.extend(chunk)
        if len(value) > 524288:
            raise StorageError('BODY_TOO_LARGE')
    try:
        import json
        return json.loads(value)
    except Exception:
        raise StorageError('INVALID_REQUEST') from None


def validated(model, value):
    try:
        return model.model_validate(value)
    except ValidationError:
        raise StorageError('INVALID_REQUEST') from None


def output(model):
    return JSONResponse(model.model_dump(mode='json'),headers={'Cache-Control':'no-store'})


@router.get('/status')
async def status():
    return JSONResponse({'configured':bool(setting('DATABASE_URL')),'sessionAvailable':len(setting('CONVERSATION_SESSION_SECRET'))>=32},headers={'Cache-Control':'no-store'})


@router.post('/session')
async def session(request: Request):
    validated(StorageConsent,await body(request))
    key = secret()
    token = request.headers.get('x-ton-session')
    if token:
        owner(request)
    else:
        token = issue_session(key,int(time.time()))
    return JSONResponse({'token':token},headers={'Cache-Control':'no-store'})


@router.get('')
async def list_conversations(request: Request, identity=Depends(owner),cursor: str | None = None):
    return output(await request.app.state.conversation_store.list(identity,cursor))


@router.post('')
async def create(request: Request, identity=Depends(owner)):
    payload = validated(ConversationCreate,await body(request))
    return output(await request.app.state.conversation_store.create(identity,payload))


@router.get('/{id}')
async def get(id: UUID, request: Request, identity=Depends(owner),beforeSequence: int | None = None):
    return output(await request.app.state.conversation_store.get(identity,id,beforeSequence))


@router.post('/{id}/messages')
async def append(id: UUID, request: Request, identity=Depends(owner)):
    payload = validated(MessageCreate,await body(request))
    if len(payload.model_dump_json().encode('utf-8'))>491520:
        raise StorageError('BODY_TOO_LARGE')
    return output(await request.app.state.conversation_store.append(identity,id,payload))


@router.delete('/{id}')
async def delete(id: UUID, request: Request, identity=Depends(owner)):
    await request.app.state.conversation_store.delete(identity,id)
    return JSONResponse({'deleted':True},headers={'Cache-Control':'no-store'})


@router.delete('')
async def delete_all(request: Request, identity=Depends(owner)):
    count = await request.app.state.conversation_store.delete_all(identity)
    return JSONResponse({'deleted':count},headers={'Cache-Control':'no-store'})
