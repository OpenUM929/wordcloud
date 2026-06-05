"""공통 테스트 라우트 — 모든 테스트 유형이 동일한 API 규격으로 실행/결과 반환."""

import os
import json
from flask import Blueprint, request, jsonify

from src.modules.test_framework import TestRunner, TestCase

# ── executors (테스트 유형별 실제 분석 함수) ────────────────────────────

def _exec_profanity(text: str, params: dict) -> dict:
    """욕설 필터 executor. 검토 보고서 수정#2 반영: detected 키 정규화."""
    from src.modules.profanity_filter import advanced_filter_profanity
    raw = advanced_filter_profanity(text)
    return {
        **raw,
        # 테스트케이스 비교용 정규화 키 추가
        "detected": len(raw.get("detected_profanity", [])) > 0,
    }

def _exec_sentiment(text: str, params: dict) -> dict:
    """감정 분석 executor."""
    from src.modules.emotion_analysis import analyze_emotion
    from src.services.perspective_service import sentence_sentiment_override, has_contrastive
    from src.modules.text_preprocessing import split_sentences

    sentences = split_sentences(text)
    total = len(sentences)
    sent_results = []
    for i, sent in enumerate(sentences):
        is_last = (i == total - 1)
        result = analyze_emotion(sent)
        scores = result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})
        pos = scores.get('positive', 0.0) or 0.0
        neg = scores.get('negative', 0.0) or 0.0
        neutral = scores.get('neutral', 0.0) or 0.0
        corrected_score = sentence_sentiment_override(
            pos, neg, sent, is_last, total,
            threshold=params.get('threshold', 0.20),
            weight=params.get('weight', 2.0),
            neutral=neutral
        )
        if corrected_score > 0:
            label = 'positive'
        elif corrected_score < 0:
            label = 'negative'
        else:
            label = 'neutral'
        sent_results.append({
            'text': sent,
            'pos': round(pos, 4),
            'neg': round(neg, 4),
            'neutral': round(neutral, 4),
            'corrected_score': round(corrected_score, 4),
            'result': label,
            'is_last': is_last,
            'has_contrast': has_contrastive(sent),
        })
    return {
        'sentences': sent_results,
        'sentence_count': total,
        'detected': True,  # 항상 True (감정은 항상 분석됨)
    }

# ── test case persistence ──────────────────────────────────────────────

_TEST_CASES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'configs', 'test_cases')
os.makedirs(_TEST_CASES_DIR, exist_ok=True)

def _get_cases_path(test_type: str) -> str:
    return os.path.join(_TEST_CASES_DIR, f"{test_type}_cases.json")

def _load_cases(test_type: str) -> list:
    path = _get_cases_path(test_type)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_cases(test_type: str, cases: list):
    path = _get_cases_path(test_type)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

# ── blueprint ──────────────────────────────────────────────────────────

test_bp = Blueprint('test', __name__)

_EXECUTORS = {
    'profanity': _exec_profanity,
    'sentiment': _exec_sentiment,
}

@test_bp.route('/api/test/run', methods=['POST'])
def api_test_run():
    """단일 테스트 실행."""
    data = request.get_json(silent=True) or {}
    test_type = data.get('test_type')
    text = data.get('text', '')
    params = data.get('params', {})

    if not test_type or test_type not in _EXECUTORS:
        return jsonify({'success': False, 'error': f'Unknown test_type: {test_type}'}), 400
    if not text:
        return jsonify({'success': False, 'error': 'text is required'}), 400

    try:
        runner = TestRunner(test_type, _EXECUTORS[test_type])
        result = runner.run_single(text, **params)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@test_bp.route('/api/test/batch', methods=['POST'])
def api_test_batch():
    """배치 테스트 실행."""
    data = request.get_json(silent=True) or {}
    test_type = data.get('test_type')
    cases_raw = data.get('cases', [])
    params = data.get('params', {})

    if not test_type or test_type not in _EXECUTORS:
        return jsonify({'success': False, 'error': f'Unknown test_type: {test_type}'}), 400
    if not cases_raw:
        return jsonify({'success': False, 'error': 'cases is required'}), 400

    try:
        cases = [TestCase(**c) for c in cases_raw]
        runner = TestRunner(test_type, _EXECUTORS[test_type])
        result = runner.run_batch(cases, **params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@test_bp.route('/api/test/cases/<test_type>', methods=['GET'])
def api_test_cases_get(test_type):
    """테스트케이스 목록 조회."""
    try:
        cases = _load_cases(test_type)
        return jsonify({'success': True, 'test_type': test_type, 'cases': cases})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@test_bp.route('/api/test/cases/<test_type>', methods=['POST'])
def api_test_cases_post(test_type):
    """테스트케이스 추가/수정."""
    data = request.get_json(silent=True) or {}
    case_id = data.get('id')
    if not case_id:
        return jsonify({'success': False, 'error': 'id is required'}), 400

    try:
        cases = _load_cases(test_type)
        # 동일 ID가 있으면 교체, 없으면 추가
        idx = next((i for i, c in enumerate(cases) if c['id'] == case_id), None)
        if idx is not None:
            cases[idx] = data
        else:
            cases.append(data)
        _save_cases(test_type, cases)
        return jsonify({'success': True, 'message': f'Case {case_id} saved'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@test_bp.route('/api/test/cases/<test_type>/<case_id>', methods=['DELETE'])
def api_test_cases_delete(test_type, case_id):
    """테스트케이스 삭제."""
    try:
        cases = _load_cases(test_type)
        new_cases = [c for c in cases if c['id'] != case_id]
        if len(new_cases) == len(cases):
            return jsonify({'success': False, 'error': f'Case {case_id} not found'}), 404
        _save_cases(test_type, new_cases)
        return jsonify({'success': True, 'message': f'Case {case_id} deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
