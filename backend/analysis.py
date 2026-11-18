"""Contratos, rastreabilidade e heurísticas locais; nenhuma inferência visual."""
import hashlib
import json
import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

ALGORITHM = 2
CATEGORIES = Literal['reacao', 'humor', 'susto', 'discussao', 'jogada', 'falha', 'revelacao', 'emocao', 'historia', 'informacao', 'tensao', 'evento_sonoro']
PROFILES = ['gameplay', 'live', 'podcast', 'entrevista', 'react', 'informativo', 'generico']
PURPOSES = ['shorts', 'reels', 'tiktok', 'melhores_momentos', 'decupagem']


class AnalysisOptions(BaseModel):
    provider: Literal['local', 'openai', 'ollama'] = 'local'
    model: str = Field(default='', max_length=100, pattern=r'^[\w.\-:/]*$')
    content_profile: Literal['gameplay', 'live', 'podcast', 'entrevista', 'react', 'informativo', 'generico'] = 'generico'
    purpose: Literal['shorts', 'reels', 'tiktok', 'melhores_momentos', 'decupagem'] = 'shorts'
    min_duration: float = Field(default=15, ge=2, le=300, allow_inf_nan=False)
    preferred_duration: float = Field(default=35, ge=2, le=300, allow_inf_nan=False)
    max_duration: float = Field(default=60, ge=2, le=600, allow_inf_nan=False)
    margin_before: float = Field(default=3, ge=0, le=30, allow_inf_nan=False)
    margin_after: float = Field(default=4, ge=0, le=30, allow_inf_nan=False)
    analyze_audio: bool = True
    silence_db: float = Field(default=-45, ge=-80, le=-15, allow_inf_nan=False)
    max_suggestions: int = Field(default=30, ge=1, le=100)
    max_blocks: int = Field(default=100, ge=1, le=200)
    ollama_port: int = Field(default=11434, ge=1024, le=65535)
    consent: bool = False
    replace_existing: bool = False

    @model_validator(mode='after')
    def durations(self):
        if not self.min_duration <= self.preferred_duration <= self.max_duration:
            raise ValueError('Use duração mínima ≤ preferencial ≤ máxima.')
        return self


class AnalysisRequest(AnalysisOptions):
    api_key: SecretStr = Field(default=SecretStr(''), exclude=True, repr=False)


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    kind: Literal['transcript', 'audio']
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    reference: str = Field(max_length=80)
    detail: str = Field(max_length=1500)


class Suggestion(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str
    title: str = Field(max_length=120)
    category: CATEGORIES
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    duration: float = Field(gt=0)
    description: str = Field(max_length=800)
    rationale: str = Field(max_length=1000)
    hook: str = Field(max_length=300)
    transcript_excerpt: str = Field(max_length=2000)
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=1, max_length=40)
    inferences: list[str] = Field(max_length=10)
    warnings: list[str] = Field(max_length=10)
    status: Literal['pending', 'approved', 'rejected'] = 'pending'
    provider: Literal['local', 'openai', 'ollama']


class Proposal(BaseModel):
    # Sem defaults: todos os campos são obrigatórios no JSON Schema do provedor.
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    segment_ids: list[int] = Field(min_length=1, max_length=25)
    title: str = Field(min_length=1, max_length=100)
    category: CATEGORIES
    interpretation: str = Field(max_length=600)
    hook: str = Field(max_length=250)
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)


class Proposals(BaseModel):
    model_config = ConfigDict(extra='forbid')
    moments: list[Proposal] = Field(max_length=10)


