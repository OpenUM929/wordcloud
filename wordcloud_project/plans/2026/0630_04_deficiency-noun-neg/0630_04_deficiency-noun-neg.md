# 0630_04 결핍명사(부족·미흡·결여·부재) 부→긍 누수 차단 (rule4_default 잔존 구멍)

> 상태: Drop — substring 부정화는 전수 재생서 긍→부 263(장점 138) 잔존, 긍↔부 0 불가. 목표는 극성표/파인튜닝 트랙으로 이관 | 작성일: 2026-06-30
> 작업 유형: A — 버그 수정/핫픽스 (RUNBOOK §2-1 step5 규칙 재마이닝 겸함) · 0630_03 후속

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-30 | 신규 | 최초 작성. 0630_03이 닫지 못한 결핍명사 경로 누수 차단 |
| 2026-06-30 | §5·상태 | 구현+전수 재생 → 긍→부 263 잔존(술어결정 명사) → 코드 원복·**Drop**. 근거 `result/replay_result_260630.md` |

---

## 1. 문제 정의

- **관찰(코드 추적 + 0630_03 후속 감사)**: 0630_03이 신설한 `improvement_request_neutral` 분기는
  트리거가 `_has_improvement_request_core`(희망형·요함/요망·보완|개선 요청) · `has_constructive_need`('필요'/'요구됨')
  · `has_unnegated_deficiency`(**결함술어 `소홀` 단일**)뿐이다.
  **결핍 *명사* `부족·미흡·결여·부재`는 어느 트리거도 포착하지 못한다.**
- **누수 경로(재현)**: `소통이 부족합니다`(정답=부정)가 KoTE 긍정우세(pos>neg)·**비종결 또는 고신뢰**일 때:
  - `positive_rescue`: `부족`∈`NEGATIVE_IMPLYING_WORDS`(L282) → rescue 차단(여기선 부→긍 안 남).
  - `rule3_last_low`(L835): **종결+저신뢰**일 때만 `-strength`(부정). → 비종결이거나 `|pos-neg|≥threshold`면 미발동.
  - 그 외 분기 전부 미스 → **`rule4_default`(L839 `pos-neg`)로 KoTE 긍정 그대로 출력 = 부→긍 누수.**
- **규모 근거**: RUNBOOK §누적 로그 2026-06-24 — 단점필드 30.8%(131,566)가 여전히 positive,
  **78%(24,019)가 `rule4_default` 무override**. 0630_03이 `필요/소홀/개선요청` 부분을 닫았고,
  **결핍명사 부분은 그대로 남아 있다**(본 작업 대상).
- **사용자 의도**: 제보(`보완 필요`=부정)와 0630_03 §판단의 "완전 부정화는 트랩 가드 확보 후 후속"을 잇는다.

## 2. 원인 분석

> ⛔ 원인 확정 게이트 — 3개 충족

1. **재현했다**: `_sentence_sentiment_override_explain(0.55, 0.30, '소통이 부족합니다', is_last=False, total=3, neutral=0.15)`
   → 어느 override도 미발동 → `rule4_default`, `+0.25`(긍정). (전수 재생 §5에서 실데이터로 정량화)
2. **그 줄이 범인**: 결핍 *명사* 포착 함수가 override 트리거 집합에 **부재**다.
   기존 `_has_unnegated_other_negative`(`부족/미흡/결여/부재/아쉽/여지`, negation-aware, L697)는
   **`is_no_weakness_declaration`의 혼합 판별 전용**(L712)으로만 호출되고, 보정 분기 트리거로는 쓰이지 않는다.
   → `부족·미흡·결여·부재`는 극성을 끌어내릴 경로가 없다.
3. **반증 실험**: pos>neg + 미부정 결핍명사를 가로채면 단점필드 부→긍이 추가로 사라져야 한다(§5 전수 재생).
   사라지지 않으면 가설 오류.

