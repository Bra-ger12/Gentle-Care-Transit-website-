import { useState } from "react";
import {
  useApproveDriverMutation,
  useDriversQuery,
  useRejectDriverMutation,
} from "./useDrivers";

export function DriverApprovalPage() {
  const { data, isLoading, isError } = useDriversQuery();
  const approveDriver = useApproveDriverMutation();
  const rejectDriver = useRejectDriverMutation();
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return <div className="page-status">Loading drivers...</div>;
  }
  if (isError) {
    return <div className="page-status">Could not load drivers.</div>;
  }

  const drivers = data?.results ?? [];

  async function handleApprove(id: string) {
    setError(null);
    try {
      await approveDriver.mutateAsync(id);
    } catch {
      setError("Could not approve this driver.");
    }
  }

  async function handleReject(id: string) {
    setError(null);
    try {
      await rejectDriver.mutateAsync({ id });
    } catch {
      setError("Could not reject this driver.");
    }
  }

  return (
    <div className="portal-page">
      <h1>Driver approvals</h1>

      {error && <p className="form-error">{error}</p>}

      {drivers.length === 0 && <p>No drivers found.</p>}

      <ul className="driver-list">
        {drivers.map((driver) => (
          <li key={driver.id} className="driver-list__row">
            <div>
              <strong>
                {driver.first_name} {driver.last_name}
              </strong>{" "}
              &lt;{driver.email}&gt;
              <div>
                Vehicle: {driver.vehicle_type || "unspecified"} &middot; Background check:{" "}
                {driver.background_check_status}
                {driver.is_approved && " · Approved"}
              </div>
              {driver.license_expiry_date && (
                <span
                  className={
                    driver.license_expired
                      ? "license-badge license-badge--expired"
                      : driver.license_expiring_soon
                        ? "license-badge license-badge--expiring"
                        : "license-badge"
                  }
                >
                  License {driver.license_expired ? "expired" : "expires"}{" "}
                  {driver.license_expiry_date}
                </span>
              )}
            </div>
            <div>
              <button onClick={() => handleApprove(driver.id)} disabled={driver.is_approved}>
                Approve
              </button>
              <button onClick={() => handleReject(driver.id)}>Reject</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
