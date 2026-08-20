# 계획서 — 그룹분석 이어하기 시 그래프 저장이 배포용 태그로 바뀌는 버그 수정

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: A
> 선행: 12_01(그래프 저장 기능 최초 구현)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 |
| 2026-08-20 | §3, §5, §6 | 구현 착수 — **§3의 "4개 파일이 `create_session()`을 호출한다"는 전제가 사실과 다름을 실측으로 확인**: `grep -rn "create_session("` 결과 실제 호출부는 `perspective_routes.py:202` 단 한 곳뿐. `batch_merge_service.py`/`batch_work_order_service.py`/`user_data_manager.py`는 `deploy_session_service`의 `_get_conn`/`_init_db` 커넥션 헬퍼만 재사용할 뿐 `deploy_sessions` 테이블에 쓰지 않는다(각 파일 6~26행대 import 확인). DL-8 대사 대상 자체가 없어 "대사 완료 후 확정"으로 미뤘던 세부 수정을 바로 구현함. `kind` 컬럼 추가·`saveGraph` 재개 지원까지 코드 적용 완료, 서버 미기동으로 실제 재현 검증은 미수행(Pre-Done) |
| 2026-08-20 | §2 | 독립 `plan-reviewer` 검증 결과 반영 — DL-8 오류 지적은 위 구현 착수 시 발견과 교차 확인(일치). 추가로 §2 코드 인용 라인 번호 드리프트 정정(`:2007`→`:1995`, HEAD 기준으로 명시), 스키마 컬럼 목록 오류 정정(`started_at`→`completed_at`이 원본 컬럼, `started_at`은 v8 마이그레이션 추가분), `deploy_gallery.html` 인용에 실제 비교 지점(`:1678`) 추가 |

## 1. 배경 및 목적

사용자가 그룹분석(`/perspective_test`) 화면에서 "그래프 저장"을 실행하던 중 처리 속도 저하로 강제 종료했다가, 재실행 후 "이어하기" 팝업에서 이어하기를 선택하면 저장 갤러리(`/deploy-gallery`)에 동일 작업 결과가 **그래프 태그와 배포용 태그 2종으로 쪼개져** 나타난다. 앞서 완료된 항목은 "그래프", 이어하기 이후 완료된 항목은 "배포용"으로 표시된다. 이 오분류를 없애 하나의 작업이 하나의 태그로 일관되게 저장되도록 한다.

## 2. 원인 분석

> ⛔ 원인 확정 게이트 — **정적 코드 추적으로 사용자 보고 5단계 타임라인 전 구간을 코드 호출 경로와 1:1 대조**했다. 서버 미기동(사용자 승인 없는 서버 실행 금지) 상태라 **실제 브라우저 실행 재현은 아직 하지 못했다** — 이 점을 §5 결과에서 사용자 실행 확인으로 보완해야 완결된다.

- **사용자 보고 재현 조건**: ① 그래프 저장 실행 → ② 도중 강제 종료 → ③ 재실행 → ④ 이어하기 팝업에서 "이어서 계속" 선택 → ⑤ 정상 속도로 완료. 결과: 앞부분(중단 전 완료분)=그래프, 뒷부분(이어하기 이후 완료분)=배포용.
> 아래 §2의 라인 번호는 **수정 전 커밋(git HEAD, 20_02 스로틀 패치 반영·본 계획서 수정 반영 전)** 기준으로 고정 인용한다. 실제 수정으로 파일 라인 수가 늘어나 현재 작업트리 번호와는 다르다 — 수정 후 위치는 §5·§6 참조.

