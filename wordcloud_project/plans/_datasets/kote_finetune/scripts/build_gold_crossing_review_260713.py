# -*- coding: utf-8 -*-
"""긍↔부 gold 교차 정정 후보 → 그룹검토 게시판용 검토 파일 생성.

배경: L1 라벨감사(label_audit_prefill_260708)에서 gold를 긍↔부로 뒤집자는 제안 12건(고유 11건).
긍↔부 플립은 핵심가치(긍↔부 0)를 직접 건드리는 편집이라 확립된 정정정책(중립방향만)의 예외 —
**반드시 사람 확정**을 거쳐야 한다. 그래서 자동적용 대신 그룹검토 게시판에서 사용자가 판정하도록
게시판 계약(eval/review/*.jsonl: text·field·cur_rule_label·ai_reference·claude_judgment·human_decision)
에 맞춰 검토 파일을 만든다.

각 행에 (1) 내 의견(claude_judgment + ai_reference) (2) 현재 gold(cur_rule_label) (3) 권위 스트림값
(4) **왜 사용자 판단이 필요한지**(group 태그 + reason)를 넣는다. 사용자가 결정(human_decision)을
채우면, 그 확정분만 gold 파일에 append-only 리비전으로 반영한다(별도 apply 단계).

출력: eval/review/gold_crossing_review_260713.jsonl (게시판이 자동 목록화)
"""
import json
import os
import io

HERE = os.path.dirname(__file__)
DS = os.path.abspath(os.path.join(HERE, '..'))
AUDIT = os.path.join(DS, 'eval', 'review', 'label_audit_prefill_260708.jsonl')
STREAM = os.path.join(DS, 'emotion', 'emotion.jsonl')
OUT = os.path.join(DS, 'eval', 'review', 'gold_crossing_review_260713.jsonl')

# rec_id별 내 판단(의견)·확신·판단필요 사유 카테고리. proposal을 맹종하지 않고 문장 재판정한 결과.
#   cat A=명백 gold 오류(제안 동의) · B=사람 중립판정과 충돌(재정 필요) · C=양가·경계(확신 medium)
MY = {
    'batch_20260624_1-137694': dict(  # 관리감독없이업무수행 (장점)
        label='positive', conf='medium', cat='C 양가·경계',
        why='장점란의 "관리감독 없이 업무수행"은 자율성(긍정)으로 읽히나 서술이 짧아 해석 여지가 있고, '
            '권위 스트림은 중립으로 본다. 긍↔부 방향 변경이라 사용자 확정 필요.',
        op='장점 맥락 자율수행 → 긍정 추천(확신 보통).'),
    'batch_20260624_0-377567': dict(  # 노하우 공유 필요 (단점)
        label='negative', conf='high', cat='A 명백오류(제안 동의)',
        why='개선요청 화행("공유 필요")은 부정. 권위 스트림도 부정으로 일치. 다만 긍↔부 gold 변경이라 '
            '정책상(중립방향 예외) 사용자 확정 필수.',
        op='개선요청=부정. 스트림 일치. 부정 추천.'),
    'batch_20260624_0-426407': dict(  # 의사소통 뛰어나나 개선필요 (단점)
        label='negative', conf='medium', cat='B 사람중립과 충돌(재정)',
        why='혼합문(칭찬+개선요청). 사람이 이미 **중립**으로 확정한 이력(emotion.jsonl rev2, human+ai_audit)이 '
            '있는데 제안은 부정. "개선필요=부정" 규칙과 "혼합=중립" 판정이 충돌 — 중립 유지 vs 부정 전환 재정 필요.',
        op='규칙상 개선요청=부정이나, 사람의 중립 확정과 충돌. 저는 약하게 부정 기울음(확신 낮음).'),
    'val-batch_20260624_0-154306': dict(  # 필요한 행동을 솔선하여 실행 (단점)
        label='positive', conf='high', cat='A 명백오류(제안 동의)',
        why="'필요' 어휘가 트리거한 렉시콘 트랩으로 파일·스트림 둘 다 부정 오분류. "
            '실제는 "필요한 행동을 솔선하여 실행"=명백 긍정 행위서술. 긍↔부 방향이라 사용자 확정 필요.',
        op="'필요' 트랩 오류. 명백 긍정. 긍정 추천."),
    'batch_20260624_1-94956': dict(  # 의사소통이 원화(원활)합니다 (장점)
        label='positive', conf='high', cat='A 명백오류(제안 동의)',
        why='"의사소통이 원활합니다"(원화=오타)는 명백 긍정인데 파일·스트림 모두 부정. '
            '오타가 부정 오분류를 유발한 것으로 보임. 긍↔부 방향이라 사용자 확정 필요.',
        op='명백 긍정(오타 원인 오분류). 긍정 추천.'),
    'val-batch_20260624_1-332958': dict(  # 타부서 입장에서 업무 수행 (장점)
        label='positive', conf='medium', cat='C 양가·경계',
        why='"타부서 입장에서 업무 수행"은 배려·협업(긍정)으로 읽히나 단정적 칭찬어가 없어 경계적. '
            '장점란 맥락 고려 시 긍정. 긍↔부 방향이라 사용자 확정 필요.',
        op='장점란 배려수행 → 긍정 추천(확신 보통).'),
    'batch_20260624_0-293159': dict(  # 빠른 문제해결...좋습니다 (단점)
        label='positive', conf='high', cat='A 명백오류(제안 동의)',
        why='명시적 칭찬어("좋습니다")가 있는데 단점란에 있다는 이유로 부정 오분류(필드 역전). '
            '내용이 명백 긍정이라 필드보다 문장이 우선. 긍↔부 방향이라 사용자 확정 필요.',
        op='명시 칭찬("좋습니다"). 긍정 추천.'),
    'batch_20260624_1-148381': dict(  # 업무 전문성 향상하기 위해 노력 (장점)
        label='positive', conf='high', cat='A 명백오류(제안 동의)',
        why='장점란 "전문성 향상 노력"은 긍정 행위서술인데 파일·스트림 부정. '
            "'향상/노력'을 개선요청으로 오독한 것으로 보임. 긍↔부 방향이라 사용자 확정 필요.",
        op='장점란 향상노력 → 긍정 추천.'),
    'val-batch_20260624_0-71779': dict(  # 본사의 의견에 의존함 (단점)
        label='negative', conf='high', cat='A 명백오류(제안 동의)',
        why='"본사 의견에 의존함"은 자립성 결핍 지적(부정)인데 파일·스트림 모두 긍정. '
            '명백한 gold 오류로 보임. 긍↔부 방향이라 사용자 확정 필요.',
        op='의존=결핍 지적 → 부정 추천.'),
    'val-batch_20260624_1-6960': dict(  # 조직 원하는 방향으로 행동 유발 (장점)
        label='positive', conf='medium', cat='C 양가·경계',
        why='"조직이 원하는 방향으로 주변 행동을 유발"은 영향력·리더십(긍정)으로 읽히나, '
            '"행동 유발"이 조종적으로도 해석될 여지가 있어 경계적. 긍↔부 방향이라 사용자 확정 필요.',
        op='리더십 영향력 → 긍정 추천(확신 보통, 조종적 해석 여지).'),
    'batch_20260624_0-372103': dict(  # 의견수렴해주세요 (단점)
        label='negative', conf='high', cat='B 사람중립과 충돌(재정)',
        why='요청표지("~해주세요")는 부정(개선요청) 규칙에 부합하나, 권위 스트림은 **중립**으로 본다. '
            '요청표지=부정 규칙 적용 vs 중립 유지 재정 필요.',
        op='요청표지(해주세요)=부정 추천이나, 스트림 중립과 충돌.'),
}


