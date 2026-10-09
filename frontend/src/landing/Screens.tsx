import { useEffect, useState } from "react";
import { Activity, Bell, Camera, LayoutGrid, ScanFace, ShieldAlert, ShieldCheck } from "lucide-react";

/**
 * Contenus HTML projetés dans la scène 3D (Html transform) : écran de reconnaissance faciale,
 * tableau de bord sur ordinateur et sur téléphone. Données de démonstration.
 */

/** Alterne entre un membre de l'équipe reconnu et un visage inconnu. */
function useCycle(ms: number) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const id = window.setInterval(() => setOn((v) => !v), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return on;
}

export function FaceScreen() {
  const intruder = useCycle(3600);
  return (
    <div className={`face-card ${intruder ? "is-intruder" : "is-known"}`}>
      <div className="face-card-head">
        <span className="kicker">Reconnaissance faciale</span>
        <span className="face-live">En direct</span>
      </div>
      <div className="face-view">
        <svg viewBox="0 0 200 220" className="face-svg" aria-hidden="true">
          <path className="face-outline" d="M100 22c-38 0-60 30-60 70 0 30 10 58 26 76 10 11 22 18 34 18s24-7 34-18c16-18 26-46 26-76 0-40-22-70-60-70Z" />
          <path className="face-feature" d="M64 96q14-8 28 0M108 96q14-8 28 0M100 104v30q-6 6 0 8M80 160q20 12 40 0" />
          {FACE_POINTS.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.2" className="face-pt" style={{ animationDelay: `${i * 60}ms` }} />)}
        </svg>
        <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
        <span className="scanline" />
      </div>
      <div className="face-result">
        <span className="face-icon">{intruder ? <ShieldAlert size={26} /> : <ScanFace size={26} />}</span>
        <div>
          <strong>{intruder ? "Visage inconnu" : "Camille D."}</strong>
          <span>{intruder ? "Alerte critique · capture enregistrée" : "Équipe infrastructure · accès autorisé"}</span>
        </div>
        <em>{intruder ? "—" : "96 %"}</em>
      </div>
    </div>
  );
}

const FACE_POINTS: [number, number][] = [
  [64, 96], [78, 92], [92, 96], [108, 96], [122, 92], [136, 96], [100, 104], [100, 120], [96, 140], [104, 140],
  [80, 160], [100, 166], [120, 160], [52, 120], [148, 120], [70, 176], [130, 176], [100, 190], [100, 40], [66, 58], [134, 58],
];

function Spark({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 200 40" preserveAspectRatio="none" className="mini-spark" aria-hidden="true">
      <path d={`${d} L200 40 L0 40 Z`} className="mini-spark-fill" />
      <path d={d} className="mini-spark-line" />
    </svg>
  );
}

const TEMP = "M0 26 L20 24 L40 27 L60 22 L80 23 L100 18 L120 20 L140 16 L160 19 L180 14 L200 15";
const HUM = "M0 18 L20 20 L40 17 L60 21 L80 19 L100 22 L120 20 L140 23 L160 21 L180 24 L200 22";

function Signal({ step }: { step: number }) {
  return <span className="mini-bars">{[1, 2, 3].map((i) => <i key={i} className={i <= step ? "on" : ""} />)}</span>;
}

export function LaptopScreen() {
  return (
    <div className="screen screen-laptop">
      <aside className="scr-side">
        <div className="scr-brand"><b>Sentinel</b><span>Boîtier box01</span></div>
        {[[LayoutGrid, "Vue d'ensemble"], [Camera, "Caméra"], [Activity, "Historique"], [Bell, "Alertes"]].map(([Icon, label], i) => {
          const I = Icon as typeof LayoutGrid;
          return <div key={i} className={`scr-nav ${i === 0 ? "on" : ""}`}><I size={14} />{label as string}</div>;
        })}
      </aside>
      <div className="scr-main">
        <div className="scr-banner">
          <span className="scr-tile"><ShieldCheck size={16} /></span>
          <Signal step={1} />
          <div className="scr-level"><small>Niveau de menace</small><b>Calme</b></div>
          <span className="scr-reason">Aucun signal suspect sur la dernière minute.</span>
          <span className="scr-armed">Armé</span>
        </div>
        <div className="scr-grid">
          <div className="scr-card"><small>Température</small><b>22,4<em>°C</em></b><Spark d={TEMP} /></div>
          <div className="scr-card"><small>Humidité</small><b>47,8<em>%</em></b><Spark d={HUM} /></div>
          <div className="scr-card"><small>Présence (PIR)</small><span className="scr-state"><i className="dot ok" />Aucun mouvement</span><span className="scr-meta">Dernier déclenchement · 14 min</span></div>
          <div className="scr-card"><small>Armement (RFID)</small><span className="scr-state"><i className="dot ok" />Système armé</span><span className="scr-meta">Badge de Camille D. · il y a 2 min</span></div>
          <div className="scr-card"><small>Caméra</small><span className="scr-state"><i className="dot ok" />Flux verrouillé</span><span className="scr-meta">S'ouvre à la détection</span></div>
        </div>
        <div className="scr-row">
          <div className="scr-card scr-chart">
            <small>Score de menace · 24 h</small>
            <svg viewBox="0 0 240 90" preserveAspectRatio="none" aria-hidden="true">
              {[22, 45, 68].map((y) => <line key={y} x1="0" x2="240" y1={y} y2={y} className="grid-line" />)}
              {SCORES.map((v, i) => <rect key={i} x={i * 10 + 2} y={90 - v} width="6" height={v} rx="1.5" className={`bar ${v > 60 ? "crit" : v > 35 ? "warn" : ""}`} />)}
            </svg>
          </div>
          <div className="scr-card">
            <small>Dernières alertes</small>
            <ul className="scr-list">
              <li><span className="lvl crit">Critique</span>Visage inconnu<em>02:14</em></li>
              <li><span className="lvl warn">Alerte</span>Badge refusé<em>02:13</em></li>
              <li><span className="lvl">Info</span>Badge · système désarmé<em>08:02</em></li>
              <li><span className="lvl">Info</span>Système armé<em>08:03</em></li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

const SCORES = [8, 6, 10, 7, 5, 9, 12, 8, 6, 74, 52, 20, 10, 8, 14, 9, 7, 11, 38, 16, 9, 7, 6, 8];

export function PhoneScreen() {
  return (
    <div className="screen screen-phone">
      <div className="ph-status"><span>9:41</span><span className="ph-island" /><span>5G</span></div>
      <div className="ph-head"><b>Sentinel</b><span>box01</span></div>
      <div className="ph-banner">
        <span className="scr-tile warn"><ShieldAlert size={15} /></span>
        <Signal step={2} />
        <div className="scr-level"><small>Niveau de menace</small><b className="warn">Alerte</b></div>
      </div>
      <div className="ph-card"><small>Température</small><b>27,1<em>°C</em></b><Spark d="M0 30 L25 28 L50 27 L75 24 L100 22 L125 18 L150 15 L175 10 L200 8" /></div>
      <div className="ph-card">
        <small>Dernières alertes</small>
        <ul className="ph-alerts">
          <li><span className="lvl warn">Alerte</span>Température en hausse</li>
          <li><span className="lvl">Info</span>Système armé · Camille D.</li>
          <li><span className="lvl crit">Critique</span>Visage inconnu</li>
        </ul>
      </div>
      <div className="ph-tabbar">{[LayoutGrid, Camera, Activity, Bell].map((I, i) => <I key={i} size={16} className={i === 0 ? "on" : ""} />)}</div>
    </div>
  );
}
