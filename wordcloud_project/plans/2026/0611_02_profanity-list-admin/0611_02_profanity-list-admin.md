# 구현 계획서: 전사 욕설 리스트 (Admin 전용)

> 상태: DN | 작성일: 2026-06-11 | 완료일: 2026-06-11
> 수정 이력: 2026-06-11 | §4, §5, §7 | DB 일원화, 배치 처리 연동, 삭제 CASCADE 반영

---

## 1. 목표 및 범위

### 1.1 목표
- 전체 직원(전사) 중 **욕설이 감지된 직원과 문장**을 한 곳에서 목록 조회할 수 있는 Admin 전용 페이지를 신규 구현한다.
- 기존 `그룹분석(perspective_test)`에서 개별 직원 조회 시 욕설 정보를 확인하는 것을 **전체 직원 대상**으로 확장한다.

### 1.2 범위
- 백엔드: 전사 욕설 데이터 집계 API 2종
- 프론트엔드: 테이블 조회, 필터, 정렬, CSV 다운로드, 문장 상세 모달
- 네비게이션: `base.html` 메뉴 추가

---

## 2. 기능 요구사항

### 2.1 목록 조회

| 항목 | 설명 |
|------|------|
| 직원 기본 정보 | 이름(가명/실명), 사번, 부서 |
| 욕설 통계 | 총 평가 수, 욕설 건수, 욕설 비율 |
| 감지 단어 | 상위 5개 단어 태그 표시 |
| 액션 | **"상세 보기"** 버튼 → 문장 모달 |

### 2.2 필터 및 정렬

| 필터 | 타입 |
|------|------|
| 검색 | 직원명/사번 텍스트 검색 |
| 부서 | 드롭다운 (부서 목록 동적 로드) |
| 최소 욕설 수 | 숫자 입력 (예: 1건 이상) |

| 정렬 | 기본 |
|------|------|
| 욕설 건수 | 내림차순 (기본) |
| 욕설 비율 | 내림차순 |
| 직원명 | 오름차순 |

### 2.3 CSV 다운로드
- 현재 필터/정렬 기준으로 전체 데이터를 CSV로 다운로드
- 컬럼: 사번, 이름, 부서, 총평가수, 욕설건수, 비율, 감지단어, 문장목록

### 2.4 문장 상세 모달
- 직원별 **모든 욕설 문장** 표시
- 컬럼: No, 원본 문장, 필터링 결과, 감지 단어, 평가자 ID, 평가 배치

---

## 3. API 설계

### 3.1 `GET /api/perspective/profanity-list`

**전사 욕설 리스트 조회**

Query Parameters:
- `search` (string): 직원명/사번 검색
- `department` (string): 부서 필터
- `min_count` (int): 최소 욕설 수 (기본 1)
- `sort` (string): `count` \| `ratio` \| `name`
- `order` (string): `asc` \| `desc`
- `page` (int): 페이지 (기본 1)
- `limit` (int): 페이지당 수 (기본 50)

Response:
```json
{
  "success": true,
  "total": 120,
  "page": 1,
  "limit": 50,
  "items": [
    {
      "employee_id": "U001",
      "name": "홍길동",
      "department": "개발팀",
      "total_evaluations": 45,
      "profanity_count": 3,
      "profanity_ratio": 0.0667,
      "profanity_words": ["시발", "개XX"],
      "profanity_sentences": [
        {
          "original_text": "...",
          "filtered_text": "...",
          "detected_words": ["시발"],
          "evaluator_id": "E001",
          "batch_id": "B20260101"
        }
      ]
    }
  ]
}
```

### 3.2 `GET /api/perspective/profanity-list/csv`

**CSV 다운로드**

- Query Parameters: 동일
- Response: `text/csv` (파일 다운로드)

---

## 4. 구현 방식

### 4.1 DB 스키마 (`deploy_sessions.db` 일원화)

`deploy_session_service.py`의 `_init_db()`에 추가:

```sql
CREATE TABLE IF NOT EXISTS profanity_employees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        TEXT NOT NULL,
    employee_id     TEXT NOT NULL,
    profanity_count INTEGER NOT NULL,
    profanity_words TEXT,  -- JSON array
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pe_batch ON profanity_employees (batch_id);
CREATE INDEX IF NOT EXISTS idx_pe_employee ON profanity_employees (employee_id);

CREATE TABLE IF NOT EXISTS profanity_sentences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    profanity_employee_id INTEGER NOT NULL,
    original_text       TEXT,
    filtered_text       TEXT,
    detected_words      TEXT,  -- JSON array
    evaluator_id        TEXT,
    FOREIGN KEY (profanity_employee_id) REFERENCES profanity_employees(id) ON DELETE CASCADE
);
```

### 4.2 배치 처리 시 저장

**파일**: `src/services/batch_processor.py` (또는 `batch_events.py`)

배치 완료 시 `done` 이벤트 또는 `batch_processing_state` 처리 단계에서:

```python
from src.services.profanity_db_service import save_batch_profanity

# batch_state에서 profanity_employees 추출 후 DB 저장
save_batch_profanity(batch_id, batch_state['profanity_employees'])
```

`profanity_db_service.py` 신규:

```python
def save_batch_profanity(batch_id, profanity_employees_list):
    conn = _get_conn()  # deploy_sessions.db
    try:
        for emp in profanity_employees_list:
            eid = emp['employee_id']
            count = emp['profanity_count']
            words = json.dumps(emp.get('profanity_words', []), ensure_ascii=False)
            
            cursor = conn.execute(
                "INSERT INTO profanity_employees (batch_id, employee_id, profanity_count, profanity_words) VALUES (?, ?, ?, ?)",
                (batch_id, eid, count, words)
            )
            pe_id = cursor.lastrowid
            
            for sent in emp.get('profanity_sentences', []):
                conn.execute(
                    "INSERT INTO profanity_sentences (profanity_employee_id, original_text, filtered_text, detected_words, evaluator_id) VALUES (?, ?, ?, ?, ?)",
                    (pe_id, sent['original_text'], sent['filtered_text'],
                     json.dumps(sent.get('detected_words', []), ensure_ascii=False),
                     sent.get('evaluator_id', ''))
                )
        conn.commit()
    finally:
        conn.close()
```

### 4.3 배치 삭제 연동

**파일**: `src/services/user_data_manager.py`

`remove_batch_from_all()`에 한 줄 추가:

```python
def remove_batch_from_all(batch_id, employee_ids):
    conn = _get_eval_conn()
    try:
        cursor = conn.execute("DELETE FROM evaluations WHERE batch_id = ?", (batch_id,))
        conn.execute("DELETE FROM profanity_employees WHERE batch_id = ?", (batch_id,))  # 추가
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
```

### 4.4 조회

**파일**: `src/services/perspective_service.py`

`build_all_profanity_summary()` 수정:

```python
def build_all_profanity_summary(search=None, department=None, min_count=1):
    conn = _get_conn()  # deploy_sessions.db
    try:
        # employees 테이블 JOIN
        sql = """
            SELECT e.employee_id, e.name, e.department,
                   SUM(p.profanity_count) as profanity_count,
                   GROUP_CONCAT(p.profanity_words) as words_json
            FROM profanity_employees p
            JOIN employees e ON p.employee_id = e.employee_id
            GROUP BY p.employee_id
            HAVING profanity_count >= ?
        """
        rows = conn.execute(sql, (min_count,)).fetchall()
        # ... 필터/정렬/페이징 적용
    finally:
        conn.close()
```

### 4.5 백엔드 라우트

**파일**: `src/routes/perspective_routes.py`

- `api_profanity_list()` → `_is_admin()` → `build_all_profanity_summary()` → JSON
- `api_profanity_list_csv()` → CSV 응답

**파일**: `src/routes/ui_routes.py`

- `/profanity-list` → `profanity_list.html` 렌더링

### 4.6 프론트엔드

**파일**: `web/templates/profanity_list.html`

