# 계획서 — 연도별 긍정/부정 추이 라인 그래프 이미지 생성 및 「그래프 저장」 버튼 추가

> 상태: Todo | 작성일: 2026-08-12
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 없음

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-12 | 전체 | 최초 작성 |

---

## 0. 문서 규약

- 이 문서의 모든 경로는 **저장소 루트 `D:/dev/wordcloud/` 기준**이다.
- 축약 규약: `WP/` = `D:/dev/wordcloud/wordcloud_project/`
- 인용한 코드 위치는 모두 `파일:라인` 으로 표기하며, 작성 시점(2026-08-12) 워킹트리 기준 실측이다.

---

## 요구사항 원자화

| # | 원자 질문 | 기대 (사용자 확인) | 작업 후 답 (근거) |
|---|-----------|--------------------|-------------------|
| 1.1 | 새로 만드는 그래프는 막대가 아니라 **선(line)** 으로 그리는가? | Y | 미검증(미착수) |
| 1.2 | 선은 **긍정 1개 + 부정 1개, 총 2개**인가? | Y | 미검증(미착수) |
| 1.3 | X축은 **평가 연도**이고, 사용자가 화면에서 체크한 연도만 표시되는가? (예: 2024·2026만 체크하면 점 2개) | Y | 미검증(미착수) |
| 1.4 | 그래프 대상은 **선택한 직원 1명 기준**인가? | Y | 미검증(미착수) |
| 2.1 | 그래프를 만들 때 **비율 산출 지표를 사용자가 선택**할 수 있는가? (긍/부정 단어 수, 긍/부정 문장 수 등) | Y | 미검증(미착수) |
| 2.2 | 그래프를 만들 때 **표시 단위(백분율 % / 수량)** 를 사용자가 선택할 수 있는가? | Y | 미검증(미착수) |
| 2.3 | 백분율 모드의 분모는 **긍정+부정**(중립 제외)인가? | Y | 미검증(미착수) |
| 3.1 | 그래프는 화면에만 뜨는 게 아니라 **PNG 파일로 저장**되는가? | Y | 미검증(미착수) |
| 3.2 | 저장 위치는 제출용 저장과 같은 `outputs/배포/` 아래의 **별도 폴더**인가? | Y | 미검증(미착수) |
| 3.3 | 파일명은 **직원 사번(또는 이름_사번)** 으로 시작하는가? | Y | 미검증(미착수) |
| 3.4 | 제출용 저장처럼 **직원 여러 명(CSV·전체)** 도 일괄 생성 가능한가? | Y | 미검증(미착수) |
| 3.5 | 생성된 그래프가 **결과물 ZIP 다운로드에 포함**되는가? | Y | 미검증(미착수) |
| 4.1 | 「그래프 저장」 버튼은 **「제출용 저장」 버튼의 바로 우측**에 있는가? | Y | 미검증(미착수) |
| 4.2 | 기존 「제출용 저장」 동작은 **변경되지 않는가**? | Y | 미검증(미착수) |
| 5.1 | 이 작업으로 긍정/부정 **판정 로직(문장·단어 점수)** 이 바뀌는가? | N (집계·표시만) | 미검증(미착수) |

> 작업 후 각 행의 `작업 후 답` 을 실측 근거(`파일:라인`, 테스트명, 로그)로 채운다. 기대와 답이 불일치하면 Done 불가.

---

## 1. 배경 및 목적

인사처는 직원별 납품 산출물로 **긍정 워드클라우드 · 부정 워드클라우드 · 연도별 긍/부정 추이 그래프** 3종을 사번명 이미지 파일로 받기를 원한다. 앞의 2종은 「제출용 저장」이 이미 생성하지만(§2-2), **연도별 추이 그래프는 시스템에 존재하지 않는다.**

현재 화면에서 긍정/부정 비율을 볼 수 있는 곳은 매트릭스 셀 안의 CSS 막대(가로 바)뿐이다 — `WP/web/templates/perspective_test.html:165-166`(`.metric-bar-bg`/`.metric-bar-fill` 스타일), 렌더는 `:2827-2829`. 이것은 **연도 간 추이를 잇는 선이 아니며 이미지 파일로도 저장되지 않는다.** 인사처 요구(연도별 선 그래프)를 충족하려면 신규 구현이 필요하다.

