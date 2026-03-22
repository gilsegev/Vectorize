"use client";

import { DragEvent, FormEvent, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
type FabricationStyle = "precision_inlay" | "bold_signage" | "abstract_art";
type JobStatus = "processing" | "waiting_for_selection" | "completed" | "failed";

type StorefrontPayload = {
  job_id: string;
  status: JobStatus;
  artifacts: {
    art: string | null;
    toolpath_svg: string | null;
    package_zip: string | null;
  };
  settings?: { fabrication_style?: FabricationStyle };
  cnc_metrics?: { node_count?: number; mse_fidelity?: number };
  error: string | null;
};

const STYLE_LABEL: Record<FabricationStyle, string> = {
  precision_inlay: "Hardwood",
  bold_signage: "Signage",
  abstract_art: "Abstract Art",
};

export default function UserStorefrontPage() {
  const [file, setFile] = useState<File | null>(null);
  const [fabricationStyle, setFabricationStyle] = useState<FabricationStyle>("bold_signage");
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<StorefrontPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchJob(idArg?: string) {
    const id = idArg ?? jobId;
    if (!id) {
      return;
    }
    try {
      const resp = await fetch(`${API_BASE}/api/jobs/${id}?view=storefront`, { cache: "no-store" });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setJob((await resp.json()) as StorefrontPayload);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch job");
    }
  }

  useEffect(() => {
    if (!jobId) {
      return;
    }
    const t = setInterval(() => fetchJob(), 2200);
    return () => clearInterval(t);
  }, [jobId]);

  function onDropFile(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const f = event.dataTransfer.files?.[0];
    if (f) {
      setFile(f);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Please upload an image.");
      return;
    }
    setLoading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("fabrication_style", fabricationStyle);
    form.append("source_frontend", "storefront");
    form.append("num_variants", "1");
    try {
      const resp = await fetch(`${API_BASE}/api/jobs`, { method: "POST", body: form });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const data = await resp.json();
      setJobId(data.job_id);
      await fetchJob(data.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start job");
    } finally {
      setLoading(false);
    }
  }

  const nodeCount = job?.cnc_metrics?.node_count;
  const success = typeof nodeCount === "number" && nodeCount < 800;

  return (
    <main className="container user-page">
      <div className="card user-hero">
        <h1>Vectorize Storefront</h1>
        <p>Upload a photo, choose a style, and download your production-ready package.</p>
        <form onSubmit={onSubmit}>
          <div
            className="dropzone"
            onDrop={onDropFile}
            onDragOver={(e) => e.preventDefault()}
          >
            {file ? `Selected: ${file.name}` : "Drag and drop an image here, or choose a file below"}
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <input type="file" accept=".png,.jpg,.jpeg,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <select value={fabricationStyle} onChange={(e) => setFabricationStyle(e.target.value as FabricationStyle)}>
              <option value="precision_inlay">{STYLE_LABEL.precision_inlay}</option>
              <option value="bold_signage">{STYLE_LABEL.bold_signage}</option>
              <option value="abstract_art">{STYLE_LABEL.abstract_art}</option>
            </select>
            <button type="submit" disabled={loading}>{loading ? "Processing..." : "Create Package"}</button>
          </div>
        </form>
        {error && <p className="error-text">{error}</p>}
      </div>

      {jobId && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h2>Result</h2>
            <div className={`status ${success ? "status-success" : ""}`}>{success ? "Success" : job?.status ?? "processing"}</div>
          </div>
          <p><strong>Job ID:</strong> {jobId}</p>
          <div className="grid">
            <StorefrontAsset title="Artistic Illustration" src={job?.artifacts.art ?? null} />
            <StorefrontAsset title="Production Toolpath SVG" src={job?.artifacts.toolpath_svg ?? null} />
          </div>
          <div style={{ marginTop: 14 }}>
            {job?.artifacts.package_zip ? (
              <a href={job.artifacts.package_zip}>
                <button>Download Package ZIP</button>
              </a>
            ) : (
              <button disabled>Package pending...</button>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function StorefrontAsset({ title, src }: { title: string; src: string | null }) {
  if (!src) {
    return (
      <div className="card">
        <h3>{title}</h3>
        <p>Not available yet.</p>
      </div>
    );
  }
  const fullSrc = src.startsWith("http") ? src : `${API_BASE}${src}`;
  const isSvg = src.endsWith(".svg");
  return (
    <div className="card">
      <h3>{title}</h3>
      {isSvg ? <object data={fullSrc} type="image/svg+xml" width="100%" height={260} /> : <img src={fullSrc} alt={title} />}
    </div>
  );
}
