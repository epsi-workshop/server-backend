import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../store";
import { Logo3DSlot } from "../three/Views";
import { errMsg } from "../util";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await login(username, password); } catch (e2) { setErr(errMsg(e2)); } finally { setBusy(false); }
  };
  return (
    <div className="login">
      <div className="login-hero">
        <Logo3DSlot className="login-logo" />
        <h1 className="login-title">Sentinel</h1>
        <p className="login-sub">Surveillance discrète au cœur de la salle serveur.</p>
      </div>
      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">Connexion</div>
        <label className="field"><span>Identifiant</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required /></label>
        <label className="field"><span>Mot de passe</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        {err && <p className="form-error">{err}</p>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Connexion…" : "Se connecter"}</button>
        {api.mode === "mock" && (
          <div className="demo-hint">
            <strong>Mode démo, boîtier simulé</strong>
            <p>Comptes : <code>admin</code>, <code>operateur</code> ou <code>lecteur</code>, mot de passe <code>demo</code>. Chaque rôle voit des écrans différents.</p>
          </div>
        )}
      </form>
    </div>
  );
}