- **근거**: `perspective_service.py` L819 `improvement_request_neutral` 트리거 집합, L697 `_has_unnegated_other_negative`,
  L280 `NEGATIVE_IMPLYING_WORDS`(`부족/미흡/아쉽/여지`), L835 `rule3_last_low`, L839 `rule4_default`.
- **회귀 도입 지점**: 신규 회귀 아님 — KoTE의 구조적 한계(개선/결핍 화행을 칭찬으로 오판)를 override가 부분만 덮던 상태.
  0630_03이 `필요/소홀/개선요청`을 덮었고 결핍명사는 미피복으로 잔존.

## 3. 수정 방안 (additive·시그니처 불변·O(n))

> 🔴 **핵심 원칙: 누수를 닫되, 부정화 여부는 전수 양방향 재생이 결정한다.**
> 결핍명사 부정화는 `부족한 부분을 채워 성장`(자기개선=긍정) 같은 **긍→부 트랩**이 실재한다.
> 따라서 ① 먼저 **중립 강등**(긍↔부 0 보장)으로 누수를 닫고, ② 부정화는 **전수 재생서 긍→부 0일 때만** 채택한다.

- **신규 게이트 `has_deficiency_noun_critical(sentence)`** (negation-aware + 자기개선 트랩 가드):
  - 대상 명사(트랩 경미한 코어): `부족·미흡·결여·부재`. (⚠️ `여지`=다의(발전 여지=긍정)·`아쉽`=연성 → **코어 제외**, 전수 재생 후 별도 판단.)
  - 제외 1 (재부정): 명사 직후 창에 `없/않/아니` → 제외(`부족함이 없다`=긍정). 기존 `_has_unnegated_other_negative` 로직 재사용.
  - 제외 2 (자기개선 트랩, 신규): 관형형 `부족한/미흡한` + 근접 자기개선 동사(`채우·보완·학습·노력·성장·발전·극복·개선`) → 제외(`부족한 부분을 채워 성장`=긍정).
  - 제외 3 (양보): 문장 단위 `has_contrast`로 분기에서 제외(`부족하나 우수`=rule1/2 처리).
- **신규 분기** (euphemistic_negative 뒤, improvement_request_neutral 앞):
  ```
  if pos > neg and not has_contrast and has_deficiency_noun_critical(sentence):
      return <S>, 'deficiency_noun_<R>'
  ```
  - **`<S>,<R>` 는 전수 재생이 결정**:
    - 전수 양방향 재생에서 **긍→부 = 0** → `<S>=-strength`, `<R>='deficiency_noun_negative'` (부정화, 사용자 의도 충족).
    - 긍→부 ≥ 1 → 트랩 가드를 보강해 재재생; 그래도 잔존하면 해당 패턴은 **`<S>=0.0`(중립)** 으로 후퇴(긍↔부 0 우선, 0630_03 동형).
  - `improvement_request_neutral`(`필요/개선요청`)은 **불변**(트랩 다수라 중립 유지). 결핍명사 분기를 앞에 두어
    `소통 부족, 보완 필요` 동시 출현 시 강한 신호(결핍명사)가 우선.
- **비변경**: `필요/소홀/개선요청` 경로, is_negation_praise, 욕설, 레거시 시그니처. `_has_unnegated_other_negative`·`is_no_weakness_declaration` 동작 불변.

## 4. 롤백 계획

- 단일 파일(`perspective_service.py`): `deficiency_noun_*` 분기 + `has_deficiency_noun_critical`/`_DEFICIENCY_NOUNS_CRITICAL` 도입분 원복. 골든 테스트 1개 파일·재생 스크립트(plans, 배포무관) 제거.

## 5. 결과 (전수 재생 검증 — Drop 확정)

**전수 재생** (`emotion/weak_export_260624.jsonl` 889,465행, 저장 weak_kote 재사용). 상세: `result/replay_result_260630.md`.

