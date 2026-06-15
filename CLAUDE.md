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
