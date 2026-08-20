# 계획서 — 배치 관리 화면 로딩 지연 조사

> 상태: Doing | 작성일: 2026-08-20
> 작업 유형: A
> 선행: (없음)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 — §2 조사 결과 원인 미확정, §3 보류 |
| 2026-08-20(3차) | §2, §3, §7, §8 | **사용자 지시로 진행 방식 변경** — "가설대로 미리 구현하되, 콘솔·서버 로그로 다른 원인일 경우를 동시에 찾는다". 이 계획서는 §2에서 코드 후보가 **전부 배제되어** 미리 구현할 수정 자체가 없는 상태였다. 따라서 여기서의 선행 조치는 코드 수정이 아니라 **계측 신설**이다(20_09 §3.3과 공용). 전역 요청 계측 + 이 화면의 두 API 구간 계측 + 브라우저 fetch/렌더 계측을 심어, 다음 실행 1회로 원인이 드러나게 했다. §3에 계측 내용과 판정 규칙을 기재하고, §7을 사용자 실측 절차로 구체화 |
| 2026-08-20 | §1, §2 | 독립 검증 반영 — (1) §1의 URL `/metadata/batch`가 실존하지 않음을 확인해 정정(`/integrated_batch`가 정확한 경로, `ui_routes.py:63~66`). `/metadata` 라우트(`ui_routes.py:57~60`)는 `render_template('metadata.html')`을 호출하나 그 템플릿 파일은 커밋 `7600abf`("metadata→integrated 전면 리팩토링")로 삭제되어 **현재 호출 시 500 에러가 나는 죽은 라우트**임을 확인 — 사용자가 보는 화면과 무관, 조사 범위(`/integrated_batch`)는 그대로 유효. (2) `batch_work_orders` 인덱스 존재 여부를 실측(`deploy_session_service.py:113~114` `idx_wo_status`/`idx_wo_created ON batch_work_orders (created_at DESC)` 확인됨) — §2 가능성 2를 정정. (3) 화면 라우트 핸들러 자체(`ui_routes.py:63~66`)를 열람해 §2 가능성 3(`render_template` 비용) 배제 근거 추가, `/api/mappings/last`(`api_routes.py:693~708`) 실측해 단일 JSON 파일 읽기(경량)임을 확인 |

## 1. 문제 정의

- **증상**: 배치 관리 화면(정확한 경로 `/integrated_batch`, 라우트 정의 `wordcloud_project/src/routes/ui_routes.py:63~66`, 템플릿 파일 `wordcloud_project/web/templates/integrated_batch.html` — 과거 `metadata_batch.html`에서 커밋 `7600abf`로 리네이밍됨. 네비게이션 링크는 `wordcloud_project/web/templates/base.html:190` "📄 통합데이터 생성") 진입 시 로딩 시간이 매우 길다. 사용자는 "굳이 데이터 호출까지 필요 없는데 데이터까지 모두 호출하는 것으로 보임"이라고 원인을 추정.
- **관찰된 실패 산출물**: 없음(에러 로그·스택트레이스 미보고, "느리다"는 체감 보고만 있음) — 이 계획서는 정적 코드 검토로 후보를 좁히는 단계이며, §2의 원인 확정 게이트를 아직 통과하지 못했다.
- **재현 조건**: 미확보. 실행 재현에는 서버 기동이 필요한데 사용자 승인 없는 서버 실행은 금지(DL-12)라 이번 조사는 코드 정적 분석까지만 수행했다.

## 2. 원인 분석

> ⛔ 원인 확정 게이트 미통과 — 재현하지 못했고, 아래는 "무엇이 원인이 **아닌지**"를 코드로 배제한 결과다. §3 수정 방안은 게이트 통과 전이라 작성하지 않는다(14-bugfix-gate.md, 01-type-a-bugfix.md 준수).

