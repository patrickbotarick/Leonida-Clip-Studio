import copy
import json
import subprocess
import sys
import time

import pytest

from backend import database as db
from backend import processing, transcription
from backend.transcription import TranscriptionOptions, global_segments, normalize_segments, windows


def wait(client, job_id):
    for _ in range(200):
        result = client.get('/api/processing/' + job_id).json()
        if result['status'] not in transcription.ACTIVE:
            return result
        time.sleep(.025)
    pytest.fail('Tarefa não terminou no prazo.')


@pytest.fixture
def configured(project):
    project['selected_audio'] = [2]
    return db.save(project)


@pytest.fixture
def fake_local_model(monkeypatch):
    # Só representa o catálogo em testes de contrato/cache; não simula inferência real.
    folder = transcription.model_directory('tiny')
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ('config.json', 'model.bin', 'tokenizer.json'):
        (folder / name).write_bytes(b'fixture')
        files[name] = {'size': 7, 'sha256': 'test-only'}
    transcription.write_json(folder / 'leonida-model.json', {'name': 'tiny', 'revision': 'test-revision', 'files': files})
    yield folder


def test_capabilities_no_network_and_explicit_model_consent(client):
    result = client.get('/api/transcription/capabilities')
    assert result.status_code == 200
    assert {m['name'] for m in result.json()['models']} == {'tiny', 'base', 'small'}
    assert client.post('/api/transcription/models', json={'model': 'base'}).status_code == 422
    assert client.post('/api/transcription/models', json={'model': '../../outside', 'consent': True}).status_code == 422


def test_selection_and_replacement_are_explicit(client, project, fake_local_model):
    url = f'/api/projects/{project["id"]}/transcribe'
    assert client.post(url, json={}).status_code == 422
    project['selected_audio'] = [2]
    project['transcript'] = [{'id': 1, 'start': 0, 'end': 1, 'text': 'Preservar'}]
    db.save(project)
    assert client.post(url, json={}).status_code == 422
    assert db.get(project['id'])['transcript'][0]['text'] == 'Preservar'


def test_cuda_requires_runtime_libraries(client, configured, fake_local_model, monkeypatch):
    monkeypatch.setattr(processing, 'capabilities', lambda: {'cuda_libraries_available': False})
    monkeypatch.setattr(processing, 'spawn', lambda *a, **kw: pytest.fail('GPU sem bibliotecas não deve iniciar worker'))
    result = client.post(f'/api/projects/{configured["id"]}/transcribe', json={'device': 'cuda'})
    assert result.status_code == 422
    assert 'Use CPU' in result.json()['detail']


@pytest.mark.parametrize('options', [{'threads': 0}, {'threads': 5}, {'language': 'xx'}, {'device': 'auto'}, {'model': 'large'}, {'end': 0}, {'start': -1}, {'start': 3, 'end': 2}, {'start': 100}, {'end': 100}])
def test_invalid_transcription_options(client, configured, fake_local_model, options):
    assert client.post(f'/api/projects/{configured["id"]}/transcribe', json=options).status_code == 422


def test_missing_model_never_starts_implicit_download(client, configured, monkeypatch):
    monkeypatch.setattr(processing, 'installed_model', lambda name: None)
    monkeypatch.setattr(processing, 'spawn', lambda *a, **kw: pytest.fail('Não deveria criar processo/download'))
    response = client.post(f'/api/projects/{configured["id"]}/transcribe', json={})
    assert response.status_code == 422 and 'Modelo ausente' in response.json()['detail']


def test_cache_hit_applies_without_worker_and_preserves_global_times(client, configured, fake_local_model, monkeypatch):
    options = TranscriptionOptions().model_dump()
    key = transcription.cache_key(configured, options, transcription.installed_model('tiny'))
    transcription.write_json(transcription.ASR_ROOT / 'cache' / f'{key}.json', dict(segments=[{'start': 2.125, 'end': 3.5, 'text': 'Texto em cache'}], options=options, languages=[]))
    monkeypatch.setattr(processing, 'spawn', lambda *a, **kw: pytest.fail('Cache deveria evitar inferência'))
    response = client.post(f'/api/projects/{configured["id"]}/transcribe', json={})
    assert response.status_code == 202
    job = wait(client, response.json()['id'])
    assert job['status'] == 'completed' and job['cache_hit'] is True
    saved = db.get(configured['id'])
    assert saved['transcript'][0]['start'] == 2.125
    assert saved['settings']['transcription']['device'] == 'cpu'
    assert client.get(f'/api/projects/{configured["id"]}/transcript/srt').status_code == 200


def test_cache_key_includes_audio_language_profile_and_model_revision(configured, fake_local_model):
    options = TranscriptionOptions().model_dump()
    manifest = transcription.installed_model('tiny')
    key = transcription.cache_key(configured, options, manifest)
    assert transcription.cache_key(configured, {**options, 'replace_existing': True}, manifest) == key
    assert transcription.cache_key(configured, {**options, 'language': 'en'}, manifest) != key
    assert transcription.cache_key(configured, {**options, 'profile': 'alta_qualidade'}, manifest) != key
    assert transcription.cache_key({**configured, 'selected_audio': [1]}, options, manifest) != key
    assert transcription.cache_key(configured, options, {**manifest, 'revision': 'changed'}) != key


