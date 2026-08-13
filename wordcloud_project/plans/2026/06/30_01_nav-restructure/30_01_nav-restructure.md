# 계획서 — Nav 메뉴 전수 조사 및 워크플로 중심 재구성

> 상태: Todo | 작성일: 2026-06-30
> 작업 유형: B (기능 개선/신규 기능)
> 선행: `plans/2026/0701_01_nav-hub-version`(DN·커밋 `6e296bb`) — **탭 허브 병합·섹션 접기·버전 배지는 이미 구현·반영됨.** 본 계획서는 그 결과 위에 **리베이스**되어, 잔여 고유 범위(`/batch-monitor`·`/judgment-extract` 신규 페이지 + 파이프라인 순번화)만 다룬다.

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-30 | 전체 | 최초 작성 |
| 2026-07-01 | §2.1·§3.1·§3.2·§7 + 신설 §0 | [리베이스·코드대조] 후속 `0701_01`(DN)이 탭 허브 병합·접기·버전 배지를 이미 구현 → 해당 제안 삭제. 범위를 신규 2페이지+순번화로 축소. §2.1 현 nav 실측 갱신(L186-226), §7 관리자 표시는 신규 JS 불요(`_is_admin_session` 기존 존재)로 정정. CSS 클래스명 실측 반영(`.collapsed`/`.active`/`.version-badge`) 및 지침 `06-navigation.md` 미갱신 지적 |
| 2026-07-01 | §0·§2.2·§3.1·§3.2·§3.4·§4·§5·§7 | [코드대조 검토] 순번 표시 방식 CSS counter로 전환(HTML 이모지→CSS `counter-increment`). `nav.css`에 counter 규칙 추가로 영향도 변경. `judgment_extract.html` 배치 소스·마진 옵션 명세 구체화. `batch_monitor.html` 공통 JS 모듈 분리 권장. 관리자 체크 리스크 보강 |
| 2026-07-01 | §3.2 | [재검토·CSS 정정] `content` 이스케이프 버그 수정 — `"\fe0f⃣\0020"`(무효, `\u`는 CSS 이스케이프 아님)→`"\fe0f\20e3\0020"`. 키캡 렌더 근거·아이콘 중복(선두 이모지+순번) 참고 주석 추가 |

## 0. 리베이스 요약 (2026-07-01 재검토)

본 계획서 작성(06-30) 다음날 `0701_01`이 아래를 **이미 구현·머지**(커밋 `6e296bb`, `base.html`/`nav.css` 실측 확인)했다. 중복 실행 금지:

- ✅ **탭 허브 병합**: `설정`+`불용어`→허브, `욕설 리스트`+`습득 데이터`→`🚨 리스트·데이터` 허브. → 본 계획서 §3.1의 "코퍼스 데이터/욕설 리스트/설정/불용어 개별 나열"은 **폐기**(그대로 하면 병합 UI 회귀).
- ✅ **섹션 접기 + 상태 기억**: `nav.css`에 `.nav-section-title .collapse-caret` / `.nav-section.collapsed > a { display:none }` 존재. → 본 계획서 §3.2의 `.collapsible` 신규 제안은 **폐기**(이미 `.collapsed`로 존재).
- ✅ **버전 배지 / active 하이라이트**: `nav.css`에 `.version-badge`, `.nav-section a.active` 존재.

**→ 본 계획서의 잔여 고유 범위(유효):**
1. `/batch-monitor` 신규 페이지 — 배치 진행/재개 (API는 있으나 UI 없음: `batch_routes.py:134` `work-orders` 등 실측 확인).
2. `/judgment-extract` 신규 페이지 — 판정 패킷 추출 (API POST 전용 + admin 필수, UI 없음: `perspective_routes.py:617` 실측 확인).
3. 파이프라인 항목 **워크플로 순번화**(CSS counter 자동 번호) — 기존 병합 nav HTML을 건드리지 않고 순서만 부여.

## 1. 배경 및 목적

Nav의 밀도·병합은 `0701_01`에서 해소됐으나, **파이프라인 진입점 2개가 여전히 누락**돼 사용자 워크플로가 끊긴다:

- **핵심 기능 진입점 부재(잔여)**: 판정 패킷 추출 UI(`/judgment/extract` — POST 전용), 배치 모니터링 페이지가 네비에 없음
- **워크플로 순서 불명**: 메타데이터 생성→판정 추출→판정 반영→그룹 검토가 한 파이프라인인데 순서 힌트가 없어 신규 사용자가 진입 지점을 못 찾음

