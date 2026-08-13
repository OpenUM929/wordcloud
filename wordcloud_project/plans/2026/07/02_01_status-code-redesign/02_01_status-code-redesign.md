# 0702_01 — 판정 패킷 상태 코드 체계 재설계 및 DB 반영 버튼 추가

> 상태: Todo | 작성일: 2026-07-02 | 작업 유형: type-B 신규 기능 + type-C 설계
>
> 선행: 0701_03_needs-human-bridge (판정 패킷 ↔ 그룹검토 게시판 통합, Pre-Done)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-02 | 전면 | 최초 작성 |
| 2026-07-02 | §3.1.3·3.1.4·3.2.2·3.2·3.7·구현순서·리스크 | 코드 대조 검토 반영: ①리다이렉트 발화 시점을 apply-db 응답으로 이동 ②레거시 3→human_decision 분기 ③group-review load/save 갱신 단계 추가 ④resolve_item 순수화(인플레이스 변조 제거) ⑤_doc/_stages 동시 갱신 ⑥_status_codes 라벨 정정 ⑦setInterval 폴링 제거 |
| 2026-07-02 | §3.3.2·3.4.5·3.6.2·3.7·구현순서 | 프론트 실소스 대조 보정(옵션 무관): ⑧실함수명 `loadFiles(done)`(loadFileList 아님) ⑨IIFE 스코프—인라인 onclick 폐기·addEventListener 와이어링 ⑩jaApplyDbBtn/grApplyDb 이벤트 등록 단계 명시 ⑪summaryHtml에 ai_ready/human_ready 표기 추가 |

## 요구사항 원자화

> 지침 `03.plan-mode.md` §14. 각 원자 질문에 예측 답(기대) 제시 → 사용자 재확인 후 작업.
> **기대(N확인 필요)** = 사용자 확인 후 확정.

### 질문 1: 상태 코드 체계 개편

| # | 원자 질문 | 기대 (예측) | 작업 후 답 (근거) |
|---|-----------|-------------|------------------|
| 1.1 | 새 상태 코드는 현재 요구사항(1=AI대기, 2=Human대기, 3=AI작업완료, 4=Human작업완료, 10=AI DB반영완료, 11=Human DB반영완료)을 그대로 숫자만 유지하는가, 아니면 완전히 새 체계(예: 100단위)로 갈아타는가? | N확인 필요 — 아래 §3 설계안에서 선택지 제시 | |
| 1.2 | 기존 패킷 파일(legacy status=3)은 런타임 매핑으로 처리할지, 일회성 마이그레이션 스크립트로 일괄 변환할지? | 런타임 매핑(하위 호환) — 기존 파일 영향 없음 | |

### 질문 2: 그룹검토 게시판 → Human 판정 저장 시 status 값

| # | 원자 질문 | 기대 (예측) | 작업 후 답 (근거) |
|---|-----------|-------------|------------------|
| 2.1 | `update_packet_decisions()`에서 valid label(positive/negative/neutral) 저장 시 status를 얼마로 설정하는가? | **4** (Human 작업 완료) — 기존 `3`에서 `4`로 변경 | |
| 2.2 | `not_group`/`skip` 저장 시 status를 얼마로 설정하는가? | **2** (Human 대기 유지) — 기존과 동일, DB 반영 대상 아님 | |

### 질문 3: "DB에 반영" 버튼 활성화 조건

| # | 원자 질문 | 기대 (예측) | 작업 후 답 (근거) |
|---|-----------|-------------|------------------|
| 3.1 | judgment_apply 페이지에서 "DB에 반영" 버튼은 어떤 조건에서 활성화되는가? | **status 3 (AI 작업 완료)이 존재할 때** — AI 판정 완료 항목을 DB에 반영 | |
| 3.2 | group_review 페이지에서 "DB에 반영" 버튼은 어떤 조건에서 활성화되는가? | **status 4 (Human 작업 완료)가 존재할 때** — Human 판정 완료 항목을 DB에 반영 | |
| 3.3 | "DB에 반영" 버튼 클릭 시 status 3→10, 4→11로 전이하는가? | **Y** — DB에 쓰고 status 변경 | |

### 질문 4: 팝업 → 그룹검토 리다이렉트 조건

| # | 원자 질문 | 기대 (예측) | 작업 후 답 (근거) |
|---|-----------|-------------|------------------|
| 4.1 | judgment_apply에서 "10만 존재할 경우"의 정확한 의미는? | **packet에 status 10은 있지만 status 11은 없는 경우** — AI DB 반영 완료 Item만 있고 Human DB 반영 완료는 없음 (=Human 쪽이 아직 안 끝남) | |
| 4.2 | 이 팝업은 judgment_apply의 업로드 후에만 뜨는가, 재적용 후에도 뜨는가? | **둘 다** — `api_judgment_apply()` 응답에 `redirect_to_group_review` 플래그 포함 | |
| 4.3 | 팝업 확인 시 group_review 페이지로 이동할 때 어떤 방식으로 파일을 전달하는가? | **URL 쿼리 파라미터** `?file=...` 또는 `sessionStorage` — group_review JS가 읽어서 자동 선택 | |
| 4.4 | group_review 페이지로 이동한 후, 해당 파일이 이미 로드된 상태여야 하는가? | **Y** — 드롭다운에서 자동 선택 + loadFile() 자동 호출 | |

### 질문 5: `apply_judgment_packet()` 동작 변경

| # | 원자 질문 | 기대 (예측) | 작업 후 답 (근거) |
|---|-----------|-------------|------------------|
| 5.1 | `apply_judgment_packet()`은 어떤 status만 DB에 반영하는가? | **312, 322 (10→AI, 11→Human의 새 코드 기준)** — 즉 "DB 반영 완료" 상태만. 212/222(3,4→작업완료)는 집계만 하고 DB 쓰지 않음 | |
| 5.2 | 반영되지 않은 status 3/4 항목은 응답에 별도 집계 필드로 포함하는가? | **Y** — 기존 `pending_ai`/`pending_human`에 추가로 `ai_ready`/`human_ready` 필드 반환 | |

## 배경 및 목적

### 현재 상황

0701_03으로 판정 패킷과 그룹검토 게시판이 `status`(1/2/3)로 통합되었다.
하지만 사용자 피드백에 따르면:

1. **상태 코드가 의미상 2단계만 표현** (1=대기, 2=대기(사람), 3=확정) → 실제 작업 흐름(AI 판정 완료 vs Human 판정 완료 vs DB 반영 완료)을 구분 못 함
2. **"DB 반영"이 항상 `apply_judgment_packet()` 호출 순간 결정됨** → 사용자가 DB 반영 시점을 선택할 수 없음
3. **AI 작업만 완료되고 Human 작업이 남은 상태를 UI에서 감지/안내하지 못함**

### 목적

