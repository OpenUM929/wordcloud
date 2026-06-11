"""UI routes for the WordCloud application."""

from flask import Blueprint, render_template, jsonify, request
from src.config.settings import NLP_CONFIG_PATH
import json

ui_bp = Blueprint('ui', __name__)


@ui_bp.route('/')
def index():
    """Home page."""
    return render_template('index.html')


@ui_bp.route('/settings')
def settings():
    """Settings page."""
    from src.services.metadata_service import load_config
    
    current_config = load_config()
    from src.config.settings import EMOTION_NAMES
    return render_template(
        'settings.html',
        emotions=EMOTION_NAMES,
        config=current_config,
        emotions_json=json.dumps(EMOTION_NAMES, separators=(',', ':')),
        config_json=json.dumps(current_config, separators=(',', ':'))
    )


@ui_bp.route('/results')
def results():
    """Results page."""
    try:
        with open(NLP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            nlp_config = json.load(f)
        wordcloud_pos = nlp_config.get('wordcloud_pos', ['Noun'])
    except:
        wordcloud_pos = ['Noun']
    
    return render_template('results.html', wordcloud_pos=wordcloud_pos)


@ui_bp.route('/preprocess')
def preprocess():
    """Preprocess page."""
    return render_template('preprocess.html')


@ui_bp.route('/sarcasm')
def sarcasm():
    """Sarcasm analysis page."""
    return render_template('sarcasm.html')


@ui_bp.route('/metadata')
def metadata():
    """Metadata page."""
    return render_template('metadata.html')


@ui_bp.route('/metadata_batch')
def metadata_batch():
    """Batch metadata page."""
    return render_template('metadata_batch.html')


@ui_bp.route('/get_batch_list')
def get_batch_list_api():
    """API to get list of batches."""
    try:
        from src.services.metadata_service import get_batch_list
        
        batches = get_batch_list()
        return jsonify({'batches': batches})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ui_bp.route('/get_batch_metadata')
def get_batch_metadata_api():
    """API to get metadata for a specific batch."""
    try:
        from src.services.metadata_service import get_batch_metadata
        
        batch_path = request.args.get('path')
        if not batch_path:
            return jsonify({'error': 'Batch path is required'}), 400
            
        metadata = get_batch_metadata(batch_path)
        return jsonify({'metadata': metadata})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ui_bp.route('/wordcloud')
def wordcloud():
    """Wordcloud page with metadata information."""
    try:
        from src.services.metadata_service import get_batch_list
        
        batches = get_batch_list()
        return render_template('wordcloud.html', batches=batches)
    except Exception as e:
        return render_template('wordcloud.html', batches=[])


@ui_bp.route('/stopwords')
def stopwords():
    """Stopwords management page."""
    return render_template('stopwords.html')


@ui_bp.route('/wordcloud_debug')
def wordcloud_debug():
    """Debug page for wordcloud issues."""
    return render_template('wordcloud_debug.html')


@ui_bp.route('/perspective_test')
def perspective_test():
    """Test page for perspective/group analysis."""
    return render_template('perspective_test.html')


@ui_bp.route('/profanity-list')
def profanity_list():
    """Admin page for company-wide profanity list."""
    return render_template('profanity_list.html')


@ui_bp.route('/sentiment-test')
def sentiment_test():
    """Sentence-level sentiment override test page."""
    return render_template('sentiment_test.html')


@ui_bp.route('/profanity-test')
def profanity_test():
    """Profanity filter test page."""
    return render_template('profanity_test.html')


@ui_bp.route('/deploy-gallery')
def deploy_gallery():
    """Deployment gallery page for viewing saved images."""
    return render_template('deploy_gallery.html')


@ui_bp.route('/acquired-data')
def acquired_data():
    """Acquired corpus data page."""
    return render_template('acquired_data.html')
