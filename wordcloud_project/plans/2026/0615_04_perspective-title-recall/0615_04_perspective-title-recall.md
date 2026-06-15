# 0615_04 — perspective_test 배치 명칭 기반 재호출

> 상태: PND | 작성일: 2026-06-15

---

## 1. 배경 및 목적

`perspective_test.html`(그룹 분석 테스트) 페이지에서 **매트릭스 저장** 또는 **제출용 저장** 실행 후
다른 페이지로 이동했다가 복귀하면 `resultArea`가 초기화되어 분석 결과가 사라진다.

재분석을 위해 직원 선택, X·Y축 설정, WC 옵션 등을 처음부터 다시 입력해야 하며,
특히 **수백~수천 명 CSV 업로드 기반 배치**의 경우 재구성 비용이 크다.

**목표**: 과거 **제출용 저장** 시 입력한 배치 명칭을 선택하면 해당 배치의 직원 목록과 설정을 즉시 복원하고,
`[매트릭스 저장]` 한 번으로 재분석이 가능하도록 한다.

---

## 2. 구현 범위

| 구분 | 대상 | 신규/수정 |
|------|------|-----------|
| 프론트엔드 | `wordcloud_project/web/templates/perspective_test.html` | 수정 |
| 백엔드 | 없음 — 기존 API 재사용 | — |

### 사용 기존 API

| 엔드포인트 | 역할 | 호출 위치 |
|-----------|------|-----------|
| `GET /api/perspective/deploy-gallery/batch-titles` | 과거 배치 명칭 목록 | 드롭다운 열 때 |
| `GET /api/perspective/deploy-gallery/list?source=deploy&batch_title={title}&all=1` | 해당 명칭의 갤러리 항목 전체 | 명칭 선택 시 |

**확인된 서비스 함수 시그니처:**

```python
# gallery_db_service.py:304
def get_distinct_batch_titles(is_admin=False) -> list[str]:
    """고유 batch_title 목록 반환. is_admin=False이면 pseudonym 모드 데이터만."""

# gallery_db_service.py:146
def list_entries(
    page=1, per_page=20, fetch_all=False,
    employee_id=None, source=None,
    output_mode=None, date_from=None, date_to=None,
    dates=None, batch_titles=None,
    is_admin=False,
) -> dict:  # {total, entries}
    """fetch_all=True 시 페이징 없이 전체 반환."""
```

**갤러리 항목(deploy source)에 저장된 복원 가능 필드:**

| 필드 | 저장 여부 | 비고 |
|------|-----------|------|
| `employee_id` | ✅ | 직원별 1개 항목 |
| `row_field` | ✅ | X축 필드 |
| `row_values` | ✅ | 선택된 row 값 목록 |
| `row_combine_all` | ✅ | 통합 출력 여부 |
| `analysis_type` | ✅ | 단수(첫 번째 분석 유형만) |
| `options.background_color` | ✅ | WC 옵션 |
| `options.width` / `height` | ✅ | |
| `options.max_words` | ✅ | |
| `options.apply_emotion_colors` | ✅ | |
| `options.remove_profanity` | ✅ | |
| `options.word_color` | ✅ | |
| `options.wordcloud_pos` | ✅ | |
| `col_mode` | ❌ | 갤러리에 미저장 → UI 현재값 유지 |
| `analysis_types` (복수) | ❌ | `analysis_type` 단수만 저장됨 |

---

## 3. UI 변경 — action-row

배치 명칭 입력창(`#batchTitleInput`) 옆에 `📂` 버튼을 추가한다.

**변경 전:**
```html
<input type="text" id="batchTitleInput" ... style="flex:1;max-width:320px;...">
```

**변경 후:**
```html
<div style="position:relative;flex:1;max-width:340px;display:flex;gap:4px;">
    <input type="text" id="batchTitleInput" ...>
    <button onclick="toggleBatchTitlePicker(this)">📂</button>
    <div id="batchTitlePickerDropdown" style="display:none;position:absolute;...">
        <div>제출용 저장 명칭 선택 / [✕]</div>
        <div id="batchTitlePickerList">로딩...</div>
    </div>
</div>
```

