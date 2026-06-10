# 0608_02_batch-title-input — 배치 명칭 입력 및 중복 확인 계획서

> 상태: 구현 완료 (버그 수정 포함) | 작성일: 2026-06-08

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-08 | §3·§8.1·§8.3·§8.7(신규)·§9·§11 | 검토 반영: 세션 서비스 누락 추가, safeKey 방식 변경(인덱스 기반), 삭제 패널 UI 위치 명시, 배치 명칭 선택 칩 신규 설계, 페이징 그룹 분리 위험 추가 |
| 2026-06-08 | §3·§6.2·§8.3·§8.7·§10 | UX 최적화: 칩 클릭을 필터+자동선택 통합으로 변경, 텍스트 필터 제거, 날짜/소스 필터 접힘 처리 |
| 2026-06-08 | §3·§5.1·§6.1·§7.3·§7.5·§9·§11 | 최종 검토 반영: `batch_title` 길이 제한(100자), 공백/trim 처리 명시, 중복 확인 API `count` 필드 추가, `deploy_session_service.py` 수정 불필요로 변경, 구현 전 확인 항목(V-01~V-02) 신규 추가 |
 | 2026-06-08 | §2·§3·§5.1·§8.1 | **버튼 이름 변경**: "매트릭스 생성" → "매트릭스 저장". 일반 갤러리 배치 명칭 칩 추가(삭제 모드와 동일한 UI 패턴). Q2 고아 파일 이미 삭제됨 확인. |
 | 2026-06-09 | §3·§5.1·§8.1 | **중복 처리 방식 변경**: `confirm()` 다이얼로그 제거 → **실시간 debounce(300ms) + 버튼 비활성화 + 빨간색 안내 메시지** 방식으로 변경. 사용자 요청 반영. |
 | 2026-06-09 | §3·§8.1·§11 | **구현 후 검토 버그 수정**: Bug-1 `toggleGroupSelect` safeKey 불일치(그룹 선택 불동작) 수정 — `addEventListener` closure + plain `dateKey`로 교체. Bug-2 배치 칩 비활성화 시 `selectedEntryIds` 미정리 수정 — `allDeleteEntries` 직접 순회로 교체. Bug-3 갤러리 정렬 `reverse=True` 오류 수정 — 2단계 안정 정렬로 교체. |
 | 2026-06-09 | §3·§5.1·§8.1·§8.3 | **버튼 외관 + source별 중복 + 필수 입력**: (1) `:disabled` 상태 CSS 연한 배경색 + `cursor: not-allowed` 추가. (2) 중복 확인 API 응답에 `sources` 필드 추가하여 매트릭스(파랑)/배포(초록)/둘다(빨강) 구분. (3) 텍스트 박스 테두리 색상 + 색상 범례(legend) UI 추가. (4) 배치 명칭 **필수 입력**으로 변경 — 빈 값 시 버튼 비활성화 + "배치 명칭을 입력해주세요" 안내. |
 | 2026-06-09 | §5.1·§8.1 | **저장 중 버튼 비활성화 + 완료 후 재평가**: `generateMatrix()`/`saveDeploy()` 시작 시 두 버튼 모두 `disabled=true`. 완료 후 `onComplete` 콜백에서 `_doBatchTitleCheck()` 호출 → manifest 업데이트 반영 → 동일 명칭 재저장 방지. 사용자 제안 반영. |

---

## 1. 개요

현재 그룹분석 페이지의 `매트릭스 생성`과 `제출용 저장`은 둘 다 실제 PNG 파일을 생성하고 `deploy_manifest.json`에 인덱싱하지만, 사용자가 **의미 있는 배치 명칭**을 입력할 수 있는 UI가 없습니다. 결과적으로 갤러리에서 저장 결과를 조회할 때 `deploy_name`(자동 생성 파일명)만으로는 어떤 평가 배치인지 식별이 어렵고, 두 버튼의 결과물이 명칭 체계 없이 섞여 저장됩니다.

---

## 2. 목표

1. **버튼 앞에 텍스트 박스 추가**: 사용자가 `매트릭스 생성` 또는 `제출용 저장` 실행 전에 배치 명칭을 입력할 수 있게 한다.
2. **명칭 중복 확인**: 동일 명칭이 이미 manifest에 존재하면 경고 및 재확인을 거친다.
3. **명칭 통일**: 매트릭스 생성과 제출용 저장 모두 동일한 `batch_title` 필드를 사용하여 갤러리에서 일관되게 표시한다.
4. **갤러리 개선**: 입력된 명칭이 갤러리 카드/상세에서 우선적으로 노출되고, 명칭 기반 검색이 가능하도록 한다.
5. **버튼 이름 변경**: "매트릭스 생성" → "매트릭스 저장"으로 변경하여 실제 파일 저장 동작을 명확히 전달.

---

## 3. 자체 확정 사항 (추가 질의 없이 결정)

