"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL } from "@/lib/api-client";

import styles from "./frame.module.css";

type JsonObject = Record<string, unknown>;

type FrameAssuranceLabProps = {
  contract: JsonObject;
};

type LabState = "idle" | "running" | "passed" | "review" | "failed";

type RhinoAdapterResponse = {
  status?: string;
  exchange_hash?: string;
  contract_hash?: string | null;
  structural_contract?: { nodes?: unknown[]; members?: unknown[] } | null;
  violations?: Array<{ code?: string; message?: string }>;
};

type CadResponse = {
  status?: string;
  contract_hash?: string;
  artifact_hash?: string;
  dxf_base64?: string;
  verification?: {
    status?: string;
    summary?: Record<string, unknown>;
    violations?: Array<{ code?: string; message?: string }>;
  };
  error?: { message?: string } | null;
};

type SurrogateResponse = {
  status?: "PREDICTED" | "REVIEW_REQUIRED";
  model_id?: string;
  model_hash?: string;
  max_displacement_mm?: number | null;
  max_utilization?: number | null;
  uncertainty?: {
    calibrated_score?: number;
    threshold?: number;
    relative_score?: number;
    calibrated_threshold?: number;
    [key: string]: unknown;
  };
  ood_reasons?: string[];
  review_reasons?: string[];
  authoritative?: boolean;
  exact_solver_required?: boolean;
};

type BenchmarkResponse = {
  status?: string;
  model_comparison?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  versions?: Record<string, unknown>;
  error?: { message?: string } | null;
};

function compactHash(value?: string | null) {
  if (!value) return "not issued";
  return value.length > 24 ? `${value.slice(0, 14)}…${value.slice(-7)}` : value;
}

function finiteMetric(value: unknown, digits = 3) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "pending";
}

function statusClass(state: LabState) {
  if (state === "passed") return styles.labPassed;
  if (state === "review") return styles.labReview;
  if (state === "failed") return styles.labFailed;
  if (state === "running") return styles.labRunning;
  return styles.labIdle;
}

function decodeBase64(value: string) {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

async function jsonResponse<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => null)) as T | null;
  if (!response.ok || !payload) {
    const message =
      payload && typeof payload === "object" && "error" in payload
        ? String((payload as { error?: { message?: string } }).error?.message ?? "")
        : "";
    throw new Error(message || `Request returned HTTP ${response.status}.`);
  }
  return payload;
}

