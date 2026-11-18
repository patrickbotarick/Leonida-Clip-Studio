import copy
import json
import time

import numpy as np
import pytest

from backend import database as db
from backend.editing import EditCommand, edit_project, context_digest
from backend.media import binary
from backend.waveform import BASE, RATE, cache_path, generate, manifest, read_range


def edit(client, project, action, **fields):
    return client.post(f'/api/projects/{project["id"]}/cuts', json=dict(expected_revision=project['revision'], action=action, **fields))


def create(client, project, **fields):
    result = edit(client, project, 'create', start=fields.pop('start', .5), end=fields.pop('end', 2), **fields)
    assert result.status_code == 200, result.text
    return result.json()['project']


def test_review_edit_undo_redo_persistence_and_conflict(client, project):
    original = copy.deepcopy(project)
    project = create(client, project, title='Primeiro corte')
    cut = project['cuts'][0]
    assert cut['score'] is None and cut['confidence'] is None
    assert cut['status'] == 'pending'
    approved = edit(client, project, 'status', ids=[cut['id']], status='approved').json()['project']
    adjusted = edit(client, approved, 'update', ids=[cut['id']], end=3, note='Conferido no player').json()['project']
    assert adjusted['cuts'][0]['status'] == 'pending'
    assert adjusted['cuts'][0]['review_note'] == 'Conferido no player'
    assert edit(client, approved, 'delete', ids=[cut['id']]).status_code == 409
    undone = edit(client, adjusted, 'undo').json()['project']
    assert undone['cuts'] == approved['cuts']
    redone = edit(client, undone, 'redo').json()['project']
    assert redone['cuts'] == adjusted['cuts']
    assert db.get(project['id'])['cuts'] == redone['cuts']
    assert redone['path'] == original['path'] and redone['metadata'] == original['metadata']


@pytest.mark.parametrize('fields', [dict(start=-1,end=2),dict(start=3,end=2),dict(start=1,end=9),dict(start=1,end=1.001),dict(start=1,end=2,title='   ')])
def test_invalid_intervals_atomic(client, project, fields):
    assert edit(client, project, 'create', **fields).status_code == 422
    assert db.get(project['id']) == project


def test_split_merge_gaps_and_branch_history(client, project):
    project = create(client, project, start=0,end=4)
    old_id = project['cuts'][0]['id']
    split = edit(client, project, 'split', ids=[old_id], position=2).json()
    assert [(c['start'],c['end']) for c in split['project']['cuts']] == [(0,2),(2,4)]
    assert all(c['status']=='pending' and c['score'] is None for c in split['project']['cuts'])
    assert edit(client, split['project'], 'split', ids=[split['selected_ids'][0]], position=0).status_code==422
    merged = edit(client, split['project'], 'merge', ids=split['selected_ids']).json()['project']
    assert len(merged['cuts']) == 1
    project = create(client, merged, start=5,end=6)
    ids = [c['id'] for c in project['cuts']]
    assert edit(client, project, 'merge', ids=ids).status_code == 422
    merged = edit(client, project, 'merge', ids=ids,allow_gaps=True).json()['project']
    assert merged['cuts'][0]['included_gaps'] == [{'start':4,'end':5}]
    undone=edit(client, merged, 'undo').json()['project']
    branch=edit(client, undone, 'status',ids=ids,status='rejected').json()
    assert not branch['editor']['can_redo']


def test_archives_source_change_and_restore(client, project):
    project=create(client,project)
    cut_id=project['cuts'][0]['id']
    response=client.put(f'/api/projects/{project["id"]}/audio',json={'indices':[1]})
    next_project=response.json()
    assert next_project['cuts'][0]['id']==cut_id
    assert next_project['cuts'][0]['evidence_historical']
    state=client.get(f'/api/projects/{project["id"]}/editor').json()
    archive=state['archives'][0]
    assert not archive['compatible'] and not state['can_undo']
    assert edit(client,next_project,'restore',archive_id=archive['id']).status_code==422
    snapshot=client.get(f'/api/projects/{project["id"]}/cuts/archives/{archive["id"]}').json()
    assert snapshot['cuts']==project['cuts']
    next_project=client.put(f'/api/projects/{project["id"]}/audio',json={'indices':[]}).json()
    assert context_digest(next_project)==context_digest(project)
    restored=edit(client,next_project,'restore',archive_id=archive['id']).json()
    assert restored['project']['cuts']==project['cuts']
    assert not restored['editor']['can_undo']


def test_overlap_detection_and_optional_sentence_alignment(client, project):
    project['transcript']=[dict(id=0,start=0,end=3,text='Uma frase completa.')]
    project=db.save(project)
    project=create(client,project,start=.5,end=2,align_to_transcript=True)
    assert project['cuts'][0]['start']==0 and project['cuts'][0]['end']==3
    project=create(client,project,start=2,end=4)
    state=client.get(f'/api/projects/{project["id"]}/editor').json()
    assert set(state['overlap_ids'])=={c['id'] for c in project['cuts']}


