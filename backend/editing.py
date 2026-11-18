"""Edição não destrutiva de intervalos, revisões, undo/redo por diferenças e arquivos históricos."""
import hashlib
import json
import math
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from . import database as db
from .analysis import TranscriptIndex, sentence_units
from .media import check_unchanged
from .transcription import signature

MAX_CUTS = 1000
HISTORY_LIMIT = 100


class EditCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    expected_revision: int = Field(ge=0)
    action: Literal['create', 'update', 'status', 'split', 'merge', 'delete', 'undo', 'redo', 'restore']
    ids: list[str] = Field(default_factory=list, max_length=1000)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    status: Literal['pending', 'approved', 'rejected'] | None = None
    position: float | None = Field(default=None, ge=0)
    align_to_transcript: bool = False
    allow_gaps: bool = False
    archive_id: int | None = Field(default=None, gt=0)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def context_digest(project):
    # Um arquivo idêntico movido conserva o contexto. Não é hash integral da mídia.
    return digest([signature(project), project['selected_audio'], project['transcript']])


def minimum_duration(project):
    fps = project['metadata'].get('fps') or 0
    return max(.001, 1 / fps) if fps > 0 else .001


def validate_interval(project, start, end):
    duration = project['metadata']['duration']
    if start is None or end is None or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration:
        raise ValueError('Use 0 ≤ IN < OUT ≤ duração da mídia.')
    if end - start + 1e-6 < minimum_duration(project):
        raise ValueError('O corte precisa ter pelo menos um quadro nominal de duração.')


def validate_cuts(project, cuts):
    if len(cuts) > MAX_CUTS or len({c['id'] for c in cuts}) != len(cuts):
        raise ValueError('Limite de 1.000 cortes excedido ou identificadores duplicados.')
    for cut in cuts:
        validate_interval(project, cut['start'], cut['end'])
        if not math.isclose(cut['duration'], cut['end'] - cut['start'], abs_tol=.001):
            raise ValueError('Duração de corte inconsistente.')
        if cut['status'] not in ('pending', 'approved', 'rejected'):
            raise ValueError('Status de corte inválido.')
        if not isinstance(cut['title'], str) or not cut['title'].strip() or len(cut['title']) > 120:
            raise ValueError('Informe um título de até 120 caracteres.')
        for name in ('score', 'confidence'):
            value = cut.get(name)
            if value is not None and (not math.isfinite(value) or value < 0 or value > (100 if name == 'score' else 1)):
                raise ValueError('Pontuação/confiança de corte inválida.')


def align_bounds(project, start, end):
    for row in sentence_units(project['transcript']):
        if row['start'] < start < row['end']:
            start = row['start']
        if row['start'] < end < row['end']:
            end = row['end']
    return start, end


def retained_cuts(project, invalidate=False):
    retained = []
    for original in project.get('cuts', []):
        if original.get('manual') or original.get('edited') or original.get('status') in ('approved', 'rejected'):
            cut = dict(original)
            if invalidate:
                cut.update(status='pending', evidence_historical=True, score=None, confidence=None)
                cut['warnings'] = list(dict.fromkeys(cut.get('warnings', []) + ['Fontes de análise alteradas. Evidências anteriores são históricas; revise novamente.']))
            retained.append(cut)
    return retained


def refresh_cut(project, original, start, end, title=None, note=None, manual=False):
    validate_interval(project, start, end)
    cut = dict(original)
    cut.setdefault('origin', {k: original.get(k) for k in ('id', 'title', 'start', 'end', 'score', 'confidence', 'provider')})
    changed = start != original.get('start') or end != original.get('end')
    cut.update(start=start, end=end, duration=end - start, edited=True, updated_at=db.now())
    if title is not None:
        cut['title'] = title.strip()
    if note is not None:
        cut['review_note'] = note
    if changed or manual:
        cut.update(status='pending', score=None, confidence=None, provider='manual' if manual else cut.get('provider', 'manual'))
    evidence = list({json.dumps(e, sort_keys=True): e for e in original.get('evidence', []) + original.get('context_evidence', [])}.values())
    cut['evidence'] = [e for e in evidence if e['end'] > start and e['start'] < end][:80]
    cut['context_evidence'] = [e for e in evidence if e['end'] <= start or e['start'] >= end][:80]
    rows = TranscriptIndex(project['transcript']).overlap(start, end)
    cut['transcript_excerpt'] = '\n'.join(r['text'] for r in rows)[:2000]
    cut['partial_transcript'] = any(r['start'] < start < r['end'] or r['start'] < end < r['end'] for r in rows)
    return cut


