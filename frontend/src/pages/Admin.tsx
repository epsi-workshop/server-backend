import { useCallback, useEffect, useRef, useState } from "react";
import { BellRing, Camera, ImagePlus, Nfc, KeyRound, Power, RefreshCw, Trash2, UserPlus } from "lucide-react";
import { api } from "../api";
import { useAuth, useLive, useToast } from "../store";
import { Confirm, Dot, Empty, Loading, Panel, Tabs } from "../components/ui";
import type { Badge, BadgeEnrollState, RestartRequest, Role, ServiceHealth, Settings, TeamMember, User } from "../types";
import { ROLE_LABEL, ago, errMsg, fmtDuration, fmtNum } from "../util";

type Tab = "systeme" | "utilisateurs" | "equipe" | "badges" | "detection";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("systeme");
  return (
    <div className="stack">
      <div className="toolbar">
        <h1>Administration</h1>
        <Tabs value={tab} onChange={setTab} items={[
          { id: "systeme", label: "Système" }, { id: "utilisateurs", label: "Utilisateurs" },
          { id: "equipe", label: "Équipe" }, { id: "badges", label: "Badges" }, { id: "detection", label: "Détection" },
        ]} />
      </div>
      {tab === "systeme" && <SystemTab />}
      {tab === "utilisateurs" && <UsersTab />}
      {tab === "equipe" && <TeamTab />}
      {tab === "badges" && <BadgesTab />}
      {tab === "detection" && <DetectionTab />}
    </div>
  );
}

// ---------------------------------------------------------------- Système
type Pending = { target: RestartRequest; title: string; body: string; text?: string } | null;

