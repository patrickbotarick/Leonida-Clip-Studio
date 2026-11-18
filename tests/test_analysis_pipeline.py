import json
import subprocess
import sys
import time
import re
from pathlib import Path

import pytest

from backend import database as db, processing, audio_analysis
from backend.analysis import AnalysisOptions, analysis_key, finish_suggestions, local_candidates
from backend.media import binary, NO_WINDOW
from scripts.validar_analise import generate


@pytest.fixture(scope='session')
def analysis_media(tmp_path_factory):
    return generate(tmp_path_factory.mktemp('analysis-fixtures'))


@pytest.fixture
def analysis_project(client, analysis_media):
    media, transcript = analysis_media
    result = client.post('/api/projects', json={'path': str(media), 'name': 'Fixture de análise explícita'}).json()
    result.update(selected_audio=[1, 2], transcript=transcript)
    return db.save(result)


def config(**changes):
    return AnalysisOptions(min_duration=8, preferred_duration=18, max_duration=30, **changes).model_dump()


def wait(client, job_id):
    for _ in range(500):
        job = client.get('/api/processing/' + job_id).json()
        if job['status'] not in ('queued', 'running', 'cancelling'):
            return job
        time.sleep(.02)
    pytest.fail('Análise não terminou no prazo.')


def test_real_audio_separate_tracks_levels_silence_and_cache(client, project, monkeypatch):
    results = []
    for index in (1, 2):
        rows = audio_analysis.scan_track(project, index, binary('ffmpeg'), lambda seconds: None)
        stats = audio_analysis.features(rows, index, -45)
        assert -23 < stats['median_active_rms_db'] < -19
        # Referência independente: astats do FFmpeg, após a mesma conversão para mono/8 kHz.
        reference = subprocess.run([binary('ffmpeg'), '-hide_banner', '-i', project['path'], '-map', f'0:{index}',
            '-t', str(project['metadata']['duration']), '-af', 'aresample=8000,aformat=channel_layouts=mono,astats=reset=0', '-f', 'null', '-'],
            capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
        peaks = re.findall(r'Peak level dB: (-?[\d.]+)', reference.stderr)
        assert peaks and abs(stats['max_peak_db'] - float(peaks[-1])) < .15
        assert stats['event_count'] == 0
        assert len(stats['curve']) <= 500
        results.append(rows)
    monkeypatch.setattr(audio_analysis, 'spawn', lambda *a, **k: pytest.fail('Deveria reutilizar cache de medições'))
    assert audio_analysis.scan_track(project, 1, 'unused', lambda seconds: None) == results[0]


def test_real_analysis_pipeline_evidence_intervals_export_and_cache(client, analysis_project, monkeypatch):
    url = f'/api/projects/{analysis_project["id"]}'
    plan = client.get(url + '/analysis/plan').json()
    assert plan['provider_blocks'] >= 1 and plan['transcript_segments'] == 4
    response = client.post(url + '/analyze', json=config())
    assert response.status_code == 202
    result = wait(client, response.json()['id'])
    assert result['status'] == 'completed', result
    saved = client.get(url).json()
    assert len(saved['cuts']) >= 3
    assert len(saved['analysis']['audio']['tracks']) == 2
    for track in saved['analysis']['audio']['tracks']:
        assert track['event_count'] >= 2
        assert -5 < track['max_peak_db'] < 0
    assert saved['analysis']['audio']['tracks'][1]['silence_seconds'] > 70
    assert all(c['status'] == 'pending' for c in saved['cuts'])
    assert all(8 <= c['duration'] <= 30 for c in saved['cuts'])
    assert client.get(url + '/analysis/export').status_code == 200
    assert client.post(url + '/analyze', json=config()).status_code == 422
    monkeypatch.setattr(processing, 'spawn', lambda *a, **k: pytest.fail('Cache deveria evitar worker'))
    repeated = client.post(url + '/analyze', json=config(replace_existing=True)).json()
    assert wait(client, repeated['id'])['cache_hit'] is True
    assert client.put(url + '/audio', json={'indices': [1]}).status_code == 200
    assert client.get(url).json()['cuts'] == []
    assert client.get(url + '/analysis/export').status_code == 409


def test_text_only_analysis_works_without_selected_audio(client, analysis_project):
    url = f'/api/projects/{analysis_project["id"]}'
    client.put(url + '/audio', json={'indices': []})
    response = client.post(url + '/analyze', json=config(analyze_audio=False))
    result = wait(client, response.json()['id'])
    assert result['status'] == 'completed'
    saved = client.get(url).json()
    assert saved['cuts'] and saved['analysis']['audio']['tracks'] == []


def test_reanalysis_preserves_reviewed_and_manual_cuts_and_archives_previous(client, analysis_project):
    from backend.editing import EditCommand, edit_project
    project = analysis_project
    url = f'/api/projects/{project["id"]}'
    result = client.post(url + '/analyze', json=config(analyze_audio=False)).json()
    assert wait(client, result['id'])['status'] == 'completed'
    project = db.get(project['id'])
    first = project['cuts'][0]
    project = edit_project(project['id'], EditCommand(expected_revision=project['revision'], action='status', ids=[first['id']], status='approved'))['project']
    project = edit_project(project['id'], EditCommand(expected_revision=project['revision'], action='create', start=0, end=3, title='Meu corte'))['project']
    retained = [c for c in project['cuts'] if c['id']==first['id'] or c.get('manual')]
    result = client.post(url + '/analyze', json=config(analyze_audio=False, replace_existing=True)).json()
    assert wait(client, result['id'])['status'] == 'completed'
    saved = db.get(project['id'])
    for cut in retained:
        assert cut in saved['cuts']
    for cut in saved['cuts']:
        if cut not in retained:
            assert all(cut['start']>=r['end'] or cut['end']<=r['start'] for r in retained)
            assert cut['status']=='pending'
    archives = client.get(url + '/editor').json()['archives']
    assert archives[0]['compatible']
    assert client.get(url + f'/cuts/archives/{archives[0]["id"]}').json()['cuts']==project['cuts']


def test_real_audio_only_analysis_does_not_invent_dialogue_or_events(client, analysis_project):
    analysis_project['transcript'] = []
    analysis_project = db.save(analysis_project)
    url = f'/api/projects/{analysis_project["id"]}'
    response = client.post(url + '/analyze', json=config(content_profile='generico'))
    result = wait(client, response.json()['id'])
    assert result['status'] == 'completed', result
    cuts = client.get(url).json()['cuts']
    assert cuts
    assert all(c['category'] == 'evento_sonoro' and c['confidence'] <= .3 and c['score'] < 50 for c in cuts)
    assert all(c['transcript_excerpt'] == '' and all(e['kind'] == 'audio' for e in c['evidence']) for c in cuts)


def test_no_sources_invalid_options_and_nonconsensual_provider_never_spawn(client, project, monkeypatch):
    monkeypatch.setattr(processing, 'spawn', lambda *a, **k: pytest.fail('Nenhum envio/processo deveria iniciar'))
    url = f'/api/projects/{project["id"]}/analyze'
    assert client.post(url, json={'analyze_audio': False}).status_code == 422
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={'provider': 'openai', 'api_key': 'segredo'}).status_code == 422
    assert client.post(url, json={'min_duration': 99, 'max_duration': 20}).status_code == 422


