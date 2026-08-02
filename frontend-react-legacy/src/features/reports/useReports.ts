import { useQuery } from "@tanstack/react-query";
import { getKpiSummary, getRevenueByMonth, listAuditLogs, type AuditLogFilters } from "./api";

export function useKpiSummaryQuery(dateFrom?: string, dateTo?: string) {
  return useQuery({
    queryKey: ["kpi-summary", dateFrom, dateTo],
    queryFn: () => getKpiSummary(dateFrom, dateTo),
  });
}

export function useRevenueByMonthQuery(dateFrom?: string, dateTo?: string) {
  return useQuery({
    queryKey: ["revenue-by-month", dateFrom, dateTo],
    queryFn: () => getRevenueByMonth(dateFrom, dateTo),
  });
}

export function useAuditLogsQuery(filters: AuditLogFilters) {
  return useQuery({
    queryKey: ["audit-logs", filters],
    queryFn: () => listAuditLogs(filters),
  });
}
