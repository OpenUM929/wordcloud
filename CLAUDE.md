# CLAUDE.md — 워드클라우드 프로젝트 나침반

> 🧭 **나침반 문서** — 내용을 담지 않고 위치만 가리킨다. 구체적 내용은 `.clinerules` 하위 문서에 있다.

---

## ⛔ 작업 시작 전 필수 체크 — 예외 없이 적용

**작업 요청을 받는 즉시 아래 4단계를 실행한다. 어떤 이유로도 건너뛰지 않는다.**

| # | 행동 |
|---|------|
| 0 | [`project.json`](project.json) 을 Read 해 `project_id` 와 `guideline.project_dir` 를 확인한다 |
| 1 | [`.clinerules/common/core/00-core.md`](.clinerules/common/core/00-core.md) 를 Read 한다 |
| 2 | 분류표에서 현재 작업 유형을 찾는다 |
| 3 | 지정된 문서를 Read 한 뒤 작업을 시작한다 |

`project.json` 이 없으면 git 루트 폴더명으로 폴백하고 **폴백했음을 응답에 표시**한다. 둘 다 실패하면 작업을 멈추고 질문한다. → [`19-project-identity.md`](.clinerules/common/core/19-project-identity.md)

> 이 4단계를 실행하지 않고 바로 작업에 진입하는 것은 **지침 위반**이다.

---

## 프로젝트 개요

한국어 인사평가 문서를 분석해 **감정(긍정/부정/중립)**, **단어 빈도**, **워드클라우드**를 생성하는 시스템.

| 항목 | 값 |
|------|-----|
| 백엔드 | Python + Flask |
| 핵심 모델 | KoTE (Korean Text Emotion, 44개 감정 레이블) + HR 도메인 파인튜닝 3분류 |
| 앱 루트 | `wordcloud_project/` (정본은 `project.json` 의 `paths.app_root`) |
| 프로젝트 지침 | [`.clinerules/projects/wordcloud/README.md`](.clinerules/projects/wordcloud/README.md) |

---

## 자주 여는 문서

| 주제 | 문서 |
|------|------|
| 감정 분석 규칙 / KoTE 모델 특성 / 중립·부정 키워드 | [`modules/emotion-analysis.md`](.clinerules/projects/wordcloud/modules/emotion-analysis.md) |
| 가명 관리(PseudonymManager) 절대 규칙 | [`modules/pseudonym-manager.md`](.clinerules/projects/wordcloud/modules/pseudonym-manager.md) |
| 배포 | [`deployment.md`](.clinerules/projects/wordcloud/deployment.md) |
| 지침 저장소 안내 | [`.clinerules/CLAUDE.md`](.clinerules/CLAUDE.md) |

---

## 🛡 파일 일괄 삭제 대비 (사내 보안 프로그램)

2026-08-20 사내 프로그램이 `.html` `.txt` `.csv` `.png` 을 **확장자 단위로 전량 하드 삭제**했다(휴지통 우회, 본체 61 + `.clinerules` 56). `.git` 내부는 온전했다 → **커밋된 것만 산다.** 정책상 재발 전제.

| 상황 | 행동 |
|------|------|
| 파일이 사라졌을 때 | `powershell -NoProfile -File wordcloud_project/scripts/dlp_guard.ps1 -Restore` — 본체+`.clinerules` 동시, **삭제분만** 복원(수정분 불가침) |
| 점검 | 인자 없이 실행. 세션 시작 시 자동 실행되어 삭제 발견 시 경고 |
| 신규 산출물 확장자 | 실행로그·리포트 `.txt`→`.md`, 표 데이터 `.csv`→`.jsonl`, 도식 `.png`→`.svg`. **생존이 실측된 확장자만 쓴다**(md·json·jsonl·py·js·css·svg·log) |
| 확장자를 못 바꾸는 것 | 앱 템플릿 `.html`, 반입 원본 `.csv` → **생성 즉시 커밋**. 커밋할 수 없으면 `-Snapshot`(스윕 대상 밖 `.dlpbak` 아카이브) |

> `wordcloud_project/outputs/` 의 생성 PNG 처럼 `.gitignore` 대상은 git 이 지키지 못한다. 재생성 불가한 자산을 그런 위치에 두지 않는다.

---

## 📦 학습 데이터셋 누적 지침 (KoTE 파인튜닝)

> 🔴 **데이터 도착·감정/리더십 작업 착수 시 반드시 [`RUNBOOK.md`](wordcloud_project/plans/_datasets/kote_finetune/RUNBOOK.md) 를 펴고 §2 체크리스트 → §누적 로그를 수행한다.** RUNBOOK 은 완료(DN) 개념이 없는 **상시 절차**이며, 이 누적 작업이 잊히지 않게 하는 단일 진입점이다.

| 항목 | 값 |
|------|-----|
| 데이터셋 명칭 | `hr-kote-finetune` |
| 저장 폴더(고정) | `wordcloud_project/plans/_datasets/kote_finetune/` |
| 감정어 스트림 | `emotion/emotion.jsonl` (append-only) |
| 리더십 스트림 | `leadership/leadership.jsonl` (append-only) |
| 폴더 규약 | [`README`](wordcloud_project/plans/_datasets/kote_finetune/README.md) |

- **누적 방식**: append-only(기존 행 수정·삭제 금지, 정정은 동일 `id` 신규 리비전 행). 라인당 1 JSON(JSONL, UTF-8).
- **프라이버시**: 가명화 완료 텍스트만 보관(원천 ID 비보관). `plans/` 는 배포 제외 폴더다 — **이 폴더 외 다른 위치에 학습 데이터를 두지 말 것**(배포 유출 방지).
- **원칙**: 긍↔부 오분류 방지가 최우선. 신규 감정·리더십 그룹은 **코퍼스 발굴 근거가 있을 때만** 추가(추측 금지).
