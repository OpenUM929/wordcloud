# 규칙/패턴 발굴 리포트 — 260714

> 데이터셋에서 다면평가 판정을 정밀화할 **규칙·패턴 후보**를 발굴(RUNBOOK §2-5 자동화).
> ⚠️ 후보 제시까지만 — 어휘집/규칙 반영은 사람 additive append + 회귀(긍↔부 0) 통과 후에만.

- 분석 레코드: **2705461**

## A. 규칙이 KoTE 방향을 뒤집은 지점 (과/미보정 감사)

| applied_rule | flip 수 |
|---|---|
| no_weakness_neutral | 489194 |
| improvement_request_neg | 83492 |
| positive_rescue | 54207 |
| no_response_neutral | 36579 |
| neutral_dominant | 29788 |
| improvement_request_neutral | 27071 |
| clause_positive_rule | 15680 |
| personal_wellbeing_neutral | 15027 |
| garbage_line_neutral | 6311 |
| clause_leadership_gate | 5899 |
| rule3_last_low | 5466 |
| clause_negative_rule | 2480 |
| health_advice_neutral | 666 |
| neutral_keyword | 643 |
| no_weakness_positive | 550 |
| excess_complaint_neg | 343 |
| euphemistic_negative | 329 |
| negation_praise | 206 |

### 🔴 긍↔부 방향 뒤집기 (최우선 감사): **118215건**
> 규칙이 KoTE 긍↔부를 반대로 뒤집은 행. 규칙이 교정한 것인지 망친 것인지 표본 확인 필수.

- [positive_rescue] negative→positive: 우선순위를 정하여 해결책 제시, 인과관계 파악
- [improvement_request_neg] positive→negative: 내향적인 모습 소통시간 늘릴필요
- [improvement_request_neg] positive→negative: 리더쉽과 책임감 필요
- [improvement_request_neg] positive→negative: 조직내의 인간관계나 갈등 따위를 자신이 중심적으로 해결하려고 하면서 팀의 공감대 형성을 위해 노력필요
- [improvement_request_neg] positive→negative: 다양한 의견 수렴 및 소통 필요
- [improvement_request_neg] positive→negative: 업무에 관한 전문성을 더욱 강화해야 한다
- [improvement_request_neg] positive→negative: 타 부서와의 적극적인 협업 필요
- [improvement_request_neg] positive→negative: 부서원들과 함께 할수 있는 시간이 좀더 있었으면 함
- [improvement_request_neg] positive→negative: 세밀한 업무파익 필요
- [improvement_request_neg] positive→negative: 맡은 업무외에도 부서일에 참여하려는 적극성 필요
- [positive_rescue] negative→positive: 업무 열의, 업무 전문성
- [positive_rescue] negative→positive: 업무전문성및업무열의

## B. 긍정표지 + 직후 negation (§9 패턴)

- 비판 후보(상쇄명사 없음, 부→긍 위험): **26973**
- 칭찬 유지(상쇄명사 있음): **400**

- (비판후보) 표지'모범'+neg(비판후보): 전문적이고 타인의 모범이됨 나무람없이 뛰어남(세심하고 노력함)
- (비판후보) 표지'동료'+neg(비판후보): 낯가림이 조금 심한편이어서 주변 동료들과 어울리지 못하는 경향이 있음
- (비판후보) 표지'적극적'+neg(비판후보): 업무에 적극적이고 자기일이 아니더라도 주도적으로 업무를 처리하여 부서 전체 능률을 올림
- (비판후보) 표지'적극적'+neg(비판후보): 업무에 적극적이고 자기일이 아니더라도
- (칭찬유지) 표지'소통'+상쇄+neg(칭찬유지): 동일 업무하는 다른 직원들과 소통이 없어서 간혹 갈등이 있다
- (칭찬유지) 표지'의사소통'+상쇄+neg(칭찬유지): 수평적 의사소통으로 문제점 없음
- (칭찬유지) 표지'책임감'+상쇄+neg(칭찬유지): 맡은업무에 책임감을 가지고 차질없이 업무 수행함
- (칭찬유지) 표지'동료'+상쇄+neg(칭찬유지): 친근한 이미지로 동료직원들과 어려움 없으며 적극적인 리더십

## C. 긍정표지 + 결핍명사(부족/부재/결여/미흡/소홀) — 지배적 부→긍 위험

- 해당 행: **70565**

- 표지'협업'+결핍: 업무협업 능력이 부족함
- 표지'소통'+결핍: 부드러운 리더쉽으로 문제해결을 하나 가끔씩 소통의 부재가 있을 때가 있음
- 표지'성과'+결핍: 성과기여도가 다소 부족함
- 표지'지식'+결핍: 업무지식이 다소 부족함

## D. 미매칭 + 고확신 문장의 빈출 표현 (신규 표지 후보)
> 현 어휘집이 못 잡는데 KoTE는 확신(|pos-neg|>0.5)한 문장의 빈출 명사구. 표지 승격 후보(근거 검토 후).

| 표현 | 빈도 |
|---|---|
| 없음 | 60234 |
| 업무에 | 55046 |
| 최선을 | 42973 |
| 업무를 | 30898 |
| 맡은 | 30572 |
| 업무 | 28384 |
| 보완할 | 27674 |
| 다함 | 24277 |
| 없습니다 | 19423 |
| 항상 | 18564 |
| 열심히 | 18069 |
| 있음 | 16629 |
| 특별한 | 16388 |
| 딱히 | 14392 |
| 점이 | 13041 |
| 보완 | 12187 |
| 대한 | 11435 |
| 뛰어남 | 11369 |
| 능력이 | 10501 |
| 맡은바 | 10456 |
| 너무 | 10091 |
| 특별히 | 10001 |
| 사항이 | 9967 |
| 않음 | 9935 |
| 못함 | 8687 |
| 일을 | 8541 |
| 필요한 | 7357 |
| 업무처리 | 7344 |
| 다소 | 7265 |
| 모르겠음 | 7153 |

## E. 절 분리 후 반전표지 잔존 (분리기 개선 후보)

- 잔존 행: **17548**

- 업무량이 많음에도 불구하고
- 전문성은 좋으나
- 특별히 두드러진 행동은 없지만
- 지금도 강력한 리더십을 보유하시지만

## 다음 행동(사람 검토 큐)
- A 긍↔부 flip + B 비판후보 + C 결핍 → **최우선** 표본 감사 → 규칙 보강/회귀.
- D 빈출 표현 → 신규 표지 후보(코퍼스 근거 확인 후 additive).
- E 잔존 → split_clauses 연결어미 보강 후보.

