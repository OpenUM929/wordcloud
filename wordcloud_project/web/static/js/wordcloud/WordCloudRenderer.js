/**
 * WordCloudRenderer.js
 * Renders an animated SVG word-cloud using d3-cloud + D3.js.
 *
 * Dependencies (must be loaded before this file):
 *   - d3 v7          (window.d3)
 *   - d3-cloud       (window.d3.layout.cloud)
 *   - WordCloudTheme (WordCloudTheme.js)
 *   - WordCloudAnimator (WordCloudAnimator.js)
 */

class WordCloudRenderer {
    /**
     * @param {string} containerId - DOM id of the container element
     * @param {object} options
     * @param {number}  [options.width=800]
     * @param {number}  [options.height=500]
     * @param {number}  [options.maxWords=60]
     * @param {string}  [options.animationMode='fadeIn']  'fadeIn'|'spiral'|'pop'
     * @param {string}  [options.theme='emotion_based']
     */
    constructor(containerId, options = {}) {
        this._containerId = containerId;
        this._opts = Object.assign({
            width: 800,
            height: 500,
            maxWords: 60,
            animationMode: 'fadeIn',
            theme: 'emotion_based',
        }, options);

        this._words = [];
        this._svg = null;
        this._wordClickCb = null;
        this._wordHoverCb = null;
    }

    // ── Data loading ───────────────────────────────────────────────────────────

    async loadFromAPI(batchId, employeeId) {
        const url = `/api/wordcloud/data/${batchId}/${employeeId}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`API 오류: ${res.status}`);
        const json = await res.json();
        if (!json.success) throw new Error(json.error || 'API 응답 실패');
        this._apiData = json.data;
        this.loadFromData(json.data.words);
        return json.data;
    }

    loadFromData(wordData) {
        this._words = wordData.slice(0, this._opts.maxWords);
    }

    // ── Rendering ──────────────────────────────────────────────────────────────

    render() {
        if (!this._words.length) return;

        const container = document.getElementById(this._containerId);
        if (!container) throw new Error(`컨테이너 없음: #${this._containerId}`);

        container.innerHTML = '';

        const { width, height, theme: themeName, animationMode } = this._opts;
        const theme = WordCloudTheme.get(themeName);

        // Background
        container.style.background = theme.background;

        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .attr('xmlns', 'http://www.w3.org/2000/svg');

        this._svg = svg;

        const g = svg.append('g')
            .attr('transform', `translate(${width / 2},${height / 2})`);

        const maxWeight = d3.max(this._words, (d) => d.weight) || 1;
        const fontScale = d3.scaleSqrt()
            .domain([1, maxWeight])
            .range([12, Math.min(width, height) * 0.18]);

        const wordsWithSize = this._words.map((w) => ({
            ...w,
            size: fontScale(w.weight),
        }));

        d3.layout.cloud()
            .size([width, height])
            .words(wordsWithSize)
            .padding(4)
            .rotate(() => (Math.random() < 0.3 ? 90 : 0))
            .font(theme.fontFamily)
            .fontSize((d) => d.size)
            .on('end', (placed) => this._draw(g, placed, theme, animationMode))
            .start();
    }

    _draw(g, words, theme, animationMode) {
        const texts = g.selectAll('text')
            .data(words)
            .enter()
            .append('text')
            .style('font-family', theme.fontFamily)
            .style('font-size', (d) => `${d.size}px`)
            .style('font-weight', (d) => d.normalized_weight > 0.6 ? 'bold' : 'normal')
            .style('fill', (d, i) => theme.getColor(d, i))
            .style('cursor', 'pointer')
            .attr('text-anchor', 'middle')
            .attr('transform', (d) => `translate(${d.x},${d.y}) rotate(${d.rotate})`)
            .text((d) => d.text);

        // Events
        texts.on('click', (event, d) => {
            if (this._wordClickCb) this._wordClickCb(d, event);
        });

        texts.on('mouseover', (event, d) => {
            d3.select(event.currentTarget).style('opacity', 0.7);
            if (this._wordHoverCb) this._wordHoverCb(d, event, true);
        });

        texts.on('mouseout', (event, d) => {
            d3.select(event.currentTarget).style('opacity', null);
            if (this._wordHoverCb) this._wordHoverCb(d, event, false);
        });

        WordCloudAnimator.animate(texts, animationMode);
    }

    // ── Event hooks ────────────────────────────────────────────────────────────

    onWordClick(callback) { this._wordClickCb = callback; return this; }
    onWordHover(callback) { this._wordHoverCb = callback; return this; }

    // ── Export ─────────────────────────────────────────────────────────────────

    exportSVG() {
        if (!this._svg) return null;
        const node = this._svg.node();
        const serializer = new XMLSerializer();
        return serializer.serializeToString(node);
    }

    exportPNG() {
        return new Promise((resolve, reject) => {
            const svgStr = this.exportSVG();
            if (!svgStr) return reject(new Error('SVG 없음'));

            const { width, height } = this._opts;
            const blob = new Blob([svgStr], { type: 'image/svg+xml' });
            const url = URL.createObjectURL(blob);
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                const theme = WordCloudTheme.get(this._opts.theme);
                ctx.fillStyle = theme.background;
                ctx.fillRect(0, 0, width, height);
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);
                canvas.toBlob(resolve, 'image/png');
            };
            img.onerror = reject;
            img.src = url;
        });
    }

    resize(width, height) {
        this._opts.width = width;
        this._opts.height = height;
        if (this._words.length) this.render();
    }
}
