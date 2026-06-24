# 집단 분석 결과 → 습득 데이터 일괄 이동 (감정 버킷 + 욕설, KoTE 분류값 동반)

> 상태: Done | 작성일: 2026-06-17 | 완료일: 2026-06-17
> 작업 유형: 기능 추가(백엔드 API + 화면) + DB 스키마 additive 마이그레이션
> 연관: `0617_01_emotion-rule-mining`(규칙 마이닝의 **입력 데이터 확보** 경로) — 본 계획이 코퍼스 적재를 자동화한다.

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-17 | 전체 | 최초 작성 (집단분석 버킷·욕설 일괄 이동 + 분류 시점 KoTE 값 동반 적재) |
| 2026-06-17 | §1,§3-3,§4-D,§4-F,§8 | 출처를 DOM→`_deployResults`(배포 실행 전량)로 정정. 화면 페이징 무관 전량 이동(사용자 확정 §8-2) |
| 2026-06-17 | §8, §4-B, §4-D | 계획서 검토 반영: §8-1/3/4 결정 확정(권고 채택) |
| 2026-06-17 | §2, §4-D, §4-F, §9 | 확정 결정 본문 정합화: 잔존 DOM 표현→`_deployResults`, §4-D 단건 동기화 '선택'→'적용', §9 작업순서 확정 반영 |
| 2026-06-17 | 전체 | **수행 완료(DN)**: v7 마이그레이션·5튜플·detail KoTE·bulk 서비스/라우트·프런트 버튼·단건 동기화 구현. 테스트 2종 통과. result/완료보고 참조 |

---

## 1. 배경 / 목적

사용자 요구(대화 기준):

1. **(배포 전량 일괄 이동)** **제출용 배포(save_to_deploy) 한 번의 실행으로 생성된 모든 문장**(직원 1명~전체직원 루프 결과 전부)을, 화면 페이징과 **무관하게 전량** `습득한 데이터(acquired_sentences)`로 옮긴다. 각 문장을 단건(📋)으로 옮기는 대신 **버킷 단위 버튼**("긍정 전체 이동", "부정 전체 이동", "중립 전체 이동", "욕설 전체 이동", "전체 이동")으로 한 번에 적재. 받은 **장점 데이터**가 부정/중립으로 오분류되는 사례, **단점 데이터**의 유사 현상을 코퍼스로 모아 규칙·알고리즘 강화(0617_01)의 입력으로 쓴다.
   - **출처(사용자 확정)**: 프런트가 배포 시 받아 보유 중인 전체 결과(`_deployResults`)에서 끌어온다. DOM(현재 페이지)이 아님 → 페이징으로 안 보이는 문장도 포함. 서버 재집계·KoTE 재실행 없음.
2. **(욕설 포함)** "욕설이 아닌데 욕설로 잡힌" 사례가 많아, **욕설 감지 문장도 함께** 습득 데이터로 이동한다.
3. **(KoTE 값 동반)** 문장 분류 시점에 이미 계산된 **KoTE 결과값(pos/neg/neutral·보정점수)** 을 함께 가져가, 적재 후 KoTE를 **다시 돌리지 않고도** 분석 데이터가 완성되게 한다.

> 정답 라벨 기준(사용자 확인): 화면에 분류가 **이미 표시**되므로, 정답(user_label)은 그 **분류값(버킷)을 그대로** 가져간다. 별도 정답 지정 단계는 두지 않는다(필요 시 적재 후 습득 데이터 화면에서 수정).

---

## 2. 환경 제약 (재확인)

- dev: 원데이터·배치 실행 불가, KoTE는 로드됨. 본 기능은 **배포 실행으로 이미 받아둔 결과(`_deployResults`)** 의 값만 사용 → 추가 KoTE 실행 없음(DOM/현재 페이지 아님, §3-3).
- 서버 무단 실행 금지(검증은 사용자 승인 후).
- 핵심 가치: 긍↔부 오분류 방지. 본 기능은 **분류값을 보존 이동**할 뿐 분류를 바꾸지 않으므로 가치와 무충돌.

---

## 3. 현재 코드 확인 (실측)

