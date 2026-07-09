# 워드클라우드 분석 시스템 — 기술 메뉴얼

> 한국어 인사평가 문서를 입력받아 **감정·단어 빈도·리더십·비속어·관점(matrix)** 을 분석하고
> **워드클라우드 이미지**까지 생성하는 시스템에 집약된 기술들을 설명하는 통합 메뉴얼.
>
> ※ 같은 폴더 상위의 `Manual/README.md`(내부망 설치 메뉴얼), `01.기능_프로토타입_설명서.html`,
> `02.실제_데이터_워크스루_설명서.html` 와는 별개의 **기술 설명 문서**다.

---

## 0. 이 메뉴얼의 사용법

- 각 장(章)은 **앞부분 "개요"**(비기술 독자용)와 **뒷부분 "기술 상세"**(개발자/유지보수자용)로 나뉜 **혼합형** 구성이다.
- "코드 위치"에 표기된 `파일:라인` 은 실제 소스 기준이며, 코드가 변경되면 라인 번호는 달라질 수 있다.
- 빠르게 "무슨 기술이 얼마나 들어가 있나"를 보려면 **§1 기술 집약도 한눈에 보기**만 읽어도 된다.

---

## 1. 기술 집약도 한눈에 보기

이 시스템 하나에 다음과 같은 이질적 기술 영역이 **동시에** 통합되어 있다.

| # | 기술 영역 | 핵심 기술 / 라이브러리 | 한 줄 설명 | 상세 문서 |
|---|-----------|------------------------|-----------|-----------|
| 1 | 병렬·대량 처리 | `ThreadPoolExecutor`, `multiprocessing`, 체크포인트/재개 | 약 1.9만 명 평가를 동적 워커로 병렬 처리, 중단 시 이어서 재개 | [02-parallel-processing.md](02-parallel-processing.md) |
| 2 | 자연어 형태소 분석 | Kiwi(`kiwipiepy`), 품사 태깅 | 한국어 문장을 형태소로 쪼개 의미 단어(명사/동사/형용사)만 추출 | [03-nlp-morphological-analysis.md](03-nlp-morphological-analysis.md) |
| 3 | 워드클라우드 생성 | `wordcloud`, `PIL`, `matplotlib`, 커스텀 나선 배치 | 단어 빈도 + 감정 색상을 입힌 워드클라우드 이미지 생성 | [04-wordcloud-generation.md](04-wordcloud-generation.md) |
| 4 | 감정 분석 (딥러닝) | KoTE 모델, `transformers`, `torch` | 44개 감정 레이블 → 긍정/부정/중립 3분류 | [05-emotion-analysis.md](05-emotion-analysis.md) |
| 5 | 리더십 역량 분석 | KoTE + 키워드/감정 매핑 | 6가지 리더십 역량 점수 산출 | [06-leadership-analysis.md](06-leadership-analysis.md) |
| 6 | 반어법(비꼼) 분석 | `transformers` 파인튜닝 + `scikit-learn` 폴백 | 칭찬을 가장한 비꼼 탐지 | [07-sarcasm-analysis.md](07-sarcasm-analysis.md) |
| 7 | 비속어 필터링 | 2계층(Kiwi 형태소 + 음절 간격 regex) + 영어 필터 | "시.발", "개 새 끼" 같은 우회 표기까지 탐지 | [08-profanity-filter.md](08-profanity-filter.md) |
| 8 | 관점(매트릭스) 분석 | X/Y 매트릭스 그룹핑 엔진, 반전 표지어 사전 | 부서×직책 등 교차 집계로 분석 결과 비교 | [09-perspective-matrix.md](09-perspective-matrix.md) |
| 9 | 데이터 보안·파이프라인 | 가명화, 파일 파싱, SQLite/PostgreSQL, 배포 패키지 | 개인정보 가명화 + 문서 파싱 + 무결성 보존 | [10-data-security-pipeline.md](10-data-security-pipeline.md) |

> 전체 데이터 흐름과 기술 스택 표는 **[01-architecture-overview.md](01-architecture-overview.md)** 참조.

---

## 2. 문서 목차

| 장 | 제목 | 대상 |
|----|------|------|
| 01 | [시스템 전체 구조 & 데이터 흐름](01-architecture-overview.md) | 전체 |
| 02 | [병렬·대량 배치 처리](02-parallel-processing.md) | 혼합 |
| 03 | [자연어 형태소 분석 (Kiwi)](03-nlp-morphological-analysis.md) | 혼합 |
| 04 | [워드클라우드 생성](04-wordcloud-generation.md) | 혼합 |
| 05 | [감정 분석 (KoTE 딥러닝)](05-emotion-analysis.md) | 혼합 |
| 06 | [리더십 역량 분석](06-leadership-analysis.md) | 혼합 |
| 07 | [반어법(비꼼) 분석](07-sarcasm-analysis.md) | 혼합 |
| 08 | [비속어 필터 (2계층 탐지)](08-profanity-filter.md) | 혼합 |
| 09 | [관점 매트릭스 분석](09-perspective-matrix.md) | 혼합 |
| 10 | [데이터 보안·전처리·배포 파이프라인](10-data-security-pipeline.md) | 혼합 |

---

## 3. 기술 스택 요약

- **백엔드 프레임워크**: Python 3 + Flask 3.1
- **딥러닝**: PyTorch 2.6, HuggingFace Transformers 4.57 (KoTE 한국어 감정 모델)
- **한국어 NLP**: Kiwi(kiwipiepy 0.22)
- **머신러닝**: scikit-learn 1.7 (반어법 폴백 모델)
- **시각화**: wordcloud 1.9, matplotlib 3.10, Pillow 12
- **데이터**: pandas, SQLite(WAL), PostgreSQL(psycopg2), Redis
- **문서 처리**: python-docx, weasyprint / mkdocs-to-pdf (PDF 출력)
- **보안**: cryptography, 자체 가명화(PseudonymManager)

---

*본 메뉴얼은 `wordcloud_project/` 소스 코드를 기준으로 작성되었다.*