또한 저장소 전체에서 라인 차트를 그리는 코드는 없다. `matplotlib` 의 `plt.figure` 사용처는 `WP/src/modules/wordcloud_generator.py:192, 262` 두 곳뿐이고 둘 다 워드클라우드 이미지 렌더용이다. → **차트 생성 함수는 신규 생성 필요.**

**목적**: 선택 연도별 긍정/부정 추이를 라인 차트 PNG로 생성하고, 「제출용 저장」과 동일한 방식(직원별 파일·일괄 처리·ZIP 포함)으로 저장하는 「그래프 저장」 버튼을 추가한다.

---

## 2. 현재 시스템 분석 (실측)

### 2-1. 화면 — 버튼과 조건 선택 UI

파일: `WP/web/templates/perspective_test.html`

| 위치 | 내용 |
|------|------|
| `:324` | `<button id="btnGenerateMatrix" class="btn-primary" onclick="generateMatrix()" disabled>매트릭스 저장</button>` |
| `:325` | `<button id="btnSaveDeploy" class="btn-success" onclick="saveDeploy()" disabled>제출용 저장</button>` |
| `:326` | `<button id="zipDownloadBtn" class="btn-secondary" style="display:none;..." onclick="downloadDeployZip()">⬇️ 결과물 ZIP</button>` — 평소 숨김, 저장 완료 후 노출 |
| `:281` | 행 필드 선택 `<select id="rowFieldSelect">` — 옵션이 **`evaluation_date__year`(평가 연도) 하나뿐** |
| `:282` | `<div class="options" id="rowValuesContainer">` — 연도 체크박스가 동적 생성되는 컨테이너 |
| `:602-605` | `function getSelectedRowValues()` → `.rowValueCb:checked` 의 `value` 배열 반환 (선택 연도 문자열 목록) |
| `:607-610` | `function isRowCombineAll()` → 라디오 `rowOutputMode` 가 `combined` 인지 |
| `:682-684` | `function getOutputMode()` → 항상 `'real'` 반환(실명/실사번 출력 모드) |
| `:3338-3352` | `function getWcOptions()` → 배경색·크기(`800x600` 등)·max_words 등 워드클라우드 옵션 |

→ **신규 버튼은 `:325` 와 `:326` 사이에 삽입**해야 "제출용 저장 우측" 요구를 만족한다.
→ X축 데이터는 `getSelectedRowValues()` 가 이미 제공하므로 **연도 선택 UI를 새로 만들 필요가 없다.**

### 2-2. 제출용 저장의 실제 동작

프론트: `saveDeploy()` — `WP/web/templates/perspective_test.html:1474`

1. `:1482-1531` 대상 결정(`_csvEmployeeIds` / `allEmployeesCheck` / `employeeSelect`)과 요청 body 구성(`row_field`, `row_values`, `output_mode`, `include_name`, `include_id`, 워드클라우드 옵션, `batch_title`)
2. `:1593-1596` `btnGenerateMatrix` · `btnSaveDeploy` 비활성화
3. `:1599` `showBusyOverlay('제출용 저장 중… …')` — **전면 차단 오버레이**
4. `:1656` `POST /api/perspective/deploy-session/start` 로 세션 생성 → `:1688` 청크 폴링 루프 → `:1702` `WORKER_COUNT = 4` 병렬
5. `:1711` 직원 1명씩 `POST /api/perspective/matrix/save-deploy`
6. `:1791` `downloadDeployZip()` 로 결과물 ZIP 다운로드

백엔드 라우트: `WP/src/routes/perspective_routes.py:463` `api_save_deploy()`
- `:474-475` `employee_id` / `employee_ids` / `all_employees` 중 하나 필수, 없으면 400
- `:476-477` `_is_admin()` 아니면 401
- `:482-499` options 조립(`row_values`, `output_mode`, `include_name`, `include_id`, `batch_title` 등)
- `:501` `_setup_korean_font()` 를 **분기 진입 전 1회** 호출
- `:511`, `:534` 직원별 `save_to_deploy(...)` 호출

