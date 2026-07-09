# 계획서 — eval 데이터 이중 가명화 방지 → 워드클라우드 정상화

> 상태: Done — ⚠️ 본문(§1~§7)은 **당시의 오진(誤診) 기록을 그대로 보존**한 학습 자료다. 실제 원인·해결은 최하단 **"🔄 반전"** 섹션 참조 | 작성일: 2026-06-25 | 수정일: 2026-06-30
> 작업 유형: B — 기능 개선 (당시 분류 그대로 보존 — 사실은 A 버그였고 이 오분류 자체가 실패의 일부였다)

> 📌 **읽는 법**: 아래 §1~§7은 "우리가 그때 무엇을 사실이라 믿었는가"의 기록이다. **고치지 않고 남긴다.** 그 믿음이 어떻게 빗나갔는지는 문서 맨 끝 "🔄 반전"에서 밝힌다.

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-25 | - | 최초 작성 |
| 2026-06-26 | 전반 | 근본 원인 분석 추가, 수정 방안 구체화, eval 이중 가명화 방지 로직 추가 |
| 2026-06-29 | 전반 | 워드클라우드 정상화 중심 재정비, 외부 eval 반입 사전 검증 추가, 불필요한 기능 제거 |
| 2026-06-29 | 2.1, 3.1, 3.5, 5.1, 5.2 | **auto-generated evaluator_id 이중 가명화 원인 추가 발견** — _extract_rows_from_chunk()에서 이미 가명화된 emp_id로 eval-{emp_id}-date 생성 후 재가명화되는 루트 추가, 2중 방어 로직 확장 |

## 1. 배경 및 목적

- **워드클라우드가 기존에 잘 동작하던 기능이 이중 가명화로 인해 비정상 상태**
- **외부 eval 데이터 재반입 시 evaluator_id 이중 가명화 문제 발견**
  - 메타데이터 생성 배치 처리 시 이미 가명(`평가자_XXXXXX`)인 `evaluator_id`가 재가명화되어 `평가자_YYYYYY` 생성
  - 결과적으로 실제 사번(숫자) 복원 불가 → 워드클라우드/그룹분석 결과 오류
- **해결 방법**: 이중 가명화만 막으면 매핑 체인이 유지되고, 기존 워드클라우드 코드(`get_real_id()`)가 정상 복원 → 기능 그대로 복구됨
- **전제**: 기존 DB 및 매핑 파일은 사용자가 전체 초기화 예정이므로, 마이그레이션/정리 스크립트 불필요

## 2. 현재 시스템 분석

### 2.1 전체 데이터 파이프라인

