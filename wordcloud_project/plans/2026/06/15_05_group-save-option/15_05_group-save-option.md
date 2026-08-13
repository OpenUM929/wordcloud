# 그룹 분석 테스트 — 페이지 설정 저장, 전체직원 기본 체크, x축 통합출력 기본

> 상태: Done | 작성일: 2026-06-15 | 완료일: 2026-06-15

## 작업 개요

`perspective_test.html` — 그룹 분석 페이지의 UX 개선.

| 항목 | 요구사항 |
|------|----------|
| 1 | 모든 페이지 데이터를 사용자가 마지막에 설정한 값으로 sessionStorage 저장 및 자동 복원 |
| 2 | "전체 직원 대상" 체크박스 기본값 `checked` |
| 3 | x축(시가/회차) 개별출력/통합출력 순서 변경 + 통합출력 기본 선택 |

---

## 변경 사항

### ① 페이지 데이터 자동 저장/복원 (신규)

**파일**: `perspective_test.html`

#### 저장 함수 신규 생성 — `_autoSavePageState()`

- 저장 항목 (기존 `_saveLastRunParams()`와 동일한 필드):
  - `empId`, `allEmp`, `csvIds`
  - `rowField`, `rowValues`, `rowCombineAll`
  - `colMode`
  - `analysisTypes`
  - `batchTitle`
  - `wco` (word cloud options)
  - `includeNameInFilename`, `includeIdInFilename`
- 세션 저장소 키: `pt_page_state` (기존 `pt_last_run`과 별도)

#### 모든 form 컨트롤에 change 이벤트 연결

`DOMContentLoaded` 내부에서 다음 요소에 `change` 이벤트 리스너를 등록하여 `_autoSavePageState()` 호출:

| 요소 | 선택자 | 이벤트 |
|------|--------|--------|
| 직원 선택 | `#employeeSelect` | `change` |
| 전체 직원 체크 | `#allEmployeesCheck` | `change` |
| X축 select | `#rowFieldSelect` | `change` |
| Y축 select | `#colModeSelect` | `change` |
| 분석 유형 체크박스 | `input[name="analysisType"]` | `change` (위임) |
| 파일명 옵션 | `#includeNameInFilename`, `#includeIdInFilename` | `change` |
| 배치 명칭 입력 | `#batchTitleInput` | `input` (디바운스 300ms) |
| rowValue 체크박스 | `.rowValueCb` | — `onRowFieldChange()` 내부 생성이므로 MutationObserver로 감지 |
| rowOutputMode 라디오 | `input[name="rowOutputMode"]` | — `onRowFieldChange()` 내부 생성이므로 MutationObserver로 감지 |

#### MutationObserver로 동적 생성 요소 감지

`onRowFieldChange()`가 `#rowValuesContainer`의 내용을 동적으로 생성/교체하므로, `#rowValuesContainer`에 `MutationObserver`를 연결하여 하위 `.rowValueCb`와 `input[name="rowOutputMode"]`의 `change` 이벤트를 위임 처리한다.

#### 페이지 로드 시 자동 복원

`DOMContentLoaded` 내부, `loadMeta()` 호출 후 로직:

1. `sessionStorage.getItem('pt_page_state')` 확인
2. 값이 있으면 `_restorePageState(parsed)` 실행
3. 없으면 기본 상태 유지

#### `_restorePageState(params)` 함수 신규 생성

`_restoreLastMatrix()`의 복원 로직과 동일하게 동작하되, `generateMatrix()`를 **자동 호출하지 않음** (사용자가 [매트릭스 저장] 버튼을 누르도록 대기). 설정만 복원하고 결과는 복원하지 않음.

#### 기존 코드 영향

- `_saveLastRunParams()`는 그대로 유지 (generateMatrix 성공 시에도 저장)
- `pt_last_run` 키는 기존 복원 배너 용도로 유지 (충돌 없음)

---

### ② "전체 직원 대상" 체크박스 기본 체크

**파일**: `perspective_test.html` — line 252

**변경 전**:
```html
<input type="checkbox" id="allEmployeesCheck" onchange="toggleAllEmployees()">
```

**변경 후**:
```html
<input type="checkbox" id="allEmployeesCheck" onchange="toggleAllEmployees()" checked>
```

이미 `DOMContentLoaded` → `toggleAllEmployees()`에서 `cb.checked` 상태에 따라 `employeeSelect.disabled`를 설정하므로, `checked` 속성만 추가하면 정상 동작한다.

**영향도**:
- `loadMeta()` (line 531): `empSel.value = d.employees[0].employee_id` 실행되나 select는 disabled 상태이므로 무시됨
- `_restoreLastMatrix()` (line 1262-1264): `allEmp`가 true면 checked 세팅 후 `toggleAllEmployees()` 호출 — 충돌 없음
- `pt_page_state` 복원 시: 저장된 `allEmp` 값이 우선 적용됨

---

### ③ x축 통합출력 순서 변경 및 기본값

