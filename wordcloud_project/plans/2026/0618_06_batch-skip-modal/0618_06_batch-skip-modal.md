# 계획서 — 배치 중복 스킵 안내 모달

> 상태: DN(구현 완료, 2026-06-18) | 작성일: 2026-06-18
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 본 세션에서 배치 이력 출력을 작업서(batch_work_orders) 기준으로 전환 완료 (적용됨) · 관련 [[0611_01_batch-db-unification]]

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-18 | (신규) | 최초 작성 — 배치 시 중복(미저장) 평가 목록 + 증거값 모달 |
| 2026-06-18 | §5 전체 | 구현 완료 — `upsert` 반환 `(inserted, skipped)`, `batch_processor` 집계(`SKIP_DETAIL_CAP=10`), `_ensure_batch_summary` 임베드, `get_skipped_evaluations`+`GET /api/batch/skipped/<batch_id>`, 완료 화면 버튼 + `skippedModal` |

---

## 1. 배경 및 목적

배치 메타데이터 생성 시, 동일 직원·평가가 이미 DB에 있으면 평가 INSERT가 중복으로 거부되어 **신규 저장 0건**이 될 수 있다. 현재는 이 스킵이 `except sqlite3.IntegrityError: pass`로 **조용히** 처리되고, 작업서에는 여전히 "성공"으로 집계되어, 사용자가 *"배치를 했는데 데이터가 안 늘었다(없다)"*고 혼란을 겪는다.

**목적**: 배치 완료 시 **저장되지 않은(중복) 평가 목록**을, **이미 존재하는 기존 데이터와 동일하다는 증거값(중복 판정 키)** 과 함께 모달로 안내하여 혼란을 제거한다.

> 참고: 평가 1년 1회(`target_employee_id` 기준 독립) 도메인 규칙상, 중복 판정 키 `(employee_id, evaluator_id, evaluation_date)` 는 자연 유일키가 되어 **정당한 평가가 오삭제될 위험은 없다**. 따라서 저장/삭제 모델은 변경하지 않으며, 본 작업은 **가시성(알림) 추가**에 한정한다.

## 2. 요구사항

1. 배치 완료 시 **스킵(미저장) 평가 총 건수**를 표시한다.
2. "자세히 보기" 시, 스킵된 평가 목록을 **모달**로 보여준다.
3. 각 행에 **증거값**을 함께 표시한다: 스킵된 평가의 키(직원/평가자/평가일자/문서) + **일치하는 기존 데이터의 출처(batch_id·등록일)**.
4. 대규모 재import 대비, 상세 목록은 **상위 10건만** 저장/표시하고(`SKIP_DETAIL_CAP = 10`), 총 건수는 전수 집계한다.
5. 표시 데이터는 모두 가명 ID·가명 텍스트(관리자 화면) — 원천 식별자 비노출.

## 3. 현재 시스템 분석 (코드 실측)

- **`upsert(employee_id, metadata, evaluations, batch_id)`** — `src/services/user_data_manager.py:55`
  - 평가를 1건씩 루프 INSERT. 반환값 `inserted: int` (`:97`).
  - 중복 시 `:94` `except sqlite3.IntegrityError: pass` — 스킵 정보 미수집.
  - 지문 `_fingerprint(ev)` (`:35`) = `md5(evaluator_id, evaluation_date, document[:100])`. fp는 `:79`에서 계산.