| 결정 항목 | 확정 내용 |
|-----------|-----------|
| **중복 확인 범위** | Manifest 전체 `entries`에서 `batch_title` 일치 여부 확인. `source`("deploy"/"matrix") 구분하여 응답에 `sources` 배열로 반환. |
| **갤러리 그룹핑** | 동일 `batch_title` 엔트리는 상단에 **그룹 헤더 라벨**을 붙여 시각적 묶음 제공. |
| **빈 명칭 허용** | **불가**. 배치 명칭은 **필수 입력**. 빈 값 시 버튼 비활성화 + "배치 명칭을 입력해주세요" 안내. 사용자 입력 `.trim()` 적용. |
| **명칭 통일 필드명** | `batch_title` (manifest 엔트리 신규 필드). |
| **역호환성** | 기존 엔트리는 `batch_title` 필드 없음 → 갤러리 표시 시 `batch_title → deploy_name → employee_id` fallback. |
| **텍스트 박스 위치** | `action-row` 내 버튼들 **왼쪽**. |
| **safeKey 방식** | 인라인 `onchange` + 문자열 치환 방식 제거. **`addEventListener` + closure**로 `dateKey`를 직접 캡처. `dateKey`는 `timestamp.slice(0,8)` 8자리 숫자이므로 HTML 인젝션 위험 없음. |
| **삭제 모드 명칭 칩 동작** | 칩 클릭 = **필터링 + 해당 그룹 항목 자동 체크 선택** 통합. 텍스트 직접 입력 필터 없음. §8.7 참조. |
| **삭제 모드 날짜/소스 필터** | 기본 **접힘(collapsed)** 처리. 고급 필터 토글 버튼으로 펼침. |
| **batch_title 최대 길이** | **100자(한글 기준)**. 프론트엔드 `maxlength="100"` + 백엔드 검증. 초과 시 100자로 자르고 경고 toast. |
| **보안(XSS)** | `batch_title`은 HTML/JS 컨텍스트에 삽입됨. `escapeHtml()`로 출력 시 이스케이프. 백엔드 저장 시 특수문자 제한 없음(사용자 자유 입력). |
| **버튼 이름** | "매트릭스 생성" → **"매트릭스 저장"**. 실제 PNG 파일 생성 + manifest 인덱싱 동작을 명확히 전달. |
| **일반 갤러리 배치 명칭 칩** | 삭제 모드와 **동일한 UI 패턴** 사용: `.chip` / `.chip--active` 클래스, `toggleXxxChip()` 함수, "전체" 칩 동작. 날짜 칩과 유사한 레이아웃. |
| **중복 처리 방식** | **실시간 debounce 체크 + 버튼 비활성화 + source별 색상/안내**. `confirm()` 다이얼로그 사용 안 함. 사용자가 타자를 치는 동안 300ms debounce로 `/deploy-title/check` API 호출. 중복 응답 시 `sources` 필드로 매트릭스(파랑 `#007bff`)/배포(초록 `#28a745`)/둘다(빨강 `#dc3545`) 구분. 텍스트 박스 테두리 색상 변경 + 색상 범례(legend) 표시 + 안내 메시지 출력. 빈 값 시 필수 입력 안내. |
| **버튼 비활성화 외관** | `:disabled` 상태에서 연한 배경색 + 흐린 텍스트 + `cursor: not-allowed` + `opacity: 0.65`. 시각적으로 명확히 비활성화됨을 표현. |

---

## 4. 데이터 모델 변경

### 4.1 `deploy_manifest.json` 엔트리 구조

```json
{
  "id": "uuid",
  "employee_id": "EMP001",
  "deploy_name": "김OO_evaluation_date__year_all_nlp_20260608_143052",
  "batch_title": "2026년 상반기 다면평가 결과 1그룹",
  "timestamp": "20260608_143052",
  "source": "deploy",
  ...
}
```

- **`batch_title`**: 사용자가 입력한 명칭. 없으면 `null` 또는 `""`.

### 4.2 갤러리 API 응답 (`/deploy-gallery/list`)

```json
{
  "id": "...",
  "employee_id": "...",
  "deploy_name": "...",
  "batch_title": "2026년 상반기 다면평가 결과 1그룹",
  "display_title": "2026년 상반기 다면평가 결과 1그룹",
  "timestamp": "...",
  "output_mode": "...",
  "source": "...",
  "image_count": 0,
  "thumbnail_url": "..."
}
```

- `display_title`: 서버에서 계산한 표시용 명칭 (`batch_title || deploy_name || employee_id`).

---

## 5. API 변경

### 5.1 신규 API: 중복 확인

```
POST /api/perspective/deploy-title/check
Content-Type: application/json

Request:
{
  "batch_title": "2026년 상반기 다면평가 결과 1그룹"
}

Response:
{
  "success": true,
  "exists": false,   // true 이면 중복 존재
  "count": 0         // 중복 엔트리 개수 (exists가 true일 때 유효)
}
```

### 5.2 기존 API 수정: 요청 바디에 `batch_title` 추가 및 options 전달

**⚠️ 핵심 결함 1**: 기존 API(`generate-and-save`, `save-deploy`)가 body에서 받은 `options`를 **재생성**하여 `batch_title`이 누락됨. 반드시 아래와 같이 수정.

**`generate-and-save` API** (`api_generate_and_save_matrix`):
```python
options = {
    'wordcloud_pos': data.get('wordcloud_pos', ['Noun']),
    ...
    'batch_title': data.get('batch_title'),   # ← 신규 추가
}
```

**`save-deploy` API** (`api_save_deploy`):
```python
options = {
    'wordcloud_pos': data.get('wordcloud_pos', ['Noun']),
    ...
    'batch_title': data.get('batch_title'),   # ← 신규 추가
}
```

| API | 메서드 | 변경 내용 |
|-----|--------|-----------|
| `/api/perspective/matrix/generate` | POST | `batch_title` 선택적 필드 추가 |
| `/api/perspective/matrix/save-deploy` | POST | `batch_title` 선택적 필드 추가 |
| `/api/perspective/matrix/save-deploy-batch` | POST | `batch_title` 선택적 필드 추가 |
| `/api/perspective/deploy-session/start` | POST | 세션 옵션에 `batch_title` 포함 (후속 chunk 처리에서 사용) |

