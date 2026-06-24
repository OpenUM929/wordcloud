# 계획서 — 리더십 판단 AI (Leadership-Judge AI)

> 상태: Todo | 작성일: 2026-06-19
> 작업 유형: C (설계/아키텍처/데이터셋)
> 선행:
> - 외부 골격(사용자 조사 출처): `https://github.com/OpenUM929/leadership` (AGENTS v2.1, commit `49b261c`)
> - 로컬 정본 스냅샷(재클론 말고 이것 사용): `wordcloud_project/plans/_datasets/kote_finetune/leadership/trait_library_ref.md` (§0 활용전략·§3 micro 검증본)
> - 택소노미 스펙: `…/leadership/TRAIT_TREE.md` · 약지도 LF: `…/leadership/weak_labeling_lf.md`
> - 상위 로드맵: `…/kote_finetune/ROADMAP.md` (본 기획 = 그 **P7 "리더십 전용 검사 모델"** 의 독립 설계서)

> ⚠️ **문서 배치 규약**: 본 문서는 *일회성 설계 산출물*이라 `plans/2026/`에 둔다(완료 개념 있음). 데이터 누적·현황은 `_datasets/kote_finetune/`(RUNBOOK·ROADMAP). 둘을 섞지 않는다.

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-19 | 전체 | 최초 작성 — 향후 리더십 판단 AI 설계(외부 OpenUM929/leadership 골격 + 우리 코퍼스 gold 기반). KoTE 감정 파인튜닝과 별개 산출물. |

---

## §0. 한 장 요약 (비전문가용 — 먼저 읽으세요)

### 무엇을 만드나

> **인사평가에 적힌 문장을 읽고 "이 사람은 어떤 리더십 유형인가"(예: 코칭형·결단형, 또는 위험신호인 권위주의·회피형)를 자동으로 판정·프로파일링하는 전용 AI.** 기존 감정 분석(KoTE)과 **별개의 새 검사기**다.

```
 ┌──────────────────────────────────────────────────────────────┐
 │  감정 AI(KoTE)  :  "이 문장은 칭찬/불만인가?"        ← 이미 보유  │
 │  리더십 판단 AI :  "이 사람은 어떤 리더십 유형인가?" ← 이번 신규  │
 │                                                                │
 │  공유 자산: 같은 리더십 분류표(20유형) · 같은 정답 데이터(gold)   │
 │            · 같은 안전장치(긍정↔위험 오판 방지)                  │
 └──────────────────────────────────────────────────────────────┘
```

### 무엇으로 만드나 — 두 개의 재료

```
  ① 외부 조사 골격 (사용자 제공)        ② 우리 인사 코퍼스
     github.com/OpenUM929/leadership      (가명화된 실제 평가 문장)
     · 리더십 20유형 + 행동단위 125개         │
     · "긍정처럼 보이나 위험" 경계 사전        │
       │                                      │
       └──── 설계 재료(스키마)로만 ───┐  ┌──── 정답(gold)은 여기서만 ────┘
                                     ▼  ▼
                          [ 리더십 판단 AI ]
        ※ 외부 12,460 샘플은 "참고 골격"일 뿐 정답으로 쓰지 않음
          (생성 데이터·분포 편향 → 우리 정답은 실제 평가에서만)
```

### 지금 상황 (정직하게)

| 항목 | 상태 | 설명 |
|------|------|------|
| 리더십 분류표(20유형) | 🟢 확정 | 외부 골격 정본 채택 완료 |
| 안전장치(긍↔위험 게이트) | 🟢 가동 | 기존 규칙 재사용 가능 |
| 약지도 후보 라벨러 | 🟡 설계됨 | 코드 미배선(코퍼스 도착 시) |
| **핵심 부품: 문장→행동단위 추출기** | 🔴 **미구축** | AI의 심장. 별도로 만들어야 함(§4-B) |
| **정답 데이터(gold)** | 🔴 **0건** | 실제 인사 코퍼스 미반입 → 학습 불가 |

### 한 줄 결론

> **"분류표·안전장치·설계는 준비됐다. 그러나 이 AI는 ① '문장을 리더십 행동단위로 번역하는 부품'을 새로 만들어야 하고 ② 실제 정답 데이터가 모여야 학습할 수 있다. 그래서 '규칙 기반으로 먼저 가동 → 데이터 모이면 전용 모델 학습'의 2단계로 간다."**

