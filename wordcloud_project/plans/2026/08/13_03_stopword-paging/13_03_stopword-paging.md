# 계획서 — 불용어 관리 페이지 페이징 영역이 세로로 길게 늘어나는 현상 수정

> 상태: Todo | 작성일: 2026-08-13
> 작업 유형: A (버그 수정)
> 선행: 없음 (같은 화면을 다루는 기능 계획서: 2026/08/13_02)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-13 | 전체 | 최초 작성 |

---

## 요구사항 원자화

| # | 원자 질문 | 기대 (사용자 확인) | 작업 후 답 (근거) |
|---|-----------|--------------------|------------------|
| 3.1 | 문제가 보이는 화면은 `/settings#stopwords`(설정 허브의 불용어 관리 탭)인가? | Y — `/stopwords` 는 이 주소로 302 리다이렉트된다(`ui_routes.py:121`). 별도 파일 `web/templates/stopwords.html` 은 **어떤 라우트도 렌더하지 않는 레거시**(실측: 참조 0건) | |
| 3.2 | 늘어나는 대상은 **목록 아래 페이지 번호 영역**(1·2·3·이전·다음)인가, 불용어 목록 카드 전체인가? | 페이지 번호 영역(`<div id="pagination-container">`, `_stopwords_body.html:73`). 이 영역이 화면 높이만큼(100vh) 세로로 늘어나 목록 카드가 통째로 길어져 보이는 것으로 본다 | |
| 3.3 | 「한 페이지에 표시할 개수」를 1000(전체 보기)로 놓아서 길어진 것인가? | N — 그 경우는 표 자체가 길어지는 정상 동작이며, 기본값 10에서도 재현되어야 이 버그다 | |
| 3.4 | 같은 증상이 다른 화면에도 있는가? | N — 콘텐츠 영역에서 `<nav>` 태그를 만들어 쓰는 곳은 `stopwords.js:259` 한 곳뿐이다(실측: 템플릿·JS 전수 grep) | |
| 3.5 | 페이지 번호가 **가로 한 줄**로 나오는 것이 정상 기대인가? | Y — 가운데 정렬, 가로 배치 | |

---

## 1. 문제 정의

### 1.1 관찰된 실패 산출물

- **콘솔 에러·서버 로그 없음.** 이 증상은 예외가 아니라 CSS 적용 결과이므로 스택트레이스가 존재하지 않는다. 따라서 이 계획의 "실패 산출물"은 **렌더된 DOM의 계산 스타일 값**(`#pagination-container > nav` 의 `height`)으로 정의한다.
- 확보된 산출물(2026-08-13, 정적 하네스 + 헤드리스 Chrome, 서버 미기동): `plans/2026/08/13_03_stopword-paging/test/repro_pagination.html` + `test/measure.py` 실행 결과 `test/measure_result.json`.
  - `#pagination-container-A > nav` (원본 마크업): `height: 749px`(= 그 시점 `viewport.innerHeight` 749px와 정확히 일치) · `width: 170px` · `position: sticky` · `display: flex`.
  - `#pagination-container-A ul.pagination` (내부 목록): `height: 65px` · `display: flex` — 번호 자체는 가로 배치 유지(§2.2 예측과 일치).

### 1.2 증상 (사용자 보고 원문)

> 불용어 관리 페이지에서 페이징 카드쪽의 레이아웃이 아래로 길게 늘어나는 현상이 있다.

### 1.3 재현 조건

| 항목 | 값 |
|------|-----|
| 화면 | `/settings` → 「🗑️ 불용어 관리」 탭 (`settings_hub.html:192`) |
| 전제 | 불용어가 11건 이상이어야 페이지 번호가 그려진다. 현재 사전은 101단어(`src/configs/stopwords.json` 실측)이고 기본 페이지 크기는 10(`stopwords.js:36`)이므로 **기본 상태에서 항상 재현 조건 충족** |
| 트리거 | 목록이 그려지는 즉시 `updatePagination()`(`stopwords.js:230`)이 `#pagination-container` 에 HTML을 주입 |

---

## 2. 원인 분석

