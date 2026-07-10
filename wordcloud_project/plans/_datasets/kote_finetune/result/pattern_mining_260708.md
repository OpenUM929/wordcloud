# 규칙/패턴 발굴 리포트 — 260708

> 데이터셋에서 다면평가 판정을 정밀화할 **규칙·패턴 후보**를 발굴(RUNBOOK §2-5 자동화).
> ⚠️ 후보 제시까지만 — 어휘집/규칙 반영은 사람 additive append + 회귀(긍↔부 0) 통과 후에만.

- 분석 레코드: **886985**

## A. 규칙이 KoTE 방향을 뒤집은 지점 (과/미보정 감사)

| applied_rule | flip 수 |
|---|---|
| no_weakness_neutral | 158535 |
| improvement_request_neg | 25219 |
| positive_rescue | 18060 |
| no_response_neutral | 13356 |
| neutral_dominant | 9373 |
| improvement_request_neutral | 7496 |
| clause_positive_rule | 5419 |
| personal_wellbeing_neutral | 4689 |
| clause_leadership_gate | 1972 |
| rule3_last_low | 1782 |
| clause_negative_rule | 782 |
| health_advice_neutral | 225 |
| no_weakness_positive | 219 |
| neutral_keyword | 193 |
| euphemistic_negative | 116 |
| excess_complaint_neg | 77 |
| negation_praise | 66 |

### 🔴 긍↔부 방향 뒤집기 (최우선 감사): **37580건**
> 규칙이 KoTE 긍↔부를 반대로 뒤집은 행. 규칙이 교정한 것인지 망친 것인지 표본 확인 필수.

- [improvement_request_neg] positive→negative: 폭 넓은 업무에 대한 관심이 필요함
- [rule3_last_low] positive→negative: 모든면에서 완벽을 기하다 보니 다소 속도가 늦기도 함
- [improvement_request_neg] positive→negative: 변전설비의 정리 및 분석에 철저함 필요
- [improvement_request_neg] positive→negative: 현장경험이 풍부하지 않아 자기개발이 필요
- [positive_rescue] negative→positive: 의견을 적극적으로 표현하여 간혹 과하게 느껴질 때가 있음
- [improvement_request_neg] positive→negative: 본인 업무에 대한 책임감을 높일 필요가 있으며 타인과 좋은 관계개선에 노력하여야 함
- [improvement_request_neg] positive→negative: 팀원들과 주기적인 소통이 필요
- [improvement_request_neg] positive→negative: 전문성에 대한 목표와 업무열의가 높아 구성원에 따른 적절한 눈높이가 필요
- [improvement_request_neg] positive→negative: 기본 예의가 필요하며, 조직에 대한 충실도가 필요
- [improvement_request_neg] positive→negative: 환경 변화를 감지 예측하고 유연하고 구체적인 계획수립이 필요함
- [improvement_request_neg] positive→negative: 폭넓은 사고와 적극적인 대인관계 필요
- [rule3_last_low] positive→negative: 퇴직 앞두셔서 부득이 8점 드립니다

## B. 긍정표지 + 직후 negation (§9 패턴)

- 비판 후보(상쇄명사 없음, 부→긍 위험): **8853**
- 칭찬 유지(상쇄명사 있음): **151**

- (비판후보) 표지'경험'+neg(비판후보): 현장경험이 풍부하지 않아 자기개발이 필요
- (비판후보) 표지'리더십'+neg(비판후보): 탁월한 리더십으로 보완이 필요없음
- (비판후보) 표지'관심'+neg(비판후보): 업무파악에 큰 관심은 없으셔서 회의 또는 보고 때 면피성 발언을 하시는데
- (비판후보) 표지'관심'+neg(비판후보): 가끔 업무에 대한 관심이 없음
- (칭찬유지) 표지'적극적'+상쇄+neg(칭찬유지): 고장등 다양한 업무에도 적극적으로 수행하며 차질없이 해냅니다
- (칭찬유지) 표지'역량'+상쇄+neg(칭찬유지): 팀원들의 역량개발과 도서현안 문제해결에 적극노력함
- (칭찬유지) 표지'탁월'+상쇄+neg(칭찬유지): 업무 능력이 탁월하며 문제점 없음
- (칭찬유지) 표지'탁월'+상쇄+neg(칭찬유지): 업무 능력이 탁월하며 문제점 없음

## C. 긍정표지 + 결핍명사(부족/부재/결여/미흡/소홀) — 지배적 부→긍 위험

- 해당 행: **24539**

- 표지'소통'+결핍: 상대방에 대한 이해 부족으로 직원간 소통 부족, 자기 중심적 사고로 업무 협업 및 화합 부족
- 표지'배려'+결핍: 자기 중심적인 사고로 부서간 배려가 부족함
- 표지'유연'+결핍: 유연성이 부족하여 부서간 갈등이 있음
- 표지'배려'+결핍: 배려가 부족함

## D. 미매칭 + 고확신 문장의 빈출 표현 (신규 표지 후보)
> 현 어휘집이 못 잡는데 KoTE는 확신(|pos-neg|>0.5)한 문장의 빈출 명사구. 표지 승격 후보(근거 검토 후).

| 표현 | 빈도 |
|---|---|
| 없음 | 19093 |
| 업무에 | 17867 |
| 최선을 | 13785 |
| 업무를 | 10824 |
| 맡은 | 9993 |
| 업무 | 9815 |
| 보완할 | 9043 |
| 다함 | 7741 |
| 없습니다 | 6723 |
| 열심히 | 6390 |
| 특별한 | 5596 |
| 항상 | 5512 |
| 있음 | 5475 |
| 딱히 | 4766 |
| 점이 | 4039 |
| 대한 | 3977 |
| 보완 | 3825 |
| 뛰어남 | 3603 |
| 능력이 | 3540 |
| 맡은바 | 3489 |
| 특별히 | 3463 |
| 너무 | 3193 |
| 사항이 | 3141 |
| 않음 | 3091 |
| 못함 | 2979 |
| 일을 | 2932 |
| 모르겠음 | 2534 |
| 찾지 | 2478 |
| 필요한 | 2452 |
| 다소 | 2447 |

## E. 절 분리 후 반전표지 잔존 (분리기 개선 후보)

- 잔존 행: **6038**

- 어학 공부 열의는 있으나
- 업무도 중요하지만
- 과업에 대한 충성도가 낮으나
- 본인의 업무는 잘 처리 하고 있으나

## 다음 행동(사람 검토 큐)
- A 긍↔부 flip + B 비판후보 + C 결핍 → **최우선** 표본 감사 → 규칙 보강/회귀.
- D 빈출 표현 → 신규 표지 후보(코퍼스 근거 확인 후 additive).
- E 잔존 → split_clauses 연결어미 보강 후보.

