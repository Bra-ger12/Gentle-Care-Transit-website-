import { useState } from "react";
import { Link } from "react-router-dom";
import { useDriversQuery } from "../drivers/useDrivers";
import { TripStatusBadge } from "../trips/TripStatusBadge";
import { useAssignTripMutation, useAutoAssignTripMutation, useTripsQuery } from "../trips/useTrips";

const POLL_INTERVAL_MS = 15000;

export function DispatchBoard() {
  const needsAssignment = useTripsQuery(1, "CONFIRMED", {
    refetchInterval: POLL_INTERVAL_MS,
  });
  const inFlight = useTripsQuery(1, "ASSIGNED,EN_ROUTE,PICKED_UP", {
    refetchInterval: POLL_INTERVAL_MS,
  });
  const { data: driversData } = useDriversQuery(true);
  const assignTrip = useAssignTripMutation();
  const autoAssignTrip = useAutoAssignTripMutation();
  const [selectedDriver, setSelectedDriver] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const drivers = driversData?.results ?? [];

  async function handleAssign(tripId: string) {
    const driverId = selectedDriver[tripId];
    if (!driverId) {
      setError("Select a driver first.");
      return;
    }
    setError(null);
    try {
      await assignTrip.mutateAsync({ id: tripId, driverId });
    } catch {
      setError("Could not assign that driver (unapproved, incompatible, or already booked).");
    }
  }

  async function handleAutoAssign(tripId: string) {
    setError(null);
    try {
      await autoAssignTrip.mutateAsync(tripId);
    } catch {
      setError("No available driver found for that trip.");
    }
  }

  return (
    <div className="portal-page">
      <h1>Dispatch board</h1>
      <p>
        <Link to="/admin/drivers">Manage driver approvals</Link> &middot;{" "}
        <Link to="/admin/billing/invoices">Invoices</Link> &middot;{" "}
        <Link to="/admin/reports">Reports</Link>
      </p>

      {error && <p className="form-error">{error}</p>}

      <h2>Needs assignment</h2>
      {needsAssignment.isLoading && <p>Loading...</p>}
      {(needsAssignment.data?.results.length ?? 0) === 0 && !needsAssignment.isLoading && (
        <p>No confirmed trips awaiting assignment.</p>
      )}
      <table className="dispatch-table">
        <tbody>
          {needsAssignment.data?.results.map((trip) => (
            <tr key={trip.id} className="dispatch-table__row">
              <td>{new Date(trip.scheduled_pickup_time).toLocaleString()}</td>
              <td>
                {trip.pickup_address} &rarr; {trip.dropoff_address}
              </td>
              <td>
                <select
                  value={selectedDriver[trip.id] ?? ""}
                  onChange={(e) =>
                    setSelectedDriver((prev) => ({ ...prev, [trip.id]: e.target.value }))
                  }
                >
                  <option value="">Select driver...</option>
                  {drivers.map((driver) => (
                    <option key={driver.id} value={driver.id}>
                      {driver.first_name} {driver.last_name}
                    </option>
                  ))}
                </select>
              </td>
              <td className="dispatch-table__actions">
                <button onClick={() => handleAssign(trip.id)}>Assign</button>
                <button onClick={() => handleAutoAssign(trip.id)}>Auto-assign</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>In flight</h2>
      {(inFlight.data?.results.length ?? 0) === 0 && !inFlight.isLoading && (
        <p>No trips currently assigned or in progress.</p>
      )}
      <table className="dispatch-table">
        <tbody>
          {inFlight.data?.results.map((trip) => (
            <tr key={trip.id} className="dispatch-table__row">
              <td>{new Date(trip.scheduled_pickup_time).toLocaleString()}</td>
              <td>
                {trip.pickup_address} &rarr; {trip.dropoff_address}
              </td>
              <td>{trip.assigned_driver_name ?? "—"}</td>
              <td>
                <TripStatusBadge status={trip.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
