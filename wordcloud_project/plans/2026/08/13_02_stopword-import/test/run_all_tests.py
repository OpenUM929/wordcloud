#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
불용어 CSV/엑셀 일괄 등록 — 백엔드 검증 스크립트 (T1~T11 + 이름/일반 분리 확인).

서버를 기동하지 않는다(DL-12). Flask 라우트 검증은 app.test_client() 로
in-process 디스패치만 사용한다(소켓을 열지 않음).

실행:
    <venv>/Scripts/python.exe run_all_tests.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
# test -> 13_02_stopword-import -> 08 -> 2026 -> plans -> wordcloud_project
APP_ROOT = os.path.abspath(os.path.join(TEST_DIR, '..', '..', '..', '..', '..'))
sys.path.insert(0, APP_ROOT)
os.chdir(APP_ROOT)

REAL_GENERAL = os.path.join(APP_ROOT, 'src', 'configs', 'stopwords.json')
REAL_NAMES = os.path.join(APP_ROOT, 'src', 'configs', 'stopwords_names.json')

PY = sys.executable

RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    status = 'PASS' if ok else 'FAIL'
    print(f'[{status}] {name}' + (f' - {detail}' if detail else ''))


def make_isolated_manager(tmp_dir, seed_categories=None):
    """격리된 임시 설정 경로로 StopwordManager 를 만든다. settings 모듈의
    STOPWORDS_CONFIG_PATH / STOPWORDS_NAMES_CONFIG_PATH 를 이 테스트 동안만
    임시 경로로 바꿔치기한다(프로세스 전역 — 순차 실행 전제)."""
    import src.config.settings as settings_mod
    general_path = os.path.join(tmp_dir, 'stopwords.json')
    names_path = os.path.join(tmp_dir, 'stopwords_names.json')
    settings_mod.STOPWORDS_CONFIG_PATH = general_path
    settings_mod.STOPWORDS_NAMES_CONFIG_PATH = names_path

    if seed_categories is not None:
        cfg = {
            "module_name": "stopword_manager",
            "description": "test fixture",
            "categories": seed_categories,
            "settings": {
                "ignore_comments": True, "normalize_case": True,
                "min_word_length": 1, "max_word_length": 10
            }
        }
        with open(general_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False)

    from src.modules.stopword_manager import StopwordManager
    mgr = StopwordManager(config_path=general_path)
    return mgr, general_path, names_path


