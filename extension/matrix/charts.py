import os,json
from extension.matrix.common import *
os.environ['MPLCONFIGDIR']=str(HOME/'plot-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    folder=ROOT/'docs/matrix-figures';folder.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(14,4),sharey=True)
    for ax,schedule in zip(axes,('frozen','within40','expanded')):
        groups={}
        for path in (HOME/'quality').glob('*.json'):
            d=json.loads(path.read_text(encoding='utf-8'));c=d['manifest']['config']
            if c['schedule']==schedule and c['label']=='screen-v2' and c['seed']==SEEDS[0]:groups.setdefault(c['variant']+' / '+c['level'],[]).append((c['size'],d['aggregate']['hit10_by_turn5']*100))
        for label,points in sorted(groups.items()):
            points.sort();ax.plot([p[0] for p in points],[p[1] for p in points],marker='o',label=label)
        ax.axhline(90,color='gray',linestyle='--',linewidth=1);ax.set_title(schedule);ax.set_xlabel('Active products');ax.set_ylim(0,105);ax.grid(alpha=.2)
        if groups:ax.legend(fontsize=6)
    axes[0].set_ylabel('Recovery within five turns (%)');fig.suptitle('Exploratory development matrix; incomplete cells stay empty');fig.tight_layout();fig.savefig(folder/'quality-growth.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4))
    for schedule in ('within40','within30','expanded'):
        values=[]
        for path in (HOME/'growth').glob(schedule+'-*.json'):
            d=json.loads(path.read_text(encoding='utf-8'))
            size=d['manifest']['config']['size'];optimized=HOME/f'optimized-growth/{schedule}-{size}/result.json'
            if optimized.exists():d=json.loads(optimized.read_text(encoding='utf-8'))
            if d['added'] and d['incremental_seconds'] is not None:values.append((size,d['incremental_seconds'],d['parity']['rebuild_seconds']))
        values.sort()
        if values:
            ax.plot([v[0] for v in values],[v[1] for v in values],marker='o',label=schedule+' incremental')
            ax.plot([v[0] for v in values],[v[2] for v in values],linestyle='--',label=schedule+' rebuild')
    ax.set_xlabel('Active products');ax.set_ylabel('Seconds');ax.set_title('Measured lexical catalog growth costs');ax.grid(alpha=.2)
    if ax.lines:ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(folder/'update-growth.png',dpi=150);plt.close(fig)

if __name__=='__main__':main()
