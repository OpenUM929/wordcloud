// 판정 결과 반영 — 판정 완료 패킷 JSON 업로드 → POST /judgment/apply
(function () {
    'use strict';

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

    function renderResult(data) {
        var s = data.summary || {};
        var summaryHtml = ''
            + stat(s.inserted_sentences != null ? s.inserted_sentences : 0, '반영된 문장')
            + stat(s.updated_evaluations != null ? s.updated_evaluations : 0, '갱신된 평가')
            + stat(s.needs_human != null ? s.needs_human : 0, '사람 검토 필요', 'warn')
            + stat(s.skipped != null ? s.skipped : 0, '건너뜀', 'mute');
        $('jaSummary').innerHTML = summaryHtml;

        var queue = data.needs_human_queue || [];
        if (queue.length > 0) {
            $('jaQueueCount').textContent = '(' + queue.length + '건)';
            $('jaQueueList').innerHTML = queue.map(function (it) {
                var key = it.key || {};
                var res = it.result || {};
                var meta = 'db_id=' + escapeHtml(key.db_id) + ' · sent_idx=' + escapeHtml(key.sent_idx)
                    + (res.label ? ' · 제안=' + escapeHtml(res.label) : '');
                return '<div class="ja-queue__item">'
                    + '<div class="ja-queue__text">' + escapeHtml(it.text) + '</div>'
                    + '<div class="ja-queue__meta">' + meta + '</div></div>';
            }).join('');
            $('jaQueue').style.display = 'block';
        } else {
            $('jaQueue').style.display = 'none';
        }
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

        fetch('/judgment/apply', { method: 'POST', body: formData })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
            .then(function (res) {
                setLoading(false);
                if (!res.body || res.body.success !== true) {
                    var msg = (res.body && res.body.error) || ('반영 실패 (HTTP ' + (res.ok ? '?' : 'error') + ')');
                    $('jaSummary').innerHTML = '<div class="ja-error">⚠ ' + escapeHtml(msg) + '</div>';
                    $('jaQueue').style.display = 'none';
                    $('jaResult').style.display = 'block';
                    return;
                }
                renderResult(res.body);
            })
            .catch(function (err) {
                setLoading(false);
                console.error('판정 반영 오류:', err);
                $('jaSummary').innerHTML = '<div class="ja-error">⚠ 패킷 반영 중 오류가 발생했습니다.</div>';
                $('jaQueue').style.display = 'none';
                $('jaResult').style.display = 'block';
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var area = $('jaUploadArea');
        var input = $('jaFileInput');

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
