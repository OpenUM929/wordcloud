# 인사 평가 감정 분석 시스템 구현 계획

## 시스템 개요
인사 평가 데이터를 기반으로 감정 분석을 수행하여 평가자의 피드백 패턴을 시각화하고 추세를 분석하는 웹 기반 시스템.

## 공통 모듈: 통합데이터 관리 시스템
- [ ] **IntegratedDataManager 클래스**
  - **세부 기능 M.1: 통합데이터 생성 (Create)**
    - **함수 명칭**: `create_metadata(session_id: str, initial_data: dict) -> dict`
    - **구현 방법**:
      1. 세션 ID 기반 통합데이터 구조 초기화
      2. 타임스탬프 및 버전 정보 추가
      3. 기본 필드 (target_employee_id, evaluation_document 등) 생성
      4. 데이터 유효성 검증 및 기본값 설정
      5. 반환 값: 생성된 통합데이터 딕셔너리
  - **세부 기능 M.2: 통합데이터 조회 (Read)**
    - **함수 명칭**: `get_metadata(session_id: str, field_path: str = None) -> dict`
    - **구현 방법**:
      1. 세션 ID로 통합데이터 파일 로드
      2. 특정 필드 경로가 주어지면 해당 부분만 반환
      3. 캐싱을 통한 성능 최적화
      4. 파일 존재 여부 및 무결성 검증
      5. 반환 값: 통합데이터 또는 특정 필드 값
  - **세부 기능 M.3: 통합데이터 업데이트 (Update)**
    - **함수 명칭**: `update_metadata(session_id: str, updates: dict, step: str) -> bool`
    - **구현 방법**:
      1. 기존 통합데이터 로드
      2. 업데이트할 필드들을 병합
      3. 처리 단계(step) 기록 및 타임스탬프 업데이트
      4. 변경 이력(revision history) 유지
      5. 반환 값: 업데이트 성공 여부
  - **세부 기능 M.4: 통합데이터 삭제 (Delete)**
    - **함수 명칭**: `delete_metadata(session_id: str, field_path: str = None) -> bool`
    - **구현 방법**:
      1. 전체 통합데이터 삭제 또는 특정 필드만 삭제
      2. 삭제 전 백업 생성
      3. 관련 파일 정리 (분석 결과 파일들)
      4. 삭제 로그 기록
      5. 반환 값: 삭제 성공 여부
  - **세부 기능 M.5: 통합데이터 검증**
    - **함수 명칭**: `validate_metadata(metadata: dict) -> dict`
    - **구현 방법**:
      1. 필수 필드 존재 여부 검증
      2. 데이터 타입 및 값 범위 검증
      3. 참조 무결성 확인 (파일 경로 존재 여부)
      4. 스키마 준수성 검증
      5. 반환 값: 검증 결과 (valid: bool, errors: list)
  - **세부 기능 M.6: 통합데이터 백업 및 복원**
    - **함수 명칭**: `backup_metadata(session_id: str) -> str`
    - **구현 방법**:
      1. 현재 통합데이터를 타임스탬프 기반 백업 파일로 저장
      2. 백업 파일 압축 및 저장소 이동
      3. 백업 이력 관리
      4. 반환 값: 백업 파일 경로

## 구현 단계별 체크리스트

### 1. 데이터 입력 단계
- [ ] **대표 기능: 통합데이터 초기 생성**
  - **세부 기능 1.1: 세션 식별자 생성**
    - **함수 명칭**: `generate_session_id() -> str`
    - **구현 방법**:
      1. UUID4 라이브러리를 사용하여 36자 고유 식별자 생성
      2. 타임스탬프 (YYYYMMDD_HHMMSS) 추가하여 가독성 향상
      3. 기존 세션 ID와의 충돌 검증
      4. 반환 값: "session_20260115_142530_uuid4" 형식의 문자열
  - **세부 기능 1.2: 초기 통합데이터 구조화**
    - **함수 명칭**: `create_initial_metadata(session_id: str) -> dict`
    - **구현 방법**:
      1. 빈 통합데이터 구조 생성 (target_employee_id, evaluation_document 등 필드)
      2. 처리 상태 초기화 (current_step: "input_started")
      3. 통합데이터 버전 및 생성 타임스탬프 추가
      4. 세션 폴더 구조 생성
      5. 반환 값: 초기화된 통합데이터 딕셔너리
  - **세부 기능 1.3: 통합데이터 파일 초기화**
    - **함수 명칭**: `initialize_metadata_file(metadata: dict, session_id: str) -> str`
    - **구현 방법**:
      1. processed_data/YYYY/MM/DD/session_id/ 폴더 생성
      2. 초기 통합데이터를 JSON으로 저장
      3. 파일 경로 반환 및 세션에 저장
      4. 반환 값: 초기화된 통합데이터 파일 경로

