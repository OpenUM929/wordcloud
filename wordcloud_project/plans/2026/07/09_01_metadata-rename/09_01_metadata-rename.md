# 계획서 — 메타데이터→통합데이터 용어 통일 리팩토링

> 상태: Todo | 작성일: 2026-07-09
> 작업 유형: D (리팩토링)
> 선행: (없음)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-09 | 전체 | 최초 작성 |

## 1. 배경 및 목적

### 1.1 배경

현재 시스템의 핵심 데이터 구조 명칭으로 **"메타데이터(metadata)"** 를 사용 중이나, 실제 저장 및 관리되는 데이터의 성격과 부합하지 않음.

**실제 데이터 구조가 포함하는 내용:**

| 항목 | 포함 여부 | 설명 |
|------|-----------|------|
| 원본 평가 문서 | ✅ | CSV에서 읽은 평가 텍스트 원본 |
| 정제 결과 | ✅ | 노이즈 제거, 정규화된 텍스트 |
| NLP 분석 | ✅ | 형태소 분석, 토큰, 의미 단어, 문장 경계 |
| 감정 분석 | ✅ | 긍/부/중 분류, 신뢰도, 문장별 분석, 키워드 |
| 리더십 분석 | ✅ | 리더십 점수, 강점/약점 |
| 비꼼 분석 | ✅ | 비꼬임 감지 결과 |
| 욕설 분석 | ✅ | 욕설 탐지, 빈도, 통계 |
| 통합 분석 | ✅ | 다중 평가 통합 감정, 단어 빈도, 평가자 분포 |
| 문장 KoTE 캐시 | ✅ | 문장별 원시 감정 점수 |
| 워드클라우드 | ✅ | 생성 경로, 생성 정보 |
| **메타정보** (세션ID, 생성시각, 버전) | ✅ | **이것만이 진정한 메타데이터** |

> **현재 "메타데이터" 구조에서 진정한 메타데이터는 `session_id`, `created_at`, `version`, `processing_status` 등 극히 일부에 불과함. 대부분은 **분석이 완료된 통합 데이터** 자체임.**

### 1.2 목적

1. 용어 정확성 확보 — 데이터의 실제 성격을 반영하는 명칭으로 변경
2. 도메인 언어 통일 — 사용자/이해관계자와의 커뮤니케이션 혼선 방지
3. 문서/코드 일관성 — 용어 혼용(`메타데이터` vs `통합데이터`) 해소
4. 유지보수성 향상 — 신규 개발자 온보딩 시 개념 이해 용이

## 2. 현재 코드 분석

### 2.1 영향 범위 종합

**총 87개 파일, 약 1,205건 참조** (build/lib 제외, plans 제외 시 42개 파일·약 835건)

| 범주 | 파일 수 | 메타데이터(한글) | metadata(영문) | Metadata(클래스) | imeta/tmeta(폴더) | 합계 |
|------|---------|-----------------|----------------|------------------|-------------------|------|
| 핵심 모듈 (src/) | 17 | 25 | 269 | 10 | 33 | 337 |
| 템플릿/JS (web/) | 8 | 42 | 79 | 63 | 10 | 194 |
| 문서 (doc/) | 11 | 119 | 128 | 15 | 20 | 282 |
| 계획서 (plans/) | 45 | 109 | 218 | 2 | 41 | 370 |
| 기타 | 6 | 13 | 7 | 0 | 0 | 20 |
| **합계** | **87** | **304** | **701** | **90** | **104** | **1,205** |

### 2.2 주요 변경 대상 파일 (Top 10)

| 파일 | 참조 수 | 주요 참조 형태 |
|------|---------|---------------|
| `src/models/metadata_manager.py` | 102 | 클래스명, 메서드명, 변수명, 주석, 폴더경로(`tmeta/`, `imeta/`) |
| `web/templates/wordcloud.html` | 87 | 템플릿 변수(`metadata`), JS 변수, UI 레이블 |
| `src/services/batch_processor.py` | 62 | `metadata` 변수, `tmeta` 경로, `imeta` 경로 |
| `doc/implementation_plan.md` | 56 | 문서 설명, 데이터 구조 명세 |
| `doc/metadata_modularization_plan.md` | 52 | 문서 전체 — 용어 변경 필요 |
| `web/static/js/metadata_batch.js` | 51 | JS 변수, 함수명, API 호출 |
| `src/services/metadata_service.py` | 45 | 함수명, 변수명, 주석 |
| `plans/2026/0612_01_batch-work-order.md` | 32 | `metadata` 경로 참조 |
| `doc/metadata_modularization_checklist.md` | 33 | 체크리스트 항목 |
| `src/modules/metadata_analysis.py` | 2 | 모듈명, 주석 |

