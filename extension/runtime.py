"""Owned local model runtime with temporary idle-sleep prevention."""
import ctypes
import subprocess
import time
from extension.common import ARTIFACTS, MODEL_CACHE, manifest,write_json


def main():
    guard=ctypes.windll.kernel32.SetThreadExecutionState
    if not guard(0x80000001):raise RuntimeError('Idle-sleep guard unavailable')
    command=[str(MODEL_CACHE/'llama/llama-server.exe'),'-m',str(MODEL_CACHE/'Qwen3-4B-Q4_K_M.gguf'),
             '--host','127.0.0.1','--port','8091','-ngl','99','-c','16384','--parallel','4','--threads','4','--jinja','--cache-ram','512']
    folder=ARTIFACTS/'runtime';folder.mkdir(parents=True,exist_ok=True)
    with (folder/'model.log').open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        write_json(folder/'model.json',{'manifest':manifest({}),'pid':process.pid,'command':command})
        try:
            while process.poll() is None:time.sleep(1)
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=20)
            guard(0x80000000)


if __name__=='__main__':main()
