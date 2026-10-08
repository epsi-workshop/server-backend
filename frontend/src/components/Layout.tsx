import { NavLink, Outlet } from "react-router-dom";
import { Activity, Bell, Camera, KeyRound, LayoutGrid, LogOut, Moon, ScrollText, Settings2, ShieldAlert, ShieldCheck, ShieldOff, Siren, Sun, WifiOff, type LucideIcon } from "lucide-react";
import { Suspense, useState } from "react";
import { api } from "../api";
import { useAuth, useLive, useToast } from "../store";
import { Confirm, Loading } from "./ui";
import { Logo3DSlot } from "../three/Views";
import { useTheme } from "../theme";
import { ChangePasswordDialog } from "../pages/ChangePassword";
import { LEVEL_LABEL, ROLE_LABEL, ago, cameraOpen, errMsg } from "../util";

export default function Layout() {
  const { user, logout, can } = useAuth();
  const { openAlerts, state } = useLive();
  const [pwdOpen, setPwdOpen] = useState(false);
  const camLive = !!state && cameraOpen(state.camera);
  const nav = [
    { to: "/", label: "Vue d'ensemble", icon: LayoutGrid, show: true },
    { to: "/camera", label: "Caméra", icon: Camera, show: true, badge: camLive ? "en direct" : undefined },
    { to: "/capteurs", label: "Historique capteurs", icon: Activity, show: true },
    { to: "/alertes", label: "Alertes", icon: Bell, show: true, count: openAlerts },
    { to: "/journaux", label: "Journaux", icon: ScrollText, show: can("operateur") },
    { to: "/admin", label: "Administration", icon: Settings2, show: can("admin") },
  ];
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <Logo3DSlot className="brand-logo" />
          <div>
            <strong>Sentinel</strong>
            <span>Pot sentinelle · box01</span>
          </div>
        </div>
        <nav className="nav">
          {nav.filter((n) => n.show).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => (isActive ? "nav-item on" : "nav-item")}>
              <n.icon size={18} aria-hidden="true" />
              <span>{n.label}</span>
              {!!n.count && <em className="count">{n.count}</em>}
              {n.badge && <em className="live-badge">{n.badge}</em>}
            </NavLink>
          ))}
        </nav>
        <svg className="vine" viewBox="0 0 240 120" aria-hidden="true">
          <path className="vine-stem" d="M-5 110 C 40 100, 60 70, 95 72 S 150 95, 180 60 S 225 30, 250 38" />
          <path className="vine-leaf" d="M60 84 q 10 -22 30 -14 q -12 18 -30 14 Z" />
          <path className="vine-leaf" d="M120 82 q 16 -4 22 16 q -18 2 -22 -16 Z" />
          <path className="vine-leaf" d="M176 62 q 4 -22 26 -22 q -6 20 -26 22 Z" />
          <circle className="vine-bud" cx="232" cy="36" r="3" />
        </svg>
        <div className="me">
          <div>
            <strong>{user?.username}</strong>
            <span>{user && ROLE_LABEL[user.role]}{api.mode === "mock" ? " (démo)" : ""}</span>
          </div>
          <div className="me-actions">
            <ThemeToggle />
            <button className="icon-btn" onClick={() => setPwdOpen(true)} aria-label="Changer mon mot de passe" title="Changer mon mot de passe"><KeyRound size={18} /></button>
            <button className="icon-btn" onClick={logout} aria-label="Se déconnecter" title="Se déconnecter"><LogOut size={18} /></button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Annunciator />
        <div className="page"><Suspense fallback={<Loading />}><Outlet /></Suspense></div>
      </main>
      <ChangePasswordDialog open={pwdOpen} onClose={() => setPwdOpen(false)} />
    </div>
  );
}

type Level = "info" | "alerte" | "critique" | "offline";
const LEVEL_ICON: Record<Level, LucideIcon> = { info: ShieldCheck, alerte: ShieldAlert, critique: Siren, offline: WifiOff };
const LEVEL_STEP: Record<Level, number> = { offline: 0, info: 1, alerte: 2, critique: 3 };

/** Témoin de niveau : pastille à icône + trois barres qui se remplissent avec la menace. */
function LevelSignal({ level }: { level: Level }) {
  const Icon = LEVEL_ICON[level];
  const step = LEVEL_STEP[level];
  return (
    <div className="signal" aria-hidden="true">
      <span className="signal-tile"><Icon size={20} strokeWidth={2.2} /></span>
      <span className="signal-bars">{[1, 2, 3].map((i) => <i key={i} className={i <= step ? "on" : ""} />)}</span>
    </div>
  );
}

/** Bandeau d'état : la pièce maîtresse, couleur = niveau de menace. */
function Annunciator() {
  const { state, connected } = useLive();
  const { can } = useAuth();
  const toast = useToast();
  const [confirmDisarm, setConfirmDisarm] = useState(false);
  if (!state) return <div className="annun annun-offline"><LevelSignal level="offline" /><div className="annun-level"><span className="annun-word">Connexion au serveur…</span></div></div>;
  const lvl: Level = !state.device.online ? "offline" : state.threat.level;
  const arm = async () => {
    try { await api.arm(); toast("Système armé"); } catch (e) { toast(errMsg(e), "err"); }
  };
  return (
    <div className={`annun annun-${lvl}`}>
      <LevelSignal level={lvl} />
      <div className="annun-level">
        <span className="annun-kicker">Niveau de menace</span>
        <span className="annun-word">{state.device.online ? LEVEL_LABEL[state.threat.level] : "Boîtier muet"}<span className="annun-score">{state.threat.score}</span></span>
      </div>
      <p className="annun-reasons">
        {!state.device.online
          ? `Dernier signe de vie ${ago(state.device.lastHeartbeat)}. Vérifiez l'alimentation et le Wi-Fi du boîtier.`
          : state.threat.reasons.length ? state.threat.reasons.join(", ") : "Aucun signal suspect sur la dernière minute."}
      </p>
      <div className="annun-side">
        <span className={connected ? "link-state" : "link-state link-down"}>{connected ? "Temps réel connecté" : "Temps réel coupé, reconnexion…"}</span>
        {can("operateur") ? (
          state.device.armed
            ? <button className="arm-btn armed" onClick={() => setConfirmDisarm(true)}><ShieldCheck size={18} />Armé</button>
            : <button className="arm-btn" onClick={arm}><ShieldOff size={18} />Désarmé</button>
        ) : (
          <span className="arm-btn static">{state.device.armed ? <><ShieldCheck size={18} />Armé</> : <><ShieldOff size={18} />Désarmé</>}</span>
        )}
      </div>
      <Confirm open={confirmDisarm} title="Désarmer le système ?"
        body="Les détections continuent d'être enregistrées, mais le score n'est plus majoré et le buzzer ne se déclenche plus. L'action est journalisée."
        confirmLabel="Désarmer" danger onClose={() => setConfirmDisarm(false)}
        onConfirm={async () => { await api.disarm(); toast("Système désarmé", "warn"); }} />
    </div>
  );
}

function ThemeToggle() {
  const [theme, toggle] = useTheme();
  const label = theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre";
  return (
    <button className="icon-btn" onClick={toggle} aria-label={label} title={label}>
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
