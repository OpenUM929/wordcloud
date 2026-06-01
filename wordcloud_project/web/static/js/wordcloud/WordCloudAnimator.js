/**
 * WordCloudAnimator.js - animation modes for SVG word elements.
 * Operates on D3 selections of <text> elements already placed by d3-cloud.
 */

const WordCloudAnimator = (() => {
    /**
     * @param {d3.Selection} textSelection - D3 selection of all <text> elements
     * @param {string} mode - 'fadeIn' | 'spiral' | 'pop'
     */
    function animate(textSelection, mode) {
        switch (mode) {
            case 'spiral': return _spiral(textSelection);
            case 'pop':    return _pop(textSelection);
            default:       return _fadeIn(textSelection);
        }
    }

    // Central → outward fade, heaviest words first (already sorted by weight)
    function _fadeIn(sel) {
        sel.style('opacity', 0)
           .transition()
           .delay((_, i) => i * 30)
           .duration(600)
           .style('opacity', 1);
    }

    // Scale-in from centre simultaneously, staggered by distance from origin
    function _spiral(sel) {
        sel.style('opacity', 0)
           .attr('transform', (d) => `translate(${d.x},${d.y}) rotate(${d.rotate}) scale(0.1)`)
           .transition()
           .delay((d) => Math.sqrt(d.x * d.x + d.y * d.y) * 0.8)
           .duration(700)
           .ease(d3.easeCubicOut)
           .style('opacity', 1)
           .attr('transform', (d) => `translate(${d.x},${d.y}) rotate(${d.rotate}) scale(1)`);
    }

    // Pop: scale 0 → 1.2 → 1 with a spring feel
    function _pop(sel) {
        sel.style('opacity', 0)
           .attr('transform', (d) => `translate(${d.x},${d.y}) rotate(${d.rotate}) scale(0)`)
           .transition()
           .delay((_, i) => i * 25)
           .duration(400)
           .ease(d3.easeBackOut.overshoot(1.5))
           .style('opacity', 1)
           .attr('transform', (d) => `translate(${d.x},${d.y}) rotate(${d.rotate}) scale(1)`);
    }

    return { animate };
})();
