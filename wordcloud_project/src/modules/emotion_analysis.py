#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import threading
import torch
from typing import Dict, Any, Optional
from transformers import pipeline
from utils.logger import setup_logger, get_log_file_path, get_timestamp
from src.modules.kote_shared import KoTEModel

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

        # 기본 모델 (leadership_analysis와 GPU 인스턴스 공유 — 중복 로드 시 VRAM 한도 초과)
        try:
            self.logger.info("공유 KoTE 모델(KoTEModel) 로드 중...")
            shared = KoTEModel()
            # pipeline 대신 직접 모델 호출로 모든 score 얻기
            self.classifiers["base"] = (shared.model, shared.tokenizer)
            self.logger.info(f"공유 KoTE 모델 로드 완료 (device={shared.device})")
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

    def _postprocess_predictions(self, predictions) -> Dict[str, Any]:
        """예측 결과(label/score 리스트) 후처리: top_3, 레이블 매핑, 감성 점수 집계.

        analyze()(단일)와 analyze_batch()(배치) 양쪽에서 공유 — 두 경로의 결과가
        항상 동일한 로직으로 계산되도록 보장(배치화로 인한 결과 오차 방지).
        """
        top_predictions = sorted(predictions, key=lambda x: x['score'], reverse=True)[:3]
        prediction = top_predictions[0]

        # 레이블 매핑
        label_id = prediction.get("label", "")

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
            for key, value in self.config["labels"].items():
                if value == label_id:
                    mapped_label = label_id
                    break

        # 긍정/부정/중립 확률 합산
        positive_score = 0.0
        negative_score = 0.0
        neutral_score = 0.0

        for p in predictions:
            p_label_id = p['label']
            p_score = p['score']

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

        return {
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
                    inputs = {k: v.to(model.device) for k, v in inputs.items()}
                    with torch.no_grad():
                        outputs = model(**inputs)
                    logits = outputs.logits[0]
                    if logits.is_cuda:
                        logits = logits.cpu()
                    scores = logits.softmax(dim=0).tolist()

                    # id2label 매핑 (모델 config에서 가져오기)
                    id2label = model.config.id2label
                    predictions = [{"label": id2label[i], "score": score} for i, score in enumerate(scores)]
                else:
                    # 파인튜닝 모델은 pipeline 사용
                    predictions = classifier(text)
                    if isinstance(predictions[0], list):
                        predictions = predictions[0]

                results["analysis"][f"{model_name}_result"] = self._postprocess_predictions(predictions)
                self.logger.info(f"{model_name} 모델 분석 완료")
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

    def analyze_batch(self, texts: list) -> list:
        """다건 텍스트 배치 추론 ('base' 분류기만 대상).

        sentence_emotion.py처럼 문장 단위로 동일 모델을 반복 호출하던 곳에서
        텍스트를 모아 1회 forward pass로 처리 — GPU 커널 launch 오버헤드 절감.
        파인튜닝 모델(use_fine_tuned)은 현재 비활성 상태라 배치 대상에서 제외.

        Args:
            texts: 분석할 텍스트 리스트

        Returns:
            list[dict]: 각 항목은 analyze()의 단일 반환값과 동일한 구조
                        ({"input_text": ..., "analysis": {"base_result": {...}}})
        """
        if "base" not in self.classifiers:
            raise RuntimeError("base 분류기가 로드되지 않았습니다.")
        model, tokenizer = self.classifiers["base"]

        inputs = tokenizer(texts, return_tensors="pt", truncation=True, padding=True, max_length=512)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs)
        logits = outputs.logits
        if logits.is_cuda:
            logits = logits.cpu()
        scores_batch = logits.softmax(dim=1).tolist()
        id2label = model.config.id2label

        batch_results = []
        for text, scores in zip(texts, scores_batch):
            predictions = [{"label": id2label[i], "score": score} for i, score in enumerate(scores)]
            batch_results.append({
                "input_text": text,
                "analysis": {"base_result": self._postprocess_predictions(predictions)}
            })
        return batch_results

# 싱글톤 인스턴스 저장
_emotion_analyzer_instance = None
_emotion_analyzer_lock = threading.Lock()

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
        with _emotion_analyzer_lock:
            if _emotion_analyzer_instance is None:
                _emotion_analyzer_instance = EmotionAnalysis(config_path)
    return _emotion_analyzer_instance.analyze(text, output_path)


def analyze_emotion_batch(texts: list, config_path: Optional[str] = None) -> list:
    """
    편의 함수: 다건 텍스트 배치 감정 분석 (예: 문장 단위 반복 호출 대체)

    Args:
        texts: 분석할 텍스트 리스트
        config_path: 설정 파일 경로 (None이면 기본 경로 사용)

    Returns:
        list[dict]: analyze_emotion()의 단일 반환값과 동일한 구조의 리스트
    """
    global _emotion_analyzer_instance
    if config_path is None:
        from src.config.settings import EMOTION_CONFIG_PATH
        config_path = EMOTION_CONFIG_PATH

    if _emotion_analyzer_instance is None:
        with _emotion_analyzer_lock:
            if _emotion_analyzer_instance is None:
                _emotion_analyzer_instance = EmotionAnalysis(config_path)
    return _emotion_analyzer_instance.analyze_batch(texts)