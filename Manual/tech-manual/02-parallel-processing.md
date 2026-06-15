# 02. 병렬·대량 배치 처리

> 코드 위치: `wordcloud_project/src/services/batch_processor.py`

## 개요 — 왜 필요한가

분석 대상은 **약 1.9만 명**의 인사평가다. 한 명당 형태소 분석 + 감정 분석(딥러닝) + 리더십 + 반어법 + 비속어 검사를 모두 수행하면, 한 명을 순서대로(順次) 처리할 경우 전체가 매우 오래 걸린다.

그래서 이 시스템은 **여러 직원을 동시에(병렬로) 처리**하고, **처리량에 따라 일꾼(worker) 수를 자동으로 늘렸다 줄였다** 하며, **중간에 멈춰도 처음부터 다시 하지 않고 멈춘 지점부터 이어서** 한다.

비유하자면, 평가서 1.9만 장을 여러 직원이 나눠서 동시에 채점하되,
- 일감이 적으면 1~2명만 투입하고, 많으면 최대 인원을 투입하며,
- 채점한 답안지는 그 즉시 금고(DB)에 넣고,
- 정전이 나도 "어디까지 채점했는지" 메모(체크포인트)를 보고 이어서 채점한다.

---

## 적용 분야

- 대규모 인사평가 일괄 분석 (수천~수만 건)
- 야간/장시간 배치 작업 (중단 후 재개 필요)
- 서버 자원에 맞춘 적응형(adaptive) 처리량 조절

---

## 기술 상세

### 1. 동적 워커 수 결정 (데이터 양에 비례)

직원 수에 따라 병렬 워커 수를 단계적으로 정한다. CPU 코어 수는 최대 8로 상한을 둔다.

코드 위치: `batch_processor.py:541`

```python
employee_count = len(grouped_data)
cpu_count = min(multiprocessing.cpu_count(), 8)

if employee_count < 10:      num_workers = 1
elif employee_count < 50:    num_workers = min(2, cpu_count)
elif employee_count < 100:   num_workers = min(4, cpu_count)
elif employee_count < 500:   num_workers = min(6, cpu_count)
else:                        num_workers = cpu_count
```

| 직원 수 | 워커 수 |
|---------|---------|
| < 10명 | 1 |
| < 50명 | 2 |
| < 100명 | 4 |
| < 500명 | 6 |
| 500명 이상 | CPU 코어 수 (최대 8) |

> 소량일 때 과도한 병렬화로 인한 오버헤드를 피하고, 대량일 때 자원을 최대한 활용하기 위한 설계.

### 2. 병렬 실행 — `ThreadPoolExecutor`

코드 위치: `batch_processor.py:665`

```python
with ThreadPoolExecutor(max_workers=num_workers) as executor:
    future_to_employee = {
        executor.submit(process_single_employee, item): item[0]
        for item in employee_items
    }
    for future in as_completed(future_to_employee):
        result = future.result()
        ...
```

- 직원 1명 처리 단위 함수: `process_single_employee(args)` (`batch_processor.py:590`)
- `as_completed` 로 **먼저 끝난 직원부터** 결과를 회수해 즉시 후처리(비속어 검사·DB 저장)한다.

> AI 추론은 내부적으로 C/CUDA 레벨에서 GIL을 해제하므로, 스레드 풀로도 실질적인 병렬 처리 이득을 얻는다. (별도 프로세스 풀 대비 모델 메모리 공유·직렬화 비용이 없는 장점.)

### 3. 분석기 사전 초기화 (Stage 2)

병렬 루프 진입 전에 무거운 분석기/사전을 **한 번만** 초기화해 모든 워커가 공유한다.

코드 위치: `batch_processor.py:559`

```python
nlp_analyzer = NLPAnalysis.get_instance(NLP_CONFIG_PATH)     # 싱글톤
stopword_mgr = get_stopword_manager(...stopwords.json)
```

### 4. 직원 단위 즉시 저장 (Crash-safe)

한 직원의 메타데이터가 완성되면 **그 즉시 DB에 영구 저장**한다. 따라서 이후 "완료"로 기록되는 직원은 반드시 DB에 존재한다.

코드 위치: `batch_processor.py:676`

```python
upsert(_eid, _meta, _meta.get('evaluations', []), batch_id)   # 직원별 즉시 DB 저장
```

저장 후에는 `metadata`를 `None`으로 비워 **메모리를 즉시 해제**한다(`batch_processor.py:695`) — 1.9만 명 분량을 메모리에 쌓지 않기 위함.

### 5. 체크포인트 & 재개(Resume)

- 1000건마다 체크포인트를 저장한다. (`CHECKPOINT_INTERVAL = 1000`, `batch_processor.py:9`)
- 체크포인트에는 처리 수, 전체 수, 마지막 직원 ID, 완료 직원 목록이 들어간다. (`save_checkpoint`, `batch_processor.py:12`)
- 재개 시 이미 완료된 직원은 건너뛴다. (`batch_processor.py:634`)

```python
if _is_resume and prior_completed:
    employee_items = [item for item in employee_items
                      if str(item[0]) not in prior_completed]
```

### 6. 작업서(Work Order) 진행 추적 — O(델타)

진행 상황 추적을 **O(n²) 가 되지 않도록** 설계했다. 매번 전체를 다시 쓰지 않고, **새로 저장된 직원 ID 델타만** items 테이블에 append 한다.

코드 위치: `batch_processor.py:644` `_flush_work_order()`

```python
if _pending_persisted:
    add_completed_employees(batch_id, _pending_persisted)   # 신규분만 append (O(델타))
    _pending_persisted = []
update_work_order_progress(batch_id, processed_employees=..., ...)
```

> ⚠️ **유지보수 주의**: 1.9만 명 규모에서 추적 로직을 O(n²)으로 만들면(매 직원마다 전체 목록 재기록) 전체 처리 시간이 급격히 늘어난다. 반드시 델타 기반으로 유지할 것.

---

## 관점 분석에서의 병렬 처리

관점(매트릭스) 분석도 별도로 병렬화되어 있다.

코드 위치: `perspective_service.py:1859`

```python
num_workers = min(multiprocessing.cpu_count(), 4)
with ThreadPoolExecutor(max_workers=num_workers) as executor:
    ...
```

여기서는 상한이 4로, 매트릭스 셀 단위 집계를 병렬화한다.

---

## 핵심 포인트 정리

| 기법 | 효과 |
|------|------|
| 데이터 양 비례 워커 수 | 소량은 가볍게, 대량은 최대 활용 |
| `ThreadPoolExecutor` + `as_completed` | 끝난 것부터 즉시 후처리 |
| 싱글톤 분석기 사전 초기화 | 모델 1회 로드, 워커 공유 |
| 직원별 즉시 DB 저장 | 중단되어도 완료분 보존 (crash-safe) |
| 1000건 체크포인트 + Resume | 처음부터 다시 안 함 |
| 델타 기반 진행 추적 | O(n) 유지, 대규모에서도 빠름 |

---

*다음: [03. 자연어 형태소 분석 (Kiwi)](03-nlp-morphological-analysis.md)*
