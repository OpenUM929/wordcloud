# 계획서 — 모델이 확립된 규칙을 지키게 만들기 (승격 갭 해소 + 운영 override 재가동)

> 상태: Track2 **완료(DN·미배포)** · Track1 큐레이션 gold 38 배선·긍↔부보드 해소 · seed45 A/B **게이트 미통과(순이득 없음·천장)** → 배포 안 함, gold는 append-only 보존 | 작성일: 2026-07-13
> 작업 유형: 데이터셋/모델 개선 (RUNBOOK 상시 절차 연동)
> ⚠ **이 계획서는 `/compact`(문맥 압축) 이후 이 파일만 보고 실행하도록 자기완결로 작성**(규칙 #15).
>   모든 경로·명령·라인번호·수치는 2026-07-13 실측. 대화 문맥 없이도 §0~§7만으로 실행 가능해야 함.

> 📁 **경로 규약**: 저장소 루트 = `D:\dev\wordcloud`. 데이터셋 루트 `DS/` = `wordcloud_project/plans/_datasets/kote_finetune/`.
>   모든 상대경로는 루트 기준. 파인튜닝 소스 = `wordcloud_project/`.

---

## 수정 이력

| 날짜 | 변경 | 요약 |
|------|------|------|
| 2026-07-13 | 최초 작성 | 세션 진단(모델의 규칙위반·승격갭·override 우회) → 2트랙 실행계획으로 정리 |
| 2026-07-13 | Track2 실행·완료 | 실증 결과 §9 추가. override 통째 재가동 유해 판명(모델>규칙) → R1만 이식. §0 진단 부분정정 |
| 2026-07-13 | Track1 큐레이션 | §10(대량승격 기각)·§11(중립 gold 35 배선·긍↔부 5 보드) 추가. 사용자 "큐레이션 하드샘플" 방향 |
| 2026-07-13 | 긍↔부 보드 해소 | 5건 전부 규칙판정(사용자 확정): positive 3 gold 배선·not_group 2 제외. 큐레이션 gold 38행 확정, 재학습만 잔여 |
| 2026-07-13 | seed45 A/B 실행 | 명령정정(ensemble_eval_r8 --save-seed 45). 유효 A/B=순이득 없음(긍↔부 총1 불변·8c→c3 이동·c3 취약)·천장 재확인 → 배포 안 함, gold append-only 보존. §11-4-b |

---

## §0. 배경·진단 (왜 이 작업을 하는가 — 문맥 없이 이해되도록)

**증상**: 배포된 감정모델(seed45 field-aware, `model/hr_sentiment_finetuned`, sha 620faad, 7/8 학습)이
우리가 문서로 확립한 규칙을 **일부 어긴다**. 2026-07-13 실측(gold 긍↔부 교차 하드 11건을 현 모델에
필드 프리픽스 적용해 재판정): **5건에서 규칙 위반**.

위반 5건과 어긴 규칙:
| 문장 | 필드 | 규칙상 정답 | 현 모델 | 어긴 규칙 |
|---|---|---|---|---|
| 관리감독없이 업무수행 | 장점 | 긍정 | 중립 | 무서술어 단편=필드가 극성([[project_field_signal_for_finetune]]) |
| 필요한 행동을 솔선하여 실행 | 단점 | 긍정 | 부정 | '필요' 렉시콘 트랩(행위서술은 긍정) |
| 직원들과 의사소통이 원활 | 장점 | 긍정 | 부정 | 명백 긍정 |
| 조직 원하는 방향으로 행동 유발 | 장점 | 긍정 | 부정 | 무서술어=필드 |
| 의견수렴해주세요 | 단점 | 부정 | 긍정 | 요청표지(~해주세요)=부정 |

**근본 원인 2가지**:
1. **운영에서 override 규칙이 우회됨.** `wordcloud_project/src/services/perspective_service.py`의
   `_get_sentence_level_scores`(약 1979행 `if model_labels is not None:`): 파인튜닝 모델이 켜져 있으면
   모델 라벨을 그대로 쓰고 `sentence_sentiment_override`(개선요청/요청표지/무응답/약점없음 등 규칙 집합)를
   **실행하지 않는다**(fallback 전용). 즉 우리 규칙 다수가 운영에 반영되는 유일 통로는 "모델이 gold에서 학습".
2. **승격(promotion) 갭.** 그룹검토 리뷰폴더(`DS/eval/review/`)에 사람이 라벨한 데이터가 대량 있는데
   학습에 안 들어가 있다. 모델이 패턴을 어기는 건 라벨이 없어서가 아니라 **라벨된 예시가 학습셋에
   배선되지 않아서**([[project_training_promotion_gap]]).

**핵심 결론**: "데이터/모델 천장"([[project_finetune_data_ceiling]])은 이 관점에서 **부분 재해석** —
천장이 아니라 **미승격 + 규칙 우회**일 수 있다. 신규 라벨링 없이 개선 여지가 있다.

---

## §1. 목표 & 성공기준

**목표**: 배포 모델이 §0의 5개(및 동류 패턴)에서 규칙을 지키게 한다. 핵심가치(긍↔부 오분류 0)는 불변.

**성공기준(둘 다 충족)**:
- (Track1 재학습) 4개 held-out 슬라이스에서 **전 슬라이스 긍↔부 0 유지** + c3_neu149 부recall이 현 c4라인
  (0.688) 대비 1std(±3.4pp) 초과 개선 또는 분산 축소. baseline399·8c_hard 정확도 회귀 없음(±노이즈 내).
- (Track2 override) §0의 11-case 재판정에서 **위반 5건 → 0건**, 동시에 4슬라이스 긍↔부 0 유지(신규 위반 0).

**실패 시**: Track1 정정분·승격분은 append-only로 보존(회수 없음, 데이터정합 개선). 모델은 c4라인 유지.
Track2 override가 신규 긍↔부를 만들면 해당 규칙만 롤백(다른 규칙 보존).

---

## §2. 현황 실측 데이터 (2026-07-13, 전체 TRAIN_FILES=11개 기준)

- **학습 실제 사용**: `wordcloud_project/src`가 아니라 `DS/scripts/finetune_sentiment.py`의
  `TRAIN_FILES`(27행~, 11개 파일) → 고유 텍스트 **3,646행**. 학습 라벨 키 = 각 파일의 `human_decision`
  (finetune `load()`가 `human_decision ∈ {positive,negative,neutral}`만 사용; `not_group`/공란 제외).
- **stranded(리뷰폴더 라벨분 중 학습 미포함) 3,807행**, 출처별:
  - `hd무표시` **1,947** (대부분 260703 그룹감사 — human_decision 채워짐·출처 무표시. **진짜 사람판정 여부 표본검증 필요**)
  - `human명시`(decision_source=human) **196** (안전)
  - `claude_silver`(suggested_source=claude_auto) **863** (대량 금지)
  - `auto`(decision_source=auto_fragment) **801** (대량 금지)
  - → **사람분 최대 ~2,143**(196+1,947), auto/silver 1,664.
- **실패패턴 파일별 stranded 행수**(`DS/eval/review/` 하위, 파일명 prefix):
  `grp7_improvement*` 1,034 · `8c_other_neu*` 923 · `8a_other_pos*` 497 · `grp2_no_weakness*` 122 ·
  `grp5_effort_need*` 98 · `8b_other_neg*` 70 · `grp1_no_response*` 49 · `grp6_spec_need*` 28 ·
  `grp3_health*` 27 · `grp4_excess*` 22.
- **주의**: 파일별 출처가 섞임(예: `grp7_improvement__comm_260703.jsonl` 244행 전량 human_decision;
  `8c_other_neu__comm_260703.jsonl`은 대부분 `auto_fragment`; `8a_other_pos__care_260703.jsonl`은 대부분 미결정).
  → **파일 단위 일괄 승격 금지. 행 단위로 사람판정분만.**

---

## §3. Track 1 — 사람확정 stranded 승격 → 재학습

> 신규 라벨링 아님. **이미 사람이 라벨한 stranded 행을 학습셋에 배선**하는 작업.

### 3-1. [고] 사람판정 진위 표본검증 (승격 전 필수 게이트)
`hd무표시` 1,947행이 진짜 사람판정인지 불확실. 표본(패턴 파일별 20~30행)을 **문장 직접 재판정**해
human_decision과 대조([[feedback_distrust_prelabels_reanalyze]], [[feedback_judge_first_then_reconcile]]).
- 일치율 높으면(≥~90%) 해당 파일군을 승격 후보로.
- 낮으면 그 파일군은 제외(품질 미달 → 승격 시 오염).

### 3-2. [고] 승격 스크립트 작성 → 승격 파일 생성
`DS/scripts/promote_stranded_260713.py`(신규 작성). 동작:
- 입력: `DS/eval/review/`의 실패패턴 파일들 중 3-1 통과분.
- 필터(행 단위): `human_decision ∈ {positive,negative,neutral}` **AND** 출처가 사람(`decision_source`가
  `auto_fragment` 아님, `suggested_source`가 `claude_auto` 아님). 텍스트가 이미 TRAIN/TEST에 있으면 제외(누수·중복).
- 출력: `DS/eval/gold_promoted_stranded_260713.jsonl` — 스키마 `{text, field, human_decision, rec_id, source_file}`.
- **자기검산 출력(규칙 #17)**: 승격 행수·출처별 내역·클래스 분포·auto/silver 유입 0 assert·TEST 누수 0 assert.
- ⚠ **auto/silver 대량 금지**: silver 대량 증강은 정확도 추락 실측([[project_finetune_data_ceiling]]).
  이 스크립트는 사람분만.

### 3-3. [고] TRAIN_FILES 배선
`DS/scripts/finetune_sentiment.py`의 `TRAIN_FILES`(27행) 리스트에 `'gold_promoted_stranded_260713.jsonl'`
추가(additive, 기존 행 보존). 주석으로 출처·행수·날짜 명기.

### 3-4. [사용자/GPU] 재학습 + A/B
```
cd wordcloud_project/plans/_datasets/kote_finetune
python scripts/finetune_sentiment.py --field-token on --tag promote_stranded_260713
```
- `--field-token on` 필수(train/serve 정합, 0707_01). `--weak 0 --silver 0`(기본, 대량증강 금지).
- 출력 `DS/model_out`(구본은 사전 백업: `cp -r model_out model_out_backup_pre260713`).
- 4슬라이스(baseline399·8c_hard·c3_neu149·sa_speech74) 자동 측정 → §1 성공기준 판정.
- 통과 시에만 배포: `model_out` → `model/hr_sentiment_finetuned` 교체 + `gen_version.py` 재생성 +
  **서버 재시작(사용자, [[feedback_no_server_start]])**. 배포 갭 방지([[project_version_json_deploy_gap]]).

---

## §4. Track 2 — 운영 override 재가동 (결정론적 안전 보증)

> 모델 학습 여부와 무관하게, 고정밀 안전 패턴을 모델 출력 위에서 규칙으로 보증. 즉효·GPU 불요.

### 4-1. [고] 대상 분기
`wordcloud_project/src/services/perspective_service.py` `_get_sentence_level_scores`
약 1979행 `if model_labels is not None:` 분기. 현재는 모델 라벨을 그대로 score로 변환하고 override 미실행.

### 4-2. [고] 좁은 고정밀 override 레이어 추가
모델 라벨 획득 **후**, 아래 문서화된 고정밀 패턴에만 후처리 보정(전면 override 아님):
- **요청표지/개선요청 core**(`~해주세요`·`~할 필요`·`~했으면`·요망/요함): 모델=긍정이어도 → 부정
  (기존 `_has_improvement_request_core`·`has_constructive_need` 재사용, perspective_service 내 존재).
- **무서술어 단편 + 필드**: 서술어 없는 단편이면 필드 극성 채택(장점→긍/단점→부). 필드 없으면 미적용.
- **긍부 혼재**: 절 분리 결과 극성 상충 시 중립([[project_clause_level_sentiment_unit]], `split_clauses` 존재).
- **명시 서술어 우선**: 명시 칭찬어("좋습니다" 등) 있으면 필드보다 문장 극성 우선.

### 4-3. [고] 안전 제약 (불가침)
- 이 레이어는 **긍↔부를 새로 만들면 안 됨**. 중립방향 보정 또는 규칙이 명확한 플립만
  ([[project_sentiment_core_value]], `apply_gold_corrections_260630.py`의 "중립방향만" 원칙 계승).
- 기존 게이트(negation 칭찬·반전표지) 보존 — 진짜 부정을 긍정으로 뒤집지 말 것.

### 4-4. [고] 검증 (게이트)
- **재판정 테스트**: §0의 11-case를 현 모델+override로 재실행 → 위반 **5→0** 확인.
  (재현 스크립트: `predict_sentiments(texts, fields)` 후 override 적용, 세션에서 사용한 방식.)
- **회귀 게이트**: 4슬라이스에서 긍↔부 0 유지·정확도 회귀 없음. 신규 긍↔부 발생 시 해당 규칙 롤백.
- 단위테스트: `plans/2026/07/13_03_rule-alignment/test/test_override_guard.py`(골든/트랩 각 패턴).

---

## §5. 실행 순서 & 역할 분담 (규칙 #17)

```
Track2(즉효·GPU불요) ─ [고] override 레이어+단위테스트 ─▶ [고] 11-case+4슬라이스 검증 ─▶ 통과 시 커밋
Track1(모델기본기)  ─ [고] 표본검증 ─▶ [고] 승격스크립트+배선 ─▶ [사용자/GPU] 재학습 A/B ─▶ 통과 시 배포
```
- **[고](고비용 AI)**: 표본검증·스크립트 설계·자기검증 스캐폴딩·override 코드·판정·산출물 검증(출력 확인).
- **[저](저비용 AI)**: 승격/검증 스크립트 대량 실행, 스크립트가 출력한 수치를 로그에 기록(손집계 금지).
- **[사용자]**: GPU 재학습·서버 재시작·표본검증 이견 재정.
- **권고 순서**: **Track2 먼저**(즉시 결정론적 보증, GPU 불요) → Track1(재학습으로 기본기 향상).

---

## §6. 재론 금지 / 주의 (실측 기각 — 반복 금지)

- **auto/silver 대량 증강 금지**: 정확도 추락 실측(c5 회수 인과 확정, [[project_finetune_data_ceiling]]).
  Track1은 **사람분만** 승격.
- **경계(boundary) gold 소량 증강 단독 금지**: c5·c6 후퇴 실측(부recall↔긍↔부 맞바꿈).
- **파일 단위 일괄 승격 금지**: 출처 혼재(§2 주의) — 행 단위 사람분만.
- **긍↔부 방향 gold/override 임의생성 금지**: 사람 확정만([[feedback_no_group_stamp_per_row]]).
- **서버 무단 실행/재시작 금지**([[feedback_no_server_start]]) — 안내만.
- **escalation은 규칙 잔여만**([[feedback_escalate_only_rule_residual]]) — 규칙이 정하는 건 사용자에게 되묻지 말 것.

---

## §7. 완료 정의 (DN — 실동작 검증 후에만, [[feedback_dn_after_runtime_verify]])

- **Track2 DN**: override 레이어 병합 + 11-case 위반 0 + 4슬라이스 긍↔부 0 + 단위테스트 PASS + 실동작(재분석) 확인.
- **Track1 DN**: 승격파일 생성(자기검산 PASS) + TRAIN 배선 + 재학습 A/B가 §1 성공기준 충족 + (배포 시) 서버 재시작 후 스팟체크.
- 그 전 단계는 PND(보류) + 체크리스트로 관리.

---

## §8. 참조 (경로·스크립트·근거)

- 진단 근거: 본 폴더 상위 `13_02_model-next-cycle/13_02_model-next-cycle.md` §12·§13(모델 규칙위반·2트랙).
- 학습: `DS/scripts/finetune_sentiment.py`(TRAIN_FILES:27·load()·main:142·`--field-token`).
- 승격 참고: `DS/scripts/promote_gold.py`(emotion.jsonl 스트림용 — **finetune는 이걸 안 읽음**, TRAIN_FILES를 읽음. 혼동 주의).
- 운영 추론 분기: `wordcloud_project/src/services/perspective_service.py:~1979`(model_labels 분기).
- 필드 추론: `wordcloud_project/src/modules/hr_sentiment.py`(`predict_sentiments(texts, fields=)`·`_prefixed`).
- 세션 산출물(이미 생성): `DS/scripts/mine_hard_samples.py`(미채점 가드·자기검산) · `prefill_hard_queue.py`
  (escalation 자기검산) · `extract_holdout.py` · `build_gold_crossing_review_260713.py` ·
  `apply_gold_crossing_260713.py`(P1 긍↔부 11건 반영 완료).
- 메모리: [[project_training_promotion_gap]] · [[project_field_signal_for_finetune]] · [[project_finetune_data_ceiling]] ·
  [[project_sentiment_core_value]] · [[project_clause_level_sentiment_unit]] · [[feedback_escalate_only_rule_residual]] ·
  [[feedback_extend_metadata_structure_not_bespoke_ui]] · [[project_version_json_deploy_gap]] · [[project_override_bypass_is_correct]].

---

## §9. Track 2 실행 결과 (2026-07-13, 실증) — **§0 진단 부분정정**

> 산출물: `plans/2026/07/13_03_rule-alignment/test/` (reproduce_11case.py · diag_ruleids.py ·
>   override_layer.py(프로토타입) · verify_override.py(게이트) · test_override_guard.py(단위) ·
>   *_result.json). 이식: `src/services/perspective_service.py` `apply_model_label_override()` + 모델분기 wiring.

### 9-1. Baseline 재현 (현 배포 모델, 필드 프리픽스 적용)
11-case: **위반 5 · 그중 긍↔부 4**(§0과 정확히 일치). 진짜 긍↔부 4건 = case4·5·10(부→긍)·case11(긍→부).
case1(장점, 모델=중립, gold=긍정)은 **중립→긍정 허용**(핵심가치)이라 긍↔부 아님 = 허용되는 중립 미스.

### 9-2. 🔴 핵심 발견 — "override 우회 = 근본원인"은 **틀렸다**
diag_ruleids로 기존 override cascade를 11-case에 재적용 → **모델이 규칙보다 정확**:
- case2(부정 정답)를 `improvement_request_neutral`이 부→중 **회귀**시킴.
- case3(혼재=중립 정답)를 `improvement_request_neg`가 중→부 **회귀**시킴.
- case6(긍정 정답)을 점수기반 `rule3_last_low`가 긍→부 **회귀**(긍↔부!)시킴.
→ **override 통째 재가동은 유해.** 모델은 field 프리픽스로 학습(train/serve 정합)돼 **필드신호를
이미 내장**하므로, 규칙 대부분이 모델보다 열등. §0 근본원인 ①(override 우회)은 **부분 오진** —
override는 fallback으로만 두는 게 맞다([[project_override_bypass_is_correct]]).

### 9-3. 실증 게이트 결과 (4슬라이스 pre=모델단독 / post=+override)
| override 시도 | baseline399 | 8c_hard | c3_neu149 | sa_speech74 | 판정 |
|---|---|---|---|---|---|
| **R2**(무서술어 단편→필드극성) | 긍↔부 0→2·acc−11 | 0→? ·acc−27 | 0→2·acc−9 | 0→0 | **FAIL(폐기)** — 모델과 필드신호 중복 |
| **R1**(요청표지 core 포함) | 0→0 | 0→0 | 0→0(acc−1) | 0→0 | 집요함('요함' substring) 트랩 발견 |
| **R1**(고정밀 `_has_request_marker`만) | 0→0 | 0→0 | 0→0 | 0→0 | **PASS(채택)** — 발동 0·청정 |

### 9-4. 채택 — R1만 이식 (좁은 고정밀 override)
`apply_model_label_override(model_label, sentence, field)`: **model=='positive' + 요청표지 화행
(`_has_request_marker`, 트랩가드 내장) + 명시강긍정·차단반전 없음 → 'neutral'**. 긍→중만(긍→부 없음)
→ **긍↔부 구조적 불생성**. R2(필드신호)·core('요함' substring)는 폐기.
- 단위테스트 `test_override_guard.py`: **12/12 PASS**(집요함·중요함 트랩 보호, 강긍정 보호, 모델 부정/중립 불변).
- 4슬라이스: **긍↔부 신규 0(전부 PASS)**, 정확도 회귀 없음.
- 11-case: 긍↔부 **4→3**(case11 긍→중으로 제거). wiring 스모크테스트 통과.

### 9-5. Track 2 미해결(=Track 1로 이관) — 부→긍 3건
case4·5·10(모델이 명백 긍정을 부정으로): override로 안전 교정 불가(positive_rescue는 KoTE neg≥0.85
게이트에 막힘, 넓히면 긍↔부 위험). **이들은 모델이 배워야 함 → Track 1 재학습이 유일한 안전 통로.**
즉 **실질 개선 레버는 Track 1(승격+재학습)이며 Track 2는 얇은 안전망**이었음이 실증됨.

### 9-6. Track 2 DN 체크(§7)
✅ override 병합 ✅ 11-case 긍↔부 감소(4→3) ✅ 4슬라이스 긍↔부 신규 0 ✅ 단위테스트 PASS
✅ 실동작(_get_sentence_level_scores) 스모크 확인. **미배포**(코드는 dev, 서버 재시작은 사용자 몫).

---

## §10. Track 1 3-1 결과 (2026-07-13, 실증) — **대량 승격 기각, 큐레이션으로 전환**

> 산출물: `scripts/inventory_stranded_260713.py`(재고조사·자기검산) · `eval/stranded_candidates_260713.jsonl`
>   (사람분 stranded 1,942) · `test/verify_stranded_quality.py`(hd vs 모델 진단) ·
>   `test/stranded_pn_disagreements.jsonl`(긍↔부 14).

### 10-1. 재고조사 정정치(전 TRAIN 11파일 기준)
- TRAIN 고유텍스트 **3,646** · TEST 762. 사람분 stranded = **1,942행(전부 hd무표시)**.
  human명시 stranded는 **0**(762건 전부 이미 TRAIN/TEST). TEST 누수 162행은 승격셋에서 제외.
- 클래스 편중: **부정 1,390(72%)·중립 477(25%)·긍정 75(4%)**. 대부분 grp7_improvement(1,030).

### 10-2. 🔴 핵심 발견 — hd무표시는 노이즈, **대량 승격은 유해**
후보 1,942를 현 모델과 대조(`verify_stranded_quality.py`):
- **hd==model 일치 85.6%(1,663)** → 모델이 이미 앎 = 승격 가치 낮음. grp7_improvement는 95% 일치
  (모델이 이미 개선요청→부정 학습) → 대량 추가는 새 신호 없이 **부정 분포만 키워 c6식 중립recall
  하락 위험**([[project_finetune_data_ceiling]], c6=개선요청 74 gold 회수 전례).
- **hd무표시 라벨에 실제 오류 혼입**(직접 판정): 긍↔부 불일치 14 중 **≥5가 오라벨**(hd=부정이나
  명백 긍정 — "…모습은 찾아볼 수 없으며"(부정어의부정=긍), "불필요한 업무 배제", "자기계발 노력").
  중립층도 불일치: hd=중립인데 실제 개선요청=부정("소통 능력의 필요성"·"협력 저해") 다수 = hd 오류.
  → **hd무표시 = 구규칙 출력+부분 사람편집 혼합**, 우리 확립규칙과 불일치. 대량 승격 시 **긍↔부
  오류 + 부정 오라벨을 학습에 주입** = c6 회귀를 14배로 재현. **기각**([[project_override_bypass_is_correct]] 계열).

### 10-3. 실제 가치가 있는 곳 = 소수 큐레이션 대상(모델 진짜 오류)
- **건강/사생활→중립**(모델이 부정화): grp3_health 19%일치(26행 대부분)·"건강 우려"·"휴가 좋겠다" — 고가치.
- **역량=긍정인데 모델이 부정화**: "너무 전문적/업무에 빠져있음"(장점), "개선하고자 하는 부분 많음"(부정 맞음) 등.
- 이들은 **행 단위 [고] 판정 + 사용자 확정**([[feedback_prefill_judgment_escalate_uncertain]],
  [[feedback_no_group_stamp_per_row]]) 후에만 소량 gold로. 규모는 수십~수백(수천 아님).

### 10-4. 개정된 Track 1 (§3 대체) — **큐레이션 하드샘플, 대량 승격 금지**
1. [고] 후보 불일치(279행: 긍↔부 14 + 중립층 265)를 per-row 판정 prefill → 모델과 불일치이고
   내 판정이 확실한 것만 gold 후보. 불확실만 사용자 escalation.
2. [사용자] escalation분 확정.
3. [고] 확정분으로 소량 gold 파일 생성(자기검산) → TRAIN 배선.
4. [사용자/GPU] 재학습 + 4슬라이스 A/B(§1 게이트, 특히 c3_neu149 부recall·긍↔부 0).
- ⚠ **grp7 등 85.6% 일치분은 승격 제외**(무가치+분포위험). auto/silver·대량 금지(§6 유지).
- **[[project_training_promotion_gap]]는 부분 재해석**: stranded 대부분은 "미승격 갭"이 아니라
  "모델이 이미 아는 것 + 노이즈". 진짜 갭은 소수 하드샘플(건강중립·역량긍정)뿐.

---

## §11. Track 1 큐레이션 실행 결과 (2026-07-13) — 사용자 방향 "큐레이션 하드샘플" 채택

> 산출물: `scripts/inventory_stranded_260713.py` · `scripts/build_hardsample_gold_260713.py` ·
>   `test/triage_hardsamples.py` · `eval/gold_hardsample_neutral_260713.jsonl`(35) ·
>   `eval/review/hardsample_pn_review_260713.jsonl`(긍↔부 5 보드).

### 11-1. 3자(모델·규칙·hd) 트리아지 — 불일치 279행
`triage_hardsamples.py`: **GOLD 35 · DISCARD 118(hd노이즈) · ESCALATE 126**.
- 자동 GOLD 기준 = **중립방향 규칙(personal_wellbeing/health/no_weakness/no_response)이 hd=중립을
  확증 + 모델이 극성 오판**. 극성뒤집기(positive_rescue·improvement_request_neg)는 트랩 상습
  (집요함·"했으면"·개인안녕 오발동)이라 자동 gold 금지 → escalation.

### 11-2. ✅ 채택 gold — 중립 하드샘플 35 (긍↔부 불생성)
전부 **개인안녕·건강·피로·스트레스**("건강관리 필요"·"번아웃"·"스트레스 받는듯"·"상처 안받았으면")를
모델이 **부정으로 과오판**한 것 → 문서정책(개인안녕→중립)대로 **중립 교정**. 하드 중립클래스
([[project_neutral_is_the_hard_class]]) 강화, 긍↔부 위험 0(중립방향).
- `eval/gold_hardsample_neutral_260713.jsonl` 생성(자기검산: 전부 neutral·TEST누수 0).
- **TRAIN_FILES 배선 완료**(finetune_sentiment.py, 12파일째). 기존과 라벨충돌 0·누수 0 확인. 재학습=사용자 GPU.

### 11-3. ✅ 긍↔부 5 보드 — 규칙적용으로 해소(사용자 확정 260713, 진짜 잔여 0)
⚠ **재-교훈**: 5건 모두 **우리 확립규칙이 이미 정하는 것**이었다(또 over-escalation,
[[feedback_escalate_only_rule_residual]]). 사용자 확정 결과 = 규칙 판정과 일치:
| 문장(장점) | hd/모델 | 확정 | 근거(규칙) |
|---|---|---|---|
| …업무전가하는 모습은 찾아볼 수 없으며… | 부/긍 | **positive** | 부정어의 부정=칭찬. 현규칙 부정은 "했으면" 희망형 트랩 오탐 |
| 업무에 너무 빠져있고 전문적인 편임 | 긍/부 | **positive** | 장점+전문성, 모델 과부정 오판 |
| 업무에 너무 전문적이다 | 긍/부 | **positive** | 장점+칭찬, 모델 과부정 오판 |
| …적기 필요한 조치 요구 | 긍/부 | **not_group** | 무서술어·필드의존([[project_field_signal_for_finetune]]) → 학습제외 |
| 너무 이성적이고 워커홀릭임 | 부/긍 | **not_group** | 무서술어·필드의존 → 학습제외 |
→ positive 3 = `eval/gold_hardsample_pn_260713.jsonl` 생성 + **TRAIN 배선 완료**(충돌0·누수0).
not_group 2 = 보드에 기록·학습 제외(필드 프리픽스가 극성 담당). `resolve_hardsample_pn_260713.py`.

### 11-4. 남은 단계 — [사용자/GPU] **seed45 경로로** 재학습 (⚠ 명령 정정)
🔴 **정본 재학습 경로 = `ensemble_eval_r8_260708.py --save-seed 45`** (배포 seed45가 만들어진 경로).
`finetune_sentiment.py`는 **seed=42 개발 스크립트**라 배포와 시드 불일치 → A/B 무효. 정정:
```
cd wordcloud_project/plans/_datasets/kote_finetune
python scripts/ensemble_eval_r8_260708.py --save-seed 45 --save-dir model_out --field-token on
```
(TRAIN_FILES를 임포트하므로 +38 gold 자동 포함. model_out에 seed45+gold 저장·4슬라이스 출력.)
- **A/B 기준 = 배포 seed45 실측**: baseline **91.5**·8c **84.3**·c3 **73.8**·sa **81.1**, **긍↔부 총 1**.
- §1 게이트: 전 슬라이스 **긍↔부 0**(특히 c3, [[project_neutral_is_the_hard_class]]) · c3 부recall 개선 · 회귀 없음.
- ⚠ **c3 중립경계 취약**: 모델수프도 c3 긍↔부 0→3 유발해 기각됨(IMPROVEMENT_HISTORY 9차). +38 gold 효과는
  작을 수 있고, 통과 못하면 **배포 안 함**(gold는 append-only 데이터품질로 보존, 다음 대규모 재학습 시 반영).

#### 11-4-b. ✅ 유효 seed45 A/B 결과(2026-07-13) — **게이트 미통과·배포 안 함**
`ensemble_eval_r8_260708.py --save-seed 45`(직접 실행). 저장전 재현확인 baseline **91.5**·8c **84.3** =
배포 seed45 정확일치 → 경로 검증됨, c3/sa 차이는 gold 귀속.
| slice | 배포 seed45 | +38 gold | Δ |
|---|---|---|---|
| baseline399 | 91.5·긍↔부0 | 91.5·긍↔부0 | = |
| 8c_hard | 84.3·긍↔부1 | 84.3·**긍↔부0** | 8c 긍↔부 1→0 ✓ |
| c3_neu149 | 73.8·긍↔부0 | 72.5·**긍↔부1**(부→긍) | c3 긍↔부 0→1·acc−1.3 ✗ |
| sa_speech74 | 81.1·긍↔부0 | 78.4·긍↔부0 | acc−2.7 |
| 긍↔부 총합 | 1 | 1 | 8c→c3 이동만 |

**판정: 순이득 없음(긍↔부 총합 1 불변, 위치만 이동)·c3 부recall 0.604<0.688(개선 아님)·c3 중립경계
긍↔부 0→1 교란(모델수프 기각과 동형). → §1 게이트 미통과, 배포 안 함.** 현 배포 seed45 유지.
- 근본: 모델 천장([[project_finetune_data_ceiling]]) — 38행은 유의미 이동 불가, c3만 교란.
- **38 gold 처리**: 라벨 자체는 검증된 정본이므로 TRAIN_FILES에 **append-only 보존**(회수 없음).
  다음 **대규모** 재학습(하드샘플 수백~수천 누적) 시 함께 반영. model_out=미배포(수동복사 안 함).
- ⚠ 부수효과: TRAIN_FILES에 38 포함돼 이후 seed45 재현런은 c3 72.5로 나옴(배포본 73.8과 구분).

#### 11-4-a. seed42 오런 기록(2026-07-13, 무효)
`finetune_sentiment.py`(seed=42, n_train 4014) 실행 결과 — **시드교란으로 무효·미배포**:
baseline 91.2·8c 82.9·**c3 70.5(긍↔부 4: 긍→부1·부→긍3)**·sa 77.0. 배포 seed45 대비 전 슬라이스 열세이나
seed42≠45(45는 5시드 best 손선택)라 gold 판정 근거 아님. model_out에 이 오런이 저장돼 있으니 **덮어쓰기 전 배포 금지**.
- 📌 선재 이슈(비차단): 기존 TRAIN 파일 간 **라벨충돌 26건**(no_weakness 긍↔중 엇갈림) — 내 신규분 무관.

### 11-5. Track 1 상태
큐레이션 gold = 중립 35 + 긍정 3 = **38행 배선완료(자기검산·충돌0·누수0)**. 긍↔부 보드 해소(잔여 0).
재학습 A/B는 사용자 GPU 대기 = PND(A/B 통과 전 최종 DN 아님, [[feedback_dn_after_runtime_verify]]).
