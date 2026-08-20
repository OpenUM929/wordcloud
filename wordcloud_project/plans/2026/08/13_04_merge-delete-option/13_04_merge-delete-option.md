# 계획서 — 배치 병합 시 원본 배치 삭제 여부 선택

> 상태: Pre-Done | 작성일: 2026-08-13
> 작업 유형: B (기능 개선/신규 기능)
> 선행: [13_01_batch-merge](../13_01_batch-merge/13_01_batch-merge.md) (병합 기능 본체 — 이 계획은 그 위에 옵션 1개를 얹는다)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-13 | 전체 | 최초 작성 |
| 2026-08-20 | §3, §5 | 착수 전 코드 재검증 — §2의 모든 라인 참조가 현재 코드와 정확히 일치(`batch_merge_service.py:251~257`·`259~266`, `perspective_routes.py` 병합/삭제 라우트, `admin_batch_management.html:109`·`168` 모두 그대로)해 계획 그대로 구현. §3.1·§3.2 전량 적용 완료. T1~T4는 임시 sqlite로 스크립트 실행해 4건 전부 통과(pytest, 서버 미기동·DL-12 준수). 브라우저 2단계 실동작 확인만 PND |

---

## 요구사항 원자화

> 절차: `기대` 열은 코드 실측으로 채운 예측 답이다. 착수 전 사용자가 O/X 로 교정한다. `작업 후 답`은 구현·검증 후 근거와 함께 채운다.

| # | 원자 질문 | 기대 (사용자 확인) | 작업 후 답 (근거) |
|---|-----------|--------------------|------------------|
| 1.1 | 지금도 병합하면 원본 배치의 **평가 데이터**가 남아있는가? | N — `batch_merge_service.py:196-199` 가 `UPDATE evaluations SET batch_id=? WHERE batch_id=?` 로 재라벨하므로 원본 배치 아래에는 평가가 0건 남는다. 남는 건 `batch_work_orders` 의 껍데기 행(`status='merged'`)과 물리 폴더뿐 | |
| 1.2 | 사용자가 말한 "삭제 여부 선택"은 이 남은 껍데기(작업서 행 + 물리 폴더)를 지울지 말지인가? | Y — 사용자 확정: "병합 확인창에서 '원본 유지 vs 원본 삭제'를 매번 선택하게 함" | |
| 1.3 | "원본 삭제"를 선택하면 병합 이력(`batch_merges` 테이블, 되돌리기 근거)도 함께 지우는가? | N — 이력 테이블은 감사 추적 목적이라 삭제 여부와 무관하게 항상 남긴다. 사용자가 지우는 건 목록에 보이던 "원본 배치" 자체이지, 병합했다는 기록이 아니다 | |
| 1.4 | 이미 존재하는 `DELETE /api/perspective/batch/<batch_id>`(개별 배치 삭제)를 재사용할 수 있는가? | 부분적으로만 — 로직(작업서 삭제+물리 폴더 rmtree)은 동일하지만, 병합 서비스는 **하나의 트랜잭션 커넥션**을 쓰므로(`batch_merge_service.py:38-43`) 별도 커넥션을 여는 기존 라우트 함수를 그대로 호출하면 SQLITE_BUSY 위험이 있다(13_01 계획서 §2.4와 동일 이유). 같은 커넥션 안에서 동등한 SQL만 재현한다 | |
| 1.5 | 기본값(체크박스 초기 상태)은 유지·삭제 중 무엇인가? | **원본 유지**(안전 기본값, 비가역 삭제를 실수로 트리거하지 않도록) | |

---

## 1. 배경 및 목적

병합(13_01)은 이미 "복사가 아니라 이동"이라 원본 배치에는 평가가 남지 않는다. 다만 작업서 레지스트리 행(`status='merged'`)과 물리 폴더(`processed_data/batch/<원본ID>/`)는 그대로 남아 디스크·DB에 흔적이 계속 쌓인다. 사용자는 병합할 때마다 이 흔적을 지울지 남길지 직접 고를 수 있어야 한다고 요청했다.

---

## 2. 현재 시스템 분석 (실측)

