# 감정 p/n/u 분류 감사 — batch_20260622_0 (다면평가 363,728행)

> 2026-06-22 · 핵심가치 긍↔부 0 측정. **파일 `y`/`s`/`e`(KoTE 출력)는 정답 아님 → 문장 직접 재판정**(메모리 `feedback_distrust_prelabels_reanalyze`).
> 가명화 통계·패턴만 기록(원문 최소 예시는 내부망 전용, PII 정규식 게이트 통과분). plans/ 배포 제외.

## 1. 측정 방법 (정직)
- KoTE 재실행 없이 파일 `s=[pos,neg,neu]`를 **실제 보정 파이프라인** `perspective_service._sentence_sentiment_override_explain(pos,neg,text,is_last=True,total=1,neutral)`에 투입 → 최종 p/n/u 산출(O(n), 서버·배치·GPU 불요).
- **감사 기준셋(reference)**: 내가 직접 판정한 층화 표본 165문장(결핍40·부정표지40·저마진35·긍정표지25·무작위25). 파일 라벨 미신뢰.
- ⚠️ 한계: `is_last=True`로 **단문 단독 평가**. production은 문서(다문장) 맥락에서 `is_last`가 달라 일부 규칙(rule3/euphemistic)이 다르게 동작 → 아래 B2는 맥락 의존(artifact 가능성).

## 2. 감사셋 대비 결과 (165문장)
- 전체 불일치 **13/165** (92.1% 일치).
- **긍↔부 핵심가치 위반 1건** — 혼합·양보 문장("업무품질 좋다 (단,…낮은 퀄리티…압박 필요)"). positive_rescue. 모호(내 gold=n).
- 나머지 12 = **중립 경계**(p→u 8, n→u 2, u↔ 2). 대부분 KoTE가 짧은 명사구에 `s=[0,0,0]` 무신호 → 중립 강등(중립↔긍정은 허용 범주).

## 3. 코퍼스 전수 — 규칙이 KoTE 방향을 뒤집는 지점 (오류 집중 구역)
규칙 발동 분포(363,728): positive_rescue 264,973 · rule4_default 84,799 · neutral_dominant 5,439 · rule2_contrast 4,487 · no_response_neutral 2,935 · rule3_last_low 715 · neutral_keyword 157 · negation_praise 148 · euphemistic_negative 25.

### A. 부→긍 (positive_rescue) — 🔴 진짜 production 버그 **50건**
- 패턴: **긍정표지(관심/책임감/업무열의/경험/배려…) 직후 부정어(없다/부족)** 인데 `positive_rescue`의 `neg<0.85` 게이트만으론 못 막아 긍정 상향.
  - 예: `업무에 관심이 없다`(s=[0.07,**0.83**,0.1])·`책임감이 없습니다`(0.77)·`업무열의가 없음`(0.79)·`근무경험이 없어 평가유보`.
- 원인 = **§9 positive-negation 비대칭이 `positive_rescue` 게이트에 존재**(긍정표지 평면매칭, 직후 negation 미인식). leadership_polarity가 아니라 **여기**가 정확한 위치.
- **is_last 무관 → production 동일 발동.** 핵심가치 직결.

### B1. 긍→부 (euphemistic_negative, negation 무시) — 🔴 진짜 버그 **8건(고유 1문장)**
- `보완이 필요하지 않으며 높은 평가`(s=[0.94,…]) → "보완이 필요"가 STRONG_NEGATIVE_PHRASES 매칭하나 **`하지 않으며` negation 무시** → 부정 반전.
- is_last 필요(문서 끝일 때만 production 발동).

### B2. 긍→부 (rule3_last_low) — ⚠️ 맥락 의존 **265 후보**
- `기술적으로 너무 뛰어남`·`공정한 업무 수행`·`원만한 갈등을 해결`(KoTE pos>neg) 인데 `is_last + 저신뢰 + strength>0.5` → 부정 강등.
- 단, rule3는 **다문장 평가의 마지막 문장 = 핵심 비판** 가설(0617_01) — **단독 단문 평가 artifact**일 수 있음. 일부는 진짜 중립/부정("적을만한 장점은 없습니다"). **production 문서맥락 검증 선결** → 일괄 수정 금지.

