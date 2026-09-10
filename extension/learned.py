from extension.common import dataset_path
"""Train-only calibrated intent classification and frozen residual ranking."""
import argparse
import json
import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion,Pipeline
from sklearn.linear_model import LogisticRegression
from extension.common import ARTIFACTS,read_jsonl,write_json,manifest
from extension.datasets import Shopper


def label(row,turn):
    if turn==3 and row['scenario'] in ('category_override','partial_override'):return row['scenario']
    if row['scenario'] in ('browsing','browsing_to_buying') and (turn<3 or row['scenario']=='browsing'):return 'browsing'
    return 'buying'


class Router:
    def __init__(self,path=None):self.pipeline=joblib.load(path or ARTIFACTS/'learned/router.joblib')
    def predict(self,text,history=''):
        probabilities=self.pipeline.predict_proba([history[-400:]+' [TURN] '+text])[0]
        index=int(np.argmax(probabilities));return str(self.pipeline.classes_[index]),float(probabilities[index])


def train():
    rows=sorted(read_jsonl(dataset_path('train')),key=lambda r:r['sample_id']);texts=[];labels=[];groups=[]
    for row in rows:
        shopper=Shopper(row);history=''
        for turn in range(1,6):
            text=shopper.message(turn,'other');texts.append(history[-400:]+' [TURN] '+text);labels.append(label(row,turn));groups.append(row['sample_id']);history+=' '+text
    features=FeatureUnion([('word',TfidfVectorizer(ngram_range=(1,2),max_features=20000,min_df=2)),('char',TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=30000,min_df=2))])
    from sklearn.model_selection import GroupKFold
    folds=list(GroupKFold(3).split(texts,labels,groups))
    classifier=CalibratedClassifierCV(LogisticRegression(max_iter=600,class_weight='balanced',random_state=20260910),cv=folds)
    model=Pipeline([('features',features),('classifier',classifier)]);model.fit(texts,labels)
    folder=ARTIFACTS/'learned';folder.mkdir(parents=True,exist_ok=True);joblib.dump(model,folder/'router.joblib')
    write_json(folder/'router-training.json',{'manifest':manifest({'labels':'buying/browsing/partial_override/category_override','calibration_cv':3,'calibration_group':'product task'},[dataset_path('train')]),
        'product_tasks':len(rows),'turns':len(texts),'training_only':True})


def score():
    from sklearn.metrics import classification_report,confusion_matrix
    rows=read_jsonl(dataset_path('dev'));router=Router();truth=[];pred=[];prob=[]
    for row in rows:
        shopper=Shopper(row);history=''
        for turn in range(1,6):
            text=shopper.message(turn,'other');y,p=router.predict(text,history);truth.append(label(row,turn));pred.append(y);prob.append(p);history+=' '+text
    write_json(ARTIFACTS/'learned/router-dev.json',{'manifest':manifest({},[dataset_path('dev')]),
        'classification_report':classification_report(truth,pred,output_dict=True,zero_division=0),'confusion_matrix':confusion_matrix(truth,pred).tolist(),
        'mean_confidence':float(np.mean(prob))})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['train','score']);a=p.parse_args();train() if a.action=='train' else score()
