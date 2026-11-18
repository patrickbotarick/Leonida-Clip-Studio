"""Verifica imports nativos e ferramentas realmente executaveis."""
import importlib
import json
import platform
import struct
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.media import binary, NO_WINDOW
from backend.config import ROOT, DATA
from backend.processes import run


def diagnose():
    checks = dict(python_312_x64=sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8)
    errors = []
    versions = dict(python=platform.python_version())
    for name in ('fastapi','uvicorn','python_multipart','pydantic','faster_whisper','ctranslate2','av','numpy','httpx','onnxruntime'):
        try:
            module = importlib.import_module(name)
            checks[name] = True
            versions[name] = getattr(module, '__version__', 'importado')
        except Exception as exc:
            checks[name] = False
            errors.append(f'{name}: {exc}')
    for name in ('ffmpeg', 'ffprobe'):
        try:
            executable = binary(name)
            result = run([executable,'-version'], timeout=15, text=True, creationflags=NO_WINDOW) if executable else None
            checks[name] = bool(result and result.returncode == 0)
            if checks[name]: versions[name] = result.stdout.splitlines()[0]
            else: errors.append(f'{name} ausente. Execute Configurar Leonida Clip Studio.bat.')
        except Exception as exc:
            checks[name] = False; errors.append(f'{name}: {exc}')
    if checks.get('ffmpeg'):
        try:
            result = run([binary('ffmpeg'),'-hide_banner','-encoders'], timeout=15, text=True, creationflags=NO_WINDOW)
            checks['h264_aac'] = result.returncode == 0 and 'libx264' in result.stdout and ' aac ' in result.stdout
        except Exception as exc:
            checks['h264_aac'] = False; errors.append(f'Encoders: {exc}')
    checks['frontend'] = (ROOT / 'frontend/dist/index.html').is_file()
    try:
        with tempfile.TemporaryFile(dir=DATA) as output: output.write(b'leonida'); output.flush()
        checks['data_writable'] = True
    except OSError as exc:
        checks['data_writable'] = False; errors.append(f'Pasta de dados: {exc}')
    return dict(ok=all(checks.values()),checks=checks,versions=versions,errors=errors,
                help='docs/INSTALL_WINDOWS.md. DLLs: Visual C++ Redistributable x64. GPU/CUDA e modelos Whisper sao opcionais.')


if __name__ == '__main__':
    result = diagnose()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['ok'] else 1)