> 참고(해소됨): 용어 불일치("습득 데이터"), 관리자 메뉴 혼재, 밀도 문제는 `0701_01`의 허브 병합·접기에서 상당 부분 처리됨 → §0 참조.

**목표**: 누락된 UI 진입점 2개(`/batch-monitor`·`/judgment-extract`)를 추가하고, 기존 병합 nav의 파이프라인 항목에 CSS counter 워크플로 순번을 부여한다. **기존 병합 구조는 유지**한다.

## 2. 현재 시스템 분석

### 2.1 현재 Nav 구조 (base.html:186-226 — `0701_01` 반영 후 실측)

> ⚠️ 최초 작성 시 기재했던 `base.html:164-206`의 5개 평면 섹션은 **낡음**. `0701_01` 병합·접기 반영 후 실제 구조는 아래와 같다(각 `.nav-section-title`에 `.collapse-caret` 접기 캐럿 존재).

```html
<!-- 📋 주기능 (data-nav-section="main") -->
📄 메타데이터 생성     → /metadata_batch
📥 판정 결과 반영      → /judgment_apply
🏷️ 그룹 검토           → /group-review
📊 그룹분석            → /perspective_test
⚙️ 설정 ▸탭            → /settings          (설정+불용어 허브)

<!-- 📦 결과물 (data-nav-section="results") -->
📁 저장 갤러리         → /deploy-gallery
🚨 리스트·데이터 ▸탭    → /profanity-list    (욕설 리스트+습득 데이터 허브)
📝 배치 관리           → /admin/batch-management

<!-- ✍️ 수동 조작 (data-nav-section="manual") -->
💬 입력                → /
💭 반어법 분석          → /sarcasm
🎨 워드클라우드        → /wordcloud
🎬 애니메이션 (WC)     → /wordcloud-preview

<!-- 🧪 테스트 (data-nav-section="test") -->
😊 감정 테스트          → /sentiment-test
🔍 욕설 테스트          → /profanity-test

<!-- 👨‍💼 관리자 (data-nav-section="admin") -->
🔐 관리자 대시보드     → /admin/dashboard
📋 계획 현황           → /admin/plans
```

- `/stopwords`·`/acquired-data`는 nav 항목에서 제거되고 각 허브 탭으로 흡수됨(라우트는 리다이렉트로 유지).

### 2.2 관련 파일/함수

- **템플릿**: `web/templates/base.html` (nav HTML, L186-226)
- **스타일**: `web/static/css/nav.css` (네비 스타일 전체 — counter 규칙 추가 예정)
- **UI 라우트**: `src/routes/ui_routes.py` (페이지 라우트 24개)
- **존재하나 네비 미등록 페이지**: `/preprocess`(preprocess.html), `/metadata`(metadata.html), `/wordcloud_debug`(wordcloud_debug.html)
- **API 전용이나 UI 부재**: `POST /api/perspective/judgment/extract`(admin 필수, perspective_routes.py:617), 배치 모니터링 SSE `/api/batch/events`(batch_routes.py:104)
- **작업서 API**: `GET /api/batch/work-orders`(batch_routes.py:134, batch_work_order_service.py → SQLite)

### 2.3 문제점 상세

| 문제 | 코드 실측 |
|------|-----------|
| 워크플로 단절 | metadata_batch→judgment_apply는 4단계 룰(extract→judge→insert)인데 "주기능"에 평면 배치 |
| 용어 불일치 | acquired_data.html 제목="습득한 데이터", nav="습득 데이터", RUNBOOK/RREADME="코퍼스 데이터" |
| 관리자 혼재 | batch-management는 admin_required(admin_routes.py:57)인데 "결과물" 섹션에 위치 |
| 누락 진입점 | judgment/extract API(perspective_routes.py:617)는 POST 전용 — UI 페이지 없음 |
| 단일 메타데이터 중복 | `/metadata`(metadata.html)는 배치의 1건 특례 — `/metadata_batch`로 대체 가능 |

## 3. 구현 상세

### 3.1 프론트엔드: Nav HTML 최소 삽입 (base.html) + CSS Counter 순번

> **원칙**: `0701_01` 병합 nav를 **그대로 두고**, 📋 주기능 섹션에 신규 2항목을 삽입한다. **순번은 HTML이 아닌 CSS counter로 자동 부여**하여, 항목 추가/삭제 시 HTML 수정이 불필요하다.