def manual_cut(project, start, end, title, note=''):
    cut = dict(id=uuid4().hex, title=title or 'Corte manual', category='manual', start=start, end=end,
               duration=end - start, description='Intervalo marcado manualmente pelo editor.', rationale='Marcação manual.', hook='',
               transcript_excerpt='', score=None, confidence=None, evidence=[], inferences=[], warnings=[], status='pending',
               provider='manual', manual=True, edited=True, created_at=db.now(), source_digest=context_digest(project))
    return refresh_cut(project, cut, start, end, note=note, manual=True)


def merge_gaps(cuts):
    ordered = sorted(cuts, key=lambda c: c['start'])
    gaps, end = [], ordered[0]['end']
    for cut in ordered[1:]:
        if cut['start'] > end + .001:
            gaps.append({'start': end, 'end': cut['start']})
        end = max(end, cut['end'])
    return gaps


def delta(before, after):
    old = {c['id']: c for c in before}; new = {c['id']: c for c in after}
    changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
    return dict(before=[{'index': i, 'cut': c} for i, c in enumerate(before) if c['id'] in changed],
                after=[{'index': i, 'cut': c} for i, c in enumerate(after) if c['id'] in changed])


def apply_delta(current, record, direction):
    ids = {e['cut']['id'] for side in ('before', 'after') for e in record[side]}
    output = [c for c in current if c['id'] not in ids]
    for entry in sorted(record[direction], key=lambda e: e['index']):
        output.insert(min(entry['index'], len(output)), entry['cut'])
    return output


