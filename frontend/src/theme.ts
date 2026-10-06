import { useEffect, useState } from "react";

/** Thème clair / sombre : préférence système par défaut, choix de l'utilisateur mémorisé localement. */
export type Theme = "light" | "dark";
const KEY = "sentinel-theme";

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null; // navigation privée, stockage bloqué
  }
}

function system(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

apply(stored() ?? system());

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) ?? system());
  useEffect(() => {
    apply(theme);
  }, [theme]);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(KEY, next); } catch { /* sans stockage : le choix vaut pour la session */ }
    setTheme(next);
  };
  return [theme, toggle];
}
