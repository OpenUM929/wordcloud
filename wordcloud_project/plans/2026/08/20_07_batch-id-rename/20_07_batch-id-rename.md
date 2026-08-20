# 계획서 — 배치 관리 화면에서 배치 이름 변경 기능 추가(한글 입력 차단)

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: B
> 선행: (없음)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 |
| 2026-08-20(3차) | §2, §3, §6, §7 | **구현 완료(Pre-Done).** 착수 시 실측으로 §2의 미확인 항목 해소 — `_load_batch_list()`(`perspective_service.py:1695·1710`)는 `display_name`을 **이미 포함**하므로 그룹분석 화면은 손댈 것이 없고, 배치관리 화면만 병합이 필요했다. 구현: ①`batch_manager.validate_display_name()`(순수 함수) 신설 후 공유 라우트 `PATCH /api/perspective/batch/<id>/display-name`에 연결 — 비ASCII(한글 포함)·경로 금지문자(`\ / : * ? " < > |`) 거부, **빈 문자열은 "명칭 해제"로 계속 허용**(기존 동작 유지). ②`batch_manager.read_display_name()` 신설, `GET /api/batch/work-orders` 응답에 `display_name` 병합(LIMIT 20이라 파일 읽기 최대 20회 — 프론트 조인 대안은 채택하지 않음). ③`integrated_batch.js`에 「명칭」 열 + ✏️ 편집(`editWorkOrderDisplayName()`) 추가, 클라이언트 선검증 이중화. **§3.2 대비 변경**: 계획서는 "작업 ID 컬럼을 `display_name || batch_id`로 대체"였으나, 배치관리 화면의 `batch_id`는 「이어서 작업」 조작 키라 감추면 안 되므로 그룹분석 화면과 동일하게 **명칭 열을 신설하고 작업 ID는 유지**했다(정보 손실 방지). 허용 문자 집합(§7 미확정 항목)은 "ASCII 출력 가능 문자 전부 − 경로 금지문자"로 확정 — 계획서 초안의 `^[A-Za-z0-9 _.-]+$`보다 넓다(괄호·쉼표 등 실무 표기 허용, 요구는 "한글 금지"였으므로 과잉 제한을 피함). T1~T4 총 23건 pytest 통과(서버 미기동, Flask test_client, 운영 `processed_data/` 무변경 확인). 브라우저 실동작 검증만 PND |
| 2026-08-20 | §2, §3, §4, §5 | **중대 정정**: "배치 이름 변경" 기능이 이미 코드베이스에 존재함을 확인(`perspective_test.html`의 `editDisplayName()` → `PATCH /api/perspective/batch/<batch_id>/display-name` → `batch_summary.json.batch_info.display_name`). 신규 DB 컬럼·신규 라우트를 만드는 설계를 폐기하고, 기존 필드·기존 엔드포인트를 배치 관리 화면에 연결하는 설계로 전면 수정 |

## 요구사항 원자화

| # | 원자 질문 | 기대(제 이해, 코드 근거) | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | "배치 아이디 변경"은 시스템 내부 식별자(`batch_id`, 예: `batch_20260611_0`) 그 자체를 바꾸는 것인가, 아니면 화면에 보이는 이름(표시용 라벨)만 바꾸는 것인가? | **표시용 라벨을 신설해 바꾸는 쪽을 권장** — `batch_id`는 `wordcloud_project/src/services/batch_work_order_service.py`의 `batch_work_orders.batch_id`(`UNIQUE NOT NULL`, `deploy_session_service.py:98`)일 뿐 아니라, `grep -rln "batch_id" src/services/*.py` 결과 `acquired_handoff.py`·`batch_manager.py`·`batch_merge_service.py`·`batch_processor.py`·`batch_service.py`·`batch_work_order_service.py`·`deploy_session_service.py`·`judgment_packet_service.py`·`perspective_service.py`·`profanity_db_service.py`·`user_data_manager.py`·`wordcloud_data_service.py` **12개 서비스 파일**이 이 값을 키로 참조하고, 물리 폴더명(`processed_data/batch/<batch_id>/`)으로도 쓰인다(`batch_manager.py:40` `os.path.join(processed_data_dir, 'batch', batch_id, ...)`). 이 값 자체를 바꾸면 12개 파일의 참조·물리 폴더·DB FK를 전부 같이 바꿔야 해 범위와 위험이 크게 늘어난다. `batch_work_orders`에는 현재 표시용 라벨 컬럼이 없으므로(스키마 확인, `deploy_session_service.py:96~112`) 신규 컬럼(`display_name`)을 추가해 화면에는 이 라벨을 보여주고 내부 식별은 `batch_id` 그대로 두는 쪽이 안전 | 미착수 |
| 1.2 | "영문 사용을 권장할 경우 한글로 설정 못하게"는 표시용 라벨에도 적용하는가, 아니면 (실제 ID를 바꾸는 경우에 한해) ID 값에만 적용하는가? | 1.1에서 표시용 라벨로 결정된다면 라벨에도 적용 — 사용자가 굳이 언급한 이유가 "폴더명·경로 충돌"을 걱정한 것이라면 표시용 라벨은 물리 경로와 무관해 한글이어도 안전하지만, 사용자가 원문에서 한글 금지를 명시했으므로 **라벨에도 그대로 적용**하는 쪽을 기본안으로 한다 | 미착수 |

