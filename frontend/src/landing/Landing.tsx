import { useEffect, useLayoutEffect, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { Canvas } from "@react-three/fiber";
import { useProgress } from "@react-three/drei";
import { ArrowDown, ArrowRight, BellRing, Eye, Pause, Play, ScanFace, Smartphone, Thermometer, VideoOff, CreditCard } from "lucide-react";
import { Stage } from "./Stage";
import { buildStops, type Stop } from "./timeline";

// Adresse du tableau de bord : ./ par défaut (même dossier), /dashboard/ sur l'UNO Q (deploy/uno-q).
const DASHBOARD_URL: string = import.meta.env.VITE_DASHBOARD_URL || "./";
const CHAPTERS = ["Concept", "En situation", "Système", "Accès", "Supervision"];

export default function Landing() {
  const sections = useRef<HTMLElement[]>([]);
  const stops = useRef<Stop[]>([]);
  const [active, setActive] = useState(0);
  // Mode démo : activé par le bouton, ou d'office avec ?demo dans l'adresse (borne, salon).
  const [demo, setDemo] = useState(() => new URLSearchParams(window.location.search).has("demo"));
  useDemo(sections, demo, () => setDemo(false));

  // Points d'ancrage du défilement, recalculés quand la mise en page change.
  useLayoutEffect(() => {
    const update = () => { stops.current = buildStops(sections.current, window.innerHeight); };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(document.body);
    document.fonts?.ready.then(update);
    return () => ro.disconnect();
  }, []);

  // Chapitre actif (navigation latérale) et apparition des textes.
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("in");
        setActive(sections.current.indexOf(e.target as HTMLElement));
      }
    }, { rootMargin: "-45% 0px -45% 0px" });
    sections.current.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, []);

  const keep = (i: number) => (el: HTMLElement | null) => { if (el) sections.current[i] = el; };
  const go = (i: number) => sections.current[i]?.scrollIntoView({ behavior: "smooth" });

  return (
    <>
      <Canvas className="lp-canvas" dpr={[1, 2]} camera={{ fov: 32, near: 0.1, far: 60, position: [0, 1.5, 6.6] }}
        gl={{ antialias: true }} aria-hidden="true">
        <Stage stops={stops} />
      </Canvas>
      <Loader />

      <header className="lp-top">
        <a className="lp-brand" href="#" onClick={(e) => { e.preventDefault(); go(0); }}>
          <Shield /> Sentinel
        </a>
        <div className="lp-top-actions">
          <button className={`lp-btn lp-btn-ghost lp-demo ${demo ? "on" : ""}`} data-demo-toggle onClick={() => setDemo((v) => !v)} aria-pressed={demo}>
            {demo ? <><Pause size={15} /> Arrêter la démo</> : <><Play size={15} /> Mode démo</>}
          </button>
          <a className="lp-btn lp-btn-ghost" href={DASHBOARD_URL}>Tableau de bord <ArrowRight size={16} /></a>
        </div>
      </header>

      <nav className="lp-rail" aria-label="Chapitres">
        {CHAPTERS.map((c, i) => (
          <button key={c} className={i === active ? "on" : ""} onClick={() => go(i)} aria-current={i === active}>
            <em>{c}</em><span>{String(i + 1).padStart(2, "0")}</span>
          </button>
        ))}
      </nav>

      <main className="lp">
        <section ref={keep(0)} className="lp-sec lp-hero in">
          <div className="lp-inner lp-left">
            <span className="lp-kicker">Sentinel · surveillance physique discrète</span>
            <h1>La sécurité qui se fond dans le décor.</h1>
            <p className="lp-lead">
              Une citrouille animée d'Halloween, comme on en trouve en magasin. Avec elle : une caméra, quatre capteurs
              et un contrôleur connecté. Sentinel veille sur vos baies serveurs sans jamais ressembler à un équipement de sécurité.
            </p>
            <dl className="lp-stats">
              <div><dt>Capteurs</dt><dd>4</dd></div>
              <div><dt>Caméra</dt><dd>Orientable</dd></div>
              <div><dt>Alertes</dt><dd>Temps réel</dd></div>
            </dl>
            <button className="lp-scroll" onClick={() => go(1)}><ArrowDown size={16} /> Découvrir</button>
          </div>
        </section>

        <section ref={keep(1)} className="lp-sec lp-tall">
          <div className="lp-inner lp-right">
            <span className="lp-kicker">01 · En situation</span>
            <h2>Posé sur la baie, il veille.</h2>
            <p className="lp-lead">Sur une étagère de la salle serveur, il passe pour une simple décoration. Il détecte, score la menace et alerte.</p>
            <ul className="lp-features">
              <Feature icon={<Eye size={18} />} title="Intrusion">Présence devant la baie, personne détectée par la caméra, mouvement hors horaires.</Feature>
              <Feature icon={<Thermometer size={18} />} title="Environnement">Température et humidité hors plage, projection à 15 minutes.</Feature>
              <Feature icon={<VideoOff size={18} />} title="Sabotage">Objectif masqué, boîtier muet ou déconnecté.</Feature>
            </ul>
            <p className="lp-note"><BellRing size={15} /> Score de menace, buzzer sur place et alerte instantanée sur le tableau de bord.</p>
          </div>
        </section>

        <section ref={keep(2)} className="lp-sec lp-xtall">
          <div className="lp-inner lp-right">
            <span className="lp-kicker">02 · Le système</span>
            <h2>Une décoration en façade, un système complet derrière.</h2>
            <p className="lp-lead">
              Caméra et laser dans le nez, lecteur RFID dans la tête, DHT22 sous la cape, d'où dépasse le dôme du détecteur
              PIR. Derrière, l'Arduino UNO Q et la breadboard ; les câbles passent sous la citrouille.
            </p>
            <ol className="lp-parts">
              <li><b>ESP32-CAM · laser</b><span>cachés dans le nez</span></li>
              <li><b>Arduino UNO Q</b><span>contrôleur, Wi-Fi</span></li>
              <li><b>Détecteur PIR</b><span>présence, dépasse sous la cape</span></li>
              <li><b>DHT22</b><span>température, humidité, sous la cape</span></li>
              <li><b>Lecteur RFID</b><span>dans la tête, armement</span></li>
            </ol>
            <p className="lp-fine">Modèle 3D simplifié.</p>
          </div>
        </section>

        <section ref={keep(3)} className="lp-sec lp-tall">
          <div className="lp-inner lp-left">
            <span className="lp-kicker">03 · Contrôle d'accès</span>
            <h2>Il reconnaît les visages. Et les badges.</h2>
            <div className="lp-duo">
              <div>
                <span className="lp-ico"><ScanFace size={20} /></span>
                <h3>Reconnaissance faciale</h3>
                <p>La caméra identifie les membres de l'équipe enregistrés. Un visage inconnu déclenche une alerte critique, avec capture.</p>
              </div>
              <div>
                <span className="lp-ico"><CreditCard size={20} /></span>
                <h3>Badge RFID</h3>
                <p>Le badge, présenté devant la citrouille (le lecteur est dans la tête), sert uniquement à armer ou désarmer le système. Seuls les badges enregistrés sont acceptés, et chaque passage est journalisé.</p>
              </div>
            </div>
          </div>
        </section>

        <section ref={keep(4)} className="lp-sec lp-tall lp-last">
          <div className="lp-inner lp-left">
            <span className="lp-kicker">04 · Supervision</span>
            <h2>Toutes les alertes, sur ordinateur et sur mobile.</h2>
            <p className="lp-lead">
              Le tableau de bord temps réel affiche l'état du boîtier, le niveau de menace, le flux caméra et l'historique des capteurs.
              Rôles administrateur, opérateur et lecteur ; chaque action sensible est journalisée.
            </p>
            <div className="lp-cta">
              <a className="lp-btn" href={DASHBOARD_URL}>Ouvrir le tableau de bord <ArrowRight size={16} /></a>
              <span className="lp-fine"><Smartphone size={14} /> Navigateur, ordinateur ou téléphone</span>
            </div>
          </div>
        </section>
        <footer className="lp-foot">Sentinel · surveillance physique discrète pour salles serveur</footer>
      </main>
    </>
  );
}

