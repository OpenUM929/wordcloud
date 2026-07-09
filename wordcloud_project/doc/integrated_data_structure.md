# 통합데이터 구조 설명서

## 1. 통합데이터 구조 트리

```
metadata (JSON Object)
├── session_id: string                    # 세션 고유 식별자
├── created_at: ISO 8601 timestamp        # 통합데이터 생성 시각
├── version: semantic version string      # 통합데이터 스키마 버전
├── target_employee_id: string            # 평가 대상자 ID
├── evaluation_document: string           # 평가 문서 원본 텍스트
├── evaluator_id: string (optional)       # 평가자 ID
├── evaluation_date: string (optional)    # 평가 일자
├── processing_status: object             # 처리 진행 상태
│   ├── current_step: string              # 현재 처리 단계
│   ├── completed_steps: array            # 완료된 단계 목록
│   └── next_step: string                 # 다음 처리 단계
├── preprocessing_results: object         # 데이터 정제 결과 (정제 단계 후 추가)
│   ├── original_length: number           # 원본 텍스트 길이
│   ├── cleaned_content: string           # 정제된 텍스트 내용
│   ├── removed_noise: array              # 제거된 노이즈 패턴 목록
│   └── processing_time_ms: number        # 처리 소요 시간 (밀리초)
├── nlp_analysis_results: object          # 자연어 분석 결과 (NLP 단계 후 추가)
│   ├── kiwi_tokens: array                # Kiwi 형태소 분석 토큰
│   ├── okt_morphemes: array              # Okt 형태소 분석 결과
│   ├── meaningful_words: array           # 의미 있는 단어 목록
│   └── sentence_boundaries: array        # 문장 경계 위치
├── emotion_analysis_results: object      # 감정 분석 결과 (감정 분석 단계 후 추가)
│   ├── overall_sentiment: string         # 전체 감정 분류 (positive/negative/neutral)
│   ├── confidence_score: number          # 신뢰도 점수 (0.0-1.0)
│   ├── sentence_level_analysis: array    # 문장별 감정 분석
│   └── key_emotion_words: object         # 감정별 키워드
├── wordcloud_path: string                # 워드클라우드 이미지 경로 (워드클라우드 생성 후 추가)
└── data_integrity_hash: string           # 데이터 무결성 검증 해시
```

## 2. 통합데이터 필드 상세 설명 표

| 필드명 | 데이터 타입 | 필수 여부 | 설명 | 예시 값 |
|--------|-------------|-----------|------|---------|
| `session_id` | string | 필수 | 각 분석 세션의 고유 식별자로 UUID 기반 생성 | `"session_20260115_142530_550e8400-e29b-41d4-a716-446655440000"` |
| `created_at` | ISO 8601 timestamp | 필수 | 통합데이터 생성 시각 (UTC 기준) | `"2026-01-15T05:25:30.123Z"` |
| `version` | semantic version string | 필수 | 통합데이터 스키마 버전 (MAJOR.MINOR.PATCH) | `"1.0.0"` |
| `target_employee_id` | string | 필수 | 인사 평가 대상자의 고유 식별자 | `"EMP_00123"` |
| `evaluation_document` | string | 필수 | 평가 문서의 원본 텍스트 내용 | `"평가 대상자의 업무 수행 능력이 우수하며 팀워크가 뛰어나다."` |
| `evaluator_id` | string | 선택 | 평가를 수행한 평가자의 식별자 | `"MGR_00456"` |
| `evaluation_date` | string | 선택 | 평가가 수행된 일자 (YYYY-MM-DD 형식) | `"2025-12-31"` |
| `processing_status.current_step` | string | 필수 | 현재 진행 중인 처리 단계 | `"emotion_analysis"` |
| `processing_status.completed_steps` | array | 필수 | 완료된 처리 단계 목록 | `["input_validation", "data_preprocessing", "nlp_analysis"]` |
| `processing_status.next_step` | string | 필수 | 다음에 수행할 처리 단계 | `"wordcloud_generation"` |
| `preprocessing_results.original_length` | number | 필수 | 원본 텍스트의 문자 수 | `156` |
| `preprocessing_results.cleaned_content` | string | 필수 | 노이즈 제거 및 정규화된 텍스트 | `"평가 대상자 업무 수행 능력 우수 팀워크 뛰어나다"` |
| `preprocessing_results.removed_noise` | array | 필수 | 제거된 노이즈 요소 목록 | `["특수문자", "중복문장"]` |
| `preprocessing_results.processing_time_ms` | number | 필수 | 정제 처리에 소요된 시간 | `45` |
| `nlp_analysis_results.kiwi_tokens` | array | 필수 | Kiwi 분석기의 토큰화 결과 | `[{"form": "평가", "tag": "NNG", "start": 0, "len": 2}]` |
| `nlp_analysis_results.okt_morphemes` | array | 필수 | Okt 분석기의 형태소 분석 결과 | `["평가", "대상자", "업무", "수행", "능력", "우수"]` |
| `nlp_analysis_results.meaningful_words` | array | 필수 | 의미 분석을 위한 핵심 단어 목록 | `["업무", "수행", "능력", "우수", "팀워크", "뛰어나다"]` |
| `nlp_analysis_results.sentence_boundaries` | array | 필수 | 텍스트 내 문장 시작/끝 위치 | `[0, 23, 35]` |
| `emotion_analysis_results.overall_sentiment` | string | 필수 | 전체 텍스트의 감정 분류 | `"positive"` |
| `emotion_analysis_results.confidence_score` | number | 필수 | 감정 분류의 신뢰도 (0.0-1.0) | `0.87` |
| `emotion_analysis_results.sentence_level_analysis` | array | 필수 | 각 문장별 감정 분석 결과 | `[{"text": "업무 수행 능력이 우수하며", "sentiment": "positive", "score": 0.92}]` |
| `emotion_analysis_results.key_emotion_words` | object | 필수 | 감정별 주요 단어 분류 | `{"positive": ["우수", "뛰어나다"], "negative": [], "neutral": ["수행", "능력"]}` |
| `wordcloud_path` | string | 필수 | 생성된 워드클라우드 이미지 파일 경로 | `"processed_data/2026/01/15/session_xxx/wordcloud.png"` |
| `data_integrity_hash` | string | 필수 | 모든 분석 결과의 SHA-256 해시 (무결성 검증용) | `"a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"` |

