import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Lock, Unlock } from "lucide-react";
import { api } from "../api";
import { FaceBanner } from "../components/FaceBanner";
import { useAuth, useLive, useToast } from "../store";
import { Confirm, Empty, Loading, Panel } from "../components/ui";
import { LEVEL_LABEL, ago, fmtDateTime, overrideLeftS } from "../util";
import type { Alert } from "../types";

// Flux simulé : uniquement en mode démo. La condition doit porter directement sur import.meta.env
// (remplacé à la compilation) pour que le bundler élimine ce chunk du build live.
const MockFeed = import.meta.env.VITE_API_MODE !== "live" ? lazy(() => import("../api/MockFeed")) : () => null;

export default function Camera() {
  const { state, alerts } = useLive();
  const { can } = useAuth();
  const toast = useToast();
  const [askOverride, setAskOverride] = useState(false);
  const [zoom, setZoom] = useState<Alert | null>(null);
  const [, force] = useState(0);
  useEffect(() => { const t = setInterval(() => force((n) => n + 1), 1000); return () => clearInterval(t); }, []);

  if (!state) return <Loading />;
  const c = state.camera;
  const overrideLeft = overrideLeftS(c);
  const open = c.detectionActive || overrideLeft > 0;
  const captures = alerts.filter((a) => a.snapshotUrl);

  return (
    <div className="stack">
      <FaceBanner face={c.lastFace} />
      <Panel title="Flux en direct" icon="camera" tone={open ? "crit" : undefined}
        action={open ? <span className="live-pill">{overrideLeft > 0 ? `accès forcé, ${overrideLeft} s restantes` : "détection en cours"}</span> : undefined}>
        {!c.online ? (
          <div className="cam-locked"><Lock size={36} /><strong>Caméra hors ligne</strong><span>Dernière détection {ago(c.lastDetection?.ts)}. Vérifiez l'alimentation de l'ESP32-CAM.</span></div>
        ) : open ? (
          <div className="feed">
            <span className="feed-live">En direct</span>
            {api.streamUrl()
              ? <LiveStream url={api.streamUrl()!} />
              : <Suspense fallback={null}><MockFeed /></Suspense>}
          </div>
        ) : (
          <div className="cam-locked">
            <Lock size={36} aria-hidden="true" />
            <strong>Flux verrouillé : aucun mouvement détecté</strong>
            <span>Pour limiter la surveillance des personnes, le flux ne s'ouvre que pendant une détection. Il apparaîtra ici automatiquement.</span>
            {can("admin") && (
              <button className="btn" onClick={() => setAskOverride(true)}><Unlock size={16} />Forcer l'accès 60 secondes</button>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Captures liées aux alertes">
        {captures.length === 0 ? <Empty>Aucune capture. Une image est enregistrée à chaque mouvement détecté devant la caméra.</Empty> : (
          <div className="captures">
            {captures.map((a) => (
              <button key={a.id} className="capture" onClick={() => setZoom(a)}>
                <img src={a.snapshotUrl!} alt={`Capture de l'alerte ${a.title} du ${fmtDateTime(a.ts)}`} />
                <span><span className={`lvl lvl-${a.level}`}>{LEVEL_LABEL[a.level]}</span>{fmtDateTime(a.ts)}</span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      <Confirm open={askOverride} title="Forcer l'accès à la caméra"
        body="Le flux sera visible pendant 60 secondes sans détection. Votre identifiant, l'heure et le motif sont inscrits au journal d'audit."
        requireReason={{ label: "Motif de l'accès", min: 10 }}
        confirmLabel="Ouvrir le flux" onClose={() => setAskOverride(false)}
        onConfirm={async (reason) => { await api.cameraOverride(reason); toast("Accès caméra ouvert pour 60 s", "warn"); }} />

      <ZoomDialog alert={zoom} onClose={() => setZoom(null)} />
    </div>
  );
}

function ZoomDialog({ alert, onClose }: { alert: Alert | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (alert && !d.open) d.showModal();
    if (!alert && d.open) d.close();
  }, [alert]);
  return (
    <dialog ref={ref} className="dialog dialog-wide" onClose={onClose}>
      {alert && (
        <>
          <h2>{alert.title}, {fmtDateTime(alert.ts)}</h2>
          <img className="zoom-img" src={alert.snapshotUrl!} alt={`Capture de l'alerte ${alert.title}`} />
          <p className="muted small">{alert.reasons.join(", ")}</p>
          <div className="dialog-actions">
            <a className="btn" href={alert.snapshotUrl!} download={`capture-${alert.id}.jpg`}>Télécharger</a>
            <button className="btn btn-primary" onClick={onClose}>Fermer</button>
          </div>
        </>
      )}
    </dialog>
  );
}

const RETRY_MS = 2000;

/**
 * Flux MJPEG qui se reconnecte seul : une balise <img> en erreur (caméra pas encore joignable,
 * service vision redémarré) ne réessaie jamais d'elle-même. Un paramètre change à chaque essai
 * pour forcer une nouvelle requête.
 */
function LiveStream({ url }: { url: string }) {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!failed) return;
    const t = setTimeout(() => { setFailed(false); setAttempt((n) => n + 1); }, RETRY_MS);
    return () => clearTimeout(t);
  }, [failed]);
  const src = attempt ? `${url}${url.includes("?") ? "&" : "?"}r=${attempt}` : url;
  return (
    <>
      <img key={attempt} src={src} alt="Flux vidéo annoté de la salle serveur" onError={() => setFailed(true)} />
      {failed && <span className="feed-retry">Reconnexion au flux…</span>}
    </>
  );
}
