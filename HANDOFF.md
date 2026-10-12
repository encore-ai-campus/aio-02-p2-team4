# 팩트체크 에이전트 UI MVP 작업 인계서

## 2026-10-10 DeepSeek MAX·하이브(Hive) API 전환 및 Experiential 제거

- **완료:** 기존 Experiential 게이트웨이 연결을 완전히 제거하고, `https://docs.thehive.ai/docs/chat-completions-openai-compatible-llms` 가이드에 따라 DeepSeek-V4.1-Flash MAX를 하이브(Hive) API로 전환했습니다.
- **호출 규격:**
  - Base URL: `https://api-cdn.thehive.ai/api/v3` (엔드포인트: `/chat/completions`)
  - Model Key: `deepseek-ai/deepseek-v4.1-flash`
  - 인증: `Authorization: Bearer <HIVE_API_KEY>` (환경변수 `HIVE_API_KEY`)
  - 추론 설정: `reasoning_effort="max"`
  - 출력 토큰: `max_completion_tokens=max(16_000, max_output_tokens)`
  - 구조화 응답: OpenAI 호환 JSON 모드 (`response_format={"type": "json_object"}`)
  - 멀티모달: `messages` 내 `image_url` data URL 전송 지원
- **UI 및 안내:**
  - 모델 선택 드롭다운에서 DeepSeek V4.1 Flash Max 항목의 태그를 `Experiential`에서 `Hive`로 갱신하였으며, 해당 항목 클릭 시 DeepSeek 모델이 선택되어 Hive API로 라우팅됩니다.
  - 외부 전송 동의 모달, 설정 안내 문구(`configurationHelp`), 개인정보 처리방침(`/privacy`)의 게이트웨이 안내를 하이브(Hive) API로 갱신했습니다.
- **검증:**
  - 백엔드 pytest 440개 전원 통과 (`tests/test_hive.py` 24개 테스트 신규 작성).
  - 프론트엔드 Node.js 테스트 121개 전원 통과.
  - TypeScript 타입 체크(`npm run typecheck`) 통과.

> 아래 2026-10-07 기록은 당시 동작입니다. 합성 실행·복구 경로는 이후 2026-10-08 합성 제거로 대체되었으며 과거 partial 결과의 읽기 호환만 유지합니다.

## 2026-10-07 검증된 일반 사실 판정을 최종 답변으로 재사용

- **완료:** 짧은 단일 질문에 한정했던 직접 조립을 일반 사실/유형 불명확 주장 1~3개로 확대했습니다. 질문 길이·물음표·진술문·링크/이미지 입력·일부 지지·조건/경고를 이유로 추가 합성을 호출하지 않습니다. 판정 요약·확인 내용·미해결 조건·경고와 연결된 직접 인용을 서버에서 배치하고 `grounded`로 반환합니다. 모든 사실 판정이 근거 부족이면 판정을 유지한 채 개요를 생략하고 종료합니다.
- **안전 경계:** 그래프의 원문/인용 검사와 최대 1회 재탐색을 유지합니다. 재탐색 전 임시 요약은 최종으로 사용하지 않습니다. 주장별 근거 ID·원문 전체·단일 발췌와 인용 방향을 검사하고, 출처 충돌에는 서로 다른 출처의 지지·반박을 함께 남깁니다. 문단 상한에 맞추려고 조건·경고를 잘라 버리지 않습니다. 완전한 재사용이 불가능하거나 예측/의견이 섞이면 기존 합성·상한 복구 경로를 유지합니다.
- **검증:** 최초 18개 실패 및 출처 충돌의 인용 순서 경계 1개 실패로 불필요한 합성 호출을 재현한 뒤 BE 537개·FE 109개·타입 검사를 통과했습니다. 재탐색 그래프는 추출 1회·판정 2회만 실행하고 마지막 판정과 인용만 최종에 남겼습니다. 실제 결과 JSON의 FE NDJSON 파싱·대화 스냅샷 복원도 통과했습니다. 프런트 코드·공개 계약·모델/추론/출력 한도·공급자 순서·동의/DB·AGENTS.md는 변경하지 않았습니다.
- **실호출:** 이전과 같은 다이아몬드 비 질문에서 추출 2.490초·검색 1.883초·읽기 0.536초·판정 46.947초·최종 서버 조립 0.002초, 전체 51.937초를 확인했습니다. 추가 합성 LLM 호출은 0회이며 기존 판정 요약과 일부 지지 65점·조건·원문 인용을 그대로 유지했습니다. answer.model/reasoning은 null이고 판정 모델 정보는 유지합니다.
- **남은 범위:** 이전 186.134초와 이번 51.937초는 각 1회 관측입니다. 판정 응답과 캐시 상태가 달라 전체 감소를 모두 이번 수정의 효과로 해석하지 않습니다. 확정한 것은 재사용 가능한 사실 답변의 추가 합성 호출 제거입니다. 판정 자체의 시간 최적화·예측/혼합 입력·한도 초과/불완전 근거의 추가 합성·반복 평균/p95·실제 브라우저/DB·원격 배포는 남습니다. [실행 기록](docs/qa/실행기록/2026-10-07-판정최종재사용.md)을 따릅니다. 진단 서버 종료와 8010 포트 닫힘을 확인했습니다. 사용자 지시에 따라 main에서 진행합니다.

## 2026-10-07 출력 상한 종료 답변 복구

- **완료:** 최종 합성에서만 출력 상한 종료를 복구합니다. 완성된 JSON·인용이면 `grounded`, 잘린 응답의 완성·검증 문단 또는 앞 단계의 검증된 사실 요약을 재사용하면 `partial`로 반환합니다. 추출·판정·이미지·검색은 기존 엄격한 응답 검사를 유지합니다.
- **안전 경계:** 원문 전체와 전달된 단일 발췌의 인용 검사를 유지합니다. 미완성 문자열·내부 추론·거부 응답은 노출하지 않습니다. 재사용은 연결된 검증 인용이 있는 지지/일부 지지/반박 사실 판정에 한정하며 확인·미해결·경고를 함께 보존합니다. 문단 한도를 넘는 조건을 잘라 버리지 않습니다. 안전한 답이 없으면 기존 실패 처리를 유지합니다.
- **계약·화면:** BE/FE에 `partial`을 추가하고 인용 필수 조건은 `grounded`와 동일하게 적용합니다. 화면에는 생성 중단·일부 생략 안내와 복구 답변을 함께 표시하며 저장·복원 후에도 상태와 출처 인용을 유지합니다. 모델·추론·키·출력 한도·공급자 순서·90초 타임아웃·AGENTS.md는 변경하지 않았습니다.
- **검증:** 새 BE 회귀 27개(최초 7개 실패 및 UTF-16 경계 1개 실패 재현), 전체 BE 531개·FE 109개·타입·프로덕션 빌드 통과. 실제 같은 질문 1회에서 DeepSeek 합성 90.011초 타임아웃 뒤 Luna 20.565초 출력 상한 종료(4,000토큰 전부 추론, 최종 텍스트 0자)를 검증 요약으로 복구했습니다. `partial`·일부 지지 65점으로 끝났고 Luna 축소 재시도·Gemini 추가 호출은 발생하지 않았습니다.
- **남은 범위:** 전체 186.134초로 응답 지연은 여전히 남습니다. 이전 진단과 판정/입력 패킷이 달라 속도·점수 전후 개선이나 반복 완료율의 증거로 사용하지 않습니다. DeepSeek 타임아웃·Gemini 요청 400·출력 없는 예측/의견·원격 배포·실제 브라우저/DB 통합은 별도 과제입니다. [출력 상한 복구 QA](docs/qa/실행기록/2026-10-07-출력상한복구.md)를 따릅니다. 진단 서버 종료·8010 포트 닫힘을 확인했습니다. 작업은 사용자 지시에 따라 main에서 진행합니다.

## 2026-10-06 1번: 관련 원문 구간·검증 근거 패킷

- **완료 범위:** 판정에는 기존 추출 검색어/주장과 관련된 원문 구간, 최종 생성에는 검증된 인용과 주변 구간·번역·관계·판정 결과를 전달합니다. 원문 전체를 다시 검색하거나 새 구간 선택 LLM을 호출하지 않습니다. 대화에서 승인한 1번이며 2번 근거 ID 출력·3번 생성 전 출력 범위 제한은 미구현입니다.
- **구간·안전 경계:** 원문 문자 위치와 정확한 발췌를 보존하고 일치 구간 앞뒤 450자의 범위를 병합합니다. 같은 검증 인용이 여러 위치에 나타나면 각 위치의 맥락을 보존합니다. 관련 구간이 없거나 맥락 발췌가 6,000자를 넘으면 기존 앞부분 입력으로 돌아가며 fallback임을 모델에 알립니다. 검증된 인용 묶음은 한도를 맞추려고 삭제하지 않습니다. 원문 전체 대조와 전달된 단일 구간 안의 인용 대조를 모두 통과해야 합니다.
- **예측·보존:** 예측/의견·검증 인용이 없는 출처는 contextOnly 맥락 발췌를 사용하고 사실 검증 근거로 승격하지 않습니다. 발언자·시점·부정·조건과 판정 summary/confirmed/unresolved/warnings·번역·외부 URL을 유지합니다. 4번 직접 답변의 원문 대조도 전체 보존 본문을 사용합니다. 모델·추론·출력 토큰 한도·검색 순위·JEV·동의·저장·AGENTS.md는 변경하지 않았습니다.
- **검증:** 새 회귀 최초 5개 실패와 영어 부분 문자열·반복 인용 맥락 누락 각 1개 실패를 재현한 뒤, 원문 위치·예측·부정/조건·지지/반박/맥락·폴백·단일 구간 검사 및 실제 DeepSeek 런타임 preview/result를 포함한 17개 회귀를 확인했습니다. 전체 BE 483개·FE 107개·타입 검사 통과. 합성 시험 자료의 입력 JSON은 사실 6,573→1,660자, 예측 6,431→1,052자입니다. 실제 토큰·응답 시간·평균/p95는 측정하지 않았습니다.
- **남은 범위·인계:** [근거 패킷 실행 기록](docs/qa/실행기록/2026-10-06-근거패킷.md)을 따릅니다. 원래 실패 증상의 실공급자 재현·속도/완료율 개선, 브라우저·Render 실통합, 2/3번 및 T14 실패 상태 분리는 남습니다. 구간 선택은 어휘 일치 기반이며 의미상 전체 관련성·모든 조건의 발견을 보장하지 않습니다. 코드 `7e8fdec`를 main에 푸시하고 기존 8010 백엔드를 같은 설정으로 재시작하여 health=ok·해당 코드 리비전을 확인했습니다. 기존 3000 프런트 및 사용자 파일은 보존했으며 이 확인을 실공급자 성능 검증으로 표시하지 않습니다.

## 2026-10-05 단순 사실 질문의 추가 합성 호출 제거

- **완료:** 짧은 단일 사실 질문에서 판정의 요약·확인 내용·미해결 내용·직접 인용을 재사용해 최종 답변을 서버에서 조립합니다. 기존 synthesizing/NDJSON 단계와 최종 응답 계약은 유지하되 조건을 충족하면 공급자 클라이언트·추가 LLM 요청을 만들지 않습니다.
- **적용 조건:** UTF-16 120단위 이하, 물음표(`?`/`？`) 1개로 끝나는 텍스트, 사실 주장 1개, mostly_supported/contradicted, 경고·CONDITION_UNKNOWN 없음, verified 비-YouTube 원문에서 유효한 주장/근거 ID·직접 인용 확인. 링크·이미지·JEV·예측/의견·판단 유보·여러 주장·진행 중 재탐색·문단 한도 초과는 기존 경로를 유지합니다. 확인/미해결 내용이 각 3개 또는 문단 1,200 UTF-16 단위를 넘으면 잘라 버리지 않고 기존 합성을 사용합니다.
- **검증·정보 보존:** 기존 인용 대조와 응답 계약 검증을 다시 적용합니다. 판정·점수·원문·영문 인용 번역·출처 링크를 유지하고 동일 인용은 중복 제거합니다. 별도 생성 호출이 없으므로 answer.model/reasoning은 null이며 실제 판정 모델 정보는 그대로입니다. 모델·추론 수준·키·검색·폴백·90초 제한·AGENTS.md는 변경하지 않았습니다.
- **시험:** 최초 회귀 3개 실패/29개 통과에서 불필요한 합성 1회와 그래프 LLM 3회를 재현했습니다. UTF-16 경계 2개 실패도 확인한 뒤 전체 BE 466개·FE 107개·타입 검사 및 실제 BE 조립 JSON→FE 파서/채팅/외부 출처 연결을 통과했습니다. 모의 그래프는 추출·판정 2회만 호출하고 preview→최종 result를 완료합니다. intent와 검색 호출은 별개로 유지되며 추가 유료 호출은 수행하지 않았습니다.
- **남은 범위:** [직접 조립 QA](docs/qa/실행기록/2026-10-05-직접답변.md)를 따릅니다. 실제 공급자 개선 후 시간·완료율·브라우저 시각 비교·Render 배포·복잡한 질문의 근거 패킷 최적화는 미검증입니다. T19/T14를 전체 완료로 표시하지 않으며 기존 3000 서버와 사용자 변경은 보존합니다.

## 2026-10-05 판정·최종 생성 구조 분석(미구현 제안)

- **확인:** `32d63a8`의 Graphify 경로와 실제 코드를 대조했습니다. 판정은 출처별 앞 6,000자에서 판정·요약·직접 인용·번역을 만들고 서버가 근거/조건을 검사합니다. 합성은 그 결과뿐 아니라 비-YouTube 출처별 앞 6,000자를 다시 받아 서술과 인용 문자열을 생성합니다. 원문을 다시 HTTP로 수집한다는 뜻은 아니며 별도 LLM 입력으로 재전달합니다.
- **출력 구조:** 현재 합성 계약은 최대 14개 문단·42개 인용 항목을 허용하며 문단 수를 출처 수에 맞추는 코드는 생성 후 실행합니다. 이는 허용 최대치이지 직전 실측에서 실제 해당 개수를 생성했다는 뜻은 아닙니다. 본문/추론별 출력 내역을 수집하지 않았으므로 16,000토큰을 장황한 본문으로 단정하지 않습니다.
- **우선 제안:** 모델·추론 설정을 유지한 채 판정에 주장별 관련 구간을 전달하고, 합성에는 검증된 근거 패킷과 근거 ID를 전달하여 표현 구성으로 역할을 좁힙니다. 인용 문자열·출처 링크는 서버가 복원하고 출력 범위는 생성 전에 제한합니다. 단순 사실 질문의 추가 합성 생략과 판정 결과 보존·합성 실패 구분을 검토합니다. 예측/의견은 기존 판정 근거가 비어 있을 수 있어 별도 맥락 구간을 확보하거나 기존 경로를 유지해야 합니다.
- **후속·검증:** 단일 LLM 호출에서 판정과 답변 초안을 함께 만드는 안은 서버 판정 조정·재탐색 이후 초안 무효화·출처 조건 정합 회귀가 필요한 후순위 대안입니다. 검증·원문 보존·직접 인용 검사를 제거하거나 독립적인 판정/합성을 단순 병렬화하는 안은 권장하지 않습니다. [구조 분석 기록](docs/qa/실행기록/2026-10-05-지연구조분석.md)에 기존 실측과 정적 검사·평가 조건을 기록했으며 실제 최적화·설정 변경·추가 유료 호출은 수행하지 않았습니다. T19/T14는 미완료 상태를 유지합니다.

## 2026-10-05 모델 설정 고정·단일 지연 측정

- **범위:** 현재 코드 `42f7d61`에서 “인류는 달에 갔나?”를 실제 intent와 백엔드 스트림 경로로 1회 실행했습니다. 별도 Python 진단 프로세스에서 기존 함수의 시간·호출 횟수만 관찰했으며 모델·추론 수준·출력 한도·프롬프트·검색·폴백·재탐색 정책은 변경하지 않았습니다. 모델 종류·추론 수준은 이번 원인 분석과 개선 변수에서 제외합니다.
- **실측:** 분류 2.45초→추출 2.68초→검색 1.90초→읽기 3.98초→판정 22.51초→최종 생성 64.96초로, 시작 후 33.53초에 1차 결과가 나오고 98.49초에 실패했습니다. 판정·생성 구간은 전체 대기의 88.8%, 단계 합계 밖 전환·준비는 약 0.017초입니다. 구조화 LLM 4회·Tavily 검색 1회·웹 원문 읽기 시도 3회를 관찰했고 재탐색·다른 모델 폴백은 발생하지 않았습니다.
- **실패 근거:** 최종 생성은 HTTP 200이지만 `finish_reason=length`, 보고된 출력 16,000토큰으로 종료했습니다. `providers.py`의 불완전 응답 거부가 `SYNTHESIS_FAILED`→`MODEL_FAILED`로 이어졌습니다. 90초 단일 호출 제한이나 240초 전체 제한에 걸린 사례가 아니며 16,000토큰 보완만으로 실공급자 완료가 보장되지 않는 것을 확인했습니다. 모델·MAX의 속도가 원인이라고 단정하지 않습니다.
- **한계·후속:** 성공한 최종 답변의 시간·평균/p95·브라우저/프록시/화면/DB 시간은 미측정입니다. 마지막 일반 웹 읽기 종료 뒤 read 단계 종료까지 약 2.99초가 남지만 다른 조회·후처리 시간을 분리하지 않아 CPU 처리로 단정하지 않습니다. 호출 수·판정/합성 입력 중복·후처리를 우선 조사하되 실제 최적화는 수행하지 않았습니다. [지연 측정 QA 기록](docs/qa/실행기록/2026-10-05-지연측정.md)과 잔여 T19를 따릅니다. 진단 프로세스는 정상 종료했으며 기존 서버·AGENTS.md·사용자 파일은 유지했습니다.

## 2026-10-05 DeepSeek MAX 출력 한도 보완