# ─────────────────────────────────────────────────────────────────────────
# T1 — 경로 고정 (3-CWD)
# ─────────────────────────────────────────────────────────────────────────
def test_t1():
    subproc_script = os.path.join(tempfile.mkdtemp(prefix='wc_t1_script_'), 'probe.py')
    with open(subproc_script, 'w', encoding='utf-8') as f:
        f.write(
            "import sys, os, json\n"
            "sys.path.insert(0, os.environ['WC_APP_ROOT'])\n"
            "from src.config.settings import STOPWORDS_CONFIG_PATH\n"
            "from src.modules.stopword_manager import get_stopword_manager\n"
            "mgr = get_stopword_manager()\n"
            "print(json.dumps({\n"
            "    'resolved': os.path.abspath(STOPWORDS_CONFIG_PATH),\n"
            "    'mgr_path': os.path.abspath(mgr.config_path),\n"
            "    'categories': len(mgr.get_all_categories()),\n"
            "    'words': len(mgr.get_all_stopwords()),\n"
            "    'cwd': os.getcwd(),\n"
            "}))\n"
        )

    other_dir = tempfile.mkdtemp(prefix='wc_t1_cwd_')
    cwds = [APP_ROOT, os.path.join(APP_ROOT, 'src'), other_dir]

    # 정답값은 StopwordManager 의 실제 중복 제거 로직(카테고리 간 dedup)을 그대로
    # 재사용해서 구한다 — 원본 JSON 카테고리별 words 를 단순 합산하면 카테고리 간
    # 중복 단어(예: "이"가 여러 카테고리에 존재)가 이중 계산돼 어긋난다.
    from src.modules.stopword_manager import StopwordManager
    gt_mgr = StopwordManager(config_path=REAL_GENERAL)
    gt_categories = len(gt_mgr.get_all_categories())
    gt_words = len(gt_mgr.get_all_stopwords())

    outs = []
    for cwd in cwds:
        env = dict(os.environ)
        env['WC_APP_ROOT'] = APP_ROOT
        env['PYTHONIOENCODING'] = 'utf-8'
        proc = subprocess.run(
            [PY, subproc_script], cwd=cwd, env=env,
            capture_output=True, text=True, encoding='utf-8', timeout=60
        )
        if proc.returncode != 0:
            record('T1 경로 고정(3-CWD)', False, f'cwd={cwd} 서브프로세스 실패: {proc.stderr[-800:]}')
            return
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception as e:
            record('T1 경로 고정(3-CWD)', False, f'cwd={cwd} 출력 파싱 실패: {e} / stdout={proc.stdout!r}')
            return
        outs.append(data)

    resolved_set = {o['resolved'] for o in outs}
    mgr_path_set = {o['mgr_path'] for o in outs}
    cat_set = {o['categories'] for o in outs}
    word_set = {o['words'] for o in outs}

    ok = (
        len(resolved_set) == 1 and len(mgr_path_set) == 1 and
        resolved_set == mgr_path_set and
        len(cat_set) == 1 and len(word_set) == 1 and
        list(cat_set)[0] == gt_categories and list(word_set)[0] == gt_words and
        os.path.abspath(REAL_GENERAL) in resolved_set
    )
    detail = f'resolved={resolved_set}, categories={cat_set}(기대 {gt_categories}), words={word_set}(기대 {gt_words})'
    record('T1 경로 고정(3-CWD)', ok, detail)


# ─────────────────────────────────────────────────────────────────────────
# T2 — UTF-8 CSV 임포트 (이름 20건, 머리글 있음)
# ─────────────────────────────────────────────────────────────────────────
def _make_name_rows(n, prefix='이름'):
    return [f'{prefix}{i:03d}철수' for i in range(n)]


def test_t2():
    from src.services.file_parser import parse_csv_with_encoding
    names = _make_name_rows(20)
    csv_text = '이름\n' + '\n'.join(names) + '\n'
    df, encoding = parse_csv_with_encoding(csv_text.encode('utf-8'), 'names.csv')
    if df is None:
        record('T2 UTF-8 CSV 임포트', False, 'parse_csv_with_encoding 이 UTF-8 을 못 읽음')
        return

    tmp = tempfile.mkdtemp(prefix='wc_t2_')
    mgr, general_path, names_path = make_isolated_manager(tmp)
    raw_words = df.iloc[:, 0].tolist()
    result = mgr.add_stopwords_bulk(raw_words, category='인명', dry_run=False, target='names')

    ok = (result['total'] == 20 and result['added'] == 20 and
          result['duplicated'] == 0 and result['invalid'] == 0 and
          os.path.exists(names_path) and not os.path.exists(general_path))
    record('T2 UTF-8 CSV 임포트(이름 20건)', ok, f'encoding={encoding}, result={result if not ok else "OK"}')


