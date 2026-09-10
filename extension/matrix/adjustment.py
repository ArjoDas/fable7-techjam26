"""Batch-boundary residual adjustment from current training products and fixed replay."""
import argparse,time,json
import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from extension.residual import features
from extension.matrix.common import *
from extension.matrix.growth import OrderedCatalog
from extension.matrix.evaluate import evaluate,summary

class Adjusted:
    def __init__(self,store,model):self.store=store;self.model=model;self.trace={}
    def reset(self,sid,profile):self.store.agent.reset(sid,profile)
    def close(self,sid):self.store.agent._sessions.pop(sid,None)
    def respond(self,sid,text,turn,top_k):
        result=self.store.agent.respond(sid,text,turn,top_k);state=self.store.agent._sessions[sid];pool=state.get('last_candidates',[])[:100]
        ids=list(dict.fromkeys([r['parent_asin'] for r in result['recommendations'] if r['parent_asin'] in pool]+pool))
        if ids:
            probability=self.model.predict_proba(features(text,ids,self.store.agent))[:,1];ranked=sorted(range(len(ids)),key=lambda i:(-(.5/(i+1)+probability[i]),i))
            result={**result,'recommendations':[{'parent_asin':ids[i]} for i in ranked[:top_k]]}
        self.trace[sid]={'candidate_ids':ids,'model_calls':0,'version':self.store.version};return result

def main(schedule,size):
    store=OrderedCatalog(HOME/f'published/{schedule}-{size}');path=HOME/f'adjustment/{schedule}-{size}.json'
    if path.exists():store.close();return
    rows=sorted(read_jsonl(HOME/'prepared/train.jsonl'),key=lambda r:stable(r['sample_id']));membership=json.loads((HOME/'prepared/membership.json').read_text(encoding='utf-8'));base=set(membership[schedule][str(SCHEDULES[schedule][0])])
    replay=[r for r in rows if r['ground_truth']['parent_asin'] in base][:100];replay_ids={r['sample_id'] for r in replay}
    selected=replay+[r for r in rows if r['ground_truth']['parent_asin'] in store.products and r['sample_id'] not in replay_ids][:100]
    began=time.perf_counter();training=evaluate(store.agent,selected,store.products,'wording',SEEDS[0],True);x=[];y=[]
    for row in training:
        for turn in row['turns']:
            pool=turn['candidate_ids'];ids=list(dict.fromkeys([a for a in turn['recommendations'] if a in pool]+pool))[:30]
            if row['target'] in ids:x.extend(features(turn['message'],ids,store.agent));y.extend(int(a==row['target']) for a in ids)
    if len(set(y))<2:
        write_json(path,{'outcome':'infeasible','reason':'Insufficient positive/negative training candidates'});store.close();return
    model=LogisticRegression(max_iter=500,class_weight='balanced',random_state=SEEDS[0]).fit(np.asarray(x),y);seconds=time.perf_counter()-began
    path.parent.mkdir(parents=True,exist_ok=True);joblib.dump(model,path.with_suffix('.joblib'))
    dev=sorted((r for r in read_jsonl(HOME/'prepared/dev.jsonl') if r['ground_truth']['parent_asin'] in store.products),key=lambda r:stable(r['sample_id']))[:120]
    baseline=summary(evaluate(store.agent,dev,store.products,'wording'));adjusted=summary(evaluate(Adjusted(store,model),dev,store.products,'wording'))
    write_json(path,{'manifest':manifest({'schedule':schedule,'size':size},[HOME/'prepared/train.jsonl']),'training_seconds':seconds,'training_tasks':[r['sample_id'] for r in selected],'fixed_replay_ids':sorted(replay_ids),'training_candidate_rows':len(x),
        'base_weights_unchanged':True,'baseline':baseline,'adjusted':adjusted,'outcome':'retain' if adjusted['hit10_by_turn5']>baseline['hit10_by_turn5'] else 'reject','scope':'Separate development ablation, excluded from primary frozen-weight matrix'})
    store.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--schedule',required=True);p.add_argument('--size',type=int,required=True);a=p.parse_args();main(a.schedule,a.size)
