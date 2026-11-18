import { useEffect, useRef, useState } from "react";
import {
  Cpu,
  Download,
  LoaderCircle,
  Mic,
  Square,
  ShieldCheck,
} from "lucide-react";

type Model = {
  name: string;
  label: string;
  approx_mb: number;
  installed: boolean;
};
type Capabilities = {
  cuda_libraries_available: boolean;
  cuda_missing_libraries: string[];
  installed: boolean;
  models: Model[];
  cuda_devices: number;
};
type ProcessingJob = {
  created_at: string;
  options: { model: string };
  id: string;
  kind: string;
  project_id: string | null;
  status: string;
  stage: string;
  progress: number | null;
  error?: string;
  cache_hit: boolean;
  segments?: number;
  processed_seconds?: number;
  completed_units?: number;
  total_units?: number;
  unit?: string;
};
export type TranscriptionSettings = {
  profile: string;
  model: string;
  language: string;
  device: string;
  threads: number;
};
type Props = {
  projectId: string;
  audioCount: number;
  transcriptCount: number;
  position: number;
  duration: number;
  initial?: TranscriptionSettings;
  onApplied: () => void;
  onTaskStarted: () => void;
  processing?: boolean;
};
const active = (j: ProcessingJob) =>
  ["queued", "running", "cancelling"].includes(j.status);
export const processingStages: Record<string, string> = {
  exporting_video: "Exportando MP4",
  exporting_reports: "Gerando relatórios e legendas",
  verifying_export: "Validando e publicando lote",
  waveform: "Gerando waveform",
  queued: "Na fila",
  starting: "Iniciando processo local",
  connecting: "Conectando ao repositório de modelos",
  downloading: "Baixando pesos do modelo",
  verifying: "Validando modelo por CPU",
  loading_model: "Carregando modelo local",
  extracting: "Extraindo áudio selecionado",
  transcribing: "Transcrevendo fala",
  saving: "Validando e salvando",
  completed: "Concluído",
  cancelling: "Encerrando processo",
  cancelled: "Cancelado",
  interrupted: "Interrompido",
  failed: "Falha",
  analyzing_audio: "Medindo áudio por faixa",
  analyzing_text: "Analisando texto",
  provider_request: "Consultando provedor autorizado",
  ranking: "Classificando sugestões",
};
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
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : "Confira as configurações da transcrição.",
    );
  return result;
}

