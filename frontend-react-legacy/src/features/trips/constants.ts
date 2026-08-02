import type { TripStatus } from "./types";

export const MOBILITY_NEEDS = [
  { value: "AMBULATORY", label: "Ambulatory" },
  { value: "WHEELCHAIR", label: "Wheelchair" },
  { value: "STRETCHER", label: "Stretcher" },
  { value: "WALKER", label: "Walker" },
  { value: "OXYGEN", label: "Oxygen support" },
];

export const WEEKDAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

export const TRIP_STATUS_LABELS: Record<TripStatus, string> = {
  REQUESTED: "Requested",
  CONFIRMED: "Confirmed",
  ASSIGNED: "Assigned",
  EN_ROUTE: "En route",
  PICKED_UP: "Picked up",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  NO_SHOW: "No-show",
};

// A trip can only ever be cancelled from these statuses; the server is the
// source of truth on the 24h cutoff -- this is a client-side hint only.
export const CANCELLABLE_STATUSES: TripStatus[] = [
  "REQUESTED",
  "CONFIRMED",
  "ASSIGNED",
  "EN_ROUTE",
  "PICKED_UP",
];
