# -*- coding: utf-8 -*-
"""0630_04 전수 양방향 재생 — 결핍명사 부정화의 긍↔부 0 검증 (배포 제외).

old = git HEAD(0630_03까지) perspective_service / new = 작업트리.
weak_export_260624.jsonl 870,367행에 두 override를 적용, sentiment 라벨(score>0 pos / <0 neg / ==0 neu)을
비교해 긍↔부 신규 교차·필드별 전이를 카운트. 모델/서버 불요(저장 weak_kote 재사용).
프로덕션 매핑 동일: neutral=kote_neutral, is_last/total=행값 (refine_acquired_row L3076 참조).
"""
import os, sys, json, subprocess, importlib.util, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, ROOT)
REL = 'src/services/perspective_service.py'
WEAK = os.path.join(ROOT, 'plans', '_datasets', 'kote_finetune', 'emotion', 'weak_export_260624.jsonl')


def _load_module(src_text, name):
    """소스 문자열을 임시 .py로 써서 독립 모듈로 로드(old/new 동시 보유)."""
    tmp = os.path.join(tempfile.gettempdir(), f'{name}.py')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(src_text)
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _label(explain, pos, neg, text, is_last, total, neu):
    score, rule = explain(pos, neg, text, is_last, total, neutral=neu)
    return ('pos' if score > 0 else 'neg' if score < 0 else 'neu'), rule


def main():
    old_src = subprocess.check_output(['git', 'show', f'HEAD:./{REL}'], cwd=ROOT).decode('utf-8')
    with open(os.path.join(ROOT, REL), 'r', encoding='utf-8') as f:
        new_src = f.read()
    old = _load_module(old_src, 'ps_old_0630_04')
    new = _load_module(new_src, 'ps_new_0630_04')
    oexp = old._sentence_sentiment_override_explain
    nexp = new._sentence_sentiment_override_explain

    n = 0
    pos_to_neg = neg_to_pos = 0            # 🔴 긍↔부 신규 교차(양방향)
    cons_pos_to_neg = cons_pos_to_neu = 0  # 단점필드 부→긍 차단(긍→부/긍→중 전이)
    cons_neu_to_neg = 0
    pros_pos_to_neg = pros_pos_to_neu = 0  # 장점필드 부작용(긍→부=위반 / 긍→중=연성)
    examples = {'pos_to_neg': [], 'neg_to_pos': [], 'pros_pos_to_neg': [], 'cons_pos_to_neg': []}
    rule_fire = 0

    with open(WEAK, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            wk = d.get('weak_kote') or {}
            pos = wk.get('pos', 0.0); neg = wk.get('neg', 0.0); neu = wk.get('neu', 0.0)
            text = d.get('text', '') or ''
            is_last = bool(d.get('is_last', True))
            total = int(d.get('total_sentences', 1) or 1)
            ol, _ = _label(oexp, pos, neg, text, is_last, total, neu)
            nl, nr = _label(nexp, pos, neg, text, is_last, total, neu)
            n += 1
            if nr == 'deficiency_noun_negative':
                rule_fire += 1
            if ol == nl:
                continue
            is_cons = '_0-' in d.get('id', '')   # batch_20260624_0 = 단점
            is_pros = '_1-' in d.get('id', '')   # batch_20260624_1 = 장점
            if ol == 'pos' and nl == 'neg':
                pos_to_neg += 1
                if len(examples['pos_to_neg']) < 15:
                    examples['pos_to_neg'].append((d.get('id'), text[:60]))
                if is_pros:
                    pros_pos_to_neg += 1
                    if len(examples['pros_pos_to_neg']) < 80:
                        examples['pros_pos_to_neg'].append((d.get('id'), text[:70]))
                if is_cons:
                    cons_pos_to_neg += 1
                    if len(examples['cons_pos_to_neg']) < 40:
                        examples['cons_pos_to_neg'].append((d.get('id'), text[:70]))
            elif ol == 'neg' and nl == 'pos':
                neg_to_pos += 1
                if len(examples['neg_to_pos']) < 15:
                    examples['neg_to_pos'].append((d.get('id'), text[:60]))
            elif ol == 'pos' and nl == 'neu':
                if is_cons:
                    cons_pos_to_neu += 1
                if is_pros:
                    pros_pos_to_neu += 1
            elif ol == 'neu' and nl == 'neg':
                if is_cons:
                    cons_neu_to_neg += 1

    print(f'총 행수: {n:,}')
    print(f'deficiency_noun_negative 발동: {rule_fire:,}')
    print('--- 🔴 긍↔부 신규 교차(양방향) ---')
    print(f'  pos→neg: {pos_to_neg:,}   (그중 장점필드: {pros_pos_to_neg:,})')
    print(f'  neg→pos: {neg_to_pos:,}')
    print('--- 단점필드 전이(부→긍 차단 효과) ---')
    print(f'  단점 pos→neg: {cons_pos_to_neg:,}   (부→긍 위반 부정화)')
    print(f'  단점 pos→neu: {cons_pos_to_neu:,}   (부→긍 위반 중립화)')
    print(f'  단점 neu→neg: {cons_neu_to_neg:,}')
    print('--- 장점필드 부작용 ---')
    print(f'  장점 pos→neg: {pros_pos_to_neg:,}   (🔴 긍→부=위반)')
    print(f'  장점 pos→neu: {pros_pos_to_neu:,}   (긍→중=연성)')
    for k, v in examples.items():
        if v:
            print(f'\n[예시 {k}]')
            for _id, t in v:
                print(f'  {_id}: {t}')


if __name__ == '__main__':
    main()
