# 수정 계획서: 욕설 볼드 처리 불가 & 영어 욕설 미감지 문제

**작성일시**: 2026-06-02 16:24
**작업 유형**: bug fix
**상태**: Pending
**대상**: `perspective_test.html` renderComplete(), `profanity_filter.py`

---

## 1. 현상

1. 욕설 단어가 볼드 처리되지 않고 그냥 붉은 색으로만 보임
2. 영어 욕설은 색상 변화조차 없음

---

## 2. 근본 원인 분석

### 2-1. 볼드 처리 안됨

**코드 확인**: `perspective_test.html:1026`
```javascript
return text.replace(new RegExp(pattern, 'gi'), m =>
    `<strong style="color:#dc3545;background:#ffeeee;border-radius:2px;padding:0 1px;font-weight:bold;">${m}</strong>`);
```

`font-weight:bold` 인라인 스타일은 이미 있다. 그러나 **두 가지 문제**:

**문제 A — 데이터 소스 불일치 (핵심 원인)**

```
negative_sentences  → _extract_sentences_for_words()로 추출
                      조건: 문장이 "상위 부정 단어"를 포함해야 함

profanity_sentences → advanced_filter_profanity()로 감지
                      조건: 욕설이 감지된 문장
```

욕설 단어("시발")가 단어 빈도에서 상위 부정 단어로 선택되지 않으면
→ 해당 문장이 `negative_sentences`에 포함되지 않음
→ `markProfanity(s)` 실행해도 매칭할 문장 자체가 없음
→ 아무 변화 없이 그대로 반환

**문제 B — 7px에서 bold 인식 불가**

문장 표시 영역이 `font-size:7px`. 이 크기에서 bold는 시각적으로 구분이 어려움.
또한 이미 negative word coloring으로 `<span style="color:rgb(230,150,150)">단어</span>` 처리되어
붉은 색이 이미 표시 중임 → 사용자는 "그냥 붉은 색"으로 인식.

### 2-2. 영어 욕설 미감지

**두 가지 경로 분석**:

**경로 A — 기존 배치 데이터**

이미 저장된 배치의 `profanity_analysis_results.detected_profanity`에 영어 단어가 없음.
이유: 영어 욕설 탐지는 `language in ["en", "mixed"]`일 때만 `profanity_check` 라이브러리를 사용.
한국어 문서(`language="ko"`)에 섞인 영어 욕설("fuck")은:
- `profanity_check` 라이브러리: 언어 조건으로 스킵
- Kiwi 1계층: 이전에는 `t.form in self.profanity_words`로 대소문자 구분 → "FUCK" 미매칭 가능

**경로 B — 신규 배치 데이터 (`.lower()` 수정 후)**

Kiwi가 "fuck"을 SL 토큰으로 분리 → `t.form.lower() in self.profanity_words` → 탐지 가능.
BUT: 탐지되더라도 **2-1 문제 A**와 동일하게 해당 문장이 `negative_sentences`에 없을 수 있음.

**추가 문제 — gap_pattern 영어 단어 패턴 오작동**

`_build_gap_patterns()`는 모든 `profanity_words`에 대해 패턴 생성.
영어 단어 "fuck"에 대한 패턴: `f[^가-힣]+u[^가-힣]*c[^가-힣]*k`
→ `+` (1개 이상 비한글 문자)이 필요해 "fuck" 자체는 매칭 안됨 (의도대로 우회 탐지만 가능).
이 부분은 설계 의도이므로 수정 불필요.

---

## 3. 수정 계획

### Step 1 — 데이터 소스 불일치 해결 (핵심)

**파일**: `perspective_test.html` `renderComplete()` 내부

현재 방식을 버리고, 욕설 문장 표시를 `negative_sentences`에 의존하지 않는다.

**변경 전 방식**: 부정 문장 리스트에서 욕설 단어 regex 매칭 시도
→ 욕설 문장이 부정 문장 리스트에 없으면 아무 효과 없음

**변경 후 방식**: `profanity_summary.profanity_sentences`를 직접 렌더링
→ 부정 컬럼 아래에 욕설 문장 섹션을 별도로 추가
→ `original_text` + `detection_details.span` 기반 정확한 하이라이팅 (`highlightProfanity()` 재사용)

```javascript
// 부정 컬럼 아래에 추가
if (label === '부정' && profanityWords.size > 0 && res.profanity_summary?.profanity_sentences?.length > 0) {
    h += '<div style="margin-top:4px;border-top:1px dashed #f5c6cb;padding-top:3px;">';
    h += '<div style="font-size:7px;color:#dc3545;font-weight:bold;margin-bottom:2px;">⚠ 욕설 감지 문장</div>';
    res.profanity_summary.profanity_sentences.forEach(s => {
        const hl = highlightProfanity(s.original_text, s.detection_details);
        h += '<div style="font-size:7px;color:#555;line-height:1.4;margin-bottom:3px;padding:2px 4px;background:#fff8f8;border-left:2px solid #dc3545;">';
        h += hl;
        h += '</div>';
    });
    h += '</div>';
}
```

이 방식의 장점:
- `negative_sentences` 포함 여부와 무관하게 욕설 문장 표시
- `highlightProfanity()`의 span 기반 정확한 위치 표시 유지
- 볼드 불필요 (span 기반 하이라이팅이 시각적으로 명확)

### Step 2 — `markProfanity` 제거

Step 1로 대체되므로 `profanityWords`, `markProfanity` 코드 및 `applyMark` 플래그 제거.
`negative_sentences` 렌더링은 원래 방식(`s` 직접 출력)으로 복원.

### Step 3 — 영어 욕설 백엔드 탐지 보완

**파일**: `wordcloud_project/src/modules/profanity_filter.py`

현재 `_detect_by_morpheme()` 수정(`t.form.lower()`)은 이미 적용됨 — 유지.

추가로 `advanced_filter_text()`에서 한국어 문서 내 영어 단어도 명시적으로 substring 체크:

```python
# 기존 한국어 2계층 탐지 이후에 추가
# 영어 욕설 단어 직접 포함 여부 확인 (language에 무관하게)
for word in self.profanity_words:
    if not re.search(r'[가-힣]', word):  # 영어 단어만
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        for m in pattern.finditer(text):
            if not any(m.start() == s and m.end() == e for _, s, e in morpheme_spans):
                morpheme_spans.append((m.group(), m.start(), m.end()))
                if m.group().lower() not in detected_profanity:
                    detected_profanity.append(m.group().lower())
```

단, 이 수정은 **신규 배치 처리**에만 적용됨. 기존 저장된 데이터는 재처리 필요 없음
(기존 배치는 이미 `profanity_count` 기준으로 필터링되므로, 영어 욕설이 없으면 표시 자체가 생략됨).

---

## 4. 변경 파일 요약

| 파일 | 변경 내용 |
|------|---------|
| `perspective_test.html` | ① `markProfanity`, `profanityWords`, `applyMark` 제거 ② 부정 컬럼 아래 욕설 문장 직접 렌더링 추가 |
| `profanity_filter.py` | 영어 단어 대소문자 무관 직접 탐지 추가 (`advanced_filter_text`) |

---

## 5. 검증 시나리오

1. 욕설이 포함된 배치로 **제출용 저장** 실행
2. 완료 화면 → 부정 컬럼 하단 "⚠ 욕설 감지 문장" 섹션 노출 확인
3. 욕설 단어 빨간 하이라이팅 표시 확인 (span 기반)
4. 영어 욕설 포함 신규 배치 처리 후 동일 확인