def test_interrupted_job_recovery_preserves_project_and_cleans_own_work(configured):
    job_id = 'a' * 32
    work = transcription.ASR_ROOT / 'work' / job_id
    work.mkdir(parents=True, exist_ok=True)
    (work / 'partial.wav').write_bytes(b'partial')
    db.save_job({'id': job_id, 'kind': 'transcription', 'project_id': configured['id'], 'status': 'running'})
    queue = processing.ProcessingQueue()
    try:
        assert db.get_job(job_id)['status'] == 'interrupted'
        assert not work.exists()
        assert db.get(configured['id'])['selected_audio'] == [2]
    finally:
        queue.close()


def test_stale_save_cannot_overwrite_current_project(configured):
    stale = copy.deepcopy(configured)
    current = db.get(configured['id']); current['selected_audio'] = [1]; db.save(current)
    stale['selected_audio'] = [2]
    with pytest.raises(ValueError, match='alterado'):
        db.save(stale)
    assert db.get(configured['id'])['selected_audio'] == [1]


def test_result_cannot_overwrite_a_project_modified_during_job(client, configured, fake_local_model):
    current = db.get(configured['id']); current['selected_audio'] = [1]; db.save(current)
    job = {'options': TranscriptionOptions().model_dump()}
    with pytest.raises(ValueError, match='mudou'):
        client.app.state.processing._apply(job, configured, {'segments': [{'start': 1, 'end': 2, 'text': 'Descartar'}]})
    assert db.get(configured['id'])['transcript'] == []


def test_model_download_failure_is_recoverable(client, monkeypatch):
    original_spawn = processing.spawn
    monkeypatch.setattr(processing, 'spawn', lambda command, **kwargs: original_spawn([sys.executable, '-c', 'raise SystemExit(7)'], **kwargs))
    response = client.post('/api/transcription/models', json={'model': 'base', 'consent': True})
    assert response.status_code == 202
    result = wait(client, response.json()['id'])
    assert result['status'] == 'failed' and 'download' in result['error']
    assert not (transcription.ASR_ROOT / 'work' / result['id']).exists()
    assert not transcription.model_directory('base').exists()


def test_loading_process_can_be_cancelled_and_job_persists(client, configured, fake_local_model, monkeypatch):
    original_spawn = processing.spawn
    monkeypatch.setattr(processing, 'spawn', lambda command, **kwargs: original_spawn([sys.executable, '-u', '-c', 'import time; print(\'{"stage":"loading_model","progress":0}\',flush=True); time.sleep(60)'], **kwargs))
    response = client.post(f'/api/projects/{configured["id"]}/transcribe', json={'language': 'en', 'start': .321})
    job_id = response.json()['id']
    for _ in range(150):
        if db.get_job(job_id)['stage'] == 'loading_model':
            break
        time.sleep(.01)
    process = client.app.state.processing.controls[job_id]['process']
    assert process and process.poll() is None
    assert client.put(f'/api/projects/{configured["id"]}/audio', json={'indices': [1]}).status_code == 422
    assert db.get(configured['id'])['selected_audio'] == [2]
    # Segunda tarefa para o mesmo projeto é rejeitada.
    assert client.post(f'/api/projects/{configured["id"]}/transcribe', json={}).status_code == 422
    assert client.delete('/api/processing/' + job_id).status_code == 200
    assert wait(client, job_id)['status'] == 'cancelled'
    assert process.poll() is not None
    assert db.get(configured['id'])['transcript'] == []
    assert any(j['id'] == job_id for j in client.get(f'/api/processing?project_id={configured["id"]}').json())


def test_block_context_and_global_ownership():
    blocks = list(windows(0, 7205))
    assert len(blocks) == 25
    assert blocks[1] == (300, 600, 295, 605)
    assert blocks[-1][1] == 7205
    segment = {'start': 7, 'end': 11, 'text': 'Frase inteira'}
    output = global_segments([segment], 300, 600, 295, 7205)
    assert output == [{'start': 302, 'end': 306, 'text': 'Frase inteira'}]
    assert global_segments([segment], 0, 300, 295, 7205) == []


def test_normalization_rejects_bad_times_and_deduplicates():
    rows = [{'start': 300, 'end': 305, 'text': 'Fala'}, {'start': 301, 'end': 306, 'text': 'Fala'}, {'start': 310, 'end': 315, 'text': 'Fala'}]
    assert len(normalize_segments(rows, 400)) == 2
    with pytest.raises(ValueError):
        normalize_segments([{'start': 1, 'end': float('inf'), 'text': 'Inválido'}], 400)
    with pytest.raises(ValueError):
        transcription.remove_work(transcription.ASR_ROOT.parent)