def edit_project(project_id, command):
    side_effects = {}
    def transform(project):
        check_unchanged(project)
        before = project.get('cuts', [])
        by_id = {c['id']: c for c in before}
        if len(set(command.ids)) != len(command.ids) or any(i not in by_id for i in command.ids):
            raise ValueError('Seleção contém cortes inexistentes ou duplicados.')
        selected = [by_id[i] for i in command.ids]
        context = context_digest(project)
        side_effects.update(before=before, context=context, selected_ids=[])
        if command.action in ('undo', 'redo'):
            return
        if command.action == 'restore':
            if command.archive_id is None:
                raise ValueError('Selecione um conjunto anterior para restaurar.')
            snapshot = db.get_cut_archive(project_id, command.archive_id)
            if snapshot['source_digest'] != context:
                raise ValueError('As fontes são diferentes. Exporte esse histórico para consultar, sem aplicar ao projeto atual.')
            side_effects['archive'] = db.capture_cuts(project, 'archive_restore')
            project['cuts'] = snapshot['cuts']
            validate_cuts(project, project['cuts'])
            side_effects['selected_ids'] = [c['id'] for c in project['cuts'][:1]]
            return
        if command.action == 'create':
            validate_interval(project, command.start, command.end)
            start, end = align_bounds(project, command.start, command.end) if command.align_to_transcript else (command.start, command.end)
            cut = manual_cut(project, start, end, command.title, command.note or '')
            project['cuts'] = before + [cut]; side_effects['selected_ids'] = [cut['id']]
        elif command.action == 'update':
            if len(selected) != 1:
                raise ValueError('Selecione um corte para ajustar.')
            cut = selected[0]
            start = cut['start'] if command.start is None else command.start
            end = cut['end'] if command.end is None else command.end
            if command.align_to_transcript:
                start, end = align_bounds(project, start, end)
            replacement = refresh_cut(project, cut, start, end, command.title, command.note)
            project['cuts'] = [replacement if c['id'] == cut['id'] else c for c in before]
            side_effects['selected_ids'] = [cut['id']]
        elif command.action == 'status':
            if not selected or command.status is None:
                raise ValueError('Selecione cortes e um status de revisão.')
            project['cuts'] = [{**c, 'status': command.status, 'reviewed_at': db.now(), 'reviewed_by': 'local_editor'} if c['id'] in command.ids else c for c in before]
            side_effects['selected_ids'] = command.ids
        elif command.action == 'delete':
            if not selected:
                raise ValueError('Selecione cortes para remover da decupagem.')
            project['cuts'] = [c for c in before if c['id'] not in command.ids]
        elif command.action == 'split':
            if len(selected) != 1 or command.position is None:
                raise ValueError('Selecione um corte e posicione o playhead para dividir.')
            cut, position = selected[0], command.position
            if not cut['start'] < position < cut['end']:
                raise ValueError('O playhead precisa estar dentro do corte selecionado.')
            children = []
            for index, (start, end) in enumerate(((cut['start'], position), (position, cut['end'])), 1):
                child = refresh_cut(project, cut, start, end, (cut['title'][:114] + f' · {index}')[:120], manual=True)
                child.update(id=uuid4().hex, manual=True, parent_ids=[cut['id']])
                children.append(child)
            output = []
            for item in before:
                output.extend(children if item['id'] == cut['id'] else [item])
            project['cuts'] = output; side_effects['selected_ids'] = [c['id'] for c in children]
        elif command.action == 'merge':
            if not 2 <= len(selected) <= 20:
                raise ValueError('Selecione de dois a vinte cortes para unir.')
            gaps = merge_gaps(selected)
            if gaps and not command.allow_gaps:
                raise ValueError('A união inclui lacunas. Confira o intervalo proposto e autorize incluir as lacunas.')
            start, end = min(c['start'] for c in selected), max(c['end'] for c in selected)
            merged = manual_cut(project, start, end, command.title or 'União de cortes', command.note or '')
            merged.update(parent_ids=command.ids, included_gaps=gaps,
                          evidence=[e for c in selected for e in c.get('evidence', [])][:80])
            merged['warnings'] = ['União manual: confira o conteúdo entre os intervalos de origem.'] if gaps else []
            first = min(i for i, c in enumerate(before) if c['id'] in command.ids)
            output = [c for c in before if c['id'] not in command.ids]
            output.insert(first, merged); project['cuts'] = output; side_effects['selected_ids'] = [merged['id']]
        validate_cuts(project, project['cuts'])

    def transaction(connection, project):
        cursor = project.get('editor_cursor', 0)
        if command.action in ('undo', 'redo'):
            seq = cursor if command.action == 'undo' else cursor + 1
            row = connection.execute('SELECT document FROM cut_history WHERE project_id=? AND seq=?', (project_id, seq)).fetchone()
            if not row:
                raise ValueError('Não há operação disponível para desfazer/refazer.')
            record = json.loads(row['document'])
            expected = record['after_hash'] if command.action == 'undo' else record['before_hash']
            if record['context'] != side_effects['context'] or digest(project['cuts']) != expected:
                raise ValueError('O histórico pertence a outro estado das fontes/cortes. Reabra o projeto.')
            direction = 'before' if command.action == 'undo' else 'after'
            project['cuts'] = apply_delta(project['cuts'], record, direction)
            validate_cuts(project, project['cuts'])
            project['editor_cursor'] = cursor - 1 if command.action == 'undo' else cursor + 1
            side_effects['selected_ids'] = [e['cut']['id'] for e in record[direction]]
            return
        if command.action == 'restore':
            db.store_cut_archive(connection, side_effects.get('archive'))
            db.reset_cut_history(connection, project)
            return
        before, after = side_effects['before'], project['cuts']
        if before == after:
            return
        connection.execute('DELETE FROM cut_history WHERE project_id=? AND seq>?', (project_id, cursor))
        record = dict(action=command.action, created_at=db.now(), context=side_effects['context'],
                      before_hash=digest(before), after_hash=digest(after), **delta(before, after))
        cursor += 1
        connection.execute('INSERT INTO cut_history VALUES (?,?,?)', (project_id, cursor, json.dumps(record, ensure_ascii=False, allow_nan=False)))
        connection.execute('DELETE FROM cut_history WHERE project_id=? AND seq<=?', (project_id, cursor - HISTORY_LIMIT))
        project['editor_cursor'] = cursor

    project = db.update(project_id, transform, expected_revision=command.expected_revision, transaction_hook=transaction)
    return dict(project=project, selected_ids=side_effects['selected_ids'], editor=editor_state(project))


def editor_state(project):
    cursor = project.get('editor_cursor', 0)
    with db.connect() as connection:
        rows = connection.execute('SELECT seq,document FROM cut_history WHERE project_id=? AND seq IN (?,?)', (project['id'], cursor, cursor + 1)).fetchall()
    records = {r['seq']: json.loads(r['document']) for r in rows}
    context, state = context_digest(project), digest(project.get('cuts', []))
    undo = records.get(cursor); redo = records.get(cursor + 1)
    overlaps = []
    ids = set()
    ordered = sorted(project.get('cuts', []), key=lambda c: c['start'])
    for i, cut in enumerate(ordered):
        for other in ordered[i + 1:]:
            if other['start'] >= cut['end']:
                break
            ids.update((cut['id'], other['id']))
            if len(overlaps) < 100:
                overlaps.append([cut['id'], other['id']])
    return dict(can_undo=bool(undo and undo['context'] == context and undo['after_hash'] == state),
                can_redo=bool(redo and redo['context'] == context and redo['before_hash'] == state),
                undo_action=undo['action'] if undo else None, redo_action=redo['action'] if redo else None,
                overlap_ids=sorted(ids), overlap_pairs=overlaps,
                archives=[{**a, 'compatible': a['source_digest'] == context} for a in db.list_cut_archives(project['id'])])
