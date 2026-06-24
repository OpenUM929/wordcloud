# 미완료 기능 통합 마무리 계획서 (6/11 이후 계획서 정리)

> 상태: Hold(HOLD) — 3-A(정합성) 적용 완료 / 3-B·C·E 무해·미적용 보류 (2026-06-18) | 작성일: 2026-06-18
> 작업 유형: 미완료 기능 통합 마무리 (정합성 버그 수정 + 성능 + 죽은 코드 제거) + 계획서 상태 정리
> 선행/연관: `0615_09_metadata-group-fix`(PND), `0617_01_emotion-rule-mining`(코드완료), `0617_05_kote-finetune-data`(설계), `0611_01_batch-db-unification`

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-18 | 전체 | 최초 작성 — 6/11 이후 계획서 코드 대조 검증 + 잔여 작업 통합 |
| 2026-06-18 | §3 | **3-A 적용 완료** — `perspective_service._generate_wc_for_items`에서 `split_sentences(doc)` 재분할 + index 맵 제거, `_get_sentence_level_scores` 결과를 단일 출처로 직접 순회(정렬 시 출력 동일, 캐시/재분할 드리프트로 인한 긍↔부 오분류 제거). **3-B·C·E는 보류** — 코드 실측 결과 현재 동작 무해(B·C는 셀 렌더 한정 미세중복으로 1.9만 배치 O(n²)와 무관, E는 호출 0건 죽은 코드)하여 업그레이드 필수 수정 아님. 향후 셀 렌더 성능 이슈/리팩토링 시 재개. |

---

## 1. 목적

2026-06-11 이후 작성된 계획서를 **실제 코드와 대조 검증**하여, ①이미 구현되었으나 인덱스가 `PND`로 남은 항목을 `DN`으로 정리하고, ②genuinely 미완료인 항목을 한 계획서로 모아 마무리한다.

> 본 문서는 plan-mode 산출물이다. "수행" 지시 전까지 코드 변경 없음. (단, 계획서 상태/인덱스 문서 갱신은 본 요청에 포함된 산출물이므로 적용한다.)

---

## 2. 6/11 이후 계획서 검증 결과 (코드 대조)

| 계획서 | 기존 인덱스 | 검증 결과 | 조치 |
|--------|------------|-----------|------|
| `0611_01_batch-db-unification` | 🟡 PND | **완료** — `batch_manager.py`(L8 `_get_eval_conn`, L26/83/139/168 `FROM evaluations`/`employees`)·`wordcloud_data_service.py`(L19 `_get_eval_conn`, L210 `FROM evaluations`) 모두 DB 전환. `batch_processor.py`의 per-employee imeta/tmeta 쓰기(Stage 4/5) 제거됨(`save_imeta_single`/`save_tmeta_single` 부재, staging.db 경유). `batch_summary.json`만 display_name 보관용으로 의도적 잔존. | → DN |
| `0615_01_batch-csv-stream` | 🟡 PND | **완료** — 문서 자체 `DONE`. `src/services/batch_staging.py` 존재, `batch_processor.py` L541/639/665/770 staging 파이프라인 구현. | → DN |
| `0615_02_batch-display-name` | 🔴 PND | **완료** — `batch_processor._ensure_batch_summary`(L492) + 호출(L1004-1005), `perspective_routes.api_batch_update_display_name`(L837-838, PATCH), `perspective_test.html` `editDisplayName`/`metadata_batch.js` 모두 존재. | → DN |
| `0615_04_perspective-title-recall` | 🟡 PND | **완료** — `perspective_test.html`에 `toggleBatchTitlePicker`/`selectBatchTitleForRestore`/`_saveLastRunParams`/`editDisplayName` 존재. | → DN |
| `0615_09_metadata-group-fix` | 🟡 PND | **부분 완료** — 결함 D(메타 vs 그룹 불일치)는 `0617_01 §15 Step B`에서 `metadata_analysis.calculate_consolidated_analysis`(L49-50 `_get_sentence_level_scores`)로 해결됨. **결함 A·B·C·E 미구현.** | → §3 통합 (PND 유지) |
| `0617_01_emotion-rule-mining` | 🔴 PND | **코드 완료** — positive_rescue / negation_praise / no_response_neutral / 리더십 게이트 / 메타 override 전부 구현·검증. 잔여는 코드가 아닌 ①step1 정답 최종 합의(사용자 검토) ②혼합극성 규칙(코퍼스 3/475로 표본부족 → deferred). | → DN (잔여는 §4 deferred) |
| `0617_05_kote-finetune-data` | 🟡 PND | **설계 완료, 구현 승인 대기** — P0(스키마/택소노미) + P2/P5 스크립트 인프라(export_jsonl/build_splits) 선행 수행. P1(gold 컬럼 마이그레이션 + 검토 UI) 이후는 §13 사용자 결정 + 🟡 승인 대기. | → PND 유지 (로드맵, §5 결정 대기) |

