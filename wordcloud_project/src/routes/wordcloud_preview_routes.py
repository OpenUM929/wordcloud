"""Wordcloud preview page routes."""

from flask import Blueprint, render_template

wordcloud_preview_bp = Blueprint('wordcloud_preview', __name__)


@wordcloud_preview_bp.route('/wordcloud-preview')
def wordcloud_preview():
    return render_template('wordcloud_preview.html')