이 작업은 **예산·내부망 LLM 사용·모델 학습 착수** 같은 상위 결정이 필요하므로(§10), 본 문서는 그 결정을 위한 설계 청사진이다.

---

## 1. 배경 및 목적

사용자가 조사한 리더십 유형·trait 체계(`OpenUM929/leadership`)를 토대로, **인사평가 문장에서 리더십 유형을 판정하는 전용 AI**를 만든다. 이는 KoTE 감정 파인튜닝(ROADMAP P0~P6, 감정 44 + 리더십 보조헤드)과 **별개의 독립 산출물**이며, ROADMAP §0-4·P7에서 "미래 가능성"으로만 기록해 둔 것을 **독립 설계서로 승격**한 것이다.

**왜 별도인가**: 감정(긍/부/중립)과 리더십 유형(20종)은 라벨 공간·추론 경로가 다르다. 특히 리더십은 **관찰 가능한 행동단위(micro)의 조합 패턴**으로 정의되는데, KoTE는 micro를 직접 산출하지 못한다(`trait_library_ref.md` §0-4 (d)). 따라서 전용 파이프라인이 필요하다.

---

## 2. 현황 실측 (재사용 자산 / 빈 부품)

### 2-1. 이미 있는 것 (재사용)

| 자산 | 위치(실측) | 본 AI에서의 역할 |
|------|-----------|------------------|
| 리더십 20-trait 정본 | `trait_library_ref.md` §3 (외부 `data/traits/trait_definitions.json`) | 출력 라벨 공간 |
| micro 125 + required/optional/forbidden 패턴 | `trait_library_ref.md` §3 | trait 추론 규칙(전문가 prior) |
| 안정 노드 트리 + 게이트 | `TRAIT_TREE.md` §3·§4 (백본2+대그룹9+세부20, split-only) | 출력 구조 + grouped/active |
| 긍↔부 게이트 | `hr_context_lexicon.py` `leadership_polarity`/`is_negation_praise`(:72/:111) | 극성 안전장치 |
| 6역량(거친 1층) | `leadership_analysis.py:80` `leadership_competencies` | 리더십 관련성 1차 필터 |
| 약지도 LF 설계 | `weak_labeling_lf.md` §4 (trait별 발화 seed) | 검토 가속/후보 라벨 |
| gold 스트림 | `leadership/leadership.jsonl` (append-only, 스키마 `TRAIT_TREE.md` §5-1) | 학습·검증 데이터 |
| 사람 단위 타이핑 설계 | `TRAIT_TREE.md` §4-T·§5-3 | 최종 출력(리더 프로파일) |

### 2-2. 없는 것 (새로 만들 부품)

1. **문장→micro 추출기** — 핵심. KoTE는 감정 44만 산출, micro(Mxx/Nxx)를 못 뽑는다. 이 번역기가 없으면 micro 조합 기반 trait 추론이 불가(§4-B).
2. **micro→trait 추론기** — 외부 `leadership_engine.py`의 required/optional/forbidden 로직을 우리 환경에 이식하거나 학습.
3. **전용 학습 데이터** — 실 인사 코퍼스 gold(특히 trait 라벨). 현재 0건(dev 미반입).
4. **(선택) 전용 분류 모델** — KoE5 768-dim 임베딩 + trait 분류 헤드(외부가 쓰는 방식). gold 충족 시.

### 2-3. 결론

분류표·안전장치·출력 구조는 있으나, **"문장을 리더십 행동단위로 번역하는 부품"이 없고 학습 정답이 0건**이다. → 규칙/패턴 기반으로 먼저 가동하고, 데이터가 쌓이면 전용 모델로 승격하는 단계 전략이 필수(§6).

---

## 3. 설계 원칙 (불변)

1. **긍↔부(=positive↔risk) 오분류 0** — 모든 trait 판정은 `leadership_polarity` 게이트 재통과. "강압적이지 않음"=칭찬을 권위주의로 오귀속 금지(`is_negation_praise`).
2. **외부는 스키마만, gold는 우리 코퍼스로만** — 외부 20-trait·125 micro·forbidden은 **설계 재료(코드북·규칙·prior)**. 외부 12,460 샘플은 gold·평가셋에 **절대 미혼입**(생성·균등분포·도메인갭). 사전학습/증강에만 조건부(△)·사용자 결정.
3. **추측 분류 금지** — trait active 승격은 우리 코퍼스 군집(`TRAIT_TREE.md` §6) + 게이트(distinct 문장 N·직원 M) 통과 후에만. 빈 trait는 대그룹 grouped 유지.
4. **단조·비교가능** — 트리는 split-only로 아래로만 성장. 사람 유형 비교는 안정 `leadership_node` id 조상관계로(연도 간 비교가능).
5. **프라이버시·내부망·O(n)** — 가명화 텍스트만, `src_hash`, 내부망 전용. 1.9만 규모에서 문장당 상수/선형. 외부 텍스트 비반입.
6. **사용자 고유 결정 에스컬레이션** — 전용 모델 착수·예산·내부망 LLM 도입·배포는 선점 금지, 권고+선택지(§10).

