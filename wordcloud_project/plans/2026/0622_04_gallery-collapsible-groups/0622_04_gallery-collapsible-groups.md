# 갤러리 삭제/다운로드 모드 경량화 (이미지 비표시 + 그룹 접기)

> 상태: 구현 완료 · 실동작 검증 대기(PND) | 작성일: 2026-06-22 | 개정: 2026-06-22 (이미지 비표시 방침 반영)
>
> **구현 기록 (2026-06-22)**: 계획서 전체 적용. 이전 검토 시 계획서만 있고 코드 미반영이었음을 확인 → 다음을 구현.
> - 서버 `gallery_db_service.list_entries()` `fetch_all` 슬림화: `SELECT`를 7개 컬럼으로 한정, 이미지 JSON 미파싱, `image_count`/`thumbnail_url` 미산출.
> - `deploy_gallery.html` CSS 추가: `.gallery-card--row`, `.date-group-content(.open)`, `.date-group-header .arrow(.open)`.
> - `renderGalleryGrid()`: `selectMode` 분기 + ▶ 화살표(접기 전용, `stopPropagation`), 기본 접힘·펼칠 때 1회 지연 렌더. 일반 모드는 기존 `buildGalleryCard` 유지.
> - `buildSelectRow()` 신규: 이미지 없는 행(`.gallery-card`·`data-entry-id`·`.selected` 규약 유지), 행 클릭=선택, [미리보기]=`openDetail` on-demand.
> - 선택 로직(`toggleCardSelect`/`toggleGroupSelect`/`toggleSelectAll`/`syncGroupCheckboxes`)은 모두 데이터 기반 + DOM 가드라 접힌 그룹에서도 무수정 동작 확인. `py_compile` 통과.
> - ⚠️ 6장 브라우저 테스트는 **사용자 실동작 검증 후** 체크.

## 1. 개요

- **핵심 방침 변경**: 삭제/다운로드 모드는 **선택 작업**이 목적이므로 **썸네일 이미지를 기본 표시하지 않는다.** (사용자 확인: "삭제·다운로드에 전체 이미지는 불필요, 몇 개만 확인하면 됨") → 이미지 요청·DOM·서버 이미지 파싱을 전부 제거하여 부하의 근본 원인을 해소한다.
- **목적**:
  1. (근본) 삭제/다운로드 모드에서 전 항목 이미지 로드 제거 → 스크롤 멈춤 해소
  2. (서버) `all=1` 페이로드 슬림화 → 전 행 이미지 JSON 파싱·MB 단위 전송 제거
  3. (확인용) 필요한 몇 건만 행 클릭으로 상세 모달에서 on-demand 이미지 확인
- **대상 파일**:
  - `wordcloud_project/web/templates/deploy_gallery.html` (클라이언트 렌더링)
  - `wordcloud_project/src/services/gallery_db_service.py` + `src/routes/perspective_routes.py` (슬림 페이로드)
- **적용 범위**: `renderGalleryGrid()` — 삭제·다운로드 모드는 **이미지 없는 텍스트 행 + 그룹 접기**, **일반(페이지네이션) 모드는 기존 이미지 카드 유지** (공용 함수이므로 모드 분기 필수)
- **호출 경로(검증됨)**: `renderDeleteGrid()`(1661행)·`renderDownloadGrid()`(1421행) → `renderGalleryGrid(galleryEntries)`. 일반 모드는 `loadGallery()`(1024행) → `renderGalleryGrid()`. 세 경로 모두 같은 함수로 수렴하므로 모드 게이팅이 없으면 일반 모드까지 영향.
- **참고 패턴**: `perspective_test.html` 의 아코디언 접기(`.emp-header` + `.arrow` + `.emp-content`)
- **별도 처리(완료)**: 갤러리 카드 제목이 `batch_title`로 표시되어 누구의 워드클라우드인지 식별 불가 → **제목을 사번(`employee_id`) 기준**으로 변경(이름이 다르면 `이름 (사번)`). 배치명은 그룹 헤더·하단 라벨에 유지. `buildGalleryCard()` 1140행 수정 완료.

