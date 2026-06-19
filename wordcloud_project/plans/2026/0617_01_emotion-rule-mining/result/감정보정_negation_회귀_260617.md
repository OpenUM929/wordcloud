# 감정보정 negation_praise 회귀 잠금 — 2026-06-17

> 계획서 §12-8 Step 3. `result/refine_diag_260617.csv`(475문장)의 KoTE 점수·is_last를
> explain()에 무손실 재투입한 변경 전/후 rule_id 비교(KoTE 재실행 불필요).

## 결과 요약: ✅ 통과

- 전체 문장: **475**
- rule_id 변경: **6건** (기대: 전부 `negation_praise`)
- 신규 분기 외 변경: **0건** 위반
- 진짜 부정(polarity=negative)의 negation_praise 전이: **0건** 기대

기존 7개 rule_id의 분기 조건·점수·시그니처는 불변이며, 변경은 오직 새 분기
`negation_praise`(부정의 부정 = 칭찬)가 중립/부정으로 강등되던 문장을 긍정으로
끌어올린 것뿐이다(중립→긍정 허용, 긍↔부 오분류 0).

## 변경 행 (전 → 후)

| id | 문장 | 변경 전(rule/score) | 변경 후(rule/score) | polarity | corrected |
|----|------|--------------------|--------------------|----------|-----------|
| 350 | 자발적으로 업무를 할 수 있도록 강압적이지 않음 | neutral_dominant / 0.0 | negation_praise / 0.544 | positive | neutral |
| 348 | 부서원들과 수평적 관계를 유지하며 고압적인 태도를 보이지 않음 | neutral_dominant / 0.0 | negation_praise / 0.467 | positive | neutral |
| 251 | 수평적 의사소통과 강압적이지않다 | neutral_dominant / 0.0 | negation_praise / 0.553 | positive | neutral |
| 60 | 업무의 중요도에 따른 관심도에 차별을 두며 고압적이지 않습니다 | neutral_dominant / 0.0 | negation_praise / 0.403 | positive | neutral |
| 332 | 권위의식이 없음 | rule4_default / -0.856 | negation_praise / 0.956 | positive | neutral |
| 141 | 직원들에게 잔소리를 안한다 | rule4_default / -0.277 | negation_praise / 0.807 | positive | neutral |