> ✅ **원인 확정 게이트 — 현재 상태: 통과 (2026-08-13)**
> ① 재현: 정적 하네스로 완료(서버 미기동, DL-12 준수). ② 그 줄이 범인임을 관측: `<nav>` 래퍼의 계산 높이 749px = 그 순간 뷰포트 높이(100vh)와 정확히 일치, 너비 170px, `position:sticky` — F2 규칙이 실제로 적용됨을 확인. ③ 반증 실험: 같은 마크업의 `<nav>`만 `<div>`로 바꾼 사본은 높이 39.6px(내용 높이)·너비 283px(컨테이너 폭 따름)·`position:static`으로 정상화됨 — 가설과 정확히 일치.
> §2.2는 이제 **확정 원인**이다. §3 수정을 실제 적용했다(아래).

### 2.1 정적 대조로 확인한 사실 (여기까지는 실측)

| # | 사실 | 근거 |
|---|------|------|
| F1 | 페이지 번호 마크업은 **`<nav>` 로 감싸여 생성**된다 | `web/static/js/stopwords.js:259` — `let paginationHTML = '<nav><ul class="pagination justify-content-center mb-0">';` |
| F2 | 전역 CSS가 **요소 선택자 `nav`** 에 좌측 네비게이션 스타일을 건다 | `web/static/css/nav.css:6-22` — `nav { width:170px; min-height:100vh; height:100vh; position:sticky; top:0; padding:12px 8px; display:flex; flex-direction:column; overflow-y:auto; border-right:2px solid …; }` |
| F3 | 그 CSS는 이 화면에도 로드된다 | `web/templates/base.html:182` `<link rel="stylesheet" href="/static/css/nav.css">` — `settings_hub.html` 은 `base.html` 을 상속 |
| F4 | 콘텐츠 영역 안에서 `<nav>` 를 쓰는 곳은 이 한 곳뿐 | 템플릿·JS 전수 grep: `base.html:186`(진짜 좌측 네비)과 `stopwords.js:259` 두 곳뿐. 그래서 **이 화면에서만** 증상이 보인다는 사용자 보고와 맞물린다 |
| F5 | 컨테이너 CSS는 이 마크업과 맞지 않는다 | `settings_hub.html:88-113` 은 `.pagination-container button {…}` 를 정의하지만 실제 생성물은 `<a class="page-link">` 다(`stopwords.js:261-276`) → 이 규칙들은 **적용되지 않는 사문(死文)** |
| F6 | 부트스트랩은 정상 로드되며 `.pagination` 가로 배치 규칙을 갖고 있다 | `base.html:7` `static/vendor/bootstrap.min.css`(v5.3.0) 안에 `.pagination{…display:flex;padding-left:0;list-style:none}` 존재 → **"부트스트랩이 없어서 세로로 쌓였다"는 가설은 반증됨** |

### 2.2 유력 가설

`#pagination-container`(`display:flex`, `settings_hub.html:81-86`)의 자식으로 들어간 `<nav>` 가 F2의 전역 규칙을 그대로 받아 **높이 100vh · 너비 170px · 세로 flex · 우측 테두리**를 갖는 박스가 된다. 그 결과 목록 표 아래에 화면 한 폭 높이의 빈 상자가 생겨 "페이징 카드가 아래로 길게 늘어난" 것처럼 보인다.

내부 `<ul class="pagination">` 자체는 F6에 따라 가로 배치를 유지하므로, **번호는 가로로 붙어 있는데 그 아래 공백만 길게 늘어나는** 모양이 될 것으로 예측한다. 이 예측이 실제 화면과 다르면(예: 번호가 세로로 쌓임) 가설은 틀린 것이다(§2.3 반증 조건).

### 2.3 게이트 통과 절차 (구현 착수 전 수행)

서버를 띄우지 않고 재현한다.

