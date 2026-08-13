# -*- coding: utf-8 -*-
"""능동학습 6라운드 큐 — **개선요청·완곡부정 화행**(광맥 교체).

배경(c5 실패 진단, IMPROVEMENT_HISTORY 5차 §④): bare NP 광맥은 c4에서 극성이 고갈됐다
(c5 재채굴 → 극성 192→135·중립 38→95 폭증, 중립 95 중 요청표지 1건뿐 = 진짜 중립).
c3_neu149의 미검출 부정 48건을 실측 분류하니 **개선요청 화행 22(46%)+완곡부정 서술 20(42%)**로
지배적이고 bare NP는 6(12%)뿐. 즉 남은 부정 헤드룸은 **서술어를 가진 화행 문장**에 있고,
bare NP 마이너는 극성을 나르는 서술어(필요/보완/자제)를 버려 이 광맥에 구조적으로 못 닿았다.

노선: 단점 field의 요청/완곡부정 화행 → **부정**. c4 안전원리(양필드 페어) 그대로 —
장점 field의 **같은 공유토큰**(보완/고집/과도/신경/챙기/치우) 완결서술 → **긍정** 카운터웨이트로
동반 투입해 토큰→부정 누수(긍↔부)를 차단. 라벨은 per-row 사람확정 gold(미확정 대량 silver 금지).

함정 가드(사전라벨 불신·직접검증에서 발견): "특별한 보완점 없음/필요없습니다" 부류는
요청표지(보완/필요)가 있으나 **부정을 부정 → 중립/긍정**. 부정 버킷에서 배제하고 중립후보로 라우팅.

버킷:
  A_단점_요청부정  : 단점 + 요청/완곡부정 표지 - 함정 = 목표 부정
  B_장점_공유토큰긍정: 장점 + 공유토큰 완결서술 = 목표 긍정(카운터웨이트)
  C_중립후보       : 함정(없음-부정)·무종결 단편·양가/변호 = 목표 중립(소량)

누수 가드: 전 학습셋(+c5) + 전 테스트셋 텍스트 제외. 모델 추론으로 flip-risk(교차확인) 부기.
산출: eval/review/speechact_r6_260707.jsonl (게시판 스키마, human_decision=null → per-row 판정 대기).
※ ai_reference.polarity=모델예측은 힌트일 뿐 정답 아님 — 최종 라벨은 사람(=위임된 claude) 판정.
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

LEAK_FILES = (
    'gold_8c_train_260706.jsonl', 'gold_active_260707.jsonl',
    'gold_active_260707_c2.jsonl', 'silver_active_260707_c2.jsonl',
    'gold_active_260707_c4.jsonl', 'silver_active_260707_c4.jsonl',
    'gold_active_260707_c5.jsonl', 'silver_active_260707_c5.jsonl',  # c5 회수분도 재출제 방지
    'group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
    'field_conflict_review_260624.jsonl', 'hard_failure_review_260630.jsonl',
    'baseline_eval_260624.jsonl', 'gold_8c_test_260706.jsonl',
    'gold_8c_test_c3neu_260707.jsonl',
)

# 요청/완곡부정 화행 표지(단점 field에서 부정 신호)
REQ_DIRECT = ('보완', '필요', '해주', '주세요', '주셨으면', '좋겠', '했으면', '하셨으면',
              '되었으면', '바랍', '바람', '부탁', '자제', '줄이', '줄였', '당부', '개선',
              '키워', '신경써', '챙기', '요망', '권장', '지양', '모르겠')
REQ_SOFT = ('아쉽', '부족', '과도', '지나치', '미흡', '고집', '편중', '치우', '미루')
# 공유토큰(단점↔장점 극성반전) — 장점 카운터웨이트 후보 선별용
SHARED = ('보완', '고집', '과도', '자제', '챙기', '치우', '신경', '줄이', '미루',
          '부탁', '지양', '기대')
# 함정: 요청표지가 '없음'과 결합해 부정을 부정 → 중립/긍정
NEG_OF_NEG = ('없음', '없습니다', '없다', '없어', '없슴', '엇ㅂ음', '없슨', '알지못', '발견')


def norm(t):
    return _WS.sub(' ', (t or '').strip()).lower().strip(' .。!?！？·…-')


def is_trap(t):
    """요청표지 + 없음-부정 결합 = 함정(부정 아님)."""
    has_req = any(m in t for m in ('보완', '필요', '보와', '보완필', '보완피'))
    return has_req and any(z in t for z in NEG_OF_NEG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=os.path.join(DATASET_DIR, 'model_out'))  # c5rollback 산출
    ap.add_argument('--min-len', type=int, default=6)
    ap.add_argument('--max-len', type=int, default=80)
    args = ap.parse_args()

    exclude = set()
    for fn in LEAK_FILES:
        p = os.path.join(EVAL, fn)
        if os.path.exists(p):
            for l in open(p, encoding='utf-8'):
                if l.strip():
                    exclude.add(norm(json.loads(l).get('text')))
    print(f'누수/중복 제외셋 {len(exclude)} (파일 {len(LEAK_FILES)})')

    seen = set()
    A, B, C = [], [], []   # 단점부정 / 장점긍정 / 중립후보
    for f in sorted(glob.glob(os.path.join(REVIEW, '*8c_*.jsonl'))):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            t = (r.get('text') or '').strip()
            fld = (r.get('field') or '').strip()
            n = norm(t)
            if not t or n in exclude or n in seen:
                continue
            if not (args.min_len <= len(t) <= args.max_len):
                continue
            item = {'rec_id': r.get('rec_id'), 'text': t, 'field': fld,
                    'cur_rule_label': r.get('cur_rule_label'), 'group': r.get('group'),
                    'source_file': os.path.basename(f)}
            is_danj = '단' in fld
            has_req = any(m in t for m in REQ_DIRECT) or any(m in t for m in REQ_SOFT)
            has_shared = any(m in t for m in SHARED)
            if is_danj and has_req:
                seen.add(n)
                if is_trap(t):
                    item['bucket'] = 'C_중립후보_함정없음'
                    C.append(item)
                else:
                    item['bucket'] = 'A_단점_요청부정'
                    A.append(item)
            elif (not is_danj) and fld and has_shared:
                seen.add(n)
                item['bucket'] = 'B_장점_공유토큰긍정'
                B.append(item)
    print(f'A 단점요청부정 {len(A)} · B 장점공유긍정 {len(B)} · C 중립후보(함정) {len(C)}')

    queue = A + B + C
    # 모델 교차확인(힌트) — 추론만
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        tok = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(args.model, local_files_only=True)
        model.eval()
        texts = [r['text'] for r in queue]
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt')
                probs = torch.softmax(model(**enc).logits, -1)
                conf, pred = probs.max(-1)
                for j in range(len(conf)):
                    q = queue[i + j]
                    q['pred'] = ID2LAB[int(pred[j])]
                    q['conf'] = round(float(conf[j]), 4)
    except Exception as e:
        print(f'[warn] 모델 추론 생략({e}) — 힌트 없이 큐만 출력')
        for q in queue:
            q['pred'], q['conf'] = None, None

    out = os.path.join(REVIEW, 'speechact_r6_260707.jsonl')
    with open(out, 'w', encoding='utf-8') as w:
        for r in queue:
            w.write(json.dumps({
                'rec_id': r['rec_id'], 'text': r['text'], 'field': r.get('field'),
                'cur_rule_label': r.get('cur_rule_label'), 'group': r.get('group'),
                'human_decision': None, 'suggested_source': None, 'decision_source': None,
                'ai_reference': {'polarity': r.get('pred'), 'confidence': r.get('conf'),
                                 'reason': f"[{r['bucket']}] 모델={r.get('pred')} conf={r.get('conf')}"},
                'source_file': r.get('source_file'), 'note': 'speechact_r6',
            }, ensure_ascii=False) + '\n')
    print(f'→ {os.path.relpath(out, DATASET_DIR)}  (총 {len(queue)})')


if __name__ == '__main__':
    main()
