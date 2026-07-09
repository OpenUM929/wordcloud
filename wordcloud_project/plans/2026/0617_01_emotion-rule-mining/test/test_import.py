"""CSV 업로드(import) 파서 단위 테스트 (DB·KoTE 불요)."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import _parse_acq_import_rows, _normalize_acq_label

BOM = '﻿'


def test_label_normalize():
    assert _normalize_acq_label('positive') == 'positive'
    assert _normalize_acq_label('긍정') == 'positive'
    assert _normalize_acq_label('부정') == 'negative'
    assert _normalize_acq_label('중립') == 'neutral'
    assert _normalize_acq_label('NEG') == 'negative'      # 대소문자
    assert _normalize_acq_label('') == 'neutral'           # 미지정 → default
    assert _normalize_acq_label('garbage') == 'neutral'    # 미인식 → default
    assert _normalize_acq_label('', default='positive') == 'positive'
    print('[OK] 라벨 정규화 (한글/영문/대소문자/default)')


def test_parse_refined_csv():
    """정제 CSV(24컬럼, BOM 포함) 일부를 파싱."""
    csv_text = (
        BOM + 'id,sentence_text,user_label,kote_pos,kote_neg,kote_neutral,raw_model_label,'
        'applied_rule,corrected_label,override_score,kote_vs_truth,pipeline_vs_truth,'
        'rule_helped,rule_hurt,is_last,total_sentences,model_label_at_capture,'
        'confidence_at_capture,source_employee_id,source_evaluation_id,source_batch_id,'
        'sentence_index,context,created_at\n'
        '7,"성실하지만 보고가 미흡합니다.",negative,0.01,0.99,0.0,negative,rule2_contrast_lasthigh,'
        'negative,-1.0,correct,correct,False,False,True,2,negative,0.98,E001,V123,B9,1,'
        '"업무 태도는 좋습니다. 성실하지만 보고가 미흡합니다.",2026-06-15 20:00:00\n'
    )
    rows, errors = _parse_acq_import_rows(csv_text)
    assert errors == [], errors
    assert len(rows) == 1
    r = rows[0]
    assert r['sentence_text'] == '성실하지만 보고가 미흡합니다.'
    assert r['user_label'] == 'negative'
    assert r['model_label'] == 'negative'        # model_label_at_capture는 매핑 안 함 → user_label fallback
    assert r['confidence'] == 0.98               # confidence_at_capture 사용
    assert r['source_evaluation_id'] == 'V123'
    assert r['sentence_index'] == 1
    assert '업무 태도는 좋습니다' in r['context']
    print('[OK] 정제 CSV 파싱 + confidence_at_capture/위치/컨텍스트')


def test_parse_basic_csv_korean_label():
    """기본 CSV + 한글 라벨 + user_label 누락 행."""
    csv_text = (
        'sentence_text,user_label,model_label,confidence,sentence_index\n'
        '목표의식 강화가 돋보입니다.,긍정,중립,0.3,0\n'
        ',긍정,긍정,0.1,0\n'                              # sentence_text 빈 행 → 건너뜀
        '책임감이 강합니다.,,,0,0\n'                        # user_label 누락 → neutral
    )
    rows, errors = _parse_acq_import_rows(csv_text)
    assert len(rows) == 2, (rows, errors)
    assert any('비어있음' in e for e in errors)
    assert rows[0]['user_label'] == 'positive'
    assert rows[0]['model_label'] == 'neutral'
    assert rows[1]['sentence_text'] == '책임감이 강합니다.'
    assert rows[1]['user_label'] == 'neutral'             # 누락 → default
    print('[OK] 기본 CSV + 한글 라벨 + 빈문장/누락 처리')


def test_missing_required_column():
    rows, errors = _parse_acq_import_rows('foo,bar\n1,2\n')
    assert rows == []
    assert any('sentence_text' in e for e in errors)
    rows, errors = _parse_acq_import_rows('')
    assert rows == [] and errors == ['빈 파일']
    print('[OK] 필수컬럼 누락/빈 파일 가드')


if __name__ == '__main__':
    test_label_normalize()
    test_parse_refined_csv()
    test_parse_basic_csv_korean_label()
    test_missing_required_column()
    print('\n전체 통과')
