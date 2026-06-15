> 상태: PND | 작성일: 2026-06-15

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 전체 | 초안 |
| 2026-06-15 | §4-5, §4-6, §4-8 | **검토 반영: ①`display_name_old` → `saved_display_name` 변수명 수정(`NameError` 방지). ②§4-6 `import json` 추가 불필요로 정정(line 5에 이미 존재). ③§4-8 `display_name` innerHTML 삽입 시 HTML 이스케이프 처리 추가** |
| 2026-06-15 | §4-7, §6.2 | **버그 수정 반영: 기존 배치에 `batch_summary.json`이 없는 경우 PATCH API가 404를 반환하던 문제. 파일이 없으면 최소 summary(`batch_id`만)를 생성 후 진행하도록 변경** |
| 2026-06-15 | §4-5 | **버그 수정 반영: `metadata_service.get_batch_list()`가 `batch_summary.json`이 있는 배치만 반환하여, 기존 배치(파일 미존재)가 목록에서 누락되던 문제. `os.path.exists(summary_path)` 조건을 제거하고 모든 `batch_*` 폴더를 포함하도록 수정. summary가 없으면 배치명 기반 표시 + employee_count=0** |

---

# 배치 명칭 지정 및 수정

## 1. 개요

배치 처리 시 사용자가 배치의 표시 이름(display_name)을 직접 지정하고, 이후 그룹분석 페이지에서 수정할 수 있는 기능을 추가한다.

**작업 유형:** 기능 추가 (백엔드 + 프론트엔드)

---

## 2. 요구사항

| # | 요구사항 | 상세 |
|---|---------|------|
| 1 | 배치 처리 시작 전 명칭 입력 | 4단계(저장) "배치 처리 시작" 버튼 위에 입력란 추가 |
| 2 | 그룹분석에서 명칭 수정 | perspective_test.html 배치 이력 테이블에 수정 버튼 추가 |
| 3 | DB 스키마 변경 없음 | `batch_summary.json`에만 `display_name` 저장 |
| 4 | 폴더명 변경 없음 | 실제 폴더명(`batch_YYYYMMDD_X`)은 기존 로직 유지 |

---

## 3. 구현 방식

### 3.1 저장 방식

`batch_summary.json` 파일의 `batch_info` 객체에 `display_name` 필드를 추가한다.

```json
{
  "batch_info": {
    "batch_id": "batch_20260615_1",
    "display_name": "2025년 상반기 개발팀 평가",   // ← 신규 필드
    "created_at": "2026-06-15T14:30:00Z",
    ...
  }
}
```

### 3.2 display_name 우선순위

- `batch_summary.json`에 `display_name`이 있으면 → 우선 표시
- 없으면 → 기존 `batch_YYYYMMDD_X` 형식 표시

---

## 4. 상세 구현

### Phase 1: 배치 생성 시 명칭 입력

#### 4-1. `metadata_batch.html` (line 328~340, 4단계 영역)

**변경:** "배치 처리 시작" 버튼 바로 위에 입력란 추가

```html
<!-- 추가할 위치: line 338 <button class="btn btn-primary" onclick="startBatchProcessing()"> 앞 -->
<div style="margin: 15px 0; padding: 12px; background: #fff; border: 1px solid #ddd; border-radius: 6px;">
  <label for="batchDisplayName" style="font-weight: bold; display: block; margin-bottom: 5px;">
    배치 명칭 (선택)
  </label>
  <input type="text" id="batchDisplayName"
         placeholder="예: 2025년 상반기 개발팀 평가"
         style="width: 100%; padding: 8px 12px; border: 1px solid #dee2e6; border-radius: 6px; box-sizing: border-box;">
  <p style="font-size: 12px; color: #666; margin: 5px 0 0 0;">
    미입력 시 배치 ID(batch_YYYYMMDD_X)가 표시됩니다
  </p>
</div>
```

#### 4-2. `metadata_batch.js` — `startBatchProcessing()` (line 742)

**변경:** `settings` 객체에 `batch_display_name` 키 추가

```javascript
// line 762~766 settings 객체에 추가
var settings = {
    enablePreprocessing: document.getElementById('enablePreprocessing').checked,
    enableEmotionAnalysis: document.getElementById('enableEmotionAnalysis').checked,
    mappings: columnMappings,
    batch_display_name: document.getElementById('batchDisplayName').value.trim()  // ← 추가
};
```

#### 4-3. `batch_service.py` — `process_batch_metadata()` (line 305)

