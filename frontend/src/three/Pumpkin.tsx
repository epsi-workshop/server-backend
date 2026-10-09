import { useMemo, useRef, type MutableRefObject } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { MOTION } from "./threat";
import { ElectronicsModule, MODULE_SCALE, MODULE_Z } from "./Electronics";

/**
 * Le boîtier : une citrouille animée d'Halloween (tête sculptée, buste en tissu noir, mains griffues,
 * gaze verte). Modèle entièrement procédural. Le module électronique est posé derrière, au sol.
 *
 * Repère : base posée en y = 0, face vers +z, hauteur ≈ 2,05, envergure des mains ≈ 2,2.
 */

export const PUMPKIN_GLOW = "#a8e34c"; // vert acide des yeux, comme sur le produit

export type PumpkinProps = {
  glow?: string; // couleur des yeux et de la bouche
  glowLevel?: number; // 0 éteint, ~1.5 allumé
  yaw?: number; // rotation de la tête (servo), radians
  yawRef?: MutableRefObject<number>; // idem, lue à chaque image (prioritaire sur yaw)
  wave?: number; // 0 mains immobiles, 1 mains qui s'agitent
  inside?: number; // surcroît de lueur (mise en avant des composants)
  insideRef?: MutableRefObject<number>; // idem, lu à chaque image
  dim?: boolean; // boîtier hors ligne : couleurs ternies
  module?: boolean; // module électronique derrière (par défaut : oui)
};

// ------------------------------------------------------------------------------------- tête

const HEAD_R = 0.56;
const HEAD_Y = 1.47; // centre de la tête
const LOBES = 10;

/** Déforme une direction unitaire en citrouille : côtes verticales, aplatie, creusée aux pôles. */
function pumpkinPoint(theta: number, phi: number, scale = 1): THREE.Vector3 {
  const groove = Math.pow(Math.abs(Math.sin((LOBES * phi) / 2)), 0.6);
  const pole = Math.sin(theta);
  const r = HEAD_R * scale * (0.92 + 0.08 * groove * (0.4 + 0.6 * pole));
  const x = r * Math.sin(theta) * Math.cos(phi);
  const z = r * Math.sin(theta) * Math.sin(phi);
  let y = r * Math.cos(theta) * 0.84;
  y -= HEAD_R * scale * 0.13 * Math.exp(-Math.pow(theta / 0.32, 2)); // creux du pédoncule
  y += HEAD_R * scale * 0.08 * Math.exp(-Math.pow((Math.PI - theta) / 0.35, 2)); // creux du dessous
  return new THREE.Vector3(x, y, z);
}

/** Sphère déformée en citrouille. */
function headGeometry() {
  const g = new THREE.SphereGeometry(1, 128, 64);
  const pos = g.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    const theta = Math.acos(THREE.MathUtils.clamp(y, -1, 1));
    // SphereGeometry : x = -cos(phi)·sin(theta), z = sin(phi)·sin(theta)
    const phi = Math.atan2(z, -x);
    const p = pumpkinPoint(theta, phi);
    pos.setXYZ(i, -p.x, p.y, p.z);
  }
  g.computeVertexNormals();
  return g;
}

let faceTextures: { map: THREE.CanvasTexture; glow: THREE.CanvasTexture; bump: THREE.CanvasTexture } | null = null;

/**
 * Textures de la tête, peintes sur canvas : peau orange à côtes, visage sculpté (yeux en amande
 * sous un sourcil lourd, nez en cœur renversé, sourire en dents de scie). Le masque « glow »
 * ne laisse briller que les ouvertures.
 */
