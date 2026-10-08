import { useEffect, useState } from "react";
import DataCleaner from "./DataCleaner";
import type { StatusResponse, VisitsResponse, VisitsSummaryResponse } from "./types";

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

/** Minimal hand-rolled SVG bar chart — no charting library needed for a
 * 24-bar sparkline, and it keeps the bundle small. */
function HourlyBarChart({ data }: { data: VisitsSummaryResponse["hourly"] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const barWidth = 100 / data.length;

  return (
    <svg
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      className="hourly-chart"
      role="img"
      aria-label="Visits per hour over the last 24 hours"
    >
      {data.map((bucket, i) => {
        const height = (bucket.count / max) * 36;
        return (
          <rect
            key={bucket.hour + i}
            x={i * barWidth + 0.5}
            y={40 - height}
            width={Math.max(0, barWidth - 1)}
            height={height}
          >
            <title>
              {bucket.hour} — {bucket.count} visit{bucket.count === 1 ? "" : "s"}
            </title>
          </rect>
        );
      })}
    </svg>
  );
}

function AnalyticsPanel() {
  const [state, setState] = useState<LoadState<VisitsSummaryResponse>>({ kind: "loading" });

  useEffect(() => {
    fetchJson<VisitsSummaryResponse>("/api/visits/summary")
      .then((data) => setState({ kind: "loaded", data }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, []);

  if (state.kind === "loading") return <p>Loading analytics…</p>;
  if (state.kind === "error") return <p role="alert">Analytics unavailable: {state.message}</p>;

  const { total, last_24h, hourly } = state.data;
  const first = hourly[0];
  const last = hourly[hourly.length - 1];

  return (
    <div>
      <dl className="analytics-summary">
        <dt>Total visits</dt>
        <dd>{total}</dd>
        <dt>Last 24 hours</dt>
        <dd>{last_24h}</dd>
      </dl>
      <HourlyBarChart data={hourly} />
      <div className="chart-labels">
        <span>{first.hour}</span>
        <span>{last.hour}</span>
      </div>
    </div>
  );
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
        <h2>Data cleaning tool (pandas)</h2>
        <DataCleaner />
      </section>

      <section>
        <h2>Backend status</h2>
        <StatusPanel />
      </section>

      <section>
        <h2>Visit counter (Postgres-backed)</h2>
        <VisitsPanel />
      </section>

      <section>
        <h2>Visit analytics</h2>
        <p className="section-note">
          Aggregated with a <code>GROUP BY date_trunc('hour', ...)</code> query against the same
          visits table — a small example of the app doing real data work, not just CRUD.
        </p>
        <AnalyticsPanel />
      </section>
    </main>
  );
}