function SystemTab() {
  const toast = useToast();
  const { state } = useLive();
  const [services, setServices] = useState<ServiceHealth[] | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const load = useCallback(() => api.getServices().then(setServices).catch((e) => toast(errMsg(e), "err")), [toast]);
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, [load]);

  // "all" est orchestré par le backend (ordre, reprise sur erreur) : une seule requête.
  const restart = async (target: RestartRequest) => {
    await api.restart(target);
    toast(target === "all" ? "Redémarrage complet lancé" : "Redémarrage demandé", "warn");
    load();
  };
  const buzzer = async () => {
    try {
      await api.buzzer(true);
      toast("Buzzer activé pendant 2 secondes");
      setTimeout(() => api.buzzer(false).catch(() => {}), 2000);
    } catch (e) { toast(errMsg(e), "err"); }
  };

  return (
    <>
      <Panel title="Matériel">
        <div className="controls">
          <div className="control">
            <div>
              <strong>Boîtier box01</strong>
              <span className="muted small"><Dot tone={state?.device.online ? "ok" : "crit"} />{state?.device.online ? `En ligne depuis ${fmtDuration(state.device.uptimeS)}` : "Hors ligne"}</span>
            </div>
            <button className="btn" onClick={() => setPending({ target: "box", title: "Redémarrer le boîtier ?",
              body: "Le boîtier sera hors ligne environ 30 secondes. Pendant ce temps, aucune détection n'est remontée et l'alerte « boîtier muet » peut se déclencher.", text: "box01" })}>
              <Power size={16} />Redémarrer le boîtier
            </button>
          </div>
          <div className="control">
            <div>
              <strong>Caméra ESP32-CAM</strong>
              <span className="muted small"><Dot tone={state?.camera.online ? "ok" : "crit"} />{state?.camera.online ? "En ligne" : "Hors ligne"}</span>
            </div>
            <button className="btn" onClick={() => setPending({ target: "camera", title: "Redémarrer la caméra ?",
              body: "Le flux vidéo et la détection de mouvement seront interrompus environ 15 secondes." })}>
              <Camera size={16} />Redémarrer la caméra
            </button>
          </div>
          <div className="control">
            <div>
              <strong>Alarme locale</strong>
              <span className="muted small">Fait sonner le buzzer du boîtier pour vérifier qu'il fonctionne.</span>
            </div>
            <button className="btn" onClick={buzzer}><BellRing size={16} />Tester le buzzer</button>
          </div>
        </div>
      </Panel>

      <Panel title="Services du serveur" action={<button className="icon-btn" onClick={load} aria-label="Actualiser" title="Actualiser"><RefreshCw size={16} /></button>}>
        {!services ? <Loading /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Service</th><th>État</th><th>Démarré depuis</th><th className="num">CPU</th><th className="num">Mémoire</th><th>Version</th><th /></tr></thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s.name}>
                    <td><strong>{s.name}</strong></td>
                    <td><Dot tone={s.status === "ok" ? "ok" : s.status === "degrade" ? "warn" : "crit"} />{s.status === "ok" ? "Opérationnel" : s.status === "degrade" ? "Dégradé" : "Arrêté"}</td>
                    <td>{s.status === "arrete" ? "redémarrage…" : fmtDuration(s.uptimeS)}</td>
                    <td className="num tabular">{fmtNum(s.cpu)} %</td>
                    <td className="num tabular">{s.memMb} Mo</td>
                    <td>{s.version}</td>
                    <td className="num">
                      {s.target && (
                        <button className="btn btn-small" disabled={s.status === "arrete"}
                          onClick={() => setPending({ target: s.target!, title: `Redémarrer ${s.name} ?`, body: "Le service sera indisponible quelques secondes. Les messages MQTT en attente sont conservés par le broker." })}>
                          Redémarrer
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Redémarrage complet" tone="crit">
        <div className="control">
          <span className="muted">Redémarre le boîtier, la caméra et tous les services applicatifs. Le système est aveugle pendant environ une minute.</span>
          <button className="btn btn-danger" onClick={() => setPending({ target: "all", title: "Redémarrer tout le système ?",
            body: "Le boîtier, la caméra et les services vision, anomalies, broker et backend vont redémarrer. Aucune intrusion ne sera détectée pendant environ une minute.", text: "REDEMARRER" })}>
            <Power size={16} />Tout redémarrer
          </button>
        </div>
      </Panel>

      <Confirm open={!!pending} title={pending?.title ?? ""} body={pending?.body ?? ""} requireText={pending?.text}
        confirmLabel="Redémarrer" danger onClose={() => setPending(null)} onConfirm={() => restart(pending!.target)} />
    </>
  );
}

// ---------------------------------------------------------------- Utilisateurs
const ROLES: Role[] = ["lecteur", "operateur", "admin"];
function genPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_!";
  const a = new Uint32Array(16);
  crypto.getRandomValues(a);
  return Array.from(a, (n) => chars[n % chars.length]).join("");
}

