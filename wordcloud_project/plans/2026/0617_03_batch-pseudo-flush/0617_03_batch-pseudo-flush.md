# 배치 "데이터 수집" 멈춤 해소 — 가명화 매핑 일괄 저장(flush) 전환

> 상태: DN | 완료일: 2026-06-17
> 작업 유형: 기능 문제 분석/디버깅 + 성능 결함 수정

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-17 | 최초 작성 | 가명화 O(n²) 파일 재기록 병목 진단 및 일괄 저장 전환 계획 수립 |
| 2026-06-17 | 구현 완료 | bulk_mode 도입 + Phase 1 래핑 + 진행 문구 보강. 테스트 7건 통과 (DN) |

## 구현 결과 (2026-06-17)

- `src/modules/pseudonym_manager.py`: `bulk_mode()`/`flush()`/`_maybe_save()` 추가, `get_pseudonym`·`link_mapping` 저장 호출을 `_maybe_save`로 교체. 기본 동작(즉시 저장) 불변.
- `src/services/batch_processor.py`: Phase 1 ingest 루프를 `_pseudo_mgr.bulk_mode()`(None 시 `nullcontext`)로 래핑, 파일 분석 구간 진행 문구 선설정, 첫 청크 전 `(0 / N 라인)` 표기.
- 테스트: 신규 `test/test_bulk_mode.py` 3건(기본 즉시저장 / 일괄 보류·flush·전건보존 / 예외 시 flush) + 기존 `test_pseudonym_manager.py` 4건 회귀 = **총 7건 통과**.
| 2026-06-17 | 4-1, 7 | 검토 피드백 반영: 인스턴스 전역 플래그 명시, Phase 2 확인 결과 추가, link_mapping 교체 누락 방지, self-assignment 노트 |

---

## 1. 문제 현상 (REQ: 260617.txt)

- "4. 배치 처리 및 저장 > 배치 처리 시작" 클릭 후 **1단계 "데이터 수집 준비 중..."에서 멈춤**.
- 입력 데이터: CSV, 38.7MB, **2,448,160 라인**.
- 사용자 요청: "사전 작업 중 문제라면 해당 부분 로딩 정보 갱신 기능도 필요함. 무작정 기다려야함."

> 화면이 죽은 게 아니라 **Phase 1(데이터 수집) 가명화 처리가 사실상 정지 수준으로 느린 것**이 원인이다.

---

## 2. 근본 원인 분석 (코드 확인 완료)

### 2-1. 진행 상태 텍스트가 첫 청크 완료 전까지 갱신 안 됨

- `src/services/batch_processor.py:517~519`
  - `current_step=0`, `progress=5`, `status_message='데이터 수집 준비 중...'` 설정.
- 같은 파일 `:531~537` — **첫 청크 처리가 끝나야** `status_message`가 `'데이터 수집 중 (N / total 라인)'`으로 갱신된다.
- 즉 첫 청크가 끝나지 않으면 SSE(`src/services/batch_events.py:49~75`, 0.5초 폴링)가 계속 "데이터 수집 준비 중..."만 전송한다 → **멈춘 것처럼 보임**.

### 2-2. 진짜 병목: 가명화가 새 ID마다 파일 전체를 재암호화·재기록 (O(n²))

호출 경로:

1. Phase 1 ingest 루프 `batch_processor.py:521~528`
   → 청크마다 `_extract_rows_from_chunk()` 호출(`:90~139`).
2. `_extract_rows_from_chunk` 내부:
   - `:100~101` — 직원 ID마다 `_pseudo_mgr.get_pseudonym(emp_id)`.
   - `:121~123` — `evaluator_id`가 없으면 **행마다** `eval-{emp_id}-{date_str}` 생성.
   - `:134~135` — `_pseudo_mgr.apply_pseudonyms_to_dict(evaluation, pseudonym_fields)`.
3. 강제 가명화 대상에 `evaluator_id` 포함(`:454~461`) → 생성된 `evaluator_id`가 전부 가명화 대상.
4. `apply_pseudonyms_to_dict`(`src/modules/pseudonym_manager.py:96~104`) → 필드별 `get_pseudonym()`.
5. `get_pseudonym`(`:62~74`) — **새 ID가 나올 때마다** `:73`에서 `_save_mappings(data)` 호출.
6. `_save_mappings`(`:50~60`) — 매핑 전체를 `json.dumps` → `Fernet.encrypt` → `.tmp` 파일 쓰기 → `os.replace`.

