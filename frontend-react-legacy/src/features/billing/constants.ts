import type { InvoiceStatus } from "./types";

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  DRAFT: "Draft",
  FINALIZED: "Finalized",
  PAID: "Paid",
  VOID: "Void",
};
