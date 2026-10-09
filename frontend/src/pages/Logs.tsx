import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api } from "../api";
import { useAuth, useLive } from "../store";
import { Empty, Loading, Panel, Tabs } from "../components/ui";
import type { AuditEntry, LogEntry, LogLevel, LogSource } from "../types";
import { LOG_LEVEL_LABEL, downloadCsv, errMsg, fmtDateTime } from "../util";

const SOURCES: { id: LogSource; label: string }[] = [
  { id: "boitier", label: "Boîtier" }, { id: "camera", label: "Caméra" }, { id: "vision", label: "Vision" },
  { id: "anomaly", label: "Anomalies" }, { id: "backend", label: "Backend" }, { id: "auth", label: "Connexions" }, { id: "admin", label: "Administration" },
];
const LEVELS: LogLevel[] = ["info", "warn", "error", "critical"];
const srcLabel = (s: LogSource) => SOURCES.find((x) => x.id === s)?.label ?? s;

export default function Logs() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"events" | "audit">("events");
  return (
    <div className="stack">
      <div className="toolbar">
        <h1>Journaux</h1>
        {can("admin") && <Tabs value={tab} onChange={setTab} items={[{ id: "events", label: "Événements" }, { id: "audit", label: "Audit des actions" }]} />}
      </div>
      {tab === "events" ? <Events /> : <Audit />}
    </div>
  );
}

function toggle<T>(arr: T[], v: T): T[] {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}

function Events() {
  const [sources, setSources] = useState<LogSource[]>([]);
  const [levels, setLevels] = useState<LogLevel[]>([]);
  const [q, setQ] = useState("");
  const [follow, setFollow] = useState(true);
  const [rows, setRows] = useState<LogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Suivi en direct : rechargement déclenché par les messages `log` du WebSocket (plus de sondage).
  const { logSeq } = useLive();
  const trigger = follow ? logSeq : 0;
  useEffect(() => {
    let alive = true;
    const load = () => api.getLogs({ sources, levels, q })
      .then((r) => { if (alive) { setRows(r); setError(null); } })
      .catch((e) => alive && setError(errMsg(e)));
    const debounce = setTimeout(load, 300);
    return () => { alive = false; clearTimeout(debounce); };
  }, [sources, levels, q, trigger]);

  const exportCsv = () => rows && downloadCsv(`sentinel-journaux-${new Date().toISOString().slice(0, 19)}.csv`,
    [["horodatage", "niveau", "source", "message"], ...rows.map((r) => [r.ts, r.level, r.source, r.message])]);

  return (
    <Panel title={rows ? `${rows.length} entrée${rows.length > 1 ? "s" : ""}` : "Événements"}
      action={<button className="btn btn-small" onClick={exportCsv} disabled={!rows?.length}><Download size={15} />Exporter en CSV</button>}>
      <div className="filters">
        <input className="search" type="search" placeholder="Rechercher dans les messages" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Rechercher dans les messages" />
        <div className="chips" role="group" aria-label="Filtrer par source">
          {SOURCES.map((s) => (
            <button key={s.id} className={sources.includes(s.id) ? "chip on" : "chip"} aria-pressed={sources.includes(s.id)}
              onClick={() => setSources((v) => toggle(v, s.id))}>{s.label}</button>
          ))}
        </div>
        <div className="chips" role="group" aria-label="Filtrer par niveau">
          {LEVELS.map((l) => (
            <button key={l} className={levels.includes(l) ? `chip on chip-${l}` : `chip chip-${l}`} aria-pressed={levels.includes(l)}
              onClick={() => setLevels((v) => toggle(v, l))}>{LOG_LEVEL_LABEL[l]}</button>
          ))}
        </div>
        <label className="switch">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
          <span>Suivi en direct</span>
        </label>
      </div>
      {error ? <Empty>Impossible de charger les journaux : {error}</Empty> : !rows ? <Loading /> : rows.length === 0 ? (
        <Empty>Aucune entrée ne correspond à ces filtres.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table table-stack stack-last-wide">
            <thead><tr><th>Horodatage</th><th>Niveau</th><th>Source</th><th>Message</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={`row-${r.level}`}>
                  <td className="tabular nowrap">{fmtDateTime(r.ts)}</td>
                  <td><span className={`loglvl loglvl-${r.level}`}>{LOG_LEVEL_LABEL[r.level]}</span></td>
                  <td className="nowrap">{srcLabel(r.source)}</td>
                  <td>{r.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Audit() {
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.getAudit().then(setRows).catch((e) => setError(errMsg(e)));
  }, []);
  const exportCsv = () => rows && downloadCsv(`sentinel-audit-${new Date().toISOString().slice(0, 19)}.csv`,
    [["horodatage", "utilisateur", "action", "ip", "resultat"], ...rows.map((r) => [r.ts, r.user, r.action, r.ip, r.success ? "succes" : "echec"])]);
  return (
    <Panel title="Qui a fait quoi"
      action={<button className="btn btn-small" onClick={exportCsv} disabled={!rows?.length}><Download size={15} />Exporter en CSV</button>}>
      {error ? <Empty>Impossible de charger l'audit : {error}</Empty> : !rows ? <Loading /> : (
        <div className="table-wrap">
          <table className="table table-stack">
            <thead><tr><th>Horodatage</th><th>Utilisateur</th><th>Action</th><th>Adresse IP</th><th>Résultat</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="tabular nowrap">{fmtDateTime(r.ts)}</td>
                  <td>{r.user}</td>
                  <td>{r.action}</td>
                  <td className="tabular">{r.ip}</td>
                  <td>{r.success ? <span className="ok-txt">Succès</span> : <span className="crit-txt">Échec</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
