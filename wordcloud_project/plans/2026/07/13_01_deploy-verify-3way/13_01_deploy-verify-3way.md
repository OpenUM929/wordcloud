# 계획서 — 3자 무결성 검증 배포 마무리 + 내부망 준수율 검증

> 상태: Todo | 작성일: 2026-07-13
> 작업 유형: B (기능 마무리·배포 — 복구 F/설계 요소 일부 포함)
> 선행:
> - 0709 스냅샷 복구 머지 `a41e5a6` (완료)
> - VERSION.json 재생성 `5998a9d` (완료)
> - `10_01_plan-folder-month-restructure` (plans 월별 개편 — 별도 추적, 본 계획과 병행)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-13 | 전체 | 최초 작성 |

---

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1 | **커밋** | | |
| 1.1 | 3자 무결성 3파일(`hr_sentiment.py`·`version_service.py`·`base.html`)이 하나의 커밋으로 master에 올라가는가? | Y | 미검증(수행 대기) |
| 1.2 | 검증 리포트 `batch_verify_260710.md`(현재 untracked)도 같은 흐름에서 커밋되는가? | Y | 미검증(수행 대기) |
| 1.3 | plans 월별 개편 산출물(`2026/04·06·07/`)은 이 커밋에 **섞지 않고** `10_01`에서 별도 커밋하는가? | Y | 미검증(수행 대기) |
| 2 | **배포 zip 재빌드** | | |
| 2.1 | 재빌드한 `wordcloud-project.zip`에 3자 무결성 코드(`verify_integrity` 3자 대조)가 포함되는가? | Y | 미검증(수행 대기) |
| 2.2 | zip 안 `VERSION.json`의 `source_commit`이 3자 무결성 커밋 해시로 갱신되는가? | Y | 미검증(수행 대기) |
| 2.3 | zip에 감정규칙 5종(health_advice_neutral 등)이 여전히 포함되는가? | Y | 미검증(수행 대기) |
| 3 | **내부망 반입** | | |
| 3.1 | 모델 파일(`hr_sentiment_finetuned` 620faad)은 재반입 **불필요**한가(이미 정상)? | Y | 미검증(사용자 확인 대기) |
| 3.2 | zip만 재반입하면 되는가(구 폴더 삭제 후 반입)? | Y | 미검증(사용자 확인 대기) |
| 4 | **검증** | | |
| 4.1 | 재시작 후 버전 모달이 "선언·디스크·메모리 3자 일치"로 뜨는가? | Y | 미검증(내부망) |
| 4.2 | health_advice 배치 준수율이 45.2% → 90%+ 로 오르는가? | Y | 미검증(내부망) |

---

## 1. 배경 및 목적

7/9 rename 세션이 8일치 작업(감정규칙 5종·판정패킷·데이터셋)을 워킹트리에서 소거했고, 이를
스냅샷(`187dee9`) 머지(`a41e5a6`)로 복구했다. 이후 두 갈래 후속 작업이 **워킹트리에만 남아
미커밋** 상태다.

1. **3자 무결성 검증 기능** — "무결성 일치인데 구모델 동작?" 의혹의 재발 방지책. 기존 무결성
   검사는 디스크 파일 해시만 봤고, Flask 지연 싱글톤이 파일 교체 후에도 이전 가중치를 메모리에
   유지하는 상태를 못 잡았다. 선언(VERSION.json)·디스크(model.safetensors)·메모리(로드본 지문)를
   3자 대조해 "파일만 교체되고 서버 미재시작" 상태를 버전 모달에서 자동 탐지한다.
2. **배치 재검증 리포트** — `batch_20260709_0`이 실제로 7/8 모델(620faad) 산출물임을 프리픽스
   합의셋 100%로 확정. 앞선 "구모델 상주" 판단은 재추론 시 서빙 프리픽스(`장점 평가:`) 누락에서
   비롯된 **오진**이었음을 기록.

**목적**: (a) 위 미커밋 작업을 커밋으로 확정, (b) 3자 무결성이 포함된 배포 zip을 재빌드해 내부망에
반입, (c) 재시작 후 health_advice 준수율(45.2%→90%+)과 3자 일치를 실측 검증하여 개선 파이프라인을
종결한다.

