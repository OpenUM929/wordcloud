# KoTE 파인튜닝용 데이터셋 설계 (코퍼스 통합 구축)

> 상태: Hold(HOLD, 2026-06-18) — 설계+P0/P2/P5 인프라 완료. P1 이후(gold 컬럼 마이그레이션·확정 UI·JSONL export)는 §13 결정 6건 대기 로드맵. 코드 수정 대상 아님 | 작성일: 2026-06-17
> 작업 유형: 설계 (데이터셋 스키마 + 어노테이션 워크플로우 + 파인튜닝 포맷)
> 선행: `0617_01_emotion-rule-mining`(규칙/검증), `0615_10_corpus-refine-csv`(정제 CSV), `0617_02_group-bulk-move`(습득데이터 적재)
> ⚠️ 본 문서는 **일회성 설계**다(스키마·택소노미·보안 확정). 코드 변경은 "수행" 지시 후 착수한다(plan-mode 규칙).
> 📌 **데이터 도착 시 반복 수행하는 누적 절차·로그는 본 설계가 아니라 상시 운영 문서 [`../../_datasets/kote_finetune/RUNBOOK.md`](../../_datasets/kote_finetune/RUNBOOK.md)** 에서 관리한다(2026-06-18 분리). 설계=한번 합의 후 DN 가능 / 누적 실행=RUNBOOK(완료 개념 없음).

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-17 | 전체 | 최초 작성 — 신규 데이터 지속 수집을 KoTE 파인튜닝 데이터셋 구축과 통합하는 설계 |
| 2026-06-17 | 12, 13, 14(신설) | 검토 피드백 반영: 프라이버시 리스크 구체화, §14 보안 및 프라이버시 상세 추가, §13 보안 결정 질문 2건 추가 |
| 2026-06-17 | 14-2, 11(수행) | 결정 반영(범위=비-🟡, 라벨=3분류, 어노테이터=단독). §14-2 JSONL 위치 오기(`processed_data/`→`plans/_datasets/`) 정정. P2/P5 일부 수행: 독립 export/분할 스크립트 작성·실행(첫 스냅샷 713행). |
| 2026-06-18 | §6-L 신설 | **리더십 택소노미 확장 기준선 확정**(사용자 결정 "trait 중심"). 현 6역량(파생 1층)을 넘어 **리더십 유형(trait) ~18 스캐폴드** 채택, micro/macro는 후속. 외부 참조 레포(OpenUM929/leadership) = **설계 골격 참고만**(데이터·코드 비복제, 코퍼스 발굴로만 gold 채움). |
| 2026-06-19 | §6-L 정정 | **외부 레퍼런스 정본 확정 + micro 전수 검증**(사용자 확정). 레포 내 trait 정의 두 벌(20 vs 18) 중 **`data/traits` 20-trait**(정의서 `leadership_trait_system.md`+엔진 사용본) 채택 → 누락됐던 **전략실행형(T10)·공감형(T11)** 보강, 스캐폴드 ~18→**~20**. 실측 갱신: trait20·micro125(trait 참조본; 개별 178 공존)·macro80(이론 8). 20 trait 결정 micro label 전수 대조 결과 깨진 참조 0 — 검증본 [`trait_library_ref.md`](../../_datasets/kote_finetune/leadership/trait_library_ref.md). |
| 2026-06-24 | (상시 현황 갱신 포인터) | **"수집 단계=정상" 명문화 + 단점 적대검증 반영분**을 상시 로드맵에 기록: [`ROADMAP.md §5-3`](../../_datasets/kote_finetune/ROADMAP.md). 요지 — 현재 gold 0·평면 weak은 정체 아닌 **의도된 수집 단계**(수집→군집/분석으로 규칙성·공통성 발견→대표만 판정해 gold). P5/P6 보강: ① weak positive 62.6% 편중+단점→긍정 오염 → **균형·경계 우선 샘플링** ② **필드(장점/단점) 1급 피처화**(군집·학습) ③ raw 임베딩 단독 군집은 폴리세미 미분리 → 필드+규칙신호 동반. (본 설계 문서는 Hold·일회성이므로 상세는 ROADMAP에 둠 — 문서 배치 규약.) |