1. 상태 코드를 **작업 주체(AI/Human) × 작업 단계(대기/완료/반영완료)** 의 2차원으로 확장하여 유의미한 상태 표현
2. "DB에 반영"을 **사용자 버튼 클릭**으로 분리하여 DB 반영 시점을 사용자에게 위임
3. AI 작업 완료 시나리오에서 Human 작업 필요를 UI가 자동 감지하여 안내/리다이렉트
4. **향후 확장**(2차 검토, QA, 앙상블 AI 등)에 대비한 상태 코드 체계 설계

## 현재 시스템 분석

### 현재 상태 코드 (0701_03)

| 값 | 의미 | 설명 |
|----|------|------|
| 1 | AI 판정 대기 | 추출 직후, AI가 아직 판정하지 않음 |
| 2 | 사람 판정 대기 | AI가 확신 못해 Human에게 넘김 |
| 3 | 확정 (DB 반영 대상) | AI가 확신 또는 Human이 판정 완료 |

### 흐름

```
추출 → status=1 → AI 판정(ai_reference 채움)
  ├─ 확신 → status=3 → apply_judgment_packet() → DB 반영
  └─ 애매 → status=2 → 그룹검토 게시판 → human_decision → status=3 → apply_judgment_packet() → DB 반영
```

### 문제점

1. **status=3이 2가지 의미**: "AI 판정 완료"와 "Human 판정 완료"가 같은 status=3으로 합쳐짐 → 어느 쪽인지 식별 불가
2. **DB 반영이 강제**: `apply_judgment_packet()`이 status=3을 발견하면 무조건 DB에 씀 → 사용자 통제 불가
3. **인간 판정 저장이 DB 반영과 분리 안 됨**: 그룹검토 save는 파일에만 저장하지만, 최종적으로 judgment_apply 재적용으로 DB에 써야 함 → 혼란
4. **확장성 부족**: 1, 2, 3만으로는 2차 검토/QA/롤백 등 미래 요구 대응 불가

### 관련 파일/함수 (실제 코드 확인 완료)

| 파일 | 함수/라인 | 역할 |
|------|-----------|------|
| `judgment_packet_service.py:97-151` | `_packet_skeleton()` | 패킷 골격 정의, `_status_codes` 포함 |
| `judgment_packet_service.py:266-287` | `resolve_item(it)` | status → (status, final_label) 변환 |
| `judgment_packet_service.py:290-348` | `apply_judgment_packet()` | status==3만 DB 반영 |
| `judgment_packet_service.py:360-386` | `update_packet_decisions()` | 게시판 저장 → status=3 전이 |
| `perspective_routes.py:652-706` | `api_judgment_apply()` | 패킷 업로드/재적용 → apply 호출 |
| `perspective_routes.py:709-733` | `api_judgment_packets()` | 패킷 목록 + status 분포 |
| `perspective_routes.py:1663-1694` | `api_group_review_files()` | 패킷 파일 노출 (status==2 rows) |
| `perspective_routes.py:1697-1736` | `api_group_review_load()` | 패킷 중 status==2만 로드 |
| `perspective_routes.py:1739-1790` | `api_group_review_save()` | 게시판 저장 → `update_packet_decisions` |
| `judgment_apply.js` (전체) | upload/reapply/packet list | 프론트엔드 upload API + 재적용 드롭다운 |
| `group_review.js` (전체) | loadFile/save | 게시판 파일 로드/저장 |

## 설계: 상태 코드 체계

### 설계 원칙

1. **의미 계층화**: 100단위 = 대분류(단계), 10단위 = 중분류(주체), 1단위 = 세부상태
2. **여유 공간**: 각 블록에 10개씩 여유 (미래 확장 대비)
3. **하위 호환**: 레거시 status=1,2,3을 런타임 매핑으로 신규 체계에 대응
4. **단순성**: 3자리 코드지만 익숙해지면 유추 가능

### 선택지

#### 옵션 A: 3자리 코드 (권장) — 최대 확장성

| 코드 | 의미 | 설명 |
|------|------|------|
| **100** | EXTRACT_PENDING | 추출 대기 (select_hard_sentences 직후) |
| **110** | EXTRACT_DONE | 추출 완료 (패킷 생성됨) |
| | | |
| **200** | AI_JUDGE_PENDING | AI 판정 대기 (구 1) |
| **201** | AI_JUDGE_IN_PROGRESS | AI 판정 진행 중 |
| **210** | AI_JUDGE_DONE | AI 판정 완료 — 확신 O, DB 반영 대기 (구 3) |
| **211** | AI_JUDGE_DEFERRED | AI 판정 보류 — 확신 X, Human 이관 (구 2) |
| **215** | AI_JUDGE_FAILED | AI 판정 실패 |
| | | |
| **220** | HUMAN_JUDGE_PENDING | Human 판정 대기 (구 2) |
| **221** | HUMAN_JUDGE_IN_PROGRESS | Human 판정 진행 중 |
| **222** | HUMAN_JUDGE_DONE | Human 판정 완료 — DB 반영 대기 (구 4→될 값) |
| **223** | HUMAN_JUDGE_SKIPPED | Human 건너뜀 (not_group/skip) |
| **225** | HUMAN_JUDGE_FAILED | Human 판정 실패 |
| | | |
| **230** | REVIEW_PENDING | 2차 검토 대기 (미래) |
| **231** | REVIEW_DONE | 2차 검토 완료 (미래) |
| | | |
| **300** | AI_APPLY_PENDING | AI 반영 대기 (버튼 눌렀으나 미처리) |
| **310** | AI_APPLY_DONE | AI 반영 완료 — DB에 써짐 (구 10) |
| **311** | AI_APPLY_PARTIAL | AI 부분 반영 (일부 실패) |
| | | |
| **320** | HUMAN_APPLY_PENDING | Human 반영 대기 |
| **322** | HUMAN_APPLY_DONE | Human 반영 완료 — DB에 써짐 (구 11) |
| | | |
| **400** | COMPLETED | 전체 완료 |
| **410** | ARCHIVED | 아카이브 |
| **430** | ROLLED_BACK | 롤백 |
| | | |
| **900** | ERROR | 오류 |
| **999** | DELETED | 삭제 |

#### 옵션 B: 2자리 코드 — 적당한 확장성

| 코드 | 의미 | 설명 |
|------|------|------|
| 10 | AI_JUDGE_PENDING | AI 판정 대기 |
| 11 | AI_JUDGE_DONE | AI 판정 완료 |
| 12 | AI_JUDGE_DEFERRED | AI 판정 보류 (Human 이관) |
| 20 | HUMAN_JUDGE_PENDING | Human 판정 대기 |
| 22 | HUMAN_JUDGE_DONE | Human 판정 완료 |
| 23 | HUMAN_JUDGE_SKIPPED | Human 건너뜀 |
| 30 | AI_APPLY_DONE | AI DB 반영 완료 |
| 31 | AI_APPLY_PARTIAL | AI 부분 반영 |
| 32 | HUMAN_APPLY_DONE | Human DB 반영 완료 |
| 40~49 | 미래: 2차검토/QA | |
| 50~59 | 미래: 에러/실패 | |

#### 옵션 C: 현행 유지 + 최소 확장 — 가장 단순

