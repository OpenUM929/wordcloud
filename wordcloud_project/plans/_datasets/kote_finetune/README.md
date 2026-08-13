# hr-kote-finetune — 인사평가 KoTE 파인튜닝 코퍼스 (누적)

> 향후 KoTE 모델을 인사평가 도메인으로 파인튜닝하여 **신규 감정 / 리더십 그룹**을 생성하기 위한
> 학습 데이터셋. 감정어·리더십 분석 및 알고리즘 강화 작업에서 사용/검토한 데이터를 **여기에 지속 누적**한다.
> 📌 **데이터 도착 시 반복 절차 + 누적 로그는 [`RUNBOOK.md`](RUNBOOK.md)** (상시 운영, 완료 개념 없음). 본 README는 폴더 규약.
> 설계 상세: `../../2026/0617_05_kote-finetune-data/0617_05_kote-finetune-data.md`

## 📑 문서 지도 (역할 정의 — 헷갈리면 여기부터)

> 이 도메인 문서가 늘어나 혼동될 때의 **단일 범례**. "무슨 문서가 어떤 역할이고, 언제 펴는가."

| 문서 | 한 줄 정의 (역할) | 펴는 때 | 갱신 성격 |
|------|------------------|---------|-----------|
| `../../../../CLAUDE.md` | 프로젝트 나침반 → `.clinerules` 분류표로 보냄 | 모든 작업 착수 시 | 정적 |
| **`RUNBOOK.md`** | **상시 운영 절차**(데이터 도착 시 반복 체크리스트 §2 + 누적 로그) + 🧭 **복원 앵커** | 데이터 도착·감정/리더십 작업 시 | 상시(완료 없음) |
| **`ROADMAP.md`** | **상시 현황·로드맵**(전체 그림: 어디까지·다음 무엇·어떻게 구현 P0~P7) | 방향/진행 파악, 상사 설명 | 상시(현황 갱신) |
| **`AUDIT_STANDARD.md`** | **실배치 감사·오류후보 추출 표준 절차**(재현 가능: 4단계·시드·스크립트·택소노미·보고서 규정) | 배포 결과 검증·감사 보고, 인사처 타당성 근거 | 정적(절차 정본) |
| `README.md` (본 문서) | **폴더·데이터 규약** + 본 문서 지도 | 폴더 구조·파일 의미 확인 | 정적 |
| `leadership/TRAIT_TREE.md` | 리더십 택소노미 **스펙 정본**(20-trait 트리·rollup) | trait 구조 확인·갱신 | 군집 근거 시 |
| `leadership/trait_library_ref.md` | 외부 레포(`OpenUM929`) **활용 전략 §0** + micro 검증본 §3 | 외부 골격 대조·군집 | 정적(스냅샷) |
| `leadership/weak_labeling_lf.md` | **약지도 LF 설계** + §8 lexicon 보강로그 + §9 positive-negation 게이트 설계 | LF 배선·표지 보강·게이트 구현 | 설계 진화 |
| **`result/IMPROVEMENT_HISTORY.md`** | **개선 이력(기간대별·append-only 척추)**: 지표 타임라인(8c_hard·baseline·긍↔부) + 기간별 상세 링크. 개선 역사 전량 보존(RUNBOOK §불변원칙) | 개선 흐름·역사 추적 | append-only |
| `result/status_YYMMDD.md` | **기간 상세 스냅샷**(예 `status_260707.md`): 그 기간 수치·변경·다음. 덮어쓰지 말고 날짜별 신규 | 특정 기간 상세 | 스냅샷(날짜별) |
| **`MODELING_LEVERS_PLAN.md`** | **모델링 레버 계획서**(데이터 천장 이후): 앙상블·비대칭손실·캘리브레이션·캐스케이드·대조학습·베이스A/B. 각 레버 목표/가설/방법/성공기준/롤백 | 다음 실험 뭘·어떻게 | 계획(PND, 채택분만 DN) |
| `result/worklog_260703.md` | **세션 작업 정리**(엔진 교정 9건·그룹재편·검증) — 보고서 재료 | 보고서 작성·진척 요약 | 스냅샷 |
| `result/review_todo_260703.md` | **사람 검토 To-Do**(그룹별 우선순위·미판정 수) | 다음 뭘 검토할지 | 현황(재생성) |
| `result/group_audit_260703.md`·`scripts/group_audit_260703.py` | **그룹단위 분류 감사**(그룹별 일치율·누수원인) | 규칙 수정 후 검증 | 재실행 |
| **`result/review_queue_index_260806.md`** | **검토큐 지도·근거 대장**(우선순위 P1~P3 정의 · 파일별 출처·산출 스크립트·미판정 수 · 큐 제외 사유별 집계 · 인용 규약). 행 단위 근거는 `eval/review/_archive/_ledger_260806.jsonl` | 무엇을 먼저 판정할지 · 판정 결과를 문서/모델에 인용할 때 | 재생성(멱등, `scripts/build_review_index_260806.py`) |
| ~~`result/group_files_index_260703.md`~~ | **게시판 파일 지도**(29 그룹파일 위치·검토법) | 게시판 파일 의미 | 재생성 |
| `emotion/emotion.jsonl`·`leadership/leadership.jsonl` | **정식 gold 스트림**(confirmed만, append-only, 학습 대상) | gold append | append-only |
| **`eval/label_master_260804.jsonl`**·`result/label_master_260804.md` | **라벨 마스터**(흩어진 라벨을 고유 (칸,문장) 1행으로 통합 + 출처 티어·학습/테스트 포함 여부·라벨 충돌 표시). 🔴 **출처 판별은 필드명이 아니라 `decision_source` 로만 한다** — `human_decision` 필드에 Claude·규칙 산출이 섞여 있음 | "사람 라벨이 무엇인가"·홀드아웃·충돌 검토 | 재생성(멱등, `scripts/build_label_master_260804.py`) |
| `../../2026/0617_05_kote-finetune-data/` | 데이터셋 **설계 정본**(스키마·보안) — *일회성* | 스키마 근거 확인 | 보류(고정) |
| `../../2026/0617_01_emotion-rule-mining/` | 규칙 마이닝 + 회귀 테스트 — *일회성* | 규칙·테스트 근거 | DN(고정) |

