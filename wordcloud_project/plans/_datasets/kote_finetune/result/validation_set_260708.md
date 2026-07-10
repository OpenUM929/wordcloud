# 검증용 데이터셋 요약 — 260708

> prelabel(KoTE)↔규칙 불일치 = 평가가 틀렸/어려운 케이스. 사람 확정 후 회귀·정확도 측정 기준.
> ⚠️ override도 정답 아님 — 양쪽 라벨 보존, 사람이 판정. train과 누수 분리(별 파일).

- 검증 후보(근접중복 캡 후): **74894**

## 불일치 유형

| 유형 | 수 |
|---|---|
| to_neutral | 34794 |
| pol_flip | 24849 |
| low_margin | 15251 |

## 배치별

| batch | 수 |
|---|---|
| batch_20260708_0 | 74894 |

## 🔴 긍↔부 flip 예 (최우선 검증, 총 24849)

- [positive→negative improvement_request_neg] 폭 넓은 업무에 대한 관심이 필요함
- [positive→negative rule3_last_low] 모든면에서 완벽을 기하다 보니 다소 속도가 늦기도 함
- [positive→negative improvement_request_neg] 변전설비의 정리 및 분석에 철저함 필요
- [positive→negative improvement_request_neg] 현장경험이 풍부하지 않아 자기개발이 필요
- [negative→positive positive_rescue] 의견을 적극적으로 표현하여 간혹 과하게 느껴질 때가 있음
- [positive→negative improvement_request_neg] 본인 업무에 대한 책임감을 높일 필요가 있으며 타인과 좋은 관계개선에 노력하여야 함
- [positive→negative improvement_request_neg] 팀원들과 주기적인 소통이 필요
- [positive→negative improvement_request_neg] 전문성에 대한 목표와 업무열의가 높아 구성원에 따른 적절한 눈높이가 필요
- [positive→negative improvement_request_neg] 기본 예의가 필요하며, 조직에 대한 충실도가 필요
- [positive→negative improvement_request_neg] 환경 변화를 감지 예측하고 유연하고 구체적인 계획수립이 필요함
- [positive→negative improvement_request_neg] 폭넓은 사고와 적극적인 대인관계 필요
- [positive→negative rule3_last_low] 퇴직 앞두셔서 부득이 8점 드립니다
- [negative→positive positive_rescue] 업무협업 능력이 뛰어나므로 업무조정 및 협의에 장시간소요
- [negative→positive positive_rescue] 우선순위를 정하여 해결책 제시
- [positive→negative improvement_request_neg] 타 부서와의 협조를 통한 정보 입수와 소통 필요

