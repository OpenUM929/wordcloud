"""20_07 배치 명칭 표시·변경 T1~T4 (계획서 §6).

서버는 기동하지 않는다(DL-12). 라우트 검증은 Flask test_client 로 수행한다.
"""
import pytest


# ---------------------------------------------------------------------------
# T1. 입력 검증 — 한글 차단, 영문 허용, 빈 값(명칭 해제) 허용
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('name', [
    '', None, 'batch A', 'HR-2025_v2', 'Q3 (final)', 'a' * 200,
])
def test_t1_valid_names_pass(name):
    from src.services.batch_manager import validate_display_name
    ok, err = validate_display_name(name)
    assert ok, f"허용돼야 할 이름이 거부됨: {name!r} ({err})"
    assert err is None


@pytest.mark.parametrize('name,reason', [
    ('23년 통합', '한글'),
    ('배치', '한글'),
    ('batch A', '비ASCII 공백'),
    ('emoji ✅', '이모지'),
    ('a\tb', '제어문자'),
])
def test_t1_non_ascii_names_rejected(name, reason):
    from src.services.batch_manager import validate_display_name
    ok, err = validate_display_name(name)
    assert not ok, f"거부돼야 할 이름이 통과됨({reason}): {name!r}"
    assert err


@pytest.mark.parametrize('name', ['a/b', 'a\\b', 'a:b', 'a*b', 'a?b', 'a"b', 'a<b', 'a>b', 'a|b'])
def test_t1_path_hostile_chars_rejected(name):
    from src.services.batch_manager import validate_display_name
    ok, err = validate_display_name(name)
    assert not ok, f"경로 금지문자가 통과됨: {name!r}"
    assert '사용할 수 없는 문자' in err


# ---------------------------------------------------------------------------
# T2. 명칭 정본 읽기 — batch_summary.json 유무에 따른 동작
# ---------------------------------------------------------------------------
def test_t2_read_display_name(processed_dir, write_summary):
    from src.services.batch_manager import read_display_name

    write_summary('batch_20260820_0', 'HR batch A')
    assert read_display_name(processed_dir, 'batch_20260820_0') == 'HR batch A'
    # 파일이 없는 배치 → 빈 문자열(하위 호환: 화면은 batch_id를 그대로 쓴다)
    assert read_display_name(processed_dir, 'batch_없음') == ''
    assert read_display_name(None, 'batch_20260820_0') == ''
    assert read_display_name(processed_dir, None) == ''


# ---------------------------------------------------------------------------
# T3. /api/batch/work-orders 응답에 display_name 이 병합되는지
# ---------------------------------------------------------------------------
def test_t3_work_orders_includes_display_name(processed_dir, write_summary, monkeypatch):
    from flask import Flask
    import src.services.batch_work_order_service as wos
    import src.config.settings as settings
    from src.routes.batch_routes import batch_bp

    write_summary('batch_A', 'named one')
    monkeypatch.setattr(settings, 'PROCESSED_DATA_DIR_PATH', processed_dir)
    monkeypatch.setattr(wos, 'get_all_work_orders',
                        lambda limit=20: [{'batch_id': 'batch_A'}, {'batch_id': 'batch_B'}])

    app = Flask(__name__)
    app.register_blueprint(batch_bp)
    res = app.test_client().get('/api/batch/work-orders')

    assert res.status_code == 200
    data = res.get_json()['data']
    by_id = {d['batch_id']: d for d in data}
    assert by_id['batch_A']['display_name'] == 'named one'
    # 명칭이 없는 작업서는 빈 문자열 — 프론트가 batch_id 로 대체 표시한다
    assert by_id['batch_B']['display_name'] == ''


# ---------------------------------------------------------------------------
# T4. PATCH 라우트 — 한글 거부(400)·영문 저장(200)·정본 파일 반영
#     그룹분석/배치관리 두 화면이 같은 라우트를 쓰므로 여기 검증이 곧 회귀 확인이다.
# ---------------------------------------------------------------------------
def test_t4_patch_route_validates_and_saves(processed_dir, monkeypatch):
    from flask import Flask
    import src.config.settings as settings
    import src.routes.perspective_routes as pr
    from src.services.batch_manager import read_display_name

    monkeypatch.setattr(settings, 'PROCESSED_DATA_DIR_PATH', processed_dir)
    monkeypatch.setattr(pr, '_is_admin', lambda: True)
    monkeypatch.setattr(pr, 'log_action', lambda *a, **kw: None)

    app = Flask(__name__)
    app.register_blueprint(pr.perspective_bp)
    client = app.test_client()

    url = '/api/perspective/batch/batch_A/display-name'

    res_ko = client.patch(url, json={'display_name': '23년 통합'})
    assert res_ko.status_code == 400
    assert res_ko.get_json()['success'] is False
    assert read_display_name(processed_dir, 'batch_A') == '', "거부된 값이 파일에 쓰였음"

    res_en = client.patch(url, json={'display_name': 'merged 23'})
    assert res_en.status_code == 200
    assert res_en.get_json()['success'] is True
    assert read_display_name(processed_dir, 'batch_A') == 'merged 23'

    # 빈 값 = 명칭 해제(하위 호환 — 기존 동작 유지)
    res_clear = client.patch(url, json={'display_name': '  '})
    assert res_clear.status_code == 200
    assert read_display_name(processed_dir, 'batch_A') == ''