| 지표 | 가드 1차 | 가드 2차(조력/에도양보/자기개선 보강) |
|------|----------|----------------------------------------|
| 🔴 pos→neg(긍↔부 위반·양방향) | 386 (장점 237) | **263 (장점 138)** |
| neg→pos | 0 | 0 |
| 단점 부→긍 차단(진짜수정) | 149 | 125 |

- **게이트 실패**: 부정화는 양방향 긍↔부 0의 *양보* 방향(긍→부)을 깬다. 가드 보강으로도 263 잔존.
- **원인(데이터 확증)**: `부족/부재/미흡`은 술어가 극성을 정하는 **토픽 명사**. 장점필드 138 위반은 거의 전부 진짜 칭찬
  (`부족한 점을 챙겨주심`·`부재 시 대행`·`부족함에도 솔선수범`). 단점 "차단"분에도 약점없음 오탐(`부족한 부분 없음`) 다수.
  필드(장/단점)조차 분리 못 함 → substring 불가. `[[project_polarity_lexicon_field_skew]]` 전수 확증.
- **중립 후퇴도 미채택**: 장점 138 진짜 칭찬을 중립 강등 = 방어 불가한 정밀도 손실(0630_03의 583과 질이 다름). 비용>이득.
- **처리**: 코드 전량 원복(58줄), 회귀 전 종 PASS·`py_compile` OK. 목표는 극성표/파인튜닝(P6) 트랙으로 이관.
- 재생 스크립트 `test/replay_deficiency_260630.py`는 재사용 적대검증 하니스로 보존(배포 제외).

> 교훈 준수: 가드마다 전수 양방향 재생이 substring 부정화 불가를 입증 — 게이트가 제 역할(`[[feedback_diagnose_from_symptom_not_hypothesis]]`·`[[feedback_execute_plan_no_descope.md]]`).

## 판단 — 중립 vs 부정

- 사용자 의도는 부정화(보완 필요=부정). 본 작업은 **부정화를 시도하되 긍↔부 0을 절대 우선**한다:
  전수 재생서 긍→부 0이면 부정 채택, 1건이라도 나오면 해당 패턴 중립 후퇴(0630_03 §판단 동일 원칙).
- 결핍명사(`부족/미흡/결여/부재`)는 `필요`보다 트랩이 경미(다의·조사 함정 적음)해 부정화 성공 가능성이 높다 — 단, **데이터가 결정**.

## 영향도 분석

- **호출 경로**: `_sentence_sentiment_override_explain` → `sentence_sentiment_override`(L842)·refine → 메타데이터/그룹분석/제출용저장 문장 극성에 일관 반영.
- **DB**: 신규 메타데이터 생성분부터 단점 결핍명사가 (부정 또는 중립)으로 적재. 기존분은 재생성 시 정정.
- **성능**: 순수 문자열 O(n), KoTE 재사용 불요, 시그니처 불변.

## 운영 반영 검증 대기 (Done 승격 조건)

내부망 메타데이터 재생성 → 단점필드 `소통 부족·보고 미흡`류가 (부정/중립)으로 적재되고 장점 긍정이 보존되는지 표본 확인 시 `Done`.

## 핵심 파일

- `src/services/perspective_service.py` — `deficiency_noun_*` 분기 + `has_deficiency_noun_critical`
- `plans/2026/0630_04_deficiency-noun-neg/test/test_deficiency_noun.py` — 골든·트랩 회귀(신규)
- `plans/2026/0630_04_deficiency-noun-neg/test/replay_deficiency_260630.py` — 전수 양방향 재생(신규, 배포 제외)

## 불변 제약

긍↔부 0(양방향·전수검증) · 부정화는 긍→부 0 게이트 통과 시만(미통과 패턴은 중립 후퇴) · additive·레거시 시그니처 불변(회귀 필수) · O(n) · 서버 무단 실행 금지·dev 모델재실행 불요(저장 weak_kote 재생) · plans/test 배포 제외.
