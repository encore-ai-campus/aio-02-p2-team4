"""Local True or Not API backed by the assembled LangGraph workflow."""
import hmac
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from streaming import stream_events
from pydantic import BaseModel, ConfigDict, Field

from contracts import AgentStatus, ContentSummary, FactCheckResponse
from intent import classify_intent
from jev import JevError
from summarize import summarize_content
from providers import ProviderAuthenticationError, ProviderCallError, configured_model_options, configured_providers, providers_for_preference, run_with_fallback
from runtime import build_runtime_workflow, load_settings, run_jev_fast_check
from schemas import FactCheckRequest
from conversation_api import router as conversation_router, storage_error
from conversation_store import ConversationStore, StorageError
from dotenv import dotenv_values


@asynccontextmanager
async def lifespan(app):
    values = dotenv_values(Path(__file__).with_name('.env'))
    app.state.conversation_store = ConversationStore(os.getenv('DATABASE_URL',values.get('DATABASE_URL') or ''))
    try:
        yield
    finally:
        await app.state.conversation_store.close()


app = FastAPI(title="True or Not Backend", version="0.1.0", lifespan=lifespan)
app.include_router(conversation_router)


@app.exception_handler(StorageError)
async def conversation_error(request, error):
    return storage_error(error)


@app.middleware('http')
async def conversation_body_limit(request, call_next):
    if request.url.path.startswith('/api/conversations'):
        try:
            if int(request.headers.get('content-length','0')) > 524288:
                return storage_error(StorageError('BODY_TOO_LARGE'))
        except ValueError:
            return storage_error(StorageError('INVALID_REQUEST'))
    return await call_next(request)


def _code_revision() -> str:
    """Identify the running tree so a stale deployment is visible via /health."""
    try:
        root = Path(__file__).resolve().parent.parent
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=5,
        )
        revision = head.stdout.strip()
        if head.returncode != 0 or not revision:
            return "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=5,
        )
        if dirty.returncode == 0 and dirty.stdout.strip():
            revision += "-dirty"
        return revision
    except Exception:
        return "unknown"


_CODE_REVISION = _code_revision()


@app.middleware("http")
async def _shared_secret_gate(request: Request, call_next):
    """Require the proxy secret on API routes when one is configured.

    Unset (local default) means open on loopback. /health always stays open
    so hosting health checks keep working.
    """
    if request.url.path != "/health":
        expected = os.environ.get("BACKEND_SHARED_SECRET", "")
        if expected:
            provided = request.headers.get("x-factlens-secret", "")
            if not hmac.compare_digest(provided, expected):
                return JSONResponse(
                    {"code": "FORBIDDEN", "message": "백엔드 접근이 거부되었습니다."},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )
    return await call_next(request)


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["factlens-backend"] = "factlens-backend"
    revision: str = "unknown"


@app.get("/health", response_model=HealthStatus)
async def health():
    """Report process liveness, not provider readiness."""
    return HealthStatus(revision=_CODE_REVISION)


@app.get("/api/fact-check", response_model=AgentStatus)
async def agent_status(response: Response):
    """Report whether the real four-stage workflow can be constructed."""
    response.headers["Cache-Control"] = "no-store"
    settings = load_settings()
    providers = configured_providers(settings)
    configured = bool(providers)
    primary = providers[0] if providers else None
    return AgentStatus(
        configured=configured,
        jevConfigured=bool(settings.typesafe_api_key.get_secret_value().strip()),
        workflowReady=configured,
        engine="langgraph",
        model=primary.model if primary else None,
        reasoning=primary.reasoning if primary else None,
        webSearch=bool(settings.tavily_api_key.get_secret_value().strip()) or any(provider.kind != "hive" for provider in providers),
        modelOptions=configured_model_options(settings),
        phase="workflow-ready" if configured else "api-foundation",
    )


def get_workflow():
    """Build the provider-backed graph only when a server-side key is configured."""
    settings = load_settings()
    if not configured_providers(settings):
        return None
    return build_runtime_workflow(settings)


