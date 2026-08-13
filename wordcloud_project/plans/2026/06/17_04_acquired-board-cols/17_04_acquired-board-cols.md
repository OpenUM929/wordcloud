# 습득데이터 게시판 — 감정분석/욕설/비꼼 칸 전부 '-' 표시 수정

> 상태: Done | 완료일: 2026-06-17
> 작업 유형: 기능 문제 분석/디버깅 (프론트 표시 + 적재 데이터 계약 정합)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-17 | 최초 작성 | 게시판 표시-적재 계약 불일치 진단 및 수정 방안 수립 |
| 2026-06-17 | 3, 4-1, 4-2, 7 | 검토 피드백 반영: 감정 result 우선순위 명확화, 과거 데이터 NULL 처리 방안, 비꼼/욕설 리스크 세분화 |
| 2026-06-17 | 2, 3, 4, 5, 7, 8 | 코드 재검증 반영: 감정 라벨은 model_label 재사용으로 단순화, 비꼼 소스 부재 확정(범위 외), 백필 불필요, **표시 폴백 단독으로 전 행 복구**(페이로드 합성은 선택), 단건 캡처 경로 2곳 추가 |
| 2026-06-17 | 구현 완료 | §4-1 + §4-2 전체 적용. node 시뮬레이션 5케이스 통과 (DN) |

## 구현 결과 (2026-06-17)

- **§4-1 (필수)** `web/templates/acquired_data.html` renderTable:
  - 감정칸: `analysis_results.emotion` 없으면 `item.model_label`(라벨) + `item.kote_*`(점수, NULL이면 라벨만) 폴백. 색상 클래스는 기존 `result-pos/neg/neu` 규칙에 맞춰 `emoLabel.substr(0,3)` 적용.
  - 욕설칸: `profanity.detected` **또는** `is_profanity` 둘 다 인식.
- **§4-2 (전방 일관성)** `web/templates/perspective_test.html` 4개 경로에 표준 `analysis_results` 합성:
  - 감정 벌크 `_collectDeployDetailItems`(`:1838~`), 감정 단건 saveToCorpus(`:1754~`): `{emotion:{result, positive, negative, neutral}}`.
  - 욕설 벌크 bulkMoveProfanity(`:1890~`), 욕설 단건 saveProfanityToCorpus(`:1784~`): `{profanity:{detected:true,...}, is_profanity:true,...}`(구·신형 키 양립).
- **백엔드/DB 무변경.**
- 검증: node로 renderTable 폴백 로직 5케이스 통과 — 버그 행(`negative`) `[neg]negative<0.10/0.80/0.10>` 표기, 기존 욕설행 ⚠️, 신규 표준형, CSV 임포트(kote NULL→라벨만), 신규 욕설 표준형 모두 정상.

---

## 1. 문제 현상 (REQ: 260617.txt ②)

- NNav 메뉴 "습득데이터" 게시판에서 **감정분석 / 욕설 / 비꼼** 칸이 모든 행에서 `-`로 표시됨.
- 사용자: "해당 칸에 KoTE 감정 분석 결과와 욕설이면 욕설 등 추가 정보가 들어가야 하는데 모두 '-'은 상식적으로 말이 안 됨."
- 보고된 행: `업무에 열성적입니다 / 사용자=negative / 모델=negative / 일치 ✅ / 감정분석 - / 욕설 - / 비꼼 - / 삭제` → 집단분석에서 일괄 이동된 `group_emotion` 행.

---

## 2. 근본 원인 분석 (코드 확인 완료)

### 2-1. 게시판은 `analysis_results` JSON만 읽는다

`web/templates/acquired_data.html:140~152` — `renderTable()`:
- 감정분석: `analysisResults.emotion.result` (+ `positive/negative/neutral`) 없으면 `-`.
- 욕설: `analysisResults.profanity.detected` 없으면 `-`.
- 비꼼: `analysisResults.sarcasm.detected` 없으면 `-`.

즉 게시판이 기대하는 계약 형태:
```json
{ "emotion": {"result": "positive", "positive": 0.0, "negative": 0.0, "neutral": 0.0},
  "profanity": {"detected": true},
  "sarcasm": {"detected": false} }
```

### 2-2. 적재 측 4개 경로 모두 그 계약을 안 지킴

감정/욕설을 습득데이터로 넣는 경로는 **벌크 2 + 단건 2 = 4곳**이며, 전부 계약을 어긴다:

| 경로 | 위치 | source_kind | 증상 원인 |
|------|------|-------------|-----------|
| 감정 벌크 이동 | `perspective_test.html:1824~1838` (`_collectDeployDetailItems`) | `group_emotion` | `kote_*`만 보내고 `analysis_results` 미전송 → `'{}'` 저장 → 감정/욕설/비꼼 `-` |
| 욕설 벌크 이동 | `perspective_test.html:1881~1890` (`bulkMoveProfanity`) | `group_profanity` | `analysis_results={is_profanity:true,...}` → 게시판은 `profanity.detected`를 봄 → 욕설칸 `-` |
| 감정 단건 캡처(📋) | `perspective_test.html:1745~1754` (saveToCorpus) | `group_emotion` | 위 감정 벌크와 동일(`analysis_results` 미전송) |
| 욕설 단건 캡처 | `perspective_test.html:1786~1793` (saveProfanityToCorpus) | `group_profanity` | `analysis_results={is_profanity:true,...}` → 키 불일치 |

