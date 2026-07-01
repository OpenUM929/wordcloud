# -*- coding: utf-8 -*-
"""감정 스트림 D1 — KoTE 미피복 부분코퍼스 멀티뷰 군집 (Track A, 무모델·O(n)).

목적(계획서 0624_04): KoTE 44가 못 잡는 영역("없음" 28%·저신뢰 15%·rule4_default
무보정)을 무지도 군집해 **신규 HR 화행 그룹 ≤3개 후보**를 근거와 함께 발굴한다.
군집은 후보 제시까지만 — gold는 대표 판정(사람/AI)으로만 확정(군집≠gold).

방법(멀티뷰 피처, 필드 1급 + 규칙신호 동반 → 폴리세미 가드):
  TF-IDF(HR n-gram) ⊕ KoTE top-3 감정(44) ⊕ [pos,neg,neu] ⊕ field(장점/단점)
  ⊕ applied_rule ⊕ override_score  →  MiniBatchKMeans(k-sweep, silhouette) 또는 sklearn HDBSCAN.

제약: dev·CSV/로컬 분석만, 서버/GPU/배치 불요, plans 배포 제외. 대표 예문은 가명(스냅샷은
이미 PII 격리분 제외). 입력 = emotion/weak_export_<date>.jsonl(dataset_pipeline 산출).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler, normalize
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.config.settings import EMOTION_NAMES  # noqa: E402
from src.services.perspective_service import (  # noqa: E402
    is_no_weakness_declaration, has_improvement_request, is_no_response)

EMO_IDX = {n: i for i, n in enumerate(EMOTION_NAMES)}
N_EMO = len(EMOTION_NAMES)
# 블록 가중(해석 우선 — 어휘가 화행을 가르고, 감정/극성/필드/규칙은 맥락 보강).
W_TFIDF, W_EMO, W_POL, W_FIELD, W_RULE = 1.0, 0.6, 0.6, 0.8, 0.3
LOWCONF = 0.40  # 저신뢰 임계 max(pos,neg)


def field_of(rid):
    if '_1-' in rid:
        return '장점'
    if '_0-' in rid:
        return '단점'
    return '?'


def kote_top1(emotions_topk):
    for it in (emotions_topk or []):
        if isinstance(it, list) and it:
            return it[0]
    return None


def load_uncovered(path, limit=0, exclude_known=False):
    """문장 레코드 중 'KoTE 미피복'만 적재(없음 ∪ 저신뢰 ∪ rule4_default).

    exclude_known=True → 기존 화행 술어(약점부재·개선요청·무응답)로 잡히는 행 제외
    = 규칙 밖 미탐색 공간만 군집(순환 회피, work_convergence_analysis 권고).
    """
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r.get('is_clause'):
                continue
            k = r.get('kote') or [0, 0, 0]
            t1 = kote_top1(r.get('emotions_topk'))
            uncovered = (t1 == '없음') or (max(k[0], k[1]) < LOWCONF) \
                or (r.get('applied_rule') == 'rule4_default')
            if not uncovered:
                continue
            if exclude_known:
                t = r.get('text') or ''
                if is_no_weakness_declaration(t) or has_improvement_request(t) or is_no_response(t):
                    continue
            rows.append({
                'text': r.get('text') or '',
                'pos': float(k[0]), 'neg': float(k[1]), 'neu': float(k[2] if len(k) > 2 else 0),
                'field': field_of(r.get('id', '')),
                'rule': r.get('applied_rule') or '(none)',
                'ovr': float(r.get('override_score') or 0.0),
                'emos': r.get('emotions_topk') or [],
                'sent': r.get('sentiment') or 'none',
            })
            if limit and len(rows) >= limit:
                break
    return rows


def build_features(rows):
    texts = [r['text'] for r in rows]
    tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=20, max_features=800,
                            token_pattern=r'(?u)\b\w\w+\b')
    X_txt = tfidf.fit_transform(texts)

    # KoTE top-3 감정 44-dim(점수 가중)
    E = np.zeros((len(rows), N_EMO), dtype=np.float32)
    for i, r in enumerate(rows):
        for it in r['emos'][:3]:
            if isinstance(it, list) and len(it) == 2 and it[0] in EMO_IDX:
                E[i, EMO_IDX[it[0]]] = float(it[1])
    E = normalize(E)

    POL = np.array([[r['pos'], r['neg'], r['neu']] for r in rows], dtype=np.float32)
    POL = StandardScaler().fit_transform(POL)

    fields = sorted({r['field'] for r in rows})
    FID = {f: j for j, f in enumerate(fields)}
    F = np.zeros((len(rows), len(fields)), dtype=np.float32)
    for i, r in enumerate(rows):
        F[i, FID[r['field']]] = 1.0

    rules = sorted({r['rule'] for r in rows})
    RID = {x: j for j, x in enumerate(rules)}
    R = np.zeros((len(rows), len(rules) + 1), dtype=np.float32)
    for i, r in enumerate(rows):
        R[i, RID[r['rule']]] = 1.0
        R[i, -1] = r['ovr']
    R[:, -1:] = StandardScaler().fit_transform(R[:, -1:])

    dense = np.hstack([E * W_EMO, POL * W_POL, F * W_FIELD, R * W_RULE]).astype(np.float32)
    X = sparse.hstack([X_txt * W_TFIDF, sparse.csr_matrix(dense)]).tocsr()
    return X, tfidf


def sweep_k(X, ks, sample=8000, seed=0):
    rng = np.random.RandomState(seed)
    idx = rng.choice(X.shape[0], min(sample, X.shape[0]), replace=False)
    best = None
    scores = []
    for k in ks:
        km = MiniBatchKMeans(n_clusters=k, random_state=seed, batch_size=2048, n_init=3)
        labels = km.fit_predict(X)
        sil = silhouette_score(X[idx], labels[idx])
        scores.append((k, sil))
        if best is None or sil > best[1]:
            best = (k, sil, km, labels)
    return best, scores


def char_clusters(rows, labels, tfidf, k):
    feat_names = tfidf.get_feature_names_out()
    out = []
    for c in range(k):
        members = [i for i in range(len(rows)) if labels[i] == c]
        if not members:
            continue
        sz = len(members)
        # top 어휘(군집 평균 TF-IDF 상위) — 텍스트만 재벡터화해 상위어 추출
        sub_txt = [rows[i]['text'] for i in members]
        sv = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=2000,
                             token_pattern=r'(?u)\b\w\w+\b')
        try:
            M = sv.fit_transform(sub_txt)
            means = np.asarray(M.mean(axis=0)).ravel()
            top = [sv.get_feature_names_out()[j] for j in means.argsort()[::-1][:10]]
        except ValueError:
            top = []
        emo = Counter()
        fld = Counter()
        sent = Counter()
        pol = []
        for i in members:
            t1 = kote_top1(rows[i]['emos'])
            emo[t1 or '—'] += 1
            fld[rows[i]['field']] += 1
            sent[rows[i]['sent']] += 1
            pol.append(rows[i]['pos'] - rows[i]['neg'])
        reps = [rows[i]['text'][:50] for i in members[:6]]
        out.append({
            'c': c, 'size': sz, 'top': top,
            'emo': emo.most_common(4), 'field': dict(fld), 'sent': dict(sent),
            'pol_mean': round(float(np.mean(pol)), 3), 'reps': reps,
        })
    out.sort(key=lambda d: -d['size'])
    return out


def write_report(path, info, clusters, scores, date_tag):
    L = [f'# 감정 군집 발굴 — Track A (D1) — {date_tag}', '',
         '> 계획서 `plans/2026/0624_04_emotion-clustering`. KoTE 미피복 부분코퍼스 무지도 군집.',
         '> ⚠️ 군집은 후보까지만 — gold는 대표 판정으로만(군집≠gold). 신규그룹 ≤3 승격은 4조건 AND.', '',
         f'- 입력: `{info["input"]}`',
         f'- 미피복 부분코퍼스(없음 ∪ 저신뢰<{LOWCONF} ∪ rule4_default): **{info["n"]:,}**',
         f'- 선택 k = **{info["k"]}** (silhouette {info["sil"]:.3f})',
         f'- k-sweep: ' + ', '.join(f'k{k}={s:.3f}' for k, s in scores), '',
         '## 군집 (크기순)', '']
    for d in clusters:
        fld = ', '.join(f'{k} {v}' for k, v in sorted(d['field'].items(), key=lambda x: -x[1]))
        emo = ', '.join(f'{n}:{c}' for n, c in d['emo'])
        snt = ', '.join(f'{k} {v}' for k, v in sorted(d['sent'].items(), key=lambda x: -x[1]))
        L += [f'### C{d["c"]} — {d["size"]:,}행 · 극성평균(pos-neg) {d["pol_mean"]}',
              f'- top 표현: {", ".join(d["top"])}',
              f'- KoTE top-1: {emo}',
              f'- 필드: {fld}  |  규칙판정(sentiment): {snt}',
              '- 대표문(가명):']
        for rep in d['reps']:
            L.append(f'  - {rep}')
        L.append('')
    L += ['## 다음 (계획서 D3/D4)',
          '- 위 군집 중 4조건(빈도·응집·KoTE미피복·HR의미) 만족 + 필드 극성 비분리 → 신규그룹 ≤3 승격 후보.',
          '- 승격 후보 대표문 → 판정 패킷(0623_01) → /judgment_apply(0624_03) → gold 확정.', '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser(description='감정 스트림 D1 Track A 군집')
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--date', default='260624')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--ks', type=int, nargs='+', default=[10, 14, 18, 22])
    ap.add_argument('--exclude-known', action='store_true',
                    help='기존 화행 술어(약점부재·개선요청·무응답)로 잡히는 행 제외=미탐색 공간만')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print(f'[1/4] 반입(미피복 필터{"·기존규칙제외" if args.exclude_known else ""}): {os.path.basename(args.inp)}')
    rows = load_uncovered(args.inp, args.limit, exclude_known=args.exclude_known)
    print(f'      대상 {len(rows):,}행')
    print('[2/4] 피처 구성(멀티뷰: TF-IDF⊕감정⊕극성⊕필드⊕규칙)')
    X, tfidf = build_features(rows)
    print(f'      피처 차원 {X.shape[1]:,}')
    print(f'[3/4] k-sweep {args.ks} + silhouette')
    (k, sil, km, labels), scores = sweep_k(X, args.ks)
    print(f'      선택 k={k} sil={sil:.3f}')
    print('[4/4] 군집 특성화 + 리포트')
    clusters = char_clusters(rows, labels, tfidf, k)
    out = os.path.join(DATASET_DIR, 'result', f'emotion_clusters_{args.date}.md')
    write_report(out, {'input': os.path.basename(args.inp), 'n': len(rows), 'k': k, 'sil': sil},
                 clusters, scores, args.date)
    print(f'      → {os.path.relpath(out, PROJECT_ROOT)}')


if __name__ == '__main__':
    main()
