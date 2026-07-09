# 리더십 약지도 라벨링 함수(LF) — 검토 큐 후보라벨 매핑 (초안 v1)

> ⚠️ **이것은 gold 생성기가 아니다.** 우리 코퍼스 문장에 **약한 후보 라벨(weak)** 만 붙여 RUNBOOK §2-3 **사람 검토 큐**에 우선순위로 태우는 가속기다. 확정 gold는 사람 검토로만(추측 분류 금지).
> 위치: [`trait_library_ref.md`](trait_library_ref.md) §0-3 4-레이어 중 **②약지도 LF**의 구현 설계. 정본 trait/micro = `trait_library_ref.md`(20-trait, commit `49b261c`).
> 상태: **설계 초안**(미구현). dev는 실 코퍼스 미반입·서버 무단 실행 금지 → 실데이터 도착 시 `refine_acquired_row`에 additive 배선.

---

## 1. 파이프라인 위치 (어디에 끼는가)

```
import_acquired_sentences_csv → acquired_sentences
      ↓
[약지도 사전라벨]  perspective_service.refine_acquired_row()  ← src/services/perspective_service.py:2334
      ├─ (기존) KoTE top3 + sentiment override → weak_sentiment / applied_rule
      └─ (신규·additive) **weak_leadership** = 본 LF 산출         ← 본 문서
      ↓
[사람 검토 큐]  acquired_data.html — queue_tier 우선순위로 정렬
      ↓
[gold 확정]  사람만 → leadership_gold (active=세부 / grouped=대그룹)
```

- **재사용 자산(검증됨)**: `hr_context_lexicon.leadership_polarity()`(hr_context_lexicon.py:67) · `POSITIVE_MARKERS`/`NEGATIVE_MARKERS`(:33/:45) · `is_negation_praise()`(:106) · `NEGATION_WINDOW=14` · 6역량 `leadership_competencies`(leadership_analysis.py:80, keywords+KoTE emotion idx).
- 6역량은 이미 "거친 LF(keyword+emotion)"다 → 본 LF는 이를 **6→20 trait 후보 + 극성 게이트 + grouped 기본**으로 확장(레거시 시그니처 불변, additive).

---

## 2. 입력 신호 ↔ 외부 micro 패턴의 브리지 (임피던스 해소)

외부 trait은 micro(`Mxx/Nxx`) 조합으로 정의되나 **우리 추론기는 micro를 직접 못 뽑는다**(KoTE=44감정, lexicon=표지). 브리지:

| 외부 정의 | 우리 근사 신호(현재 가능) |
|---|---|
| micro 라벨(M/N) | **micro 이름에서 추출한 한국어 표면 표지**(§4 seed) + 6역량 keywords |
| trait required(AND) | seed **다수 매칭** = 고신뢰 |
| trait optional(가산) | seed 추가 매칭 = score 보너스 |
| hard_forbidden(veto) | **부정표지 매칭 → 후보 제거/극성 충돌 플래그** |
| soft_forbidden(penalty) | score 감점 |
| KoTE 감정 차원 | 6역량 `emotions` idx 신호 |
| k_trait · context_weight | **약지도라 참고만**(tie-break) — 데이터 없을 땐 1.0 |

> 🔭 micro를 **모델 타깃으로** 승격하려면 별도 "문장→micro 추출기"(LLM/규칙)가 필요(후속, `trait_library_ref.md` §0-4 (d)). 현 LF는 표면 표지 근사다.

---

## 3. LF 산출 스키마 (additive · 비-gold)

`acquired_sentences` 행에 **weak 필드만** 추가(절대 `*_gold` 미기록):

```json
"weak_leadership": {
  "is_leadership": true,
  "polarity": "positive",            // leadership_polarity 재게이트: positive|risk|neutral
  "candidates": [
    {"node": "G_REL", "level": 1, "trait_ref": "T07", "score": 0.62,
     "evidence": ["격려","육성"], "status_hint": "grouped"},
    {"node": "T_COACH", "level": 2, "trait_ref": "T07", "score": 0.41,
     "evidence": ["성장 피드백"], "status_hint": "active_candidate"}
  ],
  "queue_tier": 1,                    // RUNBOOK §2 3-tier (1=최우선)
  "confidence": "B",                 // A|B|C (§6)
  "flags": ["polarity_ok"],          // forbidden_veto | polarity_conflict | negation_praise ...
  "lf_version": "1"
}
```

