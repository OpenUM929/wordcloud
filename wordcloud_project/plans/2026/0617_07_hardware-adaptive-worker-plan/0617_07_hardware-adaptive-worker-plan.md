# 성능 최적화 개발 계획서 — 하드웨어 기반 워커 수 동적 선정

> 상태: DN | 작성일: 2026-06-17 | 최종 수정: 2026-06-18 (v6, 작업6 구현 완료)
> 대상 시스템: `batch_processor.py`, `perspective_service.py`, `emotion_analysis.py`, `leadership_analysis.py`
> 작업 유형: 성능 최적화

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-17 | 전체 | v1 초안: 하드웨어 실측, AS-IS 분석, 전략 A/B/C 비교 |
| 2026-06-17 | 전체 | v2: 1차 검토 반영 |
| 2026-06-18 | VRAM게이트/우선순위/검증 | v3: VRAM 용량 게이트 추가, 작업7(모델통합) 필수화, 워커 상한 통일, 싱글톤 락(작업0) 추가, 배치추론 에러귀속 보완, V6 검증 추가 |
| 2026-06-18 | 워커 상한 계산식 | v3.1: GPU 워커 상한·VRAM 게이트를 고정값(6, 2500MB)에서 실측 VRAM 기반 동적 계산으로 교체 |
| 2026-06-18 | 전체 | v4: 비교/논쟁 과정 제거, 최종 결정사항과 구현 코드만 남겨 compact화 |
| 2026-06-18 | 작업0-4 | v5: 작업0-4 구현 완료(작업5는 P2 후속, 미착수). 부수 발견: `leadership_analysis.py`의 `_initialized` 플래그가 끝까지 True로 설정되지 않아 호출마다 모델을 재로드하던 기존 버그 — 작업3의 모델 통합(`KoTEModel` 공유)으로 로딩 경로 자체가 교체되며 함께 해소됨. 스모크 테스트로 `device=cuda:0`, 모델/토크나이저 동일 인스턴스 공유 확인(V1). V2-V6은 대규모 배치 실데이터 검증 필요 — 미수행 |
| 2026-06-18 | 작업5 재설계, 작업6 신규 | v6: `scripts/bench_kote_batch_inference.py`(독립 벤치마크) 작성·실행 결과, 실제 GPU 호출량은 작업5 원안(문서 단위, evaluations 리스트)이 아니라 `sentence_emotion.py`의 문장 단위 루프에 몰려 있음을 확인(문서 단위 배치 speedup 1.6~1.8x vs 문장 단위 배치 speedup 최대 7.09x, RTX 3050 6GB 기준). 이에 따라 **작업5(문서 단위)는 보류**하고 **작업6(문장 단위 배치)을 대신 구현**. 단일 호출 vs 배치 호출 결과가 1e-6 이내로 일치함을 회귀 테스트로 확인(V3 일부 충족) |

---

## 1. 배경 (확정 사실)

- `batch_processor.py`(L608-619): CPU 캡 8 고정 + 데이터량 구간별 고정 워커 수, `ThreadPoolExecutor`(L735) 사용.
- `perspective_service.py`(L2047): `min(cpu_count, 4)` 고정.
- 현재 PC 실측: i5-14400(16스레드) / RAM 32GB / RTX 3050 6GB(여유 ~5.4GB). GPU 유휴 상태.
- `emotion_analysis.py`, `leadership_analysis.py`가 동일 KoTE 모델 파일을 **각자 로딩**(싱글톤이지만 모듈이 2개라 인스턴스도 2개, ~3GB 중복).
- Sarcasm 모델(`sarcasm_analysis.py` L61-62,80-81,131-132)은 이미 GPU 사용 중 — 동일 패턴 재사용 가능.
- 내부망 배포(`deployment.md` L101,114)도 CUDA 드라이버 설치 + torch CUDA 빌드를 전제 — 운영 환경도 GPU 보유 가정 유효.
- ProcessPoolExecutor는 **배제**: Windows는 spawn만 지원해 워커당 모델 재로딩(~4GB) 필요, GPU 전환으로 CPU 부하가 줄어든 만큼 GIL도 더는 병목이 아님.

## 2. 최종 설계 결정

1. 워커 수는 CPU 코어/가용 RAM/가용 VRAM을 **매 실행 시 실측**해서 계산한다 (PC가 바뀌면 자동으로 값도 바뀜 — 고정 상수 금지).
2. GPU 사용 가능 + VRAM 충분 → GPU 모드. VRAM 부족 시 자동으로 CPU-only 모드로 강하.
3. emotion/leadership은 **KoTE 모델 1개 인스턴스를 GPU에서 공유**한다 (중복 로드 금지 — 안 그러면 VRAM 안전 한도 초과).
4. 단일 GPU 디바이스에 대한 동시 추론 호출은 거의 직렬화되므로, GPU 모드 워커 수는 VRAM 여유량이 결정한다(CPU 코어 수가 아님).

