# hr-kote-finetune — 데이터셋 누적 RUNBOOK (상시 운영)

> ⚠️ **이 문서는 "계획서"가 아니다. 완료(DN) 개념이 없다.** 데이터가 들어올 때마다 반복 수행하는 **상시 절차 + 누적 로그**다.
> 설계(스키마·택소노미·보안): `../../2026/0617_05_kote-finetune-data/0617_05_kote-finetune-data.md` · 폴더 규약: [`README.md`](README.md)
> 핵심 가치: **긍↔부 오분류 방지.** 현재 최대 공백 = **positive gold 부족**(아래 §누적 로그 참조).

---

## §0. 내 역할 — 핵심 엔지니어 (데이터셋 작업 전용 위임)

> 본 RUNBOOK이 트리거되는 모든 데이터셋 작업(감정/리더십 분석·강화, CSV 도착, 어노테이션, export/분할, 택소노미 갱신)에서 Claude는 **핵심 엔지니어**로 일한다. 이 역할은 아래 가드레일을 **덮어쓰지 못하고 품는다**.

**책임지는 것**
- 데이터셋 설계·택소노미·파인튜닝 전략의 기술 판단을 **주도**하고, 근거·트레이드오프를 먼저 제시한다.
- **긍↔부 0 오분류**와 데이터 무결성(append-only·비식별화)을 지키는 최종 기술 책임을 진다.
- 결정을 미루지 않되, **되돌리기 어려운 일**(스키마 파괴적 변경, 백본/대그룹 경계 변경, gold 대량 확정, 모델 학습 착수)은 "권고 + 선택지"로 올린다.

**그대로 지키는 가드레일 (역할이 못 덮음 — §2 불변 원칙·제약과 동일)**
- **추측 분류 금지** — 분류는 데이터 군집(TRAIT_TREE §6) 후에만. 빈 leaf는 grouped 유지.
- **append-only** — 기존 행 수정/삭제 금지, 정정은 동일 `id` 신규 리비전.
- **비식별화·dev 반출 금지** — 가명화 텍스트만, `src_hash`, 내부망 전용.
- **서버 무단 실행 금지 / dev 배치 불가·CSV만 / O(n)**(1.9만 규모).
- **사용자 고유 결정**(범위·예산·배포·신규 라벨 채택)은 **선점하지 않고 에스컬레이션**.

**작업 방식**
- 추측보다 **코드·데이터 확인 우선**. 못 박힌 사실은 재유도하지 않음.
- 완료/실패/생략을 **정직하게 보고**(과장·자축 금지). 핵심가치 위반 가능성은 즉시 표면화.

---

## §1. 트리거 (언제 이 RUNBOOK을 펴는가)

다음 중 **하나라도** 해당하면 반드시 본 RUNBOOK의 §2 체크리스트를 수행한다.

- 감정어/리더십 **분석·알고리즘 강화 작업**을 진행할 때 (검토 1회 = gold 확정 1회로 겸함).
- 취득 코퍼스 **CSV가 새로 도착**했을 때 (`data/*.csv` 반입).
- `acquired_sentences`에 **신규 행이 적재**되었을 때.

> CLAUDE.md "📦 학습 데이터셋 누적 지침"이 이 RUNBOOK의 나침반 진입점이다.

---

## §2. 데이터 도착 시 체크리스트 (매회 반복)

### §2-0. 단일 자기실행 명령 (먼저 이것부터 — 재량 개입 차단)

> ⚠️ **데이터 빌드를 임의로 건너뛰지 말 것.** 과거 1회, 범위를 "규칙 트랙 한정"으로 줄여 데이터셋 빌드를 생략한 사고가 있었다(입력 36만인데 기록 0). 이를 막기 위해 1~6단계를 **한 명령**으로 묶었다. 데이터가 오면 **반드시 먼저 이 명령을 돌린다.**

```
cd wordcloud_project/plans/_datasets/kote_finetune/scripts
python dataset_pipeline.py --in <드롭파일.jsonl|csv> [--date YYMMDD]
```

