export const MOBILITY_NEEDS = [
  { value: "AMBULATORY", label: "Ambulatory" },
  { value: "WHEELCHAIR", label: "Wheelchair" },
  { value: "STRETCHER", label: "Stretcher" },
  { value: "WALKER", label: "Walker" },
  { value: "OXYGEN", label: "Oxygen" },
];

export const MOBILITY_LABELS = Object.fromEntries(MOBILITY_NEEDS.map((m) => [m.value, m.label]));

export const WEEKDAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

export const TRIP_STATUS_LABELS = {
  REQUESTED: "Requested",
  CONFIRMED: "Confirmed",
  ASSIGNED: "Assigned",
  EN_ROUTE: "En route",
  ARRIVED: "At pickup",
  PICKED_UP: "Picked up",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  NO_SHOW: "No-show",
};

export const INVOICE_STATUS_LABELS = {
  DRAFT: "Draft",
  FINALIZED: "Finalized",
  PAID: "Paid",
  VOID: "Void",
};

export function formatDateTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

export function formatCurrency(value) {
  if (value === null || value === undefined || value === "") return "—";
  return `$${Number(value).toFixed(2)}`;
}

export function formatMonthLabel(value) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}
