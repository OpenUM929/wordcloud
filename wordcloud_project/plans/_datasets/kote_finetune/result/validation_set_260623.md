# 검증용 데이터셋 요약 — 260623

> prelabel(KoTE)↔규칙 불일치 = 평가가 틀렸/어려운 케이스. 사람 확정 후 회귀·정확도 측정 기준.
> ⚠️ override도 정답 아님 — 양쪽 라벨 보존, 사람이 판정. train과 누수 분리(별 파일).

- 검증 후보(근접중복 캡 후): **46791**

## 불일치 유형

| 유형 | 수 |
|---|---|
| to_neutral | 17480 |
| low_margin | 16028 |
| pol_flip | 13283 |

## 배치별

| batch | 수 |
|---|---|
| batch_20260622_2 | 29690 |
| batch_20260622_0 | 12062 |
| batch_20260623_1 | 4054 |
| batch_20260623_3 | 764 |
| batch_20260623_2 | 221 |

## 🔴 긍↔부 flip 예 (최우선 검증, 총 13283)

- [negative→positive positive_rescue] 업무에 관련한 지식,기준의 수준이 매우 뛰어나 따라가기가 힘들
- [positive→negative rule3_last_low] 부서원에게 문제가 생겼을때 부서장의 역할을 해주었으면 함
- [negative→positive positive_rescue] 타 부서와 협력과 소통
- [negative→positive positive_rescue] 강한 자기중심적 사고로 공감대 형성이 어려움
- [positive→negative rule3_last_low] 보완할점이 없습니다
- [negative→positive positive_rescue] 성과지향적인 성향이 강함
- [negative→positive positive_rescue] 다소 업무 추진에 대한 관심이 줄고 있음
- [positive→negative rule3_last_low] 모든면에 있어서 보완필요점은 없어 보입니다
- [positive→negative rule3_last_low] 직원들 의견을 두루두루 청취하여 업무에 반영하는 노력 필요
- [positive→negative euphemistic_negative] IT트렌드 등 새로운 IT활용능력을 향상시키려는 노력이 필요
- [negative→positive positive_rescue] 업무지시시 중요점과 강조사항을 구체적으로 표현해서 제시해주면 좋겠다
- [negative→positive positive_rescue] 직원들에게 불편을 최소화하기 위해 노력
- [negative→positive positive_rescue] 노동조합과의 관계 개선
- [positive→negative rule3_last_low] 신입사원들과의 더 많은 소통의 시간이 필요
- [positive→negative rule3_last_low] 븍별히 보완필요점 없음

