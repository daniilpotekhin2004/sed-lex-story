import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useRole } from "../../auth/useRole";

type AllowedRole = "admin" | "author" | "player";

type Props = {
  allowedRoles: AllowedRole[];
  redirectTo?: string;
  fallback?: React.ReactNode;
  children: React.ReactNode;
};

export const RoleGuard: React.FC<Props> = ({ allowedRoles, redirectTo = "/player", fallback = null, children }) => {
  const { roles } = useRole();
  const location = useLocation();

  const allowed = roles.some((r) => allowedRoles.includes(r as AllowedRole));
  if (!allowed) {
    if (redirectTo) {
      return <Navigate to={redirectTo} replace state={{ from: location }} />;
    }
    return <>{fallback}</>;
  }

  return <>{children}</>;
};
