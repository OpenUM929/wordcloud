# 계획서 — perspective_test 정렬 기능 개선

> 상태: **구현 완료 · 실동작(브라우저) 검증 대기** (PND) | 작성일: 2026-06-30
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 없음

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-30 | 전체 | 최초 작성 |
| 2026-07-01 | §2,4.1,4.4,5.1,9 | 코드 실측 검토 반영: `override_score` 정렬키 제거(응답 부재), 매트릭스 다중타입 정렬 기준 규칙 추가, 중립 matrix 셀은 백엔드 변경 필요로 이번 범위 제외, §3.2 evaluation_count 위치 정정 |
| 2026-07-01 | 구현 | `perspective_test.html`에 정렬 기능 구현(§4.0~4.5). 정렬 유틸 블록 1개 + 6개 함수 배선(renderDeployComplete·renderDeployPage·renderAllEmployees·renderMatrixPage·renderCellSection·renderMatrix). additive·시그니처 불변. JS 문법 검증(`node --check`) 통과. **실동작 검증 대기(PND)** |

---

## 1. 배경 및 목적

`/perspective_test` 그룹 분석 페이지에서 **매트릭스 생성** 및 **제출용 저장** 후 결과 화면에 정렬 기능이 전혀 없어, 사용자가 다음 정보를 파악하기 어렵다:
- 긍정률/부정률이 높은 순으로 직원/셀 보기
- 욕설 건수가 많은 순으로 결과 정렬
- 단어 빈도수나 감정 점수 순으로 단어 리스트 정렬

**목표**: 매트릭스 셀, 배포 결과 직원 리스트, 감정 문장 리스트, 워드클라우드 단어 리스트에 **오름차순/내림차순 정렬 기능**과 **긍정/부정/중립/욕설 값 기준 정렬**을 추가한다.

---

## 2. 요구사항

1. **매트릭스 테이블 내 셀 정렬**: 행/열 헤더 클릭 시 해당 컬럼/로우의 셀 값을 기준으로 정렬
2. **전체 직원 리스트 정렬 (renderMatrixPage)**: 긍정률·부정률·욕설건수·평가건수 기준 오름/내림차순 정렬
3. **제출용 저장 결과 정렬 (renderDeployPage)**: 긍정문장수·부정문장수·중립문장수·욕설건수 기준 정렬
4. **감정 문장 리스트 정렬 (셀 내 positive/negative_sentence_details)**: confidence·kote_pos/kote_neg(극성강도) 기준 정렬 (~~override_score~~ 응답 details에 부재 → 제외)
5. **워드클라우드 단어 리스트 정렬 (top_words)**: 빈도수·감정점수 기준 정렬

---

## 3. 현재 시스템 분석

### 3.1 관련 파일/함수 (grep/read 실측 결과)

| 파일 | 함수/변수 | 역할 |
|------|-----------|------|
| `web/templates/perspective_test.html:2566` | `renderMatrix(data, container, types)` | 단일 직원 매트릭스 테이블 렌더링 (행×열 헤더 정렬 없음) |
| `web/templates/perspective_test.html:2725` | `renderAllEmployees(data, container)` | 전체 직원 결과 집계 + 페이징 초기화 (정렬 없음) |
| `web/templates/perspective_test.html:2764` | `renderMatrixPage()` | 페이지 단위 직원별 아코디언 매트릭스 렌더링 (정렬 없음) |
| `web/templates/perspective_test.html:2139` | `renderDeployComplete(summary)` | 제출용 저장 완료 화면 (옵션바 없음) |
| `web/templates/perspective_test.html:2238` | `renderDeployPage(page)` | 직원별 배포 결과 렌더링 (정렬 없음) |
| `web/templates/perspective_test.html:2609` | `renderCellSection(d, type)` | 셀 내 NLP·감정·욕설 상세 HTML (문장/단어 정렬 없음) |
| `web/templates/perspective_test.html:2697` | `renderCell(cell, types)` | 셀 전체 렌더링 |
| `web/templates/perspective_test.html:2005` | `_buildEmployeeResultHtml(res, expandWc, expandSent)` | 배포 결과 개별 직원 HTML (문장 리스트 정렬 없음) |

### 3.2 데이터 구조 (분석 시점 확인)

**매트릭스 셀 데이터** (`cell[type]`):
```
nlp:     {avg_sentiment: {positive, negative}, top_words: {word: count}, 
          evaluation_count, wordcloud_url, total_words}
emotion: {avg_sentiment: {positive, negative}, emotion_labels: {label: count},
          positive_sentence_details: [{text, confidence, kote_pos, kote_neg, ...}],
          negative_sentence_details: [{text, confidence, ...}], evaluation_count}
profanity: {total_profanity_count, profanity_ratio, profanity_words: [],
            profanity_sentences: [{evaluator_id, original_text, ...}]}
```
> 정정: `evaluation_count`는 각 type 안이 아니라 **셀 레벨**(`cell.evaluation_count`, `perspective_test.html:2703`)에 있다. §4.1 본문 접근(`matrix[rk][ck].evaluation_count`)이 옳다.