**파일**: `perspective_test.html` — lines 584-585 (함수 `onRowFieldChange()` 내부)

**변경 전**:
```javascript
html += '<label style="font-size:12px;"><input type="radio" name="rowOutputMode" value="individual" checked> 개별 출력</label>';
html += '<label style="font-size:12px;"><input type="radio" name="rowOutputMode" value="combined"> 통합 출력</label>';
```

**변경 후**:
```javascript
html += '<label style="font-size:12px;"><input type="radio" name="rowOutputMode" value="combined" checked> 통합 출력</label>';
html += '<label style="font-size:12px;"><input type="radio" name="rowOutputMode" value="individual"> 개별 출력</label>';
```

**영향도** (모두 명시적 값 세팅이므로 호환됨):
- `_restoreLastMatrix()` (line 1282-1285): `params.rowCombineAll`로 combined 세팅
- `selectBatchTitleForRestore()` (line 1183-1186): `ref.row_combine_all`로 combined 세팅
- `isRowCombineAll()` (line 595-598): `value === 'combined'` 비교 — 영향 없음
- `saveDeploy()` (line 1314+): `isRowCombineAll()` 호출 — 영향 없음
- `generateMatrix()` (line 954+): `isRowCombineAll()` 호출 — 영향 없음

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | §3 `_restorePageState` | csvIds/empId 브랜치에서 체크박스 강제 해제 및 select disabled 상태 보정 추가 |
| 2026-06-15 | §3 `_restorePageState` | `setTimeout` → `await new Promise(r => setTimeout(r, 30))`로 변경 (async) |
| 2026-06-15 | §3 `loadMeta` | 복원 후 `_autoSavePageState()` 호출하여 초기 상태 캡처 |
| 2026-06-15 | §3 `generateMatrix` 완료 후 | `_autoSavePageState()` 추가 호출 |

## 수정 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `web/templates/perspective_test.html` | 수정 | 3가지 요구사항 모두 이 파일 1개에서 처리 |

---

## 수정 상세 (v2)

### 버그 수정 ① — `_restorePageState` 체크박스/select 상태 불일치

**원인**: HTML에 `checked` 속성이 기본 추가되어 체크박스가 항상 체크된 상태로 시작. `_restorePageState(csvIds)` 또는 `_restorePageState(empId)` 실행 시 체크박스를 해제하지 않아 UI가 모순됨.

**변경 전**:
```javascript
} else if (params.csvIds && params.csvIds.length > 0) {
    _csvEmployeeIds = params.csvIds;
    // ... allEmployeesCheck remained checked from HTML default
} else if (params.empId) {
    document.getElementById('employeeSelect').value = params.empId;
    // employeeSelect remained disabled from DOMContentLoaded toggleAllEmployees
}
```

**변경 후**:
```javascript
} else if (params.csvIds && params.csvIds.length > 0) {
    _csvEmployeeIds = params.csvIds;
    document.getElementById('allEmployeesCheck').checked = false;     // 추가
    // ...
} else if (params.empId) {
    document.getElementById('allEmployeesCheck').checked = false;     // 추가
    document.getElementById('employeeSelect').disabled = false;       // 추가
    document.getElementById('employeeSelect').value = params.empId;
}
```

### 버그 수정 ② — `_restorePageState` setTimeout 타이밍

**원인**: `setTimeout(() => { ... }, 30)` 비동기로 인해 `loadMeta()`가 `_autoSavePageState()`를 호출할 때 rowValues 복원이 아직 완료되지 않음.

**변경 전**: `setTimeout(() => { ... }, 30)` — fire-and-forget
**변경 후**: `await new Promise(r => setTimeout(r, 30))` — async/await로 순차 처리

### 초기 상태 저장 추가

`loadMeta()` 마지막에 `_autoSavePageState()`를 호출하여 복원 후 현재 상태를 `pt_page_state`에 저장. 이를 통해:
- 복원된 상태가 즉시 저장됨
- 최초 방문 시에도 기본 상태가 저장되어 이후 새로고침 시 복원 가능

---

## 미적용 사항

- 결과 매트릭스 데이터는 저장/복원하지 않음 (용량 및 성능)
- `pt_last_run` / 복원 배너 기존 로직 유지 (호환성)

---

## 테스트 항목

1. 페이지 새로고침 후 모든 설정이 복원되는지 확인
2. "전체 직원 대상"이 페이지 로드 시 체크되어 있는지 확인
3. x축 라디오 버튼 순서가 "통합 출력 → 개별 출력"인지 확인
4. 통합 출력이 기본 선택되어 있는지 확인
5. 직원 개별 선택 → 새로고침 → 체크박스 해제/select 활성화 확인
6. CSV 업로드 → 새로고침 → 체크박스 해제/CSV 상태 표시 확인
7. 기존 pt_last_run 복원 배너가 여전히 동작하는지 확인
8. generateMatrix() 후에도 설정이 저장되는지 확인
