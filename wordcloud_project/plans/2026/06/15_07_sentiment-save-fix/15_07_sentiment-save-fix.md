# 워드클라우드 감정 분리 모드 저장 누락 수정

> 상태: Done | 작성일: 2026-06-15 | 완료일: 2026-06-15
> 작업 유형: 버그 수정 (기능 문제 분석/디버깅)

## 문제

워드클라우드 페이지에서 **감정 분리 모드**(`sentimentMode`: 통합/긍정부정 분리/통합+분리)만 `localStorage`에 저장되지 않아 페이지 새로고침 시 항상 "통합"으로 리셋됨.

## 원인

`wordcloud.html`의 3군데 누락:

| 위치 | 문제 |
|------|------|
| `saveOptions()` | `sentimentMode` 값 수집 안 함 |
| `loadOptions()` | 저장된 `sentimentMode` 복원 코드 없음 |
| 이벤트 리스너 | `sentimentMode` 라디오 버튼에 `change` → `saveOptions()` 연결 안 됨 |

## 수정 사항

**파일**: `web/templates/wordcloud.html`

1. **`saveOptions()`** — `sentimentMode` 필드 추가: 선택된 라디오값 읽어 저장, 미선택 시 기본값 `'combined'`
2. **`loadOptions()`** — 저장된 `sentimentMode`로 라디오 버튼 체크 복원
3. **이벤트 리스너** — `sentimentMode` 라디오 버튼에 `change` → `saveOptions()` 연결

## 영향도

- 다른 옵션(형태소, 배경색, 크기 등) 저장 로직에 영향 없음
- `localStorage` 키 `wordcloudOptions`만 사용 (기존 키 그대로)
- 다른 페이지에 영향 없음

## 결과

- 감정 분리 모드 변경 시 자동 저장
- 페이지 새로고침 후에도 선택한 모드 유지
- 상태: ✅ 완료
