// Contrat dashboard <-> backend. Toute modification = pull request relue (issue #1).
// Horodatages : chaînes ISO 8601 UTC.

export type Role = "lecteur" | "operateur" | "admin";
export type ThreatLevel = "info" | "alerte" | "critique";
export type LogLevel = "info" | "warn" | "error" | "critical";
export type LogSource = "boitier" | "camera" | "vision" | "anomaly" | "backend" | "auth" | "admin";
export type RestartTarget = "box" | "camera" | "vision" | "anomaly" | "mosquitto" | "backend";
/** "all" : redémarrage complet orchestré par le backend (ordre et reprise sur erreur côté serveur). */
export type RestartRequest = RestartTarget | "all";
export type HistorySensor = "temperature" | "humidity" | "distance";
export type HistoryRange = "1h" | "6h" | "24h" | "7d";

export interface User {
  id: string;
  username: string;
  role: Role;
  active: boolean;
  lastLogin: string | null;
  /** true après création du compte ou réinitialisation par un admin : changement obligatoire. */
  mustChangePassword: boolean;
}

/** État complet du système, renvoyé par GET /api/state et poussé par WS `state`. */
export interface SystemState {
  device: {
    id: string;
    online: boolean;
    armed: boolean;
    lastHeartbeat: string | null;
    uptimeS: number;
    rssi: number; // dBm
    firmware: string;
  };
  threat: { score: number; level: ThreatLevel; reasons: string[] };
  sensors: {
    temperature: { value: number; ts: string };
    humidity: { value: number; ts: string };
    pir: { active: boolean; lastTriggered: string | null; countLastHour: number };
    distance: { cm: number; ts: string };
    imu: { accelG: number; tiltDeg: number; shock: boolean; lastShock: string | null };
    rfid: { lastUid: string | null; lastName: string | null; accepted: boolean | null; ts: string | null };
  };
  camera: {
    online: boolean;
    /** true tant que le PIR détecte un mouvement, et cameraUnlockSeconds après le dernier mouvement. */
    detectionActive: boolean;
    lastDetection: { ts: string; confidence: number } | null;
    /** Dernier visage vu : membre de l'équipe reconnu (name) ou intrus. */
    lastFace?: FaceSighting | null;
    /** Accès forcé par un admin (journalisé), sinon null. */
    overrideUntil: string | null;
    masked: boolean;
  };
  anomaly: { score: number; isAnomaly: boolean; projectedTemp15: number; features: string[] };
}

export interface Alert {
  id: string;
  ts: string;
  level: ThreatLevel;
  score: number;
  title: string;
  reasons: string[];
  snapshotUrl: string | null;
  status: "ouverte" | "acquittee";
  ackBy: string | null;
  ackAt: string | null;
  comment: string | null;
}

export interface LogEntry {
  id: string;
  ts: string;
  level: LogLevel;
  source: LogSource;
  message: string;
}

export interface AuditEntry {
  id: string;
  ts: string;
  user: string;
  action: string;
  ip: string;
  success: boolean;
}

export interface ServiceHealth {
  name: string;
  target: RestartTarget | null;
  status: "ok" | "degrade" | "arrete";
  uptimeS: number;
  cpu: number; // %
  memMb: number;
  version: string;
}

export interface FaceSighting {
  ts: string;
  known: boolean;
  name: string | null;
  confidence: number;
  snapshotUrl: string | null;
}

/** Membre de l'équipe reconnu par la caméra. photo : miniature en data URL. */
export interface TeamMember {
  id: string;
  name: string;
  photo: string;
  active: boolean;
  createdAt: string;
  lastSeen: string | null;
}

/** Enregistrement par lecture : listening tant qu'aucun badge n'a été passé. */
export interface BadgeEnrollState {
  listening: boolean;
  until: string | null;
  uid: string | null;
  /** Titulaire si le badge lu est déjà enregistré. */
  owner: string | null;
}

/** Sortie des sons : haut-parleur du boîtier, enceinte Bluetooth (repli sur le boîtier si absente), les deux, muet. */
export type AudioOutput = "wired" | "bluetooth" | "both" | "off";

/** Sortie sonore et enceinte Bluetooth de l'UNO Q. */
export interface AudioState {
  /** Absent sur une carte pas encore mise à jour (équivaut à « both »). */
  output?: AudioOutput;
  speaker: { mac: string; name: string | null; connected: boolean } | null;
  /** Enceinte connectée et prête à jouer (sortie audio créée). */
  ready: boolean;
  volume: number;
  sounds: string[];
}

export interface BluetoothDevice {
  mac: string;
  name: string;
  paired: boolean;
  connected: boolean;
  /** Appareil capable de jouer du son (enceinte, casque). */
  audio: boolean;
}

export type TestSound = "test" | "ok" | "refused" | "hello" | "siren" | "alarm" | "unknown";

export interface Badge {
  id: string;
  uid: string;
  owner: string;
  active: boolean;
  lastUsed: string | null;
}

export interface Settings {
  weights: Record<
    "pir" | "proximite" | "anomalie" | "vision" | "choc" | "muet" | "badgeRefuse",
    number
  >;
  thresholds: { alerte: number; critique: number };
  armedMultiplier: number;
  occupancy: { start: string; end: string; days: number[] }; // 1 = lundi
  cameraUnlockSeconds: number;
  retentionDays: number;
}

export interface Point {
  ts: string;
  value: number;
}

export interface LogFilter {
  sources?: LogSource[];
  levels?: LogLevel[];
  q?: string;
}

/** Messages poussés sur WS /ws/live */
export type LiveMessage =
  | { type: "state"; data: SystemState }
  | { type: "alert"; data: Alert }
  | { type: "log"; data: LogEntry };