### 5.3 갤러리 API 수정

| API | 변경 내용 |
|-----|-----------|
| `/deploy-gallery/list` | 응답에 `batch_title`, `display_title` 추가. `batch_title` 쿼리 파라미터로 contains 검색 지원. |
| `/deploy-gallery/detail/<entry_id>` | 응답에 `batch_title` 필드 추가. |

---

## 6. 프론트엔드 변경

### 6.1 `perspective_test.html`

#### A. action-row 텍스트 박스 추가

```html
<div class="action-row">
    <input type="text" id="batchTitleInput" maxlength="100"
           placeholder="배치 명칭 (예: 2026년 상반기 다면평가 결과 1그룹)"
           style="flex:1;max-width:320px;padding:6px 10px;font-size:13px;
                  border:1px solid #ccc;border-radius:5px;">
    <button class="btn-primary" onclick="generateMatrix()">매트릭스 생성</button>
    <button class="btn-success" onclick="saveDeploy()">제출용 저장</button>
    ...
</div>
```

#### B. 중복 확인 로직

```javascript
async function checkBatchTitleDuplicate(title) {
    if (!title || !title.trim()) return {exists: false};
    const r = await fetch('/api/perspective/deploy-title/check', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({batch_title: title.trim()})
    });
    return await r.json();
}
```

#### C. 버튼 클릭 시 흐름

1. `batchTitleInput.value.trim()` 취득
2. 값이 있으면 `/deploy-title/check` 호출
3. `exists === true`이면 `confirm("이미 동일한 명칭의 저장 결과가 존재합니다. 계속 진행하시겠습니까?")`
4. 사용자가 취소하면 함수 종료
5. `options`에 `batch_title` 추가 후 기존 API 호출

### 6.2 `deploy_gallery.html`

#### A. 검색 바에 명칭 필터 추가 (일반 모드)

```html
<div class="filter-group" style="flex:1;min-width:200px;">
    <label>배치 명칭</label>
    <input type="text" id="filterBatchTitle" placeholder="명칭 검색">
</div>
```

#### B. 카드 표시 개선

- 카드 상단/상세 모달 제목에 `display_title` 사용
- 동일 `batch_title`끼리 **그룹 헤더 라벨** 삽입

#### C. 삭제 모드 패널 구조 (§8.7 참조)

삭제 모드 패널(`deleteModePanel`) 내부를 아래 구조로 교체:

```html
<!-- deleteModePanel 내부 -->
<div class="delete-filter-section">

    <!-- ① 배치 명칭 칩 (필터 + 자동 선택 통합) — 항상 노출 -->
    <div class="delete-filter-row" id="batchTitleChipRow">
        <span class="filter-label">배치 선택</span>
        <div class="batch-title-chips" id="deleteBatchTitleChips">
            <!-- JS로 동적 렌더링 -->
        </div>
    </div>

    <!-- ② 날짜/소스 필터 — 기본 접힘, 토글로 펼침 -->
    <div class="delete-filter-advanced-toggle"
         onclick="toggleAdvancedDeleteFilter()">
        고급 필터 ▾
    </div>
    <div class="delete-filter-advanced" id="deleteAdvancedFilter"
         style="display:none;">
        <!-- 기존 날짜/소스 필터 행 그대로 유지 -->
        ...
    </div>

</div>
```

---

## 7. 백엔드 변경

### 7.1 `perspective_routes.py`

**⚠️ 핵심 결함 3**: 갤러리 API 응답에 `batch_title`/`display_title` 누락. 정렬 로직도 누락.

**A. 기존 API들**: `data.get('batch_title')` 추출 → `options`에 포함하여 서비스 함수 전달.

**B. 신규 `api_deploy_title_check()`**:
```python
@perspective_bp.route('/deploy-title/check', methods=['POST'])
def api_deploy_title_check():
    data = request.get_json(silent=True) or {}
    batch_title = data.get('batch_title', '').strip()
    if not batch_title:
        return jsonify({'success': True, 'exists': False, 'count': 0})
    
    manifest = {"version": "1.0", "entries": []}
    if os.path.exists(DEPLOY_MANIFEST_PATH):
        with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    
    entries = manifest.get('entries', [])
    matches = [e for e in entries if e.get('batch_title') == batch_title]
    return jsonify({'success': True, 'exists': len(matches) > 0, 'count': len(matches)})
```

**C. `api_deploy_gallery_list()` 수정**:
```python
# 필터 로직 내 batch_title contains 검색 추가
batch_title_filter = request.args.get('batch_title', '').strip()
if batch_title_filter:
    if batch_title_filter.lower() not in (entry.get('batch_title') or '').lower():
        continue

# list_item에 batch_title, display_title 추가
list_item = {
    "id": entry.get('id'),
    "employee_id": entry.get('employee_id'),
    "deploy_name": entry.get('deploy_name'),
    "batch_title": entry.get('batch_title'),   # ← 신규
    "display_title": entry.get('batch_title') or entry.get('deploy_name') or entry.get('employee_id'),  # ← 신규
    ...
}

# ⚠️ 핵심: 정렬 로직 변경
filtered.sort(
    key=lambda x: (not bool(x.get('batch_title')), x.get('batch_title', ''), x.get('timestamp', ''))
)
```

### 7.2 `perspective_service.py`

