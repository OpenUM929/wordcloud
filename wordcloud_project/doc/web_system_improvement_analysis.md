# 웹 시스템 폴더 구조 개선 분석

## 문제 개요
현재 웹 시스템의 폴더 구조는 batch 처리 결과를 저장하는 방식이 불명확하고 관리가 어렵습니다. 특히 batch 폴더 이름이 timestamp를 기반으로 생성되어 중복 가능성이 있고, 데이터와 이미지가 분리되어 저장되어 검색과 관리가 복잡합니다.

## 요구사항
1. `processed_data/batch/batch_YYYYMMDD_N` 폴더 구조로 변경 (N은 0부터 증가)
2. 배치 결과 메타데이터는 `processed_data/batch/batch_YYYYMMDD_N/tdata`에 저장
3. 워드클라우드 이미지는 `processed_data/batch/batch_YYYYMMDD_N/word`에 저장

## 수정 계획

### 1. 폴더 생성 로직 변경
- 기존: `processed_data/batch/batch_YYYYMMDD_HHMMSS`
- 새로운: `processed_data/batch/batch_YYYYMMDD_N` (N은 0부터 증가)

### 2. 메타데이터 저장 경로 변경
- 기존: 배치 폴더 직접
- 새로운: `processed_data/batch/batch_YYYYMMDD_N/tdata`

### 3. 워드클라우드 저장 경로 변경
- 기존: `processed_data/batch/batch_YYYYMMDD_N/wordclouds`
- 새로운: `processed_data/batch/batch_YYYYMMDD_N/word`

### 4. 배치 폴더 찾기 로직 변경
- 기존: timestamp 기반 검색
- 새로운: 날짜별 N 번호 기반 검색

## 수정 사항 목록

### web/app.py 수정

#### 1. 배치 폴더 생성 경로 변경
```python
# 변경 전
batch_dir = os.path.abspath(os.path.join(PROJECT_ROOT, PROCESSED_DATA_DIR, "batch", f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"))

# 변경 후
current_date = datetime.now().strftime('%Y%m%d')
batch_num = 0
while True:
    batch_dir = os.path.abspath(os.path.join(PROJECT_ROOT, PROCESSED_DATA_DIR, "batch", f"batch_{current_date}_{batch_num}"))
    if not os.path.exists(batch_dir):
        break
    batch_num += 1
os.makedirs(batch_dir, exist_ok=True)

# 메타데이터와 워드클라우드 폴더 생성
tdata_dir = os.path.join(batch_dir, "tdata")
word_dir = os.path.join(batch_dir, "word")
os.makedirs(tdata_dir, exist_ok=True)
os.makedirs(word_dir, exist_ok=True)
```

#### 2. 메타데이터 저장 경로 변경
```python
# 변경 전
metadata_path = os.path.join(batch_dir, f"employee_{employee_id}.json")

# 변경 후
metadata_path = os.path.join(tdata_dir, f"employee_{employee_id}.json")
```

#### 3. 워드클라우드 저장 경로 변경
```python
# 변경 전
wordcloud_dir = os.path.join(batch_dir, "wordclouds")
os.makedirs(wordcloud_dir, exist_ok=True)
output_path = os.path.abspath(os.path.join(wordcloud_dir, f"wordcloud_{employee_id}.png"))

# 변경 후
word_dir = os.path.join(batch_dir, "word")
os.makedirs(word_dir, exist_ok=True)
output_path = os.path.abspath(os.path.join(word_dir, f"wordcloud_{employee_id}.png"))
```

#### 4. 워드클라우드 URL 생성 로직 변경
```python
# 변경 전
if wordcloud_path.startswith('wordclouds/'):
    batch_name = os.path.basename(batch_path)
    wordcloud_url = f"/processed_data/batch/{batch_name}/{wordcloud_path}"

# 변경 후
if wordcloud_path.startswith('word/'):
    batch_name = os.path.basename(batch_path)
    wordcloud_url = f"/processed_data/batch/{batch_name}/{wordcloud_path}"
```

