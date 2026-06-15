# 01. 시스템 전체 구조 & 데이터 흐름

## 개요 — 한눈에 보는 시스템

이 시스템은 **"한국어 인사평가 문장 한 덩어리"를 넣으면, 그 안에 담긴 감정·핵심 단어·리더십·비속어를 자동으로 읽어내고, 결과를 그림(워드클라우드)과 표로 보여주는" 자동 분석 공장**이다.

사람이 평가서 한 장을 읽고 "이 평가는 대체로 긍정적이고, '성실'·'협력'이라는 단어가 자주 나오며, 리더십은 보통이고, 욕설은 없다"고 판단하는 과정을, 약 1.9만 명 규모로 **자동·병렬**로 수행한다.

---

## 처리 파이프라인 (데이터 흐름)

```
 [1] 원본 평가 문서 (엑셀/CSV/Word)
        │  파일 파싱 (pandas, python-docx)
        ▼
 [2] 개인정보 가명화 (PseudonymManager)        ← 이름/부서 → 가명
        │
        ▼
 [3] 텍스트 전처리 (정제·문장 분리)
        │
        ├──────────────┬──────────────┬───────────────┬──────────────┐
        ▼              ▼              ▼               ▼              ▼
 [4a] 형태소 분석   [4b] 감정 분석  [4c] 리더십 분석  [4d] 반어법 분석 [4e] 비속어 필터
   (Kiwi)          (KoTE 딥러닝)   (KoTE+키워드)    (Transformers)   (2계층 탐지)
   명사/동사/형용사  긍/부/중 + 점수  6개 역량 점수     비꼼 여부        욕설 span
        │              │              │               │              │
        └──────────────┴──────────────┴───────────────┴──────────────┘
        ▼
 [5] 직원별 메타데이터로 통합 (metadata_analysis)
        │  직원 단위 즉시 DB 저장 (crash-safe)
        ▼
 [6] 워드클라우드 이미지 생성 (wordcloud + PIL, 감정 색상)
        │
        ▼
 [7] 관점(매트릭스) 분석 — 부서×직책 등 교차 집계 (perspective_service)
        │
        ▼
 [8] 결과 제공 (웹 UI / CSV / PDF / 배포 패키지)
```

위 [4a]~[4e] 단계는 **직원별로 병렬 처리**되며, 1000건마다 체크포인트를 남겨 중단 시 이어서 재개한다(→ [02장](02-parallel-processing.md)).

---

## 기술 상세 — 코드 레이어 구조

`wordcloud_project/src/` 아래는 세 계층으로 나뉜다.

| 계층 | 폴더 | 역할 | 대표 파일 |
|------|------|------|-----------|
| **라우트(Route)** | `src/routes/` | Flask HTTP 엔드포인트, 요청/응답 처리 | `batch_routes.py`, `wordcloud_routes.py`, `perspective_routes.py` |
| **서비스(Service)** | `src/services/` | 비즈니스 로직, 배치 오케스트레이션, DB 접근 | `batch_processor.py`, `perspective_service.py`, `wordcloud_service.py` |
| **모듈(Module)** | `src/modules/` | 순수 분석 알고리즘 (AI 추론·NLP·필터) | `emotion_analysis.py`, `nlp_analysis.py`, `wordcloud_generator.py` |

- **모듈**은 가능한 한 외부 의존이 적은 "분석 엔진"이다. 대부분 **싱글톤**(`get_instance()`/`__new__`)으로 한 번만 모델을 로드해 재사용한다 — 1.9만 명 처리 중 모델을 매번 로드하면 비용이 폭발하기 때문이다.
- **서비스**는 모듈들을 호출해 한 직원의 메타데이터를 만들고, 병렬 실행·체크포인트·DB 저장을 담당한다.
- **라우트**는 얇게 유지하고 실제 일은 서비스에 위임한다.

### 분석 종류 (관점 분석에서 선택 가능한 5종)

`perspective_service.py:59` `ANALYSIS_TYPES` 에 정의된 분석 축:

| 키 | 라벨 | 담당 모듈 |
|----|------|-----------|
| `nlp` | NLP 단어 분석 | `nlp_analysis.py` |
| `emotion` | 감정 분석 | `emotion_analysis.py` |
| `leadership` | 리더십 분석 | `leadership_analysis.py` |
| `profanity` | 욕설 분석 | `profanity_filter.py` |
| `sarcasm` | 비꼼 분석 | `sarcasm_analysis.py` |

### 데이터 저장

- **분석 중간/결과**: SQLite (WAL 모드) — `perspective_service.py:31` `_get_eval_conn()` 에서 `PRAGMA journal_mode=WAL` 설정으로 동시 읽기/쓰기 성능 확보.
- **운영 DB**: PostgreSQL(`psycopg2`) 지원.
- **체크포인트/작업서**: JSON 파일 + DB (→ [02장](02-parallel-processing.md)).

---

## 핵심 설계 포인트

1. **모듈 = 싱글톤 분석 엔진**: 무거운 AI 모델은 한 번만 로드.
2. **직원 단위 즉시 저장(crash-safe)**: 한 직원이 끝나면 바로 DB에 저장 → 중간에 죽어도 완료분은 보존.
3. **가명화 우선**: 개인정보는 분석 파이프라인 진입 전에 가명으로 치환 (→ [10장](10-data-security-pipeline.md)).
4. **모델이 못 하는 건 사전(辭典)으로 보완**: KoTE가 통사 구조(역접)를 못 읽으므로 반전 표지어 사전을 외부에서 관리 (→ [09장](09-perspective-matrix.md)).

---

*다음: [02. 병렬·대량 배치 처리](02-parallel-processing.md)*