**⚠️ 핵심 결함 2**: `_append_to_deploy_manifest`와 `_index_matrix_to_manifest`가 entry에 `batch_title` 필드를 추가하지 않음.

**A. `_append_to_deploy_manifest(..., batch_title=None)`**:
```python
entry = {
    "id": str(uuid.uuid4()),
    "employee_id": employee_id,
    "deploy_name": result.get('name', ''),
    "batch_title": batch_title or options.get('batch_title'),   # ← 신규
    ...
}
```

**B. `_index_matrix_to_manifest(..., batch_title=None)`**:
```python
entry = {
    "id": str(uuid.uuid4()),
    "employee_id": employee_id,
    "deploy_name": batch_title or employee_id,   # ← batch_title이 있으면 사용, 없으면 employee_id fallback
    "batch_title": batch_title or options.get('batch_title'),   # ← 신규
    ...
}
```

**C. `save_to_deploy(...)`**: `options`에서 `batch_title` 읽어 `_append_to_deploy_manifest`에 전달. 수정 불필요(options가 그대로 전달됨).

**D. `generate_perspective_matrix(...)`**: `options`에서 `batch_title` 읽어 `_index_matrix_to_manifest`에 전달. 수정 불필요(options가 그대로 전달됨).

### 7.3 `deploy_session_service.py`

- **수정 불필요**. `options`가 JSON 문자열 그대로 SQLite에 저장/복원되므로, `batch_title`이 `options` dict에 포함되어 전달되면 자동으로 세션에 보관됨. 별도 필드 추가나 추출 로직 불필요.

---

## 7.5 구현 전 확인 항목 (이미 검증 완료)

| ID | 확인 항목 | 결과 |
|----|-----------|------|
| V-01 | `runSessionProcess`가 chunk POST body에 `options`를 포함하는가? | **✅ 확인 완료** — `processOne` 내 `const body = params.buildRequestBody ? ... : {...opts, employee_id: eid};`로 `options`가 body에 포함됨 |
| V-02 | `/api/perspective/matrix/generate-and-save` API가 실제로 존재하는가? | **✅ 확인 완료** — `perspective_routes.py` Line 430에 `@perspective_bp.route('/matrix/generate-and-save', methods=['POST'])` 존재 |

---

## 8. 갤러리 인식 및 동작 상세 설계

### 8.1 그리드 렌더링 (`renderGalleryGrid`)

**현재**: `timestamp.slice(0, 8)` 기준으로 **날짜별 그룹핑**만 수행.

**변경 후**:

- **1차 그룹핑**: `batch_title`이 존재하면 `batch_title`로, 없으면 `dateKey`로 그룹핑.
- **2차 그룹핑(내부)**: 동일 `batch_title` 그룹 내에서도 `dateKey` 서브 헤더로 구분.

**그룹핑 로직**:

```javascript
const groups = {};
const groupOrder = [];

entries.forEach(item => {
    const primaryKey = item.batch_title || (item.timestamp || '').slice(0, 8);
    if (!groups[primaryKey]) { groups[primaryKey] = []; groupOrder.push(primaryKey); }
    groups[primaryKey].push(item);
});
```

**체크박스 key — `addEventListener` closure 방식 (Bug-1 수정)**:

인라인 `onchange="toggleGroupSelect('${safeKey}', ...)"` 방식은 safeKey(`dateKey + '_' + idx`)를 함수에 전달하지만, 함수 내부는 `entry.timestamp.slice(0,8)`(`dateKey`)와 비교하여 **항상 mismatch** → 그룹 선택이 전혀 동작하지 않는 버그 발생. 수정 방안:

```javascript
const groupCb = document.createElement('input');
groupCb.type = 'checkbox';
groupCb.className = 'date-group-select-all';
groupCb.addEventListener('change', () => toggleGroupSelect(dateKey, groupCb.checked));

header.onclick = (e) => {
    if (!deleteMode) return;
    if (e.target.closest('input[type="checkbox"]')) return;
    const newState = !groupCb.checked || groupCb.indeterminate;
    groupCb.checked = newState;
    toggleGroupSelect(dateKey, newState);
};
```

- closure가 `dateKey`를 직접 캡처하므로 별도 safeKey 변환 불필요.
- `dateKey = timestamp.slice(0,8)` (8자리 숫자)이므로 HTML 인젝션 위험 없음.

**그룹 헤더 렌더링**:

| 조건 | 헤더 내용 |
|------|----------|
| `batch_title` 존재 | `📁 2026년 상반기 다면평가 결과 1그룹 (12개)` |
| `batch_title` 없음 | `06/08 (5개)` — 기존 날짜 헤더 그대로 |

### 8.2 카드 (`buildGalleryCard`)

**현재**:
```html
<div class="card-title">${escapeHtml(item.deploy_name || item.employee_id)}</div>
```

**변경 후**:
```html
<div class="card-title">${escapeHtml(item.display_title)}</div>
```

- `display_title` = 서버가 계산한 `batch_title || deploy_name || employee_id`.
- `batch_title`이 있는 경우 카드 상단/하단에 작은 라벨로 표시 (단, `display_title`이 이미 `batch_title`이면 중복 표시 생략).

### 8.3 검색/필터 동작

#### 일반 모드 (`loadGallery`)

**추가 요청 파라미터**: `batch_title` (contains 검색)

```javascript
const batchTitle = document.getElementById('filterBatchTitle')?.value.trim();
if (batchTitle) params.set('batch_title', batchTitle);
```

**백엔드 필터 로직** (`api_deploy_gallery_list`):

