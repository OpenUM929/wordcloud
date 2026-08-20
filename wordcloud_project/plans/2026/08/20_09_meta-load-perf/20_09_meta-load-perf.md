# 계획서 — 그룹분석 대상 직원 콤보박스 로딩 지연 조사(배치 이력은 원인 미상 확인)

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: A
> 선행: 없음 (관련: 20_10 — 콤보박스를 검색형 입력으로 바꾸면 이 문제도 함께 해소될 가능성 있음)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 |
| 2026-08-20(3차) | §2, §3.1, §3.2, §5, §7 | **사용자 지시로 진행 방식 변경** — "가설에 맞춰 미리 구현하고, 콘솔·서버 로그로 다른 원인일 경우를 동시에 찾는다". 이에 따라 (1) §3.2(가명 역변환 배치화)를 실측 전 구현, (2) 가설이 틀렸을 때 진짜 원인이 드러나도록 서버·브라우저 양쪽 계측을 신설. 조사 중 **§3.1의 효과에 대한 종전 기재를 정정** — `utils/logger.py:118~119`의 파일 핸들러가 `setLevel(DEBUG)`라 info→debug 하향은 콘솔 출력만 줄였고 **파일 기록은 그대로 남고 있었다**(호출당 2줄). 즉 §3.1만으로는 로깅 비용이 제거되지 않았고, §3.2(호출 자체 제거)가 실질 조치다 |
| 2026-08-20 | §3.1, §5 | §3.1(게이트 불요) 2건 구현: `get_real_id()` 로깅 3곳(182/187/189행) 전부 `logger.debug`로 하향(반환값 불변, 계획서엔 182행만 명시됐으나 189행 `found=False` 경고도 같은 대량호출 경로에서 매번 발생하는 정상 케이스라 같은 위험분류로 판단해 함께 낮춤 — 판단 근거 §5에 기재), `loadMeta()` 옵션 삽입을 `DocumentFragment` 배치로 전환. `.clinerules/.../pseudonym-manager.md` 확인 후 반환값·매핑 로직은 불변으로 유지. py_compile/node --check 통과. §3.2(호출 자체 축소, 게이트 필요)는 미착수 유지 |

## 1. 문제 정의

- **증상**: 그룹분석(`/perspective_test`) 화면 접속 시 (1.1) 대상 직원 콤보박스, (1.2) 배치 이력 패널 로딩에 시간이 오래 걸린다. 사용자는 "전체 데이터를 다 불러와서 그런 것 아니냐"고 추정.
- **재현 조건**: 미확보(서버 미기동, DL-12로 이번 조사는 정적 코드 추적까지만 수행).
- **관찰된 실패 산출물**: 없음(에러 없음, 체감 지연 보고).

## 2. 원인 분석

> ⛔ 원인 확정 게이트 — **미통과**. 재현·실측을 하지 못했다. 아래는 코드 추적으로 확인한 "무엇이 원인이 아닌지"와 "무엇이 유력한 후보인지"이며, §3은 이 상태에 맞춰 "저위험 선제 조치 + 실측 후 확정 조치"로 나눠 제시한다(14-bugfix-gate.md의 "게이트 통과 전 수정 구현 금지" 원칙을 지키되, 로그 제거처럼 위험이 사실상 없는 조치는 선제 적용 가능하도록 구분).

### 1.1 대상 직원 콤보박스