# ─────────────────────────────────────────────────────────────────────────
# T3 — CP949(엑셀 기본) CSV
# ─────────────────────────────────────────────────────────────────────────
def test_t3():
    from src.services.file_parser import parse_csv_with_encoding
    names = _make_name_rows(20, prefix='업무단어')
    csv_text = '단어\n' + '\n'.join(names) + '\n'
    df, encoding = parse_csv_with_encoding(csv_text.encode('cp949'), 'words.csv')
    if df is None:
        record('T3 CP949 CSV 임포트', False, 'parse_csv_with_encoding 이 CP949 를 못 읽음')
        return

    tmp = tempfile.mkdtemp(prefix='wc_t3_')
    mgr, general_path, names_path = make_isolated_manager(tmp)
    raw_words = df.iloc[:, 0].tolist()
    result = mgr.add_stopwords_bulk(raw_words, category='기타', dry_run=False, target='general')

    ok = (result['total'] == 20 and result['added'] == 20 and
          result['duplicated'] == 0 and result['invalid'] == 0 and
          os.path.exists(general_path) and not os.path.exists(names_path) and
          encoding in ('cp949', 'euc-kr', 'cp932'))
    record('T3 CP949 CSV 임포트', ok, f'encoding={encoding}, result={result if not ok else "OK"}')


# ─────────────────────────────────────────────────────────────────────────
# T4 — 중복·무효 혼재
# ─────────────────────────────────────────────────────────────────────────
def test_t4():
    tmp = tempfile.mkdtemp(prefix='wc_t4_')
    seed = [{"name": "기타", "words": ["가나다", "라마바", "사아자"]}]
    mgr, general_path, names_path = make_isolated_manager(tmp, seed_categories=seed)

    words = ["가나다", "라마바", "사아자", "ㄱ", "ㄴ", "", "새단어1", "새단어2"]
    result = mgr.add_stopwords_bulk(words, category='기타', dry_run=False, target='general')

    ok = (result['total'] == 8 and result['duplicated'] == 3 and
          result['invalid'] == 3 and result['added'] == 2 and
          set(result['duplicated_words']) == {"가나다", "라마바", "사아자"} and
          set(result['added_words']) == {"새단어1", "새단어2"})
    record('T4 중복·무효 혼재', ok, f'result={result}')


# ─────────────────────────────────────────────────────────────────────────
# T5 — dry_run 무변경
# ─────────────────────────────────────────────────────────────────────────
def test_t5():
    tmp = tempfile.mkdtemp(prefix='wc_t5_')
    seed = [{"name": "기타", "words": ["기존단어"]}]
    mgr, general_path, names_path = make_isolated_manager(tmp, seed_categories=seed)

    with open(general_path, 'rb') as f:
        before = f.read()

    result = mgr.add_stopwords_bulk(["새단어A", "새단어B"], category='기타', dry_run=True, target='general')

    with open(general_path, 'rb') as f:
        after = f.read()

    unchanged_file = (before == after)
    unchanged_memory = not mgr.is_stopword('새단어A') and not mgr.is_stopword('새단어B')

    # 재로드해도 원본만 있어야 함
    from src.modules.stopword_manager import StopwordManager
    reloaded = StopwordManager(config_path=general_path)
    reload_ok = ('새단어A' not in reloaded.get_all_stopwords() and
                 '새단어B' not in reloaded.get_all_stopwords() and
                 '기존단어' in reloaded.get_all_stopwords())

    ok = (result['added'] == 2 and unchanged_file and unchanged_memory and reload_ok)
    record('T5 dry_run 무변경', ok,
           f'result={result}, file_unchanged={unchanged_file}, mem_unchanged={unchanged_memory}, reload_ok={reload_ok}')


