import shutil
import subprocess
import time
from pathlib import Path

import pytest

from backend import database as db
from backend.media import binary, NO_WINDOW

SRT = b'1\n00:00:00,500 --> 00:00:01,500\nPrimeiro trecho\n\n2\n00:00:02,000 --> 00:00:03,000\nSegundo trecho\n'


def wait_job(client, job_id):
    for _ in range(150):
        result = client.get(f'/api/jobs/{job_id}').json()
        if result['status'] not in ('running', 'queued'):
            return result
        time.sleep(0.05)
    pytest.fail('Tarefa não finalizou no prazo do teste.')


def test_import_metadata_multitrack_and_persistence(client, project, media):
    assert project['path'] == str(media.resolve())
    meta = project['metadata']
    assert 5.9 < meta['duration'] < 6.1
    assert (meta['width'], meta['height']) == (320, 180)
    assert abs(meta['fps'] - 29.97003) < 0.001
    assert len(meta['audio']) == 2
    assert [a['index'] for a in meta['audio']] == [1, 2]
    assert all(a['sample_rate'] == 48000 for a in meta['audio'])
    assert project['selected_audio'] == []
    assert db.get(project['id'])['metadata'] == meta
    assert any(p['id'] == project['id'] for p in client.get('/api/projects').json())


def test_audio_selection_validates_and_persists(client, project):
    url = f'/api/projects/{project["id"]}/audio'
    assert client.put(url, json={'indices': [1, 2, 2]}).json()['selected_audio'] == [1, 2]
    assert db.get(project['id'])['selected_audio'] == [1, 2]
    assert client.put(url, json={'indices': [99]}).status_code == 422


def test_media_ranges_for_seek_without_copy(client, project, media):
    response = client.get(f'/api/projects/{project["id"]}/media', headers={'Range': 'bytes=0-99'})
    assert response.status_code == 206
    assert len(response.content) == 100
    assert response.content == media.read_bytes()[:100]
    assert response.headers['content-range'].startswith('bytes 0-99/')


def test_transcript_import_export_and_invalid_atomicity(client, project):
    url = f'/api/projects/{project["id"]}/transcript'
    response = client.post(url, files={'file': ('Premiere.srt', SRT, 'text/plain')})
    assert response.status_code == 200
    rows = response.json()['transcript']
    assert rows[0]['start'] == 0.5
    assert len(rows) == 2
    for fmt in ('csv', 'json', 'txt', 'srt'):
        exported = client.get(url + '/' + fmt)
        assert exported.status_code == 200
        assert 'attachment' in exported.headers['content-disposition']
        assert 'Primeiro trecho' in exported.text
    assert client.post(url, files={'file': ('invalid.srt', b'1\n00:00:09,000 --> 00:00:10,000\nFora')}).status_code == 422
    assert db.get(project['id'])['transcript'] == rows


def test_transcript_upload_size(client, project):
    response = client.post(f'/api/projects/{project["id"]}/transcript', files={'file': ('large.csv', b'x' * (10 * 1024 * 1024 + 1))})
    assert response.status_code == 413


def test_csv_localized_encoding(client, project):
    text = 'Início;Fim;Texto\n0,5;1,5;Informação'
    response = client.post(f'/api/projects/{project["id"]}/transcript', files={'file': ('premiere.csv', text.encode('cp1252'))})
    assert response.status_code == 200
    assert response.json()['transcript'][0]['text'] == 'Informação'


def test_previews_extract_requested_stream_and_cache(client, project):
    previews = []
    for index in (1, 2):
        response = client.post(f'/api/projects/{project["id"]}/preview', json={'index': index, 'start': 1})
        assert response.status_code == 202
        j = wait_job(client, response.json()['id'])
        assert j['status'] == 'completed', j
        assert j['progress'] == 100
        audio = client.get(f'/api/jobs/{j["id"]}/audio')
        assert audio.status_code == 200 and len(audio.content) > 500
        previews.append(audio.content)
        cached = client.post(f'/api/projects/{project["id"]}/preview', json={'index': index, 'start': 1}).json()
        assert cached['status'] == 'completed'
    assert previews[0] != previews[1]
    assert client.post(f'/api/projects/{project["id"]}/preview', json={'index': 88}).status_code == 422
    assert client.post(f'/api/projects/{project["id"]}/preview', json={'index': 1, 'start': 99}).status_code == 422


