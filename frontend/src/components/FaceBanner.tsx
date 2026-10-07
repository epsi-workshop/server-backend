import { ScanFace, ShieldAlert } from "lucide-react";
import type { FaceSighting } from "../types";
import { ago } from "../util";

const RECENT_MS = 60_000;

/** Bandeau du dernier visage vu, affiché pendant une minute : « Bonjour Léa » ou « Intrus détecté ». */
export function FaceBanner({ face }: { face: FaceSighting | null | undefined }) {
  if (!face || Date.now() - Date.parse(face.ts) > RECENT_MS) return null;
  return (
    <div className={`face-banner ${face.known ? "is-known" : "is-intruder"}`} role={face.known ? "status" : "alert"}>
      {face.snapshotUrl && <img src={face.snapshotUrl} alt={face.known ? `Capture de ${face.name}` : "Capture de l'intrus"} />}
      <span className="face-banner-icon">{face.known ? <ScanFace size={22} /> : <ShieldAlert size={22} />}</span>
      <div>
        <strong>{face.known ? `Bonjour ${face.name}` : "Intrus détecté"}</strong>
        <span>{face.known ? `Visage reconnu (${Math.round(face.confidence * 100)} %)` : "Visage inconnu devant la caméra"} · {ago(face.ts)}</span>
      </div>
    </div>
  );
}
