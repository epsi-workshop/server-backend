import { Suspense, useMemo, useRef, type ReactNode } from "react";
import { useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer, PerspectiveCamera, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { MOTION, PALETTE, STATE_COLOR } from "./threat";
import potClosedUrl from "../assets/pot-ferme.glb?url";
import potOpenUrl from "../assets/pot-ouvert.glb?url";

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

// ------------------------------------------------------------------------------------- pot sentinelle

export type PotState = {
  online: boolean; // boîtier joignable
  motion: boolean; // PIR en cours de détection
  cameraLive: boolean; // flux caméra ouvert (détection en cours)
  doorOpen: boolean; // porte du pot ouverte (capteur infrarouge)
};

// Modèle réel du boîtier (Blender) : demi-coques, insert, terreau et plante, exporté en glTF,
// en deux versions (porte fermée / porte ouverte) affichées selon le capteur de la porte.
const POT_HEIGHT = 2; // hauteur totale dans la scène, en unités three.js
const VIEW_ANGLE = -0.31; // même angle que le rendu de présentation (caméra à 18° sur la gauche)

/** Le boîtier camouflé, d'après le modèle 3D du pot : porte ouverte ou fermée selon le capteur, lumières d'état discrètes. */
export function PotSentinel({ state }: { state: PotState }) {
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 1.25, 4.4]} fov={33} onUpdate={(c) => c.lookAt(0, 0.82, 0)} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[3, 5, 4]} intensity={1.7} />
      <directionalLight position={[-4, 2, -2]} intensity={0.5} color="#dfe8ff" />
      <StudioEnvironment resolution={256} />
      {/* Détection : lueur ocre sur la façade ; flux en direct : touche rouge dans le feuillage */}
      <pointLight position={[0, 0.6, 1.4]} intensity={state.motion ? 4 : 0} distance={3} color={STATE_COLOR.warn} />
      <pointLight position={[0, 1.7, 0.9]} intensity={state.cameraLive ? 3 : 0} distance={2} color={STATE_COLOR.crit} />
      <Suspense fallback={null}><PotModel url={state.doorOpen ? potOpenUrl : potClosedUrl} dim={!state.online} /></Suspense>
      <ContactShadows position={[0, -0.16, 0]} opacity={0.5} scale={3.2} blur={2.4} far={1.6} />
    </>
  );
}

function PotModel({ url, dim }: { url: string; dim: boolean }) {
  const { scene } = useGLTF(url, false);
  // Porte ouverte face à la caméra : léger balancement autour de cet angle, l'intérieur reste visible.
  const sway = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (sway.current) sway.current.rotation.y = VIEW_ANGLE + Math.sin(clock.elapsedTime * 0.35 * MOTION) * 0.22;
  });
  // Copie mise à l'échelle et posée au sol, axe du pot au centre.
  const model = useMemo(() => {
    const root = scene.clone(true);
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const k = POT_HEIGHT / size.y;
    root.scale.setScalar(k);
    const center = box.getCenter(new THREE.Vector3());
    root.position.set(-center.x * k, -box.min.y * k - 0.15, -center.z * k);
    root.traverse((o) => { if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).castShadow = true; });
    return root;
  }, [scene]);
  // Boîtier hors ligne : légèrement désaturé et assombri.
  useMemo(() => {
    model.traverse((o) => {
      const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
      if (!m || !("color" in m)) return;
      m.userData.base ??= m.color.clone();
      m.color.copy(m.userData.base as THREE.Color);
      if (dim) m.color.lerp(new THREE.Color("#777777"), 0.55);
    });
  }, [model, dim]);
  return <group ref={sway}><primitive object={model} /></group>;
}

useGLTF.preload(potClosedUrl, false);
useGLTF.preload(potOpenUrl, false);
