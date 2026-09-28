export interface StatusResponse {
  hostname: string;
  uptime_seconds: number;
  version: string;
  server_time: string;
}

export interface VisitsResponse {
  visits: number;
}

export interface HealthResponse {
  status: string;
}
