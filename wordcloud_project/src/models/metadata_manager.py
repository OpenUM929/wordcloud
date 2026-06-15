#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
메타데이터 관리 모듈
"""

import os
import json
import uuid
import hashlib
from datetime import datetime
from src.config.settings import (
    PROCESSED_DATA_DIR_PATH,
    OUTPUTS_DIR_PATH
)


class MetadataManager:
    """메타데이터 생성, 저장, 검색, 수정 관리 클래스"""
    
    def __init__(self, processed_data_dir=PROCESSED_DATA_DIR_PATH):
        """
        초기화
        
        Args:
            processed_data_dir (str): 처리된 데이터가 저장된 디렉토리 경로
        """
        self.processed_data_dir = processed_data_dir
    
    def create_employee_metadata(self, employee_id, evaluations, department="생산부", position="사원",
                              target_hierarchy_level="staff", evaluator_hierarchy_level="staff"):
        """
        직원 메타데이터 생성
        
        Args:
            employee_id (str): 직원 ID
            evaluations (list): 평가 데이터 리스트
            department (str): 부서 (기본값: 생산부)
            position (str): 직위 (기본값: 사원)
            target_hierarchy_level (str): 피평가자 계층 레벨 (기본값: staff)
            evaluator_hierarchy_level (str): 평가자 계층 레벨 (기본값: staff)
            
        Returns:
            dict: 생성된 메타데이터
        """
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        # 각 평가에 분석 결과 추가
        analyzed_evaluations = []
        for idx, evaluation in enumerate(evaluations):
            try:
                analyzed_eval = evaluation.copy()

                # evaluation_id 추가 (없을 경우 생성)
                if 'evaluation_id' not in analyzed_eval:
                    analyzed_eval['evaluation_id'] = f"eval-{employee_id}-{idx+1}-{datetime.now().strftime('%Y%m%d')}"

                # evaluator_id 추가 (없을 경우 None)
                if 'evaluator_id' not in analyzed_eval:
                    analyzed_eval['evaluator_id'] = analyzed_eval.get('evaluator_id')

                # NLP 분석
                from src.modules.nlp_analysis import analyze_text
                nlp_result = analyze_text(analyzed_eval.get('evaluation_document', ''))
                analyzed_eval['nlp_analysis_results'] = nlp_result

                # 감정 분석
                from src.modules.emotion_analysis import analyze_emotion
                emotion_result = analyze_emotion(analyzed_eval.get('evaluation_document', ''))
                analyzed_eval['emotion_analysis_results'] = emotion_result

                # 욕설 분석 (캐싱된 singleton 사용)
                from src.modules.profanity_filter import advanced_filter_profanity
                profanity_result = advanced_filter_profanity(analyzed_eval.get('evaluation_document', ''))
                analyzed_eval['profanity_analysis_results'] = profanity_result

                # 리더십 분석 (캐싱된 singleton 사용)
                from src.modules.leadership_analysis import LeadershipAnalysis
                leadership_analyzer = LeadershipAnalysis()
                leadership_result = leadership_analyzer.analyze_leadership(analyzed_eval.get('evaluation_document', ''))
                analyzed_eval['leadership_analysis_results'] = leadership_result

                # 비꼬임 분석
                from src.modules.sarcasm_analysis import analyze_sarcasm
                sarcasm_result = analyze_sarcasm(analyzed_eval.get('evaluation_document', ''))
                analyzed_eval['sarcasm_analysis_results'] = sarcasm_result

                analyzed_evaluations.append(analyzed_eval)
            except Exception as e:
                import traceback
                doc = evaluation.get('evaluation_document', '')[:200]
                eval_id = evaluation.get('evaluation_id', f'#{idx}')
                raise RuntimeError(
                    f"Evaluation {idx} (id={eval_id}) failed for employee={employee_id}: "
                    f"{type(e).__name__}: {e}\n"
                    f"Document: {doc!r}\n"
                    f"Traceback:\n{traceback.format_exc()}"
                ) from e
        
        metadata = {
            "session_id": session_id,
            "target_employee_id": employee_id,
            "target_employee_department": department,
            "target_employee_position": position,
            "target_hierarchy_level": target_hierarchy_level,
            "total_evaluations": len(analyzed_evaluations),
            "evaluations": analyzed_evaluations,
            "version": "2.2.0",
            "processing_status": {
                "current_step": "completed",
                "completed_steps": ["input_validation", "data_preprocessing", "nlp_analysis", 
                                  "emotion_analysis", "sarcasm_analysis", "leadership_analysis", 
                                  "wordcloud_generation", "consolidation"],
                "next_step": None
            },
            "created_at": datetime.now().isoformat() + 'Z'
        }
        
        # 통합 분석 결과 추가
        from src.modules.metadata_analysis import calculate_consolidated_analysis
        metadata['consolidated_analysis'] = calculate_consolidated_analysis(analyzed_evaluations)
        
        return metadata
    
    def save_employee_metadata(self, metadata, batch_dir=None):
        """
        직원 메타데이터 저장 (통합 인사데이터)
        
        Args:
            metadata (dict): 저장할 메타데이터
            batch_dir (str): 배치 처리 디렉토리 (기본값: None - 단일 처리)
            
        Returns:
            str: 저장된 파일 경로
        """
        if batch_dir:
            # 배치 처리의 경우
            tmeta_dir = os.path.join(batch_dir, "tmeta")
            os.makedirs(tmeta_dir, exist_ok=True)
            metadata_path = os.path.join(tmeta_dir, f"employee_{metadata['target_employee_id']}.json")
        else:
            # 단일 처리의 경우
            current_year_month = datetime.now().strftime('%Y%m')
            metadata_dir = os.path.abspath(os.path.join(self.processed_data_dir, current_year_month, "single"))
            os.makedirs(metadata_dir, exist_ok=True)
            metadata_path = os.path.join(metadata_dir, f"employee_{metadata['target_employee_id']}.json")
        
        # 데이터 무결성 해시 생성
        metadata_json = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
        metadata["data_integrity_hash"] = hashlib.sha256(metadata_json.encode('utf-8')).hexdigest()
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # 기본 인사데이터 저장 (imeta 폴더)
        if batch_dir and 'evaluations' in metadata:
            self.save_individual_metadata(metadata, batch_dir)
        
        return metadata_path
    
    def save_individual_metadata(self, consolidated_metadata, batch_dir):
        """
        기본 인사데이터 개별 저장
        
        Args:
            consolidated_metadata (dict): 통합 메타데이터
            batch_dir (str): 배치 디렉토리
            
        Returns:
            list: 저장된 기본 메타데이터 파일 경로 리스트
        """
        imeta_dir = os.path.join(batch_dir, "imeta")
        os.makedirs(imeta_dir, exist_ok=True)
        
        saved_paths = []
        target_id = consolidated_metadata.get('target_employee_id')
        
        for idx, evaluation in enumerate(consolidated_metadata.get('evaluations', [])):
            # 기본 인사데이터 구성
            individual_metadata = {
                "evaluation_id": evaluation.get('evaluation_id'),
                "target_employee_id": target_id,
                "target_employee_department": consolidated_metadata.get('target_employee_department'),
                "target_employee_position": consolidated_metadata.get('target_employee_position'),
                "target_hierarchy_level": consolidated_metadata.get('target_hierarchy_level', 'staff'),
                "evaluation_document": evaluation.get('evaluation_document'),
                "evaluator_id": evaluation.get('evaluator_id'),
                "evaluator_department": evaluation.get('evaluator_department'),
                "evaluator_position": evaluation.get('evaluator_position'),
                "evaluator_hierarchy_level": evaluation.get('evaluator_hierarchy_level', 'staff'),
                "evaluation_date": evaluation.get('evaluation_date'),
                "preprocessing_results": evaluation.get('preprocessing_results'),
                "emotion_analysis_results": evaluation.get('emotion_analysis_results'),
                "nlp_analysis_results": evaluation.get('nlp_analysis_results'),
                "profanity_analysis_results": evaluation.get('profanity_analysis_results'),
                "leadership_analysis_results": evaluation.get('leadership_analysis_results'),
                "sarcasm_analysis_results": evaluation.get('sarcasm_analysis_results'),
                "processing_status": consolidated_metadata.get('processing_status'),
                "session_id": consolidated_metadata.get('session_id'),
                "created_at": consolidated_metadata.get('created_at')
            }
            
            # 파일명: eval_{target_id}_{index}.json
            eval_id = evaluation.get('evaluation_id', f'eval-{target_id}-{idx+1}')
            individual_path = os.path.join(imeta_dir, f"{eval_id}.json")
            
            # 데이터 무결성 해시 생성
            metadata_json = json.dumps(individual_metadata, sort_keys=True, ensure_ascii=False)
            individual_metadata["data_integrity_hash"] = hashlib.sha256(metadata_json.encode('utf-8')).hexdigest()
            
            with open(individual_path, 'w', encoding='utf-8') as f:
                json.dump(individual_metadata, f, ensure_ascii=False, indent=2)
            
            saved_paths.append(individual_path)
        
        return saved_paths
    
    def load_employee_metadata(self, employee_id, batch_dir=None):
        """
        직원 메타데이터 로드
        
        Args:
            employee_id (str): 직원 ID
            batch_dir (str): 배치 처리 디렉토리 (기본값: None - 단일 처리)
            
        Returns:
            dict or None: 로드된 메타데이터 or None (파일 없음)
        """
        if batch_dir:
            metadata_path = os.path.join(batch_dir, "tmeta", f"employee_{employee_id}.json")
        else:
            # 단일 처리의 경우 최신 날짜 폴더 찾기
            return None
            
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def update_employee_metadata(self, employee_id, updates, batch_dir=None):
        """
        직원 메타데이터 업데이트
        
        Args:
            employee_id (str): 직원 ID
            updates (dict): 업데이트할 필드와 값
            batch_dir (str): 배치 처리 디렉토리 (기본값: None - 단일 처리)
            
        Returns:
            dict or None: 업데이트된 메타데이터 or None (파일 없음)
        """
        metadata = self.load_employee_metadata(employee_id, batch_dir)
        if metadata:
            metadata.update(updates)
            # 데이터 무결성 해시 재계산
            metadata_json = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
            metadata["data_integrity_hash"] = hashlib.sha256(metadata_json.encode('utf-8')).hexdigest()
            
            self.save_employee_metadata(metadata, batch_dir)
            return metadata
        return None
    
    def list_batch_directories(self):
        """
        배치 디렉토리 목록 반환
        
        Returns:
            list: 배치 디렉토리 경로 리스트
        """
        batch_dir = os.path.join(self.processed_data_dir, "batch")
        if not os.path.exists(batch_dir):
            return []
        
        batch_dirs = []
        for item in os.listdir(batch_dir):
            item_path = os.path.join(batch_dir, item)
            if os.path.isdir(item_path) and item.startswith("batch_"):
                batch_dirs.append(item_path)
        
        # 날짜 순으로 정렬
        batch_dirs.sort(reverse=True)
        return batch_dirs
    
    def get_batch_summary(self, batch_dir):
        """
        배치 처리 요약 정보 반환
        
        Args:
            batch_dir (str): 배치 디렉토리 경로
            
        Returns:
            dict or None: 배치 요약 정보
        """
        summary_path = os.path.join(batch_dir, "tmeta", "batch_summary.json")
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def verify_data_integrity(self, metadata):
        """
        데이터 무결성 검증
        
        Args:
            metadata (dict): 검증할 메타데이터
            
        Returns:
            bool: 무결성이 유지되었는지 여부
        """
        # 해시 제외한 메타데이터 생성
        metadata_copy = metadata.copy()
        if "data_integrity_hash" in metadata_copy:
            del metadata_copy["data_integrity_hash"]
            
        metadata_json = json.dumps(metadata_copy, sort_keys=True, ensure_ascii=False)
        calculated_hash = hashlib.sha256(metadata_json.encode('utf-8')).hexdigest()
        
        return calculated_hash == metadata.get("data_integrity_hash")

    def get_wordcloud_path(self, metadata, batch_path=None):
        """Get wordcloud path from metadata."""
        wordcloud_path = metadata.get('wordcloud_path')
        wordcloud_url = None

        if wordcloud_path:
            if wordcloud_path.startswith('word/') and batch_path:
                wordcloud_url = f'/api/wordcloud/batch/{os.path.basename(batch_path)}/{wordcloud_path}'
            elif wordcloud_path.startswith('/outputs/'):
                wordcloud_url = wordcloud_path
            elif wordcloud_path.startswith('outputs/'):
                wordcloud_url = '/' + wordcloud_path
            else:
                wordcloud_url = '/outputs/' + os.path.basename(wordcloud_path)

        return wordcloud_url

    def update_wordcloud_info(self, metadata, wordcloud_url, wordcloud_info):
        """Update wordcloud information in metadata."""
        metadata['wordcloud_path'] = wordcloud_url
        metadata['wordcloud_generation_info'] = wordcloud_info
        return metadata