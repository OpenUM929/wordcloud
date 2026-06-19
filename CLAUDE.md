# CLAUDE.md — 워드클라우드 프로젝트 나침반

> ⚠️ **이 파일은 나침반이다. 구체적 내용은 `.clinerules` 하위 문서에 있다.**
> **작업 유형을 파악 → [`.clinerules/core/00-core.md`](.clinerules/core/00-core.md)의 분류표에서 해당 유형 찾기 → 명시된 문서로 이동 → 그 문서 읽기**

---

## ⛔ 작업 시작 전 필수 체크 — 모든 작업에 예외 없이 적용

**작업 요청을 받는 즉시, 아래 3단계를 실행한다. 어떤 이유로도 건너뛰지 않는다.**

1. `.clinerules/core/00-core.md` 를 Read 도구로 연다
2. 분류표에서 현재 작업 유형을 찾는다
3. 해당 문서를 Read 도구로 열어 읽은 뒤 작업을 시작한다

> 이 3단계를 실행하지 않고 바로 작업에 진입하는 것은 **지침 위반**이다.

---

## 프로젝트 개요

한국어 인사평가 문서를 분석하여 **감정(긍정/부정/중립)**, **단어 빈도**, **워드클라우드**를 생성하는 시스템.

- 백엔드: Python + Flask
- 핵심 모델: KoTE (Korean Text Emotion, 44개 감정 레이블)
- 위치: `wordcloud_project/`

---

## 감정 분석 상세 지침

> 원래 이 파일에 있던 감정 분석 규칙 시스템, 반전 표지어 체계, KoTE 모델 특성, 개발 규칙 등은 아래 문서로 이관되었다.

| 주제 | 문서 위치 |
|------|----------|
| 감정 분석 규칙 / KoTE 모델 특성 / 중립·부정 키워드 / 개발 규칙 | [`.clinerules/docs/project_wordcloud/modules/emotion-analysis.md`](.clinerules/docs/project_wordcloud/modules/emotion-analysis.md) |

---

## 📦 학습 데이터셋 누적 지침 (KoTE 파인튜닝)

> **감정어·리더십 분석 또는 알고리즘 강화 작업을 진행할 때는, 사용·검토한 데이터를 항상 지정 데이터셋에 함께 누적한다.** 향후 KoTE 모델을 인사평가 도메인으로 파인튜닝하여 **신규 감정 / 신규 리더십 그룹**을 생성하기 위함이다. (규칙 작업과 데이터셋 구축을 1회 작업으로 겸한다.)

> 🔴 **데이터 도착·감정/리더십 작업 착수 시 반드시 [`wordcloud_project/plans/_datasets/kote_finetune/RUNBOOK.md`](wordcloud_project/plans/_datasets/kote_finetune/RUNBOOK.md)를 펴고 §2 체크리스트 → §누적 로그를 수행한다.** RUNBOOK은 완료(DN) 개념이 없는 **상시 절차**이며, 이 누적 작업이 잊히지 않도록 하는 단일 진입점이다. (설계 `0617_05`는 일회성 문서, 누적 실행은 RUNBOOK.)

- **데이터셋 명칭**: `hr-kote-finetune`
- **저장 폴더(지정·고정)**: `wordcloud_project/plans/_datasets/kote_finetune/`
  - 감정어 스트림: `emotion/emotion.jsonl` (append-only)
  - 리더십 스트림: `leadership/leadership.jsonl` (append-only)
- **누적 방식**: append-only(기존 행 수정·삭제 금지, 정정은 동일 `id` 신규 리비전 행). 라인당 1 JSON(JSONL, UTF-8).
- **프라이버시**: 가명화 완료 텍스트만 보관(원천 ID 비보관). `plans/`는 배포 제외 폴더이므로 내부망 패키지에 포함되지 않는다 — **이 폴더 외 다른 위치에 학습 데이터를 두지 말 것**(배포 유출 방지).
- **원칙**: 긍↔부 오분류 방지가 최우선. 신규 감정·리더십 그룹은 **코퍼스 발굴 근거가 있을 때만** 추가(추측 금지).
- **상세 설계/스키마**: [`wordcloud_project/plans/2026/0617_05_kote-finetune-data/0617_05_kote-finetune-data.md`](wordcloud_project/plans/2026/0617_05_kote-finetune-data/0617_05_kote-finetune-data.md) · 폴더 규약: [`README`](wordcloud_project/plans/_datasets/kote_finetune/README.md)

---

## 프로젝트 전체 지침

모든 작업의 상세 규칙은 **`.clinerules/core/00-core.md`** 를 따른다.

```
작업 유형 파악
    ↓
.clinerules/core/00-core.md → 작업 유형 분류표 확인
    ↓
해당 문서로 이동하여 상세 지침 준수
```

---

*본 파일은 이전 `CLAUDE.md`의 구체적 내용을 `.clinerules` 체계로 이관한 후 나침반 역할로 축소되었다.*
