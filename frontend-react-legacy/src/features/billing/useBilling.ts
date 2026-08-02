import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createRateSchedule,
  finalizeInvoice,
  generateInvoices,
  getInvoice,
  listInvoices,
  listRateSchedules,
  markInvoicePaid,
  updateRateSchedule,
  voidInvoice,
} from "./api";
import type { RateSchedulePayload } from "./types";

export function useRateSchedulesQuery() {
  return useQuery({
    queryKey: ["rate-schedules"],
    queryFn: listRateSchedules,
  });
}

export function useCreateRateScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RateSchedulePayload) => createRateSchedule(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rate-schedules"] });
    },
  });
}

export function useUpdateRateScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<RateSchedulePayload> }) =>
      updateRateSchedule(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rate-schedules"] });
    },
  });
}

export function useInvoicesQuery(page = 1) {
  return useQuery({
    queryKey: ["invoices", page],
    queryFn: () => listInvoices(page),
  });
}

export function useInvoiceQuery(id: string) {
  return useQuery({
    queryKey: ["invoices", id],
    queryFn: () => getInvoice(id),
    enabled: !!id,
  });
}

function useInvoiceActionMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
  });
}

export function useGenerateInvoicesMutation() {
  return useInvoiceActionMutation((tripId: string | undefined) => generateInvoices(tripId));
}

export function useFinalizeInvoiceMutation() {
  return useInvoiceActionMutation((id: string) => finalizeInvoice(id));
}

export function useVoidInvoiceMutation() {
  return useInvoiceActionMutation(({ id, reason }: { id: string; reason: string }) =>
    voidInvoice(id, reason),
  );
}

export function useMarkInvoicePaidMutation() {
  return useInvoiceActionMutation(
    ({ id, paymentReference }: { id: string; paymentReference?: string }) =>
      markInvoicePaid(id, paymentReference),
  );
}
