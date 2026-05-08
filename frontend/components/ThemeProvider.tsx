"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type UiTheme = "classic" | "modern";
export type ColorScheme = "dark" | "light";

const STORAGE_THEME = "novel-writer-ui-theme";
const STORAGE_SCHEME = "novel-writer-color-scheme";
const DEFAULT_THEME: UiTheme = "modern";
const DEFAULT_SCHEME: ColorScheme = "dark";

const Ctx = createContext<{
  theme: UiTheme;
  setTheme: (t: UiTheme) => void;
  colorScheme: ColorScheme;
  setColorScheme: (s: ColorScheme) => void;
  toggleColorScheme: () => void;
}>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
  colorScheme: DEFAULT_SCHEME,
  setColorScheme: () => {},
  toggleColorScheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<UiTheme>(DEFAULT_THEME);
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>(DEFAULT_SCHEME);

  useEffect(() => {
    try {
      const t = localStorage.getItem(STORAGE_THEME);
      if (t === "classic" || t === "modern") setThemeState(t);
      const s = localStorage.getItem(STORAGE_SCHEME);
      if (s === "dark" || s === "light") setColorSchemeState(s);
    } catch {}
  }, []);

  const setTheme = (t: UiTheme) => {
    setThemeState(t);
    try { localStorage.setItem(STORAGE_THEME, t); } catch {}
  };
  const setColorScheme = (s: ColorScheme) => {
    setColorSchemeState(s);
    try { localStorage.setItem(STORAGE_SCHEME, s); } catch {}
  };
  const toggleColorScheme = () => setColorScheme(colorScheme === "dark" ? "light" : "dark");

  // Reflect on <html> attributes so CSS variables can switch.
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.dataset.theme = theme;
      document.documentElement.dataset.colorScheme = colorScheme;
      // Also set the standard color-scheme so browser UI (scrollbars, form controls) adapts.
      document.documentElement.style.colorScheme = colorScheme;
    }
  }, [theme, colorScheme]);

  return (
    <Ctx.Provider value={{ theme, setTheme, colorScheme, setColorScheme, toggleColorScheme }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme() {
  return useContext(Ctx);
}