```
📋 주기능 (data-nav-section="main")  ← 신규 2항목 삽입 (순번은 CSS counter)
├── 메타데이터 생성                        → /metadata_batch
├── 진행 상황 & 재개  [신규]               → /batch-monitor
├── 판정 패킷 추출    [신규]               → /judgment-extract
├── 판정 결과 반영                         → /judgment_apply
├── 그룹 검토                              → /group-review
├── 📊 그룹분석                           → /perspective_test   (순번 제외)
└── ⚙️ 설정 ▸탭                           → /settings           (변경 없음, 순번 제외)

📦 결과물 · ✍️ 수동 조작 · 🧪 테스트 · 👨‍💼 관리자   → 변경 없음(0701_01 상태 유지)
```

**변경 규칙**:
- 신규 `<a>` 2개(`/batch-monitor`·`/judgment-extract`)를 📋 주기능에 삽입.
- **순번은 CSS counter로 자동 생성** — `<a>` 텍스트에 `1️⃣` 이모지 직접 삽입 금지. 대상은 파이프라인 5개(메타데이터 생성~그룹 검토). `perspective_test`·`settings`는 파이프라인 밖이므로 counter 제외.
- 허브 탭(설정·리스트·데이터)·접기·버전 배지는 **그대로 유지**(재작성 금지 — 0701_01 회귀 방지).
- `/metadata`(단일)·`/wordcloud_debug`·`/preprocess` → 네비 추가 안 함(개발자/특례).
- 관리자 섹션 조건부 표시: `_is_admin_session` context processor가 이미 전역 주입됨(`base.html:252` 사용 확인). 관리자 섹션 전체를 `{% if _is_admin_session %}`로 래핑(§7 참조).

### 3.2 프론트엔드: nav.css 변경 — CSS Counter 규칙 추가

> ⚠️ 최초안의 `.collapsible`·`.nav-admin` 신규 제안은 **폐기**. `0701_01`이 접기·active·배지 클래스를 이미 넣었다(실측):
> - 접기: `.nav-section-title .collapse-caret` + `.nav-section.collapsed > a { display:none }` (nav.css:146-156)
> - active: `.nav-section a.active` (nav.css:159-165) · 버전 배지: `.version-badge` (nav.css:168-200)

**신규 추가 (nav.css 말단, 버전 배지 이후):**
```css
/* ── 파이프라인 순번 (CSS counter) ──────────────────────── */
.nav-section[data-nav-section="main"] {
    counter-reset: pipeline;
}
.nav-section[data-nav-section="main"] > a:not([href*="perspective_test"]):not([href*="settings"]) {
    counter-increment: pipeline;
}
.nav-section[data-nav-section="main"] > a:not([href*="perspective_test"]):not([href*="settings"])::before {
    content: counter(pipeline) "\fe0f\20e3\0020";
    font-size: inherit;
    vertical-align: baseline;
}
```

> **설명**: `counter-reset`으로 📋 주기능 섹션 내 카운터 초기화. `perspective_test`·`settings`를 `:not()`로 제외하여 파이프라인 5개 항목(메타데이터 생성→그룹 검토)만 순번 부여. `::before` pseudo-element로 숫자 표시. 신규 항목 추가 시 HTML 수정 불필요 — counter가 자동 조정됨.