**변경:** `session_data`에 `batch_display_name`을 포함시켜 `_run_batch_process` → `process_batch`로 전달

```python
# line 339~344 session_data에 추가
session_data = {
    'csv_file_path': session_obj.get('csv_file_path'),
    'input_type': session_obj.get('input_type'),
    'csv_filename': session_obj.get('csv_filename'),
    'csv_rows': session_obj.get('csv_rows'),
    'batch_display_name': data.get('batch_display_name', ''),  # ← 추가 (data에서 추출)
}
```

**실제 동작:** `_run_batch_process()` (line 266) → `process_batch(PROCESSED_DATA_DIR_PATH, data, session_data)` → `data` 딕셔너리에 `batch_display_name`이 이미 포함되어 있으므로 `session_data`보다는 `data`에서 직접 읽는 것이 정확하다.

**수정 방향:** `_run_batch_process`는 `data`를 그대로 `process_batch`에 전달하므로, `process_batch_metadata`에서 `data`에 `batch_display_name`을 이미 포함시킨 상태로 전달하면 된다. 별도 수정 불필요.

> 확인 완료: `process_batch_metadata` (line 346~354)는 `data`를 그대로 `_run_batch_process(data, session_data)`에 전달하고, `_run_batch_process`는 `process_batch(PROCESSED_DATA_DIR_PATH, data, session_data)`로 전달한다.

#### 4-4. `batch_processor.py` — `process_batch()` 내 summary 저장 (line 810~865)

**현재 상태:** `create_batch_summary()` 함수(line 325)가 정의되어 있으나 `process_batch()`에서 호출되지 않음.

**변경:** `process_batch()` 종료 직전(line 846~847 부근)에서 `batch_summary.json`을 생성하도록 추가

```python
# line 846 ("session_data['batch_dir'] = batch_dir" 직후)에 추가
# batch_summary.json 생성
display_name = (data.get('batch_display_name') or '').strip()
_ensure_batch_summary(batch_dir, batch_processing_state, display_name)
```

**신규 함수:**
```python
def _ensure_batch_summary(batch_dir, batch_processing_state, display_name=''):
    """
    batch_summary.json 생성 또는 갱신 (display_name 저장용).
    
    Args:
        batch_dir: 배치 디렉토리 경로
        batch_processing_state: 처리 상태 dict
        display_name: 사용자 지정 배치 명칭 (없으면 빈 문자열)
    
    Returns:
        dict: 생성된 summary
    """
    import os, json
    summary_path = os.path.join(batch_dir, "tmeta", "batch_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    
    summary = {
        'batch_info': {
            'batch_id': os.path.basename(batch_dir),
            'display_name': display_name if display_name else '',
            'created_at': batch_processing_state.get('created_at', ''),
            'processed_at': datetime.now().isoformat() + 'Z',
            'unique_employees': batch_processing_state.get('total_employees', 0),
            'total_evaluations': batch_processing_state.get('total_rows', 0),
            'success_count': batch_processing_state.get('success_count', 0),
            'error_count': batch_processing_state.get('error_count', 0)
        },
        'processing_config': {}
    }
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return summary
```

---

### Phase 2: 배치 목록 조회 시 display_name 반영

#### 4-5. `metadata_service.py` — `get_batch_list()` (line 90)

**현재:** `batch_summary.json`에서 배치 정보를 읽어 `display_name`을 자체 계산 (날짜 기반).

**변경:** `display_name` 필드를 읽어 있으면 우선 사용, 없으면 기존 로직 유지.

```python
# line 123~129: if year and month and day: 블록 내에서 display_name 계산 직후 삽입
# 기존 변수명이 display_name이므로, JSON 저장값을 saved_display_name으로 분리한다.
saved_display_name = summary.get('batch_info', {}).get('display_name', '') or ''
batches.append({
    'name': saved_display_name if saved_display_name else display_name,  # JSON 값 우선, 없으면 날짜계산값
    'original_name': batch_name,
    'path': item_path,
    'employee_count': summary.get('batch_info', {}).get('unique_employees', 0),
    'created_at': summary.get('batch_info', {}).get('created_at', '').replace('Z', '').split('T')[0]
})
```

> ⚠️ **검토 수정:** 초안은 `display_name_old`를 사용했으나 해당 변수는 현 코드에 존재하지 않는다(`NameError` 발생). 날짜 기반으로 계산된 기존 값의 변수명이 `display_name`이므로, JSON에서 읽은 값을 `saved_display_name`으로 분리하여 우선순위를 적용한다.

#### 4-6. `perspective_service.py` — `_load_batch_list()` (line 552)

