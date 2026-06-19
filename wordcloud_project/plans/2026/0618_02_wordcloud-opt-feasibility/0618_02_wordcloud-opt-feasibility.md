#하기 내용은 잘못된 분석으로 계획을 폐기함

# 집단 분석 워드클라우드 최적화 가능성 분석

> 상태: 폐기(DROP) — 잘못된 분석으로 계획 폐기 | 작성일: 2026-06-18
> 대상: `perspective_service.py` 집단 분석 워드클라우드 생성 경로
> 관련 계획: `0617_07_hardware-adaptive-worker-plan`

---

## 1. 질문

**"0617_07(하드웨어 기반 워커 수 동적 선정 + GPU 배치 추론) 방식을 집단 분석의 워드클라우드 생성에도 적용할 수 있는가?"**

---

## 2. 0617_07의 핵심 속도 향상 원인

0617_07에서 speedup 5~7배를 달성한 원인은 **하나**입니다.

| 기법 | 대상 | 측정된 효과 | 워드클라우드 적용 가능? |
|------|------|------------|----------------------|
| **GPU 배치 추론 (KoTEModel 공유 + 문장 단위 배치)** | `emotion_analysis.py` KoTE forward (Transformer) | **최대 7.09x** | ❌ |
| 동적 워커 산정 (`_calc_adaptive_workers`) | `batch_processor.py` ThreadPoolExecutor | 보조적 | △ |
| VRAM 기반 워커 캡 | GPU 메모리 보호 | 보조적 | ❌ |
| 싱글톤 락 | 모델 중복 로드 방지 | 보조적 | ❌ |

> **0617_07의 5~7배 speedup은 거의 전적으로 "KoTE 모델을 GPU에서 문장 단위로 배치 추론"한 것에서 나왔습니다. GPU를 전혀 사용하지 않는 워드클라우드 생성에는 적용할 수 없습니다.**

---

## 3. 집단 분석 워드클라우드 생성 파이프라인 분석

`perspective_service.py` → `_generate_nlp_cell()`이 매트릭스 셀 하나당 실행됩니다.

### 3-1. 호출 구조

```
generate_all_employee_matrix()          ← 직원 수만큼 병렬
  └─ generate_perspective_matrix()      ← 직원 1명
       └─ _generate_nlp_cell()          ← 매트릭스 셀 1개
            ├─ extract_words()          ← (1) 단어 집계
            ├─ calculate_word_scores()  ← (2) 단어별 감정 점수
            ├─ _aggregate_emotion()     ← (3) 감정 평균
            └─ _save_wordcloud_to_path() ← (4) PIL 이미지 렌더링
```

### 3-2. 각 단계의 실제 비용

| 단계 | 함수 | 실제 동작 | 비용 |
|------|------|----------|------|
| (1) | `extract_words()` | 메타데이터 `nlp_analysis_results['analysis']['meaningful_words_with_pos']`를 읽어 Counter 집계 | **거의 없음** (메타데이터에 이미 저장된 정보) |
| (2) | `calculate_word_scores()` | 단어별로 evaluation을 순회하며 `_get_sentence_level_scores()` 호출. `sentence_emotion_cache`가 있으면 캐시 조회만 | **거의 없음** (메타데이터에 이미 캐시 있음) |
| (3) | `_aggregate_emotion()` | 동일하게 `_get_sentence_level_scores()` 캐시 조회 | **거의 없음** |
| (4) | `_save_wordcloud_to_path()` → `generate_with_colors_and_options()` | PIL 비트맵 충돌 감지 + 나선형 배치 | **대부분의 시간** |

### 3-3. 핵심 발견

**형태소 분석, 감정 분석, 문장 점수 계산은 모두 메타데이터 생성(`metadata_manager.py`) 시점에 완료되어 캐시(`sentence_emotion_cache`)로 저장됩니다.** 집단 분석에서는 이 캐시를 읽기만 하므로 거의 비용이 들지 않습니다.

**실질적인 병목은 `generate_with_colors_and_options()`의 PIL 기반 이미지 렌더링**입니다. 단어를 중앙 나선형으로 배치하며 충돌 감지(`ImageDraw.text()` + `Image.crop()`)를 100회(max_words) 수행합니다.

---

## 4. 적용 가능성 판정

