import { Canvas } from "@react-three/fiber";
import { View } from "@react-three/drei";
import { BoxSentinel, Icon3D, Logo3D, type BoxState, type IconKind, type Tone } from "./Objects";

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

export function BoxSlot({ state, className }: { state: BoxState; className?: string }) {
  return <View className={`slot3d ${className ?? ""}`}><BoxSentinel state={state} /></View>;
}
