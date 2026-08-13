# 메타데이터 생성·그룹 분석 결함 수정 계획서

> 상태: Done(2026-06-18) — 결함 D·A 해결, B·C·E는 무해로 [[0618_01_pending-wrapup]]에서 보류 | 작성일: 2026-06-15
> 작업 유형: 기능 문제 분석/디버깅 + 성능 개선 + 감정 산출 정합성

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 전체 | 최초 작성 (A~E 전부, D 포함 범위 확정) |
| 2026-06-18 | 진행상태 | **코드 대조 검증**: 결함 D(메타 vs 그룹 불일치)는 `0617_01 §15 Step B`에서 `metadata_analysis.calculate_consolidated_analysis`가 `_get_sentence_level_scores`(override 질량 기반) 공유로 전환되어 **해결됨**. 잔여 A·B·C·E는 통합 마무리 계획 `0618_01_pending-wrapup §3`으로 이관. 본 계획은 잔여 4건이 남아 PND 유지. |
| 2026-06-18 | 진행상태 | **종결(DN)**: 결함 A(제출용 저장 문장-점수 정합)를 `0618_01 §3-A`로 적용 완료(재분할 제거·단일 출처화). 잔여 B·C·E는 코드 실측상 현재 동작 무해(셀 렌더 한정 미세중복/죽은 코드)하여 `0618_01`에서 **보류(HOLD)** 관리. 핵심가치(긍↔부 오분류 방지) 직결 항목 모두 해소되어 본 계획 종결. |

---

## 1. 배경 및 분석 범위

메타데이터 생성 → DB 저장 → 그룹/관점 분석 → 제출용 저장 전 경로를 추적하여 결함을 식별했다.
추적한 핵심 경로(실제 코드 확인 완료):

- 생성: `src/models/metadata_manager.py::MetadataManager.create_employee_metadata` (문장 단위 KoTE 캐시 생성: L77-79)
- 통합 분석: `src/modules/metadata_analysis.py::calculate_consolidated_analysis` (문서 단위 가중평균)
- DB 저장: `src/services/batch_processor.py` L736 `upsert(...)` → `src/services/user_data_manager.py::upsert` (evaluation JSON에 `sentence_emotion_cache` 포함 저장)
- 그룹 로드: `src/services/perspective_service.py::load_all_batches` (DB `evaluations.data`에서 캐시 복원)
- 문장 점수: `perspective_service.py::_get_sentence_level_scores` (캐시 재사용/없으면 fallback)
- 셀 생성: `perspective_service.py::_aggregate_emotion`, `_generate_emotion_cell`, `calculate_word_scores`
- 제출용 저장: `perspective_service.py::save_to_deploy._generate_wc_for_items`

---

## 2. 결함 목록

### 결함 A — [정합성 버그] 제출용 저장의 문장-점수 오정렬
- 위치: `perspective_service.py` L1750-1773 (`save_to_deploy._generate_wc_for_items`)
- 현상:
  - `sent_scores_list = _get_sentence_level_scores(doc, ..., sentence_cache=ev.get('sentence_emotion_cache'))` → 점수/신뢰도는 **캐시 순서** index로 산출(`sent_score_map[idx]`, `confidence_map[idx]`).
  - 직후 `for i, sent in enumerate(split_sentences(doc))` → 문장 텍스트는 **현재 doc 재분할**로 따로 만들고 `sent_score_map.get(i)`를 index로 매핑.
  - `_get_sentence_level_scores`가 튜플[0]으로 이미 문장을 반환하는데 이를 버리고(`for idx, (_, sc, pos, neg)`) 독립 재분할에 의존 → 캐시 길이/순서와 재분할 결과가 어긋나면 점수가 다른 문장에 붙음.
- 위험: `sentence_emotion_cache`는 DB에 영구 저장되므로 저장 당시 doc과 조회 시점 doc 차이, 또는 `split_sentences`(`src/modules/text_preprocessing.py`) 로직 변경 시 인덱스 드리프트 발생 → 제출용 산출물의 문장 색상·긍/부정 분류·교정 반영 오류.
- 대비: 셀 뷰 `_generate_emotion_cell`(L1093)은 튜플의 `sent`를 직접 사용해 안전 → 두 경로가 불일치.

### 결함 B — [성능, O(n²) 위험] `calculate_word_scores` 문장 점수 중복 계산
- 위치: `perspective_service.py` L824-858
- 현상: `for word in word_frequency: for item in filtered_evaluations: sent_scores = _get_sentence_level_scores(doc, ...)` — 동일 문서의 문장 점수를 **(단어 W × 평가 E)회** 재계산. 캐시 재사용으로 KoTE 재추론은 없으나 `sentence_sentiment_override`(정규식 `has_contrastive` 등)를 W×E회 반복.
- 영향: 셀당 복잡도 O(W×E×S). 1.9만명 배치·다수 평가 셀에서 비효율. (메모리: 배치 규모 1.9만 — O(n²) 금지)

