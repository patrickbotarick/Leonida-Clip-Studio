"""Fila de prévias limitada a um processo FFmpeg; cancelamento cooperativo."""
import hashlib
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from .config import DATA
from .media import NO_WINDOW, binary, check_unchanged
from .processes import spawn


class PreviewQueue:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='audio-preview')
        self.jobs = {}
        self.lock = threading.Lock()

    def submit(self, project, index, start):
        path = check_unchanged(project)
        if index not in [a['index'] for a in project['metadata']['audio']]:
            raise ValueError('Faixa de áudio inexistente.')
        if not 0 <= start < project['metadata']['duration']:
            raise ValueError('Posição fora da mídia.')
        if not binary('ffmpeg'):
            raise ValueError('FFmpeg não encontrado.')
        duration = min(30, project['metadata']['duration'] - start)
        key = hashlib.sha256(f'{path}:{project["metadata"]["mtime_ns"]}:{project["metadata"]["size"]}:{index}:{start:.3f}'.encode()).hexdigest()
        folder = DATA / 'previews'
        folder.mkdir(exist_ok=True)
        target = folder / f'{key}.m4a'
        with self.lock:
            pending = [j for j in self.jobs.values() if j['status'] in ('queued', 'running')]
            if len(pending) >= 4:
                raise ValueError('A fila está cheia. Aguarde ou cancele uma prévia.')
            # Histórico em memória é limitado; arquivos são reutilizados por chave.
            if len(self.jobs) >= 100:
                for old in list(self.jobs):
                    if self.jobs[old]['status'] not in ('queued', 'running'):
                        del self.jobs[old]
                        break
            job = dict(id=uuid4().hex, project_id=project['id'], status='queued', progress=0,
                       start=start, duration=duration, index=index, target=target, cancel=threading.Event())
            self.jobs[job['id']] = job
        if target.is_file():
            job.update(status='completed', progress=100)
        else:
            self.pool.submit(self.run, job, path)
        return self.public(job)

    def run(self, job, path):
        tmp = job['target'].with_name(job['id'] + '.part.m4a')
        process = None
        try:
            if job['cancel'].is_set():
                job['status'] = 'cancelled'
                return
            job['status'] = 'running'
            command = [binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                       '-ss', str(job['start']), '-i', str(path), '-t', str(job['duration']),
                       '-map', f'0:{job["index"]}', '-vn', '-c:a', 'aac', '-b:a', '128k',
                       '-threads', '2', '-progress', 'pipe:1', str(tmp)]
            process = spawn(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, creationflags=NO_WINDOW)
            job['process'] = process
            for line in process.stdout:
                if job['cancel'].is_set():
                    process.terminate()
                    break
                if line.startswith('out_time_us='):
                    try:
                        job['progress'] = min(99, max(0, int(line.split('=')[1]) / 10000 / job['duration']))
                    except ValueError:
                        pass
            code = process.wait(timeout=15)
            if job['cancel'].is_set():
                job['status'] = 'cancelled'
            elif code:
                job.update(status='failed', error='Não foi possível gerar a prévia de áudio. Verifique a integridade da mídia.')
            else:
                os.replace(tmp, job['target'])
                job.update(status='completed', progress=100)
        except Exception:
            job.update(status='failed', error='Falha ao processar prévia de áudio.')
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
            tmp.unlink(missing_ok=True)
            job.pop('process', None)

    @staticmethod
    def public(job):
        return {k: v for k, v in job.items() if k not in ('cancel', 'process', 'target')}

    def get(self, job_id):
        if job_id not in self.jobs:
            raise KeyError('Tarefa não encontrada. Pode ter sido encerrada ou expirada.')
        return self.jobs[job_id]

    def cancel(self, job_id):
        job = self.get(job_id)
        if job['status'] in ('queued', 'running'):
            job['cancel'].set()
            process = job.get('process')
            if process and process.poll() is None:
                process.terminate()
        return self.public(job)

    def close(self):
        for job in list(self.jobs.values()):
            self.cancel(job['id'])
        self.pool.shutdown(wait=True, cancel_futures=True)
