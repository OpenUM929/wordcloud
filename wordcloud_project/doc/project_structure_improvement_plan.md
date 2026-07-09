# 프로젝트 구조 개선 계획

## 목표
1. 테스트 파일을 주제별로 분류하여 tests 폴더에 이동
2. 다양한 기능에 맞춰 폴더 구조 개선
3. app.py를 800라인 이내로 리팩토링
4. 개발 체크리스트 상세 정리

## Phase 5: 프로젝트 구조 정리 (2일)

### Step 1: 테스트 파일 분류 및 이동 (1일)

#### 현재 테스트 파일 목록
```
wordcloud_project/
├── test_actual_data.py
├── test_api_quick.py
├── test_api_simple.py
├── test_batch_dir.py
├── test_confidence_calculation.py
├── test_consolidated_analysis.py
├── test_encoding.py
├── test_flask_app_with_context.py
├── test_improved_wordcloud.py
├── test_metadata_read.py
├── test_qwen_model.py
├── test_server_status.py
├── test_tdata_file.py
├── test_user_feedback_scenario.py
├── test_web_api.py
├── test_web_page.py
├── test_wordcloud_endpoints.py
├── test_wordcloud_file_existence.py
├── test_wordcloud_page.html
├── test_wordcloud_serve.py
├── test_wordcloud_serve2.py
├── test_wordcloud_serve3.py
├── tests/
│   ├── test_integrated_analysis.py
│   └── test_integrated_data_manager.py
```

#### 분류 기준
| 카테고리 | 파일명 |
|---------|--------|
| **통합 분석** | test_actual_data.py, test_consolidated_analysis.py, test_confidence_calculation.py |
| **API 테스트** | test_api_quick.py, test_api_simple.py, test_web_api.py, test_wordcloud_endpoints.py |
| **통합데이터** | test_metadata_read.py, test_tdata_file.py, tests/test_integrated_analysis.py, tests/test_integrated_data_manager.py |
| **배치 처리** | test_batch_dir.py |
| **워드클라우드** | test_improved_wordcloud.py, test_wordcloud_file_existence.py, test_wordcloud_page.html, test_wordcloud_serve.py, test_wordcloud_serve2.py, test_wordcloud_serve3.py |
| **Flask 앱** | test_flask_app_with_context.py, test_web_page.py |
| **서버 상태** | test_server_status.py |
| **인코딩** | test_encoding.py |
| **사용자 피드백** | test_user_feedback_scenario.py |
| **모델 테스트** | test_qwen_model.py |

#### 분류 결과 폴더 구조
```
wordcloud_project/
├── tests/
│   ├── __init__.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_actual_data.py
│   │   ├── test_consolidated_analysis.py
│   │   └── test_confidence_calculation.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── test_api_quick.py
│   │   ├── test_api_simple.py
│   │   ├── test_web_api.py
│   │   └── test_wordcloud_endpoints.py
│   ├── metadata/
│   │   ├── __init__.py
│   │   ├── test_metadata_read.py
│   │   ├── test_tdata_file.py
│   │   ├── test_integrated_analysis.py
│   │   └── test_integrated_data_manager.py
│   ├── batch/
│   │   ├── __init__.py
│   │   └── test_batch_dir.py
│   ├── wordcloud/
│   │   ├── __init__.py
│   │   ├── test_improved_wordcloud.py
│   │   ├── test_wordcloud_file_existence.py
│   │   ├── test_wordcloud_page.html
│   │   ├── test_wordcloud_serve.py
│   │   ├── test_wordcloud_serve2.py
│   │   └── test_wordcloud_serve3.py
│   ├── flask/
│   │   ├── __init__.py
│   │   ├── test_flask_app_with_context.py
│   │   └── test_web_page.py
│   ├── server/
│   │   ├── __init__.py
│   │   └── test_server_status.py
│   ├── encoding/
│   │   ├── __init__.py
│   │   └── test_encoding.py
│   ├── user_feedback/
│   │   ├── __init__.py
│   │   └── test_user_feedback_scenario.py
│   └── models/
│       ├── __init__.py
│       └── test_qwen_model.py
```

### Step 2: 기능별 폴더 구조 개선 (1일)

#### 현재 폴더 구조 문제점
```
wordcloud_project/
├── [루트 폴더에 분산된 파일들]
├── modules/          # 모듈 파일
├── tests/            # 테스트 파일
├── configs/          # 설정 파일
├── data_set/         # 데이터 셋
├── doc/              # 문서
├── inputs/           # 입력 데이터
├── logs/             # 로그
├── outputs/          # 출력 데이터
├── processed_data/   # 처리된 데이터
├── utils/            # 유틸리티
├── venv/             # 가상 환경
└── web/              # 웹 앱
```

