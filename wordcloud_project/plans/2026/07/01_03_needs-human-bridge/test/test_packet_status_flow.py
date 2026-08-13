# -*- coding: utf-8 -*-
"""0701_03 v2 — status 기반 통합 패킷 흐름 단위테스트 (서버·KoTE 불요).

현행 6-코드 계약(0702_01, DB 반영 버튼 분리):
  1=AI판정대기 · 2=사람판정대기 · 3=AI작업완료 · 4=Human작업완료 · 10=AI DB반영완료 · 11=Human DB반영완료.
  - resolve_item: 레거시 status==3+human_decision 은 4(Human 작업완료)로 승격. 레거시 result 파생.
  - apply_judgment_packet: **DB 반영 완료(10/11)만** corrections 기록. 작업완료(3/4)는 ai_ready/human_ready
    집계만(버튼 대기), 대기(1/2)는 pending 집계.
  - apply_db_to_packet: "DB에 반영" 버튼 — 작업완료 3→10·4→11 로 전이하며 DB 기록.
  - update_packet_decisions: 게시판 저장 → human_decision 기록, 감정3분류→status 4, not_group/skip→status 2.

실행: python test_packet_status_flow.py  (또는 pytest)
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services import judgment_packet_service as jps


def _item(db_id, sent_idx, status, ai_pol=None, human=None):
    return {
        'rec_id': '%s_%s' % (db_id, sent_idx),
        'key': {'db_id': db_id, 'sent_idx': sent_idx},
        'text': 't', 'field': '', 'cur_rule_label': 'neutral',
        'ai_reference': {'polarity': ai_pol, 'confidence': 'low', 'reason': ''},
        'status': status, 'human_decision': human,
    }


class ResolveTest(unittest.TestCase):
    def test_status3_human_promotes_to_4(self):
        # status3 + human_decision 유효 → 4(Human 작업완료), 라벨은 human 우선
        self.assertEqual(jps.resolve_item(_item(1, 0, 3, 'positive', 'negative')), (4, 'negative'))
        # status3 + human 없음 → 3(AI 작업완료), 라벨 = ai_reference.polarity
        self.assertEqual(jps.resolve_item(_item(1, 0, 3, 'positive', None)), (3, 'positive'))
        # 반영완료 상태는 라벨 보유
        self.assertEqual(jps.resolve_item(_item(1, 0, 10, 'positive', None)), (10, 'positive'))
        self.assertEqual(jps.resolve_item(_item(1, 0, 11, 'neutral', 'negative')), (11, 'negative'))
        # 대기 상태는 라벨 없음
        self.assertEqual(jps.resolve_item(_item(1, 0, 2, 'positive')), (2, None))
        self.assertEqual(jps.resolve_item(_item(1, 0, 1)), (1, None))

    def test_legacy_result_derivation(self):
        self.assertEqual(jps.resolve_item({'result': {'needs_human': True}}), (2, None))
        # 레거시 result.label → status 3(AI 작업완료) + 라벨 파생(_final_label 폴백)
        self.assertEqual(jps.resolve_item({'result': {'label': 'positive'}}), (3, 'positive'))
        self.assertEqual(jps.resolve_item({'result': None}), (1, None))


def _conn():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE evaluations (id INTEGER PRIMARY KEY, sentiment_corrections TEXT)')
    conn.execute('INSERT INTO evaluations VALUES (101, ?)', (json.dumps({'5': 'neutral'}),))
    conn.execute('INSERT INTO evaluations VALUES (205, NULL)')
    conn.commit()
    return conn


class ApplyPacketTest(unittest.TestCase):
    """apply_judgment_packet — DB 반영 완료(10/11)만 기록, 나머지는 집계만."""

    def test_only_applied_states_written(self):
        conn = _conn()
        packet = {'items': [
            _item(101, 2, 10, 'positive', None),         # AI 반영완료 → positive 기록
            _item(205, 0, 11, 'neutral', 'negative'),    # Human 반영완료(human 우선) → negative 기록
            _item(205, 1, 3, 'positive'),                # AI 작업완료 → ai_ready(미기록)
            _item(205, 2, 4, 'positive', 'neutral'),     # Human 작업완료 → human_ready(미기록)
            _item(205, 3, 2, 'positive'),                # 사람 대기 → pending_human
            _item(205, 4, 1),                            # AI 대기 → pending_ai
            {'rec_id': 'x', 'key': {}, 'status': 10,     # 반영완료지만 라벨 없음 → skipped
             'ai_reference': {'polarity': None}, 'human_decision': None},
        ]}
        s = jps.apply_judgment_packet(packet, conn=conn)
        self.assertEqual(s['inserted_sentences'], 2)
        self.assertEqual(s['updated_evaluations'], 2)
        self.assertEqual(s['ai_ready'], 1)
        self.assertEqual(s['human_ready'], 1)
        self.assertEqual(s['pending_human'], 1)
        self.assertEqual(s['pending_ai'], 1)
        self.assertEqual(s['skipped'], 1)

        c101 = json.loads(conn.execute(
            'SELECT sentiment_corrections FROM evaluations WHERE id=101').fetchone()[0])
        self.assertEqual(c101, {'5': 'neutral', '2': 'positive'})   # 기존 보존 + 신규
        c205 = json.loads(conn.execute(
            'SELECT sentiment_corrections FROM evaluations WHERE id=205').fetchone()[0])
        self.assertEqual(c205, {'0': 'negative'})                   # human 우선, 3/4/2/1 미반영
        conn.close()


class ApplyDbButtonTest(unittest.TestCase):
    """apply_db_to_packet — "DB에 반영" 버튼: 작업완료 3→10·4→11 전이 + DB 기록."""

    def test_all_target_transitions_and_writes(self):
        conn = _conn()
        packet = {'items': [
            _item(101, 2, 3, 'positive', None),          # AI 작업완료 → 10, positive 기록
            _item(205, 0, 4, 'neutral', 'negative'),     # Human 작업완료 → 11, negative 기록
            _item(205, 1, 2, 'positive'),                # 사람 대기 → 전이/기록 없음
            {'rec_id': 'x', 'key': {}, 'status': 3,      # 라벨 없음 → skipped
             'ai_reference': {'polarity': None}, 'human_decision': None},
        ]}
        r = jps.apply_db_to_packet(packet, conn=conn, target='all')
        self.assertEqual(r['applied_ai'], 1)
        self.assertEqual(r['applied_human'], 1)
        self.assertEqual(r['skipped'], 1)
        by_rec = {it['rec_id']: it for it in packet['items']}
        self.assertEqual(by_rec['101_2']['status'], 10)             # 3 → 10
        self.assertEqual(by_rec['205_0']['status'], 11)             # 4 → 11
        self.assertEqual(by_rec['205_1']['status'], 2)              # 불변

        c101 = json.loads(conn.execute(
            'SELECT sentiment_corrections FROM evaluations WHERE id=101').fetchone()[0])
        self.assertEqual(c101, {'5': 'neutral', '2': 'positive'})
        c205 = json.loads(conn.execute(
            'SELECT sentiment_corrections FROM evaluations WHERE id=205').fetchone()[0])
        self.assertEqual(c205, {'0': 'negative'})
        conn.close()

    def test_target_ai_only(self):
        conn = _conn()
        packet = {'items': [
            _item(101, 2, 3, 'positive', None),          # AI 작업완료
            _item(205, 0, 4, 'neutral', 'negative'),     # Human 작업완료 → target=ai 이면 제외
        ]}
        r = jps.apply_db_to_packet(packet, conn=conn, target='ai')
        self.assertEqual(r['applied_ai'], 1)
        self.assertEqual(r['applied_human'], 0)
        by_rec = {it['rec_id']: it for it in packet['items']}
        self.assertEqual(by_rec['101_2']['status'], 10)             # 전이됨
        self.assertEqual(by_rec['205_0']['status'], 4)              # 미전이(target=ai)
        # Human 작업완료분은 DB 미기록
        c205 = conn.execute('SELECT sentiment_corrections FROM evaluations WHERE id=205').fetchone()[0]
        self.assertIn(c205, (None, '{}'))
        conn.close()


class UpdatePacketTest(unittest.TestCase):
    def test_board_save_writes_decision_and_status(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'pkt.json')
        packet = {
            '_status': {'counts': {}}, '_stages': {'x': 1},   # 봉투(보존 확인)
            'items': [_item(1, 0, 2, 'positive'), _item(1, 1, 2, 'negative'),
                      _item(2, 0, 2, None)],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(packet, f, ensure_ascii=False)

        found = jps.update_packet_decisions(path, [
            {'rec_id': '1_0', 'decision': 'neutral'},     # 감정 → status 4(Human 작업완료)
            {'rec_id': '1_1', 'decision': 'not_group'},   # 그룹아님 → status 2 유지
        ])
        self.assertEqual(found, 2)
        out = json.load(open(path, encoding='utf-8'))
        by_rec = {it['rec_id']: it for it in out['items']}
        self.assertEqual(by_rec['1_0']['human_decision'], 'neutral')
        self.assertEqual(by_rec['1_0']['status'], 4)       # 감정 3분류 → Human 작업완료(DB 반영 대기)
        self.assertEqual(by_rec['1_1']['human_decision'], 'not_group')
        self.assertEqual(by_rec['1_1']['status'], 2)       # 감정 3분류 아님 → 사람대기 유지
        self.assertEqual(by_rec['2_0']['status'], 2)       # 미선택 행 불변
        self.assertIn('_stages', out)                      # 봉투 보존
        self.assertEqual(out['_status']['counts']['human_decided'], 1)

        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
