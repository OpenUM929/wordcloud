# 0608_01_gallery-search-delete

> 상태: DN(코드 적용 확인, 2026-06-18) | 작성일: 2026-06-08

## Context

deploy-gallery 페이지(`/deploy-gallery`)에는 두 가지 기능이 부재하다:
1. 날짜 선택이 텍스트 입력(YYYYMMDD)으로만 가능해 UX가 불편하다.
2. 저장된 갤러리 항목을 삭제하는 기능이 전혀 없다.

이미지는 **날짜 → 직원 → 소스(deploy/matrix)** 계층으로 생성되므로, 검색과 삭제도 이 계층 구조를 기준으로 설계한다.

---

## 데이터 계층 (이미지 생성 방식 기준)

```
날짜 (YYYYMMDD)          ← 대분류
  └─ 직원 (employee_id)  ← 중분류
       └─ 개별 항목       ← 소분류 (timestamp + source)
```

---

## 구현 내역

### Backend (perspective_routes.py)

| 변경 | 설명 |
|------|------|
| `GET /deploy-gallery/dates` 신규 | manifest 내 고유 날짜(YYYYMMDD) 목록 반환 |
| `DELETE /deploy-gallery/entries` 신규 | entry_ids 배열로 항목 삭제, 이미지 파일 best-effort 삭제, 감사 로그 기록, 관리자 전용 |
| `GET /deploy-gallery/list` 수정 | `dates` 쿼리 파라미터 추가 (콤마 구분 YYYYMMDD, 기존 date_from/date_to 하위 호환 유지) |

### Frontend (deploy_gallery.html)

| 변경 | 설명 |
|------|------|
| CSS 추가 | 날짜 칩, 삭제 모드 카드 스타일, 날짜 그룹 헤더, 하단 바, 확인 다이얼로그 |
| 필터 바 HTML 교체 | 텍스트 날짜 입력 → `#dateChipsContainer` 동적 칩, "삭제 모드" 버튼 추가 |
| HTML 추가 | `#deleteBottomBar`, `#deleteConfirmDialog` |
| JS 신규 함수 | `loadAvailableDates`, `renderDateChips`, `toggleDateChip`, `renderGalleryGrid`, `buildGalleryCard`, `toggleDeleteMode`, `toggleCardSelect`, `toggleGroupSelect`, `syncGroupCheckboxes`, `updateDeleteCount`, `openDeleteConfirm`, `closeDeleteConfirm`, `executeDelete`, `confirmDeleteByDate`, `_executeDeleteByIds`, `_executeDeleteSelected` |
| 날짜 전체 삭제 | 날짜 그룹 헤더 "날짜 삭제" 버튼 → `confirmDeleteByDate(dateKey)` → 다이얼로그(배포용/매트릭스 개수 표시) → `_executeDeleteByIds(ids)` |
| `loadGallery` 수정 | dates 칩 파라미터 사용, `galleryEntries` 저장, `renderGalleryGrid` 호출 |
| 다운로드 버튼 수정 | `url.split('?')[0]` + `download="${filename}"` (쿼리스트링 제거) |

---

## 검토 노트 반영 (260608.txt)

- **다운로드 URL**: 기존 `<a href="${url}" download>` 버튼이 `?v=타임스탬프` 포함 URL을 사용해 파일명 오류 발생 → `split('?')[0]`으로 정리하고 명시적 `download="${filename}"` 적용
- **변수 혼입 방지**: 신규 상태 변수는 `selectedDateChips`, `deleteMode`, `selectedEntryIds`, `galleryEntries` 4개로 제한

---

## 검증 방법

1. 페이지 로드 후 날짜 칩 렌더링 확인 ("전체" + MM/DD 형태)
2. 복수 날짜 칩 선택 → 해당 날짜 항목만 표시
3. "전체" 클릭 → 전체 항목 표시
4. 날짜 그룹 헤더 확인
5. "삭제 모드" → 체크박스 출현, 하단 바 등장
6. 카드 클릭 → 빨간 테두리, 하단 바 카운트 갱신
7. 그룹 체크박스 → 날짜 전체 선택, indeterminate 상태
8. "선택 삭제" → 확인 다이얼로그 → "취소" → 항목 유지
9. 삭제 실행 → `deleted_count` 응답 확인 → 갤러리 갱신
10. 파일 삭제 여부 확인
11. 비관리자 DELETE API → 403
12. 모든 항목 삭제 후 해당 날짜 칩 사라짐 확인
13. 다운로드 파일명이 `파일명.png` 형태인지 확인 (쿼리스트링 없음)