#### 5. 다운로드 함수 업데이트
```python
@app.route('/download_batch_results')
def download_batch_results():
    try:
        if 'batch_results' not in session or 'batch_dir' not in session:
            return jsonify({'error': '배치 처리 결과가 없습니다.'}), 400

        summary = json.loads(session['batch_results'])
        batch_dir = session['batch_dir']

        if not batch_dir or not os.path.exists(batch_dir):
            return jsonify({'error': '배치 처리 결과를 찾을 수 없습니다.'}), 404

        import zipfile
        from io import BytesIO

        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('batch_summary.json', json.dumps(summary, ensure_ascii=False, indent=2))

            # tdata 폴더의 모든 파일 추가
            tdata_dir = os.path.join(batch_dir, 'tdata')
            if os.path.exists(tdata_dir):
                for file_name in os.listdir(tdata_dir):
                    file_path = os.path.join(tdata_dir, file_name)
                    if os.path.isfile(file_path):
                        relative_path = os.path.relpath(file_path, batch_dir)
                        zf.write(file_path, relative_path)

            # word 폴더의 모든 파일 추가
            word_dir = os.path.join(batch_dir, 'word')
            if os.path.exists(word_dir):
                for file_name in os.listdir(word_dir):
                    file_path = os.path.join(word_dir, file_name)
                    if os.path.isfile(file_path):
                        relative_path = os.path.relpath(file_path, batch_dir)
                        zf.write(file_path, relative_path)

        memory_file.seek(0)

        from flask import send_file
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'batch_results_{os.path.basename(batch_dir)}.zip'
        )

    except Exception as e:
        return jsonify({'error': f'결과 다운로드 실패: {str(e)}'}), 500
```

#### 6. 정적 파일 서빙 경로 추가
```python
@app.route('/processed_data/batch/<batch_name>/word/<filename>')
def serve_batch_word(batch_name, filename):
    batch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../processed_data/batch/{batch_name}"))
    word_dir = os.path.join(batch_dir, "word")
    return send_from_directory(word_dir, filename)
```

#### 7. 워드클라우드 재생성 함수 업데이트
```python
@app.route('/regenerate_wordcloud', methods=['POST'])
def regenerate_wordcloud():
    try:
        data = request.json
        employee_id = data.get('employee_id')
        batch_path = data.get('batch_path')
        
        if not employee_id or not batch_path:
            return jsonify({'success': False, 'error': '직원 ID와 배치 경로가 필요합니다.'}), 400

        word_dir = os.path.join(batch_path, "word")
        os.makedirs(word_dir, exist_ok=True)
        
        output_path = os.path.abspath(os.path.join(word_dir, f"wordcloud_{employee_id}.png"))
        
        # 나머지 코드...
        
        metadata['wordcloud_path'] = f"word/wordcloud_{employee_id}.png"
        
        return jsonify({
            'success': True,
            'wordcloud_url': f"/processed_data/batch/{os.path.basename(batch_path)}/word/wordcloud_{employee_id}.png",
            'wordcloud_info': metadata['wordcloud_generation_info']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'워드클라우드 재생성 실패: {str(e)}'}), 500
```

