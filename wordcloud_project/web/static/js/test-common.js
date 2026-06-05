/**
 * 공통 테스트 프론트엔드 모듈
 * 모든 테스트 페이지(sentiment, profanity, ...)가 공유
 */

const TestRunner = {
    async run(testType, text, params = {}) {
        const res = await fetch('/api/test/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_type: testType, text, params })
        });
        return res.json();
    },

    async runBatch(testType, cases, params = {}) {
        const res = await fetch('/api/test/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_type: testType, cases, params })
        });
        return res.json();
    },

    async loadCases(testType) {
        const res = await fetch(`/api/test/cases/${testType}`);
        return res.json();
    }
};

const TestRenderer = {
    renderTable(containerId, results, columns) {
        const container = document.getElementById(containerId);
        if (!container) return;
        let h = '<table class="test-table"><thead><tr>';
        columns.forEach(col => { h += `<th>${col.header}</th>`; });
        h += '</tr></thead><tbody>';
        results.forEach(row => {
            h += '<tr>';
            columns.forEach(col => {
                const val = col.accessor(row);
                h += `<td>${col.formatter ? col.formatter(val, row) : val}</td>`;
            });
            h += '</tr>';
        });
        h += '</tbody></table>';
        container.innerHTML = h;
    },

    renderSummary(containerId, stats) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = `
            <div class="test-summary">
                <div class="test-summary-item">
                    <div class="number">${stats.total}</div>
                    <div class="label">총 케이스</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#28a745">${stats.passed}</div>
                    <div class="label">통과</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#dc3545">${stats.failed}</div>
                    <div class="label">실패</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#fd7e14">${stats.accuracy}%</div>
                    <div class="label">정확도</div>
                </div>
                <div class="test-summary-item">
                    <div class="number" style="color:#6f42c1">${stats.avg_time_ms}ms</div>
                    <div class="label">평균 처리시간</div>
                </div>
            </div>
        `;
    }
};

const TestLogger = {
    log(containerId, msg, type = 'info') {
        const area = document.getElementById(containerId);
        if (!area) return;
        const cls = type === 'success' ? 'test-log-success' : type === 'error' ? 'test-log-error' : 'test-log-info';
        area.innerHTML += `<div class="${cls}">${new Date().toLocaleTimeString()} ${msg}</div>`;
        area.scrollTop = area.scrollHeight;
    },
    clear(containerId) {
        const area = document.getElementById(containerId);
        if (area) area.innerHTML = '';
    }
};
