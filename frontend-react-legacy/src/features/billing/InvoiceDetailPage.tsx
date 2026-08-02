import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { InvoiceStatusBadge } from "./InvoiceStatusBadge";
import {
  useFinalizeInvoiceMutation,
  useInvoiceQuery,
  useMarkInvoicePaidMutation,
  useVoidInvoiceMutation,
} from "./useBilling";

export function InvoiceDetailPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const { data: invoice, isLoading, isError } = useInvoiceQuery(id);

  const finalizeInvoice = useFinalizeInvoiceMutation();
  const voidInvoice = useVoidInvoiceMutation();
  const markInvoicePaid = useMarkInvoicePaidMutation();

  const [voidReason, setVoidReason] = useState("");
  const [showVoidForm, setShowVoidForm] = useState(false);
  const [paymentReference, setPaymentReference] = useState("");
  const [showPaidForm, setShowPaidForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return <div className="page-status">Loading invoice...</div>;
  }
  if (isError || !invoice) {
    return <div className="page-status">Could not load that invoice.</div>;
  }

  async function handleFinalize() {
    setError(null);
    try {
      await finalizeInvoice.mutateAsync(id);
    } catch {
      setError("Could not finalize this invoice.");
    }
  }

  async function handleVoid() {
    setError(null);
    try {
      await voidInvoice.mutateAsync({ id, reason: voidReason });
      setShowVoidForm(false);
      setVoidReason("");
    } catch {
      setError("Could not void this invoice.");
    }
  }

  async function handleMarkPaid() {
    setError(null);
    try {
      await markInvoicePaid.mutateAsync({ id, paymentReference });
      setShowPaidForm(false);
    } catch {
      setError("Could not mark this invoice paid.");
    }
  }

  const backPath = isAdmin ? "/admin/billing/invoices" : "/rider/billing/invoices";

  return (
    <div className="portal-page">
      <h1>Invoice {invoice.invoice_number}</h1>
      <p>
        <Link to={backPath}>&larr; Back to invoices</Link>
      </p>

      <div className="trip-detail">
        <p>
          <InvoiceStatusBadge status={invoice.status} />
        </p>
        <p>Rider: {invoice.rider_name_snapshot}</p>
        {invoice.medicaid_id_snapshot && <p>Medicaid ID: {invoice.medicaid_id_snapshot}</p>}
        <p>Payer type: {invoice.payer_type === "MEDICAID" ? "Medicaid" : "Private pay"}</p>
        <p>Mobility tier: {invoice.mobility_need_snapshot || "Ambulatory (default)"}</p>
        <p>Mileage: {invoice.mileage_snapshot} mi</p>
        <p>Base fare: ${invoice.base_fare}</p>
        <p>
          Mileage amount: ${invoice.mileage_amount} (${invoice.per_mile_rate}/mi)
        </p>
        <p>
          <strong>Total: ${invoice.total_amount}</strong>
        </p>
        {invoice.payment_reference && <p>Payment reference: {invoice.payment_reference}</p>}
        {invoice.void_reason && <p>Void reason: {invoice.void_reason}</p>}
        <p className="page-status-note">
          Created {new Date(invoice.created_at).toLocaleString()}
          {invoice.finalized_at && ` · Finalized ${new Date(invoice.finalized_at).toLocaleString()}`}
          {invoice.paid_at && ` · Paid ${new Date(invoice.paid_at).toLocaleString()}`}
          {invoice.voided_at && ` · Voided ${new Date(invoice.voided_at).toLocaleString()}`}
        </p>
      </div>

      {error && <p className="form-error">{error}</p>}

      {isAdmin && invoice.status === "DRAFT" && (
        <button onClick={handleFinalize} disabled={finalizeInvoice.isPending}>
          {finalizeInvoice.isPending ? "Finalizing..." : "Finalize"}
        </button>
      )}

      {isAdmin && invoice.status === "FINALIZED" && !showPaidForm && (
        <button onClick={() => setShowPaidForm(true)}>Mark paid</button>
      )}
      {isAdmin && showPaidForm && (
        <div className="auth-form">
          <label htmlFor="payment_reference">Payment reference (optional)</label>
          <input
            id="payment_reference"
            value={paymentReference}
            onChange={(e) => setPaymentReference(e.target.value)}
          />
          <button onClick={handleMarkPaid} disabled={markInvoicePaid.isPending}>
            {markInvoicePaid.isPending ? "Saving..." : "Confirm paid"}
          </button>
        </div>
      )}

      {isAdmin && (invoice.status === "DRAFT" || invoice.status === "FINALIZED") && (
        <>
          {!showVoidForm && <button onClick={() => setShowVoidForm(true)}>Void invoice</button>}
          {showVoidForm && (
            <div className="auth-form">
              <label htmlFor="void_reason">Reason for voiding</label>
              <input
                id="void_reason"
                value={voidReason}
                onChange={(e) => setVoidReason(e.target.value)}
                required
              />
              <button onClick={handleVoid} disabled={voidInvoice.isPending || !voidReason}>
                {voidInvoice.isPending ? "Voiding..." : "Confirm void"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