#### 8. get_batch_list 함수 업데이트
```python
@app.route('/get_batch_list')
def get_batch_list():
    """배치 처리 결과 목록 반환 - 연월일 정보 포함"""
    try:
        processed_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../processed_data"))
        batches = []
        
        batch_dir = os.path.join(processed_data_dir, "batch")
        if os.path.exists(batch_dir):
            for item in os.listdir(batch_dir):
                item_path = os.path.join(batch_dir, item)
                if os.path.isdir(item_path) and item.startswith('batch_'):
                    summary_path = os.path.join(item_path, 'tdata', 'batch_summary.json')
                    
                    if os.path.exists(summary_path):
                        try:
                            with open(summary_path, 'r', encoding='utf-8') as f:
                                summary = json.load(f)
                            
                            # 배치 정보 추출
                            batch_name = item
                            # 형식: batch_YYYYMMDD_N
                            parts = batch_name.split('_')
                            if len(parts) >= 3:
                                date_str = parts[1]
                                number_str = parts[2]
                                display_time = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} (Batch {number_str})"
                                display_name = f"{display_time} {batch_name}"
                            else:
                                display_name = batch_name
                            
                            batches.append({
                                'name': display_name,
                                'original_name': batch_name,
                                'path': item_path,
                                'employee_count': summary.get('batch_info', {}).get('unique_employees', 0),
                                'created_at': summary.get('batch_info', {}).get('created_at', '').replace('Z', '').split('T')[0]
                            })
                        except:
                            continue
        
        batches.sort(key=lambda x: x['created_at'], reverse=True)
        
        return jsonify({'batches': batches})
        
    except Exception as e:
        return jsonify({'error': f'배치 목록 로드 실패: {str(e)}'}), 500
```

#### 9. get_batch_metadata 함수에서 워드클라우드 URL 생성 로직 업데이트
```python
wordcloud_url = None
if wordcloud_path:
    # wordcloud_path가 "/outputs/filename.png" 형식이면 그대로 사용
    if wordcloud_path.startswith('/outputs/'):
        wordcloud_url = wordcloud_path
    # wordcloud_path가 "word/filename.png" 형식이면 배치 경로에 맞게 생성
    elif wordcloud_path.startswith('word/'):
        batch_name = os.path.basename(batch_path)
        wordcloud_url = f"/processed_data/batch/{batch_name}/{wordcloud_path}"
    # 그 외의 경우는 파일명만 추출하여 "/outputs/filename.png"로 생성
    else:
        wordcloud_url = '/outputs/' + os.path.basename(wordcloud_path)
```

## 실행 계획

### 1. 파일 백업
```bash
cd wordcloud_project
cp web/app.py web/app.py.backup_$(date +%Y%m%d_%H%M%S)
```

### 2. 코드 수정
위의 수정 사항을 web/app.py에 적용합니다.

### 3. 폴더 구조 생성 테스트
```bash
cd wordcloud_project
python -c "
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DATA_DIR = 'processed_data'

current_date = datetime.now().strftime('%Y%m%d')
batch_num = 0
while True:
    batch_dir = os.path.abspath(os.path.join(PROJECT_ROOT, PROCESSED_DATA_DIR, 'batch', f'batch_{current_date}_{batch_num}'))
    if not os.path.exists(batch_dir):
        break
    batch_num += 1
os.makedirs(batch_dir, exist_ok=True)
tdata_dir = os.path.join(batch_dir, 'tdata')
word_dir = os.path.join(batch_dir, 'word')
os.makedirs(tdata_dir, exist_ok=True)
os.makedirs(word_dir, exist_ok=True)
print(f'생성된 폴더 구조: {batch_dir}')
"
```

### 4. Flask 앱 테스트
```bash
cd wordcloud_project
python -c "
import sys
import os
sys.path.append(os.path.abspath('.'))
sys.path.append(os.path.abspath('./web'))

from web.app import app
print('Flask 앱이 성공적으로 로드되었습니다.')
"
```

### 5. 웹 애플리케이션 실행
```bash
cd wordcloud_project
python web/app.py
```

## 개선 효과

### 1. 폴더 구조 명확성 향상
- 날짜별로 분류되고 번호가 증가하는 구조로 쉽게 관리 가능
- 데이터와 이미지가 별도 폴더에 저장되어 검색과 관리가 용이

### 2. 중복 방지
- 번호가 증가하는 방식으로 중복 폴더 생성 방지
- 날짜별로 관리되어 같은 날에 여러 배치 처리 가능

### 3. 코드 일관성 향상
- 모든 함수에서 폴더 구조가 동일하게 사용되어 유지보수가 쉬워짐

### 4. 사용자 경험 개선
- 웹 페이지에서 배치 목록이 더욱 직관적으로 표시됨
- 다운로드시 폴더 구조가 유지되어 추후 검토가 용이