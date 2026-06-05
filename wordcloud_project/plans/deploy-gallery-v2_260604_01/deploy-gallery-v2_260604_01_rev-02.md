# 저장 갤러리 V2 — 상세보기 개선 및 매트릭스 자동 저장 기획서 (rev-02)

- **작업명**: deploy-gallery-v2
- **작성일시**: 2026-06-04
- **작업 유형**: 기능 개선 (프론트엔드 + 백엔드 API)
- **상태**: PND (Pending)
- **원본 계획서**: `deploy-gallery-v2_260604_01.md`
- **개정 이력**:
  - rev-01: Critical 이슈 2건(FR-01 이미지 경로, 긍/부정 분리), High 이슈 2건(all_employees, 썸네일) 수정
  - rev-02: 상세 모달 진입 방식(openDetail 시그니처 + 직원별 엔트리 조회 API) 설계 보완

---

## 개정 요약 (rev-01 대비 변경점)

| 구분 | rev-01 | rev-02 |
|------|--------|--------|
| 모달 진입 시그니처 | `openDetail(entryId)` — 단일 ID만 | `openDetail(entryId, employeeId)` — ID + 직원ID 전달 |
| 탭 데이터 로딩 | 미설계 | 신규 엔드포인트 `employee-entries/<employee_id>` + 클릭 entry detail 병렬 호출 |
| 반대 source 탭 | 미설계 | 최신 1건 자동 조회, 없으면 "데이터 없음" 표시 |
| 기본 활성 탭 | 미정의 | 클릭한 카드의 source가 기본 탭 |

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
- 갤러리 카드에 출처 배지 표시
- **신규 API**: `GET /api/perspective/deploy-gallery/employee-entries/<employee_id>`

### 3.2 Out-of-Scope

- 매트릭스 결과 별도 페이지 생성
- 삭제/편집 기능
- 데이터베이스 도입
- `all_employees=True` 전체 직원 매트릭스 인덱싱 (단일 직원만 인덱싱)
- 매트릭스 셀 긍/부정 이미지 신규 생성 (combined만 저장)

---

## 4. 현재 구조 이해 (구현 전 필수)

### 4.1 `generate_perspective_matrix()` 반환 구조

```python
# perspective_service.py:1269
{
  'employee_id': 'EMP001',
  'row_field': 'evaluation_date__year',
  'rows': ['2024', '2025'],
  'columns': ['전체'],
  'matrix': {
    '2024': {
      '전체': {
        'evaluation_count': 10,
        'nlp': {
          'wordcloud_url': '/outputs/유저/EMP001/evaluation_date__year_all_nlp/2024_전체.png',
          'top_words': {...},
          'avg_sentiment': {...}
        }
      }
    },
    '2025': { ... }
  },
  ...
}
```

- `combined/positive/negative` 최상위 키 **없음**
- 이미지 URL은 `matrix[row_key][col_key]['nlp']['wordcloud_url']`에 위치
- 파일은 이미 `outputs/유저/` 하위에 저장됨 (`_generate_nlp_cell`이 `save_path` 있을 때 저장)
- `/outputs/유저/<path>` 라우트가 존재하여 HTTP 접근 가능

### 4.2 `save_to_deploy()` 반환 구조 (비교용)

```python
{
  'name': '홍길동_EMP001',
  'timestamp': '20260604_143052',
  'combined': '/outputs/배포/통합/EMP001_...png',
  'positive': '/outputs/배포/긍정/EMP001_...png',
  'negative': '/outputs/배포/부정/EMP001_...png',
  'row_results': {
    '2024': {'combined': ..., 'positive': ..., 'negative': ...},
    '2025': {'combined': ..., 'positive': ..., 'negative': ...}
  }
}
```

### 4.3 매트릭스 이미지 인덱싱 전략

