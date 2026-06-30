# 0630_02 비건전 단어 substring 오탐 수정 (회사정책→"사정" 욕설 오인)

> 상태: Pre-Done | 작성일: 2026-06-30
> 작업 유형: A — 버그 수정/핫픽스

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-30 | 신규 | 최초 작성 (재현·원인 확정 완료 상태) |
| 2026-06-30 | §5 결과 | 구현·단위검증 완료(Pre-Done). 동음이의어(사정/가슴) 별도 결정 대기 발견 |

---

## 1. 문제 정의

- **관찰된 실패 산출물(실측)**: 입력 `대내외 소통을 통한 회사정책 홍보 능력 탁월`(긍정 문장)을
  `advanced_filter_profanity()`에 넣으면 욕설로 표시됨. 실측 결과:
  - `methods_used = []` — 욕설 2계층(Kiwi 형태소·gap 패턴) 탐지는 **0건**
  - `filtered_text` = `… 회***책 …` — `회사정책` 의 `사정` 구간이 `***`로 치환
  - `detected_profanity = ['사정']` — 비건전 단어 `사정`(射精)이 검출 목록에 적재
- **증상**: 정상 복합어 **회사정책**(회·**사·정**·책) 안의 부분 문자열 `사정`이 비건전 단어로 걸려, 직원이 욕설 사용자로 오집계됨.
- **재현 조건(실제 호출 파라미터 그대로)**:
  ```python
  from src.modules.profanity_filter import advanced_filter_profanity
  advanced_filter_profanity('대내외 소통을 통한 회사정책 홍보 능력 탁월')
  # → detected_profanity == ['사정'], filtered_text 에 '회***책'
  ```
  (서버·배치·GPU 불요. cwd=`wordcloud_project`, `configs/profanity_config.json` 부재 → 기본 내장 리스트 사용.)

## 2. 원인 분석

> ⛔ 원인 확정 게이트 — 3개 모두 충족 확인

1. **재현했다**: 위 §1 실제 입력으로 재현, `detected_profanity=['사정']` 관측.
2. **그 줄이 범인임을 관측했다**: `src/modules/profanity_filter.py` 의 **비건전 단어 분기**가 순수 substring 매칭이다.
   - `advanced_filter_text()` L389–393:
     ```python
     for word in self.unhealthy_words:
         if word in original_text:          # ← 부분 문자열 매칭
             filtered_text = filtered_text.replace(word, "***")
             detected_profanity.append(word)
     ```
   - `filter_text()` L244–249 도 동일 패턴(`if word in text`).
   - `unhealthy_words`(기본 리스트, L94–98)에 성적 의미의 **`사정`** 포함 → `'사정' in '대내외 … 회사정책 …'` == True.
   - 대조: 욕설은 `_detect_by_morpheme`(L137–150, Kiwi 형태소 정확일치)+`_detect_by_gap_pattern`으로 경계를 검사하므로 `회사정책`에서 0건. **비건전 단어 분기만 경계 검사를 안 한다.**
3. **반증 실험**: 비건전 매칭을 형태소/단어경계 기준으로 바꾸면 `회사정책`은 더 이상 안 걸린다(= `사정`이 단독 형태소가 아니므로). 바꿔도 여전히 걸리면 이 가설은 틀린 것.

- **근거**: `src/modules/profanity_filter.py:389-393`(advanced), `:244-249`(basic), 리스트 `:94-98`. 재현 로그 `detected_profanity=['사정']`, `methods_used=[]`.
- **분석**: 코드 주석 "비건전 단어 — substring 유지 (복합어 오탐 위험 낮음)"의 전제가 한국어에서 성립하지 않음. `사정`은 "회사 사정/업무 사정/사정상" 등 일상어이자 다수 복합어의 부분 문자열.
- **회귀 도입 지점**: 욕설 경로는 2계층(Kiwi+gap)으로 개선되었으나(0602/이후), **비건전 단어 경로는 구식 substring 그대로 남음** — 같은 개선이 비건전어에는 미적용.

