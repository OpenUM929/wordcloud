# 테스트 메뉴 통합 및 욕설 필터 가시성 개선 계획서

> 작성일: 2026-06-02
> 대상: WordCloud Project
> 상태: 계획 확정 → Build Mode 진입 대기

---

## 1. 배경 및 목표

### 1.1 현재 문제점

1. **네비게이션 비체계화**: `sentiment_test.html`은 `base.html`을 상속하지 않고 독립 HTML로 작성되어 네비게이션 바가 중복·불일치함. `perspective_test`, `sentiment-test` 등 테스트 페이지가 메뉴에 제각각 흩어져 있음.
2. **테스트 코드 중복**: 감정테스트·욕설필터 등 각 테스트마다 고유 API + 고유 JS 렌더링 로직이 중복됨. 신규 테스트 추가 시 라우트·템플릿·JS를 처음부터 작성해야 함.
3. **워드클라우드 욕설 가시성 부족**: `wordcloud.html` 576번 라인에서 `detected_profanity`는 출력하지만, **어떤 계층(1/2)에서 어떤 방식으로 탐지했는지**, **원문 대비 필터링 결과는 무엇인지**, **처리 시간은 얼마인지** 알 수 없음.

### 1.2 목표

| # | 목표 | 산출물 |
|---|------|--------|
| 1 | 서버에 "테스트" 상위 메뉴를 만들고, 기존·향후 테스트 페이지를 하위 메뉴로 통합 | `base.html` 드롭다운, `test-common.css/js` |
| 2 | 모든 테스트 페이지가 공통 모듈(백엔드 프레임워크 + 프론트엔드 렌더러)을 통해 동일한 패턴으로 동작 | `test_framework.py`, `test_routes.py` |
| 3 | 워드클라우드 문장 출력 영역에 욕설 필터의 계층별 탐지 상세 정보 추가 | 확장된 `profanity_analysis_results`, `wordcloud.html` 상세折りたたみ |

---

## 2. 전체 구조

```
web/
├── templates/
│   ├── base.html                    ← "테스트" 드롭다운 메뉴 추가
│   ├── sentiment_test.html          ← base.html 상속 전환 + 공통 JS 적용
│   ├── profanity_test.html          ← 신규 (base.html 상속)
│   └── wordcloud.html               ← 평가 아이템에 필터 상세折りたたみ 추가
├── static/
│   ├── css/
│   │   └── test-common.css          ← 신규: 패널·테이블·배지·로그영역 공통 스타일
│   └── js/
│       └── test-common.js           ← 신규: TestRunner, TestRenderer, TestLogger
src/
├── modules/
│   └── test_framework.py            ← 신규: TestCase, TestRunner 공통 프레임워크
├── routes/
│   ├── ui_routes.py                 ← /profanity-test 라우트 추가
│   ├── test_routes.py               ← 신규: /api/test/* 공통 API
│   └── perspective_routes.py        ← 기존 API 호환 유지 (단계적 마이그레이션)
└── models/
    └── metadata_manager.py          ← profanity 상세 필드 저장 확장
```

---

## 3. 상세 구현 계획

### 3.1 네비게이션 재구성 (`base.html`)

#### 현재 상태
```html
<nav>
    <a href="/metadata_batch">메타데이터 생성 (배치)</a>
    <a href="/settings">설정</a>
    <span class="sep">│ 수동 조작</span>
    <a href="/">입력</a>
    <a href="/sarcasm">반어법 분석</a>
    <a href="/wordcloud">워드클라우드</a>
    <a href="/perspective_test">그룹분석(Test)</a>
    <a href="/wordcloud-preview">애니메이션 WC</a>
    <a href="/stopwords">불용어 관리</a>
    <span class="sep">│</span>
    <a href="/admin/batch-management">배치 관리</a>
    <a href="/admin/login">🔐 관리자</a>
</nav>
```