---

## 3. 구현 작업 (순서대로 적용)

### 작업 0 (P1) — 싱글톤 초기화 락 추가
**대상**: `emotion_analysis.py`(L298-321), `leadership_analysis.py`(L25-33)
**이유**: 워커가 동시에 첫 호출을 하면 `if _instance is None` 락 부재로 모델이 일시 중복 로드될 수 있음(VRAM 한도 잠식).

```python
# emotion_analysis.py
import threading
_emotion_analyzer_instance = None
_emotion_analyzer_lock = threading.Lock()

def analyze_emotion(text, config_path=None, output_path=None):
    global _emotion_analyzer_instance
    if _emotion_analyzer_instance is None:
        with _emotion_analyzer_lock:
            if _emotion_analyzer_instance is None:
                _emotion_analyzer_instance = EmotionAnalysis(config_path)
    return _emotion_analyzer_instance.analyze(text, output_path)
```

```python
# leadership_analysis.py
import threading

class LeadershipAnalysis:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, model_path=None, config_path=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
```
**롤백**: 락 제거.

---

### 작업 1 (P1) — CPU 캡 해제 + 워커 산정 단일화
**대상**: `batch_processor.py` L608-619

```python
# AS-IS
cpu_count = min(multiprocessing.cpu_count(), 8)
if employee_count < 10:     num_workers = 1
elif employee_count < 50:   num_workers = min(2, cpu_count)
elif employee_count < 100:  num_workers = min(4, cpu_count)
elif employee_count < 500:  num_workers = min(6, cpu_count)
else:                       num_workers = cpu_count

# TO-BE: 산정 로직을 _calc_adaptive_workers()(작업2)로 단일화
num_workers = _calc_adaptive_workers(employee_count)
```
**롤백**: AS-IS 코드로 복원.

---

### 작업 2 (P1) — `_calc_adaptive_workers()` 신규 함수 (CPU/RAM/VRAM 실측 기반)
**대상**: `batch_processor.py` (신규 함수 추가)

```python
import psutil
import multiprocessing

MODEL_VRAM_RESERVE_MB = 2300   # KoTE 공유 1개(~1.8GB) + Sarcasm(~0.5GB) — 모델 크기는 PC 무관
VRAM_PER_WORKER_MB = 250       # 워커 1개당 배치 추론 텐서 예상치
GPU_OS_RESERVE_MB = 1024       # GPU OS/디스플레이 예약
GPU_SAFETY_RATIO = 0.20        # 전체 VRAM의 20% 추가 예비

def _calc_adaptive_workers(employee_count=0):
    """CPU/RAM/VRAM 실측값 기반 워커 수 동적 계산 (PC마다 자동으로 달라짐)"""
    cpu_cores = multiprocessing.cpu_count()
    ram_gb = psutil.virtual_memory().available / (1024**3)
    gpu_ok = False
    vram_worker_cap = 0
    try:
        import torch
        if torch.cuda.is_available():
            free_vram_mb, total_vram_mb = (x / (1024**2) for x in torch.cuda.mem_get_info())
            safety_available_mb = total_vram_mb - GPU_OS_RESERVE_MB - (total_vram_mb * GPU_SAFETY_RATIO)
            available_for_workers_mb = safety_available_mb - MODEL_VRAM_RESERVE_MB
            if available_for_workers_mb >= VRAM_PER_WORKER_MB:
                gpu_ok = True
                vram_worker_cap = max(2, int(available_for_workers_mb // VRAM_PER_WORKER_MB))
    except ImportError:
        pass

    if gpu_ok:
        # GPU가 실제 병목 → VRAM 여유에서 도출한 상한이 결정 (이 PC=6GB에서는 결과가 6)
        cpu_worker_cap = max(2, int(cpu_cores * 0.5))
        max_workers = min(cpu_worker_cap, vram_worker_cap)
    else:
        # CPU-only: GIL 제약, 4개 초과는 실익 없음
        max_workers = max(1, int(cpu_cores * 0.15))
        max_workers = min(max_workers, 4)

    if ram_gb < 4:
        max_workers = 1

    if employee_count < 10:
        return min(1, max_workers)
    return max_workers
```
**검증**: 이 PC에서 `total_vram_mb=6144 → safety_available=3891 → available_for_workers=1591 → vram_worker_cap=6`, `cpu_worker_cap=8` → `max_workers=6`.
**롤백**: 함수 삭제, 작업1의 AS-IS 코드로 복원.

