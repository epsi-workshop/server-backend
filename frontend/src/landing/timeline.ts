/**
 * Chorégraphie de la scène 3D, pilotée par le défilement.
 * Chaque section de la page déclare une ou plusieurs poses ; entre deux poses, toutes les valeurs
 * sont interpolées (courbe douce), puis la scène les rejoint avec un amortissement.
 */

type V3 = [number, number, number];

export type Pose = {
  cam: V3; // position de la caméra
  look: V3; // point visé
  pot: V3; // position du pot (base posée à y = pot[1])
  rot: number; // orientation du pot quand il ne tourne pas (radians)
  spin: number; // 1 = rotation continue, 0 = orientation fixe
  scale: number;
  door: number; // 0 fermée, 1 ouverte
  floor: number; // hauteur du sol réfléchissant (descend pour révéler la baie)
  room: number; // mur de la salle serveur
  inside: number; // éclairage intérieur et repères des composants
  access: number; // carte de reconnaissance faciale et badge RFID
  devices: number; // ordinateur portable et téléphone
};

const FLOOR_DOWN = -3.25; // sol abaissé : la baie (hauteur 3,2) apparaît sous le pot
export const RACK_X = -1.4; // la baie est fixe, le pot s'y pose dans les sections 2 et 3
// Orientation où la porte (charnière du modèle) fait face à la caméra.
export const DOOR_FACING = -0.31;

const base: Pose = {
  cam: [0, 1.4, 6.4], look: [0, 1, 0], pot: [0, 0, 0], rot: DOOR_FACING, spin: 0, scale: 1,
  door: 0, floor: 0, room: 0, inside: 0, access: 0, devices: 0,
};
const pose = (p: Partial<Pose>): Pose => ({ ...base, ...p });

/** Poses par section, dans l'ordre de la page. Deux poses : la section en scrolle une vers l'autre. */
export const SECTIONS: Pose[][] = [
  // 1. Présentation : le pot seul sur le sol noir, il tourne.
  [pose({ cam: [0, 1.5, 6.6], look: [0, 1.05, 0], pot: [1.55, 0, 0], spin: 1, scale: 1.15 })],
  // 2. En situation : le sol s'enfonce, la baie apparaît sous le pot, le mur de la salle se dessine.
  [pose({ cam: [-0.4, 0.7, 10.6], look: [-0.2, -0.6, 0], pot: [RACK_X, 0, 0], rot: DOOR_FACING + 0.5, floor: FLOOR_DOWN, room: 1 })],
  // 3. À l'intérieur : la caméra s'approche, puis la porte pivote.
  [
    pose({ cam: [0.15, 1.35, 5.6], look: [-0.25, 0.95, 0], pot: [RACK_X, 0, 0], rot: DOOR_FACING - 0.35, floor: FLOOR_DOWN, room: 1, inside: 0.15 }),
    pose({ cam: [0.2, 1.3, 5.2], look: [-0.2, 0.92, 0], pot: [RACK_X, 0, 0], rot: DOOR_FACING - 0.35, door: 1, floor: FLOOR_DOWN, room: 1, inside: 1 }),
  ],
  // 4. Contrôle d'accès : retour sur le sol, carte de reconnaissance faciale et badge.
  [pose({ cam: [0, 1.35, 6.6], look: [0, 1.0, 0], pot: [0.55, 0, 0], rot: DOOR_FACING - 0.15, access: 1 })],
  // 5. Supervision : ordinateur et téléphone, le pot en retrait.
  [pose({ cam: [0, 2.1, 9.8], look: [0, 0.8, 0], pot: [0.15, 0, 0.4], spin: 0.35, scale: 0.7, devices: 1 })],
];

const KEYS = Object.keys(base) as (keyof Pose)[];

export function mix(a: Pose, b: Pose, t: number): Pose {
  const out = {} as Record<keyof Pose, unknown>;
  for (const k of KEYS) {
    const x = a[k], y = b[k];
    out[k] = Array.isArray(x) ? (x as V3).map((v, i) => v + ((y as V3)[i] - v) * t) : (x as number) + ((y as number) - (x as number)) * t;
  }
  return out as Pose;
}

const smooth = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);

/** Points d'ancrage (en pixels de défilement) : la pose est tenue tant que la section couvre l'écran. */
export type Stop = { at: number; pose: Pose };

export function buildStops(sections: HTMLElement[], vh: number): Stop[] {
  const stops: Stop[] = [];
  sections.forEach((el, i) => {
    const poses = SECTIONS[i];
    const start = el.offsetTop;
    const span = Math.max(0, el.offsetHeight - vh);
    if (poses.length === 1) {
      stops.push({ at: start, pose: poses[0] }, { at: start + span, pose: poses[0] });
    } else {
      poses.forEach((p, k) => stops.push({ at: start + (span * k) / (poses.length - 1), pose: p }));
    }
  });
  return stops;
}

export function poseAt(stops: Stop[], y: number): Pose {
  if (!stops.length) return SECTIONS[0][0];
  if (y <= stops[0].at) return stops[0].pose;
  for (let i = 1; i < stops.length; i++) {
    const a = stops[i - 1], b = stops[i];
    if (y <= b.at) return b.at === a.at ? b.pose : mix(a.pose, b.pose, smooth((y - a.at) / (b.at - a.at)));
  }
  return stops[stops.length - 1].pose;
}

/** Écran en portrait : on centre la caméra sur le sujet et on recule pour tout garder dans le cadre. */
export function adaptToViewport(p: Pose, aspect: number): Pose {
  if (aspect >= 1) return p;
  const k = Math.min(1.9, 1.15 / aspect);
  const focusX = p.devices > 0.5 ? 1.6 * p.devices : p.pot[0] + 0.7 * p.access;
  const lookX = p.look[0] + (focusX - p.look[0]) * 0.9;
  return {
    ...p,
    // Visée abaissée : le sujet remonte dans la moitié haute, les textes occupent le bas de l'écran.
    look: [lookX, p.look[1] - 1.15, p.look[2]],
    cam: [lookX + (p.cam[0] - p.look[0]), p.cam[1] - 0.6, p.cam[2] * k],
  };
}
