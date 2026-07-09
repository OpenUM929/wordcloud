# -*- coding: utf-8 -*-
"""0623_01 판정 패킷 추출 — 마진 밴드 태깅 + save_packet_file 경로 안전 (서버·KoTE 불요).

검증:
  1) _margin_band: gap → 0.05/0.10/0.15 밴드 분류.
  2) select_hard_sentences: item에 gap·margin_band(저마진은 밴드, pol_flip은 'flip') 부여.
  3) save_packet_file: 고정 루트에 기록·경로 탈출 차단(라벨 sanitize, 루트 이탈 없음).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

import src.services.judgment_packet_service as jp
from src.services.judgment_packet_service import (
    select_hard_sentences, _margin_band, save_packet_file, _MARGIN_BANDS, _packet_skeleton,
)


def _fake_ev(db_id, sentences):
    """sentence_emotion_cache 주입 가짜 평가(KoTE 재실행 불요)."""
    doc = '. '.join(s[0] for s in sentences)
    cache = [{'sentence': s[0], 'pos': s[1], 'neg': s[2], 'neutral': s[3]} for s in sentences]
    return {'_db_id': db_id, 'evaluation_document': doc, 'sentence_emotion_cache': cache}


def test_margin_band_classify():
    assert _margin_band(0.01) == '0.05'      # < 0.05
    assert _margin_band(0.07) == '0.10'      # 0.05 ≤ gap < 0.10
    assert _margin_band(0.12) == '0.15'      # 0.10 ≤ gap < 0.15
    assert _margin_band(0.30) == '0.15'      # 모든 밴드 초과 → 최대 밴드
    print('[OK] _margin_band: gap → 밴드 분류')


def test_item_gap_and_band():
    # 저마진 3종(각 밴드) + 명확 긍정(제외). 가장 넓은 밴드(0.15)로 추출.
    ev = _fake_ev(10, [
        ('아주 미세하게 긍정인 문장', 0.50, 0.48, 0.02),   # gap 0.02 → 0.05
        ('약간 애매한 문장입니다', 0.50, 0.43, 0.07),       # gap 0.07 → 0.10
        ('조금 더 기운 문장이다', 0.55, 0.43, 0.02),        # gap 0.12 → 0.15
        ('업무 능력이 매우 뛰어남', 0.95, 0.01, 0.04),      # gap 0.94 → 제외(하드 아님)
    ])
    items, _ = select_hard_sentences(ev, 10, existing_corr={}, margin=max(_MARGIN_BANDS))
    bands = {it['text']: it['margin_band'] for it in items}
    assert bands.get('아주 미세하게 긍정인 문장') == '0.05', bands
    assert bands.get('약간 애매한 문장입니다') == '0.10', bands
    assert bands.get('조금 더 기운 문장이다') == '0.15', bands
    assert '업무 능력이 매우 뛰어남' not in bands, '명확 긍정은 하드 아님 → 제외'
    for it in items:
        assert 'gap' in it and isinstance(it['gap'], float)
    print('[OK] item gap·margin_band 부여(저마진 밴드 분류, 명확분 제외)')


def test_band_values_and_flip_invariant():
    # 확실한 저마진(gap 0.04)으로 선택 보장 + 밴드/플립 불변식 검증.
    ev = _fake_ev(11, [('판단이 어려운 경계 문장입니다', 0.50, 0.46, 0.04)])
    items, _ = select_hard_sentences(ev, 11, existing_corr={}, margin=max(_MARGIN_BANDS))
    assert items, '저마진(gap<0.15) 문장은 하드케이스로 잡혀야 함'
    for it in items:
        # 밴드는 유효 집합 + hard 종류와 정합(pol_flip ↔ 'flip')
        assert it['margin_band'] in ('flip', '0.05', '0.10', '0.15'), it['margin_band']
        assert (it['hard'] == 'pol_flip') == (it['margin_band'] == 'flip'), it
    print('[OK] 밴드 유효집합 + pol_flip↔flip 불변식')


def test_save_packet_file_path_safe(tmp_root=None):
    # 임시 루트로 교체(실 데이터셋 폴더 오염 방지).
    tmp = tempfile.mkdtemp(prefix='jp_test_')
    orig = jp._judgment_root
    jp._judgment_root = lambda: tmp
    try:
        packet = _packet_skeleton('judge_test', {'batch_id': 'b1'})
        packet['items'] = [{'key': {'db_id': 1, 'sent_idx': 0}, 'text': '가명 문장', 'result': None}]

        # 정상 경로
        path = save_packet_file(packet, 'mylabel', 'batch_20260623_0')
        assert os.path.isfile(path)
        assert os.path.abspath(path).startswith(os.path.abspath(tmp) + os.sep)
        loaded = json.load(open(path, encoding='utf-8'))
        assert loaded['items'][0]['text'] == '가명 문장'

        # 경로 탈출 시도 라벨 → sanitize 되어 루트 안에 머무름
        path2 = save_packet_file(packet, '../../etc', '../../../evil')
        assert os.path.abspath(path2).startswith(os.path.abspath(tmp) + os.sep), path2
        print('[OK] save_packet_file: 기록·로드 왕복 + 경로 탈출 차단(sanitize)')
    finally:
        jp._judgment_root = orig
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    test_margin_band_classify()
    test_item_gap_and_band()
    test_band_values_and_flip_invariant()
    test_save_packet_file_path_safe()
    print('\n전체 통과')
