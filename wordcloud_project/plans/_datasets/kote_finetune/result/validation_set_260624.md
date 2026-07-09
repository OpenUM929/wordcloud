# 검증용 데이터셋 요약 — 260624

> prelabel(KoTE)↔규칙 불일치 = 평가가 틀렸/어려운 케이스. 사람 확정 후 회귀·정확도 측정 기준.
> ⚠️ override도 정답 아님 — 양쪽 라벨 보존, 사람이 판정. train과 누수 분리(별 파일).

- 검증 후보(근접중복 캡 후): **51724**

## 불일치 유형

| 유형 | 수 |
|---|---|
| to_neutral | 20683 |
| low_margin | 17267 |
| pol_flip | 13774 |

## 배치별

| batch | 수 |
|---|---|
| batch_20260624_0 | 37308 |
| batch_20260624_1 | 14416 |

## 🔴 긍↔부 flip 예 (최우선 검증, 총 13774)

- [negative→positive positive_rescue] 성과기여도, 업무열의, 전문성, 협업능력, 윤리의식
- [negative→positive positive_rescue] 업무전문성, 타부서와 협업
- [negative→positive positive_rescue] 종합적인 문제해결능력
- [negative→positive positive_rescue] 수평적 의사소통을 원합니다
- [positive→negative rule3_last_low] 한번 결정한 것은 끝까지 밀어붙이는 성격
- [negative→positive positive_rescue] 업무 실행력, 대안제시
- [negative→positive positive_rescue] 요청하는 것이 명확함
- [negative→positive positive_rescue] 공감성 이해력 다양성
- [negative→positive positive_rescue] 직원들 업무에 관심이 많음
- [positive→negative rule3_last_low] 스트레스를 오래 가져가지 않음
- [negative→positive negation_praise] 직원들에게 고압적인 태도를 보이지 않음
- [negative→positive positive_rescue] 성과기여도 업무열의
- [negative→positive positive_rescue] 성과기여도, 업무열의, 전문성, 협업능력, 윤리의식
- [negative→positive positive_rescue] 적극적인 업무태도, 약자 배려
- [negative→positive positive_rescue] 무책임한 자세로 업무에 임함

