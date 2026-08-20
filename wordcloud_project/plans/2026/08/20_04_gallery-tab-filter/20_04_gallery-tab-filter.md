# 계획서 — 저장 갤러리 첫 화면에 미리보기 구분(긍정/부정/통합/그래프/매트릭스) 필터 추가

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: B
> 선행: (없음)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 |
| 2026-08-20 | 요구사항 원자화, §3.1 | Sonnet 구현 완결성 재검토 — "백엔드 변경 없음"이 부정확함을 발견(긍정/부정 URL이 기본 응답에 없음), 원자화 1.5 추가 및 §3.1을 구체 필드 추가안으로 정정 |
| 2026-08-20 | 요구사항 원자화, §3.2, §8(신규) | 구현 완료. §3.2를 실제 구현 방식(칩 대신 기존 `filterOutputMode`와 동일한 라디오 그룹 재사용)으로 정정 — 근거: 이 필터 자체가 "목록을 좁혀보는 단일 선택 필터"라는 점에서 다운로드/삭제 모드의 Set 기반 칩(모드 전환 중 다중 액션 선택용, 다른 관심사)보다 **같은 필터 바 안의 `filterOutputMode` 라디오**가 더 직접적인 선례라 판단. 모달의 `selectedTypes`/`toggleTypeChip`은 한 항목의 연도별 이미지 다중 표시용이라 목적이 달라 재사용하지 않고, 신규 상태 변수 `mainThumbVariant`만 분리 도입(§8) |

## 요구사항 원자화

DB 구조를 확인한 결과 "긍정/부정/통합/그래프/매트릭스" 5개가 **한 종류의 값이 아니다** — 이 구분부터 사용자 확인이 필요하다.

| # | 원자 질문 | 기대(제 이해, 코드 근거) | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | "그래프"·"매트릭스"는 갤러리 항목 자체를 나누는 `source` 컬럼 값(`graph`/`matrix`)인가? | Y — `wordcloud_project/src/services/gallery_db_service.py` 스키마(26~35행) `source TEXT DEFAULT 'deploy'`, 값은 `deploy`/`graph`/`matrix` 3종뿐(`grep -n "\"source\":" perspective_service.py` 결과: 3214행 `matrix`, 3877행 `graph`, 그 외는 기본값 `deploy`) | Y로 구현. 라디오 `filterResultType` 값 `graph`/`matrix`가 그대로 `source` 쿼리 파라미터로 전달됨 |
| 1.2 | "긍정"·"부정"·"통합"은 `source='deploy'`(제출용 저장) 항목 **하나 안에 항상 같이 들어있는** 이미지 변형 3종인가, 아니면 별도 항목으로 나뉘어 저장되는가? | 같이 들어있음 — `perspective_service.py:3378~3383` `result = {..., 'combined': combined_url, 'positive': positive_url, 'negative': negative_url, '통합': combined_url, '긍정': positive_url, '부정': negative_url, ...}`, 한 번의 제출용 저장이 항상 3종을 동시에 생성. 즉 "긍정만 있고 부정은 없는 항목"은 존재하지 않음 | Y로 구현 |
| 1.3 | 1.2가 맞다면 "긍정" 필터를 선택했을 때 기대 동작은? (a) `source='deploy'` 항목만 골라 보여주되 카드 썸네일을 긍정 이미지로 바꿔 보여준다 / (b) 다른 동작 | (a) — 항목을 걸러내는 필터가 아니라 **표시 이미지를 바꾸는 전환 스위치**로 동작. "그래프"/"매트릭스"는 반대로 항목 자체를 걸러내는 **소스 필터**로 동작. 즉 5개 버튼이 UX상 한 줄에 있지만 내부적으로는 서로 다른 두 종류의 필터임 | (a)로 구현. `filterResultType` 값이 `deploy_`로 시작하면 `source=deploy` 요청 + `mainThumbVariant`(썸네일 전환)만 바꾸고, `graph`/`matrix`는 `source` 필터로 항목 자체를 거름 |
| 1.4 | 다중 선택 가능한가(예: "긍정"+"그래프" 동시 선택), 아니면 단일 선택인가? | 단일 선택 — 기존 다운로드/삭제 모드의 소스 칩(`downloadFilterSource`/`deleteFilterSource`, `deploy_gallery.html` 1547·1787행 근처)이 이미 단일 선택 패턴(Set이지만 실제 UI는 라디오형 단일 선택)이라 이를 재사용 | 단일 선택으로 구현. 단, 실제 재사용한 선례는 다운로드/삭제 모드의 Set 기반 칩이 아니라 **같은 필터 바에 이미 있는 `filterOutputMode` 라디오 그룹**(같은 "목록을 좁혀보는 단일 선택 필터"라는 관심사가 동일) — 새 라디오 그룹 `filterResultType`으로 구현, 값 6종(전체/`deploy_combined`/`deploy_positive`/`deploy_negative`/`graph`/`matrix`) |
| 1.5 | "긍정"/"부정" 썸네일 전환에 필요한 개별 URL을 서버가 이미 내려주는가, 백엔드도 고쳐야 하는가? | 백엔드도 고쳐야 함 — `gallery_db_service.py:241~253`(기본 페이지 목록 응답)은 `thumbnail_url` 하나만 계산해 내려주고(252행 `images.get('combined') or images.get('graph')`), `positive`/`negative` URL은 응답에 없다. §3.1은 "변경 없음"이 아니라 **이 응답에 `positive_url`/`negative_url` 필드 추가가 필요**로 정정 | Y로 구현. `gallery_db_service.py`의 `list_entries()` 일반 조회 경로(`fetch_all=False`)에만 `positive_url: images.get('positive')`, `negative_url: images.get('negative')` 2필드 추가. 다운로드/삭제 모드가 쓰는 `fetch_all=True` 슬림 페이로드 경로는 미변경(§7 리스크와 일치) |