- **근거(코드 경로 대조, HEAD 기준)**:
  1. `wordcloud_project/web/templates/perspective_test.html:1872` `saveGraph()`가 `wordcloud_project/web/templates/perspective_test.html:1965`에서 `POST /api/perspective/deploy-session/start`로 세션을 만들고, 항목마다 `wordcloud_project/web/templates/perspective_test.html:1995`의 `POST /api/perspective/matrix/save-graph`를 호출한다. 이 저장 경로는 `wordcloud_project/src/services/perspective_service.py:3877`에서 `"source": "graph"`로 고정 기록한다(`_append_trend_graph_to_manifest`).
  2. `saveGraph()`는 `localStorage.setItem('deploy_session_id', ...)`를 **호출하지 않는다** — `perspective_test.html` 전체에서 이 호출은 `saveDeploy()` 안(1718행)에만 있다(`grep -n "localStorage" perspective_test.html` 결과로 확인, 그래프 지표/단위 저장용 `localStorage.setItem('graph_metric'/'graph_unit', ...)`와는 별개 키).
  3. 강제 종료 시 서버 쪽 `deploy_sessions` 레코드는 `status='running'`으로 남는다(`wordcloud_project/src/services/deploy_session_service.py:400` 부근 `create_session`이 `'running'`으로 INSERT, 정상 종료 전까지 상태 전이 없음).
  4. 재실행 시 `checkResume()`(`perspective_test.html:3735`)가 `GET /api/perspective/deploy-session/active`로 이 세션을 찾아 "이어서 계속" 버튼을 노출한다. 이 버튼은 `resumeDeploySession(sessionId)`(`perspective_test.html:3797`)에 고정 연결되어 있고, 이 함수는 무조건 `saveDeploy(sessionId)`(`perspective_test.html:3804`)를 호출한다. `saveGraph`용 재개 함수(`resumeGraphSession` 같은 것)는 코드베이스에 **존재하지 않는다**(`grep -n "resumeGraphSession"` 결과 0건).
  5. `deploy_sessions` 테이블 스키마(`wordcloud_project/src/services/deploy_session_service.py:24`~`33`, `CREATE TABLE deploy_sessions`, 이어서 `35`~`44`가 `deploy_tasks`)에는 이 세션이 그래프 저장용인지 제출용 저장용인지 구분하는 컬럼이 **없다**(컬럼: `session_id, created_at, status, options, total_count, completed_count, failed_count, paused_at, completed_at`뿐 — `started_at`은 별도 컬럼이 아니라 Schema v8 마이그레이션이 나중에 추가한 것, `:274` `ALTER TABLE`). `options`에 원본 요청 바디가 JSON으로 들어있어 이론상 구분 가능한 정보는 있으나, 재개 로직이 이를 읽어 분기하지 않는다.
  6. `saveDeploy()`는 재개된 세션의 나머지 `employee_ids`를 `/deploy-session/chunk`로 이어받아 `POST /api/perspective/matrix/save-deploy`(`perspective_test.html:1744`)를 호출하고, 이 경로는 `_append_to_deploy_manifest` → `entry.source` 를 `'deploy'`로 저장한다(`gallery_db_service.py` 25~35행 스키마 `source TEXT DEFAULT 'deploy'`). 화면상 `source==='deploy'`가 "배포용"으로 라벨링되는 지점은 `deploy_gallery.html:1547`,`1787`(소스 칩 라벨 배열 `[['deploy','배포용'],...]`)과 `:1678`(`_buildDownloadFileName()`의 `src === 'deploy' ? '배포용' : ...` 실제 비교/분기)이다.
- **분석**: ①~⑥을 이으면 "앞부분=그래프, 뒷부분=배포용"이 정확히 재현된다 — `saveGraph()`가 만든 세션을 재개할 방법이 코드에 `saveDeploy()` 경유 하나뿐이라, 재개된 나머지 항목은 항상 다른 저장 API(`save-deploy`)로 처리되어 다른 `source` 값을 얻는다.
- **반증 실험**: 만약 이 가설이 틀렸다면, `saveGraph()`가 자체적으로 `deploy_session_id`를 localStorage에 저장하고 `resumeDeploySession` 이전에 세션 종류를 판별해 `saveGraph(sessionId)`를 호출하는 코드가 어딘가에 있어야 한다 — 전체 파일 grep(`resumeGraphSession`, `session.*kind`, `session_type`)에서 0건이므로 반증되지 않았다.
- **회귀 도입 지점**: 신규 결함이 아니라 **최초 설계 누락** — `saveGraph()`(그래프 저장, 2026/08/12_01에서 신규 구현)가 `saveDeploy()`(기존 제출용 저장, 그 이전부터 존재)의 세션 인프라를 재사용하면서 재개 경로를 그래프 전용으로 분기하지 않고 넘어간 것으로 판단된다(12_01 계획서에 재개 시나리오 명시 없음).

