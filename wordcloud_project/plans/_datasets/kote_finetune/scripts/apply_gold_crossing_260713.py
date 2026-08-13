# -*- coding: utf-8 -*-
"""긍↔부 gold 교차 정정 — 사용자 그룹검토 확정분을 TRAIN 파일에 반영.

입력: eval/review/gold_crossing_review_260713.jsonl (human_decision 채워진 상태).
학습 라벨은 각 TRAIN 파일의 human_decision 키(finetune_sentiment.load()가 읽음).
정정 = 소스 TRAIN 파일(_src_file)의 해당 rec_id 행 human_decision 을 확정값으로 교체.

not_group: LAB2ID(pos/neg/neu)에 없어 load()가 학습에서 자동 제외 → 필드의존 문장에 정확한 처리.
안전: 파일별 백업(.bak_gc260713) + rec_id 매칭 후 text 교차확인(불일치 시 abort) + prev 보존 + 감사로그.
"""
import json
import os
import io
import shutil
from datetime import date

HERE = os.path.dirname(__file__)
DS = os.path.abspath(os.path.join(HERE, '..'))
REVIEW = os.path.join(DS, 'eval', 'review', 'gold_crossing_review_260713.jsonl')
AUDIT = os.path.join(DS, 'eval', 'gold_crossing_corrections_260713.jsonl')
TODAY = date.today().strftime('%y%m%d')


def load(path):
    return [json.loads(l) for l in io.open(path, encoding='utf-8') if l.strip()]


def find(rows, rid, text):
    """rec_id(val- 접두 양쪽) 매칭 → 없으면 text. 반환: 행 or None."""
    for x in rows:
        if x.get('rec_id') == rid:
            return x
    for x in rows:
        if x.get('rec_id') == rid.replace('val-', ''):
            return x
    for x in rows:
        if x.get('text', '').strip() == text.strip():
            return x
    return None


def main():
    review = load(REVIEW)
    # 소스 파일별 그룹핑
    by_file = {}
    for r in review:
        if r.get('human_decision') is None:
            raise SystemExit(f'미결정 행 존재: {r["rec_id"]} — 게시판 확정 후 재실행')
        by_file.setdefault(r['_src_file'], []).append(r)

    corrections = []
    for fn, items in by_file.items():
        path = os.path.join(DS, 'eval', fn)
        rows = load(path)
        # 백업(1회)
        bak = path + f'.bak_gc{TODAY}'
        if not os.path.exists(bak):
            shutil.copyfile(path, bak)
        for r in items:
            row = find(rows, r['rec_id'], r['text'])
            if row is None:
                raise SystemExit(f'매칭 실패: {fn} / {r["rec_id"]} — 중단(무결성)')
            if row.get('text', '').strip() != r['text'].strip():
                raise SystemExit(f'텍스트 불일치 abort: {fn} / {r["rec_id"]}')
            old = row.get('human_decision')
            new = r['human_decision']
            if old == new:
                continue
            row['prev_human_decision'] = old
            row['human_decision'] = new
            row['corrected_by'] = 'human(group-review)+opus_apply'
            row['corrected_at'] = f'20{TODAY[:2]}-{TODAY[2:4]}-{TODAY[4:]}'
            row['correction_source'] = 'gold_crossing_260713'
            corrections.append({'file': fn, 'rec_id': r['rec_id'], 'text': r['text'],
                                'old': old, 'new': new, 'field': r.get('field')})
        with io.open(path, 'w', encoding='utf-8') as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')

    with io.open(AUDIT, 'w', encoding='utf-8') as f:
        for c in corrections:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')

    # ── 자기검산(규칙 #17) ──
    from collections import Counter
    fixed = {c['rec_id'] for c in corrections}
    trans = Counter(f'{c["old"]}->{c["new"]}' for c in corrections)
    to_train = sum(1 for c in corrections if c['new'] in ('positive', 'negative', 'neutral'))
    to_excl = sum(1 for c in corrections if c['new'] == 'not_group')
    # 재검증: 각 소스 파일에서 확정값이 실제로 기록됐는지
    reverify_ok = True
    for fn, items in by_file.items():
        rows = load(os.path.join(DS, 'eval', fn))
        for r in items:
            row = find(rows, r['rec_id'], r['text'])
            if row.get('human_decision') != r['human_decision']:
                reverify_ok = False
    print(f'정정 적용: {len(corrections)}건 (학습라벨 {to_train} + not_group 제외 {to_excl})')
    print(f'  전이: {dict(trans)}')
    print(f'  백업: eval/*.bak_gc{TODAY} · 감사: {os.path.relpath(AUDIT, DS)}')
    print(f'── 자기검산 ── 재검증(파일 기록=확정값): {"OK" if reverify_ok else "FAIL"} · '
          f'적용 {len(corrections)}/11 {"OK" if len(corrections) == 11 else "(중복/무변경 존재)"}')
    assert reverify_ok, '재검증 실패 — 파일 기록이 확정값과 불일치'


if __name__ == '__main__':
    main()
