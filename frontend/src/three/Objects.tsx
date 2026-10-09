import { useMemo, useRef, type ReactNode } from "react";
import { useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import { MOTION, PALETTE, STATE_COLOR } from "./threat";
import { Pumpkin } from "./Pumpkin";

/**
 * Objets 3D de l'interface, en finition « studio » : céramique émaillée, métal brossé, feuillage mat.
 * Les reflets viennent d'un environnement généré localement (Lightformer), sans fichier HDR à télécharger.
 * Rendus dans les Views (Views.tsx).
 */

export type IconKind =
  | "temperature" | "humidity" | "camera" | "pir" | "distance"
  | "integrity" | "rfid" | "device" | "anomaly" | "alerts";

export type Tone = "ok" | "warn" | "crit";

// ------------------------------------------------------------------------------------- matériaux

function Ceramic({ color, rough = 0.32 }: { color: string; rough?: number }) {
  return <meshPhysicalMaterial color={color} roughness={rough} clearcoat={1} clearcoatRoughness={0.06} />;
}
function Metal({ color = PALETTE.brass, rough = 0.28 }: { color?: string; rough?: number }) {
  return <meshStandardMaterial color={color} metalness={1} roughness={rough} />;
}
function Glass() {
  return <meshPhysicalMaterial color="#0c0c0e" roughness={0.05} metalness={0.2} clearcoat={1} clearcoatRoughness={0} />;
}

/** Éclairage de studio : grandes boîtes à lumière pour des reflets nets et doux sur la céramique et le métal. */
function Studio({ children, z = 4.4 }: { children: ReactNode; z?: number }) {
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 0.25, z]} fov={34} onUpdate={(c) => c.lookAt(0, 0, 0)} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[3, 4, 5]} intensity={1.6} />
      <directionalLight position={[-4, 1, -2]} intensity={0.6} color="#dfe8ff" />
      <StudioEnvironment />
      <Float speed={1.1 * MOTION} rotationIntensity={0.12 * MOTION} floatIntensity={0.25 * MOTION}>{children}</Float>
    </>
  );
}

export function StudioEnvironment({ resolution = 128 }: { resolution?: number }) {
  return (
    <Environment resolution={resolution} frames={1}>
      <Lightformer form="rect" intensity={3} position={[0, 3, 3]} scale={[6, 1.2, 1]} />
      <Lightformer form="rect" intensity={1.5} position={[-4, 0.5, 1]} rotation-y={Math.PI / 2} scale={[4, 2, 1]} />
      <Lightformer form="rect" intensity={1} position={[4, -0.5, 1]} rotation-y={-Math.PI / 2} scale={[4, 1, 1]} />
      <Lightformer form="ring" intensity={0.8} position={[0, 0, -4]} scale={2} />
    </Environment>
  );
}

function useSpin(speed = 0.35) {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * speed * MOTION; });
  return ref;
}

// ------------------------------------------------------------------------------------- feuille

/** Feuille légèrement creusée et cambrée (base à l'origine, pointe vers +y, longueur 1). */
function useLeafGeometry() {
  return useMemo(() => {
    const s = new THREE.Shape();
    s.moveTo(0, 0);
    s.bezierCurveTo(0.4, 0.2, 0.38, 0.72, 0, 1);
    s.bezierCurveTo(-0.38, 0.72, -0.4, 0.2, 0, 0);
    const g = new THREE.ShapeGeometry(s, 16);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i);
      p.setZ(i, -0.55 * x * x + 0.12 * Math.sin(y * Math.PI)); // creusée en largeur, cambrée en longueur
    }
    g.computeVertexNormals();
    return g;
  }, []);
}

