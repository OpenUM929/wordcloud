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

| 단계 | 작업 | 도구/위치 | 산출 |
|------|------|-----------|------|
| 1. 반입 | CSV 업로드 → `acquired_sentences` 적재 | `acquired_data.html` "데이터 가져오기" → `POST /api/perspective/acquired-sentences/import` (`perspective_service.import_acquired_sentences_csv`) | 적재 행 |
| 2. 약지도 사전라벨 | KoTE top3 + 발동 규칙/리더십 극성 자동 부여 | `perspective_service.refine_acquired_row` (내보내기/검토 화면에서 재계산) | weak_sentiment, applied_rule |
| 3. 사람 검토(gold) | 우선순위 큐로 `sentiment_gold`(+선택 `emotions_gold`/`leadership_gold`) 확정 | `acquired_data.html` 검토 뷰 | `review_status=confirmed` |
| 4. 스트림 append | **confirmed gold만** 정식 스트림에 append-only 기록 | `emotion/emotion.jsonl`, `leadership/leadership.jsonl` | gold 누적 |
| **5. 규칙 재마이닝** | **신규 데이터로 케이스바이케이스 규칙도 함께 강화**: ① deferred 규칙(혼합극성 등, [`0617_01`](../../2026/0617_01_emotion-rule-mining/0617_01_emotion-rule-mining.md) §0-A) 표본 충족 여부 재확인 ② 신규 오분류 패턴(`rule_hurt`·저마진·검토 피드백)에서 표지/분기 도출 → `hr_context_lexicon`(`POSITIVE_MARKERS`/`NEGATIVE_MARKERS`/분기)에 **additive append** ③ 회귀 재검증 통과 확인 | `src/modules/hr_context_lexicon.py`(append) + `0617_01/test/run_*_regression.py`, `test_leadership_polarity.py` | 신규 표지/분기 + 회귀 ✅ |
| 6. 스냅샷·분할 재생성 | 비식별화 게이트 + 누수방지 분할 + 품질 리포트 | `python scripts/export_jsonl.py` → `python scripts/build_splits.py` | `*.jsonl`, `result/*_report_<date>.md` |
| 7. **누적 로그 갱신** | 본 RUNBOOK §누적 로그에 1행 추가 | (이 파일) | 진행/공백 가시화 |
| 8. 핵심가치 점검 | 긍↔부 오분류 0 + positive gold 확보 추세 확인 | `result/split_report_<date>.md` | 게이트 통과 |

> 🔁 **규칙 트랙도 상시 루프다.** 규칙 마이닝은 `0617_01`(DN)에서 끝난 게 아니라, **데이터가 올 때마다 5단계로 재실행**된다(표본 부족으로 보류했던 deferred 규칙이 충족되면 그때 추가). 규칙은 파인튜닝(D5) 후에도 **후처리 가드로 유지**(`0617_05` §9·§12) — 모델이 규칙을 대체하지 않는다. 단, **추측으로 표지를 늘리지 않는다**: 코퍼스 오분류 근거가 있을 때만 append(`0617_01` §5-2 원칙).

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

> **현재 차단(blocker)**: positive gold 0건(neutral/negative만). §2-3 사람 검토로 **긍정 gold 확보**가 파인튜닝 진입의 1순위 선결 과제.

---

## §3. 진행 현황 한눈에

- ✅ 인프라: import 경로 + `export_jsonl.py` + `build_splits.py` + 비식별화/누수방지 게이트.
- ✅ 규칙 트랙: `hr_context_lexicon` negation 게이트 가동(긍↔부 오분류 0, 회귀 ✅). **상시 5단계로 데이터마다 재마이닝**(deferred: 혼합극성 — 표본 충족 대기).
- 🟡 대기(0617_05 §13 결정·🟡 승인): gold 컬럼 additive 마이그레이션 + `acquired_data.html` gold 확정 UI(P1).
- 🔴 선결: **positive gold 확보**(검토). 충족 전까지 P6(파인튜닝) 진입 불가.

### 택소노미 기준선 (2026-06-18 확정)
- **감정 스트림**: KoTE 44 + HR신규 ≤3 = **~47** (멀티라벨).
- **리더십 스트림**: 유형(trait)을 **안정 백본(positive/risk) + 합집합 대그룹 9 + split-only 단조 세분화**로 관리(희소 세부→대그룹 합집합 흡수, 데이터 성장 시 split 독립). 같은 게이트를 **사람(리더) 단위 유형 타이핑**에도 재사용. 현 6역량=거친 macro 1층. 외부 레포(OpenUM929/leadership)는 **스키마만 흡수·gold 비흡수**(코드북·약지도 LF·군집 가설·부정표지 마이닝 / 미래 리더십 전용모델 시드) — 활용 전략·정본 스냅샷 [`leadership/trait_library_ref.md`](leadership/trait_library_ref.md) §0, 택소노미 스펙 [`leadership/TRAIT_TREE.md`](leadership/TRAIT_TREE.md).

---

*본 문서는 상시 운영 RUNBOOK이다. "완료"로 닫지 않는다. 데이터가 들어올 때마다 §2(gold + 규칙 재마이닝) → §누적 로그를 반복한다. **gold(데이터셋)와 규칙(케이스바이케이스)은 같은 루프에서 함께 자란다.***
