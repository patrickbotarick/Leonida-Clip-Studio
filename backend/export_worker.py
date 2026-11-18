"""Exporta em staging exclusivo; o supervisor publica o lote após validação."""
import json
import subprocess
import sys
from pathlib import Path

from .exports import ExportOptions, plan_export, write_reports, write_text
from .media import NO_WINDOW, binary, check_unchanged, probe
from .premiere_xml import build_xml
from .processes import run, spawn
from .transcription import write_json
from .transcription_worker import emit


def preceding_keyframe(project, cut):
    # Leitura limitada ao primeiro pacote retornado no seek do índice do contêiner.
    result = run([binary('ffprobe'), '-v', 'error', '-select_streams', str(project['metadata'].get('video_index', 0)), '-read_intervals', f'{cut["start"]}%+#1',
                  '-show_packets', '-show_entries', 'packet=pts_time,flags', '-of', 'json', project['path']], timeout=30, creationflags=NO_WINDOW)
    packets = json.loads(result.stdout).get('packets', []) if result.returncode == 0 else []
    if not packets or 'K' not in packets[0].get('flags', ''):
        raise ValueError('Não foi possível determinar um quadro-chave para cópia rápida. Use recodificação.')
    start = max(0, float(packets[0]['pts_time']) - project['metadata'].get('start_time', 0))
    if start > cut['start'] + .001:
        raise ValueError('O índice não encontrou quadro-chave anterior. Use recodificação.')
    return start


def render_clip(request, cut, target, completed, total):
    project, options = request['project'], request['options']
    fast = options['method'] == 'fast'
    start = preceding_keyframe(project, cut) if fast else cut['start']
    duration = cut['end'] - start
    command = [request['ffmpeg'], '-hide_banner', '-v', 'error', '-nostdin', '-n', '-ss', f'{start:.9f}', '-i', project['path'],
               '-t', f'{duration:.9f}', '-map', f'0:{project["metadata"].get("video_index", 0)}']
    for index in options['audio_indices']:
        command.extend(['-map', f'0:{index}'])
    command.extend(['-map_metadata', '-1', '-map_chapters', '-1', '-sn', '-dn'])
    tracks = {a['index']: a for a in project['metadata']['audio']}
    for number, index in enumerate(options['audio_indices']):
        command.extend([f'-metadata:s:a:{number}', f'title={tracks[index]["name"]}',
                        f'-metadata:s:a:{number}', f'handler_name={tracks[index]["name"]}',
                        f'-metadata:s:a:{number}', f'language={tracks[index].get("language", "und")}',
                        f'-disposition:a:{number}', 'default' if number == 0 else '0'])
    if fast:
        command.extend(['-c', 'copy', '-avoid_negative_ts', 'make_zero'])
    else:
        command.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(options['crf']), '-threads', '2',
                        '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough', '-c:a', 'aac', '-b:a', '192k'])
    command.extend(['-movflags', '+faststart+use_metadata_tags', '-progress', 'pipe:1', '-nostats', str(target)])
    with (Path(request['work']) / 'ffmpeg-error.txt').open('w', encoding='utf-8') as error:
        with spawn(command, stdout=subprocess.PIPE, stderr=error, text=True, encoding='utf-8', creationflags=NO_WINDOW) as process:
            try:
                for line in process.stdout:
                    if line.startswith('out_time_us='):
                        try:
                            elapsed = max(0, int(line.strip().split('=', 1)[1]) / 1e6)
                        except ValueError:
                            continue
                        emit(stage='exporting_video', progress=min(94, (completed + min(elapsed, cut['duration'])) / total * 94), processed_seconds=completed + min(elapsed, cut['duration']))
                if process.wait():
                    raise ValueError('FFmpeg não conseguiu exportar o MP4. Verifique codec, dimensões e espaço em disco; tente recodificação se usou cópia rápida.')
            finally:
                if process.poll() is None:
                    process.kill(); process.wait()
                process.stdout.close()
    meta = probe(target)
    if len(meta['audio']) != len(options['audio_indices']) or (meta['width'], meta['height']) != (project['metadata']['width'], project['metadata']['height']):
        raise ValueError('O MP4 exportado não preservou resolução ou quantidade de faixas.')
    if any(actual['channels'] != tracks[index]['channels'] for actual, index in zip(meta['audio'], options['audio_indices'])):
        raise ValueError('O MP4 exportado não preservou os canais das faixas selecionadas.')
    frame = 1 / (project['metadata'].get('fps') or 25)
    if not fast and abs(meta['duration'] - cut['duration']) > max(frame * 2, .12):
        raise ValueError('Duração do MP4 fora da tolerância de quadros/amostras. Lote não publicado.')
    return dict(source_start=start, source_end=cut['end'], video_start=meta.get('video_start_time', 0), duration=meta['duration'],
                requested_start=cut['start'], requested_end=cut['end'], method=options['method'],
                width=meta['width'], height=meta['height'], frame_rate=meta['frame_rate'], audio=meta['audio'],
                precision='aproximada por quadro-chave' if fast else 'recodificada; limitada aos quadros/amostras disponíveis')


def export(request):
    project, options = request['project'], request['options']
    plan = plan_export(project, ExportOptions.model_validate({k: v for k, v in options.items() if k != 'resolved_destination'}))
    if plan['token'] != options['plan_token']:
        raise ValueError('Prévia de exportação não corresponde ao projeto/opções.')
    folder = Path(request['export_stage'])
    folder.mkdir(exist_ok=False)
    (folder / '.leonida-owner').write_text(request['job_id'], encoding='ascii')
    rendered = {}
    completed = 0
    for number, row in enumerate(plan['rows'], 1):
        if 'mp4' not in options['formats']:
            break
        emit(stage='exporting_video', progress=completed / plan['total_source_seconds'] * 94, completed_units=number-1, total_units=len(plan['rows']), unit='cortes')
        rendered[row['cut']['id']] = render_clip(request, row['cut'], folder / (row['name'] + '.mp4'), completed, plan['total_source_seconds'])
        completed += row['cut']['duration']
    emit(stage='exporting_reports', progress=95)
    write_reports(folder, project, plan, options, rendered)
    if 'xml' in options['formats']:
        write_text(folder, 'sequencia.xml', build_xml(project, plan))
    check_unchanged(project)
    manifest = dict(schema_version=1, export_id=request['job_id'], project_id=project['id'], project_name=project['name'],
                    revision=project['revision'], source=project['path'], source_metadata=project['metadata'],
                    created_at=request['created_at'], options=options, cuts=plan['cuts'], rendered=rendered,
                    warnings=plan['warnings'], files=[dict(name=name, bytes=(folder / name).stat().st_size) for name in plan['files'] if name != 'manifesto.json'])
    write_text(folder, 'manifesto.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    write_json(Path(request['work']) / 'result.json', dict(files=plan['files'], cut_count=len(plan['cuts']), warnings=plan['warnings']))
    emit(stage='verifying_export', progress=99, completed_units=len(plan['rows']), total_units=len(plan['rows']), unit='cortes')


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        export(request)
    except Exception as exc:
        write_json(Path(request['work']) / 'error.json', dict(message=str(exc) if isinstance(exc, ValueError) else 'Não foi possível gravar o lote. Confira a pasta, permissões e espaço livre. Nenhum arquivo anterior foi sobrescrito.'))
        raise SystemExit(1)
