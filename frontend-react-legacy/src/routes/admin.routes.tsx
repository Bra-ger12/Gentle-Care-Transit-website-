import { Route, Routes } from "react-router-dom";
import { InvoiceDetailPage } from "../features/billing/InvoiceDetailPage";
import { InvoiceListPage } from "../features/billing/InvoiceListPage";
import { MedicaidExportPage } from "../features/billing/MedicaidExportPage";
import { RateScheduleListPage } from "../features/billing/RateScheduleListPage";
import { DispatchBoard } from "../features/dispatch/DispatchBoard";
import { DriverApprovalPage } from "../features/drivers/DriverApprovalPage";
import { AuditLogViewerPage } from "../features/reports/AuditLogViewerPage";
import { KpiDashboardPage } from "../features/reports/KpiDashboardPage";

export function AdminRoutes() {
  return (
    <Routes>
      <Route index element={<DispatchBoard />} />
      <Route path="drivers" element={<DriverApprovalPage />} />
      <Route path="billing/rate-schedules" element={<RateScheduleListPage />} />
      <Route path="billing/invoices" element={<InvoiceListPage />} />
      <Route path="billing/invoices/:id" element={<InvoiceDetailPage />} />
      <Route path="billing/medicaid-export" element={<MedicaidExportPage />} />
      <Route path="reports" element={<KpiDashboardPage />} />
      <Route path="reports/audit-log" element={<AuditLogViewerPage />} />
    </Routes>
  );
}
