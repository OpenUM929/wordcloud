# 계획서 — .clinerules msys 오염 제거 및 wordcloud 문서 구조 교정

> 상태: Done | 작성일: 2026-07-23 | 완료일: 2026-07-23
> 작업 유형: D (리팩토링) + B (기능 개선 — 신규 디렉토리 구조)
> 선행: -

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-23 | 전체 | 초안 작성 |

---

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | `.clinerules/core/00-core.md` 20행의 "wordcloud 관련 작업" 경로가 `docs/msys/`를 가리키는가? | Y | Y — core/00-core.md:20에 `docs/msys/README.md` 하드코딩 확인 |
| 1.2 | `.clinerules/core/00-core.md` 42행의 "운영자 메뉴얼 작성/수정" 경로가 `docs/msys/`를 가리키는가? | Y | Y — core/00-core.md:42에 `docs/msys/operator-manual/DEVELOPMENT.md` 하드코딩 확인 |
| 1.3 | `docs/msys/operator-manual/developer-manual/` 하위 10개 파일이 wordcloud 프로젝트 전용 콘텐츠인가? | Y | Y — developer-manual/00-index.md에 "wordcloud_project/", "KoTE", "hr-sentiment-v1.0" 명시 |
| 1.4 | `.clinerules/docs/project_wordcloud/operator-manual/` 디렉토리가 현재 존재하지 않는가? | Y | Y — project_wordcloud 하위에 operator-manual 없음 (deployment.md, modules/, routes/, services/, templates/만 존재) |
| 1.5 | wordcloud 프로젝트의 가상환경 폴더명이 `venv/`인가? | Y | Y — `wordcloud_project/venv/pyvenv.cfg` 확인 |
| 1.6 | wordcloud의 메인 앱 진입점이 `web/app.py`인가? | Y | Y — `wordcloud_project/web/app.py` 확인 (msys_app.py 없음) |
| 1.7 | `data_report.md` 템플릿이 wordcloud 프로젝트에 존재하는가? | N | N — 해당 파일 없음 (16-report-writing.md:19 참조 대상 부재) |
| 1.8 | `build_zip.py` 스크립트가 wordcloud에 존재하는가? | N | N — 없음 (06.git-rules.md의 msys.zip 규칙은 wordcloud와 무관) |
| 1.9 | `.githooks/` 디렉토리가 wordcloud에 존재하는가? | N | N — 없음 (pre-commit hook 구조 없음) |

---

## 1. 배경 및 목적

### 문제

`A/core/00-core.md`(MSYS 프로젝트 템플릿)에서 `.clinerules/core/00-core.md`(wordcloud 프로젝트 공통 규칙)로 복사·적용할 때, **프로젝트명(msys) 하드코딩을 wordcloud로 치환하지 않은 채 방치**했다.

이로 인해:
1. **AI(서브에이전트 포함)가 00-core.md의 지시를 정직하게 따르면서** wordcloud 메뉴얼을 `docs/msys/`에 생성
2. **코어 공통 규칙 파일 7개**에 msys 전용 내용이 오염
3. **검증 시나리오 3개**가 msys 경로를 참조
4. wordcloud 전용 개발자 메뉴얼이 msys 폴더 구조 안에 섞임

### 목적

1. wordcloud 전용 operator-manual 디렉토리 구조 신설
2. 코어 공통 규칙에서 msys 전용 내용 제거/wordcloud 전환
3. 오염된 검증 시나리오 삭제
4. msys 전용 CR 보고서 삭제
5. 재발 방지 — 향후 프로젝트 템플릿 복사 시 프로젝트명 치환 필수화

---

## 2. 현재 코드 분석

### 2.1 코어 규칙 오염 파일

