import { INVOICE_STATUS_LABELS } from "./constants";
import type { InvoiceStatus } from "./types";

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span className={`invoice-status invoice-status--${status.toLowerCase()}`}>
      {INVOICE_STATUS_LABELS[status]}
    </span>
  );
}
