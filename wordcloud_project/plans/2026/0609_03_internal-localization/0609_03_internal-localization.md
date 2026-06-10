# 웹시스템 내부망 로컬화 계획서

> 상태: DN | 완료일: 2026-06-09

---

## 1. 개요

현재 웹시스템을 완전히 내부망(오프라인) 환경으로 이전하기 위해, 외부에서 참조하는 모든 정적 리소스와 AI 모델을 로컬에 저장하고 코드 경로를 전환한다.

---

## 2. 발견된 외부 참조 현황

| 구분 | 위치 | 외부 참조 내용 | 필수 여부 |
|------|------|----------------|-----------|
| 정적 리소스 (CDN) | `base.html` | Bootstrap 5.3.0, jQuery 3.6.0 (jsdelivr, code.jquery.com) | ✅ 필수 |
| | `wordcloud_preview.html` | D3.js v7, d3-cloud (jsdelivr) | ✅ 필수 |
| | `results.html`, `preprocess.html`, `sarcasm.html` | jQuery 3.6.0 (code.jquery.com) | ✅ 필수 |
| | `doc/*.html` | Mermaid 10.6.1 (jsdelivr) | ⚠️ 문서용 |
| AI 모델 (Hugging Face) | `translation_service.py` | `Helsinki-NLP/opus-mt-ko-en`, `opus-mt-en-ko`, `facebook/nllb-200-distilled-600M` | ✅ 필수 |
| | 그 외 분석 모듈 | `emotion_analysis`, `sarcasm_analysis`, `leadership_analysis` 등은 **로컬 모델 경로** 사용 | ✅ 이미 로컬 |
| Python 패키지 | 전체 프로젝트 | `torch`, `transformers`, `flask`, `kiwipiepy`, `konlpy`, `wordcloud`, `pandas` 등 100+ 패키지 | ✅ 필수 |
| 외부 API 호출 | Python/JS 전체 | **없음** — 모든 `fetch`/`requests`는 내부 `/api/...` 호출만 사용 | ✅ 이미 로컬 |
| 환경 설정 | `.env` | 외부 API 키/URL은 주석 처리, 미사용 | ✅ 이미 로컬 |

---

## 3. 로컬화 실행 단계

### Phase 1: 정적 리소스 (CDN) → 로컬 자체 보관

**목표**: 모든 HTML 템플릿에서 CDN URL을 로컬 정적 파일로 교체

**작업 목록**:
1. `wordcloud_project/web/static/vendor/` 폴더 생성
2. 아래 5개 라이브러리를 CDN에서 다운로드하여 해당 폴더에 저장
   - `bootstrap.min.css` (Bootstrap 5.3.0)
   - `bootstrap.bundle.min.js` (Bootstrap 5.3.0)
   - `jquery-3.6.0.min.js` (jQuery)
   - `d3.min.js` (D3 v7)
   - `d3.layout.cloud.min.js` (d3-cloud 1.2.7)
   - `mermaid.min.js` (Mermaid 10.6.1) — `doc/`용
3. 모든 HTML 템플릿의 `<link>` / `<script>` 경로를 `{{ url_for('static', filename='vendor/...') }}` 형식으로 변경
4. 영향 HTML 목록:
   - `web/templates/base.html`
   - `web/templates/wordcloud_preview.html`
   - `web/templates/results.html`
   - `web/templates/preprocess.html`
   - `web/templates/sarcasm.html`
   - `doc/metadata_visualization.html`
   - `doc/data_flow_diagram.html`

**예상 시간**: 2~3시간

---

### Phase 2: 번역 모듈 제거 (완료)

**목표**: 사용하지 않는 번역 모듈 완전 제거

**작업 목록**:
1. `translation_service.py` 파일 삭제
   - `Helsinki-NLP/opus-mt-ko-en`
   - `Helsinki-NLP/opus-mt-en-ko`
   - `facebook/nllb-200-distilled-600M`
2. `perspective_routes.py`에서 `back_translate` import 및 호출 로직 제거
3. `sentiment_test.html`에서 `back_translation` 결과 표시 제거
4. `model/translation/` 폴더 및 다운로드 스크립트 정리

**예상 시간**: 3~4시간 (모델 다운로드 1~2GB 포함)

---

### Phase 3: Python 패키지 → 내부망 설치용 패키지 준비

**목표**: 내부망에서 오프라인 pip 설치가 가능하도록 `.whl` 파일 모두 준비

**작업 목록**:
1. `requirements.txt` 생성 (현재 없음)
2. `pip download -r requirements.txt -d ./vendor_python_pkgs` 실행
3. 내부망 서버에서 `pip install --no-index --find-links ./vendor_python_pkgs -r requirements.txt`로 설치 가능하도록 가이드 작성

