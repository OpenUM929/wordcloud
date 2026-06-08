# 제출용 저장 완료 시 워드클라우드 인라인 미리보기 복구 계획서

- **작성일시**: 2026-06-05
- **작업 유형**: 버그 수정 / 기능 복구 (사전 승인 없이 제거된 기능 원상복구)
- **상태**: PND (Pending, 승인 대기)
- **계획서 경로**: `wordcloud_project/plans/restore-deploy-preview_260605_01/restore-deploy-preview_260605_01.md`

---

## 1. 사고 경위

### 무엇이 제거되었나
`saveDeploy()` 완료 후 `renderDeployComplete()` 함수의 **"전부 성공 시" 조건 분기**에서, 인라인 워드클라우드 썸네일 미리보기가 사용자 승인 없이 제거되었습니다.

### 언제 제거되었나
커밋 `81be7dd` ("로그인으로 변경, 갤러리 기능 추가") 에서 `renderDeployComplete` 함수가 신규 작성될 때 성공 경로의 미리보기가 생략되었고, 이 상태가 현재까지 유지됩니다.

### 제거 전 동작 (원래 기능)
저장 완료 후 `resultArea`에 **각 직원별 워드클라우드 썸네일 3종(통합·긍정·부정)** 을 인라인으로 표시:
- 직원명 헤더
- 연도(rowKey)별 구분 행
- 통합 / 긍정 / 부정 이미지 썸네일 (클릭 시 모달 확대)
- 감지 문장 목록 (옆에 소자 텍스트)
- 욕설 감지 경고 블록
- 실패 시 재시도 버튼

### 현재 동작 (잘못된 상태)
**전부 성공 시**: 토스트 1개 + "갤러리에서 확인 →" 텍스트 링크만 표시. 미리보기 없음.
**일부 실패 시**: 성공분 미리보기 + 실패 목록 + 재시도 버튼 (정상 동작).

즉, 실패가 있어야만 미리보기가 보이는 역설적 상태입니다.

---

## 2. 복구 범위

### 수정 대상 파일
| 파일 | 변경 유형 |
|------|----------|
| `web/templates/perspective_test.html` | `renderDeployComplete()` 내 early-return 블록 제거 |

**다른 파일 수정 없음.** 백엔드·CSS·기타 JS 변경 불필요.

### 유지할 신규 기능 (갤러리 추가분)
- `showDeployToast()` — 우측 하단 토스트 알림 **유지**
- 성공 헤더 바에 "갤러리에서 확인 →" 링크 **추가** (이전에는 없던 편의 기능이므로 함께 유지)

---

## 3. 변경 상세

### 제거 대상 블록 (perspective_test.html 현재 1141~1158행)

```javascript
// ❌ 이 블록 전체 제거
if (failCountItems === 0 && successCount > 0) {
    showDeployToast('✅ ' + successCount + '명 저장 완료', '/deploy-gallery');
    let h = '<div class="summary-bar" style="background:#d4edda;border-color:#c3e6cb;color:#155724;">';
    h += '<span><strong>✅ 저장 완료</strong></span>';
    h += '<span>' + successCount + '명의 이미지가 갤러리에 저장되었습니다.</span>';
    h += '<a href="/deploy-gallery" ...>갤러리에서 확인 →</a>';
    h += '</div>';
    ...
    return;   // ← 여기서 함수 종료 (미리보기 렌더링 도달 불가)
}
```

### 복구 후 동작

성공/실패 여부와 관계없이 항상 전체 미리보기를 렌더링하고, 헤더 바에 갤러리 링크를 추가:

```javascript
function renderDeployComplete(summary) {
    const successItems = summary.success || [];
    const failItems   = summary.fail   || [];
    ...

    // 토스트는 항상 표시 (성공이 있을 때)
    if (successCount > 0) {
        showDeployToast('✅ ' + successCount + '명 저장 완료', '/deploy-gallery');
    }

    // 헤더 바 — 성공 시 갤러리 링크 포함
    let h = '<div class="summary-bar" style="background:#d4edda;border-color:#c3e6cb;">';
    h += '<span><strong>✅ 제출용 저장 완료</strong></span>';
    h += '<span>' + successCount + '/' + totalItems + ' 성공</span>';
    if (failCountItems > 0) h += '<span style="color:#dc3545;">' + failCountItems + '건 실패</span>';
    if (successCount > 0) {
        h += '<a href="/deploy-gallery" style="margin-left:auto;color:#155724;font-size:12px;font-weight:bold;text-decoration:underline;">갤러리에서 확인 →</a>';
    }
    h += '</div>';

    // ... (이하 기존 미리보기 렌더링 코드 동일)
```

---

## 4. 리스크 평가

| 항목 | 평가 |
|------|------|
| 영향 범위 | `renderDeployComplete()` 함수 내부만 |
| 회귀 위험 | 없음. 기존 미리보기 코드(1160~1260행)는 현재도 존재하며 실패 케이스에서 정상 동작 중 |
| 신규 기능 영향 | 없음. 갤러리 링크·토스트는 유지 |
| 데이터 변경 | 없음 |

변경 줄 수: 약 15줄 수정 (early-return 블록 제거 + 헤더 바 갤러리 링크 조건 추가).

---

## 5. 검증 방법

1. `제출용 저장` 실행 (전체 성공 케이스)
   - 결과: 저장 후 `resultArea`에 각 직원 썸네일 표시, 클릭 시 모달 확대 ✓
   - 결과: 우측 하단 토스트 표시 ✓
   - 결과: 헤더 바에 "갤러리에서 확인 →" 링크 표시 ✓

2. `제출용 저장` 실행 (일부 실패 케이스)
   - 결과: 성공분 미리보기 + 실패 목록 + 재시도 버튼 ✓ (기존과 동일)

---

## 6. 수행 승인 요청

"수행"을 명시적으로 입력하시면 위 변경을 진행합니다.
