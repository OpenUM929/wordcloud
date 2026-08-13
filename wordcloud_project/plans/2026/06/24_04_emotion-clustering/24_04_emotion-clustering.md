# 계획서 — KoTE 파인튜닝용 신규 HR 감정그룹 군집 발굴 (감정 스트림 D1)

> 상태: Doing | 작성일: 2026-06-24
> 작업 유형: C (설계/데이터셋)
> 상위 로드맵: `plans/_datasets/kote_finetune/ROADMAP.md` §5(P5/P6)·§5-3(수집→군집→대표 gold) / 운영: `RUNBOOK.md`
> 선행 자산: `0617_05_kote-finetune-data`(데이터셋 설계) · `0623_01_judgment-extract-ui`(대표 판정 패킷) · `result/sentiment_misclass_260624.md`(오늘 오분류 발굴)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-24 | 전체 | 최초 작성. 파인튜닝 신규 감정그룹을 군집으로 발굴하는 방법론·로드맵 설계 |
| 2026-06-24 | D1·D3 실행 | `cluster_emotion.py` Track A 군집 수행(미피복 484,119=전체 56%, k24). 24군집→3대 화행 수렴. D3 후보 ≤3 승격분석 산출(`result/emotion_new_groups_260624.md`). 상태 Doing. Track B(D2)는 인코더 미설치로 보류 |
| 2026-06-24 | D4 실행(G1+G2) | 사용자 G1+G2 선택. `extract_group_gold.py`: G1 128,265·G2 48,218 태깅(**G2 현규칙 긍8,496/부26,906/중12,816 3분열=누수 정량확증**). `judge_group_packet.py` AI 1차판정(독립 trap·혼합 신호). 직접 검증 통과 |
| 2026-06-24 | D4·D5 확대(최고성과) | 사용자 위임 → 표본 확대: gold 1,000/그룹(2,000)·baseline 1,500. needs_human에 **내 판정 `ai_reference`(polarity·confidence·reason) 동봉**(사람 대조용). D5 `propagate_group_weak.py`: **전체 176,483 weak 전파**(neutral 166,334/positive 9,627칭찬형/negative 326/trap 196). 통합 리포트 `result/finetune_progress_260624.md`. 잔여=택소노미 문서반영·needs_human 사람확인·D6 |
| 2026-06-24 | 수렴분석+미탐색 심화 | "작업 특징 비슷" 관찰 → **순환 위험 메타분석**(`result/work_convergence_analysis_260624.md`): 신규그룹 G1·G2=기존 규칙과 동일→파인튜닝이 규칙 증류 위험, 미피복 66.6%(322K) 미탐색. `cluster_emotion.py --exclude-known` 추가 → 미탐색 322,266 재군집. **결론: 큰 숨은 템플릿 없음(≤3 상한 옳음)**, 잔여는 역량서술↔결핍서술(KoTE 부분피복). **신규 후보 G4 자기개발/학습지향(C7·KoTE 없음·T14 대응)** 발굴. 해석 `result/emotion_residual_findings_260624.md` |
| 2026-06-24 | G4 편입(1항) | `g4_extract.py` 선별기 정의·**표본 2회 직접검증·정밀화**(자발적 참여 노이즈/결핍/필요 누수 제거, 27K→14,020 전부 positive). `g4_finalize.py`: **G4 weak 14,020 전파** + gold후보 200(장점)·needs_human 100(단점경계 ai_reference). 신규 3종 확정(G1·G2·G4=≤3). 다음=2항 경계 gold |
| 2026-06-24 | 사람검토 피드백 반영 | 사용자가 field_conflict(800)·needs_human 완료. ① **G4 ai_reference 단점필드 일괄 positive 오류** 확인(일치 64%)→라벨링 3원칙 도출([[feedback_incomplete_fragment_neutral]]: 무종결→중립·요청→부정). ② **혼합극성 절분리** — `rebuild_baseline.split_ext`로 '다보니·하나' 보강(production split_clauses 불변). ③ **baseline 재구성**: 870K→고유 367,492(중복 58% 확인)→축소 + 3원칙 ai_reference(`rebuild_baseline.py`). "밝은 분위기 조성→neg"는 현규칙 긍→부 오류(field_conflict로 사용자 gold 교정) |
| 2026-06-24 | 사람정렬 라벨러+버그수정 | 불일치 전수분석(`analyze_disagreements.py`·`mine_disagree_patterns.py`)→사람정렬 라벨러 `human_label.py`. 사용자 지적 **버그 연속수정**: '향상/제고' 명사 오탐 / 부정표지를 무종결이 가로챔 / '기여'(⊂성과기여도)·'무능'(⊂업무능력) 부분문자열 함정 / 조건부 제언("~다면 기대됨") / 장점부재→부정 / 아쉽·미비·오해·힘들 누락 / '필요한' 관형사. **정직한 결론: 라벨러 천장 ~63%(나머지는 본질적 주관)→힌트로만, gold가 정답** |
| 2026-06-24 | 🔴사고+복구 | g4_finalize 재실행이 **g4 needs_human 100건 또 덮음**(2번째 사고). 고정시드+disagreements 기록으로 **100건 전량 복구**(64/17/19 정확일치). **4 gold 전부 `_gold_backup/`백업** + g4_finalize에 사람판정 보호 가드 |
| 2026-06-24 | **D6 파인튜닝 완료** | 환경에 torch+CUDA 확인, 사용자 승인(P6). `finetune_sentiment.py`: KoTE 베이스→3분류, 학습 gold 1,579(비순환), 테스트 baseline 398 held-out. **전(규칙) 56.0%·긍↔부오류10 → 후(파인튜닝) 89.7%·긍↔부오류0**(63초). 리포트 `result/finetune_report_260624.md`·모델 `model_out/`. ① G4 재전파(라벨러 극성)도 완료 |