### 동일 분류의 잠재 오탐 (같은 substring 결함, 코퍼스에서 재발 예상)
- 한글: `사정`(회사정책/회사 사정/사정상), `가슴`(가슴 벅참/가슴 깊이), `젖`(젖다/젖어).
- 영어: `ass`(assessment/class/passion/assist), `butt`(button), `sex`(unisex) — 영어도 substring이라 동일 결함.

## 3. 수정 방안

- **핵심 변경**: 비속어와 **동일한 경계 검사**를 비건전 단어에도 적용 — 한국어는 Kiwi 형태소 정확일치, 영어는 단어경계(`\b`) regex. 순수 substring 제거.
- **세부 수정** (`src/modules/profanity_filter.py`, additive·시그니처 불변·O(n)):
  - `__init__`: 욕설의 `english_profanity_words` 캐싱(L48)과 동형으로 `unhealthy_words`를 **한글/영어로 분리** 캐싱
    (`korean_unhealthy_words`, `english_unhealthy_words`).
  - 신규 내부 메서드 `_detect_unhealthy(text) -> List[(word,start,end)]`:
    - 한글: Kiwi 형태소 토큰 `t.form`이 `korean_unhealthy_words`에 **정확 일치**할 때만 hit(`_detect_by_morpheme`와 동형). Kiwi 미가용 시 fallback은 §리스크 참조.
    - 영어: `re.compile(r'\b'+re.escape(w)+r'\b', re.IGNORECASE)` 로 단어경계 매칭.
  - `advanced_filter_text()` L389–393 교체: `_detect_unhealthy` 결과 span으로 치환·`detected_profanity` 적재.
  - `filter_text()` L244–249 교체: 동일 로직 사용(코드 중복 제거 위해 `_detect_unhealthy` 재사용).
  - `_build_gap_patterns`/`_detect_by_gap_pattern`(욕설 전용)은 **불변**.
- **비변경(범위 밖)**: 비건전 단어를 "욕설"과 별 카테고리로 분리 표기하는 UI/집계 개선은 본 건과 무관 → 제외. 본 건은 *오탐 제거*만.

## 4. 롤백 계획

- 단일 파일(`profanity_filter.py`) 변경 → 해당 커밋 `git revert` 또는 `_detect_unhealthy` 도입분 제거 + L244–249/L389–393 원복.

## 5. 결과 (구현·단위검증 완료 — Pre-Done)

- **적용된 변경** (`src/modules/profanity_filter.py`):
  - `__init__`: `korean_unhealthy_words` + `_english_unhealthy_patterns`(`\b…\b`, IGNORECASE) 캐싱 추가.
  - 신규 `_detect_unhealthy(text)`: 한글=Kiwi 형태소 정확일치, 영어=단어경계. 신규 `_apply_spans(text, spans)`: 우→좌 span 치환(str.replace 미사용 → 복합어 내부 미오염).
  - `advanced_filter_text`·`filter_text`의 비건전 분기를 span 기반으로 교체. 욕설 2계층·시그니처 불변.
- **검증 결과**:
  - 원 버그 `대내외 … 회사정책 … 탁월` → `detected_profanity == []`(이전 `['사정']`). 토큰 `회사`/`정책` 분리로 `사정` 미검출 관측.
  - 복합어 오탐 회귀 8건(회사정책·assessment·class/passion·button·회사 사정·사정상·가슴 벅찬·젖은) **0** PASS. 정탐 1건 유지. (`test/test_unhealthy_boundary.py`)
  - 기존 `src/configs/test_cases/profanity_cases.json` 12건 중 11건 PASS, 1건(`pf-06 '씨1발점은'`)은 **HEAD 원본도 동일 False = 본 수정과 무관한 기존 동작**(gap 패턴 `발(?![가-힣])`가 후행 `점`에 막힘). 회귀 0.
  - `py_compile` OK.