| 코드 | 의미 | 설명 |
|------|------|------|
| 1 | AI 대기 | 변동 없음 |
| 2 | Human 대기 | 변동 없음 |
| 3 | AI 작업 완료 | 신규 |
| 4 | Human 작업 완료 | 신규 |
| 10 | AI DB 반영 완료 | 신규 |
| 11 | Human DB 반영 완료 | 신규 |
| 20~29 | 미래 예약 | 2차 검토 등 |
| 30~39 | 미래 예약 | 에러/실패 |

---

**비교:**

| 기준 | 옵션 A (3자리) | 옵션 B (2자리) | 옵션 C (현행+) |
|------|---------------|---------------|---------------|
| 학습 곡선 | 중 | 중 | 낮음 |
| 확장 가능 블록 | 9개(0~9 × 0~9) | 5개(10/20/30/40/50) | 3개(10/20/30) |
| 하위 호환 | 런타임 매핑 필요 | 런타임 매핑 필요 | 런타임 매핑 불필요 |
| 코드 가독성 | 높음 (200=AI, 300=Apply) | 중 (10=AI, 20=Human) | 낮음 (의미 없음) |
| 구현 복잡도 | 중 | 중 | 낮음 |

## 우려사항

### 1. 레거시 패킷 호환성

**문제**: 기존 `eval/judgment/**/*.json` 파일들 중 status=3이 "확정(DB 반영 대상)"으로 저장되어 있음. 새 체계에서 status=3은 "AI 작업 완료"가 됨.

**영향**:
- 기존 status=3은 신규 체계의 `210`(AI_JUDGE_DONE) 또는 `222`(HUMAN_JUDGE_DONE) 중 어디에 매핑되어야 하는지 알 수 없음
- `human_decision` 유무로 추정 가능하나 100% 정확하지 않음

**대응**:
- 옵션 A/B: `resolve_item()`에 레거시 매핑 함수 추가
- 옵션 C: 레거시 3을 3(AI 작업 완료)으로 자연 매핑 (의미상 일치)

### 2. `apply_judgment_packet()`과 신규 "DB 반영" 버튼의 역할 중복

**문제**: 현재 `apply_judgment_packet()`은 "judgment/apply API 호출 시 status 3을 DB 반영"한다. 새 체계에서는 "DB 반영" 버튼이 별도 API(`/judgment/apply-db`)를 호출하여 status 3→10, 4→11을 처리한다.

**혼선 가능성**: 기존 `apply_judgment_packet()`을 계속 호출하면 status 3, 4도 DB에 써버릴 위험.

**대응**: `apply_judgment_packet()`을 신규 status 코드(10, 11)만 반영하도록 수정. status 3, 4는 집계만 하고 무시.

### 3. 프론트엔드 패킷 드롭다운 정보 밀집

**문제**: 현재 `jaPacketFile` 옵션 텍스트에 `[확정 3 · 사람대기 2 · AI대기 1]`이 표시됨. 새 체계에서 6개 status를 모두 표시하면 한 줄이 너무 길어짐.

**대응**: DB 반영 대기(ready) 항목만 별도 표시하거나, 툴팁/2줄 표시 고려.

### 4. 버튼 활성화 조건 문구 (사용자 확인 필요)

**문제**: 사용자 요구사항 #7 "10, 11만 status 존재 시 해당 버튼을 활성화"가 논리적으로 모순 가능성.
- status 10/11 = "DB 반영 완료" 상태
- "DB 반영 완료"된 항목만 있을 때 "DB에 반영" 버튼을 활성화하는 것은 의미 없음

**추정**: "3, 4만 status 존재 시" (작업 완료 → DB 반영 대기 상태)가 의도일 가능성 높음.

→ **§요구사항 원자화 질문 3.1, 3.2에서 사용자 확인 필요**

## 구현 상세

### 3.1 백엔드 — `judgment_packet_service.py`

#### 3.1.1 상태 코드 상수 정의 (파일 상단)

```python
# ============================================================
# 판정 패킷 상태 코드
# ============================================================
# --- AI 판정 ---
AI_JUDGE_PENDING      = 200   # AI 판정 대기
AI_JUDGE_IN_PROGRESS  = 201   # AI 판정 진행 중
AI_JUDGE_DONE         = 210   # AI 판정 완료 (확신 O, DB 반영 대기)
AI_JUDGE_DEFERRED     = 211   # AI 판정 보류 (확신 X, Human 이관)
AI_JUDGE_FAILED       = 215   # AI 판정 실패

# --- Human 판정 ---
HUMAN_JUDGE_PENDING   = 220   # Human 판정 대기
HUMAN_JUDGE_DONE      = 222   # Human 판정 완료 (DB 반영 대기)
HUMAN_JUDGE_SKIPPED   = 223   # Human 건너뜀 (not_group/skip)
HUMAN_JUDGE_FAILED    = 225   # Human 판정 실패

# --- DB 반영 ---
AI_APPLY_DONE         = 310   # AI DB 반영 완료
AI_APPLY_PARTIAL      = 311   # AI 부분 반영
HUMAN_APPLY_DONE      = 322   # Human DB 반영 완료
```

**또는 옵션 C (현행+):**

```python
STATUS_AI_PENDING     = 1   # AI 대기
STATUS_HUMAN_PENDING  = 2   # Human 대기
STATUS_AI_READY       = 3   # AI 작업 완료 (DB 반영 대기)
STATUS_HUMAN_READY    = 4   # Human 작업 완료 (DB 반영 대기)
STATUS_AI_APPLIED     = 10  # AI DB 반영 완료
STATUS_HUMAN_APPLIED  = 11  # Human DB 반영 완료
```

#### 3.1.2 `_packet_skeleton()` — `_status_codes` **+ `_doc`/`_stages`/`output_schema` 동시 갱신** (라인 100~147)

> ⚠️ **`_status_codes` dict만 바꾸면 자기설명 패킷이 내부 모순이 된다.** 외부 AI judge는 `_doc`(라인 100)과 `_stages.judge.instruction`/`output_schema`(라인 123~141), `_stages.insert.instruction`(라인 145)의 "status=3 확신 / status=2 애매" 문구를 읽고 그대로 emit한다. 코드표만 210/211로 바꾸면 본문은 3, 표는 210으로 어긋난다. **아래 4곳을 신규 코드로 함께 고친다** (judge가 3/2를 emit해도 레거시 매핑으로 흡수되지만, 자기설명 패킷의 정합성을 위해 반드시 동기화).

```python
'_status_codes': {
    '200': 'AI 판정 대기',
    '210': 'AI 판정 완료 — 확신(DB 반영 대기)',
    '211': 'AI 판정 보류 — 애매(Human 이관)',
    '220': 'Human 판정 대기',
    '222': 'Human 판정 완료(DB 반영 대기)',
    '223': 'Human 건너뜀(not_group/skip)',
    '310': 'AI DB 반영 완료',
    '322': 'Human DB 반영 완료',
},
```

