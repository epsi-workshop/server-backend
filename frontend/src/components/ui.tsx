import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Point } from "../types";
import { errMsg } from "../util";
import { Icon3DSlot } from "../three/Views";
import type { IconKind } from "../three/Objects";

/** Panneau en verre : coins de visée, icône 3D facultative, inclinaison vers la souris (profondeur). */
/** Panneau à fond plein, icône 3D facultative à gauche du titre. */
export function Panel(props: {
  title: string; action?: ReactNode; children: ReactNode; className?: string; tone?: "ok" | "warn" | "crit";
  icon?: IconKind; iconValue?: number;
}) {
  const iconTone = props.tone === "crit" ? "crit" : props.tone === "warn" ? "warn" : "ok";
  return (
    <section className={`panel ${props.tone ? `panel-${props.tone}` : ""} ${props.className ?? ""}`}>
      <header className="panel-head">
        <div className="panel-title">
          {props.icon && <Icon3DSlot kind={props.icon} tone={iconTone} value={props.iconValue} className="panel-icon" />}
          <h2>{props.title}</h2>
        </div>
        {props.action}
      </header>
      <div className="panel-body">{props.children}</div>
    </section>
  );
}

export function Logo({ size }: { size: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7L16 2Z" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <circle cx="16" cy="15" r="4.2" fill="currentColor" />
    </svg>
  );
}

export function Dot({ tone }: { tone: "ok" | "warn" | "crit" | "off" }) {
  return <span className={`dot dot-${tone}`} aria-hidden="true" />;
}

export function Sparkline({ points, height = 44, className }: { points: Point[]; height?: number; className?: string }) {
  const w = 240;
  if (points.length < 2) return <svg className={`spark ${className ?? ""}`} viewBox={`0 0 ${w} ${height}`} aria-hidden="true" />;
  const vals = points.map((p) => p.value);
  let min = Math.min(...vals), max = Math.max(...vals);
  if (max - min < 0.5) { const m = (max + min) / 2; min = m - 0.25; max = m + 0.25; }
  const x = (i: number) => (i / (points.length - 1)) * w;
  const y = (v: number) => height - 3 - ((v - min) / (max - min)) * (height - 6);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  return (
    <svg className={`spark ${className ?? ""}`} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={`${d} L${w} ${height} L0 ${height} Z`} className="spark-fill" />
      <path d={d} className="spark-line" />
    </svg>
  );
}

export function Tabs<T extends string>(props: { value: T; onChange: (v: T) => void; items: { id: T; label: string }[] }) {
  return (
    <div className="tabs" role="tablist">
      {props.items.map((it) => (
        <button key={it.id} role="tab" aria-selected={props.value === it.id}
          className={props.value === it.id ? "tab tab-on" : "tab"} onClick={() => props.onChange(it.id)}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Loading() {
  return <p className="empty">Chargement…</p>;
}

/** Fenêtre de confirmation pour les actions sensibles. requireText : texte à recopier ; requireReason : motif obligatoire. */
export function Confirm(props: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  requireText?: string;
  requireReason?: { label: string; min: number };
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (props.open && !d.open) { setTyped(""); setReason(""); setErr(null); d.showModal(); }
    if (!props.open && d.open) d.close();
  }, [props.open]);
  const ok = (!props.requireText || typed === props.requireText) && (!props.requireReason || reason.trim().length >= props.requireReason.min);
  const go = async () => {
    setBusy(true); setErr(null);
    try { await props.onConfirm(reason.trim()); props.onClose(); }
    catch (e) { setErr(errMsg(e)); }
    finally { setBusy(false); }
  };
  return (
    <dialog ref={ref} className="dialog" onClose={props.onClose}>
      <h2>{props.title}</h2>
      <div className="dialog-body">{props.body}</div>
      {props.requireReason && (
        <label className="field">
          <span>{props.requireReason.label}</span>
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
          <small>{Math.max(0, props.requireReason.min - reason.trim().length)} caractères minimum restants</small>
        </label>
      )}
      {props.requireText && (
        <label className="field">
          <span>Tapez <strong>{props.requireText}</strong> pour confirmer</span>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </label>
      )}
      {err && <p className="form-error">{err}</p>}
      <div className="dialog-actions">
        <button className="btn" onClick={props.onClose} disabled={busy}>Annuler</button>
        <button className={props.danger ? "btn btn-danger" : "btn btn-primary"} onClick={go} disabled={!ok || busy}>
          {busy ? "En cours…" : props.confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
