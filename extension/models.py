"""Local model interfaces. A missing dependency never masquerades as a model result."""
import json
import urllib.request
from extension.common import ARTIFACTS, MODEL_CACHE

class LocalLLM:
    def __init__(self, url='http://127.0.0.1:8091/v1/chat/completions', timeout=30):
        self.url, self.timeout = url, timeout

    def complete(self, prompt, max_tokens=200, seed=20260910, schema=None):
        payload = {'model': 'qwen3-4b', 'messages': [{'role': 'user', 'content': prompt + '\n/no_think'}], 'temperature': 0.3, 'seed': seed, 'max_tokens': max_tokens, 'chat_template_kwargs': {'enable_thinking': False}}
        if schema is not None:payload['response_format']={'type':'json_schema','json_schema':{'name':'output','strict':True,'schema':schema}}
        request = urllib.request.Request(self.url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.load(response)
        return result['choices'][0]['message']['content'], result.get('usage', {})

class Embeddings:
    def __init__(self, gpu=False, fp32=False):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        root = MODEL_CACHE / 'minilm'
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        if gpu:
            ort.preload_dlls(directory='')
        model_path = root / ('onnx/model.onnx' if gpu or fp32 else 'onnx/model_quint8_avx2.onnx')
        providers = [('CUDAExecutionProvider', {'gpu_mem_limit': 512 * 2**20, 'arena_extend_strategy': 'kSameAsRequested', 'use_tf32': 0}), 'CPUExecutionProvider'] if gpu else ['CPUExecutionProvider']
        self.session = ort.InferenceSession(str(model_path), options, providers=providers)
        if gpu and self.session.get_providers()[0] != 'CUDAExecutionProvider':
            raise RuntimeError('GPU preprocessing requested but CUDA is unavailable')
        self.batch_size = 8 if gpu else 32
        self.tokenizer = Tokenizer.from_file(str(root / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()

    def encode(self, texts):
        import numpy as np
        result = []
        for offset in range(0, len(texts), self.batch_size):
            tokens = self.tokenizer.encode_batch(texts[offset:offset + self.batch_size])
            values = {'input_ids': np.array([x.ids for x in tokens], dtype=np.int64), 'attention_mask': np.array([x.attention_mask for x in tokens], dtype=np.int64), 'token_type_ids': np.array([x.type_ids for x in tokens], dtype=np.int64)}
            hidden = self.session.run(None, {x.name: values[x.name] for x in self.session.get_inputs()})[0]
            mask = values['attention_mask'][..., None]
            pooled = (hidden * mask).sum(1) / mask.sum(1).clip(1)
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(1e-9)
            result.append(pooled.astype('float32'))
        return np.concatenate(result)