---

## 4. trait별 발화 규칙 매핑 (핵심 — 20 trait)

> seed = micro 이름에서 뽑은 한국어 표면 표지(**약한 prior**). 부정표지는 기존 `NEGATIVE_MARKERS`와 겹치는 항목이 많아 **lexicon additive 후보**이기도 함(§7 회귀 게이트). 모든 긍정 trait는 `leadership_polarity≠negative` AND `is_negation_praise=false`일 때만 발화.

### 긍정·균형 (백본 positive)
| trait_ref | 세부 / 대그룹 | 긍정 발화 seed(표면) | KoTE 6역량 신호 | soft/hard veto(부정표지) |
|---|---|---|---|---|
| T01 | 결단형 / 방향·전략 | 비전 제시·목표 설정·신속한 의사결정·방향 | leadership·problem_solving | 책임 전가/회피, 독단(soft) |
| T02 | 협업형 / 관계·소통 | 경청·심리적 안전·의견 청취·소통·협력·팀워크 | teamwork·communication | 경청 거부·의견 폄하·공개적 비난·권위 과시 |
| T03 | 혁신형 / 혁신·학습 | 새로운 접근·변화 실행·혁신 아이디어·창의적 질문·실험 | innovation | 아이디어 무시·비판 금지·변화 억압 |
| T04 | 위기대응형 / 실행·성과 | 위기 대응·신속 의사결정·문제 해결·불확실성 안정 | problem_solving | 불안 조장·위기 과장 |
| T05 | 분석형 / 방향·전략 | 데이터 기반·분석·논리·정확 | problem_solving | 비전 과장·정보 은폐 |
| T06 | 실행형 / 실행·성과 | 실행력·완수·목표 지향 실행·성과 | problem_solving·leadership | 마감 무시·자원 독점 |
| T07 | 코칭형 / 관계·소통 | 성장 기회·성장 피드백·격려·인정·육성 | communication | 공개적 질책·공로 가로채기 |
| T08 | 감정지능형 / 관계·소통 | 공감·감정적 배려·경청·심리적 안전·정서적 지지 | communication | 공감 결여·정서적 무관심·심리적 압박 |
| T09 | 비전제시형 / 방향·전략 | 비전·비전 공유·장기 방향·카리스마·롤모델·동기부여 | leadership | 방향성 불일치 |
| T10 | **전략실행형** / 실행·성과 | 비전+실행·목표 지향 실행·전략적 자원 배분 | leadership·problem_solving | 실행 부진·마감 무시 |
| T11 | **공감형** / 관계·소통 | 공감·배려·타인 우선·희생적 지원·심리적 안전 | communication·teamwork | 공감 결여·정서적 무관심·자기 이익 우선 |
| T12 | 균형형 / 윤리·신뢰 | 운영 안정·투명한 소통·포용·다양성·균형 | ethics | 정보 은폐·언행 불일치·차별 |
| T13 | 윤리적용기형 / 윤리·신뢰 | 도덕적 용기·부당행위 대응·언행 일치·공정·원칙·자기성찰 | ethics | 부당행위 묵인·문제 회피·정보 은폐(soft) |
| T14 | 학습민첩형 / 혁신·학습 | 학습·디지털 민첩·실패 수용·혁신 기회·디지털 도구·AI | innovation | 디지털 거부·혁신 차단·실패 은폐 |

