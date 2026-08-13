# 제출용 저장/매트릭스 결과 이미지 조회 갤러리 기획서

- **작업명**: deploy-image-gallery
- **작성일시**: 2026-06-04
- **작업 유형**: 기능 추가 (프론트엔드 + 백엔드 API)
- **상태**: PND (Pending)

---

## 1. 개요 (Background)

현재 `그룹분석(perspective_test.html)` 화면에서 **매트릭스 생성** 및 **제출용 저장** 기능을 통해 직원별 워드클라우드 이미지(PNG)를 생성·저장할 수 있다.

- 매트릭스 생성: 셀 단위 워드클라우드를 즉시 화면에 표시하지만, **새로고침 후 재조회 불가**
- 제출용 저장(`save_to_deploy`): `outputs/배포/통합|긍정|부정/` 디렉토리에 파일을 저장하고 경로만 반환하지만, **이를 조회할 수 있는 별도 화면이 없음**

따라서 사용자가 이전에 생성·저장한 이미지를 다시 확인하거나 다운로드할 수 있는 **히스토리(갤러리) 조회 화면**이 필요하다.

---

## 2. 목표 (Goals)

1. **제출용 저장(`save_to_deploy`) 및 매트릭스 생성 결과 이미지의 영속적 조회 화면 제공**
2. **직원별·배치별·생성일자별 필터링 및 검색 가능**
3. **이미지 미리보기, 상세 정보 확인, 다운로드 기능 제공**
4. **기존 저장 플로우를 최소한으로 변경하면서 인덱싱 적용**

---

## 3. 범위 (Scope)

### 3.1 In-Scope

- `save_to_deploy()` 실행 시 저장된 결과의 **메타데이터 인덱싱**
- 저장 결과 목록 조회 API
- 저장 결과 상세(이미지 미리보기 + 메타정보) API
- 갤러리 UI 페이지 (`/deploy-gallery`)
- 기존 내비게이션(`base.html`)에 메뉴 추가

### 3.2 Out-of-Scope (현재 단계)

- 매트릭스 생성 결과의 **실시간 자동 인덱싱** (매트릭스 생성 결과는 메모리/화면 표시 후 소멸하므로, 별도 "저장" 동작이 필요함. 본 기능은 제출용 저장 중심)
- 삭제 기능 (Phase 2에서 검토)
- 데이터베이스 도입 (기존 파일 기반 아키텍처 유지)

---

## 4. 현재 저장 구조 분석

### 4.1 저장 경로

```
PROJECT_ROOT/outputs/배포/
  ├── 통합/{filename}.png
  ├── 긍정/{filename}.png
  └── 부정/{filename}.png
```

- `filename` 형식: `{deploy_name}_{label_suffix}.png`
- `deploy_name`: 직원ID (또는 관리자 인증 시 실명_사번)
- `label_suffix`: `통합` / `{row_value}_개별` 등

### 4.2 현재 문제점

- 파일은 저장되지만 **인덱스가 없어** 어떤 직원/어떤 조건/언제 저장되었는지 파일명 외에는 알 수 없음
- `save_to_deploy()` 반환값은 API 응답에만 존재하고 **영속화되지 않음**
- Audit 로그(`log_action`)에는 기록되지만, **사용자 조회용이 아님**

---

## 5. 기능 요구사항 (Functional Requirements)

### FR-01: 저장 결과 자동 인덱싱

`save_to_deploy()` 성공 시 `outputs/배포/` 아래 `deploy_manifest.json` 파일에 다음 정보를 추가 기록한다.

```json
{
  "entries": [
    {
      "id": "uuid-v4",
      "employee_id": "EMP001",
      "deploy_name": "홍길동_EMP001",
      "timestamp": "20260604_143052",
      "output_mode": "real",
      "row_field": "evaluation_date__year",
      "analysis_type": "nlp",
      "options_summary": {
        "wordcloud_pos": ["Noun"],
        "background_color": "white",
        "max_words": 100
      },
      "images": {
        "combined": "/outputs/배포/통합/홍길동_EMP001_통합.png",
        "positive": "/outputs/배포/긍정/홍길동_EMP001_긍정.png",
        "negative": "/outputs/배포/부정/홍길동_EMP001_부정.png"
      },
      "row_results": { ... }
    }
  ]
}
```

