// progress-time.js — elapsed time and ETA display helpers

function formatElapsed(startIso) {
    var start = new Date(startIso);
    var diff = Date.now() - start.getTime();
    var h = Math.floor(diff / 3600000);
    var m = Math.floor((diff % 3600000) / 60000);
    var s = Math.floor((diff % 60000) / 1000);
    return h ? h + '\uC2DC\uAC04 ' + m + '\uBD84 ' + s + '\uCD08' : m + '\uBD84 ' + s + '\uCD08';
}

function formatEta(etaStr) {
    return etaStr || '\uACC4\uC0B0 \uC911...';
}

function startProgressTimer(getStartIso, getCurrent, getTotal, onUpdate) {
    var timer = setInterval(function () {
        var start = getStartIso();
        if (!start) return;
        var elapsed = formatElapsed(start);
        var current = getCurrent();
        var total = getTotal();
        var eta = '\uACC4\uC0B0 \uC911...';
        if (total > 0 && current > 0) {
            var startTime = new Date(start).getTime();
            var rate = current / ((Date.now() - startTime) / 1000);
            if (rate > 0) {
                var remainSec = (total - current) / rate;
                var etaDate = new Date(Date.now() + remainSec * 1000);
                eta = etaDate.toLocaleTimeString('ko-KR', { hour12: false });
            }
        }
        onUpdate(elapsed, eta);
    }, 1000);
    return function () { clearInterval(timer); };
}