- **조사 범위**: 배치 관리 화면 진입 시 로드되는 API 전부를 프론트엔드 소스에서 추적.
  - 초기화 시퀀스: `wordcloud_project/web/static/js/integrated_batch.js:1654` `DOMContentLoaded` → `renderIntegratedDataTree()`(1711행) → `loadWorkOrders()`(1712행).
- **배제됨 — `renderIntegratedDataTree()`(`integrated_batch.js:433`)**: 서버 호출이 전혀 없다. 정적 상수 `integratedDataStructure`(필드 매핑 설정, 로컬 객체)만 순회해 DOM을 만든다 — 데이터 호출 자체가 없으므로 로딩 지연의 원인이 될 수 없다.
  - 참고: 사용자가 언급한 "배치 이력" 패널을 채우는 함수와는 다른 함수다 — 이 화면에는 "필드 매핑 트리"와 "작업 이력 목록"이라는 서로 다른 두 목록이 있고, 사용자가 말한 "데이터 호출"은 후자(작업 이력)일 가능성이 높다고 보고 그쪽을 조사했다.
  - **오판 정정**: 처음에는 `GET /api/batch/list`(`wordcloud_project/src/routes/batch_routes.py:53`, `get_batch_list()`)가 이 화면의 목록 소스라고 가정했으나, `grep -rn "'/api/batch/list'"` 결과 이 엔드포인트는 `wordcloud_project/web/templates/wordcloud_preview.html:289`에서만 호출되고 있었다 — **배치 관리 화면(`integrated_batch.html`/`integrated_batch.js`)은 이 API를 쓰지 않는다.** 이 가정에서 출발해 `get_batch_list()`의 파일 I/O 루프(`batch_manager.py:18~48`, 배치별 `batch_summary.json` 파일을 열어 `display_name`을 읽는 부분)를 원인으로 지목할 뻔했으나, 실제 호출 경로가 아니므로 폐기.
  - **실제 목록 소스 — `loadWorkOrders()`(`integrated_batch.js:1316`)**: `GET /api/batch/work-orders` 1회 호출. 서버(`batch_routes.py:135~143`)는 `get_all_work_orders(limit=20)`(`batch_work_order_service.py:166~177`)을 호출하며, 이 함수는 `SELECT * FROM batch_work_orders ORDER BY created_at DESC, id DESC LIMIT 20` **단일 쿼리, 20건 상한**이다. `renderWorkOrders()`(`integrated_batch.js:1326`)는 응답을 그대로 테이블 행으로 렌더링할 뿐 행마다 추가 API를 부르는 N+1 패턴이 없다(코드 전체 확인, 반복문 안에 `fetch` 없음).
  - **부수 확인 — `/api/mappings/last`**(`api_routes.py:693~708`, DOMContentLoaded 초반에도 호출됨): 실측 결과 "마지막 저장된 컬럼 매핑"을 담은 단일 JSON 파일(`MAPPINGS_FILE`)을 통째로 읽어 반환하는 경량 조회로 확인됨(파일 크기 0바이트 시 조기 반환 분기도 있음) — "많은 데이터"의 후보에서 제외.
  - **화면 라우트 핸들러 자체 확인 — `ui_routes.py:63~66`**: `@ui_bp.route('/integrated_batch')` 핸들러는 `return render_template('integrated_batch.html')` 한 줄뿐, 템플릿에 넘기는 컨텍스트 데이터가 **전혀 없다**(kwargs 0개). 즉 페이지 셸 자체는 서버 쪽에서 아무 것도 계산·조회하지 않으며, 모든 데이터는 클라이언트가 로드 후 호출하는 `/api/batch/work-orders`·`/api/mappings/last` 두 API로만 들어온다 — 아래 가능성 3(템플릿 렌더 비용)은 이 화면에서는 배제된다.
