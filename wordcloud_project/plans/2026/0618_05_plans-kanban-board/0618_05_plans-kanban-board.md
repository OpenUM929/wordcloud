# 계획서 — Plans Kanban Board + 폴더 선택형 프레임워크

> 상태: Done(코드 적용 확인 — /admin/plans 운영 중, 2026-06-18) | 작성일: 2026-06-18
> 작업 유형: B (기능 개선/신규 기능)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-18 | 전체 | 최초 작성 |

## 1. 배경 및 목적

### 1.1 문제
- `plans/2026/` 폴더에 48개 계획서가 누적되었지만 **현황 파악이 어려움** (폴더명으로만 확인)
- `_index.md`의 **상태 표기가 불일치** (`DN`/`✅ DN`/`🟡 PND`/`PND` 혼용)
- 각 계획서 문서를 열어야만 **상세 내용 확인 가능**
- **타 프로젝트에서 재사용 불가** — 현재 구조가 wordcloud 프로젝트에 강결합

### 1.2 목표
1. `plans/` 폴더를 **Kanban 보드** 형태로 시각화 (Todo → Doing → Done)
2. **폴더 경로를 선택 가능**하게 하여 타 프로젝트에서도 동일 컴포넌트 사용 가능
3. `_index.md` 포맷을 **표준화**하여 파싱 안정성 확보
4. 개별 계획서 **상세 내용을 모달로 바로 확인**

## 2. 현재 시스템 분석

### 2.1 _index.md 포맷 (현재)
```markdown
| 계획서 | 작업 요약 | 상태 | 작성일 |
|--------|-----------|------|--------|
| 0421_01_batch-scalability-plan | 배치 처리 대용량 최적화 | PND | 2026-04-21 |
```
- **문제점**: 상태 컬럼에 `PND`, `🟡 PND`, `DN`, `✅ DN`, `📄 분석` 혼용 → 파싱 복잡도 증가
- **개선 방향**: 상태는 **약어만** 사용 (`PND`/`DN`/`분석`), 표시용 emoji는 UI에서 처리

### 2.2 개별 계획서 포맷 (현재)
```markdown
> 상태: Todo | 작성일: 2026-06-18
> 작업 유형: B
```
- **문제점**: `_index.md`의 `작업 요약`과 중복 정보. Kanban 카드에 필요한 제목/요약을 파싱하려면 두 파일을 모두 읽어야 함
- **개선 방향**: `_index.md`를 **단일 정보 원천(Single Source of Truth)** 으로 사용

### 2.3 관련 파일/함수
- `src/routes/admin_routes.py` — admin_bp 패턴 (참조용)
- `src/config/settings.py` — 설정 추가 위치
- `web/app.py` — blueprint 등록 위치
- `web/templates/base.html` — nav 링크 추가 위치
- `mistune==3.1.4` — `.md` → HTML 변환용 (requirements.txt에 존재)

## 3. 구현 상세

### 3.1 설정 계층 (`src/config/settings.py`)

```python
# Plans directory (칸반보드 대상 폴더, 다중 프로젝트 지원)
PLANS_DIR = os.getenv('PLANS_DIR', os.path.join(PROJECT_ROOT, '..', 'plans', '2026'))
PLANS_ROOTS = os.getenv('PLANS_ROOTS', '').split(',') if os.getenv('PLANS_ROOTS') else []
# PLANS_ROOTS 예시: "D:/project-a/plans/2026,D:/project-b/docs/plans"
```

- `PLANS_DIR`: 기본 대상 폴더
- `PLANS_ROOTS`: 쉼표 구분 다중 경로 — UI 드롭다운에 표시됨

### 3.2 백엔드 (`src/routes/plans_routes.py`)

**4개 라우트**:

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `GET /admin/plans` | HTML | 칸반보드 페이지 (서버사이드 렌더링) |
| `GET /admin/api/plans/check` | JSON | `{modified_at}` — `_index.md` 수정시각만 반환 |
| `GET /admin/api/plans?dir=<path>` | JSON | 전체 plan 목록 (상태별 그룹, 지정 경로의 `_index.md` 파싱) |
| `GET /admin/api/plans/<plan_id>/content?dir=<path>` | JSON | 특정 plan 메인 `.md` → mistune HTML 변환 |

**데이터 추출 로직** (`parse_plans()`):
1. 지정된 `dir`의 `_index.md` 읽기
2. 마크다운 테이블 파싱 (정규식)
3. 각 plan 폴더 스캔: 메인 `.md` 존재여부, `result/`, `test/` 서브폴더 여부
4. 상태 정규화: `DN`/`✅ DN` → `done`, `PND`/`🟡 PND` → `todo`, `분석`/`📄 분석` → `doing`
5. 상태별 그룹핑 + 통계 (완료/작업중/예정/총계)

### 3.3 프론트엔드 (`web/templates/plans_kanban.html`)

**레이아웃**:
```
┌──────────────────────────────────────────────────────────┐
│ 📋 Plans Kanban    ✅ 34 / 🔄 1 / 📋 13 / 총 48         │
│ [▼ 폴더 선택] D:\dev\wordcloud\plans\2026                │
├──────────┬──────────────┬────────────────────────────────┤
│ 📋 Todo  │ 🔄 Doing     │ ✅ Done                        │
│ (13)     │ (1)          │ (34)                           │
│ ┌──────┐ │ ┌──────────┐ │ ┌──────┐ ┌──────┐ ┌──────┐   │
│ │card  │ │ │card      │ │ │card  │ │card  │ │card  │   │
│ └──────┘ │ └──────────┘ │ └──────┘ └──────┘ └──────┘   │
└──────────┴──────────────┴────────────────────────────────┘
```

