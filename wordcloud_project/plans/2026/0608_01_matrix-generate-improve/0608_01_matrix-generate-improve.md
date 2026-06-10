# 0608_01_matrix-generate-improve — 매트릭스 생성 개선 계획 (rev-04, ✅ 구현 완료)

> 작성일: 2026-06-08
> 상태: **✅ 구현 완료** — 테스트 대기 중

---

## 1. 사용자 요구사항 정리

### 1.1 원래 질문
1. "매트릭스 생성을 할 경우에는 왜 제출용 저장 버튼 눌렀을 때처럼 현재 작업 로그가 출력되지 않는 거야?"
2. "제출용 저장처럼 다운로드 기능은 없는 거야?"

### 1.2 추가 요구사항
3. **기능 호출 방식/구조 = 제출용 저장과 동일하게** 일관성 유지
4. **공용 모듈로 재사용** (세션/폴링/Worker/진행로그)
5. **제출용 저장 버튼은 절대 건드리지 말 것** (이전처럼 똑같이)
6. **매트릭스 생성 ≠ 제출용 저장**: 매트릭스 생성은 "미리보기", 제출용 저장은 "영속 저장"

### 1.3 확정 사항

| 항목 | 결정 |
|------|------|
| **매트릭스 생성 manifest 등록** | ❌ 안 함 (미리보기는 갤러리에 등록하지 않음) |
| **매트릭스 생성 실패 재시도** | ❌ 없음 (미리보기라 불필요) |
| **매트릭스 생성 ZIP 다운로드** | ✅ 있음 (완료 후 전체 ZIP 버튼) |
| **매트릭스 생성 진행 로그** | ✅ 있음 (제출용 저장과 동일한 UI) |
| **공용 모듈화** | ✅ `runSessionProcess()` 공용 함수로 추출 |

---

## 2. 설계: 공용 모듈 (Session Process Runner)

### 2.1 핵심 설계 원칙

> **제출용 저장**과 **매트릭스 생성**은 **내부 구조(세션/폴링/Worker/진행로그)는 공유**하되, **최종 동작(저장 vs 미리보기)은 다르다**.

### 2.2 공용 함수: `runSessionProcess(params)`

`saveDeploy()`와 `generateMatrix()`의 **공통 로직**을 하나의 공용 함수로 추출합니다.

```javascript
// perspective_test.html
async function runSessionProcess(params) {
  // === 공통 입력 ===
  // params.apiUrl          : '/api/perspective/matrix/save-deploy'  또는 '/api/perspective/matrix/generate-and-save'
  // params.options         : 공통 옵션 (row_field, col_mode, analysis_types, ...)
  // params.employeeSource  : {csvIds, allEmp, empId}
  // params.buildRequestBody: (options, eid) => requestBody (각 API에 맞는 body 구성)
  // params.onComplete      : (summary, extraData) => void (완료 후 렌더링 콜백)
  // params.sessionKey      : 'deploy_session_id' 또는 'matrix_session_id' (localStorage key)
  // params.title           : '제출용 저장 중...' 또는 '매트릭스 생성 중...'
  // params.collectExtraData: boolean (matrix_data 등 추가 데이터 수집 여부)
  
  // === 공통 로직 (saveDeploy와 동일) ===
  // 1. 세션 생성 (/deploy-session/start)
  // 2. Chunk 폴링 (/deploy-session/chunk?count=50)
  // 3. Worker Sharding (4개 워커 병렬 처리)
  // 4. 각 직원마다 params.apiUrl 호출
  // 5. addLine() + renderProgress() (진행 로그/진행률 실시간)
  // 6. 완료 보고 (/deploy-session/complete)
  // 7. renderDeployComplete() (성공/실패 요약, 다운로드)
  // 8. params.onComplete() 호출
}
```

### 2.3 사용 예시

```javascript
// 제출용 저장 (기존 동작 그대로)
async function saveDeploy(resumeSessionId = null) {
  await runSessionProcess({
    apiUrl: '/api/perspective/matrix/save-deploy',
    options: { ... },
    employeeSource: { csvIds, allEmp, empId },
    buildRequestBody: (opts, eid) => ({ ...opts, employee_id: eid }),
    onComplete: (summary) => {
      // renderDeployComplete만 호출 (기존과 동일)
      renderDeployComplete(summary);
    },
    sessionKey: 'deploy_session_id',
    title: '제출용 저장 중...',
    showGalleryLink: true,
    showRetryButton: true,
  });
}

// 매트릭스 생성 (세션 기반 + 완료 후 테이블)
async function generateMatrix() {
  await runSessionProcess({
    apiUrl: '/api/perspective/matrix/generate-and-save',
    options: { ... },
    employeeSource: { csvIds, allEmp, empId },
    buildRequestBody: (opts, eid) => ({ ...opts, employee_id: eid }),
    onComplete: (summary, extraData) => {
      // 1. renderDeployComplete (다운로드 UI)
      renderDeployComplete(summary, {
        title: '✅ 매트릭스 생성 완료',
        showGalleryLink: false,
        showRetryButton: false,
      });
      // 2. 매트릭스 테이블 미리보기
      if (extraData.matrixData && Object.keys(extraData.matrixData).length > 0) {
        renderMatrixPreview(extraData.matrixData, extraData.analysisTypes);
      }
    },
    sessionKey: 'matrix_session_id',
    title: '매트릭스 생성 중...',
    showGalleryLink: false,
    showRetryButton: false,
    collectExtraData: true,  // matrix_data 수집
  });
}
```

