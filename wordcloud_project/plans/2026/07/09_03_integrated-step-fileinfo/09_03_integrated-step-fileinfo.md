> 상태: Done (DN) | 작성일: 2026-07-09 | 구현확인: 2026-07-09 | 종료: 2026-07-09

## 구현 완료 요약

- 대상: `web/templates/integrated_batch.html`(상단 인디케이터 원복), `web/static/js/integrated_batch.js`(`getUploadedFileLabel()` 추가 + `updateStepButtons()`의 `current-step-info`에 라벨 덧붙이기)
- 동작: 파일 업로드 시 `(파일명)`, 폴더 업로드 시 `(실제파일1, 실제파일2, …)`(>3개는 "외 N개" 축약)가 단계 라벨에 지속 표시
- 검증: `node -c` 통과, 폴더명(`inputs`)이 아닌 `file_structures[].filename` 사용으로 확정
- 영향: 백엔드/타 마법사 미변경, 알려진 제한(이어하기 시 `uploadedData` 미복원으로 파일명 미표시)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-09 | 전체 | 초안 (상단 인디케이터 방식) |
| 2026-07-09 | 전체 | **위치 변경**: 사용자 확인 결과 표시 위치는 상단 인디케이터가 아닌 하단 `current-step-info`임. 상단 변경 원복 → `current-step-info`에 라벨 덧붙이기로 재구현 |

---

# 통합데이터 생성 — `current-step-info`에 업로드 파일명 표시

## 1. 개요

통합데이터 생성(배치 처리) 마법사에서 데이터를 업로드하면, 하단 step-navigation 바의 **`current-step-info`**(예: "1단계: 데이터 업로드") 텍스트 옆에 현재 작업 중인 파일명을 `(파일명)` 형태로 지속적으로 표시한다. 단계를 이동해도 현재 단계 라벨 옆에 파일명이 따라붙어 "어떤 파일이 업로드 되었는지" 즉시 인지할 수 있다.

**작업 유형:** UI 기능 추가 (프론트엔드: HTML + JS)

---

## 2. 요구사항

| # | 요구사항 | 상세 |
|---|---------|------|
| 1 | `current-step-info`에 파일명 표시 | 하단 단계 라벨 텍스트 옆에 `(파일명)` 덧붙이기 |
| 2 | 지속 표시 | 단계 이동(매핑/미리보기/저장) 후에도 파일명 유지 |
| 3 | 폴더 업로드 표시 | 다중 파일인 경우 `폴더명 · N개 파일` 형태 |
| 4 | 미업로드 시 미표시 | 파일/폴더를 아직 올리지 않았으면 괄호 미표시 |
| 5 | 표시 위치 정확성 | 상단 `.step` 인디케이터가 아닌 하단 `current-step-info` (사용자 최종 확인) |

---

## 3. 구현 방식

### 3.1 데이터 소스 (실제 응답 구조 검증 완료)

두 업로드 경로 모두 성공 시 `uploadedData` 전역 객체를 채우며 `uploadedData.filename`에 이름이 들어간다. **폴더 업로드 응답의 `filename`은 폴더명(basename)임을 백엔드에서 확인** — `src/services/batch_service.py:173` `'filename': os.path.basename(inputs_dir)` → 예: `"inputs"`. (JS 폴더 설명 also `data.filename` 사용)

- 단일 파일 업로드: `integrated_batch.js` `uploadedData = data;` (DOMContentLoaded 내 fileInput change 핸들러)
- 폴더 업로드: `integrated_batch.js` `selectFolder()` 내 `uploadedData = data;`, 다중 파일 시 `uploadedData.file_structures.length` 로 개수 확인

> 폴더 응답 구조 예시: `{ success, filename: "inputs", rows, input_type: "folder", columns, file_structures: [{filename, columns, row_count}, ...], ... }`

### 3.2 표시 위치

하단 step-navigation 바의 `<span id="current-step-info">`. 이 요소는 `updateStepButtons()`가 단계 이동 시마다 `stepMessages[currentStep]` 값으로 갱신한다(기존 동작). 여기에 파일 라벨을 덧붙인다.

### 3.3 라벨 생성 규칙

| 조건 | 표시 형식 | 예 |
|------|-----------|-----|
| 단일 파일 | `기본라벨 (파일명)` | `1단계: 데이터 업로드 (평가_2025.csv)` |
| 폴더(다중 파일, ≤3개) | `기본라벨 (파일1, 파일2, ...)` | `1단계: 데이터 업로드 (a.csv, b.csv)` |
| 폴더(다중 파일, >3개) | `기본라벨 (처음 3개, 외 N개)` | `1단계: 데이터 업로드 (a.csv, b.csv, c.csv 외 2개)` |
| 미업로드 | `기본라벨` (변화 없음) | `1단계: 데이터 업로드` |

> 폴더 업로드는 시스템 폴더명(`inputs`) 대신 `uploadedData.file_structures[].filename`(실제 파일명)을 나열. 3개 초과 시 처음 3개만 보이고 "외 N개"로 축약.

---

## 4. 상세 구현 (완료)

### 4-1. HTML (`web/templates/integrated_batch.html`)