- 기존 반환 구조와의 호환성을 위해 `save_to_deploy()` 함수 내에서 병행 기록
- 파일 I/O는 원자적(atomic)으로 처리 (임시 파일 → rename)

### FR-02: 목록 조회 API

**Endpoint**: `GET /api/perspective/deploy-gallery/list`

**Query Parameters**:
- `employee_id` (optional): 특정 직원 필터
- `output_mode` (optional): `real` | `pseudonym`
- `date_from`, `date_to` (optional): YYYYMMDD 형식
- `page` (optional, default 1)
- `per_page` (optional, default 20, max 100)

**Response**:

```json
{
  "success": true,
  "total": 150,
  "page": 1,
  "per_page": 20,
  "entries": [
    {
      "id": "uuid",
      "employee_id": "EMP001",
      "deploy_name": "홍길동_EMP001",
      "timestamp": "20260604_143052",
      "output_mode": "real",
      "image_count": 3,
      "thumbnail_url": "/outputs/배포/통합/..."
    }
  ]
}
```

**접근 제어**:
- 비관리자: `output_mode=real` 인 데이터는 **목록에서 제외** (마스킹 없이 완전 제외)
- 관리자: 전체 데이터 조회 가능

### FR-03: 상세 조회 API

**Endpoint**: `GET /api/perspective/deploy-gallery/detail/<entry_id>`

**Response**: 해당 entry의 전체 메타데이터 + 이미지 URL 리스트

**접근 제어**:
- `output_mode=real` 인 데이터는 관리자 로그인 필요

### FR-04: 갤러리 UI 페이지

**경로**: `/deploy-gallery` (새 템플릿 `deploy_gallery.html`)

**화면 구성**:

```
┌─────────────────────────────────────────────────────┐
│  [내비게이션]                                         │
├──────────────┬──────────────────────────────────────┤
│              │  필터: [직원ID ▼] [날짜 From] [To]  │
│  필터 패널    │  [실명/가명 토글]  [검색]            │
│              │                                      │
│  - 직원 목록  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐      │
│  - 배치 목록  │  │썸네│ │썸네│ │썸네│ │썸네│      │
│  - 날짜 범위  │  │일1 │ │일2 │ │일3 │ │일4 │      │
│              │  └────┘ └────┘ └────┘ └────┘      │
│              │  ... (페이지네이션)                 │
│              │                                      │
└──────────────┴──────────────────────────────────────┘
```

**상세 모달(또는 아코디언)**:
- 클릭 시 전체 이미지 원본 표시
- 생성 옵션 정보 (형태소, 배경색, 크기 등)
- 다운로드 버튼

### FR-05: 내비게이션 통합

`base.html` 내비게이션에 갤러리 링크 추가:

```html
<a href="/deploy-gallery">📁 저장 갤러리</a>
```

위치: "📊 그룹분석" 메뉴 근처 또는 "관리자" 섹션 내.

---

## 6. 비기능 요구사항 (Non-Functional Requirements)

### NFR-01: 호환성
- 기존 `save_to_deploy()`의 반환값 및 동작은 **변경 없이 유지**
- 기존에 저장된 이미지는 인덱스에 없으므로 **갤러리에 표시되지 않음** (역호환성 문제 없음)

### NFR-02: 성능
- `deploy_manifest.json` 파일 크기가 10MB 이상 예상될 경우, **역순 인덱싱** 또는 **페이지 단위 로딩** 적용
- 현재 단계에서는 파일 전체 로드 후 메모리 필터링으로 충분 (파일 크기 임계점 도달 시 DB 고려)

### NFR-03: 보안
- `real` 모드 저장 결과는 관리자 인증(`session.get('admin_logged_in')`) 없이 조회 불가
- 이미지 자체는 `/outputs/배포/...` 경로로 정적 제공되므로, **URL 노출 시 접근 가능** (현재와 동일)
- ⚠️ 이 갤러리 기능으로 인해 URL 패턴 노출 가능성이 높아짐. Phase 2 이후 `/outputs/배포` 정적 라우트에 관리자 인증 체크 추가를 검토할 것

---

## 7. 설계 (Design)

