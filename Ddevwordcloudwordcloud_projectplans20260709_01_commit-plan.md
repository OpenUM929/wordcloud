# 누적 워킹트리 커밋 계획 (0701_01 이후 ~ 0709 정비까지)

> 유형: type-D 리팩토링/정리(커밋 조직화) · 상태: Todo(계획) · 작성일: 2026-07-09
> 참고: 기존에 이 파일에 있던 "판정 패킷↔그룹검토 게시판 통합" 설계(0701_03)는
> `_index.md` 확인 결과 **이미 Pre-Done으로 구현 완료**되어 있어 이 파일에서 교체한다.

## Context

마지막 커밋(`6e296bb` nav-hub, 2026-07-01)이후 `0701_02`~`0708_02` 및 오늘(0709) 배포 정비까지
**8일치 작업이 한 번도 커밋되지 않고** 워킹트리에 쌓였다(`git status` 188개 변경/미추적 항목).
사용자가 커밋 계획서 작성을 요청했다 — 실제 `git commit`은 계획 승인 + "수행" 지시 후에만 실행한다.

**가장 중요한 리스크**: `plans/_datasets/kote_finetune/` 아래 `model_out*`·`model_soup*` 디렉터리
**12개, 각 ~477MB = 총 6.7GB**가 `.gitignore`에 걸리지 않은 채 미추적 상태다. 무심코 `git add -A`를
하면 이 전부가 스테이징된다 — **반드시 1단계(gitignore 확장)를 먼저 커밋한 뒤에만** 이후 단계를 진행한다.

## 원칙

- 이 저장소의 기존 커밋 스타일을 따른다(`git log` 확인): `feat:`/`fix:`/`docs:`/`chore:` +
  한글 요약 + 관련 계획 ID를 괄호로 병기. 예: `feat: nav hub merge + collapse + version badge (0701_01)`.
- **레이어/관심사 단위의 굵은 커밋**을 쓴다(이 저장소 선례: `b20b54b routes & api layer`,
  `a81a7e1 emotion & batch core logic`) — 한 파일에 여러 계획의 변경이 누적된 경우(특히
  `perspective_service.py`) 훅 단위로 쪼개지 않고 파일째 하나의 커밋에 담는다(쪼개기 시도는
  대규모 로직 diff를 훅 단위로 잘못 나눌 위험이 커 오히려 불안전).
- **대용량·재생성 가능·백업성 파일은 커밋하지 않는다**(아래 §1 gitignore 확장 대상).
- `.clinerules`는 별도 서브모듈 저장소 — 이번 계획의 커밋 대상이 아니다(포인터 갱신은 §5 참고).

## §1. 선행 커밋 — `.gitignore` 확장 (필수, 최우선)

아래 패턴이 없으면 후속 `git add`에서 대형 바이너리가 실수로 스테이징될 수 있다. 실측 확인:

| 대상 | 크기 | 현재 상태 |
|------|------|-----------|
| `plans/_datasets/kote_finetune/model_out*` (12개) | 477MB × 12 ≈ 5.7GB | 미추적, 미무시 |
| `plans/_datasets/kote_finetune/model_soup_{uniform,greedy}` | 477MB × 2 ≈ 1GB | 미추적, 미무시 |
| `plans/_datasets/kote_finetune/eval/_gold_backup/` | 68MB | 미추적, 미무시 |
| `**/*.bak_*`, `**/*.bak_finetune`, `emotion.jsonl.bak_*` 등 타임스탬프 백업 | 다수 | 미추적, 미무시 |
| `wordcloud_project/build/` (setup.py 빌드 산출물) | 5.4MB | 미추적, 미무시 |
| 루트 `outputs/*.png`, `1.PNG`, `q.txt`, `.opencode/` | 소 | 미추적, 미무시(작업 스크래치) |

**커밋 내용**: `.gitignore`에 다음 패턴 추가.
```
wordcloud_project/plans/_datasets/kote_finetune/model_out*/
wordcloud_project/plans/_datasets/kote_finetune/model_soup_*/
wordcloud_project/plans/_datasets/kote_finetune/eval/_gold_backup/
**/*.bak_*
wordcloud_project/build/
outputs/
.opencode/
```
루트 `1.PNG`·`q.txt`는 gitignore 대상이 아니라 **작업 스크래치이므로 커밋에서 제외**(삭제는 사용자 확인 후).

커밋 메시지: `chore: gitignore 확장 — 대형 모델 산출물·타임스탬프 백업·빌드 산출물 제외`

## §2. 커밋 순서 (레이어별, §1 완료 후)

