import React, { useCallback, useEffect, useMemo, useState } from "react";
import { App as CapacitorApp } from "@capacitor/app";
import { AuthContext } from "./useAuth";
import type { User } from "../shared/types";
import { getMe, login as authLogin } from "../api/auth";
import { AUTH_EXPIRED_EVENT } from "../api/client";
import {
  clearAuthSession,
  getAccessTokenSnapshot,
  getAuthSession,
  persistAuthSession,
  subscribeToAuthSession,
  type AuthSessionTokens,
} from "./sessionStore";
import { isNativeShell } from "../utils/runtimePlatform";

type Props = {
  children: React.ReactNode;
};

export const AuthProvider: React.FC<Props> = ({ children }) => {
  const [token, setToken] = useState<string | null>(getAccessTokenSnapshot());
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [reauthOpen, setReauthOpen] = useState(false);
  const [reauthUsername, setReauthUsername] = useState("");
  const [reauthPassword, setReauthPassword] = useState("");
  const [reauthLoading, setReauthLoading] = useState(false);
  const [reauthError, setReauthError] = useState<string | null>(null);

  const loadUser = useCallback(async () => {
    const session = await getAuthSession();
    if (!session?.accessToken) {
      setIsLoading(false);
      return;
    }

    setToken(session.accessToken);
    try {
      const profile = await getMe();
      setUser(profile);
    } catch (err) {
      console.error("Failed to load user", err);
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401 || status === 403) {
        setReauthOpen(true);
      }
    } finally {
      setToken(getAccessTokenSnapshot());
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  useEffect(() => {
    if (!isNativeShell()) return;

    const listener = CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) {
        void loadUser();
      }
    });

    return () => {
      void listener.then((handle) => handle.remove());
    };
  }, [loadUser]);

  useEffect(() => {
    return subscribeToAuthSession((session) => {
      setToken(session?.accessToken ?? null);
      if (!session?.accessToken) {
        setUser(null);
      }
    });
  }, []);

  const login = useCallback((session: AuthSessionTokens, profile: User) => {
    setToken(session.accessToken);
    setUser(profile);
    setReauthOpen(false);
    setReauthError(null);
    void persistAuthSession(session).catch((error) => {
      console.error("Failed to persist auth session", error);
    });
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setReauthOpen(false);
    setReauthError(null);
    setReauthUsername("");
    setReauthPassword("");
    void clearAuthSession().catch((error) => {
      console.error("Failed to clear auth session", error);
    });
  }, []);

  const handleReauth = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!reauthUsername.trim() || !reauthPassword.trim()) {
        setReauthError("Введите логин и пароль.");
        return;
      }

      setReauthLoading(true);
      setReauthError(null);
      try {
        const { access_token, refresh_token } = await authLogin({
          username: reauthUsername.trim(),
          password: reauthPassword,
        });
        await persistAuthSession({
          accessToken: access_token,
          refreshToken: refresh_token,
        });
        const profile = await getMe();
        login(
          {
            accessToken: access_token,
            refreshToken: refresh_token,
          },
          profile,
        );
        setReauthPassword("");
      } catch (err) {
        const message = (err as { message?: string })?.message || "Не удалось авторизоваться.";
        setReauthError(message);
      } finally {
        setReauthLoading(false);
      }
    },
    [login, reauthPassword, reauthUsername],
  );

  useEffect(() => {
    const onAuthExpired = () => {
      setReauthUsername((current) => current || user?.username || "");
      setReauthOpen(true);
      setReauthError(null);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired as EventListener);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired as EventListener);
  }, [user?.username]);

  const value = useMemo(
    () => ({
      user,
      token,
      login,
      logout,
    }),
    [user, token, login, logout],
  );

  if (isLoading) {
    return <div className="page">Загрузка профиля...</div>;
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
      {reauthOpen && (
        <div className="auth-modal-backdrop">
          <form className="auth-modal-card" onSubmit={handleReauth}>
            <h2>Сессия истекла</h2>
            <p className="muted">Войдите снова, чтобы продолжить работу без перезагрузки страницы.</p>
            <label>
              Логин
              <input
                autoFocus
                value={reauthUsername}
                onChange={(event) => setReauthUsername(event.target.value)}
                autoComplete="username"
                placeholder="username"
              />
            </label>
            <label>
              Пароль
              <input
                type="password"
                value={reauthPassword}
                onChange={(event) => setReauthPassword(event.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </label>
            {reauthError && <div className="sequence-editor-error">{reauthError}</div>}
            <div className="auth-modal-actions">
              <button type="submit" className="primary" disabled={reauthLoading}>
                {reauthLoading ? "Входим..." : "Войти"}
              </button>
              <button type="button" className="ghost danger" onClick={logout} disabled={reauthLoading}>
                Выйти
              </button>
            </div>
          </form>
        </div>
      )}
    </AuthContext.Provider>
  );
};