매트릭스 셀은 **combined만** 존재하므로:
- `row_results[year].combined` = `matrix[year][first_col]['nlp']['wordcloud_url']`
- `row_results[year].positive` = `null`
- `row_results[year].negative` = `null`
- `images.combined` (썸네일) = 첫 번째 행의 combined (없으면 null)
- `images.positive` = `null`
- `images.negative` = `null`

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
      "options": { "...": "..." },
      "images": {
        "combined": "/outputs/유저/EMP001/.../2024_전체.png",
        "positive": null,
        "negative": null
      },
      "row_results": {
        "2024": {
          "combined": "/outputs/유저/EMP001/.../2024_전체.png",
          "positive": null,
          "negative": null
        },
        "2025": {
          "combined": "/outputs/유저/EMP001/.../2025_전체.png",
          "positive": null,
          "negative": null
        }
      }
    }
  ]
}
```

- `source` 필드: `"deploy"` 또는 `"matrix"`
- 기존 엔트리는 `source` 필드 없음 → `source: "deploy"` 로 간주 (역호환)
- `all_employees=True` 호출은 인덱싱하지 않음

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

- 클릭한 카드의 source가 기본 활성 탭
- 반대 source 데이터가 없으면 탭은 표시하되 "데이터 없음" 메시지 출력
- 탭 전환 시 이미지 그리드 및 칩 필터 갱신

### FR-03: 칩 필터 (Chip Filter)

```
┌─────────────────────────────────────┐
│  종류:  [통합] [긍정] [부정]        │  ← 다중 선택
│  연도:  [전체] [2023] [2024] [2025] │  ← 데이터 기반 동적 생성, 다중 선택
├─────────────────────────────────────┤
│  (필터링된 이미지만 표시)            │
└─────────────────────────────────────┘
```

**종류 칩**:
- `source='matrix'` 엔트리: `[긍정]`, `[부정]` 칩 비활성화(회색), `[통합]`만 선택 가능
- `source='deploy'` 엔트리: 3종 모두 활성화

**연도 칩**: 현재 탭 엔트리의 `row_results` 키에서 동적 추출 + "전체" 옵션

- 선택 없으면 "전체"로 간주
- 다중 선택 시 OR 조건

### FR-04: 오름차순 정렬

예시 출력 순서 (deploy 엔트리):
```
1. 통합 (최상위 combined)   ← row 없음, 맨 앞
2. 2024 통합
3. 2024 긍정
4. 2024 부정
5. 2025 통합
...
```

예시 출력 순서 (matrix 엔트리):
```
1. 2024 통합
2. 2025 통합
```

---

## 6. 설계 (Design)

### 6.1 백엔드 인덱싱 설계

#### `generate_perspective_matrix()` 변경

`src/services/perspective_service.py`의 `generate_perspective_matrix()` 마지막 `return result` 직전에 추가:

```python
# perspective_service.py:1337~1352 — return result 직전
# all_employees 케이스는 이 함수가 단일 직원 단위로 호출되므로 여기서 인덱싱
if result.get('matrix') and result.get('rows'):
    _index_matrix_to_manifest(result, employee_id, row_field, col_mode, analysis_type, options)

return result
```

#### `_index_matrix_to_manifest()` 신규 함수

```python
def _index_matrix_to_manifest(matrix_result, employee_id, row_field, col_mode, analysis_type, options):
    """매트릭스 결과를 deploy_manifest.json에 인덱싱."""
    matrix = matrix_result.get('matrix', {})
    rows = matrix_result.get('rows', [])
    columns = matrix_result.get('columns', [])

    first_col = columns[0] if columns else None
    if not first_col:
        return

    row_results = {}
    for row_key in rows:
        cell = matrix.get(row_key, {}).get(first_col, {})
        nlp_data = cell.get('nlp') or cell.get(analysis_type, {})
        combined_url = nlp_data.get('wordcloud_url') if isinstance(nlp_data, dict) else None
        if combined_url:
            row_results[row_key] = {
                'combined': combined_url,
                'positive': None,
                'negative': None,
            }

    thumbnail = next((v['combined'] for v in row_results.values() if v['combined']), None)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    entry = {
        "id": str(uuid.uuid4()),
        "employee_id": employee_id,
        "deploy_name": employee_id,
        "timestamp": ts,
        "output_mode": options.get('output_mode', 'pseudonym'),
        "source": "matrix",
        "row_field": row_field,
        "col_mode": col_mode,
        "analysis_type": analysis_type,
        "options": {
            "wordcloud_pos": options.get('wordcloud_pos', ['Noun']),
            "background_color": options.get('background_color', 'white'),
            "width": options.get('width', 400),
            "height": options.get('height', 300),
            "max_words": options.get('max_words', 80),
            "apply_emotion_colors": options.get('apply_emotion_colors', True),
            "remove_profanity": options.get('remove_profanity', False),
        },
        "images": {
            "combined": thumbnail,
            "positive": None,
            "negative": None,
        },
        "row_results": row_results,
    }

    lock_path = DEPLOY_MANIFEST_PATH + '.lock'
    try:
        if FileLock:
            with FileLock(lock_path, timeout=10):
                _write_manifest_entry(entry)
        else:
            _write_manifest_entry(entry)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Matrix manifest write failed: {e}")