### 3-1. 집단 분석 문장 상세 생성 (백엔드)
`src/services/perspective_service.py`:
- **그룹 분석 경로**(L1109~1138): `_get_sentence_level_scores(...)` → `(sent, score, pos, neg)` 반복. `positive_details`/`negative_details` 항목에 담는 필드: `text, evaluation_id, db_id, sentence_index, sentiment, confidence(=|pos-neg|), batch_id, context`. **score·pos·neg는 계산되나 detail에 미포함**(neutral 미반환).
- **배포/제출용 경로**(L1767~1790): 동일 헬퍼 → `pos_details/neg_details/neutral_details`. base 필드: `text, evaluation_id, db_id, item_index, sentence_index, confidence, batch_id, context`. positive/negative에 `score`(round 3)·`text_html` 추가. **neutral은 score=0.0 고정, pos/neg 미포함**.
- 반환 키: `positive_sentence_details / negative_sentence_details / neutral_sentence_details` (L1145/1817).

### 3-2. 점수 헬퍼 `_get_sentence_level_scores` (L782)
- 반환: `(sent, score, pos, neg)` **4-튜플**. 내부에서 `neutral`을 캐시/계산으로 보유하나 **반환에 미포함**.
- `score` = `sentence_sentiment_override(pos,neg,sent,is_last,total,...)` 결과(부호 있는 보정점수) + 사용자 교정 반영.
- 캐시(`sentence_emotion_cache`): `[{sentence,pos,neg,neutral}, ...]` — **3-class 원점수만**. **44개 감정 top 라벨은 없음.**
- 호출부(언팩) 4곳: L863~864, L1040, L1110, L1770.

### 3-3. 프런트 렌더·단건 저장 (`web/templates/perspective_test.html`)
- 감정 문장 행 `.sentence-row`(L1818): data-`db-id/eval-id/sent-idx/orig-sentiment/full-text/confidence/batch-id/context`. 라디오는 `sentiment`로 기본 선택. `saveToCorpus(btn)`(L1722) → user_label=체크 라디오, model_label=orig-sentiment, `/api/perspective/acquired-sentences/save`로 **단건** POST. **현재 점수(pos/neg/neutral)는 미전송.**
- 욕설 문장 행 `.profanity-sentence-row`(L1949): data-`full-text/eval-id/profanity-context(JSON: detected_words/detection_details)`. 라디오 **기본 미선택**. `saveProfanityToCorpus(btn)`(L1763) → `model_label:'profanity'`, user_label=체크 라디오(미선택 시 저장 거부) 단건 POST.
- **⭐ 전량 저장소 `_deployResults`(L1969, `renderDeployComplete`에서 `summary.success`로 설정 L1983)**: 배포 실행으로 받은 **모든 직원 결과 객체 배열**을 보유. 각 객체에 `positive_sentence_details / negative_sentence_details / neutral_sentence_details`(전량, 잘림 없음) + `profanity_summary.profanity_sentences`. 렌더(`renderDeployPage` L2061)는 `slice`로 **페이징만** → DOM엔 한 페이지뿐이지만 `_deployResults`엔 전량. **일괄 이동은 이 배열에서 끌어온다(DOM 아님).**
  - 결과 객체 두 형태: ① 단일/제출용 = **top-level** `*_sentence_details`(`save_to_deploy` L1817). ② 매트릭스 = `res.row_results[rowKey].*_sentence_details`(`_buildEmployeeResultHtml` L1858~1869). 일괄 이동은 두 형태 모두 순회해야 함.

### 3-4. 저장 경로 (`acquired_sentences`)
- `save_acquired_sentence(data)`(perspective_service.py L1903): `INSERT OR REPLACE` 단건. 컬럼=`sentence_text,user_label,model_label,confidence,source_employee_id,source_evaluation_id,source_batch_id,sentence_index,db_id,context`.
- 라우트 `POST /acquired-sentences/save`(perspective_routes.py L1214, 관리자 전용).
- **일괄 저장 함수/라우트는 없음 — 신규 필요.**

