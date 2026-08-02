import { Route, Routes } from "react-router-dom";
import { DriverTripDetailPage } from "../features/driver/DriverTripDetailPage";
import { DriverTripsPage } from "../features/driver/DriverTripsPage";

export function DriverRoutes() {
  return (
    <Routes>
      <Route index element={<DriverTripsPage />} />
      <Route path="trips/:id" element={<DriverTripDetailPage />} />
    </Routes>
  );
}