- **미확정**: 위 조사 범위(화면 셸 + 클라이언트가 실제로 호출하는 API 2종) 안에서는 "많은 데이터를 불필요하게 호출"할 만한 코드를 찾지 못했다. 가능성:
  1. 사용자가 보는 지연이 이 화면이 아니라 다른 화면(예: `wordcloud_preview.html`의 `/api/batch/list`, 또는 배치 처리 자체의 SSE 스트림 `/api/batch/events`)일 가능성 — 화면 특정이 더 필요하다.
  2. ~~로컬 개발 DB 실측 시 `batch_work_orders`에 인덱스 부재 가능성~~ **배제됨** — `deploy_session_service.py:113~114`에 `idx_wo_status`·`idx_wo_created ON batch_work_orders (created_at DESC)`가 이미 존재함을 확인. 다만 실제 운영 DB의 `batch_work_orders` 행수 자체는 이번 조사에서 세지 않았다(쿼리에 `LIMIT 20`이 있어 인덱스가 있는 한 행수와 무관하게 빨라야 정상).
  3. ~~서버 기동·템플릿 렌더(Flask `render_template`) 자체의 비용~~ **배제됨** — 위 라우트 핸들러 확인 결과 컨텍스트 데이터 없이 정적 렌더만 수행. 남는 것은 네트워크/프록시 구간, 또는 브라우저 자체의 렌더링(DOM 생성) 비용인데 코드 검토로는 판단 불가.
- **반증 실험(다음 조사자를 위한 지침)**: 브라우저 개발자도구 Network 탭에서 `/integrated_batch` 진입 시 실제로 어떤 요청이 뜨는지, 각 요청의 소요 시간이 얼마인지 캡처하면 이 가설(=원인을 못 찾음)이 맞는지 즉시 반증된다 — `/api/batch/work-orders`·`/api/mappings/last` 둘 다 20ms 이내로 끝나면 "코드에 원인 없음"이 확정되고 남는 후보는 화면 오인(가능성 1)뿐이며, 반대로 둘 중 하나가 느리면 그 응답에 걸리는 시간을 서버 로그와 대조해야 한다.

## 3. 수정 방안 — 계측 신설(2026-08-20 3차)

§2에서 **이 화면의 코드 후보가 전부 배제**되었다. 즉 "미리 구현해 둘 수정"이 존재하지 않는다 — 짐작으로 코드를 고치면 원인이 아닌 곳을 바꾸는 것이 된다. 대신 다음 실행 1회로 원인이 드러나도록 계측을 심었다(로그·콘솔 출력만, 동작 불변).

| 심은 곳 | 남는 것 | 이 계획서에서 무엇을 가르는가 |
|---------|---------|------------------------------|
| `utils/perf.py` `install_request_timing`(전역, `web/app.py`) | **모든** 요청의 `method·path·status·bytes·ms`(`STAGE:PERF_REQ`) | §2 가능성 1(다른 화면·다른 요청 오인)을 판별하는 유일한 수단 — 우리가 후보로 꼽지 않은 요청과 정적 자원까지 전부 보인다 |
| `batch_routes.work_orders` — `work_orders.query` / `work_orders.display_name` | 구간 ms | 20_07이 추가한 `batch_summary.json` 파일 읽기 루프(최대 20회)가 지연에 기여하는지. 조사 당시엔 없던 코드라 §2가 검토하지 못한 신규 후보다 |
| `web/static/js/perf_probe.js`(base.html 전역) | 모든 fetch·XHR 왕복시간 + 페이지 nav 타이밍(ttfb/htmlDownload/domContentLoaded/load) | 서버 ms와 대조해 **서버 / 네트워크 / 브라우저** 중 어디인지. 문서 자체(HTML·스크립트 파싱)가 느린 경우도 여기서 잡힌다 |
| `integrated_batch.js` — `renderIntegratedDataTree` span, `loadWorkOrders:total` / `loadWorkOrders:render` mark | 요청 이후 DOM 조립 ms | §2가 "서버 호출 없음"으로 배제했던 트리 렌더의 **브라우저 비용**을 처음으로 실측한다(코드로는 판단 불가라고 적어둔 부분) |

