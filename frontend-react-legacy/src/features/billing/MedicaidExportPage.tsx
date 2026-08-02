import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { downloadMedicaidExport } from "./api";

export function MedicaidExportPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload(event: FormEvent, exportFormat: "csv" | "pdf") {
    event.preventDefault();
    setError(null);
    setIsDownloading(true);
    try {
      await downloadMedicaidExport(dateFrom, dateTo, exportFormat);
    } catch {
      setError("Could not generate that export. Check the date range and try again.");
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="portal-page">
      <h1>ND Medicaid NEMT export</h1>
      <p>
        <Link to="/admin/billing/invoices">Invoices</Link> &middot;{" "}
        <Link to="/admin/billing/rate-schedules">Rate schedules</Link>
      </p>
      <p className="page-status-note">
        Exports finalized/paid invoices with a Medicaid ID on file, for the selected trip-date
        range. This is a general reimbursement export, not a certified ND DHS claim form.
      </p>

      <form className="auth-form">
        <label htmlFor="date_from">From</label>
        <input
          id="date_from"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          required
        />

        <label htmlFor="date_to">To</label>
        <input
          id="date_to"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          required
        />

        {error && <p className="form-error">{error}</p>}

        <div className="export-actions">
          <button
            onClick={(e) => handleDownload(e, "csv")}
            disabled={isDownloading || !dateFrom || !dateTo}
          >
            {isDownloading ? "Preparing..." : "Download CSV"}
          </button>
          <button
            onClick={(e) => handleDownload(e, "pdf")}
            disabled={isDownloading || !dateFrom || !dateTo}
          >
            {isDownloading ? "Preparing..." : "Download PDF"}
          </button>
        </div>
      </form>
    </div>
  );
}
