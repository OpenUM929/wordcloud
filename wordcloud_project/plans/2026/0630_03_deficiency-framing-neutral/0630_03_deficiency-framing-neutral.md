# 0630_03 결핍·개선요청 프레이밍 부→긍 누수 중립화 (rule4_default 경로)

> 상태: Pre-Done | 작성일: 2026-06-30
> 작업 유형: A — 버그 수정/핫픽스 (RUNBOOK §2-1 step5 규칙 재마이닝 겸함)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-30 | 신규 | 최초 작성. 전수 재생 검증 완료(Pre-Done) |

---

## 1. 문제 정의

- **관찰(실측, 사용자 제보 `260625.txt`)**: `근면 성실 장점 보완 필요`(정답=부정)가 **긍정**으로 분류됨(#6).
  재감사: KoTE `pos 0.48/neg 0.13/neu 0.39` → 보정 `rule4_default` → `pos-neg=+0.35` = positive.
- **규모(구조적 공백)**: §누적 로그 2026-06-24 기록 — 단점필드 **30.8%(131,566)가 여전히 positive**,
  그중 **78%가 `rule4_default` 무override**. 산발 버그가 아니라 13만 규모 구멍.
- **재현(저장 weak_kote 재생, 서버/모델 불요)**: `weak_export_260624.jsonl` 870,367행에서
  단점필드 `보완 필요`·`자기관리 필요`·`자세가 필요`류가 KoTE 긍정우세로 긍정 통과.

## 2. 원인 분석

> ⛔ 원인 확정 게이트 — 3개 충족

1. **재현했다**: `_sentence_sentiment_override_explain(0.48,0.13,'근면 성실 장점 보완 필요',True,1,neutral=0.39)` → `rule4_default`, +0.35.
2. **그 줄이 범인**: 결핍/개선요청 게이트(`has_constructive_need`·`has_improvement_request`·`has_unnegated_deficiency`)는
   **`positive_rescue` 차단 전용**(L723-733의 `and not …`)이다. positive_rescue가 안 걸리면 그대로
   `rule4_default`(L796 `pos-neg`)로 떨어져 **KoTE 긍정우세가 그대로 긍정 출력**된다. 결핍 프레이밍을
   *부정/중립으로 끌고 가는 경로가 없다*.
3. **반증 실험**: pos>neg + 결핍/개선요청일 때 중립으로 가로채면 단점필드 부→긍이 사라져야 한다(아래 §5 = 24,384 수정). 안 바뀌면 가설 오류.

- **근거**: `perspective_service.py` 보정 분기 순서(L723 positive_rescue … L796 rule4_default), 게이트 함수 L576/L630/L554.
- **핵심**: KoTE(구어 감정모델)는 "X 필요/보완"의 개선요청 화행을 칭찬으로 자주 오판 → override가 안 잡으면 누수.

## 3. 수정 방안 (additive·시그니처 불변·O(n))

- **신규 분기 `improvement_request_neutral`** (euphemistic_negative 뒤, rule1 앞):
  `pos>neg and not has_contrast and (개선요청core or 건설적필요 or 결핍)` → **중립(0.0)**.
  - **부정 아닌 중립으로만 강등** → 긍↔부 0 구조 보장(부→긍 위반 제거, 긍→부 미생성).
  - `neg≥pos` 진짜 부정은 미발동(rule3/rule4가 부정 산출). `has_contrast`는 rule1/2가 방향 판단 → 제외.
- **트랩 가드 (긍→중/긍→부 방지)**:
  - `has_constructive_need`: `필요 인물/인재/존재/인력/자원`(불가결=긍정) 제외 추가.
    ⚠️ `필요 이상`(과도=비판)은 **넣지 않음** — 전수검증서 부→긍 3건 유발 확인(가드 대상 아님).
  - `has_improvement_request`를 **core(개선요청) + 곤란(어려움)** 으로 분리. 중립화는 **core만** 사용
    ("어려움을 해결/도와줌" = 남을 돕는 긍정 트랩 제거). positive_rescue용 합집합 동작은 보존(리팩토링).
  - `_DIFFICULTY_OK`에 조력 동사(`해결/도와/도움/살피/살펴/나서/앞장/지나치`) 추가.
- **비변경**: 완전 부정화(neutral→negative)는 범위 밖(§판단 참조). is_negation_praise·욕설·시그니처 불변.

## 4. 롤백 계획

- 단일 파일(`perspective_service.py`). `improvement_request_neutral` 분기 제거 + `_NEED_POSITIVE_TAILS`/
  `_has_improvement_request_core`/`_has_difficulty_complaint` 도입분 원복. 골든 테스트 1개 파일.

## 5. 결과 (전수 재생 검증 — Pre-Done)

**전수 재생** (`weak_export_260624.jsonl` 870,367행, 저장 weak_kote 사용, 모델/서버 불요):

| 지표 | 값 |
|------|-----|
| 🔴 긍↔부 신규 교차(양방향) | **0** |
| 🟢 단점필드 positive→neutral (부→긍 위반 수정) | **24,384** |
| 단점필드 negative→neutral (개선요청=중립 정합) | 6,702 |
| 🟡 장점필드 positive→neutral (연성 긍→중) | 583 (장점 443,637의 0.13%) |

- 장점 583 중 다수는 장점칸에 적힌 **진짜 개선제안**("건강관리가 필요함"·"창의력이 필요합니다")으로
  화행상 중립이 방어가능. 소수 잔여 트랩(`필요사항/필요지식` 합성명사, "면 함께" 등)은 긍→중(긍↔부 아님).
- **회귀**: 기존 6종 전부 PASS(`test_positive_rescue`의 `legacy==explain` 동작보존 포함,
  `run_negation_praise`·`run_no_response`·`run_leadership_gate`·`test_leadership_polarity`·`test_no_response`).
  신규 골든/트랩 6종 PASS(`test/test_improvement_request_neutral.py`). `py_compile` OK.

### 검증 과정에서 차단한 오류 (전수 양방향이 잡음)
- `필요 이상`을 불가결 가드에 넣었다가 **부→긍 3건**("필요이상의 일에 시달려") → 제거.
- `필요+음절` 합성명사 가드(필요사항 등)가 `필요가 있음`(조사=개선요청)까지 제외 → **부→긍 1,031건** → 즉시 revert.
- 교훈: 가드마다 전수 양방향 재생 필수(`[[feedback_diagnose_from_symptom_not_hypothesis]]`).

## 판단 — 중립 vs 부정 (사용자 결정 반영)

- 사용자 제보는 `보완 필요`=**부정**. 본 수정은 **중립**으로 처리(사용자 승인 2026-06-30).
- 근거: ① 긍↔부 0 최우선 — 부정화는 `필요사항/필요지식`(긍정) 트랩에서 긍→부 위험(가드 시도가 위반 1,031 유발이 증거). ② 개선요청 화행 기본극성=중립(`[[project_finetune_groups_are_speechacts]]`). ③ 중립만으로 부→긍 위반(현 최악) 제거.
- **완전 부정화는 트랩 가드 추가 확보 후 후속**(neutral→negative, 별도 작업).

## 영향도 분석

- **호출 경로**: `_sentence_sentiment_override_explain`는 `sentence_sentiment_override`(L820)·refine(L2978)에서 사용 → 메타데이터/그룹분석/제출용저장의 문장 극성에 일관 반영.
- **DB**: 신규 메타데이터 생성분부터 단점 결핍 프레이밍이 긍정 미적재(중립). 기존 적재분은 재생성 시 정정.
- **성능**: 순수 문자열 O(n), KoTE 토큰 재사용 불요. 시그니처 불변.

## 운영 반영 검증 대기 (Done 승격 조건)

내부망에서 메타데이터 재생성 → 단점필드 결핍 프레이밍("보완 필요"류)이 욕설 아닌 **중립**으로 적재되고,
장점 긍정이 보존되는지 표본 확인 시 `Done` 승격.

## 핵심 파일

- `src/services/perspective_service.py` — `improvement_request_neutral` 분기 + `has_constructive_need` 가드 + `has_improvement_request` 분리(core/곤란)
- `plans/2026/0630_03_deficiency-framing-neutral/test/test_improvement_request_neutral.py` — 골든·트랩 회귀(신규)

## 불변 제약

긍↔부 0(양방향·전수검증) · 중립으로만 강등(부정 미생성) · additive·레거시 시그니처 불변(회귀 필수) · O(n) · 서버 무단 실행 금지·dev 모델재실행 불요(저장 weak_kote 재생) · plans/test 배포 제외.