| # | 범위(관련 계획 ID) | 주요 파일/디렉터리 | 커밋 메시지(제안) |
|---|---------------------|---------------------|---------------------|
| 2 | 배포 패키징 스캐폴딩 | `pyproject.toml`, `MANIFEST.in`, `README_PACKAGE.md`, `src/**/__init__.py`(7개), `deploy/build_deploy.ps1`, `VERSION.json` | `chore: pip 설치가능 패키지 스캐폴딩 + 배포스크립트 VERSION.json 동기화` |
| 3 | 판정 패킷 v2 + 그룹검토 게시판 (0701_03, 0702_01, 0623_01 갱신) | `judgment_packet_service.py`, `perspective_routes.py`, `web/static/js/{judgment_apply,group_review}.js`, `web/templates/{judgment_apply,group_review,judgment_extract,batch_monitor,base}.html`, `web/static/css/nav.css`, `plans/2026/{0701_03,0702_01}/`, `plans/2026/0623_01.../test/test_judgment_extract.py` | `feat: 판정 패킷 status 통합 + 그룹검토 게시판 연결 (0701_03, 0702_01)` |
| 4 | 메타데이터 배치 + 필드신호 배선 (0701_02, 0707_01, 0708_01 일부) | `batch_routes.py`, `batch_events.py`, `batch_processor.py`, `batch_service.py`, `ui_routes.py`, `metadata_service.py`, `metadata_analysis.py`, `acquired_handoff.py`, `text_preprocessing.py`, `pseudonym_manager.py`, `pseudonym_mappings.enc`, `hr_sentiment.py`, `src/config/settings.py`, `utils/logger.py`, `utils/date_normalize.py`(신규), `plans/2026/{0701_02,0707_01,0708_01}/` | `feat: 메타데이터 배치 저장 개선 + 필드신호(장점/단점) 서빙 배선 (0701_02, 0707_01, 0708_01)` |
| 5 | 감정 판정 규칙 갱신 + 배포 정비 3종 (0708_02 L1~L3, 0709 q.txt) | `perspective_service.py`(누적 전체), 관련 유닛테스트 5개(`test_positive_rescue.py` 등 이미 추적분 포함), `plans/2026/0708_02.../` | `feat: 요청표지 화행 가드 + T-scaling 서빙 배선 + 부→긍 적대검증 (0708_02, 0709)` |
| 6 | KoTE 파인튜닝 스크립트·문서(대용량 데이터 제외) | `plans/_datasets/kote_finetune/scripts/*.py`(신규 다수), `RUNBOOK.md`, `README.md`, `ROADMAP.md`, `DEPLOYMENT_CHECKLIST.md`, `result/IMPROVEMENT_HISTORY.md`, `result/*.{md,json}`(소형만), `emotion/emotion.jsonl`(리비전) | `docs: KoTE 파인튜닝 데이터셋 누적 로그 + 감사/적대검증 스크립트` |
| 7 | plans 잔여 신규 폴더 + 인덱스 | `plans/2026/{0624_04,0624_05,0625_01,0630_01,0630_04}/`, `plans/2026/_index.md` | `docs: plans 인덱스 갱신 + 잔여 계획서(0624~0630) 반영` |

## §3. 커밋 대상에서 제외(보류) — 별도 검토 필요

- `plans/_datasets/kote_finetune/eval/validation_candidates_{260623,260624,260708}.jsonl` (합 ~62MB, 재생성 가능) —
  기본 제외 권고. 사용자가 "정본으로 보존"을 원하면 §6에 별도 커밋으로 추가.
- `plans/_datasets/kote_finetune/eval/review/` (9.5MB, 판정 큐/prefill 다수) — 정정 확정 전 임시 산출물 성격이 강해
  보류 권고. 확정되면 gold와 함께 커밋.
- 각종 `.bak`, `.bak_*` — §1 gitignore로 커밋 대상에서 원천 제외.

## §4. 검증 절차 (실행 단계에서)

1. §1 커밋 직후 `git status --short | grep model_out` → 결과 없어야 함(무시 확인).
2. 각 커밋 전 `git add <경로들>`(파일 나열, `-A` 금지) → `git status`로 스테이징 내역 재확인.
3. 커밋 후 `git show --stat HEAD`로 의도한 파일만 포함됐는지 확인, 특히 5.4MB 이상 파일 없는지.
4. 전체 완료 후 `git log --oneline -10`으로 순서·메시지 확인, `git status`가 깨끗한지(추적 대상 기준) 확인.

## §5. `.clinerules` 서브모듈

`git -C .clinerules status`는 클린(로컬 변경 없음) — 루트의 `M .clinerules`는 **포인터만 최신 커밋
(`5049a3d`)으로 전진**한 상태다. `06.git-rules.md` 규칙대로 별도 커밋: `git add .clinerules && git commit`.
서브모듈 자체 push는 불필요(이미 그쪽 저장소에 커밋되어 있음, 포인터만 메인에 반영).

## §6. 실행 순서 요약

