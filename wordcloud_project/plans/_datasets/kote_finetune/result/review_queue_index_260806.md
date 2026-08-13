# 검토큐 지도·근거 대장 (2026-08-06 재편)

> 게시판 `/group-review` 는 `eval/review/` **최상위 `.jsonl` 만** 파일명 알파벳순으로 나열한다.
> 따라서 접두어 `P1_ < P2_ < P3_` 가 곧 검토 우선순위다. 하위 폴더(`_archive/`)는 노출되지 않는다.
> 이 문서는 `scripts/build_review_index_260806.py` 로 현재 파일에서 재생성한다(멱등).

## 1. 우선순위 정의

| 등급 | 정의 |
|---|---|
| **P1** | 긍↔부 뒤바뀜 후보 — 핵심 가치 직결. 규칙 자동 처리 금지, 전건 사람 판정. |
| **P2** | 극성↔중립 경계·양가·화행 — 규칙 프리필 후 잔여. |
| **P3** | 대량 유니크 풀 — 티어링 전수 판정 대상. 개별 가치는 낮으나 모델 과부정 패턴의 발굴원. |

## 2. 현재 판정 대상 (게시판 노출)

| 파일 | 전체 | **미판정** | 프리필 | 출처 | 산출 스크립트 |
|---|---:|---:|---:|---|---|
| `P1_prod25_flip_neg2pos_260806.jsonl` | 2314 | **2314** | 144 | 2025 실배치 감사(260716) | `audit_screen_prod_260716 → audit_stratify_prod_260716 → audit_extract_queue_260716 (시드 20260716)` |
| `P1_prod25_flip_pos2neg_260806.jsonl` | 533 | **533** | 5 | 2025 실배치 감사(260716) | `동상` |
| `P2_8a_other_pos__care_260703.jsonl` | 184 | **178** | 0 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__comm_260703.jsonl` | 1027 | **972** | 16 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__degree_260703.jsonl` | 467 | **314** | 16 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__drive_260703.jsonl` | 1538 | **1355** | 23 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__etc_260703.jsonl` | 1288 | **1225** | 11 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__expert_260703.jsonl` | 506 | **471** | 17 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__leader_260703.jsonl` | 109 | **102** | 0 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8a_other_pos__trait_260703.jsonl` | 65 | **62** | 0 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8b_other_neg__degree_260703.jsonl` | 108 | **70** | 13 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8b_other_neg__etc_260703.jsonl` | 881 | **844** | 29 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8b_other_neg__trait_260703.jsonl` | 60 | **59** | 1 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__accuracy_260703.jsonl` | 33 | **24** | 7 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__comm_260703.jsonl` | 317 | **113** | 195 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__degree_260703.jsonl` | 45 | **29** | 11 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__drive_260703.jsonl` | 94 | **49** | 32 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__expert_260703.jsonl` | 102 | **35** | 55 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__it_260703.jsonl` | 43 | **17** | 26 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_8c_other_neu__trait_260703.jsonl` | 144 | **80** | 60 | 검토큐 그룹재편(260703) | `split_by_group_260703.py` |
| `P2_bareNP_r4_260707.jsonl` | 233 | **233** | 0 | 맨명사구 라운드 | `mine_bareNP_r4_260707.py` |
| `P2_bareNP_r5_260707.jsonl` | 228 | **228** | 0 | 맨명사구 라운드 | `mine_bareNP_r4_260707.py` |
| `P2_hard_escalate_260707_c2.jsonl` | 8 | **8** | 8 | 하드샘플 escalation | `prefill_hard_queue.py` |
| `P2_hard_prefilled_260707_c2.jsonl` | 203 | **203** | 203 | 하드샘플 프리필 | `prefill_hard_queue.py` |
| `P2_hard_prefilled_260707_c3.jsonl` | 244 | **244** | 244 | 하드샘플 프리필 | `prefill_hard_queue.py` |
| `P2_hard_queue_260713.jsonl` | 151 | **151** | 151 | 하드샘플 마이닝 | `mine_hard_samples 계열` |
| `P2_hard_queue_260715.jsonl` | 127 | **127** | 17 | 하드샘플 마이닝 | `mine_hard_samples 계열` |
| `P2_pattern_D_traitpos_review_260715.jsonl` | 101 | **101** | 101 | 패턴 D 마이닝(260715) | `build_pattern_gold_260715.py` |
| `P2_prod25_ambivalent_260806.jsonl` | 795 | **795** | 456 | 2025 실배치 감사(260716) | `동상` |
| `P2_speechact_r6_260707.jsonl` | 56 | **56** | 0 | 화행 라운드 | `mine_speechact_r6_260707.py` |
| `P3_packet_b346_pool_260714.jsonl` | 287 | **287** | 157 | 대량 판정 패킷 버킷 풀(260714) | `judge_packet_260714.py` |
| `P3_packet_review_pool_260714.jsonl` | 9266 | **9266** | 671 | 대량 판정 패킷 유니크 풀(260714) | `judge_packet_260714.py` |
| **합계** | **21557** | **20545** | **2669** | | |

## 3. 큐에서 제외한 것 — 사유별 (삭제 아님, 근거로 보존)

| 사유 | 행수 |
|---|---:|
| 중복 — 우선순위 높은 파일을 정본으로 채택 | 1518 |
| 큐에서 제외(silver = 규칙·모델 합의 자동분. 사람 판정 대상이 아니며 학습 silver 로만 쓴다) | 772 |
| 정식 gold 에 이미 확정 라벨이 있음 — 재판정 불요 | 292 |
| 큐에서 제외(260714 블라인드 감사 산출물(표본·불일치 기록). 판정 대상이 아니라 감사 증적) | 141 |
| **합계** | **2723** |

행 단위 원본은 `eval/review/_archive/_ledger_260806.jsonl` 에 있다 — `text · from_file · kept_in · reason · gold_label · cur_rule_label · claude_judgment` 로 1행씩. **어떤 문장이 왜 큐에서 빠졌고 대신 어디에 있는지**를 이 파일 하나로 되짚을 수 있다.

## 4. 보관 위치

| 위치 | 파일 | 행 | 성격 |
|---|---:|---:|---|
| `_archive/` | 48 | 16607 | 판정 완료분·감사 증적·재편 전 원본 |
| `_archive/silver/` | 17 | 1419 | 규칙·모델 합의 자동분. 학습 silver 로만 사용, **gold 아님** |
| `_gold_backup/pre_queue_split_260806/` | 1 | 5,597 | 260716 원본 큐 스냅샷 |

## 5. 인용 규약 (문서·모델에 이 판정을 쓸 때)

- `decision_source` 로만 출처를 판별한다. `human`=사람 확정 / `claude_rule_prefill_260806`=**규칙 발동 결과이지 문장 개별 판독이 아님** / `auto_rule_wellbeing_260806`=건강·개인안녕 중립화 자동분.
- 프리필·silver 는 **gold 로 승격하지 않는다.** 승격은 사람 확정 후 `promote_gold.py` 로만 한다 (AUDIT_STANDARD §4, 대량 확정=escalation).
- 보고서에 건수를 인용할 때는 이 문서의 **재생성 시점**을 함께 적는다(큐는 판정에 따라 변한다).

## 6. 알려진 제약

- `prod25_*` 3파일은 원 배치에 평가 칸(장점/단점)이 없어 `field` 가 전부 `null` 이다(`batch_20260714_0` 에서 필드 0/758,880). 칸 신호 없이 문장만으로 판정해야 한다.
- 260806 이전 이름을 **문자열로 박아 둔 과거 스크립트**가 있다(`build_hard_labeling_queue_260715` · `judge_packet_260714` · `audit_extract_queue_260716` 등). 재실행하면 `FileNotFoundError` 로 **소리내어 실패**한다. glob 사용처는 접두 허용 패턴으로 이미 고쳤다(조용히 0건이 되는 쪽이 위험하므로).
- 낡은 지도 `result/group_files_index_260703.md`(29파일)·`result/review_todo_260703.md` 는 **이 문서로 대체**된다.