## 2. 문제 분석

### 2.1 현재 구조

| 항목 | dev 값 | 운영 추정 |
|------|--------|-----------|
| 갤러리 DB 항목 수 (`gallery_entries`) | 417개 (배치명 11종) | **수천~수만(대상 1.9만명 × 배치 회차)** |
| `all=1` 반환 | `SELECT * ... ` **LIMIT 없음** (전 행) | 동일 — 행 수에 비례해 폭증 |
| 행당 서버 처리 | `_row_to_dict`가 행마다 `images`·`row_results` JSON 파싱(218~237행) | N행 전수 파싱 → 싱글스레드 CPU 점유 |
| 렌더링 방식 | 전 항목 카드 + `<img>` 동시 생성 | N개 카드 + N개 이미지 요청 |
| 동시 접속 사용자 | 5명 미만 | 동일 |

> dev(417)에선 재현이 약하나, **운영은 행 수가 훨씬 많아** 스크롤 불가 수준의 멈춤이 발생(사용자 보고: "1.9만명분이 한 번에 로딩되는 듯"). 부하는 행 수 N에 **선형 비례**한다.

### 2.2 근본 원인 (RCA)

| # | 현상 | 원인 |
|---|------|------|
| 1 | 모드 진입 후 스크롤 멈춤 | N개 `.gallery-card` DOM + **N개 `<img>` 동시 요청** (지배적 원인) |
| 2 | 진입 시 초기 지연 | 서버가 전 행을 이미지 JSON까지 파싱 + MB 단위 JSON 전송 (`all=1` 유지 시 잔존) |
| 3 | Flask 블로킹 | 싱글스레드에서 N개 이미지 요청·전 행 파싱이 큐잉 |

### 2.3 해결 방향 (이미지 비표시)

- **삭제/다운로드는 이미지가 불필요** → 리스트에서 `<img>`를 만들지 않으면 **원인 1·3이 소멸**(요청 0건).
- **서버 슬림 페이로드**(컬럼만 반환, 이미지 JSON 파싱 생략) → **원인 2 소멸**.
- 그룹 접기(지연 DOM)는 이미지를 없앤 뒤에도 **텍스트 행이 수천 개일 때의 DOM 비용**을 줄이는 보조 수단으로 유지.
- 몇 건 확인은 행 클릭 → 기존 상세 모달(`openDetail`)이 **그 1건만** 이미지 로드(on-demand).

## 3. 작업 내용

### 3-1. 삭제/다운로드 모드 = 이미지 없는 텍스트 행 (핵심)

선택 모드에서는 **썸네일 `<img>`를 생성하지 않는다.** 항목을 다음과 같은 경량 행으로 렌더링한다:

```
[☑] U001 (홍길동)   2026-06-15 13:07   제출용   [미리보기]
[☑] U002 (김철수)   2026-06-15 13:08   매트릭스 [미리보기]
```

| 요소 | 내용 |
|------|------|
| 체크박스 | 기존 선택 로직용 (`data-entry-id`) |
| 식별자 | **사번(`employee_id`)** 우선, 이름 다르면 `이름 (사번)` — 제목 수정과 동일 규칙 |
| 메타 | 날짜·시각 + 소스 배지(제출용/매트릭스) |
| 미리보기 | 버튼/링크 → `openDetail(item.id, item.employee_id)`로 **그 1건만** 이미지 로드 (on-demand) |

- **DOM 호환 유지**: 행 요소도 기존 선택 로직이 쓰는 규약을 그대로 따른다 — 최상위 class에 `gallery-card`(+ `gallery-card--row` 수식자) 유지, `dataset.entryId`, 내부 `input[type=checkbox][data-entry-id]`, 선택 시 `.selected`. → `toggleCardSelect`/`toggleGroupSelect`/`syncGroupCheckboxes`의 `.gallery-card[data-entry-id=...]` 셀렉터가 **수정 없이 동작**한다.
- **행 클릭 = 선택 토글**(기존 선택 모드 UX 유지). 미리보기는 **별도 버튼**으로 분리해 `event.stopPropagation()` 처리.

