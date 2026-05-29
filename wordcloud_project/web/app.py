"""WordCloud Application - Main Flask app entry point."""

import sys
import os
import locale
from sys import path

# UTF-8 encoding settings for Windows
if sys.platform == 'win32':
    import _locale
    _locale._getdefaultlocale = (lambda *args: ['ko_KR', 'utf-8'])

# Set default encoding
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Add project root to path
path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_from_directory, session
import json
import uuid
import hashlib
from datetime import datetime
import torch

# Load environment variables
load_dotenv()

# Configuration
from src.config.settings import (
    SECRET_KEY,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT
)

# Import blueprints
from src.routes.ui_routes import ui_bp
from src.routes.metadata_routes import metadata_bp
from src.routes.batch_routes import batch_bp
from src.routes.wordcloud_routes import wordcloud_bp
from src.routes.api_routes import api_bp
from src.routes.perspective_routes import perspective_bp
from src.routes.admin_routes import admin_bp

# One-time migration: old batch_summary (full data) → users/*.json + lightweight summaries
from src.services.user_data_manager import migrate_from_old_format
_migrate_result = migrate_from_old_format()
if _migrate_result.get('migrated'):
    print(f"[Migration] 기존 배치 데이터를 users/*.json으로 변환 완료: "
          f"{_migrate_result['batches_migrated']}개 배치, "
          f"{_migrate_result['employees_migrated']}명, "
          f"{_migrate_result['evaluations_migrated']}건 평가")
elif _migrate_result.get('reason'):
    print(f"[Migration] {_migrate_result['reason']}")


def create_app():
    """Create and configure Flask application instance."""
    app = Flask(__name__, 
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
                static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'static')))
    
    # Configuration
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['JSON_AS_ASCII'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
    
    # Register blueprints
    app.register_blueprint(ui_bp)
    app.register_blueprint(metadata_bp)
    app.register_blueprint(batch_bp)
    app.register_blueprint(wordcloud_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(perspective_bp)
    app.register_blueprint(admin_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """404 error handler."""
        return jsonify({'success': False, 'error': 'Not Found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """500 error handler."""
        print("Internal server error:", str(error))
        import traceback
        print("Stack trace:", traceback.format_exc())
        return jsonify({'success': False, 'error': 'Internal Server Error'}), 500
    
    # Serve outputs directories
    @app.route('/outputs/<path:filename>')
    def serve_outputs(filename):
        outputs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../outputs'))
        return send_from_directory(outputs_dir, filename)

    @app.route('/outputs/유저/<path:filename>')
    def serve_user_outputs(filename):
        user_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../outputs/유저'))
        return send_from_directory(user_dir, filename)

    @app.route('/outputs/배포/<path:filename>')
    def serve_deploy_outputs(filename):
        deploy_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../outputs/배포'))
        return send_from_directory(deploy_dir, filename)
    
    return app


if __name__ == '__main__':
    """Run the Flask application."""
    app = create_app()
    
    # Load models before running (optional, can be loaded lazily)
    print("=== WordCloud Application ===")
    print(f"Debug: {FLASK_DEBUG}")
    print(f"Host: {FLASK_HOST}")
    print(f"Port: {FLASK_PORT}")
    print("===============================")
    
    app.run(
        debug=FLASK_DEBUG,
        host=FLASK_HOST,
        port=FLASK_PORT,
        threaded=True
    )