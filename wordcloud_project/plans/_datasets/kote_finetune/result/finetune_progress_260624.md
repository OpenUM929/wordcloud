# KoTE 파인튜닝 준비 — 신규 그룹 발굴 진행 리포트 (D1→D5, 260624)

> 계획서 `plans/2026/0624_04_emotion-clustering`. 보고서용 통합 히스토리.
> 핵심가치: 긍↔부 오분류 0(양방향) · 군집≠gold · 신규그룹 기본극성 neutral.

## 0. 한 줄 요약

다면평가 87만 문장 중 **KoTE가 못 잡는 56%(484K)** 를 무지도 군집 → 3대 화행으로 수렴 → 신규 그룹 **G1 약점부재·G2 개선요청**(둘 다 neutral)을 발굴·라벨. **G2의 현 규칙 3분열(긍8,496/부26,906/중12,816)=긍↔부 누수**가 neutral 그룹화로 닫힘. 전체 176,483건 weak 전파(학습 볼륨) + 대표 gold 1,318 + 전/후 비교 baseline 1,500 동결.

## 1. 단계별 결과

| 단계 | 내용 | 결과 | 산출 |
|------|------|------|------|
| **D1** 군집 | KoTE 미피복(없음∪저신뢰<0.4∪rule4_default) 멀티뷰 군집 | 484,119(56%) → 24군집, k선택 silhouette 0.134 | `emotion_clusters_260624.md`, `cluster_emotion.py` |
| **D3** 후보 | 24군집 → 화행 패밀리 승격 판정(4조건) | G1 약점부재·G2 개선요청 승격(neutral), G3 역량서술 보류(안심/신뢰 기피복) | `emotion_new_groups_260624.md` |
| **D4** 대표 | 멤버 태깅 + 대표 판정 패킷 + AI 1차판정 + baseline 동결 | G1 128,265·G2 48,218. gold후보 1,318·needs_human 679(ai_reference 동봉)·trap 3 | `eval/group_packet_*`, `group_gold_candidates_*`, `group_needs_human_*`, `baseline_eval_*` |
| **D5** 전파 | 전체 멤버 weak 라벨(학습 볼륨) | 176,483 전파: neutral 166,334 / positive 9,627(칭찬형) / negative 326 / trap제외 196 | `emotion/group_weak_260624.jsonl`, `group_weak_d5_260624.json` |

## 2. 핵심 발견 (보고 포인트)

1. **KoTE의 구조적 사각 = 56%.** 44 감정이 전부 정서라 인사평가 *화행*(요청·선언·사실서술)에 레이블이 없어 28%가 "없음"·15%가 저신뢰. → 정서가 아니라 **화행 그룹**을 추가해야 한다는 게 데이터로 증명됨.
2. **긍↔부 누수의 정체 = 화행의 극성 강제.** 같은 개선요청(G2 48,218)이 현 규칙에서 긍8,496/부26,906/중12,816로 분열. 화행을 neutral 그룹으로 라벨하면 강제 분류가 사라져 **부→긍 누수 8,496이 구조적으로 소멸**.
3. **칭찬형은 분리 보존.** "완벽한 사람이라 보완점 없음" 류 9,627건은 neutral로 강제하지 않고 positive 유지 → 긍→부 역오염 방지(양방향 긍↔부 0).

## 3. 파인튜닝 전/후 비교 설계 (동결)

- **baseline_eval_260624.jsonl(1,500)**: 층화 표본 + 현 규칙 라벨 `rule_label_before` 동봉. `gold`(사람/AI 정답)는 held-out.
- **before** = 현 규칙 파이프라인 정확도(baseline). **after** = 파인튜닝 KoTE를 동일 셋 재채점.
- 비교 지표: ① 긍↔부 오분류 수(양방향, 0 목표) ② 3분류 정확일치율 ③ "없음"/저신뢰 → 화행 그룹 회수율.

## 4. 사람 확인 대기 (ai_reference 동봉)

- `eval/group_needs_human_260624.jsonl` — 칭찬형/강부정/저신뢰 경계. 각 행에 **내 판정(`ai_reference`: polarity·confidence·reason)** 을 참고로 넣음(사람 판단과 대조용). `human_decision` 칸은 비움.
- 분포: G1 666(대부분 칭찬형 positive 경계), G2 13. 강부정형은 ai_reference=negative.

## 5. 다음

- **D5-잔여**: 신규 그룹 2종 택소노미 문서 반영(ROADMAP/RUNBOOK) + needs_human 사람 확인 회수.
- **D6(사용자 결정)**: export/split → KoTE 파인튜닝 → baseline 재채점으로 전/후 비교 리포트.

## 산출 파일 색인
- 스크립트: `cluster_emotion.py` · `extract_group_gold.py` · `judge_group_packet.py` · `propagate_group_weak.py`
- 군집/후보: `result/emotion_clusters_260624.md` · `result/emotion_new_groups_260624.md`
- gold/weak: `eval/group_gold_candidates_260624.jsonl`(1,318) · `emotion/group_weak_260624.jsonl`(176,483) · `eval/group_needs_human_260624.jsonl`(679)
- 비교: `eval/baseline_eval_260624.jsonl`(1,500)
- 요약(JSON): `result/group_gold_d4_*` · `group_judge_d4_*` · `group_weak_d5_*`