```python
batch_title_filter = request.args.get('batch_title', '').strip()
if batch_title_filter:
    if batch_title_filter.lower() not in (entry.get('batch_title') or '').lower():
        continue
```

- **대소문자 구분 없음**, **부분 일치(contains)**.
- `batch_title`이 없는 엔트리는 검색에서 제외됨 (의도된 동작).

#### 삭제 모드 (`_getDeleteFiltered`)

칩 선택 상태만으로 필터링. 텍스트 직접 입력 필터 없음.

```javascript
function _getDeleteFiltered() {
    return allDeleteEntries.filter(e => {
        // 기존 날짜/소스 필터 (고급 필터 패널에서 적용)
        // ...

        // 배치 명칭 칩 필터 — 선택된 칩이 있으면 해당 batch_title만 통과
        if (selectedDeleteBatchTitles.size > 0) {
            if (!selectedDeleteBatchTitles.has(e.batch_title || '')) return false;
        }

        return true;
    });
}
```

### 8.4 상세 모달 (`openDetail`, `renderModal`, `renderMeta`)

#### 모달 제목

**현재**:
```javascript
`${escapeHtml(clickedEntry.deploy_name || clickedEntry.employee_id)} 상세 정보`
```

**변경 후**:
```javascript
`${escapeHtml(clickedEntry.display_title || clickedEntry.deploy_name || clickedEntry.employee_id)} 상세 정보`
```

#### 메타 정보 (`renderMeta`)

메타 테이블에 행 추가:

```html
<div class="meta-row">
    <div class="meta-key">배치 명칭</div>
    <div class="meta-value">${escapeHtml(entry.batch_title || '—')}</div>
</div>
```

#### 탭 영향

- **변경 없음**. `source` 필드에 따라 탭은 기존과 동일하게 동작.
- 동일 `batch_title`을 가진 엔트리가 "deploy"와 "matrix" 탭에 각각 표시될 수 있음. 이는 사용자가 "어떤 버튼으로 저장했는지"를 구분할 수 있게 하는 의도된 동작.

### 8.5 정렬 (Sorting)

**현재**: `timestamp` desc만.

**변경 후**:
1. `batch_title` 존재 여부 (`True` 먼저)
2. `batch_title` 값 (alphabetical)
3. `timestamp` desc

이 정렬을 유지하면 `batch_title`이 있는 엔트리가 상단에 모이고, 동일 배치명은 연속해서 표시되어 **그룹핑 효과**를 자연스럽게 얻을 수 있습니다.

> **주의**: 페이징(20개/페이지) 경계에서 동일 `batch_title` 그룹이 분리될 수 있습니다. 완전한 해결은 스크롤 무한 로드 방식으로의 전환이 필요하나 이번 작업 범위에서 제외합니다. 현재는 §11 위험도 테이블에 기록하고 수용합니다.

### 8.6 삭제 확인 다이얼로그 (`_buildDeleteSummaryHtml`)

**현재**: 날짜별/소스별 분류만 표시.

**변경 후**: `batch_title`이 있는 항목은 **배치 명칭별 분류**도 추가 표시.

```html
<p class="confirm-date-label">배치 명칭별</p>
<ul class="confirm-breakdown">
    <li>2026년 상반기 다면평가 결과 1그룹 — 8개</li>
    <li>2026년 하반기 다면평가 결과 2그룹 — 5개</li>
</ul>
```

### 8.7 삭제 모드 배치 명칭 선택 칩

#### 설계 원칙

삭제 모드에서 사용자의 핵심 패턴은 **"이 배치 전부 지우겠다"** 입니다.
칩 클릭 한 번으로 **그리드 필터링 + 해당 그룹 항목 자동 체크**가 동시에 완료됩니다.
텍스트 직접 입력 필터는 제공하지 않습니다.

#### 상태 관리

```javascript
let selectedDeleteBatchTitles = new Set();  // 활성화된 칩의 batch_title 값 집합
```

#### 칩 렌더링

삭제 모드 진입 시 `allDeleteEntries`에서 고유 `batch_title`을 집계해 칩을 생성합니다.
`batch_title`이 없는 항목만 존재하면 칩 행 자체를 숨깁니다.

```javascript
function renderDeleteBatchTitleChips(entries) {
    const counts = {};
    entries.forEach(e => {
        if (e.batch_title) counts[e.batch_title] = (counts[e.batch_title] || 0) + 1;
    });

    const container = document.getElementById('deleteBatchTitleChips');
    if (!container) return;

    const titles = Object.keys(counts).sort();
    if (titles.length === 0) {
        document.getElementById('batchTitleChipRow').style.display = 'none';
        return;
    }

    container.innerHTML = titles.map(title =>
        `<span class="batch-chip" data-title="${escapeHtml(title)}"
               onclick="toggleDeleteBatchChip(this)">
            ${escapeHtml(title)} <em>(${counts[title]})</em>
         </span>`
    ).join('');
}
```

#### 토글 동작 — 필터 + 자동 선택 통합

```javascript
function toggleDeleteBatchChip(chip) {
    const title = chip.dataset.title;

    if (selectedDeleteBatchTitles.has(title)) {
        // 칩 비활성화 → 해당 그룹 항목 체크 해제
        selectedDeleteBatchTitles.delete(title);
        chip.classList.remove('chip-active');
        allDeleteEntries.forEach(e => {
            if (e.batch_title === title) selectedEntryIds.delete(e.id);
        });
    } else {
        // 칩 활성화 → 해당 그룹 항목 전체 자동 체크
        selectedDeleteBatchTitles.add(title);
        chip.classList.add('chip-active');
        allDeleteEntries.forEach(e => {
            if (e.batch_title === title) selectedEntryIds.add(e.id);
        });
    }

    renderDeleteGrid();         // 그리드 필터 재적용
    updateDeleteCount();        // 선택 카운트 갱신 (실제 함수명)
}
```