---

## 1. 목표

사용자 요구: **신규 데이터를 계속 수집하면서, 향후 KoTE 모델을 인사평가 도메인에 맞게 파인튜닝**할 수 있도록 데이터셋을 포괄적으로 설계한다. 핵심은 "지금 하는 규칙 마이닝/정제/검토 작업"이 그대로 **데이터셋 어노테이션 작업이 되게** 만들어 이중 작업을 없애는 것이다.

파인튜닝으로 달성하려는 두 가지:
1. **(교정)** KoTE가 인사평가에서 자주 틀리는 패턴(긍정 미검출, 무응답→부정, 부정의부정, 완곡부정)을 모델 자체가 학습.
2. **(감정 추가)** 인사평가 고유 신호(예: 평가불가/무응답, 완곡 비판 등)를 KoTE 감정 라벨 체계에 **데이터 주도로** 추가.

---

## 2. 현재 데이터 실측 (설계의 전제 — 추측 아님)

`data/new_260617.csv`(722행) 및 `acquired_sentences` 적재분 실측:

- 컬럼: `id, sentence_text, user_label, model_label, confidence, source_employee_id, source_evaluation_id, source_batch_id, sentence_index, context, created_at` (적재 함수 `import_acquired_sentences_csv` L2497).
- **`user_label == model_label` (불일치 0건), positive 라벨 0건.** → 현재 라벨은 **모델 출력의 복사본**이며 **사람 정답(gold)이 아니다.**
- 즉 **현 상태로는 파인튜닝 학습셋으로 쓸 수 없다.** gold 라벨 생성이 #1 임계 경로.
- 라벨은 **3분류 감정(positive/negative/neutral)** 뿐 — KoTE의 44 감정 라벨 단위 정답은 없음.

> 결론: "데이터를 모으는 것"과 "정답을 붙이는 것"은 별개다. 본 설계의 핵심은 **정답 생성(어노테이션)을 기존 작업 흐름에 녹이는 것**이다.

---

## 3. KoTE 모델 구조 사실 (`src/configs/emotion_config.json` 실측)

- **44개 감정 라벨 멀티라벨 분류기**(`num_labels: 44`, `type: text-classification`). 단일 라벨 아님 — 한 문장이 여러 감정에 동시 점수.
- `emotion_names`: 불평/불만, 환영/호의, … 안심/신뢰 (44개).
- `emotion_to_sentiment`: 44감정 → 0(긍정)/1(부정)/2(중립) 정적 매핑.
- 모델 경로: base=`../model/kote_for_easygoing_people`, fine_tuned=`fine_tune/fine_tuned_kote_large_model`(현 `use_fine_tuned:false`). → **파인튜닝 산출물 적재 슬롯이 이미 설정에 존재.**
- 추론 경로: `analyze_emotion(text)`(`emotion_analysis.py:300`) → `base_result.mapped.sentiment_scores{positive,negative,neutral}` + `top_3`(44 중 상위 3).

> 설계 함의: 파인튜닝 데이터는 **멀티라벨(멀티핫) 포맷**을 보존해야 base KoTE와 호환된다. 3분류 sentiment만으로는 KoTE 재학습이 불가 → 감정 라벨 어노테이션이 별도로 필요.

---

## 4. 설계 원칙 (반드시 준수)

1. **핵심 가치**: 긍↔부 오분류 방지. gold는 **극성(긍/부)에서 특히 신뢰**되어야 하며, 평가 지표도 긍↔부 혼동을 1순위로 본다.
2. **추측 금지**: 신규 감정 라벨은 **코퍼스에서 발굴**한다(아래 §6). 임의로 감정명을 만들지 않는다.
3. **프라이버시**: 인사평가 원천. 데이터셋은 **가명화된 텍스트만**(PseudonymManager / `pseudonym_mappings.enc`) 보관하고 `source_*_id`는 해시/제거. 내부망 전용 — dev 반출 금지(원데이터·배치 불가 제약과 동일).
4. **기존 작업 재사용**: `acquired_sentences` 테이블 + `refine_acquired_row`(KoTE+규칙 사전라벨, L2305) + `export/import CSV`(L2400/L2497) + 검토 화면 `acquired_data.html` 를 어노테이션 인프라로 그대로 활용.
5. **레거시 보호**: 기존 규칙/시그니처 불변. 데이터셋 컬럼 추가는 additive 마이그레이션으로만.

