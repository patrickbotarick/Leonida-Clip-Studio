"""Teste HTTP real sobre mídia sintética. Serviço deve estar aberto em 127.0.0.1:8765."""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
fixture = ROOT / '.local/fixtures/Validacao sintetica - duas faixas.mp4'
subtitle = ROOT / '.local/fixtures/Validacao sintetica.srt'
if not fixture.exists() or not subtitle.exists():
    raise SystemExit('Execute scripts/gerar_fixture.py primeiro.')
with httpx.Client(base_url='http://127.0.0.1:8765', headers={'X-Leonida-Client': '1'}, timeout=30) as client:
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/').status_code == 200
    recent = client.get('/api/projects').json()
    project = next((p for p in recent if p['path'] == str(fixture)), None)
    if not project:
        result = client.post('/api/projects', json={'path': str(fixture), 'name': 'VALIDAÇÃO SINTÉTICA · duas faixas'})
        result.raise_for_status()
        project = result.json()
    base = f'/api/projects/{project["id"]}'
    result = client.get(base + '/media', headers={'Range': 'bytes=0-99'})
    assert result.status_code == 206 and len(result.content) == 100
    result = client.put(base + '/audio', json={'indices': [2]})
    result.raise_for_status()
    assert result.json()['selected_audio'] == [2]
    with subtitle.open('rb') as file:
        result = client.post(base + '/transcript', files={'file': (subtitle.name, file, 'text/plain')})
    result.raise_for_status()
    assert len(result.json()['transcript']) == 3
    result = client.post(base + '/preview', json={'index': 2, 'start': 1})
    result.raise_for_status()
    task = result.json()
    for _ in range(100):
        task = client.get(f'/api/jobs/{task["id"]}').json()
        if task['status'] not in ('queued', 'running'):
            break
        time.sleep(.1)
    assert task['status'] == 'completed', task
    assert client.get(f'/api/jobs/{task["id"]}/audio').status_code == 200
    for fmt in ('srt', 'csv', 'json', 'txt'):
        assert client.get(base + '/transcript/' + fmt).status_code == 200
    saved = client.get(base).json()
    assert saved['selected_audio'] == [2] and len(saved['transcript']) == 3
    report = {'status': 'PASS', 'project_id': project['id'], 'media': 'sintética, 12 s, 2 faixas',
              'http': ['health', 'frontend', 'import', 'range 206', 'audio selection', 'SRT upload via API', 'AAC preview', '4 transcript exports', 'persistence']}
    (ROOT / '.local/smoke-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
