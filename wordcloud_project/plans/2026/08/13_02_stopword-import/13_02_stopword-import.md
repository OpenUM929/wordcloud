# 계획서 — 불용어 CSV/엑셀 파일 일괄 등록 (직원 이름 대량 불용어 처리)

> 상태: Todo | 작성일: 2026-08-13
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 없음

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-13 | 전체 | 최초 작성 |

---

## 요구사항 원자화

> `기대` 열은 코드 실측을 근거로 내가 채운 예측 답이다. 착수 전 사용자가 O/X 로 교정한다.

| # | 원자 질문 | 기대 (사용자 확인) | 작업 후 답 (근거) |
|---|-----------|--------------------|------------------|
| 2.1 | 파일 업로드 버튼이 붙는 화면은 `/settings#stopwords`(불용어 관리 탭)인가? | Y — `ui_routes.py:121` 이 `/stopwords` 를 `/settings#stopwords` 로 302 리다이렉트. 실제 화면은 `settings_hub.html` + `partials/_stopwords_body.html` | |
| 2.2 | 업로드 파일 형식은 CSV와 엑셀(.xlsx/.xls) 둘 다인가? | Y가 요구사항. 다만 **현재 서버에 `openpyxl` 이 없어 .xlsx 는 지금 그대로면 실패**한다(§2.4) → D-1 결정 필요 | |
| 2.3 | 파일의 **첫 번째 열**을 불용어 단어로 읽으면 되는가? | Y — 1열=단어. 2열이 있으면 카테고리로 읽는다(선택) | |
| 2.4 | 파일 첫 행이 머리글(예: `이름`)이면 자동으로 건너뛰는가? | Y — 첫 행 값이 `단어/이름/불용어/word/name` 중 하나면 머리글로 보고 제외. 그 외에는 데이터로 취급 | |
| 2.5 | 업로드한 단어는 어느 카테고리에 들어가는가? | 사용자가 화면에서 고른 카테고리 1개로 전부 들어간다. 직원 이름용으로 **`인명` 카테고리를 새로 만든다** → D-2 | |
| 2.6 | 업로드 시 각 단어의 품사를 자동 분류하는가? | N — 자동 분류(`auto_classify_word`)는 단어마다 형태소 분석기를 호출해 수천 건에서 매우 느리다. 임포트는 고정 카테고리로 넣는다 → D-4 | |
| 2.7 | 이미 등록된 단어가 파일에 있으면 어떻게 되는가? | 건너뛴다(중복 추가 안 함). 결과 화면에 「중복 n건」으로 보고한다 | |
| 2.8 | 업로드하면 바로 저장되는가, 미리보기를 먼저 보는가? | **미리보기 먼저.** 총 n건 / 신규 n건 / 중복 n건 / 무효 n건 + 샘플 20개를 보여주고 사용자가 [등록] 을 눌러야 저장한다 | |
| 2.9 | 등록 후 워드클라우드에 즉시 반영되는가, 서버를 다시 켜야 하는가? | 즉시 반영 — 불용어 관리자는 프로세스 내 싱글톤이고(`stopword_manager.py:353`) 워드클라우드·NLP가 같은 인스턴스를 쓴다(`nlp_analysis.py:121`, `wordcloud_generator.py:295`) | |
| 2.10 | 이름을 불용어로 넣으면 「홍길동이」, 「홍길동님」 처럼 조사가 붙은 형태도 제거되는가? | Y(워드클라우드 경로 한정) — 워드클라우드 단어는 형태소 단위로 뽑히므로 조사가 분리된 뒤 대조된다(`nlp_analysis.py:189`). 단 **텍스트 통째 필터(`filter_stopwords`)는 공백 단위라 조사 결합형을 못 지운다** → R-4 | |
| 2.11 | 한 글자 이름/단어도 제거되는가? | N — 워드클라우드 단어 추출이 `len(word) > 1` 조건을 걸어 한 글자는 애초에 후보에서 빠진다(`nlp_analysis.py:189`) | |
| 2.12 | 직원 실명이 파일로 저장되는데, 그 파일이 배포 패키지에 들어가도 되는가? | **현재 구조로는 들어간다** — `src/configs/` 는 배포 제외 목록에 없다(`deploy/build_deploy.ps1:34-41`). 실명 유출 방지를 위해 **별도 파일로 분리하고 배포 제외**를 권고 → D-3 | |
| 2.13 | 업로드로 넣은 단어를 나중에 파일 단위로 되돌릴(일괄 삭제) 수 있어야 하는가? | N — 이번 범위 밖. 개별 삭제(기존 DELETE API)만 | |