> 🔴 **일반 모드 비적용**: `renderGalleryGrid()`는 일반(페이지네이션) 모드도 호출한다. `const selectMode = deleteMode || downloadMode;`가 **true일 때만** 텍스트 행 + 접기를 적용하고, false면 기존 **이미지 카드**(`buildGalleryCard`)를 그대로 쓴다. (게이팅 누락 시 일반 갤러리에서 이미지가 사라지거나 접혀 공백이 됨)

### 3-2. 그룹 접기/펼치기 + 헤더 역할 분리

텍스트 행이라도 운영에서는 한 그룹이 수백~수천 건일 수 있으므로 **그룹은 기본 접힘**, ▶ 펼칠 때만 행 DOM을 1회 생성한다(지연 렌더링). 헤더만 보이면 모드 진입이 즉시 끝난다.

> 🔴 **기존 `header.onclick`(1095행)은 "헤더 행 클릭 → 그룹 전체 선택 토글"** 이다. 접기를 같은 핸들러로 덮으면 충돌하므로 역할을 분리한다.

| 클릭 대상 | 동작 |
|-----------|------|
| 그룹 체크박스 `.date-group-select-all` | 그룹 전체 선택 (기존 `change` 리스너, 1086행) |
| ▶ 화살표 `.arrow` | **접기/펼치기 전용** (신규, `stopPropagation()`) |
| 헤더 행 나머지 | 그룹 전체 선택 (기존 `header.onclick` 유지) |

```javascript
// renderGalleryGrid() 내부, selectMode === true 분기
const groupContent = document.createElement('div');
groupContent.className = 'date-group-content';   // 기본 접힘 (CSS display:none)

const arrowEl = document.createElement('span');
arrowEl.className = 'arrow';
arrowEl.textContent = '▶';
arrowEl.onclick = (e) => {
    e.stopPropagation();                         // 헤더 행 onclick(그룹 선택)과 분리
    const opening = !groupContent.classList.contains('open');
    if (opening && groupContent.children.length === 0) {
        dateGroups[dateKey].forEach(item =>
            groupContent.appendChild(buildSelectRow(item))   // 이미지 없는 행
        );
    }
    groupContent.classList.toggle('open', opening);
    arrowEl.classList.toggle('open', opening);
};
header.insertBefore(arrowEl, groupSpan);         // 체크박스 다음, 라벨 앞

grid.appendChild(header);
grid.appendChild(groupContent);
```

### 3-3. 서버 슬림 페이로드 (`all=1` 이미지 파싱 제거)

`all=1` 응답은 **필터 칩 + ID 추적 + 텍스트 행 표시**에만 쓰이고 **이미지가 불필요**하므로, 전 행 이미지 JSON 파싱을 제거한다.

- `gallery_db_service.list_entries(fetch_all=True)`에서 행당 `images`/`row_results` JSON 파싱(218~237행)을 생략하고 **컬럼 직접 값만** 반환: `id, employee_id, deploy_name, batch_title, timestamp, output_mode, source`.
- `image_count`·`thumbnail_url`은 텍스트 행에 불필요 → `fetch_all` 경로에서 미산출(또는 `light` 파라미터로 분기). **상세 모달은 별도 `detail` API로 그때 이미지를 읽으므로 영향 없음.**
- 효과: 전 행 JSON 파싱 제거(서버 CPU↓) + 응답 JSON 크기 대폭 축소(전송↓).

> 페이지네이션(일반 모드) 경로는 기존대로 `thumbnail_url`/`image_count` 포함 — 이미지 카드를 그려야 하므로 유지.

### 3-4. 온디맨드 미리보기

"몇 건만 확인" 요구는 기존 상세 모달을 재사용한다. 행의 **[미리보기]** 클릭 → `openDetail(item.id, item.employee_id)` → `detail` API가 **그 1건의 이미지만** 로드. 리스트에서는 이미지 요청이 0건이다.

