import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import App from "./App";
import type { StatusResponse, VisitsResponse, VisitsSummaryResponse } from "./types";

const mockStatus: StatusResponse = {
  hostname: "test-host",
  uptime_seconds: 42,
  version: "1.1.0",
  server_time: "2026-09-28T00:00:00Z",
};

const mockVisits: VisitsResponse = { visits: 7 };

const mockSummary: VisitsSummaryResponse = {
  total: 42,
  last_24h: 9,
  hourly: Array.from({ length: 24 }, (_, i) => ({
    hour: `${String(i).padStart(2, "0")}:00`,
    count: i === 12 ? 3 : 0,
  })),
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      let body: unknown;
      if (url.includes("/api/status")) body = mockStatus;
      else if (url.includes("/api/visits/summary")) body = mockSummary;
      else body = mockVisits;

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

  it("shows visit analytics once they load", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByLabelText("Visits per hour over the last 24 hours")).toBeInTheDocument();
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
