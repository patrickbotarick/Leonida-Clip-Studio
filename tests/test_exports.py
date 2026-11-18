import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import pytest
import av
import numpy as np

from backend import database as db
from backend.editing import EditCommand, edit_project
from backend.exports import ExportOptions, frame_rate, layout, plan_export, remap_segments, safe_name
from backend.media import binary, NO_WINDOW
from backend.premiere_xml import build_xml


@pytest.fixture
def approved(project):
    project['transcript'] = [dict(id=1, start=0, end=2, text='Uma fala antes e durante.'),
                             dict(id=2, start=2, end=4, text='Uma frase que cruza a borda.'),
                             dict(id=3, start=4, end=6, text='Uma fala no segundo corte.')]
    project = db.save(project)
    for a, b, title in [(1.101, 2.803, 'CON: "primeiro" / ?'), (4.104, 5.806, '=Segundo teste')]:
        result = edit_project(project['id'], EditCommand(expected_revision=project['revision'], action='create', start=a, end=b, title=title))
        project = result['project']
    project = edit_project(project['id'], EditCommand(expected_revision=project['revision'], action='status', ids=[c['id'] for c in project['cuts']], status='approved'))['project']
    return project


def options(project, **values):
    return dict(expected_revision=project['revision'], formats=['mp4','xml','csv','json','txt','srt'], audio_indices=[2,1], confirm_cfr=True, **values)


def start(client, project, **values):
    body=options(project, **values)
    plan=client.post(f'/api/projects/{project["id"]}/exports/plan',json=body)
    assert plan.status_code==200,plan.text
    response=client.post(f'/api/projects/{project["id"]}/exports',json={**body,'plan_token':plan.json()['token']})
    assert response.status_code==202,response.text
    return response.json(),plan.json()


def wait(client, job):
    for _ in range(600):
        result=client.get('/api/processing/'+job['id']).json()
        if result['status'] not in ('queued','running','cancelling'):return result
        time.sleep(.025)
    pytest.fail('Exportação excedeu o prazo de teste.')


