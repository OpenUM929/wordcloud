"""Wordcloud generation service - handles wordcloud creation and configuration."""

import os
import json
import uuid
from datetime import datetime
from src.config.settings import (
    OUTPUTS_DIR_PATH,
    WORDCLOUD_CONFIG_PATH,
    NLP_CONFIG_PATH,
    PROCESSED_DATA_DIR_PATH
)
from src.modules.wordcloud_generator import WordCloudGenerator


def _filter_freq_by_sentiment(word_freq, word_scores, sentiment):
    if sentiment == 'positive':
        return {w: f for w, f in word_freq.items() if word_scores.get(w, 0) > 0}
    elif sentiment == 'negative':
        return {w: f for w, f in word_freq.items() if word_scores.get(w, 0) < 0}
    return word_freq


def _filter_scores_by_sentiment(word_scores, sentiment):
    if sentiment == 'positive':
        return {w: s for w, s in word_scores.items() if s > 0}
    elif sentiment == 'negative':
        return {w: s for w, s in word_scores.items() if s < 0}
    return word_scores


def regenerate_wordcloud(data):
    """Regenerate wordcloud with specific parameters."""
    try:
        employee_id = data.get('employee_id')
        batch_path = data.get('batch_path')
        wordcloud_pos = data.get('wordcloud_pos', ['Noun'])
        background_color = data.get('background_color', 'white')
        apply_emotion_colors = data.get('apply_emotion_colors', True)
        remove_profanity = data.get('remove_profanity', False)
        generate_png = data.get('generate_png', True)
        width = data.get('width', 800)
        height = data.get('height', 600)
        max_words = data.get('max_words', 100)
        sentiment_mode = data.get('wordcloud_sentiment_mode', 'combined')

        if not employee_id or not batch_path:
            return {'success': False, 'error': '직원 ID와 배치 경로가 필요합니다.'}, 400

        # Load metadata
        from src.services.metadata_service import get_batch_metadata
        batch_metadata = get_batch_metadata(batch_path)
        employee_metadata = next((meta for meta in batch_metadata if meta['employee_id'] == employee_id), None)

        if not employee_metadata:
            return {'success': False, 'error': '직원 메타데이터를 찾을 수 없습니다.'}, 404

        metadata = employee_metadata['metadata']
        if not metadata.get('consolidated_analysis', {}).get('word_frequency'):
            return {'success': False, 'error': '워드클라우드 생성을 위한 단어 빈도 정보가 없습니다.'}, 400

        # Calculate word frequency
        filtered_words = []
        if 'evaluations' in metadata:
            for evaluation in metadata['evaluations']:
                if 'nlp_analysis_results' in evaluation:
                    if 'analysis' in evaluation['nlp_analysis_results'] and 'meaningful_words_with_pos' in evaluation['nlp_analysis_results']['analysis']:
                        # 새로운 메타데이터 구조 (analysis 키가 있는 경우)
                        for word, pos in evaluation['nlp_analysis_results']['analysis']['meaningful_words_with_pos']:
                            if pos in wordcloud_pos:
                                filtered_words.append(word)
                    elif 'pos_tags' in evaluation['nlp_analysis_results']:
                        # 기존 메타데이터 구조 (analysis 키가 없는 경우)
                        for word, pos in evaluation['nlp_analysis_results']['pos_tags']:
                            if pos in wordcloud_pos and len(word) > 1 and word not in ['이', '그', '저', '것', '수', '등']:
                                filtered_words.append(word)
                    elif 'meaningful_words' in evaluation['nlp_analysis_results']:
                        # meaningful_words만 있는 경우 (POS 정보가 없는 경우)
                        filtered_words.extend(evaluation['nlp_analysis_results']['meaningful_words'])

        # Collect all profanity words from consolidated analysis
        profanity_words = set()
        if remove_profanity:
            if 'consolidated_analysis' in metadata and 'profanity_consolidated' in metadata['consolidated_analysis']:
                profanity_words.update(metadata['consolidated_analysis']['profanity_consolidated'].get('profanity_words', []))
            else:
                for evaluation in metadata['evaluations']:
                    if 'profanity_analysis_results' in evaluation and 'detected_profanity' in evaluation['profanity_analysis_results']:
                        profanity_words.update(evaluation['profanity_analysis_results']['detected_profanity'])

        from collections import Counter
        new_word_freq = dict(Counter(filtered_words))

        # Remove profanity words from word frequency only if remove_profanity is True
        if remove_profanity and profanity_words:
            new_word_freq = {word: freq for word, freq in new_word_freq.items() if word not in profanity_words}

        if not new_word_freq:
            new_word_freq = metadata['consolidated_analysis']['word_frequency']
            # Also remove profanity from consolidated word frequency if needed
            if remove_profanity and profanity_words:
                new_word_freq = {word: freq for word, freq in new_word_freq.items() if word not in profanity_words}

        # Calculate word scores
        word_scores = {}
        if apply_emotion_colors:
            for word in new_word_freq.keys():
                positive_score = 0.0
                negative_score = 0.0
                pos_count = 0
                neg_count = 0

                for evaluation in metadata["evaluations"]:
                    if "nlp_analysis_results" in evaluation:
                        # Determine meaningful words based on metadata structure
                        if "analysis" in evaluation["nlp_analysis_results"] and "meaningful_words" in evaluation["nlp_analysis_results"]["analysis"]:
                            meaningful_words = evaluation["nlp_analysis_results"]["analysis"]["meaningful_words"]
                        elif "meaningful_words" in evaluation["nlp_analysis_results"]:
                            meaningful_words = evaluation["nlp_analysis_results"]["meaningful_words"]
                        elif "pos_tags" in evaluation["nlp_analysis_results"]:
                            meaningful_words = [word for word, pos in evaluation["nlp_analysis_results"]["pos_tags"] if len(word) > 1 and word not in ['이', '그', '저', '것', '수', '등']]
                        else:
                            continue
                        
                        if word in meaningful_words:
                            # Get sentiment scores based on emotion analysis structure
                            if "analysis" in evaluation["emotion_analysis_results"] and "base_result" in evaluation["emotion_analysis_results"]["analysis"] and "mapped" in evaluation["emotion_analysis_results"]["analysis"]["base_result"]:
                                pos_score = evaluation["emotion_analysis_results"]["analysis"]["base_result"]["mapped"]["sentiment_scores"]["positive"]
                                neg_score = evaluation["emotion_analysis_results"]["analysis"]["base_result"]["mapped"]["sentiment_scores"]["negative"]
                            elif "base_model" in evaluation["emotion_analysis_results"] and "sentiment_scores" in evaluation["emotion_analysis_results"]["base_model"]:
                                pos_score = evaluation["emotion_analysis_results"]["base_model"]["sentiment_scores"]["positive"]
                                neg_score = evaluation["emotion_analysis_results"]["base_model"]["sentiment_scores"]["negative"]
                            else:
                                continue
                            
                            if pos_score > neg_score:
                                positive_score += pos_score
                                pos_count += 1
                            elif neg_score > pos_score:
                                negative_score += neg_score
                                neg_count += 1

                if pos_count > 0 or neg_count > 0:
                    if pos_count > neg_count:
                        word_scores[word] = positive_score / pos_count * 2.5
                    elif neg_count > pos_count:
                        word_scores[word] = - (negative_score / neg_count) * 2.5
                    else:
                        average_pos = positive_score / pos_count
                        average_neg = negative_score / neg_count
                        if average_pos > average_neg:
                            word_scores[word] = average_pos * 2.5
                        elif average_neg > average_pos:
                            word_scores[word] = - average_neg * 2.5
                        else:
                            word_scores[word] = 0.0
                else:
                    word_scores[word] = 0.0

        from src.modules.word_boost_manager import get_word_boost_manager
        new_word_freq = get_word_boost_manager().apply_to_frequency(new_word_freq)

        generator = WordCloudGenerator(config_path=WORDCLOUD_CONFIG_PATH)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        def _generate_one(freq, scores, suffix=''):
            out_name = f"wordcloud_regen_{employee_id}_{timestamp}{suffix}.png"
            out_path = os.path.abspath(os.path.join(OUTPUTS_DIR_PATH, out_name))
            ok = generator.generate_with_colors_and_options(
                freq, scores, out_path,
                background_color=background_color,
                max_words=max_words,
                width=width,
                height=height
            )
            return (ok, f"/api/wordcloud/outputs/{out_name}")

        if sentiment_mode == 'combined':
            result = {
                'success': True,
                'wordcloud_info': {
                    "word_frequency": new_word_freq,
                    "word_scores": word_scores,
                    "total_words": len(new_word_freq),
                    "morphology_types": wordcloud_pos,
                    "background_color": background_color,
                    "generation_timestamp": datetime.now().isoformat() + 'Z'
                }
            }
            if generate_png:
                ok, url = _generate_one(new_word_freq, word_scores)
                if not ok:
                    return {'success': False, 'error': '워드클라우드 생성 실패'}, 500
                result['wordcloud_url'] = url
            return result

        pos_freq = _filter_freq_by_sentiment(new_word_freq, word_scores, 'positive')
        neg_freq = _filter_freq_by_sentiment(new_word_freq, word_scores, 'negative')
        pos_scores = _filter_scores_by_sentiment(word_scores, 'positive')
        neg_scores = _filter_scores_by_sentiment(word_scores, 'negative')

        result = {'success': True, 'sentiment_mode': sentiment_mode}

        if generate_png:
            if sentiment_mode == 'separate':
                if pos_freq:
                    ok, url = _generate_one(pos_freq, pos_scores, '_positive')
                    result['wordcloud_url_positive'] = url
                if neg_freq:
                    ok, url = _generate_one(neg_freq, neg_scores, '_negative')
                    result['wordcloud_url_negative'] = url

            elif sentiment_mode == 'both':
                if new_word_freq:
                    ok, url = _generate_one(new_word_freq, word_scores)
                    result['wordcloud_url'] = url
                if pos_freq:
                    ok, url = _generate_one(pos_freq, pos_scores, '_positive')
                    result['wordcloud_url_positive'] = url
                if neg_freq:
                    ok, url = _generate_one(neg_freq, neg_scores, '_negative')
                    result['wordcloud_url_negative'] = url

            if not result.get('wordcloud_url') and not result.get('wordcloud_url_positive') and not result.get('wordcloud_url_negative'):
                return {'success': False, 'error': '워드클라우드 생성 실패'}, 500

        result['wordcloud_info'] = {
            "word_frequency": new_word_freq,
            "word_scores": word_scores,
            "total_words": len(new_word_freq),
            "morphology_types": wordcloud_pos,
            "background_color": background_color,
            "generation_timestamp": datetime.now().isoformat() + 'Z'
        }
        return result

    except Exception as e:
        return {'success': False, 'error': f'워드클라우드 재생성 실패: {str(e)}'}, 500


