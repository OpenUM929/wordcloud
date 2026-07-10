# KoTE 도메인 파인튜닝 — 전/후 비교 리포트 (D6, 260624)

> 계획서 `plans/2026/0624_04_emotion-clustering` D6. 사용자 승인(P6) 하에 GPU 학습.
> 핵심가치: 긍↔부 오분류 0(양방향).

## 결과 (headline)

| | 3분류 정확도 | ★긍↔부 오류(양방향) |
|---|---|---|
| **before — 현 규칙 파이프라인**(KoTE+override) | 56.0% | **10** (부→긍 10·긍→부 0) |
| **after — 파인튜닝 KoTE** | **89.7%** | **0** ✅ |

- **정확도 +33.7%p, 긍↔부 오류 10 → 0.** 규칙 트랙의 천장(부→긍 누수)을 모델이 넘어섬.

## 셋업

- **베이스**: 로컬 KoTE(`model/kote_for_easygoing_people`, ELECTRA 44 멀티라벨) → 3분류 단일라벨 헤드 교체.
- **학습**: 사람 gold **1,579**(needs_human 679 + g4 100 + field_conflict 800). 분포 positive 594 / neutral 685 / negative 300. **비순환**(규칙 weak 미사용 — 사람 판정만).
- **테스트**: `baseline_eval_260624`(held-out **398**, 학습·라벨러 튜닝에 미사용). 분포 positive 233 / negative 97 / neutral 68.
- 4 epoch · lr 2e-5 · fp16 · 학습 63초(GPU 1).
- 스크립트 `scripts/finetune_sentiment.py` · 모델 `model_out/` · 지표 `result/finetune_eval_260624.json`.

## 의미

- **당신(사람)의 gold가 결정적**이었다. 규칙으로는 못 넘던 "보완점 없음/배려가 아쉽다/장점 없음/조건부 제언" 등 경계를 모델이 gold에서 학습.
- before(규칙) 56%는 baseline이 **일부러 모은 어려운 경계 + 절 분리**라 낮게 나온 면이 있으나, **동일 테스트 apples-to-apples** 비교라 개선폭은 신뢰 가능.
- 라벨러(규칙)는 63%가 천장이었는데, 파인튜닝은 **89.7% + 긍↔부 0** — "규칙은 보조, 모델이 본체"가 데이터로 증명됨.

## ③ weak 증강 실험 (수행 — 정직한 음성 결과)

gold에 규칙 weak 라벨을 클래스별 2,000(총 6,000) 증강해 재학습 → **오히려 악화**:

| 학습 데이터 | 정확도 | ★긍↔부 오류 |
|---|---|---|
| **gold-only (1,579)** | **89.7%** | **0** |
| gold + weak 6,000 | 85.7% | **7** (부→긍 7) |

- weak는 규칙 파이프라인 출력(부→긍 누수 포함)이라, 학습 시 **모델이 규칙의 실수를 흡수 → 제거했던 부→긍 7이 되살아남.** 순환 가설의 실증.
- **결론: weak 증강 채택 안 함. gold-only가 최종.** "규칙은 보조, 사람 gold가 본체"가 한 번 더 확인됨.

## 멀티라벨 헤드 실험 (KoTE44 + G1/G2/G4 통합 — 수행)

ROADMAP 택소노미(KoTE44+≤3)를 단일 47-라벨 모델로 구현. 12,000 표본, 희소그룹 오버샘플 +임계 0.3.

| 라벨 | F1 | 비고 |
|---|---|---|
| G1 약점부재 | 0.906 | 양호 |
| G2 개선요청 | 0.411 | 고recall·저precision(과예측) |
| G4 자기개발 | 0.362 | 동일 |
| 44감정 retention | 0.553 | 헤드가 감정 다소 손상 |

**정직한 결론: 통합 멀티라벨 헤드는 현재 분리 구성보다 열등 → 채택 보류.**
- 신규 3그룹은 **결정적 선별기(is_no_weakness/has_improvement_request/is_growth)가 F1 1.0·무비용** 인데, 신경망 증류는 0.36~0.91로 손실만 발생.
- 44감정은 **베이스 KoTE 그대로**가 retention 0.55보다 우월.
- → 권장 아키텍처: **베이스 KoTE(44감정) + 선별기(G1/G2/G4) + 3분류 파인튜닝(극성)** 을 분리 유지. 통합은 추론 1회 이점이나 정확도 손실이 커 비추천(per-class 임계·soft 증류·데이터 증량으로 개선 여지는 있음).
- 산출: `scripts/finetune_multilabel.py`·`result/finetune_multilabel_260624.json`·`model_out_multilabel/`.

## 운영 투입(교체) — 되돌리기 가능·폴백 안전 (수행)

- **모델 배치**: `model/hr_sentiment_finetuned/`(베이스 KoTE 불변·additive). 배포 빌드 `/E` 재귀라 -Package에 자동 포함.
- **설정**: `settings.py` `USE_HR_SENTIMENT_MODEL`(env `USE_HR_SENTIMENT_MODEL=0`로 끔) + `HR_SENTIMENT_MODEL_PATH`. settings.py 백업 `settings.py.bak_finetune`.
- **추론 모듈**: `src/modules/hr_sentiment.py`(싱글톤·지연로드). **로드/추론 실패 시 None→규칙 폴백**(production 무중단).
- **통합 지점**: `perspective_service._get_sentence_level_scores`(배치) — 플래그 on이면 문장 배치 추론으로 극성 결정, off/실패면 기존 `sentence_sentiment_override`(규칙). 베이스 KoTE 44감정·리더십은 불변.
- ⚠️ **검증 전제**: 서버 무단 실행 금지로 **실서버 미검증**. 프로덕션 빌드 전 dev에서 플래그 on 배치 1회 비교 권장. 롤백 = `USE_HR_SENTIMENT_MODEL=0`(즉시).
- 미덮는 경로(직접 override 호출): `perspective_routes:975`(감정 테스트), `test_routes`(테스트) — 단건/테스트라 영향 작음, 규칙 유지.

## 정직한 한계 / 다음

- 테스트는 같은 시기·분포의 held-out — **완전 신규 배치**로 한 번 더 검증하면 일반화 확증.
- neutral(모호 영역)이 가장 어려움 — 잔여 오차의 주류로 추정(긍↔부 아닌 영역).
- 개선 여지: weak 데이터 증강(③ 절분리 weak)·gold 추가·하이퍼파라미터·신규 그룹(G1/G2/G4) 멀티라벨 헤드 확장.
- 배포: 모델·plans 산출은 내부망 전용(배포 제외). 운영 투입은 별도 결정.