- **호출 경로**: `loadMeta()`(`wordcloud_project/web/templates/perspective_test.html:540`) → `POST /api/perspective/meta`(`wordcloud_project/src/routes/perspective_routes.py:62`) → `get_matrix_meta_light(employee_id=None, enrich=_is_admin())`(`wordcloud_project/src/services/perspective_service.py:2843`).
- **배제됨 — 평가 본문(19,000건) 재적재**: 이 함수는 과거(0619_03) 이미 `load_all_batches()`의 "19,000건 json.loads 병목"을 제거하고 `GROUP BY` 집계로 대체한 경량 버전이다(2843~2892행, `data` blob 미적재). row_options 계산도 집계 쿼리 1회(2869~2880행)뿐.
- **유력 후보 — 직원별 가명 역변환 루프(2926~2948행)**: `enrich`(=`_is_admin()`, 관리자 로그인 상태에서는 항상 참)가 참이면, 조회된 전 직원(운영 규모 약 1.9만 명, DL-3)에 대해 **직원 1명당 최대 4회** `pseudo_mgr.get_real_id()`를 호출한다(`emp_id`, `name`, `department`, `position` 각각) — 최대 약 **7.6만 회/요청**.
  - `get_real_id()`(`wordcloud_project/src/modules/pseudonym_manager.py:178`)는 매 호출마다 **`logger.info(...)`를 무조건 실행**하고(182행), 이어서 `logger.debug(...)` 또는 `logger.warning(...)`을 추가로 실행한다(187/189행) — 호출당 로그 1~2줄.
  - 로거는 `get_pipeline_logger()`(`wordcloud_project/utils/logger.py:84`)이며 **`setLevel(logging.DEBUG)`로 전체 레벨이 열려 있어(94행) DEBUG 로그도 필터링되지 않고 그대로 처리**된다. 콘솔 핸들러(106~109행) 외 파일 핸들러도 구성됨(독스트링 "logs/pipeline/ 디렉토리에 타임스탬프별 파일 생성" — 파일 핸들러 상세 코드는 이번 조사에서 109행 이후까지는 확인하지 않음, 착수 시 재확인 필요).
  - 매핑 데이터 자체는 캐시됨(`_load_mappings()`, `pseudonym_manager.py:39~59`, `self._mapping_cache` 히트 시 파일 재read·복호화 없음) — **파일 I/O 반복은 배제됨**. 다만 `get_real_id()`·`_load_mappings()` 둘 다 `self._lock`(`threading.RLock`, 27행 — 재진입 가능해 데드락은 아님)을 매 호출 진입한다.
  - **결론(가설)**: 7.6만 회의 함수 호출 자체(락 획득/해제, dict lookup)는 개별로는 저렴하지만, **매 호출 로깅(문자열 포맷 + `datetime.now()` + 핸들러 I/O)이 이 정도 호출량에서 누적되면 유의미한 지연(초 단위)을 만들 수 있다** — 실측(예: 이 구간만 별도 타이밍 로그)으로 확정 필요.
- **프론트엔드 후보**: `loadMeta()`(549~557행)가 응답받은 `employees` 배열(최대 약 1.9만 개)을 `document.createElement('option')` + `appendChild`로 **하나씩** live DOM(`<select>`)에 추가한다 — `DocumentFragment` 배치 삽입이 아니라 매 삽입마다 브라우저가 재계산할 수 있음. 이 자체도 대량 옵션에서는 체감 가능한 지연 요인.

### 1.2 배치 이력

- **호출 경로**: `loadBatchHistory()`(`perspective_test.html:3460`) → `GET /api/perspective/batches`(`perspective_routes.py:1056`) → `load_batch_history()`(`perspective_service.py:1809`) → `_load_batch_list()`(1649행).
- **조사 결과**: 세 함수 모두 **이미 경량화되어 있음**(0619_03 주석으로 명시) — `evaluations`/`batch_work_orders` 테이블에 대한 소수의 집계(`COUNT`, `GROUP BY`) SQL만 실행, 직원 단위 반복 루프 없음, 가명 역변환도 없음(배치 단위 표시만이라 `pseudo_mgr` 호출 자체가 없음).
- **미확정**: 정적 조사로는 지연 원인을 찾지 못했다 — 20_06(배치 관리 화면) 조사와 동일한 상황. 가능성: (a) 사용자가 실제로 지연을 느낀 시점이 배치 이력 자체가 아니라 콤보박스(1.1)와 겹쳐 체감했을 가능성, (b) 운영 DB의 `batch_work_orders`/`evaluations` 인덱스 부재, (c) 이번 조사에서 못 본 다른 호출.

## 3. 수정 방안

### 3.1 즉시 적용 가능(게이트 불요 — 위험 사실상 없음, 로깅 레벨/삭제만)

- `get_real_id()`(`pseudonym_manager.py:178~190`)의 **무조건 `logger.info` 호출(182행)을 제거하거나 `logger.debug`로 낮춘다** — 현재도 `logger.setLevel(DEBUG)`라 레벨을 낮추는 것만으로는 부족하므로, 대량 호출 구간(예: `get_matrix_meta_light`의 enrich 루프)에서는 **호출 자체를 줄이는 쪽**(3.2)이 근본적이다. 로깅 레벨 조정은 보조 조치.
- 프론트엔드 `loadMeta()`(549~557행)의 옵션 삽입을 `DocumentFragment`에 모아 한 번에 `appendChild`하도록 변경 — 동작 변화 없이 렌더 방식만 바꾸는 저위험 개선.

