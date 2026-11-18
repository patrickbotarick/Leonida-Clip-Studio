import copy
import json

import pytest

from backend.analysis import (AnalysisOptions, analysis_key, finish_suggestions, fit_interval,
                              input_digest, local_candidates, provider_candidates, transcript_blocks, validate_result)


def sample():
    return dict(path='C:/synthetic.mp4', metadata={'duration': 120, 'size': 123, 'mtime_ns': 42}, selected_audio=[1],
                transcript=[dict(id=1, start=20, end=25, text='Meu Deus, que susto! Não acredito.'),
                            dict(id=2, start=75, end=80, text='Uma dica: vou explicar como funciona.')])


def options(**kwargs):
    return AnalysisOptions(min_duration=8, preferred_duration=18, max_duration=30, **kwargs).model_dump()


@pytest.mark.parametrize('data', [{'min_duration': 40, 'preferred_duration': 20}, {'preferred_duration': 100, 'max_duration': 30}, {'silence_db': -100}, {'max_suggestions': 0}, {'ollama_port': 80}, {'provider': 'unknown'}, {'max_duration': float('inf')}])
def test_invalid_analysis_options(data):
    with pytest.raises(ValueError):
        AnalysisOptions(**data)


def test_local_text_heuristics_have_actual_evidence_and_pending_status():
    project, opts = sample(), options()
    candidates = local_candidates(project, {'events': []}, opts)
    cuts = finish_suggestions(project, candidates, opts)
    assert len(cuts) == 2
    assert all(c['status'] == 'pending' and c['evidence'][0]['kind'] == 'transcript' for c in cuts)
    assert all(c['inferences'] and c['warnings'] for c in cuts)
    assert len(validate_result({'suggestions': cuts}, project, opts)) == 2


def test_unremarkable_text_is_not_forced_into_a_highlight():
    project = sample(); project['transcript'][0]['text'] = 'Estamos aqui no menu.'; project['transcript'][1]['text'] = 'A tela continua carregando.'
    assert local_candidates(project, {'events': []}, options()) == []


def test_audio_only_is_generic_low_confidence_without_visual_claims():
    project = sample(); project['transcript'] = []
    event = dict(stream=1, start=20, end=21, rms_db=-5, peak_db=-2, delta_db=30, kind='high_energy')
    cuts = finish_suggestions(project, local_candidates(project, {'events': [event]}, options()), options())
    assert cuts[0]['category'] == 'evento_sonoro'
    assert cuts[0]['confidence'] <= .3 and cuts[0]['score'] < 50
    assert cuts[0]['transcript_excerpt'] == ''
    assert 'Variação' in cuts[0]['title']


def test_audio_complements_text_and_duplicate_intervals_are_removed():
    project = sample()
    event = dict(stream=1, start=21, end=22, rms_db=-5, peak_db=-2, delta_db=30, kind='high_energy')
    cuts = finish_suggestions(project, local_candidates(project, {'events': [event, event]}, options()), options())
    assert len(cuts) == 2
    assert any({e['kind'] for e in c['evidence']} == {'transcript', 'audio'} for c in cuts)
    assert max(c['score'] for c in cuts) > max(c['score'] for c in finish_suggestions(project, local_candidates(project, {'events': []}, options()), options()))


def test_context_never_splits_a_phrase_or_invents_minimum_duration():
    rows = [dict(id=1, start=10, end=28, text='Frase longa')]
    start, end = fit_interval(14, 16, rows, 120, options())
    assert start <= 10 and end >= 28 and 8 <= end - start <= 30
    assert fit_interval(14, 16, rows, 120, {**options(), 'max_duration': 12, 'preferred_duration': 10}) is None
    assert fit_interval(1, 2, [], 5, options()) is None


def test_adjacent_unfinished_segments_are_kept_as_one_sentence():
    rows = [dict(id=1, start=10, end=14, text='Uma frase ainda'), dict(id=2, start=14.2, end=19, text='com o seu final.')]
    settings = AnalysisOptions(min_duration=2, preferred_duration=4, max_duration=10, margin_before=0, margin_after=0).model_dump()
    start, end = fit_interval(11, 12, rows, 120, settings)
    assert start <= 10 and end >= 19


def test_cache_key_tracks_text_streams_and_options_but_not_consent():
    project, opts = sample(), options()
    key = analysis_key(project, opts)
    assert analysis_key(project, {**opts, 'consent': True, 'replace_existing': True}) == key
    changed = copy.deepcopy(project); changed['transcript'][0]['text'] += ' Alterado'
    assert input_digest(project) != input_digest(changed)
    assert analysis_key({**project, 'selected_audio': [2]}, opts) != key
    assert analysis_key(project, {**opts, 'max_duration': 50}) != key


def test_blocks_are_bounded_overlap_and_keep_global_ids():
    rows = [dict(id=i, start=1000 + i * 5, end=1002 + i * 5, text='texto de contexto') for i in range(200)]
    blocks = list(transcript_blocks(rows))
    assert len(blocks) > 1
    assert set(r['id'] for b in blocks for r in b) == set(range(200))
    assert {r['id'] for r in blocks[0][-2:]} <= {r['id'] for r in blocks[1]}
    assert blocks[0][0]['start'] == 1000
    with pytest.raises(ValueError):
        list(transcript_blocks([dict(id=1, start=0, end=10, text='x' * 13000)]))


def proposal(**changes):
    return {'start': 20, 'end': 25, 'segment_ids': [1], 'title': 'Reação para revisar', 'category': 'reacao',
            'interpretation': 'A fala pode indicar surpresa.', 'hook': 'Abrir pela frase de reação.', 'score': 70, 'confidence': .7, **changes}


@pytest.mark.parametrize('change', [{'start': -1}, {'end': 200}, {'end': 19}, {'segment_ids': [999]}, {'segment_ids': [2]}, {'score': 101}, {'confidence': 2}, {'category': 'headshot'}, {'start': float('nan')}, {'unexpected': 'field'}])
def test_provider_responses_reject_bad_references_times_schema(change):
    with pytest.raises(ValueError):
        provider_candidates({'moments': [proposal(**change)]}, sample()['transcript'], 'openai')


def test_provider_evidence_is_built_from_source_not_generated_quotes():
    project = sample()
    cuts = finish_suggestions(project, provider_candidates({'moments': [proposal()]}, project['transcript'], 'openai'), options())
    assert cuts[0]['evidence'][0]['detail'] == project['transcript'][0]['text']
    assert 'não verificado' in cuts[0]['rationale']
    forged = copy.deepcopy(cuts); forged[0]['evidence'][0]['detail'] = 'Um fato inventado'
    with pytest.raises(ValueError, match='diferente da fonte'):
        validate_result({'suggestions': forged}, project, options())
    approved = copy.deepcopy(cuts); approved[0]['status'] = 'approved'
    with pytest.raises(ValueError, match='aprovar'):
        validate_result({'suggestions': approved}, project, options())
