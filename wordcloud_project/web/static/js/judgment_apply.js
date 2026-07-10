// 판정 결과 반영 — 판정 패킷 업로드/재적용 → POST /api/perspective/judgment/apply.
// status==3(확정)만 DB 반영. status==2(사람 판정 대기)는 그룹검토 게시판으로.
(function () {
    'use strict';

    var API = '/api/perspective/judgment';

    function $(id) { return document.getElementById(id); }

    function setLoading(on) {
        $('jaLoading').style.display = on ? 'block' : 'none';
        if (on) { $('jaResult').style.display = 'none'; }
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function stat(num, label, mod) {
        return '<div class="ja-stat' + (mod ? ' ja-stat--' + mod : '') + '">'
            + '<div class="ja-stat__num">' + num + '</div>'
            + '<div class="ja-stat__label">' + label + '</div></div>';
    }

    function num(v) { return v != null ? v : 0; }

    function summaryHtml(s) {
        s = s || {};
        return ''
            + stat(num(s.inserted_sentences), 'DB 반영된 문장(status 10/11)')
            + stat(num(s.updated_evaluations), '갱신된 평가')
            + stat(num(s.ai_ready), 'AI 작업 완료·DB 반영 대기(status 3)', 'warn')
            + stat(num(s.human_ready), 'Human 작업 완료·DB 반영 대기(status 4)', 'warn')
            + stat(num(s.pending_human), '사람 판정 대기(status 2)', 'warn')
            + stat(num(s.pending_ai), 'AI 판정 대기(status 1)', 'mute')
            + stat(num(s.skipped), '건너뜀', 'mute');
    }

    function renderResult(data) {
        $('jaSummary').innerHTML = summaryHtml(data.summary);
        var s = data.summary || {};
        var ex = $('jaExport');
        var lines = [];
        if (data.packet_file) {
            lines.push('💾 패킷을 서버에 저장했습니다: <code>' + escapeHtml(data.packet_file) + '</code>');
        }
        if (s.pending_human) {
            lines.push('🙋 <strong>' + s.pending_human + '건</strong>이 사람 판정 대기입니다 — '
                + '<a href="/group-review">그룹검토 게시판에서 판정 →</a> 후 아래 "서버 저장 패킷 재적용"으로 반영하세요.');
        }
        if (lines.length) {
            ex.innerHTML = lines.map(function (l) { return '<p style="margin:4px 0;">' + l + '</p>'; }).join('');
            ex.style.display = 'block';
            loadPackets();   // 방금 저장된 패킷이 재적용 드롭다운에 뜨도록 갱신
        } else {
            ex.style.display = 'none';
        }
        $('jaResult').style.display = 'block';
    }

    function showError(msg) {
        $('jaSummary').innerHTML = '<div class="ja-error">⚠ ' + escapeHtml(msg) + '</div>';
        $('jaExport').style.display = 'none';
        $('jaResult').style.display = 'block';
    }

    function upload(file) {
        if (!file) { return; }
        if (!/\.json$/i.test(file.name)) {
            alert('판정 패킷 JSON 파일(.json)을 선택하세요.');
            return;
        }
        var formData = new FormData();
        formData.append('packet', file);
        setLoading(true);
        fetch(API + '/apply', { method: 'POST', body: formData })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
            .then(function (res) {
                setLoading(false);
                if (!res.body || res.body.success !== true) {
                    showError((res.body && res.body.error) || '반영 실패');
                    return;
                }
                renderResult(res.body);
            })
            .catch(function (err) {
                setLoading(false);
                console.error('판정 반영 오류:', err);
                showError('패킷 반영 중 오류가 발생했습니다.');
            });
    }

    // ── 서버 저장 패킷 재적용 ──
    function loadPackets() {
        fetch(API + '/packets')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j || !j.success) { return; }
                var sel = $('jaPacketFile');
                var cur = sel.value;
                sel.innerHTML = '<option value="">— 서버 저장 패킷 선택 —</option>';
                (j.packets || []).forEach(function (p) {
                    var o = document.createElement('option');
                    o.value = p.name;
                    o.textContent = p.name + '  [AI대기 ' + num(p.pending_ai)
                        + ' · AI완료 ' + num(p.ai_ready)
                        + ' · 사람대기 ' + num(p.pending_human)
                        + ' · Human완료 ' + num(p.human_ready)
                        + ' · AI적용 ' + num(p.ai_applied)
                        + ' · Human적용 ' + num(p.human_applied) + ']';
                    o.dataset.aiReady = num(p.ai_ready);
                    sel.appendChild(o);
                });
                sel.value = cur;
                $('jaReapplyBtn').disabled = !sel.value;
                updateApplyDbBtn();
            })
            .catch(function () {});
    }

    // "DB에 반영"(AI) 버튼 — 선택 패킷에 AI 작업완료(status 3)가 있을 때만 노출·활성화
    function updateApplyDbBtn() {
        var sel = $('jaPacketFile');
        var opt = sel.options[sel.selectedIndex];
        var btn = $('jaApplyDbBtn');
        var aiReady = opt ? parseInt(opt.dataset.aiReady || '0', 10) : 0;
        if (opt && opt.value && aiReady > 0) {
            btn.style.display = 'inline-block';
            btn.disabled = false;
            btn.textContent = '💾 DB에 반영 (AI ' + aiReady + '건)';
        } else {
            btn.style.display = 'none';
            btn.disabled = true;
        }
    }

    function applyDb() {
        var file = $('jaPacketFile').value;
        if (!file) { return; }
        var btn = $('jaApplyDbBtn');
        btn.disabled = true;
        var prev = btn.textContent;
        btn.textContent = '반영 중…';
        fetch(API + '/apply-db', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file: file, target: 'ai' })   // judgment_apply는 AI분(3)만 반영
        }).then(function (r) { return r.json(); }).then(function (j) {
            if (!j || j.success !== true) {
                btn.disabled = false; btn.textContent = prev;
                $('jaReapplyResult').innerHTML = '<div class="ja-error">⚠ '
                    + escapeHtml((j && j.error) || 'DB 반영 실패') + '</div>';
                return;
            }
            var s = j.summary || {};
            $('jaReapplyResult').innerHTML = stat(num(s.applied_ai), 'AI DB 반영 완료(status 10)')
                + stat(num(s.skipped), '건너뜀', 'mute');
            if (j.redirect_to_group_review) {   // AI 반영 후 사람 이관분 잔존 → 게시판 유도
                $('jaRedirectAlert').style.display = 'block';
            }
            loadPackets();   // 상태 분포·버튼 갱신
        }).catch(function () {
            btn.disabled = false; btn.textContent = prev;
            $('jaReapplyResult').innerHTML = '<div class="ja-error">⚠ DB 반영 중 오류가 발생했습니다.</div>';
        });
    }

    function goToGroupReview() {
        var file = $('jaPacketFile').value;
        if (file) { sessionStorage.setItem('gr_preset_file', file); }
        window.location.href = '/group-review' + (file ? '?file=' + encodeURIComponent(file) : '');
    }

    function dismissRedirect() { $('jaRedirectAlert').style.display = 'none'; }

    function reapply() {
        var file = $('jaPacketFile').value;
        if (!file) { return; }
        var btn = $('jaReapplyBtn');
        btn.disabled = true;
        $('jaReapplyResult').innerHTML = '<div class="ja-stat ja-stat--mute"><div class="ja-stat__label">재적용 중…</div></div>';
        fetch(API + '/apply', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file: file })
        }).then(function (r) { return r.json(); }).then(function (j) {
            btn.disabled = false;
            if (!j || j.success !== true) {
                $('jaReapplyResult').innerHTML = '<div class="ja-error">⚠ '
                    + escapeHtml((j && j.error) || '재적용 실패') + '</div>';
                return;
            }
            $('jaReapplyResult').innerHTML = summaryHtml(j.summary);
            loadPackets();   // 반영 후 상태 분포 갱신
        }).catch(function () {
            btn.disabled = false;
            $('jaReapplyResult').innerHTML = '<div class="ja-error">⚠ 재적용 중 오류가 발생했습니다.</div>';
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var area = $('jaUploadArea');
        var input = $('jaFileInput');

        loadPackets();
        $('jaPacketFile').addEventListener('change', function (e) {
            $('jaReapplyBtn').disabled = !e.target.value;
            updateApplyDbBtn();
        });
        $('jaReapplyBtn').addEventListener('click', reapply);
        $('jaPacketRefresh').addEventListener('click', loadPackets);
        $('jaApplyDbBtn').addEventListener('click', applyDb);
        $('jaGoGroupReview').addEventListener('click', goToGroupReview);
        $('jaDismissRedirect').addEventListener('click', dismissRedirect);

        area.addEventListener('click', function () { input.click(); });
        input.addEventListener('change', function (e) {
            if (e.target.files.length > 0) { upload(e.target.files[0]); }
            input.value = '';
        });

        ['dragenter', 'dragover'].forEach(function (ev) {
            area.addEventListener(ev, function (e) { e.preventDefault(); area.classList.add('dragover'); });
        });
        ['dragleave', 'drop'].forEach(function (ev) {
            area.addEventListener(ev, function (e) { e.preventDefault(); area.classList.remove('dragover'); });
        });
        area.addEventListener('drop', function (e) {
            if (e.dataTransfer.files.length > 0) { upload(e.dataTransfer.files[0]); }
        });
    });
})();