`_doc` / `_stages.judge.instruction` / `output_schema.status` / `_stages.insert.instruction` 의 "status=3/2" 표현을 각각 "status=210(확신)/211(애매)", "insert 대상은 310·322(DB 반영 완료)뿐" 으로 교체한다.

> **옵션 C 선택 시**: 1/2/3 의미가 유지되므로 `_doc`/`_stages` 문구는 "3=AI 작업완료, 4=Human 작업완료, 10/11=DB 반영완료" 로만 소폭 보강하면 되고 judge 프롬프트(3=확신/2=애매)는 그대로 둔다 → 자기설명 정합성 리스크가 가장 작다.

#### 3.1.3 `resolve_item()` — 신규 status 인식 (라인 266-287)

> ⚠️ **결함 수정 2가지**:
> 1. **레거시 3의 주체 분기**: 현행 `update_packet_decisions()`는 **Human 판정 완료도 status=3**으로 저장한다(`judgment_packet_service.py:376`). 따라서 단순 `{3: 210}` 매핑은 Human 판정분을 AI 작업완료(210)로 오귀속시켜 group_review가 아닌 judgment_apply 버튼이 잡는다. → 레거시 3은 `human_decision` 유무로 210(AI) / 222(Human)를 갈라야 한다.
> 2. **`resolve_item`은 순수 함수 유지** — 카운트/목록 루프(`api_judgment_packets`, `api_group_review_files`)에서 읽기 전용으로 호출되므로 **`it['status']=...` 인플레이스 변조 금지**(부분 마이그레이션이 파일에 새어들 위험). 파일 마이그레이션이 필요하면 저장 경로(§3.1.6 `apply_db_to_packet` 등)에서 명시적으로만 수행한다.

```python
def _map_legacy_status(it):
    """레거시(status 없음/1/2/3) → 신규 코드. 순수(변조 없음)."""
    status = it.get('status')
    if status is None:                      # 구 result 스키마
        res = it.get('result') or {}
        if res.get('needs_human') is True:
            return 220
        return 210 if res.get('label') in _VALID_LABELS else 200
    if status == 1:
        return 200
    if status == 2:
        return 220
    if status == 3:                         # 확정 → 주체 분기
        return 222 if it.get('human_decision') in _VALID_LABELS else 210
    return status                           # 이미 신규 코드

def resolve_item(it):
    status = _map_legacy_status(it)         # 반환만, it 미변조

    # 작업 완료(DB 반영 대기) 210/222 · DB 반영 완료 310/322 → 최종 라벨 산출
    if status in (210, 222, 310, 322):
        hd = it.get('human_decision')
        pol = (it.get('ai_reference') or {}).get('polarity')
        label = hd if hd in _VALID_LABELS else (pol if pol in _VALID_LABELS else None)
        return status, label

    # 대기/보류/건너뜀/실패 → 라벨 없음
    return status, None
```

#### 3.1.4 `apply_judgment_packet()` — status 310, 322만 DB 반영 (라인 290-348)

> ⚠️ **의미 변경의 부작용 명시**: 재설계 후 `apply_judgment_packet()`은 210/222(작업 완료)를 **쓰지 않고 집계만** 하므로, 종전의 "AI 판정 패킷을 업로드하면 즉시 DB 반영" 동작이 **사라진다**(210은 반영 안 됨 → 버튼을 눌러야 310으로 전이하며 그때만 반영). 레거시 status=3 패킷을 재적용해도 마찬가지로 아무것도 안 쓴다. 이는 D5의 "DB 반영 시점 위임"이라는 의도된 결과지만, **회귀로 오인되기 쉬우므로** 릴리스 노트·운영자 안내에 명시한다. (D5에서 "완전 이관"을 택하면 이 함수는 사실상 카운터로만 남는다 → §D5 결정 필요.)

```python
def apply_judgment_packet(packet, conn=None):
    """status 310(AI DB 완료), 322(Human DB 완료)만 DB 반영.
    210/222는 집계(ai_ready/human_ready)만 하고 DB 미접촉."""
    
    # ... 같은 구조 ...
    for it in packet.get('items', []):
        st, label = resolve_item(it)
        if st == 200:    # AI 대기
            pending_ai += 1; continue
        if st in (211, 220, 223):  # Human 대기
            pending_human += 1; continue
        if st == 210:    # AI 작업 완료 (미반영)
            ai_ready += 1; continue
        if st == 222:    # Human 작업 완료 (미반영)
            human_ready += 1; continue
        # 310 or 322 (DB 반영 완료)
        if label not in _VALID_LABELS: skipped += 1; continue
        # ... DB UPDATE 로직 ...
    
    return {
        'inserted_sentences': inserted,
        'updated_evaluations': len(by_db),
        'pending_ai': pending_ai,
        'pending_human': pending_human,
        'ai_ready': ai_ready,        # 신규: AI 작업 완료 but 미반영
        'human_ready': human_ready,  # 신규: Human 작업 완료 but 미반영
        'skipped': skipped,
    }
```

#### 3.1.5 `update_packet_decisions()` — status=222 (Human 작업 완료)로 변경 (라인 376)

```python
it['human_decision'] = dec
it['status'] = 222 if dec in _VALID_LABELS else 220   # 3 → 222, 2→220
```

#### 3.1.6 신규 함수 `apply_db_to_packet()` — "DB 반영" 버튼 전용

```python
def apply_db_to_packet(packet, conn=None, target='all'):
    """패킷의 status 210→310, 222→322로 전이 + DB 반영.
    target='ai'  → 210(AI 작업완료)만, 'human' → 222(Human 작업완료)만, 'all' → 둘 다.
    Returns: {applied_ai, applied_human, skipped, packet}"""
    from src.services.perspective_service import _get_eval_conn
    own = conn is None
    conn = conn or _get_eval_conn()

    want = {'ai': {210}, 'human': {222}, 'all': {210, 222}}[target]
    by_db = {'ai': {}, 'human': {}}
    applied_ai = applied_human = skipped = 0
    
    for it in packet.get('items', []):
        st, label = resolve_item(it)
        if st not in want:        # target에 해당하는 작업 완료 상태만
            continue
        if label not in _VALID_LABELS:
            skipped += 1
            continue
        key = it.get('key', {})
        db_id = key.get('db_id')
        sent_idx = key.get('sent_idx')
        if db_id is None or sent_idx is None:
            skipped += 1
            continue
        
        target = 'ai' if st == 210 else 'human'
        by_db[target].setdefault(int(db_id), {})[str(sent_idx)] = label
        it['status'] = 310 if st == 210 else 322  # 상태 전이
    
    try:
        for target, dbs in by_db.items():
            for db_id, sent_corr in dbs.items():
                cur = conn.execute(...).fetchone()
                existing = json.loads(cur[0] or '{}') if cur else {}
                merged = {**existing, **sent_corr}
                conn.execute("UPDATE evaluations SET sentiment_corrections = ? WHERE id = ?",
                           (json.dumps(merged), db_id))
                if target == 'ai': applied_ai += len(sent_corr)
                else: applied_human += len(sent_corr)
        conn.commit()
    finally:
        if own: conn.close()
    
    return {'applied_ai': applied_ai, 'applied_human': applied_human,
            'skipped': skipped, 'packet': packet}
```

