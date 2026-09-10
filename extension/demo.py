"""Runnable source-backed ingestion, conversation, removal and timeout demonstration."""
import argparse
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,manifest
from extension.catalog import Catalog
from extension.agent import Agent
from extension.rerankers import CrossEncoder
from extension.datasets import Shopper


class TimeoutMatcher:
    mode='ranking'
    def match(self,query,cards,timeout):raise TimeoutError('Deliberate demo provider timeout')


def run(label):
    folder=ARTIFACTS/'demo'/label;store=Catalog(folder/'catalog',ROOT/'data/catalog.jsonl')
    records=read_jsonl(ARTIFACTS/'catalog/additions.jsonl');source={r['product']['parent_asin']:r for r in records}
    tasks=sorted(read_jsonl(ARTIFACTS/'datasets/dev.jsonl'),key=lambda r:r['sample_id']);row=next(r for r in tasks if r['target'] in source and r['scenario']=='buying')
    item=source[row['target']];store.register([item]);agent=Agent(catalog=store,reranker=CrossEncoder('tinybert',limit=100));log=[]
    agent.reset('protocol',{});category=next(iter(agent.category_ids))
    text="I'm looking for "+category+", but I'm still exploring."
    response=agent.respond('protocol',text,1,10);log.append({'scene':'unchanged_protocol','request':text,'response':response,'trace':agent.trace['protocol']})
    version=store.apply([{'parent_asin':row['target'],'revision':store.revisions.get(row['target'],0)+1,'operation':'upsert','product':item['product']}])
    log.append({'scene':'ingestion','source_asin':row['target'],'published_version':version,'derived_product_builds':store.metrics[-1]['derived_product_builds']})
    agent.reset('natural',{});shopper=Shopper(row,replay=True);found=False
    for turn in range(1,6):
        text=shopper.message(turn,'other');response=agent.respond('natural',text,turn,10);found|=row['target'] in [r['parent_asin'] for r in response['recommendations']]
        log.append({'scene':'natural_shopping','request':text,'response':response,'trace':agent.trace['natural']})
    for turn,text in [(6,'Actually blue instead of red, please'),(7,'Forget everything. Switch to a different category: wallets.')]:
        response=agent.respond('natural',text,turn,10);log.append({'scene':'correction' if turn==6 else 'category_change','request':text,'response':response,'trace':agent.trace['natural']})
    version=store.apply([{'parent_asin':row['target'],'revision':store.revisions[row['target']]+1,'operation':'delete'}])
    agent.model=TimeoutMatcher();agent.reset('timeout',{});text='Could you help me choose something suited to an unusual purpose?'
    response=agent.respond('timeout',text,1,10);log.append({'scene':'removal_and_timeout','published_version':version,'request':text,'response':response,'trace':agent.trace['timeout']})
    assert row['target'] not in [r['parent_asin'] for r in response['recommendations']]
    write_json(folder/'transcript.json',{'manifest':manifest({'label':label}),'target':row['target'],'natural_target_recovered':found,'scenes':log,
        'note':'The selected target is the first eligible buying example, not cherry-picked for recovery. Failure remains visible.'});store.close();print('Demo retained; natural target recovered:',found,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',default='run-1');a=p.parse_args();run(a.label)