function Leaf({ color = PALETTE.leaf, ...props }: { color?: string } & JSX.IntrinsicElements["group"]) {
  const geom = useLeafGeometry();
  return (
    <group {...props}>
      <mesh geometry={geom}>
        <meshPhysicalMaterial color={color} roughness={0.55} sheen={1} sheenColor="#d8ecd2" sheenRoughness={0.4} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

// ------------------------------------------------------------------------------------- logo

/** Bouclier en métal brossé (même tracé que le logo), une feuille de céramique sauge en son centre. */
export function Logo3D() {
  const spin = useSpin(0.4);
  const shape = useMemo(() => {
    const outline = (k: number) => {
      const s = new THREE.Shape();
      s.moveTo(0, 14 * k);
      s.lineTo(-12 * k, 9 * k);
      s.lineTo(-12 * k, 1 * k);
      s.bezierCurveTo(-12 * k, -6.5 * k, -6.9 * k, -12.4 * k, 0, -14 * k);
      s.bezierCurveTo(6.9 * k, -12.4 * k, 12 * k, -6.5 * k, 12 * k, 1 * k);
      s.lineTo(12 * k, 9 * k);
      s.closePath();
      return s;
    };
    const s = outline(1);
    s.holes.push(outline(0.82) as unknown as THREE.Path);
    return s;
  }, []);
  return (
    <Studio z={4.3}>
      <group ref={spin}>
        <mesh scale={0.075} position={[0, 0, -0.1]}>
          <extrudeGeometry args={[shape, { depth: 2.6, bevelEnabled: true, bevelThickness: 0.7, bevelSize: 0.5, bevelSegments: 6, curveSegments: 32 }]} />
          <Metal color="#d4d0c8" rough={0.22} />
        </mesh>
        <Leaf position={[0, -0.5, 0.05]} scale={[0.75, 0.95, 0.75]} color={PALETTE.sage} />
      </group>
    </Studio>
  );
}

// ------------------------------------------------------------------------------------- icônes des capteurs

export function Icon3D({ kind, tone = "ok", value }: { kind: IconKind; tone?: Tone; value?: number }) {
  const Body = ICONS[kind];
  return <Studio><Body color={STATE_COLOR[tone]} value={value ?? 0.5} /></Studio>;
}

type IconProps = { color: string; value: number };

function Thermometer({ color, value }: IconProps) {
  const spin = useSpin();
  const level = Math.max(0.15, Math.min(1, value));
  return (
    <group ref={spin} rotation={[0, 0, 0.12]}>
      <mesh><capsuleGeometry args={[0.26, 1.4, 12, 32]} /><Ceramic color={PALETTE.ivory} /></mesh>
      <mesh position={[0, 0.82, 0]}><cylinderGeometry args={[0.15, 0.2, 0.12, 32]} /><Metal /></mesh>
      <mesh position={[0, -0.7 + level * 0.7, 0.2]}><capsuleGeometry args={[0.06, level * 1.3, 8, 16]} /><Ceramic color={color} rough={0.2} /></mesh>
      <mesh position={[0, -0.82, 0]}><sphereGeometry args={[0.3, 32, 32]} /><Ceramic color={color} rough={0.2} /></mesh>
    </group>
  );
}

function Droplet({ color }: IconProps) {
  const spin = useSpin(0.3);
  const geom = useMemo(() => {
    const pts: THREE.Vector2[] = [];
    for (let i = 0; i <= 48; i++) {
      const th = (i / 48) * Math.PI;
      pts.push(new THREE.Vector2(0.72 * Math.sin(th) * Math.pow(Math.sin(th / 2), 1.3), Math.cos(th) * 0.95));
    }
    return new THREE.LatheGeometry(pts, 64);
  }, []);
  return (
    <group ref={spin}>
      <mesh geometry={geom}><Ceramic color={PALETTE.water} rough={0.12} /></mesh>
      <mesh position={[0.45, -0.55, 0.3]}><sphereGeometry args={[0.1, 24, 24]} /><Ceramic color={color} /></mesh>
    </group>
  );
}

function Lens({ color }: IconProps) {
  const spin = useSpin(0.3);
  return (
    <group ref={spin}>
      <group rotation={[Math.PI / 2, 0, 0]}>
        <mesh><cylinderGeometry args={[0.66, 0.72, 0.6, 64]} /><Ceramic color={PALETTE.graphite} rough={0.4} /></mesh>
        <mesh position={[0, 0.31, 0]}><cylinderGeometry args={[0.6, 0.6, 0.04, 64]} /><Metal /></mesh>
      </group>
      <mesh position={[0, 0, 0.32]}><circleGeometry args={[0.46, 64]} /><Glass /></mesh>
      <mesh position={[0, 0, 0.33]}><ringGeometry args={[0.2, 0.24, 64]} /><Metal /></mesh>
      <mesh position={[0.5, 0.5, 0.2]}><sphereGeometry args={[0.05, 16, 16]} /><meshBasicMaterial color={color} /></mesh>
    </group>
  );
}

function Dome({ color }: IconProps) {
  const spin = useSpin(0.3);
  return (
    <group ref={spin} position={[0, -0.25, 0]}>
      <mesh><sphereGeometry args={[0.72, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2]} /><meshPhysicalMaterial color={PALETTE.ivory} roughness={0.3} clearcoat={1} flatShading /></mesh>
      <mesh position={[0, -0.08, 0]}><cylinderGeometry args={[0.82, 0.86, 0.16, 64]} /><Ceramic color={PALETTE.graphite} rough={0.45} /></mesh>
      <mesh position={[0, -0.002, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.72, 0.76, 64]} /><Metal /></mesh>
      <mesh position={[0, 0.74, 0]}><sphereGeometry args={[0.08, 24, 24]} /><Ceramic color={color} /></mesh>
    </group>
  );
}

function Sonar({ color }: IconProps) {
  const spin = useSpin(0.3);
  return (
    <group ref={spin}>
      <mesh><boxGeometry args={[1.5, 0.75, 0.12]} /><Ceramic color={PALETTE.ivory} /></mesh>
      {[-0.38, 0.38].map((x) => (
        <group key={x} position={[x, 0, 0.2]} rotation={[Math.PI / 2, 0, 0]}>
          <mesh><cylinderGeometry args={[0.27, 0.27, 0.28, 48]} /><Metal color="#cfcbc3" rough={0.3} /></mesh>
          <mesh position={[0, 0.145, 0]}><cylinderGeometry args={[0.2, 0.2, 0.01, 48]} /><meshStandardMaterial color="#1a1a1c" roughness={0.9} /></mesh>
        </group>
      ))}
      <mesh position={[0, -0.28, 0.07]}><sphereGeometry args={[0.04, 16, 16]} /><meshBasicMaterial color={color} /></mesh>
    </group>
  );
}

function Crate({ color }: IconProps) {
  const spin = useSpin(0.3);
  const lid = useRef<THREE.Group>(null);
  useFrame(({ clock }) => { if (lid.current) lid.current.rotation.x = -Math.abs(Math.sin(clock.elapsedTime * 0.5 * MOTION)) * 0.35; });
  return (
    <group ref={spin} rotation={[0.3, 0, 0]}>
      <mesh position={[0, -0.15, 0]}><boxGeometry args={[1.15, 0.75, 0.95]} /><Ceramic color={PALETTE.ivory} /></mesh>
      <group ref={lid} position={[0, 0.25, -0.48]}>
        <mesh position={[0, 0, 0.48]}><boxGeometry args={[1.2, 0.08, 1]} /><Metal color="#cfcbc3" /></mesh>
      </group>
      <mesh position={[0, -0.15, 0.48]}><boxGeometry args={[0.18, 0.1, 0.02]} /><Ceramic color={color} /></mesh>
    </group>
  );
}

function Card({ color }: IconProps) {
  const spin = useSpin(0.35);
  return (
    <group ref={spin}>
      <mesh><boxGeometry args={[1.3, 0.84, 0.04]} /><Ceramic color={PALETTE.ivory} rough={0.25} /></mesh>
      <mesh position={[-0.34, 0.08, 0.025]}><boxGeometry args={[0.26, 0.2, 0.01]} /><Metal /></mesh>
      <mesh position={[0.28, -0.22, 0.025]}><boxGeometry args={[0.5, 0.05, 0.005]} /><Ceramic color={color} /></mesh>
    </group>
  );
}

function Chip({ color }: IconProps) {
  const spin = useSpin(0.3);
  const pins = useMemo(() => {
    const p: [number, number, number][] = [];
    for (let i = 0; i < 5; i++) {
      const o = -0.44 + i * 0.22;
      p.push([o, 0.74, 0], [o, -0.74, 0], [0.74, o, 0], [-0.74, o, 0]);
    }
    return p;
  }, []);
  return (
    <group ref={spin} rotation={[0.45, 0, 0]}>
      <mesh><boxGeometry args={[1.2, 1.2, 0.16]} /><Ceramic color={PALETTE.graphite} rough={0.4} /></mesh>
      <mesh position={[0, 0, 0.085]}><boxGeometry args={[0.46, 0.46, 0.02]} /><Metal color="#cfcbc3" rough={0.18} /></mesh>
      <mesh position={[0.4, 0.4, 0.09]}><sphereGeometry args={[0.04, 16, 16]} /><meshBasicMaterial color={color} /></mesh>
      {pins.map((pos, i) => (
        <mesh key={i} position={pos} rotation={[0, 0, Math.abs(pos[0]) > 0.7 ? Math.PI / 2 : 0]}><boxGeometry args={[0.06, 0.28, 0.04]} /><Metal /></mesh>
      ))}
    </group>
  );
}

function Knot({ color }: IconProps) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (!ref.current) return;
    ref.current.rotation.x += dt * 0.25 * MOTION;
    ref.current.rotation.y += dt * 0.35 * MOTION;
  });
  return (
    <mesh ref={ref}>
      <torusKnotGeometry args={[0.52, 0.17, 200, 32, 2, 3]} />
      <Ceramic color={color} rough={0.22} />
    </mesh>
  );
}