@app.post("/api/fact-check", response_model=FactCheckResponse)
async def fact_check(payload: FactCheckRequest, graph=Depends(get_workflow)):
    if graph is None:
        return JSONResponse(
            {"code": "NOT_CONFIGURED", "message": "서버의 LLM provider 설정이 필요합니다."},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    try:
        state = await graph.ainvoke(payload.model_dump(exclude_defaults=True))
        response = FactCheckResponse.model_validate({"result": state.get("result")})
        return JSONResponse(
            response.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        # Do not expose provider diagnostics, input text, or partial internal state.
        return JSONResponse(
            {"code": "AGENT_FAILED", "message": "검증을 완료하지 못했습니다."},
            status_code=502,
            headers={"Cache-Control": "no-store"},
        )


@app.post("/api/summarize")
async def summarize(payload: FactCheckRequest):
    """Summarize content for research; never judges truth."""
    if payload.image is not None:
        return JSONResponse(
            {"code": "INVALID_REQUEST", "message": "이미지 요약은 지원하지 않습니다. 텍스트나 링크로 보내주세요."},
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )
    settings = load_settings()
    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            result = await summarize_content(
                text=payload.text,
                focus=payload.focus,
                link_url=payload.linkUrl,
                image=None,
                consent=payload.consent,
                settings=settings,
                client=client,
                model_preference=payload.modelPreference,
            )
        response = ContentSummary.model_validate(result)
        return JSONResponse(
            {"result": response.model_dump(mode="json")},
            headers={"Cache-Control": "no-store"},
        )
    except ValueError as exc:
        messages = {
            "INVALID_REQUEST": (422, "요약 요청을 확인해 주세요."),
            "NOT_CONFIGURED": (503, "서버의 LLM provider 설정이 필요합니다."),
            "NO_CONTENT": (422, "요약할 내용을 찾지 못했습니다. 원문·링크를 확인해 주세요."),
            "SOURCE_UNREADABLE": (502, "링크 원문을 읽지 못했습니다."),
            "SOURCE_TOO_LONG": (422, "30분 이상 영상은 요약하지 않습니다."),
            "SUMMARIZE_FAILED": (502, "요약을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."),
        }
        status, message = messages.get(str(exc), (502, "요약을 만들지 못했습니다."))
        return JSONResponse(
            {"code": str(exc), "message": message},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )


@app.post("/api/fact-check/stream")
async def fact_check_stream(payload: FactCheckRequest, graph=Depends(get_workflow)):
    if graph is None:
        return JSONResponse({'code':'NOT_CONFIGURED','message':'서버의 LLM provider 설정이 필요합니다.'}, status_code=503, headers={'Cache-Control':'no-store'})
    return StreamingResponse(stream_events(graph, payload.model_dump(exclude_defaults=True)), media_type='application/x-ndjson', headers={'Cache-Control':'no-store','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff'})


@app.post("/api/fact-check/jev")
async def fact_check_jev(payload: FactCheckRequest):
    """Jev fast path: one verdict, no pipeline stages."""
    if not payload.jevMode:
        return JSONResponse(
            {"code": "INVALID_REQUEST", "message": "Jev 모드 요청이 아닙니다."},
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )
    if payload.image is not None:
        return JSONResponse(
            {"code": "INVALID_REQUEST", "message": "Jev 모드에서는 이미지를 지원하지 않습니다."},
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )
    settings = load_settings()
    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            result = await run_jev_fast_check(
                text=payload.text,
                focus=payload.focus,
                link_url=payload.linkUrl,
                consent=payload.consent,
                client=client,
                api_key=settings.typesafe_api_key.get_secret_value(),
                settings=settings,
                model_preference=payload.modelPreference,
            )
    except JevError as exc:
        messages = {
            "LOW_CONFIDENCE": "JEV가 확신하지 못했습니다. 증거가 엇갈리거나 부족합니다.",
            "GATEWAY_ERROR": "JEV 게이트웨이 호출에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            "NOT_CONFIGURED": "JEV 키 설정이 필요합니다. backend/.env를 확인해 주세요.",
            "NO_JUDGMENT": "JEV가 판정을 반환하지 않았습니다.",
            "BAD_RESPONSE": "JEV 응답 형식이 올바르지 않습니다.",
            "INVALID_REQUEST": "JEV 모드 요청이 아닙니다.",
        }
        code = exc.code if isinstance(exc.code, str) else "AGENT_FAILED"
        return JSONResponse(
            {"code": code, "message": messages.get(code, "Jev 판정에 실패했습니다.")},
            status_code=502,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        result.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


class IntentClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    quote: str = Field(max_length=200)
    verdict: str = Field(max_length=100)
    score: int = Field(ge=0, le=100)


class IntentContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    previousText: str | None = Field(default=None, max_length=12000)
    previousFocus: str = Field(default="", max_length=500)
    previousLinkUrl: str | None = Field(default=None, max_length=2048)
    previousClaims: list[IntentClaim] = Field(default_factory=list, max_length=3)
    recentUser: list[str] = Field(default_factory=list, max_length=5)
    recentAssistant: list[str] = Field(default_factory=list, max_length=2)
    previousSources: list["IntentSource"] = Field(default_factory=list, max_length=6)
    previousWarnings: list[str] = Field(default_factory=list, max_length=8)
    previousAttachment: bool = False


class IntentSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(max_length=2048)
    title: str = Field(max_length=300)
    accessStatus: Literal["verified", "unavailable"]


class IntentRequest(FactCheckRequest):
    focus: str = Field(default="", max_length=500)
    context: IntentContext = Field(default_factory=IntentContext)


@app.post("/api/intent")
async def intent(payload: IntentRequest):
    """동일 공급자 호출에서 의도를 분류하고 일반 답변을 반환합니다."""
    settings = load_settings()
    try:
        providers = providers_for_preference(settings, payload.modelPreference)
    except ValueError:
        return JSONResponse(
            {"code": "NOT_CONFIGURED", "message": "선택한 모델의 API 키가 설정되어 있지 않습니다."},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    if not providers:
        return JSONResponse(
            {"code": "NOT_CONFIGURED", "message": "서버의 LLM provider 설정이 필요합니다."},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            decision, _ = await run_with_fallback(
                providers,
                lambda provider: classify_intent(
                    payload.text,
                    payload.context.model_dump(),
                    client=client,
                    provider=provider,
                    focus=payload.focus,
                    image=payload.image.model_dump() if payload.image is not None else None,
                    link_url=payload.linkUrl,
                ),
            )
    except ProviderCallError as exc:
        authentication_failed = isinstance(exc, ProviderAuthenticationError)
        return JSONResponse(
            {"code": "PROVIDER_AUTH_FAILED" if authentication_failed else "AGENT_FAILED",
             "message": "선택한 모델의 인증에 실패했습니다. 서버 API 키와 접근 권한을 확인해 주세요."
             if authentication_failed else "의도 파악에 실패했습니다."},
            status_code=502,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        decision,
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(
        {"code": "INVALID_REQUEST", "message": "본문, 확인 요청 길이 및 외부 전송 동의를 확인해 주세요."},
        status_code=422,
        headers={"Cache-Control": "no-store"},
    )
