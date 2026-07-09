// 신규 그룹 gold 검토 — 게시판(표). 키보드 ↑↓ 이동·1~4 판정, 💾 배치 저장(원자적). 0624_05.
(function () {
    'use strict';
    function $(id) { return document.getElementById(id); }
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    // 원천 텍스트에 남은 HTML 엔티티(&nbsp; &#46776; 등)를 실제 글자로 복원(표시용).
    // textarea 파싱은 스크립트 실행 없이 rcdata로만 디코드 → 결과를 다시 esc()해 안전 주입.
    var _dec = document.createElement('textarea');
    function decodeEntities(s) {
        if (s == null) { return ''; }
        _dec.innerHTML = String(s);
        return _dec.value;
    }
    var API = '/api/perspective/group-review';
    var PAGE = 100;
    var state = { file: '', all: [], view: [], page: 0, total: 0, undecidedOnly: true, cursor: 0 };

    function toast(msg) {
        var t = $('grToast'); t.textContent = msg; t.classList.add('show');
        setTimeout(function () { t.classList.remove('show'); }, 1800);
    }

    function sortFiles(files, mode) {
        var arr = files.slice();
        arr.sort(function (a, b) {
            if (mode === 'name_asc') { return a.name.localeCompare(b.name); }
            if (mode === 'name_desc') { return b.name.localeCompare(a.name); }
            var ma = a.mtime || 0, mb = b.mtime || 0;
            return (mode === 'date_asc') ? (ma - mb) : (mb - ma);  // 기본 date_desc(최신 먼저)
        });
        return arr;
    }

    function renderFileOptions() {
        var sel = $('grFile');
        var cur = sel.value;                                  // 선택 유지
        var mode = ($('grSort') || {}).value || 'date_desc';
        sel.innerHTML = '<option value="">— 검토 파일 선택 —</option>';
        sortFiles(state.files || [], mode).forEach(function (f) {
            var o = document.createElement('option');
            var dec = (f.decided != null) ? f.decided : 0;
            var tot = (f.total != null) ? f.total : (f.rows != null ? f.rows : 0);
            o.value = f.name; o.textContent = f.name + ' (' + dec + '/' + tot + ')';  // 판정/전체
            sel.appendChild(o);
        });
        sel.value = cur;
    }

    function loadFiles(done) {
        fetch(API + '/files').then(function (r) { return r.json(); }).then(function (j) {
            if (!j.success) { return; }
            state.files = j.files || [];
            renderFileOptions();
            if (typeof done === 'function') { done(); }   // 목록 완성 후(자동선택 등)
        });
    }

    function loadFile(name) {
        state.file = name; state.all = []; state.page = 0; state.cursor = 0;
        if (!name) { render(); refreshApplyDb(); return; }
        fetch(API + '/load?file=' + encodeURIComponent(name) + '&limit=100000')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j.success) { alert(j.error || '로드 실패'); return; }
                state.total = j.total;
                state.all = j.items.map(function (it) { it.pending = null; return it; });
                applyFilter(); state.cursor = 0; render();
                refreshApplyDb();   // Human 작업완료(status 4) 건수 → "DB에 반영" 버튼
            });
    }

    // 선택 파일(판정 패킷)의 Human 작업완료(status 4) 건수로 "DB에 반영" 버튼 노출·활성화
    function refreshApplyDb() {
        var btn = $('grApplyDb');
        if (!state.file) { btn.style.display = 'none'; btn.disabled = true; return; }
        fetch('/api/perspective/judgment/packets')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j || !j.success) { return; }
                var p = (j.packets || []).filter(function (x) { return x.name === state.file; })[0];
                var cnt = p ? (p.human_ready || 0) : 0;
                if (cnt > 0) {
                    btn.style.display = 'inline-block'; btn.disabled = false;
                    btn.textContent = '💾 DB에 반영 (Human ' + cnt + '건)';
                } else {
                    btn.style.display = 'none'; btn.disabled = true;
                }
            }).catch(function () {});
    }

    function applyDb() {
        if (!state.file) { return; }
        var btn = $('grApplyDb');
        btn.disabled = true; var prev = btn.textContent; btn.textContent = '반영 중…';
        fetch('/api/perspective/judgment/apply-db', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file: state.file, target: 'human' })   // group_review는 Human분(4)만
        }).then(function (r) { return r.json(); }).then(function (j) {
            if (!j || j.success !== true) {
                btn.disabled = false; btn.textContent = prev;
                alert((j && j.error) || 'DB 반영 실패'); return;
            }
            var s = j.summary || {};
            toast('DB 반영 완료 (Human ' + (s.applied_human || 0) + '건)');
            loadFile(state.file);   // 재로드(반영분 status 11 → 목록/버튼 갱신)
        }).catch(function () {
            btn.disabled = false; btn.textContent = prev; alert('DB 반영 중 오류가 발생했습니다.');
        });
    }

    function autoSelectPresetFile() {
        var params = new URLSearchParams(window.location.search);
        var preset = params.get('file') || sessionStorage.getItem('gr_preset_file');
        if (!preset) { return; }
        sessionStorage.removeItem('gr_preset_file');
        var sel = $('grFile');
        var match = false;
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].value === preset) { match = true; break; }
        }
        if (match) { sel.value = preset; loadFile(preset); }   // 목록에 있을 때만
    }

    // 미판정만: 로드/토글 시에만 적용(저장 직후엔 유지해 "사라짐" 방지)
    function applyFilter() {
        state.view = state.undecidedOnly
            ? state.all.filter(function (it) { return it.decision == null; })
            : state.all;
        if (state.cursor >= state.view.length) { state.cursor = Math.max(0, state.view.length - 1); }
        state.page = Math.floor(state.cursor / PAGE);
    }

    function chosen(it) { return it.pending != null ? it.pending : it.decision; }
    function dirtyList() { return state.all.filter(function (it) { return it.pending != null && it.pending !== it.decision; }); }

    var POL_KO = { positive: '긍', negative: '부', neutral: '중', not_group: '노그' };
    function polSpan(pol) {
        if (!pol) { return '<span class="sub">—</span>'; }
        return '<span class="pol ' + esc(pol) + '">' + (POL_KO[pol] || esc(pol)) + '</span>';
    }
    // 알고리즘 결과(ai_reference): 규칙엔진 산출 극성·신뢰도·발동규칙(참고). Claude 생각이 아니다.
    function algoRef(ref) {
        if (!ref || !ref.polarity) { return '<span class="sub">—</span>'; }
        return '<span class="gr-ref">' + polSpan(ref.polarity)
            + ' <span class="sub">(' + esc(ref.confidence || '') + ')</span><br>'
            + '<span class="sub">' + esc(ref.reason || '') + '</span></span>';
    }
    // 네 판정(claude_judgment): Claude가 그룹 기준으로 판단한 극성 + 근거 설명.
    function claudeJudge(cj) {
        if (!cj || !cj.polarity) { return '<span class="sub">—</span>'; }
        return '<span class="gr-ref">' + polSpan(cj.polarity) + '<br>'
            + '<span class="sub">' + esc(cj.reason || '') + '</span></span>';
    }

    var DECS = [['positive', 'pos', '긍'], ['negative', 'neg', '부'],
                ['neutral', 'neu', '중'], ['not_group', 'non', '그룹아님']];

    function pickButtons(it) {
        var cur = chosen(it);
        return '<div class="gr-pick">' + DECS.map(function (d) {
            var on = cur === d[0] ? ' on' : '';
            var pend = (it.pending != null && it.pending === d[0]) ? ' pending' : '';
            return '<button class="gr-pb ' + d[1] + on + pend + '" data-rec="' + esc(it.rec_id)
                + '" data-d="' + d[0] + '">' + d[2] + '</button>';
        }).join('') + '</div>';
    }

    // 출처 배지: 사람 확정(gold) vs claude_auto 프리필(silver, 미확정).
    function srcBadge(it) {
        if (it.decision_source === 'human') { return ' <span class="gr-src human">✓사람</span>'; }
        if (it.suggested_source === 'claude_auto' && it.pending == null) {
            return ' <span class="gr-src auto">auto</span>';
        }
        return '';
    }

    function rowClass(it, isCursor) {
        var c = it.pending != null && it.pending !== it.decision ? 'dirty'
            : (it.decision != null ? 'decided' : '');
        return (c + (isCursor ? ' cursor' : '')).trim();
    }

    function updateSaveBtn() {
        var n = dirtyList().length;
        var b = $('grSave'); b.textContent = '💾 저장 (' + n + ')'; b.disabled = n === 0;
    }

    // 드롭다운의 현재 파일 라벨을 (판정/전체)로 실시간 갱신(저장 직후 호출).
    function updateFileOptionLabel() {
        var sel = $('grFile');
        if (!sel || !state.file) { return; }
        var decided = state.all.filter(function (it) { return it.decision != null; }).length;
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].value === state.file) {
                sel.options[i].textContent = state.file + ' (' + decided + '/' + state.total + ')';
                return;
            }
        }
    }

    function render() {
        var has = state.file && state.view.length > 0;
        $('grEmpty').style.display = state.file ? (has ? 'none' : 'block') : 'block';
        if (state.file && !has) {
            var done = state.all.filter(function (it) { return it.decision != null; }).length;
            $('grEmpty').textContent = (state.undecidedOnly && state.total > 0 && done >= state.total)
                ? '✅ 이 파일은 모두 판정했습니다 (' + done + '/' + state.total + '). "미판정만" 해제 시 전체 보기.'
                : '표시할 항목이 없습니다. ("미판정만" 해제 시 전체 표시)';
        }
        $('grTbl').style.display = has ? 'table' : 'none';
        $('grPage').style.display = has ? 'flex' : 'none';
        var decided = state.all.filter(function (it) { return it.decision != null; }).length;
        $('grProgress').textContent = state.file
            ? ('저장됨 ' + decided + ' / 전체 ' + state.total + ' · 표시 ' + state.view.length) : '';
        updateSaveBtn();
        if (!has) { return; }

        var start = state.page * PAGE;
        var rows = state.view.slice(start, start + PAGE);
        $('grBody').innerHTML = rows.map(function (it, i) {
            var gi = start + i;
            return '<tr class="' + rowClass(it, gi === state.cursor) + '" data-rec="' + esc(it.rec_id) + '" data-gi="' + gi + '">'
                + '<td class="txt">' + esc(decodeEntities(it.text)) + '</td>'
                + '<td>' + polSpan(it.cur_rule_label) + '</td>'
                + '<td>' + algoRef(it.ai_reference) + '</td>'
                + '<td>' + claudeJudge(it.claude_judgment) + '</td>'
                + '<td>' + pickButtons(it) + srcBadge(it) + '</td>'
                + '<td class="sub">' + esc(it.field || '') + '</td></tr>';
        }).join('');
        var pages = Math.ceil(state.view.length / PAGE);
        $('grPageInfo').textContent = (state.page + 1) + ' / ' + pages;
        $('grPrev').disabled = state.page <= 0;
        $('grNext').disabled = state.page >= pages - 1;
    }

    function setDecision(it, d) {
        it.pending = (it.pending === d && it.decision !== d) ? null : d;
        updateSaveBtn();
        scheduleFlush();   // 선택 즉시 자동저장(0.4초 묶음, 충돌 방지)
    }

    // ── 자동저장: 단일 처리(saving) + 디바운스로 병렬 lost-update 방지 ──
    var saving = false, flushTimer = null;
    function scheduleFlush() { clearTimeout(flushTimer); flushTimer = setTimeout(flush, 400); }
    function flush() {
        clearTimeout(flushTimer);
        if (saving) { return; }                 // 진행 중이면 끝난 뒤 재시도
        var dirty = dirtyList();
        if (!dirty.length) { return; }
        saving = true;
        var payload = { file: state.file, decisions: dirty.map(function (it) {
            return { rec_id: it.rec_id, decision: it.pending };
        }) };
        fetch(API + '/save', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (r) { return r.json(); }).then(function (j) {
            saving = false;
            if (!j.success) { alert(j.error || '저장 실패'); updateSaveBtn(); return; }
            dirty.forEach(function (it) { it.decision = it.pending; it.pending = null; });
            toast('저장됨 ' + (j.saved != null ? j.saved : dirty.length) + '건');
            updateFileOptionLabel();   // 드롭다운 (판정/전체) 즉시 갱신
            render();
            refreshApplyDb();   // 저장분(status 4) 반영 → "DB에 반영" 버튼 갱신
            if (dirtyList().length) { scheduleFlush(); }   // 저장 중 쌓인 선택 처리
        }).catch(function () { saving = false; updateSaveBtn(); scheduleFlush(); });
    }

    // 커서 이동(페이지 자동 추종 + 상단 스크롤)
    function moveCursor(delta) {
        if (!state.view.length) { return; }
        var nc = Math.min(state.view.length - 1, Math.max(0, state.cursor + delta));
        var oldPage = state.page;
        state.cursor = nc;
        state.page = Math.floor(nc / PAGE);
        render();
        if (state.page !== oldPage) { window.scrollTo({ top: 0 }); }
        else {
            var tr = document.querySelector('tr[data-gi="' + nc + '"]');
            if (tr) { tr.scrollIntoView({ block: 'nearest' }); }
        }
    }

    function gotoPage(p) {
        var pages = Math.ceil(state.view.length / PAGE);
        if (p < 0 || p >= pages) { return; }
        state.page = p; state.cursor = p * PAGE; render(); window.scrollTo({ top: 0 });
    }

    function saveAll() { flush(); }   // 💾 = 즉시 저장(자동저장과 동일 경로·충돌안전)

    document.addEventListener('DOMContentLoaded', function () {
        loadFiles(autoSelectPresetFile);   // 목록 로드 후 ?file=/sessionStorage 프리셋 자동선택
        $('grFile').addEventListener('change', function (e) {
            if (dirtyList().length && !confirm('저장하지 않은 선택이 있습니다. 파일을 바꾸면 사라집니다. 계속할까요?')) {
                e.target.value = state.file; return;
            }
            loadFile(e.target.value);
        });
        $('grSort').addEventListener('change', renderFileOptions);  // 정렬 변경 → 드롭다운 재구성(선택 유지)
        $('grUndecided').addEventListener('change', function (e) {
            state.undecidedOnly = e.target.checked; applyFilter(); render();
        });
        $('grSave').addEventListener('click', saveAll);
        $('grApplyDb').addEventListener('click', applyDb);
        $('grPrev').addEventListener('click', function () { gotoPage(state.page - 1); });
        $('grNext').addEventListener('click', function () { gotoPage(state.page + 1); });
        $('grBody').addEventListener('click', function (e) {
            var b = e.target.closest('.gr-pb');
            if (b) {
                var tr = b.closest('tr');
                state.cursor = parseInt(tr.getAttribute('data-gi'), 10);
                var it = state.all.filter(function (x) { return String(x.rec_id) === b.getAttribute('data-rec'); })[0];
                if (it) { setDecision(it, b.getAttribute('data-d')); render(); }
                return;
            }
            // 행 아무 곳이나 클릭 → 그 행으로 커서 이동(키보드 없이도 항 선택)
            var row = e.target.closest('tr[data-gi]');
            if (row) { state.cursor = parseInt(row.getAttribute('data-gi'), 10); render(); }
        });
        document.addEventListener('keydown', function (e) {
            if (!state.view.length || /^(INPUT|SELECT|TEXTAREA)$/.test((e.target.tagName || ''))) { return; }
            if (e.key === 'ArrowDown') { e.preventDefault(); moveCursor(1); return; }
            if (e.key === 'ArrowUp') { e.preventDefault(); moveCursor(-1); return; }
            var km = { '1': 'positive', '2': 'negative', '3': 'neutral', '4': 'not_group' };
            if (km[e.key]) {
                e.preventDefault();
                var it = state.view[state.cursor];
                if (it) { setDecision(it, km[e.key]); render(); moveCursor(1); }
            }
        });
        window.addEventListener('beforeunload', function (e) {
            if (dirtyList().length) { e.preventDefault(); e.returnValue = ''; }
        });
    });
})();