function Warning({ color }: IconProps) {
  const spin = useSpin(0.35);
  const shape = useMemo(() => {
    const s = new THREE.Shape();
    s.moveTo(0, 0.88); s.lineTo(-0.92, -0.68); s.lineTo(0.92, -0.68); s.closePath();
    return s;
  }, []);
  return (
    <group ref={spin}>
      <mesh position={[0, 0, -0.08]}>
        <extrudeGeometry args={[shape, { depth: 0.14, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.05, bevelSegments: 6 }]} />
        <Ceramic color={PALETTE.ivory} />
      </mesh>
      <mesh position={[0, 0.02, 0.13]}><capsuleGeometry args={[0.055, 0.34, 8, 16]} /><Ceramic color={color} rough={0.2} /></mesh>
      <mesh position={[0, -0.4, 0.13]}><sphereGeometry args={[0.07, 24, 24]} /><Ceramic color={color} rough={0.2} /></mesh>
    </group>
  );
}

const ICONS: Record<IconKind, (p: IconProps) => JSX.Element> = {
  temperature: Thermometer,
  humidity: Droplet,
  camera: Lens,
  pir: Dome,
  distance: Sonar,
  integrity: Crate,
  rfid: Card,
  device: Chip,
  anomaly: Knot,
  alerts: Warning,
};

