import type { Api } from "./client";
import { ApiError, notifyUnauthorized } from "./client";
import type { LiveMessage, LogFilter } from "../types";

// Implémentation réelle : REST sur /api, temps réel sur /ws/live.
// Authentification par cookie HttpOnly posé par POST /api/auth/login (credentials: "include").

// Routes où un 401 est une réponse normale (identifiants faux, pas encore connecté).
const AUTH_PROBES = ["/api/auth/login", "/api/auth/me", "/api/auth/password"];

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* corps vide */ }
    if (res.status === 401 && !AUTH_PROBES.includes(path)) {
      notifyUnauthorized();
      msg = "Session expirée, reconnectez-vous.";
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(p: string) => req<T>("GET", p);
const post = <T>(p: string, b?: unknown) => req<T>("POST", p, b ?? {});
const patch = <T>(p: string, b: unknown) => req<T>("PATCH", p, b);
const del = (p: string) => req<void>("DELETE", p);
const seg = encodeURIComponent;

function qs(filter: LogFilter): string {
  const p = new URLSearchParams();
  filter.sources?.forEach((s) => p.append("source", s));
  filter.levels?.forEach((l) => p.append("level", l));
  if (filter.q) p.set("q", filter.q);
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Code de fermeture WebSocket envoyé par le backend quand le cookie est absent ou expiré. */
const WS_UNAUTHORIZED = 4401;

export const liveApi: Api = {
  mode: "live",
  login: (username, password) => post("/api/auth/login", { username, password }),
  logout: () => post("/api/auth/logout"),
  me: async () => {
    try {
      return await get("/api/auth/me");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  },
  changeOwnPassword: (current, password) => post("/api/auth/password", { current, password }),

  getState: () => get("/api/state"),
  getHistory: (sensor, range) => get(`/api/measurements?sensor=${seg(sensor)}&range=${seg(range)}`),
  subscribe(onMessage, onStatus) {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 1000;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const schedule = () => {
      if (closed) return;
      timer = setTimeout(reconnect, retry);
      retry = Math.min(retry * 2, 15000);
    };
    // Avant de se reconnecter, vérifie que la session est toujours valide : un refus du handshake
    // HTTP (401) n'est pas visible côté navigateur (code 1006), il bouclerait sinon indéfiniment.
    const reconnect = async () => {
      if (closed) return;
      try {
        const me = await liveApi.me();
        if (closed) return;
        if (!me) { notifyUnauthorized(); return; }
      } catch { /* serveur injoignable : on retente plus tard */ schedule(); return; }
      connect();
    };
    const connect = () => {
      if (closed) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(`${proto}://${location.host}/ws/live`);
      ws = sock;
      sock.onopen = () => { retry = 1000; onStatus(true); };
      sock.onmessage = (ev) => {
        try { onMessage(JSON.parse(ev.data) as LiveMessage); } catch { /* message invalide ignoré */ }
      };
      sock.onclose = (ev) => {
        if (ws !== sock) return;
        ws = null;
        onStatus(false);
        if (closed) return;
        if (ev.code === WS_UNAUTHORIZED) { notifyUnauthorized(); return; }
        schedule();
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
      ws = null;
    };
  },

  getAlerts: () => get("/api/alerts"),
  ackAlert: (id, comment) => post(`/api/alerts/${seg(id)}/ack`, { comment }),

  getLogs: (filter) => get(`/api/logs${qs(filter)}`),
  getAudit: () => get("/api/audit"),

  arm: () => post("/api/devices/box01/arm"),
  disarm: () => post("/api/devices/box01/disarm"),
  buzzer: (on) => post("/api/devices/box01/buzzer", { on }),
  restart: (target) => post("/api/system/restart", { target }),
  cameraOverride: (reason) => post("/api/camera/override", { reason }),
  streamUrl: () => "/api/stream",

  getServices: () => get("/api/system/services"),
  getUsers: () => get("/api/users"),
  createUser: (u) => post("/api/users", u),
  updateUser: (id, p) => patch(`/api/users/${seg(id)}`, p),
  resetPassword: (id, password) => post(`/api/users/${seg(id)}/password`, { password }),
  deleteUser: (id) => del(`/api/users/${seg(id)}`),

  getBadges: () => get("/api/badges"),
  createBadge: (b) => post("/api/badges", b),
  updateBadge: (id, p) => patch(`/api/badges/${seg(id)}`, p),
  deleteBadge: (id) => del(`/api/badges/${seg(id)}`),
  startBadgeEnroll: () => post("/api/badges/enroll", {}),
  getBadgeEnroll: () => get("/api/badges/enroll"),
  stopBadgeEnroll: () => del("/api/badges/enroll"),

  getAudio: () => get("/api/audio"),
  scanSpeakers: () => get("/api/audio/devices"),
  connectSpeaker: (t) => post("/api/audio/connect", t),
  disconnectSpeaker: () => post("/api/audio/disconnect", {}),
  forgetSpeaker: async () => { await del("/api/audio/speaker"); return get("/api/audio"); },
  setVolume: (pct) => post(`/api/audio/volume/${Math.round(pct)}`, {}),
  playSound: (s) => post(`/api/audio/sound/${s}`, {}),
  stopSound: () => post("/api/audio/stop", {}),

  getTeam: () => get("/api/team"),
  createMember: (m) => post("/api/team", m),
  updateMember: (id, p) => patch(`/api/team/${seg(id)}`, p),
  deleteMember: (id) => del(`/api/team/${seg(id)}`),

  getSettings: () => get("/api/settings"),
  saveSettings: (s) => req("PUT", "/api/settings", s),
};