이 한 명령이 **반입 → 절분리(혼합극성 분해) → 이중 약지도(감정 override + 리더십 weak LF) → 비식별화 → append-only 스냅샷 → 패턴 마이닝 → 회귀 게이트 → 실행 요약**을 자동 수행한다(O(n)·서버/GPU 불요).

**기계검증 FAIL 게이트(자동 — 사람 판단 불요):**
- `입력 행수 > 0` 인데 `기록 레코드 = 0` → **FAIL**(빌드 누락. "규칙 트랙 한정"으로 0 기록 금지).
- 회귀 스위트(긍↔부 0) 실패 → **FAIL**.
- PASS/FAIL은 종료코드 + `result/pipeline_run_<date>.md`에 기록. **FAIL이면 §누적 로그에 '완료'로 적지 않는다.**

**자동(빌드) vs 사람(escalation) 경계 — 명문화:**
- **자동(절대 생략 금지)**: 위 1~6단계 = 약지도 데이터셋 빌드 + 패턴 후보 발굴.
- **사람(escalation에서만)**: gold **대량 확정**(3~4단계 confirmed), 신규 trait/대그룹 채택, 택소노미 파괴적 변경, 파인튜닝 착수. → 빌드를 멈추지 말고, 이 항목만 "권고+선택지"로 올린다.

> 스크립트: `scripts/dataset_pipeline.py`(오케스트레이터) · `scripts/leadership_lf.py`(리더십 weak LF) · `scripts/mine_patterns.py`(규칙·패턴 발굴) · `leadership/trait_tree.json`(택소노미 — 코드 아닌 데이터). 절 분리 = `src/modules/text_preprocessing.split_clauses`(production `split_sentences` 불변).

### §2-1. 단계 상세 (위 명령이 자동 수행)

| 단계 | 작업 | 도구/위치 | 산출 |
|------|------|-----------|------|
| 1. 반입 | CSV 업로드 → `acquired_sentences` 적재 | `acquired_data.html` "데이터 가져오기" → `POST /api/perspective/acquired-sentences/import` (`perspective_service.import_acquired_sentences_csv`) | 적재 행 |
| 2. 약지도 사전라벨 | KoTE top3 + 발동 규칙/리더십 극성 자동 부여 | `perspective_service.refine_acquired_row` (내보내기/검토 화면에서 재계산) | weak_sentiment, applied_rule |
| 3. 사람 검토(gold) | 우선순위 큐로 `sentiment_gold`(+선택 `emotions_gold`/`leadership_gold`) 확정 | `acquired_data.html` 검토 뷰 | `review_status=confirmed` |
| 4. 스트림 append | **confirmed gold만** 정식 스트림에 append-only 기록 | `emotion/emotion.jsonl`, `leadership/leadership.jsonl` | gold 누적 |
| **5. 규칙 재마이닝** | **신규 데이터로 케이스바이케이스 규칙도 함께 강화**: ① deferred 규칙(혼합극성 등, [`0617_01`](../../2026/0617_01_emotion-rule-mining/0617_01_emotion-rule-mining.md) §0-A) 표본 충족 여부 재확인 ② 신규 오분류 패턴(`rule_hurt`·저마진·검토 피드백)에서 표지/분기 도출 → `hr_context_lexicon`(`POSITIVE_MARKERS`/`NEGATIVE_MARKERS`/분기)에 **additive append** ③ 회귀 재검증 통과 확인 | `src/modules/hr_context_lexicon.py`(append) + `0617_01/test/run_*_regression.py`, `test_leadership_polarity.py` | 신규 표지/분기 + 회귀 ✅ |
| **5.5 잔여 하드케이스 판정(케이스 트랙)** | **규칙으로 못 잡는 잔여**(희망형·양보·타인지칭·저마진)를 **판정 패킷**으로 추출 → AI(Claude)가 1건씩 판정 → `sentiment_corrections`에 **가명 키 in-place 삽입**. 규칙(대량)과 별개로 **케이스바이케이스 최대치**를 뽑는 트랙. needs_human은 사람 모달 큐로. | `judgment_packet_service.build_judgment_packet`/`apply_judgment_packet` · routes `POST /api/perspective/judgment/extract`·`/apply` · 입력원 `eval/validation_candidates_<date>.jsonl` | corrections 보정 + needs_human 큐 + (확정분) gold 승격 후보 |
| 6. 스냅샷·분할 재생성 | 비식별화 게이트 + 누수방지 분할 + 품질 리포트 | `python scripts/export_jsonl.py` → `python scripts/build_splits.py` | `*.jsonl`, `result/*_report_<date>.md` |
| 7. **누적 로그 갱신** | 본 RUNBOOK §누적 로그에 1행 추가 | (이 파일) | 진행/공백 가시화 |
| 8. 핵심가치 점검 | 긍↔부 오분류 0 + positive gold 확보 추세 확인 | `result/split_report_<date>.md` | 게이트 통과 |

