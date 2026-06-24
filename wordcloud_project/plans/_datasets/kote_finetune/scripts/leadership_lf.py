# -*- coding: utf-8 -*-
"""리더십 약지도 라벨링 함수(LF) — weak_leadership 후보 생성.

설계 정본: ../leadership/weak_labeling_lf.md §3~§6 · 택소노미: ../leadership/trait_tree.json
정본 스펙: ../leadership/TRAIT_TREE.md (백본2 + 대그룹9 + 세부20, split-only 단조)

⚠️ 이것은 gold 생성기가 아니다. 문장에 **약한 후보 라벨(weak)** 만 붙여 사람 검토 큐에
   우선순위로 태우는 가속기다. 확정 gold는 사람만(추측 분류 금지).

핵심 가드레일(weak_labeling_lf §7):
  - weak-only: `*_gold` 절대 미기록. 후보만.
  - 기본 grouped(대그룹): 추측 세분화 금지. 세부 trait/micro는 '힌트'로만.
  - 긍↔부(positive↔risk) 재게이트: leadership_polarity 결과를 그대로 따른다.
      · 문장 극성 positive/neutral → positive 백본 후보만, risk 후보 차단(+flag).
      · 문장 극성 negative        → risk 백본 후보만.
      · is_negation_praise("강압적이지 않음") → risk 오귀속 차단(극성이 이미 positive).
  - trait/label은 언제든 바뀔 수 있다 → 근거(evidence_markers)+안정 node id+trait_ref+
    lf_version을 함께 남겨, 택소노미가 바뀌면 재라벨링 없이 node id로 재정렬한다.
  - O(n): 문장당 표지 매칭 상수.
"""
import json
import os

HERE = os.path.dirname(__file__)
_TREE_PATH = os.path.abspath(os.path.join(HERE, '..', 'leadership', 'trait_tree.json'))
_TREE_CACHE = None


def load_tree(path=None):
    """trait_tree.json을 로드(캐시). 택소노미 변경은 코드가 아닌 이 파일에서."""
    global _TREE_CACHE
    if _TREE_CACHE is not None and path is None:
        return _TREE_CACHE
    with open(path or _TREE_PATH, encoding='utf-8') as f:
        tree = json.load(f)
    # 노드 인덱싱
    nodes = {n['id']: n for n in tree['nodes']}
    tree['_by_id'] = nodes
    tree['_groups'] = [n for n in tree['nodes'] if n.get('level') == 1]
    tree['_traits'] = [n for n in tree['nodes'] if n.get('level') == 2]
    if path is None:
        _TREE_CACHE = tree
    return tree


def _polarity_to_backbone(polarity):
    """문장 극성(positive|negative|neutral) → 허용 백본 극성(positive|risk)."""
    if polarity == 'negative':
        return 'risk'
    # positive·neutral 모두 positive 백본만 허용(risk는 명시적 negative일 때만 — 긍↔부 0)
    return 'positive'


