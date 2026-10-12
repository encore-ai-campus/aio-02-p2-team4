# FactLens 백엔드

이 디렉터리는 FastAPI와 LangGraph로 구성된 팩트체크 API입니다. 주장을 분류하고 검색어를 만들며, 관련 출처를 찾고 원문을 읽은 뒤 직접 인용을 검증해 근거 기반 답변을 구성합니다. 기본 실행 주소는 `http://127.0.0.1:8010`입니다.

## 요구 사항

- Python 3.11 이상
- [uv](https://docs.astral.sh/uv/) 패키지 관리자
- 지원되는 LLM 제공자 중 하나 이상의 서버 측 API 키

## 설치 및 실행

저장소 루트에서 백엔드 디렉터리로 이동해 의존성을 설치하고 환경 파일을 만듭니다.

```powershell
Set-Location backend
uv sync --locked
Copy-Item .env.example .env
```

`backend/.env`를 열어 사용할 키를 설정한 다음 백엔드를 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8010
```

백엔드 상태는 `http://127.0.0.1:8010/health`에서 확인할 수 있습니다. 이 경로는 프로세스가 실행 중인지 확인하며, LLM 키나 외부 제공자 응답 가능성까지 검사하지는 않습니다. 프런트엔드 실행법은 저장소 루트의 [README](../README.md)를 참고하세요.

## 환경 변수

키는 `backend/.env` 또는 백엔드 프로세스 환경 변수에 설정합니다. `.env`는 Git에서 제외됩니다. 키를 소스 코드, 프런트엔드 환경 변수, 브라우저 번들 또는 저장소에 넣지 마세요.

| 변수 | 용도 |
|---|---|
| `HIVE_API_KEY` | DeepSeek V4.1 Flash MAX를 하이브(Hive) API로 호출합니다. 서버 전용입니다. 키는 Hive Service API Keys에서 생성합니다. |
| `GEMINI_API_KEY` | Gemini 3.8 Flash 및 Gemini 3.7 Flash 사용에 필요합니다. |
| `OPENAI_API_KEY` | GPT-6 Luna 사용과 OpenAI 웹 검색 경로에 필요합니다. |
| `TYPESAFE_API_KEY` | JEV 고속 판정(TypeSafe System One) 사용에 필요합니다. 없으면 JEV 스위치가 비활성화되고 일반 LLM 검증만 동작합니다. |
| `TAVILY_API_KEY` | 선택 사항입니다. 설정하면 Tavily 검색을 LLM 검색과 함께 사용합니다. |
| `SERPAPI_API_KEY` | 선택 사항입니다. 무료 요금제 조건이 확인되면 Google 자연검색을 사용합니다. |
| `YOUTUBE_API_KEY` | 선택 사항입니다. 검색 결과에 YouTube 영상이 있을 때 영상 정보와 공개 댓글을 가져오는 데 사용합니다. |
| `FINNHUB_API_KEY` | 선택 사항입니다. 주가 조회 어댑터에 사용합니다. |

Hive·OpenAI·Gemini 키 중 하나 이상을 설정해야 LLM 검증을 시작할 수 있습니다. 모델을 `auto`로 선택하면 키가 설정된 모델만 다음 순서로 시도합니다.

1. DeepSeek V4.1 Flash (`deepseek-v4.1-flash`, `reasoning_effort=max`)
2. GPT-6 Luna (`max`, Fast 처리; 추출·검색·판정·개요·요약 전 경로 동일)
3. Gemini 3.8 Flash (`high`)
4. Gemini 3.7 Flash (`high`)

`auto`가 아닌 특정 모델을 선택하면 구조화 LLM 호출은 그 모델만 호출합니다. 선택한 모델이 설정되어 있지 않거나 응답하지 않으면 다른 모델로 자동 전환하지 않습니다. DeepSeek는 공급자 내장 웹 검색이 없어 검색 단계만 기존 Tavily 또는 GPT/Gemini 검색을 사용합니다. DeepSeek 단독 설정으로 검색이 필요한 검증을 실행하려면 `TAVILY_API_KEY` 또는 기존 검색 모델의 키도 필요합니다.

DeepSeek의 모든 텍스트·이미지 구조화 호출은 `https://api-cdn.thehive.ai/api/v3/chat/completions`와 `HIVE_API_KEY`만 사용합니다. 모델 키는 `deepseek-ai/deepseek-v4.1-flash`입니다. GPT/Gemini의 엔드포인트와 키는 변경하지 않습니다. DeepSeek에는 JSON 모드와 스키마 안내를 보내고 기존 Pydantic 검증을 유지합니다. MAX 추론과 JSON 출력의 공통 예산은 최소 16,000토큰(`max_completion_tokens`)이며, 단계에서 더 큰 예산을 요청하면 해당 값을 보존합니다. 이는 최대 허용량이며 매번 모두 사용하지는 않습니다. 긴 출력은 시간·비용이 늘 수 있고 기존 90초 호출 제한은 유지됩니다. 중단·거절·스키마 오류는 여전히 실패로 처리합니다. [공식 호환성 안내](https://docs.thehive.ai/docs/chat-completions-openai-compatible-llms), [DeepSeek 모델 안내](https://docs.thehive.ai/docs/deepseek-v41-flash)를 참고하세요.

현재 Render Blueprint의 `HIVE_API_KEY`는 `sync: false`입니다. 기존 서비스에 새 변수를 추가해도 자동으로 값을 묻거나 로컬 키를 복사하지 않으므로, 배포 시 백엔드 Environment에 직접 설정해야 합니다. 프런트엔드에는 설정하지 않습니다.

## 검색·검증 흐름

1. 입력에서 검증할 주장과 검색어를 추출합니다. 최대 3개 주장을 처리합니다.
2. `SERPAPI_API_KEY`가 있으면 계정이 무료 요금제이고, 월 요금이 0이며, 추가 크레딧이 없고, 필요한 무료 검색 쿼터가 남았는지 먼저 확인합니다. 조건을 확인할 수 없으면 SerpApi 검색 요청을 보내지 않고 기존 LLM 웹 검색으로 대체합니다.
3. 검색 후보 중 최대 6개 출처를 읽고 페이지 원문을 정리합니다. 검색 요약만으로 직접 인용을 만들지 않습니다.
4. 모델이 제시한 인용을 실제로 읽은 원문과 대조하고, 근거가 확인된 범위에서 답변을 구성합니다.

SerpApi는 확인된 무료 쿼터 안에서만 호출하도록 제한되어 있지만, 무료 쿼리 한도는 검색 요청으로 차감됩니다. LLM 제공자 API 사용량과 비용은 SerpApi 한도와 별개입니다. 무료 요금제나 잔여량을 확인할 수 없으면 일반 웹 검색으로 대체되며, 이때 표시되는 검색 후보 순서는 Google 자연검색 순위가 아닙니다. YouTube 공개 댓글은 맥락 정보로만 표시하며 팩트 점수나 직접 인용 근거로 사용하지 않습니다.

## API

| 메서드와 경로 | 설명 |
|---|---|
| `GET /health` | 프로세스 생존 상태와 실행 중인 코드 리비전을 반환합니다. 제공자 연결 검사는 하지 않습니다. |
| `GET /api/fact-check` | 설정된 모델과 워크플로 준비 상태를 반환합니다. |
| `POST /api/fact-check` | 팩트체크를 실행하고 완료된 JSON 결과를 반환합니다. |
| `POST /api/fact-check/stream` | 진행 단계와 최종 결과를 NDJSON 스트림으로 반환합니다. 프런트엔드는 이 스트리밍 경로를 사용합니다. |

팩트체크 요청 예시는 다음과 같습니다.

```json
{
  "text": "AGI는 2030년 안에 오나?",
  "focus": "",
  "consent": true,
  "modelPreference": "auto"
}
```

`consent`는 반드시 `true`여야 합니다. 텍스트는 1~12,000자, 확인 초점은 최대 500자입니다. 모델 선택값은 `auto`, `deepseek-v4.1-flash`, `gemini-3.8-flash`, `gemini-3.7-flash`, `gpt-6-luna` 중 하나입니다.

`/api/intent`도 `consent: true`를 필수로 받습니다. 모든 외부 POST 경로는 누락·false·문자열·숫자·null 동의를 외부 클라이언트 생성 전에 422로 거부합니다. 브라우저는 최초 안내에서 사용자가 선택한 동의를 동일 사이트의 다음 질문·새로고침에 재사용하며 철회·사이트 데이터 삭제·안내 버전 변경 시 다시 확인합니다. 전송 동의와 아래의 대화 보관 동의는 별개이고 `consent`는 이용자 인증 수단이 아닙니다.

## 대화 저장 · Render PostgreSQL

기존 검증과 별도인 `/api/conversations` API가 대화 생성·목록·메시지 저장·복원·삭제를 제공합니다. `DATABASE_URL`과 최소 32자 무작위 `CONVERSATION_SESSION_SECRET`은 무시되는 `backend/.env` 또는 Render 백엔드 환경 설정에만 둡니다. 키를 바꾸면 기존 익명 쿠키가 무효화됩니다. 브라우저·Next.js·Git에는 넣지 않습니다.

- 로컬 및 다른 PC에서 실행하는 백엔드: **External Database URL**, TLS, 해당 네트워크의 공인 IP 허용 규칙을 사용합니다.
- 같은 워크스페이스·Singapore 리전의 Render 백엔드: **Internal Database URL**을 사용합니다.
- DB 설정이 없거나 실패해도 기존 검증은 사용할 수 있으며, 저장 재시도는 LLM을 호출하지 않습니다.

백엔드 디렉터리에서 실행합니다. 마이그레이션은 프로젝트의 두 테이블만 반복 가능하게 생성하며 기존 데이터나 DB를 삭제하지 않습니다.

```powershell
uv sync --locked
uv run python migrate_conversations.py --init-session-secret
uv run python smoke_test_conversations.py
```

`--init-session-secret`은 Git ignore가 확인된 `.env`에 서명 키가 없을 때만 생성합니다. Render에서는 환경 설정에 서명 키를 별도로 넣고 `uv run python migrate_conversations.py`만 실행합니다. 합성 DB 시험은 임시 대화만 만들고 종료 시 삭제하며 접속 정보·실제 사용자 대화를 출력하지 않습니다.

연결 풀은 최대 4개이며 DB 작업 제한은 3초입니다. 목록은 최대 30개, 메시지는 최신 100개까지 조회하고 이전 페이지를 제공합니다. 큰 한국어 답변이 모이면 응답 바이트 상한을 지키도록 페이지당 메시지 수를 줄입니다. 원문 전체·이미지·YouTube API 메타데이터/댓글·시장 데이터·진행 중 메시지는 저장하지 않습니다. 복원한 결과는 원래 검증 시각의 과거 기록입니다.

무료 시연 DB: `true-or-not-conversations`, Singapore, PostgreSQL 18, 2026-11-03 만료 예정. 공개 웹서비스 배포·백업·유료 전환은 별도 범위입니다.

삭제 시 제목과 메시지·결과를 제거하고 내용 없는 생성 요청 삭제 표식만 유지합니다. 다른 탭의 늦은 재시도로 삭제한 대화가 재생성되는 것을 차단합니다.

브라우저 재현 시험은 `tests/browser/conversation_smoke.py`와 `conversation_restore_regression.py`에 보존했습니다. 합성 대화만 사용하며 실제 LLM을 호출하지 않습니다. 백엔드 8017, 해당 백엔드에 연결한 개발 프론트 3017을 별도로 실행하고 백엔드 디렉터리에서 `uv run --with playwright python tests/browser/conversation_smoke.py` 또는 `uv run --with playwright python tests/browser/conversation_restore_regression.py`로 실행합니다. 로컬 Chrome이 필요하며 실행 후 시험 서버를 종료합니다.

## 일반 테스트 및 점검

백엔드 디렉터리에서 오프라인 테스트를 실행합니다.

```powershell
uv run pytest -q
uv lock --check
```

SerpApi 연결을 실제로 확인하려면 다음 명령을 사용할 수 있습니다.

```powershell
uv run python smoke_google_serp.py
```

이 점검은 계정 상태를 확인한 뒤 `AGI 2030년`으로 Google 검색 요청 1회를 보낼 수 있으므로 무료 검색 쿼터를 사용합니다. 키 값은 출력하지 않습니다. 실제 LLM 검증은 제공자 API 사용량이 발생할 수 있으므로, 자동 테스트와 구분해 실행하세요.
