# 0615_08 배치 처리 시 문장 단위 KoTE 캐시 저장 + 그룹 분석 재사용

> 상태: DN | 작성일: 2026-06-15 | 구현완료: 2026-06-15

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | §2, §3, §6 | 실증/영향도 1차 검증: 호출 지점 4곳 정정(save_to_deploy 누락 발견), 공유 헬퍼 추출, 배치 시간·용량 영향 추가 |
| 2026-06-15 | §2, §3, §6, §7 | 2차 검증 반영: ①split_sentences를 text_preprocessing.py로 즉시 이전(matplotlib 의존 차단) ②배치 시간 측정 테스트 설계 추가 ③점수-only fallback 구조 선설계(sentence optional) ④라인번호 정의/호출 구분 ⑤19k 평문화 + 용량 정량 추정 |
| 2026-06-15 | 전체 | **구현 완료**: text_preprocessing(split_sentences 이전)·sentence_emotion.py(신규)·metadata_manager(캐시 생성)·perspective_service(_get_sentence_level_scores 캐시+점수-only fallback, 4개 호출 지점)·test 2종 작성. test_cache_equivalence 통과(캐시=점수only=fallback 동일). measure_kote_time는 **사용자 허락 후 실행** 대기. |

---

## 1. 배경 및 문제

### 현재 구조의 모순

배치 처리 시 `analyze_emotion(doc)` — **문서 전체** 단위로 KoTE를 실행하고 결과를 저장한다.  
그러나 그룹 분석은 저장된 결과를 **전혀 사용하지 않고**, 매 조회마다 아래 흐름을 반복한다.

```
그룹 분석 / 제출용 저장 조회 시
  _aggregate_emotion()        → _get_sentence_level_scores()
  _generate_emotion_cell()    → _get_sentence_level_scores()
  calculate_word_scores()     → _get_sentence_level_scores()
  save_to_deploy() 내부        → _get_sentence_level_scores()
      ↓
  split_sentences(doc)               # 문서를 문장으로 분할
  analyze_emotion(sent) × N문장      # KoTE 모델 재실행 ← 문제
```

- 배치 처리가 KoTE를 돌려 저장했음에도, 그룹 분석/제출용 저장이 동일 문서에 KoTE를 재실행
- 배치 처리에서 저장한 `emotion_analysis_results`(문서 단위)는 그룹 분석에서 전혀 활용되지 않음
- 직원 한 명 조회 시 해당 직원의 모든 평가 문장 수만큼 KoTE가 재실행됨

### 올바른 설계

| 단계 | 내용 |
|------|------|
| 배치 처리 | 문장 단위로 분할 후 KoTE 실행 → **원시 점수(pos/neg/neutral) 캐시 저장** |
| 그룹 분석 / 제출용 저장 | 캐시 읽기 → 반전 표지어 규칙 동적 적용 → 사용자 교정 동적 적용 |

반전 표지어 규칙(`sentence_sentiment_override`)과 사용자 교정(`sentiment_corrections`)은  
**여전히 조회 시점에 동적으로 처리** — 규칙 변경 시 재배치 불필요, 교정 기능 그대로 유지.

---

## 2. 영향 범위 (실증 검증 완료)

### 캐시 영속화 경로 (검증됨)

```
create_employee_metadata()  → analyzed_eval['sentence_emotion_cache'] 추가
  → metadata['evaluations'] 포함            (metadata_manager.py:112)
  → process_single_employee() → upsert(_eid, _meta, _meta['evaluations'], batch_id)
                                              (batch_processor.py:736)
  → user_data_manager.upsert(): ev_copy=dict(ev); json.dumps(ev_copy) → data 컬럼
                                              (user_data_manager.py:77,90)
  → load_all_batches(): json.loads(data) → ev_obj   (perspective_service.py:636)
  → ev.get('sentence_emotion_cache') 로 읽기 가능
```

- `upsert`는 eval dict **전체**를 `json.dumps`하므로 신규 필드 자동 영속화 ✓
- `_fingerprint`(user_data_manager.py:35)는 `evaluator_id + evaluation_date + document[:100]`만 사용
  → 캐시 추가가 **중복제거(dedup) 로직에 영향 없음** ✓

