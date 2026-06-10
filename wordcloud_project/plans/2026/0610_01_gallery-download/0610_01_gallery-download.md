# 저장 갤러리 이미지 다운로드 기능

> 상태: PND | 작성일: 2026-06-10

## 1. 개요

저장 갤러리(`deploy_gallery.html`)에서 이미지를 다운로드하는 기능을 추가한다.

- **기능 1**: 날짜/연도/배치 명칭 칩으로 필터링 후 선택된 항목들을 ZIP으로 다운로드
- **기능 2**: 개별 이미지 다운로드 (모달 상세보기에서)

## 2. 요구사항

### 2.1 필터 기반 일괄 다운로드
- 날짜 칩, 배치 명칭 칩, 연도 칩, 소스(배포용/매트릭스) 칩으로 필터링
- 필터링된 결과 중 원하는 항목을 체크박스로 선택
- 선택된 항목들을 ZIP으로 압축하여 다운로드
- ZIP 파일명은 **선택된 칩들의 이름을 합쳐서** 생성
- 예: `배포용_2024상반기_외_1건_2024_20250610.zip`

### 2.2 개별 이미지 다운로드
- 모달 상세보기(Detail Modal)에서 각 이미지에 마우스 오버 시 "↓ 저장" 버튼 표시
- 클릭 시 해당 이미지 단독 다운로드

### 2.3 ZIP 내부 구조 (2가지 모드)

| 모드 | 구조 | 설명 |
|------|------|------|
| **종류별 저장** | `combined/` `positive/` `negative/` | 감정 종류별 폴더 생성 |
| **통합 저장** | (평탄) | `직원ID_연도_종류.png` 형태로 루트에 저장 |

### 2.4 칩 상호배타 규칙

| 규칙 | 동작 |
|------|------|
| **소스** | 배포용/매트릭스 중 **단일 선택**만 가능 (라디오 방식) |
| **연도 ↔ 날짜** | 연도 선택 시 날짜 칩 **비활성화 + 해제** |
| **다운로드 ↔ 삭제 모드** | **상호 배타** — 하나만 켜질 수 있음 |

## 3. 영향도 분석

### 3.1 변경 대상 파일

| 파일 | 변경 유형 | 영향 범위 |
|------|-----------|-----------|
| `perspective_routes.py` | 수정 | 신규 API 엔드포인트 추가 |
| `deploy_gallery.html` | 수정 | UI 추가 (다운로드 모드, 패널, 하단바, 칩 필터) |

### 3.2 호출 관계
- **신규 API**: `POST /api/perspective/deploy-gallery/download`
  - 호출자: `deploy_gallery.html` (JavaScript `fetch`)
  - 응답: `application/zip` (Blob 다운로드)

### 3.3 롤백 계획
- `perspective_routes.py`: 추가된 함수/헬퍼 함수 삭제
- `deploy_gallery.html`: 추가된 HTML/CSS/JS 블록 삭제
- 백업: Git checkout 또는 수동 롤백

## 4. 구현 계획

### 4.1 백엔드 API

**엔드포인트**: `POST /api/perspective/deploy-gallery/download`

**Request Body**:
```json
{
  "entry_ids": ["id1", "id2"],
  "folder_mode": "by_type" | "flat"
}
```

**동작**:
1. `entry_ids`에 해당하는 갤러리 항목 조회 (manifest)
2. 각 항목의 `images` 및 `row_results`에서 이미지 URL 추출
3. URL → 실제 파일 경로 변환 (`_url_to_abs_path`)
4. 파일 존재 여부 확인
5. `folder_mode`에 따라 ZIP 내부 경로 생성:
   - `by_type`: `combined/직원ID_연도.png`
   - `flat`: `직원ID_연도_통합.png`
6. `tempfile`로 ZIP 생성 후 `send_file` 반환

**파일명 규칙**:
- 선택된 칩 이름을 `_`로 연결
- 2개 이상이면 `첫항목_외_N건` 형식
- 끝에 `_YYYYMMDD` 타임스탬프
- 특수문자는 `_`로 치환

### 4.2 프론트엔드 UI

#### 4.2.1 다운로드 모드 버튼
- 삭제 모드 버튼 옆에 추가
- `toggleDownloadMode()` 호출

#### 4.2.2 다운로드 모드 패널
- 삭제 모드 패널과 동일한 구조
- 소스/배치명/연도/날짜 칩
- 전체 선택 체크박스
- **저장 방식 라디오**: `종류별 저장` / `통합 저장`
- 선택 개수 표시

#### 4.2.3 다운로드 하단 바
- 고정 하단 바
- 선택 개수 표시
- "선택 다운로드" 버튼
- "취소" 버튼