§1(gitignore) → §5(서브모듈 포인터, 언제 넣어도 무해) → §2의 2~7번 순서대로.
사용자가 "수행"이라고 명시할 때까지 실제 `git add`/`git commit`은 실행하지 않는다.
각 커밋 후 결과(해시·포함 파일 수·용량)를 간단히 보고한다.


1차 구현(0701_03 v1)은 needs_human 항목을 **별도 파일(eval/*.jsonl)로 내보내고 다시 반영**하는
2-아티팩트 브리지였다. 사용자 피드백: 그건 스스로 만든 복잡함이며, **패킷 item 스키마를 그룹검토
게시판 행 구조와 통일**하고 **각 item에 `status` 상태값**을 두면 변환·별도 파일이 필요 없다.
같은 게시판이 패킷을 직접 판정하고, 포맷이 하나로 일관된다.

사용자 확정 결정:
- **상태 필드 = `status` 정수**: `1`=AI 검증 필요, `2`=사람 판단 필요, `3`=확정.
- **그룹검토 게시판이 패킷을 직접 로드/저장** (별도 eval jsonl·변환·reflect 엔드포인트 폐기).

목표: 추출→AI판정→(저확신) 사람 게시판→반영이 **패킷 하나** 안에서 status 전이로 흐르게 한다.

## 통합 item 스키마 (게시판 행 = 패킷 item)

게시판이 읽는 필드(`perspective_routes.py:1621-1627`)에 맞춰 패킷 item을 재정의:

```json
{
  "rec_id": "101_2",                    // db_id_sent_idx (게시판 키)
  "key": {"db_id": 101, "sent_idx": 2}, // DB 반영 키(유지)
  "text": "협업이 원활했다",             // 가명
  "field": "",                          // 장점/단점(문장별 미상 시 "")
  "cur_rule_label": "neutral",          // 게시판 '현규칙'(구 cur_label)
  "kote": [0.4,0.4,0.2], "gap":0.0, "hard":"low_margin", "margin_band":"0.05",
  "ai_reference": {"polarity": null, "confidence": null, "reason": null}, // AI 판정 출력(구 result)
  "status": 1,                          // 1/2/3
  "human_decision": null                // 게시판이 씀
}
```

**status 전이:**
- 추출(`build_judgment_packet`) → `status=1`, ai_reference=null, human_decision=null.
- AI 판정(오프라인, `_stages.judge` 지침대로) → ai_reference 채움 + **확신 시 `status=3`, 저확신 시 `status=2`**.
- 게시판(status==2만 노출) → human_decision 기록, **`status=3`**.
- 반영(`apply_judgment_packet`) → **status==3만** DB 반영. 최종 라벨 = `human_decision or ai_reference.polarity`.

## 전체 흐름 (단일 패킷)

```
추출 → 패킷(items status=1)  [배치 시 eval/judgment/<label>/<batch>.json 자동 저장]
  ↓ (AI가 패킷 판정: ai_reference+status 채움)
[판정반영 페이지 업로드] → status==3 반영 + 패킷을 서버에 저장(게시판 접근용) + status 분포 표시
  ↓ (status==2 남으면 게시판에서)
[그룹검토: 같은 게시판이 패킷 로드→status==2 판정→human_decision·status=3 저장(같은 파일)]
  ↓
[판정반영: 저장된 서버 패킷 선택 → 재적용] → 신규 status==3 반영
```

## 구현

### 1. `src/services/judgment_packet_service.py`

- **v1 잔재 삭제**: `_eval_root`, `export_needs_human_to_review`, `reflect_review_file` 제거.
- **`select_hard_sentences`(`:151`)**: item을 통합 스키마로 생성 — `rec_id`, `field=""`,
  `cur_rule_label`(구 cur_label), `ai_reference={polarity:null,...}`(구 result:null),
  `status=1`, `human_decision=null`. (`key`/`text`/`kote`/`gap`/`hard`/`margin_band` 유지.)
- **`_packet_skeleton`(`:97`)**: `_stages.judge` 지침을 status 흐름으로 재작성
  ("각 item의 ai_reference를 채우고, 긍↔부 확신 시 status=3, 애매하면 status=2. status=2는
  사람 게시판으로 감"). `긍↔부 오분류 0·중립↔긍정 허용` 규칙 유지. `_key_fields`에 rec_id 추가.
- **`apply_judgment_packet`(`:256`)**: status==3 item만 반영(라벨=human_decision or
  ai_reference.polarity, 유효 3분류만). status==2→pending_human, status==1→pending_ai,
  그 외→skipped 로 집계. 레거시 호환: `status` 없고 `result` 있으면 파생(needs_human→2 else 3).
  반환 `{inserted_sentences, updated_evaluations, pending_human, pending_ai, skipped}`.
- **신규 `load_packet(path)` / `update_packet_decisions(path, decisions)`**: 게시판 저장용 —
  패킷 로드 후 rec_id로 item 찾아 `human_decision` 기록·`status=3` 설정, 봉투 보존하며 재기록.
  경로 안전화는 라우트의 `_safe_packet_path` 통과분만.

### 2. `src/routes/perspective_routes.py`

- **v1 잔재 삭제**: `/judgment/review-files`, `/judgment/reflect-from-review` 라우트 제거.
- **`api_judgment_apply`(`:652`) 개정**: 업로드/JSON 패킷 반영 후 **서버에 저장**
  (`save_packet_file`(`:86`) 재사용, label/batch = packet.source) → 응답에 status 분포와
  저장 파일명 포함. `POST` body에 `{file}`(서버 패킷 재적용)도 허용.
- **게시판 3종 확장**(패킷 파일 지원, 게시판 JS 무변경):
  - `_safe_packet_path()` 신규: `eval/judgment/**/*.json` 서브트리 화이트리스트(traversal 가드,
    기존 `_safe_eval_path`(`:1571`)와 동형).
  - `/group-review/files`(`:1582`): 기존 `*.jsonl` + `eval/judgment/**/*.json` 패킷도 나열
    (name에 상대경로, rows=status==2 건수).
  - `/group-review/load`(`:1601`): 파일이 패킷(.json)이면 `items`에서 **status==2만** 게시판 행으로
    매핑(rec_id/text/field/cur_rule_label/ai_reference/decision=human_decision).
  - `/group-review/save`(`:1631`): 패킷이면 `update_packet_decisions`로 위임(human_decision+status=3).
    기존 jsonl 경로는 그대로.

### 3. UI

- **v1 잔재 되돌리기** (`web/templates/judgment_apply.html`, `web/static/js/judgment_apply.js`):
  "그룹검토 완료분 반영" 섹션·`review_file` 안내·review-files/reflect 호출 제거.
  **단, apply POST URL 교정(`/judgment/apply`→`/api/perspective/judgment/apply`)은 유지**(기존 버그).
- **판정반영 결과 표시**: 요약을 status 분포로 — 반영(3) / 사람 대기(2) / AI 대기(1) / 건너뜀.
  status==2가 있으면 "[그룹검토에서 판정](/group-review)" 안내. 서버 저장 패킷 재적용 드롭다운(선택).
- **그룹검토 게시판(`group_review.html/js`)은 무변경** — 스키마 일치로 열/키보드/저장 그대로,
  드롭다운에 패킷 파일이 추가로 뜬다.

## 재사용

- 패킷 저장: `save_packet_file`(`judgment_packet_service.py:86`), 경로 안전화 `_safe_segment`(`:64`).
- DB 병합: `apply_judgment_packet`의 by_db in-place UPDATE 로직(`:285-302`) 유지.
- 배치 자동 저장: `batch_processor.py:1084-1086`은 `build_judgment_packet`/`save_packet_file` 호출만
  하므로 스키마 변경이 자동 반영(수정 불요).

## 검증 (end-to-end)

> 서버 무단 실행 금지 — 수동 왕복은 사용자 실행. 아래는 단위테스트 + 수동 절차.

1. **기존 테스트 갱신**: `plans/2026/0623_01_judgment-extract-ui/test/test_judgment_extract.py` —
   item 스키마 변경(rec_id/status/ai_reference)에 맞춰 단언 수정.
2. **신규 단위테스트**(`plans/2026/0701_03.../test/test_packet_status_flow.py`):
   - `apply_judgment_packet`: status 1/2/3 혼합 → status==3만 인메모리 sqlite에 반영
     (라벨=human_decision 우선, 없으면 ai_reference.polarity), 2/1은 pending 집계.
   - `update_packet_decisions`: 패킷 파일 rec_id로 human_decision 기록·status=3 전이, 봉투·key 보존.
   - 레거시 패킷(status 없음, result 있음) 파생 반영.
3. **수동 왕복**(사용자): 배치→패킷 저장 확인 → 패킷을 AI 판정(ai_reference+status) → 판정반영
   업로드(status 분포 확인) → `/group-review`에서 패킷 파일 선택·status==2 판정 → 판정반영에서
   서버 패킷 재적용 → 대상 evaluations `sentiment_corrections`에 반영·status 전이 확인.

## 문서/상태

- 프로젝트 계획서 `wordcloud_project/plans/2026/0701_03_needs-human-bridge/0701_03_needs-human-bridge.md`를
  본 재설계로 **개정**(수정 이력 테이블에 "v1 별도파일 브리지 → v2 status 통합 패킷" 기록), `_index.md` 갱신.
- v1에서 이미 커밋 전 워킹트리에 만든 코드(export/reflect/UI 섹션)는 **되돌린다**.
- DN은 수동 왕복 실동작 검증 후. 단위테스트만 통과 시 Pre-Done.
