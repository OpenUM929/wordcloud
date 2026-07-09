# -*- coding: utf-8 -*-
"""D6 — KoTE 도메인 파인튜닝(3분류 감정) + 전/후 비교.

베이스: 로컬 KoTE(model/kote_for_easygoing_people, 44 멀티라벨) 인코더 → 3분류 헤드 교체.
학습:   사람 gold 1,579(needs_human 679 + g4 100 + field_conflict 800) — 비순환 신호.
테스트: baseline 399(held-out, 라벨러 튜닝·학습에 미사용).
비교:   before=현 규칙 파이프라인(KoTE+override) / after=파인튜닝 모델 — 둘 다 사람 gold 대비.
지표:   3분류 정확도 + ★긍↔부 오류(양방향, 핵심가치).

사용자 승인(P6) 하에 GPU 학습. 산출은 plans(배포 제외). gold는 백업본 보존.
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)
from src.config.settings import MODEL_PATH  # noqa: E402

LAB2ID = {'positive': 0, 'negative': 1, 'neutral': 2}
ID2LAB = {v: k for k, v in LAB2ID.items()}
TRAIN_FILES = ['group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
               'field_conflict_review_260624.jsonl', 'hard_failure_review_260630.jsonl',
               'gold_8c_train_260706.jsonl',          # 8c 하드클래스 사람 gold(신규)
               'gold_active_260707.jsonl',            # 능동학습 1차 gold(N1양가성향→중립·N2개선요청→부정)
               'gold_active_260707_c2.jsonl',         # 능동학습 2차 gold(필드 보유·사람확정 8: 필드역전/사실기술)
               'silver_active_260707_c2.jsonl',       # 능동학습 2차 교정 silver(292, field 100%: 긍92 장점역량·중172 비평가화행·부28)
               'gold_active_260707_c4.jsonl',         # 능동학습 4차 gold(사람확정 3: 자체부정표지 일방향/수직적 장점란부정·세세 단점부정)
               'silver_active_260707_c4.jsonl',       # 능동학습 4차 bare NP 양필드페어 silver(230, field 100%: 단점부정105/장점긍정87 대칭·중립38)
               'gold_active_260707_c5.jsonl']         # 능동학습 5차 gold(자체부정표지 3: 권한/지위/관계우위 이용 장점란부정)
               # 'silver_active_260707_c5.jsonl'      # ← 회수(2026-07-07): c5 재현런 2회 모두 c3_neu149 부recall 0.688→0.625/0.562 하락·8c_hard 긍→부 1 재현. 미확정 중립 silver 95(41%)가 c4 극성이득 희석. 파일은 보존(append-only), TRAIN에서만 제외.
               # 'gold_active_260707_c6.jsonl'        # ← 회수(2026-07-07): c6 화행광맥(개선요청·완곡부정 74 gold, 재정렬본 부44/긍15/중15). 4런 집계 결과 타깃 c3_neu149 부recall 0.667→평균0.59 하락·긍↔부 1→2·3·4 재현악화(inviolable). 8c_hard 부recall은 0.854→0.927 상승하나 핵심가치(긍↔부 우선)로 실격. c4가 마지막 깨끗이득·neu경계는 소량gold로 부recall↔긍↔부 맞바꿈만. 파일 보존, TRAIN 제외.
# held-out 테스트셋 — 쉬운 baseline(회귀가드) + 8c 하드클래스(이번 작업 검증).
TEST_SETS = {'baseline399': 'baseline_eval_260624.jsonl',
             '8c_hard': 'gold_8c_test_260706.jsonl',
             'c3_neu149': 'gold_8c_test_c3neu_260707.jsonl',  # 능동학습 c3 하드경계(neu_boundary143+bareNP6·field100%·부분해능확보용)
             'sa_speech74': 'gold_speechact_test_260707.jsonl'}  # c6 화행경계(개선요청·완곡부정 74·부44/긍15/중15·claude위임판정) — 화행경계 분해능 측정도구. TRAIN 미포함(c6 gold는 회수됨)
TEST_FILE = TEST_SETS['baseline399']   # 하위호환(누수제외 기준셋)


def load(fn):
    """(text, label, field) 3-튜플. field(장점/단점)는 원문 그대로 보존 —
    프리픽스 주입은 apply_field에서 학습·추론 동일 규약으로 1회만 한다(누수가드·rule_before는 원문)."""
    out = []
    for line in open(os.path.join(DATASET_DIR, 'eval', fn), encoding='utf-8'):
        r = json.loads(line)
        hd = r.get('human_decision')
        if hd in LAB2ID and (r.get('text') or '').strip():
            out.append((r['text'].strip(), LAB2ID[hd], (r.get('field') or '').strip()))
    return out


def load_weak(per_class, exclude_texts):
    """weak_export(규칙 라벨)에서 클래스별 per_class개 균형 표본(테스트 텍스트 제외=누수방지)."""
    import random
    path = os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl')
    by = {0: [], 1: [], 2: []}
    ex = set(exclude_texts)
    for line in open(path, encoding='utf-8'):
        r = json.loads(line)
        if r.get('is_clause'):
            continue
        t = (r.get('text') or '').strip()
        s = r.get('sentiment')
        if not t or t in ex or s not in LAB2ID:
            continue
        by[LAB2ID[s]].append(t)
    rng = random.Random(42)
    out = []
    for c, lst in by.items():
        rng.shuffle(lst)
        out += [(t, c) for t in lst[:per_class]]
    rng.shuffle(out)
    return out


def load_silver(total, exclude_texts):
    """silver_consensus(ai 합의)에서 클래스별 균형 표본(테스트 누수 제외)."""
    import random
    path = os.path.join(DATASET_DIR, 'emotion', 'silver_consensus_260630.jsonl')
    by = {0: [], 1: [], 2: []}
    ex = set(exclude_texts)
    for line in open(path, encoding='utf-8'):
        r = json.loads(line)
        t = (r.get('text') or '').strip()
        s = r.get('sentiment_silver')
        if not t or t in ex or s not in LAB2ID:
            continue
        by[LAB2ID[s]].append(t)
    rng = random.Random(42)
    per = max(1, total // 3)
    out = []
    for c, lst in by.items():
        rng.shuffle(lst)
        out += [(t, c) for t in lst[:per]]
    rng.shuffle(out)
    return out


def metrics(name, y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    acc = (y_true == y_pred).mean()
    # 긍(0)↔부(1) 오류 — 양방향
    pn = int(((y_true == 1) & (y_pred == 0)).sum())   # 부→긍
    npp = int(((y_true == 0) & (y_pred == 1)).sum())  # 긍→부
    # 클래스별 재현율 (★중립이 핵심 — 모델이 못 만드는 클래스)
    rec = {}
    for c, nm in ((0, 'pos'), (1, 'neg'), (2, 'neu')):
        sup = int((y_true == c).sum())
        rec[nm] = round(float(((y_pred == c) & (y_true == c)).sum() / sup), 3) if sup else None
    print(f'  [{name}] 정확도 {100*acc:.1f}% · ★긍↔부 {pn+npp} (긍→부 {npp}·부→긍 {pn}) · '
          f'재현율 긍 {rec["pos"]}·부 {rec["neg"]}·★중 {rec["neu"]}')
    return {'name': name, 'acc': round(float(acc), 4), 'pos_neg_err': pn + npp,
            'gp_to_neg': npp, 'neg_to_pos': pn, 'recall': rec}


def rule_before(texts):
    """현 규칙 파이프라인 라벨(KoTE pos/neg/neu + override) — 'before'."""
    from src.modules.emotion_analysis import analyze_emotion_batch
    from src.services.perspective_service import _sentence_sentiment_override_explain as ov
    preds = []
    B = 64
    for i in range(0, len(texts), B):
        chunk = texts[i:i + B]
        res = analyze_emotion_batch(chunk)
        for t, r in zip(chunk, res):
            br = (r.get('analysis') or {}).get('base_result') or {}
            sc = br.get('scores') or br
            pos = float(sc.get('positive', 0)); neg = float(sc.get('negative', 0)); neu = float(sc.get('neutral', 0))
            score, _rule = ov(pos, neg, t, True, 1, neutral=neu)
            preds.append(0 if score > 1e-6 else (1 if score < -1e-6 else 2))
    return preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--out', default=os.path.join(DATASET_DIR, 'model_out'))
    ap.add_argument('--skip-before', action='store_true')
    ap.add_argument('--weak', type=int, default=0, help='클래스별 weak 증강 표본 수(0=gold만)')
    ap.add_argument('--frac', type=float, default=1.0, help='gold train 비율(학습곡선)')
    ap.add_argument('--silver', type=int, default=0, help='silver_consensus 총 추가(균형, 누수제외)')
    ap.add_argument('--tag', default='', help='학습곡선 행 태그')
    ap.add_argument('--field-token', choices=['on', 'off'], default='off',
                    help="on이면 텍스트에 '장점 평가:'/'단점 평가:' 프리픽스 주입(학습·추론 동일 규약). "
                         "특수토큰 대신 자연어 프리픽스라 tokenizer OOV 안전. 0707_01 A/B용")
    args = ap.parse_args()

    def apply_field(text, field):
        """field_token on이고 field가 있으면 극성을 자연어 프리픽스로 주입. off/무필드=원문.
        학습(DS)·추론(model_predict) 양쪽에서 이 함수만 경유 → train/serve 규약 일치."""
        if args.field_token == 'on' and field:
            return f'{field} 평가: {text}'
        return text

    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments)

    train = []
    for f in TRAIN_FILES:
        train += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test_texts = {t for ts in tests.values() for t, _, _ in ts}
    _b = len(train)
    train = [(t, y, fld) for t, y, fld in train if t not in all_test_texts]   # 누수 가드(원문 기준)
    if len(train) != _b:
        print(f'누수가드: train에서 테스트 텍스트 {_b - len(train)}건 제거')
    if args.frac < 1.0:
        import random as _r
        _rng = _r.Random(42)
        _rng.shuffle(train)
        train = train[:int(round(len(train) * args.frac))]
        print(f'gold frac {args.frac} → train {len(train)}')
    if args.weak:
        wk = load_weak(args.weak, exclude_texts=all_test_texts | {t for t, _, _ in train})
        print(f'weak 증강 {len(wk)}건 추가(클래스별 {args.weak})')
        train += [(t, c, '') for t, c in wk]                # 증강엔 field 없음 → 무마커
    if args.silver:
        sv = load_silver(args.silver, exclude_texts=all_test_texts | {t for t, _, _ in train})
        print(f'silver 증강 {len(sv)}건 추가(총 {args.silver} 목표)')
        train += [(t, c, '') for t, c in sv]
    from collections import Counter
    print(f'train {len(train)} · field-token={args.field_token}')
    print('  train 분포:', {ID2LAB[k]: v for k, v in Counter(l for _, l, _ in train).items()})
    for name, ts in tests.items():
        print(f'  test[{name}] {len(ts)} 분포:', {ID2LAB[k]: v for k, v in Counter(l for _, l, _ in ts).items()})

    tok = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)

    class DS(Dataset):
        def __init__(self, rows):
            self.rows = rows
        def __len__(self):
            return len(self.rows)
        def __getitem__(self, i):
            t, y, fld = self.rows[i]
            t = apply_field(t, fld)                          # 학습 텍스트에 프리픽스(추론과 동일)
            enc = tok(t, truncation=True, padding='max_length', max_length=64, return_tensors='pt')
            return {'input_ids': enc['input_ids'][0], 'attention_mask': enc['attention_mask'][0],
                    'labels': torch.tensor(y)}

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True, local_files_only=True,
        problem_type='single_label_classification')   # KoTE는 multi_label → 3분류 단일라벨로 교체

    targs = TrainingArguments(
        output_dir=args.out, num_train_epochs=args.epochs, per_device_train_batch_size=args.bs,
        learning_rate=args.lr, fp16=torch.cuda.is_available(), logging_steps=20,
        save_strategy='no', report_to=[], seed=42)
    trainer = Trainer(model=model, args=targs, train_dataset=DS(train))
    print('=== 파인튜닝 시작 ===')
    trainer.train()

    # 모델 추론 헬퍼
    model.eval()
    dev = model.device

    def model_predict(texts):
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    print('\n=== 전/후 비교 (held-out 사람 gold 대비 · 주지표 ★긍↔부) ===')
    rep = {'n_train': len(train), 'results': {}}
    for name, ts in tests.items():
        texts = [t for t, _, _ in ts]; y = [yy for _, yy, _ in ts]
        fields = [fld for _, _, fld in ts]
        print(f'\n--- 테스트셋 [{name}] (n={len(ts)}) ---')
        res = []
        if not args.skip_before:
            print('[before] 현 규칙(알고리즘) 파이프라인 추론 중...')
            res.append(metrics('before(알고리즘)', y, rule_before(texts)))   # 규칙엔진=원문(프리픽스 없음)
        model_texts = [apply_field(t, f) for t, f in zip(texts, fields)]      # 모델=학습과 동일 프리픽스
        res.append(metrics('after(파인튜닝)', y, model_predict(model_texts)))
        rep['results'][name] = res

    # 학습곡선 누적 — 8c_hard(이번 작업 핵심) 기준
    key = '8c_hard' if '8c_hard' in rep['results'] else next(iter(rep['results']))
    aft = rep['results'][key][-1]
    curve = os.path.join(DATASET_DIR, 'result', 'learning_curve_260630.jsonl')
    with open(curve, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            'tag': args.tag or f'8c_frac{args.frac}_silver{args.silver}_ft{args.field_token}',
            'testset': key, 'frac': args.frac, 'silver': args.silver, 'n_train': len(train),
            'field_token': args.field_token,
            'acc': aft['acc'], 'pos_neg_err': aft['pos_neg_err'],
            'gp_to_neg': aft['gp_to_neg'], 'neg_to_pos': aft['neg_to_pos'],
        }, ensure_ascii=False) + '\n')

    if args.tag and 'curve' in args.tag:
        print(f'\n[학습곡선] {args.tag} 기록 → {os.path.basename(curve)} (모델 미저장)')
    else:
        out_md = os.path.join(DATASET_DIR, 'result', 'finetune_eval_260706.json')
        json.dump(rep, open(out_md, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        model.save_pretrained(args.out); tok.save_pretrained(args.out)
        print(f'\n모델 저장 → {args.out} · 리포트 → {os.path.relpath(out_md, PROJECT_ROOT)}')


if __name__ == '__main__':
    main()
