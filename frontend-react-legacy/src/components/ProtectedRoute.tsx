import { Navigate, Outlet } from "react-router-dom";
import { useAuth, type Role } from "../features/auth/AuthContext";

export function ProtectedRoute({ allowedRoles }: { allowedRoles: Role[] }) {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <div className="page-status">Loading session...</div>;
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(user.role)) {
    return <Navigate to="/forbidden" replace />;
  }

  return <Outlet />;
}