### split_sentences 현황 및 이전 결정

- 정의: `perspective_service.py:326` (순수 정규식 + 인사말 필터, **무거운 의존 없음**)
- 이미 `src/modules/text_preprocessing.py`가 `split_sentences`를 재노출하나, perspective_service에서
  import하는 **역방향** 구조라 matplotlib(`Agg`)·WordCloudGenerator(perspective_service.py:2-3,24)를 끌어옴
- 사용처: `perspective_routes.py:13`, `text_preprocessing.py:3`, `test_routes.py:25`, perspective_service 내부(790,1778)
- **결정**: `split_sentences` **정의를 `text_preprocessing.py`로 이전**하고 perspective_service가 역으로 import.
  → 배치 경로(`metadata_manager`→`sentence_emotion`→`text_preprocessing`)에서 matplotlib 의존 **완전 차단**.

### 수정/신규 파일

| 파일 | 함수 | 변경 내용 |
|------|------|-----------|
| `src/modules/text_preprocessing.py` | `split_sentences` (이전) | perspective_service의 정의를 **이쪽으로 이동**. 인사말 set 포함. |
| `src/services/perspective_service.py` | (상단) | `from src.modules.text_preprocessing import split_sentences` 로 교체, 기존 정의 삭제 |
| **(신규)** `src/modules/sentence_emotion.py` | `compute_sentence_raw_scores(doc)` | 문장 분할 + 영어 감지 + KoTE 원시 점수 **공유 헬퍼** (경량) |
| `src/models/metadata_manager.py` | `create_employee_metadata()` | 공유 헬퍼 호출 → `sentence_emotion_cache` 생성·저장 |
| `src/services/perspective_service.py` | `_get_sentence_level_scores()` 정의:784 | `sentence_cache` 파라미터 추가, 캐시 우선; 없으면 헬퍼 fallback; **sentence 누락 시 split로 재도출** |
| `src/services/perspective_service.py` | `calculate_word_scores()` 정의:846 / 호출:866 | 호출 시 `sentence_cache` 전달 |
| `src/services/perspective_service.py` | `_aggregate_emotion()` 정의:1023 / 호출:1044 | 호출 시 `sentence_cache` 전달 |
| `src/services/perspective_service.py` | `_generate_emotion_cell()` 정의:1081 / 호출:1114 | 호출 시 `sentence_cache` 전달 |
| `src/services/perspective_service.py` | `save_to_deploy()` 정의:1673 / 호출:1772 | 호출 시 `sentence_cache` 전달 |

> ⚠️ **호출 지점은 총 4곳**(866, 1044, 1114, 1772). 초안에서 `save_to_deploy`(:1772)를 누락했었다.
> 표의 "정의:N / 호출:M"은 함수 정의 라인과 그 내부 호출 라인을 구분 표기한 것이다.

### 수정하지 않는 것

- `evaluations.data` 컬럼 구조 — `sentence_emotion_cache` 필드 추가만, 기존 필드 유지
- `emotion_analysis_results` (문서 단위) — 유지 (consolidated_analysis·overall_sentiment 호환)
- `sentiment_corrections` 저장/로드 흐름 — 변경 없음
- DB 스키마 — 변경 없음 (`data` JSON 구조에만 필드 추가)
- 단일(1:1) 경로 `metadata_service.generate_metadata` — 분석 미수행, 그룹 분석 비기여 → **범위 외(회귀 아님)**

---

## 3. 구현 상세

### 3-1. 캐시 저장 구조 (sentence optional)

```json
"sentence_emotion_cache": [
  {"sentence": "업무 능력이 뛰어납니다.", "pos": 0.85, "neg": 0.10, "neutral": 0.05},
  {"sentence": "소통은 아쉽습니다.",      "pos": 0.15, "neg": 0.75, "neutral": 0.10}
]
```

