import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import App from "./App";
import type { StatusResponse, VisitsResponse } from "./types";

const mockStatus: StatusResponse = {
  hostname: "test-host",
  uptime_seconds: 42,
  version: "1.1.0",
  server_time: "2026-09-28T00:00:00Z",
};

const mockVisits: VisitsResponse = { visits: 7 };

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.includes("/api/status") ? mockStatus : mockVisits;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
      } as Response);
    })
  );
});

describe("App", () => {
  it("renders the heading immediately", () => {
    render(<App />);
    expect(screen.getByText("AWS IaC Pipeline")).toBeInTheDocument();
  });

  it("shows status data once it loads", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("test-host")).toBeInTheDocument());
    expect(screen.getByText("1.1.0")).toBeInTheDocument();
  });

  it("shows the visit count once it loads", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
  });

  it("shows an error message if the API call fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response))
    );
    render(<App />);
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
  });
});
