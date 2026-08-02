import { apiClient } from "../../lib/apiClient";
import type {
  CompleteTripPayload,
  CreateRecurringSeriesPayload,
  CreateTripPayload,
  Paginated,
  RecurringTripSeries,
  Trip,
  TripListItem,
} from "./types";

export async function listTrips(
  page = 1,
  status?: string,
): Promise<Paginated<TripListItem>> {
  const response = await apiClient.get<Paginated<TripListItem>>("/trips/", {
    params: { page, status },
  });
  return response.data;
}

export async function getTrip(id: string): Promise<Trip> {
  const response = await apiClient.get<Trip>(`/trips/${id}/`);
  return response.data;
}

export async function createTrip(payload: CreateTripPayload): Promise<Trip> {
  const response = await apiClient.post<Trip>("/trips/", payload);
  return response.data;
}

export async function cancelTrip(id: string, reason?: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/cancel/`, {
    reason,
  });
  return response.data;
}

export async function createRecurringSeries(
  payload: CreateRecurringSeriesPayload,
): Promise<RecurringTripSeries> {
  const response = await apiClient.post<RecurringTripSeries>(
    "/trips/recurring-series/",
    payload,
  );
  return response.data;
}

export async function assignTrip(id: string, driverId: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/assign/`, {
    driver_id: driverId,
  });
  return response.data;
}

export async function autoAssignTrip(id: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/auto-assign/`);
  return response.data;
}

export async function acceptTrip(id: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/accept/`);
  return response.data;
}

export async function declineTrip(id: string, reason?: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/decline/`, {
    reason,
  });
  return response.data;
}

export async function markEnRoute(id: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/en-route/`);
  return response.data;
}

export async function markPickedUp(id: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/picked-up/`);
  return response.data;
}

export async function completeTrip(
  id: string,
  payload: CompleteTripPayload,
): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/complete/`, payload);
  return response.data;
}

export async function reportNoShow(id: string, reason?: string): Promise<Trip> {
  const response = await apiClient.post<Trip>(`/trips/${id}/no-show/`, {
    reason,
  });
  return response.data;
}
