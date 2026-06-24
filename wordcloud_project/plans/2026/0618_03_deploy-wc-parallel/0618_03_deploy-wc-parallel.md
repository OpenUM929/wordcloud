# 계획서 — 제출용 저장 워드클라우드 생성 병렬화

> 상태: Done(코드 적용 확인 — save-deploy-stream ThreadPool 병렬화, 2026-06-18) | 작성일: 2026-06-18
> 작업 유형: D (리팩토링/성능 개선)
> 선행: `plans/2026/0617_07_hardware-adaptive-worker-plan/0617_07_hardware-adaptive-worker-plan.md` (DN — 배치/매트릭스 경로 병렬화·GPU 통합), `plans/2026/0615_08_sentence-kote-cache/` (DN — 문장 KoTE 캐시)
> 참고(타 AI 분석): `plans/2026/0618_02_wordcloud-opt-feasibility/0618_02_wordcloud-opt-feasibility.md`

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-18 | 전체 | v1 초안: 제출용 저장 직렬 스트림 병렬화 설계 |
| 2026-06-18 | §3 작업6, §8 | v2: 타 AI 가능성 분석(0618_02) 교차검토 반영 — 결과 캐싱(작업6) 추가, ProcessPool vs ThreadPool 판단 근거 보강 |
| 2026-06-18 | 전체 | v3: 코드 전수 교차 검증 후 본문을 검증된 사실 기준으로 확정 — 호출처(`save_to_deploy` 3곳)·import 경로(`src.` 접두사)·`json_lib`(routes L4)·캐시 키(`round(score,6)`·경로 분리)·GIL 해제 범위·`request` 미사용(죽은 파라미터) |

---

## 1. 배경 및 목적

집단 분석 테스트의 **"제출용 저장"** 버튼(전체 직원 일괄 저장 포함)은 다음 경로로 직원별 워드클라우드(통합/긍정/부정 3장)를 생성한다.

```
api_save_deploy_stream (perspective_routes.py:660)
  └─ generate() (L710-746)  ← 직원 ID 리스트를 for 루프로 1명씩 순차 처리
       └─ save_to_deploy (perspective_service.py:1824)
            └─ _generate_wc_for_items (L1893)
                 ├─ extract_words / calculate_word_scores
                 ├─ _save_wc × 3 (통합/긍정/부정) → _save_wordcloud_to_path (L1072)
                 │     └─ WordCloudGenerator.generate_with_colors_and_options (wordcloud_generator.py:275)
                 └─ 문장 상세(_get_sentence_level_scores, _highlight_words_in_sentence)
            └─ _append_to_deploy_manifest (L1723) → gallery_db_service.upsert_entry
```

**문제**: `generate()`(perspective_routes.py:715)의 `for idx, eid in enumerate(ids)` 루프는 완전 직렬이다. 전체 직원(약 1.9만명, [[project_batch_scale_19k]]) 일괄 저장 시 직원 수에 정비례하는 벽시계 시간이 발생한다.

**선행 계획서와의 관계**: `0617_07`(DN)이 병렬화·GPU 통합한 대상은 **배치 분석**(`batch_processor.py`)과 **매트릭스 미리보기**(`perspective_service.py` L2047 `generate_all_employee_matrix`의 `ThreadPoolExecutor`)였다. **본 계획의 대상인 제출용 저장 스트림은 0617_07이 손대지 않은 별개 경로**이며, 동일한 ThreadPoolExecutor 패턴이 아직 적용되지 않았다.

**목적**: 제출용 저장 스트림을 직원 단위로 병렬 처리하여 일괄 저장 벽시계 시간을 단축한다. **출력 이미지/문장 데이터의 내용은 변경하지 않는다**(동작 동일, 속도만 개선).

---

## 2. 현재 코드 분석

### 2-1. 워크로드 성격 (병렬화 방식 결정 근거)

`0615_08`(DN)로 문장 단위 KoTE 점수가 배치 시 캐시(`sentence_emotion_cache`)되므로, 제출용 저장 경로의 `_get_sentence_level_scores`(L930)는 **캐시 경로로 동작하여 KoTE(GPU)를 재실행하지 않는다**. 따라서 이 경로의 잔여 비용은:

