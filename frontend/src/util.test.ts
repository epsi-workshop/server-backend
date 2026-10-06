import { describe, expect, it } from "vitest";
import { cameraOpen, csvCell, hasRole, overrideLeftS, stats, toCsv } from "./util";
import type { SystemState } from "./types";

describe("csvCell", () => {
  it("double les guillemets", () => {
    expect(csvCell('a "b" c')).toBe('"a ""b"" c"');
  });
  it.each(["=HYPERLINK(\"http://x\")", "+1+2", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"])(
    "neutralise la formule %j",
    (v) => {
      expect(csvCell(v).startsWith(`"'`)).toBe(true);
    },
  );
  it("laisse les nombres et le texte ordinaire intacts", () => {
    expect(csvCell(-58)).toBe('"-58"');
    expect(csvCell("Connexion réussie : admin")).toBe('"Connexion réussie : admin"');
  });
  it("produit des lignes CRLF séparées par des points-virgules", () => {
    expect(toCsv([["a", "b"], ["c", 1]])).toBe('"a";"b"\r\n"c";"1"');
  });
});

describe("hasRole", () => {
  it("respecte la hiérarchie lecteur < opérateur < admin", () => {
    expect(hasRole("admin", "operateur")).toBe(true);
    expect(hasRole("operateur", "admin")).toBe(false);
    expect(hasRole("lecteur", "lecteur")).toBe(true);
    expect(hasRole(undefined, "lecteur")).toBe(false);
  });
});

describe("caméra", () => {
  const cam = (p: Partial<SystemState["camera"]>): SystemState["camera"] => ({
    online: true, detectionActive: false, lastDetection: null, overrideUntil: null, masked: false, ...p,
  });
  it("ignore un accès forcé expiré", () => {
    const past = new Date(Date.now() - 5000).toISOString();
    expect(overrideLeftS(cam({ overrideUntil: past }))).toBe(0);
    expect(cameraOpen(cam({ overrideUntil: past }))).toBe(false);
  });
  it("ouvre le flux pendant un accès forcé valide ou une détection", () => {
    const future = new Date(Date.now() + 30_000).toISOString();
    expect(cameraOpen(cam({ overrideUntil: future }))).toBe(true);
    expect(cameraOpen(cam({ detectionActive: true }))).toBe(true);
  });
});

describe("stats", () => {
  it("gère de très grands tableaux sans dépasser la pile", () => {
    const big = Array.from({ length: 500_000 }, (_, i) => i % 100);
    expect(stats(big)).toEqual({ min: 0, max: 99, avg: 49.5 });
  });
  it("renvoie null pour un tableau vide", () => {
    expect(stats([])).toBeNull();
  });
});