- **중복 방지 인덱스** `idx_ev_fp ON evaluations (employee_id, fingerprint)` — `src/services/deploy_session_service.py:171` (스키마 v3, "no cross-batch duplicates").
- **유일 호출처**: `src/services/batch_processor.py:869` — `as_completed` 메인 스레드 루프(`:858~:909`) 내. `_meta`, `_eid` 보유, 현재 반환값 미사용(`_persisted=True`만 설정).
- **완료 상태 정리**: `batch_processor.py:983~:994` 에서 `batch_processing_state[...]` 설정. 최종 반환 dict `:1029`.
- **배치 요약 파일**: `_ensure_batch_summary(batch_dir, batch_processing_state, display_name='')` — `batch_processor.py:492`. `batch/<batch_id>/tmeta/batch_summary.json` 생성. 매 호출 시 `summary` dict 신규 구성 후 write.
- **SSE**: `get_processing_events()` → `create_sse_response(batch_processing_state)` — `src/services/batch_service.py:433`. **상태 dict 전체를 스트리밍**하므로, 정수 `skipped_count`만 추가하면 자동 전달됨(대용량 리스트는 넣지 않음).
- **프론트 완료 처리**: `web/static/js/metadata_batch.js:823~:861` — `data.completed` 시 결과 테이블 렌더. `data.profanity_employees`, `data.failed_employees` 리스트를 동일 패턴으로 이미 표시 중. 모달 인프라 존재(`resumeModal`, `mappingManagerModal`).
- **라우트**: `batch_bp` (`url_prefix='/api/batch'`) — `src/routes/batch_routes.py`. 기존 `/sample`, `/failed-list` 등과 동일 패턴으로 신규 GET 추가 가능.

## 4. 구현 상세

### 4.1 백엔드

- **`user_data_manager.upsert()` 반환 확장** (`user_data_manager.py:55`)
  - `IntegrityError` 분기에서 기존 일치 행을 조회하여 증거 수집:
    ```python
    except sqlite3.IntegrityError:
        existing = conn.execute(
            "SELECT batch_id, created_at FROM evaluations "
            "WHERE employee_id=? AND fingerprint=?", (employee_id, fp)
        ).fetchone()
        skipped.append({
            'employee_id': employee_id,
            'evaluator_id': ev_copy.get('evaluator_id', ''),
            'evaluation_date': ev_copy.get('evaluation_date', ''),
            'document': str(ev_copy.get('evaluation_document',
                            ev_copy.get('content', '')))[:120],
            'fingerprint': fp,
            'matched_batch_id': existing['batch_id'] if existing else '',
            'matched_created_at': existing['created_at'] if existing else '',
        })
    ```
  - 반환을 `inserted` → **`(inserted, skipped)`** 로 변경. (호출처 1곳뿐)
- **`batch_processor` 집계** (`batch_processor.py:869` 루프)
  - 모듈 상수 `SKIP_DETAIL_CAP = 10` 추가.
  - 루프 진입 전 `_skip_total = 0`, `_skip_detail = []` 초기화.
  - 호출부 `_inserted, _skip = upsert(_eid, _meta, _meta.get('evaluations', []), batch_id)`.
    - `_skip_total += len(_skip)`; `for s in _skip: if len(_skip_detail) < SKIP_DETAIL_CAP: _skip_detail.append(s)`.
  - 완료 정리부(`:990` 부근)에 `batch_processing_state['skipped_count'] = _skip_total` 설정(→ SSE 자동 전달).
  - `_ensure_batch_summary(...)` 호출 시 상세 목록 전달.
- **`_ensure_batch_summary` 확장** (`batch_processor.py:492`)
  - 시그니처에 `skipped_count=0, skipped_detail=None` 추가.
  - `summary['batch_info']['skipped_count'] = skipped_count`,
    `summary['skipped_evaluations'] = skipped_detail or []` 추가.
- **신규 조회 함수** `get_skipped_evaluations(batch_id)` — `batch_service.py` (신규)
  - `PROCESSED_DATA_DIR_PATH/batch/<batch_id>/tmeta/batch_summary.json` 로드.
  - `{'success': True, 'skipped_count': N, 'skipped': [...]}` 반환. 파일/키 없으면 빈 목록.
- **신규 라우트** `GET /api/batch/skipped/<batch_id>` — `batch_routes.py` (신규)
  - `get_skipped_evaluations(batch_id)` 위임. 모달 오픈 시 on-demand 호출.

### 4.2 프론트엔드 (`metadata_batch.js`, 배치 템플릿)

- 완료 핸들러(`:823~`)의 결과 테이블에, `data.skipped_count > 0` 이면 안내 줄 + **"중복 N건 · 자세히 보기"** 버튼 추가.
- 버튼 클릭 → `fetch('/api/batch/skipped/' + batchId)` → 모달에 표 렌더:

  | 스킵된 평가 | 기존 등록 데이터(증거) |
  |---|---|
  | 직원·평가자·평가일자·문서(앞 120자) | `matched_batch_id` (등록 `matched_created_at`) · 키 일치 |