| 비용 항목 | 성격 | GIL |
|-----------|------|-----|
| `extract_words`, `calculate_word_scores` | 파이썬 dict/Counter 연산 | 점유 |
| **WordCloudGenerator 나선형 배치 × 3장** | 순수 파이썬 루프 (핫스팟) | **점유** |
| 문장 상세 빌드 + HTML 하이라이트 | 파이썬 문자열 연산 | 점유 |
| PNG 파일 저장(`img_color.save`) | 디스크 I/O | 해제 |
| gallery DB `upsert_entry` | SQLite I/O | 해제 |
| `_load_corrections_map` DB 조회 | SQLite I/O | 해제 |

→ **GPU 바운드가 아니라 CPU/GIL + I/O 바운드**다. 그러므로 0617_07의 GPU·VRAM 기반 `_calc_adaptive_workers()`를 그대로 쓰는 것은 부적합하며, I/O 혼합 워크로드에 맞는 스레드 풀이 적합하다.

### 2-2. 핫스팟 — 나선형 충돌 감지 (wordcloud_generator.py:383-384)

```python
region = img_grey.crop((x1, y1, x2, y2))
if max(region.getdata()) == 0:          # ← getdata()로 전 픽셀을 파이썬 시퀀스로 변환 후 max()
```

`getdata()` + `max()`는 영역 픽셀 전체를 파이썬 레벨로 끌어와 순회한다(GIL 점유). 단어마다, 나선 스텝마다 반복되어 이미지 1장 생성의 대부분 시간을 차지한다. **이 부분이 GIL을 잡고 있으면 스레드 병렬화의 실효 speedup이 제한**된다.

추가로 루프 내부에서 매 단어마다 생성되는 다음 두 객체도 불필요한 반복이다(스레드와 무관한 단일 호출 비용이지만 동반 개선 가능):
- `dummy_draw = ImageDraw.Draw(Image.new('L', (1, 1)))` (L368)
- `font = ImageFont.truetype(font_path, font_size)` (L364) — 크기별 캐시 가능

### 2-3. 동시성 위험 — 모듈 전역 RNG (wordcloud_generator.py:304, 373)

```python
random.seed(42)                          # L304 — 호출마다 모듈 전역 RNG를 시드
...
start_angle = random.uniform(0, 2*math.pi)  # L373 — 모듈 전역 RNG 사용
```

`generate_with_colors_and_options`가 여러 스레드에서 동시에 호출되면 모듈 전역 `random` 상태를 공유하여 (1) 시드/소비가 인터리빙되어 배치 결과가 비결정적이 되고, (2) 전역 상태에 대한 경쟁이 발생한다. **병렬화 전제로 지역 RNG(`random.Random(42)`)로 전환 필수.**

### 2-4. 공유 자원 스레드 안전성 점검 결과

| 자원 | 위치 | 판정 | 근거 |
|------|------|------|------|
| gallery DB 쓰기 | `gallery_db_service.upsert_entry` (L61) | 안전(보강 권장) | 호출마다 새 커넥션(`check_same_thread=False`, `journal_mode=WAL`), 엔트리 `id`는 `uuid4`로 고유 → 충돌 없음. 단 고경합 시 `database is locked` 가능 → `PRAGMA busy_timeout` 보강 |
| corrections DB 조회 | `_load_corrections_map` (L904) | 안전 | 호출마다 새 커넥션 open/close |
| PNG 파일 저장 | `_save_wc`/`_save_wordcloud_to_path` | 안전 | 직원·감정별 파일명(`{safe_name}_{suffix}.png`)이 디렉토리(통합/긍정/부정)별로 분리되어 경로 충돌 없음 |
| matplotlib 폰트 설정 | `_setup_korean_font` (L1682) | 무해(중복) | 전역 `plt.rcParams` 설정. PIL 기반 생성기는 실제로는 `font_path`를 직접 사용하므로 이 설정에 의존하지 않음 → 루프 밖 1회 호출로 이동 권장 |
| WordCloudGenerator 인스턴스 | `_save_wordcloud_to_path` (L1075) | 안전 | 호출마다 새 인스턴스 → 스레드 간 공유 없음(설정 JSON을 매번 재로딩하는 낭비는 본 계획 범위 외, [[deploy-wc-generator-reuse]] 후속 가능) |
| 전역 `random` | `wordcloud_generator.py` L304/373 | **위험** | §2-3 — 지역 RNG 전환 필요 |

