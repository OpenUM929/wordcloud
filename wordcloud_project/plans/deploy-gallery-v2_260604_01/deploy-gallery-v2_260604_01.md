# 저장 갤러리 V2 — 상세보기 개선 및 매트릭스 자동 저장 기획서

- **작업명**: deploy-gallery-v2
- **작성일시**: 2026-06-04
- **작업 유형**: 기능 개선 (프론트엔드 + 백엔드 API)
- **상태**: PND (Pending)
- **원본 계획서**: `deploy-image-gallery_260604_01.md`

---

## 1. 개요 (Background)

현재 갤러리(`deploy_gallery.html`)는 **제출용 저장(`save_to_deploy`) 결과**만 조회 가능합니다.

사용자 요구사항:
1. **매트릭스 생성 결과도 자동 저장**되어 갤러리에서 조회 가능해야 함
2. **상세보기**에서 출처(제출용/매트릭스)에 따라 탭으로 분리
3. **칩 필터**(Chip)로 통합/긍정/부정 + **동적 연도**를 다중 선택하여 필터링
4. 필터링된 이미지는 **오름차순**으로 정렬 표시

---

## 2. 목표 (Goals)

1. **매트릭스 생성 결과 자동 인덱싱** — `generate_perspective_matrix()` 호출 시 결과를 `deploy_manifest.json`에 기록
2. **상세보기 출처 탭** — "제출용 저장" / "매트릭스" 탭으로 분리하여 조회
3. **칩 필터(Chip)** — 통합/긍정/부정 + 동적 연도(데이터 기반) 다중 선택
4. **오름차순 정렬** — 연도 기준 오름차순, 같은 연도 내에서는 통합→긍정→부정 순

---

## 3. 범위 (Scope)

### 3.1 In-Scope

- `generate_perspective_matrix()` 결과 자동 인덱싱 (`deploy_manifest.json`)
- 상세보기 UI 탭 분리 (제출용 / 매트릭스)
- 칩 필터 UI (통합/긍정/부정 + 동적 연도)
- 다중 선택 로직 및 필터링
- 오름차순 정렬 적용

### 3.2 Out-of-Scope

- 매트릭스 결과 별도 페이지 생성 (갤러리 상세보기 내에서 통합)
- 삭제/편집 기능
- 데이터베이스 도입

---

## 4. 현재 문제점

### 4.1 매트릭스 생성은 저장되지 않음

`generate_perspective_matrix()`는:
- 셀별 워드클라우드 이미지를 생성하여 **화면 HTML**에 포함
- `save_to_deploy()`와 달리 **파일 저장 없이** 메모리/응답으로만 반환
- 따라서 `deploy_manifest.json`에 기록되지 않음

### 4.2 갤러리 상세보기의 단순 구조

현재 상세보기:
- 통합/긍정/부정 이미지를 그리드로 한꺼번에 표시
- 연도별 `row_results`도 동일 그리드에 합쳐서 표시
- 출처 구분 없음, 필터 없음

---

## 5. 기능 요구사항 (Functional Requirements)

### FR-01: 매트릭스 생성 결과 자동 인덱싱

`generate_perspective_matrix()` 성공 시 `deploy_manifest.json`에 기록.

```json
{
  "entries": [
    {
      "id": "uuid-v4",
      "employee_id": "EMP001",
      "deploy_name": "EMP001",
      "timestamp": "20260604_143052",
      "output_mode": "pseudonym",
      "source": "matrix",
      "row_field": "evaluation_date__year",
      "analysis_type": "nlp",
      "options": { ... },
      "images": {
        "combined": "/outputs/...",
        "positive": "/outputs/...",
        "negative": "/outputs/..."
      },
      "row_results": {
        "2024": { "combined": "...", "positive": "...", "negative": "..." },
        "2025": { "combined": "...", "positive": "...", "negative": "..." }
      }
    }
  ]
}
```

