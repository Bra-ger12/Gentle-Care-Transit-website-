import { apiClient } from "../../lib/apiClient";
import type { Paginated } from "../trips/types";
import type { Invoice, InvoiceListItem, RateSchedule, RateSchedulePayload } from "./types";

export async function listRateSchedules(): Promise<Paginated<RateSchedule>> {
  const response = await apiClient.get<Paginated<RateSchedule>>("/billing/rate-schedules/");
  return response.data;
}

export async function createRateSchedule(payload: RateSchedulePayload): Promise<RateSchedule> {
  const response = await apiClient.post<RateSchedule>("/billing/rate-schedules/", payload);
  return response.data;
}

export async function updateRateSchedule(
  id: string,
  payload: Partial<RateSchedulePayload>,
): Promise<RateSchedule> {
  const response = await apiClient.patch<RateSchedule>(`/billing/rate-schedules/${id}/`, payload);
  return response.data;
}

export async function listInvoices(page = 1): Promise<Paginated<InvoiceListItem>> {
  const response = await apiClient.get<Paginated<InvoiceListItem>>("/billing/invoices/", {
    params: { page },
  });
  return response.data;
}

export async function getInvoice(id: string): Promise<Invoice> {
  const response = await apiClient.get<Invoice>(`/billing/invoices/${id}/`);
  return response.data;
}

export async function generateInvoices(tripId?: string): Promise<Invoice[]> {
  const response = await apiClient.post<Invoice[]>("/billing/invoices/generate/", {
    trip_id: tripId,
  });
  return response.data;
}

export async function finalizeInvoice(id: string): Promise<Invoice> {
  const response = await apiClient.post<Invoice>(`/billing/invoices/${id}/finalize/`);
  return response.data;
}

export async function voidInvoice(id: string, reason: string): Promise<Invoice> {
  const response = await apiClient.post<Invoice>(`/billing/invoices/${id}/void/`, { reason });
  return response.data;
}

export async function markInvoicePaid(
  id: string,
  paymentReference?: string,
): Promise<Invoice> {
  const response = await apiClient.post<Invoice>(`/billing/invoices/${id}/mark-paid/`, {
    payment_reference: paymentReference,
  });
  return response.data;
}

// No prior precedent in this codebase for downloading a binary response --
// unlike every other endpoint here, this one bypasses TanStack Query
// entirely (there's no cached "data", just a one-shot file save) and
// triggers a browser download via an object URL.
export async function downloadMedicaidExport(
  dateFrom: string,
  dateTo: string,
  exportFormat: "csv" | "pdf",
): Promise<void> {
  const response = await apiClient.get("/billing/medicaid-export/", {
    params: { date_from: dateFrom, date_to: dateTo, export_format: exportFormat },
    responseType: "blob",
  });
  const url = URL.createObjectURL(response.data as Blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `medicaid_export_${dateFrom}_${dateTo}.${exportFormat}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
