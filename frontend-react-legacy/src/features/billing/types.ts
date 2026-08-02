export type InvoiceStatus = "DRAFT" | "FINALIZED" | "PAID" | "VOID";
export type PayerType = "MEDICAID" | "PRIVATE_PAY";

export interface RateSchedule {
  id: string;
  mobility_need: string;
  base_fare: string;
  per_mile_rate: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RateSchedulePayload {
  mobility_need: string;
  base_fare: string;
  per_mile_rate: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

export interface InvoiceListItem {
  id: string;
  invoice_number: string;
  trip: string;
  rider: string;
  status: InvoiceStatus;
  rider_name_snapshot: string;
  total_amount: string;
  created_at: string;
  finalized_at: string | null;
  paid_at: string | null;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  trip: string;
  rider: string;
  rate_schedule: string;
  status: InvoiceStatus;
  rider_name_snapshot: string;
  medicaid_id_snapshot: string | null;
  mobility_need_snapshot: string;
  mileage_snapshot: string;
  base_fare: string;
  per_mile_rate: string;
  mileage_amount: string;
  total_amount: string;
  payer_type: PayerType;
  generated_by: string | null;
  finalized_at: string | null;
  finalized_by: string | null;
  paid_at: string | null;
  paid_by: string | null;
  payment_reference: string;
  voided_at: string | null;
  voided_by: string | null;
  void_reason: string;
  created_at: string;
  updated_at: string;
}
