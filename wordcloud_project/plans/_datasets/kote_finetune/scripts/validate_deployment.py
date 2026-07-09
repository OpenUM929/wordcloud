# -*- coding: utf-8 -*-
"""배포 환경 검증 — 파인튜닝 모델 ON/OFF 비교(메타데이터 생성).

배포 후 운영 환경에서:
  python validate_deployment.py --deploy-root <배포경로> --test-data <테스트파일>

산출: 메타데이터 JSON + 리포트(극성 불일치 샘플 포함).
"""
import argparse
import json
import os
import sys
from collections import Counter

# 배포 경로 추가
ap = argparse.ArgumentParser()
ap.add_argument('--deploy-root', required=True, help='배포 디렉터리(wordcloud_*)')
ap.add_argument('--test-data', required=True, help='테스트 JSONL 파일 (text/이미 s=[pos/neg/neu])')
ap.add_argument('--out', default='deployment_validation.json')
args = ap.parse_args()

deploy_root = args.deploy_root
sys.path.insert(0, os.path.join(deploy_root, 'source'))

from src.config.settings import MODEL_PATH, HR_SENTIMENT_MODEL_PATH, USE_HR_SENTIMENT_MODEL
from src.modules.emotion_analysis import analyze_emotion_batch
from src.services.perspective_service import _sentence_sentiment_override_explain as ov

# 테스트 데이터 로드 (파일의 s=[pos/neg/neu] 사용)
rows = []
with open(args.test_data, encoding='utf-8') as f:
    for line in f:
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get('s'):  # KoTE 점수 있으면 사용
                rows.append(r)
        except:
            pass

if not rows:
    print('테스트 데이터 없음')
    sys.exit(1)

print(f'테스트: {len(rows)}건')

# before: 규칙 파이프라인(모델 OFF)
os.environ['USE_HR_SENTIMENT_MODEL'] = '0'
# (모듈 재로드 필요 — 간단히 수동으로 override 계산)
before = []
for r in rows:
    pos, neg, neu = r['s'].get('pos', 0), r['s'].get('neg', 0), r['s'].get('neutral', 0)
    t = r.get('text', '')
    score, _rule = ov(pos, neg, t, True, 1, neutral=neu)
    pol = 'positive' if score > 1e-6 else ('negative' if score < -1e-6 else 'neutral')
    before.append({'text': t[:50], 'rule_pol': pol})

# after: 파인튜닝 모델(모델 ON)
os.environ['USE_HR_SENTIMENT_MODEL'] = '1'
from src.modules import hr_sentiment  # 재로드
m = hr_sentiment._get()
if m is None:
    print('⚠️ 모델 로드 실패 → 규칙으로만 검증')
    after = before
else:
    texts = [r.get('text', '') for r in rows]
    model_pols = m.predict(texts)
    after = [{'text': t[:50], 'model_pol': p} for t, p in zip(texts, model_pols)]

# 비교 + 메타데이터
diff = []
for b, a in zip(before, after):
    if b.get('rule_pol') != a.get('model_pol'):
        diff.append({'text': b['text'], 'rule': b.get('rule_pol'), 'model': a.get('model_pol')})

rule_dist = Counter(b.get('rule_pol') for b in before)
model_dist = Counter(a.get('model_pol') for a in after)

meta = {
    'deployment': deploy_root,
    'test_count': len(rows),
    'model_path': HR_SENTIMENT_MODEL_PATH,
    'model_available': m is not None,
    'use_hr_sentiment_model': USE_HR_SENTIMENT_MODEL,
    'before_distribution': dict(rule_dist),
    'after_distribution': dict(model_dist),
    'difference_count': len(diff),
    'difference_rate': f'{100*len(diff)/len(rows):.1f}%',
    'sample_differences': diff[:10]  # 처음 10개만
}

with open(args.out, 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f'\n=== 검증 결과 ===')
print(f'모델 로드: {"✓" if m else "✗"} USE_HR_SENTIMENT_MODEL={USE_HR_SENTIMENT_MODEL}')
print(f'규칙 분포: {dict(rule_dist)}')
print(f'모델 분포: {dict(model_dist)}')
print(f'극성 변화: {len(diff)}건 ({meta["difference_rate"]})')
print(f'메타데이터 → {args.out}')