### 3.2 백엔드 — `perspective_routes.py`

#### 3.2.1 신규 엔드포인트: `POST /judgment/apply-db`

```python
@perspective_bp.route('/judgment/apply-db', methods=['POST'])
def api_judgment_apply_db():
    """패킷 내 작업 완료(210/222) 항목을 DB 반영 후 310/322로 전이.

    body: {file, target?: 'ai'|'human'|'all'(기본 'all')}
      - judgment_apply 버튼 → target='ai' (210만 반영)
      - group_review 버튼   → target='human' (222만 반영)
    """
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    path = _safe_packet_path(data.get('file'))
    if not path:
        return jsonify({'success': False, 'error': '허용되지 않은 파일'}), 400
    packet = load_packet(path)
    result = apply_db_to_packet(packet, target=data.get('target', 'all'))
    # 변경된 패킷을 같은 경로에 in-place 저장(save_packet_file 대신 원경로 덮어쓰기 — 경로 안정)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result['packet'], f, ensure_ascii=False, indent=1)

    # 🔑 리다이렉트 판정은 '여기서'(AI 반영 직후) 한다 — 업로드 시점(§3.2.2)이 아님
    items = result['packet'].get('items', [])
    has_310 = any(resolve_item(it)[0] == 310 for it in items)   # AI DB 반영 완료 존재
    has_322 = any(resolve_item(it)[0] == 322 for it in items)   # Human DB 반영 완료 존재
    has_human_pending = any(resolve_item(it)[0] in (211, 220) for it in items)
    # AI는 DB에 들어갔고, Human 반영은 아직 없고, 남은 Human 이관분이 있음
    need_human = has_310 and (not has_322) and has_human_pending
    result.pop('packet', None)
    return jsonify({'success': True, 'summary': result,
                    'redirect_to_group_review': need_human})
```

> **왜 여기로 옮겼나 (검토 결함 1)**: 재설계 후 `apply_judgment_packet()`(업로드/재적용)은 210→310 전이를 하지 않으므로, **업로드 직후엔 310이 존재하지 않는다.** 리다이렉트 조건을 업로드 응답(구 §3.2.2)에 두면 `has_310`이 항상 False → 영영 안 뜬다. status 10(310)이 실제로 생기는 시점은 **AI "DB에 반영" 버튼 처리 직후**이므로 리다이렉트 판정도 그 응답에서 한다. 또한 "Human 이관분이 실제로 남아 있음"(`has_human_pending`)을 AND 조건에 추가해, 넘길 것이 없는데 게시판으로 보내는 헛이동을 막는다.

> `apply_db_to_packet(packet, target)` — `target`으로 210(ai)/222(human)만 골라 반영하도록 §3.1.6에 `target` 파라미터를 추가한다(judgment_apply는 AI분만, group_review는 Human분만 반영해 버튼별 책임을 분리).

#### 3.2.2 `api_judgment_apply()` — 리다이렉트 플래그 **제거**(집계만) (라인 699)

> ~~기존 계획: 업로드 응답에서 `has_310`으로 리다이렉트 판정~~ → **폐기**(검토 결함 1). 업로드 시점엔 310이 존재하지 않으므로 여기서 판정하면 안 됨. 리다이렉트는 §3.2.1(apply-db 응답)로 이관했다.

이 함수는 재설계 후 **DB를 쓰지 않고 status 분포만 집계**해 프론트가 "DB에 반영" 버튼을 켤 수 있게 한다(`ai_ready`/`human_ready` 반환은 §3.1.4·3.2.3 참조).

```python
summary = apply_judgment_packet(packet)   # 210/222는 집계만, 310/322만 반영(사실상 신규 업로드엔 없음)
return jsonify({
    'success': True,
    'summary': summary,          # ai_ready/human_ready 포함 → 버튼 활성 판단
    'packet_file': packet_file,
})
```

#### 3.2.3 `api_judgment_packets()` — 신규 status 카운트 추가 (라인 722-730)

```python
counts = {200: 0, 210: 0, 211: 0, 220: 0, 222: 0, 223: 0, 310: 0, 322: 0}
for it in load_packet(p).get('items', []):
    st, _ = resolve_item(it)
    counts[st] = counts.get(st, 0) + 1
out.append({
    'name': ...,
    'pending_ai': counts.get(200, 0),
    'pending_human': counts.get(211, 0) + counts.get(220, 0) + counts.get(223, 0),
    'ai_ready': counts.get(210, 0),       # AI 작업 완료 (미반영)
    'human_ready': counts.get(222, 0),    # Human 작업 완료 (미반영)
    'ai_applied': counts.get(310, 0),     # AI DB 반영 완료
    'human_applied': counts.get(322, 0),  # Human DB 반영 완료
})
```

#### 3.2.4 `api_group_review_files()` — human_ready 카운트 추가 (라인 1692)

```python
files.append({
    'name': ..., 'rows': n,
    'human_ready': sum(1 for it in load_packet(p).get('items', [])
                       if resolve_item(it)[0] == 222)  # Human 작업 완료 개수
})
```

그리고 `rows`(사람 판정 대기 수) 계산의 `== 2` 필터도 신규 코드로 교체한다(아래 §3.2.5와 동일 사유).

#### 3.2.5 `api_group_review_load()` · `api_group_review_save()` — 사람대기 필터 갱신 (라인 1697-1790) 🔴 **누락 방지**

> 🔴 **검토 결함 3**: 두 함수는 사람 판정 대기 항목을 `resolve_item(it)[0] == 2`로 필터한다(`perspective_routes.py:1712-1713`, save 매칭부). 옵션 A/B를 택하면 사람대기가 **211/220**으로 바뀌므로 `== 2`가 전부 탈락 → **게시판에 아무 행도 안 뜨는 회귀**. `api_group_review_files`의 `rows` 계산(라인 1691 부근)도 동일. 세 곳을 함께 고친다.

```python
# 사람이 게시판에서 판정해야 할 상태 집합 (한 곳에 정의해 세 함수가 공유)
HUMAN_PENDING = (211, 220)   # 옵션 A/B. 옵션 C면 (2,) 로 두어 현행 유지 → 무변경

# api_group_review_load: status==2 → resolve_item(it)[0] in HUMAN_PENDING
pending = [it for it in load_packet(ppath).get('items', [])
           if resolve_item(it)[0] in HUMAN_PENDING]

# api_group_review_files rows: 동일하게 in HUMAN_PENDING
# api_group_review_save: 매칭·집계에서 == 2 사용처를 in HUMAN_PENDING 으로 교체
```

> **옵션 C 선택 시**: 2(Human 대기)가 그대로 유지되므로 이 세 곳은 **변경 불필요** — 회귀 리스크가 원천 제거된다(§D1에서 C를 권고하는 핵심 근거).