---

## 3. 백엔드 API 설계

### 3.1 `/matrix/generate-and-save` (POST) — 신규 추가

**목적**: 매트릭스 생성 + 결과 반환 (미리보기용). 서버에 파일 저장 안 함.

**동작**:
1. `generate_perspective_matrix()` 호출 → 매트릭스 데이터 + wordcloud_url 생성
2. wordcloud_url을 기반으로 **save_result 형태로 패키징** (URL만 수집, 실제 파일 저장 안 함)
3. 응답: `{success, save_result, matrix_data}`

**제출용 저장과의 차이**:

| 구분 | `/matrix/save-deploy` | `/matrix/generate-and-save` |
|------|----------------------|----------------------------|
| 목적 | 파일 영속 저장 | 매트릭스 미리보기 |
| 서버 저장 | `outputs/배포/`에 PNG 저장 | 저장 안 함 |
| manifest 등록 | `deploy_manifest.json`에 등록 | 등록 안 함 |
| 갤러리 노출 | ✅ | ❌ |
| 응답 | `{success, ...saveResult}` | `{success, save_result, matrix_data}` |

### 3.2 `/matrix/save-deploy` (POST) — 기존 그대로 유지

**변경 없음.** 세션/Chunk/Worker/진행로그 모두 기존과 동일.

---

## 4. 완료 후 화면 구성

### 4.1 제출용 저장 (기존 그대로)

```
[상단] ✅ 제출용 저장 완료  N/M 성공
[진행률 바] 100%
[개별 다운로드] [⬇️ ZIP] [갤러리에서 확인 →]
[실패 목록 + ✏️ 실패 사번 수정 → 버튼]
```

### 4.2 매트릭스 생성 (신규)

```
[상단] ✅ 매트릭스 생성 완료  N/M 성공
[진행률 바] 100%
[개별 다운로드] [⬇️ ZIP]

[하단] 📊 매트릭스 미리보기
▶ 직원A  2행×3열
  [테이블: 연도/부서별 × NLP/감정/리더십 ...]
▶ 직원B  2행×3열
  ...
```

**차이점 요약**:

| 요소 | 제출용 저장 | 매트릭스 생성 |
|------|-----------|--------------|
| 타이틀 | "제출용 저장 완료" | "매트릭스 생성 완료" |
| 갤러리 링크 | ✅ | ❌ |
| 실패 재시도 | ✅ | ❌ |
| 하단 콘텐츠 | 없음 | 매트릭스 테이블 |

---

## 5. 수정 대상 파일 및 상세 작업

### 5.1 `src/routes/perspective_routes.py`

| # | 작업 | 라인 위치 |
|---|------|----------|
| 1 | `/matrix/generate-and-save` 엔드포인트 추가 | `/matrix/save-deploy` 바로 위에 추가 |
| 2 | `generate_perspective_matrix()` 호출 후 `save_result` + `matrix_data` 반환 | 신규 함수 내 |
| 3 | `/matrix/save-deploy`는 **변경 없음** | 기존 위치 유지 |

### 5.2 `web/templates/perspective_test.html`

| # | 작업 | 대상 함수/위치 |
|---|------|--------------|
| 1 | `runSessionProcess(params)` 공용 함수 생성 | `generateMatrix()` 바로 위에 추가 |
| 2 | `saveDeploy()` → `runSessionProcess()` 사용하도록 리팩토링 | 기존 `saveDeploy()` 대체 |
| 3 | `generateMatrix()` → `runSessionProcess()` 사용하도록 재작성 | 기존 `generateMatrix()` 대체 |
| 4 | `renderDeployComplete()` 확장 | `title`, `showGalleryLink`, `showRetryButton` 옵션 추가 |
| 5 | `renderMatrixPreview()` 추가 | `renderDeployComplete()` 호출 후 하단에 테이블 렌더링 |
| 6 | 가명 라디오 버튼 숨김 유지 | 이미 완료 |
| 7 | `_resolve_output_mode()` 가명 무시 유지 | `perspective_routes.py`에서 이미 완료 |

