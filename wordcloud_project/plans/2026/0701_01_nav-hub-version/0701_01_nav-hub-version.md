# 계획서 — Nav 메뉴 통합·접기 + 버전 배지

> 상태: DN | 작성일: 2026-07-01
> 작업 유형: B (기능 개선/신규 기능) + UI 변경(04.design-change)
> 선행: `plans/2026/0630_01_nav-restructure`(Nav 워크플로 재구성 — Todo). 본 계획서는 그 방향을 **탭 허브 병합 + 섹션 접기 + 버전 배지**로 구체화한다.

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-01 | 최초 작성 | Nav 2쌍 탭 병합 + 섹션 접기(기억) + 버전 배지 |
| 2026-07-01 | §4.1·§5·§6·§8 | [검토반영] JS 충돌 게이트 구체화, 컨텍스트 실측 강화, 구 경로 grep 범위 명시, active 기본 포함 권장, 배지 반응형·관리자 제한 추가 |
| 2026-07-01 | §4.1·§4.3·§5·§8 | [코드대조 정정] ①관리자 판정은 `current_user.is_admin`(부재)이 아니라 `session['admin_logged_in']`/`_is_admin_session`(실제) ②`stopwords`/`profanity_list`/`acquired_data`는 컨텍스트 0개 → 변수 충돌 불가, 접두어 방어 불요 ③이중 해시(`#a#b`)는 URL상 불가능하므로 리스크 삭제 |
| 2026-07-01 | §4.1·§4.3·§4.5·§5·§8 | [재검토반영] ①모바일 nav 접힘+배지 가려짐 시나리오 ②테스트 라우트 컨텍스트 확인 필요 ③partial 추출 시 settings.html content/scripts 구조 사전 확인 ④`gen_version.py` 모델 해시 전략 문서화 |
| 2026-07-01 | §4.3 | [코드대조 정정] 모델 해시 대상 `pytorch_model.bin`(부재) → 실측 파일 `model.safetensors`(498MB). 폴더 실파일 6개 확인 |
| 2026-07-01 | §4.3 | [전제 정정] 시스템은 내부망 데스크톱 전용 → 모바일 반응형 리스크 삭제(범위 밖) |
| 2026-07-01 | 전면 | 구현 완료: partial 4추출 · hub 2생성 · nav 접기+active+배지 · 라우트 리다이렉트 · version_service · gen_version |

---

## 1. 배경 및 목적

- 현재 Nav는 5개 섹션·18개 항목으로 밀도가 높아, 자주 안 쓰는 항목이 시야를 차지한다.
- 배포 후 **"개선 버전이 정상 적용됐는지"** 를 화면에서 즉시 확인할 방법이 없다(버전 문자열 부재 — `settings.py`/`app.py` grep 결과 0건).
- 목적:
  1. 관련 페이지를 **탭 허브로 병합**해 메뉴 수를 줄인다.
  2. 섹션 제목 클릭으로 **접기/펼치기 + 상태 기억**(재방문 시 유지).
  3. Nav에 **버전 배지**를 상시 노출해 시스템·모델 버전과 **로드 정상 여부**를 한눈에 본다.

## 2. 요구사항

**사용자 명시 요구:**
1. **주기능** — `감정어 설정`(`/settings`) + `불용어 관리`(`/stopwords`)를 **한 메뉴 + 탭**으로. **감정어 설정이 먼저** 출력.
2. **결과물** — `습득 데이터`(`/acquired-data`) + `욕설 리스트`(`/profanity-list`)를 **한 메뉴 + 탭**으로. **욕설 리스트가 먼저** 출력.
3. Nav **상단 또는 하단**에 버전 배지 — 즉시 확인 가능하게.
4. 섹션 **제목 클릭 → 접기** + 그 상태를 **기억**.
5. 메뉴 가짓수 축소.

**제안 추가(사용자 "좋은 아이디어 추가" 요청 반영 — §4.5에서 선택):**
6. 현재 페이지 Nav 항목 **active 하이라이트**(접기와 함께 길찾기 개선) — **§4.5-6에 두고 선택으로 명시했으나 접기와 시너지가 크므로 구현 시 기본 포함을 강력 권장**(§8 참조).
7. **테스트 섹션**(`감정 테스트`+`욕설 테스트`)도 동일 탭 패턴으로 병합(일관성).
8. 탭 **딥링크**(`#tab` 해시)로 특정 탭 직접 열기 + 병합 후 구 경로 **리다이렉트**(북마크 보존).
9. 버전 배지 **클릭 시 상세 모달**(커밋·학습일·모델 로드 상태·무결성 검사 버튼).

