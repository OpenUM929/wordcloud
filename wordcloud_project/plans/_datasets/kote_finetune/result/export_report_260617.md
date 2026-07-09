# 약지도 JSONL export 리포트 — 260617

> 입력: `data\new_260617.csv` · 출력: `weak_export_260617.jsonl`
> 설계: 0617_05 §5/§10/§14 · 범위=비-🟡, 라벨=3분류, 어노테이터=단독

## 요약

- 입력 행: **722**
- JSONL 기록: **713**
- PII 격리(제외): **9**
- src_hash 없음(원천 ID 결측): **0**

> ⚠️ sentiment_gold는 **잠정(모델 복사본)** — 사람 검토로 confirmed 승격 전에는 학습 금지.

## 잠정 gold 분포 (sentiment_gold)

| label | 건수 |
|---|---|
| neutral | 362 |
| negative | 351 |

## 약지도 KoTE 라벨 분포 (weak_sentiment)

| label | 건수 |
|---|---|
| negative | 444 |
| neutral | 198 |
| positive | 71 |

## 발동 규칙 분포 (applied_rule)

| rule_id | 건수 |
|---|---|
| rule4_default | 293 |
| neutral_dominant | 206 |
| no_response_neutral | 133 |
| rule3_last_low | 42 |
| rule2_contrast_lasthigh | 20 |
| positive_rescue | 14 |
| neutral_keyword | 5 |

## PII 격리 행 (§14-1 게이트 적발 — JSONL 제외)

| id | pii | 문장(앞40) |
|---|---|---|
| 567 | rrn,longnum | 11111111111111 |
| 589 | longnum | 12111111111 |
| 626 | longnum | 00000000000000 |
| 628 | longnum | 000000000000 |
| 630 | longnum | 0000000000 |
| 666 | rrn,longnum | 1111111111111111111111111111111111111111 |
| 669 | longnum | 9999999999999 |
| 717 | rrn,longnum | 1111111111111111111111111111111111111111 |
| 811 | rrn,longnum | 잘모르겠음 1111111111111111111111 |

