<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->


# 1. 지침

- 알아보고 답한다. 확신이 없으면 먼저 조사·확인한 뒤 답한다.
- 결론부터 먼저 말한다.
- 새 질문이 들어오면 먼저 이전 대화와의 관련성을 판단한다. 불명확하면 되물어보고, 관련성이 명확하면 맥락을 이어받고, 관련이 없다면 이전 주제와 가정을 끌어오지 않는다.
- .env 파일은 절대 직접 확인하지 않는다
- 프로젝트·문서·파일·코드 주석 등 작업 결과물에는 반말을 넣지 않는다(정중한 문체로 작성).
- 둘 이상을 비교할 때는 보기 쉽게 표(table) 형태로 표현한다.
- 간단한 질문이나 작은 문제는 군더더기 없이 짧게 답한다.
- 파일을 읽기 전에는 수정하지 않는다
- 파괴적 명령은 확인을 먼저하고 경고를 한다.
- 작업 전후로 diff·상태를 확인한다
- 보안·키·토큰은 절대 출력·커밋하지 않는다
- 긴 작업은 단계별로 보고하고, 막히면 early stop한다.
- 작업이 끝나면 검증 후 작업 브랜치에 commit·push하고 완료 처리한다. main 직접 push는 금지하며, 머지는 PR과 담당자 확인을 거쳐 진행한다, 일반 push가 불가능하거나 force push·비밀정보 노출 위험이 있으면 즉시 알린다.
- 테스트가 끝난 웹·서버·검증용 프로세스가 2개 이상이라면 모두 종료하고 사용자가 사용중인 포트만 남긴다, 사용자가 사용중이던 서버는 재시작한다.


# 2. Karpathy 지침

## 1. Think Before Coding (코딩 전에 생각)

추측 금지. 헷갈리면 숨기지 말고 명확하게 드러낸다.

- 가정을 명시하고. 불확실하면 물어본다.
- 해석이 여러 개면 맘대로 고르지 않고 제시하라
- 필요할 때는 반박하고 더 간단한 방법이 있다면 말하라.
- 이해가 안될때는 멈춘다. 무엇이 헷갈리는지 사용자에게 물어본다. 

## 2. Simplicity First (단순 우선)

문제를 해결하는 데 필요한 최소한의 코드만 작성한다. 추측성 코드는 일절 포함하지 않는다.

- 시킨 것 외 기능 추가 금지.
- 일회용 코드에 추상화 금지.
- 안 시킨 유연성·설정화 금지.
- 일어날 수 없는 에러 처리 금지.
- 200줄을 50줄로 줄일 수 있다면 다시 쓴다
테스트: 시니어 엔지니어가 불필요하게 복잡하다고 할거같다면 단순화한다.

## 3. Surgical Changes (외과수술식 수정)

꼭 필요한 것만 만진다. 자신이 저지른 일은 스스로 수습한다.

기존 코드를 편집할 때:
- 인접한 코드, 주석 또는 서식을 "개선"하지 않는다
- 멀쩡한 것을 굳이 리팩토링하지 않는다
- 네 생각과 방식이 다르더라도 기존 스타일 따라간다
- 관련 없는 데드코드 보이면 삭제하지 않고 보고한다.
변경 사항으로 인해 고아 파일이 생성되는 경우:
- 네 변경이 만든 미사용 import·변수·함수는 지운다.
- 요청받지 않는 한 기존의 사용되지 않는 코드는 삭제하지 않는다.
테스트: 바뀐 모든 줄이 사용자 요청과 직결되어야 한다.

## 4. Goal-Driven Execution (목표 기반 실행)

성공 기준 정의하고 검증될 때까지 반복.

- "유효성 검사 추가" → "잘못된 입력 테스트 쓰고 해당 테스트를 통과시킨다"
- "버그를 수정하라" → "재현 테스트 쓰고 통과시킨다"
- "X 리팩터" → "전후 테스트 통과 확인한다"
- 여러 단계면 계획+검증 세트로:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```
- 성공 기준이 강하면 혼자 돌 수 있고, 약하면 ("되게 해줘") 계속 물어봐야 함.

