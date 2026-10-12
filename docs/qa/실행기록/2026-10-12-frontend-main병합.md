# feat/frontend → main 병합 검증 (2026-10-12)

## 통합 내용

- 사용자 요청에 따라 기존 [PR #4](https://github.com/teach97/TRUE-OR-NOT/pull/4)를 사용합니다. 시작 프런트엔드 HEAD는 `f44ecf9`, 최신 main은 `107a600`입니다.
- `feat/frontend`에서 main을 통합하면서 대시보드와 작업현황 문서의 충돌을 구간별로 해결했습니다.
- 현재 대시보드 배치·주장별 점수 고정·출처 강조·중복 패널 제거·반투명 배경을 보존했습니다. main의 Hive·의도 분류·별도 합성 제거·본문 출처 번호·partial 결과 복원·완료 시 진행 메시지 처리도 보존했습니다.
- 오른쪽 출처 후보 표시를 기대하던 화면 테스트는 왼쪽 검토한 출처의 검색 경로·순위 표시를 확인하도록 조정했습니다.
- 통합 회귀 테스트는 추출의 `max`와 판정의 `high` 설정을 각각 확인합니다. 추가 합성 요청이 없으며 원문 인용·판정·불확실성이 유지되는 기존 검증을 보존했습니다.
- 빌드가 변경한 `next-env.d.ts`는 빌드 전 상태로 복구했습니다.
- 개별 작업 커밋을 유지하는 merge commit 방식으로 PR을 반영합니다. 원격 병합 결과는 PR의 merged 상태와 merge commit에서 확인합니다.

## 실행 및 결과

| 명령·확인 | 결과 |
|---|---|
| `git fetch origin main feat/frontend` | 원격 브랜치 확인 완료 |
| `git merge-tree --write-tree origin/main origin/feat/frontend` | 두 파일 충돌 확인 |
| `git merge --no-commit --no-ff origin/main` | 두 파일 충돌을 구간별로 해결 |
| `uv lock --check` | 62개 패키지 잠금 검사 통과 |
| `npm test -- --test-isolation=none --test-reporter=dot` | FE 131개 통과. 최초 실행에서 삭제된 오른쪽 카드의 이전 기대를 확인하고 조정했습니다. |
| backend `.venv`의 `python -B -m pytest -q tests -p no:cacheprovider --basetemp <고유 임시 경로> --tb=short` | BE 458개 통과. 최초 3개 실패는 이전 판정 추론 설정의 기대·모의 응답 검사였으며 단계별 설정으로 조정했습니다. 기존 Starlette 경고 1개입니다. |
| `npm run typecheck` | 통과 |
| `npm run build` | Next.js 16.3.5 프로덕션 빌드·8개 페이지 생성 통과 |
| `git diff --check origin/main` | PR 변경 범위 검사 통과 |
| `git diff --cached --check` | main에 이미 있던 출처 번호 테스트의 공백·Agent 문서의 마지막 빈 줄 경고를 확인했습니다. 해당 main 내용은 유지했습니다. |

## 남은 확인 범위

- 실제 공급자·검색·DB 호출과 브라우저 화면 확인은 이번 병합 검증에서 재실행하지 않았습니다.
- GitHub CI·원격 main 반영 상태의 기준 링크는 [PR #4](https://github.com/teach97/TRUE-OR-NOT/pull/4)입니다.