---

## 4. 시스템 아키텍처

### 4-1. 추론 파이프라인 (문장 → 리더 유형)

```
 [가명화 인사평가 문장]
        │
        ▼  ① 리더십 관련성 게이트  (약한 prior, 분류 아님)
   6역량 키워드 + hr_context_lexicon 표지 보유?  ──아니오──▶ 리더십 무관(제외)
        │ 예
        ▼  ② 문장→micro 추출기  ★신규 핵심 부품(§4-B)
   문장 → {M01-01, M11-01, …} / {N08-01, …}  (관찰 행동단위 멀티라벨)
        │
        ▼  ③ micro→trait 추론  (외부 required/optional/forbidden 패턴 §4-C)
   trait 후보 score = required 충족 + optional 가산 − forbidden veto
        │
        ▼  ④ 긍↔부 게이트 재검증  (leadership_polarity / is_negation_praise)
   극성 충돌(긍 trait ↔ 부정표지) → 보류·검토 큐(rule_hurt) / negation 칭찬 → risk 차단
        │
        ▼  ⑤ 트리 게이트  (TRAIT_TREE §4-A)
   세부 충분(문장≥N·직원≥M)? → active 세부 / 아니면 grouped 대그룹
        │
        ▼  ⑥ 사람 단위 집계  (TRAIT_TREE §4-T·§5-3)
   한 대상자의 문장 trait 분포 → 프로파일 벡터 + dominant_type + polarity_mix
        │
        ▼
 [리더십 유형 프로파일]  예: "방향·전략(결단형) 0.42 · 관계·소통 0.30 · 위험 0.05"
```

### 4-2. 핵심 부품 — 문장→micro 추출기 (§2-2 ①, 가장 중요)

micro(Mxx/Nxx) = "명확한 비전 제시", "적극적 경청", "직접 책임 전가" 같은 **관찰 가능한 행동단위**(외부 125종). 문장을 이 단위로 번역하는 3가지 구현안:

| 안 | 방식 | 장점 | 단점/제약 |
|----|------|------|-----------|
| **A. 규칙/표지 확장** | micro 이름→한국어 표면표지 사전(`weak_labeling_lf.md` §4 seed 확장) + 매칭 | 학습 불요·해석가능·즉시·내부망 안전 | 표현 다양성 한계(재현율↓), 표지 유지보수 |
| **B. 내부망 LLM few-shot** | micro 정의를 프롬프트로 문장→micro 추출 | 재현율↑·문맥 이해 | **내부망 LLM 필요(도입 결정)**, 비용·속도, 환각 검증 필요 |
| **C. 학습된 micro 분류기** | 문장 임베딩(KoE5 768) → micro 멀티라벨 헤드 | 정밀·빠름(추론) | **micro gold 다량 필요**(현재 0), 학습 인프라 |

> **권장 단계**: A(부트스트랩, 지금 설계 완료분 확장) → B/C(데이터·인프라 갖춰지면). A만으로도 ③④⑤⑥ 파이프라인 전체를 가동·검증할 수 있어 **무모델 프로토타입**이 가능하다.

### 4-3. micro→trait 추론 (§4-1 ③) — 외부 로직 이식

외부 `trait_definitions.json`의 각 trait는 `required`(AND)·`optional`(가산)·`hard_forbidden`(veto)·`soft_forbidden`(감점)·`k_trait`(context_weight)로 정의된다(`trait_library_ref.md` §3 전수 검증본). 추론:

```
 for trait in TRAITS(20):
     if any(hard_forbidden in micros):  score = 0   # veto = 긍↔부 안전
     score  = w_req * (required ∩ micros 비율)
            + w_opt * (optional ∩ micros 가산)
            - w_soft * (soft_forbidden ∩ micros)
     score *= k_trait                                # 약지도라 초기 1.0
 후보 = score 상위 + 극성 게이트 통과분
```

