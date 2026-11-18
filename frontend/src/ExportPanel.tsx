import { useEffect, useRef, useState } from "react";
import { Download, FolderOpen, LoaderCircle, X } from "lucide-react";
import type { Project } from "./main";
import { timestamp } from "./CutEditor";
import { processingStages } from "./TranscriptionControls";

type Props = {
  project: Project;
  processing: boolean;
  onClose: () => void;
  onStarted: () => void;
  onApplied: () => void;
};
type Plan = {
  token: string;
  destination: string;
  files: string[];
  cuts: { id: string; title: string; start: number; end: number }[];
  total_source_seconds: number;
  sequence_seconds: number;
  warnings: string[];
  audio: { index: number; name: string }[];
};
type Job = {
  id: string;
  kind: string;
  status: string;
  stage: string;
  progress: number | null;
  error?: string;
  files?: string[];
  export_folder?: string;
  warnings?: string[];
  completed_units?: number;
  total_units?: number;
  options?: { expected_revision: number };
};
type History = {
  id: string;
  created_at: string;
  cut_count: number;
  revision: number;
  formats: string[];
  folder: string;
};
const labels: Record<string, string> = {
  mp4: "MP4 individuais",
  xml: "XML FCP7 · Premiere",
  json: "Relatório JSON",
  csv: "Relatório CSV",
  txt: "Relatório TXT",
  srt: "SRT por corte + sequência",
};
const active = (j: Job | null) =>
  !!j && ["queued", "running", "cancelling"].includes(j.status);
async function api<T>(
  path: string,
  body?: unknown,
  method = body ? "POST" : "GET",
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: { "X-Leonida-Client": "1", "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Confira as opções informadas.",
    );
  return data;
}

