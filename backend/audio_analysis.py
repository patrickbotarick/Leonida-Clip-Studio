"""Medidas por stream com PCM em fluxo, sem carregar o áudio completo."""
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from .config import DATA
from .media import NO_WINDOW
from .processes import spawn
from .transcription import signature, write_json

RATE = 8000
WINDOW = .5


def scan_track(project, index, ffmpeg, emit):
    key = hashlib.sha256(json.dumps([1, project['path'], signature(project), index], sort_keys=True).encode()).hexdigest()
    target = DATA / 'analysis' / 'audio-cache' / f'{key}.json'
    if target.is_file():
        try:
            rows = json.loads(target.read_text(encoding='utf-8'))
            if isinstance(rows, list) and all(set(r) == {'start', 'end', 'rms_db', 'peak_db'} and all(math.isfinite(v) for v in r.values()) for r in rows):
                emit(project['metadata']['duration'])
                return rows
        except (ValueError, TypeError):
            pass
    command = [ffmpeg, '-v', 'error', '-nostdin', '-i', project['path'], '-map', f'0:{index}', '-vn',
               '-t', str(project['metadata']['duration']), '-threads', '2', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-acodec', 'pcm_f32le', 'pipe:1']
    rows = []
    with spawn(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW) as process:
        try:
            while True:
                chunk = process.stdout.read(int(RATE * WINDOW * 4))
                if not chunk:
                    break
                if len(chunk) % 4:
                    raise ValueError('PCM incompleto na análise sonora.')
                data = np.frombuffer(chunk, dtype='<f4')
                start = len(rows) * WINDOW
                end = min(project['metadata']['duration'], start + len(data) / RATE)
                if end <= start:
                    break
                rms = float(np.sqrt(np.mean(np.square(data, dtype=np.float64))))
                peak = float(np.max(np.abs(data)))
                rows.append(dict(start=start, end=end, rms_db=max(-96, 20 * math.log10(max(1e-12, rms))),
                                 peak_db=max(-96, 20 * math.log10(max(1e-12, peak)))))
                if len(rows) % 20 == 0:
                    emit(end)
            if process.wait(timeout=15):
                raise ValueError('Não foi possível decodificar uma das faixas para análise.')
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            process.stdout.close()
    if not rows:
        raise ValueError('A faixa não forneceu amostras de áudio.')
    write_json(target, rows)
    emit(rows[-1]['end'])
    return rows


def features(rows, index, silence_db):
    non_silent = [r['rms_db'] for r in rows if r['rms_db'] > silence_db]
    baseline = float(np.median(non_silent)) if non_silent else -96
    threshold = max(-20, baseline + 10)
    silences, events = [], []
    silence_start = None
    previous = rows[0]['rms_db']
    for row in rows:
        if row['rms_db'] < silence_db:
            if silence_start is None:
                silence_start = row['start']
        elif silence_start is not None:
            if row['start'] - silence_start >= 1:
                silences.append(dict(start=silence_start, end=row['start']))
            silence_start = None
        delta = row['rms_db'] - previous
        kind = 'high_energy' if row['rms_db'] >= threshold and row['peak_db'] > -12 else 'energy_rise' if delta >= 12 and row['rms_db'] > -35 and (previous > silence_db or row['rms_db'] > -18) else None
        if kind and (not events or row['start'] - events[-1]['start'] >= 2):
            events.append(dict(stream=index, start=row['start'], end=row['end'], rms_db=row['rms_db'], peak_db=row['peak_db'], delta_db=delta, kind=kind))
        previous = row['rms_db']
    if silence_start is not None and rows[-1]['end'] - silence_start >= 1:
        silences.append(dict(start=silence_start, end=rows[-1]['end']))
    stride = max(1, math.ceil(len(rows) / 500))
    curve = [dict(time=group[0]['start'], rms_db=max(r['rms_db'] for r in group), peak_db=max(r['peak_db'] for r in group)) for i in range(0, len(rows), stride) if (group := rows[i:i+stride])]
    return dict(stream=index, measured_seconds=rows[-1]['end'], median_active_rms_db=baseline,
                max_peak_db=max(r['peak_db'] for r in rows), silence_seconds=sum(s['end'] - s['start'] for s in silences),
                silence_intervals=silences, event_count=len(events), curve=curve, events=events)