### 결함 C — [중복 연산] `_generate_emotion_cell` 셀당 문장 점수 2회 계산
- 위치: `perspective_service.py` L1059-1092
- 현상: 본문에서 `_aggregate_emotion(...)`(L1060) 호출 시 한 번, 이어 본문 루프(L1092)에서 다시 `_get_sentence_level_scores`. 동일 cell_items에 대해 문장 점수 2회 산출.

### 결함 D — [산출 방식 불일치] 메타 overall_sentiment vs 그룹 avg_sentiment
- 위치: `metadata_analysis.py::calculate_consolidated_analysis`(문서 단위 가중평균, 반전 규칙·교정 미적용) vs `perspective_service.py::_aggregate_emotion`(문장 단위 override+교정).
- 현상: 메타 목록 뷰(`metadata_service.py::get_batch_metadata` L218-229)는 문서 단위 `overall_sentiment`를 표시, 그룹/관점 분석은 문장 단위 결과를 표시 → 같은 직원이 두 화면에서 다른 감정(예: 메타=긍정, 그룹=부정)으로 보일 수 있음.
- 핵심가치 위반 소지: 긍정↔부정 오분류 방지 규칙이 메타 목록 뷰에는 적용되지 않음.

### 결함 E — [경미] 죽은 코드
- 위치: `batch_processor.py` L266 `calculate_word_scores(metadata, word_freq)` (문서 단위 `(pos-neg)*2.5` 구버전). 호출처 없음(검색 결과 정의만 존재) → 혼동 유발.

---

## 3. 수정 방안

### A. 제출용 저장 인덱스 정합성 (필수, 동작 보존)
`_generate_wc_for_items`의 문장 루프를 **재분할 제거 후 `sent_scores_list`를 직접 순회**하도록 변경.

```python
# 변경 전: split_sentences(doc)로 재분할 후 index 매핑
# 변경 후: _get_sentence_level_scores 결과를 단일 출처로 사용
for i, (sent, sent_score, pos, neg) in enumerate(sent_scores_list):
    if not sent:
        continue
    confidence = abs(pos - neg)
    ...  # 기존 text_key 중복제거 / pos·neg·neutral 분류 로직 그대로
```
- `sent_score_map` / `confidence_map` / 별도 `split_sentences(doc)` 루프 제거.
- 캐시에 `sentence` 누락 시에도 `_get_sentence_level_scores` 내부에서 이미 derived로 보강하므로 동일 결과.

### B. `calculate_word_scores` 평가별 1회 캐싱
단어 루프 진입 전, **평가별 문장 점수 + 단어→점수 매핑을 1회 선계산**.

```python
def calculate_word_scores(filtered_evaluations, word_frequency, threshold=0.20, weight=2.0, corrections_map=None):
    # 1) 평가별 문장 점수 1회 계산
    per_eval_sent_scores = []
    for item in filtered_evaluations:
        ev = item['evaluation']
        doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
        eval_corrections = corrections_map.get(ev.get('_db_id')) if corrections_map else None
        sent_scores = _get_sentence_level_scores(doc, threshold, weight,
                                                 corrections=eval_corrections,
                                                 sentence_cache=ev.get('sentence_emotion_cache'))
        per_eval_sent_scores.append((ev, sent_scores))
    # 2) 단어별 집계 (문장 점수 재계산 없음)
    word_scores = {}
    for word in word_frequency.keys():
        total, count = 0.0, 0
        for ev, sent_scores in per_eval_sent_scores:
            ... # meaningful_words 판정 후 word가 속한 문장 점수 사용 (기존 규칙 유지)
        word_scores[word] = round(total / count, 4) if count > 0 else 0.0
    return word_scores
```
- 결과값은 기존과 동일(같은 점수·같은 fallback 규칙), 복잡도만 O(W×E×S)→O(E×S + W×E).

### C. `_generate_emotion_cell` 단일 계산 공유
- `_get_sentence_level_scores` 결과를 셀 내에서 1회만 산출하여 `_aggregate_emotion` 집계와 본문 분류가 공유하도록 리팩토링.
- 방식: `_aggregate_emotion`을 "이미 계산된 sent_scores 리스트"를 받는 내부 헬퍼로 분리하거나, `_generate_emotion_cell`에서 평가별 sent_scores를 1회 계산 후 pos/neg 합산과 문장 상세 수집을 동시에 수행.
- 동작/숫자 보존: 집계식(`pos_sum += max(0, score)` 등)과 분류 임계(`score>0 / <0`)는 그대로 유지.