서비스: `WP/src/services/perspective_service.py:3230` `save_to_deploy(unified_data, employee_id, row_field, col_mode, analysis_type, options, request=None, request_id='')`
- `:3240` `_resolve_to_pseudo()` 로 내부 가명 ID 확정 → `:3247-3264` `output_mode=='real'` 이면 실명/실사번으로 `deploy_name` 조립, 아니면 가명 ID
- `:3275` `safe_name = re.sub(r'[\\/*?:"<>|]', '_', str(deploy_name))`
- `:3278` `os.makedirs(DEPLOY_OUTPUT_DIR, exist_ok=True)` — `DEPLOY_OUTPUT_DIR` 정의는 `:72` `os.path.join(OUTPUTS_DIR_PATH, '배포')`, `OUTPUTS_DIR_PATH` 는 `WP/src/config/settings.py:43`
- `:3289-3299` `_save_wc(wf, scores, suffix, filename)` — `DEPLOY_OUTPUT_DIR/<suffix>/<filename>.png` 로 저장하고 `/outputs/<상대경로>?v=<ts>` URL 반환
- `:3314-3317` 파일명 = `f"{safe_name}_통합"`, 폴더 = `통합` / `긍정` / `부정` 세 개
  → **실제 산출 파일은 `outputs/배포/긍정/<사번>_통합.png` 형태**다. 인사처가 예로 든 `110110_긍정.png` 와 파일명 규칙이 다르다(폴더가 극성을 구분). §7 결정 D-1 참조.
- `:3358` `_filter_items_by_row(all_items, row_field, row_values)` 로 선택 연도만 남김
- `:3364` `_generate_wc_for_items(filtered_items, '통합')` — **선택 연도 전체를 하나로 합쳐 1세트만 생성**한다. 연도별 분리 산출은 하지 않는다.
- `:3366-3385` 결과 dict(`combined`/`positive`/`negative` URL, 문장 상세 등)
- `:3392` `_append_to_deploy_manifest(result, ...)`

### 2-3. 집계에 쓸 수 있는 원천 데이터

| 지표 원천 | 위치 | 형태 |
|---|---|---|
| 연도 추출 | `perspective_service.py:2391-2395` `_extract_row_values()` → `:1602-1621` `_get_eval_field_value()` | `evaluation_date__year` 는 `normalize_eval_date()` 로 정규화 후 앞 4자리 문자열(`'2024'`). 정수 `2025` 같은 입력도 처리(과거 전건 탈락 버그 수정 이력이 주석에 기재됨) |
| 연도 필터 | `perspective_service.py:2398-2407` `_filter_items_by_row(all_items, row_field, row_values)` | `row_values` 가 비면 전체 반환 |
| 문장 극성 | `perspective_service.py:3337-3355` (`save_to_deploy` 내부) | `_get_sentence_level_scores()` 결과를 순회하며 `sent_score > 0` → 긍정, `< 0` → 부정, `== 0` → 중립으로 분류. **중립이 별도 버킷으로 분리됨** |
| 문장 점수 계산 | `perspective_service.py:2190` `_get_sentence_level_scores(doc, threshold=0.20, weight=2.0, corrections=None, sentence_cache=None, field=None)` | `(문장, 점수, pos, neg, neutral)` 튜플 리스트 |
| 단어 빈도 | `perspective_service.py:2111-2161` `extract_words(filtered_evaluations, wordcloud_pos, remove_profanity)` | `{'word_frequency': {단어: 빈도}, ...}` |
| 단어 극성 점수 | `perspective_service.py:2274-2308` `calculate_word_scores(filtered_evaluations, word_frequency, threshold=0.20, weight=2.0, corrections_map=None)` | `{단어: 평균점수}`. **비용 주의**: 단어마다 전체 평가를 순회하므로 대략 O(단어수 × 평가수 × 문장수) |
| 단어 극성 분류 | `perspective_service.py:3312-3313` | `wf_positive = score >= 0`, `wf_negative = score < 0` → **점수 0(중립)이 긍정 쪽에 포함**된다. 문장 기준(§위)과 경계 규칙이 다르다 |
| 감정 보정 | `perspective_service.py:2164` `_load_corrections_map(employee_id)` | 사용자 수정 반영 맵 |

### 2-4. 갤러리·ZIP 연동 현황

- `perspective_service.py:3129-3174` `_append_to_deploy_manifest()` → `gallery_db_service.upsert_entry(entry)`. `entry["source"] = "deploy"`(`:3146`), `entry["images"] = {combined, positive, negative}`(`:3161-3165`)
- `WP/src/services/gallery_db_service.py:39` `images TEXT` (JSON 문자열), `:100` `json.dumps(entry.get('images') or {})` → **키 추가는 스키마 변경 없이 가능**
- 갤러리 UI 는 3종을 **하드코딩**: `WP/web/templates/deploy_gallery.html:875-877`(칩 3개), `:2150-2151`, `:2207`, `:2216`, `:2234`(`labelMap = { combined: '통합', positive: '긍정', negative: '부정' }`) → 그래프를 갤러리에 노출하려면 이 목록 확장이 필요
- ZIP 다운로드 라우트는 `WP/src/routes/perspective_routes.py:344-353` 에서 `combined`/`positive`/`negative` **키를 하드코딩**해 수집 → 그래프 포함하려면 키 추가 필요