1. **정적 재현 하네스**: `test/repro_pagination.html` 을 만든다. 실제 화면과 같은 순서로 `vendor/bootstrap.min.css` → `css/base.css` → `css/nav.css` 와 `settings_hub.html` 의 인라인 `<style>` 블록(페이징 규칙 `:81-113` 포함)을 로드하고, `stopwords.js:259-277` 이 만드는 것과 **한 글자도 다르지 않은 마크업**을 `#pagination-container` 에 넣는다.
2. **계측**: 브라우저에서 열어 `getComputedStyle(nav).height / width / display` 를 읽는다(파일 하단 스크립트가 값을 화면에 출력). 사용자 확인이 어려우면 `selenium`(설치 확인됨 — `requirements.txt` `selenium==4.41.0`)으로 헤드리스 실행해 값을 파일로 남긴다. **어느 쪽도 Flask 서버를 켜지 않는다.**
3. **관측 기준(②)**: `nav` 의 계산 높이가 뷰포트 높이(100vh)와 같고 너비가 170px 이면 F2 규칙이 실제로 적용된 것으로 확정한다.
4. **반증 실험(③)**: 같은 하네스에서 `<nav>` 만 `<div>` 로 바꾼 사본을 함께 측정한다.
   - 가설이 옳다면: 높이가 내용 높이(수십 px)로 줄고 너비가 컨테이너를 따른다.
   - **가설이 틀렸다면**: `<div>` 로 바꿔도 세로로 길게 남는다 → 그 경우 다음 후보를 조사한다. (a) `.info-section` 의 높이 규칙, (b) `.pagination-container` 의 `display:flex` 와 자식 정렬, (c) 페이지 크기 1000 선택 시의 표 길이(=정상 동작).
5. 1~4의 결과를 §1.1과 이 절에 수치로 기입한 뒤에야 §3을 구현한다.

### 2.4 회귀 도입 지점

미확정. `stopwords.js` 의 부트스트랩식 마크업(`<nav><ul class="pagination">`)과 `settings_hub.html` 의 버튼 기반 CSS(F5)가 서로 다른 구현 세대를 가리킨다 — 한쪽을 교체하면서 다른 쪽을 남긴 흔적으로 보이나, 커밋 이력 대조는 게이트 통과 후 수행한다.

---

## 3. 수정 방안 (게이트 통과 후 적용)

- **핵심 변경**: 페이지 번호를 감싸는 래퍼를 `<nav>` 에서 `<div>` 로 바꿔, 좌측 네비게이션용 전역 스타일이 걸리지 않게 한다.

- **세부 수정**

| 파일 | 변경 |
|------|------|
| `web/static/js/stopwords.js:259` | `'<nav><ul class="pagination justify-content-center mb-0">'` → `'<div><ul class="pagination justify-content-center mb-0">'` |
| `web/static/js/stopwords.js:277` | 닫는 `</ul></nav>` → `</ul></div>` |
| `web/templates/settings_hub.html:88-113` (선택) | 사문 규칙 `.pagination-container button …` 4개를 `.pagination-container .page-link …` 로 정정하거나 삭제. **부트스트랩 기본 모양으로 충분하면 삭제를 권장** |

- **선택하지 않은 대안과 이유**

| 대안 | 기각 사유 |
|------|-----------|
| `nav.css:6` 을 `body > nav` 또는 `.site-nav` 로 좁히기 | 전역 네비 CSS는 모든 화면이 쓰는 공통 자산이다(DL-8). 한 화면 문제를 고치려고 공통 선택자를 바꾸면 영향 범위가 전 화면으로 번진다 |
| `.pagination-container nav { height:auto; width:auto; … }` 로 덮어쓰기 | 원인(잘못된 태그 선택)을 남겨 둔 채 증상만 가린다. 같은 실수가 다른 화면에서 재발한다 |

---

## 4. 롤백 계획

- 변경은 JS 1개 파일의 2줄(+선택적으로 CSS 4규칙)뿐이다. `git checkout -- web/static/js/stopwords.js` 로 즉시 복원된다.
- 수정 전 `web/static/js/stopwords.js` 를 `plans/2026/08/13_03_stopword-paging/backup/` 에 사본 보관한다(`18-backup-before-modify.md`).

---

## 5. 영향도 분석

| 파일 | 변경 | 영향 |
|------|------|------|
| `web/static/js/stopwords.js` | 래퍼 태그 2곳 | 이 파일을 로드하는 살아있는 화면은 `settings_hub.html:204` 1곳. (다른 참조 `stopwords.html:273` 은 라우트 없는 레거시) |
| `web/templates/settings_hub.html` | (선택) 사문 CSS 정리 | 같은 화면 내 감정어 설정 탭에는 `.pagination-container` 사용처가 없음 — 실측 확인 후 진행 |

- **레거시 파일 주의**: `web/templates/stopwords.html`(273줄)은 어떤 라우트도 렌더하지 않는다(실측). **이 파일은 수정 대상이 아니다.** 여기를 고치면 화면에 아무 변화가 없어 "고쳤는데 그대로"라는 오진으로 이어진다.
- 백엔드·API·데이터 무변경. 감정 판정 로직 무관.

