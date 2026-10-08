import { Suspense, useMemo, useRef, type MutableRefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Html, MeshReflectorMaterial, RoundedBox, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { StudioEnvironment } from "../three/Objects";
import { MOTION, STATE_COLOR } from "../three/threat";
import potOpenUrl from "../assets/pot-ouvert.glb?url";
import { RACK_X, SECTIONS, adaptToViewport, poseAt, type Pose, type Stop } from "./timeline";
import { FaceScreen, LaptopScreen, PhoneScreen } from "./Screens";

/**
 * Scène unique de la page de présentation : le pot, la baie de la salle serveur, le contrôle d'accès
 * et les écrans de supervision. Tout est piloté par la pose courante, amortie à partir du défilement.
 */

type Live = { pose: Pose; rotY: number };
type LiveRef = MutableRefObject<Live>;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
/** Rampe : 0 sous `a`, 1 au-dessus de `b`. */
const ramp = (v: number, a: number, b: number) => clamp01((v - a) / (b - a));
const wrapPi = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));

export function Stage({ stops }: { stops: MutableRefObject<Stop[]> }) {
  const live = useRef<Live>({ pose: SECTIONS[0][0], rotY: SECTIONS[0][0].rot });
  return (
    <>
      <color attach="background" args={["#000000"]} />
      <fog attach="fog" args={["#000000", 10, 24]} />
      <Rig stops={stops} live={live} />
      <ambientLight intensity={0.28} />
      <directionalLight position={[3, 5, 4]} intensity={1.6} />
      <directionalLight position={[-4, 2, -2]} intensity={0.5} color="#dfe8ff" />
      <StudioEnvironment resolution={256} />
      <Floor live={live} />
      <Rack live={live} x={RACK_X} />
      <Rack live={live} x={-4.1} z={-0.7} />
      <Room live={live} />
      <Suspense fallback={null}><Pot live={live} /></Suspense>
      <Access live={live} />
      <Devices live={live} />
    </>
  );
}

/** Lit le défilement, amortit la pose et place la caméra. */
function Rig({ stops, live }: { stops: MutableRefObject<Stop[]>; live: LiveRef }) {
  const { camera, size } = useThree();
  const look = useMemo(() => new THREE.Vector3(), []);
  useFrame((_, dt) => {
    const target = adaptToViewport(poseAt(stops.current, window.scrollY), size.width / size.height);
    const cur = live.current.pose;
    const k = 1 - Math.exp(-dt * 3.2);
    const next = {} as Record<keyof Pose, unknown>;
    for (const key of Object.keys(target) as (keyof Pose)[]) {
      const a = cur[key], b = target[key];
      next[key] = Array.isArray(a) ? a.map((v, i) => v + ((b as number[])[i] - v) * k) : (a as number) + ((b as number) - (a as number)) * k;
    }
    const p = next as Pose;
    live.current.pose = p;
    // Rotation : continue quand spin = 1, ramenée par le plus court chemin vers `rot` quand spin = 0.
    let r = live.current.rotY + dt * 0.45 * MOTION * p.spin;
    r += wrapPi(p.rot - r) * (1 - p.spin) * (1 - Math.exp(-dt * 3));
    live.current.rotY = r;
    camera.position.set(...p.cam);
    look.set(...p.look);
    camera.lookAt(look);
  });
  return null;
}

// ------------------------------------------------------------------------------------- pot

const POT_HEIGHT = 2;

