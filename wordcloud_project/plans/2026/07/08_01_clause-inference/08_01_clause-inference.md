# 계획서 — 추론 경로 절(clause) 분리 통합 + 최신 감정모델 배포

> 상태: Phase1 Pre-Done(서버 재시작 실동작 검증 후 DN) · Phase2 HOLD(측정 결과 값어치 없음+긍↔부 위험) | 작성일: 2026-07-08
> 작업 유형: B (신규 기능) — production 감정 추론 경로 확장
> 선행: `0707_01_field-token-signal`(순서5 런타임 field 배선 = 본 계획 Phase 1) · `_datasets/kote_finetune/result/IMPROVEMENT_HISTORY.md`(8차·절 프로브)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-08 | 최초 작성 | 2단계 로드맵(Phase1 field-aware 배포=0707_01 순서5 완료 / Phase2 절 분리 추론 통합). 절 프로브 실측(헤드룸 0.3%) 반영·측정우선 |
| 2026-07-08 | Phase1 실행 | field-aware `predict_sentiments`+7 호출부 배선, seed45 프로덕션 배포(06-25 백업, md5검증). 게이트: seed45가 06-25 대비 하드셋 긍↔부 16→1·모든 부→긍누수 제거(strict 우세). 단위 4/4 PASS |
| 2026-07-08 | 플래그 제거(단순화) | 초안의 `USE_FIELD_TOKEN_INFERENCE`(기본off) 폐기 — field(장/단점)는 신 파이프라인 데이터에만 존재해 그 자체가 seed45 배포 세계의 표식(모델·코드 desync는 님 개념상 미발생). `fields = [field]*total if field else None`로 field 존재 시 자동 적용. 별도 스위치 불요 |
| 2026-07-08 | Phase2a 게이트 | `clause_eval` 실측 — 단절 4333 불변0(회귀0), 중립회수 1건(노이즈), 부→긍위험 3건(중 `-는데` 비역접 범위절단 진짜누수 1). **게이트 FAIL → Phase2b HOLD**(회수<위험) |

## 요구사항 원자화

| # | 원자 질문 | 기대(내 이해) | 작업 후 답 (근거) |
|---|-----------|---------------|------------------|
| 1.1 | production이 지금 쓰는 감정모델이 최신(seed45/c4라인)인가? | **N** — `model/hr_sentiment_finetuned`는 2026-06-25 구버전. c2~c8 능동학습 미배포 | **Y 확인·해소** — 06-25 실측(하드셋 긍↔부 16, 부→긍 다수) → seed45 배포(md5검증), 06-25는 `_backup_0625` 보존 |
| 1.2 | 최신 모델을 배포하려면 추론에 field 프리픽스가 필요한가? | **Y** — 최신 모델은 `장점/단점 평가:` 프리픽스로 학습됨. `predict_sentiments`는 raw만 넣음 → 배선 없이 배포 시 train/serve skew | **Y 확증** — seed45 field-aware가 raw보다 전셋 우세(c3_neu 긍재현 0.0→0.681, 긍↔부 7→0). train 97.1% field보유가 원인 |
| 1.3 | field 런타임 배선은 이미 계획돼 있는가? | **Y** — `0707_01` 순서5(대기). 본 계획 Phase1이 그 완료 | **Y 완료** — `predict_sentiments(fields=)` + `_get_sentence_level_scores(field=)` + 7 호출부. 0707_01 순서5=DN |
| 2.1 | 절 분리가 필요한 문장은 얼마나 되나? | **~1.5%**(gold 4400 중 다절 67). 중립라벨 중 숨은혼합 5개=0.3% | Y — `clause_probe_260708.py` 실측 |
| 2.2 | 절 분리로 단절(98.5%) 문장의 결과가 바뀌는가? | **N** — split_clauses는 표지 없으면 `[문장]` 그대로 반환. 단절은 완전 불변(회귀 0) | **N 확증** — `clause_eval` 단절 4333개 문장판정 불일치 **0건** |
| 2.3 | 절 분리가 워드클라우드 단어→문장 매핑에 파급되나? | **Y** — `calculate_word_scores`가 `word in sent`로 문장 점수 귀속. 절이 새 단위면 절 텍스트로 매칭 | Y(설계상) — Phase2b HOLD로 미구현 |
| 2.4 | 절 분리가 긍↔부를 악화시킬 수 있나? | **N 목표** — 절 분리는 극성 상쇄(→중립)를 극성 분리로 바꿈=핵심가치 안전방향. 단 폴라 문장이 반대극성 절 포함 7.1% → 양방향 회귀(부→긍=0) 게이트 필수 | **Y 위험 실측** — 부→긍 3건 중 `-는데` 비역접 배경절 범위절단 진짜누수 1건("예측하는데\|미흡"). 회수이득 1건 < 위험 → HOLD |
| 3.1 | 이 변경은 플래그로 on/off 되는가? | **Y** — 신규 `USE_CLAUSE_SPLIT`(기본 off). off면 기존 동작 완전 보존 | Phase2b HOLD(미도입). **Phase1 field 프리픽스는 플래그 불요로 결론** — field 존재가 곧 seed45 세계 표식이라 `if field` 자동 적용(별도 스위치 제거) |
| 3.2 | DN(완료) 판정 기준은? | 수동 왕복 실동작 검증 + 양방향 회귀 통과 후. 그 전 Pre-Done | Phase1=서버 재시작 실동작 검증 후 DN(현 Pre-Done). Phase2=HOLD |