# ─────────────────────────────────────────────────────────────────────────
# T6 — 저장 1회
# ─────────────────────────────────────────────────────────────────────────
def test_t6():
    # 일반 저장 카운트
    tmp = tempfile.mkdtemp(prefix='wc_t6a_')
    mgr, general_path, names_path = make_isolated_manager(tmp)
    counter = {'n': 0}
    original_save = mgr.save_stopwords

    def wrapped_save(*a, **kw):
        counter['n'] += 1
        return original_save(*a, **kw)
    mgr.save_stopwords = wrapped_save

    words = [f'대량단어{i:03d}' for i in range(50)]
    result_general = mgr.add_stopwords_bulk(words, category='기타', dry_run=False, target='general')
    general_ok = (counter['n'] == 1 and result_general['added'] == 50)

    # 이름 저장 카운트
    tmp2 = tempfile.mkdtemp(prefix='wc_t6b_')
    mgr2, general_path2, names_path2 = make_isolated_manager(tmp2)
    counter2 = {'n': 0}
    original_save_names = mgr2._save_names_stopwords

    def wrapped_save_names(*a, **kw):
        counter2['n'] += 1
        return original_save_names(*a, **kw)
    mgr2._save_names_stopwords = wrapped_save_names

    names_list = [f'김직원{i:03d}' for i in range(50)]
    result_names = mgr2.add_stopwords_bulk(names_list, category='인명', dry_run=False, target='names')
    names_ok = (counter2['n'] == 1 and result_names['added'] == 50)

    ok = general_ok and names_ok
    record('T6 저장 1회(단어수 무관)', ok,
           f'general_saves={counter["n"]}, names_saves={counter2["n"]}, '
           f'general_added={result_general["added"]}, names_added={result_names["added"]}')


# ─────────────────────────────────────────────────────────────────────────
# T7 — 조회 성능 (set vs list)
# ─────────────────────────────────────────────────────────────────────────
def test_t7():
    tmp = tempfile.mkdtemp(prefix='wc_t7_')
    mgr, general_path, names_path = make_isolated_manager(tmp)

    NAMES_COUNT = 5000
    names_list = [f'성명{ i:05d}김철수' for i in range(NAMES_COUNT)]
    result = mgr.add_stopwords_bulk(names_list, category='인명', dry_run=False, target='names')
    if result['added'] != NAMES_COUNT:
        record('T7 조회 성능(set vs list)', False, f'사전 등록 실패: {result}')
        return

    import random
    random.seed(42)
    hits = random.choices(names_list, k=60000)
    misses = [f'없는단어{i:06d}xyz' for i in range(40000)]
    queries = hits + misses
    random.shuffle(queries)
    SET_ITERS = len(queries)  # 100,000

    t0 = time.perf_counter()
    hit_count = 0
    for w in queries:
        if mgr.is_stopword(w):
            hit_count += 1
    t_set = time.perf_counter() - t0

    # 예전 방식(list 순차 탐색) 비교 — 100,000회는 너무 오래 걸려 20,000회로 축소.
    old_list = list(mgr.all_stopwords)
    LIST_ITERS = 20000
    list_queries = queries[:LIST_ITERS]
    t0 = time.perf_counter()
    for w in list_queries:
        _ = w.strip() in old_list
    t_list = time.perf_counter() - t0

    per_call_set_us = (t_set / SET_ITERS) * 1e6
    per_call_list_us = (t_list / LIST_ITERS) * 1e6
    speedup = per_call_list_us / per_call_set_us if per_call_set_us > 0 else float('inf')

    ok = (hit_count == len(hits) and t_set < 3.0 and speedup > 3)
    record('T7 조회 성능(set vs list)', ok,
           f'set: {SET_ITERS}회/{t_set:.3f}s ({per_call_set_us:.2f}us/call) | '
           f'list: {LIST_ITERS}회/{t_list:.3f}s ({per_call_list_us:.2f}us/call) | '
           f'speedup={speedup:.1f}x | hit_count={hit_count}(기대 {len(hits)})')


