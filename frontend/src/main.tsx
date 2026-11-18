import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  AudioLines,
  Check,
  ChevronRight,
  Clock3,
  Cpu,
  Download,
  FileText,
  Film,
  FolderOpen,
  HardDrive,
  Headphones,
  Home,
  Info,
  Layers3,
  LoaderCircle,
  MonitorPlay,
  Pause,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  SkipBack,
  SkipForward,
  SlidersHorizontal,
  Upload,
  Volume2,
  X,
} from "lucide-react";
import "./styles.css";
import { CutEditor } from "./CutEditor";
import { ExportPanel } from "./ExportPanel";
import {
  TranscriptionControls,
  processingStages,
  type TranscriptionSettings,
} from "./TranscriptionControls";
import { AnalysisPanel, type Analysis, type Suggestion } from "./AnalysisPanel";

type AudioTrack = {
  index: number;
  codec: string;
  channels: number;
  sample_rate: number;
  name: string;
  language: string;
};
type Segment = { id: number; start: number; end: number; text: string };
type Metadata = {
  duration: number;
  width: number;
  height: number;
  fps: number;
  frame_rate: string;
  video_codec: string;
  audio: AudioTrack[];
  size: number;
  browser_hint: boolean;
  mtime_ns: number;
};
export type Project = {
  revision: number;
  id: string;
  name: string;
  path: string;
  metadata: Metadata;
  selected_audio: number[];
  transcript: Segment[];
  transcript_source?: string;
  updated_at: string;
  available: boolean;
  settings?: { transcription?: TranscriptionSettings };
  cuts: Suggestion[];
  analysis?: Analysis | null;
};
type Recent = Pick<
  Project,
  "id" | "name" | "path" | "metadata" | "updated_at" | "available"
