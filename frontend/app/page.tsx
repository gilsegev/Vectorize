"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type JobStatus = "processing" | "waiting_for_selection" | "completed" | "failed";

type JobPayload = {
  job_id: string;
  status: JobStatus;
  batch_run_id?: string | null;
  output_dir?: string | null;
  log_url?: string | null;
  artifacts: {
    original: string | null;
    normalized: string | null;
    grayscale: string | null;
    edge_map: string | null;
    candidates: (string | null)[];
    binary: string | null;
    cleanup_preview: string | null;
    final_svg: string | null;
    final_preview: string | null;
  };
  settings: {
    detail_level: string;
    num_variants: number;
    cleanup_strength: string;
    log_verbosity?: string;
  };
  selected_candidate: string | null;
  stage_durations: Record<string, number>;
  error: string | null;
};

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [detailLevel, setDetailLevel] = useState("medium");
  const [cleanupStrength, setCleanupStrength] = useState("medium");
  const [numVariants, setNumVariants] = useState(1);
  const [logVerbosity, setLogVerbosity] = useState("mid");
  const [jobId, setJobId] = useState<string>("");
  const [job, setJob] = useState<JobPayload | null>(null);
  const [runLog, setRunLog] = useState<string>("");
  const [focusedAsset, setFocusedAsset] = useState<{ title: string; src: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchJob(idArg?: string) {
    const id = idArg ?? jobId;
    if (!id) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${id}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as JobPayload;
      setJob(payload);
      setError(null);
      if (payload.log_url) {
        const logResp = await fetch(`${API_BASE}${payload.log_url}`, { cache: "no-store" });
        if (logResp.ok) {
          setRunLog(await logResp.text());
        }
      }
      if (!focusedAsset) {
        const first = payload.artifacts.final_preview ?? payload.artifacts.candidates[0] ?? payload.artifacts.normalized;
        if (first) {
          setFocusedAsset({ title: "Focused preview", src: first });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch job");
    }
  }

  useEffect(() => {
    fetchJob();
    if (!jobId) {
      return;
    }
    const timer = setInterval(() => fetchJob(), 2200);
    return () => clearInterval(timer);
  }, [jobId]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Please choose an image file first.");
      return;
    }
    setError(null);
    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("detail_level", detailLevel);
    formData.append("cleanup_strength", cleanupStrength);
    formData.append("num_variants", String(numVariants));
    formData.append("log_verbosity", logVerbosity);

    try {
      const response = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Upload failed");
      }
      const data = await response.json();
      setJobId(data.job_id);
      setJob(null);
      setRunLog("");
      setFocusedAsset(null);
      await fetchJob(data.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  async function selectVariant(candidateUrl: string | null) {
    if (!candidateUrl || !job || job.status !== "waiting_for_selection") {
      return;
    }
    const candidate = candidateUrl.split("/").pop();
    if (!candidate) {
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${job.job_id}/select-variant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await fetchJob(job.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to select candidate");
    } finally {
      setBusy(false);
    }
  }

  const canSelect = job?.status === "waiting_for_selection";
  const canDownload = job?.status === "completed";
  const sortedDurations = useMemo(() => Object.entries(job?.stage_durations ?? {}), [job?.stage_durations]);
  const outputDirHref = job?.output_dir ? `file:///${job.output_dir.replace(/\\/g, "/")}` : null;

  async function copyLog() {
    if (!runLog) {
      return;
    }
    try {
      await navigator.clipboard.writeText(runLog);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to copy log");
    }
  }

  async function clearLog() {
    if (!jobId) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${jobId}/log/clear`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setRunLog("");
      await fetchJob(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear log");
    }
  }

  async function openOutputDir() {
    if (!jobId) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${jobId}/open-output-dir`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await response.text());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open output directory");
    }
  }

  return (
    <main className="container">
      <div className="card">
        <h1>Image to Vector</h1>
        <p>Upload and review results in one screen.</p>
        <form onSubmit={onSubmit}>
          <div className="row">
            <div>
              <label className="label">Image</label>
              <input type="file" accept=".png,.jpg,.jpeg,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            <div>
              <label className="label">Detail level</label>
              <select value={detailLevel} onChange={(e) => setDetailLevel(e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            <div>
              <label className="label">Cleanup strength</label>
              <select value={cleanupStrength} onChange={(e) => setCleanupStrength(e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            <div>
              <label className="label">Variants (1-4)</label>
              <input type="number" min={1} max={4} value={numVariants} onChange={(e) => setNumVariants(Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Log verbosity</label>
              <select value={logVerbosity} onChange={(e) => setLogVerbosity(e.target.value)}>
                <option value="low">Low</option>
                <option value="mid">Mid</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <button type="submit" disabled={loading}>{loading ? "Starting..." : "Start Job"}</button>
          </div>
          {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
        </form>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h2>Run Results</h2>
        {!jobId && <p>No job yet. Start one above to see live outputs here.</p>}
        {jobId && (
          <>
            <p><strong>Job:</strong> {jobId}</p>
            {job && <div className="status">{job.status}</div>}
            {job?.batch_run_id && <p><strong>Batch run:</strong> {job.batch_run_id}</p>}
            {job?.output_dir && (
              <p>
                <strong>Output dir:</strong>{" "}
                <a href={outputDirHref ?? "#"} target="_blank" rel="noreferrer">
                  {job.output_dir}
                </a>{" "}
                <button type="button" onClick={openOutputDir}>Open Folder</button>
              </p>
            )}
            {job?.error && <p style={{ color: "#b91c1c" }}>{job.error}</p>}

            <h3>Focused Preview</h3>
            <div className="card">
              {focusedAsset ? (
                <FocusedAsset title={focusedAsset.title} src={focusedAsset.src} />
              ) : (
                <p>Click any asset button to inspect it full size here.</p>
              )}
            </div>

            <h3 style={{ marginTop: 14 }}>Pipeline Outputs</h3>
            <div className="grid">
              <Artifact title="Original" src={job?.artifacts.original} onFocus={setFocusedAsset} />
              <Artifact title="Normalized" src={job?.artifacts.normalized} onFocus={setFocusedAsset} />
              <Artifact title="Grayscale" src={job?.artifacts.grayscale} onFocus={setFocusedAsset} />
              <Artifact title="Edge map" src={job?.artifacts.edge_map} onFocus={setFocusedAsset} />
              <Artifact title="Cleanup" src={job?.artifacts.cleanup_preview} onFocus={setFocusedAsset} />
              <Artifact title="Final preview" src={job?.artifacts.final_preview} onFocus={setFocusedAsset} />
            </div>

            <h3 style={{ marginTop: 14 }}>Generated Variants</h3>
            <div className="grid">
              {(job?.artifacts.candidates ?? []).map((candidateUrl, index) => (
                <div key={candidateUrl ?? index} className="card">
                  <h3>Candidate {index + 1}</h3>
                  <Artifact title={`Candidate ${index + 1}`} src={candidateUrl} compact onFocus={setFocusedAsset} />
                  {canSelect && (
                    <button disabled={busy} onClick={() => selectVariant(candidateUrl)}>
                      Select this variant
                    </button>
                  )}
                </div>
              ))}
            </div>

            <h3 style={{ marginTop: 14 }}>Timings (seconds)</h3>
            <div className="row">
              {sortedDurations.map(([stage, seconds]) => (
                <div key={stage} className="card">
                  <strong>{stage}</strong>
                  <div>{seconds}</div>
                </div>
              ))}
            </div>

            {canDownload && (
              <div style={{ marginTop: 14 }}>
                <a href={`${API_BASE}/api/jobs/${job?.job_id}/download/svg`}>
                  <button>Download SVG</button>
                </a>
              </div>
            )}

            <h3 style={{ marginTop: 14 }}>Run Log</h3>
            <div className="row" style={{ marginBottom: 8 }}>
              <button type="button" onClick={copyLog} disabled={!runLog}>Copy Log</button>
              <button type="button" onClick={clearLog}>Clear Log</button>
            </div>
            <div className="card" style={{ whiteSpace: "pre-wrap", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, maxHeight: 300, overflow: "auto" }}>
              {runLog || "Log not available yet"}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function Artifact({
  title,
  src,
  compact = false,
  onFocus,
}: {
  title: string;
  src?: string | null;
  compact?: boolean;
  onFocus?: (asset: { title: string; src: string }) => void;
}) {
  if (!src) {
    return (
      <div className="card">
        {!compact && <h3>{title}</h3>}
        <p>Not available yet</p>
      </div>
    );
  }
  const fullSrc = src.startsWith("http") ? src : `${API_BASE}${src}`;
  const isSvg = src.endsWith(".svg");
  return (
    <div className="card">
      {!compact && <h3>{title}</h3>}
      {isSvg ? <object data={fullSrc} type="image/svg+xml" width="100%" height={240} /> : <img src={fullSrc} alt={title} />}
      <div style={{ marginTop: 8 }}>
        <button type="button" onClick={() => onFocus?.({ title, src })}>
          View Full Size
        </button>
      </div>
    </div>
  );
}

function FocusedAsset({ title, src }: { title: string; src: string }) {
  const fullSrc = src.startsWith("http") ? src : `${API_BASE}${src}`;
  const isSvg = src.endsWith(".svg");
  return (
    <div>
      <h3>{title}</h3>
      {isSvg ? (
        <object data={fullSrc} type="image/svg+xml" width="100%" height={680} />
      ) : (
        <img src={fullSrc} alt={title} style={{ width: "100%", maxHeight: 760, objectFit: "contain" }} />
      )}
    </div>
  );
}
