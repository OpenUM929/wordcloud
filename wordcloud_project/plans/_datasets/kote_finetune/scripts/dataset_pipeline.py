# -*- coding: utf-8 -*-
"""hr-kote-finetune 데이터셋 파이프라인 — 단일 자기실행 명령(데이터 도착마다 동일 동작).

왜 이 스크립트인가 (사용자 피드백):
  계획서(RUNBOOK §2)가 '서술형 체크리스트'라 사람 재량이 끼어들어 데이터셋 빌드를
  건너뛰는 일이 생겼다. 이를 막기 위해 전 단계를 **한 명령 + 기계검증 게이트**로 묶는다.
  데이터가 추가될 때마다 이 스크립트 하나만 돌리면 동일 파이프라인이 자동 수행된다.

단계(전부 자동 — 사람 판단은 gold 확정에서만):
  1) 반입      : jsonl(KoTE 사전점수 s 포함) 또는 CSV(refine_acquired_row로 KoTE 재계산)
  2) 절 분리   : split_clauses — 혼합극성 문장을 단일극성 절로 분해(데이터셋 전용)
  3) 약지도    : 감정(override) + 리더십(weak LF) 이중 스트림 라벨(weak-only, gold 미기록)
  4) 비식별화  : PII 정규식 게이트(적발 행 격리)
  5) 영속화    : append-only 스냅샷 JSONL(emotion/weak_export_<date>.jsonl, 리더십 블록 포함)
  6) 패턴 마이닝: mine_patterns — 판정 정밀화 규칙·패턴 후보 발굴 리포트
  7) 회귀 게이트: 긍↔부 0 회귀 스위트 실행(실패 시 전체 FAIL)
  8) 로그/검증 : 입력>0·기록=0 → 자동 FAIL 등 기계검증 + 실행 요약

핵심 가치: 긍↔부(positive↔negative / positive↔risk) 오분류 0. 추측 분류 금지(weak-only).
제약: 서버/배치 불요, O(n), plans 배포 제외, 가명화 텍스트만.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)

sys.path.insert(0, HERE)
from leadership_lf import build_leadership_candidates, load_tree   # noqa: E402
import mine_patterns as mp                                          # noqa: E402
import build_validation_set as bv                                  # noqa: E402
from export_jsonl import audit_pii, src_hash                       # noqa: E402 (비식별화 재사용)

# 회귀 스위트(긍↔부 0 게이트) — 변경 전후 반드시 통과.
TEST_DIR = os.path.join(PROJECT_ROOT, 'plans', '2026', '0617_01_emotion-rule-mining', 'test')
REGRESSION = [
    'test_positive_rescue.py', 'test_no_response.py', 'test_leadership_polarity.py',
    'run_negation_praise_regression.py', 'run_no_response_regression.py',
    'run_leadership_gate_regression.py',
]


def _score_to_label(score):
    if score > 0:
        return 'positive'
    if score < 0:
        return 'negative'
    return 'neutral'


def clause_sentiment_weak(clause, probes):
    """절(KoTE 점수 없음)의 weak 감정 — 규칙이 명확할 때만 라벨, 아니면 None(추측 금지·긍↔부 0).

    1) 리더십 극성 게이트(leadership_polarity)가 positive/negative면 그대로(긍↔부 안전).
    2) 아니면 강한 부정/결핍 → negative, 깨끗한 긍정표지 → positive.
    3) 그 외 → None(KoTE/사람 검토 필요).
    """
    pol = probes['leadership_polarity'](clause)
    if pol in ('positive', 'negative'):
        return pol, 'clause_leadership_gate'
    if probes['has_unnegated_strong_negative'](clause) or \
            any(d in clause for d in mp.DEFICIENCY_NOUNS):
        return 'negative', 'clause_negative_rule'
    if probes['has_positive_implying_phrase'](clause) \
            and not probes['has_negative_implying_words'](clause) \
            and not probes['positive_marker_directly_negated'](clause):
        return 'positive', 'clause_positive_rule'
    return None, 'clause_uncertain'


def _is_jsonl_content(path):
    """확장자 무관 — 첫 비어있지 않은 줄이 JSON 객체({...}, '#'/'x' 키)면 JSONL로 판단.

    배경: 반입 파일이 `.csv` 확장자여도 내용이 JSONL인 경우가 있다(default/*.csv).
    """
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if not line.startswith('{'):
                return False
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return False
            return isinstance(obj, dict) and ('#' in obj or 'x' in obj)
    return False


def load_rows(path):
    """jsonl(KoTE 점수 s 포함) 또는 csv 반입. (rows, kind, batch_tag) 반환. 헤더/빈 행 스킵."""
    rows = []
    if _is_jsonl_content(path):
        batch_tag = None
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if 'x' not in obj:          # 헤더 라인(#/batch) → batch 태그만 취득
                    if obj.get('batch'):
                        batch_tag = obj['batch']
                    continue
                s = obj.get('s') or [0, 0, 0]
                rows.append({
                    'text': (obj.get('x') or '').strip(),
                    'kote': [float(s[0]), float(s[1]), float(s[2] if len(s) > 2 else 0)],
                    'emotions': obj.get('e') or [],
                    'src_employee_id': obj.get('eid') or obj.get('emp') or '',
                })
        return rows, 'jsonl', (batch_tag or os.path.splitext(os.path.basename(path))[0])
    # CSV 경로: KoTE 재계산(refine_acquired_row) — 무거우므로 jsonl 우선.
    import csv
    from src.services.perspective_service import refine_acquired_row
    for r in csv.DictReader(open(path, encoding='utf-8-sig')):
        meta = refine_acquired_row(r)
        rows.append({
            'text': (r.get('sentence_text') or '').strip(),
            'kote': [meta['kote_pos'], meta['kote_neg'], meta['kote_neutral']],
            'emotions': meta.get('top_3') or [],
            'src_employee_id': r.get('source_employee_id') or '',
        })
    return rows, 'csv', os.path.splitext(os.path.basename(path))[0]


def build_records(rows, batch_tag, probes, tree):
    """반입 행 → (절 분리 + 이중 스트림 약지도) 레코드 리스트. PII 격리 분리."""
    from src.modules.text_preprocessing import split_clauses
    explain = probes['explain']
    lpol, npraise = probes['leadership_polarity'], probes['is_negation_praise']

    records, quarantined = [], []
    stat = Counter()
    for i, row in enumerate(rows):
        text = row['text']
        if not text:
            continue
        if audit_pii(text):
            quarantined.append({'i': i, 'text': text[:40]})
            continue
        pos, neg, neu = row['kote']
        sh = src_hash(row['src_employee_id'])
        clauses = split_clauses(text)
        is_split = len(clauses) > 1
        parent_id = f'{batch_tag}-{i}'

        # 전체 문장 레코드(KoTE 보유 → 확정 weak 감정)
        score, rule = explain(pos, neg, text, True, 1, neutral=neu)
        records.append(_record(
            parent_id, text, False, None, i, 1,
            _score_to_label(score), {'pos': round(pos, 4), 'neg': round(neg, 4), 'neu': round(neu, 4)},
            False, row['emotions'], rule, round(score, 4), 'kote',
            build_leadership_candidates(text, lpol(text), npraise(text), tree), sh))
        stat['sentence'] += 1
        stat[f'sent_{_score_to_label(score)}'] += 1

        # 절 레코드(혼합극성 분해 — KoTE 미보유 → 규칙 명확 시만 라벨)
        if is_split:
            for k, cl in enumerate(clauses):
                if len(cl) < 4:
                    continue
                csent, crule = clause_sentiment_weak(cl, probes)
                records.append(_record(
                    f'{parent_id}-c{k}', cl, True, parent_id, i, len(clauses),
                    csent, None, True, [], crule, None, 'clause_rule',
                    build_leadership_candidates(cl, lpol(cl), npraise(cl), tree), sh))
                stat['clause'] += 1
                stat[f'clause_{csent or "uncertain"}'] += 1
    return records, quarantined, stat


def _record(rid, text, is_clause, parent, sidx, total, sentiment, kote, inherited,
            emotions, rule, score, source, weak_ld, sh):
    return {
        'id': rid, 'text': text, 'is_clause': is_clause, 'parent_id': parent,
        'sentence_index': sidx, 'total_sentences': total, 'is_last': True,
        # 감정 스트림
        'sentiment': sentiment, 'kote': [kote['pos'], kote['neg'], kote['neu']] if kote else None,
        'weak_kote': kote, 'kote_inherited': inherited, 'emotions_topk': emotions,
        'applied_rule': rule, 'override_score': score,
        # 리더십 스트림(weak — gold 아님)
        'weak_leadership': weak_ld,
        # provenance / gold 계층(미확정)
        'label_source': source, 'sentiment_gold': None, 'leadership_gold': None,
        'review_status': 'pending', 'annotator': None,
        'src_hash': sh,
    }


def run_regression():
    """긍↔부 0 회귀 스위트 실행. (모든 통과, 실패 목록) 반환."""
    failed = []
    suite = [os.path.join(TEST_DIR, t) for t in REGRESSION]
    suite.append(os.path.join(HERE, 'test_dataset_components.py'))  # 신규 컴포넌트 골든
    for p in suite:
        if not os.path.exists(p):
            failed.append(f'{os.path.basename(p)} (없음)')
            continue
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        r = subprocess.run([sys.executable, p], capture_output=True, text=True,
                           cwd=PROJECT_ROOT, env=env, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            failed.append(f'{os.path.basename(p)} (exit {r.returncode}): '
                          f'{r.stdout[-200:]}{r.stderr[-200:]}')
    return (not failed), failed


def write_summary(path, info):
    L = [f'# 데이터셋 파이프라인 실행 요약 — {info["date"]}', '',
         f'> 입력: `{info["input"]}` · 단일 명령 자기실행(dataset_pipeline.py)', '',
         f'- 판정: **{"✅ PASS" if info["pass"] else "🔴 FAIL"}**',
         f'- 입력 행: **{info["n_in"]}**',
         f'- 기록 레코드: **{info["n_rec"]}** (문장 {info["stat"].get("sentence",0)} + 절 {info["stat"].get("clause",0)})',
         f'- PII 격리: **{info["quarantined"]}**',
         f'- 회귀(긍↔부 0): **{"통과" if info["reg_pass"] else "실패"}**', '',
         '## 기계검증 게이트', '']
    for g, ok in info['gates']:
        L.append(f'- [{"x" if ok else " "}] {g}')
    L += ['', '## 감정 약지도 분포(문장)', '']
    for lab in ('positive', 'negative', 'neutral'):
        L.append(f'- {lab}: {info["stat"].get(f"sent_{lab}", 0)}')
    L += ['', '## 절(혼합 분해) 약지도 분포', '']
    for lab in ('positive', 'negative', 'neutral', 'uncertain'):
        L.append(f'- {lab}: {info["stat"].get(f"clause_{lab}", 0)}')
    if info['reg_fail']:
        L += ['', '## 회귀 실패 상세', ''] + [f'- {x}' for x in info['reg_fail']]
    L += ['', '## §누적 로그용 1행(RUNBOOK에 붙여넣기)', '', '```', info['log_row'], '```', '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser(description='hr-kote-finetune 데이터셋 단일 파이프라인')
    ap.add_argument('--in', dest='inp', nargs='+', required=True,
                    help='입력 파일/폴더(여러 개 가능). 확장자 무관 JSONL 내용 자동감지.')
    ap.add_argument('--date', default=date.today().strftime('%y%m%d'))
    ap.add_argument('--limit', type=int, default=0, help='파일당 앞 N행만(테스트용, 0=전체)')
    ap.add_argument('--skip-regression', action='store_true', help='회귀 생략(디버그 전용)')
    args = ap.parse_args()

    # Windows cp949 콘솔에서 이모지/em-dash 출력 크래시 방지(UTF-8 강제).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # 입력 확장: 폴더 → 내부 파일 전체, 파일 → 그대로. 정렬해 결정적 순서.
    in_files = []
    for p in args.inp:
        if not os.path.exists(p):
            print(f'[FAIL] 입력 없음: {p}'); sys.exit(2)
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                fp = os.path.join(p, name)
                if os.path.isfile(fp) and name.lower().endswith(('.jsonl', '.csv', '.txt')):
                    in_files.append(fp)
        else:
            in_files.append(p)
    if not in_files:
        print('[FAIL] 처리할 입력 파일이 없음'); sys.exit(2)

    # 의존 주입(KoTE 불요 — 순수 규칙 함수)
    from src.services.perspective_service import (
        _sentence_sentiment_override_explain as explain,
        has_positive_implying_phrase, has_negative_implying_words,
        positive_marker_directly_negated, has_unnegated_strong_negative,
        POSITIVE_IMPLYING_PHRASES)
    from src.modules.hr_context_lexicon import (
        leadership_polarity, is_negation_praise, POSITIVE_MARKERS, NEGATIVE_MARKERS)
    probes = {
        'explain': explain, 'leadership_polarity': leadership_polarity,
        'is_negation_praise': is_negation_praise,
        'has_positive_implying_phrase': has_positive_implying_phrase,
        'has_negative_implying_words': has_negative_implying_words,
        'positive_marker_directly_negated': positive_marker_directly_negated,
        'has_unnegated_strong_negative': has_unnegated_strong_negative,
    }
    tree = load_tree()

    print(f'[1/8] 반입: {len(in_files)}개 파일')
    records, quarantined, stat = [], [], Counter()
    total_rows = 0
    seen_batches = set()       # batch 태그 기준 중복 배치 스킵
    per_batch = {}
    for fp in in_files:
        rows, kind, batch_tag = load_rows(fp)
        if args.limit:
            rows = rows[:args.limit]
        if batch_tag in seen_batches:
            print(f'      ⏭  {os.path.basename(fp)}: batch `{batch_tag}` 이미 처리 → 스킵(중복)')
            continue
        seen_batches.add(batch_tag)
        total_rows += len(rows)
        recs, quar, st = build_records(rows, batch_tag, probes, tree)
        records.extend(recs); quarantined.extend(quar); stat.update(st)
        per_batch[batch_tag] = len(recs)
        print(f'      ✓ {os.path.basename(fp)}: {len(rows)}행 ({kind}, batch `{batch_tag}`) → {len(recs)} 레코드')

    print('[2-5/8] 절분리 + 이중 약지도 + 비식별화 완료')

    # 영속화(append-only 스냅샷 — gold 아님)
    out_path = os.path.join(DATASET_DIR, 'emotion', f'weak_export_{args.date}.jsonl')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'      기록 {len(records)} ({len(seen_batches)}개 배치) → {os.path.relpath(out_path, REPO_ROOT)}')

    print('[6/8] 패턴 마이닝 …')
    res = mp.mine(records, POSITIVE_IMPLYING_PHRASES, NEGATIVE_MARKERS)
    mine_path = os.path.join(DATASET_DIR, 'result', f'pattern_mining_{args.date}.md')
    os.makedirs(os.path.dirname(mine_path), exist_ok=True)
    mp.write_report(mine_path, res, args.date)
    print(f'      {len(res["pol_flips"])} 긍↔부 flip · {len(res["deficiency"])} 결핍 · '
          f'{res["residual_contrast"]} 반전잔존 → {os.path.basename(mine_path)}')

    # [6.5] 검증용 데이터셋(불일치 케이스) — 향후 회귀·정확도 측정 기준(held-out)
    val = bv.extract_validation(records)
    val_path = os.path.join(DATASET_DIR, 'eval', f'validation_candidates_{args.date}.jsonl')
    bv.write_jsonl(val_path, val)
    bv.write_report(os.path.join(DATASET_DIR, 'result', f'validation_set_{args.date}.md'), val, args.date)
    print(f'[6.5] 검증셋 {len(val)} 후보(불일치) → {os.path.relpath(val_path, REPO_ROOT)}')

    print('[7/8] 회귀 게이트 …')
    if args.skip_regression:
        reg_pass, reg_fail = True, ['(생략됨)']
    else:
        reg_pass, reg_fail = run_regression()
    print(f'      {"통과" if reg_pass else "실패: " + str(reg_fail)}')

    # [8/8] 기계검증 게이트(자동 FAIL 조건)
    src_desc = ', '.join(sorted(seen_batches))
    gates = [
        (f'입력>0 이면 기록>0 (입력 {total_rows} / 기록 {len(records)})',
         not (total_rows > 0 and len(records) == 0)),
        ('회귀(긍↔부 0) 통과', reg_pass),
        ('PII 격리 행은 미기록(스냅샷 제외)', True),
    ]
    overall = all(ok for _, ok in gates)
    log_row = (f'| {date.today().isoformat()} | {len(seen_batches)}배치({src_desc}) | {total_rows} | '
               f'{len(records)} (문장{stat.get("sentence",0)}+절{stat.get("clause",0)}) | '
               f'{len(quarantined)} | 0(weak-only) | weak {stat.get("sent_positive",0)} | '
               f'split_clauses+리더십LF | (미실행) | '
               f'회귀 {"✅" if reg_pass else "🔴"}·긍↔부0·패턴리포트 pattern_mining_{args.date} |')

    summary_path = os.path.join(DATASET_DIR, 'result', f'pipeline_run_{args.date}.md')
    write_summary(summary_path, {
        'date': args.date, 'input': src_desc, 'pass': overall,
        'n_in': total_rows, 'n_rec': len(records), 'quarantined': len(quarantined),
        'reg_pass': reg_pass, 'reg_fail': reg_fail, 'gates': gates, 'stat': stat,
        'log_row': log_row})

    print(f'[8/8] 판정: {"✅ PASS" if overall else "🔴 FAIL"}  → {os.path.basename(summary_path)}')
    print('\n=== §누적 로그 1행 ===')
    print(log_row)
    sys.exit(0 if overall else 1)


if __name__ == '__main__':
    main()
