# 통합데이터 처리 시스템 모듈화 계획 문서

## 1. 현재 시스템 분석

### 1.1 시스템 구조 현황
- **플랫폼**: Flask 기반 웹 애플리케이션
- **주요 기능**: 통합데이터 생성, 배치 처리, 워드클라우드 생성, 분석 결과 표시
- **기존 모듈**: `nlp_analysis`, `emotion_analysis`, `leadership_analysis`, `profanity_filter`, `sarcasm_analysis`, `wordcloud_generator`, `data_preprocessing`

### 1.2 통합데이터 처리의 문제점

#### 1.2.1 통합 분석 로직 중복 (가장 심각한 문제)
- **2가지 다른 구현 방식**:
  1. `calculate_consolidated_analysis` 함수 (app.py): 개별 평가의 감정 결과를 가중 평균하는 방식
  2. `/process_batch_metadata` 엔드포인트 내 코드: 모든 평가를 합쳐서 한 번 감정 분석하는 방식
- **결과 불일치 예시**:
  - U011 직원 데이터:
    - `calculate_consolidated_analysis`: 신뢰도 0.639 (63.9%)
    - `/process_batch_metadata`: 신뢰도 0.23 (23.0%)

#### 1.2.2 모듈화 부족
- 통합데이터 처리가 Flask 앱에 강하게 결합되어 재사용 불가
- 통합 분석 기능이 함수로 분리되어 있으나 모듈화되지 않음
- 통합데이터 유지 관리 기능이 없음

#### 1.2.3 테스트 어려움
- 함수 단위 테스트가 어려움 (Flask 앱과의 결합성 높음)
- 통합 분석 결과의 일관성 검증이 힘듦

## 2. 모듈화 계획

### 2.1 목표
1. **단일 소스 원칙**: 모든 통합데이터 통합 분석을 단일 모듈로 관리
2. **재사용성**: 통합데이터 처리 기능을 독립 모듈로 제공
3. **일관성**: 모든 경로에서 동일한 통합 분석 로직 사용
4. **테스트ability**: 함수 단위 테스트 용이성 확보
5. **유지보수성**: 모듈화로 인한 코드 관리 용이성

### 2.2 모듈 구조 설계

#### 2.2.1 핵심 모듈: integrated_analysis.py
```
├── integrated_analysis.py
│   ├── calculate_consolidated_analysis(evaluations)  # 통합 분석 계산
│   └── [보조 함수들]
```

**기능**:
- 평가 리스트의 통합 분석 계산 (단일 소스)
- 가중 평균 기반 신뢰도 계산
- 감정, 리더십, 욕설, 단어 빈도 분석 결과 통합

**메소드 구조**:
```python
def calculate_consolidated_analysis(evaluations):
    """
    평가 리스트의 통합 분석 계산
    
    Args:
        evaluations (list): 평가 데이터 리스트
        
    Returns:
        dict: 통합 분석 결과
    """
    # 처리 로직...
```

#### 2.2.2 통합데이터 관리 모듈: integrated_data_manager.py
```
├── integrated_data_manager.py
│   ├── IntegratedDataManager 클래스
│   │   ├── __init__(processed_data_dir)
│   │   ├── create_employee_metadata()
│   │   ├── save_employee_metadata()
│   │   ├── load_employee_metadata()
│   │   └── update_employee_metadata()
```

**기능**:
- 통합데이터 생성, 저장, 검색, 수정 관리
- 배치 처리와 단일 처리 모두 지원
- 데이터 무결성 해시 관리

#### 2.2.3 의존성 관계
```
app.py
├── integrated_data_manager.py
│   └── integrated_analysis.py
│       ├── leadership_analysis.py
│       └── [기타 분석 모듈들]
```

## 3. 구현 단계

### Phase 1: 핵심 모듈 구현 (1-2일)

#### 3.1 Step 1: integrated_analysis.py 생성
- 기존 app.py의 calculate_consolidated_analysis 함수 추출
- 독립 모듈로 재구현
- 필요한 의존성 import 추가
- 함수 단위 테스트 작성

