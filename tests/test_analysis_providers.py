import json

import httpx
import pytest

from backend.analysis import AnalysisOptions
from backend.analysis_providers import ProviderFailure, analyze_block

BLOCK = [dict(id=7, start=3600, end=3607, text='Meu Deus, que susto!')]
MOMENTS = {'moments': [dict(start=3600, end=3607, segment_ids=[7], title='Reação', category='reacao', interpretation='Pode indicar surpresa.', hook='Abrir com a frase.', score=60, confidence=.6)]}
KEY = 'sk-SENTINELA-NAO-PERSISTIR'


def test_openai_responses_contract_store_false_fixed_url_and_no_secret_in_prompt():
    observed = []
    def handler(request):
        data = json.loads(request.content); observed.append(data)
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['Authorization'] == 'Bearer ' + KEY
        assert KEY not in request.content.decode()
        assert data['store'] is False and data['text']['format']['strict'] is True
        assert data['text']['format']['schema']['additionalProperties'] is False
        assert '3600' in data['input'][1]['content']
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(MOMENTS)}]}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = analyze_block('openai', AnalysisOptions(provider='openai', model='modelo-configurado').model_dump(), BLOCK, KEY, client)
    assert result[0]['evidence'][0]['reference'] == 'segment:7'
    assert len(observed) == 1


@pytest.mark.parametrize('response', [httpx.Response(401, json={'error': KEY}), httpx.Response(200, json={'status': 'incomplete'}),
    httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal', 'refusal': KEY}]}]}),
    httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'not JSON'}]}]})])
def test_provider_errors_never_include_secret_or_raw_body(response):
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(ProviderFailure) as error:
            analyze_block('openai', AnalysisOptions(provider='openai', model='modelo-configurado').model_dump(), BLOCK, KEY, client)
    assert KEY not in str(error.value)


def test_ollama_uses_loopback_schema_no_download_or_key():
    seen = []
    def handler(request):
        seen.append(request.url.path)
        assert request.url.host == '127.0.0.1'
        assert 'authorization' not in request.headers
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'model_info': {}})
        data = json.loads(request.content)
        assert data['stream'] is False and data['format']['additionalProperties'] is False
        assert data['keep_alive'] == 0
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps(MOMENTS)}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert analyze_block('ollama', AnalysisOptions(provider='ollama', model='modelo-local').model_dump(), BLOCK, '', client)
    assert seen == ['/api/show', '/api/chat']


def test_ollama_cloud_metadata_is_rejected_before_chat():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'remote_host': 'https://remote.example'}))) as client:
        with pytest.raises(ProviderFailure, match='remota'):
            analyze_block('ollama', AnalysisOptions(provider='ollama', model='modelo').model_dump(), BLOCK, '', client)