/** Modèle réel du boîtier, version « porte ouverte » : la charnière est un nœud que l'on fait pivoter. */
function Pot({ live }: { live: LiveRef }) {
  const { scene } = useGLTF(potOpenUrl, false);
  const { model, hinge, open } = useMemo(() => {
    const root = scene.clone(true);
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const k = POT_HEIGHT / size.y;
    root.scale.setScalar(k);
    const c = box.getCenter(new THREE.Vector3());
    root.position.set(-c.x * k, -box.min.y * k, -c.z * k);
    root.traverse((o) => { if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).castShadow = true; });
    const h = root.getObjectByName("charniere") ?? null;
    return { model: root, hinge: h, open: h ? h.quaternion.clone() : new THREE.Quaternion() };
  }, [scene]);
  const closed = useMemo(() => new THREE.Quaternion(), []);
  const group = useRef<THREE.Group>(null);
  const spin = useRef<THREE.Group>(null);
  const glow = useRef<THREE.PointLight>(null);
  const tags = useRef<HTMLDivElement[]>([]);
  useFrame(() => {
    const p = live.current.pose;
    if (group.current) {
      group.current.position.set(...p.pot);
      group.current.scale.setScalar(p.scale);
    }
    if (spin.current) spin.current.rotation.y = live.current.rotY;
    if (hinge) hinge.quaternion.slerpQuaternions(closed, open, p.door);
    if (glow.current) glow.current.intensity = p.inside * 1.4;
    const o = ramp(p.inside, 0.6, 0.95);
    tags.current.forEach((el) => { el.style.opacity = String(o); el.style.visibility = o > 0.01 ? "visible" : "hidden"; });
  });
  return (
    <group ref={group}>
      <group ref={spin}><primitive object={model} /></group>
      <pointLight ref={glow} position={[0, 0.7, 0.3]} intensity={0} distance={2.4} color="#ffdcb0" />
      <ContactShadows position={[0, 0.006, 0]} opacity={0.55} scale={3} blur={2.4} far={1.6} />
      {HOTSPOTS.map((h, i) => (
        <Html key={h.label} position={h.at} zIndexRange={[20, 10]} style={{ pointerEvents: "none" }}>
          <div className={`hotspot hotspot-${h.side}`} ref={(el) => { if (el) tags.current[i] = el; }}>
            <i /><span><b>{h.label}</b>{h.detail}</span>
          </div>
        </Html>
      ))}
    </group>
  );
}

/**
 * Repères des composants, dans le repère du pot (base au sol, axe au centre).
 * Emplacements indicatifs : à recaler sur le modèle 3D détaillé.
 */
const HOTSPOTS: { at: [number, number, number]; label: string; detail: string; side: "l" | "r" }[] = [
  { at: [-0.1, 1.95, 0.25], label: "ESP32-CAM", detail: "caméra sur servo, dans le feuillage", side: "l" },
  { at: [0.3, 1.38, 0.42], label: "Détecteur PIR", detail: "présence devant la baie", side: "r" },
  { at: [-0.28, 1.12, 0.4], label: "Capteur à ultrasons", detail: "distance d'approche", side: "l" },
  { at: [0.28, 0.9, 0.4], label: "Arduino UNO Q", detail: "contrôleur, Wi-Fi", side: "r" },
  { at: [-0.3, 0.68, 0.42], label: "DHT22", detail: "température et humidité", side: "l" },
  { at: [0.3, 0.46, 0.44], label: "Accéléromètre", detail: "choc et inclinaison", side: "r" },
  { at: [-0.3, 0.26, 0.46], label: "Capteur de porte", detail: "infrarouge", side: "l" },
  { at: [0.26, 0.12, 0.5], label: "Lecteur RFID", detail: "badges de l'équipe", side: "r" },
];

// ------------------------------------------------------------------------------------- sol et salle

function Floor({ live }: { live: LiveRef }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(() => { if (ref.current) ref.current.position.y = live.current.pose.floor + 0.002; });
  return (
    <mesh ref={ref} rotation-x={-Math.PI / 2}>
      <planeGeometry args={[60, 60]} />
      <MeshReflectorMaterial blur={[400, 120]} resolution={768} mixBlur={1} mixStrength={1.4} roughness={0.85}
        depthScale={1.1} minDepthThreshold={0.4} maxDepthThreshold={1.4} color="#070707" metalness={0.6} mirror={0.5} />
    </mesh>
  );
}

const RACK_W = 2.1, RACK_D = 1.3, RACK_H = 3.2;

