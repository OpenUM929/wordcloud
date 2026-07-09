# 웹 시스템 개선 체크리스트

## 1. 통합데이터 저장 구조 개선
- [x] 폴더 구조 변경: {YYYYMM}으로 단위 변경 (기존 {YYYY/MM/DD} → {YYYYMM})
- [ ] 통합 저장 구조 구현: 1:1 평가의 `employee_{id}.json` 형식 저장
- [ ] 통합 분석 필드 추가: 종합 감정 판단, 리더십 종합 평가
- [ ] 데이터 무결성 검증: SHA-256 해시로 통합데이터 변조 검증
- [ ] 검색 기능 개선: 대상자 ID, 부서, 직책 등으로 검색
- [ ] 프론트엔드 수정: 통합데이터 상세 페이지, 통합 분석 보기

## 2. 기존 기능 유지
- [x] `/generate_metadata` 엔드포인트: 기본 통합데이터 생성 시 모든 모듈 결과 추가
- [x] `/process_batch_metadata` 엔드포인트: 배치 처리 시 통합데이터 통합 분석
- [x] 모듈 테스트: 모든 분석 모듈 정상 동작 확인

## 3. 폴더 구조 예시
```
processed_data/
├── 202603/
│   ├── single/
│   │   ├── employee_U001.json
│   │   └── employee_U002.json
│   └── multi/
│       ├── batch_1678901234/
│       │   ├── employee_U001.json
│       │   └── employee_U002.json
│       └── batch_1678905678/
│           ├── employee_U003.json
│           └── employee_U004.json
```

## 4. 통합데이터 구조 상세 정보

### 기본 통합데이터 구조 (단일 평가)
```json
{
  "evaluation_id": "eval-20260312-abc123",
  "session_id": "session_20260312_164902_abc123",
  "created_at": "2026-03-12T16:49:02Z",
  "version": "1.2.0-1to1",
  "target_employee_id": "U001",
  "target_employee_department": "기획부",
  "target_employee_position": "팀장",
  "target_hierarchy_level": "team_leader",
  "evaluation_document": "이 직원은 팀원들과의 협업이 좋고, 문제 해결 능력이 뛰어나다.",
  "evaluator_id": "E001",
  "evaluator_department": "기획부",
  "evaluator_position": "팀장",
  "evaluator_hierarchy_level": "team_leader",
  "evaluation_date": "2026-03-12",
  "processing_status": {
    "current_step": "completed",
    "completed_steps": ["input_validation", "data_preprocessing", "nlp_analysis", "emotion_analysis", "sarcasm_analysis", "leadership_analysis", "wordcloud_generation"],
    "next_step": null
  },
  "preprocessing_results": {},
  "profanity_analysis_results": {},
  "nlp_analysis_results": {},
  "emotion_analysis_results": {},
  "sarcasm_analysis_results": {},
  "leadership_analysis_results": {},
  "wordcloud_path": "/outputs/wordcloud_session_20260312_164902_abc123.png",
  "wordcloud_generation_info": {},
  "data_integrity_hash": "sha256:abc123..."
}
```

### 통합 통합데이터 구조 (여러 평가)
```json
{
  "session_id": "session_20260312_164902_abc123",
  "target_employee_id": "U001",
  "target_employee_department": "기획부",
  "target_employee_position": "팀장",
  "total_evaluations": 2,
  "evaluations": [
    {
      "id": 1,
      "evaluation_document": "이 직원은 팀원들과의 협업이 좋고, 문제 해결 능력이 뛰어나다.",
      "evaluator_id": "E001",
      "evaluator_department": "기획부",
      "evaluator_position": "팀장",
      "evaluator_hierarchy_level": "team_leader",
      "evaluation_date": "2026-03-12",
      "preprocessing_results": {},
      "profanity_analysis_results": {},
      "nlp_analysis_results": {},
      "emotion_analysis_results": {},
      "sarcasm_analysis_results": {},
      "leadership_analysis_results": {}
    },
    {
      "id": 2,
      "evaluation_document": "이 직원은 리더십이 부족하고, 의사결정이 느리다.",
      "evaluator_id": "E002",
      "evaluator_department": "기획부",
      "evaluator_position": "과장",
      "evaluator_hierarchy_level": "manager",
      "evaluation_date": "2026-03-11",
      "preprocessing_results": {},
      "profanity_analysis_results": {},
      "nlp_analysis_results": {},
      "emotion_analysis_results": {},
      "sarcasm_analysis_results": {},
      "leadership_analysis_results": {}
    }
  ],
  "consolidated_analysis": {
    "combined_cleaned_content": "이 직원은 팀원들과의 협업이 좋고, 문제 해결 능력이 뛰어나다. 이 직원은 리더십이 부족하고, 의사결정이 느리다.",
    "overall_sentiment": "neutral",
    "confidence_score": 0.5,
    "consolidated_emotion_words": {
      "positive": ["협업", "문제해결"],
      "negative": ["리더십", "의사결정"],
      "neutral": []
    },
    "consolidated_nlp_words": ["협업", "문제해결", "리더십", "의사결정"],
    "word_frequency": {"협업": 1, "문제해결": 1, "리더십": 1, "의사결정": 1},
    "evaluator_analysis": {
      "department_distribution": {"기획부": 2},
      "position_distribution": {"팀장": 1, "과장": 1}
    },
    "profanity_consolidated": {
      "total_profanity_count": 0,
      "profanity_words": [],
      "profanity_frequency": {},
      "evaluations_with_profanity": 0,
      "profanity_ratio": 0
    },
    "leadership_consolidated": {
      "overall_leadership_score": 0.3,
      "leadership_sentiment": "needs_improvement",
      "strengths": ["협업", "문제해결"],
      "weaknesses": ["리더십", "의사결정"]
    }
  },
  "wordcloud_path": "/outputs/wordcloud_U001_20260312_164902.png",
  "wordcloud_generation_info": {},
  "data_integrity_hash": "sha256:def456..."
}
```

## 5. 공통 모듈 설정 파일 위치

| 모듈 이름               | 설정 파일 경로                  |
|--------------------------|--------------------------------|
| emotion_analysis         | configs/emotion_config.json    |
| sarcasm_analysis         | configs/sarcasm_config.json    |
| nlp_analysis             | configs/nlp_config.json        |
| profanity_filter         | configs/profanity_config.json  |
| leadership_analysis      | configs/leadership_config.json |
| wordcloud_generator      | configs/wordcloud_config.json  |

## 6. 진행 중인 작업
- web/app.py 파일 수정: 공통 모듈 사용하도록 변경
- analyze 함수 수정: modules/emotion_analysis.analyze_emotion 사용
- 모델 경로 수정: 기본 kote 모델로 변경