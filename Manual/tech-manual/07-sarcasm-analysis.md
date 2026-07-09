# 07. 반어법(비꼼) 분석

> 코드 위치: `wordcloud_project/src/modules/sarcasm_analysis.py`

## 개요 — 무엇을 하는가

"참 잘~ 하셨네요" 처럼 **칭찬의 탈을 쓴 비꼼**은 단어만 보면 긍정으로 오해하기 쉽다. 이 모듈은 문장이 **반어법(비꼼)인지 아닌지**를 판별해, 감정 분석이 표면적 단어에 속지 않도록 보조한다.

비유하자면, 감정 분석이 "단어의 사전적 의미"를 본다면, 반어법 분석은 "그 말투에 숨은 진짜 의도(빈정거림)"를 잡아낸다.

---

## 적용 분야

- 긍정 단어로 위장한 부정 평가 탐지
- 감정 분석 결과의 신뢰도 보정
- 관점 매트릭스의 `sarcasm` 분석 축([09장](09-perspective-matrix.md))

---

## 기술 상세

### 1. 3단계 모델 우선순위 (Graceful Fallback)

가용한 가장 좋은 모델을 자동으로 선택한다. 하나가 없거나 로드 실패하면 다음으로 넘어간다.

코드 위치: `sarcasm_analysis.py:42` `_load_models()`

```
[1순위] Transformers 파인튜닝 모델  (use_fine_tuned = true, 도메인 학습 모델)
   └ 실패/없음 ↓
[2순위] Transformers 기본 모델      (base_path)
   └ 실패/없음 ↓
[3순위] scikit-learn 모델           (sarcasm_model.pkl: model + vectorizer)
   └ 모두 없으면 → 반어법 기능 비활성화
```

세 경로 모두 실패하면 기능을 끄되 시스템 전체는 계속 동작한다(`sarcasm_analysis.py:39`).

### 2. 딥러닝 경로 (Transformers)

코드 위치: `sarcasm_analysis.py:58`

```python
self.tokenizer = AutoTokenizer.from_pretrained(fine_tuned_path)
self.model = AutoModelForSequenceClassification.from_pretrained(fine_tuned_path)
if torch.cuda.is_available():
    self.model = self.model.to('cuda')        # GPU 가속 자동 적용
```

### 3. 머신러닝 폴백 경로 (scikit-learn)

GPU/Transformers 모델이 없는 환경을 위해 가벼운 **scikit-learn 모델 + 벡터라이저**를 pickle로 보관한다.

코드 위치: `sarcasm_analysis.py:93`

```python
with open(model_path, 'rb') as f:
    model_data = pickle.load(f)
    self.scikit_model = model_data['model']
    self.vectorizer = model_data['vectorizer']
```

> 딥러닝(정확) ↔ 전통 ML(가벼움) 의 **이중화**로, 고사양/저사양 환경 모두에서 동작한다.

### 4. 추론 + 임계값(Threshold) 적용

비꼼은 **과탐(false positive)이 위험**하므로, Sarcasm 확률이 임계값(기본 0.5, 설정 가능) 이상일 때만 반어법으로 인정한다.

코드 위치: `sarcasm_analysis.py:135`

```python
with torch.no_grad():
    outputs = self.model(**inputs)
    probabilities = torch.softmax(outputs.logits, dim=1)[0]

# LABEL_0 = Non-Sarcasm, LABEL_1 = Sarcasm
threshold = self.config.get('threshold', 0.5)
# Sarcasm 확률이 threshold 이상일 때만 반어법으로 인정
```

토크나이징은 `max_length=128`, `truncation=True` 로 긴 문장도 안전하게 자른다(`sarcasm_analysis.py:122`).

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 목적 | 칭찬을 가장한 비꼼(반어법) 탐지 |
| 모델 우선순위 | 파인튜닝 → 기본 Transformers → scikit-learn |
| 가속 | CUDA 사용 가능 시 자동 GPU |
| 안전장치 | 임계값(threshold) 적용으로 과탐 억제 |
| 견고성 | 모든 모델 부재 시에도 시스템 정상 동작 |

---

*다음: [08. 비속어 필터 (2계층 탐지)](08-profanity-filter.md)*
