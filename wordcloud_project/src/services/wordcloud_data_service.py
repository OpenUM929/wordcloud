"""Wordcloud data service - extracts rendering data from employee JSON for SVG animation."""

import os
import json
from datetime import datetime
from src.config.settings import PROCESSED_DATA_DIR_PATH

EMOTION_COLORS = {
    "강한_긍정": "#64BF91",
    "약한_긍정": "#91D2A5",
    "중립":      "#ACB2C8",
    "약한_부정": "#E69696",
    "강한_부정": "#D77882",
}

_STOP_CHARS = set('.,:;!?()[]{}"\'/\\-_*+=#@~`^&%$<>|')


def _score_to_emotion(score: float) -> str:
    if score > 0.5:
        return "강한_긍정"
    elif score > 0:
        return "약한_긍정"
    elif score > -0.5:
        return "중립"
    elif score > -1.0:
        return "약한_부정"
    else:
        return "강한_부정"


def _calc_emotion_from_evaluations(evaluations: list) -> dict:
    pos_scores, neg_scores, neu_scores = [], [], []
    for ev in evaluations:
        mapped = (ev.get('emotion_analysis_results', {})
                    .get('analysis', {})
                    .get('base_result', {})
                    .get('mapped', {}))
        scores = mapped.get('sentiment_scores', {})
        if scores:
            pos_scores.append(scores.get('positive', 0))
            neg_scores.append(scores.get('negative', 0))
            neu_scores.append(scores.get('neutral', 0))

    if not pos_scores:
        return {'avg_pos': 0.5, 'avg_neg': 0.0, 'avg_neu': 0.5, 'emotion_score': 0.5}

    avg_pos = sum(pos_scores) / len(pos_scores)
    avg_neg = sum(neg_scores) / len(neg_scores)
    avg_neu = sum(neu_scores) / len(neu_scores) if neu_scores else max(0.0, 1.0 - avg_pos - avg_neg)
    emotion_score = avg_pos - avg_neg
    return {'avg_pos': avg_pos, 'avg_neg': avg_neg, 'avg_neu': avg_neu, 'emotion_score': emotion_score}


def _filter_words(word_frequency: dict) -> dict:
    result = {}
    for w, freq in word_frequency.items():
        w = w.strip()
        if len(w) < 2:
            continue
        if all(c in _STOP_CHARS for c in w):
            continue
        result[w] = freq
    return result


def get_employee_wordcloud_data(batch_id: str, employee_id: str) -> tuple:
    """
    Returns (data_dict, error_str). error_str is None on success.
    """
    tmeta_dir = os.path.join(PROCESSED_DATA_DIR_PATH, "batch", batch_id, "tmeta")
    emp_file = os.path.join(tmeta_dir, f"employee_{employee_id}.json")
    if not os.path.exists(emp_file):
        return None, f"직원 데이터 없음: {employee_id}"

    with open(emp_file, encoding='utf-8') as f:
        raw = json.load(f)

    ca = raw.get('consolidated_analysis', {})
    word_frequency = ca.get('word_frequency', {})
    evaluations = raw.get('evaluations', [])

    emotion = _calc_emotion_from_evaluations(evaluations)
    emotion_score = emotion['emotion_score']
    emotion_label = _score_to_emotion(emotion_score)
    color = EMOTION_COLORS[emotion_label]

    filtered = _filter_words(word_frequency)
    max_freq = max(filtered.values()) if filtered else 1

    words = [
        {
            "text": text,
            "weight": freq,
            "normalized_weight": round(freq / max_freq, 4),
            "emotion_score": round(emotion_score, 4),
            "emotion_label": emotion_label,
            "color": color,
            "frequency": freq,
        }
        for text, freq in sorted(filtered.items(), key=lambda x: -x[1])
    ]

    avg_pos = emotion['avg_pos']
    avg_neg = emotion['avg_neg']
    avg_neu = emotion['avg_neu']
    if avg_pos >= avg_neg and avg_pos >= avg_neu:
        dominant = "positive"
    elif avg_neg >= avg_neu:
        dominant = "negative"
    else:
        dominant = "neutral"

    return {
        "meta": {
            "employee_id": employee_id,
            "batch_id": batch_id,
            "department": raw.get('target_employee_department', ''),
            "position": raw.get('target_employee_position', ''),
            "total_evaluations": raw.get('total_evaluations', len(evaluations)),
            "generated_at": datetime.now().isoformat(),
        },
        "words": words,
        "emotion_summary": {
            "positive_ratio": round(avg_pos, 4),
            "neutral_ratio": round(avg_neu, 4),
            "negative_ratio": round(avg_neg, 4),
            "dominant_emotion": dominant,
        },
        "render_hints": {
            "suggested_max_words": min(60, len(words)),
            "color_theme": "emotion_based",
            "total_word_count": sum(filtered.values()),
        },
    }, None