판정 규칙:
- 어떤 요청도 느리지 않고 `nav`의 `load`만 크다 → 문서·정적 자원 로딩이 원인.
- `renderIntegratedDataTree` span이 크다 → 필드 매핑 트리 DOM 조립이 원인(§2가 배제한 "서버 호출 없음"과 모순되지 않는다 — 브라우저 비용이라 코드 검토로는 안 보였던 것).
- `PERF_REQ`에 이 화면과 무관한 무거운 요청이 찍힌다 → §2 가능성 1(화면 오인)이 확정.
- 서버 ms ≪ 브라우저 fetch ms → 네트워크·프록시 구간.

## 4. 롤백 계획

- 계측만 제거하려면 `web/templates/base.html`의 `perf_probe.js` 로드 1줄, `web/app.py`의 `install_request_timing(app)` 2줄, `batch_routes.py`·`integrated_batch.js`의 span/mark를 지우면 된다. 기능 코드는 건드리지 않았으므로 되돌림 위험 없음.

## 5. 결과 (구현 완료 후 기재)

- **원인 미확정 유지** — 이 계획서는 아직 무엇도 고치지 않았다. 바뀐 것은 "다음 실행에서 원인이 반드시 드러나게 만든 것"뿐이다.
- 계측 구현 실체와 자동 검증(T1~T6, 14 passed)은 20_09 §3.3·§6-2에 공용으로 기재했다(같은 계측 모듈을 두 계획서가 함께 쓴다).

## 6. 영향도 분석

- 변경 파일: `utils/perf.py`(신규), `web/app.py`, `web/templates/base.html`, `src/routes/batch_routes.py`, `web/static/js/integrated_batch.js`, `web/static/js/perf_probe.js`(신규).
- 기능 코드의 반환값·분기는 변경 없음. 계측 실패가 화면·요청을 깨지 않도록 서버·브라우저 양쪽 모두 예외 격리.

## 7. 테스트/검증 계획 — 사용자 실측 절차(PND)

1. F12 → Console 을 연 채 좌측 메뉴 "📄 통합데이터 생성"(`/integrated_batch`) 진입.
2. 콘솔의 `[PERF]` 줄을 본다: `fetch GET /api/batch/work-orders`, `fetch GET /api/mappings/last`, `span renderIntegratedDataTree`, `mark loadWorkOrders:render`, `nav ...`.
3. 서버 콘솔 또는 `logs/pipeline/pipeline_*.log`에서 같은 시각의 `STAGE:PERF_REQ` 줄 전체를 훑는다 — **여기서 목록에 없던 요청이 보이면 그게 범인**이다.
4. §3의 판정 규칙에 대입한다. 어느 쪽이든 이 한 번으로 §2의 "원인 미확정"이 종료된다.
5. 필요하면 콘솔에 `__perf.report()`를 입력해 수집된 표를 한 번에 본다.

## 8. 리스크 및 제약

- 서버 무단 기동 금지(DL-12)로 실측 재현을 하지 못해 이 계획서는 "무엇이 원인이 아닌지"만 확정한 상태다 — 실제 원인 확정과 수정은 후속 조사 이후.
- **계측이 원인을 못 잡을 수 있는 경우**: 지연이 서버 기동 직후 1회성(모델 적재·최초 import)이라면 두 번째 접속부터는 재현되지 않는다. §7 실측 시 **서버를 켜고 처음 들어간 1회**와 **새로고침 2~3회째**를 나눠 기록하면 이 경우도 구분된다.
- **정적 분석은 사실상 소진됨**: 이 화면이 실제로 부르는 API 2종(`/api/batch/work-orders`, `/api/mappings/last`) 모두 경량 확인, 화면 라우트 자체도 서버 데이터 없음 확인, 인덱스도 존재 확인 — 코드만으로 더 좁힐 수 있는 후보가 남아 있지 않다. 다음 단계는 코드 재검토가 아니라 **사용자의 실측(Network 탭) 또는 화면 재확인**이어야 한다.