### D. 메타 overall_sentiment를 문장 단위 기준으로 통일
- `metadata_analysis.py`에 문장 단위 감정 집계를 도입하여 `overall_sentiment`/`confidence_score`를 그룹 분석과 동일 기준(문장 단위 override 적용)으로 산출.
- 공유 로직 재사용: `sentence_emotion_cache` + `sentence_sentiment_override`(현재 `perspective_service`에 정의)를 **공용 모듈로 추출**하여 메타 생성과 그룹 분석이 같은 함수를 호출하도록 단일화(중복 구현 방지).
  - 후보 위치: `src/modules/sentence_emotion.py`에 override 적용 집계 헬퍼 추가(경량 의존 유지) → `metadata_analysis.py`와 `perspective_service.py`가 공유.
- 주의: 사용자 교정(`sentiment_corrections`)은 그룹 분석 시점 DB값 기준이므로, 메타 생성 시점에는 **교정 미반영 원시 문장 점수 기준**으로 산출(생성 시점엔 교정 데이터 부재). 교정 반영 표시는 그룹/관점 분석 뷰에서 유지.
- 영향도: `metadata_service.py::get_batch_metadata`가 노출하는 `overall_sentiment`/`confidence_score` 값이 변동 → 메타 목록 뷰 표시값 변경(의도된 정합화).

### E. 죽은 코드 제거
- `batch_processor.py` L266 `calculate_word_scores` 제거(호출처 전무 확인). 제거 전 재검색으로 0건 재확인 후 삭제.

---

## 4. 영향도 분석

| 변경 | 직접 영향 | 회귀 위험 | 검증 포인트 |
|------|-----------|-----------|-------------|
| A | 제출용 저장 산출물(문장 상세/색상/긍부정) | 낮음(단일 출처화) | 캐시 有/無 배치 모두 동일 문장-점수 매핑 |
| B | 그룹 분석 셀·제출용 word_scores | 낮음(값 동일) | 동일 입력 시 word_scores 값 불변 |
| C | 그룹 분석 감정 셀 | 낮음 | avg_sentiment·문장 상세 수치 불변 |
| D | 메타 목록 overall_sentiment/confidence | **중간** | 메타 뷰와 그룹 뷰 감정 일치, 긍↔부 오분류 0건 |
| E | 없음(미사용 함수) | 없음 | grep 0건 재확인 |

- 공통 모듈 추출(D) 시 `00-core` 공통 모듈 수정 절차에 따라 사용처 전수 검색 후 상대경로 검증.
- 롤백: 각 항목 독립 커밋(A/B/C/E는 동작 보존, D는 별도 커밋)으로 분리하여 D만 단독 롤백 가능하게 구성.

---

## 5. 작업 순서

1. E(죽은 코드 제거) — 위험 0, 선행 정리.
2. A(제출용 저장 정합성) — 단일 출처화.
3. B, C(중복 계산 제거) — 동작 보존 리팩토링.
4. D(감정 산출 통일) — 공용 모듈 추출 + 메타 생성/그룹 분석 단일화. (별도 커밋)
5. 검증: §6 테스트 수행 후 `result/`에 보고서 저장.

---

## 6. 테스트 계획 (`test/`, `result/`)

- A: 캐시 有 배치와 캐시 無(과거) 배치 각각 제출용 저장 → 문장별 score가 해당 문장과 일치하는지(텍스트-점수 정합) 검증.
- B: 동일 cell_items에 대해 변경 전/후 `calculate_word_scores` 결과 dict 동등성 단언.
- C: 변경 전/후 `_generate_emotion_cell` 출력(avg_sentiment, positive/negative_sentence_details) 동등성 단언.
- D: 샘플 직원에 대해 메타 `overall_sentiment` == 그룹 분석 감정 방향(긍/부/중) 일치, 긍↔부 정반대 0건 확인.
- 회귀: 기존 그룹 분석/제출용 저장 시나리오(`docs/verification/scenarios/`) 통과.

---

## 7. 미해결 질문 / 결정 필요

- D의 메타 `confidence_score` 정의: 문장 단위 통일 시 신뢰도를 (a) 평균 |pos-neg| (b) 최종 감정 방향 문장 비율 중 무엇으로 정의할지 — 구현 단계에서 확정 필요(기본 제안: 그룹 `_aggregate_emotion` 산출 강도와 정합되는 (a)).

---

*승인("수행") 전까지 코드 변경 없음. 본 계획서는 저장만 수행됨.*
