# -*- coding: utf-8 -*-
"""D7 — 하드샘플 능동학습: 파인튜닝 모델로 풀을 채점해 검토 후보를 마이닝.

목적: 84%대 8c_hard를 더 올리기 위해, 모델이 **틀리거나 헷갈리는** 문장만 골라
사람 검토 큐로 방출한다(무작위 대량 금지·하드샘플 우선, project_finetune_data_ceiling).

풀(둘 다 텍스트+약/실버 라벨 보유, 아직 gold 아님):
  emotion/weak_export_260624.jsonl   (규칙 라벨 sentiment, is_clause 제외)
  emotion/silver_consensus_260630.jsonl (ai 합의 sentiment_silver, field 보유)
이미 gold(train+test)인 텍스트는 제외(재라벨 낭비 방지).

하드 tier(--tiers로 선택, --mix로 혼합):
  ① flip_pn      : 모델 극(긍/부) ≠ 풀 극(긍/부)  ← 긍↔부 불일치, 고확신부터(모델 오류 or 풀 오류)
  ② low_margin   : |p_pos - p_neg| < margin        ← 모델이 긍/부 구분 못 함
  ③ neu_boundary : 모델 neu ↔ 풀 극  또는  모델 극(저확신) ↔ 풀 neu  ← 진짜 어려운 중립 클래스

⚠ 능동학습 1차 교훈(2026-07-07): flip_pn만 상위 300 뽑았더니 **모델 긍↔부 오류 0건**
(그 tier는 모델이 이미 맞는 영역·불일치=풀 라벨 오류) → 재학습 지표 무변화. 2차는
**low_margin·neu_boundary**(모델이 실제로 헷갈리는 중립경계)로 옮기고, strict 우선순위
독식을 막으려 --mix(tier 라운드로빈)로 tier를 고르게 섞는다. (IMPROVEMENT_HISTORY 참조.)

출력: eval/review/hard_queue_YYMMDD.jsonl (판정 prefill·escalation용, status=1).
     claude_judgment/human_decision 은 비움 — 다음 단계에서 채운다
     (feedback_prefill_judgment_escalate_uncertain: claude prefill→불확실만 사용자).
     field는 풀(silver_consensus)에서 상속 — gold에 필드신호가 실린다(field-token 학습용).

GPU 채점만 사용자 실행. 2차 권장(field 필수·중립경계·tier 혼합):
  python scripts/mine_hard_samples.py --model model_out_ft_on --field-token on \
    --require-field --tiers low_margin,neu_boundary --mix --n 300
⚠ --require-field 필수: field 없는 후보(weak_export 87만, field 0%)는 장점/단점 협의 해석이
  불가해 중립으로 뭉개진다(1차 gold_active field="" 전멸의 원인). silver_consensus(field 100%)만 남긴다.
(1차식 전체 tier 강경순위: --tiers flip_pn,low_margin,neu_boundary 로 --mix 생략)

진행상황·재개: 배치마다 진행률·ETA를 출력하고 확률을 체크포인트(.mine_ckpt_*.jsonl)에
append 저장한다. 도중에 Ctrl-C로 죽여도 같은 명령으로 다시 켜면 완료분을 재사용해 이어서
채점한다(풀크기·필드토큰·모델이 같을 때). 처음부터 다시 하려면 --no-resume. 빠른 1차 표본은
--max-pool 100000.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)

LAB2ID = {'positive': 0, 'negative': 1, 'neutral': 2}
ID2LAB = {v: k for k, v in LAB2ID.items()}
# ⚠ silver_consensus를 먼저 로드한다: silver의 3만 텍스트가 weak_export에 100% 포함돼 있어
# (실측 2026-07-07: 30000/30000 겹침) weak_export를 먼저 읽으면 dedup이 field 보유 silver 행을
# 전부 버려 --require-field가 0건이 된다. field 있는 쪽이 dedup을 이기도록 silver를 앞에 둔다.
POOLS = [
    ('emotion/silver_consensus_260630.jsonl', 'sentiment_silver'),
    ('emotion/weak_export_260624.jsonl', 'sentiment'),
]
# gold(=이미 사람 확정) 텍스트는 마이닝 제외 — finetune_sentiment.TRAIN_FILES/TEST_SETS 와 동일
GOLD_FILES = ['group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
              'field_conflict_review_260624.jsonl', 'hard_failure_review_260630.jsonl',
              'gold_8c_train_260706.jsonl', 'baseline_eval_260624.jsonl',
              'gold_8c_test_260706.jsonl', 'gold_active_260707.jsonl',
              'gold_active_260707_c2.jsonl', 'silver_active_260707_c2.jsonl']


def _gold_texts():
    ex = set()
    for fn in GOLD_FILES:
        p = os.path.join(DATASET_DIR, 'eval', fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = (r.get('text') or '').strip()
            if t:
                ex.add(t)
    return ex


def _load_pool(exclude):
    """[(text, field, pool_label)], 텍스트 중복·gold·절(clause) 제외."""
    seen = set(exclude)
    rows = []
    for rel, label_key in POOLS:
        p = os.path.join(DATASET_DIR, rel)
        if not os.path.exists(p):
            print(f'  (풀 없음, 건너뜀) {rel}')
            continue
        for line in open(p, encoding='utf-8'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('is_clause'):
                continue
            t = (r.get('text') or '').strip()
            lab = r.get(label_key)
            if not t or t in seen or lab not in LAB2ID:
                continue
            seen.add(t)
            rows.append((t, (r.get('field') or '').strip(), LAB2ID[lab]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True, help='파인튜닝 모델 디렉터리(예: model_out_ft_on)')
    ap.add_argument('--field-token', choices=['on', 'off'], default='off',
                    help='모델 학습 규약과 동일하게(on이면 장점/단점 프리픽스). train/serve 정합 필수')
    ap.add_argument('--margin', type=float, default=0.15, help='low_margin 임계 |p_pos-p_neg|')
    ap.add_argument('--tiers', default='low_margin,neu_boundary',
                    help='포함 tier(콤마): flip_pn,low_margin,neu_boundary. 2차 기본=중립경계 두 tier')
    ap.add_argument('--mix', action='store_true',
                    help='tier 라운드로빈 혼합(한 tier 독식 방지). 미지정 시 tier 강경 우선순위')
    ap.add_argument('--require-field', action='store_true',
                    help='장점/단점 field 있는 문장만 채굴(field 없으면 장점·단점 협의 해석 불가→중립도장 방지). '
                         'silver_consensus만 field 보유. 2차 필수.')
    ap.add_argument('--n', type=int, default=300, help='큐 최대 후보 수')
    ap.add_argument('--max-pool', type=int, default=0,
                    help='채점할 풀 상한(0=전체). 빠른 1차 마이닝 시 예: 100000(무작위 표본)')
    ap.add_argument('--out', default='', help='출력 경로(기본 eval/review/hard_queue_YYMMDD.jsonl)')
    ap.add_argument('--ckpt', default='', help='체크포인트 경로(기본 eval/review/.mine_ckpt_*.jsonl)')
    ap.add_argument('--no-resume', action='store_true', help='체크포인트 무시하고 처음부터 채점')
    args = ap.parse_args()

    def apply_field(text, field):
        if args.field_token == 'on' and field:
            return f'{field} 평가: {text}'
        return text

    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    model_dir = args.model if os.path.isabs(args.model) else os.path.join(DATASET_DIR, args.model)
    tok = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True)
    model.eval()
    dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(dev)  # ★ CUDA 있으면 GPU로 — 없으면 스크립트가 CPU에 남아 수십 배 느려짐
    print(f'채점 디바이스: {dev}'
          + (f' ({torch.cuda.get_device_name(0)})' if dev.type == 'cuda' else ' — GPU 미탐지, CPU'),
          flush=True)

    ex = _gold_texts()
    pool = _load_pool(ex)
    if args.require_field:
        before = len(pool)
        pool = [row for row in pool if row[1]]  # row=(text, field, label); field 있어야 협의 해석 가능
        print(f'  --require-field: field 있는 문장만 → {before}→{len(pool)}건(장점/단점 보유)', flush=True)
    print(f'gold 제외 {len(ex)}건 · 마이닝 풀 {len(pool)}건 · field-token={args.field_token}',
          flush=True)
    if args.max_pool and len(pool) > args.max_pool:
        import random as _r
        pool = _r.Random(42).sample(pool, args.max_pool)
        print(f'  풀 상한 적용 → 무작위 {len(pool)}건만 채점', flush=True)
    if not pool:
        print('풀이 비었습니다. 종료.')
        return

    import time
    texts = [apply_field(t, f) for t, f, _ in pool]
    BATCH = 128
    n_batches = (len(texts) + BATCH - 1) // BATCH

    # ── 체크포인트: 죽였다 다시 켜도 이어서 채점(대량 풀 재채점 방지) ──
    # 배치 단위로 확률을 append 저장. 재실행 시 설정(풀크기·필드토큰·모델)이 같으면 재사용.
    # 풀 순서는 결정적(파일순 dedup·seed42 표본)이라 배치 인덱스 정합이 유지된다.
    ckpt = args.ckpt or os.path.join(
        DATASET_DIR, 'eval', 'review',
        f'.mine_ckpt_{args.field_token}_{len(pool)}.jsonl')
    os.makedirs(os.path.dirname(ckpt), exist_ok=True)
    meta = {'pool_size': len(pool), 'field_token': args.field_token,
            'model': os.path.basename(model_dir.rstrip('/\\')), 'n_batches': n_batches}
    probs_by_b = {}
    if os.path.exists(ckpt) and not args.no_resume:
        try:
            lines = open(ckpt, encoding='utf-8').read().splitlines()
            if lines and json.loads(lines[0]).get('meta') == meta:
                for ln in lines[1:]:
                    if ln.strip():
                        rec = json.loads(ln)
                        probs_by_b[rec['b']] = rec['probs']
                print(f'체크포인트 발견 → {len(probs_by_b)}/{n_batches} 배치 재사용, 이어서 채점',
                      flush=True)
            else:
                print('체크포인트 설정 불일치(풀/모델/토큰 변경) → 처음부터', flush=True)
                os.remove(ckpt)
        except (ValueError, OSError, KeyError, IndexError):
            print('체크포인트 손상 → 처음부터', flush=True)
            probs_by_b = {}
    if not probs_by_b:  # 새 시작이면 meta 헤더 기록
        with open(ckpt, 'w', encoding='utf-8') as cf:
            cf.write(json.dumps({'meta': meta}, ensure_ascii=False) + '\n')

    print(f'채점 시작: {len(texts)}문장 / {n_batches}배치(dev={dev}) · 이미완료 {len(probs_by_b)}',
          flush=True)
    remaining0 = n_batches - len(probs_by_b)
    scored, t0 = 0, time.time()
    with torch.no_grad(), open(ckpt, 'a', encoding='utf-8') as cf:
        for bi, i in enumerate(range(0, len(texts), BATCH)):
            if bi in probs_by_b:
                continue
            enc = tok(texts[i:i + BATCH], truncation=True, padding=True, max_length=64,
                      return_tensors='pt').to(dev)
            pr = F.softmax(model(**enc).logits, dim=-1).cpu().tolist()
            probs_by_b[bi] = pr
            cf.write(json.dumps({'b': bi, 'probs': pr}, ensure_ascii=False) + '\n')
            cf.flush()
            scored += 1
            total = len(probs_by_b)
            if scored == 1 or scored % 50 == 0 or total == n_batches:
                el = time.time() - t0
                rate = scored / el if el > 0 else 0
                eta = (remaining0 - scored) / rate / 60 if rate > 0 else 0
                print(f'  채점 {total}/{n_batches} ({100*total/n_batches:.0f}%) · '
                      f'{rate:.1f}배치/s · ETA {eta:.1f}분', flush=True)
    probs = [p for bi in range(n_batches) for p in probs_by_b[bi]]

    inc = {s.strip() for s in args.tiers.split(',') if s.strip()}
    bad = inc - {'flip_pn', 'low_margin', 'neu_boundary'}
    if bad:
        print(f'알 수 없는 tier: {bad}. 허용=flip_pn,low_margin,neu_boundary', flush=True)
        return
    print(f'포함 tier={sorted(inc)} · 혼합={args.mix}', flush=True)

    cands = []
    for (t, field, pool_lab), pr in zip(pool, probs):
        p_pos, p_neg, p_neu = pr[0], pr[1], pr[2]
        pred = int(max(range(3), key=lambda c: pr[c]))
        conf = float(pr[pred])
        margin_pn = abs(p_pos - p_neg)
        model_polar = pred in (0, 1)
        pool_polar = pool_lab in (0, 1)

        # 포함 tier만 진입 — 제외된 tier의 표본은 다음 tier 조건으로 흘러내려 재분류된다
        # (예: flip_pn 제외 시, 긍↔부 불일치이면서 마진 작은 표본은 low_margin으로 잡힘).
        if 'flip_pn' in inc and model_polar and pool_polar and pred != pool_lab:
            tier, hard, sort = 0, 'flip_pn', -conf          # 고확신 불일치 우선
        elif 'low_margin' in inc and margin_pn < args.margin:
            tier, hard, sort = 1, 'low_margin', margin_pn    # 마진 작을수록 우선
        elif 'neu_boundary' in inc and ((pred == 2 and pool_polar)
                                        or (model_polar and pool_lab == 2 and conf < 0.6)):
            tier, hard, sort = 2, 'neu_boundary', -abs(p_neu - max(p_pos, p_neg))
        else:
            continue                                          # 쉬운 일치·고확신·제외 tier는 스킵

        cands.append({
            'text': t, 'field': field, 'tier': tier, 'hard': hard, 'sort': sort,
            'pool_label': ID2LAB[pool_lab], 'model_pred': ID2LAB[pred], 'model_conf': round(conf, 3),
            'probs': {'pos': round(p_pos, 3), 'neg': round(p_neg, 3), 'neu': round(p_neu, 3)},
        })

    if args.mix:
        # tier별 정렬 후 라운드로빈으로 n개 — 한 tier가 큐를 독식하지 못하게(1차 flip_pn 100% 교훈)
        by_tier = {}
        for c in cands:
            by_tier.setdefault(c['tier'], []).append(c)
        for lst in by_tier.values():
            lst.sort(key=lambda c: c['sort'])
        picked, ti = [], sorted(by_tier)
        cursor = {tier: 0 for tier in ti}
        while len(picked) < args.n and ti:
            for tier in list(ti):
                if cursor[tier] < len(by_tier[tier]):
                    picked.append(by_tier[tier][cursor[tier]])
                    cursor[tier] += 1
                    if len(picked) >= args.n:
                        break
                else:
                    ti.remove(tier)
    else:
        cands.sort(key=lambda c: (c['tier'], c['sort']))
        picked = cands[:args.n]

    from collections import Counter
    dist = Counter(c['hard'] for c in picked)
    n_field = sum(1 for c in picked if c['field'])
    print(f'하드 후보 {len(cands)}건 중 상위 {len(picked)}건 선정 · 유형 {dict(dist)} · '
          f'필드보유 {n_field}/{len(picked)}')

    out = args.out or os.path.join(
        DATASET_DIR, 'eval', 'review',
        f'hard_queue_{datetime.date.today().strftime("%y%m%d")}.jsonl')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        for i, c in enumerate(picked):
            f.write(json.dumps({
                'rec_id': f'hard_{i}',
                'text': c['text'],
                'field': c['field'],
                'cur_rule_label': c['pool_label'],           # 게시판 '현규칙'(풀 라벨=약/실버)
                'group': c['hard'],
                'ai_reference': {                            # 게시판 '알고리즘'(모델 예측)
                    'polarity': c['model_pred'], 'confidence': c['model_conf'],
                    'reason': f"모델={c['model_pred']}({c['model_conf']}) vs 풀={c['pool_label']} · "
                              f"p{c['probs']} · {c['hard']}",
                },
                'claude_judgment': '',                       # 다음 단계: claude prefill
                'human_decision': None,                      # 그다음: 불확실만 사용자
                'status': 1,                                 # 1=AI판정대기
                'source_file': 'mine_hard_samples',
                'note': f'hard_queue_{datetime.date.today().strftime("%y%m%d")}',
            }, ensure_ascii=False) + '\n')
    print(f'큐 저장 → {os.path.relpath(out, PROJECT_ROOT)} ({len(picked)}행)')
    try:  # 정상 완료 시 체크포인트 정리
        os.remove(ckpt)
    except OSError:
        pass


if __name__ == '__main__':
    main()