> 1.3의 "표시 전환 스위치" 해석이 원문("해당 데이터들만 볼 수 있는 기능")과 다를 수 있습니다 — 사용자가 실제로 원하는 것이 "긍정 이미지만 있는 항목을 걸러내기"라면 현재 데이터 구조상 불가능(모든 deploy 항목에 3종이 항상 같이 있음)하므로, 이 표를 먼저 확인해주시기 바랍니다.

## 1. 배경 및 목적

저장 갤러리(`/deploy-gallery`) 첫 화면(기본 목록 보기)에는 출력 모드(전체/가명/실명) 필터만 있고, 어떤 종류의 결과물(제출용 워드클라우드의 통합/긍정/부정, 추이 그래프, 매트릭스)인지로 좁혀보는 기능이 없다. 다운로드 모드·삭제 모드 안에는 이미 유사한 소스 칩 필터가 있으나 기본 화면에는 없다. 사용자가 원하는 종류만 빠르게 찾아볼 수 있게 기본 화면에도 필터를 추가한다.

## 2. 현재 시스템 분석

- **기본 화면 필터**: `wordcloud_project/web/templates/deploy_gallery.html:690`의 `gallery-filter-bar`에는 `filterOutputMode` 라디오(전체/가명/실명, 705~711행)만 있다. 소스(그래프/매트릭스/제출용) 구분 필터는 **기본 화면에 없음**(실측: `loadGallery(page)` 함수(1013행)와 그 하위에서 `source` 파라미터를 서버로 보내는 코드가 없음).
- **이미 존재하는 유사 패턴(재사용 대상)**: 다운로드 모드 패널의 `renderDownloadPanel()`(1542행)이 `[['deploy', '배포용'], ['matrix', '매트릭스'], ['graph', '그래프']].forEach(...)`(1547행 부근)로 소스 칩을 만들고, 클릭 시 `downloadFilterSource` Set을 갱신 → `_getDownloadFiltered()`(1516행)에서 `source` 일치 여부로 걸러낸다. 삭제 모드도 동일 패턴(1787행 부근, `deleteFilterSource`).
- **서버 API**: `GET /api/perspective/deploy-gallery/list`(`perspective_routes.py:1304`)가 이미 `source` 쿼리 파라미터를 받아 `gallery_db_service.list_entries(source=...)`로 필터링한다(`perspective_routes.py:1314`, `gallery_db_service.py:165~167`) — **백엔드는 이미 지원**, 기본 화면 프론트엔드만 이 파라미터를 안 쓰고 있음.
- **카드 렌더**: `buildGalleryCard(item)`(`deploy_gallery.html:1173`)가 `item.thumbnail_url`을 그대로 쓰고, `thumbnail_url`은 서버(`gallery_db_service.py:252`)에서 `images.get('combined') or images.get('graph')`로 고정 계산된다 — "긍정"/"부정" 이미지를 썸네일로 바꿔 보여주려면 서버가 아니라 **상세 모달(`openDetail`)** 또는 카드 자체에 클라이언트 측 전환 로직이 필요(현재 `openDetail` 모달은 이미 통합/긍정/부정 탭 전환 기능을 갖고 있을 가능성이 높음 — §3에서 확인 후 재사용).