- `base.html` 상속
- 필터 영역, 테이블, CSV 다운로드, 문장 상세 모달

**파일**: `web/templates/base.html`

- 네비게이션 메뉴에 **"🚨 욕설 리스트"** 추가

---

## 5. 변경 파일 요약

| 파일 | 변경 내용 | 신규/수정 |
|------|----------|----------|
| `src/services/profanity_db_service.py` | 배치 욕설 데이터 저장/조회 (DB 일원화) | 신규 |
| `src/services/deploy_session_service.py` | `_init_db()`에 `profanity_employees`, `profanity_sentences` 테이블 추가 | 수정 |
| `src/services/batch_processor.py` | 배치 완료 시 `save_batch_profanity()` 호출 | 수정 |
| `src/services/user_data_manager.py` | `remove_batch_from_all()`에 `profanity_employees` 삭제 추가 | 수정 |
| `src/services/perspective_service.py` | `build_all_profanity_summary()` DB 조회 방식으로 수정 | 수정 |
| `src/routes/perspective_routes.py` | `/api/perspective/profanity-list`, `/api/perspective/profanity-list/csv` 추가 | 수정 |
| `src/routes/ui_routes.py` | `/profanity-list` 라우트 추가 | 수정 |
| `web/templates/profanity_list.html` | 전사 욕설 리스트 UI | 신규 |
| `web/templates/base.html` | 네비게이션 메뉴 추가 | 수정 |

---

## 6. 검증 시나리오

| 케이스 | 조건 | 확인 항목 | 예상 결과 |
|--------|------|----------|----------|
| A | 욕설 1건 이상 직원 3명 존재 | 목록에 3명 표시, 건수/비율 정확 | 3명 표시, 건수 일치 |
| B | 검색어 "홍길" 입력 | 해당 직원만 필터링 | 1명 표시 |
| C | 부서 "개발팀" 필터 | 개발팀 직원만 표시 | 개발팀 직원만 |
| D | CSV 다운로드 | 파일명 및 컬럼 확인 | `profanity_list_YYYYMMDD.csv`, 컬럼 정확 |
| E | 상세 모달 | 해당 직원의 모든 욕설 문장 표시 | 원본/필터링/감지단어 확인 |
| F | Admin 아닌 사용자 접근 | 401 응답 | Unauthorized |
| G | 배치 삭제 후 조회 | 삭제된 배치의 욕설 데이터 미표시 | 0건 또는 해당 직원 제외 |
| H | 신규 배치 처리 | 배치 완료 후 욕설 리스트에 자동 노출 | 신규 데이터 표시 |

---

## 7. 리스크 & 주의사항

### 7.1 데이터 일원화

- **DB만 사용**: `deploy_sessions.db`가 유일한 저장소. JSON 파일 이원화 금지.
- **배치 삭제 CASCADE**: `remove_batch_from_all`에서 `evaluations`와 `profanity_employees`를 동일 트랜잭션으로 삭제. 배치 삭제 시 욕설 데이터도 함께 제거됨.
- **스키마 마이그레이션**: 기존 DB에 테이블이 없으면 `_init_db()` 실행 시 자동 생성 (`CREATE TABLE IF NOT EXISTS`).

### 7.2 가명/원본 처리

- 저장: `employee_id`는 **가명(pseudo_id)** 그대로 사용 (`batch_processor`에서 이미 가명화 완료).
- 조회 시 원본 복원: `perspective_service._enrich_with_real_ids()` 레이어에서 처리 (기존 시스템 활용).
- 관리자 페이지는 `output_mode`에 따라 실명/가명 표시 (기존 로직 재사용).

---

## 8. 후속 확장 (선택)

- 욕설 단어별 통계: 어떤 단어가 가장 많이 사용되는지
- 부서별 통계: 부서별 욕설 비율 비교
- 기간별 추이: 월/년별 욕설 건수 변화
- 코퍼스 저장: `acquired_data` 형태로 욕설 문장을 별도 DB에 누적

---

*본 계획서는 DB 일원화와 배치 처리 연동을 핵심 설계로 반영한다.*