RULES = {
    'humor': ['kkkk', 'hahaha', 'que engracado', 'to rindo', 'estou rindo', 'nao aguento rir', 'that was funny'],
    'susto': ['que susto', 'me assustou', 'levei um susto', 'scared me'],
    'reacao': ['meu deus', 'nao acredito', 'caramba', 'oh my god', 'no way'],
    'discussao': ['discordo', 'nao concordo', 'voce esta errado', 'i disagree'],
    'jogada': ['que jogada', 'jogada incrivel', 'acertei', 'ganhamos', 'what a play'],
    'falha': ['deu errado', 'eu errei', 'falhei', 'morri', 'perdi tudo', 'that failed'],
    'revelacao': ['descobri', 'a verdade e', 'ninguem sabia', 'o segredo e', 'i discovered'],
    'emocao': ['emocionado', 'chorei', 'muito obrigado', 'estou orgulhoso', 'proud of'],
    'historia': ['vou contar uma historia', 'quando eu era', 'aconteceu comigo', 'let me tell you'],
    'informacao': ['uma dica', 'e importante', 'vou explicar', 'como funciona', 'aprendi', 'important tip'],
    'tensao': ['toma cuidado', 'estou nervoso', 'estou com medo', 'nao podemos errar', 'be careful'],
}
LABELS = {'humor': 'Expressão de humor', 'susto': 'Fala sobre susto', 'reacao': 'Reação verbal',
          'discussao': 'Divergência na fala', 'jogada': 'Fala sobre jogada', 'falha': 'Fala sobre falha',
          'revelacao': 'Possível revelação', 'emocao': 'Expressão emocional', 'historia': 'Início de história',
          'informacao': 'Informação potencialmente relevante', 'tensao': 'Expressão de tensão', 'evento_sonoro': 'Variação de energia sonora'}


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def input_digest(project):
    payload = {k: project[k] for k in ('path', 'metadata', 'selected_audio', 'transcript')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def analysis_key(project, options):
    effective = {k: v for k, v in options.items() if k not in ('consent', 'replace_existing', 'cache_key')}
    return hashlib.sha256(json.dumps([ALGORITHM, input_digest(project), effective], sort_keys=True).encode()).hexdigest()


def transcript_blocks(rows, max_chars=12000):
    cursor = 0
    while cursor < len(rows):
        end, count = cursor, 0
        while end < len(rows):
            row = rows[end]
            size = len(json.dumps(row, ensure_ascii=False))
            if size > max_chars:
                raise ValueError('Há um trecho de texto muito longo para o provedor. Divida-o ou use o modo local.')
            if end > cursor and (count + size > max_chars or end - cursor >= 80 or row['start'] - rows[cursor]['start'] >= 300):
                break
            count += size
            end += 1
        yield rows[cursor:end]
        cursor = end if end == len(rows) else max(cursor + 1, end - 2)


def transcript_evidence(row):
    return dict(kind='transcript', start=row['start'], end=row['end'], reference=f'segment:{row["id"]}', detail=row['text'][:1500])


def audio_evidence(event):
    label = {'high_energy': 'Energia acima do limiar adaptativo', 'energy_rise': 'Aumento abrupto de energia'}[event['kind']]
    return dict(kind='audio', start=event['start'], end=event['end'], reference=f'stream:{event["stream"]}',
                detail=f"{label}; RMS {event['rms_db']:.1f} dBFS; pico {event['peak_db']:.1f} dBFS; variação {event['delta_db']:.1f} dB.")


def local_candidates(project, audio, options):
    candidates = []
    for row in project['transcript']:
        text = normalized(row['text'])
        matches = [(category, [phrase for phrase in words if re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text)]) for category, words in RULES.items()]
        matches = [(cat, hits) for cat, hits in matches if hits]
        if not matches:
            continue
        category, hits = max(matches, key=lambda pair: len(pair[1]))
        score = min(78, 35 + 9 * sum(len(h) for _, h in matches))
        preferred = {'gameplay': {'jogada', 'falha', 'susto'}, 'live': {'humor', 'emocao', 'reacao'},
                     'podcast': {'historia', 'informacao', 'discussao'}, 'entrevista': {'historia', 'revelacao', 'informacao'},
                     'react': {'reacao', 'humor'}, 'informativo': {'informacao', 'revelacao'}}
        if category in preferred.get(options['content_profile'], set()):
            score += 6
        candidates.append(dict(start=row['start'], end=row['end'], title=LABELS[category], category=category,
                               score=score, confidence=.55, evidence=[transcript_evidence(row)],
                               inferences=[f"A expressão textual pode indicar {LABELS[category].lower()}; contexto e interesse dependem de revisão."],
                               rationale='Expressões reconhecidas na transcrição: ' + ', '.join(hits), hook=row['text'][:250], provider='local'))
    for candidate in candidates:
        nearby = [e for e in audio.get('events', []) if e['start'] <= candidate['end'] + 2 and e['end'] >= candidate['start'] - 2][:5]
        if nearby:
            candidate['evidence'].extend(audio_evidence(e) for e in nearby)
            candidate['start'] = min(candidate['start'], *(e['start'] for e in nearby))
            candidate['end'] = max(candidate['end'], *(e['end'] for e in nearby))
    for event in audio.get('events', []):
        candidates.append(dict(start=event['start'], end=event['end'], title=LABELS['evento_sonoro'], category='evento_sonoro',
                               score=32 if event['kind'] == 'energy_rise' else 38, confidence=.25,
                               evidence=[audio_evidence(event)], inferences=['Uma mudança sonora pode merecer revisão; não identifica sua origem nem um acontecimento visual.'],
                               rationale='Variação de energia medida na faixa selecionada, sem atribuir significado ao som.',
                               hook='Sugestão editorial: abrir no instante da mudança sonora, após conferir o contexto.', provider='local'))
    return candidates


