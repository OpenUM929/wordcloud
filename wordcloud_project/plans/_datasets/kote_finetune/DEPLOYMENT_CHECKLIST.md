# 파인튜닝 모델 배포 체크리스트 (260624)

> 배포 환경에서 파인튜닝 모델이 제대로 작동하는지 확인하는 절차.

## 배포 전 (dev 환경)

- [ ] `model/hr_sentiment_finetuned/` 존재 확인
  ```bash
  ls model/hr_sentiment_finetuned/
  # config.json, model.safetensors, tokenizer.json 등
  ```

- [ ] settings.py 수정 확인
  ```bash
  grep HR_SENTIMENT_MODEL src/config/settings.py
  # HR_SENTIMENT_MODEL_PATH, USE_HR_SENTIMENT_MODEL 두 줄 존재
  ```

- [ ] hr_sentiment.py 존재 확인
  ```bash
  ls src/modules/hr_sentiment.py
  ```

- [ ] perspective_service.py 통합 확인 (배치 지점)
  ```bash
  grep -n "model_labels = predict_sentiments" src/services/perspective_service.py
  ```

- [ ] 컴파일 검증
  ```bash
  python -m py_compile src/config/settings.py src/modules/hr_sentiment.py src/services/perspective_service.py
  ```

## 배포 단계

### 1. 패키지 빌드 (PowerShell)
```powershell
cd D:\dev\wordcloud
.\wordcloud_project\deploy\build_deploy.ps1 -Mode Package -OutputPath "D:\deploy_output"
```

### 2. 배포 패키지 전송
```bash
# 배포 환경으로 복사
D:\deploy_output\wordcloud_*\ → [운영 서버]
```

### 3. 배포 환경에서 검증

#### 3-1. 모델 파일 확인
```bash
ls [배포경로]\model\hr_sentiment_finetuned\
# model.safetensors 존재 확인
```

#### 3-2. 설정 확인
```python
python -c "from src.config.settings import HR_SENTIMENT_MODEL_PATH, USE_HR_SENTIMENT_MODEL; print(HR_SENTIMENT_MODEL_PATH, USE_HR_SENTIMENT_MODEL)"
```

#### 3-3. 모델 로드 테스트
```python
from src.modules.hr_sentiment import predict_sentiments
result = predict_sentiments(['이것은 테스트입니다'])
print(result)  # ['neutral'] 같은 라벨 반환
```

#### 3-4. 배치 검증 (메타데이터 생성)
```bash
# 테스트 데이터 준비 (기존 baseline_eval 사용)
python plans/_datasets/kote_finetune/scripts/validate_deployment.py \
  --deploy-root [배포경로] \
  --test-data baseline_eval_260624.jsonl \
  --out validation_result.json
```

결과 해석:
- `model_available: true` → 모델 로드 성공 ✓
- `difference_count` → 극성 변화 건수(파인튜닝 모델이 규칙과 다른 예측)
- `sample_differences` → 샘플 케이스

## 롤백 (문제 발생 시)

### 즉시 해제 (모델 OFF)
```bash
# 환경변수 설정
export USE_HR_SENTIMENT_MODEL=0
# 또는 Windows
set USE_HR_SENTIMENT_MODEL=0
```

### 영구 롤백 (코드)
```bash
git checkout src/config/settings.py src/services/perspective_service.py src/modules/hr_sentiment.py
```

## 검증 체크

| 항목 | 기대값 | 확인 |
|---|---|---|
| 모델 로드 | ✓ (None 아님) | |
| 극성 변화율 | ~20~30% (규칙과 다른 예측) | |
| 긍↔부 오류 감소 | before 10 → after 0~2 | |
| 응답 시간 | baseline + 배치추론시간 (<1초/100문장) | |
| 폴백 작동 | 모델 OFF 시 규칙 복귀 | |

## 문제 해결

### 모델 로드 실패
- 경로 확인: `model/hr_sentiment_finetuned/model.safetensors` 존재?
- GPU 메모리: `torch.cuda.is_available()` 확인
- 로그 확인: `HR 감정모델 로드 실패` 메시지

→ 해제: `USE_HR_SENTIMENT_MODEL=0`

### 극성 변화 없음 (before==after)
- 모델 로드 실패(위 참조)
- 또는 배치가 규칙과 일치하는 simple 경우

### 서비스 지연
- 배치 추론 시간 측정 (64 문장 단위, GPU에서 ~10ms)
- 모델 OFF로 비교

## 모니터링 (운영 중)

- 일일 배치 메타데이터: 극성 분포, 변화율 추이
- 오류 로그 모니터링: "HR 감정모델 추론 실패" → 즉시 OFF
- 정기 회귀 검증: 감사 기준셋(1,978 gold) 일치율 추적

---

산출: `plans/_datasets/kote_finetune/result/finetune_eval_260624.json`(전/후 비교)
      `deployment_validation.json`(배포 환경 메타데이터)