### 7.1 데이터 인덱싱 설계

**파일 위치**: `OUTPUTS_DIR_PATH/deploy_manifest.json`

**구조**:

```json
{
  "version": "1.0",
  "last_updated": "2026-06-04T14:30:52",
  "entries": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "employee_id": "EMP001",
      "deploy_name": "홍길동_EMP001",
      "timestamp": "20260604_143052",
      "output_mode": "real",
      "row_field": "evaluation_date__year",
      "row_values": ["2023", "2024"],
      "row_combine_all": false,
      "analysis_type": "nlp",
      "options": {
        "wordcloud_pos": ["Noun"],
        "background_color": "white",
        "width": 800,
        "height": 600,
        "max_words": 100,
        "apply_emotion_colors": true,
        "remove_profanity": false
      },
      "images": {
        "combined": "/outputs/배포/통합/홍길동_EMP001_2024_개별.png",
        "positive": "/outputs/배포/긍정/홍길동_EMP001_2024_개별.png",
        "negative": "/outputs/배포/부정/홍길동_EMP001_2024_개별.png"
      },
      "row_results": {
        "2024": { "combined": "...", "positive": "...", "negative": "..." }
      }
      // row_results: 행 값(연도 등)별 이미지 URL만 저장. combined_sentences 등 문장 필드는 포함하지 않음
    }
  ]
}
```

**쓰기 전략**:
1. 임시 파일에 기존 JSON 로드 + 새 entry append
2. `os.replace()`로 원자적 교체
3. Flask `threaded=True` 환경에서 동시 쓰기 가능성이 있으므로 **Phase 1부터 `filelock` 적용** (lock 파일명: `deploy_manifest.lock`)

**manifest 부재/손상 시 동작**:
- 파일이 없으면 신규 생성(`{"version": "1.0", "entries": []}`)
- JSON 파싱 오류 시 API는 빈 목록(`"entries": []`, `"total": 0`)을 반환하고 서버 로그에 경고 기록 (500 에러 발생시키지 않음)
- 쓰기 시 파싱 오류가 감지되면 기존 파일을 `deploy_manifest.json.bak`으로 백업 후 신규 생성

### 7.2 API 설계

#### `GET /api/perspective/deploy-gallery/list`

```python
@perspective_bp.route('/deploy-gallery/list', methods=['GET'])
def api_deploy_gallery_list():
    # query params 파싱
    # manifest 로드
    # 필터링 (employee_id, date, output_mode)
    # 권한 체크: real 데이터 마스킹
    # 페이지네이션 적용
    # JSON 반환
```

#### `GET /api/perspective/deploy-gallery/detail/<entry_id>`

```python
@perspective_bp.route('/deploy-gallery/detail/<entry_id>', methods=['GET'])
def api_deploy_gallery_detail(entry_id):
    # manifest에서 entry 검색
    # 권한 체크
    # 상세 반환
```

### 7.3 UI 설계

**템플릿**: `web/templates/deploy_gallery.html`

**주요 컴포넌트**:
- **FilterBar**: 직원ID 입력, 날짜 범위, output_mode 라디오, 검색 버튼
- **GalleryGrid**: 카드 형태 그리드. 카드 = 썸네일 + 직원명 + 저장일 + 이미지 수
- **DetailModal**: 클릭 시 오버레이. 원본 이미지 + 옵션 정보 + 다운로드 링크
- **Pagination**: 페이지 번호 버튼

**스타일**: 기존 `base.html`의 `.cards-container`, `.option-card` 스타일 재활용

---

## 8. 구현 단계 (Implementation Steps)

### Phase 1: 백엔드 인덱싱 및 API (1일)

1. **`src/services/perspective_service.py`**
   - `_append_to_deploy_manifest(result, options)` 헬퍼 함수 추가
   - `save_to_deploy()` 마지막에 manifest 기록 호출 추가
   - `requirements.txt`에 `filelock` 패키지 추가

2. **`src/routes/perspective_routes.py`**
   - `api_deploy_gallery_list()` 구현
   - `api_deploy_gallery_detail()` 구현

3. **테스트**
   - 제출용 저장 1회 수행 후 `deploy_manifest.json` 생성 확인
   - 목록/상세 API 응답 확인

