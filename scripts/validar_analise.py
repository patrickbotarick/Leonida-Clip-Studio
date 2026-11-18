"""Fixture e smoke reais do modo local; nenhum provedor externo é chamado."""
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import database as db
from backend.analysis import AnalysisOptions, validate_result
from backend.media import NO_WINDOW, binary, probe
from backend.processing import ProcessingQueue


def generate(folder):
    folder.mkdir(parents=True, exist_ok=True)
    movie = folder / 'Fase 1C - eventos sonoros sinteticos.mp4'
    if not movie.exists():
        files = []
        for index, moments in enumerate(([20, 55], [38, 75])):
            path = folder / f'analise-stream-{index}.wav'
            rate = 8000
            with wave.open(str(path), 'wb') as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
                # Um segundo por vez, sem manter toda a fonte na memória.
                for second in range(90):
                    t = np.arange(rate) / rate
                    amplitude = .8 if second in moments else .006 if index == 0 else 0
                    pcm = (np.sin(2 * np.pi * (440 + index * 220) * t) * amplitude * 32767).astype('<i2')
                    output.writeframes(pcm.tobytes())
            files.append(path)
        subprocess.run([binary('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i', 'color=c=0x171B21:s=640x360:r=5',
                        '-i', str(files[0]), '-i', str(files[1]), '-t', '90', '-map', '0:v', '-map', '1:a', '-map', '2:a',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
                        '-metadata:s:a:0', 'handler_name=Pulsos sinteticos A', '-metadata:s:a:1', 'handler_name=Pulsos sinteticos B',
                        '-movflags', '+faststart', str(movie)], check=True, timeout=30, creationflags=NO_WINDOW)
    transcript = [dict(id=1, start=18, end=23, text='Meu Deus, que susto! Eu não acredito no que eu ouvi.'),
                  dict(id=2, start=35, end=41, text='Eu discordo, não concordo com essa ideia.'),
                  dict(id=3, start=53, end=59, text='Eu errei e deu errado. Precisamos tentar de novo.'),
                  dict(id=4, start=72, end=79, text='Uma dica importante: vou explicar como funciona esta ferramenta.')]
    return movie, transcript


def main():
    movie, transcript = generate(ROOT / '.local/fixtures')
    existing = next((p for p in db.recent() if p['name'] == 'VALIDAÇÃO 1C · evidências sintéticas' and p['path'] == str(movie)), None)
    project = existing or db.create('VALIDAÇÃO 1C · evidências sintéticas', movie, probe(movie))
    project.update(selected_audio=[1, 2], transcript=transcript, transcript_source='Texto sintético de teste, não transcrição real')
    project = db.save(project)
    queue = ProcessingQueue()
    options = AnalysisOptions(content_profile='gameplay', min_duration=8, preferred_duration=18, max_duration=30, margin_before=2, margin_after=2, replace_existing=True).model_dump()
    started = time.perf_counter()
    def wait(job):
        for _ in range(600):
            job = db.get_job(job['id'])
            if job['status'] not in ('queued', 'running', 'cancelling'):
                assert job['status'] == 'completed', job
                return job
            time.sleep(.1)
        raise AssertionError('Análise excedeu 60 segundos de teste.')
    try:
        job = wait(queue.analyze(project, options))
        first_seconds = time.perf_counter() - started
        saved = db.get(project['id'])
        assert len(saved['cuts']) >= 3
        assert {t['stream'] for t in saved['analysis']['audio']['tracks']} == {1, 2}
        assert any(e['stream'] == 1 and 19 <= e['start'] <= 21 for e in saved['analysis']['audio']['events'])
        assert all(c['status'] == 'pending' for c in saved['cuts'])
        validate_result({**saved['analysis'], 'suggestions': saved['cuts']}, saved, options)
        repeated = wait(queue.analyze(saved, options))
        assert repeated['cache_hit'] is True
        report = dict(status='PASS', mode='local/offline', elapsed_seconds=round(first_seconds, 2),
                      project_id=project['id'], suggestions=len(saved['cuts']), tracks=2, cache_hit=True,
                      note='Áudio e texto explicitamente sintéticos. Nenhum vídeo ou acontecimento real é alegado.')
        (ROOT / '.local/analysis-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        queue.close()


if __name__ == '__main__':
    main()