## 3. 현재 시스템 분석 (코드 검증 완료)

**Nav 구조** — `web/templates/base.html:164-209` (`<nav>` 내 `.nav-section` 5개):

| 섹션 | 항목(경로) |
|------|-----------|
| 📋 주기능 | 메타데이터 생성(`/metadata_batch`) · 판정 결과 반영(`/judgment_apply`) · 그룹 검토(`/group-review`) · 그룹분석(`/perspective_test`) · **설정(`/settings`)** · **불용어 관리(`/stopwords`)** |
| 📦 결과물 | 저장 갤러리(`/deploy-gallery`) · **욕설 리스트(`/profanity-list`)** · **습득 데이터(`/acquired-data`)** · 배치 관리(`/admin/batch-management`) |
| ✍️ 수동 조작 | 입력(`/`) · 반어법 분석(`/sarcasm`) · 워드클라우드(`/wordcloud`) · 애니메이션(`/wordcloud-preview`) |
| 🧪 테스트 | 감정 테스트(`/sentiment-test`) · 욕설 테스트(`/profanity-test`) |
| 👨‍💼 관리자 | 관리자 대시보드(`/admin/dashboard`) · 계획 현황(`/admin/plans`) |

**병합 대상 라우트** — 전부 `src/routes/ui_routes.py`:
- `settings()` (16) · `stopwords()` (121) · `profanity_list()` (139) · `acquired_data()` (163)

**병합 대상 템플릿** — 4개 모두 `{% extends "base.html" %}`(독립 전체 페이지). → 탭 병합 시 각 페이지의 `{% block content %}`를 **partial로 추출**하고 `{% block scripts %}` JS를 허브에서 **함께 로드**해야 한다(핵심 난점: ID/전역함수 충돌 점검 필요).

**모델 상태 노출원** — `src/modules/hr_sentiment.py`: 전역 `_instance`·`_load_failed`, 토글 `USE_HR_SENTIMENT_MODEL`, `os.path.isdir(HR_SENTIMENT_MODEL_PATH)` 체크(54행), 실패 시 규칙 폴백. → 배지의 "✓ 로드 / ⚠️ 폴백" 판정에 그대로 사용.

**버전 문자열** — 현재 없음(신규 생성 필요). 모델 경로 `HR_SENTIMENT_MODEL_PATH = .../model/hr_sentiment_finetuned` (`settings.py:26`).

**nav.css** — `.nav-section`/`.nav-section-title` 스타일 존재(118·128행), collapse/active 로직 **없음**(신규).

## 4. 구현 상세

### 4.1 탭 허브 병합 (요구 1·2)

**병합 방식 — partial 추출 + include (권장):**
1. 각 페이지 본문을 partial로 이동:
   - `web/templates/partials/_settings_body.html` ← `settings.html`의 content
   - `web/templates/partials/_stopwords_body.html` ← `stopwords.html`의 content
   - `web/templates/partials/_profanity_body.html` ← `profanity_list.html`의 content
   - `web/templates/partials/_acquired_body.html` ← `acquired_data.html`의 content
2. 허브 페이지(각각 `extends base.html`) 신규:
   - `settings_hub.html` — 탭 바 `[감정어 설정 | 불용어 관리]`, 기본 활성 = **감정어 설정**. 두 partial을 `{% include %}`.
   - `results_hub.html` — 탭 바 `[욕설 리스트 | 습득 데이터]`, 기본 활성 = **욕설 리스트**.
3. 각 페이지 `{% block scripts %}` JS를 허브 scripts로 합침. **충돌 점검 필수**(같은 `id`/전역 `function`명이 두 partial에 동시 존재하는지 grep). 충돌 시 네임스페이스/접두어로 격리.
   - **grep 게이트 패턴 예시:** `^(function\s+|const\s+\w+\s*=|let\s+\w+\s*=)` / `\bid="[^"]*"` / `\baddEventListener\b` — 양쪽 partial 비교 후 공통명 발견 시 접두어(`settings_`/`stopwords_`) 부여.
   - **충돌 검증 시나리오(§7-5 보강):** 콘솔 에러 0건 + 각 탭의 버튼(추가/삭제/저장) 클릭 시 의도한 fetch 요청이 전송되는지 Network 탭 확인.
4. 탭 전환은 **CSS 표시 토글**(패널 둘 다 DOM에 있고 `display` 스위치) — 각 페이지 JS가 로드 시 1회 초기화되어 재실행 문제 없음.