#### 변경 후
```html
<nav>
    <a href="/metadata_batch">메타데이터 생성 (배치)</a>
    <a href="/settings">설정</a>
    <span class="sep">│ 수동 조작</span>
    <a href="/">입력</a>
    <a href="/sarcasm">반어법 분석</a>
    <a href="/wordcloud">워드클라우드</a>
    <a href="/wordcloud-preview">애니메이션 WC</a>
    <a href="/stopwords">불용어 관리</a>
    <span class="sep">│</span>
    <div class="dropdown">
        <a href="javascript:void(0)" class="dropbtn">테스트 ▼</a>
        <div class="dropdown-content">
            <a href="/perspective_test">그룹분석</a>
            <a href="/sentiment-test">감정테스트</a>
            <a href="/profanity-test">욕설필터</a>
        </div>
    </div>
    <span class="sep">│</span>
    <a href="/admin/batch-management">배치 관리</a>
    <a href="/admin/login">🔐 관리자</a>
</nav>
```

> `sentiment_test.html` 내부의 `<nav>` 중복 태그 제거. `perspective_test.html`의 네비게이션도 `base.html` 기준으로 동기화.

#### CSS 추가 (`nav.css` 또는 `base.html` `<style>`)
```css
.dropdown { position: relative; display: inline-block; }
.dropbtn { cursor: pointer; }
.dropdown-content {
    display: none; position: absolute; background: #333;
    min-width: 160px; box-shadow: 0 8px 16px rgba(0,0,0,0.2); z-index: 1;
}
.dropdown-content a {
    color: #ddd; padding: 10px 16px; text-decoration: none; display: block; font-size: 14px;
}
.dropdown-content a:hover { background: #555; color: #fff; }
.dropdown:hover .dropdown-content { display: block; }
```

---

### 3.2 공통 테스트 프레임워크 (`src/modules/test_framework.py`)

#### 설계 개요
모든 테스트 유형(감정·욕설·형태소 등)이 동일한 인터페이스로 실행되고, 동일한 응답 규격을 반환하도록 추상화.

#### 핵심 클래스
```python
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List
import time

@dataclass
class TestCase:
    id: str
    input: str
    expected: Any
    category: str
    description: str = ""

@dataclass
class TestResult:
    case_id: str
    input: str
    expected: Any
    actual: Any
    match: bool
    processing_time_ms: int
    details: Dict[str, Any] = field(default_factory=dict)

class TestRunner:
    """공통 테스트 실행기. executor에 실제 분석 함수를 주입받아 동작."""
    
    def __init__(self, test_type: str, executor: Callable[[str, Dict], Dict]):
        self.test_type = test_type
        self.executor = executor
    
    def run_single(self, text: str, **params) -> Dict[str, Any]:
        """단일 실행"""
        start = time.time()
        actual = self.executor(text, params)
        elapsed = int((time.time() - start) * 1000)
        return {
            "test_type": self.test_type,
            "mode": "single",
            "input": text,
            "actual": actual,
            "processing_time_ms": elapsed,
        }
    
    def run_batch(self, cases: List[TestCase], **params) -> Dict[str, Any]:
        """배치 실행 → 통계 자동 계산"""
        results: List[TestResult] = []
        passed = 0
        total_time = 0
        
        for case in cases:
            start = time.time()
            actual = self.executor(case.input, params)
            elapsed = int((time.time() - start) * 1000)
            total_time += elapsed
            
            match = self._compare(actual, case.expected)
            if match:
                passed += 1
            
            results.append(TestResult(
                case_id=case.id,
                input=case.input,
                expected=case.expected,
                actual=actual,
                match=match,
                processing_time_ms=elapsed,
                details=actual  # 실제 결과 전체를 details에 포함
            ))
        
        total = len(cases)
        return {
            "success": True,
            "test_type": self.test_type,
            "mode": "batch",
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "accuracy": round(passed / total * 100, 2) if total > 0 else 0,
            "total_time_ms": total_time,
            "avg_time_ms": round(total_time / total, 1) if total > 0 else 0,
            "results": [vars(r) for r in results],
        }
    
    def _compare(self, actual: Dict, expected: Any) -> bool:
        """실제 결과와 기대값 비교. 테스트 유형별 오버라이드 가능."""
        if isinstance(expected, dict):
            for key, val in expected.items():
                if actual.get(key) != val:
                    return False
            return True
        return actual == expected
```

