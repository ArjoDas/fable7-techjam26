"""Resume retained generation after the isolated LightRAG pilot releases the model."""
import time
from extension.common import ARTIFACTS


def main():
    gate=ARTIFACTS/'updates/lightrag-100/watchdog.json'
    deadline=time.monotonic()+1500
    while not gate.exists():
        if time.monotonic()>deadline:raise RuntimeError('LightRAG watchdog did not finish; refusing concurrent generation')
        time.sleep(2)
    from extension.datasets import generate
    for split in ('train','dev','test'):generate(split)
    from extension.finalize_datasets import run
    run()
    from extension.audit import audit
    audit()
    from extension.semantic_audit import main as semantic_audit
    semantic_audit()

if __name__=='__main__':main()