export function TranscriptionControls(props: Props) {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [options, setOptions] = useState<TranscriptionSettings>(
    props.initial ?? {
      profile: "economico",
      model: "tiny",
      language: "auto",
      device: "cpu",
      threads: 2,
    },
  );
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [downloadConsent, setDownloadConsent] = useState(false);
  const [replace, setReplace] = useState(false);
  const [sample, setSample] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(props.transcriptCount === 0);
  const callback = useRef(props.onApplied);
  callback.current = props.onApplied;
  const seen = useRef(new Set<string>());
  const current = jobs.find(
    (j) => j.kind === "transcription" && j.project_id === props.projectId,
  );
  const downloading = jobs.find(
    (j) => j.kind === "model_download" && active(j),
  );
  const running = current && active(current);
  const model = caps?.models.find((m) => m.name === options.model);
  useEffect(() => {
    let stopped = false;
    let fetching = false;
    let modelsLoaded = false;
    const load = async () => {
      if (fetching) return;
      fetching = true;
      try {
        const [projectJobs, globalJobs] = await Promise.all([
          request<ProcessingJob[]>(`/processing?project_id=${props.projectId}`),
          request<ProcessingJob[]>("/processing"),
        ]);
        if (stopped) return;
        const combined = [
          ...projectJobs.filter((j) => j.kind === "transcription"),
          ...globalJobs.filter((j) => j.kind === "model_download"),
        ].sort((a, b) => b.created_at.localeCompare(a.created_at));
        setJobs(combined);
        let updateModels = false;
        for (const job of combined) {
          if (!active(job) && !seen.current.has(job.id)) {
            seen.current.add(job.id);
            if (job.kind === "transcription" && job.status === "completed")
              callback.current();
            if (job.kind === "model_download") updateModels = true;
          }
        }
        if (updateModels || !modelsLoaded) {
          const info = await request<Capabilities>(
            "/transcription/capabilities",
          );
          if (!stopped) setCaps(info);
          modelsLoaded = true;
        }
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      } finally {
        fetching = false;
      }
    };
    load();
    const timer = setInterval(load, 1500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [props.projectId]);

  async function run(kind: "download" | "transcribe") {
    setBusy(true);
    setError("");
    try {
      const job =
        kind === "download"
          ? await request<ProcessingJob>(
              "/transcription/models",
              { model: options.model, consent: downloadConsent },
              "POST",
            )
          : await request<ProcessingJob>(
              `/projects/${props.projectId}/transcribe`,
              {
                ...options,
                replace_existing: replace,
                start: sample
                  ? Math.min(props.position, Math.max(0, props.duration - 0.1))
                  : 0,
                end: sample
                  ? Math.min(props.duration, props.position + 30)
                  : null,
              },
              "POST",
            );
      setJobs((previous) => [job, ...previous.filter((j) => j.id !== job.id)]);
      props.onTaskStarted();
      setExpanded(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel(id: string) {
    setBusy(true);
    try {
      const result = await request<ProcessingJob>(
        `/processing/${id}`,
        undefined,
        "DELETE",
      );
      setJobs((rows) => rows.map((j) => (j.id === id ? result : j)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const shown =
    downloading ??
    jobs.find(
      (j) => j.kind === "transcription" || j.options.model === options.model,
    );
  return (
    <section className="asr-controls">
      <button
        className="asr-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span>
          <Mic size={15} /> Transcrição local
        </span>
        <span>
          {running ? (
            <LoaderCircle size={13} className="spin" />
          ) : expanded ? (
            "−"
          ) : (
            "+"
          )}
        </span>
      </button>
      {expanded && (
        <div className="asr-form">
          <p className="asr-privacy">
            <ShieldCheck size={13} /> Processamento no computador. Sem envio de
            áudio ou texto.
          </p>
          {caps && !caps.installed && (
            <p className="asr-error">
              Faster Whisper ausente. Execute Configurar Leonida Clip
              Studio.bat.
            </p>
          )}
          <fieldset disabled={busy || !!running || props.processing}>
            <label>
              Perfil
              <select
                aria-label="Perfil de transcrição"
                value={options.profile}
                onChange={(e) => {
                  const profile = e.target.value;
                  setOptions((o) => ({
                    ...o,
                    profile,
                    model:
                      profile === "economico"
                        ? "tiny"
                        : profile === "equilibrado"
                          ? "base"
                          : "small",
                    threads: profile === "economico" ? 2 : 4,
                  }));
                  setDownloadConsent(false);
                }}
              >
                <option value="economico">Econômico</option>
                <option value="equilibrado">Equilibrado</option>
                <option value="alta_qualidade">Alta qualidade</option>
              </select>
            </label>
            <div className="asr-fields">
              <label>
                Modelo
                <select
                  aria-label="Modelo de transcrição"
                  value={options.model}
                  onChange={(e) => {
                    setOptions((o) => ({ ...o, model: e.target.value }));
                    setDownloadConsent(false);
                  }}
                >
                  {(
                    caps?.models ?? [
                      {
                        name: "tiny",
                        label: "Tiny",
                        installed: false,
                        approx_mb: 75,
                      },
                    ]
                  ).map((m) => (
                    <option value={m.name} key={m.name}>
                      {m.label} {m.installed ? "· local" : "· baixar"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Idioma
                <select
                  aria-label="Idioma da transcrição"
                  value={options.language}
                  onChange={(e) =>
                    setOptions((o) => ({ ...o, language: e.target.value }))
                  }
                >
                  <option value="auto">Detectar</option>
                  <option value="pt">Português</option>
                  <option value="en">Inglês</option>
                </select>
              </label>
            </div>
            <div className="asr-fields">
              <label>
                Dispositivo
                <select
                  aria-label="Dispositivo de transcrição"
                  value={options.device}
                  onChange={(e) =>
                    setOptions((o) => ({ ...o, device: e.target.value }))
                  }
                >
                  <option value="cpu">CPU · int8</option>
                  <option
                    value="cuda"
                    disabled={!caps?.cuda_libraries_available}
                  >
                    GPU CUDA · experimental
                  </option>
                </select>
              </label>
              <label>
                Threads
                <select
                  aria-label="Limite de threads"
                  value={options.threads}
                  onChange={(e) =>
                    setOptions((o) => ({
                      ...o,
                      threads: Number(e.target.value),
                    }))
                  }
                >
                  {[1, 2, 3, 4].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {caps?.cuda_devices && !caps.cuda_libraries_available ? (
              <p className="asr-warning">
                GPU detectada, mas as bibliotecas CUDA/cuDNN necessárias não
                estão disponíveis. Use CPU.
              </p>
            ) : null}
            {options.device === "cuda" && (
              <p className="asr-warning">
                CUDA detectada não garante cuBLAS/cuDNN compatíveis. Se houver
                falha, selecione CPU; nenhum driver será instalado.
              </p>
            )}
            {!model?.installed && (
              <div className="asr-download">
                <label className="asr-check">
                  <input
                    type="checkbox"
                    checked={downloadConsent}
                    onChange={(e) => setDownloadConsent(e.target.checked)}
                  />
                  <span>
                    Autorizo baixar os pesos do modelo selecionado do Hugging
                    Face (~{model?.approx_mb ?? 75} MB). Requer internet apenas
                    para o download.
                  </span>
                </label>
                <button
                  className="secondary full"
                  disabled={
                    !caps?.installed || !downloadConsent || !!downloading
                  }
                  onClick={() => run("download")}
                >
                  <Download size={13} /> Baixar {model?.label ?? "Tiny"}
                </button>
              </div>
            )}
            <label className="asr-check">
              <input
                type="checkbox"
                checked={sample}
                onChange={(e) => setSample(e.target.checked)}
              />
              <span>Testar até 30 s a partir da posição atual</span>
            </label>
            {props.transcriptCount > 0 && (
              <label className="asr-check">
                <input
                  type="checkbox"
                  checked={replace}
                  onChange={(e) => setReplace(e.target.checked)}
                />
                <span>Substituir a transcrição atual somente após sucesso</span>
              </label>
            )}
            <p className="asr-summary">
              <Cpu size={12} /> {props.audioCount} faixa(s) selecionada(s)
              {props.audioCount > 1 ? " · mixagem normalizada" : ""}
            </p>
            <button
              className="primary full"
              disabled={
                !model?.installed ||
                !props.audioCount ||
                (props.transcriptCount > 0 && !replace) ||
                !!running
              }
              onClick={() => run("transcribe")}
            >
              <Mic size={14} />{" "}
              {running
                ? "Transcrevendo…"
                : sample
                  ? "Transcrever trecho de teste"
                  : "Transcrever vídeo"}
            </button>
          </fieldset>
          {shown && (
            <div className={`asr-job ${shown.status}`} role="status">
              <strong>
                {processingStages[shown.stage] ?? shown.stage}
                {shown.cache_hit ? " · cache" : ""}
              </strong>
              {active(shown) && (
                <>
                  <progress
                    max={100}
                    {...(shown.progress == null
                      ? {}
                      : { value: shown.progress })}
                  />
                  <div className="asr-progress-label">
                    <span>
                      {shown.progress == null
                        ? shown.unit === "bytes"
                          ? `${((shown.completed_units ?? 0) / 1024 ** 2).toFixed(1)} MB recebidos`
                          : "Preparando modelo"
                        : `${shown.progress.toFixed(1)}% de áudio processado`}
                    </span>
                    <button
                      className="text-button"
                      disabled={busy || shown.status === "cancelling"}
                      onClick={() => cancel(shown.id)}
                    >
                      <Square size={10} /> Cancelar
                    </button>
                  </div>
                </>
              )}
              {shown.status === "completed" &&
                shown.kind === "transcription" && (
                  <p>
                    {shown.segments ?? 0} trechos salvos. A transcrição
                    automática pode conter erros; revise o texto.
                  </p>
                )}
              {shown.error && <p>{shown.error}</p>}
              {shown.status === "cancelled" && (
                <p>A transcrição anterior foi preservada.</p>
              )}
            </div>
          )}
          {error && (
            <p className="asr-error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
