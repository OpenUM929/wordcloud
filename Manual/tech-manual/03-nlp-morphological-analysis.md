# 03. 자연어 형태소 분석 (Kiwi)

> 코드 위치: `wordcloud_project/src/modules/nlp_analysis.py`

## 개요 — 무엇을 하는가

한국어는 영어처럼 띄어쓰기만으로 단어를 나눌 수 없다. "성실하고"는 "성실"(명사) + "하고"(어미)로 쪼개야 의미 단어인 "성실"을 얻는다. 이렇게 **문장을 의미 최소 단위(형태소)로 쪼개고, 각 조각의 품사(명사·동사·형용사 등)를 판별**하는 것이 형태소 분석이다.

이 모듈은 **Kiwi**(한국어 형태소 분석기)를 사용해 평가 문장에서 **워드클라우드와 빈도 분석에 쓸 의미 단어만** 골라낸다. 조사·어미·의존명사처럼 의미가 약한 조각은 버린다.

비유하자면, 문장이라는 광석에서 **"이름값 하는 단어"라는 금**만 추려내는 정련 과정이다.

---

## 적용 분야

- 워드클라우드용 단어 추출 (명사/동사/형용사)
- 단어 빈도(word frequency) 통계
- 비속어 필터의 1계층(형태소 단위 정확 매칭) — [08장](08-profanity-filter.md)
- 문장 경계 추출

---

## 기술 상세

### 1. 엔진 — Kiwi (kiwipiepy)

코드 위치: `nlp_analysis.py:52`

```python
self.kiwi = Kiwi() if self.config["kiwi"]["enabled"] else None
```

### 2. 싱글톤 + Thread-safe

대량 병렬 처리 중 Kiwi 인스턴스를 매번 만들면 비용이 크므로, 설정 경로별로 **하나의 인스턴스만** 만들어 재사용한다.

코드 위치: `nlp_analysis.py:56`

```python
@classmethod
def get_instance(cls, config_path="configs/nlp_config.json"):
    if config_path not in cls._instances:
        with cls._lock:                       # threading.Lock — 동시 생성 방지
            if config_path not in cls._instances:
                cls._instances[config_path] = cls(config_path)
    return cls._instances[config_path]
```

### 3. 품사 매핑 — Kiwi 태그 → 워드클라우드 품사

Kiwi의 세분화된 품사 태그를 시스템 내부의 3종 레이블(Noun/Verb/Adjective)로 변환한다.

코드 위치: `nlp_analysis.py:12`

```python
_KIWI_POS_MAP = {
    'Noun':      ['NNG', 'NNP', 'SL'],   # 일반명사, 고유명사, 영어/외래어
    'Verb':      ['VV'],                 # 동사
    'Adjective': ['VA'],                 # 형용사
}
```

- `SL`(영어/외래어)은 **Noun으로 분류**한다 — "팀워크", "리더십" 같은 외래어를 명사로 잡기 위함.
- **의존명사(NNB)는 의도적으로 제외**한다 — "것", "수", "때" 처럼 단독으로 의미가 약한 단어를 걸러내기 위함.

### 4. 의미 단어 추출

코드 위치: `nlp_analysis.py:152` `_extract_meaningful_words_kiwi()`

```python
for token in tokens:
    pos_label = _KIWI_TAG_TO_POS.get(tag_str)
    if pos_label and pos_label in pos_labels \
       and len(word) > 1 \                      # 한 글자 단어 제외
       and not manager.is_stopword(word):        # 불용어 제외
        result.append((word, pos_label))
```

3중 필터:
1. **품사 필터** — 명사/동사/형용사만
2. **길이 필터** — 2글자 이상만 (한 글자 노이즈 제거)
3. **불용어 필터** — `stopword_manager` 의 불용어 목록 제외

### 5. 두 가지 산출물

`analyze()` 는 두 형태의 단어 목록을 저장한다(`nlp_analysis.py:116`).

| 키 | 내용 | 용도 |
|----|------|------|
| `meaningful_words_with_pos` | **전체 품사** 단어 + 품사 (Noun/Verb/Adjective 모두) | 나중에 품사 옵션을 바꿔 재생성 가능 |
| `meaningful_words` | `wordcloud_pos` 설정으로 **필터된** 단어만 | 단어 빈도 계산용 |

> 전체 품사를 함께 저장해 두는 이유: 사용자가 "명사만" → "명사+형용사"로 워드클라우드 옵션을 바꿔도 **원문을 다시 분석하지 않고** 저장된 결과만 재필터링하면 되기 때문(재처리 비용 절약).

또한 `sentence_boundaries`(문장 경계)도 함께 추출해(`nlp_analysis.py:130`) 문장 단위 후속 분석(감정·반어법)에 활용한다.

### 6. 버전 호환 처리

`kiwipiepy` 버전에 따라 `token.tag` 가 문자열일 수도, IntEnum일 수도 있어 양쪽을 모두 처리한다.

코드 위치: `nlp_analysis.py:172`

```python
tag_str = tag if isinstance(tag, str) \
          else (tag.name if hasattr(tag, 'name') else str(tag).split('.')[-1])
```

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 엔진 | Kiwi (kiwipiepy) — 순수 Python, Java/JDK 불필요 |
| 인스턴스 관리 | 설정별 싱글톤 + Lock (병렬 안전) |
| 추출 품사 | 명사(NNG/NNP/SL), 동사(VV), 형용사(VA) |
| 제외 대상 | 의존명사(NNB), 1글자, 불용어 |
| 산출물 | 전체품사 목록 + 필터 목록 (재생성 대비 이중 저장) |

---

*다음: [04. 워드클라우드 생성](04-wordcloud-generation.md)*