# ─────────────────────────────────────────────────────────────────────────
# T8 — 이름 제거 실효 (nlp_analysis 경로) — 실 싱글톤·실 파일 사용, 백업/복원
# ─────────────────────────────────────────────────────────────────────────
def test_t8():
    backup_general = None
    backup_names = None
    names_existed = os.path.exists(REAL_NAMES)
    try:
        with open(REAL_GENERAL, 'rb') as f:
            backup_general = f.read()
        if names_existed:
            with open(REAL_NAMES, 'rb') as f:
                backup_names = f.read()

        subproc_script = os.path.join(tempfile.mkdtemp(prefix='wc_t8_script_'), 'probe.py')
        with open(subproc_script, 'w', encoding='utf-8') as f:
            f.write(
                "import sys, os, json\n"
                "sys.path.insert(0, os.environ['WC_APP_ROOT'])\n"
                "from src.modules.stopword_manager import get_stopword_manager\n"
                "mgr = get_stopword_manager()\n"
                "add_result = mgr.add_stopwords_bulk(['홍길동'], category='인명', dry_run=False, target='names')\n"
                "from src.config.settings import NLP_CONFIG_PATH\n"
                "from src.modules.nlp_analysis import NLPAnalysis\n"
                "analyzer = NLPAnalysis(config_path=NLP_CONFIG_PATH)\n"
                "res = analyzer.analyze('홍길동이 보고서를 작성했다')\n"
                "meaningful = res['analysis'].get('meaningful_words', [])\n"
                "print(json.dumps({'add_result': add_result, 'meaningful_words': meaningful}))\n"
            )
        env = dict(os.environ)
        env['WC_APP_ROOT'] = APP_ROOT
        env['PYTHONIOENCODING'] = 'utf-8'
        proc = subprocess.run([PY, subproc_script], cwd=APP_ROOT, env=env,
                               capture_output=True, text=True, encoding='utf-8', timeout=120)
        if proc.returncode != 0:
            record('T8 이름 제거 실효(nlp_analysis)', False, f'서브프로세스 실패: {proc.stderr[-1500:]}')
            return
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        meaningful = data['meaningful_words']
        add_result = data['add_result']
        ok = (add_result.get('added') == 1 and '홍길동' not in meaningful)
        record('T8 이름 제거 실효(nlp_analysis)', ok,
               f'add_result={add_result}, meaningful_words={meaningful}')
    finally:
        if backup_general is not None:
            with open(REAL_GENERAL, 'wb') as f:
                f.write(backup_general)
        if names_existed and backup_names is not None:
            with open(REAL_NAMES, 'wb') as f:
                f.write(backup_names)
        elif not names_existed and os.path.exists(REAL_NAMES):
            os.remove(REAL_NAMES)


# ─────────────────────────────────────────────────────────────────────────
# T9 — 텍스트 통째 필터 한계 (R-4, 사실 기록)
# ─────────────────────────────────────────────────────────────────────────
def test_t9():
    tmp = tempfile.mkdtemp(prefix='wc_t9_')
    mgr, general_path, names_path = make_isolated_manager(tmp)
    mgr.add_stopword('홍길동', '인명')
    mgr.save_stopwords()

    text = '홍길동이 보고서를 작성했다'
    filtered = mgr.filter_stopwords(text)

    # 한계 확인: 공백 분리 필터라 "홍길동이"(조사 결합) 는 그대로 남는다.
    limitation_confirmed = ('홍길동이' in filtered)
    # 반대로 순수 "홍길동" 단독 토큰은 정상 제거되는지도 같이 확인.
    filtered2 = mgr.filter_stopwords('홍길동 보고서 작성')
    pure_token_removed = ('홍길동' not in filtered2.split())

    ok = limitation_confirmed and pure_token_removed
    record('T9 filter_stopwords 한계(R-4)', ok,
           f'filtered="{filtered}" (조사결합형 잔존 확인), filtered2="{filtered2}" (순수토큰 제거 확인)')


# ─────────────────────────────────────────────────────────────────────────
# T10/T11/추가 분리검증 — 라우트(app.test_client()) 기반, 공유 격리 컨텍스트
# ─────────────────────────────────────────────────────────────────────────
def _build_test_client():
    import src.config.settings as settings_mod
    tmp = tempfile.mkdtemp(prefix='wc_route_')
    general_path = os.path.join(tmp, 'stopwords.json')
    names_path = os.path.join(tmp, 'stopwords_names.json')
    settings_mod.STOPWORDS_CONFIG_PATH = general_path
    settings_mod.STOPWORDS_NAMES_CONFIG_PATH = names_path

    from flask import Flask
    from src.routes.api_routes import api_bp
    app = Flask(__name__)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.testing = True
    return app.test_client(), general_path, names_path


