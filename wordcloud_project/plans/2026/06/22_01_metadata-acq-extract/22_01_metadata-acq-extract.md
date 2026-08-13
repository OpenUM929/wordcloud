# 계획서 — 메타데이터 시점 문장 추출 → LLM 핸드오프 코퍼스(인라인)

> 상태: Pre-Done | 작성일: 2026-06-22
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 데이터셋 누적 — `wordcloud_project/plans/_datasets/kote_finetune/RUNBOOK.md` (감정 스트림 연계)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-22 | 최초 작성 | 메타데이터 시점 문장+KoTE 직추출(별도 버튼·DB 적재) 설계 |
| 2026-06-22 | 트리거·저장대상 전면 개정 | 별도 버튼 → **인라인(배치 저장 중)**, 저장대상 → **압축 JSONL 핸드오프 파일**(LLM 분석용, 최소 토큰) |
| 2026-06-22 | 감정 해상도 추가 | 3버킷만으론 감정분석 시 KoTE 재실행 필요 → **top-3 감정(`e`) 포함**으로 재실행 회피. `compute_sentence_raw_scores`가 top_3 보존하도록 확장 |
| 2026-06-22 | DB 적재 결정 확정 | 용도=LLM 재학습. **파일만 유지**(DB 미적재) 확정 — DB는 export 단계만 추가돼 토큰 손해, dedup 이점은 batch_id별 파일 overwrite로 흡수 |
| 2026-06-22 | 구현 완료(코드) | 캐시 top3 확장·핸드오프 라이터·인라인 훅·UI·단위테스트 완료. 단위테스트 4종 ALL PASS. **실배치 검증 전이라 PND 유지** |
| 2026-06-22 | 상태 | Kanban PDN 도입에 따라 PND → PDN 전환. 실배치 검증 대기 중 |

---

## 구현 결과 (코드 완료, 실동작 검증 대기)

**변경/신규 파일**

| 파일 | 내용 |
|------|------|
| `src/modules/sentence_emotion.py` | `compute_sentence_raw_scores`가 `top3`(=`mapped.top_3` 압축 `[[label,conf],...]`) 보존. 영어 우회·예외 시 `[]`. 추가 추론 0 |
| `src/services/acquired_handoff.py` (신규) | `resolve_handoff_path`(루트 강제·세그먼트 안전화), `build_records_from_metadata`(캐시 재사용·부호→p/n/u·top3 전달), `append_handoff_records`(레전드 1줄+x/y/s/e, 2자리, resume 시 레전드 비중복) |
| `src/services/batch_processor.py` | 메인 루프 upsert 직후 인라인 훅(`_acq_handoff_enabled`/`_acq_handoff_label`). 단일 스레드 구간이라 파일 append 동시쓰기 안전 |
| `web/templates/metadata_batch.html` | "핸드오프 코퍼스 적립" 토글 + 대상 라벨 입력 |
| `web/static/js/metadata_batch.js` | settings에 `acq_handoff_enabled`/`acq_handoff_label` 포함 |
| `plans/2026/0622_01_.../test/test_handoff.py` (신규) | 단위테스트 4종 (경로탈출·스키마/반올림·resume멱등·라벨매핑) — **ALL PASS** |

**설계 대비 단순화(실측 후 확정)**
- 핸드오프 파일은 `x/y/s/e`만 담아 **id 불필요** → `db_id` 부여 타이밍 의존 제거. INSERT 직후가 아니라 **메인 루프 upsert 직후**(cache+metadata 메모리 상주)에서 처리. §2.3의 db_id 제약은 해소됨.
- 라벨 산출은 `_get_sentence_level_scores` 재사용(그룹분석과 동일 매핑). 메인 스레드에서 호출하므로 워커에 matplotlib 미유입.
- 레전드에서 `n`(문장수) 제외 — 스트리밍 append와 부적합, 파싱에 불필요.

**잔여(사용자 실동작 검증 후 DN):**
- [ ] 운영망에서 소규모 배치 실행 + 적립 토글 on → `plans/_datasets/kote_finetune/emotion/handoff/<label>/<batch_id>.jsonl` 생성 확인
- [ ] 생성 파일을 Claude가 읽어 레전드만으로 키 해석 가능한지 확인
- [ ] (dev 불가: CSV만·배치 실행 불가 — 운영망에서만 검증)

