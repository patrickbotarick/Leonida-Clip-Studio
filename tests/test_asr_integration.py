"""Inferência REAL opt-in. Não baixa modelos nem substitui o motor por mocks."""
import os
import subprocess
import time

import pytest

from backend import database as db, transcription
from backend.config import ROOT
from backend.media import binary, probe, NO_WINDOW

pytestmark = pytest.mark.skipif(os.environ.get('LEONIDA_TEST_ASR') != '1', reason='Defina LEONIDA_TEST_ASR=1 após instalar Tiny e gerar a fixture falada local.')


@pytest.fixture
def real_project(monkeypatch):
    monkeypatch.setattr(transcription, 'MODEL_ROOT', ROOT / '.local/models')
    if not transcription.installed_model('tiny'):
        pytest.fail('Tiny não instalado. Baixe-o explicitamente antes deste teste opt-in.')
    movie = ROOT / '.local/fixtures/Fase 1B - fala sintetica na segunda faixa.mp4'
    if not movie.exists():
        pytest.fail('Execute scripts/validar_transcricao.py para gerar a fixture de fala.')
    project = db.create('ASR real isolado', movie, probe(movie))
    project['selected_audio'] = [2]
    return db.save(project)


def wait(client, job_id):
    for _ in range(600):
        result = client.get('/api/processing/' + job_id).json()
        if result['status'] not in transcription.ACTIVE:
            return result
        time.sleep(.1)
    pytest.fail('ASR real não concluiu no prazo do teste.')


def test_real_cpu_speech_auto_language_silence_cache_and_exports(client, real_project):
    url = f'/api/projects/{real_project["id"]}'
    response = client.post(url + '/transcribe', json={'language': 'auto'})
    assert response.status_code == 202
    result = wait(client, response.json()['id'])
    assert result['status'] == 'completed', result
    saved = client.get(url).json()
    assert saved['transcript']
    assert saved['transcript_info']['languages'][0]['language'] == 'pt'
    assert 'computador' in ' '.join(s['text'].lower() for s in saved['transcript'])
    for fmt in ('srt', 'csv', 'json', 'txt'):
        assert client.get(url + '/transcript/' + fmt).status_code == 200
    assert client.put(url + '/audio', json={'indices': [1]}).status_code == 200
    silent = client.post(url + '/transcribe', json={'language': 'pt', 'replace_existing': True}).json()
    assert wait(client, silent['id'])['status'] == 'completed'
    assert client.get(url).json()['transcript'] == []
    assert client.put(url + '/audio', json={'indices': [2]}).status_code == 200
    cached = client.post(url + '/transcribe', json={'language': 'auto', 'replace_existing': True}).json()
    assert wait(client, cached['id'])['cache_hit'] is True
    # Mistura real de duas faixas: silêncio + fala, com normalização.
    assert client.put(url + '/audio', json={'indices': [1, 2]}).status_code == 200
    mixed = client.post(url + '/transcribe', json={'language': 'pt', 'replace_existing': True}).json()
    assert wait(client, mixed['id'])['status'] == 'completed'
    assert 'computador' in ' '.join(s['text'].lower() for s in client.get(url).json()['transcript'])


def test_cancel_real_whisper_during_loading_preserves_previous_text(client, real_project):
    url = f'/api/projects/{real_project["id"]}'
    real_project['transcript'] = [{'id': 1, 'start': 0, 'end': 1, 'text': 'Texto anterior'}]
    db.save(real_project)
    result = client.post(url + '/transcribe', json={'replace_existing': True, 'threads': 1}).json()
    for _ in range(200):
        status = client.get('/api/processing/' + result['id']).json()
        if status['stage'] in ('loading_model', 'extracting', 'transcribing'):
            break
        time.sleep(.01)
    assert status['status'] == 'running'
    process = client.app.state.processing.controls[result['id']]['process']
    assert client.delete('/api/processing/' + result['id']).status_code == 200
    assert wait(client, result['id'])['status'] == 'cancelled'
    assert process.poll() is not None
    assert client.get(url).json()['transcript'][0]['text'] == 'Texto anterior'


def test_real_transcription_across_five_minute_boundary(client, real_project, tmp_path):
    # Vídeo de 320 s: a fala real sintética começa aos 298 s e atravessa a fronteira.
    movie = tmp_path / 'long-boundary.mp4'
    speech = ROOT / '.local/fixtures/fala-sintetica-ptbr.wav'
    subprocess.run([binary('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=16x16:r=1',
                    '-i', str(speech), '-filter_complex', '[1:a]adelay=298000,apad[voice]', '-t', '320',
                    '-map', '0:v', '-map', '[voice]', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(movie)],
                   check=True, timeout=30, creationflags=NO_WINDOW)
    project = db.create('Fronteira 300 s real', movie, probe(movie)); project['selected_audio'] = [1]; project = db.save(project)
    response = client.post(f'/api/projects/{project["id"]}/transcribe', json={'language': 'pt'})
    result = wait(client, response.json()['id'])
    assert result['status'] == 'completed', result
    assert result['blocks'] == 2
    rows = db.get(project['id'])['transcript']
    assert rows and all(295 <= s['start'] < s['end'] <= 320 for s in rows)
    assert any(s['end'] > 300 for s in rows)
    assert 'computador' in ' '.join(s['text'].lower() for s in rows)
