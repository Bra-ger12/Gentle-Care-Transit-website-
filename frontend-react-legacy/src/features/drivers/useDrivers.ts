import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { approveDriver, listDrivers, rejectDriver } from "./api";

export function useDriversQuery(isApproved?: boolean) {
  return useQuery({
    queryKey: ["drivers", isApproved],
    queryFn: () => listDrivers(isApproved),
  });
}

export function useApproveDriverMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => approveDriver(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drivers"] });
    },
  });
}

export function useRejectDriverMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      rejectDriver(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drivers"] });
    },
  });
}
