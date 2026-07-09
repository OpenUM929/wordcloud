# 제출용 저장 결과 화면 페이징 + 아코디언 + 옵션 최적화

## 1. 개요

- **목적**: 360명 직원의 제출용 저장 결과를 한 번에 렌더링할 때 Chrome 응답없음 문제 해결
- **대상 파일**: `wordcloud_project/web/templates/perspective_test.html`
- **적용 범위**: `renderDeployComplete`(제출용 저장), `renderAllEmployees`(매트릭스 저장)

## 2. 작업 내용

### 2-1. 페이징 처리
- 결과를 10명(기본) / 20명 / 40명 / 100명 단위로 분할
- 상단과 하단에 페이지바 배치
- `_deployResults` 배열에 전체 결과 저장 후 페이징 렌더링

### 2-2. 아코디언 구조
- 각 직원 결과는 접힌 상태(헤더: 직원명 + 사번 + 상태 배지만 표시)
- 헤더 클릭 시 펼쳐짐
- CSS 클래스 기반 토글: `.emp-content { display: none; }` / `.emp-content.open { display: block; }`
- **주의**: `emp-content`에 인라인 `style="display:none"` 추가 금지 — CSS 클래스 우선순위를 깨뜨려 토글이 동작하지 않음

### 2-3. 펼침 옵션
- "워드클라우드 기본 펼침" 체크박스: 체크 시 아코디언이 처음부터 펼쳐짐 (워드클라우드 이미지 노출)
- "문장 기본 펼침" 체크박스: 체크 시 `<details>` 태그가 처음부터 열림
- 옵션 변경 시 현재 페이지 리렌더링
- 자동 펼침은 CSS 클래스(`open`)만으로 제어 — `style.display` 직접 조작 금지

### 2-4. 이미지 지연 로드
- `<img>`에 `loading="lazy"` 추가

## 3. 수정 함수

| 함수 | 수정 내용 |
|------|----------|
| `renderDeployComplete` | 전체 결과 저장, 페이징/옵션 UI 렌더링 후 `renderDeployPage()` 호출 |
| `renderDeployPage` (신규) | 현재 페이지 직원 리스트 아코디언 렌더링 |
| `buildDeployPaginationHtml` (신규) | 페이지 버튼 + 페이지당 수 선택 HTML 생성 |
| `changeDeployPage` / `goToDeployPage` / `changeDeployPerPage` (신규) | 페이지 이동 제어 |
| `onDeployOptionChange` (신규) | 옵션 체크박스 변경 시 현재 페이지 리렌더링 |
| `_buildEmployeeResultHtml` | 아코디언 구조로 변경, `expandWc`/`expandSent` 파라미터 추가, 상태 배지 추가 |
| `_renderDeploymentSentences` | `<details>/<summary>` 구조로 감싸기 (expandSent 제어) |
| `resubmitEmployee` | `_buildEmployeeResultHtml` 호출 시 `true, true` 파라미터 추가 |
| `renderAllEmployees` | 페이징 + 아코디언 + 옵션 동일 적용, `renderMatrixPage()` 호출로 분리 |
| `renderMatrixPage` (신규) | 현재 페이지 매트릭스 렌더링 |
| `buildMatrixPaginationHtml` (신규) | 매트릭스용 페이지 버튼 HTML 생성 |
| `changeMatrixPage` / `goToMatrixPage` / `changeMatrixPerPage` (신규) | 매트릭스 페이지 이동 제어 |

## 4. 구현 후 발견 및 수정된 버그 (2026-06-12)

| # | 버그 | 원인 | 수정 |
|---|------|------|------|
| 1 | 아코디언 클릭해도 열리지 않음 | `emp-content`에 인라인 `style="display:none"` → CSS 클래스보다 우선순위 높아 `.emp-content.open { display: block; }` 무효화 | 인라인 스타일 제거, CSS에만 의존 |
| 2 | 자동 펼침 후 수동 닫기 불가 | `classList.add('open')` + `style.display='block'` 혼용 → 클래스 제거해도 인라인 스타일이 남아 닫히지 않음 | `style.display` 직접 조작 제거 |
| 3 | 헤더에 상태 배지 누락 | 구현 누락 | "✅ 완료" 배지 추가 |

## 5. 일정

| 단계 | 내용 | 상태 |
|------|------|------|
| 1 | renderDeployComplete + renderDeployPage + 아코디언 | ✅ 완료 |
| 2 | 옵션 UI + 펼침 제어 | ✅ 완료 |
| 3 | renderAllEmployees 동일 적용 | ✅ 완료 |
| 4 | 버그 수정 (아코디언 토글, 자동 펼침, 상태 배지) | ✅ 완료 |
