import { createContext, useContext } from "react";
import type { User } from "../shared/types";
import type { AuthSessionTokens } from "./sessionStore";

export type AuthContextValue = {
  user: User | null;
  token: string | null;
  login: (session: AuthSessionTokens, user: User) => void;
  logout: () => void;
};

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
