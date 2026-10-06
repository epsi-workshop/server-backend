import { useState } from "react";
import { api } from "../api";
import { useAuth, useLive, useToast } from "../store";
import { Empty, Panel, Tabs } from "../components/ui";
import { LEVEL_LABEL, ago, errMsg, fmtDateTime } from "../util";

type Filter = "ouvertes" | "critiques" | "toutes";

export default function Alerts() {
  const { alerts, setAlerts } = useLive();
  const { can } = useAuth();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("ouvertes");
  const [selId, setSelId] = useState<string | null>(null);
  // Un brouillon de commentaire par alerte : changer de sélection ne réutilise pas le texte d'une autre.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const list = alerts.filter((a) =>
    filter === "toutes" ? true : filter === "ouvertes" ? a.status === "ouverte" : a.level === "critique");
  const sel = list.find((a) => a.id === selId) ?? list[0] ?? null;
  const comment = sel ? drafts[sel.id] ?? "" : "";
  const setComment = (v: string) => sel && setDrafts((d) => ({ ...d, [sel.id]: v }));

  const ack = async () => {
    if (!sel) return;
    setBusy(true);
    try {
      const updated = await api.ackAlert(sel.id, comment);
      setAlerts((all) => all.map((a) => (a.id === updated.id ? updated : a)));
      setDrafts(({ [updated.id]: _done, ...rest }) => rest);
      toast("Alerte acquittée");
    } catch (e) {
      toast(errMsg(e), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div className="toolbar">
        <h1>Alertes</h1>
        <Tabs value={filter} onChange={setFilter} items={[
          { id: "ouvertes", label: `Ouvertes (${alerts.filter((a) => a.status === "ouverte").length})` },
          { id: "critiques", label: "Critiques" },
          { id: "toutes", label: "Toutes" },
        ]} />
      </div>
      <div className="split">
        <Panel title={`${list.length} alerte${list.length > 1 ? "s" : ""}`} className="split-list">
          {list.length === 0 ? (
            <Empty>{filter === "ouvertes" ? "Aucune alerte en attente d'acquittement." : "Aucune alerte pour ce filtre."}</Empty>
          ) : (
            <ul className="alert-list">
              {list.map((a) => (
                <li key={a.id}>
                  <button className={sel?.id === a.id ? "alert-row on" : "alert-row"} onClick={() => setSelId(a.id)}>
                    <span className={`lvl lvl-${a.level}`}>{LEVEL_LABEL[a.level]}</span>
                    <span className="alert-title">{a.title}</span>
                    <span className="muted small">{ago(a.ts)}</span>
                    <span className={a.status === "ouverte" ? "status-open" : "status-done"}>{a.status === "ouverte" ? "à traiter" : "acquittée"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Détail" className="split-detail">
          {!sel ? <Empty>Sélectionnez une alerte.</Empty> : (
            <div className="detail">
              <div className="detail-head">
                <span className={`lvl lvl-${sel.level}`}>{LEVEL_LABEL[sel.level]}</span>
                <h3>{sel.title}</h3>
              </div>
              <dl className="facts">
                <div><dt>Date</dt><dd>{fmtDateTime(sel.ts)}</dd></div>
                <div><dt>Score de menace</dt><dd>{sel.score}</dd></div>
              </dl>
              <h4>Pourquoi ce score</h4>
              <ul className="reasons">{sel.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              {sel.snapshotUrl && <img className="detail-img" src={sel.snapshotUrl} alt={`Capture de l'alerte ${sel.title}`} />}
              {sel.status === "acquittee" ? (
                <div className="ack-done">
                  <strong>Acquittée par {sel.ackBy} {ago(sel.ackAt)}</strong>
                  <p>{sel.comment}</p>
                </div>
              ) : can("operateur") ? (
                <div className="ack-form">
                  <label className="field">
                    <span>Commentaire d'acquittement</span>
                    <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)}
                      placeholder="Ce qui a été vérifié et la conclusion" />
                  </label>
                  <button className="btn btn-primary" disabled={!comment.trim() || busy} onClick={ack}>
                    {busy ? "Acquittement…" : "Acquitter l'alerte"}
                  </button>
                </div>
              ) : <p className="muted small">L'acquittement est réservé aux opérateurs.</p>}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