def get_batch_employee_list(batch_id: str) -> tuple:
    """
    Returns (employee_ids list, error_str).
    """
    tmeta_dir = os.path.join(PROCESSED_DATA_DIR_PATH, "batch", batch_id, "tmeta")
    summary_file = os.path.join(tmeta_dir, "batch_summary.json")
    if not os.path.exists(summary_file):
        return None, f"배치 없음: {batch_id}"

    with open(summary_file, encoding='utf-8') as f:
        summary = json.load(f)

    employee_ids = summary.get('employee_ids', [])
    return employee_ids, None


def get_batch_aggregate_data(batch_id: str) -> tuple:
    """
    Aggregates word frequencies across all employees in the batch.
    Returns (data_dict, error_str).
    """
    employee_ids, err = get_batch_employee_list(batch_id)
    if err:
        return None, err

    combined_freq: dict = {}
    all_pos, all_neg, all_neu = [], [], []

    tmeta_dir = os.path.join(PROCESSED_DATA_DIR_PATH, "batch", batch_id, "tmeta")
    for emp_id in employee_ids:
        emp_file = os.path.join(tmeta_dir, f"employee_{emp_id}.json")
        if not os.path.exists(emp_file):
            continue
        with open(emp_file, encoding='utf-8') as f:
            raw = json.load(f)

        wf = _filter_words(raw.get('consolidated_analysis', {}).get('word_frequency', {}))
        for word, freq in wf.items():
            combined_freq[word] = combined_freq.get(word, 0) + freq

        emotion = _calc_emotion_from_evaluations(raw.get('evaluations', []))
        all_pos.append(emotion['avg_pos'])
        all_neg.append(emotion['avg_neg'])
        all_neu.append(emotion['avg_neu'])

    if not combined_freq:
        return None, "배치에 단어 데이터 없음"

    avg_pos = sum(all_pos) / len(all_pos) if all_pos else 0.5
    avg_neg = sum(all_neg) / len(all_neg) if all_neg else 0.0
    avg_neu = sum(all_neu) / len(all_neu) if all_neu else 0.5
    emotion_score = avg_pos - avg_neg
    emotion_label = _score_to_emotion(emotion_score)
    color = EMOTION_COLORS[emotion_label]

    max_freq = max(combined_freq.values())
    words = [
        {
            "text": text,
            "weight": freq,
            "normalized_weight": round(freq / max_freq, 4),
            "emotion_score": round(emotion_score, 4),
            "emotion_label": emotion_label,
            "color": color,
            "frequency": freq,
        }
        for text, freq in sorted(combined_freq.items(), key=lambda x: -x[1])
    ]

    dominant = "positive" if avg_pos >= avg_neg and avg_pos >= avg_neu else (
        "negative" if avg_neg >= avg_neu else "neutral"
    )

    return {
        "meta": {
            "batch_id": batch_id,
            "employee_count": len(employee_ids),
            "generated_at": datetime.now().isoformat(),
        },
        "words": words,
        "emotion_summary": {
            "positive_ratio": round(avg_pos, 4),
            "neutral_ratio": round(avg_neu, 4),
            "negative_ratio": round(avg_neg, 4),
            "dominant_emotion": dominant,
        },
        "render_hints": {
            "suggested_max_words": min(80, len(words)),
            "color_theme": "emotion_based",
            "total_word_count": sum(combined_freq.values()),
        },
    }, None