---

## 5. 데이터셋 스키마 (2계층 라벨, JSONL)

각 예시 1줄(JSONL, HuggingFace 호환):

```json
{
  "id": "as-000123",
  "text": "강압적이지 않고 자발적 참여를 유도함",   // 가명화 완료 단문
  "context": "…문서 전체(선택)…",
  "sentence_index": 2, "total_sentences": 4, "is_last": false,

  "sentiment_gold": "positive",                 // 사람 확정 3분류(필수 gold)
  "emotions_gold": ["존경", "안심/신뢰"],         // 사람/약지도 멀티라벨(44 + 신규후보)
  "emotions_new": ["__평가불가__"],              // §6에서 발굴된 신규 후보(있으면)

  "weak_kote_top3": {"존경":0.41,"환영/호의":0.22,"안심/신뢰":0.10},  // 모델 사전라벨(provenance)
  "weak_sentiment": "neutral",                  // 보정 전 KoTE 3분류
  "applied_rule": "negation_praise",            // 어떤 override가 발동했나(약지도 근거)
  "label_source": "human|rule|kote",            // gold 출처
  "review_status": "confirmed|pending|conflict",
  "annotator": "rev01", "annot_confidence": 0.9,
  "split": "train|val|test",
  "src_hash": "sha256(source_employee_id)"      // 누수방지 그룹키(원ID 비보관)
}
```

- **sentiment_gold**(3분류)와 **emotions_gold**(44 멀티핫)는 **별도 계층**. 초기엔 sentiment_gold만 채우고, 감정 멀티라벨은 점진 확충 가능.
- `applied_rule`/`weak_*`는 **약지도(weak supervision) 근거**로 보존 — 어떤 규칙이 어떤 정답과 결합하는지 추후 분석/검증에 사용.

---

## 6. 라벨 택소노미 — 44 유지 + HR 신규 후보 (데이터 주도 발굴)

직접 새 감정명을 만들지 않는다. 다음 절차로 **발굴**한다:

1. 코퍼스 전수에 `analyze_emotion` 실행 → 문장별 `kote_top3` 수집(이미 `refine_acquired_row`가 산출).
2. **KoTE 감정 × 사람 sentiment_gold 교차표** 작성 → `emotion_to_sentiment` 정적 매핑과 **실측 다수 정답이 어긋나는 감정** 식별(0617_01 §4-C와 동일 분석).
3. KoTE 어떤 라벨로도 잘 안 잡히는(top1 점수 낮고 산포된) 군집 → **후보 신규 라벨**. 예측되는 1순위 후보(데이터로 확정 전 가설):
   - `__평가불가/무응답__`: "잘 모르겠음/대면한 적 없음/내용없음" — 현재 KoTE는 "없음"(24)/저신뢰로 흩어짐. (0617_01 §13에서 137건 실측 존재 → 가장 유력.)
   - `__완곡비판__`: "개선의 여지가 있음/아쉬움" 류 — 완곡부정(STRONG_NEGATIVE_PHRASES)과 연결.
   - `__부정의부정(칭찬)__`: "강압적이지 않음" — negation_praise와 연결.
4. 신규 라벨은 **빈도·합의(IAA) 기준 충족 시에만 채택**. 미달이면 44 라벨 내 매핑으로 흡수.

> 채택된 신규 라벨은 멀티핫 차원을 44→44+k로 확장(파인튜닝 헤드 확장). base 가중치는 44에 대해 보존.

### 6-L. 리더십 택소노미 (별도 스트림, trait 중심 — 2026-06-18 확정)