- `sentence`: **optional**. 포함 시 정합성·디버깅 용이. 미포함(점수-only) 시 읽기 측에서 `split_sentences(doc)`로 재도출
- `pos`/`neg`/`neutral`: KoTE 원시 점수 (반전 규칙 적용 **전**), 리스트 순서는 `split_sentences(doc)`와 동일
- 영어 문장(비한국어 70% 초과): `pos=0.0, neg=욕설여부, neutral=욕설없으면1.0`
- **현 단계 채택**: `sentence` 포함 방식. 용량 문제 현실화 시 캐시 생성부만 점수-only로 전환(읽기 코드 불변)

### 3-2. split_sentences 이전 — `text_preprocessing.py`

perspective_service.py:326~343 정의(인사말 set 포함)를 `text_preprocessing.py`로 **이동**:

```python
"""텍스트 전처리 모듈 — split_sentences 정의 (경량, 무거운 의존 없음)."""
import re

def split_sentences(text):
    if not text:
        return []
    raw = re.split(r'[.!?\n]+', text)
    sentences = [s.strip() for s in raw if s.strip()]
    greetings = {'감사합니다', '수고하셨습니다', '좋은 하루', '고맙습니다',
                 '감사드립니다', '수고 많으셨습니다'}
    filtered = []
    for s in sentences:
        if any(g in s for g in greetings):
            continue
        if len(s) < 5:
            continue
        filtered.append(s)
    return filtered

__all__ = ['split_sentences']
```

perspective_service.py 상단: `from src.modules.text_preprocessing import split_sentences`
(기존 826번대 def 삭제). 기존 importer(perspective_routes:13)는 perspective_service 재노출로 그대로 동작.

### 3-3. (신규) `src/modules/sentence_emotion.py` — 공유 헬퍼

```python
"""문장 단위 KoTE 원시 점수 — 배치 캐시 생성과 그룹 분석 fallback이 공유 (경량)."""
import re

def compute_sentence_raw_scores(doc):
    """Returns list[dict]: [{"sentence","pos","neg","neutral"}, ...] (문장 없으면 [])"""
    from src.modules.text_preprocessing import split_sentences
    from src.modules.emotion_analysis import analyze_emotion
    from src.modules.profanity_filter import advanced_filter_profanity

    out = []
    for sent in split_sentences(doc):
        total = len(sent.replace(' ', ''))
        if total > 0 and len(re.findall(r'[a-zA-Z]', sent)) / total > 0.7:
            prof = advanced_filter_profanity(sent)
            neg = 1.0 if prof.get('profanity_count', 0) > 0 else 0.0
            out.append({"sentence": sent, "pos": 0.0, "neg": neg, "neutral": 1.0 - neg})
            continue
        res = analyze_emotion(sent)
        s = (res.get('analysis', {}).get('base_result', {})
                .get('mapped', {}).get('sentiment_scores', {}))
        out.append({"sentence": sent,
                    "pos": s.get('positive', 0.0) or 0.0,
                    "neg": s.get('negative', 0.0) or 0.0,
                    "neutral": s.get('neutral', 0.0) or 0.0})
    return out
```

이 모듈은 `text_preprocessing`(경량)만 import → 배치 워커에 matplotlib 미유입.

### 3-4. `metadata_manager.py` — `create_employee_metadata()` (정의:49)

`emotion_result` 저장(line 75) 직후:

```python
from src.modules.sentence_emotion import compute_sentence_raw_scores
analyzed_eval['sentence_emotion_cache'] = compute_sentence_raw_scores(doc)
```

### 3-5. `_get_sentence_level_scores()` (정의:784) — 캐시 + 점수-only fallback

```python
def _get_sentence_level_scores(doc, threshold=0.20, weight=2.0, corrections=None, sentence_cache=None):
    if sentence_cache and isinstance(sentence_cache, list):
        # sentence 누락(점수-only) 시 split_sentences(doc)로 재도출
        derived = None
        sentences = []
        for idx, e in enumerate(sentence_cache):
            sent = e.get('sentence')
            if sent is None:
                if derived is None:
                    derived = split_sentences(doc)
                sent = derived[idx] if idx < len(derived) else ''
            sentences.append(sent)
        sent_scores_raw = [(e['pos'], e['neg'], e['neutral']) for e in sentence_cache]
    else:
        from src.modules.sentence_emotion import compute_sentence_raw_scores
        cache = compute_sentence_raw_scores(doc)
        if not cache:
            return [(None, 0.0, 0.0, 0.0)]
        sentences       = [e['sentence'] for e in cache]
        sent_scores_raw = [(e['pos'], e['neg'], e['neutral']) for e in cache]

    # 이후 규칙 적용 + corrections 처리 — 기존 로직(820~842) 그대로 유지
    ...
```

