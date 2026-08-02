import { apiFetch, apiFetchBlob } from "./client.js";

export function getKpiSummary(dateFrom, dateTo) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const query = params.toString();
  return apiFetch(`/reports/kpis/summary/${query ? `?${query}` : ""}`);
}

export function getRevenueByMonth(dateFrom, dateTo) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const query = params.toString();
  return apiFetch(`/reports/kpis/revenue-by-month/${query ? `?${query}` : ""}`);
}

export function getDriverReport(dateFrom, dateTo) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const query = params.toString();
  return apiFetch(`/reports/driver/summary/${query ? `?${query}` : ""}`);
}

export function getDriverPerformance(dateFrom, dateTo) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const query = params.toString();
  return apiFetch(`/reports/driver-performance/${query ? `?${query}` : ""}`);
}

export const REPORT_EXPORTS = [
  ["trips", "Trips", "Every trip in the range, with status, driver and mileage."],
  ["revenue", "Revenue", "Invoice lines with the full fare breakdown."],
  ["drivers", "Driver performance", "Trips, no-shows, miles and rating per driver."],
  ["mileage", "Mileage", "Miles per driver per day, for reimbursement."],
];

/**
 * Fetch a CSV export as a blob.
 *
 * Deliberately not a plain <a download> link: the API is authenticated with a
 * bearer token held in memory, which a browser-initiated navigation would not
 * send. The blob is turned into a download by the caller.
 */
export function downloadReport(report, dateFrom, dateTo) {
  const params = new URLSearchParams({ report });
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return apiFetchBlob(`/reports/export/?${params.toString()}`);
}