## 1. 배경 및 목적

배치 관리 화면(`/metadata/batch`, `integrated_batch.html`)의 작업 이력 목록에는 시스템이 자동 생성한 `batch_id`(예: `batch_20260611_0`)만 표시되고, 이를 사용자가 알아보기 쉬운 이름으로 바꿀 방법이 없다. 이름을 바꿀 수 있게 해 배치를 식별하기 쉽게 한다.

## 2. 현재 시스템 분석

- **현재 화면(배치 관리, `/metadata/batch`)**: `renderWorkOrders(orders)`(`wordcloud_project/web/static/js/integrated_batch.js:1326`)가 `wo.batch_id`를 "작업 ID" 컬럼에 그대로 출력(1353행 `escapeHtml(wo.batch_id)`) — 이름 변경 UI 없음.
- **관련 파일/함수**: `GET /api/batch/work-orders`(`wordcloud_project/src/routes/batch_routes.py:135`) → `get_all_work_orders(limit=20)`(`wordcloud_project/src/services/batch_work_order_service.py:166`) → `SELECT * FROM batch_work_orders`. 스키마(`deploy_session_service.py:96~112`)에 `display_name` 컬럼 없음 — **`batch_work_orders` 테이블 자체에는 표시용 이름을 저장할 곳이 없다.**
- **🔴 이미 존재하는 이름 변경 기능(재확인 완료, 그대로 재사용 가능)**: 그룹분석(`/perspective_test`) 화면의 "배치 이력" 패널에 실제로 동작하는 이름 변경 기능이 있다.
  - 프론트: `editDisplayName(batchId)`(`wordcloud_project/web/templates/perspective_test.html:3501`)가 `prompt()`로 새 이름을 받아 `PATCH /api/perspective/batch/<batchId>/display-name`(3507행)을 호출. 목록 렌더(`loadBatchHistory()`, 3460~3494행)는 `b.display_name || b.batch_id`를 이름 칸에 표시(3484행 `dnDisplay`).
  - 백엔드: `api_batch_update_display_name(batch_id)`(`wordcloud_project/src/routes/perspective_routes.py:1143~1177`)가 `wordcloud_project/processed_data/batch/<batch_id>/tdata/batch_summary.json`을 열어 `batch_info.display_name`에 값을 쓰고 저장한다(1150~1168행). **입력값 검증이 전혀 없다**(1150행 `.strip()`만 — 한글이든 특수문자든 그대로 저장됨).
  - 이 `batch_summary.json.batch_info.display_name` 필드는 `wordcloud_project/src/services/batch_manager.py`의 `get_batch_list()`(18~48행)도 이미 읽고 있다(38~47행) — `/api/batch/list`(`wordcloud_preview.html`이 사용)의 배치 선택 화면에도 이 이름이 반영된다는 뜻.
  - **배치 이력(`/perspective/batches`)의 응답 구조 확인**: `_load_batch_list()`(`perspective_service.py:1649`)가 `display_name`을 포함해 반환하는지는 이번 재조사에서 끝까지 확인하지 않았다 — 착수 시 1649~1720행대를 다시 읽어 `display_name` 필드가 이미 포함되는지, 포함되지 않으면 `batch_summary.json`을 배치별로 읽어 병합해야 하는지 확정 필요(§3.1의 전제 조건).
