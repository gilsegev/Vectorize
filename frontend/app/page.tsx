"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type JobStatus = "processing" | "waiting_for_selection" | "completed" | "failed";
type FabricationStyle = "precision_inlay" | "bold_signage" | "abstract_art";
type PromptProfile = "legacy" | "base_professional_pen" | "stronger_polish" | "realism_preserving";
type SelectionMode = "manual" | "auto";

type JobPayload = {
  job_id: string;
  status: JobStatus;
  batch_run_id?: string | null;
  source_frontend?: "storefront" | "workbench";
  output_dir?: string | null;
  log_url?: string | null;
  artifacts: {
    original: string | null;
    normalized: string | null;
    grayscale: string | null;
    edge_map: string | null;
    subject_mask: string | null;
    refined: string | null;
    refined_candidates: (string | null)[];
    candidates: (string | null)[];
    binary: string | null;
    cleanup_preview: string | null;
    final_svg: string | null;
    final_preview: string | null;
    package_zip?: string | null;
  };
  settings: {
    detail_level: string;
    num_variants: number;
    cleanup_strength: string;
    log_verbosity?: string;
    fabrication_style?: FabricationStyle;
    prompt_profile?: PromptProfile;
    selection_mode?: SelectionMode;
    benchmark_tag?: string | null;
    source_image_id?: string | null;
    inking_denoise?: number;
    potrace_turdsize?: number;
    potrace_opttolerance?: number;
    cleanup_threshold_bias?: number;
    cleanup_min_component_px?: number;
    cleanup_speck_morph?: number;
  };
  selected_candidate: string | null;
  stage_durations: Record<string, number>;
  prompt_version?: string | null;
  selection_reason?: string | null;
  candidate_scores?: Record<string, { score?: number; diagnostics?: Record<string, number | null> }>;
  quality_diagnostics?: { small_component_count?: number; interior_line_density?: number; face_region_density?: number | null };
  cnc_metrics?: {
    node_count?: number;
    mse_fidelity?: number;
  };
  error: string | null;
};

