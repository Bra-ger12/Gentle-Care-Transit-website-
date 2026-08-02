import { useState } from "react";
import { useParams } from "react-router-dom";
import { TripCompletionForm } from "../trips/TripCompletionForm";
import { TripStatusBadge } from "../trips/TripStatusBadge";
import {
  useAcceptTripMutation,
  useDeclineTripMutation,
  useMarkEnRouteMutation,
  useMarkPickedUpMutation,
  useReportNoShowMutation,
  useTripQuery,
} from "../trips/useTrips";

export function DriverTripDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: trip, isLoading, isError, refetch } = useTripQuery(id ?? "");
  const acceptTrip = useAcceptTripMutation();
  const declineTrip = useDeclineTripMutation();
  const markEnRoute = useMarkEnRouteMutation();
  const markPickedUp = useMarkPickedUpMutation();
  const reportNoShow = useReportNoShowMutation();
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return <div className="page-status">Loading trip...</div>;
  }
  if (isError || !trip) {
    return <div className="page-status">Trip not found.</div>;
  }

  async function runAction(action: () => Promise<unknown>, failureMessage: string) {
    setError(null);
    try {
      await action();
    } catch {
      setError(failureMessage);
    }
  }

  return (
    <div className="portal-page">
      <h1>Trip details</h1>
      <div className="trip-detail">
        <TripStatusBadge status={trip.status} />
        <p>{new Date(trip.scheduled_pickup_time).toLocaleString()}</p>
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
      </div>

      {error && <p className="form-error">{error}</p>}

      {trip.status === "ASSIGNED" && !trip.accepted_at && (
        <>
          <button
            onClick={() =>
              runAction(() => acceptTrip.mutateAsync(trip.id), "Could not accept this trip.")
            }
            disabled={acceptTrip.isPending}
          >
            Accept
          </button>
          <button
            onClick={() =>
              runAction(
                () => declineTrip.mutateAsync({ id: trip.id }),
                "Could not decline this trip.",
              )
            }
            disabled={declineTrip.isPending}
          >
            Decline
          </button>
        </>
      )}

      {trip.status === "ASSIGNED" && trip.accepted_at && (
        <button
          onClick={() =>
            runAction(() => markEnRoute.mutateAsync(trip.id), "Could not start this trip.")
          }
          disabled={markEnRoute.isPending}
        >
          Start (mark en route)
        </button>
      )}

      {trip.status === "EN_ROUTE" && (
        <>
          <button
            onClick={() =>
              runAction(() => markPickedUp.mutateAsync(trip.id), "Could not mark picked up.")
            }
            disabled={markPickedUp.isPending}
          >
            Mark picked up
          </button>
          <button
            onClick={() =>
              runAction(
                () => reportNoShow.mutateAsync({ id: trip.id }),
                "Could not report a no-show.",
              )
            }
            disabled={reportNoShow.isPending}
          >
            Report no-show
          </button>
        </>
      )}

      {trip.status === "PICKED_UP" && (
        <TripCompletionForm tripId={trip.id} onCompleted={() => refetch()} />
      )}
    </div>
  );
}
