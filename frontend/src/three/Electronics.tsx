import { useMemo } from "react";
import * as THREE from "three";

/**
 * Module électronique du boîtier, posé au sol derrière la citrouille, d'après le plan de montage
 * (enclosure/montage-3d.html) : socle, Arduino UNO Q, breadboard et câbles Dupont. Les câbles
 * passent sous la citrouille jusqu'à la tête (caméra et laser dans le nez).
 *
 * Cotes en millimètres, comme le plan ; le groupe est mis à l'échelle par l'appelant.
 */

const Y0 = 9; // dessus du socle

/** Position du module derrière la citrouille et échelle mm → unités de la scène. */
export const MODULE_SCALE = 0.0046;
export const MODULE_Z = -1.0;
// Distance (mm, repère du module) jusqu'au centre de la citrouille : les câbles s'y engagent sous le tissu.
const UNDER = -MODULE_Z / MODULE_SCALE;

function useMaterials() {
  return useMemo(() => {
    const m = (color: string, o: THREE.MeshStandardMaterialParameters = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, ...o });
    return {
      plate: m("#f2f2ef", { roughness: 0.7 }),
      steel: m("#a9adb1", { metalness: 0.85, roughness: 0.35 }),
      pcbBlue: m("#1f5fa8", { roughness: 0.5 }),
      bread: m("#f1efe6", { roughness: 0.8 }),
      dark: m("#161819", { roughness: 0.4 }),
      cable: m("#2c2c2c", { roughness: 0.6 }),
      velcro: m("#303436"),
      red: m("#c0392b"), orange: m("#e08a2e"), yellow: m("#e0c23a"),
    };
  }, []);
}

type Mat = THREE.Material;
type V3 = [number, number, number];

function Box({ size, at, mat }: { size: V3; at: V3; mat: Mat }) {
  return <mesh position={at} material={mat} castShadow receiveShadow><boxGeometry args={size} /></mesh>;
}

function Cyl({ r, h, at, mat, seg = 32 }: { r: number; h: number; at: V3; mat: Mat; seg?: number }) {
  return <mesh position={at} material={mat} castShadow><cylinderGeometry args={[r, r, h, seg]} /></mesh>;
}

function Wire({ pts, r, mat, seg = 32 }: { pts: V3[]; r: number; mat: Mat; seg?: number }) {
  const geo = useMemo(() => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p))), seg, r, 6), [pts, r, seg]);
  return <mesh geometry={geo} material={mat} castShadow />;
}

/** Câble Dupont en arc entre deux points du socle. */
const arc = (a: V3, b: V3, lift: number): V3[] => [a, [(a[0] + b[0]) / 2, Math.max(a[1], b[1]) + lift, (a[2] + b[2]) / 2], b];

/** Câble qui quitte le socle, descend au sol et file sous la citrouille. */
const toPumpkin = (from: V3, x: number): V3[] => [
  from,
  [from[0], from[1] + 18, from[2] + 20],
  [x, 3, 115],
  [x * 0.6, 2, UNDER - 120],
  [x * 0.2, 2, UNDER - 40],
];

export function ElectronicsModule() {
  const M = useMaterials();
  return (
    <group>
      {/* socle : disque PVC Ø 200 */}
      <Cyl r={100} h={5} at={[0, 6.5, 0]} mat={M.plate} seg={96} />

      {/* Arduino UNO Q */}
      <group position={[-50, Y0, 0]}>
        <Box size={[53, 1.6, 69]} at={[0, 6, 0]} mat={M.pcbBlue} />
        {[-30, 30].flatMap((z) => [-22, 22].map((x) => <Cyl key={`${x}${z}`} r={1.6} h={6} at={[x, 3, z]} mat={M.steel} seg={10} />))}
        <Box size={[14, 2, 14]} at={[2, 7.8, 6]} mat={M.dark} />
        <Box size={[2.5, 8, 40]} at={[-24, 11, 4]} mat={M.dark} />
        <Box size={[2.5, 8, 50]} at={[24, 11, 0]} mat={M.dark} />
      </group>

      {/* breadboard, collée au scratch */}
      <group position={[50, Y0, -5]}>
        <Box size={[40, 1, 18]} at={[0, 0.4, 0]} mat={M.velcro} />
        <Box size={[55, 9, 83]} at={[0, 4.5, 0]} mat={M.bread} />
        <Box size={[3, 0.6, 81]} at={[-23, 9.2, 0]} mat={M.red} />
        <Box size={[3, 0.6, 81]} at={[23, 9.2, 0]} mat={M.pcbBlue} />
      </group>

      {/* câbles Dupont entre la carte et la breadboard */}
      <Wire pts={arc([36, Y0 + 9, 10], [-42, Y0 + 14, 26], 40)} r={0.9} mat={M.orange} />
      <Wire pts={arc([56, Y0 + 9, -30], [-62, Y0 + 14, -14], 46)} r={0.9} mat={M.yellow} />

      {/* faisceau vers la citrouille : il passe sous le tissu jusqu'à la tête */}
      <Wire pts={toPumpkin([40, Y0 + 9, 30], 14)} r={1.1} mat={M.red} />
      <Wire pts={toPumpkin([60, Y0 + 9, 30], 4)} r={1.1} mat={M.yellow} />
      <Wire pts={toPumpkin([-40, Y0 + 14, 30], -6)} r={1.1} mat={M.orange} />
      <Wire pts={toPumpkin([-60, Y0 + 14, 30], -16)} r={1.6} mat={M.cable} />
    </group>
  );
}