---

### 작업 3 (P1, 작업7과 동시 적용 — 필수) — KoTE GPU 전환 + 모델 인스턴스 통합
**대상**: `emotion_analysis.py`(L58-69, L107), `leadership_analysis.py`(L62-63, L223, L227), 신규 `kote_shared.py`

> ⚠️ emotion/leadership을 GPU로 옮기면서 모델을 통합하지 않으면 KoTE가 GPU에 2벌(~3~3.6GB) 올라가 VRAM 안전 한도(3,892MB)를 초과할 수 있다. **반드시 통합과 동시에 적용.**

```python
# kote_shared.py (신규)
import threading
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

class KoTEModel:
    """emotion + leadership 공유 KoTE 모델 싱글톤"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    from src.config.settings import MODEL_PATH
                    cls._instance.tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
                    cls._instance.model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
                    if torch.cuda.is_available():
                        cls._instance.model = cls._instance.model.to('cuda')
                    cls._instance.device = next(cls._instance.model.parameters()).device
        return cls._instance
```

`emotion_analysis.py`와 `leadership_analysis.py`는 각자 모델/토크나이저를 로딩하던 부분(L58-69, L62-63)을 `KoTEModel()` 호출로 교체하고, 추론 시 입력 텐서를 모델과 같은 device로 이동:

```python
# 추론 호출부 공통 패턴 (emotion_analysis.py L107, leadership_analysis.py L223 적용)
inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
inputs = {k: v.to(model.device) for k, v in inputs.items()}
with torch.no_grad():
    outputs = model(**inputs)
probs = torch.softmax(outputs.logits, dim=1)[0]
if probs.is_cuda:
    probs = probs.cpu()
```
**롤백**: 각 모듈이 독립적으로 모델 로딩하도록 복원, `if torch.cuda.is_available()` 블록 제거.

---

### 작업 4 (P1) — `perspective_service.py` 캡 완화
**대상**: `perspective_service.py` L2047

```python
# AS-IS
num_workers = min(multiprocessing.cpu_count(), 4)
# TO-BE
num_workers = min(multiprocessing.cpu_count(), 8)
```
배치 처리와 맥락이 달라(이미 분석된 결과를 행렬로 재구성하는 가벼운 연산) 동일 로직을 적용하지 않고 캡만 완화.
**롤백**: `4`로 복원.

---

### 작업 5 (보류) — GPU 배치 추론(문서 단위, evaluations 리스트)
**대상**: `metadata_manager.py`의 `create_employee_metadata()`(L50-107)

> **보류 사유**: 벤치마크(작업6 참고) 결과 문서 단위 배치는 speedup 1.6~1.8x로 효과가 제한적인 반면,
> `metadata_manager.py`의 평가문서별 `try/except` 에러 귀속(`evaluation_id` 단위)을 깨야 하는 리스크가 더 큼.
> 작업6(문장 단위 배치)이 같은 호출 경로(`analyze_emotion`)를 더 큰 효과(최대 7x)로 대체하므로 우선순위 낮춤.
> 필요 시 아래 코드로 별도 구현 가능 — 단, L98-107 에러 귀속을 배치 인덱스 기준으로 재매핑해야 함.

```python
def analyze_batch(self, texts: list[str]):
    inputs = self.tokenizer(texts, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = self.model(**inputs)
    return outputs.logits.softmax(dim=1).cpu().tolist()
```

---

### 작업 6 (구현 완료) — 문장 단위 KoTE 배치 추론
**대상**: `emotion_analysis.py`(신규 `_postprocess_predictions`/`analyze_batch`/`analyze_emotion_batch`), `sentence_emotion.py`(`compute_sentence_raw_scores`), 신규 `scripts/bench_kote_batch_inference.py`

**배경**: `sentence_emotion.py`의 `compute_sentence_raw_scores()`가 평가문서 1건당 문장 수만큼(평균 ~8회) `analyze_emotion()`을 개별 호출 — 실제 GPU 호출량 대부분이 여기서 발생. 작업5(문서 단위, 직원당 3~10건)보다 호출 빈도가 훨씬 높아 배치화 효과가 큼.