### 3-5. CSS 추가

```css
/* 선택 모드 텍스트 행 — 이미지 없음, 세로 리스트 */
.date-group-content { display: none; }
.date-group-content.open { display: block; }          /* 행 리스트이므로 grid 불필요 */
.gallery-card--row {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 10px; border-bottom: 1px solid #eee; cursor: pointer;
}
.gallery-card--row.selected { background: #fdecea; }
.gallery-card--row .row-preview { margin-left: auto; font-size: 12px; color: #2563eb; cursor: pointer; }
.date-group-header .arrow {
    cursor: pointer; transition: transform 0.2s; font-size: 12px; color: #999;
}
.date-group-header .arrow.open { transform: rotate(90deg); }
```

> ✅ 텍스트 행은 세로 리스트(`display:block`)라, 이전 검토의 **CSS Grid 붕괴 위험이 해당 없음**(이미지 카드 다열 그리드를 쓰지 않으므로).

### 3-6. 변경 함수

| 파일 / 함수 | 변경 | 내용 |
|------|------|------|
| `deploy_gallery.html` · `renderGalleryGrid()` (1036행) | 수정 | `selectMode` 분기: 선택 모드 = 접이식 헤더 + `buildSelectRow` 지연 렌더, 일반 모드 = 기존 `buildGalleryCard` flat |
| `deploy_gallery.html` · `buildSelectRow()` | **신규** | 이미지 없는 행 (체크박스·사번·날짜·소스·미리보기). `gallery-card` class·`data-entry-id`·`.selected` 규약 유지 |
| `deploy_gallery.html` · `buildGalleryCard()` (1109행) | 변경 없음 | 일반 모드 이미지 카드 전용으로 유지 (제목 사번화는 별도 완료) |
| `gallery_db_service.py` · `list_entries()` (147행) | 수정 | `fetch_all` 경로에서 이미지 JSON 파싱 생략, 컬럼 값만 반환 |
| `deploy_gallery.html` CSS (~439행 부근) | 추가 | `.gallery-card--row`, `.date-group-content(.open)`, `.arrow` |

### 3-7. 변경하지 않는 항목

| 항목 | 이유 |
|------|------|
| 선택/삭제/다운로드 처리 | `toggleGroupSelect`(1285행)·`toggleCardSelect`(1277행)·`syncGroupCheckboxes`(1302행)·삭제/다운로드 실행 — 행이 `gallery-card`·`data-entry-id` 규약을 지키므로 무수정 동작 |
| 헤더 행 클릭 = 그룹 선택 | 기존 `header.onclick`(1095행) 유지 — 접기는 ▶ 화살표로 분리 |
| 필터 칩 패널 | `renderDeletePanel`/`renderDownloadPanel` — 칩은 `batch_title`/`date`/`source`만 사용(슬림 페이로드에 포함) → 변경 없음 |
| 상세 모달(`openDetail`/`detail` API) | 이미지 on-demand 로드 경로 그대로 |
| 일반 모드 | 이미지 카드 + 페이지네이션 유지 |

## 4. 영향도 분석

### 4.1 변경 대상

| 파일 | 변경 유형 | 영향 범위 |
|------|-----------|-----------|
| `deploy_gallery.html` | 수정 | CSS 추가 + `renderGalleryGrid()` selectMode 분기 + `buildSelectRow()` 신규 + (제목 사번화 완료) |
| `gallery_db_service.py` | 수정 | `list_entries()` `fetch_all` 경로 슬림화(이미지 파싱 생략) |

### 4.2 리스크