## 배경 및 목적

- 파인튜닝 목표(ROADMAP): KoTE를 인사평가 도메인에 맞춘다. 택소노미 기준선 = **KoTE 44 + HR신규 ≤3 (멀티라벨)**. 신규 그룹은 **코퍼스 군집 근거가 있을 때만** 추가(추측 금지, ROADMAP §3-2·§9 원칙).
- 사용자 요청: "KoTE에 추가 그룹 감정 정보를 어떻게 만들지 고민하고, 군집 알고리즘 같은 전문적 방법으로 방안을 검토해 다음 단계 계획을 잡아라."
- **왜 신규 그룹이 필요한가 (데이터 근거, 실측)**: KoTE 44는 전부 *정서*(분노·신뢰·고마움…)이고 인사평가가 많이 쓰는 *화행(speech-act)* 범주가 없다. 그 결과 다면평가 문장의 상당수가 KoTE에서 무감정/저신뢰로 빠지며, 이게 오늘 발견한 긍↔부 오분류의 토양이다.
  - 870,367 문장 중 KoTE top-1 = **"없음"(무감정) 243,613건(28.0%)**, 저신뢰(max(pos,neg)<0.4) **132,938건(15.3%)**.
  - 오늘 수작업 발굴(`sentiment_misclass_260624.md`)한 누수 패밀리 — 개선요청("X 필요/보완")·약점부재 선언("단점 없음")·평가회피("잘 모름")·역량 사실서술("명확한 의사전달") — 은 전부 KoTE 44에 대응 감정이 없는 화행이다.
- 목적: 이 "KoTE 미피복 영역"을 **무지도 군집**으로 체계 발굴해, 파인튜닝에 추가할 **신규 HR 감정/화행 그룹 ≤3개 후보**를 근거와 함께 도출하고, 그 다음 단계(대표 gold→택소노미 반영→학습)까지 계획을 확정한다.

## 1. 현황 실측 (코드/데이터 확인 완료)

- **KoTE 44 정본**: `src/config/settings.py` `EMOTION_NAMES`(44종, 실측 확인). 모두 정서 카테고리 + "없음" 1종.
- **보유 감정 신호(레코드당)**: `plans/_datasets/kote_finetune/emotion/weak_export_260624.jsonl`(889,465, 문장 870,367).
  - `text`, `kote=[pos,neg,neu]`, `emotions_topk`(= KoTE **top-3** 감정명+점수, **full 44 logit 아님**), `applied_rule`, `override_score`, `is_clause`, `src_hash`. 필드(장점/단점)는 `id` 배치태그(`_1-`=장점/`_0-`=단점)로 식별 가능.
  - ⚠️ **제약**: full 44-차원 분포가 아니라 top-3만 보존 → 군집 입력은 희소(sparse). full logit/임베딩은 KoTE/인코더 재실행 필요(아래 §2 제약과 직결).
