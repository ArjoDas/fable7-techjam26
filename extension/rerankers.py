"""Pinned ONNX cross-encoder comparison, with no remote executable model code."""
import argparse
import json
from pathlib import Path
import urllib.request
import numpy as np
from extension.common import ARTIFACTS,manifest,write_json,sha256

REPOS={'tinybert':'cross-encoder/ms-marco-TinyBERT-L2-v2','minilm':'cross-encoder/ms-marco-MiniLM-L6-v2'}


def download():
    from huggingface_hub import HfApi,hf_hub_download
    api=HfApi(token=False)
    for name,repo in REPOS.items():
        folder=ARTIFACTS/'models'/name;folder.mkdir(parents=True,exist_ok=True)
        info=api.model_info(repo);files=api.list_repo_files(repo,revision=info.sha)
        candidates=['onnx/model_quint8_avx2.onnx','onnx/model_quantized.onnx','onnx/model.onnx']
        model=next((f for f in candidates if f in files),None)
        if model is None:raise RuntimeError('No published ONNX cross-encoder: '+repo)
        selected=[model,'tokenizer.json','tokenizer_config.json','config.json']
        for file in selected:
            hf_hub_download(repo,file,revision=info.sha,local_dir=folder,token=False)
        write_json(folder/'manifest.json',{'manifest':manifest({}),'repo':repo,'revision':info.sha,'onnx_file':model,
            'files':{f:sha256(folder/f) for f in selected}})
        print('Pinned',name,info.sha,model,flush=True)


class CrossEncoder:
    def __init__(self,name,limit=20):
        self.limit=limit
        import onnxruntime as ort
        from tokenizers import Tokenizer
        folder=ARTIFACTS/'models'/name;info=json.loads((folder/'manifest.json').read_text())
        options=ort.SessionOptions();options.intra_op_num_threads=2
        self.session=ort.InferenceSession(str(folder/info['onnx_file']),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(folder/'tokenizer.json'));self.tokenizer.enable_padding();self.tokenizer.enable_truncation(max_length=256)
    def rank(self,query,ids,agent):
        scores=[]
        for start in range(0,len(ids),8):
            batch=ids[start:start+8];encoded=self.tokenizer.encode_batch([(query,' '.join(agent._product_views[a][:6])) for a in batch])
            arrays={'input_ids':np.array([e.ids for e in encoded],dtype='int64'),'attention_mask':np.array([e.attention_mask for e in encoded],dtype='int64'),'token_type_ids':np.array([e.type_ids for e in encoded],dtype='int64')}
            value=self.session.run(None,{i.name:arrays[i.name] for i in self.session.get_inputs()})[0].reshape(-1)
            scores.extend(zip(value.tolist(),batch))
        return [a for _,a in sorted(scores,key=lambda p:(-p[0],p[1]))]


if __name__=='__main__':download()