function useFaceTextures() {
  return useMemo(() => {
    if (faceTextures) return faceTextures;
    const W = 2048, H = 1024;
    const mk = () => { const c = document.createElement("canvas"); c.width = W; c.height = H; return [c, c.getContext("2d")!] as const; };
    const [cm, m] = mk(), [cg, g] = mk(), [cb, b] = mk();

    // Peau : orange, côtes plus sombres (u = k / LOBES), marbrures.
    const skin = m.createLinearGradient(0, 0, 0, H);
    skin.addColorStop(0, "#9a4a14"); skin.addColorStop(0.25, "#d9762a"); skin.addColorStop(0.55, "#e0802f"); skin.addColorStop(1, "#8a3f10");
    m.fillStyle = skin; m.fillRect(0, 0, W, H);
    b.fillStyle = "#808080"; b.fillRect(0, 0, W, H);
    for (let k = 0; k <= LOBES; k++) {
      const x = (k / LOBES) * W;
      const gr = m.createLinearGradient(x - 70, 0, x + 70, 0);
      gr.addColorStop(0, "rgba(90,35,5,0)"); gr.addColorStop(0.5, "rgba(90,35,5,.55)"); gr.addColorStop(1, "rgba(90,35,5,0)");
      m.fillStyle = gr; m.fillRect(x - 70, 0, 140, H);
      const gb = b.createLinearGradient(x - 50, 0, x + 50, 0);
      gb.addColorStop(0, "#808080"); gb.addColorStop(0.5, "#3a3a3a"); gb.addColorStop(1, "#808080");
      b.fillStyle = gb; b.fillRect(x - 50, 0, 100, H);
    }
    for (let i = 0; i < 900; i++) {
      m.fillStyle = `rgba(${Math.random() < 0.5 ? "255,190,120" : "110,45,10"},${Math.random() * 0.06})`;
      m.beginPath(); m.ellipse(Math.random() * W, Math.random() * H, 6 + Math.random() * 30, 20 + Math.random() * 80, 0, 0, Math.PI * 2); m.fill();
    }

    g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
    // Visage centré sur u = 0.25 (face +z), sous l'équateur (v = 0.5).
    const cx = W * 0.25, cy = H * 0.5;
    const eye = (s: number) => {
      const p = new Path2D();
      const x = cx + s * 120;
      p.moveTo(x - s * 72, cy - 92); // coin intérieur, haut (sourcil froncé)
      p.quadraticCurveTo(x - s * 10, cy - 150, x + s * 82, cy - 128);
      p.quadraticCurveTo(x + s * 104, cy - 60, x + s * 40, cy - 34);
      p.quadraticCurveTo(x - s * 40, cy - 22, x - s * 72, cy - 92);
      return p;
    };
    const nose = new Path2D();
    nose.moveTo(cx, cy + 34); nose.quadraticCurveTo(cx - 40, cy - 6, cx - 26, cy - 22); nose.quadraticCurveTo(cx - 10, cy - 30, cx, cy - 14);
    nose.quadraticCurveTo(cx + 10, cy - 30, cx + 26, cy - 22); nose.quadraticCurveTo(cx + 40, cy - 6, cx, cy + 34);
    const mouth = new Path2D();
    const mw = 300, top = cy + 70;
    const teeth = 7;
    mouth.moveTo(cx - mw, top - 30);
    for (let i = 0; i <= teeth * 2; i++) { // lèvre supérieure en dents de scie
      const x = cx - mw + (i / (teeth * 2)) * mw * 2;
      const arc = Math.pow((x - cx) / mw, 2) * -40;
      mouth.lineTo(x, top + arc + (i % 2 ? 46 : 4));
    }
    for (let i = teeth * 2; i >= 0; i--) { // lèvre inférieure
      const x = cx - mw + (i / (teeth * 2)) * mw * 2;
      const arc = Math.pow((x - cx) / mw, 2) * -70;
      mouth.lineTo(x, top + 150 + arc + (i % 2 ? -44 : 0));
    }
    mouth.closePath();
    const holes = [eye(-1), eye(1), nose, mouth];
    for (const h of holes) {
      // Bord sculpté : liseré sombre puis tranche claire, fond vert translucide.
      m.lineJoin = "round"; m.lineWidth = 34; m.strokeStyle = "#4a1e06"; m.stroke(h);
      m.lineWidth = 14; m.strokeStyle = "#f0a560"; m.stroke(h);
      m.fillStyle = "#3d6a14"; m.fill(h);
      g.fillStyle = "#fff"; g.fill(h);
      b.lineWidth = 40; b.strokeStyle = "#202020"; b.stroke(h);
      b.fillStyle = "#101010"; b.fill(h);
    }
    // Sourcils lourds au-dessus des yeux (relief).
    for (const s of [-1, 1]) {
      const x = cx + s * 120;
      const br = b.createRadialGradient(x, cy - 150, 10, x, cy - 150, 120);
      br.addColorStop(0, "#c8c8c8"); br.addColorStop(1, "rgba(128,128,128,0)");
      b.fillStyle = br; b.fillRect(x - 130, cy - 270, 260, 220);
    }
    const tex = (c: HTMLCanvasElement, srgb: boolean) => {
      const t = new THREE.CanvasTexture(c);
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 8;
      return t;
    };
    faceTextures = { map: tex(cm, true), glow: tex(cg, false), bump: tex(cb, false) };
    return faceTextures;
  }, []);
}

