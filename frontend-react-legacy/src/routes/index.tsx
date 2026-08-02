import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuth, type Role } from "../features/auth/AuthContext";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { AdminRoutes } from "./admin.routes";
import { DriverRoutes } from "./driver.routes";
import { RiderRoutes } from "./rider.routes";

const ROLE_HOME: Record<Role, string> = {
  RIDER: "/rider",
  DRIVER: "/driver",
  ADMIN: "/admin",
};

function ForbiddenPage() {
  return (
    <div className="page-status">
      <h1>403</h1>
      <p>You don&apos;t have access to this page.</p>
    </div>
  );
}

function HomeRedirect() {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <div className="page-status">Loading...</div>;
  }
  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }
  return <Navigate to={ROLE_HOME[user.role]} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forbidden" element={<ForbiddenPage />} />

      <Route element={<ProtectedRoute allowedRoles={["RIDER"]} />}>
        <Route path="/rider/*" element={<RiderRoutes />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["DRIVER"]} />}>
        <Route path="/driver/*" element={<DriverRoutes />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["ADMIN"]} />}>
        <Route path="/admin/*" element={<AdminRoutes />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