// ------------------------------------------------------------------------------------- boîtier

export type BoxState = {
  online: boolean; // boîtier joignable
  motion: boolean; // PIR en cours de détection
  cameraLive: boolean; // flux caméra ouvert (détection en cours)
};

/**
 * Le boîtier en direct : citrouille animée. Yeux verts au repos, ambre pendant une détection,
 * rouges quand le flux caméra est ouvert, éteints hors ligne. La tête balaie et les mains
 * s'agitent pendant un mouvement.
 */
export function BoxSentinel({ state }: { state: BoxState }) {
  const glow = state.cameraLive ? STATE_COLOR.crit : state.motion ? STATE_COLOR.warn : undefined;
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 1.6, 5.4]} fov={33} onUpdate={(c) => c.lookAt(0, 0.95, -0.45)} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[3, 5, 4]} intensity={1.7} />
      <directionalLight position={[-4, 2, -2]} intensity={0.5} color="#dfe8ff" />
      <StudioEnvironment resolution={256} />
      <BoxModel state={state} glow={glow} />
      <ContactShadows position={[0, 0.005, -0.45]} opacity={0.55} scale={4} blur={2.4} far={1.6} />
    </>
  );
}

function BoxModel({ state, glow }: { state: BoxState; glow?: string }) {
  // Balayage de la tête par le servo : large pendant une détection, lent au repos.
  const sweep = useRef(0);
  const turn = useRef<THREE.Group>(null);
  useFrame(({ clock }, dt) => {
    const t = clock.elapsedTime * MOTION;
    sweep.current = state.motion ? Math.sin(t * 1.2) * 0.45 : Math.sin(t * 0.3) * 0.12;
    // L'ensemble (citrouille et module électronique) tourne lentement sur lui-même.
    if (turn.current) turn.current.rotation.y += dt * 0.35 * MOTION;
  });
  return (
    // Pivot au centre de l'emprise (citrouille + module derrière).
    <group ref={turn} position={[0, 0, -0.45]}>
      <group position={[0, 0, 0.45]}>
        <Pumpkin glow={glow} glowLevel={state.online ? 1.5 : 0}
          yawRef={sweep} wave={state.motion ? 1 : 0.15} dim={!state.online} />
      </group>
    </group>
  );
}
