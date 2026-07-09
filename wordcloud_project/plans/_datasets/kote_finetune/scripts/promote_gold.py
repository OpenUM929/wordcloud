# -*- coding: utf-8 -*-
"""confirmed 사람 검토(eval/*.jsonl) → 정식 gold 스트림(emotion/emotion.jsonl) 적립 (§2-1 step4 / D5).

검토 UI(0624_05)·판정 패킷이 채운 `human_decision`(독립 사람 판정, AI 프리필 아님 — ai_reference와 19~64%만 일치)을
정식 append-only 스트림에 표준 스키마로 적립한다. 군집/검토는 끝났고 이 단계는 **확정분의 기계적 누적**이다(신규 확정 아님).

원칙:
  - append-only: 기존 행 보존, id 기준 dedup. 같은 id가 다른 라벨이면 conflict로 격리(학습 제외).
  - 비식별화: PII 정규식 감사로 적발 행은 적립 제외(별도 격리 파일). src_hash는 eval 행에 직원ID 부재 → null(직원단위 누수보호 한계 — 리포트에 명시; baseline은 이미 held-out).
  - 추측 금지: human_decision ∈ {positive,negative,neutral}만 sentiment_gold. not_group/skip/공란 제외.
  - O(n), dev·로컬, plans 배포 제외.

스키마(0617_05 §design): id·text·field·sentiment_gold·emotions_gold·weak_sentiment·applied_rule·
  label_source=human·review_status=confirmed·annotator·src_hash·source_file·promoted_at
"""
import argparse
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
EVAL_DIR = os.path.join(DATASET_DIR, 'eval')
STREAM = os.path.join(DATASET_DIR, 'emotion', 'emotion.jsonl')
QUARANTINE = os.path.join(DATASET_DIR, 'emotion', 'emotion_pii_quarantine.jsonl')

# 확정 검토 파일(human_decision 보유). 미판정 후보(group_gold_candidates*)는 제외.
SOURCE_FILES = [
    'group_needs_human_260624.jsonl',
    'group_needs_human_g4_260624.jsonl',
    'field_conflict_review_260624.jsonl',
    'baseline_eval_260624.jsonl',
    'hard_failure_review_260630.jsonl',   # 능동학습 1라운드 — 사용자 라벨(정본)
    'neutral_gold_review_260701.jsonl',   # 중립 화행 확충 — 사용자 라벨(정본)
    'gold_8c_train_260706.jsonl',         # 8c 하드클래스 사람 gold(decision_source=human 선별분)
    'gold_8c_test_260706.jsonl',          # 8c held-out(source_file로 학습 제외 식별 가능)
]
VALID = {'positive', 'negative', 'neutral'}

# 비식별화 감사(보수적): 주민번호·전화·이메일. 적발 시 적립 제외.
PII = [
    re.compile(r'\d{6}\s*-\s*\d{7}'),               # 주민등록번호
    re.compile(r'01\d\s*-?\s*\d{3,4}\s*-?\s*\d{4}'), # 휴대전화
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),         # 이메일
]


def decision_key(row):
    if 'human_decision' in row:
        return 'human_decision'
    if 'gold' in row:
        return 'gold'
    return None