**제출용 저장 결과** (`res`):
```
{employee_id, name, combined, positive, negative,
 positive_sentence_details, negative_sentence_details, neutral_sentence_details,
 profanity_summary: {total_count, profanity_sentences},
 row_results: {rowKey: {combined, positive, negative, combined_sentences,
                        positive_sentence_details, negative_sentence_details,
                        neutral_sentence_details}}}
```

---

## 4. 구현 상세

### 4.0 공통 정렬 유틸리티 (프론트엔드)

`perspective_test.html` 최상단(기존 JS 상단)에 정렬 유틸리티 함수와 상태 변수를 추가한다.

```javascript
// 정렬 상태 관리 (전역)
let _sortState = { key: null, order: 'desc', type: 'deploy' };
// type: 'deploy' | 'matrix-employees' | 'matrix-rows' | 'matrix-cols'

// 정렬 아이콘 HTML
function sortIcon(key, state) {
    if (state.key !== key) return ' · ';
    return state.order === 'asc' ? ' ▲' : ' ▼';
}

// 배열 정렬 헬퍼 — key가 함수면 계산값 정렬
function sortArray(arr, keyFn, order) {
    return [...arr].sort((a, b) => {
        const av = keyFn(a), bv = keyFn(b);
        if (av === bv) return 0;
        return (av > bv ? 1 : -1) * (order === 'desc' ? 1 : -1);
    });
}

// 문자열·숫자 하이브리드 정렬
function safeCmp(a, b) {
    const na = Number(a), nb = Number(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return String(a).localeCompare(String(b));
}
```

### 4.1 매트릭스 테이블 내 셀 정렬

**대상**: `renderMatrix(data, container, analysisTypes)` — 단일 직원 매트릭스

**변경 사항**:
- `cols` 배열 순서 변경 (열 헤더 클릭 → 해당 컬럼 값 기준으로 행 재정렬) — **행 기준 정렬이 더 직관적**이므로, **열 헤더 클릭 시 해당 열의 모든 행 셀을 비교하여 행 순서 재정렬**
- `rows` 배열 순서 변경 (행 헤더 클릭 → 해당 행의 모든 열 셀을 비교하여 열 순서 재정렬)
- 현재 `matrix[rk][ck]` 구조이므로, 정렬 시 `rows`/`cols` 배열 순서만 변경하여 matrix 접근 보존

**정렬 키**(헤더 클릭 시 순환: 오름차순 → 내림차순 → 원래순서):
| 정렬 키 | 데이터 추출 | 적용 대상 |
|---------|-------------|-----------|
| 평가 건수 | `matrix[rk][ck].evaluation_count` | 행·열 |
| 긍정률 | `matrix[rk][ck]?.[type]?.avg_sentiment?.positive || 0` | 행·열 |
| 부정률 | `matrix[rk][ck]?.[type]?.avg_sentiment?.negative || 0` | 행·열 |
| 욕설 건수 | `matrix[rk][ck]?.profanity?.total_profanity_count || 0` | 행·열 |

**다중 분석타입 규칙(검토 반영)**: `_matrixTypes`가 복수(`['nlp','emotion',...]`)이고 nlp·emotion 모두 `avg_sentiment`를 가지므로, 긍정률/부정률 정렬 시 **기준 타입 = emotion 우선, 없으면 nlp**로 고정한다(`analysisTypes` 배열에서 첫 매칭). 욕설은 `profanity`, 평가건수는 셀 레벨.

**구현**: 테이블 헤더 클릭 핸들러(이벤트 위임 or 헤더에 `onclick` 추가)로 `renderMatrix()` 재호출

### 4.2 전체 직원 리스트 정렬 (renderMatrixPage)

**대상**: `renderMatrixPage()` — `_matrixEmpIds` 기준으로 직원 목록 정렬

**현재**: `_matrixEmpIds`를 `Object.keys(results).sort()`로 항상 사번순 정렬

**변경 사항**:
- 옵션 바에 정렬 드롭다운 `<select>` 추가
- `_matrixEmpIds`를 선택된 정렬 기준으로 재정렬
- 기존 `sort()`를 정렬 함수로 교체

