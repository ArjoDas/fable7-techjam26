"""Run the official public simulator against actual FastAPI session endpoints."""
import argparse
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient
from api.main import create_app
from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl


class HTTPAgent:
    def __init__(self, client):
        self.client, self.count, self.model_calls = client, 0, 0

    def reset(self, sid, profile):
        response = self.client.post('/v1/sessions', json={'mode': 'demo', 'include_trace': True, 'semantic': True, 'user_profile': profile})
        response.raise_for_status()
        self.sid = response.json()['session_id']
        self.count += 1
        if self.count % 20 == 0:
            print('HTTP public', self.count, flush=True)

    def respond(self, sid, message, turn, top_k):
        response = self.client.post(f'/v1/sessions/{self.sid}/turns', json={'message': message})
        response.raise_for_status()
        value = response.json()
        assert value['trace']['extension']['route'] == 'protocol'
        self.model_calls += value['trace']['extension']['model_calls']
        return {**value['assistant'], 'recommendations': value['recommendations']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', default='data/catalog.jsonl')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    path = Path(args.output)
    if path.exists():
        raise RuntimeError('Result already retained')
    ids, categories, products = catalog_index(args.catalog)
    with TestClient(create_app(catalog_path=Path(args.catalog))) as client:
        deadline = time.monotonic() + 300
        while client.get('/readyz').status_code != 200:
            if time.monotonic() >= deadline:
                raise RuntimeError('Frontend readiness timeout')
            time.sleep(.1)
        agent = HTTPAgent(client)
        result = evaluate(agent, load_jsonl('data/public_set.jsonl'), ids, categories, products)
        result['model_calls'] = agent.model_calls
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2))
        print(json.dumps({k:v for k,v in result.items() if k != 'sessions'}, indent=2))
        assert result['hit_rate_at_10'] == result['mrr'] == 1.0
        assert result['mttc'] == 2.1 and result['recommended_technical_score'] == .978
        assert agent.model_calls == 0


if __name__ == '__main__':
    main()