---

## 1. 배경 및 목적

### 1.1 요청 원문

> 불용어 추가를 CSV 파일이나 엑셀 파일로도 할 수 있게 해야 한다. 특히 사내 직원들 이름을 불용어 처리하기 위해서는 파일 업로드를 통한 방법이 매우 중요하다.

### 1.2 왜 필요한가 (실측)

현재 불용어 추가는 **화면에서 한 단어씩 입력하는 경로뿐**이다. `POST /api/stopwords` 는 `word` 1개만 받는다(`src/routes/api_routes.py:325-330`) 하고, 화면도 입력창 1개다(`partials/_stopwords_body.html:24-27`). 현재 사전에 등록된 단어는 **8개 카테고리 101단어**다(`src/configs/stopwords.json` 실측). 직원 이름 수백~수천 건을 이 경로로 넣는 것은 사실상 불가능하다.

---

## 2. 현재 시스템 분석 (전부 실측)

### 2.1 불용어 저장·조회 계통

| 구분 | 위치 | 내용 |
|------|------|------|
| 모듈 | `src/modules/stopword_manager.py` (395줄) | `StopwordManager` — 카테고리별 dict + 평탄화 리스트 |
| 저장 파일 | `src/configs/stopwords.json` | `{"module_name", "description", "categories":[{"name","words":[...]}], "settings"}` — 8카테고리 101단어 |
| 단건 추가 | `add_stopword(word, category='기타')` `:262` | 카테고리 없으면 생성, 중복이면 `False` 반환 |
| 저장 | `save_stopwords(config_path="configs/stopwords.json")` `:316` | `self.stopwords` → `config["categories"]` 동기화 후 JSON 덮어쓰기 |
| 조회 | `is_stopword(word)` `:227` | `word.strip() in self.all_stopwords` — **리스트 순차 탐색** |
| 싱글톤 | `get_stopword_manager(config_path="configs/stopwords.json")` `:353` | thread-safe 지연 초기화 |

### 2.2 API (`src/routes/api_routes.py`)

| 메서드·경로 | 라인 | 비고 |
|-------------|------|------|
| `GET /api/stopwords` | `:227` | 전체 반환(페이징 없음), `{word, category}` 배열 |
| `GET /api/stopwords/categories` | `:275` | 카테고리명 목록 |
| `GET /api/stopwords/category/<category>` | `:300` | |
| `POST /api/stopwords` | `:325` | **단건** `{word, category}` |
| `DELETE /api/stopwords/<word>` | `:361` | |
| `POST /api/stopwords/check` | `:386` | |

**일괄 등록 엔드포인트는 없다 — 신규 필요.**

### 2.3 🔴 설정 파일 경로가 실행 디렉터리에 의존한다 (선행 결함)

- 모든 호출부가 기본값으로 호출한다: `api_routes.py:233/279/304/339/365`, `nlp_analysis.py:121`, `wordcloud_generator.py:295` — 전부 인자 없는 `get_stopword_manager()`.
- 기본값은 **상대 경로** `"configs/stopwords.json"` (`stopword_manager.py:353`) → 프로세스의 현재 작업 디렉터리 기준으로 해석된다.
- `src/config/settings.py` 에는 **불용어 경로 상수가 없다**(`grep stopword src/config/settings.py` → 0건). 다른 설정은 전부 상수화돼 있다: `NLP_CONFIG_PATH`·`WORD_BOOST_CONFIG_PATH` 등(`settings.py:32-40`, `CONFIGS_DIR_PATH = <app_root>/src/configs`).
- 실측: `wordcloud_project/configs/` 디렉터리는 **존재하지 않는다**. 실제 파일은 `wordcloud_project/src/configs/stopwords.json` 뿐이다.

