import { Link } from "react-router-dom";
import { Lock, Video } from "lucide-react";
import { useLive } from "../store";
import { Dot, Empty, Loading, Panel, Sparkline } from "../components/ui";
import { LEVEL_LABEL, ago, cameraOpen, fmtDuration, fmtNum, overrideLeftS } from "../util";

const DIST_MAX = 250;
const DIST_THRESHOLD = 50;

export default function Overview() {
  const { state, trend, alerts, error } = useLive();
  if (error) return <Empty>Impossible de charger l'état du système : {error}</Empty>;
  if (!state) return <Loading />;
  const { sensors: s, device: d, camera: c, anomaly: an } = state;
  const camOpen = cameraOpen(c);
  const forced = overrideLeftS(c) > 0;
  const distPct = Math.min(100, (s.distance.cm / DIST_MAX) * 100);
  const tooClose = s.distance.cm < DIST_THRESHOLD;
  const rssiTone = d.rssi > -65 ? "ok" : d.rssi > -75 ? "warn" : "crit";

  return (
    <div className="grid">
      <Panel title="Température" className="span-4" tone={an.isAnomaly ? "warn" : undefined}>
        <div className="readout">
          <span className="readout-value">{fmtNum(s.temperature.value)}</span>
          <span className="readout-unit">°C</span>
        </div>
        <Sparkline points={trend.temperature} />
        <dl className="facts">
          <div><dt>Projection à 15 min</dt><dd className={an.projectedTemp15 >= 26 ? "txt-warn" : ""}>{fmtNum(an.projectedTemp15)} °C</dd></div>
          <div><dt>Mesure</dt><dd>{ago(s.temperature.ts)}</dd></div>
        </dl>
      </Panel>

      <Panel title="Humidité" className="span-4">
        <div className="readout">
          <span className="readout-value">{fmtNum(s.humidity.value)}</span>
          <span className="readout-unit">%</span>
        </div>
        <Sparkline points={trend.humidity} />
        <dl className="facts">
          <div><dt>Plage recommandée</dt><dd>40 à 60 %</dd></div>
          <div><dt>Mesure</dt><dd>{ago(s.humidity.ts)}</dd></div>
        </dl>
      </Panel>

      <Panel title="Caméra" className="span-4" tone={camOpen ? "crit" : undefined}
        action={camOpen ? <Link className="btn btn-small btn-primary" to="/camera"><Video size={15} />Voir le flux</Link> : undefined}>
        <div className={`cam-state ${camOpen ? "cam-open" : ""}`}>
          {camOpen ? <Video size={30} aria-hidden="true" /> : <Lock size={30} aria-hidden="true" />}
          <div>
            <strong>{camOpen ? (forced ? "Accès forcé en cours" : "Mouvement détecté") : "Flux verrouillé"}</strong>
            <span>{camOpen ? "Le flux est consultable tant que la détection est active." : "Le flux s'ouvre automatiquement dès qu'un mouvement est détecté devant la caméra."}</span>
          </div>
        </div>
        <dl className="facts">
          <div><dt>État</dt><dd><Dot tone={!c.online ? "crit" : c.masked ? "warn" : "ok"} />{!c.online ? "Hors ligne" : c.masked ? "Objectif masqué" : "En ligne"}</dd></div>
          <div><dt>Dernière détection</dt><dd>{c.lastDetection ? `${ago(c.lastDetection.ts)} (${Math.round(c.lastDetection.confidence * 100)} %)` : "aucune"}</dd></div>
        </dl>
      </Panel>

      <Panel title="Présence (PIR)" className="span-3" tone={s.pir.active ? "warn" : undefined}>
        <div className="big-state">
          <Dot tone={s.pir.active ? "warn" : "ok"} />
          <strong>{s.pir.active ? "Mouvement en cours" : "Aucun mouvement"}</strong>
        </div>
        <dl className="facts">
          <div><dt>Dernier déclenchement</dt><dd>{ago(s.pir.lastTriggered)}</dd></div>
          <div><dt>Sur la dernière heure</dt><dd>{s.pir.countLastHour}</dd></div>
        </dl>
      </Panel>

      <Panel title="Proximité (ultrasons)" className="span-3" tone={tooClose ? "warn" : undefined}>
        <div className="readout readout-small">
          <span className="readout-value">{s.distance.cm}</span>
          <span className="readout-unit">cm</span>
        </div>
        <div className="gauge" role="img" aria-label={`Distance ${s.distance.cm} cm, seuil ${DIST_THRESHOLD} cm`}>
          <div className="gauge-zone" style={{ width: `${(DIST_THRESHOLD / DIST_MAX) * 100}%` }} />
          <div className={`gauge-fill ${tooClose ? "near" : ""}`} style={{ width: `${distPct}%` }} />
        </div>
        <div className="gauge-scale"><span>0</span><span>seuil {DIST_THRESHOLD} cm</span><span>{DIST_MAX} cm</span></div>
      </Panel>

      <Panel title="Intégrité du boîtier" className="span-3" tone={s.lid.open || s.imu.shock ? "crit" : undefined}>
        <dl className="facts facts-tight">
          <div><dt>Capot</dt><dd><Dot tone={s.lid.open ? "crit" : "ok"} />{s.lid.open ? "Ouvert" : "Fermé"}</dd></div>
          <div><dt>Accélération</dt><dd className={s.imu.shock ? "txt-crit" : ""}>{fmtNum(s.imu.accelG, 2)} g</dd></div>
          <div><dt>Inclinaison</dt><dd>{fmtNum(s.imu.tiltDeg)}°</dd></div>
          <div><dt>Dernier choc</dt><dd>{ago(s.imu.lastShock)}</dd></div>
        </dl>
      </Panel>

      <Panel title="Badge (RFID)" className="span-3" tone={s.rfid.accepted === false ? "warn" : undefined}>
        {s.rfid.ts ? (
          <>
            <div className="big-state">
              <Dot tone={s.rfid.accepted ? "ok" : "warn"} />
              <strong>{s.rfid.accepted ? "Badge accepté" : "Badge refusé"}</strong>
            </div>
            <dl className="facts">
              <div><dt>Titulaire</dt><dd>{s.rfid.lastName ?? "inconnu"}</dd></div>
              <div><dt>UID</dt><dd className="tabular">{s.rfid.lastUid}</dd></div>
              <div><dt>Présenté</dt><dd>{ago(s.rfid.ts)}</dd></div>
            </dl>
          </>
        ) : <Empty>Aucun badge présenté.</Empty>}
      </Panel>

      <Panel title="Boîtier" className="span-4" tone={!d.online ? "crit" : undefined}>
        <dl className="facts">
          <div><dt>Connexion</dt><dd><Dot tone={d.online ? "ok" : "crit"} />{d.online ? "En ligne" : "Hors ligne"}</dd></div>
          <div><dt>Dernier heartbeat</dt><dd>{ago(d.lastHeartbeat)}</dd></div>
          <div><dt>Allumé depuis</dt><dd>{fmtDuration(d.uptimeS)}</dd></div>
          <div><dt>Signal Wi-Fi</dt><dd><Dot tone={rssiTone} />{d.rssi} dBm</dd></div>
          <div><dt>Firmware</dt><dd>{d.firmware}</dd></div>
        </dl>
      </Panel>

      <Panel title="Détection d'anomalies" className="span-4" tone={an.isAnomaly ? "warn" : undefined}>
        <div className="big-state">
          <Dot tone={an.isAnomaly ? "warn" : "ok"} />
          <strong>{an.isAnomaly ? "Comportement anormal" : "Comportement normal"}</strong>
        </div>
        <div className="meter" role="img" aria-label={`Score d'anomalie ${Math.round(an.score * 100)} sur 100`}>
          <div className={`meter-fill ${an.isAnomaly ? "warn" : ""}`} style={{ width: `${an.score * 100}%` }} />
          <div className="meter-mark" style={{ left: "60%" }} />
        </div>
        <p className="muted small">
          Score {Math.round(an.score * 100)} / 100, seuil 60.
          {an.features.length > 0 && <> En cause : {an.features.join(", ")}.</>}
        </p>
      </Panel>

      <Panel title="Dernières alertes" className="span-4" action={<Link className="link" to="/alertes">Tout voir</Link>}>
        {alerts.length === 0 ? <Empty>Aucune alerte.</Empty> : (
          <ul className="mini-list">
            {alerts.slice(0, 4).map((a) => (
              <li key={a.id}>
                <span className={`lvl lvl-${a.level}`}>{LEVEL_LABEL[a.level]}</span>
                <span className="mini-title">{a.title}</span>
                <span className="muted small">{ago(a.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