- **원인:** 20:19(KST) 답변 합성 호출의 게이트웨이 기록에서 출력 6,000토큰 중 추론 5,491토큰을 사용하고 `incomplete`로 종료한 것을 확인했습니다. 마지막 답변 생성 단계의 서버 오류·저장된 실패 시각과 일치합니다. GPT의 합성 실패는 상세 로그가 없어 동일 원인이라고 확정하지 않았습니다.
- **완료:** DeepSeek의 텍스트·이미지 구조화 호출에 적용하는 최소 출력 한도를 6,000에서 16,000토큰으로 늘렸습니다. 더 큰 단계별 요청은 보존하며 MAX·기존 모델/검색·인용 검증·폴백·90초 제한은 변경하지 않았습니다. 한도는 실제 사용량이 아니며 긴 출력의 시간·비용이 늘 수 있습니다. 아래 게이트웨이 연결 체크포인트의 초기 6,000토큰 설정을 대체합니다.
- **검증·남은 범위:** 수정 전 예산 검사 7개 실패를 재현한 뒤 전체 BE 429개·FE 107개·타입 검사를 통과했습니다(기존 Starlette/AnyIO 경고 1건). 기존 8010 백엔드 재시작·health/모델 상태 확인을 완료하고 3000 프런트엔드는 유지했습니다. 실제 공급자 재호출·개선된 완료율·원격 배포는 별도 검증 대상이며 오류 상세 분류·재시도는 이번 범위에 추가하지 않았습니다. [출력 한도 QA 기록](docs/qa/실행기록/2026-10-05-DeepSeek-출력한도.md)을 따릅니다. `AGENTS.md`·비밀 설정·기존 사용자 변경은 보존합니다.

## 2026-10-05 DeepSeek MAX·Experiential 게이트웨이

- **완료:** Auto에 `deepseek-v4.1-flash` MAX를 첫 순서로 추가하고 GPT-6 Luna MAX/Fast·Gemini 3.8/3.7 HIGH를 그대로 보존했습니다. 선택 항목·요청/결과 계약·설정 조회도 네 모델을 반영합니다.
- **호출 경계:** DeepSeek의 텍스트·이미지 호출은 고정 `https://api.experientiallabs.ai/v1/chat/completions`·서버 전용 `EXPLABS_API_KEY`만 사용합니다. JSON 모드·스키마 안내·기존 Pydantic 검증을 적용하고 추론과 JSON이 공유하는 최소 출력 예산은 6,000토큰입니다. 거절·불완전 출력·MAX 무시·잘못된 스키마는 성공으로 사용하지 않습니다.
- **검색·동의:** 검색 단계는 기존 Tavily 및 GPT/Gemini 도구를 사용합니다. DeepSeek 명시 선택도 검색만 기존 도구로 처리하며 구조화 LLM 호출은 DeepSeek에 고정합니다. NDJSON·취소·기존 공급자 요청은 유지합니다. 전송 안내에 Experiential을 추가하고 외부 전송 안내 버전을 v2로 갱신했습니다. 대화 저장 선택 v1·쿠키·DB 정책은 변경하지 않았습니다.
- **실호출:** 합성 입력으로 정확히 1회 호출하여 HTTP 200·`experiential_cloud`·`is_byok=false`·입력 237/출력 29/총 266토큰·보고 비용 $0.0001059를 확인했습니다. MAX를 요청했고 무시된 추론 설정 표시는 없었습니다. 원문 데이터나 키를 로그·문서에 남기지 않았습니다.
- **검증·남은 범위:** BE 421개·FE 107개·모의 브라우저의 네 모델/재동의/저장 선택 유지 경계를 검증했습니다. 실제 이미지·전체 검증 파이프라인·추론 중 토큰 스트리밍·Render 배포 실통합은 이번 합성 1회 호출로 확인하지 않았습니다. 기존 Render 서비스에는 `EXPLABS_API_KEY`를 별도 설정해야 합니다. [QA 기록](docs/qa/실행기록/2026-10-05-DeepSeek.md)을 따릅니다.

## 2026-10-05 대화 저장 선택 유지

- **완료:** 사용자가 확정한 대화 저장 선택을 동일 사이트·브라우저에서 새로고침 후에도 유지합니다. `ton_storage_consent`에는 별도 안내 버전만 기록하며 대화 본문·사용자 ID·소유권 쿠키는 넣지 않습니다. 처음 사용·기록 없음·잘못된/이전 버전 기록은 꺼짐입니다.
- **선택 경계:** 최초 동의 창과 하단 설정에서 확정할 때만 기록합니다. 저장 해제는 선택 기록을 제거하고 신규 저장을 중단하며 취소·닫기는 기록을 바꾸지 않습니다. 다른 탭의 해제·사이트 데이터 삭제도 반영합니다. 저장소 차단은 현재 화면만 적용하며 확정 직후에도 이전 기록이 남아 있을 가능성을 안내합니다. 정상 저장 재시도 후에는 해당 경고를 해제합니다.
- **소유권 유지:** IP가 아니라 기존 30일 HttpOnly 서명 쿠키로 대화 소유권을 확인합니다. 선택 유지가 로그인·기기 간 동기화나 쿠키 만료 후 접근을 제공하지 않습니다. DB·백엔드 계약·삭제·보관 정책은 변경하지 않았습니다.
- **검증:** 수정 전 새로고침 후 미체크 및 저장 해제 실패 안내 누락을 재현한 뒤 모의 Chrome의 23개 저장 선택 경계와 기존 외부 동의 회귀를 통과했습니다. 로컬 FE 107개·BE 404개·타입 검사·빌드를 통과했고 실제 공급자·DB 호출은 하지 않았습니다. [선택 유지 QA 기록](docs/qa/실행기록/2026-10-05-저장선택유지.md)을 따릅니다.

## 2026-10-05 저장 선택·안내 위치 정리

- **완료:** 데스크톱 사이드바와 모바일 대화 목록에서 저장 체크박스·접이식 개인정보 안내를 제거했습니다. 선택 사항인 ‘이 브라우저에서 대화 저장’은 최초 외부 전송 동의 창에 배치하고 ‘동의하고 시작’으로 확정합니다. 체크만 하거나 거절·닫기한 경우 기존 저장 설정을 유지합니다.
- **재설정·안내:** 웹 하단 ‘대화 저장 설정’에서 별도로 변경·확정·취소할 수 있습니다. 하단 개인정보 처리방침은 새 탭의 `/privacy#conversation-storage`로 연결되어 현재 입력·대화를 유지합니다. 이후 같은 날짜의 ‘대화 저장 선택 유지’ 보완에서 새로고침 기본 꺼짐을 확정한 선택 유지로 변경했습니다. 첫 사용 기본 꺼짐·기존 기록 복원 정책은 유지합니다.
- **검증:** 로컬 FE 107개·BE 404개(기존 Starlette/AnyIO 경고 1건)·타입 검사·프로덕션 빌드를 통과했습니다. API를 모두 모의 처리한 Chrome에서 저장 선택 14개 경계와 기존 외부 전송 동의 회귀를 검증했습니다. 같은 저장값을 확정해도 진행 중인 기록 조회를 취소하지 않으며 최초 창에서 선택한 첫 메시지·답변의 저장 순서도 확인했습니다. 실제 공급자·DB 호출, 로그인·백엔드 계약 변경은 수행하지 않았습니다. [저장 선택 QA 기록](docs/qa/실행기록/2026-10-05-저장선택안내.md)을 따릅니다.

## 2026-10-05 T11 최초 외부 전송 동의

- **완료:** 첫 intent·검증·JEV·요약 호출 전에 ‘동의하고 시작’을 선택합니다. 안내 버전만 동일 사이트·브라우저의 localStorage에 저장해 다음 질문과 새로고침 후 유지합니다. 거절·닫기는 입력을 보존하며 외부 호출을 하지 않습니다. 합성 예시와 로컬 모델 안내에는 외부 동의가 필요하지 않습니다.
- **철회·재확인:** 입력창의 ‘외부 전송 동의 철회’로 다음 요청을 차단하고 진행 중 요청의 취소를 시도합니다. 다른 탭의 철회도 반영합니다. 사이트 데이터 삭제·안내 버전 변경 시 다시 확인하며 저장 차단 환경에서는 현재 화면에서만 유지합니다. 이미 전송된 정보의 회수·삭제를 보장하지 않습니다.
- **경계:** Next.js 네 POST 프록시와 FastAPI 다섯 외부 POST 경로에서 동의 누락·false·문자열·숫자·null을 차단합니다. 대화 저장 동의는 여전히 별도 기본 꺼짐입니다. `consent=true`는 로그인·위조 요청 방지 인증이나 모든 법적 요건 충족을 뜻하지 않습니다.
- **검증·인계:** 로컬 FE 107개·BE 404개·타입 검사·프로덕션 빌드 및 모의 API 기반 Chrome 회귀를 통과했습니다. 실제 공급자·DB 호출은 수행하지 않았습니다. 상세 근거는 [최초 동의 실행 기록](docs/qa/실행기록/2026-10-05-최초동의.md), 완료 T11과 잔여 공개·운영자 검토 T15/T26은 [작업현황](docs/작업현황.md)을 따릅니다. 전송 대상·목적·범위가 바뀌면 대시보드의 `EXTERNAL_CONSENT_VERSION`을 함께 변경해야 합니다.
- **실행 서버:** 코드 커밋 `ccf0804`를 적용한 기존 백엔드를 같은 `127.0.0.1:8010`으로 재시작하고 `/health`의 `status=ok`·리비전 및 실제 동의 false 요청의 422 거부를 확인했습니다. 기존 3000 프론트엔드는 유지했고 임시 3018 포트·시험 브라우저는 종료했습니다. DB·비밀 설정·AGENTS.md는 변경하지 않았습니다.

## 2026-10-04 T33 대화 저장용 장기기억

- **완료:** My Workspace에 Render PostgreSQL `true-or-not-conversations`(Free·Singapore·PostgreSQL 18)을 실제 생성하고 연결했습니다. `conversations`·`messages` 테이블과 대화 생성·목록·저장·복원·이어쓰기·이전 메시지 조회·삭제를 구현했습니다. DB 장애 시 현재 답변을 유지하며, 저장만 재시도하면 LLM을 다시 호출하지 않습니다. DB 생성과 저장 기능 재구현은 잔여 작업이 아닙니다.
- **소유권·동의:** 서버가 검증하는 30일 HttpOnly 서명 쿠키로 같은 브라우저의 익명 소유권을 확인하고, 다른 소유자의 읽기·쓰기·삭제를 차단합니다. 대화 저장 동의는 기본 꺼짐이며 외부 API 전송 동의와 별개입니다. 저장 동의를 끄면 신규 저장을 중단하지만 기존 기록을 자동 삭제하지 않습니다.
- **저장 범위·제약:** 정제한 대화 메시지와 최종 검증 스냅샷만 저장합니다. 원문 전체·이미지·YouTube API 메타데이터/댓글·시장 데이터·진행 중 결과는 제외합니다. 복원 결과는 원래 검증 시각의 기록입니다. 쿠키 삭제·만료 또는 서명 키 변경 시 이전 기록에 접근할 수 없으며, 쿠키 만료는 DB 자동 삭제를 뜻하지 않습니다. 로그인·기기 간 동기화·벡터 검색·자동 기억 요약은 제공하지 않습니다.
- **삭제·복원 보완:** 사용자 삭제는 제목·메시지·결과를 제거하고 늦은 재시도의 재생성을 막는 내용 없는 기술 식별자만 남깁니다. YouTube 출처가 포함된 기록의 복원 검증 오류도 `a1fc050`에서 수정했으며, API 메타데이터를 다시 저장하는 방식으로 해결하지 않았습니다.
- **검증 근거:** 2026-10-04 실제 DB 합성 시험에서 중복 방지·다른 소유자 접근 차단·재연결·페이지 조회·삭제 후 부활 차단을 확인했습니다. 로컬 Chrome에서 저장·새로고침·복원·이어쓰기·저장만 재시도·동의 해제·삭제·모바일을 검증했습니다. 상세 시험과 당시 회귀의 후속 처리 경계는 [대화 저장 실행 기록](docs/qa/실행기록/2026-10-04-대화저장.md)을 따릅니다. 이번 인계 문서 보완에서는 DB나 실제 공급자를 다시 호출하지 않았습니다.
- **남은 범위:** T15의 공개 웹서비스 배포·원격 통합 시험과 T34의 운영 HTTPS 쿠키·소유권 경계 검증, 보관 기간·자동 삭제·백업·무료 DB 만료 대응이 남습니다. 기록된 무료 DB 만료 예정일은 **2026-11-03**이며, 영구 보관이나 백업을 보장하지 않습니다. PostgreSQL 선정·실제 생성·로컬 저장 구현은 완료 상태로 유지합니다.
- **설정·현황:** `DATABASE_URL`과 `CONVERSATION_SESSION_SECRET`은 서버 전용 비밀 설정에만 둡니다. 다른 PC의 로컬 백엔드는 External URL·TLS·해당 공인 IP 허용 규칙을, 같은 리전·워크스페이스의 Render 백엔드는 Internal URL을 사용합니다. 연결·마이그레이션·시험 방법은 [백엔드 README](backend/README.md), 완료 T33과 잔여 T15/T34·결정 사항 D13/D16/D17은 [작업현황](docs/작업현황.md)을 확인합니다.

## 2026-10-04 T13 숫자 계산 안전 경계