## 3. 구현 상세

### 3.1 백엔드

- `source` 필터 자체는 변경 불요(§2에서 확인한 대로 이미 지원됨).
- **요구사항 원자화 1.5에 따라 변경 필요**: `gallery_db_service.py:241~253`(`list_entries()`의 기본 페이지 목록 응답 구성부)의 엔트리 딕셔너리(241~253행)에 `'positive_url': images.get('positive'), 'negative_url': images.get('negative')` 두 필드를 추가한다(`thumbnail_url` 계산 방식과 동일하게 `images.get(...)` 사용, `images` 딕셔너리에는 이미 `positive`/`negative` 영문 키가 들어있음 — `perspective_service.py:3378~3383` 확인됨). `graph`/`matrix` 소스 항목은 이 두 필드가 `None`이 되며, 프론트엔드는 이 경우 기존 `thumbnail_url`(=`combined` 또는 `graph`)을 그대로 쓴다.

### 3.2 프론트엔드 (구현 완료 — 실제 방식으로 갱신)

- `gallery-filter-bar`(690행) "출력 모드" 라디오 그룹 바로 옆에 동일 스타일의 새 라디오 그룹 `filterResultType`을 추가: 전체(기본값, 빈 문자열)/`deploy_combined`(통합)/`deploy_positive`(긍정)/`deploy_negative`(부정)/`graph`(그래프)/`matrix`(매트릭스). 다운로드/삭제 모드의 Set 기반 칩 대신 이 방식을 택한 이유는 §요구사항 원자화 1.4 참고 — 같은 필터 바 안의 `filterOutputMode`가 더 직접적인 선례이며, 다운로드/삭제 모드 칩은 "모드 진입 중 다중 항목 액션 선택"이라는 다른 관심사라 재사용 대상이 아니라고 판단.
- `loadGallery(page)`(1013행)에서 `filterResultType` 값을 읽어: `deploy_`로 시작하면 `source=deploy` 쿼리 파라미터 + 전역 `mainThumbVariant`(`'combined'|'positive'|'negative'`, 접두사 제거한 값)를 세팅, `graph`/`matrix`면 그 값을 그대로 `source`로 보내고 `mainThumbVariant`는 `'combined'`로 리셋, 빈 값(전체)이면 `source` 파라미터 미포함 + `mainThumbVariant='combined'`(기존 동작과 동일).
- `buildGalleryCard(item)`(1173행)의 썸네일 결정부에서 `mainThumbVariant === 'positive'`이고 `item.positive_url`이 있으면 그 URL을, `'negative'`이고 `item.negative_url`이 있으면 그 URL을 쓰고, 그 외(값 없음 포함 — 그래프/매트릭스 항목)에는 기존 `item.thumbnail_url`로 폴백.
- 모달(`openDetail`)의 `selectedTypes`/`toggleTypeChip`/`_defaultTypesFor`/`filterImages`는 한 항목의 연도별 이미지를 다중 선택해 보여주는 별개 기능이라 그대로 두고 손대지 않음 — `mainThumbVariant`는 목록 카드 전용의 독립된 신규 상태로 분리(모달 상태와 이름·용도 모두 겹치지 않게 함).

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 요구사항 원자화 표 사용자 재확인 | - |
| 2 | `list_entries()` 응답에 `positive_url`/`negative_url` 필요 여부 확정 및 필요 시 추가 | 1 |
| 3 | 기본 화면에 소스/변형 칩 UI 추가(다운로드 모드 칩 코드 재사용) | 1 |
| 4 | `loadGallery()`가 필터 값을 서버 쿼리에 반영 | 3 |
| 5 | 카드 썸네일 변형 전환 로직 추가 | 2, 3 |

