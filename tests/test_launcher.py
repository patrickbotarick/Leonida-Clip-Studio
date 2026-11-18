import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Launcher piloto para Windows')
def test_real_launcher_http_exclusive_instance_and_graceful_stop(tmp_path):
    root = Path(__file__).resolve().parents[1]
    if not (root / 'frontend/dist/index.html').exists():
        pytest.skip('Compile o frontend para validar o launcher real.')
    env = {**os.environ, 'LEONIDA_DATA_DIR': str(tmp_path), 'PYTHONUTF8': '1'}
    launcher = subprocess.Popen([sys.executable, 'scripts/launch.py', '--port', '0', '--no-browser'], cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        state = None
        for _ in range(150):
            try:
                state = json.loads((tmp_path / 'run.json').read_text(encoding='utf-8'))
                result = httpx.get(state['url'] + '/api/health', timeout=.2)
                if result.status_code == 200:
                    break
            except (OSError, ValueError, httpx.HTTPError):
                pass
            time.sleep(.05)
        else:
            pytest.fail('Launcher não disponibilizou health no prazo.')
        assert httpx.get(state['url'], timeout=2).status_code == 200
        second = subprocess.run([sys.executable, 'scripts/launch.py', '--port', '0', '--no-browser'], cwd=root, env=env,
                                capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        assert second.returncode == 1
        assert json.loads((tmp_path / 'run.json').read_text(encoding='utf-8'))['token'] == state['token']
        stopped = subprocess.run(['powershell.exe', '-NoProfile', '-File', 'scripts/encerrar.ps1'], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        assert stopped.returncode == 0, stopped.stderr
        launcher.wait(timeout=5)
        assert launcher.returncode == 0
        assert not (tmp_path / 'run.json').exists()
        assert not list(tmp_path.glob('stop-*'))
        logs = launcher.stdout.read()
        assert 'Application shutdown complete' in logs
        assert 'Traceback' not in logs
        with pytest.raises(httpx.HTTPError):
            httpx.get(state['url'] + '/api/health', timeout=.5)
    finally:
        if launcher.poll() is None:
            launcher.kill(); launcher.wait()
        launcher.stdout.close()
