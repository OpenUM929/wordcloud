# -*- coding: utf-8 -*-
"""hr-kote-finetune 약지도 JSONL export (3분류 scope · 비-🟡 독립 스크립트).

설계 근거: plans/2026/0617_05_kote-finetune-data §5(스키마)·§10(통합)·§14(보안).
사용자 결정(2026-06-17): 범위=비-🟡 부분만, 라벨=3분류 sentiment 먼저, 어노테이터=단독.

동작:
  1) 취득 코퍼스 반입 포맷 CSV(기본 data/new_260617.csv)를 읽는다.
  2) refine_acquired_row(프로덕션과 동일한 KoTE→override 경로)로 약지도 라벨 재현
     — weak_sentiment / applied_rule / override 후 라벨 / KoTE 원시점수.
  3) §14-1 비식별화 게이트:
       - source_employee_id/evaluation_id/batch_id → JSONL 미포함, src_hash로만 보존.
       - sentence_text PII 정규식 감사(주민/전화/이메일/장수 숫자열) → 적발 행은 격리(제외).
  4) §5 스키마 JSONL로 출력. gold 미확정 단계이므로 sentiment_gold는 잠정
     (label_source=kote, review_status=pending) — 사람 검토 후 confirmed 승격 예정.

주의:
  - 정식 append-only 스트림(emotion/emotion.jsonl, 확정 gold 전용)과 분리한다.
    본 스크립트는 날짜 스냅샷(emotion/weak_export_<date>.jsonl)을 멱등 재기록한다.
  - 서버/배치 불요. KoTE 1회 로드(refine 경로). plans/는 배포 제외 폴더.
핵심가치: 긍↔부 오분류 방지 — gold 확정 전이므로 잠정 라벨을 학습에 그대로 쓰지 말 것.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date

HERE = os.path.dirname(__file__)
# scripts → kote_finetune → _datasets → plans → wordcloud_project
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, '..'))
sys.path.insert(0, PROJECT_ROOT)

DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
DEFAULT_CSV = os.path.join(REPO_ROOT, 'data', 'new_260617.csv')

# §14-1 PII 감사 — 구체적·고신뢰 패턴만(한국어 이름 추정은 신뢰 불가하므로 미포함)
PII_PATTERNS = [
    ('rrn', re.compile(r'\d{6}[-\s]?[1-4]\d{6}')),          # 주민등록번호류
    ('phone', re.compile(r'01[016-9][-\s.]?\d{3,4}[-\s.]?\d{4}')),
    ('email', re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')),
    ('longnum', re.compile(r'\d{6,}')),                     # 사번 등 장수 숫자열
]


def audit_pii(text):
    """텍스트에서 적발된 PII 패턴명 목록 반환(빈 목록이면 통과)."""
    return [name for name, pat in PII_PATTERNS if pat.search(text or '')]


def src_hash(value):
    """원천 식별자 → 누수방지 그룹키(원문 비보관). 빈 값은 None."""
    if not value or not str(value).strip():
        return None
    return hashlib.sha256(str(value).strip().encode('utf-8')).hexdigest()[:16]


def build_record(row, meta):
    """§5 스키마 1행(JSONL) 생성. source_*_id는 절대 포함하지 않는다."""
    rid = (row.get('id') or '').strip()
    try:
        sidx = int(row.get('sentence_index') or 0)
    except (TypeError, ValueError):
        sidx = 0
    return {
        'id': f'as-{rid}' if rid else None,
        'text': (row.get('sentence_text') or '').strip(),
        'sentence_index': sidx,
        'total_sentences': meta['total_sentences'],
        'is_last': meta['is_last'],

        # gold 계층(3분류) — 현재는 잠정(모델 복사본). 사람 검토 후 승격.
        'sentiment_gold': (row.get('user_label') or '').strip() or None,
        'emotions_gold': [],                       # 44 멀티라벨은 P4(추후)

        # 약지도 근거(provenance)
        'weak_sentiment': meta['raw_model_label'],
        'weak_kote': {'pos': meta['kote_pos'], 'neg': meta['kote_neg'],
                      'neu': meta['kote_neutral']},
        'applied_rule': meta['applied_rule'],
        'override_sentiment': meta['corrected_label'],
        'override_score': meta['override_score'],

        'label_source': 'kote',                    # 잠정 gold 출처
        'review_status': 'pending',
        'annotator': None,
        'annot_confidence': None,
        'split': None,                             # build_splits.py에서 부여

        'src_hash': src_hash(row.get('source_employee_id')),
    }


def main():
    ap = argparse.ArgumentParser(description='hr-kote-finetune 약지도 JSONL export')
    ap.add_argument('--csv', default=DEFAULT_CSV, help='입력 취득 코퍼스 CSV')
    ap.add_argument('--date', default=date.today().strftime('%y%m%d'),
                    help='스냅샷 날짜 태그(YYMMDD)')
    args = ap.parse_args()

    from src.services.perspective_service import refine_acquired_row

    if not os.path.exists(args.csv):
        print(f'[error] CSV 없음: {args.csv}')
        sys.exit(1)

    rows = list(csv.DictReader(open(args.csv, encoding='utf-8-sig')))
    out_path = os.path.join(DATASET_DIR, 'emotion', f'weak_export_{args.date}.jsonl')
    report_path = os.path.join(DATASET_DIR, 'result', f'export_report_{args.date}.md')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    written = 0
    quarantined = []          # PII 적발 격리 행(JSONL 제외)
    rule_ct = Counter()
    gold_ct = Counter()
    weak_ct = Counter()
    no_srchash = 0

    with open(out_path, 'w', encoding='utf-8') as fout:
        for r in rows:
            text = (r.get('sentence_text') or '').strip()
            pii = audit_pii(text)
            if pii:
                quarantined.append({'id': r.get('id', ''), 'pii': pii,
                                    'text': text[:40]})
                continue
            meta = refine_acquired_row(r)
            rec = build_record(r, meta)
            if rec['src_hash'] is None:
                no_srchash += 1
            rule_ct[rec['applied_rule']] += 1
            gold_ct[rec['sentiment_gold'] or '(없음)'] += 1
            weak_ct[rec['weak_sentiment']] += 1
            fout.write(json.dumps(rec, ensure_ascii=False) + '\n')
            written += 1

    write_report(report_path, args, len(rows), written, quarantined,
                 rule_ct, gold_ct, weak_ct, no_srchash, out_path)
    print(f'[done] 입력 {len(rows)}행 → 기록 {written}행, 격리(PII) {len(quarantined)}행')
    print(f'[write] {out_path}')
    print(f'[write] {report_path}')


def _tbl(items, cols, fmt):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    out += [fmt(i) for i in items]
    return '\n'.join(out)


def write_report(path, args, total, written, quarantined, rule_ct, gold_ct,
                 weak_ct, no_srchash, out_path):
    lines = [
        f'# 약지도 JSONL export 리포트 — {args.date}',
        '',
        f'> 입력: `{os.path.relpath(args.csv, REPO_ROOT)}` · 출력: `{os.path.basename(out_path)}`',
        '> 설계: 0617_05 §5/§10/§14 · 범위=비-🟡, 라벨=3분류, 어노테이터=단독',
        '',
        '## 요약',
        '',
        f'- 입력 행: **{total}**',
        f'- JSONL 기록: **{written}**',
        f'- PII 격리(제외): **{len(quarantined)}**',
        f'- src_hash 없음(원천 ID 결측): **{no_srchash}**',
        '',
        '> ⚠️ sentiment_gold는 **잠정(모델 복사본)** — 사람 검토로 confirmed 승격 전에는 학습 금지.',
        '',
        '## 잠정 gold 분포 (sentiment_gold)',
        '',
        _tbl(sorted(gold_ct.items(), key=lambda x: -x[1]), ['label', '건수'],
             lambda kv: f'| {kv[0]} | {kv[1]} |'),
        '',
        '## 약지도 KoTE 라벨 분포 (weak_sentiment)',
        '',
        _tbl(sorted(weak_ct.items(), key=lambda x: -x[1]), ['label', '건수'],
             lambda kv: f'| {kv[0]} | {kv[1]} |'),
        '',
        '## 발동 규칙 분포 (applied_rule)',
        '',
        _tbl(sorted(rule_ct.items(), key=lambda x: -x[1]), ['rule_id', '건수'],
             lambda kv: f'| {kv[0]} | {kv[1]} |'),
        '',
        '## PII 격리 행 (§14-1 게이트 적발 — JSONL 제외)',
        '',
    ]
    if quarantined:
        lines.append(_tbl(
            quarantined, ['id', 'pii', '문장(앞40)'],
            lambda q: f"| {q['id']} | {','.join(q['pii'])} | "
                      f"{q['text'].replace('|', '/')} |"))
    else:
        lines.append('_없음 — 적발된 구체적 PII 패턴 0건._')
    lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