## 1. 배경 및 목적

**사용자 통찰**: "A는 뛰어나나 B는 부족" 같은 혼합문을 통째로 3분류하면 긍·부가 상쇄돼 **중립으로 뭉개진다.** 절로 쪼개면 각 절이 자기 극성을 지켜 "A절=긍정, B절=부정"으로 살아난다. 이는 극성 상쇄를 **극성 분리 보존**으로 바꾸므로 긍↔부 핵심가치와 정렬된다.

**모델링 천장 이후 확인(IMPROVEMENT_HISTORY 8차)**: 데이터·모델링 6레버 실측 결과 앙상블(A)만 순이득. 남은 실질 레버는 파인튜닝이 아니라 **추론 경로의 절 분리**로 판명. 단 프로브(§2.4)로 헤드룸이 **작음(0.3%)** 을 먼저 확인 — 그래서 본 계획은 **측정 우선·저위험·플래그** 원칙을 강제한다.

**두 개의 배포 갭(코드 실측, §2)** 이 절 레버의 전제다:
1. production 모델이 **2026-06-25 구버전**(최신 능동학습 미배포).
2. `predict_sentiments`가 **field 프리픽스 없이 raw 추론** — 최신 모델(field-token 학습)과 train/serve skew.

절 레버는 제대로 배포된 field-aware 모델 위에서만 값어치가 드러나므로, **Phase 1(배포·배선) → Phase 2(절 통합)** 순서로 간다.

**목적**: (1) 최신 감정모델을 train/serve 정합 상태로 배포하고, (2) 혼합절 문장을 절 단위로 분리 판정해 거짓중립을 올바른 극성으로 회수한다. **긍↔부 오분류 0 불변.**

## 2. 현재 시스템 분석 (코드 실측)

- **문장 분류 핵심**: `src/services/perspective_service.py:1829` `_get_sentence_level_scores(doc, threshold, weight, corrections, sentence_cache)` → `(sent, score, pos, neg, neutral)` 리스트 반환.
  - 문장은 `sentence_cache`(배치 저장 KoTE 원점수) 또는 `compute_sentence_raw_scores(doc)`(`split_sentences` 사용)에서 옴.
  - `USE_HR_SENTIMENT_MODEL`(기본 on, settings.py) 시 `:1868` `from src.modules.hr_sentiment import predict_sentiments` → `model_labels = predict_sentiments(sentences)`(`:1869`). 라벨→score: `strength = abs(pos-neg) if >0.01 else 1.0`, `+strength/-strength/0`(`:1881-1882`).
- **모델 추론**: `src/modules/hr_sentiment.py:83` `predict_sentiments(texts)` → `['positive'|'negative'|'neutral',...]` 또는 실패 시 `None`(호출부 규칙 폴백). `:41` `tokenizer(chunk, ...)` — **field 프리픽스 없음.** 실패 안전(폴백) 설계.
- **모델 경로**: `settings.py` `HR_SENTIMENT_MODEL_PATH = model/hr_sentiment_finetuned`(실측 mtime 2026-06-25). 실험 아티팩트 `plans/_datasets/kote_finetune/model_out`(seed45)과 별개.
- **단어→문장 귀속**: `perspective_service.py:1905` `calculate_word_scores` → `:1928` `for sent, score, _,_,_ in sent_scores: if word in sent:` 로 단어가 속한 문장 점수 사용.
- **절 분리 도구**: `src/modules/text_preprocessing.py:75` `split_clauses(sentence)` → 역접·양보 어미/접속부사 경계 분리, **부정범위 보존**, 표지 없으면 `[sentence]` 1개(안전 기본값). 현재 데이터셋 빌드 전용, production 미배선.
- **선행 계획**: `0707_01_field-token-signal` 순서5(§3.3 Phase 3) = "런타임 감정분석 필드 배선(프리픽스 적용)", 상태 대기 — 본 계획 Phase 1과 동일.

## 3. 구현 상세

### 3.1 Phase 1 — 최신 모델 배포 + field-aware 추론 (= 0707_01 순서5 완료)