드롭다운은 `position:absolute; top:100%`로 입력창 바로 아래 표시.
외부 클릭 시 닫히도록 `document.addEventListener('click', ...)` one-time 리스너 등록.

---

## 4. JS 함수 명세

### 4-A. 배치 명칭 피커

#### `toggleBatchTitlePicker(btn): async`
- 드롭다운이 열려 있으면 `closeBatchTitlePicker()` 호출 후 반환
- 드롭다운 표시 → `GET /api/perspective/deploy-gallery/batch-titles` 호출
- 응답 `batch_titles[]` 가 비어있으면 "저장된 명칭 없음" 표시
- 각 명칭을 클릭 가능한 `<div>` 행으로 렌더링, `onclick="selectBatchTitleForRestore(title)"` 연결
- 외부 클릭 감지: `setTimeout(() => document.addEventListener('click', _batchPickerOutsideClick, {once:true}), 0)`

#### `_batchPickerOutsideClick(e): void`
- `batchTitlePickerDropdown` 외부 클릭이면 `closeBatchTitlePicker()` 호출
- `{once:true}` 리스너이므로 1회 실행 후 자동 해제

#### `closeBatchTitlePicker(): void`
- `#batchTitlePickerDropdown` 을 `display:none` 으로 숨김

#### `selectBatchTitleForRestore(title): async`
1. `closeBatchTitlePicker()` 호출
2. `#batchTitleInput` 에 `title` 입력 → `_doBatchTitleCheck()` 호출
3. `setStatus('배치 불러오는 중...')`
4. `GET /api/perspective/deploy-gallery/list?source=deploy&batch_title={title}&all=1` 호출
5. 항목 없으면 에러 메시지 표시 후 반환
6. 직원 ID 목록 수집: `[...new Set(entries.map(e => e.employee_id).filter(Boolean))]`
7. `_csvEmployeeIds = empIds` 설정
8. `#csvStatus` 에 `"✅ "title" — N명 복원됨"` 표시
9. 첫 번째 항목(`entries[0]`) 기준으로 설정 복원:
   - `#rowFieldSelect` → `onRowFieldChange()` → 30ms 대기 → `.rowValueCb` 체크 복원 → `rowCombineAll` 라디오
   - `#colModeSelect`: 저장값 없으므로 **변경 안 함**
   - `input[name="analysisType"]`: `ref.analysis_type` 에 해당하는 것만 체크
   - `applyWcOptions(ref.options)` 호출 (기존 함수 `perspective_test.html:2640`)
10. `setStatus("복원 완료 — N명 / 매트릭스 저장을 눌러 재실행하세요")`

---

### 4-B. sessionStorage 세션 복원 (부가 기능)

같은 브라우저 탭에서 이동 후 복귀 시 자동 복원 배너를 표시한다.
제출용 저장 기반 복원과 상호보완적으로 동작한다.

#### `_saveLastRunParams(): void`
- `generateMatrix()` 완료 직후 호출
- 다음 파라미터를 `sessionStorage('pt_last_run')` 에 JSON 저장:
  `empId`, `allEmp`, `csvIds`, `rowField`, `rowValues`, `rowCombineAll`, `colMode`,
  `analysisTypes`, `batchTitle`, `wco`, `includeNameInFilename`, `includeIdInFilename`, `savedAt`
- 저장 실패(용량 초과 등)는 silent catch

#### `_showRestoreBanner(params): void`
- `loadMeta()` 성공 후 `sessionStorage('pt_last_run')` 존재 시 호출
- `#resultArea` 에 복원 배너 렌더링 (저장 시각, 대상, 배치명 요약 포함)
- `[복원하기 (재실행)]` → `_restoreLastMatrix()` 호출
- `[무시]` → `_dismissRestore()` 호출

