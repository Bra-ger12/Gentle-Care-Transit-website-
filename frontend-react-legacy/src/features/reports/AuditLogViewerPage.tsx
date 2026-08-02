import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuditLogsQuery } from "./useReports";

const ACTIONS = ["VIEW", "CREATE", "UPDATE", "DELETE", "EXPORT"];

export function AuditLogViewerPage() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [modelName, setModelName] = useState("");

  const { data, isLoading, isError } = useAuditLogsQuery({
    page,
    action: action || undefined,
    model_name: modelName || undefined,
  });

  if (isError) {
    return <div className="page-status">Could not load the audit log.</div>;
  }

  const logs = data?.results ?? [];

  return (
    <div className="portal-page">
      <h1>Audit log</h1>
      <p>
        <Link to="/admin/reports">KPI dashboard</Link>
      </p>

      <div className="date-range-form">
        <label htmlFor="action">
          Action
          <select
            id="action"
            value={action}
            onChange={(e) => {
              setPage(1);
              setAction(e.target.value);
            }}
          >
            <option value="">All</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="model_name">
          Model
          <input
            id="model_name"
            value={modelName}
            onChange={(e) => {
              setPage(1);
              setModelName(e.target.value);
            }}
            placeholder="e.g. Invoice"
          />
        </label>
      </div>

      {isLoading && <p>Loading...</p>}
      {!isLoading && logs.length === 0 && <p>No matching audit log entries.</p>}

      <table className="dispatch-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Model</th>
            <th>Object ID</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((entry) => (
            <tr key={entry.id} className="dispatch-table__row">
              <td>{new Date(entry.timestamp).toLocaleString()}</td>
              <td>{entry.actor_email ?? "—"}</td>
              <td>{entry.action}</td>
              <td>{entry.model_name}</td>
              <td>{entry.object_id}</td>
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