| 리스크 | 완화 방안 |
|--------|-----------|
| **선택 로직이 행 DOM을 못 찾음** | 행이 `gallery-card`·`data-entry-id`·`.selected` 규약 유지 → 기존 셀렉터 무수정 동작. 구현 후 전체/그룹/개별 선택 검증 |
| **일반 모드 영향(이미지 사라짐)** | `selectMode = deleteMode\|\|downloadMode` 분기, false면 기존 `buildGalleryCard` 유지 (3-1) |
| **헤더 클릭 충돌 (선택 vs 접기)** | ▶ 화살표 `stopPropagation()` 분리, `header.onclick` 미덮음 (3-2) |
| 슬림 페이로드에서 필터 칩 데이터 누락 | 칩은 `batch_title`/`timestamp`/`source`만 사용 → 슬림 페이로드에 포함 확인 |
| `image_count` 제거로 다른 소비처 영향 | `fetch_all` 경로 한정 변경. 페이지네이션/상세 경로는 기존 유지 — grep으로 `image_count`/`thumbnail_url` 소비처 확인 후 적용 |
| 펼친 그룹 선택 후 접었다 펼침 → 선택 상태 소실 | `buildSelectRow()`가 생성 시 `selectedEntryIds`/`selectedDownloadEntryIds` 재확인하여 `.selected`·체크 반영 |
| DOM 중복 생성 | `groupContent.children.length === 0` 체크로 1회만 생성 |

### 4.3 롤백 계획

- `deploy_gallery.html`: `git checkout -- web/templates/deploy_gallery.html`
- `gallery_db_service.py`: `git checkout -- src/services/gallery_db_service.py`
- 제목 사번화는 독립 변경 — 롤백 시 함께 원복 여부 별도 판단

## 5. 구현 순서

| 단계 | 내용 | 비고 |
|------|------|------|
| 1 | 서버 `list_entries()` `fetch_all` 슬림화 — 이미지 파싱 생략, 컬럼 값만 반환 | 슬림 후 `image_count`/`thumbnail_url` 소비처 grep 확인 |
| 2 | CSS 추가 (`.gallery-card--row`, `.date-group-content(.open)`, `.arrow`) | ~439행 부근 |
| 3 | `buildSelectRow()` 신규 — 이미지 없는 행, 선택 규약(`gallery-card`·`data-entry-id`·`.selected`) 유지 | |
| 4 | `renderGalleryGrid()` `selectMode` 분기 + ▶ 화살표(접기 전용, `stopPropagation`) | `header.onclick` 미수정 |
| 5 | Python 문법 확인 | `py_compile` |
| 6 | 브라우저 테스트 (아래 6장) | 사용자 승인 후 |

## 6. 테스트 계획

### 6.1 제목 사번화 (완료분 확인)
- [ ] 일반/선택 모드 모두 항목 제목이 **사번(이름 다르면 `이름 (사번)`)** 으로 표시
- [ ] 배치명은 그룹 헤더·하단 라벨에 계속 표시

### 6.2 일반 모드 (회귀)
- [ ] 갤러리 목록 정상 로드 (페이지네이션 20개, **이미지 카드 유지**)
- [ ] 날짜 칩/배치명 칩 필터링 정상
- [ ] 상세 모달 오픈 정상

### 6.3 삭제 모드
- [ ] 진입 시 그룹 **접힌 상태**(헤더만) + 즉시 표시(지연 없음)
- [ ] **리스트에 이미지 `<img>` 요청 0건** (DevTools Network 확인) ← 핵심
- [ ] ▶ 클릭 → 텍스트 행 펼침 + ▶ 회전
- [ ] 헤더 행(화살표·체크박스 외) 클릭 → 그룹 전체 선택 토글(기존 유지)
- [ ] 체크박스(전체/그룹/개별) 선택 정상, 접힌 그룹도 ID 기반 선택 가능
- [ ] 그룹 선택 → 펼침 → 행이 선택 상태로 표시
- [ ] **[미리보기] 클릭 → 상세 모달에서 그 1건 이미지 로드**
- [ ] 선택 → 삭제 → 목록 갱신

### 6.4 다운로드 모드
- [ ] 진입 시 그룹 접힘 + 이미지 요청 0건
- [ ] 펼치기 + 체크박스 + 다운로드 정상

### 6.5 부하 확인
- [ ] 모드 진입 후 스크롤 정상(멈춤 해소)
- [ ] `all=1` 응답 JSON 크기·서버 응답 시간 이전 대비 감소(슬림 페이로드 효과)
