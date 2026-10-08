import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Canvas } from "@react-three/fiber";
import { useProgress } from "@react-three/drei";
import { ArrowDown, ArrowRight, BellRing, DoorOpen, Eye, ScanFace, Smartphone, Thermometer, VideoOff, CreditCard } from "lucide-react";
import { Stage } from "./Stage";
import { buildStops, type Stop } from "./timeline";

const CHAPTERS = ["Concept", "En situation", "Intérieur", "Accès", "Supervision"];

export default function Landing() {
  const sections = useRef<HTMLElement[]>([]);
  const stops = useRef<Stop[]>([]);
  const [active, setActive] = useState(0);

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
        <a className="lp-btn lp-btn-ghost" href="./">Tableau de bord <ArrowRight size={16} /></a>
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
              Un pot en céramique, une plante, et à l'intérieur une caméra, six capteurs et un contrôleur connecté.
              Sentinel veille sur vos baies serveurs sans jamais ressembler à un équipement de sécurité.
            </p>
            <dl className="lp-stats">
              <div><dt>Capteurs</dt><dd>6</dd></div>
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
            <p className="lp-lead">Sur une étagère de la salle serveur, il passe pour une plante d'intérieur. Il détecte, score la menace et alerte.</p>
            <ul className="lp-features">
              <Feature icon={<Eye size={18} />} title="Intrusion">Présence devant la baie, approche, mouvement hors horaires.</Feature>
              <Feature icon={<DoorOpen size={18} />} title="Manipulation">Ouverture de la porte, choc ou inclinaison du boîtier.</Feature>
              <Feature icon={<Thermometer size={18} />} title="Environnement">Température et humidité hors plage, projection à 15 minutes.</Feature>
              <Feature icon={<VideoOff size={18} />} title="Sabotage">Objectif masqué, boîtier muet ou déconnecté.</Feature>
            </ul>
            <p className="lp-note"><BellRing size={15} /> Score de menace, buzzer sur place et alerte instantanée sur le tableau de bord.</p>
          </div>
        </section>

        <section ref={keep(2)} className="lp-sec lp-xtall">
          <div className="lp-inner lp-right">
            <span className="lp-kicker">02 · À l'intérieur</span>
            <h2>Une plante en façade, un système complet derrière la porte.</h2>
            <p className="lp-lead">
              La demi-coque pivote sur sa charnière. L'électronique est logée dans le corps du pot, la caméra se cache dans le feuillage
              et suit les mouvements grâce à son servo.
            </p>
            <ol className="lp-parts">
              <li><b>ESP32-CAM</b><span>caméra orientable</span></li>
              <li><b>Arduino UNO Q</b><span>contrôleur, Wi-Fi</span></li>
              <li><b>PIR · ultrasons</b><span>présence et approche</span></li>
              <li><b>DHT22</b><span>température, humidité</span></li>
              <li><b>Accéléromètre</b><span>choc, inclinaison</span></li>
              <li><b>Porte · RFID</b><span>infrarouge, badges</span></li>
            </ol>
            <p className="lp-fine">Modèle 3D simplifié, emplacements des composants indicatifs.</p>
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
                <p>Un badge autorisé arme ou désarme le système et verrouille la porte. Chaque passage est journalisé.</p>
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
              <a className="lp-btn" href="./">Ouvrir le tableau de bord <ArrowRight size={16} /></a>
              <span className="lp-fine"><Smartphone size={14} /> Navigateur, ordinateur ou téléphone</span>
            </div>
          </div>
        </section>
        <footer className="lp-foot">Sentinel · surveillance physique discrète pour salles serveur</footer>
      </main>
    </>
  );
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

/** Voile de chargement tant que le modèle 3D n'est pas prêt. */
function Loader() {
  const { active, progress } = useProgress();
  const [gone, setGone] = useState(false);
  useEffect(() => {
    if (!active && progress >= 100) { const t = window.setTimeout(() => setGone(true), 250); return () => window.clearTimeout(t); }
  }, [active, progress]);
  return (
    <div className={`lp-loader ${gone ? "done" : ""}`} aria-hidden={gone}>
      <Shield />
      <div className="lp-loader-bar"><i style={{ width: `${progress}%` }} /></div>
    </div>
  );
}
