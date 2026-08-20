"""20_05 다운로드 모드 로드 스코프 T1~T3 (계획서 §6).

프론트 동작(체크박스 전용 선택·진행률 게이지)은 브라우저 검증(PND) 대상이라
여기서는 프론트가 의존하는 **서버 측 계약**을 검증한다:
  - date_from/date_to 로 로드 범위를 실제로 줄일 수 있는가(§3.1의 전제)
  - all=1 슬림 페이로드에 이미지 JSON이 섞여 들어오지 않는가(§2 (2)의 전제)
"""


# ---------------------------------------------------------------------------
# T1. date_from 스코프 — 기본값(최근 N개월) 축소가 서버에서 실제로 동작하는지
# ---------------------------------------------------------------------------
def test_t1_date_from_narrows_scope(gallery_db, add_entry):
    from src.services.gallery_db_service import list_entries

    add_entry('old1', '20250101_1000')
    add_entry('old2', '20250630_1000')
    add_entry('new1', '20260819_1000')
    add_entry('new2', '20260820_0930')

    full = list_entries(fetch_all=True, is_admin=True)
    assert full['total'] == 4

    scoped = list_entries(fetch_all=True, date_from='20260601', is_admin=True)
    assert {e['id'] for e in scoped['entries']} == {'new1', 'new2'}
    assert scoped['total'] == 2, "total 도 필터 기준이어야 화면 표시가 일관된다"

    # 경계 포함 여부(>=) — 시작일 당일 항목은 포함되어야 한다
    boundary = list_entries(fetch_all=True, date_from='20260819', is_admin=True)
    assert {e['id'] for e in boundary['entries']} == {'new1', 'new2'}


# ---------------------------------------------------------------------------
# T2. 전체 기간 조회로 되돌리기 — 파라미터 생략 시 예전 항목이 다시 보인다
#     ("데이터가 사라졌다" 오인 방지 경로, §7 R-1)
# ---------------------------------------------------------------------------
def test_t2_expanding_scope_restores_old_entries(gallery_db, add_entry):
    from src.services.gallery_db_service import list_entries

    add_entry('old1', '20240101_1000')
    add_entry('new1', '20260820_1000')

    scoped = list_entries(fetch_all=True, date_from='20260601', is_admin=True)
    assert {e['id'] for e in scoped['entries']} == {'new1'}

    expanded = list_entries(fetch_all=True, is_admin=True)
    assert {e['id'] for e in expanded['entries']} == {'old1', 'new1'}


# ---------------------------------------------------------------------------
# T3. 슬림 페이로드 유지 — 다운로드 모드 목록에 이미지 JSON이 실리지 않는다
# ---------------------------------------------------------------------------
def test_t3_fetch_all_payload_is_slim(gallery_db, add_entry):
    from src.services.gallery_db_service import list_entries

    add_entry('e1', '20260820_1000')
    entries = list_entries(fetch_all=True, is_admin=True)['entries']

    assert len(entries) == 1
    keys = set(entries[0].keys())
    assert 'images' not in keys and 'row_results' not in keys, \
        "슬림 페이로드에 이미지 JSON이 섞이면 로딩 축소 효과가 사라진다"
    assert {'id', 'employee_id', 'timestamp', 'source'} <= keys


# ---------------------------------------------------------------------------
# T4. 비관리자에게는 원데이터 모드 항목이 노출되지 않는다(스코프 변경 후에도 유지)
# ---------------------------------------------------------------------------
def test_t4_non_admin_scope_still_hides_real_mode(gallery_db, add_entry):
    from src.services.gallery_db_service import list_entries

    add_entry('real1', '20260820_1000', output_mode='real')
    add_entry('pseudo1', '20260820_1100', output_mode='pseudonym')

    scoped = list_entries(fetch_all=True, date_from='20260801', is_admin=False)
    assert {e['id'] for e in scoped['entries']} == {'pseudo1'}
