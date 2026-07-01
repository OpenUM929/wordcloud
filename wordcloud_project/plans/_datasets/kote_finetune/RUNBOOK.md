# hr-kote-finetune — 데이터셋 누적 RUNBOOK (상시 운영)

> ⚠️ **이 문서는 "계획서"가 아니다. 완료(DN) 개념이 없다.** 데이터가 들어올 때마다 반복 수행하는 **상시 절차 + 누적 로그**다.
> 설계(스키마·택소노미·보안): `../../2026/0617_05_kote-finetune-data/0617_05_kote-finetune-data.md` · 폴더 규약: [`README.md`](README.md)
> 핵심 가치: **긍↔부 오분류 방지.** positive gold는 정식 스트림에 826 적립 완료(2026-06-30, D5) — 다음 공백 = **gold 증강**(미판정 후보 검토·weak 승격, 아래 §누적 로그 참조).

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

> **규칙 마이닝(§2-5, 2026-06-30) — 결핍·개선요청 rule4_default 누수 차단(0630_03)**: 06-24 기록한 "단점필드 30.8% positive·78%가 rule4_default 무override" 구멍을 닫음. 기존 결핍/개선요청 게이트는 `positive_rescue` 차단 전용이라 KoTE 긍정우세가 그대로 `rule4_default`로 긍정 통과하던 부→긍 누수. 신규 분기 **`improvement_request_neutral`**(pos>neg + 개선요청core/건설적필요/결핍 → **중립** 강등, 부정 미생성=긍↔부 0) + 트랩 가드(`필요 인물`=불가결 제외, `has_improvement_request`를 core/곤란 분리해 "어려움을 돕는" 긍정 트랩 제거). **전수 재생(weak_export_260624 870,367행): 단점 부→긍 24,384 수정·긍↔부 신규교차 0·장점 긍→중 583(0.13%, 다수 방어가능).** 검증 중 `필요 이상`(부→긍 3)·`필요+조사` 합성명사 가드(부→긍 1,031) 시도→전수 양방향이 적발→revert. 회귀 기존 6종+신규 6종 PASS. 판단: 사용자 제보 `보완 필요`=부정이나 긍↔부 0 우선·개선요청 화행=중립으로 **중립 채택**(완전 부정화는 후속). 계획서 `2026/0630_03_deficiency-framing-neutral`. → [[project_finetune_groups_are_speechacts]]·[[project_sentiment_core_value]].
> **규칙 마이닝(§2-5, 2026-06-30) — 결핍명사 substring 부정화 시도·폐기(0630_04)**: 0630_03이 닫은 `필요/소홀/개선요청` 외 잔존하던 결핍*명사*(`부족/미흡/결여/부재`) rule4_default 부→긍 누수를 *부정화*로 닫으려 시도. 신규 게이트 `has_deficiency_noun_critical`(negation·양보·조력·자기개선 가드) + `deficiency_noun_negative` 분기 + positive_rescue 차단 추가. **전수 재생(weak_export_260624 889,465행): 가드 2차 후에도 긍→부 263(장점 138) 잔존** → 긍↔부 0 불가 → **코드 전량 원복·Drop**. 원인: `부족/부재/미흡`은 술어가 극성을 정하는 **토픽 명사**(장점필드 138 위반=`부족한 점을 챙겨주심`·`부재 시 대행`·`부족함에도 솔선수범` 진짜 칭찬 / 단점 차단분에도 `부족한 부분 없음` 약점없음 오탐 다수). 필드조차 분리 못 함 → substring 불가. 중립 후퇴도 장점 진짜칭찬 138 훼손이라 미채택. **결론: 결핍명사 정확화는 극성표(술어 인식) 또는 파인튜닝(P6) 정공법으로만.** 계획서 `2026/0630_04_deficiency-noun-neg`·결과 `result/replay_result_260630.md`. → [[project_polarity_lexicon_field_skew]]·[[project_sentiment_core_value]].
> **정식 gold 적립(§2-1 step4 / D5, 2026-06-30) — "positive gold 0" 블로커 해소**: 진단 결과 positive gold는 *확정* 부재가 아니라 *적립* 누락이었다 — 사람 검토는 끝났으나(eval/ 4파일에 `human_decision` 1,977건, ai_reference/규칙과 19~64%만 일치=독립 판정) **정식 스트림 `emotion/emotion.jsonl`이 0행**(D5 미실행)이었다. `scripts/promote_gold.py`(append-only·id dedup·PII감사·비식별화 게이트)로 confirmed 1,976 적립(**positive 826·negative 397·neutral 753**, not_group 1·dup 1 제외, conflict 0·PII 0). emotions_gold에 hr_그룹(약점부재/개선요청/성장지향) 동반. ⚠️ eval 행에 직원ID 부재 → `src_hash=null`(직원단위 누수보호 N/A — baseline은 held-out이라 영향 제한, 필요 시 원데이터 조인으로 후속 복구). → **정식 positive gold 0 → 826.** 미판정 후보 `group_gold_candidates*`(1,518)는 0624_05 검토 UI로 추가 적립 대기. → [[project_field_signal_for_finetune]]·[[project_sentiment_core_value]].
> **gold 증강 검토큐 생성(B+C, 2026-06-30)**: `scripts/build_gold_review_260630.py`로 0624_05 UI용 검토큐 2종 생성(human_decision 공란, **독립 힌트 2개**=군집/필드 polarity + `human_label` ai_reference[이유 포함], 두 신호 불일치=고가치 대조). **(B) `eval/group_gold_review_260630.jsonl`** 미판정 후보 1,518(라벨러↔군집 일치 909/불일치 609). **(C) `eval/weak_positive_review_260630.jsonl`** weak positive 553,077 중 층화 899(단점∧긍 누수후보 / 장점 pos≥0.95 안전수확 / 저마진 경계 각 300). ai_reference는 JSON 정형(구 파일 surrogate 깨짐 교정). → 사람 검토(긍/부/중/그룹아님) 후 `promote_gold.py`로 정식 적립. **gold 확정은 사람(추측 분류 금지) — 큐만 제공.**
> **gold 긍↔부 오염 재감사(2026-06-30) — 파인튜닝 투입 전 안전검사**: `scripts/audit_gold_260630.py`(독립 스크린: human_label + 미부정 부정어/긍정표지) → 의심 88(부→긍 31·긍→부 57) **직접 재판정**. **위험 오염(부→긍·긍→부) 0건** — 88건 전부 ① HL 부분문자열 트랩(`고압`·`갈등 조정`·`부족한 점 개선`=진짜 긍정) ② 중립 경계(허용 방향)였다. 개별 재판정(사용자 결정)으로 **18건→neutral 정정**(발전지향·연성제안·칭찬우세 개선요청; 명시적 결여·과잉 `적극성 필요`·`과도`는 negative 유지=사용자 원의도). `apply_gold_corrections_260630.py`(백업+prev_gold/rev provenance). **정정 후 positive 822·neutral 771·negative 383, 긍↔부 0 불변.** 결론: gold 1,976 안전 — 2차 파인튜닝 투입 가능. 리포트 `result/gold_audit_260630.md`·감사기록 `eval/gold_corrections_260630.jsonl`. → [[project_sentiment_core_value]]·[[feedback_distrust_prelabels_reanalyze]].
> **AI 합의 silver 증강셋 빌드(2026-06-30) — human gold와 분리 계층**: gold 1,976이 작고 부정클래스 얇아(383), 다면평가 코퍼스(weak_export_260624 870,367)에서 **3신호 합의**(KoTE override == human_label == 필드 prior, 대조/양보 트랩 제외) 고정밀 구역만 추출. 가능량 471,750(pos 236k·neg 80k·neu 156k) 중 **균형 30,000(각 10k, 텍스트 중복제거·gold 중복제외·PII제외)** 채택 → `emotion/silver_consensus_260630.jsonl`. **별도 계층**(`label_source=ai_consensus`·`tier=silver`·`review_status=ai_auto`) — human gold 절대 비혼합, 학습 시 gold=앵커·테스트/silver=증강(가중치 분리). **표본 적대감사: 부→긍 0.00%·긍→부 0**(negative의 긍정표지 동반 1,387은 전부 진짜 부정=결여·개선요청 오탐, 무작위 15 확인). 한계: silver negative는 개선요청 neu/neg 경계 노이즈 포함(허용 방향, 안전). 하드존(불일치 45.8%=39.8만)은 **의도적 제외** — 거기는 사람 C큐 몫(silver≠사람검토 대체). `scripts/build_silver_260630.py`. → [[project_field_signal_for_finetune]]·[[project_finetune_groups_are_speechacts]].
> **객관성 측정 — 학습곡선(2026-06-30)**: gold held-out(baseline 398)에서 gold train 비율별 파인튜닝 → 정확도 **50%(790) 88.7% / 75%(1,184) 89.5% / 100%(1,579) 90.5%**, 긍↔부 오류 0~2. **단조 상승=데이터가 천장**(평탄화 없음 → 올바른 데이터 더 넣으면 오름). **단 silver 30k 증강은 정확도 90.5%→77.1% 추락·부→긍 1**(silver가 gold 20:1 압도 → 쉬운구역 분포쏠림 + 개선요청 neu/neg 경계노이즈가 사람테스트와 충돌). **→ 양(silver)≠개선, 질·하드샘플이 답**(사용자 직관 검증). `scripts/finetune_sentiment.py --frac/--silver`, `result/learning_curve_260630.jsonl`. ⚠️ finetune은 eval/ human_decision 직접 로드 → emotion.jsonl 감사정정(18건) 미반영(실 2차학습 전 배선 필요).
> **능동학습 1라운드 하드샘플 큐(2026-06-30) — 사용자 라벨링**: "실패 10%를 정답화해 재학습"이 최고 레버(1차 56→89.7도 불일치존 gold). 단 실패구역은 자동라벨이 자기오류 강화 → **사람 판정 전용**. 무라벨 코퍼스에서 실패 대리신호로 발굴(`scripts/build_hard_failure_queue_260630.py`, CPU·누수없음): **s1 부→긍 누수후보 250(★)·s2 긍→부 50·s3 불일치 150·s4 저마진 100 = 550** → `eval/hard_failure_review_260630.jsonl`(ai_reference 힌트·human_decision 공란). 사용자가 0624_05 UI로 긍/부/중 판정 → promote_gold 적립 → 재학습·측정(능동학습 루프). silver(쉬운구역)와 상보: 양은 silver, 정확도·핵심가치는 하드샘플.
> **능동학습 1라운드 결과(2026-06-30) — 진짜 병목=중립 규약 불일치**: 사용자가 하드샘플 550 직접 라벨(긍138·부308·중98·그룹아님6) → 정식 적립(emotion.jsonl 2,520, 사용자 라벨 정본·내 18 감사정정과 충돌분은 정정본 보존). 재학습 측정(baseline 398 held-out): **대조(gold 1,579) 90.2%·중립재현 0.647 vs +하드(2,123) 89.9%·중립재현 0.618** — 하드샘플이 baseline 미개선(긍↔부 양쪽 0 유지). 예측 diff: 회귀 11≈개선 10, **회귀 8/11이 gold=중립→긍/부**(`잘되었으면 좋겠다`→부·`적극적 마인드와 지식`→긍·`장점 보이지 않음`→부). **원인=데이터 양 아님, 중립경계 라벨규약 불일치**(사용자 하드규약 개선요청·희망=부정 ↔ baseline 옛규약 중립). 모델은 중립경계서 오류 맞바꿈. **→ 선결=중립 규약 1회 확정·전 gold 일관화 + 하드 held-out 테스트**(baseline은 다툼구역 과소표집=잘못된 자). 긍↔부는 전 구간 0=핵심가치 안전. `model_out_round1`·`model_out_ctrl`. → [[project_neutral_is_the_hard_class]]·[[project_finetune_data_ceiling]].
> **재정렬 + 필드 프리픽스 측정(2026-07-01)**: 사용자가 옛gold 중립경계 456 재판정(변경 39: 과긍정개선구 긍→중 19·놓친결여 중→부 13) → 정식스트림 반영(긍941·중876·부703). 개선요청은 blanket 아닌 **3분岐**(능동=긍/발전지향=중/결여=부, 사용자 판정)=문맥의존 실증. 필드프리픽스 실험(`finetune_field_exp_260701.py`, 정식스트림 학습·baseline+하드held-out): **필드無 baseline 91.2%/중0.712 → 필드有 93.2%/중0.712**(긍0.965→0.987·부0.937→0.968, 긍↔부0). **필드는 긍↔부 모호구(전문성 향상=[장/단]) 분리엔 효과(+2%p), 중립재현엔 무효**(0.712 불변). 하드held-out 89.8→88.9(108건 노이즈). **→ 필드프리픽스 채택가치 有, 그러나 남은 천장=중립 화행 인식**(필드·silver 다 무효). 다음: 중립화행 gold 확충 / 신규그룹 멀티라벨 헤드. → [[project_neutral_is_the_hard_class]]·[[project_field_signal_for_finetune]].
> **중립 화행 확충 결과(2026-07-01) — 결손 클래스 보강 성공**: 사용자가 중립큐 520 라벨(중185·부191·긍144) → **중립 185 복원**(raw 모델은 이 화행에 중립 0). 건강기원 16건 중립 정정·바람 3분류 규약(현재 업무결여 지적=부정 / 격려축원·개인안녕=중립) 확립. 정식 gold **3,040**(긍1,085·중1,077·부878, 균형). 재학습 측정(정식스트림·baseline+하드held-out): **하드존 중립재현 0.625→0.77~0.82**(+0.14~0.20)·하드 정확도 88.9→90.7%·baseline 92.4%·긍↔부 0. baseline 중립(~0.71)은 평평(대표셋 쉬운 중립은 천장, 확충효과는 하드 중립에서). 필드프리픽스는 중립gold가 주역되며 노이즈화. **→ 데이터 일관성+중립 화행 gold가 천장을 밀어올림. 중립은 아직 천장 아님(더 넣으면 여지).** 바람→긍정은 raw KoTE 문제였고 gold는 이미 교정됨(오적립 2건뿐, 방어가능). `scripts/build_neutral_queue_260701.py`·`finetune_field_exp_260701.py`. → [[project_neutral_is_the_hard_class]].
> **남은 차단(blocker)**: 정식 positive gold 822 확보+재감사 통과로 P6 진입 선결은 충족. 추가 강화 = ① 미판정 후보 1,518 사람 검토(B 큐) ② weak positive 표본 899 검토 승격(C 큐) → 둘 다 `promote_gold.py`로 적립. (리더십 trait gold·세부 승격은 군집(D1)+사람 후 — weak 후보는 grouped/hint로만 적재됨.)
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
- 🟡 감정 스트림 군집(D1, 2026-06-24): `scripts/cluster_emotion.py`(Track A, 무모델·O(n))로 **KoTE 미피복 부분코퍼스 484,119(전체 56%)** 멀티뷰 군집(24) → 3대 화행 수렴. 신규그룹 ≤3 후보 **G1 약점부재 선언·G2 개선요청·G3 역량서술**(기본 극성 neutral/positive, 긍↔부0 보호). `result/emotion_clusters_260624.md`·`result/emotion_new_groups_260624.md`. 계획서 `2026/0624_04_emotion-clustering`. **D4 완료(G1+G2)**: G2 개선요청 48,218이 현규칙 긍8,496/부26,906/중12,816 **3분열=누수 정량확증**, neutral 그룹화로 닫힘. 대표 AI판정·검증통과. **D4·D5 완료**: 표본 확대(gold 1,318·baseline 1,500), needs_human 679에 내 판정 `ai_reference` 동봉(사람 대조), **전체 176,483 weak 전파**(neutral 166,334/positive 9,627칭찬형/negative 326). 통합 리포트 `result/finetune_progress_260624.md`. 잔여=택소노미 문서반영·needs_human 사람확인·D6(파인튜닝, 사용자결정). Track B 인코더 미설치 보류.
- ✅ 규칙 트랙(A. 대량): `hr_context_lexicon` negation 게이트 가동(긍↔부 오분류 0, 회귀 ✅). **상시 5단계로 데이터마다 재마이닝**.
- ✅ 케이스 트랙(B): 판정 패킷(`judgment_packet_service`, 추출→AI판정→in-place 삽입, 가명 안전) 가동 — 규칙 잔여를 1건씩 케이스 최대치로 추격(§2-1 step5.5·§2-2). 입력원 = `eval/validation_candidates_<date>.jsonl`. 테스트 `0617_01/test/test_judgment_packet.py`(5종 ✅).
- 🟡 대기(0617_05 §13 결정·🟡 승인): gold 컬럼 additive 마이그레이션 + `acquired_data.html` gold 확정 UI(P1).
- ✅ **정식 gold 적립(D5) 완료(2026-06-30)**: confirmed 1,976 → `emotion/emotion.jsonl`(positive **826**·negative 397·neutral 753). `scripts/promote_gold.py`(append-only·dedup·PII감사). **"positive gold 0" 블로커 해소.** 후속 증강 = 미판정 1,518 검토 + weak 승격.
- ✅ **P6 1차 파인튜닝 완료(2026-06-24)**: 사람 gold 1,978 확보(needs_human 679+g4 100+field_conflict 800+baseline 399). KoTE 베이스→3분류 파인튜닝(학습 gold 1,579·비순환, 테스트 baseline 398 held-out). **전(규칙) 56.0%·긍↔부오류 10 → 후 89.7%·긍↔부오류 0**. 사람 gold가 규칙 천장(라벨러 ~63%·부→긍 누수)을 넘김. `result/finetune_report_260624.md`·`scripts/finetune_sentiment.py`·`model_out/`. ⚠️ gold는 `eval/_gold_backup/`에 백업(재생성 사고 2회→가드·백업 도입). 다음: 신규 배치 일반화 검증·weak 증강·신규그룹 멀티라벨 헤드.

