# 데이터셋 파이프라인 실행 요약 — 260708

> 입력: `batch_20260708_0` · 단일 명령 자기실행(dataset_pipeline.py)

- 판정: **🔴 FAIL**
- 입력 행: **868889**
- 기록 레코드: **886985** (문장 867889 + 절 19096)
- PII 격리: **1000**
- 회귀(긍↔부 0): **실패**

## 기계검증 게이트

- [x] 입력>0 이면 기록>0 (입력 868889 / 기록 886985)
- [ ] 회귀(긍↔부 0) 통과
- [x] PII 격리 행은 미기록(스냅샷 제외)

## 감정 약지도 분포(문장)

- positive: 523104
- negative: 144597
- neutral: 200188

## 절(혼합 분해) 약지도 분포

- positive: 6987
- negative: 1186
- neutral: 0
- uncertain: 10923

## 회귀 실패 상세

- test_positive_rescue.py (exit 1): [OK] 진짜 부정 3건 → 어떤 점수에서도 구제 안 됨(positive_rescue/negation_praise 모두)
[OK] negation 칭찬 → negation_praise 긍정 상향(중립→긍정, 긍↔부 안전)
[OK] 긍정표지 직접부정 → 구제차단·부정(부→긍 0)
[OK] 강조어/상쇄/양면표지/없이·없는 trap → 차단 안 됨(긍→부 0)
test_euphemistic_negative_respects_negation
    assert rule != 'euphemistic_negative' and score > 0, f'{s_pos} -> {rule}/{score}'
AssertionError: 보완이 필요하지 않으며 높은 평가를 드리고 싶음 -> no_weakness_neutral/0.0


## §누적 로그용 1행(RUNBOOK에 붙여넣기)

```
| 2026-07-08 | 1배치(batch_20260708_0) | 868889 | 886985 (문장867889+절19096) | 1000 | 0(weak-only) | weak 523104 | split_clauses+리더십LF | (미실행) | 회귀 🔴·긍↔부0·패턴리포트 pattern_mining_260708 |
```

