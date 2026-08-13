# hr-kote-finetune — 향후 개발 통합 로드맵 (상시 현황)

> ⚠️ **이 문서는 "계획서"가 아니다.** RUNBOOK과 같은 **상시 현황·로드맵** 문서다(완료 DN 개념 없음).
> 일회성 설계/구현 산출물은 `plans/2026/`(0617_01·0617_05)에, **누적 실행·현황은 본 폴더**에 둔다(CLAUDE.md "📦 데이터셋 누적 지침" 규약).
> 갱신: 2026-06-24 · 진입점: [`RUNBOOK.md`](RUNBOOK.md) 🧭 앵커에서 연결
> 🔺 **현행 스냅샷은 [`result/status_260715.md`](result/status_260715.md)** (이전 [`status_260707.md`](result/status_260707.md)) — 본 문서 §0 이하의 로드맵 신호등은 낡았다. **현재 상태: 배포 7/8(seed45) 동결.** 정확도 향상 목적의 gold 누적·모델 확대는 **천장 2회 확증으로 중단**(대표셋 97.7%·중립경계 76.5%·긍↔부 0). **남은 유일 실험 = 도메인 이어사전학습(DAPT, 원문 270만·라벨 불요)** — 채택 근거·명칭 대응은 [`result/MODEL_SELECTION_REPORT_260715.md`](result/MODEL_SELECTION_REPORT_260715.md). 방향 파악은 이 두 문서 우선.
> 관련:
> - [`RUNBOOK.md`](RUNBOOK.md) — 상시 운영 절차(반복 실행 체크리스트·누적 로그)
> - [`leadership/`](leadership/) — trait_library_ref.md · TRAIT_TREE.md · weak_labeling_lf.md
> - `plans/2026/0617_05_kote-finetune-data/` (데이터셋 설계 정본, 보류) · `plans/2026/0617_01_emotion-rule-mining/` (규칙 마이닝, DN)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-19 | 전체 | 최초 작성 — 지금까지 기획·구현분을 향후 개발 로드맵으로 통합 |
| 2026-06-19 | §0 추가, §3~§6 시각화·구현 디테일 보강 | 비전문가용 요약 + ASCII 다이어그램/트리 + 단계별 실제 구현 방법(DDL·코드·테스트)까지 확장 |
| 2026-06-24 | §0 결론 주석 + §5-3 신설 | "gold 0=정체" 오독 차단(수집→군집→대표gold 순서 명문화) + 단점 적대검증 반영(불균형·오염 인지, 필드 1급 피처, 군집 폴리세미 주의) |
| 2026-07-07 | 헤더 🔺 현행 포인터 | status_260707.md 스냅샷 연결 — 신호등 낡음 고지(positive gold 826·8c 파인튜닝 가동·필드신호 완료). 상세 갱신은 status 보고서에 위임 |
| 2026-07-15 | 헤더 🔺 현행 포인터 | status_260715.md·MODEL_SELECTION_REPORT 연결 — 배포 7/8 동결·천장 2회 확증·정확도 목적 누적 중단. 남은 레버=DAPT(원문 270만) |

---

## §0. 한 장 요약 (비전문가용 — 먼저 읽으세요)

### 우리가 만드는 것

> **한국어 인사평가 글을 읽고 "칭찬인지 불만인지, 어떤 리더십 유형인지"를 자동으로 판별하는 AI**를 우리 회사 인사평가에 딱 맞게 길들이는(파인튜닝) 작업입니다. 기반 모델은 KoTE(한국어 감정 44종 분류기)입니다.

쉽게 비유하면 — **"AI 요리사를 우리 회사 입맛에 맞게 훈련시키는 일"** 입니다.

```
 ┌─────────────────────────────────────────────────────────────┐
 │  비유: AI 요리사 길들이기                                     │
 │                                                              │
 │   ① 주방·도구  →  ② 재료(예시 데이터)  →  ③ 사람이 간 봄  →  ④ 훈련 │
 │     (인프라)        (코퍼스 수집)        (gold 확정)      (파인튜닝) │
 │                                                              │
 │   ✅ 완성         🟡 모으는 중           🔴 핵심 부족      ⏳ 대기   │
 │                  (긍정 예시 0건)        ← 지금 여기 막힘            │
 └─────────────────────────────────────────────────────────────┘
```

