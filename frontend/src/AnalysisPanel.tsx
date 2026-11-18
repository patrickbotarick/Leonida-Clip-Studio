import { useEffect, useRef, useState } from "react";
import {
  Download,
  Play,
  Search,
  ShieldCheck,
  Sparkles,
  Square,
} from "lucide-react";

export type Evidence = {
  kind: string;
  start: number;
  end: number;
  reference: string;
  detail: string;
};
export type Suggestion = {
  id: string;
  title: string;
  category: string;
  start: number;
  end: number;
  duration: number;
  score: number | null;
  confidence: number | null;
  review_note?: string;
  partial_transcript?: boolean;
  evidence_historical?: boolean;
  context_evidence?: Evidence[];
  description: string;
  rationale: string;
  hook: string;
  transcript_excerpt: string;
  evidence: Evidence[];
  inferences: string[];
  warnings: string[];
  status: string;
  provider: string;
};
type Track = {
  stream: number;
  measured_seconds: number;
  silence_seconds: number;
  max_peak_db: number;
  event_count: number;
  curve: { time: number; rms_db: number }[];
};
export type Analysis = {
  options: Record<string, unknown>;
  audio: { enabled: boolean; tracks: Track[] };
  limitations: string[];
  speech_indicators: { words_per_media_minute: number };
};
type Job = {
  id: string;
  status: string;
  stage: string;
  progress: number | null;
  error?: string;
  cache_hit: boolean;
  suggestions?: number;
};
type Plan = {
  characters: number;
  provider_blocks: number | null;
  transcript_segments: number;
};
type Options = {
  provider: string;
  model: string;
  content_profile: string;
  purpose: string;
  min_duration: number;
  preferred_duration: number;
  max_duration: number;
  margin_before: number;
  margin_after: number;
  analyze_audio: boolean;
  silence_db: number;
  max_suggestions: number;
  max_blocks: number;
  ollama_port: number;
};
type Props = {
  projectId: string;
  audioCount: number;
  transcriptCount: number;
  cuts: Suggestion[];
  analysis?: Analysis | null;
  processing: boolean;
  onApplied: () => void;
  onTaskStarted: () => void;
  onPreview: (start: number, end: number) => void;
};
export const categories: Record<string, string> = {
  manual: "Manual",
  reacao: "Reação",
  humor: "Humor",
  susto: "Susto",
  discussao: "Discussão",
  jogada: "Fala sobre jogada",
  falha: "Falha",
  revelacao: "Revelação",
  emocao: "Emoção",
  historia: "História",
  informacao: "Informação",
  tensao: "Tensão",
  evento_sonoro: "Evento sonoro",
};
const stages: Record<string, string> = {
  queued: "Na fila",
  starting: "Iniciando",
  analyzing_audio: "Medindo áudio por faixa",
  analyzing_text: "Analisando transcrição",
  provider_request: "Consultando provedor autorizado",
  ranking: "Classificando e ajustando contexto",
  saving: "Validando resultados",
  completed: "Concluído",
  failed: "Falha",
  cancelling: "Encerrando",
  cancelled: "Cancelado",
  interrupted: "Interrompido",
};
const active = (j: Job | null) =>
  !!j && ["queued", "running", "cancelling"].includes(j.status);
