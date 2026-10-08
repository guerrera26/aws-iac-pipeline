import { useEffect, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import type { CleanOptions, CleanResponse } from "./types";

const SAMPLE_NAME = "messy_customers_sample.csv";

const DEFAULT_OPTIONS: CleanOptions = {
  normalize_headers: true,
  trim_whitespace: true,
  standardize_nulls: true,
  standardize_text: true,
  normalize_phones: true,
  normalize_dates: true,
  parse_numbers: true,
  remove_duplicates: true,
  fill_numeric_median: false,
};

const OPTION_CONTROLS: { key: keyof CleanOptions; label: string; hint: string }[] = [
  { key: "normalize_headers", label: "Standardize column names", hint: "First Name becomes first_name" },
  { key: "trim_whitespace", label: "Trim extra whitespace", hint: "Leading, trailing and doubled spaces" },
  { key: "standardize_nulls", label: "Treat N/A, none and - as blank", hint: "One consistent way to say missing" },
  { key: "standardize_text", label: "Fix capitalization", hint: "Lowercase emails, capitalize names, cities and states" },
  { key: "normalize_phones", label: "Format phone numbers", hint: "(617) 555-0142 becomes 617-555-0142" },
  { key: "normalize_dates", label: "Standardize dates", hint: "Any common format becomes YYYY-MM-DD (03/04/2025 is read as March 4)" },
  { key: "parse_numbers", label: "Strip $ and thousands commas", hint: "$1,250.00 becomes 1250.00" },
  { key: "remove_duplicates", label: "Remove duplicate rows", hint: "Checked after cleaning, so near-duplicates match" },
  { key: "fill_numeric_median", label: "Fill missing numbers with the median", hint: "Off by default because it invents data" },
];

interface Source {
  name: string;
  file: Blob;
}

function errorMessage(body: unknown, status: number): string {
  if (typeof body === "object" && body !== null && "error" in body) {
    const { error } = body as { error: unknown };
    if (typeof error === "string") return error;
  }
  return `Request failed (${status})`;
}

function show(value: string): ReactNode {
  return value === "" ? <span className="blank">blank</span> : value;
}

function downloadCsv(data: CleanResponse) {
  // The leading BOM makes Excel read non-ASCII characters correctly.
  const url = URL.createObjectURL(new Blob(["﻿", data.cleaned_csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = data.cleaned_filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function DataCleaner() {
  const [source, setSource] = useState<Source | null>(null);
  const [options, setOptions] = useState<CleanOptions>(DEFAULT_OPTIONS);
  const [result, setResult] = useState<CleanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);

  // Re-run whenever the file or any option changes. The previous result stays on
  // screen while the new one loads, so toggling a step doesn't blank the table.
  useEffect(() => {
    if (!source) return;
    const controller = new AbortController();
    const form = new FormData();
    form.append("file", source.file, source.name);
    form.append("options", JSON.stringify(options));

    setBusy(true);
    setError(null);
    fetch("/api/clean", { method: "POST", body: form, signal: controller.signal })
      .then(async (response) => {
        const body: unknown = await response.json().catch(() => null);
        if (!response.ok) throw new Error(errorMessage(body, response.status));
        return body as CleanResponse;
      })
      .then((data) => {
        setResult(data);
        setBusy(false);
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setResult(null);
        setError(err.message);
        setBusy(false);
      });

    return () => controller.abort();
  }, [source, options]);

  async function loadSample() {
    setSampleError(null);
    try {
      const response = await fetch("/api/clean/sample");
      if (!response.ok) throw new Error(`/api/clean/sample returned ${response.status}`);
      const text = await response.text();
      setSource({ name: SAMPLE_NAME, file: new Blob([text], { type: "text/csv" }) });
    } catch (err) {
      setSampleError(err instanceof Error ? err.message : "Could not load the sample data");
    }
  }

  function onFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) setSource({ name: file.name, file });
  }

  function toggle(key: keyof CleanOptions) {
    setOptions((previous) => ({ ...previous, [key]: !previous[key] }));
  }

  return (
    <div className="cleaner">
      <p className="section-note">
        Drop in a messy CSV (up to 2 MB and 5,000 rows) and a pandas pipeline running on the EC2
        instance standardizes it and reports exactly what it changed. Nothing is stored: the file
        is cleaned in memory and sent straight back.
      </p>

      <div className="cleaner-actions">
        <button type="button" onClick={loadSample}>
          Try the sample data
        </button>
        <label className="file-button">
          Upload a CSV
          <input type="file" className="visually-hidden" accept=".csv,.tsv,.txt,text/csv" onChange={onFileChosen} />
        </label>
      </div>
      {sampleError && <p role="alert">Sample unavailable: {sampleError}</p>}

      <fieldset className="cleaner-options">
        <legend>Cleaning steps</legend>
        {OPTION_CONTROLS.map(({ key, label, hint }) => (
          <label key={key} className="cleaner-option">
            <input type="checkbox" checked={options[key]} onChange={() => toggle(key)} />
            <span>
              {label}
              <small>{hint}</small>
            </span>
          </label>
        ))}
      </fieldset>

      {source && (
        <p className="cleaner-source" aria-live="polite">
          {busy ? "Cleaning " : "Cleaned "}
          <strong>{source.name}</strong>
          {busy ? "…" : ""}
        </p>
      )}
      {error && <p role="alert">Could not clean this file: {error}</p>}

      {result && <CleanReport data={result} />}
    </div>
  );
}

function CleanReport({ data }: { data: CleanResponse }) {
  const { summary, steps, columns, original_columns, preview } = data;

  return (
    <div className="cleaner-result">
      <dl className="stat-tiles">
        <div>
          <dt>Rows in</dt>
          <dd>{summary.rows_in}</dd>
        </div>
        <div>
          <dt>Rows out</dt>
          <dd>{summary.rows_out}</dd>
        </div>
        <div>
          <dt>Cells fixed</dt>
          <dd>{summary.cells_changed}</dd>
        </div>
        <div>
          <dt>Duplicates removed</dt>
          <dd>{summary.duplicates_removed}</dd>
        </div>
      </dl>

      <h3>What the pipeline did</h3>
      <ul className="cleaner-steps">
        {steps.map((step) => (
          <li key={step.id} className={step.count === 0 ? "nothing" : undefined}>
            <span className="step-count">{step.count}</span>{" "}
            {step.label}
          </li>
        ))}
      </ul>

      <h3>Before and after</h3>
      <p className="section-note">
        {preview.rows_changed === 0
          ? "Nothing needed fixing, so these are the first rows as they are."
          : `Showing ${preview.rows.length} of ${preview.rows_changed} changed rows. Highlighted cells were changed, with the original value struck through above the new one.`}
      </p>
      <div className="table-wrap" role="region" aria-label="Cleaned data preview" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Line</th>
              {columns.map((column, i) => (
                <th key={i} scope="col">
                  {original_columns[i] !== column && <del>{show(original_columns[i] ?? "")}</del>}
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row) => (
              <tr key={row.source_line}>
                <th scope="row">{row.source_line}</th>
                {row.cells.map((cell, i) =>
                  cell.was === undefined ? (
                    <td key={i}>{show(cell.v)}</td>
                  ) : (
                    <td key={i} className="changed">
                      <del>{show(cell.was)}</del>
                      <ins>{show(cell.v)}</ins>
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p>
        <button type="button" className="download" onClick={() => downloadCsv(data)}>
          Download cleaned CSV
        </button>
      </p>
    </div>
  );
}