### 3.3 프론트엔드 — `judgment_apply.html`

#### 3.3.1 "DB에 반영" 버튼 추가 (라인 64-70 사이)

```html
<div style="display:flex; gap:var(--space-3); align-items:center; margin-top:var(--space-3); flex-wrap:wrap;">
    <select id="jaPacketFile" style="...">...</select>
    <button class="btn btn-primary" id="jaReapplyBtn" disabled>재적용</button>
    <button class="btn" id="jaPacketRefresh" type="button">목록 새로고침</button>
    <button class="btn btn-primary" id="jaApplyDbBtn" disabled style="display:none;">
        💾 DB에 반영
    </button>
</div>
```

#### 3.3.2 팝업/리다이렉트 영역 추가 (페이지 하단)

> ⚠️ **인라인 `onclick` 금지 (검토: IIFE 스코프)**: `judgment_apply.js`는 `(function(){…})()` 모듈 스코프라 `goToGroupReview`/`dismissRedirect`가 **전역에 없다** → 인라인 `onclick`은 함수를 못 찾는다. 버튼에 **id만 부여**하고 `DOMContentLoaded`에서 `addEventListener`로 묶는다(기존 코드 스타일과 동일, `judgment_apply.js:136~145`).

```html
<div id="jaRedirectAlert" style="display:none; ...">
    <p>⚠️ AI 작업이 DB에 반영되었습니다. Human 작업을 위해 그룹 검토 게시판으로 이동하시겠습니까?</p>
    <button class="btn btn-primary" id="jaGoGroupReview">이동</button>
    <button class="btn" id="jaDismissRedirect">닫기</button>
</div>
```

### 3.4 프론트엔드 — `judgment_apply.js`

#### 3.4.1 `loadPackets()` — 신규 status 표시 + 버튼 활성화

```javascript
function loadPackets() {
    fetch(API + '/packets')
        .then(function (r) { return r.json(); })
        .then(function (j) {
            if (!j || !j.success) { return; }
            var sel = $('jaPacketFile');
            var cur = sel.value;
            sel.innerHTML = '<option value="">— 서버 저장 패킷 선택 —</option>';
            (j.packets || []).forEach(function (p) {
                var o = document.createElement('option');
                o.value = p.name;
                // AI대기/AI완료/Human대기/Human완료/AI적용/Human적용
                o.textContent = p.name + '  [AI대기 ' + p.pending_ai
                    + ' · AI완료 ' + (p.ai_ready || 0)
                    + ' · Human대기 ' + p.pending_human
                    + ' · Human완료 ' + (p.human_ready || 0)
                    + ' · AI적용 ' + (p.ai_applied || 0)
                    + ' · Human적용 ' + (p.human_applied || 0) + ']';
                o.dataset.aiReady = p.ai_ready || 0;
                o.dataset.humanReady = p.human_ready || 0;
                o.dataset.aiApplied = p.ai_applied || 0;
                o.dataset.humanApplied = p.human_applied || 0;
                sel.appendChild(o);
            });
            sel.value = cur;
            $('jaReapplyBtn').disabled = !sel.value;
            updateApplyDbBtn();
        });
}
```

#### 3.4.2 `updateApplyDbBtn()` — 버튼 표시/활성화

```javascript
function updateApplyDbBtn() {
    var sel = $('jaPacketFile');
    var opt = sel.options[sel.selectedIndex];
    var btn = $('jaApplyDbBtn');
    if (!opt || !opt.value) { btn.style.display = 'none'; return; }
    
    var aiReady = parseInt(opt.dataset.aiReady || 0, 10);
    if (aiReady > 0) {
        btn.style.display = 'inline-block';
        btn.disabled = false;
        btn.textContent = '💾 DB에 반영 (AI ' + aiReady + '건)';
    } else {
        btn.style.display = 'none';
        btn.disabled = true;
    }
}
```

#### 3.4.3 `applyDb()` — API 호출

```javascript
function applyDb() {
    var file = $('jaPacketFile').value;
    if (!file) return;
    var btn = $('jaApplyDbBtn');
    btn.disabled = true; btn.textContent = '반영 중…';
    
    fetch('/api/perspective/judgment/apply-db', { method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({file: file, target: 'ai'})   // judgment_apply는 AI분(210)만 반영
    }).then(function(r){return r.json()}).then(function(j){
        btn.disabled = false;
        if (!j || j.success !== true) { alert('실패: ' + ((j&&j.error)||'?')); return; }
        var s = j.summary || {};
        $('jaReapplyResult').innerHTML = stat(s.applied_ai||0, 'AI 반영 완료');
        if (j.redirect_to_group_review) {   // AI 반영 후 Human 이관분 남음 → 게시판 안내
            $('jaRedirectAlert').style.display = 'block';
        }
        loadPackets();
    });
}
```

#### 3.4.4 리다이렉트 처리

> ⚠️ **리다이렉트 트리거 위치 정정** (검토 결함 1): `redirect_to_group_review`는 **apply-db 응답**에서 온다(§3.2.1). 업로드 응답(`renderResult`)이 아니다. 따라서 §3.4.3 `applyDb()`의 `.then` 안에서 플래그를 확인해 알림을 띄운다.

```javascript
// §3.4.3 applyDb()의 응답 핸들러 끝에 추가:
//   if (j.redirect_to_group_review) { $('jaRedirectAlert').style.display = 'block'; }

function goToGroupReview() {
    var file = $('jaPacketFile').value;
    sessionStorage.setItem('gr_preset_file', file);
    window.location.href = '/group-review?file=' + encodeURIComponent(file);
}

function dismissRedirect() {
    $('jaRedirectAlert').style.display = 'none';
}
```

#### 3.4.5 이벤트 와이어링 + `summaryHtml()` 갱신 (검토 누락 보정)

**(a) DOMContentLoaded 버튼 등록** — 기존 `judgment_apply.js:136~145` 스타일로 추가:
```javascript
$('jaApplyDbBtn').addEventListener('click', applyDb);
$('jaGoGroupReview').addEventListener('click', goToGroupReview);
$('jaDismissRedirect').addEventListener('click', dismissRedirect);
$('jaPacketFile').addEventListener('change', updateApplyDbBtn);   // 선택 바뀌면 버튼 재평가
```

**(b) `summaryHtml()` 신규 필드 반영** — 현 함수(`judgment_apply.js:26~34`)는 `status 1/2/3` 라벨을 하드코딩한다. 재설계 후 `apply_judgment_packet()`은 210/222를 반영하지 않고 `ai_ready`/`human_ready`로 집계하므로, "반영된 문장" 옆에 **미반영 대기(작업 완료지만 DB 미반영)** 를 함께 표기한다:
```javascript
// summaryHtml에 추가 (라벨은 D1 옵션 따라 숫자만 교체)
+ stat(s.ai_ready != null ? s.ai_ready : 0, 'AI 작업 완료·DB 반영 대기', 'warn')
+ stat(s.human_ready != null ? s.human_ready : 0, 'Human 작업 완료·DB 반영 대기', 'warn')
```