### 지금 상황을 신호등으로

| 구분 | 상태 | 한 줄 설명 |
|------|------|-----------|
| 데이터 처리 공장(인프라) | 🟢 완성 | 데이터 넣고 → 자동 분류 → 검토 → 저장 → 학습용 분할까지 라인 완비 |
| 규칙(임시 판별기) | 🟢 가동 | "강압적이지 **않다**"=칭찬을 정확히 구분. 긍정↔부정 헷갈림 0건(자동 테스트 통과) |
| 리더십 유형 분류표 | 🟢 확정 | 20가지 리더십 유형 체계 확정(긍정 14 + 위험 6) |
| **긍정 예시 데이터** | 🔴 **막힘** | 학습에 꼭 필요한 "칭찬" 정답 데이터가 **0건** → 이게 풀려야 다음 단계 가능 |
| AI 파인튜닝 | ⚪ 대기 | 위가 풀리면 착수(예산·승인은 상사 결정 사항) |

### 한 줄 결론

> **"공장과 도구는 다 지었고, 안전장치(긍정↔부정 오판 방지)도 검증됐다. 이제 필요한 건 사람이 검토해 모으는 '긍정 정답 데이터'다. 그것만 모이면 곧바로 AI 훈련에 들어간다."**

남은 일의 대부분은 새 코드가 아니라 **데이터 수집·검토**이며, 코드 쪽은 이미 설계가 끝나 "데이터가 도착하는 순간" 켜면 되는 상태입니다.

> ⚠️ **"긍정 gold 0건 🔴"을 "고장/정체"로 읽지 말 것.** 이는 **설계상 의도된 수집 단계**다(§5-3).
> 순서가 **수집 먼저 → 군집/분석으로 규칙성·공통성 발견 → 대표만 판정해 gold 확정**이므로, 지금 평면 weak 적립(756k, gold 0)은 정상 진행이다. 🔴는 "다음 게이트(P5)에 아직 진입 안 함"이지 "막혀 부서짐"이 아니다.

---

## 1. 배경 및 목적

지난 기간(0615~0619) 동안 **KoTE 인사평가 도메인 파인튜닝**을 목표로 다음을 설계·구현했다.

- 데이터셋 누적 인프라(import → 약지도 → 검토 → append → export → split)와 상시 운영 RUNBOOK
- 감정·리더십 **규칙 트랙**(`hr_context_lexicon` negation 게이트 + 외부 forbidden 8코어)
- **리더십 trait 택소노미 정본**(20-trait: 긍정·균형 14 + 리스크 6)과 백본/대그룹 스캐폴드
- 약지도 라벨링 함수(LF) 설계와 **positive-negation 게이트 설계(§9, 구현 보류)**