---

## 1. 배경 및 목적

다면 평가 문서를 **문장별 + KoTE 결과**로 정리하는 데 필요한 문장 단위 KoTE 원시 점수는 **이미 메타데이터 생성 시점에 계산·저장**된다:

- `metadata_manager.py:79` — `analyzed_eval['sentence_emotion_cache'] = compute_sentence_raw_scores(doc)`

따라서 그룹 분석 테스트를 별도로 돌릴 필요 없이, **배치 저장 흐름 안에서** 문장을 함께 추출하면 재읽기 패스 없이 거의 무비용으로 코퍼스를 얻을 수 있다.

**목적**: 배치 메타데이터가 저장되는 시점에, 모든 문장을 KoTE 결과와 함께 **압축 JSONL 핸드오프 파일**로 함께 기록한다. 이 파일은 **Claude(LLM)에게 그대로 전달해 감정 규칙 마이닝·KoTE 분류 검증·신규 감정/리더십 군집 발굴에 사용**하는 것이 1차 용도이며, 따라서 **LLM이 정확히 파싱하면서 토큰/데이터량이 최소**인 구조여야 한다.

**감정 해상도 — 재실행 회피**: pos/neg/neutral 3버킷만 담으면 감정 단위 분석 시 KoTE를 다시 돌려야 한다. 그러나 KoTE 후처리는 문장마다 **`top_3`(매핑된 44개 감정 중 상위 3개 + confidence)** 를 이미 계산한다(`emotion_analysis.py:177-189`). 이를 핸드오프에 함께 담으면 **추가 추론 0으로 감정 해상도를 확보**하여 분석 시 재실행이 사실상 불필요해진다.

> 본 코퍼스는 KoTE 파인튜닝 감정 스트림의 원천이다(RUNBOOK §누적). 가명화·정제·배포제외 규약을 따른다.

---

## 2. 현재 시스템 분석 (코드 실측)

### 2.1 문장 캐시 생성·영속

- `src/models/metadata_manager.py`
  - `create_employee_metadata(...)` → 각 평가에 `sentence_emotion_cache` 부여 (L79)
  - `save_employee_metadata` (L134) / `save_individual_metadata` (L170) → `processed_data` 배치 폴더에 영속
  - `load_employee_metadata` (L227)

### 2.2 캐시 → 문장별 라벨 산출 (그룹 분석과 공유)

- `src/services/perspective_service.py`
  - `_get_sentence_level_scores(doc, threshold=0.20, weight=2.0, corrections=None, sentence_cache=None)` (L1076)
    - `sentence_cache` 제공 시 **KoTE 재실행 없이** 캐시 사용
    - 반환: `[(sent, score, pos, neg, neutral), ...]`
  - `sentence_sentiment_override(...)` (L516) — 반전 규칙 적용 점수

### 2.3 `db_id` 부여 시점 (인라인 부착 지점 결정 요소)

- `_db_id`(=evaluations DB row id)는 **DB INSERT 시 부여**되어, 이후 DB에서 다시 읽을 때만 평가 객체에 채워진다 (`perspective_service.py:809·822·918·923`).
- ∴ 순수 in-memory 생성 시점(L79)에는 `db_id`가 아직 없을 수 있다 → **인라인 추출 훅은 evaluations DB INSERT 직후**(여전히 배치 저장 경로 내부)에 두어, `sentence_emotion_cache`와 `db_id`가 동시에 메모리에 있는 상태에서 재읽기 없이 처리한다.
- ※ 구현 1단계에서 배치 저장 경로의 정확한 INSERT 위치를 실측 확인한다(현재 미확인 — `batch_processor`/`metadata` 저장 경로 추적 필요).

### 2.4 KoTE top_3 가용성 + 현재 캐시의 손실

- `compute_sentence_raw_scores(doc)` (`src/modules/sentence_emotion.py`)는 KoTE 결과에서 **`mapped.sentiment_scores`(pos/neg/neutral)만** 추출해 캐시하고, **`mapped.top_3`(상위 3개 감정)는 버린다** (L52-57).
- 따라서 현재 `sentence_emotion_cache`에는 감정 어휘가 없음 → 감정 단위 분석 시 재실행 불가피.
- **확장 필요**: `compute_sentence_raw_scores`가 `top_3`(label, sentiment, confidence)도 dict에 보존하도록 한다. 생성 시점엔 이미 계산된 값이라 **추가 추론 비용 0**. (기존 배치 캐시엔 없음 → 신규 배치부터 `e` 채움)

