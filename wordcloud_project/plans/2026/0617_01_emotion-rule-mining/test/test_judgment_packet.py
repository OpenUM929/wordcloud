# -*- coding: utf-8 -*-
"""감정 판정 작업 패킷 — 단위/왕복 테스트 (서버·KoTE 불요, 인메모리 DB).

검증:
  1) select_hard_sentences: 하드케이스(긍↔부 불일치·저마진)만 추출, 이미 보정분/PII 제외.
  2) 패킷 골격: 자기설명(_stages/judge.rules/output_schema) + 가명 키만(실 ID 없음).
  3) apply_judgment_packet(집계) + apply_db_to_packet(반영): status 전이·in-place 병합·기존 보존.

수정 이력: 0709 — v2 status 패킷(0701_03 재설계: rec_id/status/ai_reference/human_decision,
  집계와 DB 반영 분리)에 맞춰 v1 스키마(result/needs_human) 단언 교체.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.judgment_packet_service import (
    select_hard_sentences, _packet_skeleton, apply_judgment_packet,
    apply_db_to_packet, _kote_label, _audit_pii,
    STATUS_AI_PENDING, STATUS_HUMAN_PENDING, STATUS_AI_READY,
    STATUS_AI_APPLIED,
)


def _fake_ev(db_id, sentences):
    """sentence_emotion_cache 주입 가짜 평가(KoTE 재실행 불요)."""
    doc = '. '.join(s[0] for s in sentences)
    cache = [{'sentence': s[0], 'pos': s[1], 'neg': s[2], 'neutral': s[3]} for s in sentences]
    return {'_db_id': db_id, 'evaluation_document': doc, 'sentence_emotion_cache': cache}


def test_select_hard_only():
    # 명확한 긍정/부정은 제외, 저마진·극불일치만 추출
    ev = _fake_ev(10, [
        ('업무 능력이 매우 뛰어남', 0.95, 0.01, 0.04),        # 명확 긍정 → 제외
        ('협업능력이 부족합니다', 0.01, 0.98, 0.01),          # 명확 부정 → 제외
        ('보다 적극적인 문제 해결 태도', 0.32, 0.30, 0.10),    # 저마진 → 추출
    ])
    items, quar = select_hard_sentences(ev, 10, existing_corr={}, margin=0.05)
    texts = [it['text'] for it in items]
    assert '보다 적극적인 문제 해결 태도' in texts, texts
    assert '업무 능력이 매우 뛰어남' not in texts
    for it in items:
        assert it['status'] == STATUS_AI_PENDING and it['human_decision'] is None
        assert it['ai_reference'] == {'polarity': None, 'confidence': None, 'reason': None}
        assert set(it['key']) == {'db_id', 'sent_idx'}
        assert it['rec_id'] == '%s_%s' % (it['key']['db_id'], it['key']['sent_idx'])
    print('[OK] 하드케이스(저마진/극불일치)만 추출, 명확분 제외, status=1 초기화')


def test_skip_existing_correction():
    ev = _fake_ev(11, [('보다 적극적인 문제 해결 태도', 0.32, 0.30, 0.10)])
    items, _ = select_hard_sentences(ev, 11, existing_corr={'0': 'negative'}, margin=0.05)
    assert items == [], '이미 보정된 문장은 재추출 금지'
    print('[OK] 이미 보정된 문장 제외(중복 판정 방지)')


def test_pii_quarantine():
    ev = _fake_ev(12, [('연락처 010-1234-5678 로 문의', 0.4, 0.45, 0.15)])
    items, quar = select_hard_sentences(ev, 12, existing_corr={}, margin=0.2)
    assert items == [] and quar and quar[0]['pii'], 'PII 문장은 격리(패킷 제외)'
    print('[OK] PII 문장 격리(패킷에 미포함)')


def test_packet_self_describing_no_real_id():
    pk = _packet_skeleton('judge_test', {'batch_id': 'b1'})
    assert pk['_status']['current_stage'] == 'judge'
    j = pk['_stages']['judge']
    assert j['rules'] and 'ai_reference' in j['output_schema'] and 'status' in j['output_schema']
    # 실명/원본 ID 필드가 골격에 없음
    blob = json.dumps(pk, ensure_ascii=False)
    assert 'employee_id' not in blob and 'target_employee' not in blob
    print('[OK] 자기설명 패킷 + 실 ID 없음(가명 안전)')


def test_apply_roundtrip_inmemory():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE evaluations (id INTEGER PRIMARY KEY, sentiment_corrections TEXT DEFAULT '{}')")
    conn.execute("INSERT INTO evaluations (id, sentiment_corrections) VALUES (10, ?)",
                 (json.dumps({'5': 'positive'}),))   # 기존 보정 1건
    conn.commit()
    packet = _packet_skeleton('judge_test', {})
    packet['items'] = [
        {'rec_id': '10_2', 'key': {'db_id': 10, 'sent_idx': 2}, 'text': '...',
         'ai_reference': {'polarity': 'negative', 'confidence': 0.9, 'reason': ''},
         'status': STATUS_AI_READY, 'human_decision': None},                    # AI 확신 → 반영 대상
        {'rec_id': '10_3', 'key': {'db_id': 10, 'sent_idx': 3}, 'text': '...',
         'ai_reference': {'polarity': 'neutral', 'confidence': 0.4, 'reason': ''},
         'status': STATUS_HUMAN_PENDING, 'human_decision': None},               # 사람 게시판 대기
        {'rec_id': '10_4', 'key': {'db_id': 10, 'sent_idx': 4}, 'text': '...',
         'ai_reference': {'polarity': None, 'confidence': None, 'reason': None},
         'status': STATUS_AI_PENDING, 'human_decision': None},                  # 미판정
    ]
    # 1) 집계: 반영은 하지 않고 status 분포만
    summary = apply_judgment_packet(packet, conn=conn)
    assert summary['ai_ready'] == 1 and summary['pending_human'] == 1 \
        and summary['pending_ai'] == 1 and summary['inserted_sentences'] == 0, summary
    # 2) 반영: ai_ready(3) → DB 병합 + status 10 전이
    result = apply_db_to_packet(packet, conn=conn, target='ai')
    assert result['applied_ai'] == 1, result
    stored = json.loads(conn.execute("SELECT sentiment_corrections FROM evaluations WHERE id=10").fetchone()[0])
    assert stored == {'5': 'positive', '2': 'negative'}, stored   # 기존 보존 + 신규 병합
    assert packet['items'][0]['status'] == STATUS_AI_APPLIED
    assert packet['items'][1]['status'] == STATUS_HUMAN_PENDING   # 게시판 대기는 불변
    conn.close()
    print('[OK] 집계/반영 분리 왕복: in-place 병합(기존 보존)·status 전이·미판정 보존')


if __name__ == '__main__':
    test_select_hard_only()
    test_skip_existing_correction()
    test_pii_quarantine()
    test_packet_self_describing_no_real_id()
    test_apply_roundtrip_inmemory()
    print('\n전체 통과')