**작업 내용**:
```
1. wordcloud_project/modules/integrated_analysis.py 파일 생성
2. calculate_consolidated_analysis 함수 구현
3. 필요한 import 문 추가
4. 함수 단위 테스트 작성 (test_integrated_analysis.py)
```

#### 3.2 Step 2: integrated_data_manager.py 생성
- IntegratedDataManager 클래스 구현
- 통합데이터 생성, 저장, 검색, 수정 메소드 구현
- 단위 테스트 작성

**작업 내용**:
```
1. wordcloud_project/modules/integrated_data_manager.py 파일 생성
2. IntegratedDataManager 클래스 구현
3. 단위 테스트 작성 (test_integrated_data_manager.py)
```

### Phase 2: Flask 앱 수정 (1일)

#### 3.3 Step 3: app.py에서 모듈 사용
- 기존의 calculate_consolidated_analysis 함수 삭제
- /process_batch_metadata 엔드포인트에서 integrated_analysis 모듈 사용
- 통합데이터 관리 기능에 integrated_data_manager 사용

**수정 부분**:
```python
# app.py
from modules.integrated_analysis import calculate_consolidated_analysis
from modules.integrated_data_manager import IntegratedDataManager

# 통합데이터 관리 인스턴스 생성
integrated_data_manager = IntegratedDataManager(PROCESSED_DATA_DIR_PATH)

@app.route('/process_batch_metadata', methods=['POST'])
def process_batch_metadata():
    # ... 기존 코드 ...
    
    # 통합 분석 계산 - 모듈 사용
    metadata["consolidated_analysis"] = calculate_consolidated_analysis(metadata["evaluations"])
    
    # ... 기존 코드 ...
```

### Phase 3: 테스트와 검증 (1일)

#### 3.4 Step 4: 기존 데이터로 테스트
- U011 직원 데이터를 사용한 통합 분석 결과 확인
- 배치 처리의 일관성 검증
- 웹 인터페이스에서의 결과 확인

**테스트 케이스**:
```
1. U011 직원의 통합 분석 결과 확인 (신뢰도 0.639 여부)
2. 여러 직원의 통합데이터 생성/수정/검색 테스트
3. 워드클라우드 생성과 통합 분석의 연계성 검증
```

## 4. 예상 이점

### 4.1 기능적 이점
- **일관성**: 모든 경로에서 동일한 통합 분석 로직
- **재사용성**: 다른 프로젝트나 시스템에서도 통합데이터 처리 기능 사용
- **테스트성**: 함수 단위 테스트로 동작 검증 용이

### 4.2 유지보수 이점
- **단일 소스**: 통합 분석 로직을 하나의 파일에서 관리
- **모듈화**: 기능별로 분리되어 변경 영향 범위 최소화
- **문서화**: 각 모듈의 역할과 사용 방법 명확화

## 5. 리스크 관리

### 5.1 기존 코드의 의존성 문제
- **대응**: 모든 필요한 import와 의존성 관계를 명확히 정의
- **테스트**: 각 단계마다 기존 기능의 정상 동작 확인

### 5.2 데이터 호환성
- **대응**: 기존 통합데이터 파일의 구조가 변경되지 않도록 유지
- **마이그레이션**: 필요한 경우 통합데이터 구조 업데이트 스크립트 작성

## 6. 최종 검증

### 6.1 기능 테스트
- 각 모듈의 단위 테스트 실행
- 통합 테스트로 전체 시스템 동작 확인

### 6.2 성능 테스트
- 대량 데이터 처리의 성능 확인
- 메모리 사용과 응답 시간 측정

### 6.3 사용자 테스트
- 웹 인터페이스에서의 통합데이터 처리 동작 확인
- 실제 사용자 시나리오 테스트

---

## 계획 실행 일정

| 단계 | 작업 내용 | 예상 일정 |
|------|-----------|----------|
| Phase 1 | integrated_analysis.py 구현 | 1일 |
| Phase 1 | integrated_data_manager.py 구현 | 1일 |
| Phase 2 | app.py 수정 | 1일 |
| Phase 3 | 테스트와 검증 | 1일 |
| **총합** | **모듈화 완료** | **4일** |