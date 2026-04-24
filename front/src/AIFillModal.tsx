import { useAuth } from "./useAuth";

export function useRole() {
  const { user } = useAuth();
  const rawRoles = user?.roles?.length
    ? user.roles
    : user?.role
      ? [user.role]
      : [];
  const roles = rawRoles.map((r) => r.toLowerCase());
  const isAdmin = roles.includes("admin");
  const isAuthor = roles.includes("author");
  const isPlayer = roles.includes("player");
  const primaryRole = roles[0] ?? "guest";

  return { roles, isAdmin, isAuthor, isPlayer, primaryRole };
}