### 3.5 프론트엔드 — `group_review.html`

#### 3.5.1 "DB에 반영" 버튼 추가 (라인 62-65)

```html
<div class="gr-bar">
  <select id="grFile">...</select>
  <label><input type="checkbox" id="grUndecided" checked> 미판정만</label>
  <button id="grSave" class="gr-savebtn" disabled>💾 저장 (0)</button>
  <button id="grApplyDb" class="gr-savebtn" disabled style="background:#e67e22; display:none;">
    💾 DB에 반영
  </button>
  <span class="gr-progress" id="grProgress"></span>
</div>
```

### 3.6 프론트엔드 — `group_review.js`

#### 3.6.1 `loadFile()` — 상태 222 개수 확인 (라인 30-41)

```javascript
function loadFile(name) {
    state.file = name;
    // ... 기존 코드 ...
    fetch(API + '/load?file=' + encodeURIComponent(name) + '&limit=100000')
        .then(function (r) { return r.json(); })
        .then(function (j) {
            // ... 기존 코드 ...
            // 파일 메타정보에서 human_ready 확인 (별도 API 호출)
            loadHumanReadyCount(name);
        });
}

function loadHumanReadyCount(name) {
    fetch('/api/perspective/judgment/packets')
        .then(function(r){return r.json()})
        .then(function(j){
            if (!j.success) return;
            var p = (j.packets||[]).find(function(x){return x.name === name;});
            var btn = $('grApplyDb');
            var cnt = p ? (p.human_ready || 0) : 0;
            if (cnt > 0) {
                btn.style.display = 'inline-block';
                btn.disabled = false;
                btn.textContent = '💾 DB에 반영 (Human ' + cnt + '건)';
            } else {
                btn.style.display = 'none';
                btn.disabled = true;
            }
        });
}
```

#### 3.6.2 `applyDb()` — group_review 전용

> ⚠️ `group_review.js`도 IIFE 스코프. `grApplyDb` 버튼은 `DOMContentLoaded`(라인 169~)에서 `$('grApplyDb').addEventListener('click', applyDb);` 로 묶는다(인라인 onclick 금지).

```javascript
function applyDb() {
    if (!state.file) return;
    var btn = $('grApplyDb');
    btn.disabled = true; btn.textContent = '반영 중…';
    
    fetch('/api/perspective/judgment/apply-db', { method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({file: state.file, target: 'human'})  // group_review는 Human분(222)만 반영
    }).then(function(r){return r.json()}).then(function(j){
        btn.disabled = false;
        if (!j || j.success !== true) { alert('DB 반영 실패'); return; }
        toast('DB 반영 완료');
        loadFile(state.file);  // 재로드
    });
}
```

### 3.7 그룹검토 파일 자동 선택 (URL 파라미터)

#### `group_review.js` DOMContentLoaded 수정

> ⚠️ **setInterval(50ms) 폴링 폐기** (검토 노란 8): 취약하고 타이밍 의존적이다. 파일 목록을 채우는 **실제 함수는 `loadFiles()`**(`group_review.js:18`, 콜백 인자 없음) 이므로, **콜백 파라미터를 추가**해 `.then` 끝에서 자동 선택을 호출한다. 또 옵션 `value`는 드롭다운이 쓰는 값과 **동일 형식(상대경로)** 이어야 하므로, 문자열 일치 대신 실제 존재하는 option을 찾아 선택하고 없으면 조용히 무시한다.

```javascript
// 기존 loadFiles()에 done 콜백 추가:
function loadFiles(done) {
    fetch(API + '/files').then(function (r) { return r.json(); }).then(function (j) {
        // ... 기존 옵션 채우기 ...
        if (typeof done === 'function') { done(); }   // 목록 완성 후 호출
    });
}

function autoSelectPresetFile() {
    var params = new URLSearchParams(window.location.search);
    var preset = params.get('file') || sessionStorage.getItem('gr_preset_file');
    if (!preset) { return; }
    sessionStorage.removeItem('gr_preset_file');
    var sel = $('grFile');
    // 목록에 실제로 존재하는 옵션만 선택 (형식 불일치 시 무시)
    var match = Array.prototype.find.call(sel.options, function (o) { return o.value === preset; });
    if (match) { sel.value = preset; loadFile(preset); }
}

// group_review.js DOMContentLoaded(라인 169) 기존 loadFiles(); → loadFiles(autoSelectPresetFile);
```

## 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 상태 코드 상수 정의 (선택지 확정 후) | — |
| 2 | `resolve_item()` 수정 — 신규 status 인식 + 레거시 매핑 | 1 |
| 3 | `apply_judgment_packet()` 수정 — 310/322만 DB 반영 | 1 |
| 4 | `update_packet_decisions()` — status 222로 변경 | 1 |
| 5 | 신규 `apply_db_to_packet(target=)` 구현 (210→310/222→322, target 분기) | 1,2 |
| 6 | `api_judgment_apply_db` 엔드포인트 신규 (**리다이렉트 판정 포함**) | 5 |
| 7 | `api_judgment_apply()` — DB 미기록·집계만, **리다이렉트 플래그 제거** | 3 |
| 8 | `api_judgment_packets()` 신규 status 카운트 | 2 |
| 9 | `api_group_review_files()` human_ready 추가 **+ rows `==2`→HUMAN_PENDING** | 2 |
| 9b | 🔴 `api_group_review_load()`·`save()` `==2`→HUMAN_PENDING (옵션 A/B만) | 2 |
| 10 | `_packet_skeleton()` `_status_codes`+`_doc`+`_stages`+`output_schema` 동기 갱신 | 1 |
| 11 | `judgment_apply.html` 버튼 + 리다이렉트 영역(id만, onclick 금지) 추가 | — |
| 12 | `judgment_apply.js` applyDb(target='ai') + 리다이렉트 처리 + **summaryHtml 신규필드 + DOMContentLoaded 이벤트 등록** | 6 |
| 13 | `group_review.html` 버튼 추가(id만) | — |
| 14 | `group_review.js` applyDb(target='human') + `loadFiles(done)` 콜백 자동선택 + **버튼 이벤트 등록** | 6,12 |
| 15 | 단위테스트 작성 (test_packet_status_flow.py 확장) | 1~10 |

## 영향도 분석

### 변경 파일 목록

| 파일 | 변경 유형 | 영향 범위 |
|------|-----------|-----------|
| `src/services/judgment_packet_service.py` | 수정 + 신규 함수 | 모든 패킷 처리 로직 |
| `src/routes/perspective_routes.py` | 수정 + 신규 엔드포인트 | judgment API |
| `web/templates/judgment_apply.html` | 수정 | UI 버튼 추가 |
| `web/static/js/judgment_apply.js` | 수정 | 버튼 로직 + 리다이렉트 |
| `web/templates/group_review.html` | 수정 | UI 버튼 추가 |
| `web/static/js/group_review.js` | 수정 | 버튼 로직 + 자동선택 |

