/**
 * WordCloudTheme.js - colour/style themes for the SVG word-cloud renderer.
 */

const WordCloudTheme = (() => {
    const EMOTION_COLORS = {
        '강한_긍정': '#64BF91',
        '약한_긍정': '#91D2A5',
        '중립':      '#ACB2C8',
        '약한_부정': '#E69696',
        '강한_부정': '#D77882',
    };

    const THEMES = {
        emotion_based: {
            name: '감정 기반',
            getColor: (word) => word.color || EMOTION_COLORS['중립'],
            background: '#ffffff',
            fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
        },
        monochrome: {
            name: '단색',
            getColor: () => '#2c3e50',
            background: '#ffffff',
            fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
        },
        pastel: {
            name: '파스텔',
            getColor: (word, i) => {
                const palette = ['#FFB3BA','#FFDFBA','#FFFFBA','#BAFFC9','#BAE1FF'];
                return palette[i % palette.length];
            },
            background: '#fafafa',
            fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
        },
        dark: {
            name: '다크',
            getColor: (word) => {
                const map = {
                    '강한_긍정': '#4ade80',
                    '약한_긍정': '#86efac',
                    '중립':      '#94a3b8',
                    '약한_부정': '#fca5a5',
                    '강한_부정': '#f87171',
                };
                return map[word.emotion_label] || '#94a3b8';
            },
            background: '#1e293b',
            fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
        },
    };

    return {
        EMOTION_COLORS,
        get(name) { return THEMES[name] || THEMES.emotion_based; },
        list() { return Object.entries(THEMES).map(([k, v]) => ({ id: k, name: v.name })); },
    };
})();
