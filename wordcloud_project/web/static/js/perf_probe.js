/**
 * perf_probe.js — 화면 지연 원인 계측(20_06 / 20_09)
 *
 * 두 계획서 모두 "느리다"는 체감만 있고 코드 정적 분석으로는 후보를 더 좁힐 수
 * 없어 멈춰 있었다. 이 스크립트는 브라우저에서 실제로 시간이 어디서 쓰이는지를
 * 콘솔에 남긴다. 서버 쪽 짝은 utils/perf.py(로그 STAGE:PERF / PERF_REQ)다.
 *
 * 보는 법 (F12 → Console):
 *   [PERF] fetch  1842.3ms POST /api/perspective/meta   ← 요청 하나의 왕복시간
 *   [PERF] mark   loadMeta:render 2103.5ms              ← 응답 이후 화면 조립 시간
 *   [PERF] nav    ttfb=... domContentLoaded=... load=... ← 페이지 자체 로딩 구간
 *   __perf.report()  ← 아무 때나 콘솔에 입력하면 지금까지 수집한 표를 출력
 *
 * 판정 기준:
 *   - 서버 로그 ms ≈ 브라우저 fetch ms → 서버가 원인.
 *   - 서버 로그 ms ≪ 브라우저 fetch ms → 네트워크·프록시 구간이 원인.
 *   - fetch 는 빠른데 mark(render) 가 크다 → 브라우저 DOM 조립이 원인.
 *
 * 계측만 하고 어떤 동작도 바꾸지 않는다. 실패해도 페이지가 깨지지 않도록
 * 모든 경로를 try/catch 로 감싼다.
 */
(function () {
    'use strict';
    if (window.__perf) { return; }

    var SLOW_MS = 300;              // 이 값 이상이면 console.warn 으로 눈에 띄게
    var entries = [];               // {type, label, ms, detail}
    var marks = {};

    function now() {
        try {
            return (window.performance && performance.now) ? performance.now() : Date.now();
        } catch (e) { return Date.now(); }
    }

    function record(type, label, ms, detail) {
        try {
            entries.push({ type: type, label: label, ms: Math.round(ms * 10) / 10, detail: detail || '' });
            var line = '[PERF] ' + type + '  ' + (Math.round(ms * 10) / 10) + 'ms  ' + label
                + (detail ? '  ' + detail : '');
            if (ms >= SLOW_MS) { console.warn(line); } else { console.log(line); }
        } catch (e) { /* 계측 실패가 화면을 막지 않게 */ }
    }

    var api = {
        entries: entries,

        /** 기준점을 찍는다. 같은 label 로 다시 찍으면 갱신된다. */
        mark: function (label) {
            try { marks[label] = now(); } catch (e) { }
        },

        /** mark(label) 이후 경과시간을 기록한다. mark 가 없으면 무시. */
        since: function (label, detail) {
            try {
                if (marks[label] === undefined) { return; }
                record('mark', label, now() - marks[label], detail);
                delete marks[label];
            } catch (e) { }
        },

        /** 동기 구간 계측: __perf.span('라벨', function () { ... }) */
        span: function (label, fn, detail) {
            var t0 = now();
            try {
                return fn();
            } finally {
                record('span', label, now() - t0, detail);
            }
        },

        /** 수집된 계측을 표로 출력. 콘솔에서 __perf.report() 로 호출. */
        report: function () {
            try {
                if (console.table) { console.table(entries); } else { console.log(entries); }
                return entries.length;
            } catch (e) { return 0; }
        },

        /** 표를 비운다(같은 화면에서 조작 전/후를 나눠 재고 싶을 때). */
        reset: function () { entries.length = 0; marks = {}; }
    };

    // --- fetch 계측 -------------------------------------------------------
    // 응답 객체를 그대로 돌려주므로 스트리밍(res.body.getReader) 사용처도 영향 없음.
    try {
        if (window.fetch) {
            var origFetch = window.fetch;
            window.fetch = function (input, init) {
                var t0 = now();
                var method = (init && init.method) || (input && input.method) || 'GET';
                var url = (typeof input === 'string') ? input : (input && input.url) || '';
                var p;
                try {
                    p = origFetch.apply(this, arguments);
                } catch (e) {
                    record('fetch', method + ' ' + url, now() - t0, 'throw');
                    throw e;
                }
                try {
                    return p.then(function (res) {
                        record('fetch', method + ' ' + url, now() - t0, 'status=' + (res && res.status));
                        return res;
                    }, function (err) {
                        record('fetch', method + ' ' + url, now() - t0, 'error');
                        throw err;
                    });
                } catch (e) { return p; }
            };
        }
    } catch (e) { }

    // --- XMLHttpRequest 계측 ---------------------------------------------
    // 일부 화면은 jQuery($.ajax)를 쓴다 — fetch 만 재면 그 요청이 통째로 안 보인다.
    try {
        var XHR = window.XMLHttpRequest;
        if (XHR && XHR.prototype) {
            var origOpen = XHR.prototype.open;
            var origSend = XHR.prototype.send;
            XHR.prototype.open = function (method, url) {
                try { this.__perfLabel = (method || 'GET') + ' ' + url; } catch (e) { }
                return origOpen.apply(this, arguments);
            };
            XHR.prototype.send = function () {
                var self = this, t0 = now();
                try {
                    self.addEventListener('loadend', function () {
                        record('xhr', self.__perfLabel || '(unknown)', now() - t0, 'status=' + self.status);
                    });
                } catch (e) { }
                return origSend.apply(this, arguments);
            };
        }
    } catch (e) { }

    // --- 페이지 로딩 구간 --------------------------------------------------
    // 요청이 다 빨라도 느리다면 문서 자체(HTML 크기·스크립트 파싱)가 원인일 수 있다.
    try {
        window.addEventListener('load', function () {
            setTimeout(function () {
                try {
                    var t = performance.timing;
                    if (!t || !t.navigationStart) { return; }
                    var nav = {
                        ttfb: t.responseStart - t.requestStart,
                        htmlDownload: t.responseEnd - t.responseStart,
                        domContentLoaded: t.domContentLoadedEventEnd - t.navigationStart,
                        load: t.loadEventEnd - t.navigationStart
                    };
                    console.log('[PERF] nav   ttfb=' + nav.ttfb + 'ms htmlDownload=' + nav.htmlDownload
                        + 'ms domContentLoaded=' + nav.domContentLoaded + 'ms load=' + nav.load + 'ms');
                    entries.push({ type: 'nav', label: location.pathname, ms: nav.load, detail: JSON.stringify(nav) });
                } catch (e) { }
            }, 0);
        });
    } catch (e) { }

    window.__perf = api;
})();
