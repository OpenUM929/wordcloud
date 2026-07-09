# 09. 관점 매트릭스 분석

> 코드 위치: `wordcloud_project/src/services/perspective_service.py`

## 개요 — 무엇을 하는가

같은 평가 데이터라도 **"어떤 기준으로 묶어 보느냐"** 에 따라 전혀 다른 통찰이 나온다. 이 모듈은 평가 결과를 **X축·Y축 두 기준으로 교차 집계한 표(매트릭스)** 로 만든다.

예: **행(Y) = 평가 연도, 열(X) = 부서별** 로 놓으면, "2025년 생산부의 감정 분포 vs 2026년 영업부의 감정 분포"를 한 표에서 비교할 수 있다. 각 칸(cell)에는 그 그룹의 NLP/감정/리더십/욕설/비꼼 분석 결과와 워드클라우드가 들어간다.

비유하자면, 단일 평가 결과들을 **피벗 테이블처럼 다차원으로 재조합**해 조직적 패턴을 드러내는 분석 엔진이다.

---

## 적용 분야

- 부서별·직책별·연도별 평가 경향 비교
- 조직 단위 감정/리더십 벤치마킹
- 1.9만 명 전체를 한 번에 교차 분석 (`generate_all_employee_matrix`)

---

## 기술 상세

### 1. 축(Axis) 구성 요소

| 구성 | 정의 위치 | 예시 |
|------|-----------|------|
| 행(Row) 기준 | `ROW_FIELDS` (`perspective_service.py:45`) | 평가 연도, 평가 월, 배치(회차), 평가 일자 |
| 열(Col) 모드 | `COL_MODES` (`perspective_service.py:52`) | 부서별, 직책별(세부), 직책별(3등분), 전체 |
| 분석 종류 | `ANALYSIS_TYPES` (`perspective_service.py:59`) | nlp, emotion, leadership, profanity, sarcasm |

### 2. 매트릭스 생성 엔진

코드 위치: `perspective_service.py:1408` `generate_perspective_matrix()`

```python
matrix = {}
for rk in rows:                 # 각 행 키
    matrix[rk] = {}
    for ck in columns:          # 각 열 키
        cell_items = ...        # 해당 (행,열) 그룹에 속한 평가들
        matrix[rk][ck] = _generate_cell_content(cell_items, analysis_types, options, ...)
```

각 셀은 그 그룹의 평가들을 모아 5종 분석을 수행하고 결과(+워드클라우드 경로)를 담는다.

### 3. 전체 직원 일괄 매트릭스 (병렬)

코드 위치: `perspective_service.py:1828` `generate_all_employee_matrix()` + `:1859`

```python
num_workers = min(multiprocessing.cpu_count(), 4)
with ThreadPoolExecutor(max_workers=num_workers) as executor:
    ...  # 직원별 매트릭스를 병렬 생성
```

→ 대규모 처리 세부는 [02장](02-parallel-processing.md) 참조.

### 4. 결과 인덱싱 (갤러리/매니페스트)

생성된 매트릭스는 갤러리 DB / 매니페스트에 인덱싱해 빠르게 조회한다(`perspective_service.py:1591` `_index_matrix_to_manifest()`). 저장 DB는 SQLite WAL 모드(`perspective_service.py:31`).

### 5. 핵심 도메인 지식 — 반전(역접) 표지어 사전

> KoTE 감정 모델은 **문장의 통사 구조(어디서 의미가 뒤집히는지)를 판단하지 못한다.** 그래서 역접·양보·대조를 나타내는 표지어를 **모델 외부에서 사전(辭典)으로 관리**한다.

코드 위치: `perspective_service.py:78` `CONTRASTIVE_MARKERS`

```python
CONTRASTIVE_MARKERS = {
    'strong': ['그러나', '그렇지만', '하지만', '다만', '단 ', '반면', '그래도', ...],
    # ... 강도별 분류
}
```

- 예: "처음엔 부족했지만 결국 훌륭했다" → '~지만' 이후가 진짜 결론(긍정)임을 표지어로 인지해 감정 판정을 보정.
- `'단 '` 처럼 **공백을 포함**시켜 "단순/단계" 같은 단어의 오탐을 방지하는 세심한 설계(`perspective_service.py:87`).

> ⚠️ **유지보수 주의**: 표지어를 추가/수정할 때는 `CLAUDE.md`의 "반전 표지어 체계" 섹션과
> `.clinerules/docs/project_wordcloud/services/perspective-service-contrastive.md` 를 함께 갱신해야 한다.

### 6. 분석 제외 컬럼

식별자·해시·문서 원문 등 분석에서 빼야 할 컬럼을 `SKIP_COLUMNS` 로 명시 관리한다(`perspective_service.py:37`).

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 본질 | 평가 데이터를 X/Y 매트릭스(피벗)로 재조합 |
| 축 | 행=연/월/배치/일자, 열=부서/직책/전체 |
| 셀 내용 | 5종 분석(nlp·emotion·leadership·profanity·sarcasm) + 워드클라우드 |
| 대규모 | 전체 직원 병렬 매트릭스 (워커 ≤4) |
| 도메인 보완 | 반전 표지어 사전으로 KoTE 통사 한계 보정 |

---

*다음: [10. 데이터 보안·전처리·배포 파이프라인](10-data-security-pipeline.md)*