### 2.5 저장 위치 제약 (배포 유출 방지)

- CLAUDE.md / 메모리 `project_dataset_doc_placement`: 학습·분석 데이터는 **`plans/_datasets/kote_finetune/` 외 위치 금지**. `plans/`는 배포 제외 폴더.
- ∴ "사용자 지정 폴더"는 자유 경로가 아니라 **위 데이터셋 폴더 하위 서브폴더/라벨 지정**으로 한정한다.

---

## 3. 구현 상세

### 3.1 핸드오프 코퍼스 포맷 (LLM 전달용, 최소 토큰)

- 형식: **JSONL**(append-only, 줄 단위 안전 파싱, 쉼표·따옴표 이스케이프 안전)
- **1줄차 = 레전드/메타** (사이드카 없이 파일만으로 키 의미 인식):
  ```
  {"#":"x=문장, y=라벨(p=긍/n=부/u=중), s=[pos,neg,neu], e=top3감정[[명,점],...]","batch":"<batch_id>","n":<문장수>}
  ```
- **2줄차~ = 문장당 1줄**:
  ```
  {"x":"맡은 업무를 성실히 수행함","y":"p","s":[0.78,0.04,0.18],"e":[["뿌듯함",0.81],["인정/신뢰",0.55],["기쁨",0.42]]}
  ```
- 필드: `x`(문장), `y`(override 라벨 p/n/u), `s`([pos,neg,neu] 소수 2자리), `e`(KoTE top-3 `[감정명, confidence]`). **ids·context·override_score 등은 핸드오프 파일에서 제외**(필요 시 DB에만 보관) → 한 줄 ≈ 55~75토큰.
- 텍스트는 **가명화 완료본만** 기록.

### 3.2 백엔드

**캐시 확장 — `compute_sentence_raw_scores` (`src/modules/sentence_emotion.py`)**

- 각 문장 dict에 `top3`(= `mapped.top_3`의 `[[label, confidence], ...]` 압축형) 보존 추가. 추가 추론 0(이미 계산됨). 영어 우회 문장은 `top3=[]`.

**신규 모듈/함수 — 핸드오프 라이터**

```
# 예: src/services/acquired_handoff.py (또는 perspective_service 내)
def append_handoff_records(dest_label, batch_id, records):
    """records: [(sentence, label, pos, neg, neutral, top3), ...]
    → plans/_datasets/kote_finetune/emotion/handoff/<dest_label>/<batch_id>.jsonl 에
      레전드 1줄 + 문장 1줄/레코드(x/y/s/e)로 append. 경로는 데이터셋 루트 하위로 강제(검증).
    """
```

**인라인 훅 — 배치 저장 경로**

- 배치 저장에서 평가가 DB INSERT되어 `db_id`가 부여된 직후, 평가별:
  - `_get_sentence_level_scores(doc, sentence_cache=ev['sentence_emotion_cache'], corrections=None)`로 문장별 `(sent, score, pos, neg, neutral)` 산출 (KoTE 재실행 0)
  - `score` 부호 → 라벨 매핑(>0 p / <0 n / ==0 u) ※기존 그룹분석 라벨 매핑과 동일성 실측 확인
  - `append_handoff_records(...)`로 누적
- **사전 지정**: 배치 시작 전 `dest_label`(저장 대상 서브폴더/라벨)을 설정값으로 받는다. 인라인·자동 실행이므로 클릭 시점 선택은 없다.
- **성능**: 데이터 메모리 상주 상태에서 라벨 계산 + 파일 append뿐 → 이미 수행한 KoTE 추론 대비 마진 비용 무시 가능. 재읽기 패스 없음(O(n)).

### 3.3 프론트엔드 (배치 시작 설정)

