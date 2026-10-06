import { NavLink, Outlet } from "react-router-dom";
import { Activity, Bell, Camera, KeyRound, LayoutGrid, LogOut, ScrollText, Settings2, ShieldCheck, ShieldOff } from "lucide-react";
import { Suspense, useState } from "react";
import { api } from "../api";
import { useAuth, useLive, useToast } from "../store";
import { Confirm, Loading, Logo } from "./ui";
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
          <Logo size={28} />
          <div>
            <strong>Sentinel-X</strong>
            <span>Salle serveur, boîtier box01</span>
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
        <div className="me">
          <div>
            <strong>{user?.username}</strong>
            <span>{user && ROLE_LABEL[user.role]}{api.mode === "mock" ? " (démo)" : ""}</span>
          </div>
          <div className="me-actions">
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

/** Bandeau d'état : la pièce maîtresse, couleur = niveau de menace. */
function Annunciator() {
  const { state, connected } = useLive();
  const { can } = useAuth();
  const toast = useToast();
  const [confirmDisarm, setConfirmDisarm] = useState(false);
  if (!state) return <div className="annun annun-off"><div className="annun-level"><span>Connexion au serveur…</span></div></div>;
  const lvl = !state.device.online ? "critique" : state.threat.level;
  const arm = async () => {
    try { await api.arm(); toast("Système armé"); } catch (e) { toast(errMsg(e), "err"); }
  };
  return (
    <div className={`annun annun-${lvl}`}>
      <div className="annun-level">
        <span className="annun-word">{state.device.online ? LEVEL_LABEL[state.threat.level] : "Boîtier muet"}</span>
        <span className="annun-score">score {state.threat.score}</span>
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