def build_leadership_candidates(text, polarity, is_neg_praise=False, tree=None):
    """문장(또는 절) 하나에 weak_leadership 후보 블록을 생성한다.

    Args:
        text: 가명화 완료 문장/절.
        polarity: hr_context_lexicon.leadership_polarity(text) 결과 ('positive'|'negative'|'neutral').
        is_neg_praise: hr_context_lexicon.is_negation_praise(text) 결과(부정의 부정=칭찬).
        tree: load_tree() 결과(미지정 시 기본 로드).

    Returns:
        dict (weak_labeling_lf §3-4 스키마). 표지 미매칭이면 is_leadership=False.
    """
    tree = tree or load_tree()
    text = text or ''
    allowed = _polarity_to_backbone(polarity)
    overlap_pairs = [set(p) for p in tree.get('overlap_grouped_pairs', [])]

    # 1) 세부 trait seed 매칭 → 부모 대그룹별로 근거 집계
    group_hits = {}     # group_id -> {evidence:set, trait_refs:set, trait_nodes:set, polarity}
    risk_suppressed = False
    for tr in tree['_traits']:
        matched = [m for m in tr.get('seed_markers', []) if m in text]
        if not matched:
            continue
        gid = tr['parent']
        grp = tree['_by_id'][gid]
        # 극성 게이트: 백본 불일치 후보는 제외(긍↔부 0)
        if grp['polarity'] != allowed:
            if grp['polarity'] == 'risk':
                risk_suppressed = True   # risk 표지가 있으나 극성이 negative가 아님 → 충돌
            continue
        slot = group_hits.setdefault(gid, {
            'evidence': set(), 'trait_refs': set(), 'trait_nodes': set(),
            'polarity': grp['polarity']})
        slot['evidence'].update(matched)
        slot['trait_refs'].add(tr.get('trait_ref'))
        slot['trait_nodes'].add(tr['id'])

    # 2) 대그룹 자체 seed도 매칭(세부엔 없지만 대그룹 수준에서 리더십성 포착)
    for grp in tree['_groups']:
        if grp['polarity'] != allowed:
            if grp['polarity'] == 'risk' and any(m in text for m in grp.get('seed_markers', [])):
                risk_suppressed = True
            continue
        matched = [m for m in grp.get('seed_markers', []) if m in text]
        if matched:
            slot = group_hits.setdefault(grp['id'], {
                'evidence': set(), 'trait_refs': set(), 'trait_nodes': set(),
                'polarity': grp['polarity']})
            slot['evidence'].update(matched)

    if not group_hits:
        return {
            'is_leadership': False, 'polarity': polarity, 'candidates': [],
            'micro_hint': [], 'queue_tier': 3, 'confidence': 'C',
            'flags': (['risk_suppressed_polarity'] if risk_suppressed else []),
            'lf_version': tree.get('lf_version', '1'),
        }

    # 3) 후보 구성(기본 grouped=대그룹). 세부 trait는 hint로만.
    candidates, all_micro = [], set()
    for gid, slot in group_hits.items():
        grp = tree['_by_id'][gid]
        trait_refs = sorted(r for r in slot['trait_refs'] if r)
        # 겹침쌍이면 세부 힌트 억제(군집 검증 전 grouped 고정)
        overlap_flag = any(set(trait_refs) >= pair for pair in overlap_pairs)
        candidates.append({
            'node': gid,                      # 불변 안정 id(택소노미 바뀌어도 고정)
            'level': 1,                       # 기본 대그룹
            'name': grp['name'],
            'polarity': slot['polarity'],     # positive | risk
            'trait_refs': trait_refs,         # 외부 앵커(가설)
            'trait_hints': ([] if overlap_flag else sorted(slot['trait_nodes'])),
            'evidence': sorted(slot['evidence']),
            'status_hint': 'grouped',         # 확정 세분화는 사람·군집 후
            'score': len(slot['evidence']),
        })
        all_micro.update(slot['evidence'])
    candidates.sort(key=lambda c: -c['score'])

    # 4) 신뢰도·큐 우선순위(weak_labeling_lf §6)
    flags = ['polarity_ok']
    if is_neg_praise:
        flags.append('negation_praise')
    queue_tier = 3
    if risk_suppressed:
        flags.append('polarity_conflict')   # 긍/리스크 표지 혼재 → rule_hurt 위험
        queue_tier = 1
    elif len(candidates) >= 2 and candidates[0]['score'] - candidates[1]['score'] < 1:
        queue_tier = 2                       # 대그룹 간 저마진 → 경계 검토
    top_score = candidates[0]['score']
    confidence = 'A' if top_score >= 3 else ('B' if top_score == 2 else 'C')

    return {
        'is_leadership': True,
        'polarity': polarity,
        'candidates': candidates,
        'micro_hint': sorted(all_micro),     # 표면표지 근사(모델 타깃 아님 — 힌트)
        'queue_tier': queue_tier,
        'confidence': confidence,
        'flags': flags,
        'lf_version': tree.get('lf_version', '1'),
    }


if __name__ == '__main__':
    # 스모크 테스트(KoTE 불요). 실제 극성은 hr_context_lexicon이 결정하나 여기선 직접 주입.
    samples = [
        ('수평적 의사소통과 경청으로 팀워크를 이끈다', 'positive', False),
        ('성장 피드백과 격려로 후배를 육성함', 'positive', False),
        ('세세한 지시 감독과 강압으로 일방적 지시', 'negative', False),
        ('강압적이지 않음', 'positive', True),         # risk 차단되어야
        ('데이터 기반 분석으로 정확한 방향제시', 'positive', False),
        ('보통 수준입니다', 'neutral', False),          # 비-리더십
    ]
    for txt, pol, npz in samples:
        out = build_leadership_candidates(txt, pol, npz)
        cands = [(c['node'], c['trait_refs'], c['evidence']) for c in out['candidates']]
        print(f"[{pol:8}] {txt}")
        print(f"   is_ld={out['is_leadership']} tier={out['queue_tier']} "
              f"conf={out['confidence']} flags={out['flags']}")
        print(f"   cands={cands}")
