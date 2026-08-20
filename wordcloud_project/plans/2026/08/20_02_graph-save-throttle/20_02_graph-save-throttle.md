# 계획서 — 그래프 저장 후반부 저속화에 대한 원인 불문 완화(적응형 동시처리 스로틀)

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: D
> 선행: 12_01(그래프 저장 기능 최초 구현)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 — 코드는 사용자 요청으로 계획서보다 먼저 구현됨(§5) |
| 2026-08-20 | §2 | 독립 검증 반영 — 두 번째 코드 블록의 라인 인용을 정정(`:2030-2056`→`:2080-2105`). 20_01(재개 지원 확장)이 `saveGraph()`에 재개 사전 로드 로직을 추가로 삽입하면서 첫 블록(`_workerCount` 등 상태 변수 선언, `:1917-1920`)보다 뒤쪽 코드가 약 50줄 밀림. 첫 블록 위치는 변동 없음(그래프 세션 상태 변수는 `let sessionId` 선언보다 앞이라 영향 없음) |

## 1. 배경 및 목적

사용자가 "그래프 저장"을 대량 실행하면 후반부로 갈수록 눈에 띄게 느려지는 현상을 반복 보고했다. 코드 정적 검토로 확정 가능한 원인을 찾지 못한 상태에서, 사용자가 직접 제시한 방향 — "원인을 특정하지 못해도 예상 동작(속도 저하)에 대한 대비를 먼저 만들고, 그래도 느려지면 그건 다른 원인이니 그때 가서 새로 조사한다" — 을 채택해, 원인 불문으로 부하 자체를 줄이는 자동 스로틀 장치를 넣는다. 이 장치가 효과가 있는지 없는지 자체가 다음 원인 조사의 단서가 된다(§7).

## 1-1. 원인 조사 경과(참고 — 이 계획서의 수정 대상 아님)

- **배제됨**: matplotlib figure 누수. `wordcloud_project/src/services/perspective_service.py`의 추이 그래프 렌더 함수(3600행대, `_save_trend_chart_to_path`)는 `fig.savefig()` 후 `finally`에서 `plt.close(fig)`를 호출한다(3768행대) — 누적 메모리 누수 아님.
- **배제됨**: 전체 배치 재적재. `load_employee_batch()`(`perspective_service.py:1843`)는 직원 1명만 인덱스 쿼리로 조회(`WHERE e.employee_id = ?`, 1867행)하며, 주석에 "17,000명 전체 적재로 인한 메모리 폭증을 피하기 위함(0619_02)"이라고 명시된 기존 최적화 — 원인 아님.
- **미확정 후보(추가 조사 필요, 이 계획서 범위 밖)**: (a) `saveGraph()`의 청크 루프가 `successData` 배열에 결과를 계속 push만 하고 비우지 않는 클라이언트(브라우저) 측 누적, (b) 청크당 4-way 병렬 처리가 장시간 이어질 때의 SQLite 연결 열기/닫기(`_get_eval_conn()`) 경합.

## 2. 변경 설계

- **적응형 동시처리 스로틀**: 항목(직원) 1건 처리 시간을 `performance.now()`로 측정해 최근 20건의 롤링 윈도우에 보관(`_itemDurations`). 처음 5건의 평균을 "기준 속도"(`_baselineAvgMs`)로 고정. 매 청크(50건) 처리 후 최근 평균이 기준 대비 3배를 넘고 현재 동시 처리 수(`_workerCount`, 초기값 4)가 1보다 크면 1단계 낮춘다(최소 1).
- **가시성 확보**: 진행률 패널에 "직전 항목 처리시간 / 최근 평균 / 현재 동시 처리 수"를 상시 표시해, 느려지는 상황 자체가 "멈춘 것처럼" 보이지 않게 한다. 스로틀이 발동하면 `⚠️ 처리 속도 저하 감지(평균 XXXms → YYYms) — 동시 처리 수를 N→M로 조정합니다` 로그 줄을 남긴다.
- **적용 범위**: 이번 구현은 "그래프 저장"(`saveGraph()`)에만 적용했다. "제출용 저장"(`saveDeploy()`)은 구조가 동일(같은 청크·워커 패턴)하지만 이번 계획서에는 포함하지 않았다 — 필요 시 별도 후속 작업으로 동일 패턴을 이식한다(§8).

```javascript
// wordcloud_project/web/templates/perspective_test.html:1917-1920 (saveGraph() 내부, let total = 0; 바로 아래)
let _workerCount = 4;
let _itemDurations = [];
let _baselineAvgMs = null;
let _lastItemMs = null;
```