> ⚠️ **CSS 이스케이프 주의(수정 반영 2026-07-01)**: `content`의 문자열 이스케이프는 `\` + 16진수 형식(`\fe0f`)이며 JS/파이썬식 `⃣`는 **무효**(`\u`가 리터럴 `u`로 해석되어 키캡이 깨짐). 키캡 조합(digit + U+FE0F + U+20E3)은 반드시 `"\fe0f\20e3\0020"`로 표기해야 `1️⃣`로 렌더된다. 구현 후 실제 브라우저 렌더 확인은 §6 검증 게이트로 유지한다.
> 📌 **아이콘 중복 참고**: 파이프라인 `<a>`는 이미 선두 이모지를 가짐(`📄 메타데이터 생성`) → counter `::before` 숫자가 앞에 붙으면 `1️⃣📄 …`로 아이콘 2개가 된다. 순번만 두려면 대상 항목의 기존 선두 이모지를 제거해야 함(디자인 판단 — §6 시각 확인 시 결정).

- 신규 삽입되는 `<a>` 2개는 **기존 `nav a` 스타일은 그대로 상속** — nav.css 기본 스타일 변경 없음.
- 현재 페이지 하이라이트는 기존 `.active` 클래스 재사용(신규 클래스 금지).

> 🔴 **지침 동기화 필요(별개 정리 항목):** `nav.css` 헤더(L4)가 정본으로 가리키는 `.clinerules/docs/ui/common/design-system/06-navigation.md`는 **여전히 구형 `.sep`+`.dropdown` 모델만 기술**하고, `0701_01`이 추가한 `.nav-section`/`.nav-section-title`/`.collapse-caret`/`.collapsed`/`.active`/`.version-badge`가 **문서에 없다**. 또한 지침의 섹션 구분자 스펙(`.sep` #bbb·600)과 실제(`.nav-section-title` primary #6366f1·700)이 불일치. → 이 계획서 범위 밖이나, `08-guideline-modification` 절차로 `06-navigation.md`를 실 CSS에 맞춰 갱신할 것(미갱신이 "CSS 지침이 적용 안 됨"의 실제 원인).

### 3.3 신규 템플릿: batch_monitor.html

기존 `metadata_batch.html`의 L432-483(처리 진행 상황 섹션)을 독립 페이지로 분리:

- **SSE 연동**: `/api/batch/events` 구독 → 실시간 진행 표시줄 (`batch_processing_state` 전역 변수 참조)
- **기능 버튼**: "이어서 처리"(`POST /api/batch/resume`→body: `{batch_id}`), "실패 재시도"(`POST /api/batch/retry-failed`)
- **작업서 게시판**: `GET /api/batch/work-orders`(batch_routes.py:134) → 최근 배치 목록 (상태·진행률·재개 버튼). 완료된 작업서는 "판정 패킷 추출" 버튼으로 `/judgment-extract` 연결
- **공통 JS 모듈 권장**: `metadata_batch.html`과 SSE 구독·진행바 업데이트 로직이 중복됨 → `web/static/js/batch-progress.js`로 분리. `metadata_batch.html`과 `batch_monitor.html`이 공유. 기존 인라인 JS를 모듈로 리팩토링하는 것이 바람직하나, **범위 외**(본 계획서는 신규 생성에 집중). 최소한 `batch_monitor.html`에 새로 작성하고, 추후 리팩토링 과제로 남김.
- **경로**: `web/templates/batch_monitor.html` (extends base.html)

### 3.4 신규 템플릿: judgment_extract.html

판정 패킷 추출 전용 UI (현재는 POST API 전용 + admin 필수):

- **입력**: 배치 선택 드롭다운 → 소스: `GET /api/batch/work-orders`(batch_routes.py:134, SQLite → 작업서 DB). 완료된 배치만 노출(status='completed').
  - 마진 드롭다운: `["자동(auto)", "0.05", "0.10", "0.15"]` → JS에서 `auto`는 `null`, 숫자는 `float`로 변환하여 API body에 전달.
- **실행**: `POST /api/perspective/judgment/extract` 호출 (admin 필수 — API 내부 `_is_admin()` 체크 존재, perspective_routes.py:626)
- **결과**: API가 직접 `Content-Disposition: attachment`로 JSON 파일 다운로드 응답(perspective_routes.py:644-646). 브라우저 측에서 Blob 처리 → 프론트에서 다운로드 트리거.
  - 응답 헤더 `Content-Type: application/json` + `Content-Disposition: attachment; filename="{packet_id}.json"` → fetch → blob → `URL.createObjectURL` → `<a>` click 다운로드.
  - 추출 건수(items.length)와 격리 건수(quarantined)는 응답 JSON의 `_status.counts`에서 추출.
- **가이드**: "다운로드 → AI 판정 → 판정 결과 반영" 3단계 플로우 안내 (judgment_apply.html로 링크)
- **경로**: `web/templates/judgment_extract.html` (extends base.html)
- **인증**: API가 admin 필수이므로, UI에서도 `_is_admin_session` 확인 → 비관리자에게 "관리자 로그인 필요" 메시지 표시

### 3.5 백엔드: 신규 라우트 (ui_routes.py)

```python
@ui_bp.route('/batch-monitor')
def batch_monitor():
    """배치 진행 상황 및 재개 페이지."""
    return render_template('batch_monitor.html')

@ui_bp.route('/judgment-extract')
def judgment_extract():
    """판정 패킷 추출 페이지.
    POST API(perspective_routes.py:617)는 admin 필수이므로,
    UI에서도 _is_admin_session 확인. 비관리자는 메시지 표시.
    """
    return render_template('judgment_extract.html')