### 리스크 (백본 risk) — 발화 = 진짜 부정표지(negation 칭찬 아님)일 때만
| trait_ref | 세부 / 대그룹 | 부정 발화 seed(표면) | 비고 |
|---|---|---|---|
| T101 | 회피형 / 회피·무책임 | 책임 전가·책임 회피·의사결정 지연·문제 회피 | |
| T102 | 권위주의 / 권위·통제 | 공개적 비난·독단·권위 과시·강압·일방적·수직적·지시 감독·과도한 통제·간섭 | 다수 항목 **기존 NEGATIVE_MARKERS와 일치** |
| T103 | 정직성위반형 / 정직성 위반 | 언행 불일치·말과 행동 불일치·정보 은폐·데이터 조작·도구 남용 | |
| T104 | 자기애적 / 자기중심·조작 | 개인 숭배·공로 독점·공로 가로채기·자원 독점·팀 희생 강요 | |
| T105 | 조작적 / 자기중심·조작 | 보상 과장 약속·감정적 압박·공포 기반 동기·비현실적 목표·비전 과장 | |
| T106 | 기복(과잉통제)형 / 권위·통제 | 상황 무시 강경·과도한 통제·감정 기복·불안 조장·실험 실패 처벌 | |

---

## 5. 극성 게이트 · grouped 기본 (핵심가치 보호)

1. **극성 재게이트(필수)**: 모든 후보는 `leadership_polarity(text)` 통과. 긍정 trait 후보인데 `polarity=='negative'` → **후보 보류 + queue_tier=1**(rule_hurt 위험, 사람 확정). `is_negation_praise` → risk 후보 **차단**(예: "강압적이지 않음"을 권위주의로 오귀속 금지).
2. **기본 grouped**: 후보는 **대그룹(level1)** 로만 제시 → 추측 세분화 방지. 세부(level2)는 `status_hint:"active_candidate"`로 **힌트만**(확정은 사람·§7 게이트 N/M).
3. **겹침쌍 자동 세부 금지**: **T11 공감형↔T08 감정지능형**, **T10 전략실행형↔T01 결단형/T06 실행형** 은 seed 겹침이 커 군집 검증 전 **무조건 grouped**(세부 힌트 억제).
4. **단조성**: LF는 트리를 바꾸지 않음 — 후보만 제시. trait 채택/split은 §6 군집 + 사람.

---

## 6. 신뢰도 등급 · 검토 큐 우선순위 (RUNBOOK §2 3-tier)

**confidence**: A=required seed 다수 + 극성 일치 / B=required 1 + (optional·KoTE) / C=optional·KoTE만.

**queue_tier**(고가치부터):
1. **rule_hurt 위험**: 극성 충돌(긍 trait ↔ 부정표지) · forbidden veto 발동 · negation 칭찬.
2. **극성 경계**: weak polarity ↔ 후보 trait 극성 불일치, 저마진 후보(top1−top2 score < 0.05).
3. **저신뢰 보강**: is_leadership 약함(seed 1개) · 세부 힌트 마진 작음.

> RUNBOOK §2-3 우선순위 큐(rule_hurt → 극성 불일치 → 저마진)와 정렬 — 같은 키로 통합.

---

## 7. 가드레일 · 후속

**가드레일(불변)**
- **gold 아님**: LF는 `weak_leadership`만, `*_gold` 절대 미기록. 확정은 사람.
- **추측 세분화 금지**: 기본 grouped, 세부는 힌트.
- **긍↔부 재게이트**: 모든 후보 `leadership_polarity` 경유 — 오분류 0 최우선.
- **additive·레거시 보호**: `refine_acquired_row` 기존 산출·6역량·`leadership_polarity` 시그니처 불변. 부정 seed를 `NEGATIVE_MARKERS`에 반영할 땐 **append만 + 회귀(`0617_01/test/run_*_regression.py`, `test_leadership_polarity.py`) 통과 필수**.
- **외부 텍스트 비반입**: 표지(스키마)만 차용, 외부 샘플 미반입(`trait_library_ref.md` §0-5).
- **O(n)**: 표지 매칭은 문장당 상수 — 1.9만 규모 안전.

**후속(데이터 도착 시)**
- ⓞ **positive-negation 게이트 활성화**(§9 설계 확정분 — 긍↔부 양방향 0 선결, §8-2 긍정표지 보류 해제와 동시). ① `refine_acquired_row`에 `weak_leadership` 배선(additive). ② §4 seed → 설정화(`trait_tree.json` seed_markers와 단일화). ③ 문장→micro 추출기 검토(micro 모델타깃 승격 시). ④ score 임계값·context_weight는 프로토타입 분포 확인 후 확정(추측 금지).

