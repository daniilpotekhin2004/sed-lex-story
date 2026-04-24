import { render, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider, useTheme } from "../theme/ThemeProvider";

function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button onClick={toggleTheme} data-theme={theme}>
      Toggle
    </button>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("toggles theme and persists selection", () => {
    render(
      <ThemeProvider>
        <ThemeToggleButton />
      </ThemeProvider>
    );

    const btn = screen.getByRole("button", { name: /toggle/i });
    expect(btn).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem("lexquest_theme")).toBe("dark");

    fireEvent.click(btn);
    expect(btn).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem("lexquest_theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