## 4. 결론 (정직)
- 현 파이프라인은 **이미 긍↔부 ~99%**(감사셋 164/165, 결핍문은 KoTE neg로 이미 부정 정분류). 이전 세션의 "결핍 부→긍 미탐 161건"은 **`leadership_polarity` 단독 측정 오류**(감정분류엔 미사용).
- "100% 구분"의 실제 지렛대:
  1) **A 수정**(부→긍 50): positive_rescue에 positive-negation 가드 신설(§9 패턴, 올바른 위치). additive·회귀.
  2) **B1 수정**(긍→부 8): euphemistic_negative에 negation 인식.
  3) **B2**: 단독평가 artifact 여부 production 맥락 확인 후 결정(일괄수정 금지).
  4) 중립→긍정 누락(짧은 명사구): POSITIVE_IMPLYING_PHRASES additive 보강(긍↔부 안전, 중립↔긍정 허용).

## 5. 구현 결과 (2026-06-22 — A·B1 수정, 회귀 통과)
규칙 트랙 P3 범위로 **A·B1만** 수정(B2/중립보강은 보류). 위치 = `perspective_service`(production 감정보정).

### A. positive_rescue에 positive-negation 가드 신설 (`positive_marker_directly_negated`)
- 긍정표지 직후 좁은 창(3자)에서 bare negation(없다/없음/않…) 직접 부정 → 구제 차단.
- **trap 제외(긍→부 0)**: ① 강조어 어간(아낌없이·끊임없이·막힘없는) ② `없이/없는/없을`(비종결=강조·관계절·시간) ③ 재부정·양보 ④ 양면표지(개선·예측·효율·대안·해결책·문제해결) 가드 제외 ⑤ 표지~negation 사이 단어가 끼면(안전사고도 없음) 창 밖.
- `부족/미흡/안 되`는 기존 `NEGATIVE_IMPLYING_WORDS`가 이미 차단(중복 아님).

### B1. euphemistic_negative에 negation 인식 (`has_unnegated_strong_negative`)
- `보완이 필요`+`하지 않으며` = 칭찬 → 부정 반전 금지. 진짜 완곡부정(개선이 필요한 부분이 많음)은 그대로 부정.

### 검증 (전체 코퍼스 old→new, 고유 문장)
| 변화 | 건수 | 판정 |
|---|---|---|
| p→n (부→긍 교정: 관심이 없다·책임감이 없습니다) | 27 | ✅ A |
| n→p (긍→부 교정: 보완이 필요하지 않으며) | 1 | ✅ B1 |
| p→u (평가유보 → 중립) | 12 | ✅ 허용(중립) |
| **신규 긍↔부 오류** | **0** | ✅ 양방향 0 |
- 가드 발동 184문장 전수 = 진짜 부정(`없이/없는/없을` 오탐 0). 회귀: `test_positive_rescue`(신규 3종)·`test_no_response`·`test_leadership_polarity`·`run_negation_praise_regression`·`run_no_response_regression` 전부 통과.

### 보류(정직)
- **B2(rule3_last_low 265 후보)**: 단독-단문 평가 artifact 가능 → production 문서맥락(`is_last`) 검증 선결. 일괄수정 금지.
- **중립→긍정 누락(짧은 명사구)**: 핵심가치 위반 아님 → 다음 턴 POSITIVE_IMPLYING_PHRASES 보강.
- **gold 미적재**: 이번은 규칙 트랙 한정. gold 확정·스트림 append는 별도(P1 검토 UI·범위 결정 후).
- 직전 세션의 `leadership_polarity` 결핍어 급조분은 **전부 원복**(감정분류 미사용 — 측정 오류였음).
