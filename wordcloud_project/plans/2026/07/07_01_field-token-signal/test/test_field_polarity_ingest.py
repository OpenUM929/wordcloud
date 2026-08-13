# -*- coding: utf-8 -*-
"""0707_01 Phase2 — 장점/단점 문서 필드 수집 분리·전파 단위테스트.

_extract_rows_from_chunk:
  - 극성 문서 필드 미매핑이면 기존 단일 evaluation_document(하위호환).
  - evaluation_document_strength/weakness 매핑 시 필드마다 별도 레코드 + evaluation_document_field 부착.
  - 빈 극성 컬럼은 레코드 생략.
select_hard_sentences: evaluation_document_field → 문장 item field 상속(간접 계약 확인).

서버·GPU 불요. 실행: python plans/2026/0707_01_field-token-signal/test/test_field_polarity_ingest.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

import pandas as pd  # noqa: E402
from src.services.batch_processor import _extract_rows_from_chunk  # noqa: E402


def _rows(df, mappings):
    # 가명화 없이(_pseudo_mgr=None) 원데이터 유지 경로로 계약만 검증
    return [json.loads(j) for _, j in _extract_rows_from_chunk(df, 'emp', mappings, None, [])]


def test_legacy_single_document():
    df = pd.DataFrame([{'emp': 'A', '평가문': '협업이 좋았다'}])
    mappings = {'target_employee_id': 'emp', 'evaluation_document': '평가문'}
    recs = _rows(df, mappings)
    assert len(recs) == 1, recs
    assert recs[0]['evaluation_document'] == '협업이 좋았다'
    assert 'evaluation_document_field' not in recs[0], '레거시엔 극성 필드 없어야'
    print('OK legacy_single_document')


def test_polarity_split_two_fields():
    # 케이스 ①: 장점·단점 필드 둘 다 매핑 → 별도 레코드 2개, 각기 극성 태그
    df = pd.DataFrame([{'emp': 'A', '장점칸': '주도적이다', '단점칸': '보고가 늦다'}])
    mappings = {
        'target_employee_id': 'emp',
        'evaluation_document_strength': '장점칸',
        'evaluation_document_weakness': '단점칸',
    }
    recs = _rows(df, mappings)
    assert len(recs) == 2, recs
    by_field = {r['evaluation_document_field']: r['evaluation_document'] for r in recs}
    assert by_field == {'장점': '주도적이다', '단점': '보고가 늦다'}, by_field
    print('OK polarity_split_two_fields')


def test_single_polarity_field_only():
    # 케이스 ②③: 장점 필드만 매핑 → 단일 극성 레코드
    df = pd.DataFrame([{'emp': 'A', '장점칸': '성실함'}])
    mappings = {
        'target_employee_id': 'emp',
        'evaluation_document_strength': '장점칸',
    }
    recs = _rows(df, mappings)
    assert len(recs) == 1, recs
    assert recs[0]['evaluation_document_field'] == '장점'
    assert recs[0]['evaluation_document'] == '성실함'
    print('OK single_polarity_field_only')


def test_empty_polarity_column_skipped():
    # 극성 필드가 매핑됐어도 셀이 비면 그 레코드 생략(반대편만 남음)
    df = pd.DataFrame([{'emp': 'A', '장점칸': '성실함', '단점칸': ''}])
    mappings = {
        'target_employee_id': 'emp',
        'evaluation_document_strength': '장점칸',
        'evaluation_document_weakness': '단점칸',
    }
    recs = _rows(df, mappings)
    assert len(recs) == 1, recs
    assert recs[0]['evaluation_document_field'] == '장점'
    print('OK empty_polarity_column_skipped')


def test_shared_metadata_copied_to_both():
    df = pd.DataFrame([{'emp': 'A', '부서': '영업', '장점칸': 'x', '단점칸': 'y'}])
    mappings = {
        'target_employee_id': 'emp',
        'evaluator_department': '부서',
        'evaluation_document_strength': '장점칸',
        'evaluation_document_weakness': '단점칸',
    }
    recs = _rows(df, mappings)
    assert len(recs) == 2
    assert all(r.get('evaluator_department') == '영업' for r in recs), recs
    print('OK shared_metadata_copied_to_both')


if __name__ == '__main__':
    test_legacy_single_document()
    test_polarity_split_two_fields()
    test_single_polarity_field_only()
    test_empty_polarity_column_skipped()
    test_shared_metadata_copied_to_both()
    print('\nALL PASS')