**비용 구조:**
- 새 ID 1개 추가 = 매핑 dict **전체**를 직렬화·암호화·디스크 재기록.
- 매핑이 커질수록 1회 저장 비용도 커짐 → 새 ID 누적 N개에 대해 **합계 O(N²)**.
- `evaluator_id = eval-{직원}-{연도}` 카디널리티가 (직원 수 × 연도) 규모. 1.9만+ 직원 × 평가 연도이므로 새 ID 수만 수만~수십만 개.
- 결과적으로 첫 청크(10,000행)조차 수만 회의 전체 파일 재암호화를 유발 → "데이터 수집 준비 중"에서 정지.

> 메모리 기록 `배치 규모 19,000명 — 추적 로직 O(n) 이하 유지(O(n²) 금지)` 규칙 위반.

### 2-3. 관련 상수/설정 (확인)

- `CHUNK_SIZE = 10000` (`batch_processor.py:423`).
- 매핑 파일 경로: `PSEUDONYM_MAPPINGS_PATH` (`src/config/settings.py`), 인스턴스 생성 `batch_processor.py:465~467`.

---

## 3. 영향도 분석 (사용처 전수 조사 완료)

`PseudonymManager` 가명 생성/저장 경로 전수 검색 결과:

| 위치 | 호출 | 신규 가명 생성 | 비고 |
|------|------|----------------|------|
| `batch_processor.py:101,135` | `get_pseudonym`, `apply_pseudonyms_to_dict` | **O | 핫패스 (이번 대상) |
| `profanity_db_service.py:219` | `get_pseudonym` | O(단건) | 단건 호출, 영향 미미 |
| `admin_routes.py:107` | `link_mapping` | O(단건) | 관리자 수동 매핑 |
| `perspective_service.py:553~559` | 읽기 전용(`get_real_id`류, 신규 생성 안 함) | X | 복원 전용 |
| `batch_events.py` 복원 | `get_real_id` | X | 배치 완료 후 복원 |
| `wordcloud_data_service.py:116`, `batch_manager.py:15` | 인스턴스 생성 | - | 별도 인스턴스 |

**보존해야 할 제약:**
- `plans/2026/0604_01_deploy-resume/test/test_pseudonym_manager.py` — 100 스레드 동시 `get_pseudonym` 후 파일에 100건 저장되어 있어야 함을 검증.
  → **기본 동작(즉시 저장)은 절대 변경 금지.** 신규 일괄 모드는 배치 경로에서만 명시적으로 활성화.
- 다중 인스턴스가 같은 파일을 공유 → 일괄 모드 종료 시점(= flush)에 반드시 파일이 최신화되어, 이후 Phase 2/완료 복원이 새 매핑을 읽을 수 있어야 함.

---

## 4. 수정 방안

### 4-1. `PseudonymManager`에 일괄 저장 모드 추가 (`src/modules/pseudonym_manager.py`)

기본 동작은 그대로 두고, **명시적 컨텍스트 동안만** per-ID 저장을 보류했다가 1회 flush.

```python
from contextlib import contextmanager

# __init__ 에 추가
self._defer_save = False
self._dirty = False

def _maybe_save(self, data):
    """일괄 모드면 저장 보류(dirty 표시)만, 아니면 즉시 저장."""
    if self._defer_save:
        self._dirty = True
    else:
        self._save_mappings(data)

@contextmanager
def bulk_mode(self):
    """이 블록 동안 새 가명을 메모리에만 누적하고, 종료 시 1회 저장."""
    with self._lock:
        self._defer_save = True
    try:
        yield self
    finally:
        with self._lock:
            self._defer_save = False
            if self._dirty:
                self._save_mappings(self._mapping_cache)
                self._dirty = False

def flush(self):
    """보류된 변경을 즉시 디스크에 반영."""
    with self._lock:
        if self._dirty:
            self._save_mappings(self._mapping_cache)
            self._dirty = False
```

- `get_pseudonym`(`:73`)과 `link_mapping`(`:89`)의 `self._save_mappings(data)` → `self._maybe_save(data)`로 교체.
- `_mapping_cache`는 `_save_mappings`가 항상 갱신하므로(`:52`), 일괄 모드에서도 메모리 상 매핑은 즉시 최신 → 같은 인스턴스 내 후속 `get_pseudonym` 정합성 유지.
- 기본값 `_defer_save=False` → **기존 호출자/테스트 동작 불변**.
- `_defer_save`는 인스턴스 전역 플래그이므로 `bulk_mode`가 활성화된 동안 동일 인스턴스를 공유하는 **모든 스레드**의 저장이 보류됨. 배치 Phase 1에서는 `_pseudo_mgr`를 배치 프로세서 내부에서 매번 새로 생성(`batch_processor.py:467`)하므로 타 스레드 간섭 없음. 구현 시 이 전제가 유지되는지 확인 필요.

### 4-2. 배치 Phase 1을 일괄 모드로 감싸기 (`src/services/batch_processor.py`)

