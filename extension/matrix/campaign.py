"""Resumable staged matrix campaign; later stages cannot silently bypass failed gates."""
import json,subprocess,sys,time,ctypes
import psutil
from extension.matrix.common import *

def run(module,*args,python=None):
    folder=HOME/'logs';folder.mkdir(parents=True,exist_ok=True);name=module.rsplit('.',1)[-1]+'-'+'-'.join(map(str,args));path=folder/(name+'.log')
    write_json(HOME/'current.json',{'module':module,'args':args,'status':'running','log':str(path)})
    with path.open('a',encoding='utf-8') as log:result=subprocess.run([python or sys.executable,'-u','-m',module,*map(str,args)],stdout=log,stderr=subprocess.STDOUT)
    write_json(HOME/'current.json',{'module':module,'args':args,'status':'completed' if result.returncode==0 else 'failed','returncode':result.returncode,'log':str(path)})
    if result.returncode:raise RuntimeError('Matrix stage failed: '+name)
    print('Completed',name,flush=True)

def evaluation(schedule,size,variant,level,label,split='dev',seed=SEEDS[0],limit=None,threshold=.65,replay=False):
    name=f'{schedule}-{size}-{variant}-{level}-{split}-s{seed}-{label}'+('-replay' if replay else '')
    if (HOME/f'quality/{name}.json').exists():return
    args=['--schedule',schedule,'--size',size,'--variant',variant,'--level',level,'--label',label,'--split',split,'--seed',seed,'--threshold',threshold]
    if limit:args+=['--limit',limit]
    if replay:args+=['--replay']
    run('extension.matrix.evaluate',*args)

def main():
    if hasattr(ctypes,'windll'):ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        run('extension.matrix.prepare')
        run('extension.matrix.validate')
        for schedule,sizes in SCHEDULES.items():
            for size in sizes:
                run('extension.matrix.growth','--schedule',schedule,'--size',size)
                measured=json.loads((HOME/f'growth/{schedule}-{size}.json').read_text(encoding='utf-8'))
                if measured['added'] and (measured['incremental_seconds'] is None or measured['manifest']['config'].get('ordinal_lookup')!='rowid'):run('extension.matrix.rebenchmark','--schedule',schedule,'--size',size)
                evaluation(schedule,size,'main','constrained','screen-v2',limit=120)
                for variant in ('main','rules'):evaluation(schedule,size,variant,'wording','screen-v2',limit=120)
        run('extension.matrix.regression');run('extension.matrix.correctness');run('extension.matrix.report')
        # An already running, explicitly owned generation process may finish first.
        while any('extension.matrix.bank' in (p.info['cmdline'] or []) for p in psutil.process_iter(['cmdline'])):time.sleep(2)
        bank=HOME/'paraphrases/manifest.json'
        if not bank.exists() or not json.loads(bank.read_text(encoding='utf-8'))['complete']:run('extension.matrix.bank')
        from extension.matrix.bank import seal
        seal()
        run('extension.matrix.audit')
        choices=[]
        for threshold in (.55,.65,.75):
            label='threshold-'+str(threshold)
            evaluation('frozen',50000,'qwen','semantic',label,limit=120,threshold=threshold)
            d=json.loads((HOME/f'quality/frozen-50000-qwen-semantic-dev-s{SEEDS[0]}-{label}.json').read_text(encoding='utf-8'))
            choices.append((d['aggregate']['hit10_by_turn5'],threshold))
        threshold=max(choices)[1];write_json(HOME/'threshold-selection.json',{'development_only':True,'scores':choices,'threshold':threshold})
        for schedule,sizes in SCHEDULES.items():
            for size in sizes:
                for variant in ('main','rules','qwen','semantic'):
                    for level in ('wording','semantic'):evaluation(schedule,size,variant,level,'screen-v2',limit=120,threshold=threshold)
                run('extension.matrix.adjustment','--schedule',schedule,'--size',size)
        from extension.matrix.selection import choose_converter,freeze,paired
        converter=choose_converter('screen-v2');final_checkpoints=(('frozen',50000),('within40',50000),('expanded',60000))
        for schedule,size in final_checkpoints:
            evaluation(schedule,size,'main','constrained','full-dev')
            for variant in ('main',converter,'semantic'):
                for level in ('wording','semantic'):
                    for seed in SEEDS:evaluation(schedule,size,variant,level,'full-dev',seed=seed,threshold=threshold)
        for schedule in ('within40','within30','expanded'):run('extension.matrix.embedding_work','--schedule',schedule,'--gpu',python=str(ROOT/'.venv-embed/Scripts/python.exe'))
        freeze(converter,threshold)
        for schedule,size in final_checkpoints:
            evaluation(schedule,size,'main','constrained','sealed',split='test')
            for variant in ('main',converter,'semantic'):
                for level in ('wording','semantic'):
                    for seed in SEEDS:
                        evaluation(schedule,size,variant,level,'sealed',split='test',seed=seed,threshold=threshold)
                        evaluation(schedule,size,variant,level,'sealed',split='test',seed=seed,threshold=threshold,replay=True)
        paired();run('extension.matrix.report');run('extension.matrix.load_campaign');run('extension.matrix.report')
        write_json(HOME/'complete.json',{'manifest':manifest({}),'status':'Measurements completed; inspect gates, completion does not imply acceptance'})
    finally:
        if hasattr(ctypes,'windll'):ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

if __name__=='__main__':main()