```

#### `_append_to_deploy_manifest()` 변경 없음

### 6.2 목록 조회 API 변경

`GET /api/perspective/deploy-gallery/list`

**새 Query Parameter**: `source` (optional): `deploy` | `matrix`

```python
# perspective_routes.py — api_deploy_gallery_list() 내 필터 루프 수정
source_filter = request.args.get('source', '').strip()

for entry in entries:
    # source 역호환: 필드 없으면 'deploy'로 간주
    entry_source = entry.get('source', 'deploy')
    if source_filter and entry_source != source_filter:
        continue
    # ... 기존 필터 로직 유지 ...

    images = entry.get('images', {})
    row_results = entry.get('row_results', {})

    # image_count: 최상위 images + row_results 전체 포함
    top_count = sum(1 for v in images.values() if v)
    row_count = sum(
        1 for rv in row_results.values()
        for v in (rv.values() if isinstance(rv, dict) else [])
        if v
    )

    list_item = {
        "id": entry.get('id'),
        "employee_id": entry.get('employee_id'),
        "deploy_name": entry.get('deploy_name'),
        "timestamp": entry.get('timestamp'),
        "output_mode": entry.get('output_mode'),
        "source": entry_source,
        "image_count": top_count + row_count,
        "thumbnail_url": images.get('combined'),
    }
    filtered.append(list_item)
```

### 6.3 신규 API: 직원별 최신 엔트리 조회

`GET /api/perspective/deploy-gallery/employee-entries/<employee_id>`

모달 진입 시 같은 직원의 deploy/matrix 양쪽 최신 엔트리를 한 번에 반환합니다.

**응답 구조**:

```json
{
  "success": true,
  "employee_id": "EMP001",
  "deploy": { /* 최신 deploy entry 전체 (detail 수준), 없으면 null */ },
  "matrix": { /* 최신 matrix entry 전체 (detail 수준), 없으면 null */ }
}
```

**구현**:

```python
@perspective_bp.route('/deploy-gallery/employee-entries/<employee_id>', methods=['GET'])
def api_employee_entries(employee_id):
    """같은 직원의 deploy/matrix 양쪽 최신 entry를 반환."""
    is_admin = _is_admin()

    manifest = {"entries": []}
    if os.path.exists(DEPLOY_MANIFEST_PATH):
        try:
            with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json_lib.load(f)
        except Exception:
            pass

    latest = {'deploy': None, 'matrix': None}

    for entry in manifest.get('entries', []):
        if entry.get('employee_id') != employee_id:
            continue
        if not is_admin and entry.get('output_mode') == 'real':
            continue

        src = entry.get('source', 'deploy')
        if src not in latest:
            continue

        # 더 최신 타임스탬프로 교체
        current = latest[src]
        if current is None or entry.get('timestamp', '') > current.get('timestamp', ''):
            latest[src] = entry

    return jsonify({
        'success': True,
        'employee_id': employee_id,
        'deploy': latest['deploy'],
        'matrix': latest['matrix'],
    })
```

### 6.4 상세 조회 API 변경 없음

`GET /api/perspective/deploy-gallery/detail/<entry_id>` — 기존 그대로.

### 6.5 UI 설계

#### 갤러리 카드 — 출처 배지 추가

카드 `.thumb-wrap`에 `position: relative` 추가, 배지 오버레이:

```html
<div class="thumb-wrap" style="position:relative;">
  ${thumbHtml}
  <div class="source-badge source-badge--${src}">
    ${src === 'matrix' ? '매트릭스' : '제출용'}
  </div>