**정렬 드롭다운 옵션**:
```
사번순 (기본)    → employee_id 문자열 비교
평가건수 순      → results[empId].rows × cols 전체 셀의 evaluation_count 합산
긍정률 높은 순   → 셀 avg_sentiment.positive 평균
부정률 높은 순   → 셀 avg_sentiment.negative 평균
욕설 건수 많은 순 → 셀 profanity.total_profanity_count 합산
```

**정렬 방향 토글 버튼**: 옆에 ▲/▼ 토글 버튼 추가

### 4.3 제출용 저장 결과 정렬 (renderDeployPage)

**대상**: `renderDeployPage(page)` — `_deployResults` 배열의 직원별 결과 정렬

**현재**: 직원 저장 완료 순서(`successItems` push 순) 그대로 노출

**변경 사항**:
- 옵션 바(`summary-bar` 내부)에 정렬 드롭다운 + 방향 토글 추가
- `_deployResults` 정렬 후 `renderDeployPage(1)` 재호출

**정렬 드롭다운 옵션**:
| 옵션 | 데이터 키 | 비교값 |
|------|-----------|--------|
| 저장 순서 (기본) | index | push 순서 유지 |
| 긍정 문장 수 | `res.positive_sentence_details?.length \|\| 0` | 내림차순 |
| 부정 문장 수 | `res.negative_sentence_details?.length \|\| 0` | 내림차순 |
| 중립 문장 수 | `res.neutral_sentence_details?.length \|\| 0` | 내림차순 |
| 욕설 건수 | `res.profanity_summary?.total_count \|\| 0` | 내림차순 |
| 긍정률 | positive/(positive+negative) 비율 | 내림차순 |
| 부정률 | negative/(positive+negative) 비율 | 내림차순 |

**UI**:
```html
<!-- 현재 deploy 옵션 바에 추가 -->
<select id="deploySortSelect" onchange="onDeploySortChange()">
  <option value="index">저장 순서</option>
  <option value="positive_cnt">긍정 문장 수</option>
  <option value="negative_cnt">부정 문장 수</option>
  <option value="neutral_cnt">중립 문장 수</option>
  <option value="profanity_cnt">욕설 건수</option>
  <option value="positive_ratio">긍정률</option>
  <option value="negative_ratio">부정률</option>
</select>
<button onclick="toggleDeploySortOrder()">▲/▼</button>
```

### 4.4 감정 문장 리스트 정렬 (셀 내부 details)

**대상**: `renderCellSection(d, type)` — type === 'emotion' 일 때 `positive_sentence_details`/`negative_sentence_details`

**현재**: 문장이 API 반환 순서 그대로 노출됨

**변경 사항**:
- `<details>` summary 옆에 **정렬 아이콘** + 토글 버튼 추가 (작은 폰트, 클릭 시 정렬 순환)
- [긍정 사유 N건 ▼] 옆에 `⇕` 버튼 → 클릭 시 confidence 내림/오름차순 토글

**정렬 키**:
| 순서 | 기준 |
|------|------|
| 1 (기본) | API 반환 순서 |
| 2 | `confidence`(=`abs(pos-neg)`) 높은 순 |
| 3 | `confidence` 낮은 순 |
| 4 | `kote_pos - kote_neg`(극성 강도) 높은 순 |
| 5 | `kote_pos - kote_neg` 낮은 순 |

> 검토: `confidence`·`kote_pos`·`kote_neg`는 응답 details에 존재 확인(`perspective_service.py:1799-1819`, `2587-2589`). `override_score`는 응답에 없어 제외.

### 4.5 워드클라우드 단어 리스트 정렬 (top_words)

**대상**: `renderCellSection(d, type)` — type === 'nlp' 일 때 `top_words` 부분

**현재**: `Object.entries(d.top_words).slice(0,5)`로 빈도수 내림차순 고정

**변경 사항**:
- `top_words` 렌더링 전 정렬 로직 추가
- 정렬 버튼을 작은 아이콘으로 UI 우측에 추가

**정렬 키**:
| 순서 | 기준 |
|------|------|
| 1 (기본) | 빈도수(`count`) 높은 순 |
| 2 | 빈도수 낮은 순 |
| 3 | 단어명 가나다순 |
| 4 | 단어명 역순 |

---

## 5. 영향도 분석

### 5.1 변경 파일 목록

| 파일 | 변경 내용 | 영향도 |
|------|-----------|--------|
| `web/templates/perspective_test.html` | 정렬 유틸리티 JS 추가, 4개 렌더링 함수 수정 (renderMatrix, renderMatrixPage, renderDeployPage, renderCellSection), 옵션 바 UI 추가 | **중간** — JS 전용 변경, 백엔드 영향 없음 |
| `src/services/perspective_service.py` | 변경 없음 (기존 데이터 구조로 충분히 정렬 가능) | **없음** |

