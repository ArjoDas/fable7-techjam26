"""A small extended-route residual ranker; the base encoder and main weights stay frozen."""
import argparse
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from extension.common import ARTIFACTS,read_jsonl,write_json,manifest
from starter.agent import _terms


def features(query,ids,agent):
    words=set(_terms(query));rows=[]
    for i,a in enumerate(ids):
        view=agent._product_views[a];tokens=set(_terms(' '.join(view[:6])));category=set(_terms(view[1]));title=set(_terms(view[0]))
        rows.append([1/(i+1),len(words&tokens)/max(1,len(words)),len(words&title)/max(1,len(words)),len(words&category),np.log1p(agent._popularity.get(a,0))])
    return np.asarray(rows,dtype='float64')


class Residual:
    def __init__(self):self.model=joblib.load(ARTIFACTS/'learned/residual.joblib')
    def rank(self,query,ids,agent):
        probability=self.model.predict_proba(features(query,ids,agent))[:,1]
        return [ids[i] for i in sorted(range(len(ids)),key=lambda i:(-(.5/(i+1)+probability[i]),ids[i]))]


def train(limit):
    from extension.evaluate import build
    from extension.datasets import Shopper
    rows=sorted(read_jsonl(ARTIFACTS/'datasets/train.jsonl'),key=lambda r:r['sample_id'])[:limit]
    store,agent=build('hybrid');x=[];y=[];source=[]
    for row in rows:
        shopper=Shopper(row);sid=row['sample_id'];agent.reset(sid,{});messages=[]
        for turn in range(1,4):
            message=shopper.message(turn,'other');messages.append(message);agent.respond(sid,message,turn,10)
        ids=agent.trace[sid]['candidate_ids'][:30]
        # Never inject a missed positive into training candidates.
        if row['target'] in ids:
            x.extend(features(' '.join(messages),ids,agent.base));y.extend(int(a==row['target']) for a in ids);source.append(sid)
        agent.close(sid)
    # A fixed replay slice of the beginning of this training set receives equal
    # weight at later batch retraining boundaries; no dev or test labels enter.
    replay=min(len(x),300);weights=np.ones(len(x));weights[:replay]=2
    model=LogisticRegression(max_iter=500,class_weight='balanced',random_state=20260910).fit(np.asarray(x),y,sample_weight=weights)
    folder=ARTIFACTS/'learned';folder.mkdir(parents=True,exist_ok=True);joblib.dump(model,folder/'residual.joblib')
    write_json(folder/'residual-training.json',{'manifest':manifest({'limit':limit,'replay_rows':replay},[ARTIFACTS/'datasets/train.jsonl']),
        'eligible_tasks':len(source),'candidate_rows':len(x),'sample_ids':source,'base_weights_modified':False,'encoder_weights_modified':False})
    store.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=200);a=p.parse_args();train(a.limit)