- `source` 필드 추가: `"deploy"`(제출용 저장) 또는 `"matrix"`(매트릭스 생성)
- 기존 제출용 저장 엔트리도 `source: "deploy"`로 간주 (역호환성)

### FR-02: 상세보기 출처 탭

상세 모달 상단에 탭 버튼:

```
┌─────────────────────────────────────┐
│  [제출용 저장]  [매트릭스]           │  ← 탭
├─────────────────────────────────────┤
│                                     │
│  (선택된 탭에 해당하는 이미지만 표시) │
│                                     │
└─────────────────────────────────────┘
```

- 탭 전환 시 이미지 그리드 갱신
- 같은 직원/같은 시간이어도 `source`가 다르면 별도 엔트리로 표시

### FR-03: 칩 필터 (Chip Filter)

```
┌─────────────────────────────────────┐
│  종류:  [통합] [긍정] [부정]        │  ← 다중 선택 가능
│  연도:  [전체] [2023] [2024] [2025] │  ← 데이터 기반 동적 생성, 다중 선택
├─────────────────────────────────────┤
│                                     │
│  (필터링된 이미지만 표시)            │
│                                     │
└─────────────────────────────────────┘
```

**종류 칩**: 통합 / 긍정 / 부정 — 다중 선택 가능 (1개 이상 필수)
**연도 칩**: 해당 엔트리의 `row_results` 키에서 동적 추출 + "전체" 옵션

- 하나도 선택 안 하면 "전체"로 간주
- 다중 선택 시 OR 조건 (통합 OR 긍정, 2024 OR 2025)

### FR-04: 오름차순 정렬

필터링된 이미지를 아래 기준으로 오름차순 정렬:

1. 연도 (오름차순) — `row_results` 키 기준, 최상위 `images`는 연도 없으므로 맨 앞
2. 종류 순서 — 통합 → 긍정 → 부정 (고정 순서)

예시 출력 순서:
```
1. 통합 (최상위 combined)
2. 2024 통합
3. 2024 긍정
4. 2024 부정
5. 2025 통합
6. 2025 긍정
7. 2025 부정
```

---

## 6. 설계 (Design)

### 6.1 백엔드 인덱싱 설계

#### `generate_perspective_matrix()` 변경

`src/services/perspective_service.py`의 `generate_perspective_matrix()` 마지막에:

```python
# 인덱싱
index_entry = {
    "id": str(uuid.uuid4()),
    "employee_id": employee_id,
    "deploy_name": employee_id,
    "timestamp": datetime.now().strftime('%Y%m%d_%H%M%S'),
    "output_mode": options.get('output_mode', 'pseudonym'),
    "source": "matrix",
    "row_field": row_field,
    "analysis_type": analysis_type,
    "options": { ... },
    "images": {
        "combined": result.get('combined'),
        "positive": result.get('positive'),
        "negative": result.get('negative'),
    },
    "row_results": {  # 이미지 URL만 저장
        row_key: {
            "combined": row_val.get('combined'),
            "positive": row_val.get('positive'),
            "negative": row_val.get('negative'),
        }
        for row_key, row_val in (result.get('row_results') or {}).items()
    },
}
_append_to_deploy_manifest(index_entry, employee_id, row_field, analysis_type, options)
```

- 이미지 파일 저장이 이미 `matrix/save-deploy`나 셀 생성 과정에서 이루어지는지 확인 필요
- 만약 이미지가 메모리(Image 객체)만 존재한다면, `generate_perspective_matrix()` 내에서 `save_to_deploy()`와 유사한 파일 저장 로직 추가

#### `_append_to_deploy_manifest()` 변경

기존 `_append_to_deploy_manifest()`는 `result` dict(제출용 저장 반환값)를 받습니다. 매트릭스용으로 오버로드 또는 내부 분기:

```python
def _append_to_deploy_manifest(result_or_entry, employee_id, row_field, analysis_type, options):
    # result_or_entry가 이미 완성된 entry dict이면 그대로 사용
    if isinstance(result_or_entry, dict) and 'source' in result_or_entry:
        entry = result_or_entry
    else:
        # 기존 제출용 저장 result dict 처리
        entry = _build_entry_from_result(result_or_entry, ...)
    
    # 기존 filelock + atomic write 로직 그대로
```

### 6.2 목록 조회 API 변경

`GET /api/perspective/deploy-gallery/list`

**기존 응답에 추가**:
```json
{
  "entries": [
    {
      "id": "uuid",
      "employee_id": "EMP001",
      "deploy_name": "홍길동_EMP001",
      "timestamp": "20260604_143052",
      "output_mode": "real",
      "source": "deploy",
      "image_count": 3,
      "thumbnail_url": "/outputs/..."
    }
  ]
}
```

**새 Query Parameter**:
- `source` (optional): `deploy` | `matrix`

### 6.3 상세 조회 API 변경

`GET /api/perspective/deploy-gallery/detail/<entry_id>`

**변경 없음** — `source` 필드는 entry에 포함되어 있으므로 기존 API 그대로 사용.

### 6.4 UI 설계

#### 상세 모달 구조

```
┌─────────────────────────────────────────────────────┐
│  직원 홍길동 상세 정보                        [X]   │
├─────────────────────────────────────────────────────┤
│  [제출용 저장] [매트릭스]      ← 탭                 │
├─────────────────────────────────────────────────────┤
│  종류: [통합] [긍정] [부정]    ← 칩 (다중 선택)     │
│  연도: [전체] [2023] [2024] [2025]  ← 칩 (다중 선택)│
├─────────────────────────────────────────────────────┤
│  ┌────────┐ ┌────────┐ ┌────────┐                │
│  │ 2024   │ │ 2024   │ │ 2024   │                │
│  │ 통합   │ │ 긍정   │ │ 부정   │                │
│  │ [이미지]│ │ [이미지]│ │ [이미지]│                │
│  └────────┘ └────────┘ └────────┘                │
│  ┌────────┐ ┌────────┐                            │
│  │ 2025   │ │ 2025   │                            │
│  │ 통합   │ │ 긍정   │                            │
│  │ [이미지]│ │ [이미지]│                            │
│  └────────┘ └────────┘                            │
└─────────────────────────────────────────────────────┘
```

#### JavaScript 필터링 로직

```javascript
function filterImages(entry, selectedTypes, selectedYears) {
    const images = [];
    
    // 최상위 images (연도 없음)
    if (selectedYears.has('all') || selectedYears.size === 0) {
        ['combined', 'positive', 'negative'].forEach(type => {
            if (selectedTypes.has(type) && entry.images[type]) {
                images.push({year: null, type, url: entry.images[type]});
            }
        });
    }
    
    // row_results (연도별)
    Object.entries(entry.row_results || {}).forEach(([year, rowData]) => {
        if (selectedYears.has('all') || selectedYears.has(year) || selectedYears.size === 0) {
            ['combined', 'positive', 'negative'].forEach(type => {
                if (selectedTypes.has(type) && rowData[type]) {
                    images.push({year, type, url: rowData[type]});
                }
            });
        }
    });
    
    // 정렬: year 오름차순 (null은 맨 앞), type 순서: combined < positive < negative
    const typeOrder = {combined: 0, positive: 1, negative: 2};
    images.sort((a, b) => {
        if (a.year === null && b.year !== null) return -1;
        if (a.year !== null && b.year === null) return 1;
        if (a.year !== b.year) return String(a.year).localeCompare(String(b.year));
        return typeOrder[a.type] - typeOrder[b.type];
    });
    
    return images;
}
```

---

## 7. 구현 단계 (Implementation Steps)

### Phase 1: 백엔드 매트릭스 인덱싱 (0.5일)