---

## 3. 변경 설계

### 작업 1 (필수, 스레드 안전 전제) — 전역 RNG → 지역 인스턴스

**대상**: `wordcloud_generator.py` `generate_with_colors_and_options` (L304, L373)

```python
# AS-IS
random.seed(42)
...
start_angle = random.uniform(0, 2 * math.pi)

# TO-BE
rng = random.Random(42)          # 호출 지역 RNG — 스레드 간 상태 공유 없음
...
start_angle = rng.uniform(0, 2 * math.pi)
```

단일 호출 결과는 기존과 **동일**(시드 42 고정). 병렬 호출 시 결정성·스레드 안전 확보.

### 작업 2 (필수, 병렬 효과 enabler) — 충돌 감지 C레벨화 + 루프 불변식 추출

**대상**: `wordcloud_generator.py` (L364-388)

```python
# (a) 충돌 감지: getdata()/max() → getextrema() (C레벨, GIL 해제)
# AS-IS
region = img_grey.crop((x1, y1, x2, y2))
if max(region.getdata()) == 0:
# TO-BE
region = img_grey.crop((x1, y1, x2, y2))
if region.getextrema()[1] == 0:        # 최댓값이 0이면 충돌 없음 — 동일 판정

# (b) dummy_draw 루프 밖 1회 생성 (L368을 단어 루프 진입 전으로 이동)
# (c) 폰트 크기별 캐시: font_cache: dict[int, ImageFont] 로 truetype 재사용
```

판정 의미가 동일(영역 내 픽셀 최댓값 == 0)하므로 **출력 동일**. C레벨 스캔으로 이미지당 시간 단축 + 해당 구간 GIL 해제.

> ⚠️ **실효 speedup 한계**: `getextrema()`는 픽셀 스캔 구간만 GIL을 해제한다. 나선 루프 본체의 `img_grey.crop(...)`(매 스텝 Python Image 객체 생성)·좌표 계산·제너레이터는 여전히 Python 레벨이라 GIL을 재점유한다. 따라서 작업2는 스레드 중첩을 **부분적으로 개선**할 뿐이다(상한 존재). ProcessPool 배제의 주근거는 §8의 unified pickle 전송 비용이며, getextrema는 보조 근거다.

### 작업 3 (핵심) — 제출용 저장 스트림 병렬화

**대상**: `perspective_routes.py` `api_save_deploy_stream`의 `generate()` (L710-746)

직렬 `for` 루프를 `ThreadPoolExecutor` + `as_completed`로 교체하되, **NDJSON 스트리밍 진행 보고는 완료 순서대로 그대로 yield**한다(프론트는 메시지의 `employee` 키로 추적하므로 처리 순서 무관).

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

def generate():
    success_list, fail_list = [], []
    total = len(ids)
    _setup_korean_font()                       # 루프 밖 1회 (작업4)
    num_workers = min(multiprocessing.cpu_count(), 8)   # 매트릭스 경로(L2047)와 동일 관례
    completed = 0

    def _work(eid):
        # request는 save_to_deploy 본문에서 미사용(아래 주의 참조)이므로 None 전달
        return eid, save_to_deploy(unified, eid, row_field, col_mode, analysis_type, options, None)

    with ThreadPoolExecutor(max_workers=num_workers) as ex:
        futures = {ex.submit(_work, eid): eid for eid in ids}
        for fut in as_completed(futures):
            eid = futures[fut]
            completed += 1
            try:
                _, result = fut.result()
                if result:
                    result['employee_id'] = eid
                    result['profanity_summary'] = build_profanity_summary(unified, eid)
                    success_list.append(result)
                    yield json_lib.dumps({'employee': eid, 'name': result.get('name', eid),
                                          'status': 'done', 'result': result,
                                          'current': completed, 'total': total}) + '\n'
                else:
                    fail_list.append({'employee_id': eid, 'error': '평가 데이터 없음'})
                    yield json_lib.dumps({'employee': eid, 'status': 'fail',
                                          'error': '평가 데이터 없음',
                                          'current': completed, 'total': total}) + '\n'
            except Exception as ex2:
                fail_list.append({'employee_id': eid, 'error': str(ex2)})
                yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': str(ex2),
                                      'current': completed, 'total': total}) + '\n'
    # log_action + complete 메시지는 기존과 동일