**카드** (최소화, 클릭 시 모달):
```
┌─────────────────────┐
│ 0617_01             │  ← plan_id (bold)
│ emotion-rule-mining │  ← slug (muted)
│ ✅ Done             │  ← status badge
└─────────────────────┘
```

**모달** (클릭 시):
```
┌─────────────────────────────────────────────────────┐
│ 📄 0617_01_emotion-rule-mining               [✕]    │
├─────────────────────────────────────────────────────┤
│  (mistune HTML 렌더링 — .md 내용)                    │
│                                                     │
│  # 코퍼스 기반 감정 규칙 마이닝                       │
│  ...                                                │
│                                                     │
│  📁 폴더 열기  ·  📄 result/ (파일수)  ·  🧪 test/   │
├─────────────────────────────────────────────────────┤
│                                        [닫기]        │
└─────────────────────────────────────────────────────┘
```

**자동 갱신**:
- JS 10초 간격 `GET /admin/api/plans/check?dir=...` → `_index.md` 수정시각 확인
- 변경 감지 시에만 `GET /admin/api/plans?dir=...` 호출 → 카드 재렌더링
- 폴더 선택 변경 시 전체 페이지 리로드 없이 카드 교체

**폴더 선택기**:
- 상단 `<select>` 드롭다운
- `PLANS_ROOTS` + 현재 `PLANS_DIR` 목록 표시
- 변경 시 `?dir=` 파라미터 업데이트 + 칸반 재렌더링

### 3.4 _index.md 포맷 표준화

**변경 후 포맷** (상태 컬럼 통일):
```markdown
# 2026 계획서 인덱스

| 계획서 | 작업 요약 | 상태 | 작성일 |
|--------|-----------|------|--------|
| 0618_04_batch-resume-progress | 배치 이어서 처리 진행 현황 수정 | DN | 2026-06-18 |
| 0618_03_deploy-wc-parallel | 제출용 저장 워드클라우드 생성 병렬화 | PND | 2026-06-18 |
| 0618_02_wordcloud-opt-feasibility | 0617_07 기법의 워드클라우드 적용 가능성 분석 | 분석 | 2026-06-18 |
```

**규칙**:
- 상태값은 항상 **약어**만: `DN` / `PND` / `분석`
- Kanban 표시용 emoji는 UI 레이어에서 자동 추가
- `_index.md` 수정 시 자동으로 Kanban에 반영됨

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `settings.py` — `PLANS_DIR`, `PLANS_ROOTS` 추가 | 없음 |
| 2 | `src/routes/plans_routes.py` 생성 — `_index.md` 파서 + 4개 라우트 | 1 |
| 3 | `web/templates/plans_kanban.html` 생성 — 칸반보드 + 모달 + JS 폴링 | 2 |
| 4 | `web/app.py` — `plans_bp` 등록 | 2 |
| 5 | `web/templates/base.html` — 네비 링크 추가 | 4 |
| 6 | `03.plan-mode.md` — _index.md 포맷 지침 업데이트 | 없음 |
| 7 | `_index.md` — 오염된 상태값 정리 + 신규 항목 추가 | 6 |

## 5. 영향도 분석

| 변경 파일 | 영향 범위 | 리스크 |
|-----------|-----------|--------|
| `src/config/settings.py` | 설정 2개 추가 | 기본값 있으므로 기존 코드 변경 없음 |
| `src/routes/plans_routes.py` | 신규 파일 | 기존 라우트와 충돌 없음 (`/admin/plans` 새 경로) |
| `web/templates/plans_kanban.html` | 신규 파일 | 단독 페이지, 기존 템플릿 의존 없음 |
| `web/app.py` | 블루프린트 1줄 추가 | 단순 등록, 사이드 이펙트 없음 |
| `web/templates/base.html` | nav 링크 1줄 추가 | 디자인 영향 없음 |
| `.clinerules/core/00-core/03.plan-mode.md` | _index.md 규칙 업데이트 | 향후 계획서 작성에만 영향 |
| `plans/2026/_index.md` | 상태값 정규화 | 48개 엔트리 상태값 일괄 수정 필요 |

## 6. 테스트/검증 계획

| 시나리오 | 검증 항목 | 방법 |
|----------|-----------|------|
| 칸반보드 페이지 로드 | 3개 컬럼에 카드가 올바르게 분류되는가 | 브라우저 확인 |
| 폴더 선택 변경 | 다른 `_index.md`로 전환 시 카드가 교체되는가 | 드롭다운 조작 |
| 카드 클릭 | 모달에 `.md` 내용이 HTML로 표시되는가 | 클릭 확인 |
| `_index.md` 수정 | 10초 내 자동 갱신되는가 | `_index.md` 수정 후 대기 |
| 상태값 혼용 내성 | `✅ DN`/`DN`/`🟡 PND`/`PND` 모두 정상 파싱되는가 | 혼용 상태 입력 후 확인 |
| 타 프로젝트 폴더 | 다른 구조의 `_index.md`도 동일하게 표시되는가 | 경로 변경 테스트 |
| 존재하지 않는 폴더 | 에러 메시지 표시 + 빈 보드 | 유효하지 않은 경로 입력 |

## 7. 리스크 및 제약

- **`_index.md` 테이블 파싱은 행 수와 포맷 일관성에 의존** — 형식이 크게 달라지면 파싱 실패
- **파일시스템 기반이므로 WAS 여러 개일 때 동기화 문제 없음** (stateless)
- `.md` 파일이 매우 클 경우 모달 렌더링 성능 저하 가능 — mistune은 스트리밍 미지원, 전체 로드
- **PLANS_ROOTS 경로는 보안 검증 필요** — 임의 경로 접근 가능하므로 관리자 전용