def test_t10(client):
    import pandas as pd
    names = _make_name_rows(20, prefix='엑셀이름')
    df = pd.DataFrame({'이름': names})
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine='openpyxl')
    buf.seek(0)

    resp = client.post('/api/stopwords/import', data={
        'file': (buf, 'names.xlsx'),
        'target': 'names',
        'mode': 'commit',
    }, content_type='multipart/form-data')

    ok = False
    detail = ''
    if resp.status_code == 200:
        body = resp.get_json()
        ok = (body.get('success') and body.get('added') == 20 and
              body.get('duplicated') == 0 and body.get('invalid') == 0)
        detail = f'status=200, body={body}'
    else:
        detail = f'status={resp.status_code}, body={resp.get_data(as_text=True)[:500]}'
    record('T10 엑셀 20건 업로드', ok, detail)


def test_t11(client):
    all_ok = True
    details = []

    # (a) 확장자 미지원
    resp = client.post('/api/stopwords/import', data={
        'file': (io.BytesIO(b'a\nb\n'), 'names.txt'),
        'target': 'general', 'mode': 'preview',
    }, content_type='multipart/form-data')
    ok_a = (resp.status_code == 400)
    all_ok &= ok_a
    details.append(f'.txt 확장자: status={resp.status_code} ok={ok_a}')

    # (b) 빈 파일
    resp = client.post('/api/stopwords/import', data={
        'file': (io.BytesIO(b''), 'empty.csv'),
        'target': 'general', 'mode': 'preview',
    }, content_type='multipart/form-data')
    ok_b = (resp.status_code == 400)
    all_ok &= ok_b
    details.append(f'빈 파일: status={resp.status_code} ok={ok_b}')

    # (c) 100MB 초과
    big = io.BytesIO(b'word\n' + b'a\n' * 1 + os.urandom(0))
    big_content = ('word\n' + '\n'.join(['x'] * 5)).encode('utf-8')
    # 실제로 100MB+1 바이트를 채운다.
    filler = b'a,b\n' * (1024 * 1024)  # ~4MB per rep
    reps_needed = (100 * 1024 * 1024) // len(filler) + 2
    huge = io.BytesIO(filler * reps_needed)
    size_mb = huge.getbuffer().nbytes / (1024 * 1024)
    resp = client.post('/api/stopwords/import', data={
        'file': (huge, 'huge.csv'),
        'target': 'general', 'mode': 'preview',
    }, content_type='multipart/form-data')
    ok_c = (resp.status_code == 400)
    all_ok &= ok_c
    details.append(f'100MB 초과({size_mb:.1f}MB): status={resp.status_code} ok={ok_c}')

    # (d) target='general' + category='인명' 조합 거부
    resp = client.post('/api/stopwords/import', data={
        'file': (io.BytesIO('단어\n가나다라\n'.encode('utf-8')), 'w.csv'),
        'target': 'general', 'category': '인명', 'mode': 'preview',
    }, content_type='multipart/form-data')
    ok_d = (resp.status_code == 400)
    all_ok &= ok_d
    details.append(f"general+인명 조합: status={resp.status_code} ok={ok_d}")

    record('T11 잘못된 파일/입력', bool(all_ok), ' | '.join(details))