def test_real_ffmpeg_cancellation(client, project, monkeypatch):
    from backend import jobs
    original_spawn = jobs.spawn
    def slow_spawn(command, **kwargs):
        command.insert(command.index('-i'), '-re')
        return original_spawn(command, **kwargs)
    monkeypatch.setattr(jobs, 'spawn', slow_spawn)
    result = client.post(f'/api/projects/{project["id"]}/preview', json={'index': 1, 'start': 0.123}).json()
    queue = client.app.state.queue
    for _ in range(100):
        if queue.get(result['id']).get('process'):
            break
        time.sleep(0.01)
    process = queue.get(result['id']).get('process')
    assert process and process.poll() is None
    assert client.delete(f'/api/jobs/{result["id"]}').status_code == 200
    assert wait_job(client, result['id'])['status'] == 'cancelled'
    assert process.poll() is not None
    assert not list(queue.get(result['id'])['target'].parent.glob('*.part.m4a'))


def test_failed_preview_reports_recoverable_error(client, project, monkeypatch):
    from backend import jobs
    monkeypatch.setattr(jobs, 'spawn', lambda *a, **k: (_ for _ in ()).throw(OSError('test failure')))
    response = client.post(f'/api/projects/{project["id"]}/preview', json={'index': 1, 'start': 0.456}).json()
    result = wait_job(client, response['id'])
    assert result['status'] == 'failed'
    assert result['error']


def test_missing_media_and_relink(client, project, media, tmp_path):
    moved = tmp_path / 'Mídia relocalizada.mp4'
    shutil.copy2(media, moved)
    p = db.get(project['id'])
    p['path'] = str(tmp_path / 'ausente.mp4')
    p['transcript'] = [{'id': 1, 'start': 0, 'end': 1, 'text': 'Preservar'}]
    db.save(p)
    assert client.get(f'/api/projects/{p["id"]}').json()['available'] is False
    assert client.get(f'/api/projects/{p["id"]}/media').status_code == 409
    response = client.post(f'/api/projects/{p["id"]}/relink', json={'path': str(moved)})
    assert response.status_code == 200
    assert response.json()['transcript'][0]['text'] == 'Preservar'


def test_changed_source_detected_and_relink_resets(client, project, media, tmp_path):
    changed = tmp_path / 'alterado.mp4'
    shutil.copy2(media, changed)
    p = db.get(project['id']); p['path'] = str(changed); p['transcript'] = [{'text': 'old'}]; db.save(p)
    with changed.open('ab') as file:
        file.write(b'changed')
    assert client.get(f'/api/projects/{p["id"]}/media').status_code == 422
    response = client.post(f'/api/projects/{p["id"]}/relink', json={'path': str(changed)})
    assert response.status_code == 200
    assert response.json()['transcript'] == []


@pytest.mark.parametrize('path,status', [('relative.mp4', 422), ('C:/does-not-exist.mp4', 409), ('C:/unsupported.avi', 422)])
def test_bad_imports(client, path, status):
    assert client.post('/api/projects', json={'path': path}).status_code == status


def test_corrupt_media(client, tmp_path):
    path = tmp_path / 'corrupt.mp4'; path.write_bytes(b'not a movie')
    assert client.post('/api/projects', json={'path': str(path)}).status_code == 422
    assert client.get('/api/projects/no-such-project').status_code == 404


@pytest.mark.parametrize('extension', ['mkv', 'mov', 'webm'])
def test_containers(client, media, tmp_path, extension):
    path = tmp_path / ('fixture.' + extension)
    codecs = ['-c:v', 'libvpx-vp9', '-deadline', 'realtime', '-cpu-used', '8', '-c:a', 'libopus'] if extension == 'webm' else ['-c', 'copy']
    subprocess.run([binary('ffmpeg'), '-v', 'error', '-i', str(media), '-map', '0', *codecs, str(path)], check=True, timeout=30, creationflags=NO_WINDOW)
    response = client.post('/api/projects', json={'path': str(path)})
    assert response.status_code == 201, response.text
    assert len(response.json()['metadata']['audio']) == 2


def test_long_media_over_two_hours(client, tmp_path):
    path = tmp_path / 'long.mp4'
    subprocess.run([binary('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=16x16:r=1', '-t', '7205', '-c:v', 'libx264', '-preset', 'ultrafast', str(path)], check=True, timeout=30, creationflags=NO_WINDOW)
    response = client.post('/api/projects', json={'path': str(path)})
    assert response.status_code == 201
    assert response.json()['metadata']['duration'] > 7200
    assert response.json()['metadata']['audio'] == []


def test_local_security(client):
    assert client.get('/api/health').status_code == 200
    assert client.post('/api/projects', json={'path': 'bad'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/projects', headers={'Host': 'evil.example'}).status_code == 400
    response = client.post('/api/projects', json={'path': 'bad'}, headers={'X-Leonida-Client': ''})
    assert response.status_code == 403
    assert client.get('/api/projects', headers={'Origin': 'http://127.0.0.1'}).status_code == 200