### 2-5. 이미지 생성 기반

- `perspective_service.py:2-3` `import matplotlib` / `matplotlib.use('Agg')` — 헤드리스 렌더 이미 설정됨
- `perspective_service.py:3088-3107` `_setup_korean_font()` — **Windows 한정**으로 `malgun.ttf` 등을 `plt.rcParams['font.family']` 에 등록. 실패해도 예외를 삼킴(`:3106-3107`). 리눅스 배포 시 한글 깨짐 가능 → §7 리스크

---

## 3. 구현 상세

### 3-0. 그래프 형태 (합의된 시각 사양)

```
 직원 110110 — 연도별 긍정/부정 비율            지표: 긍정/부정 문장 수 · 단위: %
 %
100 ┤
 80 ┤        ●────────────●                     ● 긍정  (초록 #28a745)
 60 ┤   ●────╯             ╰───●                ▲ 부정  (빨강 #dc3545)
 40 ┤
 20 ┤   ▲────╮        ╭────▲
  0 ┤        ▲────────╯                         분모 = 긍정+부정 (중립 제외)
    └────┬────────┬────────┬────────┬──          각 점 위 라벨: 78.2% (수량 모드면 156)
       2023     2024     2025     2026
                평가 연도 (화면에서 체크한 연도만)
```

- 계열 2개: 긍정(초록 `#28a745`) · 부정(빨강 `#dc3545`) — 매트릭스 셀 막대에서 쓰는 색과 동일(`perspective_test.html:2827`, `:2829`)
- X축: 선택 연도 오름차순. 점(marker) + 실선, 각 점에 값 라벨
- Y축: `%` 모드는 0~100 고정, `수량` 모드는 자동 스케일(0 기준)
- 제목: `{deploy_name} — 연도별 긍정/부정 {지표명}`, 부제에 지표·단위 명시
- 기본 크기 800×600 (제출용 저장의 `getWcOptions()` 크기 옵션과 동일 기본값)

### 3-1. 백엔드

파일: `WP/src/services/perspective_service.py` (모두 **신규 함수** — 동일 목적 함수가 없음을 §1에서 확인)

**(a) 집계 함수**

```python
def aggregate_sentiment_trend(items, row_field, row_values, metric, options, corrections_map=None):
    """연도(row_value)별 긍정/부정 집계값을 반환한다.
    반환: {'rows': ['2024', '2026'],
           'positive': [n1, n2], 'negative': [m1, m2],
           'metric': metric, 'skipped_rows': [...]}
    """
```

- 연도별 분리: `row_values` 각 값마다 `_filter_items_by_row(items, row_field, [value])` (`perspective_service.py:2398`) 를 호출해 부분집합을 만든다. `row_values` 가 비어 있으면 `_extract_row_values()`(`:2391`) 로 실제 존재하는 연도를 수집해 오름차순 사용.
- 지표별 산식 (§3-1(b))
- 데이터가 0건인 연도는 `skipped_rows` 에 기록하고 계열값은 `None`(선 끊김)으로 둔다.

**(b) 지표 정의 — `metric` 파라미터**

| `metric` 값 | 화면 표기 | 산식 | 근거 함수 |
|---|---|---|---|
| `sentence_cnt` **(기본)** | 긍정/부정 문장 수 | 연도별 items 를 `_get_sentence_level_scores()` 로 문장 분해 후 `score > 0` 개수 / `score < 0` 개수 | `perspective_service.py:2190`, 분류 규칙은 `:3348` 과 동일하게 재현 |
| `word_freq` | 긍정/부정 단어 수(빈도 합) | `extract_words()` → `calculate_word_scores()` → `sum(freq for w in wf_positive)` / `wf_negative` | `:2111`, `:2274`, 분류 `:3312-3313` |
| `word_uniq` | 긍정/부정 단어 종류 수 | `len(wf_positive)` / `len(wf_negative)` | 동일 |
| `word_weighted` | 감정 가중 단어량 | `Σ(빈도 × |word_score|)` 를 극성별로 합산 | 동일 |
| `sentence_power` | 감정 강도 합 | 문장별 `Σ|score|` 를 극성별로 합산 | `:2190` |