→ 즉 서버를 `src/` 이외의 위치에서 띄우면 `_load_config` 가 파일을 못 찾아 **모듈 내부 하드코딩 기본 사전**(`stopword_manager.py:139-182`)으로 뜨고, `save_stopwords()` 는 그 위치에 새 `configs/` 폴더를 만들어 저장한다. 파일 업로드로 수백 건을 넣는 기능을 붙이기 전에 **저장 위치부터 못 박아야 한다**(§4.1).

선례: `word_boost_manager.get_word_boost_manager()` 는 `settings.WORD_BOOST_CONFIG_PATH` 를 쓴다(`src/modules/word_boost_manager.py:137-138`). 같은 방식으로 맞춘다.

### 2.4 🔴 엑셀(.xlsx) 을 지금 읽을 수 없다

- `pandas==2.3.3` 은 설치돼 있다(`requirements.txt`).
- 그러나 `.xlsx` 를 읽으려면 `openpyxl` 이 필요한데 **설치돼 있지 않다**. 실측: `venv/Lib/site-packages` 에 `openpyxl` 없음, `vendor_python_pkgs/`(오프라인 설치용 휠 모음)에도 없음, `python -c "import openpyxl"` → `ModuleNotFoundError`.
- 기존 코드는 이미 `.xlsx` 를 받는 것처럼 돼 있다 — `file_parser.py:135` `pd.read_excel(file)`, `integrated_batch.html:218` `accept=".csv,.xlsx,.xls"`. 즉 배치 업로드 화면에서 엑셀을 올려도 같은 오류를 만나는 상태로 보인다(이 계획의 범위 밖이지만 D-1 판단 근거).

### 2.5 재사용 가능한 파일 파서 (`src/services/file_parser.py`, 199줄)

| 함수 | 라인 | 시그니처·동작 |
|------|------|---------------|
| `parse_csv_with_encoding(file_content, filename=None)` | `:9` | 인코딩 7종(utf-8·utf-8-sig·cp949·euc-kr…) × 구분자 4종을 순회 → `(DataFrame, encoding)` 또는 `(None, None)` |
| `parse_uploaded_file(file)` | `:96` 부근 | 확장자 검사(csv/xlsx/xls), 100MB 제한, CSV는 위 함수·엑셀은 `pd.read_excel`, 미리보기 10행 반환 |
| `normalize_dataframe(df)` / `extract_column_info(df)` | | 인코딩 정규화·열 메타 추출 |

한국어 CSV의 cp949/euc-kr 처리를 이미 갖추고 있어 **인코딩 로직을 새로 만들 필요가 없다**.

### 2.6 불용어가 실제로 적용되는 3개 경로

| 경로 | 위치 | 대조 단위 | 이름 제거 효과 |
|------|------|-----------|----------------|
| 워드클라우드 단어 추출 | `nlp_analysis.py:189` `not manager.is_stopword(word)` | **형태소**(Kiwi 토큰), `len(word) > 1` 조건 | 조사 분리 후 대조 → 「홍길동이」의 `홍길동` 제거됨 |
| 빈도 기반 렌더 | `wordcloud_generator.py:295-297` | 단어 빈도 dict의 키 | 위 결과를 받으므로 동일 |
| 텍스트 통째 필터 | `wordcloud_generator.py:167/229` → `filter_stopwords(text)` (`stopword_manager.py:239`) | **공백 분리 토큰** | 「홍길동이」는 그대로 남음 → R-4 |

---

## 3. 결정 필요 사항 (채택안 제시)

