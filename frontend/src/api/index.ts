import type { Api } from "./client";
import { liveApi } from "./live";

// Vite remplace import.meta.env.VITE_API_MODE à la compilation : en mode live, la branche mock est
// du code mort, éliminée du bundle (le simulateur et ses comptes de démo ne sont pas livrés).
// La condition doit rester écrite ici sur import.meta.env (une constante importée d'un autre module
// n'est pas propagée par le bundler).

// Liaison ES « vivante » : les modules qui importent `api` voient la valeur affectée par initApi().
export let api: Api = liveApi;

/** À appeler avant le premier rendu. */
export async function initApi(): Promise<void> {
  if (import.meta.env.VITE_API_MODE !== "live") api = (await import("./mock")).mockApi;
}

export { ApiError } from "./client";
