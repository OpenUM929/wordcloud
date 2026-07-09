"""save_acquired_sentences_bulk 단위 테스트 (임시 sqlite, KoTE 불요)."""
import os, sys, json, sqlite3, tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

import src.services.perspective_service as ps

# v5 + v7 컬럼 포함 임시 acquired_sentences 테이블 생성 → _get_acq_conn 패치
_TMP = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
_TMP.close()
_DB = _TMP.name

DDL = """
CREATE TABLE acquired_sentences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence_text TEXT NOT NULL,
    user_label  TEXT CHECK(user_label  IN ('positive','negative','neutral')),
    model_label TEXT CHECK(model_label IN ('positive','negative','neutral')),
    confidence REAL DEFAULT 0.0,
    source_employee_id TEXT DEFAULT '',
    source_evaluation_id TEXT DEFAULT '',
    source_batch_id TEXT DEFAULT '',
    sentence_index INTEGER DEFAULT 0,
    db_id INTEGER DEFAULT 0,
    context TEXT DEFAULT '',
    memo TEXT DEFAULT '',
    analysis_results TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    kote_pos REAL, kote_neg REAL, kote_neutral REAL, override_score REAL,
    source_kind TEXT DEFAULT '',
    UNIQUE(sentence_text, source_evaluation_id, sentence_index)
);
"""
_c = sqlite3.connect(_DB); _c.executescript(DDL); _c.commit(); _c.close()


def _conn():
    return sqlite3.connect(_DB)


ps._get_acq_conn = _conn  # 패치


def _rows():
    c = _conn()
    r = c.execute("SELECT sentence_text,user_label,model_label,kote_pos,kote_neg,kote_neutral,override_score,source_kind,analysis_results FROM acquired_sentences ORDER BY id").fetchall()
    c.close()
    return r


def test_basic_insert_with_kote():
    items = [
        {'sentence_text': '목표의식 강화가 돋보입니다.', 'user_label': 'positive', 'model_label': 'neutral',
         'source_evaluation_id': 'V1', 'sentence_index': 0, 'source_kind': 'group_emotion',
         'kote_pos': 0.31, 'kote_neg': 0.02, 'kote_neutral': 0.67, 'override_score': 1.0},
        {'sentence_text': '보고가 미흡합니다.', 'user_label': 'negative', 'model_label': 'negative',
         'source_evaluation_id': 'V1', 'sentence_index': 1, 'source_kind': 'group_emotion',
         'kote_pos': 0.01, 'kote_neg': 0.95, 'kote_neutral': 0.04, 'override_score': -1.0},
    ]
    res = ps.save_acquired_sentences_bulk(items)
    assert res['inserted'] == 2 and res['skipped'] == 0, res
    rows = _rows()
    assert rows[0][3] == 0.31 and rows[0][6] == 1.0     # kote_pos / override_score 보존
    assert rows[0][7] == 'group_emotion'
    print('[OK] 기본 적재 + KoTE 값 보존')


def test_profanity_item():
    items = [{
        'sentence_text': '이건 욕설이 아닌데 잡혔다', 'user_label': 'neutral', 'model_label': 'neutral',
        'source_evaluation_id': 'EV9', 'sentence_index': 0, 'source_kind': 'group_profanity',
        'analysis_results': {'is_profanity': True, 'detected_words': ['씨']},
    }]
    res = ps.save_acquired_sentences_bulk(items)
    assert res['inserted'] == 1, res
    row = [r for r in _rows() if r[7] == 'group_profanity'][0]
    ar = json.loads(row[8])
    assert ar['is_profanity'] is True and ar['detected_words'] == ['씨']
    print('[OK] 욕설 항목 source_kind/analysis_results 적재')


def test_dup_skip_and_overwrite():
    base = {'sentence_text': '중복 테스트 문장', 'user_label': 'positive', 'model_label': 'positive',
            'source_evaluation_id': 'D1', 'sentence_index': 0, 'override_score': 0.5}
    r1 = ps.save_acquired_sentences_bulk([base])
    assert r1['inserted'] == 1
    r2 = ps.save_acquired_sentences_bulk([base])               # 중복 → skip
    assert r2['inserted'] == 0 and r2['skipped'] == 1, r2
    over = dict(base, user_label='negative', override_score=-0.5)
    r3 = ps.save_acquired_sentences_bulk([over], overwrite=True)  # 덮어쓰기
    assert r3['inserted'] == 1, r3
    row = [r for r in _rows() if r[0] == '중복 테스트 문장'][0]
    assert row[1] == 'negative' and row[6] == -0.5
    print('[OK] 중복 skip + overwrite 동작')


def test_label_normalize_and_empty():
    items = [
        {'sentence_text': '한글라벨', 'user_label': '긍정', 'model_label': '중립', 'source_evaluation_id': 'K1'},
        {'sentence_text': '   ', 'user_label': 'positive'},   # 빈 문장 → 건너뜀
    ]
    res = ps.save_acquired_sentences_bulk(items)
    assert res['inserted'] == 1, res
    assert any('비어있음' in e for e in res['errors'])
    row = [r for r in _rows() if r[0] == '한글라벨'][0]
    assert row[1] == 'positive' and row[2] == 'neutral'
    print('[OK] 라벨 정규화 + 빈 문장 가드')


if __name__ == '__main__':
    try:
        test_basic_insert_with_kote()
        test_profanity_item()
        test_dup_skip_and_overwrite()
        test_label_normalize_and_empty()
        print('\n전체 통과')
    finally:
        os.unlink(_DB)
