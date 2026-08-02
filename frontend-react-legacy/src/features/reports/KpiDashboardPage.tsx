import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useKpiSummaryQuery, useRevenueByMonthQuery } from "./useReports";

function monthLabel(month: string) {
  return new Date(`${month}T00:00:00`).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
  });
}

export function KpiDashboardPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [showTable, setShowTable] = useState(false);

  const summary = useKpiSummaryQuery(dateFrom || undefined, dateTo || undefined);
  const revenueByMonth = useRevenueByMonthQuery(dateFrom || undefined, dateTo || undefined);

  const chartData = (revenueByMonth.data ?? []).map((row) => ({
    month: monthLabel(row.month),
    total: Number(row.total),
  }));

  return (
    <div className="portal-page">
      <h1>KPI dashboard</h1>
      <p>
        <Link to="/admin/reports/audit-log">Audit log</Link>
      </p>

      <form className="date-range-form">
        <label htmlFor="date_from">
          From
          <input
            id="date_from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </label>
        <label htmlFor="date_to">
          To
          <input
            id="date_to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </label>
      </form>
      <p className="page-status-note">
        Defaults to the trailing 30 days when no range is set.
      </p>

      {summary.isLoading && <p>Loading KPIs...</p>}
      {summary.isError && <p className="form-error">Could not load KPIs.</p>}

      {summary.data && (
        <div className="kpi-grid">
          <div className="kpi-tile">
            <div className="kpi-tile__label">Trips</div>
            <div className="kpi-tile__value">{summary.data.trip_volume.total}</div>
          </div>
          <div className="kpi-tile">
            <div className="kpi-tile__label">Cancellation rate</div>
            <div className="kpi-tile__value">
              {(summary.data.cancellation_no_show.cancellation_rate * 100).toFixed(1)}%
            </div>
          </div>
          <div className="kpi-tile">
            <div className="kpi-tile__label">No-show rate</div>
            <div className="kpi-tile__value">
              {(summary.data.cancellation_no_show.no_show_rate * 100).toFixed(1)}%
            </div>
          </div>
          <div className="kpi-tile">
            <div className="kpi-tile__label">Avg cycle time</div>
            <div className="kpi-tile__value">
              {summary.data.cycle_time.avg_cycle_minutes !== null
                ? `${summary.data.cycle_time.avg_cycle_minutes} min`
                : "—"}
            </div>
          </div>
          <div className="kpi-tile">
            <div className="kpi-tile__label">Billed</div>
            <div className="kpi-tile__value">${summary.data.revenue.billed_total}</div>
          </div>
          <div className="kpi-tile">
            <div className="kpi-tile__label">Outstanding</div>
            <div className="kpi-tile__value">${summary.data.revenue.outstanding_total}</div>
          </div>
          <div className="kpi-tile">
            <div className="kpi-tile__label">Paid</div>
            <div className="kpi-tile__value">${summary.data.revenue.paid_total}</div>
          </div>
        </div>
      )}

      <h2>Revenue by month</h2>
      {chartData.length === 0 && !revenueByMonth.isLoading && <p>No billed revenue in range.</p>}
      {chartData.length > 0 && (
        <>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="month" stroke="var(--text-muted)" fontSize={12} />
              <YAxis stroke="var(--text-muted)" fontSize={12} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                formatter={(value) => [`$${Number(value).toFixed(2)}`, "Revenue"]}
                contentStyle={{ background: "var(--bg)", border: "1px solid var(--border)" }}
                labelStyle={{ color: "var(--text)" }}
              />
              <Bar dataKey="total" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <button onClick={() => setShowTable((v) => !v)}>
            {showTable ? "Hide" : "Show"} as table
          </button>
          {showTable && (
            <table className="dispatch-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Revenue</th>
                </tr>
              </thead>
              <tbody>
                {chartData.map((row) => (
                  <tr key={row.month} className="dispatch-table__row">
                    <td>{row.month}</td>
                    <td>${row.total.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