| 파일 | 행 | 오염 내용 | 심각도 |
|------|-----|-----------|--------|
| `core/00-core.md` | 20 | `wordcloud 관련 작업 → docs/msys/README.md` | 높음 |
| `core/00-core.md` | 42 | `운영자 메뉴얼 → docs/msys/operator-manual/DEVELOPMENT.md` | 높음 |
| `core/02.documentation.md` | 61 | `docs/msys/operator-manual/DEVELOPMENT.md` 참조 | 높음 |
| `core/06.git-rules.md` | 150~163 | `msys.zip` 자동 생성, `msys_app.py`, `msys_venv/` 등 전용 빌드 로직 | 높음 |
| `core/06.git-rules.md` | 537 | `root 저장소(msys)` | 낮음 |
| `core/14.comment-log-removal.md` | 11,73,83,87~90 | `msys_venv/`, `msys_app`, `D:\dev\msys` | 높음 |
| `core/16-report-writing.md` | 19 | `docs/msys/templates/data_report.md` 참조 (파일 자체 없음) | 중간 |

### 2.2 msys에 섞인 wordcloud 콘텐츠

| 위치 | 파일 수 | 내용 |
|------|---------|------|
| `docs/msys/operator-manual/developer-manual/` | 10개 | wordcloud 아키텍처, 모듈지도, 감정분석엔진, 빌드/배포, 파인튜닝 등 |

### 2.3 오염된 검증 시나리오

| 파일 | msys 참조 수 |
|------|-------------|
| `verification/scenarios/02-time-handling-workflow.md` | 10건 |
| `verification/scenarios/03-setting-popup-scenario.md` | 8건 |
| `verification/scenarios/04-user-statistic-scenario.md` | 20건+ |

### 2.4 wordcloud 실제 구조 (실측 기반)

| 항목 | 실제 경로 | msys 규칙의 경로 |
|------|----------|-----------------|
| 가상환경 | `wordcloud_project/venv/` | `msys_venv/` |
| 메인 앱 | `wordcloud_project/web/app.py` | `msys_app.py` |
| 빌드 스크립트 | `wordcloud_project/deploy/build_deploy.ps1` | `scripts/build_zip.py` |
| zip 산출물 | `wordcloud-project.zip` | `msys.zip` |
| pre-commit hook | 없음 | `.githooks/` |

---

## 3. 변경 설계

### Phase 1: wordcloud operator-manual 디렉토리 신설

**대상**: `docs/msys/operator-manual/developer-manual/` (10 파일) 이전

```
Before:
.clinerules/docs/msys/operator-manual/developer-manual/  ← wordcloud 콘텐츠가 msys 안에

After:
.clinerules/docs/project_wordcloud/operator-manual/                ← 신규 생성
.clinerules/docs/project_wordcloud/operator-manual/DEVELOPMENT.md  ← 신규 작성
.clinerules/docs/project_wordcloud/operator-manual/DEVELOPMENT/    ← 신규 생성
.clinerules/docs/project_wordcloud/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md ← 복사
.clinerules/docs/project_wordcloud/operator-manual/developer-manual/ ← 이전
.clinerules/docs/project_wordcloud/operator-manual/developer-manual/00-index.md
.clinerules/docs/project_wordcloud/operator-manual/developer-manual/01-architecture.md
... (02~09)
```

**작업**:
1. `docs/project_wordcloud/operator-manual/` 생성
2. `docs/project_wordcloud/operator-manual/DEVELOPMENT/` 생성
3. `docs/msys/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md` → `docs/project_wordcloud/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md` 복사
4. `docs/msys/operator-manual/developer-manual/` 전체 → `docs/project_wordcloud/operator-manual/developer-manual/`로 이동 (cut)
5. `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` 신규 작성 (wordcloud 운영자 메뉴얼 작성 가이드)

### Phase 2: 코어 규칙 msys→wordcloud 전환 (7 파일)

