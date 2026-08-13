# -*- coding: utf-8 -*-
"""실배치 감사 표준 절차 — 단계 4: 오류후보 추출(검토큐, human_decision:null).

단계 3 판독으로 확립한 오류 유형을 고유문장 전체에서 규칙으로 추출·태깅하고,
빈도(production 영향) 내림차순 검토큐를 만든다. 정식 gold 적립은 escalation(미포함).
표준 절차 정본: ../AUDIT_STANDARD.md §2 단계4 · §3 택소노미.
유형:
  E1_ambivalent : 양가 업무태도(너무/과도 + 꼼꼼/철저/열의) + 모델 극성 → 재검(중/긍)
  E2_bareNP_neg : 맨 명사구 칭찬인데 모델=부(필드의존 긍↔부 위험) → 재검(긍?, 필드확인)
  E4_wellbeing_neg : 건강/개인안녕/평가유보 + 모델=부 → 재검(중립)
  E5_clearflip  : rule·KoTE 삼각으로 명백극성인데 모델 반대극성(진짜 긍↔부)
⚠️ substring 함정 주의(RUNBOOK §2-2 A트랙): 강조어+형질 동시조건·해악표지 게이트로 재게이트.
   그래도 큐 항목은 자동 gold 아님 — per-row 사람 판정 대상.

사용:  python audit_extract_queue_260716.py [입력csv]
"""
import io, os, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.join('D:', os.sep, 'dev', 'wordcloud', 'wordcloud_project')
sys.path.insert(0, ROOT)
from src.services import perspective_service as P
IN = sys.argv[1] if len(sys.argv) > 1 else os.path.join('D:', os.sep, 'dev', 'wordcloud', 'data', '25.csv')
QDIR = os.path.join(ROOT, 'plans', '_datasets', 'kote_finetune', 'eval', 'review')
os.makedirs(QDIR, exist_ok=True)
QOUT = os.path.join(QDIR, 'prod25_audit_queue_260716.jsonl')

# 강조어(너무/과다) + 양가형질 → 진짜 양가만. 평이한 칭찬("열의가 높음")은 제외.
AMBI = re.compile(r'(너무|지나치게|과도|과다|과하|넘치).{0,8}(꼼꼼|철저|완벽|적극|열의|열정|세세|예민|깐깐|원칙)'
                  r'|(꼼꼼|철저|완벽|세세|예민).{0,8}(하지만|하나|한데|하여|해서).{0,14}(어려|힘들|부담|아쉽|느림|늦)')
HARM = re.compile(r'(고압|갑질|막말|무시|편향|기복|불성실|독단|강압|비아냥|짜증|화를|욕설|무례)')
def argmax3(p,n,u): m=max(p,n,u); return 'p' if m==p else ('n' if m==n else 'u')
def bareNP(x):
    return len(x.strip())<=25 and not re.search(r'(다|음|함|됨|임|까|요|죠|셈|셨|한다|니다)$', x.strip())

uniq={}
for line in open(IN,encoding='utf-8'):
    line=line.strip()
    if not line: continue
    r=json.loads(line)
    if '#' in r: continue
    x=r.get('x'); y=r.get('y'); s=r.get('s')
    if not x or y not in ('p','n','u') or not s or len(s)<3: continue
    if x not in uniq: uniq[x]={'x':x,'y':y,'s':[float(s[0]),float(s[1]),float(s[2])],'freq':0}
    uniq[x]['freq']+=1

from collections import Counter
cnt=Counter(); queue=[]
for u in uniq.values():
    x=u['x']; my=u['y']; pos,neg,neu=u['s']
    ky=argmax3(pos,neg,neu)
    try:
        sc,tag=P._sentence_sentiment_override_explain(pos,neg,x,True,1,neutral=neu)
        ry='p' if sc>1e-6 else ('n' if sc<-1e-6 else 'u')
    except: ry,tag='u','ERR'
    et=None; sug=None; conf=None
    has_req = bool(re.search(r'(필요|좋겠|좋을|하면|한다면|바람|바랍|늘리|높이|줄이|보완|개선|았으면|었으면|해야|더욱|키우|기르|보강|아쉬|미흡|부족|기대|지만|으나|는데|은데|바랍|부탁)', x))
    # E1 양가/해악 (정책 게이트) — 최우선
    if my in ('p','n') and AMBI.search(x):
        if my=='p' and HARM.search(x):
            et='E1_harm_pos'; sug='n'; conf='mid'      # 해악표지인데 긍정 → 부정 재검
        elif my=='n' and not HARM.search(x):
            et='E1_ambi_neg'; sug='u'; conf='mid'      # 양가(해악없음)인데 부정 → 중립/긍정 재검
    # E5/E2 삼각 명백 flip (진짜 긍↔부)
    if et is None and {my,ry}=={'p','n'} and {my,ky}=={'p','n'}:
        if my=='n' and not has_req:
            et='E2_bareNP_neg' if bareNP(x) else 'E5_clearflip_n'; sug='p'; conf='mid'
        elif my=='p' and not has_req:
            et='E5_clearflip_p'; sug='n'; conf='mid'
    # E4 건강/개인안녕/평가유보 + 모델 부정 → 중립 (원칙 함수, 고신뢰)
    if et is None and my=='n':
        try:
            if P.is_personal_wellbeing_neutral(x) or P.is_health_advice(x) or P.is_cannot_assess(x):
                et='E4_wellbeing_neg'; sug='u'; conf='high'
        except: pass
    if et:
        cnt[et]+=1
        queue.append({'x':x,'model_y':my,'s':u['s'],'freq':u['freq'],
                      'error_type':et,'suggested':sug,'confidence':conf,'rule_y':ry,'kote_y':ky,
                      'human_decision':None,'decision_source':None,'src':'prod25_batch_20260714_0'})

queue.sort(key=lambda q:-q['freq'])
with open(QOUT,'w',encoding='utf-8') as w:
    w.write(json.dumps({'#':'프로덕션 25년(batch_20260714_0) 감사 오류후보 검토큐 — human_decision:null, 정식 gold는 escalation','date':'260716'},ensure_ascii=False)+'\n')
    for q in queue: w.write(json.dumps(q,ensure_ascii=False)+'\n')

print('고유 %d, 큐 %d'%(len(uniq),len(queue)))
print('유형별 (고유 후보수):')
for et,n in cnt.most_common(): print('  %-18s %6d'%(et,n))
print('\n큐 인스턴스 영향 합계:', sum(q['freq'] for q in queue))
print('저장:', QOUT)