### 2.3 기존 용어 사용 패턴

| 패턴 | 예시 | 변경 방향 |
|------|------|-----------|
| 클래스명 | `MetadataManager` | `IntegratedDataManager` |
| 모듈명 | `metadata_analysis.py` | `integrated_analysis.py` |
| 라우트 | `/api/metadata/generate` | `/api/integrated/generate` |
| 블루프린트 | `metadata_bp` | `integrated_bp` |
| 폴더명 | `tmeta/`, `imeta/` | `tdata/`, `idata/` |
| 변수명 | `metadata` | `integrated_data` |
| API 응답 | `{'success': True, 'data': metadata}` | key 유지 (API 호환) |

## 3. 변경 설계

### 3.1 네이밍 매핑

| 현재 명칭 | 변경 명칭 | 근거 |
|-----------|-----------|------|
| **메타데이터** | **통합데이터** | 인사평가 분석 결과가 통합된 데이터 |
| **Metadata** | **IntegratedData** | 영문 코드 일관성 |
| **metadata** | **integrated_data** | Python 변수/속성 snake_case |
| **tmeta** (통합메타) | **tdata** (통합데이터) | 폴더명, 약어 길이 유지 |
| **imeta** (개별메타) | **idata** (개별데이터) | 폴더명, 약어 길이 유지 |
| **MetadataManager** | **IntegratedDataManager** | 클래스명 |
| **metadata_analysis** | **integrated_analysis** | 모듈명 |
| **metadata_service** | **integrated_data_service** | 서비스명 |
| **metadata_routes** | **integrated_data_routes** | 라우트명 |
| **metadata_bp** | **integrated_bp** | 블루프린트명 |
| `/api/metadata/...` | `/api/integrated/...` | API 엔드포인트 |
| `metadata_batch.js` | `integrated_batch.js` | JS 파일명 |

### 3.2 제외 대상 (변경 불필요)

| 대상 | 사유 |
|------|------|
| `build/` 폴더 | 빌드 산출물, 재빌드 시 자동 반영 |
| `backup_*` 폴더 | 백업 데이터, 레거시 보호 |
| 의존성 패키지 | 외부 라이브러리, 수정 불가 |
| `start.bat`, `build_deploy.ps1` | 배포 실행 파일 (레거시 보호 🔴) |

### 3.3 API 호환성 유지

- 기존 API 엔드포인트 `/api/metadata/...` → **신규** `/api/integrated/...` 로 변경
- 기존 엔드포인트 유지 (리디렉트 또는 alias) — **Deprecated** 처리 후 2주 유예
- API 응답 JSON 키(`data`, `success`)는 변경 없음 → 프론트엔드 영향 최소화

### 3.4 폴더 구조 변경 (고위험)

**현재:**
```
processed_data/
└── batch/batch_YYYYMMDD_N/
    ├── tmeta/          # 통합 메타데이터
    │   └── employee_*.json
    ├── imeta/          # 개별 메타데이터
    │   └── eval_*.json
    └── word/           # 워드클라우드
```

**변경:**
```
processed_data/
└── batch/batch_YYYYMMDD_N/
    ├── tdata/          # 통합데이터 (renamed)
    │   └── employee_*.json
    ├── idata/          # 개별데이터 (renamed)
    │   └── eval_*.json
    └── word/           # 워드클라우드
```

> **데이터 마이그레이션 필요**: 기존 `tmeta/`, `imeta/` 폴더 데이터를 `tdata/`, `idata/`로 이동 또는 심볼릭 링크 처리

## 4. 변경 파일 목록