#### 개선된 폴더 구조
```
wordcloud_project/
├── src/
│   ├── core/         # 핵심 기능 모듈
│   │   ├── __init__.py
│   │   ├── integrated_analysis.py
│   │   ├── integrated_data_manager.py
│   │   ├── nlp_analysis.py
│   │   ├── wordcloud_generator.py
│   │   ├── sarcasm_analysis.py
│   │   ├── profanity_filter.py
│   │   ├── leadership_analysis.py
│   │   └── emotion_analysis.py
│   ├── services/     # 비즈니스 로직 서비스
│   │   ├── __init__.py
│   │   ├── integrated_data_service.py
│   │   ├── batch_service.py
│   │   ├── wordcloud_service.py
│   │   └── analysis_service.py
│   ├── routes/       # Flask 라우터
│   │   ├── __init__.py
│   │   ├── integrated_data_routes.py
│   │   ├── batch_routes.py
│   │   ├── wordcloud_routes.py
│   │   ├── analysis_routes.py
│   │   └── ui_routes.py
│   ├── utils/        # 유틸리티 함수
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   ├── state_manager.py
│   │   └── config_manager.py
│   └── web/          # 웹 앱
│       ├── __init__.py
│       ├── app.py
│       ├── templates/
│       └── static/
├── tests/            # 테스트 파일 (카테고리별로 분류)
├── configs/          # 설정 파일
├── data/
│   ├── raw/          # 원본 데이터
│   ├── processed/    # 처리된 데이터
│   └── datasets/     # 학습 데이터 셋
├── docs/             # 문서
├── logs/             # 로그
├── outputs/          # 출력 데이터
├── temp/             # 임시 파일
├── .env              # 환경 변수
├── requirements.txt  # 의존성
└── README.md         # 프로젝트 설명
```

### Step 3: app.py 리팩토링 (800라인 이내)

#### 리팩토링 전 app.py 구조
```python
# 현재 app.py는 ~2000라인으로 매우 비대
- 모든 Flask 라우터 함수 (~20개)
- 각 라우터 내의 복잡한 비즈니스 로직
- 전역 변수와 상태 관리
```

#### 리팩토링 후 app.py 구조
```python
# app.py (예상 ~500라인)
import sys
import os
from sys import path
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_from_directory, session
import json
import uuid
import hashlib
from datetime import datetime
import torch

# 환경 설정
path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

# 서비스와 라우터 import
from src.services.integrated_data_service import MetadataService
from src.services.batch_service import BatchService
from src.services.wordcloud_service import WordCloudService
from src.services.analysis_service import AnalysisService
from src.routes.integrated_data_routes import integrated_data_routes
from src.routes.batch_routes import batch_routes
from src.routes.wordcloud_routes import wordcloud_routes
from src.routes.analysis_routes import analysis_routes
from src.routes.ui_routes import ui_routes

# 앱 초기화
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# 서비스 인스턴스 생성
integrated_data_service = MetadataService()
batch_service = BatchService()
wordcloud_service = WordCloudService()
analysis_service = AnalysisService()

# 라우터 등록
app.register_blueprint(integrated_data_routes)
app.register_blueprint(batch_routes)
app.register_blueprint(wordcloud_routes)
app.register_blueprint(analysis_routes)
app.register_blueprint(ui_routes)

# 기본 라우터
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)
```

### Step 4: 라우터 모듈화 (Blueprints 사용)

#### integrated_data_routes.py 예시
```python
from flask import Blueprint, request, jsonify, send_from_directory
from src.services.integrated_data_service import MetadataService

integrated_data_routes = Blueprint('metadata', __name__)
integrated_data_service = MetadataService()

@integrated_data_routes.route('/generate_metadata', methods=['POST'])
def generate_metadata():
    try:
        return integrated_data_service.generate_metadata(request.json)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@integrated_data_routes.route('/get_batch_metadata')
def get_batch_metadata():
    try:
        return integrated_data_service.get_batch_metadata(request.args)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 추가 통합데이터 관련 라우터...
```

### Step 5: 서비스 모듈화

#### integrated_data_service.py 예시
```python
class MetadataService:
    def __init__(self):
        self.integrated_data_manager = IntegratedDataManager()
    
    def generate_metadata(self, data):
        # 통합데이터 생성 로직
        pass
    
    def get_batch_metadata(self, args):
        # 배치 통합데이터 조회 로직
        pass
    
    # 추가 통합데이터 관리 메서드...
```

## Phase 6: 개발 체크리스트 상세 정리 (1일)

### 상세 체크리스트
1. **테스트 파일 분류**
   - 각 테스트 파일의 카테고리 확인
   - 폴더 생성과 파일 이동
   - __init__.py 파일 생성
   - import 경로 수정

2. **폴더 구조 개선**
   - src/ 폴더 생성
   - core, services, routes, utils 폴더 생성
   - 기존 modules 파일 이동과 import 경로 수정
   - web 폴더 구조 개선

3. **app.py 리팩토링**
   - Blueprint 기반 라우터 분리
   - 서비스 계층 구현
   - 전역 변수와 상태 관리 개선
   - 코드 라인수 확인 (<=800라인)

4. **기능 테스트**
   - 각 라우터 함수 테스트
   - 서비스 메서드 테스트
   - 모듈 간 연동 테스트
   - 전체 시스템 통합 테스트

5. **문서화**
   - 프로젝트 구조 설명
   - 각 모듈 기능 설명
   - API 문서 생성
   - 테스트 파일 설명 메뉴얼

## 결론

이 개선 계획을 통해 프로젝트 구조가 더욱 체계화되고, app.py가 800라인 이내로 리팩토링될 예정입니다. 각 phase는 순차적으로 진행하며, 매 단계마다 테스트를 통해 안정성을 확인해야 합니다.