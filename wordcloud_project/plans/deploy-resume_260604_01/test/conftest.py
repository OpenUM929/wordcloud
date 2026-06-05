import os
import sys
import tempfile
import pytest

# Ensure project root is on path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from web.app import create_app


@pytest.fixture(scope='session')
def app():
    """Flask application instance for the test session."""
    _app = create_app()
    _app.config['TESTING'] = True
    return _app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def admin_client(client):
    """Flask test client with admin session."""
    with client.session_transaction() as sess:
        sess['admin_logged_in'] = True
    return client


@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch):
    """Patch deploy_session_service to use a temporary SQLite DB."""
    from src.services import deploy_session_service as dss
    original_db_path = dss._DB_PATH
    db_file = str(tmp_path / "test_deploy_sessions.db")
    monkeypatch.setattr(dss, '_DB_PATH', db_file)
    dss._init_db()
    yield db_file
    # Restore original path
    monkeypatch.setattr(dss, '_DB_PATH', original_db_path)


@pytest.fixture
def reset_pseudo_mgr(monkeypatch):
    """Reset the global PseudonymManager singleton before each test."""
    import src.services.perspective_service as ps
    monkeypatch.setattr(ps, '_pseudo_mgr_instance', None)
    yield
    monkeypatch.setattr(ps, '_pseudo_mgr_instance', None)


@pytest.fixture
def tmp_mappings_path(tmp_path):
    """Temporary path for pseudonym mappings file."""
    return str(tmp_path / "test_pseudonym_mappings.enc")