- 배치 생성 시작 화면(메타데이터/배치)에 **"핸드오프 코퍼스 적립" 토글 + 대상 라벨(`dest_label`) 입력**을 추가.
- 기본값: 토글 on 시 `dest_label` 기본 = `default`. 경로 루트는 고정(데이터셋 폴더), 사용자는 라벨만 지정.
- 차단 규칙 준수(메모리 `feedback_busy_disable_not_block`): 인라인 적립은 배치 진행에 묻어가므로 별도 장시간 차단 없음. 진행 표시는 기존 배치 진행 배너에 적립 건수만 부가.

---

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 배치 저장 경로의 evaluations DB INSERT 지점 + `sentence_emotion_cache` 잔존 여부 실측 확인 | - |
| 2 | `compute_sentence_raw_scores`가 `top_3` 보존하도록 확장(추가 추론 0) | - |
| 3 | `append_handoff_records` 라이터(경로 루트 강제·레전드·x/y/s/e append) 구현 | 2 |
| 4 | score→라벨 매핑이 그룹분석과 동일한지 실측 확인 | - |
| 5 | INSERT 직후 인라인 훅 연결(평가별 산출→append) | 1,3,4 |
| 6 | 배치 시작 UI: 적립 토글 + `dest_label` 입력 | 5 |
| 7 | 단위 테스트(캐시 주입 → 핸드오프 줄 x/y/s/e 스키마·라벨·자릿수 검증, 서버 불요) | 3 |
| 8 | 실동작 검증(소규모 CSV 배치 → 파일 생성 확인 → 내가 파싱) 후 DN 전환 | 5,6,7 |

---

## 5. 영향도 분석

| 파일 | 변경 | 영향 범위 |
|------|------|-----------|
| `src/modules/sentence_emotion.py` | `compute_sentence_raw_scores`에 `top_3` 보존 추가 | 캐시 dict 필드 +1(신규 배치). 그룹분석은 기존 키만 읽으므로 무영향 |
| 배치 저장 경로(`batch_processor`/`metadata` 저장부 — 1단계 실측 확정) | INSERT 직후 인라인 훅 추가 | 배치 저장 흐름 +1 단계(조건부) |
| `src/services/acquired_handoff.py`(신규) 또는 `perspective_service.py` | 라이터 함수 신규 | 파일 출력 신규 |
| 배치 시작 템플릿(메타데이터/배치 화면) | 토글 + 라벨 입력 | 설정 UI |

- 기존 그룹 분석 추출·`acquired_sentences` DB 경로는 **변경 없이 병존**.
- DB 스키마 변경 없음. 핸드오프 파일은 데이터셋 폴더에만 생성.

---

## 6. 테스트/검증 계획

- **단위(서버 불요)**: `sentence_emotion_cache` 주입 가짜 평가 → 핸드오프 줄의 `x/y/s`, 라벨 부호, 소수 2자리, 레전드 1줄 구조 검증. (`test_metadata_override.py` 패턴, 저장 `test/`)
- **동등성**: 동일 배치를 그룹분석 경로로 본 라벨과 핸드오프 `y` 라벨 집합 일치.
- **멱등성/누적**: 재실행 시 append 정책(중복 줄 처리 방식) 정의·검증 — batch_id별 파일 단위 재생성(overwrite) 권장.
- **LLM 파싱**: 생성 파일을 실제로 내가 읽어 레전드만으로 키 해석이 되는지 확인.
- **실동작**: 소규모 CSV 배치 → 적립 토글 on → 파일 생성·내용 확인. (메모리 `feedback_dn_after_runtime_verify`: 실동작 후에만 DN)

> ⚠️ 서버 실행은 사용자 허락 후에만(메모리 `feedback_no_server_start`). 본 계획은 안내까지만.

---

## 7. 리스크 및 제약

