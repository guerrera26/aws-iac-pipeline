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
