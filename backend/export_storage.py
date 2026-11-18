"""Publicação e limpeza restritas aos lotes exclusivos criados pelo aplicativo."""
import json
import os
from pathlib import Path
import re
import shutil

from . import database as db


def cleanup_stage(job):
    if not re.fullmatch('[a-f0-9]{32}', job['id']) or not job.get('export_stage'):
        return
    folder = Path(job['export_stage'])
    expected = f'.leonida-{job["id"]}.partial'
    if folder.name != expected or folder.is_symlink() or not folder.exists() or folder.resolve() != folder.parent.resolve() / expected:
        return
    marker = folder / '.leonida-owner'
    if marker.is_file() and marker.read_text(encoding='ascii') == job['id']:
        shutil.rmtree(folder)
    elif not any(folder.iterdir()):
        folder.rmdir()


def published_result(job):
    folder = Path(job['export_folder'])
    data = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
    if data['export_id'] != job['id'] or data['project_id'] != job['project_id']:
        raise ValueError('Manifesto de exportação incompatível.')
    files = [f['name'] for f in data['files']] + ['manifesto.json']
    for name in files:
        if Path(name).name != name or not (folder / name).is_file() or (folder / name).is_symlink():
            raise ValueError('Arquivo do lote ausente ou inválido.')
    if any((folder / f['name']).stat().st_size != f['bytes'] for f in data['files']):
        raise ValueError('Arquivo do lote incompleto: tamanho diferente do manifesto.')
    return dict(files=files, warnings=data['warnings'], cut_count=len(data['cuts']))


def finalize_export(job):
    stage, target = Path(job['export_stage']), Path(job['export_folder'])
    if target.exists():
        raise ValueError('A pasta final deste lote já existe. Nada foi sobrescrito.')
    result = published_result({**job, 'export_folder': str(stage)})
    os.rename(stage, target)  # No Windows, falha caso o destino exista; pasta no mesmo volume.
    job.update(**result, status='completed', stage='completed', progress=100, updated_at=db.now(), publication_pending=True)
    db.record_export(job)
    job['publication_pending'] = False


def recover_export(job):
    try:
        result = published_result(job)
    except (OSError, ValueError, KeyError, TypeError):
        try:
            cleanup_stage(job)
            job['cleanup_pending'] = False
        except OSError:
            job['cleanup_pending'] = True
        return False
    job.update(**result, status='completed', stage='completed', progress=100, updated_at=db.now(),
               recovery_note='Lote publicado recuperado após interrupção do serviço.', publication_pending=False)
    db.record_export(job)
    try:
        cleanup_stage(job)
        job['cleanup_pending'] = False
    except OSError:
        job['cleanup_pending'] = True
    db.save_job(job)
    return True