- **경계 처리 명시**: 문장 기준(`sentence_cnt`, `sentence_power`)은 점수 0을 중립으로 제외한다. 단어 기준(`word_*`)은 현행 코드가 `score >= 0` 을 긍정으로 묶으므로(`:3312`) **중립 단어가 긍정에 포함**된다. 이 규칙은 워드클라우드 이미지와 동일해야 하므로 **바꾸지 않는다.** 대신 그래프 이미지 하단과 UI 툴팁에 "단어 기준은 중립 단어를 긍정에 포함(워드클라우드와 동일 기준)" 을 표기한다.
- 단어 기준 지표는 `calculate_word_scores()` 비용이 크다(§2-3). 연도별로 items 가 분할되므로 총 비용은 전체 1회 호출과 유사하나, **연도 수가 많으면 선형 증가**한다.

**(c) 단위 변환 — `unit` 파라미터**

- `pct`: `pos_pct = pos / (pos + neg) * 100`, `neg_pct = neg / (pos + neg) * 100`. `pos + neg == 0` 이면 해당 연도는 `None`(선 끊김) + `skipped_rows` 기록
- `count`: 원값 그대로

**(d) 차트 렌더 함수**

```python
def _save_trend_chart_to_path(trend, output_path, options):
    """aggregate_sentiment_trend 결과를 라인 차트 PNG로 저장. 성공 시 True."""
```

- `matplotlib.pyplot` 사용(`Agg` 백엔드는 `perspective_service.py:2-3` 에서 이미 설정됨)
- 호출 전 `_setup_korean_font()`(`:3088`) 가 라우트에서 1회 실행되어 있어야 한다(`perspective_routes.py:501` 과 동일 패턴)
- `plt.close(fig)` 로 반드시 해제(파일 디스크립터·메모리 누수 방지)

**(e) 저장 함수**

```python
def save_trend_graph_to_deploy(unified_data, employee_id, row_field, row_values,
                               metric, unit, options, request_id=''):
    """직원 1명의 추이 그래프를 outputs/배포/그래프/ 에 저장하고 결과 dict 반환."""
```

- `save_to_deploy`(`:3230`) 의 이름 결정 로직(`:3240`, `:3247-3264`, `:3275`)을 **그대로 재사용**해 동일한 `safe_name` 을 얻는다(같은 직원의 워드클라우드와 파일명 앞부분이 일치해야 인사처가 짝을 지을 수 있다).
- 저장 경로: `DEPLOY_OUTPUT_DIR/그래프/{safe_name}_긍부정그래프.png` (`DEPLOY_OUTPUT_DIR` = `outputs/배포`, `:72`)
- 반환: `{'name': deploy_name, 'timestamp': ts, 'graph': '/outputs/배포/그래프/....png?v=<ts>', 'metric': metric, 'unit': unit, 'rows': [...], 'skipped_rows': [...]}`
- 갤러리 등록: `_append_to_deploy_manifest()`(`:3129`) 를 참고한 별도 함수로 `source='graph'`, `images={'graph': url}` 행을 upsert 한다. `gallery_db_service.py:39, :100` 상 스키마 변경 불필요.

**(f) 라우트** — `WP/src/routes/perspective_routes.py`

```
POST /api/perspective/matrix/save-graph
```

| 항목 | 내용 |
|---|---|
| 요청 | `employee_id` **또는** `employee_ids`(배열) **또는** `all_employees:true` (기존 `api_save_deploy` `:467-475` 와 동일 규약) + `row_field`(기본 `evaluation_date__year`) · `row_values`(선택 연도 배열) · `metric` · `unit` · `output_mode` · `include_name` · `include_id` · `batch_title` · `width` · `height` |
| 인증 | `_is_admin()` 아니면 401 (`:476-477` 와 동일) |
| 사전 처리 | `_setup_korean_font()` 1회 호출 (`:501` 과 동일 위치 규약) |
| 데이터 로딩 | `load_employee_batch(eid)` (`perspective_service.py:1834`), 전체 대상은 `list_all_employee_ids()` (`:2055`) |
| 응답 | 단건 `{success, name, graph, metric, unit, rows, skipped_rows}` / 배치 `{success, results:[...], total, batch:true}` |
| 오류 | 대상 없음 400 · 해당 연도 평가 0건 400(메시지에 연도 명시) · 렌더 실패 500 |