type HeadProps = Required<Pick<PumpkinProps, "glow" | "glowLevel" | "dim">> & { inside: MutableRefObject<number> };

function Head({ glow, glowLevel, inside, dim }: HeadProps) {
  const tex = useFaceTextures();
  const geo = useMemo(headGeometry, []);
  const light = useRef<THREE.PointLight>(null);
  useFrame(({ clock }) => {
    // Lueur de bougie : léger scintillement.
    const flicker = 1 + Math.sin(clock.elapsedTime * 7.3) * 0.05 + Math.sin(clock.elapsedTime * 13.1) * 0.03;
    if (light.current) light.current.intensity = (glowLevel * 0.6 + inside.current * 0.5) * flicker;
  });
  return (
    <group position={[0, HEAD_Y, 0]}>
      <mesh geometry={geo} castShadow>
        <meshPhysicalMaterial map={tex.map} bumpMap={tex.bump} bumpScale={2.2} color={dim ? "#7a6a5e" : "#ffffff"} roughness={0.42} clearcoat={0.35} clearcoatRoughness={0.4}
          emissive={glow} emissiveMap={tex.glow} emissiveIntensity={glowLevel} />
      </mesh>
      {/* lueur projetée devant le visage */}
      <pointLight ref={light} position={[0, -0.05, 0.75]} color={glow} intensity={glowLevel * 0.6} distance={1.4} />
      <Stem />
      <NoseKit dim={dim} />
    </group>
  );
}

/**
 * Petite caméra (ESP32-CAM) et module laser logés dans le nez sculpté : on ne voit qu'un objectif
 * sombre et la pointe du laser au fond de l'ouverture.
 */
function NoseKit({ dim }: { dim: boolean }) {
  const z = HEAD_R - 0.01; // surface du visage au niveau du nez
  return (
    <group position={[0, -0.002, z]}>
      {/* caméra : bague noire et objectif */}
      <mesh position={[-0.012, 0, 0]} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.022, 0.024, 0.03, 28]} />
        <meshStandardMaterial color="#141416" roughness={0.5} />
      </mesh>
      <mesh position={[-0.012, 0, 0.016]} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.013, 0.013, 0.004, 28]} />
        <meshPhysicalMaterial color="#05070a" roughness={0.05} metalness={0.3} clearcoat={1} />
      </mesh>
      {/* laser : petit fût laiton, pointe rouge */}
      <mesh position={[0.022, 0.012, -0.002]} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.0075, 0.0075, 0.03, 16]} />
        <meshStandardMaterial color="#b8955a" metalness={0.9} roughness={0.3} />
      </mesh>
      <mesh position={[0.022, 0.012, 0.0135]}>
        <sphereGeometry args={[0.0042, 12, 8]} />
        <meshStandardMaterial color="#ff2a1a" emissive="#ff2a1a" emissiveIntensity={dim ? 0 : 3} toneMapped={false} />
      </mesh>
    </group>
  );
}