#### 테스트 유형별 Executor 주입 예시

| 테스트 유형 | Executor 함수 | 설명 |
|-------------|-------------|------|
| 감정분석 | `_exec_sentiment(text, params)` | `analyze_emotion` → `sentence_sentiment_override` 호출 |
| 욕설필터 | `_exec_profanity(text, params)` | `ProfanityFilter.advanced_filter_text` 호출 |
| 형태소분석 | `_exec_morphology(text, params)` | `Kiwi.tokenize` 결과 반환 |

---

### 3.3 공통 API 라우트 (`src/routes/test_routes.py`)

#### 엔드포인트 목록

| Method | Path | 설명 | 요청 본문 | 응답 |
|--------|------|------|-----------|------|
| POST | `/api/test/run` | 단일 테스트 실행 | `{test_type, text, params}` | `TestRunner.run_single` 결과 |
| POST | `/api/test/batch` | 배치 테스트 실행 | `{test_type, cases, params}` | `TestRunner.run_batch` 결과 |
| GET | `/api/test/cases/<test_type>` | 등록된 테스트케이스 목록 | - | `{cases: [...]}` |
| POST | `/api/test/cases/<test_type>` | 테스트케이스 추가/수정 | `{id, input, expected, category, description}` | `{success, message}` |
| DELETE | `/api/test/cases/<test_type>/<case_id>` | 테스트케이스 삭제 | - | `{success, message}` |

#### 기존 API 호환성
- 기존 `/api/perspective/test/sentence-sentiment`는 **그대로 유지**.
- `sentiment_test.html`은 1단계에서 공통 JS(`test-common.js`)로 교체하고, 2단계에서 공통 API(`/api/test/run`)로 점진적 마이그레이션.

---

### 3.4 공통 프론트엔드 자산

#### `web/static/css/test-common.css`

```css
/* 공통 테스트 페이지 스타일 */
.test-container { max-width: 1400px; margin: 20px auto; padding: 0 20px; }
.test-panel { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.test-input-area { display: flex; gap: 10px; margin-bottom: 15px; }
.test-textarea { flex: 1; height: 80px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; resize: vertical; }
.test-btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 600; }
.test-btn-primary { background: #007bff; color: white; }
.test-btn-success { background: #28a745; color: white; }
.test-btn-secondary { background: #6c757d; color: white; }
.test-btn:disabled { background: #ccc; cursor: not-allowed; }

/* 프리셋 버튼 */
.preset-buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 15px; }
.preset-btn { padding: 6px 12px; border: 1px solid #007bff; background: white; color: #007bff; border-radius: 4px; cursor: pointer; font-size: 12px; }
.preset-btn:hover { background: #007bff; color: white; }

/* 요약 패널 */
.test-summary { display: flex; gap: 30px; margin-bottom: 15px; padding: 15px; background: #f8f9fa; border-radius: 6px; }
.test-summary-item { text-align: center; }
.test-summary-item .number { font-size: 28px; font-weight: bold; color: #007bff; }
.test-summary-item .label { font-size: 12px; color: #666; }

/* 결과 테이블 */
.test-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.test-table th { background: #f0f0f0; padding: 10px 8px; text-align: left; font-weight: 600; border-bottom: 2px solid #ddd; position: sticky; top: 0; }
.test-table td { padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; }
.test-table tr:hover { background: #f8f9fa; }

/* 배지 */
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-pass { background: #d4edda; color: #155724; }
.badge-fail { background: #f8d7da; color: #721c24; }
.badge-layer1 { background: #cce5ff; color: #004085; }
.badge-layer2 { background: #fff3cd; color: #856404; }

/* 로그 영역 */
.test-log-area { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 6px; font-family: 'Consolas', monospace; font-size: 12px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; }
.test-log-info { color: #4fc1ff; }
.test-log-success { color: #4ec9b0; }
.test-log-error { color: #f48771; }
```