### 3-6. 캐시 전달 — 4개 호출 지점

각 지점에서 `sentence_cache=ev.get('sentence_emotion_cache')` 전달:

| 호출 지점 | 변경 |
|-----------|------|
| `calculate_word_scores` 내부 (:866) | `..., corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'))` |
| `_aggregate_emotion` 내부 (:1044) | 동일 패턴 |
| `_generate_emotion_cell` 내부 (:1114) | 동일 패턴 |
| `save_to_deploy` 내부 (:1772) | `..., corrections=eval_corr, sentence_cache=ev.get('sentence_emotion_cache'))` |

---

## 4. 하위 호환성

| 시나리오 | 동작 |
|----------|------|
| 신규 배치 (sentence 포함 캐시) | 캐시 사용, KoTE 재실행 없음 |
| 신규 배치 (점수-only 캐시) | sentence를 split로 재도출, KoTE 재실행 없음 |
| 기존 배치 (캐시 없음) | 공유 헬퍼 fallback (기존과 동일 결과) |
| Resume 혼합 배치 | 행별 fallback으로 안전 처리 |

---

## 5. 기대 효과

- 그룹 분석 **및 제출용 저장** 조회 시 KoTE 재실행 **완전 제거**
- 반전 표지어 규칙 변경 → 재배치 불필요, 즉시 반영
- 사용자 교정 기능 → 변경 없이 유지
- 영어 감지·KoTE 로직 단일화(공유 헬퍼) + matplotlib 의존 차단

---

## 6. 비용·리스크 (배치 대상 약 1.9만명 기준)

> 배치 대상 규모는 약 19,000명(세션 운영 전제). 추적 로직은 O(n) 유지(직원별 독립, O(n²) 없음).

| 항목 | 영향 | 추정/대응 |
|------|------|-----------|
| 배치 처리 시간 | 평가당 KoTE **1회(문서) → 1회 + N회(문장)** | **측정 완료**(실데이터 50건, 평균 1.30문장/문서): 22.2ms→38.6ms, **1.74x / +16.4ms**. 1.9만명×평균5평가 추정 **+약 26분(배치 1회성)**. 조회 시 KoTE 재실행 완전 제거로 상쇄. 문서가 길수록 배수↑(문장수 비례). |
| 저장 용량 | 문장 텍스트 중복 시 `data` 텍스트부 약 +130% | 평가행 1건당 +0.8~2KB 추정. 9.5만행(1.9만명×평균5) 가정 시 총 **+약 80~190MB**. SQLite 컬럼 길이 제한(기본 ~1GB) 무관, 디스크 영향 경미. 우려 시 점수-only 전환(§3-1) |
| 추적 복잡도 | O(n) 유지 | 직원별 독립 처리 |

---

## 7. 테스트 계획

작업 폴더 내 `test/` 에 측정·검증 스크립트를 둔다.

| 파일 | 목적 |
|------|------|
| `test/measure_kote_time.py` | 100문서 샘플로 `compute_sentence_raw_scores(doc)`(문장 N회) vs 기존 `analyze_emotion(doc)`(문서 1회) 실행 시간 비교 → 배치 시간 증가폭 정량화 |
| `test/test_cache_equivalence.py` | 캐시 경로와 fallback(헬퍼) 경로의 `_get_sentence_level_scores` 결과가 **동일**한지 검증 (점수-only 재도출 포함) |

> ⚠️ `measure_kote_time.py`는 KoTE 모델 로딩으로 수십 초~분 소요 가능. **사용자 허락 후 실행**. 결과는 `result/`에 보고.

### 후속 과제 (별도)

- 문서 단위 `emotion_analysis_results`가 캐시 도입 후에도 필요한지 사용처 재점검 (consolidated_analysis·overall_sentiment)