```
┌─ 1️⃣ 메타데이터 생성/배치 저장 ──────────────────────────────────────────┐
│  CSV(실제 사번) → process_batch() → _extract_rows_from_chunk()         │
│  → evaluator_id 가명화: "98765" → "평가자_ABC123"                       │
│  → pseudonym_mappings.enc: "98765" → "평가자_ABC123" 저장              │
│  → 가명화된 데이터 DB 저장 (evaluator_id = "평가자_ABC123")             │
│  → 실패 시: failed/YYYYMMDD/emp_XXX/data.csv에 가명 상태 그대로 저장    │
├─────────────────────────────────────────────────────────────────────────┤
│ 2️⃣ 판정 패킷 추출 (배치 종료 후)                                        │
│  build_judgment_packet(batch_id)                                        │
│  → _load_pseudonymized_evals(): DB에서 가명 그대로 로드 (원복 안 함)     │
│  → select_hard_sentences(): 긍↔부 경계·저마진 문장만 추출               │
│  → plans/_datasets/kote_finetune/eval/judgment/<라벨>/<batch_id>.json  │
├─────────────────────────────────────────────────────────────────────────┤
│ 3️⃣ 재반입/재시도 경로 (❌ 버그: 이중 가명화!)                            │
│  관리자 "실패 직원 재처리" → retry_failed_employees()                    │
│  → failed/.../data.csv 읽음 (evaluator_id = "평가자_ABC123" 이미 가명!) │
│  → process_batch() 재호출 → _extract_rows_from_chunk()                  │
│  → forced_pseudo에 'evaluator_id' 포함 → get_pseudonym("평가자_ABC123") |
│  → **실명으로 착각 → 새 가명 "평가자_XYZ789" 생성 (이중 가명화!)**        │
│  → 매핑 체인 끊김: 98765↔평가자_ABC123 + 평가자_ABC123↔평가자_XYZ789    │
│  → get_real_id("평가자_XYZ789") → 원본 98765 복원 불가                  │
│  → **워드클라우드/그룹분석 실패**                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 관련 파일/함수 (grep/read 실측 완료)

| 파일 | 함수/위치 | 역할 |
|------|-----------|------|
| `batch_processor.py:210` | `_extract_rows_from_chunk()` | CSV 청크 → 평가 데이터 가명화 **(수정 완료, 검증 필요)** |
| `batch_processor.py:576` | `forced_pseudo` 선언 | 강제 가명화 필드 목록 (evaluator_id 포함) |
| `batch_processor.py:521` | `process_batch()` | 배치 처리 메인 함수 **(외부 CSV 사전 검증 추가 필요)** |
| `batch_service.py:499` | `retry_failed_employees()` | 실패 직원 재처리 → 재반입 경로 |
| `pseudonym_manager.py:153` | `get_pseudonym(real_id)` | 가명 생성/조회 **(eval 가명 감지 로그 추가 완료)** |
| `pseudonym_manager.py:172` | `get_real_id(pseudonym)` | 실명 복원 |
| `judgment_packet_service.py:190` | `_load_pseudonymized_evals()` | 가명 그대로 DB 로드 (정상) |
| `judgment_packet_service.py:223` | `build_judgment_packet()` | 판정 패킷 생성 (정상) |

### 2.3 워드클라우드 복원 가능성 검증

| 경로 | 기존 코드 | 이중 가명화 제거 시 |
|------|-----------|-------------------|
| `wordcloud_data_service.py:_load_evaluations()` | `get_real_id()`로 직원 정보 복원 중 | 매핑 체인 유지 → `evaluator_id` 실사번 정상 복원 |
| `wordcloud_service.py:regenerate_wordcloud()` | 메타데이터 JSON → 평가 데이터 사용 | 동일, 매핑만 정상이면 복원 가능 |
| **결론** | **워드클라우드 코드 자체는 정상** — 이중 가명화만 복구되면 기능 그대로 복구 |

## 3. 구현 상세

### 3.1 `batch_processor.py` — `_extract_rows_from_chunk()` 이중 가명화 방지

**상태**: `batch_processor.py:260-271` 라인에 이미 구현 완료. 검증만 필요.

**파일**: `src/services/batch_processor.py` → `_extract_rows_from_chunk()` (260-271라인)

```python
# 공유 리스트 변조 방지를 위해 사본으로 작업
_pseudo_fields = list(pseudonym_fields)
if _pseudo_mgr and 'evaluator_id' in evaluation:
    evaluator_id = evaluation['evaluator_id']
    if isinstance(evaluator_id, str) and evaluator_id.startswith('평가자_'):
        if 'evaluator_id' in _pseudo_fields:
            _pseudo_fields.remove('evaluator_id')
        logger.info("eval_pseudo_detected skip_pseudonymization evaluator_id=%s",
                   evaluator_id, extra={'request_id': '', 'stage': 'PSEUDO_EVAL_DETECT'})
```

### 3.2 `batch_processor.py` — `process_batch()` 외부 CSV 사전 검증 (신규)

**파일**: `src/services/batch_processor.py` → `process_batch()` 진입부 (forced_pseudo 확정 직후, ~600라인 부근)

```python
def _detect_and_exclude_pseudo_evaluator_id(csv_path, pseudonym_fields):
    """
    외부 CSV(eval 재반입 등)의 evaluator_id 컬럼이 이미 가명(평가자_XXXXXX)
    패턴이면 pseudonym_fields에서 자동 제외하여 재가명화를 원천 차단한다.
    """
    try:
        import pandas as pd
        df_sample = pd.read_csv(csv_path, nrows=5)
        if 'evaluator_id' in df_sample.columns:
            sample_vals = df_sample['evaluator_id'].dropna().astype(str).tolist()
            if sample_vals and all(v.startswith('평가자_') for v in sample_vals[:3]):
                pseudonym_fields = [f for f in pseudonym_fields if f != 'evaluator_id']
                logger.info("external_eval_detected exclude_evaluator_id_from_pseudo",
                           extra={'request_id': '', 'stage': 'PSEUDO_EVAL_DETECT'})
    except Exception:
        pass  # 샘플링 실패 시 기본 로직 유지
    return pseudonym_fields