```

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `ui_routes.py`에 `/batch-monitor`, `/judgment-extract` 라우트 추가 | 없음 |
| 2 | `batch_monitor.html` 신규 생성 (SSE 연동 + 작업서 게시판) | 1 |
| 3 | `judgment_extract.html` 신규 생성 (패킷 추출 UI + 다운로드 + admin 체크) | 1 |
| 4 | `nav.css` 말단에 CSS counter 규칙 추가 (파이프라인 자동 순번) | 없음 |
| 5 | `base.html` 📋 주기능 섹션에 `<a>` 2개 삽입 (**순번 이모지 없음** — CSS counter가 자동 생성) | 2·3·4 |
| 6 | 관리자 섹션 `{% if _is_admin_session %}` 조건부 표시 적용 | 5 |
| 7 | 전체 Nav 링크 클릭 테스트 (404 없는지) + 0701_01 병합/접기/배지 회귀 없음 확인 | 1~6 |

## 5. 영향도 분석

| 파일 | 변경 유형 | 영향 |
|------|-----------|------|
| `web/templates/base.html` | 수정 | 📋 주기능 섹션에 `<a>` 2개 삽입 (순번 이모지 없음) + 관리자 섹션 `{% if %}` 래핑 |
| `web/static/css/nav.css` | 수정 | 말단에 CSS counter 규칙 추가 (파이프라인 자동 순번) — 기존 nav a 스타일 불변 |
| `src/routes/ui_routes.py` | 수정 | 라우트 2개 추가 (`/batch-monitor`·`/judgment-extract`) |
| `web/templates/batch_monitor.html` | **신규 생성** | 배치 진행 독립 페이지 (SSE + 작업서 게시판) |
| `web/templates/judgment_extract.html` | **신규 생성** | 판정 패킷 추출 UI + admin 체크 |
| 기존 페이지들 | **영향 없음** | 라우트·템플릿·API 전혀 변경 없음 |

**변경 최소화 원칙**: 0701_01 병합 nav 유지. base.html에 `<a>` 2개·nav.css counter 규칙·라우트 2개·템플릿 2개만 추가.

## 6. 테스트/검증 계획

| 검증 항목 | 방법 | 기준 |
|-----------|------|------|
| 모든 링크 정상 동작 | 각 Nav 링크 클릭 → 404 없는지 확인 | 404 0건 |
| CSS counter 순번 표시 | 📋 주기능 파이프라인 5개 항목에 1~5 순번 숫자 표시 확인 | perspective_test·settings는 순번 없음 |
| 관리자 조건부 표시 | 비로그인 시 관리자 메뉴 미노출 | 템플릿 `{% if _is_admin_session %}` |
| 신규 페이지 렌더링 | `/batch-monitor`, `/judgment-extract` 접속 → 템플릿 정상 로드 | 200 OK + 내용 표시 |
| 0701_01 회귀 없음 | 허브 탭·섹션 접기·버전 배지 정상 동작(수정 전과 동일) | 병합/접기/배지 유지 |
| 기존 페이지 영향 없음 | 검증 후에도 기존 페이지 기능 변경 없음 | 수정 전과 동일 |

## 7. 리스크 및 제약

| 리스크 | 대응 |
|--------|------|
| `base.html` nav 수정으로 모든 페이지에 영향 | 변경 범위를 `<nav>` 블록으로 한정 — 다른 부분 건드리지 않음 |
| 새 템플릿 `batch_monitor.html`이 SSE 없이 로딩만 표시 | Fallback: "진행 중인 배치 없음" 메시지 + 수동 새로고침 유도 |
| `judgment_extract.html` — API가 admin 필수인데 비관리자 접근 시 | 템플릿에서 `_is_admin_session` 확인 → `{% if %}`로 UI 차단 + "관리자 로그인 필요" 메시지. API 자체도 401 반환하므로 이중 방어 |
| 관리자 섹션 조건부 표시 | `session['admin_logged_in']`은 `app.py`에서 context processor로 `_is_admin_session` 전역 노출(`base.html:252` 실측 확인). 단, **관리자 nav 섹션(`base.html:222-226`)은 아직 조건부 래핑되지 않음** — `{% if _is_admin_session %}`로 래핑 필요(§4 순서 6). "24개 render_template 수정"·"JS 대안" 모두 **불요** |
| CSS counter `::before`가 기존 `nav a` padding에 영향 | `::before`는 inline 요소로 기존 `padding-left` 내에 표시됨. 순번 숫자가 2자리(10+)가 될 일이 없으므로 레이아웃 영향 없음 |
| `base.html` 관리자 섹션 래핑 후 관리자 nav가 보이지 않음 | `_is_admin_session`이 JS 로그인 후 세션에 설정되는 시점(`app.py` 로그인 라우트) 확인 필요. 이미 버전 모달(L252)에서 동일 변수 사용 중이므로 정상 동작 |