- 규칙/스코어 임계값은 **프로토타입 분포 확인 후 확정**(추측 금지, `weak_labeling_lf.md` §7 후속 ④).
- 겹침쌍(T11↔T08, T10↔T01/T06)은 군집 검증 전 **grouped 강제**(`TRAIT_TREE.md` §3 주의).

### 4-4. 출력 — 리더 유형 프로파일 (사람은 단일 라벨 아님)

`TRAIT_TREE.md` §5-3 스키마 사용: `profile[]`(node·level·weight·status) + `dominant_type` + `polarity_mix` + `evidence_count`. 한 사람은 **혼합형**으로 표현(가장 강한 축 + 받쳐주는 깊이 + 부차 축).

---

## 5. 데이터 전략 (gold·외부샘플 경계)

```
 외부 12,460 샘플 ──┐
   (생성·균등분포)   │ X gold/평가셋 (절대 금지)
                     │ △ 전용모델 사전학습·증강 한정(도메인갭 수용·사용자 결정·평가셋 격리)
                     └ O 스키마/패턴/forbidden 표지(코드북·규칙·prior)

 우리 인사 코퍼스 ───┐
   (가명화 실데이터)  │ O gold (유일한 정답 출처)
                     │   약지도 LF → 검토 큐 → 사람 확정 → leadership.jsonl
                     └ O 군집(trait 채택 근거, TRAIT_TREE §6)
```

- **평가셋(검증) 격리 불변**: 외부 샘플은 평가셋에 한 톨도 섞지 않는다(`trait_library_ref.md` §0-4 (a)). 성능 수치 신뢰의 전제.
- **gold 확보 경로 = ROADMAP P5와 공유**: 같은 검토 큐·같은 gold 스트림. 즉 본 AI의 학습 데이터는 KoTE 파인튜닝과 **동일 gold를 공유**(라벨만 trait).

---

## 6. 단계별 로드맵

```
  LP0 설계 합의(본 문서)
   │
   ▼
  LP1 규칙 부트스트랩  ── 문장→micro 추출기(안 A) + micro→trait 이식
   │   · 무모델, 기존 코퍼스 샘플로 프로토타입 검증(서버 불요·CSV/KoTE만)
   │   · 산출: trait 후보 스코어 + 극성 게이트 + 프로파일 시제품
   ▼          (실 코퍼스 도착)
  LP2 군집 검증 + gold 확보  ── TRAIT_TREE §6 군집으로 trait 채택, 검토로 trait gold
   │   · ROADMAP P5와 동일 루프(검토 큐·gold 스트림 공유)
   ▼
  LP3 추출기 고도화  ── 안 B(내부망 LLM) 또는 안 C(micro 분류기) — 인프라·gold 충족 시
   │   🔴 내부망 LLM 도입 = 사용자 결정
   ▼
  LP4 전용 분류 모델  ── KoE5 임베딩 + trait 헤드 학습(gold 검증셋·긍↔부 게이트·출처격리 전제)
   │   🔴 모델 학습 착수 = 사용자 결정(예산·배포)
   ▼
  LP5 운영·강화  ── 매년 다면평가 누적 → 군집 재실행 → split-only 심화(TRAIT_TREE §6-A)
                   규칙은 후처리 가드로 유지(모델이 규칙 대체 안 함)
```

| 단계 | 산출물 | 의존/트리거 |
|------|--------|-------------|
| LP0 | 본 설계 합의 | (현재) |
| LP1 | 무모델 규칙 파이프라인 + 프로토타입 리포트 | LP0 · `weak_labeling_lf.md` §4 seed |
| LP2 | trait 채택 근거 + trait gold 누적 | **실 코퍼스 도착** · 군집 |
| LP3 | 고재현율 micro 추출기 | LP2 gold · 🔴 내부망 LLM 결정 |
| LP4 | 리더십 전용 분류 모델 | LP3 · gold 검증셋 · 🔴 학습 착수 결정 |
| LP5 | 연간 강화 사이클 | LP4 · 다면평가 누적 |

---

## 7. 영향도 분석

