# 06. 리더십 역량 분석

> 코드 위치: `wordcloud_project/src/modules/leadership_analysis.py`

## 개요 — 무엇을 하는가

평가 문장에서 **6가지 리더십 역량**(커뮤니케이션·리더십·문제해결·팀워크·혁신·윤리)의 점수를 뽑아낸다.

이 모듈은 [05장 감정 분석](05-emotion-analysis.md)과 같은 **KoTE 감정 모델**을 토대로 하되, "어떤 감정이 어떤 역량과 연결되는가"라는 **도메인 지식 매핑**을 더한다. 예를 들어 '존경'·'고마움'·'안심/신뢰' 같은 감정이 강하게 나오고 '소통'·'협력' 같은 키워드가 보이면 **커뮤니케이션·팀워크 역량**이 높다고 본다.

비유하자면, 감정이라는 원재료(KoTE 출력)에 "이 감정 조합은 이 역량을 뜻한다"는 해석 규칙을 입혀 **역량 점수표**로 가공한다.

---

## 적용 분야

- 관리자/리더 후보 평가 문서의 역량 프로파일링
- 부서·직급별 리더십 역량 비교(관점 매트릭스의 `leadership` 축)
- 강점/약점 자동 식별

---

## 기술 상세

### 1. 싱글톤 + 로컬 모델 로드

코드 위치: `leadership_analysis.py:25`, `:60`

```python
def __new__(cls, model_path=None, config_path=None):   # 싱글톤
    if cls._instance is None:
        cls._instance = super().__new__(cls)
        cls._instance._initialized = False
    return cls._instance

# KoTE 모델 로드 (오프라인)
self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
self.model = AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True)
```

`local_files_only=True` 로 **인터넷 없이 로컬 모델만** 사용 — 내부망 오프라인 환경 대응.

### 2. 44개 감정 이름

KoTE의 44개 감정 레이블을 코드에 명시적으로 보유한다(`leadership_analysis.py:64`):

> 불평/불만, 환영/호의, 감동/감탄, 지긋지긋, 고마움, 슬픔, 화남/분노, 존경, 기대감, 우쭐댐/무시함, 안타까움/실망, 비장함, 의심/불신, 뿌듯함, 편안/쾌적, 신기함/관심, 아껴주는, 부끄러움, 공포/무서움, 절망, 한심함, 역겨움/징그러움, 짜증, 어이없음, 없음, 패배/자기혐오, 귀찮음, 힘듦/지침, 즐거움/신남, 깨달음, 죄책감, 증오/혐오, 흐뭇함, 당황/난처, 경악, 부담/안내킴, 서러움, 재미없음, 불쌍함/연민, 놀람, 행복, 불안/걱정, 기쁨, 안심/신뢰

### 3. 6대 역량 정의 — 키워드 + 감정 인덱스 + 가중치

코드 위치: `leadership_analysis.py:73` `self.leadership_competencies`

각 역량은 ① 관련 **키워드**, ② 관련 **감정 인덱스 목록**, ③ **가중치**로 정의된다.

| 역량 키 | 이름 | 예시 키워드 | 관련 감정 인덱스 |
|---------|------|------------|------------------|
| `communication` | 커뮤니케이션 | 소통, 의사소통, 대화, 전달 | 1,4,7,13,16,32,43 |
| `leadership` | 리더십 | 리더십, 지도력, 주도, 책임감, 비전 | 7,11,13,28,29,40,42 |
| `problem_solving` | 문제해결 | 해결, 분석, 판단, 전략, 대책 | 13,29,30,33,34,41 |
| `teamwork` | 팀워크 | 협력, 협동, 단합, 화합, 함께 | 1,4,13,14,16,32,40,42,43 |
| `innovation` | 혁신 | 창의, 새로운, 개선, 아이디어 | 15,28,29,39 |
| `ethics` | 윤리 | 정직, 신뢰, 책임, 공정, 투명 | 7,13,16,30,43 |

> 예) `communication` 의 감정 인덱스 [1,4,7,13,16,32,43] = 환영/호의, 고마움, 존경, 뿌듯함, 아껴주는, 흐뭇함, 안심/신뢰.

### 4. 점수 산출 흐름

코드 위치: `leadership_analysis.py:138` `analyze_leadership()`

```python
emotion_result = self._analyze_emotions(text)           # KoTE 감정 분석
for competency_key, info in self.leadership_competencies.items():
    score = self._calculate_competency_score(text, emotion_result, info)   # 키워드+감정+가중치
    leadership_scores[competency_key] = score
    total_score += score * info["weight"]
overall_score = total_score / len(self.leadership_competencies)            # 종합 점수
```

추가 산출물:
- `key_indicators` — 리더십 키워드 추출 (`_extract_leadership_keywords`)
- `leadership_sentiment` — 리더십 감정 분류 (`_classify_leadership_sentiment`)
- `strengths`, `weaknesses` — 강점/약점 식별 (`_identify_strengths_and_weaknesses`, `leadership_analysis.py:170`)

### 5. 감정→감성 기본 매핑 보유

설정 파일이 없을 때를 대비해 44개 감정의 긍정/부정/중립 기본 매핑을 코드에 내장한다(`leadership_analysis.py:125`).

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 기반 | KoTE 감정 모델(오프라인 로컬 로드) |
| 역량 수 | 6개 (커뮤니케이션·리더십·문제해결·팀워크·혁신·윤리) |
| 산출 방식 | 키워드 + 감정 인덱스 + 가중치 조합 점수 |
| 부가 산출 | 종합점수, 강점/약점, 핵심 키워드, 리더십 감성 |
| 설계 | 도메인 지식(감정↔역량 매핑)을 코드로 명시 관리 |

---

*다음: [07. 반어법(비꼼) 분석](07-sarcasm-analysis.md)*
