"""메타데이터 시점 문장+KoTE 핸드오프 코퍼스 라이터 (0622_01).

배치 저장 흐름 안에서 각 평가 문장을 KoTE 결과(top-3 감정 포함)와 함께 압축 JSONL로
누적한다. 이 파일은 Claude(LLM)에게 그대로 전달해 감정 규칙 마이닝·KoTE 분류 검증·
신규 감정/리더십 군집 발굴에 사용한다(LLM 재학습 1차 용도, 최소 토큰 구조).

출력 루트는 데이터셋 폴더(plans/_datasets/kote_finetune) 하위로 강제한다.
plans/는 배포 제외 폴더 — 학습/분석 데이터는 이 폴더 외 위치 금지(배포 유출 방지).
가명화 완료 텍스트만 기록된다(원천 ID 비보관).
"""

import os
import json
import re

from src.config.settings import PROJECT_ROOT_DIR

# 데이터셋 루트(고정) — 자유 경로 금지
_DATASET_ROOT = os.path.join(PROJECT_ROOT_DIR, 'plans', '_datasets', 'kote_finetune')
_HANDOFF_ROOT = os.path.abspath(os.path.join(_DATASET_ROOT, 'emotion', 'handoff'))

# 레전드(1줄차) — 사이드카 없이 파일만으로 키 의미를 LLM이 인식
_LEGEND_DESC = "x=문장, y=라벨(p=긍/n=부/u=중), s=[pos,neg,neu], e=top3감정[[명,점],...]"


def _safe_segment(value):
    """경로 한 세그먼트로 안전화 — 경로 탈출/구분자 차단. 영숫자·한글·-/_만 허용."""
    s = str(value or '').strip()
    s = s.replace('/', '_').replace('\\', '_')
    s = re.sub(r'[^0-9A-Za-z가-힣_\-]', '_', s)
    s = s.strip('._')
    return s


def resolve_handoff_path(dest_label, batch_id):
    """핸드오프 파일 절대경로. 데이터셋 루트 하위 강제(탈출 시 ValueError)."""
    label = _safe_segment(dest_label) or 'default'
    bid = _safe_segment(batch_id) or 'batch'
    path = os.path.abspath(os.path.join(_HANDOFF_ROOT, label, bid + '.jsonl'))
    if path != _HANDOFF_ROOT and not path.startswith(_HANDOFF_ROOT + os.sep):
        raise ValueError(f'핸드오프 경로가 데이터셋 루트를 벗어남: {path}')
    return path


def build_records_from_metadata(metadata):
    """직원 메타데이터 → [(sentence, label, pos, neg, neutral, top3), ...].

    label: override 점수 부호 → 'p'(>0)/'n'(<0)/'u'(==0). 그룹분석과 동일 매핑.
    sentence_emotion_cache를 재사용하므로 KoTE 재실행 0. 가명화 텍스트 기준.
    """
    # 무거운 의존(perspective_service=matplotlib)은 호출 시 지연 임포트 — 모듈 임포트 경량 유지.
    from src.services.perspective_service import _get_sentence_level_scores

    records = []
    for ev in metadata.get('evaluations', []) or []:
        doc = ev.get('evaluation_document') or ev.get('evaluation_document_original') or ''
        cache = ev.get('sentence_emotion_cache')
        scores = _get_sentence_level_scores(doc, sentence_cache=cache, field=ev.get('evaluation_document_field'))
        for i, (sent, score, pos, neg, neutral) in enumerate(scores):
            if not sent:
                continue
            label = 'p' if score > 0 else ('n' if score < 0 else 'u')
            top3 = []
            if cache and i < len(cache):
                top3 = cache[i].get('top3') or []
            records.append((sent, label, pos, neg, neutral, top3))
    return records


def append_handoff_records(dest_label, batch_id, records):
    """records를 핸드오프 JSONL에 append. 파일이 비어있으면 레전드 1줄 선기록.

    Returns: 기록한 문장(줄) 수. records 비면 0.
    """
    if not records:
        return 0
    path = resolve_handoff_path(dest_label, batch_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    new_file = (not os.path.exists(path)) or os.path.getsize(path) == 0
    with open(path, 'a', encoding='utf-8') as f:
        if new_file:
            f.write(json.dumps({"#": _LEGEND_DESC, "batch": str(batch_id)},
                               ensure_ascii=False) + '\n')
        for sent, label, pos, neg, neutral, top3 in records:
            line = {
                "x": sent,
                "y": label,
                "s": [round(pos or 0.0, 2), round(neg or 0.0, 2), round(neutral or 0.0, 2)],
                "e": [[t[0], round(t[1] or 0.0, 2)] for t in (top3 or []) if t],
            }
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
    return len(records)


__all__ = ['resolve_handoff_path', 'build_records_from_metadata', 'append_handoff_records']