> & { transcript_count: number };
type Environment = {
  system: string;
  python: string;
  logical_cpus: number;
  ffmpeg: boolean;
  ffprobe: boolean;
  gpu: string | null;
  cuda_validated: boolean;
};
type Job = {
  id: string;
  status: string;
  progress: number;
  start: number;
  duration: number;
  index: number;
  error?: string;
};
type BackgroundJob = {
  options?: { provider?: string };
  id: string;
  kind: string;
  project_id: string | null;
  status: string;
  stage: string;
  progress: number | null;
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "X-Leonida-Client": "1",
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Operação não concluída (${response.status}). Verifique os dados informados.`,
    );
  }
  return response.json();
}
function time(seconds: number, fractional = false) {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const result = [
    Math.floor(safe / 3600),
    Math.floor(safe / 60) % 60,
    Math.floor(safe) % 60,
  ]
    .map((v) => String(v).padStart(2, "0"))
    .join(":");
  return (
    result +
    (fractional
      ? `.${String(Math.floor((safe % 1) * 1000)).padStart(3, "0")}`
      : "")
  );
}
const bytes = (n: number) =>
  n >= 1024 ** 3
    ? `${(n / 1024 ** 3).toFixed(2)} GB`
    : `${(n / 1024 ** 2).toFixed(1)} MB`;

function App() {
  const [view, changeView] = useState<"home" | "editor" | "settings">("home");
  const [cutDirty, setCutDirty] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const seenExport = useRef("");
  function guardDraft() {
    if (!cutDirty) return true;
    setError(
      "Salve ou descarte o ajuste do corte antes de sair ou alterar as fontes.",
    );
    return false;
  }
  function setView(next: "home" | "editor" | "settings") {
    if (guardDraft()) changeView(next);
  }
  const [recent, setRecent] = useState<Recent[]>([]);
  const [environment, setEnvironment] = useState<Environment | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [modal, setModal] = useState<"import" | "relink" | null>(null);
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [tab, setTab] = useState<
    "audio" | "transcript" | "metadata" | "analysis"
  >("audio");
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(1);
  const [speed, setSpeed] = useState(1);
  const [playerError, setPlayerError] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [job, setJob] = useState<Job | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [backgroundJobs, setBackgroundJobs] = useState<BackgroundJob[]>([]);
  useEffect(() => {
    const latest = backgroundJobs.find(
      (j) =>
        j.project_id === project?.id &&
        j.kind === "export" &&
        j.status === "completed",
    );
    if (!latest || !project || cutDirty || seenExport.current === latest.id)
      return;
    seenExport.current = latest.id;
    const id = project.id;
    api<Project>(`/projects/${id}`)
      .then((next) => {
        if (projectRef.current === id)
          setProject((current) =>
            current && current.revision > next.revision ? current : next,
          );
      })
      .catch(() => {
        seenExport.current = "";
      });
  }, [backgroundJobs, project?.id, cutDirty]);
  const video = useRef<HTMLVideoElement>(null);
  const clipEnd = useRef<number | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const transcriptInput = useRef<HTMLInputElement>(null);
  const projectRef = useRef<string | null>(null);
  useEffect(() => {
    clipEnd.current = null;
  }, [view, project?.id]);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const player = video.current;
      if (
        player &&
        clipEnd.current != null &&
        player.currentTime >= clipEnd.current
      ) {
        const end = clipEnd.current;
        player.pause();
        player.currentTime = end;
        setPosition(end);
        clipEnd.current = null;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);
  const modalRef = useRef<HTMLDialogElement>(null);
  const filtered = useMemo(
    () =>
      project?.transcript.filter((s) =>
        s.text
          .toLocaleLowerCase("pt-BR")
          .includes(search.toLocaleLowerCase("pt-BR")),
      ) ?? [],
    [project?.transcript, search],
  );
  const activeIndex = useMemo(() => {
    const rows = project?.transcript ?? [];
    let a = 0,
      b = rows.length - 1,
      best = -1;
    while (a <= b) {
      const mid = (a + b) >> 1;
      if (rows[mid].start <= position) {
        best = mid;
        a = mid + 1;
      } else b = mid - 1;
    }
    return best >= 0 && rows[best].end > position ? best : -1;
  }, [position, project?.transcript]);
  const active =
    project && activeIndex >= 0 ? project.transcript[activeIndex] : undefined;
  const refresh = () => api<Recent[]>("/projects").then(setRecent);
  const refreshProcessing = () =>
    api<BackgroundJob[]>("/processing").then(setBackgroundJobs);
  useEffect(() => {
    let disposed = false;
    const load = () =>
      api<BackgroundJob[]>("/processing")
        .then((rows) => {
          if (!disposed) setBackgroundJobs(rows);
        })
        .catch(() => {});
    load();
    const timer = setInterval(load, 2000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    Promise.all([
      refresh(),
      api<Environment>("/environment").then(setEnvironment),
    ]).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    projectRef.current = project?.id ?? null;
  }, [project?.id]);
  useEffect(() => {
    if (modal) modalRef.current?.showModal();
    else modalRef.current?.close();
  }, [modal]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const current = await api<Job>(`/jobs/${job.id}`);
        setJob((old) => (old?.id === current.id ? current : old));
        if (current.status === "completed")
          setPreviewUrl(`/api/jobs/${current.id}/audio`);
        if (current.status === "failed")
          setError(current.error ?? "Erro na prévia de áudio.");
      } catch (e) {
        setError((e as Error).message);
        setJob(null);
      }
    }, 500);
    return () => clearInterval(timer);
  }, [job?.id, job?.status]);
  useEffect(() => {
    if (playing && activeIndex >= 0 && !search)
      setPage(Math.floor(activeIndex / 100));
  }, [activeIndex, playing, search]);
  const report = (e: unknown) =>
    setError(
      e instanceof Error ? e.message : "Não foi possível concluir a operação.",
    );
  async function open(id: string) {
    if (!guardDraft()) return;
    setBusy("Abrindo projeto");
    setError("");
    try {
      if (job && ["queued", "running"].includes(job.status))
        await api(`/jobs/${job.id}`, { method: "DELETE" });
      const next = await api<Project>(`/projects/${id}`);
      video.current?.pause();
      audio.current?.pause();
      setProject(next);
      setView("editor");
      setPosition(0);
      setPlaying(false);
      setPlayerError("");
      setJob(null);
      setPreviewUrl("");
      setSearch("");
      setPage(0);
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  function seek(at: number) {
    clipEnd.current = null;
    if (video.current && project) {
      video.current.currentTime = Math.max(
        0,
        Math.min(at, project.metadata.duration),
      );
      setPosition(video.current.currentTime);
    }
  }
  async function choose() {
    setBusy("Selecionando arquivo");
    setError("");
    try {
      const result = await api<{ path: string }>("/dialog", { method: "POST" });
      if (result.path) setPath(result.path);
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  async function importMedia(event: React.FormEvent) {
    if (!guardDraft()) return;
    event.preventDefault();
    setBusy(
      modal === "relink" ? "Localizando mídia" : "Lendo mídia com FFprobe",
    );
    setError("");
    try {
      const next = await api<Project>(
        modal === "relink" && project
          ? `/projects/${project.id}/relink`
          : "/projects",
        { method: "POST", body: JSON.stringify({ path, name }) },
      );
      video.current?.pause();
      audio.current?.pause();
      setProject({ ...next, available: true });
      setView("editor");
      setModal(null);
      setPosition(0);
      setPlaying(false);
      setPlayerError("");
      setJob(null);
      setPreviewUrl("");
      setSearch("");
      setPage(0);
      await refresh();
      setNotice(
        "Mídia vinculada. O arquivo original permanece no local de origem.",
      );
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  async function selectTrack(index: number, checked: boolean) {
    if (!guardDraft()) return;
    if (!project) return;
    setBusy("Salvando faixas");
    try {
      setProject(
        await api<Project>(`/projects/${project.id}/audio`, {
          method: "PUT",
          body: JSON.stringify({
            indices: checked
              ? [...project.selected_audio, index]
              : project.selected_audio.filter((i) => i !== index),
          }),
        }),
      );
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  async function preview(index: number) {
    if (!project) return;
    setBusy("Preparando prévia");
    setPreviewUrl("");
    audio.current?.pause();
    video.current?.pause();
    try {
      const next = await api<Job>(`/projects/${project.id}/preview`, {
        method: "POST",
        body: JSON.stringify({ index, start: Math.floor(position) }),
      });
      setJob(next);
      if (next.status === "completed")
        setPreviewUrl(`/api/jobs/${next.id}/audio`);
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  async function importTranscript(file?: File) {
    if (!guardDraft()) return;
    if (!file || !project) return;
    const id = project.id;
    setBusy("Importando transcrição");
    setError("");
    try {
      if (file.size > 10 * 1024 ** 2)
        throw new Error("A transcrição deve ter até 10 MiB.");
      const data = new FormData();
      data.append("file", file);
      const next = await api<Project>(`/projects/${id}/transcript`, {
        method: "POST",
        body: data,
      });
      if (projectRef.current === id) {
        setProject(next);
        setTab("transcript");
        setPage(0);
        setSearch("");
      }
      await refresh();
      setNotice(
        `${next.transcript.length} trechos importados e salvos no projeto.`,
      );
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
      if (transcriptInput.current) transcriptInput.current.value = "";
    }
  }
  function openImport() {
    if (!guardDraft()) return;
    setModal("import");
    setPath("");
    setName("");
    setError("");
  }
  const pending = !!job && ["queued", "running"].includes(job.status);
  const activeBackground = backgroundJobs.find((j) =>
    ["queued", "running", "cancelling"].includes(j.status),
  );
  const projectBusy = backgroundJobs.some(
    (j) =>
      j.project_id === project?.id &&
      ["queued", "running", "cancelling"].includes(j.status),
  );

  return (
    <div className="app-shell">
      <aside className="rail">
        <button
          className="brand-icon"
          aria-label="Início Leonida"
          onClick={() => {
            video.current?.pause();
            audio.current?.pause();
            setView("home");
            refresh().catch(report);
          }}
        >
          <span>L</span>
          <i />
        </button>
        <div className="rail-nav">
          <button
            title="Projetos"
            aria-label="Projetos"
            className={view === "home" ? "active" : ""}
            onClick={() => {
              video.current?.pause();
              audio.current?.pause();
              setView("home");
              refresh().catch(report);
            }}
          >
            <Home size={21} />
          </button>
          <button
            title="Editor de mídia"
            aria-label="Editor de mídia"
            disabled={!project}
            className={view === "editor" ? "active" : ""}
            onClick={() => setView("editor")}
          >
            <MonitorPlay size={21} />
          </button>
        </div>
        <div className="rail-bottom">
          <button
            title="Ambiente e configurações"
            aria-label="Ambiente e configurações"
            className={view === "settings" ? "active" : ""}
            onClick={() => {
              video.current?.pause();
              audio.current?.pause();
              setView("settings");
            }}
          >
            <Settings2 size={21} />
          </button>
          <span className="studio-mark">BTRK</span>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="wordmark">
            LEONIDA <span>CLIP STUDIO</span>
            <small>v0.1.0</small>
          </div>
          <div className="topbar-right">
            <span className="local-status">
              <i /> AMBIENTE LOCAL
            </span>
            <span className="brand-by">
              por <b>BTRK Studio</b>
            </span>
          </div>
        </header>
        {error && (
          <div className="message error" role="alert">
            <Info size={17} />
            <span>{error}</span>
            <button aria-label="Fechar erro" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="message notice" role="status">
            <Check size={17} />
            <span>{notice}</span>
            <button aria-label="Fechar aviso" onClick={() => setNotice("")}>
              <X size={16} />
            </button>
          </div>
        )}

        {view === "home" && (
          <main
            className="home-page"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              openImport();
              setNotice(
                "O navegador não fornece o caminho absoluto do arquivo arrastado. Use “Selecionar vídeo” ou cole o caminho para vinculá-lo sem cópia.",
              );
            }}
          >
            <div className="page-heading">
              <div>
                <span className="eyebrow">SEU ESPAÇO DE CRIAÇÃO</span>
                <h1>Todo grande corte começa aqui.</h1>
                <p>
                  Menos trabalho repetitivo. Mais tempo para contar boas
                  histórias.
                </p>
              </div>
              <span className="version-pill">PILOTO · FASE 1F</span>
            </div>
            <section className="import-hero">
              <div className="hero-copy">
                <span className="eyebrow gold">DO VÍDEO À HISTÓRIA</span>
                <h2>
                  O próximo momento
                  <br />
                  merece ser encontrado<span>.</span>
                </h2>
                <p>
                  Abra sua gravação, conheça suas faixas de áudio
                  <br className="desktop-br" /> e organize a transcrição em um
                  só lugar.
                </p>
                <button
                  className="primary"
                  onClick={openImport}
                  disabled={!!busy}
                >
                  <Plus size={18} /> Novo projeto <ArrowRight size={17} />
                </button>
                <div className="hero-foot">
                  <ShieldCheck size={14} /> Seus arquivos permanecem no seu
                  computador.
                </div>
              </div>
              <div className="hero-art" aria-hidden="true">
                <div className="art-grid" />
                <div className="art-frame">
                  <div className="art-frame-head">
                    <span />
                    <span />
                    <span />
                    <small>LEONIDA / ORIGINAL MEDIA</small>
                  </div>
                  <div className="art-visual">
                    <div className="art-orbit" />
                    <div className="art-play">
                      <Play size={32} fill="currentColor" />
                    </div>
                    <span>ENCONTRE A SUA HISTÓRIA</span>
                  </div>
                  <div className="art-timeline">
                    <span />
                    <span />
                    <span />
                    <span />
                    <span />
                    <span />
                    <i />
                  </div>
                </div>
                <div className="art-tag">
                  <Layers3 size={16} />
                  <span>
                    Várias faixas.
                    <br />
                    <b>Um fluxo de trabalho.</b>
                  </span>
                </div>
              </div>
            </section>
            <section className="recent-section">
              <div className="section-title">
                <div>
                  <h2>
                    Projetos recentes{" "}
                    <span>{recent.length.toString().padStart(2, "0")}</span>
                  </h2>
                  <p>Continue de onde você parou.</p>
                </div>
                <button
                  className="text-button"
                  onClick={() => refresh().catch(report)}
                  disabled={!!busy}
                >
                  Atualizar <Activity size={15} />
                </button>
              </div>
              {recent.length ? (
                <div className="project-list">
                  {recent.map((p) => (
                    <button
                      key={p.id}
                      className="project-row"
                      disabled={!!busy}
                      onClick={() => open(p.id)}
                    >
                      <div className="project-thumb">
                        <Film size={25} />
                      </div>
                      <div className="project-name">
                        <strong>{p.name}</strong>
                        <span title={p.path}>{p.path}</span>
                      </div>
                      <div className="project-meta">
                        <span>{time(p.metadata.duration)}</span>
                        <small>
                          {p.metadata.width} × {p.metadata.height} ·{" "}
                          {p.metadata.audio.length} faixas
                        </small>
                      </div>
                      <span
                        className={
                          p.available ? "file-state" : "file-state missing"
                        }
                      >
                        {p.available ? "Vinculado" : "Mídia ausente"}
                      </span>
                      <ChevronRight size={18} />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-projects">
                  <div className="empty-icon">
                    <FolderOpen size={26} />
                  </div>
                  <div>
                    <h3>Seu primeiro projeto está a um clique.</h3>
                    <p>
                      Importe um vídeo local para começar. MP4, MKV, MOV ou
                      WEBM.
                    </p>
                  </div>
                  <button className="secondary" onClick={openImport}>
                    <Upload size={16} /> Importar vídeo
                  </button>
                </div>
              )}
            </section>
            <div className="home-bottom">
              <div>
                <HardDrive size={18} />
                <span>
                  <b>Originais preservados</b>
                  <small>
                    Importação por referência, sem duplicar o vídeo.
                  </small>
                </span>
              </div>
              <div>
                <AudioLines size={18} />
                <span>
                  <b>Áudio em suas mãos</b>
                  <small>Identifique e escute cada faixa separadamente.</small>
                </span>
              </div>
              <div>
                <FileText size={18} />
                <span>
                  <b>Comece pela transcrição</b>
                  <small>Importe SRT ou CSV, sem executar modelos de IA.</small>
                </span>
              </div>
            </div>
          </main>
        )}

        {view === "settings" && (
          <main className="settings-page">
            <button className="text-button" onClick={() => setView("home")}>
              <ArrowLeft size={16} /> Projetos
            </button>
            <span className="eyebrow">ESTAÇÃO DE TRABALHO</span>
            <h1>Ambiente e configurações</h1>
            <p className="muted">
              Diagnóstico real dos recursos disponíveis nesta instalação.
            </p>
            <div className="settings-grid">
              <section className="panel setting-card">
                <Cpu size={26} />
                <h2>Processamento local</h2>
                <dl>
                  <dt>Sistema</dt>
                  <dd>{environment?.system ?? "Indisponível"}</dd>
                  <dt>Python</dt>
                  <dd>{environment?.python ?? "—"}</dd>
                  <dt>Processadores lógicos</dt>
                  <dd>{environment?.logical_cpus ?? "—"}</dd>
                  <dt>GPU / VRAM / driver</dt>
                  <dd>{environment?.gpu ?? "Não detectada"}</dd>
                  <dt>CUDA com Faster Whisper</dt>
                  <dd>Ainda não validado</dd>
                </dl>
              </section>
              <section className="panel setting-card">
                <SlidersHorizontal size={26} />
                <h2>Perfil inicial</h2>
                <dl>
                  <dt>Dispositivo recomendado</dt>
                  <dd>CPU</dd>
                  <dt>Perfil</dt>
                  <dd>Econômico · 2 threads por prévia</dd>
                  <dt>FFmpeg</dt>
                  <dd>{environment?.ffmpeg ? "Disponível" : "Ausente"}</dd>
                  <dt>FFprobe</dt>
                  <dd>{environment?.ffprobe ? "Disponível" : "Ausente"}</dd>
                  <dt>Armazenamento padrão</dt>
                  <dd>.local / SQLite e cache de prévias</dd>
                </dl>
              </section>
            </div>
            <div className="inline-info">
              <ShieldCheck size={20} />
              <div>
                <strong>Fluxo básico sem serviços externos</strong>
                <p>
                  O modo local mantém mídia e transcrição no computador. A
                  transcrição está no painel Texto e as sugestões no painel
                  Análise. Downloads de modelos exigem confirmação.
                  OpenAI/Ollama só recebem texto quando você seleciona o
                  provedor e autoriza cada execução.
                </p>
              </div>
            </div>
          </main>
        )}

        {view === "editor" && project && (
          <main className="editor-page">
            <div className="editor-heading">
              <div className="editor-breadcrumb">
                <button
                  aria-label="Voltar aos projetos"
                  onClick={() => {
                    video.current?.pause();
                    audio.current?.pause();
                    setView("home");
                    refresh().catch(report);
                  }}
                >
                  <ArrowLeft size={18} />
                </button>
                <span>PROJETO</span>
                <ChevronRight size={14} />
                <h1 title={project.path}>{project.name}</h1>
                <span className="saved">
                  <Check size={12} />{" "}
                  {cutDirty ? "Ajuste não salvo" : "Salvo localmente"}
                </span>
              </div>
              <div className="editor-delivery-actions">
                <button
                  className="primary"
                  disabled={!!busy || cutDirty}
                  onClick={() => {
                    video.current?.pause();
                    audio.current?.pause();
                    setShowExport(true);
                  }}
                >
                  <Download size={15} /> Exportar
                </button>
                <button
                  className="secondary"
                  onClick={openImport}
                  disabled={!!busy}
                >
                  <Plus size={15} /> Novo projeto
                </button>
              </div>
            </div>
            <div className="editor-grid">
              <section className="viewer-panel panel">
                <div className="panel-heading">
                  <span>
                    <MonitorPlay size={16} /> Monitor de origem
                  </span>
                  <span className="mono">
                    {project.metadata.width} × {project.metadata.height} <i />{" "}
                    {project.metadata.fps.toFixed(3)} FPS
                  </span>
                </div>
                <div className="video-stage">
                  <video
                    key={`${project.id}-${project.metadata.mtime_ns}-${project.path}`}
                    ref={video}
                    src={
                      project.available === false
                        ? undefined
                        : `/api/projects/${project.id}/media`
                    }
                    preload="metadata"
                    onTimeUpdate={(e) => {
                      setPosition(e.currentTarget.currentTime);
                      if (
                        clipEnd.current != null &&
                        e.currentTarget.currentTime >= clipEnd.current
                      ) {
                        e.currentTarget.pause();
                        clipEnd.current = null;
                      }
                    }}
                    onPlay={() => {
                      audio.current?.pause();
                      setPlaying(true);
                    }}
                    onPause={() => setPlaying(false)}
                    onEnded={() => setPlaying(false)}
                    onError={() =>
                      setPlayerError(
                        "O navegador não conseguiu reproduzir esta mídia. O suporte a contêiner e codec depende do navegador; use um MP4 H.264/AAC para validar o player nesta fase.",
                      )
                    }
                    onLoadedMetadata={(e) => {
                      e.currentTarget.volume = volume;
                      e.currentTarget.playbackRate = speed;
                      setPlayerError("");
                    }}
                  />
                  {(project.available === false || playerError) && (
                    <div className="player-overlay">
                      <Film size={34} />
                      <h3>
                        {project.available === false
                          ? "Arquivo original não encontrado"
                          : "Reprodução indisponível"}
                      </h3>
                      <p>
                        {project.available === false
                          ? "A referência foi preservada. Localize a mídia para continuar."
                          : playerError}
                      </p>
                      <button
                        className="secondary"
                        onClick={() => {
                          setModal("relink");
                          setPath("");
                          setError("");
                        }}
                      >
                        <FolderOpen size={16} /> Localizar mídia
                      </button>
                    </div>
                  )}
                  {active && !playerError && (
                    <div className="subtitle-preview">{active.text}</div>
                  )}
                  <span className="stage-label">
                    ORIGINAL <i /> {project.metadata.video_codec.toUpperCase()}
                  </span>
                </div>
                <div className="transport">
                  <span className="timecode">
                    {time(position, true)}{" "}
                    <small>/ {time(project.metadata.duration)}</small>
                  </span>
                  <div className="transport-buttons">
                    <button
                      title="Voltar 5 segundos"
                      aria-label="Voltar 5 segundos"
                      onClick={() => seek(position - 5)}
                    >
                      <SkipBack size={18} />
                    </button>
                    <button
                      className="play-button"
                      title={playing ? "Pausar" : "Reproduzir"}
                      aria-label={playing ? "Pausar" : "Reproduzir"}
                      onClick={() => {
                        if (video.current)
                          playing
                            ? video.current.pause()
                            : video.current.play().catch(report);
                      }}
                    >
                      {playing ? (
                        <Pause size={20} fill="currentColor" />
                      ) : (
                        <Play size={20} fill="currentColor" />
                      )}
                    </button>
                    <button
                      title="Avançar 5 segundos"
                      aria-label="Avançar 5 segundos"
                      onClick={() => seek(position + 5)}
                    >
                      <SkipForward size={18} />
                    </button>
                  </div>
                  <div className="play-options">
                    <Volume2 size={15} />
                    <input
                      aria-label="Volume do vídeo"
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={volume}
                      onChange={(e) => {
                        setVolume(Number(e.target.value));
                        if (video.current)
                          video.current.volume = Number(e.target.value);
                      }}
                    />
                    <select
                      aria-label="Velocidade de reprodução"
                      value={speed}
                      onChange={(e) => {
                        setSpeed(Number(e.target.value));
                        if (video.current)
                          video.current.playbackRate = Number(e.target.value);
                      }}
                    >
                      {[0.5, 0.75, 1, 1.25, 1.5, 2].map((s) => (
                        <option key={s} value={s}>
                          {s}×
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="viewer-note">
                  <Info size={13} />
                  <span>
                    O player usa o áudio padrão do navegador. Para identificar
                    outras faixas, use a escuta individual ao lado.
                  </span>
                </div>
              </section>
              <aside className="inspector panel">
                <div
                  className="inspector-tabs"
                  role="tablist"
                  aria-label="Informações do projeto"
                >
                  <button
                    role="tab"
                    aria-selected={tab === "audio"}
                    className={tab === "audio" ? "selected" : ""}
                    onClick={() => setTab("audio")}
                  >
                    <AudioLines size={15} /> Áudio
                  </button>
                  <button
                    role="tab"
                    aria-selected={tab === "transcript"}
                    className={tab === "transcript" ? "selected" : ""}
                    onClick={() => setTab("transcript")}
                  >
                    <FileText size={15} /> Texto
                  </button>
                  <button
                    role="tab"
                    aria-selected={tab === "analysis"}
                    className={tab === "analysis" ? "selected" : ""}
                    onClick={() => setTab("analysis")}
                  >
                    <Sparkles size={14} /> Análise
                  </button>
                  <button
                    role="tab"
                    aria-selected={tab === "metadata"}
                    className={tab === "metadata" ? "selected" : ""}
                    onClick={() => setTab("metadata")}
                  >
                    <Info size={15} /> Mídia
                  </button>
                </div>
                {tab === "analysis" && (
                  <AnalysisPanel
                    key={project.id}
                    projectId={project.id}
                    audioCount={project.selected_audio.length}
                    transcriptCount={project.transcript.length}
                    cuts={project.cuts ?? []}
                    analysis={project.analysis}
                    processing={projectBusy || cutDirty}
                    onTaskStarted={() => {
                      refreshProcessing().catch(report);
                    }}
                    onApplied={() => {
                      const id = project.id;
                      api<Project>(`/projects/${id}`)
                        .then((next) => {
                          if (projectRef.current === id) setProject(next);
                        })
                        .catch(report);
                    }}
                    onPreview={(start, end) => {
                      seek(start);
                      clipEnd.current = end;
                      video.current?.play().catch(report);
                    }}
                  />
                )}
                {tab === "audio" && (
                  <div className="inspector-content">
                    <div className="inspector-title">
                      <span className="eyebrow">MAPA DE ÁUDIO</span>
                      <h2>
                        {project.metadata.audio.length}{" "}
                        {project.metadata.audio.length === 1
                          ? "faixa identificada"
                          : "faixas identificadas"}
                      </h2>
                      <p>
                        Escolha as faixas para transcrição local. Nenhuma é
                        selecionada automaticamente.
                      </p>
                    </div>
                    <div className="audio-track-list">
                      {project.metadata.audio.map((a, i) => (
                        <div
                          className={`audio-track ${project.selected_audio.includes(a.index) ? "chosen" : ""}`}
                          key={a.index}
                        >
                          <div className="audio-track-header">
                            <span className="track-number">A{i + 1}</span>
                            <label>
                              <input
                                type="checkbox"
                                checked={project.selected_audio.includes(
                                  a.index,
                                )}
                                disabled={!!busy || projectBusy || cutDirty}
                                onChange={(e) =>
                                  selectTrack(a.index, e.target.checked)
                                }
                              />
                              <strong>{a.name}</strong>
                            </label>
                            <button
                              title={`Ouvir ${a.name}`}
                              aria-label={`Ouvir ${a.name}`}
                              disabled={
                                !!busy || pending || project.available === false
                              }
                              onClick={() => preview(a.index)}
                            >
                              <Headphones size={17} />
                            </button>
                          </div>
                          <div className="track-info">
                            <span>Stream {a.index}</span>
                            <span>{a.codec.toUpperCase()}</span>
                            <span>{a.channels} ch</span>
                            <span>{(a.sample_rate / 1000).toFixed(1)} kHz</span>
                          </div>
                        </div>
                      ))}
                    </div>
                    {!project.metadata.audio.length && (
                      <p className="muted">
                        Esta mídia não contém faixas de áudio.
                      </p>
                    )}
                    <div className="audio-preview">
                      <div className="preview-label">
                        <Headphones size={15} />
                        <strong>Escuta individual</strong>
                        <span>ATÉ 30 S</span>
                      </div>
                      {pending && job ? (
                        <>
                          <p>Gerando prévia · stream {job.index}</p>
                          <progress max={100} value={job.progress} />
                          <div className="preview-progress">
                            <span>
                              {Math.floor(job.progress)}% ·{" "}
                              {job.status === "queued"
                                ? "Na fila"
                                : "Processando"}
                            </span>
                            <button
                              className="text-button"
                              onClick={async () => {
                                try {
                                  setJob(
                                    await api<Job>(`/jobs/${job.id}`, {
                                      method: "DELETE",
                                    }),
                                  );
                                } catch (e) {
                                  report(e);
                                }
                              }}
                            >
                              Cancelar
                            </button>
                          </div>
                        </>
                      ) : previewUrl && job ? (
                        <>
                          <p>
                            Stream {job.index} · {time(job.start)} —{" "}
                            {time(job.start + job.duration)}
                          </p>
                          <audio
                            ref={audio}
                            controls
                            src={previewUrl}
                            onPlay={() => video.current?.pause()}
                          />
                        </>
                      ) : (
                        <p>
                          {job?.status === "cancelled"
                            ? "Prévia cancelada. Selecione uma faixa para tentar novamente."
                            : "Clique nos fones de uma faixa. A prévia começa na posição atual do vídeo."}
                        </p>
                      )}
                    </div>
                    <div className="selection-summary">
                      <Check size={14} />
                      {project.selected_audio.length
                        ? `${project.selected_audio.length} faixa(s) selecionada(s) e salva(s)`
                        : "Selecione a voz principal após escutar as faixas."}
                    </div>
                  </div>
                )}
                {tab === "metadata" && (
                  <div className="inspector-content">
                    <div className="inspector-title">
                      <span className="eyebrow">ARQUIVO ORIGINAL</span>
                      <h2>Detalhes da mídia</h2>
                    </div>
                    <dl className="metadata-list">
                      <dt>Duração</dt>
                      <dd>{time(project.metadata.duration, true)}</dd>
                      <dt>Resolução</dt>
                      <dd>
                        {project.metadata.width} × {project.metadata.height}
                      </dd>
                      <dt>Taxa de quadros</dt>
                      <dd>
                        {project.metadata.frame_rate} (
                        {project.metadata.fps.toFixed(3)} FPS)
                      </dd>
                      <dt>Codec de vídeo</dt>
                      <dd>{project.metadata.video_codec}</dd>
                      <dt>Tamanho</dt>
                      <dd>{bytes(project.metadata.size)}</dd>
                      <dt>Localização</dt>
                      <dd className="file-path">{project.path}</dd>
                    </dl>
                    <button
                      className="secondary full"
                      onClick={() => {
                        setModal("relink");
                        setPath("");
                        setError("");
                      }}
                      disabled={!!busy || projectBusy || cutDirty}
                    >
                      <FolderOpen size={15} /> Relocalizar arquivo
                    </button>
                    <p className="fine-print">
                      Se o arquivo substituído for diferente, transcrição e
                      seleção de faixas serão limpas. Mantenha uma cópia do
                      texto exportado.
                    </p>
                    {!project.metadata.browser_hint && (
                      <div className="codec-warning">
                        <Info size={16} />
                        <p>
                          Esta mídia pode ter limitações de reprodução no
                          navegador. A importação via FFprobe funciona
                          independentemente do suporte do player.
                        </p>
                      </div>
                    )}
                  </div>
                )}
                {tab === "transcript" && (
                  <div className="transcript-panel">
                    <div className="transcript-top">
                      <div>
                        <span className="eyebrow">TRANSCRIÇÃO</span>
                        <h2>
                          {project.transcript.length
                            ? `${project.transcript.length} trechos`
                            : "Palavras com contexto."}
                        </h2>
                      </div>
                      <button
                        className="icon-button"
                        title="Importar ou substituir transcrição"
                        aria-label="Importar ou substituir transcrição"
                        disabled={!!busy || projectBusy || cutDirty}
                        onClick={() => transcriptInput.current?.click()}
                      >
                        <Upload size={17} />
                      </button>
                    </div>
                    <TranscriptionControls
                      key={project.id}
                      projectId={project.id}
                      audioCount={project.selected_audio.length}
                      transcriptCount={project.transcript.length}
                      position={position}
                      duration={project.metadata.duration}
                      initial={project.settings?.transcription}
                      processing={projectBusy || cutDirty}
                      onTaskStarted={() => {
                        refreshProcessing().catch(report);
                      }}
                      onApplied={() => {
                        const id = project.id;
                        api<Project>(`/projects/${id}`)
                          .then((next) => {
                            if (projectRef.current === id) setProject(next);
                          })
                          .catch(report);
                      }}
                    />
                    {project.transcript.length ? (
                      <>
                        <div className="transcript-search">
                          <Search size={15} />
                          <input
                            aria-label="Buscar na transcrição"
                            placeholder="Buscar na transcrição..."
                            value={search}
                            onChange={(e) => {
                              setSearch(e.target.value);
                              setPage(0);
                            }}
                          />
                        </div>
                        <div className="transcript-segments">
                          {filtered
                            .slice(page * 100, page * 100 + 100)
                            .map((s) => (
                              <button
                                className={`segment ${active?.id === s.id ? "current" : ""}`}
                                key={s.id}
                                onClick={() => seek(s.start)}
                              >
                                <span>{time(s.start)}</span>
                                <p>{s.text}</p>
                              </button>
                            ))}
                          {!filtered.length && (
                            <p className="muted">Nenhum trecho encontrado.</p>
                          )}
                        </div>
                        <div className="pagination">
                          <button
                            aria-label="Página anterior"
                            disabled={page === 0}
                            onClick={() => setPage((p) => p - 1)}
                          >
                            <ArrowLeft size={14} />
                          </button>
                          <span>
                            {page + 1} /{" "}
                            {Math.max(1, Math.ceil(filtered.length / 100))}
                          </span>
                          <button
                            aria-label="Próxima página"
                            disabled={(page + 1) * 100 >= filtered.length}
                            onClick={() => setPage((p) => p + 1)}
                          >
                            <ArrowRight size={14} />
                          </button>
                        </div>
                        <div className="transcript-exports">
                          <span>Exportar</span>
                          {["srt", "csv", "json", "txt"].map((f) => (
                            <a
                              key={f}
                              href={`/api/projects/${project.id}/transcript/${f}`}
                              download
                            >
                              <Download size={11} />
                              {f.toUpperCase()}
                            </a>
                          ))}
                        </div>
                      </>
                    ) : (
                      <div className="transcript-empty">
                        <FileText size={34} />
                        <h3>Traga sua transcrição.</h3>
                        <p>
                          Importe SRT ou CSV do Premiere e navegue pelo vídeo
                          clicando nos trechos. Nenhum modelo precisa ser
                          executado.
                        </p>
                        <button
                          className="secondary"
                          disabled={!!busy}
                          onClick={() => transcriptInput.current?.click()}
                        >
                          <Upload size={16} /> Importar SRT / CSV
                        </button>
                        <small>
                          CSV: Start, End, Text ou Início, Fim, Texto.
                          <br />
                          Timecodes HH:MM:SS:FF usam o FPS da mídia; drop-frame
                          não é suportado.
                        </small>
                      </div>
                    )}
                  </div>
                )}
              </aside>
              <CutEditor
                key={project.id}
                project={project}
                position={position}
                busy={
                  !!busy ||
                  backgroundJobs.some(
                    (j) =>
                      j.project_id === project.id &&
                      j.kind !== "waveform" &&
                      ["queued", "running", "cancelling"].includes(j.status),
                  )
                }
                onDirty={setCutDirty}
                onProject={setProject}
                onSeek={seek}
                onToggle={() => {
                  if (video.current?.paused) video.current.play().catch(report);
                  else video.current?.pause();
                }}
                onPreview={(start, end) => {
                  seek(start);
                  clipEnd.current = end;
                  video.current?.play().catch(report);
                }}
              />
            </div>
          </main>
        )}

        <footer className="statusbar">
          <span>
            {busy || activeBackground ? (
              <LoaderCircle size={12} className="spin" />
            ) : (
              <i className="status-dot" />
            )}
            {busy ||
              (activeBackground
                ? `${activeBackground.kind === "model_download" ? "Modelo" : activeBackground.kind === "analysis" ? "Análise" : activeBackground.kind === "waveform" ? "Waveform" : activeBackground.kind === "export" ? "Exportação" : "Transcrição local"} · ${processingStages[activeBackground.stage] ?? activeBackground.stage}${activeBackground.progress == null ? "" : ` · ${Math.floor(activeBackground.progress)}%`}`
                : pending
                  ? `Prévia em processamento · ${Math.floor(job!.progress)}%`
                  : "Pronto para criar")}
          </span>
          <span>
            {environment?.ffprobe
              ? "FFprobe disponível"
              : "Verificando FFprobe"}
            <i />
            {activeBackground?.kind === "analysis" &&
            activeBackground.options?.provider !== "local"
              ? `TEXTO AUTORIZADO · ${activeBackground.options?.provider?.toUpperCase() ?? "PROVEDOR"}`
              : "LOCAL · SEM ENVIO AUTOMÁTICO"}
            <i />
            BTRK STUDIO © 2026
          </span>
        </footer>
      </div>
      <input
        ref={transcriptInput}
        type="file"
        accept=".srt,.csv"
        className="visually-hidden"
        onChange={(e) => importTranscript(e.target.files?.[0])}
      />
      {showExport && project && (
        <ExportPanel
          key={project.id}
          project={project}
          processing={projectBusy}
          onClose={() => setShowExport(false)}
          onStarted={() => refreshProcessing().catch(report)}
          onApplied={() => {
            const id = project.id;
            api<Project>(`/projects/${id}`)
              .then((next) => {
                if (projectRef.current === id) setProject(next);
              })
              .catch(report);
            refresh().catch(report);
            refreshProcessing().catch(report);
          }}
        />
      )}
      <dialog
        ref={modalRef}
        onCancel={(e) => {
          if (busy) e.preventDefault();
          else setModal(null);
        }}
      >
        <form onSubmit={importMedia}>
          <div className="modal-heading">
            <div className="modal-icon">
              <Film size={23} />
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label="Fechar"
              disabled={!!busy}
              onClick={() => setModal(null)}
            >
              <X size={20} />
            </button>
          </div>
          <span className="eyebrow">
            {modal === "relink" ? "RECUPERAR REFERÊNCIA" : "NOVO PROJETO"}
          </span>
          <h2>
            {modal === "relink"
              ? "Localize sua mídia."
              : "Vamos abrir uma história."}
          </h2>
          <p className="muted">
            Selecione o vídeo original. Ele será vinculado ao projeto sem cópia
            ou alteração.
          </p>
          <button
            type="button"
            className="file-picker"
            onClick={choose}
            disabled={!!busy}
          >
            <FolderOpen size={27} />
            <strong>
              {busy === "Selecionando arquivo"
                ? "Aguardando seleção no Windows…"
                : "Selecionar vídeo no computador"}
            </strong>
            <span>MP4 · MKV · MOV · WEBM</span>
          </button>
          <label className="field-label" htmlFor="media-path">
            Caminho absoluto do arquivo
          </label>
          <input
            id="media-path"
            autoFocus
            required
            placeholder="C:\Gravações\minha-gravacao.mp4"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            disabled={!!busy}
          />
          {modal === "import" && (
            <>
              <label className="field-label" htmlFor="project-name">
                Nome do projeto <small>opcional</small>
              </label>
              <input
                id="project-name"
                placeholder="Usar o nome do arquivo"
                value={name}
                maxLength={160}
                onChange={(e) => setName(e.target.value)}
                disabled={!!busy}
              />
            </>
          )}
          {modal === "relink" && (
            <p className="fine-print">
              Um arquivo diferente limpa a transcrição e seleção anteriores.
              Exporte sua transcrição antes de substituir a mídia.
            </p>
          )}
          {error && (
            <p className="modal-error" role="alert">
              {error}
            </p>
          )}
          <div className="modal-actions">
            <button
              type="button"
              className="text-button"
              onClick={() => setModal(null)}
              disabled={!!busy}
            >
              Cancelar
            </button>
            <button className="primary" disabled={!!busy || !path.trim()}>
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <ArrowRight size={16} />
              )}{" "}
              {busy ||
                (modal === "relink" ? "Atualizar referência" : "Criar projeto")}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
