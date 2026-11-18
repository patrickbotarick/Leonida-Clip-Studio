import { useEffect, useRef, useState } from "react";
import type { Project } from "./main";
import { categories, type Suggestion } from "./AnalysisPanel";

type Props = {
  project: Project;
  position: number;
  busy: boolean;
  onProject: (p: Project) => void;
  onSeek: (n: number) => void;
  onPreview: (a: number, b: number) => void;
  onDirty: (dirty: boolean) => void;
  onToggle: () => void;
};
type Editor = {
  can_undo: boolean;
  can_redo: boolean;
  overlap_ids: string[];
  archives: {
    id: number;
    created_at: string;
    cut_count: number;
    reason: string;
    compatible: boolean;
  }[];
};
type Draft = {
  id?: string;
  start: string;
  end: string;
  title: string;
  note: string;
};
type Wave = { start: number; step: number; peaks: number[][] };
const statuses: Record<string, string> = {
  pending: "Pendente",
  approved: "Aprovado",
  rejected: "Rejeitado",
};
export function timestamp(n: number) {
  const ms = Math.round(n * 1000);
  return `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
}
function seconds(s: string) {
  if (!/^\d+(?::[0-5]?\d){0,2}(?:[.,]\d{1,6})?$/.test(s.trim())) return NaN;
  return s
    .replace(",", ".")
    .split(":")
    .reduce((a, b) => a * 60 + Number(b), 0);
}
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body ? "POST" : "GET",
    headers: { "X-Leonida-Client": "1", "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Confira os valores informados.",
    );
  return data;
}
function fromCut(cut: Suggestion): Draft {
  return {
    id: cut.id,
    start: timestamp(cut.start),
    end: timestamp(cut.end),
    title: cut.title,
    note: cut.review_note ?? "",
  };
}

export function CutEditor(props: Props) {
  const p = props.project,
    duration = p.metadata.duration;
  const [editor, setEditor] = useState<Editor | null>(null);
  const [ids, setIds] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [align, setAlign] = useState(false);
  const [allowGaps, setAllowGaps] = useState(false);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [minDuration, setMinDuration] = useState(0);
  const [maxDuration, setMaxDuration] = useState("");
  const [query, setQuery] = useState("");
  const [jump, setJump] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState(0);
  const [track, setTrack] = useState(
    p.selected_audio[0] ?? p.metadata.audio[0]?.index ?? -1,
  );
  const [wave, setWave] = useState<Wave | null>(null);
  const [ready, setReady] = useState(false);
  const [job, setJob] = useState<{
    id: string;
    status: string;
    progress: number;
    error?: string;
  } | null>(null);
  const [waveError, setWaveError] = useState("");
  const trackRef = useRef<HTMLDivElement>(null);
  const dragged = useRef(false);
  const drag = useRef<{
    edge: string;
    x: number;
    start: number;
    end: number;
    width: number;
  } | null>(null);
  const span = duration / zoom,
    left = Math.min(pan, duration - span),
    right = left + span;
  const locked = saving || props.busy;
  const selected = p.cuts.filter((c) => ids.includes(c.id));
  const single = selected.length === 1 ? selected[0] : null;
  const filtered = p.cuts
    .filter(
      (c) =>
        (!status || c.status === status) &&
        (!category || c.category === category) &&
        (c.score ?? 0) >= minScore &&
        c.duration >= minDuration &&
        (!maxDuration || c.duration <= Number(maxDuration)) &&
        `${c.title} ${c.transcript_excerpt}`
          .toLocaleLowerCase()
          .includes(query.toLocaleLowerCase()),
    )
    .sort((a, b) => a.start - b.start);
  const changes = (next: Draft) => {
    setDraft(next);
    setDirty(true);
  };
  const guard = () => {
    if (dirty) {
      setError(
        "Salve ou descarte o ajuste em aberto antes de trocar de corte ou revisar.",
      );
      return false;
    }
    return true;
  };
  useEffect(() => {
    props.onDirty(dirty || saving);
    return () => props.onDirty(false);
  }, [dirty, saving]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty || saving) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty, saving]);
  useEffect(() => {
    let active = true;
    request<Editor>(`/projects/${p.id}/editor`)
      .then((result) => {
        if (active) setEditor(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [p.id, p.revision]);
  useEffect(() => {
    setWave(null);
    setReady(false);
    setJob(null);
    setWaveError("");
    let active = true;
    if (track >= 0)
      request<{ ready: boolean }>(`/projects/${p.id}/waveform/${track}`)
        .then((r) => {
          if (active) setReady(r.ready);
        })
        .catch((e) => {
          if (active) setWaveError(e.message);
        });
    return () => {
      active = false;
    };
  }, [p.id, p.path, p.metadata.mtime_ns, track]);
  useEffect(() => {
    if (!job || !["queued", "running", "cancelling"].includes(job.status))
      return;
    let active = true;
    const timer = setInterval(() => {
      request<typeof job>(`/processing/${job.id}`)
        .then((r) => {
          if (!active || !r) return;
          setJob(r);
          if (r.status === "completed") setReady(true);
          if (r.status === "failed")
            setWaveError(r.error ?? "Falha na waveform.");
        })
        .catch((e) => {
          if (active) setWaveError(e.message);
        });
    }, 800);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job?.id, job?.status]);
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetch(
        `/api/projects/${p.id}/waveform/${track}/range?start=${left}&end=${right}&points=1600`,
        { signal: controller.signal },
      )
        .then(async (r) => {
          if (!r.ok) throw new Error("Não foi possível consultar a waveform.");
          return r.json();
        })
        .then(setWave)
        .catch((e) => {
          if (e.name !== "AbortError") setWaveError(e.message);
        });
    }, 100);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [ready, p.id, track, left, right]);
  async function command(body: Record<string, unknown>, allowDirty = false) {
    if (locked || (!allowDirty && !guard())) return;
    setSaving(true);
    setError("");
    try {
      const result = await request<{
        project: Project;
        selected_ids: string[];
        editor: Editor;
      }>(`/projects/${p.id}/cuts`, { ...body, expected_revision: p.revision });
      props.onProject(result.project);
      setEditor(result.editor);
      setIds(result.selected_ids);
      const cut = result.project.cuts.find(
        (c) => c.id === result.selected_ids[0],
      );
      setDraft(cut ? fromCut(cut) : null);
      setDirty(false);
      setAllowGaps(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  function choose(cut: Suggestion, multi = false) {
    if (!guard()) return;
    setError("");
    if (multi) {
      setIds(
        ids.includes(cut.id)
          ? ids.filter((id) => id !== cut.id)
          : [...ids, cut.id],
      );
      setDraft(null);
    } else {
      setIds([cut.id]);
      setDraft(fromCut(cut));
      props.onSeek(cut.start);
    }
  }
  function mark(edge: "start" | "end") {
    if (locked) return;
    const base = draft ?? {
      start: timestamp(props.position),
      end: timestamp(
        Math.min(
          duration,
          props.position + Math.max(1, 1 / (p.metadata.fps || 25)),
        ),
      ),
      title: "Corte manual",
      note: "",
    };
    changes({ ...base, [edge]: timestamp(props.position) });
  }
  function save() {
    if (!draft) return;
    const original = p.cuts.find((c) => c.id === draft.id);
    const start =
      original && draft.start === timestamp(original.start)
        ? original.start
        : seconds(draft.start);
    const end =
      original && draft.end === timestamp(original.end)
        ? original.end
        : seconds(draft.end);
    if (
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      start >= end ||
      end > duration
    ) {
      setError(
        "Use 0 ≤ IN < OUT ≤ duração. Formato: HH:MM:SS.mmm ou segundos.",
      );
      return;
    }
    command(
      {
        action: draft.id ? "update" : "create",
        ids: draft.id ? [draft.id] : [],
        start,
        end,
        title: draft.title,
        note: draft.note,
        align_to_transcript: align,
      },
      true,
    );
  }
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement).closest(
          "input,textarea,select,[contenteditable]",
        ) ||
        document.querySelector("dialog[open]")
      )
        return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        command({ action: e.shiftKey ? "redo" : "undo" });
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key.toLowerCase() === "i") {
        e.preventDefault();
        mark("start");
      } else if (e.key.toLowerCase() === "o") {
        e.preventDefault();
        mark("end");
      } else if (e.code === "Space") {
        if ((e.target as HTMLElement).closest("button")) return;
        e.preventDefault();
        props.onToggle();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        props.onSeek(
          Math.max(
            0,
            Math.min(
              duration,
              props.position +
                (e.key === "ArrowLeft" ? -1 : 1) / (p.metadata.fps || 25),
            ),
          ),
        );
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });
  async function generate() {
    setWaveError("");
    try {
      setJob(await request(`/projects/${p.id}/waveform`, { index: track }));
    } catch (e) {
      setWaveError((e as Error).message);
    }
  }
  const waveformPath =
    wave?.peaks
      .map(([min, max], i) => {
        const x = ((wave.start + i * wave.step - left) / span) * 1000;
        return `M${x.toFixed(2)},${(35 - max * 32).toFixed(2)}V${(35 - min * 32).toFixed(2)}`;
      })
      .join("") ?? "";
  function beginDrag(e: React.PointerEvent, edge: string, cut: Suggestion) {
    e.stopPropagation();
    if (e.ctrlKey || e.metaKey) return;
    if (locked || (dirty && draft?.id !== cut.id)) return;
    dragged.current = false;
    const base = draft?.id === cut.id ? draft : fromCut(cut);
    const a = seconds(base.start),
      b = seconds(base.end);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return;
    setDraft(base);
    drag.current = {
      edge,
      x: e.clientX,
      start: a,
      end: b,
      width: trackRef.current?.clientWidth || 1,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function moveDrag(e: React.PointerEvent) {
    const current = drag.current;
    if (!current || !draft) return;
    if (Math.abs(e.clientX - current.x) < 2 && !dragged.current) return;
    dragged.current = true;
    setIds([draft.id!]);
    const delta = ((e.clientX - current.x) / current.width) * span;
    const frame = 1 / (p.metadata.fps || 1000);
    let a = current.start,
      b = current.end;
    if (current.edge === "start")
      a = Math.max(0, Math.min(b - frame, a + delta));
    else if (current.edge === "end")
      b = Math.min(duration, Math.max(a + frame, b + delta));
    else {
      a = Math.max(0, Math.min(duration - (b - a), a + delta));
      b = a + current.end - current.start;
    }
    changes({ ...draft, start: timestamp(a), end: timestamp(b) });
  }
  return (
    <section className="cut-workspace panel" aria-label="Editor de decupagem">
      <div className="cut-toolbar">
        <strong>
          DECUPAGEM <small>ORIGEM · {p.cuts.length} cortes</small>
        </strong>
        <button
          disabled={locked || dirty || !editor?.can_undo}
          onClick={() => command({ action: "undo" })}
        >
          ↶ Desfazer
        </button>
        <button
          disabled={locked || dirty || !editor?.can_redo}
          onClick={() => command({ action: "redo" })}
        >
          ↷ Refazer
        </button>
        <button
          disabled={locked || dirty}
          onClick={() => {
            setIds([]);
            changes({
              start: timestamp(props.position),
              end: timestamp(
                Math.min(duration, props.position + Math.min(30, duration)),
              ),
              title: "Corte manual",
              note: "",
            });
          }}
        >
          + Corte manual
        </button>
        <label>
          Zoom{" "}
          <select
            value={zoom}
            onChange={(e) => {
              setZoom(Number(e.target.value));
              setPan(
                Math.min(
                  props.position,
                  duration - duration / Number(e.target.value),
                ),
              );
            }}
          >
            {[1, 2, 4, 8, 16, 32, 64, 128].map((z) => (
              <option key={z} value={z}>
                {z}×
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => setPan(Math.max(0, props.position - span / 2))}>
          Ver playhead
        </button>
        <form
          className="jump-form"
          onSubmit={(e) => {
            e.preventDefault();
            const n = seconds(jump);
            if (Number.isFinite(n) && n >= 0 && n <= duration) props.onSeek(n);
            else setError("Timestamp fora da mídia ou inválido.");
          }}
        >
          <input
            aria-label="Ir para timestamp"
            placeholder="HH:MM:SS.mmm"
            value={jump}
            onChange={(e) => setJump(e.target.value)}
          />
          <button>Ir</button>
        </form>
      </div>
      <div className="cut-ruler">
        {Array.from({ length: 7 }, (_, i) => (
          <span key={i}>{timestamp(left + (span * i) / 6)}</span>
        ))}
      </div>
      <div
        className="cut-track"
        ref={trackRef}
        onClick={(e) => {
          if (e.target === e.currentTarget)
            props.onSeek(
              left +
                ((e.clientX - e.currentTarget.getBoundingClientRect().left) /
                  e.currentTarget.clientWidth) *
                  span,
            );
        }}
      >
        <svg
          className="pcm-wave"
          viewBox="0 0 1000 70"
          preserveAspectRatio="none"
          aria-label={
            ready
              ? "Forma de onda PCM da faixa escolhida"
              : "Forma de onda ainda não gerada"
          }
        >
          <path d={waveformPath} />
        </svg>
        <div className="cut-regions">
          {p.cuts
            .filter((c) => c.end >= left && c.start <= right)
            .map((cut, i) => {
              const active = draft?.id === cut.id;
              const a =
                  active && Number.isFinite(seconds(draft.start))
                    ? seconds(draft.start)
                    : cut.start,
                b =
                  active && Number.isFinite(seconds(draft.end))
                    ? seconds(draft.end)
                    : cut.end;
              return (
                <div
                  key={cut.id}
                  className={`cut-region ${cut.status} ${ids.includes(cut.id) ? "chosen" : ""} ${active && dirty ? "draft" : ""}`}
                  style={{
                    left: `${((a - left) / span) * 100}%`,
                    width: `${((b - a) / span) * 100}%`,
                    top: 4 + (i % 3) * 23,
                  }}
                  title={`${cut.title} · ${statuses[cut.status]}`}
                >
                  <button
                    className="cut-handle"
                    aria-label={`Arrastar IN de ${cut.title}`}
                    onPointerDown={(e) => beginDrag(e, "start", cut)}
                    onPointerMove={moveDrag}
                    onPointerUp={() => {
                      drag.current = null;
                    }}
                    onPointerCancel={() => {
                      drag.current = null;
                    }}
                  >
                    ⟨
                  </button>
                  <button
                    className="cut-region-title"
                    onClick={(e) => {
                      if (dragged.current) {
                        dragged.current = false;
                        return;
                      }
                      choose(cut, e.ctrlKey || e.metaKey);
                    }}
                    onPointerDown={(e) => beginDrag(e, "body", cut)}
                    onPointerMove={moveDrag}
                    onPointerUp={() => {
                      drag.current = null;
                    }}
                    onPointerCancel={() => {
                      drag.current = null;
                    }}
                  >
                    {cut.title}
                  </button>
                  <button
                    className="cut-handle"
                    aria-label={`Arrastar OUT de ${cut.title}`}
                    onPointerDown={(e) => beginDrag(e, "end", cut)}
                    onPointerMove={moveDrag}
                    onPointerUp={() => {
                      drag.current = null;
                    }}
                    onPointerCancel={() => {
                      drag.current = null;
                    }}
                  >
                    ⟩
                  </button>
                </div>
              );
            })}
        </div>
        {draft &&
          !draft.id &&
          Number.isFinite(seconds(draft.start)) &&
          Number.isFinite(seconds(draft.end)) &&
          seconds(draft.end) > seconds(draft.start) && (
            <div
              className="cut-new-draft"
              style={{
                left: `${((seconds(draft.start) - left) / span) * 100}%`,
                width: `${((seconds(draft.end) - seconds(draft.start)) / span) * 100}%`,
              }}
            >
              Novo corte · não salvo
            </div>
          )}
        <div
          className="cut-playhead"
          style={{ left: `${((props.position - left) / span) * 100}%` }}
        />
        <div className="cut-marker-label">{timestamp(props.position)}</div>
      </div>
      <input
        className="cut-pan"
        aria-label="Deslocar janela da timeline"
        type="range"
        min={0}
        max={Math.max(0, duration - span)}
        step={0.01}
        value={left}
        onChange={(e) => setPan(Number(e.target.value))}
      />
      <div className="wave-tools">
        <label>
          Waveform{" "}
          <select
            aria-label="Faixa da waveform"
            value={track}
            disabled={
              !!job && ["queued", "running", "cancelling"].includes(job.status)
            }
            onChange={(e) => setTrack(Number(e.target.value))}
          >
            {p.metadata.audio.map((a) => (
              <option key={a.index} value={a.index}>
                #{a.index} · {a.name || a.codec}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={
            track < 0 ||
            props.busy ||
            (!!job && ["queued", "running", "cancelling"].includes(job.status))
          }
          onClick={generate}
        >
          {ready ? "Reutilizar cache" : "Gerar waveform"}
        </button>
        {job && ["queued", "running", "cancelling"].includes(job.status) && (
          <>
            <span>{Math.floor(job.progress || 0)}%</span>
            <button
              onClick={() =>
                fetch(`/api/processing/${job.id}`, {
                  method: "DELETE",
                  headers: { "X-Leonida-Client": "1" },
                })
                  .then(async (r) => {
                    if (!r.ok) throw new Error("Falha ao cancelar.");
                    setJob(await r.json());
                  })
                  .catch((e) => setWaveError(e.message))
              }
            >
              Cancelar
            </button>
          </>
        )}
        <small>
          PCM min/max · faixa individual · I / O marcam pontos · arraste bordas
          ou região e salve
        </small>
        {waveError && <span role="alert">{waveError}</span>}
      </div>
      {error && (
        <div className="cut-error" role="alert">
          {error}
        </div>
      )}
      <div className="cut-bottom">
        <div className="cut-inspector">
          <h3>
            {draft?.id ? "Ajustar corte" : "Criar corte"}{" "}
            {dirty && <small>• não salvo</small>}
          </h3>
          {draft ? (
            <>
              <label>
                Título
                <input
                  maxLength={120}
                  value={draft.title}
                  onChange={(e) => changes({ ...draft, title: e.target.value })}
                />
              </label>
              <div className="cut-points">
                <label>
                  IN
                  <input
                    aria-label="IN do corte"
                    value={draft.start}
                    onChange={(e) =>
                      changes({ ...draft, start: e.target.value })
                    }
                  />
                </label>
                <button disabled={locked} onClick={() => mark("start")}>
                  Marcar I
                </button>
                <label>
                  OUT
                  <input
                    aria-label="OUT do corte"
                    value={draft.end}
                    onChange={(e) => changes({ ...draft, end: e.target.value })}
                  />
                </label>
                <button disabled={locked} onClick={() => mark("end")}>
                  Marcar O
                </button>
              </div>
              <label>
                Nota de revisão
                <textarea
                  maxLength={2000}
                  value={draft.note}
                  onChange={(e) => changes({ ...draft, note: e.target.value })}
                />
              </label>
              <label className="cut-check">
                <input
                  type="checkbox"
                  checked={align}
                  onChange={(e) => setAlign(e.target.checked)}
                />
                Expandir IN/OUT até os limites de frase da transcrição
              </label>
              <div className="cut-actions">
                <button
                  className="primary"
                  disabled={locked || !dirty}
                  onClick={save}
                >
                  Salvar ajuste
                </button>
                <button
                  disabled={saving || !dirty}
                  onClick={() => {
                    setDraft(single ? fromCut(single) : null);
                    setDirty(false);
                    setError("");
                  }}
                >
                  Descartar
                </button>
                <button
                  disabled={dirty}
                  onClick={() => {
                    const a = seconds(draft.start),
                      b = seconds(draft.end);
                    if (a < b) props.onPreview(a, b);
                  }}
                >
                  ▶ Reproduzir corte
                </button>
              </div>
              {single?.partial_transcript && (
                <p className="fine-print">
                  O intervalo atravessa um segmento de fala. Confira os limites
                  no player.
                </p>
              )}
              {single?.evidence_historical && (
                <p className="fine-print">
                  Evidências históricas: fontes alteradas; revise novamente.
                </p>
              )}
              {!!single?.context_evidence?.length && (
                <p className="fine-print">
                  {single.context_evidence.length} evidências anteriores estão
                  fora do intervalo ajustado.
                </p>
              )}
            </>
          ) : (
            <p>
              Selecione uma região ou crie um corte no playhead. Os pontos são
              segundos absolutos da mídia original.
            </p>
          )}
          <div className="cut-actions">
            <button
              disabled={locked || dirty || selected.length !== 1}
              onClick={() =>
                command({ action: "split", ids, position: props.position })
              }
            >
              Dividir no playhead
            </button>
            <button
              disabled={locked || dirty || selected.length < 2}
              onClick={() =>
                command({ action: "merge", ids, allow_gaps: allowGaps })
              }
            >
              Unir selecionados
            </button>
            <button
              disabled={locked || dirty || !selected.length}
              onClick={() => command({ action: "delete", ids })}
            >
              Remover cortes
            </button>
          </div>
          {selected.length > 1 && (
            <>
              <p>
                União proposta:{" "}
                {timestamp(Math.min(...selected.map((c) => c.start)))} →{" "}
                {timestamp(Math.max(...selected.map((c) => c.end)))}. Todo o
                conteúdo entre esses pontos será incluído.
              </p>
              <label className="cut-check">
                <input
                  type="checkbox"
                  checked={allowGaps}
                  onChange={(e) => setAllowGaps(e.target.checked)}
                />
                Incluir eventuais lacunas entre os cortes
              </label>
            </>
          )}
          <small>
            ← / →: passo por FPS nominal. O player do navegador não garante
            precisão de quadro, especialmente em VFR.
          </small>
          <details className="cut-archives">
            <summary>
              Conjuntos anteriores ({editor?.archives.length ?? 0})
            </summary>
            {editor?.archives.map((a) => (
              <div key={a.id}>
                <span>
                  {new Date(a.created_at).toLocaleString("pt-BR")} ·{" "}
                  {a.cut_count} cortes · {a.reason}
                </span>
                <a
                  href={`/api/projects/${p.id}/cuts/archives/${a.id}`}
                  download
                >
                  JSON
                </a>
                <button
                  disabled={locked || dirty || !a.compatible}
                  onClick={() =>
                    command({ action: "restore", archive_id: a.id })
                  }
                >
                  Restaurar
                </button>
              </div>
            ))}
            <small>
              Restaurar arquiva o conjunto atual e reinicia desfazer/refazer.
              Fontes diferentes permitem apenas consulta.
            </small>
          </details>
        </div>
        <div className="cut-review">
          <h3>
            Revisão{" "}
            <small>
              {filtered.length} de {p.cuts.length} · {ids.length} selecionados
            </small>
          </h3>
          <div className="cut-filters">
            <input
              aria-label="Buscar cortes"
              placeholder="Buscar título ou fala"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select
              aria-label="Filtrar status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Todos os status</option>
              {Object.entries(statuses).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <select
              aria-label="Filtrar categoria"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">Todas as categorias</option>
              {[...new Set(p.cuts.map((c) => c.category))].map((k) => (
                <option key={k} value={k}>
                  {categories[k] ?? k}
                </option>
              ))}
            </select>
            <label>
              Score ≥
              <input
                type="number"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
              />
            </label>
            <label>
              Duração ≥ s
              <input
                type="number"
                min={0}
                value={minDuration}
                onChange={(e) => setMinDuration(Number(e.target.value))}
              />
            </label>
            <label>
              ≤ s
              <input
                type="number"
                min={0}
                value={maxDuration}
                onChange={(e) => setMaxDuration(e.target.value)}
              />
            </label>
          </div>
          <div className="cut-actions">
            {Object.entries(statuses).map(([k, v]) => (
              <button
                key={k}
                disabled={locked || dirty || !ids.length}
                onClick={() => command({ action: "status", ids, status: k })}
              >
                {v}
              </button>
            ))}
          </div>
          <div className="cut-list">
            {filtered.map((c) => (
              <article
                key={c.id}
                className={`cut-row ${c.status} ${ids.includes(c.id) ? "selected" : ""}`}
              >
                <input
                  type="checkbox"
                  aria-label={`Selecionar ${c.title}`}
                  checked={ids.includes(c.id)}
                  disabled={dirty}
                  onChange={() => choose(c, true)}
                />
                <button className="cut-row-main" onClick={() => choose(c)}>
                  <strong>{c.title}</strong>
                  <small>
                    {timestamp(c.start)} → {timestamp(c.end)} ·{" "}
                    {c.duration.toFixed(2)} s
                  </small>
                  <span>
                    {statuses[c.status]} ·{" "}
                    {categories[c.category] ?? c.category} ·{" "}
                    {c.score == null ? "Sem pontuação" : `${c.score}/100`}
                    {editor?.overlap_ids.includes(c.id)
                      ? " · Sobreposição"
                      : ""}
                  </span>
                </button>
                <button
                  aria-label={`Reproduzir corte ${c.title}`}
                  onClick={() => props.onPreview(c.start, c.end)}
                >
                  ▶
                </button>
              </article>
            ))}
            {!filtered.length && (
              <p>
                Nenhum corte atende aos filtros. Crie um corte ou gere sugestões
                na aba Análise.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
