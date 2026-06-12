"""
리더십 역량 분석 모듈
KOTE 감정 분석을 기반으로 리더십 관련 역량을 평가합니다.
"""

import torch
import json
import os
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# 환경 변수 로드
load_dotenv()


class LeadershipAnalysis:
    """
    리더십 역량 분석 클래스
    KOTE 모델을 사용하여 텍스트에서 리더십 관련 감정을 분석하고
    6가지 리더십 역량 점수를 계산합니다.
    """

    _instance = None

    def __new__(cls, model_path=None, config_path=None):
        """싱글톤 인스턴스 생성"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 초기화 메서드에서 실제 초기화 수행
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_path=None, config_path=None):
        """
        LeadershipAnalysis 초기화 (싱글톤)

        Args:
            model_path (str): KOTE 모델 경로
            config_path (str): 리더십 분석 설정 파일 경로
        """
        if hasattr(self, '_initialized') and self._initialized:
            return
        """
        LeadershipAnalysis 초기화

        Args:
            model_path (str): KOTE 모델 경로
            config_path (str): 리더십 분석 설정 파일 경로
        """
        if model_path is None:
            from src.config.settings import MODEL_PATH
            model_path = MODEL_PATH
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "../configs/leadership_config.json")

        self.model_path = model_path
        self.config_path = config_path

        # 모델 로드
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True)

        # 감정 이름
        self.emotion_names = [
            "불평/불만", "환영/호의", "감동/감탄", "지긋지긋", "고마움", "슬픔", "화남/분노", "존경", "기대감", "우쭐댐/무시함",
            "안타까움/실망", "비장함", "의심/불신", "뿌듯함", "편안/쾌적", "신기함/관심", "아껴주는", "부끄러움", "공포/무서움", "절망",
            "한심함", "역겨움/징그러움", "짜증", "어이없음", "없음", "패배/자기혐오", "귀찮음", "힘듦/지침", "즐거움/신남", "깨달음",
            "죄책감", "증오/혐오", "흐뭇함(귀여움/예쁨)", "당황/난처", "경악", "부담/안_내킴", "서러움", "재미없음", "불쌍함/연민", "놀람",
            "행복", "불안/걱정", "기쁨", "안심/신뢰"
        ]

        # 리더십 역량 설정
        self.leadership_competencies = {
            "communication": {
                "name": "커뮤니케이션",
                "keywords": ["소통", "의사소통", "대화", "설명", "전달", "청취", "듣다", "말하다", "표현"],
                "emotions": [1, 4, 7, 13, 16, 32, 43],  # 환영/호의, 고마움, 존경, 뿌듯함, 아껴주는, 흐뭇함, 안심/신뢰
                "weight": 1.0
            },
            "leadership": {
                "name": "리더십",
                "keywords": ["리더십", "리더", "지도력", "영도", "인도", "이끌다", "주도", "책임감", "비전"],
                "emotions": [7, 11, 13, 28, 29, 40, 42],  # 존경, 비장함, 뿌듯함, 즐거움/신남, 깨달음, 행복, 기쁨
                "weight": 1.0
            },
            "problem_solving": {
                "name": "문제해결",
                "keywords": ["문제해결", "해결", "분석", "판단", "결정", "논리", "추론", "전략", "대책"],
                "emotions": [13, 29, 30, 33, 34, 41],  # 뿌듯함, 깨달음, 죄책감(반성), 당황/난처, 경악, 불안/걱정
                "weight": 1.0
            },
            "teamwork": {
                "name": "팀워크",
                "keywords": ["팀워크", "협력", "협동", "단합", "화합", "공동", "함께", "협력심", "조화"],
                "emotions": [1, 4, 13, 14, 16, 32, 40, 42, 43],  # 환영/호의, 고마움, 뿌듯함, 편안/쾌적, 아껴주는, 흐뭇함, 행복, 기쁨, 안심/신뢰
                "weight": 1.0
            },
            "innovation": {
                "name": "혁신",
                "keywords": ["혁신", "창의", "창의성", "새로운", "개선", "발전", "진화", "변화", "아이디어"],
                "emotions": [15, 28, 29, 39],  # 신기함/관심, 즐거움/신남, 깨달음, 놀람
                "weight": 1.0
            },
            "ethics": {
                "name": "윤리",
                "keywords": ["윤리", "정직", "신뢰", "책임", "도덕", "공정", "투명", "진실", "약속"],
                "emotions": [7, 13, 16, 30, 43],  # 존경, 뿌듯함, 아껴주는, 죄책감, 안심/신뢰
                "weight": 1.0
            }
        }

        # 설정 로드
        self.config = self._load_config()

    def _load_config(self):
        """설정 파일 로드"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")

        # 기본 설정
        return {
            "emotion_to_sentiment": {
                # 긍정 감정
                1: 0, 2: 0, 4: 0, 7: 0, 8: 0, 11: 0, 13: 0, 14: 0, 16: 0, 28: 0, 29: 0, 32: 0, 38: 0, 40: 0, 42: 0, 43: 0,
                # 부정 감정
                0: 1, 3: 1, 5: 1, 6: 1, 9: 1, 10: 1, 12: 1, 17: 1, 18: 1, 19: 1, 20: 1, 21: 1, 22: 1, 23: 1, 25: 1, 26: 1,
                27: 1, 30: 1, 31: 1, 33: 1, 34: 1, 35: 1, 36: 1, 37: 1, 41: 1,
                # 중립 감정
                15: 2, 24: 2, 39: 2
            },
            "weights": {str(i): {"positive": 1.0, "negative": 1.0} for i in range(44)}
        }

    def analyze_leadership(self, text):
        """
        텍스트에서 리더십 역량 분석

        Args:
            text (str): 분석할 텍스트

        Returns:
            dict: 리더십 분석 결과
        """
        try:
            # 감정 분석 수행
            emotion_result = self._analyze_emotions(text)

            # 리더십 역량 계산
            leadership_scores = {}
            total_score = 0.0

            for competency_key, competency_info in self.leadership_competencies.items():
                score = self._calculate_competency_score(text, emotion_result, competency_info)
                leadership_scores[competency_key] = score
                total_score += score * competency_info["weight"]

            overall_score = total_score / len(self.leadership_competencies)

            # 키워드 추출
            key_indicators = self._extract_leadership_keywords(text)

            # 리더십 감정 분류
            leadership_sentiment = self._classify_leadership_sentiment(leadership_scores)

            # 강점과 개선점 식별
            strengths, weaknesses = self._identify_strengths_and_weaknesses(leadership_scores)

            return {
                "leadership_score": round(overall_score, 3),
                "leadership_sentiment": leadership_sentiment,
                "confidence": round(emotion_result.get("confidence", 0.5), 3),
                "key_phrases": key_indicators,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "leadership_competencies": leadership_scores,
                "overall_leadership_score": round(overall_score, 3),
                "key_leadership_indicators": key_indicators,
                "emotion_analysis": emotion_result
            }

        except Exception as e:
            print(f"리더십 분석 실패: {e}")
            return self._get_default_result()

    def _identify_strengths_and_weaknesses(self, leadership_scores):
        """
        리더십 강점과 개선점 식별

        Args:
            leadership_scores (dict): 역량별 점수

        Returns:
            tuple: (강점 리스트, 개선점 리스트)
        """
        strengths = []
        weaknesses = []

        # 역량별로 평가 (0.7 이상: 강점, 0.4 미만: 개선점)
        for competency, score in leadership_scores.items():
            competency_info = self.leadership_competencies.get(competency, {})
            competency_name = competency_info.get("name", competency)

            if score >= 0.7:
                strengths.append(competency_name)
            elif score < 0.4:
                weaknesses.append(competency_name)

        return strengths, weaknesses

    def _analyze_emotions(self, text):
        """감정 분석 수행"""
        try:
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)

            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)[0]

            # 감정 확률 추출 (상위 5개)
            top_emotions = []
            for i, prob in enumerate(probs):
                if prob > 0.01:  # 1% 이상인 감정만
                    top_emotions.append({
                        "emotion": self.emotion_names[i],
                        "probability": round(prob.item(), 4),
                        "sentiment": self.config["emotion_to_sentiment"].get(i, 2)  # 0: 긍정, 1: 부정, 2: 중립
                    })

            top_emotions.sort(key=lambda x: x["probability"], reverse=True)
            top_emotions = top_emotions[:5]  # 상위 5개만

            # 전체 감정 점수 계산
            pos_score = sum(prob for emotion in top_emotions if emotion["sentiment"] == 0 for prob in [emotion["probability"]])
            neg_score = sum(prob for emotion in top_emotions if emotion["sentiment"] == 1 for prob in [emotion["probability"]])

            overall_sentiment = "neutral"
            confidence = 0.5
            if pos_score > neg_score:
                overall_sentiment = "positive"
                confidence = pos_score / (pos_score + neg_score) if (pos_score + neg_score) > 0 else 0.5
            elif neg_score > pos_score:
                overall_sentiment = "negative"
                confidence = neg_score / (pos_score + neg_score) if (pos_score + neg_score) > 0 else 0.5

            return {
                "overall_sentiment": overall_sentiment,
                "confidence": confidence,
                "top_emotions": top_emotions,
                "positive_score": round(pos_score, 3),
                "negative_score": round(neg_score, 3)
            }

        except Exception as e:
            print(f"감정 분석 실패: {e}")
            return {
                "overall_sentiment": "neutral",
                "confidence": 0.5,
                "top_emotions": [],
                "positive_score": 0.0,
                "negative_score": 0.0
            }

    def _calculate_competency_score(self, text, emotion_result, competency_info):
        """특정 리더십 역량 점수 계산"""
        try:
            score = 0.0

            # 1. 키워드 매칭 점수 (0-0.4)
            keyword_score = 0.0
            text_lower = text.lower()
            for keyword in competency_info["keywords"]:
                if keyword in text_lower:
                    keyword_score += 0.1
                    if keyword_score >= 0.4:
                        break
            score += min(keyword_score, 0.4)

            # 2. 감정 기반 점수 (0-0.6)
            emotion_score = 0.0
            top_emotions = emotion_result.get("top_emotions", [])

            for emotion in top_emotions:
                # 감정 이름으로 인덱스 찾기
                try:
                    emotion_idx = self.emotion_names.index(emotion["emotion"])
                    if emotion_idx in competency_info["emotions"]:
                        if emotion["sentiment"] == 0:  # 긍정 감정
                            emotion_score += emotion["probability"] * 0.6
                        elif emotion["sentiment"] == 1:  # 부정 감정
                            emotion_score += emotion["probability"] * 0.3  # 부정 감정도 일부 점수 부여 (개선 영역)
                except ValueError:
                    continue

            score += min(emotion_score, 0.6)

            return round(score, 3)

        except Exception as e:
            print(f"역량 점수 계산 실패: {e}")
            return 0.0

    def _extract_leadership_keywords(self, text):
        """리더십 관련 키워드 추출"""
        keywords = []
        text_lower = text.lower()

        for competency_info in self.leadership_competencies.values():
            for keyword in competency_info["keywords"]:
                if keyword in text_lower and keyword not in keywords:
                    keywords.append(keyword)
                    if len(keywords) >= 5:  # 최대 5개 키워드
                        break
            if len(keywords) >= 5:
                break

        return keywords

    def _classify_leadership_sentiment(self, leadership_scores):
        """리더십 감정 분류"""
        avg_score = sum(leadership_scores.values()) / len(leadership_scores)

        if avg_score >= 0.7:
            return "excellent"
        elif avg_score >= 0.5:
            return "good"
        elif avg_score >= 0.3:
            return "fair"
        else:
            return "needs_improvement"

    def _get_default_result(self):
        """기본 결과 반환"""
        return {
            "leadership_competencies": {key: 0.0 for key in self.leadership_competencies.keys()},
            "overall_leadership_score": 0.0,
            "key_leadership_indicators": [],
            "leadership_sentiment": "neutral",
            "confidence_score": 0.0,
            "emotion_analysis": {
                "overall_sentiment": "neutral",
                "confidence": 0.0,
                "top_emotions": [],
                "positive_score": 0.0,
                "negative_score": 0.0
            }
        }

    def consolidate_leadership_analysis(self, individual_results):
        """
        개별 평가 결과를 통합하여 그룹 전체 리더십 분석 수행

        Args:
            individual_results (list): 개별 리더십 분석 결과 리스트

        Returns:
            dict: 통합 리더십 분석 결과
        """
        if not individual_results:
            return self._get_consolidated_default()

        try:
            # 역량별 평균 계산
            competency_sums = {key: 0.0 for key in self.leadership_competencies.keys()}
            competency_counts = {key: 0 for key in self.leadership_competencies.keys()}

            all_keywords = []
            total_overall_score = 0.0
            valid_results = 0

            for result in individual_results:
                if "leadership_competencies" in result:
                    for competency, score in result["leadership_competencies"].items():
                        if competency in competency_sums:
                            competency_sums[competency] += score
                            competency_counts[competency] += 1

                if "key_leadership_indicators" in result:
                    all_keywords.extend(result["key_leadership_indicators"])

                if "overall_leadership_score" in result and result["overall_leadership_score"] > 0:
                    total_overall_score += result["overall_leadership_score"]
                    valid_results += 1

            # 평균 계산
            average_competencies = {}
            for competency in competency_sums:
                if competency_counts[competency] > 0:
                    average_competencies[competency] = round(competency_sums[competency] / competency_counts[competency], 3)
                else:
                    average_competencies[competency] = 0.0

            overall_score = round(total_overall_score / valid_results, 3) if valid_results > 0 else 0.0

            # 역량 분포 분석
            competency_distribution = self._analyze_competency_distribution(average_competencies)

            # 강점 및 개선 영역 식별
            strengths = [comp for comp, score in average_competencies.items() if score >= 0.6]
            development_areas = [comp for comp, score in average_competencies.items() if score < 0.4]

            # 고유 키워드 추출
            unique_keywords = list(set(all_keywords))[:10]  # 최대 10개

            # 리더십 감정 분류
            leadership_sentiment = self._classify_leadership_sentiment(average_competencies)

            # 신뢰도 계산
            confidence_score = min(1.0, valid_results / len(individual_results)) if individual_results else 0.0

            return {
                "average_competencies": average_competencies,
                "overall_leadership_score": overall_score,
                "competency_distribution": competency_distribution,
                "leadership_strengths": strengths,
                "leadership_development_areas": development_areas,
                "leadership_sentiment": leadership_sentiment,
                "confidence_score": round(confidence_score, 3)
            }

        except Exception as e:
            print(f"통합 리더십 분석 실패: {e}")
            return self._get_consolidated_default()

    def _analyze_competency_distribution(self, competencies):
        """역량 분포 분석"""
        high_performers = []
        needs_improvement = []
        consistent = []

        for comp, score in competencies.items():
            if score >= 0.7:
                high_performers.append(comp)
            elif score < 0.4:
                needs_improvement.append(comp)
            else:
                consistent.append(comp)

        return {
            "high_performers": high_performers,
            "needs_improvement": needs_improvement,
            "consistent": consistent
        }

    def _get_consolidated_default(self):
        """통합 기본 결과 반환"""
        return {
            "average_competencies": {key: 0.0 for key in self.leadership_competencies.keys()},
            "overall_leadership_score": 0.0,
            "competency_distribution": {
                "high_performers": [],
                "needs_improvement": [],
                "consistent": []
            },
            "leadership_strengths": [],
            "leadership_development_areas": [],
            "leadership_sentiment": "neutral",
            "confidence_score": 0.0
        }