def test_extra_separation(client):
    """이름 업로드/일반 업로드가 서로 다른 파일에 저장되고, is_stopword 는
    합쳐서 조회되는지 확인 (신규 요구사항 — 계획서 표에는 없음)."""
    import src.config.settings as settings_mod

    name_words = ['김철수', '이영희']
    resp1 = client.post('/api/stopwords/import', data={
        'file': (io.BytesIO(('이름\n' + '\n'.join(name_words)).encode('utf-8')), 'n.csv'),
        'target': 'names', 'mode': 'commit',
    }, content_type='multipart/form-data')

    gen_words = ['프로젝트관리', '분기보고서']
    resp2 = client.post('/api/stopwords/import', data={
        'file': (io.BytesIO(('단어\n' + '\n'.join(gen_words)).encode('utf-8')), 'g.csv'),
        'target': 'general', 'category': '기타', 'mode': 'commit',
    }, content_type='multipart/form-data')

    general_path = settings_mod.STOPWORDS_CONFIG_PATH
    names_path = settings_mod.STOPWORDS_NAMES_CONFIG_PATH

    with open(general_path, 'r', encoding='utf-8') as f:
        general_cfg = json.load(f)
    with open(names_path, 'r', encoding='utf-8') as f:
        names_cfg = json.load(f)

    general_all = {w for c in general_cfg['categories'] for w in c['words']}
    names_all = {w for c in names_cfg['categories'] for w in c['words']}

    separation_ok = (
        set(name_words) <= names_all and set(name_words).isdisjoint(general_all) and
        set(gen_words) <= general_all and set(gen_words).isdisjoint(names_all)
    )

    from src.modules.stopword_manager import get_stopword_manager
    mgr = get_stopword_manager()
    union_query_ok = all(mgr.is_stopword(w) for w in name_words + gen_words)

    ok = (resp1.status_code == 200 and resp2.status_code == 200 and
          separation_ok and union_query_ok)
    record('추가: 이름/일반 파일 분리 + is_stopword 합집합 조회', ok,
           f'resp1={resp1.status_code}, resp2={resp2.status_code}, '
           f'separation_ok={separation_ok}, union_query_ok={union_query_ok}, '
           f'general_all={sorted(general_all)}, names_all={sorted(names_all)}')


def test_route_reject_names_category_in_general():
    """target=general 인데 category=인명 이면 add_stopwords_bulk 도 ValueError 로 막는지
    (라우트뿐 아니라 모듈 계층에서도 방어) 재확인."""
    tmp = tempfile.mkdtemp(prefix='wc_reject_')
    mgr, general_path, names_path = make_isolated_manager(tmp)
    try:
        mgr.add_stopwords_bulk(['아무개'], category='인명', dry_run=True, target='general')
        ok = False
        detail = '예외가 발생하지 않음'
    except ValueError as e:
        ok = True
        detail = str(e)
    record('모듈 계층: general+인명 조합 ValueError', ok, detail)


def main():
    print(f'APP_ROOT = {APP_ROOT}')
    print(f'REAL_GENERAL = {REAL_GENERAL} (exists={os.path.exists(REAL_GENERAL)})')
    print(f'REAL_NAMES = {REAL_NAMES} (exists={os.path.exists(REAL_NAMES)})')
    print('=' * 70)

    # T1은 실 파일을 읽기만 하므로 가장 먼저 실행 (다른 테스트의 settings 패치 영향 없음)
    test_t1()
    test_t2()
    test_t3()
    test_t4()
    test_t5()
    test_t6()
    test_t7()
    test_t9()
    test_route_reject_names_category_in_general()

    # 라우트(app.test_client) 기반 — 프로세스 내 싱글톤을 처음이자 유일하게 초기화
    client, general_path, names_path = _build_test_client()
    test_t10(client)
    test_t11(client)
    test_extra_separation(client)

    # T8은 실제 싱글톤·실제 설정 파일 경로를 써야 하므로 반드시 별도 서브프로세스로
    # 실행한다(이 프로세스의 싱글톤은 이미 위에서 임시 경로로 굳어졌기 때문).
    test_t8()

    print('=' * 70)
    n_pass = sum(1 for _, ok, _ in RESULTS if ok)
    n_total = len(RESULTS)
    print(f'결과: {n_pass}/{n_total} PASS')
    for name, ok, detail in RESULTS:
        if not ok:
            print(f'  [FAIL] {name}: {detail}')
    sys.exit(0 if n_pass == n_total else 1)


if __name__ == '__main__':
    main()