| # | 결정 | 선택지 | 채택안과 근거 |
|---|------|--------|---------------|
| D-1 | 엑셀 지원 | (A) `openpyxl` 휠을 `vendor_python_pkgs/` 에 동봉해 .xlsx 지원 / (B) 1차는 CSV 전용, 엑셀은 "다른 이름으로 저장 → CSV" 안내 | **A 채택(권장).** 요청이 "csv 파일이나 엑셀 파일" 이고, 인사 실무 파일은 대개 .xlsx 다. 내부망이라 pip 설치가 안 되므로 휠 동봉이 유일한 경로다. **단 휠 조달이 안 되면 B로 자동 축소**하고, 그 경우 업로드 시 "엑셀은 CSV로 저장 후 올려주세요" 메시지를 명확히 낸다 |
| D-2 | 직원 이름 카테고리 | (A) `인명` 카테고리 신설 / (B) 기존 `기타` 사용 / (C) 업로드 시 사용자가 임의 이름 입력 | **A + C 채택.** 기본 선택지로 `인명` 을 만들고, 화면에서 기존 카테고리 선택 또는 새 이름 입력을 허용한다. `인명` 으로 분리해야 나중에 사람 이름만 골라 보거나 지울 수 있다 |
| D-3 | 실명 저장 위치 | (A) `stopwords.json` 에 그대로 저장 / (B) `src/configs/stopwords_names.json` 으로 분리 + 배포 제외 목록에 추가 | **B 채택(권장).** 실측상 `src/configs/` 는 배포 패키지에 포함된다(`build_deploy.ps1:34-41` 의 `$ExcludeDirs`·`$ExcludeFiles` 에 없음). 불용어 목적상 **이름은 가명이 아닌 실명이어야 하므로**(원문에서 지워야 함) 가명화로 회피할 수 없다 → 파일을 분리하고 `$ExcludeFiles` 에 `stopwords_names.json` 을 추가하는 것이 유일한 차단책. 운영 서버에서는 업로드로 다시 넣는다. **사용자가 A를 택하면 그대로 진행하되 이 사실을 계획서에 남긴다** |
| D-4 | 임포트 시 자동 품사 분류 | (A) 미적용(고정 카테고리) / (B) 적용 | **A 채택.** `auto_classify_word`(`stopword_manager.py:108`)는 단어마다 형태소 분석기를 호출한다. 수천 건이면 지연이 크고, 사람 이름은 품사 분류가 무의미하다 |
| D-5 | 중복 단어 처리 | (A) 건너뛰고 보고 / (B) 카테고리 이동 | **A 채택.** B는 기존 분류를 덮어써 되돌리기 어렵다 |
| D-6 | 등록 절차 | (A) 미리보기 → 확인 → 등록 2단계 / (B) 업로드 즉시 등록 | **A 채택.** 잘못된 열을 올리면 사전이 오염되고 되돌리기 수단이 개별 삭제뿐이다 |

---

## 4. 구현 상세

### 4.1 선행 정리 — 저장 경로 고정 (§2.3 해소)

| 파일 | 변경 |
|------|------|
| `src/config/settings.py` | `STOPWORDS_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "stopwords.json")` 추가 (기존 `WORD_BOOST_CONFIG_PATH` `:40` 옆) |
| `src/modules/stopword_manager.py` | `get_stopword_manager(config_path=None)` → `None` 이면 `settings.STOPWORDS_CONFIG_PATH` 사용. `save_stopwords(config_path=None)` 도 동일. **기존 호출부는 전부 인자 없이 부르므로 시그니처 호환 유지**(실측: 인자를 넘기는 호출부는 모듈 내부 편의 함수 2곳뿐 — `:381`, `:395`) |

이 변경으로 실행 디렉터리와 무관하게 `wordcloud_project/src/configs/stopwords.json` 이 정본이 된다.

### 4.2 백엔드 — 모듈 계층

`src/modules/stopword_manager.py` 에 추가:

```python
def add_stopwords_bulk(self, words, category='기타', dry_run=False) -> dict:
    """단어 목록을 한 번에 추가한다.

    반환: {'total': n, 'added': n, 'duplicated': n, 'invalid': n,
           'added_words': [...], 'duplicated_words': [...], 'invalid_words': [...]}
    dry_run=True 면 사전을 변경하지 않고 집계만 낸다(미리보기용).
    """
```

