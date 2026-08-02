import { apiClient } from "../../lib/apiClient";
import type { AuditLogEntry, KpiSummary, RevenueByMonthEntry } from "./types";
import type { Paginated } from "../trips/types";

export async function getKpiSummary(dateFrom?: string, dateTo?: string): Promise<KpiSummary> {
  const response = await apiClient.get<KpiSummary>("/reports/kpis/summary/", {
    params: { date_from: dateFrom, date_to: dateTo },
  });
  return response.data;
}

export async function getRevenueByMonth(
  dateFrom?: string,
  dateTo?: string,
): Promise<RevenueByMonthEntry[]> {
  const response = await apiClient.get<RevenueByMonthEntry[]>("/reports/kpis/revenue-by-month/", {
    params: { date_from: dateFrom, date_to: dateTo },
  });
  return response.data;
}

export interface AuditLogFilters {
  page?: number;
  action?: string;
  model_name?: string;
  date_from?: string;
  date_to?: string;
}

export async function listAuditLogs(
  filters: AuditLogFilters = {},
): Promise<Paginated<AuditLogEntry>> {
  const response = await apiClient.get<Paginated<AuditLogEntry>>("/audit/logs/", {
    params: filters,
  });
  return response.data;
}