### 4.1 단계 1 — 핵심 모듈 (해야 할 일)

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `src/models/metadata_manager.py` | 수정 | 클래스 `MetadataManager`, 메서드 `create_employee_metadata`, 변수 `metadata` | 클래스 `IntegratedDataManager`, 메서드 `create_employee_integrated_data`, 변수 `integrated_data` |
| `src/modules/metadata_analysis.py` | 수정 | 함수명 `calculate_consolidated_analysis` | 함수 유지 (기능 변경 없음), 주석만 변경 |
| `src/services/metadata_service.py` | 수정 | 파일명 `metadata_service.py`, 함수명 `generate_metadata`, `get_batch_metadata` | 파일명 `integrated_data_service.py` |
| `src/routes/metadata_routes.py` | 수정 | 블루프린트 `metadata_bp`, prefix `/api/metadata` | 블루프린트 `integrated_bp`, prefix `/api/integrated` |
| `src/services/batch_processor.py` | 수정 | `metadata` 변수, `tmeta` 경로, `imeta` 경로 | `integrated_data` 변수, `tdata` 경로, `idata` 경로 |
| `src/services/batch_service.py` | 수정 | `process_batch_metadata` 함수, `get_sample_metadata` | 함수명 변경 |
| `src/services/batch_events.py` | 수정 | `tmeta/` 경로 상수 | `tdata/` 경로 |
| `src/services/perspective_service.py` | 수정 | `metadata` 변수, `META` 상수명 | `integrated_data`, `ABSENT` 상수 (기능 무관) |
| `src/services/batch_manager.py` | 수정 | `tmeta` 경로 참조 | `tdata` 경로 |
| `src/routes/batch_routes.py` | 수정 | `get_sample_metadata` 호출 | `get_sample_integrated_data` 호출 |
| `src/routes/perspective_routes.py` | 수정 | `metadata` 변수 | `integrated_data` |
| `src/routes/ui_routes.py` | 수정 | `metadata` 템플릿 변수 | `integrated_data` 템플릿 변수 |
| `web/app.py` | 수정 | `metadata_bp` 블루프린트 등록 | `integrated_bp` 등록 |

### 4.2 단계 2 — 템플릿/JS (해야 할 일)

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `web/templates/wordcloud.html` | 수정 | `metadata` JS 객체, `metadata` 템플릿 변수, UI "메타데이터" 레이블 | `integratedData` JS 객체, UI "통합데이터" 레이블 |
| `web/templates/metadata.html` | 수정 | 파일명 `metadata.html`, UI "메타데이터" | 파일명 `integrated_data.html` |
| `web/templates/metadata_batch.html` | 수정 | 파일명 `metadata_batch.html`, UI 레이블 | 파일명 `integrated_batch.html` |
| `web/static/js/metadata_batch.js` | 수정 | 파일명 `metadata_batch.js`, 함수/변수명 | 파일명 `integrated_batch.js` |
| `web/templates/wordcloud_debug.html` | 수정 | `metadata` 디버그 표시 | `integrated_data` |
| `web/templates/base.html` | 수정 | Nav 메뉴 "메타데이터" | "통합데이터" |
| `web/templates/batch_monitor.html` | 수정 | `tmeta` 경로 표시 | `tdata` 경로 |
| `web/templates/admin_batch_management.html` | 변경 없음 | 이미 "통합데이터" 사용 | 유지 |
| `web/templates/mockup/mockup_metadata_batch.html` | 수정 | 파일명/내용 mockup | mockup 업데이트 |

### 4.3 단계 3 — 문서 (해야 할 일)

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `doc/metadata_structure.md` | 수정 | 제목/본문 "메타데이터 구조" | "통합데이터 구조" |
| `doc/metadata_modularization_plan.md` | 수정 | 전체 문서 | 용어 전면 변경 |
| `doc/metadata_modularization_checklist.md` | 수정 | 체크리스트 항목 | 용어 변경 |
| `doc/metadata_visualization.html` | 수정 | 시각화 제목/설명 | 용어 변경 |
| `doc/data_flow_diagram.html` | 수정 | "메타데이터" 노드 레이블 | "통합데이터" |
| `doc/web_system_modification_checklist.md` | 수정 | 체크리스트 항목 | 용어 변경 |
| `doc/web_system_improvement_analysis.md` | 수정 | 경로 설명 | 용어 변경 |
| `doc/implementation_plan.md` | 수정 | 상세 기능 설명 전체 | 용어 전면 변경 |
| `doc/development_checklist.md` | 수정 | 체크리스트 | 용어 변경 |
| `doc/project_structure_improvement_plan.md` | 수정 | 용 | 용어 변경 |