| 항목 | 위치 | 내용 |
|------|------|------|
| 병합 후 원본 처리 | `batch_merge_service.py:251-257` | `UPDATE batch_work_orders SET status='merged' ... WHERE batch_id IN (...)` — 행은 지우지 않고 상태만 바꾼다 |
| 목록 숨김 | `perspective_service.py` `_load_batch_list()` | `status='merged'` 배치를 목록에서 제외(13_01 §4.2) |
| 개별 배치 완전 삭제(참고용 기존 기능) | `perspective_routes.py:1106-1140` `DELETE /api/perspective/batch/<batch_id>` | ①`remove_batch_from_all` (evaluations DELETE, 이미 0건이라 no-op)→②`delete_work_order`(작업서 행 DELETE)→③물리 폴더 `shutil.rmtree`→④`log_action` |
| 병합 이력 | `batch_merges` 테이블(스키마 v9) | `merged_batch_id`/`source_batch_id`/`moved_count`/`source_status` 기록 — 삭제 여부와 무관하게 항상 남는 감사 로그 |

병합 서비스는 자체 SQLite 커넥션(`_get_conn()`)으로 단일 트랜잭션을 열어두므로, 이 트랜잭션 도중에 `batch_work_order_service.delete_work_order()`(별도 커넥션, 즉시 commit)를 호출하면 잠금 경합 위험이 있다(13_01 §2.4 동일 문제). 따라서 "삭제" 로직은 기존 라우트 함수를 호출하지 않고 같은 트랜잭션 안에서 동등 SQL로 재현한다.

---

## 3. 구현 상세

### 3.1 백엔드

**`src/services/batch_merge_service.py` `merge_batches()` 시그니처 확장**

```python
def merge_batches(source_batch_ids, display_name='', new_batch_id=None,
                   processed_data_dir=None, delete_sources=False):
```

- 8단계(원본 작업서 처리, 현재 `:251-257`)를 분기:
  - `delete_sources=False`(기본, 원본 유지): 기존 그대로 `UPDATE ... SET status='merged'`.
  - `delete_sources=True`(원본 삭제): 같은 커넥션으로 `DELETE FROM batch_work_orders WHERE batch_id IN (...)` — `batch_work_order_items`는 이미 4단계에서 원본 행이 DELETE된 상태(13_01 §4.2 순서 4)라 추가 조치 불필요.
- `batch_merges` 기록(9단계, `:259-266`)은 **분기와 무관하게 항상 실행** — 삭제해도 병합했다는 사실 자체는 감사 로그에 남아야 한다(원자 질문 1.3). `source_status`에는 삭제 여부와 상관없이 병합 직전 실제 status를 기록(기존 로직 그대로, 삭제 시에도 이 값 자체는 삭제 *전에* 읽으므로 영향 없음).
- 물리 폴더: commit 이후(트랜잭션 밖) `delete_sources=True`인 원본 배치 폴더를 `shutil.rmtree(os.path.join(processed_data_dir, 'batch', bid), ignore_errors=True)` — 기존 `api_batch_delete`의 방식(`:1131-1134`, 예외 무시)과 동일하게 실패해도 API 전체는 성공으로 취급.
- 반환값에 `deleted_sources: bool` 추가(프론트 결과 메시지용).

**`src/routes/perspective_routes.py` `api_batch_merge()`(`:1071`)**

```python
delete_sources = bool(data.get('delete_sources', False))
result = merge_batches(source_batch_ids, display_name=display_name, delete_sources=delete_sources)
```

`log_action('batch_merge', {...})` 페이로드에 `delete_sources` 추가(감사 로그에서 어떤 선택이었는지 확인 가능하도록).

### 3.2 프론트엔드

`web/templates/admin_batch_management.html` `mergeSelectedBatches()`(`:109-166`)

- 「선택 배치 병합」 버튼 옆에 체크박스 추가: `<label><input type="checkbox" id="mergeDeleteSourcesCheck"> 병합 후 원본 배치 완전 삭제(되돌릴 수 없음)</label>` — 기본 unchecked(원자 질문 1.5).
- `mergeSelectedBatches()`에서 이 값을 읽어:
  - 확인 대화상자(`:130-137`) 문구를 분기 — 체크 시 기존 "평가 데이터는 삭제되지 않고 소속만 바뀝니다." 뒤에 "⚠️ 원본 배치 ○개는 완전히 삭제되며 되돌릴 수 없습니다." 를 추가하고, `confirm()` 통과 후 **2차 확인**(`confirm('정말 원본을 삭제할까요?')`)을 한 번 더 요구한다 — 기존 `deleteBatch()`(`:168-170`)의 2단계 확인 패턴과 동일 수준의 안전장치.
  - `fetch` body에 `delete_sources: checked` 추가.
  - 성공 알림 문구에 `d.deleted_sources`면 "원본 배치 삭제 완료" 를 덧붙인다.
- 병합 완료 후 체크박스는 unchecked로 리셋(다음 병합에서 실수로 이어지지 않도록 — 원자 질문 1.5와 동일 원칙).