**개별 체크박스 수동 해제**: 칩이 활성화된 상태에서도 카드 체크박스를 개별적으로 해제할 수 있습니다. 이 경우 칩 활성 상태는 유지되며 그리드는 그대로 표시되고 `selectedEntryIds`에서만 해당 id가 제거됩니다.

#### 삭제 모드 진입/해제 시 초기화

```javascript
function enterDeleteMode() {
    selectedDeleteBatchTitles = new Set();
    renderDeleteBatchTitleChips(allDeleteEntries);
    // ... 기존 로직
}

function exitDeleteMode() {
    selectedDeleteBatchTitles = new Set();
    // ... 기존 로직
}
```

#### 고급 필터 (날짜/소스) 접힘 처리

```javascript
function toggleAdvancedDeleteFilter() {
    const panel = document.getElementById('deleteAdvancedFilter');
    const isOpen = panel.style.display !== 'none';
    panel.style.display = isOpen ? 'none' : 'block';
    document.querySelector('.delete-filter-advanced-toggle').textContent =
        isOpen ? '고급 필터 ▾' : '고급 필터 ▴';
}
```

#### CSS

```css
.batch-title-chips {
    display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px;
}
.batch-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 12px; border-radius: 14px; font-size: 12px; cursor: pointer;
    background: #f0f0f0; border: 1px solid #ccc; transition: all 0.15s;
    user-select: none;
}
.batch-chip:hover  { background: #e0e8ff; border-color: #7a9edc; }
.batch-chip.chip-active { background: #3b5fc0; color: #fff; border-color: #3b5fc0; }
.batch-chip em { font-style: normal; opacity: 0.7; font-size: 11px; }

.delete-filter-advanced-toggle {
    font-size: 12px; color: #666; cursor: pointer; padding: 4px 0;
    user-select: none;
}
.delete-filter-advanced-toggle:hover { color: #333; }
```

---

## 9. 파일 변경 목록

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `web/templates/perspective_test.html` | 수정 | 텍스트 박스 추가, 중복 확인 JS, `batch_title`을 options에 포함 |
| `web/templates/deploy_gallery.html` | 수정 | 명칭 검색 필터(일반 모드), 카드/상세 `display_title` 적용, 그룹 헤더(CSS 클래스 수정 포함), 삭제 모드 명칭 칩(필터+자동선택), 날짜/소스 필터 접힘, 정렬, 삭제 확인 다이얼로그 수정 |
| `src/routes/perspective_routes.py` | 수정 | `batch_title` 수신/전달, 중복 확인 API 신규, 갤러리 API 수정 |
| `src/services/perspective_service.py` | 수정 | `_append_to_deploy_manifest`, `_index_matrix_to_manifest`, `save_to_deploy`, `generate_perspective_matrix`에 `batch_title` 파라미터 추가 |

---

## 10. 테스트 시나리오

| ID | 시나리오 | 예상 결과 |
|----|----------|-----------|
| T-01 | 명칭 "2026-1그룹" 입력 → 매트릭스 생성 | manifest에 `batch_title: "2026-1그룹"` 기록. 갤러리에 동일 명칭 표시. |
| T-02 | 동일 명칭 "2026-1그룹"으로 제출용 저장 | 중복 확인 API `exists: true`. `confirm` 다이얼로그 노출. 취소 시 저장 안 함. |
| T-03 | confirm "계속" 선택 → 제출용 저장 진행 | 저장 완료. 갤러리에 동일 명칭 엔트리 2건. |
| T-04 | 명칭 미입력 → 매트릭스 생성 | `batch_title` 없이 저장. `deploy_name`으로 표시. 기존 동작 유지. |
| T-05 | 갤러리에서 "2026-1그룹" 검색 | 해당 명칭을 가진 엔트리만 필터링되어 표시. |
| T-06 | 기존 저장 결과(명칭 없음) 조회 | `deploy_name`이 표시되고, 기존 동작 깨지지 않음. |
| T-07 | 갤러리 그룹핑 확인 | 동일 `batch_title` 상단에 그룹 헤더 표시. |
| T-08 | 동일 배치, 다른 날짜 저장 | 그룹 헤더 아래 서브 헤더로 날짜별 구분. |
| T-09 | 삭제 모드에서 칩 클릭 1회 | 해당 명칭 항목만 그리드에 표시되고 전체 자동 체크. 선택 카운트 즉시 반영. |
| T-10 | 삭제 모드에서 복수 칩 선택 | 선택된 명칭들의 항목이 누적 표시·체크됨. |
| T-11 | 칩 활성 상태에서 카드 체크박스 개별 해제 | 해당 카드만 체크 해제. 칩 활성 유지. 선택 카운트 1 감소. |
| T-12 | 활성 칩 재클릭(비활성화) | 해당 그룹 항목 체크 해제 및 그리드에서 제거. |
| T-13 | 삭제 모드 해제 후 재진입 | 칩 선택 상태 초기화. 그리드 전체 표시. |
| T-14 | 삭제 확인 다이얼로그 | 배치 명칭별 분류가 추가로 표시됨. |
| T-15 | 고급 필터 토글 클릭 | 날짜/소스 필터 패널 펼침/접힘 전환. |
| T-16 | 배포 세션(chunked) 완료 후 갤러리 확인 | manifest에 `batch_title` 정상 기록. 갤러리 카드에 명칭 표시. |
| T-17 | API options 재생성 확인 | `generate-and-save`/`save-deploy`의 `options` dict에 `batch_title`이 포함되어 서비스 함수까지 전달되는지 디버깅 로그로 확인 |
| T-18 | `_append_to_deploy_manifest` entry 필드 확인 | manifest JSON을 직접 열어 `batch_title` 필드가 존재하는지 확인 |
| T-19 | 갤러리 정렬 확인 | `batch_title`이 있는 엔트리가 상단에, 동일 배치명은 연속해서 표시됨 |
| T-20 | `_index_matrix_to_manifest` deploy_name 확인 | `batch_title`이 있을 때 `deploy_name`이 `batch_title`로 기록됨 |

