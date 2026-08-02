import { useState } from "react";
import { Link } from "react-router-dom";
import { TripStatusBadge } from "./TripStatusBadge";
import { useTripsQuery } from "./useTrips";

export function TripListPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useTripsQuery(page);

  if (isLoading) {
    return <div className="page-status">Loading trips...</div>;
  }
  if (isError) {
    return <div className="page-status">Could not load trips.</div>;
  }

  const trips = data?.results ?? [];

  return (
    <div className="portal-page">
      <h1>Your trips</h1>
      <p>
        <Link to="/rider/book">Book a new trip</Link> &middot;{" "}
        <Link to="/rider/billing/invoices">Your invoices</Link>
      </p>

      {trips.length === 0 && <p>No trips yet.</p>}

      <ul className="trip-timeline">
        {trips.map((trip) => (
          <li key={trip.id} className="trip-timeline__item">
            <Link to={`/rider/trips/${trip.id}`} className="trip-timeline__link">
              <div className="trip-timeline__row">
                <span>{new Date(trip.scheduled_pickup_time).toLocaleString()}</span>
                <TripStatusBadge status={trip.status} />
              </div>
              <div className="trip-timeline__addresses">
                {trip.pickup_address} &rarr; {trip.dropoff_address}
              </div>
            </Link>
          </li>
        ))}
      </ul>

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