- **대표 판정 인프라(재사용 가능, 실측)**: `src/services/judgment_packet_service.py` `build_judgment_packet`/`apply_judgment_packet`(추출→판정→in-place 삽입, 가명 안전) + 방금 구축한 `/judgment_apply` UI(0624_03). 군집 대표를 싸게 gold화하는 경로.
- **패턴 마이닝 기반(재사용/확장)**: `scripts/mine_patterns.py`(A~E 발굴), `dataset_pipeline.py`(단일 명령 파이프라인). 군집 스크립트는 이 옆에 신규 추가.
- **군집 라이브러리**: `cluster_emotion.py`는 **신규 생성 필요**. HDBSCAN/UMAP/sentence-transformers 설치 여부는 **미확인 → §5 결정사항**(미설치 시 Track A(순수 numpy/sklearn)만으로 1차 수행 가능하도록 설계).
- **결론**: full 임베딩 없이도 top-3 감정 + [pos,neg,neu] + 필드 + applied_rule + 경량 n-gram으로 **Track A 군집은 dev에서 O(n)·무 GPU로 즉시 가능**. 더 풍부한 의미 군집(Track B)은 한국어 문장 인코더를 **표본(sample)** 에만 CPU로 돌려 보완.

## 2. 설계 원칙

1. **추측 금지 — 군집 근거만.** 신규 그룹은 빈도·응집도·KoTE 미피복이 동시에 성립하는 군집에서만 후보화. ≤3개 상한(택소노미 기준선). 나머지는 grouped 유지.
2. **군집 ≠ gold.** 군집은 "묶기"일 뿐 긍/부/중 진위를 만들지 못한다(ROADMAP §5-3). 라벨링을 *싸게*(대표만 판정→전파) 할 뿐, 최종 gold는 대표 판정(사람/AI)이 받친다.
3. **필드(장점/단점)는 1급 피처 + 폴리세미 가드.** 같은 토큰이 필드로 극성이 뒤집힌다("어려움": 장점 긍 ↔ 단점 부). 군집 입력에 필드 + 규칙신호(applied_rule/override_score) 동반, raw 감정 표면만으로 묶지 않는다(§5-3 경고).
4. **긍↔부 0(양방향) 불변.** 신규 그룹은 극성 오분류를 만들면 안 된다 — 화행 그룹(개선요청·평가회피 등)은 **기본 극성 neutral**로 정의해 긍↔부 위반 회피.
5. **append-only·비식별화·내부망 전용·O(n).** 대표 예문은 가명+PII 게이트 통과분만. plans/JSONL 배포 제외. 군집 본계산은 O(n)(Track A) / 표본(Track B). 서버·prod배치·GPU 불요.

## 3. 군집 방법론 (구조)

### 3-1. 군집 대상 = "KoTE 미피복 부분코퍼스" (근거 기반 축소)

전체 87만을 다 군집하지 않고, 신규 그룹이 사는 영역으로 좁힌다(노이즈↓·해석성↑):
```
 미피복 부분코퍼스 = (KoTE top-1 = "없음")              243,613
                   ∪ (저신뢰 max(pos,neg) < 0.4)        132,938
                   ∪ (rule4_default 통과 = 무보정)       ← 오늘 누수 경로
   → 중복 제거 후 군집. 나머지(고신뢰 정서)는 KoTE 44가 이미 커버.
```

### 3-2. Track A — 경량 멀티뷰 군집 (먼저, O(n)·무모델)

레코드당 피처 벡터(혼합):
```
 [ KoTE top-3 감정 44-dim 희소 (점수 가중) ]   ← 정서 표면
 ⊕ [ pos, neg, neu ]                          ← 극성
 ⊕ [ field(장점/단점) one-hot ]                ← 1급 피처(폴리세미)
 ⊕ [ applied_rule one-hot, override_score ]    ← 규칙신호
 ⊕ [ HR n-gram TF-IDF (필요/보완/없음/모름/…) ] ← 화행 표면
   → 표준화 → 군집
```
- 알고리즘: 1차 **HDBSCAN**(밀도기반·k 불요·노이즈 라벨링) 권장. 미설치 시 **MiniBatchKMeans k-sweep + silhouette**(sklearn)로 대체. 둘 다 비교 가능하게 모듈화.
- 산출: 군집별 크기·top TF-IDF 표현·대표문(가명)·KoTE-44 분포·필드 편향·극성(s) 분포·applied_rule 혼합.

### 3-3. Track B — 의미 임베딩 군집 (다음, 표본 한정)

