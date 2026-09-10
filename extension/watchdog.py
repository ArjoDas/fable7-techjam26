"""Enforce wall time and RSS outside a dependency's cancellation handlers."""
import subprocess
import time
import psutil


def bounded_process(command, seconds, memory_bytes=8 * 2**30):
    start = time.monotonic()
    child = subprocess.Popen(command, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    peak = 0
    reason = None
    while child.poll() is None:
        try:
            parent = psutil.Process(child.pid)
            family = [parent, *parent.children(recursive=True)]
            rss = sum(p.memory_info().rss for p in family if p.is_running())
            peak = max(peak, rss)
            if time.monotonic() - start >= seconds or rss > memory_bytes:
                reason = 'wall_time' if time.monotonic() - start >= seconds else 'memory'
                for process in reversed(family):
                    try: process.kill()
                    except psutil.NoSuchProcess: pass
                child.wait(timeout=10)
                break
        except psutil.NoSuchProcess:
            pass
        time.sleep(.1)
    return {'returncode': child.wait(), 'gate': reason,
            'elapsed_seconds': time.monotonic() - start,
            'peak_process_family_rss_mb': peak / 2**20}