</div>
```

```css
.source-badge {
    position: absolute; top: 6px; right: 6px;
    font-size: 10px; font-weight: 700;
    padding: 2px 6px; border-radius: 10px;
    pointer-events: none;
}
.source-badge--deploy { background: #d1ecf1; color: #0c5460; }
.source-badge--matrix { background: #fce8b2; color: #6d4c0a; }
```

#### 상세 모달 구조

```
┌─────────────────────────────────────────────────────┐
│  직원 EMP001 상세 정보                        [X]   │
├─────────────────────────────────────────────────────┤
│  [제출용 저장] [매트릭스]      ← 탭                 │
├─────────────────────────────────────────────────────┤
│  종류: [통합] [긍정*] [부정*]  ← (* matrix시 비활성) │
│  연도: [전체] [2024] [2025]    ← 현재 탭 entry 기준  │
├─────────────────────────────────────────────────────┤
│  (이미지 그리드)                                    │
└─────────────────────────────────────────────────────┘
```

#### JavaScript 모달 진입 및 탭 로직

**카드 렌더링**: `openDetail(item.id, item.employee_id)` 로 변경

```javascript
card.onclick = () => openDetail(item.id, item.employee_id);
```

**openDetail 전체 흐름**:

```javascript
let currentEntries = { deploy: null, matrix: null };
let currentTab = 'deploy';
let selectedTypes = new Set(['combined']);
let selectedYears = new Set();

async function openDetail(entryId, employeeId) {
    const modal = document.getElementById('detailModal');
    const body  = document.getElementById('modalBody');
    body.innerHTML = '<p style="text-align:center;padding:30px;color:#999;">로드 중...</p>';
    modal.classList.add('open');

    // 클릭된 entry detail + 직원별 양쪽 최신 entry 병렬 조회
    const [detailRes, employeeRes] = await Promise.all([
        fetch(`/api/perspective/deploy-gallery/detail/${encodeURIComponent(entryId)}`),
        fetch(`/api/perspective/deploy-gallery/employee-entries/${encodeURIComponent(employeeId)}`),
    ]);
    const detailData   = await detailRes.json();
    const employeeData = await employeeRes.json();

    if (!detailData.success) {
        body.innerHTML = `<p style="color:#dc3545;">오류: ${detailData.error}</p>`;
        return;
    }

    const clickedEntry  = detailData.entry;
    const clickedSource = clickedEntry.source || 'deploy';

    // employee-entries 응답으로 양쪽 탭 채우기
    // 클릭한 entry는 detail 버전(풀 데이터)으로 덮어씀
    currentEntries.deploy  = employeeData.deploy  || null;
    currentEntries.matrix  = employeeData.matrix  || null;
    currentEntries[clickedSource] = clickedEntry;   // 클릭 entry는 detail 버전 우선

    // 기본 탭 = 클릭한 카드의 source
    currentTab = clickedSource;

    document.getElementById('modalTitle').textContent =
        `${escapeHtml(clickedEntry.deploy_name || clickedEntry.employee_id)} 상세 정보`;

    renderModal();
}

// 탭 전환
function switchTab(tabName) {
    currentTab = tabName;
    selectedTypes = new Set(['combined']);  // 탭 바뀔 때 칩 초기화
    selectedYears = new Set();
    renderModal();
}

// 모달 전체 재렌더
function renderModal() {
    renderTabs();
    const entry = currentEntries[currentTab];
    if (!entry) {
        renderNoData();
        return;
    }
    updateChipAvailability(entry.source || 'deploy');
    renderYearChips(entry);
    renderFilteredImages(entry);
}

// 탭 버튼 렌더
function renderTabs() {
    const tabsEl = document.getElementById('modalTabs');
    ['deploy', 'matrix'].forEach(src => {
        const btn = tabsEl.querySelector(`[data-tab="${src}"]`);
        btn.classList.toggle('active', src === currentTab);
        btn.disabled = false;
    });
}

// source에 따라 긍정/부정 칩 활성화 여부
function updateChipAvailability(source) {
    const posChip = document.getElementById('chipPositive');
    const negChip = document.getElementById('chipNegative');
    const isMatrix = source === 'matrix';
    posChip.disabled = isMatrix;
    negChip.disabled = isMatrix;
    posChip.classList.toggle('chip--disabled', isMatrix);
    negChip.classList.toggle('chip--disabled', isMatrix);
    if (isMatrix) {
        selectedTypes = new Set(['combined']);
    }
}

// 연도 칩 동적 생성 (현재 탭 entry 기준)
function renderYearChips(entry) {
    const container = document.getElementById('yearChips');
    const years = Object.keys(entry.row_results || {}).sort();
    container.innerHTML = '';
    // '전체' 칩
    const allBtn = makeChip('전체', 'all', selectedYears.size === 0 || selectedYears.has('all'));
    container.appendChild(allBtn);
    years.forEach(y => {
        container.appendChild(makeChip(y, y, selectedYears.has(y)));
    });
}

// 이미지 필터링 + 정렬
function filterImages(entry, selectedTypes, selectedYears) {
    const images = [];
    const typeOrder = { combined: 0, positive: 1, negative: 2 };

    // 최상위 images (연도 없음) — deploy 엔트리만 해당, 연도 전체 선택 시만 표시
    if (selectedYears.size === 0 || selectedYears.has('all')) {
        ['combined', 'positive', 'negative'].forEach(type => {
            if (selectedTypes.has(type) && entry.images?.[type]) {
                images.push({ year: null, type, url: entry.images[type] });
            }
        });
    }

    // row_results (연도별)
    Object.entries(entry.row_results || {}).forEach(([year, rowData]) => {
        if (selectedYears.size === 0 || selectedYears.has('all') || selectedYears.has(year)) {
            ['combined', 'positive', 'negative'].forEach(type => {
                if (selectedTypes.has(type) && rowData[type]) {
                    images.push({ year, type, url: rowData[type] });
                }
            });
        }
    });

    images.sort((a, b) => {
        if (a.year === null && b.year !== null) return -1;
        if (a.year !== null && b.year === null) return 1;
        if (a.year !== b.year) return String(a.year).localeCompare(String(b.year));
        return typeOrder[a.type] - typeOrder[b.type];
    });

    return images;
}

function renderNoData() {
    document.getElementById('imageGrid').innerHTML =
        '<p style="text-align:center;color:#adb5bd;padding:40px;">이 직원의 해당 출처 데이터가 없습니다.</p>';
    document.getElementById('typeChips').style.display = 'none';
    document.getElementById('yearChips').parentElement.style.display = 'none';
}
```

**API 호출 흐름 요약**:

```
카드 클릭 (entryId, employeeId)
        ↓
[병렬 2건]
  ├── GET /detail/<entryId>          → 클릭된 entry 풀 데이터
  └── GET /employee-entries/<empId>  → deploy/matrix 양쪽 최신 entry
        ↓
currentEntries.deploy / currentEntries.matrix 구성
(클릭된 entry는 detail 버전으로 해당 source 덮어쓰기)
        ↓
기본 탭 = 클릭 entry의 source
```

---

## 7. 구현 단계 (Implementation Steps)

### Phase 1: 백엔드 (0.5일)

1. **`src/services/perspective_service.py`**
   - `_index_matrix_to_manifest()` 신규 함수 추가
   - `generate_perspective_matrix()` 내 `return result` 직전에 인덱싱 호출 추가

2. **`src/routes/perspective_routes.py`**
   - `api_deploy_gallery_list()` — `source` 파라미터 + 역호환 + `image_count` 수정
   - `api_employee_entries()` 신규 엔드포인트 추가

### Phase 2: 프론트엔드 (1일)

1. **`web/templates/deploy_gallery.html`**
   - 카드 onclick: `openDetail(item.id, item.employee_id)` 로 변경
   - 카드 `.thumb-wrap`에 배지 오버레이 추가
   - 모달 HTML: 탭 버튼 2개(`data-tab="deploy"`, `data-tab="matrix"`)
   - 모달 HTML: 종류 칩 컨테이너(`id="typeChips"`) + 연도 칩 컨테이너(`id="yearChips"`)
   - 모달 HTML: 이미지 그리드(`id="imageGrid"`)
   - JS: `openDetail`, `switchTab`, `renderModal`, `updateChipAvailability`,
     `renderYearChips`, `filterImages`, `renderNoData` 구현

### Phase 3: 통합 테스트 (0.5일)

---

## 8. 테스트 계획

| 테스트 ID | 내용 | 방법 | 기대 결과 |
|-----------|------|------|-----------|
| T-01 | 매트릭스 생성 인덱싱 | 단일 직원 매트릭스 생성 API 호출 | manifest에 `source: "matrix"` entry 추가, row_results 연도별 combined URL 포함 |
| T-02 | all_employees 인덱싱 제외 | `all_employees: true` 호출 | manifest에 새 entry 없음 |
| T-03 | 목록 source 필터 | `?source=matrix` 쿼리 | 매트릭스 결과만 반환 |
| T-04 | source 역호환 | `?source=deploy` 쿼리 | source 필드 없는 기존 엔트리도 반환 |
| T-05 | employee-entries API | `GET /employee-entries/EMP001` | deploy/matrix 양쪽 최신 entry 반환 (없으면 null) |
| T-06 | employee-entries 비관리자 | 비관리자로 real 모드 직원 조회 | deploy/matrix 모두 null 반환 |
| T-07 | 모달 진입 — deploy 카드 클릭 | deploy 카드 클릭 | deploy 탭 활성, matrix 탭 데이터 있으면 표시/없으면 "데이터 없음" |
| T-08 | 모달 진입 — matrix 카드 클릭 | matrix 카드 클릭 | matrix 탭 활성, 긍/부정 칩 비활성화 |
| T-09 | 탭 전환 | 모달에서 반대 탭 클릭 | 해당 source 이미지/칩 상태로 갱신 |
| T-10 | 연도 칩 동적 생성 | row_results 연도 다른 entry | 해당 entry의 연도만 칩으로 표시 |
| T-11 | 오름차순 정렬 | 다양한 연도/종류 조합 | year 오름차순 → combined→positive→negative 순 |
| T-12 | image_count 정확성 | row_results 있는 entry | 최상위 + row_results 합산 카운트 |
| T-13 | 출처 배지 표시 | 갤러리 카드 목록 | matrix는 '매트릭스' 배지, deploy는 '제출용' 배지 |

---

## 9. 관련 파일

| 파일 | 역할 |
|------|------|
| `src/services/perspective_service.py` | `_index_matrix_to_manifest()` 신규, `generate_perspective_matrix()` 인덱싱 호출 추가 |
| `src/routes/perspective_routes.py` | 목록 API 수정, `api_employee_entries()` 신규 엔드포인트 |
| `web/templates/deploy_gallery.html` | 카드 배지, 모달 탭/칩/그리드, openDetail 수정 |

---

## 10. 완료 기준 (Definition of Done)

- [ ] 단일 직원 매트릭스 생성 시 `deploy_manifest.json`에 `source: "matrix"`로 기록된다.
- [ ] `all_employees=True` 호출 시 manifest에 기록되지 않는다.
- [ ] `row_results`에 연도별 `combined` URL이 저장되고, `positive`/`negative`는 `null`이다.
- [ ] 갤러리 목록 API에 `source` 필터가 추가된다.
- [ ] 기존 `source` 필드 없는 엔트리가 `?source=deploy` 필터에서 반환된다.
- [ ] `image_count`가 최상위 images + row_results 전체를 합산한다.
- [ ] `GET /employee-entries/<employee_id>` API가 deploy/matrix 양쪽 최신 entry를 반환한다.
- [ ] 카드 클릭 시 `openDetail(entryId, employeeId)` 호출로 병렬 2건 API 요청이 실행된다.
- [ ] 클릭한 카드의 source가 기본 활성 탭으로 설정된다.
- [ ] 반대 source 데이터가 없으면 탭 버튼은 표시되고 "데이터 없음" 메시지가 나온다.
- [ ] 갤러리 카드에 출처 배지('제출용'/'매트릭스')가 표시된다.
- [ ] 상세 모달에 통합/긍정/부정 칩 필터가 추가된다.
- [ ] `source='matrix'` 탭에서 긍정/부정 칩이 비활성화된다.
- [ ] 상세 모달에 동적 연도 칩 필터가 추가된다 (현재 탭 entry 기준).
- [ ] 칩 필터는 다중 선택이 가능하다.
- [ ] 필터링 결과는 연도 오름차순, 종류 순서(통합→긍정→부정)로 정렬된다.
- [ ] 비관리자는 `real` 모드 데이터를 볼 수 없다.

---

*본 계획서는 `.clinerules/core/00-core/03.plan-mode.md` 지침에 따라 작성되었다.*
*실제 코드 변경은 사용자가 "수행"을 명시적으로 요청할 때까지 대기한다.*

**계획서 저장 위치**: `D:\dev\wordcloud\wordcloud_project\plans\deploy-gallery-v2_260604_01\deploy-gallery-v2_260604_01_rev-02.md`