- 정규화: 앞뒤 공백 제거, 빈 문자열·`nan` 제외, 파일 내 중복 제거.
- 무효 판정: 빈 값 / 길이 1 (워드클라우드 추출이 `len(word) > 1` 이라 효과 없음 — `nlp_analysis.py:189`) / 사전에 이미 있음(중복으로 분류).
- 저장은 호출부에서 `save_stopwords()` **1회**만 수행한다(단건 API처럼 단어마다 파일을 쓰지 않는다).

**성능(DL-3)**: 현재 `is_stopword` 는 리스트 순차 탐색이다(`:237`). 이름 수천 건이 들어오면 형태소 1개당 수천 회 비교가 되어 워드클라우드 생성 전체가 느려진다. 따라서 `self._stopword_index: set` 를 추가하고 `_flatten_stopwords()`·`add_stopword`·`add_stopwords_bulk`·`remove_stopword` 에서 함께 갱신, `is_stopword` 는 set 조회로 바꾼다. `all_stopwords` 리스트는 기존 반환 계약(`get_all_stopwords()`)이 있으므로 **유지한다**.

### 4.3 백엔드 — 서비스·라우트 계층

`src/routes/api_routes.py` 에 추가:

```
POST /api/stopwords/import        (multipart/form-data)
  file      : CSV 또는 XLSX 파일 (필수)
  category  : 저장할 카테고리명 (기본 '인명')
  mode      : 'preview' | 'commit'  (기본 'preview')
  column    : 단어가 든 열 이름 또는 인덱스 (기본 0)

  200 preview: {success, total, new, duplicated, invalid,
                sample: [{word, status}], columns: [...]}
  200 commit : {success, added, duplicated, invalid, category, total_after}
  400        : 파일 없음 / 지원하지 않는 형식 / 열 없음 / 빈 파일
  413 대체   : 100MB 초과는 400 + 메시지 (file_parser 규약 재사용)
  500        : 파싱·저장 실패
```

파싱은 `file_parser.parse_csv_with_encoding()` 을 재사용한다. 엑셀은 `pd.read_excel` 사용 — D-1이 B로 확정되면 확장자 단계에서 400 + 안내 메시지로 차단한다(`ModuleNotFoundError` 를 500으로 노출하지 않는다).

`preview` 응답은 `add_stopwords_bulk(..., dry_run=True)` 결과를 그대로 쓴다. `commit` 은 사용자가 미리보기에서 확인한 **같은 파일을 다시 업로드**하는 방식(서버에 임시 파일을 남기지 않는다 — PII 파일을 디스크에 방치하지 않기 위함, DL-9).

### 4.4 프론트엔드

`web/templates/partials/_stopwords_body.html` — 기존 `.add-section`(`:22-28`) 아래에 파일 등록 블록 추가:

```
[파일로 일괄 등록]
  파일 선택(.csv, .xlsx, .xls)   카테고리 [인명 ▼ / 직접입력]   [미리보기]
  ── 미리보기 결과 ──────────────────────────
  총 1,234건 · 신규 1,180건 · 중복 42건 · 무효 12건
  (표: 단어 / 상태  최대 20행)
  [등록] [취소]
```

`web/static/js/stopwords.js` — `importPreview()` / `importCommit()` 추가, 성공 시 기존 `loadStopwords()`·`loadCategories()`·`updateUI()`·`updateStatistics()` 재호출. 진행 중에는 **버튼만 비활성화**하고 진행 문구를 남긴다(전면 오버레이 금지).

안내 문구(화면): "직원 이름은 두 글자 이상만 반영됩니다", "이미 등록된 단어는 건너뜁니다".