**(g) ZIP 포함** — `WP/src/routes/perspective_routes.py:344-353` 의 URL 수집부에 `result['graph']` 키를 추가한다(현재 `combined`/`positive`/`negative` 만 수집).

### 3-2. 프론트엔드

파일: `WP/web/templates/perspective_test.html`

**(a) 버튼 추가** — `:325`(제출용 저장)와 `:326`(결과물 ZIP) **사이**에 삽입

```html
<button id="btnSaveGraph" class="btn-primary" onclick="openGraphOptions()" disabled>📈 그래프 저장</button>
```

- 활성/비활성 조건은 `btnSaveDeploy` 와 동일하게 처리한다. 현재 활성화 로직은 `:973`(`const btnGen = document.getElementById('btnGenerateMatrix')`) 부근에 있으므로 같은 자리에서 `btnSaveGraph` 도 함께 토글한다.

**(b) 옵션 선택 UI** — `openGraphOptions()`

- 버튼 클릭 시 작은 인라인 패널(또는 기존 모달 패턴)을 열어 아래 2개를 받는다.
  - 지표 `<select id="graphMetric">`: 문장 수(기본) / 단어 수(빈도) / 단어 종류 수 / 감정 가중 단어량 / 감정 강도 합
  - 단위 `<select id="graphUnit">`: 백분율(%) (기본) / 수량
- 선택값은 기존 프리셋 저장 패턴(`_autoSavePageState`, `:3511` 부근)에 맞춰 `localStorage` 에 보존한다.
- 패널 하단에 대상 연도 요약을 표시: `getSelectedRowValues()`(`:602`) 결과를 그대로 보여주고, **1개 이하이면 "연도를 2개 이상 선택해야 선으로 이어집니다" 경고**를 띄운다(생성 자체는 허용).

**(c) 저장 실행** — `saveGraph()`

- `saveDeploy()`(`:1474-1531`)의 대상 결정·body 구성 로직을 그대로 따르되 `metric`·`unit` 을 추가하고, 워드클라우드 전용 옵션(`max_words`, `word_color`, `apply_emotion_colors`, `wordcloud_pos`)은 보내지 않는다.
- 진행 표시: 대상이 1명이면 단건 호출, 여러 명이면 `saveDeploy()` 의 청크·워커 패턴(`:1688-1715`)을 재사용한다.
- **전면 차단 오버레이(`showBusyOverlay`, `:1599`)는 사용하지 않는다.** 「그래프 저장」은 버튼(`btnGenerateMatrix`·`btnSaveDeploy`·`btnSaveGraph`)만 비활성화하고 진행률은 결과 영역에 표시한다.
- 완료 후 결과 영역에 생성된 이미지 썸네일과 파일 경로를 표시하고, `zipDownloadBtn` 을 노출한다.

---

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 수정 대상 4개 파일 백업(`WP/src/services/perspective_service.py`, `WP/src/routes/perspective_routes.py`, `WP/web/templates/perspective_test.html`, `WP/web/templates/deploy_gallery.html`) | — |
| 2 | `aggregate_sentiment_trend()` 구현 — 지표 5종·단위 2종, 연도 0건 처리 | 1 |
| 3 | 단독 스크립트로 실데이터 1명분 집계값 검증(문장 수 합계가 기존 `positive_sentence_details` 길이와 일치하는지 대조) | 2 |
| 4 | `_save_trend_chart_to_path()` 구현 — 라인 차트 렌더·한글 폰트·`plt.close` | 2 |
| 5 | `save_trend_graph_to_deploy()` 구현 — 이름/경로 규칙, 갤러리 DB 등록 | 3,4 |
| 6 | 라우트 `POST /api/perspective/matrix/save-graph` 추가(단건·배치·권한·폰트 초기화) | 5 |
| 7 | ZIP 수집부(`perspective_routes.py:344-353`)에 `graph` 키 추가 | 5 |
| 8 | 화면: 버튼 추가(`:325`↔`:326` 사이) + 활성화 토글 연동 | — |
| 9 | 화면: 옵션 패널 + `saveGraph()` 실행·진행표시·결과 렌더 | 6,8 |
| 10 | (선택) 갤러리 노출 — `deploy_gallery.html:875-877, 2150-2151, 2207, 2234` 에 `graph` 타입 추가 | 5 |
| 11 | §6 테스트 시나리오 전건 수행 후 결과를 `result/` 에 기록 | 9 |