### 3.2 가명 역변환 호출 축소 — 실측 전 선구현(2026-08-20 3차)

> 진행 방식 변경: 사용자가 "가설이 맞을 경우 한 번에 해결되도록 미리 구현하고, 로그로 다른 원인일 경우를 동시에 찾자"고 결정했다. 이 조치는 **결과값을 바꾸지 않는 순수 성능 조치**(아래 등가성 근거)라 가설이 빗나가도 손해가 없다는 판단이 근거다. 원인 확정은 §7의 실측으로 사후 판정한다.

- `PseudonymManager.get_real_id_map()` 신설 — `pseudo_to_real` 매핑의 **얕은 복사본**을 락 1회로 반환. 내부 캐시를 그대로 넘기지 않는 이유는 호출부가 매핑 원본을 오염시킬 수 없게 하기 위함(가명 매핑 절대 규칙 준수, 신규 가명 생성 경로에는 쓰지 않는 조회 전용 API).
- `perspective_service._make_real_id_resolver()` 신설 — 위 스냅샷으로 로컬 dict 조회를 하는 해석기. **`get_real_id()`와 반환 규칙을 1:1로 맞춘다**(빈값·공백뿐이면 원값 통과, 그 외엔 strip 후 조회, 미발견 시 strip 된 값 반환).
- 적용처: `get_matrix_meta_light()`의 enrich 루프, `search_employees()`의 enrich 루프. 직원 1명당 최대 4회 × 1.9만 명 = **최대 7.6만 회의 락 획득 + 로깅**이 **스냅샷 1회 + 로컬 조회**로 바뀐다.
- 등가성 근거: T2가 경계값 9종(매핑 있음/없음, 앞뒤 공백, 빈 문자열, 공백뿐, None, 0, 비문자열)에 대해 해석기 == `get_real_id()`를 대조하고, T3이 `/meta` enrich 응답 전체를 **종전 방식으로 그 자리에서 재계산한 기대값**과 필드 단위로 대조한다(복원이 실제로 일어났는지도 함께 확인해 대조가 공허해지지 않게 했다).
- 규칙 준수: 가명 관리 문서 §2("조회 시 원본 복원")의 의무는 그대로다 — 복원을 생략하는 게 아니라 **같은 복원을 더 적은 오버헤드로** 한다. `get_real_id()` 자체는 손대지 않았다.

### 3.3 계측 — 가설이 틀렸을 경우를 같은 실행에서 찾기(신설)

정적 분석이 소진된 상태라, "가설 검증"과 "다른 원인 탐색"을 한 번의 실행으로 동시에 하도록 계측을 심었다. 계측은 로그·콘솔 출력만 하고 어떤 반환값·동작도 바꾸지 않으며, 계측 자체가 실패해도 요청이 진행되도록 전 경로를 예외로부터 격리했다.

| 위치 | 남는 것 | 무엇을 가르는가 |
|------|---------|----------------|
| `utils/perf.py` `install_request_timing` (전역, `web/app.py`) | 모든 요청의 `method·path·status·bytes·ms` (`STAGE:PERF_REQ`) | 우리가 후보로 꼽지 않은 요청(정적 자원 포함)까지 전부 보인다 — 20_06 §2 가능성 1의 유일한 판별 수단 |
| `utils/perf.py` `perf_span` — `meta.sql.facet` / `meta.sql.employees` / `meta.employees` | 구간별 ms (`STAGE:PERF`) | `/meta`가 느릴 때 **SQL이냐 가명 역변환이냐 조립이냐** |
| `batch_history.count_sql` / `count_batches` / `list` | 구간별 ms | 1.2(배치 이력)의 미확정 원인을 세 후보로 쪼갠다 |
| `work_orders.query` / `work_orders.display_name` | 구간별 ms | 20_07이 추가한 파일 읽기 루프(최대 20회)가 20_06 지연에 기여하는지 |
| `web/static/js/perf_probe.js` (base.html 전역) | 모든 fetch·XHR 왕복시간, 페이지 nav 타이밍, `__perf.mark/since/span` (`[PERF]` 콘솔) | 서버 ms와 대조해 **서버 / 네트워크 / 브라우저 렌더** 중 어디인지 |
| `loadMeta:parse` / `loadMeta:render` / `loadBatchHistory:total` / `loadWorkOrders:*` / `renderIntegratedDataTree` | 응답 이후 화면 조립 시간 | 요청이 다 빠른데 느린 경우(=DOM 조립이 범인)를 잡는다 |

