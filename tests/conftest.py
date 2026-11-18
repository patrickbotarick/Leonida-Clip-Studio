import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Isolamento configurado ANTES de carregar o backend; nunca toca nos projetos reais.
TEST_ROOT = Path(tempfile.mkdtemp(prefix='leonida-tests-'))
os.environ['LEONIDA_DATA_DIR'] = str(TEST_ROOT / 'data')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.main import app
from backend.media import binary, NO_WINDOW
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(app, base_url='http://127.0.0.1', headers={'X-Leonida-Client': '1'}) as test:
        yield test


@pytest.fixture(scope='session')
def media():
    ffmpeg = binary('ffmpeg')
    if not ffmpeg:
        pytest.fail('FFmpeg necessário para os testes integrados de mídia. Execute configurar.ps1 -DownloadFFmpeg.')
    path = TEST_ROOT / 'Gravação sintética com espaços.mp4'
    subprocess.run([ffmpeg, '-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30000/1001',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                    '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000', '-t', '6',
                    '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-metadata:s:a:0', 'title=Microfone',
                    '-metadata:s:a:1', 'title=Jogo', '-movflags', '+faststart', str(path)],
                   check=True, timeout=30, creationflags=NO_WINDOW)
    return path


@pytest.fixture
def project(client, media):
    response = client.post('/api/projects', json={'path': str(media), 'name': 'Teste integrado'})
    assert response.status_code == 201, response.text
    return response.json()