### 5.1 도메인 잠금 점검

| 잠금 | 판정 |
|------|------|
| DL-4 감정 극성 | 해당 없음 — 판정 코드 무변경 |
| DL-8 공통 모듈 침범 | **준수** — 공통 자산인 `nav.css` 를 건드리지 않고 호출 측 마크업만 고친다 |
| DL-10 완료 판정 | 화면 육안 확인 전 `Done` 금지 |
| DL-12 서버 무단 기동 | **준수** — 재현·검증 모두 정적 하네스로 수행. 최종 화면 확인만 사용자가 서버를 켠 뒤 진행 |
| 그 외(DL-1·2·3·5·6·7·9) | 해당 없음 — 데이터·배치·가명·학습 경로 무관 |

---

## 6. 테스트/검증 계획

`test/` 폴더: `plans/2026/08/13_03_stopword-paging/test/`

| # | 시나리오 | 방법 | 기대 | 결과(2026-08-13) |
|---|----------|------|------|------|
| T1 | 수정 전 계측(게이트 ②) | `repro_pagination.html` 원본 마크업, `measure.py`(헤드리스 Chrome) | `nav` 높이 = 뷰포트 높이, 너비 = 170px | ✅ 통과 — 749px=749px, 170px |
| T2 | 반증 실험(게이트 ③) | 같은 하네스의 `<div>` 판 | 높이 = 내용 높이(≈40px 내외), 너비 = 컨테이너 폭 | ✅ 통과 — 39.6px, 283px |
| T3 | 문법 검사 | `node --check web/static/js/stopwords.js` | 오류 0 | ✅ 통과 |
| T4 | 페이지 이동 동작 유지 | `stopwords.js:281-291` 은 `paginationContainer.querySelectorAll('.page-link[data-page]')` 기준 — 코드 확인 결과 래퍼 태그(`nav`/`div`)를 셀렉터에서 참조하지 않음 | 클릭 시 `data-page` 값이 정상 전달 | ✅ 통과(정적 코드 대조) |
| T5 | 회귀 — 좌측 네비 | `nav.css` 파일 자체는 이번 수정에서 미변경(diff 0줄) | 폭 170px·전체 높이 그대로 | ✅ 통과(무변경 확인) |

**실동작 검증(사용자 승인 후, 사용자가 서버 기동)**

1. `/settings#stopwords` 진입 → 페이지 번호가 목록 바로 아래 가로 한 줄로 표시되고 아래 빈 공간이 없는지 확인.
2. 페이지 크기 10/20/50/전체 보기로 바꿔가며 레이아웃 유지 확인.
3. 검색으로 결과 0건 → 페이징 영역이 숨겨지는지 확인(`stopwords.js:297-299`).

1~3 통과 후에만 상태를 `Done` 으로 올린다(DL-10).

---

## 7. 리스크 및 제약

| # | 리스크 | 영향 | 대응 |
|---|--------|------|------|
| R-1 | 가설이 틀릴 가능성 | 엉뚱한 곳을 고쳐 증상 유지 | §2.3-4 반증 실험을 먼저 수행. `<div>` 로 바꿔도 남으면 즉시 다른 후보로 이동하고 이 계획서 §2를 갱신 |
| R-2 | 사용자가 본 증상이 3.2·3.3과 다를 가능성(예: 목록 카드 자체가 길다) | 범위 오판 | 원자 질문 3.2·3.3으로 착수 전 확인. 필요하면 화면 캡처 1장으로 확정 |
| R-3 | 정적 하네스가 실제 화면과 다른 조건일 가능성 | 재현 신뢰도 저하 | CSS 로드 순서·인라인 규칙을 `base.html`·`settings_hub.html` 원문에서 복사해 맞춘다. 최종 판정은 실동작 검증 1항 |
| R-4 | 사문 CSS(F5) 정리 시 다른 화면 영향 | 예상치 못한 스타일 변화 | `.pagination-container` 사용처를 전수 grep한 뒤 진행. 불확실하면 이번에는 손대지 않는다(래퍼 태그 교체만으로 증상은 해소) |

**제약**

- `nav.css` 등 공통 CSS는 수정하지 않는다.
- 레거시 `web/templates/stopwords.html` 은 수정하지 않는다.
- 페이징 컴포넌트를 새로 설계하지 않는다(현행 부트스트랩 마크업 유지).
