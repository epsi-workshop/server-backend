import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { setUnauthorizedHandler } from "./api/client";
import type { Alert, Point, Role, SystemState, User } from "./types";
import { errMsg, hasRole } from "./util";

// ---------------------------------------------------------------- toasts
type Toast = { id: number; text: string; kind: "ok" | "err" | "warn" };
const ToastCtx = createContext<(text: string, kind?: Toast["kind"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast toast-${t.kind}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

// ---------------------------------------------------------------- authentification
interface AuthValue {
  user: User | null;
  loading: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
  can: (min: Role) => boolean;
}
const AuthCtx = createContext<AuthValue | null>(null);
export const useAuth = () => useContext(AuthCtx)!;

export function AuthProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const userRef = useRef(user);
  userRef.current = user;
  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }, []);
  // Session expirée côté serveur (401 sur une route protégée, ou WebSocket refusé) : retour à l'écran de connexion.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (!userRef.current) return;
      setUser(null);
      toast("Session expirée, reconnectez-vous.", "warn");
    });
    return () => setUnauthorizedHandler(() => {});
  }, [toast]);
  const value = useMemo<AuthValue>(() => ({
    user,
    loading,
    login: async (u, p) => setUser(await api.login(u, p)),
    logout: async () => { await api.logout().catch(() => {}); setUser(null); },
    changePassword: async (current, next) => setUser(await api.changeOwnPassword(current, next)),
    can: (min) => hasRole(user?.role, min),
  }), [user, loading]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

// ---------------------------------------------------------------- temps réel
export type Trend = { temperature: Point[]; humidity: Point[]; distance: Point[] };
interface LiveValue {
  state: SystemState | null;
  connected: boolean;
  trend: Trend;
  alerts: Alert[];
  openAlerts: number;
  setAlerts: (fn: (a: Alert[]) => Alert[]) => void;
  error: string | null;
  /** Incrémenté à chaque message `log` reçu : la page Journaux se recharge sur ce signal. */
  logSeq: number;
}
const LiveCtx = createContext<LiveValue | null>(null);
export const useLive = () => useContext(LiveCtx)!;
const TREND_MAX = 90;

export function LiveProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [state, setState] = useState<SystemState | null>(null);
  const [connected, setConnected] = useState(false);
  const [alerts, setAlertsRaw] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [trend, setTrend] = useState<Trend>({ temperature: [], humidity: [], distance: [] });
  const [logSeq, setLogSeq] = useState(0);
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const alertsRef = useRef(alerts);
  alertsRef.current = alerts;

  const pushTrend = (s: SystemState) =>
    setTrend((t) => {
      const add = (arr: Point[], ts: string, value: number) =>
        (arr.length && arr[arr.length - 1].ts === ts ? arr : [...arr, { ts, value }]).slice(-TREND_MAX);
      return {
        temperature: add(t.temperature, s.sensors.temperature.ts, s.sensors.temperature.value),
        humidity: add(t.humidity, s.sensors.humidity.ts, s.sensors.humidity.value),
        distance: add(t.distance, s.sensors.distance.ts, s.sensors.distance.cm),
      };
    });

  useEffect(() => {
    let alive = true;
    let lost = false;
    // Chargement complet : au démarrage, puis après chaque reconnexion du temps réel
    // (les alertes émises pendant la coupure ne sont pas rejouées par le WebSocket).
    const load = () =>
      Promise.all([api.getState(), api.getAlerts()])
        .then(([s, a]) => { if (!alive) return; setState(s); pushTrend(s); setAlertsRaw(a); setError(null); })
        .catch((e) => alive && setError(errMsg(e)));
    load();
    const unsub = api.subscribe(
      (m) => {
        if (m.type === "state") { setState(m.data); pushTrend(m.data); setError(null); }
        if (m.type === "alert") {
          const prev = alertsRef.current.find((x) => x.id === m.data.id);
          // Notification à la création ou à l'escalade, pas lors d'un acquittement.
          if (m.data.status === "ouverte" && (!prev || prev.level !== m.data.level || prev.title !== m.data.title))
            toastRef.current(`${m.data.title}, score ${m.data.score}`, m.data.level === "critique" ? "err" : "warn");
          setAlertsRaw((a) => [m.data, ...a.filter((x) => x.id !== m.data.id)]);
        }
        if (m.type === "log") setLogSeq((n) => n + 1);
      },
      (c) => {
        setConnected(c);
        if (!c) lost = true;
        else if (lost) { lost = false; load(); }
      },
    );
    return () => { alive = false; unsub(); };
  }, []);

  const value = useMemo<LiveValue>(() => ({
    state, connected, trend, alerts, error, logSeq,
    openAlerts: alerts.filter((a) => a.status === "ouverte").length,
    setAlerts: (fn) => setAlertsRaw(fn),
  }), [state, connected, trend, alerts, error, logSeq]);
  return <LiveCtx.Provider value={value}>{children}</LiveCtx.Provider>;
}
