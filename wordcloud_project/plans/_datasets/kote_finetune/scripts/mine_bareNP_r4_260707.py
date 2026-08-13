# -*- coding: utf-8 -*-
"""능동학습 4라운드 큐 — 서술어 없는 역량명사구(bare NP)를 **양 필드 균형**으로 수집.

목적: c3_neu149에서 노출된 헤드룸(부recall 0.5·긍↔부 4, 전부 부→긍)의 원인 =
      모델이 중립/긍정으로 확신하는 bare-단점 역량명사구. 이를 학습으로 메우되
      **반드시 단점(→부정)·장점(→긍정)을 균형 수집**해야 필드 토큰이 폴리세미(극성=필드)를
      배운다. 단방향(단점만) 투입은 "bare NP=부정"을 내용신호로 오학습 → 긍↔부 누수.

필터:
  - bare NP 휴리스틱: 종결서술어 없이 명사로 끝나는 단편(다/음/함/됨/임/기/요/… 종결 제외).
    → '없음'·'모르겠음'(음 종결=서술어 有)은 자동 제외되어 중립 유지와 일치.
  - field 有(단점/장점)만. model_out_8c 추론으로 flip-risk 우선순위.

버킷:
  - 단점 bare NP (목표 부정): 모델이 부정이 아닌 것(neutral/positive) 우선 = 가르칠 지점.
  - 장점 bare NP (목표 긍정): 모델이 긍정이 아닌 것(neutral/negative) 우선.
  - 두 버킷 **동수(min)**로 잘라 균형 보장.

누수 가드: 전 학습셋(gold_8c_train·gold_active·c2·silver_c2·group/field/hard 리뷰)
           + 전 테스트셋(baseline·gold_8c_test·c3_neu149) 텍스트(정규화 동일) 제외.
산출: eval/review/bareNP_r4_260707.jsonl (게시판 스키마, human_decision=null, ai_reference=모델힌트).
"""
import argparse
import glob
# 260806 검토큐 재편으로 파일명에 우선순위 접두어(P1_/P2_/P3_)가 붙었다.
# glob 은 실패해도 빈 목록을 돌려 **조용히 0건**이 되므로 접두 허용 패턴으로 고친다.
import json
import os
import re

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
EVAL = os.path.join(DATASET_DIR, 'eval')
REVIEW = os.path.join(EVAL, 'review')
ID2LAB = {0: 'positive', 1: 'negative', 2: 'neutral'}
_WS = re.compile(r'\s+')

# 전 학습셋 + 전 테스트셋(finetune_sentiment.TRAIN_FILES/TEST_SETS와 일치) — 누수/중복 제외
LEAK_FILES = (
    'gold_8c_train_260706.jsonl', 'gold_active_260707.jsonl',
    'gold_active_260707_c2.jsonl', 'silver_active_260707_c2.jsonl',
    'group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
    'field_conflict_review_260624.jsonl', 'hard_failure_review_260630.jsonl',
    'baseline_eval_260624.jsonl', 'gold_8c_test_260706.jsonl',
    'gold_8c_test_c3neu_260707.jsonl',
)

# 종결어미 표지(이 중 하나로 끝나면 서술어 有 → bare NP 아님)
PRED_END = ('다', '기', '요', '죠', '네', '까', '나', '겠', '었', '았', '였', '해', '야',
            '듯', '셈', '것', '줄', '지', '데', '고', '서', '며', '만', '흡', '제')
BARE_MAX_LEN = 35   # 이보다 길면 절/문장(서술어 포함) — bare NP 아님


def norm(t):
    return _WS.sub(' ', (t or '').strip()).lower().strip(' .。!?！？·…-')


def _jongseong_m(ch):
    """마지막 음절 종성이 ㅁ이면 True — 한국어 명사화 어미 음/ㅁ(함·됨·씀·남·뛰어남…)의 신호."""
    if not ('가' <= ch <= '힣'):
        return False
    return (ord(ch) - 0xAC00) % 28 == 16   # 종성 인덱스 16 == ㅁ


