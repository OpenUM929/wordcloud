"""배치 시간 영향 측정 — 문장 단위 캐시 생성 비용 정량화.

100문서 샘플로 비교:
  기존 : analyze_emotion(doc)               — 문서 1회 KoTE
  신규 : compute_sentence_raw_scores(doc)    — 문장 N회 KoTE (+ 분할/영어감지)

문서 증가폭(신규/기존 배수, 평가당 추가 초)을 산출해 배치 시간 영향을 추정한다.

⚠️ 실제 KoTE 모델을 로딩한다(수십 초~분 소요 가능). **사용자 허락 후 실행.**

실행: 프로젝트 루트(wordcloud_project)에서
  python plans/2026/0615_08_sentence-kote-cache/test/measure_kote_time.py [N]
문서 출처: .sessions/deploy_sessions.db 의 evaluations.data(JSON).evaluation_document
           (없으면 내장 합성 샘플 사용). 결과는 result/measure_kote_time.txt 에 저장.
"""
import os
import sys
import json
import time
import sqlite3

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DB_PATH = os.path.join(_ROOT, '.sessions', 'deploy_sessions.db')
_RESULT_DIR = os.path.join(os.path.dirname(__file__), '..', 'result')

_SYNTHETIC = [
    "업무 능력이 뛰어납니다. 소통은 아쉽습니다. 전반적으로 우수한 직원입니다.",
    "성실하고 책임감이 훌륭합니다. 다만 협업이 미흡한 편입니다. 발전 가능성이 큽니다.",
    "목표 달성률이 높고 동료 평가가 좋습니다. 보고 체계는 개선이 필요합니다.",
]


def _load_docs(limit):
    docs = []
    if os.path.exists(_DB_PATH):
        try:
            conn = sqlite3.connect(_DB_PATH)
            cur = conn.execute("SELECT data FROM evaluations LIMIT ?", (limit,))
            for (data,) in cur.fetchall():
                try:
                    obj = json.loads(data)
                    doc = obj.get('evaluation_document') or obj.get('evaluation_document_original') or ''
                    if isinstance(doc, str) and doc.strip():
                        docs.append(doc)
                except Exception:
                    continue
            conn.close()
        except Exception as e:
            print(f"[warn] DB 로드 실패({e}) — 합성 샘플 사용")
    if not docs:
        docs = [_SYNTHETIC[i % len(_SYNTHETIC)] for i in range(limit)]
        print(f"[info] DB 문서 없음 — 합성 샘플 {len(docs)}건 사용")
    return docs[:limit]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    docs = _load_docs(limit)

    from src.modules.emotion_analysis import analyze_emotion
    from src.modules.sentence_emotion import compute_sentence_raw_scores
    from src.modules.text_preprocessing import split_sentences

    # warmup (모델 로딩 시간 제외)
    analyze_emotion("워밍업 문장입니다.")
    compute_sentence_raw_scores("워밍업 문장입니다. 두 번째 문장.")

    t0 = time.perf_counter()
    for d in docs:
        analyze_emotion(d)
    t_old = time.perf_counter() - t0

    total_sentences = 0
    t1 = time.perf_counter()
    for d in docs:
        c = compute_sentence_raw_scores(d)
        total_sentences += len(c)
    t_new = time.perf_counter() - t1

    n = len(docs)
    avg_sent = total_sentences / n if n else 0
    ratio = (t_new / t_old) if t_old > 0 else 0
    extra_per_doc = (t_new - t_old) / n if n else 0

    lines = [
        "=== KoTE 문장 캐시 생성 비용 측정 ===",
        f"문서 수            : {n}",
        f"평균 문장 수/문서  : {avg_sent:.2f}",
        f"기존(문서1회) 총   : {t_old:.3f}s  (평가당 {t_old / n * 1000:.1f}ms)" if n else "",
        f"신규(문장N회) 총   : {t_new:.3f}s  (평가당 {t_new / n * 1000:.1f}ms)" if n else "",
        f"배수(신규/기존)    : {ratio:.2f}x",
        f"평가당 추가 시간   : +{extra_per_doc * 1000:.1f}ms",
        f"1.9만명×평균5평가 추정 추가: +{extra_per_doc * 19000 * 5 / 60:.1f}분",
    ]
    report = "\n".join([l for l in lines if l])
    print(report)

    os.makedirs(_RESULT_DIR, exist_ok=True)
    out = os.path.join(_RESULT_DIR, 'measure_kote_time.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(report + "\n")
    print(f"\n[saved] {os.path.abspath(out)}")


if __name__ == '__main__':
    main()
