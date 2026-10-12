# 2026-10-10 하이브(Hive) API 연결 및 Experiential 제거 검증

## 1. 개요
- **목적:** 공식 문서(`https://docs.thehive.ai/docs/chat-completions-openai-compatible-llms`)에 기반하여 DeepSeek-V4.1-Flash MAX 모델을 하이브(Hive) OpenAI 호환 API로 연결하고, 기존 Experiential 연결(`api.experientiallabs.ai`)을 완전히 제거하며, UI 상에서 태그를 Hive로 표기하고 해당 모델 선택 시 하이브 API로 라우팅되도록 적용합니다.
- **적용 모델:** `DeepSeek-V4.1-Flash MAX`
  - Hive API 모델 키: `deepseek-ai/deepseek-v4.1-flash`
  - Base URL: `https://api-cdn.thehive.ai/api/v3`
  - Chat completions 경로: `/chat/completions`
  - 헤더: `Authorization: Bearer <HIVE_API_KEY>`
  - 추론 설정: `reasoning_effort="max"`
  - 토큰 한도: `max_completion_tokens=max(16_000, max_output_tokens)`
  - 구조화 응답: OpenAI 호환 JSON 모드 (`response_format={"type": "json_object"}`)

## 2. 변경 내역
1. **백엔드 공급자 및 런타임 (`backend/providers.py`, `backend/runtime.py`)**
   - `ProviderKind`: `"hive" | "openai" | "gemini"`로 전환 (기존 `"experiential"` 제거).
   - `_HIVE_BASE_URL = "https://api-cdn.thehive.ai/api/v3"` 정의.
   - `Settings` 및 `load_settings`: `HIVE_API_KEY` 환경 변수 사용 (`explabs_api_key` 제거).
   - `_structured_payload`: Hive 전송 시 model 키를 `deepseek-ai/deepseek-v4.1-flash`, `max_completion_tokens` 필드 사용.
   - `_hive_text`: 응답 파싱 및 검증 (`finish_reason="stop"`, 유효한 JSON content, refusal/tool_call 실패 처리).
   - `request_search`: Hive는 검색 도구를 제공하지 않으므로 기존 Tavily/GPT/Gemini 검색으로 폴백.
2. **테스트 및 설정 파일**
   - `backend/tests/test_experiential.py` 삭제 및 `backend/tests/test_hive.py` (24개 단위/경계 테스트) 신규 작성.
   - `backend/tests/test_direct_answer.py`, `test_evidence_context.py`: `hive_api_key` 및 Hive 모델 wire 페이로드 검증 반영.
   - `backend/.env.example`: `EXPLABS_API_KEY` 제거 및 `HIVE_API_KEY` 추가.
   - `render.yaml`: 환경 변수 `HIVE_API_KEY`로 교체.
3. **프론트엔드 UI (`app/components/fact-check-dashboard.tsx`, `app/privacy/page.tsx`)**
   - 모델 선택 드롭다운(`GlideSelect`)에서 `deepseek-v4.1-flash`의 태그를 `Experiential`에서 `Hive`로 변경.
   - 드롭다운 옵션 또는 태그 클릭 시 `deepseek-v4.1-flash`가 선택되어 백엔드에서 Hive API로 라우팅.
   - 외부 전송 동의 창 안내 문구 및 개인정보 처리방침 안내 문구를 하이브(Hive) API로 갱신.

## 3. 검증 결과

| 검증 단계 | 명령어 | 결과 |
|---|---|---|
| 백엔드 전체 테스트 | `.\.venv\Scripts\pytest tests -q` | 440 passed, 1 warning (Starlette AnyIO 비권장 경고) |
| Hive 신규 경계 테스트 | `.\.venv\Scripts\pytest tests/test_hive.py -q` | 24 passed |
| 프론트엔드 전체 테스트 | `npm test` | 121 passed |
| TypeScript 타입 검사 | `npm run typecheck` | 통과 (오류 0건) |

## 4. 미검증 범위 및 주의사항
- 실제 유효한 Hive Secret Key(`HIVE_API_KEY`)가 환경 변수 또는 `backend/.env`에 입력되어야 외부 실호출이 가능합니다. 키가 없으면 Auto 순서에서 다음 모델로 안전하게 폴백되거나 단독 선택 시 `MODEL_UNAVAILABLE` 에러를 반환합니다.
- Render 등 배포 환경에서는 백엔드 환경 변수에 `HIVE_API_KEY`를 직접 설정해야 합니다.