> 참고(6/11 이전 잔존 PND): `0602_01_profanity-eng-fix`, `0604_01_profanity-display-fix`, `0605_01_restore-deploy-preview`, `0610_01~04`, `0421_01`. 본 요청 범위(6/11 이후) 밖이므로 본 계획서에서 다루지 않는다.

---

## 3. 통합 마무리 대상 — `0615_09` 잔여 결함 (A·B·C·E)

> 결함 D는 이미 해결(0617_01 §15). 아래 4건이 실제 미완료. 모두 **동작 보존 리팩토링 또는 죽은 코드 제거**이며, 핵심가치(긍↔부 오분류 방지)에 직접 닿는 A를 최우선으로 한다.

### 3-A. [정합성 버그·최우선] 제출용 저장 문장-점수 오정렬

- **위치**: `perspective_service.py::_generate_wc_for_items` L1923-1954.
- **현상(실측)**: L1923 `sent_scores_list = _get_sentence_level_scores(doc, ...)`로 점수를 얻고 L1929-1934에서 **캐시 순서 index**로 `sent_score_map`/`pos_map`/`neg_map`/`neutral_map`을 만든 뒤, L1935 `for i, sent in enumerate(split_sentences(doc))`로 **doc을 독립 재분할**하여 `sent_score_map.get(i)`로 매핑한다. `sent_scores_list`가 이미 튜플[0]에 문장 텍스트를 담고 있는데 이를 버리고 재분할에 의존 → 캐시 길이/순서와 `split_sentences(doc)` 결과가 어긋나면 점수가 다른 문장에 붙는다.
- **위험**: `sentence_emotion_cache`는 DB 영구 저장 → 저장 시점 doc과 조회 시점 doc, 또는 `split_sentences`(`src/modules/text_preprocessing.py`) 로직 변경 시 index 드리프트. 제출 산출물의 문장 색상·긍/부정 분류·교정 반영 오류 → **긍↔부 오분류 직결**.
- **대비**: 셀 뷰 경로(`_generate_emotion_cell`)는 튜플 `sent`를 직접 사용해 안전 → 두 경로 불일치.
- **수정**: 재분할(`split_sentences(doc)`)·index 맵 제거, `sent_scores_list`를 **단일 출처**로 직접 순회.

  ```python
  # 변경 후 (실제 시그니처: 5-튜플 sent, sent_score, pos, neg, neutral)
  all_seen = set()
  for i, (sent, sent_score, pos, neg, neutral) in enumerate(sent_scores_list):
      if not sent:
          continue
      text_key = sent[:80]
      if text_key in all_seen:
          continue
      all_seen.add(text_key)
      confidence = abs(pos - neg)
      base = {'text': sent, 'evaluation_id': eval_id, 'db_id': db_id,
              'item_index': item_idx, 'sentence_index': i, 'confidence': confidence,
              'batch_id': ev.get('batch_id', ''), 'context': doc,
              'kote_pos': round(pos, 4), 'kote_neg': round(neg, 4),
              'kote_neutral': round(neutral, 4), 'override_score': round(sent_score, 4)}
      if sent_score > 0:
          base['text_html'] = _highlight_words_in_sentence(sent, top_pos, word_scores)
          pos_details.append({**base, 'sentiment': 'positive', 'score': round(sent_score, 3)})
      elif sent_score < 0:
          base['text_html'] = _highlight_words_in_sentence(sent, top_neg, word_scores)
          neg_details.append({**base, 'sentiment': 'negative', 'score': round(sent_score, 3)})
      else:
          neutral_details.append({**base, 'sentiment': 'neutral', 'score': 0.0})
  ```
- **주의**: `sent_score_map`/`confidence_map`/`pos_map`/`neg_map`/`neutral_map` 및 `split_sentences(doc)` 루프 전부 제거. `all_seen` 중복제거·`text_key` 규칙은 그대로 유지.

