import { Link } from "react-router-dom";
import { TripStatusBadge } from "../trips/TripStatusBadge";
import { useTripsQuery } from "../trips/useTrips";

export function DriverTripsPage() {
  const { data, isLoading, isError } = useTripsQuery();

  if (isLoading) {
    return <div className="page-status">Loading your manifest...</div>;
  }
  if (isError) {
    return <div className="page-status">Could not load your trips.</div>;
  }

  const trips = data?.results ?? [];

  return (
    <div className="portal-page">
      <h1>Your trips</h1>

      {trips.length === 0 && <p>No trips assigned yet.</p>}

      <ul className="trip-timeline">
        {trips.map((trip) => (
          <li key={trip.id} className="trip-timeline__item">
            <Link to={`/driver/trips/${trip.id}`} className="trip-timeline__link">
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
    </div>
  );
}