상단 `.step-indicator`의 4개 `.step` 블록에 임시로 추가했던 `<div class="step-file" id="stepFileN">` 영역 및 관련 CSS(`.step-file` / `.step.has-file .step-file`)를 **원복(제거)**. 표시 대상은 `current-step-info`(기존 요소, 변경 불필요)이므로 HTML 신규 추가 없음.

### 4-2. JS (`web/static/js/integrated_batch.js`) — 헬퍼 유지

`escapeHtml` 아래에 `getUploadedFileLabel()` 추가(유지):

```javascript
function getUploadedFileLabel() {
    if (!uploadedData || !uploadedData.filename) return '';
    var name = uploadedData.filename;
    var structures = uploadedData.file_structures;
    if (structures && structures.length > 1) {
        var names = structures.map(function(s) { return s.filename; });
        if (names.length > 3) {
            return names.slice(0, 3).join(', ') + ' 외 ' + (names.length - 3) + '개';
        }
        return names.join(', ');
    }
    return name;
}
```

### 4-3. JS — `updateStepButtons()`의 `current-step-info` 갱신에 라벨 덧붙이기

기존 `currentStepInfo.textContent = stepMessages[currentStep] || '';` 를 아래로 변경(완료):

```javascript
if (currentStepInfo) {
    var stepMessages = {
        1: '1단계: 데이터 업로드',
        2: '2단계: 통합데이터 매핑',
        3: '3단계: 미리보기',
        4: '4단계: 배치 처리 및 저장'
    };
    var base = stepMessages[currentStep] || '';
    var label = getUploadedFileLabel();
    currentStepInfo.textContent = base + (label ? ' (' + label + ')' : '');
}
```

### 4-4. 호출 위치 (별도 호출 불필요)

`updateStepButtons()`는 **업로드 성공 직후**(폴더 `selectFolder` / 파일 fileInput 핸들러 모두 호출) 및 **단계 이동**(`showStep`→`updateStepButtons`) 시마다 실행된다. 따라서 `current-step-info`가 갱신될 때마다 라벨이 자동 반영되므로, 추가 호출/함수(`updateStepFileInfo`)는 생성하지 않음(초안 대비 단순화).

> ⚠️ **비동기 타이밍 검증**: 페이지 로드 시 `uploadedData`를 동기 복원하는 로직이 없고, `이어하기(resume)`(`confirmResume()`)는 `/api/batch/resume` → SSE 처리로 직행해 `uploadedData`를 채우지 않는다. `current-step-info`는 `uploadedData`가 실제로 채워진 후 `updateStepButtons()`가 호출될 때만 갱신되므로 빈 타이밍 문제 없음. (이어하기 시 파일명 미표시는 기존과 동일한 제한.)

---

## 5. 수정 파일 목록

| # | 파일 경로 | 변경 내용 | 비고 |
|---|----------|-----------|------|
| 1 | `web/templates/integrated_batch.html` | 상단 인디케이터 `step-file`/CSS 원복 | -20줄 |
| 2 | `web/static/js/integrated_batch.js` | `getUploadedFileLabel()` 추가, `updateStepButtons()`의 `current-step-info` 할당에 라벨 덧붙이기 | +8줄 / -`updateStepFileInfo` |

**순변화: 코드량 감소 (상단 원복 + 단순화)**

---

## 6. 영향도 분석

### 6.1 기존 코드 영향

| 항목 | 영향 | 설명 |
|------|------|------|
| 단계 이동 로직 | ❌ 없음 | `showStep`/`updateStepIndicators` 미수정 |
| 업로드 로직 | ❌ 없음 | 기존 응답 처리 그대로 |
| 백엔드 API | ❌ 없음 | 프론트엔드 전용 변경 |
| 다른 마법사 | ❌ 없음 | `integrated_batch` 전용 |

### 6.2 예외 처리

| 상황 | 처리 |
|------|------|
| `uploadedData` 없음 | 라벨 공백 → 괄호 미표시 |
| 파일명 매우 김 | `current-step-info`는 부모 `.step-info` 영역 내 텍스트로 표시(별도 truncate 미적용, 자연스러운 줄바꿈/영역 폭 내 수용) |
| 폴더명에 괄호 포함 | 라벨 전체를 한 쌍의 소괄호로 감싸 구조 훼손 없음 |
| 이어하기 진입 | `uploadedData` 미복원 → 파일명 미표시(알려진 제한, 영향 미미) |

---

## 7. 테스트 항목

1. 파일 업로드 → "1단계: 데이터 업로드 (파일.csv)" 표시 확인
2. 폴더 선택(다중 파일) → "1단계: 데이터 업로드 (a.csv, b.csv, …)" 실제 파일명 나열 확인 (3개 초과 시 "외 N개" 축약)
3. 2/3/4단계 이동 → 각 단계 라벨("2단계: 통합데이터 매핑 (…)" 등)에 동일 파일명 지속 확인
4. 업로드 전에는 괄호 미표시("1단계: 데이터 업로드") 확인
5. 새 파일 업로드 시 기존 라벨이 새 파일명으로 갱신되는지 확인 (세션 내 덮어쓰기)
