import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Empty, Loading, Panel, Tabs } from "../components/ui";
import type { HistoryRange, HistorySensor, Point } from "../types";
import { errMsg, fmtNum, stats } from "../util";

const RANGES: { id: HistoryRange; label: string }[] = [
  { id: "1h", label: "1 heure" }, { id: "6h", label: "6 heures" }, { id: "24h", label: "24 heures" }, { id: "7d", label: "7 jours" },
];

const CHARTS: { sensor: HistorySensor; title: string; unit: string; refs: { y: number; label: string }[]; domain: [number | "auto", number | "auto"] }[] = [
  { sensor: "temperature", title: "Température", unit: "°C", refs: [{ y: 26, label: "26 °C" }], domain: ["auto", "auto"] },
  { sensor: "humidity", title: "Humidité", unit: "%", refs: [{ y: 40, label: "40 %" }, { y: 60, label: "60 %" }], domain: [30, 65] },
  { sensor: "distance", title: "Distance mesurée par les ultrasons", unit: "cm", refs: [{ y: 50, label: "seuil 50 cm" }], domain: [0, 250] },
];

export default function Sensors() {
  const [range, setRange] = useState<HistoryRange>("6h");
  const [data, setData] = useState<Partial<Record<HistorySensor, Point[]>>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      Promise.all(CHARTS.map((c) => api.getHistory(c.sensor, range)))
        .then((res) => { if (alive) { setData(Object.fromEntries(CHARTS.map((c, i) => [c.sensor, res[i]]))); setError(null); } })
        .catch((e) => alive && setError(errMsg(e)));
    setData({});
    load();
    const t = setInterval(load, 30_000);
    return () => { alive = false; clearInterval(t); };
  }, [range]);

  const tick = (ts: string) => {
    const d = new Date(ts);
    return range === "7d"
      ? d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" })
      : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="stack">
      <div className="toolbar">
        <h1>Historique des capteurs</h1>
        <Tabs value={range} onChange={setRange} items={RANGES} />
      </div>
      {error && <Empty>Impossible de charger l'historique : {error}</Empty>}
      {CHARTS.map((c) => {
        const pts = data[c.sensor];
        const st = stats(pts?.map((p) => p.value) ?? []);
        return (
          <Panel key={c.sensor} title={c.title}
            action={st ? <span className="muted small">min {fmtNum(st.min)}, moyenne {fmtNum(st.avg)}, max {fmtNum(st.max)} {c.unit}</span> : undefined}>
            {!pts ? <Loading /> : (
              <div className="chart">
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={pts} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
                    <defs>
                      <linearGradient id={`g-${c.sensor}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.22} />
                        <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="ts" tickFormatter={tick} minTickGap={48} stroke="var(--muted)" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis domain={c.domain} stroke="var(--muted)" fontSize={12} tickLine={false} axisLine={false} width={48}
                      tickFormatter={(v: number) => `${fmtNum(v, 0)}`} />
                    <Tooltip
                      contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, color: "var(--ink)" }}
                      labelFormatter={(ts) => new Date(String(ts)).toLocaleString("fr-FR")}
                      formatter={(v) => [`${fmtNum(Number(v))} ${c.unit}`, c.title]} />
                    {c.refs.map((r) => (
                      <ReferenceLine key={r.y} y={r.y} stroke="var(--warn)" strokeDasharray="4 4"
                        label={{ value: r.label, position: "insideTopRight", fill: "var(--warn)", fontSize: 12 }} />
                    ))}
                    <Area type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={1.8} fill={`url(#g-${c.sensor})`} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </Panel>
        );
      })}
    </div>
  );
}