> 🔁 **규칙 트랙도 상시 루프다.** 규칙 마이닝은 `0617_01`(DN)에서 끝난 게 아니라, **데이터가 올 때마다 5단계로 재실행**된다(표본 부족으로 보류했던 deferred 규칙이 충족되면 그때 추가). 규칙은 파인튜닝(D5) 후에도 **후처리 가드로 유지**(`0617_05` §9·§12) — 모델이 규칙을 대체하지 않는다. 단, **추측으로 표지를 늘리지 않는다**: 코퍼스 오분류 근거가 있을 때만 append(`0617_01` §5-2 원칙).

### §2-2. 방법 일반화 — 두 트랙 + 리더십도 같은 골격

> 데이터가 와도, 리더십으로 넘어가도 **동일 절차**가 돌도록 방법을 못 박는다. 이 표가 "우리가 하는 과정"의 정본 골격이다.

**같은 데이터에서 함께 자라는 두 트랙(매 도착 반복):**

| 트랙 | 무엇 | 어떻게 | 누가 | 산출 |
|------|------|--------|------|------|
| **A. 대량/체계**(자동) | 빈출·체계적 오분류 버킷을 한꺼번에 교정 | `dataset_pipeline.py`(약지도+규칙 재마이닝 §2-1 step5)·FAIL게이트·회귀 | system(자동) | weak 스냅샷 + additive 표지/분기 |
| **B. 케이스**(AI/사람) | 규칙으로 못 잡는 잔여를 **1건씩** 판정 | 판정 패킷(§2-1 step5.5) → AI 판정 → in-place 삽입 + gold 확정(step3) | AI(Claude)/사람 | corrections 보정 + confirmed gold |

- **원칙**: 먼저 A로 대량을 정리 → 남은 잔여만 B로 케이스 추격(B를 A보다 먼저 돌려 낭비 금지). 두 트랙 모두 **긍↔부 0** 게이트를 공유한다. A는 substring 함정 위험으로 **체계 패턴만**(추측 금지), B는 함정 없이 개별 판정 가능.

**리더십 트랙도 같은 골격으로 진행(감정 ↔ 리더십 대응):**

| 단계 | 감정 트랙 | 리더십 트랙(같은 형태) |
|------|-----------|------------------------|
| 약지도 | KoTE override → pos/neg/neu | `leadership_lf.build_leadership_candidates`(grouped 기본·micro 힌트·polarity 재게이트) |
| 대량 마이닝(A) | `hr_context_lexicon` 표지/분기 additive | `trait_tree.json` 택소노미(코드 아닌 데이터) — split-only 단조 세분화 |
| 케이스(B) | 판정 패킷(긍/부/중 1건씩) | 동일 패킷 골격 재사용(trait/극성 판정 슬롯) — **무지도 군집(D1) 후** 세부 승격 |
| gold 확정 | `sentiment_gold` confirmed | `leadership_gold` confirmed(대그룹 우선, 세부는 군집 근거 시) |
| 회귀 잠금 | 긍↔부 0 | 긍↔부(positive↔risk) 0 — 같은 게이트 |