> 순서 10은 **P2(선택)** 다. 인사처 납품은 파일·ZIP 으로 충족되므로 갤러리 노출 없이도 요구는 만족된다.

---

## 5. 영향도 분석

| 파일 | 변경 | 영향 범위 |
|------|------|-----------|
| `WP/src/services/perspective_service.py` | 신규 함수 3개 추가(`aggregate_sentiment_trend`, `_save_trend_chart_to_path`, `save_trend_graph_to_deploy`) + 갤러리 등록 함수 1개 | 기존 함수 **무수정**. `save_to_deploy`(`:3230`)·`generate_perspective_matrix`(`:2992`) 는 손대지 않는다 |
| `WP/src/routes/perspective_routes.py` | 라우트 1개 신규 + ZIP 수집부(`:344-353`) 1줄 추가 | 기존 `/matrix`, `/matrix/save-deploy` 무영향. ZIP 은 `graph` 키가 없는 과거 결과에도 안전(키 부재 시 건너뜀) |
| `WP/web/templates/perspective_test.html` | 버튼 1개 + 옵션 패널 + JS 함수 2개 | 액션 행 레이아웃이 버튼 1개만큼 넓어짐. `zipDownloadBtn` 은 우측으로 밀림 |
| `WP/web/templates/deploy_gallery.html` | (P2) 타입 칩 1개 추가 | 미수행 시 갤러리 표시만 없음, 파일 생성에는 영향 없음 |
| `outputs/배포/` | 하위 폴더 `그래프/` 신설 | 기존 `통합`/`긍정`/`부정` 폴더와 병렬. 기존 파일 무변경 |
| `gallery_entries` 테이블 | `source='graph'` 행 추가, `images` JSON 에 `graph` 키 | 스키마 변경 없음(`gallery_db_service.py:39`). 기존 조회는 `source` 필터(`:165-167`)로 분리됨 |

**변경하지 않는 것**: 감정 판정 로직(`_get_sentence_level_scores`, `calculate_word_scores`), 단어 극성 경계(`>= 0` / `< 0`), 가명 관리, 기존 파일명 규칙.

---

## 6. 테스트/검증 계획

> 계획서 상태를 `Done` 으로 올리려면 아래를 **실제 화면에서 동작시켜** 통과해야 한다. 단위 테스트만으로는 `Done` 불가(`Pre-Done` 까지).
> 서버 실행은 사용자가 직접 한다 — 구현자는 실행 명령만 안내한다.

| # | 시나리오 | 기대 결과 |
|---|----------|-----------|
| T1 | 직원 1명 + 연도 2개(예: 2024·2026) 체크 → 그래프 저장(문장 수, %) | `outputs/배포/그래프/<이름_사번>_긍부정그래프.png` 생성, 점 2개가 선으로 연결, 긍+부 = 100% |
| T2 | 같은 조건에서 단위를 `수량` 으로 변경 | Y축이 건수, 두 계열 값이 T1 의 분자와 일치 |
| T3 | 지표를 `단어 수(빈도)` 로 변경 | 파일 재생성, 값이 T1 과 다르며 워드클라우드 긍/부정 단어 집합과 방향 일치 |
| T4 | 연도 1개만 체크 | 경고 표시 후 생성 가능, 점 1개(선 없음)로 렌더 |
| T5 | 해당 직원에게 평가가 없는 연도를 포함해 체크 | 그 연도는 선이 끊기고 `skipped_rows` 에 기록, 오류로 죽지 않음 |
| T6 | 긍정·부정이 모두 0인 연도(중립만 존재) | % 모드에서 분모 0 → 결측 처리, 예외 없음 |
| T7 | CSV 업로드로 여러 명 일괄 저장 | 직원 수만큼 PNG 생성, 진행률 표시, 실패 직원은 목록에 표시 |
| T8 | 저장 후 「⬇️ 결과물 ZIP」 | ZIP 안에 `배포/그래프/*.png` 포함 |
| T9 | 제출용 저장 회귀 | 기존 3종(통합/긍정/부정) 파일·경로·갤러리 등록이 이전과 동일 |
| T10 | 한글 표시 | 제목·범례·축 라벨의 한글이 깨지지 않음(□ 없음) |
| T11 | 문장 수 지표 교차검증 | 같은 직원·같은 연도에 대해 그래프 집계값 == 제출용 저장 결과의 `positive_sentence_details` / `negative_sentence_details` 길이(`perspective_service.py:3381-3382`) |

