export interface StatusResponse {
  hostname: string;
  uptime_seconds: number;
  version: string;
  server_time: string;
}

export interface VisitsResponse {
  visits: number;
}

export interface HourlyVisitBucket {
  hour: string;
  count: number;
}

export interface VisitsSummaryResponse {
  total: number;
  last_24h: number;
  hourly: HourlyVisitBucket[];
}

export interface HealthResponse {
  status: string;
}

/** Which cleaning steps to run; mirrors DEFAULT_OPTIONS in app/cleaner.py. */
export interface CleanOptions {
  normalize_headers: boolean;
  trim_whitespace: boolean;
  standardize_nulls: boolean;
  standardize_text: boolean;
  normalize_phones: boolean;
  normalize_dates: boolean;
  parse_numbers: boolean;
  remove_duplicates: boolean;
  fill_numeric_median: boolean;
}

export interface CleanedCell {
  /** The cleaned value. */
  v: string;
  /** The original value; present only when the cleaner changed this cell. */
  was?: string;
}

export interface CleanedPreviewRow {
  /** Line number in the uploaded file (header is line 1). */
  source_line: number;
  cells: CleanedCell[];
}

export interface CleanStep {
  id: string;
  label: string;
  count: number;
}

export interface CleanSummary {
  rows_in: number;
  rows_out: number;
  cells_changed: number;
  duplicates_removed: number;
  blank_rows_removed: number;
}

export interface CleanResponse {
  summary: CleanSummary;
  steps: CleanStep[];
  original_columns: string[];
  columns: string[];
  preview: { rows: CleanedPreviewRow[]; rows_changed: number };
  cleaned_csv: string;
  filename: string;
  cleaned_filename: string;
}
