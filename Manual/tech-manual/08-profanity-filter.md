# 08. 비속어 필터 (2계층 탐지)

> 코드 위치: `wordcloud_project/src/modules/profanity_filter.py`

## 개요 — 무엇을 하는가

평가 문서에 **욕설·비속어·유해 표현**이 있는지 찾아낸다. 단순히 "시발" 같은 정확한 단어만 찾는 게 아니라, **"시.발", "시 발", "개!새끼"** 처럼 글자 사이에 점·공백·기호를 끼워 **필터를 우회하려는 표기까지** 잡아낸다.

비유하자면, 금지어를 그대로 쓴 경우(1계층)뿐 아니라, **글자를 띄우거나 기호로 분절해 숨긴 경우(2계층)** 까지 잡는 이중 검문소다.

---

## 적용 분야

- 인사평가 문서의 부적절 표현 탐지·차단
- 관점 매트릭스의 `profanity` 분석 축([09장](09-perspective-matrix.md))
- 한글/영어 양쪽 비속어 동시 처리

---

## 기술 상세

### 1. 단어 사전 3종

코드 위치: `profanity_filter.py:44`

| 목록 | 용도 |
|------|------|
| `profanity_words` | 욕설/비속어 |
| `stop_words` | 불용어 |
| `unhealthy_words` | 유해(선정성 등) 표현 |

영어 욕설은 별도로 캐싱해 반복 필터링을 피한다(`profanity_filter.py:48`):

```python
self.english_profanity_words = [w for w in self.profanity_words if not re.search(r'[가-힣]', w)]
```

### 2. 1계층 — Kiwi 형태소 단위 정확 매칭

[03장](03-nlp-morphological-analysis.md)의 Kiwi로 문장을 형태소로 쪼갠 뒤, **형태소가 욕설 사전과 정확히 일치**하는지 본다. 원본 텍스트의 정확한 위치(span)까지 반환한다.

코드 위치: `profanity_filter.py:137` `_detect_by_morpheme()`

```python
tokens = self.kiwi.tokenize(text)
return [(text[t.start:t.end], t.start, t.end)
        for t in tokens
        if t.form.lower() in self.profanity_words or t.form in self.profanity_words]
```

> 형태소 단위 매칭은 "시스템"의 "시"처럼 **우연히 욕설 글자를 포함한 정상 단어를 오탐하지 않는** 장점이 있다.

### 3. 2계층 — 음절 간격 정규식 (우회 표기 탐지)

핵심 차별 기술. 욕설 각 음절 사이에 **한글이 아닌 문자(점·공백·기호)** 가 끼어드는 변형을 잡는다.

#### (a) 패턴 사전 컴파일

코드 위치: `profanity_filter.py:105` `_build_gap_patterns()`

각 욕설에 대해 "**적어도 한 쌍의 음절 사이에 비한글 문자가 강제로 들어간**" regex들을 미리 컴파일한다.

```python
# 2음절 '시발'  → 시[^가-힣]+발
# 3음절 '개새끼' → 개[^가-힣]+새[^가-힣]*끼,  개[^가-힣]*새[^가-힣]+끼
parts.append(re.escape(syllables[i]) + r'[^가-힣]+')   # 강제 간격 위치
...
parts.append(re.escape(syllables[i]) + r'[^가-힣]*')   # 그 외 위치
parts.append(re.escape(syllables[-1]) + r'(?![가-힣])') # 마지막 음절 뒤 한글 금지
```

#### (b) 매칭 동작

코드 위치: `profanity_filter.py:152` `_detect_by_gap_pattern()`

| 입력 | 판정 | 이유 |
|------|------|------|
| `시. 발` | ✅ 탐지 | '시'와 '발' 사이 '. '(비한글) |
| `개 새 끼` | ✅ 탐지 | 음절 사이 공백 |
| `개!새끼` | ✅ 탐지 | '개'-'새' 사이 '!'(비한글) |
| `시스템 발전` | ❌ 미탐지 | '시' 뒤 '스템'(한글 포함) → 욕설 아님 |

> `(?![가-힣])` (마지막 음절 뒤에 한글이 오면 안 됨) 조건이 **정상 단어 오탐을 막는 핵심 안전장치**다.

### 4. 영어 비속어 처리

`profanity-check`(ML 기반 영어 욕설 확률), `better-profanity`, `korcen`(한국어 욕설 라이브러리) 등을 함께 활용한다(`requirements.txt`, `profanity_filter.py:19`, `:68`). 라이브러리 미설치 시에는 substring fallback으로 동작한다(`profanity_filter.py:61`).

### 5. 견고성 — 선택적 의존

Kiwi(`kiwipiepy`)나 `profanity_check`가 없어도 죽지 않는다. import 가능 여부를 플래그로 두고, 1계층이 없으면 substring 방식으로 대체한다(`profanity_filter.py:12`, `:53`).

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 구조 | 2계층 (형태소 정확매칭 + 음절간격 regex) |
| 1계층 | Kiwi 형태소 단위 → 정상 단어 오탐 최소화 |
| 2계층 | "시.발", "개 새 끼" 등 우회 표기 탐지 |
| 오탐 방지 | 마지막 음절 뒤 한글 금지 `(?![가-힣])` |
| 영어 | profanity-check / better-profanity / korcen |
| 견고성 | 라이브러리 부재 시 substring fallback |

---

*다음: [09. 관점 매트릭스 분석](09-perspective-matrix.md)*