---

## 11. 위험도 및 주의사항

| 위험 | 수준 | 대응 |
|------|------|------|
| 기존 manifest `batch_title` 필드 누락 | 낮음 | 응답 시 `entry.get('batch_title')`로 안전하게 fallback 처리 |
| 빈 명칭으로 인한 `display_title` 계산 | 낮음 | `batch_title or deploy_name or employee_id` 순으로 계산 |
| 중복 확인 API 성능 (manifest 1만 건 이상) | 중간 | manifest는 파일 기반이므로, 목록 API가 이미 전체 순회를 하고 있음. 동일 로직 재사용. |
| 동시 저장 시 중복 확인 race condition | 낮음 | 중복 확인 후 저장 사이에 새 엔트리가 추가될 수 있으나, 사용자 confirm 단계에서 최종 판단하도록 설계. 완벽한 방지는 파일 기반에서는 불가능. |
| `batch_title`에 `"`, `<`, `>` 등이 포함되어 XSS | 낮음 | `escapeHtml()` 이미 모든 카드/모달에 적용 중. 추가 작업 불필요. |
| `batch_title`에 매우 긴 문자열(100자+) 입력 시 UI 깨짐 | 낮음 | CSS `text-overflow: ellipsis`, `max-width` 제한. |
| 동일 `batch_title` + 동일 `employee_id` + 동일 `source`로 엔트리가 수백 건 쌓임 | 중간 | 갤러리 페이징(20개/페이지)으로 완화. 그룹핑은 헤더만 추가하고 페이징은 유지. |
| 검색어 `" "`(공백) 입력 시 결과 0건 | 낮음 | `.trim()` 후 빈 문자열이면 필터 무시. |
| 페이징 경계에서 동일 `batch_title` 그룹 분리 | 중간 | 수용. 이번 범위에서 해결하지 않음. 무한 스크롤 전환 시 재검토. |
| **`safeKey` 문자열 충돌** | 해결됨 | 인덱스 기반 `grp_N` key 방식으로 전환. §8.1 참조. |
| `deploy_session_service.py`에서 `batch_title` 미전달 | **해결됨** | §7.3 확인. `options` JSON에 포함되어 자동 전달. 별도 수정 불필요. |
| **API(`generate-and-save`, `save-deploy`)의 `options` 재생성으로 `batch_title` 누락** | **높음 → 해결됨** | §5.2에 명시. `options` dict에 `'batch_title': data.get('batch_title')` 추가. |
| **`_append_to_deploy_manifest`/`_index_matrix_to_manifest`의 `batch_title` 필드 누락** | **높음 → 해결됨** | §7.2에 명시. entry에 `"batch_title": batch_title or options.get('batch_title')` 추가. |
| **`_index_matrix_to_manifest`의 `deploy_name`이 항상 `employee_id`** | **중간 → 해결됨** | §7.2에 명시. `"deploy_name": batch_title or employee_id`로 변경. |
| 칩 자동선택 후 수동 해제 항목이 재선택 시 복원됨 | 낮음 | 칩 재클릭은 그룹 전체를 다시 체크하는 것으로 정의. UX상 의도된 동작. |
| **[Bug-1] `toggleGroupSelect` safeKey 불일치 → 그룹 선택 불동작** | **높음 → 해결됨** | 구현 후 검토에서 발견. `safeKey = dateKey + '_' + idx`를 함수 인자로 전달했으나 함수 내부는 `dateKey`와 비교 → 항상 mismatch. `addEventListener` closure로 교체하여 수정 (2026-06-09). |
| **[Bug-2] 배치 칩 비활성화 시 `selectedEntryIds` 미정리** | **중간 → 해결됨** | 다른 칩이 활성인 경우 `_getDeleteFiltered()` 결과에 비활성화 항목이 포함되지 않아 `delete()` 미호출. `allDeleteEntries.forEach`로 직접 처리하도록 수정 (2026-06-09). |
| **[Bug-3] 갤러리 정렬 `reverse=True` 오류** | **중간 → 해결됨** | `(not bool(batch_title), batch_title, timestamp)`에 `reverse=True` 적용 시 batch_title 없는 항목이 먼저 표시되고 알파벳 역순 정렬됨. timestamp desc → batch_title asc 2단계 안정 정렬로 교체 (2026-06-09). |

---

## 12. 구현 흐름 (Step-by-Step) — 압축 후에도 이 순서로 작업

> **⚠️ 압축 시 이 섹션을 반드시 확인하고 순서대로 작업할 것**

