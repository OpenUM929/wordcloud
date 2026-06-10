# 실패 사번 수정 재시도 시 failData 중복 누적 버그 수정

> 상태: DN | 작성일: 2026-06-09 | 완료일: 2026-06-09

## 1. 버그 요약

그룹 분석 → 제출용 저장 → 실패 사번 수정(재시도) 시, 동일한 실패 사번이 `failData` 배열에 2회 누적되어 UI에 2배로 표시되는 버그.

## 2. 버그 상세

### 2.1 재현 조건
1. `perspective_test.html`에서 전체 직원 대상, x축=2026년, 통합 출력, y축=전체 설정
2. **제출용 저장** 버튼 클릭
3. 일부 직원(예: 5명) 처리 실패 → `failData`에 5명 저장
4. `renderDeployComplete`에서 **실패 사번 수정** 버튼 표시
5. 버튼 클릭 → `openIdInputModal(failedIds, sessionId)` 모달 열림
6. 수정 후 **확인** → `confirmIdInput()` → `saveDeploy(sessionId)` 재시도
7. 다시 실패 시 `failData`에 기존 5명 + 새로 5명 = **10명**으로 중복 출력

### 2.2 코드 흐름

```
saveDeploy(resumeSessionId)
  ├─ existingFailData ← get_session_tasks(failed)  // 5명
  ├─ failData = [...existingFailData]               // 5명
  ├─ retry (failed → pending 리셋)
  ├─ chunk 폴링 → pending 5명 할당
  │   └─ processOne(eid)
  │       ├─ 성공: failData.splice(제거)  ← 중복 방지 있음
  │       └─ 실패: failData.push(...)     ← 중복 방지 없음 ✗
  └─ renderDeployComplete({fail: failData})  // 중복 포함 10명
```

### 2.3 문제 코드 위치

`wordcloud_project/web/templates/perspective_test.html`
- `saveDeploy()` 함수 내부 `processOne()` 함수
- **1203행**: `failData.push({employee_id: eid, error: d.error || '처리 실패'});`
- **1209행**: `failData.push({employee_id: eid, error: '네트워크 오류'});`

두 곳 모두 `push` 전에 동일 `employee_id` 존재 여부를 검사하지 않음.

## 3. 수정 대상

| 파일 | 위치 | 내용 |
|------|------|------|
| `web/templates/perspective_test.html` | `saveDeploy()` 내 `processOne()` 1203행 | 실패 시 `failData.push` 전 중복 검사 추가 |
| `web/templates/perspective_test.html` | `saveDeploy()` 내 `processOne()` 1209행 | catch 블록 동일 수정 |

## 4. 수정 계획

### 4.1 수정 방식

`processOne` 함수 내 실패 핸들링(`else` 블록, `catch` 블록)에서 `failData.push` 전에 동일 `employee_id`가 이미 존재하는지 `Array.find()`로 검사:

```javascript
// AS-IS (중복 발생)
failData.push({employee_id: eid, error: d.error || '처리 실패'});
failCount++;

// TO-BE (중복 방지)
const fi = failData.findIndex(f => f.employee_id === eid);
if (fi === -1) {
    failData.push({employee_id: eid, error: d.error || '처리 실패'});
    failCount++;
} else {
    failData[fi].error = d.error || '처리 실패';  // 에러 메시지만 갱신
}
```

`catch` 블록도 동일 패턴 적용.

### 4.2 영향도

- **failData 배열**: 중복 방지로 정확한 실패 건수 유지
- **failCount**: 중복 증가 방지
- **renderDeployComplete**: 정확한 `failCountItems`로 UI 표시
- **실패 사번 수정 버튼**: 중복 없는 정확한 `failedIds` 전달
- **다른 기능**: 영향 없음 (`processOne` 내부만 변경)

## 5. 위험도 및 검증

| 항목 | 내용 |
|------|------|
| 위험도 | 낮음 (로컬 변수 배열 조작, API/DB 변경 없음) |
| 검증 방법 | 재시도 시나리오 재현 후 failData 길이 확인 |

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-09 | 전체 | 최초 작성 |