검증 결과는 `WP/plans/2026/08/12_01_sentiment-trend/result/` 에 기록한다. 테스트 스크립트가 생기면 `WP/plans/2026/08/12_01_sentiment-trend/test/` 에 둔다.

---

## 7. 리스크 및 제약

| # | 리스크 | 대응 |
|---|--------|------|
| R1 | **단어 기준 지표의 중립 포함** — `wf_positive = score >= 0`(`perspective_service.py:3312`)이라 중립 단어가 긍정에 섞인다. 그래프만 기준을 바꾸면 워드클라우드와 수치가 어긋나고, 판정 기준을 바꾸면 긍↔부 오분류 위험이 생긴다 | 기준을 **바꾸지 않고** 그래프·UI에 "단어 기준은 워드클라우드와 동일(중립을 긍정에 포함)" 을 명시. 기본 지표는 중립이 분리되는 문장 기준으로 둔다 |
| R2 | **성능** — 단어 기준 지표는 `calculate_word_scores()`(`:2274`)가 단어×평가×문장을 순회. 연도 수만큼 반복 | 기본값을 문장 기준으로. 배치 저장은 제출용 저장과 동일한 청크·4워커 패턴 사용. 전 직원(약 1.9만 명) 일괄은 소요시간을 사전 안내 |
| R3 | **한글 폰트** — `_setup_korean_font()`(`:3088-3107`)는 Windows 경로만 등록하고 실패를 삼킨다. 리눅스 환경이면 한글이 □ 로 렌더 | T10 으로 배포 대상 환경에서 확인. 깨지면 폰트 등록 실패를 로그로 남기도록 보완(별건) |
| R4 | **실명 파일 생성** — `getOutputMode()`(`perspective_test.html:682-684`)가 항상 `'real'` 이라 파일명에 실명·실사번이 들어간다 | 제출용 저장과 동일한 성격이므로 정책 변경 없음. `outputs/배포/` 폴더 취급 주의는 기존과 동일 |
| R5 | **파일명 규칙 불일치** — 인사처 예시(`110110_긍정.png`)와 실제(`배포/긍정/110110_통합.png`)가 다름 | §7 결정 D-1 로 처리. 기존 파일명 개명은 갤러리 DB에 저장된 기존 URL을 전부 무효화하므로 기본은 **유지** |
| R6 | **연도 1개** 선택 시 "선"이 성립하지 않음 | 경고 후 점만 렌더(T4) |
| R7 | 갤러리 UI 가 3종 하드코딩(`deploy_gallery.html:875-877` 등) | P2 로 분리. 미수행 시 갤러리에 그래프가 보이지 않을 뿐 파일·ZIP 은 정상 |

### 결정 필요 사항 (착수 전 O/X 확인)

| # | 결정 항목 | 계획서 채택안(권고) | 대안 |
|---|-----------|---------------------|------|
| D-1 | 파일명 규칙 | **신규 그래프만** 새 규칙 `<사번>_긍부정그래프.png` 적용, 기존 워드클라우드 파일명(`<사번>_통합.png` + 폴더로 극성 구분)은 유지 | 기존 3종도 `<사번>_긍정.png` 식으로 개명 — 갤러리 DB의 기존 이미지 URL 전량 무효화, 재저장 필요 |
| D-2 | 저장 폴더명 | `outputs/배포/그래프/` | `outputs/배포/추이/` 등 |
| D-3 | 기본 옵션 | 지표 = 긍정/부정 **문장 수**, 단위 = **%** | 단어 수 기준 기본 |
| D-4 | 제출용 저장과의 결합 | 「그래프 저장」은 **독립 버튼**으로만 동작(제출용 저장은 무변경) | 제출용 저장 시 그래프도 자동 동시 생성 |

> D-1~D-4 는 위 채택안으로 구현을 진행해도 되는지 확인만 받으면 되며, 반대 의견이 없으면 채택안대로 진행한다.

---

## 8. 참고 — 이 계획서가 다루지 않는 것

- 매트릭스 셀 내부 CSS 막대(`perspective_test.html:2827-2829`)의 변경 — 그대로 둔다
- 연도 외 다른 X축(부서·직급 등) — `rowFieldSelect`(`:281`)에 옵션이 하나뿐이라 현행 데이터로 불가
- 그래프의 화면 미리보기(저장 전) — 요구에 없으므로 제외. 저장 후 결과 영역에서 이미지로 확인한다
- 모바일/반응형 대응 — 내부망 데스크톱 전용
