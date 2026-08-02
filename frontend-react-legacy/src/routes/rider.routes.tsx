import { Route, Routes } from "react-router-dom";
import { InvoiceDetailPage } from "../features/billing/InvoiceDetailPage";
import { InvoiceListPage } from "../features/billing/InvoiceListPage";
import { BookingForm } from "../features/trips/BookingForm";
import { TripDetailPage } from "../features/trips/TripDetailPage";
import { TripListPage } from "../features/trips/TripListPage";

export function RiderRoutes() {
  return (
    <Routes>
      <Route index element={<TripListPage />} />
      <Route path="book" element={<BookingForm />} />
      <Route path="trips/:id" element={<TripDetailPage />} />
      <Route path="billing/invoices" element={<InvoiceListPage />} />
      <Route path="billing/invoices/:id" element={<InvoiceDetailPage />} />
    </Routes>
  );
}
