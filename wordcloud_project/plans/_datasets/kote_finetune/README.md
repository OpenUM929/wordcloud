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
| `README.md` (본 문서) | **폴더·데이터 규약** + 본 문서 지도 | 폴더 구조·파일 의미 확인 | 정적 |
| `leadership/TRAIT_TREE.md` | 리더십 택소노미 **스펙 정본**(20-trait 트리·rollup) | trait 구조 확인·갱신 | 군집 근거 시 |
| `leadership/trait_library_ref.md` | 외부 레포(`OpenUM929`) **활용 전략 §0** + micro 검증본 §3 | 외부 골격 대조·군집 | 정적(스냅샷) |
| `leadership/weak_labeling_lf.md` | **약지도 LF 설계** + §8 lexicon 보강로그 + §9 positive-negation 게이트 설계 | LF 배선·표지 보강·게이트 구현 | 설계 진화 |
| `emotion/emotion.jsonl`·`leadership/leadership.jsonl` | **정식 gold 스트림**(confirmed만, append-only, 학습 대상) | gold append | append-only |
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