- **결론**: "표시용 라벨 신설" 자체는 이미 되어 있다. 이번 계획서가 실제로 할 일은 **① 배치 관리 화면의 작업 이력 목록(`batch_work_orders` 기반)이 같은 `batch_id`에 대한 `batch_summary.json`의 `display_name`을 읽어와 보여주게 하고, ② 같은 편집 UI(기존 `editDisplayName` 패턴 재사용)를 배치 관리 화면에도 추가하고, ③ 기존에 없던 한글 차단 검증을 기존 PATCH 라우트에 추가**하는 것으로 범위가 크게 줄어든다.

## 3. 구현 상세

### 3.1 백엔드

- **신규 DB 컬럼 없음** — `batch_summary.json.batch_info.display_name`을 그대로 정본으로 쓴다.
- `GET /api/batch/work-orders`(`batch_routes.py:135~143`) 또는 `get_all_work_orders()`(`batch_work_order_service.py:166~177`)가 반환하는 각 작업서(`batch_id` 보유)에 대해, `wordcloud_project/src/services/batch_manager.py`의 `get_batch_list()`(18~48행)가 이미 하는 방식 그대로 — `processed_data/batch/<batch_id>/tdata/batch_summary.json`을 열어 `display_name`을 읽어 응답에 병합한다. 배치 개수가 많지 않다면(§20_06 조사에서 로컬 28건 확인) 이 방식을 그대로 따르되, 운영 규모에서 파일 I/O 비용이 걱정되면 `get_all_work_orders()` 안에서가 아니라 **프론트엔드가 `/api/batch/list`(이미 `display_name` 포함, `batch_manager.py` 확인됨)를 별도로 호출해 `batch_id` 기준으로 매핑**하는 방식도 대안(백엔드 수정 없이 프론트에서 두 응답을 조인) — 착수 시 두 방식 중 선택.
- **한글 차단 검증 신설(기존 라우트 보강)**: `api_batch_update_display_name(batch_id)`(`perspective_routes.py:1143~1177`)의 1150행 `display_name = (data.get('display_name') or '').strip()` 다음 줄에 정규식 검증 추가 — `^[A-Za-z0-9 _.-]+$` 불일치 시 `{"success": False, "error": "영문/숫자만 입력 가능합니다"}`와 함께 400 반환(정확한 허용 문자 집합은 착수 시 재확인). **이 검증은 배치관리·그룹분석 두 화면이 같은 엔드포인트를 쓰므로 한 번만 고치면 양쪽에 다 적용된다.**
- 신규 라우트(`POST /api/batch/rename` 등) 불필요 — 기존 `PATCH /api/perspective/batch/<batch_id>/display-name`을 배치관리 화면에서도 그대로 호출.

### 3.2 프론트엔드

- `renderWorkOrders()`(`integrated_batch.js:1326`)가 3.1에서 병합된 `display_name`을 받아 "작업 ID" 컬럼에 `display_name || batch_id`로 표시(`perspective_test.html:3484` `dnDisplay` 로직과 동일 패턴 재사용).
- 편집 버튼·인라인 편집은 `perspective_test.html`의 `editDisplayName(batchId)`(3501~3510행대) 로직을 `integrated_batch.js`로 그대로 이식(같은 `PATCH` 엔드포인트를 호출하므로 함수 이식만으로 충분, 신규 설계 불요).
- 클라이언트 측에서도 `input` 이벤트에서 비ASCII 문자를 즉시 걸러내는 보조 필터 추가(서버 검증과 이중화, UX 개선용) — 필터링 시 안내 문구 동반.

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 요구사항 원자화 표 재확인(1.1 라벨 vs 실제 ID) | - |
| 2 | `_load_batch_list()`가 이미 `display_name`을 포함하는지 확인(§2 미확인 사항) — 포함 안 하면 §3.1 병합 방식 확정 | 1 |
| 3 | 기존 `PATCH /api/perspective/batch/<batch_id>/display-name`에 한글 차단 검증 추가 | 1 |
| 4 | 배치 관리 화면에 `display_name` 표시 + 편집 UI 이식(`editDisplayName` 로직 재사용) | 2, 3 |

## 5. 영향도 분석