이 정보들은 RUNBOOK·leadership/*.md·메모리에 분산 기록되어 있다. 본 보고서는 이를 **단일 향후 개발 로드맵**으로 통합하여 ① 무엇이 가동 중이고 ② 무엇이 차단(blocker)이며 ③ 어떤 순서로 어떻게 구현하는지까지 한 장에서 추적·실행 가능하게 한다.

> 본 보고서는 **로드맵 + 구현 지침** 문서다. RUNBOOK(완료 개념 없는 상시 절차)을 대체하지 않고 보완한다. 반복 실행 절차는 RUNBOOK §2를 따른다.

---

## 2. 전체 그림 (시스템 한눈에)

### 2-1. 데이터 흐름 (CSV 한 줄이 학습 데이터가 되기까지)

```
 [내부망 원데이터]                     ※ dev에는 원데이터 반입 금지 — CSV만
        │  (가명화 완료 텍스트만)
        ▼
 ┌──────────────┐   ①반입        ┌─────────────────────┐
 │  코퍼스 CSV   │ ────────────▶ │  acquired_sentences │  (SQLite 테이블)
 └──────────────┘  import_acquired│  sentence_text/context│
                   _sentences_csv │  /user_label …       │
                                  └──────────┬──────────┘
                                             │ ②약지도 사전라벨(자동)
                                             ▼
                      refine_acquired_row()  ─ perspective_service.py:2334
                        ├─ KoTE top3 + 감정 보정     → weak_sentiment
                        └─ (신규) 리더십 LF          → weak_leadership
                                             │
                                             ▼ ③사람 검토 (우선순위 큐)
                      ┌────────────────────────────────────┐
                      │ 3-tier 큐  (acquired_data.html)     │
                      │ 1순위: rule_hurt(보정이 틀린 행)    │
                      │ 2순위: 긍↔부 경계 불일치            │
                      │ 3순위: 저마진/저신뢰                │
                      └───────────────┬────────────────────┘
                                      │ ④gold 확정(사람만)
                                      ▼
                  sentiment_gold / leadership_gold  (review_status=confirmed)
                                      │ ⑤append-only 기록
                                      ▼
              emotion/emotion.jsonl   ·   leadership/leadership.jsonl
                                      │ ⑥내보내기 + 누수방지 분할
                                      ▼
              export_jsonl.py → build_splits.py → train/val/test
                                      │ ⑦임계 도달 시
                                      ▼
                            ★ KoTE 파인튜닝 + 규칙은 후처리 가드로 유지
```

### 2-2. 어디까지 됐나 (위 흐름에 신호등 겹쳐보기)

```
  ①반입 🟢 ─ ②약지도 🟡(LF 미배선) ─ ③검토 🟡(UI 대기) ─ ④gold 🔴(긍정 0)
        ─ ⑤append 🟢 ─ ⑥분할 🟢 ─ ⑦파인튜닝 ⚪(gold 대기)

  🟢 완성/가동   🟡 설계완료·구현대기   🔴 차단(blocker)   ⚪ 후속
```

**핵심 병목 = ④ gold(특히 positive 0건).** ②③은 설계가 끝나 "데이터 도착 시 켜기"만 남았고, ④가 풀려야 ⑦로 간다.

---

## 3. 핵심 자산 ① — 리더십 유형 분류표 (택소노미)

> 정본: `leadership/TRAIT_TREE.md` · `trait_library_ref.md`(외부 `OpenUM929/leadership` commit `49b261c`, **스키마만 흡수·gold 비흡수**)

### 3-1. 트리 구조 (20-trait)

```
리더십 유형 (20)
│
├─ [긍정·균형 백본]  T01–T14  ── 5개 대그룹으로 묶음
│   │
│   ├─ 방향·전략       ─ T01 결단형 · T05 분석형 · T09 비전제시형
│   ├─ 관계·소통       ─ T02 협업형 · T07 코칭형 · T08 감정지능형 · T11 공감형*
│   ├─ 실행·성과       ─ T04 위기대응형 · T06 실행형 · T10 전략실행형*
│   ├─ 혁신·학습       ─ T03 혁신형 · T14 학습민첩형
│   └─ 윤리·신뢰       ─ T12 균형형 · T13 윤리적용기형
│
└─ [리스크 백본]      T101–T106  ── 4개 대그룹
    │
    ├─ 회피·무책임     ─ T101 회피형
    ├─ 권위·통제       ─ T102 권위주의 · T106 기복(과잉통제)형
    ├─ 정직성 위반     ─ T103 정직성위반형
    └─ 자기중심·조작   ─ T104 자기애적 · T105 조작적

  * 겹침쌍 = 군집 검증 전 무조건 grouped(세부 자동분류 금지):
      T11 공감형  ↔  T08 감정지능형
      T10 전략실행형 ↔ T01 결단형 / T06 실행형
```

### 3-2. 운용 원칙 — "큰 묶음 먼저, 쪼개기는 근거 있을 때만"

```
   현재(데이터 적음)              데이터 성장 후
   ┌──────────────┐              ┌──────────────┐
   │  대그룹(9)    │   split만    │  세부 trait  │
   │  로만 분류    │ ───단조───▶ │  으로 독립    │
   └──────────────┘   (근거 시)   └──────────────┘
   · 빈 세부 leaf = 대그룹에 흡수(추측 분류 금지)
   · 합치기(merge) 없음 = 한번 쪼갠 건 되돌리지 않음(단조성)
   · 현 운용 = 6역량(leadership_analysis.py:80)이 거친 1층
```

> 외부 레포 20-trait은 **약한 참고(prior)**일 뿐, 우리 gold는 **우리 인사 코퍼스 군집**으로만 채운다(원칙 2). 그들 12,460 샘플은 gold로 흡수 금지.

---

## 4. 핵심 자산 ② — 규칙 판별기 (긍↔부 안전장치)

> 구현 완료: `src/modules/hr_context_lexicon.py` · 테스트 `0617_01/test/test_leadership_polarity.py`

### 4-1. 왜 규칙이 필요한가 (한 문장 예시)

```
  "수직적 의사소통과 강요로 문제해결"
        │
        ├─ 단순 키워드만 보면 → '소통/문제해결' 때문에 [강점]으로 오판 ❌
        └─ 우리 규칙 → '강요/수직적' 부정표지 인식 → [약점] 정답 ✅

  "강압적이지 않음"
        │
        ├─ 단순 부정표지만 보면 → '강압' 때문에 [약점]으로 오판 ❌
        └─ 우리 규칙 → 뒤의 '않음'(negation) 인식 → "부정의 부정=칭찬" → [강점] ✅
```

### 4-2. 현재 판정 로직 (가동 중, 회귀 ✅)

```
 leadership_polarity(text)            ── hr_context_lexicon.py:72
 ─────────────────────────────────────────────────────────
  for 부정표지 in NEGATIVE_MARKERS(:45):     ← 외부 8코어 포함(:51-56)
        뒤 14글자에 negation(않/없/안…) 있나?
            있음 → "부정의 부정 = 칭찬"  (has_negated_praise)
            없음 → 진짜 부정             (has_real_negative)

  판정 우선순위:
     ① has_real_negative  → 'negative'   (가장 보수적)
     ② 칭찬 or 긍정표지     → 'positive'
     ③ 표지 없음           → 'neutral'    (호출부 동작 보존=회귀 안전)
```

### 4-3. 현재 구멍 — 긍정표지는 negation을 못 본다 (§9에서 해결 설계)

```
  부정표지: negation 인식  ✅   (비대칭!)
  긍정표지: 평면 매칭만    ❌   ← any(m in text), hr_context_lexicon.py:104

  결과 구멍:  "경청하지 않는다"  →  현재 'positive' (틀림, 부→긍 위반)
  동시 함정:  "소통에 문제가 없다" → 반드시 'positive' 유지해야(긍→부 함정)
```

이 비대칭이 §8-2 긍정표지 보강을 막는 직접 원인 → **§9 positive-negation 게이트가 단일 선결 과제**(§5 P3).

---

## 5. 단계별 로드맵 (전체)

### 5-1. 단계 의존도 (한눈에)

```
  P0 ─ 설계합의(본 문서)
   │
   ▼
  P1 ─ gold 입력 UI/컬럼  ───┐         🟡 사용자 승인 필요
   │                         │
   ▼          (데이터 도착) ▼
  P2 ─ 코퍼스 적재 ─┬─ P3 positive-negation 게이트 켜기  (코퍼스 1회 감사)
                    └─ P4 약지도 LF 배선
                          │
                          ▼
  P5 ─ 사람 검토로 positive gold 확보 + 규칙 재마이닝   ◀── 최대 병목
                          │
                          ▼
  P6 ─ 품질 게이트 통과 → KoTE 파인튜닝 착수  🔴 사용자 결정(예산/배포)
                          │
                          ▼
  P7 ─ (미래) 리더십 전용 검사모델 시드  🔴 사용자 결정
```

### 5-2. 로드맵 표

| 단계 | 내용 | 산출물 | 의존/트리거 |
|------|------|--------|-------------|
| **P0** | 설계 통합·로드맵 합의 | 본 보고서 DN | (현재) |
| **P1** | gold 컬럼 마이그레이션 + `acquired_data.html` gold 확정 UI | gold 입력 가능 | P0 · 🟡 사용자 승인(0617_05 §13) |
| **P2** | 코퍼스 CSV 도착 → 적재 + 약지도 사전라벨 | weak_sentiment/weak_leadership | P1 · **데이터 도착** |
| **P3** | positive-negation 게이트 활성화(§9) + §8-2 긍정표지 보류 해제 | 게이트 코드 + 골든/회귀 ✅ | P2(표본 감사) |
| **P4** | 약지도 LF 배선(`refine_acquired_row` additive) + 3-tier 큐 | weak_leadership 가동 | P2 |
| **P5** | 사람 검토로 **positive gold 확보** + 규칙 재마이닝. ⚠️**균형·경계 우선 샘플링**(weak positive 62.6% 편중+단점→긍정 오염, §5-3) | confirmed gold 누적 | P4 · 검토 진행 |
| **P6** | export/split 품질 게이트 → **KoTE 파인튜닝 착수**. ⚠️**필드(장점/단점) 명시 피처화**(§5-3) | 학습셋 + 후처리 가드 | P5(gold 임계) · 🔴 사용자 결정 |
| **P7(미래)** | 리더십 전용 검사모델 시드(문장→micro 추출기) → **독립 설계서**: [`../../2026/0619_04_leadership-judge-ai/0619_04_leadership-judge-ai.md`](../../2026/0619_04_leadership-judge-ai/0619_04_leadership-judge-ai.md) | 보조헤드/전용모델 | P6 · 🔴 사용자 결정 |

### 5-3. 수집 → 군집 → 대표 gold 단계 정합 (2026-06-24 명문화)

> **왜 지금 gold 0·평면 weak인가**: 이건 정체가 아니라 **"수집 먼저, 군집/분석으로 규칙성·공통성을 찾은 뒤, 대표만 판정해 gold"** 라는 의도된 순서의 *수집 단계*다. (운용 원칙 §3-2 "큰 묶음 먼저, split은 군집 근거 시에만"·원칙 "gold는 코퍼스 군집으로만"과 동일 줄기.)

```
 수집(현재) ─▶ 군집/분석 ─▶ 대표 판정(판정 패킷) ─▶ 클러스터 전파 ─▶ gold 확정 ─▶ 파인튜닝
 weak 756k     규칙성·공통성     사람/AI가 대표만        묶음 단위         P5             P6
 gold 0        발견              (0623_01)              라벨 전파
```

**군집/분석이 주는 것(수집 많을수록 ↑)** — `scripts/mine_patterns.py`로 **일부 가동 중**:
- 패턴 패밀리 발견: "X 필요/했으면(개선요청)"·"단점 없음(약점없음)"·"어려움(필드별 양극)" 등 규칙성·공통성을 데이터에서 떠오르게 함. (오늘 수작업으로 찾은 단점 프레이밍도 이 종류 → 군집화 시 체계적 발굴.)
- trait 무지도 군집(D1)은 데이터·필드피처 갖춰진 뒤 진행(현 단계는 대그룹 9 유지, 추측 split 금지).

**군집이 못 주는 것(수집만으론 불가)**:
- **gold "정답"(긍/부/중)은 군집이 만들지 못함** — 군집은 "묶기"일 뿐 "이 묶음이 긍정인가"를 결정 못 함. → 군집은 라벨링을 **싸게**(대표만 판정 → 클러스터 전파) 할 뿐, 최종 gold 진위는 **대표 판정(사람/AI)** 이 받쳐야 함.

**오늘(2026-06-24 단점 적대검증) 반영분 — P5/P6에 추가 적용**:
1. **불균형·오염 인지**: 현재 weak 극성 = **positive 62.6%** / neutral 19.7% / negative 16.4%인데, 그 positive 안에 **단점→긍정 미검출(필드 폴리세미)** 이 섞여 있음. → P5 gold 샘플링은 **무작위 대량 금지, 균형·경계 우선**(negative·중립·폴리세미 양쪽 의미를 의도적으로 채움).
2. **필드(장점/단점)를 1급 피처로**: 현재 배치 id에만 암묵(0622_0=장점 36만 / 0622_2=단점 35만 …). **군집 피처·학습 피처로 명시 승격.** 같은 토큰이 필드로 극성이 뒤집힘(어려움: 장점 94% 긍 ↔ 단점 75% 부). → 상세 [[../result/accuracy_trend_260623.md]] §5차·`project_field_signal_for_finetune`.
3. **군집 피처 주의**: raw 텍스트/KoTE 임베딩만으로 군집하면 표면 감정으로 묶여 폴리세미("어려움 도와줌"↔"어려움 겪음")가 한 군집에 섞임. → 군집 입력에 **필드 + 규칙신호(applied_rule/override_score)** 동반.

---

## 6. 구현 상세 (실제 개발에 들어가는 방법)

> 각 단계의 "어디를·어떻게 바꾸는가". 모든 파일·함수·라인은 실측 확인분(추측 금지).

### 6-1. P1 — gold 입력 컬럼 마이그레이션 (DB)

**현황 실측**: `acquired_sentences` 테이블은 `deploy_session_service.py:193`에서 `schema_version` 단계 마이그레이션으로 생성된다(현재 v5 블록). **gold/검토 컬럼은 아직 없다.** 동일 패턴으로 **신규 버전 블록을 additive append**한다.

```python
# deploy_session_service.py — 기존 if current < N 패턴에 신규 블록 추가(additive)
if current < 7:
    conn.executescript("""
        ALTER TABLE acquired_sentences ADD COLUMN sentiment_gold  TEXT
              CHECK(sentiment_gold IN ('positive','negative','neutral'));
        ALTER TABLE acquired_sentences ADD COLUMN leadership_gold TEXT DEFAULT '';   -- node/trait id
        ALTER TABLE acquired_sentences ADD COLUMN review_status   TEXT DEFAULT 'pending'
              CHECK(review_status IN ('pending','confirmed','skipped'));
        ALTER TABLE acquired_sentences ADD COLUMN weak_leadership TEXT DEFAULT '{}'; -- LF JSON(§4-3)
        ALTER TABLE acquired_sentences ADD COLUMN reviewed_by     TEXT DEFAULT '';
        ALTER TABLE acquired_sentences ADD COLUMN reviewed_at     TEXT DEFAULT '';
    """)
    conn.execute("INSERT INTO schema_version (version, applied_at, note) VALUES (7, datetime('now'), ?)",
                 ('add gold/review columns to acquired_sentences for finetune labeling',))
```

- **안전장치**: 기존 컬럼·UNIQUE 제약 불변, 신규 컬럼만 추가(NULL/기본값) → 기존 행·경로 무영향. SQLite `ADD COLUMN`은 즉시·비파괴.
- **UI(P1-b)**: `acquired_data.html` 검토 뷰에 gold 확정 컨트롤 추가 → `POST /api/perspective/acquired-sentences/<id>/gold` (신규 엔드포인트, `perspective_routes.py`). 확정 시 `review_status='confirmed'` + `reviewed_by/at` 기록.

### 6-2. P3 — positive-negation 게이트 (규칙 코드)

**해법 = 상쇄명사(CANCEL_NOUNS) 차단**: 긍정표지 뒤 negation이 있을 때, 그 사이에 부정 가치 명사("문제/부족…")가 **있으면** negation이 그 명사를 상쇄(칭찬 유지), **없으면** negation이 긍정표지를 직접 부정(비판).

```
  긍정표지 ──[ window 14글자 ]── negation?
                  │
       상쇄명사("문제/부족"…) 사이에 있나?
           ├─ 있음 → "문제가 없다" = 칭찬 유지   → positive ✅
           └─ 없음 → "경청하지 않는다" = 비판     → negative ✅
```

```python
# hr_context_lexicon.py — 신규 상수 + 술어(additive)
CANCEL_NOUNS = ["문제", "부족", "어려움", "이슈", "걱정", "불만", "갈등",
                "미흡", "결여", "부재", "거리낌", "차질", "흠"]

def _negated_positive_is_criticism(text, after):
    if not _has_negation_after(text, after):      # 기존 함수 재사용
        return False
    window = text[after:after + NEGATION_WINDOW]
    return not any(n in window for n in CANCEL_NOUNS)
```

```
  leadership_polarity(:104) 변경 — 긍정표지를 부정표지와 동형 루프로 교체:
    (기존)  has_positive = any(m in text for m in POSITIVE_MARKERS)
    (신규)  for m in POSITIVE_MARKERS:
                각 출현 위치 스캔 →
                  _negated_positive_is_criticism True → has_real_negative=True
                                              else    → has_positive=True
    우선순위(real_negative > positive > neutral)·시그니처 불변 → additive·O(n)
    is_negation_praise()는 손대지 않음(부정표지 전용 술어)
```

**골든 케이스** (구현 시 `test_leadership_polarity.py`에 동시 추가):

| 분류 | 입력 | 기대 |
|------|------|------|
| catch(구멍) | 경청하지 않는다 / 배려가 없다 / 소통이 전혀 안 됨 / 동기부여를 하지 않음 | negative |
| trap(함정) | 소통에 문제가 없다 / 배려에 부족함이 없다 / 경청에 거리낌이 없다 | positive |
| 회귀 6종 | 강압적이지 않음 등 기존 전부 | 불변 |

### 6-3. P4 — 약지도 LF 배선 (자동 사전라벨)

**현황 실측**: `refine_acquired_row(row)`(perspective_service.py:2334)는 이미 KoTE 재계산 + 감정 보정(`weak_sentiment`/`applied_rule`)을 산출한다. 여기에 **리더십 LF 한 블록을 additive append**(기존 산출·시그니처 불변).

```python
# refine_acquired_row 말미에 추가(additive) — weak_leadership 산출
from src.modules.hr_context_lexicon import leadership_polarity, is_negation_praise

pol = leadership_polarity(text)                  # 재게이트(긍↔부 0)
weak_leadership = build_leadership_candidates(   # §4 seed 매핑 → 대그룹 후보
    text, polarity=pol,
    block_risk_on_praise=is_negation_praise(text),  # "강압적이지 않음"=권위주의 오귀속 차단
    default_status="grouped",                    # 세부 자동분류 금지
)
result["weak_leadership"] = weak_leadership       # JSON(§4-3 스키마)
```

- 산출 스키마(§4-3): `candidates[].status_hint="grouped"` 기본, `queue_tier`로 3-tier 큐 정렬, `flags`에 `polarity_conflict`/`forbidden_veto`/`negation_praise`.
- **절대 `*_gold` 미기록** — LF는 후보만, 확정은 사람.

### 6-4. P5 — 검토 + 규칙 재마이닝 (상시 루프)

```
  데이터 도착마다 반복 (RUNBOOK §2):
   검토 큐 ── gold 확정 ──▶ JSONL append
       │
       └─ 동시: 신규 오분류 패턴 → hr_context_lexicon에 표지 append
                 → 회귀(run_*_regression.py + test_leadership_polarity.py) 통과 필수
                 → §8-2 보류 표지(회피/비난/차별…)는 코퍼스 근거 생길 때 승격
```

### 6-5. P6 — 파인튜닝 (별도 파이프라인 · 사용자 결정)

```
  export_jsonl.py(비식별화 게이트) → build_splits.py(누수방지 분할)
        → 품질 리포트(result/split_report_<date>.md): 긍↔부 0 + positive gold 추세
        → [게이트 통과 & 사용자 승인] → KoTE 파인튜닝
        → 학습 후에도 규칙은 후처리 가드로 유지(모델이 규칙을 대체하지 않음)
```

---

## 7. 영향도 분석

| 단계 | 변경 파일(실측) | 영향 범위 | 안전장치 |
|------|----------------|-----------|----------|
| P1 | `deploy_session_service.py`(schema v7), `acquired_data.html`, `perspective_routes.py` | gold 입력 경로 신설 | additive 컬럼, 기존 UNIQUE/경로 불변 |
| P3 | `hr_context_lexicon.py`(:104 긍정 루프), `test_leadership_polarity.py` | `leadership_polarity` 분기 | 시그니처 불변, 골든+회귀 통과 전 비활성 |
| P4 | `perspective_service.refine_acquired_row`(:2334), `acquired_data.html`(큐 정렬) | 약지도 1필드 추가 | `*_gold` 미기록, 6역량·기존 산출 불변 |
| P5 | `hr_context_lexicon`(append), JSONL 스트림 | 표지 additive, gold append | 회귀 필수, append-only |
| P6 | (학습 파이프라인 — 별도) | 모델 산출 | 규칙은 후처리 가드 유지 |

- **공통**: dev 미반입·내부망 전용. `plans/`·JSONL 배포 제외. O(n) 유지(1.9만 규모).

---

## 8. 테스트/검증 계획

1. **회귀 게이트(상시)**: 표지/분기 변경 전후 `0617_01/test/run_*_regression.py` + `test_leadership_polarity.py` 통과 — **긍↔부 오분류 0** 확인.
2. **P3 골든(§6-2 표)**: catch 4종 + trap 3종 + 기존 6종 전부 유지(특히 '강압적이지 않음'→positive).
3. **P1 마이그레이션**: schema v7 적용 후 기존 행 무손실 + 신규 컬럼 NULL 기본 확인.
4. **P5 핵심가치 점검**: `result/split_report_<date>.md`로 긍↔부 0 + positive gold 확보 추세(RUNBOOK §2-8).
5. **누수 방지 분할 / PII 감사**: `build_splits.py` 출처 분리 + export 전 정규식 게이트로 가명화 미완 행 격리.

---

## 9. 리스크 및 제약

| 리스크 | 영향 | 대응 |
|--------|------|------|
| §6-2 CANCEL_NOUNS 누락 1개 = 긍→부 오분류 | 핵심가치 위반 | 라이브 보류, 코퍼스 표본 감사로 실측 보강 후 1회 활성화(P3) |
| positive gold 0 지속 | 파인튜닝 무기한 차단 | P1 gold UI + P5 검토를 최우선 선결로 고정 |
| 외부 샘플 gold 오염 | 평가 신뢰 붕괴 | 스키마만 흡수, 출처 분리·평가셋 격리(원칙 5) |
| 추측 세분화로 trait 과적합 | 희소 leaf 노이즈 | 기본 grouped, split은 군집 근거 시에만 |
| dev 코퍼스 부재로 설계 검증 지연 | P3/P4 미검증 잔존 | 설계만 확정, 구현은 데이터 트리거로 명시 |

**설계 원칙(불변)**: ① 긍↔부 오분류 0(양방향) ② 추측 분류 금지(군집 근거 시에만) ③ append-only·비식별화·내부망 전용 ④ additive·레거시 보호(회귀 통과) ⑤ 외부는 스키마만 ⑥ 사용자 고유 결정 에스컬레이션·O(n).
**제약**: 서버 무단 실행 금지 · dev 배치 불가(CSV만) · 외부 텍스트 비반입.

---

## 10. 결정 필요 사항 (사용자 에스컬레이션)

1. **P1 착수 승인 시점** — gold 컬럼 마이그레이션 + 확정 UI를 데이터 도착 전 미리 만들지, 도착과 함께 만들지(0617_05 §13 보류 중).
2. **P6 파인튜닝 진입 기준** — positive gold 최소 건수·평가셋 규모·학습 예산(모델 학습 착수는 사용자 고유 결정).
3. **P7 리더십 전용 모델** — 추진 여부 및 외부 12,460 샘플의 사전학습/증강 한정 사용 허용 여부(평가셋 격리 전제). 권장: P6 이후 재론.

---

*본 보고서는 향후 개발 통합 로드맵 + 구현 지침이다. 실제 데이터 도착·검토·규칙 재마이닝의 반복 실행은 RUNBOOK(상시 절차)을 따른다. 다이어그램은 plans 칸반 렌더러(코드블록 monospace) 기준으로 작성되었다.*