## 3. 수정 방안

- **핵심 변경**: `deploy_sessions` 세션 생성 시 어떤 저장 종류(`deploy`/`graph`)인지 기록하고, 재개 버튼이 그 값을 보고 맞는 저장 함수로 분기하도록 한다.
- **DL-8 재확인 결과 — 대사 불필요로 정정**: 최초 작성 시 "`batch_merge_service.py`/`batch_work_order_service.py`/`user_data_manager.py` 3개 파일도 `create_session()`을 호출한다"고 적었으나, 구현 착수 시 `grep -n "create_session(" wordcloud_project/src -r`로 재확인한 결과 **실제 호출부는 `perspective_routes.py:202` 단 한 곳뿐**이었다. 위 3개 파일은 `deploy_session_service`의 `_get_conn`/`_init_db`(커넥션·초기화 헬퍼)만 import해 자신들의 테이블(`batch_work_orders` 등)에 쓸 뿐, `deploy_sessions`/`create_session()`은 건드리지 않는다. 따라서 컬럼 추가로 영향받는 호출부는 처음부터 1곳뿐이었고, 대사 없이 바로 구현 가능했다.
- **적용된 변경**:
  - `deploy_session_service.py`: Schema v10 마이그레이션으로 `deploy_sessions.kind TEXT DEFAULT 'deploy'` 추가(기존 `Schema v8`/`started_at` 사례와 동일 패턴, `_apply_schema_migrations()` 내 `if current < 10:` 블록). `create_session(options, employee_ids, kind='deploy')`로 시그니처 확장, INSERT문에 `kind` 반영. `get_active_sessions()`의 SELECT 컬럼에 `kind` 추가.
  - `perspective_routes.py`: `/deploy-session/start` 라우트가 요청 바디에서 `kind = data.get('kind', 'deploy')`를 읽어 `create_session(options, employee_ids, kind=kind)`로 전달.
  - `perspective_test.html`:
    - `saveDeploy()`의 신규 세션 생성 바디에 `kind: 'deploy'` 명시 추가(1692행 부근).
    - `saveGraph()`를 `saveDeploy()`와 동일한 구조로 확장: 시그니처를 `saveGraph(resumeSessionId = null)`로 변경, `const options` → `let options`(재개 시 세션 저장값으로 재할당하기 위함), 재개 시 `/deploy-session/tasks`로 기존 completed/failed 결과를 사전 로드하고 `/deploy-session/retry`로 실패 태스크를 pending 리셋, 신규 세션 생성 바디에 `kind: 'graph'` 추가, 재개 시 `/deploy-session/progress`로 `total`·저장된 `options`(metric/unit 포함) 복원. 완료 요약(`renderGraphComplete`)의 metric/unit도 함수 상단 UI값 대신 실제 처리에 쓰인 `options.metric`/`options.unit`을 참조하도록 수정(재개 시 UI값과 세션 저장값이 다를 수 있어 요약 불일치를 방지).
    - `checkResume()`: "이어서 계속" 버튼의 `onclick`을 `targetSession.kind === 'graph' ? 'resumeGraphSession' : 'resumeDeploySession'`으로 분기.
    - 신규 함수 `resumeGraphSession(sessionId)` 추가 — `resumeDeploySession()`과 동일하게 `/deploy-session/resume` 호출 후 `saveGraph(sessionId)` 실행.
  - `/deploy-session/tasks`·`/deploy-session/retry`·`/deploy-session/progress` 라우트는 `session_id`로만 동작하는 범용 라우트(그래프/배포 구분 없음)라 백엔드 추가 변경 불요, 실측으로 확인 완료.
- **기존 미완료 세션 하위호환**: 마이그레이션 이전에 생성된 세션은 `kind` 컬럼이 없거나 기본값 `'deploy'`가 들어가므로, 이 계획서 배포 이전에 이미 중단된 그래프 세션은 재개 시 여전히 배포용으로 저장된다 — 사용자에게 고지 필요(§5에 기재).