```

> ⚠️ **변경 사항**: 기존엔 처리 직전 `status: 'processing'` 메시지를 직원별로 보냈으나, 병렬에선 완료 순서만 의미가 있어 `processing` 선행 메시지는 제거하고 `done`/`fail`만 보낸다. 프론트엔드(`perspective_test.html`)가 `processing` 메시지에 의존하는지 영향도 분석(§4)에서 확인 후, 의존 시 진행 표시를 `current/total` 기반으로 유지하도록 보정한다.

> ℹ️ **`request=None` 전달**: `request`는 `save_to_deploy`의 시그니처 정의부(`perspective_service.py:1824`)에만 존재하고 본문에서 사용되지 않는 죽은 파라미터다(파일 전체 grep = 1회). 따라서 워커 스레드에 `request=None`을 넘기면 충분하며 별도 데이터 추출이 필요 없다. (단, 추후 `save_to_deploy`가 `request`를 실제 참조하도록 바뀌면 워커 스레드엔 Flask 요청 컨텍스트가 없으므로, `generate()` 진입부에서 필요한 값을 추출해 전달하도록 변경해야 한다.)

> ℹ️ **`json_lib` 정체**: 위 코드 스니펫에서 `json_lib`은 `perspective_routes.py` 상단에 `import json as json_lib`로 정의되어 있다(동 파일 L4). 표준 라이브러리 `json`의 별칭이며, ThreadPoolExecutor 워커 스레드에서도 안전하다(순수 함수, 전역 상태 없음). 다른 이름으로 사용 중인지 확인 후 통일할 것.

### 작업 4 (동반) — `_setup_korean_font()` 호출 위치 이동

**대상**: `perspective_service.py` `save_to_deploy` (L1825) / `perspective_routes.py` `generate()`

`save_to_deploy` 내부 매 호출 `_setup_korean_font()`를 제거하고 `generate()` 진입 시 1회 호출(작업3 코드 참조). 비스트리밍 라우트도 1회 호출되도록 호출부 점검. (PIL 생성기는 이 설정에 의존하지 않으므로 기능 영향 없음 — §2-4)

> 🔴 **호출처 전수 — 폰트 보강 위치**: `grep save_to_deploy` 결과 routes 내 호출은 **3곳**이다.
> | 줄 | 위치 | 조치 |
> |----|------|------|
> | `perspective_routes.py:718` | `api_save_deploy_stream` `generate()` (스트리밍) | 작업3에서 루프 밖 1회 호출 |
> | `perspective_routes.py:499` | 비스트리밍 라우트 — **`for eid in employee_ids` 직렬 배치 루프(L496-501) 내부** | 동일 라우트 진입부에서 1회 호출(루프 밖) |
> | `perspective_routes.py:521` | 동일 비스트리밍 라우트 — 단일 직원 분기 | 위 진입부 1회 호출로 함께 커버됨 |
> `save_to_deploy` 내부 호출을 제거하면 비스트리밍 라우트도 폰트 설정을 잃으므로, **이 라우트 진입부(L482 `load_all_batches()` 이후, L496 분기 이전)에서 `_setup_korean_font()`를 1회 호출**하면 배치 루프(L499)·단일(L521) 두 분기를 모두 커버한다. (`save_to_deploy`의 `request=None` 처리는 §3 작업3 참조 — 현재 미사용 죽은 파라미터)

> ℹ️ **범위 외 명시**: 비스트리밍 라우트의 직렬 배치 루프(L496-501)는 스트리밍 경로와 동일한 직렬 패턴이지만, **본 계획은 스트리밍 경로(`generate()`)만 병렬화 대상**으로 한다. 따라서 작업 후에도 비스트리밍 배치 저장은 직렬로 남는다(의도적 범위 외 — 동일 패턴이므로 동일 방식 후속 적용 가능).

> **import 주의**: `_setup_korean_font()`는 `perspective_service.py`에 정의되어 있다. `perspective_routes.py`의 `generate()`에서 호출하려면 import가 필요하다. **이 코드베이스 컨벤션은 `src.` 접두사를 쓴다**(routes L7-12 `from src.services.perspective_service import (...)`). 따라서 기존 import 블록(L8-)에 `_setup_korean_font`를 추가하는 형태가 자연스럽다 — `from src.services.perspective_service import (..., _setup_korean_font)`. (`from services.perspective_service ...`는 컨벤션 불일치이므로 사용 금지.)
> 
> **호출처 전수 확인 필요**: `save_to_deploy`를 호출하는 곳(`api_save_deploy_stream`의 `generate()` 외)이 있는지 확인한다. `_setup_korean_font()`가 제거되면 해당 호출처에서도 폰트 설정 타이밍이 달라질 수 있다. `api_save_deploy`(비스트리밍 단일 저장 경로)에도 동일한 폰트 설정 보강이 필요. `grep -rn "save_to_deploy"`로 호출 전수를 확인할 것.

### 작업 5 (보강, 선택) — gallery DB busy_timeout

**대상**: `gallery_db_service._get_conn` (L12)

```python
conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")   # 동시 쓰기 경합 시 최대 5초 대기 (즉시 lock 에러 방지)
```

### 작업 6 (고효율, 선택 — 타 AI 분석 0618_02 §5-3 반영) — 동일 입력 재생성 스킵 캐싱

**대상**: `_generate_wc_for_items` / `_save_wc` (perspective_service.py L1878-1905)

**근거**: 재제출(`resubmitEmployee`, perspective_test.html:1959) 흐름은 **변경되지 않은 직원도 다시 전부 렌더링**한다. 입력이 동일하면 PNG를 다시 그릴 필요가 없다. 단, 출력물을 결정하는 입력에는 **감정 교정(`sentiment_corrections`)이 포함**되므로 캐시 키에 반드시 넣어야 한다(누락 시 교정 반영 누락 — [[project_eval_id_not_unique]] 관련, 교정은 `_db_id` 키잉).

```python
# 캐시 키 = 직원 + 필터 + 옵션 + 단어빈도/점수 + 교정 시그니처 해시
# scores는 float 정밀도 정규화(round 6) 후 직렬화
sig = hashlib.sha1(json.dumps({
    'eid': resolved_id, 'row_field': row_field, 'row_values': row_values,
    'pos': wordcloud_pos, 'wc': wc_options, 'sentiment': label_suffix,
    'wf': sorted(wf.items()),
    'scores': sorted((k, round(v, 6)) for k, v in word_scores.items()),
    'corr': sorted((str(k), v) for k, v in (deploy_corrections_map or {}).items()),
}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
# 동일 sig의 PNG가 이미 존재하면 렌더 생략, 경로만 반환
```

**효과**: 첫 전체 저장은 히트 0(효과 없음), **재제출/부분 재생성에서 변경 없는 직원은 렌더 비용 ~0**. 병렬화(작업3)와 직교 — 함께 적용 시 누적.
**주의**: 캐시 무효화 키에서 교정·옵션 누락 시 "수정했는데 그림이 그대로"인 정합성 버그가 난다. V1 회귀에 "교정 후 재제출 시 이미지 갱신" 케이스 필수.
> **float 정밀도 주의**: `word_scores` 값이 float일 경우 동일 점수라도 미세한 부동소수점 차이로 SHA1 해시가 달라질 수 있다. 구현 시 `round(score, 6)` 등으로 정규화 후 직렬화해야 캐시 효율이 보장된다.
> **경로 분리로 false-hit 없음**: `output_mode`/`deploy_name`은 sig에 미포함이지만, 출력 PNG 경로(`safe_name`)가 이 값들로 갈라지므로 캐시는 경로별로 분리되어 서로 다른 모드 간 오적중이 발생하지 않는다. PNG에 그려지는 것은 단어뿐(이름·사번은 파일명에만 반영)이라 동일 sig면 그림 내용도 동일 — 정합성 유지. 캔버스 크기 등 출력 결정 요소는 `wc`(=`wc_options`)에 포함됨.
**롤백**: 캐시 분기 제거(무조건 렌더).

---

## 4. 영향도 분석

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `src/modules/wordcloud_generator.py` | 수정 | 전역 `random`, `getdata()/max()`, 루프 내 객체 생성 | 지역 `random.Random(42)`, `getextrema()`, 객체/폰트 캐시 |
| `src/routes/perspective_routes.py` | 수정 | `generate()` 직렬 for 루프 | `ThreadPoolExecutor` + `as_completed` 스트리밍 |
| `src/services/perspective_service.py` | 수정 | `save_to_deploy` 내부 폰트 설정 | 폰트 설정 호출 제거(호출부로 이동) |
| `src/services/gallery_db_service.py` | 수정(선택) | WAL만 | `busy_timeout` 추가 |
| `web/templates/perspective_test.html` | 점검 | `processing`/`done`/`fail` 메시지 처리 | **코드 확인 결과**: `addLine(..., 'processing')`(L1619)은 요청 전 클라이언트 측 UI 표시 — 서버 NDJSON의 `processing` 메시지와 무관. 서버 `processing` 제거 영향 없음 |

**사용처 전수 확인 필요**:
- `generate_with_colors_and_options` 호출처: `_save_wordcloud_to_path`(제출용/매트릭스 공용) → **작업1·2는 매트릭스 경로에도 적용됨**. 출력 동일(시드 42, 판정 동일)하므로 매트릭스 결과 회귀 없음. 단 회귀 테스트 대상에 매트릭스도 포함.
- `_setup_korean_font` 호출처 전수: `save_to_deploy` 외 호출 위치 확인 후 이동.
- `perspective_test.html`의 NDJSON 파싱부에서 `status === 'processing'` 사용 여부 grep.

**롤백**: 작업별 독립 — 작업1(전역 random 복원), 작업2(`max(getdata())` 복원), 작업3(직렬 for 복원), 작업4(내부 호출 복원), 작업5(`busy_timeout` 제거). 전체는 `git stash`.

---

## 5. 효과 예상

| 항목 | 현재(AS-IS) | 변경 후(TO-BE) | 비고 |
|------|-------------|----------------|------|
| 이미지 1장 충돌 감지 시간 | getdata+max (파이썬 전수) | getextrema (C레벨) | [측정 필요] — 단어/캔버스 크기 의존 |
| 직원 N명 일괄 저장 벽시계 | N × 직렬 | 작업2로 GIL 부분 해제 + I/O 중첩으로 워커 수에 따라 단축 | 스레드 단독 기대 1.5~2x. 작업2는 부분 개선(crop 등 Python 레벨 잔존으로 상한 존재). 정량은 §6 V6 측정 |
| 출력 이미지/문장 내용 | — | **동일**(회귀 없음 목표) | 시드 42·판정 의미 불변 |

> 정량 수치는 dev에서 합성/CSV 데이터로 1차 측정([[project_dev_no_batch_csv_only]] — dev는 배치 불가, CSV 반입만), 실데이터 N=500/1000 측정은 내부망에서 수행.

---

## 6. 테스트/검증 계획

작업 폴더 `test/`·`result/` 사용 (03.plan-mode.md §10).

- [ ] V1 (회귀, dev): 동일 입력으로 제출용 저장 전/후 생성된 PNG가 픽셀 동일(또는 시각 동일) — 작업1·2가 출력을 바꾸지 않음 확인. 매트릭스 미리보기 1건도 동일 확인.
- [ ] V2 (정합, dev): 충돌 감지 `getextrema()[1] == 0`과 `max(getdata()) == 0` 판정이 동일 영역에서 일치(유닛 테스트).
- [ ] V3 (동시성, dev): 워커 2~8개로 동시 저장 시 (a) 예외 없음, (b) gallery DB 엔트리 수 == 성공 직원 수, (c) `database is locked` 미발생.
- [ ] V4 (스트리밍): NDJSON `done`/`fail` 메시지가 직원당 정확히 1건, `complete` 메시지의 success/fail 합계 == total.
- [ ] V5 (프론트): `perspective_test.html` 진행률 표시가 `current/total` 기준으로 정상 갱신, 카드 렌더 정상.
- [ ] V6 (성능, 내부망): N=500/1000 일괄 저장 전후 벽시계 3회 측정. RAM 사용량 모니터링(OOM 없음).

---

## 7. 리스크 및 제약

| 리스크 | 영향 | 완화 |
|--------|------|------|
| GIL로 인한 실효 speedup 제한 | 스레드 단독 효과 작을 수 있음 | 작업2(getextrema, GIL 부분 해제) 동반. 단 crop·좌표계산은 Python 레벨이라 speedup 상한 존재(§3 작업2 한계). ProcessPool은 §8 사유로 배제 |
| `processing` 메시지 제거로 프론트 진행표시 영향 | 진행률 미갱신 | §4 코드 확인 결과 `addLine(..., 'processing')`은 클라이언트 측 UI — 서버 메시지 제거와 무관 |
| Flask `request` 컨텍스트 부재 (작업3) | **현재 무위험** — `save_to_deploy` 본문이 `request` 미사용(죽은 파라미터, grep 1회) | `request=None` 전달로 충분. 추출·딕셔너리 변환 불필요. 향후 `request` 참조 추가 시에만 재검토(§3 방어 노트) |
| 캐시 키 float 정밀도 (작업6) | 동일 점수여도 부동소수점 미세 차이로 캐시 미스 | 구현 시 `round(score, 6)` 정규화 후 직렬화 |
| 동시 SQLite 쓰기 경합 | `database is locked` | 작업5 `busy_timeout`, 엔트리 uuid 고유로 충돌 없음 |
| 작업1·2가 매트릭스 경로에도 적용 | 매트릭스 출력 회귀 가능성 | V1에 매트릭스 회귀 포함 |
| 메모리: 워커당 캔버스 이미지 동시 보유 | 피크 메모리 증가 | 워커 상한 `min(cpu, 8)`, V6에서 모니터링 |

## 8. 제외 결정

| 항목 | 사유 |
|------|------|
| ProcessPoolExecutor | 채택하지 않음. **주근거**: 워커 함수 `save_to_deploy(unified, ...)`에 **`unified=load_all_batches()` 전체(약 1.9만명)가 인자로 들어가** Windows spawn 시 매 워커로 pickle 전달 → 데이터 전송 비용이 GIL 손실을 상회. **보조근거**: 작업2(getextrema)로 핫스팟 일부가 C레벨(GIL 해제)로 바뀌어 ThreadPool로도 부분 개선 가능(단 crop 등은 Python 레벨로 GIL 재점유 — §3 작업2 한계 참조). ProcessPool은 직원별 슬라이스만 전달하도록 리팩토링한 뒤에야 검토 가치 |
| 0617_07 `_calc_adaptive_workers()` 재사용 | 그 함수는 GPU/VRAM 기반 — 본 경로는 GPU 미사용(캐시) CPU/IO 워크로드. 매트릭스 경로 관례(`min(cpu,8)`)가 적합 |
| WordCloudGenerator 인스턴스/설정 재사용 | 별개 최적화(설정 JSON 재로딩 제거). 본 계획 범위 외 — [[deploy-wc-generator-reuse]] 후속 |

---

*상태: PND — 승인("수행") 시 작업1→2→4→5(보강)→3 순으로 적용하고, 각 단계 후 V1·V2 회귀를 먼저 통과시킨 뒤 병렬화(작업3) 진입한다.*
