import { useState } from "react";
import { useParams } from "react-router-dom";
import { CANCELLABLE_STATUSES } from "./constants";
import { TripStatusBadge } from "./TripStatusBadge";
import { useCancelTripMutation, useTripQuery } from "./useTrips";

const CUTOFF_HOURS = 24;

export function TripDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: trip, isLoading, isError } = useTripQuery(id ?? "");
  const cancelTrip = useCancelTripMutation();
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return <div className="page-status">Loading trip...</div>;
  }
  if (isError || !trip) {
    return <div className="page-status">Trip not found.</div>;
  }

  const pickupTime = new Date(trip.scheduled_pickup_time);
  const cutoff = new Date(pickupTime.getTime() - CUTOFF_HOURS * 60 * 60 * 1000);
  const isCancellableStatus = CANCELLABLE_STATUSES.includes(trip.status);
  const canCancel = isCancellableStatus && new Date() < cutoff;

  async function handleCancel() {
    setError(null);
    try {
      await cancelTrip.mutateAsync({ id: trip!.id });
    } catch {
      setError("Could not cancel this trip.");
    }
  }

  return (
    <div className="portal-page">
      <h1>Trip details</h1>
      <div className="trip-detail">
        <TripStatusBadge status={trip.status} />
        <p>{pickupTime.toLocaleString()}</p>
        <p>
          <strong>Pickup:</strong> {trip.pickup_address}
        </p>
        <p>
          <strong>Dropoff:</strong> {trip.dropoff_address}
        </p>
        <p>
          <strong>Mileage:</strong> {trip.mileage} mi
        </p>
        {trip.notes && (
          <p>
            <strong>Notes:</strong> {trip.notes}
          </p>
        )}
        {trip.cancellation_reason && (
          <p>
            <strong>Cancellation reason:</strong> {trip.cancellation_reason}
          </p>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      {canCancel && (
        <button onClick={handleCancel} disabled={cancelTrip.isPending}>
          {cancelTrip.isPending ? "Cancelling..." : "Cancel trip"}
        </button>
      )}
      {!canCancel && isCancellableStatus && (
        <p className="page-status-note">
          This trip can no longer be self-cancelled (within {CUTOFF_HOURS} hours of
          pickup).
        </p>
      )}
    </div>
  );
}