**라우트(백엔드) — `src/routes/ui_routes.py`:**
- `settings()` → `settings_hub.html` 렌더(기존 컨텍스트 유지 + stopwords 컨텍스트 병합). `stopwords()` → `redirect('/settings#stopwords', 302)`.
- `profanity_list()` → `results_hub.html` 렌더(+ acquired 컨텍스트 병합). `acquired_data()` → `redirect('/profanity-list#acquired', 302)`.
- **컨텍스트 실측 완료(코드 확인):** `settings()`만 4개 변수(`emotions`·`config`·`emotions_json`·`config_json`)를 전달하고, `stopwords()`·`profanity_list()`·`acquired_data()`는 **컨텍스트 0개**(데이터는 페이지 JS의 fetch로 로드). → 병합 쌍 사이 **변수명 충돌 불가**. `settings_hub`엔 settings 4개만 그대로 전달(stopwords 추가분 없음), `results_hub`엔 전달 컨텍스트 없음. 접두어 방어 불요.

**프론트(딥링크):** 허브 로드 시 `location.hash`(`#stopwords`/`#acquired`) 있으면 해당 탭 활성, 없으면 기본 탭.

### 4.2 섹션 접기 + 상태 기억 (요구 4)

- `base.html`: `.nav-section-title`에 캐럿(▸/▾) 추가 + `role="button"`. 클릭 시 해당 섹션 `.collapsed` 토글.
- `nav.css`: `.nav-section.collapsed a { display:none; }` + 캐럿 회전.
- JS(base.html): 토글 시 `localStorage['navCollapse:<섹션키>'] = '1'|'0'` 저장, `DOMContentLoaded`에서 복원. 섹션키 = 섹션 제목 텍스트(이모지 제외) 슬러그.

### 4.3 버전 배지 (요구 3·9)

**백엔드(신규):**
- `wordcloud_project/VERSION.json` — 빌드 시 각인:
  ```json
  { "system_version": "1.1.0", "model_version": "hr-sentiment-v1.0",
    "model_sha256": "a3f9c1e8...", "model_trained": "2026-07-01",
    "source_commit": "0339e3d", "build_date": "2026-07-01T14:41:00Z" }
  ```
- `src/services/version_service.py`(**신규**) — `get_version_info()`:
  - `VERSION.json` 읽기(없으면 `system_version="dev"` 폴백).
  - 런타임 상태: `os.path.isdir(HR_SENTIMENT_MODEL_PATH)` + `hr_sentiment.model_status()`(신규, 아래) → `{loaded|fallback}`.
  - **무결성 미포함**(페이지 로드 시 477MB 해시 금지) — 선언 버전 + 로드 상태만 반환.
- `src/modules/hr_sentiment.py`(**함수 추가**) — `model_status()`: 전역 `_instance`/`_load_failed` + `isdir` 읽어 `{enabled, dir_exists, loaded, load_failed}` 반환(무거운 로드 강제 안 함).
- `web/app.py` — **context processor** 등록: `{'version_info': get_version_info()}` → 모든 페이지 base.html에서 사용(페이지별 라우트 불요). 앱 기동 1회 캐시.
- 라우트 `GET /api/version`(상세 모달용) + `GET /api/version/verify`(**on-demand** 설치 모델 재해시 → 선언값 대조, 무결성 판정). → `perspective_routes.py` 또는 신규 `version_routes.py`.

**프론트(배지):**
- `base.html` `<nav>` **하단 sticky**에 배지: `⚙ v{system_version} · 모델 {✓ 로드 | ⚠️ 폴백}`.
- **모바일 반응형 불요:** 본 시스템은 **내부망 데스크톱 전용**(모바일 접속 없음). 반응형/뷰포트 대응은 범위 밖. 단, 섹션 다수 접힘으로 nav가 짧아져도 배지가 항상 보이도록 `<nav>` 하단 sticky 고정만 확인.
- 클릭 → 상세 모달(시스템/모델 버전·지문·학습일·커밋·로드 상태·`[무결성 검사]` 버튼 → `/api/version/verify`).
- **무결성 검사 버튼 — 관리자 제한:** 본 프로젝트는 Flask-Login 미사용. `session.get('admin_logged_in')`(app.py:79에서 컨텍스트 변수 `_is_admin_session`으로 노출, perspective_routes.py `_is_admin()` 헬퍼) 참일 때만 버튼 노출. 템플릿에서 `{% if _is_admin_session %}`, `/api/version/verify`도 서버측 `_is_admin()` 게이트로 이중 차단.