| 파일 | 수정 방식 |
|------|----------|
| `core/00-core.md:20` | `docs/msys/README.md` → `docs/project_wordcloud/README.md` |
| `core/00-core.md:42` | `docs/msys/operator-manual/DEVELOPMENT.md` → `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` + DEVELOPMENT/00-a4-authoring-guide.md 경로도 갱신 |
| `core/02.documentation.md:61` | `docs/msys/operator-manual/DEVELOPMENT.md` → `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` |
| `core/06.git-rules.md:148~163` | **"msys.zip 자동 생성 (pre-commit hook)" 섹션 통째로 삭제** — 공통 규칙에 프로젝트 전용 빌드 로직 부적절 |
| `core/06.git-rules.md:537` | `root 저장소(msys)` → `root 저장소` |
| `core/14.comment-log-removal.md:11` | `msys_venv/` → `venv/` |
| `core/14.comment-log-removal.md:73` | `from msys_app import create_app` → `from web.app import create_app` (wordcloud 기준) |
| `core/14.comment-log-removal.md:83~90` | msys_venv 경로 → wordcloud venv 경로 |
| `core/16-report-writing.md:19` | `docs/msys/templates/data_report.md` 행 삭제 (파일 자체 존재하지 않음) |

### Phase 3: 검증 시나리오 삭제

| 파일 | 처리 |
|------|------|
| `.clinerules/docs/verification/scenarios/02-time-handling-workflow.md` | 삭제 |
| `.clinerules/docs/verification/scenarios/03-setting-popup-scenario.md` | 삭제 |
| `.clinerules/docs/verification/scenarios/04-user-statistic-scenario.md` | 삭제 |

### Phase 4: CR 보고서 msys 전용 건 삭제

`docs/cr/` 폴더에서 `레파지토리` 필드에 `msys` 또는 `D:\dev\msys`가 포함된 파일 전수 삭제.

### Phase 5: 검증 시나리오 전처리 삭제

`docs/scenario-test_guidelines.md`에서 msys 전용 참조 제거 또는 해당 파일 삭제 검토.

---

## 4. 변경 파일 목록

### Phase 1 — 신규 생성/이동

| 파일 | 변경 유형 | 현재 | 변경 |
|------|-----------|------|------|
| `docs/project_wordcloud/operator-manual/` | 신규 | 없음 | 디렉토리 생성 |
| `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` | 신규 | 없음 | wordcloud 운영자 메뉴얼 작성 가이드 |
| `docs/project_wordcloud/operator-manual/DEVELOPMENT/` | 신규 | 없음 | 디렉토리 생성 |
| `docs/project_wordcloud/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md` | 복사 | `docs/msys/.../00-a4-authoring-guide.md` | wordcloud용 복사 |
| `docs/project_wordcloud/operator-manual/developer-manual/` | 이동 | `docs/msys/.../developer-manual/` | 10 파일 이동 |

### Phase 2 — 수정

| 파일 | 변경 유형 |
|------|-----------|
| `core/00-core.md` | 수정 (2행 경로 갱신) |
| `core/02.documentation.md` | 수정 (1행 경로 갱신) |
| `core/06.git-rules.md` | 수정 (섹션 삭제 + 1행 수정) |
| `core/14.comment-log-removal.md` | 수정 (3곳 경로 갱신) |
| `core/16-report-writing.md` | 수정 (1행 삭제) |

### Phase 3 — 삭제

| 파일 | 변경 유형 |
|------|-----------|
| `verification/scenarios/02-time-handling-workflow.md` | 삭제 |
| `verification/scenarios/03-setting-popup-scenario.md` | 삭제 |
| `verification/scenarios/04-user-statistic-scenario.md` | 삭제 |

### Phase 4 — 삭제

| 파일 | 변경 유형 |
|------|-----------|
| `docs/cr/REQ-*.md` (msys 전용 건) | 삭제 |

---

## 5. 영향도 분석

| 범위 | 영향 |
|------|------|
| 코어 규칙 | 5개 파일 수정 — 향후 모든 작업에 적용되는 공통 규칙 |
| wordcloud 프로젝트 문서 | operator-manual 디렉토리 신설 — 운영자 메뉴얼 작성 기반 마련 |
| 검증 시나리오 | 3개 파일 삭제 — msys 전용 시나리오 제거 |
| CR 보고서 | msys 전용 건 삭제 — 과거 이력 정리 |
| docs/msys | developer-manual 하위 10 파일만 이동 후 제거 (msys 운영자 메뉴얼 구조는 보존) |

---