- **차이는 "분류 발굴 방법"뿐**: 감정은 코퍼스 오분류 근거로 규칙 append, 리더십은 **무지도 군집 후에만** trait 승격(추측 금지 — 빈 leaf는 grouped 유지). 절차·게이트·gold 흐름·패킷은 **그대로 재사용**한다. → 리더십 데이터가 오면 본 §2 루프를 그대로 돌리고, 마이닝(A)만 군집으로 치환.

### 우선순위 검토 큐 (3단계, 전수 아님 — 고가치부터)
1. `rule_hurt`(보정이 정답을 틀린 행) — 즉시 검수.
2. 극성 불일치(`weak_sentiment` ↔ 사람 직관, 특히 부↔긍 경계).
3. 저마진 argmax(`|pos-neg|<0.05`) → 신규 분기 발동분 표본 감사.

### 불변 원칙 (매회 준수)
- **append-only**: 기존 행 수정/삭제 금지. 정정은 **동일 `id`의 신규 리비전 행**(최신 confirmed 채택).
- **비식별화**: `source_*_id` → `src_hash`, PII 정규식 감사로 적발 행 격리(§14-1). 가명화 미완 텍스트 기록 금지.
- **dev 반출 금지**: JSONL·원문은 내부망 전용. `plans/`는 배포 제외 폴더.
- **신규 감정/리더십 그룹**: 코퍼스 발굴 근거 있을 때만 추가(추측 금지).
- **규칙 additive·추적성**: `hr_context_lexicon` 표지/분기는 **append만**(기존 표지·rule_id·시그니처 불변), 신규 분기엔 rule_id 부여. 추가 전후 **회귀(`run_*_regression.py`) 통과 필수** — 긍↔부 오분류 0 유지.

---

## §누적 로그 (append — 매 도착마다 1행)

