# -*- coding: utf-8 -*-
"""감정 판정 작업 패킷 — 추출 / 판정(AI) / 삽입의 자기설명 왕복 패킷.

배경(사용자 설계):
  - DB는 가명으로 저장된다(읽기 시 기본 원복은 상위 enrich 계층에서만). 따라서 평가를 그대로
    읽으면 가명이다 → 패킷은 가명이라 외부(LLM)에 안전.
  - 삽입은 같은 DB 레코드를 가명 키로 in-place 수정(기존 sentiment_corrections 재사용) →
    가명 원복/재가명 불필요.
  - 패킷 1개가 "단계 정의·현재 진행 상태·프롬프트·각 단계 지침·데이터(+키)"를 모두 품어,
    사용자는 파일만 주고받으면 된다(추출→판정→삽입).

비식별:
  - 패킷에는 실명/원본 ID 없음. 텍스트는 가명(저장 시 처리됨) + PII 정규식 게이트 통과분만.
  - 키 = {db_id(evaluations.id, 내부 정수), sent_idx} — 개인 식별정보 아님(in-place 수정용).

핵심가치: 판정 단계 규칙에 "긍↔부 오분류 0·중립↔긍정 허용"을 패킷 안에 명시(AI가 그대로 따름).
서버/배치 불요. corrections 스키마 재사용(신규 스키마 0).
"""
import json
import os
import re
from datetime import datetime, timezone

SCHEMA_VERSION = '1.0'

# 마진 사다리(검색형) — 0.05(기본/tight) → 0.10 → 0.15(wide). 가장 넓은 값으로 1회 추출하면서
# 각 문장의 gap=|pos-neg|을 밴드로 태깅해, 재추출 없이 3개 마진 결과를 동시에 비교·선택한다.
_MARGIN_BANDS = (0.05, 0.10, 0.15)
_DEFAULT_MARGIN = _MARGIN_BANDS[0]

# 판정 패킷 저장 루트(고정) — plans 하위 강제(배포 제외 폴더, 가명 텍스트만). 자유 경로 금지.
_JUDGMENT_SUBPATH = ('plans', '_datasets', 'kote_finetune', 'eval', 'judgment')