## 6. 테스트/검증 계획

| # | 검증 항목 | 방법 |
|---|-----------|------|
| 1 | `core/00-core.md`에 msys 잔재 없음 | `grep -i msys core/00-core.md` → 0건 |
| 2 | `core/02.documentation.md`에 msys 잔재 없음 | `grep -i msys core/02.documentation.md` → 0건 |
| 3 | `core/06.git-rules.md`에 msys 잔재 없음 | `grep -i msys core/06.git-rules.md` → 0건 |
| 4 | `core/14.comment-log-removal.md`에 msys 잔재 없음 | `grep -i msys core/14.comment-log-removal.md` → 0건 |
| 5 | `docs/project_wordcloud/operator-manual/developer-manual/` 10 파일 전부 존재 | glob 확인 |
| 6 | `docs/msys/operator-manual/developer-manual/` 비어 있음 | glob 확인 → 0 파일 |
| 7 | 삭제된 검증 시나리오 3개 없음 | glob 확인 → 0 파일 |
| 8 | msys 전용 CR 보고서 삭제됨 | grep으로 `레파지토리.*msys` 검색 → 0건 |

---

## 7. 리스크 및 제약

| 리스크 | 대응 |
|--------|------|
| 검증 시나리오 삭제 후 wordcloud 전용 시나리오 누락 | wordcloud 전용 시나리오는 `docs/project_wordcloud/` 하위에 별도 관리 (현재 `scenario-test_project.md` 존재) |
| CR 보고서 과거 이력 유실 | Git 히스토리에 보존 — 필요 시 복구 가능 |
| `docs/msys/` 내 잔여 msys 참조 | msys 프로젝트 전용이므로 정상 — 추가 정리 불필요 |
| 16-report-writing.md의 data_report 행 삭제 후 보고서 작성 경로 부재 | 해당 보고서 유형은 UI 페이지로 구현 (문서 아님) — 행 자체가 부정확했음 |

---

## 실행 로그(수행일·작업자)

- **수행일**: 2026-07-23
- **작업자**: opencode (AI)

### Phase 1 — 디렉토리 구조 교정
- `docs/project_wordcloud/operator-manual/` 생성
- `docs/project_wordcloud/operator-manual/DEVELOPMENT/` 생성
- `docs/msys/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md` → wordcloud로 복사
- `docs/msys/operator-manual/developer-manual/` (10 md + build/ + integrated-manual.* + MANIFEST.txt) → wordcloud로 이동 후 msys 원본 삭제
- `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` 신규 작성

### Phase 2 — 코어 규칙 전환
- `core/00-core.md` 2행 수정 (wordcloud→project_wordcloud 경로)
- `core/00-core.md` 1행 수정 (운영자 메뉴얼→project_wordcloud 경로)
- `core/02.documentation.md` 1행 수정
- `core/06.git-rules.md` "빌드 자동화 규칙" 섹션 통째로 삭제 (16줄)
- `core/06.git-rules.md` 1행 수정 (root 저장소)
- `core/14.comment-log-removal.md` 3곳 수정 (venv, web.app, 경로)
- `core/16-report-writing.md` 1행 수정 (data_report 참조 제거)

### Phase 3 — 검증 시나리오 삭제
- `verification/scenarios/02-time-handling-workflow.md` 삭제
- `verification/scenarios/03-setting-popup-scenario.md` 삭제
- `verification/scenarios/04-user-statistic-scenario.md` 삭제
- `docs/scenario-test_guidelines.md` 삭제

### Phase 4 — CR 보고서 삭제
- msys 전용 CR 보고서 35건 삭제 (`docs/cr/`)

### 검증 결과
- `core/*.md` msys 참조: 0건 ✅
- `docs/project_wordcloud/*.md` msys 참조: 0건 ✅
- `docs/project_wordcloud/operator-manual/developer-manual/` 파일 수: 11개 ✅
- `docs/msys/operator-manual/developer-manual/` 존재 여부: False ✅
- 검증 시나리오 잔존: 0건 ✅
- msys CR 보고서 잔존: 0건 ✅
