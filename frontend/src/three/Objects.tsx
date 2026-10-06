import { useMemo, useRef, type ReactNode } from "react";
import { useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import { MOTION, PALETTE, STATE_COLOR } from "./threat";

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

function StudioEnvironment({ resolution = 128 }: { resolution?: number }) {
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

// ------------------------------------------------------------------------------------- galet d'état

/** Galet de céramique émaillée qui respire doucement, couleur = niveau de menace. */
export function ThreatCore({ color, critical }: { color: string; critical: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.elapsedTime * MOTION * (critical ? 3 : 1);
    const k = 1 + Math.sin(t * 1.4) * 0.03;
    ref.current.scale.set(k, 0.8 * k, k);
    ref.current.rotation.y = t * 0.2;
  });
  return (
    <Studio z={3.4}>
      <mesh ref={ref}>
        <sphereGeometry args={[0.85, 64, 64]} />
        <Ceramic color={color} rough={0.25} />
      </mesh>
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
};

const POT_H = 0.9;
const potRadius = (y: number) => 0.5 + (0.74 - 0.5) * (y / POT_H); // pot évasé vers le haut

/** Le boîtier camouflé : pot en céramique émaillée, plante au feuillage mat, capteurs discrets en façade. */
export function PotSentinel({ state }: { state: PotState }) {
  const spin = useSpin(0.22);
  const plant = useRef<THREE.Group>(null);
  const body = useMemo(() => new THREE.LatheGeometry([
    new THREE.Vector2(0.001, 0), new THREE.Vector2(0.46, 0), new THREE.Vector2(0.5, 0.03),
    new THREE.Vector2(potRadius(POT_H), POT_H), new THREE.Vector2(0.8, POT_H + 0.015),
    new THREE.Vector2(0.81, POT_H + 0.08), new THREE.Vector2(0.73, POT_H + 0.09), new THREE.Vector2(0.71, POT_H),
  ], 96), []);
  const stems = useMemo(() => [
    { end: [0.05, 1.9, 0.05], ctrl: [0.22, 1.4, 0], leaf: 0.5, rot: 0.3 },
    { end: [-0.48, 1.62, 0.1], ctrl: [-0.12, 1.3, 0.1], leaf: 0.44, rot: 1.1 },
    { end: [0.5, 1.58, -0.15], ctrl: [0.15, 1.25, -0.1], leaf: 0.44, rot: -1.1 },
    { end: [-0.2, 1.52, -0.46], ctrl: [-0.05, 1.2, -0.2], leaf: 0.4, rot: 0.6 },
    { end: [0.26, 1.46, 0.46], ctrl: [0.1, 1.2, 0.2], leaf: 0.36, rot: -0.5 },
  ].map((s) => {
    const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(0, POT_H, 0),
      new THREE.Vector3(...(s.ctrl as [number, number, number])), new THREE.Vector3(...(s.end as [number, number, number])));
    return { ...s, geom: new THREE.TubeGeometry(curve, 24, 0.016, 8, false), tip: curve.getPoint(1), dir: curve.getTangent(1) };
  }), []);
  useFrame(({ clock }) => {
    if (!plant.current) return;
    const t = clock.elapsedTime * MOTION;
    plant.current.rotation.z = Math.sin(t * 0.6) * 0.025;
    plant.current.rotation.x = Math.sin(t * 0.45) * 0.02;
  });
  const front = (y: number) => potRadius(y) + 0.01;
  const tilt = -Math.atan((0.74 - 0.5) / POT_H); // inclinaison de la paroi
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 1.25, 4.4]} fov={33} onUpdate={(c) => c.lookAt(0, 0.82, 0)} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[3, 5, 4]} intensity={1.7} />
      <directionalLight position={[-4, 2, -2]} intensity={0.5} color="#dfe8ff" />
      <StudioEnvironment resolution={256} />
      <group position={[0, -0.15, 0]}>
        <group ref={spin}>
          {/* Pot : céramique ivoire émaillée, liseré laiton, terreau */}
          <mesh geometry={body}><meshPhysicalMaterial color={PALETTE.ivory} roughness={0.3} clearcoat={1} clearcoatRoughness={0.05} side={THREE.DoubleSide} /></mesh>
          <mesh position={[0, POT_H + 0.085, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.77, 0.008, 8, 128]} /><Metal /></mesh>
          <mesh position={[0, POT_H + 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[0.71, 64]} /><meshStandardMaterial color="#2b2119" roughness={1} /></mesh>

          {/* Capteurs en façade : deux yeux à ultrasons, dôme du PIR, écran */}
          <group position={[0, 0.66, front(0.66)]} rotation={[tilt, 0, 0]}>
            {[-0.12, 0.12].map((x) => (
              <group key={x} position={[x, 0, 0.02]} rotation={[Math.PI / 2, 0, 0]}>
                <mesh><cylinderGeometry args={[0.065, 0.065, 0.05, 32]} /><Metal color="#cfcbc3" rough={0.3} /></mesh>
                <mesh position={[0, 0.026, 0]}><cylinderGeometry args={[0.048, 0.048, 0.004, 32]} /><meshStandardMaterial color="#141416" roughness={0.9} /></mesh>
              </group>
            ))}
          </group>
          <group position={[0, 0.4, front(0.4)]} rotation={[tilt, 0, 0]}>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <sphereGeometry args={[0.075, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
              <meshPhysicalMaterial color="#111113" roughness={0.05} clearcoat={1} emissive={STATE_COLOR.warn} emissiveIntensity={state.motion ? 0.9 : 0} />
            </mesh>
          </group>
          <group position={[0, 0.16, front(0.16)]} rotation={[tilt, 0, 0]}>
            <mesh><planeGeometry args={[0.3, 0.12]} /><meshPhysicalMaterial color="#0d0d0f" roughness={0.04} clearcoat={1} /></mesh>
            <mesh position={[0, 0, 0.002]}><planeGeometry args={[0.18, 0.016]} />
              <meshBasicMaterial color={state.online ? (state.motion ? STATE_COLOR.warn : STATE_COLOR.ok) : STATE_COLOR.off} />
            </mesh>
          </group>

          {/* Plante, la caméra discrètement logée dans le feuillage */}
          <group ref={plant}>
            {stems.map((s, i) => (
              <group key={i}>
                <mesh geometry={s.geom}><meshStandardMaterial color="#3f5a3a" roughness={0.7} /></mesh>
                <Leaf position={s.tip} rotation={[0.35, s.rot, -Math.atan2(s.dir.x, s.dir.y)]} scale={s.leaf} />
                <Leaf position={s.tip} rotation={[-0.3, s.rot + Math.PI * 0.8, -Math.atan2(s.dir.x, s.dir.y) + 0.9]} scale={s.leaf * 0.8} color={PALETTE.sage} />
              </group>
            ))}
            <group position={[stems[0].tip.x, stems[0].tip.y - 0.3, stems[0].tip.z + 0.1]}>
              <mesh rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.06, 0.068, 0.1, 32]} /><Ceramic color={PALETTE.graphite} rough={0.4} /></mesh>
              <mesh position={[0, 0, 0.051]}><circleGeometry args={[0.04, 32]} />
                <meshPhysicalMaterial color="#0a0a0c" roughness={0.02} clearcoat={1} emissive={STATE_COLOR.crit} emissiveIntensity={state.cameraLive ? 0.8 : 0} />
              </mesh>
              <mesh position={[0, 0, 0.052]}><ringGeometry args={[0.042, 0.05, 32]} /><Metal /></mesh>
            </group>
          </group>
        </group>
      </group>
      <ContactShadows position={[0, -0.16, 0]} opacity={0.5} scale={3.2} blur={2.4} far={1.6} />
    </>
  );
}
