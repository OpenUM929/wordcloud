# 개발 체크리스트 (상세)

## 목표
- 프로젝트 구조 개선 완료
- 테스트 파일 분류 및 문서화
- app.py를 800라인 이내로 리팩토링

## Phase 5: 프로젝트 구조 정리 (2일)

### Step 1: 테스트 파일 분류 및 이동 (1일)

#### 테스트 파일 분류 카테고리
1. **통합 분석 테스트**
   - [ ] test_actual_data.py → tests/integration/
   - [ ] test_consolidated_analysis.py → tests/integration/
   - [ ] test_confidence_calculation.py → tests/integration/

2. **API 테스트**
   - [ ] test_api_quick.py → tests/api/
   - [ ] test_api_simple.py → tests/api/
   - [ ] test_web_api.py → tests/api/
   - [ ] test_wordcloud_endpoints.py → tests/api/

3. **통합데이터 테스트**
   - [ ] test_metadata_read.py → tests/metadata/
   - [ ] test_tdata_file.py → tests/metadata/
   - [ ] tests/test_integrated_analysis.py → tests/metadata/
   - [ ] tests/test_integrated_data_manager.py → tests/metadata/

4. **배치 처리 테스트**
   - [ ] test_batch_dir.py → tests/batch/

5. **워드클라우드 테스트**
   - [ ] test_improved_wordcloud.py → tests/wordcloud/
   - [ ] test_wordcloud_file_existence.py → tests/wordcloud/
   - [ ] test_wordcloud_page.html → tests/wordcloud/
   - [ ] test_wordcloud_serve.py → tests/wordcloud/
   - [ ] test_wordcloud_serve2.py → tests/wordcloud/
   - [ ] test_wordcloud_serve3.py → tests/wordcloud/

6. **Flask 앱 테스트**
   - [ ] test_flask_app_with_context.py → tests/flask/
   - [ ] test_web_page.py → tests/flask/

7. **서버 상태 테스트**
   - [ ] test_server_status.py → tests/server/

8. **인코딩 테스트**
   - [ ] test_encoding.py → tests/encoding/

9. **사용자 피드백 테스트**
   - [ ] test_user_feedback_scenario.py → tests/user_feedback/

10. **모델 테스트**
    - [ ] test_qwen_model.py → tests/models/

#### 분류 작업 세부 체크리스트
1. [ ] 각 카테고리별 폴더 생성 (tests/integration, tests/api, 등)
2. [ ] 각 폴더에 __init__.py 파일 생성
3. [ ] 테스트 파일 이동
4. [ ] 각 테스트 파일의 import 경로 수정
5. [ ] 테스트 파일 설명 메뉴얼 작성 (tests/README.md)
6. [ ] pytest 실행으로 모든 테스트 통과 확인

### Step 2: 기능별 폴더 구조 개선 (1일)

#### 폴더 구조 개선
1. **src/ 폴더 생성**
   - [ ] src/core/ 폴더 생성 (핵심 기능 모듈)
   - [ ] src/services/ 폴더 생성 (비즈니스 로직 서비스)
   - [ ] src/routes/ 폴더 생성 (Flask 라우터)
   - [ ] src/utils/ 폴더 생성 (유틸리티 함수)
   - [ ] src/web/ 폴더 생성 (웹 앱)

2. **기존 파일 이동**
   - [ ] modules/integrated_analysis.py → src/core/
   - [ ] modules/integrated_data_manager.py → src/core/
   - [ ] modules/nlp_analysis.py → src/core/
   - [ ] modules/wordcloud_generator.py → src/core/
   - [ ] modules/sarcasm_analysis.py → src/core/
   - [ ] modules/profanity_filter.py → src/core/
   - [ ] modules/leadership_analysis.py → src/core/
   - [ ] modules/emotion_analysis.py → src/core/
   - [ ] utils/logger.py → src/utils/

3. **새 서비스 모듈 생성**
   - [ ] src/services/integrated_data_service.py 생성
   - [ ] src/services/batch_service.py 생성
   - [ ] src/services/wordcloud_service.py 생성
   - [ ] src/services/analysis_service.py 생성

4. **새 라우터 모듈 생성**
   - [ ] src/routes/integrated_data_routes.py 생성 (Blueprint)
   - [ ] src/routes/batch_routes.py 생성 (Blueprint)
   - [ ] src/routes/wordcloud_routes.py 생성 (Blueprint)
   - [ ] src/routes/analysis_routes.py 생성 (Blueprint)
   - [ ] src/routes/ui_routes.py 생성 (Blueprint)

5. **유틸리티 모듈 생성**
   - [ ] src/utils/state_manager.py 생성 (처리 상태 관리)
   - [ ] src/utils/config_manager.py 생성 (설정 관리)

#### 파일 경로 수정
1. [ ] 모든 모듈의 import 경로 수정
2. [ ] app.py의 import 경로 수정
3. [ ] 테스트 파일의 import 경로 수정
4. [ ] requirements.txt 확인 (필요한 패키지 추가)