### 3-5. 스키마 실측 (`.sessions/deploy_sessions.db`, 현 0행) — ⚠ 두 가지 제약
`deploy_session_service.py` L191~ (schema v5):
```
user_label   TEXT CHECK(user_label  IN ('positive','negative','neutral')),
model_label  TEXT CHECK(model_label IN ('positive','negative','neutral')),
... analysis_results TEXT DEFAULT '{}', ...
UNIQUE(sentence_text, source_evaluation_id, sentence_index)
```
- **(제약 A) 욕설 차단**: 실DB CHECK 확인 결과 `model_label`은 3종만 허용 → 욕설 단건 저장이 보내는 `model_label='profanity'`는 **IntegrityError로 실패**(현재 욕설 저장은 사실상 동작 안 함, 0행이 방증). → 본 계획에서 욕설 이동 시 **CHECK를 위반하지 않는 저장 방식**이 필요.
- **(제약 B) KoTE 값 저장 컬럼 없음**: pos/neg/neutral·보정점수를 담을 컬럼 부재.
- 마이그레이션 최신 = **v6**(profanity 테이블). 신규는 **v7**.

---

## 4. 설계

### 4-A. DB 스키마 v7 — additive ADD COLUMN (DDL)
`deploy_session_service.py`에 `if current < 7:` 블록 추가. **CHECK 재빌드 없음**(SQLite는 CHECK 변경에 테이블 재생성 필요 → 회귀 위험 회피). 대신 **컬럼 추가만**:
```sql
ALTER TABLE acquired_sentences ADD COLUMN kote_pos       REAL;
ALTER TABLE acquired_sentences ADD COLUMN kote_neg       REAL;
ALTER TABLE acquired_sentences ADD COLUMN kote_neutral   REAL;
ALTER TABLE acquired_sentences ADD COLUMN override_score REAL;
ALTER TABLE acquired_sentences ADD COLUMN source_kind    TEXT DEFAULT '';
```
- 전부 nullable/default → 기존 행·기존 `save_acquired_sentence`·import 경로 무영향(미지정 시 NULL/'').
- `source_kind`: `'group_emotion'` | `'group_profanity'` 구분용.

### 4-B. 욕설 저장 방식 (제약 A 우회, 핵심 결정)
**CHECK를 건드리지 않는다.** 욕설 행도 `model_label`은 **3종 중 하나로** 저장하고, "욕설"이라는 사실은 별도로 표시:
- `model_label` = 라디오 체크값(있으면) **else `'neutral'`**(유효값).
- `source_kind = 'group_profanity'`.
- 탐지어 등 메타 = 기존 `analysis_results`(JSON)에 `{"is_profanity":true,"detected_words":[...],"detection_details":[...]}` 적재.
- user_label = 라디오 체크값 else `'neutral'`.
- → 습득 데이터 화면에서 `source_kind='group_profanity'`로 필터/표시, 정답은 화면에서 보정.

> 대안(비채택): model_label CHECK에 'profanity' 추가. SQLite 특성상 **테이블 재생성** 필요 → 레거시 회귀 위험이 커서 보류. 정말 'profanity' 라벨이 필요해지면 별도 DDL 계획서로 분리.

### 4-C. 백엔드 — 분류 시점 KoTE 값 detail에 노출 (additive)
요구 #3 충족의 핵심. 현재 버려지는 pos/neg/neutral·보정점수를 detail dict에 실어 응답에 포함.

1. **`_get_sentence_level_scores` 반환을 5-튜플로 확장**: `(sent, score, pos, neg)` → `(sent, score, pos, neg, neutral)`. (neutral은 이미 내부 보유 — append만, **기존 값 불변**)
   - 언팩부 4곳 동기 수정(값 의미 불변, 추가 원소만 수용): L863~864, L1040, L1110, L1770.
   - 회귀 보호: 각 호출부의 기존 계산 결과는 동일해야 함(테스트로 단언).
2. **detail dict 보강**(L1117/1129 그룹경로, L1785/1790 배포경로): 각 항목에
   `kote_pos=round(pos,4), kote_neg=round(neg,4), kote_neutral=round(neutral,4), override_score=round(score,4)` 추가.
   - 기존 필드·키 **불변**(순수 additive). 프런트 기존 코드에 영향 없음.

