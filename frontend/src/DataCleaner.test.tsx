import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DataCleaner from "./DataCleaner";
import type { CleanResponse } from "./types";

const cleaned: CleanResponse = {
  summary: { rows_in: 13, rows_out: 10, cells_changed: 39, duplicates_removed: 1, blank_rows_removed: 2 },
  steps: [
    { id: "trim_whitespace", label: "Extra whitespace trimmed", count: 4 },
    { id: "remove_duplicates", label: "Duplicate rows removed", count: 1 },
    { id: "normalize_phones", label: "Phone numbers formatted as 555-123-4567", count: 0 },
  ],
  original_columns: ["Customer Name", "Phone"],
  columns: ["customer_name", "phone"],
  preview: {
    rows: [{ source_line: 2, cells: [{ v: "John Smith", was: "JOHN SMITH" }, { v: "", was: "N/A" }] }],
    rows_changed: 1,
  },
  cleaned_csv: "customer_name,phone\nJohn Smith,\n",
  filename: "sample.csv",
  cleaned_filename: "sample_cleaned.csv",
};

function jsonResponse(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: () => Promise.resolve(body) } as Response;
}

function mockFetch(cleanResponse: Response = jsonResponse(cleaned)) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    void init;
    if (url === "/api/clean/sample") {
      return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve("a,b\n1,2\n") } as Response);
    }
    return Promise.resolve(cleanResponse);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The multipart body of the most recent POST to /api/clean. */
function lastCleanForm(fetchMock: ReturnType<typeof mockFetch>): FormData {
  const cleanCalls = fetchMock.mock.calls.filter(([url]) => url === "/api/clean");
  const init = cleanCalls[cleanCalls.length - 1][1];
  return init?.body as FormData;
}

beforeEach(() => {
  mockFetch();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("DataCleaner", () => {
  it("does nothing until the user picks some data", () => {
    const fetchMock = mockFetch();
    render(<DataCleaner />);
    expect(screen.getByRole("button", { name: "Try the sample data" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cleans the sample data and reports what changed", async () => {
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));

    expect(await screen.findByText("Extra whitespace trimmed")).toBeInTheDocument();
    expect(screen.getByText("Rows out").nextElementSibling).toHaveTextContent("10");
    expect(screen.getByText("Duplicates removed", { selector: "dt" }).nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Phone numbers formatted as 555-123-4567")).toBeInTheDocument();
  });

  it("shows the original value next to the cleaned one for each changed cell", async () => {
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));

    const original = await screen.findByText("JOHN SMITH");
    expect(original.tagName).toBe("DEL");
    expect(screen.getByText("John Smith").tagName).toBe("INS");
    expect(screen.getByText("N/A").tagName).toBe("DEL");
  });

  it("shows the original header when a column name was standardized", async () => {
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));

    const originalHeader = await screen.findByText("Customer Name");
    expect(originalHeader.tagName).toBe("DEL");
  });

  it("uploads the chosen file along with the default options", async () => {
    const fetchMock = mockFetch();
    render(<DataCleaner />);
    const file = new File(["a,b\n1,2\n"], "mine.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Upload a CSV"), { target: { files: [file] } });

    await screen.findByText("Extra whitespace trimmed");
    const form = lastCleanForm(fetchMock);
    expect((form.get("file") as File).name).toBe("mine.csv");
    const options = JSON.parse(form.get("options") as string);
    expect(options.remove_duplicates).toBe(true);
    expect(options.fill_numeric_median).toBe(false);
  });

  it("re-runs with the new setting when a step is toggled", async () => {
    const fetchMock = mockFetch();
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));
    await screen.findByText("Extra whitespace trimmed");

    fireEvent.click(screen.getByLabelText(/Format phone numbers/));

    await waitFor(() => {
      const options = JSON.parse(lastCleanForm(fetchMock).get("options") as string);
      expect(options.normalize_phones).toBe(false);
    });
  });

  it("shows the server's error message when cleaning fails", async () => {
    mockFetch(jsonResponse({ error: "could not parse the file as CSV: bad row" }, 422));
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not parse the file as CSV: bad row");
  });

  it("falls back to a generic message when the error response isn't JSON", async () => {
    mockFetch({ ok: false, status: 502, json: () => Promise.reject(new Error("not json")) } as Response);
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed (502)");
  });

  it("tells the user when the sample can't be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 500 } as Response)));
    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sample unavailable");
  });

  it("downloads the cleaned CSV", async () => {
    const createObjectURL = vi.fn(() => "blob:cleaned");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<DataCleaner />);
    fireEvent.click(screen.getByRole("button", { name: "Try the sample data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Download cleaned CSV" }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:cleaned");
  });
});
