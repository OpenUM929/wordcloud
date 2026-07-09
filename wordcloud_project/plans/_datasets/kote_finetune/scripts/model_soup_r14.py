# -*- coding: utf-8 -*-
"""개선 레버 L2 — **모델 수프(가중치 평균)** 실측(plans/2026/0708_02 §L2).

배경: 8차에서 앙상블(seed5 소프트보팅)이 유일 순이득(+1~3pp·flutter 소거)이었으나
K배 서빙 비용으로 best-seed45 단일모델로 후퇴 → 이득 미회수 상태. 동일 베이스에서
파인튜닝된 seed들은 loss basin을 공유하므로 **state_dict 평균(soup) 단일모델**이
앙상블 이득의 상당분을 서빙비용 1배로 회수하는지 실측한다.

방법:
1. 재료 = model_out(seed45) + model_out_seed{42,43,44,46} (ensemble_eval_r8 --save-seed 재현).
2. uniform soup(전 재료 평균) + greedy soup(--dev-slice에서 개선 시만 재료 추가) 2종.
   greedy의 선택셋(dev-slice)은 판정에서 제외하고 나머지 슬라이스로만 판단(선택 과적합 방지).
3. 4슬라이스 3자 비교: soup vs seed45 단일 vs 앙상블(8차 기록 ensemble_eval_260708.json).

성공기준(0708_02 §L2): soup가 seed45 대비 c3_neu149·8c_hard 우세 + 앙상블 격차 절반 이상
회수 + **긍↔부 0(전 슬라이스)**. 배포모델 미덮어씀 — 수프는 model_soup_* 별도 디렉토리 저장.
실행: python model_soup_r14.py [--dev-slice 8c_hard]
"""
import argparse
import json
import os
import sys
from collections import OrderedDict

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from finetune_sentiment import (TEST_SETS, load, metrics,  # noqa: E402
                                ID2LAB, DATASET_DIR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dirs', default='model_out,model_out_seed42,model_out_seed43,'
                                      'model_out_seed44,model_out_seed46',
                    help='DATASET_DIR 기준 재료 모델 디렉토리(첫번째=배포 seed45 대조군)')
    ap.add_argument('--dev-slice', default='8c_hard',
                    help='greedy 선택 전용 슬라이스(판정은 나머지 슬라이스로)')
    ap.add_argument('--save', action='store_true', help='soup 가중치를 model_soup_*에 저장')
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    dirs = [os.path.join(DATASET_DIR, d.strip()) for d in args.dirs.split(',') if d.strip()]
    for d in dirs:
        assert os.path.isdir(d), f'재료 없음: {d}'
    names = [os.path.basename(d) for d in dirs]
    print(f'재료 {len(dirs)}종: {names} · greedy dev-slice={args.dev_slice}')

    tok = AutoTokenizer.from_pretrained(dirs[0], local_files_only=True)

    # 저장 모델은 전부 field-token on 규약으로 학습됨 → 테스트도 동일 프리픽스
    def apply_field(text, field):
        return f'{field} 평가: {text}' if field else text

    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    packs = {}
    for name, ts in tests.items():
        packs[name] = {'y': [y for _, y, _ in ts],
                       'mt': [apply_field(t, f) for t, _, f in ts]}

    use_cuda = torch.cuda.is_available()

    def predict(model, texts):
        model.eval()
        dev = model.device
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    def eval_model(model, tag):
        res = {}
        for name, pk in packs.items():
            res[name] = metrics(f'{name} {tag}', pk['y'], predict(model, pk['mt']))
        return res

    def gate_ok(res):
        """불가침 게이트: baseline399·8c_hard 긍↔부 0."""
        return all(res[s]['pos_neg_err'] == 0 for s in ('baseline399', '8c_hard') if s in res)

    # ── 재료 로드(state_dict CPU 보관) + 개별 성적 ──
    states, per_model = [], {}
    base_model = None
    for d, nm in zip(dirs, names):
        m = AutoModelForSequenceClassification.from_pretrained(d, local_files_only=True)
        if use_cuda:
            m = m.cuda()
        print(f'\n--- 재료 [{nm}] 개별 성적 ---')
        per_model[nm] = eval_model(m, nm)
        states.append(OrderedDict((k, v.cpu().clone()) for k, v in m.state_dict().items()))
        if base_model is None:
            base_model = m           # 수프 로딩 재사용용(마지막에 가중치 교체)
        else:
            del m
            if use_cuda:
                torch.cuda.empty_cache()

    float_keys = [k for k, v in states[0].items() if v.dtype.is_floating_point]

    def soup_of(idxs):
        """지정 재료들의 uniform 평균 state_dict(비부동소수 버퍼는 첫 재료 것)."""
        sd = OrderedDict((k, v.clone()) for k, v in states[idxs[0]].items())
        for k in float_keys:
            acc = states[idxs[0]][k].to(torch.float64)
            for i in idxs[1:]:
                acc = acc + states[i][k].to(torch.float64)
            sd[k] = (acc / len(idxs)).to(states[0][k].dtype)
        return sd

    def eval_state(sd, tag):
        base_model.load_state_dict(sd)
        if use_cuda:
            base_model.cuda()
        return eval_model(base_model, tag)

    # ── uniform soup ──
    print('\n' + '=' * 60)
    print(f'=== UNIFORM SOUP ({len(states)}재료 평균) ===')
    uni_idx = list(range(len(states)))
    uni_sd = soup_of(uni_idx)
    uni_res = eval_state(uni_sd, 'uniform_soup')
    print(f'  게이트(긍↔부 0): {"PASS" if gate_ok(uni_res) else "FAIL"}')

    # ── greedy soup: dev-slice acc 순 정렬 → 개선 시만 추가 ──
    print('\n' + '=' * 60)
    print(f'=== GREEDY SOUP (선택셋={args.dev_slice} · 판정은 나머지 슬라이스) ===')
    order = sorted(range(len(states)),
                   key=lambda i: per_model[names[i]][args.dev_slice]['acc'], reverse=True)
    chosen = [order[0]]
    best_dev = per_model[names[order[0]]][args.dev_slice]['acc']
    print(f'  시작 재료: {names[order[0]]} (dev acc {best_dev:.4f})')
    for i in order[1:]:
        cand = chosen + [i]
        sd = soup_of(cand)
        base_model.load_state_dict(sd)
        if use_cuda:
            base_model.cuda()
        pk = packs[args.dev_slice]
        acc = float(np.mean(np.array(predict(base_model, pk['mt'])) == np.array(pk['y'])))
        take = acc >= best_dev     # 동률 포함(재료 늘어날수록 분산↓ 기대)
        print(f'  +{names[i]} → dev acc {acc:.4f} ({"채택" if take else "기각"})')
        if take:
            chosen, best_dev = cand, acc
    grd_sd = soup_of(chosen)
    grd_names = [names[i] for i in chosen]
    print(f'  최종 greedy 재료 {len(chosen)}종: {grd_names}')
    grd_res = eval_state(grd_sd, 'greedy_soup')
    print(f'  게이트(긍↔부 0): {"PASS" if gate_ok(grd_res) else "FAIL"}')

    # ── 3자 비교표(vs seed45 단일 vs 앙상블 8차 기록) ──
    ens_path = os.path.join(DATASET_DIR, 'result', 'ensemble_eval_260708.json')
    ens = json.load(open(ens_path, encoding='utf-8'))['slices'] if os.path.exists(ens_path) else {}
    seed45 = per_model[names[0]]
    print('\n' + '=' * 60)
    print('=== 3자 비교: seed45 단일 vs SOUP vs 앙상블(8차 기록) ===')
    for name in packs:
        e = ens.get(name, {}).get('ensemble', {})
        print(f'\n[{name}]')
        print(f"  seed45   acc {seed45[name]['acc']:.4f} · 긍↔부 {seed45[name]['pos_neg_err']}")
        print(f"  uniform  acc {uni_res[name]['acc']:.4f} · 긍↔부 {uni_res[name]['pos_neg_err']}"
              f" (Δ vs seed45 {uni_res[name]['acc'] - seed45[name]['acc']:+.4f})")
        print(f"  greedy   acc {grd_res[name]['acc']:.4f} · 긍↔부 {grd_res[name]['pos_neg_err']}"
              f" (Δ vs seed45 {grd_res[name]['acc'] - seed45[name]['acc']:+.4f})")
        if e:
            print(f"  ensemble acc {e.get('acc'):.4f} · 긍↔부 {e.get('pos_neg_err')} (8차 기록)")

    report = {'ingredients': names, 'dev_slice': args.dev_slice,
              'per_model': per_model, 'uniform': uni_res, 'uniform_gate': gate_ok(uni_res),
              'greedy': grd_res, 'greedy_gate': gate_ok(grd_res),
              'greedy_ingredients': grd_names,
              'ensemble_ref': {k: v.get('ensemble') for k, v in ens.items()}}
    out = os.path.join(DATASET_DIR, 'result', 'model_soup_260708.json')
    json.dump(report, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')

    if args.save:
        for tag, sd in (('uniform', uni_sd), ('greedy', grd_sd)):
            d = os.path.join(DATASET_DIR, f'model_soup_{tag}')
            base_model.load_state_dict(sd)
            base_model.cpu().save_pretrained(d)
            tok.save_pretrained(d)
            print(f'수프 저장 → {d} (배포 반영은 별도 승인)')


if __name__ == '__main__':
    main()