```javascript
// wordcloud_project/web/templates/perspective_test.html:2080-2105 (processOne 종료부 + 청크 완료 후, 20_01 반영 후 기준)
_lastItemMs = performance.now() - _t0;
_itemDurations.push(_lastItemMs);
if (_itemDurations.length > 20) _itemDurations.shift();
if (_baselineAvgMs === null && _itemDurations.length >= 5) {
    _baselineAvgMs = _itemDurations.reduce((a, b) => a + b, 0) / _itemDurations.length;
}
// ... 워커 루프는 _workerCount 를 사용(고정 WORKER_COUNT=4 상수 제거)
if (_baselineAvgMs !== null && _itemDurations.length >= 5 && _workerCount > 1) {
    const _recentAvg = _itemDurations.reduce((a, b) => a + b, 0) / _itemDurations.length;
    if (_recentAvg > _baselineAvgMs * 3) {
        const _prev = _workerCount;
        _workerCount = Math.max(1, _workerCount - 1);
        addLine(`⚠️ 처리 속도 저하 감지(평균 ${Math.round(_baselineAvgMs)}ms → ${Math.round(_recentAvg)}ms) — 동시 처리 수를 ${_prev}→${_workerCount}로 조정합니다`, 'fail');
    }
}
```

## 3. 변경 파일 목록

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `wordcloud_project/web/templates/perspective_test.html` | 수정 | `saveGraph()` 청크 루프가 `WORKER_COUNT=4` 고정, 진행률 패널에 경과 시간만 표시 | 항목별 처리시간 측정 → 롤링 평균이 기준의 3배 초과 시 동시 처리 수 자동 감소, 진행률 패널에 직전/평균 처리시간·현재 동시 처리 수 노출 |

## 4. 효과 예상 (정량 가능 시)

- 정량 실측 없음(§1-1에서 밝혔듯 원인 미확정이라 "몇 % 개선"을 계산할 근거가 없음). 기대 효과는 정성적: (a) 서버/네트워크 경합이 원인이면 동시 처리 감소로 완화, (b) 그래도 느려지면 동시 처리 1까지 낮춘 뒤에도 저속화가 재현된다는 로그가 남아 "서버 동시성 경합은 원인이 아니다"라는 반증 근거를 다음 조사에 제공.

## 5. 결과 (구현 완료 후 기재)

- **적용된 변경**: 위 §2·§3 그대로 적용 완료(2026-08-20).
- **검증 결과**: `node --check`로 해당 인라인 `<script>` 블록 전체 구문 검사 통과(스크립트 블록 1개, `web/templates/perspective_test.html:525`). **실제 브라우저 실행 검증은 미수행** — 서버 무단 기동 금지로 사용자 실행 확인 대기(PND). 다음에 그래프 저장을 대량 실행할 때 진행률 패널의 "동시 처리" 숫자가 실제로 줄어드는지, 그리고 저속화 체감이 완화되는지 확인 필요.

## 6. 영향도 분석

- **변경 파일**: `wordcloud_project/web/templates/perspective_test.html`(`saveGraph()` 함수 내부만, 다른 함수 미변경)
- **영향 범위**: `saveGraph()` 단일 함수 내 지역 변수만 추가·수정 — 서버 API, DB 스키마, 다른 화면과 무관. DL-8(공통 모듈) 해당 없음(이 화면 전용 함수).

## 7. 테스트/검증 계획

- 실제 대량 실행(수십~수백 명) 시 진행률 패널에 표시되는 처리시간이 실제 네트워크 탭 타이밍과 일치하는지 확인.
- 저속화가 재현될 때 `⚠️ 처리 속도 저하 감지` 로그가 실제로 뜨고 동시 처리 수가 줄어드는지 확인.
- 동시 처리 수를 1까지 낮춘 뒤에도 저속화가 계속되면, 그 로그를 근거로 §1-1의 미확정 후보(클라이언트 배열 누적/SQLite 연결 경합) 중 서버 측 요인은 배제하고 클라이언트 측을 우선 조사하는 후속 계획서를 새로 연다.

## 8. 리스크 및 제약

- 원인을 특정하지 않은 완화책이므로 "느려지는 진짜 이유"는 여전히 미상 — 이 계획서만으로 §1-1 미확정 후보 조사를 종결한 것은 아니다.
- 동시 처리 수를 낮추는 것은 처리 자체를 늦출 수 있다(안전 vs 속도 트레이드오프) — 사용자가 이 트레이드오프를 명시적으로 요청했으므로 채택.
- `saveDeploy()`(제출용 저장)에는 아직 미적용 — 동일 저속화가 보고되면 후속 계획서로 이식.