| 단계 | 신규/변경(실측 기준) | 영향 | 안전장치 |
|------|---------------------|------|----------|
| LP1 | 신규 모듈(예: `leadership_judge.py`) + `weak_labeling_lf.md` §4 seed 설정화(`trait_tree.json`) | 신규 추론 경로 | 기존 `leadership_analysis`·`hr_context_lexicon` 시그니처 불변(재사용만) |
| LP1 | `hr_context_lexicon` 표지 보강 시 | 극성 분기 | append만 + 회귀(`test_leadership_polarity.py`) 통과 |
| LP2 | `leadership.jsonl` trait gold append | 데이터 누적 | append-only, 검토 확정만 |
| LP3 | (선택) 내부망 LLM 클라이언트 | 외부 의존 신설 | 가명화 텍스트만, 내부망, 환각 검증 |
| LP4 | 학습 파이프라인(별도) | 모델 산출물 | 규칙 후처리 가드 유지, 평가셋 격리 |

- 공통: dev 배치 불가(CSV·KoTE만), 서버 무단 실행 금지, `plans/`·gold 배포 제외, O(n).

---

## 8. 테스트/검증 계획

1. **긍↔부 게이트 회귀(상시)**: 표지/규칙 변경 전후 `0617_01/test/test_leadership_polarity.py` + `run_*_regression.py` — 오분류 0.
2. **LP1 프로토타입 정합성**: 외부 `trait_library_ref.md` §3 required/forbidden 대조 골든(예: required micro 충족→trait 후보, hard_forbidden→veto).
3. **추출기 평가**: 문장→micro 재현율/정밀도(외부 정의 대조 + 사람 표본). 외부 샘플은 **평가셋 미혼입**(우리 코퍼스 hold-out만).
4. **군집 검증(LP2)**: `TRAIT_TREE.md` §6 — 군집×trait×빈도×직원수×예문 리포트(`leadership/result/`), 채택은 20보다 적거나 많을 수 있음(정직).
5. **사람 유형 비교가능성**: 동일 `tree_version`·조상 노드 id 기준 연도 간 비교 검증(§4-B).

---

## 9. 리스크 및 제약

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 문장→micro 추출기 정밀도 부족 | trait 추론 전체 왜곡 | 안 A로 시작·해석가능 유지, gold로 점진 고도화, 사람 검토 게이트 |
| 외부 샘플 gold/평가셋 오염 | 성능 신뢰 붕괴 | 출처 분리·평가셋 격리(원칙 2·§5) |
| 추측 trait 채택 | 과적합·허위 유형 | 군집 근거 + 게이트 통과 후에만, 기본 grouped |
| 실 코퍼스 0건 | LP2+ 무기한 대기 | LP1 무모델 프로토타입으로 설계 선검증, gold 확보를 ROADMAP P5와 공유 |
| 내부망 LLM 미도입 | 안 B 불가 | 안 A/C로 대체 경로 유지(LLM은 선택) |
| 긍↔부 극성 오판 | 핵심가치 위반 | 모든 단계 `leadership_polarity` 재게이트, negation 칭찬 차단 |

**제약(불변)**: 서버 무단 실행 금지 · dev 배치 불가(CSV·KoTE만) · 외부 텍스트 비반입(스키마만) · append-only·비식별화·내부망 전용 · O(n).

---

## 10. 결정 필요 사항 (사용자 에스컬레이션)

1. **추진 여부·우선순위** — 본 AI를 KoTE 감정 파인튜닝(ROADMAP P6)과 병행할지, 그 이후로 둘지. (권장: LP1 무모델 부트스트랩은 저비용이라 선행 가능, LP3+는 P6 이후)
2. **문장→micro 추출기 노선** — 안 A(규칙) 우선 후, 고도화 시 안 B(내부망 LLM 도입 필요) vs 안 C(micro gold 다량 학습) 중 무엇? (내부망 LLM 도입은 별도 인프라 결정)
3. **외부 12,460 샘플 사용 범위** — 전용 모델 사전학습/증강에 한정 사용 허용 여부(평가셋 격리·도메인갭 수용 전제). 현재 권장: 보류, LP4 진입 시 재론.
4. **전용 모델 학습 착수 기준** — trait gold 최소 건수·검증셋 규모·예산(모델 학습은 사용자 고유 결정).

---

*본 기획서는 리더십 판단 AI의 설계 청사진(일회성 plans 문서)이다. 외부 골격은 `OpenUM929/leadership`(출처) → 로컬 정본 스냅샷 `trait_library_ref.md`로만 참조하며(재클론 금지), gold는 우리 인사 코퍼스에서만 생산한다. 누적·운영 실행은 `_datasets/kote_finetune/` RUNBOOK·ROADMAP과 연결된다.*