**빌드 각인:** `build_deploy.ps1`은 **AI 수정 금지**(deployment.md). → 독립 스크립트 `scripts/gen_version.py`(**신규**)로 `VERSION.json` 생성(모델 해시+`git rev-parse --short`+timestamp).
- **모델 해시 전략:** 폴더 실측 결과 파일은 `model.safetensors`(498 MB, 단일 최대)·`config.json`·`tokenizer.json`·`tokenizer_config.json`·`special_tokens_map.json`·`vocab.txt` 6개 (**`pytorch_model.bin` 없음 — safetensors 포맷**). 전체 해시는 비용 큼 → `HR_SENTIMENT_MODEL_PATH` 내 **`model.safetensors`만 SHA-256 해시**. 설정·토크나이저 파일은 `model_trained` 날짜로 대체(변경 시 날짜 갱신). 해시 대상 경로는 `settings.HR_SENTIMENT_MODEL_PATH` 참조.
- **실행 시점:** 배포 패키징 직전 수동 실행(`python scripts/gen_version.py`) 또는 CI 파이프라인 스텝으로 등록. `build_deploy.ps1` 내에 `Invoke-Expression`으로 끼우지 말고 **배포 전 별도 절차**로 문서화(deployment.md 갱신 시 §버전 각인 항목 추가).

### 4.4 반영 후 Nav 최종 형태

| 섹션 | 변경 후(항목 수) |
|------|-----------------|
| 📋 주기능 | 메타데이터 생성 · 판정 결과 반영 · 그룹 검토 · 그룹분석 · **⚙️ 설정**(탭: 감정어 설정▸불용어) → **6→5** |
| 📦 결과물 | 저장 갤러리 · **🚨 리스트·데이터**(탭: 욕설▸습득) · 배치 관리 → **4→3** |
| ✍️ 수동 조작 | 변경 없음(선택 §4.5-8) |
| 🧪 테스트 | 선택 §4.5-7 적용 시 **2→1** |
| 👨‍💼 관리자 | 변경 없음 |
| (하단) | **버전 배지**(신규) |

### 4.5 선택 항목(사용자 승인 시)

> **권장:** (6) active 하이라이트는 접기와 시너지가 크므로 최초 구현 시 기본 포함을 권장하며, 아래 선택 목록에도 남겨둔다(사용자 최종 결정).

- (6) active 하이라이트 — `.nav-section a.active` 스타일 + 현재 경로 매칭 JS(base.html). 접힌 섹션 내 항목이 active면 해당 섹션 자동 펼침.
- (7) 테스트 탭 병합(감정+욕설) — 패턴 일관, 2→1. `sentiment_test`/`profanity_test` 라우트·템플릿도 동일 partial 추출 패턴 적용. `test_hub.html` 신규.
  - **사전 확인 필요:** `sentiment_test`/`profanity_test` 라우트의 `render_template()` 컨텍스트 변수 존재 여부 확인. settings.html 패턴과 달라 0개일 가능성 높음(데이터는 JS fetch로 로드) → 확인 후 §4.1과 동일 결론이면 컨텍스트 병합 불요.
- (8) 수동 조작: 워드클라우드+애니메이션 탭 병합.

## 5. 구현 순서

| 순서 | 작업 | 의존 |
|------|------|------|
| 1 | 컨텍스트 실측 **완료**: `settings()`=4개 변수, 나머지 3개=0개(§4.1 참조). 충돌 없음 → `settings_hub`엔 settings 컨텍스트 그대로, `results_hub`엔 없음. **partial 추출 전 settings.html 구조 확인 필요** — `{% block content %}` 단일 블록인지 + `{% block scripts %}`에 전역함수/이벤트리스너가 어떻게 구성됐는지 미리 파악(JS 격리 난이도 추정용). 이후 partial 4개 추출 | — |
| 2 | `settings_hub.html`/`results_hub.html` 생성 + **JS 충돌 점검 게이트** — 양쪽 partial에서 `id=`, `function `, `const `, `addEventListener` 공유 명칭 grep. 충돌 시 `settings_`/`stopwords_` 접두어로 격리. 격리 후에도 콘솔 에러 0 + 각 탭 버튼 정상 동작을 확인 | 1 |
| 3 | `ui_routes.py` 허브 렌더 + 구 경로 리다이렉트 | 2 |
| 4 | 섹션 접기 CSS/JS + localStorage 복원 | — |
| 5 | `version_service.py`+`hr_sentiment.model_status()`+context processor+`/api/version[/verify]` | — |
| 6 | base.html 버전 배지 + 상세 모달 | 5 |
| 7 | `scripts/gen_version.py` + VERSION.json 생성 | 5 |
| 8 | (선택) §4.5 | 2~4 |