---

## 8. 부정표지 lexicon 보강 (레이어④ 실행 로그)

> `trait_library_ref.md` §0-3 ④의 실제 수행분. 외부 forbidden(`Nxx`) 유래 표지를 `hr_context_lexicon.NEGATIVE_MARKERS`에 **additive append**. 긍정표지는 부정문("공감 못함")을 긍정 오판할 위험(부→긍)이 있어 **이번 보강 대상에서 제외**(positive 게이트에 negation 로직 신설 전까지 보류).

### 8-1. 활성화(2026-06-19, 회귀 통과)
| 표지(코어) | 유래 | 비고 |
|---|---|---|
| 전가 | N08 책임 전가 | 활용형 커버(전가하다/전가한다) |
| 묵살 | N15 의견 묵살 | |
| 은폐 | N28 정보 은폐 | |
| 협박 | N02 공포 기반 동기 | |
| 편애 | N09 불공정 인정 | |
| 가로채 · 가로챈 | N14 공로 가로채기 | "가로챈다"(채+ㄴ=챈) 누락 방지로 활용형 2개 |
| 과도한 통제 · 과잉 통제 | N24 과도 통제 | bare "통제"는 자기통제 충돌로 금지 → 수식형만 |

- 검증: `test_leadership_polarity.py`에 케이스 추가(bare→negative, `~하지 않음`→positive) → **6/6 통과, 긍↔부 오분류 0**. negation 게이트가 칭찬 자동 보호.
- 추적성: `hr_context_lexicon.py` NEGATIVE_MARKERS 보강 블록(주석 + 본 문서 링크), append-only.

### 8-2. 보류(staged — 코퍼스 근거/추가 처리 대기)
| 후보 | 보류 사유 |
|---|---|
| 회피 | 위험/갈등 회피 등 **중립 맥락** 존재 → 코퍼스 검증 후 |
| 비난 | "비난을 수용" 등 **긍정 맥락** 오발(긍→부) 위험 |
| 독점 / 자원 독점 | "시장 독점" 등 비-리더십 중립 충돌 |
| 차별 | "차별화(전략)" 부분문자열 충돌 → "차별 대우" 형태 필요 |
| 조작(bare) | generic → "데이터 조작" 등 수식 필요(조사 변화) |
| 언행 불일치 / 불일치 | "의견 불일치" 중립 + 조사 변화로 단일 코어 포착난 |
| 무시 / 통제(bare) | "무시", "자기 통제"(positive) 충돌 → 수식형만 허용 |
| 긍정 표지(공감·피드백·공정·투명…) | **부→긍 위험**(부정문 내 긍정어) → positive negation 게이트 선결 → **설계 확정 §9**(구현 트리거=코퍼스 도착) |

> 승격 규칙: (a) 고정밀(중립/긍정 충돌 낮음) **AND** (b) negation 게이트 호환 **AND** (c) 가급적 코퍼스 오분류 근거 → 충족 시 append + 회귀 재통과(`test_leadership_polarity.py`). **추측으로 일괄 투입 금지.**

---

## 9. positive-negation 게이트 설계 (선결 · 구현 보류=코퍼스 도착 시)

> §8-2 마지막 행("긍정 표지 → 부→긍 위험")의 **단일 선결 과제**. 현재 `leadership_polarity`는 부정표지엔 negation을 인식하나, **긍정표지는 평면 매칭**(`any(m in text)`)이라 **부정문 속 긍정어를 긍정으로 오판**한다. 이 비대칭이 §8-2 긍정표지 보류의 직접 원인.

### 9-1. 닫아야 할 구멍 (현재 동작 = 부→긍 오분류)
현 코드(`hr_context_lexicon.py:104`)는 `has_real_negative`가 없으면 긍정표지 존재만으로 `positive`를 반환한다.

| 입력 | 현재 | 정답 | 오류 유형 |
|---|---|---|---|
| 경청하지 않는다 | **positive** | negative | **부→긍 (핵심가치 위반)** |
| 배려가 없다 / 배려가 부족 | **positive** | negative | 부→긍 |
| 소통이 전혀 안 됨 | **positive** | negative | 부→긍 |

