# 분할/중복제거/품질 리포트 — 2026-06-17

> 입력: `weak_export_260617.jsonl` · 출력: `weak_export_260617.split.jsonl`
> 설계: 0617_05 §8 · dup_cap=10, 비율 train/val/test=80/10/10

## 요약

- 입력 행: **713**
- 중복제거 후: **713** (드롭 0)
- 그룹 누수: **없음** (동일 src_hash가 복수 split에 걸치지 않음)

## split 분포

| split | 행 | 평가자(그룹) 수 |
|---|---|---|
| test | 89 | 32 |
| train | 554 | 230 |
| val | 70 | 25 |

## split별 잠정 gold(sentiment) 분포

**test**

| label | 건수 |
|---|---|
| negative | 52 |
| neutral | 37 |

**train**

| label | 건수 |
|---|---|
| neutral | 289 |
| negative | 265 |

**val**

| label | 건수 |
|---|---|
| neutral | 36 |
| negative | 34 |

> ⚠️ positive 잠정 gold가 희소하면(§8) 긍정 gold 확보가 선결 — 학습 전 사람 검토 필요.

