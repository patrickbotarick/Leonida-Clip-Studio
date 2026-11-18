"""Planejamento de exportações aprovadas, relatórios e remapeamento de legendas."""
import csv
import hashlib
import io
import json
import math
import re
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import database as db
from .config import DATA
from .editing import validate_cuts
from .media import check_unchanged
from .transcripts import srt


class ExportOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    expected_revision: int = Field(ge=0)
    ids: list[str] = Field(default_factory=list, max_length=1000)
    formats: list[Literal['mp4', 'xml', 'json', 'csv', 'txt', 'srt']] = Field(default_factory=lambda: ['json'], min_length=1, max_length=6)
    destination: str = Field(default='', max_length=3000)
    audio_indices: list[int] = Field(default_factory=list, max_length=32)
    method: Literal['precise', 'fast'] = 'precise'
    sequence_mode: Literal['compact', 'original'] = 'compact'
    crf: int = Field(default=20, ge=18, le=28)
    acknowledge_fast: bool = False
    confirm_cfr: bool = False
    plan_token: str = Field(default='', max_length=64)


def safe_name(value, limit=60):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', value).strip(' .')[:limit].rstrip(' .') or 'corte'
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        value = '_' + value
    return value


def destination_path(value):
    if not value.strip():
        return DATA / 'exports'
    path = Path(value.strip().strip('"'))
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        raise ValueError('A pasta de destino precisa ser um caminho absoluto local.')
    path = path.resolve()
    if not path.is_dir():
        raise ValueError('A pasta de destino informada não existe. Escolha uma pasta existente.')
    # Subpasta exclusiva por lote; nenhum arquivo preexistente é aberto para escrita.
    return path


def frame_rate(metadata):
    try:
        fps = Fraction(metadata['frame_rate'])
    except (ValueError, KeyError, ZeroDivisionError):
        raise ValueError('FPS racional ausente: XML não pode ser calculado com segurança.')
    if not 0 < fps <= 120:
        raise ValueError('XML aceita FPS de 1 a 120 nesta versão.')
    nominal = round(float(fps))
    ntsc = fps == Fraction(nominal * 1000, 1001)
    if fps.denominator != 1 and not ntsc:
        raise ValueError('FPS não representável pelo timebase/NTSC do XML FCP7.')
    return fps, nominal, ntsc


def to_frame(seconds, fps):
    value = Fraction(str(seconds)) * fps
    return (value.numerator * 2 + value.denominator) // (value.denominator * 2)


def layout(cuts, mode, fps=None):
    cursor, rows = 0, []
    for index, cut in enumerate(cuts, 1):
        a, b = (to_frame(cut['start'], fps), to_frame(cut['end'], fps)) if fps else (cut['start'], cut['end'])
        if b <= a:
            raise ValueError('Um corte fica vazio ao quantizar para os quadros da sequência XML.')
        start = cursor if mode == 'compact' else a
        rows.append(dict(cut=cut, number=index, name=f'{index:03d}-{safe_name(cut["title"])}', source_in=a, source_out=b,
                         timeline_in=start, timeline_out=start + b - a))
        cursor = start + b - a
    return rows


def remap_segments(segments, source_in, source_out, offset=0, limit=None):
    output = []
    for segment in segments:
        a, b = max(segment['start'], source_in), min(segment['end'], source_out)
        if b <= a:
            continue
        a, b = max(0, a - source_in + offset), b - source_in + offset
        if limit is not None:
            b = min(b, limit)
        # Evita eventos vazios após quantização SRT em milissegundos.
        if round(b * 1000) > round(a * 1000):
            output.append(dict(start=a, end=b, text=segment['text']))
    return output