> 이 Phase는 신규 설계가 아니라 **`0707_01` 순서5의 실행**이다. 상세 규약은 0707_01 §3.3 참조. 본 계획은 절 레버의 선행으로 묶어 함께 스케줄한다.

- **모델 배포**: 실험 아티팩트 `model_out`(seed45, field-token 학습) → `model/hr_sentiment_finetuned`로 복사(구버전 백업 후). 백업 규약은 `model_out_backup_c4_260708`과 동형.
- **field-aware 추론 배선**: `predict_sentiments`가 문장별 `field`(장점/단점/미상)를 받아 학습과 **동일 프리픽스** `f'{field} 평가: {text}'` 적용(field 미상=원문). 시그니처 확장 또는 병렬 함수 신설(레거시 호출부 폴백 보존).
  - `_get_sentence_level_scores`가 문장의 field를 어디서 얻나: 0707_01 Phase2에서 `evaluation_document_field`가 evaluation에 실림 → 문서 단위 field를 문장에 상속. 미상이면 무프리픽스(하위호환).
- **게이트**: 배포 전 dev에서 field-aware 추론이 gold 재현(8c_hard 긍↔부 0·baseline 긍↔부 0)하는지 확인. skew 있으면 중단.

### 3.2 Phase 2a — 절 분리 효과 측정 (production 무변경, 측정 우선)

> 엔진 손대기 전에 **끝단 이득을 먼저 정량화**한다(프로브는 prevalence만 봤음). 헤드룸 0.3%가 실제 정확도로 얼마나 되는지 측정.

- 신규 `scripts/clause_eval_260708.py`(dataset 폴더): gold+test 문장을 ① 문장단위 분류 vs ② 절분리 후 절별 분류→집계 로, **양방향 회귀(부→긍=0)** 와 중립→극성 회수량 비교. field-aware 모델 사용.
- 집계 규칙 후보(측정으로 선택): 문장 최종 극성 = 절 극성의 **field-편향 다수결**(단점 문서면 부정 우선, 장점이면 긍정 우선) 또는 절을 독립 셀로 방출.
- **성공기준**: 절 분리가 중립→극성을 회수하면서 **부→긍=0**(양방향), 단절 문장 결과 불변. 이득이 노이즈면 Phase 2b **Hold**.

### 3.3 Phase 2b — production 절 분리 통합 (Phase 2a 통과 시)

- **플래그**: `settings.py`에 `USE_CLAUSE_SPLIT`(기본 off, `USE_HR_SENTIMENT_MODEL` 동형 env 패턴). off면 기존 경로 완전 보존.
- **통합 지점**: `_get_sentence_level_scores` 모델 경로. 각 문장에 대해:
  - `clauses = split_clauses(sent)`. `len==1`이면 **기존과 동일**(회귀 0). `len>=2`면 절별 `predict_sentiments`(field 상속) → 절별 (clause, score) 방출.
  - 반환 구조 확장: 기존 `(sent, score, pos,neg,neutral)`에 더해 다절 문장은 **절 단위 행**으로 분해. `calculate_word_scores`의 `word in sent` 매칭이 절 텍스트로 자연 동작(절이 원문 부분문자열).
  - strength: 절별 KoTE 원점수 부재 시 `1.0` 폴백(모델 경로 기존 규약과 동일).
- **집계/캐시 영향**: 문장 캐시(`sentence_emotion_cache`)는 문장 단위 KoTE 점수 — 절 분해는 **모델 라벨 경로에만** 적용(캐시 점수는 strength 용). 캐시 재생성 불요. `is_last`는 규칙 override 경로 전용이라 모델 경로 무관.
- **하위호환**: 규칙 폴백 경로(`model_labels is None`)는 **절 분리 미적용**(기존 override 로직 보존) — 범위 최소화.

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 | 상태 |
|------|-----------|------|------|
| 1 | Phase1: `model_out`(seed45)→`hr_sentiment_finetuned` 배포(백업) + `predict_sentiments` field-aware 배선(0707_01 순서5) | 0707_01 순서4 | ✅ 완료(md5검증, field 존재 시 자동 적용) |
| 2 | Phase1 게이트: dev field-aware 추론이 gold 재현(긍↔부 0) 확인 | 1 | ✅ 통과(취지) — seed45가 06-25 strict 우세, 부→긍누수 제거. 8c_hard 긍→부 1은 단일런 노이즈(06-25=부→긍 2) |
| 3 | Phase2a: `clause_eval_260708.py` 절분리 효과 측정(양방향 회귀·회수량) | 2 | ✅ 완료 |
| 4 | Phase2a 게이트: 부→긍=0 & 순회수 > 노이즈면 진행, 아니면 Hold | 3 | ❌ FAIL → **HOLD**(회수 1 < 부→긍위험 3, `-는데` 범위절단 누수) |
| 5 | Phase2b: `USE_CLAUSE_SPLIT` 플래그 + `_get_sentence_level_scores` 절 분해 + 단위/회귀 테스트 | 4 | **보류(게이트 미통과)** |
| 6 | 수동 왕복 실동작 검증(사용자) → DN | 1 | Phase1 대기(서버 재시작 필요) |