**문서 구분 규약(중요)**: *일회성 설계/구현 산출물* = `plans/YYYY/`(0617_01·0617_05) · *상시 현황·절차* = **본 폴더**(RUNBOOK·ROADMAP·README·leadership). 현재 진행 중 작업·현황을 `plans/`에 새 계획서로 만들지 않는다(CLAUDE.md "📦 데이터셋 누적 지침" 규약).

**진입 순서**: `CLAUDE.md` → `RUNBOOK.md`(🧭 앵커) → 필요 시 `ROADMAP.md`(전체 그림) / `leadership/*`(세부). 교차 세션 복원은 메모리 `[[project-kote-dataset-runbook]]` → 이 체인.

## 위치/배포

- 경로: `wordcloud_project/plans/_datasets/kote_finetune/`
- `plans/`는 `deploy/build_deploy.ps1`의 `ExcludeDirs`에 포함 → **내부망 배포 패키지에 포함되지 않음**(프라이버시·dev 전용).
- 텍스트는 **가명화 완료분만** 보관(PseudonymManager). 원천 식별자(`source_*_id`)는 해시/비보관.

## 스트림 (append-only)

| 스트림 | 파일 | 용도 |
|--------|------|------|
| 감정어 | `emotion/emotion.jsonl` | 문장 단위 감정(3분류 + KoTE 44 멀티라벨 + 신규후보) |
| 리더십 | `leadership/leadership.jsonl` | 문장/문서 단위 리더십 극성·trait. 택소노미(2계층 트리+rollup): [`leadership/TRAIT_TREE.md`](leadership/TRAIT_TREE.md) |

- **append-only**: 기존 행 수정/삭제 대신 새 행 추가. 정정은 동일 `id`의 신규 리비전 행으로(가장 최신 `review_status=confirmed` 채택).
- 라인당 1 JSON 객체(JSONL, UTF-8). 스키마는 설계서 §5 참조.

## 스냅샷 vs 정식 스트림 (혼동 금지)

| 종류 | 파일 | 의미 |
|------|------|------|
| **정식 스트림(append-only)** | `emotion/emotion.jsonl`, `leadership/leadership.jsonl` | **사람 확정(`review_status=confirmed`) gold만** 누적. 학습 대상. |
| **약지도 스냅샷** | `emotion/weak_export_<date>.jsonl`, `*.split.jsonl` | 스크립트가 CSV에서 재생성하는 약지도(모델/규칙) 라벨. gold는 `pending`. **재기록 가능(멱등)**, 학습 금지. |

## scripts / 산출물

- `scripts/export_jsonl.py` — 취득 코퍼스 CSV → 약지도 JSONL 스냅샷. §14-1 비식별화 게이트(`source_*_id`→`src_hash`, PII 정규식 감사로 적발 행 격리) 적용.
- `scripts/build_splits.py` — 스냅샷 → 중복제거(src_hash당 동일문장 캡) + 누수방지 그룹 분할(GroupKFold, 동일 src_hash 동일 split) + 품질 리포트.
- `result/export_report_<date>.md`, `result/split_report_<date>.md` — 가명화 통계만(원문 미포함).
- 실행: `python plans/_datasets/kote_finetune/scripts/export_jsonl.py` → `build_splits.py` (서버·배치 불요, KoTE 1회 로드).

> 2026-06-17 첫 스냅샷: 입력 722행 → 713행 기록(PII 9행 격리). 잠정 gold **positive 0건** → 긍정 gold 확보가 학습 선결.

## 누적 규칙 (CLAUDE.md 지침과 동일)

감정어/리더십 분석·알고리즘 강화 작업을 진행할 때:
1. 사용·검토한 문장을 약지도 사전라벨(KoTE top3 + 발동 규칙/리더십 극성)과 함께 해당 스트림에 append.
2. 사람이 확정한 정답(`sentiment_gold` / `leadership_gold` / `emotions_gold`)을 `review_status=confirmed`로 기록.
3. 신규 감정·리더십 그룹 후보는 **코퍼스 발굴 근거가 있을 때만** 추가(추측 금지).

> 핵심 가치: 긍↔부 오분류 방지. gold는 극성에서 특히 신뢰되어야 한다.
