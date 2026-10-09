import { useEffect, useState } from "react";

/**
 * Application installable : enregistrement du service worker et invite d'installation.
 *
 * Le service worker n'est enregistré qu'en production, dans un contexte sécurisé (HTTPS ou
 * localhost : exigence des navigateurs) et hors build autonome (fichier HTML unique).
 */

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

let deferred: InstallPrompt | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

export function initPwa(): void {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // on garde l'invite pour le bouton « Installer » du tableau de bord
    deferred = e as InstallPrompt;
    notify();
  });
  window.addEventListener("appinstalled", () => { deferred = null; notify(); });

  if (import.meta.env.PROD && import.meta.env.MODE !== "single" && window.isSecureContext && "serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => { /* sans service worker, l'application reste utilisable */ });
    });
  }
}

/** Déjà lancée comme application (écran d'accueil, fenêtre dédiée). */
export function isStandalone(): boolean {
  return window.matchMedia?.("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

/** iPhone / iPad : pas d'invite automatique, l'installation passe par le menu Partager de Safari. */
export function isIos(): boolean {
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
}

/** État du bouton « Installer » : invite disponible (Chrome, Edge, Android) ou consigne iOS. */
export function useInstall(): { available: boolean; ios: boolean; install: () => Promise<boolean> } {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    listeners.add(l);
    return () => { listeners.delete(l); };
  }, []);
  const standalone = isStandalone();
  const ios = !standalone && isIos();
  return {
    available: !standalone && (!!deferred || ios),
    ios,
    install: async () => {
      if (!deferred) return false;
      await deferred.prompt();
      const { outcome } = await deferred.userChoice;
      deferred = null;
      notify();
      return outcome === "accepted";
    },
  };
}