- 한국어 문장 인코더(예: ko-SRoBERTa)로 **층화 표본 6~10만**("없음"·저신뢰·단점-positive 오버샘플)을 CPU 임베딩 → UMAP 축소 → HDBSCAN.
- 필드를 피처로 연결 + 사후 폴리세미 점검(한 군집이 필드로 극성 분리되면 flag).
- Track A 군집과 교차검증(둘 다 떠오르는 군집 = 신뢰).
- ⚠️ 인코더 설치/반입은 §5 결정사항(내부망·dev 제약). 미승인 시 Track A만으로 1차 후보 확정.

### 3-4. Track C — 후보 그룹 판정 기준 (군집→신규 그룹 승격)

군집이 **신규 그룹 후보**가 되는 4조건(AND):
1. **빈도**: 충분히 큼(예 ≥ 수천 행) — 학습가치.
2. **응집도**: 높은 intra-유사도 / 명확한 top 표현(해석 가능).
3. **KoTE 미피복**: "없음"/저신뢰 지배 또는 KoTE-44가 불일치·분산(기존 감정으로 설명 안 됨).
4. **HR 의미성**: 인사평가 화행/감정으로 명명 가능.
- **폴리세미 군집**(필드로 극성 분리)은 승격 보류·flag(병합 금지).
- 상위 후보를 **≤3개만** 승격(기준선), 근거표(크기·표현·KoTE분포·필드·극성) 첨부. 나머지 grouped/deferred.
- **선험 가설(검증 대상, 확정 아님)** — 오늘 발굴 + "없음" 28% 정황: ⓐ 개선요청/건설적 제언(neutral) ⓑ 평가회피/무응답(neutral) ⓒ 역량 사실서술(neutral) ⓓ 약점부재 선언(neutral·긍 경계). 군집이 이를 재현/반증하는지로 판정(가설을 정답으로 쓰지 않음).

### 3-5. Track D — 대표 gold (군집≠gold 해소)

- 승격 후보별 대표문 표본 → `build_judgment_packet`(추출) → AI/사람 판정 → `/judgment_apply`(in-place) → gold 확정.
- 군집 라벨은 **weak 전파**(confidence 가중), 대표만 confirmed gold. → 신규 그룹 정의서(명칭·정의·기본 극성·예문·트랩/반례) 산출.

## 3-6. 신규 그룹 정의 스키마 (산출물 형식)

```json
{
  "group_id": "hr_improvement_request",        // KoTE 44와 충돌 없는 신규 id
  "display_name": "개선요청/건설적 제언",
  "default_polarity": "neutral",               // 긍↔부 0 보호(화행 기본 중립)
  "evidence": {"cluster_id": 7, "size": 30613, "kote_none_ratio": 0.71,
               "field_skew": "단점 0.93", "polarity_s": {"pos":0.6,"neu":0.3,"neg":0.1}},
  "definition": "현 상태의 결핍을 정중한 요청/제언으로 표현(필요·보완·했으면·하면 좋겠).",
  "exemplars": ["..."], "traps": ["보완점 없음(=긍정)", "지금처럼 유지(=칭찬)"]
}
```
- multilabel: KoTE 44 헤드 + 신규 ≤3 헤드. 신규는 confirmed gold(대표) + weak 전파(군집원, 가중)로 학습.

## 4. 단계별 로드맵

| 단계 | 내용 | 산출물 | 의존 |
|------|------|--------|------|
| **D0** | 본 설계 합의(군집 방법·≤3 상한·Track B 인코더 승인 여부) | 본 계획서 합의 | (현재) · §5 결정 |
| **D1** ✅ | `cluster_emotion.py` Track A 군집(미피복 484,119=56%, k24) | `result/emotion_clusters_260624.md`(24군집) | D0 |
| **D2** 🟡 | (선택) Track B 임베딩 군집(표본) → A와 교차검증 | 군집 교차표 | D1 · §5 인코더 승인(미설치 보류) |
| **D3** ✅ | Track C 후보 판정 → 신규 그룹 ≤3 승격(근거표) | `result/emotion_new_groups_260624.md`(G1약점부재·G2개선요청·G3역량서술) | D1 |
| **D4** ✅ | Track D 대표 gold(판정 패킷·AI 1차) + baseline 동결 | gold후보 1,318·needs_human 679(ai_reference)·baseline 1,500 | D3 |
| **D5** ✅ | 전체 멤버 weak 전파(학습 볼륨) | `emotion/group_weak_260624.jsonl` 176,483(neutral 166,334) | D4 |
| **D5-잔여** 🔄 | 택소노미 2종 문서 반영 + needs_human 사람 확인 회수 | ROADMAP/RUNBOOK 갱신 + confirmed gold | D5 |
| **D5** | 택소노미 반영(KoTE44+≤3) + RUNBOOK §누적 로그 + ROADMAP §5-3 갱신 | 갱신 문서 | D4 |
| **D6** | (P6) export/split → **KoTE 파인튜닝 착수** | 학습셋 + 후처리 가드 | D5 · 🔴 사용자 결정(예산/배포) |

