# 검증용 데이터셋 요약 — 260714

> prelabel(KoTE)↔규칙 불일치 = 평가가 틀렸/어려운 케이스. 사람 확정 후 회귀·정확도 측정 기준.
> ⚠️ override도 정답 아님 — 양쪽 라벨 보존, 사람이 판정. train과 누수 분리(별 파일).

- 검증 후보(근접중복 캡 후): **214620**

## 불일치 유형

| 유형 | 수 |
|---|---|
| to_neutral | 95504 |
| pol_flip | 74299 |
| low_margin | 44817 |

## 배치별

| batch | 수 |
|---|---|
| batch_20260713_0 | 88045 |
| batch_20260709_0 | 68733 |
| batch_20260714_0 | 57842 |

## 🔴 긍↔부 flip 예 (최우선 검증, 총 74299)

- [negative→positive positive_rescue] 우선순위를 정하여 해결책 제시, 인과관계 파악
- [positive→negative improvement_request_neg] 내향적인 모습 소통시간 늘릴필요
- [positive→negative improvement_request_neg] 리더쉽과 책임감 필요
- [positive→negative improvement_request_neg] 조직내의 인간관계나 갈등 따위를 자신이 중심적으로 해결하려고 하면서 팀의 공감대 형성을 위해 노력필요
- [positive→negative improvement_request_neg] 다양한 의견 수렴 및 소통 필요
- [positive→negative improvement_request_neg] 업무에 관한 전문성을 더욱 강화해야 한다
- [positive→negative improvement_request_neg] 타 부서와의 적극적인 협업 필요
- [positive→negative improvement_request_neg] 부서원들과 함께 할수 있는 시간이 좀더 있었으면 함
- [positive→negative improvement_request_neg] 세밀한 업무파익 필요
- [positive→negative improvement_request_neg] 맡은 업무외에도 부서일에 참여하려는 적극성 필요
- [negative→positive positive_rescue] 업무 열의, 업무 전문성
- [negative→positive positive_rescue] 업무전문성및업무열의
- [positive→negative improvement_request_neg] 차분하고 고객 관리 필요
- [positive→negative improvement_request_neg] 꾸준한 자기개발이 필요합니다
- [positive→negative improvement_request_neg] 직원들과의 교류 필요