**핵심 주의**:
- `torch==2.6.0+cu124` — 내부 서버의 **CUDA 버전이 12.4**인지 반드시 확인 필요
- CUDA 버전이 다르면 CPU 버전(`torch`) 또는 해당 CUDA 버전으로 재다운로드
- `konlpy`는 내부 JDK 설치 필요
- `kiwipiepy-model`은 이미 pip 패키지로 포함됨

**예상 시간**: 1~2시간 (다운로드 시간 제외)

---

### Phase 4: 오프라인 차단 테스트 및 검증

**목표**: 외부 네트워크 차단 상태에서 모든 기능이 정상 동작하는지 검증

**작업 목록**:
1. `TRANSFORMERS_OFFLINE=1` 및 네트워크 차단 상태에서 Flask 앱 기동
2. 모든 페이지 정상 로드 확인 (CDN → 로컬 전환 검증)
3. 감정 분석, 워드클라우드 생성, 번역(백트랜슬레이션) 기능 테스트
4. `requests`, `urllib` 등의 외부 호출이 없음을 최종 grep 검증

**예상 시간**: 2~3시간

---

---

## 4. 루트 폴더 미사용 모델 정리

> **재학습 계획 없음** → 사용하지 않는 모델/학습 파일 전부 삭제

**정리 대상 및 조치**:

| 항목 | 위치 | 조치 | 사유 |
|------|------|------|------|
| Qwen3-8B 베이스 | `model/Qwen3-8B/` | 삭제 | 코드/설정 미사용 |
| Qwen3-8B 감정 모델 | `model/Qwen3-8B-Korean-Sentiment/` | 삭제 | 코드/설정 미사용 |
| KLUE RoBERTa-base | `model/KLUE RoBERTa/` | 삭제 | 재학습 없음 |
| KLUE RoBERTa-large | `model/KLUE RoBERTa-large/` | 삭제 | 재학습 없음 |
| 미사용 파인튜닝 모델 | `model/fine_tune/fine_tuned_kote_large_model/` | 삭제 | `use_fine_tuned: false` |
| 미사용 파인튜닝 모델 | `model/fine_tune/fine_tuned_model/` | 삭제 | 운영 미사용 |
| 학습 스크립트/데이터 | `model/fine_tune/` 내 `*.py`, `*.json`, `split/` 등 | 삭제 | 재학습 없음 |
| 중복 설정 파일 | `wordcloud_project/configs/*.json` | 삭제 | `wordcloud_project/src/configs/`와 중복 (실제 사용 경로) |

**예상 시간**: 30분~1시간

---

## 5. 리스크 및 주의사항

| 리스크 | 영향 | 대응 방안 |
|--------|------|-----------|
| **CUDA 버전 불일치** | `torch`가 GPU를 인식 못 하거나 실행 실패 | 내부 서버 CUDA 버전 확인 후 `torch` 버전 재매칭 |
| **Konlpy Java 의존성** | 내부 서버에 JDK 미설치 시 `konlpy` 실행 불가 | JDK 설치 확인, 또는 `kiwipiepy`만 사용하도록 전환 검토 |
| **번역 모델 용량** | 3개 모델 합계 1~2GB, 내부 전송 부담 | USB/내부 NAS 등으로 전송, 또는 번역 기능 비활성화 옵션 제공 |
| **정적 리소스 버전** | CDN 버전과 로컬 버전 불일치 시 UI 이상 | 다운로드 시 정확한 버전 문자열 확인 (bootstrap@5.3.0 등) |

---

## 5. 결정 대기 사항

아래 정보 확인 후 Phase 3~4 세부 계획을 수정할 수 있습니다.

1. **내부 서버의 CUDA 버전**은 몇 입니까? (예: 12.4, 11.8, CPU 전용 등)
2. **내부망에서 Python 패키지 설치 방식**은 어떻게 되나요? (내부 PyPI 미러 / 완전 오프라인 `.whl` 복사)
3. **내부 서버의 OS와 Python 버전**은 무엇인가요? (Windows/Linux, Python 3.10?)
4. **`doc/` 폴더의 Mermaid 다이어그램**도 내부에서 열람할 예정인가요?

---

## 6. 예상 총 소요시간

| Phase | 예상 시간 |
|-------|-----------|
| Phase 1: 정적 리소스 로컬화 | 2~3시간 |
| Phase 2: 번역 모델 로컬화 | 3~4시간 |
| Phase 3: Python 패키지 준비 | 1~2시간 |
| Phase 4: 오프라인 테스트 | 2~3시간 |
| **총합** | **1~2일** (모델 다운로드 + 환경 테스트 포함) |

---

## 7. 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-09 | §2, §3 | 번역 모델 제거 — 사용하지 않는 translation_service.py, back_translate 관련 코드, 번역 모델 파일 전부 제거 |
| 2026-06-09 | §4 | 루트 폴더 미사용 모델 정리 — Qwen, KLUE, 미사용 파인튜닝 모델, 학습 스크립트, 중복 configs 폴더 삭제 |

---

*계획서 승인("수행" 요청) 시 Phase 1부터 순차적으로 실행합니다.*