> ⚠ 한계(정직): 캐시·헬퍼는 **3-class(pos/neg/neutral)만** 보유. 44개 감정 **top 라벨(kote_top_emotion)** 은 분류 시점에 없으므로 이번 이동으로는 **가져올 수 없다**. 0617_01 §4-1의 매핑 정당성(요구 #2-①, 감정별 분포)은 여전히 재계산이 필요. 단, **0617_01 §4-2의 (B)원시 혼동행렬·(D)마진 분포**는 본 이동의 pos/neg/neutral로 **재실행 없이** 산출 가능.

### 4-D. 프런트 — 단건 저장 payload 동기화 (**확정 §8-4: 적용**)
- 일괄 이동은 `_deployResults` JS 객체에서 직접 KoTE 필드를 읽으므로 **data-attr 추가는 불필요**(4-F).
- **단건 저장도 KoTE 필드 동반(확정)**: `_renderDeploymentSentences`(L1799)에 `data-kote-pos/neg/neutral`, `data-ovr-score` 추가 → `saveToCorpus`/`saveProfanityToCorpus` payload에 신규 필드 포함. 일괄과 동일 스키마로 적재(단건도 KoTE 값 보존).

### 4-E. 백엔드 — 일괄 저장 서비스/라우트 (신규)
1. `save_acquired_sentences_bulk(items, overwrite=False)` (perspective_service.py, `save_acquired_sentence` 인접 신규):
   - 단일 커넥션(`_get_acq_conn`) 배치. `verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"`.
   - 컬럼: 기존 10 + `kote_pos,kote_neg,kote_neutral,override_score,source_kind,analysis_results`.
   - 각 item: `sentence_text` 필수, label 정규화(`_normalize_acq_label`, 0617_01에서 신규 추가됨), 누락치 기본값.
   - `cur.rowcount`로 inserted/skipped 집계. 반환 `{'inserted','skipped','errors'}`. (0617_01 `import_acquired_sentences_csv`와 동일 패턴 — O(n) 단일 트랜잭션, 19k 규모 안전)
2. 라우트 `POST /api/perspective/acquired-sentences/save-bulk`(관리자 전용, JSON `{items:[...], overwrite?}`). import 블록에 함수 추가.

### 4-F. 프런트 — 일괄 이동 UI (perspective_test.html, additive) — **`_deployResults` 기반(DOM 아님)**
- 배포 완료 요약바(`renderDeployComplete` L1990~)에 툴바 추가: **[긍정 전체 이동] [부정 전체 이동] [중립 전체 이동] [욕설 전체 이동] [전체 이동]**. `_deployResults.length>0`일 때만 노출.
- **수집 헬퍼** `_collectDeployDetails(sentiment)`: `_deployResults` 전체를 순회하며
  - 각 결과 `res`에서 top-level `res[sentiment+'_sentence_details']` **그리고** `res.row_results`가 있으면 각 row의 동일 키까지 평탄화(두 형태 모두 §3-3).
  - `sentiment='all'` → positive+negative+neutral 합집합.
  - 각 detail dict → item 매핑: `sentence_text=text, user_label=sentiment, model_label=sentiment, source_kind='group_emotion', confidence, source_evaluation_id=evaluation_id, source_batch_id=batch_id, sentence_index, db_id, context, kote_pos/kote_neg/kote_neutral, override_score`. (source_employee_id=res.employee_id)
- `bulkMoveToCorpus(sentiment)`: 위 수집 → `confirm(N건 이동?)` → `POST /save-bulk` 한 번. 결과 `inserted/skipped` 토스트 + `/acquired-data` 링크.
- `bulkMoveProfanity()`: `_deployResults[*].profanity_summary.profanity_sentences` 평탄화 → item: `sentence_text=original_text, model_label/user_label='neutral'(확정 §8-1), source_kind='group_profanity', source_evaluation_id=evaluator_id, analysis_results={is_profanity:true,detected_words,detection_details}` → POST.
- 범위 = **배포 실행 전체**(직원/행/페이지 무관). 페이로드가 클 수 있어 필요 시 클라이언트 청크(예 1,000건/요청) — 단, 코퍼스 용도는 수십~수백 규모. O(n) 평탄화.

---

## 5. 정답 라벨/필드 매핑 규칙 (요약)

| 이동 대상 | user_label | model_label | source_kind | kote_* / override_score |
|-----------|-----------|-------------|-------------|--------------------------|
| 감정 버킷(긍/부/중) | 행 라디오값(기본=버킷) | 행 orig-sentiment(=버킷) | `group_emotion` | 분류 시점 값 동반 |
| 욕설 | 라디오값 else `neutral` | 라디오값 else `neutral` | `group_profanity` | 있으면 동반(없으면 NULL), 탐지어→analysis_results |

UNIQUE 키 = `(sentence_text, source_evaluation_id, sentence_index)`. 욕설 행은 sentence_index=0 → 같은 평가의 여러 욕설 문장은 text로 구분. 동일 문장이 감정·욕설 양쪽에 있으면 index 차이로 별도 행(허용).

---

## 6. 영향도 / 레거시 보호

- **순수 additive**: 신규 컬럼(nullable)·신규 함수·신규 라우트·신규 버튼. 기존 `save_acquired_sentence`·import·단건 저장·기존 7 rule_id·집단분석 산출 **동작 불변**.
- 유일한 시그니처 변경 = `_get_sentence_level_scores` 5-튜플(append). 호출부 4곳 동기 수정 + **값 동일성 테스트**로 회귀 차단.
- DDL은 ADD COLUMN만(테이블 재생성·CHECK 변경 없음) → 기존 데이터/제약 보존.
- 0617_01과의 관계: 본 이동이 코퍼스 적재를 자동화 → §4-2 (B)/(D) 측정이 **재계산 없이** 가능. (C)/kote_top_emotion만 0617_01 §4-1 재계산 유지.

---

## 7. 테스트 (test/)

DB·KoTE 최소 의존(임시 sqlite). 
- `test_bulk_save.py`: ① 임시 DB에 v7 컬럼 ADD 후 `save_acquired_sentences_bulk` inserted/skipped/overwrite, ② 욕설 항목(source_kind/analysis_results) 적재, ③ label 정규화, ④ 중복 UNIQUE skip.
- `test_scores_tuple.py`: `_get_sentence_level_scores` 5-튜플화 후 **기존 (sent,score,pos,neg) 값 불변** + neutral 추가 동작(캐시/ fallback 경로 각각).
- 결과 보고서 → `result/`.

---

## 8. 확정 결정 사항

1. **욕설 model_label 기본값** → **확정**: `'neutral'` 적재 + `source_kind='group_profanity'` 플래그. 라디오 미선택 시 `'neutral'` 기본값. source_kind로 추후 화면 필터·보정. (권고 채택)
2. ~~"전체 이동" 범위~~ → **확정(사용자)**: `_deployResults` 전량(배포 실행 전체, 페이징 무관). DOM 스캔/블록 단위 안 함.
3. **스키마** → **확정**: ADD COLUMN 방식 채택. CHECK에 `'profanity'` 추가는 SQLite 테이블 재생성 필요 → 회귀 위험으로 보류. (권고 채택)
4. **단건 저장 동기화** → **확정**: 기존 `saveToCorpus`/`saveProfanityToCorpus`도 KoTE 필드 동반 보강. 스키마 일관성 유지. (권고 채택)

---

## 9. 작업 순서 (승인 후 "수행" 시)

1. 스키마 v7 ADD COLUMN (4-A) + 마이그레이션 검증.
2. `_get_sentence_level_scores` 5-튜플 + 호출부 4곳 (4-C-1) + 회귀 테스트.
3. detail dict KoTE 필드 보강 (4-C-2).
4. `save_acquired_sentences_bulk` + 라우트 (4-E) + 단위 테스트.
5. 프런트 일괄 이동 버튼/함수(4-F, `_deployResults` 기반) — 긍/부/중/욕/전체.
6. 단건 저장 KoTE 필드 동기화(4-D, **확정 §8-4** — 단건 행 data-attr 추가 + payload 확장).
7. `py_compile` + test/ 통과. 서버는 사용자 승인 후 기동.

---

## 10. 진행 원칙

- 추측 금지: 본 계획의 모든 함수/경로/스키마는 실측(grep·read·실DB PRAGMA) 확인됨.
- 데이터 미보유분(44 top 감정)은 "가져올 수 없음"으로 명시(4-C 한계).
- 서버 무단 실행 금지. 레거시 보호 최우선.

> 계획서 저장 위치: `D:\dev\wordcloud\wordcloud_project\plans\2026\0617_02_group-bulk-move\0617_02_group-bulk-move.md`