def provider_candidates(payload, block, provider):
    result = Proposals.model_validate(payload)
    known = {r['id']: r for r in block}
    output = []
    for proposal in result.moments:
        if proposal.end <= proposal.start or not set(proposal.segment_ids) <= known.keys():
            raise ValueError('O provedor retornou referências ou intervalos inválidos.')
        references = [known[i] for i in dict.fromkeys(proposal.segment_ids)]
        if proposal.start < min(r['start'] for r in block) or proposal.end > max(r['end'] for r in block) + .05:
            raise ValueError('O provedor retornou tempos fora do bloco enviado.')
        if any(r['end'] <= proposal.start or r['start'] >= proposal.end for r in references):
            raise ValueError('Uma referência do provedor não pertence ao intervalo sugerido.')
        output.append(dict(start=proposal.start, end=proposal.end, title=proposal.title, category=proposal.category,
                           score=proposal.score, confidence=min(.8, proposal.confidence),
                           evidence=[transcript_evidence(r) for r in references], inferences=[proposal.interpretation],
                           rationale='Interpretação do provedor apoiada nos IDs de transcrição citados; significado não verificado automaticamente.',
                           hook=proposal.hook, provider=provider))
    return output


class TranscriptIndex:
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r['start'])
        self.starts = [r['start'] for r in self.rows]
        self.ends = []
        maximum = 0
        for row in self.rows:
            maximum = max(maximum, row['end'])
            self.ends.append(maximum)

    def overlap(self, a, b):
        lo, hi = bisect_right(self.ends, a), bisect_left(self.starts, b)
        return [r for r in self.rows[lo:hi] if r['end'] > a]


def sentence_units(rows):
    units = []
    for row in sorted(rows, key=lambda r: r['start']):
        previous = units[-1] if units else None
        if previous and row['start'] - previous['end'] <= 1.2 and not re.search(r'[.!?…][\s"\'\)\]]*$', previous['text']):
            previous['end'] = max(previous['end'], row['end'])
            previous['text'] += ' ' + row['text']
        else:
            units.append(dict(row))
    return units


def fit_interval(start, end, rows, duration, options, index=None):
    index = index or TranscriptIndex(sentence_units(rows))
    # Inclui integralmente frases que cruzam as bordas; nunca as corta para cumprir um limite.
    a, b = max(0, start - options['margin_before']), min(duration, end + options['margin_after'])
    target = max(options['min_duration'], min(options['preferred_duration'], options['max_duration']))
    missing = max(0, target - (b - a))
    a, b = max(0, a - missing / 2), min(duration, b + missing / 2)
    if b - a < min(target, duration):
        a = max(0, b - target)
        b = min(duration, max(b, a + target))
    for _ in range(3):
        intersecting = index.overlap(a, b)
        na = min([a] + [r['start'] for r in intersecting])
        nb = max([b] + [r['end'] for r in intersecting])
        if na == a and nb == b:
            break
        a, b = na, nb
    if b - a < options['min_duration'] or b - a > options['max_duration'] + .05:
        return None
    if any(r['start'] < a < r['end'] or r['start'] < b < r['end'] for r in index.overlap(a, b)):
        return None
    return a, b


