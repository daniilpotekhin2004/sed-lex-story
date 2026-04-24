import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { login, getMe, registerPlayer } from "../api/auth";
import { useAuth } from "../auth/useAuth";
import { persistAuthSession } from "../auth/sessionStore";

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login: loginCtx } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const performLogin = async (usernameValue: string, passwordValue: string) => {
    const { access_token, refresh_token } = await login({ username: usernameValue, password: passwordValue });
    await persistAuthSession({
      accessToken: access_token,
      refreshToken: refresh_token,
    });
    const profile = await getMe();
    loginCtx(
      {
        accessToken: access_token,
        refreshToken: refresh_token,
      },
      profile,
    );
    const isPlayer =
      profile.role?.toLowerCase() === "player" ||
      (profile.roles ?? []).some((r) => r.toLowerCase() === "player");
    const fallback =
      !((location.state as { from?: Location })?.from?.pathname) && isPlayer
        ? "/player"
        : "/";
    const redirectTo = (location.state as { from?: Location })?.from?.pathname ?? fallback;
    navigate(redirectTo, { replace: true });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await registerPlayer({
          username,
          email,
          password,
          full_name: fullName || null,
        });
      }
      await performLogin(username, password);
    } catch (err) {
      setError((err as Error).message || "Не удалось выполнить операцию");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <div className="flex justify-between items-center">
          <h1 className="mb-2">{mode === "login" ? "Вход" : "Регистрация игрока"}</h1>
          <div className="flex gap-2">
            <button
              type="button"
              className={`ghost ${mode === "login" ? "primary" : ""}`}
              onClick={() => setMode("login")}
              disabled={loading}
            >
              Войти
            </button>
            <button
              type="button"
              className={`ghost ${mode === "register" ? "primary" : ""}`}
              onClick={() => setMode("register")}
              disabled={loading}
            >
              Новый игрок
            </button>
          </div>
        </div>
        {mode === "register" && (
          <p className="muted">
            Создайте аккаунт игрока. Роль <code>player</code> назначается автоматически.
          </p>
        )}
        <label>
          <span>Имя пользователя</span>
          <input
            className="input"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
          />
        </label>
        {mode === "register" && (
          <>
            <label>
              <span>Эл. почта</span>
              <input
                className="input"
                type="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
              />
            </label>
            <label>
              <span>Полное имя (необязательно)</span>
              <input
                className="input"
                name="fullName"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={loading}
              />
            </label>
          </>
        )}
        <label>
          <span>Пароль</span>
          <input
            className="input"
            type="password"
            name="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button
          className="primary"
          type="submit"
          disabled={
            loading ||
            !username ||
            !password ||
            (mode === "register" && !email)
          }
        >
          {loading ? (mode === "login" ? "Входим..." : "Создаём...") : mode === "login" ? "Войти" : "Создать и войти"}
        </button>
      </form>
    </div>
  );
};
