import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptTrip,
  assignTrip,
  autoAssignTrip,
  cancelTrip,
  completeTrip,
  createRecurringSeries,
  createTrip,
  declineTrip,
  getTrip,
  listTrips,
  markEnRoute,
  markPickedUp,
  reportNoShow,
} from "./api";
import type {
  CompleteTripPayload,
  CreateRecurringSeriesPayload,
  CreateTripPayload,
} from "./types";

export function useTripsQuery(
  page = 1,
  status?: string,
  options?: { refetchInterval?: number },
) {
  return useQuery({
    queryKey: ["trips", page, status],
    queryFn: () => listTrips(page, status),
    refetchInterval: options?.refetchInterval,
  });
}

export function useTripQuery(id: string) {
  return useQuery({
    queryKey: ["trips", id],
    queryFn: () => getTrip(id),
    enabled: !!id,
  });
}

export function useCreateTripMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateTripPayload) => createTrip(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trips"] });
    },
  });
}

export function useCancelTripMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      cancelTrip(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trips"] });
    },
  });
}

export function useCreateRecurringSeriesMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateRecurringSeriesPayload) =>
      createRecurringSeries(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trips"] });
    },
  });
}

function useTripActionMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trips"] });
    },
  });
}

export function useAssignTripMutation() {
  return useTripActionMutation(({ id, driverId }: { id: string; driverId: string }) =>
    assignTrip(id, driverId),
  );
}

export function useAutoAssignTripMutation() {
  return useTripActionMutation((id: string) => autoAssignTrip(id));
}

export function useAcceptTripMutation() {
  return useTripActionMutation((id: string) => acceptTrip(id));
}

export function useDeclineTripMutation() {
  return useTripActionMutation(({ id, reason }: { id: string; reason?: string }) =>
    declineTrip(id, reason),
  );
}

export function useMarkEnRouteMutation() {
  return useTripActionMutation((id: string) => markEnRoute(id));
}

export function useMarkPickedUpMutation() {
  return useTripActionMutation((id: string) => markPickedUp(id));
}

export function useCompleteTripMutation() {
  return useTripActionMutation(
    ({ id, payload }: { id: string; payload: CompleteTripPayload }) =>
      completeTrip(id, payload),
  );
}

export function useReportNoShowMutation() {
  return useTripActionMutation(({ id, reason }: { id: string; reason?: string }) =>
    reportNoShow(id, reason),
  );
}