## Phase 6: app.py 리팩토링 (800라인 이내)

### 리팩토링 목표
- 현재 ~2000라인 → 800라인 이내
- Blueprint 기반 라우터 분리
- 서비스 계층 구현
- 전역 변수와 상태 관리 개선

### 리팩토링 체크리스트
1. **기본 설정**
   - [ ] Flask 앱 초기화 코드 정리
   - [ ] 환경 변수 로드 코드 정리
   - [ ] 서비스 인스턴스 생성

2. **Blueprint 라우터 등록**
   - [ ] integrated_data_routes 블루프린트 등록
   - [ ] batch_routes 블루프린트 등록
   - [ ] wordcloud_routes 블루프린트 등록
   - [ ] analysis_routes 블루프린트 등록
   - [ ] ui_routes 블루프린트 등록

3. **기본 라우터**
   - [ ] 메인 페이지 라우터
   - [ ] 설정 페이지 라우터
   - [ ] 결과 페이지 라우터

4. **리팩토링 확인**
   - [ ] 코드 라인수 확인 (<=800라인)
   - [ ] 모든 import 경로 정확성
   - [ ] Flask 앱 정상 실행 확인

## Phase 7: 기능 테스트 (1일)

### 통합 테스트
1. [ ] 각 라우터 함수 테스트
2. [ ] 서비스 메서드 테스트
3. [ ] 모듈 간 연동 테스트
4. [ ] 전체 시스템 통합 테스트

### 단위 테스트
1. [ ] src/core/ 모듈 테스트
2. [ ] src/services/ 모듈 테스트
3. [ ] src/routes/ 모듈 테스트
4. [ ] src/utils/ 모듈 테스트

### 실제 데이터 테스트
1. [ ] U011 직원 데이터로 통합 분석 결과 확인
2. [ ] 배치 처리 기능 테스트
3. [ ] 워드클라우드 생성 기능 테스트

## Phase 8: 문서화 (1일)

### 프로젝트 문서
1. [ ] README.md 업데이트 (프로젝트 설명, 설치 방법, 사용 방법)
2. [ ] CONTRIBUTING.md 작성 (기여 가이드)
3. [ ] CHANGELOG.md 작성 (변경 기록)

### 모듈 문서
1. [ ] src/core/ 각 모듈 기능 설명
2. [ ] src/services/ 각 서비스 기능 설명
3. [ ] src/routes/ 각 라우터 설명
4. [ ] tests/ 폴더 문서화 (테스트 파일 설명 메뉴얼)

### API 문서
1. [ ] Flask API 문서 생성 (Swagger UI 또는 Postman)
2. [ ] 각 엔드포인트 설명 및 예제
3. [ ] 요청/응답 포맷 정의

## Phase 9: 최종 검증 (0.5일)

### 최종 테스트
1. [ ] 모든 테스트 실행 (pytest -v)
2. [ ] 코드 카바리지 확인 (pytest-cov)
3. [ ] 성능 테스트 (대량 데이터 처리)

### 코드 리뷰
1. [ ] PEP8 준수 확인
2. [ ] 코드 복잡도 확인
3. [ ] 보안 취약점 검토

### 배포 준비
1. [ ] requirements.txt 최신화
2. [ ] .env 파일 템플릿 생성
3. [ ] Dockerfile 생성 (옵션)

## 개발 일정

| Phase | 기간 | 주요 작업 |
|-------|------|-----------|
| Phase 5 | 1일 | 테스트 파일 분류 및 이동 |
| Phase 6 | 1일 | 기능별 폴더 구조 개선 |
| Phase 7 | 1일 | app.py 리팩토링 (800라인 이내) |
| Phase 8 | 1일 | 기능 테스트 |
| Phase 9 | 0.5일 | 문서화 |
| Phase 10 | 0.5일 | 최종 검증 |

## 성공 기준

1. **테스트 분류 완료**: 모든 테스트 파일이 카테고리별로 분류되고, tests 폴더에 정리됨
2. **폴더 구조 개선**: src/ 폴더 구조가 완성되고, 모든 모듈이 적절한 위치에 배치됨
3. **app.py 리팩토링**: 800라인 이내로 리팩토링되어, 가독성과 유지보수성이 향상됨
4. **기능 검증**: 모든 테스트가 통과하고, 실제 데이터로의 테스트가 성공함
5. **문서화**: 프로젝트 구조, 각 모듈 기능, API 문서가 완성됨

## 주의 사항

1. **단계별 진행**: 각 phase를 순차적으로 진행하며, 매 단계마다 테스트를 통해 안정성을 확인
2. **import 경로**: 파일 이동시 import 경로를 꼭 수정해야 함
3. **테스트 통과**: 모든 테스트가 통과되어야 다음 phase로 진행
4. **백업**: 중요한 파일을 수정하기 전에 백업을 생성 (Git 사용 권장)