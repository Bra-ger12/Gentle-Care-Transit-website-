import { apiClient } from "../../lib/apiClient";
import type { Paginated } from "../trips/types";
import type { DriverListItem } from "./types";

export async function listDrivers(
  isApproved?: boolean,
): Promise<Paginated<DriverListItem>> {
  const response = await apiClient.get<Paginated<DriverListItem>>("/auth/drivers/", {
    params: { is_approved: isApproved },
  });
  return response.data;
}

export async function approveDriver(id: string): Promise<DriverListItem> {
  const response = await apiClient.post<DriverListItem>(`/auth/drivers/${id}/approve/`);
  return response.data;
}

export async function rejectDriver(id: string, reason?: string): Promise<DriverListItem> {
  const response = await apiClient.post<DriverListItem>(`/auth/drivers/${id}/reject/`, {
    reason,
  });
  return response.data;
}