1. **`src/services/perspective_service.py`**
   - `_append_to_deploy_manifest()` — `source` 필드 처리 및 매트릭스 entry 지원
   - `generate_perspective_matrix()` — 완료 시 `_append_to_deploy_manifest()` 호출 추가
   - 이미지가 메모리에만 있는 경우 파일 저장 로직 추가 확인/구현

2. **`src/routes/perspective_routes.py`**
   - `api_generate_matrix()` — 응답에 `source: "matrix"` 포함 확인
   - 목록 API에 `source` query parameter 추가

### Phase 2: 프론트엔드 상세보기 개선 (1일)

1. **`web/templates/deploy_gallery.html`**
   - 상세 모달에 탭 UI 추가 (제출용 / 매트릭스)
   - 칩 필터 UI 추가 (종류: 통합/긍정/부정, 연도: 동적 생성)
   - 다중 선택 로직 + 필터링 함수
   - 오름차순 정렬 적용
   - 이미지 그리드 동적 렌더링

### Phase 3: 통합 테스트 (0.5일)

1. 매트릭스 생성 → 갤러리 목록 확인
2. 상세보기 탭 전환 확인
3. 칩 필터 다중 선택 + 정렬 확인
4. 권한 체크 (비관리자 `real` 데이터 제외) 확인

---

## 8. 테스트 계획

| 테스트 ID | 내용 | 방법 | 기대 결과 |
|-----------|------|------|-----------|
| T-01 | 매트릭스 생성 인덱싱 | 매트릭스 생성 API 호출 | `deploy_manifest.json`에 `source: "matrix"` entry 추가 |
| T-02 | 목록 source 필터 | `?source=matrix` 쿼리 | 매트릭스 결과만 반환 |
| T-03 | 상세 탭 전환 | 모달에서 탭 클릭 | 해당 source 이미지만 표시 |
| T-04 | 칩 필터 다중 선택 | 통합+긍정, 2024+2025 선택 | OR 조건 필터링 결과 |
| T-05 | 오름차순 정렬 | 다양한 연도/종류 조합 | 연도 오름차순 → 종류 순서 통합→긍정→부정 |
| T-06 | 동적 연도 칩 | row_results 키가 다른 entry | 해당 entry의 연도만 칩으로 표시 |

---

## 9. 관련 파일

| 파일 | 역할 |
|------|------|
| `src/services/perspective_service.py` | `generate_perspective_matrix()`, `_append_to_deploy_manifest()` 수정 |
| `src/routes/perspective_routes.py` | `api_generate_matrix()`, 목록 API `source` 파라미터 |
| `web/templates/deploy_gallery.html` | 상세 모달 탭/칩 필터/정렬 UI |

---

## 10. 완료 기준 (Definition of Done)

- [ ] 매트릭스 생성 시 `deploy_manifest.json`에 `source: "matrix"`로 기록된다.
- [ ] 갤러리 목록 API에 `source` 필터가 추가된다.
- [ ] 상세 모달에 "제출용 저장" / "매트릭스" 탭이 추가된다.
- [ ] 상세 모달에 통합/긍정/부정 칩 필터가 추가된다.
- [ ] 상세 모달에 동적 연도 칩 필터가 추가된다.
- [ ] 칩 필터는 다중 선택이 가능하다.
- [ ] 필터링 결과는 연도 오름차순, 종류 순서(통합→긍정→부정)로 정렬된다.
- [ ] 비관리자는 `real` 모드 데이터를 볼 수 없다.

---

*본 계획서는 `.clinerules/core/00-core/03.plan-mode.md` 지침에 따라 작성되었다.*
*실제 코드 변경은 사용자가 "수행"을 명시적으로 요청할 때까지 대기한다.*

**계획서 저장 위치**: `D:\dev\wordcloud\wordcloud_project\plans\deploy-gallery-v2_260604_01\deploy-gallery-v2_260604_01.md`
