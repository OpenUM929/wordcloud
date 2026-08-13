# -*- coding: utf-8 -*-
"""group-review 게시판용 에스컬레이션 큐 생성 — 사용자 판정 대기건이 게시판에 안 뜨던 버그 해소.

문제(사용자 보고 260715): group-review에서 label_audit_prefill_260708.jsonl 이 (644/644)로
  뜨고 판정할 게 안 보임. 원인: 그 파일은 모든 행에 gold(=감사 대상 원본 라벨)를 담았는데,
  게시판 로드(api_group_review_load)는 `decision = human_decision or gold` 로 gold를 "판정완료"
  로 해석 → 644행 전부 완료 처리 → "미판정만" 필터에서 0건. (label_audit_queue_260708.jsonl 동일)

해결(데이터 레이어 — UI 코드/서버 무수정):
  정상 프리필 스키마(hard_prefilled_260707_c2)에 맞춘 큐를 새로 만든다.
    · gold 미기록 · human_decision=null  → 게시판이 '미판정'으로 정상 노출
    · claude_judgment={polarity,reason}   → '내 판정' 열(참고)
    · cur_rule_label = 현재 파일 라벨(gold)  → '현규칙' 열
    · ai_reference = 감사 컨텍스트(충돌후보·kind·확신)  → '알고리즘 참고' 열
  대상 = escalate=True 잔여만(94). 지침: 규칙이 정하는 건 이미 적용, 진짜 애매한 것만 사용자에게.
  긍↔부(pos↔neg) 방향을 최상단 정렬(핵심가치 우선).

재실행 안전(사용자 요청 "정보도 업데이트"): 출력 파일이 이미 있으면 rec_id로 병합 —
  사용자가 판정한 행(human_decision 있음)은 그대로 보존, 미판정 행만 컨텍스트 갱신.
  → 감사 소스가 바뀌어도 사용자 작업분은 절대 유실 안 됨.

각 행에 _audit{file,line,orig} 보존 → 사용자 확정 후 propagate 스크립트가 원본 TRAIN/TEST에 역반영.
"""
import io
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
REVIEW = os.path.join(DS, 'eval', 'review')
SRC = os.path.join(REVIEW, 'label_audit_prefill_260708.jsonl')
OUT = os.path.join(REVIEW, 'label_audit_escalation_260715.jsonl')
CORPUS = os.path.join(DS, 'emotion', 'weak_export_260624.jsonl')  # 전파력(동일텍스트 반복) 측정용

CONF_MAP = {'high': 0.9, 'medium': 0.6, 'low': 0.35}


def corpus_freq():
    """동일 텍스트가 대량 코퍼스에 몇 번 나오나 — 판정 1건의 정책 전파력."""
    from collections import Counter
    c = Counter()
    if os.path.exists(CORPUS):
        for line in io.open(CORPUS, encoding='utf-8'):
            try:
                t = (json.loads(line).get('text') or '').strip()
            except ValueError:
                continue
            if t:
                c[t] += 1
    return c


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def rec_id_for(r):
    if r.get('rec_id'):
        return str(r['rec_id'])
    base = os.path.basename(r.get('file') or 'unknown').replace('.jsonl', '')
    return f'audit-{base}-{r.get("line")}'


def build_row(r, freq=None):
    orig = r.get('gold')                       # 현재 파일에 저장된 라벨(감사 대상)
    cj = r.get('claude_judgment')              # 내 제안 라벨
    conflict = r.get('conflict_labels') or []
    pn = {orig, cj} == {'positive', 'negative'}
    prop = (freq or {}).get((r.get('text') or '').strip(), 0)   # 정책 전파력
    reason = (f"L1감사({r.get('kind')})"
              + (f" · 전파 {prop}행" if prop >= 5 else '')
              + f" · 기존라벨={orig}"
              + (f" · 충돌후보={'/'.join(conflict)}" if conflict else '')
              + (' · ★긍↔부(최우선)' if pn else ''))
    return {
        'rec_id': rec_id_for(r),
        'text': r.get('text'),
        'field': r.get('field'),
        'cur_rule_label': orig,                # '현규칙' 열 = 현재 라벨
        'ai_reference': {                       # '알고리즘 참고' 열 = 감사 컨텍스트
            'polarity': orig,
            'confidence': CONF_MAP.get(r.get('claude_confidence'), 0.5),
            'reason': reason,
        },
        'claude_judgment': {                   # '내 판정' 열 = 내 제안 + 근거
            'polarity': cj,
            'reason': r.get('claude_reason') or '',
        },
        'suggested': cj,
        'suggested_source': 'claude_auto',
        'human_decision': None,                # ← 게시판 '미판정'으로 노출되는 핵심
        'group': r.get('kind'),
        'source_file': 'label_audit_prefill_260708.jsonl',
        'note': 'L1_escalation_260715',
        '_pn': pn,                             # 정렬/통계용(게시판 무시 필드)
        '_prop': prop,                         # 정책 전파력(코퍼스 반복수)
        '_audit': {'file': r.get('file'), 'line': r.get('line'), 'orig': orig, 'kind': r.get('kind')},
    }


def main():
    src = loadl(SRC)
    esc = [r for r in src if r.get('escalate')]
    freq = corpus_freq()
    new_rows = [build_row(r, freq) for r in esc]

    # ── 재실행 병합: 기존 사용자 판정 보존 ──────────────────────────────
    prev = {str(r.get('rec_id')): r for r in loadl(OUT)}
    preserved = 0
    for row in new_rows:
        old = prev.get(row['rec_id'])
        if old and old.get('human_decision') is not None:
            row['human_decision'] = old['human_decision']       # 사용자 판정 유지
            row['decision_source'] = old.get('decision_source', 'human')
            preserved += 1

    # 정렬(효용 순): ①긍↔부 최우선 ②정책 전파력 큰 순 ③확신 낮은 순(애매한 것 위로)
    #   → 상위 ~40건(긍↔부+고전파+측정자)이 먼저, 일회성 50건은 자연히 하단.
    new_rows.sort(key=lambda x: (not x['_pn'], -x['_prop'], x['ai_reference']['confidence']))

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    pend = sum(1 for r in new_rows if r.get('human_decision') is None)
    print(f'게시판 큐 생성: {len(new_rows)}행 → review/{os.path.basename(OUT)}')
    print(f'  · 미판정(게시판 노출): {pend} · 기존 사용자판정 보존: {preserved}')
    print(f'  · ★긍↔부(최우선): {sum(1 for r in new_rows if r["_pn"])}')
    print(f'  · kind: {dict(Counter(r["group"] for r in new_rows))}')
    print(f'  · rec_id 합성(원래 없던 것): {sum(1 for r in new_rows if r["rec_id"].startswith("audit-"))}')
    print('\n게시판에서 파일 선택: label_audit_escalation_260715.jsonl (0/%d로 떠야 정상)' % len(new_rows))


if __name__ == '__main__':
    main()
