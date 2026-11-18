"""Importação estrita: segundos, SRT e timecode HH:MM:SS:FF (FPS da mídia)."""
import csv
import io
import math
import re
import unicodedata

MAX_ROWS = 100000


def timestamp(value, fps=30):
    raw = str(value).strip()
    if re.fullmatch(r'\d+:\d{2}:\d{2}:\d{2}', raw):
        h, m, s, frame = map(int, raw.split(':'))
        if m >= 60 or s >= 60 or fps <= 0 or frame >= round(fps):
            raise ValueError(f'Timecode inválido: {raw}')
        return h * 3600 + m * 60 + s + frame / fps
    if ';' in raw:
        raise ValueError('Timecode drop-frame com ponto e vírgula não suportado nesta fase. Exporte SRT.')
    parts = raw.replace(',', '.').split(':')
    try:
        if len(parts) == 1:
            number = float(parts[0])
        elif len(parts) in (2, 3):
            numbers = [float(p) for p in parts]
            if any(p < 0 for p in numbers) or any(p >= 60 for p in numbers[1:]):
                raise ValueError()
            number = sum(p * 60 ** i for i, p in enumerate(reversed(numbers)))
        else:
            raise ValueError()
    except ValueError as exc:
        raise ValueError(f'Timestamp inválido: {raw}') from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f'Timestamp inválido: {raw}')
    return number


def normalized(value):
    text = unicodedata.normalize('NFKD', value.strip().lower())
    return ''.join(c for c in text if not unicodedata.combining(c)).replace('_', ' ')


def parse(text, extension, duration, fps):
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    rows = []
    if extension == '.srt':
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = block.strip().splitlines()
            if lines and lines[0].strip().isdigit():
                lines.pop(0)
            if not lines or '-->' not in lines[0]:
                raise ValueError('Bloco SRT sem intervalo válido.')
            start, end = lines[0].split('-->', 1)
            rows.append((start, end.strip(), '\n'.join(lines[1:])))
    elif extension == '.csv':
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = {normalized(h): h for h in reader.fieldnames or []}
        def column(aliases):
            return next((headers[a] for a in aliases if a in headers), None)
        start_key = column(['start', 'start time', 'start timecode', 'in', 'inicio', 'timecode in'])
        end_key = column(['end', 'end time', 'end timecode', 'out', 'fim', 'timecode out'])
        text_key = column(['text', 'transcript', 'transcription', 'texto', 'transcricao', 'subtitle', 'caption'])
        if not all((start_key, end_key, text_key)):
            raise ValueError('CSV precisa de colunas Start/End/Text ou Início/Fim/Texto. Exporte SRT caso seu Premiere use outro formato.')
        rows = [(r[start_key], r[end_key], r[text_key]) for r in reader]
    else:
        raise ValueError('Use uma transcrição SRT ou CSV.')
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError('A transcrição está vazia ou excede 100 mil trechos.')
    segments = []
    for i, (start, end, content) in enumerate(rows, 1):
        a, b = timestamp(start, fps), timestamp(end, fps)
        if not 0 <= a < b <= duration + 0.05:
            raise ValueError(f'Trecho {i}: intervalo inválido ou fora da duração do vídeo.')
        if not content or not content.strip():
            raise ValueError(f'Trecho {i}: texto vazio.')
        segments.append(dict(id=i, start=a, end=min(b, duration), text=content.strip()))
    return sorted(segments, key=lambda s: (s['start'], s['end']))


def srt(segments):
    def stamp(seconds):
        ms = round(seconds * 1000)
        return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'
    return '\n\n'.join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i, s in enumerate(segments, 1)) + '\n'