def test_api_credentials_never_persist_even_when_worker_fails(client, analysis_project, monkeypatch):
    original = processing.spawn
    key = 'sk-CHAVE-SENTINELA-NUNCA-SALVAR'
    monkeypatch.setenv('OPENAI_API_KEY', key)
    observed = []
    def failing_worker(command, **kwargs):
        work = Path(command[-1]).parent
        observed.append((work / 'request.json').read_text(encoding='utf-8'))
        assert key not in observed[-1]
        assert key not in str(command) and key not in str(kwargs.get('env', {}))
        return original([sys.executable, '-c', 'import sys; sys.stdin.readline(); raise SystemExit(9)'], **kwargs)
    monkeypatch.setattr(processing, 'spawn', failing_worker)
    url = f'/api/projects/{analysis_project["id"]}'
    response = client.post(url + '/analyze', json={**config(provider='openai', model='modelo', consent=True), 'api_key': key})
    assert response.status_code == 202 and key not in response.text
    result = wait(client, response.json()['id'])
    assert result['status'] == 'failed' and key not in json.dumps(result)
    assert key not in client.get('/api/processing').text
    assert key not in client.get(url).text
    assert client.app.state.processing.controls[result['id']]['credential'] == ''


def test_analysis_cancellation_preserves_previous_suggestions_and_locks_inputs(client, analysis_project, monkeypatch):
    previous = finish_suggestions(analysis_project, local_candidates(analysis_project, {'events': []}, config()), config())[:1]
    previous[0]['status'] = 'approved'
    analysis_project.update(cuts=previous, analysis={'marker': 'anterior'})
    db.save(analysis_project)
    original = processing.spawn
    monkeypatch.setattr(processing, 'spawn', lambda command, **kwargs: original([sys.executable, '-u', '-c', 'import sys,time; sys.stdin.readline(); print(\'{"stage":"analyzing_audio","progress":10}\',flush=True); time.sleep(60)'], **kwargs))
    response = client.post(f'/api/projects/{analysis_project["id"]}/analyze', json=config(content_profile='react', replace_existing=True))
    job_id = response.json()['id']
    for _ in range(100):
        if db.get_job(job_id)['stage'] == 'analyzing_audio':
            break
        time.sleep(.01)
    assert client.put(f'/api/projects/{analysis_project["id"]}/audio', json={'indices': [1]}).status_code == 422
    assert client.delete('/api/processing/' + job_id).status_code == 200
    assert wait(client, job_id)['status'] == 'cancelled'
    assert db.get(analysis_project['id'])['cuts'] == previous


def test_external_transcript_import_invalidates_old_analysis(client, analysis_project):
    analysis_project.update(analysis={'obsolete': True}, cuts=[{'obsolete': True}]); db.save(analysis_project)
    url = f'/api/projects/{analysis_project["id"]}'
    response = client.post(url + '/transcript', files={'file': ('external.srt', b'1\n00:00:01,000 --> 00:00:02,000\nNovo texto')})
    assert response.status_code == 200
    assert response.json()['analysis'] is None and response.json()['cuts'] == []
