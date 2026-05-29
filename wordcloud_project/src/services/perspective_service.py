"""Perspective analysis service - multi-filter grouping engine with X/Y matrix."""
import matplotlib
matplotlib.use('Agg')
import os
import json
import re
import hashlib
from collections import Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from src.config.settings import (
    OUTPUTS_DIR_PATH, WORDCLOUD_CONFIG_PATH, ADMIN_PASSWORD,
    PSEUDONYM_MAPPINGS_PATH, PROCESSED_DATA_DIR_PATH,
    POSITION_HIERARCHY_PATH, PROJECT_ROOT
)
from src.modules.wordcloud_generator import WordCloudGenerator
from src.modules.pseudonym_manager import PseudonymManager

SKIP_COLUMNS = {
    'evaluation_id', 'session_id', 'evaluator_id',
    'evaluation_document', 'evaluation_document_original',
    'version', 'data_integrity_hash',
    'target_employee_id',
    'evaluator_hierarchy_level', 'target_hierarchy_level',
}

ROW_FIELDS = {
    'evaluation_date__year': {'label': '평가 연도', 'field': 'evaluation_date', 'modifier': 'year'},
    'evaluation_date__month': {'label': '평가 월', 'field': 'evaluation_date', 'modifier': 'month'},
    'batch_id': {'label': '배치(회차)', 'field': 'batch_id', 'modifier': None},
    'evaluation_date': {'label': '평가 일자', 'field': 'evaluation_date', 'modifier': None},
}

COL_MODES = {
    'department': {'label': '부서별', 'type': 'evaluator', 'field': 'evaluator_department'},
    'position_detail': {'label': '직책별(세부)', 'type': 'evaluator', 'field': 'evaluator_position'},
    'position_3tier': {'label': '직책별(3등분)', 'type': 'evaluator', 'field': 'position_3tier'},
    'all': {'label': '전체', 'type': 'evaluator', 'field': None},
}

ANALYSIS_TYPES = {
    'nlp': {'label': 'NLP 단어 분석', 'type': 'analysis'},
    'emotion': {'label': '감정 분석', 'type': 'analysis'},
    'leadership': {'label': '리더십 분석', 'type': 'analysis'},
    'profanity': {'label': '욕설 분석', 'type': 'analysis'},
    'sarcasm': {'label': '비꼼 분석', 'type': 'analysis'},
}

USER_OUTPUT_DIR = os.path.join(OUTPUTS_DIR_PATH, '유저')
DEPLOY_OUTPUT_DIR = os.path.join(OUTPUTS_DIR_PATH, '배포')


def _get_pseudo_mgr():
    return PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)


