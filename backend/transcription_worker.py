"""Processo isolado: stdout contém eventos JSON; texto completo permanece no disco local."""
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from .transcription import PROFILES, global_segments, normalize_segments, windows, write_json
from .media import NO_WINDOW
from .processes import spawn

_output_lock = threading.Lock()


def emit(**event):
    with _output_lock:
        print(json.dumps(event, ensure_ascii=False, allow_nan=False), flush=True)


def download(request):
    from huggingface_hub import HfApi, snapshot_download
    from tqdm.auto import tqdm

    class Progress(tqdm):
        def __init__(self, *args, **kwargs):
            self.leonida_unit = 'bytes' if kwargs.get('unit') == 'B' else 'files'
            super().__init__(*args, **{**kwargs, 'disable': True})

        def update(self, n=1):
            # tqdm desabilitado não acumula n; a contagem local reflete callbacks reais.
            self.n += n or 0
            emit(stage='downloading', progress=None, completed_units=self.n, total_units=self.total, unit=self.leonida_unit)
            return True

    repo = f'Systran/faster-whisper-{request["model"]}'
    emit(stage='connecting', progress=None)
    revision = HfApi(token=False).model_info(repo).sha
    target = Path(request['work']) / 'model'
    snapshot_download(repo_id=repo, revision=revision, local_dir=target, token=False,
                      allow_patterns=['config.json', 'preprocessor_config.json', 'model.bin', 'tokenizer.json', 'vocabulary.*'],
                      max_workers=2, tqdm_class=Progress)
    emit(stage='verifying', progress=None)
    from faster_whisper import WhisperModel
    # Além da existência dos arquivos, valida o carregamento nativo CPU offline.
    model = WhisperModel(str(target), device='cpu', compute_type='int8', cpu_threads=2, num_workers=1, local_files_only=True)
    del model
    files = {}
    for file in target.iterdir():
        if file.is_file():
            digest = hashlib.sha256()
            with file.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            files[file.name] = dict(size=file.stat().st_size, sha256=digest.hexdigest())
    if not all(f in files for f in ('config.json', 'model.bin', 'tokenizer.json')):
        raise ValueError('Download incompleto.')
    write_json(target / 'leonida-model.json', dict(name=request['model'], revision=revision, files=files))
    emit(stage='ready', progress=100)


def extract(request, audio_file, start, end, progress_base, progress_span):
    selected = request['project']['selected_audio']
    filters = ''.join(f'[0:{index}]aresample=16000,aformat=sample_fmts=fltp:channel_layouts=mono[a{i}];' for i, index in enumerate(selected))
    if len(selected) > 1:
        filters += ''.join(f'[a{i}]' for i in range(len(selected))) + f'amix=inputs={len(selected)}:duration=longest:dropout_transition=0:normalize=1[out]'
    else:
        filters += '[a0]anull[out]'
    command = [request['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-ss', str(start),
               '-i', request['project']['path'], '-t', str(end - start), '-filter_complex_threads', '1',
               '-filter_complex', filters, '-map', '[out]', '-vn', '-ar', '16000', '-ac', '1',
               '-c:a', 'pcm_s16le', '-threads', str(request['options']['threads']), '-progress', 'pipe:1', str(audio_file)]
    with spawn(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, creationflags=NO_WINDOW) as process:
        try:
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:
                        ratio = min(1, max(0, int(line.split('=')[1]) / 1000000 / (end - start)))
                        emit(stage='extracting', progress=progress_base + progress_span * ratio)
                    except ValueError:
                        pass
            if process.wait():
                raise ValueError('Falha na extração da faixa selecionada.')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def transcribe(request):
    from faster_whisper import WhisperModel

    options, project = request['options'], request['project']
    duration = project['metadata']['duration']
    start, end = options['start'], options['end'] or duration
    emit(stage='loading_model', progress=0)
    model = WhisperModel(request['model_path'], device=options['device'],
                         compute_type='int8' if options['device'] == 'cpu' else 'int8_float16',
                         cpu_threads=options['threads'], num_workers=1, local_files_only=True)
    result = []
    language = None if options['language'] == 'auto' else options['language']
    detected = []
    blocks = list(windows(start, end))
    for number, (core_start, core_end, window_start, window_end) in enumerate(blocks, 1):
        base = (core_start - start) / (end - start) * 100
        span = (core_end - core_start) / (end - start) * 100
        audio_file = Path(request['work']) / f'block-{number}.wav'
        emit(stage='extracting', progress=base, block=number, blocks=len(blocks), processed_seconds=core_start - start)
        try:
            extract(request, audio_file, window_start, window_end, base, span * .1)
            emit(stage='transcribing', progress=base + span * .1)
            segments, info = model.transcribe(str(audio_file), language=language, task='transcribe',
                                             beam_size=PROFILES[options['profile']]['beam_size'],
                                             best_of=1, temperature=0, vad_filter=True,
                                             vad_parameters=dict(min_silence_duration_ms=500),
                                             condition_on_previous_text=False, word_timestamps=False)
            detected.append(dict(language=info.language, probability=info.language_probability, start=window_start))
            # Em auto, cada bloco detecta idioma: não fixa o idioma de uma abertura silenciosa.
            local = []
            for segment in segments:
                local.append(dict(start=segment.start, end=segment.end, text=segment.text))
                processed = max(0, min(core_end - core_start, window_start + segment.end - core_start))
                emit(stage='transcribing', progress=min(99.9, base + span * (.1 + .9 * processed / (core_end - core_start))),
                     processed_seconds=core_start - start + processed, segments=len(result) + len(local))
            result.extend(global_segments(local, core_start, core_end, window_start, duration))
        finally:
            audio_file.unlink(missing_ok=True)
        emit(stage='transcribing', progress=min(99.9, base + span), processed_seconds=core_end - start, segments=len(result))
        write_json(Path(request['work']) / 'checkpoint.json', dict(segments=result, completed_blocks=number))
    result = normalize_segments(result, duration)
    write_json(Path(request['work']) / 'result.json', dict(segments=result, languages=detected,
               options=options, audio_indices=project['selected_audio'], range={'start': start, 'end': end}))
    emit(stage='saving', progress=99.9, segments=len(result), processed_seconds=end - start)


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        if request['kind'] == 'model_download':
            download(request)
        else:
            transcribe(request)
        return 0
    except Exception as exc:
        # Mensagem técnica apenas no arquivo local, sem mídia/texto nem traceback em logs.
        write_json(Path(request['work']) / 'error.json', {'type': type(exc).__name__, 'message': str(exc)[:2000]})
        emit(stage='failed', error_type=type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