> 백엔드 저장(`save_acquired_sentence` `perspective_service.py:2067~`, `save_acquired_sentences_bulk` `:2539~`)은 받은 `analysis_results`를 그대로 저장할 뿐, 형태 변환을 하지 않는다(빈 값이면 `'{}'`). → 책임은 프론트 페이로드 + 게시판 표시 계약.

### 2-3. 데이터는 이미 있는데 화면이 안 씀 + 라벨은 이미 분류돼 있음

- `list_acquired_sentences`(`perspective_service.py:2136~2146`)는 `SELECT *` → `item.kote_pos/kote_neg/kote_neutral`, `item.override_score`, `item.user_label/model_label`이 **이미 프론트까지 전달**됨. 그런데 `renderTable`은 `analysis_results`만 보고 컬럼을 무시한다.
- **감정 라벨은 이미 권위 있게 분류되어 저장돼 있다**: 문장 상세 생성부(`perspective_service.py:1258~1293`, `:1947~1954`)에서 `sentiment`(positive/negative/neutral) = `override_score`(= `_get_sentence_level_scores`의 **보정 반영** 점수) 부호로 결정되고, 그 값이 그대로 `model_label`로 저장된다(`perspective_test.html:1827`). → 게시판은 **재계산 없이 `model_label`을 그대로 재사용**하면 된다.

> 결론: 감정 `-`는 "데이터(model_label+kote_*)는 있는데 화면이 안 읽음", 욕설 `-`는 "적재 형태(is_profanity) ↔ 표시 계약(profanity.detected) 불일치", 비꼼 `-`는 "적재 소스 자체가 없음".

---

## 3. 영향도 분석

**핵심: 표시 폴백(§4-1) 단독이면 게시판 1파일만 수정** → 기존/신규 전 행 복구. 페이로드 합성(§4-2)은 전방 일관성용 선택.

| 영역 | 파일 | 변경 성격 | 필수 여부 |
|------|------|-----------|-----------|
| 게시판 표시 | `web/templates/acquired_data.html` (`:133~165`) | 렌더 폴백(model_label·kote_*·is_profanity) | **필수** |
| 감정 벌크 적재 | `perspective_test.html:1824~1838` | `analysis_results` 합성 | 선택(전방 일관성) |
| 욕설 벌크 적재 | `perspective_test.html:1881~1890` | `profanity.detected` 형태 추가 | 선택 |
| 감정 단건 적재 | `perspective_test.html:1745~1754` | `analysis_results` 합성 | 선택 |
| 욕설 단건 적재 | `perspective_test.html:1786~1793` | `profanity.detected` 형태 추가 | 선택 |
| 백엔드 저장 | `perspective_service.py:2067~`, `:2539~2617` | **변경 없음** | - |
| DB 스키마/마이그레이션 | - | **변경 없음**(백필 불요, §7-3) | - |

- 페이로드를 손대기로 하면 **벌크 2곳만이 아니라 단건 2곳까지 4곳 모두** 동일하게 고쳐야 일관됨(과거 계획 누락분).

---

## 4. 수정 방안

### 4-1. (핵심·필수) 게시판 표시 폴백 — `acquired_data.html` renderTable

`analysis_results`만 의존하지 말고, 행 컬럼으로 폴백한다. **이 한 파일 수정만으로 기존에 저장된 행이 즉시 복구**된다.

- **감정칸**:
  - result: `analysis_results.emotion.result` → 없으면 **`item.model_label` 재사용**(이미 분류된 권위 라벨, §2-3). `model_label`은 항상 존재하므로 CSV 임포트 행까지 커버.
  - 점수: `analysis_results.emotion.{positive,negative,neutral}` → 없으면 `item.kote_pos/kote_neg/kote_neutral`(있을 때만 표기, NULL이면 점수 생략하고 라벨만).
  - ⚠️ **argmax·override_score 재해석 금지**: 라벨은 이미 확정돼 있으므로 재유도하지 않는다. 재유도하면 중립↔부정 경계에서 기존 분류와 어긋날 수 있음(메모리: 긍정↔부정 오분류 방지).
- **욕설칸**: `analysis_results.profanity.detected` **또는** `analysis_results.is_profanity` 둘 다 인식 → 기존 욕설 행(`is_profanity` 형태) 즉시 복구.
- **비꼼칸**: `analysis_results.sarcasm.detected` 없으면 기존대로 `-`(소스 부재, §7-2).

### 4-2. (선택·전방 일관성) 적재 페이로드 표준화 — `perspective_test.html` 4곳

