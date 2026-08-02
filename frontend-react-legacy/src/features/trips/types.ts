export type TripStatus =
  | "REQUESTED"
  | "CONFIRMED"
  | "ASSIGNED"
  | "EN_ROUTE"
  | "PICKED_UP"
  | "COMPLETED"
  | "CANCELLED"
  | "NO_SHOW";

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface TripListItem {
  id: string;
  status: TripStatus;
  scheduled_pickup_time: string;
  pickup_address: string;
  dropoff_address: string;
  mileage: string;
  assigned_driver: string | null;
  assigned_driver_name: string | null;
}

export interface Trip {
  id: string;
  rider: string;
  created_by: string | null;
  recurring_series: string | null;
  status: TripStatus;
  scheduled_pickup_time: string;
  pickup_address: string;
  pickup_lat: string;
  pickup_lng: string;
  dropoff_address: string;
  dropoff_lat: string;
  dropoff_lng: string;
  mileage: string;
  estimated_duration_minutes: number | null;
  mobility_need: string;
  notes: string;
  cancelled_at: string | null;
  cancelled_by: string | null;
  cancellation_reason: string;
  assigned_driver: string | null;
  assigned_driver_name: string | null;
  assigned_at: string | null;
  assigned_by: string | null;
  accepted_at: string | null;
  decline_reason: string;
  en_route_at: string | null;
  picked_up_at: string | null;
  completed_at: string | null;
  no_show_at: string | null;
  no_show_reason: string;
  odometer_start: number | null;
  odometer_end: number | null;
  completion_attestation: string;
  created_at: string;
  updated_at: string;
}

export interface CompleteTripPayload {
  odometer_start: number;
  odometer_end: number;
  completion_attestation: string;
}

export interface CreateTripPayload {
  scheduled_pickup_time: string;
  pickup_address: string;
  dropoff_address: string;
  mobility_need: string;
  notes: string;
}

export interface RecurringTripSeries {
  id: string;
  rider: string;
  pickup_address: string;
  pickup_lat: string;
  pickup_lng: string;
  dropoff_address: string;
  dropoff_lat: string;
  dropoff_lng: string;
  mileage: string;
  pickup_time: string;
  weekdays: number[];
  start_date: string;
  end_date: string | null;
  mobility_need: string;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateRecurringSeriesPayload {
  pickup_address: string;
  dropoff_address: string;
  pickup_time: string;
  weekdays: number[];
  start_date: string;
  end_date: string | null;
  mobility_need: string;
  notes: string;
}