def is_bare_np(t):
    """종결서술어 없이 명사로 끝나는 단편이면 True (휴리스틱, per-row 판정으로 최종 확정).

    제외: ①종성 ㅁ(음/ㅁ 명사화 서술어: 함·됨·씀·남·뛰어남) ②PRED_END 종결어미
          ③길이>35(절·문장) ④비한글 종결. 잔여 오차는 per-row 재판정이 최종 게이트.
    """
    s = (t or '').strip().rstrip(' .。!?！？·…-')
    if not (3 <= len(s) <= BARE_MAX_LEN):
        return False
    if _jongseong_m(s[-1]) or s.endswith(PRED_END):
        return False
    return bool(re.match(r'[가-힣]$', s[-1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=os.path.join(DATASET_DIR, 'model_out_8c'))
    ap.add_argument('--cap-each', type=int, default=120)  # 필드별 상한(동수로 잘림)
    args = ap.parse_args()

    exclude = set()
    for fn in LEAK_FILES:
        p = os.path.join(EVAL, fn)
        if os.path.exists(p):
            for l in open(p, encoding='utf-8'):
                if l.strip():
                    exclude.add(norm(json.loads(l).get('text')))
    print(f'누수/중복 제외셋 {len(exclude)} (파일 {len(LEAK_FILES)})')

    rows = []
    seen = set()
    for f in sorted(glob.glob(os.path.join(REVIEW, '*8c_auto__*.jsonl'))
                    + glob.glob(os.path.join(REVIEW, '*8c_other_neu__*.jsonl'))):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            # 주: 이 파일들의 human_decision은 사람 확정이 아니라 claude 프리필 다수(신뢰 불가)
            #     → gold-skip 하지 않고 누수는 LEAK_FILES 텍스트 매칭에만 의존, per-row 재판정.
            t = (r.get('text') or '').strip()
            field = r.get('field') or ''
            n = norm(t)
            if not t or n in exclude or n in seen:
                continue
            if ('단점' not in field) and ('장점' not in field):
                continue
            if not is_bare_np(t):
                continue
            seen.add(n)
            rows.append({'rec_id': r.get('rec_id'), 'text': t, 'field': field,
                         'cur_rule_label': r.get('cur_rule_label'), 'group': r.get('group'),
                         'source_file': os.path.basename(f)})
    print(f'bare NP·field有·누수제외 후보 {len(rows)}')

    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    tok = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, local_files_only=True)
    model.eval()
    texts = [r['text'] for r in rows]
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                      return_tensors='pt')
            probs = torch.softmax(model(**enc).logits, -1)
            conf, pred = probs.max(-1)
            for j in range(len(conf)):
                r = rows[i + j]
                r['pred'] = ID2LAB[int(pred[j])]
                r['conf'] = round(float(conf[j]), 4)

    # 필드별 버킷 — 목표극성과 다른 예측(가르칠 지점) 우선, 확신 높은 순
    danj = [r for r in rows if '단점' in r['field']]   # 목표 부정
    jang = [r for r in rows if '장점' in r['field']]   # 목표 긍정
    danj.sort(key=lambda r: (r['pred'] == 'negative', -r['conf']))   # 부정 아닌 것 먼저
    jang.sort(key=lambda r: (r['pred'] == 'positive', -r['conf']))   # 긍정 아닌 것 먼저
    k = min(args.cap_each, len(danj), len(jang))       # 동수 균형
    for r in danj[:k]:
        r['bucket'] = 'D_bareNP_단점_목표부정'
    for r in jang[:k]:
        r['bucket'] = 'J_bareNP_장점_목표긍정'
    queue = danj[:k] + jang[:k]
    print(f'단점 bare NP {k} · 장점 bare NP {k} · 합 {len(queue)} '
          f'(원천 단점 {len(danj)}·장점 {len(jang)} → 동수 균형)')

    out = os.path.join(REVIEW, 'bareNP_r4_260707.jsonl')
    with open(out, 'w', encoding='utf-8') as w:
        for r in queue:
            w.write(json.dumps({
                'rec_id': r['rec_id'], 'text': r['text'], 'field': r.get('field'),
                'cur_rule_label': r.get('cur_rule_label'), 'group': r.get('group'),
                'human_decision': None, 'suggested_source': None, 'decision_source': None,
                'ai_reference': {'polarity': r['pred'], 'confidence': r['conf'],
                                 'reason': f"[{r['bucket']}] 모델={r['pred']} conf={r['conf']}"},
                'source_file': r.get('source_file'), 'note': 'bareNP_r4',
            }, ensure_ascii=False) + '\n')
    print(f'→ {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
