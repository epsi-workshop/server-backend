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
    lid: { open: boolean; lastChange: string | null };
    rfid: { lastUid: string | null; lastName: string | null; accepted: boolean | null; ts: string | null };
  };
  camera: {
    online: boolean;
    /** true tant que le PIR détecte un mouvement, et cameraUnlockSeconds après le dernier mouvement. */
    detectionActive: boolean;
    lastDetection: { ts: string; confidence: number } | null;
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

export interface Badge {
  id: string;
  uid: string;
  owner: string;
  active: boolean;
  lastUsed: string | null;
}

export interface Settings {
  weights: Record<
    "pir" | "proximite" | "anomalie" | "vision" | "choc" | "muet" | "capot" | "badgeRefuse",
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
