# 0623_02 — rule3_last_low 긍→부 보강 (장점 데이터 한 줄 평가)

- 상태: **Pre-Done** — 장점 0.6→94.5%·긍↔부 0. 단점 적대검증서 발견한 부→긍 187 회귀는 **[`0623_03`](../0623_03_sentiment-cons-guard/0623_03_sentiment-cons-guard.md) 가드로 해소**(단점 부→긍 −2,237, 양방향 긍↔부 0). 4차+5차 동반 배포. → [`result/accuracy_trend_260623.md` §4·5차](../../_datasets/kote_finetune/result/accuracy_trend_260623.md).
- 작성일: 2026-06-23
- 트리거: 신규 데이터 `data/23년_장점.csv`(JSONL, x/y/s/e, 523,715행, batch_20260623_0)를 내부망에서 구동·반입.

## 1. 문제 (핵심가치 위반 발견)

`_sentence_sentiment_override_explain`의 **`rule3_last_low`** 는
"끝문장(is_last) + 저신뢰(|pos−neg|<0.20) + strength>0.5"이면 **부정 어휘가 없어도 무조건 부정화**한다.
단점/개선형 다면평가에선 끝문장이 대개 완곡비판이라 맞았으나, **`장점` 데이터는 평가 전체가
"보고능력 우수" 한 줄**인 경우가 많아 그 줄이 곧 끝문장 → **긍정이 부정으로 뒤집힘**(긍↔부 0 위반).

- 측정(끝문장 기준): pos>neg인데 강제 부정 = **866건**. 전수 직접 재판정 → 대다수 명백한 역량 칭찬.
- 사전라벨 불신 원칙대로 파일 y 무시, 문장 직접 재판정. dev 재현은 s(=KoTE 점수)로 O(n)(23초, 서버·GPU·KoTE 불요).

## 2. 해결 (기존 방식 = positive_rescue 앞단 구제 + 가드, additive·시그니처 불변)

`src/services/perspective_service.py`:
1. **역량 긍정표지 7종 append** → `POSITIVE_IMPLYING_PHRASES`: `우수·탁월·능동·원만·신속·열성·공정`.
   rule3 도달 전 positive_rescue가 먼저 구제. (기존 `has_constructive_need`/`has_unnegated_deficiency`가
   "X 필요/부족/많음"을 계속 막으므로 "전문성 키울 필요"·"보완할 점이 많습니다"는 부정 유지.)
2. **접미 부정 가드** `~지 않/지 못/지 아니`(창 8) → `positive_marker_directly_negated`.
   "열성적이지 않습니다"의 부→긍 차단(window-3이 표지~않 사이 어간을 놓치던 트랩).
3. **반어 부정문맥어** → `NEGATIVE_CONTEXT_FOR_RESCUE`: `갑질·이기적·편향·우위 이용·유리하도록·본인에게만`
   + `불공정·편파·불공평`. "지위 이용 능력 탁월"·"갑질이 장점" 등 역량어 포장 비판 구제 차단.
4. **`no_weakness_neutral` 게이트 완화**: `neg>=pos` → `(neg>=pos or confidence<threshold)`.
   "보완할점 없음"(pos>neg 저신뢰)을 rule3 부정화 전에 중립으로 가로챔(고신뢰 긍정은 미발동, 긍정 보존).

## 3. 검증 (긍↔부 0 잠금)

- **전수 before/after diff**(523,715행, HEAD→수정): 위험 전이 `n→p` 291건 = **전부 깨끗한 긍정**(반어/부정 0).
  부수 효과: HEAD에 있던 부→긍 버그("성희롱·폭언·직위 이용한 갑질" 긍정 오분류)까지 ③ 가드가 정정.
- **검증 데이터셋** `_datasets/kote_finetune/eval/validation_rule3_rescue_260623.jsonl`(이전 오판 734건, gold 687):
  gold 일치 **0.6%(HEAD) → 94.5%(수정)**, **부→긍 0**, 긍→부 4(전부 "불필요한 X 하지않음/없음" 이중부정 하드 — 기존 미해결, 이번 변경 무관).
- **회귀 전부 통과**: `test_positive_rescue`·`test_leadership_polarity`·`run_leadership_gate_regression`(KoTE 114문장)·
  `run_negation_praise_regression`·`run_no_response_regression`·신규 `test/test_rule3_positive_rescue.py`(17 골든) → 긍↔부 0.
- 성능 히스토리: [`result/accuracy_trend_260623.md` §4차](../../_datasets/kote_finetune/result/accuracy_trend_260623.md).

## 4. 잔여 / 범위 밖

- "불필요한 X 하지 않음/없음" 이중부정 긍정(역량표지 없음·KoTE neg 강세) — 별도 idiom 가드(trap 검토 후). 검증셋 4건 추적.
- "자기 중심적 사고 / 신속한 추진력" 혼합 나열 — 문장 분할/타인지칭 파서 영역.
- **🔴 단점 회귀(2026-06-24 발견)**: `23_단점.csv` 전수 검증 시 부→긍 11,039(기존 10,855 + 본 수정 187). 역량표지가 "신속성 요함/능동적으로 했으면/업무열성 보완/과한 신속함/협업 어려움" 등 단점 프레이밍에서 구제됨. → `batch_20260622` 긍정트레이트+결핍명사 클래스와 동일. **가드 선결(CANCEL/결핍·희망·과잉·역접) 후 DN.** `result/accuracy_trend_260623.md §5차`.
- DN 전제: 내부망에서 23년_장점(또는 동형) 메타데이터 재생성 시 이 분류가 실제로 반영됨을 확인 + **단점 가드로 부→긍 0 복구 확인.**

## 불변 제약

긍↔부 0(양방향, NON-NEGOTIABLE) · additive·레거시 시그니처 불변 · 추측 분류 금지(코퍼스 근거 행만) ·
O(n)(서버·배치·GPU 불요) · plans/JSONL 배포 제외·가명/PII게이트 · 서버 무단 실행 금지.