#### 4.2.4 칩 상호배타 로직
```javascript
// 소스: 단일 선택
downloadFilterSource.clear();
downloadFilterSource.add(src);

// 연도 선택 시 날짜 비활성화
if (downloadFilterYear) {
  dateChip.disabled = true;
  dateChip.classList.add('disabled');
}

// 다운로드/삭제 모드 상호 배타
if (downloadMode) { deleteMode = false; }
if (deleteMode) { downloadMode = false; }
```

### 4.3 ZIP 다운로드 흐름

```javascript
async function executeDownload() {
  const ids = Array.from(selectedDownloadEntryIds);
  const folderMode = document.querySelector('input[name="folderMode"]:checked').value;
  const fileName = _buildDownloadFileName(); // 칩 이름 조합
  
  const res = await fetch('/api/perspective/deploy-gallery/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entry_ids: ids, folder_mode: folderMode })
  });
  
  const blob = await res.blob();
  // Blob → a[download] 트리거
}
```

## 5. 테스트 계획

### 5.1 API 테스트
- [ ] `entry_ids` 없이 요청 → 400 오류
- [ ] 존재하지 않는 `entry_ids` → 404 오류
- [ ] 유효한 `entry_ids` + `by_type` → ZIP 반환 (폴더 구조 확인)
- [ ] 유효한 `entry_ids` + `flat` → ZIP 반환 (평탄 구조 확인)
- [ ] 파일명 특수문자 처리 확인

### 5.2 UI 테스트
- [ ] 다운로드 모드 토글
- [ ] 삭제 모드와 상호 배타
- [ ] 소스 단일 선택 (배포용/매트릭스)
- [ ] 연도 선택 시 날짜 비활성화
- [ ] 전체 선택 / 그룹 선택 / 개별 선택
- [ ] ZIP 파일명 생성 (칩 이름 조합)
- [ ] 모달에서 개별 이미지 다운로드

### 5.3 통합 테스트
- [ ] 필터 → 선택 → 다운로드 → ZIP 파일 확인
- [ ] 대용량 (50개 이상 항목) ZIP 생성 테스트

## 6. 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-10 | §7 | 초안 작성 및 구현 완료 |
| 2026-06-10 | §8 | `_build_arc_name()` by_type suffix 제거, `toggleDeleteMode()` allDownloadEntries 초기화 추가 |

---

## 7. 구현 완료 내역 (2026-06-10)

> ⚠️ 본 계획서 작성 전, 구현이 선행 완료되었습니다. 아래는 실제 반영된 코드 내역입니다.

### 7.1 백엔드 구현

**변경 파일**: `src/routes/perspective_routes.py`

**추가된 엔드포인트**:
```python
@perspective_bp.route('/deploy-gallery/download', methods=['POST'])
def api_deploy_gallery_download():
    """갤러리 선택 항목 이미지 ZIP 다운로드."""
    data = request.get_json(silent=True) or {}
    entry_ids = data.get('entry_ids', [])
    folder_mode = data.get('folder_mode', 'flat')  # 'flat' | 'by_type'
    # ... (entry_ids 조회 → 이미지 수집 → ZIP 생성 → send_file)
```

**추가된 헬퍼 함수**:
- `_url_to_abs_path(url)`: URL/경로 문자열 → 실제 파일 절대 경로 변환
- `_build_arc_name(folder_mode, emp_id, year, img_type, abs_path)`: ZIP 내부 파일 경로 생성
  - `by_type`: `combined/직원ID_연도_통합.png`
  - `flat`: `직원ID_연도_통합.png`

**Python import 추가**:
- `import re` (파일명 특수문자 치환용)

### 7.2 프론트엔드 구현

**변경 파일**: `web/templates/deploy_gallery.html`

**추가된 CSS**:
- `#downloadModePanel`: 다운로드 모드 패널 (파란색 테마 `#f0f7ff`)
- `.download-chip`, `.download-chip--active`, `.download-chip--disabled`: 다운로드 칩 스타일
- `#downloadBottomBar`: 다운로드 하단 바 (고정, 어두운 배경)

**추가된 HTML**:
- 다운로드 모드 버튼: 삭제 모드 버튼 옆에 위치
- 다운로드 모드 패널: 소스/배치명/연도/날짜 칩 + 전체 선택 + 저장 방식 라디오 + 선택 다운로드 버튼
- 다운로드 하단 바: 선택 개수 + 취소/다운로드 버튼

**추가된 JavaScript**:

| 함수 | 설명 |
|------|------|
| `toggleDownloadMode()` | 다운로드 모드 토글 (삭제 모드와 상호 배타) |
| `toggleDownloadCardSelect(id, checked)` | 개별 카드 선택 |
| `toggleDownloadGroupSelect(pk, checked)` | 날짜 그룹 전체 선택 |
| `updateDownloadCount()` | 선택 개수 표시 및 버튼 활성화 |
| `_loadAllForDownload()` | 전체 데이터 로드 (9999개) |
| `_getDownloadFiltered()` | 칩 필터 적용 |
| `renderDownloadGrid()` | 필터링된 결과 그리드 렌더링 |
| `renderDownloadPanel()` | 칩 패널 렌더링 |
| `_renderDownloadYearAndDateChips()` | 연도/날짜 칩 동적 렌더링 |
| `toggleDownloadSelectAll(checked)` | 전체 선택/해제 |
| `_buildDownloadFileName()` | 선택된 칩 이름 조합으로 ZIP 파일명 생성 |
| `executeDownload()` | ZIP 다운로드 API 호출 + Blob 트리거 |

**칩 상호배타 로직 구현**:
- 소스 칩: `downloadFilterSource.clear(); downloadFilterSource.add(src);` (단일 선택)
- 연도 선택 시: `downloadFilterDates.clear();` + 날짜 칩 `disabled` + `download-chip--disabled` 클래스 추가
- 다운로드/삭제 모드: 토글 시 반대 모드 강제 종료

### 7.3 기존 코드 수정 사항

**삭제 모드와의 공존 처리**:
- `buildGalleryCard()`: `deleteMode || downloadMode` 조건으로 체크박스 표시
- `renderGalleryGrid()`: `deleteMode || downloadMode`로 `delete-mode-active` 클래스 토글
- `syncGroupCheckboxes()`: 현재 활성화된 모드의 선택 집합 사용
- `toggleDeleteMode()`: 다운로드 모드 켜져 있으면 끔
- `toggleDownloadMode()`: 삭제 모드 켜져 있으면 끔

### 7.4 테스트 결과

- [x] Python 문법 체크: `py_compile` 통과
- [x] Flask 앱 생성: 정상 실행
- [x] 엔드포인트 등록: `/api/perspective/deploy-gallery/download` 확인

### 7.5 미완료 테스트 항목

- [ ] 실제 이미지가 있는 환경에서 ZIP 다운로드 API 호출
- [ ] ZIP 내부 폴더 구조 확인 (by_type / flat)
- [ ] 대용량 (50개 이상) 항목 ZIP 생성 테스트
- [ ] 프론트엔드 브라우저에서 전체 흐름 테스트 (필터 → 선택 → 다운로드)

---

## 8. 검증 결과 및 수정 완료 항목 (2026-06-10)

> 코드 검증 및 API 런타임 테스트 결과. 전체 동작 정상. 아래 2항목 수정 완료.

### 8.1 수정 완료

| # | 위치 | 수정 내용 | 우선순위 |
|---|------|-----------|---------|
| 1 | `perspective_routes.py` — `_build_arc_name()` | `by_type` 모드에서 `_통합` suffix 제거 — `combined/직원ID_연도.png` 형태로 생성 | 낮음 |
| 2 | `deploy_gallery.html` — `toggleDeleteMode()` | 다운로드 모드 종료 시 `allDownloadEntries = []` 초기화 추가 | 낮음 |

### 8.2 수정 내역

**#1 — `_build_arc_name()` by_type suffix 제거**

```python
# by_type: combined/직원ID_연도.png (suffix 제거, 폴더명이 타입 표현)
if folder_mode == 'by_type':
    type_folder = {'combined': 'combined', 'positive': 'positive', 'negative': 'negative'}.get(img_type, 'other')
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', f"{emp_id}{'_' + year if year else ''}")
    return f"{type_folder}/{safe_name}.{ext}"
# flat: 직원ID_연도_통합.png (suffix 유지)
type_ko = {'combined': '통합', 'positive': '긍정', 'negative': '부정'}.get(img_type, img_type)
safe_name = re.sub(r'[\\/:*?"<>|]', '_', f"{emp_id}{'_' + year if year else ''}_{type_ko}")
return f"{safe_name}.{ext}"
```

**#2 — `toggleDeleteMode()` 내 `allDownloadEntries` 초기화 추가**

```javascript
// deploy_gallery.html — toggleDeleteMode() download mode 종료 블록
if (downloadMode) {
    downloadMode = false;
    allDownloadEntries = [];
    selectedDownloadEntryIds.clear();
    selectedDownloadBatchTitles.clear();
    // ... 기존 UI 초기화
}
```

### 8.3 검증 통과 항목 (변경 불필요)

- `entry_ids` 미전달 → 400, 존재하지 않는 ID → 404 동작 정상
- 소스 칩 단일 선택, 연도 선택 시 날짜 칩 비활성화 로직 정상
- 다운로드/삭제 모드 상호 배타 및 종료 시 `loadGallery(1)` 복원 정상
- `_buildDownloadFileName()` 칩 조합 + `a.download` 파일명 적용 정상
- 모달 개별 이미지 `↓ 저장` hover 다운로드 정상
- `send_file` `download_name`은 서버 기본값이나 JS `a.download` 우선 적용되어 파일명 의도대로 동작
