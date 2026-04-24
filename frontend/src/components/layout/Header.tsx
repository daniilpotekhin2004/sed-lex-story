import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { ThemeToggle } from "./ThemeToggle";
import { useRole } from "../../auth/useRole";

export const Header: React.FC = () => {
  const { user, logout } = useAuth();
  const { isAdmin, isAuthor } = useRole();
  const authorView = isAdmin || isAuthor;

  return (
    <header className="topbar">
      <nav className="nav" aria-label="Основная навигация">
        {authorView && (
          <>
            <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
              Генерация
            </NavLink>
            <NavLink to="/projects" className={({ isActive }) => (isActive ? "active" : "")}>
              Проекты
            </NavLink>
            <NavLink to="/studio" className={({ isActive }) => (isActive ? "active" : "")}>
              Студия
            </NavLink>
          </>
        )}
        <NavLink to="/player" className={({ isActive }) => (isActive ? "active" : "")}>
          Плеер
        </NavLink>
        <NavLink to="/my-stats" className={({ isActive }) => (isActive ? "active" : "")}>
          Статистика
        </NavLink>
      </nav>
      <div className="topbar-right">
        <ThemeToggle />
        {user && (
          <button className="secondary topbar-logout" onClick={logout}>
            Выйти
          </button>
        )}
      </div>
    </header>
  );
};
