"""Cria fixture local explícita para a validação visual 1E/Premiere, sem mídia do usuário."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import database as db
from backend.editing import EditCommand, edit_project
from backend.media import NO_WINDOW, binary, probe


def generate(folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'Fase 1E - video sintetico 29.97 duas faixas stereo.mp4'
    if not target.exists():
        subprocess.run([binary('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30000/1001',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000',
                        '-t', '12', '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '60',
                        '-c:a', 'aac', '-ac', '2', '-metadata:s:a:0', 'handler_name=Tom sintetico 440 Hz', '-metadata:s:a:1', 'handler_name=Tom sintetico 880 Hz',
                        '-movflags', '+faststart', str(target)], check=True, timeout=30, creationflags=NO_WINDOW)
    return target


if __name__ == '__main__':
    path = generate(ROOT / '.local' / 'fixtures')
    project = db.create('VALIDAÇÃO 1E · exportações sintéticas', path, probe(path))
    project.update(selected_audio=[1, 2], transcript_source='Legendas sintéticas de teste, não reconhecimento de fala',
                   transcript=[dict(id=1, start=.8, end=4, text='Legenda sintética para testar limites do primeiro corte.'),
                               dict(id=2, start=7, end=10, text='Legenda sintética do segundo corte, depois de uma lacuna.')])
    project = db.save(project)
    ids = []
    for a, b, title in [(1.101, 3.804, 'Primeiro intervalo sintético'), (7.207, 9.810, 'Segundo intervalo sintético'), (10, 11.5, 'Pendente · não deve exportar')]:
        result = edit_project(project['id'], EditCommand(expected_revision=project['revision'], action='create', start=a, end=b, title=title))
        project = result['project']; ids.extend(result['selected_ids'])
    project = edit_project(project['id'], EditCommand(expected_revision=project['revision'], action='status', ids=ids[:2], status='approved'))['project']
    print(json.dumps(dict(project_id=project['id'], media=str(path), approved=2, pending=1, fps=project['metadata']['frame_rate'],
                         note='Imagem, tons e legendas explicitamente sintéticos para QA. Não há transcrição real de fala.'), ensure_ascii=False, indent=2))
