# 통합데이터 처리 시스템 모듈화 체크리스트

## Phase 1: 핵심 모듈 구현 (2일)

### Step 1: integrated_analysis.py 생성
- [x] `wordcloud_project/modules/integrated_analysis.py` 파일 생성
- [x] `calculate_consolidated_analysis` 함수 구현
- [x] 필요한 import 문 추가 (collections, datetime, modules.leadership_analysis 등)
- [x] 함수 단위 테스트 작성 (`test_integrated_analysis.py`)
- [x] U011 직원 데이터로 통합 분석 결과 확인 (신뢰도 0.639 여부)

### Step 2: integrated_data_manager.py 생성
- [x] `wordcloud_project/modules/integrated_data_manager.py` 파일 생성
- [x] `IntegratedDataManager` 클래스 구현
- [x] `__init__` 메소드 구현 (processed_data_dir 인수)
- [x] `create_employee_metadata` 메소드 구현
- [x] `save_employee_metadata` 메소드 구현 (배치 처리/단일 처리 지원)
- [x] `load_employee_metadata` 메소드 구현
- [x] `update_employee_metadata` 메소드 구현 (데이터 무결성 해시 재계산)
- [x] 단위 테스트 작성 (`test_integrated_data_manager.py`)

## Phase 2: Flask 앱 수정 (1일)

### Step 3: app.py에서 모듈 사용
- [x] 기존의 `calculate_consolidated_analysis` 함수 삭제
- [x] `modules.integrated_analysis`에서 `calculate_consolidated_analysis` import 추가
- [x] `modules.integrated_data_manager`에서 `IntegratedDataManager` import 추가
- [x] `IntegratedDataManager` 인스턴스 생성 (PROCESSED_DATA_DIR_PATH 사용)
- [x] `/process_batch_metadata` 엔드포인트에서 integrated_analysis 모듈 사용으로 변경
- [x] 통합데이터 관리 기능에 integrated_data_manager 사용

## Phase 3: 테스트와 검증 (1일)

### Step 4: 기존 데이터로 테스트
- [x] U011 직원 데이터를 사용한 통합 분석 결과 확인 (신뢰도 0.639)
- [x] 여러 직원의 통합데이터 생성/수정/검색 테스트 (단위 테스트 통과)
- [x] 워드클라우드 생성과 통합 분석의 연계성 검증 (단위 테스트 통과)
- [ ] 배치 처리의 일관성 검증
- [ ] 웹 인터페이스에서의 통합데이터 처리 동작 확인
- [ ] 실제 사용자 시나리오 테스트

## 추가 테스트 케이스

### 통합 분석 일관성 확인
- [ ] 단일 처리(`/generate_metadata`)와 배치 처리(`/process_batch_metadata`)의 결과 비교
- [ ] 여러 직원 데이터에 대한 통합 분석 결과 검증
- [ ] 가중 평균 기반 신뢰도 계산의 정확성 확인

### 통합데이터 관리 기능
- [ ] 통합데이터 파일 생성/수정/삭제 테스트
- [ ] 데이터 무결성 해시 확인
- [ ] 배치 폴더 구조에 대한 통합데이터 관리

### 웹 인터페이스
- [ ] 워드클라우드 생성과 통합 분석 결과의 표시
- [ ] 평가별 상세 정보 표시
- [ ] 통계 정보의 정확성

## 최종 검증

### 기능 테스트
- [ ] 각 모듈의 단위 테스트 실행
- [ ] 통합 테스트로 전체 시스템 동작 확인
- [ ] 모든 API 엔드포인트의 정상 응답

### 성능 테스트
- [ ] 대량 데이터 처리의 성능 확인
- [ ] 메모리 사용과 응답 시간 측정
- [ ] 배치 처리의 효율성

## 문제 해결

### 예상 문제 1: 의존성 문제
- [ ] 필요한 import 문 추가 확인
- [ ] 모듈 경로 문제 해결

### 예상 문제 2: 데이터 호환성
- [ ] 기존 통합데이터 파일의 구조 유지
- [ ] 필요한 경우 통합데이터 구조 업데이트

### 예상 문제 3: Flask 앱 변경
- [ ] 기존 기능의 정상 동작 확인
- [ ] 웹 인터페이스의 레이아웃과 기능 유지

---

## 완료 표시

- ✅ 완료
- 🔄 진행 중
- ❌ 미완료

## 주요 산출물

1. `wordcloud_project/modules/integrated_analysis.py`
2. `wordcloud_project/modules/integrated_data_manager.py`
3. `wordcloud_project/tests/test_integrated_analysis.py`
4. `wordcloud_project/tests/test_integrated_data_manager.py`
5. 수정된 `wordcloud_project/web/app.py`
6. 테스트 결과 문서