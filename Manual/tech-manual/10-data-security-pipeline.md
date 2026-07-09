# 10. 데이터 보안·전처리·배포 파이프라인

분석 엔진 외에도, **개인정보를 보호하고 / 다양한 원본 파일을 읽어들이고 / 결과를 안전하게 배포**하는 주변 기술들이 시스템을 떠받친다.

---

## 10-1. 개인정보 가명화 (PseudonymManager)

> 코드 위치: `wordcloud_project/src/modules/pseudonym_manager.py`

### 개요

인사평가는 민감한 개인정보다. 분석 파이프라인에 들어가기 전에 **이름·부서 등을 가명("평가자_xxx")으로 치환**하고, 출력 직전에 **원본으로 복원**한다. 매핑 정보는 **암호화**되어 저장된다.

### 기술 상세

- **암호화 키 유도**: 마스터 비밀번호 → PBKDF2-HMAC-SHA256, 10만 회 반복, 32바이트 키(`pseudonym_manager.py:11`).

```python
def _derive_key(master_password):
    return base64.urlsafe_b64encode(
        hashlib.pbkdf2_hmac('sha256', master_password.encode(), b'pseudonym_salt', 100000, dklen=32))
```

- **대칭 암호화**: `cryptography` 의 Fernet으로 매핑 파일을 암호화 저장/복호화(`pseudonym_manager.py:28`, `:42`).
- **양방향 매핑**: `real_to_pseudo` / `pseudo_to_real` 두 방향을 보관(`pseudonym_manager.py:37`).
- **Thread-safe 캐시**: `threading.RLock` + 메모리 캐시로 병렬 처리 중 안전·고속(`pseudonym_manager.py:23`).

### ⚠️ 절대 규칙 (운영 필수)

`.clinerules/docs/project_wordcloud/README.md` 에 명시된 핵심 규칙:

1. **생성 시 인자 2개 필수**: `PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)` — 인자 누락 시 `TypeError` → 서버 500.
2. **조회 시 원본 복원 필수**: DB의 `employees.name`/`department` 는 가명일 수 있으므로, UI/CSV/API 출력 전 `get_real_id()` 로 복원.

---

## 10-2. 파일 파싱 (다중 인코딩·구분자 자동 감지)

> 코드 위치: `wordcloud_project/src/services/file_parser.py`

### 개요

업로드되는 엑셀/CSV는 인코딩과 구분자가 제각각이다(한글 Windows의 `cp949`, 일본어 `shift-jis` 등). 이 모듈은 **여러 인코딩과 구분자를 자동으로 시도**해 깨지지 않게 읽어낸다.

### 기술 상세

코드 위치: `file_parser.py:20`

```python
encodings_to_try = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'cp932', 'shift-jis', 'latin1']
separators = [',', ';', '\t', '|']
# 인코딩 × 구분자 조합을 차례로 시도해 성공하는 조합 채택
```

- Word(.docx)는 `python-docx`, 표 데이터는 `pandas` 로 처리.
- 컬럼 메타데이터 추출(`extract_column_info`, `file_parser.py:38`)로 후속 분석 매핑을 돕는다.

---

## 10-3. 데이터 저장 — SQLite(WAL) / PostgreSQL

- **세션·분석 결과**: SQLite, `PRAGMA journal_mode=WAL` 로 동시 읽기/쓰기 성능 확보(`perspective_service.py:33`).
- **운영 DB**: PostgreSQL(`psycopg2`) 지원(`requirements.txt`).
- **캐시/큐**: Redis 지원(`requirements.txt`).
- **배치 중간 상태**: JSON 체크포인트 + 작업서 DB([02장](02-parallel-processing.md)).

> 📌 `evaluation_id` 는 고유하지 않다(중복 가능). 감정 보정값 등은 반드시 **DB row id(`_db_id`)** 로 키잉해야 한다.

---

## 10-4. 배포 패키지 (내부망 오프라인)

> 참조: `.clinerules/docs/project_wordcloud/deployment.md`, `Manual/README.md`(설치 메뉴얼)

### 개요

이 시스템은 **인터넷이 차단된 내부망**에 배포된다. 따라서 Python 인터프리터, 150여 개 패키지, AI 모델(KoTE·반어법, 약 1GB)까지 **전부 포함한 자기완결형 패키지**로 묶는다.

### 기술 상세

| 배포 방식 | 명령 | 산출물 |
|-----------|------|--------|
| 일반(소스 전용) | `.\deploy\build_deploy.ps1` | `wordcloud-project.zip` |
| 패키지(전체) | `.\deploy\build_deploy.ps1 -Package` | `wordcloud-internal/` (venv + model 포함) |

- 모델은 `local_files_only=True` 로 로드되어(`leadership_analysis.py:60` 등) 오프라인에서도 동작.
- PDF 리포트 출력: `weasyprint`, `mkdocs-to-pdf`.
- UI 캡처/자동화: `selenium` + `webdriver-manager`.

---

## 핵심 포인트 정리

| 영역 | 핵심 기술 |
|------|-----------|
| 가명화 | PBKDF2(10만 회) + Fernet 암호화, 양방향 매핑, RLock 캐시 |
| 파일 파싱 | 7종 인코딩 × 4종 구분자 자동 감지, python-docx |
| 저장 | SQLite(WAL), PostgreSQL, Redis |
| 배포 | 내부망 오프라인 자기완결 패키지(venv+model 동봉) |

---

*처음으로: [메뉴얼 인덱스](README.md)*