- **변경 파일**: `wordcloud_project/src/routes/perspective_routes.py`(기존 PATCH 라우트에 검증 추가), `wordcloud_project/src/routes/batch_routes.py` 또는 `wordcloud_project/src/services/batch_work_order_service.py`(§3.1의 두 대안 중 백엔드 병합을 택하면), `wordcloud_project/web/static/js/integrated_batch.js`(표시·편집 UI 이식). **신규 DB 컬럼·신규 라우트 없음** — 최초안 대비 변경 파일 수·위험이 크게 줄었다.
- **영향 범위**: `batch_id` 자체와 12개 서비스 파일·물리 폴더명은 여전히 건드리지 않는다(DL-8 위험 낮음). 기존 PATCH 라우트에 검증을 추가하는 것은 **그룹분석 화면의 기존 이름 변경 기능에도 동시에 적용된다** — 회귀 없는지 그룹분석 화면 쪽도 함께 확인 필요(§6에 추가).

## 6. 테스트/검증 계획

`test/` 폴더: `plans/2026/08/20_07_batch-id-rename/test/` — 2026-08-20 실행 `python -m pytest plans/2026/08/20_07_batch-id-rename/test/` → **23 passed**(서버 미기동).

| # | 시나리오 | 방법 | 결과 |
|---|----------|------|------|
| T1 | 입력 검증 | `validate_display_name()`에 허용값(영문·숫자·기호·빈값)/거부값(한글·이모지·비ASCII 공백·제어문자·경로 금지문자 9종) 파라미터화 | 전건 기대대로 — **PASS** |
| T2 | 명칭 정본 읽기 | 임시 `processed_data`에 `batch_summary.json` 생성 후 `read_display_name()` | 값 반환, 파일/인자 없으면 `''` — **PASS** |
| T3 | 목록 병합 | Flask test_client로 `GET /api/batch/work-orders`(작업서 조회는 monkeypatch) | 명칭 있는 배치는 값, 없으면 `''` — **PASS** |
| T4 | 공유 PATCH 라우트 | 한글 → 400·파일 미기록, 영문 → 200·파일 반영, 공백만 → 200·명칭 해제 | 전건 기대대로 — **PASS**(그룹분석 화면 회귀 확인 겸용) |

**실동작 검증(사용자 승인 후, 사용자가 서버 기동)** — 아래 통과 전에는 `Done`으로 올리지 않는다(DL-10).


- 배치 관리 화면에서 영문/숫자 이름으로 변경 시 정상 저장·화면 반영 확인.
- 한글 입력 시 저장 거부(서버) 및 사용자 안내 확인, 클라이언트 필터링도 함께 확인.
- `display_name` 미설정 상태(기존 작업서)는 기존처럼 `batch_id`가 그대로 표시되는지(하위 호환) 확인.
- **회귀 확인(신규)**: 그룹분석(`/perspective_test`) 화면의 기존 `editDisplayName` 기능이 §3.1의 한글 차단 검증 추가 이후에도 정상(영문 이름 변경 성공, 한글은 거부)인지 확인 — 같은 라우트를 공유하므로 필수.
- `/api/batch/list`(`wordcloud_preview.html`)에서도 같은 `display_name`이 일관되게 보이는지 확인(세 화면이 같은 필드를 공유하게 됨).

## 7. 리스크 및 제약

- 요구사항 원자화 1.1의 확인 없이 "실제 ID 변경"으로 오해하고 착수하면 물리 폴더·12개 파일 참조가 깨질 위험이 매우 큼 — **반드시 사용자 확인 후 착수**.
- 한글 차단 정규식의 정확한 허용 범위(공백, 특수문자)는 아직 확정하지 않음 — 착수 시 UX와 함께 재확인.
- 기존 PATCH 라우트에 검증을 추가하는 것이 그룹분석·배치관리·(간접적으로) `/api/batch/list` 세 화면에 동시 영향을 준다 — 한 곳만 테스트하고 끝내지 않는다.
- **잔여 구멍(사용자 판단 필요, 이번 범위 밖)**: 배치 **병합**(`POST /api/perspective/batches/merge` → `merge_batches(display_name=...)`, 13_01)은 이 PATCH 라우트를 거치지 않으므로 병합 시점에는 여전히 한글 명칭을 만들 수 있다(기본 사용 예시가 "23년 통합"). 규칙을 일관되게 하려면 병합 라우트에도 `validate_display_name()`을 적용해야 하지만, 이미 한글로 명명해 온 병합 운영 흐름을 막는 변경이라 임의로 적용하지 않았다.
- 기존에 저장된 한글 명칭은 그대로 **표시**된다(읽기는 검증하지 않음). 다시 저장하려 할 때만 거부된다.