- 모달은 기존 `resumeModal` 패턴 재사용(신규 `skippedModal` div + open/close 함수). `escapeHtml` 적용.
- (선택, 후속) `perspective_test.html` 배치 이력 행에도 동일 조회로 "중복 보기" 노출 — 본 계획 범위 외, 별도 항목.

## 5. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `upsert()` 반환 `(inserted, skipped)` 로 변경 + 증거 조회 | - |
| 2 | `batch_processor` 집계(`SKIP_DETAIL_CAP=10`) + 상태/요약 반영 | 1 |
| 3 | `_ensure_batch_summary` 에 skipped 임베드 | 2 |
| 4 | `get_skipped_evaluations()` + `GET /api/batch/skipped/<batch_id>` | 3 |
| 5 | 완료 화면 버튼 + `skippedModal` 렌더 | 4 |
| 6 | 검증(§7) | 5 |

## 6. 영향도 분석

- **변경 파일**
  - `src/services/user_data_manager.py` — `upsert` 반환 시그니처(호출처 1곳: `batch_processor.py:869`).
  - `src/services/batch_processor.py` — 집계 로직, `_ensure_batch_summary` 시그니처.
  - `src/services/batch_service.py` — `get_skipped_evaluations` 신규.
  - `src/routes/batch_routes.py` — `/skipped/<batch_id>` 신규.
  - `web/static/js/metadata_batch.js` (+ 배치 템플릿) — 버튼/모달.
- **영향 범위**
  - `upsert` 반환 변경: 호출처가 1곳뿐이라 국소적. (grep 확인: gallery `upsert_entry`는 무관한 별개 함수)
  - 이어서 처리(Resume)도 동일 `process_batch` Stage-3 루프를 거치므로 자동 적용됨.
  - `batch_summary.json` 스키마에 키 **추가만**(기존 키 불변) → 이력/명칭 기능 영향 없음.
  - SSE 페이로드: 정수 1개 추가뿐(상세 리스트는 미포함) → 대역폭 영향 미미.
- **롤백**: 각 파일은 독립적 추가/확장이라 역순 되돌림 가능. `upsert` 반환만 `(inserted, [])` 로 되돌리면 즉시 무력화.

## 7. 테스트/검증 계획

1. **신규 데이터 배치**: 스킵 0건 → `skipped_count=0`, 버튼 미표시.
2. **동일 데이터 재처리**: 전부 중복 → `skipped_count=평가수`, 모달에 상위 10건 + "총 N건 중 10건" 표기, 각 행의 `matched_batch_id`가 최초 저장 배치와 일치하는지 확인.
3. **부분 중복**: 일부 신규 + 일부 중복 → `inserted`와 `skipped_count` 합이 제출 평가 수와 일치.
4. **증거값 정확성**: 모달의 (직원/평가자/평가일자)가 기존 행 키와 동일함을 DB 직접 조회로 대조.
5. **상한 동작**: 스킵 50건일 때 상세 정확히 10건 저장·표시, 총계 50.
6. 검증 코드/결과는 본 폴더 `test/`, `result/` 에 보관(규칙 §10).

## 8. 리스크 및 제약

- 상세는 상위 10건만 보존 → 11건째 이후 개별 확인 불가(총계는 정확). 도메인상 "재처리 여부 인지"가 목적이므로 10건으로 충분.
- `matched_*` 증거는 "현재 그 지문을 소유한 행" 기준 — 이후 소유 배치가 삭제되면 과거 요약의 증거 batch_id는 과거 시점 값(요약은 스냅샷)임에 유의.
- 저장/삭제 모델·중복 인덱스는 **변경하지 않음**(도메인 유일키 보장으로 오삭제 위험 없음). 본 작업은 알림 한정.
- `document[:120]` 미리보기는 표시용일 뿐, 중복 판정은 기존 키(`document[:100]` 포함 지문) 그대로.

---

> 승인 대기: 사용자가 "수행" 요청 시 §5 순서대로 구현한다.