리더십은 감정 44에 평면으로 더하지 않는다. **자기 다계층 라벨 공간**으로 분리(emotion 스트림과 leadership 스트림 분리 이유). 현재 코드의 6역량(`leadership_analysis.py:80` 커뮤니케이션·리더십·문제해결·팀워크·혁신·윤리)은 **거친 macro 1층**일 뿐이다.

**확장 구조(참조 골격, 3계층)** — 외부 레포 [`OpenUM929/leadership`](https://github.com/OpenUM929/leadership)를 **설계 참고**로만 사용(데이터·코드 비복제, 라이선스/프라이버시 불변):

> 레포 실측은 2026-06-19 검증 스냅샷(AGENTS v2.1, commit `49b261c`, **정본 `data/traits` 20-trait**) 기준 — 고정·검증본 [`../../_datasets/kote_finetune/leadership/trait_library_ref.md`](../../_datasets/kote_finetune/leadership/trait_library_ref.md).

| 계층 | 레포 실측(정본·검증) | 우리 채택 기준선 | 파이프라인 정합 |
|------|-----------|------------------|------------------|
| 유형(trait) | 20 (긍·균형 14 `T01–T14` / 리스크 6 `T101–T106`) | **~20 채택**(결단형·협업형·혁신형·코칭형·전략실행형·공감형… / 권위주의·자기애적·조작적…) | 문서/사람 단위 집계(`_generate_leadership_cell`) |
| 행동신호(micro) | 125 (긍67/부58, trait 참조 사전 — 깨진 참조 0 / 개별 178 공존) | **보류**(후속 확장) | 문장 단위(KoTE+override) |
| 역량군(macro) | 80 (긍48/부32, 이론 카테고리 8) | **보류**(현 6역량이 시드) | 묶음 집계 |

**원칙**:
1. **scaffold일 뿐 gold는 코퍼스 근거만** — 레포 18 trait를 그대로 채택하지 않고 빈 골격으로 두고, 인사평가 코퍼스에서 **실제 발굴·합의된 유형만** confirmed gold로 채운다(추측 금지).
2. 부정 trait(권위주의/조작적/회피형)는 기구현 `hr_context_lexicon.leadership_polarity` 게이트와 직결 — **긍↔부 오분류 방지가 라벨 추가보다 우선.**
3. additive — 감정 44 헤드 보존, 리더십은 **별도 헤드/다운스트림**(멀티태스크).

**카테고리 천장(갱신, trait 중심)**: 감정 `44 + HR신규 ≤3 = ~47` + 리더십 trait `~20`. micro(125 참조본/178 개별)·macro(80)는 데이터 충분 시 후속 확장.

> 🌳 **트리 구조 상세**: 리더십 trait는 평면 채택이 아니라 **2계층 트리(대그룹 9 ↔ 세부 20) + rollup**(희소 세부→대그룹 흡수, 데이터 성장 시 승격)으로 설계함. 택소노미 스펙은 데이터셋 구축물이므로 리더십 스트림에 위치 → [`../../_datasets/kote_finetune/leadership/TRAIT_TREE.md`](../../_datasets/kote_finetune/leadership/TRAIT_TREE.md).

---

## 7. 어노테이션 워크플로우 (기존 작업에 통합)

```
[수집] import_acquired_sentences_csv → acquired_sentences
   ↓
[약지도 사전라벨] refine_acquired_row (KoTE top3 + override 규칙 → weak_sentiment/applied_rule)
   ↓
[사람 검토] acquired_data.html 검토 뷰에서 sentiment_gold 확정 (+ 선택적으로 emotions_gold)
   ↓
[gold 락 + 분할] export → JSONL, split 부여
   ↓
[파인튜닝(향후)] fine_tuned_kote_large_model 학습 → emotion_config.use_fine_tuned 전환
```

**검토 우선순위 큐(효율 극대화 — 전수 검토 대신 고가치부터)**:
1. `rule_hurt`(보정이 정답을 틀리게 한 행) — 즉시 검수.
2. 극성 불일치: `weak_sentiment` ↔ 사람 직관이 갈리는 행(특히 부↔긍 경계).
3. 저마진 argmax(`|pos-neg|<0.05`) — 모델이 헷갈린 행.
4. 신규 분기 발동분(positive_rescue/negation_praise/no_response_neutral) **표본 감사**(전수 아님).
5. 나머지: 약지도 라벨을 잠정 gold로 두고 샘플 감사.

> 이 큐는 0617_01에서 이미 산출하는 플래그(`rule_hurt`, `kote_vs_truth`, `applied_rule`)를 그대로 사용 → 신규 분석 불요.

---

## 8. 품질·균형·분할

- **중복 제거**: "잘 모르겠습니다" 등 동일/유사 문장 다수 → 정규화 후 near-dup 캡(예: 동일 문장 최대 N개). 무응답류가 학습셋을 지배하지 않도록.
- **클래스 균형**: 코퍼스는 부정·중립 편중, **긍정 희소**. 긍정/소수 감정 오버샘플 또는 손실 가중. (현 데이터 positive 0 → 긍정 gold 확보가 선결.)
- **누수 방지 분할**: **동일 `source_employee_id`(→ src_hash) 문장이 train/test에 분산되지 않도록** 그룹 단위(GroupKFold) 분할. sentiment 층화 동시 적용.
- **IAA**: 2인 이상 검토 시 일치도(Cohen's κ) 기록, 불일치(`review_status=conflict`)는 학습 제외 또는 중재.

---

## 9. 파인튜닝 포맷 & 평가 지표

- **포맷**: 멀티라벨 BCE(멀티핫 emotions_gold) — base KoTE와 동일. 보조로 3분류 head(또는 `emotion_to_sentiment` 집계)로 sentiment 평가.
- **평가 1순위**: **긍↔부 혼동행렬** — false positive↔negative 0 지향(핵심가치). 그 다음 매크로 F1(감정), 무응답 검출 재현율.
- **회귀 가드**: 파인튜닝 후에도 0617_01의 골든/락셋 회귀가 통과해야 함(규칙 후처리와 모델이 충돌하지 않는지). 학습은 **규칙을 대체가 아니라 보완**.
- 학습/검증 산출물은 본 폴더 `result/`에 리포트로 기록.

---

## 10. 현재 작업과의 통합 (additive)

데이터셋 구축을 위해 필요한 **최소 추가**(수행 승인 시):
- `acquired_sentences` 테이블에 gold 컬럼 추가(additive 마이그레이션): `sentiment_gold`, `emotions_gold_json`, `review_status`, `annotator`, `annot_confidence`. (기존 `user_label`은 호환 유지.)
- `acquired_data.html` 검토 뷰에 gold 확정 UI(드롭다운/체크) — 기존 화면 확장(0617_01 §7 방향과 동일).
- export 함수에 JSONL 내보내기 추가(`export_acquired_sentences_refined_csv` L2400 옆 신규 함수, 기존 CSV 불변).
- 분할/중복제거/지표 산출 스크립트는 본 폴더 `test/`·`scripts/`에 신규(서버·배치 불요, CSV/DB만).

> 즉 **신규 데이터가 들어올 때마다** 사전라벨이 자동 부여되고, 검토 화면에서 gold만 확정하면 데이터셋이 누적된다.

---

## 11. 단계별 로드맵

| 단계 | 내용 | 산출 | 의존 |
|------|------|------|------|
| P0 | 스키마/택소노미 확정(본 문서 합의) | 본 설계 DN | 사용자 결정 §13 |
| P1 | gold 컬럼 마이그레이션 + 검토 UI | 스키마 확장 | P0 |
| P2 | 약지도 사전라벨 일괄(refine 재사용) | weak label 적재 | P1 |
| P3 | 우선순위 큐 기반 사람 검토 → gold 누적 | gold 데이터 증가 | P2 |
| P4 | 신규 감정 라벨 발굴/채택(§6) | 택소노미 확장 | P3(데이터량) |
| P5 | JSONL export + 분할 + 품질 리포트 | 학습셋 v1 | P3 |
| P6 | (향후) 파인튜닝 + 회귀/긍↔부 평가 | fine_tuned 모델 | P5 |

> 본 작업(0617_01 규칙/검증)은 P2~P3과 **동시 진행**된다 — 검토 1회가 규칙 검증과 gold 확정을 겸한다.

### 수행 현황 (2026-06-17)

비-🟡 범위로 P2/P5의 **스크립트 인프라**를 선행 수행(스키마·UI·`perspective_service.py` 미변경):

- `_datasets/kote_finetune/scripts/export_jsonl.py` — CSV→약지도 JSONL(§14-1 게이트). 첫 실행 722행→**713행**(PII 9행 격리).
- `_datasets/kote_finetune/scripts/build_splits.py` — 중복제거 + 누수방지 그룹분할(train554/val70/test89, **그룹 누수 0**) + 품질 리포트.
- **차단 발견**: 잠정 gold에 **positive 0건**(neutral 362/negative 351). weak_sentiment엔 positive 71. → P3(사람 검토로 긍정 gold 확보)가 학습 선결. P1(gold 컬럼+검토 UI, 🟡)은 **승인 대기**.

---

## 12. 리스크

- **gold 없음**: 현 데이터는 학습 불가. 사람 검토 없이는 진척 불가 → 검토 효율이 전체 속도를 결정(§7 큐로 완화).
- **무응답 편중**: 데이터셋이 "모르겠음"으로 쏠리면 모델이 중립 과다 예측 → §8 캡/균형 필수.
- **규칙 vs 모델 이중화**: 파인튜닝이 규칙과 충돌 가능 → 규칙은 후처리 가드로 유지, 회귀 가드 필수.
- **프라이버시/반출**: 내부망 전용. dev에는 가명화 CSV만. 데이터셋도 동일 취급.
  - `acquired_sentences` DB에 `source_employee_id`가 평문으로 저장됨 → JSONL export 시 반드시 `src_hash`로 변환, 원문 포함 금지.
  - CSV import 경로(`import_acquired_sentences_csv`)로 유입된 데이터는 가명화되지 않았을 가능성 있음(`sentence_text`에 실명/부서명 포함 가능). §14 JSONL export 시 가명화 검증 게이트 필요.
  - gold 어노테이션 UI(`acquired_data.html`)는 인사평가 원문을 노출함 → 접근 권한(로그인 세션)과 동일한 보안 수준 적용.

---

## 13. 결정 필요 사항 (수행 전 확인)

1. **감정 라벨 범위**: (a) **3분류 sentiment gold 먼저**(권고 — 즉시 가치, 긍↔부 교정) / (b) 처음부터 44 멀티라벨까지 동시 어노테이션(고비용) / (c) 둘 다 단계적.
2. **신규 감정 라벨 채택**: KoTE 44에 HR 신규 라벨을 **추가**할지(헤드 확장) vs 44 내 매핑 재정의로 흡수할지 — §6 발굴 결과 보고 결정.
3. **어노테이터**: 사용자 단독 vs 복수(IAA). 검토 UI 설계에 영향.
4. **gold 컬럼 마이그레이션 착수 여부**(🟡 `acquired_sentences` 스키마·`acquired_data.html` 변경 → 승인 필요).
5. 🔒 **JSONL export 시 `src_hash` 생성 및 가명화 검증 게이트**: §14에 상세. export 함수의 보안 체크리스트를 어느 수준까지 자동화할지 결정 필요.
6. 🔒 **gold 어노테이션 UI 접근 권한**: 현재 `acquired_data.html` 접근 제어가 로그인 세션만 있는지, 추가 제한(예: 관리자 전용)이 필요한지 확인.

---

## 14. 보안 및 프라이버시 상세

KoTE 파인튜닝 데이터셋은 인사평가 원문을 포함하므로, 저장·가공·반출 전 구간에서 엄격한 프라이버시 보호가 필요하다. 아래 원칙은 §4 설계 원칙 #3(프라이버시)을 구체화한 것이다.

### 14-1. JSONL export 시 비식별화 절차 (필수 게이트)

export 함수(`export_acquired_sentences_refined_csv` 옆 신규 함수, §10)는 JSONL 작성 전 다음을 반드시 수행한다:

```
1. sentence_text 가명화 확인
   - 현재 DB 저장값이 PseudonymManager 경유 가명화된 텍스트인지 확인
   - CSV import 경로로 유입된 데이터는 가명화되지 않았을 수 있으므로,
     source_kind != 'group_emotion' 등 bulk move가 아닌 행은 별도 감사 필요
   - 감사 실패 시 export 중단 또는 해당 행 제외

2. source_employee_id → src_hash 변환
   - 원문 source_employee_id는 JSONL에 절대 포함 금지
   - `src_hash = hashlib.sha256(source_employee_id.encode()).hexdigest()[:16]`
   - DB에는 원문 유지(어노테이션 화면 표시용), export 시점에만 변환

3. source_evaluation_id, source_batch_id 제거 (누수 방지)
   - src_hash로 대체, 그룹 분할(GroupKFold)의 키로만 사용

4. context 필드 가명화 확인 (선택 필드, 포함 시 §1과 동일 검증)
```

### 14-2. 데이터 보관 수준

| 데이터 | 위치 | 보관 기간 | 접근 제한 | 비고 |
|--------|------|-----------|-----------|------|
| `acquired_sentences` DB | 내부망 서버 | 영구 | 로그인 세션 | `source_employee_id` 평문 포함 |
| gold 마이그레이션 컬럼 | 동일 DB | 영구 | 동일 | additive, 기존 컬럼 불변 |
| JSONL 데이터셋 | `plans/_datasets/kote_finetune/` (배포 제외) | 영구 | 서버 파일 권한 | **비가명화 텍스트 포함 금지** · `processed_data/` 등 배포 포함 폴더에 두지 말 것 |
| KoTE 파인튜닝 모델 | 서버 로컬 | 영구 | 서버 파일 권한 | 모델 가중치에 데이터 기억 가능성 有 |
| 가명화 매핑 파일 | `pseudonym_mappings.enc` | 영구 | Fernet 암호화 | 복원/복호화는 PseudonymManager 전용 |

### 14-3. 어노테이션 보안

- `acquired_data.html`은 인사평가 원문을 그대로 표시 → **현 수준의 접근 제어(로그인 세션)** 로 충분한지 확인 필요.
- gold 확정 작업은 **데이터 조회만** (쓰기는 gold 컬럼 UPDATE). 기존 데이터 불변.
- 어노테이터 익명성: `annotator` 컬럼은 사용자 식별자(예: `rev01`)로 기록. 감사 추적 용도. 실제 신원과의 연결은 별도 관리.

### 14-4. 모델 파인튜닝 환경 보안

- 파인튜닝은 **내부망 서버에서만** 실행. 클라우드/외부 GPU 사용 금지.
- `emotion_config.json`의 `fine_tuned_path`는 서버 로컬 경로만 허용.
- 학습/검증 산출물(result/ 리포트)은 **가명화 통계만** 포함, 원문 문장 미포함.
- golden test set 회귀 검증(`test/`)도 동일 — 원문 없이 csv/jsonl만 보관.

### 14-5. 프라이버시 리스크 매트릭스

| 리스크 | 심각도 | 완화 방안 | 상태 |
|--------|--------|-----------|------|
| CSV import 문장 미가명화 | **높음** | §14-1 export 게이트 감사, 미가명화 행 제외/별도 마킹 | 🔴 설계 단계 |
| `source_employee_id` 유출 | **높음** | src_hash 변환, JSONL 포함 금지 | 🟢 설계 반영 |
| context 필드 개인정보 누수 | 중간 | §14-1 게이트 동일 적용 | 🟡 export 구현 시 |
| 파인튜닝 모델에 데이터 기억 | 낮음 | differential privacy 미적용(현 단계 불필요 판단), 내부망 전용으로 리스크 허용 | 🟢 결정 필요 |
| JSONL 반출(dev) | **높음** | **JSONL 파일의 dev 반출 금지.** 검증은 내부망 서버에서만. | 🔒 본 계획서 제약 |
