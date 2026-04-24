import React from "react";
import { useTheme } from "../../theme/ThemeProvider";

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  return (
    <button className="ghost" onClick={toggleTheme} aria-label="Переключить тему">
      {theme === "dark" ? "🌙" : "🌞"}
    </button>
  );
};