- [ ] **대표 기능: 데이터 파일 업로드 및 검증**
  - **세부 기능 1.1: 파일 형식 검증**
    - **함수 명칭**: `validate_file_format(file_path: str) -> dict`
    - **구현 방법**:
      1. 파일 확장자 추출 및 허용 형식 검증 (CSV: .csv, Excel: .xlsx, .xls)
      2. 파일 크기 측정 및 최대 제한 확인 (50MB)
      3. 파일 헤더 읽기 시도하여 실제 형식 검증
      4. 인코딩 검증: UTF-8 디코딩 시도, 실패 시 CP949 재시도
      5. MIME 타입 확인 (text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
      6. 반환 값: 검증 결과 딕셔너리 (valid: bool, format: str, encoding: str, size: int, errors: list)
  - **세부 기능 1.2: 웹 인터페이스 파일 업로드**
    - **함수 명칭**: `handle_file_upload(request_files: dict, upload_dir: str) -> dict`
    - **구현 방법**:
      1. Flask request.files에서 파일 객체 추출
      2. 파일 존재 여부 및 빈 파일 검증
      3. 보안 검증: 파일명 sanitization (특수문자 제거, 경로 traversal 방지)
      4. 임시 파일 저장 (secure_filename 사용)
      5. 파일 해시 계산 (SHA-256)으로 무결성 검증
      6. 업로드 진행 상태 세션에 저장
      7. 반환 값: 업로드 결과 (success: bool, file_path: str, file_hash: str, errors: list)
  - **세부 기능 1.3: 데이터 미리보기**
    - **함수 명칭**: `preview_data(file_path: str, preview_rows: int = 10) -> dict`
    - **구현 방법**:
      1. 파일 형식에 따른 판다스 로드 함수 선택 (read_csv 또는 read_excel)
      2. 상위 N행 읽기 (기본 10행)
      3. 열 이름 및 데이터 타입 자동 감지 (dtypes)
      4. 각 열의 null 값, 중복 값, 고유 값 수 계산
      5. 데이터 품질 메트릭 계산 (완전성, 일관성)
      6. HTML 테이블 형식으로 미리보기 데이터 생성
      7. 반환 값: 미리보기 정보 (headers: list, rows: list, dtypes: dict, quality_metrics: dict)

- [ ] **대표 기능: 열 정보 설정 인터페이스**
  - **세부 기능 1.4: 통합데이터 필드 매핑**
    - **함수 명칭**: `map_columns_to_metadata(available_columns: list) -> dict`
    - **구현 방법**:
      1. 사용 가능한 열 목록을 통합데이터 필드에 매핑하는 인터페이스 생성
      2. CSV의 "사원번호" 열 → 통합데이터의 "target_employee_id" 필드 매핑
      3. CSV의 "평가내용" 열 → 통합데이터의 "evaluation_document" 필드 매핑
      4. CSV의 "평가자" 열 → 통합데이터의 "evaluator_id" 필드 매핑 (선택사항)
      5. CSV의 "평가일자" 열 → 통합데이터의 "evaluation_date" 필드 매핑 (선택사항)
      6. 실시간 매핑 검증 및 미리보기 표시
      7. 반환 값: 통합데이터 필드 매핑 딕셔너리 (metadata_mapping: dict)
  - **세부 기능 1.5: 열 유효성 검증**
    - **함수 명칭**: `validate_column_selection(file_path: str, column_mapping: dict) -> dict`
    - **구현 방법**:
      1. 선택된 열들이 실제로 파일에 존재하는지 확인
      2. 대상자 ID 열의 유일성 검증 (중복 ID 방지)
      3. 평가 문서 열의 데이터 타입 및 내용 길이 검증 (최소 길이 10자)
      4. 선택사항 열들의 존재 여부 확인
      5. 데이터 샘플링을 통한 품질 검증
      6. 반환 값: 검증 결과 (valid: bool, errors: list, warnings: list)
  - **세부 기능 1.6: 설정 저장 및 확인**
    - **함수 명칭**: `save_column_settings(session_id: str, column_mapping: dict) -> bool`
    - **구현 방법**:
      1. 사용자 설정을 Flask 세션에 임시 저장
      2. 설정 변경 이력을 리스트로 관리 (최대 10개)
      3. 설정 검증 완료 상태를 세션에 기록
      4. 다음 단계 진행 버튼 활성화 JavaScript 트리거
      5. 설정 데이터를 JSON으로 직렬화하여 저장
      6. 반환 값: 저장 성공 여부



### 2. 데이터 정제 단계
- [ ] **대표 기능: 텍스트 정규화 및 노이즈 제거**
  - **세부 기능 2.1: 텍스트 정규화**
    - **함수 명칭**: `normalize_text(text: str) -> str`
    - **구현 방법**:
      1. 줄바꿈 및 탭 문자를 공백으로 통일
      2. 연속된 공백을 단일 공백으로 축소
      3. 특수문자 표준화 (예: "…" → "...")
      4. 한국어 띄어쓰기 교정 (pykospacing 라이브러리 활용)
      5. 반환 값: 정규화된 텍스트 문자열
  - **세부 기능 2.2: 노이즈 제거**
    - **함수 명칭**: `remove_noise(text: str, noise_patterns: list) -> str`
    - **구현 방법**:
      1. 정규식을 사용한 패턴 기반 노이즈 제거 (이메일, URL, 전화번호 등)
      2. 불필요한 특수문자 및 기호 제거
      3. 중복 단어/문장 제거
      4. 최소 길이 필터링 (너무 짧은 텍스트 제외)
      5. 반환 값: 노이즈가 제거된 텍스트
  - **세부 기능 2.3: 데이터 품질 검증**
    - **함수 명칭**: `validate_data_quality(text: str) -> dict`
    - **구현 방법**:
      1. 텍스트 길이 검증 (최소 50자, 최대 5000자)
      2. 한국어 비율 계산 (한글 문자 수 / 전체 문자 수)
      3. 가독성 점수 계산 (문장 길이, 단어 다양성)
      4. 감정 표현 richness 평가
      5. 반환 값: 품질 메트릭 딕셔너리 (length: int, korean_ratio: float, readability_score: float)

- [ ] **대표 기능: 데이터 분할 및 그룹화**
  - **세부 기능 2.4: 사용자별 데이터 분할**
    - **함수 명칭**: `split_data_by_user(data: pd.DataFrame, user_column: str) -> dict`
    - **구현 방법**:
      1. pandas groupby를 사용한 사용자별 그룹화
      2. 각 그룹을 별도 데이터프레임으로 분리
      3. 그룹별 통계 정보 계산 (평가 수, 평균 길이 등)
      4. 메모리 효율적 처리 (청크 단위)
      5. 반환 값: 사용자 ID를 키로 하는 데이터프레임 딕셔너리
  - **세부 기능 2.5: 평가 유형별 분류**
    - **함수 명칭**: `classify_evaluation_type(text: str) -> str`
    - **구현 방법**:
      1. 키워드 기반 분류 (성과/태도/역량/리더십 등)
      2. 머신러닝 기반 자동 분류 (선택적)
      3. 신뢰도 점수 계산
      4. 다중 분류 허용 (하나의 평가가 여러 유형 포함 가능)
      5. 반환 값: 분류 결과 문자열 또는 리스트
  - **세부 기능 2.6: 정제 결과 저장**
    - **함수 명칭**: `save_cleaned_data(cleaned_data: dict, session_id: str) -> bool`
    - **구현 방법**:
      1. 정제된 데이터를 JSON 형식으로 저장
      2. 통합데이터에 정제 결과 경로 추가
      3. 압축 저장 옵션 (대용량 데이터)
      4. 백업 생성
      5. 반환 값: 저장 성공 여부

### 3. 자연어 분석 단계
- [ ] **대표 기능: 형태소 분석**
  - **세부 기능 3.1: Kiwi 분석기 적용**
    - **함수 명칭**: `analyze_with_kiwi(text: str) -> dict`
    - **구현 방법**:
      1. Kiwi 객체 초기화 및 모델 로드
      2. 텍스트를 문장 단위로 분리
      3. 각 문장에 대해 형태소 분석 수행
      4. 토큰 정보 추출 (형태, 품사, 위치)
      5. 반환 값: 토큰 리스트와 메타 정보
  - **세부 기능 3.2: Okt 분석기 적용**
    - **함수 명칭**: `analyze_with_okt(text: str) -> dict`
    - **구현 방법**:
      1. Okt 객체 초기화
      2. 형태소 분석 및 품사 태깅
      3. 의미 있는 단어 필터링 (명사/동사/형용사/감탄사)
      4. 불용어 제거 및 길이 필터링
      5. 반환 값: 분석 결과 딕셔너리
  - **세부 기능 3.3: 분석 결과 통합**
    - **함수 명칭**: `merge_analysis_results(kiwi_result: dict, okt_result: dict) -> dict`
    - **구현 방법**:
      1. 두 분석기의 결과를 비교 및 통합
      2. 신뢰도 기반 가중치 적용
      3. 충돌하는 분석 결과 해결
      4. 최종 토큰 리스트 생성
      5. 반환 값: 통합된 분석 결과

- [ ] **대표 기능: 의미 분석**
  - **세부 기능 3.4: 개체명 인식**
    - **함수 명칭**: `extract_named_entities(tokens: list) -> list`
    - **구현 방법**:
      1. 토큰 시퀀스에서 개체명 패턴 탐색
      2. 규칙 기반 및 통계 기반 방법 결합
      3. 인사 평가 맥락에 특화된 개체명 정의
      4. 신뢰도 점수 부여
      5. 반환 값: 개체명 리스트 (entity: str, type: str, confidence: float)
  - **세부 기능 3.5: 문장 경계 인식**
    - **함수 명칭**: `detect_sentence_boundaries(text: str) -> list`
    - **구현 방법**:
      1. 마침표, 물음표, 느낌표 기반 분리
      2. 인용구 및 괄호 처리
      3. 문장 길이 및 완전성 검증
      4. 반환 값: 문장 시작/끝 위치 리스트
  - **세부 기능 3.6: 분석 결과 저장**
    - **함수 명칭**: `save_nlp_results(results: dict, session_id: str) -> str`
    - **구현 방법**:
      1. 분석 결과를 구조화된 JSON으로 저장
      2. 통합데이터에 NLP 결과 경로 업데이트
      3. 토큰화된 데이터 압축 저장
      4. 반환 값: 저장된 파일 경로

### 4. 감정 분석 단계
- [ ] **대표 기능: 감정 분류**
  - **세부 기능 4.1: 모델 예측 수행**
    - **함수 명칭**: `predict_emotion(text: str, model_type: str) -> dict`
    - **구현 방법**:
      1. 입력 텍스트 전처리 (토큰화, 패딩)
      2. 선택된 모델 로드 (파인튜닝 또는 기본 모델)
      3. 배치 예측 수행
      4. 확률 분포 계산
      5. 반환 값: 예측 결과 (label: str, confidence: float, raw_scores: dict)
  - **세부 기능 4.2: 레이블 매핑**
    - **함수 명칭**: `map_emotion_labels(predictions: dict) -> dict`
    - **구현 방법**:
      1. 모델 출력 레이블을 의미 있는 감정으로 변환
      2. 다중 클래스 매핑 (0→부정, 1→중립, 2→긍정)
      3. 문화적 맥락 고려한 한국어 감정 표현 매핑
      4. 반환 값: 매핑된 결과 (mapped_label: str, original_label: str)
  - **세부 기능 4.3: 신뢰도 평가**
    - **함수 명칭**: `evaluate_prediction_confidence(predictions: dict) -> float`
    - **구현 방법**:
      1. 예측 확률의 엔트로피 계산
      2. 모델 간 일관성 점수 계산
      3. 텍스트 길이와 복잡도 고려
      4. 반환 값: 0-1 사이의 신뢰도 점수

- [ ] **대표 기능: 감정 강도 측정**
  - **세부 기능 4.4: 문장별 감정 분석**
    - **함수 명칭**: `analyze_sentence_emotions(text: str, sentences: list) -> list`
    - **구현 방법**:
      1. 문장 경계에 따라 텍스트 분할
      2. 각 문장별 감정 예측
      3. 감정 강도 정규화 (-1 to 1)
      4. 문맥 고려한 감정 조정
      5. 반환 값: 문장별 감정 분석 리스트
  - **세부 기능 4.5: 감정 키워드 추출**
    - **함수 명칭**: `extract_emotion_keywords(text: str, emotion: str) -> list`
    - **구현 방법**:
      1. 감정별 키워드 사전 활용
      2. TF-IDF 기반 중요 단어 추출
      3. 감정 점수 기반 가중치 적용
      4. 반환 값: 키워드 리스트 (word: str, score: float)
  - **세부 기능 4.6: 분석 결과 저장**
    - **함수 명칭**: `save_emotion_results(results: dict, session_id: str) -> str`
    - **구현 방법**:
      1. 감정 분석 결과를 JSON으로 저장
      2. 통합데이터에 감정 결과 경로 업데이트
      3. 시계열 감정 데이터 저장
      4. 반환 값: 저장된 파일 경로

### 5. 워드클라우드 생성 단계
- [ ] **대표 기능: 감정 기반 시각화**
  - **세부 기능 5.1: 단어 빈도 계산**
    - **함수 명칭**: `calculate_word_frequencies(text: str, emotion_scores: dict) -> dict`
    - **구현 방법**:
      1. 토큰화된 텍스트에서 단어 추출
      2. 감정 점수와 빈도 결합
      3. 불용어 필터링
      4. 가중치 적용 (감정 강도 × 빈도)
      5. 반환 값: 단어별 빈도 및 감정 점수 딕셔너리
  - **세부 기능 5.2: 색상 매핑 함수**
    - **함수 명칭**: `create_color_function(emotion_scores: dict) -> callable`
    - **구현 방법**:
      1. 감정 점수를 색상으로 변환하는 함수 생성
      2. 긍정: 파랑, 부정: 빨강, 중립: 회색
      3. 점수 절대값에 따른 채도 조절
      4. 반환 값: 워드클라우드 색상 함수
  - **세부 기능 5.3: 워드클라우드 생성**
    - **함수 명칭**: `generate_emotion_wordcloud(word_freq: dict, color_func: callable) -> bool`
    - **구현 방법**:
      1. WordCloud 객체 초기화 (폰트, 크기, 배경 설정)
      2. 단어 빈도로 워드클라우드 생성
      3. 색상 함수 적용
      4. 이미지 파일로 저장
      5. 반환 값: 생성 성공 여부

- [ ] **대표 기능: 시각화 결과 저장**
  - **세부 기능 5.4: 이미지 파일 저장**
    - **함수 명칭**: `save_wordcloud_image(wordcloud, session_id: str) -> str`
    - **구현 방법**:
      1. 워드클라우드 객체를 PNG 파일로 저장
      2. 해상도 및 품질 설정
      3. 파일 경로 생성 및 검증
      4. 반환 값: 저장된 이미지 파일 경로
  - **세부 기능 5.5: 통합데이터 업데이트**
    - **함수 명칭**: `update_metadata_with_wordcloud(metadata: dict, image_path: str) -> dict`
    - **구현 방법**:
      1. 통합데이터에 워드클라우드 경로 추가
      2. 생성 파라미터 기록
      3. 처리 상태 업데이트
      4. 반환 값: 업데이트된 통합데이터
  - **세부 기능 5.6: 웹 표시용 데이터 생성**
    - **함수 명칭**: `prepare_web_display_data(word_freq: dict, emotion_scores: dict) -> dict`
    - **구현 방법**:
      1. 웹에서 표시할 단어 데이터 준비
      2. 감정별 색상 코드 생성
      3. 인터랙티브 요소를 위한 JSON 데이터 생성
      4. 반환 값: 웹 표시용 데이터 딕셔너리

### 6. 추세 분석 단계
- [ ] **대표 기능: 시계열 감정 분석**
  - **세부 기능 6.1: 시간 기반 데이터 집계**
    - **함수 명칭**: `aggregate_emotions_by_time(metadata_list: list, time_range: str) -> dict`
    - **구현 방법**:
      1. 통합데이터에서 시간 정보 추출
      2. 지정된 기간별 감정 데이터 집계
      3. 평균 감정 점수 계산
      4. 변화율 분석
      5. 반환 값: 시간별 집계 데이터
  - **세부 기능 6.2: 추세 패턴 식별**
    - **함수 명칭**: `identify_trends(time_series_data: dict) -> dict`
    - **구현 방법**:
      1. 이동 평균 계산
      2. 추세선 생성 (선형 회귀)
      3. 계절성 패턴 탐지
      4. 이상치 식별
      5. 반환 값: 추세 분석 결과
  - **세부 기능 6.3: 예측 모델링**
    - **함수 명칭**: `predict_future_trends(historical_data: dict, forecast_periods: int) -> dict`
    - **구현 방법**:
      1. 시계열 모델 선택 (ARIMA, Prophet 등)
      2. 모델 학습 및 검증
      3. 미래 값 예측
      4. 신뢰 구간 계산
      5. 반환 값: 예측 결과 딕셔너리

- [ ] **대표 기능: 보고서 생성**
  - **세부 기능 6.4: 종합 보고서 작성**
    - **함수 명칭**: `generate_comprehensive_report(session_id: str) -> dict`
    - **구현 방법**:
      1. 모든 통합데이터 수집 및 통합
      2. 주요 지표 계산 (평균 감정, 추세, 키워드)
      3. 시각화 차트 생성
      4. 실행 요약 작성
      5. 반환 값: 보고서 데이터
  - **세부 기능 6.5: 보고서 저장 및 배포**
    - **함수 명칭**: `save_and_distribute_report(report_data: dict, session_id: str) -> bool`
    - **구현 방법**:
      1. 보고서를 PDF/HTML로 생성
      2. 파일 시스템에 저장
      3. 이메일 또는 웹 링크로 배포
      4. 액세스 권한 설정
      5. 반환 값: 배포 성공 여부
  - **세부 기능 6.6: 데이터 아카이빙**
    - **함수 명칭**: `archive_session_data(session_id: str) -> bool`
    - **구현 방법**:
      1. 세션 관련 모든 파일 압축
      2. 장기 저장소로 이동
      3. 통합데이터 업데이트
      4. 정리 작업 수행
      5. 반환 값: 아카이빙 성공 여부

## 기술 스택
- Backend: Python Flask
- Frontend: HTML/CSS/JavaScript
- 데이터 처리: pandas, openpyxl
- 파일 처리: os, json
- 검증: 정규식, 데이터 타입 체크

## 구현 우선순위
1. 데이터 입력 및 통합데이터 생성 (현재 단계)
2. 데이터 정제 및 검증
3. NLP 분석 파이프라인
4. 감정 분석 모델 통합
5. 시각화 및 결과 출력

## 참고 사항
- 모든 단계에서 통합데이터를 업데이트하여 처리 상태 추적
- 웹 인터페이스는 사용자 친화적 디자인 적용
- 에러 처리 및 사용자 피드백 강화
- 데이터 보안 및 프라이버시 고려
