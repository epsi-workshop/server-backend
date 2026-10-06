import type { LogLevel, Role, SystemState, ThreatLevel } from "./types";

const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });

export function ago(ts: string | null | undefined): string {
  if (!ts) return "jamais";
  const s = Math.round((Date.parse(ts) - Date.now()) / 1000);
  const a = Math.abs(s);
  if (a < 5) return "à l'instant";
  if (a < 60) return rtf.format(s, "second");
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}

export const fmtTime = (ts: string) =>
  new Date(ts).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const fmtDateTime = (ts: string) =>
  new Date(ts).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const fmtNum = (n: number, d = 1) => n.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

export function fmtDuration(s: number): string {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d} j ${h} h`;
  if (h) return `${h} h ${m} min`;
  return `${m} min ${Math.floor(s % 60)} s`;
}

export const LEVEL_LABEL: Record<ThreatLevel, string> = { info: "Calme", alerte: "Alerte", critique: "Critique" };
export const LOG_LEVEL_LABEL: Record<LogLevel, string> = { info: "Info", warn: "Avertissement", error: "Erreur", critical: "Critique" };
export const ROLE_LABEL: Record<Role, string> = { lecteur: "Lecteur", operateur: "Opérateur", admin: "Administrateur" };
const RANK: Record<Role, number> = { lecteur: 0, operateur: 1, admin: 2 };
export const hasRole = (r: Role | undefined, min: Role) => !!r && RANK[r] >= RANK[min];

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : "Erreur inattendue.";
}

/** Accès caméra forcé encore valide (le backend peut laisser une date passée dans overrideUntil). */
export function overrideLeftS(camera: SystemState["camera"], now = Date.now()): number {
  if (!camera.overrideUntil) return 0;
  return Math.max(0, Math.round((Date.parse(camera.overrideUntil) - now) / 1000));
}
export const cameraOpen = (camera: SystemState["camera"]) => camera.detectionActive || overrideLeftS(camera) > 0;

/** Min, moyenne, max sans spread (Math.min(...arr) dépasse la pile au-delà de ~100 000 valeurs). */
export function stats(vals: number[]): { min: number; avg: number; max: number } | null {
  if (!vals.length) return null;
  let min = Infinity, max = -Infinity, sum = 0;
  for (const v of vals) { if (v < min) min = v; if (v > max) max = v; sum += v; }
  return { min, avg: sum / vals.length, max };
}

/**
 * Cellule CSV sûre : guillemets doublés, et neutralisation des formules (=, +, -, @, tabulation,
 * retour chariot en tête) qu'Excel ou LibreOffice exécuteraient à l'ouverture. Un identifiant saisi
 * sur l'écran de connexion se retrouve dans les journaux : c'est une donnée contrôlée par un attaquant.
 */
export function csvCell(c: string | number): string {
  let s = String(c);
  if (typeof c === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return `"${s.replace(/"/g, '""')}"`;
}
export const toCsv = (rows: (string | number)[][]) => rows.map((r) => r.map(csvCell).join(";")).join("\r\n");

export function downloadCsv(filename: string, rows: (string | number)[][]) {
  const csv = toCsv(rows);
  const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