function Stem() {
  return (
    <group position={[0, HEAD_R * 0.84 - HEAD_R * 0.13 - 0.02, 0]}>
      <mesh position={[0, 0.08, 0]} rotation-z={0.18}>
        <cylinderGeometry args={[0.035, 0.07, 0.2, 7]} />
        <meshStandardMaterial color="#8c5a26" roughness={0.75} />
      </mesh>
      <mesh position={[0.035, 0.19, 0]} rotation-z={0.9}>
        <cylinderGeometry args={[0.02, 0.034, 0.1, 7]} />
        <meshStandardMaterial color="#7a4c1e" roughness={0.75} />
      </mesh>
    </group>
  );
}

// ------------------------------------------------------------------------------------- buste

const BODY_PROFILE: [number, number][] = [
  // Tissu tombé sur une armature : épaules tombantes, flancs presque droits, ourlet légèrement évasé.
  [0.0, 0], [0.62, 0], [0.63, 0.04], [0.58, 0.2], [0.54, 0.42], [0.52, 0.58], [0.48, 0.68], [0.38, 0.77], [0.26, 0.85], [0.19, 0.93], [0.16, 1.04], [0.0, 1.05],
];
const BODY_SX = 1.08, BODY_SZ = 0.8;

/** Rayon du buste à la hauteur y (interpolation du profil). */
function bodyRadius(y: number) {
  for (let i = 1; i < BODY_PROFILE.length; i++) {
    const [r0, y0] = BODY_PROFILE[i - 1], [r1, y1] = BODY_PROFILE[i];
    if (y <= y1 && y1 > y0) return r0 + ((r1 - r0) * (y - y0)) / (y1 - y0);
  }
  return 0.17;
}

function fabricGeometry() {
  const g = new THREE.LatheGeometry(BODY_PROFILE.map(([r, y]) => new THREE.Vector2(r, y)), 72);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const a = Math.atan2(z, x);
    // Plis verticaux qui se creusent vers le bas, comme un tissu qui retombe ; ourlet ondulé.
    const drop = THREE.MathUtils.clamp(1 - y / 0.75, 0, 1);
    const fold = (0.008 + 0.03 * drop) * Math.sin(a * 7 + Math.sin(a * 3) * 1.4) + 0.008 * Math.sin(a * 19 + y * 9);
    const k = 1 + (y > 0.005 && y < 1 ? fold : 0);
    const hem = y < 0.05 ? 0.012 * Math.sin(a * 7 + Math.sin(a * 3) * 1.4) : 0;
    p.setXYZ(i, x * k * BODY_SX, y + hem, z * k * BODY_SZ);
  }
  g.computeVertexNormals();
  return g;
}

function Fabric({ dim }: { dim: boolean }) {
  return <meshPhysicalMaterial color={dim ? "#1a1a1a" : "#141415"} roughness={0.95} sheen={1} sheenColor="#3a3a3e" sheenRoughness={0.6} side={THREE.DoubleSide} />;
}

function Body({ dim }: { dim: boolean }) {
  const geo = useMemo(fabricGeometry, []);
  return (
    <group>
      <mesh geometry={geo} castShadow receiveShadow><Fabric dim={dim} /></mesh>
      {/* manches horizontales, ouvertes vers les mains */}
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * 0.78, 0.68, 0.02]} rotation-z={(s * Math.PI) / 2} castShadow>
          <cylinderGeometry args={[0.19, 0.16, 0.52, 28, 1, true]} />
          <Fabric dim={dim} />
        </mesh>
      ))}
      <PirSensor />
    </group>
  );
}

/**
 * Détecteur de présence PIR : posé sous la cape, seul son dôme blanc dépasse de l'ourlet, à l'avant.
 * (Le DHT22, également sous la cape, et le lecteur RFID, dans la tête, ne sont pas visibles.)
 */
function PirSensor() {
  const y = 0.04;
  const z = bodyRadius(y) * BODY_SZ + 0.025;
  return (
    <group position={[0.14, y, z]}>
      <mesh position={[0, 0.005, -0.03]}>
        <boxGeometry args={[0.15, 0.012, 0.11]} />
        <meshStandardMaterial color="#1f6b45" roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.011, 0]}>
        <sphereGeometry args={[0.053, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial color="#f4f4f1" roughness={0.35} transmission={0.15} thickness={0.02} clearcoat={0.4} />
      </mesh>
    </group>
  );
}