def test_precise_batch_real_mp4_reports_subtitles_and_history(client, approved):
    before=copy.deepcopy(approved)
    source_hash=hashlib.sha256(Path(approved['path']).read_bytes()).hexdigest()
    job,plan=start(client,approved)
    job=wait(client,job)
    assert job['status']=='completed',job
    assert job['completed_units']==job['total_units']==2
    folder=Path(job['export_folder'])
    assert not Path(job['export_stage']).exists()
    assert sorted(job['files'])==sorted(plan['files'])
    assert all((folder/f).is_file() for f in plan['files'])
    manifest=json.loads((folder/'manifesto.json').read_text(encoding='utf-8'))
    for row in plan['rows']:
        c=row['cut']; file=folder/(row['name']+'.mp4')
        data=json.loads(subprocess.check_output([binary('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(file)],creationflags=NO_WINDOW))
        video=next(s for s in data['streams'] if s['codec_type']=='video')
        audio=[s for s in data['streams'] if s['codec_type']=='audio']
        assert video['codec_name']=='h264' and (video['width'],video['height'])==(320,180)
        assert Fraction(video['avg_frame_rate'])==Fraction(30000,1001)
        assert len(audio)==2
        assert abs(float(data['format']['duration'])-c['duration'])<.08
        assert abs(float(video.get('start_time',0)))<.05
        assert manifest['rendered'][c['id']]['method']=='precise'
        assert (folder/(row['name']+'.srt')).read_text(encoding='utf-8').startswith('1\n00:00:00,')
    # Compara os quadros de borda decodificados com a origem, com tolerância da recodificação.
    row=plan['rows'][0]; movie=folder/(row['name']+'.mp4')
    source_frames={}
    expected_first=33; expected_last=84
    with av.open(approved['path']) as source:
        for index,frame in enumerate(source.decode(video=0)):
            if index in (expected_first,expected_last):source_frames[index]=frame.to_ndarray(format='rgb24').astype(float)
    first_frame=last_frame=None
    with av.open(str(movie)) as output:
        for frame in output.decode(video=0):
            image=frame.to_ndarray(format='rgb24').astype(float)
            if first_frame is None:first_frame=image
            last_frame=image
    assert np.abs(first_frame-source_frames[expected_first]).mean()<4
    assert np.abs(last_frame-source_frames[expected_last]).mean()<4
    # Verifica a identidade e ordem das duas faixas, sem depender só da contagem.
    for audio_index,frequency in [(0,880),(1,440)]:
        pcm=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(movie),'-map',f'0:a:{audio_index}',
                                     '-ac','1','-ar','8000','-f','f32le','pipe:1'],creationflags=NO_WINDOW)
        data=np.frombuffer(pcm,dtype='<f4'); n=min(len(data),8000)
        spectrum=np.abs(np.fft.rfft(data[:n]*np.hanning(n)))
        dominant=np.fft.rfftfreq(n,1/8000)[spectrum.argmax()]
        assert abs(dominant-frequency)<3
    saved=db.get(approved['id'])
    assert saved['cuts']==before['cuts'] and saved['transcript']==before['transcript']
    assert len(saved['exports'])==1 and saved['revision']==before['revision']+1
    assert client.get(f'/api/projects/{approved["id"]}/exports').json()[0]['id']==job['id']
    assert hashlib.sha256(Path(approved['path']).read_bytes()).hexdigest()==source_hash
    assert '\ufeff'==(folder/'decupagem.csv').read_text(encoding='utf-8')[0]
    assert "'=Segundo teste" in (folder/'decupagem.csv').read_text(encoding='utf-8')
    assert client.get(f'/api/exports/{job["id"]}/files/decupagem.json').status_code==200
    assert client.get(f'/api/exports/{job["id"]}/files/.leonida-owner').status_code==404
    assert client.get(f'/api/exports/{job["id"]}/files/unknown').status_code==404
    # Repetir a exportação cria outra pasta, sem tocar na primeira.
    other,_=start(client,saved)
    assert wait(client,other)['status']=='completed'
    assert other['export_folder']!=job['export_folder']


def test_xml_rational_timebase_source_channels_and_modes(approved):
    for mode in ('compact','original'):
        opts=ExportOptions(**options(approved,sequence_mode=mode))
        plan=plan_export(approved,opts)
        root=ET.fromstring(build_xml(approved,plan))
        seq=root.find('sequence')
        assert root.attrib=={'version':'5'}
        assert seq.findtext('rate/timebase')=='30' and seq.findtext('rate/ntsc')=='TRUE'
        clips=seq.findall('media/video/track/clipitem')
        assert len(clips)==2
        assert [int(c.findtext('in')) for c in clips]==[33,123]
        assert [int(c.findtext('out')) for c in clips]==[84,174]
        assert [int(c.findtext('start')) for c in clips]==([0,51] if mode=='compact' else [33,123])
        assert all(int(c.findtext('end'))-int(c.findtext('start'))==int(c.findtext('out'))-int(c.findtext('in')) for c in clips)
        pathurl=root.find('.//file/pathurl').text
        assert pathurl.startswith('file:///') and '%20' in pathurl
        assert len(root.findall('.//marker'))==2
        assert len(root.findall('.//file/pathurl'))==1
        assert [t.findtext('clipitem/sourcetrack/trackindex') for t in seq.findall('media/audio/track')]==['2','1']
        ids={c.attrib['id'] for c in root.findall('.//clipitem')}
        assert all(link.text in ids for link in root.findall('.//linkclipref'))


def test_subtitles_clamp_crossing_and_remap_gap_or_compact(approved):
    cuts=approved['cuts']
    first=remap_segments(approved['transcript'],cuts[0]['start'],cuts[0]['end'])
    assert first[0]['start']==0 and first[-1]['end']==pytest.approx(cuts[0]['duration'])
    compact=[]
    for row in layout(cuts,'compact'):
        compact.extend(remap_segments(approved['transcript'],row['source_in'],row['source_out'],row['timeline_in']))
    assert compact[-1]['start']==pytest.approx(cuts[0]['duration'])
    assert compact[-1]['end']==pytest.approx(sum(c['duration'] for c in cuts))
    assert remap_segments([dict(start=10,end=11,text='fora')],1,2)==[]


@pytest.mark.parametrize('change',[{'formats':[]},{'audio_indices':[999]},{'ids':['missing']},{'method':'fast'},{'confirm_cfr':False},{'destination':'relative'},{'formats':['xml','xml']}])
def test_invalid_plan_no_side_effects(client,approved,change):
    body={**options(approved),**change}
    response=client.post(f'/api/projects/{approved["id"]}/exports/plan',json=body)
    assert response.status_code==422,response.text
    assert db.get(approved['id'])==approved


def test_pending_rejected_and_stale_revision_are_never_exported(client,approved):
    project=edit_project(approved['id'],EditCommand(expected_revision=approved['revision'],action='status',ids=[approved['cuts'][0]['id']],status='rejected'))['project']
    assert client.post(f'/api/projects/{approved["id"]}/exports/plan',json=options(approved)).status_code==409
    plan=plan_export(project,ExportOptions(**options(project)))
    assert len(plan['cuts'])==1
    assert client.post(f'/api/projects/{approved["id"]}/exports',json=options(project)).status_code==422
    assert client.post(f'/api/projects/{approved["id"]}/exports/plan',json=options(project,ids=[approved['cuts'][0]['id']])).status_code==422


def test_filename_safety_and_timebase_validation():
    assert safe_name('CON')=='_CON'
    assert '/' not in safe_name('../../a:b?')
    assert safe_name('...')=='corte'
    assert frame_rate({'frame_rate':'24000/1001'})==(Fraction(24000,1001),24,True)
    with pytest.raises(ValueError):frame_rate({'frame_rate':'29.5'})


def test_real_fast_copy_explicit_ack_and_no_audio(client,approved):
    body={**options(approved),'formats':['mp4','srt','json'],'audio_indices':[],'method':'fast','acknowledge_fast':True,'ids':[approved['cuts'][0]['id']]}
    opts=ExportOptions(**body); plan=plan_export(approved,opts)
    response=client.post(f'/api/projects/{approved["id"]}/exports',json={**body,'plan_token':plan['token']})
    result=wait(client,response.json())
    assert result['status']=='completed',result
    manifest=json.loads((Path(result['export_folder'])/'manifesto.json').read_text(encoding='utf-8'))
    render=manifest['rendered'][approved['cuts'][0]['id']]
    assert render['source_start']<approved['cuts'][0]['start'] and render['audio']==[]
    assert render['method']=='fast' and render['duration']>approved['cuts'][0]['duration']


def test_cancel_real_export_worker_ffmpeg_and_clean_only_own_staging(client,approved,monkeypatch,tmp_path):
    from backend import processing
    original_spawn=processing.spawn
    def paced_worker(command,**kwargs):
        code='''import json,sys,runpy
from pathlib import Path
from backend import processes
original=processes.spawn
def paced(command,**kwargs):
    if Path(command[0]).stem.lower()=='ffmpeg' and '-i' in command:
        command.insert(command.index('-i'),'-re')
    return original(command,**kwargs)
processes.spawn=paced
sys.argv=['backend.export_worker',sys.argv[1]]
runpy.run_module('backend.export_worker',run_name='__main__')
'''
        return original_spawn([sys.executable,'-u','-c',code,command[-1]],**kwargs)
    monkeypatch.setattr(processing,'spawn',paced_worker)
    marker=tmp_path/'arquivo-preexistente.txt';marker.write_text('preservar')
    job,_=start(client,approved,destination=str(tmp_path))
    queue=client.app.state.processing
    for _ in range(200):
        partial=Path(job['export_stage'])
        if partial.exists() and list(partial.glob('*.mp4')):break
        time.sleep(.01)
    process=queue.controls[job['id']]['process']
    assert process and process.poll() is None
    assert partial.exists() and list(partial.glob('*.mp4'))
    assert client.post(f'/api/projects/{approved["id"]}/cuts',json={'expected_revision':approved['revision'],'action':'delete','ids':[approved['cuts'][0]['id']]}).status_code==422
    client.delete('/api/processing/'+job['id'])
    result=wait(client,job)
    assert result['status']=='cancelled',result
    assert process.poll() is not None
    assert not partial.exists() and not Path(job['export_folder']).exists()
    assert marker.read_text()=='preservar'
    assert db.get(approved['id'])==approved


def test_failure_cleans_staging_and_does_not_publish(client,approved,monkeypatch,tmp_path):
    from backend import processing
    original_binary=processing.binary
    monkeypatch.setattr(processing,'binary',lambda name:sys.executable if name=='ffmpeg' else original_binary(name))
    job,_=start(client,approved,destination=str(tmp_path))
    result=wait(client,job)
    assert result['status']=='failed'
    assert not Path(job['export_stage']).exists() and not Path(job['export_folder']).exists()
    assert db.get(approved['id'])['exports']==[]


def test_recover_published_batch_and_interrupted_staging(client,approved,tmp_path):
    from backend.processing import ProcessingQueue
    from uuid import uuid4
    body={**options(approved),'formats':['json']}
    plan=plan_export(approved,ExportOptions(**body))
    job=client.post(f'/api/projects/{approved["id"]}/exports',json={**body,'plan_token':plan['token']}).json()
    completed=wait(client,job)
    assert completed['status']=='completed'
    before=db.get(approved['id'])
    completed.update(status='running',stage='verifying_export');db.save_job(completed)
    interrupted=copy.deepcopy(completed);interrupted.update(id=uuid4().hex)
    interrupted.update(export_stage=str(tmp_path/f'.leonida-{interrupted["id"]}.partial'),export_folder=str(tmp_path/'never-published'))
    stage=Path(interrupted['export_stage']);stage.mkdir();(stage/'.leonida-owner').write_text(interrupted['id']);(stage/'partial.mp4').write_bytes(b'incomplete')
    db.save_job(interrupted)
    queue=ProcessingQueue()
    try:
        assert db.get_job(job['id'])['status']=='completed'
        assert db.get_job(interrupted['id'])['status']=='interrupted'
        assert not stage.exists()
        assert db.get(approved['id'])==before  # Registro idempotente, sem revisão extra.
    finally:queue.close()


def test_overlapping_original_xml_rejected_and_compact_explicit(approved):
    project=copy.deepcopy(approved)
    project['cuts'][1].update(start=2,end=5,duration=3)
    with pytest.raises(ValueError,match='sobrepostos'):
        plan_export(project,ExportOptions(**options(project,sequence_mode='original')))
    assert any('sobrepostos' in w for w in plan_export(project,ExportOptions(**options(project)))['warnings'])


def test_publish_collision_and_cleanup_path_validation(tmp_path):
    from backend.export_storage import cleanup_stage, finalize_export
    from uuid import uuid4
    job_id=uuid4().hex
    stage=tmp_path/f'.leonida-{job_id}.partial';stage.mkdir();(stage/'.leonida-owner').write_text(job_id)
    target=tmp_path/'existing';target.mkdir();(target/'keep.txt').write_text('keep')
    job=dict(id=job_id,export_stage=str(stage),export_folder=str(target))
    with pytest.raises(ValueError,match='já existe'):finalize_export(job)
    assert (target/'keep.txt').read_text()=='keep'
    cleanup_stage({**job,'export_stage':str(target)})
    assert target.exists()
    cleanup_stage(job)
    assert not stage.exists()


def test_export_after_two_hours_with_absolute_source_and_relative_subtitles(client,tmp_path):
    path=tmp_path/'Origem longa - 7205 s.mp4'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=blue:s=16x16:r=1','-t','7205',
                    '-c:v','libx264','-preset','ultrafast',str(path)],check=True,timeout=30,creationflags=NO_WINDOW)
    project=client.post('/api/projects',json={'path':str(path)}).json()
    project['transcript']=[dict(id=1,start=7200,end=7204,text='Texto sintético próximo do final.')]
    project=db.save(project)
    project=edit_project(project['id'],EditCommand(expected_revision=project['revision'],action='create',start=7201,end=7203,title='Corte depois de duas horas'))['project']
    project=edit_project(project['id'],EditCommand(expected_revision=project['revision'],action='status',ids=[project['cuts'][0]['id']],status='approved'))['project']
    body={**options(project),'audio_indices':[]}
    plan=plan_export(project,ExportOptions(**body))
    job=client.post(f'/api/projects/{project["id"]}/exports',json={**body,'plan_token':plan['token']}).json()
    result=wait(client,job)
    assert result['status']=='completed',result
    folder=Path(result['export_folder']);row=plan['rows'][0]
    xml=ET.parse(folder/'sequencia.xml')
    assert xml.findtext('.//clipitem/in')=='7201' and xml.findtext('.//clipitem/start')=='0'
    assert '00:00:00,000 --> 00:00:02,000' in (folder/(row['name']+'.srt')).read_text(encoding='utf-8')
    with av.open(str(folder/(row['name']+'.mp4'))) as output:
        assert sum(1 for _ in output.decode(video=0))==2


def test_xml_stereo_mapping_and_control_characters(approved):
    project=copy.deepcopy(approved)
    for track in project['metadata']['audio']:track['channels']=2
    project['cuts'][0]['title']='Título & nota\x01 <teste>'
    plan=plan_export(project,ExportOptions(**options(project)))
    root=ET.fromstring(build_xml(project,plan))
    assert root.findtext('sequence/media/video/track/clipitem/name')=='Título & nota\ufffd <teste>'
    assert [t.findtext('clipitem/sourcetrack/trackindex') for t in root.findall('sequence/media/audio/track')]==['3','4','1','2']
    assert root.findtext('.//file/media/audio/channelcount')=='4'