#### `web/static/js/test-common.js`

```javascript
/**
 * 공통 테스트 프론트엔드 모듈
 * 모든 테스트 페이지(sentiment, profanity, ...)가 공유
 */

const TestRunner = {
    async run(testType, text, params = {}) {
        const res = await fetch('/api/test/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_type: testType, text, params })
        });
        return res.json();
    },

    async runBatch(testType, cases, params = {}) {
        const res = await fetch('/api/test/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_type: testType, cases, params })
        });
        return res.json();
    },

    async loadCases(testType) {
        const res = await fetch(`/api/test/cases/${testType}`);
        return res.json();
    }
};

const TestRenderer = {
    renderTable(containerId, results, columns) {
        const container = document.getElementById(containerId);
        if (!container) return;
        let h = '<table class="test-table"><thead><tr>';
        columns.forEach(col => { h += `<th>${col.header}</th>`; });
        h += '</tr></thead><tbody>';
        results.forEach(row => {
            h += '<tr>';
            columns.forEach(col => {
                const val = col.accessor(row);
                h += `<td>${col.formatter ? col.formatter(val, row) : val}</td>`;
            });
            h += '</tr>';
        });
        h += '</tbody></table>';
        container.innerHTML = h;
    },

    renderSummary(containerId, stats) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = `
            <div class="test-summary">
                <div class="test-summary-item">
                    <div class="number">${stats.total}</div>
                    <div class="label">총 케이스</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#28a745">${stats.passed}</div>
                    <div class="label">통과</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#dc3545">${stats.failed}</div>
                    <div class="label">실패</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#fd7e14">${stats.accuracy}%</div>
                    <div class="label">정확도</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#6f42c1">${stats.avg_time_ms}ms</div>
                    <div class="label">평균 처리시간</div>
                </div>
            </div>
        `;
    }
};

const TestLogger = {
    log(containerId, msg, type = 'info') {
        const area = document.getElementById(containerId);
        if (!area) return;
        const cls = type === 'success' ? 'test-log-success' : type === 'error' ? 'test-log-error' : 'test-log-info';
        area.innerHTML += `<div class="${cls}">${new Date().toLocaleTimeString()} ${msg}</div>`;
        area.scrollTop = area.scrollHeight;
    },
    clear(containerId) {
        const area = document.getElementById(containerId);
        if (area) area.innerHTML = '';
    }
};
```

---

### 3.5 욕설 필터 테스트 페이지 (`profanity_test.html`)

#### 페이지 구조

