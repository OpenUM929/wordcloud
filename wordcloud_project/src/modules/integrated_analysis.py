#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
메타데이터 통합 분석 모듈
"""

import os
import json
from datetime import datetime
from collections import Counter
from src.modules.leadership_analysis import LeadershipAnalysis

def calculate_consolidated_analysis(evaluations):
    """
    평가 리스트의 통합 분석 계산 - 단일 소스로 통일
    
    Args:
        evaluations (list): 평가 데이터 리스트
        
    Returns:
        dict: 통합 분석 결과
    """
    all_cleaned_texts = []
    all_emotion_words = {"positive": [], "negative": [], "neutral": []}
    all_nlp_words = []
    individual_leadership_results = []
    detected_profanities = []

    # 문장단위 감정보정(override) 누적 — 통합 감정/단어버킷을 perspective 화면과 동일하게.
    # _get_sentence_level_scores는 저장된 sentence_emotion_cache를 재사용(KoTE 재실행 없음).
    from src.services.perspective_service import _get_sentence_level_scores
    total_pos_mass = 0.0
    total_neg_mass = 0.0
    total_sent_count = 0
    neutral_sent_count = 0

    for evaluation in evaluations:
        # 정제된 텍스트 수집
        if 'preprocessing_results' in evaluation:
            all_cleaned_texts.append(evaluation['preprocessing_results']['cleaned_content'])
        elif 'evaluation_document' in evaluation:
            all_cleaned_texts.append(evaluation['evaluation_document'])
        
        # 감정 분석 결과 수집 — 문장단위 감정보정(override) 적용 라벨로 집계.
        # positive_rescue·negation_praise·no_response_neutral 등 신규 규칙을 메타데이터에 반영한다.
        # 라벨은 문장 override 점수의 pos/neg 질량 비교로 결정(perspective _aggregate_emotion과 동일 의미).
        if 'emotion_analysis_results' in evaluation:
            doc_text = evaluation.get('evaluation_document', '') or ''
            _sent_scores = _get_sentence_level_scores(
                doc_text, sentence_cache=evaluation.get('sentence_emotion_cache'))
            _pos_mass = sum(max(0.0, s) for _, s, _, _, _ in _sent_scores)
            _neg_mass = sum(max(0.0, -s) for _, s, _, _, _ in _sent_scores)
            if _pos_mass > _neg_mass:
                sentiment = "positive"
            elif _neg_mass > _pos_mass:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            # 통합 감정용 누적(override 질량 기반)
            total_pos_mass += _pos_mass
            total_neg_mass += _neg_mass
            total_sent_count += len(_sent_scores)
            neutral_sent_count += sum(1 for _, s, _, _, _ in _sent_scores if s == 0)

            # NLP 결과에서 meaningful words 추출
            if 'nlp_analysis_results' in evaluation:
                if 'analysis' in evaluation['nlp_analysis_results'] and 'meaningful_words' in evaluation['nlp_analysis_results']['analysis']:
                    meaningful_words = evaluation['nlp_analysis_results']['analysis']['meaningful_words']
                elif 'meaningful_words' in evaluation['nlp_analysis_results']:
                    meaningful_words = evaluation['nlp_analysis_results']['meaningful_words']
                else:
                    meaningful_words = []
                
                if sentiment == "positive":
                    all_emotion_words["positive"].extend(meaningful_words)
                elif sentiment == "negative":
                    all_emotion_words["negative"].extend(meaningful_words)
                else:
                    all_emotion_words["neutral"].extend(meaningful_words)
        
        # NLP 분석 결과 수집
        if 'nlp_analysis_results' in evaluation:
            if 'analysis' in evaluation['nlp_analysis_results'] and 'meaningful_words' in evaluation['nlp_analysis_results']['analysis']:
                all_nlp_words.extend(evaluation['nlp_analysis_results']['analysis']['meaningful_words'])
            elif 'meaningful_words' in evaluation['nlp_analysis_results']:
                all_nlp_words.extend(evaluation['nlp_analysis_results']['meaningful_words'])
        
        # 리더십 분석 결과 수집
        if 'leadership_analysis_results' in evaluation:
            individual_leadership_results.append(evaluation['leadership_analysis_results'])
        
        # 욕설 분석 결과 수집
        if 'profanity_analysis_results' in evaluation:
            if 'detected_profanity' in evaluation['profanity_analysis_results']:
                detected_profanities.extend(evaluation['profanity_analysis_results']['detected_profanity'])
    
    # 통합 감정 — 문장단위 감정보정(override) 질량 기반 결정.
    # perspective 화면의 _aggregate_emotion과 동일하게 pos/neg 질량을 비교한다(중립은 신호 부재).
    mass_total = total_pos_mass + total_neg_mass
    consolidated_sentiment = "neutral"
    if total_pos_mass > total_neg_mass:
        consolidated_sentiment = "positive"
    elif total_neg_mass > total_pos_mass:
        consolidated_sentiment = "negative"

    # 신뢰도 - 우세 감정 질량 비율. 중립은 중립 문장 비율로 표현(질량 신호 없음).
    if consolidated_sentiment == "positive":
        confidence_score = (total_pos_mass / mass_total) if mass_total > 0 else 0.0
    elif consolidated_sentiment == "negative":
        confidence_score = (total_neg_mass / mass_total) if mass_total > 0 else 0.0
    else:
        confidence_score = (neutral_sent_count / total_sent_count) if total_sent_count > 0 else 0.0
    
    # 단어 빈도 계산
    word_freq = dict(Counter(all_nlp_words))

    # 욕설 통계 계산
    all_profanity_words = []
    total_profanity_count = 0
    evaluations_with_profanity = 0

    for evaluation in evaluations:
        profanity_results = evaluation.get("profanity_analysis_results", {})
        profanity_count = profanity_results.get("profanity_count", 0)
        detected_profanity = profanity_results.get("detected_profanity", [])

        # 'legacy:' prefix 제거하고 실제 비속어만 저장
        clean_profanity = []
        for word in detected_profanity:
            if word.startswith('legacy:'):
                clean_profanity.append(word.replace('legacy:', ''))
            elif word != 'korcen_detected':  # korcen_detected는 구체적 단어가 아니므로 제외
                clean_profanity.append(word)

        total_profanity_count += profanity_count
        all_profanity_words.extend(clean_profanity)

        if profanity_count > 0:
            evaluations_with_profanity += 1

    profanity_freq = dict(Counter(all_profanity_words))

    # 리더십 통합 분석
    leadership_analyzer = LeadershipAnalysis()
    leadership_consolidated = leadership_analyzer.consolidate_leadership_analysis(individual_leadership_results)

    # combined_text 계산
    combined_text = ' '.join(all_cleaned_texts)
    
    # evaluator_analysis 계산
    department_distribution = {}
    position_distribution = {}
    hierarchy_level_distribution = {}
    for evaluation in evaluations:
        if 'evaluator_department' in evaluation:
            dept = evaluation['evaluator_department']
            department_distribution[dept] = department_distribution.get(dept, 0) + 1
        if 'evaluator_position' in evaluation:
            pos = evaluation['evaluator_position']
            position_distribution[pos] = position_distribution.get(pos, 0) + 1
        if 'evaluator_hierarchy_level' in evaluation:
            level = evaluation['evaluator_hierarchy_level']
            hierarchy_level_distribution[level] = hierarchy_level_distribution.get(level, 0) + 1
    
    return {
        "combined_cleaned_content": combined_text,
        "overall_sentiment": consolidated_sentiment,
        "confidence_score": round(confidence_score, 3),
        "consolidated_emotion_words": {k: list(set(v)) for k, v in all_emotion_words.items()},
        "consolidated_nlp_words": list(set(all_nlp_words)),
        "word_frequency": word_freq,
        "evaluator_analysis": {
            "department_distribution": department_distribution,
            "position_distribution": position_distribution,
            "hierarchy_level_distribution": hierarchy_level_distribution
        },
        "profanity_consolidated": {
            "total_profanity_count": total_profanity_count,
            "profanity_words": list(set(all_profanity_words)),
            "profanity_frequency": profanity_freq,
            "evaluations_with_profanity": evaluations_with_profanity,
            "profanity_ratio": evaluations_with_profanity / len(evaluations) if evaluations else 0
        },
        "leadership_consolidated": leadership_consolidated
    }