| 0617_07 기법 | 적용 가능? | 이유 |
|---|---|---|
| `_calc_adaptive_workers()` 동적 워커 산정 | △ 제한적 | `perspective_service.py`의 `num_workers`가 현재 `min(cpu_count, 8)`로 고정되어 있으나, ThreadPoolExecutor에서 워커 수가 GIL을 우회하지는 못함. CPU-bound 작업에서는 스레드 추가 효과가 미미. |
| GPU 전환 + 모델 통합 | ❌ | 워드클라우드 생성은 GPU를 사용하지 않음. |
| 문장 단위 배치 추론 | ❌ | KoTE 모델 호출 자체가 없음. |
| VRAM 기반 워커 캡 | ❌ | 워드클라우드는 VRAM을 소모하지 않음. |

---

## 5. 워드클라우드 전용 최적화 방향

0617_07과 **다른 접근**이 필요합니다.

### 5-1. 실질적인 병목: PIL 이미지 렌더링

`generate_with_colors_and_options()`는 `wordcloud_generator.py`에서 다음을 수행합니다:

- 단어를 빈도순으로 정렬
- 글꼴 크기 계산 (빈도에 비례)
- PIL `ImageDraw`로 단어를 회색조 캔버스에 배치하며 충돌 감지
- 나선형 배치 알고리즘으로 공간 찾기

이 과정은 순수 CPU + GIL 바운드 작업입니다.

### 5-2. 최적화 옵션 비교

| 방법 | 예상 효과 | 난이도 | 리스크 |
|------|----------|--------|--------|
| **워드클라우드 이미지 캐싱** (셀 단위 해시 키) | 🔥🔥 🔥 동일 셀 재요청 시 0에 가까움 | 낮음 | 캐시 저장 공간 |
| **max_words 축소** (100→50) | 🔥🔥 충돌 감지 횟수 절반 | 낮음 | 단어 수 감소 |
| **캔버스 크기 축소** (400×300→300×225) | 🔥 중간 | 낮음 | 화질 저하 |
| **ProcessPoolExecutor 전환** (GIL 우회) | 🔥 중간~높음 | 중간 | Windows spawn 비용 |
| **워커 수 캡 상향** (8→16) | 낮음~중간 | 낮음 | GIL 한계 |
| **렌더링 생략 옵션 추가** (데이터만 필요 시) | 🔥🔥 이미지 생성 자체 생략 | 낮음 | UI 요구사항 따라 불가 |

### 5-3. 종합 권장 우선순위

1. **워드클라우드 캐싱**: 동일 `(employee_id, row_field, col_mode, analysis_type, options)` 조합의 이미지는 재생성하지 않음. 매번 같은 이미지를 다시 그리는 낭비를 제거.
2. **ProcessPoolExecutor 검토**: `ThreadPoolExecutor` → `ProcessPoolExecutor`로 교체하여 GIL 우회. 현재 `concurrent.futures.ProcessPoolExecutor`는 Windows spawn으로 워커당 부담이 있으나, 워드클라우드 생성은 상태가 거의 없어 부담이 적음.
3. **max_words/캔버스 축소**를 옵션화하여 UI에서 선택 가능하도록 제공.

---

## 6. 현재 PC 사양 대비 워커 현황

| 항목 | 값 |
|------|-----|
| CPU | i5-14400 (10코어 / 16스레드) |
| RAM | 32GB |
| GPU | RTX 3050 6GB |
| 현재 워커 수 (`perspective_service.py`) | `min(16, 8) = 8` (고정 캡) |

16스레드 CPU에서 ThreadPoolExecutor 8개는 GIL 한계로 인해 실질적인 병렬 효과가 거의 없습니다. 워드클라우드 렌더링이 병목이라면 **ProcessPoolExecutor가 유일한 실질적 해결책**입니다.

---

## 7. 결론

> **0617_07 방식(하드웨어 적응 워커 + GPU 배치 추론)은 워드클라우드 생성에 적용할 수 없습니다.**
>
> 이유: 0617_07의 효과는 KoTE GPU 배치 추론에서 나왔고, 워드클라우드는 GPU를 사용하지 않으며, 형태소 분석/감정 분석은 이미 메타데이터 생성 시점에 완료되어 캐시되어 있기 때문입니다.
>
> 워드클라우드 생성의 유일한 실질 병목은 **PIL 이미지 렌더링**이며, 이를 해결하려면 **캐싱**과 **ProcessPoolExecutor** 등 0617_07과 다른 접근이 필요합니다.

---

*본 문서는 `0617_07_hardware-adaptive-worker-plan`의 기법이 집단 분석 워드클라우드 생성에 적용 가능한지 분석한 결과입니다.*