### 3-B. [성능·O(n²) 위험] `calculate_word_scores` 문장 점수 중복 계산

- **위치**: `perspective_service.py::calculate_word_scores` L989-1023.
- **현상(실측)**: `for word in word_frequency: for item in filtered_evaluations: ... _get_sentence_level_scores(doc, ...)`(L1009) — 동일 문서의 문장 점수를 **(단어 W × 평가 E)회** 재계산. 캐시 재사용으로 KoTE 재추론은 없으나 `_get_sentence_level_scores` 내부의 override(정규식 `has_contrastive` 등)를 W×E회 반복.
- **영향**: 셀당 O(W×E×S). 1.9만명 배치·다수 평가 셀에서 비효율 (메모리 정책상 O(n²) 금지).
- **수정**: 단어 루프 진입 **전에 평가별 문장 점수를 1회 선계산**하여 재사용.

  ```python
  def calculate_word_scores(filtered_evaluations, word_frequency, threshold=0.20, weight=2.0, corrections_map=None):
      # 1) 평가별 (meaningful_words, sent_scores) 1회 선계산
      per_eval = []
      for item in filtered_evaluations:
          ev = item['evaluation']
          nlp = ev.get('nlp_analysis_results', {})
          meaningful = []
          if isinstance(nlp, dict):
              analysis = nlp.get('analysis', {})
              if isinstance(analysis, dict):
                  meaningful = analysis.get('meaningful_words', [])
              if not meaningful:
                  meaningful = nlp.get('meaningful_words', [])
          doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
          eval_corr = corrections_map.get(ev.get('_db_id')) if corrections_map else None
          sent_scores = _get_sentence_level_scores(doc, threshold, weight,
                                                   corrections=eval_corr,
                                                   sentence_cache=ev.get('sentence_emotion_cache'))
          per_eval.append((set(meaningful), sent_scores))
      # 2) 단어별 집계 (문장 점수 재계산 없음 — 기존 규칙 동일)
      word_scores = {}
      for word in word_frequency.keys():
          total, count = 0.0, 0
          for meaningful, sent_scores in per_eval:
              if word not in meaningful:
                  continue
              word_sent_score = None
              for sent, score, _, _, _ in sent_scores:
                  if sent and word in sent:
                      word_sent_score = score
                      break
              if word_sent_score is None and sent_scores:
                  word_sent_score = sent_scores[0][1]
              if word_sent_score is not None:
                  total += word_sent_score
                  count += 1
          word_scores[word] = round(total / count, 4) if count > 0 else 0.0
      return word_scores
  ```
- **동작 보존**: 동일 입력 → 동일 `word_scores` dict(같은 점수·같은 fallback 규칙). 복잡도 O(W×E×S)→O(E×S + W×E).

### 3-C. [중복 연산] `_generate_emotion_cell` 셀당 문장 점수 2회 계산

- **위치(원 계획 기준)**: `perspective_service.py::_generate_emotion_cell` 내 `_aggregate_emotion` 집계 1회 + 본문 루프에서 `_get_sentence_level_scores` 1회 = 평가별 2회 산출.
- **검증 필요**: 본 계획서 작성 시점 정확한 라인은 구현 단계에서 `_generate_emotion_cell`·`_aggregate_emotion` 재확인 후 확정(rule 11 — 추측 금지). 현재 `calculate_word_scores`/`_get_sentence_level_scores`가 5-튜플을 반환하므로 시그니처 정합 확인 포함.
- **수정 방향**: 셀 내에서 `_get_sentence_level_scores`를 평가별 1회만 산출하여 `_aggregate_emotion`(pos/neg 합산)과 본문 분류(score>0 / <0)가 **같은 리스트를 공유**하도록 리팩토링. 집계식·임계는 그대로 유지(숫자 보존).

### 3-E. [죽은 코드] 미사용 `calculate_word_scores(metadata, word_freq)` 제거

- **위치(실측)**: `batch_processor.py` L385 `def calculate_word_scores(metadata, word_freq):` — 문서 단위 구버전(`(pos-neg)*2.5` 류). `perspective_service.calculate_word_scores`(L989, 시그니처 다름)와 **동명이지만 별개**. 호출처 전무.
- **수정**: 제거 전 `grep "calculate_word_scores"`로 `batch_processor` 내 호출 0건 재확인 후 삭제. (`perspective_service`의 동명 함수는 실사용 — 혼동 주의, 삭제 금지.)