function UsersTab() {
  const toast = useToast();
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [form, setForm] = useState({ username: "", role: "lecteur" as Role, password: genPassword() });
  const [toDelete, setToDelete] = useState<User | null>(null);
  const [toReset, setToReset] = useState<{ u: User; pwd: string } | null>(null);
  const load = useCallback(() => api.getUsers().then(setUsers).catch((e) => toast(errMsg(e), "err")), [toast]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast(ok); load(); } catch (e) { toast(errMsg(e), "err"); }
  };

  return (
    <>
      <Panel title="Comptes">
        {!users ? <Loading /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Identifiant</th><th>Rôle</th><th>Statut</th><th>Dernière connexion</th><th /></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.username}</strong>{u.id === me?.id && <span className="muted small"> (vous)</span>}</td>
                    <td>
                      <select value={u.role} aria-label={`Rôle de ${u.username}`}
                        onChange={(e) => act(() => api.updateUser(u.id, { role: e.target.value as Role }), "Rôle modifié")}>
                        {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                      </select>
                    </td>
                    <td>
                      <label className="switch">
                        <input type="checkbox" checked={u.active}
                          onChange={(e) => act(() => api.updateUser(u.id, { active: e.target.checked }), e.target.checked ? "Compte activé" : "Compte désactivé")} />
                        <span>{u.active ? "Actif" : "Désactivé"}</span>
                      </label>
                    </td>
                    <td>{ago(u.lastLogin)}</td>
                    <td className="num nowrap">
                      <button className="icon-btn" title="Réinitialiser le mot de passe" aria-label={`Réinitialiser le mot de passe de ${u.username}`}
                        onClick={() => setToReset({ u, pwd: genPassword() })}><KeyRound size={16} /></button>
                      <button className="icon-btn danger" title="Supprimer" aria-label={`Supprimer ${u.username}`} disabled={u.id === me?.id}
                        onClick={() => setToDelete(u)}><Trash2 size={16} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Ajouter un compte">
        <form className="form-row" onSubmit={(e) => {
          e.preventDefault();
          act(() => api.createUser(form), `Compte ${form.username} créé`).then(() => setForm({ username: "", role: "lecteur", password: genPassword() }));
        }}>
          <label className="field"><span>Identifiant</span>
            <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })} autoComplete="off" /></label>
          <label className="field"><span>Rôle</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select></label>
          <label className="field field-grow"><span>Mot de passe initial (12 caractères minimum)</span>
            <div className="input-group">
              <input required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="tabular" autoComplete="new-password" />
              <button type="button" className="btn" onClick={() => setForm({ ...form, password: genPassword() })}>Générer</button>
            </div></label>
          <button className="btn btn-primary" type="submit"><UserPlus size={16} />Créer le compte</button>
        </form>
        <p className="muted small">Transmettez le mot de passe par un canal séparé ; la personne devra obligatoirement le changer à sa première connexion.</p>
      </Panel>

      <Confirm open={!!toDelete} title={`Supprimer le compte ${toDelete?.username} ?`}
        body="Le compte ne pourra plus se connecter. Son historique reste dans le journal d'audit." confirmLabel="Supprimer" danger
        onClose={() => setToDelete(null)} onConfirm={async () => { await api.deleteUser(toDelete!.id); toast("Compte supprimé"); load(); }} />
      <Confirm open={!!toReset} title={`Réinitialiser le mot de passe de ${toReset?.u.username} ?`}
        body={<>Nouveau mot de passe : <code className="pwd">{toReset?.pwd}</code><br />Copiez-le avant de confirmer. La personne devra le changer à sa prochaine connexion.</>}
        confirmLabel="Réinitialiser" onClose={() => setToReset(null)}
        onConfirm={async () => { await api.resetPassword(toReset!.u.id, toReset!.pwd); toast("Mot de passe réinitialisé"); }} />
    </>
  );
}

// ---------------------------------------------------------------- Équipe (reconnaissance faciale)
/** Photo réduite à 1024 px (JPEG) avant envoi : une photo de téléphone fait plusieurs Mo. */
function shrinkPhoto(file: File, max = 1024): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * k);
      canvas.height = Math.round(img.height * k);
      canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.9));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Image illisible.")); };
    img.src = url;
  });
}

