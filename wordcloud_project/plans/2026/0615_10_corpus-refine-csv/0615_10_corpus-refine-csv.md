# 취득 코퍼스 정제 후 CSV 내보내기 (규칙 마이닝용)

> 상태: Done | 작성일: 2026-06-15 | 완료일: 2026-06-15
> 작업 유형: 기능 추가 (취득 문장 코퍼스 정제 파이프라인 + 규칙 마이닝 데이터셋 생성)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 전체 | 최초 작성 (정제 후 CSV 방식 채택) |
| 2026-06-15 | 구현 | 전 항목 구현 + 테스트 통과(test/test_refine.py 3건), 상태 DN |
| 2026-06-15 | 코퍼스 삭제 | 선택 삭제(delete-bulk)·필터 전체 삭제(delete-all) 기능 추가. 백엔드 함수+라우트+버튼, 삭제 동작 검증 완료 |

## 환경 제약 (반영)

- 다면평가 원데이터는 내부 전용. dev에는 CSV만 반입 가능, **배치 실행 불가**.
- 따라서 정제 패스는 배치/원데이터에 의존하지 않고 **코퍼스 행(sentence_text+context+user_label)+KoTE만으로 동작**하도록 구현됨.
- 운영 흐름: 내부 환경(코퍼스 DB+KoTE 보유)에서 "정제 CSV" 생성 → dev로 반입 → 규칙 마이닝.

---

## 1. 배경 / 목적

KoTE 단독으로는 인사평가 문장의 긍/부정 판정이 부정확하여, 사용자가 그룹 분석(`perspective_test`)에서 워드클라우드 생성 후 문장을 코퍼스(`acquired_sentences`)로 취득하고 있다.
이 코퍼스를 **CSV로 내보내기 직전에 "정제 패스"를 실행**하여, 규칙 마이닝에 필요한 분석 메타를 재현·부착한 데이터셋을 만든다.

핵심 통찰: 캡처 시점에 **되돌릴 수 없는 입력**(`sentence_text`, `context`(평가 문서 전체), `user_label`(사람 정답))이 이미 저장되므로, 나머지 분석 메타(KoTE 원시 점수, 보정 전/후 라벨, 발동 규칙, 문장 위치)는 **사후 재계산 가능**하다. 따라서 캡처 흐름·DB 스키마는 변경하지 않고, 내보내기 단계에만 정제 로직을 추가한다.

선례: `analyze_acquired_sentences`(`perspective_service.py:1964`)가 이미 취득 문장에 `analyze_emotion`을 재실행해 `analysis_results`에 저장한다 — 정제 패스는 이 패턴의 확장이다.

---

## 2. 현재 코드 확인 (실측)

- 취득 저장: `perspective_service.py::save_acquired_sentence` (L1886) — 저장 필드: sentence_text, user_label, model_label(보정 후 표시 감정), confidence(=abs(pos-neg)), source_*, sentence_index, db_id, context
- 기존 CSV: `perspective_service.py::export_acquired_sentences_csv` (L2034) — 11컬럼
- 기존 CSV 라우트: `perspective_routes.py::api_acquired_sentences_export` (L1268)
- 보정 규칙: `perspective_service.py::sentence_sentiment_override` (L327) — float 점수만 반환, **발동 규칙 id는 미반환**
- 프론트 내보내기 버튼: `web/templates/acquired_data.html::exportCsv` (L231), 버튼 마크업 L67
- 문장 분할: `src/modules/text_preprocessing.py::split_sentences`

---

## 3. 구현 방안 (전부 additive, 레거시 동작 보존)

### 3-1. 발동 규칙 id 노출 (동작 보존 리팩토링)
- 신규 `_sentence_sentiment_override_explain(pos, neg, sentence, is_last, total_sentences, threshold, weight, neutral)` → `(score, rule_id)` 반환. 규칙 분기는 기존과 **완전히 동일**, 각 분기에 식별자 부여:
  - `neutral_dominant`, `neutral_keyword`, `euphemistic_negative`, `rule1_contrast_lastlow`, `rule2_contrast_lasthigh`, `rule3_last_low`, `rule4_default`
