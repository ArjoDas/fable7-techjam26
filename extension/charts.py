"""Static measured-quality figures; small-sample latency is explicitly labeled."""
import json
import os
from pathlib import Path
os.environ['MPLCONFIGDIR']=str(Path(__file__).resolve().parents[1]/'data/releases/extension-v1/plot-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from extension.common import ARTIFACTS,ROOT


def main():
    files=[*sorted((ARTIFACTS/'quality').glob('*semantic-screen.json')),*sorted((ARTIFACTS/'quality').glob('*state-scope-screen.json'))]
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in files]
    if not rows:return
    names=[r['manifest']['config']['variant'].replace('rag-','').replace('tinybert-','').replace('-','\n') for r in rows];x=np.arange(len(rows));fig,axes=plt.subplots(1,2,figsize=(14,5.5))
    axes[0].bar(x-.18,[r['aggregate']['hit_rate_at_10']*100 for r in rows],.36,label='HitRate@10',color='#2166ac')
    axes[0].bar(x+.18,[r['aggregate']['recall100_any_turn']*100 for r in rows],.36,label='Recall@100',color='#67a9cf')
    axes[0].axhline(90,color='#b2182b',ls='--',lw=1,label='90% recovery gate');axes[0].set_ylim(0,105);axes[0].set_ylabel('Percent of development tasks');axes[0].set_title('Matched 120-task exploratory comparison');axes[0].legend(fontsize=8,loc='lower right')
    axes[1].bar(x-.18,[r['aggregate']['response_latency']['p50_ms'] for r in rows],.36,label='p50',color='#2166ac')
    axes[1].bar(x+.18,[r['aggregate']['response_latency']['p99_ms'] for r in rows],.36,label='Observed p99',color='#ef8a62')
    axes[1].axhline(2000,color='#b2182b',ls='--',lw=1);axes[1].set_ylabel('Offline response milliseconds');axes[1].set_title('Exploratory timing; background load varied');axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xticks(x,names,fontsize=8);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Dynamic-catalog semantic retrieval experiments',fontsize=15);fig.tight_layout();folder=ROOT/'docs/extension-figures';folder.mkdir(parents=True,exist_ok=True);fig.savefig(folder/'semantic-screen.png',dpi=160);plt.close(fig)

if __name__=='__main__':main()