| 날짜 | 입력원 | 입력 건수 | 기록 건수 | PII 격리 | gold confirmed | positive gold | 신규 규칙/표지 | 분할(train/val/test) | 비고 |
|------|--------|-----------|-----------|----------|----------------|---------------|----------------|----------------------|------|
| 2026-06-17 | `data/acquired_sentences_20260617.csv` 등 | 722 | 713 | 9 | 0 (약지도만) | **0** | `hr_context_lexicon` negation 게이트(긍61/부11 근거) | 554 / 70 / 89 | 첫 스냅샷. `user_label==model_label`(gold 부재). **positive gold 확보가 학습 선결.** 혼합극성 규칙은 3/475로 보류(deferred). |
| 2026-06-22 | `batch_20260622_0.jsonl` (다면평가, KoTE 사전라벨 36.4만) | 363,728 | ⚠️ 측정만(빌드 누락 — 06-23 정정) | — | 0 | **0** | **감정보정 §2-5 재마이닝**: `positive_rescue` positive-negation 가드(`관심이 없다`類 부→긍 27 차단) + `euphemistic_negative` negation 인식(`보완이 필요하지 않으며` 긍→부 1 교정). additive·`perspective_service` | (미실행) | **파일 `y`/`s`/`e`=KoTE 출력, 정답 아님 → 직접 재판정**(감사 165문장). old→new 양방향 긍↔부 0(신규오류 0), 회귀 5종 통과. 감사 리포트 `result/sentiment_eval_260622.md`. ⚠️ **이 행은 규칙 측정만 하고 데이터셋 빌드를 생략한 사고** → §2-0 단일 명령·FAIL게이트 신설로 재발 차단, 06-23에 실제 빌드. |
| 2026-06-23 | `default/` 5배치(장점_3차=0622_0·단점_3차=0622_2·단점_1차=0623_1·장점_2차=0623_2·단점_2차=0623_3, `.csv`지만 JSONL 내용) | 741,228 | **756,688**(문장 739,918 + 절 16,770) | 1,310 | 0 | weak 468,241(미확정) | **단일 파이프라인 `dataset_pipeline.py`**: 폴더/다중파일·내용기반 JSONL감지·batch태그 중복제거 + `split_clauses` + 리더십 weak LF + 감정 override + 검증셋 추출. 이중 스트림·weak-only | (build_splits 대기) | **자기실행+FAIL게이트 PASS·회귀 ✅·긍↔부0.** 배치별 분포 정상(강점 95% 긍 / 약점). 규칙수정 2종(`소홀` 결함가드·`has_constructive_need` 건설적필요가드, 약점 부→긍 12,795 교정·긍→부 0) 반영. 검증셋 `eval/validation_candidates_260623.jsonl`(42,474). 스냅샷 `emotion/weak_export_260623.jsonl`. |
| 2026-06-23 | `data/23년_장점.csv` (장점, KoTE 사전라벨, batch_20260623_0) | 523,715 | 검증셋 734(오판 케이스, gold 687) | PII 게이트 적용 | 687 (검증 gold) | — | **`rule3_last_low` 긍→부 보강(0623_02)**: 역량표지 7종(`우수·탁월·능동·원만·신속·열성·공정`) + 접미부정 가드(`~지 않/못`) + 반어 부정문맥어(`갑질·이기적·편향·우위 이용`·`불공정`) + `no_weakness` 저신뢰 게이트. additive·`perspective_service` | (검증셋만) | **한 줄짜리 장점이 끝문장이라 rule3로 무조건 부정화(긍→부 866)**를 발견·교정. dev 전수 재현(s=KoTE, 23초). 검증셋 gold 일치 **0.6→94.5%**, **부→긍 0**(전수 diff `n→p` 291=전부 긍정). 회귀 6종 통과. `eval/validation_rule3_rescue_260623.jsonl`, `result/accuracy_trend_260623.md §4차`. |
| 2026-06-24 | `data/23_단점.csv` (단점, KoTE 사전라벨, batch_20260623_0) + `data/23년 단점_eval.csv`(판정 패킷 judge, 128,800) | 505,011 | 검증셋 2,131(fixed 1,525 + 잔여 606) | PII 게이트 적용 | 1,525 (rule_evidenced negative) | — | **단점 맥락 부→긍 가드(0623_03)** `has_improvement_request`: 희망형(했으면/면 좋겠)·요함/요망·보완\|개선 요청·곤란(어려움), trap가드(중요함·"보완점 없음"·"어려움 극복"). positive_rescue 게이트 전용(is_no_weakness 미주입). additive·`perspective_service` | (검증셋만) | **0623_02 장점수정의 단점 적대검증**에서 발견: positive_rescue가 역량표지를 단점 맥락서 과구제 → 부→긍 11,039(기존 10,855 + 0623_02 187). 가드로 **−2,237**, 양방향 긍↔부 0(장점 94.5% 불변·하드 83.9→84.9·무작위 91.4 불변·장점 진짜 긍정트랩 0). 잔여 ~8,800은 맨 역량명사구·과잉·반어(필드/파서 트랙, 검증셋 606행 추적). 회귀 7종 통과. `eval/validation_cons_rule3_260624.jsonl`, `result/accuracy_trend_260623.md §5차`. |
| 2026-06-24 | `data/24년 장점.csv`(batch_20260624_1, 444,080) + `data/24년_단점.csv`(batch_20260624_0, 427,287) | 871,367 | **889,465**(문장 870,367 + 절 19,098) | 1,000 | 0 (약지도만) | weak 555,492(미확정) | (발굴만 — 규칙 미반영) | (검증셋만) | **자기실행 PASS·회귀 7종 ✅·긍↔부0(골든).** 단 **필드×판정 교차 감사**: 단점필드 **30.8%(131,566) 여전히 positive**(KoTE 31.4%에서 거의 안 줄음). 직접 재판정 → 부→긍 강후보 **30,613**(개선요청 표지, 트랩 제외). **핵심 구멍: 78%(24,019)가 `rule4_default`=KoTE 직접 긍정·무override** → 기존 개선요청 가드(positive_rescue 전용)가 **구조적으로 못 봄**. 긍→부(장점필드)도 짧은 긍정 트레이트 명사구로 존재(규모 gold 필요). **권고: 개선요청 게이트를 rule4_default 경로까지 승격(→neutral 강등, 트랩 보존) — 사용자 승인 후 additive+회귀.** 리포트 `result/sentiment_misclass_260624.md`·`result/pattern_mining_260624.md`. |