## 4. 롤백 계획

- `deploy_sessions.kind` 컬럼은 `DEFAULT 'deploy'`로 추가하므로, 프론트엔드 변경만 되돌리면(커밋 되돌리기) 기존 동작(전부 `saveDeploy` 경유 재개)으로 즉시 복귀 가능. 컬럼 자체를 제거할 필요는 없음(하위 호환 유지).

## 5. 결과 (구현 완료 후 기재)

- **적용된 변경**: §3에 기재된 6개 파일 위치 전부 코드 적용 완료(2026-08-20). `node --check`로 `perspective_test.html`의 인라인 스크립트 블록 구문 검증 통과.
- **검증 결과**: (미착수) — 서버 무단 기동 금지(DL-12)로 실제 재현은 하지 못함. 사용자 승인 하에 서버를 기동해 ①그래프 저장 시작 → ②강제 종료 → ③재실행 → ④"이어서 계속" → ⑤완료 시나리오를 다시 밟아, 저장 갤러리에서 해당 배치 전체 항목이 `source='graph'`로 통일되는지, 그리고 기존 제출용 저장(saveDeploy) 재개가 회귀 없이 `source='deploy'`로 유지되는지 확인 필요. 확인 후에만 상태를 Done으로 전환한다.

## 6. 영향도 분석

- **변경 파일**: `wordcloud_project/src/services/deploy_session_service.py`(스키마 v10 마이그레이션, `create_session` 시그니처, `get_active_sessions` SELECT), `wordcloud_project/src/routes/perspective_routes.py`(`/deploy-session/start`가 `kind` 수용), `wordcloud_project/web/templates/perspective_test.html`(`saveGraph`/`saveDeploy`/`checkResume`/`resumeDeploySession`/신규 `resumeGraphSession`)
- **영향 범위**: `deploy_sessions`/`deploy_tasks` 테이블에 실제로 쓰는 곳은 `perspective_routes.py`(`create_session` 호출부 유일) 하나뿐임을 실측으로 확인(§3). `batch_merge_service.py`/`batch_work_order_service.py`/`user_data_manager.py`는 커넥션 헬퍼만 공유하고 이 테이블에 쓰지 않아 영향 없음. `ALTER TABLE ... ADD COLUMN ... DEFAULT 'deploy'`이므로 기존 행·기존 쿼리(`SELECT *`가 아닌 명시적 컬럼 나열 쿼리들)는 깨지지 않음.

## 7. 테스트/검증 계획

- 시나리오 1: 그래프 저장 시작 → 중간에 세션 강제 종료(탭 닫기) → 재실행 → 이어하기 → 완료 후 저장 갤러리에서 해당 배치의 모든 항목이 `source='graph'`(그래프 태그)로 통일되는지 확인.
- 시나리오 2: 제출용 저장(saveDeploy)도 동일한 방식으로 강제 종료 후 이어하기 → 전부 `source='deploy'` 유지되는지 회귀 확인(기존 동작 보존).
- 시나리오 3: §3 마이그레이션 이전에 생성된 세션(‘kind’ 없음)을 재개했을 때 에러 없이 기존 동작(배포용 저장)으로 처리되는지 확인.

## 8. 리스크 및 제약

- `deploy_sessions`/`deploy_tasks` 공유 테이블 변경이라 DL-8(공통 모듈 침범) 대상이었으나, 실제 호출부가 1곳뿐임을 확인해 해소됨(§3, §6).
- 서버 무단 기동 금지(DL-12) — 재현·검증은 사용자 승인 하에 진행. 이 계획서는 코드 적용까지 완료했고(Pre-Done), 실행 검증 전에는 Done으로 전환하지 않는다.
- 이미 잘못 태그된 과거 갤러리 항목(그래프로 시작했다가 배포용으로 갈라진 기존 데이터)의 사후 정정은 이 계획서 범위 밖 — 별도 데이터 정정 계획 필요 여부는 사용자 확인 필요.
