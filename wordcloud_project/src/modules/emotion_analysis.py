#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from typing import Dict, Any, Optional
from transformers import pipeline
from utils.logger import setup_logger, get_log_file_path, get_timestamp

class EmotionAnalysis:
    """감정 분석 모듈"""

    def __init__(self, config_path: str = "configs/emotion_config.json"):
        """
        감정 분석기 초기화

        Args:
            config_path: 설정 파일 경로
        """
        # config_path를 절대 경로로 변환
        config_path = os.path.abspath(config_path)
        self.config = self._load_config(config_path)
        self.timestamp = get_timestamp()

        # 프로젝트 루트 계산 (현재 파일 위치 기준)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "../../"))

        # 로거 설정
        log_file = get_log_file_path(self.config["module_name"], self.timestamp)
        self.logger = setup_logger(self.config["module_name"], log_file)
        self.logger.info(f"Project root: {project_root}")

        # 모델 초기화
        self.classifiers = {}

        # 파인튜닝된 모델
        if self.config["model"]["use_fine_tuned"]:
            ft_path = os.path.abspath(os.path.join(project_root, self.config["model"]["fine_tuned_path"]))
            if os.path.exists(ft_path):
                try:
                    self.classifiers["fine_tuned"] = pipeline(
                        self.config["model"]["type"],
                        model=ft_path
                    )
                    self.logger.info("파인튜닝된 모델 로드 완료")
                except Exception as e:
                    self.logger.error(f"파인튜닝 모델 로드 실패: {e}")

        # 기본 모델
        from src.config.settings import MODEL_PATH
        base_path = MODEL_PATH
        self.logger.info(f"기본 모델 경로 확인: {base_path}, 존재: {os.path.exists(base_path)}")
        if os.path.exists(base_path):
            try:
                self.logger.info(f"{os.path.basename(base_path)} 모델 로드 시작...")
                # 로컬 모델 로드 (분류 헤드 추가)
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                self.logger.info("AutoModelForSequenceClassification 로드 중...")
                # num_labels 미지정: 모델 체크포인트의 config에서 자동으로 읽음.
                # 명시하면 저장된 헤드와 크기가 다를 때 무작위 재초기화 위험이 있음.
                model = AutoModelForSequenceClassification.from_pretrained(base_path)
                self.logger.info("AutoTokenizer 로드 중...")
                tokenizer = AutoTokenizer.from_pretrained(base_path)

                self.logger.info("Pipeline 생성 중...")
                # pipeline 대신 직접 모델 호출로 모든 score 얻기
                self.classifiers["base"] = (model, tokenizer)
                self.logger.info(f"로컬 {os.path.basename(base_path)} 모델 로드 완료")
            except Exception as e:
                self.logger.error(f"기본 모델 로드 실패: {e}")
                import traceback
                self.logger.error(f"상세 오류: {traceback.format_exc()}")

        if not self.classifiers:
            raise RuntimeError("사용 가능한 모델이 없습니다.")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """설정 파일 로드"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def analyze(self, text: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        텍스트 감정 분석

        Args:
            text: 분석할 텍스트
            output_path: 결과 저장 경로 (None이면 저장 안함)

        Returns:
            분석 결과 딕셔너리
        """
        self.logger.info(f"감정 분석 시작: {len(text)}자")

        results = {
            "input_text": text,
            "analysis": {}
        }

        # 각 모델별 분석
        for model_name, classifier in self.classifiers.items():
            try:
                if model_name == "base":
                    # 직접 모델 호출로 모든 score 얻기
                    model, tokenizer = classifier
                    inputs = tokenizer(text, return_tensors="pt")
                    outputs = model(**inputs)
                    logits = outputs.logits[0]
                    scores = logits.softmax(dim=0).tolist()
                    
                    # id2label 매핑 (모델 config에서 가져오기)
                    id2label = model.config.id2label
                    
                    # predictions 생성
                    predictions = []
                    for i, score in enumerate(scores):
                        label = id2label[i]
                        predictions.append({"label": label, "score": score})
                    
                    self.logger.info(f"{model_name} 모델 예측 완료")
                else:
                    # 파인튜닝 모델은 pipeline 사용
                    predictions = classifier(text)
                    self.logger.info(f"{model_name} 모델 예측 완료")
                    if isinstance(predictions[0], list):
                        predictions = predictions[0]
                
                # 상위 3개 예측 결과 출력
                top_predictions = sorted(predictions, key=lambda x: x['score'], reverse=True)[:3]
                self.logger.info(f"상위 3개 예측 결과: {[(p['label'], round(p['score'], 4)) for p in top_predictions]}")
                
                prediction = top_predictions[0]

                # 레이블 매핑
                label_id = prediction.get("label", "")
                self.logger.info(f"Raw label ID: {label_id}")  # 디버그용 로그
                
                mapped_label = "알 수 없음"
                if label_id in self.config["labels"]:
                    # 설정 파일에 직접 정의된 레이블인 경우
                    mapped_label = self.config["labels"][label_id]
                elif label_id.startswith("LABEL_"):
                    # LABEL_0, LABEL_1, LABEL_2 형식
                    numeric_label = int(label_id.split("_")[1])
                    mapped_label = self.config["labels"].get(str(numeric_label), "알 수 없음")
                else:
                    # 감정 이름이 직접 오는 경우 (model config의 label2id처럼)
                    # config의 labels에서 값이 label_id인 키 찾기
                    for key, value in self.config["labels"].items():
                        if value == label_id:
                            mapped_label = label_id
                            break
                
                self.logger.info(f"Mapped label: {mapped_label}")  # 디버그용 로그

                # 감성 분류 (0: 긍정, 1: 부정, 2: 중립)
                if label_id.startswith("LABEL_"):
                    numeric_label = int(label_id.split("_")[1])
                    sentiment = self.config["emotion_to_sentiment"].get(str(numeric_label), 2)
                else:
                    # label_id가 감정 이름인 경우, config의 labels에서 해당 이름에 대한 키 찾기
                    numeric_label = None
                    for key, value in self.config["labels"].items():
                        if value == label_id:
                            numeric_label = key
                            break
                    if numeric_label:
                        sentiment = self.config["emotion_to_sentiment"].get(numeric_label, 2)
                    else:
                        sentiment = 2  # 기본값: 중립

                # 감성 문자열로 변환
                sentiment_str = "중립"
                if sentiment == 0:
                    sentiment_str = "긍정"
                elif sentiment == 1:
                    sentiment_str = "부정"

                # 긍정/부정/중립 확률 합산
                positive_score = 0.0
                negative_score = 0.0
                neutral_score = 0.0
                
                for p in predictions:
                    p_label_id = p['label']
                    p_score = p['score']
                    
                    # 감성 분류
                    p_sentiment = 2
                    if p_label_id.startswith("LABEL_"):
                        p_numeric_label = int(p_label_id.split("_")[1])
                        p_sentiment = self.config["emotion_to_sentiment"].get(str(p_numeric_label), 2)
                    else:
                        p_numeric_label = None
                        for key, value in self.config["labels"].items():
                            if value == p_label_id:
                                p_numeric_label = key
                                break
                        if p_numeric_label:
                            p_sentiment = self.config["emotion_to_sentiment"].get(p_numeric_label, 2)
                    
                    if p_sentiment == 0:
                        positive_score += p_score
                    elif p_sentiment == 1:
                        negative_score += p_score
                    else:
                        neutral_score += p_score
                
                self.logger.info(f"긍정: {round(positive_score, 4)}, 부정: {round(negative_score, 4)}, 중립: {round(neutral_score, 4)}")
                
                # 최종 감성 결정
                final_sentiment = 2
                if positive_score > negative_score and positive_score > neutral_score:
                    final_sentiment = 0
                elif negative_score > positive_score and negative_score > neutral_score:
                    final_sentiment = 1
                
                final_sentiment_str = "중립"
                if final_sentiment == 0:
                    final_sentiment_str = "긍정"
                elif final_sentiment == 1:
                    final_sentiment_str = "부정"
                
                # 상위 3개 예측 결과 매핑
                mapped_top_predictions = []
                for p in top_predictions:
                    p_label_id = p['label']
                    p_mapped_label = "알 수 없음"
                    if p_label_id in self.config["labels"]:
                        p_mapped_label = self.config["labels"][p_label_id]
                    elif p_label_id.startswith("LABEL_"):
                        p_numeric_label = int(p_label_id.split("_")[1])
                        p_mapped_label = self.config["labels"].get(str(p_numeric_label), "알 수 없음")
                    else:
                        for key, value in self.config["labels"].items():
                            if value == p_label_id:
                                p_mapped_label = p_label_id
                                break
                    
                    # 감성 분류
                    p_sentiment = 2
                    if p_label_id.startswith("LABEL_"):
                        p_numeric_label = int(p_label_id.split("_")[1])
                        p_sentiment = self.config["emotion_to_sentiment"].get(str(p_numeric_label), 2)
                    else:
                        p_numeric_label = None
                        for key, value in self.config["labels"].items():
                            if value == p_label_id:
                                p_numeric_label = key
                                break
                        if p_numeric_label:
                            p_sentiment = self.config["emotion_to_sentiment"].get(p_numeric_label, 2)
                    
                    p_sentiment_str = "중립"
                    if p_sentiment == 0:
                        p_sentiment_str = "긍정"
                    elif p_sentiment == 1:
                        p_sentiment_str = "부정"
                    
                    mapped_top_predictions.append({
                        "label": p_mapped_label,
                        "sentiment": p_sentiment_str,
                        "confidence": round(p['score'], 4)
                    })

                results["analysis"][f"{model_name}_result"] = {
                    "raw": prediction,
                    "mapped": {
                        "label": mapped_label,
                        "sentiment": final_sentiment_str,
                        "confidence": prediction.get("score", 0.0),
                        "top_3": mapped_top_predictions,
                        "sentiment_scores": {
                            "positive": round(positive_score, 4),
                            "negative": round(negative_score, 4),
                            "neutral": round(neutral_score, 4)
                        }
                    }
                }

                self.logger.info(f"{model_name} 모델 분석 완료: {mapped_label}")
            except Exception as e:
                results["analysis"][f"{model_name}_result"] = {"error": str(e)}
                self.logger.error(f"{model_name} 모델 분석 실패: {e}")

        # 결과 저장
        if output_path and self.config["output"]["save_results"]:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self.logger.info(f"결과 저장 완료: {output_path}")

        self.logger.info("감정 분석 완료")
        return results

# 싱글톤 인스턴스 저장
_emotion_analyzer_instance = None

def analyze_emotion(text: str, config_path: Optional[str] = None,
                   output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    편의 함수: 감정 분석

    Args:
        text: 분석할 텍스트
        config_path: 설정 파일 경로 (None이면 기본 경로 사용)
        output_path: 결과 저장 경로

    Returns:
        분석 결과
    """
    global _emotion_analyzer_instance
    if config_path is None:
        # 기본 config 경로 계산
        from src.config.settings import EMOTION_CONFIG_PATH
        config_path = EMOTION_CONFIG_PATH

    if _emotion_analyzer_instance is None:
        _emotion_analyzer_instance = EmotionAnalysis(config_path)
    return _emotion_analyzer_instance.analyze(text, output_path)