// ------------------------------------------------------------------------------------- mains

const HAND_X = 1.04;
const HAND_SCALE = 1.75;

function HandMaterial({ dim }: { dim: boolean }) {
  return <meshPhysicalMaterial color={dim ? "#7a5e4c" : "#c9692f"} roughness={0.45} clearcoat={0.5} clearcoatRoughness={0.35} />;
}

/** Doigt griffu : trois phalanges effilées qui se recourbent vers la tête, terminées par une griffe. */
function Finger({ len, curl, dim }: { len: number; curl: number; dim: boolean }) {
  const segs = [len * 0.42, len * 0.33, len * 0.25];
  let node: JSX.Element = (
    <mesh position={[0, 0.045, 0]}>
      <coneGeometry args={[0.017, 0.08, 10]} />
      <HandMaterial dim={dim} />
    </mesh>
  );
  for (let i = segs.length - 1; i >= 0; i--) {
    const l = segs[i];
    const r0 = 0.04 - i * 0.007, r1 = r0 - 0.006;
    node = (
      <group rotation-z={curl}>
        <mesh position={[0, l / 2, 0]}>
          <cylinderGeometry args={[r1, r0, l, 10]} />
          <HandMaterial dim={dim} />
        </mesh>
        <mesh position={[0, l, 0]}><sphereGeometry args={[r1 * 1.05, 10, 8]} /><HandMaterial dim={dim} /></mesh>
        <group position={[0, l, 0]}>{node}</group>
      </group>
    );
  }
  return node;
}

/** Main droite (x > 0), paume tournée vers la tête ; la gauche est son miroir. */
function Hand({ side, dim, handRef }: { side: 1 | -1; dim: boolean; handRef: (g: THREE.Group | null) => void }) {
  const fingers = [
    { z: -0.1, len: 0.34, curl: 0.2 },
    { z: -0.035, len: 0.4, curl: 0.24 },
    { z: 0.035, len: 0.38, curl: 0.22 },
    { z: 0.1, len: 0.3, curl: 0.18 },
  ];
  return (
    <group position={[side * HAND_X, 0.6, 0.02]} scale={[side * HAND_SCALE, HAND_SCALE, HAND_SCALE]} rotation-z={side * 0.08}>
      <group ref={handRef}>
        <mesh position={[0, 0.08, 0]}><cylinderGeometry args={[0.075, 0.085, 0.2, 14]} /><HandMaterial dim={dim} /></mesh>
        <mesh position={[0, 0.27, 0]} scale={[0.08, 0.17, 0.15]}><sphereGeometry args={[1, 20, 16]} /><HandMaterial dim={dim} /></mesh>
        {fingers.map((f) => (
          <group key={f.z} position={[-0.01, 0.38, f.z]} rotation-x={f.z * 1.2}>
            <Finger len={f.len} curl={f.curl} dim={dim} />
          </group>
        ))}
        {/* pouce, vers l'avant */}
        <group position={[-0.02, 0.24, 0.12]} rotation-x={0.9}>
          <Finger len={0.22} curl={0.25} dim={dim} />
        </group>
      </group>
    </group>
  );
}

// ------------------------------------------------------------------------------------- gaze

let gauzeTex: THREE.CanvasTexture | null = null;

