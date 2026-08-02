import { TRIP_STATUS_LABELS } from "./constants";
import type { TripStatus } from "./types";

export function TripStatusBadge({ status }: { status: TripStatus }) {
  return (
    <span className={`trip-status trip-status--${status.toLowerCase()}`}>
      {TRIP_STATUS_LABELS[status]}
    </span>
  );
}
