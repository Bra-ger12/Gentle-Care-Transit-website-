import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { InvoiceStatusBadge } from "./InvoiceStatusBadge";
import { useGenerateInvoicesMutation, useInvoicesQuery } from "./useBilling";

export function InvoiceListPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useInvoicesQuery(page);
  const generateInvoices = useGenerateInvoicesMutation();
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setError(null);
    try {
      await generateInvoices.mutateAsync(undefined);
    } catch {
      setError("Could not generate invoices.");
    }
  }

  if (isLoading) {
    return <div className="page-status">Loading invoices...</div>;
  }
  if (isError) {
    return <div className="page-status">Could not load invoices.</div>;
  }

  const invoices = data?.results ?? [];
  const basePath = isAdmin ? "/admin/billing/invoices" : "/rider/billing/invoices";

  return (
    <div className="portal-page">
      <h1>{isAdmin ? "Invoices" : "Your invoices"}</h1>

      {isAdmin && (
        <p>
          <Link to="/admin/billing/rate-schedules">Rate schedules</Link> &middot;{" "}
          <Link to="/admin/billing/medicaid-export">Medicaid export</Link>
        </p>
      )}

      {isAdmin && (
        <>
          <button onClick={handleGenerate} disabled={generateInvoices.isPending}>
            {generateInvoices.isPending ? "Generating..." : "Generate invoices for completed trips"}
          </button>
          {error && <p className="form-error">{error}</p>}
        </>
      )}

      {invoices.length === 0 && <p>No invoices yet.</p>}

      <table className="dispatch-table">
        <thead>
          <tr>
            <th>Invoice #</th>
            <th>Rider</th>
            <th>Status</th>
            <th>Total</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr key={invoice.id} className="dispatch-table__row">
              <td>
                <Link to={`${basePath}/${invoice.id}`}>{invoice.invoice_number}</Link>
              </td>
              <td>{invoice.rider_name_snapshot}</td>
              <td>
                <InvoiceStatusBadge status={invoice.status} />
              </td>
              <td>${invoice.total_amount}</td>
              <td>{new Date(invoice.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {(data?.next || data?.previous) && (
        <div className="pagination">
          <button disabled={!data?.previous} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <button disabled={!data?.next} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
