# 배치 처리 대용량 최적화 개발 계획

> 문서 작성일: 2026-04-21
> 작업 유형: 리팩토링 (대용량 데이터 처리 최적화)
> 대상: 150K+ 행 (20,000 직원)
> 상태: Done(2026-06-18) — 본 로드맵의 목표(모델 싱글톤·직원 단위 병렬·체크포인트·CSV 청크/스트리밍)는 후속 계획서로 실현됨: 싱글톤=`kote_shared.py`·각 모듈 `_instance`, 병렬=`batch_processor` ThreadPoolExecutor([[0617_07_hardware-adaptive-worker-plan]]), 체크포인트=`CHECKPOINT_INTERVAL`, 청크/스트리밍=`batch_staging`([[0615_01_batch-csv-stream]]), WC 병렬=[[0618_03_deploy-wc-parallel]]. (구현 형태는 ProcessPool→ThreadPool, tmeta JSON→staging.db로 변경됨)

---

## 1. 현재 상황 요약

| 항목 | 현재 상태 | 목표 |
|------|----------|------|
| 처리 방식 | 순차 처리 | 병렬/청크 처리 |
| 모델 로딩 | 평가별 새 인스턴스 | 싱글톤 캐싱 |
| 예상 처리 시간 | 4-12시간 | 1-2시간 |
| 데이터 규모 | 150K 행 | 150K+ 행 대응 |

---

## 2. 2단계 처리 흐름

```
[Phase 1: 1차 메타데이터화] → [Phase 2: 통합 메타데이터]
        ↓                              ↓
  개별 직원 JSON 저장              통합 분석 결과 생성
  (tmeta/*.json)                 (consolidated_analysis)
```

### Phase 1: 1차 메타데이터화
- **입력**: CSV (150K 행)
- **처리**: 직원별 평가 데이터 분석 (NLP, 감정, 욕설, 리더십, 풍자)
- **출력**: `batch_dir/tmeta/employee_{id}.json` (20K 파일)

### Phase 2: 통합 메타데이터
- **입력**: Phase 1 결과물 (저장된 JSON)
- **처리**: 통합 감정, 단어 빈도, 리더십 종합
- **출력**: `consolidated_analysis` 필드

---

## 3. 수정 필요 파일 (Impact Analysis)

| 파일 | 수정 내용 | 보호 등급 |
|------|----------|----------|
| `src/models/metadata_manager.py` | 모델 싱글톤 캐싱 | 🟡 승인 필요 |
| `src/modules/profanity_filter.py` | 싱글톤 패턴 적용 | 🟡 승인 필요 |
| `src/modules/leadership_analysis.py` | 싱글톤 패턴 적용 | 🟡 승인 필요 |
| `src/modules/metadata_analysis.py` | LeadershipAnalysis 캐싱 | 🟡 승인 필요 |
| `src/services/batch_processor.py` | 병렬 처리 추가 | 🟡 승인 필요 |

---

## 4. 개발 단계

### Phase A: 모델 캐싱 (즉시 효과)
**목표**: 모델 재발생 문제 해결 → 3-5배 속도 향상

#### Step A-1: ProfanityFilter 싱글톤
```
현재: evaluate()마다 ProfanityFilter() 생성
변경: module 레벨 singleton 인스턴스
```

#### Step A-2: LeadershipAnalysis 싱글톤
```
현재: evaluate()마다 LeadershipAnalysis() 생성
변경: module 레벨 singleton 인스턴스
```

#### Step A-3: metadata_analysis 캐싱
```
현재: calculate_consolidated_analysis()에서 LeadershipAnalysis() 생성
변경: 인스턴스 전달 또는 module 레벨 캐싱
```

### Phase B: 병렬 처리 (주요 효과)
**목표**: 동시 처리 → 6-8배 속도 향상 (8코어 기준)

#### Step B-1: ProcessPoolExecutor 적용
```
batch_processor.py의 process_batch() 수정:
- concurrent.futures.ProcessPoolExecutor 사용
- 직원 단위 병렬 처리
```

#### Step B-2: 워드클라우드 병렬 생성
```
generate_employee_wordcloud() 병렬화
```

### Phase C: 안정성 (선택적)
**목표**: 실패 복구, 체크포인트

#### Step C-1: 체크포인트 추가
- 1000건 처리마다 중간 저장
- 실패 시 재개 가능

#### Step C-2: 청크 처리
- 대용량 CSV 청크 단위 로딩
- 메모리 최적화

---

## 5. 테스트 계획

| 단계 | 테스트 내용 | 예상 시간 |
|------|----------|----------|
| T1 | ProfanityFilter 캐싱 검증 | 5분 |
| T2 | LeadershipAnalysis 캐싱 검증 | 10분 |
| T3 | Phase B 처리 결과 동일성 (100건) | 30분 |
| T4 | 전체 처리 시간 측정 (1000건) | 1시간 |
| T5 | 150K 실제 데이터 처리 | 1-2시간 |

---

## 6. 롤백 계획

| 문제 발생 시 | 롤백 방법 |
|------------|------------|
| ProfanityFilter 문제 | 원본 클래스 복원 |
| LeadershipAnalysis 문제 | 원본 클래스 복원 |
| 병렬 처리 문제 | 순차 처리 코드로 복원 |
| 전체 실패 | Git stash → 이전 커밋 |

---

## 7. 체크리스트

- [ ] Step A-1: ProfanityFilter 싱글톤 수정
- [ ] Step A-2: LeadershipAnalysis 싱글톤 수정
- [ ] Step A-3: metadata_analysis 캐싱 수정
- [ ] Step B-1: ProcessPoolExecutor 적용
- [ ] Step B-2: 워드클라우드 병렬 생성
- [ ] T1-T5 테스트 실행
- [ ] 기존 배치 처리 동작 확인

---

## 8. 예상 효과

| 지표 | 현재 | Phase A 후 | Phase B 후 |
|------|------|------------|-----------|
| 20K 처리 시간 | 4-12시간 | 1-3시간 | 1-2시간 |
| 모델 인스턴스 (150K) | 170K | 2 | 2 |
| 메모리 사용량 | 높음 | 중간 | 중간 |

---

*문서 작성자: opencode*
*검토 상태: 검토 필요*