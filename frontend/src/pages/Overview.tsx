import { Link } from "react-router-dom";
import { Lock, Video } from "lucide-react";
import { useLive } from "../store";
import { Dot, Empty, Loading, Panel, Sparkline } from "../components/ui";
import { LEVEL_LABEL, ago, cameraOpen, fmtDuration, fmtNum, overrideLeftS } from "../util";
import { BoxSlot } from "../three/Views";
import { FaceBanner } from "../components/FaceBanner";

export default function Overview() {
  const { state, trend, alerts, error } = useLive();
  if (error) return <Empty>Impossible de charger l'état du système : {error}</Empty>;
  if (!state) return <Loading />;
  const { sensors: s, device: d, camera: c, anomaly: an } = state;
  const camOpen = cameraOpen(c);
  const forced = overrideLeftS(c) > 0;
  const rssiTone = d.rssi > -65 ? "ok" : d.rssi > -75 ? "warn" : "crit";

  return (
    <div className="grid">
      <FaceBanner face={c.lastFace} />
      <Panel title="Boîtier box01" className="span-4 row-2" tone={!d.online ? "crit" : s.pir.active ? "warn" : undefined}>
        <BoxSlot className="pot-view" state={{ online: d.online, motion: s.pir.active, cameraLive: camOpen}} />
        <p className="pot-caption">Modèle 3D du boîtier · état en direct</p>
        <dl className="facts pot-legend">
          <div><dt>Caméra<small>ESP32-CAM et laser, dans le nez</small></dt><dd><Dot tone={!c.online ? "crit" : camOpen ? "warn" : "ok"} />{!c.online ? "Hors ligne" : camOpen ? "En direct" : "En veille"}</dd></div>
          <div><dt>Capot<small>ouverture du boîtier, capteur infrarouge</small></dt><dd><Dot tone={s.lid.open ? "crit" : "ok"} />{s.lid.open ? "Ouvert" : "Fermé"}</dd></div>
          <div><dt>Détecteur de présence<small>PIR</small></dt><dd><Dot tone={s.pir.active ? "warn" : "ok"} />{s.pir.active ? "Mouvement" : "Calme"}</dd></div>
          <div><dt>Température · humidité<small>DHT22</small></dt><dd>{fmtNum(s.temperature.value)} °C · {fmtNum(s.humidity.value, 0)} %</dd></div>
          <div><dt>Armement<small>badge RFID</small></dt><dd><Dot tone={d.armed ? "ok" : "off"} />{d.armed ? "Armé" : "Désarmé"}</dd></div>
          <div><dt>Contrôleur<small>Arduino UNO Q</small></dt><dd><Dot tone={d.online ? "ok" : "crit"} />{d.online ? `En ligne · ${fmtDuration(d.uptimeS)}` : "Muet"}</dd></div>
        </dl>
      </Panel>

      <Panel title="Température" className="span-4" icon="temperature" iconValue={Math.min(1, Math.max(0, (s.temperature.value - 10) / 30))} tone={an.isAnomaly ? "warn" : undefined}>
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

      <Panel title="Humidité" className="span-4" icon="humidity">
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

      <Panel title="Caméra" className="span-4" icon="camera" tone={camOpen ? "crit" : undefined}
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

      <Panel title="Présence (PIR)" className="span-4" icon="pir" tone={s.pir.active ? "warn" : undefined}>
        <div className="big-state">
          <Dot tone={s.pir.active ? "warn" : "ok"} />
          <strong>{s.pir.active ? "Mouvement en cours" : "Aucun mouvement"}</strong>
        </div>
        <dl className="facts">
          <div><dt>Dernier déclenchement</dt><dd>{ago(s.pir.lastTriggered)}</dd></div>
          <div><dt>Sur la dernière heure</dt><dd>{s.pir.countLastHour}</dd></div>
        </dl>
      </Panel>

      <Panel title="Capot du boîtier" className="span-4" icon="integrity" tone={s.lid.open ? "crit" : undefined}>
        <div className="big-state">
          <Dot tone={s.lid.open ? "crit" : "ok"} />
          <strong>{s.lid.open ? "Capot ouvert" : "Capot fermé"}</strong>
        </div>
        <dl className="facts">
          <div><dt>Capteur</dt><dd>infrarouge</dd></div>
          <div><dt>Dernier changement</dt><dd>{ago(s.lid.lastChange)}</dd></div>
        </dl>
      </Panel>

      <Panel title="Visages" className="span-4" icon="rfid" tone={c.lastFace && !c.lastFace.known ? "crit" : undefined}>
        {c.lastFace ? (
          <>
            <div className="big-state">
              <Dot tone={c.lastFace.known ? "ok" : "crit"} />
              <strong>{c.lastFace.known ? `Bonjour ${c.lastFace.name}` : "Intrus détecté"}</strong>
            </div>
            <dl className="facts">
              <div><dt>Identité</dt><dd>{c.lastFace.known ? c.lastFace.name : "inconnue"}</dd></div>
              <div><dt>{c.lastFace.known ? "Ressemblance" : "Détection"}</dt><dd>{Math.round(c.lastFace.confidence * 100)} %</dd></div>
              <div><dt>Vu</dt><dd>{ago(c.lastFace.ts)}</dd></div>
            </dl>
          </>
        ) : <Empty>Aucun visage vu depuis le démarrage.</Empty>}
      </Panel>

      <Panel title="Armement (badge RFID)" className="span-4" icon="rfid" tone={s.rfid.accepted === false ? "warn" : undefined}>
        {s.rfid.ts ? (
          <>
            <div className="big-state">
              <Dot tone={s.rfid.accepted ? "ok" : "warn"} />
              <strong>{s.rfid.accepted ? (d.armed ? "Système armé" : "Système désarmé") : "Badge refusé"}</strong>
            </div>
            <dl className="facts">
              <div><dt>Titulaire</dt><dd>{s.rfid.lastName ?? "inconnu"}</dd></div>
              <div><dt>UID</dt><dd className="tabular">{s.rfid.lastUid}</dd></div>
              <div><dt>Dernier badge</dt><dd>{ago(s.rfid.ts)}</dd></div>
            </dl>
          </>
        ) : <Empty>Aucun badge présenté.</Empty>}
      </Panel>

      <Panel title="Boîtier" className="span-4" icon="device" tone={!d.online ? "crit" : undefined}>
        <dl className="facts">
          <div><dt>Connexion</dt><dd><Dot tone={d.online ? "ok" : "crit"} />{d.online ? "En ligne" : "Hors ligne"}</dd></div>
          <div><dt>Dernier heartbeat</dt><dd>{ago(d.lastHeartbeat)}</dd></div>
          <div><dt>Allumé depuis</dt><dd>{fmtDuration(d.uptimeS)}</dd></div>
          <div><dt>Signal Wi-Fi</dt><dd><Dot tone={rssiTone} />{d.rssi} dBm</dd></div>
          <div><dt>Firmware</dt><dd>{d.firmware}</dd></div>
        </dl>
      </Panel>

      <Panel title="Détection d'anomalies" className="span-4" icon="anomaly" tone={an.isAnomaly ? "warn" : undefined}>
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

      <Panel title="Dernières alertes" className="span-4" icon="alerts" action={<Link className="link" to="/alertes">Tout voir</Link>}>
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