def has_pii(text):
    return any(p.search(text or '') for p in PII)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='적립 미실행, 집계만')
    ap.add_argument('--date', default=date.today().strftime('%Y-%m-%d'))
    args = ap.parse_args()

    # 기존 정식 스트림 로드(append-only dedup)
    existing = {}
    if os.path.exists(STREAM):
        with open(STREAM, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    existing[r['id']] = r.get('sentiment_gold')

    staged = {}      # id -> formal row
    conflicts = []   # (id, existing/seen label, new label, file)
    pii_rows = []
    skipped = {'no_decision': 0, 'invalid_label': 0, 'dup_same': 0, 'no_decision_file': 0}
    per_file = {}

    for fn in SOURCE_FILES:
        path = os.path.join(EVAL_DIR, fn)
        if not os.path.exists(path):
            print(f'[warn] missing: {fn}', file=sys.stderr)
            continue
        cnt = {'promoted': 0, 'pos': 0, 'neg': 0, 'neu': 0, 'skip': 0, 'pii': 0}
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                dk = decision_key(row)
                if dk is None:
                    skipped['no_decision_file'] += 1
                    continue
                label = str(row.get(dk) or '').strip()
                if not label:
                    skipped['no_decision'] += 1
                    cnt['skip'] += 1
                    continue
                if label not in VALID:   # not_group, skip 등
                    skipped['invalid_label'] += 1
                    cnt['skip'] += 1
                    continue
                rec_id = row.get('rec_id') or row.get('id')
                text = row.get('text', '')
                if has_pii(text):
                    pii_rows.append({'id': rec_id, 'text': text, 'source_file': fn})
                    cnt['pii'] += 1
                    continue
                # conflict 검사: 기존 스트림 또는 이번 stage에 다른 라벨
                prev = existing.get(rec_id) or (staged[rec_id]['sentiment_gold'] if rec_id in staged else None)
                if prev is not None:
                    if prev != label:
                        conflicts.append((rec_id, prev, label, fn))
                    else:
                        skipped['dup_same'] += 1
                    continue
                group = row.get('group')
                emotions_gold = [group] if (group and str(group).startswith('hr_')) else []
                formal = {
                    'id': rec_id,
                    'text': text,
                    'field': row.get('field'),
                    'sentiment_gold': label,
                    'emotions_gold': emotions_gold,
                    'weak_sentiment': row.get('cur_rule_label'),
                    'applied_rule': row.get('note'),
                    'label_source': 'human',
                    'review_status': 'confirmed',
                    'annotator': 'human_review',
                    'src_hash': None,   # eval 행에 직원ID 부재 → 직원단위 누수보호 N/A
                    'source_file': fn,
                    'promoted_at': args.date,
                }
                staged[rec_id] = formal
                cnt['promoted'] += 1
                cnt[{'positive': 'pos', 'negative': 'neg', 'neutral': 'neu'}[label]] += 1
        per_file[fn] = cnt

    # conflict는 학습 제외(격리만)
    tot = {'pos': 0, 'neg': 0, 'neu': 0}
    for r in staged.values():
        tot[{'positive': 'pos', 'negative': 'neg', 'neutral': 'neu'}[r['sentiment_gold']]] += 1

    print('=== promote_gold (D5 정식 적립) ===')
    print(f'기존 스트림 행수: {len(existing)}')
    for fn, c in per_file.items():
        print(f'  {fn}: promoted={c["promoted"]} (pos {c["pos"]}/neg {c["neg"]}/neu {c["neu"]}) skip={c["skip"]} pii={c["pii"]}')
    print(f'신규 적립: {len(staged)}  (positive {tot["pos"]} / negative {tot["neg"]} / neutral {tot["neu"]})')
    print(f'skip: {skipped}')
    print(f'conflict(격리·학습제외): {len(conflicts)}')
    for c in conflicts[:10]:
        print(f'    CONFLICT id={c[0]} prev={c[1]} new={c[2]} ({c[3]})')
    print(f'PII 격리: {len(pii_rows)}')

    if args.dry_run:
        print('\n[dry-run] 미적립.')
        return

    os.makedirs(os.path.dirname(STREAM), exist_ok=True)
    with open(STREAM, 'a', encoding='utf-8') as f:
        for r in staged.values():
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    if pii_rows:
        with open(QUARANTINE, 'a', encoding='utf-8') as f:
            for r in pii_rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')

    final = sum(1 for _ in open(STREAM, encoding='utf-8'))
    print(f'\n정식 스트림 적립 완료 → {STREAM}')
    print(f'  총 행수: {final}  (positive gold {tot["pos"]} 확보 — 정식 \"positive gold 0\" 블로커 해소)')


if __name__ == '__main__':
    main()