**현재:** DB 기반 조회, `batch_summary.json` 미참조.

**변경:** 각 배치의 `batch_summary.json`을 읽어 `display_name`이 있으면 포함.

```python
# line 573~579, batches.append 부분
display_name = ''
summary_path = os.path.join(batch_path, "tmeta", "batch_summary.json")
if os.path.exists(summary_path):
    try:
        with open(summary_path, 'r', encoding='utf-8') as _sf:
            _summary = json.load(_sf)
        display_name = _summary.get('batch_info', {}).get('display_name', '') or ''
    except Exception:
        pass

batches.append({
    'batch_id': batch_id,
    'path': batch_path,
    'display_name': display_name,  # ← 추가
    'created_at': (row['created_at'] or '')[:10],
    'employee_count': row['employee_count'],
    'total_evaluations': row['total_evaluations'],
})
```

> ✅ **검토 확인:** `perspective_service.py` line 5에 `import json`이 이미 존재한다. 추가 import 불필요.

---

### Phase 3: 그룹분석에서 명칭 수정

#### 4-7. `perspective_routes.py` — PATCH API 추가 (line 835~868)

**신규 엔드포인트:**

```python
@perspective_bp.route('/batch/<batch_id>/display-name', methods=['PATCH'])
def api_batch_update_display_name(batch_id):
    """배치 명칭(display_name) 수정"""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    data = request.get_json(silent=True) or {}
    display_name = (data.get('display_name') or '').strip()

    from src.config.settings import PROCESSED_DATA_DIR_PATH
    summary_path = os.path.join(PROCESSED_DATA_DIR_PATH, 'batch', batch_id, 'tmeta', 'batch_summary.json')

    try:
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json_lib.load(f)
        else:
            # 기존 배치(batch_summary.json 없는 경우) — 최소 summary 생성 후 진행
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            summary = {'batch_info': {'batch_id': batch_id}}

        if 'batch_info' not in summary:
            summary['batch_info'] = {}
        summary['batch_info']['display_name'] = display_name

        with open(summary_path, 'w', encoding='utf-8') as f:
            json_lib.dump(summary, f, ensure_ascii=False, indent=2)

        log_action('batch_display_name_update', {
            'batch_id': batch_id,
            'display_name': display_name,
        }, request)

        return jsonify({'success': True, 'display_name': display_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

> ⚠️ `perspective_routes.py`는 `json as json_lib`로 import되어 있으므로 `json_lib`을 사용한다.
> ⚠️ **변경사항:** 기존 초안은 파일이 없으면 404를 반환했으나, 코드 변경 전 생성된 배치에는 `batch_summary.json`이 존재하지 않는다. 따라서 파일이 없으면 최소 summary(`batch_id`만)를 생성하고 진행하는 것으로 수정하였다.

#### 4-8. `perspective_test.html` — `loadBatchHistory()` 테이블에 명칭 열 추가 (line 2350~2382)

**변경:** 테이블에 "명칭" 열과 수정(✏️) 버튼 열을 추가.

```html
<!-- line 2367 <thead> 부분 -->
<thead><tr style="background:#f0f0f0;">
  <th style="padding:4px 6px;text-align:left;border-bottom:1px solid #ddd;">명칭</th>
  <th style="padding:4px 6px;text-align:left;border-bottom:1px solid #ddd;">배치 ID</th>
  <th style="padding:4px 6px;text-align:center;border-bottom:1px solid #ddd;">생성일</th>
  <th style="padding:4px 6px;text-align:center;border-bottom:1px solid #ddd;">직원</th>
  <th style="padding:4px 6px;text-align:center;border-bottom:1px solid #ddd;">평가</th>
  <th style="padding:4px 6px;text-align:center;border-bottom:1px solid #ddd;"></th>