**구현**:
1. `emotion_analysis.py`: 기존 `analyze()`의 후처리 로직(레이블 매핑·top_3·감성 점수 집계)을 `_postprocess_predictions()`로 추출해 단일/배치 양쪽에서 공유 → 두 경로의 결과가 항상 같은 로직으로 계산됨을 보장.
2. `EmotionAnalysis.analyze_batch(texts)` 신규: 텍스트 리스트를 한 번에 토크나이즈·forward, 항목별로 `_postprocess_predictions()` 적용. 모듈 함수 `analyze_emotion_batch(texts)`도 함께 추가(기존 `analyze_emotion()`과 동일한 싱글톤·락 사용).
3. `sentence_emotion.py`: 영어 문장(KoTE 우회)과 한국어 문장을 먼저 분리한 뒤, 한국어 문장만 `_SENTENCE_BATCH_SIZE=32`(벤치마크 기준 speedup이 가장 큰 구간) 단위로 묶어 `analyze_emotion_batch()` 호출. 결과는 원래 문장 순서로 재배열.

**검증 결과(이 PC, RTX 3050 6GB)**:
- 단일 호출 vs 배치 호출 결과 일치(긍정/부정/중립 점수 오차 < 1e-6, 샘플 4건 전수 일치)
- 8문장 문서 기준 처리 시간: 배치 적용 후 문서당 ~9.7ms (적용 전 추정 ~48ms, 약 5x)
- 영어 문장 혼합 문서에서도 정상 동작(KoTE 우회 경로 영향 없음) 확인

**롤백**: `sentence_emotion.py`를 `analyze_emotion_batch` 대신 `analyze_emotion`을 문장마다 호출하는 이전 방식으로 되돌리면 됨(`emotion_analysis.py`의 `analyze_batch`/`analyze_emotion_batch`는 그대로 두어도 무해 — 호출하는 곳이 없어지면 단순 미사용 코드).

---

## 4. 검증 체크리스트

- [x] V1: `model.device == 'cuda:0'` 확인 (emotion/leadership 둘 다) — 스모크 테스트로 확인, 모델/토크나이저 동일 인스턴스 공유도 확인
- [ ] V2: GPU vs CPU 결과 일치 — 100명, 감정/리더십 점수 오차 < 1e-4 (dev: GPU만 보유해 CPU 비교 불가 — 내부망에서 확인)
- [x] V3-dev: 작업6 배치추론 vs 개별추론 결과 오차 < 1e-6 — 합성 문장 4건으로 확인(코드 경로 정합성)
- [ ] V3-prod: 위와 동일하되 **실제 평가문서**로 재확인 (내부망 필요)
- [ ] V4: 처리 시간 측정 — 500명/1000명, 이번 변경 전후 각 3회
- [ ] V5: RAM 안정성 — 500명 배치 중 OOM 없음, 작업관리자 사용량 < 24GB
- [ ] V6: VRAM 안정성 — `nvidia-smi`로 배치 중 모니터링, 사용량이 4-3절 안전 한도(실측 기준 ~3,892MB) 이내, OOM 없음

## 5. 롤백 계획

| 상황 | 방법 |
|------|------|
| GPU 추론 에러 | `torch.cuda.is_available()` 조건부 분기 → CPU 폴백 |
| VRAM OOM | FP16 전환 또는 `_calc_adaptive_workers()`가 자동으로 worker=1까지 강하 |
| 작업6 배치추론 오차/문제 발생 | `sentence_emotion.py`를 문장별 `analyze_emotion()` 개별 호출로 원복(작업6 섹션 참고) |
| 전체 롤백 | `git stash` |

## 6. 제외 결정 (요약)

| 항목 | 사유 |
|------|------|
| ProcessPoolExecutor 전환 | Windows spawn으로 워커당 모델 재로딩(~4GB), GPU 전환 후 GIL은 병목 아님 |
| 워커 상한을 8/11 등 고정값으로 채택 | GPU는 단일 디바이스에서 직렬화 — CPU 코어 수 기준 상한은 무의미, VRAM 실측 기반으로 대체 |
| VRAM 용량 미확인 상태로 GPU 모드 진입 | 작은 VRAM 환경에서 OOM 위험 — `_calc_adaptive_workers()`가 자동으로 CPU 모드로 강하 |
| `perspective_service.py`에 동일 동적 로직 적용 | 연산 특성이 배치 처리와 다름(경량 I/O 위주) — 캡 완화만으로 충분 |

---

*상태: DN — 작업0-4, 작업6(문장 단위 KoTE 배치 추론) 구현 완료. 작업5(문서 단위 배치)는 효과가 작아(1.6-1.8x vs 작업6의 최대 7.09x) 보류. dev에서는 합성 문장 정합성(V3-dev)만 확인했고, V2/V3-prod/V4/V5/V6은 실제 데이터·하드웨어가 있는 내부망에서 검증 필요.*