### 4.5 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `STOPWORDS_CONFIG_PATH` 상수화 + 매니저 기본값 연결 | — |
| 2 | `add_stopwords_bulk()` + set 인덱스 | 1 |
| 3 | `POST /api/stopwords/import` (preview/commit) | 2 |
| 4 | 화면·JS 추가 | 3 |
| 5 | (D-1이 A면) `openpyxl` 휠 조달 → `vendor_python_pkgs/` + `requirements.txt` 반영 | — |
| 6 | (D-3이 B면) 이름 전용 파일 분리 + `build_deploy.ps1` `$ExcludeFiles` 추가 | 2 |
| 7 | 테스트(§6) → 사용자 실동작 검증 | 4 |

---

## 5. 영향도 분석

| 파일 | 변경 | 영향 범위 |
|------|------|-----------|
| `src/config/settings.py` | 상수 1개 추가 | 없음(추가만) |
| `src/modules/stopword_manager.py` | 기본 경로 연결, `add_stopwords_bulk` 추가, set 인덱스 | **공통 모듈** — 호출처 전수: `api_routes.py:233/279/304/339/365`, `nlp_analysis.py:121`, `wordcloud_generator.py:295`, 모듈 내부 `:381/:395`. 기존 함수 시그니처·반환값 무변경 |
| `src/routes/api_routes.py` | 라우트 1개 추가 | 기존 6개 라우트 무변경 |
| `web/templates/partials/_stopwords_body.html` | 블록 추가 | `settings_hub.html` 에서만 include |
| `web/static/js/stopwords.js` | 함수 추가 | |
| `deploy/build_deploy.ps1` | (D-3이 B일 때) 제외 파일 1개 추가 | 배포 산출물 |

**동작이 바뀌는 지점**: 불용어가 늘어나면 워드클라우드에서 해당 단어가 사라진다. 이는 의도된 동작이며, **감정 판정(긍/부/중립)에는 관여하지 않는다** — 불용어는 `nlp_analysis`·`wordcloud_generator` 경로에서만 쓰이고 감정 모듈에서는 참조되지 않는다(실측: `grep stopword src/modules/emotion_analysis.py` 해당 없음).

### 5.1 도메인 잠금 점검

| 잠금 | 판정 |
|------|------|
| DL-1 가명화 범위 | 해당 없음 — 가명 치환 로직 무변경. 다만 **불용어에는 실명이 들어간다**(가명화하면 기능이 성립하지 않음) → DL-9로 처리 |
| DL-2 평가 키잉 | 해당 없음 |
| DL-3 배치 복잡도 | **대응함** — `is_stopword` 를 O(n) 리스트 탐색에서 set 조회로 바꾼다(§4.2). 미대응 시 이름 수천 건 등록으로 전체 분석이 느려진다 |
| DL-4 감정 극성 | 해당 없음 — 감정 규칙·모델 무변경. 불용어는 감정 판정 경로에 없음(실측) |
| DL-5 필드 신호 보존 | 해당 없음 |
| DL-7 학습 데이터 위치 | 해당 없음 |
| DL-8 공통 모듈 침범 | `stopword_manager` 는 공통 모듈 — 호출처 전수 Grep 결과를 위 표에 첨부. 기존 함수 동작 무변경 |
| DL-9 원데이터 취급 | **핵심 쟁점** — 실명이 `src/configs/` 에 평문 저장되고 이 폴더는 배포 제외 목록에 없다(`build_deploy.ps1:34-41` 실측). D-3에서 결정 |
| DL-10 완료 판정 | 실동작 검증 후에만 Done |
| DL-12 서버 무단 기동 | 준수 — §6 단위 검증은 서버 없이 수행 |

---

## 6. 테스트/검증 계획

`test/` 폴더: `plans/2026/08/13_02_stopword-import/test/`