### 택소노미 기준선 (2026-06-18 확정)
- **감정 스트림**: KoTE 44 + HR신규 ≤3 = **~47** (멀티라벨). **신규 3종 확정(2026-06-24, 0624_04 군집·미탐색 심화, ≤3 상한 충족)**: ① `hr_no_weakness_declaration`(약점부재, neutral) ② `hr_improvement_request`(개선요청, neutral) ③ `hr_growth_orientation`(자기개발/학습지향, **positive**, 신규=기존 규칙 없음·순환 아님, C7 근거·리더십 T14 대응). ①② 화행+neutral로 긍↔부 0 보호, ③ 검증된 선별기(정밀도~90%). weak: ①②176,483 + ③14,020 전파. G3(역량서술)은 안심/신뢰 기피복으로 보류. 미탐색 심화 결과 **더 큰 숨은 그룹 없음 확인**(`emotion_residual_findings_260624.md`). → [[project_finetune_groups_are_speechacts]].
- **리더십 스트림**: 유형(trait)을 **안정 백본(positive/risk) + 합집합 대그룹 9 + split-only 단조 세분화**로 관리(희소 세부→대그룹 합집합 흡수, 데이터 성장 시 split 독립). 같은 게이트를 **사람(리더) 단위 유형 타이핑**에도 재사용. 현 6역량=거친 macro 1층. 외부 레포(OpenUM929/leadership)는 **스키마만 흡수·gold 비흡수**(코드북·약지도 LF·군집 가설·부정표지 마이닝 / 미래 리더십 전용모델 시드) — 활용 전략·정본 스냅샷 [`leadership/trait_library_ref.md`](leadership/trait_library_ref.md) §0, 택소노미 스펙 [`leadership/TRAIT_TREE.md`](leadership/TRAIT_TREE.md).

---

*본 문서는 상시 운영 RUNBOOK이다. "완료"로 닫지 않는다. 데이터가 들어올 때마다 §2를 반복한다: **A. 대량 규칙 재마이닝(자동) + B. 케이스 판정 패킷(AI/사람) + gold 확정** → §누적 로그. **두 트랙은 같은 데이터·같은 긍↔부 0 게이트에서 함께 자라며, 리더십 트랙도 동일 골격(§2-2)으로 진행한다.***
