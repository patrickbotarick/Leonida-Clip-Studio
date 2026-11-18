import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Job Objects são específicos do Windows')
def test_child_is_terminated_when_parent_is_killed(tmp_path):
    script = tmp_path / 'parent.py'
    pid_file = tmp_path / 'child.pid'
    root = Path(__file__).resolve().parents[1]
    script.write_text(f'import sys,time\nsys.path.insert(0, {str(root)!r})\nfrom backend.processes import spawn\np=spawn([sys.executable,"-c","import time; time.sleep(60)"])\nopen({str(pid_file)!r},"w").write(str(p.pid))\ntime.sleep(60)\n')
    parent = subprocess.Popen([sys.executable, str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = None
    try:
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text():
                break
            time.sleep(.05)
        child = int(pid_file.read_text())
        handle = kernel.OpenProcess(0x100000, False, child)
        assert handle
        assert kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT: filho vivo
        parent.kill(); parent.wait(timeout=5)
        assert kernel.WaitForSingleObject(handle, 5000) == 0  # encerramento confirmado
    finally:
        if parent.poll() is None:
            parent.kill(); parent.wait()
        if handle:
            kernel.CloseHandle(handle)