- **변경:** `backend/compute.py`는 원·달러·명·개·건과 천·만·억·조 접두 단위가 일치하는 명시적 `에서 … 으로/로`, `→`, `->` 변화만 계산합니다. 단위 내부는 일반 공백·탭만 정규화합니다. 인접 숫자를 임의로 연결하지 않으며, 단위 없음·다른 지표·단위 환산·가격 범위·분수 표기·연도·비율/퍼센트포인트·음수·지수 표기는 생략합니다. 일반 자연어의 모든 수치 의미를 해석하는 기능은 아닙니다.
- **가격:** 2,000원처럼 연도 범위와 겹치는 숫자도 명시적 측정 단위가 있으면 유지합니다. 2,000원→2,500원의 증감률은 25%입니다.
- **검증:** 초기 회귀 19개 실패·11개 통과 후 30개 통과, 리뷰 경계 보완 전 7개 실패·35개 통과 후 최종 42개 통과를 확인했습니다. 검증기 모델 입력의 `computed`에서도 잘못된 비교가 제외됨을 확인했습니다. 로컬 전체 BE 379개·FE 86개·타입 검사 통과, 기존 Starlette/AnyIO 경고 1건이 남습니다.
- **원격·서버:** [GitHub CI](https://github.com/teach97/TRUE-OR-NOT/actions/runs/37201781191)에서 BE 379개·FE 86개·타입 검사·프로덕션 빌드·잠금 의존성 검사를 통과했습니다. 기존 백엔드만 같은 `127.0.0.1:8010` 설정으로 재시작했고 `/health`의 `ok`와 수정 코드 리비전 `f8e3800`을 확인했습니다. 프론트엔드와 DB·환경 파일은 유지했습니다. 실제 공급자·DB 호출은 이번 검증에서 수행하지 않았습니다.
- **문서:** 상세 범위와 실행 근거는 [계산 QA 기록](docs/qa/실행기록/2026-10-04-계산.md), 현행 완료·잔여 범위는 [작업현황](docs/작업현황.md)을 따릅니다. 앞서 T18의 전체 Node 테스트 발견·FE/BE CI는 완료되었습니다.

## 2026-09-24 YouTube 영상 메타데이터와 댓글 아바타

- **영상 정보:** YouTube Data API `videos.list` 요청에서 `snippet,statistics`를 받아 영상 제목과 함께 채널명(`snippet.channelTitle`), 게시일(`snippet.publishedAt`), 조회수(`statistics.viewCount`)를 화면에 표시합니다. 조회수는 정수 문자열로 유지해 큰 값도 정밀도 손실 없이 쉼표 서식으로 렌더링합니다. UI의 날짜 라벨은 공식 API의 게시일 의미에 맞춰 `게시일`로 표시합니다.
- **댓글 아바타:** 각 공개 댓글 왼쪽에 로컬 SVG로 생성한 임의의 회색 프로필 그림을 배치합니다. 실제 댓글 작성자 사진·프로필 URL이나 개인정보는 요청하지 않으며, UI와 개인정보 안내에서 합성 이미지임을 밝힙니다.
- **계약·개인정보:** `youtubeChannelTitle`, `youtubePublishedAt`, `youtubeViewCount`를 Python/TypeScript 응답 계약까지 전달하고 길이·날짜·숫자 형식을 검증합니다. YouTube Data API에서 받은 제목·채널명·게시일·조회수·댓글은 기존 정책과 같이 JSON 내보내기에서 제외합니다. 동의 문구, 개인정보 처리방침, 이용약관을 갱신했습니다.
- **회귀 검증:** backend `236 passed` (기존 Starlette/AnyIO deprecation warning 1건), Node `17 passed`, `npm run typecheck`, Turbopack 기반 `npm run build`, `uv lock --check`, `git diff --check` 통과.
- **실 API:** 서버 환경에 `YOUTUBE_API_KEY`가 없어 Google API live 호출은 확인하지 않았습니다. 실제 사용 전 키를 서버 전용 `backend/.env`에 설정하고 재시작해 채널·게시일·조회수 응답을 확인해야 합니다. API 응답의 게시일은 영상 공개 시점을 나타내며, 비공개 상태로 올린 뒤 공개한 영상은 최초 업로드 시각과 다를 수 있습니다.

## 2026-09-23 중복 링크·일본어 검색 결과 보정

- **원인:** SerpApi 요청은 `gl=kr`, `hl=ko`만 설정해 검색 지역과 화면 언어를 지정했으며, 검색 문서 언어 제한이 없었습니다. URL 중복 제거도 검색 결과 단계에만 적용되어 다른 URL이 같은 최종 기사로 리디렉션되면 중복으로 남았습니다. AI 답변 UI는 문단마다 출처 전체 링크를 반복해서 렌더링했습니다.
- **검색 언어:** Google 요청에 `lr=lang_ko|lang_en`을 추가하고, 모든 검색 공급자 결과에서 `.jp` 도메인과 제목·요약에 일본어 가나가 있는 결과를 제외합니다. 원문 읽기 후에도 일본어 본문을 판별해 제외합니다. `candidateOrder`는 필터 전 Google 원래 순위를 유지합니다. 영어 페이지가 `.jp` 도메인을 쓰는 경우도 제외될 수 있습니다. SerpApi의 `lr` 언어 제한은 [공식 Google Search API 문서](https://serpapi.com/search-api)에 따릅니다.
- **중복 제거:** `www`, 끝 슬래시, 추적 매개변수와 쿼리 매개변수 순서를 정규화해 검색 단계에서 합치고, 원문 읽기 뒤 리디렉션 최종 URL도 비교합니다. 같은 페이지면 검색 순위가 높은 첫 항목과 그 원문만 유지합니다.
- **답변 표시:** AI 개요 안에서 동일한 출처 ID의 외부 링크는 한 번만 표시합니다. 같은 출처를 다시 인용하면 첫 링크를 가리키는 번호 참조로 보여주며, 한 문단 안의 반복 인용은 하나로 합칩니다.
- **실검색:** 무료 검색 1회로 `AGI 2030년`을 확인했습니다. 6개 출처는 startuprecipe.co.kr, m.joseilbo.com, brunch.co.kr, www.reddit.com, www.aitimes.kr, www.news1.kr이었으며 일본 `.jp` 사이트는 반환되지 않았습니다. 검색 시점·지역 및 Google 결과 개인화에 따라 순위는 달라질 수 있습니다.
- **회귀 검증:** backend `229 passed`(기존 Starlette/AnyIO deprecation warning 1건), Node `40 passed`, `npm run typecheck`, `npm run build` 통과. 브라우저에서 렌더링된 실제 UI 비교는 실행하지 않았습니다.

## 2026-09-23 무료 Google 자연검색 연동 및 GPT 실검증

- **검색 경로:** `backend/google_serp.py`가 `SERPAPI_API_KEY`가 설정된 경우에만 SerpApi 계정 API로 `Free`/`Free Plan`, 월 요금 0, 추가 크레딧 0, 주장별 검색어 수 이상 남은 무료 쿼터를 확인합니다. 조건을 충족할 때만 한국 설정(`hl=ko`, `gl=kr`)의 Google 자연검색 첫 페이지를 검색합니다. 최대 3개 고유 검색어를 사용하고 순위별 후보를 교차 배치해 전체 최대 6개를 읽습니다. 계정 확인 API는 무료이며 검색 쿼터를 차감하지 않습니다.
- **안전한 대체:** 계정·쿼터 확인이 안 되거나 SerpApi 검색이 실패하면 Google 순위를 꾸미지 않고 기존 GPT/Gemini 웹검색 후보로 대체하며 결과 경고를 남깁니다. 검색 snippet은 인용 근거로 쓰지 않고, 기존 원문 읽기·인용 검증 단계를 통과한 문구만 답변에 사용합니다. 유료 플랜 업그레이드나 자동 갱신 코드는 없습니다.
- **계약·UI:** `serpapi_google` 출처에는 해당 검색어의 `position`을 `Google 자연검색 N위`로 표시합니다. 기존 GPT/Gemini 후보 순서는 Google 순위라고 표시하지 않습니다. `aitimes.com`을 한국 기사 출처로 분류합니다.
- **실검색:** 서버에 설정된 키를 출력하지 않고 `AGI 2030년`으로 1회 연결 검사를 통과했습니다. 한국 설정의 1~6위 후보는 startuprecipe.co.kr, m.joseilbo.com, brunch.co.kr, aitimes.com, news1.kr, aimasterr.tistory.com이었습니다. 개인화·검색 위치·시각 차이로 사용자의 브라우저 순위와 완전히 같다고 보장하지 않습니다.
- **GPT 끝까지 검증:** `modelPreference=gpt-6-luna`로 같은 질문을 실제 5단계 그래프에 통과시켜 SerpApi 출처 6개, `grounded` 답변과 개요 인용 `s1`, `s4`를 확인했습니다. 개요는 2030년 도래 전망은 있으나 확정할 수 없다는 조건부 답변이었습니다. 처음 두 번의 시도는 PC 프록시 환경변수를 따르는 LLM HTTP 연결 때문에 추출 단계에서 실패했습니다. provider 연결을 `trust_env=False`로 바꾼 뒤 성공했으며, 값을 가진 환경변수나 키 자체는 출력하지 않았습니다.
- **검증:** backend 224 passed (기존 Starlette/AnyIO deprecation warning 1건), Node 39 passed, TypeScript 검사와 Turbopack 프로덕션 빌드 통과. 실검색 스크립트는 `backend/smoke_google_serp.py`이며 실행 시 무료 검색 1회를 사용할 수 있습니다. 프론트엔드 브라우저 실화면 비교는 이번 단계에서 실행하지 않았습니다.
- **운영:** `backend/.env.example`의 `SERPAPI_API_KEY`를 서버 전용 `backend/.env`에 설정하고 백엔드를 재시작합니다. GPT 등 LLM API 사용료는 SerpApi 무료 쿼터와 별개입니다. 실제 Google AI 개요와 동일한 답변을 보장하지 않으며, 확인된 원문 범위의 직접 답변만 생성합니다.

## 2026-09-23 검색 후보·답변 표현 보완

- 한국어 질문은 기존 OpenAI 웹검색에 한국 지역 힌트를 전달하고 검색 문맥 크기를 `medium`으로 늘렸습니다. 정확한 핵심 검색어를 먼저 사용하고, 결과가 부족할 때만 확장하도록 검색 지침을 조정했습니다.
- 검색 공급자가 반환한 후보의 순서·공급자·대표 검색어를 보존하고 출처 목록에 표시합니다. 중복 URL 및 동일 사이트 제한은 유지합니다. 이 순서는 Google 자연검색 순위가 아니며, 공급자가 실제로 어떤 질의를 실행했는지도 확인한 값은 아닙니다.
- 답변 합성 지침은 확인된 원문과 인용을 바탕으로 질문에 먼저 직접 답하고, 이후 근거와 남은 불확실성을 설명하도록 조정했습니다. 원문이 없거나 인용을 검증할 수 없으면 기존의 근거 부족 처리를 유지합니다.
- 오프라인 검증: 백엔드 205개, 프론트엔드 36개 테스트, TypeScript 검사와 Next.js Turbopack 프로덕션 빌드 통과. 기존 Starlette/AnyIO deprecation warning 1건이 있습니다. 실제 유료 LLM·검색 호출 및 Google 결과 비교는 하지 않았습니다.
- Google 상위 자연검색 결과를 그대로 인용하는 기능과 제3자 검색 API 연동은 아직 구현하지 않았습니다. 외부 검색 공급자 사용 여부와 검색어·키 전송에 대한 사용자 결정이 필요합니다.

## 2026-09-23 5단계 검색 개선 진행 현황

| 단계 | 범위 | 상태 |
|---|---|---|
| 1 | 주장·예측 질문에서 검색 키워드 추출 및 검색 단계 전달 | 완료 |
| 2 | 검색 후보 순서 보존 및 중복 출처 정리 | 완료. 현재 결과는 기존 검색 공급자 후보이며 Google 자연 검색 순위와 동일하다고 보장하지 않음 |
| 3 | 기사·페이지 본문 추출 및 화면 UI 문구 제거 | 완료 |
| 4 | YouTube 자막 대신 영상 제목과 공개 댓글(최대 10개) 수집·표시 | 구현·오프라인 검증 완료. `YOUTUBE_API_KEY` 미설정으로 실제 API 호출은 미검증 |
| 5 | 전망 질문의 찬반·불확실성 종합 및 본문 인라인 출처 표시 | 완료 (오프라인 모의 검증; 실제 provider 호출 미실행) |

### 5단계 구현 및 검증

- **최종 답변:** 기존 4단계 그래프 뒤에 원문 근거 기반 합성 단계를 추가해 `AI 개요`, 근거 유형별 섹션, 정리를 구조화 응답으로 만듭니다. 예측 claim의 `prediction` / `not_checkable` 판정과 검증기 결과는 합성 단계와 분리해 보존합니다. 검증기 모델은 결과 `model`에, 답변 합성 모델은 `answer.model`에 따로 기록합니다.
- **인용 경계:** 합성 입력은 원문을 읽은 verified 비-YouTube 출처 최대 6개이며 출처별 텍스트는 6,000자로 제한합니다. 검색 snippet·YouTube 영상 제목·댓글은 답변 근거에 넣지 않습니다. 모든 답변 블록의 출처 ID와 인용 문자열을 허용된 출처 및 원문 부분 문자열에 대조하고, 불일치 시 provider fallback을 시도합니다. 합성이 불가능하면 기존 claim·evidence를 유지하면서 `insufficient_evidence` 답변을 반환합니다.
- **화면:** AI 개요·조건부 전망·불확실성·정리를 응답 그대로 표시하고 인라인 출처 칩을 연결합니다. verified 비-YouTube 출처이며 안전한 HTTP(S) URL인 경우에만 새 탭 링크를 렌더링합니다. 근거 부족은 AI가 생성한 답처럼 보이지 않도록 고정 안내 문구를 표시합니다.
- **모델 순서:** 답변 합성도 Gemini 3.8 Flash → Gemini 3.7 Flash → GPT-6 Luna 순서를 사용합니다. 각 실제 provider 접근성과 계정별 호출 성공은 확인하지 않았습니다.
- **AGI 오프라인 회귀:** `AGI는 2030년 안에 오나?`를 5단계 그래프에 통과시키고, 조기 전망과 불확실성 원문에 정확히 포함되는 인용, 예측의 `not_checkable` 유지, 검증기/합성기 모델 분리, 확률·합의 과장 문구 부재를 고정 mock 응답으로 확인했습니다. 외부 네트워크 및 실제 LLM 호출은 사용하지 않았습니다.
- **Google 검색 한계:** 기존 검색 provider가 고른 후보와 실제 Google 자연 검색 상위 순위는 동일하다고 보장할 수 없습니다. 실제 Google SERP 순위 수집은 이 단계에서 구현하지 않았습니다. 원문 추출은 기존 공개 페이지 reader를 사용하며, YouTube 자막·트랜스크립트는 수집하지 않습니다.
- **최종 검증:** backend `uv run --no-sync pytest -q` **194 passed**, `uv lock --check` 통과, Node `node --experimental-strip-types --test` **33 passed**, `npm run typecheck` 통과, `git diff --check` 통과. 기존 Starlette/AnyIO deprecation warning 1건이 남습니다.
- **프로덕션 빌드:** 기본 `npm run build`의 Turbopack은 격리 worktree의 `node_modules` Junction이 worktree 밖을 가리켜 실패했습니다. 코드나 설정은 바꾸지 않고 `node node_modules/next/dist/bin/next build --webpack`으로 빌드·정적 페이지 생성을 완료했습니다. 따라서 Turbopack 빌드 자체는 미검증입니다.
- **후속 확인:** 실제 사용 전 비민감 질문으로 Gemini/OpenAI provider 연결과 응답 품질을 별도 확인해야 합니다. 그때도 답변 인용이 화면에 연결된 출처 원문과 일치하는지 확인하고, 실제 Google 상위 순위를 제품 요구로 삼는다면 순위 제공 검색 공급자 연동을 별도 결정해야 합니다.

### 4단계 구현 및 검증

- 공식 YouTube Data API `videos.list`에서 제목을, `commentThreads.list`에서 관련도순 공개 최상위 댓글을 최대 10개 조회합니다. 자막·영상·답글은 가져오지 않습니다. API 응답 크기는 256KB로 제한하고, 댓글을 가져오지 못해도 나머지 출처 처리는 계속됩니다.
- `backend/.env.example`에 `YOUTUBE_API_KEY` 항목을 추가했습니다. 로컬에서 사용하려면 `backend/.env`에 값을 설정하고 백엔드를 재시작해야 합니다. 현재 검증 환경에는 키가 설정되어 있지 않아 UI에는 `API 키 미설정` 상태가 표시됩니다. 키 값을 로그·문서·커밋에 기록하지 않습니다.
- 영상별 제목과 댓글은 결과 화면에 참고 맥락으로만 표시합니다. 댓글은 주장 검증용 `sourceTexts`, LLM 입력, 판정 및 인용 근거에 사용하지 않습니다. JSON 내보내기에서도 YouTube API 제목·댓글을 제거하며 서버 영속 저장은 추가하지 않았습니다.
- 개인정보 처리방침과 이용약관 페이지를 초안으로 추가했습니다. 운영자 정보·법적 검토가 완료된 문서가 아니므로 공개 서비스 전 검토가 필요합니다.
- 오프라인 회귀: backend **168 passed, 1 deselected**, frontend Node **27 passed**, `npx tsc --noEmit --incremental false`, `uv lock --no-cache --project backend --check`, `git diff --check` 통과. 기존 Starlette/AnyIO deprecation warning 1건이 남습니다. Windows 임시 디렉터리 권한 문제 때문에 `test_settings_load_file_without_exposing_key`만 실행에서 제외했습니다.
- 실제 YouTube API 호출과 브라우저 실화면 검증은 아직 하지 않았습니다. 다음 확인은 서버 전용 `YOUTUBE_API_KEY` 설정 후 실제 API에서 제목·댓글 응답 및 댓글 비활성 영상의 오류 표시를 확인하는 것입니다.
- 공식 API 문서: [videos.list](https://developers.google.com/youtube/v3/docs/videos/list), [commentThreads.list](https://developers.google.com/youtube/v3/docs/commentThreads/list), [YouTube API 개발자 정책](https://developers.google.com/youtube/terms/developer-policies).

## 2026-09-23 검색 개선 3단계 체크포인트

- **본문 추출:** 공개 페이지 HTML에서 `main`·`article`·`role=main`·`articleBody` 및 흔한 article/post 본문 컨테이너를 우선 선택합니다. 의미 있는 본문 표식이 없는 페이지는 보이는 텍스트를 보수적으로 정리해 사용합니다.
- **UI 문구 제외:** `head`·내비게이션·헤더·푸터·사이드바·폼·숨김 영역, 플레이어 UI 및 video/audio/custom player 태그를 본문 텍스트에서 제외합니다. 원문 검증은 이 정제된 `sourceTexts`에 대해서만 하므로 메뉴나 재생 컨트롤 문구를 인용으로 제안해도 근거로 통과하지 않습니다.
- **회귀 검증:** 기사 본문 선택, 메뉴·사이드바·영상 플레이어 제거, 본문 표식 없는 페이지의 정리, 플레이어 문구의 인용 거부를 테스트했습니다. 백엔드 `158 passed, 1 deselected`이며 기존 Starlette/AnyIO deprecation warning 1건이 남습니다. `test_settings_load_file_without_exposing_key`는 `tmp_path` 임시 디렉터리 접근이 Windows 환경에서 거부되어 제외했습니다. `uv lock --check`, `git diff --check` 통과.
- **검증 경계:** 검색·원문 HTTP는 fixture 기반 오프라인 검증입니다. 실제 Google 자연 검색 순위, 실제 페이지 크롤링, 유튜브 자막/트랜스크립트 추출은 이번 단계에서 검증하거나 추가하지 않았습니다. 현재 공급자 후보 순서를 Google의 실제 순위라고 해석하면 안 됩니다. 실행 중인 사용자 서버는 건드리지 않았습니다.
- **다음 단계:** `AGI는 2030년 안에 오나?` 같은 전망 질문에 대해 지지·반대·불확실한 전망을 원문 인용과 함께 균형 있게 종합하고, 이미지처럼 답변 본문과 인라인 출처가 연결되도록 구현합니다.

## 2026-09-23 모델 전환 및 fallback 우선순위 변경

이 절이 현재 서비스 모델과 provider 우선순위의 기준입니다. 이전 날짜에 기록한 초기 fallback 구현은 구현 당시 상태의 이력입니다.

- **우선순위:** `GEMINI_API_KEY`가 있으면 `gemini-3.8-flash` (`thinking_level: high`) → 같은 키의 `gemini-3.7-flash` (`thinking_level: high`) → `OPENAI_API_KEY`의 `gpt-6-luna` (`reasoning.effort: max`) 순으로 시도합니다. 설정되지 않은 키의 provider는 건너뜁니다.
- **적용 범위:** 주장 추출·웹 검색·근거 검증 각 단계가 동일한 순서를 따릅니다. 결과 상단 채팅 모델 표시는 `/api/fact-check` 상태 응답에 설정된 첫 provider를 기준으로 갱신되며, 실제 최종 provider는 검증 결과의 `model` 필드에 표시됩니다.
- **모델 ID 확인:** OpenAI 공식 문서에서 GPT-6 Luna의 API ID `gpt-6-luna`, `reasoning.effort: max`, Responses API·Structured Outputs·Web search 지원을 확인했습니다. Gemini 공식 문서에서 `gemini-3.8-flash`, `gemini-3.7-flash` 모델 ID와 Interactions API 지원을 확인했습니다.
- **키 상태:** 현재 `backend/.env` 또는 프로세스 설정에서 OpenAI와 Gemini 키가 모두 설정되어 있음을 비밀값 없이 확인했습니다. 실제 provider 호출은 이번 모델 전환 검증에서 수행하지 않았으므로 계정별 모델 접근·실응답 성공은 별도 live gate입니다.
- **회귀 검증:** backend `155 passed` (기존 Starlette/AnyIO deprecation warning 1건), frontend Node `25 passed`, `tsc --noEmit --incremental false`, `uv lock --check`, `npm run build`, `git diff --check`를 통과했습니다. 우선순위 체인, 1→2 및 1→2→3 재시도, 상태 API의 선택 모델, GPT-6 결과 계약을 검증했습니다.
- **실행 반영:** `127.0.0.1:8010`은 변경 전 코드로 실행 중일 수 있습니다. 새 모델 순서를 UI에 적용하려면 backend를 재시작해야 합니다. 기존 frontend·backend 프로세스는 작업 중 종료하지 않았습니다.
- **공식 문서:** https://developers.openai.com/api/docs/models/gpt-6-luna · https://ai.google.dev/gemini-api/docs/interactions-overview

## 2026-09-23 검색 개선 2단계 체크포인트

- **반영:** 출처 유형별 재정렬을 제거하고 공급자 후보 반환 순서를 보존합니다. 같은 사이트 그룹은 최대 2개, 전체 최대 6개로 제한하며 후보 부족 시 제한을 풀어 채우지 않습니다. 이는 독립적인 발행인 수나 신뢰도를 보장하는 규칙이 아닙니다.
- **중복:** 기존 URL 정규화에 더해 `utm_*`, `fbclid`, `gclid`, `msclkid` 차이만 있는 URL을 동일 후보로 취급합니다. 문서 ID·동영상 ID 등 나머지 쿼리는 보존합니다. 중복 제거용 식별자만 정리하고 실제 접근 링크와 위치는 최초 후보를 유지하며, 도메인뿐인 제목은 뒤의 citation 제목으로 보완합니다.
- **검증:** 순서 변경·사이트 제한 완화·추적 URL 중복 3개 회귀의 실패 확인 후 구현했습니다. 전체 백엔드 `154 passed`, 기존 Starlette/AnyIO deprecation warning 1건, `uv lock --check` 통과. 위험 URL 차단·최대 6개 제한을 유지하며 원문 접근 실패 뒤에도 다음 후보를 순차 처리하는 것을 검증했습니다.
- **Google 순위 한계:** 현재 OpenAI는 검색 도구의 후보 목록, Gemini는 답변의 URL citation 목록을 사용합니다. Google 공식 문서 https://ai.google.dev/gemini-api/docs/google-search 에서 Interactions 검색 응답 구조를 확인했으나 이 목록을 Google 브라우저의 자연 검색 순위로 간주할 근거는 확인하지 못했습니다. 실제 Google 상단 결과 순위 연동은 아직 미구현이며 순위 제공 검색 연동을 별도로 결정해야 합니다. 이번 단계에서는 공급자 변경이나 신규 서비스 가입·키 설정을 하지 않았습니다.
- **실행 범위:** 오프라인 HTTP fixture 및 실제 로컬 그래프로 검증한 기존 회귀입니다. 이번 단계에서 실제 유료 검색, 브라우저 및 프론트 빌드는 실행하지 않았고 임시 서버를 시작하지 않았습니다. 기존 실행 중 백엔드는 재시작해야 수정이 적용될 수 있습니다. 기존 `next-env.d.ts` 변경은 보존했습니다.
- **다음 3단계:** 본문 추출과 메뉴·플레이어 문구 인용 차단을 구현합니다. 이후 대화 맥락 및 전망 종합·인라인 출처 UI를 반영합니다. 미래 전망의 현재 `not_checkable` 처리와 최종 답변은 아직 그대로입니다.

## 2026-09-23 검색 개선 1단계 체크포인트

- **요청 범위:** 사용량 중단에 대비하여 키워드 추출 및 예측 질문 검색만 분리하여 반영했습니다. 아래 과거 기록보다 이 체크포인트를 우선합니다.
- **구현:** 기존 주장 추출 LLM 호출에서 `searchQuery`를 함께 생성합니다. 개체·날짜·숫자·부정 표현을 보존하도록 지시하며, `AGI는 2030년 안에 오나?`의 검색어 예시는 `AGI 2030년`입니다. 추가 LLM 호출은 없습니다. 예측 질문을 빈 주장으로 버리지 않도록 추출 지침을 보완했습니다.
- **전달:** 검색어는 공개 주장에 섞지 않고 내부 `searchQueries` 상태로 전달합니다. 검색 단계는 이를 `primaryQueries`와 주장별 `searchQuery`로 보내 먼저 검색하도록 요청합니다. 공급자가 실제로 사용한 검색어의 일치 여부까지 강제하거나 검증하는 구조는 아닙니다. 검색어 미제공 시 보수적인 문자열 정리로 대체하며 원래 주장도 함께 전달합니다.
- **예측 검색:** `prediction`도 검색 대상으로 포함합니다. `opinion`은 기존처럼 검색하지 않습니다. 현재 미래 결과의 판정은 여전히 `not_checkable`이며 전망 출처를 종합하는 답변 개선은 후속 단계입니다.
- **검증:** 기존 검색 회귀 2건과 새 추출 회귀의 실패를 확인한 뒤 구현했습니다. 전체 백엔드 `150 passed` 및 `uv lock --check` 통과. 기존 Starlette/AnyIO deprecation warning 1건이 남습니다. 그래프 내 키워드 전달, 공개 계약 비노출, 한글·영문 부정 표현 및 숫자 보존을 확인했습니다.
- **검증 한계:** 공급자 응답은 명시적 오프라인 fixture입니다. 이번 단계에서 실제 유료 LLM·검색 호출, 브라우저·프론트 빌드, 실행 중 서버 재시작은 수행하지 않았고 임시 서버도 시작하지 않았습니다. 실행 중 백엔드 반영에는 재시작이 필요할 수 있습니다.
- **검색 공급자:** 기존 OpenAI/Gemini 연결을 유지합니다. OpenAI 웹 검색 결과를 Google 실제 검색 순위라고 표시하거나 보장하지 않습니다.
- **다음 2단계:** 실제 검색 공급자와 순위 제공 가능성을 확인하고 검색 순서 보존·출처 중복 처리를 개선합니다. 현재 `_select_diverse_sources`의 재정렬과 제한 완화는 아직 남아 있습니다. 이후 본문·인용 품질, 대화 맥락, 전망 요약·인라인 출처 UI 순으로 진행합니다.
- **작업 트리:** 시작 전부터 있던 `next-env.d.ts` 변경은 수정하거나 커밋에 포함하지 않습니다.

## 2026-09-22 다중 LLM fallback 구현 완료

이 절은 2026-09-22 fallback 최초 구현 시점의 기록입니다. 모델 ID와 현재 우선순위는 2026-09-23 업데이트를 기준으로 합니다.

- **fallback 순서:** `OPENAI_API_KEY`가 있으면 `gpt-5.6-luna` + `reasoning: max`를 1순위로 사용합니다. 호출 실패 시 `GEMINI_API_KEY`의 `gemini-3.8-flash` + `thinking_level: high`, 다시 실패 시 같은 키의 `gemini-3.7-flash` + `thinking_level: high`를 사용합니다. 앞 provider의 키가 없으면 설정된 다음 provider부터 시작합니다.
- **적용 단계:** 주장 추출, 웹 검색, 근거 검증 각각에서 같은 순서로 fallback을 시도합니다. 원문 읽기 단계는 LLM 호출이 아니므로 fallback 대상이 아닙니다. 어느 provider가 성공했는지는 최종 결과의 `model`과 `reasoning`에 반영하며, API 키는 graph state·스트림·응답에 넣지 않습니다.
- **provider별 연결:** OpenAI는 기존 Responses API 구조를 유지합니다. Gemini는 Interactions API를 사용하고, 구조화 출력 schema와 `google_search` 도구를 provider adapter에서 변환합니다. 검색 결과는 Gemini의 URL citation을 수집한 뒤 기존 출처 URL 경계·원문 읽기·인용 grounding을 통과한 것만 결과에 사용합니다.
- **설정:** 저장소 루트 `.env.example`를 참고하여 실제 값은 `backend/.env`에만 설정합니다. `OPENAI_API_KEY` 또는 `GEMINI_API_KEY` 중 하나만 있어도 workflow를 구성할 수 있으며, 두 키를 모두 넣으면 위 순서대로 동작합니다. 키 값은 로그·문서·커밋에 기록하지 않습니다.
- **회귀 검증:** backend `114 passed`(기존 Starlette/AnyIO deprecation warning 1건), frontend Node `22 passed`, `tsc --noEmit --incremental false`, `uv lock --check`, `npm run build`, `git diff --check`를 통과했습니다. 추가 테스트는 provider 순서·1→2→3 retry, runtime stage retry, Gemini 구조화 출력, Gemini Google Search citation, Gemini-only status, 최종 provider metadata를 검증합니다.
- **현재 환경의 live gate:** 현재 `backend/.env`/프로세스에는 OpenAI provider만 설정되어 있어 `gpt-5.6-luna` 실제 호출은 기존 smoke로 확인했고, Gemini 실제 호출은 `GEMINI_API_KEY`가 없어 수행하지 않았습니다. Gemini wire·schema·검색 citation과 fallback retry는 비밀키 없는 mock 회귀로 확인했습니다. Gemini live fallback까지 확인하려면 `backend/.env`에 키를 추가한 뒤 실패를 유도하지 않는 별도 비용 확인이 필요합니다.
- **실행 반영 주의:** 현재 형님이 띄워 둔 `127.0.0.1:8010` backend는 이 변경 전 프로세스일 수 있으므로 새 fallback을 실제 UI에 적용하려면 backend 실행 터미널을 재시작해야 합니다. 사용 중인 `127.0.0.1:3000`과 `127.0.0.1:8010`은 작업 중 종료하지 않았습니다.

## 2026-09-22 LLM 검증 실패 원인 확정 및 수정

이 절은 현재 저장소에서 실제 OpenAI provider 호출을 포함하여 재현·수정·재검증한 최신 결과입니다. 아래 과거 기록의 오래된 실행 결과보다 이 절을 우선합니다.

- **원인 1 — 추출 단계의 포커스 처리:** 추출 프롬프트가 사용자의 확인 요청을 사실상 필터로 처리하여, 원문에 실제로 존재하는 확인 가능 주장까지 버릴 수 있었습니다. 원문에 사실 주장이 있고 포커스가 해당 문장의 세부사항을 요구하더라도, 주장을 먼저 추출하고 이후 단계에서 근거 부족을 판정하도록 수정했습니다. 모델이 원문에 없는 인용문을 섞어도 유효한 다른 주장을 보존하며, 원문 범위를 벗어난 후보는 조용히 제외합니다.
- **원인 2 — 검색 응답 상태 처리:** Responses API의 검색 결과에는 완료된 `web_search_call`과 잔여 `searching` 항목이 함께 포함될 수 있습니다. 기존 어댑터는 하나라도 완료되지 않은 항목이 있으면 전체 검색을 실패로 처리했습니다. 완료된 검색 호출만 사용하도록 수정했습니다.
- **원인 3 — 검증 단계의 컨텍스트 및 출력 예산:** 여러 출처의 원문을 최대 길이로 한꺼번에 모델에 전달하면서 검증 응답이 `status=incomplete` 상태로 종료되고 최종 구조화된 판정을 내놓지 못할 수 있었습니다. 모델에 보내는 출처별 텍스트를 6,000자로 제한하고 검증 출력 예산을 12,000토큰으로 늘렸습니다. 서버 내부의 전체 원문은 근거 대조용으로 보존합니다.
- **실제 LLM 재검증:** 동일한 한국어 입력(“구글, '제미나이 노트북'에 맞춤형 학습 기능 추가…'듣고 말하며 공부한다'”)으로 수정된 backend에 실제 provider 호출을 수행했습니다. HTTP 200, `extracting → searching → reading → verifying` 네 단계, `demo=false`, 주장 2개, 출처 6개, 근거 5개를 반환했고 최종 판정은 `대체로 확인됨`과 `근거 부족`으로 정상 생성되었습니다. 이는 데모 fixture가 아닌 실제 provider smoke 결과입니다.
- **회귀 검증:** backend `105 passed`(기존 Starlette/AnyIO deprecation warning 1건), frontend Node `21 passed`, `uv lock --check`, `npm run build`, TypeScript 검사를 통과했습니다. 추가한 회귀 테스트는 포커스 우선 추출, 부분적으로 잘못된 모델 인용 보존, 비종료 검색 항목 처리, 검증 입력 길이 제한을 다룹니다.
- **실행 반영 주의:** 현재 형님이 띄워 둔 `127.0.0.1:8010` backend 프로세스는 수정 전 코드로 시작된 기존 프로세스이므로, 새 수정본을 실제 UI에 적용하려면 해당 backend 실행 터미널을 재시작해야 합니다. 기존 frontend `127.0.0.1:3000`과 사용 중인 서버는 작업 중 종료하지 않았습니다.

## 2026-09-22 현재 환경 검증 업데이트

이 절은 현재 `C:/Users/Playdata/Desktop/프로젝트/TRUE-OR-NOT` 환경에서 수행한 최신 실행 결과입니다. 아래 과거 기록의 오래된 `C:/Users/rlagn/.../my-app` 경로와 당시 미완료 표시는 현재 상태로 해석하지 않습니다.

- **실제 LLM 호출 성공:** 현재 저장소의 FastAPI를 `127.0.0.1:8011`에서 실행하고 비민감한 문장으로 `POST /api/fact-check/stream`을 호출했습니다. HTTP 200과 `extracting → searching → reading → verifying` 네 단계 이벤트, `demo: false` 최종 결과, `gpt-5.6-luna` / `reasoning: max`를 확인했습니다. 결과 판정은 호출 실패가 아니라 수집 원문 조건 불일치에 따른 `insufficient_evidence`였습니다.
- **실제 UI 경로 성공:** `127.0.0.1:3000`에서 원문 입력·동의·검증 시작을 수행했고, 진행 단계와 `검증이 완료되었습니다`, 실제 검증 후보 1개·수집 출처 6개를 확인했습니다.
- **오프라인 회귀:** backend `101 passed`(기존 Starlette/AnyIO deprecation warning 1건), frontend Node `21 passed`, `tsc --noEmit --incremental false`, `npm run build`를 통과했습니다.
- **브라우저 7단계 회귀:** 테스트 전용 FastAPI와 기본 Turbopack scratch 실행으로 데스크톱 1440×1000·모바일 390×844에서 POST `[200, 200]`, overflow 0, 중복 ID 0, 실제 결과 선택·내보내기, 독립 데모의 POST 0건, pageerror 0을 확인했습니다. 소유한 임시 서버와 포트는 runner가 정리했습니다.
- **검증 스크립트 정합성:** Next 개발 서버의 HMR 연결 때문에 `networkidle`을 readiness 신호로 사용하지 않도록 `domcontentloaded`와 실제 hydrated 상태 selector를 사용하도록 고쳤습니다. Liquid Glass 제거 이후 남아 있던 `.factlens-glass`·`.glass-surface__content` 기대를 현재 `.panel-host`·`.detail-content` 구조로 갱신했습니다. 운영 앱 코드는 변경하지 않았습니다.
- **환경 경계:** 실제 키는 `backend/.env`에만 존재하며 값은 로그·문서에 기록하지 않았습니다. 실제 검증 실행은 비용이 발생할 수 있으므로 비민감한 한 문장으로만 수행했습니다.

## 최종 실행 인계 — 6단계 핵심 및 7단계 고정 범위 완료

### 최종 7단계 회귀 결과 (이 절이 아래 과거 체크포인트보다 우선)

- **완료:** Python 전체 101 passed(기존 Starlette/AnyIO deprecation 1건), Node 전체 5개 파일 21 passed, `uv lock --check`, `npm run typecheck`, `npm run build` 통과. 빌드는 Next.js 16.3.5 기본 Turbopack production build입니다.
- **브라우저 통과:** 설치된 Chrome headless, 데스크톱 1440×1000 / 모바일 390×844 각각 실제 Next → test-only FastAPI 스트림 POST 200. 첫 주장 인용·HTTPS 출처·불확실성, 둘째 주장 선택 시 이전 인용 제거·근거 없음, JSON 결과 export의 demo=false 및 claim/source/evidence 참조를 확인했습니다. 별도 새 문서에서 데모 3개 주장·근거·근거 없는 주장·demo=true JSON export를 확인했고 데모 POST 및 backend 실행 증가가 없었습니다. 측정 복제본 대신 `.liquid-panel-live:visible` 사용. 가로 overflow 및 pageerror 0개입니다.
- **기본 개발 번들러 통과:** `next dev --hostname 127.0.0.1 --port <자동 빈 포트>`에 webpack 옵션 없이 실행하고 로그의 `Next.js 16.3.5 (Turbopack)` 및 실제 페이지/API/browser smoke를 확인했습니다. 기존 3000 서버/lock을 건드리지 않도록 scratch 복제본을 사용했습니다. node_modules junction을 해결하기 위해 **scratch의 next.config.ts만** 설치된 Next 문서에 따라 두 경로의 공통 부모를 `turbopack.root`로 지정했습니다. 원본 config 변경 없음. 원본 루트의 기존 3000 프로세스 자체를 재검증한 것은 아닙니다.
- **증거:** `C:/Users/rlagn/AppData/Local/hermes/cache/scratch/factlens-stage7-p80au0mu/`의 `browser-evidence.json`, `cleanup.json`, `next.log`, `backend.log`, `browser.stdout`, `browser.stderr`, `desktop-result.png`, `desktop-second-claim.png`, `desktop-demo.png`, `mobile-result.png`, `mobile-second-claim.png`, `mobile-demo.png`, 양 viewport의 `*-result.json`/`*-demo.json`. 모바일 결과/데스크톱 데모 스크린샷 직접 확인. 소유 포트 14181/14182 종료 및 browser Node exit 0 확인. 서버 exit 1은 runner의 Windows taskkill 종료 결과이며 실행 실패가 아닙니다.
- **변경 범위:** 운영 코드·UI·의존성 수정 없음. 시작 시 이미 있던 `scripts/probe-stage7.py`, `scripts/probe-stage7.mjs`를 실행했습니다. `HANDOFF.md`에 최종 결과를 추가했습니다. 시작 시 있던 `scripts/__pycache__/`와 다른 변경은 보존했습니다. 커밋/푸시는 부모 작업자 담당입니다.

### 정확한 로컬 실행 / 회귀 명령 (Windows Git Bash)

기존 설치 환경에서 두 터미널로 실행합니다. 처음 설치할 때만 루트 `npm ci`, backend `uv sync --locked`를 수행합니다. 아래 포트가 사용 중이면 소유자를 확인하거나 다른 빈 포트와 backend URL을 함께 선택하고 알 수 없는 서버를 종료하지 않습니다.

```bash
# 터미널 1: 실제 backend (사용자 backend/.env, 실제 검증 제출 시 비용 발생 가능)
cd C:/Users/Playdata/Desktop/프로젝트/TRUE-OR-NOT/backend
uv run uvicorn main:app --host 127.0.0.1 --port 8010

# 터미널 2: 기본 Turbopack frontend
cd C:/Users/Playdata/Desktop/프로젝트/TRUE-OR-NOT
FACTLENS_BACKEND_URL=http://127.0.0.1:8010 npm run dev -- --port 3000
# 브라우저: http://127.0.0.1:3000
```

유료 호출 없는 이번 회귀 재현:

```bash
cd C:/Users/Playdata/Desktop/프로젝트/TRUE-OR-NOT
(cd backend && uv run pytest -q && uv lock --check)
node --experimental-strip-types --test app/lib/server/*.test.mjs app/components/*.test.mjs
npm run typecheck
npm run build
PLAYWRIGHT_MODULE='C:/Users/rlagn/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/playwright/index.mjs' backend/.venv/Scripts/python.exe scripts/probe-stage7.py
git diff --check
```

브라우저 probe는 설치된 Chrome 및 위 Playwright 경로가 필요합니다(다른 PC는 설치 경로로 교체). test-only backend를 자동 기동·복구 모드 설정하고 자식 API_KEY/TOKEN/SECRET 환경변수를 제거하며 frontend에 .env를 복사하지 않습니다. 종료 시 소유 browser/server만 정리합니다.

### 알려진 한계 / 마감 상태

- 6단계 핵심 및 **7단계의 합의된 고정 범위 완료**. 아래 역사 기록의 미완료·다음 6-C·7단계 확대 제안은 현재 TODO가 아닙니다. 새 기능/리디자인/추가 provider 호출 없이 여기서 마감합니다.
- 최종 브라우저 회귀는 명시적 TEST ONLY fixture이므로 실제 사실 검증 품질의 증거가 아닙니다. 별도로 현재 backend와 UI에서 비민감한 실제 provider smoke를 수행해 OpenAI 호출·네 단계 스트림·최종 결과 반환을 확인했으며, 해당 결과의 판정 품질 전체를 보증하는 것은 아닙니다.
- `next.log`에 React Fragment의 `id` prop 경고와 reduced-motion 안내가 있습니다. 화면의 Next 개발 issue badge도 남습니다. pageerror 0은 console 경고 0이라는 뜻이 아닙니다. 기능 smoke를 차단하지 않아 이 고정 범위에서 디자인/의존성 수정으로 확대하지 않았습니다.
- 브라우저 smoke는 reduced-motion/headless Chrome이며 모든 브라우저·애니메이션·접근성 감사가 아닙니다. 실제 provider 내부 취소/과금 중단, 모든 실행 중 서버 강제 종료 조건, 공개 배포·인증·영속 저장은 보장하지 않습니다.
- production build 성공은 production 유료 요청 허용을 의미하지 않습니다. `next start`의 POST 차단은 유지된 의도적 정책입니다.

## 이전 단계 마감 기준 및 검증 이력

### 단계 마감 기준 확정

- 6단계 완료 범위: Next.js–FastAPI 스트림 연결, 실제 요청 결과/내보내기, 상세 근거 표시, 오류 안내, 브라우저 취소/문서 이탈의 Python 작업 정리, 처리 오류 복구와 실제 서버 재시작 후 같은 화면 재시도입니다. 각 항목의 실제/테스트 전용 검증 차이는 아래 기록을 따릅니다.
- 관련 수정 및 probe는 `12d4681`, `94a34d9`, `48e64b7`, `ba33820`에 반영되었습니다. 이전 절의 미커밋/6-C 미완료 표현은 당시 기록이며 이 마감 기준이 우선합니다.
- 7단계 고정 범위: 전체 Python/Node 테스트·타입 검사·빌드, 모바일/데스크톱 결과와 데모 회귀, 기본 Turbopack 개발 경로 점검, 최종 실행 절차·알려진 한계 인계. 새로운 기능 추가나 검증 항목을 무한히 늘리지 않습니다.
- 이미 성공한 유료 실제 전체 요청은 기존 증거를 사용하고 불필요하게 재호출하지 않습니다. 실제 provider 내부 취소/과금 중단, 실행 중 서버 강제 종료의 모든 조건, 공용 배포는 보장하지 않습니다. 미검증은 명시하며 완료 범위를 과장하지 않습니다.
- 다음 작업은 7단계 최종 회귀입니다. 6-C 세부 작업을 더 추가하지 않습니다.


### 최신 체크포인트: 6-C 한정 — 실제 backend 프로세스 종료·재시작 / 같은 페이지 재시도

- 시작 Git 상태는 깨끗했습니다. **운영 코드 결함 없이 브라우저 probe 통과**, 운영 코드·UI·의존성·fixture 변경 없음. 커밋/푸시는 부모 검토 대상으로 남겼습니다.
- 수정 `scripts/probe-recovery.py`: `--network-restart` 옵션, 소유 FastAPI 프로세스 종료/동일 포트 재기동, scratch 파일 IPC, PID/종료 코드/포트 정리 증거 저장. 추가 `scripts/probe-network-restart.mjs`: 실제 Chrome → 기존 Next proxy → 명시적 test-only FastAPI fixture 경로. 기존 `backend/tests/recovery_probe_app.py`를 재사용하며 production mock이나 provider 호출을 추가하지 않았습니다.
- **실제 장애:** UI 로딩·입력·동의 후 FastAPI PID 6688을 종료하고 10260 포트 연결 불가를 먼저 확인했습니다. 백엔드가 없는 동안 UI 시작 버튼으로 연속 두 요청을 보내 **503 BACKEND_UNAVAILABLE 두 번**을 확인했습니다. “검증 실패: 검증 백엔드에 연결할 수 없습니다. 다시 시도하실 수 있습니다.”, 주장 카드 0개, 내보내기 비활성, 시작 버튼 재활성을 assertion 및 스크린샷으로 확인했습니다. 어댑터 오류 모드 전환을 네트워크 장애로 계산하지 않았습니다.
- **복구:** 같은 포트에 새 FastAPI PID 3192를 시작하고 명시적 테스트 fixture 성공 모드를 설정했습니다. 새 프로세스 attempts=[]를 확인한 뒤 **기존 문서에서** 시작 버튼으로 재시도 성공, 다시 한 번 성공했습니다. POST 상태 `[503,503,200,200]`, 재시작 backend attempts=`[success,success]`. 문서별 UUID·입력값·동의를 유지하여 reload/새 페이지 없이 복구했음을 검증했습니다. 연속 실패·성공 요청이 429 BUSY에 걸리지 않아 proxy concurrency가 고착되지 않았음을 확인했습니다. backend 내부 active/finally 계측이나 실행 중 stream 강제 단절을 새로 검증한 것은 아닙니다.
- 근거: `C:/Users/rlagn/AppData/Local/hermes/cache/scratch/factlens-recovery-i4m8ipzz/`의 `browser-evidence.json`, `network-error.png`, `restart-success.png`, `stop.done`, `restart.done`, `cleanup.json`, `backend.log`, `backend-restarted.log`, `next.log`. 두 스크린샷 직접 확인 완료. 소유 서버 포트 10260/10261 연결 불가, 브라우저 close 및 Node 정상 종료 확인. 기존 3000 서버는 건드리지 않았습니다.
- 기존 어댑터 복구/상세 근거 probe도 재실행 통과(`[200,200]`), 근거 `factlens-recovery-vd7iilsl/`. 소유 포트 1760/1761 종료 확인. 프론트엔드 **20 tests passed**, `npm run typecheck`, Python **101 passed**(기존 AnyIO 경고 1건), `uv lock --check`, `git diff --check` 통과.
- 재현: 루트에서 `PLAYWRIGHT_MODULE='C:/Users/rlagn/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/playwright/index.mjs' backend/.venv/Scripts/python.exe scripts/probe-recovery.py --network-restart`. 옵션 없이 기존 adapter-error probe도 유지합니다. .env를 복사하지 않고 자식 환경의 키/토큰/secret을 제거합니다.
- **범위/한계:** 공유 node_modules junction이 있는 scratch Next의 **webpack 개발 경로**만 검증했습니다. 이번 빌드는 재실행하지 않았으며 이전 부모 검증의 Turbopack 프로덕션 빌드와 구분합니다. 기본 Turbopack 개발 경로, 실행 중 backend 강제 종료, 실제 provider 재호출, 모바일 및 전체 7단계 회귀는 남습니다. 6-C 전체 완료로 표시하지 않습니다. 기존 셰이더 조정 패널/화면 디자인도 보존했습니다.

### 이전 체크포인트: 6-C 한정 — 장애 복구 재시도 / 실제 결과 상세 근거

- 시작 시 `git status --short`는 깨끗했습니다. 쿼터 중단의 부분 수정은 없었습니다. 커밋/푸시하지 않았습니다.
- **실제 결함:** dashboard의 근거 패널이 `selected && snapshot.demo`에서만 렌더링되어 비데모 결과의 인용·출처 링크·불확실성이 전혀 보이지 않았습니다. 브라우저 RED에서 실패→복구→재시도 완료까지 성공한 뒤 인용 표시 assertion만 timeout한 것을 확인하고 비데모 전용 패널을 추가했습니다. 기존 합성 예시·shader·CSS는 변경하지 않았습니다.
- 추가: `backend/tests/recovery_probe_app.py`, `scripts/probe-recovery.py`, `scripts/probe-recovery.mjs`. 테스트 엔트리포인트에서만 dependency override와 결정적 오류/성공 LangGraph를 사용합니다. 기본 runtime fallback이 아니며 provider workflow는 명시적으로 금지합니다. 데이터·모델·출처·경고에 TEST ONLY를 표시하고 실제 네트워크 출처 검증 결과로 취급하지 않습니다. 스크래치 Next 복제본에 .env를 복사하지 않으며 자식 환경의 키/토큰/secret을 제거합니다.
- **브라우저 GREEN:** 실제 Chrome → Next webpack proxy → FastAPI stream. 첫 실행은 HTTP 200 스트림 내부 AGENT_FAILED로 안전한 실패 문구, export 비활성, 시작 버튼 재활성, 내부 진단 미노출을 확인했습니다. 테스트 backend 복구 후 같은 화면에서 시작 버튼 재클릭 → 완료. backend attempts는 `[failure, success]`, POST 상태는 `[200, 200]`입니다. 프로세스 중단/재기동이 아니라 backend 어댑터 실패/복구입니다.
- 첫 주장 선택 후 인용·안전한 HTTPS 출처 href·주장 불확실성/경고를 확인했습니다. 둘째 주장 선택 후 전 주장 인용이 사라지고 근거 없음·둘째 불확실성이 나타납니다. UI에는 요약, 근거 관계, 발행일 미확인, 확인 내용, 주장별 주의사항 및 전체 검증 한계도 표시합니다. 원문 링크 외부 방문은 하지 않았습니다.
- 근거: `C:/Users/rlagn/AppData/Local/hermes/cache/scratch/factlens-recovery-1sjois50/`의 `browser-evidence.json`, `failure.png`, `details.png`, `backend.log`, `next.log`. details 스크린샷 직접 확인 완료. RED 근거는 `factlens-recovery-8zib4tyy/`. 중간 2회 실패는 LiquidGlass 숨김 측정 복제본/잘못된 live 클래스 선택자 문제였고 앱 실패로 계산하지 않았습니다. 최종 probe는 실제 `.liquid-panel-live`만 검사합니다.
- 검증: 프론트엔드 Node 테스트 **20 passed**, `npm run typecheck`, Python **101 passed** (기존 AnyIO 경고 1건), `git diff --check` 통과. 브라우저 회귀 probe 최종 통과. 소유 서버 3745/3746 및 브라우저 종료, 포트 연결 불가 확인. 기존 3000 서버, `next-env.d.ts`, `.playwright-cli`는 건드리지 않았습니다.
- 재현: 루트에서 `PLAYWRIGHT_MODULE='C:/Users/rlagn/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/playwright/index.mjs' backend/.venv/Scripts/python.exe scripts/probe-recovery.py`.
- **한계/남음:** webpack 개발 경로만 검증했습니다. 기본 Turbopack, 실제 provider 재호출, 네트워크 연결 중단 후 backend 프로세스 재기동, 모바일/전체 데모 회귀, 최종 빌드·7단계는 이번 범위 밖입니다. 스크린샷에는 기존 개발 UI/셰이더 조정 패널이 보이며 재디자인하지 않았습니다. 6-C 전체 완료로 표시하지 않습니다.

### 최신 검증 체크포인트: 6-C 한정 — 브라우저 취소/화면 이탈 → Python 정리 확인

- **범위:** 실제 브라우저 → 변경 없는 Next proxy → 기존 FastAPI StreamingResponse → 실제 컴파일된 LangGraph의 취소 전파만 검증했습니다. 운영 코드 결함은 발견하지 않았고 운영 코드 수정·커밋·푸시는 하지 않았습니다. 6-C 전체 완료가 아닙니다.
- 추가: `backend/tests/cancellation_probe_app.py`, `scripts/probe-cancellation.py`, `scripts/probe-cancellation.mjs`. 테스트 전용 프로세스에서 `main.app.dependency_overrides[main.get_workflow]`로 그래프를 주입합니다. extracting 어댑터는 Event에서 무기한 대기하며 CancelledError/ finally 및 그래프 iterator finally를 계측합니다. 판정/결과를 만들지 않고 유료 provider를 호출하지 않습니다. 설정 sentinel과 계측 GET도 이 테스트 엔트리포인트에만 존재합니다. 새 기본 앱 프로세스에서 override 없음·`/__test__` route 없음도 확인했습니다.
- 실제 설치 Next.js 16.3.5 **webpack 개발 서버**, Google Chrome headless, Uvicorn을 별도 loopback 포트와 scratch 프론트엔드 복제본으로 실행했습니다. `.env`는 복사하지 않았고 provider 환경변수를 자식에서 제거했습니다. 기존 3000 서버와 기존 작업 파일은 건드리지 않았습니다. 공유 node_modules junction을 사용하므로 **기본 Turbopack 검증으로 간주하지 않습니다.**
- **독립 실행 2회 통과:** 브라우저 POST 상태 `[200, 429, 200, 200]`. 첫 요청이 대기 중일 때 추가 요청은 `429 BUSY`; UI 취소 직후 서버 상태 폴링/인위적 대기 없이 UI 재시작하여 두 번째 200. 재시작 체크포인트는 graph started=2/finalized=1, adapter cancelled=1/finalized=1, active=1. `about:blank` 실제 문서 이동 뒤 started=2/finalized=2, adapter cancelled=2/finalized=2, active=0. 복귀 후 세 번째 요청도 200, 마지막 UI 취소 뒤 started=finalized=adapter_started=adapter_finalized=adapter_cancelled=3, active=0, max_active=1. 모든 정리는 서버 종료 **전** 관찰했습니다.
- 원시 JSON 이벤트/monotonic 타임스탬프 및 양 서버 로그: `C:/Users/rlagn/AppData/Local/hermes/cache/scratch/factlens-cancellation-cbsf56_0/`와 `factlens-cancellation-fzew6hfm/`의 `browser-evidence.json`, `backend.log`, `next.log`. 두 번째 실행의 소유 포트 13883/13884는 종료 후 연결 불가를 확인했습니다. 각 실행의 브라우저도 닫았습니다.
- 재현(저장소 루트, 설치된 Chrome 및 Playwright 필요): `PLAYWRIGHT_MODULE='C:/Users/rlagn/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/playwright/index.mjs' backend/.venv/Scripts/python.exe scripts/probe-cancellation.py`. 다른 환경에서는 PLAYWRIGHT_MODULE을 설치된 Playwright index.mjs로 지정합니다. repo 의존성은 추가하지 않았습니다. probe는 실패 시 nonzero로 종료하고 계측 결과를 기록합니다.
- 검증: `cd backend && uv run pytest -q` **101 passed**, 기존 Starlette/AnyIO 경고 1건; `uv lock --check` 통과. 루트 `node --experimental-strip-types --test app/lib/server/*.test.mjs app/components/*.test.mjs` **20 passed**, `npm run typecheck`, `git diff --check` 통과. 빌드는 이번 한정 작업에서 재실행하지 않았습니다.
- 준비 단계 시행착오: Playwright 전용 headless-shell 미설치 → 설치된 Chrome 채널 사용; 잘못된 버튼 이름 `검증 시작` → 실제 `팩트 검증 시작`으로 수정. 이 실패들은 앱 취소 결함의 RED가 아니며 성공 검증으로 계산하지 않았습니다. 초기 TMPDIR가 시스템 Temp를 가리킨 것을 확인하고 runner의 Windows scratch 경로를 Hermes cache로 고정했습니다. Next 로그의 기존 Three.js deprecation/중복 import 경고는 범위 밖입니다.
- **남은 6-C:** 장애 복구 후 재시도, 상세 근거 표시, 기본 Turbopack/기존 3000 서버 경로 재검증 및 최종 빌드/7단계 전체 회귀. 이번 결과는 대기 중 extracting 노드와 문서 이탈에 한정되며 모든 provider 라이브러리 내부 취소·모든 단계·SPA unmount·즉시 재시도 경합 전체를 보장하지 않습니다. 기존 `next-env.d.ts` 및 `.playwright-cli` 미커밋 산출물을 보존했습니다.

### 최신 수정 체크포인트: 6-C 한정 — loopback 별칭 LOCAL_ONLY 403 수정

- 범위는 localhost/127.0.0.1 출처 불일치 하나입니다. 6-C 전체 완료가 아닙니다. 부모 작업자가 diff 검토 및 route 테스트 9개·타입 검사·Turbopack 프로덕션 빌드를 재실행하여 통과를 확인했습니다. 기본 개발 서버 재검증은 별도로 남습니다.
- 수정 전 기존 3000 서버에 동의 없는 JSON을 실제 POST하여 localhost는 **400 INVALID_REQUEST**, 127.0.0.1은 **403 LOCAL_ONLY**를 재현했습니다.
- 설치된 Next.js 16.3.5의 `next-server.js:1275-1281`은 서버 hostname으로 initURL을 구성합니다. 더 직접적인 원인은 `server/web/next-url.js:15-20`의 loopback → localhost 정규화이며, `spec-extension/request.js:43-50`이 정규화된 NextURL을 Request.url에 사용합니다. 실제 설치된 NextRequest 실행에서도 127.0.0.1/[::1] URL은 localhost가 되고 Host/Origin은 원래 값으로 남는 것을 확인했습니다.
- `app/api/fact-check/route.ts`: 엄격하게 허용한 로컬 Host authority와 Origin을 정확히 비교합니다. localhost↔127.0.0.1을 동일 출처로 취급하지 않으며 포트·scheme 불일치도 거부합니다. production 차단, URL loopback 제한, Forwarded 및 외부/복수 x-forwarded-for 차단, sec-fetch-site 제한을 유지했습니다. x-forwarded-host/proto/port 불일치도 거부합니다. 헤더는 인증이 아니므로 기존 `npm run dev`의 `--hostname 127.0.0.1` 바인딩을 그대로 유지합니다.
- `app/lib/server/route.test.mjs`: 회귀 테스트 RED에서 **403 !== 400**을 확인한 뒤 수정했습니다. 설치된 NextRequest를 사용하는 별칭 회귀, 교차 출처/전달 헤더, production 거부 테스트를 포함하여 route **9 passed**, 프론트엔드 5개 테스트 파일 전체 **20 passed**. `npm run typecheck`, `git diff --check` 통과(기존 Git CRLF 안내만 표시).
- 실제 HTTP 재검증: 기존 3000 서버는 수정 후 요청이 30초 timeout되어 종료하지 않았습니다. 동일 루트에서 두 번째 Next 실행은 dev lock으로 차단되었고, scratch 복제본의 node_modules junction은 Turbopack filesystem 경계로 차단되어 **동일 설치 Next + webpack**, `127.0.0.1:3106` 별도 서버로 검증했습니다. localhost/127.0.0.1 각각 동의 없음·깨진 JSON **4건 모두 400 INVALID_REQUEST**; 교차 별칭·포트·외부 Origin/Host·Forwarded·외부/복수 XFF·전달 host/proto/port·cross-site **11건 모두 403 LOCAL_ONLY**. 유료 provider/백엔드 호출 없이 입력 경계만 검증했습니다.
- 검증용 서버는 직접 시작한 프로세스만 종료했고 3106 연결 불가를 확인했습니다. 기존 3000 서버는 미종료이며 소유 세션에서 재시작/정리가 필요합니다. scratch 재현 스크립트: `C:/Users/rlagn/AppData/Local/hermes/cache/scratch/factlens-http-origin-check.py`.
- **남은 6-C:** 서버 측 취소 정리 계측, 화면 이탈, 장애 복구 후 재시도, 상세 근거 표시 검증. 이번 변경의 기본 Turbopack/기존 3000 서버 재검증 및 전체 빌드·7단계 회귀는 미실행입니다. 기존 `.playwright-cli` 산출물은 보존했습니다.


### 최신 브라우저 검증 체크포인트: 실제 결과·내보내기·장애 표시 확인

- localhost:3000에서 실제 FastAPI/모델 요청으로 “물은 수소와 산소로 이루어져 있다.”를 검증했습니다. 완료 화면에 후보 1개, 출처 6개, 판정 “대체로 확인됨”이 표시되었습니다. 이는 실행 결과이며 판정 품질 전체 보증은 아닙니다.
- 결과 내보내기를 클릭해 받은 JSON을 파싱했습니다. demo=false, claims=1, sources=6, evidence=1, evidence의 sourceId 참조 및 quoteVerified=true를 확인했습니다. 다운로드 결과는 로컬 `.playwright-cli/factlens-result.json`에 있으며 원문 자료와 인용을 별도로 재대조한 검증은 아닙니다.
- FastAPI 종료 후 재요청 시 “검증 실패: 검증 백엔드에 연결할 수 없습니다. 다시 시도하실 수 있습니다.”가 표시되어 장애를 사실 판정으로 오인하지 않았습니다.
- 이전 실행에서는 검색 진행→사용자 취소→재시작→완료 문구를 확인했습니다. 자동 대기의 `/검증 완료/`가 실제 “검증이 완료되었습니다”와 불일치해 발생한 260초 타임아웃은 테스트 선택자 오류였습니다. 이번에는 실제 문구로 대기해 성공했습니다.
- 남은 6-C: 서버 측 취소 정리 계측, 화면 이탈, 장애 복구 후 재시도, 상세 근거 표시 검증. 127.0.0.1:3000 접속은 LOCAL_ONLY 오류가 남고 localhost:3000은 동작하므로 별도 원인 확인이 필요합니다. 6-C 전체 완료로 표시하지 않습니다.
- 테스트 브라우저와 FastAPI는 종료했습니다. Next 개발 서버 종료 도구가 타임아웃되어 3000 서버 응답이 남아 있음을 확인했습니다. 추가 종료 확인이 필요합니다. 앱 코드는 이번에 변경하지 않았습니다.

### 최신 수정 체크포인트: 로컬 요청 403 회귀 수정

- Next.js가 주입하는 단일 loopback `x-forwarded-for` 값(127.0.0.1, ::1, ::ffff:127.0.0.1)을 허용했습니다. 외부 주소·복수 주소·빈 값은 계속 거부하며 Origin/Forwarded/production 제한을 유지합니다.
- 헤더는 인증 수단이 아니므로 기본 `npm run dev`를 `next dev --hostname 127.0.0.1`로 제한했습니다. 이미 실행 중인 서버에는 소급 적용되지 않으므로 재시작이 필요합니다. 공용 인터페이스 바인딩 또는 프록시 공개는 지원하지 않습니다.
- 회귀 테스트가 수정 전 403 != 200으로 실패하는 것을 확인한 후 수정했습니다. route 테스트 6개, 타입 검사, 프로덕션 빌드 통과. 브라우저 재검증 및 전체 6-C는 아직 미완료입니다.
- 기존 shader-settings-config.ts 변경은 다른 작업으로 간주하여 수정/커밋 대상에서 제외했습니다.

### 최신 실행 체크포인트: 6-C 브라우저 연결 검사 — 차단 원인 발견, 미완료

- FastAPI를 loopback 8010 포트에서 실행한 뒤 실제 Next.js 3000의 GET /api/fact-check가 configured=true를 반환하는 것을 확인했습니다.
- Playwright 실제 브라우저에서 원문 입력·외부 전송 동의·검증 시작을 수행했습니다. POST가 LOCAL_ONLY 403으로 거부되어 UI에 안전한 오류와 재시도 가능한 시작 버튼이 표시되었습니다. 모델 검증 결과는 얻지 못했습니다.
- 원인: route.ts가 x-forwarded-for 헤더의 존재만으로 요청을 차단하지만, 설치된 Next.js의 node_modules/next/dist/server/base-server.js는 이 헤더가 없는 직접 요청에도 socket.remoteAddress를 자동으로 채웁니다. 단위 테스트 Request에는 이 자동 주입이 없어 이전 16개 테스트가 놓쳤습니다.
- 다음 작업: Next.js가 주입한 단일 loopback 주소와 외부/복수 전달 주소를 구분하는 정책을 회귀 테스트로 먼저 정의하고 수정합니다. 헤더는 위조 가능하므로 인증 수단으로 취급하지 않으며 개발 서버의 loopback 바인딩도 확인해야 합니다. 보안 검사를 통째로 제거하지 않습니다.
- 이번에는 원인 확인까지만 수행했고 애플리케이션 코드는 변경하지 않았습니다. 진행/완료/취소 전파 검증은 여전히 미완료입니다. FastAPI 실행 세션: proc_f18af0d8a601. 기존 3000 서버는 다른 세션 소유일 수 있으므로 종료하지 않았습니다.

### 최신 체크포인트: 6-B Next.js → FastAPI 프록시

- `app/api/fact-check/route.ts`의 GET은 FastAPI 상태를 조회하고 공개 필드만 반환합니다. POST는 `/api/fact-check/stream`으로 전달합니다. 기존 TypeScript runAgent 호출을 제거하여 provider 중복 호출을 피합니다. 입력 검증 유틸리티만 기존 모듈에서 재사용합니다.
- `.env.example`을 서버 전용 `FACTLENS_BACKEND_URL=http://127.0.0.1:8010` 설정으로 갱신했습니다. 실제 키는 backend/.env에만 필요합니다. 프록시는 HTTP loopback IP 주소만 허용하고 리다이렉트를 거부합니다.
- 로컬 동일 출처·본문 제한·프로세스별 동시 1건 제한을 유지합니다. upstream NDJSON을 전달하며 취소를 upstream fetch/reader에 전파합니다. 프록시 245초 제한, 응답 총 2MB 제한, 진단 정보 없는 HTTP 오류 매핑을 적용했습니다.
- `app/lib/server/route.test.mjs`를 프록시 계약 테스트로 교체했습니다. 상태 필드 투영, 인증정보 미전달, 동시 요청 거부, reader/요청 취소 후 재시도, 외부 backend URL 거부, 입력/출처 차단을 검증했습니다.
- 중단 후 검증을 재실행했습니다. 프론트엔드 테스트 파일 5개에서 **16 tests passed**, `npm run typecheck` 통과, `npm run build` 통과. route 단독 테스트는 5개 통과입니다. 이 기록은 실제 FastAPI 프로세스와 브라우저를 연결한 검증을 의미하지 않습니다.
- **다음 6-C:** 실제 로컬 Next.js 개발 서버와 FastAPI를 실행하여 UI 상태/진행/결과/취소/오류/재시도를 확인합니다. 연결 해제 시 Python 작업 종료도 별도 검증해야 합니다. production POST 차단 정책은 유지되므로 `next start`에서 유료 검증이 차단되는 것을 버그로 오인하지 않습니다.
- 프록시 경로만 변경했으며 화면 디자인은 수정하지 않았습니다. 6단계 전체 완료와 7단계 실서비스 전체 검증 완료로 표시하지 않습니다.



### 최신 추가 체크포인트: 6-A 백엔드 진행 스트림

- `backend/streaming.py`, `backend/tests/test_streaming.py` 추가, `backend/main.py` 수정. 기존 JSON POST는 유지하고 `POST /api/fact-check/stream` NDJSON 엔드포인트를 추가했습니다.
- 네 단계 시작 이벤트 → 계약 검증된 result를 전달합니다. 내부 sourceTexts·provider 진단은 노출하지 않습니다. 단계가 누락되거나 순서가 잘못되면 AGENT_FAILED로 종료합니다.
- 240초 전체 스트림 제한, TIMEOUT/AGENT_FAILED 이벤트, 그래프 iterator 종료 및 asyncio 취소 전파를 구현했습니다. timeout은 스트림 실행 구간 기준이며 요청 본문 수신 시간 제한은 별도로 필요합니다.
- 이번 검증: 전체 Python **101 passed**, 기존 의존성 경고 1건. TestClient + 실제 LangGraph에 테스트 어댑터를 연결한 스트림 검증, 오류/timeout 및 태스크 취소 정리를 확인했습니다. 실제 브라우저 연결 해제→서버 취소는 아직 미검증입니다.
- **6단계 전체 완료가 아닙니다.** Next.js route는 아직 기존 TypeScript provider를 사용합니다. 기존 화면과 API 호출 경로는 전환하지 않았습니다. 실서비스 전체 요청·브라우저 테스트도 수행하지 않았습니다.
- 다음 **6-B**: Next.js GET 상태 및 POST를 FastAPI 스트림으로 프록시 전환합니다. API 키는 Python에만 두고 중복 provider 호출을 제거합니다. localhost 경계·본문 제한·동시성 제한·취소 전파·안전한 오류 매핑을 보존/보강하며 route 및 client 테스트를 추가합니다.
- 이후 **6-C**: UI 진행·결과·오류·취소/화면 이탈·재시도 브라우저 확인, 타입 검사/빌드. 동시 실행 제한과 실제 연결 해제 취소 정리를 확인합니다. 원격 공개 배포하지 않습니다.
- 이번 작업에 커밋·원격 푸시는 포함하지 않았습니다. 다음 세션은 이 기록을 먼저 읽고 6-B부터 진행합니다.


> 이 절과 바로 아래 최신 체크포인트를 우선 적용합니다. 이후의 ‘이전 체크포인트’와 최초 UI MVP 설명은 과거 기록이며, 당시의 미구현·키 부재 설명을 현재 상태로 해석하지 않습니다.

### 현재 상태와 범위

- 작업 루트: `C:/Users/rlagn/Desktop/Develop/frontend_tools/React/my-app`.
- 목표: 기존 Next.js UI를 유지하면서 FastAPI + LangGraph 기반 **로컬 팩트체크 MVP**를 연결합니다. 로그인, DB 영속 저장, 공개 배포는 현재 7단계 범위 밖입니다.
- 실제 구현·검증된 범위는 **주장 추출·검색 후보·HTML/plain text 원문 수집·인용/판정·최종 응답 계약·네 단계 LangGraph 조립까지**입니다. 실제 provider를 사용하는 전체 경로의 운영 확인은 7단계에서 수행합니다.
- `backend/.env`에 사용자 API 키가 설정되어 실제 호출에 성공했습니다. 파일·키 값을 출력하거나 커밋하지 않습니다. 다른 세션에서 키가 없다고 추측하지 말고 존재 여부만 확인합니다.
- 마지막 실행 기록: Python 테스트 **96 passed**, Starlette/AnyIO deprecation 경고 1건. 실제 원문 2개 접근 및 리다이렉트 처리를 확인했고, 기본 workflow 노드 조립도 확인했습니다.
- 기존 작업에 미커밋 변경과 untracked 파일이 다수 있습니다. 초기 Git 상태를 확인하고 사용자 변경을 보존합니다. 문서 저장은 Git 커밋/원격 백업과 다릅니다.

### 전체 단계표

| 단계 | 작업 | 상태 / 완료 범위 |
|---|---|---|
| 1 | LangGraph 실행 기반 | 완료: 네 단계 순서, 상태 전달, 오류 중단 테스트 |
| 2 | FastAPI 스키마·상태 API | 완료: 요청 검증 및 상태 확인 |
| 3 | POST → LangGraph 실행 경계 | 완료: 주입 테스트, 422/502/503 처리 및 최종 계약 검증 |
| 4 | 실제 LLM·주장 추출 | 완료: `.env` 로딩, 추출 전용 그래프, 실제 Luna max 호출 성공 |
| 5 | 검색·원문·인용·판정 | 구현 완료: 5-A/5-B/5-C/5-D. 실제 provider 전체 경로 운영 확인은 7단계에서 수행 |
| 6 | UI·진행 상태·취소·타임아웃 | 진행 중: 6-A 스트림 완료, 6-B 프록시/6-C UI 검증 남음 |
| 7 | 전체 회귀·실행 검증·최종 인계 | 미완료 |

### 5단계 — 검색부터 전체 검증 그래프까지

**5-D 최종 계약·조립까지 완료했습니다. 다음 작업은 6단계 UI 연결입니다.**

- [x] **5-A 검색 커넥터:** 현재 추출된 fact 주장에 대해 실제 검색을 수행하고 후보 출처 URL·제목·기관 정보를 정규화합니다. 검색 완료 여부 확인, URL 중복 제거, 출처 개수 제한, 빈 결과·실패 테스트를 추가합니다. 기존 TypeScript 구현은 참고하되 무검토 복사하지 않습니다. 검색 요약을 검증된 원문 인용으로 취급하지 않습니다.
- [x] **5-B 원문 수집:** 후보 URL의 본문과 접근 상태를 수집합니다. SSRF 방어(내부/loopback/link-local 주소 및 리다이렉트 검증), HTTP/HTTPS 제한, 타임아웃, 응답 바이트 제한을 구현·검증합니다. 접근 실패 시 근거를 만들어내지 않습니다.
- [x] **5-C 인용·판정:** `backend/verification.py`에 원문 인용·claimId/sourceId 무결성 검사, 의견·예측·근거 부족·맥락 누락·상충 근거 판정 규칙을 추가했습니다. 검색 요약은 evidence로 사용하지 않으며, 잘못된 인용·조건 불일치·원문 접근 불가 시 보수적으로 근거 부족으로 낮춥니다.
- [x] **5-D 최종 계약·조립:** `backend/contracts.py`에 `FactCheckResult`·`FactCheckResponse`·상태 계약을 추가하여 `app/lib/fact-check-contract.ts`의 필드와 연결했습니다. claim/source/evidence 교차 참조와 `quoteVerified: true`를 검증하고, `runtime.py`에서 extracting → searching → reading → verifying 네 노드를 실제 어댑터로 조립했습니다. `main.py` 기본 workflow와 상태 API를 연결했으며, 키가 없으면 `configured/workflowReady/webSearch`를 false로 유지합니다.

5단계 완료 조건: 실제 비민감 입력으로 추출→검색→원문→판정 경로를 실행하고, 출처·인용 연결과 근거 부족 처리를 확인해야 합니다. 외부 서비스 실패와 코드 결함을 구분하여 기록합니다.

### 6단계 — 기존 UI 연결

- [ ] 현재 `app/api/fact-check/route.ts`, `app/components/fact-check-client.ts`, 공유 계약과 대시보드를 먼저 읽습니다. 기존 Next.js provider 경로와 Python 경로를 동시에 중복 호출하지 않습니다.
- [ ] Next.js 서버 경계를 통해 FastAPI로 연결하고 API 키를 브라우저에 전달하지 않습니다. 기존 UI 디자인과 레거시 파일은 범위 밖 변경을 하지 않습니다.
- [ ] `extracting/searching/reading/verifying` 단계 이벤트와 최종 결과·오류 이벤트를 전달합니다. 현재 Python 임시 JSON 응답은 기존 NDJSON 클라이언트와 바로 호환되지 않으므로 계약을 맞춥니다.
- [ ] 취소, 화면 이탈, 중복 제출, 동시 실행 제한, end-to-end 타임아웃, 오류 후 재시도를 처리하고 서버 작업 정리까지 검증합니다.
- [ ] 실제 결과와 데모 데이터를 분리합니다. 개발용 mock을 추가한다면 명시적 모드와 테스트 데이터 표시를 사용하며 실제 API 실패 시 몰래 mock으로 대체하지 않습니다.

6단계 완료 조건: 브라우저에서 입력→진행→실제 결과 및 오류/취소 흐름을 확인하고 타입 검사·빌드·회귀 테스트를 통과해야 합니다.

### 7단계 — 최종 검증 및 인계

- [ ] Python 전체 테스트, 프론트엔드 기존 테스트, `npm run typecheck`, `npm run build`를 실행합니다. 프로젝트의 실제 스크립트와 테스트 파일을 확인한 뒤 명령을 선택합니다.
- [ ] 잘못된 JSON, 동의 없음, 긴 본문, provider 실패, 검색 결과 없음, 원문 차단, 인용 불일치, 취소·타임아웃을 검증합니다.
- [ ] 데스크톱·모바일 브라우저에서 기존 화면과 리포트 기능의 회귀 여부를 확인합니다.
- [ ] 비밀정보 노출·Git 제외·서버 전용 키 경계를 점검합니다. 키나 `.env` 원문은 테스트 로그·스크린샷·문서에 넣지 않습니다.
- [ ] 임시 서버/테스트 브라우저를 종료하고 실제 실행 명령, 환경변수 이름, 검증 결과, 미해결 문제를 인계서에 갱신합니다.

### 우선 읽을 파일

| 파일 | 역할 / 주의 |
|---|---|
| `backend/runtime.py` | `.env` 로딩 및 실제 네 단계 전체 그래프 조립 |
| `backend/extraction.py` | 실제 OpenAI 주장 추출 어댑터 |
| `backend/workflow.py` | 네 노드 순차 그래프 팩토리, 어댑터 주입 필요 |
| `backend/main.py`, `backend/schemas.py` | API 경계·요청 검증. 서버 키가 있으면 기본 POST가 조립된 workflow를 실행 |
| `backend/tests/` | 기존 오프라인 회귀 테스트 |
| `app/lib/fact-check-contract.ts` | 기존 프론트엔드 요청·결과·이벤트 계약 |
| `app/lib/server/agent.ts`, `public-source.ts` | 기존 TypeScript 처리 참고. Python 대체 완료로 착각하지 않음 |
| `app/api/fact-check/route.ts` | 기존 Next.js 서버 경계 |
| `app/components/fact-check-client.ts` | 스트림 소비 및 클라이언트 요청 처리 |

### 작업·모델 운영 원칙

1. 작은 세부 작업 하나를 구현하고 테스트한 뒤 결과와 다음 시작점을 이 파일에 저장하고 멈춥니다. 쿼터 소진을 피하기 위해 여러 단계를 연속 진행하지 않습니다.
2. 변경 전 파일을 읽고 Git 상태를 확인합니다. 동작 변경은 실패 테스트→최소 구현→전체 회귀 순서로 진행합니다.
3. 구현용 AI 모델과 서비스 모델을 혼동하지 않습니다. 서비스는 현재 `gpt-5.6-luna` / reasoning `max`를 실제 확인했습니다. 개발 모델의 변경은 사용자 선택이며 이 인계로 변경을 지시하지 않습니다.
4. Luna Max로 개발하는 방안은 논의했지만 변경이 확정된 것은 아닙니다. 사용한다면 보안·인용·판정 로직은 별도 검토를 권장합니다. 모델 성능이나 쿼터 절감량은 비교 측정하지 않았습니다.
5. 로컬 테스트는 `cd backend` 후 `uv sync --locked`, `uv run pytest -q`로 재현합니다. 실제 provider 검증은 유료 호출일 수 있으므로 작고 비민감한 입력으로 제한하고 오프라인 테스트와 구분하여 기록합니다.

## 최신 체크포인트: 5-D 최종 계약·조립 완료

- 추가: `backend/verification.py`, `backend/tests/test_verification.py`. Pydantic strict 모델로 판정 출력과 evidence 후보를 검증하고, `verify_claims` provider adapter는 검증된 원문만 모델에 전달합니다.
- `ground_judgments`는 fact 주장마다 정확히 한 번의 `claimId` 판정을 요구하며, 존재하지 않거나 접근 불가한 `sourceId`, 원문에 없는 인용, 10자 미만 인용, 검색 snippet만 있는 인용을 evidence에서 제외합니다.
- 인용은 수집된 `sourceTexts`에서 공백 정규화 후 실제 포함 여부를 확인합니다. 검증된 원문이 없으면 provider 호출 없이 `insufficient_evidence`로 남기며, 검색 요약·출처 메타데이터는 evidence로 사용하지 않습니다.
- `comparison`이 `same`이 아닌 지지·반박 인용은 직접 근거로 인정하지 않습니다. `missing_context`는 조건 차이가 표시된 배경 인용을 요구하고, 동일 조건의 지지·반박이 서로 다른 출처에서 확인되면 `conflicting_sources`로 구분합니다.
- 의견·예측은 `not_checkable`, 원문 검증이 실패한 사실 주장은 `insufficient_evidence`로 처리합니다. 모델이 일부 허위 인용을 섞으면 유효 인용은 보존하되 판정은 보수적으로 근거 부족으로 낮추고 경고를 추가합니다.
- 추가: `backend/contracts.py`, `backend/tests/test_contracts.py`, `backend/tests/test_runtime_assembly.py`. 최종 결과를 strict Pydantic 모델로 검증하고, 내부 `sourceTexts`·`resolvedUrl` 필드가 HTTP 결과에 섞이지 않도록 공개 계약으로 투영합니다.
- `build_fact_check_result`는 `FactCheckResult`를 통해 원문·주장·출처·evidence 필드를 검증하며, 알 수 없는 ID·미검증 evidence·미연결 evidence를 거부합니다. `main.py`는 임시 비어 있지 않은 dict 검사를 제거하고 `FactCheckResponse`를 검증한 뒤 반환합니다.
- `build_runtime_workflow`는 실제 extraction/search/read/verification 어댑터를 네 단계에 주입하고 verifying 단계에서 최종 결과를 조립합니다. 테스트에서는 fake 어댑터로 네 단계 순서와 최종 frontend 계약을 확인했습니다.
- 상태 API는 backend `.env` 또는 프로세스 환경변수에 키가 없을 때 `configured: false`, `workflowReady: false`, `webSearch: false`, `phase: api-foundation`을 유지합니다. 키가 있으면 `workflow-ready`를 보고하지만 provider 성공을 의미하지는 않습니다.
- 검증: `uv run pytest -q` **96 passed**, `uv lock --check` 통과, `git diff --check` 통과. `uv run python`으로 기본 workflow 노드 `extracting/searching/reading/verifying` 조립을 확인했습니다. 기존 Starlette/AnyIO deprecation 경고 1건은 유지됩니다.
- 실제 provider 전체 경로 실행은 비용·외부 의존성이 있으므로 이번 단계에서 반복하지 않았습니다. 7단계에서 비민감 입력으로 추출→검색→원문→판정 및 실패·근거 부족을 운영 확인해야 합니다.

## 이전 체크포인트: 5-B 원문 수집 완료

- 추가: `backend/sources.py`, `tests/test_sources.py`, `tests/test_source_fetch.py`, `tests/test_read_graph.py`. `backend/workflow.py`에 내부 `sourceTexts` 상태를 추가하였고 aiohttp 의존성/잠금 파일을 갱신했습니다.
- 공개 주소만 반환하는 resolver를 실제 연결에 사용합니다. DNS 응답에 비공개 주소가 하나라도 있으면 거부하고, 검증한 숫자 주소를 connector에 전달하여 재조회하지 않습니다. URL의 명시적 내부 IP도 차단합니다. TLS 검증은 유지하며 환경 프록시·쿠키·자동 리다이렉트는 사용하지 않습니다.
- 매 리다이렉트 대상 URL 및 연결 DNS를 재검증합니다. 최대 리다이렉트 2회, 요청 전체 8초, 응답 512,000 bytes, 저장 본문 18,000자, 출처 최대 6개입니다.
- HTML/plain text만 지원합니다. script/style/noscript/template를 제거하고 공백을 정규화합니다. PDF·압축 응답·빈 문서·접근 실패는 unavailable로 남깁니다. JS 실행, OCR, PDF 파싱은 구현하지 않았습니다. UTF-8 외 문자셋 처리는 제한적입니다.
- `verified`는 원문을 읽었다는 의미이며 사실 판정이나 인용 일치 검증을 의미하지 않습니다. `sourceTexts`는 내부 상태이며 최종 API 응답에 그대로 노출하지 않아야 합니다. `resolvedUrl`로 최종 URL을 보존합니다.
- RED→GREEN 검증 후 전체 **72 passed**, 기존 의존성 경고 1건. 내부/혼합 DNS, 위험한 리다이렉트, 바이트·형식 제한, 빈 본문, 성공/실패 상태, LangGraph 원문 전달을 테스트했습니다.
- 실제 실행: IAPWS MeltSub 페이지의 리다이렉트 후 원문 3,686자 및 example.com 142자를 수집했습니다. 실제 LLM 호출은 이번 단계에서 수행하지 않았습니다.
- UI·FastAPI 기본 전체 workflow는 변경하지 않았습니다. POST 503 유지. 공개 배포 보안 인증 및 전체 실행 취소/타임아웃은 후속 단계 범위입니다.
- **다음은 5-C 인용·판정**이며 이후 5-D 전체 계약/조립을 진행합니다.

## 이전 체크포인트: 5-A 검색 커넥터 완료

- 추가 파일: `backend/search.py`, `backend/tests/test_search.py`, `backend/tests/test_search_errors.py`. 기존 UI·API·모델 설정·의존성은 변경하지 않았습니다.
- 실제 Responses web_search를 요청하고 검색 실행 완료 여부를 확인합니다. fact가 없으면 호출을 생략하며 동의/키가 없으면 네트워크 요청을 보내지 않습니다.
- 후보 URL 정규화·fragment 제거·중복 제거·최대 6개 제한을 적용하였습니다. publisher는 검증된 기관명이 아닌 호스트명이며 제목이 없으면 호스트명을 사용합니다.
- 후보의 `accessStatus: pending`은 Python 내부 임시 계약입니다. 원문 확인 없이 verified로 표시하지 않으며 최종 frontend FactSource와 아직 호환되지 않습니다. 검색 요약·모델 설명을 evidence로 저장하지 않습니다.
- 비 HTTP URL, 자격 증명 포함 URL, 별도 포트, 일부 명시적 내부 주소를 제외합니다. 이는 완전한 SSRF 방어가 아닙니다. DNS·redirect·연결 대상 IP 검증은 반드시 5-B fetcher에서 구현해야 합니다.
- 검색 요청은 90초 전체 제한과 응답 1MB 제한을 적용합니다. 원문 페이지를 직접 요청하지 않습니다.
- 검증: 미구현/실패 처리 RED 후 GREEN, 전체 **46 passed**. 빈 검색 결과, 비사실 주장, 미완료 검색, 동의/키 부재, HTTP 실패, URL 필터링·중복·개수 제한을 확인했습니다.
- 실제 호출: 첫 요청은 SEARCH_FAILED 계열 오류로 종료했으나 상세 원인은 수집하지 못했습니다. 비밀을 제외한 진단 재시도에서는 HTTP 200, completed 응답 및 completed web_search_call을 확인하고 후보 출처 6개를 반환했습니다. 모든 후보는 pending이며 원문 접근 가능성·인용·독립성은 확인하지 않았습니다. 성공 한 번으로 안정성을 보장하지 않습니다.
- 검색 어댑터는 상태 업데이트 함수로 추가되었으며 기본 FastAPI 전체 그래프에는 아직 등록하지 않았습니다. POST 503 유지. 자동 재시도 정책도 추가하지 않았습니다.
- **다음: 5-B 원문 수집**. 그 다음 5-C 인용/판정, 5-D 계약/조립, 6 UI 연결, 7 최종 검증 순서입니다.

## 이전 체크포인트: 4단계 완료 — 실제 주장 추출 확인

- `backend/runtime.py` 추가: backend 기준 `.env`를 읽고 프로세스 환경변수를 우선 적용합니다. 키는 SecretStr로 보관하며 repr에 노출하지 않습니다. 환경변수를 전역 변경하지 않습니다.
- `build_extraction_graph`는 START → extracting → END 구조입니다. 실제 `extract_claims` 어댑터를 주입하여 실행하였습니다. 검색/판정을 흉내 내지 않고 주장 추출에서 종료합니다.
- `python-dotenv` 의존성 및 잠금 파일을 갱신하고 `backend/tests/test_runtime.py`를 추가하였습니다.
- **실제 호출 성공:** backend/.env의 자격 증명으로 OpenAI Responses API에 `gpt-5.6-luna`, reasoning `max`, Structured Outputs 요청을 수행했습니다. 비민감 테스트 문장 `Water freezes at 0 degrees Celsius at standard atmospheric pressure.`에서 fact 주장 1개, 원문 위치 0~68을 반환했습니다. 판정 결과는 생성하지 않았습니다.
- 키 값·provider 원시 응답·인증 헤더는 출력하지 않았으며 `.env`는 수정하지 않았습니다. `git check-ignore backend/.env`로 제외 규칙을 확인했습니다.
- 검증: RED 확인 후 구현, 전체 **36 passed**, 기존 Starlette/AnyIO 경고 1건. 실제 추출 LangGraph 실행까지 확인하였습니다.
- UI 및 전체 팩트체크 POST는 아직 연결하지 않았습니다. `main.py`의 전체 workflow는 여전히 미구성이므로 503을 유지합니다. 자격 증명 확보와 추출 성공을 전체 검증 준비 완료로 표시하지 않습니다.
- **다음은 5단계:** 실제 검색 → 원문 수집 → 인용 검증 → 판정입니다. 작업량이 크므로 검색 커넥터부터 세부 단계로 나누어 진행합니다. 6 UI/진행/취소, 7 전체 회귀 검증은 이후입니다.

## 이전 체크포인트: 4단계 부분 완료 — 실제 호출은 자격 증명 대기

- 공식 모델 문서 https://developers.openai.com/api/docs/models/gpt-5.6-luna 에서 `gpt-5.6-luna`, reasoning `max`, Structured Outputs 지원을 확인하였습니다. 이는 계정별 접근 권한이나 실제 요청 성공을 보장하지 않습니다.
- `backend/extraction.py` 추가: OpenAI Responses 요청을 구성하는 서버 전용 비동기 주장 추출 어댑터입니다. 최대 3개 주장, 원문 연속 인용, 유형 분류, JS 호환 UTF-16 위치를 반환합니다. `store:false`와 요청 타임아웃을 설정합니다.
- 빈 키, HTTP 오류, 미완료 응답, 거절, 중복/원문에 없는 인용, 복수 출력은 오류로 처리하며 가짜 주장을 생성하지 않습니다.
- `backend/tests/test_extraction.py`에 MockTransport 오프라인 테스트를 추가하였습니다. 먼저 실패를 확인한 뒤 구현했으며 전체 **34 passed**, 기존 의존성 경고 1건입니다. `uv lock --check` 통과.
- `httpx`를 runtime 의존성에도 명시하고 잠금 파일을 갱신하였습니다. UI·Next.js·기존 그래프·FastAPI 엔드포인트는 변경하지 않았습니다.
- **막힌 부분:** 프로젝트에는 `.env.example`만 존재하며 backend 환경 파일 및 현재 프로세스의 `OPENAI_API_KEY`가 없습니다. 비밀 값은 읽거나 출력하지 않았습니다. 실제 provider 호출을 하지 않았으므로 4단계 전체 완료가 아닙니다.
- 어댑터는 아직 기본 그래프에 등록하지 않았습니다. API는 계속 503 미구성 상태이며 검색/판정 노드도 미구현입니다. 전체 단계가 없는 상태에서 성공 팩트체크 결과로 포장하지 않습니다.
- 다음 작업: 안전한 로컬 자격 증명 설정 후 작은 비민감 입력으로 실제 주장 추출을 확인하고 LangGraph 추출 노드에 연결합니다. 이 확인 전에는 5단계로 자동 진행하지 않습니다. 키를 채팅이나 저장소에 기록하지 않습니다.
- 추가 한계: 응답 바이트 제한, end-to-end timeout 및 최종 결과 계약은 후속 단계에서 보강해야 합니다.

## 이전 체크포인트: POST → LangGraph 3단계 완료

- 수정: `backend/main.py`, `backend/tests/test_api.py`. 추가: `backend/tests/test_execution.py`. UI·Next.js API·provider 설정·의존성은 변경하지 않았습니다.
- `POST /api/fact-check`에 `FactCheckRequest`를 연결하였습니다. 기본 `get_workflow()`는 `None`이므로 유효한 요청도 **503 NOT_CONFIGURED**로 차단하며 데모 판정을 생성하지 않습니다.
- FastAPI dependency override로 실제 컴파일된 LangGraph와 테스트 전용 어댑터를 주입하여 HTTP 요청 → 네 단계 실행 → 결과 반환을 검증하였습니다. 테스트용 어댑터는 운영 앱에 등록하지 않았습니다.
- 입력 오류·잘못된 JSON: **422 INVALID_REQUEST**. 원문이나 내부 검증 오류를 응답에 반사하지 않으며 그래프를 실행하지 않습니다.
- 그래프 예외·누락/null 결과: **502 AGENT_FAILED**. 내부 provider 진단 및 부분 상태는 반환하지 않습니다. 응답에는 `Cache-Control: no-store`를 설정합니다.
- 현재 성공 계약은 임시 JSON `{result: {...}}`입니다. 결과는 비어 있지 않은 dict인지까지만 검사합니다. 최종 FactCheckResult 스키마, NDJSON 스트리밍 및 클라이언트 호환 연결은 아직 완료하지 않았습니다.
- 검증: 미구현/오류 처리 RED 확인 후 GREEN. 전체 **26 passed**, 기존 Starlette/AnyIO deprecation 경고 1건. TestClient ASGI 요청으로 실제 LangGraph 실행을 검증하였고 외부 LLM 호출이나 브라우저 검증은 하지 않았습니다.
- 총 7단계 중 3단계까지 완료: 1 그래프 기반, 2 API 스키마/상태, 3 POST 실행 경계, **4 실제 LLM·주장 추출·모델 지원 확인**, 5 검색/원문/인용/판정, 6 UI/진행/취소/타임아웃, 7 전체 회귀 검증.
- **다음 한 단계는 4단계**입니다. 실제 모델 식별자와 reasoning 지원을 확인한 뒤 연결해야 합니다. 기존 `gpt-5.6-luna` 및 `max`를 검증 없이 지원된다고 간주하지 않습니다.
- 상태 API는 계속 미구성 상태를 반환합니다. 인증·바이트 제한·취소/타임아웃·공개 배포 보안은 미구현이며 로컬 전용 원칙을 유지합니다.

## 이전 체크포인트: FastAPI 2단계 완료

- 작업 범위: `backend/main.py`, `backend/schemas.py`, `backend/tests/test_api.py`를 추가하고 `backend/pyproject.toml`, `backend/uv.lock`을 갱신하였습니다. 기존 UI·Next.js API·LangGraph 그래프·모델 설정은 수정하지 않았습니다.
- `GET /health`: 프로세스 생존 상태를 반환합니다. 실제 provider 준비 상태를 의미하지 않습니다.
- `GET /api/fact-check`: `configured: false`, `workflowReady: false`, `webSearch: false`, `model: null`, `reasoning: null`을 반환합니다. 비밀 설정을 읽거나 출력하지 않습니다.
- `FactCheckRequest`: 기존 `text`, `focus`, `consent` 필드를 모두 요구합니다. 원문은 보존하며 공백 본문, 추가 필드, 타입 변환, 동의 누락/거부를 차단합니다. 본문 12,000·focus 500 제한은 JavaScript와 동일한 UTF-16 단위를 사용합니다.
- 요청 스키마는 독립 검증만 완료하였습니다. HTTP POST 연결은 아직 없으므로 `POST /api/fact-check`는 405입니다. 해당 요청 스키마는 아직 OpenAPI 요청 본문으로 노출되지 않습니다.
- 검증: 스키마·앱 미구현 RED 확인 후 구현하였습니다. `uv run pytest -q` **18 passed**, `uv lock --check` 통과. Starlette TestClient에서 AnyIO 별칭 관련 의존성 deprecation 경고 1건이 발생하였으나 테스트 실패는 없습니다.
- 실제 Uvicorn을 임시 loopback 포트에서 실행하여 두 GET API의 HTTP JSON 응답을 확인하고 서버를 종료하였습니다.
- 실행: `cd backend` → `uv sync --locked` → `uv run uvicorn main:app --host 127.0.0.1 --port 8010`. 8010은 예시이며 사용 중인 포트는 피해야 합니다.
- **다음 한 단계:** FastAPI POST와 LangGraph를 연결하는 실행 경계를 테스트용 어댑터 주입으로 검증합니다. 기본 실행은 실제 어댑터가 없으면 503으로 차단하며, 가짜 판정을 반환하지 않아야 합니다. 실제 provider 이전과 프론트엔드 전환은 이후 별도 단계입니다.
- 인증, body 바이트 제한, 취소·타임아웃, 외부 서비스 지원 검증, 공개 배포 보안은 아직 구현하지 않았습니다. 현재는 로컬 개발용이며 공개 배포하지 않습니다.
- 단계별 구현·검증·체크포인트 저장 후 중단 원칙을 유지합니다.

## 이전 체크포인트: LangGraph 1단계 완료

> 아래 기존 UI MVP 기록은 과거 기록입니다. 현재 `app/api/fact-check/route.ts` 및 `app/lib/server/agent.ts`가 존재하므로 기존의 API 미구현 설명을 현재 상태로 해석하지 않아야 합니다. 기존 provider의 실서비스 지원 여부는 이번 단계에서 확인하지 않았습니다.

- 작업 범위: `backend/`에 Python LangGraph 실행 기반만 추가하였습니다. 기존 UI, Next.js API, 모델 설정은 수정하지 않았습니다.
- `backend/workflow.py`: 명시적으로 전달받은 비동기 어댑터를 `extracting → searching → reading → verifying` 순서로 실행합니다. 기존 프론트엔드 단계 이름을 유지합니다.
- `backend/pyproject.toml`, `backend/uv.lock`: LangGraph 및 테스트 의존성을 관리합니다. 실제 설치 버전은 LangGraph 1.2.11입니다.
- `backend/.gitignore`: 가상환경, 캐시, 비밀 환경설정 파일을 제외합니다.
- `backend/tests/test_workflow.py`: 실행 순서·상태 전달, 단계 스트리밍, 실패 시 후속 실행 중단을 검증합니다.
- 검증: 최초 미구현 실패 확인 후 구현하였으며, `cd backend && uv run pytest -q` 결과 **3 passed**입니다. `git diff --check`도 통과하였습니다.
- 중요: 실제 LangGraph 엔진을 실행하였지만 어댑터는 테스트 전용입니다. LLM·검색 호출, FastAPI, 프론트엔드 연결, HTTP 입력 검증, 취소, 영속 저장은 아직 추가하지 않았습니다. 내부 TypedDict는 HTTP 검증 스키마가 아닙니다.
- 재실행: `cd backend` → `uv sync --locked` → `uv run pytest -q`.
- **다음 한 단계:** FastAPI 요청 스키마·상태 확인 API를 추가하고 테스트합니다. 기존 Next.js 경로 교체나 provider 이전은 별도 단계로 진행합니다.
- 작업 방식: 한 단계씩 구현·검증하고 이 체크포인트를 갱신한 뒤 중단합니다. 여러 단계를 한 번에 진행하지 않습니다.


- **작성일:** 2026-09-18 (KST)
- **프로젝트 경로:** `C:/Users/rlagn/Desktop/Develop/frontend_tools/React/my-app`
- **현재 상태:** Next.js App Router 기반 프론트엔드 UI MVP 구현 완료
- **실제 백엔드 연결:** 아직 연결하지 않음. 현재 검증 흐름과 결과는 데모 상태임

## 1. 작업 요약

설치되어 있던 시각 효과·애니메이션 패키지를 활용하여 한국어 중심의 다크 글래스모피즘 팩트체크 대시보드를 구현하였습니다.

구현된 주요 영역은 다음과 같습니다.

- 주장 입력 및 검증 시작 UI
- 검증 파이프라인 진행률 표시
- 최근 검증 결과 목록
- 신뢰도·출처 커버리지·검토 대기 지표
- 출처 품질 패널
- 시스템 활동 로그
- 데스크톱 사이드바 및 모바일 오프캔버스 메뉴
- PNG 리포트 내보내기
- 쉐이더 배경과 Liquid Glass 카드 효과
- Motion 및 Anime.js 기반의 상태·진입 애니메이션

## 2. 실행 방법

프로젝트 루트에서 다음 명령을 실행합니다.

```bash
npm ci
npm run dev
```

개발 서버 기본 주소는 다음과 같습니다.

```text
http://localhost:3000
```

프로덕션 빌드 및 실행은 다음과 같습니다.

```bash
npm run build
npm run start
```

정적 타입 검사는 다음 명령으로 실행합니다.

```bash
npm run typecheck
```

## 3. 주요 파일과 책임

| 파일 | 역할 |
|---|---|
| `app/page.tsx` | Next.js 홈 페이지에서 대시보드 컴포넌트를 렌더링합니다. |
| `app/components/fact-check-dashboard.tsx` | 대시보드 전체 UI, 상태, 이벤트, 데모 검증 흐름을 담당합니다. |
| `app/globals.css` | 전체 색상 토큰, 글래스모피즘, 반응형 레이아웃, 모바일 메뉴, 카드 스타일을 담당합니다. |
| `app/layout.tsx` | App Router 루트 레이아웃 및 페이지 메타데이터를 담당합니다. |
| `next.config.ts` | 현재 기본 Next.js 설정을 유지합니다. |
| `postcss.config.mjs` | Tailwind CSS v4 PostCSS 플러그인을 설정합니다. |
| `tsconfig.json` | Next.js TypeScript 설정 및 보존된 React Router 파일 제외 규칙을 포함합니다. |
| `package.json` | 실행 스크립트와 의존성을 정의합니다. |
| `package-lock.json` | 재현 가능한 npm 의존성 트리를 고정합니다. |

## 4. 현재 사용 중인 시각 효과 패키지

| 패키지 | 버전 | 현재 사용처 |
|---|---:|---|
| `@paper-design/shaders-react` | `0.0.81` | `MeshGradient` 기반 배경 쉐이더 |
| `liquid-glass-react` | `1.1.1` | 카드·입력 패널의 Liquid Glass 효과 |
| `motion` | `13.4.0` | 페이지 진입, 카드 등장, 상태 전환, 토스트 애니메이션 |
| `html2canvas` | `1.4.1` | 대시보드 PNG 리포트 내보내기 |
| `@shadergradient/react` | `2.4.20` | 설치 완료, 현재 화면에서는 미사용 |
| `@react-three/fiber` | `9.7.0` | 설치 완료, 추후 3D/WebGL 확장용 |
| `@react-three/drei` | `10.7.8` | 설치 완료, 추후 Three.js 보조 컴포넌트용 |
| `three` | `0.186.0` | 설치 완료, 현재 화면에서는 미사용 |
| `three-stdlib` | `2.36.1` | 설치 완료, 추후 Three.js 확장용 |
| `camera-controls` | `3.1.2` | 설치 완료, 현재 화면에서는 미사용 |

## 5. 화면 구조

### 5.1 전역 화면

- 좌측 데스크톱 사이드바
- 상단 워크스페이스 헤더
- 오늘의 검증 인사이트 영역
- 새 검증 입력 카드
- 네 개의 요약 지표 카드
- 최근 검증 목록
- 출처 품질 패널
- 시스템 활동 로그
- 하단 검증 원칙 안내

### 5.2 반응형 처리

- 데스크톱에서는 좌측 사이드바와 2열 콘텐츠 레이아웃을 사용합니다.
- 모바일에서는 사이드바가 오프캔버스 메뉴로 전환됩니다.
- 390px 폭에서 가로 스크롤이 발생하지 않도록 확인하였습니다.
- 모바일 메뉴가 열리면 배경을 불투명하게 처리하여 메뉴 글자와 본문이 겹쳐 보이지 않도록 하였습니다.

### 5.3 Liquid Glass 구현 주의사항

`liquid-glass-react`는 내부적으로 여러 레이어를 Fragment 형태로 렌더링하고 콘텐츠 크기를 측정합니다. 일반적인 문서 흐름에 바로 넣으면 카드 위치와 콘텐츠 너비가 어긋날 수 있으므로 `GlassPanel`에서 다음 구조를 유지해야 합니다.

```tsx
<div className="glass-surface">
  <div className="glass-sizer" aria-hidden="true">
    {children}
  </div>
  <LiquidGlass className="glass-live" ...>
    {children}
  </LiquidGlass>
</div>
```

`glass-sizer`는 레이아웃 높이를 확보하는 숨김 측정 레이어이고, 실제 인터랙션은 `glass-live` 내부 콘텐츠에서 처리합니다. 관련 CSS의 `.glass-live .glass` 및 `.glass-sizer` 규칙을 임의로 삭제하지 않아야 합니다.

## 6. 현재 인터랙션 동작

### 주장 검증 흐름

1. 입력창에 주장을 입력합니다.
2. `검증 시작` 버튼 또는 `Ctrl/Cmd + Enter`를 실행합니다.
3. 상태가 `checking`으로 전환됩니다.
4. 주장 분해 → 출처 대조 → 맥락 평가 단계와 진행률이 표시됩니다.
5. 진행이 완료되면 결과 스트립이 `확인 대기 완료`, 신뢰도 `88%`로 변경됩니다.
6. 해당 주장이 최근 검증 목록의 맨 앞에 추가됩니다.

현재 단계 진행은 실제 API 요청이 아닌 클라이언트 타이머로 구현되어 있습니다.

### 리포트 내보내기

`리포트 내보내기` 버튼은 `html2canvas`로 `#factcheck-dashboard`를 캡처하여 다음 파일명으로 다운로드합니다.

```text
factcheck-agent-report.png
```

WebGL 쉐이더 캔버스는 `ignoreElements`로 제외합니다. 이 처리를 하지 않으면 `preserveDrawingBuffer=false`인 WebGL 컨텍스트를 복제할 때 브라우저 경고가 발생할 수 있습니다.

### 데모 메뉴

아직 실제 페이지가 연결되지 않은 메뉴는 토스트로 `준비 중` 상태를 표시합니다.

- 리포트 보관함
- 출처 모니터
- 검증 가이드
- 설정
- 도움말
- 전체 보기
- 상세 결과
- 출처 품질 상세

## 7. 검증 결과

다음 검증을 완료하였습니다.

| 검증 항목 | 결과 |
|---|---|
| `npm run typecheck` | 통과 |
| `npm run build` | 통과 |
| Next.js 프로덕션 서버 실행 | `next start -p 3011`로 확인 |
| 로컬 HTTP 접근 | `http://127.0.0.1:3011/` 응답 확인 |
| 데스크톱 브라우저 렌더링 | 확인 |
| 390px 모바일 렌더링 | 확인 |
| 모바일 메뉴 열기 | 확인 |
| 주장 입력 → 진행률 → 목록 추가 | 확인 |
| PNG 리포트 다운로드 | 확인 |
| 리포트 캡처 후 콘솔 오류 | 오류 0개, 경고 0개 |
| `git diff --check` | 통과 |

프로덕션 검증에 사용한 서버는 검증 후 종료하였습니다.

## 8. 현재 한계

현재 구현은 UI MVP이며 다음 항목은 아직 실제 서비스 수준으로 연결되지 않았습니다.

1. **팩트체크 API 미연결**
   - 실제 LLM 또는 FastAPI 요청을 보내지 않습니다.
   - 검증 진행률과 결과는 프론트엔드 데모 상태입니다.

2. **실제 출처 수집 미연결**
   - 정부 데이터, 언론, 논문, 검색 API 등의 커넥터가 없습니다.
   - 화면에 표시되는 출처 수와 품질 점수는 데모 값입니다.

3. **메뉴 페이지 미구현**
   - 보관함·출처 모니터·설정·도움말은 토스트만 표시합니다.

4. **정적 지표**
   - `2,648`, `92.4%`, `78%` 등의 값은 정적 샘플 데이터입니다.

5. **시간 정보 정적 표시**
   - `2026. 09. 18 14:32:09`는 현재 하드코딩된 데모 값입니다.

6. **인증 및 사용자 저장 기능 미구현**
   - 계정 메뉴와 워크스페이스는 시각적 UI만 제공하며 실제 인증·권한·저장은 없습니다.

## 9. 다음 작업 권장 순서

### 1단계: API 계약 확정

실제 백엔드 연결 전에 요청·응답 구조를 확정하는 것이 우선입니다. 예시는 다음과 같습니다.

```http
POST /api/fact-check
Content-Type: application/json
```

```json
{
  "claim": "검증할 주장"
}
```

응답 예시:

```json
{
  "verdict": "verified",
  "confidence": 0.88,
  "summary": "판정 근거 요약",
  "sources": [
    {
      "title": "출처 제목",
      "url": "https://example.com/source",
      "publisher": "출처 기관",
      "publishedAt": "2026-09-18"
    }
  ]
}
```

위 API는 현재 저장소에 구현되어 있지 않은 **제안 계약**입니다. 실제 백엔드 계약을 확정한 뒤 적용해야 합니다.

### 2단계: 데모 타이머를 API 요청으로 교체

`app/components/fact-check-dashboard.tsx`의 다음 부분을 교체합니다.

- `checkState` 기반 타이머 진행 로직
- `setTimeout`으로 결과를 추가하는 부분
- 고정된 `confidence`, `sources`, `verdict` 값

권장 구현 방식:

- `AbortController`를 사용하여 중복 요청과 화면 이탈을 처리합니다.
- `loading`, `success`, `error` 상태를 분리합니다.
- API 오류와 출처 부족 상태를 별도 UI로 표시합니다.
- 사용자 입력은 서버에 전달하기 전 길이·빈 문자열·최대 크기를 검증합니다.

### 3단계: Next.js 서버 경계 추가

외부 API 키나 LLM 인증정보는 클라이언트 컴포넌트에 넣지 않아야 합니다. 다음 중 하나를 권장합니다.

- Next.js Route Handler: `app/api/fact-check/route.ts`
- 별도 FastAPI 백엔드 호출
- 서버 측 환경변수 기반 provider adapter

인증정보, API 키, OAuth 토큰, 비밀키는 저장소에 넣지 말고 `.env.local`에만 보관해야 합니다. 저장소에는 값을 기록하지 않고 `[REDACTED]`로 처리해야 합니다.

### 4단계: 결과 상세 화면 구현

- 판정 근거 요약
- 주장 원문과 문장 단위 분석
- 출처별 찬성·반대 근거
- 출처 발행일·기관·신뢰도
- 상충하는 정보 표시
- 결과 공유·리포트 저장

### 5단계: 실제 데이터 기반 지표 연결

- 검증 완료 수
- 평균 신뢰도
- 평균 응답 시간
- 출처별 통과율
- 실패·재검토 비율

각 지표는 API 또는 저장소에서 읽도록 변경해야 합니다.

## 10. 보존된 React Router 레거시 파일

다음 파일은 참고·롤백용으로 보존되어 있으나 현재 Next.js 스크립트에서는 사용하지 않습니다.

```text
app/root.tsx
app/routes.ts
app/routes/
app/welcome/
react-router.config.ts
vite.config.ts
app/app.css
```

`tsconfig.json`의 `exclude`에 레거시 파일이 포함되어 있습니다. 실제 삭제는 별도의 정리 작업으로 진행해야 하며, 현재 인계 범위에서는 삭제하지 않습니다.

## 11. 인계 체크리스트

- [x] Next.js App Router 홈 화면 구현
- [x] 한국어 다크 글래스모피즘 스타일 구현
- [x] Paper Design 쉐이더 배경 연결
- [x] Liquid Glass 카드 연결
- [x] Motion 진입·상태 애니메이션 연결
- [x] Anime.js 상태 펄스 연결
- [x] html2canvas PNG 내보내기 연결
- [x] 데스크톱·모바일 레이아웃 확인
- [x] TypeScript 검사 및 production build 확인
- [x] 데모 검증 흐름 확인
- [ ] 실제 FastAPI 또는 LLM API 연결
- [ ] 실제 출처 수집 및 인용 처리
- [ ] 사용자 인증 및 저장소 연결
- [ ] 메뉴별 상세 페이지 구현
- [ ] 실제 데이터 기반 지표 연결

## 12. 다음 작업자에게 전달할 핵심 사항

현재 결과물은 **시각적 방향과 사용자 흐름을 검증하기 위한 프론트엔드 MVP**입니다. 실제 팩트체크 기능을 추가할 때에는 UI를 먼저 크게 변경하기보다 `handleSubmit`의 데모 타이머를 실제 API 요청 상태 머신으로 교체하고, API 응답을 `checks` 데이터 구조에 매핑하는 방식으로 진행하는 것이 안전합니다.

특히 `LiquidGlass`의 측정용 `glass-sizer` 구조와 WebGL 캡처 제외 설정은 현재 레이아웃과 리포트 export 안정성에 필요하므로 유지해야 합니다.