- 기존 `sentence_sentiment_override`는 **시그니처 유지**하되 내부에서 explain을 호출해 `score`만 반환 → 모든 기존 호출처(L804 등) 영향 없음. 숫자 결과 불변.

### 3-2. 정제 함수 `refine_acquired_row(row)` (신규)
입력: acquired_sentences 한 행(dict). 출력: 분석 메타 dict.
1. `context`를 `split_sentences`로 분할 → `sentence_text`와 **텍스트 매칭**(정확일치→부분일치 순)으로 위치 확정 → `is_last`, `total_sentences` (인덱스 드리프트 방지; 매칭 실패 시 저장된 `sentence_index` fallback, total=1, is_last=True)
2. `analyze_emotion(sentence_text)` 재실행 → `kote_pos/kote_neg/kote_neutral`, `raw_model_label`(3값 최대)
3. `_sentence_sentiment_override_explain(...)` → `applied_rule`, `corrected_label`(score 부호)
4. 비교 플래그: `kote_vs_truth`, `pipeline_vs_truth`, `rule_helped`(원시 오답→보정 정답), `rule_hurt`(원시 정답→보정 오답) — `truth`=`user_label`

### 3-3. 정제 CSV `export_acquired_sentences_refined_csv(mismatch_only)` (신규)
컬럼:
```
id, sentence_text, user_label,
kote_pos, kote_neg, kote_neutral, raw_model_label,
applied_rule, corrected_label,
kote_vs_truth, pipeline_vs_truth, rule_helped, rule_hurt,
is_last, total_sentences,
model_label_at_capture, confidence_at_capture,
source_employee_id, source_evaluation_id, source_batch_id, sentence_index,
context, created_at
```
- BOM(utf-8-sig)로 Excel 한글 깨짐 방지.

### 3-4. 라우트 (신규)
- `GET /api/perspective/acquired-sentences/export-refined?mismatch_only=0|1` → 정제 CSV 다운로드. 기존 export 라우트는 그대로 유지.

### 3-5. 프론트 (acquired_data.html, additive)
- 기존 "CSV보내기" 버튼 옆에 **"정제 CSV"** 버튼 추가 + `exportRefinedCsv()` 함수(기존 `exportCsv` 복제 아님, 신규 URL 호출).

---

## 4. 영향도 / 회귀

| 변경 | 영향 | 회귀 위험 | 검증 |
|------|------|-----------|------|
| 3-1 override 분리 | `sentence_sentiment_override` 호출 전부 | **낮음**(점수 불변) | 기존 함수 반환값 동일성 |
| 3-2~3-4 신규 함수/라우트 | 신규 경로만 | 없음(additive) | 정제 CSV 생성·컬럼 확인 |
| 3-5 버튼 추가 | acquired_data.html | 없음 | 버튼 클릭→다운로드 |

- DB 스키마·취득 캡처 흐름 **무변경** → 기존 수집 데이터 호환.
- 롤백: 신규 함수/라우트/버튼 제거 + override는 explain 위임만 되돌리면 원복.

---

## 5. 테스트 계획

- 3-1 동작 보존: 대표 입력 세트에 대해 `sentence_sentiment_override`(기존) == `_sentence_sentiment_override_explain`[0] 동일성 단언.
- 정제: 샘플 행(또는 `TEST_SENTENCES_100` 기반 가상 행)으로 `refine_acquired_row` 출력 필드 존재·타입·플래그 정합 확인.
- 빈 코퍼스(현재 0건)에서도 헤더만 있는 정제 CSV 정상 생성.

---

## 6. 마이닝 활용 (후속)

정제 CSV가 쌓이면: `rule_hurt=True` 행 → 역효과 규칙 식별, `kote_vs_truth=wrong & applied_rule=rule4_default` 행 → 미처리 오류(신규 규칙 후보), `raw_model_label`별 어절/어미/구문 빈도 → 규칙 후보 제안. (별도 계획서로 진행)

---

*본 계획은 사용자 "수정까지 진행" 지시로 구현과 함께 수행됨.*