```html
{% extends "base.html" %}
{% block title %}욕설 필터 테스트{% endblock %}
{% block extra_head %}
<link rel="stylesheet" href="/static/css/test-common.css">
{% endblock %}

{% block content %}
<div class="test-container">
    <h1>욕설 필터 2계층 탐지 테스트</h1>

    <!-- 설정 패널 (1계층/2계층 ON/OFF) -->
    <div class="test-panel">
        <h3>설정</h3>
        <div class="checkbox-group">
            <label><input type="checkbox" id="enableLayer1" checked> 1계층 활성화 (Kiwi 형태소)</label>
            <label><input type="checkbox" id="enableLayer2" checked> 2계층 활성화 (음절 간격)</label>
            <label><input type="checkbox" id="showDetails" checked> 상세 정보 표시</label>
        </div>
    </div>

    <!-- 개별 테스트 -->
    <div class="test-panel">
        <h3>개별 문장 테스트</h3>
        <div class="preset-buttons">
            <button class="preset-btn" onclick="setText('시발점은 업무의 시작점입니다')">정상: 시발점</button>
            <button class="preset-btn" onclick="setText('씨발점은 업무의 시작점입니다')">1계층: 씨발점</button>
            <button class="preset-btn" onclick="setText('시. 발! 느낌표')">2계층: 시. 발!</button>
            <button class="preset-btn" onclick="setText('개!새끼 같은 태도')">2계층: 개!새끼</button>
            <button class="preset-btn" onclick="setText('업무 능력이 뛰어납니다')">정상 문장</button>
            <button class="preset-btn" onclick="setText('')">지우기</button>
        </div>
        <div class="test-input-area">
            <textarea id="testText" class="test-textarea" placeholder="테스트할 문장을 입력하세요..."></textarea>
            <button class="test-btn test-btn-primary" onclick="runSingle()">테스트 실행</button>
        </div>
        <div id="singleResult"></div>
    </div>

    <!-- 배치 테스트 -->
    <div class="test-panel">
        <h3>12개 예제 일괄 테스트</h3>
        <button class="test-btn test-btn-success" onclick="runBatch()">일괄테스트 실행</button>
        <div id="batchSummary" style="margin-top:15px;"></div>
        <div id="batchResults"></div>
    </div>

    <!-- 단어 관리 (간략히) -->
    <div class="test-panel">
        <h3>등록된 욕설 단어 목록</h3>
        <div id="wordList"></div>
    </div>

    <!-- 로그 -->
    <div class="test-panel">
        <h3>로그</h3>
        <div id="logArea" class="test-log-area"></div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/test-common.js"></script>
<script>
const TEST_TYPE = 'profanity';

function setText(t) { document.getElementById('testText').value = t; }

async function runSingle() {
    const text = document.getElementById('testText').value.trim();
    if (!text) { alert('문장을 입력하세요'); return; }
    TestLogger.clear('logArea');
    TestLogger.log('logArea', `개별 테스트 시작: "${text.substring(0,50)}..."`);

    const params = {
        enable_layer1: document.getElementById('enableLayer1').checked,
        enable_layer2: document.getElementById('enableLayer2').checked,
    };

    try {
        const d = await TestRunner.run(TEST_TYPE, text, params);
        renderSingle(d);
        TestLogger.log('logArea', `완료: ${d.processing_time_ms}ms`, 'success');
    } catch(e) {
        TestLogger.log('logArea', '오류: ' + e.message, 'error');
    }
}

function renderSingle(data) {
    const actual = data.actual || {};
    const show = document.getElementById('showDetails').checked;
    let h = '<table class="test-table">';
    h += `<tr><th>원본</th><td>${actual.original_text || ''}</td></tr>`;
    h += `<tr><th>필터링 결과</th><td>${actual.filtered_text || ''}</td></tr>`;
    h += `<tr><th>탐지 단어</th><td>${(actual.detected_profanity || []).join(', ') || '없음'}</td></tr>`;
    h += `<tr><th>사용 계층</th><td>${(actual.methods_used || []).join(', ') || '없음'}</td></tr>`;
    if (show) {
        h += `<tr><th>언어 판정</th><td>${actual.language || '-'}</td></tr>`;
        h += `<tr><th>처리 시간</th><td>${actual.processing_time_ms || 0}ms</td></tr>`;
    }
    h += '</table>';
    document.getElementById('singleResult').innerHTML = h;
}

async function runBatch() {
    TestLogger.clear('logArea');
    TestLogger.log('logArea', '배치 테스트 시작...');
    try {
        const cases = await TestRunner.loadCases(TEST_TYPE);
        if (!cases.cases || cases.cases.length === 0) {
            TestLogger.log('logArea', '등록된 테스트케이스가 없습니다.', 'error');
            return;
        }
        const d = await TestRunner.runBatch(TEST_TYPE, cases.cases);
        TestRenderer.renderSummary('batchSummary', d);
        // results 렌더링...
        TestLogger.log('logArea', `배치 완료: ${d.accuracy}% (${d.passed}/${d.total})`, 'success');
    } catch(e) {
        TestLogger.log('logArea', '오류: ' + e.message, 'error');
    }
}
</script>
{% endblock %}
```

#### 12개 테스트케이스 예시 (`configs/test_cases/profanity_cases.json`)

