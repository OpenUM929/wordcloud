"""General API routes for the WordCloud application."""

from flask import Blueprint, request, jsonify, session
from src.config.settings import (
    NLP_CONFIG_PATH,
    WORDCLOUD_CONFIG_PATH,
    OUTPUTS_DIR_PATH,
    CONFIGS_DIR_PATH
)
from src.modules.wordcloud_generator import WordCloudGenerator
from src.modules.sarcasm_analysis import analyze_sarcasm
from src.modules.emotion_analysis import analyze_emotion
from src.modules.stopword_manager import get_stopword_manager, is_stopword, filter_stopwords
import os
import json
from datetime import datetime

api_bp = Blueprint('api', __name__)


@api_bp.route('/analyze', methods=['POST'])
def analyze():
    """Analyze text for emotion and sarcasm."""
    try:
        data = request.json
        print("Analyze API received data:", data)
        
        sentences = data.get('sentences', '').strip().split('\n')
        sentences = [s.strip() for s in sentences if s.strip()]
        wordcloud_pos = data.get('wordcloud_pos', ["Noun", "Verb", "Adjective"])

        results = []
        total_pos = 0.0
        total_neg = 0.0
        all_text = ' '.join(sentences)

        for sentence in sentences:
            emotion_result = analyze_emotion(sentence)
            sarcasm_result = analyze_sarcasm(sentence)

            extracted = []
            pos_score = 0.0
            neg_score = 0.0
            sarcasm_score = 0.0

            if "analysis" in emotion_result:
                analysis = emotion_result["analysis"]

                if "base_result" in analysis and "mapped" in analysis["base_result"]:
                    base_result = analysis["base_result"]["mapped"]
                    if "sentiment_scores" in base_result:
                        pos_score = base_result["sentiment_scores"].get("positive", 0.0)
                        neg_score = base_result["sentiment_scores"].get("negative", 0.0)

                    if "top_3" in base_result:
                        for pred in base_result["top_3"]:
                            extracted.append(f"{pred['label']}({pred['confidence']:.3f})")

            if "analysis" in sarcasm_result:
                analysis = sarcasm_result["analysis"]

                if "fine_tuned_result" in analysis and "mapped" in analysis["fine_tuned_result"]:
                    fine_tuned_result = analysis["fine_tuned_result"]["mapped"]
                    if fine_tuned_result["label"] == "Sarcasm":
                        sarcasm_score = fine_tuned_result["confidence"]
                elif "sklearn_result" in analysis and "mapped" in analysis["sklearn_result"]:
                    sklearn_result = analysis["sklearn_result"]["mapped"]
                    if sklearn_result["label"] == "Sarcasm":
                        sarcasm_score = sklearn_result["confidence"]

            if sarcasm_score == 0.0 and not any(key in sarcasm_result.get("analysis", {}) for key in ["fine_tuned_result", "sklearn_result"]):
                sarcasm_score = 0.0

            total_pos += pos_score
            total_neg += neg_score

            results.append({
                'sentence': sentence,
                'extracted': ', '.join(extracted),
                'positive_score': round(pos_score, 3),
                'negative_score': round(neg_score, 3),
                'sarcasm_score': round(sarcasm_score, 3)
            })

        if all_text.strip():
            # 사용자가 선택한 형태소 유형 가져오기
            wordcloud_pos = data.get('wordcloud_pos', ["Noun", "Verb", "Adjective"])
            
            # 새로운 옵션들 가져오기
            background_color = data.get('background_color', 'white')
            width = data.get('width', 800)
            height = data.get('height', 600)
            max_words = data.get('max_words', 100)
            apply_emotion_colors = data.get('apply_emotion_colors', True)
            remove_profanity = data.get('remove_profanity', False)
            
            # 설정 파일을 로드하여 wordcloud_pos 업데이트
            import json
            nlp_config_path_abs = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../configs/nlp_config.json'))
            if os.path.exists(nlp_config_path_abs):
                with open(nlp_config_path_abs, 'r', encoding='utf-8') as f:
                    nlp_config = json.load(f)
                nlp_config['wordcloud_pos'] = wordcloud_pos
                with open(nlp_config_path_abs, 'w', encoding='utf-8') as f:
                    json.dump(nlp_config, f, ensure_ascii=False, indent=2)
            
            # NLPAnalysis 인스턴스를 새로 생성하여 설정 reload
            from src.modules.nlp_analysis import NLPAnalysis
            analyzer = NLPAnalysis(config_path=NLP_CONFIG_PATH)
            nlp_result = analyzer.analyze(all_text)
            
            # meaningful_words 추출 (正しいキー)
            meaningful_words = []
            if 'analysis' in nlp_result and 'meaningful_words' in nlp_result['analysis']:
                meaningful_words = nlp_result['analysis']['meaningful_words']
                if isinstance(meaningful_words, dict) and 'error' in meaningful_words:
                    meaningful_words = []

            from collections import Counter
            word_freq = dict(Counter(meaningful_words))

            word_scores = {}
            for sentence in sentences:
                emotion_result = analyze_emotion(sentence)

                score = 0.0
                if "analysis" in emotion_result:
                    analysis = emotion_result["analysis"]

                    if "base_result" in analysis and "mapped" in analysis["base_result"]:
                        base_result = analysis["base_result"]["mapped"]
                        if "sentiment_scores" in base_result:
                            pos_score = base_result["sentiment_scores"].get("positive", 0.0)
                            neg_score = base_result["sentiment_scores"].get("negative", 0.0)
                            score = (pos_score - neg_score) * 2.5
                
                print(f"DEBUG: sentence='{sentence}', pos_score={pos_score if 'pos_score' in dir() else 'N/A'}, neg_score={neg_score if 'neg_score' in dir() else 'N/A'}, final score={score}")

                nlp_result = analyzer.analyze(sentence)
                sentence_words = []
                if 'analysis' in nlp_result and 'meaningful_words' in nlp_result['analysis']:
                    sentence_words = nlp_result['analysis']['meaningful_words']
                    if isinstance(sentence_words, dict):
                        sentence_words = []
                
                print(f"DEBUG: sentence_words={sentence_words}")

                # 문장별로 단어에 감정 점수 할당 (덮어쓰지 않음)
                for word in sentence_words:
                    if word not in word_scores:
                        word_scores[word] = score
                
                print(f"DEBUG: word_scores after sentence={word_scores}")

            generator = WordCloudGenerator(config_path=WORDCLOUD_CONFIG_PATH)
            output_path = os.path.abspath(os.path.join(OUTPUTS_DIR_PATH, f"wordcloud_{int(datetime.now().timestamp() * 1000)}.png"))
            
            print(f"DEBUG: word_freq = {word_freq}")
            print(f"DEBUG: word_scores = {word_scores}")
            print(f"DEBUG: apply_emotion_colors = {apply_emotion_colors}")
            
            success = generator.generate_with_colors_and_options(
                word_freq, word_scores, output_path,
                background_color=background_color,
                width=width, height=height, max_words=max_words,
                remove_stopwords=not remove_profanity,
                apply_emotion_colors=apply_emotion_colors,
                word_color=data.get('word_color'),
            )

            if success:
                results.append({'wordcloud_url': f"/outputs/{os.path.basename(output_path)}"})
            else:
                results.append({'wordcloud_url': None})

        print("Analysis results:", results)
        return jsonify(results)
        
    except Exception as e:
        print("Error in analyze API:", str(e))
        import traceback
        print("Stack trace:", traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/analyze_sarcasm', methods=['POST'])
def analyze_sarcasm_route():
    """Analyze text for sarcasm."""
    try:
        data = request.json
        result = analyze_sarcasm(data)
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/upload_csv', methods=['POST'])
def upload_csv():
    """Upload CSV file for analysis."""
    try:
        from src.services.batch_service import upload_csv
        result, status = upload_csv(request, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        return jsonify({
            'success': True,
            'status': 'healthy',
            'message': 'WordCloud application is running'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@api_bp.route('/stopwords', methods=['GET'])
def get_stopwords():
    """Get all stopwords without pagination (return all data)."""
    try:
        print("=== /api/stopwords GET called ===")
        
        manager = get_stopword_manager()
        print("StopwordManager initialized successfully")
        
        categories = manager.get_all_categories()
        print(f"Categories found: {categories}")
        
        # 카테고리별로 stopwords를 정리 (word -> category 매핑)
        word_category_list = []
        for category in categories:
            words = manager.get_stopwords_by_category(category)
            print(f"Category '{category}' has {len(words) if words else 0} words")
            if words:
                for word in words:
                    word_category_list.append({'word': word, 'category': category})
        
        print(f"Total word-category pairs found: {len(word_category_list)}")
        
        # 전체 데이터 반환 (페이징 처리 없음)
        import json
        result = {
            'success': True,
            'total': len(word_category_list),
            'categories': categories,
            'stopwords': word_category_list
        }
        
        # ensure_ascii=False로 설정하여 유니코드 문자를 직접 출력하게 함
        json_str = json.dumps(result, ensure_ascii=False).encode('utf-8')
        from flask import Response
        return Response(json_str, mimetype='application/json; charset=utf-8')
    except Exception as e:
        print(f"Error in /api/stopwords: {str(e)}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500


@api_bp.route('/stopwords/categories', methods=['GET'])
def get_stopword_categories():
    """Get all stopword categories."""
    try:
        manager = get_stopword_manager()
        categories = manager.get_all_categories()
        
        import json
        from flask import Response
        
        response_data = {
            'success': True,
            'total': len(categories),
            'categories': categories
        }
        
        json_str = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
        return Response(json_str, mimetype='application/json; charset=utf-8')
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/stopwords/category/<category>', methods=['GET'])
def get_stopwords_by_category(category):
    """Get stopwords by category."""
    try:
        manager = get_stopword_manager()
        stopwords = manager.get_stopwords_by_category(category)
        if stopwords:
            return jsonify({
                'success': True,
                'category': category,
                'total': len(stopwords),
                'stopwords': stopwords
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Category not found'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/stopwords', methods=['POST'])
def add_stopword():
    """Add a new stopword."""
    try:
        data = request.json
        word = data.get('word', '')
        category = data.get('category', '기타')

        if not word:
            return jsonify({
                'success': False,
                'error': 'Word is required'
            }), 400

        manager = get_stopword_manager()
        success = manager.add_stopword(word, category)
        if success:
            manager.save_stopwords()
            return jsonify({
                'success': True,
                'message': 'Stopword added successfully',
                'word': word,
                'category': category
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Stopword already exists'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/stopwords/<word>', methods=['DELETE'])
def delete_stopword(word):
    """Delete a stopword."""
    try:
        manager = get_stopword_manager()
        success = manager.remove_stopword(word)
        if success:
            manager.save_stopwords()
            return jsonify({
                'success': True,
                'message': 'Stopword deleted successfully',
                'word': word
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Stopword not found'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/stopwords/check', methods=['POST'])
def check_stopword():
    """Check if a word is a stopword."""
    try:
        data = request.json
        word = data.get('word', '')
        if not word:
            return jsonify({
                'success': False,
                'error': 'Word is required'
            }), 400

        manager = get_stopword_manager()
        is_stop = manager.is_stopword(word)
        return jsonify({
            'success': True,
            'word': word,
            'is_stopword': is_stop
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/stopwords/classify', methods=['POST'])
def classify_word():
    """Classify a word into category automatically."""
    try:
        data = request.json
        word = data.get('word', '')
        if not word:
            return jsonify({
                'success': False,
                'error': 'Word is required'
            }), 400

        manager = get_stopword_manager()
        category = manager.auto_classify_word(word)
        
        # JSON 응답에 ensure_ascii=False 적용
        import json
        from flask import Response
        
        response_data = {
            'success': True,
            'word': word,
            'category': category
        }
        
        json_str = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
        return Response(json_str, mimetype='application/json; charset=utf-8')
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/stopwords/filter', methods=['POST'])
def filter_text_stopwords():
    """Filter stopwords from text."""
    try:
        data = request.json
        text = data.get('text', '')
        if not text:
            return jsonify({
                'success': False,
                'error': 'Text is required'
            }), 400

        filtered_text = filter_stopwords(text)
        return jsonify({
            'success': True,
            'original_text': text,
            'filtered_text': filtered_text,
            'original_length': len(text),
            'filtered_length': len(filtered_text),
            'removed_count': len(text.split()) - len(filtered_text.split())
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


MAPPINGS_DIR = os.path.join(CONFIGS_DIR_PATH, 'mappings')
MAPPINGS_FILE = os.path.join(MAPPINGS_DIR, 'last_mapping.json')
os.makedirs(MAPPINGS_DIR, exist_ok=True)


def get_all_mapping_files():
    """저장된 모든 매핑 파일 목록 반환"""
    files = []
    if os.path.exists(MAPPINGS_DIR):
        for f in os.listdir(MAPPINGS_DIR):
            if f.endswith('.json') and f != 'last_mapping.json':
                file_path = os.path.join(MAPPINGS_DIR, f)
                stat = os.stat(file_path)
                files.append({
                    'name': f,
                    'path': file_path,
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'display_name': f.replace('.json', '').replace('_', ' ').replace('-', ':')
                })
    files.sort(key=lambda x: x['modified'], reverse=True)
    return files


@api_bp.route('/mappings/save', methods=['POST'])
def save_mappings():
    """Save column mappings to file."""
    try:
        data = request.json
        mappings = data.get('mappings', {})
        save_name = data.get('name')  # 선택적: 특정 이름으로 저장
        
        if not mappings or not isinstance(mappings, dict) or len(mappings) == 0:
            print(f"[MAPPINGS SAVE] 빈 매핑 데이터 - 저장 안 함")
            return jsonify({'success': False, 'error': '저장할 매핑 데이터가 없습니다.'}), 400
        
        print(f"[MAPPINGS SAVE] 저장 경로: {MAPPINGS_FILE}")
        print(f"[MAPPINGS SAVE] 저장할 매핑: {json.dumps(mappings, ensure_ascii=False)}")
        
        # name이 있으면 사용자 지정 이름으로, 없으면 last_mapping.json만 저장
        if save_name:
            # 보안: 파일명 검증
            safe_name = os.path.basename(save_name)
            if not safe_name.endswith('.json'):
                safe_name += '.json'
            named_file = os.path.join(MAPPINGS_DIR, safe_name)
            with open(named_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            print(f"[MAPPINGS SAVE] 사용자 지정 파일 저장: {named_file}")
            return jsonify({'success': True, 'saved_file': safe_name})
        else:
            # name 없으면 last_mapping.json만 저장
            with open(MAPPINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            print(f"[MAPPINGS SAVE] last_mapping.json 저장 완료 - 크기: {os.path.getsize(MAPPINGS_FILE)} bytes")
            return jsonify({'success': True, 'saved_file': 'last_mapping.json'})
    except Exception as e:
        print(f"[MAPPINGS SAVE] 저장 실패: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/mappings/list', methods=['GET'])
def list_mappings():
    """저장된 모든 매핑 파일 목록 반환"""
    try:
        files = get_all_mapping_files()
        print(f"[MAPPINGS LIST] 찾은 매핑 파일 수: {len(files)}")
        return jsonify({
            'success': True,
            'files': [{'name': f['name'], 'display_name': f['display_name'], 'modified': f['modified'], 'size': f['size']} for f in files]
        })
    except Exception as e:
        print(f"[MAPPINGS LIST] 목록 조회 실패: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/mappings/last', methods=['GET'])
def load_last_mappings():
    """Load last saved column mappings."""
    try:
        print(f"[MAPPINGS LOAD] 파일 경로: {MAPPINGS_FILE}")
        print(f"[MAPPINGS LOAD] 파일 존재: {os.path.exists(MAPPINGS_FILE)}")
        if os.path.exists(MAPPINGS_FILE):
            file_size = os.path.getsize(MAPPINGS_FILE)
            print(f"[MAPPINGS LOAD] 파일 크기: {file_size} bytes")
            if file_size == 0:
                print("[MAPPINGS LOAD] 파일이 0바이트 - null 반환")
                return jsonify({'success': True, 'mappings': None})
            with open(MAPPINGS_FILE, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            if not mappings:
                print("[MAPPINGS LOAD] 매핑 데이터 없음 - null 반환")
                return jsonify({'success': True, 'mappings': None})
            print(f"[MAPPINGS LOAD] 매핑 로드 성공")
            return jsonify({'success': True, 'mappings': mappings})
        print("[MAPPINGS LOAD] 파일 없음 - null 반환")
        return jsonify({'success': True, 'mappings': None})
    except (json.JSONDecodeError, Exception) as e:
        print(f"[MAPPINGS LOAD] 로드 실패: {str(e)}")
        return jsonify({'success': True, 'mappings': None})


@api_bp.route('/mappings/load/<name>', methods=['GET'])
def load_named_mapping(name):
    """특정 이름의 매핑 파일 로드"""
    try:
        # 보안: 경로 순회 방지
        name = os.path.basename(name)
        if not name.endswith('.json'):
            name = name + '.json'
        
        file_path = os.path.join(MAPPINGS_DIR, name)
        print(f"[MAPPINGS LOAD FILE] 요청된 파일: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"[MAPPINGS LOAD FILE] 파일 없음: {file_path}")
            return jsonify({'success': False, 'error': '파일이 없습니다.'}), 404
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return jsonify({'success': False, 'error': '빈 파일입니다.'}), 400
        
        with open(file_path, 'r', encoding='utf-8') as f:
            mappings = json.load(f)
        
        print(f"[MAPPINGS LOAD FILE] 매핑 로드 성공: {name}")
        return jsonify({'success': True, 'mappings': mappings, 'name': name})
    except (json.JSONDecodeError, Exception) as e:
        print(f"[MAPPINGS LOAD FILE] 로드 실패: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/mappings/delete', methods=['POST'])
def delete_mapping():
    """매핑 파일 삭제"""
    try:
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({'success': False, 'error': '파일명이 필요합니다.'}), 400
        
        # last_mapping.json은 삭제 불가
        if name == 'last_mapping.json':
            return jsonify({'success': False, 'error': '마지막 매핑 파일은 삭제할 수 없습니다.'}), 400
        
        # 보안: 경로 순회 방지
        name = os.path.basename(name)
        if not name.endswith('.json'):
            name = name + '.json'
        
        file_path = os.path.join(MAPPINGS_DIR, name)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': '파일이 없습니다.'}), 404
        
        os.remove(file_path)
        print(f"[MAPPINGS DELETE] 파일 삭제 완료: {file_path}")
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[MAPPINGS DELETE] 삭제 실패: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