## 2. 현재 시스템 분석 (코드 실측)

- **`src/services/version_service.py:79` `verify_integrity()`** — 선언·디스크·메모리 3자 대조.
  반환: `match`(bool)·`restart_required`(bool)·`error`/`note`·`declared`/`disk`/`loaded`(해시 앞 16자).
  - `disk != declared` → `match=False, restart_required=False` ("모델 파일 반입 확인 필요")
  - `disk == declared` & `loaded is None` → `match=True` (미로드, 첫 추론 시 현재 디스크 로드)
  - `disk == declared` & `loaded != disk` → `match=False, restart_required=True` ("서버 재시작 필요")
  - 3자 동일 → `match=True` ("선언·디스크·메모리 로드본 모두 일치")
- **`src/services/version_service.py:15` `get_version_info()`** — `runtime_sha256`·`runtime_loaded_at`·
  `restart_required` 필드를 응답에 추가(모달 배지 구동).
- **`src/modules/hr_sentiment.py:49` `_HRSentimentModel.__init__`** — 로드 직전 디스크 가중치 해시를
  `self.sha256`(메모리 로드본 지문)·`self.loaded_at`로 기록. `model_status()`(`:136`)가
  `loaded_sha256`/`loaded_at`으로 노출.
- **`src/routes/version_routes.py`** — `GET /api/version`→`get_version_info`,
  `GET /api/version/verify`→`verify_integrity`(관리자 전용, `:20`).
- **`web/templates/base.html:236`** — 모달 배지 `restart_required` 시 "⟳ 재시작 필요" 표시,
  `:451` JS가 `d.restart_required` 분기 처리.