### 9-2. 함정 (대칭 위험 = 긍→부) — 게이트가 반드시 피해야 함
naive하게 "긍정표지 뒤 negation → negative"로 뒤집으면 **부정의 부정 = 칭찬** 문장을 망가뜨린다.

| 입력 | 구조 | 정답 | naive 게이트 결과 |
|---|---|---|---|
| 소통에 **문제가** 없다 | 긍정어 + [부정명사] + 부정 | positive | ❌ negative(긍→부) |
| 배려에 **부족함이** 없다 | 긍정어 + [부정명사] + 부정 | positive | ❌ negative |
| 경청에 **거리낌이** 없다 | 긍정어 + [부정명사] + 부정 | positive | ❌ negative |

→ **양방향(부→긍·긍→부) 모두 핵심가치 위반.** 한쪽으로 편향 불가 — 둘 다 0이어야 한다.

### 9-3. 규칙(상쇄명사 차단 방식)
긍정표지 뒤 window 안에 negation이 있을 때:
- **상쇄명사(부정 가치 명사)가 표지~negation 사이에 없으면** → negation이 긍정표지를 직접 부정 = **비판(negative)**.
- **상쇄명사가 있으면** → negation은 그 부정명사를 상쇄 = **긍정 유지**.

```
CANCEL_NOUNS = ["문제", "부족", "어려움", "이슈", "걱정", "불만", "갈등",
                "미흡", "결여", "부재", "거리낌", "차질", "흠"]   # 부정 가치 명사
def _negated_positive_is_criticism(text, after):
    # after = 긍정표지 끝 위치. window 내 negation 존재 AND 그 사이 상쇄명사 없음.
    if not _has_negation_after(text, after):      # 기존 함수 재사용
        return False
    window = text[after:after + NEGATION_WINDOW]
    return not any(n in window for n in CANCEL_NOUNS)
```
- `leadership_polarity`의 긍정표지 루프를 부정표지 루프와 동형으로 교체: 표지마다 occurrence 스캔 → `_negated_positive_is_criticism` True면 `has_real_negative=True`, 아니면 `has_positive=True`. 분기 우선순위(real_negative > positive > neutral)·시그니처 불변 → **additive·O(n) 유지**.
- `is_negation_praise`는 손대지 않음(부정표지 전용 술어).

### 9-4. 골든 케이스(구현 시 `test_leadership_polarity.py`에 동시 추가)
```
# 부→긍 구멍 닫힘 (catch)
경청하지 않는다           → negative
배려가 없다               → negative
소통이 전혀 안 됨         → negative
동기부여를 하지 않음      → negative
# 긍→부 함정 회피 (trap)  — 상쇄명사가 negation을 흡수
소통에 문제가 없다         → positive
배려에 부족함이 없다       → positive
경청에 거리낌이 없다       → positive
# 기존 회귀 6종 전부 유지(특히 '강압적이지 않음'→positive)
```

### 9-5. 왜 지금 라이브 투입을 보류하는가 (정직한 표면화)
- 긍↔부 **양방향 0**이 NON-NEGOTIABLE인데, 9-2 함정 클래스(상쇄명사 변형·조사 변화)는 **내가 지어낸 케이스만으로 전수 보장 불가**. 누락된 상쇄명사 1개 = 긍→부 오분류 1건.
- dev는 실 코퍼스 미반입([[project-dev-no-batch-csv-only]]) → 폴라리티를 **뒤집는** 규칙을 corpus 대조 없이 켜는 것은 핵심 엔지니어 가드레일("핵심가치 위반 가능성 즉시 표면화 · 되돌리기 어려운 변경은 권고+선택지")에 어긋남.
- **구현 트리거**: 첫 코퍼스 도착 시 §2 검토 큐에서 긍정표지+negation 문장을 표본 감사 → `CANCEL_NOUNS` 실측 보강 → 9-4 골든 + 회귀 통과 후 **그 1회에 활성화**(그때 §8-2 긍정표지 보류도 함께 해제).
