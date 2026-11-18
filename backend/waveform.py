"""Envelope PCM min/max em disco, com níveis para consultas limitadas por viewport."""
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np

from .config import DATA
from .media import NO_WINDOW, check_unchanged
from .processes import spawn
from .transcription import signature, write_json

RATE = 16000
BASE = 128


def cache_path(project, index):
    key = hashlib.sha256(json.dumps([1, project['path'], signature(project), index], sort_keys=True).encode()).hexdigest()
    return DATA / 'waveforms' / key


def manifest(project, index):
    check_unchanged(project)
    folder = cache_path(project, index)
    try:
        result = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if result['rate'] != RATE or result['base'] != BASE or not result['levels']:
            return None
        for level, count in enumerate(result['levels']):
            if count < 1 or (folder / f'{level}.bin').stat().st_size != count * 8:
                return None
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None


def generate(request, emit):
    project, index = request['project'], request['options']['index']
    check_unchanged(project)
    if manifest(project, index):
        return True
    folder = Path(request['work']) / 'envelope'
    folder.mkdir()
    command = [request['ffmpeg'], '-v', 'error', '-nostdin', '-i', project['path'], '-map', f'0:{index}', '-vn',
               '-t', str(project['metadata']['duration']), '-threads', '2', '-ac', '1', '-ar', str(RATE),
               '-f', 'f32le', '-acodec', 'pcm_f32le', 'pipe:1']
    count = samples = 0
    with spawn(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW) as process:
        try:
            with (folder / '0.bin').open('wb') as output:
                while chunk := process.stdout.read(BASE * 4096 * 4):
                    if len(chunk) % 4:
                        raise ValueError('PCM incompleto.')
                    data = np.frombuffer(chunk, dtype='<f4')
                    if not np.isfinite(data).all():
                        raise ValueError('PCM inválido.')
                    samples += len(data)
                    full = len(data) // BASE
                    if full:
                        windows = data[:full * BASE].reshape(-1, BASE)
                        output.write(np.column_stack((windows.min(axis=1), windows.max(axis=1))).astype('<f4').tobytes())
                        count += full
                    tail = data[full * BASE:]
                    if len(tail):
                        output.write(np.array([[tail.min(), tail.max()]], dtype='<f4').tobytes())
                        count += 1
                    emit(stage='waveform', progress=min(95, samples / RATE / project['metadata']['duration'] * 95), processed_seconds=samples / RATE)
            if process.wait(timeout=15) or not count:
                raise ValueError('A faixa não pôde ser decodificada para waveform.')
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            process.stdout.close()
    levels = [count]
    while count > 1:
        level = len(levels)
        with (folder / f'{level - 1}.bin').open('rb') as source, (folder / f'{level}.bin').open('wb') as output:
            while chunk := source.read(8192 * 8):
                rows = np.frombuffer(chunk, dtype='<f4').reshape(-1, 2)
                pairs = len(rows) // 2
                if pairs:
                    grouped = rows[:pairs * 2].reshape(-1, 2, 2)
                    output.write(np.column_stack((grouped[:, :, 0].min(axis=1), grouped[:, :, 1].max(axis=1))).astype('<f4').tobytes())
                if len(rows) % 2:
                    output.write(rows[-1].tobytes())
        count = (count + 1) // 2
        levels.append(count)
    check_unchanged(project)
    write_json(folder / 'manifest.json', dict(rate=RATE, base=BASE, samples=samples, duration=project['metadata']['duration'], stream=index, levels=levels))
    target = cache_path(project, index)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        # Cache incompleto é isolado; nunca substitui arquivos de mídia.
        os.replace(target, Path(request['work']) / 'invalid-cache')
    os.replace(folder, target)
    return False


def read_range(project, index, start, end, points):
    info = manifest(project, index)
    if not info:
        raise ValueError('Gere a forma de onda desta faixa antes de consultá-la.')
    if not 0 <= start < end <= project['metadata']['duration']:
        raise ValueError('Janela da waveform fora da duração da mídia.')
    level = min(len(info['levels']) - 1, max(0, math.ceil(math.log2(max(1, (end - start) * RATE / BASE / max(1, points - 2))))))
    step = BASE * 2 ** level / RATE
    first = min(info['levels'][level], int(start / step))
    last = min(info['levels'][level], math.ceil(end / step))
    with (cache_path(project, index) / f'{level}.bin').open('rb') as source:
        source.seek(first * 8)
        values = np.frombuffer(source.read((last - first) * 8), dtype='<f4').reshape(-1, 2).tolist()
    return dict(start=first * step, step=step, peaks=values, stream=index, level=level, duration=info['duration'])