```json
[
  {"id": "pf-01", "input": "시발점은 업무의 시작점입니다", "expected": {"detected": false}, "category": "정상", "description": "1계층: '시발'이지만 '시발점'은 정상 명사"},
  {"id": "pf-02", "input": "씨발점은 업무의 시작점입니다", "expected": {"detected": true, "methods_used": ["kiwi_morpheme"]}, "category": "1계층", "description": "1계층: 정확한 욕설 형태소"},
  {"id": "pf-03", "input": "시. 발! 느낌표", "expected": {"detected": true, "methods_used": ["gap_pattern"]}, "category": "2계층", "description": "2계층: 음절 사이 특수문자"},
  {"id": "pf-04", "input": "개!새끼 같은 태도", "expected": {"detected": true, "methods_used": ["gap_pattern"]}, "category": "2계층", "description": "2계층: 중간에 느낌표"},
  {"id": "pf-05", "input": "업무 능력이 뛰어납니다", "expected": {"detected": false}, "category": "정상", "description": "정상 문장"},
  {"id": "pf-06", "input": "씨1발점은", "expected": {"detected": true}, "category": "2계층", "description": "2계층: 숫자 간격"},
  {"id": "pf-07", "input": "개 새 끼", "expected": {"detected": true}, "category": "2계층", "description": "2계층: 공백 간격"},
  {"id": "pf-08", "input": "시발", "expected": {"detected": true, "methods_used": ["kiwi_morpheme"]}, "category": "1계층", "description": "1계층: 단독 욕설"},
  {"id": "pf-09", "input": "씨발", "expected": {"detected": true, "methods_used": ["kiwi_morpheme"]}, "category": "1계층", "description": "1계층: 단독 욕설"},
  {"id": "pf-10", "input": "개새끼", "expected": {"detected": true, "methods_used": ["kiwi_morpheme"]}, "category": "1계층", "description": "1계층: 단독 욕설"},
  {"id": "pf-11", "input": "시스템 발전을 기대합니다", "expected": {"detected": false}, "category": "정상", "description": "정상: '시발'이 포함되나 의미 없음"},
  {"id": "pf-12", "input": "미개한 사고방식", "expected": {"detected": false}, "category": "정상", "description": "정상: '개'가 포함되나 의미 없음"}
]
```

---

### 3.6 감정테스트 페이지 리팩토링 (`sentiment_test.html`)

#### 변경 사항
1. `<!DOCTYPE html>...` 독립 HTML → `{% extends "base.html" %}` 전환
2. `<nav>` 중복 태그 제거
3. 스타일 블록 → `test-common.css` 임포트
4. JS → `test-common.js` 임포트 + `TestRunner` 사용
5. API 엔드포인트를 `/api/perspective/test/sentence-sentiment` → `/api/test/run` (test_type: sentiment) 점진적 마이그레이션

> **주의**: 100문장 배치 테스트(`TEST_SENTENCES_100`)는 서버 사이드에 이미 하드코딩되어 있으므로, 공통 케이스 로더(`/api/test/cases/sentiment`)로 이관 필요.

---

### 3.7 워드클라우드 욕설 상세 정보 추가

#### A. 메타데이터 저장 확장 (`src/models/metadata_manager.py`)

현재 저장 구조:
```python
profanity_result = advanced_filter_profanity(analyzed_eval.get('evaluation_document', ''))
# → detected_profanity, profanity_count 만 저장
```

**확장 후 저장 필드:**
```json
{
  "detected_profanity": ["씨발", "개새끼"],
  "profanity_count": 2,
  "detection_details": [
    {"word": "씨발", "layer": "morpheme", "method": "kiwi_morpheme", "span": [2, 4]},
    {"word": "개새끼", "layer": "gap", "method": "gap_pattern", "span": [10, 13]}
  ],
  "filtered_text": "***점은 업무의 ***입니다",
  "methods_used": ["kiwi_morpheme", "gap_pattern"],
  "processing_time_ms": 12,
  "language_detected": "ko"
}
```

#### B. `profanity_filter.py` 반환값 확장

`advanced_filter_text` 반환값에 `detection_details` 추가:

```python
# 현재
result = {
    "original_text": original_text,
    "filtered_text": filtered_text,
    "language": language,
    "detected_profanity": list(set(detected_profanity)),
    "methods_used": methods_used,
    "profanity_count": len(set(detected_profanity)),
    "processing_time_ms": processing_time
}

# 확장 후
result = {
    ...  # 기존 필드 유지
    "detection_details": self._build_detection_details(
        morpheme_detected, gap_detected, text
    ),
}

def _build_detection_details(self, morpheme, gap, text):
    details = []
    # 1계층
    for word in morpheme:
        idx = text.find(word)
        details.append({"word": word, "layer": "morpheme", "method": "kiwi_morpheme", "span": [idx, idx+len(word)]})
    # 2계층
    for word in gap:
        # regex 매칭 위치 추적 필요 — _apply_filter에서 span 기록하도록 수정
        details.append({"word": word, "layer": "gap", "method": "gap_pattern", "span": [start, end]})
    return details
```

> **구현 주의**: 2계층 regex는 치환 시 정확한 span 기록이 어려울 수 있음. `_apply_filter` 내부에서 치환 위치를 함께 반환하도록 수정 필요.

#### C. `wordcloud.html` 평가 아이템 출력 확장

기존 576번 라인 주변:
```html
${evaluation.profanity_analysis_results?.detected_profanity && evaluation.profanity_analysis_results.detected_profanity.length > 0 ? `<p style="font-size: 14px; color: #d9534f;"><strong>비속어:</strong> ${evaluation.profanity_analysis_results.detected_profanity.join(', ')}</p>` : ''}
```

**변경 후:**
```html
${evaluation.profanity_analysis_results?.detected_profanity && evaluation.profanity_analysis_results.detected_profanity.length > 0 ? `
    <p style="font-size: 14px; color: #d9534f;"><strong>비속어:</strong> ${evaluation.profanity_analysis_results.detected_profanity.join(', ')}</p>
    <details style="margin-top:4px;font-size:12px;">
        <summary style="color:#dc3545;cursor:pointer;">▼ 필터 상세</summary>
        <div style="color:#666;padding:8px;background:#f8f9fa;border-radius:4px;">
            <p><strong>원본:</strong> ${evaluation.profanity_analysis_results.original_text || ''}</p>
            <p><strong>필터링 결과:</strong> ${evaluation.profanity_analysis_results.filtered_text || ''}</p>
            <p><strong>탐지 계층:</strong> ${(evaluation.profanity_analysis_results.methods_used || []).map(m => 
                m === 'kiwi_morpheme' ? '<span class="badge badge-layer1">1계층(형태소)</span>' : 
                m === 'gap_pattern' ? '<span class="badge badge-layer2">2계층(간격)</span>' : m
            ).join(' ')}</p>
            <p><strong>처리 시간:</strong> ${evaluation.profanity_analysis_results.processing_time_ms || 0}ms</p>
            <p><strong>언어 판정:</strong> ${evaluation.profanity_analysis_results.language_detected || '-'}</p>
            ${evaluation.profanity_analysis_results.detection_details ? `
                <p><strong>상세 위치:</strong></p>
                <ul style="margin:4px 0;padding-left:20px;">
                    ${evaluation.profanity_analysis_results.detection_details.map(d => 
                        `<li>${d.word}: ${d.layer} (${d.span[0]}-${d.span[1]})</li>`
                    ).join('')}
                </ul>
            ` : ''}
        </div>
    </details>
` : ''}
```

---

## 4. 구현 단계 (로드맵)