#### `_dismissRestore(): void`
- `sessionStorage.removeItem('pt_last_run')`
- `#resultArea` 초기 메시지로 복원

#### `_restoreLastMatrix(): async`
- `sessionStorage('pt_last_run')` 파싱
- 폼 상태 전체 복원 (직원 선택, X축, Y축, 분석 유형, 배치명, WC 옵션, 파일명 옵션)
- `generateMatrix()` 자동 호출

---

## 5. 호출 연결 지점

| 위치 | 코드 변경 |
|------|----------|
| `generateMatrix()` 완료 (`setStatus('완료')` 직후) | `_saveLastRunParams()` 추가 호출 |
| `loadMeta()` 성공 블록 (`setStatus(...)` 직후) | `sessionStorage('pt_last_run')` 체크 → `_showRestoreBanner()` 호출 |

---

## 6. 제약사항 및 한계

| 항목 | 내용 |
|------|------|
| `col_mode` 미복원 | 갤러리 deploy 항목에 저장 안 됨. UI 현재 선택값 유지 |
| `analysis_types` 단수 복원 | `analysis_type` 단수만 저장. 복원 시 1개 유형만 체크됨 |
| 관리자 전용 | `get_distinct_batch_titles(is_admin=False)` 는 `output_mode='real'` 항목 제외. 비관리자는 pseudonym 모드 배치만 노출됨 |
| sessionStorage 탭 한정 | `_saveLastRunParams` 는 탭을 닫으면 소멸. 영구 복원은 배치 명칭 피커를 사용할 것 |
| 대용량 CSV (수천 명) | `_csvEmployeeIds` 배열 전체를 sessionStorage에 저장하므로 직원 수에 따라 용량 초과 가능 → silent catch로 실패 무시 |

---

## 7. 테스트 시나리오

### 시나리오 A — 배치 명칭 피커 기본 흐름
1. 관리자 로그인 상태로 `perspective_test` 접근
2. `[📂]` 버튼 클릭 → 드롭다운에 과거 배치 명칭 목록 표시 확인
3. 명칭 선택 → `#batchTitleInput` 자동 입력, `#csvStatus`에 "N명 복원됨" 확인
4. `[매트릭스 저장]` 클릭 → 복원된 직원 대상으로 재분석 실행 확인

### 시나리오 B — 배치 명칭 피커 (저장 없음)
1. 갤러리에 `batch_title` 있는 항목이 없는 상태
2. `[📂]` 클릭 → "저장된 명칭 없음" 표시 확인

### 시나리오 C — sessionStorage 복원 배너
1. 매트릭스 저장 완료
2. 다른 페이지(`/gallery` 등) 이동 → 복귀
3. `#resultArea` 에 복원 배너 표시 확인 (저장 시각·대상 포함)
4. `[복원하기 (재실행)]` 클릭 → 폼 상태 복원 + 자동 재실행 확인
5. `[무시]` 클릭 → 배너 제거, 초기 메시지 확인

### 시나리오 D — 외부 클릭으로 드롭다운 닫기
1. `[📂]` 클릭으로 드롭다운 열기
2. 드롭다운 외부 영역 클릭 → 드롭다운 닫힘 확인

---

## 8. 변경 파일 목록

```
wordcloud_project/web/templates/perspective_test.html
  ├── action-row HTML: 배치명 입력 래퍼 + [📂] 버튼 + 드롭다운 div 추가
  ├── generateMatrix() 완료부: _saveLastRunParams() 호출 추가
  ├── loadMeta() 성공부: sessionStorage 체크 + _showRestoreBanner() 추가
  └── 신규 JS 함수 8개:
        toggleBatchTitlePicker, _batchPickerOutsideClick, closeBatchTitlePicker,
        selectBatchTitleForRestore,
        _saveLastRunParams, _showRestoreBanner, _dismissRestore, _restoreLastMatrix
```