def stream_gold(em, text):
    hits = [g for g in em if g.get('text', '').strip() == text.strip()] \
        or [g for g in em if text.strip() in g.get('text', '')]
    if not hits:
        return None
    hits.sort(key=lambda g: g.get('rev') or 0, reverse=True)
    return hits[0].get('sentiment_gold')


def main():
    rows = [json.loads(l) for l in io.open(AUDIT, encoding='utf-8') if l.strip()]
    chg = [r for r in rows if r.get('proposal') == 'change']
    cross = [r for r in chg if {r.get('gold'), r.get('claude_judgment')} == {'positive', 'negative'}]
    em = [json.loads(l) for l in io.open(STREAM, encoding='utf-8') if l.strip()]

    seen, out = set(), []
    for r in cross:
        rid = r['rec_id']
        if rid in seen:
            continue
        seen.add(rid)
        my = MY.get(rid)
        if not my:
            raise SystemExit(f'의견 미정의 rec_id: {rid} — MY 딕셔너리에 추가 필요')
        sg = stream_gold(em, r['text'])
        reason = (f"[내 의견] {my['op']}  "
                  f"[현재 gold(파일)={r['gold']} · 권위스트림={sg} · 감사제안={r['claude_judgment']}]  "
                  f"[왜 사용자 판단 필요] {my['why']}")
        out.append({
            'rec_id': rid,
            'text': r['text'],
            'field': r.get('field') or '',
            'group': my['cat'],                          # 게시판 group 열 = 판단필요 사유 카테고리
            'cur_rule_label': r['gold'],                 # 게시판 '현규칙' = 현재 파일 gold
            'claude_judgment': my['label'],              # 내 추천 라벨
            'ai_reference': {                            # 게시판 '참고' = 내 의견+사유
                'polarity': my['label'], 'confidence': my['conf'], 'reason': reason},
            'suggested_source': 'claude_auto',           # 프리필 출처(사람확정 아님) 표시
            'human_decision': None,                      # 사용자가 게시판에서 채움
            'status': 2,                                 # 사람 판정 대기
            # ── provenance(게시판 미표시, 확정 후 gold 적용용) ──
            '_src_file': r.get('file'), '_src_line': r.get('line'),
            '_stream_gold': sg, '_audit_proposal': r.get('claude_judgment'),
            'note': 'gold_crossing_review_260713',
        })

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')

    # ── 자기검산(규칙 #17) ──
    n = len(out)
    all_cross = all(o['cur_rule_label'] in ('positive', 'negative')
                    and o['claude_judgment'] in ('positive', 'negative')
                    and o['cur_rule_label'] != o['claude_judgment'] for o in out)
    all_why = all(o['ai_reference']['reason'] and '왜 사용자 판단 필요' in o['ai_reference']['reason']
                  for o in out)
    all_opinion = all(o['claude_judgment'] in ('positive', 'negative', 'neutral') for o in out)
    from collections import Counter
    cats = Counter(o['group'].split()[0] for o in out)
    print(f'생성: {n}행 → {os.path.relpath(OUT, DS)}')
    print(f'── 자기검산 ── 고유 {n}행(중복 제거) · '
          f'전행 긍↔부 방향 {"OK" if all_cross else "FAIL"} · '
          f'전행 의견 존재 {"OK" if all_opinion else "FAIL"} · '
          f'전행 판단사유 존재 {"OK" if all_why else "FAIL"}')
    print(f'  사유 카테고리: {dict(cats)} (A=명백오류·B=사람중립충돌·C=양가경계)')
    assert n == 11, f'고유 11행 기대, 실제 {n}'
    assert all_cross and all_why and all_opinion, '자기검산 실패'


if __name__ == '__main__':
    main()