---

## 4. `0617_01` 잔여 — deferred (코드 아님)

이 둘은 코드 미완이 아니라 데이터/사용자 판단 대기다. 본 통합 작업의 **코드 범위에 포함하지 않는다.**

| 잔여 | 성격 | 진행 조건 |
|------|------|-----------|
| step1 예상정답 최종 합의 | 사용자 검토 작업 (`data/*_review.csv`) | 사용자가 진짜 부정 경계·neutral↔positive 경계 합의 |
| 혼합극성(긍정-부정/부정-부정) 규칙 | 코퍼스 표본 부족(3/475) → 추측 금지로 보류 | 혼합극성 코퍼스 추가 수집 후 별도 마이닝 |

> 현재 셋 다 `neutral`로 안착 → **긍↔부 오분류 없음(핵심가치 안전)**. 정답 일치율만 미흡.

---

## 5. `0617_05` 잔여 — 설계 승인/결정 대기

P1 이후(gold 컬럼 additive 마이그레이션 + `acquired_data.html` gold 확정 UI + JSONL export 게이트)는 §13 사용자 결정 후 🟡 승인 필요. 본 통합 작업과 독립적이며, 결정 6건(라벨 범위/신규 라벨 채택/어노테이터/마이그레이션 착수/src_hash 게이트 자동화/UI 접근권한)이 선행한다. **본 계획서는 이를 착수하지 않고 결정 대기 상태로 둔다.**

---

## 6. 작업 순서 (수행 승인 시)

1. **3-E**(죽은 코드 제거) — 위험 0, 선행 정리. grep 0건 재확인 후 삭제.
2. **3-A**(제출용 저장 정합성) — 단일 출처화. 핵심가치 직결, 최우선.
3. **3-B**(word_scores 1회 캐싱) — 동작 보존.
4. **3-C**(셀 2회→1회) — 라인 재확인 후 동작 보존 리팩토링.
5. 검증(§7) 후 `result/`에 보고서 저장.

> A/B/E는 독립 커밋(동작 보존), C는 라인 재확인 후 별도 커밋. 롤백 단위 분리.

---

## 7. 테스트 계획 (`test/`, `result/`)

| 항목 | 검증 |
|------|------|
| 3-A | 캐시 有/無 배치 각각 제출용 저장 → 문장 텍스트-점수 정합(점수가 해당 문장에 붙는지). split_sentences 변경에도 드리프트 없음. 긍↔부 오분류 0. |
| 3-B | 동일 cell_items 변경 전/후 `calculate_word_scores` 결과 dict 동등성 단언. |
| 3-C | 변경 전/후 `_generate_emotion_cell` 출력(avg_sentiment, positive/negative_sentence_details) 동등성 단언. |
| 3-E | `grep calculate_word_scores` — `batch_processor` 호출 0건 재확인. import/실행 정상. |
| 회귀 | `docs/verification/scenarios/` 그룹 분석·제출용 저장 시나리오 통과. `0617_01` 골든/락셋(positive_rescue·negation_praise·no_response·metadata override) 무영향 재확인. |

> dev 제약: 서버 무단 실행 금지(스크립트 검증). 원데이터·배치 불가 → 적재된 데이터/CSV·캐시로 검증.

---

## 8. 영향도 / 핵심가치

| 변경 | 직접 영향 | 회귀 위험 | 핵심가치 |
|------|-----------|-----------|----------|
| 3-A | 제출용 저장 문장 상세/색상/긍부정 | 낮음(단일 출처화) | **긍↔부 오분류 제거(개선)** |
| 3-B | 그룹 셀·제출용 word_scores | 낮음(값 동일) | 영향 없음(성능만) |
| 3-C | 그룹 감정 셀 | 낮음(숫자 보존) | 영향 없음 |
| 3-E | 없음(미사용) | 없음 | 없음 |

- 모든 변경은 **기존 rule_id·`_get_sentence_level_scores`/`_aggregate_emotion`/`sentence_sentiment_override` 시그니처 불변**. 레거시 보호 준수.

---

*승인("수행") 전까지 코드 변경 없음. 계획서/인덱스 상태 갱신만 본 요청 산출물로 적용한다.*
