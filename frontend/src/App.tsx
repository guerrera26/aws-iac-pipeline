import { useEffect, useState } from "react";
import type { StatusResponse, VisitsResponse } from "./types";

type LoadState<T> =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "loaded"; data: T };

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return (await response.json()) as T;
}

function StatusPanel() {
  const [state, setState] = useState<LoadState<StatusResponse>>({ kind: "loading" });

  useEffect(() => {
    fetchJson<StatusResponse>("/api/status")
      .then((data) => setState({ kind: "loaded", data }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, []);

  if (state.kind === "loading") return <p>Loading status…</p>;
  if (state.kind === "error") return <p role="alert">Status unavailable: {state.message}</p>;

  const { hostname, uptime_seconds, version, server_time } = state.data;
  return (
    <dl>
      <dt>Hostname</dt>
      <dd>{hostname}</dd>
      <dt>Version</dt>
      <dd>{version}</dd>
      <dt>Uptime</dt>
      <dd>{uptime_seconds.toFixed(1)}s</dd>
      <dt>Server time</dt>
      <dd>{server_time}</dd>
    </dl>
  );
}

function VisitsPanel() {
  const [state, setState] = useState<LoadState<VisitsResponse>>({ kind: "loading" });

  useEffect(() => {
    fetchJson<VisitsResponse>("/api/visits")
      .then((data) => setState({ kind: "loaded", data }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, []);

  if (state.kind === "loading") return <p>Loading visits…</p>;
  if (state.kind === "error") return <p role="alert">Visits unavailable: {state.message}</p>;

  return <p className="visit-count">{state.data.visits}</p>;
}

export default function App() {
  return (
    <main>
      <h1>AWS IaC Pipeline</h1>
      <p className="subtitle">
        Terraform-provisioned infrastructure, deployed by Ansible, tested and gated by GitHub
        Actions — this page is a React + TypeScript frontend talking to a Flask API backed by
        Postgres.
      </p>

      <section>
        <h2>Backend status</h2>
        <StatusPanel />
      </section>

      <section>
        <h2>Visit counter (Postgres-backed)</h2>
        <VisitsPanel />
      </section>
    </main>
  );
}