const PRESETS: Record<FabricationStyle, { label: string; inking_denoise: number; turdsize: number; opttolerance: number }> = {
  precision_inlay: { label: "Precision Inlay", inking_denoise: 0.35, turdsize: 80, opttolerance: 0.5 },
  bold_signage: { label: "Bold Signage", inking_denoise: 0.5, turdsize: 200, opttolerance: 1.2 },
  abstract_art: { label: "Abstract Art", inking_denoise: 0.65, turdsize: 400, opttolerance: 2.0 },
};
const BENCHMARK_TAG_OPTIONS = [
  "round1-base-prof-pen",
  "round1-legacy-baseline",
  "round1-stronger-polish",
  "round1-realism-preserving",
  "round2-cleanup-threshold",
  "round2-cleanup-component",
  "round2-cleanup-morph",
];

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [detailLevel, setDetailLevel] = useState("medium");
  const [cleanupStrength, setCleanupStrength] = useState("medium");
  const [numVariants, setNumVariants] = useState(1);
  const [logVerbosity, setLogVerbosity] = useState("mid");
  const [fabricationStyle, setFabricationStyle] = useState<FabricationStyle>("bold_signage");
  const [inkingDenoise, setInkingDenoise] = useState(PRESETS.bold_signage.inking_denoise);
  const [potraceTurdsize, setPotraceTurdsize] = useState(PRESETS.bold_signage.turdsize);
  const [potraceOpttol, setPotraceOpttol] = useState(PRESETS.bold_signage.opttolerance);
  const [promptProfile, setPromptProfile] = useState<PromptProfile>("legacy");
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("manual");
  const [benchmarkTag, setBenchmarkTag] = useState("");
  const [sourceImageId, setSourceImageId] = useState("");
  const [cleanupThresholdBias, setCleanupThresholdBias] = useState(0);
  const [cleanupMinComponentPx, setCleanupMinComponentPx] = useState(40);
  const [cleanupSpeckMorph, setCleanupSpeckMorph] = useState(0);

  const [jobId, setJobId] = useState("");
  const [jobIdInput, setJobIdInput] = useState("");
  const [job, setJob] = useState<JobPayload | null>(null);
  const [runLog, setRunLog] = useState("");
  const [focusedAsset, setFocusedAsset] = useState<{ title: string; src: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [networkWarning, setNetworkWarning] = useState<string | null>(null);
  const [rerunDenoise, setRerunDenoise] = useState(0.5);

  const [compareOpen, setCompareOpen] = useState(false);
  const [compareSplit, setCompareSplit] = useState(50);

  async function fetchJob(idArg?: string) {
    const id = idArg ?? jobId;
    if (!id) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${id}?view=workbench`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as JobPayload;
      setJob(payload);
      setNetworkWarning(null);
      if (payload.log_url) {
        const logResp = await fetch(`${API_BASE}${payload.log_url}`, { cache: "no-store" });
        if (logResp.ok) {
          setRunLog(await logResp.text());
        }
      }
      if (!focusedAsset) {
        const first = payload.artifacts.final_preview ?? payload.artifacts.refined ?? payload.artifacts.candidates[0] ?? payload.artifacts.normalized;
        if (first) {
          setFocusedAsset({ title: "Focused Preview", src: first });
        }
      }
    } catch (err) {
      setNetworkWarning(err instanceof Error ? err.message : "Failed to fetch job");
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

  function applyPreset(style: FabricationStyle) {
    const p = PRESETS[style];
    setFabricationStyle(style);
    setInkingDenoise(p.inking_denoise);
    setPotraceTurdsize(p.turdsize);
    setPotraceOpttol(p.opttolerance);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setFormError("Please choose an image file first.");
      return;
    }
    setFormError(null);
    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("detail_level", detailLevel);
    formData.append("cleanup_strength", cleanupStrength);
    formData.append("num_variants", String(numVariants));
    formData.append("log_verbosity", logVerbosity);
    formData.append("fabrication_style", fabricationStyle);
    formData.append("prompt_profile", promptProfile);
    formData.append("selection_mode", selectionMode);
    formData.append("benchmark_tag", benchmarkTag);
    formData.append("source_image_id", sourceImageId);
    formData.append("inking_denoise", String(inkingDenoise));
    formData.append("potrace_turdsize", String(potraceTurdsize));
    formData.append("potrace_opttolerance", String(potraceOpttol));
    formData.append("cleanup_threshold_bias", String(cleanupThresholdBias));
    formData.append("cleanup_min_component_px", String(cleanupMinComponentPx));
    formData.append("cleanup_speck_morph", String(cleanupSpeckMorph));
    formData.append("source_frontend", "workbench");

    try {
      const response = await fetch(`${API_BASE}/api/jobs`, { method: "POST", body: formData });
      if (!response.ok) {
        throw new Error((await response.text()) || "Upload failed");
      }
      const data = await response.json();
      setJobId(data.job_id);
      setJobIdInput(data.job_id);
      setJob(null);
      setRunLog("");
      setFocusedAsset(null);
      await fetchJob(data.job_id);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  async function selectVariant(candidateUrl: string | null) {
    if (!candidateUrl || !job || job.status !== "waiting_for_selection") {
      return;
    }
    const candidate = candidateUrl.split("?")[0].split("/").pop();
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
      setFormError(err instanceof Error ? err.message : "Failed to select candidate");
    } finally {
      setBusy(false);
    }
  }

  const candidateUrls = useMemo(
    () => (Array.isArray(job?.artifacts.candidates) ? job?.artifacts.candidates : []),
    [job?.artifacts.candidates],
  );
  const selectedCandidateUrl = useMemo(() => {
    if (!job) {
      return null;
    }
    if (!job.selected_candidate) {
      return candidateUrls[0] ?? null;
    }
    return candidateUrls.find((u) => u?.split("/").pop() === job.selected_candidate) ?? candidateUrls[0] ?? null;
  }, [candidateUrls, job]);

  const canSelect = job?.status === "waiting_for_selection";
  const canDownload = job?.status === "completed";
  const sortedDurations = useMemo(() => Object.entries(job?.stage_durations ?? {}), [job?.stage_durations]);
  const outputDirHref = job?.output_dir ? `file:///${job.output_dir.replace(/\\/g, "/")}` : null;
  const nodeCount = job?.cnc_metrics?.node_count;
  const mseFidelity = job?.cnc_metrics?.mse_fidelity;

  const nodeClass =
    typeof nodeCount !== "number" ? "metric-neutral" : nodeCount < 800 ? "metric-good" : nodeCount <= 2000 ? "metric-warn" : "metric-bad";

  const phaseCards = [
    { key: "01", title: "01 Input Original", src: job?.artifacts.original },
    { key: "02", title: "02 Input Normalized", src: job?.artifacts.normalized },
    { key: "03", title: "03 Preprocess Grayscale", src: job?.artifacts.grayscale },
    { key: "04", title: "04 Preprocess Edge Map", src: job?.artifacts.edge_map },
    { key: "05a", title: "05 Preprocess Subject Mask", src: job?.artifacts.subject_mask },
    { key: "05b", title: "05 Generation Candidate", src: selectedCandidateUrl },
    { key: "05c", title: "05 Generation Refined", src: job?.artifacts.refined, compare: true },
    { key: "06", title: "06 Cleanup Binary", src: job?.artifacts.binary },
    { key: "07", title: "07 Cleanup Preview", src: job?.artifacts.cleanup_preview },
    { key: "08", title: "08 Vector Final SVG", src: job?.artifacts.final_svg, isFinal: true },
    { key: "09", title: "09 Vector Final Preview", src: job?.artifacts.final_preview },
  ];

  async function copyLog() {
    if (!runLog) {
      return;
    }
    try {
      await navigator.clipboard.writeText(runLog);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to copy log");
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
      setFormError(err instanceof Error ? err.message : "Failed to clear log");
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
      setFormError(err instanceof Error ? err.message : "Failed to open output directory");
    }
  }

  async function refineAndRerun() {
    if (!jobId) {
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${jobId}/refine-rerun`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inking_denoise: rerunDenoise }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await fetchJob(jobId);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to refine and rerun");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="card card-hero">
        <h1>Vector Workshop</h1>
        <p>Workshop controls and observability for semantic inking and vector fabrication.</p>
        <form onSubmit={onSubmit}>
          <div className="row">
            <div>
              <label className="label">Load Existing Job ID</label>
              <div className="row">
                <input value={jobIdInput} onChange={(e) => setJobIdInput(e.target.value)} placeholder="Paste job id" />
                <button type="button" onClick={() => { setJobId(jobIdInput.trim()); fetchJob(jobIdInput.trim()); }}>Load</button>
              </div>
            </div>
            <div>
              <label className="label">Image</label>
              <input type="file" accept=".png,.jpg,.jpeg,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            <div>
              <label className="label">Fabrication Style</label>
              <select value={fabricationStyle} onChange={(e) => applyPreset(e.target.value as FabricationStyle)}>
                {Object.entries(PRESETS).map(([key, val]) => (
                  <option key={key} value={key}>{val.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Inking Denoise</label>
              <input value={inkingDenoise.toFixed(2)} readOnly />
            </div>
            <div>
              <label className="label">Prompt Profile</label>
              <select value={promptProfile} onChange={(e) => setPromptProfile(e.target.value as PromptProfile)}>
                <option value="legacy">Legacy</option>
                <option value="base_professional_pen">Base Professional Pen</option>
                <option value="stronger_polish">Stronger Polish</option>
                <option value="realism_preserving">Realism Preserving</option>
              </select>
            </div>
            <div>
              <label className="label">Selection Mode</label>
              <select value={selectionMode} onChange={(e) => setSelectionMode(e.target.value as SelectionMode)}>
                <option value="manual">Manual</option>
                <option value="auto">Auto</option>
              </select>
            </div>
            <div>
              <label className="label">Benchmark Tag</label>
              <input list="benchmark-tag-options" value={benchmarkTag} onChange={(e) => setBenchmarkTag(e.target.value)} placeholder="round1-base" />
              <datalist id="benchmark-tag-options">
                {BENCHMARK_TAG_OPTIONS.map((tag) => (
                  <option key={tag} value={tag} />
                ))}
              </datalist>
            </div>
            <div>
              <label className="label">Source Image ID</label>
              <input value={sourceImageId} onChange={(e) => setSourceImageId(e.target.value)} placeholder="car.jpg" />
            </div>
            <div>
              <label className="label">Potrace Turdsize</label>
              <input value={potraceTurdsize} readOnly />
            </div>
            <div>
              <label className="label">Potrace Opttolerance</label>
              <input value={potraceOpttol.toFixed(1)} readOnly />
            </div>
            <div>
              <label className="label">Detail Level</label>
              <select value={detailLevel} onChange={(e) => setDetailLevel(e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            <div>
              <label className="label">Cleanup Strength</label>
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
              <label className="label">Log Verbosity</label>
              <select value={logVerbosity} onChange={(e) => setLogVerbosity(e.target.value)}>
                <option value="low">Low</option>
                <option value="mid">Mid</option>
                <option value="high">High</option>
              </select>
            </div>
            <div>
              <label className="label">Cleanup Threshold Bias</label>
              <input type="number" min={-32} max={32} value={cleanupThresholdBias} onChange={(e) => setCleanupThresholdBias(Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Cleanup Min Component Px</label>
              <input type="number" min={8} max={5000} value={cleanupMinComponentPx} onChange={(e) => setCleanupMinComponentPx(Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Cleanup Speck Morph</label>
              <input type="number" min={0} max={2} value={cleanupSpeckMorph} onChange={(e) => setCleanupSpeckMorph(Number(e.target.value))} />
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <button type="submit" disabled={loading}>{loading ? "Starting..." : "Start Job"}</button>
          </div>
          {formError && <p className="error-text">{formError}</p>}
        </form>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h2>Run Results</h2>
        {!jobId && <p>No job yet. Start one above to see live outputs here.</p>}
        {jobId && (
          <>
            <p><strong>Job:</strong> {jobId}</p>
            {job && <div className="status">{job.status}</div>}
            {job?.batch_run_id && <p><strong>Batch Run:</strong> {job.batch_run_id}</p>}
            {job?.source_frontend && <p><strong>Source Frontend:</strong> {job.source_frontend}</p>}
            {job?.prompt_version && <p><strong>Prompt Version:</strong> {job.prompt_version}</p>}
            {job?.selection_reason && <p><strong>Selection Reason:</strong> {job.selection_reason}</p>}
            {job?.output_dir && (
              <p>
                <strong>Output Dir:</strong>{" "}
                <a href={outputDirHref ?? "#"} target="_blank" rel="noreferrer">{job.output_dir}</a>{" "}
                <button type="button" onClick={openOutputDir}>Open Folder</button>
              </p>
            )}
            {job?.error && <p className="error-text">{job.error}</p>}
            {networkWarning && <p className="warn-text">Network warning: {networkWarning}</p>}
            <div className="row" style={{ marginBottom: 12 }}>
              <input
                type="number"
                step="0.01"
                min={0.1}
                max={0.9}
                value={rerunDenoise}
                onChange={(e) => setRerunDenoise(Number(e.target.value))}
              />
              <button type="button" disabled={busy || !jobId} onClick={refineAndRerun}>Refine and Re-run</button>
            </div>

            <h3>Focused Preview</h3>
            <div className="card">
              {focusedAsset ? <FocusedAsset title={focusedAsset.title} src={focusedAsset.src} /> : <p>Click any artifact card to focus it here.</p>}
            </div>

            <h3 style={{ marginTop: 14 }}>Phase Artifacts (01-09)</h3>
            <div className="grid">
              {phaseCards.map((artifact) => (
                <Artifact
                  key={artifact.key}
                  title={artifact.title}
                  src={artifact.src}
                  onFocus={setFocusedAsset}
                  onCompare={artifact.compare ? () => setCompareOpen(true) : undefined}
                  metrics={
                    artifact.isFinal
                      ? {
                          nodeCount: typeof nodeCount === "number" ? nodeCount : null,
                          mseFidelity: typeof mseFidelity === "number" ? mseFidelity : null,
                          nodeClass,
                        }
                      : undefined
                  }
                />
              ))}
            </div>

            <h3 style={{ marginTop: 14 }}>Generated Variants</h3>
            <div className="grid">
              {candidateUrls.map((candidateUrl, index) => (
                <div key={candidateUrl ?? index} className="card">
                  <h3>{`candidate_${index + 1}.png`}</h3>
                  <Artifact title={`candidate_${index + 1}`} src={candidateUrl} compact onFocus={setFocusedAsset} />
                  {job?.candidate_scores?.[`candidate_${index + 1}.png`]?.score !== undefined && (
                    <p>score: {job.candidate_scores[`candidate_${index + 1}.png`].score}</p>
                  )}
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

            {job?.quality_diagnostics && (
              <>
                <h3 style={{ marginTop: 14 }}>Quality Diagnostics</h3>
                <div className="row">
                  <div className="card"><strong>small_component_count</strong><div>{job.quality_diagnostics.small_component_count ?? "-"}</div></div>
                  <div className="card"><strong>interior_line_density</strong><div>{job.quality_diagnostics.interior_line_density ?? "-"}</div></div>
                  <div className="card"><strong>face_region_density</strong><div>{job.quality_diagnostics.face_region_density ?? "null"}</div></div>
                </div>
              </>
            )}

            {canDownload && (
              <div style={{ marginTop: 14 }}>
                <a href={`${API_BASE}/api/jobs/${job.job_id}/download/svg`}>
                  <button>Download Final SVG</button>
                </a>
                {job?.artifacts?.package_zip && (
                  <a href={job.artifacts.package_zip} style={{ marginLeft: 8 }}>
                    <button>Download Package ZIP</button>
                  </a>
                )}
              </div>
            )}

            <h3 style={{ marginTop: 14 }}>Run Log</h3>
            <div className="row" style={{ marginBottom: 8 }}>
              <button type="button" onClick={copyLog} disabled={!runLog}>Copy Log</button>
              <button type="button" onClick={clearLog}>Clear Log</button>
            </div>
            <div className="card log-box">{runLog || "Log not available yet"}</div>
          </>
        )}
      </div>

      {compareOpen && selectedCandidateUrl && job?.artifacts.refined && (
        <CompareModal
          beforeSrc={selectedCandidateUrl}
          afterSrc={job.artifacts.refined}
          split={compareSplit}
          onSplit={setCompareSplit}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </main>
  );
}

function Artifact({
  title,
  src,
  compact = false,
  onFocus,
  onCompare,
  metrics,
}: {
  title: string;
  src?: string | null;
  compact?: boolean;
  onFocus?: (asset: { title: string; src: string }) => void;
  onCompare?: () => void;
  metrics?: { nodeCount: number | null; mseFidelity: number | null; nodeClass: string };
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
  const fileName = src.split("?")[0].split("/").pop() || "artifact";
  const openInNewTab = () => window.open(fullSrc, "_blank", "noopener,noreferrer");

  async function handleDownload() {
    try {
      const response = await fetch(fullSrc, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Download failed with status ${response.status}`);
      }
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);
    } catch {
      window.open(fullSrc, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <div className="card">
      {!compact && <h3>{title}</h3>}
      {isSvg ? (
        <object data={fullSrc} type="image/svg+xml" width="100%" height={240} onClick={openInNewTab} style={{ cursor: "pointer" }} />
      ) : (
        <img src={fullSrc} alt={title} onClick={openInNewTab} style={{ cursor: "pointer" }} />
      )}
      {metrics && (
        <div className="metrics">
          <span className={`metric-pill ${metrics.nodeClass}`}>node_count: {metrics.nodeCount ?? "-"}</span>
          <span className="metric-pill metric-neutral">mse_fidelity: {metrics.mseFidelity ?? "-"}</span>
        </div>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <button type="button" onClick={() => onFocus?.({ title, src })}>View</button>
        <button type="button" onClick={handleDownload}>Download</button>
        {onCompare && <button type="button" onClick={onCompare}>Compare</button>}
      </div>
    </div>
  );
}

function FocusedAsset({ title, src }: { title: string; src: string }) {
  const fullSrc = src.startsWith("http") ? src : `${API_BASE}${src}`;
  const isSvg = src.endsWith(".svg");
  const openInNewTab = () => window.open(fullSrc, "_blank", "noopener,noreferrer");
  return (
    <div>
      <h3>{title}</h3>
      {isSvg ? (
        <object data={fullSrc} type="image/svg+xml" width="100%" height={680} onClick={openInNewTab} style={{ cursor: "pointer" }} />
      ) : (
        <img src={fullSrc} alt={title} onClick={openInNewTab} style={{ width: "100%", maxHeight: 760, objectFit: "contain", cursor: "pointer" }} />
      )}
    </div>
  );
}

function CompareModal({
  beforeSrc,
  afterSrc,
  split,
  onSplit,
  onClose,
}: {
  beforeSrc: string;
  afterSrc: string;
  split: number;
  onSplit: (v: number) => void;
  onClose: () => void;
}) {
  const before = beforeSrc.startsWith("http") ? beforeSrc : `${API_BASE}${beforeSrc}`;
  const after = afterSrc.startsWith("http") ? afterSrc : `${API_BASE}${afterSrc}`;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3>Before (Candidate) vs After (Refined)</h3>
          <button type="button" onClick={onClose}>Close</button>
        </div>
        <div className="compare-wrap">
          <img src={before} alt="Before candidate" />
          <div className="compare-after" style={{ width: `${split}%` }}>
            <img src={after} alt="After refined" />
          </div>
          <div className="compare-divider" style={{ left: `${split}%` }} />
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={split}
          onChange={(e) => onSplit(Number(e.target.value))}
          style={{ width: "100%", marginTop: 10 }}
        />
      </div>
    </div>
  );
}