def finish_suggestions(project, candidates, options):
    duration, rows = project['metadata']['duration'], project['transcript']
    index = TranscriptIndex(rows)
    boundaries = TranscriptIndex(sentence_units(rows))
    # Pré-seleção editorial limitada e distribuída no tempo antes do ajuste de frases.
    buckets = {}
    for candidate in sorted(candidates, key=lambda s: -s['score']):
        bucket = int(candidate['start'] // max(2, options['min_duration']))
        if len(buckets.setdefault(bucket, [])) < 2:
            buckets[bucket].append(candidate)
    candidates = sorted((c for group in buckets.values() for c in group), key=lambda s: -s['score'])[:max(200, options['max_suggestions'] * 20)]
    prepared = []
    for candidate in candidates:
        interval = fit_interval(candidate['start'], candidate['end'], rows, duration, options, boundaries)
        if interval is None:
            continue
        a, b = interval
        evidence = candidate['evidence'][:40]
        relevant = index.overlap(a, b)
        excerpt = '\n'.join(r['text'] for r in relevant)[:2000]
        score = candidate['score']
        if any(e['kind'] == 'transcript' for e in evidence) and any(e['kind'] == 'audio' for e in evidence):
            score = min(95, score + 8)
        identity = hashlib.sha256(f'{a:.3f}:{b:.3f}:{candidate["category"]}'.encode()).hexdigest()[:12]
        prepared.append(Suggestion(id=identity, title=candidate['title'], category=candidate['category'], start=a, end=b, duration=b - a,
            description=f"Intervalo sugerido para revisão, com {len(relevant)} trecho(s) de transcrição. Não houve análise visual.",
            rationale=candidate['rationale'], hook=candidate['hook'][:300], transcript_excerpt=excerpt, score=score,
            confidence=candidate['confidence'], evidence=evidence, inferences=candidate['inferences'],
            warnings=['Pontuação estimativa; não prevê viralização.', 'Título, categoria e gancho são sugestões editoriais.',
                      'Limites apoiados em segmentos, pontuação e pausas; confirme ao ouvir.'], provider=candidate['provider']).model_dump())
    # NMS por score, sem gerar intervalos artificiais ou multiplicar o mesmo momento.
    selected = []
    for item in sorted(prepared, key=lambda s: (-s['score'], s['start'])):
        overlaps = [p for p in selected if min(p['end'], item['end']) > max(p['start'], item['start'])]
        if overlaps:
            winner = overlaps[0]
            # Acrescenta apenas evidências dentro do corte sobrevivente.
            for evidence in item['evidence']:
                if evidence['start'] >= winner['start'] and evidence['end'] <= winner['end'] and evidence not in winner['evidence'] and len(winner['evidence']) < 40:
                    winner['evidence'].append(evidence)
            continue
        selected.append(item)
        if len(selected) >= options['max_suggestions']:
            break
    return selected


def validate_result(result, project, options):
    if len(result['suggestions']) > options['max_suggestions']:
        raise ValueError('Quantidade de sugestões inválida.')
    output = [Suggestion.model_validate(s).model_dump() for s in result['suggestions']]
    duration = project['metadata']['duration']
    source_rows = {f'segment:{r["id"]}': r for r in project['transcript']}
    for i, item in enumerate(output):
        if item['status'] != 'pending':
            raise ValueError('Uma análise não pode aprovar sugestões automaticamente.')
        if not (0 <= item['start'] < item['end'] <= duration + .05) or not math.isclose(item['duration'], item['end'] - item['start'], abs_tol=.01):
            raise ValueError('Intervalo de sugestão inválido.')
        if not options['min_duration'] <= item['duration'] <= options['max_duration'] + .05:
            raise ValueError('Duração de sugestão fora das configurações.')
        if any(e['start'] < item['start'] or e['end'] > item['end'] + .05 or e['end'] <= e['start'] for e in item['evidence']):
            raise ValueError('Evidência fora do intervalo sugerido.')
        for evidence in item['evidence']:
            if evidence['kind'] == 'transcript':
                source = source_rows.get(evidence['reference'])
                if not source or evidence['detail'] != source['text'][:1500] or abs(evidence['start'] - source['start']) > .01 or abs(evidence['end'] - source['end']) > .01:
                    raise ValueError('Evidência textual diferente da fonte.')
        if any(min(p['end'], item['end']) > max(p['start'], item['start']) for p in output[:i]):
            raise ValueError('Sugestões sobrepostas após normalização.')
    return output
