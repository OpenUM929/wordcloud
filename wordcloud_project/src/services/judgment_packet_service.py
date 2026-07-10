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
        '_doc': ('감정 판정 작업 패킷. 각 items[] 는 status 로 진행된다 '
                 '(1=AI판정대기, 2=사람판정대기, 3=AI작업완료, 4=Human작업완료, '
                 '10=AI DB반영완료, 11=Human DB반영완료). 받은 AI(judge)는 각 item 의 text 를 '
                 '읽고 ai_reference 를 채운 뒤, 긍↔부 확신 시 status=3, 애매하면 status=2 로 둔다. '
                 'status=2 는 사람 게시판(그룹검토)이 판정해 status=4 로 올린다. 작업 완료(3·4)는 '
                 '운영자가 "DB에 반영" 버튼을 누를 때 각각 10·11 로 전이되며 그때 DB 에 기록된다.'),
        'schema_version': SCHEMA_VERSION,
        'packet_id': packet_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        '_privacy': ('가명 텍스트 + PII 게이트 통과분만 포함. 실명·원본 ID 없음. '
                     '키(db_id+sent_idx)는 내부 정수라 식별정보 아님. 삽입은 같은 레코드 in-place 수정.'),
        'source': source,
        '_key_fields': ['rec_id', 'db_id', 'sent_idx'],
        '_status': {
            'current_stage': 'judge',
            'counts': {'extracted': 0, 'judged': 0, 'inserted': 0},
            'history': [],
        },
        '_status_codes': {
            '1': 'AI 판정 대기', '2': '사람 판정 대기',
            '3': 'AI 작업 완료(DB 반영 대기)', '4': 'Human 작업 완료(DB 반영 대기)',
            '10': 'AI DB 반영 완료', '11': 'Human DB 반영 완료',
        },
        '_stages': {
            'extract': {
                'by': 'system', 'done': True,
                'instruction': '가명 평가에서 하드케이스(긍↔부 불일치·저마진)와 키를 뽑아 items 에 적재(status=1).',
            },
            'judge': {
                'by': 'AI(Claude)', 'done': False,
                'instruction': ('각 items[] 의 text 를 읽고 ai_reference 에 '
                                '{polarity, confidence, reason} 를 채워라. 긍↔부 확신 시 '
                                'status=3, 애매하면 status=2(사람 게시판으로 감). status=1 은 남기지 말 것.'),
                'rules': [
                    '긍↔부(긍정↔부정) 오분류 0 이 최우선 — 확신 없으면 status=2.',
                    '중립↔긍정은 허용(과하게 부정으로 내리지 말 것).',
                    '"보완점 없음/단점 없습니다" 등 약점없음 선언은 neutral.',
                    '"~필요/요구/했으면 좋겠" 등 건설적 비판은 negative.',
                    'cur_rule_label 은 현재 시스템 추정치(참고용) — 맹신 말고 문장으로 판정.',
                    'model_ref 는 파인튜닝 모델의 캘리브레이션(T scaling) 신뢰도(참고용, 없을 수 있음) — '
                    'confidence 가 낮은 item 은 status=2(사람) 쪽으로 보수적으로.',
                ],
                'output_schema': {
                    'ai_reference': {
                        'polarity': 'positive|negative|neutral',
                        'confidence': 'high|medium|low',
                        'reason': '짧은 근거(선택)',
                    },
                    'status': '3=확신(AI 작업완료, 이후 버튼으로 DB 반영) | 2=애매(사람 게시판)',
                },
            },
            'insert': {
                'by': 'system', 'done': False,
                'instruction': ('운영자가 "DB에 반영" 버튼을 누르면 작업완료 item(3=AI, 4=Human)을 '
                                'key(db_id+sent_idx)로 evaluations.sentiment_corrections 에 in-place '
                                '반영하고 status 를 10/11 로 전이한다. 최종 라벨은 human_decision 우선, '
                                '없으면 ai_reference.polarity. status==2 는 게시판(그룹검토)으로.'),
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
    doc_field = (ev.get('evaluation_document_field') or '').strip()  # 장점/단점(문서 단위 단일극성, 0707_01)
    cache = ev.get('sentence_emotion_cache')
    rows = _get_sentence_level_scores(doc, corrections=None, sentence_cache=cache, field=(doc_field or None))
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
            'rec_id': '%s_%s' % (db_id, idx),          # 게시판 키(db_id_sent_idx)
            'key': {'db_id': db_id, 'sent_idx': idx},  # DB 반영 키
            'text': sent,                              # 가명(저장 시 처리됨)
            'field': doc_field,                        # 장점/단점(문서 단위 상속, 미상 시 "")
            'cur_rule_label': cur,                     # 게시판 '현규칙'
            'kote': [round(pos, 3), round(neg, 3), round(neutral, 3)],
            'gap': gap,                                # |pos-neg| (마진 검색용)
            'hard': 'pol_flip' if is_pol else 'low_margin',
            'margin_band': 'flip' if is_pol else _margin_band(gap),
            'ai_reference': {'polarity': None, 'confidence': None, 'reason': None},  # judge 채움
            'status': 1,                               # 1=AI판정대기 2=사람판정대기 3=확정
            'human_decision': None,                    # 게시판이 채움
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


def _annotate_model_confidence(items):
    """items 에 model_ref={'label','confidence'}(파인튜닝 모델·T 캘리브레이션) 부착 — 선택 소비(0708_02 L3).

    모델 off/부재/실패 시 아무것도 부착하지 않는다(기존 소비자 무영향). argmax 결정에는 관여하지
    않으며, judge(AI)·게시판이 escalation 라우팅 참고로만 쓴다.
    """
    if not items:
        return
    try:
        from src.config.settings import USE_HR_SENTIMENT_MODEL
        if not USE_HR_SENTIMENT_MODEL:
            return
        from src.modules.hr_sentiment import predict_proba
        res = predict_proba([it.get('text') or '' for it in items],
                            fields=[it.get('field') or None for it in items])
    except Exception:
        return
    if not res or len(res) != len(items):
        return
    for it, r in zip(items, res):
        it['model_ref'] = {'label': r['label'], 'confidence': round(r['confidence'], 4)}


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
    _annotate_model_confidence(packet['items'])   # 캘리브레이션 신뢰도(있으면) — 선택 소비
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


_VALID_LABELS = ('positive', 'negative', 'neutral')

# ============================================================
# 판정 패킷 상태 코드 (0702_01, 옵션 C — 현행+최소 확장)
#   작업 주체(AI/Human) × 단계(대기 → 작업완료 → DB반영완료) 2차원.
#   1/2 는 레거시와 동일 의미 유지 → group-review(사람대기=2) 회귀 없음.
# ============================================================
STATUS_AI_PENDING    = 1    # AI 판정 대기
STATUS_HUMAN_PENDING = 2    # 사람 판정 대기(그룹검토 게시판)
STATUS_AI_READY      = 3    # AI 작업 완료 — 확신(DB 반영 대기)
STATUS_HUMAN_READY   = 4    # Human 작업 완료(DB 반영 대기)
STATUS_AI_APPLIED    = 10   # AI DB 반영 완료
STATUS_HUMAN_APPLIED = 11   # Human DB 반영 완료

# 작업 완료(반영 대기) + 반영 완료 → 최종 라벨을 갖는 상태
_LABELED_STATES = (STATUS_AI_READY, STATUS_HUMAN_READY, STATUS_AI_APPLIED, STATUS_HUMAN_APPLIED)
# 사람 판정 대기(그룹검토 게시판 노출 대상) — 옵션 C 에서는 2 뿐
HUMAN_PENDING = (STATUS_HUMAN_PENDING,)


def _final_label(it):
    """item 의 최종 라벨 — human_decision 우선, 없으면 ai_reference.polarity, 그다음 레거시 result.label."""
    hd = it.get('human_decision')
    if hd in _VALID_LABELS:
        return hd
    pol = (it.get('ai_reference') or {}).get('polarity')
    if pol in _VALID_LABELS:
        return pol
    res_label = (it.get('result') or {}).get('label')   # 레거시(result) 스키마 파생 — _map_status 와 짝
    return res_label if res_label in _VALID_LABELS else None


def _map_status(it):
    """레거시/신규 status → 정규 코드(순수 — it 미변조).

    - status 없음(구 result 스키마): needs_human→2, label 유효→3, 그 외→1
    - 레거시 status==3(구 '확정')은 human_decision 유무로 주체 분기:
        human_decision 유효 → 4(Human 작업완료), 아니면 → 3(AI 작업완료)
      (신규 흐름의 Human 완료는 update_packet_decisions 가 이미 4 로 저장하므로
       '3+human_decision' 조합은 레거시 패킷에서만 나타난다.)
    - 그 외는 그대로.
    """
    status = it.get('status')
    if status is None:
        res = it.get('result') or {}
        if res.get('needs_human') is True:
            return STATUS_HUMAN_PENDING
        return STATUS_AI_READY if (res.get('label') in _VALID_LABELS) else STATUS_AI_PENDING
    if status == STATUS_AI_READY and it.get('human_decision') in _VALID_LABELS:
        return STATUS_HUMAN_READY
    return status


def resolve_item(it):
    """통합 item → (status, final_label). 순수 함수(it 미변조).

    반환 status ∈ {1,2,3,4,10,11}. final_label 은 라벨 보유 상태(3/4/10/11)에서만 유효.
    """
    status = _map_status(it)
    if status in _LABELED_STATES:
        return status, _final_label(it)
    return (status if status in (STATUS_AI_PENDING, STATUS_HUMAN_PENDING) else STATUS_AI_PENDING), None


def _merge_corrections_by_db(conn, by_db):
    """{db_id: {sent_idx: label}} 를 evaluations.sentiment_corrections 에 in-place 병합.

    신규 판정 우선(기존 인덱스 보존). Returns: (inserted_sentences, updated_evaluations).
    """
    inserted, updated = 0, 0
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
        merged = {**existing, **sent_corr}              # 신규 판정 우선, 기존 인덱스 보존
        conn.execute(
            "UPDATE evaluations SET sentiment_corrections = ? WHERE id = ?",
            (json.dumps(merged, ensure_ascii=False), db_id))
        inserted += len(sent_corr)
        updated += 1
    return inserted, updated


def apply_judgment_packet(packet, conn=None):
    """판정 패킷 → evaluations 반영(status 기반). **DB 반영 완료(10/11)만 실제 기록**.

    0702_01: DB 반영 시점을 사용자 버튼("DB에 반영")으로 분리. 이 함수(업로드/재적용)는
    이미 DB 반영 완료된 10/11 만 멱등 재기록하고, 작업 완료(3=AI, 4=Human)는 기록하지 않고
    ai_ready/human_ready 로 집계만 한다(버튼으로 3→10, 4→11 전이 시 반영).
    Returns: {inserted_sentences, updated_evaluations, pending_ai, pending_human,
              ai_ready, human_ready, skipped}.
    """
    from src.services.perspective_service import _get_eval_conn
    own = conn is None
    conn = conn or _get_eval_conn()
    by_db = {}
    pending_ai = pending_human = ai_ready = human_ready = skipped = 0
    for it in packet.get('items', []):
        st, label = resolve_item(it)
        if st == STATUS_AI_PENDING:
            pending_ai += 1
            continue
        if st == STATUS_HUMAN_PENDING:
            pending_human += 1
            continue
        if st == STATUS_AI_READY:                       # AI 작업완료 — 버튼 대기(미반영)
            ai_ready += 1
            continue
        if st == STATUS_HUMAN_READY:                    # Human 작업완료 — 버튼 대기(미반영)
            human_ready += 1
            continue
        # st in (10, 11) — DB 반영 완료분만 멱등 재기록
        if label not in _VALID_LABELS:
            skipped += 1
            continue
        key = it.get('key', {})
        db_id = key.get('db_id')
        sent_idx = key.get('sent_idx')
        if db_id is None or sent_idx is None:
            skipped += 1
            continue
        by_db.setdefault(int(db_id), {})[str(sent_idx)] = label
    try:
        inserted, updated = _merge_corrections_by_db(conn, by_db)
        conn.commit()
    finally:
        if own:
            conn.close()
    return {
        'inserted_sentences': inserted,
        'updated_evaluations': updated,
        'pending_ai': pending_ai,
        'pending_human': pending_human,
        'ai_ready': ai_ready,
        'human_ready': human_ready,
        'skipped': skipped,
    }


def apply_db_to_packet(packet, conn=None, target='all'):
    """"DB에 반영" 버튼 전용 — 작업 완료분을 DB 반영 + status 전이(3→10, 4→11).

    target: 'ai'→3(AI 작업완료)만, 'human'→4(Human 작업완료)만, 'all'→둘 다.
    packet.items 의 status 를 in-place 로 10/11 로 올린다(호출측이 파일 저장).
    Returns: {applied_ai, applied_human, skipped, packet}.
    """
    from src.services.perspective_service import _get_eval_conn
    own = conn is None
    conn = conn or _get_eval_conn()
    want = {'ai': {STATUS_AI_READY}, 'human': {STATUS_HUMAN_READY},
            'all': {STATUS_AI_READY, STATUS_HUMAN_READY}}.get(target, {STATUS_AI_READY, STATUS_HUMAN_READY})
    by_db, applied_ai, applied_human, skipped = {}, 0, 0, 0
    for it in packet.get('items', []):
        st, label = resolve_item(it)
        if st not in want:                              # target 에 해당하는 작업완료만
            continue
        if label not in _VALID_LABELS:
            skipped += 1
            continue
        key = it.get('key', {})
        db_id = key.get('db_id')
        sent_idx = key.get('sent_idx')
        if db_id is None or sent_idx is None:
            skipped += 1
            continue
        by_db.setdefault(int(db_id), {})[str(sent_idx)] = label
        if st == STATUS_AI_READY:
            it['status'] = STATUS_AI_APPLIED            # 3 → 10
            applied_ai += 1
        else:
            it['status'] = STATUS_HUMAN_APPLIED         # 4 → 11
            applied_human += 1
    try:
        _merge_corrections_by_db(conn, by_db)
        conn.commit()
    finally:
        if own:
            conn.close()
    return {'applied_ai': applied_ai, 'applied_human': applied_human,
            'skipped': skipped, 'packet': packet}


def load_packet(path):
    """패킷 JSON 파일 로드(dict 반환). items 없으면 ValueError."""
    with open(path, encoding='utf-8') as f:
        pkt = json.load(f)
    if not isinstance(pkt, dict) or 'items' not in pkt:
        raise ValueError('유효한 판정 패킷이 아님(items 필요): %s' % path)
    return pkt


def update_packet_decisions(path, decisions):
    """그룹검토 게시판 저장 → 패킷 item 의 human_decision 기록·status=4(Human 작업완료) 전이.

    decisions: [{rec_id, decision}, ...]. rec_id 로 item 매칭, human_decision 저장.
    감정 3분류(pos/neg/neu)만 status=4(Human 작업완료, DB 반영 대기)로 올린다. not_group/skip 은
    사람이 "감정 3분류 아님"으로 보류한 것 → human_decision 에 기록하되 status 는 2(사람대기)로 유지
    (DB 반영 대상 아님). 실제 DB 반영은 이후 "DB에 반영" 버튼(4→11)이 수행. 봉투·key 는 보존.
    Returns: 갱신된 item 수.
    """
    pkt = load_packet(path)
    dmap = {str(d.get('rec_id')): d.get('decision') for d in (decisions or [])}
    found = 0
    for it in pkt.get('items', []):
        dec = dmap.get(str(it.get('rec_id')))
        if dec is None:
            continue
        it['human_decision'] = dec
        it['status'] = STATUS_HUMAN_READY if dec in _VALID_LABELS else STATUS_HUMAN_PENDING
        found += 1
    if found:
        try:
            pkt['_status']['counts']['human_decided'] = sum(
                1 for x in pkt['items'] if x.get('status') == STATUS_HUMAN_READY)
        except (KeyError, TypeError):
            pass
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(pkt, f, ensure_ascii=False, indent=1)
    return found