### 4.4 단계 4 — 데이터 마이그레이션 (해야 할 일)

| 항목 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| 폴더 `tmeta/` → `tdata/` | 마이그레이션 | 배치 산출물 폴더명 | rename + 마이그레이션 스크립트 |
| 폴더 `imeta/` → `idata/` | 마이그레이션 | 개별 평가 저장 폴더명 | rename + 마이그레이션 스크립트 |

### 4.5 단계 5 — 계획서 문서 (해야 할 일)

| 파일 | 변경 유형 | 작업 |
|------|-----------|------|
| `plans/2026/_index.md` | 수정 | 인덱스 내 "메타데이터" 언급 4건 → "통합데이터" |
| 기존 계획서 40+개 | **변경 없음** | 과거 계획서는 역사적 문서로 보존 (용어 변경 불필요) |
| `plans/_datasets/kote_finetune/` | **변경 없음** | 데이터셋 문서는 독립 범주 |

## 5. 영향도 분석

### 5.1 기능 영향

| 영역 | 영향도 | 설명 |
|------|--------|------|
| 메타데이터 생성 API (`/api/metadata/generate`) | 🔴 높음 | 엔드포인트 경로 변경, 호출부 전면 수정 필요 |
| 메타데이터 배치 처리 | 🔴 높음 | `tmeta`/`imeta` 경로 변경으로 기존 배치 접근 불가 |
| 메타데이터 조회/표시 | 🟡 중간 | 템플릿 변수명 변경, JS 함수명 변경 |
| 워드클라우드 생성 | 🟢 낮음 | 일부 변수명만 참조, 로직 변경 없음 |
| 그룹 분석 (perspective) | 🟢 낮음 | `metadata` 변수명 변경만 영향 |
| 기존 배치 결과 조회 | 🔴 높음 | `tmeta`→`tdata` 마이그레이션 필요 (역호환) |

### 5.2 데이터 영향

| 항목 | 설명 |
|------|------|
| 기존 배치 산출물 | `processed_data/batch/batch_*/tmeta/` → `tdata/` rename 필요 |
| 기존 단일 처리 | `processed_data/YYYYMM/single/employee_*.json` — 내부 필드는 변경 없음 |
| SQLite DB | DB 내 테이블·컬럼에 `metadata` 참조 없음 → 영향 없음 |

### 5.3 프론트엔드 영향

| 항목 | 설명 |
|------|------|
| 좌측 Nav | "메타데이터 생성" → "통합데이터 생성" |
| 페이지 URL | `/metadata` → `/integrated` |
| API 호출 | 모든 `/api/metadata/*` → `/api/integrated/*` |
| JS 전역 변수 | `metadata` → `integratedData` |
| HTML 템플릿 | `{{ metadata }}` → `{{ integrated_data }}` |

## 6. 테스트/검증 계획

### 6.1 단위 테스트

| 테스트 항목 | 검증 내용 | 통과 기준 |
|------------|-----------|-----------|
| `IntegratedDataManager` 생성 | 새 클래스명으로 인스턴스 생성 가능 | ✅ 기존 기능과 동일 |
| 통합데이터 생성 | `create_employee_integrated_data()` 호출 | ✅ 분석 결과 정상 포함 |
| 통합데이터 저장 | `save_employee_integrated_data()` | ✅ `tdata/` 경로에 저장 확인 |
| 개별데이터 저장 | `save_individual_integrated_data()` | ✅ `idata/` 경로에 저장 확인 |
| API 엔드포인트 | `/api/integrated/generate` POST | ✅ 200 응답 |

### 6.2 통합 테스트