판정 규칙(§7에 절차로 재기재):
- 서버 로그 ms ≈ 브라우저 fetch ms → **서버가 원인**. 이때 `meta.employees`가 크면 이 계획서의 가설이 맞은 것.
- 서버 로그 ms ≪ 브라우저 fetch ms → **네트워크·프록시 구간**이 원인(코드 아님).
- fetch는 빠른데 `mark` 렌더 값이 크다 → **브라우저 DOM 조립**이 원인.

### 3.4 (참고) 종전 §3.2 문안 — 실측 후 확정 예정이던 내용

- `get_matrix_meta_light()`의 enrich 루프(2926~2948행)에서 직원별 4회 `get_real_id()` 호출을 **1회 배치 조회**로 바꿀 수 있는지 확인 — `PseudonymManager`에 여러 개 pseudonym을 한 번에 역변환하는 배치 API가 없다면(이번 조사에서 미확인, `pseudonym_manager.py` 전체를 더 읽어야 함) 신설을 검토. 이미 `_load_mappings()`가 캐시된 전체 매핑 dict를 갖고 있으므로, `get_real_id()`를 매번 호출하는 대신 **enrich 루프 시작 전 `mapping = pseudo_mgr._load_mappings()`류의 캐시 dict를 한 번만 얻어 로컬에서 직접 `dict.get()`**(락 없이, 락은 무결성이 필요한 쓰기 경합에만 필요하고 읽기 캐시 히트에는 불필요할 가능성) 하는 방식으로 락 오버헤드까지 없앨 수 있는지도 검토 대상 — 단, `PseudonymManager`는 도메인 절대 규칙(`.clinerules/projects/wordcloud/modules/pseudonym-manager.md`) 대상이므로 **이 문서를 먼저 읽고 그 규칙 안에서만** 변경한다.
- 1.2(배치 이력)는 원인 미확정 — Network 탭 타이밍 캡처로 실제로 느린 요청이 `/api/perspective/batches`인지 아닌지부터 확인해야 한다.

## 4. 롤백 계획

- 3.1(로깅 레벨 조정, DocumentFragment 배치 삽입)은 동작 변화가 없는 순수 성능 조치라 되돌리기 위험 없음(커밋 되돌리기).
- 3.2(가명 역변환 방식 변경)는 `PseudonymManager` 도메인 절대 규칙 대상이라 변경 시 별도 백업·검증 절차(`.clinerules/common/core/18-backup-before-modify.md`)를 따른다.

## 5. 결과 (구현 완료 후 기재)

- **§3.1 적용 완료(게이트 불요 항목만)**:
  - `pseudonym_manager.py:182` `get_real_id()` 진입 시 무조건 실행되던 `logger.info` → `logger.debug`.
  - 같은 함수 내 `logger.warning("found=False...")`(189행)도 함께 `logger.debug`로 하향. 계획서 원문(§3.1)은 182행만 명시했으나, 조사(§2)에서 확인한 것처럼 이 경고는 "가명화되지 않은 값(부서/직급 등)을 그대로 반환"하는 **정상적인 반복 경로**이지 이상 상황이 아니다 — 대량 호출(직원×최대4필드)에서 매번 WARNING 레벨로 콘솔+파일 양쪽에 기록되는 것이 182행보다 오히려 더 큰 로그량일 수 있어, 같은 "로깅 레벨만 변경·반환값 불변" 위험분류로 판단해 함께 조정. `get_real_id()`의 반환값·매핑 로직·락 사용은 전혀 바꾸지 않음.
  - `perspective_test.html:559~569` `loadMeta()`의 `<select>` 옵션 삽입을 낱개 `appendChild` → `DocumentFragment` 1회 삽입으로 전환. 렌더 결과(옵션 목록·순서·선택값) 동일, 삽입 방식만 변경.
  - 검증: `python -m py_compile pseudonym_manager.py` 통과, `perspective_test.html` 인라인 `<script>`(536~4032행) 추출 후 `node --check` 통과. 실동작(Network 탭 응답시간 비교)은 §7대로 서버 기동 승인 후 사용자 확인 필요 — PND.