export default function FrameAssuranceLab({ contract }: FrameAssuranceLabProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const contractRevision = useRef(0);
  const [rhinoState, setRhinoState] = useState<LabState>("idle");
  const [rhinoResult, setRhinoResult] = useState<RhinoAdapterResponse | null>(null);
  const [rhinoError, setRhinoError] = useState<string | null>(null);
  const [cadState, setCadState] = useState<LabState>("idle");
  const [cadResult, setCadResult] = useState<CadResponse | null>(null);
  const [cadError, setCadError] = useState<string | null>(null);
  const [surrogateState, setSurrogateState] = useState<LabState>("idle");
  const [surrogate, setSurrogate] = useState<SurrogateResponse | null>(null);
  const [surrogateError, setSurrogateError] = useState<string | null>(null);
  const [parity, setParity] = useState<BenchmarkResponse | null>(null);
  const [gnnBenchmark, setGnnBenchmark] = useState<BenchmarkResponse | null>(null);

  useEffect(() => {
    contractRevision.current += 1;
    const resetTimer = window.setTimeout(() => {
      setCadState("idle");
      setCadResult(null);
      setCadError(null);
      setSurrogateState("idle");
      setSurrogate(null);
      setSurrogateError(null);
    }, 0);
    return () => window.clearTimeout(resetTimer);
  }, [contract]);

  useEffect(() => {
    const controller = new AbortController();
    async function loadBenchmarks() {
      const [parityResponse, gnnResponse] = await Promise.allSettled([
        fetch(`${API_URL}/api/v1/frame/benchmarks/opensees`, {
          cache: "no-store",
          signal: controller.signal,
        }).then(jsonResponse<BenchmarkResponse>),
        fetch(`${API_URL}/api/v1/frame/benchmarks/gnn`, {
          cache: "no-store",
          signal: controller.signal,
        }).then(jsonResponse<BenchmarkResponse>),
      ]);
      if (parityResponse.status === "fulfilled") setParity(parityResponse.value);
      else setParity({ status: "UNAVAILABLE" });
      if (gnnResponse.status === "fulfilled") setGnnBenchmark(gnnResponse.value);
      else setGnnBenchmark({ status: "UNAVAILABLE" });
    }
    void loadBenchmarks();
    return () => controller.abort();
  }, []);

  async function importRhinoExchange(file: File) {
    setRhinoState("running");
    setRhinoResult(null);
    setRhinoError(null);
    try {
      if (file.size > 2_000_000) throw new Error("Rhino exchange JSON must be 2 MB or smaller.");
      const parsed = JSON.parse(await file.text()) as JsonObject;
      const response = await fetch(`${API_URL}/api/v1/frame/rhino/adapt`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
        cache: "no-store",
      });
      const payload = await jsonResponse<RhinoAdapterResponse>(response);
      setRhinoResult(payload);
      setRhinoState(payload.status === "ready" ? "passed" : "review");
    } catch (reason) {
      setRhinoError(reason instanceof Error ? reason.message : "Rhino exchange import failed.");
      setRhinoState("failed");
    }
  }

  async function runCadRoundTrip() {
    const requestRevision = contractRevision.current;
    setCadState("running");
    setCadResult(null);
    setCadError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/frame/cad/run`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(contract),
        cache: "no-store",
      });
      const payload = await jsonResponse<CadResponse>(response);
      if (requestRevision !== contractRevision.current) return;
      setCadResult(payload);
      const status = payload.status?.toLowerCase();
      setCadState(status === "passed" || status === "verified" ? "passed" : "review");
    } catch (reason) {
      if (requestRevision !== contractRevision.current) return;
      setCadError(reason instanceof Error ? reason.message : "DXF round-trip failed.");
      setCadState("failed");
    }
  }

  async function runSurrogate() {
    const requestRevision = contractRevision.current;
    setSurrogateState("running");
    setSurrogate(null);
    setSurrogateError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/frame/surrogate/predict`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(contract),
        cache: "no-store",
      });
      const payload = await jsonResponse<SurrogateResponse>(response);
      if (requestRevision !== contractRevision.current) return;
      setSurrogate(payload);
      setSurrogateState(payload.status === "PREDICTED" ? "passed" : "review");
    } catch (reason) {
      if (requestRevision !== contractRevision.current) return;
      setSurrogateError(reason instanceof Error ? reason.message : "Surrogate inference failed.");
      setSurrogateState("failed");
    }
  }

  function downloadDxf() {
    if (!cadResult?.dxf_base64) return;
    const blob = new Blob([decodeBase64(cadResult.dxf_base64)], {
      type: "application/dxf",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "frameguard-screening-model.dxf";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const parityStatus = parity?.status?.toUpperCase() ?? "LOADING";
  const gnnStatus = gnnBenchmark?.status?.toUpperCase() ?? "LOADING";

  return (
    <section className={styles.assuranceLab} data-testid="frame-assurance-lab">
      <header className={styles.labHeader}>
        <div>
          <span>Model-to-evidence pipeline · 04 controls</span>
          <h2>CAD coordinates in. Guarded engineering evidence out.</h2>
        </div>
        <p>
          Rhino metadata, serialized DXF, an independent solver, and a learned estimate keep
          separate provenance. Only deterministic checks can issue the screening result.
        </p>
      </header>

      <div className={styles.labGrid}>
        <article
          className={`${styles.labModule} ${styles.labSource} ${statusClass(rhinoState)}`}
          data-testid="frame-rhino-adapter"
          data-state={rhinoState}
        >
          <div className={styles.labModuleHead}>
            <span>01 / source adapter</span>
            <b>{rhinoState === "passed" ? "NORMALIZED" : rhinoState === "running" ? "READING" : rhinoState === "review" ? "CONFIRM" : rhinoState === "failed" ? "FAILED" : "WAITING"}</b>
          </div>
          <h3>Rhino + Grasshopper exchange</h3>
          <p>Straight centerlines and object user strings become a millimetre contract without guessing units or datum.</p>
          <dl className={styles.labFacts}>
            <div><dt>Exchange</dt><dd>{compactHash(rhinoResult?.exchange_hash)}</dd></div>
            <div><dt>Contract</dt><dd>{compactHash(rhinoResult?.contract_hash)}</dd></div>
            <div><dt>Entities</dt><dd>{rhinoResult?.structural_contract ? `${rhinoResult.structural_contract.nodes?.length ?? 0} N / ${rhinoResult.structural_contract.members?.length ?? 0} M · mm` : "not loaded"}</dd></div>
          </dl>
          {rhinoError && <p className={styles.labError} role="alert">{rhinoError}</p>}
          {rhinoResult?.violations?.length ? <p className={styles.labWarning}>{rhinoResult.violations[0].code}: {rhinoResult.violations[0].message}</p> : null}
          <input
            ref={fileInput}
            className={styles.visuallyHidden}
            type="file"
            accept="application/json,.json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importRhinoExchange(file);
              event.currentTarget.value = "";
            }}
          />
          <button type="button" className={styles.labAction} onClick={() => fileInput.current?.click()} disabled={rhinoState === "running"}>
            {rhinoState === "running" ? "Reading exchange…" : "Import Rhino exchange JSON"}
          </button>
        </article>

        <article
          className={`${styles.labModule} ${styles.labCad} ${statusClass(cadState)}`}
          data-testid="frame-dxf-assurance"
          data-state={cadState}
        >
          <div className={styles.labModuleHead}>
            <span>02 / serialized geometry</span>
            <b>{cadState === "passed" ? "0.001 MM VERIFIED" : cadState === "running" ? "REOPENING" : cadState === "review" ? "BLOCKED" : cadState === "failed" ? "FAILED" : "READY"}</b>
          </div>
          <h3>DXF write → reopen → remeasure</h3>
          <p>The verifier checks R2013/mm, datum metadata, XDATA identity, centerline endpoints, duplicates, and tampering.</p>
          <dl className={styles.labFacts}>
            <div><dt>Contract</dt><dd>{compactHash(cadResult?.contract_hash)}</dd></div>
            <div><dt>Artifact</dt><dd>{compactHash(cadResult?.artifact_hash)}</dd></div>
            <div><dt>Verifier</dt><dd>{cadResult?.verification?.status ?? "not run"}</dd></div>
          </dl>
          {cadError && <p className={styles.labError} role="alert">{cadError}</p>}
          {cadResult?.verification?.violations?.length ? <p className={styles.labWarning}>{cadResult.verification.violations[0].code}: {cadResult.verification.violations[0].message}</p> : null}
          <div className={styles.labActions}>
            <button type="button" className={styles.labAction} onClick={runCadRoundTrip} disabled={cadState === "running"}>
              {cadState === "running" ? "Reopening DXF…" : "Run DXF assurance"}
            </button>
            <button type="button" className={styles.labTextAction} onClick={downloadDxf} disabled={!cadResult?.dxf_base64 || cadState !== "passed"}>
              Download screened DXF
            </button>
          </div>
        </article>

        <article
          className={`${styles.labModule} ${styles.labParity} ${parityStatus === "PASSED" ? styles.labPassed : parityStatus === "FAILED" ? styles.labFailed : styles.labReview}`}
          data-testid="frame-opensees-parity"
          data-state={parityStatus.toLowerCase()}
        >
          <div className={styles.labModuleHead}><span>03 / independent solver</span><b>{parityStatus}</b></div>
          <h3>OpenSees parity benchmark</h3>
          <p>The NumPy frame implementation is compared with genuine OpenSeesPy on cantilever, portal, and pipe-rack cases.</p>
          <dl className={styles.labFacts}>
            <div><dt>Cases</dt><dd>{String(parity?.summary?.case_count ?? parity?.summary?.total_cases ?? "loading")}</dd></div>
            <div><dt>Passed</dt><dd>{String(parity?.summary?.passed_count ?? parity?.summary?.passed_cases ?? "loading")}</dd></div>
            <div><dt>OpenSees</dt><dd>{String(parity?.versions?.openseespy ?? parity?.versions?.opensees ?? "loading")}</dd></div>
          </dl>
        </article>

        <article
          className={`${styles.labModule} ${styles.labAi} ${statusClass(surrogateState)}`}
          data-testid="frame-gnn-surrogate"
          data-state={surrogateState}
        >
          <div className={styles.labModuleHead}>
            <span>04 / learned comparison</span>
            <b>{surrogate?.status ?? (surrogateState === "running" ? "INFERENCE" : gnnStatus)}</b>
          </div>
          <h3>GraphSAGE / GAT uncertainty gate</h3>
          <p>The learned model is advisory. Out-of-distribution inputs or calibrated uncertainty force REVIEW_REQUIRED.</p>
          <div className={styles.labAiMetrics}>
            <div><span>Predicted displacement</span><strong>{finiteMetric(surrogate?.max_displacement_mm, 2)}</strong><small>mm</small></div>
            <div><span>Predicted utilization</span><strong>{finiteMetric(surrogate?.max_utilization, 3)}</strong><small>ratio</small></div>
            <div><span>Uncertainty score</span><strong>{finiteMetric(surrogate?.uncertainty?.relative_score ?? surrogate?.uncertainty?.calibrated_score, 3)}</strong><small>threshold {finiteMetric(surrogate?.uncertainty?.calibrated_threshold ?? surrogate?.uncertainty?.threshold, 3)}</small></div>
          </div>
          {surrogateError && <p className={styles.labError} role="alert">{surrogateError}</p>}
          {surrogate?.review_reasons?.length ? <p className={styles.labWarning}>{surrogate.review_reasons.join(" · ")}</p> : null}
          <button type="button" className={styles.labAction} onClick={runSurrogate} disabled={surrogateState === "running"}>
            {surrogateState === "running" ? "Estimating with ensemble…" : "Run advisory GNN"}
          </button>
          <small className={styles.labBoundary}>authoritative=false · exact_solver_required=true</small>
        </article>
      </div>
    </section>
  );
}