## 3. 통합데이터 JSON 예시

```json
{
  "session_id": "session_20260115_142530_550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-01-15T05:25:30.123Z",
  "version": "1.0.0",
  "target_employee_id": "EMP_00123",
  "evaluation_document": "평가 대상자의 업무 수행 능력이 우수하며 팀워크가 뛰어나다. 다만 커뮤니케이션 능력이 약간 부족한 점이 있다.",
  "evaluator_id": "MGR_00456",
  "evaluation_date": "2025-12-31",
  "processing_status": {
    "current_step": "completed",
    "completed_steps": [
      "input_validation",
      "data_preprocessing",
      "nlp_analysis",
      "emotion_analysis",
      "wordcloud_generation"
    ],
    "next_step": null
  },
  "preprocessing_results": {
    "original_length": 89,
    "cleaned_content": "평가 대상자 업무 수행 능력 우수 팀워크 뛰어나다 다만 커뮤니케이션 능력 약간 부족 점 있다",
    "removed_noise": ["마침표", "줄바꿈"],
    "processing_time_ms": 45
  },
  "nlp_analysis_results": {
    "kiwi_tokens": [
      {"form": "평가", "tag": "NNG", "start": 0, "len": 2},
      {"form": "대상자", "tag": "NNG", "start": 3, "len": 3}
    ],
    "okt_morphemes": ["평가", "대상자", "업무", "수행", "능력", "우수"],
    "meaningful_words": ["업무", "수행", "능력", "우수", "팀워크", "뛰어나다", "커뮤니케이션", "부족"],
    "sentence_boundaries": [0, 28, 52]
  },
  "emotion_analysis_results": {
    "overall_sentiment": "mixed",
    "confidence_score": 0.76,
    "sentence_level_analysis": [
      {
        "text": "평가 대상자의 업무 수행 능력이 우수하며 팀워크가 뛰어나다",
        "sentiment": "positive",
        "score": 0.91
      },
      {
        "text": "다만 커뮤니케이션 능력이 약간 부족한 점이 있다",
        "sentiment": "negative",
        "score": 0.68
      }
    ],
    "key_emotion_words": {
      "positive": ["우수", "뛰어나다"],
      "negative": ["부족"],
      "neutral": ["업무", "수행", "능력", "커뮤니케이션"]
    }
  },
  "wordcloud_path": "processed_data/2026/01/15/session_20260115_142530_550e8400-e29b-41d4-a716-446655440000/wordcloud.png",
  "data_integrity_hash": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"
}
```

## 4. 통합데이터 처리 흐름

1. **초기 생성**: 데이터 입력 단계에서 기본 통합데이터 구조 생성
2. **점진적 업데이트**: 각 처리 단계 완료 시 해당 결과 필드 추가
3. **상태 추적**: `processing_status`를 통해 진행 상황 모니터링
4. **무결성 검증**: 최종 해시를 통한 데이터 변조 방지
5. **백업 및 복원**: 변경 이력을 통한 안정성 확보

이 구조는 특허에서 데이터 관리 체계의 체계성과 확장성을 입증하는 중요한 요소입니다.