</tr></thead>
```

```html
<!-- line 2368~2374 <tbody> 부분 -->
d.batches.forEach(b => {
    var dn = b.display_name || '';
    // display_name을 innerHTML에 직접 삽입하므로 HTML 특수문자를 이스케이프한다.
    function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
    var dnDisplay = escHtml(dn ? dn : b.batch_id);
    html += `<tr>
      <td style="padding:4px 6px;border-bottom:1px solid #eee;">
        <span id="dn-${b.batch_id}">${dnDisplay}</span>
        <button class="btn-sm" style="padding:1px 4px;font-size:10px;margin-left:4px;"
                onclick="editDisplayName('${b.batch_id}')">✏️</button>
      </td>
      <td style="padding:4px 6px;border-bottom:1px solid #eee;color:#888;font-size:10px;">${b.batch_id}</td>
      <td style="padding:4px 6px;text-align:center;border-bottom:1px solid #eee;">${(b.created_at||'').slice(0,10)}</td>
      <td style="padding:4px 6px;text-align:center;border-bottom:1px solid #eee;">${b.employee_count}</td>
      <td style="padding:4px 6px;text-align:center;border-bottom:1px solid #eee;">${b.total_evaluations}</td>
      <td style="padding:4px 6px;text-align:center;border-bottom:1px solid #eee;">
        <button class="btn-danger btn-sm" style="padding:1px 6px;font-size:10px;"
                onclick="deleteBatch('${b.batch_id}', this)">삭제</button>
      </td>
    </tr>`;
});
```

**신규 JS 함수:**

```javascript
async function editDisplayName(batchId) {
    var currentSpan = document.getElementById('dn-' + batchId);
    var currentName = currentSpan.textContent.trim();
    var newName = prompt('배치 명칭을 입력하세요:', currentName === batchId ? '' : currentName);
    if (newName === null) return;  // 취소
    
    try {
        var r = await fetch('/api/perspective/batch/' + batchId + '/display-name', {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({display_name: newName.trim()})
        });
        var d = await r.json();
        if (d.success) {
            loadBatchHistory();  // 테이블 갱신
        } else {
            alert('수정 실패: ' + (d.error || ''));
        }
    } catch (e) {
        alert('오류: ' + e.message);
    }
}
```

---

## 5. 수정 파일 목록

| # | 파일 경로 | 변경 내용 | 비고 |
|---|----------|-----------|------|
| 1 | `web/templates/metadata_batch.html` | 4단계에 배치 명칭 입력란 추가 | ~10줄 |
| 2 | `web/static/js/metadata_batch.js` | `startBatchProcessing()`에 `batch_display_name` 전송 | ~2줄 |
| 3 | `src/services/batch_processor.py` | `_ensure_batch_summary()` 함수 추가, `process_batch()`에서 호출 | ~40줄 |
| 4 | `src/services/metadata_service.py` | `get_batch_list()`에서 `display_name` 우선 표시 | ~3줄 |
| 5 | `src/services/perspective_service.py` | `_load_batch_list()`에서 `display_name` 읽기 + `import json` 추가 | ~12줄 |
| 6 | `src/routes/perspective_routes.py` | `PATCH /api/perspective/batch/<id>/display-name` 엔드포인트 추가 | ~35줄 |
| 7 | `web/templates/perspective_test.html` | `loadBatchHistory()` 테이블에 명칭 열 + 수정 버튼 추가 | ~25줄 |

**총 예상: 약 130줄 추가/수정**

---

## 6. 영향도 분석

### 6.1 기존 코드 영향

| 항목 | 영향 | 설명 |
|------|------|------|
| 배치 폴더명 | ❌ 없음 | `batch_YYYYMMDD_X` 유지 |
| DB 스키마 | ❌ 없음 | 파일 기반 저장 |
| Resume / 작업서 | ❌ 없음 | `display_name` 미참조 |
| 삭제 로직 | ❌ 없음 | batch_id 기반 삭제 유지 |
| 워드클라우드 | ❌ 없음 | 해당 없음 |
| 배포 갤러리 | ❌ 없음 | 해당 없음 |

### 6.2 예외 처리

| 상황 | 처리 |
|------|------|
| `batch_summary.json` 없음 (PATCH 시) | 최소 summary(`batch_id`만) 생성 후 `display_name` 저장 |
| 입력란 미입력 | `display_name` 미저장 → 기존 `batch_id` 표시 |
| 특수문자/공백 입력 | 제한 없음 (표시용 문자열이므로) |
| 동일 명칭 중복 | 중복 허용 (식별자는 `batch_id`) |
| 파일 읽기 실패 | `try/except`로 무시 → 기존 `batch_id` 표시 |

---

## 7. 테스트 항목

1. 배치 생성 시 명칭 입력 → `batch_summary.json`에 `display_name` 저장 확인
2. 배치 생성 시 명칭 미입력 → `display_name` 없음 (기존 동작 유지)
3. `metadata_service.get_batch_list()` → `display_name` 우선 표시 확인
4. `perspective_service._load_batch_list()` → `display_name` 포함 확인
5. 그룹분석 페이지 수정 버튼 → `PATCH` API 호출 → JSON 파일 갱신 확인
6. 빈 문자열로 수정 → `display_name` 제거 (기존 batch_id 표시)