### Phase 2: 프론트엔드 UI (1일)

1. **`web/templates/deploy_gallery.html`**
   - 필터바, 그리드, 모달 HTML/CSS 작성
   - JavaScript: API 호출, 렌더링, 페이지네이션

2. **`web/templates/base.html`**
   - 내비게이션 메뉴 추가

3. **`src/routes/ui_routes.py`**
   - `/deploy-gallery` 라우트 추가 (템플릿 렌더링)

4. **통합 테스트**
   - E2E: 저장 → 갤러리 조회 → 상세 보기 → 다운로드

### Phase 3: 정리 및 문서화 (0.5일)

1. 코드 리뷰 및 정리
2. 계획서 상태 업데이트 (`DN` 복사본 생성)
3. 완료 보고서 작성

---

## 9. 테스트 계획

| 테스트 ID | 내용 | 방법 | 기대 결과 |
|-----------|------|------|-----------|
| T-01 | manifest 기록 | 제출용 저장 API 호출 | `deploy_manifest.json`에 entry 추가됨 |
| T-02 | 목록 조회 필터 | `employee_id` 쿼리 파라미터 전달 | 필터링된 결과만 반환 |
| T-03 | 권한 체크 | 비관리자로 `real` 데이터 조회 | `real` 결과는 제외되거나 가명 표시 |
| T-04 | UI 렌더링 | 갤러리 페이지 접속 | 저장된 이미지 카드 그리드 표시 |
| T-05 | 상세 모달 | 카드 클릭 | 원본 이미지 + 메타정보 표시 |
| T-06 | 다운로드 | 다운로드 버튼 클릭 | PNG 파일 다운로드 시작 |

---

## 10. 리스크 및 고려사항

| 리스크 | 영향도 | 대응책 |
|--------|--------|--------|
| manifest 파일이 커질 경우 성능 저하 | 중 | 10MB 이상 시 파일 분할(sharding) 또는 SQLite 가벼운 도입 검토 |
| 병렬 저장 시 manifest 손상 | 낮음 | 임시 파일 + atomic rename. 필요 시 `filelock` 도입 |
| 기존 저장 이미지 미표시 | 낮음 | 본 기능은 신규 저장부터 적용. 기존 이미지는 별도 마이그레이션 스크립트로 선택적 인덱싱 가능 |
| 이미지 URL 직접 접근 보안 | 낮음 | 현재 시스템과 동일한 수준. 필요 시 `/outputs/배포` 라우트에 관리자 체크 추가 검토 |

---

## 11. 관련 파일

| 파일 | 역할 |
|------|------|
| `src/services/perspective_service.py` | `save_to_deploy()`, manifest 기록 로직 |
| `src/routes/perspective_routes.py` | 갤러리 API 엔드포인트 |
| `src/routes/ui_routes.py` | `/deploy-gallery` 페이지 라우트 |
| `web/templates/deploy_gallery.html` | 갤러리 UI 템플릿 (신규) |
| `web/templates/base.html` | 내비게이션 메뉴 추가 |
| `web/app.py` | `/outputs/배포/<path>` 정적 라우트 (구현 전 존재 여부 확인 필요) |
| `requirements.txt` | `filelock` 패키지 추가 필요 시 수정 |

---

## 12. 완료 기준 (Definition of Done)

- [ ] 제출용 저장 시 `deploy_manifest.json`에 메타데이터가 기록된다.
- [ ] `/api/perspective/deploy-gallery/list` API가 정상 응답한다.
- [ ] `/api/perspective/deploy-gallery/detail/<id>` API가 정상 응답한다.
- [ ] `/deploy-gallery` 페이지에서 저장된 이미지 목록을 조회할 수 있다.
- [ ] 이미지 상세 모달(또는 페이지)에서 원본 이미지를 확인하고 다운로드할 수 있다.
- [ ] `base.html` 내비게이션에 갤러리 메뉴가 추가된다.
- [ ] 비관리자는 `real` 모드 저장 결과를 볼 수 없다.

---

*본 계획서는 `.clinerules/core/00-core/03.plan-mode.md` 지침에 따라 작성되었다.*
*실제 코드 변경은 사용자가 "수행"을 명시적으로 요청할 때까지 대기한다.*