function TeamTab() {
  const toast = useToast();
  const [team, setTeam] = useState<TeamMember[] | null>(null);
  const [name, setName] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState<TeamMember | null>(null);
  const load = useCallback(() => api.getTeam().then(setTeam).catch((e) => toast(errMsg(e), "err")), [toast]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast(ok); load(); return true; } catch (e) { toast(errMsg(e), "err"); return false; }
  };
  return (
    <>
      <Panel title="Membres reconnus par la caméra">
        {!team ? <Loading /> : team.length === 0 ? <Empty>Aucun membre : tout visage sera signalé comme intrus.</Empty> : (
          <ul className="team-grid">
            {team.map((m) => (
              <li key={m.id} className={`team-card${m.active ? "" : " is-off"}`}>
                <img src={m.photo} alt={`Visage de ${m.name}`} />
                <div className="team-meta">
                  <strong>{m.name}</strong>
                  <span className="muted small">Vu {m.lastSeen ? ago(m.lastSeen) : "jamais"}</span>
                  <label className="switch">
                    <input type="checkbox" checked={m.active}
                      onChange={(e) => act(() => api.updateMember(m.id, { active: e.target.checked }), e.target.checked ? "Membre activé" : "Membre désactivé")} />
                    <span>{m.active ? "Reconnu" : "Ignoré"}</span>
                  </label>
                </div>
                <button className="icon-btn danger" aria-label={`Supprimer ${m.name}`} title="Supprimer" onClick={() => setToDelete(m)}><Trash2 size={16} /></button>
              </li>
            ))}
          </ul>
        )}
        <p className="muted small">Un visage reconnu affiche « BONJOUR » sur l'écran du boîtier et atténue le score de menace, comme un badge valide. Un visage inconnu affiche « INTRU DÉTECTÉ » et déclenche une alerte avec capture.</p>
      </Panel>
      <Panel title="Ajouter un membre">
        <form className="team-form" onSubmit={async (e) => {
          e.preventDefault();
          if (!photo) { toast("Choisissez une photo.", "err"); return; }
          setBusy(true);
          if (await act(() => api.createMember({ name, photo }), `${name.trim()} ajouté à l'équipe`)) { setName(""); setPhoto(null); }
          setBusy(false);
        }}>
          <label className="team-drop">
            {photo ? <img src={photo} alt="Aperçu de la photo" /> : <><ImagePlus size={28} /><span>Photo de face</span></>}
            <input type="file" accept="image/*" capture="user" onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) shrinkPhoto(file).then(setPhoto).catch((err) => toast(errMsg(err), "err"));
            }} />
          </label>
          <div className="team-fields">
            <label className="field"><span>Prénom</span>
              <input required maxLength={32} value={name} onChange={(e) => setName(e.target.value)} /></label>
            <p className="muted small">Une seule personne sur la photo, de face, bien éclairée, sans lunettes de soleil ni casquette. Seuls une miniature et l'empreinte du visage sont conservées.</p>
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Analyse du visage…" : "Ajouter à l'équipe"}</button>
          </div>
        </form>
      </Panel>
      <Confirm open={!!toDelete} title={`Supprimer ${toDelete?.name} ?`} body="Son visage ne sera plus reconnu : la caméra le signalera comme intrus."
        confirmLabel="Supprimer" danger onClose={() => setToDelete(null)}
        onConfirm={async () => { await api.deleteMember(toDelete!.id); toast("Membre supprimé"); load(); }} />
    </>
  );
}

// ---------------------------------------------------------------- Badges
/** « Lire un badge » : le backend écoute le lecteur 30 s ; l'UID du prochain badge passé remplit le formulaire. */
function BadgeReader({ onRead }: { onRead: (uid: string) => void }) {
  const toast = useToast();
  const [state, setState] = useState<BadgeEnrollState | null>(null);
  const [now, setNow] = useState(Date.now());
  const listening = !!state?.listening;
  const onReadRef = useRef(onRead);
  onReadRef.current = onRead;
  useEffect(() => {
    if (!listening) return;
    const t = setInterval(async () => {
      setNow(Date.now());
      try {
        const s = await api.getBadgeEnroll();
        setState(s);
        if (s.uid) {
          onReadRef.current(s.uid);
          toast(s.owner ? `Badge ${s.uid} déjà enregistré (${s.owner})` : `Badge ${s.uid} lu`, s.owner ? "err" : undefined);
        } else if (!s.listening) toast("Aucun badge passé : lecture arrêtée.", "err");
      } catch (e) { toast(errMsg(e), "err"); setState(null); }
    }, 700);
    return () => clearInterval(t);
  }, [listening, toast]);
  useEffect(() => () => { api.stopBadgeEnroll().catch(() => {}); }, []);  // onglet quitté : on arrête l'écoute
  const left = state?.until ? Math.max(0, Math.ceil((Date.parse(state.until) - now) / 1000)) : 0;
  return (
    <div className={`badge-reader${listening ? " is-listening" : ""}`}>
      <span className="badge-reader-icon"><Nfc size={22} /></span>
      <div>
        <strong>{listening ? "Passez le badge devant le lecteur…" : "Lire un badge sur le boîtier"}</strong>
        <span className="muted small">{listening ? `Écoute en cours, ${left} s restantes. Le badge ne sera ni accepté ni refusé.` : "Son UID remplit le formulaire, il ne reste qu'à choisir le titulaire."}</span>
      </div>
      {listening
        ? <button className="btn" type="button" onClick={async () => { await api.stopBadgeEnroll(); setState(null); }}>Annuler</button>
        : <button className="btn btn-primary" type="button" onClick={async () => {
            try { setNow(Date.now()); setState(await api.startBadgeEnroll()); } catch (e) { toast(errMsg(e), "err"); }
          }}>Lire un badge</button>}
    </div>
  );
}

