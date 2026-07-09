# 05. 감정 분석 (KoTE 딥러닝)

> 코드 위치: `wordcloud_project/src/modules/emotion_analysis.py`

## 개요 — 무엇을 하는가

평가 문장이 **긍정인지, 부정인지, 중립인지**를 판단한다. 단순 키워드 매칭이 아니라, 한국어 감정 분석용으로 학습된 **딥러닝 모델 KoTE**(Korean Text Emotion, 44개 세부 감정 레이블)를 사용한다.

KoTE는 문장을 읽고 "불평/불만", "고마움", "존경", "짜증" 같은 **44가지 세부 감정** 각각에 확률을 매긴다. 시스템은 이 44개 감정을 **긍정/부정/중립 3가지**로 묶어 최종 판정한다.

비유하자면, 사람이 문장을 읽고 "이건 고마워하는 톤이네 → 긍정" 하고 직관적으로 느끼는 과정을, 44개 감정 채점표를 가진 AI가 수치로 수행한다.

> 📌 이 프로젝트의 감정 분석 핵심 가치: **긍정↔부정 오분류를 막는 것**이 최우선이며, 중립을 긍정으로 보는 정도의 오차는 허용한다.

---

## 적용 분야

- 평가서 단위 긍정/부정/중립 판정
- 단어별 감정 점수 → 워드클라우드 색상([04장](04-wordcloud-generation.md))
- 리더십 분석의 기반 신호([06장](06-leadership-analysis.md))
- 관점 매트릭스의 `emotion` 분석 축([09장](09-perspective-matrix.md))

---

## 기술 상세

### 1. 모델 구성 — 2단 모델 (파인튜닝 + 기본)

코드 위치: `emotion_analysis.py:35`

```python
self.classifiers = {}
# (1) 파인튜닝 모델 (있을 경우 우선)
if self.config["model"]["use_fine_tuned"]:
    self.classifiers["fine_tuned"] = pipeline(self.config["model"]["type"], model=ft_path)
# (2) 기본 KoTE 모델 (직접 호출)
self.classifiers["base"] = (model, tokenizer)
```

- **기본 모델(base)**: KoTE 체크포인트를 `AutoModelForSequenceClassification` 로 로드.
- **파인튜닝 모델(fine_tuned)**: 도메인에 맞게 추가 학습한 모델이 있으면 함께 사용.
- 사용 가능한 모델이 하나도 없으면 `RuntimeError` 로 즉시 실패(`emotion_analysis.py:75`).

> `num_labels`를 명시하지 않는다(`emotion_analysis.py:60`). 명시하면 저장된 분류 헤드와 크기가 어긋날 때 가중치가 무작위로 재초기화될 위험이 있어, 체크포인트의 config에서 자동으로 읽도록 둔다.

### 2. 추론 — 직접 호출로 전체 점수 확보

`pipeline`은 보통 1등 레이블만 주기 쉬워, 기본 모델은 **직접 호출**해 44개 전 감정의 softmax 확률을 모두 얻는다.

코드 위치: `emotion_analysis.py:104`

```python
inputs = tokenizer(text, return_tensors="pt")
outputs = model(**inputs)
logits = outputs.logits[0]
scores = logits.softmax(dim=0).tolist()        # 44개 감정 각각의 확률
id2label = model.config.id2label                # 인덱스 → 감정 이름
```

### 3. 44개 감정 → 긍정/부정/중립 매핑

각 감정을 `emotion_to_sentiment` 설정으로 3분류한다. (0=긍정, 1=부정, 2=중립)

코드 위치: `emotion_analysis.py:157`

```python
sentiment = self.config["emotion_to_sentiment"].get(str(numeric_label), 2)
# 0 → 긍정, 1 → 부정, 2 → 중립
```

### 4. 확률 합산 방식 최종 판정 (단순 1등 아님)

1등 감정 하나로 결정하지 않는다. **44개 감정을 긍정/부정/중립 그룹별로 확률을 합산**한 뒤, 합이 가장 큰 그룹으로 판정한다.

코드 위치: `emotion_analysis.py:180`

```python
for p in predictions:
    if   p_sentiment == 0: positive_score += p_score
    elif p_sentiment == 1: negative_score += p_score
    else:                  neutral_score  += p_score

final_sentiment = 2                                  # 기본 중립
if   positive_score > negative_score and positive_score > neutral_score: final_sentiment = 0
elif negative_score > positive_score and negative_score > neutral_score: final_sentiment = 1
```

> 이 "그룹 확률 합산" 방식이 단일 최고 감정 방식보다 **긍정↔부정 오분류에 강건**하다. 예를 들어 1등이 약한 부정이라도, 긍정 감정들의 확률 총합이 더 크면 긍정으로 판정한다.

### 5. 레이블 형식 호환

모델/설정에 따라 레이블이 `LABEL_0` 형식일 수도, 감정 이름 직접 형식일 수도 있어 양쪽을 처리한다(`emotion_analysis.py:143`~`:171`).

---

## KoTE 모델의 한계와 보완

KoTE는 **문장의 통사 구조(어디서 의미가 뒤집히는지)를 판단하지 못한다.** 예: "처음엔 별로였지만 결국 훌륭했다" 에서 역접("~지만")을 모델이 인지하지 못해 앞부분 부정에 끌려갈 수 있다.

→ 이를 **반전(역접) 표지어 사전**으로 외부 보완한다. 상세는 [09장 관점 매트릭스 분석](09-perspective-matrix.md) 및 `perspective_service.py:78` `CONTRASTIVE_MARKERS` 참조.

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 모델 | KoTE (44 감정), HuggingFace Transformers + PyTorch |
| 구성 | 파인튜닝 모델 + 기본 모델 (이중) |
| 추론 | 직접 호출 + softmax로 44개 전 확률 확보 |
| 최종 판정 | 긍/부/중 그룹 **확률 합산** 최댓값 (1등 단독 아님) |
| 설계 가치 | 긍정↔부정 오분류 최소화 우선 |
| 한계 | 통사적 역접 미인지 → 표지어 사전으로 보완 |

---

*다음: [06. 리더십 역량 분석](06-leadership-analysis.md)*
