import { apiFetch } from "./client.js";

export function listAuditLogs({ page = 1, action, modelName, dateFrom, dateTo } = {}) {
  const params = new URLSearchParams({ page: String(page) });
  if (action) params.set("action", action);
  if (modelName) params.set("model_name", modelName);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return apiFetch(`/audit/logs/?${params.toString()}`);
}