- **`VERSION.json`** — `model_sha256=620faad…`·`model_trained=2026-07-08`·`source_commit=a41e5a6`.
- **배포 스크립트** `deploy/build_deploy.ps1` — 소스 전용 `wordcloud-project.zip`을 프로젝트 상위
  (`D:\dev\wordcloud\`)에 생성. `plans`·`*.jsonl`·`*.zip`·`.env` 등 제외.
- **미커밋 파일(git status 실측)**: `M` 3파일(위 3자 무결성) / `??` `batch_verify_260710.md`.
  plans 월별 폴더(`04·06·07/`)와 `.playwright-mcp/`·`handoff/test`·`eval/judgment/test`는
  본 계획 범위 밖(각각 `10_01`·후속 정리 대상).

## 3. 구현 상세

> 3자 무결성 **코드 구현은 이미 워킹트리에 완료**되어 있다. 본 계획의 "구현"은 그 확정(커밋)과
> 배포·검증 파이프라인 실행이다. 신규 코드 작성은 없다.

### 3.1 커밋 (요구 1)

- 스테이징 대상: `src/modules/hr_sentiment.py`, `src/services/version_service.py`,
  `web/templates/base.html`, `plans/_datasets/kote_finetune/result/batch_verify_260710.md`.
- plans 월별 개편 산출물은 **의도적으로 제외** — `10_01`에서 별도 커밋(리뷰 혼선 방지).
- 커밋 메시지(안): `feat: 버전 무결성 3자 대조(선언·디스크·메모리) + batch_260709 재검증 리포트`
  - 트레일러 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

### 3.2 배포 zip 재빌드 (요구 2)

- 커밋 후 `VERSION.json`의 `source_commit`을 새 커밋 해시로 재생성(`scripts/gen_version.py`).
- `deploy/build_deploy.ps1` 실행 → `wordcloud-project.zip` 생성.
- 빌드 후 zip 내부 검증: `verify_integrity` 3자 대조 코드 포함, 감정규칙 5종 포함,
  `VERSION.json.source_commit` = 새 해시.

### 3.3 내부망 반입·검증 (요구 3·4 — 사용자 수행)

- zip만 반입(구 폴더 삭제 후 압축 해제 — metadata_*→integrated_* 리네임 잔재 제거).
- 모델·calibration은 이미 정상(620faad)이라 재반입 불필요.
- **서버 재시작**(사용자만 수행) 후: 버전 모달 3자 일치 확인 → health_advice 배치 준수율 실측.

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 | 수행 주체 |
|------|-----------|------|-----------|
| 1 | 3자 무결성 3파일 + 검증 리포트 diff 최종 확인 | — | Claude |
| 2 | 위 4파일 스테이징·커밋(plans 개편 제외) | 1 | Claude |
| 3 | `gen_version.py`로 VERSION.json source_commit 갱신·커밋 | 2 | Claude |
| 4 | `build_deploy.ps1` 실행 → zip 재빌드 | 3 | Claude |
| 5 | zip 내부 검증(3자 코드·규칙 5종·source_commit) | 4 | Claude |
| 6 | zip 내부망 반입(구 폴더 삭제 후) | 5 | 사용자 |
| 7 | 서버 재시작 | 6 | 사용자 |
| 8 | 버전 모달 3자 일치 확인 | 7 | 사용자 |
| 9 | health_advice 배치 1회 → 준수율 45.2%→90%+ 실측 | 8 | 사용자 |

## 5. 영향도 분석

- **변경 파일(커밋)**: `src/modules/hr_sentiment.py`(+23)·`src/services/version_service.py`(+71)·
  `web/templates/base.html`(+10)·`plans/…/batch_verify_260710.md`(신규) + 재생성 `VERSION.json`.
- **런타임 영향**: `verify_integrity`/`get_version_info`는 **관리자 모달·API 조회 경로에서만** 호출.
  배치·추론 핫패스 무변경(감정 판정 로직 불변). 실패해도 `model_status()`가 안전값 반환.
- **배포 영향**: zip 재반입은 소스 전용 — 모델 파일·DB·매핑 무변경. 반입 후 **재시작 필수**
  (미재시작 시 새 3자 검사 코드가 로드되지 않아 기능 무효).

## 6. 테스트/검증 계획

| # | 시나리오 | 기대 | 방법 |
|---|----------|------|------|
| T1 | 선언=디스크=로드본 | `match=True`, 배지 정상 | `verify_integrity()` 직접 호출(스크래치패드 테스트 4종) |
| T2 | 디스크≠선언 | `match=False, restart_required=False`, "반입 확인" | 동상 |
| T3 | 디스크=선언, 로드본≠디스크 | `match=False, restart_required=True`, "재시작 필요" | 동상 |
| T4 | 미로드 | `match=True`, note "첫 추론 시 로드" | 동상 |
| T5 | zip 내부 무결성 | 3자 코드·규칙 5종·source_commit 일치 | zip 해제 후 grep |
| T6 | 내부망 3자 일치 | 모달 "선언·디스크·메모리 모두 일치" | 재시작 후 모달(사용자) |
| T7 | 준수율 개선 | 45.2% → 90%+ | health_advice 배치 1회(사용자) |

> T1~T4는 서버 미기동 함수 직접 호출로 검증 가능(스크래치패드에 4-시나리오 스크립트 존재).
> T6·T7은 내부망·서버 재시작 필요 → **DN 판정은 T6·T7 실측 후에만**(그 전엔 Pre-Done).

## 7. 리스크 및 제약

- **서버 무단 실행 금지**: T6·T7은 사용자만 수행. Claude는 커밋·빌드·정적 검증까지만.
- **미재시작 함정**: zip 반입만 하고 재시작 안 하면 3자 검사 코드 미로드 → 기능 무효.
  역설적으로 이 기능 자체가 "미재시작"을 탐지하므로, 반입 후 모달로 자기검증 가능.
- **plans 개편 혼입 금지**: 월별 폴더 이동(153+파일)을 이 커밋에 섞으면 리뷰 불가 →
  반드시 `10_01`에서 분리 커밋.
- **오진 재발 방지**: 모델 버전 재대조 시 서빙 프리픽스(`장점/단점 평가:`)를 반드시 동일 적용
  (`batch_verify_260710.md` §검증 방법론 교훈).

---

**계획서 저장 위치**: `D:\dev\wordcloud\wordcloud_project\plans\2026\07\13_01_deploy-verify-3way\13_01_deploy-verify-3way.md`
