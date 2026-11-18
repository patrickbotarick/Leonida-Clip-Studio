"""Teste real opt-in: Tiny já instalado, voz sintética Windows, ASR offline e cache."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import database as db
from backend.media import binary, probe, NO_WINDOW
from backend.processing import ProcessingQueue
from backend.transcription import TranscriptionOptions, installed_model


def main():
    if not installed_model('tiny'):
        raise SystemExit('Baixe Tiny explicitamente pelo painel Texto antes de executar este teste. O teste nao baixa modelos.')
    folder = ROOT / '.local/fixtures'
    folder.mkdir(parents=True, exist_ok=True)
    speech = folder / 'fala-sintetica-ptbr.wav'
    movie = folder / 'Fase 1B - fala sintetica na segunda faixa.mp4'
    if not speech.exists():
        subprocess.run(['powershell.exe', '-NoProfile', '-File', str(ROOT / 'scripts/gerar_fala.ps1'), '-OutputPath', str(speech)], check=True, timeout=60, creationflags=NO_WINDOW)
    if not movie.exists():
        subprocess.run([binary('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i', 'color=c=0x171B21:s=640x360:r=25',
                        '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-i', str(speech),
                        '-filter_complex', '[2:a]adelay=2000,apad[voice]', '-t', '18',
                        '-map', '0:v', '-map', '1:a', '-map', '[voice]', '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-c:a', 'aac', '-metadata:s:a:0', 'handler_name=Silencio sintetico',
                        '-metadata:s:a:1', 'handler_name=Fala sintetica pt-BR', '-movflags', '+faststart', str(movie)],
                       check=True, timeout=30, creationflags=NO_WINDOW)
    project = db.create('VALIDAÇÃO ASR · fala sintética pt-BR', movie, probe(movie))
    project['selected_audio'] = [2]
    project = db.save(project)
    queue = ProcessingQueue()
    began = time.perf_counter()
    def wait(job):
        previous = None
        for _ in range(600):
            job = db.get_job(job['id'])
            state = (job['status'], job['stage'], job.get('progress'))
            if state != previous:
                print(state, flush=True); previous = state
            if job['status'] not in ('queued', 'running', 'cancelling'):
                assert job['status'] == 'completed', job
                return job
            time.sleep(.2)
        raise AssertionError('Transcrição excedeu 120 segundos de teste.')
    try:
        options = TranscriptionOptions(language='pt').model_dump()
        job = wait(queue.transcribe(project, options))
        elapsed = time.perf_counter() - began
        result = db.get(project['id'])
        assert result['transcript'], 'ASR não reconheceu a fala sintética.'
        text = ' '.join(r['text'] for r in result['transcript']).casefold()
        assert 'teste' in text or 'computador' in text, text
        assert all(0 <= r['start'] < r['end'] <= 18 for r in result['transcript'])
        # Executa um segundo processo real de ASR na faixa silenciosa: valida escolha de stream.
        silent = db.get(project['id']); silent['selected_audio'] = [1]; silent = db.save(silent)
        wait(queue.transcribe(silent, {**options, 'replace_existing': True}))
        assert db.get(project['id'])['transcript'] == [], 'Faixa silenciosa gerou texto indevido.'
        restored = db.get(project['id']); restored['selected_audio'] = [2]; restored = db.save(restored)
        cache = wait(queue.transcribe(restored, {**options, 'replace_existing': True}))
        assert cache['cache_hit'] is True
        report = dict(status='PASS', engine='Faster Whisper Tiny CPU int8, offline', elapsed_seconds=round(elapsed, 2),
                      duration=18, audio_index=2, segments=db.get(project['id'])['transcript'],
                      silent_track_empty=True, cache_hit=True, project_id=project['id'])
        (ROOT / '.local/transcription-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        queue.close()


if __name__ == '__main__':
    main()