- **db_id 시점**: in-memory 생성 시점엔 부재 가능 → INSERT 직후 훅으로 해결(§2.3). 1단계 실측 미확인 시 잘못된 지점 부착 위험.
- **라벨 매핑 일치**: 그룹분석과 동일 매핑 확인 필수(불일치 시 코퍼스 라벨 오염).
- **데이터량(전량)**: 1.9만명 전 문장 → 파일 큼. JSONL 압축 스키마로 토큰 최소화. batch_id별 분할로 관리·전달 단위 확보.
- **감정 해상도 vs 토큰**: `e`(top-3) 포함으로 한 줄 ≈ 55~75토큰(3버킷만일 때의 약 2배). 재실행 회피와의 균형으로 채택(사용자 결정). 더 줄이려면 top-1로 축소 가능하나 분석 해상도 저하.
- **기존 배치 캐시 비호환**: 기존 `sentence_emotion_cache`엔 `top_3` 없음 → 과거 배치 핸드오프는 `e=[]`이거나 재실행 필요. **신규 배치부터** 완전한 `e` 확보.
- **배포 유출 방지**: 출력 루트를 `plans/_datasets/kote_finetune/` 하위로 **강제 검증**(자유 경로 금지). 가명화 텍스트만.
- **dev 제약**: 원데이터 배치 불가, CSV만(메모리 `project_dev_no_batch_csv_only`). 대규모 실측은 운영망에서만.

---

## 결정 필요 / 확인된 사항

- [x] 추출 범위: **전량 저장** (2026-06-22)
- [x] 트리거: **인라인(배치 저장 중 함께) + 대상 사전 지정** (2026-06-22)
- [x] 저장 대상: **압축 JSONL 핸드오프 파일**(LLM 전달용·최소 토큰), 데이터셋 폴더 하위 `dest_label` 서브폴더 (2026-06-22)
- [x] 저장 위치: **`plans/_datasets/kote_finetune/` 하위**(plans 하위, 배포 제외, 상시 누적이므로 일회성 plans 폴더 아님) (2026-06-22)
- [x] 감정 해상도: **top-3 감정(`e`) 포함** — 재실행 회피 우선 (2026-06-22)
- [x] DB 적재 여부: **파일만 유지(DB 미적재)** (2026-06-22)
  - 용도가 **LLM(나)을 통한 재학습**이므로 내가 직접 소비하는 토큰이 기준. 압축 JSONL은 **그대로 전달=그대로 파싱**이라 최소 토큰.
  - DB(acquired_sentences)의 실익은 ① UNIQUE 자동 dedup ② 습득데이터 게시판 노출뿐. ①은 **batch_id별 파일 overwrite로 동등 처리**(§6 멱등성), ②는 본 용도에 불필요.
  - DB로 가면 내가 보려면 결국 텍스트 export가 필요 → 컬럼 오버헤드 + 단계 추가로 **토큰·작업 모두 손해**. → 파일만 채택.

---

## 8. 실동작 검증 절차 (사용자 직접 수행 — 내부망)

> dev는 배치 실행 불가(CSV만, [[project_dev_no_batch_csv_only]])이므로 **내부망에서만** 수행한다.
> 이 절차를 통과해야 DN 전환([[feedback_dn_after_runtime_verify]]). 서버 기동은 사용자가 직접([[feedback_no_server_start]]).

### 8.0 사전 준비
1. 변경 코드 배포: 프로젝트 루트에서
   ```
   .\deploy\build_deploy.ps1
   ```
   - 포함 파일: `src/modules/sentence_emotion.py`, `src/services/acquired_handoff.py`(신규), `src/services/batch_processor.py`, `web/templates/metadata_batch.html`, `web/static/js/metadata_batch.js`
   - `plans/` 는 배포 제외이므로 핸드오프 출력 폴더·테스트는 패키지에 안 들어감(정상). 출력 폴더는 실행 시 자동 생성됨.
2. 내부망 서버 기동(직접). 브라우저 캐시 때문에 JS가 옛 버전일 수 있으니 **메타데이터 배치 화면에서 Ctrl+F5(강력 새로고침)**.

### 8.1 정상 케이스 — 적립 ON
1. 메타데이터 배치 → **1~3단계** 평소대로 진행(CSV 업로드·필드 매핑).
2. **4단계 "배치 처리 및 저장"** 화면에서 새 카드 확인:
   - ☑ **"핸드오프 코퍼스 적립 (감정 규칙 학습용)"** → **체크**
   - **"적립 대상 라벨"** 입력란에 식별용 라벨 입력(예: `test1`). 비우면 `default`.
