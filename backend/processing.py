"""Fila ASR persistida, um worker isolado e aplicação atômica de resultados."""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from . import database as db
from .config import DATA, ROOT
from .media import NO_WINDOW, binary, check_unchanged
from .processes import spawn
from .transcription import (ACTIVE, ASR_ROOT, MODEL_ROOT, cache_key, capabilities,
                            installed_model, model_directory, normalize_segments,
                            remove_work, signature, write_json)
from .analysis import analysis_key, input_digest, transcript_blocks, validate_result
from .editing import retained_cuts
from .exports import plan_export, safe_name
from .export_storage import cleanup_stage, finalize_export, recover_export


class ProcessingQueue:
    def __init__(self):
        self.lock = threading.RLock()
        self.controls = {}
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='processing-supervisor')
        for job in db.interrupted_jobs():
            if job['kind'] == 'export' and recover_export(job):
                remove_work(ASR_ROOT / 'work' / job['id'])
                continue
            job.update(status='interrupted', stage='interrupted', updated_at=db.now(),
                       error='A execução anterior foi interrompida. Os dados anteriores do projeto foram preservados. Inicie novamente para tentar concluir.')
            db.save_job(job)
            remove_work(ASR_ROOT / 'work' / job['id'])

    def _submit(self, kind, options, project=None, model=None, credential=''):
        with self.lock:
            if self.closed:
                raise ValueError('O serviço está encerrando.')
            active = [c['job'] for c in self.controls.values() if c['job']['status'] in ACTIVE]
            if len(active) >= 2:
                raise ValueError('A fila de processamento está cheia. Aguarde ou cancele uma tarefa.')
            if project and any(j.get('project_id') == project['id'] for j in active):
                raise ValueError('Este projeto já tem um processamento em andamento.')
            if kind == 'model_download' and any(j['kind'] == kind and j['options']['model'] == model for j in active):
                raise ValueError('Este modelo já está sendo baixado.')
            job_id = uuid4().hex
            work = ASR_ROOT / 'work' / job_id
            work.mkdir(parents=True)
            job = dict(id=job_id, kind=kind, project_id=project['id'] if project else None,
                       status='queued', stage='queued', progress=0, options=options,
                       created_at=db.now(), updated_at=db.now(), cache_hit=False)
            if kind == 'export':
                destination = Path(options['resolved_destination'])
                destination.mkdir(parents=True, exist_ok=True)
                job.update(export_stage=str(destination / f'.leonida-{job_id}.partial'),
                           export_folder=str(destination / f'{safe_name(project["name"], 40)}-{job_id}'))
            control = dict(job=job, cancel=threading.Event(), process=None, credential=credential)
            self.controls[job_id] = control
            db.save_job(job)
            request = dict(kind=kind, work=str(work), options=options, model=model)
            if kind == 'export':
                request.update(export_stage=job['export_stage'], job_id=job_id, created_at=job['created_at'])
            if project:
                request.update(project=project, ffmpeg=binary('ffmpeg'))
                if kind == 'transcription':
                    request['model_path'] = str(model_directory(options['model']))
            write_json(work / 'request.json', request)
            self.pool.submit(self._run, control, request)
            # Retém apenas controles ativos; histórico completo é consultado pelo SQLite.
            for old in list(self.controls):
                if len(self.controls) > 100 and self.controls[old]['job']['status'] not in ACTIVE:
                    del self.controls[old]
            return dict(job)

    def download(self, model, consent):
        model_directory(model)
        if not consent:
            raise ValueError('Confirme o download do modelo. Nenhum arquivo de mídia será enviado.')
        if not capabilities()['installed']:
            raise ValueError('Faster Whisper não está instalado. Execute o script de configuração.')
        if installed_model(model):
            raise ValueError('Este modelo já está instalado e pronto para uso offline.')
        return self._submit('model_download', {'model': model}, model=model)

    def waveform(self, project, index):
        check_unchanged(project)
        if index not in {a['index'] for a in project['metadata']['audio']}:
            raise ValueError('Faixa de áudio inexistente.')
        if not binary('ffmpeg'):
            raise ValueError('FFmpeg não encontrado.')
        return self._submit('waveform', {'index': index}, project=project)

    def export(self, project, options):
        plan = plan_export(project, options)
        if not options.plan_token or options.plan_token != plan['token']:
            raise ValueError('Atualize e confira a prévia antes de iniciar a exportação.')
        if 'mp4' in options.formats and not binary('ffmpeg'):
            raise ValueError('FFmpeg não encontrado.')
        return self._submit('export', {**options.model_dump(), 'resolved_destination': plan['destination']}, project=project)

    def transcribe(self, project, options):
        check_unchanged(project)
        if not binary('ffmpeg'):
            raise ValueError('FFmpeg não encontrado.')
        audio = set(project['selected_audio'])
        available = {a['index'] for a in project['metadata']['audio']}
        if not audio or not audio <= available:
            raise ValueError('Escolha pelo menos uma faixa de áudio válida antes de transcrever.')
        if project['transcript'] and not options['replace_existing']:
            raise ValueError('O projeto já tem transcrição. Confirme a substituição; o texto atual só muda após sucesso.')
        end = options['end'] or project['metadata']['duration']
        if not 0 <= options['start'] < end <= project['metadata']['duration']:
            raise ValueError('O trecho de transcrição está fora da duração da mídia.')
        manifest = installed_model(options['model'])
        if not manifest:
            raise ValueError('Modelo ausente ou incompleto. Baixe-o explicitamente antes de transcrever.')
        if options['device'] == 'cuda' and not capabilities()['cuda_libraries_available']:
            raise ValueError('GPU ou bibliotecas CUDA/cuDNN necessárias indisponíveis. Use CPU; nenhuma ferramenta de sistema será instalada automaticamente.')
        key = cache_key(project, options, manifest)
        project = {**project, 'selected_audio': sorted(audio)}
        return self._submit('transcription', {**options, 'cache_key': key}, project=project)

    def _update(self, control, **fields):
        with self.lock:
            control['job'].update(**fields, updated_at=db.now())
            db.save_job(control['job'])

    def analyze(self, project, options, credential=''):
        credential = credential.strip()
        if len(credential) > 1000 or '\n' in credential or '\r' in credential:
            raise ValueError('Formato de chave inválido. Informe apenas a chave para esta execução.')
        check_unchanged(project)
        if (project.get('analysis') or project.get('cuts')) and not options['replace_existing']:
            raise ValueError('Confirme a substituição das sugestões anteriores; elas só mudam após sucesso.')
        if options['analyze_audio']:
            if not binary('ffmpeg'):
                raise ValueError('FFmpeg não encontrado.')
            if not project['selected_audio'] or len(project['selected_audio']) > 8:
                raise ValueError('Escolha entre uma e oito faixas para análise sonora, ou desative o áudio.')
            if not set(project['selected_audio']) <= {a['index'] for a in project['metadata']['audio']}:
                raise ValueError('Há faixas de áudio inválidas na seleção.')
        if not options['analyze_audio'] and not project['transcript']:
            raise ValueError('Importe/transcreva texto ou ative a análise sonora para encontrar evidências.')
        if options['provider'] != 'local':
            if not options['consent']:
                raise ValueError('Autorize explicitamente o envio da transcrição ao provedor escolhido.')
            if not options['model'] or not project['transcript']:
                raise ValueError('Informe um modelo e uma transcrição para análise por provedor.')
            if options['provider'] == 'openai' and not credential.strip():
                raise ValueError('Informe a chave OpenAI para esta execução. Ela não será salva.')
            if options['provider'] == 'ollama' and 'cloud' in options['model'].casefold():
                raise ValueError('Selecione um modelo Ollama local; modelos cloud não são permitidos.')
            if len(list(transcript_blocks(project['transcript']))) > options['max_blocks']:
                raise ValueError('A transcrição excede o limite de blocos configurado; nenhum texto foi enviado.')
        return self._submit('analysis', {**options, 'cache_key': analysis_key(project, options)}, project=project,
                            credential=credential if options['provider'] == 'openai' else '')

    def _apply(self, job, project, result):
        if job.get('kind') == 'analysis':
            suggestions = validate_result(result, project, job['options'])
            check_unchanged(project)
            def apply_analysis(current):
                if input_digest(current) != result['input_digest'] or result['input_digest'] != input_digest(project):
                    raise ValueError('As fontes mudaram durante a análise; sugestões anteriores preservadas.')
                archives['snapshot'] = db.capture_cuts(current, 'analysis_replaced')
                retained = retained_cuts(current)
                fresh = [c for c in suggestions if not any(c['start'] < r['end'] and c['end'] > r['start'] for r in retained)]
                fresh = fresh[:max(0, 1000 - len(retained))]
                current.update(cuts=retained + fresh, analysis={k: v for k, v in result.items() if k != 'suggestions'})
                current['settings']['analysis'] = {k: v for k, v in job['options'].items() if k not in ('cache_key', 'consent', 'replace_existing')}
            archives = {}
            def archive_analysis(connection, current):
                db.store_cut_archive(connection, archives.get('snapshot'))
                db.reset_cut_history(connection, current)
            db.update(project['id'], apply_analysis, expected_revision=project.get('revision', 0), transaction_hook=archive_analysis)
            return
        rows = normalize_segments(result['segments'], project['metadata']['duration'])
        check_unchanged(project)
        def apply(current):
            if signature(current) != signature(project) or current['path'] != project['path']:
                raise ValueError('O arquivo vinculado ao projeto mudou durante a transcrição.')
            archives['snapshot'] = db.capture_cuts(current, 'transcript_replaced')
            current.update(transcript=rows, transcript_source='Faster Whisper local',
                           transcript_info={k: v for k, v in result.items() if k != 'segments'})
            current.update(cuts=retained_cuts(current, invalidate=True), analysis=None)
            current['settings']['transcription'] = {k: v for k, v in job['options'].items() if k not in ('cache_key', 'replace_existing')}
        archives = {}
        def archive_transcript(connection, current):
            db.store_cut_archive(connection, archives.get('snapshot'))
            db.reset_cut_history(connection, current)
        db.update(project['id'], apply, expected_revision=project.get('revision', 0), transaction_hook=archive_transcript)

    def _run(self, control, request):
        job, work = control['job'], Path(request['work'])
        process = None
        failure = None
        try:
            with self.lock:
                if control['cancel'].is_set():
                    return
                self._update(control, status='running', stage='starting')
            cached = ASR_ROOT / 'cache' / f'{job["options"].get("cache_key", "unused")}.json'
            if job['kind'] in ('transcription', 'analysis') and cached.is_file():
                try:
                    result = json.loads(cached.read_text(encoding='utf-8'))
                    if job['kind'] == 'analysis':
                        validate_result(result, request['project'], job['options'])
                        if result['input_digest'] != input_digest(request['project']):
                            raise ValueError('Cache com origem diferente.')
                    else:
                        normalize_segments(result['segments'], request['project']['metadata']['duration'])
                except (ValueError, KeyError, TypeError):
                    cached.unlink(missing_ok=True)
                else:
                    with self.lock:
                        if control['cancel'].is_set():
                            return
                        self._apply(job, request['project'], result)
                        self._update(control, status='completed', stage='completed', progress=100, cache_hit=True,
                                     **({'suggestions': len(result['suggestions'])} if job['kind'] == 'analysis' else {'segments': len(result['segments'])}))
                    return
            env = {**os.environ, 'PYTHONUTF8': '1', 'HF_HOME': str(DATA / 'hf-cache'),
                   'HF_HUB_CACHE': str(DATA / 'hf-cache' / 'hub'), 'HF_HUB_DISABLE_TELEMETRY': '1',
                   'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1', 'HF_HUB_DISABLE_XET': '1',
                   'OMP_NUM_THREADS': str(job['options'].get('threads', 2))}
            for secret_name in ('OPENAI_API_KEY', 'OPENAI_API_TOKEN', 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
                env.pop(secret_name, None)
            if job['kind'] == 'transcription':
                env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            else:
                env.pop('HF_HUB_OFFLINE', None)
            with self.lock:
                if control['cancel'].is_set():
                    return
                module = {'analysis': 'backend.analysis_worker', 'waveform': 'backend.waveform_worker', 'export': 'backend.export_worker'}.get(job['kind'], 'backend.transcription_worker')
                process = spawn([sys.executable, '-X', 'utf8', '-m', module, str(work / 'request.json')],
                                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                **({'stdin': subprocess.PIPE} if job['kind'] == 'analysis' else {}),
                                text=True, encoding='utf-8', creationflags=NO_WINDOW)
                control['process'] = process
                if job['kind'] == 'analysis':
                    process.stdin.write(json.dumps({'credential': control['credential']}) + '\n')
                    process.stdin.close()
                    control['credential'] = ''
            last_saved, last_stage = 0, None
            for line in process.stdout:
                if control['cancel'].is_set():
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                fields = {k: v for k, v in event.items() if k in ('stage', 'progress', 'processed_seconds', 'segments', 'suggestions', 'stream', 'block', 'blocks', 'completed_units', 'total_units', 'unit')}
                if fields.get('progress') is not None:
                    fields['progress'] = min(99.9, max(job.get('progress') or 0, fields['progress']))
                current_time = time.monotonic()
                if current_time - last_saved >= .3 or event.get('stage') != last_stage:
                    self._update(control, **fields)
                    last_saved, last_stage = current_time, event.get('stage')
            process.wait()
            with self.lock:
                if control['cancel'].is_set():
                    return
                if process.returncode:
                    if job['kind'] == 'waveform':
                        raise ValueError('Falha ao decodificar waveform. Confira a mídia e o espaço em disco.')
                    if job['kind'] in ('analysis', 'export'):
                        error_file = work / 'error.json'
                        message = json.loads(error_file.read_text(encoding='utf-8'))['message'] if error_file.is_file() else 'O processo de análise foi interrompido por erro. Os resultados anteriores foram preservados.'
                        raise ValueError(message)
                    if job['kind'] == 'model_download':
                        raise ValueError('Falha no download ou validação do modelo. Verifique internet e espaço em disco e tente novamente.')
                    if job['options'].get('device') == 'cuda':
                        raise ValueError('Falha na execução CUDA. Verifique bibliotecas CUDA/cuDNN compatíveis ou selecione CPU. Nenhum driver foi alterado.')
                    raise ValueError('O motor de transcrição falhou. Verifique a mídia, o modelo local e o espaço em disco. A transcrição anterior foi preservada.')
                if job['kind'] == 'model_download':
                    target = model_directory(request['model'])
                    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
                    # Não sobrescreve instalações existentes, nem pastas incompletas desconhecidas.
                    if target.exists():
                        raise ValueError('Já existe uma pasta para este modelo. Verifique-a antes de tentar instalar novamente.')
                    os.replace(work / 'model', target)
                    if not installed_model(request['model']):
                        raise ValueError('O modelo baixado não passou na validação final.')
                elif job['kind'] == 'export':
                    check_unchanged(request['project'])
                    finalize_export(job)
                elif job['kind'] != 'waveform':
                    result = json.loads((work / 'result.json').read_text(encoding='utf-8'))
                    if job['kind'] == 'analysis':
                        validate_result(result, request['project'], job['options'])
                    else:
                        result['segments'] = normalize_segments(result['segments'], request['project']['metadata']['duration'])
                    write_json(cached, result)
                    self._apply(job, request['project'], result)
                self._update(control, status='completed', stage='completed', progress=100,
                             **({'suggestions': len(result['suggestions'])} if job['kind'] == 'analysis' else {'segments': len(result['segments']) if job['kind'] == 'transcription' else 0}))
        except Exception as exc:
            if not control['cancel'].is_set():
                failure = str(exc) if isinstance(exc, ValueError) else 'Erro ao processar tarefa local. Tente novamente; o projeto anterior foi preservado.'
                if job.get('publication_pending'):
                    failure = 'Os arquivos do lote foram publicados, mas o histórico não pôde ser registrado. Reinicie o serviço para recuperar o registro, sem exportar novamente.'
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
            if job['kind'] == 'export':
                try:
                    cleanup_stage(job)
                    job['cleanup_pending'] = False
                except OSError:
                    job['cleanup_pending'] = True
                    failure = (failure or 'Processamento encerrado.') + ' Não foi possível limpar a pasta temporária; a limpeza será repetida ao iniciar o serviço.'
            remove_work(work)
            with self.lock:
                control['process'] = None
                control['credential'] = ''
                if control['cancel'].is_set():
                    self._update(control, status='cancelled', stage='cancelled', error=failure if job.get('cleanup_pending') else None)
                elif failure:
                    self._update(control, status='failed', stage='failed', error=failure)

    def cancel(self, job_id):
        with self.lock:
            control = self.controls.get(job_id)
            if not control:
                return db.get_job(job_id)
            if control['job']['status'] in ACTIVE:
                control['cancel'].set()
                control['credential'] = ''
                process = control['process']
                if process is not None and process.poll() is None:
                    process.kill()
                self._update(control, status='cancelling' if process else 'cancelled', stage='cancelling' if process else 'cancelled')
            return dict(control['job'])

    def assert_editable(self, project_id, allow_waveform=False):
        with self.lock:
            if any(c['job'].get('project_id') == project_id and c['job']['status'] in ACTIVE and not (allow_waveform and c['job']['kind'] == 'waveform') for c in self.controls.values()):
                raise ValueError('Aguarde ou cancele o processamento antes de alterar faixas, substituir texto ou relocalizar a mídia.')

    def close(self):
        with self.lock:
            self.closed = True
            for job_id in list(self.controls):
                self.cancel(job_id)
        # Também aguarda tarefas enfileiradas para que cada uma limpe sua própria pasta.
        self.pool.shutdown(wait=True)