def test_waveform_pcm_extrema_lod_and_bounded_range(client, project, tmp_path):
    request=dict(project=project,options={'index':2},work=str(tmp_path),ffmpeg=binary('ffmpeg'))
    assert generate(request,lambda **kw:None) is False
    info=manifest(project,2)
    assert info['samples']>RATE*5
    folder=cache_path(project,2)
    base=np.fromfile(folder/'0.bin',dtype='<f4').reshape(-1,2)
    assert np.all(base[:,0]<=base[:,1])
    assert base.min()<-.1 and base.max()>.1
    for level,count in enumerate(info['levels']):
        data=np.fromfile(folder/f'{level}.bin',dtype='<f4').reshape(-1,2)
        assert len(data)==count
        assert data[:,0].min()==base[:,0].min()
        assert data[:,1].max()==base[:,1].max()
    # Comparação com PCM decodificado independentemente, com os mesmos parâmetros.
    import subprocess
    pcm=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',project['path'],'-map','0:2','-ac','1','-ar',str(RATE),'-f','f32le','pipe:1'])
    decoded=np.frombuffer(pcm,dtype='<f4')[:BASE]
    assert np.allclose(base[0],[decoded.min(),decoded.max()],atol=1e-6)
    for points in (4,17,500,4000):
        result=read_range(project,2,.13,5.9,points)
        assert len(result['peaks'])<=points
    assert generate(request,lambda **kw:None) is True
    assert client.get(f'/api/projects/{project["id"]}/waveform/2/range?start=0&end=6&points=9000').status_code==422
    assert client.get(f'/api/projects/{project["id"]}/waveform/2/range?start=5&end=3').status_code==422


def test_waveform_job_does_not_change_project_revision(client, project):
    job=client.post(f'/api/projects/{project["id"]}/waveform',json={'index':1})
    assert job.status_code==202
    for _ in range(150):
        result=client.get('/api/processing/'+job.json()['id']).json()
        if result['status'] not in ('queued','running','cancelling'):break
        time.sleep(.03)
    assert result['status']=='completed',result
    assert db.get(project['id'])==project
    assert client.get(f'/api/projects/{project["id"]}/waveform/1').json()['ready']
    assert client.post(f'/api/projects/{project["id"]}/waveform',json={'index':99}).status_code==422


def test_two_hour_waveform_and_cancel_isolated_worker(client, tmp_path):
    import subprocess
    from backend.media import NO_WINDOW
    path=tmp_path/'waveform-duas-horas.mp4'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=black:s=16x16:r=1',
                    '-f','lavfi','-i','anullsrc=r=8000:cl=mono','-t','7205','-map','0:v','-map','1:a','-map','1:a',
                    '-c:v','libx264','-preset','ultrafast','-c:a','aac',str(path)],check=True,timeout=60,creationflags=NO_WINDOW)
    project=client.post('/api/projects',json={'path':str(path)}).json()
    assert project['metadata']['duration']>7200
    work=tmp_path/'work';work.mkdir()
    assert generate(dict(project=project,options={'index':1},work=str(work),ffmpeg=binary('ffmpeg')),lambda **kw:None) is False
    info=manifest(project,1)
    assert info['samples']>=RATE*7200
    assert read_range(project,1,7200,7204,4000)['peaks']
    assert len(read_range(project,1,0,7205,1000)['peaks'])<=1000
    assert sum(f.stat().st_size for f in cache_path(project,1).glob('*.bin'))<15_000_000
    started=client.post(f'/api/projects/{project["id"]}/waveform',json={'index':2}).json()
    for _ in range(100):
        job=client.get('/api/processing/'+started['id']).json()
        if job['stage']=='waveform':break
        time.sleep(.02)
    assert job['status']=='running',job
    assert client.put(f'/api/projects/{project["id"]}/audio',json={'indices':[1]}).status_code==422
    project=create(client,project,start=7200,end=7204)
    client.delete('/api/processing/'+started['id'])
    for _ in range(150):
        job=client.get('/api/processing/'+started['id']).json()
        if job['status']=='cancelled':break
        time.sleep(.02)
    assert job['status']=='cancelled',job
    assert manifest(project,2) is None
    assert db.get(project['id'])['cuts']==project['cuts']


def test_bounded_history_and_atomic_bad_selection(client, project):
    project=create(client,project)
    cut=project['cuts'][0]
    assert edit(client,project,'status',ids=[cut['id'],'missing'],status='approved').status_code==422
    assert db.get(project['id'])==project
    for index in range(103):
        project=edit_project(project['id'],EditCommand(expected_revision=project['revision'],action='update',ids=[cut['id']],note=str(index)))['project']
    with db.connect() as connection:
        assert connection.execute('SELECT count(*) FROM cut_history WHERE project_id=?',(project['id'],)).fetchone()[0]==100
    for _ in range(100):
        project=edit_project(project['id'],EditCommand(expected_revision=project['revision'],action='undo'))['project']
    assert edit(client,project,'undo').status_code==422