```

### 3.3 `pseudonym_manager.py` 로깅 확장 (eval 가명 방어)

**상태**: `pseudonym_manager.py:158-162` 라인에 이미 구현 완료. 검증만 필요.

| 함수 | 로그 포인트 | 레벨 | 메시지 |
|------|-------------|------|--------|
| `get_pseudonym(real_id)` | 진입 + 이미 가명 감지 | WARNING | `[STAGE:PSEUDO_GET] eval_pseudo_as_real_input real_id={real_id}` |
| `get_real_id(pseudonym)` | 진입 + 매핑 발견 | INFO/DEBUG | `[STAGE:PSEUDO_REAL] found=True/False real_id={real_id}` |

### 3.4 새 스테이지 `PSEUDO_EVAL_DETECT`

| 로그 포인트 | 레벨 | 메시지 |
|-------------|------|--------|
| eval 가명 감지 (batch_processor) | INFO | `[STAGE:PSEUDO_EVAL_DETECT] skip_pseudonymization evaluator_id={id}` |
| 외부 eval 반입 감지 (batch_processor) | INFO | `[STAGE:PSEUDO_EVAL_DETECT] external_eval_detected exclude_evaluator_id_from_pseudo` |
| eval 가명이 실명으로 전달됨 (pseudonym_manager) | WARNING | `[STAGE:PSEUDO_GET] eval_pseudo_as_real_input real_id={id}` |

## 4. 영향도 분석

### 4.1 변경 파일 목록

| 파일 | 변경 내용 | 영향 범위 |
|------|-----------|-----------|
| `src/services/batch_processor.py` | `_extract_rows_from_chunk()` 이중 가명화 방지 (이미 구현) + `process_batch()` 외부 CSV 사전 검증 | 재반입/외부반입 경로의 evaluator_id 가명화 스킵 |
| `src/modules/pseudonym_manager.py` | `get_pseudonym()` eval 가명 방어 로그 (이미 구현) | 내부 동작 변경 없음, 로그만 추가 |

### 4.2 영향도

- **기능 변경**: 재반입/외부반입 경로에서 `evaluator_id` 재가명화 방지 → 기존 잘못된 동작 수정
- **워드클라우드 복원**: 별도 코드 수정 불필요 — 매핑 체인 유지로 `get_real_id()` 정상 복원 → 기존 기능 그대로 복구
- **하위 호환성**: 신규 CSV(숫자 사번) → 정상 가명화 (기존 동작 유지)
- **판정 패킷**: 영향 없음 — `_load_pseudonymized_evals()`는 가명 그대로 로드 (정상)
- **성능**: INFO 레벨 로그 I/O 1회 + 샘플 CSV 리드 5행 (1ms 미만)
- **동시성**: `logging` 모듈은 스레드 세이프, 기존 `ThreadPoolExecutor`와 충돌 없음

## 5. 테스트/검증 계획

### 5.1 단위 검증

| # | 시나리오 | 확인 사항 |
|---|----------|-----------|
| 1 | CSV에 `evaluator_id="평가자_ABC123"` 입력 → `_extract_rows_from_chunk()` | 재가명화 안 됨, `PSEUDO_EVAL_DETECT` 로그 출력 |
| 2 | CSV에 `evaluator_id="98765"` (숫자 사번) 입력 | 정상 가명화 `평가자_XXXXXX` 생성 |
| 3 | 외부 CSV(`평가자_` 패턴) 반입 → `process_batch()` | `pseudonym_fields`에서 `evaluator_id` 자동 제외, 가명화 스킵 |
| 4 | `pseudonym_manager.get_pseudonym("평가자_ABC123")` 호출 | WARNING 로그 출력 (이중 가명화 시도 감지) |

### 5.2 통합 검증 (워드클라우드 정상화 중심)

| # | 시나리오 | 확인 사항 |
|---|----------|-----------|
| 1 | 실패 직원 재처리 (retry) → 재반입 | `evaluator_id` 기존 가명 유지, `PSEUDO_EVAL_DETECT` 로그 확인 |
| 2 | `get_real_id("평가자_ABC123")` 호출 | 실제 사번(숫자) 반환 확인 |
| 3 | **워드클라우드 생성 (DB 경로)** | `wordcloud_data_service.py` 경로 → `evaluator_id` 실사번 복원돼 정상 생성 |
| 4 | **워드클라우드 생성 (메타데이터 경로)** | `wordcloud_service.py` 경로 → `evaluator_id` 실사번 복원돼 정상 생성 |
| 5 | 신규 CSV 최초 정상 배치 처리 | 정상 가명화, 워드클라우드 정상 생성 |

## 6. 리스크 및 제약

| 리스크 | 영향 | 대책 |
|--------|------|------|
| `평가자_` 접두사가 실제 사번에 포함될 가능성 | 오탐으로 가명화 누락 | `평가자_`는 PseudonymManager가 생성하는 전용 접두사. 실제 사번에는 있을 수 없음 |
| 기존 `pseudonym_mappings.enc` 오염 (이중 가명화 매핑) | 잘못된 매핑 잔존 | 사용자 계획: 전체 초기화 후 재구축 (이 계획서의 전제 조건) |
| 외부 CSV 샘플링 실패 | 사전 검증 누락 → 기본 로직 유지 | 예외 처리되어 기존 로직 영향 없음 |

## 7. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 계획서 업데이트 (본 문서) | 없음 |
| 2 | `_extract_rows_from_chunk()` 이중 가명화 방지 **기존 구현 검증** | 없음 |
| 3 | `pseudonym_manager.py` eval 가명 방어 로그 **기존 구현 검증** | 없음 |
| 4 | `process_batch()` 외부 CSV 사전 검증 로직 **신규 구현** | 없음 |
| 5 | DB/매핑 파일 전체 초기화 (사용자) | 개발 완료 후 |
| 6 | 검증 — 5장 테스트 계획 전항 실행 | 2, 3, 4 |
| 7 | `_index.md` — 상태 업데이트 | 6 |

---

# 🔄 반전 (2026-06-30) — 위의 진단은 전부 빗나갔다

> 여기부터는 **사실**이다. 위 §1~§7은 전부 **틀린 가설**이었다. 둘을 나란히 둔 이유: 우리가 무엇을, 왜 잘못 짚었는지 잊지 않기 위해서.

## 우리가 믿었던 것 (위 본문)
> "워드클라우드가 안 되는 건 evaluator_id가 **이중 가명화**되어 매핑 체인이 끊겼기 때문이다. 이중 가명화만 막으면 복구된다."

→ 이 전제로 멱등화·`forced_pseudo` 축소·eval 감지 로직·3중 방어까지 만들었다.

## 실제로 참이었던 것 (사용자 터미널 로그가 밝힘)
가명화는 **처음부터 정상**이었다. 로그가 그대로 보여줬다:
```
STAGE:DB_LOAD   row_count=28 eval_count=28      ← 가명 해석·DB 조회 성공
STAGE:DEPLOY_SAVE  filtered_items_empty row_field=evaluation_date__year row_values=['2025']
STAGE:API_ENTRY    deploy_failed
```
- 진짜 실패 지점은 가명화가 아니라 **행 필터**.
- `evaluation_date`가 JSON에 **정수 `2025`**로 저장돼 있었는데(385건 전부 int), `_get_eval_field_value`의 연/월 추출이 `isinstance(raw_val, str)`만 통과시켜 **정수면 `None` 반환** → 행 필터가 전건 탈락 → "제출용 저장" 14명 전원 실패.
- 행 옵션 드롭다운은 DB 컬럼(TEXT `'2025'`)에서 만들어 `row_values=['2025']`를 보냈는데, 필터는 JSON의 int를 읽는 **비대칭**이 결정타였다.

## 실제 해결 (가명화와 무관)
- 신규 `wordcloud_project/utils/date_normalize.py` — `normalize_eval_date()`로 다양한 형식(int 2025, `2025-06-01`, `20250601`, `250105`(YYMMDD), `202506`(YYYYMM))을 표준형으로 정규화.
- **입력**: `metadata_service.py`가 저장 전 정규화(DB 컬럼·JSON blob이 같은 값에서 파생 → 통일).
- **읽기**: `perspective_service._get_eval_field_value`가 추출 전 정규화.
- 검증: 실제 실패 파라미터(`row_values=['2025']`)로 14명 → **14/14 정상**, 형식별 연/월 추출 정상.
- (위 본문의 가명화 변경 = 멱등화·target_employee_id 단일화는 그 자체로 유효한 개선이지만, **이 실패의 원인은 전혀 아니었다.**)

## 왜 빗나갔나 — 잊지 말 것 6가지
1. **증상이 아니라 추정 원인에서 출발했다.** 실제 에러 메시지·로그·실패 입력 없이 인과부터 단정.
2. **"코드가 존재함"을 "코드가 원인임"으로 승격.** §2.2 "실측 완료"는 함수 존재 확인일 뿐 원인 증거가 아니었다.
3. **재현 없이 수정부터 구현.** "이미 구현 완료, 검증만 필요" — 미확정 가설에 코드를 먼저 맞췄다.
4. **버그(A)를 기능개선(B)으로 오분류** → 버그 템플릿의 *재현·근거* 규율을 우회.
5. **정교함을 증거로 오인.** ASCII 다이어그램·3중 방어가 "검증된 듯한" 착시를 줬다.
6. **재검토가 전제를 의심하지 않고 같은 가설을 강화**(06-29 "추가 발견").

→ 재발 방지 지침: `.clinerules/core/00-core/03-plan-mode/type-a-bugfix.md` §원인 확정 게이트, `03.plan-mode.md`.