# PII 정규식 게이트(고신뢰 패턴만 — export_jsonl.py와 동일 정책)
_PII_PATTERNS = [
    ('rrn', re.compile(r'\d{6}[-\s]?[1-4]\d{6}')),
    ('phone', re.compile(r'01[016-9][-\s.]?\d{3,4}[-\s.]?\d{4}')),
    ('email', re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')),
    ('longnum', re.compile(r'\d{6,}')),
]


def _audit_pii(text):
    return [name for name, pat in _PII_PATTERNS if pat.search(text or '')]


def _kote_label(pos, neg, neu):
    m = max(pos, neg, neu)
    return 'positive' if m == pos else ('negative' if m == neg else 'neutral')


def _score_label(score):
    return 'positive' if score > 0 else ('negative' if score < 0 else 'neutral')


def _margin_band(gap):
    """gap(|pos-neg|)이 속하는 최소 마진 밴드 라벨('0.05'/'0.10'/'0.15'). 모든 밴드 초과 시 최대 밴드."""
    for b in _MARGIN_BANDS:
        if gap < b:
            return '%.2f' % b
    return '%.2f' % _MARGIN_BANDS[-1]


def _safe_segment(value):
    """경로 한 세그먼트 안전화 — 경로 탈출/구분자 차단(acquired_handoff와 동형)."""
    s = str(value or '').strip()
    s = s.replace('/', '_').replace('\\', '_')
    s = re.sub(r'[^0-9A-Za-z가-힣_\-]', '_', s)
    s = s.strip('._')
    return s


def _judgment_root():
    """판정 패킷 저장 루트 절대경로(plans 하위 고정)."""
    from src.config.settings import PROJECT_ROOT_DIR
    return os.path.abspath(os.path.join(PROJECT_ROOT_DIR, *_JUDGMENT_SUBPATH))


def save_packet_file(packet, label, batch_id):
    """판정 패킷(dict)을 고정 루트 `eval/judgment/<label>/<batch_id>.json`에 기록(멱등 덮어쓰기).

    경로 탈출 차단(루트 이탈 시 ValueError). plans 폴더는 배포 제외 — 가명 텍스트만 기록.
    Returns: 저장 절대경로.
    """
    root = _judgment_root()
    label = _safe_segment(label) or 'default'
    bid = _safe_segment(batch_id) or 'batch'
    path = os.path.abspath(os.path.join(root, label, bid + '.json'))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError('판정 패킷 경로가 데이터셋 루트를 벗어남: %s' % path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(packet, f, ensure_ascii=False, indent=1)
    return path


def _packet_skeleton(packet_id, source):
    """자기설명 패킷 골격 — 받은 쪽이 _status/_stages만 보고 진행할 수 있게."""
    return {
        '_doc': ('감정 판정 작업 패킷. 단계: extract→judge→insert. 받은 쪽은 '
                 '_status.current_stage 와 _stages[해당단계].instruction 을 읽고 그대로 수행하라. '
                 '판정(judge) 단계면 각 items[].result 를 채우고 _status 를 갱신해 돌려주면 된다.'),
        'schema_version': SCHEMA_VERSION,
        'packet_id': packet_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        '_privacy': ('가명 텍스트 + PII 게이트 통과분만 포함. 실명·원본 ID 없음. '
                     '키(db_id+sent_idx)는 내부 정수라 식별정보 아님. 삽입은 같은 레코드 in-place 수정.'),
        'source': source,
        '_key_fields': ['db_id', 'sent_idx'],
        '_status': {
            'current_stage': 'judge',
            'counts': {'extracted': 0, 'judged': 0, 'inserted': 0},
            'history': [],
        },
        '_stages': {
            'extract': {
                'by': 'system', 'done': True,
                'instruction': '가명 평가에서 하드케이스(긍↔부 불일치·저마진)와 키를 뽑아 items 에 적재.',
            },
            'judge': {
                'by': 'AI(Claude)', 'done': False,
                'instruction': ('각 items[] 의 text 를 읽고 result 에 '
                                '{label, confidence, needs_human, reason} 를 채워라. 끝나면 '
                                "_status.current_stage='insert', _stages.judge.done=true, "
                                'counts.judged 갱신.'),
                'rules': [
                    '긍↔부(긍정↔부정) 오분류 0 이 최우선 — 확신 없으면 needs_human=true.',
                    '중립↔긍정은 허용(과하게 부정으로 내리지 말 것).',
                    '"보완점 없음/단점 없습니다" 등 약점없음 선언은 neutral.',
                    '"~필요/요구/했으면 좋겠" 등 건설적 비판은 negative.',
                    'cur_label 은 현재 시스템 추정치(참고용) — 맹신 말고 문장으로 판정.',
                ],
                'output_schema': {
                    'label': 'positive|negative|neutral',
                    'confidence': 'high|medium|low',
                    'needs_human': 'true 면 사람 모달 확정으로 보냄',
                    'reason': '짧은 근거(선택)',
                },
            },
            'insert': {
                'by': 'system', 'done': False,
                'instruction': ('result 가 채워진 items 를 key(db_id+sent_idx)로 '
                                'evaluations.sentiment_corrections 에 in-place 반영. '
                                'needs_human=true 는 사용자 모달 큐로.'),
            },
        },
        'items': [],
    }


def select_hard_sentences(ev, db_id, existing_corr, margin=0.05):
    """평가(ev) 한 건 → 하드케이스 문장 item 리스트(순수 함수, DB 불요).

    하드 = (KoTE argmax 극 ≠ 보정후 극, 즉 긍↔부/극 불일치) 또는 (|pos-neg|<margin 저마진).
    이미 보정된(sent_idx ∈ existing_corr) 문장은 제외. PII 적발 문장은 (quarantine, item=None).
    """
    from src.services.perspective_service import _get_sentence_level_scores
    doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
    cache = ev.get('sentence_emotion_cache')
    rows = _get_sentence_level_scores(doc, corrections=None, sentence_cache=cache)
    items, quarantined = [], []
    for idx, (sent, score, pos, neg, neutral) in enumerate(rows):
        if not sent:
            continue
        if existing_corr and str(idx) in existing_corr:
            continue                                   # 이미 사람/이전 판정으로 확정 → 제외
        cur = _score_label(score)
        kote = _kote_label(pos, neg, neutral)
        is_pol = {cur, kote} == {'positive', 'negative'}
        is_low = abs(pos - neg) < margin
        if not (is_pol or is_low):
            continue
        if _audit_pii(sent):
            quarantined.append({'db_id': db_id, 'sent_idx': idx, 'pii': _audit_pii(sent)})
            continue
        gap = round(abs(pos - neg), 4)
        items.append({
            'key': {'db_id': db_id, 'sent_idx': idx},
            'text': sent,                              # 가명(저장 시 처리됨)
            'cur_label': cur,
            'kote': [round(pos, 3), round(neg, 3), round(neutral, 3)],
            'gap': gap,                                # |pos-neg| (마진 검색용)
            'hard': 'pol_flip' if is_pol else 'low_margin',
            'margin_band': 'flip' if is_pol else _margin_band(gap),
            'result': None,                            # judge 단계에서 채움
        })
    return items, quarantined


def _load_pseudonymized_evals(batch_id=None, limit=None):
    """evaluations 를 가명 그대로 로드(원복 안 함). [(ev_obj(+_db_id), employee_id), ...]."""
    from src.services.perspective_service import _get_eval_conn
    conn = _get_eval_conn()
    try:
        sql = "SELECT id, employee_id, data, sentiment_corrections FROM evaluations"
        params = ()
        if batch_id:
            sql += " WHERE batch_id = ?"
            params = (batch_id,)
        sql += " ORDER BY id"
        if limit:
            sql += " LIMIT %d" % int(limit)
        out = []
        for row in conn.execute(sql, params).fetchall():
            db_id, emp_id, data, corr = row
            if not data:
                continue
            try:
                ev = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
            ev['_db_id'] = db_id
            try:
                existing = json.loads(corr or '{}')
            except (json.JSONDecodeError, TypeError):
                existing = {}
            out.append((ev, emp_id, existing))
        return out
    finally:
        conn.close()


def build_judgment_packet(batch_id=None, margin=None, limit=None):
    """가명 평가에서 하드케이스를 추출해 자기설명 판정 패킷(dict) 생성.

    margin 미지정 시 가장 넓은 밴드(_MARGIN_BANDS[-1])로 1회 추출하고, 각 item을 margin_band로
    태깅해 `_margin.bands`(0.05/0.10/0.15/flip 건수)를 함께 산출 → 재추출 없이 마진 검색.
    Returns: (packet, quarantined). packet 은 그대로 파일로 저장해 LLM 전달 가능(가명).
    """
    if margin is None:
        margin = _MARGIN_BANDS[-1]
    pid = 'judge_%s_%s' % (batch_id or 'all', datetime.now().strftime('%y%m%d_%H%M'))
    packet = _packet_skeleton(pid, {'batch_id': batch_id, 'margin': margin})
    quarantined = []
    for ev, emp_id, existing in _load_pseudonymized_evals(batch_id, limit):
        items, quar = select_hard_sentences(ev, ev['_db_id'], existing, margin)
        packet['items'].extend(items)
        quarantined.extend(quar)
    # 마진 밴드 요약(검색형) — 사용자가 재추출 없이 적정 마진을 비교·선택
    bands = {('%.2f' % b): 0 for b in _MARGIN_BANDS}
    bands['flip'] = 0
    for it in packet['items']:
        mb = it.get('margin_band')
        if mb in bands:
            bands[mb] += 1
    packet['_margin'] = {'default': _DEFAULT_MARGIN, 'extracted_at': margin, 'bands': bands}
    packet['_status']['counts']['extracted'] = len(packet['items'])
    packet['_status']['counts']['quarantined'] = len(quarantined)
    packet['_status']['history'].append({
        'stage': 'extract', 'by': 'system',
        'at': datetime.now(timezone.utc).isoformat(),
        'n': len(packet['items']), 'quarantined': len(quarantined)})
    return packet, quarantined


def apply_judgment_packet(packet, conn=None):
    """판정 완료 패킷 → evaluations.sentiment_corrections 에 in-place 반영(기존 스키마 재사용).

    result.label 이 있고 needs_human != true 인 item 만 반영. needs_human=true 는 모달 큐로.
    Returns: 요약 dict.
    """
    from src.services.perspective_service import _get_eval_conn
    own = conn is None
    conn = conn or _get_eval_conn()
    # db_id 별로 {sent_idx: label} 묶기
    by_db, needs_human, skipped = {}, [], 0
    for it in packet.get('items', []):
        res = it.get('result')
        key = it.get('key', {})
        if not res or 'label' not in res:
            skipped += 1
            continue
        if res.get('needs_human') is True:
            needs_human.append(it)
            continue
        if res['label'] not in ('positive', 'negative', 'neutral'):
            skipped += 1
            continue
        db_id = key.get('db_id')
        sent_idx = key.get('sent_idx')
        if db_id is None or sent_idx is None:
            skipped += 1
            continue
        by_db.setdefault(int(db_id), {})[str(sent_idx)] = res['label']
    inserted = 0
    try:
        for db_id, sent_corr in by_db.items():
            cur = conn.execute(
                "SELECT sentiment_corrections FROM evaluations WHERE id = ?", (db_id,)
            ).fetchone()
            if cur is None:
                continue
            try:
                existing = json.loads(cur[0] or '{}')
            except (json.JSONDecodeError, TypeError):
                existing = {}
            merged = {**existing, **sent_corr}          # 신규 판정 우선, 기존 인덱스 보존
            conn.execute(
                "UPDATE evaluations SET sentiment_corrections = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=False), db_id))
            inserted += len(sent_corr)
        conn.commit()
    finally:
        if own:
            conn.close()
    return {
        'inserted_sentences': inserted,
        'updated_evaluations': len(by_db),
        'needs_human': len(needs_human),
        'needs_human_items': needs_human,
        'skipped': skipped,
    }