---

## 6. 체크리스트 (구현 후 검증)

### 6.1 제출용 저장 (기존 동작 유지 확인)

- [ ] "제출용 저장" 클릭 시 세션 생성 → Chunk 폴링 → Worker 병렬 처리 동작
- [ ] 진행 로그 (⏳/✅/❌) 실시간 출력
- [ ] 진행률 바 실시간 업데이트
- [ ] 완료 후 갤러리 링크 표시
- [ ] 완료 후 실패 재시도 버튼 표시
- [ ] 완료 후 ZIP 다운로드 가능
- [ ] 실패 시 이어하기(Resume) 동작

### 6.2 매트릭스 생성 (신규 기능 확인)

- [ ] "매트릭스 생성" 클릭 시 세션 생성 → Chunk 폴링 → Worker 병렬 처리 동작
- [ ] 진행 로그 (⏳/✅/❌) 실시간 출력 (제출용 저장과 동일한 UI)
- [ ] 진행률 바 실시간 업데이트
- [ ] 완료 후 타이틀 = "매트릭스 생성 완료"
- [ ] 완료 후 갤러리 링크 **없음**
- [ ] 완료 후 실패 재시도 버튼 **없음**
- [ ] 완료 후 ZIP 다운로드 가능
- [ ] 완료 후 하단에 매트릭스 테이블 미리보기 표시
- [ ] 갤러리에 매트릭스 생성 결과가 등록되지 않음

### 6.3 공용 모듈 확인

- [ ] `runSessionProcess()`가 `saveDeploy`와 `generateMatrix` 모두에서 호출됨
- [ ] 동일한 세션/Chunk/Worker/진행로그 로직이 공유됨
- [ ] 각 기능의 `onComplete` 콜백만 다르게 동작함

---

## 7. 참고: 이전 잘못된 구현 교훈

### 7.1 잘못 (rev-01 ~ rev-02)

- **오해**: "매트릭스 생성도 제출용 저장처럼 진행 로그와 다운로드를 보여줘" → "매트릭스 생성 자체를 제출용 저장과 똑같은 동작으로 만들라"
- **결과**: `generateMatrix()`를 세션 기반으로 바꿨으나, 완료 후 `renderDeployComplete()`만 호출하고 매트릭스 테이블을 보여주지 않음. 사용자가 "제출용 저장으로 바뀌었다"고 인식.

### 7.2 바른 접근 (rev-04)

- **핵심**: 세션/폴링/Worker/진행로구는 **공용 모듈**로 재사용
- **차이점**: 완료 후 콜백만 다르게
  - 제출용 저장: `renderDeployComplete()` (저장 결과 + 갤러리 + 재시도)
  - 매트릭스 생성: `renderDeployComplete()` (다운로드만) + `renderMatrixPreview()` (테이블)
- **경계 유지**: 매트릭스 생성은 **미리보기**, 제출용 저장은 **영속 저장**

---

## 8. 구현 후 발견된 문제 및 수정 (2026-06-08)

### 8.1 문제: 매트릭스 생성 완료 후 "통합/긍정/부정 워드클라우드"가 출력됨

**원인**: `generateMatrix()`의 `onComplete`에서 `renderDeployComplete()`를 호출했는데, 이 함수가 `save_result`를 기반으로 통합/긍정/부정 워드클라우드 이미지를 렌더링하기 때문.

**결과 화면 (잘못된)**:
```
[상단] ✅ 매트릭스 생성 완료
[통합 워드클라우드] [긍정 워드클라우드] [부정 워드클라우드]
[하단] 📊 매트릭스 미리보기 테이블
```

→ 사용자가 "매트릭스 생성을 했는데 왜 제출용 저장 화면이 나오냐"는 불만.

### 8.2 수정 방안

**원칙**: 매트릭스 생성의 완료 화면은 **XY 매트릭스 테이블만** 보여야 한다. 통합/긍정/부정 워드클라우드 이미지는 제출용 저장에서만 표시.

**구현**:
1. `renderDeployComplete(summary, opts)`에 `showImagePreviews = true` 옵션 추가
2. 매트릭스 생성의 `onComplete`에서 `renderDeployComplete(summary, {showImagePreviews: false, ...})` 호출
3. 제출용 저장은 기본값(`true`)으로 동작 변경 없음

**수정 후 화면 (매트릭스 생성)**:
```
[상단] ✅ 매트릭스 생성 완료  N/M 성공
[진행률 바] 100%
[⬇️ ZIP 다운로드]

[하단] 📊 매트릭스 미리보기
▶ 직원A  2행×3열
  [테이블: 연도/부서별 × NLP/감정/리더십 ...]
```

**통합/긍정/부정 워드클라우드 이미지는 완전히 제거됨**.
