import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from .config import ROOT
from .processes import run

EXTENSIONS = {'.mp4', '.mkv', '.mov', '.webm'}
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def binary(name):
    configured = os.environ.get(name.upper() + '_PATH')
    if configured:
        path = Path(configured)
        return str(path) if path.is_file() else None
    found = shutil.which(name)
    if found:
        return found
    return next((str(p) for p in (ROOT / '.tools').glob(f'**/{name}.exe')), None)


def source_path(value):
    raw = Path(value.strip().strip('"'))
    if not raw.is_absolute():
        raise ValueError('Informe um caminho absoluto para o vídeo.')
    path = raw.resolve()
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError('Formato não suportado. Use MP4, MKV, MOV ou WEBM.')
    if not path.is_file():
        raise FileNotFoundError('Arquivo original indisponível. Localize-o novamente.')
    return path


def probe(path):
    ffprobe = binary('ffprobe')
    if not ffprobe:
        raise ValueError('FFprobe não encontrado. Execute scripts/configurar.ps1 ou configure FFPROBE_PATH.')
    try:
        result = run([ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                     timeout=60, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('A leitura da mídia excedeu 60 segundos.') from exc
    if result.returncode:
        raise ValueError('FFprobe não conseguiu ler esta mídia. Verifique se o arquivo está íntegro.')
    data = json.loads(result.stdout)
    videos = [s for s in data.get('streams', []) if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        raise ValueError('O arquivo não contém uma faixa de vídeo reproduzível.')
    video = videos[0]
    rate = video.get('avg_frame_rate', '0/1')
    try:
        fps = float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        fps = 0
    duration = float(data.get('format', {}).get('duration') or video.get('duration') or 0)
    if duration <= 0:
        raise ValueError('A duração da mídia não pôde ser determinada.')
    audio = [dict(index=s['index'], codec=s.get('codec_name', '?'), channels=s.get('channels', 0),
                  sample_rate=int(s.get('sample_rate', 0)), name=s.get('tags', {}).get('title') or (s.get('tags', {}).get('handler_name') if s.get('tags', {}).get('handler_name') not in (None, 'SoundHandler') else None) or f'Faixa {i + 1}',
                  language=s.get('tags', {}).get('language', 'und'))
             for i, s in enumerate(s for s in data.get('streams', []) if s['codec_type'] == 'audio')]
    stat = path.stat()
    return dict(duration=duration, start_time=float(data.get('format', {}).get('start_time') or 0),
                video_start_time=float(video.get('start_time') or 0),
                sample_aspect_ratio=video.get('sample_aspect_ratio', '1:1'), field_order=video.get('field_order', 'unknown'),
                color_transfer=video.get('color_transfer', 'unknown'),
                width=video.get('width', 0), height=video.get('height', 0), fps=fps,
                frame_rate=rate, video_codec=video.get('codec_name', '?'), video_index=video['index'],
                audio=audio, size=stat.st_size, mtime_ns=stat.st_mtime_ns,
                browser_hint=path.suffix.lower() == '.mp4' and video.get('codec_name') == 'h264')


def check_unchanged(project):
    path = source_path(project['path'])
    stat = path.stat()
    meta = project['metadata']
    if stat.st_size != meta['size'] or stat.st_mtime_ns != meta['mtime_ns']:
        raise ValueError('A mídia foi modificada. Relocalize o arquivo para atualizar os metadados e limpar dados incompatíveis.')
    return path
