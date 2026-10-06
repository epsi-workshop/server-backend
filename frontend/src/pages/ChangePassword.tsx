import { useEffect, useRef, useState } from "react";
import { useAuth, useToast } from "../store";
import { Logo } from "../components/ui";
import { errMsg } from "../util";

const MIN_LENGTH = 12;

/** Formulaire de changement de son propre mot de passe. */
export function ChangePasswordForm({ onDone, onCancel }: { onDone?: () => void; onCancel?: () => void }) {
  const { changePassword } = useAuth();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mismatch = confirm.length > 0 && confirm !== next;
  const ok = current.length > 0 && next.length >= MIN_LENGTH && next === confirm;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ok) return;
    setBusy(true); setErr(null);
    try {
      await changePassword(current, next);
      toast("Mot de passe modifié");
      onDone?.();
    } catch (e2) { setErr(errMsg(e2)); } finally { setBusy(false); }
  };

  return (
    <form className="form-col" onSubmit={submit}>
      <label className="field"><span>Mot de passe actuel</span>
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required /></label>
      <label className="field"><span>Nouveau mot de passe ({MIN_LENGTH} caractères minimum)</span>
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required minLength={MIN_LENGTH} />
        <small>{Math.max(0, MIN_LENGTH - next.length)} caractères minimum restants</small></label>
      <label className="field"><span>Confirmer le nouveau mot de passe</span>
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
        {mismatch && <small className="form-error">Les deux saisies ne correspondent pas.</small>}</label>
      {err && <p className="form-error">{err}</p>}
      <div className="dialog-actions">
        {onCancel && <button type="button" className="btn" onClick={onCancel} disabled={busy}>Annuler</button>}
        <button className="btn btn-primary" disabled={!ok || busy}>{busy ? "Enregistrement…" : "Changer le mot de passe"}</button>
      </div>
    </form>
  );
}

/** Écran plein (changement obligatoire après création ou réinitialisation du compte). */
export default function ChangePassword({ forced }: { forced?: boolean }) {
  const { user, logout } = useAuth();
  return (
    <div className="login">
      <div className="login-card">
        <div className="brand brand-login">
          <Logo size={34} />
          <div><strong>Sentinel-X</strong><span>Compte {user?.username}</span></div>
        </div>
        {forced && <p className="muted">Votre mot de passe a été fixé par un administrateur. Choisissez-en un nouveau pour continuer.</p>}
        <ChangePasswordForm />
        <button className="btn btn-block" onClick={logout}>Se déconnecter</button>
      </div>
    </div>
  );
}

/** Fenêtre de changement de mot de passe, ouverte depuis la barre latérale. */
export function ChangePasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="dialog" onClose={onClose}>
      <h2>Changer mon mot de passe</h2>
      {open && <ChangePasswordForm onDone={onClose} onCancel={onClose} />}
    </dialog>
  );
}