> **검토 확정**: 백엔드 무변경 유지. 단 matrix 셀 emotion details는 `positive/negative`만 존재하고 `neutral_sentence_details`는 **deploy 경로에만** 있음(`:1829-1830` vs `:2624-2626`). 따라서 §9-Q3(중립 matrix 셀 노출)은 백엔드 변경 사안이라 **이번 범위 제외**. 중립 문장 정렬은 deploy 결과(§4.3)에서만 적용.

### 5.2 영향 범위
- `/perspective_test` 페이지 내부 JS 기능 개선 — 다른 페이지 영향 없음
- 기존 데이터 구조 변경 없음 (API 응답 동일)

---

## 6. 테스트/검증 계획

### 6.1 시나리오

| # | 시나리오 | 예상 결과 | 검증 방법 |
|---|----------|-----------|-----------|
| 1 | 매트릭스 생성 후 행 헤더 클릭 | 해당 열 기준으로 행 순서 정렬 | 눈으로 정렬 순서 확인 |
| 2 | 전체 직원 보기 → 긍정률 정렬 선택 | 직원 목록이 긍정률 높은 순으로 재배열 | 각 직원 셀 긍정값 비교 |
| 3 | 제출용 저장 → 긍정 문장 수 정렬 | 직원 리스트 긍정문장수 내림차순 정렬 | 각 직원 details summary count 비교 |
| 4 | 감정 셀 → 문장 confidence 정렬 버튼 | 문장 리스트가 confidence 높은 순으로 재배열 | 각 문장 confidence 값 비교 |
| 5 | NLP 셀 → 단어 가나다순 정렬 | top_words가 가나다순으로 표시 | 단어 순서 육안 확인 |
| 6 | 정렬 방향 토글 (▲/▼) | 같은 키로 오름차순/내림차순 전환 | 헤더 아이콘 + 순서 확인 |

### 6.2 회귀 검증
- 정렬이 **기본값(정렬 없음)**일 때 기존 화면과 동일한 순서인지 확인
- 페이징 + 정렬 조합 시 페이지번호 리셋 확인

---

## 7. 리스크 및 제약

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 정렬 시 원본 배열 변경 | 부작용으로 기존 참조에 영향 | `sortArray`에서 spread(`[...arr]`)로 복사 후 정렬 |
| 매트릭스 행/열 정렬 시 동일 값 셀 많음 | 정렬 효과 미미 | 2차 정렬 키(평가건수)로 fallback |
| 제출용 저장 결과 `profanity_summary`가 없는 레거시 결과 | 정렬 시 undefined 참조 에러 | `?.` 옵셔널 체이닝 + `|| 0` fallback |
| 큰 데이터(수백 명)에서 정렬 연산 | 브라우저 프리징 위험 | `requestAnimationFrame` 또는 `setTimeout`으로 프레임 분할 (선택적) |

---

## 8. 구현 순서

| 순서 | 작업 내용 | 의존 | 예상 시간 |
|------|-----------|------|-----------|
| 1 | 공통 정렬 유틸리티 함수 추가 (`sortArray`, `sortIcon`, 상태 변수) | 없음 | 20분 |
| 2 | 제출용 저장 결과 정렬 (renderDeployPage) — 정렬 드롭다운 + onDeploySortChange | 1 | 1시간 |
| 3 | 전체 직원 리스트 정렬 (renderMatrixPage) — 드롭다운 + 방향 토글 | 1 | 1시간 |
| 4 | 매트릭스 테이블 행/열 정렬 (renderMatrix) — 헤더 클릭 이벤트 | 1 | 1시간 |
| 5 | 감정 문장 리스트 정렬 (renderCellSection emotion details) | 1 | 30분 |
| 6 | 워드클라우드 단어 리스트 정렬 (renderCellSection nlp top_words) | 1 | 20분 |
| 7 | 정렬 상태 sessionStorage 저장/복원 (선택) | 2-6 | 30분 |
| 8 | 수동 검증 + 회귀 테스트 | 2-7 | 30분 |

**총 예상 시간**: 약 4-5시간

---

## 9. 열린 질문 (사용자 결정 필요)

1. ~~정렬 기본값~~ → **결정: 원본순(사번순/저장순) 유지**. 정렬은 사용자가 선택 시 적용(회귀 안전, §6.2 정합).
2. ~~행/열 정렬 방향~~ → **결정: 열 헤더 클릭 → 행 재정렬**(스프레드시트 관행). 계획대로 진행.
3. ~~중립 matrix 셀~~ → **결정: 이번 범위 제외**(백엔드 변경 필요, §5.1 참조). 중립 정렬은 deploy에서만.