def serve_batch_wordcloud(batch_name, filename):
    """Serve wordcloud file from batch processing."""
    try:
        batch_dir = os.path.abspath(os.path.join(PROCESSED_DATA_DIR_PATH, "batch", batch_name))
        word_dir = os.path.join(batch_dir, 'word')
        wordcloud_path = os.path.join(word_dir, filename)

        if os.path.exists(wordcloud_path):
            from flask import send_from_directory
            return send_from_directory(word_dir, filename)
        else:
            return {'error': f'워드클라우드 파일을 찾을 수 없습니다. Path: {wordcloud_path}'}, 404
    except Exception as e:
        return {'error': f'파일 제공 오류: {str(e)}'}, 500


def update_wordcloud_pos(data):
    """Update wordcloud part-of-speech configuration."""
    try:
        wordcloud_pos = data.get('wordcloud_pos', ["Noun"])

        with open(NLP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            nlp_config = json.load(f)
        nlp_config['wordcloud_pos'] = wordcloud_pos
        with open(NLP_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(nlp_config, f, ensure_ascii=False, indent=2)

        sample_text = "영화가 정말 재미있었어. 날씨가 너무 추워서 짜증 나. 교통이 너무 막혀서 화나. 친구가 도와줘서 고마워. 케이크가 맛있어서 행복해."
        sentences = sample_text.strip().split('\n')
        sentences = [s.strip() for s in sentences if s.strip()]
        all_text = ' '.join(sentences)

        from src.modules.nlp_analysis import analyze_text
        nlp_result = analyze_text(all_text, config_path=NLP_CONFIG_PATH)
        meaningful_words = []
        if 'analysis' in nlp_result and 'okt' in nlp_result['analysis']:
            okt_result = nlp_result['analysis']['okt']
            pos_tags = okt_result.get('pos_tags', [])
            meaningful_words = [word for word, pos in pos_tags if pos in wordcloud_pos and len(word) > 1 and word not in ['이', '그', '저', '것', '수', '등']]

        from collections import Counter
        word_freq = dict(Counter(meaningful_words))

        word_scores = {}
        for sentence in sentences:
            from src.modules.emotion_analysis import analyze_emotion
            emotion_result = analyze_emotion(sentence)

            score = 0.0
            if "analysis" in emotion_result:
                analysis = emotion_result["analysis"]
                if "base_result" in analysis and "mapped" in analysis["base_result"]:
                    base_result = analysis["base_result"]["mapped"]
                    if base_result["sentiment"] == "positive":
                        score = 1.0
                    elif base_result["sentiment"] == "negative":
                        score = -1.0
                    else:
                        score = 0.0

            nlp_result = analyze_text(sentence, config_path=NLP_CONFIG_PATH)
            sentence_words = []
            if 'analysis' in nlp_result and 'okt' in nlp_result['analysis']:
                okt_result = nlp_result['analysis']['okt']
                pos_tags = okt_result.get('pos_tags', [])
                sentence_words = [word for word, pos in pos_tags if pos in wordcloud_pos and len(word) > 1 and word not in ['이', '그', '저', '것', '수', '등']]

            for word in sentence_words:
                word_scores[word] = score

        generator = WordCloudGenerator(config_path=WORDCLOUD_CONFIG_PATH)
        output_path = os.path.abspath(os.path.join(OUTPUTS_DIR_PATH, f"wordcloud_{int(datetime.now().timestamp() * 1000)}.png"))
        success = generator.generate_with_colors(word_freq, word_scores, output_path)

        if success:
            return {'wordcloud_url': f"/api/wordcloud/outputs/{os.path.basename(output_path)}"}
        else:
            return {'error': '워드클라우드 생성 실패'}, 500

    except Exception as e:
        return {'error': str(e)}, 500