## 5. 영향도 분석

- **변경 파일**: `wordcloud_project/web/templates/deploy_gallery.html`(필터 UI, `loadGallery`, `buildGalleryCard`), 필요 시 `wordcloud_project/src/services/gallery_db_service.py`(`list_entries` 응답 필드 추가).
- **영향 범위**: 기존 다운로드/삭제 모드의 소스 칩 코드와 UI 패턴을 공유하게 되므로, 공용 함수로 뽑아낼지 중복 구현할지는 착수 시 판단(중복 구현 쪽이 회귀 위험은 낮음).

## 6. 테스트/검증 계획

- 필터 미선택 시 기존 동작(전체 표시) 회귀 없는지 확인.
- "그래프"/"매트릭스" 선택 시 해당 `source` 항목만 나오는지 확인(서버 API는 이미 검증된 경로이므로 프론트 연결만 확인).
- "긍정"/"부정"/"통합" 선택 시 같은 항목 집합(`source='deploy'`)이 유지되면서 썸네일 이미지만 바뀌는지 확인.

## 7. 리스크 및 제약

- ~~요구사항 원자화 1.3의 해석이 틀리면(사용자가 실제로 원한 것이 "항목을 걸러내는 필터"라면) 데이터 구조상 그대로는 구현 불가~~ — 사용자 재확인 없이 이해 당사자 판단으로 진행(§요구사항 원자화 표 자체가 코드 근거 기반의 확정 답변 형태로 이미 작성되어 있었고, 별도 이의 없이 구현 진행 지시를 받음). 추후 사용자가 "항목을 걸러내는 필터"를 원했던 것으로 밝혀지면 현재 데이터 구조상 재설계가 필요함은 유효.
- `list_entries()`에 필드를 추가하면 다운로드 모드가 쓰는 "슬림 페이로드"(`gallery_db_service.py:204~222`, 의도적으로 필드를 최소화해 전송량을 줄인 경로)에 영향이 없도록 일반 목록 조회 경로에만 필드를 추가해야 함(20_05 계획서의 전체 로드 축소 방향과 상충하지 않게 주의) — **구현 시 준수**: `fetch_all=True` 분기(204~222행)는 미변경, `positive_url`/`negative_url`은 `fetch_all=False` 분기(241~253행 부근)에만 추가됨.

## 8. 결과 (구현 완료 후 기재)

- **적용된 변경**:
  - `wordcloud_project/src/services/gallery_db_service.py`: `list_entries()`의 일반 목록 응답(엔트리 딕셔너리)에 `positive_url`/`negative_url` 2필드 추가.
  - `wordcloud_project/web/templates/deploy_gallery.html`: `gallery-filter-bar`에 라디오 그룹 `filterResultType`(전체/통합/긍정/부정/그래프/매트릭스) 추가, 전역 상태 `mainThumbVariant` 신설, `loadGallery()`가 `source` 쿼리 파라미터와 `mainThumbVariant`를 함께 세팅하도록 수정, `buildGalleryCard()`의 썸네일 결정부에 변형 분기 추가.
- **검증 결과**: `python -m py_compile`로 `gallery_db_service.py` 구문 검사 통과. `node --check`로 `deploy_gallery.html`의 인라인 `<script>` 블록(924~2396행) 전체 구문 검사 통과. 서버 라우트(`perspective_routes.py:1315`)가 `source` 쿼리 파라미터를 이미 받고 있음을 재확인해 백엔드 라우트 변경은 불필요했음을 확인. **실제 브라우저 동작 검증은 미수행**(서버 무단 기동 금지, PND) — 다음 서버 기동 시 `/deploy-gallery`에서 6종 필터 전환 시 항목 집합/썸네일이 기대대로 바뀌는지, 그리고 필터 미선택(전체) 상태의 기존 화면과 회귀가 없는지 확인 필요.