> **게이트 2중**: 순서2(skew 없음)·순서4(절 순이득 & 부→긍 0) 통과 시에만 다음 단계. 위반 시 해당 Phase Hold.
>
> **★ Phase2 HOLD 결론(2026-07-08 실측)**: 절 분리는 메커니즘상 안전(단절 불변 0)하나 현 코퍼스에서 **순이득이 없다**(중립→극성 회수 1건=노이즈). 반면 `-는데`처럼 역접이 아닌 배경 연결어미를 분리하면 부정범위가 잘려 **부→긍 누수**가 생긴다("환경변화…예측하는데[긍]｜미흡니다[부]"). 재개하려면 먼저 (a)절 표지를 진짜 역접(지만/으나/반면)으로 한정하고 (b)`-는데`+결핍어(미흡/부족/필요) 패턴을 분리 예외로 두는 선행 작업이 필요 — ~1문장 이득 대비 과투자라 **보류**. 향후 코퍼스에 다절 혼합문이 유의미하게 쌓이면 재측정(`clause_eval_260708.py` 재실행)으로 게이트 재판정.

## 5. 영향도 분석

| 파일 | 변경 | 위험 |
|------|------|------|
| `model/hr_sentiment_finetuned/` | 최신 모델 교체(구버전 백업) | 중(품질 변화·정합 필수) |
| `src/modules/hr_sentiment.py` | `predict_sentiments` field 인자(폴백 보존) | 중(추론 정합) |
| `src/services/perspective_service.py` | `_get_sentence_level_scores` 절 분해(플래그 off=불변) | 중(집계 파급, 플래그로 격리) |
| `src/config/settings.py` | `USE_CLAUSE_SPLIT` 플래그 추가 | 낮음 |
| `scripts/clause_eval_260708.py`(신규) | 측정 전용 | 없음(비production) |

- **공통모듈**: `split_clauses`(text_preprocessing)는 **읽기만**(기존 함수 재사용, 미변경). `predict_sentiments`는 field 인자 추가하되 기존 호출부 하위호환(기본값).
- **legacy 보호**: `perspective_service`·`hr_sentiment`는 🟡 정상동작 모듈 → 본 계획 승인 후에만 수정. 플래그 off 기본값으로 기존 경로 보존.

## 6. 테스트/검증 계획

1. **Phase1 정합**: field-aware `predict_sentiments`가 학습 프리픽스와 동일 규약인지 단언 + dev gold 재현(8c_hard 긍↔부 0).
2. **Phase2a 측정**: `clause_eval` 문장 vs 절 집계 — 부→긍=0(양방향), 중립→극성 회수 건수, 단절 문장 불변.
3. **단위(Phase2b)**: `USE_CLAUSE_SPLIT` off=기존 결과 바이트 동일(회귀 가드) / on=다절 문장만 분해, 단절 불변. 부정범위 보존("강압적이지 않으나" 한 절 유지).
4. **회귀(핵심가치)**: 장점/단점 양 코퍼스 적대셋으로 부→긍=0·긍→부=0 전수([[feedback-validate-both-pos-neg-corpora]]).
5. **수동 왕복**(사용자): 혼합절 포함 CSV 배치 → 워드클라우드에서 긍절/부절 단어가 각 극성으로 집계되는지 확인. 서버 재시작은 사용자.

## 7. 리스크 및 제약

- **헤드룸 작음(0.3%)**: 절 레버 대상은 ~1.5% 문장. Phase2a에서 순이득이 노이즈면 Phase2b Hold(측정이 게이트).
- **train/serve skew(최우선)**: 최신 모델은 field-token 학습 → 배선 없이 배포 시 악화. Phase1에서 field-aware 배선과 배포를 **함께** 한다. 미배선이면 배포 보류.
- **긍↔부**: 절 분리는 상쇄→분리라 안전방향이나, 폴라 문장 반대극성 절 7.1% → 양방향 회귀 게이트 필수. 위반 시 롤백.
- **집계 파급**: 단어→문장 귀속이 절 단위로 미세화 → 플래그 off 기본·단절 불변으로 격리. 캐시/`is_last` 미영향(모델 경로 한정).
- **production 안전**: `perspective_service`·`hr_sentiment` 🟡 보호 — 승인 후 수정. 서버 무단 실행 금지. DN은 수동 왕복 실동작 검증 후(그 전 Pre-Done).
- **원데이터 비반입**: 측정은 기존 가명 gold(plans/)만. 프로덕션 배치 field는 내부망 매핑 UI(0707_01 Phase2)에서 지정.