def load_position_hierarchy(hierarchy_path=None):
    if hierarchy_path is None:
        hierarchy_path = POSITION_HIERARCHY_PATH
    if not os.path.exists(hierarchy_path):
        return []
    with open(hierarchy_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('hierarchy', [])


def save_position_hierarchy(hierarchy, hierarchy_path=None):
    if hierarchy_path is None:
        hierarchy_path = POSITION_HIERARCHY_PATH
    os.makedirs(os.path.dirname(hierarchy_path), exist_ok=True)
    with open(hierarchy_path, 'w', encoding='utf-8') as f:
        json.dump({'hierarchy': hierarchy}, f, ensure_ascii=False, indent=2)


def get_position_level(name, hierarchy):
    for entry in hierarchy:
        if entry['name'] == name:
            return entry['level']
    return None


def get_position_grade(name, hierarchy):
    for entry in hierarchy:
        if entry['name'] == name:
            return entry.get('grade', entry.get('level'))
    return None


def get_relative_groups(name, hierarchy):
    target_grade = get_position_grade(name, hierarchy)
    if target_grade is None:
        return {'junior': [], 'peer': [], 'senior': []}
    junior = []
    peer = []
    senior = []
    for entry in hierarchy:
        entry_grade = entry.get('grade', entry.get('level'))
        if entry_grade < target_grade:
            junior.append(entry['name'])
        elif entry_grade == target_grade:
            peer.append(entry['name'])
        else:
            senior.append(entry['name'])
    return {'junior': junior, 'peer': peer, 'senior': senior}


def _get_pseudonym_fields(batch_summary):
    fields = batch_summary.get('processing_config', {}).get('pseudonym_fields', [])
    return fields if isinstance(fields, list) else []


def _enrich_with_real_ids(results, pseudonym_fields, enrich=False):
    if not enrich:
        return results
    mgr = _get_pseudo_mgr()
    RESULT_LEVEL_MAP = {
        'target_employee_id': 'employee_id',
        'target_employee_department': 'employee_department',
        'target_employee_position': 'employee_position',
    }
    if not pseudonym_fields:
        pseudonym_fields = list(RESULT_LEVEL_MAP.keys())
    for item in results:
        ev = item.get('evaluation', {})
        for field in pseudonym_fields:
            if field in ev and isinstance(ev[field], str):
                ev[f"{field}_real"] = mgr.get_real_id(ev[field])
            result_key = RESULT_LEVEL_MAP.get(field)
            if result_key and result_key in item and isinstance(item[result_key], str):
                item[f"{result_key}_real"] = mgr.get_real_id(item[result_key])
    return results


def _build_column_label_map(batch_summary):
    label_map = {}
    mappings = batch_summary.get('processing_config', {}).get('mappings', {})
    for field, csv_col in mappings.items():
        if isinstance(csv_col, str) and csv_col.strip():
            label_map[field] = csv_col.strip()
    return label_map


def _field_to_label(field_name):
    KNOWN_LABELS = {
        'evaluator_position': '평가자 직책',
        'evaluator_department': '평가자 부서',
        'evaluation_date': '평가 실시 일',
        'evaluation_date__year': '평가 연도',
        'evaluation_date__month': '평가 월',
        'target_employee_department': '대상자 부서',
        'target_employee_position': '대상자 직책',
        'preprocessing_results': '전처리 결과',
    }
    return KNOWN_LABELS.get(field_name, field_name.replace('_', ' '))


def _get_eval_field_value(ev, raw_field):
    parts = raw_field.split('__', 1)
    base_field = parts[0]
    modifier = parts[1] if len(parts) > 1 else None
    raw_val = ev.get(base_field)
    if raw_val is None:
        return None
    if modifier == 'year':
        if isinstance(raw_val, str) and len(raw_val) >= 4:
            return raw_val[:4]
        return None
    elif modifier == 'month':
        if isinstance(raw_val, str) and len(raw_val) >= 7:
            parts = raw_val.split('-')
            if len(parts) >= 2:
                return parts[1]
        return None
    return raw_val


def _resolve_field_name(raw_field):
    return raw_field.split('__')[0]


def load_batch_summary(batch_path):
    summary_path = os.path.join(batch_path, "tmeta", "batch_summary.json")
    if not os.path.exists(summary_path):
        return None
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_batches(processed_data_dir=None):
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH
    batch_dir = os.path.join(processed_data_dir, 'batch')
    users_dir = os.path.join(processed_data_dir, 'users')

    merged = {
        'batch_info': {'total_evaluations': 0, 'unique_employees': 0, 'batch_count': 0},
        'employee_results': [],
        'batches': [],
    }
    seen_employees = set()
    total_evals = 0

    # 1. Build batch list from lightweight batch_summary.json
    if os.path.exists(batch_dir):
        for item in sorted(os.listdir(batch_dir)):
            item_path = os.path.join(batch_dir, item)
            if not os.path.isdir(item_path) or not item.startswith('batch_'):
                continue
            summary = load_batch_summary(item_path)
            if not summary:
                continue
            merged['batches'].append({
                'batch_id': item, 'path': item_path,
                'created_at': summary.get('batch_info', {}).get('created_at', ''),
                'employee_count': summary.get('batch_info', {}).get('unique_employees', 0),
                'total_evaluations': summary.get('batch_info', {}).get('total_evaluations', 0),
            })
            # Collect employee IDs from lightweight employee_ids list
            for emp_id in summary.get('employee_ids', []):
                if emp_id:
                    seen_employees.add(emp_id)

    # 2. Read user data from users/*.json (primary source)
    if os.path.exists(users_dir):
        for fname in sorted(os.listdir(users_dir)):
            if not fname.endswith('.json'):
                continue
            path = os.path.join(users_dir, fname)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    user = json.load(f)
            except Exception:
                continue
            emp_id = user.get('employee_id', '')
            if not emp_id:
                continue
            evals = user.get('evaluations', [])
            total_evals += len(evals)
            merged['employee_results'].append({
                'metadata': {
                    'target_employee_id': emp_id,
                    'target_employee_name': user.get('name', ''),
                    'target_employee_department': user.get('department', ''),
                    'target_employee_position': user.get('position', ''),
                    'evaluations': evals,
                }
            })

    # 3. Fallback: if no users/*.json yet, read from old batch_summary format
    if not merged['employee_results'] and os.path.exists(batch_dir):
        for item in sorted(os.listdir(batch_dir)):
            item_path = os.path.join(batch_dir, item)
            if not os.path.isdir(item_path) or not item.startswith('batch_'):
                continue
            summary = load_batch_summary(item_path)
            if not summary:
                continue
            old_results = summary.get('employee_results', [])
            if not old_results:
                continue
            for er in old_results:
                meta = er.get('metadata', {})
                emp_id = meta.get('target_employee_id')
                if emp_id:
                    seen_employees.add(emp_id)
                meta.setdefault('evaluations', [])
                for ev in meta['evaluations']:
                    ev['batch_id'] = item
                merged['employee_results'].append(er)
            break  # Only use old format once (all batches have same structure)

    total_evals = max(total_evals, sum(
        len(er.get('metadata', {}).get('evaluations', []))
        for er in merged['employee_results']
    ))

    merged['batch_info']['total_evaluations'] = total_evals
    merged['batch_info']['unique_employees'] = max(len(seen_employees), len(merged['employee_results']))
    merged['batch_info']['batch_count'] = len(merged['batches'])
    return merged


def filter_evaluations(batch_summary, filters, employee_id=None, enrich=False):
    if not filters:
        return []
    results = []
    for er in batch_summary.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if employee_id and emp_id != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            conds = []
            for f in filters:
                col = f.get('column', f.get('column_name'))
                vals = f.get('values', [f.get('value', f.get('column_value'))])
                ev_val = _get_eval_field_value(ev, col)
                conds.append(ev_val in vals)
            if not conds:
                continue
            groups = [[0]]
            for i in range(1, len(conds)):
                connector = filters[i].get('connector', 'and')
                if connector == 'or':
                    groups[-1].append(i)
                else:
                    groups.append([i])
            group_results = [any(conds[j] for j in g) for g in groups]
            if all(group_results):
                results.append({
                    'evaluation': ev,
                    'employee_id': emp_id,
                    'employee_department': meta.get('target_employee_department'),
                    'employee_position': meta.get('target_employee_position'),
                })
    pseudonym_fields = _get_pseudonym_fields(batch_summary)
    results = _enrich_with_real_ids(results, pseudonym_fields, enrich)
    return results


def extract_words(filtered_evaluations, wordcloud_pos=None, remove_profanity=False):
    if wordcloud_pos is None:
        wordcloud_pos = ['Noun']
    all_words = []
    profanity_set = set()
    employee_ids = set()
    for item in filtered_evaluations:
        ev = item['evaluation']
        employee_ids.add(item['employee_id'])
        nlp = ev.get('nlp_analysis_results', {})
        pos_data = None
        if isinstance(nlp, dict):
            analysis = nlp.get('analysis', {})
            if isinstance(analysis, dict):
                pos_data = analysis.get('meaningful_words_with_pos')
        if pos_data and isinstance(pos_data, list):
            for entry in pos_data:
                if isinstance(entry, list) and len(entry) == 2:
                    word, pos = entry
                    if pos in wordcloud_pos:
                        all_words.append(word)
                elif isinstance(entry, str):
                    all_words.append(entry)
        else:
            meaningful = None
            if isinstance(nlp, dict):
                analysis = nlp.get('analysis', {})
                if isinstance(analysis, dict):
                    meaningful = analysis.get('meaningful_words')
                if not meaningful:
                    meaningful = nlp.get('meaningful_words')
            if meaningful and isinstance(meaningful, list):
                all_words.extend(meaningful)
        if remove_profanity:
            prof = ev.get('profanity_analysis_results', {})
            if isinstance(prof, dict):
                detected = prof.get('detected_profanity', [])
                if isinstance(detected, list):
                    profanity_set.update(detected)
    word_freq = dict(Counter(all_words))
    if remove_profanity and profanity_set:
        for pw in profanity_set:
            pw_clean = pw.replace('legacy:', '')
            if pw_clean in word_freq:
                del word_freq[pw_clean]
    return {
        'word_frequency': word_freq,
        'total_evaluations': len(filtered_evaluations),
        'total_employees': len(employee_ids),
        'profanity_removed': list(profanity_set) if remove_profanity else [],
    }


def calculate_word_scores(filtered_evaluations, word_frequency):
    word_scores = {}
    for word in word_frequency.keys():
        total_score = 0.0
        count = 0
        for item in filtered_evaluations:
            ev = item['evaluation']
            nlp = ev.get('nlp_analysis_results', {})
            meaningful_words = []
            if isinstance(nlp, dict):
                analysis = nlp.get('analysis', {})
                if isinstance(analysis, dict):
                    meaningful_words = analysis.get('meaningful_words', [])
                if not meaningful_words:
                    meaningful_words = nlp.get('meaningful_words', [])
            if word not in meaningful_words:
                continue
            emotion = ev.get('emotion_analysis_results', {})
            pos_score = 0.0
            neg_score = 0.0
            if isinstance(emotion, dict):
                analysis = emotion.get('analysis', {})
                if isinstance(analysis, dict):
                    base_result = analysis.get('base_result', {})
                    if isinstance(base_result, dict):
                        mapped = base_result.get('mapped', {})
                        if isinstance(mapped, dict):
                            scores = mapped.get('sentiment_scores', {})
                            if isinstance(scores, dict):
                                pos_score = scores.get('positive', 0.0) or 0.0
                                neg_score = scores.get('negative', 0.0) or 0.0
            score = pos_score - neg_score
            total_score += score
            count += 1
        word_scores[word] = round(total_score / count, 4) if count > 0 else 0.0
    return word_scores


def _save_wordcloud_to_path(word_freq, word_scores, output_path, options):
    from src.modules.word_boost_manager import get_word_boost_manager
    word_freq = get_word_boost_manager().apply_to_frequency(word_freq)
    generator = WordCloudGenerator(config_path=WORDCLOUD_CONFIG_PATH)
    success = generator.generate_with_colors_and_options(
        word_freq, word_scores, output_path,
        background_color=options.get('background_color', 'white'),
        max_words=options.get('max_words', 100),
        width=options.get('width', 400),
        height=options.get('height', 300),
    )
    return success


def _filters_to_desc(filters):
    parts = []
    for f in filters:
        col = f.get('column', '')
        vals = f.get('values', [f.get('value', '')])
        col_short = col.replace('evaluation_date', 'date').replace('evaluator_', '').replace('__', '_')
        parts.append(f"{col_short}_{'_'.join(str(v) for v in vals)}")
    return '_'.join(parts) if parts else 'all'


def _get_employee_metadata(unified_data, employee_id):
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        if meta.get('target_employee_id') == employee_id:
            return meta
    return None


def _extract_row_values(ev, row_field):
    if row_field == 'batch_id':
        return [ev.get('batch_id', '?')]
    val = _get_eval_field_value(ev, row_field)
    return [str(val)] if val is not None else []


def _extract_col_group(evaluator_ev, col_mode, hierarchy, target_employee_meta, pseudo_mgr=None, output_mode='pseudonym'):
    def _resolve(val):
        if not val:
            return val
        if output_mode == 'real' and pseudo_mgr:
            resolved = pseudo_mgr.get_real_id(str(val))
            return resolved if resolved and resolved != str(val) else val
        return val

    if col_mode == 'all':
        return ['전체']
    if col_mode == 'department':
        val = evaluator_ev.get('evaluator_department', '')
        if val:
            val = _resolve(val)
        return [str(val)] if val else ['알수없음']
    if col_mode == 'position_detail':
        val = evaluator_ev.get('evaluator_position', '')
        if val:
            val = _resolve(val)
        return [str(val)] if val else ['알수없음']
    if col_mode == 'position_3tier':
        target_pos = target_employee_meta.get('target_employee_position', '') if target_employee_meta else ''
        if not target_pos:
            target_pos = evaluator_ev.get('target_employee_position', '')
        if target_pos:
            target_pos = _resolve(target_pos)
        eval_pos = evaluator_ev.get('evaluator_position', '')
        if eval_pos:
            eval_pos = _resolve(eval_pos)
        groups = get_relative_groups(target_pos, hierarchy)
        if eval_pos in groups['junior']:
            return ['부하']
        elif eval_pos in groups['peer']:
            return ['동료']
        elif eval_pos in groups['senior']:
            return ['상위직책']
        return ['알수없음']
    return ['알수없음']


def _aggregate_emotion(filtered_items):
    pos_sum = 0.0
    neg_sum = 0.0
    count = 0
    for item in filtered_items:
        ev = item['evaluation']
        emotion = ev.get('emotion_analysis_results', {})
        scores = {}
        if isinstance(emotion, dict):
            analysis = emotion.get('analysis', {})
            if isinstance(analysis, dict):
                br = analysis.get('base_result', {})
                if isinstance(br, dict):
                    mp = br.get('mapped', {})
                    if isinstance(mp, dict):
                        scores = mp.get('sentiment_scores', {})
        if not isinstance(scores, dict):
            scores = {}
        if scores:
            pos_sum += scores.get('positive', 0.0) or 0.0
            neg_sum += scores.get('negative', 0.0) or 0.0
            count += 1
    return {
        'positive': round(pos_sum / count, 4) if count > 0 else 0,
        'negative': round(neg_sum / count, 4) if count > 0 else 0,
    }


def _generate_nlp_cell(filtered_items, options, save_path):
    word_data = extract_words(filtered_items, wordcloud_pos=options.get('wordcloud_pos', ['Noun']))
    wf = word_data['word_frequency']
    result = {
        'evaluation_count': word_data['total_evaluations'],
        'total_words': len(wf),
        'top_words': dict(Counter(wf).most_common(20)),
    }
    if not wf:
        result['warning'] = '추출된 단어 없음'
        return result

    word_scores = calculate_word_scores(filtered_items, wf)
    emotion_agg = _aggregate_emotion(filtered_items)
    result['avg_sentiment'] = emotion_agg

    if save_path:
        success = _save_wordcloud_to_path(wf, word_scores, save_path, options)
        if success:
            rel_path = os.path.relpath(save_path, OUTPUTS_DIR_PATH).replace('\\', '/')
            result['wordcloud_url'] = f"/outputs/{rel_path}"

    return result


def _generate_emotion_cell(filtered_items):
    emotion_agg = _aggregate_emotion(filtered_items)
    all_labels = []
    for item in filtered_items:
        ev = item['evaluation']
        emotion = ev.get('emotion_analysis_results', {})
        if isinstance(emotion, dict):
            an = emotion.get('analysis', {})
            if isinstance(an, dict):
                br = an.get('base_result', {})
                if isinstance(br, dict):
                    raw = br.get('raw', {})
                    if isinstance(raw, dict):
                        label = raw.get('label', '')
                        if label:
                            all_labels.append(label)
    return {
        'evaluation_count': len(filtered_items),
        'avg_sentiment': emotion_agg,
        'emotion_labels': dict(Counter(all_labels).most_common(10)),
    }


def _generate_leadership_cell(filtered_items):
    total_leadership = 0.0
    count = 0
    competencies_sum = {}
    for item in filtered_items:
        ev = item['evaluation']
        ldr = ev.get('leadership_analysis_results', {})
        if isinstance(ldr, dict):
            score = ldr.get('leadership_score') or ldr.get('overall_leadership_score')
            if score is not None:
                total_leadership += float(score)
                count += 1
            comps = ldr.get('leadership_competencies', {})
            for k, v in comps.items():
                if isinstance(v, (int, float)):
                    competencies_sum[k] = competencies_sum.get(k, 0) + v
    return {
        'evaluation_count': len(filtered_items),
        'avg_leadership_score': round(total_leadership / count, 4) if count > 0 else 0,
        'competencies': {k: round(v / count, 4) for k, v in competencies_sum.items()} if count > 0 else {},
    }


def _generate_profanity_cell(filtered_items):
    total_count = 0
    profanity_words = set()
    for item in filtered_items:
        ev = item['evaluation']
        prof = ev.get('profanity_analysis_results', {})
        if isinstance(prof, dict):
            total_count += prof.get('profanity_count', 0)
            detected = prof.get('detected_profanity', [])
            if isinstance(detected, list):
                profanity_words.update(detected)
    return {
        'evaluation_count': len(filtered_items),
        'total_profanity_count': total_count,
        'profanity_ratio': round(total_count / max(len(filtered_items), 1), 4),
        'profanity_words': list(profanity_words),
    }


def _generate_sarcasm_cell(filtered_items):
    sarcasm_count = 0
    for item in filtered_items:
        ev = item['evaluation']
        sar = ev.get('sarcasm_analysis_results', {})
        if isinstance(sar, dict):
            an = sar.get('analysis', {})
            if isinstance(an, dict):
                for result_key in ['fine_tuned_result', 'sklearn_result']:
                    res = an.get(result_key, {})
                    if isinstance(res, dict):
                        mp = res.get('mapped', {})
                        if isinstance(mp, dict) and mp.get('label') == 'Sarcasm':
                            sarcasm_count += 1
                            break
    return {
        'evaluation_count': len(filtered_items),
        'sarcasm_count': sarcasm_count,
        'non_sarcasm_count': len(filtered_items) - sarcasm_count,
        'sarcasm_ratio': round(sarcasm_count / max(len(filtered_items), 1), 4),
    }


def _generate_cell_content(filtered_items, analysis_type, options, save_path=None):
    if not filtered_items:
        return {'evaluation_count': 0, 'warning': '평가 없음'}
    if analysis_type == 'nlp':
        return _generate_nlp_cell(filtered_items, options, save_path)
    elif analysis_type == 'emotion':
        return _generate_emotion_cell(filtered_items)
    elif analysis_type == 'leadership':
        return _generate_leadership_cell(filtered_items)
    elif analysis_type == 'profanity':
        return _generate_profanity_cell(filtered_items)
    elif analysis_type == 'sarcasm':
        return _generate_sarcasm_cell(filtered_items)
    return _generate_nlp_cell(filtered_items, options, save_path)


def _build_save_path(user_or_deploy, employee_id, row_field, col_mode, analysis_type, row_val, col_val, pseudo_mgr=None, output_mode='pseudonym'):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if user_or_deploy == 'user':
        pseudo = employee_id
        if output_mode == 'real' and pseudo_mgr:
            real_id = pseudo_mgr.get_real_id(employee_id)
            if real_id and real_id != employee_id:
                pseudo = employee_id
        safe_pseudo = re.sub(r'[\\/*?:"<>|]', '_', str(pseudo))
        safe_rv = re.sub(r'[\\/*?:"<>|]', '_', str(row_val))
        safe_cv = re.sub(r'[\\/*?:"<>|]', '_', str(col_val))
        subdir = f"{row_field}_{col_mode}_{analysis_type}"
        filename = f"{safe_rv}_{safe_cv}.png"
        full_dir = os.path.join(USER_OUTPUT_DIR, safe_pseudo, subdir)
        os.makedirs(full_dir, exist_ok=True)
        return os.path.join(full_dir, filename)
    else:
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', str(employee_id))
        filename = f"{safe_name}_{row_field}_{col_mode}_{analysis_type}_{ts}.png"
        return filename


def _get_row_value_counts(unified_data, row_field, employee_id=None):
    counts = {}
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        if employee_id and meta.get('target_employee_id') != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            vals = _extract_row_values(ev, row_field)
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
    return counts


def get_matrix_meta(unified_data, employee_id=None, enrich=False):
    hierarchy = load_position_hierarchy()
    row_options = []
    for key, info in ROW_FIELDS.items():
        vals = _get_row_value_counts(unified_data, key, employee_id)
        if vals:
            vals_sorted = sorted(vals.items(), key=lambda x: (-x[1], x[0]))
            row_options.append({
                'field': key,
                'label': info['label'],
                'values': [{'value': v, 'count': c} for v, c in vals_sorted],
            })
    col_modes = [{'mode': k, 'label': v['label'], 'type': v['type']} for k, v in COL_MODES.items()]
    analysis_types = [{'mode': k, 'label': v['label'], 'type': v['type']} for k, v in ANALYSIS_TYPES.items()]
    pseudo_mgr = _get_pseudo_mgr() if enrich else None
    employees = []
    seen = set()
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if emp_id and emp_id not in seen:
            seen.add(emp_id)
            entry = {
                'employee_id': emp_id,
                'department': meta.get('target_employee_department'),
                'position': meta.get('target_employee_position'),
                'evaluation_count': meta.get('total_evaluations', 0),
                'employee_name': None,  # 가명 모드에서는 실제 이름 노출 안 함
            }
            if enrich and pseudo_mgr:
                def _dr(v):
                    if not v:
                        return v
                    r = pseudo_mgr.get_real_id(str(v))
                    return r if r != v else v
                real_id = _dr(emp_id)
                entry['employee_id_real'] = real_id if real_id != emp_id else None
                entry['employee_name'] = meta.get('target_employee_name') or None
                entry['department'] = _dr(entry.get('department')) if entry.get('department') else entry.get('department')
                entry['position'] = _dr(entry.get('position')) if entry.get('position') else entry.get('position')
            employees.append(entry)
    employees.sort(key=lambda e: e['employee_id'] or '')

    return {
        'row_options': row_options,
        'col_modes': col_modes,
        'analysis_types': analysis_types,
        'employees': employees,
        'position_hierarchy': hierarchy,
        'batch_count': unified_data.get('batch_info', {}).get('batch_count', 0),
        'total_evaluations': unified_data.get('batch_info', {}).get('total_evaluations', 0),
    }


def _get_evaluations_for_employee(unified_data, employee_id):
    items = []
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        if meta.get('target_employee_id') != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            items.append({
                'evaluation': ev,
                'employee_id': employee_id,
                'employee_department': meta.get('target_employee_department'),
                'employee_position': meta.get('target_employee_position'),
            })
    return items


def _sort_keys(keys, row_field):
    if row_field == 'evaluation_date':
        return sorted(keys)
    elif row_field == 'evaluation_date__year':
        return sorted(keys)
    elif row_field == 'evaluation_date__month':
        return sorted(keys, key=lambda x: int(x) if x.isdigit() else x)
    elif row_field == 'batch_id':
        return sorted(keys)
    return sorted(keys)


def _sort_col_keys(keys, col_mode, hierarchy):
    if col_mode == 'position_detail':
        order = [e['name'] for e in hierarchy]
        order.append('알수없음')
        return [k for k in order if k in keys] + [k for k in keys if k not in order]
    if col_mode == 'position_3tier':
        order = ['부하', '동료', '상위직책', '알수없음', '전체']
        return [k for k in order if k in keys] + [k for k in keys if k not in order]
    return sorted(keys)


def generate_perspective_matrix(unified_data, employee_id, row_field, col_mode, analysis_type, options):
    hierarchy = load_position_hierarchy()
    target_meta = _get_employee_metadata(unified_data, employee_id)
    all_items = _get_evaluations_for_employee(unified_data, employee_id)
    if not all_items:
        return None

    output_mode = options.get('output_mode', 'pseudonym')
    pseudo_mgr = _get_pseudo_mgr() if output_mode == 'real' else None

    row_values = options.get('row_values')
    row_combine_all = options.get('row_combine_all', False)

    row_cells = {}
    col_cells = {}

    for item in all_items:
        ev = item['evaluation']
        row_vals = _extract_row_values(ev, row_field)
        if row_values and not row_combine_all:
            row_vals = [v for v in row_vals if v in row_values]
            if not row_vals:
                continue
        elif row_combine_all:
            if row_values and not any(v in row_values for v in row_vals):
                continue
            row_vals = ['선택 통합']
        col_vals = _extract_col_group(ev, col_mode, hierarchy, target_meta, pseudo_mgr, output_mode)
        for rv in row_vals:
            if rv not in row_cells:
                row_cells[rv] = {}
            for cv in col_vals:
                if cv not in col_cells:
                    col_cells[cv] = True
                if cv not in row_cells[rv]:
                    row_cells[rv][cv] = []
                row_cells[rv][cv].append(item)

    row_keys_sorted = _sort_keys(row_cells.keys(), row_field)
    col_keys_sorted = _sort_col_keys(col_cells.keys(), col_mode, hierarchy)

    matrix = {}
    for rk in row_keys_sorted:
        matrix[rk] = {}
        for ck in col_keys_sorted:
            cell_items = row_cells.get(rk, {}).get(ck, [])
            save_path = _build_save_path(
                'user', employee_id, row_field, col_mode, analysis_type,
                rk, ck, pseudo_mgr, options.get('output_mode', 'pseudonym')
            ) if cell_items else None
            matrix[rk][ck] = _generate_cell_content(cell_items, analysis_type, options, save_path)

    def _deref(val):
        if not val or not pseudo_mgr:
            return val
        resolved = pseudo_mgr.get_real_id(str(val))
        return resolved if resolved != val else val

    pseudo_id = _deref(employee_id) if output_mode == 'real' else employee_id

    raw_name = (target_meta or {}).get('target_employee_name') or ''
    raw_dept = (target_meta or {}).get('target_employee_department') or ''
    # 실제 이름은 원데이터 모드(관리자 인증 완료 후 매트릭스 생성/저장 시)에만 노출
    employee_name = _deref(raw_name) if output_mode == 'real' else None
    employee_department = _deref(raw_dept) if output_mode == 'real' else raw_dept

    return {
        'employee_id': employee_id,
        'employee_id_real': pseudo_id if (output_mode == 'real' and pseudo_id != employee_id) else None,
        'employee_name': employee_name or None,
        'employee_department': employee_department or None,
        'row_field': row_field,
        'row_label': ROW_FIELDS.get(row_field, {}).get('label', row_field),
        'col_mode': col_mode,
        'col_label': COL_MODES.get(col_mode, {}).get('label', col_mode),
        'analysis_type': analysis_type,
        'rows': row_keys_sorted,
        'columns': col_keys_sorted,
        'matrix': matrix,
    }


def _setup_korean_font():
    try:
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt
        import platform
        system = platform.system()
        if system == 'Windows':
            candidates = [
                'C:/Windows/Fonts/malgun.ttf',
                'C:/Windows/Fonts/malgunsl.ttf',
                'C:/Windows/Fonts/gulim.ttc',
            ]
            for font_path in candidates:
                if os.path.exists(font_path):
                    fm.fontManager.addfont(font_path)
                    font_name = fm.FontProperties(fname=font_path).get_name()
                    plt.rcParams['font.family'] = font_name
                    break
    except Exception:
        pass


def _save_cell_wordcloud(cell_items, sentiment_filter, options, cell_path):
    """셀 워드클라우드를 PIL Image로 생성하고 파일 저장 후 Image 객체 반환."""
    from PIL import Image
    word_data = extract_words(cell_items, wordcloud_pos=options.get('wordcloud_pos', ['Noun']))
    wf = word_data['word_frequency']
    if sentiment_filter == 'positive':
        word_scores = calculate_word_scores(cell_items, wf)
        wf = {w: c for w, c in wf.items() if word_scores.get(w, 0) > 0}
    elif sentiment_filter == 'negative':
        word_scores = calculate_word_scores(cell_items, wf)
        wf = {w: c for w, c in wf.items() if word_scores.get(w, 0) < 0}
    if wf:
        word_scores = calculate_word_scores(cell_items, wf)
        _save_wordcloud_to_path(wf, word_scores, cell_path, options)
        return Image.open(cell_path).convert('RGB')
    return None


def save_to_deploy(unified_data, employee_id, row_field, col_mode, analysis_type, options, request=None):
    _setup_korean_font()
    output_mode = options.get('output_mode', 'pseudonym')

    target_meta = _get_employee_metadata(unified_data, employee_id)

    include_name = options.get('include_name', True)
    include_id   = options.get('include_id', True)

    if output_mode == 'real' and (include_name or include_id):
        pseudo_mgr = _get_pseudo_mgr()
        # 사번: 가명 → 원본 역변환
        real_id = pseudo_mgr.get_real_id(employee_id)
        real_id = real_id if (real_id and real_id != employee_id) else None
        # 이름: target_employee_name도 가명화 대상이므로 역변환
        raw_name = (target_meta or {}).get('target_employee_name', '') or ''
        real_name = pseudo_mgr.get_real_id(raw_name) if raw_name else ''
        if not real_name or real_name == employee_id or real_name == raw_name == employee_id:
            real_name = ''

        parts = []
        if include_name and real_name:
            parts.append(real_name)
        if include_id and real_id and real_id not in parts:
            parts.append(real_id)
        deploy_name = '_'.join(parts) if parts else employee_id
    else:
        deploy_name = employee_id

    all_items = _get_evaluations_for_employee(unified_data, employee_id)
    if not all_items:
        return None

    row_values = options.get('row_values')
    row_combine_all = options.get('row_combine_all', False)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', str(deploy_name))

    wordcloud_pos = options.get('wordcloud_pos', ['Noun'])
    os.makedirs(DEPLOY_OUTPUT_DIR, exist_ok=True)

    wc_options = {
        'background_color': options.get('background_color', 'white'),
        'max_words': options.get('max_words', 100),
        'width': options.get('width', 800),
        'height': options.get('height', 600),
    }

    def _save_wc(wf, scores, suffix, filename):
        if not wf:
            return None
        sub_dir = os.path.join(DEPLOY_OUTPUT_DIR, suffix)
        os.makedirs(sub_dir, exist_ok=True)
        path = os.path.join(sub_dir, f"{filename}.png")
        ok = _save_wordcloud_to_path(wf, scores, path, wc_options)
        if ok and os.path.exists(path):
            rel = os.path.relpath(path, OUTPUTS_DIR_PATH).replace('\\', '/')
            return f"/outputs/{rel}?v={ts}"
        return None

    def _generate_wc_for_items(items, label_suffix):
        word_data = extract_words(items, wordcloud_pos=wordcloud_pos)
        wf_all = word_data['word_frequency']
        if not wf_all:
            return None, None, None
        word_scores = calculate_word_scores(items, wf_all)
        wf_positive = {w: c for w, c in wf_all.items() if word_scores.get(w, 0) > 0}
        wf_negative = {w: c for w, c in wf_all.items() if word_scores.get(w, 0) < 0}
        filename = f"{safe_name}_{label_suffix}" if label_suffix else safe_name
        combined_url = _save_wc(wf_all, word_scores, '통합', filename)
        positive_url = _save_wc(wf_positive, {w: s for w, s in word_scores.items() if w in wf_positive}, '긍정', filename)
        negative_url = _save_wc(wf_negative, {w: s for w, s in word_scores.items() if w in wf_negative}, '부정', filename)
        return combined_url, positive_url, negative_url

    # 통합 출력: 선택된 값들을 하나로 합산
    if row_combine_all:
        filtered_items = []
        for item in all_items:
            ev = item['evaluation']
            row_vals = _extract_row_values(ev, row_field)
            if row_values and not any(v in row_values for v in row_vals):
                continue
            filtered_items.append(item)
        if not filtered_items:
            return None
        combined_url, positive_url, negative_url = _generate_wc_for_items(filtered_items, '통합')
        return {
            'name': deploy_name,
            'timestamp': ts,
            'combined': combined_url,
            'positive': positive_url,
            'negative': negative_url,
            '통합': combined_url,
            '긍정': positive_url,
            '부정': negative_url,
        }

    # 개별 출력: 선택된 각 값별로 별도 파일 생성
    targets = row_values if row_values else sorted(set(
        v for item in all_items
        for v in _extract_row_values(item['evaluation'], row_field)
    ))

    row_results = {}
    for rv in targets:
        items_for_rv = []
        for item in all_items:
            ev = item['evaluation']
            if rv in _extract_row_values(ev, row_field):
                items_for_rv.append(item)
        if not items_for_rv:
            continue
        safe_rv = re.sub(r'[\\/*?:"<>|]', '_', str(rv))
        c_url, p_url, n_url = _generate_wc_for_items(items_for_rv, f'{safe_rv}_개별')
        row_results[rv] = {'combined': c_url, 'positive': p_url, 'negative': n_url}

    if not row_results:
        return None

    return {
        'name': deploy_name,
        'timestamp': ts,
        'row_results': row_results,
        # 첫 번째 결과를 대표값으로 노출 (기존 필드 호환)
        'combined': next((v['combined'] for v in row_results.values() if v['combined']), None),
        'positive': next((v['positive'] for v in row_results.values() if v['positive']), None),
        'negative': next((v['negative'] for v in row_results.values() if v['negative']), None),
    }


def parse_csv_employee_ids(content):
    import csv, io
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return []

    header = rows[0]
    id_col_idx = None
    possible_names = ['employee_id', '사번', 'ID', 'emp_id', '직원ID', '대상자ID', '아이디', '직원번호', 'id', 'employeeid', 'empno']
    for name in possible_names:
        for i, col in enumerate(header):
            if col.strip().lower() == name.lower():
                id_col_idx = i
                break
        if id_col_idx is not None:
            break

    if id_col_idx is not None:
        ids = [row[id_col_idx].strip() for row in rows[1:] if len(row) > id_col_idx and row[id_col_idx].strip()]
    else:
        ids = [row[0].strip() for row in rows if row and row[0].strip()]

    return ids


def generate_all_employee_matrix(unified_data, row_field, col_mode, analysis_type, options, employee_ids=None):
    hierarchy = load_position_hierarchy()
    employees = []
    seen = set()
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if emp_id and emp_id not in seen:
            seen.add(emp_id)
            if employee_ids is None or emp_id in employee_ids:
                employees.append({
                    'employee_id': emp_id,
                    'department': meta.get('target_employee_department'),
                    'position': meta.get('target_employee_position'),
                })

    def process_emp(emp):
        emp_id = emp['employee_id']
        try:
            result = generate_perspective_matrix(unified_data, emp_id, row_field, col_mode, analysis_type, options)
            return emp_id, result
        except Exception as e:
            return emp_id, {'error': str(e)}

    results = {}
    num_workers = min(multiprocessing.cpu_count(), 4)
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_emp, emp): emp['employee_id'] for emp in employees}
        for future in as_completed(futures):
            emp_id = futures[future]
            try:
                emp_result = future.result()
                if isinstance(emp_result, tuple):
                    emp_id, emp_result = emp_result
                results[emp_id] = emp_result
            except Exception as e:
                results[emp_id] = {'error': str(e)}
    return results