> **현재 차단(blocker)**: positive gold 0건(neutral/negative만 confirmed). 06-23 빌드로 **weak positive 468,241건 확보**(5배치 74만 문장, 미확정) → §2-3 사람 검토로 **confirmed positive gold 승격**이 파인튜닝 진입 1순위 선결. (리더십 trait gold·세부 승격은 군집(D1)+사람 후 — weak 후보는 grouped/hint로만 적재됨.)
> **규칙 마이닝 3회차(§2-5) 완료(2026-06-23) — 최대 정확도 개선**: 무작위 분포 손판정(70문장)에서 **3분류 정확일치 77%로 낮은 주범 = "약점 없음" 선언("보완점 없음"·"단점 없습니다")이 부정 오분류**(부정 라벨의 23.8% = 38,196건)임을 발견. KoTE가 '보완/단점'만 보고 부정, override는 긍정표지 없어 미구제. 규칙 **`is_no_weakness_declaration` → `no_weakness_neutral`**(약점명사+negation, 혼합은 negation-aware 게이트로 부정 보존, neg≥pos일 때만 발동=긍정문 불변) 신설. **실측: 부정 160,238→122,945(37,293 교정), 무작위 정확도 77%→91%, 긍↔부 2 유지(불변·중립만 산출).** 회귀 골든 추가. 벤치마크 `eval/accuracy_benchmark_random_260623.jsonl`. 정확도 추이 `result/accuracy_trend_260623.md`.
> **규칙 마이닝 2회차(§2-5) 완료(2026-06-23, 약점 배치)**: 약점 배치 부→긍 고neg(≥0.6) 표본 감사 → **지배 패턴 = "[긍정표지]+필요/요구"**(경청 필요·소통이 필요함·자세가 필요함·책임감 요구됨 = "더 ~하면 좋겠다" 건설적 비판). negation 인식 헬퍼 **`has_constructive_need`** 신설(관형형 '필요한'·'필요하지 않'·'필요 없'·'불필요'·'고객 요구' 전부 trap 제외) → `positive_rescue` 차단. **실측: positive→negative 10,786 + →neutral 2,009 = 12,795 교정, 무작위 25 표본 긍→부 trap 0**(diff 전수 검증). 부→긍 flip 29,071→23,929. 회귀 골든 추가. ⚠️ substring 목록(STRONG_NEGATIVE_PHRASES) 시도분은 '필요한' 관형 trap·bare '필요' 미포착으로 **헬퍼(경계+negation 인식)로 대체**.
> **검증용 데이터셋(2026-06-23)**: prelabel(KoTE)↔규칙 불일치 = '평가가 틀렸/어려운' 케이스를 `eval/validation_candidates_260623.jsonl`(**42,474 후보**: 긍↔부 flip·중립경계·저마진, 양쪽 라벨 보존)로 분리 — 향후 회귀·정확도 측정 기준(held-out, 사람 확정 대기). 파이프라인 단계로 배선(매 실행 자동 생성). 요약 `result/validation_set_260623.md`.
> **규칙 마이닝 1회차(§2-5) 완료(2026-06-23)**: 발굴 리포트의 결핍명사 786·부→긍 후보를 **표본 감사**(전수 flip 2,863 중 무작위 25 직접 판정). **정직한 결과: 현 파이프라인은 이미 flip의 ~90%+ 정확** — "786"은 대부분 노이즈/기처리였고, 진짜 부→긍은 산발적 소수. additive 가드 **`has_unnegated_deficiency`(결함술어 `소홀`, negation 인식)** 신설 → `positive_rescue` 차단. **실측: 부→긍 2건 교정, 신규 긍→부 0**(diff 전수 검증). ⚠️ `무관심`은 시도했으나 `업무관심도`(긍정) 부분문자열 trap으로 **긍→부 4건 유발 → 즉시 revert**(diff가 적발). 교훈: 단축 한글 substring 가드는 trap-prone → 광범위 추가 금지, 토크나이저 경계 인식은 후속. 회귀 골든 추가(`test_positive_rescue` catch/trap). `개인적인 ...에만 관심` 배타성은 trap 밀집(자기개발/본인이 떠맡아)으로 **보류**(표본 더 필요).