- **§3.1 효과에 대한 정정(2026-08-20 3차)**: 위 로깅 하향은 **콘솔 출력만** 줄였다. `utils/logger.py`의 파일 핸들러가 `setLevel(logging.DEBUG)`(118~119행)라 debug 로그도 파일에는 그대로 기록된다 — 즉 대량 호출 구간의 로그 파일 I/O는 §3.1로 제거되지 않았다. 종전 §5 기재가 이 점을 구분하지 않았으므로 정정한다. 실질 제거는 §3.2(호출 자체를 없앰)로 이뤄졌다.

- **§3.2 구현 완료(2026-08-20 3차, 실측 전 선구현)**:
  - `src/modules/pseudonym_manager.py` — `get_real_id_map()` 신설(락 1회, 방어적 복사본). 기존 메서드는 무변경.
  - `src/services/perspective_service.py` — `_make_real_id_resolver()` 신설, `get_matrix_meta_light()`·`search_employees()`의 enrich 루프가 이 해석기를 쓰도록 교체. 최대 7.6만 회 락+로깅 → 스냅샷 1회 + 로컬 dict 조회.
  - 등가성은 T2(경계값 9종)·T3(응답 전체 필드 대조)로 검증 — §6 참조.

- **§3.3 계측 신설(2026-08-20 3차)**:
  - `utils/perf.py`(신규) — `perf_span` 구간 계측 + `install_request_timing` 전역 요청 계측. 300ms 이상은 WARNING으로 올려 콘솔에도 뜨게 했다.
  - `web/app.py` — `create_app()`에서 요청 계측 훅 설치.
  - `src/services/perspective_service.py` — `/meta` 3구간, 배치 이력 3구간에 span 추가.
  - `src/routes/batch_routes.py` — 작업서 조회/명칭 병합 2구간에 span 추가(20_06 대상).
  - `web/static/js/perf_probe.js`(신규) + `web/templates/base.html` `<head>` 로드 — 전 화면의 fetch·XHR·nav 타이밍 콘솔 계측. `__perf.report()`로 표 출력.
  - `web/templates/perspective_test.html`·`web/static/js/integrated_batch.js` — 응답 이후 화면 조립 구간 mark 추가.
  - 검증: `py_compile`(5개 파일) 통과, `node --check`(perf_probe.js, integrated_batch.js, perspective_test.html 인라인 스크립트) 통과.

- **1.2(배치 이력) — 원인 미확정 유지, 다만 계측으로 판별 가능해짐**: `batch_history.count_sql`/`count_batches`/`list` 세 구간과 브라우저 `loadBatchHistory:total`을 대조하면 "실제로 느린지"부터 즉시 갈린다.

## 6. 영향도 분석

- **변경 파일(실제)**: `src/modules/pseudonym_manager.py`(로깅 하향 + `get_real_id_map()` 신설), `src/services/perspective_service.py`(`_make_real_id_resolver` 신설, enrich 루프 2곳 교체, span 6곳), `src/routes/batch_routes.py`(span 2곳), `web/app.py`(요청 계측 훅), `utils/perf.py`(신규), `web/static/js/perf_probe.js`(신규), `web/templates/base.html`(계측 스크립트 로드), `web/templates/perspective_test.html`·`web/static/js/integrated_batch.js`(렌더 구간 mark).
- **영향 범위**: `pseudonym_manager.py`는 프로젝트 전역에서 가명 역변환에 쓰이는 핵심 모듈(DL-1 대상) — 이번 변경은 **기존 메서드를 건드리지 않고 조회 전용 API 1개를 추가**하는 방식이라 다른 호출부는 영향받지 않는다. `base.html` 변경은 전 화면에 계측 스크립트가 실린다는 뜻이므로, 계측 실패가 화면을 깨지 않도록 `perf_probe.js` 전 경로를 try/catch로 감쌌고 `window.__perf` 부재 시에도 호출부가 동작하도록 모든 사용처를 `if (window.__perf)`로 가드했다.
- **되돌리는 법**: 계측만 끄려면 `base.html`의 `perf_probe.js` 로드 1줄과 `web/app.py`의 `install_request_timing(app)` 2줄을 제거하면 된다(나머지 코드는 계측이 없어도 동작).

