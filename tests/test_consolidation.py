import json
from pathlib import Path
from uuid import uuid4

import pytest

from backend import database as db
from backend.export_storage import cleanup_stage, published_result, recover_export


def test_recovery_rejects_truncated_published_file(tmp_path):
    folder=tmp_path/'published';folder.mkdir()
    (folder/'clip.mp4').write_bytes(b'truncated')
    job=dict(id=uuid4().hex,project_id='test',export_folder=str(folder))
    (folder/'manifesto.json').write_text(json.dumps(dict(export_id=job['id'],project_id='test',files=[dict(name='clip.mp4',bytes=200)],warnings=[],cuts=[])))
    with pytest.raises(ValueError,match='tamanho diferente'):published_result(job)
    assert (folder/'clip.mp4').read_bytes()==b'truncated'


def test_locked_staging_is_recorded_for_retry(monkeypatch,tmp_path):
    from backend import export_storage
    job=dict(id=uuid4().hex,project_id='test',export_folder=str(tmp_path/'missing'))
    def denied(_):raise PermissionError('Arquivo bloqueado pelo sistema.')
    monkeypatch.setattr(export_storage,'cleanup_stage',denied)
    assert recover_export(job) is False
    assert job['cleanup_pending'] is True


def test_publication_failure_is_recoverable_even_after_failed_status(client,project,monkeypatch,tmp_path):
    from backend.editing import EditCommand,edit_project
    from backend.exports import ExportOptions,plan_export
    from backend.processing import ProcessingQueue
    import time
    result=edit_project(project['id'],EditCommand(expected_revision=project['revision'],action='create',start=1,end=3))
    project=edit_project(project['id'],EditCommand(expected_revision=result['project']['revision'],action='status',ids=result['selected_ids'],status='approved'))['project']
    body=dict(expected_revision=project['revision'],formats=['json'],destination=str(tmp_path))
    plan=plan_export(project,ExportOptions(**body))
    original=db.record_export
    def fail(_):raise OSError('Falha de escrita do registro após publicação.')
    monkeypatch.setattr(db,'record_export',fail)
    job=client.post(f'/api/projects/{project["id"]}/exports',json={**body,'plan_token':plan['token']}).json()
    for _ in range(300):
        saved=db.get_job(job['id'])
        if saved['status']=='failed':break
        time.sleep(.01)
    assert saved['status']=='failed' and saved['publication_pending']
    assert (Path(saved['export_folder'])/'manifesto.json').is_file()
    assert db.get(project['id'])['exports']==[]
    monkeypatch.setattr(db,'record_export',original)
    queue=ProcessingQueue()
    try:
        assert db.get_job(job['id'])['status']=='completed'
        assert not db.get_job(job['id'])['publication_pending']
        assert len(db.get(project['id'])['exports'])==1
    finally:queue.close()


def test_cleanup_never_follows_directory_symlink(tmp_path):
    # A guarda de nome impede qualquer remoção de uma pasta vizinha, mesmo com marcador.
    target=tmp_path/'real-user-folder';target.mkdir()
    job=dict(id=uuid4().hex,export_stage=str(target))
    (target/'.leonida-owner').write_text(job['id'])
    cleanup_stage(job)
    assert target.is_dir()