## 6. 영향도 분석

**변경(수정):**
- `web/templates/base.html` — Nav(배지·접기·탭 진입점), scripts
- `web/static/css/nav.css` — collapse/active/배지 스타일
- `src/routes/ui_routes.py` — 4개 함수(허브 렌더 + 리다이렉트)
- `src/modules/hr_sentiment.py` — `model_status()` 추가
- `web/app.py` — context processor 등록

**신규:**
- `web/templates/partials/_{settings,stopwords,profanity,acquired}_body.html`
- `web/templates/{settings_hub,results_hub}.html`
- `src/services/version_service.py` · `scripts/gen_version.py` · `VERSION.json`
- (선택) `src/routes/version_routes.py`

**영향 범위:** Nav는 전 페이지 공유(base.html) → 회귀 표면 넓음. 구 경로(`/stopwords`·`/acquired-data`)를 참조하는 **다른 링크 존재 여부 전수 grep 필수** — 검색 패턴: `href=".*(stopwords|acquired-data)"`, `url_for.*(stopwords|acquired_data)` 등 라우트명(`stopwords`, `acquired_data`)도 포함. 발견 시 리다이렉트로 흡수되나 #해시 앵커(`/stopwords#...`) 참조는 리다이렉트 후 해시가 유지되는지 별도 확인 필요.

## 7. 테스트/검증 계획 (시나리오)

1. `/settings` 진입 → 감정어 설정 탭 먼저 활성, 불용어 탭 클릭 시 기존 불용어 관리 기능 정상 동작(추가/삭제/저장).
2. `/stopwords` 진입 → `/settings#stopwords`로 리다이렉트 + 불용어 탭 활성.
3. `/profanity-list` 진입 → 욕설 리스트 탭 먼저, 습득 데이터 탭 정상.
4. `/acquired-data` → `/profanity-list#acquired` 리다이렉트.
5. 병합 페이지에서 두 원본 기능의 JS 충돌 無(콘솔 에러 0, 버튼/이벤트 정상).
6. 섹션 제목 클릭 → 접힘, 새로고침·타 페이지 이동 후에도 상태 유지(localStorage).
7. 버전 배지: 모델 폴더 있음 → `✓ 로드`, 폴더 rename 후 → `⚠️ 폴백` 표시. 배지 클릭 모달 값 정상.
8. 무결성 검사 버튼 → 설치 모델 해시=VERSION.json 값이면 일치, 다른 모델로 바꾸면 불일치.
9. `gen_version.py` 실행 → VERSION.json에 실제 모델 해시·커밋 기록.

> DN 조건: 위 1~9를 **브라우저 실동작**으로 확인 후에만 Done. 그 전 Pre-Done + 체크리스트.

## 8. 리스크 및 제약

- **JS 충돌(최대 위험)**: 두 독립 페이지 병합 시 중복 `id`/전역 함수. → §5-2 충돌 점검(grep 게이트 패턴: `^(function\s+|const\s+\w+\s*=)` / `\bid="`)을 게이트로. 격리 후 콘솔 에러 0건 + 각 탭 버튼 fetch 정상 전송 확인 필수.
- **컨텍스트 누락**: 실측 결과 `settings()`만 4개 변수, 나머지 3개는 0개(§4.1) → 병합 시 누락·충돌 위험 없음. `settings_hub`에 settings 컨텍스트만 유지하면 됨.
- **Nav 전역 영향**: base.html 변경은 전 페이지 회귀. → 시나리오 6·전 페이지 스모크.
- **build_deploy.ps1 수정 금지**(deployment.md) → 버전 각인은 독립 `gen_version.py`로만. 실행 시점은 배포 전 별도 절차로 문서화.
- **무결성 해시 비용**: 477MB 해시는 on-demand 버튼만(페이지 로드 시 금지). 버튼은 `_is_admin_session`(session 기반)일 때만 노출 + 서버측 `_is_admin()` 게이트.
- **구 경로 해시 앵커:** URL 프래그먼트는 `#` 하나뿐이라 `#a#b` 이중 해시는 성립 불가 — 별도 위험 아님. 구 경로 3개(stopwords/profanity/acquired)는 컨텍스트 0개·정적 페이지라 인바운드 `#앵커` 참조가 사실상 없음. §6 grep으로 실참조 0건 확인만 하면 됨(발견 시 302 리다이렉트가 흡수).
- 서버 무단 실행 금지 — 검증은 사용자 실행 안내로.
