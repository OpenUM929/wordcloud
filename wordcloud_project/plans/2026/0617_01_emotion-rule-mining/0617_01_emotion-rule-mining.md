# 코퍼스 기반 감정 규칙 마이닝 + KoTE 분류 정당성 검증 + 긍정어 강화

> 상태: DN(코드) | 작성일: 2026-06-17 | 완료확인: 2026-06-18 | 잔여: deferred(코드 아님)
> 작업 유형: 알고리즘 강화 (데이터 기반 규칙 도출 + 감정 분류 체계 검증)
> 선행 계획: `0615_10_corpus-refine-csv`(DN) — 정제 CSV 파이프라인을 입력으로 사용
> **완료 정리(2026-06-18)**: positive_rescue / negation_praise / no_response_neutral / 리더십 게이트(§12) / 메타 override(§15) 전부 구현·검증 완료 → 코드 범위 DN. 잔여는 코드가 아닌 ①step1 정답 최종 합의(사용자 검토) ②혼합극성 규칙(코퍼스 표본부족 3/475 → deferred). 상세는 `0618_01_pending-wrapup §4`.

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-17 | 전체 | 최초 작성 (코퍼스 수십~수백건 수령 전제, 측정→마이닝→강화 3단계) |
| 2026-06-17 | §3-2, §4-1, §4-2, §5-3, §6-3, §9 | 검토 반영: data/ .gitignore 확인, top3 JSON 형식, scripts/ 위치, hurt 허용치, 결정 권고 추가 |
| 2026-06-17 | §7 신설(번호 7→11 시프트) | 검증 화면 & human-in-the-loop 반복 루프 추가 (acquired_data.html 확장 채택) |
| 2026-06-17 | §3, §7-5 신설 | **1차 구현 착수**: 데이터 업로드(import) 경로 + 화면 버튼 (데이터 반입 선행 인프라). 구현·테스트 완료 |
| 2026-06-17 | §0-A 신설 | compact 대비 재개 지점 정리 (완료/다음/파일/테스트/결정/보류) |
| 2026-06-17 | §0-A 갱신, §6-2 | **데이터 수령 + step1~3 완료**: 예상정답 생성 → 원인진단(KoTE 실행, 재현 100%) → `positive_rescue` 구현·검증(정확도 81.9%, 긍정복원 87.1%, 부정→긍정 0). 리더십 후속 기록 |
| 2026-06-17 | §0-A(다음작업) | **혼합극성 한계 기록**: 본 코퍼스 혼합극성 3/475(긍정-부정 2, 부정-부정 1)뿐 → 규칙 마이닝 보류, 코퍼스 추가 수집 후속으로 명시. 리더십 후속 착수 |
| 2026-06-17 | §12 신설, §0-A(리더십) | **리더십 1+3 통합 설계 기록**: negation 인식 `leadership_polarity` 신규 모듈 + leadership_analysis 게이트(3)+감정보정 공유(1). 데이터근거(긍61/부11, 진짜부정~4) 명시. 진행순서 B 권고. 🟡 live 2파일 수정 승인 대기 |
| 2026-06-17 | §12-7 신설, §0-A(리더십) | **B안 구현 완료**(사용자 승인): 신규 `hr_context_lexicon.py`(`leadership_polarity`) + `leadership_analysis.py` 게이트. 골든 테스트 4종 + 게이트/회귀안전 검증 전부 통과. 감정보정 공유(1)는 검증 후 별도 승인 대기(미착수) |
| 2026-06-17 | §12-8 신설, §0-A(리더십) | **추천 다음 단계 확정**(사용자 "추천 방향대로 진행" 승인): ①코퍼스 회귀 검증 → ②`perspective_service.py` 신규 분기 `negation_praise`로 negation 칭찬 긍정 구제(§0-A #3 통합) → ③회귀 재검증. compact 후 §12-8부터 착수 |
| 2026-06-17 | §12-9 신설, §12-8 완료표시 | **§12-8 1→2→3 전부 완료**: ①리더십게이트 코퍼스 회귀(긍정104 Δ0/negation칭찬6 보존/진짜부정4 0점화, 위반0) ②`perspective_service.py` `negation_praise` 신규 분기(기존7 rule_id 불변) ③회귀 락셋(475중 6건만 전이, 진짜부정 전이0). 부정오분류 2건(`권위의식이 없음`·`잔소리를 안한다`) 긍정 교정. ⚠라벨 불일치 2건(정답=negative 오기 추정) 사용자 확인 권고. 산출 `result/리더십게이트_회귀_260617.md`·`result/감정보정_negation_회귀_260617.md` |
| 2026-06-17 | §12-9 라벨 종결, CSV 교정 | **사용자 판단 반영**("중립 OK, 절대 부정 아님"): `refine_diag_260617.csv` id332·141 `corrected_label` negative→neutral 교정. 변경 6건 전부 중립→긍정(허용)으로 정렬, 긍↔부 오분류 0. 알고리즘 코드 수정 불요(이미 부정 이탈). 회귀 리포트 재생성 |
| 2026-06-17 | §15 신설 | **신규데이터 검증 + 메타데이터 적용**(사용자 승인): ①`data/new_260617.csv`(722행) 전수 KoTE 재분류 → 긍↔부 전이 **0건**, positive_rescue 14·no_response_neutral 137 정상 발동(산출 `result/신규데이터_분류검증_260617.md`). ②🟡 `metadata_analysis.py::calculate_consolidated_analysis`를 raw KoTE→**문장단위 override 질량 기반**으로 전환(통합감정+단어버킷 모두). `_get_sentence_level_scores`(sentence_emotion_cache 재사용, KoTE 재실행 0) 공유로 perspective 화면과 일치. 골든 `test/test_metadata_override.py` 4종 통과·py_compile OK. 한계 2건(id1190 부→무응답 미포착·무응답게이트 과중립화 3건) 후속 후보로 기록 |
| 2026-06-17 | §13 신설, §0-A #2 완료 | **무응답 중립화 완료**(§0-A #2): `perspective_service.py`에 신규 분기 `no_response_neutral` 추가(`neutral_dominant` 뒤·`euphemistic_negative`/rule3 앞). 평가불가(`잘 모르겠습니다`·`뵌 적 없어 모름`)/내용없음/낙서(ㅈㅈㅈ·성실성실) **27건**을 부정→중립 교정. 회귀 락셋: 475중 27건만 전이(전부 no_response_neutral→중립), 긍정 손실 0, 긍↔부 오분류 0, 낙서 중립 11건(neutral_dominant) 불변. 기존 rule_id·시그니처 불변. 산출 `result/감정보정_무응답_회귀_260617.md` |

---

## 0-A. 재개 지점 (RESUME POINT — compact 후 여기부터)

> 이 섹션은 컨텍스트 압축 후 작업을 끊김 없이 잇기 위한 요약이다. 상세는 각 §로.

### ✅ 완료 (1차: 데이터 업로드 인프라)
- **결정 확정**: 검증 화면은 **신규 페이지 X — 기존 `acquired_data.html` 확장**으로 진행(§10-④).
- **구현(전부 additive, 테스트 통과)**:
  - `src/services/perspective_service.py`: `_normalize_acq_label()`, `_parse_acq_import_rows()`(순수 파서), `import_acquired_sentences_csv(csv_text, overwrite)` — 정제 CSV 함수들(`refine_acquired_row` L2121 등) **바로 뒤**에 위치.
  - `src/routes/perspective_routes.py`: `POST /api/perspective/acquired-sentences/import` (관리자 전용, multipart, utf-8-sig→cp949). import 블록(L16~)에 `import_acquired_sentences_csv` 추가됨.
  - `web/templates/acquired_data.html`: "데이터 가져오기" 버튼 + 숨김 file input + `importCsv()`.
  - 적재는 **기본 컬럼만**(KoTE 불요). 정제 메타는 내보내기/후속 화면에서 재계산.
- **테스트**: `python plans/2026/0617_01_emotion-rule-mining/test/test_import.py` (DB·KoTE 불요, 4건 통과). `py_compile` 통과.
- **미실행**: 서버는 기동하지 않음 → 실제 업로드 동작 확인은 서버 기동 후 사용자 진행.

### ✅ 완료 (2차: 데이터 수령 + step1~3, 2026-06-17)
- **데이터**: `data/acquired_sentences_20260617.csv`(475행) 수령. 단, `user_label==model_label`(불일치 0, positive 0)이라 정답셋 불가.
- **step1 예상정답**: 405고유 문장 재분류 초안 → `data/*_proposed.csv`, `*_review.csv`, `result/예상정답_생성리포트_260617.md`. (사용자 최종 합의 대기)
- **step2 원인진단**(KoTE 475 실행, 재현 100%): `result/원인진단_알고리즘보강안_260617.md`, `result/refine_diag_260617.csv`.
  - 1순위 원인=base KoTE 긍정 미검출 91% + 매핑편향(부정25/긍정16) + `neutral_dominant`(긍정 301흡수)·`rule3`(62 강등)·`rule4`(61 base부정).
- **step3 보강·검증**: `_sentence_sentiment_override_explain`에 **`positive_rescue`** 신규 분기(neutral_dominant 앞). 정확도 9%→**81.9%**, 긍정복원 0→**87.1%**, 부정→긍정 **0**, 진짜부정 3/3 보존. 동작보존·골든 테스트 통과.

### ▶ 다음 작업 (우선순위 순)
1. **step1 정답 최종 합의**: `review.csv` 검토(특히 진짜 부정 3건 + neutral↔positive 경계). 합의 후 잔여 긍정→부정 34건 재검토.
2. ~~**무응답 중립화 규칙**: `잘 모르겠습니다`/낙서 → 부정 27건(보강 전부터 존재) 교정 후보.~~ → ✅ **완료**(2026-06-17, §13). 신규 분기 `no_response_neutral`로 27건 부정→중립 교정, 긍↔부 오분류 0.
3. **부정 부정문(negation) 처리**: `고압적이지 않음`류 칭찬 구제(현재 배제로 중립 유지).
4. **혼합극성(긍정-부정/부정-부정) 규칙 — 보류**: 본 코퍼스엔 혼합극성이 **3/475(0.6%)**뿐(긍정-부정 반전 2, 부정-부정 1). 표본 부족으로 규칙 마이닝 불가(추측 금지). 셋 다 현재 `neutral`로 안착 → **긍↔부 오분류 없음(핵심가치 안전)**, 단 정답 일치는 미흡. 해당 3건의 성격:
   - `불필요한 지시를 하지 않음`(truth 긍정) → "~하지 않음형 칭찬" = 위 3번 negation 후속과 동일 건.
   - `업무 중요성 판단 능력`(truth 긍정) → 반전 표지 **오탐**으로 rescue 차단 → 반전 표지 오탐 정밀화 후보.
   - `수직적…강요…수동적 참여 유도`(truth 부정) → 진짜 부정인데 KoTE 미검출로 중립(부정 미검출).
   → **조치**: 혼합극성 코퍼스를 추가 수집한 뒤 별도 마이닝(rule1/rule2 반전 + negation). 현 데이터로는 진행하지 않음.
5. (선택) §4-2 측정 스크립트/§7 화면 검증 뷰 — 필요 시.

### ✅ 리더십 후속 — B안 구현 완료 (요구 1+3, 2026-06-17) → 상세 §12-7
- 사용자 결정: **요구 1+3 통합**, **B안(권고)대로 처리** 승인 + 🟡 live 파일 수정 승인.
- **완료(전부 additive)**:
  - 신규 `src/modules/hr_context_lexicon.py`: `leadership_polarity(text) -> positive|negative|neutral`. **negation 인식**(부정표지 뒤 14자 내 부정어 → 칭찬으로 반전). KoTE·DB·서버 불요 순수 로직.
  - `src/modules/leadership_analysis.py`(🟡): `analyze_leadership`에서 극성 1회 판정 → `_calculate_competency_score(…, polarity)` 게이트. **polarity=='negative'면 강점 가점 0(개선영역)**, 그 외(neutral/positive)는 **기존 채점 그대로**(default `'neutral'`로 회귀 안전).
- **검증 전부 통과**: 골든 테스트 `test/test_leadership_polarity.py`(negation칭찬→긍/진짜부정→부/긍정표지→긍/무표지→중립). 게이트 단위검증(부정0점·긍정0.64·레거시 미지정 0.74 불변). `py_compile` 통과.
- **미착수(검증 후 별도 승인)**: 요구 1 = `perspective_service.py` 감정보정이 동일 `leadership_polarity` 공유(B 순서상 3 검증 통과 후). 현재 `perspective_service.py` **무수정**.
- **▶ 추천 다음 단계(사용자 승인, compact 후 여기부터) → §12-8**: ①코퍼스 회귀 검증(긍61 불변/negation칭찬 보존/진짜부정~4 0점화) → ②`perspective_service.py` 신규 분기 `negation_praise`로 negation 칭찬 긍정 구제(§0-A #3 통합) → ③회귀 재검증. 서버 무단 실행 금지.
- 기존 코드 상태(참고): `리더십`/`리더쉽`은 `POSITIVE_IMPLYING_PHRASES` 일반 긍정표지, `word_boost.json` 가점 2.0x 기설정.

### ⚠ 잊지 말 핵심 제약/사실
- **1차원 매핑**=`src/configs/emotion_config.json::emotion_to_sentiment`(44감정→긍0/부1/중2). **점수 argmax**=`src/modules/emotion_analysis.py:181-217`(임계값·동률처리 없음). 둘 다 §4 검증 대상.
- **긍정 구제 목록 부재**: override엔 NEGATIVE/STRONG_NEGATIVE/NEUTRAL만 있음(`perspective_service.py:277~317`). "목표의식 강화"류 미감지의 원인(§6).
- **핵심 가치**: 긍↔부 오분류만 방지, 중립→긍정은 허용. §6 긍정강화는 **neg 게이트로 부정 무영향** 보장 시에만.
- **레거시 보호**: 기존 7개 rule_id 분기·`sentence_sentiment_override` 시그니처/결과 **불변**. 신규는 신규 id로만.
- **dev 제약**: 원데이터·배치 불가, KoTE는 로드됨. 업로드 CSV(또는 적재된 `acquired_sentences`)만으로 동작.
- **서버 무단 실행 금지**(사용자 허락 필요).

### ⏸ 보류 (사용자 명시적 연기)
- **KoTE 파인튜닝**: "발전 가능성" 논의 시점에 별도로. 현재 계획은 **규칙 기반 후처리 강화만**(모델 재학습 아님).

### ❔ 미결정(§10)
① 데이터 지금 반입 vs §4 측정 먼저 구현 / ② 강화 범위 (a)보정규칙만(권고) vs (b)매핑수정/(c)argmax임계값 / ③ 한 문서 vs 측정 후 분리.

---

## 0. 환경 제약 (재확인)

- 다면평가 원데이터는 내부 전용. dev에는 **CSV만 반입**, 배치 실행 불가.
- 따라서 본 작업은 `0615_10`의 정제 CSV(코퍼스 행 + KoTE 재계산만으로 동작)를 **입력 데이터셋**으로 사용한다. 원데이터·배치에 의존하지 않는다.
- 운영 흐름: 내부 환경에서 "정제 CSV" 생성 → dev로 반입 → 본 계획의 측정/마이닝/검증.

---

## 1. 배경 / 목적

사용자 요구는 3가지다.

1. **(패턴 주입·검증)** 취득 코퍼스 수십~수백 건을 기반으로 패턴을 파악하고, 현재 보정 로직에 규칙으로 주입한 뒤, 해당 문장들이 의도대로 동작하는지 확인한다.
2. **(분류 정당성 검증)** KoTE 감정 분석 결과를 "기쁨→긍정"처럼 **1차원적으로 정적 매핑**하고 있고, 긍/부 판단은 **점수 합산**으로 한다. 이 두 설계의 정당성을 데이터로 확인한다.
3. **(긍정어 강화)** "목표의식 강화"처럼 인사평가에서 명백히 긍정인 표현을 KoTE가 제대로 감지하지 못한다. 알고리즘 강화 시 이 부분을 포함해 개선한다.

본 계획은 위 3가지를 **측정 → 마이닝 → 강화 → 회귀검증**의 데이터 주도(data-driven) 순서로 묶는다. 추측으로 규칙을 추가하지 않고, 코퍼스가 보이는 오류 패턴에 근거해서만 규칙을 도출한다.

---

## 2. 현재 코드 확인 (실측)

### 2-1. 1차원 정적 매핑 (검증 대상 ①)
- `src/configs/emotion_config.json`
  - `emotion_names`: KoTE 44개 감정 레이블.
  - `emotion_to_sentiment`: 44개 감정 → `0(긍정)/1(부정)/2(중립)` **정적 1:1 매핑**. 예: `"42"(기쁨)→0`, `"0"(불평/불만)→1`, `"24"(없음)→2`, `"15"(신기함/관심)→2`, `"39"(놀람)→2`.
  - 이 매핑은 일반 도메인 기준이며 **인사평가 도메인에 대한 검증 이력 없음**.

### 2-2. 점수 합산 argmax 판단 (검증 대상 ②)
- `src/modules/emotion_analysis.py::EmotionAnalysis.analyze`
  - L110: 44개 로짓을 softmax → 44개 확률.
  - L181~208: 각 확률을 `emotion_to_sentiment`로 3계열(positive/negative/neutral)에 **합산**.
  - L213~217: 세 합산값 중 **최댓값(argmax)** 으로 최종 감성 결정. (동률·근소차 가중치·임계값 **없음** — 단순 최대)
  - 반환 경로: `results['analysis']['base_result']['mapped']['sentiment_scores']` = `{positive, negative, neutral}`.

### 2-3. 문장별 보정 규칙 (패턴 주입 지점)
- `src/services/perspective_service.py::_sentence_sentiment_override_explain` (L327) → `(score, rule_id)`.
  - 분기: `neutral_dominant`, `neutral_keyword`, `euphemistic_negative`, `rule1_contrast_lastlow`, `rule2_contrast_lasthigh`, `rule3_last_low`, `rule4_default`.
  - `sentence_sentiment_override`(L372)는 시그니처 유지하며 explain에 위임(동작 보존, score만 반환).
- 보유 키워드/구문 목록 (L277~317):
  - `NEGATIVE_IMPLYING_WORDS`(단어), `STRONG_NEGATIVE_PHRASES`(구문), `NEUTRAL_KEYWORDS`(`보통/무난/평범`).
  - **긍정 구제(positive-rescue) 목록은 존재하지 않음** → 검증 대상 ③(긍정어 강화)의 핵심 공백.
- 반전 표지어: `CONTRASTIVE_MARKERS`(L79) → `has_contrastive`(L267).

### 2-4. 입력 데이터셋 (정제 CSV)
- `refine_acquired_row(row)` (L2121) → KoTE 재계산 + 보정 재현 + 비교 플래그.
  - 현 출력: `kote_pos/kote_neg/kote_neutral`, `raw_model_label`(3분류), `applied_rule`, `corrected_label`, `override_score`, `is_last/total_sentences`, `kote_vs_truth`, `pipeline_vs_truth`, `rule_helped`, `rule_hurt`.
  - **공백**: 지배 KoTE 감정(44개 중 1개)·top_3 라벨을 담지 않음 → §2-1 매핑 검증에 필요.
- `export_acquired_sentences_refined_csv(mismatch_only)` (L2216) → 24컬럼 CSV(BOM).

> ⚠️ 핵심 가치(메모리): **긍정↔부정 오분류만 방지, 중립→긍정 오분류는 허용.** 단, 요구 #3("목표의식 강화" 미감지)은 정답=긍정인데 모델=중립인 케이스로, 엄밀히는 "허용" 범주다. 본 계획은 이 긴장을 §6에서 명시적으로 다룬다(워드클라우드 집계에서 긍정 신호 소실 방지 목적의 **제한적·데이터 게이트** 강화로 한정, true-negative→positive 반전은 절대 금지).

---

## 3. 작업 데이터 수령 절차 (선행)

1. 내부 환경에서 코퍼스 취득(수십~수백 건) → "정제 CSV"(또는 기본 CSV) 생성 → dev 반입.
2. **반입 방식 — 화면 업로드(import) (1차 구현 완료, §7-5)**: dev의 취득 데이터 게시판에서 CSV를 직접 업로드 → `acquired_sentences` 테이블에 적재 → 화면에서 즉시 확인. 별도 스크립트/수동 DB 조작 불요.
   - 보조 보관: 원본 CSV는 본 작업 폴더 `data/` 하위에 둘 수 있음. 현재 `.gitignore`에 `data/` 미등록이므로, 반입 전에 등록하거나 `data/.gitkeep`로 폴더만 추적할 것.
3. 본 계획의 분석 스크립트·화면 측정은 적재된 `acquired_sentences`(또는 동일 CSV)만 읽고 동작(원데이터·배치 불요).

> 수령 전이라도 §7-5 업로드 경로·§4 측정 스크립트·§4-1 CSV 컬럼 보강은 선구현 가능. 규칙 도출(§5)·긍정어 목록(§6)은 **실데이터 수령 후** 확정한다(추측 금지 원칙).

---

## 4. Phase 1 — 분류 정당성 측정 프레임워크 (요구 #2)

목적: "1차원 정적 매핑"과 "점수 합산 argmax"가 인사평가 도메인에서 타당한지 **수치로** 보인다.

### 4-1. CSV 컬럼 보강 (additive, 측정 입력 확보)
- `refine_acquired_row`에 다음을 **추가 출력**(기존 컬럼·동작 불변):
  - `kote_top_emotion`(44개 중 최상위 라벨명), `kote_top_score`, `kote_top3`(라벨:점수 3쌍, JSON 문자열 `{"기쁨":0.85,"자신감":0.07,"만족":0.03}`).
  - 산출처: `analyze_emotion(text)` 결과의 `base_result.mapped.top_3`(이미 존재, `emotion_analysis.py:261`)를 그대로 매핑.
- `export_acquired_sentences_refined_csv` 헤더·행에 신규 3컬럼 append.

### 4-2. 측정 스크립트 `analyze_corpus.py` (신규, `scripts/` 하위)
정제 CSV를 입력으로 다음 지표를 산출(서버·DB 불요, pandas/csv만):

- **(A) 파이프라인 혼동행렬**: `pipeline_vs_truth` 기준 긍/부/중 3x3 + 정확도/정밀도/재현율.
- **(B) 원시 KoTE 혼동행렬**: `raw_model_label` vs `user_label` — 보정 전 성능 baseline.
- **(C) 매핑 정당성(요구 #2-①)**: `kote_top_emotion`별로 `user_label` 분포 집계 →
  - 각 KoTE 감정이 인사평가에서 실제로 어떤 정답과 결합하는지의 표.
  - `emotion_to_sentiment`의 정적 라벨과 **실측 다수 정답이 불일치**하는 감정 식별(예: "없음"이 중립이 아니라 긍정/부정에 치우치는지, "놀람/신기함"의 도메인 편향 등).
- **(D) 점수 판단 정당성(요구 #2-②)**: argmax 결정의 마진 분포 — `|pos-neg|`, `max - 2nd` 히스토그램. 마진이 극히 작은 구간(예: <0.05)에서 오답률이 급등하는지 → **임계값/동률 처리 부재**의 정량 근거.
- **(E) 규칙 효과**: `applied_rule`별 건수, `rule_helped`/`rule_hurt` 비율 → 역효과 규칙 식별.
- **(F) 미처리 오류 풀**: `kote_vs_truth=wrong & applied_rule=rule4_default` 행 추출 → §5 신규 규칙 후보.

### 4-3. 산출물
- `result/측정리포트_YYYYMMDD.md` — (A)~(F) 표/요약 + **판정**:
  - 1차원 매핑이 도메인에서 깨지는 감정 목록(근거: C).
  - 점수 argmax의 취약 마진 구간(근거: D).
  - 위 근거로 §5/§6의 강화 방향을 **데이터로 정당화**.

---

## 5. Phase 2 — 패턴 마이닝 → 규칙 주입·검증 (요구 #1)

목적: 코퍼스가 보이는 오분류 패턴을 규칙으로 도출하고 보정 로직에 주입, 의도대로 동작 확인.

### 5-1. 마이닝 (데이터 기반, 스크립트화)
- (F) 미처리 오류 풀과 `rule_hurt` 풀에서:
  - 어절/어미/구문(2~3그램) 빈도 → 오분류를 가르는 표지 후보 추출.
  - 후보를 기존 목록(`NEGATIVE_IMPLYING_WORDS`/`STRONG_NEGATIVE_PHRASES`/`NEUTRAL_KEYWORDS`)과 대조해 **신규/중복** 분류.
- 산출: 규칙 후보표(표지, 방향, 근거 건수, 예상 helped/예상 hurt).

### 5-2. 규칙 주입 (additive, 동작 보존 원칙)
- 신규 표지는 **기존 목록에 append** 또는 explain에 **신규 분기 추가**로 반영.
  - 신규 분기는 기존 분기보다 **앞·뒤 위치를 명시**하고, 각 분기에 rule_id 부여(마이닝 추적성 유지).
  - 기존 7개 rule_id의 분기 조건·점수는 **불변**(레거시 보호). 신규는 신규 id로만 추가.
- 오탐 억제: 구문(2어절+) 우선, 단어 단위는 마진·`strength` 게이트와 결합.

### 5-3. 회귀 검증 (의도대로 동작 확인)
- **회귀 락셋**: 현재 코퍼스 전체를 "주입 전 corrected_label"로 스냅샷 → 주입 후와 diff.
  - `rule_hurt` 신규 발생 0건이 목표(불가피 시 hurt ≤ 기존 전체 hurt의 10%이고 helped/hurt 비율 ≥ 5로 입증).
  - 동작 보존 단언: 기존 7 rule_id가 발동한 행의 score는 **완전 동일**.
- **지정 케이스 테스트**: 사용자가 "이렇게 나와야 한다"고 지정한 문장 세트를 골든 케이스로 고정(test/).

---

## 6. Phase 3 — 인사평가 긍정어 강화 (요구 #3)

목적: "목표의식 강화"류 도메인 긍정어가 KoTE에서 중립/저긍정으로 떨어지는 문제를 **제한적으로** 보정.

### 6-1. 데이터 정의 (추측 금지)
- §4의 (C)/(F)에서 **truth=positive & raw=neutral**(또는 저긍정) 행을 모아 빈출 긍정 표지를 추출.
- 후보 예시(검증 전 가설, 실데이터로 확정): `목표의식`, `책임감`, `주도적`, `적극적`, `성실`, `기여`, `개선 주도`, `목표 달성`, `역량 강화` 등.

### 6-2. 보정 설계 — `POSITIVE_IMPLYING_PHRASES`(신규, 제한적)
- 새 구문 목록 + explain 신규 분기 `positive_rescue`:
  - 발동 조건(보수적): 표지 포함 **AND** `not has_contrast`(반전 없음) **AND** `kote_neg`가 낮음(예: neg < 0.2) **AND** raw가 negative가 아님.
  - 효과: 중립/저긍정 → 긍정으로 상향. **true-negative를 긍정으로 뒤집는 경로는 원천 차단**(neg 게이트).
- 핵심 가치와의 정합: 본 강화는 "긍↔부 오분류 방지" 원칙을 **위반하지 않음**(부정 문장은 건드리지 않음). 중립→긍정 상향은 허용 범주이며, 워드클라우드에서 긍정 신호 보존이라는 명시적 효용이 있음.

### 6-3. 대안 검토 (리포트에 비교)
- (a) 보정 규칙(위) vs (b) `emotion_to_sentiment` 매핑 자체 수정(예: 특정 감정 재매핑) vs (c) 점수 argmax에 임계값/가중 도입.
- §4 측정 결과로 (a/b/c) 중 **최소 변경·최대 효과**를 선택. 기본 권고는 (a) 보정 규칙(레거시 영향 최소). (b)는 전 파이프라인 파급이 커 측정 근거가 충분할 때만.
- **의사결정 게이트**: Phase 1 측정 리포트에서 (b)/(c)의 필요성을 입증하는 데이터(예: 매핑 불일치 감정이 전체 오류의 30% 이상)가 나올 경우에만 (b)/(c)를 별도 계획서로 분리·검토한다. 그렇지 않으면 (a)로 한정.

---

## 7. 검증 화면 & 반복 루프 (acquired_data.html 확장)

목적: 제가 산출한 분석·규칙을 사용자가 **화면에서 직접 검증**하고, "무엇이 틀렸는지" 피드백을 남기면 제가 그 피드백을 받아 **재분석→규칙 보정**하는 human-in-the-loop 루프를 구축한다. 신규 페이지를 만들지 않고 **기존 `acquired_data.html`(취득 데이터 게시판)을 additive 확장**한다.

### 7-1. 화면 확장 (acquired_data.html, additive)
- 기존 테이블에 **정제 메타 컬럼 추가(토글 표시)**: `kote_top_emotion`, `raw_model_label`, `applied_rule`, `corrected_label`, `rule_helped`/`rule_hurt`, `override_score`. (기존 컬럼·CSV 버튼 유지)
- 상단에 **집계 패널 탭**: (A) 혼동행렬, (C) 감정별 매핑표, (D) 마진분포 — §4 측정값을 화면에서 즉시 확인.
- 행별 **피드백 버튼**: `[맞음]` `[틀림]` `[정답지정(긍/부/중)]` → 사용자 판정을 저장.
- **규칙 시뮬레이션 토글**: 후보 규칙 적용 시 `corrected_label` **전→후 diff**를 행마다 색상 표시(코드 커밋 없이 미리보기).

### 7-2. 백엔드 (additive, 신규 라우트만)
- `GET /api/perspective/acquired-sentences/refined-view` — `refine_acquired_row`를 **화면 렌더용 JSON**으로 페이징 반환(다운로드 아님). 기존 export 라우트는 유지.
- `GET /api/perspective/acquired-sentences/metrics` — §4-2 `analyze_corpus` 로직을 재사용해 혼동행렬·매핑표·마진분포 집계 JSON 반환.
- `POST /api/perspective/acquired-sentences/annotate` — 행별 사용자 판정 저장(`verdict`: correct/wrong, `corrected_truth`: positive/negative/neutral, `note`).
- `POST /api/perspective/acquired-sentences/simulate-rules` — 후보 규칙(긍정/부정 표지 목록·분기 파라미터)을 받아 **파라미터 주입형 override 복제본**으로 전/후 `corrected_label` diff 반환. **실제 `_sentence_sentiment_override_explain`은 미수정**(시뮬레이션 전용 변형 함수 사용) → 레거시 보존.

### 7-3. 주석 영속화 (스키마)
- 신규 사이드카 테이블 `sentence_annotations(sentence_id, verdict, corrected_truth, note, created_at)` — **acquired_sentences는 무변경**(컬럼 추가 X). 키는 `acquired_sentences.id`(취득 게시판 고유 id, eval_id 아님).
- 주석은 §5/§6 규칙 보정의 **정답 보강 신호**로 사용: 특히 `verdict=wrong`·`corrected_truth` 지정 행을 우선 분석.

### 7-5. 데이터 업로드(import) — 1차 구현 ✅ (선행 인프라)

검증 루프의 전제: dev에 코퍼스 데이터가 **들어와 있어야** 화면·측정이 동작한다. dev는 배치/원데이터가 없으므로 **CSV 업로드**로 적재한다.

- **서비스** `perspective_service.py`:
  - `_parse_acq_import_rows(csv_text)` (신규, 순수함수) — BOM 제거, 헤더 기반 매핑. `sentence_text` 필수, `user_label` 선택(없으면 neutral). `model_label`/`context`/`source_*`/`sentence_index`/`confidence`(또는 `confidence_at_capture`) 선택. 라벨 정규화(`긍정/부정/중립`↔`positive/...`). 반환 `(rows, errors)`.
  - `import_acquired_sentences_csv(csv_text, overwrite=False)` (신규) — 위 파서 결과를 단일 커넥션 배치로 `acquired_sentences`에 적재. 중복(UNIQUE: sentence_text+source_evaluation_id+sentence_index)은 `overwrite=False`면 `INSERT OR IGNORE`로 건너뛰고, `True`면 `INSERT OR REPLACE`. 반환 `{inserted, skipped, errors}`. **KoTE 불요**(기본 컬럼만 적재; 정제 메타는 화면/내보내기에서 재계산).
- **라우트** `perspective_routes.py`: `POST /api/perspective/acquired-sentences/import` — 관리자 전용, `multipart` 파일 업로드(utf-8-sig→cp949 폴백), `overwrite` 플래그. 기본/정제 CSV 모두 수용.
- **화면** `acquired_data.html`: "데이터 가져오기" 버튼 + 숨김 `file input`. 업로드 후 결과(추가/건너뜀/오류) 알림 + 목록 새로고침.
- **테스트** `test/test_import.py`: 파서 단위(정제 CSV/기본 CSV/한글 라벨/필수컬럼 누락) — DB·KoTE 불요로 검증.
- **레거시 보호**: 전부 additive. 기존 저장 흐름(`save_acquired_sentence`)·스키마·기존 라우트/버튼 무변경.

### 7-4. 반복 루프 (human-in-the-loop)
1. 제가 후보 규칙 도출 → `simulate-rules`로 화면에 전/후 표시.
2. 사용자가 행별 검증(`annotate`) — 틀린 보정·기대 정답 지정.
3. 제가 주석(특히 `wrong`/`corrected_truth`)을 읽어 **무엇이 왜 틀렸는지 재분석** → 규칙 보정.
4. 만족 시에만 규칙을 코드(explain 신규 분기/목록)로 **확정 commit** → §5-3 회귀 락셋 재검증.
- 루프는 코드 변경 없이 (1)~(3)을 반복하다가, 합의된 규칙만 (4)에서 1회 반영 → 잦은 코드 변경·회귀 위험을 줄인다.

---

## 8. 영향도 / 회귀

| 변경 | 영향 범위 | 회귀 위험 | 검증 |
|------|-----------|-----------|------|
| §4-1 CSV 3컬럼 추가 | refine/export | 없음(additive) | 신규 컬럼 값·기존 컬럼 불변 |
| §4-2 측정 스크립트 | 신규 파일 | 없음 | 리포트 산출 |
| §5-2 신규 rule_id 분기 | override 경로 | **중간** | 기존 7 rule 동작 보존 단언 + 회귀 락셋 diff |
| §5-2 키워드 목록 append | override 경로 | 중간(오탐) | 회귀 락셋 hurt=0 |
| §6-2 positive_rescue | override 경로 | 중간 | neg 게이트로 부정 무영향 단언 |
| §6-3(b) 매핑 수정(선택) | 전 KoTE 소비처 | **높음** | 채택 시 별도 영향도 분석 필수 |
| §7-1 화면 컬럼/패널 | acquired_data.html | 없음(토글·additive) | 기존 게시판 동작 불변 |
| §7-2 신규 라우트 4종 | 신규 경로만 | 없음(additive) | 각 응답 스키마 확인 |
| §7-3 annotations 테이블 | 신규 테이블 | 없음 | acquired_sentences 무변경 |
| §7-2 simulate-rules | 시뮬 전용 변형 함수 | 없음 | 실제 override 미호출 단언 |

- DB 스키마: 기존 테이블 **무변경**(주석은 신규 사이드카 테이블). 취득 캡처 흐름 **무변경**.
- 롤백: 신규 분기·목록·컬럼·스크립트·라우트·테이블·화면 요소 제거로 원복. 기존 함수는 위임 구조 유지.

---

## 9. 테스트 계획

- **동작 보존**: 기존 `test/test_refine.py`의 override 동일성 단언 유지 + 신규 rule_id 추가 후에도 기존 7 rule 발동 케이스 score 불변.
- **측정 정확성**: 합성 미니 코퍼스(라벨 알려진 10~20행)로 혼동행렬·매핑 집계 수치 검산.
- **규칙 효과**: 회귀 락셋 diff에서 `rule_hurt` 신규 0건(또는 helped/hurt 비율 보고).
- **긍정 강화 안전성**: 부정 골든 케이스(반전·완곡부정 포함)가 positive_rescue로 뒤집히지 않음 단언.
- **지정 골든 케이스**: 사용자 제공 "기대 출력" 문장 세트 통과.

---

## 10. 결정 필요 사항 (사용자 확인)

1. **데이터 수령 시점**: 지금 정제 CSV(수십~수백건)를 `data/`에 반입 후 §5/§6 규칙을 확정할지, 아니면 §4 측정 프레임워크/§4-1 컬럼 보강을 **먼저 구현**해두고 데이터가 오면 돌릴지.
   - 권고: **§4를 먼저 구현**하라. 데이터가 도착하자마자 분석을 돌릴 수 있어 전체 일정이 단축된다.
2. **강화 범위**: 요구 #3을 (a) 보정 규칙만(권고)으로 한정할지, (b) `emotion_to_sentiment` 매핑 수정 또는 (c) 점수 argmax 임계값까지 열어둘지(파급 큼).
   - 권고: **(a) 보정 규칙만 한정**하라. (b)/(c)는 Phase 1 리포트 이후 별도 판단하는 것이 레거시 영향을 최소화한다.
3. **본 계획 분리 여부**: 측정(Phase 1)과 강화(Phase 2·3)를 한 계획으로 진행할지, 측정 리포트 후 강화를 별도 계획서로 분리할지.
   - 권고: **한 문서로 진행하되, Phase 1 완료 시점에 Go/No-Go 게이트**를 두어라. 측정 결과가 예상보다 파급이 크면 그때 Phase 2/3를 분리해도 늦지 않다.
4. **검증 화면 방식**: ✅ **결정됨 — 기존 `acquired_data.html` 확장**(2026-06-17). §7 참조. 신규 페이지 미생성, additive 확장.

---

## 11. 진행 원칙

- 본 문서는 **Plan Mode 산출물**(상태 PND). 사용자가 "수행"을 명시하기 전까지 코드 변경 없음.
- 모든 신규 규칙·키워드는 **코퍼스 실데이터 근거**로만 확정(추측 금지). 데이터 미수령 구간은 가설로 표기.
- 레거시 보호: 기존 rule_id 분기·`sentence_sentiment_override` 시그니처/결과 불변.

---

## 12. 리더십 후속 — negation 인식 리더십 극성 통합 (요구 1+3)

> 상태: 설계 합의 대기(🟡 승인 필요). 작성일 2026-06-17. 사용자 요청: "1항(감정분류 정확도)+3항(리더십 분석모듈)을 같이 가자. 우리는 문맥 파악 AI가 없으니까."

### 12-1. 문제 정의 (왜 통합이 필요한가)
- 우리에겐 **문맥 파악 AI가 없다.** 리더십 모듈(`leadership_analysis.py`)은 키워드 매칭(소통/문제해결/리더십…) + 감정점수만으로 6역량을 채점하고, **부정 감정에도 ×0.3 가점**을 준다(L294). 문맥 게이트가 전무.
- 결과: `수직적 의사소통…문제해결을 강요` 같은 **부정 리더십**도 `문제해결/소통` 키워드 때문에 **리더십 강점으로 오채점**된다. → 그룹리포트 `_generate_leadership_cell`(perspective_service.py:1220) 점수 왜곡.

### 12-2. ★ 데이터 근거 (코퍼스 475문장, refine_diag 기반 실측)
- 리더십 **긍정표지** 문장 **61건**, **부정표지** 문장 **11건**.
- ⚠️ 핵심 발견: 부정표지 11건의 **대부분이 "부정어의 부정 = 칭찬"**이다.
  | 문장 | 표면표지 | 실제 |
  |------|---------|------|
  | `강압적이지 않음` / `강압적이지않다` | 강압 | **긍정** |
  | `고압적인 태도를 보이지 않음` | 고압 | **긍정** |
  | `권위의식이 없음` / `부드러운 권위와 소통` | 권위 | **긍정** |
  | `잔소리를 안한다` | 잔소리 | **긍정** |
  | `세세한 지시 감독하는 성향이 강함` | 지시감독 | **부정** |
  | `수직적…강요하며…수동적 참여 유도` | 강요/수직 | **부정** |
  | `출세의지가 강하고 발언시간 길다` | 출세 | **부정** |
- → **진짜 부정은 ~4건**, 나머지는 negation 칭찬. **단순 키워드 게이트(강요/수직 있으면 부정)는 칭찬을 부정으로 망가뜨려 역효과.** ∴ negation 인식이 필수. (이는 §0-A 후속 #3 negation 처리와 동일 문제.)

### 12-3. 설계 (additive, 레거시 보호)
- **신규 파일** `src/modules/hr_context_lexicon.py` (additive, 기존 영향 0):
  - 리더십 긍정표지(방향제시/솔선수범/동기부여/코칭/위임/경청/비전/모범…) + 부정표지(강요/수직적/독단/고압/일방적/권위의식/출세/세세한 지시/간섭/잔소리/상관 마인드/수동적…).
  - `leadership_polarity(text) -> 'positive'|'negative'|'neutral'`: **negation 인식** — 부정표지 뒤 N글자 내 부정종결(않/없/안/아니) 발견 시 극성 반전(부정→긍정).
- **수정 ① `src/modules/leadership_analysis.py`** (🟡 live, 승인 필요):
  - `_calculate_competency_score`/`analyze_leadership`에 `leadership_polarity` 게이트 추가 → 부정 리더십은 강점 가점 차단·개선영역으로. **표지 없으면 기존 동작 그대로(회귀 안전).**
  - 영향: `leadership_analysis_results` → `_generate_leadership_cell`(perspective_service.py:1220) 그룹 점수. 부정 리더십 평가만 변동.
- **수정 ② `src/services/perspective_service.py`** (🟡 live, 승인 필요):
  - 감정 보정이 동일 `leadership_polarity` 공유. negation 칭찬(`강압적이지 않음`)을 긍정 구제 가능하게. **기존 7 rule_id·`sentence_sentiment_override` 시그니처/결과 불변, 신규 분기만.**

### 12-4. 진행 순서 (권고 = B: live 파일 하나씩)
- **B(권고)**: 신규 모듈 → leadership_analysis 게이트(3) → 검증 → 그 다음 감정보정 공유(1).
- A(전체): 신규 모듈 + 3 + 1 동시. (레거시 위험 ↑)
- → 본 계획은 **B로 착수**하고, 1번 확장은 3번 검증 통과 후 별도 승인.

### 12-5. 검증 계획
- 골든 테스트(KoTE 불요): `leadership_polarity`가 위 표 11건 + negation 칭찬을 정확히 분류.
- 코퍼스 회귀: 긍정 61건 점수 불변/상승, 진짜 부정 ~4건만 개선영역으로. 일반 케이스(표지 없음) 점수 불변.
- 핵심가치: 긍↔부 오분류 0 유지.

### 12-6. ⛔ 미해결 — 착수 전 사용자 승인 필요 항목
- (a) 수정 범위 **A vs B** 확정(권고 B). → ✅ **B 승인**(2026-06-17).
- (b) `leadership_analysis.py`·`perspective_service.py` **🟡 live 파일 수정 승인**. → ✅ **승인**(B에서는 leadership_analysis.py만 수정, perspective_service.py는 검증 후).

### 12-7. ✅ B안 구현 결과 (2026-06-17, 사용자 "권고안대로 처리" 승인)
- **신규 `src/modules/hr_context_lexicon.py`** (additive, 기존 영향 0):
  - `POSITIVE_MARKERS`(방향제시/솔선수범/동기부여/코칭/위임/경청/수평적/소통/배려…), `NEGATIVE_MARKERS`(강요/강압/고압/수직적/일방적/독단/권위의식/세세한 지시/잔소리/수동적 참여/출세…), `NEGATION_TOKENS`(않/없/아니/안…), `NEGATION_WINDOW=14`.
  - `leadership_polarity(text)`: ①부정표지+직후창 negation=칭찬, ②부정표지+negation없음=진짜부정, ③진짜부정 1개라도 있으면 negative(보수적), ④없고 (negation칭찬 or 긍정표지)면 positive, ⑤무표지=neutral.
- **수정 `src/modules/leadership_analysis.py`** (🟡):
  - `import ... leadership_polarity`; `analyze_leadership`에서 1회 판정 후 `_calculate_competency_score(text, emotion_result, competency_info, polarity)`로 전달.
  - 게이트: `if polarity == 'negative': score = 0.0`(강점 가점 차단→개선영역). 파라미터 default `'neutral'` → 기존/직접 호출자 회귀 안전.
- **검증**:
  - 골든 `test/test_leadership_polarity.py`: §12-2 표 11건 + negation칭찬/진짜부정/긍정표지/무표지 — 4 그룹 전부 통과. **긍↔부 오분류 0**.
  - 게이트 단위검증(KoTE 미인스턴스화): 부정 리더십(`수직적 의사소통…강요`)=0.0, 긍정(`경청…방향제시`)=0.64, **polarity 미지정(레거시)=0.74 불변**. `py_compile` 통과.
- **회귀 안전 근거**: 표지 없는 일반 평가문은 `neutral` → 점수 산식 무변동. 기존 ×0.3 부정감정 가점(L294)도 neutral/positive에선 그대로(전역 변경 아님).
- **다음(요구 1, 별도 승인 대기)**: `perspective_service.py` 감정보정이 `leadership_polarity` 공유 → `강압적이지 않음`류 negation 칭찬 긍정 구제. **미착수**(B 순서: 3 운영검증 후).

### 12-8. ✅ 추천 다음 단계 — 1→2→3 전부 완료 (2026-06-17, 결과는 §12-9)

> 사용자 승인(2026-06-17): "네가 추천하는 방향으로 진행." compact 후 아래 1→2→3 순서로 착수.

1. **운영 검증 먼저 (코퍼스 회귀, 서버 불요·KoTE 로드)**
   - `leadership_analysis` 게이트를 코퍼스 리더십 문장(긍정표지 61 / 부정표지 11)에 적용해 수치 확인:
     - 긍정 61건: 점수 **불변 또는 상승**(게이트 미발동).
     - negation 칭찬(`강압적이지 않음`·`권위의식이 없음`·`잔소리를 안한다`류, 부정표지 11 중 ~7): polarity=positive → **0점화 안 됨**(칭찬 보존).
     - 진짜 부정 ~4건(`세세한 지시 감독`·`수직적…강요`·`출세의지`): polarity=negative → **0점(개선영역)**.
   - 산출: `result/리더십게이트_회귀_260617.md`(전/후 점수 diff 표). KoTE 일회 로드, DB·배치 불요.
   - 게이트는 입력 단문(문장) 기준. 그룹 집계 영향은 `_generate_leadership_cell`(perspective_service.py:1220) 평균에 반영됨을 표로 명시(코드 수정 아님, 영향 설명).

2. **요구 1 — `perspective_service.py` 감정보정 negation 칭찬 구제 (🟡, 신규 분기만)**
   - `hr_context_lexicon`(또는 `leadership_polarity`)를 공유해 `강압적이지 않음`/`고압적이지 않음`/`권위의식이 없음`/`잔소리를 안한다`류를 **긍정 구제**.
   - **신규 분기 `negation_praise`로만 추가**(기존 7 rule_id 분기 조건·점수, `sentence_sentiment_override` 시그니처/결과 **불변**). 위치는 `positive_rescue` 전후 명시.
   - 게이트: 진짜 부정표지(negation 없음)는 구제 차단 → **긍↔부 오분류 0 유지**.
   - 이로써 §0-A 다음작업 **#3(부정 부정문 negation 처리)** 과 통합 해결.

3. **회귀 재검증**: `test/test_positive_rescue.py` 동작보존 + 신규 `negation_praise` 골든 케이스 추가. 회귀 락셋 diff에서 진짜부정 3/3 보존·hurt 0 확인.

⛔ 제약 재확인: 서버 무단 실행 금지(검증은 스크립트로). 신규는 신규 rule_id로만. 추측 금지(표지는 코퍼스 §12-2 근거).

### 12-9. ✅ 실행 결과 (2026-06-17, §12-8 1→2→3 완료)

**Step 1 — 리더십 게이트 운영 검증** (`result/리더십게이트_회귀_260617.md`, KoTE 1회 로드·서버 미사용)
- 코퍼스 475문장 중 리더십 표지 보유 **114문장** 분류: 긍정표지 104 / negation칭찬 6 / 진짜부정 4.
- A) 긍정표지 104: **전부 Δ=0** (게이트 미발동, 회귀 안전).
- B) negation 칭찬 6 (`강압적이지않다`/`고압적이지 않음`/`권위의식이 없음`/`잔소리를 안한다` 등): polarity=positive → **0점화 안 됨**.
- C) 진짜 부정 4 (`수직적…강요`/`세세한 지시 감독`/`출세의지`/`수직적 업무지시`): polarity=negative → **0점화**(개선영역).
- 긍↔부 오분류 위반 **0건**. (혼합극성 id312 `…격려, 수직적 업무지시`는 보수적으로 개선영역 처리 — 정답=neutral, 긍↔부 위반 아님; §0-A 혼합극성 deferred.)

**Step 2 — `perspective_service.py` negation_praise 분기 추가** (🟡, 사용자 승인)
- `hr_context_lexicon.is_negation_praise`(진짜 부정 0 + negation 칭찬 존재일 때만 True) 신설.
- `_sentence_sentiment_override_explain`에 **신규 분기 `negation_praise`만** 추가(위치: `positive_rescue` 직후 → `neutral_dominant`/`euphemistic_negative` 앞, 부정 반전 차단). 기존 7 rule_id 조건·점수·`sentence_sentiment_override` 시그니처 **불변**. 두 함수 docstring에 분기 명시.

**Step 3 — 회귀 재검증** (`result/감정보정_negation_회귀_260617.md`)
- 골든: `test/test_positive_rescue.py`에 `test_negation_praise_rescued_to_positive` 추가, 진짜부정 미진입(positive_rescue/negation_praise 모두) 검증 강화. 기존 동작보존 케이스 불변. 전체 통과.
- 코퍼스 락셋(신규 분기 on/off monkeypatch 격리): 475문장 중 **정확히 6건만 변경**, 전부 `negation_praise`로 전이(중립/부정→긍정), 진짜부정 전이 **0**, 나머지 469 불변.
- ★ 핵심 교정 2건: `권위의식이 없음`(**-0.856→+0.956**), `잔소리를 안한다`(**-0.277→+0.807**) — 기존 **부정 오분류**를 긍정으로 교정.
- ✅ **라벨 교정 완료(사용자 판단 반영, 2026-06-17)**: 위 2건의 CSV `corrected_label`이 `negative`였으나, 사용자 판단 "**중립으로 봐도 되지만 절대 부정은 아니다**"에 따라 **negative→neutral**로 교정. (positive 아님 — 사용자가 중립으로 보심.) 이로써 변경 6건 전부 정답=neutral → 출력 positive, 즉 **중립→긍정(코어밸류 허용)** 으로 정렬되어 긍↔부 오분류 0. 알고리즘 출력은 두 건 모두 부정에서 양수로 이미 빠져나와 "부정 아님" 조건 충족 — 코드 수정 불요.

**변경 파일**: `src/modules/hr_context_lexicon.py`(+is_negation_praise), `src/services/perspective_service.py`(import+negation_praise 분기+docstring), `test/test_positive_rescue.py`(골든 추가), 신규 검증 스크립트 2종(`test/run_leadership_gate_regression.py`, `test/run_negation_praise_regression.py`).

▶ 남은 확인 사항: §0-A deferred 중 **무응답 중립화 ✅ 완료(§13)**. 남은 항목 = 혼합극성(보류)·step1 정답 최종합의(별도 착수). (2건 정답 라벨 건은 negative→neutral로 종결.)

### 13. ✅ 무응답 중립화 (§0-A #2, 2026-06-17)

> 사용자 지시 "다음건 진행" + 다음건=무응답 중립화 선택. 🟡 live `perspective_service.py` 신규 분기만 추가(기존 rule_id·시그니처 불변).

**문제 (코퍼스 실측)**: 평가를 하지 않은(또는 못 한) **비평가 문장**이 KoTE→`rule4_default`에서 부정으로 강등됨(중립→부정 오분류). 유형 3종:
- 평가불가/모름: `잘 모르겠습니다`, `뵌 적이 없어서 잘 모르겠습니다`, `같이 근무를 안해서 모름`, `대면한 적이 없어서 평가 할 수가 없습니다`, `특별한 장점을 알지 못합니다` 등.
- 내용없음/해당없음: `내용없음 내용없음 내용없음`, `특이사항 및 해당사항 없음`, `의견이 없습니다`, `특별히 서술할 내용 없음`.
- 낙서: `ㅈㅈㅈㅈ…`, `성실성실성실…`, (이미 중립인 `ㅂㅂㅂ`/`11111`/`-----` 포함).

**탐지기 검증 (추측 금지)**: 마커 기반 탐지기를 코퍼스 475 전체에 적용 → **37건 매칭, 오탐 0건**(실제 평가 내용 섞임 없음). 그중 11건은 이미 중립(`neutral_dominant`, 낙서)이라 변경 불필요, **27건이 현재 부정**(`rule4_default`) → 교정 대상.

**구현 (additive, 🟡 신규 분기만)**:
- `perspective_service.py`에 `NO_RESPONSE_PHRASES`(평가불가/내용없음 구문 목록) + `is_gibberish()`(자모반복·동일토큰3회+·숫자/기호도배) + `is_no_response()` 신설.
- `_sentence_sentiment_override_explain`에 신규 분기 **`no_response_neutral`**(→ `0.0`) 추가. 위치: `neutral_dominant` **직후** · `neutral_keyword`/`euphemistic_negative`/rule3 **앞**. 이로써 이미 중립인 낙서는 `neutral_dominant`가 선행 처리(불변), 부정으로 떨어질 비평가 문장만 가로챔.
- 게이트: `is_no_response`는 진짜 부정 신호(`NEGATIVE_IMPLYING_WORDS`/`STRONG_NEGATIVE_PHRASES`)가 섞이면 False → **부→중 강등 차단**(비평가는 긍정도 부정도 아니므로 중립화는 긍↔부 오분류를 만들지 않음). 긍정은 선행 `positive_rescue`가 처리.
- 기존 7 rule_id 분기 조건·점수·`sentence_sentiment_override` 시그니처 **불변**. 두 함수 docstring에 분기 명시.

**검증**:
- 골든 `test/test_no_response.py`: 무응답/낙서→`no_response_neutral`(0.0), 무응답+진짜부정 혼합→차단(부정보존), 진짜긍정→`positive_rescue` 유지, `is_gibberish` 술어. 전부 통과.
- 코퍼스 락셋(`test/run_no_response_regression.py`, 신규 술어 on/off 격리): 475 중 **정확히 27건 전이**, 전부 `rule4_default`(부정) → `no_response_neutral`(중립 0.0), 긍정 손실 **0**, 긍↔부 오분류 **0**, 낙서 중립 11건 불변. 산출 `result/감정보정_무응답_회귀_260617.md`.
- `test/test_positive_rescue.py`(legacy==explain 동작보존 포함)·negation 락셋 6건 — **무영향 재확인**.

**변경 파일**: `src/services/perspective_service.py`(NO_RESPONSE_PHRASES·is_gibberish·is_no_response·no_response_neutral 분기+docstring), 신규 `test/test_no_response.py`·`test/run_no_response_regression.py`.

### 14. (없음 — §15로 이어짐)

### 15. ✅ 신규 데이터 검증 + 메타데이터 생성 적용 (2026-06-17)

> 사용자 요청: "신규 데이터가 신규 규칙/강화 알고리즘으로 제대로 분류되는지 확인 → 그 후 메타데이터 생성에 모듈 적용." 🟡 `metadata_analysis.py` 수정은 적용범위(통합감정+단어버킷 모두) 승인 후 진행.

**Step A — 신규 데이터 분류 검증** (`result/신규데이터_분류검증_260617.md`, KoTE 1회 로드)
- `data/new_260617.csv` **722행** 전수를 `refine_acquired_row`(프로덕션과 동일 KoTE→override)로 재분류.
- **긍↔부(negative↔positive) 전이 0건** — 핵심가치 충족. 부정 351건 전부 부정 유지.
- 신규 분기 발동 151건: positive_rescue 14(중립→긍정, 명백한 긍정 복원)·no_response_neutral 137(평가불가/낙서 중립)·negation_praise 0(표본 없음).
- 한계(긍↔부 아님·회귀 아님, 후속 튜닝 후보): ①id1190 `대화를 나눠 보지 못하였습니다`가 무응답 미포착으로 rule4 부정. ②무응답 게이트가 `소름끼치게 별로…`(id738)·`…갖다 버렸으면`(id801)·`…힘들게만 만들었기에`(id579) 등 부정 혼합문을 과중립화(부→중 recall 손실).

**Step B — 메타데이터 생성에 override 적용** (🟡 `src/modules/metadata_analysis.py`, 사용자 승인)
- **문제**: `create_employee_metadata`는 raw KoTE만 저장하고 `calculate_consolidated_analysis`가 raw doc-level KoTE로 `overall_sentiment`·감정별 단어버킷을 산출 → positive_rescue·no_response_neutral 등 신규 보정이 메타데이터에 전혀 반영 안 됨(perspective 화면과 불일치).
- **조치(additive·최소)**: `calculate_consolidated_analysis`가 evaluation별로 `_get_sentence_level_scores(doc, sentence_cache=...)`(perspective와 동일 함수, 저장된 `sentence_emotion_cache` 재사용 → **KoTE 재실행 0**, 19k 배치 O(n) 안전)로 문장단위 override 점수를 받아 **pos/neg 질량 비교**(perspective `_aggregate_emotion`과 동일 의미)로 라벨 결정. 통합감정·단어버킷 모두 보정 라벨 기준으로 산출. 라벨값(positive/negative/neutral)·스키마 불변(소비처 `metadata_service`는 표시용만).
- **검증**: 골든 `test/test_metadata_override.py` 4종(positive_rescue→positive, no_response→neutral, 진짜부정→negative, 혼합 질량결정) 전부 통과. `py_compile` OK.
- **변경 파일**: `src/modules/metadata_analysis.py`(통합감정 로직 override 전환), 신규 `test/test_metadata_override.py`·`test/run_new260617_verify.py`.