/** Trame de gaze : tissu lâche, percé de petits trous et de déchirures, bords effilochés (masque alpha). */
function useGauzeTexture() {
  return useMemo(() => {
    if (gauzeTex) return gauzeTex;
    const W = 256, H = 512;
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const x = c.getContext("2d")!;
    x.fillStyle = "#fff"; x.fillRect(0, 0, W, H);
    // Bords effilochés : le tissu s'amincit vers les deux lisières.
    const edge = x.createLinearGradient(0, 0, W, 0);
    edge.addColorStop(0, "rgba(0,0,0,1)"); edge.addColorStop(0.16, "rgba(0,0,0,0)"); edge.addColorStop(0.84, "rgba(0,0,0,0)"); edge.addColorStop(1, "rgba(0,0,0,1)");
    x.fillStyle = edge; x.fillRect(0, 0, W, H);
    x.fillStyle = "#000";
    for (let i = 0; i < 900; i++) { // maille
      x.globalAlpha = 0.6 + Math.random() * 0.4;
      x.fillRect(Math.random() * W, Math.random() * H, 2 + Math.random() * 4, 2 + Math.random() * 5);
    }
    for (let i = 0; i < 28; i++) { // déchirures
      x.globalAlpha = 1;
      x.beginPath(); x.ellipse(Math.random() * W, Math.random() * H, 5 + Math.random() * 16, 12 + Math.random() * 46, (Math.random() - 0.5) * 0.6, 0, Math.PI * 2); x.fill();
    }
    x.strokeStyle = "#fff"; // fils qui traversent les déchirures
    for (let i = 0; i < 60; i++) {
      x.globalAlpha = 0.8; x.lineWidth = 1 + Math.random() * 1.5;
      const x0 = Math.random() * W;
      x.beginPath(); x.moveTo(x0, Math.random() * H); x.lineTo(x0 + Math.random() * 10 - 5, Math.random() * H); x.stroke();
    }
    gauzeTex = new THREE.CanvasTexture(c);
    gauzeTex.wrapS = gauzeTex.wrapT = THREE.RepeatWrapping;
    return gauzeTex;
  }, []);
}