### 영향받는 기존 기능

| 기능 | 영향 | 대응 |
|------|------|------|
| 기존 패킷 파일 (.json) | status=3 레거시 → 새 체계에서 210(AI 작업 완료)으로 매핑 | 런타임 매핑, 정합성 문제 없음 |
| `batch_processor.py`에서 build_judgment_packet 호출 | status=1 생성 → `resolve_item()`이 레거시로 인식 후 매핑 | 영향 없음 (자동 매핑) |
| 외부 AI judge (Claude) | status=3 생성 → 새 체계에서 210으로 매핑 | 영향 없음 (자동 매핑) |
| 그룹검토 게시판 save | 기존 status=3이었던 human_decision 저장이 222로 변경 | 그룹검토 JS 무변경 (백엔드만) |

## 테스트/검증 계획

### 단위 테스트 (`0701_03/test/test_packet_status_flow.py` 확장)

| 테스트 | 검증 내용 |
|--------|-----------|
| `test_resolve_item_new_codes` | 신규 status(210, 222, 310, 322) resolve 정상 동작 |
| `test_resolve_item_legacy_map` | 레거시 status(1, 2, 3)가 올바른 신규 코드로 매핑되는가 |
| `test_legacy_3_human_decision_to_222` | 🔴 레거시 3 + human_decision 있음 → **222**(210 아님), human_decision 없음 → 210 |
| `test_resolve_item_pure_no_mutation` | 🔴 resolve_item 호출 후 원본 item['status'] **불변**(순수성) |
| `test_apply_judgment_packet_no_write_on_210` | 업로드 반영 시 210/222는 DB 미기록, ai_ready/human_ready 집계만 |
| `test_apply_db_target_ai_only_210` | apply_db_to_packet(target='ai')가 210만 310으로, 222는 미접촉 |
| `test_apply_db_target_human_only_222` | apply_db_to_packet(target='human')가 222만 322로, 210은 미접촉 |
| `test_apply_db_to_packet_210to310` | 210→310 전이 + DB 반영(라벨=human_decision 우선) |
| `test_apply_db_to_packet_222to322` | 222→322 전이 + DB 반영 |
| `test_redirect_only_after_ai_apply` | 🔴 업로드 응답엔 redirect 없음, **apply-db(AI) 후** 310존재·322없음·이관분있음일 때만 need_human=True |
| `test_group_review_load_new_pending_codes` | 🔴 (옵션 A/B) load가 211/220 항목을 게시판 행으로 노출(==2 회귀 없음) |
| `test_update_packet_decisions_222` | 게시판 저장 시 status=222 설정 |

### 수동 테스트 시나리오

1. **AI 판정 완료 패킷 업로드** (코드는 A/B=210→310, C=3→10)
   - judgment_apply에서 파일 업로드 → **이 시점엔 DB 미기록**(집계만) 확인
   - `"DB에 반영(AI)" 버튼 활성화 확인` → 버튼 클릭
   - 210→310 전이 + DB corrections 기록 확인 (패킷 파일·DB 양쪽)

2. **Human 판정 완료 후 DB 반영** (A/B=222→322, C=4→11)
   - group_review에서 사람대기 항목 판정 → 저장(status=222)
   - `"DB에 반영(Human)" 버튼 활성화 확인` → 버튼 클릭
   - 222→322 전이 + DB 기록 확인

3. **리다이렉트 시나리오** (팝업은 **업로드가 아니라 "DB에 반영"(AI) 클릭 직후** 뜬다)
   - judgment_apply에서 AI 확신분(210) + Human 이관분(211/220)이 섞인 패킷 업로드
   - "DB에 반영(AI)" 클릭 → 210→310 반영 후 **팝업 표시 확인**(310 존재·322 없음·이관분 있음) → "이동" 클릭
   - group_review 페이지로 이동 + 파일 자동 선택(콜백) 확인
   - (반례) 이관분이 없으면 팝업이 뜨지 않아야 함

4. **기존 패킷 호환성**
   - 0701_03 이전에 생성된 패킷 로드
   - 모든 status가 올바르게 표시되는지 확인

### 테스트 코드 위치

`wordcloud_project/plans/2026/0702_01_status-code-redesign/test/`

## 리스크 및 제약

| 리스크 | 영향 | 대응 |
|--------|------|------|
| **선택지 결정 지연** | 구현 시작 불가 | §3 설계 중 사용자 결정 대기 |
| **기존 패킷 호환성 깨짐** | 그룹검토에서 기존 패킷을 열 수 없음 | `resolve_item()` 레거시 매핑으로 회피 |
| **외부 AI judge가 생성한 status=3** | 신규 체계와 불일치 | `resolve_item()` 매핑으로 해결 |
| **apply_judgment_packet 중복 호출** | 310/322인 항목 재반영 시도 | skipped 처리로 보호 |
| **그룹검토 게시판 빈 목록 회귀** | load/save의 `==2` 필터가 A/B에서 전탈락 → 게시판에 행 0 | §3.2.5에서 load·save·files rows를 `HUMAN_PENDING`(211,220)으로 교체(옵션 C면 무변경) |
| **리다이렉트 영영 안 뜸** | 업로드 시점엔 310 부재 → 조건 상시 False | §3.2.1로 판정 이관(apply-db 응답) + `has_human_pending` AND |
| **레거시 3 Human분 오귀속** | Human 판정분이 AI 버튼으로 잡힘 | `_map_legacy_status`가 human_decision로 210/222 분기 |
| **자동선택 타이밍 실패** | setInterval 폴링·value 형식 불일치로 미선택 | 목록 로드 `.then` 콜백 + 실제 option 탐색 후 선택 |
| **프론트엔드 패킷 표시 텍스트 길이** | 드롭다운 UI 깨짐 | text-overflow: ellipsis 또는 요약 포맷 |

## 결정 필요 사항 (사용자)

| # | 결정 항목 | 선택지 |
|---|-----------|--------|
| **D1** | 상태 코드 체계 | **A**(3자리), **B**(2자리), **C**(현행+최소) |
| **D2** | "DB에 반영" 버튼 활성화 조건 | **judgment_apply: status 3(210) 존재 시** / **group_review: status 4(222) 존재 시** — 위 질문 3.1/3.2에서 확인 필요 |
| **D3** | group_review "DB에 반영" 버튼 위치 | 그룹검토 바(grSave 옆) / 별도 영역 |
| **D4** | 팝업 메시지 문구 | `"AI 작업이 DB에 반영되었습니다. Human 작업을 위해 그룹 검토 게시판으로 이동하시겠습니까?"` |
| **D5** | `api_judgment_apply()`에서 **기존 apply_judgment_packet 동작 유지** vs **제거하고 apply-db로 완전 이관** | 유지 시: 업로드 시 status 10/11만 자동 DB 반영. 제거 시: 모든 DB 반영은 버튼으로만 |
| **D6** | 리다이렉트 시 파일 전달 방식 | a) URL 파라미터 `?file=...` / b) sessionStorage / c) 둘 다 |