### Phase 1: 데이터 모델 + 백엔드 API (독립, 프론트엔드 의존 없음)

| 순서 | 파일 | 작업 내용 | 검증 방법 |
|------|------|-----------|-----------|
| 1 | `src/services/perspective_service.py` | `_append_to_deploy_manifest`에 `"batch_title": options.get('batch_title')` 추가 | `deploy_manifest.json` 열어 필드 확인 |
| 2 | `src/services/perspective_service.py` | `_index_matrix_to_manifest`에 `"batch_title": options.get('batch_title')`, `"deploy_name": options.get('batch_title') or employee_id` 추가 | 매트릭스 생성 후 manifest 확인 |
| 3 | `src/routes/perspective_routes.py` | `api_generate_and_save_matrix`의 `options` dict에 `'batch_title': data.get('batch_title')` 추가 | 프론트엔드 개발자 도구 Network 탭에서 request body 확인 |
| 4 | `src/routes/perspective_routes.py` | `api_save_deploy`의 `options` dict에 `'batch_title': data.get('batch_title')` 추가 | 동일 |
| 5 | `src/routes/perspective_routes.py` | **신규** `api_deploy_title_check()` 구현 | Postman/curl로 `POST /deploy-title/check` 호출 |
| 6 | `src/routes/perspective_routes.py` | `api_deploy_gallery_list`에 `batch_title` 필터, `batch_title`/`display_title` 응답, 정렬 로직 추가 | 갤러리 API 호출 후 응답 JSON 확인 |
| 7 | `src/routes/perspective_routes.py` | `api_deploy_gallery_detail`에 `batch_title` 응답 추가 | 상세 API 호출 후 응답 확인 |

### Phase 2: 프론트엔드 — 그룹분석 페이지

| 순서 | 파일 | 작업 내용 | 검증 방법 |
|------|------|-----------|-----------|
| 8 | `web/templates/perspective_test.html` | action-row에 `batchTitleInput` 텍스트 박스 추가 (`maxlength="100"`) | 화면에서 텍스트 박스 위치/동작 확인 |
| 9 | `web/templates/perspective_test.html` | `checkBatchTitleDuplicate(title)` JS 함수 추가 | 중복 명칭 입력 시 confirm 다이얼로그 확인 |
| 10 | `web/templates/perspective_test.html` | `generateMatrix()`/`saveDeploy()` 시작 시 `batchTitleInput.value.trim()`을 `options.batch_title`에 추가 | Network 탭에서 request body에 `batch_title` 포함 확인 |

### Phase 3: 프론트엔드 — 갤러리 페이지

| 순서 | 파일 | 작업 내용 | 검증 방법 |
|------|------|-----------|-----------|
| 11 | `web/templates/deploy_gallery.html` | 검색 바에 `filterBatchTitle` 입력란 추가 | 화면에서 검색 필터 표시/동작 확인 |
| 12 | `web/templates/deploy_gallery.html` | `buildGalleryCard`에 `display_title` 적용, `batch_title` 라벨 추가 | 카드에 명칭 표시 확인 |
| 13 | `web/templates/deploy_gallery.html` | `renderGalleryGrid`에 `batch_title` 기반 1차 그룹핑 + 인덱스 기반 safeKey 추가 | 동일 배치명 상단 그룹 헤더 확인 |
| 14 | `web/templates/deploy_gallery.html` | `openDetail`/`renderMeta`에 `display_title`/`batch_title` 추가 | 상세 모달에 배치 명칭 표시 확인 |
| 15 | `web/templates/deploy_gallery.html` | 삭제 모드 패널에 `deleteBatchTitleChips` 칩 렌더링 + `toggleDeleteBatchChip` 토글 + `selectedDeleteBatchTitles` 상태 추가 | 삭제 모드에서 칩 클릭 시 필터+자동선택 확인 |
| 16 | `web/templates/deploy_gallery.html` | `_getDeleteFiltered`에 `selectedDeleteBatchTitles` 필터 추가 | 칩 선택 시 그리드 필터링 확인 |
| 17 | `web/templates/deploy_gallery.html` | `_buildDeleteSummaryHtml`에 배치 명칭별 분류 추가 | 삭제 확인 다이얼로그에 배치 명칭 표시 확인 |
| 18 | `web/templates/deploy_gallery.html` | 고급 필터 토글 UI(`toggleAdvancedDeleteFilter`) 추가 | 날짜/소스 필터 접힘/펼침 확인 |

### Phase 4: 통합 테스트

| 순서 | 테스트 | 검증 방법 |
|------|--------|-----------|
| 19 | T-01: 매트릭스 생성 + 명칭 입력 | manifest JSON에서 `batch_title` 필드 확인 |
| 20 | T-02: 제출용 저장 + 동일 명칭 | confirm 다이얼로그 확인 |
| 21 | T-05: 갤러리 검색 | 검색 결과 필터링 확인 |
| 22 | T-07: 그룹핑 | 동일 배치명 상단 그룹 헤더 확인 |
| 23 | T-09: 삭제 모드 칩 | 필터+자동선택 동시 동작 확인 |
| 24 | T-14: 삭제 확인 다이얼로그 | 배치 명칭별 분류 표시 확인 |
| 25 | T-16: 배포 세션 완료 후 갤러리 | chunked 저장 후에도 `batch_title` 정상 기록 확인 |

---

*본 계획서는 2026-06-08 UX 최적화 반영 수정본입니다. 위 확정 사항을 바탕으로 즉시 구현 가능합니다.*