---

## 4. 영향도 분석

| 파일 | 변경 | 성격 |
|------|------|------|
| `src/services/batch_merge_service.py` | `merge_batches()`에 `delete_sources` 파라미터 + 분기 | 수정 |
| `src/routes/perspective_routes.py` | `api_batch_merge()` 파라미터 전달 + 로그 필드 추가 | 수정 |
| `web/templates/admin_batch_management.html` | 체크박스 1개 + 확인 대화상자 분기 + body 필드 추가 | 수정 |

- `batch_merges`(병합 이력), `_load_batch_list()`(목록 필터) 등 13_01의 다른 소비처는 무변경 — 이 계획은 8단계(원본 처리) 분기 1곳만 건드린다.
- 도메인 잠금: DL-9(원데이터 취급) 해당 없음(신규 파일 기록 없음). DL-12(서버 무단 기동) 준수 — 검증은 §5의 독립 스크립트로.

---

## 5. 테스트/검증 계획

`test/` 폴더: `plans/2026/08/13_04_merge-delete-option/test/`

| # | 시나리오 | 방법 | 기대 |
|---|----------|------|------|
| T1 | `delete_sources=False`(기본) — 회귀 확인 | 임시 DB에서 병합 후 원본 `batch_work_orders` 조회 | 행 존재, `status='merged'`(13_01 T2·T6과 동일 결과, 회귀 없음) — **PASS** |
| T2 | `delete_sources=True` | 동일 조건, `delete_sources=True`로 병합 | 원본 `batch_work_orders` 행 0건, `batch_merges`에는 원본 기록 그대로 존재 — **PASS** |
| T3 | 물리 폴더 삭제 | 원본 배치 폴더에 더미 파일 생성 후 `delete_sources=True` 병합 | 폴더 자체가 사라짐(`os.path.isdir` False) — **PASS** |
| T4 | 삭제 실패해도 API 전체 성공 | `shutil.rmtree`를 monkeypatch해 `ignore_errors=True`가 실제로 전달되는지 검증(전달 안 되면 예외) | `merge_batches()` 예외 없이 `success: true`, `deleted_sources: true` — **PASS** |

2026-08-20 실행: `python -m pytest plans/2026/08/13_04_merge-delete-option/test/` → 4 passed (`test/test_delete_option.py`, `test/conftest.py`는 13_01 conftest 복제).

**실동작 검증(사용자 승인 후, 사용자가 서버 기동)**

1. `/admin/batch-management`에서 체크박스 미체크 상태로 병합 → 원본이 목록엔 안 보이지만(status='merged') DB엔 행이 남아있는 기존 동작과 동일한지 확인.
2. 체크박스 체크 후 병합 → 2단계 확인창 통과 → 완료 후 원본 배치의 물리 폴더가 실제로 사라졌는지 파일탐색기로 확인.

위 2항 통과 전에는 상태를 `Done`으로 올리지 않는다(DL-10).

---

## 6. 리스크 및 제약

| # | 리스크 | 영향 | 대응 |
|---|--------|------|------|
| R-1 | 원본 폴더에 병합 후에도 필요한 캐시(예: 과거 렌더링된 워드클라우드 PNG)가 있을 수 있음 | 삭제 시 재생성 필요한 리소스 유실 | 기존 「배치 완전 삭제」 기능(`api_batch_delete`)과 동일한 리스크이며 이미 운영 중인 정책이므로 이번 계획에서 새로 발생하는 리스크는 아니다. UI 문구에 "되돌릴 수 없음" 명시로 대응 |
| R-2 | 체크 상태가 실수로 유지된 채 다음 병합에 재사용 | 원치 않는 원본 삭제 | §3.2 — 병합 완료 후 체크박스 자동 리셋 |
| R-3 | 트랜잭션 내 DELETE와 커밋 후 폴더 삭제 사이에 실패 시 부분 상태(DB엔 삭제, 폴더는 남음 또는 그 반대) | 흔적 불일치 | DB 삭제는 트랜잭션 커밋으로 원자적. 폴더 삭제는 커밋 후 별도 단계라 실패해도 DB는 이미 정상 완료 상태 — 폴더만 수동 정리하면 됨(기존 `api_batch_delete`와 동일한 한계, 신규 리스크 아님) |

**제약**

- 이미 `status='merged'`로 남아있는 **과거** 원본 배치를 나중에 일괄 삭제하는 기능은 범위 밖(이번 계획은 "병합 시점"의 선택만 다룬다).