표시 폴백만으로 복구되므로 **필수는 아니나**, 이후 저장 행을 계약대로 채우려면 4곳 모두 일관 적용:

- 감정 경로(`_collectDeployDetailItems` `:1824~1838`, saveToCorpus `:1745~1754`): item에
  ```js
  analysis_results: { emotion: { result: (s.sentiment || truth),   // = model_label
                                 positive: s.kote_pos, negative: s.kote_neg, neutral: s.kote_neutral } }
  ```
  (단건은 `userLabel`/`modelLabel`·`kotePos` 등 해당 변수로 매핑)
- 욕설 경로(`bulkMoveProfanity` `:1881~1890`, saveProfanityToCorpus `:1786~1793`):
  ```js
  analysis_results: { profanity: { detected: true, words: s.detected_words || [] },
                      is_profanity: true, detected_words: s.detected_words || [] }
  ```
  (구형/신형 키 양립; 게시판은 `words` 미표시이므로 생략해도 무방 — §7-4)

> 권장 순서: **§4-1 먼저 적용(전 행 즉시 복구) → 검증 → 여유 시 §4-2로 신규 행 계약 정합.**

---

## 5. 작업 순서

1. `acquired_data.html` renderTable: 감정(model_label·kote_* 폴백)·욕설(is_profanity 인식) 폴백 추가. (표시 전용, DB 무변경)
2. 검증: 기존 습득데이터 행에서 감정칸(라벨+점수)·욕설칸이 표기되는지 확인. 비꼼은 `-` 유지 정상.
3. (선택) `perspective_test.html` 4개 경로 `analysis_results` 표준 합성 → 신규 이동 행 검증.
4. 결과를 `result/`에 기록.

## 6. 롤백 계획

- 표시 폴백/페이로드 합성 제거 시 종전 동작 복귀. DB 스키마·백엔드 저장 로직 무변경이라 데이터 영향 없음.

## 7. 확인 필요 / 리스크 — 코드 재검증으로 해소됨

### 7-1. 감정 result 도출 규칙 — ✅ 해소(단순화)

`override_score`는 `_get_sentence_level_scores`의 보정 반영 점수이며, 그 부호로 `sentiment`가 정해지고 그대로 `model_label`로 저장된다(`perspective_service.py:1258~1293`/`1947~1954`, `perspective_test.html:1827`). → 게시판은 **`model_label`을 그대로 재사용**. argmax/override_score 재해석 불요 → 중립↔부정 경계 불일치 위험 소멸.

### 7-2. 비꼼(sarcasm) — ✅ 해소(범위 외 확정)

문장 상세(`positive/negative/neutral_sentence_details`)에 `sarcasm` 필드가 **존재하지 않음**(emotion + 별도 `profanity_summary`만, `:1944~1954`, `:1984`). 벌크·단건 어느 경로도 비꼼을 싣지 않는다. → 현재 데이터로는 비꼼칸을 채울 수 없음. **본 수정 범위 외**, 문장 단위 sarcasm 적재는 별도 작업으로 분리.

### 7-3. 과거 데이터 `kote_*` NULL — ✅ 해소(백필 불요)

감정·욕설의 벌크/단건 경로는 모두 `kote_*`를 채운다(상세 객체에 항상 포함). NULL 가능성은 CSV 임포트 행 정도. 그러나 §4-1 감정 폴백을 **`model_label` 기준**으로 두면(항상 존재) CSV 임포트 행까지 라벨이 표기된다(점수만 생략). → **DB 백필 마이그레이션 불필요**.

### 7-4. 욕설 `words` 필드 — 비차단

게시판은 `detected`만 표시. `words`는 페이로드에 둬도 표시 무관. 범위 최소화 시 생략 가능.

### 7-5. `user_label`/`model_label` 출처 — ✅ 확인

`list_acquired_sentences`의 `SELECT *`로 DB 컬럼에서 직접 전달(`item.user_label`/`item.model_label`). `kote_*`와 독립 컬럼이며, 감정 폴백에서 `model_label`을 result로 재사용해도 사용자/모델 칸 표시(별도 `<td>`)와 중복 충돌 없음.

---

## 8. 검토자 질문 — 코드 재검증으로 답변 완료

| # | 질문 | 결론 |
|---|------|------|
| Q1 | 감정 result 산출(override_score 성격)? | **model_label 재사용**으로 단순화. override_score는 보정 점수이고 그 부호가 곧 model_label → 재유도 불요(§7-1) |
| Q2 | 비꼼 이번 범위 포함? | **미포함**. 상세에 sarcasm 소스 없음 → 별도 작업(§7-2) |
| Q3 | 과거 kote_* NULL 추가 폴백/백필? | **백필 불요**. 감정 폴백을 model_label 기준으로 → CSV 임포트 행까지 커버(§7-3) |
| Q4 | 욕설 words 포함? | 비차단. 생략 가능, 확장 위해 포함 무방(§7-4) |

> 구현 착수 가능 상태. 남은 결정은 "§4-1만(권장) vs §4-1+§4-2" 범위 선택뿐.