---

## §3. 진행 현황 한눈에

- ✅ 인프라: **단일 파이프라인 `dataset_pipeline.py`(자기실행+FAIL게이트)** + `export_jsonl.py` + `build_splits.py` + 비식별화/누수방지 게이트.
- ✅ 절 분리: `split_clauses`로 혼합극성 문장을 단일극성 절로 분해(데이터셋 빌드 전용, production 불변) → **혼합극성 deferred 해소 착수**.
- ✅ 리더십 weak LF: `trait_tree.json`(백본2+대그룹9+세부20) 기반 `build_leadership_candidates` 가동 — grouped 기본·micro 힌트·polarity 재게이트(긍↔부 0), weak-only. 택소노미 변경은 코드 아닌 JSON에서(node id 재정렬).
- ✅ 패턴 마이닝: `mine_patterns`로 데이터마다 규칙·패턴 후보 자동 발굴(RUNBOOK §2-5 자동화) → `result/pattern_mining_<date>.md`.
- ✅ 규칙 트랙(A. 대량): `hr_context_lexicon` negation 게이트 가동(긍↔부 오분류 0, 회귀 ✅). **상시 5단계로 데이터마다 재마이닝**.
- ✅ 케이스 트랙(B): 판정 패킷(`judgment_packet_service`, 추출→AI판정→in-place 삽입, 가명 안전) 가동 — 규칙 잔여를 1건씩 케이스 최대치로 추격(§2-1 step5.5·§2-2). 입력원 = `eval/validation_candidates_<date>.jsonl`. 테스트 `0617_01/test/test_judgment_packet.py`(5종 ✅).
- 🟡 대기(0617_05 §13 결정·🟡 승인): gold 컬럼 additive 마이그레이션 + `acquired_data.html` gold 확정 UI(P1).
- 🔴 선결: **positive gold 확보**(검토). 충족 전까지 P6(파인튜닝) 진입 불가.

### 택소노미 기준선 (2026-06-18 확정)
- **감정 스트림**: KoTE 44 + HR신규 ≤3 = **~47** (멀티라벨).
- **리더십 스트림**: 유형(trait)을 **안정 백본(positive/risk) + 합집합 대그룹 9 + split-only 단조 세분화**로 관리(희소 세부→대그룹 합집합 흡수, 데이터 성장 시 split 독립). 같은 게이트를 **사람(리더) 단위 유형 타이핑**에도 재사용. 현 6역량=거친 macro 1층. 외부 레포(OpenUM929/leadership)는 **스키마만 흡수·gold 비흡수**(코드북·약지도 LF·군집 가설·부정표지 마이닝 / 미래 리더십 전용모델 시드) — 활용 전략·정본 스냅샷 [`leadership/trait_library_ref.md`](leadership/trait_library_ref.md) §0, 택소노미 스펙 [`leadership/TRAIT_TREE.md`](leadership/TRAIT_TREE.md).

---

*본 문서는 상시 운영 RUNBOOK이다. "완료"로 닫지 않는다. 데이터가 들어올 때마다 §2를 반복한다: **A. 대량 규칙 재마이닝(자동) + B. 케이스 판정 패킷(AI/사람) + gold 확정** → §누적 로그. **두 트랙은 같은 데이터·같은 긍↔부 0 게이트에서 함께 자라며, 리더십 트랙도 동일 골격(§2-2)으로 진행한다.***
