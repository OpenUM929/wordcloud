# 계획서 — 배치 이어서 처리 진행 현황 및 배치 명칭 출력 오류 수정

> 상태: DN | 작성일: 2026-06-18 | 완료일: 2026-06-18
> 작업 유형: A (버그 수정/핫픽스)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-18 | 전체 | 최초 작성 |

## 1. 배경 및 목적

메타데이터 생성(배치) 기능에서 다음 두 가지 버그가 보고됨:

1. **이어서 배치(resume) 시 진행 현황이 "메타데이터 생성 중"으로만 출력**되고, 현재 처리 인원 수/전체 인원 수가 표시되지 않음
2. **메타데이터 생성 시 기록한 배치 명칭(display_name)이 그룹 분석 테스트에서 자동 생성 이름(batch_YYYYMMDD_X)으로 출력**됨

## 2. 원인 분석

### 이슈 1: Resume 진행 현황 표시 오류

**근거**: `batch_processor.py` 코드 분석 및 `metadata_batch.js` 프론트엔드 코드 분석

**3개 원인**:

| # | 위치 | 문제 | 설명 |
|---|------|------|------|
| 1a | `batch_processor.py:844` | 초기 메시지 포맷 불일치 | `f'메타데이터 생성 중 (0/{total_employee_count})'` — 892행의 `f'분석 처리 중 ({completed:,} / {total_employee_count:,}명)'`와 포맷이 다름 |
| 1b | `batch_processor.py:815-843` | Resume 시 `prior_completed` 미반영 | `total_employee_count = len(employee_items)`에서 `prior_completed`(이미 완료된 인원) 제외되어 잔여 인원만 표시. 사용자는 "(완료인원+진행) / (완료인원+잔여)" 기대 |
| 1c | `metadata_batch.js:1341-1345` | `openBatchSse()`가 `data.status` 무시 | `openBatchSse()`(resume flow)는 `steps[currentStepIdx]`만 사용. `openSseAndListen()`(신규 flow)은 `data.status` 우선 사용 |

### 이슈 2: 배치 명칭(display_name) 출력 오류

**근거**: `batch_processor.py` → `_ensure_batch_summary()` 호출 시점, `batch_manager.py` `get_batch_list()` 코드 분석

**2개 원인**:

| # | 위치 | 문제 | 설명 |
|---|------|------|------|
| 2a | `batch_processor.py:1003-1005` | `batch_summary.json` 생성 시점이 너무 늦음 | `_ensure_batch_summary()`는 `process_batch()` 맨 마지막에만 호출됨. Stage 3에서 DB에는 데이터가 저장되지만 `batch_summary.json`이 없으면 `display_name`을 읽을 수 없음 → `batch_id`로 fallback |
| 2b | `batch_manager.py:38-44` | `get_batch_list()`가 `batch_summary.json` 미참조 | `/api/batch/list` 엔드포인트가 사용. `display_name`을 `batch_id` 문자열 파싱으로만 생성, `batch_summary.json`의 `display_name` 필드를 전혀 읽지 않음 |

## 3. 수정 방안

### 수정 1a: Stage 3 초기 메시지 포맷 통일

- **파일**: `batch_processor.py:844`
- **변경**: `f'메타데이터 생성 중 (0/{total_employee_count})'` → `f'분석 처리 중 ({_prior_count:,} / {_total_all:,}명)'`
- **효과**: 초기 메시지 포맷이 진행 중 업데이트 메시지(892행)와 동일해짐

### 수정 1b: Resume 시 전체 인원 표시

- **파일**: `batch_processor.py:842-844, 890-892`
- **변경**:
  - `_total_all = len(prior_completed) + len(employee_items)` (전체 인원)
  - `_prior_count = len(prior_completed)` (이미 완료된 인원)
  - `_display_completed = _prior_count + completed` (누적 완료 인원)
  - 진행 메시지에 `_display_completed / _total_all` 사용
  - 진행률(progress) 계산은 잔여 인원 기준 유지 (45% ~ 90% 맵핑 정확성)
- **효과**: "분석 처리 중 (45 / 100명)" 형태로 전체 인원 기준 표시

### 수정 1c: openBatchSse()에 data.status 반영

- **파일**: `metadata_batch.js:1341-1345`
- **변경**: `openSseAndListen()`과 동일하게 `data.status` 우선 사용, 없으면 `steps[idx]` fallback
- **효과**: Resume flow에서도 서버가 보내는 `status_message`(예: "분석 처리 중 (45 / 100명)")가 정상 표시됨

### 수정 2a: batch_summary.json 조기 생성

- **파일**: `batch_processor.py:763` (Stage 2 성공 직후)
- **변경**: Stage 2(분석기 초기화) 성공 직후 `_ensure_batch_summary()` 호출 추가
  - `display_name = (data.get('batch_display_name') or '').strip()`으로 전달
  - 기존 종료 시점(1005행) 호출 유지 (employee_count 등 최종값 갱신)
- **효과**: Stage 3 시작 시점에 `batch_summary.json`이 존재하게 되어, 그룹 분석 테스트 등에서 display_name 조회 가능

### 수정 2b: batch_manager.get_batch_list()에 display_name 읽기 추가

- **파일**: `batch_manager.py:38-44`
- **변경**: `perspective_service._load_batch_list()`와 동일하게 `batch_summary.json` 로드하여 `display_name` 필드 읽기
  - `display_name`이 있으면 사용, 없으면 기존 batch_id 기반 포맷 유지
- **효과**: `/api/batch/list` 엔드포인트를 사용하는 페이지(워드클라우드 미리보기 등)에서도 명칭 정상 표시

## 4. 영향도 분석

| 변경 파일 | 영향 범위 | 리스크 |
|-----------|-----------|--------|
| `batch_processor.py` (3개 변경) | 배치 처리 전체 흐름 — Stage 2~3 메시지 | Stage 2 성공 직후에도 `batch_dir`이 유효해야 함 (확인 완료) |
| `metadata_batch.js` (1개 변경) | Resume flow SSE 텍스트 표시 | 하위 호환: `data.status`가 없으면 기존 `steps[idx]` 사용 |
| `batch_manager.py` (1개 변경) | `/api/batch/list` 응답 | `processed_data_dir`이 None이면 skip (기존 동작 유지) |

## 5. 테스트 계획

| 시나리오 | 검증 항목 | 방법 |
|----------|-----------|------|
| 신규 배치 처리 | 진행 메시지가 "분석 처리 중 (X / Y명)" 포맷으로 표시되는가 | UI 확인 |
| 이어서 배치 (resume) | 진행 메시지에 "전체인원 중 완료+진행"이 표시되는가 | UI 확인 |
| 배치 명칭 입력 후 그룹 분석 테스트 | 입력한 명칭이 그룹 분석 배치 목록에 표시되는가 | UI 확인 |
| 배치 명칭 미입력 | 기존처럼 batch_id가 표시되는가 | UI 확인 |
| `/api/batch/list` | display_name이 batch_summary.json에서 로드되는가 | API 응답 확인 |

## 6. 리스크 및 제약

- `batch_processor.py`의 Stage 2 성공 직후 `_ensure_batch_summary()` 호출 시 `batch_dir`이 유효해야 함. `initialize_batch_directory()` 또는 resume의 `batch_dir` 재사용 로직 이후이므로 유효함.
- `batch_manager.get_batch_list()`의 `processed_data_dir` 파라미터가 `None`인 경우 `batch_summary.json` 조회를 skip하도록 처리함.