| 단계 | 작업 | 산출물 | 예상 소요 | 의존성 |
|------|------|--------|-----------|--------|
| **1** | `base.html` 네비게이션에 "테스트" 드롭다운 추가 + `nav.css` 수정 | UI 통합 | 30분 | - |
| **2** | `test_framework.py` 작성 + `test_routes.py` 신규 | 공통 백엔드 | 1.5시간 | - |
| **3** | `test-common.css`, `test-common.js` 작성 | 공통 프론트엔드 | 1시간 | - |
| **4** | `profanity_test.html` 신규 작성 + `ui_routes.py` 라우트 추가 | 욕설필터 테스트 페이지 | 1.5시간 | 1, 2, 3 |
| **5** | `sentiment_test.html` → `base.html` 상속 전환 + 공통 JS 적용 | 감정테스트 리팩토링 | 2시간 | 1, 3 |
| **6** | `profanity_filter.py`에 `detection_details` 반환 추가 | 필터 상세 정보 | 1시간 | - |
| **7** | `metadata_manager.py`에 profanity 상세 필드 저장 확장 | 메타데이터 저장 | 1시간 | 6 |
| **8** | `wordcloud.html` 평가 아이템에 필터 상세折りたたみ 추가 | 워드클라우드 UI 개선 | 1시간 | 7 |
| **9** | 통합 테스트: 100문장 감정분석 + 12개 욕설케이스 + 워드클라우드 출력 검증 | 검증 완료 | 1시간 | 4, 5, 8 |

**총 예상:** 10.5시간 (단계별 순차 실행, 단계 1~3은 병렬 가능)

---

## 5. 리스크 및 대응

| 리스크 | 영향도 | 대응 방안 |
|--------|--------|-----------|
| `sentiment_test.html` `base.html` 상속 전환 시 스타일 깨짐 | 중간 | 전환 후 visual regression 확인. `extra_head`로 기존 스타일 보충 |
| 2계층 regex span 추적 구현 복잡성 | 중간 | 단순화: `_apply_filter`에서 `(word, start, end)` 튜플 반환으로 변경 |
| 기존 API 마이그레이션 중 호환성 깨짐 | 높음 | 기존 `/api/perspective/test/sentence-sentiment`는 **유지**. `sentiment_test.html`이 신규 API를 호출하도록 단계적 전환 |
| 12개 테스트케이스 JSON 파일 관리 | 낮음 | `configs/test_cases/` 디렉토리 생성. Git 버전 관리 |

---

## 6. 확인 필요 사항

계획대로 진행하기 전에 아래 사항을 확인해 주세요:

1. **`sentiment_test.html`을 `base.html` 상속으로 전환**해도 되는지 확인 필요. (현재 독립 HTML이라 `<style>` 블록이 크게 다를 수 있음)
2. **테스트 케이스 저장 위치**: `configs/test_cases/` JSON 파일 방식이 적절한지?
3. **워드클라우드 필터 상세 정보**는 모든 사용자에게 보이게 할 것인지, 아니면 "관리자/디버그 모드"에서만 보이게 할 것인지?
4. **구현 시작 단계**: 1단계부터 순차적으로 진행할 것인지, 특정 단계를 우선으로 할 것인지?

---

## 7. 관련 파일

| 파일 | 역할 |
|------|------|
| `web/templates/base.html` | 네비게이션 드롭다운 수정 대상 |
| `web/templates/sentiment_test.html` | 리팩토링 대상 (독립 HTML → base.html 상속) |
| `web/templates/profanity_test.html` | 신규 작성 대상 |
| `web/templates/wordcloud.html` | 필터 상세 출력 추가 대상 |
| `web/static/css/test-common.css` | 신규 공통 스타일 |
| `web/static/js/test-common.js` | 신규 공통 JS 모듈 |
| `src/modules/test_framework.py` | 신규 공통 테스트 프레임워크 |
| `src/routes/test_routes.py` | 신규 공통 API 라우트 |
| `src/routes/ui_routes.py` | `/profanity-test` 라우트 추가 |
| `src/modules/profanity_filter.py` | `detection_details` 반환 추가 |
| `src/models/metadata_manager.py` | profanity 상세 저장 확장 |
| `configs/test_cases/profanity_cases.json` | 신규 테스트케이스 JSON |
| `configs/test_cases/sentiment_cases.json` | 기존 100문장 이관 대상 |

---

*본 계획서는 Plan Mode 조사 결과를 바탕으로 작성되었습니다.*
*Build Mode 전환 후 단계별 구현을 시작합니다.*
