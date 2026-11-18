"""Processamento analítico isolado: áudio local e provedores só com consentimento."""
import json
import sys
from pathlib import Path

from .analysis import (ALGORITHM, finish_suggestions, input_digest, local_candidates,
                       transcript_blocks, validate_result)
from .analysis_providers import ProviderFailure, analyze_block
from .audio_analysis import features, scan_track
from .transcription import write_json
from .transcription_worker import emit


def analyze(request, credential):
    project, options = request['project'], request['options']
    duration = project['metadata']['duration']
    audio = {'tracks': [], 'events': [], 'enabled': options['analyze_audio']}
    indices = project['selected_audio'] if options['analyze_audio'] else []
    for number, index in enumerate(indices):
        emit(stage='analyzing_audio', progress=number / len(indices) * 60, stream=index)
        rows = scan_track(project, index, request['ffmpeg'], lambda seconds: emit(stage='analyzing_audio',
            progress=(number + min(1, seconds / duration)) / len(indices) * 60, processed_seconds=seconds, stream=index))
        data = features(rows, index, options['silence_db'])
        audio['events'].extend(data.pop('events'))
        audio['tracks'].append(data)
    emit(stage='analyzing_text', progress=60)
    if options['provider'] == 'local':
        candidates = local_candidates(project, audio, options)
    else:
        if not options['consent']:
            raise ProviderFailure('Consentimento de envio ausente.')
        blocks = list(transcript_blocks(project['transcript']))
        if len(blocks) > options['max_blocks']:
            raise ProviderFailure('A transcrição excede o limite de blocos autorizado.')
        candidates = []
        for i, block in enumerate(blocks):
            emit(stage='provider_request', progress=60 + 35 * i / len(blocks), block=i + 1, blocks=len(blocks))
            candidates.extend(analyze_block(options['provider'], options, block, credential))
        # Eventos sem fala também permanecem possíveis, sem inventar significado semântico.
        candidates.extend(local_candidates({**project, 'transcript': []}, audio, options))
    emit(stage='ranking', progress=96)
    suggestions = finish_suggestions(project, candidates, options)
    words = sum(len(r['text'].split()) for r in project['transcript'])
    result = dict(algorithm=ALGORITHM, input_digest=input_digest(project), suggestions=suggestions, audio=audio,
                  speech_indicators={'transcript_segments': len(project['transcript']), 'words': words,
                                     'words_per_media_minute': words / (duration / 60),
                                     'note': 'Contagem derivada da transcrição, não detecção acústica de pessoas/falas.'},
                  limitations=['Sem análise visual.', 'Resultados heurísticos/editoriais; não garantem engajamento.',
                               'Nenhuma sugestão aprovada automaticamente.'], options={k: v for k, v in options.items() if k not in ('consent', 'replace_existing', 'cache_key')})
    validate_result(result, project, options)
    write_json(Path(request['work']) / 'result.json', result)
    emit(stage='saving', progress=99, suggestions=len(suggestions))


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    # Credencial só por stdin: não vai para request.json, argumentos, ambiente ou cache.
    credential = json.loads(sys.stdin.readline() or '{}').get('credential', '')
    try:
        analyze(request, credential)
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, ProviderFailure) else 'A análise falhou ao validar mídia ou resultados. Os resultados anteriores foram preservados.'
        write_json(Path(request['work']) / 'error.json', {'message': message})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