/** Baie ouverte de la salle serveur : montants, étagères, serveurs aux voyants qui clignotent. */
function Rack({ live, x, z = 0 }: { live: LiveRef; x: number; z?: number }) {
  const leds = useRef<THREE.MeshStandardMaterial[]>([]);
  const group = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (group.current) group.current.visible = live.current.pose.floor < -0.05;
    const t = clock.elapsedTime;
    leds.current.forEach((m, i) => { m.emissiveIntensity = 0.6 + 2.4 * (Math.sin(t * (1.3 + (i % 5) * 0.7) + i * 1.7) > 0.2 ? 1 : 0.15); });
  });
  const units = useMemo(() => {
    const out: { y: number; h: number }[] = [];
    for (const shelf of [-1.07, -2.14, -3.2]) {
      let y = shelf + 0.03;
      for (const h of [0.22, 0.34, 0.22]) { out.push({ y: y + h / 2, h }); y += h + 0.02; }
    }
    return out;
  }, []);
  const ledColor = (i: number) => (i % 7 === 3 ? STATE_COLOR.warn : i % 3 === 0 ? "#7fb8ff" : STATE_COLOR.ok);
  return (
    <group ref={group} position={[x, 0, z]}>
      {/* montants */}
      {[-1, 1].flatMap((sx) => [-1, 1].map((sz) => (
        <mesh key={`${sx}${sz}`} position={[(sx * RACK_W) / 2, -RACK_H / 2, (sz * RACK_D) / 2]}>
          <boxGeometry args={[0.06, RACK_H, 0.06]} />
          <meshStandardMaterial color="#3a3a3e" metalness={1} roughness={0.35} />
        </mesh>
      )))}
      {/* étagères : celle du haut affleure à y = 0, le pot y est posé */}
      {[0, -1.07, -2.14, -3.2].map((y) => (
        <mesh key={y} position={[0, y - 0.03, 0]}>
          <boxGeometry args={[RACK_W + 0.08, 0.06, RACK_D + 0.08]} />
          <meshStandardMaterial color="#232326" metalness={0.9} roughness={0.4} />
        </mesh>
      ))}
      {units.map((u, i) => (
        <group key={i} position={[0, u.y, 0.02]}>
          <mesh>
            <boxGeometry args={[RACK_W - 0.14, u.h, RACK_D - 0.12]} />
            <meshStandardMaterial color="#141416" metalness={0.7} roughness={0.45} />
          </mesh>
          {/* façade : grille et voyants */}
          {Array.from({ length: 9 }, (_, g) => (
            <mesh key={g} position={[-0.25 + g * 0.1, 0, (RACK_D - 0.12) / 2 + 0.002]}>
              <planeGeometry args={[0.04, u.h * 0.6]} />
              <meshStandardMaterial color="#0a0a0b" />
            </mesh>
          ))}
          {[0, 1, 2].map((l) => (
            <mesh key={l} position={[-0.82 + l * 0.08, 0, (RACK_D - 0.12) / 2 + 0.006]}>
              <circleGeometry args={[0.014, 12]} />
              <meshStandardMaterial ref={(m) => { if (m) leds.current[i * 3 + l] = m; }} color="#000" emissive={ledColor(i * 3 + l)} emissiveIntensity={1} toneMapped={false} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

/** Mur de la salle serveur et bandeaux lumineux : apparaissent avec la mise en situation. */
function Room({ live }: { live: LiveRef }) {
  const group = useRef<THREE.Group>(null);
  const mats = useRef<THREE.Material[]>([]);
  useFrame(() => {
    const o = live.current.pose.room;
    if (group.current) group.current.visible = o > 0.01;
    mats.current.forEach((m) => { m.opacity = o * (m.userData.max as number); });
  });
  const keep = (max: number) => (m: THREE.Material | null) => { if (m && !mats.current.includes(m)) { m.userData.max = max; mats.current.push(m); } };
  return (
    <group ref={group}>
      <mesh position={[0, -0.5, -2]}>
        <planeGeometry args={[18, 10]} />
        <meshStandardMaterial ref={keep(1)} color="#0d0d0f" metalness={0.2} roughness={0.9} transparent />
      </mesh>
      {[-6.4, -5.8].map((x) => (
        <mesh key={x} position={[x, -0.6, -1.98]}>
          <planeGeometry args={[0.035, 6]} />
          <meshBasicMaterial ref={keep(0.35)} color="#cfe0ff" transparent toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

// ------------------------------------------------------------------------------------- contrôle d'accès

const BADGE_CYCLE = 4.6;

function Access({ live }: { live: LiveRef }) {
  const card = useRef<HTMLDivElement>(null);
  const badge = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Mesh>(null);
  const ringMat = useRef<THREE.MeshBasicMaterial>(null);
  const rest = useMemo(() => new THREE.Vector3(), []);
  const tap = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ clock }) => {
    const p = live.current.pose;
    const a = p.access;
    if (card.current) {
      const o = ramp(a, 0.55, 0.95);
      card.current.style.opacity = String(o);
      card.current.style.transform = `translateY(${(1 - o) * 40}px)`;
      card.current.style.visibility = o > 0.01 ? "visible" : "hidden";
    }
    // Le badge vient se présenter devant le lecteur, en bas de la façade du pot, puis repart.
    const [px, , pz] = p.pot;
    rest.set(px - 0.95, 1.25, pz + 1.3);
    tap.set(px - 0.12, 0.42, pz + 0.62);
    const t = (clock.elapsedTime * MOTION) % BADGE_CYCLE;
    const go = t < 1.1 ? easeInOut(t / 1.1) : t < 1.9 ? 1 : t < 3 ? 1 - easeInOut((t - 1.9) / 1.1) : 0;
    if (badge.current) {
      badge.current.visible = a > 0.02;
      badge.current.position.lerpVectors(rest, tap, go);
      badge.current.scale.setScalar(easeInOut(ramp(a, 0.3, 0.9)));
      badge.current.rotation.set(-0.15 + go * 0.15, 0.35 - go * 0.25, 0.08);
    }
    if (ring.current && ringMat.current) {
      const r = t >= 1.1 && t < 2.3 ? (t - 1.1) / 1.2 : -1;
      ring.current.visible = r >= 0 && a > 0.5;
      ring.current.position.copy(tap).add(new THREE.Vector3(0, 0, -0.04));
      ring.current.scale.setScalar(0.06 + r * 0.32);
      ringMat.current.opacity = (1 - r) * 0.9;
    }
  });
  return (
    <>
      <Html transform position={[1.95, 1.25, 0]} rotation-y={-0.3} distanceFactor={0.75} zIndexRange={[15, 5]} style={{ pointerEvents: "none" }}>
        <div ref={card} className="face-card-wrap"><FaceScreen /></div>
      </Html>
      <group ref={badge}>
        <RoundedBox args={[0.38, 0.6, 0.018]} radius={0.03} smoothness={4}>
          <meshPhysicalMaterial color="#f2f0ea" roughness={0.3} clearcoat={1} clearcoatRoughness={0.08} />
        </RoundedBox>
        <mesh position={[-0.09, 0.15, 0.011]}>
          <boxGeometry args={[0.08, 0.06, 0.004]} />
          <meshStandardMaterial color="#c9a85f" metalness={1} roughness={0.25} />
        </mesh>
        <mesh position={[0, -0.21, 0.01]}>
          <boxGeometry args={[0.38, 0.045, 0.002]} />
          <meshStandardMaterial color={STATE_COLOR.ok} emissive={STATE_COLOR.ok} emissiveIntensity={0.4} />
        </mesh>
      </group>
      <mesh ref={ring}>
        <torusGeometry args={[1, 0.012, 8, 64]} />
        <meshBasicMaterial ref={ringMat} color={STATE_COLOR.ok} transparent toneMapped={false} />
      </mesh>
    </>
  );
}

function easeInOut(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

// ------------------------------------------------------------------------------------- supervision

function Devices({ live }: { live: LiveRef }) {
  const laptop = useRef<THREE.Group>(null);
  const lid = useRef<THREE.Group>(null);
  const phone = useRef<THREE.Group>(null);
  const screens = useRef<HTMLDivElement[]>([]);
  useFrame(() => {
    const d = live.current.pose.devices;
    const show = easeInOut(ramp(d, 0.05, 0.6));
    if (laptop.current) {
      laptop.current.visible = d > 0.02;
      laptop.current.scale.setScalar(0.6 + 0.4 * show);
      laptop.current.position.y = (1 - show) * -0.6;
    }
    if (lid.current) lid.current.rotation.x = Math.PI / 2 + (-0.26 - Math.PI / 2) * easeInOut(ramp(d, 0.35, 0.85));
    if (phone.current) {
      phone.current.visible = d > 0.02;
      const s = easeInOut(ramp(d, 0.25, 0.8));
      phone.current.position.y = (1 - s) * -1.2;
      phone.current.scale.setScalar(s);
    }
    const o = ramp(d, 0.8, 0.98);
    screens.current.forEach((el) => { el.style.opacity = String(o); el.style.visibility = o > 0.01 ? "visible" : "hidden"; });
  });
  const keep = (el: HTMLDivElement | null) => { if (el && !screens.current.includes(el)) screens.current.push(el); };
  return (
    <>
      <group position={[1.85, 0, -0.5]} rotation-y={-0.2}>
        <group ref={laptop}>
          <RoundedBox args={[2.5, 0.07, 1.65]} radius={0.03} smoothness={4} position={[0, 0.035, 0]}>
            <meshStandardMaterial color="#2c2c30" metalness={1} roughness={0.32} />
          </RoundedBox>
          <mesh position={[0, 0.072, -0.12]} rotation-x={-Math.PI / 2}>
            <planeGeometry args={[2.2, 0.9]} />
            <meshStandardMaterial color="#0c0c0d" roughness={0.6} />
          </mesh>
          <mesh position={[0, 0.072, 0.52]} rotation-x={-Math.PI / 2}>
            <planeGeometry args={[0.8, 0.45]} />
            <meshStandardMaterial color="#1e1e21" metalness={0.6} roughness={0.35} />
          </mesh>
          <group ref={lid} position={[0, 0.07, -0.81]}>
            <RoundedBox args={[2.5, 1.6, 0.045]} radius={0.03} smoothness={4} position={[0, 0.8, 0]}>
              <meshStandardMaterial color="#2c2c30" metalness={1} roughness={0.32} />
            </RoundedBox>
            <mesh position={[0, 0.8, 0.024]}>
              <planeGeometry args={[2.42, 1.52]} />
              <meshPhysicalMaterial color="#050506" roughness={0.08} clearcoat={1} />
            </mesh>
            <Html transform position={[0, 0.81, 0.027]} distanceFactor={1} zIndexRange={[15, 5]} style={{ pointerEvents: "none" }}>
              <div ref={keep}><LaptopScreen /></div>
            </Html>
          </group>
        </group>
      </group>
      <group position={[2.95, 0, 0.75]} rotation-y={-0.45} scale={0.85}>
        <group ref={phone}>
          <mesh position={[0, 0.02, 0.05]}>
            <cylinderGeometry args={[0.32, 0.36, 0.04, 48]} />
            <meshStandardMaterial color="#2c2c30" metalness={1} roughness={0.3} />
          </mesh>
          <group position={[0, 0.8, 0]} rotation-x={-0.1}>
            <RoundedBox args={[0.74, 1.5, 0.07]} radius={0.09} smoothness={6}>
              <meshStandardMaterial color="#38383d" metalness={1} roughness={0.25} />
            </RoundedBox>
            <mesh position={[0, 0, 0.036]}>
              <planeGeometry args={[0.7, 1.46]} />
              <meshPhysicalMaterial color="#050506" roughness={0.08} clearcoat={1} />
            </mesh>
            <Html transform position={[0, 0, 0.038]} distanceFactor={1} zIndexRange={[15, 5]} style={{ pointerEvents: "none" }}>
              <div ref={keep}><PhoneScreen /></div>
            </Html>
          </group>
        </group>
      </group>
    </>
  );
}

useGLTF.preload(potOpenUrl, false);