3. **배치 처리 시작**. (소규모 CSV 권장 — 5~20명이면 충분)
4. 처리 진행 중 배너/콘솔에서 진행이 멈추지 않는지 확인(적립은 기존 흐름에 묻어감).
5. 완료 후 **파일 생성 확인**. 내부망 서버의 다음 경로:
   ```
   <설치경로>\wordcloud_project\plans\_datasets\kote_finetune\emotion\handoff\test1\<batch_id>.jsonl
   ```
   - `<batch_id>` 예: `batch_20260622_1` (4단계 완료 후 결과/이력 화면에 표시되는 배치 ID와 동일)
   - 파일이 없으면 → 8.5 트러블슈팅.

### 8.2 파일 내용 검증 (메모장/VS Code로 열기)
- **1줄차(레전드)** 가 다음 형태인지:
  ```json
  {"#":"x=문장, y=라벨(p=긍/n=부/u=중), s=[pos,neg,neu], e=top3감정[[명,점],...]","batch":"batch_20260622_1"}
  ```
- **2줄차~** 가 문장당 1줄, 다음 형태인지:
  ```json
  {"x":"맡은 업무를 성실히 수행함","y":"p","s":[0.78,0.04,0.18],"e":[["뿌듯함",0.81],["인정/신뢰",0.55],["기쁨",0.42]]}
  ```
- 체크리스트:
  - [ ] **줄 수** = 레전드 1줄 + (배치 전체 문장 수). 한 줄이라도 깨진 JSON 없는지(각 줄이 `{`로 시작 `}`로 끝).
  - [ ] `x` 가 **가명화 완료 텍스트**인지(실명·실 사번이 노출되면 즉시 중단·보고).
  - [ ] `y` ∈ {`p`,`n`,`u`} 만 존재.
  - [ ] `s` 는 소수 2자리 3개 `[pos,neg,neu]`.
  - [ ] `e` 가 이번 신규 배치 문장마다 채워짐(한국어 문장 기준). **영어 문장은 `e:[]` 정상**.

### 8.3 라벨 정합성 교차 확인 (긍↔부 오분류 방지 — 최우선)
> 코퍼스 신뢰의 핵심. `y` 라벨이 기존 그룹분석 결과와 어긋나면 학습 데이터가 오염된다([[project_sentiment_core_value]]).
1. 같은 배치를 **그룹 분석 테스트**(또는 제출용 저장 결과의 긍/부/중 문장 탭)로 연다.
2. 표본 5~10문장을 골라 그룹분석의 긍/부/중 분류와 핸드오프 `y`(p/n/u)를 **1:1 대조**.
   - [ ] **긍↔부 뒤바뀐 문장이 0건**인지(이게 가장 중요 — 1건이라도 있으면 보고).
   - [ ] 중립↔긍/부 차이는 허용 범위([[project_sentiment_core_value]]: 긍↔부만 치명적).

### 8.4 회귀·OFF 케이스
1. **적립 OFF**: 토글을 **끄고** 동일 절차로 배치 1건 → 기존과 100% 동일 동작인지(핸드오프 파일이 새로 안 생기는지). 훅은 `acq_handoff_enabled`일 때만 실행되므로 OFF면 영향 0이어야 함.
2. **resume(이어서 처리)**: 같은 라벨·같은 배치로 이어서 처리 시, jsonl에 **레전드가 중복으로 다시 안 적히고** 문장만 이어붙는지(1줄차만 레전드인지 확인).

### 8.5 트러블슈팅 (안 될 때 수집할 것)
- 파일 자체가 없음 → 서버 로그에서 `핸드오프 적립 실패(<직원id>): ...` 경고 검색. 그 메시지 전문을 전달.
- 토글이 화면에 안 보임 → JS 캐시. **Ctrl+F5** 후 재시도. 그래도 없으면 배포에 `metadata_batch.html/js`가 반영됐는지 확인.
- `e`가 전부 `[]` → 기존(구버전) 캐시로 만든 배치일 가능성. **새로 생성한 배치**에서 확인(과거 배치 캐시엔 top_3 없음).
- 권한/경로 오류 → 출력 루트(`plans/_datasets/kote_finetune/...`)에 서버 프로세스 쓰기 권한 있는지.

### 8.6 검증 완료 후
- 위 8.1~8.4 통과 + 생성된 `.jsonl` **1개를 Claude에게 전달** → 레전드만으로 파싱되는지 최종 확인 → **DN 전환**.
- 전달 시 원천 식별자 없는 가명화본인지 한 번 더 확인(파일이 `plans/` 밖으로 새지 않도록).
