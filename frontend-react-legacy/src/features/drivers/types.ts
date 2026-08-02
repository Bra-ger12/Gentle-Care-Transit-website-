export type BackgroundCheckStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface DriverListItem {
  id: string;
  user: string;
  email: string;
  first_name: string;
  last_name: string;
  license_number: string;
  license_expiry_date: string | null;
  license_expiring_soon: boolean;
  license_expired: boolean;
  vehicle_type: string;
  vehicle_plate: string;
  vehicle_capacity: number | null;
  insurance_document: string | null;
  background_check_status: BackgroundCheckStatus;
  is_approved: boolean;
  approved_at: string | null;
  approved_by: string | null;
  rejection_reason: string;
  created_at: string;
  updated_at: string;
}
