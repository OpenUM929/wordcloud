# 계획서 — 불용어 필터링 데모 결과가 화면에 표시되지 않는 버그 수정

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: A
> 선행: (없음)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 — 코드는 사용자 요청으로 계획서보다 먼저 구현됨(§5) |
| 2026-08-20 | §5, §6 | 독립 검증 반영 — §5 "인라인 `<script>` 파일" 표현 정정(`stopwords.js`는 외부 파일, 20_02 문구가 잘못 옮겨온 흔적). §6 "단독 `stopwords.html`이 실제 라우트에서 쓰이는지 미확인"을 재확인해 정정 — `grep -rn "stopwords.html" wordcloud_project/src` 결과 0건으로 라우트 참조 없음을 직접 확인(13_03 계획서의 기존 결론과도 일치) |

## 1. 문제 정의

- **증상**: `/settings` 화면의 "주기능 > 설정 > 불용어 관리" 안 "불용어 필터링 데모" 섹션에서 필터링이 제대로 안 되는 것처럼 보인다(사용자 보고).
- **위치 확인**: "불용어 필터링 데모"는 `wordcloud_project/web/templates/partials/_stopwords_body.html:128`(`/settings` 허브가 로드하는 부분 템플릿)과 단독 페이지 `wordcloud_project/web/templates/stopwords.html:234`에 동일하게 존재. 둘 다 결과 표시 영역이 `<div id="demo-results" style="display: none;">`로 시작한다(`_stopwords_body.html:136`, `stopwords.html:242` — 인라인 스타일로 초기 숨김).
- **재현 조건**: `/settings` 화면 → 불용어 관리 탭 → 데모 텍스트 입력 → "필터링 적용" 클릭.
- **관찰된 실패 산출물**: 별도 에러 로그는 없음(요청은 200 성공) — 결과 데이터는 정상 수신되지만 화면에 나타나지 않는 **표시 버그**임을 코드로 확인.

## 2. 원인 분석

> ⛔ 원인 확정 게이트
> 1. **재현**: 실제 브라우저 클릭까지는 서버 미기동으로 못 했으나, 클릭 핸들러 코드 경로를 끝까지 정적 추적해 "성공 응답을 받아도 결과 div가 열리지 않는다"를 코드 상에서 확정했다(아래 근거).
> 2. **그 줄이 범인임을 관측**: `wordcloud_project/web/static/js/stopwords.js:616`(수정 전) `demoResults.classList.remove('d-none');` — 이 요소에는 `d-none` 클래스가 애초에 없다(템플릿에 `class` 속성 자체가 없음, `style="display: none;"`만 있음). 없는 클래스를 제거하는 연산은 아무 효과가 없고, 인라인 `display: none`은 그대로 유지된다.
> 3. **반증 실험**: 만약 이 줄이 원인이 아니라면, 같은 파일 안에서 다른 곳들도 `classList` 방식을 쓰거나, `demo-results`에 실제로 `d-none` 클래스가 붙는 다른 코드가 있어야 한다 — `grep -n "classList.remove\|classList.add\|style.display" stopwords.js` 결과, 이 파일의 다른 모든 show/hide 처리(272~348, 415~484행 등)는 전부 `.style.display` 방식이고, `classList`로 `d-none`을 다루는 곳은 이 한 줄뿐이었다(자동완성/복붙 과정에서 다른 프레임워크의 관용구가 섞여 들어간 것으로 추정). 반증되지 않았다.
- **분석**: `filterDemoText()`(`stopwords.js:584`)가 `POST /api/stopwords/filter`(`api_routes.py:448`, `filter_text_stopwords()`)를 호출해 성공적으로 `original_text`/`filtered_text`/통계를 받아 `demoOriginal`/`demoFiltered`/`demoStats`에 채워 넣지만(605~615행), 그 다음 줄(616행)이 결과 컨테이너를 열지 못해 사용자 눈에는 "필터링이 안 된 것"처럼 보인다. 백엔드(`api_routes.py:448~473`)는 `filter_stopwords(text)` 호출·응답 구성에 결함이 없음을 별도로 확인했다.
- **회귀 도입 지점**: 미상(최초 작성 시점부터의 결함으로 추정, 관련 커밋 특정은 이번 조사 범위 밖).

## 3. 수정 방안

- **핵심 변경**: `demoResults`를 여는 방식을 이 파일의 다른 모든 곳과 동일하게 `.style.display`로 통일한다.
- **세부 수정**:
  - `wordcloud_project/web/static/js/stopwords.js:616`: `demoResults.classList.remove('d-none');` → `demoResults.style.display = 'block';`

## 4. 롤백 계획

- 한 줄 변경이므로 해당 줄을 원래 코드로 되돌리면 즉시 롤백 가능(기능적으로는 원래도 깨져 있던 상태로 돌아갈 뿐이라 위험 없음).

## 5. 결과 (구현 완료 후 기재)

- **적용된 변경**: 2026-08-20, `wordcloud_project/web/static/js/stopwords.js:616` 수정 완료.
- **검증 결과**: 외부 스크립트 파일 `wordcloud_project/web/static/js/stopwords.js`를 `node --check`로 구문 검사만 통과 확인. **실제 브라우저 동작 검증은 미수행**(서버 무단 기동 금지, PND) — 다음 서버 기동 시 `/settings` → 불용어 관리 → 데모 텍스트 입력 → "필터링 적용" 클릭 → 결과 영역이 실제로 나타나는지 사용자 확인 필요.

## 6. 영향도 분석

- **변경 파일**: `wordcloud_project/web/static/js/stopwords.js` 1줄만 변경.
- **영향 범위**: `demoResults` 요소는 이 데모 섹션 전용이며 다른 화면과 공유되지 않음(DL-8 해당 없음). `_stopwords_body.html`(`/settings` 허브가 로드하는 부분 템플릿)과 단독 `stopwords.html`이 같은 `stopwords.js`를 쓰지만, `grep -rn "stopwords.html" wordcloud_project/src` 결과 0건 — 단독 `stopwords.html`을 렌더링하는 라우트가 없어 실사용자에게 노출되지 않는 파일임을 확인했다. 실질적으로 이번 수정의 영향은 `/settings` 허브 경로 하나뿐이다.

## 7. 테스트/검증 계획

- `/settings` → 불용어 관리 탭 → 데모 텍스트 입력 → "필터링 적용" → 원본/필터링된 텍스트·통계(원본 길이/필터링 후 길이/제거된 단어 수)가 화면에 나타나는지 확인.
- 빈 텍스트로 클릭 시 기존 경고 토스트(`stopwords.js:588` "테스트 텍스트를 입력하세요.")가 그대로 뜨는지 회귀 확인.

## 8. 리스크 및 제약

- 없음 — 표시 전용 1줄 수정, 데이터 흐름·백엔드 변경 없음.