## 5. 결정 필요 사항

1. **Track B 인코더 사용 승인** — 한국어 문장 인코더(ko-SBERT류)를 dev에 설치/반입해 표본 임베딩 군집을 할지. 미승인 시 **Track A(무모델, O(n))만으로 D1~D3 1차 수행**(권장: 우선 Track A로 후보 도출 → 필요 시 B로 보강).
2. **신규 그룹 상한·성격** — 기준선 "≤3"을 유지할지, 그리고 "정서"가 아닌 **화행 그룹**(개선요청·평가회피 등)을 KoTE 멀티라벨 헤드로 추가하는 방향에 동의하는지(데이터상 "없음" 28%의 정체가 화행).
3. **D6 파인튜닝 진입** — gold 임계·학습 예산·배포는 사용자 고유 결정(ROADMAP §10-2). 본 계획은 D5까지(학습 직전)를 범위로 하고 D6은 별도 승인.

## 영향도 분석

| 단계 | 변경/신규 파일 | 영향 | 안전장치 |
|------|----------------|------|----------|
| D1 | `scripts/cluster_emotion.py`(신규), `result/emotion_clusters_<date>.md` | 분석 산출만 | production 무변경·읽기 전용 |
| D4 | 판정 패킷(eval/*.jsonl), emotion.jsonl append | gold 추가 | append-only·대표만 confirmed |
| D5 | 택소노미 문서(ROADMAP/RUNBOOK), 신규 그룹 정의서 | 라벨 체계 ≤3 추가 | 군집 근거 첨부·긍↔부 0 회귀 |
| D6 | (학습 파이프라인 별도) | 모델 산출 | 규칙은 후처리 가드 유지 |

- production 코드(`perspective_service`/`hr_context_lexicon`) **무변경**(D1~D5는 데이터셋·분석 트랙). 긍↔부 0 회귀는 D4에서 동반.

## 테스트/검증 계획

1. 군집 품질: silhouette/응집도 + 대표문 사람 점검(군집이 해석 가능한가).
2. 폴리세미 점검: 승격 후보가 필드로 극성 분리되지 않는지(분리되면 보류).
3. 긍↔부 0: 신규 그룹 weak 전파 후에도 기존 회귀 7종 + 신규 골든 통과.
4. 재현성: Track A↔B 교차로 동일 군집이 떠오르는지(우연 군집 배제).
5. PII/누수: 대표 예문 export 전 정규식 게이트, plans 배포 제외 확인.

## 리스크 및 제약

| 리스크 | 영향 | 대응 |
|--------|------|------|
| top-3만 보존 → 감정공간 희소 | 군집 해상도↓ | Track A에 n-gram/규칙신호 보강 + Track B(표본 임베딩)로 교차 |
| 표면감정 군집이 폴리세미 혼합 | 긍↔부 오염 | 필드+규칙신호 동반·필드 분리 flag·병합 금지(§2-3) |
| 군집을 gold로 오용 | 정답 신뢰 붕괴 | 군집≠gold(§2-2), 대표 판정으로만 확정 |
| 신규 그룹 과다·추측 | 과적합/노이즈 | ≤3 상한·4조건 AND·근거표 필수 |
| 인코더 dev 반입 제약 | Track B 지연 | Track A 단독으로 1차 후보 확정(설계상 분리) |

**설계 원칙(불변)**: 긍↔부 0(양방향) · 추측 금지(군집 근거) · 군집≠gold · 필드 1급·폴리세미 가드 · append-only·비식별화·내부망 전용 · additive·회귀 통과 · O(n)(Track A)/표본(Track B) · 신규그룹/파인튜닝 진입은 사용자 결정.
**제약**: 서버 무단 실행 금지 · dev 배치 불가(CSV/로컬 분석만) · 외부 텍스트 비반입.
