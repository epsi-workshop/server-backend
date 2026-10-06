/** Palette des objets 3D : céramique, métal brossé, sauge (le boîtier est un pot de fleurs camouflé). */
export const PALETTE = {
  ivory: "#ece8df",
  graphite: "#2a2a2d",
  brass: "#b89a5e",
  sage: "#8fae8b",
  leaf: "#6f8f6a",
  water: "#a9bcc4",
} as const;

/** Couleur d'état : sauge (normal), ocre (alerte), terre cuite (critique), gris (hors ligne). */
export const STATE_COLOR = {
  ok: "#8fae8b",
  warn: "#d1a04a",
  crit: "#c9614a",
  off: "#8a8a8f",
} as const;

/** Préférence système : animations réduites (vitesse des rotations divisée par 5). */
export const MOTION =
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0.2 : 1;