## 6-2. 자동 검증(서버 미기동) — 2026-08-20 3차

| # | 검증 대상 | 방법 | 결과 |
|---|-----------|------|------|
| T1 | `get_real_id_map()`이 방어적 복사본인가 | 반환 dict를 오염시킨 뒤 매니저 상태 재확인 | 통과 |
| T2 | 배치 해석기 == `get_real_id()` | 경계값 9종(매핑 유무·앞뒤 공백·빈값·공백뿐·None·0·비문자열) 파라미터화 대조 | 통과(9건) |
| T3 | `/meta` enrich 응답이 종전 방식과 동일 | 종전 규칙으로 기대값 재계산 후 필드 단위 대조 + 복원이 실제로 일어났는지 확인 | 통과 |
| T4 | `enrich=False` 노출 규칙 불변 | 가명 유지·`employee_id_real` 키 부재 확인 | 통과 |
| T5 | `perf_span`이 흐름을 바꾸지 않음 | 정상 반환 / 예외 전파 확인 | 통과 |
| T6 | 요청 계측 훅이 응답을 바꾸지 않음 | Flask `test_client`로 200 본문 동일·500 그대로 확인 | 통과 |

실행: `python -m pytest plans/2026/08/20_09_meta-load-perf/test/ -q` → **14 passed**(파라미터화 포함). 다른 계획서 스위트와 동시 실행 시 **55 passed**.

운영 영향: `outputs/`·`processed_data/` 신규 생성 0건, `.sessions/deploy_sessions.db` 행수 불변(직원 50·평가 12·갤러리 18·작업서 3), 테스트 유입 행 0건. DB 파일 mtime은 갱신되는데, 이는 `deploy_session_service.py:404~405`가 **import 시점에** 실 DB로 스키마 마이그레이션을 돌리는 기존 동작 때문이며 이번 변경과 무관하다(스키마 전용, 데이터 무변경).

## 7. 테스트/검증 계획 — 사용자 실측 절차(PND)

서버를 기동할 수 있는 시점에 아래를 그대로 하면 **가설 확정 또는 진짜 원인 특정**이 한 번에 끝난다.

1. 브라우저 F12 → Console 열고 `/perspective_test` 접속.
2. 콘솔에서 `[PERF]` 줄을 읽는다 — `fetch POST /api/perspective/meta`, `mark loadMeta:render`, `fetch GET /api/perspective/batches`, `nav ...`.
3. 서버 콘솔·`logs/pipeline/pipeline_*.log`에서 같은 시각의 `STAGE:PERF_REQ`(요청 총시간)와 `STAGE:PERF span=meta.*`(구간)를 본다.
4. 판정:
   - `span=meta.employees`가 크다 → **이 계획서의 가설이 맞았고 §3.2로 이미 해소**(적용 전 수치가 없으므로, 필요하면 `_make_real_id_resolver` 대신 `get_real_id` 건별 호출로 되돌린 임시 빌드와 비교).
   - `span=meta.sql.*`가 크다 → 원인은 SQL·인덱스. 가설이 틀린 경우로, `evaluations`/`employees` 인덱스 점검이 다음 수.
   - 서버 총시간은 작은데 브라우저 fetch가 크다 → 네트워크·프록시 구간(코드 아님).
   - fetch는 작은데 `loadMeta:render`가 크다 → 브라우저 DOM 조립. (20_10에서 1.9만 option 생성을 이미 없앴으므로 이 값이 작아졌는지도 함께 확인된다.)
   - `/api/perspective/batches`가 실제로 느린지 여기서 처음 확정된다 — 느리면 `batch_history.*` 세 구간 중 어느 것인지 바로 보인다.
5. 표가 필요하면 콘솔에 `__perf.report()`.

## 8. 리스크 및 제약

- 원인 확정 게이트 미통과 상태 — 3.2는 실측 전 착수 금지.
- `PseudonymManager`는 도메인 절대 규칙 대상(가명 관리) — 변경 전 `.clinerules/projects/wordcloud/modules/pseudonym-manager.md` 필독.
- 서버 무단 기동 금지(DL-12) — 실측은 사용자 승인 하에.