function stamp(n: number) {
  return [Math.floor(n / 3600), Math.floor(n / 60) % 60, Math.floor(n) % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}
async function request<T>(
  path: string,
  body?: unknown,
  method = "GET",
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { "X-Leonida-Client": "1", "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Confira as opções da análise.",
    );
  return data;
}

export function AnalysisPanel(props: Props) {
  const [options, setOptions] = useState<Options>({
    provider: "local",
    model: "",
    content_profile: "generico",
    purpose: "shorts",
    min_duration: 15,
    preferred_duration: 35,
    max_duration: 60,
    margin_before: 3,
    margin_after: 4,
    analyze_audio: props.audioCount > 0,
    silence_db: -45,
    max_suggestions: 30,
    max_blocks: 100,
    ollama_port: 11434,
    ...(props.analysis?.options ?? {}),
  } as Options);
  const [secret, setSecret] = useState("");
  const [consent, setConsent] = useState(false);
  const [replace, setReplace] = useState(false);
  const [expanded, setExpanded] = useState(!props.analysis);
  const [job, setJob] = useState<Job | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [score, setScore] = useState(0);
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("score");
  const [query, setQuery] = useState("");
  const callback = useRef(props.onApplied);
  callback.current = props.onApplied;
  const seen = useRef(new Set<string>());
  const wasActive = useRef(new Set<string>());
  useEffect(() => {
    let disposed = false,
      fetching = false;
    request<Plan>(`/projects/${props.projectId}/analysis/plan`)
      .then((p) => {
        if (!disposed) setPlan(p);
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    const load = async () => {
      if (fetching) return;
      fetching = true;
      try {
        const jobs = await request<(Job & { kind: string })[]>(
          `/processing?project_id=${props.projectId}`,
        );
        if (disposed) return;
        const latest = jobs.find((j) => j.kind === "analysis");
        if (latest) {
          setJob(latest);
          if (active(latest)) wasActive.current.add(latest.id);
          if (!active(latest) && !seen.current.has(latest.id)) {
            seen.current.add(latest.id);
            if (
              latest.status === "completed" &&
              wasActive.current.has(latest.id)
            ) {
              callback.current();
              setExpanded(false);
            }
          }
        }
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        fetching = false;
      }
    };
    load();
    const timer = setInterval(load, 1200);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [props.projectId]);
  const change = (key: keyof Options, value: string | number | boolean) =>
    setOptions((previous) => ({ ...previous, [key]: value }));
  async function analyze(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const submitted = await request<Job>(
        `/projects/${props.projectId}/analyze`,
        { ...options, consent, replace_existing: replace, api_key: secret },
        "POST",
      );
      setJob(submitted);
      wasActive.current.add(submitted.id);
      props.onTaskStarted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSecret("");
      setConsent(false);
      setBusy(false);
    }
  }
  async function cancel() {
    if (!job) return;
    try {
      setJob(await request<Job>(`/processing/${job.id}`, undefined, "DELETE"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const filtered = props.cuts
    .filter(
      (c) =>
        (c.score ?? 0) >= score &&
        (!category || c.category === category) &&
        `${c.title} ${c.transcript_excerpt}`
          .toLocaleLowerCase()
          .includes(query.toLocaleLowerCase()),
    )
    .sort((a, b) =>
      sort === "time" ? a.start - b.start : (b.score ?? -1) - (a.score ?? -1),
    );
  const number = (
    key: keyof Options,
    label: string,
    min: number,
    max: number,
  ) => (
    <label>
      {label}
      <input
        aria-label={label}
        type="number"
        min={min}
        max={max}
        step="1"
        required
        value={Number(options[key])}
        onChange={(e) => change(key, Number(e.target.value))}
      />
    </label>
  );
  return (
    <div className="analysis-panel">
      <div className="analysis-heading">
        <span className="eyebrow">MOMENTOS PARA REVISÃO</span>
        <h2>
          {props.analysis
            ? `${props.cuts.length} sugestões encontradas`
            : "Encontre possíveis momentos."}
        </h2>
        <p>
          Estimativas editoriais, sem garantia de engajamento. Nenhuma análise
          visual.
        </p>
      </div>
      <button
        className="asr-toggle analysis-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span>
          <Sparkles size={15} /> Configurar análise
        </span>
        <span>{expanded ? "−" : "+"}</span>
      </button>
      {expanded && (
        <form className="analysis-form" onSubmit={analyze}>
          <fieldset disabled={busy || active(job) || props.processing}>
            <label>
              Modo
              <select
                aria-label="Provedor de análise"
                value={options.provider}
                onChange={(e) => {
                  change("provider", e.target.value);
                  change("model", "");
                  setSecret("");
                  setConsent(false);
                }}
              >
                <option value="local">Heurísticas locais · offline</option>
                <option value="openai">OpenAI · envio de texto</option>
                <option value="ollama">Ollama · servidor local</option>
              </select>
            </label>
            <div className="asr-fields">
              <label>
                Conteúdo
                <select
                  aria-label="Perfil de conteúdo"
                  value={options.content_profile}
                  onChange={(e) => change("content_profile", e.target.value)}
                >
                  {Object.entries({
                    gameplay: "Gameplay",
                    live: "Live de entretenimento",
                    podcast: "Podcast",
                    entrevista: "Entrevista",
                    react: "React",
                    informativo: "Informativo",
                    generico: "Genérico",
                  }).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Finalidade
                <select
                  aria-label="Finalidade dos cortes"
                  value={options.purpose}
                  onChange={(e) => change("purpose", e.target.value)}
                >
                  {Object.entries({
                    shorts: "YouTube Shorts",
                    reels: "Instagram Reels",
                    tiktok: "TikTok",
                    melhores_momentos: "Melhores momentos",
                    decupagem: "Decupagem geral",
                  }).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="analysis-durations">
              {number("min_duration", "Mínima (s)", 2, 300)}
              {number("preferred_duration", "Preferencial (s)", 2, 300)}
              {number("max_duration", "Máxima (s)", 2, 600)}
            </div>
            <div className="asr-fields">
              {number("margin_before", "Contexto antes (s)", 0, 30)}
              {number("margin_after", "Contexto depois (s)", 0, 30)}
            </div>
            <label className="asr-check">
              <input
                type="checkbox"
                checked={options.analyze_audio}
                onChange={(e) => change("analyze_audio", e.target.checked)}
              />
              <span>
                Analisar energia, picos e silêncio nas {props.audioCount}{" "}
                faixa(s) selecionada(s), separadamente
              </span>
            </label>
            <div className="asr-fields">
              {options.analyze_audio ? (
                number("silence_db", "Limiar de silêncio (dBFS)", -80, -15)
              ) : (
                <span />
              )}
              {number("max_suggestions", "Máximo de sugestões", 1, 100)}
            </div>
            {options.provider !== "local" && (
              <div className="provider-options">
                <label>
                  Modelo
                  <input
                    aria-label="Modelo de análise"
                    required
                    maxLength={100}
                    autoComplete="off"
                    placeholder="Nome do modelo disponível"
                    value={options.model}
                    onChange={(e) => change("model", e.target.value)}
                  />
                </label>
                {options.provider === "openai" ? (
                  <label>
                    Chave OpenAI · somente nesta execução
                    <input
                      aria-label="Chave OpenAI"
                      type="password"
                      autoComplete="off"
                      required
                      value={secret}
                      onChange={(e) => setSecret(e.target.value)}
                    />
                  </label>
                ) : (
                  number(
                    "ollama_port",
                    "Porta Ollama em 127.0.0.1",
                    1024,
                    65535,
                  )
                )}
                {number("max_blocks", "Limite de requisições/blocos", 1, 200)}
                <p className="asr-warning">
                  {plan?.provider_blocks == null
                    ? "Há trechos grandes demais para envio; use o modo local ou divida o texto."
                    : `${plan.provider_blocks} bloco(s), ${plan.characters.toLocaleString("pt-BR")} caracteres na transcrição. Blocos têm sobreposição.`}{" "}
                  {options.provider === "openai"
                    ? "Pode haver cobrança conforme sua conta OpenAI."
                    : "Nenhum modelo será baixado. Use apenas modelo local; tags cloud são bloqueadas."}
                </p>
                <p className="fine-print">
                  Cancelar encerra o cliente local; requisições já recebidas
                  pelo provedor podem continuar sendo processadas.
                </p>
                <label className="asr-check">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  <span>
                    Autorizo enviar a transcrição ao{" "}
                    {options.provider === "openai"
                      ? "OpenAI"
                      : `Ollama em 127.0.0.1:${options.ollama_port}`}{" "}
                    para esta análise. Vídeo e áudio não serão enviados.
                  </span>
                </label>
              </div>
            )}
            {props.analysis && (
              <label className="asr-check">
                <input
                  type="checkbox"
                  checked={replace}
                  onChange={(e) => setReplace(e.target.checked)}
                />
                <span>
                  Substituir sugestões anteriores somente após sucesso
                </span>
              </label>
            )}
            <p className="asr-privacy">
              <ShieldCheck size={13} />
              {options.provider === "local"
                ? "Nenhum serviço externo é usado no modo local."
                : "Credencial não é salva em projeto, cache ou relatório."}
            </p>
            <button
              className="primary full"
              type="submit"
              disabled={
                busy ||
                active(job) ||
                (props.analysis != null && !replace) ||
                (options.provider !== "local" &&
                  (!consent ||
                    !props.transcriptCount ||
                    plan?.provider_blocks == null ||
                    (plan.provider_blocks ?? 0) > options.max_blocks))
              }
            >
              <Sparkles size={14} /> Analisar momentos
            </button>
          </fieldset>
        </form>
      )}
      {job && (
        <div className={`asr-job ${job.status}`} role="status">
          <strong>
            {stages[job.stage] ?? job.stage}
            {job.cache_hit ? " · cache" : ""}
          </strong>
          {active(job) && (
            <>
              <progress
                max={100}
                {...(job.progress == null ? {} : { value: job.progress })}
              />
              <div className="asr-progress-label">
                <span>
                  {job.progress?.toFixed(1) ?? "—"}% do fluxo de análise
                </span>
                <button
                  className="text-button"
                  disabled={job.status === "cancelling"}
                  onClick={cancel}
                >
                  <Square size={10} /> Cancelar
                </button>
              </div>
            </>
          )}
          {job.error && <p>{job.error}</p>}
        </div>
      )}
      {error && (
        <p className="asr-error" role="alert">
          {error}
        </p>
      )}
      {props.analysis && (
        <>
          <details className="audio-summary">
            <summary>Indicadores medidos · mono / 8 kHz</summary>
            {props.analysis.audio.tracks.map((track) => (
              <div className="audio-metrics" key={track.stream}>
                <strong>Stream {track.stream}</strong>
                <span>
                  Pico {track.max_peak_db.toFixed(1)} dBFS · silêncio{" "}
                  {track.silence_seconds.toFixed(1)} s · {track.event_count}{" "}
                  eventos
                </span>
                <svg
                  viewBox="0 0 300 50"
                  role="img"
                  aria-label={`Curva de energia RMS do stream ${track.stream}`}
                >
                  <polyline
                    fill="none"
                    stroke="#e9b655"
                    strokeWidth="1.5"
                    points={track.curve
                      .map(
                        (p) =>
                          `${(p.time / track.measured_seconds) * 300},${50 - ((Math.max(-96, p.rms_db) + 96) / 96) * 48}`,
                      )
                      .join(" ")}
                  />
                </svg>
                <small>Energia RMS agregada; não é waveform de amostras.</small>
              </div>
            ))}
            <p>
              {props.analysis.speech_indicators.words_per_media_minute.toFixed(
                1,
              )}{" "}
              palavras/min de mídia, derivadas da transcrição.
            </p>
          </details>
          <div className="analysis-filters">
            <div className="transcript-search">
              <Search size={13} />
              <input
                aria-label="Buscar sugestões"
                placeholder="Buscar sugestões..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="asr-fields">
              <select
                aria-label="Filtrar categoria"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">Todas as categorias</option>
                {[...new Set(props.cuts.map((c) => c.category))].map((c) => (
                  <option key={c} value={c}>
                    {categories[c] ?? c}
                  </option>
                ))}
              </select>
              <select
                aria-label="Ordenar sugestões"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                <option value="score">Por pontuação</option>
                <option value="time">Cronológico</option>
              </select>
            </div>
            <label>
              Pontuação mínima: {score}
              <input
                aria-label="Pontuação mínima"
                type="range"
                min={0}
                max={100}
                value={score}
                onChange={(e) => setScore(Number(e.target.value))}
              />
            </label>
          </div>
          <div className="analysis-results">
            {filtered.map((cut) => (
              <article className="suggestion-card" key={cut.id}>
                <div className="suggestion-top">
                  <span>{categories[cut.category] ?? cut.category}</span>
                  <strong title="Estimativa editorial, não previsão de viralização">
                    {cut.score ?? "Manual/ajustado"}
                    {cut.score != null && <small>/100</small>}
                  </strong>
                </div>
                <small className="suggested-label">Título sugerido</small>
                <h3>{cut.title}</h3>
                <div className="suggestion-time">
                  <span>
                    {stamp(cut.start)} — {stamp(cut.end)} ·{" "}
                    {cut.duration.toFixed(1)} s
                  </span>
                  <button
                    className="icon-button"
                    aria-label={`Reproduzir sugestão ${cut.title}`}
                    title="Reproduzir intervalo sugerido"
                    onClick={() => props.onPreview(cut.start, cut.end)}
                  >
                    <Play size={16} />
                  </button>
                </div>
                <p>{cut.rationale}</p>
                <div className="suggestion-confidence">
                  {cut.confidence == null
                    ? "Sem estimativa de confiança"
                    : `Confiança estimada ${(cut.confidence * 100).toFixed(0)}%`}{" "}
                  ·{" "}
                  {cut.status === "approved"
                    ? "aprovado"
                    : cut.status === "rejected"
                      ? "rejeitado"
                      : "pendente"}
                </div>
                <details>
                  <summary>Evidências e interpretações</summary>
                  <p>{cut.description}</p>
                  <h4>
                    {cut.evidence_historical
                      ? "Evidências históricas · fontes alteradas"
                      : "Evidências observadas"}
                  </h4>
                  {cut.evidence.map((e, i) => (
                    <blockquote key={i}>
                      <small>
                        {e.kind === "audio"
                          ? "Medição de áudio"
                          : "Texto da transcrição"}{" "}
                        · {e.reference} · {stamp(e.start)}
                      </small>
                      {e.detail}
                    </blockquote>
                  ))}
                  {!!cut.context_evidence?.length && (
                    <p>
                      {cut.context_evidence.length} evidências do intervalo
                      anterior ficaram fora do corte ajustado.
                    </p>
                  )}
                  <h4>Inferências · precisam de revisão</h4>
                  {cut.inferences.map((text, i) => (
                    <p key={i}>{text}</p>
                  ))}
                  <h4>Gancho sugerido</h4>
                  <p>{cut.hook}</p>
                  <p className="asr-warning">
                    Não houve validação visual nem aprovação automática.
                  </p>
                </details>
              </article>
            ))}
            {!filtered.length && (
              <p className="analysis-empty">
                {props.cuts.length
                  ? "Nenhuma sugestão atende aos filtros."
                  : "Nenhum momento passou pelos critérios e durações. Isso é um resultado válido; revise as fontes ou ajuste as configurações."}
              </p>
            )}
          </div>
          <a
            className="secondary full analysis-export"
            href={`/api/projects/${props.projectId}/analysis/export`}
            download
          >
            <Download size={13} /> Baixar relatório JSON
          </a>
          <p className="fine-print">
            Aprove, rejeite e ajuste IN/OUT no editor de decupagem abaixo do
            player. A análise não altera a mídia.
          </p>
        </>
      )}
    </div>
  );
}
