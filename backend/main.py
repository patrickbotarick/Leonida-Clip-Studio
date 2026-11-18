import csv
import io
import json
import os
import platform
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import database as db
from .config import ROOT, VERSION
from .jobs import PreviewQueue
from .media import NO_WINDOW, binary, check_unchanged, probe, source_path
from .transcripts import parse, srt
from .processes import run
from .processing import ProcessingQueue
from .transcription import TranscriptionOptions, capabilities
from .analysis import AnalysisRequest, PROFILES, PURPOSES, transcript_blocks
from .editing import EditCommand, edit_project, editor_state, retained_cuts
from .waveform import manifest, read_range
from .exports import ExportOptions, plan_export


@asynccontextmanager
async def lifespan(app):
    app.state.queue = PreviewQueue()
    app.state.processing = ProcessingQueue()
    yield
    app.state.processing.close()
    app.state.queue.close()


app = FastAPI(title='Leonida Clip Studio', version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])


@app.middleware('http')
async def local_guard(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        origin = request.headers.get('origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != request.url.scheme or parsed.netloc != request.headers.get('host'):
                return JSONResponse({'detail': 'Origem não autorizada.'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('x-leonida-client') != '1':
            return JSONResponse({'detail': 'Requisição local inválida.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=422)


@app.exception_handler(db.RevisionConflict)
async def conflict(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.get('/api/projects/{project_id}/editor')
def get_editor(project_id: str):
    return editor_state(db.get(project_id))


@app.post('/api/projects/{project_id}/exports/plan')
def export_plan(project_id: str, body: ExportOptions):
    return plan_export(db.get(project_id), body)


@app.post('/api/projects/{project_id}/exports', status_code=202)
def start_export(project_id: str, body: ExportOptions, request: Request):
    return request.app.state.processing.export(db.get(project_id), body)


@app.get('/api/projects/{project_id}/exports')
def export_history(project_id: str):
    return db.get(project_id).get('exports', [])


@app.get('/api/exports/{job_id}/files/{filename}')
def export_file(job_id: str, filename: str):
    job = db.get_job(job_id)
    if job['kind'] != 'export' or job['status'] != 'completed' or filename not in job.get('files', []):
        raise HTTPException(404, 'Arquivo não publicado neste lote.')
    root = Path(job['export_folder']).resolve()
    path = (root / filename).resolve()
    if Path(filename).name != filename or not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, 'Arquivo exportado indisponível.')
    return FileResponse(path, filename=filename)


@app.post('/api/dialog/directory')
def directory_dialog():
    if os.name != 'nt':
        raise HTTPException(409, 'Cole o caminho absoluto da pasta de destino.')
    script = """Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Leonida Clip Studio — Pasta de destino das exportações'
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
try { if ($dialog.ShowDialog($owner) -eq 'OK') { [Console]::Write($dialog.SelectedPath) } } finally { $dialog.Dispose(); $owner.Dispose() }
"""
    try:
        result = run(['powershell.exe', '-NoProfile', '-STA', '-Command', script], timeout=120, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Seleção de pasta expirou. Cole o caminho absoluto.') from exc
    if result.returncode:
        raise ValueError('Não foi possível abrir o seletor de pasta. Cole o caminho absoluto.')
    return dict(path=result.stdout.decode('utf-8-sig').strip())


@app.post('/api/projects/{project_id}/cuts')
def edit_cuts(project_id: str, body: EditCommand, request: Request):
    request.app.state.processing.assert_editable(project_id, allow_waveform=True)
    return edit_project(project_id, body)


@app.get('/api/projects/{project_id}/cuts/archives/{archive_id}')
def export_cut_archive(project_id: str, archive_id: int):
    content = json.dumps(db.get_cut_archive(project_id, archive_id), ensure_ascii=False, indent=2)
    return Response(content, media_type='application/json', headers={'Content-Disposition': 'attachment; filename="historico-cortes.json"'})


@app.exception_handler(FileNotFoundError)
async def missing_file(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.exception_handler(KeyError)
async def missing(request, exc):
    return JSONResponse({'detail': str(exc).strip("'")}, status_code=404)


class ImportMedia(BaseModel):
    path: str = Field(min_length=1, max_length=32768)
    name: str = Field(default='', max_length=160)


class Selection(BaseModel):
    indices: list[int] = Field(max_length=64)


class Preview(BaseModel):
    index: int
    start: float = Field(default=0, ge=0, allow_inf_nan=False)


class ModelDownload(BaseModel):
    model: str = Field(max_length=16)
    consent: bool = False


class WaveformRequest(BaseModel):
    index: int


@app.post('/api/projects/{project_id}/waveform', status_code=202)
def generate_waveform(project_id: str, body: WaveformRequest, request: Request):
    return request.app.state.processing.waveform(db.get(project_id), body.index)


@app.get('/api/projects/{project_id}/waveform/{index}')
def waveform_status(project_id: str, index: int):
    return dict(ready=bool(manifest(db.get(project_id), index)))


@app.get('/api/projects/{project_id}/waveform/{index}/range')
def waveform_range(project_id: str, index: int, start: float = Query(ge=0, allow_inf_nan=False),
                   end: float = Query(gt=0, allow_inf_nan=False), points: int = Query(default=1200, ge=4, le=4000)):
    return read_range(db.get(project_id), index, start, end, points)


@app.get('/api/analysis/capabilities')
def analysis_capabilities():
    return dict(providers=['local', 'openai', 'ollama'], content_profiles=PROFILES, purposes=PURPOSES,
                score_note='Estimativa editorial/heurística, sem garantia de engajamento.', visual_analysis=False)


@app.get('/api/projects/{project_id}/analysis/plan')
def analysis_plan(project_id: str):
    project = db.get(project_id)
    try:
        count = len(list(transcript_blocks(project['transcript'])))
    except ValueError:
        count = None
    return dict(transcript_segments=len(project['transcript']), characters=sum(len(r['text']) for r in project['transcript']),
                provider_blocks=count, selected_audio=project['selected_audio'], duration=project['metadata']['duration'])


@app.post('/api/projects/{project_id}/analyze', status_code=202)
def analyze(project_id: str, body: AnalysisRequest, request: Request):
    return request.app.state.processing.analyze(db.get(project_id), body.model_dump(), body.api_key.get_secret_value())


@app.get('/api/projects/{project_id}/analysis/export')
def export_analysis(project_id: str):
    project = db.get(project_id)
    if not project.get('analysis'):
        raise HTTPException(409, 'Projeto ainda sem análise.')
    content = json.dumps({'project': project['name'], 'analysis': project['analysis'], 'suggestions': project['cuts']}, ensure_ascii=False, indent=2)
    return Response(content, media_type='application/json', headers={'Content-Disposition': 'attachment; filename="decupagem-analise.json"'})


@app.get('/api/transcription/capabilities')
def transcription_capabilities():
    return capabilities()


@app.post('/api/transcription/models', status_code=202)
def download_model(body: ModelDownload, request: Request):
    return request.app.state.processing.download(body.model, body.consent)


@app.post('/api/projects/{project_id}/transcribe', status_code=202)
def transcribe(project_id: str, body: TranscriptionOptions, request: Request):
    return request.app.state.processing.transcribe(db.get(project_id), body.model_dump())


@app.get('/api/processing')
def processing_jobs(project_id: str | None = None):
    if project_id:
        db.get(project_id)
    return db.list_jobs(project_id)


@app.get('/api/processing/{job_id}')
def processing_job(job_id: str):
    return db.get_job(job_id)


@app.delete('/api/processing/{job_id}')
def cancel_processing(job_id: str, request: Request):
    return request.app.state.processing.cancel(job_id)


@app.get('/api/health')
def health():
    return {'name': 'Leonida Clip Studio', 'version': VERSION, 'status': 'ok'}


@app.get('/api/environment')
def environment():
    gpu = None
    try:
        result = run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
                     text=True, timeout=4, creationflags=NO_WINDOW)
        if result.returncode == 0:
            gpu = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return dict(system=platform.platform(), python=platform.python_version(), logical_cpus=os.cpu_count(),
                ffmpeg=bool(binary('ffmpeg')), ffprobe=bool(binary('ffprobe')), gpu=gpu,
                recommended=dict(device='cpu', profile='econômico', threads=2, whisper='tiny/base int8'),
                cuda_validated=False, version=VERSION)


@app.get('/api/projects')
def projects():
    return [{**p, 'available': Path(p['path']).is_file()} for p in db.summaries()]


@app.post('/api/projects', status_code=201)
def import_media(body: ImportMedia):
    path = source_path(body.path)
    return db.create(body.name.strip() or path.stem, path, probe(path))


@app.get('/api/projects/{project_id}')
def project(project_id: str):
    p = db.get(project_id)
    p['available'] = Path(p['path']).is_file()
    return p


@app.post('/api/projects/{project_id}/relink')
def relink(project_id: str, body: ImportMedia, request: Request):
    request.app.state.processing.assert_editable(project_id)
    p = db.get(project_id)
    path = source_path(body.path)
    meta = probe(path)
    original = p['metadata']
    archive = db.capture_cuts(p, 'media_changed')
    # Mantém transcrições somente para um arquivo idêntico movido (tamanho e mtime).
    same = all(meta[k] == original[k] for k in ('size', 'mtime_ns', 'duration'))
    p.update(path=str(path), metadata=meta)
    if not same:
        p.update(transcript=[], cuts=[], selected_audio=[])
        p.pop('transcript_source', None)
        p.pop('transcript_info', None)
        p['analysis'] = None
    return db.save(p, cut_archive=archive if not same else None)


@app.put('/api/projects/{project_id}/audio')
def select_audio(project_id: str, body: Selection, request: Request):
    request.app.state.processing.assert_editable(project_id)
    p = db.get(project_id)
    available = {a['index'] for a in p['metadata']['audio']}
    if not set(body.indices) <= available:
        raise ValueError('Seleção contém faixas inexistentes.')
    archive = None
    if p['selected_audio'] != sorted(set(body.indices)):
        archive = db.capture_cuts(p, 'audio_changed')
        p.update(cuts=retained_cuts(p, invalidate=True), analysis=None)
    p['selected_audio'] = sorted(set(body.indices))
    return db.save(p, cut_archive=archive)


@app.get('/api/projects/{project_id}/media')
def media(project_id: str):
    p = db.get(project_id)
    return FileResponse(check_unchanged(p))


@app.post('/api/projects/{project_id}/preview', status_code=202)
def preview(project_id: str, body: Preview, request: Request):
    return request.app.state.queue.submit(db.get(project_id), body.index, body.start)


@app.get('/api/jobs/{job_id}')
def job(job_id: str, request: Request):
    return request.app.state.queue.public(request.app.state.queue.get(job_id))


@app.delete('/api/jobs/{job_id}')
def cancel(job_id: str, request: Request):
    return request.app.state.queue.cancel(job_id)


@app.get('/api/jobs/{job_id}/audio')
def preview_audio(job_id: str, request: Request):
    j = request.app.state.queue.get(job_id)
    if j['status'] != 'completed':
        raise HTTPException(409, 'Prévia ainda não disponível.')
    return FileResponse(j['target'], media_type='audio/mp4')


@app.post('/api/projects/{project_id}/transcript')
def import_transcript(project_id: str, request: Request, file: UploadFile = File(...)):
    request.app.state.processing.assert_editable(project_id)
    p = db.get(project_id)
    # A mídia nunca passa por upload. Apenas texto externo, limitado a 10 MiB.
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Transcrição excede 10 MiB.')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('cp1252')
    archive = db.capture_cuts(p, 'transcript_import')
    p['transcript'] = parse(text, Path(file.filename or '').suffix.lower(), p['metadata']['duration'], p['metadata']['fps'])
    p['transcript_source'] = Path(file.filename or '').name
    p.pop('transcript_info', None)
    p.update(cuts=retained_cuts(p, invalidate=True), analysis=None)
    return db.save(p, cut_archive=archive)


@app.get('/api/projects/{project_id}/transcript/{format}')
def export_transcript(project_id: str, format: str):
    p = db.get(project_id)
    rows = p['transcript']
    if not rows:
        raise HTTPException(409, 'Projeto sem transcrição.')
    if format == 'json':
        content, mime = json.dumps(rows, ensure_ascii=False, indent=2), 'application/json'
    elif format == 'srt':
        content, mime = srt(rows), 'application/x-subrip'
    elif format == 'txt':
        content, mime = '\n'.join(f'[{r["start"]:.3f} - {r["end"]:.3f}] {r["text"]}' for r in rows), 'text/plain'
    elif format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['Start', 'End', 'Text'])
        writer.writerows((r['start'], r['end'], "'" + r['text'] if r['text'].startswith(('=', '+', '-', '@')) else r['text']) for r in rows)
        content, mime = '\ufeff' + output.getvalue(), 'text/csv'
    else:
        raise HTTPException(404, 'Formato não suportado.')
    return Response(content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="transcricao.{format}"'})


@app.post('/api/dialog')
def dialog():
    if os.name != 'nt':
        raise HTTPException(409, 'Seletor nativo disponível no Windows. Cole o caminho absoluto.')
    script = """Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Leonida Clip Studio — Selecionar vídeo original'
$dialog.Filter = 'Vídeos|*.mp4;*.mkv;*.mov;*.webm'
$dialog.CheckFileExists = $true
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
try { if ($dialog.ShowDialog($owner) -eq 'OK') { [Console]::Write($dialog.FileName) } } finally { $dialog.Dispose(); $owner.Dispose() }
"""
    try:
        result = run(['powershell.exe', '-NoProfile', '-STA', '-Command', script],
                     timeout=120, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Seleção de arquivo expirou. Tente novamente ou cole o caminho absoluto.') from exc
    if result.returncode:
        raise ValueError('Não foi possível abrir o seletor. Cole o caminho absoluto no campo.')
    return {'path': result.stdout.decode('utf-8-sig').strip()}


dist = ROOT / 'frontend' / 'dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