/**
 * Programme du mode démo, chapitre par chapitre. `to` : début ou fin de la section (une section
 * haute fait défiler ses poses entre les deux) ; `move` : durée du défilement ; `hold` : temps laissé
 * aux animations (caméra amortie, porte des écrans, cycle du badge 4,6 s, carte du visage 2 × 3,6 s).
 */
const DEMO_STEPS: { section: number; to: "start" | "end"; move: number; hold: number }[] = [
  { section: 0, to: "start", move: 3200, hold: 6000 },
  { section: 1, to: "start", move: 2800, hold: 3500 },
  { section: 1, to: "end", move: 2200, hold: 2500 },
  { section: 2, to: "start", move: 2800, hold: 2500 },
  { section: 2, to: "end", move: 4500, hold: 5000 },
  { section: 3, to: "start", move: 2800, hold: 4500 },
  { section: 3, to: "end", move: 2200, hold: 4500 },
  { section: 4, to: "start", move: 2800, hold: 5000 },
  { section: 4, to: "end", move: 1800, hold: 4000 },
];

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** Enchaîne les étapes de DEMO_STEPS en boucle ; toute action de l'utilisateur sur le défilement l'arrête. */
function useDemo(sections: MutableRefObject<HTMLElement[]>, on: boolean, stop: () => void) {
  const stopRef = useRef(stop);
  stopRef.current = stop;
  useEffect(() => {
    if (!on) return;
    let alive = true;
    let raf = 0;
    let timer = 0;
    const wait = (ms: number) => new Promise<void>((r) => { timer = window.setTimeout(r, ms); });
    const scrollTo = (y: number, ms: number) => new Promise<void>((r) => {
      const from = window.scrollY, t0 = performance.now();
      const frame = (now: number) => {
        if (!alive) return r();
        const k = Math.min(1, (now - t0) / ms);
        window.scrollTo({ top: from + (y - from) * easeInOut(k), behavior: "instant" });
        if (k < 1) raf = requestAnimationFrame(frame); else r();
      };
      raf = requestAnimationFrame(frame);
    });
    const target = (i: number, to: "start" | "end") => {
      const el = sections.current[i];
      if (!el) return 0;
      return to === "start" ? el.offsetTop : el.offsetTop + Math.max(0, el.offsetHeight - window.innerHeight);
    };
    (async () => {
      while (alive) {
        for (const s of DEMO_STEPS) {
          if (!alive) return;
          await scrollTo(target(s.section, s.to), s.move);
          if (!alive) return;
          await wait(s.hold);
        }
      }
    })();
    // L'utilisateur reprend la main : molette, toucher ou clavier (hors bouton de la démo).
    const interrupt = (e: Event) => {
      if (e.type === "keydown" && (e.target as HTMLElement | null)?.closest?.("[data-demo-toggle]")) return;
      stopRef.current();
    };
    const opts = { passive: true } as const;
    window.addEventListener("wheel", interrupt, opts);
    window.addEventListener("touchstart", interrupt, opts);
    window.addEventListener("keydown", interrupt);
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      window.clearTimeout(timer);
      window.removeEventListener("wheel", interrupt);
      window.removeEventListener("touchstart", interrupt);
      window.removeEventListener("keydown", interrupt);
    };
  }, [on, sections]);
}

function Feature({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return <li><span className="lp-ico">{icon}</span><div><b>{title}</b><span>{children}</span></div></li>;
}

function Shield() {
  return (
    <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true">
      <path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7L16 2Z" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="16" cy="15" r="4.2" fill="currentColor" />
    </svg>
  );
}

/** Voile de chargement le temps que la scène 3D démarre. */
function Loader() {
  const { active, progress } = useProgress();
  const [gone, setGone] = useState(false);
  useEffect(() => {
    // Plus rien à charger (le modèle est procédural, seules les polices et textures passent ici).
    if (!active) { const t = window.setTimeout(() => setGone(true), 400); return () => window.clearTimeout(t); }
  }, [active]);
  return (
    <div className={`lp-loader ${gone ? "done" : ""}`} aria-hidden={gone}>
      <Shield />
      <div className="lp-loader-bar"><i style={{ width: `${active ? progress : 100}%` }} /></div>
    </div>
  );
}