| # | 시나리오 | 방법 | 기대 |
|---|----------|------|------|
| T1 | 경로 고정 | CWD를 3곳(app_root / src / 임의 폴더)으로 바꿔 `get_stopword_manager()` 호출 | 세 경우 모두 `src/configs/stopwords.json` 을 읽고 카테고리 8·단어 101 로드 |
| T2 | UTF-8 CSV 임포트 | 이름 20건 CSV(머리글 있음) | added 20, duplicated 0, invalid 0 |
| T3 | CP949(엑셀 기본) CSV | 같은 파일을 cp949로 저장 | T2와 동일 결과 (`parse_csv_with_encoding` 경유) |
| T4 | 중복·무효 혼재 | 기존 단어 3건 + 한 글자 2건 + 빈칸 1건 포함 | duplicated 3, invalid 3, added는 나머지 |
| T5 | dry_run 무변경 | `add_stopwords_bulk(dry_run=True)` 후 사전 재로드 | 파일·메모리 사전 모두 변경 0 |
| T6 | 저장 1회 | commit 중 `save_stopwords` 호출 횟수 계측 | 1회 (단어 수와 무관) |
| T7 | 조회 성능 | 이름 5,000건 등록 후 `is_stopword` 10만 회 호출 시간 측정, 변경 전후 비교 | set 전환 후 상수 시간, 회귀 없음 |
| T8 | 이름 제거 실효 | "홍길동이 보고서를 작성했다" 를 `nlp_analysis` 단어 추출에 통과 | `홍길동` 이 결과에 없음 (2.10 검증) |
| T9 | 텍스트 통째 필터 한계 확인 | 같은 문장을 `filter_stopwords()` 에 통과 | 「홍길동이」가 남음 → R-4를 사실로 기록(수정이 아니라 **한계 명시**) |
| T10 | 엑셀 | D-1=A: .xlsx 20건 업로드 / D-1=B: .xlsx 업로드 | A: T2와 동일 / B: 400 + "CSV로 저장 후 업로드" 메시지 |
| T11 | 잘못된 파일 | 열 없는 파일, 100MB 초과, 확장자 .txt | 각각 400 + 사람이 읽을 수 있는 메시지 |

**실동작 검증(사용자 승인 후, 사용자가 서버 기동)**

1. 불용어 관리 화면에서 실제 직원 명단 파일 업로드 → 미리보기 수치 확인 → 등록.
2. 등록 직후(서버 재시작 없이) 워드클라우드 생성 → 이름이 사라졌는지 확인(2.9·2.10).
3. `src/configs/stopwords.json`(또는 D-3 채택 시 분리 파일)에 실제로 기록됐는지 확인.

---

## 7. 리스크 및 제약

| # | 리스크 | 영향 | 대응 |
|---|--------|------|------|
| R-1 | 실명이 평문 파일로 남고 배포 패키지에 포함 | PII 유출(DL-9) | D-3 (분리 + 배포 제외). 사용자가 A를 택하면 그 결정을 계획서·완료보고에 명시 |
| R-2 | `openpyxl` 미조달 | 엑셀 업로드 불가 | D-1의 B로 자동 축소 + 안내 메시지. 오류를 500으로 흘리지 않는다 |
| R-3 | 이름이 일반 명사와 겹침(예: `한길`, `보람`) | 정상 단어가 워드클라우드에서 사라짐 | 미리보기에서 **기존 사전·일반명사와 겹치는 단어를 경고 표시**. 등록 후 개별 삭제로 회수 가능 |
| R-4 | `filter_stopwords()`(공백 분리)는 조사 결합형을 못 지움 | 이 경로를 쓰는 출력에는 이름이 남을 수 있음 | T9로 사실 확인 후 한계로 명시. 형태소 기반 필터로 바꾸는 것은 **범위 밖**(공통 모듈 동작 변경) |
| R-5 | 대량 등록으로 JSON 파일이 커짐(수천 건) | 로딩·저장 시간 증가 | T7로 계측. 수만 건 이상이면 별도 저장소 검토(범위 밖) |
| R-6 | 싱글톤 캐시와 파일의 불일치(멀티 프로세스 구동 시) | 다른 워커에 반영 지연 | 현재 단일 프로세스 구동 전제. 실동작 검증 2항으로 확인 |

**제약**

- 파일 단위 일괄 삭제(되돌리기)는 범위 밖(2.13).
- 임포트 시 자동 품사 분류는 하지 않는다(D-4).
- 감정 분석 규칙·모델은 이 작업에서 일절 수정하지 않는다.
