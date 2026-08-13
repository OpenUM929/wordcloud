# -*- coding: utf-8 -*-
"""게시판 큐에 확립규칙 적용 → 규칙이 정하는 건 자동해소(silver), 진짜 잔여만 사용자에게.

사용자 지적(260715): "규칙으로 만든 부분(혼합→중립·필드의존·건강 등)을 안 지키고 나한테 묻는다."
  → 지침 feedback_escalate_only_rule_residual 위반. 큐 생성 시 규칙을 먼저 안 태운 탓.
해결: 각 행을 생산 규칙엔진(_sentence_sentiment_override_explain, 0715 혼합규칙 반영)에 태워
  **정책 규칙**이 발동하면 그 값으로 자동해소(auto_resolved=silver, 사용자 큐에서 제외).
  정책 규칙 없이 KoTE 우세/기본만이면(neutral_dominant·rule4_default·garbage) 진짜 잔여 → 사용자.

정책 규칙(확립·문서화): improvement_request_neutral(혼합·요청혼재)·improvement_request_neg(개선요청)·
  health_advice_neutral·personal_wellbeing_neutral·no_weakness_neutral/positive·no_response_neutral·
  positive_rescue·negation_praise·excess_complaint_neg.
⚠ KoTE 점수 미보유 큐라 pos=neg=중립 stub으로 태움 → **어휘 정책 규칙만** 발동(KoTE 의존
  positive_rescue(neg<0.85)·neutral_dominant는 보수적으로 잔여 취급). 필드는 그대로 유지.
필드의존(장점/단점로 극성 갈림)은 규칙이 못 정하므로 잔여로 남긴다(모델·사람 판정 영역).

입력: review/<큐>.jsonl → 출력: 동파일 갱신(잔여만 human_decision=null 유지) +
  <큐>.silver_260715.jsonl(자동해소분 별도 보존). 사용자 판정(human_decision) 있으면 보존.
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter

# ── 무서술어 단독 명사구(bare NP) 감지 — 사용자 규칙: 서술어 없으면 필드극성(장점=긍/단점=부) ──
#   mine_bareNP_r5_260707.py의 검증된 휴리스틱 이식. 서빙 override 폐기(이중계산)와 별개로
#   라벨링/gold 생성에는 유효한 정답규칙(c4 양필드페어 gold가 이 규칙으로 적립됨).
_PRED_END = ('다', '기', '요', '죠', '네', '까', '나', '겠', '었', '았', '였', '해', '야',
             '듯', '셈', '것', '줄', '지', '데', '고', '서', '며', '만', '흡', '제')
_BARE_MAX = 35


def _jongseong_m(ch):
    return '가' <= ch <= '힣' and (ord(ch) - 0xAC00) % 28 == 16   # 종성 ㅁ(함/됨/남=명사화)


def is_bare_np(t):
    """종결서술어 없이 명사로 끝나는 단편이면 True(무서술어)."""
    # 끝에 홀로 남은 자모(오타 'ㅇ'·'ㄴ' 등)는 떼고 판정 — "협업능력ㅇ" → "협업능력".
    s = (t or '').strip().rstrip(' .。!?！？·…-')
    s = re.sub(r'[ㄱ-ㅎㅏ-ㅣ]+$', '', s).strip()
    if not (3 <= len(s) <= _BARE_MAX):
        return False
    if _jongseong_m(s[-1]) or s.endswith(_PRED_END):
        return False
    return bool(re.match(r'[가-힣]$', s[-1]))

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
REVIEW = os.path.join(DS, 'eval', 'review')
sys.path.insert(0, WP)

# 자동해소(silver) 대상 = **중립/긍정 방향의 안전·검증된 정책 규칙만**.
#   ⚠ negative 방향(improvement_request_neg·excess)은 KoTE stub에서 과발동한다(실측 260715:
#     "집이 멀어 피곤…갔으면 좋겠음"=개인안녕중립인데 부정 오해·"어케 아나요"=무응답인데 부정).
#     → negative는 자동해소 금지, 잔여로 돌려 프리필=부정으로 사용자 확인(오발동 사용자가 잡음).
#   중립/긍정은 방향상 긍↔부 무관 + 회귀테스트 통과 규칙이라 자동해소 안전.
POLICY_RULES = {
    'improvement_request_neutral': 'neutral',   # 혼합(뛰어나나 개선필요) — 0715
    'mixed_pos_neg_neutral': 'neutral',         # 광의 혼합(뛰어나나 관심없음) — 0715 감사
    'cannot_assess_neutral': 'neutral',         # 상호작용/관찰 부재 평가불가 — 0715 감사
    'meta_comment_neutral': 'neutral',          # 비평가 메타(제도/설문/근무일정) — 0715 감사
    'health_advice_neutral': 'neutral',
    'personal_wellbeing_neutral': 'neutral',
    'no_weakness_neutral': 'neutral',
    'no_weakness_positive': 'positive',
    'no_response_neutral': 'neutral',
    'negation_praise': 'positive',
    'garbage_line_neutral': 'neutral',
}
# negative 방향 규칙: 자동해소 않고 잔여로(프리필만 부정, 사용자 확인).
NEG_RULES = {'improvement_request_neg': 'negative', 'excess_complaint_neg': 'negative'}


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('queue', help='review/ 내 파일명')
    a = ap.parse_args()
    from src.services.perspective_service import _sentence_sentiment_override_explain as ov

    path = os.path.join(REVIEW, a.queue)
    silver_path = path.replace('.jsonl', '.silver_260715.jsonl')
    rows = loadl(path)

    residual, silver, stat = [], [], Counter()
    for r in rows:
        # 사용자가 이미 판정한 행은 절대 건드리지 않음
        if r.get('human_decision') is not None:
            residual.append(r)
            stat['user_kept'] += 1
            continue
        text = (r.get('text') or '').strip()
        # KoTE 미보유 → 중립 stub. 어휘 정책 규칙만 발동(보수적).
        _s, rid = ov(0.4, 0.4, text, True, 1, neutral=0.2)
        field = (r.get('field') or '').strip()
        if rid in POLICY_RULES:
            lab = POLICY_RULES[rid]
            r['claude_judgment'] = {'polarity': lab, 'reason': f'규칙확정({rid})'}
            r['rule_resolved'] = rid
            r['suggested'] = lab
            silver.append(r)
            stat[f'silver_{lab}'] += 1
            stat['auto_resolved'] += 1
        elif is_bare_np(text) and field in ('장점', '단점'):
            # 무서술어 명사구 → 필드극성(사용자 규칙). 장점=긍정·단점=부정. 자동해소.
            lab = 'positive' if field == '장점' else 'negative'
            r['claude_judgment'] = {'polarity': lab, 'reason': f'무서술어 명사구→{field}극성(규칙)'}
            r['rule_resolved'] = f'bare_np_{field}'
            r['suggested'] = lab
            silver.append(r)
            stat[f'silver_barenp_{lab}'] += 1
            stat['auto_resolved'] += 1
        else:
            # 잔여: 프리필을 현재 규칙 결과로 갱신(옛 cur_rule_label 잔재 제거). 사용자 확인용.
            cur_pol = 'positive' if _s > 1e-6 else ('negative' if _s < -1e-6 else 'neutral')
            r['claude_judgment'] = {'polarity': cur_pol, 'reason': f'규칙={rid}·확인요'}
            r['suggested'] = cur_pol
            r['_rule_stub'] = rid   # 왜 잔여인지 흔적(neutral_dominant/rule4/improvement_neg 등)
            residual.append(r)
            stat['residual'] += 1
            stat[f'residual_{cur_pol}'] += 1

    with io.open(path, 'w', encoding='utf-8') as f:
        for r in residual:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with io.open(silver_path, 'w', encoding='utf-8') as f:
        for r in silver:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    pend = sum(1 for r in residual if r.get('human_decision') is None)
    print(f'[{a.queue}] 총 {len(rows)} → 잔여(사용자큐) {len(residual)} (미판정 {pend}) · 자동해소 {len(silver)}')
    print(f'  자동해소 내역: {dict((k, v) for k, v in stat.items() if k.startswith("silver_"))}')
    print(f'  자동해소분 보존 → review/{os.path.basename(silver_path)}')
    print(f'  게시판: {a.queue} ({sum(1 for r in residual if r.get("human_decision") is not None)}/{len(residual)})')


if __name__ == '__main__':
    main()
