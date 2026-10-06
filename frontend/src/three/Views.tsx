import { Canvas } from "@react-three/fiber";
import { View } from "@react-three/drei";
import { Icon3D, Logo3D, PotSentinel, ThreatCore, type IconKind, type PotState, type Tone } from "./Objects";
import { STATE_COLOR } from "./threat";

/**
 * Un seul canvas WebGL, au-dessus des panneaux, dans lequel sont dessinés tous les objets 3D de
 * l'interface. Chaque objet est un <View> : un emplacement dans le DOM, suivi au pixel près
 * (défilement, redimensionnement). Un seul contexte WebGL quel que soit le nombre d'objets.
 */
export function ViewsCanvas() {
  return (
    <Canvas className="views-canvas" eventSource={document.getElementById("root")!} dpr={[1, 2]}
      gl={{ alpha: true, antialias: true }} aria-hidden="true">
      <View.Port />
    </Canvas>
  );
}

export function Icon3DSlot({ kind, tone = "ok", value, className }: { kind: IconKind; tone?: Tone; value?: number; className?: string }) {
  return <View className={`slot3d ${className ?? ""}`}><Icon3D kind={kind} tone={tone} value={value} /></View>;
}

export function Logo3DSlot({ className }: { className?: string }) {
  return <View className={`slot3d ${className ?? ""}`}><Logo3D /></View>;
}

export type CoreLevel = "info" | "alerte" | "critique" | "offline";
const CORE_COLOR: Record<CoreLevel, string> = { info: STATE_COLOR.ok, alerte: STATE_COLOR.warn, critique: STATE_COLOR.crit, offline: STATE_COLOR.off };

export function ThreatCoreSlot({ level, className }: { level: CoreLevel; className?: string }) {
  return <View className={`slot3d ${className ?? ""}`}><ThreatCore color={CORE_COLOR[level]} critical={level === "critique"} /></View>;
}

export function PotSlot({ state, className }: { state: PotState; className?: string }) {
  return <View className={`slot3d ${className ?? ""}`}><PotSentinel state={state} /></View>;
}
