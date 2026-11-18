"""Contratos e arquivos locais compartilhados pelo serviço e pelo worker ASR."""
import hashlib
import ctypes
import importlib.metadata
import importlib.util
import json
import math
import os
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .config import DATA

MODELS = {
    'tiny': {'label': 'Tiny', 'approx_mb': 75},
    'base': {'label': 'Base', 'approx_mb': 145},
    'small': {'label': 'Small', 'approx_mb': 485},
}
PROFILES = {
    'economico': {'model': 'tiny', 'beam_size': 1, 'threads': 2},
    'equilibrado': {'model': 'base', 'beam_size': 3, 'threads': 4},
    'alta_qualidade': {'model': 'small', 'beam_size': 5, 'threads': 4},
}
ALGORITHM = 1
ACTIVE = {'queued', 'running', 'cancelling'}
MODEL_ROOT = DATA / 'models'
ASR_ROOT = DATA / 'transcription'


class TranscriptionOptions(BaseModel):
    profile: Literal['economico', 'equilibrado', 'alta_qualidade'] = 'economico'
    model: Literal['tiny', 'base', 'small'] = 'tiny'
    device: Literal['cpu', 'cuda'] = 'cpu'
    language: Literal['auto', 'pt', 'en'] = 'auto'
    threads: int = Field(default=2, ge=1, le=4)
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    replace_existing: bool = False

    @model_validator(mode='after')
    def valid_range(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError('O fim do trecho precisa ser posterior ao início.')
        return self


def model_directory(name):
    if name not in MODELS:
        raise ValueError('Modelo não suportado. Use tiny, base ou small.')
    return MODEL_ROOT / name


def installed_model(name):
    folder = model_directory(name)
    try:
        manifest = json.loads((folder / 'leonida-model.json').read_text(encoding='utf-8'))
        required = ('config.json', 'model.bin', 'tokenizer.json')
        if manifest['name'] != name or not all((folder / f).is_file() and (folder / f).stat().st_size == manifest['files'][f]['size'] for f in required):
            return None
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        return None


def catalog():
    return [dict(name=name, **info, installed=bool(installed_model(name)), repository=f'Systran/faster-whisper-{name}') for name, info in MODELS.items()]


def capabilities():
    installed = bool(importlib.util.find_spec('faster_whisper'))
    devices = 0
    missing_libraries = []
    if installed:
        try:
            import ctranslate2
            devices = ctranslate2.get_cuda_device_count()
        except (ImportError, RuntimeError, OSError):
            pass
    if devices and os.name == 'nt':
        for library in ('cublas64_12.dll', 'cudnn64_9.dll'):
            try:
                ctypes.WinDLL(library)
            except OSError:
                missing_libraries.append(library)
    return dict(installed=installed, models=catalog(), profiles=PROFILES, cuda_devices=devices,
                cuda_libraries_available=devices > 0 and not missing_libraries, cuda_missing_libraries=missing_libraries,
                cuda_validated=False, default_device='cpu', max_threads=4,
                engine_version=importlib.metadata.version('faster-whisper') if installed else None)


def signature(project):
    return {k: project['metadata'][k] for k in ('size', 'mtime_ns', 'duration')}


def cache_key(project, options, manifest):
    payload = dict(algorithm=ALGORITHM, path=project['path'], signature=signature(project),
                   audio=sorted(project['selected_audio']), options={k: v for k, v in options.items() if k != 'replace_existing'},
                   model_revision=manifest['revision'], engine=importlib.metadata.version('faster-whisper'))
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def remove_work(path):
    """Só remove uma pasta filha, resolvida, dentro do diretório de trabalho ASR."""
    root = (ASR_ROOT / 'work').resolve()
    target = Path(path).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError('Diretório temporário fora da área de trabalho permitida.')
    if target.exists():
        shutil.rmtree(target)


def windows(start, end, block_seconds=300, overlap=5):
    cursor = start
    while cursor < end:
        core_end = min(cursor + block_seconds, end)
        yield (cursor, core_end, max(start, cursor - overlap), min(end, core_end + overlap))
        cursor = core_end


def global_segments(segments, core_start, core_end, window_start, media_end):
    """Atribui cada fala ao bloco que contém seu ponto médio, preservando contexto."""
    result = []
    for segment in segments:
        a = float(segment['start']) + window_start
        b = min(float(segment['end']) + window_start, media_end)
        middle = (a + b) / 2
        text = segment['text'].strip()
        if math.isfinite(a) and math.isfinite(b) and core_start <= middle < core_end and 0 <= a < b and text:
            result.append(dict(start=a, end=b, text=text))
    return result


def normalize_segments(rows, duration):
    if len(rows) > 100000:
        raise ValueError('A transcrição excede 100 mil trechos.')
    output = []
    for row in sorted(rows, key=lambda r: (r['start'], r['end'])):
        a, b, text = float(row['start']), float(row['end']), str(row['text']).strip()
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= duration + .05) or not text:
            raise ValueError('O motor retornou um trecho com timestamp inválido.')
        duplicate = any(p['text'].casefold() == text.casefold() and min(p['end'], b) - max(p['start'], a) > 0 for p in output[-5:])
        if not duplicate:
            output.append(dict(id=len(output) + 1, start=a, end=min(b, duration), text=text))
    return output