/** Ruban de gaze le long d'un chemin, plaqué contre une surface (normale fournie à chaque point). */
function ribbon(points: THREE.Vector3[], normals: THREE.Vector3[], widths: number[]) {
  const verts: number[] = [], uvs: number[] = [], idx: number[] = [];
  let len = 0;
  for (let i = 0; i < points.length; i++) {
    const t = points[Math.min(i + 1, points.length - 1)].clone().sub(points[Math.max(i - 1, 0)]).normalize();
    const side = new THREE.Vector3().crossVectors(t, normals[i]).normalize().multiplyScalar(widths[i] / 2);
    const a = points[i].clone().add(side), b = points[i].clone().sub(side);
    verts.push(a.x, a.y, a.z, b.x, b.y, b.z);
    if (i > 0) len += points[i].distanceTo(points[i - 1]);
    uvs.push(0, len * 2, 1, len * 2);
    if (i < points.length - 1) { const k = i * 2; idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

/** Pseudo-aléatoire déterministe : la gaze garde la même forme d'un rendu à l'autre. */
function rand(seed: number) {
  const s = Math.sin(seed * 127.1) * 43758.5453;
  return s - Math.floor(s);
}

function gauzeGeometries() {
  const out: THREE.BufferGeometry[] = [];
  // Lambeaux qui tombent du cou sur le buste et s'étalent au sol.
  const n = 13;
  for (let k = 0; k < n; k++) {
    const a = (k / n) * Math.PI * 2 + rand(k) * 0.3;
    const pts: THREE.Vector3[] = [], nor: THREE.Vector3[] = [], wid: number[] = [];
    const w0 = 0.18 + rand(k + 7) * 0.16;
    const spread = 0.15 + rand(k + 3) * 0.35; // longueur étalée au sol
    for (let i = 0; i <= 26; i++) {
      const y = 1.02 - (i / 26) * 1.0;
      const r = bodyRadius(Math.max(y, 0.01)) + 0.02;
      const wob = Math.sin(i * 0.7 + k) * 0.05;
      const dir = new THREE.Vector3(Math.cos(a + wob), 0, Math.sin(a + wob));
      pts.push(new THREE.Vector3(dir.x * r * BODY_SX, y, dir.z * r * BODY_SZ));
      nor.push(new THREE.Vector3(dir.x, 0.25, dir.z).normalize());
      wid.push(w0 * (0.7 + 0.6 * Math.sin(i * 0.35 + k)) + 0.02);
    }
    // Étalé au sol, vers l'extérieur
    const last = pts[pts.length - 1];
    const out2 = new THREE.Vector3(Math.cos(a), 0, Math.sin(a));
    for (let i = 1; i <= 6; i++) {
      const d = (i / 6) * spread;
      pts.push(new THREE.Vector3(last.x + out2.x * d, 0.008, last.z + out2.z * d));
      nor.push(new THREE.Vector3(0, 1, 0));
      wid.push(w0 * (1 - i / 9));
    }
    out.push(ribbon(pts, nor, wid));
  }
  // Lambeaux sur les manches, qui pendent sous les mains.
  for (const s of [-1, 1]) {
    for (let k = 0; k < 3; k++) {
      const z = -0.08 + k * 0.08;
      const pts: THREE.Vector3[] = [], nor: THREE.Vector3[] = [], wid: number[] = [];
      for (let i = 0; i <= 10; i++) { const x = 0.5 + (i / 10) * 0.55; pts.push(new THREE.Vector3(s * x, 0.9 - (i / 10) * 0.04, z)); nor.push(new THREE.Vector3(0, 1, 0)); wid.push(0.12); }
      for (let i = 1; i <= 12; i++) {
        const y = 0.86 - (i / 12) * (0.55 + rand(s * 10 + k) * 0.3);
        pts.push(new THREE.Vector3(s * (1.08 + Math.sin(i * 0.6 + k) * 0.03), y, z + (s * 0.03 * i) / 12));
        nor.push(new THREE.Vector3(s, 0, 0)); wid.push(0.11 * (1 - i / 16));
      }
      out.push(ribbon(pts, nor, wid));
    }
  }
  return out;
}

function Gauze({ dim }: { dim: boolean }) {
  const alpha = useGauzeTexture();
  const geos = useMemo(gauzeGeometries, []);
  return (
    <group>
      {geos.map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial color={dim ? "#34331f" : "#4c4a24"} roughness={1} alphaMap={alpha} alphaTest={0.5} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  );
}

// ------------------------------------------------------------------------------------- assemblage

/** La citrouille complète. Les valeurs animées (tête, mains) sont amorties ici. */
export function Pumpkin({ glow = PUMPKIN_GLOW, glowLevel = 1.4, yaw = 0, yawRef, wave = 0.15, inside = 0, insideRef, dim = false, module = true }: PumpkinProps) {
  const head = useRef<THREE.Group>(null);
  const hands = useRef<(THREE.Group | null)[]>([]);
  const insideNow = useRef(inside);
  const cur = useRef({ yaw, wave });
  useFrame(({ clock }, dt) => {
    const k = 1 - Math.exp(-dt * 5);
    const c = cur.current;
    insideNow.current = insideRef ? insideRef.current : inside;
    c.yaw += ((yawRef ? yawRef.current : yaw) - c.yaw) * k;
    c.wave += (wave - c.wave) * k;
    const t = clock.elapsedTime * MOTION;
    if (head.current) {
      head.current.rotation.y = c.yaw + Math.sin(t * 0.6) * 0.04;
      head.current.rotation.z = Math.sin(t * 0.9) * 0.02 * (1 + c.wave * 2);
    }
    hands.current.forEach((h, i) => {
      if (!h) return;
      const ph = t * (1.2 + c.wave * 4) + i * Math.PI;
      h.rotation.z = Math.sin(ph) * (0.03 + c.wave * 0.22);
      h.rotation.x = Math.cos(ph * 0.8) * (0.02 + c.wave * 0.12);
    });
  });
  return (
    <group>
      <Body dim={dim} />
      <Gauze dim={dim} />
      {module && <group position={[0, 0, MODULE_Z]} scale={MODULE_SCALE}><ElectronicsModule /></group>}
      {([1, -1] as const).map((s, i) => <Hand key={s} side={s} dim={dim} handRef={(g) => { hands.current[i] = g; }} />)}
      {/* la tête pivote autour de l'axe du cou (servo) */}
      <group ref={head}>
        <Head glow={glow} glowLevel={glowLevel} inside={insideNow} dim={dim} />
      </group>
    </group>
  );
}

export { bodyRadius, HEAD_Y, HEAD_R };
