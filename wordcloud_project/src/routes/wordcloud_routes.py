"""Wordcloud generation routes for the WordCloud application."""

from flask import Blueprint, request, jsonify, send_from_directory, session
from src.services.wordcloud_service import (
    regenerate_wordcloud,
    serve_batch_wordcloud
)
from src.config.settings import OUTPUTS_DIR_PATH
from src.modules.word_boost_manager import get_word_boost_manager

wordcloud_bp = Blueprint('wordcloud', __name__, url_prefix='/api/wordcloud')


@wordcloud_bp.route('/regenerate', methods=['POST'])
def regenerate():
    """Regenerate wordcloud with specific parameters."""
    try:
        data = request.json
        result = regenerate_wordcloud(data)
        if isinstance(result, tuple) and len(result) == 2:
            return jsonify(result[0]), result[1]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wordcloud_bp.route('/batch/<batch_name>/word/<path:filename>')
def serve_batch(batch_name, filename):
    """Serve wordcloud file from batch processing."""
    try:
        result = serve_batch_wordcloud(batch_name, filename)
        return result
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wordcloud_bp.route('/outputs/<path:filename>')
def serve_outputs(filename):
    """Serve wordcloud file from outputs directory."""
    try:
        return send_from_directory(OUTPUTS_DIR_PATH, filename)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wordcloud_bp.route('/update_pos', methods=['POST'])
def update_pos():
    """Update wordcloud part-of-speech configuration."""
    try:
        data = request.json
        from src.services.wordcloud_service import update_wordcloud_pos
        result = update_wordcloud_pos(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 단어 가점(Word Boost) CRUD ───────────────────────────────────────────────

@wordcloud_bp.route('/word-boost', methods=['GET'])
def word_boost_list():
    """전체 가점 단어 목록 및 카테고리 반환."""
    try:
        mgr = get_word_boost_manager()
        return jsonify({
            'success': True,
            'boost_words': mgr.get_all(),
            'categories': mgr.get_categories(),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wordcloud_bp.route('/word-boost', methods=['POST'])
def word_boost_add():
    """가점 단어 추가 또는 덮어쓰기. Body: {word, factor, category}"""
    try:
        data = request.get_json(silent=True) or {}
        word = (data.get('word') or '').strip()
        if not word:
            return jsonify({'success': False, 'error': '단어를 입력하세요.'}), 400
        factor = float(data.get('factor', 2.0))
        category = (data.get('category') or '').strip()
        ok = get_word_boost_manager().add(word, factor, category)
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wordcloud_bp.route('/word-boost/<word>', methods=['PUT'])
def word_boost_update(word):
    """가점 단어 배율/활성 수정. Body: {factor?, enabled?, category?}"""
    try:
        data = request.get_json(silent=True) or {}
        factor = float(data['factor']) if 'factor' in data else None
        enabled = bool(data['enabled']) if 'enabled' in data else None
        category = data.get('category')
        ok = get_word_boost_manager().update(word, factor=factor, enabled=enabled,
                                             category=category)
        if not ok:
            return jsonify({'success': False, 'error': '단어를 찾을 수 없습니다.'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wordcloud_bp.route('/word-boost/<word>', methods=['DELETE'])
def word_boost_delete(word):
    """가점 단어 삭제."""
    try:
        ok = get_word_boost_manager().remove(word)
        if not ok:
            return jsonify({'success': False, 'error': '단어를 찾을 수 없습니다.'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500