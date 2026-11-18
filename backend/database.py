import json
import sqlite3
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from .config import DATA


class RevisionConflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    db = sqlite3.connect(DATA / 'projects.sqlite3', timeout=15)
    try:
        with db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS processing_jobs (id TEXT PRIMARY KEY, project_id TEXT, kind TEXT NOT NULL, status TEXT NOT NULL, document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS cut_history (project_id TEXT NOT NULL, seq INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(project_id,seq))')
            db.execute('CREATE TABLE IF NOT EXISTS cut_archives (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, created_at TEXT NOT NULL, reason TEXT NOT NULL, cut_count INTEGER NOT NULL, source_digest TEXT NOT NULL, document BLOB NOT NULL)')
            yield db
    finally:
        db.close()


def save(project, cut_archive=None):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT document FROM projects WHERE id=?', (project['id'],)).fetchone()
        revision = json.loads(previous['document']).get('revision', 0) if previous else 0
        if previous and project.get('revision', 0) != revision:
            raise ValueError('O projeto foi alterado em outra operação. Reabra-o antes de tentar novamente.')
        project.update(updated_at=now(), revision=revision + 1, schema_version=1)
        if cut_archive:
            store_cut_archive(db, cut_archive)
        _write(db, project)
    return project


def _write(db, project):
    db.execute('INSERT INTO projects VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at, document=excluded.document',
               (project['id'], project['name'], project['created_at'], project['updated_at'], json.dumps(project, ensure_ascii=False, allow_nan=False)))


def update(project_id, transform, expected_revision=None, transaction_hook=None):
    """Atualiza o documento atual em uma transação, sem sobrescrever trabalho concorrente."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT document FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise KeyError('Projeto não encontrado.')
        project = json.loads(row['document'])
        revision = project.get('revision', 0)
        if expected_revision is not None and revision != expected_revision:
            raise RevisionConflict('O projeto mudou. Reabra-o para carregar a revisão atual; seus dados salvos foram preservados.')
        transform(project)
        project.update(updated_at=now(), revision=revision + 1, schema_version=1)
        if transaction_hook:
            transaction_hook(db, project)
        _write(db, project)
    return project


def capture_cuts(project, reason):
    if not project.get('cuts'):
        return None
    from .editing import context_digest
    return dict(project_id=project['id'], project_name=project['name'], reason=reason, created_at=now(),
                source_digest=context_digest(project), path=project['path'], metadata=project['metadata'],
                cuts=project['cuts'], analysis_options=(project.get('analysis') or {}).get('options'))


def store_cut_archive(connection, snapshot):
    if snapshot:
        payload = zlib.compress(json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        connection.execute('INSERT INTO cut_archives (project_id,created_at,reason,cut_count,source_digest,document) VALUES (?,?,?,?,?,?)',
                           (snapshot['project_id'], snapshot['created_at'], snapshot['reason'], len(snapshot['cuts']), snapshot['source_digest'], payload))


def list_cut_archives(project_id):
    with connect() as connection:
        rows = connection.execute('SELECT id,created_at,reason,cut_count,source_digest FROM cut_archives WHERE project_id=? ORDER BY id DESC LIMIT 50', (project_id,)).fetchall()
    return [dict(row) for row in rows]


def get_cut_archive(project_id, archive_id):
    with connect() as connection:
        row = connection.execute('SELECT document FROM cut_archives WHERE project_id=? AND id=?', (project_id, archive_id)).fetchone()
    if not row:
        raise KeyError('Conjunto anterior de cortes não encontrado.')
    return json.loads(zlib.decompress(row['document']).decode('utf-8'))


def reset_cut_history(connection, project):
    connection.execute('DELETE FROM cut_history WHERE project_id=?', (project['id'],))
    project['editor_cursor'] = 0


def save_job(job):
    with connect() as db:
        db.execute('INSERT INTO processing_jobs VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, document=excluded.document',
                   (job['id'], job.get('project_id'), job['kind'], job['status'], json.dumps(job, ensure_ascii=False, allow_nan=False)))


def get_job(job_id):
    with connect() as db:
        row = db.execute('SELECT document FROM processing_jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        raise KeyError('Tarefa não encontrada.')
    return json.loads(row['document'])


def record_export(job):
    """Registro idempotente do lote e da tarefa concluída, sem substituir outros campos."""
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT document FROM projects WHERE id=?', (job['project_id'],)).fetchone()
        if not row:
            raise KeyError('Projeto não encontrado ao registrar exportação.')
        project = json.loads(row['document'])
        history = project.setdefault('exports', [])
        if not any(item['id'] == job['id'] for item in history):
            history.append(dict(id=job['id'], created_at=job['created_at'], folder=job['export_folder'],
                                revision=job['options']['expected_revision'], cut_count=job['cut_count'], formats=job['options']['formats']))
            project.update(updated_at=now(), revision=project.get('revision', 0) + 1)
            _write(connection, project)
        connection.execute('INSERT INTO processing_jobs VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,document=excluded.document',
                           (job['id'], job['project_id'], job['kind'], job['status'], json.dumps(job, ensure_ascii=False, allow_nan=False)))
    return project


def list_jobs(project_id=None, limit=30):
    with connect() as db:
        if project_id:
            rows = db.execute('SELECT document FROM processing_jobs WHERE project_id=? ORDER BY rowid DESC LIMIT ?', (project_id, limit)).fetchall()
        else:
            rows = db.execute('SELECT document FROM processing_jobs ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
    return [json.loads(r['document']) for r in rows]


def interrupted_jobs():
    with connect() as db:
        rows = db.execute("SELECT document FROM processing_jobs WHERE status IN ('queued','running','cancelling') OR json_extract(document,'$.cleanup_pending')=1 OR json_extract(document,'$.publication_pending')=1").fetchall()
    return [json.loads(r['document']) for r in rows]


def create(name, path, metadata):
    return save(dict(id=uuid4().hex, name=name, path=str(path), metadata=metadata,
                     selected_audio=[], transcript=[], cuts=[], settings={'profile': 'economico', 'device': 'cpu'},
                     exports=[], created_at=now()))


def get(project_id):
    with connect() as db:
        row = db.execute('SELECT document FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row:
        raise KeyError('Projeto não encontrado.')
    return json.loads(row['document'])


def recent():
    with connect() as db:
        rows = db.execute('SELECT document FROM projects ORDER BY updated_at DESC').fetchall()
    return [json.loads(row['document']) for row in rows]


def summaries():
    """Dashboard não materializa transcrições longas de todos os projetos."""
    with connect() as db:
        rows = db.execute("SELECT id,name,updated_at,json_extract(document,'$.path') AS path,json_extract(document,'$.metadata') AS metadata,json_array_length(document,'$.transcript') AS transcript_count FROM projects ORDER BY updated_at DESC").fetchall()
    return [dict(id=r['id'], name=r['name'], updated_at=r['updated_at'], path=r['path'],
                 metadata=json.loads(r['metadata']), transcript_count=r['transcript_count'] or 0) for r in rows]
