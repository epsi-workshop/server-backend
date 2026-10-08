// Mode démo : simule le boîtier, le backend et ses règles (scoring, droits, journaux)
// entièrement dans le navigateur. Activé par VITE_API_MODE=mock.
import type { Api } from "./client";
import { ApiError, notifyUnauthorized } from "./client";
import { hasRole } from "../util";
import type {
  Alert, AuditEntry, Badge, TeamMember, HistoryRange, HistorySensor, LiveMessage, LogEntry, LogLevel, LogSource,
  Point, RestartRequest, RestartTarget, Role, ServiceHealth, Settings, SystemState, ThreatLevel, User,
} from "../types";
import { captureDataUrl, type SceneOpts } from "./mockScene";

const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR;
const iso = (t = Date.now()) => new Date(t).toISOString();
const wait = (ms = 120) => new Promise<void>((r) => setTimeout(r, ms));
let seq = 1;
const uid = (p: string) => `${p}-${(seq++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const round1 = (n: number) => Math.round(n * 10) / 10;

// ---------------------------------------------------------------- référentiels
const users: (User & { password: string })[] = [
  { id: "u1", username: "admin", role: "admin", active: true, lastLogin: iso(Date.now() - 2 * HOUR), mustChangePassword: false, password: "demo" },
  { id: "u2", username: "operateur", role: "operateur", active: true, lastLogin: iso(Date.now() - 5 * HOUR), mustChangePassword: false, password: "demo" },
  { id: "u3", username: "lecteur", role: "lecteur", active: true, lastLogin: iso(Date.now() - 2 * DAY), mustChangePassword: false, password: "demo" },
];

const team: TeamMember[] = [];

const badges: Badge[] = [
  { id: "b1", uid: "04:A3:1F:6B", owner: "Équipe infra", active: true, lastUsed: iso(Date.now() - 3 * HOUR) },
  { id: "b2", uid: "04:7C:E2:19", owner: "Responsable de salle", active: true, lastUsed: null },
  { id: "b3", uid: "04:11:9D:C0", owner: "Ancien prestataire", active: false, lastUsed: iso(Date.now() - 20 * DAY) },
];

let settings: Settings = {
  weights: { pir: 20, proximite: 20, anomalie: 30, vision: 40, choc: 40, muet: 50, capot: 60, badgeRefuse: 30, masque: 50 },
  thresholds: { alerte: 30, critique: 70 },
  armedMultiplier: 1.5,
  occupancy: { start: "08:00", end: "19:00", days: [1, 2, 3, 4, 5] },
  cameraUnlockSeconds: 300,
  retentionDays: 30,
};

const services: ServiceHealth[] = [
  { name: "caddy", target: null, status: "ok", uptimeS: 2 * 86400 + 3600, cpu: 0.4, memMb: 28, version: "2.8" },
  { name: "mosquitto", target: "mosquitto", status: "ok", uptimeS: 2 * 86400 + 3500, cpu: 0.6, memMb: 9, version: "2.0" },
  { name: "backend", target: "backend", status: "ok", uptimeS: 86400 + 1200, cpu: 3.1, memMb: 142, version: "0.1.0" },
  { name: "vision", target: "vision", status: "ok", uptimeS: 86400 + 1100, cpu: 38, memMb: 910, version: "0.1.0" },
  { name: "anomaly", target: "anomaly", status: "ok", uptimeS: 86400 + 1100, cpu: 1.2, memMb: 210, version: "0.1.0" },
  { name: "db (TimescaleDB)", target: null, status: "ok", uptimeS: 2 * 86400 + 3600, cpu: 1.8, memMb: 320, version: "pg16" },
  { name: "API capteurs (talos.local:8000)", target: null, status: "ok", uptimeS: 86400 + 900, cpu: 0, memMb: 0, version: "0.2.0" },
  { name: "ntfy", target: null, status: "ok", uptimeS: 2 * 86400 + 3600, cpu: 0.1, memMb: 18, version: "2.11" },
];

// ---------------------------------------------------------------- session
const SESSION_KEY = "sx-demo-session";
let session: User | null = null;
try {
  const name = localStorage.getItem(SESSION_KEY);
  const u = users.find((x) => x.username === name && x.active);
  if (u) session = strip(u);
} catch { /* stockage indisponible */ }

function strip(u: User & { password?: string }): User {
  const { password: _p, ...rest } = u;
  void _p;
  return { ...rest };
}
function need(role: Role) {
  if (!session) { notifyUnauthorized(); throw new ApiError(401, "Session expirée, reconnectez-vous."); }
  if (!hasRole(session.role, role)) throw new ApiError(403, "Action réservée au rôle " + role + ".");
}

// ---------------------------------------------------------------- état du boîtier
const now0 = Date.now();
const state: SystemState = {
  device: { id: "box01", online: true, armed: true, lastHeartbeat: iso(), uptimeS: 3 * 3600 + 412, rssi: -58, firmware: "sx-uno-q 0.1.0" },
  threat: { score: 0, level: "info", reasons: [] },
  sensors: {
    temperature: { value: 22.6, ts: iso() },
    humidity: { value: 41.2, ts: iso() },
    pir: { active: false, lastTriggered: iso(now0 - 47 * MIN), countLastHour: 2 },
    distance: { cm: 192, ts: iso() },
    imu: { accelG: 1.0, tiltDeg: 0.4, shock: false, lastShock: null },
    lid: { open: false, lastChange: iso(now0 - 3 * DAY) },
    rfid: { lastUid: "04:A3:1F:6B", lastName: "Équipe infra", accepted: true, ts: iso(now0 - 3 * HOUR) },
  },
  camera: { online: true, detectionActive: false, lastDetection: null, overrideUntil: null, masked: false },
  anomaly: { score: 0.08, isAnomaly: false, projectedTemp15: 22.6, features: [] },
};

const logs: LogEntry[] = [];
const audit: AuditEntry[] = [];
let alerts: Alert[] = [];
const listeners = new Set<(m: LiveMessage) => void>();
const emit = (m: LiveMessage) => listeners.forEach((l) => l(m));
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

function log(level: LogLevel, source: LogSource, message: string, ts = Date.now()) {
  const e: LogEntry = { id: uid("log"), ts: iso(ts), level, source, message };
  logs.unshift(e);
  if (logs.length > 1000) logs.length = 1000;
  emit({ type: "log", data: e });
}
function auditAdd(action: string, success = true, user = session?.username ?? "inconnu", ts = Date.now()) {
  audit.unshift({ id: uid("aud"), ts: iso(ts), user, action, ip: "192.168.50.104", success });
}

// ---------------------------------------------------------------- historique initial
(function seed() {
  const t = Date.now();
  const seedLogs: [number, LogLevel, LogSource, string][] = [
    [6 * HOUR, "info", "backend", "Démarrage du backend, connexion MQTT établie (TLS, certificat backend)"],
    [6 * HOUR - 40_000, "info", "vision", "Service vision démarré (YOLO11n, ONNX, CPU)"],
    [6 * HOUR - 35_000, "info", "anomaly", "Modèle Isolation Forest chargé (entraîné sur 4 jours de mesures)"],
    [5 * HOUR, "info", "auth", "Connexion réussie : operateur"],
    [4 * HOUR + 20 * MIN, "warn", "auth", "Échec de connexion : admin (mot de passe incorrect)"],
    [4 * HOUR + 19 * MIN, "info", "auth", "Connexion réussie : admin"],
    [3 * HOUR, "info", "boitier", "Badge accepté : Équipe infra (04:A3:1F:6B)"],
    [3 * HOUR - 30_000, "info", "admin", "Système désarmé par badge"],
    [2 * HOUR + 10 * MIN, "info", "admin", "Système armé par operateur"],
    [2 * HOUR, "warn", "backend", "Message rejeté : numéro de séquence déjà reçu (rejeu possible), box01"],
    [95 * MIN, "error", "backend", "Connexion MQTT refusée : certificat client non signé par la CA"],
    [80 * MIN, "info", "camera", "Flux caméra reconnecté (RSSI -61 dBm)"],
    [47 * MIN, "info", "boitier", "Mouvement détecté (PIR), aucune personne confirmée"],
    [40 * MIN, "warn", "boitier", "Badge refusé : UID inconnu 04:5E:88:D2"],
    [40 * MIN - 2000, "warn", "backend", "Alerte créée : Badge refusé (score 45)"],
    [40 * MIN - 1500, "info", "backend", "Notification push envoyée (ntfy, niveau alerte)"],
    [12 * MIN, "info", "anomaly", "Réentraînement planifié terminé, 0 anomalie sur les 24 dernières heures"],
  ];
  seedLogs.forEach(([ago, lvl, src, msg]) => log(lvl, src, msg, t - ago));
  logs.sort((a, b) => b.ts.localeCompare(a.ts));

  const seedAudit: [number, string, string, boolean][] = [
    [5 * HOUR, "operateur", "Connexion", true],
    [4 * HOUR + 20 * MIN, "admin", "Connexion", false],
    [4 * HOUR + 19 * MIN, "admin", "Connexion", true],
    [4 * HOUR, "admin", "Paramètres de détection modifiés (seuil critique 70)", true],
    [2 * HOUR + 10 * MIN, "operateur", "Système armé", true],
    [35 * MIN, "operateur", "Alerte acquittée : Badge refusé", true],
  ];
  seedAudit.forEach(([ago, user, action, ok]) => auditAdd(action, ok, user, t - ago));

  const y = new Date(t - DAY);
  y.setHours(2, 14, 0, 0);
  alerts = [
    {
      id: uid("al"), ts: iso(t - 40 * MIN), level: "alerte", score: 45, title: "Badge refusé",
      reasons: ["Badge refusé (+30)", "Hors horaires ou armé (× 1,5)"], snapshotUrl: null,
      status: "acquittee", ackBy: "operateur", ackAt: iso(t - 35 * MIN), comment: "Badge d'un stagiaire pas encore enregistré.",
    },
    {
      id: uid("al"), ts: iso(t - 9 * HOUR), level: "alerte", score: 36, title: "Anomalie environnementale",
      reasons: ["Anomalie environnementale (+30)", "Température projetée 27,4 °C"], snapshotUrl: null,
      status: "acquittee", ackBy: "admin", ackAt: iso(t - 8.8 * HOUR), comment: "Climatisation coupée 10 min pour maintenance.",
    },
    {
      id: uid("al"), ts: y.toISOString(), level: "critique", score: 120, title: "Intrusion détectée",
      reasons: ["Mouvement PIR (+20)", "Objet à moins de 50 cm (+20)", "Personne confirmée par la caméra (+40)", "Hors horaires ou armé (× 1,5)"],
      snapshotUrl: captureDataUrl(0.45, 0.91, y.getTime()),
      status: "acquittee", ackBy: "operateur", ackAt: iso(y.getTime() + 7 * MIN), comment: "Agent d'entretien hors planning, vérifié par téléphone.",
    },
  ];
})();

// ---------------------------------------------------------------- simulation
type Signal = keyof Settings["weights"];
const SIGNAL_LABEL: Record<Signal, string> = {
  pir: "Mouvement PIR", proximite: "Objet à moins de 50 cm", anomalie: "Anomalie environnementale",
  vision: "Personne confirmée par la caméra", choc: "Choc ou déplacement du boîtier", muet: "Boîtier muet",
  capot: "Capot ouvert", badgeRefuse: "Badge refusé", masque: "Caméra masquée",
};
let signals: { kind: Signal; ts: number }[] = [];
const addSignal = (kind: Signal) => signals.push({ kind, ts: Date.now() });
let validBadgeTs = 0;
let lastLevel: ThreatLevel = "info";
const tempHistory: number[] = [];
let pirEvents: number[] = [now0 - 47 * MIN, now0 - 52 * MIN];

let scenario: { name: string; step: number } | null = null;
let cooldown = 4;
const person = { visible: false, x: 0.1, conf: 0.88 };
let offlineTicks = 0;

function inOccupancy(t = new Date()): boolean {
  const day = ((t.getDay() + 6) % 7) + 1;
  const hm = t.toTimeString().slice(0, 5);
  return settings.occupancy.days.includes(day) && hm >= settings.occupancy.start && hm < settings.occupancy.end;
}

function computeThreat() {
  const t = Date.now();
  signals = signals.filter((s) => t - s.ts < 60_000);
  const kinds = new Set<Signal>(signals.map((s) => s.kind));
  if (state.sensors.lid.open) kinds.add("capot");
  if (!state.device.online) kinds.add("muet");
  if (state.anomaly.isAnomaly) kinds.add("anomalie");
  if (state.camera.masked) kinds.add("masque");
  let base = 0;
  const reasons: string[] = [];
  kinds.forEach((k) => {
    base += settings.weights[k];
    reasons.push(`${SIGNAL_LABEL[k]} (+${settings.weights[k]})`);
  });
  let mult = 1;
  if (base > 0 && (state.device.armed || !inOccupancy())) {
    mult *= settings.armedMultiplier;
    reasons.push(`Hors horaires ou armé (× ${String(settings.armedMultiplier).replace(".", ",")})`);
  }
  if (base > 0 && t - validBadgeTs < 2 * MIN) {
    mult *= 0.3;
    reasons.push("Badge valide présenté récemment (× 0,3)");
  }
  const score = Math.round(base * mult);
  const level: ThreatLevel = score >= settings.thresholds.critique ? "critique" : score >= settings.thresholds.alerte ? "alerte" : "info";
  state.threat = { score, level, reasons };
  return kinds;
}

const LEVEL_RANK: Record<ThreatLevel, number> = { info: 0, alerte: 1, critique: 2 };
const TITLES: [Signal[], string, number][] = [
  [["vision"], "Intrusion détectée", 6],
  [["capot", "choc", "masque"], "Sabotage du boîtier", 5],
  [["pir", "proximite"], "Présence détectée", 4],
  [["muet"], "Boîtier muet", 3],
  [["badgeRefuse"], "Badge refusé", 2],
  [["anomalie"], "Anomalie environnementale", 1],
];
function titleFor(kinds: Set<Signal>): { title: string; prio: number } {
  for (const [sig, title, prio] of TITLES) if (sig.some((k) => kinds.has(k))) return { title, prio };
  return { title: "Activité inhabituelle", prio: 0 };
}
const prioOf = (title: string) => TITLES.find((t) => t[1] === title)?.[2] ?? 0;

function maybeAlert(kinds: Set<Signal>) {
  const lvl = state.threat.level;
  if (lvl !== "info") {
    const { title, prio } = titleFor(kinds);
    // Une alerte ouverte depuis moins de 90 s est mise à jour (escalade) plutôt que dupliquée.
    const recent = alerts.find((a) => a.status === "ouverte" && Date.now() - Date.parse(a.ts) < 90_000);
    if (recent) {
      const up = LEVEL_RANK[lvl] > LEVEL_RANK[recent.level];
      const better = prio > prioOf(recent.title);
      const snap = kinds.has("vision") && !recent.snapshotUrl;
      if (up || better || snap) {
        if (up) recent.level = lvl;
        if (better) recent.title = title;
        if (state.threat.score > recent.score) { recent.score = state.threat.score; recent.reasons = [...state.threat.reasons]; }
        if (snap) recent.snapshotUrl = captureDataUrl(person.x, person.conf);
        emit({ type: "alert", data: clone(recent) });
        if (up || better) {
          log(lvl === "critique" ? "critical" : "warn", "backend", `Alerte escaladée : ${recent.title} (score ${recent.score})`);
          if (up) log("info", "backend", `Notification push envoyée (ntfy, niveau ${lvl})`);
          if (up && lvl === "critique" && state.device.armed) log("info", "boitier", "Buzzer déclenché");
        }
      }
    } else if (LEVEL_RANK[lvl] > LEVEL_RANK[lastLevel]) {
      const a: Alert = {
        id: uid("al"), ts: iso(), level: lvl, score: state.threat.score, title, reasons: [...state.threat.reasons],
        snapshotUrl: kinds.has("vision") ? captureDataUrl(person.x, person.conf) : null,
        status: "ouverte", ackBy: null, ackAt: null, comment: null,
      };
      alerts.unshift(a);
      emit({ type: "alert", data: a });
      log(lvl === "critique" ? "critical" : "warn", "backend", `Alerte créée : ${title} (score ${a.score})`);
      log("info", "backend", `Notification push envoyée (ntfy, niveau ${lvl})`);
      if (lvl === "critique" && state.device.armed) log("info", "boitier", "Buzzer déclenché");
    }
  }
  lastLevel = lvl;
}

function runScenario() {
  if (!scenario) return;
  const s = scenario;
  const sen = state.sensors;
  const t = Date.now();
  switch (s.name) {
    case "intrusion": {
      if (s.step <= 9) {
        sen.pir.active = true;
        if (s.step === 0) {
          sen.pir.lastTriggered = iso(); pirEvents.push(t); addSignal("pir");
          log("info", "boitier", "Mouvement détecté (PIR)");
        }
      }
      if (s.step === 1) sen.distance.cm = 128;
      if (s.step >= 2 && s.step <= 8) {
        sen.distance.cm = Math.round(rand(42, 68));
        addSignal("proximite");
        if (s.step === 2) log("info", "boitier", `Objet à ${sen.distance.cm} cm du boîtier`);
      }
      if (s.step >= 3 && s.step <= 9) {
        person.visible = true;
        person.x = Math.min(0.9, 0.1 + (s.step - 3) * 0.12);
        person.conf = round1(rand(0.82, 0.95) * 100) / 100;
        state.camera.lastDetection = { ts: iso(), confidence: person.conf };
        addSignal("vision");
        if (s.step === 3) log("warn", "vision", `Personne détectée (confiance ${Math.round(person.conf * 100)} %), capture enregistrée`);
      }
      if (s.step === 10) { person.visible = false; sen.pir.active = false; sen.distance.cm = 190; }
      if (s.step >= 14) scenario = null;
      break;
    }
    case "derive": {
      if (s.step < 14) sen.temperature.value = round1(sen.temperature.value + 0.22);
      else sen.temperature.value = round1(Math.max(22.6, sen.temperature.value - 0.35));
      if (s.step === 5) log("warn", "anomaly", "Dérive de température détectée, projection au-dessus de 26 °C dans 15 min");
      if (s.step >= 24) scenario = null;
      break;
    }
    case "badgeOk": {
      const b = badges.find((x) => x.id === "b1")!;
      b.lastUsed = iso();
      sen.rfid = { lastUid: b.uid, lastName: b.owner, accepted: true, ts: iso() };
      validBadgeTs = t;
      log("info", "boitier", `Badge accepté : ${b.owner} (${b.uid})`);
      scenario = null;
      break;
    }
    case "badgeRefuse": {
      sen.rfid = { lastUid: "04:5E:88:D2", lastName: null, accepted: false, ts: iso() };
      addSignal("badgeRefuse");
      log("warn", "boitier", "Badge refusé : UID inconnu 04:5E:88:D2");
      scenario = null;
      break;
    }
    case "sabotage": {
      if (s.step === 0) {
        sen.imu = { accelG: 2.4, tiltDeg: 14, shock: true, lastShock: iso() };
        addSignal("choc");
        log("critical", "boitier", "Choc détecté sur le boîtier (2,4 g, inclinaison 14°)");
      }
      if (s.step === 1) {
        sen.lid = { open: true, lastChange: iso() };
        log("critical", "boitier", "Capot du boîtier ouvert");
      }
      if (s.step === 2) sen.imu = { ...sen.imu, accelG: 1.0, tiltDeg: 1.2, shock: false };
      if (s.step === 5) {
        sen.lid = { open: false, lastChange: iso() };
        log("info", "boitier", "Capot du boîtier refermé");
      }
      if (s.step >= 7) scenario = null;
      break;
    }
  }
  if (scenario) scenario.step++;
}

function pickScenario(): string {
  const r = Math.random();
  return r < 0.4 ? "intrusion" : r < 0.6 ? "derive" : r < 0.75 ? "badgeOk" : r < 0.9 ? "badgeRefuse" : "sabotage";
}

function tick() {
  const t = Date.now();
  const sen = state.sensors;

  if (offlineTicks > 0) {
    offlineTicks--;
    if (offlineTicks === 0) {
      state.device.online = true;
      state.device.uptimeS = 0;
      log("info", "boitier", "Boîtier reconnecté au broker (TLS, certificat box01)");
    }
  }

  if (state.device.online) {
    if (!scenario || scenario.name !== "derive") {
      sen.temperature.value = round1(sen.temperature.value + (22.6 - sen.temperature.value) * 0.15 + rand(-0.06, 0.06));
    }
    sen.humidity.value = round1(Math.min(55, Math.max(32, sen.humidity.value + rand(-0.25, 0.25))));
    if (!scenario || scenario.name !== "intrusion") sen.distance.cm = Math.round(rand(186, 196));
    sen.pir.active = scenario?.name === "intrusion" ? sen.pir.active : false;
    sen.temperature.ts = sen.humidity.ts = sen.distance.ts = iso();
    state.device.lastHeartbeat = iso();
    state.device.uptimeS += 2;
    state.device.rssi = Math.round(rand(-62, -55));
  }

  // détection d'anomalies : pente sur ~20 s projetée à 15 min
  tempHistory.push(sen.temperature.value);
  if (tempHistory.length > 10) tempHistory.shift();
  const avg = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
  const slopePerTick = tempHistory.length >= 8
    ? (avg(tempHistory.slice(-3)) - avg(tempHistory.slice(0, 3))) / (tempHistory.length - 3)
    : 0;
  const projected = round1(sen.temperature.value + Math.max(-2, Math.min(6, slopePerTick * 18)));
  const dev = Math.abs(sen.temperature.value - 22.6) + Math.max(0, projected - sen.temperature.value);
  const score = Math.min(1, round1(0.05 + dev / 3) );
  const isAnomaly = score >= 0.6;
  state.anomaly = {
    score, isAnomaly, projectedTemp15: projected,
    features: isAnomaly ? ["variation de température sur 5 min", "écart à la moyenne horaire"] : [],
  };

  pirEvents = pirEvents.filter((p) => t - p < HOUR);
  sen.pir.countLastHour = pirEvents.length;

  if (scenario) runScenario();
  else if (--cooldown <= 0) {
    scenario = { name: pickScenario(), step: 0 };
    cooldown = Math.round(rand(14, 26));
    runScenario();
  }
  if (!scenario || scenario.name !== "intrusion") person.visible = false;

  const lastDet = state.camera.lastDetection ? Date.parse(state.camera.lastDetection.ts) : 0;
  if (state.camera.overrideUntil && Date.parse(state.camera.overrideUntil) < t) state.camera.overrideUntil = null;
  state.camera.detectionActive = t - lastDet < settings.cameraUnlockSeconds * 1000;

  services.forEach((s) => { if (s.status === "ok") s.uptimeS += 2; });

  const kinds = computeThreat();
  maybeAlert(kinds);
  emit({ type: "state", data: clone(state) });
}

const RESTART_ORDER: RestartTarget[] = ["box", "camera", "vision", "anomaly", "mosquitto", "backend"];
function restartOne(target: RestartRequest) {
  if (target === "all") { RESTART_ORDER.forEach(restartOne); return; }
  if (target === "box") {
    state.device.online = false;
    offlineTicks = 4;
    log("warn", "boitier", "Boîtier hors ligne (redémarrage en cours)");
  } else if (target === "camera") {
    state.camera.online = false;
    setTimeout(() => { state.camera.online = true; log("info", "camera", "Caméra reconnectée"); }, 6000);
  } else {
    const s = services.find((x) => x.target === target);
    if (s) {
      s.status = "arrete";
      setTimeout(() => { s.status = "ok"; s.uptimeS = 0; log("info", target === "mosquitto" ? "backend" : (target as LogSource), `Service ${s.name} redémarré`); }, 3500);
    }
  }
}

let timer: ReturnType<typeof setInterval> | null = null;

export function getMockScene(): SceneOpts {
  return { person: person.visible, personX: person.x, confidence: person.conf, masked: state.camera.masked };
}

// ---------------------------------------------------------------- historique
const RANGE_MS: Record<HistoryRange, number> = { "1h": HOUR, "6h": 6 * HOUR, "24h": DAY, "7d": 7 * DAY };
function series(sensor: HistorySensor, range: HistoryRange): Point[] {
  const span = RANGE_MS[range], n = 144, t1 = Date.now();
  const pts: Point[] = [];
  for (let i = 0; i < n; i++) {
    const ts = t1 - span + (span * i) / (n - 1);
    const h = new Date(ts).getHours() + new Date(ts).getMinutes() / 60;
    let v: number;
    if (sensor === "temperature") v = 22.4 + 0.7 * Math.sin(((h - 9) / 24) * 2 * Math.PI) + rand(-0.12, 0.12);
    else if (sensor === "humidity") v = 42 - 3 * Math.sin(((h - 9) / 24) * 2 * Math.PI) + rand(-0.5, 0.5);
    else v = Math.random() < 0.03 ? rand(45, 120) : rand(186, 196);
    pts.push({ ts: iso(ts), value: round1(v) });
  }
  const cur = sensor === "temperature" ? state.sensors.temperature.value : sensor === "humidity" ? state.sensors.humidity.value : state.sensors.distance.cm;
  pts[pts.length - 1] = { ts: iso(t1), value: cur };
  return pts;
}

// ---------------------------------------------------------------- API
export const mockApi: Api = {
  mode: "mock",
  async login(username, password) {
    await wait(350);
    const u = users.find((x) => x.username === username.trim());
    if (!u || u.password !== password || !u.active) {
      log("warn", "auth", `Échec de connexion : ${username || "(vide)"}`);
      auditAdd("Connexion", false, username || "(vide)");
      throw new ApiError(401, "Identifiant ou mot de passe incorrect.");
    }
    u.lastLogin = iso();
    session = strip(u);
    try { localStorage.setItem(SESSION_KEY, u.username); } catch { /* ignoré */ }
    log("info", "auth", `Connexion réussie : ${u.username}`);
    auditAdd("Connexion", true, u.username);
    return session;
  },
  async logout() {
    if (session) auditAdd("Déconnexion");
    session = null;
    try { localStorage.removeItem(SESSION_KEY); } catch { /* ignoré */ }
  },
  async me() { await wait(60); return session; },
  async changeOwnPassword(current, password) {
    need("lecteur"); await wait();
    const u = users.find((x) => x.id === session!.id)!;
    if (u.password !== current) throw new ApiError(403, "Mot de passe actuel incorrect.");
    if (password.length < 12) throw new ApiError(422, "Mot de passe : 12 caractères minimum.");
    if (password === current) throw new ApiError(422, "Le nouveau mot de passe doit être différent de l'actuel.");
    u.password = password;
    u.mustChangePassword = false;
    session = strip(u);
    auditAdd("Mot de passe personnel modifié");
    return session;
  },

  async getState() { need("lecteur"); await wait(); computeThreat(); return clone(state); },
  async getHistory(sensor, range) { need("lecteur"); await wait(200); return series(sensor, range); },
  subscribe(onMessage, onStatus) {
    listeners.add(onMessage);
    onStatus(true);
    if (!timer) timer = setInterval(tick, 2000);
    return () => {
      listeners.delete(onMessage);
      if (listeners.size === 0 && timer) { clearInterval(timer); timer = null; }
    };
  },

  async getAlerts() { need("lecteur"); await wait(); return clone(alerts); },
  async ackAlert(id, comment) {
    need("operateur");
    await wait();
    const a = alerts.find((x) => x.id === id);
    if (!a) throw new ApiError(404, "Alerte introuvable.");
    if (!comment.trim()) throw new ApiError(422, "Un commentaire est obligatoire pour acquitter.");
    Object.assign(a, { status: "acquittee", ackBy: session!.username, ackAt: iso(), comment: comment.trim() });
    auditAdd(`Alerte acquittée : ${a.title}`);
    log("info", "admin", `Alerte acquittée par ${session!.username} : ${a.title}`);
    return clone(a);
  },

  async getLogs(f) {
    need("operateur");
    await wait();
    const q = f.q?.toLowerCase().trim();
    return logs.filter((l) =>
      (!f.sources?.length || f.sources.includes(l.source)) &&
      (!f.levels?.length || f.levels.includes(l.level)) &&
      (!q || l.message.toLowerCase().includes(q))).slice(0, 500);
  },
  async getAudit() { need("admin"); await wait(); return clone(audit); },

  async arm() {
    need("operateur"); await wait();
    state.device.armed = true;
    auditAdd("Système armé"); log("info", "admin", `Système armé par ${session!.username}`);
    emit({ type: "state", data: clone(state) });
  },
  async disarm() {
    need("operateur"); await wait();
    state.device.armed = false;
    auditAdd("Système désarmé"); log("info", "admin", `Système désarmé par ${session!.username}`);
    emit({ type: "state", data: clone(state) });
  },
  async buzzer(on) {
    need("operateur"); await wait();
    auditAdd(on ? "Test du buzzer" : "Arrêt du buzzer");
    log("info", "boitier", on ? "Buzzer activé depuis le dashboard" : "Buzzer arrêté depuis le dashboard");
  },
  async restart(target) {
    need("admin"); await wait(400);
    auditAdd(`Redémarrage demandé : ${target}`);
    log("warn", "admin", `Redémarrage demandé par ${session!.username} : ${target}`);
    restartOne(target);
  },
  async cameraOverride(reason) {
    need("admin"); await wait();
    if (reason.trim().length < 10) throw new ApiError(422, "Motif trop court : 10 caractères minimum.");
    state.camera.overrideUntil = iso(Date.now() + 60_000);
    auditAdd(`Accès caméra forcé (60 s) : ${reason.trim()}`);
    log("warn", "admin", `Accès caméra forcé par ${session!.username} : ${reason.trim()}`);
    emit({ type: "state", data: clone(state) });
  },
  streamUrl: () => null,

  async getServices() { need("admin"); await wait(); return clone(services); },
  async getUsers() { need("admin"); await wait(); return users.map(strip); },
  async createUser(u) {
    need("admin"); await wait();
    if (!/^[a-z0-9._-]{3,32}$/.test(u.username)) throw new ApiError(422, "Identifiant : 3 à 32 caractères parmi a-z, 0-9, . _ -");
    if (users.some((x) => x.username === u.username)) throw new ApiError(409, "Cet identifiant existe déjà.");
    if (u.password.length < 12) throw new ApiError(422, "Mot de passe : 12 caractères minimum.");
    const nu = { id: uid("u"), username: u.username, role: u.role, active: true, lastLogin: null, mustChangePassword: true, password: u.password };
    users.push(nu);
    auditAdd(`Utilisateur créé : ${u.username} (${u.role})`);
    return strip(nu);
  },
  async updateUser(id, p) {
    need("admin"); await wait();
    const u = users.find((x) => x.id === id);
    if (!u) throw new ApiError(404, "Utilisateur introuvable.");
    if (u.username === session!.username && (p.role && p.role !== "admin" || p.active === false))
      throw new ApiError(409, "Vous ne pouvez pas retirer vos propres droits d'administration.");
    Object.assign(u, p);
    auditAdd(`Utilisateur modifié : ${u.username} ${p.role ? `rôle ${p.role}` : ""}${p.active !== undefined ? (p.active ? "activé" : "désactivé") : ""}`);
    return strip(u);
  },
  async resetPassword(id, password) {
    need("admin"); await wait();
    const u = users.find((x) => x.id === id);
    if (!u) throw new ApiError(404, "Utilisateur introuvable.");
    if (password.length < 12) throw new ApiError(422, "Mot de passe : 12 caractères minimum.");
    u.password = password;
    u.mustChangePassword = true;
    auditAdd(`Mot de passe réinitialisé : ${u.username}`);
  },
  async deleteUser(id) {
    need("admin"); await wait();
    const u = users.find((x) => x.id === id);
    if (!u) throw new ApiError(404, "Utilisateur introuvable.");
    if (u.username === session!.username) throw new ApiError(409, "Vous ne pouvez pas supprimer votre propre compte.");
    users.splice(users.indexOf(u), 1);
    auditAdd(`Utilisateur supprimé : ${u.username}`);
  },

  async getBadges() { need("admin"); await wait(); return clone(badges); },
  async createBadge(b) {
    need("admin"); await wait();
    const norm = b.uid.trim().toUpperCase();
    if (!/^([0-9A-F]{2}:){3,6}[0-9A-F]{2}$/.test(norm)) throw new ApiError(422, "UID attendu au format 04:A3:1F:6B.");
    if (badges.some((x) => x.uid === norm)) throw new ApiError(409, "Ce badge est déjà enregistré.");
    const nb: Badge = { id: uid("b"), uid: norm, owner: b.owner.trim() || "Sans titulaire", active: true, lastUsed: null };
    badges.push(nb);
    auditAdd(`Badge ajouté : ${nb.uid} (${nb.owner})`);
    return clone(nb);
  },
  async updateBadge(id, p) {
    need("admin"); await wait();
    const b = badges.find((x) => x.id === id);
    if (!b) throw new ApiError(404, "Badge introuvable.");
    Object.assign(b, p);
    auditAdd(`Badge modifié : ${b.uid}${p.active !== undefined ? (p.active ? " activé" : " désactivé") : ""}`);
    return clone(b);
  },
  async deleteBadge(id) {
    need("admin"); await wait();
    const b = badges.find((x) => x.id === id);
    if (!b) throw new ApiError(404, "Badge introuvable.");
    badges.splice(badges.indexOf(b), 1);
    auditAdd(`Badge supprimé : ${b.uid}`);
  },

  async getTeam() { need("admin"); await wait(); return clone(team); },
  async createMember(m) {
    need("admin"); await wait();
    if (!m.name.trim()) throw new ApiError(422, "Prénom requis.");
    const nm: TeamMember = { id: uid("m"), name: m.name.trim(), photo: m.photo, active: true, createdAt: iso(), lastSeen: null };
    team.push(nm);
    auditAdd(`Membre de l'équipe ajouté : ${nm.name}`);
    return clone(nm);
  },
  async updateMember(id, p) {
    need("admin"); await wait();
    const m = team.find((x) => x.id === id);
    if (!m) throw new ApiError(404, "Membre introuvable.");
    Object.assign(m, p);
    auditAdd(`Membre modifié : ${m.name}`);
    return clone(m);
  },
  async deleteMember(id) {
    need("admin"); await wait();
    const m = team.find((x) => x.id === id);
    if (!m) throw new ApiError(404, "Membre introuvable.");
    team.splice(team.indexOf(m), 1);
    auditAdd(`Membre de l'équipe supprimé : ${m.name}`);
  },

  async getSettings() { need("admin"); await wait(); return clone(settings); },
  async saveSettings(s) {
    need("admin"); await wait();
    if (s.thresholds.alerte >= s.thresholds.critique) throw new ApiError(422, "Le seuil Alerte doit être inférieur au seuil Critique.");
    settings = clone(s);
    auditAdd(`Paramètres de détection modifiés (alerte ${s.thresholds.alerte}, critique ${s.thresholds.critique})`);
    log("info", "admin", `Paramètres de détection modifiés par ${session!.username}`);
    return clone(settings);
  },
};