- Phase 1 ingest 루프(`:521~`)를 `with _pseudo_mgr.bulk_mode():` 로 감싼다.
- 직원 ID 가명화(`:101`)도 같은 루프 안이므로 함께 포함됨.
- **Phase 1 종료 직후(= bulk_mode 블록 종료)에 1회 flush** 되어, Phase 2 및 완료 시 복원이 최신 매핑을 읽도록 순서 보장.
- 단, `_pseudo_mgr`가 `None`일 수 있으므로(`:463~467`) `None` 가드 필요. (예: `contextlib.nullcontext()` 사용 또는 분기.)

### 4-3. 진행 표시 보강 (사용자 요청: "로딩 정보 갱신")

- `_count_total_lines`(`:473~481`)는 2.4M 라인 전체를 1패스 스캔 → 수 초 소요. 스캔 직전 상태를 `'데이터 수집 시작 — 파일 분석 중...'` 으로 먼저 설정해, 카운트 구간에도 화면이 변하도록 한다.
- 4-1/4-2 적용으로 청크 처리 속도가 정상화되면 `:531~537`의 청크별 갱신(10,000행 단위)이 0.5초 SSE 주기로 흘러 진행률이 실시간 반영된다.
- (선택) 첫 청크 진입 전 `status_message='데이터 수집 중 (0 / N 라인)'`을 선설정해 "준비 중" 고착 인상을 제거.

---

## 5. 작업 순서

1. `pseudonym_manager.py`: `bulk_mode`/`flush`/`_maybe_save` 추가, `get_pseudonym`·`link_mapping` 저장 호출 교체. (기본 동작 불변)
2. `batch_processor.py`: Phase 1 루프 `bulk_mode` 래핑(+ `None` 가드), 진행 상태 선설정 문구 추가.
3. 테스트: 기존 `test_pseudonym_manager.py` 회귀(즉시 저장 100건) + 신규 `bulk_mode` 테스트(블록 내 0회 저장, 종료 시 1회 저장·전건 보존) 작성 → `test/`에 저장.
4. 소규모 CSV로 정확성 검증, 결과를 `result/`에 기록.

## 6. 롤백 계획

- 변경 파일 2개(`pseudonym_manager.py`, `batch_processor.py`)로 국한.
- 문제 시 `bulk_mode` 래핑 제거 + `_maybe_save` → `_save_mappings` 원복이면 즉시 종전 동작 복귀.

## 7. 리스크 / 확인 필요

- **중단 시 매핑 유실 가능성**: 일괄 모드 도중 프로세스가 강제 종료되면 보류된 신규 매핑이 디스크에 없을 수 있음. 단, bulk_mode `finally`에서 flush → 정상/예외 모두 저장. `_run_batch_process`(`batch_service.py:281~299`) except 경로 추가 flush는 불필요(이미 `finally`에서 저장 완료됨). 프로세스 kill 시 유실은 허용 범위로 판단.
- **Phase 2 추가 신규 가명 생성**: `batch_processor.py:540` 이후 코드 재확인 결과, Phase 2에서는 `_pseudo_mgr`를 직접 사용하지 않고 Phase 1에서 이미 가명화된 staging.db 데이터를 처리함. **신규 가명 생성 없음 — Phase 1 한정으로 확인됨**.
- **`link_mapping` `_maybe_save` 교체 누락 방지**: `pseudonym_manager.py:89`의 `link_mapping`도 `_save_mappings` → `_maybe_save`로 교체 대상. 현재 배치 Phase 1에서는 호출되지 않지만(영향도 표: `admin_routes.py` 단건), 방어적 코딩 차원에서 누락 없이 적용.
- **`_save_mappings(self._mapping_cache)` self-assignment (cosmetic)**: `_save_mappings:52`에서 `self._mapping_cache = data`를 수행하므로, `bulk_mode` finally에서 `self._save_mappings(self._mapping_cache)`를 호출하면 무의미한 자기 재할당 발생. 기능상 무해하나 가독성을 위해 `_save_mappings` 내부에 `if data is self._mapping_cache: return` 가드 추가 검토 가능. 필수 수정 사항 아님.

---

## 부록 — ②번 습득 데이터 게시판 (별건, 본 계획 범위 외)

사용자 확인: "NNav 메뉴의 '습득데이터' 게시판 열 이름과 열 내용" 건. `web/templates/acquired_data.html` 컬럼 정렬 자체는 정상이며, 보고된 행은 `analysis_results` 미저장으로 감정분석/욕설/비꼼이 `-`로 표시됨(`perspective_service.py:2067~2107`, `acquired_data.html:140~163`). **별도 계획서로 분리 처리 예정** — 정확히 어떤 열/내용 불일치인지 추가 확인 후 진행.
