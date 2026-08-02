export interface TripVolumeSummary {
  total: number;
  by_status: Record<string, number>;
}

export interface CancellationNoShowSummary {
  total: number;
  cancelled: number;
  no_show: number;
  cancellation_rate: number;
  no_show_rate: number;
}

export interface CycleTimeSummary {
  avg_cycle_minutes: number | null;
  sample_size: number;
}

export interface RevenueSummary {
  draft_total: string;
  outstanding_total: string;
  paid_total: string;
  billed_total: string;
}

export interface KpiSummary {
  date_from: string;
  date_to: string;
  trip_volume: TripVolumeSummary;
  cancellation_no_show: CancellationNoShowSummary;
  cycle_time: CycleTimeSummary;
  revenue: RevenueSummary;
}

export interface RevenueByMonthEntry {
  month: string;
  total: string;
}

export type AuditAction = "VIEW" | "CREATE" | "UPDATE" | "DELETE" | "EXPORT";

export interface AuditLogEntry {
  id: number;
  actor: string | null;
  actor_email: string | null;
  action: AuditAction;
  model_name: string;
  object_id: string;
  timestamp: string;
  ip_address: string | null;
  metadata: Record<string, unknown>;
}
