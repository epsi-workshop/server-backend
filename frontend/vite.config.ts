/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// `npm run build`        -> build classique (dist/) servi par nginx derrière Caddy
// `npm run build:single` -> un seul fichier HTML autonome (démo hors-ligne)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  // Backend utilisé par `npm run dev` en mode live (fichier .env : VITE_BACKEND_URL=https://…).
  const backend = env.VITE_BACKEND_URL || "https://192.168.50.10";
  const wsBackend = backend.replace(/^http/, "ws");
  // Le backend vérifie l'en-tête Origin (anti-CSRF) : en dev, on présente l'origine du backend
  // au lieu de http://localhost:5173, sinon toutes les requêtes POST/PUT/PATCH/DELETE seraient refusées.
  const headers = { Origin: backend };
  return {
    plugins: mode === "single" ? [react(), viteSingleFile()] : [react()],
    // Deux pages : le tableau de bord (index.html) et la page de présentation (presentation.html).
    // Le build autonome (mode single) ne contient que le tableau de bord.
    build: mode === "single" ? {} : {
      rolldownOptions: { input: { main: "index.html", presentation: "presentation.html" } },
    },
    server: {
      port: 5173,
      proxy: {
        // secure: false accepte le certificat auto-signé du réseau dédié (dev uniquement).
        "/api": { target: backend, changeOrigin: true, secure: false, headers },
        "/ws": { target: wsBackend, ws: true, changeOrigin: true, secure: false, headers },
      },
    },
    test: {
      environment: "node",
    },
  };
});
