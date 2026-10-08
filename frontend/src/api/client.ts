import type {
  Alert, AuditEntry, Badge, BadgeEnrollState, TeamMember, HistoryRange, HistorySensor, LiveMessage, LogEntry, LogFilter,
  Point, RestartRequest, ServiceHealth, Settings, SystemState, User,
} from "../types";

/** Tout ce dont le dashboard a besoin. Deux implémentations : mock (démo) et live (backend réel). */
export interface Api {
  readonly mode: "mock" | "live";
  login(username: string, password: string): Promise<User>;
  logout(): Promise<void>;
  me(): Promise<User | null>;
  /** Changement de son propre mot de passe (obligatoire si user.mustChangePassword). */
  changeOwnPassword(current: string, password: string): Promise<User>;

  getState(): Promise<SystemState>;
  getHistory(sensor: HistorySensor, range: HistoryRange): Promise<Point[]>;
  subscribe(onMessage: (msg: LiveMessage) => void, onStatus: (connected: boolean) => void): () => void;

  getAlerts(): Promise<Alert[]>;
  ackAlert(id: string, comment: string): Promise<Alert>;

  getLogs(filter: LogFilter): Promise<LogEntry[]>;
  getAudit(): Promise<AuditEntry[]>;

  arm(): Promise<void>;
  disarm(): Promise<void>;
  buzzer(on: boolean): Promise<void>;
  restart(target: RestartRequest): Promise<void>;
  cameraOverride(reason: string): Promise<void>;
  /** URL du flux MJPEG rediffusé par le serveur ; null en mode démo (flux simulé). */
  streamUrl(): string | null;

  getServices(): Promise<ServiceHealth[]>;
  getUsers(): Promise<User[]>;
  createUser(u: { username: string; role: User["role"]; password: string }): Promise<User>;
  updateUser(id: string, patch: Partial<Pick<User, "role" | "active">>): Promise<User>;
  resetPassword(id: string, password: string): Promise<void>;
  deleteUser(id: string): Promise<void>;

  getBadges(): Promise<Badge[]>;
  createBadge(b: { uid: string; owner: string }): Promise<Badge>;
  updateBadge(id: string, patch: Partial<Pick<Badge, "active" | "owner">>): Promise<Badge>;
  deleteBadge(id: string): Promise<void>;
  /** Lance l'écoute du lecteur : le prochain badge passé est capturé au lieu d'être accepté ou refusé. */
  startBadgeEnroll(): Promise<BadgeEnrollState>;
  getBadgeEnroll(): Promise<BadgeEnrollState>;
  stopBadgeEnroll(): Promise<void>;

  getTeam(): Promise<TeamMember[]>;
  /** photo : image en data URL ; le backend refuse une photo sans visage ou avec plusieurs visages. */
  createMember(m: { name: string; photo: string }): Promise<TeamMember>;
  updateMember(id: string, patch: Partial<Pick<TeamMember, "active" | "name">>): Promise<TeamMember>;
  deleteMember(id: string): Promise<void>;

  getSettings(): Promise<Settings>;
  saveSettings(s: Settings): Promise<Settings>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Session expirée : l'implémentation API le signale, AuthProvider renvoie vers l'écran de connexion.
let unauthorizedHandler: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  unauthorizedHandler = fn;
}
export function notifyUnauthorized() {
  unauthorizedHandler();
}