| 테스트 항목 | 시나리오 |
|------------|----------|
| 배치 처리 완료 | CSV 업로드 → 전처리 → 통합데이터 생성 → 산출물 폴더 확인 (`tdata/`, `idata/`) |
| 기존 배치 호환 | 이전 `tmeta/` 데이터 → 신규 코드에서 조회 (마이그레이션 후) |
| 단일 처리 완료 | 단일 평가 → 통합데이터 생성 → 조회 |
| UI 표시 | 통합데이터 상세 페이지 → 모든 분석 결과 정상 표시 |

### 6.3 마이그레이션 검증

| 항목 | 검증 방법 |
|------|-----------|
| `tmeta`→`tdata` 이전 | 기존 배치 수만큼 폴더 rename 확인 |
| `imeta`→`idata` 이전 | 내부 파일명 변경 없이 폴더명만 변경 확인 |
| 역호환성 | `tmeta` 경로 직접 접근 코드 잔여 여부 grep 검증 |

## 7. 리스크 및 제약

### 7.1 리스크 매트릭스

| 리스크 | 확률 | 영향 | 대응 방안 |
|--------|------|------|-----------|
| 기존 배치 데이터 접근 불가 (마이그레이션 누락) | 중 | 🔴 | 마이그레이션 스크립트 사전 작성 및 자동화 |
| 프론트엔드 변수명 불일치로 렌더링 오류 | 중 | 🔴 | Find All References / grep으로 전수 검증 |
| API 경로 변경으로 외부 연동 깨짐 | 낮음 | 🟡 | 기존 경로 임시 유지 (Deprecated 헤더) |
| 빌드/배포 스크립트 영향 | 낮음 | 🟡 | 배포 파일은 변경 대상 제외 (레거시 보호) |
| 지침 파일(`.clinerules`) 참조 누락 | 낮음 | 🟡 | grep으로 전수 검증 |

### 7.2 제약 사항

1. **레거시 보호**: `start.bat`, `build_deploy.ps1`, `build/` 폴더 변경 불가
2. **API 역호환**: 기존 `/api/metadata/*` 엔드포인트는 2주 유예 후 제거
3. **계획서 보존**: 과거 계획서(`plans/2026/*`)는 역사적 정확성을 위해 용어 변경하지 않음
4. **동시 작업**: 용어 변경 중 다른 작업과의 충돌 방지 (PR 단위 격리)

### 7.3 규모 추정

| 단계 | 파일 수 | 예상 공수 | 실행 전략 |
|------|---------|-----------|-----------|
| 1단계: 핵심 모듈 | ~20 | 4~6시간 | Find/Replace + 수동 검증 |
| 2단계: 템플릿/JS | ~10 | 3~4시간 | 템플릿 변수 + JS 변수 전수 변경 |
| 3단계: 문서 | ~11 | 1~2시간 | 용어 일괄 변경 |
| 4단계: 마이그레이션 스크립트 | ~2 | 1~2시간 | 폴더 rename + 역호환 확인 |
| **합계** | **~43 ファイル** | **9~14시간** | |

## 8. 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | 용어 변경 범위에 **폴더명(tmeta/tmeta→tdata/idata)** 이 포함되는가? | Y | — |
| 1.2 | 용어 변경 범위에 **API 엔드포인트(/api/metadata→/api/integrated)** 가 포함되는가? | Y (역호환 유지) | — |
| 1.3 | 용어 변경 범위에 **내부 변수명(metadata→integrated_data)** 이 포함되는가? | Y | — |
| 1.4 | 용어 변경 범위에 **클래스명(MetadataManager→IntegratedDataManager)** 이 포함되는가? | Y | — |
| 1.5 | 용어 변경 범위에 **과거 계획서 문서**가 포함되는가? | N | — |
| 1.6 | 용어 변경 범위에 **UI 사용자 노출 레이블("메타데이터" 텍스트)** 이 포함되는가? | Y ("통합데이터"로) | — |
| 1.7 | 기존 `/api/metadata/*` 엔드포인트를 얼마나 유지할 것인가? | 전환 후 즉시 제거 / 2주 유예 | — |
| 1.8 | `build/` 폴더의 복사본도 변경해야 하는가? | N (재빌드 시 자동 반영) | — |