export function ExportPanel(props: Props) {
  const p = props.project,
    approved = p.cuts
      .filter((c) => c.status === "approved")
      .sort((a, b) => a.start - b.start);
  const [ids, setIds] = useState(approved.map((c) => c.id));
  const [formats, setFormats] = useState(["mp4", "json", "srt"]);
  const [tracks, setTracks] = useState(p.selected_audio);
  const [destination, setDestination] = useState("");
  const [method, setMethod] = useState("precise");
  const [mode, setMode] = useState("compact");
  const [quality, setQuality] = useState(20);
  const [fastAck, setFastAck] = useState(false);
  const [cfr, setCfr] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [history, setHistory] = useState<History[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [fileSearch, setFileSearch] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const seen = useRef("");
  const options = {
    expected_revision: p.revision,
    ids,
    formats,
    audio_indices: tracks,
    destination,
    method,
    sequence_mode: mode,
    crf: quality,
    acknowledge_fast: fastAck,
    confirm_cfr: cfr,
  };
  const serialized = JSON.stringify(options);
  const running = active(job),
    locked = running || pending || props.processing;
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  useEffect(() => {
    setPlan(null);
  }, [serialized]);
  useEffect(() => {
    let mounted = true;
    Promise.all([
      api<History[]>(`/projects/${p.id}/exports`),
      api<Job[]>(`/processing?project_id=${p.id}`),
    ])
      .then(([past, jobs]) => {
        if (mounted) {
          setHistory(past);
          setJob(jobs.find((j) => j.kind === "export") ?? null);
        }
      })
      .catch((e) => {
        if (mounted) setError(e.message);
      });
    return () => {
      mounted = false;
    };
  }, [p.id]);
  useEffect(() => {
    if (!job || !active(job)) return;
    let mounted = true;
    const timer = setInterval(
      () =>
        api<Job>(`/processing/${job.id}`)
          .then((next) => {
            if (!mounted) return;
            setJob(next);
            if (next.status === "completed" && seen.current !== next.id) {
              seen.current = next.id;
              props.onApplied();
              api<History[]>(`/projects/${p.id}/exports`)
                .then(setHistory)
                .catch((e) => setError(e.message));
            }
            if (next.status === "failed")
              setError(next.error ?? "Falha na exportação.");
          })
          .catch((e) => {
            if (mounted) setError(e.message);
          }),
      600,
    );
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [job?.id, job?.status]);
  const toggle = (values: string[], value: string) =>
    values.includes(value)
      ? values.filter((v) => v !== value)
      : [...values, value];
  async function preview() {
    setPending(true);
    setError("");
    try {
      setPlan(await api(`/projects/${p.id}/exports/plan`, options));
    } catch (e) {
      setError((e as Error).message);
      setPlan(null);
    } finally {
      setPending(false);
    }
  }
  async function start() {
    if (!plan) return;
    setPending(true);
    setError("");
    try {
      setJob(
        await api(`/projects/${p.id}/exports`, {
          ...options,
          plan_token: plan.token,
        }),
      );
      setPlan(null);
      props.onStarted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  async function chooseFolder() {
    setPending(true);
    setError("");
    try {
      const value = await api<{ path: string }>(
        "/dialog/directory",
        {},
        "POST",
      );
      if (value.path) setDestination(value.path);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <dialog
      className="export-dialog"
      ref={dialog}
      onCancel={(e) => {
        e.preventDefault();
        if (!pending) props.onClose();
      }}
      aria-labelledby="export-heading"
    >
      <header>
        <div>
          <span className="eyebrow">ENTREGA · ORIGINAIS PRESERVADOS</span>
          <h2 id="export-heading">Exportar decupagem</h2>
          <p>
            {p.name} · revisão {p.revision}
          </p>
        </div>
        <button
          className="icon-button"
          aria-label="Fechar exportação"
          disabled={pending}
          onClick={props.onClose}
        >
          <X size={20} />
        </button>
      </header>
      {error && (
        <div role="alert" className="export-error">
          {error}
        </div>
      )}
      <div className="export-columns">
        <div className="export-options">
          <fieldset disabled={locked}>
            <legend>1 · Cortes aprovados</legend>
            <div className="export-selection">
              <button onClick={() => setIds(approved.map((c) => c.id))}>
                Todos
              </button>
              <button onClick={() => setIds([])}>Limpar</button>
              <small>
                {ids.length} selecionados de {approved.length}
              </small>
            </div>
            <div className="export-cuts">
              {approved.map((c) => (
                <label key={c.id}>
                  <input
                    type="checkbox"
                    checked={ids.includes(c.id)}
                    onChange={() => setIds(toggle(ids, c.id))}
                  />
                  <span>
                    {c.title}
                    <small>
                      {timestamp(c.start)} → {timestamp(c.end)}
                    </small>
                  </span>
                </label>
              ))}
              {!approved.length && (
                <p>Aprove cortes no editor antes de exportar.</p>
              )}
            </div>
          </fieldset>
          <fieldset disabled={locked}>
            <legend>2 · Arquivos e sequência</legend>
            <div className="export-format-grid">
              {Object.entries(labels).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={formats.includes(key)}
                    onChange={() => setFormats(toggle(formats, key))}
                  />
                  {label}
                </label>
              ))}
            </div>
            <label className="export-field">
              Posição dos cortes na sequência
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="compact">Consolidada · sem lacunas</option>
                <option value="original">
                  Original · preservar posições/lacunas
                </option>
              </select>
            </label>
            <p>
              Clipes MP4 são individuais. O modo da sequência aplica-se ao XML,
              relatório e SRT de sequência.
            </p>
            {formats.includes("xml") && (
              <label className="export-ack">
                <input
                  type="checkbox"
                  checked={cfr}
                  onChange={(e) => setCfr(e.target.checked)}
                />
                Confirmo que a fonte usa FPS constante (CFR). XML usa quadros e
                timecode zero/NDF; validar no Premiere.
              </label>
            )}
          </fieldset>
          <fieldset disabled={locked}>
            <legend>3 · Faixas de áudio</legend>
            {p.metadata.audio.map((a) => (
              <label className="export-audio" key={a.index}>
                <input
                  type="checkbox"
                  checked={tracks.includes(a.index)}
                  onChange={() =>
                    setTracks(
                      tracks.includes(a.index)
                        ? tracks.filter((i) => i !== a.index)
                        : [...tracks, a.index],
                    )
                  }
                />
                #{a.index} · {a.name} <small>{a.channels} canais</small>
              </label>
            ))}
            <p>
              {tracks.length
                ? "Cada faixa selecionada permanece separada no MP4. XML referencia os canais da mídia original."
                : "Nenhuma faixa selecionada: MP4/XML somente com vídeo."}
            </p>
          </fieldset>
          {formats.includes("mp4") && (
            <fieldset disabled={locked}>
              <legend>4 · MP4</legend>
              <label className="export-field">
                Método
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                >
                  <option value="precise">
                    Recodificar · cortes mais precisos (H.264/AAC)
                  </option>
                  <option value="fast">
                    Cópia rápida · corte aproximado (stream copy)
                  </option>
                </select>
              </label>
              {method === "precise" ? (
                <>
                  <label className="export-field">
                    Qualidade CRF · menor valor = arquivo maior
                    <select
                      value={quality}
                      onChange={(e) => setQuality(Number(e.target.value))}
                    >
                      <option value={18}>18 · alta</option>
                      <option value={20}>20 · padrão</option>
                      <option value={23}>23 · econômica</option>
                    </select>
                  </label>
                  <p>
                    Resolução original, timestamps/FPS da fonte, duas threads de
                    CPU. A precisão depende dos quadros e amostras disponíveis.
                  </p>
                </>
              ) : (
                <label className="export-ack">
                  <input
                    type="checkbox"
                    checked={fastAck}
                    onChange={(e) => setFastAck(e.target.checked)}
                  />
                  Aceito início no quadro-chave anterior, conteúdo extra e
                  duração/legendas aproximadas. XML mantém os IN/OUT aprovados.
                </label>
              )}
            </fieldset>
          )}
          <fieldset disabled={locked}>
            <legend>5 · Destino</legend>
            <div className="export-destination">
              <input
                aria-label="Pasta de destino"
                placeholder="Padrão: armazenamento local / exports"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              />
              <button
                onClick={chooseFolder}
                aria-label="Escolher pasta de destino"
              >
                <FolderOpen size={16} />
              </button>
            </div>
            <p>
              Uma pasta nova por lote. Não sobrescreve exportações anteriores.
            </p>
          </fieldset>
        </div>
        <div className="export-results">
          <section className="export-preview">
            <h3>Conferir antes de exportar</h3>
            <p>
              Somente cortes aprovados. Notas, evidências e sugestões não
              aprovadas não entram como clipes adicionais.
            </p>
            <button
              className="secondary"
              disabled={locked || !ids.length || !formats.length}
              onClick={preview}
            >
              {pending ? <LoaderCircle className="spin" size={14} /> : null}{" "}
              Atualizar prévia
            </button>
            {plan && (
              <>
                <div className="export-summary">
                  <strong>
                    {plan.cuts.length} cortes · {plan.files.length} arquivos
                  </strong>
                  <span>
                    {plan.total_source_seconds.toFixed(3)} s de cortes ·
                    sequência {plan.sequence_seconds.toFixed(3)} s
                  </span>
                  <span>
                    Áudio:{" "}
                    {plan.audio
                      .map((a) => `#${a.index} ${a.name}`)
                      .join(", ") || "sem áudio"}
                  </span>
                  <code>{plan.destination}</code>
                </div>
                <ul className="export-warnings">
                  {plan.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
                <details>
                  <summary>Arquivos planejados ({plan.files.length})</summary>
                  <div className="export-planned-files">
                    {plan.files.map((f) => (
                      <code key={f}>{f}</code>
                    ))}
                  </div>
                </details>
                <button className="primary" disabled={locked} onClick={start}>
                  <Download size={15} /> Exportar {plan.cuts.length} corte(s)
                  aprovado(s)
                </button>
              </>
            )}
            {!plan && !running && (
              <p className="fine-print">
                Altere as opções e atualize a prévia. Qualquer mudança invalida
                a prévia anterior.
              </p>
            )}
          </section>
          {job && (
            <section className="export-task">
              <h3>
                {running
                  ? "Exportação em andamento"
                  : job.status === "completed"
                    ? "Lote concluído"
                    : job.status === "cancelled"
                      ? "Exportação cancelada"
                      : "Última tarefa de exportação"}
              </h3>
              <p>
                {processingStages[job.stage] ?? job.stage}{" "}
                {job.progress != null ? `· ${Math.floor(job.progress)}%` : ""}
                {job.total_units
                  ? ` · ${job.status === "completed" ? job.total_units : (job.completed_units ?? 0)}/${job.total_units} cortes`
                  : ""}
              </p>
              {running && (
                <>
                  <progress max={100} value={job.progress ?? 0} />
                  <button
                    disabled={job.status === "cancelling"}
                    onClick={() =>
                      api<Job>(`/processing/${job.id}`, undefined, "DELETE")
                        .then(setJob)
                        .catch((e) => setError(e.message))
                    }
                  >
                    Cancelar exportação
                  </button>
                  <p>
                    Você pode fechar este painel; a tarefa continua.
                    Cancelamento remove somente o lote temporário.
                  </p>
                </>
              )}
              {job.error && <p role="alert">{job.error}</p>}
              {job.status === "completed" && (
                <>
                  <code className="export-folder">{job.export_folder}</code>
                  <small>
                    Revisão exportada: {job.options?.expected_revision}. Os
                    arquivos já estão salvos na pasta; baixar cria uma cópia
                    pelo navegador.
                  </small>
                  <input
                    aria-label="Filtrar arquivos exportados"
                    placeholder="Filtrar arquivos"
                    value={fileSearch}
                    onChange={(e) => setFileSearch(e.target.value)}
                  />
                  <div className="export-file-list">
                    {job.files
                      ?.filter((name) =>
                        name
                          .toLocaleLowerCase()
                          .includes(fileSearch.toLocaleLowerCase()),
                      )
                      .slice(0, 100)
                      .map((name) => (
                        <a
                          key={name}
                          href={`/api/exports/${job.id}/files/${encodeURIComponent(name)}`}
                          download
                        >
                          <Download size={12} />
                          {name}
                        </a>
                      ))}
                  </div>
                  <small>Exibindo até 100 arquivos por filtro.</small>
                </>
              )}
            </section>
          )}
          <section className="export-history">
            <h3>Lotes publicados ({history.length})</h3>
            {history
              .slice()
              .reverse()
              .slice(0, 20)
              .map((item) => (
                <button
                  disabled={locked}
                  key={item.id}
                  onClick={() =>
                    api<Job>(`/processing/${item.id}`)
                      .then((j) => {
                        setJob(j);
                        setFileSearch("");
                      })
                      .catch((e) => setError(e.message))
                  }
                >
                  <span>
                    {new Date(item.created_at).toLocaleString("pt-BR")} ·{" "}
                    {item.cut_count} cortes · revisão {item.revision}
                  </span>
                  <small>{item.formats.join(" · ")}</small>
                </button>
              ))}
            {!history.length && <p>Nenhum lote concluído neste projeto.</p>}
          </section>
        </div>
      </div>
      <footer>
        <span>
          XML FCP7 preparado para revisão no Premiere · sem garantia de
          importação validada no aplicativo
        </span>
        <button onClick={props.onClose} disabled={pending}>
          Fechar
        </button>
      </footer>
    </dialog>
  );
}