- **동음이의어 결정 반영(2026-06-30)**: 사용자 결정에 따라 `사정`(circumstances)·`가슴`(emotion)·`젖`(젖다)을 `unhealthy_words` 기본 리스트에서 **제거**(`_load_config` 기본 딕셔너리). 형태소로 성적 의미 구분 불가하고 HR 코퍼스에선 무해 빈도 압도적 → 오탐 제거 우선. 위 회귀 8건에 4건(회사 사정·사정상·가슴·젖) 추가해 0 확인.
- **운영 반영 검증 대기(Done 승격 조건)**: 내부망에서 메타데이터 재생성 → 욕설 목록에 `사정`/`가슴`/`젖`/`회사정책` 류 미적재 확인 시 `Done` 승격.

---

## 영향도 분석

- **호출 경로**(grep 실측): `advanced_filter_profanity`는 `metadata_manager.py:83`, `sentence_emotion.py:39`, `perspective_service.py:2860`, `test_routes.py:14`에서 사용. 모두 `detected_profanity`/`filtered_text` 소비 → 오탐 1건 제거가 일관 반영됨.
- **DB 영향**: 신규 메타데이터 생성분부터 `profanity_employees`/`profanity_sentences`에 `사정` 류 오탐 미적재. 기존 적재분은 본 수정 대상 아님(사용자 재생성 시 정정).
- **성능**: Kiwi tokenize는 욕설 경로에서 이미 1회 수행 → 토큰 재사용 가능. O(n) 유지.

## 테스트 계획

- 골든/회귀 케이스 추가 (`plans/2026/0630_02_unhealthy-substr-fp/test/test_unhealthy_boundary.py` 신규):
  - (오탐 0 검증) `회사정책`, `회사 사정으로 지연`, `사정상 불가`, `가슴 벅찬 성과`, `assessment`, `class`, `passion` → **검출 0**.
  - (정탐 유지 검증) 실제 비건전어 단독 사용 문장 → **검출 1**(리스트 단어가 형태소/단어로 등장하는 경우).
  - 긍정 문장 회귀: §1 원문 → `detected_profanity == []`.
- 기존 `src/configs/test_cases/profanity_cases.json` 회귀 전부 통과 확인(욕설 2계층 불변).

## 리스크

- **Kiwi 미가용 fallback**: 운영/개발 모두 Kiwi 로드 확인됨(재현 시 경고 없음). 만약 미가용이면 한글 비건전어는 (a) 검출 생략 또는 (b) 양옆 한글 경계 검사 substring 중 택1 — 기본은 **(a) 생략**(오탐<미탐, 핵심가치=긍↔부 오분류 0과 별개로 욕설 오탐 0 우선). 구현 시 결정.
- **정탐 누락 가능성**: 형태소 정확일치로 바꾸면 띄어쓰기/변형 회피(`사 정`)는 욕설처럼 gap 패턴이 없어 놓칠 수 있음 — 비건전어는 본래 회피 표기가 드물고, 오탐 제거 이득이 큼. 필요 시 후속 작업으로 gap 패턴 확장(범위 밖).

## 검증 (end-to-end)

1. `python plans/2026/0630_02_unhealthy-substr-fp/test/test_unhealthy_boundary.py` → 전 케이스 PASS(오탐 0·정탐 유지).
2. `advanced_filter_profanity('대내외 소통을 통한 회사정책 홍보 능력 탁월')` → `detected_profanity == []`, `filtered_text == 원문`.
3. 기존 `profanity_cases.json` 욕설 케이스 회귀 통과(2계층 불변).
4. 서버·배치·GPU 미사용, O(n), 시그니처 불변 확인.

## 불변 제약

긍↔부 오분류와 무관(욕설 오탐 제거) · additive·레거시 시그니처 불변 · O(n) · 서버 무단 실행 금지 · plans/test는 배포 제외.

## 핵심 파일

- `src/modules/profanity_filter.py` — `_detect_unhealthy` 신규 + L244-249·L389-393 교체 + `__init__` 캐싱 분리
- `src/configs/test_cases/profanity_cases.json` — 기존 회귀(불변 확인)
- `plans/2026/0630_02_unhealthy-substr-fp/test/test_unhealthy_boundary.py` — 신규 골든·회귀