function BadgesTab() {
  const toast = useToast();
  const [badges, setBadges] = useState<Badge[] | null>(null);
  const [form, setForm] = useState({ uid: "", owner: "" });
  const [toDelete, setToDelete] = useState<Badge | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const ownerRef = useRef<HTMLInputElement>(null);
  useEffect(() => { api.getUsers().then(setUsers).catch(() => setUsers([])); }, []);
  const load = useCallback(() => api.getBadges().then(setBadges).catch((e) => toast(errMsg(e), "err")), [toast]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast(ok); load(); return true; } catch (e) { toast(errMsg(e), "err"); return false; }
  };
  return (
    <>
      <Panel title="Badges autorisés à désarmer">
        {!badges ? <Loading /> : badges.length === 0 ? <Empty>Aucun badge enregistré.</Empty> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>UID</th><th>Titulaire</th><th>Statut</th><th>Dernière utilisation</th><th /></tr></thead>
              <tbody>
                {badges.map((b) => (
                  <tr key={b.id}>
                    <td className="tabular">{b.uid}</td>
                    <td>{b.owner}</td>
                    <td>
                      <label className="switch">
                        <input type="checkbox" checked={b.active}
                          onChange={(e) => act(() => api.updateBadge(b.id, { active: e.target.checked }), e.target.checked ? "Badge activé" : "Badge désactivé")} />
                        <span>{b.active ? "Actif" : "Désactivé"}</span>
                      </label>
                    </td>
                    <td>{ago(b.lastUsed)}</td>
                    <td className="num">
                      <button className="icon-btn danger" aria-label={`Supprimer le badge ${b.uid}`} title="Supprimer" onClick={() => setToDelete(b)}><Trash2 size={16} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">Les badges MIFARE Classic sont clonables : un badge seul ne doit jamais suffire à couper la surveillance sans trace. Chaque désarmement par badge est journalisé et notifié.</p>
      </Panel>
      <Panel title="Enregistrer un badge">
        <BadgeReader onRead={(uid) => { setForm((f) => ({ ...f, uid })); ownerRef.current?.focus(); }} />
        <form className="form-row" onSubmit={async (e) => {
          e.preventDefault();
          if (await act(() => api.createBadge(form), "Badge enregistré")) setForm({ uid: "", owner: "" });
        }}>
          <label className="field"><span>UID</span>
            <input required placeholder="04:A3:1F:6B" value={form.uid} onChange={(e) => setForm({ ...form, uid: e.target.value })} className="tabular" /></label>
          <label className="field field-grow"><span>Titulaire (compte ou nom)</span>
            <input ref={ownerRef} required list="badge-owners" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} />
            <datalist id="badge-owners">{users.map((u) => <option key={u.id} value={u.username} />)}</datalist></label>
          <button className="btn btn-primary" type="submit">Enregistrer le badge</button>
        </form>
      </Panel>
      <Confirm open={!!toDelete} title={`Supprimer le badge ${toDelete?.uid} ?`} body="Ce badge ne pourra plus armer ni désarmer le système."
        confirmLabel="Supprimer" danger onClose={() => setToDelete(null)}
        onConfirm={async () => { await api.deleteBadge(toDelete!.id); toast("Badge supprimé"); load(); }} />
    </>
  );
}

// ---------------------------------------------------------------- Détection
const WEIGHT_LABEL: Record<keyof Settings["weights"], string> = {
  pir: "Mouvement PIR", proximite: "Objet à moins de 50 cm", vision: "Détection de la caméra",
  choc: "Choc ou déplacement du boîtier", capot: "Capot ouvert", muet: "Boîtier muet",
  anomalie: "Anomalie environnementale", badgeRefuse: "Badge refusé", masque: "Caméra masquée",
};
const DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function DetectionTab() {
  const toast = useToast();
  const [s, setS] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.getSettings().then(setS).catch((e) => toast(errMsg(e), "err")); }, [toast]);
  if (!s) return <Loading />;
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const example = Math.round((s.weights.pir + s.weights.vision) * s.armedMultiplier);
  const exLevel = example >= s.thresholds.critique ? "Critique" : example >= s.thresholds.alerte ? "Alerte" : "Calme";
  const save = async () => {
    setSaving(true);
    try { setS(await api.saveSettings(s)); toast("Paramètres enregistrés"); }
    catch (e) { toast(errMsg(e), "err"); }
    finally { setSaving(false); }
  };
  return (
    <>
      <Panel title="Points par signal">
        <div className="weights">
          {(Object.keys(WEIGHT_LABEL) as (keyof Settings["weights"])[]).map((k) => (
            <label key={k} className="weight">
              <span>{WEIGHT_LABEL[k]}</span>
              <input type="number" min={0} max={200} value={s.weights[k]}
                onChange={(e) => setS({ ...s, weights: { ...s.weights, [k]: num(e.target.value) } })} />
            </label>
          ))}
        </div>
        <p className="muted small">Les points des signaux reçus sur 60 secondes s'additionnent pour former le score de menace.</p>
      </Panel>

      <div className="grid">
        <Panel title="Niveaux et majoration" className="span-6">
          <div className="form-col">
            <label className="field"><span>Seuil Alerte (score)</span>
              <input type="number" min={1} value={s.thresholds.alerte} onChange={(e) => setS({ ...s, thresholds: { ...s.thresholds, alerte: num(e.target.value) } })} /></label>
            <label className="field"><span>Seuil Critique (score)</span>
              <input type="number" min={1} value={s.thresholds.critique} onChange={(e) => setS({ ...s, thresholds: { ...s.thresholds, critique: num(e.target.value) } })} /></label>
            <label className="field"><span>Majoration si armé ou hors horaires</span>
              <input type="number" min={1} max={5} step={0.1} value={s.armedMultiplier} onChange={(e) => setS({ ...s, armedMultiplier: num(e.target.value) })} /></label>
          </div>
          <p className="example">Exemple : mouvement PIR et mouvement devant la caméra la nuit donnent un score de <strong>{example}</strong>, soit le niveau <strong>{exLevel}</strong>.</p>
        </Panel>

        <Panel title="Horaires et conservation" className="span-6">
          <div className="form-col">
            <div className="form-row">
              <label className="field"><span>Occupation normale de</span>
                <input type="time" value={s.occupancy.start} onChange={(e) => setS({ ...s, occupancy: { ...s.occupancy, start: e.target.value } })} /></label>
              <label className="field"><span>à</span>
                <input type="time" value={s.occupancy.end} onChange={(e) => setS({ ...s, occupancy: { ...s.occupancy, end: e.target.value } })} /></label>
            </div>
            <div className="chips" role="group" aria-label="Jours d'occupation">
              {DAYS.map((d, i) => {
                const n = i + 1, on = s.occupancy.days.includes(n);
                return <button key={d} type="button" className={on ? "chip on" : "chip"} aria-pressed={on}
                  onClick={() => setS({ ...s, occupancy: { ...s.occupancy, days: on ? s.occupancy.days.filter((x) => x !== n) : [...s.occupancy.days, n].sort() } })}>{d}</button>;
              })}
            </div>
            <label className="field"><span>Durée d'ouverture du flux après la dernière détection (secondes)</span>
              <input type="number" min={5} max={300} value={s.cameraUnlockSeconds} onChange={(e) => setS({ ...s, cameraUnlockSeconds: num(e.target.value) })} /></label>
            <label className="field"><span>Conservation des mesures et captures (jours)</span>
              <input type="number" min={1} max={365} value={s.retentionDays} onChange={(e) => setS({ ...s, retentionDays: num(e.target.value) })} /></label>
          </div>
        </Panel>
      </div>
      <div className="save-bar">
        <button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? "Enregistrement…" : "Enregistrer les paramètres"}</button>
      </div>
    </>
  );
}