def plan_export(project, options):
    if project.get('revision', 0) != options.expected_revision:
        raise db.RevisionConflict('O projeto mudou. Reabra-o e atualize a prévia de exportação.')
    check_unchanged(project)
    if len(set(options.ids)) != len(options.ids) or len(set(options.formats)) != len(options.formats):
        raise ValueError('Seleção duplicada na exportação.')
    all_cuts = {cut['id']: cut for cut in project.get('cuts', [])}
    if options.ids and any(i not in all_cuts or all_cuts[i]['status'] != 'approved' for i in options.ids):
        raise ValueError('Somente cortes aprovados e existentes podem ser exportados.')
    cuts = sorted((all_cuts[i] for i in options.ids), key=lambda c: (c['start'], c['end'], c['id'])) if options.ids else sorted((c for c in all_cuts.values() if c['status'] == 'approved'), key=lambda c: (c['start'], c['end'], c['id']))
    if not cuts:
        raise ValueError('Aprove pelo menos um corte antes de exportar.')
    validate_cuts(project, cuts)
    tracks = {a['index']: a for a in project['metadata']['audio']}
    if len(set(options.audio_indices)) != len(options.audio_indices) or any(i not in tracks for i in options.audio_indices):
        raise ValueError('Faixas de áudio inexistentes ou duplicadas.')
    warnings = ['Somente os cortes aprovados desta revisão serão incluídos. O arquivo original não é modificado.']
    if any(cuts[i]['start'] < max(c['end'] for c in cuts[:i]) for i in range(1, len(cuts))):
        if options.sequence_mode == 'original' and any(f in options.formats for f in ('xml', 'srt')):
            raise ValueError('Cortes sobrepostos no modo original: ajuste os intervalos ou use sequência consolidada.')
        warnings.append('Há cortes sobrepostos: o conteúdo repetido permanece em clipes distintos e na sequência consolidada.')
    fps = None
    if 'xml' in options.formats:
        if not options.confirm_cfr:
            raise ValueError('Confirme que a fonte usa FPS constante (CFR). XML não representa VFR fielmente nesta versão.')
        fps, _, _ = frame_rate(project['metadata'])
        if project['metadata'].get('field_order', 'progressive') not in ('unknown', 'progressive'):
            raise ValueError('XML de fonte entrelaçada não suportado nesta versão.')
        if project['metadata'].get('sample_aspect_ratio', '1:1') not in ('1:1', '0:1', 'N/A'):
            raise ValueError('XML de pixels não quadrados não suportado nesta versão.')
        if sum(a['channels'] for a in tracks.values()) > 32:
            raise ValueError('XML limitado a 32 canais de áudio de origem.')
        if any(a['channels'] < 1 for a in tracks.values()) or len({a['sample_rate'] for a in tracks.values()}) > 1:
            raise ValueError('XML requer canais conhecidos e mesma taxa de amostragem nas faixas de origem.')
        warnings.append('XML FCP7: pontos arredondados ao quadro mais próximo, timecode zero/NDF; importação real no Premiere ainda requer validação.')
    if 'mp4' in options.formats:
        if options.method == 'fast':
            if not options.acknowledge_fast:
                raise ValueError('Confirme o corte rápido aproximado por quadros-chave.')
            if project['metadata']['video_codec'] not in ('h264', 'hevc', 'av1', 'mpeg4') or any(tracks[i]['codec'] not in ('aac', 'mp3', 'ac3', 'eac3', 'alac') for i in options.audio_indices):
                raise ValueError('Codec não aceito no MP4 rápido. Escolha recodificação.')
            warnings.append('MP4 rápido inicia no quadro-chave anterior e pode incluir conteúdo extra; duração e legendas são aproximadas. XML/relatórios mantêm os IN/OUT aprovados.')
        elif project['metadata'].get('color_transfer') in ('smpte2084', 'arib-std-b67'):
            raise ValueError('Recodificação SDR de uma fonte HDR foi bloqueada. Use cópia rápida ou converta com gestão de cor apropriada.')
        if options.method == 'precise':
            warnings.append('Recodificação usa H.264/AAC, preserva resolução e timestamps/FPS da fonte; precisão limitada aos quadros/amostras disponíveis. Não há reenquadramento vertical automático.')
    rows = layout(cuts, options.sequence_mode, fps)
    if options.sequence_mode == 'original' and any(rows[i]['source_in'] < rows[i-1]['source_out'] for i in range(1, len(rows))):
        if 'xml' in options.formats:
            raise ValueError('Os pontos se sobrepõem após arredondamento ao quadro. Use modo consolidado.')
    formats = options.formats
    files = [f'decupagem.{f}' for f in formats if f in ('json', 'csv', 'txt')]
    if 'xml' in formats:
        files.append('sequencia.xml')
    if 'srt' in formats:
        files.append('sequencia.srt')
        files.extend(f'{r["name"]}.srt' for r in rows)
    if 'mp4' in formats:
        files.extend(f'{r["name"]}.mp4' for r in rows)
    files.append('manifesto.json')
    options_dict = options.model_dump(exclude={'plan_token'})
    destination = str(destination_path(options.destination))
    token = hashlib.sha256(json.dumps([project['id'], project['revision'], project['metadata'], project['path'], cuts,
                                      project['transcript'], options_dict, destination], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(token=token, destination=destination, project_id=project['id'], revision=project['revision'],
                cuts=cuts, rows=rows, files=files, warnings=warnings,
                audio=[tracks[i] for i in options.audio_indices], sequence_mode=options.sequence_mode,
                sequence_seconds=float(max(r['timeline_out'] for r in rows) / fps) if fps else max(r['timeline_out'] for r in rows),
                total_source_seconds=sum(c['duration'] for c in cuts), fps=str(fps) if fps else None)


def write_text(folder, filename, text):
    with (folder / filename).open('x', encoding='utf-8', newline='') as output:
        output.write(text)


def report_document(project, plan):
    fps = Fraction(plan['fps']) if plan['fps'] else 1
    return dict(schema_version=1, project=project['name'], project_id=project['id'], revision=project['revision'],
                source=project['path'], source_metadata=project['metadata'], selected_audio=plan['audio'],
                sequence_mode=plan['sequence_mode'], warnings=plan['warnings'],
                cuts=[dict(**r['cut'], timeline_start=float(r['timeline_in'] / fps), timeline_end=float(r['timeline_out'] / fps),
                           sequence_source_in=float(r['source_in'] / fps), sequence_source_out=float(r['source_out'] / fps)) for r in plan['rows']])


def write_reports(folder, project, plan, options, rendered):
    document = report_document(project, plan)
    if 'json' in options['formats']:
        write_text(folder, 'decupagem.json', json.dumps(document, ensure_ascii=False, indent=2))
    if 'csv' in options['formats']:
        output = io.StringIO(newline=''); writer = csv.writer(output)
        writer.writerow(['ID', 'Title', 'Status', 'Category', 'SourceInSeconds', 'SourceOutSeconds', 'DurationSeconds', 'TimelineInSeconds', 'TimelineOutSeconds', 'Score', 'ReviewNote'])
        def cell(value):
            text = str(value if value is not None else '')
            return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text
        for c in document['cuts']:
            writer.writerow([cell(v) for v in [c['id'], c['title'], c['status'], c['category'], c['start'], c['end'], c['duration'], c['timeline_start'], c['timeline_end'], c.get('score'), c.get('review_note', '')]])
        write_text(folder, 'decupagem.csv', '\ufeff' + output.getvalue())
    if 'txt' in options['formats']:
        lines = [f'{project["name"]} · revisão {project["revision"]} · cortes aprovados', f'Origem: {project["path"]}', *plan['warnings'], '']
        for c in document['cuts']:
            lines.extend([f'{c["title"]} | {c["start"]:.6f} → {c["end"]:.6f} s | aprovado', c.get('review_note', ''), c.get('transcript_excerpt', ''), ''])
        write_text(folder, 'decupagem.txt', '\n'.join(lines))
    if 'srt' in options['formats']:
        sequence = []
        fps = Fraction(plan['fps']) if plan['fps'] else 1
        for row in plan['rows']:
            c = row['cut']
            rendered_clip = rendered.get(c['id'])
            a = rendered_clip['source_start'] if rendered_clip else c['start']
            b = rendered_clip['source_end'] if rendered_clip else c['end']
            offset = rendered_clip['video_start'] if rendered_clip else 0
            relative = remap_segments(project['transcript'], a, b, offset=offset,
                                      limit=rendered_clip['duration'] if rendered_clip else c['duration'])
            write_text(folder, row['name'] + '.srt', srt(relative))
            sequence.extend(remap_segments(project['transcript'], float(row['source_in'] / fps), float(row['source_out'] / fps), float(row['timeline_in'] / fps)))
        write_text(folder, 'sequencia.srt', srt(sorted(sequence, key=lambda r: (r['start'], r['end']))))
